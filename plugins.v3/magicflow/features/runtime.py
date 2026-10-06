# -*- coding: utf-8 -*-
"""魔流 · runtime —— 运行时状态（活跃实例、热层缓存、进程内锁）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime
from typing import Any, Dict, List


from app.schemas import Response

from ..dtier import PvLedger, TierCache
from ..sitestore import slot_callbacks


from ..common import (
    PV_BUDGET_RESERVE,
    PV_DEFAULT_DAILY_BUDGET,
)


def _filter_kind(records: List[Any], kind: str) -> List[Any]:
    """按 ``kind`` 过滤操作记录（逗号分隔多类型；空 = 全部）。

    ★ 兼容性说明：不用 store 侧的筛选参数——`MagicFlowStore` 进程级单例跨热重载存活，
    其 `journal` 可能还是旧类，新加的关键字参数会 TypeError。
    """
    wanted = [k.strip() for k in str(kind or "").split(",") if k.strip()]
    if not wanted:
        return list(records or [])
    return [r for r in (records or []) if str(getattr(r, "kind", "") or "") in wanted]


class RuntimeMixin:
    """runtime 功能集（原 MagicFlow 方法原样搬入）。"""

    # ------------------------------------------------------------- 数据分层(3.7.1)
    #  持久层 save_data(PluginData 表) / 缓存层 TierCache(内存+FileCache) / 进程态内存
    def _cache_base(self):
        """冷层缓存根目录(插件数据目录下 cache/);拿不到返回 None(退化纯内存)。"""
        try:
            return self.get_data_path() / "cache"
        except Exception:  # noqa: BLE001
            return None

    def _collect_ref(self):
        """采集模块（可能因启动早期未就绪而为 None）。"""
        return getattr(self, "collect", None)

    def _cache_collect(self) -> TierCache:
        """采集模块的规范化 URL 缓存（一轮一抓：同一 URL 全模块共享一份）。"""
        cache = getattr(self, "_tier_collect_obj", None)
        if cache is None:
            cache = self._tier_collect_obj = TierCache("collect", base=self._cache_base())
        return cache

    def _pv_ledger(self) -> PvLedger:
        """PV 账本（持久层：表 mf_site.pv_usage，随卸载保留/重装继承）。"""
        led = getattr(self, "_pv_ledger_obj", None)
        if led is None:
            _get, _save = slot_callbacks(self, "pv_usage")
            led = self._pv_ledger_obj = PvLedger(
                getter=lambda k: _get(),
                setter=lambda k, v: _save(value=v),
            )
        return led

    def _pv_budget(self, site_id) -> int:
        """站点 PV 日预算(0=不限)。站点覆盖值优先,否则全局默认。"""
        try:
            override = int((getattr(self, "_pv_budget_cfg", {}) or {}).get(str(int(site_id or 0)), 0) or 0)
        except Exception:  # noqa: BLE001
            override = 0
        if override > 0:
            return override
        try:
            return int(getattr(self, "_pv_default_budget", PV_DEFAULT_DAILY_BUDGET) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _pv_spend(self, site_id, kind: str, n: int = 1) -> int:
        """记一笔站点请求到账本,返回今日累计;异常不影响主流程。"""
        try:
            return self._pv_ledger().bump(site_id, kind, n)
        except Exception:  # noqa: BLE001
            return 0

    def _pv_allow(self, site_id, kind: str = "browse", want: int = 1) -> bool:
        """抓取前判断 PV 预算是否还够(预留 PV_BUDGET_RESERVE)。预算 0=不限 → 恒 True。"""
        budget = self._pv_budget(site_id)
        if budget <= 0:
            return True
        try:
            used = self._pv_ledger().today_total(site_id)
        except Exception:  # noqa: BLE001
            return True
        return (used + max(int(want), 1)) <= (budget - PV_BUDGET_RESERVE)

    def live_cache(self) -> TierCache:
        """站点实时数据缓存(内存热层 + FileCache 冷层；LiveStats 自动取用)。"""
        cache = getattr(self, "_tier_live_obj", None)
        if cache is None:
            cache = self._tier_live_obj = TierCache("live", base=self._cache_base())
        return cache

    def pv_snapshot(self, days: int = 7) -> Dict[str, Any]:
        """PV 账本快照(供 /pv 端点与看板)。站点名尽量补上。"""
        names: Dict[str, str] = {}
        try:
            for row in self._list_sites() or []:
                names[str(row.get("id"))] = str(row.get("name") or row.get("domain") or "")
        except Exception:  # noqa: BLE001
            pass
        snap = self._pv_ledger().snapshot(days=days, name_of=lambda sid: names.get(str(sid), str(sid)))
        # 附上各站预算,方便前端显示「已用/预算」
        budgets = {}
        for day in snap.get("days", []):
            for sid in (day.get("sites") or {}):
                budgets[sid] = self._pv_budget(sid)
        # 把「已配置但今天还没花 PV」的站点也列出来(否则看不出预算是否生效)
        for sid, val in (getattr(self, "_pv_budget_cfg", {}) or {}).items():
            budgets.setdefault(str(sid), int(val))
        snap["budgets"] = budgets
        snap["pv_budget_default"] = int(getattr(self, "_pv_default_budget", 0) or 0)
        snap["cache"] = self.cache_status()
        return snap

    def cache_status(self) -> Dict[str, Any]:
        """缓存层健康度:冷层是不是真的可用（FileCache/Redis），还是退化成了纯内存。"""
        out: Dict[str, Any] = {}
        for name in ("cand", "formula", "live", "official"):
            try:
                if name == "cand":
                    tc = self._cache_cands()
                elif name == "formula":
                    tc = self._cache_formula()
                elif name == "live":
                    tc = self.live_cache()
                else:
                    tc = self._cache_official()
                be = getattr(tc, "_backend", None)
                out[name] = {
                    "persistent": be is not None,
                    "backend": type(be).__name__ if be is not None else "memory-only",
                    "hot": len(getattr(tc, "_hot", {}) or {}),
                }
            except Exception as err:  # noqa: BLE001
                out[name] = {"persistent": False, "backend": f"error: {err}", "hot": 0}
        return out

    def _site_pv_blocked(self, site_id: int) -> float:
        """站点是否因「每日访问次数已达上限」被封(返回封到的时间戳,0=未封)。"""
        try:
            if getattr(self, "_live", None) is None:
                return 0.0
            return float(self._live.pv_blocked_until(int(site_id)))
        except Exception:  # noqa: BLE001
            return 0.0

    def _pv_block_reason(self, site_id: int) -> str:
        until = self._site_pv_blocked(site_id)
        if until <= time.time():
            return ""
        return time.strftime("%m-%d %H:%M", time.localtime(until))

    def get_pv_ledger(self) -> Response:
        """站点 PV 账本:每站每天耗了多少配额(可按历史查询)。"""
        try:
            return Response(success=True, data=self.pv_snapshot(days=7))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取 PV 账本失败:{err}")

    def set_pv_budget(self, payload: Dict[str, Any]) -> Response:
        """设置站点 PV 日预算:{default: int, sites: {site_id: int}};0=不限。"""
        try:
            if isinstance(payload, dict):
                if "default" in payload:
                    self._pv_default_budget = max(0, int(payload.get("default") or 0))
                sites = payload.get("sites")
                if isinstance(sites, dict):
                    cfg: Dict[str, int] = {}
                    for k, v in sites.items():
                        try:
                            if int(v or 0) > 0:
                                cfg[str(int(k))] = int(v)
                        except (TypeError, ValueError):
                            continue
                    self._pv_budget_cfg = cfg
                slot_callbacks(self, "pv_budget")[1](value=dict(self._pv_budget_cfg))
            return Response(success=True, data={
                "default": self._pv_default_budget,
                "sites": dict(self._pv_budget_cfg),
            })
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"设置 PV 预算失败:{err}")

    def store_stats(self) -> Dict[str, Any]:
        """状态存储概况（热层是否启用 + 冷备份文件），供 /status 与设置面板展示。"""
        hot = getattr(self, "_hot", None)
        out: Dict[str, Any] = {
            "hot": bool(hot is not None and hot.available()),
            "backend": "none",
            "region": "",
            "dirty": {},
            "files": {},
        }
        try:
            if hot is not None:
                st = hot.stats()
                out["backend"] = st.get("backend", "none")
                out["region"] = st.get("region", "")
                out["hot_keys"] = int(st.get("keys") or 0)
                out["hot_groups"] = dict(st.get("groups") or {})
                out["hot_writes"] = int(st.get("hot_writes") or 0)
        except Exception:  # noqa: BLE001
            pass
        try:
            store = getattr(self, "_store", None)
            if store is not None:
                out["dirty"] = store.hot_stats()
                base = self.get_data_path()
                for name in ("seen", "dead", "add_gate", "task_states", "operations", "recommend", "cloud"):
                    f = base / f"{name}.json"
                    out["files"][name] = {
                        "exists": f.exists(),
                        "bytes": f.stat().st_size if f.exists() else 0,
                        "mtime": f.stat().st_mtime if f.exists() else 0,
                    }
                try:
                    from ..persistence import get_gate_store
                    out["gate_keys"] = get_gate_store(base, getattr(self, "_hot", None)).count()
                except Exception as _ge:  # noqa: BLE001
                    out["gate_error"] = repr(_ge)
        except Exception:  # noqa: BLE001
            pass
        return out

    def debug_store(self, action: str = "") -> Response:
        """诊断/维护状态存储。

        action:
          · 空        → 热层 + 冷备份健康度
          · flush     → 把内存快照写进热层 + JSON 冷备份
          · drop-hot  → **只清我们自己的热层键**（用于验证「热层丢 → 从 JSON 回灌」）
        """
        action = str(action or "").strip().lower()
        store = getattr(self, "_store", None)
        hot = getattr(self, "_hot", None)
        if action == "flush":
            counts = store.flush_to_disk_and_hot() if store is not None else {}
            return Response(success=True, message="已落盘", data={"stores": counts, "store": self.store_stats()})
        if action in ("selftest", "test"):
            data = hot.selftest() if hot is not None else {"ok": False, "error": "no hot layer"}
            return Response(success=bool(data.get("ok")), message="热层自检", data=data)
        if action in ("drop-hot", "drop", "clear-hot"):
            if hot is None or not hot.available():
                return Response(success=False, message="热层未启用（MP 未配 Redis），状态本来就只在 JSON", data=self.store_stats())
            out = hot.drop_all_own_keys()
            return Response(success=bool(out.get("success")), message=f"已清热层键 {out.get('deleted', 0)} 个（JSON 仍在）", data=self.store_stats())
        return Response(success=True, message="OK", data=self.store_stats())

    def get_operations(self, task_id: str, kind: str = "", limit: int = 50) -> Response:
        """获取任务操作记录。

        ``kind``：按类型筛选（逗号分隔多类型，如 ``deletion,selection``；空 = 全部）。
        ``limit``：返回条数上限（默认 50）。

        ★ 筛选在**本层**做，不依赖 store 侧方法签名：`MagicFlowStore` 是进程级单例
        （跨热重载存活，见 persistence.py），热重载后 store 里的 `journal` 仍是**旧类**，
        给 `list_recent()` 新加的关键字参数在旧实例上会 TypeError。
        """
        if not self._store:
            return Response(success=True, data={"operations": [], "total": 0})
        try:
            cap = max(1, min(int(limit or 50), 500))
        except (TypeError, ValueError):
            cap = 50
        # ★ 先取足够大的窗口再筛再截断：若先按 cap 截断，类型筛选会取不到（旧的记录被截掉了）
        _win = max(cap, 500) if kind else cap
        records = _filter_kind(
            self._store.journal.list_by_task(task_id, limit=_win), kind)[:cap]
        operations = [r.to_dict() for r in records]
        return Response(success=True, data={"operations": operations, "total": len(operations),
                                            "kind": kind or "", "scope": "task"})

    def get_all_operations(self, kind: str = "", limit: int = 100) -> Response:
        """获取全部任务的操作记录（主页「操作记录」全局视图：跨任务 / 跨站点汇总）。

        ``kind``：按类型筛选（逗号分隔多类型；空 = 全部）；``limit``：条数上限（默认 100）。
        """
        if not self._store:
            return Response(success=True, data={"operations": [], "total": 0})
        try:
            cap = max(1, min(int(limit or 100), 1000))
        except (TypeError, ValueError):
            cap = 100
        _win = max(cap, 2000) if kind else cap
        records = _filter_kind(self._store.journal.list_recent(limit=_win), kind)[:cap]
        operations = [r.to_dict() for r in records]
        return Response(success=True, data={"operations": operations, "total": len(operations),
                                            "kind": kind or "", "scope": "all"})
