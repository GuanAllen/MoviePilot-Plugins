# -*- coding: utf-8 -*-
"""魔流 · 账本读写层（**5 表 = 唯一真值源**；12.0.0 起无影子/无兼容/无回滚镜像）

「标签账本」的**唯一实现**就在这里（``SeedLedgerStore`` / ``ResourceLedgerStore``），
**kv 不再是后端**：两个账本对象**自成一体、不继承任何 kv 类**，直接读写
``LedgerBackend``（见 ``db.py``），对象 API 与业务代码完全不变。

    SeedLedgerStore     ← mf_seed（归属/发布进度） + mf_resource.identity（身份）
    ResourceLedgerStore ← mf_resource（资源/入库/评分列） + mf_seed（hash↔resource 关联）

★ 12.0.0 清算：
  - 「标签账本」只认 5 表，**kv 不再是后端**（旧 kv 账本实现、``_mirror_legacy`` 双写、
    快照机制、旧 kv 键常量一并删除）；
  - 影子列（``rt``/``mmbr``/``library``/``extra``）与「退役列 DROP」逻辑一并删除；
  - 结构自愈只保留「补列」（``_ensure_columns`` 的 ADD 分支）。
"""

from __future__ import annotations

import copy
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, inspect as sa_inspect, select, text, update

from . import db as mfdb
from .common import HR_HOST_TASK_ID, ONDEMAND_TASK_ID, ONDEMAND_TASK_NAME, task_is_participating
from .tags import (
    LEASE_TTL,
    SILENT_NEW_TIMEOUT,
    STATE_BONUS,
    STATE_BRUSH,
    STATE_HR,
    STATE_ONDEMAND,
    STATE_SILENT,
    STATES_WITH_SUB,
    SUB_NEW,
    SUB_PLAIN,
    SUB_RESOURCE,
    _clean,
    is_library_asset,
    tag_for,
)


# ★ 10.0.0：合法「完整特征码」= sha1 十六进制（32~64 位）。不是这个样子的 group/rid 就是
#   历史遗留的**弱身份**（``|2.0`` 这种体积档）。弱组被清理时要把残留种子直接解绑，
#   否则资源行会因「还有种子指着它」被留下 → 下次重载弱组复活。
_STRONG_RID = re.compile(r"^[0-9a-f]{32,64}$")

_SCHEMA_LOCK = threading.Lock()   # 结构自愈串行化（启动瞬间多 worker 抢建列会撞 DuplicateColumn）


def norm_res_id(value: Any) -> str:
    """资源主键归一：老键 ``fp:<hash>`` ↔ 行主键 ``<hash>``。"""
    s = str(value or "").strip()
    return s[3:] if s.startswith("fp:") else s


def group_key(resource_id: str) -> str:
    """资源主键 → 老 group id（``fp:<hash>``，业务代码里到处这么拼，必须保持）。"""
    return f"fp:{resource_id}"


