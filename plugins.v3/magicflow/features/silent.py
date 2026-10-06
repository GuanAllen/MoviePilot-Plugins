# -*- coding: utf-8 -*-
"""魔流 · silent —— 静默池（托管非任务种：保挂/清理/分拣）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


from app.schemas import Response

from ..bonus import (
    calc_bonus_per_hour,
)
from ..persistence import OperationItem
from ..tags import (
    asset_member_hashes,
    is_asset_tags,
    is_library_asset,
    MARK_REUSE,
    SPECIAL_TAGS,
    MARK_HR,
    STATE_SILENT,
    SUB_NEW,
    SUB_PLAIN,
    SUB_RESOURCE,
    retag,
    tag_for,
)


from ..common import (
    RECOMMEND_SCAN_MAX,
    SILENT_HOST_INTERVAL_MINUTES,
    SILENT_HOST_TASK_ID,
    SILENT_HR_SPLIT_ENABLED,
    TAG_NEW_TIMEOUT,
    begin_decision_round,
    note_snapshot_pull,
    torrent_data_key,
)
from ..downloader_ops import seed_hours_for_hr


def _data_key(_t: Any) -> str:
    """种子「数据路径」key —— 唯一实现在 ``common.torrent_data_key``（不造第二口径）。"""
    return torrent_data_key(_t)


def _shared_key_hits(key: str, done: Dict[str, Set[str]], self_hash: str) -> bool:
    """``key`` 是否与「别的**已完成**种子」共用同一份数据（相等 / 互为上下级目录）。

    保守取向（Master 2026-10-07 00:04「只删真孤儿」）：判不准就当**共用** → 只删条目留文件。
    """
    k = str(key or "").rstrip("/")
    if not k:
        return False
    for k2, hs in (done or {}).items():
        kk = str(k2 or "").rstrip("/")
        if not kk:
            continue
        if k == kk or k.startswith(kk + "/") or kk.startswith(k + "/"):
            if any(str(x) != str(self_hash) for x in (hs or ())):
                return True
    return False


class SilentMixin:
    """silent 功能集（原 MagicFlow 方法原样搬入）。"""

    def silent_host(self) -> None:
        """★ 静默托管（**常驻 worker**，Master 2026-09-28 06:30：「常驻，不用每20分钟检查一次」）。

        静默池的「负责人」——常驻（reload 即注册，不随任务增减开关）、低频（默认 60min）。
        九步职责（每次运行在**操作记录**里留一条流水，明细即各步结果；职责说明见 docs/静默托管.md）：
        ① 池清理 ② **H&R 保挂**（只对欠 H&R 的种强制挂种）③ H&R 统一管理 ④ 辅种校验
        ⑤ 静默-普通 清理 ⑥ 推荐过期降级 ⑦ 分拣 ⑧ 静默-新 超时归普通 ⑨ 库内资产刷新
        """
        summary: List[tuple] = []

        def _step(key: str, label: str, fn) -> None:
            """跑一步：成功记结果文本，失败记失败原因（不中断后续步骤）。"""
            try:
                txt = fn() or ""
            except Exception as err:  # noqa: BLE001
                self._log(f"静默托管:{label}失败:{err}", "warning")
                summary.append((key, f"{label} 失败：{err}"))
                return
            summary.append((key, f"{label}：{txt}" if txt else f"{label}：无需处理"))

        try:
            store = self._tag_state()
            _started = time.time()
            # ★ P0：本轮只拉一次 qB 全量快照，同一轮内的 H&R 管理 / 超时归位 / 空壳清理共用一份
            begin_decision_round()
            self._decision_round_label = "silent_host"
            _round_snap = self._tag_all_torrents() or {}
            note_snapshot_pull(1)
            # 上一轮若被 reload/重启打断，会留下一条「运行中」记录 → 先收尾（>10min 才算异常）
            try:
                for _r in self._store.journal.list_by_task(SILENT_HOST_TASK_ID, limit=5):
                    if str(getattr(_r, "state", "")) in ("submitting", "accepted") \
                            and (time.time() - float(getattr(_r, "created_at", 0) or 0)) > 600:
                        self._store.journal.finalize(
                            _r.operation_id, "failed",
                            items=[OperationItem(hash="", title="上一轮被中断（reload/重启）", source="run")],
                            error_message="上一轮被中断",
                        )
            except Exception:  # noqa: BLE001
                pass
            # ★ 操作记录：开始时先登记一条「运行中」，结束时落明细（前台「操作记录」可展开）
            _rec = None
            try:
                _rec = self._store.journal.add(
                    task_id=SILENT_HOST_TASK_ID, kind="run",
                    items=[OperationItem(hash="", title="静默托管运行中…", source="run")],
                )
            except Exception as err:  # noqa: BLE001
                self._log(f"静默托管:操作记录登记失败:{err}", "warning")

            def _s1() -> str:
                i = self._silent_purge_incomplete(apply=True, limit=200)
                if i.get("deleted"):
                    self._log(f"魔流:静默托管:未下完直接删 {i.get('deleted')} 个（不计 H&R）")
                    return f"删未下完 {i.get('deleted')} 个（不计 H&R）"
                return ""

            def _s2() -> str:
                # ★ 11.11.0：静默池全 paused，H&R 保挂已拆到 __hr_host__（hr_host worker）。本步退役。
                return ""

            def _s3() -> str:
                # ★ 11.11.0：H&R 统一管理已迁移到 hr_host() worker，不再由静默托管负责。本步退役。
                return ""

            def _s4() -> str:
                i = self._silent_verify_marks(apply=True, limit=60)
                if i.get("checked"):
                    self._log(f"魔流:静默托管:辅种 recheck {i.get('checked')} 个")
                    return f"recheck {i.get('checked')} 个"
                return ""

            def _s5() -> str:
                i = self._silent_plain_sweep(apply=True, limit=0)
                if i.get("deleted"):
                    self._log(f"魔流:静默托管:删除低效普通种 {i.get('deleted')} 个")
                    return f"删低效普通种 {i.get('deleted')} 个"
                return ""

            def _s6() -> str:
                i = self._recommend_downgrade_expired(apply=True, limit=0)
                if i.get("downgraded"):
                    self._log(f"魔流:静默托管:推荐过期降级转普通 {i.get('downgraded')} 个")
                    return f"推荐过期降级 {i.get('downgraded')} 个"
                return ""

            def _s7() -> str:
                self._silent_triage(apply=True, limit=60, budget=600.0)
                return ""

            def _s8() -> str:
                _snap = _round_snap
                try:
                    _hr_wait = self._silent_hr_pending(_snap)
                except Exception:  # noqa: BLE001
                    _hr_wait = set()
                moved = store.expire_new(
                    timeout=float(self._tags_cfg.get("new_timeout") or TAG_NEW_TIMEOUT),
                    skip=_hr_wait,
                )
                if moved:
                    self._log(f"魔流:静默托管:「静默-新」超时归「静默-普通」{len(moved)} 个")
                    for _h in moved:
                        try:
                            self._silent_to_plain(_h)
                        except Exception:  # noqa: BLE001
                            pass
                    return f"超时归普通 {len(moved)} 个"
                return ""

            def _s10() -> str:
                # ★ 7.6.0: 文件已不在的托管种 → 认出即清（只删种不删文件）
                i = self._missing_files_tick(apply=True, snap=_round_snap)
                if i.get("deleted"):
                    return f"空壳种清理 {i.get('deleted')} 个（标称 {i.get('size_gb')}GB）"
                return ""

            def _s9() -> str:
                i = self.sync_tag_assets(apply=True)
                if i.get("changed"):
                    self._log(f"魔流:静默托管:库内资产标记刷新 {i.get('changed')} 个（资产 {i.get('asset')}）")
                    return f"资产标记刷新 {i.get('changed')} 个（资产 {i.get('asset')}）"
                return ""

            def _s11() -> str:
                # ★ 12.7.1 静默不变量**周期收敛**：账本 state=静默 但 qB 没停的 → 补 pause
                #   （设计口径 11.11.0「静默池本意就是暂停不上传」；只 pause、不删、不 resume）
                i = self._silent_enforce_pause(apply=True)
                if i.get("paused") or i.get("failed"):
                    return (f"补暂停 {i.get('paused')} 个（违背不变量 {i.get('violations')}，"
                            f"失败 {i.get('failed')}）")
                return ""

            _step("purge", "①池清理", _s1)
            _step("hr_keep", "②H&R保挂", _s2)
            _step("hr_guard", "③H&R管理", _s3)
            _step("verify", "④辅种校验", _s4)
            _step("plain", "⑤普通清理", _s5)
            _step("downgrade", "⑥推荐降级", _s6)
            _step("triage", "⑦分拣", _s7)
            _step("expire", "⑧超时归位", _s8)
            _step("assets", "⑨资产刷新", _s9)
            _step("missing", "⑩空壳清理", _s10)
            _step("pause", "⑪不变量收敛", _s11)

            self._silent_host_last = time.time()
            self._decision_round_end()
            # ★ 操作记录：落明细 = 九步结果（前台「操作记录」可展开）
            try:
                _items = [OperationItem(hash="", title="静默托管运行完成", source="run")]
                for _k, _t in summary:
                    _items.append(OperationItem(hash="", title=str(_t), source=str(_k)))
                _dur = round(time.time() - _started, 2)
                if _rec is not None:
                    self._store.journal.finalize(_rec.operation_id, "completed", items=_items, duration=_dur)
                else:
                    self._store.journal.record(task_id=SILENT_HOST_TASK_ID, kind="run", items=_items, duration=_dur)
            except Exception as err:  # noqa: BLE001
                self._log(f"静默托管:操作记录写入失败:{err}", "warning")
        except Exception as err:  # noqa: BLE001
            self._log(f"静默托管异常:{err}", "warning")

    def _silent_host_card(self) -> Dict[str, Any]:
        """★ 「静默托管」常驻任务在**任务列表**里的只读条目（Master 2026-09-28 06:33）。

        带 30s 内存缓存（按运行身份）：原来每次 /status 都会全量走 _tag_all_torrents
        拉到 868 个种子，跳表 + 分类 + stat 组装，在 status 30s 轮询时是最大慢点之一。
        缓存后稳态首次 0.01s。
        """
        cache = getattr(self, "_silent_host_card_cache", None)
        now = time.time()
        if cache and (now - cache["ts"]) < 30:
            return cache["data"]
        n_sil = 0
        n_hr = 0
        by_state: Dict[str, int] = {}
        by_site: Dict[str, Dict[str, int]] = {}
        try:
            _store = self._tag_state()
            _led = _store.items()
            for _h, _t in (self._tag_all_torrents() or {}).items():
                _tg = [str(x) for x in (getattr(_t, "tags", None) or [])]
                _rec = _led.get(_h) or {}
                if str(_rec.get("state") or "") != STATE_SILENT:
                    continue  # ★ 账本判池内：职务=静默才算；在岗(刷流/魔力)/未知跳过
                n_sil += 1
                _ishr = bool(MARK_HR in _tg)
                if _ishr:
                    n_hr += 1
                _sub = str(_rec.get("sub") or SUB_NEW)
                by_state[_sub] = int(by_state.get(_sub) or 0) + 1
                _site = str(_rec.get("site") or "") or self._torrent_site_name(_tg, "") or "未知"
                _d = by_site.setdefault(_site, {"total": 0, "hr": 0})
                _d["total"] += 1
                if _ishr:
                    _d["hr"] += 1
        except Exception:  # noqa: BLE001
            try:
                led = self._tag_state().items() or {}
                n_sil = sum(1 for r in led.values() if str(r.get("state") or "") == STATE_SILENT)
                n_hr = 0
            except Exception:  # noqa: BLE001
                n_sil, n_hr = 0, 0
        try:
            _min = float(getattr(self, "_tags_cfg", {}).get("host_interval") or SILENT_HOST_INTERVAL_MINUTES)
        except Exception:  # noqa: BLE001
            _min = float(SILENT_HOST_INTERVAL_MINUTES)
        last = float(getattr(self, "_silent_host_last", 0) or 0)
        try:
            _rows = self._store.journal.list_by_task(SILENT_HOST_TASK_ID, limit=1)
            if _rows:
                _t = float(getattr(_rows[0], "resolved_at", None) or getattr(_rows[0], "created_at", 0) or 0)
                if _t > last:
                    last = _t
        except Exception:  # noqa: BLE001
            pass
        return {
            "id": SILENT_HOST_TASK_ID,
            "name": "静默托管",
            "builtin": True,
            "enabled": True,
            "run_mode": "running",
            "task_type": "host",
            "state": "running",
            "site_id": 0,
            "site_domain": "",
            "site_name": "全部站点（静默池）",
            "downloader": "所有下载器",
            "brush_tag": "魔流-<站点>-静默[-子类]",
            "save_path": "",
            "seeding_count": n_sil,
            "hr_count": n_hr,
            "nonhr_count": max(0, n_sil - n_hr),
            "active_seeding_count": n_sil,
            "downloading_count": 0,
            "paused_count": 0,
            "classify": {
                "by_state": by_state,
                "by_site": by_site,
            },
            "host_interval_minutes": round(_min, 1),
            "host_last_run": (time.strftime("%m-%d %H:%M", time.localtime(last)) if last else "—"),
        }
        out = {
            "id": SILENT_HOST_TASK_ID,
            "name": "静默托管",
            "builtin": True,
            "enabled": True,
            "run_mode": "running",
            "task_type": "host",
            "state": "running",
            "site_id": 0,
            "site_domain": "",
            "site_name": "全部站点（静默池）",
            "downloader": "所有下载器",
            "brush_tag": "魔流-<站点>-静默[-子类]",
            "save_path": "",
            "seeding_count": n_sil,
            "hr_count": n_hr,
            "nonhr_count": max(0, n_sil - n_hr),
            "active_seeding_count": n_sil,
            "downloading_count": 0,
            "paused_count": 0,
            "classify": {
                "by_state": by_state,
                "by_site": by_site,
            },
            "host_interval_minutes": round(_min, 1),
            "host_last_run": (time.strftime("%m-%d %H:%M", time.localtime(last)) if last else "—"),
        }
        if cache is None:
            cache = self._silent_host_card_cache = {}
        cache["ts"] = now
        cache["data"] = out
        return out

    def silent_enforce(self, confirm: Any = 0) -> Response:
        """★ 12.7.1 静默不变量收敛（UI 入口）——把「账本静默、qB 没停」的种补 pause。

        默认干跑（``confirm=0``）；真写需 ``confirm=1``。幂等、只 pause（不删种、不动文件）。
        职责：存量自愈（设计口径「静默池本意就是暂停不上传」，11.11.0 07:55）。
        """
        try:
            _c = 1 if bool(self._as_bool_arg(confirm)) else 0
        except Exception:  # noqa: BLE001
            _c = 1 if str(confirm or "").strip().lower() in ("1", "true", "yes", "on") else 0
        try:
            rep = self._silent_enforce_pause(apply=bool(_c))
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"静默不变量收敛失败: {e}", data={})
        _n = int(rep.get("violations") or 0)
        if not _c:
            msg = f"干跑：违背不变量 {_n} 个（未发任何写请求）"
        else:
            msg = f"已补 pause {rep.get('paused', 0)} 个（违背 {_n}，失败 {rep.get('failed', 0)}）"
        if rep.get("disabled"):
            msg = "静默拆分未启用（SILENT_HR_SPLIT_ENABLED=False），已跳过"
        return Response(success=True, message=msg, data=rep)

    def silent_pool(self, limit: Any = 400, records: Any = 60) -> Response:
        """★ 静默池全局视图（7.16.0，只读）：概览 / 按站 / 条目 / 记录。

        静默池 = 「无主」种的池子（跨站 / 跨任务）。这些种不归任何任务管，由常驻
        「静默托管」worker 负责：保挂 H&R、清未下完、超时降级（新→普通）、分拣（推荐→资源）。
        本端点只做聚合（真值源 = 标签账本 ``tag_state`` + 下载器快照 + 跨站来源份），
        不改动任何逻辑。
        """
        try:
            _limit = int(limit or 400)
        except (TypeError, ValueError):
            _limit = 400
        try:
            _rlimit = int(records or 60)
        except (TypeError, ValueError):
            _rlimit = 60
        now = time.time()
        try:
            led = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            led = {}
        try:
            torrents = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            torrents = {}
        try:
            cssrc = dict(self._crossseed_sources().items() or {})
        except Exception:  # noqa: BLE001
            cssrc = {}
        by_sub: Dict[str, int] = {}
        sites: Dict[str, Dict[str, Any]] = {}
        items: List[Dict[str, Any]] = []
        hr_n = 0
        total_gb = 0.0
        incomplete = 0
        for h, t in torrents.items():
            rec = led.get(h) or {}
            if str(rec.get("state") or "") != STATE_SILENT:
                continue  # 只看「职务=静默」的；在岗（刷流/魔力）不算池内
            tags = [str(x) for x in (getattr(t, "tags", None) or [])]
            sub = str(rec.get("sub") or SUB_NEW)
            site = str(rec.get("site") or "") or self._torrent_site_name(tags, "") or "未知"
            # ★ 11.11.0：owed_hr = _hr_obligation 真值（弃退役标签 MARK_HR 的假信号）
            ishr = False
            try:
                ishr = bool(self._hr_obligation(site, t, snap=torrents)[0])
            except Exception:  # noqa: BLE001
                ishr = False
            try:
                size_gb = float(rec.get("size_gb") or getattr(t, "size_gb", 0) or 0.0)
            except (TypeError, ValueError):
                size_gb = 0.0
            try:
                progress = float(getattr(t, "progress", 0) or 0.0)
            except (TypeError, ValueError):
                progress = 0.0
            # ★ 进池时间：账本不保证有 ts（各入口写入字段不一）→ 没有就 None，别编造
            _ts = rec.get("ts") or rec.get("since") or rec.get("taken_at") or 0
            try:
                _tsf = float(_ts)
            except (TypeError, ValueError):
                _tsf = 0.0
            if _tsf > 1e11:
                _tsf = _tsf / 1000.0
            age_h = round(max(0.0, now - _tsf) / 3600.0, 2) if _tsf > 0 else None
            remain_min = None
            need_hours = 0.0
            seeded_h = 0.0
            cs = cssrc.get(h) or {}
            if cs:
                try:
                    until = float(cs.get("seed_until") or 0.0)
                except (TypeError, ValueError):
                    until = 0.0
                if until:
                    remain_min = round(max(0.0, (until - now) / 60.0), 1)
                try:
                    need_hours = float(cs.get("need_hours") or 0.0)
                except (TypeError, ValueError):
                    need_hours = 0.0
                try:
                    seeded_h = round(float(cs.get("seeded_sec") or 0.0) / 3600.0, 2)
                except (TypeError, ValueError):
                    seeded_h = 0.0
            src = "crossseed" if (rec.get("crossseed") or cs) else "task"
            if progress < 0.999:
                incomplete += 1
            hr_n += 1 if ishr else 0
            total_gb += size_gb
            by_sub[sub] = int(by_sub.get(sub) or 0) + 1
            d = sites.setdefault(site, {"site": site, "total": 0, "hr": 0, "size_gb": 0.0})
            d["total"] += 1
            d["hr"] += 1 if ishr else 0
            d["size_gb"] = round(float(d["size_gb"]) + size_gb, 2)
            items.append({
                "hash": h,
                "title": str(rec.get("title") or getattr(t, "title", "") or ""),
                "site": site,
                "sub": sub,
                "hr": ishr,
                "owed_hr": ishr,
                "size_gb": round(size_gb, 2),
                "progress": round(progress, 4),
                "state": str(getattr(t, "state", "") or ""),
                "taken_by": str(rec.get("taken_by") or ""),
                "source": src,
                "crossseed": bool(src == "crossseed"),
                "remain_min": remain_min,
                "need_hours": need_hours,
                "seeded_h": seeded_h,
                "age_h": age_h,
                "reason": str(rec.get("reason") or ""),
            })
        # 未下完的排前面，其次按进池时间倒序
        items.sort(key=lambda x: (0 if float(x.get("progress") or 0) < 0.999 else 1, -float(x.get("age_h") or 0.0)))
        sub_labels = {SUB_NEW: "静默-新", SUB_RESOURCE: "静默-资源", SUB_PLAIN: "静默-普通"}
        try:
            host_min = float(getattr(self, "_tags_cfg", {}).get("host_interval") or SILENT_HOST_INTERVAL_MINUTES)
        except Exception:  # noqa: BLE001
            host_min = float(SILENT_HOST_INTERVAL_MINUTES)
        try:
            new_timeout_h = float(self._tags_cfg.get("new_timeout") or 0) / 3600.0
        except Exception:  # noqa: BLE001
            new_timeout_h = 0.0
        last = float(getattr(self, "_silent_host_last", 0) or 0)
        recs: List[Dict[str, Any]] = []
        try:
            rows = self._store.journal.list_by_task(SILENT_HOST_TASK_ID, limit=_rlimit) or []
            for r in rows:
                try:
                    d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
                except Exception:  # noqa: BLE001
                    continue
                ts = float(d.get("ts") or d.get("created_at") or d.get("resolved_at") or 0)
                if ts > last:
                    last = ts
                recs.append({
                    "ts": ts,
                    "kind": str(d.get("kind") or ""),
                    "count": int(d.get("count") or len(d.get("items") or []) or 0),
                    "reason": str(d.get("reason") or d.get("message") or ""),
                    "duration_ms": d.get("duration_ms") or d.get("duration") or 0,
                    "items": (d.get("items") or [])[:6],
                })
        except Exception:  # noqa: BLE001
            recs = []
        data = {
            "summary": {
                "total": len(items),
                "hr": hr_n,
                "non_hr": max(0, len(items) - hr_n),
                "incomplete": incomplete,
                "size_gb": round(total_gb, 2),
                "subs": [
                    {"key": k, "label": sub_labels.get(k, k), "count": v}
                    for k, v in sorted(by_sub.items(), key=lambda kv: -kv[1])
                ],
                "sites": sorted(sites.values(), key=lambda x: -int(x.get("total") or 0)),
            },
            "items": items[:_limit],
            "items_truncated": max(0, len(items) - _limit),
            "records": recs,
            "host": {
                "interval_minutes": round(host_min, 1),
                "last_run": (time.strftime("%m-%d %H:%M", time.localtime(last)) if last else "—"),
                "last_run_ts": last,
            },
            "settings": {
                "new_timeout_hours": round(new_timeout_h, 2),
                "hr_default_hours": 0.0,
            },
            "stage": "active",
            "pool_cleanup": True,
            "generated_at": now,
        }
        try:
            data["settings"]["hr_default_hours"] = float(
                getattr(self, "_cs_cfg", {}).get("seed_hours_default") or 0.0
            )
        except Exception:  # noqa: BLE001
            pass
        return Response(success=True, data=data)

    def _silent_pool_records(self, limit: int = 60) -> List[Dict[str, Any]]:
        """静默池操作记录（kind=run / reseed 等，来源于静默托管 worker）。"""
        try:
            rows = self._store.journal.list_recent(limit=limit, kind="run") or []
            return [r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in rows]
        except Exception:  # noqa: BLE001
            return []

    def _silent_audit(self, limit: int = 1000) -> Dict[str, Any]:
        """★ 11.11.0：静默池盘点（只读）——一次调用答「池里 704 个怎么分类、谁违背不变量」。

        四类判据（真值源同源，不造第二真值源）：
          - owed_hr：``_hr_obligation`` 真值（欠 H&R）——注意：欠债种应由 hr_host 迁到保种，池里不该有；
          - library_asset：库内资产（★ 12.0.0 真值 = ``mf_resource.in_library`` 随资源回填的
            ``rec["in_library"]`` 或身份「资源」；永不删）；
          - crossseed：``_crossseed_source_hashes``（跨站来源份 H&R 保种期）；
          - claim / manual：``_claim_protected_hashes`` / ``store.protected_torrents``（承诺）；
          - stalled_violation：qB 态不在 paused/stopped/queued（= 违背「静默全 paused」不变量）；
          - 其余 → relocate（清理候选）。
        """
        counts = {"owed_hr": 0, "library_asset": 0, "crossseed": 0, "claim": 0,
                  "manual": 0, "stalled_violation": 0, "relocate": 0, "total": 0}
        items: List[Dict[str, Any]] = []
        try:
            led = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            led = {}
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        try:
            cssrc = {str(x).strip().lower() for x in (self._crossseed_source_hashes() or set())}
        except Exception:  # noqa: BLE001
            cssrc = set()
        try:
            claim = {str(x).strip().lower() for x in (self._claim_protected_hashes() or set())}
        except Exception:  # noqa: BLE001
            claim = set()
        # ★ 13.0.0（Master「辅种应该按资源的身份打标签」）：副本跟随资源身份。
        #   真值源 = 资源账本成员表；另外再按 **保存目录/名字** 兜一层（同数据的副本共享目录）。
        try:
            _asset_members = set(asset_member_hashes(self._tag_groups()) or set())
        except Exception:  # noqa: BLE001
            _asset_members = set()
        #   「资产目录」集合：资产份（账本 in_library/身份资源，或资源成员）用的保存目录+种名。
        _asset_keys: Set[str] = set()
        for _h2, _t2 in (snap or {}).items():
            _hh2 = str(_h2 or "").strip().lower()
            _r2 = led.get(_hh2) or {}
            if not (bool(_r2.get("in_library")) or str(_r2.get("sub") or "") == SUB_RESOURCE
                    or _hh2 in _asset_members):
                continue
            _k = _data_key(_t2)
            if _k:
                _asset_keys.add(_k)
        try:
            manual = set()
            store = getattr(self, "_store", None)
            if store is not None:
                _tids = list((getattr(self, "_task_configs", None) or {}).keys())
                _tids.append("")
                for _tid in _tids:
                    try:
                        manual |= set(store.get_protected_torrents(_tid) or set())
                    except Exception:  # noqa: BLE001
                        continue
            manual = {str(x).strip().lower() for x in manual}
        except Exception:  # noqa: BLE001
            manual = set()
        _lim = int(limit or 0)
        for h, rec in list(led.items()):
            hh = str(h or "").strip().lower()
            if str((rec or {}).get("state") or "") != STATE_SILENT:
                continue
            counts["total"] += 1
            t = snap.get(hh)
            tags = [str(x) for x in (getattr(t, "tags", None) or [])] if t is not None else []
            site = str((rec or {}).get("site") or "") or self._torrent_site_name(tags, "")
            sub = str((rec or {}).get("sub") or SUB_NEW)
            owed = False
            if t is not None:
                try:
                    owed = bool(self._hr_obligation(site, t, snap=snap)[0])
                except Exception:  # noqa: BLE001
                    owed = False
            # ★ 12.0.0：库内资产真值 = 资源库记（``mf_resource.in_library``，随资源回填）或身份「资源」。
            #   旧判据 ``rec["asset"]`` 是 7.0.0 已退役的幽灵字段（恒空）；``is_asset_tags`` 也因
            #   「标签主权」摘掉了 qB 的 已整理/辅种 而失效 —— 两条都不可再用。
            asset = bool((rec or {}).get("in_library")) or (sub == SUB_RESOURCE)
            if not asset and hh in _asset_members:
                asset = True
            if not asset and t is not None and _asset_keys:
                _k = _data_key(t)
                if _k and _k in _asset_keys:
                    asset = True
            stalled = False
            if t is not None:
                st = str(getattr(t, "state", "") or "").strip().lower()
                stalled = not (st.startswith("paused") or st.startswith("stopped")
                               or st.startswith("queued"))
            if owed:
                cls = "owed_hr"
            elif asset:
                cls = "library_asset"
            elif hh in cssrc:
                cls = "crossseed"
            elif hh in claim:
                cls = "claim"
            elif hh in manual:
                cls = "manual"
            else:
                cls = "relocate"
            counts[cls] = int(counts.get(cls) or 0) + 1
            if stalled:
                counts["stalled_violation"] = int(counts["stalled_violation"]) + 1
            if _lim and len(items) >= _lim:
                continue
            items.append({
                "hash": hh, "site": site, "sub": sub,
                "class": cls, "owed_hr": bool(owed),
                "stalled_violation": bool(stalled),
                "state": str(getattr(t, "state", "") or "") if t is not None else "",
                "size_gb": round(float((rec or {}).get("size_gb") or (getattr(t, "size_gb", 0) or 0.0)), 2),
            })
        return {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stage": "active",
            "pool_cleanup": True,
            "counts": counts,
            "items": items,
            "source_of_truth": ["tag_state(账本)", "_tag_all_torrents()", "_hr_obligation",
                                "_crossseed_source_hashes", "_claim_protected_hashes",
                                "store.protected_torrents"],
            "note": ("静默池全 paused 硬不变量：stalled_violation = 违背不变量的种；"
                     "owed_hr 应由 hr_host 迁到保种（池里不该有）；relocate = 清理候选（删条目+删文件，过删除闸门）。"),
        }

    # ---------------------------------------------------------
    # 静默池分拣（3.14.0）：静默-新 --(挂种完成 H&R)--> 推荐 → 整理入库 → 静默-资源
    #                                                    否则 → 静默-普通
    # ---------------------------------------------------------

    def _silent_hr_done(self, site: str, torrent: Any) -> Tuple[bool, str]:
        """静默种的 H&R/保种义务是否完成（站点规则 + 实测做种时长）。无 H&R → 直接算完成。

        ★ 7.20.1：站点短名 → 域名再查规则库。规则库（``sites/rules.py``）的键是**域名**，
        而账本/标签里存的是**中文短名**（如「红豆饭」）—— 不转换就查不到 → 全落「未知保守
        24h」→ 假 H&R：普通清理被过度保护、分拣（新→推荐）被无限期挂起。
        """
        dom = str(site or "").strip().lower()
        try:
            dom = self._site_domain_by_name(site) or dom
        except Exception:  # noqa: BLE001
            pass
        try:
            protect, hours, src = self._crossseed_hr_decision(dom, None)
        except Exception:  # noqa: BLE001
            protect, hours, src = False, 0.0, "unknown"
        if not protect:
            return True, f"无H&R({src})"
        need = 0.0
        try:
            need = float(self._crossseed_seed_need_hours(dom) or 0.0)
        except Exception:  # noqa: BLE001
            need = 0.0
        if need <= 0:
            need = float(hours or 0.0)
        if need <= 0:
            return True, f"无时长要求({src})"
        try:
            seeded = seed_hours_for_hr(torrent) * 3600.0
        except Exception:  # noqa: BLE001
            seeded = 0.0
        if seeded >= need * 3600.0:
            return True, f"已挂{seeded / 3600.0:.1f}h/{need:.0f}h"
        return False, f"挂{seeded / 3600.0:.1f}h/{need:.0f}h"

    def _silent_to_plain(self, h: str) -> bool:
        """静默-新 → 静默-普通（不达标；此后可被磁盘压力清理）。"""
        hh = str(h or "").strip().lower()
        if not hh:
            return False
        try:
            rec = self._tag_state().get(hh) or {}
        except Exception:  # noqa: BLE001
            rec = {}
        site = str(rec.get("site") or "").strip()
        dl_name = str(rec.get("downloader") or "qbittorrent")
        try:
            t = (self._tag_all_torrents() or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(t, "tags", None) or [])] if t is not None else []
        except Exception:  # noqa: BLE001
            cur = []
        if not site:
            site = self._torrent_site_name(cur, "")
        # ★ 降级要**摘掉**「魔流-推荐」（它是推荐生命周期的标记，不走状态模型保留）
        _keep = tuple(x for x in SPECIAL_TAGS if x != "魔流-推荐")
        new_tags = (
            retag(cur, site=site, state=STATE_SILENT, sub=SUB_PLAIN, keep=_keep)
            if cur
            else [tag_for(site, STATE_SILENT, SUB_PLAIN)]
        )
        ok = False
        try:
            dl = self._get_downloader(dl_name)
            fn = getattr(dl, "replace_torrent_tags", None) if dl is not None else None
            ok = bool(fn(hh, new_tags)) if callable(fn) else False
        except Exception as err:  # noqa: BLE001
            self._log(f"静默分拣:归普通失败 {hh[:12]}:{err}", "warning")
            ok = False
        if ok:
            try:
                self._tag_state().put(hh, {"sub": SUB_PLAIN, "reason": "静默分拣:未达标→普通"})
            except Exception:  # noqa: BLE001
                pass
        if ok:
            self._silent_pause_gate(hh)
        return ok


    def _promote_resource(self, gid: str) -> int:
        """★ 资源已入库 → **立刻**把该资源的「静默」成员转「静默-资源」。

        Master 2026-09-28 07:23：入库后应该**当场**变「静默-资源」，而不是等静默托管那轮
        分拣（现在每小时一轮 → 最多滞后 1 小时）。入库事件（TransferComplete）/ 推荐确认
        入库成功后直接调用本方法。
        """
        _gid = str(gid or "").strip()
        if not _gid:
            return 0
        try:
            rec = (self._tag_groups().items() or {}).get(_gid) or {}
            members = [str(h).lower() for h in (rec.get("members") or {}) if h]
        except Exception:  # noqa: BLE001
            return 0
        st = self._tag_state()
        try:
            self._tag_groups().set_identity(_gid, SUB_RESOURCE, by="promote")
        except Exception:  # noqa: BLE001
            pass
        n = 0
        for _h in members:
            try:
                cur = st.get(_h) or {}
                if str(cur.get("state") or "") != STATE_SILENT:
                    continue
                if str(cur.get("sub") or "") == SUB_RESOURCE:
                    continue
                if self._silent_to_resource(_h):
                    n += 1
            except Exception:  # noqa: BLE001
                continue
        if n:
            self._log(f"入库即转:资源 {_gid[:40]} → 静默-资源 {n} 个")
        return n

    def _silent_to_resource(self, h: str) -> bool:
        """静默-新 → 静默-资源（该**资源**已在影视库；库内资产永不删）。

        与 ``_silent_to_plain`` 同构，仅状态子类与账本标记不同。
        """
        hh = str(h or "").strip().lower()
        if not hh:
            return False
        try:
            rec = self._tag_state().get(hh) or {}
        except Exception:  # noqa: BLE001
            rec = {}
        site = str(rec.get("site") or "").strip()
        dl_name = str(rec.get("downloader") or "qbittorrent")
        try:
            t = (self._tag_all_torrents() or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(t, "tags", None) or [])] if t is not None else []
        except Exception:  # noqa: BLE001
            cur = []
        if not site:
            site = self._torrent_site_name(cur, "")
        _keep = tuple(x for x in SPECIAL_TAGS if x != "魔流-推荐")
        new_tags = (
            retag(cur, site=site, state=STATE_SILENT, sub=SUB_RESOURCE, keep=_keep)
            if cur
            else [tag_for(site, STATE_SILENT, SUB_RESOURCE)]
        )
        ok = False
        try:
            dl = self._get_downloader(dl_name)
            fn = getattr(dl, "replace_torrent_tags", None) if dl is not None else None
            ok = bool(fn(hh, new_tags)) if callable(fn) else False
        except Exception as err:  # noqa: BLE001
            self._log(f"静默分拣:归资源失败 {hh[:12]}:{err}", "warning")
            ok = False
        if ok:
            try:
                self._tag_state().put(hh, {"sub": SUB_RESOURCE,
                                           "reason": "静默分拣:资源已入库→静默-资源"})
            except Exception:  # noqa: BLE001
                pass
        if ok:
            self._silent_pause_gate(hh)
        return ok

    def _silent_pause_gate(self, hashes: Any) -> Dict[str, Any]:
        """★ 静默硬不变量（11.11.0）：任何 ``state=静默`` 的种子一律 pause（**无 H&R 例外**）。

        H&R 保种已拆到 ``__hr_host__``（职务 ``保种``），静默池不再 resume 任何种。
        所有写 ``state=静默`` 的路径，写完账本后**立即**调它。幂等（已暂停的不重复写）。
        """
        rep: Dict[str, Any] = {"paused": 0, "failed": 0}
        if not SILENT_HR_SPLIT_ENABLED:
            rep["disabled"] = True
            return rep
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        hs = [str(h or "").strip().lower() for h in hs if str(h or "").strip()]
        if not hs:
            return rep
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        live = [h for h in hs if h in snap]
        if not live:
            return rep
        try:
            dl = self._get_downloader("qbittorrent")
            if dl is not None:
                n, _e = dl.pause_torrents(live)
                rep["paused"] = int(n or 0)
                if _e:
                    rep["failed"] = int(rep.get("failed") or 0) + 1
        except Exception as err:  # noqa: BLE001
            rep["failed"] = int(rep.get("failed") or 0) + 1
            self._log(f"静默闸:暂停失败:{err}", "warning")
        return rep

    def _silent_enforce_pause(self, apply: bool = True, limit: int = 0) -> Dict[str, Any]:
        """★ 12.7.1 静默不变量**周期收敛**：把「账本 state=静默、qB 里却没停」的种补 pause。

        Master 2026-10-06 22:53「之前设计怎么做的呀」→ 设计原话（11.11.0）07:55
        「**静默池本意就是暂停不上传**」：任何 ``state=静默`` 的种一律 pause，**无例外**；
        「库内资产」只保证**永不删**（12.3.0 删除闸门第 5 类硬拦），**不保证在做种**。

        为什么要这一步：``_silent_pause_gate`` 只在**写状态那一刻**调用，「补 pause」又只在手动跑
        阶段 2 迁出时**按 sub 过滤**顺带做 → **存量违背无人收敛**（2026-10-06 实测 36 个：
        35 个 ``stalledUP`` + 1 个 ``uploading``，都是 sub=资源/新 的库内资产/迁出候选）。

        真值源：``_silent_audit`` 的 ``stalled_violation``（与 ``_delete_gate`` 同源，不造第二真值源）。
        幂等：已 paused 的不会再写；**只 pause，不删种、不动文件、不 resume**。
        调用点：① ``silent_host`` 周期步（自动收敛）② ``GET /agent/silent/enforce``（手动，默认干跑）。
        """
        rep: Dict[str, Any] = {"apply": bool(apply), "scanned": 0, "violations": 0,
                              "paused": 0, "failed": 0, "items": [], "note": ""}
        if not SILENT_HR_SPLIT_ENABLED:
            rep["disabled"] = True
            return rep
        audit = self._silent_audit(limit=0)
        rep["scanned"] = int((audit.get("counts") or {}).get("total") or 0)
        bad = [str(it.get("hash") or "").strip().lower()
               for it in (audit.get("items") or [])
               if it.get("stalled_violation") and str(it.get("hash") or "").strip()]
        rep["violations"] = len(bad)
        rep["items"] = bad[:50]
        if not bad:
            rep["note"] = "静默池全 paused（不变量成立）"
            return rep
        if limit:
            bad = bad[:int(limit)]
        if not apply:
            rep["note"] = "干跑（confirm=0）：零写入；确认后加 confirm=1"
            return rep
        r = self._silent_pause_gate(bad)
        rep["paused"] = int((r or {}).get("paused") or 0)
        rep["failed"] = int((r or {}).get("failed") or 0)
        if rep["paused"] or rep["failed"]:
            self._log(f"魔流:静默闸:补暂停收敛 {rep['paused']} 个"
                      f"（违背不变量 {rep['violations']}，失败 {rep['failed']}）")
        return rep

    def _silent_hr_pending(self, snap: Optional[Dict[str, Any]] = None) -> Set[str]:
        """仍欠 H&R（没挂满）的「静默-新」hash：不许被超时降级成「普通」。"""
        out: Set[str] = set()
        try:
            data = self._tag_state().items() or {}
        except Exception:  # noqa: BLE001
            return out
        shots = snap if snap is not None else self._tag_all_torrents()
        # 推荐待确认的（状态 recommended/pending）也不许被超时降级：它们走推荐生命周期
        try:
            _rstore = getattr(self._store, "recommend", None)
            _rwait = _rstore.list("recommended") + _rstore.list("pending") if _rstore else []
            for _r in _rwait:
                _rh = str(_r.get("hash") or "").lower()
                if _rh:
                    out.add(_rh)
        except Exception:  # noqa: BLE001
            pass
        for h, rec in data.items():
            if str(rec.get("state") or "") != STATE_SILENT or str(rec.get("sub") or "") != SUB_NEW:
                continue
            t = (shots or {}).get(str(h).lower())
            if t is None:
                continue
            site = str(rec.get("site") or "").strip() or self._torrent_site_name(
                getattr(t, "tags", None), ""
            )
            try:
                done, _why = self._silent_hr_done(site, t)
            except Exception:  # noqa: BLE001
                done = True
            if not done:
                out.add(str(h).lower())
        return out

    def _silent_resume_tick(self, apply: bool = True, limit: int = 0) -> Dict[str, Any]:
        """★ **H&R 保挂**：只对**欠 H&R 的静默种**强制挂种（Master 2026-09-28 06:44：

        「你得拆出来啊，只有 h&r 要强制挂种」）——静默池必须"拆开"看：
        - **欠 H&R** 的种 → ``force_start`` 强制挂种（义务，不能被暂停/清掉）；
        - **其余**（静默-资源 / 静默-普通 / 静默-新 里不欠 H&R 的）→ **不强制**，保持原状，
          由站点魔力产出 / 资源价值决定去留（可被清理/换种，不受此 tick 干预）。
        """
        rep: Dict[str, Any] = {"apply": bool(apply), "checked": 0, "silent": 0, "hr_pending": 0,
                               "nonhr": 0, "resumed": 0, "skipped_manual": 0,
                               "skipped_incomplete": 0, "failed": 0, "items": [], "sites": []}
        # ★ 11.11.0：静默池全 paused（硬不变量，无 H&R 例外）。H&R 保挂已拆到 __hr_host__
        #   （hr_host() worker 负责）。本 tick 退役：不再对静默种 force_start。
        if SILENT_HR_SPLIT_ENABLED:
            rep["retired"] = True
            rep["reason"] = "静默池已全 paused；H&R 保挂由 __hr_host__（hr_host worker）承担，本 tick 退役"
            return rep
        snap = self._tag_all_torrents() or {}
        if not snap:
            rep["reason"] = "无快照"
            return rep
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        cap = int(limit or 0)
        to_resume: List[str] = []
        for hh, t in snap.items():
            tags = [str(x) for x in (getattr(t, "tags", None) or [])]
            rec = ledger.get(hh) or {}
            if str(rec.get("state") or "") != STATE_SILENT:
                continue  # ★ 账本判池内：在岗(刷流/魔力)/未知 → 不是静默池，跳过
            rep["silent"] = int(rep["silent"]) + 1
            if cap and rep["checked"] >= cap:
                continue
            rep["checked"] = int(rep["checked"]) + 1
            if rec.get("manual_paused"):
                rep["skipped_manual"] = int(rep["skipped_manual"]) + 1
                continue
            try:
                done = float(getattr(t, "progress", 0) or 0) >= 0.999
            except (TypeError, ValueError):
                done = False
            reuse = (MARK_REUSE in tags) or is_asset_tags(tags) or bool(rec.get("in_library"))
            if not done and not reuse:
                rep["skipped_incomplete"] = int(rep["skipped_incomplete"]) + 1
                continue
            st = str(getattr(t, "state", "") or "").strip().lower()
            if not (st.startswith("paused") or st.startswith("stopped") or st.startswith("queued")):
                continue  # 已在做种/校验 → 不动
            site = str(rec.get("site") or "").strip() or self._torrent_site_name(tags, "")
            try:
                obl = bool(self._hr_obligation(site, t)[0])
            except Exception:  # noqa: BLE001
                obl = False
            if not obl:
                rep["nonhr"] = int(rep["nonhr"]) + 1  # 非 H&R → 不强制，保持原状
                continue
            rep["hr_pending"] = int(rep["hr_pending"]) + 1
            rep["sites"][site] = int(rep["sites"].get(site) or 0) + 1
            if len(rep["items"]) < 40:
                rep["items"].append({"hash": hh[:12], "site": site, "state": st})
            to_resume.append(hh)
        if apply and to_resume:
            try:
                dl = self._get_downloader("qbittorrent")
                fn = getattr(dl, "force_start_torrents", None) if dl is not None else None
                if callable(fn):
                    cnt, err = fn(to_resume)
                elif dl is not None:
                    cnt, err = dl.resume_torrents(to_resume)
                else:
                    cnt, err = 0, "无下载器"
                rep["resumed"] = int(cnt or 0)
                if err:
                    self._log(f"H&R 保挂:强制挂种失败 {err}", "warning")
            except Exception as err:  # noqa: BLE001
                rep["failed"] = int(rep["failed"]) + 1
                self._log(f"H&R 保挂:强制挂种异常:{err}", "warning")
        if rep["resumed"]:
            self._log(f"魔流:H&R 保挂:强制挂种 {rep['resumed']} 个"
                      f"（静默 {rep['silent']} · 欠H&R {rep['hr_pending']} · 非H&R{rep['nonhr']}不动）")
        return rep

    def _silent_identity_ctx(self, snap: "Dict[str, Any] | None" = None) -> Dict[str, Any]:
        """★ 13.0.2：静默池「身份保护」的**唯一口径**（只读现成账本/资源组，不另存真值）。

        Master 2026-10-07 01:21「统一成身份就好」——取代过去「按 ``魔流-跨站`` / ``魔流-辅种``
        / ``已整理·辅种`` 标签各自硬豁免」的多套判据（那正是「各自保护各自」的分叉之源）。
        身份真值源（全部只读）：
          ① 跨站来源份 ← ``_crossseed_source_hashes()``（来源账本 active，已剔除义务已履行）
          ② 已认领     ← ``_claim_protected_hashes()``
          ③ 资源成员   ← ``asset_member_hashes(self._tag_groups())``（资源份本体 + 其副本）
          ④ 同数据副本 ← 「资产份（身份=资源 / 库记 ``in_library`` / 资源成员）」的
                          ``content_path`` 集合（``content_path`` 是唯一「同数据」口径）
        """
        snap = snap if snap is not None else (self._tag_all_torrents() or {})
        try:
            members = set(asset_member_hashes(self._tag_groups()) or set())
        except Exception:  # noqa: BLE001
            members = set()
        try:
            crossseed = set(self._crossseed_source_hashes() or set())
        except Exception:  # noqa: BLE001
            crossseed = set()
        try:
            claim = set(self._claim_protected_hashes() or set())
        except Exception:  # noqa: BLE001
            claim = set()
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        asset_keys: Set[str] = set()
        for _h, _t in (snap or {}).items():
            _hh = str(_h or "").strip().lower()
            if not (is_library_asset(ledger.get(_hh)) or _hh in members):
                continue
            _k = _data_key(_t)
            if _k:
                asset_keys.add(_k)
        return {"members": members, "crossseed": crossseed, "claim": claim,
                "asset_keys": asset_keys}

    def _silent_identity_protected(self, h: str, rec: Dict[str, Any], t: Any,
                                   ctx: Dict[str, Any]) -> str:
        """该种是否受**身份**保护 → 命中原因（``crossseed``/``claim``/``resource``/
        ``in_library``/``resource_copy``）；未命中 ``""``。

        ★ 跨站来源份 / 已认领**优先**：那是欠**他站**的 H&R 保种责任，跟自家资源评级无关，
        不受 ``asset_recheck=fail``（推荐复核不达标）影响；资产/副本类则尊重该 fail 标记
        （与 13.0.0 口径一致：不达标就不再享受资产保护）。
        """
        hh = str(h or "").strip().lower()
        if hh in (ctx.get("crossseed") or set()):
            return "crossseed"
        if hh in (ctx.get("claim") or set()):
            return "claim"
        if str((rec or {}).get("asset_recheck") or "") == "fail":
            return ""
        if hh in (ctx.get("members") or set()):
            return "resource"
        if is_library_asset(rec):
            return "in_library"
        _k = _data_key(t)
        if _k and _k in (ctx.get("asset_keys") or set()):
            return "resource_copy"
        return ""

    def _silent_drop_incomplete_now(self, h: str, rec: Any = None, t: Any = None,
                                    *, reason: str = "入池即删·未下完") -> bool:
        """★ 13.0.2：**入池即判** —— 「没下完」的种刚进静默池就删（Master 2026-10-07 01:30）。

        「没下完的新进入静默池的那一刻就应该被删除」—— 不必等 `silent_host`（默认 60min）那轮。

        放行（不删）四类，任一命中即不动：
          ① **身份保护**（跨站来源份 / 已认领 / 资源份 / 同数据副本）—— `_silent_identity_protected`；
          ② **欠 H&R**（保种义务，绝不删；判不准 → fail-closed 不删）；
          ③ **手动保护**（``manual_paused``）；
          ④ **同数据另有种**（辅种/复用副本在等校验：数据在本机，不是「真下载」）。
        删除走**单闸门** ``DownloaderAdapter.delete_torrents``（内含欠 H&R / 跨站来源 / 已认领 /
        手动保留硬拦 + 删除账单断言 + 熔断），并登记操作流水。
        """
        hh = str(h or "").strip().lower()
        if not hh:
            return False
        try:
            if t is None:
                t = (self._tag_all_torrents() or {}).get(hh)
            if t is None:
                return False
            if rec is None:
                rec = dict(self._tag_state().get(hh) or {})
            if str((rec or {}).get("state") or "") != STATE_SILENT:
                return False
            if (rec or {}).get("manual_paused"):
                return False
            try:
                prog = float(getattr(t, "progress", 1.0) or 0.0)
            except (TypeError, ValueError):
                prog = 1.0
            if prog >= 0.999:
                return False
            _ctx = self._silent_identity_ctx()
            if self._silent_identity_protected(hh, rec, t, _ctx):
                return False
            tags = [str(x) for x in (getattr(t, "tags", None) or [])]
            site = str((rec or {}).get("site") or "").strip() or self._torrent_site_name(tags, "")
            try:
                if self._hr_obligation(site, t)[0]:
                    return False
            except Exception:  # noqa: BLE001
                return False                     # fail-closed：判不准就不删
            # ④ 同数据另有种 → 是副本/等校验，不是「真下载」
            _key = _data_key(t)
            if _key:
                for _h2, _t2 in (self._tag_all_torrents() or {}).items():
                    if str(_h2 or "").strip().lower() != hh and _data_key(_t2) == _key:
                        return False
            dl = self._get_downloader(str((rec or {}).get("downloader") or "qbittorrent"))
            if dl is None:
                return False
            cnt, err = dl.delete_torrents(hashes=[hh], delete_file=True,
                                          reason=reason, source="silent.enter")
            if not cnt:
                if err:
                    self._log(f"入池即删:删除失败 {hh[:12]}:{err}", "warning")
                return False
            try:
                self._tag_state().drop(hh)
            except Exception:  # noqa: BLE001
                pass
            try:
                _sz = round(float(getattr(t, "size", 0) or 0) / 1073741824.0, 3)
            except (TypeError, ValueError):
                _sz = 0.0
            self._journal_deletions(
                {SILENT_HOST_TASK_ID: [OperationItem(
                    hash=hh, title=str(getattr(t, "title", "") or ""),
                    reason=f"{reason}({prog * 100:.1f}%)", size_gb=_sz, source="silent")]},
                log_prefix="静默池",
            )
            self._log(f"魔流:静默池:入池即删（未下完 {prog * 100:.1f}%）{hh[:12]}")
            return True
        except Exception as err:  # noqa: BLE001
            self._log(f"入池即删:异常 {hh[:12]}:{err}", "warning")
            return False

    def _silent_verify_marks(self, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 静默池「辅种/复用种」校验：停在 pausedDL 是**等校验**，不是没下完。

        （Master 2026-09-28：「所有跨站辅种都是 pausedDL吧」）
        对带 ``魔流-辅种`` / ``辅种`` / ``已整理`` 标记、且未到 100% 的静默种 → recheck + 恢复做种。
        校验完若文件对得上 → 自动 100% 继续做种；对不上 → 由后续流程按「坏辅种」处理（只删种）。
        """
        rep: Dict[str, Any] = {"apply": bool(apply), "pending": 0, "checked": 0,
                               "failed": 0, "items": []}
        try:
            data = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            return rep
        snap = self._tag_all_torrents() or {}
        cap = int(limit or 0)
        _ictx = self._silent_identity_ctx(snap)
        for h, rec in list(data.items()):
            hh = str(h or "").lower()
            if str(rec.get("state") or "") != STATE_SILENT:
                continue
            t = snap.get(hh)
            if t is None:
                continue
            # ★ 13.0.2：选种同「身份」口径（跨站来源份 / 资源份 / 同数据副本）—— 这类种停在
            #   pausedDL 是**等校验**，不是「没下完」（旧版按 `魔流-辅种`/`已整理·辅种` 标签判）
            if not self._silent_identity_protected(hh, rec, t, _ictx):
                continue
            try:
                prog = float(getattr(t, "progress", 1.0) or 0.0)
            except (TypeError, ValueError):
                prog = 1.0
            if prog >= 0.999:
                continue
            rep["pending"] += 1
            rep["items"].append({
                "hash": hh[:12], "title": str(getattr(t, "title", "") or "")[:50],
                "progress": round(prog * 100.0, 1), "state": str(getattr(t, "state", "") or ""),
                "tries": int(rec.get("verify_n") or 0),
            })
            if not apply or (cap and rep["checked"] >= cap):
                continue
            # ★ 别每小时反复 recheck 同一颗（磁盘 IO 浪费）：同一颗 6h 内只校验一次
            now = time.time()
            try:
                last = float(rec.get("verify_at") or 0.0)
            except (TypeError, ValueError):
                last = 0.0
            if now - last < 6 * 3600.0:
                rep["skipped"] = int(rep.get("skipped") or 0) + 1
                continue
            try:
                dl = self._get_downloader(str(rec.get("downloader") or "qbittorrent"))
                if dl is None:
                    rep["failed"] += 1
                    continue
                dl.recheck_torrents([hh])
                dl.resume_torrents([hh])
                rep["checked"] += 1
                _tries = int(rec.get("verify_n") or 0) + 1
                try:
                    self._tag_state().put(hh, {"verify_at": now, "verify_n": _tries})
                except Exception:  # noqa: BLE001
                    pass
                if _tries >= 3:
                    rep["stuck"] = int(rep.get("stuck") or 0) + 1
            except Exception as err:  # noqa: BLE001
                rep["failed"] += 1
                self._log(f"静默池校验:辅种 recheck 失败 {hh[:12]}:{err}", "warning")
        if apply and rep["checked"]:
            self._log(
                f"魔流:静默池校验:辅种复用种 recheck {rep['checked']} 个"
                f"（停在 pausedDL 是等校验，不是没下完）"
            )
        if apply and rep.get("stuck"):
            self._log(
                f"静默池校验:{rep['stuck']} 个辅种反复校验仍不完整（疑似文件已移走/坏种），"
                f"已不自动删——请人工确认", "warning"
            )
        return rep

    def _silent_purge_incomplete(self, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 静默池「未下完」清理：没下完的直接删，**不计 H&R**（Master 2026-09-28 00:16）。

        - 只扫静默池**「没下完」**的种（不分身份；「资源/来源/副本」等由身份保护挡住）（★ 13.0.2）
        - 排除：跨站来源份（``魔流-跨站``：数据已下、正在校验）、推荐待确认（``魔流-推荐``）、
          库内资产（已整理/辅种）—— 这些都不是「没下完的半成品」
        - 删文件策略：同目录还有别的**已完成**种子在用 → 只删种子；否则连文件一起删
        """
        rep: Dict[str, Any] = {"apply": bool(apply), "pending": 0, "deleted": 0,
                               "torrent_only": 0, "failed": 0, "items": []}
        _by_task: Dict[str, List[Any]] = {}
        try:
            store = self._tag_state()
            data = dict(store.items() or {})
        except Exception:  # noqa: BLE001
            return rep
        snap = self._tag_all_torrents() or {}
        cap = int(limit or 0)
        _ictx = self._silent_identity_ctx(snap)
        # ★ 同「Release 目录」保护：另一个**已完成**种子占着同一个
        #   `save_path/name`（典型：跨站辅种同一发布）→ 只删种子、不删文件。
        #   注意 qB 的 save_path 是**根目录**（几百个种共用），不能拿它当判据。
        def _rkey(_t: Any) -> str:
            return _data_key(_t)

        done_keys: Dict[str, Set[str]] = {}
        for _h, _t in (snap or {}).items():
            try:
                if float(getattr(_t, "progress", 0) or 0) >= 0.999:
                    _k = _rkey(_t)
                    if _k:
                        done_keys.setdefault(_k, set()).add(str(_h).lower())
            except Exception:  # noqa: BLE001
                continue
        for h, rec in list(data.items()):
            h = str(h or "").lower()
            if str(rec.get("state") or "") != STATE_SILENT:
                continue
            t = snap.get(h)
            if t is None:
                continue
            tags = [str(x) for x in (getattr(t, "tags", None) or [])]
            # ★ 13.0.2：保护 = **身份**（跨站来源份 / 已认领 / 资源份 / 同数据副本，
            #   它们停在 pausedDL 是等校验，不是「没下完」）+ 推荐在途
            #   （旧版按 `魔流-跨站`/`魔流-辅种`/`已整理·辅种` 标签判 → 已删标签判据）
            if "魔流-推荐" in tags or self._silent_identity_protected(h, rec, t, _ictx):
                continue
            try:
                prog = float(getattr(t, "progress", 1.0) or 0.0)
            except Exception:  # noqa: BLE001
                prog = 1.0
            state_name = str(getattr(t, "state", "") or "")
            if not (prog < 0.999 or state_name.endswith("DL")):
                continue
            rep["pending"] += 1
            rep["items"].append({"hash": h[:12], "title": str(getattr(t, "title", "") or "")[:60],
                                 "progress": round(prog * 100.0, 1), "state": state_name})
            if not apply or (cap and rep["deleted"] >= cap):
                continue
            _k = _rkey(t)
            shared = _shared_key_hits(_k, done_keys, h)
            try:
                dl = self._get_downloader(str(rec.get("downloader") or "qbittorrent"))
                if dl is None:
                    rep["failed"] += 1
                    continue
                cnt, err = dl.delete_torrents(hashes=[h], delete_file=not shared)
                if cnt:
                    rep["deleted"] += 1
                    if shared:
                        rep["torrent_only"] += 1
                    try:
                        _sz = float(getattr(t, "size", 0) or 0) / 1073741824.0
                    except (TypeError, ValueError):
                        _sz = 0.0
                    _by_task.setdefault(
                        str(rec.get("taken_by") or SILENT_HOST_TASK_ID), []
                    ).append(OperationItem(
                        hash=h,
                        title=str(getattr(t, "title", "") or ""),
                        reason=(f"静默池未下完({state_name} {prog * 100:.1f}%)"
                                + ("·同目录另有完成种，仅删种保留文件" if shared else "")),
                        size_gb=round(_sz, 3),
                        source="silent",
                    ))
                    try:
                        store.drop(h)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    rep["failed"] += 1
                    self._log(f"静默池清理:删除失败 {h[:12]}:{err}", "warning")
            except Exception as err:  # noqa: BLE001
                rep["failed"] += 1
                self._log(f"静默池清理:删除异常 {h[:12]}:{err}", "warning")
        self._journal_deletions(_by_task, log_prefix="静默池清理")
        if apply and rep["deleted"]:
            self._log(
                f"魔流:静默池清理:未下完直接删 {rep['deleted']} 个（不计 H&R；"
                f"其中只删种 {rep['torrent_only']} 个）"
            )
        return rep

    def _recommend_downgrade_expired(self, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 推荐「过期 → 转普通」，覆盖**静默池**里的推荐记录。

        （任务范围那条路在 ``recommend_scan`` 里；静默池的推荐没有活跃任务归属，
        以前既不过期也不清理 → 这里补上。Master 01:17：推荐过期**不删，转普通**。）
        """
        rep: Dict[str, Any] = {"apply": bool(apply), "scanned": 0, "downgraded": 0,
                               "not_yet": 0, "items": []}
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            rep["reason"] = "推荐库不可用"
            return rep
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        try:
            expire_sec = float(cfg.get("expire_days", 7.0) or 0) * 86400.0
        except (TypeError, ValueError):
            expire_sec = 7 * 86400.0
        if expire_sec <= 0:
            rep["reason"] = "未设过期"
            return rep
        dl = None
        try:
            all_items = dict(store.all() or {})
        except Exception:  # noqa: BLE001
            return rep
        now = time.time()
        cap = int(limit or 0)
        for h, rec in list(all_items.items()):
            if str(rec.get("status") or "") not in ("recommended", "pending"):
                continue
            try:
                first = float(rec.get("first_seen") or rec.get("evaluated_at") or 0) or now
            except (TypeError, ValueError):
                first = now
            if now - first <= expire_sec:
                rep["not_yet"] = int(rep.get("not_yet") or 0) + 1
                continue
            rep["scanned"] = int(rep.get("scanned") or 0) + 1
            members = [str(x or "").lower() for x in (rec.get("members") or [])] or [str(h).lower()]
            rep["items"].append({"hash": str(h)[:12], "title": str(rec.get("title") or "")[:50],
                                 "members": len(members)})
            if not apply or (cap and rep["downgraded"] >= cap):
                continue
            if dl is None:
                try:
                    dl = self._get_downloader("qbittorrent")
                except Exception:  # noqa: BLE001
                    dl = None
            for m in members:
                try:
                    self._recommend_downgrade_one(dl, m)
                except Exception as err:  # noqa: BLE001
                    self._log(f"推荐过期降级失败 {m[:12]}:{err}", "warning")
            try:
                store.set_status(str(h), "downgraded", note="过期→转普通", downgraded_at=now)
            except Exception:  # noqa: BLE001
                pass
            rep["downgraded"] = int(rep.get("downgraded") or 0) + 1
        return rep

    def _recommend_downgrade_one(self, downloader: Any, h: str) -> bool:
        """推荐「过期 → 转普通」（Master 01:17）：

        - 静默池成员（``静默-新``）→ 降级成 ``静默-普通``（会摘掉「魔流-推荐」）
        - 其它（任务名下的种）→ **只摘掉「魔流-推荐」标签**，其余标签/归属不动
        """
        hh = str(h or "").strip().lower()
        if not hh:
            return False
        try:
            rec = self._tag_state().get(hh) or {}
        except Exception:  # noqa: BLE001
            rec = {}
        if (str(rec.get("state") or "") == STATE_SILENT
                and str(rec.get("sub") or "") == SUB_NEW):
            return self._silent_to_plain(hh)
        try:
            t = (self._tag_all_torrents() or {}).get(hh)
            cur = [str(x).strip() for x in (getattr(t, "tags", None) or [])] if t is not None else []
            if cur and "魔流-推荐" in cur:
                new_tags = [x for x in cur if x != "魔流-推荐"]
                fn = getattr(downloader, "replace_torrent_tags", None)
                if callable(fn):
                    return bool(fn(hh, new_tags))
        except Exception as err:  # noqa: BLE001
            self._log(f"推荐降级:摘标签失败 {hh[:12]}:{err}", "warning")
        return False

    def _qb_num_complete(self) -> Dict[str, int]:
        """qB 真实做种人数（``num_complete``）→ ``{hash: n}``。

        ★ 魔力公式里的 Ni 用**做种人数**；站点页面上的 seeders 是抓来的快照，
        用 qB 的实时值更准（Master 2026-09-27 提过）。
        """
        out: Dict[str, int] = {}
        try:
            dl = self._get_downloader("qbittorrent")
            qbc = getattr(dl, "_qb_client", lambda: None)() if dl is not None else None
            if qbc is None:
                return out
            for x in (qbc.torrents_info() or []):
                try:
                    _h = str(x.get("hash") or "").lower()
                except Exception:  # noqa: BLE001
                    _h = ""
                if _h:
                    try:
                        out[_h] = int(x.get("num_complete") or 0)
                    except (TypeError, ValueError):
                        out[_h] = 0
        except Exception as err:  # noqa: BLE001
            self._log(f"魔力考核:读取 qB num_complete 失败:{err}", "warning")
        return out

    def _magic_out_per_hour(self, t: Any, ni: int = 0) -> float:
        """单个种子的每小时魔力产出（估计）。Ni 优先取 qB ``num_complete``。"""
        try:
            sz = float(getattr(t, "size_gb", 0) or 0)
        except (TypeError, ValueError):
            sz = 0.0
        try:
            _ni = int(ni or 0)
        except (TypeError, ValueError):
            _ni = 0
        if _ni <= 0:
            try:
                _ni = int(getattr(t, "seeder", 0) or 0)
            except (TypeError, ValueError):
                _ni = 0
        age_w = 0.0
        try:
            _added = float(getattr(t, "added_on", 0) or 0)
            if _added > 0:
                age_w = max(0.0, (time.time() - _added) / (7.0 * 86400.0))
        except (TypeError, ValueError):
            age_w = 0.0
        try:
            return float(calc_bonus_per_hour(
                size_gb=sz, seeders=max(_ni, 1), age_weeks=age_w,
                is_zero_bonus=bool(getattr(t, "is_zero_bonus", False)),
            ))
        except Exception:  # noqa: BLE001
            return 0.0

    def _site_magic_enough(self, site: str) -> Tuple[bool, str]:
        """该站「魔力产出够了」吗？= 有配了目标的 bonus 任务且**目标已达成**。

        没配目标 → **视为没够**（不清理）。
        """
        s = str(site or "").strip()
        if not s:
            return False, "无站点"
        try:
            tasks = list(self._task_configs.values())
        except Exception:  # noqa: BLE001
            return False, "任务不可读"
        for t in tasks:
            try:
                if str(getattr(t, "task_type", "bonus") or "bonus").lower() != "bonus":
                    continue
                if not getattr(t, "goal_value", None):
                    continue
                if str(getattr(t, "site_name", "") or "").strip() != s:
                    continue
                st = self._task_goal_status(t) or {}
                if st.get("goal_reached"):
                    return True, f"{getattr(t, 'title', '')} 目标已达成"
            except Exception:  # noqa: BLE001
                continue
        return False, "未达标/未设目标"

    def _site_domain_by_name(self, name: str) -> str:
        """站点短名/全名 → 域名（带 300s 缓存）。

        ★ 规则库（``sites/rules.py``）的键是**域名**，而标签/账本里存的是**中文短名**
        （如「红豆饭」「学校」）—— 不转换就会出现「所有站点都按未知保守 24h」的假象。
        """
        nm = str(name or "").strip()
        if not nm:
            return ""
        if "." in nm and " " not in nm:
            return nm.lower()
        cache = getattr(self, "_site_name2dom", None)
        if not isinstance(cache, dict):
            cache = {}
            self._site_name2dom = cache
        now = time.time()
        ts = float(getattr(self, "_site_name2dom_at", 0) or 0)
        if not cache or (now - ts) > 300:
            # ★ ① 规则库自带「中文站名 ↔ 域名」映射（最准，优先）
            try:
                for _dom, _rec in (self._site_rules().items() or {}).items():
                    # ★ 7.21.1：规则库里站点名是 `name`（不是 `site_name`）——读错字段
                    #   会让本缓存恒为空，只能靠 MP 站点表兜底；一旦 MP 名称大小写/别名
                    #   不一致（如 CARPT/CarPT），H&R 解析就会失准。
                    _n = str((_rec or {}).get("name") or (_rec or {}).get("site_name") or "").strip()
                    _d = str(_dom or "").strip().lower()
                    if _n and _d:
                        cache.setdefault(_n, _d)
            except Exception as err:  # noqa: BLE001
                self._log(f"H&R:规则库站名映射失败:{err}", "warning")
            # ② MoviePilot 站点表兜底（同名的**不覆盖**规则库结果）
            try:
                for it in self._list_sites() or []:
                    _n = str((it or {}).get("name") or "").strip()
                    _d = str((it or {}).get("domain") or "").strip().lower()
                    if _n and not cache.get(_n):
                        cache[_n] = _d or _n.lower()
            except Exception as err:  # noqa: BLE001
                self._log(f"H&R:站点名解析失败:{err}", "warning")
            self._site_name2dom_at = now
        return str(cache.get(nm) or "").lower()

    def _silent_plain_sweep(self, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 静默-普通 清理：**考核魔力产出**，站点魔力够了就把「没用的」直接删。

        Master 2026-09-28 01:17：「推荐不过过期转普通 普通考核魔力产出没用，
        在魔力产出够的情况下普通的直接干」

        - 「够」= 该站有配目标的 bonus 任务且**目标已达成**（没配 → 不清理）
        - 「没用」= 本种每小时魔力产出 ≤ 池内中位数 × ratio（默认 0.5）
        - ★ 7.21.0：**水位驱动 · 清到目标线**（Master 08:33「一直清到 75% 才合格」）
          - 触发：池用量 ≥ watermark（默认 85%，不再仅 80%）
          - 目标：池用量 ≤ target_pct（默认 75%）。未到目标水位则**跨过「低效门槛」**
            继续清「中产出」，但**留高产**（默认产出于中位×max_ratio 以上）。
        - 永不删：库内资产 / 推荐中 / 跨站来源份 / 辅种复用种 / 欠 H&R / 手动保护
        - 删文件按「Release 目录」共用判断（同 3.14.1）：有别的已完成种子在用 → 只删种子
        """
        rep: Dict[str, Any] = {"apply": bool(apply), "pending": 0, "deleted": 0,
                               "torrent_only": 0, "failed": 0, "sites": {},
                               "skipped_site": 0, "items": []}
        _by_task: Dict[str, List[Any]] = {}
        cfg = getattr(self, "_silent_cfg", {}) or {}
        if not cfg.get("sweep", True):
            rep["reason"] = "未启用"
            return rep
        try:
            ratio = float(cfg.get("ratio", 0.5) or 0.5)
        except (TypeError, ValueError):
            ratio = 0.5
        _dp_on = bool(cfg.get("disk_pressure", True))
        try:
            _wm = float(cfg.get("watermark", 0.85) or 0.85)
        except (TypeError, ValueError):
            _wm = 0.85
        # ★ 7.21.0：目标水位（清到这个水位才算合格）；默认 0.75（Master 08:33）
        try:
            _target_pct = float(cfg.get("target_pct", 0.75) or 0.75)
        except (TypeError, ValueError):
            _target_pct = 0.75
        try:
            _max_ratio = float(cfg.get("max_ratio", 2.0) or 2.0)
        except (TypeError, ValueError):
            _max_ratio = 2.0
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            return rep
        snap = self._tag_all_torrents() or {}
        ni_map = self._qb_num_complete()
        # ★ 7.20.0 磁盘压力：该种所在池用量（读不到给 0）
        try:
            _pool_dirs = self._pool_dirs()
        except Exception:  # noqa: BLE001
            _pool_dirs = []

        def _pool_pct_of(_t: Any) -> float:
            try:
                _sp = str(getattr(_t, "save_path", "") or "")
                _nm2, _ct = self._match_pool(_sp, _pool_dirs)
                _u = self._usage(_ct) if _ct else {}
                return float(_u.get("pct") or 0.0)
            except Exception:  # noqa: BLE001
                return 0.0

        def _rkey(_t: Any) -> str:
            return _data_key(_t)

        done_keys: Dict[str, Set[str]] = {}
        for _h, _t in (snap or {}).items():
            try:
                if float(getattr(_t, "progress", 0) or 0) >= 0.999:
                    _k = _rkey(_t)
                    if _k:
                        done_keys.setdefault(_k, set()).add(str(_h).lower())
            except Exception:  # noqa: BLE001
                continue
        # ★ 13.0.2：身份保护统一口径（资源成员 / 库记 / 同数据副本 / 跨站来源 / 已认领）
        _ictx = self._silent_identity_ctx(snap)

        by_site: Dict[str, List[Tuple[str, Any, float, Dict[str, Any]]]] = {}
        protected = 0
        _pwhy = {"resource": 0, "resource_copy": 0, "in_library": 0, "crossseed": 0,
                 "claim": 0, "recommend": 0, "hr": 0}
        for h, rec in list(ledger.items()):
            hh = str(h or "").lower()
            if (str(rec.get("state") or "") != STATE_SILENT
                    or str(rec.get("sub") or "") != SUB_PLAIN):
                continue
            t = snap.get(hh)
            if t is None:
                continue
            tags = [str(x) for x in (getattr(t, "tags", None) or [])]
            # ★ 13.0.2：保护 = **身份**（跨站来源份 / 已认领 / 资源份 / 同数据副本）+ 推荐在途；
            #   **不再按标签**（`魔流-跨站`/`魔流-辅种`/`已整理·辅种`）各自硬豁免
            #   （Master 2026-10-07 01:21「统一成身份就好」）。
            _iw = self._silent_identity_protected(hh, rec, t, _ictx)
            if _iw:
                protected += 1
                _pwhy[_iw] = int(_pwhy.get(_iw) or 0) + 1
                continue
            if "魔流-推荐" in tags:
                protected += 1
                _pwhy["recommend"] = int(_pwhy.get("recommend") or 0) + 1
                continue
            site = str(rec.get("site") or "").strip() or self._torrent_site_name(tags, "")
            done_hr, _why = self._silent_hr_done(site, t)
            if not done_hr:
                protected += 1
                _pwhy["hr"] = int(_pwhy.get("hr") or 0) + 1
                try:
                    _seeded_h = round(seed_hours_for_hr(t), 1)
                except Exception:  # noqa: BLE001
                    _seeded_h = 0.0
                try:
                    _hsrc = str(self._crossseed_hr_decision(str(site or "").strip(), None)[2] or "")
                except Exception:  # noqa: BLE001
                    _hsrc = ""
                rep.setdefault("protected_hr", []).append({
                    "hash": hh, "site": site,
                    "title": str(getattr(t, "title", "") or "")[:64],
                    "seeded_h": _seeded_h, "why": str(_why or ""),
                    "hr_src": _hsrc,
                })
                continue
            by_site.setdefault(site or "-", []).append(
                (hh, t, self._magic_out_per_hour(t, int(ni_map.get(hh, 0) or 0)), rec)
            )
        rep["protected"] = protected
        rep["protected_why"] = _pwhy
        cap = int(limit or 0)
        for site, rows in by_site.items():
            enough, why = self._site_magic_enough(site)
            outs = sorted(x[2] for x in rows)
            med = outs[len(outs) // 2] if outs else 0.0
            # ★ 7.20.0 磁盘压力：该站种子所在池用量 ≥ 水位 → 也触发清理（不再等魔力达标）
            _dp = _pool_pct_of(rows[0][1]) if (_dp_on and rows) else 0.0
            _dp_fire = bool(_dp_on and _dp >= _wm * 100)
            rep["sites"][str(site)] = {
                "members": len(rows), "enough": bool(enough), "why": why,
                "disk_pct": round(_dp, 1), "disk_fire": bool(_dp_fire),
                "median_per_hour": round(med, 2),
                "total_per_hour": round(sum(outs), 2),
            }
            if not enough and not _dp_fire:
                rep["skipped_site"] = int(rep.get("skipped_site") or 0) + 1
                continue
            if _dp_fire and not enough:
                why = f"磁盘压力 {_dp:.1f}%≥{_wm * 100:.0f}%"
            rep["sites"][str(site)].update({
                "target_pct": round(_target_pct * 100, 1),
                "watermark_pct": round(_wm * 100, 1),
            })
            thr = med * ratio
            for hh, t, out_h, rec in sorted(rows, key=lambda x: x[2]):
                # ★ 7.21.0 水位驱动：先看池用量是否已到目标线
                try:
                    _cur_pct = _pool_pct_of(t)
                except Exception:  # noqa: BLE001
                    _cur_pct = _dp
                if _cur_pct <= _target_pct * 100:
                    rep.setdefault("target_reached", 0)
                    rep["target_reached"] = int(rep["target_reached"]) + 1
                    break
                # 极高产护住（中位 × max_ratio 默认 ×2）；低于这个阈都清
                if out_h > med * _max_ratio:
                    rep.setdefault("kept_high", 0)
                    rep["kept_high"] = int(rep["kept_high"]) + 1
                    break
                rep["pending"] += 1
                rep["items"].append({
                    "hash": hh[:12], "site": site, "title": str(getattr(t, "title", "") or "")[:50],
                    "per_hour": round(out_h, 2), "median": round(med, 2),
                })
                if not apply or (cap and rep["deleted"] >= cap):
                    continue
                _k = _rkey(t)
                shared = _shared_key_hits(_k, done_keys, hh)
                try:
                    dl = self._get_downloader(str(rec.get("downloader") or "qbittorrent"))
                    if dl is None:
                        rep["failed"] = int(rep["failed"]) + 1
                        continue
                    cnt, err = dl.delete_torrents(hashes=[hh], delete_file=not shared)
                    if cnt:
                        rep["deleted"] = int(rep["deleted"]) + 1
                        if shared:
                            rep["torrent_only"] = int(rep["torrent_only"]) + 1
                        try:
                            _sz = float(getattr(t, "size", 0) or 0) / 1073741824.0
                        except (TypeError, ValueError):
                            _sz = 0.0
                        _by_task.setdefault(
                            str(rec.get("taken_by") or SILENT_HOST_TASK_ID), []
                        ).append(OperationItem(
                            hash=hh,
                            title=str(getattr(t, "title", "") or ""),
                            reason=(f"静默-普通低效[{site}]：{why}，"
                                    f"时魔 {out_h:.2f} ≤ 中位数 {med:.2f}×{ratio:g}"
                                    + ("·同目录另有完成种，仅删种" if shared else "")),
                            size_gb=round(_sz, 3),
                            source="silent",
                        ))
                        try:
                            self._tag_state().drop(hh)
                        except Exception:  # noqa: BLE001
                            pass
                        # ★ 跨站来源份：既然删了种，来源份账本也一起收口（不留悬挂记录）
                        try:
                            if hh in (self._crossseed_sources().items() or {}):
                                self._crossseed_sources().drop(hh)
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        rep["failed"] = int(rep["failed"]) + 1
                        self._log(f"静默普通清理:删除失败 {hh[:12]}:{err}", "warning")
                except Exception as err:  # noqa: BLE001
                    rep["failed"] = int(rep["failed"]) + 1
                    self._log(f"静默普通清理:删除异常 {hh[:12]}:{err}", "warning")
        self._journal_deletions(_by_task, log_prefix="静默普通清理")
        if apply and rep["deleted"]:
            self._log(
                f"魔流:静默普通清理:删掉 {rep['deleted']} 个低效普通种（魔力达标/磁盘压力）"
                f"（只删种 {rep['torrent_only']} 个；共查 {len(by_site)} 站）"
            )
        return rep

    def _silent_triage(self, apply: bool = False, limit: int = 0, budget: float = 900.0) -> Dict[str, Any]:
        """★ 静默池分拣（**以「资源」为单位**，不是以「种」为单位）。

        Master 2026-09-28：「推荐推的是资源，不是种」→
        - 同一资源（文件特征码/文件组）下的静默成员**一起判定、一起打标**：
          达标 → 全部成员都打 ``魔流-推荐``（入库后由库记统一转 ``静默-资源``）；
          不达标 → 全部成员一起转 ``静默-普通``；
        - ★ 资源身份 = **资源组库记** ``library.in_library``（不是种上的 ``已整理/辅种`` 标签）
          + 推荐过（Master 2026-09-28 14:47；13.0.2 起口径统一为「身份」）：
          - 库内 + 推荐过 → ``静默-资源``（资产永不删）
          - 库内但推荐没过 → ``静默-普通``（即使已入库，没过推荐也不算合格资源）
        - 该资源**已有推荐记录**（推荐中/待确认/已确认）→ 整组不重复甄别、不重复通知；
        - 资源内**代表种**（优先已完成、其次体积大）欠 H&R → 整组原地挂种等待。
        """
        tag_state = self._tag_state()
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        rec_tag = str(cfg.get("tag") or "魔流-推荐")
        rstore = getattr(self._store, "recommend", None)
        try:
            files = self._tag_groups()
        except Exception:  # noqa: BLE001
            files = None
        snap = self._tag_all_torrents()
        # ★ 豆瓣评分源：本轮预算（防风控，超了就回退 TMDB）。3.24.3 加上，原逻辑 step 5 evaluate
        # 一直没设预算,现在闸门也要 evaluate,一并补上。
        try:
            self._get_recommend_engine().begin_round(int(cfg.get("douban_max_per_run") or 0))
        except Exception:  # noqa: BLE001
            pass
        # ---- 1) 候选（静默-新）按「资源」归组（没有文件组 → 单种成组）
        buckets: Dict[str, List[Tuple[str, Dict[str, Any], Any]]] = {}
        for h, rec in list((tag_state.items() or {}).items()):
            if str(rec.get("state") or "") != STATE_SILENT or str(rec.get("sub") or "") != SUB_NEW:
                continue
            hh = str(h or "").lower()
            t = (snap or {}).get(hh)
            if t is None:
                continue  # 已不在下载器 → 交给对账
            gid = ""
            try:
                gid = files.group_of(hh) if files is not None else ""
            except Exception:  # noqa: BLE001
                gid = ""
            # ★ §1 点播（权威来源 1）：手动指定的资源**直接=资源**，不观察、不分拣
            try:
                if self._ondemand_is_pending(hh):
                    if files is not None and gid:
                        files.set_identity(gid, SUB_RESOURCE, by="ondemand")
                    self._ondemand_unmark(hh)
                    rep["ondemand"] = int(rep.get("ondemand") or 0) + 1
                    continue
            except Exception:  # noqa: BLE001
                pass
            buckets.setdefault(str(gid) or ("h:" + hh), []).append((hh, rec, t))

        def _pick(items: List[Tuple[str, Dict[str, Any], Any]]) -> Tuple[str, Dict[str, Any], Any]:
            """代表种：优先「已完成」，其次体积大（导入要用它）。"""

            def _k(x: Tuple[str, Dict[str, Any], Any]) -> Tuple[int, float]:
                _t = x[2]
                try:
                    _done = 1 if float(getattr(_t, "progress", 0) or 0) >= 0.999 else 0
                except (TypeError, ValueError):
                    _done = 0
                try:
                    _sz = float(getattr(_t, "size_gb", 0) or 0)
                except (TypeError, ValueError):
                    _sz = 0.0
                return (_done, _sz)

            return sorted(items, key=_k, reverse=True)[0]

        cap = int(limit or 0) or max(int(RECOMMEND_SCAN_MAX), 1)
        rep: Dict[str, Any] = {
            "apply": bool(apply), "pending": len(buckets),
            "torrents": sum(len(v) for v in buckets.values()),
            "scanned": 0, "waiting_hr": 0, "promoted": 0, "plain": 0,
            "recognized": 0, "limited": False, "evaluated": 0, "kept": 0,
            "asset": 0, "items": [],
        }
        _deadline = time.time() + float(budget or 0)
        _used = 0
        for gid, members in buckets.items():
            if budget and time.time() > _deadline:
                rep["limited"] = True
                break
            if cap and _used >= cap:
                break
            rep["scanned"] += 1
            h_list = [x[0] for x in members]
            r_h, r_rec, r_t = _pick(members)
            # ---- 2) 资源身份 = 资源组库记 in_library + 推荐过（Master 2026-09-28 14:47）。
            # 库内 + 推荐过 → 静默-资源；库内但推荐没过 → 静默-普通。
            in_lib = False
            if files is not None and not str(gid).startswith("h:"):
                try:
                    in_lib = bool((files.items().get(gid) or {}).get("library", {}).get("in_library"))
                except Exception:  # noqa: BLE001
                    in_lib = False
            if in_lib:
                _rcf = False
                try:
                    _st0 = self._tag_state()
                    for _h0 in h_list:
                        if str((_st0.get(_h0) or {}).get("asset_recheck") or "") == "fail":
                            _rcf = True
                            break
                except Exception:  # noqa: BLE001
                    _rcf = False
                if _rcf:
                    rep["recheck_fail"] = int(rep.get("recheck_fail") or 0) + 1
                    continue
                # ★ 补闸门：库内 + 推荐过 = 资源。仅库记不够，必须过推荐（Master 2026-09-28 14:47）。
                _in_lib_like: Dict[str, Any] = {"recognized": False}
                _in_lib_title: str = str(getattr(r_t, "title", "") or "")
                if _in_lib_title:
                    try:
                        _in_lib_like = self._get_recommend_engine().evaluate(_in_lib_title, with_poster=False)
                    except Exception:  # noqa: BLE001
                        _in_lib_like = {"recognized": False}
                _in_lib_worth = bool(self._recommend_worth(_in_lib_like, cfg))
                if _in_lib_worth:
                    rep["asset"] = int(rep.get("asset") or 0) + 1
                    if apply:
                        for _h, _r, _t in members:
                            try:
                                self._silent_to_resource(_h)
                            except Exception as err:  # noqa: BLE001
                                self._log(f"静默分拣:归资源失败 {_h[:12]}:{err}", "warning")
                    continue
                # 库内但推荐没过 → 普通（不算合格资源）。
                rep["plain"] = int(rep.get("plain") or 0) + 1
                if apply:
                    for _h, _r, _t in members:
                        try:
                            self._silent_to_plain(_h)
                        except Exception as err:  # noqa: BLE001
                            self._log(f"静默分拣:库内但推荐不过→归普通失败 {_h[:12]}:{err}", "warning")
                    try:
                        rep["items"].append({
                            "hash": r_h[:12], "title": _in_lib_title,
                            "verdict": "普通(库内但推荐不过)",
                            "rating": _in_lib_like.get("rating"), "members": len(members),
                        })
                    except Exception:  # noqa: BLE001
                        pass
                continue
            # ---- 3) 该资源已有推荐记录 → 整组不重复
            _dup = self._recommend_dup_group(rstore, gid, h_list)
            if _dup:
                rep["kept"] = int(rep.get("kept") or 0) + 1
                continue
            # ---- 4) H&R 门槛（看代表种）
            site = str(r_rec.get("site") or "").strip() or self._torrent_site_name(
                getattr(r_t, "tags", None), ""
            )
            done, _why = self._silent_hr_done(site, r_t)
            if not done:
                rep["waiting_hr"] += 1
                continue
            _used += 1
            # ---- 5) 识别 + 评分（每个**资源**只评一次）
            title = str(getattr(r_t, "title", "") or "")
            like: Dict[str, Any] = {"recognized": False}
            media: Optional[Dict[str, Any]] = None
            if title:
                try:
                    like = self._get_recommend_engine().evaluate(title, with_poster=False)
                except Exception:  # noqa: BLE001
                    like = {"recognized": False}
                if like.get("media_id"):
                    media = {
                        "source": like.get("media_source"), "id": like.get("media_id"),
                        "type": like.get("type"), "year": like.get("year"),
                        # ★ 必须带「资源名」（Master 2026-09-28 07:08：列表要显示资源名，不是种子名）
                        "title": like.get("title") or like.get("name") or "",
                    }
            _mkey = self._recommend_media_key(media, like)
            if like.get("recognized"):
                rep["recognized"] += 1
            worth = bool(self._recommend_worth(like, cfg)) and not self._recommend_dup(
                rstore, _mkey, r_h, ("recommended", "confirmed")
            )
            _sz = sum(float(getattr(x[2], "size_gb", 0) or 0) for x in members)
            if worth:
                rep["promoted"] += 1
                rep["items"].append({"hash": r_h[:12], "title": title, "verdict": "推荐",
                                     "rating": like.get("rating"), "members": len(members)})
                if apply and rstore is not None:
                    now = time.time()
                    try:
                        rstore.upsert(
                            r_h, status="recommended", title=title, size_gb=_sz,
                            media=media, media_key=_mkey, rating=like.get("rating"),
                            in_chart=bool(like.get("in_chart")),
                            in_subscribe=bool(like.get("in_subscribe")),
                            group_id=("" if str(gid).startswith("h:") else str(gid)),
                            members=h_list,
                            source="silent_triage", first_seen=now, evaluated_at=now,
                            reason=("评分 %.1f" % float(like.get("rating") or 0))
                            + ("·在榜" if like.get("in_chart") else "")
                            + ("·订阅" if like.get("in_subscribe") else ""),
                        )
                    except Exception as err:  # noqa: BLE001
                        self._log(f"静默分拣:推荐建档失败 {r_h[:12]}:{err}", "warning")
                    # ★ 资源级打标：**整组静默成员**都打「魔流-推荐」
                    try:
                        dl = self._get_downloader(str(r_rec.get("downloader") or "qbittorrent"))
                        if dl is not None:
                            for _h, _r, _t in members:
                                try:
                                    self._recommend_tag(dl, f"silent:{site}", rec_tag, _h)
                                except Exception as err:  # noqa: BLE001
                                    self._log(f"静默分拣:推荐打标失败 {_h[:12]}:{err}", "warning")
                    except Exception as err:  # noqa: BLE001
                        self._log(f"静默分拣:推荐打标失败 {r_h[:12]}:{err}", "warning")
            else:
                rep["plain"] += 1
                rep["items"].append({"hash": r_h[:12], "title": title, "verdict": "普通",
                                     "rating": like.get("rating"), "members": len(members)})
                if apply:
                    for _h, _r, _t in members:
                        try:
                            self._silent_to_plain(_h)
                        except Exception as err:  # noqa: BLE001
                            self._log(f"静默分拣:归普通失败 {_h[:12]}:{err}", "warning")
        rep["evaluated"] = _used
        if apply and (rep["promoted"] or rep["plain"] or rep["asset"]):
            self._log(
                f"魔流:静默池分拣(按资源):{rep['scanned']} 组/{rep['torrents']} 种"
                f"（欠H&R {rep['waiting_hr']} 组，已推荐 {rep['kept']} 组）"
                f"→ 推荐 {rep['promoted']} 组 · 普通 {rep['plain']} 组 · 资源 {rep['asset']} 组"
            )
        if apply and rep["promoted"]:
            self._silent_promote_notify(rep)
        return rep

    def _silent_promote_notify(self, report: Dict[str, Any]) -> None:
        """静默池分拣出的推荐：一轮一条汇总通知（避免逐条刷屏）。"""
        if not bool((getattr(self, "_recommend_cfg", {}) or {}).get("notify", True)):
            return
        rows = [x for x in (report.get("items") or []) if x.get("verdict") == "推荐"]
        if not rows:
            return
        try:
            lines = []
            for it in rows[:10]:
                _r = it.get("rating")
                lines.append(f"· {str(it.get('title') or '')[:48]}（评分 {_r if _r else '—'}）")
            more = f"\n…共 {len(rows)} 部" if len(rows) > 10 else ""
            self.post_message(
                title="魔流·静默池推荐",
                text=(
                    "静默池分拣完成，以下资源值得收藏（已打「魔流-推荐」并保护）：\n"
                    + "\n".join(lines) + more
                    + "\n在工作台 →「推荐」确认入库，确认后自动整理进资源库（转「静默-资源」）。"
                ),
            )
        except Exception as err:  # noqa: BLE001
            self._dbg(f"静默分拣:汇总通知失败:{err}")
