# -*- coding: utf-8 -*-
"""魔流 · 账本结构自迁移（6.0.0 引入，计划在后续版本整块下线）

把老的「整包」键拆进 **MP 插件专属库**的 5 张表（``db.py`` 声明，MP 启动时建表）：

    tag_state         -> mf_seed / mf_resource（补丁）
    tag_groups        -> mf_resource
    site_rules + site_caps -> mf_site
    crossseed_sources -> mf_resource.hrs
    身份表由代码常量落盘；任务表由当前任务配置落盘。

铁律：
- **只增不删**：旧 kv 键原样保留（另存 ``schema_v5_backup:<key>`` 作回滚点），
  迁移完成只落一个完成戳 ``schema_v5_done`` + 行数清单 ``schema_v5_manifest``；
- **幂等可续跑**：游标 ``schema_v5_cursor`` 记录 stage+offset，中断后从断点继续；
- **失败零副作用**：任何异常都不置完成戳、不删旧键 → 旧代码照常能跑；
- **任何版本都能自愈**：闸门看完成戳，不绑插件版本（<6.0 直跳 6.1+ 会被拦）。

升级闸门（Master 16:43）：<6.0 直跳 6.1+ → 提示先升 6.0.0；≥6.1 但迁移没做好 → **不让升**。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .. import db as mfdb
from .. import tables as T

MIGRATE_INTERVAL_MINUTES = 1.0     # 迁移期间每分钟推一块
MIGRATE_CHUNK = 800                # 单次调用最多写多少行
BACKED_KEY = "schema_v5_backed"
MANIFEST_KEY = "schema_v5_manifest"      # 迁完记行数（校验「准备做好了没」）
V6_MARKER_KEY = "schema_v6_done"         # 6.1.0 收敛（影子 JSON → 真列）完成戳
V6_MANIFEST_KEY = "schema_v6_manifest"
PUBDATE_MARKER_KEY = "schema_v6_pubdates"   # 6.1.6 发布时间 → 种子表 published_at 镜像完成戳
LAST_VERSION_KEY = "last_version"        # 上次运行的插件版本（判「跳过 6.0」）
MIN_MIGRATION_VERSION = "6.0.0"          # 迁移必须在 6.0.x 上完成
GATE_VERSION = "6.1.0"                   # 6.1+ 强制要求迁移已完成
LEGACY_KEYS = ("tag_state", "tag_groups", "site_rules", "site_caps", "crossseed_sources")


def _ver_tuple(v: Any) -> tuple:
    out = []
    for part in str(v or "").split("."):
        out.append(int("".join(ch for ch in part if ch.isdigit()) or 0))
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def _ver_ge(a: Any, b: Any) -> bool:
    return _ver_tuple(a) >= _ver_tuple(b)


def _ver_lt(a: Any, b: Any) -> bool:
    return _ver_tuple(a) < _ver_tuple(b)


def _norm_res_id(gid: Any) -> str:
    """老 group id → 资源主键：老键是 ``fp:<hash>``，种子侧 fp 是裸 hash，必须归一。"""
    s = str(gid or "").strip()
    return s[3:] if s.startswith("fp:") else s


class MigrateMixin:
    """账本 5 表自迁移 worker（一次性）。"""

    # ------------------------------------------------------------ 基础

    def _mf_session(self):
        """插件自有库会话（MP 官方 `get_database()`）。"""
        handle = self.get_database()
        return handle.session()

    def _migrate_site_ids(self) -> Dict[str, int]:
        """域名/站点名 -> MP site_id。"""
        out: Dict[str, int] = {}
        try:
            rows = self._reseed_mp_sites() or []
        except Exception:  # noqa: BLE001
            rows = []
        for row in rows:
            sid = row.get("id")
            if sid is None:
                continue
            for key in (str(row.get("domain") or "").strip().lower(),
                        str(row.get("name") or "").strip().lower()):
                if key:
                    out[key] = int(sid)
        return out

    def _migrate_task_ids(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for tid, cfg in (getattr(self, "_task_configs", {}) or {}).items():
            tid = str(tid)
            out[tid] = tid
            nm = str(getattr(cfg, "name", "") or "").strip().lower()
            if nm:
                out[nm] = tid
        return out

    def _mig_ident_map(self) -> Dict[str, str]:
        """资源 id(fp) -> 身份（老记录里身份散在种子账本：sub/origin_sub/asset）。"""
        cached = getattr(self, "_mig_ident_cache", None)
        if cached is not None:
            return cached
        out: Dict[str, str] = {}
        try:
            state = self.get_data("tag_state") or {}
        except Exception:  # noqa: BLE001
            state = {}
        for rec in state.values():
            if not isinstance(rec, dict):
                continue
            fp = str(rec.get("fp") or "").strip().lower()
            if not fp:
                continue
            code = str(rec.get("sub") or rec.get("origin_sub") or "").strip()
            if not code and rec.get("asset"):
                code = T.IDENT_RESOURCE
            if code:
                out[fp] = code
        self._mig_ident_cache = out
        return out

    # ------------------------------------------------------------ 计划 / 状态

    def _migrate_plan(self) -> List[str]:
        stages: List[str] = []
        if self.get_data("site_rules") or self.get_data("site_caps"):
            stages.append(T.TABLE_SITE)
        if self.get_data("tag_groups"):
            stages.append(T.TABLE_RESOURCE)
        if self.get_data("tag_state"):
            stages.append(T.TABLE_SEED)
        if getattr(self, "_task_configs", None):
            stages.append(T.TABLE_TASK)
        stages.append(T.TABLE_IDENTITY)
        return stages

    def migrate_done(self) -> bool:
        return bool(self.get_data(T.MARKER_KEY))

    def backfill_done(self) -> bool:
        """6.1.0 收敛（影子 JSON → 真列）是否已跑完。"""
        return bool(self.get_data(V6_MARKER_KEY))

    def _legacy_present(self) -> bool:
        for key in LEGACY_KEYS:
            try:
                if self.get_data(key):
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    # ------------------------------------------------------------ 升级闸门

    def migrate_gate(self) -> Dict[str, Any]:
        """版本闸门：<6.0 直跳 6.1+ → 提示先升 6.0；≥6.1 而迁移没做好 → 不让升。"""
        cur = str(getattr(self, "plugin_version", "") or "")
        last = str(self.get_data(LAST_VERSION_KEY) or "")
        done = self.migrate_done()
        need = bool(self._legacy_present())
        reason = ""
        if _ver_ge(cur, GATE_VERSION):
            if last and _ver_lt(last, MIN_MIGRATION_VERSION) and need:
                reason = (f"检测到从 {last} 直接升级到 {cur}，跳过了 {MIN_MIGRATION_VERSION} 的数据迁移。"
                          f"请先升级到 {MIN_MIGRATION_VERSION} 跑完迁移，再升级到 {GATE_VERSION} 及以上。")
            elif not done and need:
                reason = (f"数据迁移尚未完成（缺 {T.MARKER_KEY}）。"
                          f"请先在 {MIN_MIGRATION_VERSION} 上完成迁移，再升级到 {GATE_VERSION} 及以上。")
        return {
            "current": cur, "last": last, "gate_from": GATE_VERSION,
            "min_migration": MIN_MIGRATION_VERSION, "migrated": done,
            "legacy_present": need, "blocked": bool(reason), "reason": reason,
        }

    def migrate_record_version(self) -> None:
        cur = str(getattr(self, "plugin_version", "") or "")
        if not cur:
            return
        try:
            if str(self.get_data(LAST_VERSION_KEY) or "") != cur:
                self.save_data(key=LAST_VERSION_KEY, value=cur)
        except Exception:  # noqa: BLE001
            pass

    def _table_counts(self) -> Dict[str, int]:
        """当前 5 表行数（校验「搬家没丢行」用）。"""
        out: Dict[str, int] = {}
        try:
            from sqlalchemy import func, select as sa_select
            sess = self._mf_session()
            try:
                for key, model in ((T.TABLE_SITE, mfdb.SiteRow), (T.TABLE_RESOURCE, mfdb.ResourceRow),
                                   (T.TABLE_SEED, mfdb.SeedRow), (T.TABLE_TASK, mfdb.TaskRow),
                                   (T.TABLE_IDENTITY, mfdb.IdentityRow)):
                    out[key] = int(sess.execute(sa_select(func.count()).select_from(model)).scalar() or 0)
            finally:
                sess.close()
        except Exception as err:  # noqa: BLE001
            self._log(f"账本:校验行数失败:{err}", "warning")
        return out

    def migrate_verify(self) -> Dict[str, Any]:
        """校验「搬家没丢行」：完成戳 + **现在表里行数 ≥ 当时搬进多少**（旧键仍在=可回滚）。

        注意：不能拿旧键当下限——旧键会随运行继续增长（新种子），那样永远对不上。
        """
        done = self.migrate_done()
        manifest = dict(self.get_data(MANIFEST_KEY) or {})
        got = {str(k): int(v or 0) for k, v in (manifest.get("counts") or {}).items()}
        now = self._table_counts()
        ok = bool(done) and bool(now) and all(now.get(k, 0) >= v for k, v in got.items())
        return {"done": done, "ok": ok, "manifest": manifest, "counts": got, "now": now,
                "legacy": {T.TABLE_SEED: len(self.get_data("tag_state") or {}),
                           T.TABLE_RESOURCE: len(self.get_data("tag_groups") or {})}}

    def migrate_pending(self) -> bool:
        if getattr(self, "_gate_blocked", None):
            return False
        if not self.migrate_done():
            return bool(self._migrate_plan())
        if not self.get_data(PUBDATE_MARKER_KEY):
            return True                          # 6.1.6：还欠一次「发布时间落表」镜像
        return not self.backfill_done()          # 5 表就位 → 还欠一次 6.1 收敛回填

    def migrate_status(self) -> Dict[str, Any]:
        return {
            "done": self.migrate_done(),
            "marker": self.get_data(T.MARKER_KEY) or None,
            "cursor": self.get_data(T.CURSOR_KEY) or None,
            "backed": bool(self.get_data(BACKED_KEY)),
            "plan": self._migrate_plan(),
            "chunk": MIGRATE_CHUNK,
            "interval_minutes": MIGRATE_INTERVAL_MINUTES,
            "tables": list(mfdb.table_names().values()),
            "gate": self.migrate_gate(),
            "verify": self.migrate_verify(),
            "backfill": {
                "done": self.backfill_done(),
                "manifest": self.get_data(V6_MANIFEST_KEY) or None,
            },
        }

    # ------------------------------------------------------------ 备份 / 主循环

    def _migrate_backup_once(self) -> None:
        if self.get_data(BACKED_KEY):
            return
        saved: List[str] = []
        for key in LEGACY_KEYS:
            try:
                val = self.get_data(key)
            except Exception:  # noqa: BLE001
                continue
            if val in (None, {}, []):
                continue
            try:
                self.save_data(key=f"{T.BACKUP_PREFIX}{key}", value=val)
                saved.append(key)
            except Exception as err:  # noqa: BLE001
                self._log(f"账本迁移:备份 {key} 失败:{err}", "warning")
        self.save_data(key=BACKED_KEY, value={"at": time.time(), "keys": saved})
        if saved:
            self._log(f"账本迁移:已备份旧键 {','.join(saved)}")

    def migrate_scan(self, force: bool = False) -> Dict[str, Any]:
        """迁移 worker 主体：每次推一块，推完落完成戳；5 表就位后再做一次 6.1 收敛回填。"""
        if getattr(self, "_gate_blocked", None):
            return {"ok": False, "blocked": self._gate_blocked.get("reason")}
        if self.migrate_done():
            out = self._backfill_scan(force=force)
            # ★ 6.1.6：顺手把 TaskState.pub_dates → 种子表 published_at 镜像一次（幂等、单独打戳）
            try:
                out = dict(out or {})
                out["pubdates"] = self._sync_pubdate_pass(force=force)
            except Exception as err:  # noqa: BLE001
                self._log(f"发布时间落表:同步失败（下次重试）:{err}", "warning")
            return out
        stages = self._migrate_plan()
        if not stages:
            self.save_data(key=T.MARKER_KEY, value={"at": time.time(), "note": "no-legacy"})
            return {"ok": True, "note": "no-legacy"}
        self._migrate_backup_once()

        cur = dict(self.get_data(T.CURSOR_KEY) or {})
        stage = str(cur.get("stage") or stages[0])
        if stage not in stages:
            stage, cur["offset"] = stages[0], 0
        offset = int(cur.get("offset") or 0)

        written = 0
        while written < MIGRATE_CHUNK:
            budget = MIGRATE_CHUNK - written
            n = self._migrate_stage(stage, offset, budget)
            if n < 0:                                   # ★ 出错：本轮不推进、不落戳
                return {"ok": False, "error": stage, "stage": stage, "offset": offset}
            if n == 0:                                  # 本阶段完成 → 下一阶段
                idx = stages.index(stage) + 1
                if idx >= len(stages):
                    counts = self._migrate_counts()
                    self.save_data(key=T.CURSOR_KEY, value={})
                    self.save_data(key=MANIFEST_KEY, value={"at": time.time(), "counts": counts})
                    self.save_data(key=T.MARKER_KEY, value={"at": time.time(), "version": T.SCHEMA_VERSION})
                    self.migrate_record_version()
                    self._reset_ledger_stores()
                    self._log(f"账本迁移:完成（5 表入插件库，旧键保留可回滚）{counts}")
                    return {"ok": True, "done": True, "written": written, "counts": counts}
                stage, offset = stages[idx], 0
            else:
                written += n
                offset += n
            self.save_data(key=T.CURSOR_KEY, value={"stage": stage, "offset": offset})
        return {"ok": True, "done": False, "stage": stage, "offset": offset, "written": written}

    def _backfill_scan(self, force: bool = False) -> Dict[str, Any]:
        """6.1.0：影子 JSON → 真列（幂等；影子保留，可回滚）。"""
        if self.backfill_done() and not force:
            return {"ok": True, "skipped": "backfilled"}
        try:
            counts = self._ledger().backfill_columns()
        except Exception as err:  # noqa: BLE001
            self._log(f"账本收敛:回填失败（下次重试）:{err}", "error")
            return {"ok": False, "error": "backfill", "detail": str(err)}
        self.save_data(key=V6_MANIFEST_KEY, value={"at": time.time(), "counts": counts})
        self.save_data(key=V6_MARKER_KEY, value={"at": time.time(), "version": "6.1"})
        self._reset_ledger_stores()
        self._log(f"账本收敛:完成（JSON 兜底 → 真列，影子保留可回滚）{counts}")
        return {"ok": True, "done": True, "counts": counts}

    def _sync_pubdate_pass(self, force: bool = False) -> Dict[str, Any]:
        """6.1.6：把边缘 TaskState.pub_dates 一次性镜像进种子表 published_at（幂等）。

        Ti 的真值仍然是 TaskState（Redis 热层）；种子表列只是 5 表契约里的位置——
        但列不能永远空着，否则回滚/新建库后 Ti 无据可依。打 ``PUBDATE_MARKER_KEY`` 戳，
        见戳即跳（force=True 可强制重跑）。
        """
        if not force and self.get_data(PUBDATE_MARKER_KEY):
            return {"ok": True, "skipped": "done"}
        states = getattr(getattr(self, "_store", None), "task_states", None)
        if states is None:
            self._log("发布时间落表:取不到任务状态存储，稍后重试", "warning")
            return {"ok": False, "error": "no-state-store"}
        # ★ 6.1.8 修：TaskStateStore 的迭代 API 是 ``list_all()``（不是 ``all()``）——
        #   旧写法 hasattr(.,"all") 为 False → 静默拿到 [] → tasks=0、published_at 永远不动。
        getter = getattr(states, "list_all", None) or getattr(states, "all", None)
        if getter is None:
            self._log("发布时间落表:任务状态存储不支持枚举，稍后重试", "warning")
            return {"ok": False, "error": "no-enum"}
        rows = list(getter() or [])
        try:
            # ★ 6.1.9 修：要的是 **账本 store**（SeedLedgerStore，有 put_many），
            #   不是 ``get_backend()`` 那个 LedgerBackend（只有 load_*/save_* dict API）——
            #   6.1.7/6.1.8 调 ``ledger.put_many`` 全部 AttributeError（7 条 warning）。
            store = self._tag_state()
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "error": "ledger", "detail": str(err)}
        patched = 0
        tasks = 0
        for st in rows or []:
            pd = dict(getattr(st, "pub_dates", None) or {})
            if not pd:
                continue
            patches = {
                str(h).lower(): {"published_at": float(ts)}
                for h, ts in pd.items()
                if ts and float(ts) > 0
            }
            if not patches:
                continue
            tasks += 1
            try:
                patched += int(store.put_many(patches) or 0)
            except Exception as err:  # noqa: BLE001
                self._log(f"发布时间落表:{getattr(st, 'task_id', '')} 写入失败:{err}", "warning")
        self.save_data(
            key=PUBDATE_MARKER_KEY,
            value={"at": time.time(), "states": len(rows), "tasks": tasks, "patched": patched},
        )
        if patched:
            self._log(f"发布时间落表:已把 {tasks} 个任务的 {patched} 个种子发布时间同步进种子表")
        return {"ok": True, "tasks": tasks, "patched": patched}

    def _migrate_counts(self) -> Dict[str, int]:
        return {
            T.TABLE_SITE: len(set(list((self.get_data("site_rules") or {}).keys()) +
                                  list((self.get_data("site_caps") or {}).keys()))),
            T.TABLE_RESOURCE: len(self.get_data("tag_groups") or {}),
            T.TABLE_SEED: len(self.get_data("tag_state") or {}),
        }

    # ------------------------------------------------------------ 分阶段写行

    def _migrate_stage(self, stage: str, offset: int, limit: int) -> int:
        """返回：写入行数；0 = 本阶段到底；**-1 = 出错**（本轮不推进，勿当成完成）。"""
        fn = {
            T.TABLE_SITE: self._stage_site,
            T.TABLE_RESOURCE: self._stage_resource,
            T.TABLE_SEED: self._stage_seed,
            T.TABLE_TASK: self._stage_task,
            T.TABLE_IDENTITY: self._stage_identity,
        }.get(stage)
        if fn is None:
            return 0
        try:
            return int(fn(offset, limit) or 0)
        except Exception as err:  # noqa: BLE001
            self._log(f"账本迁移:{stage} 阶段出错（保持旧键与游标，稍后重试）:{err}", "error")
            return -1

    def _upsert(self, model: Any, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        sess = self._mf_session()
        try:
            for row in rows:
                sess.merge(model(**row))
            sess.commit()
        finally:
            sess.close()

    def _upsert_patch(self, model: Any, patches: List[Dict[str, Any]]) -> None:
        """按 ``resource_id`` 只写给定列：已存在则 update，缺失则 insert（不覆盖其它列）。"""
        if not patches:
            return
        sess = self._mf_session()
        try:
            for patch in patches:
                rid = patch.get("resource_id")
                if not rid:
                    continue
                exists = sess.get(model, rid)
                if exists is None:
                    sess.merge(model(**patch))
                else:
                    for k, v in patch.items():
                        if k != "resource_id" and getattr(exists, k, None) in (None, "", 0, {}, []):
                            setattr(exists, k, v)
            sess.commit()
        finally:
            sess.close()

    def _reset_ledger_stores(self) -> None:
        """迁移一完成，就把两个账本单例切到 5 表后端（老单例已缓存旧 kv 数据）。"""
        try:
            import sys as _sys
            mod = _sys.modules.get("__magicflow_shared__")
            if mod is not None:
                for key in ("tag_state", "tag_groups"):
                    getattr(mod, "instances", {}).pop(key, None)
            self._tag_state_obj = None
            self._tag_groups_obj = None
        except Exception:  # noqa: BLE001
            pass

    def _ledger(self):
        from ..ledger import get_backend
        return get_backend(self)

    def _stage_identity(self, offset: int, limit: int) -> int:
        rows = [dict(x) for x in T.DEFAULT_IDENTITIES]
        if offset >= len(rows):
            return 0
        chunk = rows[offset:offset + limit]
        self._upsert(mfdb.IdentityRow, chunk)
        return len(chunk)

    def _stage_site(self, offset: int, limit: int) -> int:
        rules = self.get_data("site_rules") or {}
        caps = self.get_data("site_caps") or {}
        domains = sorted(set(list(rules.keys()) + list(caps.keys())))
        if offset >= len(domains):
            return 0
        ids = self._migrate_site_ids()
        mp_name = {}                      # 域名 -> MP 站点名（site_rules 缺 name 时兜底）
        try:
            for row in (self._reseed_mp_sites() or []):
                dom = str(row.get("domain") or "").strip().lower()
                nm = str(row.get("name") or "").strip()
                if dom and nm:
                    mp_name[dom] = nm
        except Exception:  # noqa: BLE001
            pass
        tz = 8.0
        try:
            from ..common import SITE_TZ_OFFSET_HOURS  # type: ignore
            tz = float(SITE_TZ_OFFSET_HOURS)
        except Exception:  # noqa: BLE001
            pass
        pv_budget = self.get_data("pv_budget") or {}
        pv_block = self.get_data("live_pv_block") or {}
        alerts = self.get_data("live_alerts") or {}
        now = time.time()
        rows: List[Dict[str, Any]] = []
        skip = 0
        for dom in domains[offset:offset + limit]:
            rule = dict(rules.get(dom) or {})
            cap = dict(caps.get(dom) or {})
            sid = rule.get("site_id") or ids.get(str(dom).lower())
            if not sid:
                skip += 1
                continue
            row: Dict[str, Any] = {
                "site_id": int(sid),
                "name": rule.get("name") or mp_name.get(str(dom).lower()) or dom,
                "domain": str(rule.get("domain") or dom or "").lower(),
                "domains": [], "mp_site_id": int(sid),
                "tz_offset": tz, "created": now, "updated": now,
            }
            for field in T.SITE_FIELDS:
                if field in row or field in ("iyuu_sid", "credential", "pv_usage"):
                    continue
                if field in rule:
                    row[field] = rule[field]
                elif field in cap:
                    row[field] = cap[field]
            if str(sid) in pv_budget:
                row["pv_budget"] = pv_budget[str(sid)]
            if str(sid) in pv_block:
                row["pv_block"] = pv_block[str(sid)]
            site_alerts = {k.split(":", 1)[1]: v for k, v in alerts.items()
                           if str(k).split(":", 1)[0] == str(sid)}
            if site_alerts:
                row["alerts"] = site_alerts
            rows.append(row)
        self._upsert(mfdb.SiteRow, rows)
        if skip:
            self._dbg(f"账本迁移:站点 {skip} 个无 site_id，跳过（待补）")
        return len(domains[offset:offset + limit])

    def _stage_resource(self, offset: int, limit: int) -> int:
        groups = self.get_data("tag_groups") or {}
        ids = self._migrate_site_ids()
        idents = self._mig_ident_map()
        keys = sorted(groups.keys())
        if offset >= len(keys):
            return 0
        now = time.time()
        be = self._ledger()
        rows: List[Dict[str, Any]] = []
        member_patches: List[Dict[str, Any]] = []
        for gid in keys[offset:offset + limit]:
            g = groups.get(gid)
            if not isinstance(g, dict):
                continue
            if not str(gid).startswith("fp:"):
                continue                      # 老账本里两条畸形键（|5.1 / |27.4）直接丢
            rec = dict(g)
            rid = _norm_res_id(gid).lower()
            rec.setdefault("created", now)
            rec.setdefault("updated", now)
            if not rec.get("identity"):
                rec["identity"] = idents.get(rid) or ""
            row = be.res_row(rid, rec, now)
            row["grouped"] = True
            rows.append(row)
            for h, m in (rec.get("members") or {}).items():     # 组员：mmbr 的唯一主人
                if not isinstance(m, dict):
                    continue
                patch: Dict[str, Any] = {"hash": str(h).lower(), "resource_id": rid,
                                         "mmbr": dict(m), "updated": now}
                sid = ids.get(str(m.get("site") or "").strip().lower())
                if sid:
                    patch["site_id"] = sid
                member_patches.append(patch)
        self._upsert(mfdb.ResourceRow, rows)
        if member_patches:
            self._upsert(mfdb.SeedRow, member_patches)
        return len(keys[offset:offset + limit])

    def _stage_seed(self, offset: int, limit: int) -> int:
        state = self.get_data("tag_state") or {}
        ids = self._migrate_site_ids()
        tasks = self._migrate_task_ids()
        keys = sorted(state.keys())
        if offset >= len(keys):
            return 0
        now = time.time()
        be = self._ledger()
        rows: List[Dict[str, Any]] = []
        orphan = 0
        res_patch: List[Dict[str, Any]] = []
        for h in keys[offset:offset + limit]:
            rec = state.get(h)
            if not isinstance(rec, dict):
                continue
            rows.append(be.seed_row(str(h), rec, now))
            if not rec.get("fp"):
                orphan += 1
            elif rec.get("sub"):
                # 身份/体积归资源表（资源行可能只有种子一张脸，先补上避免孤儿）
                rid = str(rec.get("fp") or "").strip().lower()
                patch: Dict[str, Any] = {"resource_id": rid, "identity": str(rec.get("sub")),
                                         "identity_at": rec.get("identity_at") or now,
                                         "created": rec.get("created") or now, "updated": now}
                if rec.get("size_gb") is not None:
                    patch["size_gb"] = rec.get("size_gb")
                res_patch.append(patch)
        self._upsert(mfdb.SeedRow, rows)
        if res_patch:
            self._upsert_patch(mfdb.ResourceRow, res_patch)
        if orphan:
            self._dbg(f"账本迁移:种子 {len(rows)} 行中 {orphan} 行暂无资源关联（待后续同步补）")
        return len(keys[offset:offset + limit])

    def _stage_task(self, offset: int, limit: int) -> int:
        cfgs = list((getattr(self, "_task_configs", {}) or {}).items())
        if offset >= len(cfgs):
            return 0
        now = time.time()
        rows: List[Dict[str, Any]] = []
        for tid, cfg in cfgs[offset:offset + limit]:
            try:
                dump = cfg.model_dump() if hasattr(cfg, "model_dump") else dict(getattr(cfg, "__dict__", {}))
            except Exception:  # noqa: BLE001
                dump = {}
            params = {k: v for k, v in dump.items()
                      if k not in ("id", "name", "site_id", "task_type", "run_mode", "enabled",
                                   "downloader", "brush_tag", "save_path")}
            try:
                mode = self._normalize_run_mode(getattr(cfg, "run_mode", None))
            except Exception:  # noqa: BLE001
                mode = None
            rows.append({
                "task_id": str(tid),
                "name": str(getattr(cfg, "name", "") or "") or None,
                "site_id": getattr(cfg, "site_id", None),
                "task_type": str(getattr(cfg, "task_type", "") or "") or None,
                "run_mode": mode,
                "enabled": bool(getattr(cfg, "enabled", False)),
                "downloader": str(getattr(cfg, "downloader", "") or "") or None,
                "brush_tag": str(getattr(cfg, "brush_tag", "") or "") or None,
                "save_path": str(getattr(cfg, "save_path", "") or "") or None,
                "params": params, "updated": now,
            })
        self._upsert(mfdb.TaskRow, rows)
        return len(cfgs[offset:offset + limit])

    # ------------------------------------------------------------ API

    def get_migrate(self) -> Dict[str, Any]:
        return self.migrate_status()

    def run_migrate(self, force: bool = False) -> Dict[str, Any]:
        return self.migrate_scan(force=bool(force))