class LedgerBackend:
    """整包 dict ↔ 5 张表。所有写操作加锁（MP 是多线程跑的）。"""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self._lock = threading.RLock()
        self._seeds: Optional[Dict[str, Dict[str, Any]]] = None
        self._seed_prev: Dict[str, Dict[str, Any]] = {}
        self._groups: Optional[Dict[str, Dict[str, Any]]] = None
        self._group_prev: Dict[str, Dict[str, Any]] = {}
        self._site_by_name: Dict[str, int] = {}
        self._name_by_id: Dict[int, str] = {}
        self._site_at = 0.0
        self._schema_checked = False

    # ------------------------------------------------------------ 基础设施

    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self.plugin._log(msg, level)
        except Exception:  # noqa: BLE001
            pass

    def _session(self):
        return self.plugin.get_database().session()

    def ensure_schema(self) -> bool:
        """结构自愈：表缺了补建，列缺了补加（直接升到 6.1+ 的老库也能站起来）。

        ★ 并发护栏：启动瞬间会有多个 worker 同时首次触及账本 → 不加锁会并发
        ``ALTER TABLE ADD COLUMN`` 撞车（DuplicateColumn）。用模块级锁串行，
        并且单列用 SAVEPOINT 隔离（PG 上一句报错会把整个事务打成 aborted）。
        """
        if self._schema_checked:
            return True
        with _SCHEMA_LOCK:
            if self._schema_checked:
                return True
            try:
                mfdb.Base.metadata.create_all(self.plugin.get_database().engine)
            except Exception as err:  # noqa: BLE001
                self._log(f"账本:建表失败:{err}", "error")
                return False
            try:
                self._ensure_columns()
            except Exception as err:  # noqa: BLE001
                self._log(f"账本:补列失败:{err}", "error")
                return False
            self._schema_checked = True
            return True

    def _ensure_columns(self) -> None:
        """补列：``create_all`` 只建表不改表，这里比对后 ``ALTER TABLE ADD COLUMN``。

        单列独立 SAVEPOINT：已存在/并发抢建 → 跳过而不是把整轮搞挂。
        """
        added: List[str] = []
        sess = self._session()
        try:
            conn = sess.connection()
            insp = sa_inspect(conn)
            for model in mfdb.ALL_MODELS:
                table = model.__table__
                try:
                    have = {c["name"] for c in insp.get_columns(table.name)}
                except Exception:  # noqa: BLE001
                    continue
                for col in table.columns:
                    if col.name in have:
                        continue
                    ddl = col.type.compile(dialect=conn.dialect)
                    try:
                        with conn.begin_nested():          # SAVEPOINT：单列失败不污染事务
                            conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}"))
                        added.append(f"{table.name}.{col.name}")
                    except Exception as err:  # noqa: BLE001
                        msg = str(err).lower()
                        if "already exists" in msg or "duplicate" in msg:
                            added.append(f"{table.name}.{col.name}(已有)")
                            continue
                        self._log(f"账本:补列 {table.name}.{col.name} 跳过:{err}", "warning")
            if added:
                sess.commit()
                self._log(f"账本:补列 {len(added)} 个（结构自愈）{'/'.join(added[:6])}"
                          f"{'…' if len(added) > 6 else ''}")
        finally:
            sess.close()

    # ------------------------------------------------------------ 站点索引

    def _site_names(self) -> Dict[int, str]:
        if time.time() - self._site_at < 60.0 and self._name_by_id:
            return self._name_by_id
        try:
            sess = self._session()
            try:
                rows = sess.execute(select(mfdb.SiteRow.site_id, mfdb.SiteRow.name)).all()
            finally:
                sess.close()
        except Exception:  # noqa: BLE001
            return self._name_by_id
        self._name_by_id = {int(r[0]): str(r[1] or "") for r in rows if r[0] is not None}
        self._site_by_name = {v.strip().lower(): k for k, v in self._name_by_id.items() if v.strip()}
        self._site_at = time.time()
        return self._name_by_id

    def _site_id(self, name: str, *, create: bool = True) -> Optional[int]:
        key = str(name or "").strip()
        if not key:
            return None
        self._site_names()
        sid = self._site_by_name.get(key.lower())
        if sid is not None or not create:
            return sid
        try:                                     # 新站点：补一行，保持引用完整
            sess = self._session()
            try:
                top = sess.execute(select(mfdb.SiteRow.site_id).order_by(mfdb.SiteRow.site_id.desc()).limit(1)).scalar()
                sid = int(top or 0) + 1
                now = time.time()
                sess.merge(mfdb.SiteRow(site_id=sid, name=key, created=now, updated=now))
                sess.commit()
            finally:
                sess.close()
        except Exception as err:  # noqa: BLE001
            self._log(f"账本:补站点「{key}」失败:{err}", "warning")
            return None
        self._name_by_id[sid] = key
        self._site_by_name[key.lower()] = sid
        return sid

    def _task_name(self, task_id: Any) -> str:
        tid = str(task_id or "")
        # ★ 11.11.0：__hr_host__（H&R 保种）伪任务可寻址（不在 _task_configs / mf_task 里）
        if tid == HR_HOST_TASK_ID:
            return "H&R保种"
        # ★ 15.8.4：__ondemand__（点播在途）伪任务可寻址
        if tid == ONDEMAND_TASK_ID:
            return ONDEMAND_TASK_NAME
        cfg = (getattr(self.plugin, "_task_configs", {}) or {}).get(tid)
        return str(getattr(cfg, "name", "") or "") if cfg is not None else ""

    def _task_state(self, task_id: Any) -> str:
        """任务 id → 职务（刷流/魔力/保种/静默）。7.0.0 退役 state 列后，职务由任务推导。

        ★ 关键：任务被停止（遣散）→ 静默，不看 task_type。只有 running/seeding
          （participating）才算在岗（刷流/魔力）。否则 stopped 任务的种会被误算成在岗。
        ★ 11.11.0：__hr_host__（伪任务）→ 保种（H&R 保挂职务）。
        """
        tid = str(task_id or "")
        if tid == HR_HOST_TASK_ID:
            return STATE_HR
        # ★ 15.8.4：点播在途伪任务 → 职务「点播」（≠ 静默 → 免疫静默池暂停/清理）
        if tid == ONDEMAND_TASK_ID:
            return STATE_ONDEMAND
        cfg = (getattr(self.plugin, "_task_configs", {}) or {}).get(tid)
        if cfg is None:
            return STATE_SILENT
        if not task_is_participating(cfg):
            return STATE_SILENT
        return STATE_BRUSH if str(getattr(cfg, "task_type", "") or "") == "brush" else STATE_BONUS

    def _task_id(self, name: str) -> Optional[str]:
        key = str(name or "").strip().lower()
        if not key:
            return None
        # ★ 11.11.0：__hr_host__ / H&R保种 伪任务名 → __hr_host__（不在 _task_configs 里，但账本可寻址）
        if key in ("__hr_host__", "h&r保种", "hr保种", "保种"):
            return HR_HOST_TASK_ID
        # ★ 15.8.4：点播在途伪任务名 → __ondemand__（账本可寻址，seed_row 写 task_id 用）
        if key in ("__ondemand__", "ondemand", "点播", "点播下载"):
            return ONDEMAND_TASK_ID
        for tid, cfg in (getattr(self.plugin, "_task_configs", {}) or {}).items():
            if str(tid).lower() == key or str(getattr(cfg, "name", "") or "").strip().lower() == key:
                return str(tid)
        return None

    # ------------------------------------------------------------ 字段映射（读）

    def _rec_from_seed(self, s: Any, names: Dict[int, str]) -> Dict[str, Any]:
        """一行种子 → 台账 rec（★ 7.0.0 重写：只读 ORM 声明列）。

        退役的旧真列（state/title/reason/asset/taken_*/verify_*/crossseed/downloader/ts/created）
        不再读出 —— 它们已经被 DROP，SQLAlchemy 访问会报 AttributeError。身份走 resource。
        """
        rec: Dict[str, Any] = {}
        rec["site"] = names.get(s.site_id) or ""
        if s.task_id:
            rec["task"] = self._task_name(s.task_id) or ""
        if s.resource_id:
            rec["fp"] = s.resource_id
        if s.published_at is not None:
            rec["published_at"] = s.published_at
        if s.vfy_miss:
            rec["miss"] = int(s.vfy_miss)
        if s.updated is not None:
            rec["updated"] = s.updated
        return rec

    @staticmethod
    def _member_rec(s: Any, names: Dict[int, str]) -> Dict[str, Any]:
        """一行种子的组员字段（★ 7.0.0 重写：只读 ORM 声明列）。

        退役的组员真列（in_group/m_*/mmbr）不再读出。
        """
        m: Dict[str, Any] = {}
        m["site"] = names.get(s.site_id) or ""
        if s.resource_id:
            m["fp"] = s.resource_id
        return m

    def _rec_from_resource(self, r: Any, members: Dict[str, Dict[str, Any]],
                           names: Dict[int, str]) -> Dict[str, Any]:
        """一行资源 → 资源账本 rec（真列优先，影子兜底）。"""
        rec: Dict[str, Any] = {}
        rec["created"] = r.created
        rec["updated"] = r.updated
        rec["size_gb"] = r.size_gb
        rec["files_shared"] = bool(r.files_shared)
        rec["source_hash"] = r.source_hash or ""
        rec["source_site"] = names.get(r.source_site_id) or r.source_site_name or rec.get("source_site") or ""
        rec["members"] = dict(members or {})           # 已按资源 id 取好的成员表
        lib: Dict[str, Any] = {}
        for col, key in (("in_library", "in_library"), ("lib_first_at", "first_at"),
                         ("lib_updated", "updated"), ("lib_path", "path"), ("lib_media_id", "media_id")):
            v = getattr(r, col, None)
            if v is not None:
                lib[key] = bool(v) if col == "in_library" else v
        rec["library"] = lib
        if r.identity:
            rec["identity"] = r.identity
            rec["identity_at"] = r.identity_at
            rec["identity_by"] = r.identity_by
        if r.hrs:
            hr = dict(r.hrs[0] or {})
            hr.pop("site_id", None)
            rec["hr"] = hr
        if r.rating is not None:
            rec["rating"] = r.rating
        if r.asset_recheck:
            rec["asset_recheck"] = r.asset_recheck
            rec["asset_recheck_at"] = r.asset_recheck_at
        return rec

    # ------------------------------------------------------------ 字段映射（写）

    def seed_row(self, h: str, rec: Dict[str, Any], now: float) -> Dict[str, Any]:
        """台账 rec → mf_seed 整行（★ 7.0.0 重写：只写真列）。

        退役的真列（state/title/reason/asset/taken_*/verify_*/crossseed/downloader/ts/created）
        不再写入。状态/身份/H&R 走 resource；进度/体积/做种时长走下载器实况。
        """
        site_name = str(rec.get("site") or "").strip()
        sid = self._site_id(site_name)
        task_name = str(rec.get("task") or "").strip()
        tid = self._task_id(task_name)
        rid = norm_res_id(rec.get("fp")).lower()
        return {
            "hash": str(h).lower(),
            "site_id": sid,
            "resource_id": rid or None,
            "task_id": tid,
            "published_at": rec.get("published_at"),
            "vfy_miss": int(rec.get("miss") or 0),
            "updated": rec.get("updated") or now,
        }

    def _member_patch(self, h: str, rid: Optional[str], m: Dict[str, Any],
                      now: float) -> Dict[str, Any]:
        """组员字段 → mf_seed 组员列（★ 7.0.0 重写：只写核心列）。

        组员的体积/进度/状态走 resource.members；这里只保留 hash↔resource_id 关联。
        """
        patch: Dict[str, Any] = {
            "hash": str(h).lower(),
            "resource_id": (str(rid).lower() or None) if rid else None,
            "updated": now,
        }
        site_name = str((m or {}).get("site") or "").strip()
        sid = self._site_id(site_name) if site_name else None
        if sid:
            patch["site_id"] = sid
        return patch

    def res_row(self, rid: str, rec: Dict[str, Any], now: float) -> Dict[str, Any]:
        # ★ 10.0.0：账单**按站分账**（``hrs``）—— 同一资源多站各欠一份，全部写入
        _bills = rec.get("hrs") if isinstance(rec.get("hrs"), dict) else None
        if not _bills:
            _h0 = rec.get("hr") or {}
            _bills = {str(_h0.get("site") or "_"): _h0} if isinstance(_h0, dict) and _h0 else {}
        hrs: List[Dict[str, Any]] = []
        for _b in (_bills or {}).values():
            if not isinstance(_b, dict) or not _b:
                continue
            item = dict(_b)
            site_name = str(item.get("site") or "").strip()
            if site_name:
                item["site_id"] = self._site_id(site_name)
                item.pop("site", None)
            hrs.append(item)
        src_site = str(rec.get("source_site") or "").strip()
        src_id = self._site_id(src_site) if src_site else None
        lib = rec.get("library") or {}
        row: Dict[str, Any] = {
            "resource_id": rid,
            "grouped": True,
            "size_gb": rec.get("size_gb"),
            "files_shared": bool(rec.get("files_shared")),
            "source_hash": str(rec.get("source_hash") or "").lower() or None,
            "hrs": hrs,
            "created": rec.get("created") or now,
            "updated": rec.get("updated") or now,
        }
        if src_id or not src_site:
            row["source_site_id"] = src_id
        else:
            row["source_site_name"] = src_site     # 关联不上 → 单列兜底
        # 入库真列
        row["in_library"] = None if lib.get("in_library") is None else bool(lib.get("in_library"))
        row["lib_first_at"] = lib.get("first_at")
        row["lib_updated"] = lib.get("updated")
        row["lib_path"] = lib.get("path") or None
        row["lib_media_id"] = str(lib.get("media_id") or "") or None
        if rec.get("identity"):
            row["identity"] = str(rec["identity"])
            row["identity_at"] = rec.get("identity_at")
            row["identity_by"] = rec.get("identity_by")
        if rec.get("rating") is not None:
            row["rating"] = rec.get("rating")
        return row

    # ------------------------------------------------------------ 种子账本

    def load_seeds(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if self._seeds is None:
                self._seeds = self._read_seeds()
                self._seed_prev = copy.deepcopy(self._seeds)
            return self._seeds

    def _read_seeds(self) -> Dict[str, Dict[str, Any]]:
        names = self._site_names()
        try:
            sess = self._session()
            try:
                seeds = sess.execute(select(mfdb.SeedRow)).scalars().all()
                res = {}
                for r in sess.execute(select(mfdb.ResourceRow)).scalars().all():
                    res[r.resource_id] = r
            finally:
                sess.close()
        except Exception as err:  # noqa: BLE001
            self._log(f"账本:读种子表失败:{err}", "error")
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for s in seeds:
            h = str(s.hash or "").lower()
            if not h:
                continue
            rec = self._rec_from_seed(s, names)
            # ★ 7.0.0：state/taken_by 列已退役，职务/归属从 task_id 推导
            #   （task_id 空 = 静默不在岗；非空 = 按任务类型刷流/魔力）
            if s.task_id:
                rec["taken_by"] = str(s.task_id)
                rec["state"] = self._task_state(s.task_id)
            else:
                rec["state"] = STATE_SILENT
            if s.resource_id:                      # 身份/体积/评分顺资源表（种子不存）
                rr = res.get(s.resource_id)
                if rr is not None:
                    if not rec.get("sub") and rr.identity:
                        rec["sub"] = rr.identity
                        if rr.identity_at:
                            rec.setdefault("identity_at", rr.identity_at)
                    if rec.get("size_gb") is None and rr.size_gb is not None:
                        rec["size_gb"] = rr.size_gb
                    if rec.get("rating") is None and rr.rating is not None:
                        rec["rating"] = rr.rating
                    # ★ 12.0.0：库记只存资源（``mf_resource.in_library``），随资源回填给种子 rec。
                    #   7.0.0 起 ``mf_seed.asset`` 已退役（读它恒空），库内资产判定一律看这里。
                    if rr.in_library is not None:
                        rec["in_library"] = bool(rr.in_library)
                    if rr.asset_recheck:
                        rec["asset_recheck"] = rr.asset_recheck
                        if rr.asset_recheck_at:
                            rec.setdefault("asset_recheck_at", rr.asset_recheck_at)
            out[h] = rec
        return out

    def save_seeds(self, data: Dict[str, Dict[str, Any]]) -> None:
        with self._lock:
            base = self._seed_prev if self._seed_prev else self._read_seeds()
            now = time.time()
            changed = [h for h, rec in (data or {}).items() if base.get(h) != rec]
            removed = [h for h in base if h not in (data or {})]
            if changed or removed:
                try:
                    sess = self._session()
                    try:
                        for h in changed:
                            rec = data.get(h) or {}
                            sess.merge(mfdb.SeedRow(**self.seed_row(h, rec, now)))
                            self._touch_resource(sess, rec, now)
                        if removed:
                            sess.execute(delete(mfdb.SeedRow).where(mfdb.SeedRow.hash.in_(removed)))
                        sess.commit()
                    finally:
                        sess.close()
                except Exception as err:  # noqa: BLE001
                    self._log(f"账本:写种子表失败:{err}", "error")
                    return
            self._seeds = dict(data or {})
            self._seed_prev = copy.deepcopy(self._seeds)

    def _touch_resource(self, sess: Any, rec: Dict[str, Any], now: float) -> None:
        """种子的身份/体积 → 资源表（资源表仍是身份的唯一真值源）。"""
        rid = norm_res_id(rec.get("fp")).lower()
        if not rid:
            return
        patch: Dict[str, Any] = {"resource_id": rid}
        if rec.get("sub"):
            patch["identity"] = str(rec["sub"])
            patch["identity_at"] = rec.get("identity_at") or now
        if rec.get("size_gb") is not None:
            patch["size_gb"] = rec.get("size_gb")
        if rec.get("rating") is not None:
            patch["rating"] = rec.get("rating")
        # ★ 12.0.0：推荐复核结论落资源真列（旧写法只进内存 rec，重启即丢）
        if rec.get("asset_recheck"):
            patch["asset_recheck"] = str(rec["asset_recheck"])
            patch["asset_recheck_at"] = rec.get("asset_recheck_at") or now
        if len(patch) > 1:
            sess.merge(mfdb.ResourceRow(**patch))

    # ------------------------------------------------------------ 资源账本

    def load_groups(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if self._groups is None:
                self._groups = self._read_groups()
                self._group_prev = copy.deepcopy(self._groups)
            return self._groups

    def _read_groups(self) -> Dict[str, Dict[str, Any]]:
        names = self._site_names()
        try:
            sess = self._session()
            try:
                resources = sess.execute(select(mfdb.ResourceRow)).scalars().all()
                seeds = sess.execute(select(mfdb.SeedRow)).scalars().all()
            finally:
                sess.close()
        except Exception as err:  # noqa: BLE001
            self._log(f"账本:读资源表失败:{err}", "error")
            return {}
        members: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for s in seeds:
            if not s.resource_id:
                continue
            members.setdefault(s.resource_id, {})[str(s.hash).lower()] = self._member_rec(s, names)
        out: Dict[str, Dict[str, Any]] = {}
        for r in resources:
            if not r.grouped:                       # 只有「下完成组」的才算资源账本
                continue
            mem = members.get(r.resource_id) or {}
            if not mem:
                continue                            # 没成员 = 不是一个组（含「摘完成员」后的空壳）
            out[group_key(r.resource_id)] = self._rec_from_resource(r, mem, names)
        return out

    def save_groups(self, data: Dict[str, Dict[str, Any]]) -> None:
        with self._lock:
            base = self._group_prev if self._group_prev else self._read_groups()
            now = time.time()
            changed = [g for g, rec in (data or {}).items() if base.get(g) != rec]
            removed = [g for g in base if g not in (data or {})]
            if changed or removed:
                try:
                    sess = self._session()
                    try:
                        for gid in changed:
                            rec = data.get(gid) or {}
                            rid = norm_res_id(gid).lower()
                            if not rid:
                                continue
                            sess.merge(mfdb.ResourceRow(**self.res_row(rid, rec, now)))
                            self._sync_members(sess, rid, rec.get("members") or {},
                                               (base.get(gid) or {}).get("members") or {}, now)
                        for gid in removed:                     # 整个组没了 → 资源行按引用情况保留
                            rid = norm_res_id(gid).lower()
                            if not rid:
                                continue
                            if not _STRONG_RID.match(rid):          # 弱身份组被清 → 残留种直接解绑
                                sess.execute(update(mfdb.SeedRow)
                                             .where(mfdb.SeedRow.resource_id == rid)
                                             .values(resource_id=None))
                            left = sess.execute(select(func.count()).select_from(mfdb.SeedRow)
                                                .where(mfdb.SeedRow.resource_id == rid)).scalar()
                            if left:
                                continue      # 还有种子指着它 → 资源行留着（身份/体积别丢）
                            sess.execute(delete(mfdb.ResourceRow).where(mfdb.ResourceRow.resource_id == rid))
                        sess.commit()
                    finally:
                        sess.close()
                except Exception as err:  # noqa: BLE001
                    self._log(f"账本:写资源表失败:{err}", "error")
                    return
            self._groups = dict(data or {})
            self._group_prev = copy.deepcopy(self._groups)

    def _sync_members(self, sess: Any, rid: str, members: Dict[str, Any],
                      prev: Dict[str, Any], now: float) -> None:
        """组员 → mf_seed 组员列（组员的唯一主人；不碰台账列）。"""
        for h, m in (members or {}).items():
            if not isinstance(m, dict):
                continue
            if prev.get(h) == m and prev.get(h) is not None:
                continue                                  # 组员没变，跳过（省一写）
            sess.merge(mfdb.SeedRow(**self._member_patch(str(h), rid, m, now)))
        for h in (prev or {}):
            if h not in (members or {}):                  # 退出资源 → 摘 resource_id（7.0.0：无组员列）
                sess.execute(update(mfdb.SeedRow).where(mfdb.SeedRow.hash == str(h).lower())
                             .values(resource_id=None))

class SeedLedgerStore:
    """``tag_state`` 账本对象（★ 12.0.0 自成一体，不再继承 kv 类）。

    记录：``hash -> {site, state, sub, taken_by, taken_at, lease_until, free,
    size_gb, title, group_id, approx, …}``。存储后端 = ``LedgerBackend``（5 表），
    直接读写 ``load_seeds``/``save_seeds``，不经任何 kv 键。
    """

    def __init__(self, backend: LedgerBackend, log: Any = None) -> None:
        self.backend = backend
        self._log = log

    # ---- 读写
    def items(self) -> Dict[str, Dict[str, Any]]:
        # 缓存 items() 返回接口状态（状态账本写入后会调 _invalidate 失效）
        cached = getattr(self, "_items_cache", None)
        if cached is not None:
            return cached
        try:
            data = self.backend.load_seeds() or {}
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        out = {str(k).lower(): v for k, v in data.items() if isinstance(v, dict)}
        self._items_cache = out
        return out

    def _invalidate(self) -> None:
        try:
            self._items_cache = None
        except Exception:
            pass

    def _write(self, data: Dict[str, Any]) -> None:
        try:
            self.backend.save_seeds(data)
            self._invalidate()
        except Exception as err:  # noqa: BLE001
            self._log and self._log(f"标签:状态账本写入失败:{err}", "error")

    def set_asset(self, hash_string: str, *, sub: str = "") -> bool:
        """固化「库内资产」身份（= 写 ``sub``，落 ``mf_resource.identity``）。

        ★ 12.0.0：删掉退役的 ``asset`` 字段（7.0.0 起就不落库，写它="写个寂寞"）。
        库内资产的**库记**在 ``mf_resource.in_library``（由资源侧写），这里只管身份。
        """
        h = _clean(hash_string).lower()
        if not h:
            return False
        sub = _clean(sub)
        if not sub:
            return False                     # 没给身份 → 无事可做
        data = self.items()
        rec = dict(data.get(h) or {})
        if not rec or rec.get("sub") == sub:
            return False
        rec["sub"] = sub
        rec["updated"] = time.time()
        data[h] = rec
        self._write(data)
        return True

    def get(self, hash_string: str) -> Dict[str, Any]:
        return dict(self.items().get(_clean(hash_string).lower()) or {})

    def put(self, hash_string: str, patch: Dict[str, Any], *, now: Optional[float] = None) -> Dict[str, Any]:
        """写入/合并一条记录（``state`` = 职务，``sub`` = 身份；不再记 origin）。"""
        h = _clean(hash_string).lower()
        if not h:
            return {}
        data = self.items()
        rec = dict(data.get(h) or {})
        ts = float(now if now is not None else time.time())
        _old_sub = _clean(rec.get("sub"))
        new_state = _clean(patch.get("state", rec.get("state")))
        new_sub = _clean(patch.get("sub", rec.get("sub")))
        _state_given = bool(_clean(patch.get("state")))
        rec.update({k: v for k, v in patch.items() if v is not None})
        if new_state:
            rec["state"] = new_state
        if new_state in STATES_WITH_SUB:
            rec["sub"] = new_sub
        elif new_state in (STATE_BRUSH, STATE_BONUS) and not _state_given and "sub" in patch:
            # ★ 5.0.0 铁律：在岗（职务轴）期间**不接**「顺手改身份」的写
            #   （分拣/推荐只能改池内种子的身份；在岗的等回池再过站）
            if _old_sub:
                rec["sub"] = _old_sub
            else:
                rec.pop("sub", None)
        elif "sub" in patch and not patch.get("sub"):
            rec.pop("sub", None)
        rec.setdefault("created", ts)
        rec["updated"] = ts
        data[h] = rec
        self._write(data)
        return rec

    def put_many(self, patches: Dict[str, Dict[str, Any]], *, now: Optional[float] = None) -> int:
        """批量写入（一次落盘）。语义与 :meth:`put` 一致。"""
        ts = float(now if now is not None else time.time())
        data = self.items()
        n = 0
        for h, patch in (patches or {}).items():
            hh = _clean(h).lower()
            if not hh or not isinstance(patch, dict):
                continue
            rec = dict(data.get(hh) or {})
            _old_sub = _clean(rec.get("sub"))
            new_state = _clean(patch.get("state", rec.get("state")))
            new_sub = _clean(patch.get("sub", rec.get("sub")))
            _state_given = bool(_clean(patch.get("state")))
            rec.update({k: v for k, v in patch.items() if v is not None})
            if new_state:
                rec["state"] = new_state
            if new_state in STATES_WITH_SUB:
                rec["sub"] = new_sub
            elif new_state in (STATE_BRUSH, STATE_BONUS) and not _state_given and "sub" in patch:
                # ★ 在岗不动身份（同 put）
                if _old_sub:
                    rec["sub"] = _old_sub
                else:
                    rec.pop("sub", None)
            elif "sub" in patch and not patch.get("sub"):
                rec.pop("sub", None)
            rec.setdefault("created", ts)
            rec["updated"] = ts
            data[hh] = rec
            n += 1
        if n:
            self._write(data)
        return n

    def reconcile(self, live_hashes: Any, *, keep_miss: int = 3, min_live: int = 50) -> Dict[str, int]:
        """账本对账：连续 ``keep_miss`` 轮不在下载器里 → 销账（防僵尸记录）。

        ★ 安全阀：``live`` 少于 ``min_live`` 视为「快照异常」直接跳过，
        绝不因为一次抓取失败把账本清空。
        """
        try:
            live = {_clean(h).lower() for h in (live_hashes or []) if _clean(h)}
        except Exception:  # noqa: BLE001
            live = set()
        if len(live) < int(min_live):
            return {"skipped": 1, "live": len(live), "dropped": 0, "pending": 0}
        data = self.items()
        dropped = 0
        pending = 0
        for h, rec in list(data.items()):
            if h in live:
                if rec.get("miss"):
                    rec.pop("miss", None)
                continue
            miss = int(rec.get("miss") or 0) + 1
            if miss >= int(keep_miss):
                data.pop(h, None)
                dropped += 1
                try:
                    self._log and self._log(f"账本:销账僵尸记录 {h[:8]}（{miss} 轮未见）")
                except Exception:  # noqa: BLE001
                    pass
            else:
                rec["miss"] = miss
                pending += 1
        if dropped or pending:
            self._write(data)
        return {"live": len(live), "dropped": dropped, "pending": pending}

    def stale_count(self) -> int:
        """账本里「本轮未见」的待销账记录数（看板用）。"""
        try:
            return sum(1 for r in self.items().values() if r.get("miss"))
        except Exception:  # noqa: BLE001
            return 0

    def drop(self, hash_string: str) -> bool:
        h = _clean(hash_string).lower()
        data = dict(self.items())   # ★ 拷贝再改：直接改缓存会让账本别名（5.0.0 修）
        if h not in data:
            return False
        data.pop(h, None)
        self._write(data)
        return True

    # ---- 查询
    def hashes_by_state(self, state: str = "", sub: str = "", *, site: str = "") -> List[str]:
        state = _clean(state)
        sub = _clean(sub)
        site = _clean(site)
        out: List[str] = []
        for h, rec in self.items().items():
            if site and _clean(rec.get("site")) != site:
                continue
            if state and _clean(rec.get("state")) != state:
                continue
            if sub and _clean(rec.get("sub")) != sub:
                continue
            out.append(h)
        return out

    def stats(self) -> Dict[str, int]:
        """按 ``站点|状态[-子类]`` 计数（看板用）。"""
        out: Dict[str, int] = {}
        for rec in self.items().values():
            key = f"{_clean(rec.get('site')) or '-'}|{_clean(rec.get('state')) or '-'}"
            sub = _clean(rec.get("sub"))
            if sub:
                key += f"-{sub}"
            out[key] = out.get(key, 0) + 1
        return out

    def expire_new(self, *, now: Optional[float] = None, timeout: float = SILENT_NEW_TIMEOUT,
                   skip: Optional[Any] = None) -> List[str]:
        """``静默-新`` 超时未分拣 → 归 ``静默-普通``；返回被改动的 hash。

        ``skip``：这些 hash 不参与超时降级（例如 H&R 义务还没挂满，仍要留在「新」等分拣）。
        """
        ts = float(now if now is not None else time.time())
        _skip = {str(x).strip().lower() for x in (skip or [])}
        moved: List[str] = []
        for h, rec in self.items().items():
            if _skip and str(h).strip().lower() in _skip:
                continue
            if _clean(rec.get("state")) == STATE_SILENT and _clean(rec.get("sub")) == SUB_NEW:
                born = float(rec.get("created") or 0)
                if born and (ts - born) >= timeout:
                    self.put(h, {"sub": SUB_PLAIN, "reason": "静默-新超时自动归普通"}, now=ts)
                    moved.append(h)
        return moved

    # ---- 占用（并发安全：先写账本再改标签，带租约）
    def claim(
        self,
        hash_string: str,
        task_id: str,
        *,
        state: str,
        site: str = "",
        ttl: float = LEASE_TTL,
        now: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """占用一个静默种（贴**职务**：``静默-*`` → ``刷流``/``魔力``）。

        返回 ``(是否成功, 原因)``。已有**未过期**占用者时拒绝（刷流/魔力互不接管）。
        ★ 只写职务，**身份（``sub``）原样保留**。
        """
        h = _clean(hash_string).lower()
        if not h:
            return False, "空 hash"
        ts = float(now if now is not None else time.time())
        data = self.items()
        rec = dict(data.get(h) or {})
        cur_state = _clean(rec.get("state"))
        owner = _clean(rec.get("taken_by"))
        lease = float(rec.get("lease_until") or 0)
        if owner and owner != _clean(task_id) and lease > ts:
            return False, f"已被任务 {owner} 占用（租约到 {int(lease)}）"
        if owner and owner != _clean(task_id) and cur_state in (STATE_BRUSH, STATE_BONUS) and lease <= ts:
            # 租约过期的孤儿占用：允许抢占，但记一笔
            self._log and self._log(f"标签:抢占过期占用 {h[:8]}（原 {owner}）", "warning")
        if cur_state in (STATE_BRUSH, STATE_BONUS) and owner and owner != _clean(task_id):
            return False, f"状态已被占用：{cur_state}"
        # ★ 5.0.0：``state`` 只表达**职务**；``sub`` 是**身份** —— 占用不改写、不清空，
        #   也就没有「回退目标 origin」这个字段了（旧记录里残留的无害，可忽略）。
        rec.update({
            "state": state,
            "taken_by": _clean(task_id),
            "taken_at": ts,
            "lease_until": ts + float(ttl),
            "updated": ts,
        })
        if site:
            rec["site"] = _clean(site)
        rec.setdefault("created", ts)
        data[h] = rec
        self._write(data)
        return True, "ok"

    def release(self, hash_string: str, *, task_id: str = "", now: Optional[float] = None) -> Optional[str]:
        """下班：**只摘职务** —— 身份（``sub``）原样保留，返回回到的标签串。

        ★ 5.0.0：不再有「按 origin 退回」这一步 —— 上班前是资源/普通，下班还是资源/普通。
        只有账本里没有身份的老记录才兜底（库内资产 → 资源，其余 → 普通）。
        """
        h = _clean(hash_string).lower()
        data = self.items()
        rec = dict(data.get(h) or {})
        if not rec:
            return None
        owner = _clean(rec.get("taken_by"))
        if task_id and owner and owner != _clean(task_id):
            return None  # 不是本任务占用的，别乱放
        state = STATE_SILENT
        sub = _clean(rec.get("sub"))
        if not sub:
            sub = SUB_RESOURCE if is_library_asset(rec) else SUB_PLAIN
        rec.update({"state": state, "sub": sub, "updated": float(now if now is not None else time.time())})
        rec.pop("taken_by", None)
        rec.pop("taken_at", None)
        rec.pop("lease_until", None)
        rec.pop("origin_state", None)
        rec.pop("origin_sub", None)
        data[h] = rec
        self._write(data)
        return tag_for(_clean(rec.get("site")), state, sub)


class ResourceLedgerStore:
    """★ 资源账本（Resource）：一份内容 = 一条资源，多站各挂一个种。

    存储后端 = ``LedgerBackend``（5 表），直接读写 ``load_groups``/``save_groups``。
    ``group_id -> {size_gb, files_shared, members:{hash:{site,downloader,added,
    downloaded,progress,state,fp}}, source_site, source_hash,
    hrs:{site:{site,required_hours,need_hours,seeded_seconds,settled,settled_at,checked_at,by_hash}},
    hr:<主账单(兼容)>, library:{in_library,first_at,media_id,path}, created, updated}``
    """

    def __init__(self, backend: LedgerBackend, log: Any = None) -> None:
        self.backend = backend
        self._log = log
        self._lib_pending: Dict[str, Dict[str, Any]] = {}   # 库记待办（进程内缓冲，不再走 kv 键）

    def items(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = self.backend.load_groups() or {}
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for gid, rec in data.items():
            if isinstance(rec, dict):
                members = rec.get("members")
                if not isinstance(members, dict):
                    rec = dict(rec)
                    rec["members"] = {}
                out[str(gid)] = rec
        return out

    def _write(self, data: Dict[str, Any]) -> None:
        try:
            self.backend.save_groups(data)
        except Exception as err:  # noqa: BLE001
            self._log and self._log(f"标签:文件组账本写入失败:{err}", "error")

    def group_of(self, hash_string: str) -> str:
        h = _clean(hash_string).lower()
        for gid, rec in self.items().items():
            if h in (rec.get("members") or {}):
                return gid
        return ""

    def group_with_fp(self, fp: str) -> str:
        """按特征码找资源组（辅种配对用）。"""
        _fp = _clean(fp)
        if not _fp:
            return ""
        for gid, rec in self.items().items():
            for m in (rec.get("members") or {}).values():
                if _clean((m or {}).get("fp")) == _fp:
                    return gid
        return ""

    def add_member(
        self,
        group_id: str,
        hash_string: str,
        *,
        site: str = "",
        downloader: str = "",
        size_gb: float = 0.0,
        files_shared: Optional[bool] = None,
        downloaded: bool = True,
        progress: float = 1.0,
        state: str = "",
        fp: str = "",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        gid = _clean(group_id)
        h = _clean(hash_string).lower()
        if not gid or not h:
            return {}
        ts = float(now if now is not None else time.time())
        data = self.items()
        rec = dict(data.get(gid) or {"members": {}})
        members = dict(rec.get("members") or {})
        # ★ 只有「下完」的种才建立资源/成为资源成员（没下完的只有种子，没有资源）
        if not downloaded and not members:
            return {"group_id": gid, "members": 0, "skipped": "not_downloaded"}
        prev = dict(members.get(h) or {})
        members[h] = {"site": _clean(site), "downloader": _clean(downloader), "added": prev.get("added") or ts,
                      "downloaded": bool(downloaded), "progress": round(float(progress or 0), 4)}
        if state:
            members[h]["state"] = _clean(state)
        _fp = _clean(fp) or _clean(prev.get("fp"))
        if _fp:
            members[h]["fp"] = _fp
        # 资源级的「来源站」= 真正把它下回来的那个站（H&R 义务所在）
        if downloaded and not _clean(rec.get("source_site")):
            rec["source_site"] = _clean(site)
            rec["source_hash"] = h
        rec["members"] = members
        # ★ 同一 hash 只能属于一个资源：从其它组里摘掉（fp 计算出来后从「关键词组」搬进「特征码组」）
        for other_gid in [k for k in data if k != gid and h in (data[k].get("members") or {})]:
            orec = dict(data.get(other_gid) or {})
            omembers = dict(orec.get("members") or {})
            omembers.pop(h, None)
            if omembers:
                orec["members"] = omembers
                orec["files_shared"] = True
                orec["updated"] = ts
                data[other_gid] = orec
            else:
                data.pop(other_gid, None)
        if size_gb:
            rec["size_gb"] = float(size_gb)
        rec["files_shared"] = bool(len(members) > 1 if files_shared is None else files_shared)
        rec.setdefault("created", ts)
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return {"group_id": gid, "members": len(members)}

    # ---------------------------------------------------------------- 资源级：来源站 / H&R / 库记
    def set_hr(
        self,
        group_id: str,
        *,
        site: str = "",
        required_hours: float = 0.0,
        need_hours: float = 0.0,
        by_hash: str = "",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """挂/更新资源上的 H&R 账单（义务靠来源站那个种子挂种结清）。

        ★ 10.0.0：账单**按来源站分账**（``hrs = {site: bill}``）。``hr`` 仍是「主账单」
        （``by_hash`` 命中的那张，否则第一张）。
        """
        gid = _clean(group_id)
        data = self.items()
        rec = dict(data.get(gid) or {})
        if not gid or not rec:
            return {}
        ts = float(now if now is not None else time.time())
        _site = _clean(site)
        _by = _clean(by_hash).lower()
        bills = dict(rec.get("hrs") or {})
        key = _site or _by or "_"
        hr = dict(bills.get(key) or {})
        hr.update({
            "site": _site or hr.get("site", ""),
            "required_hours": float(required_hours or hr.get("required_hours") or 0.0),
            "need_hours": float(need_hours or hr.get("need_hours") or 0.0),
            "by_hash": _by or hr.get("by_hash", ""),
            "checked_at": ts,
        })
        hr.setdefault("settled", False)
        bills[key] = hr
        rec["hrs"] = bills
        _main = next((b for b in bills.values() if _by and _clean(b.get("by_hash")).lower() == _by), None)
        rec["hr"] = _main or next(iter(bills.values()))
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return hr

    def note_hr_progress(
        self,
        group_id: str,
        *,
        seeded_seconds: float = 0.0,
        by_hash: str = "",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """记录来源种挂种进度；挂够要求 → **给资源结清 H&R 账单**。

        ★ 10.0.0：账单分站存 ``hrs``。给了 ``by_hash`` 就只更新它自己那张。
        """
        gid = _clean(group_id)
        data = self.items()
        rec = dict(data.get(gid) or {})
        if not gid or not rec:
            return {}
        bills = dict(rec.get("hrs") or {})
        if not bills:
            _hr0 = dict(rec.get("hr") or {})
            if _hr0:
                bills = {_clean(_hr0.get("site")) or "_": _hr0}
        if not bills:
            return {}
        ts = float(now if now is not None else time.time())
        seeded = float(seeded_seconds or 0.0)
        _by = _clean(by_hash).lower()
        _hit = None
        for key, b in list(bills.items()):
            b = dict(b)
            if _by and _clean(b.get("by_hash")).lower() not in ("", _by):
                continue
            b["seeded_seconds"] = round(seeded, 1)
            b["checked_at"] = ts
            need = max(float(b.get("required_hours") or 0.0), float(b.get("need_hours") or 0.0))
            if not b.get("settled") and need > 0 and seeded >= need * 3600.0:
                b["settled"] = True
                b["settled_at"] = ts
            bills[key] = b
            if _by and _clean(b.get("by_hash")).lower() == _by:
                _hit = b
        rec["hrs"] = bills
        rec["hr"] = _hit or next(iter(bills.values()))
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return rec["hr"]

    def set_library(
        self,
        group_id: str,
        in_library: bool,
        *,
        media_id: str = "",
        path: str = "",
        now: Optional[float] = None,
    ) -> bool:
        """资源级「库记」：这份内容是否已整理入库。"""
        gid = _clean(group_id)
        data = self.items()
        rec = dict(data.get(gid) or {})
        if not gid or not rec:
            return False
        ts = float(now if now is not None else time.time())
        lib = dict(rec.get("library") or {})
        if bool(lib.get("in_library")) == bool(in_library) and not media_id and not path:
            return False
        lib["in_library"] = bool(in_library)
        if in_library:
            lib.setdefault("first_at", ts)
        if media_id:
            lib["media_id"] = str(media_id)
        if path:
            lib["path"] = str(path)
        lib["updated"] = ts
        rec["library"] = lib
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return True

    # ------------------------------------------------------------ 资源级：身份
    def identity(self, group_id: str) -> str:
        """资源身份：``资源`` / ``普通``（无此资源返回空串）。"""
        rec = self.items().get(_clean(group_id)) or {}
        if not rec:
            return ""
        ident = _clean(rec.get("identity"))
        if ident in (SUB_RESOURCE, SUB_PLAIN):
            return ident
        if bool((rec.get("library") or {}).get("in_library")):
            return SUB_RESOURCE
        return SUB_PLAIN

    def set_identity(self, group_id: str, identity: str, *, by: str = "",
                     now: Optional[float] = None) -> bool:
        """写资源身份（``资源``/``普通``）。"""
        gid = _clean(group_id)
        ident = _clean(identity)
        if not gid or ident not in (SUB_RESOURCE, SUB_PLAIN):
            return False
        data = self.items()
        rec = dict(data.get(gid) or {})
        if not rec:
            return False
        if _clean(rec.get("identity")) == ident:
            return False
        ts = float(now if now is not None else time.time())
        rec["identity"] = ident
        rec["identity_by"] = _clean(by)
        rec["identity_at"] = ts
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return True

    def queue_library(
        self,
        hash_string: str,
        *,
        path: str = "",
        media_id: str = "",
        now: Optional[float] = None,
    ) -> str:
        """整理完成事件到达时登记「库记」。

        - 该 hash 已在账本里 → 直接写所属资源的 ``library``，返回 group_id；
        - 还没纳管（事件早于我们的扫描）→ 记进**进程内待办**，等 ``flush_pending_library`` 补齐。

        ★ 12.0.0：待办缓冲改存**进程内**（``_lib_pending``），不再走 kv 键 ``tag_lib_pending``。
        """
        h = _clean(hash_string).lower()
        gid = _clean(self.group_of(h)) if h else ""
        if gid:
            self.set_library(gid, True, media_id=media_id, path=path, now=now)
            return gid
        if not h:
            return ""
        pend = self._lib_pending
        ts = float(now if now is not None else time.time())
        rec = dict(pend.get(h) or {})
        rec["path"] = _clean(path) or rec.get("path") or ""
        if media_id:
            rec["media_id"] = str(media_id)
        rec.setdefault("first_at", ts)
        rec["updated"] = ts
        pend[h] = rec
        return ""

    def pending_library(self) -> Dict[str, Dict[str, Any]]:
        return {str(k): dict(v) for k, v in self._lib_pending.items() if isinstance(v, dict)}

    def flush_pending_library(self, *, now: Optional[float] = None) -> int:
        """把「已纳管」的库记待办落到资源上；返回落地条数。"""
        pend = self.pending_library()
        if not pend:
            return 0
        done = 0
        left: Dict[str, Dict[str, Any]] = {}
        for h, rec in pend.items():
            gid = self.group_of(h)
            if gid:
                if self.set_library(gid, True, media_id=str(rec.get("media_id") or ""),
                                    path=str(rec.get("path") or ""), now=now):
                    done += 1
                continue
            left[h] = rec
        self._lib_pending = left
        return done

    def resources(self, *, limit: int = 0) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for gid, rec in self.items().items():
            members = rec.get("members") or {}
            hr = dict(rec.get("hr") or {})
            lib = dict(rec.get("library") or {})
            _fps = sorted({_clean((m or {}).get("fp")) for m in members.values() if _clean((m or {}).get("fp"))})
            out.append({
                "group_id": gid,
                "fp": _fps[0] if _fps else "",
                "size_gb": round(float(rec.get("size_gb") or 0), 2),
                "members": len(members),
                "sites": sorted({str((m or {}).get("site") or "") for m in members.values() if (m or {}).get("site")}),
                "source_site": rec.get("source_site") or "",
                "hr": hr,
                "library": lib,
            })
        out.sort(key=lambda x: x["members"], reverse=True)
        return out[: max(1, int(limit))] if limit else out

    def remove_member(self, hash_string: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        """摘掉一个成员；返回 ``{found, group_id, remaining, delete_files}``。

        ``delete_files=True`` 仅当**组内再无成员**（最后一个站也不要了）。
        找不到组 = 独立种，按 ``remaining=0`` 处理（可以删文件）。
        """
        h = _clean(hash_string).lower()
        data = self.items()
        gid = ""
        for key, rec in data.items():
            if h in (rec.get("members") or {}):
                gid = key
                break
        if not gid:
            return {"found": False, "group_id": "", "remaining": 0, "delete_files": True}
        rec = dict(data.get(gid) or {})
        members = dict(rec.get("members") or {})
        members.pop(h, None)
        if members:
            rec["members"] = members
            rec["files_shared"] = True
            rec["updated"] = float(now if now is not None else time.time())
            data[gid] = rec
            self._write(data)
            return {"found": True, "group_id": gid, "remaining": len(members), "delete_files": False}
        data.pop(gid, None)
        self._write(data)
        return {"found": True, "group_id": gid, "remaining": 0, "delete_files": True}

    def stats(self) -> Dict[str, int]:
        items = self.items()
        multi = sum(1 for rec in items.values() if len(rec.get("members") or {}) > 1)
        with_fp = sum(1 for rec in items.values()
                      if any(_clean((m or {}).get("fp")) for m in (rec.get("members") or {}).values()))
        return {"groups": len(items), "multi_site_groups": multi, "groups_with_fp": with_fp}


def get_backend(plugin: Any) -> LedgerBackend:
    """取本插件的读写后端（热重载后重建，数据从库里来，不丢）。"""
    be = getattr(plugin, "_ledger_backend", None)
    if be is None:
        be = LedgerBackend(plugin)
        be.ensure_schema()
        plugin._ledger_backend = be
    return be
