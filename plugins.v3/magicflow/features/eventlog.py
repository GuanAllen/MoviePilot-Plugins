# -*- coding: utf-8 -*-
"""魔流 · eventlog —— 结构化事件流（可观测④）。

Master 口径（2026-10-02 11:10）：不装 Prometheus、不暴露 /metrics → 全部插件内建。

**不做第二份日志**：已有的「操作日志」（`persistence.OperationJournal`，热层 Redis + 冷备 JSON）
本来就是结构化的「发生了什么」流水（选种/删种/辅种/保护/标签/换种/认领/签到/推荐…）。
本模块把它**读成一条统一事件流**，并补上 journal 里没有的事件（健康告警、任务执行失败等，
落在本模块自己的小环形缓冲 —— ★ 12.6.0 起存热层 ``cache-eventlog``，不再落 kv）。

事件统一 schema：
    {
      "id": str,            # journal: operation_id；本模块: "ev:<seq>"
      "ts": float,          # 秒（unix）
      "kind": str,          # 分类
      "level": str,         # info | warning | error
      "action": str,        # 中文动作名
      "task_id": str, "task_name": str,
      "site_id": int, "site_name": str,
      "state": str,         # journal 的最终态 completed/failed（未完成态默认不返回）
      "count": int,         # 涉及种子数
      "reason": str,        # 主因（去重后的前两条）
      "items": [ ... ],      # 明细（最多 10 条）
      "metrics": { ... },    # 结构化数字（时魔合计 / 体积合计）
      "error": str,
    }

只读端点：
    GET /events?since=&limit=&kind=&task_id=&level=&scope=&include_open=
    GET /debug/events
"""

import time
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from app.schemas import Response

from ..common import CACHE_TTL_HISTORY
from ..kvstore import cache_get, cache_set

EVENTLOG_KEY = "eventlog_v1"    # 热层逻辑键（★ 12.6.0 起不再落 kv）
EVENTLOG_KEEP = 300
FLUSH_MIN_INTERVAL = 2.0

# kind → (level, 中文动作名)
KIND_META: Dict[str, tuple] = {
    "deletion": ("warning", "删除种子"),
    "delete": ("warning", "删除种子"),
    "unprotection": ("warning", "解除保护"),
    "swap": ("warning", "自动换种"),
    "state": ("warning", "任务状态变更"),
    "pause": ("info", "暂停做种"),
    "resume": ("info", "恢复做种"),
    "sitecap": ("warning", "站点容量变动"),
    "run": ("info", "执行一轮"),
    "health": ("warning", "健康告警"),
    "hr": ("warning", "H&R 欠账"),
    "leeching": ("info", "下载中"),
    "recheck": ("info", "重新校验"),
    "protection": ("info", "保护种子"),
    "reseed": ("info", "辅种"),
    "reuse": ("info", "存量复用"),
    "selection": ("info", "选种"),
    "tag": ("info", "标签/纳管"),
    "claim": ("info", "认领"),
    "sign": ("info", "签到"),
    "signin": ("info", "签到"),
    "recommend": ("info", "推荐"),
    "exam": ("info", "新手考核"),
    "goal": ("info", "目标达成"),
    "cloud": ("info", "云盘归档"),
    "fallback": ("warning", "元数据兜底"),
    "official": ("info", "官种处理"),
    "live": ("info", "做种同步"),
    "formula": ("info", "魔力公式"),
    "browse": ("info", "站点浏览"),
    "inbox": ("info", "站内信"),
    "welcome": ("info", "站点问候"),
    "passkey": ("warning", "Passkey 变更"),
    "login": ("warning", "站点登录"),
    "api": ("info", "接口调用"),
    "debug": ("info", "调试"),
    "rules": ("info", "站点规则"),
}
_LEVEL_RANK = {"info": 1, "warning": 2, "error": 3}


def _kind_meta(kind: str) -> tuple:
    return KIND_META.get(str(kind or "").strip(), ("info", str(kind or "")))


class EventLogMixin:
    """统一事件流：journal 读模型 + 本地补充事件环形缓冲。"""

    # ------------------------------------------------------------
    # 本地补充事件（journal 覆盖不到的）
    # ------------------------------------------------------------

    def _eventlog_data(self) -> Dict[str, Any]:
        cache = getattr(self, "_eventlog_cache", None)
        if cache is None:
            cache = {"seq": 0, "rows": []}
            try:
                raw = cache_get(self, "eventlog", EVENTLOG_KEY, CACHE_TTL_HISTORY)
                if isinstance(raw, dict):
                    cache = {"seq": int(raw.get("seq") or 0), "rows": list(raw.get("rows") or [])}
            except Exception:  # noqa: BLE001
                pass
            self._eventlog_cache = cache
        return cache

    def _eventlog_flush(self, force: bool = False) -> None:
        now = time.time()
        last = float(getattr(self, "_eventlog_flushed_at", 0.0) or 0.0)
        if not force and now - last < FLUSH_MIN_INTERVAL:
            return
        try:
            cache_set(self, "eventlog", EVENTLOG_KEY, self._eventlog_data(), CACHE_TTL_HISTORY)
            self._eventlog_flushed_at = now
        except Exception:  # noqa: BLE001
            pass

    def _emit_event(
        self,
        kind: str,
        action: str = "",
        level: str = "info",
        task_id: str = "",
        reason: str = "",
        metrics: Optional[Dict[str, Any]] = None,
        dedup_key: str = "",
    ) -> None:
        """写一条本地补充事件（journal 里没有的那些）。"""
        try:
            data = self._eventlog_data()
            # 同 dedup_key 且最近 10 分钟内已发过 → 不重复（防抖）
            if dedup_key:
                cutoff = time.time() - 600
                for row in reversed(data.get("rows") or []):
                    if float(row.get("ts") or 0) < cutoff:
                        break
                    if row.get("dedup") == dedup_key:
                        return
            seq = int(data.get("seq") or 0) + 1
            data["seq"] = seq
            task_id = str(task_id or "")
            row = {
                "id": f"ev:{seq}",
                "seq": seq,
                "ts": time.time(),
                "kind": str(kind or ""),
                "level": str(level or "info"),
                "action": str(action or _kind_meta(kind)[1]),
                "task_id": task_id,
                "task_name": self._event_task_name(task_id),
                "site_id": self._event_site_of(task_id),
                "site_name": self._event_site_name(task_id),
                "reason": str(reason or "")[:300],
                "metrics": dict(metrics or {}),
                "count": int((metrics or {}).get("count") or 0),
                "dedup": dedup_key,
            }
            rows = list(data.get("rows") or [])
            rows.append(row)
            data["rows"] = rows[-EVENTLOG_KEEP:]
            self._eventlog_flush()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------
    # journal → 事件（读模型）
    # ------------------------------------------------------------

    def _journal_events(self, limit: int) -> List[Dict[str, Any]]:
        if not self._store:
            return []
        try:
            records = self._store.journal.list_recent(limit=limit) or []
        except Exception:  # noqa: BLE001
            return []
        out: List[Dict[str, Any]] = []
        for r in records:
            try:
                out.append(self._event_from_record(r))
            except Exception:  # noqa: BLE001
                continue
        return out

    def _event_from_record(self, record: Any) -> Dict[str, Any]:
        def _g(name: str, default: Any = None) -> Any:
            if isinstance(record, dict):
                return record.get(name, default)
            return getattr(record, name, default)

        kind = str(_g("kind", "") or "")
        level, action = _kind_meta(kind)
        task_id = str(_g("task_id", "") or "")
        items = _g("items", []) or []
        raw_items: List[Dict[str, Any]] = []
        for it in items[:10]:
            if isinstance(it, dict):
                d = it
            elif hasattr(it, "to_dict"):
                d = it.to_dict()
            elif is_dataclass(it):
                d = asdict(it)
            else:
                d = {k: getattr(it, k, None) for k in ("hash", "title", "reason", "source",
                                                       "bonus_per_hour", "size_gb", "seeders", "tags")}
            raw_items.append({
                "hash": str(d.get("hash") or "")[:16],
                "title": str(d.get("title") or "")[:80],
                "reason": str(d.get("reason") or "")[:120],
                "source": str(d.get("source") or ""),
                "bonus_per_hour": round(float(d.get("bonus_per_hour") or 0.0), 3),
                "size_gb": round(float(d.get("size_gb") or 0.0), 3),
                "seeders": int(d.get("seeders") or 0),
                "tags": str(d.get("tags") or "")[:60],
            })
        reasons: List[str] = []
        for d in raw_items:
            rr = str(d.get("reason") or "").split("，")[0].strip()
            if rr and rr not in reasons:
                reasons.append(rr)
        error = str(_g("error_message", "") or "")
        if error:
            level = "error"
        return {
            "id": str(_g("operation_id", "") or ""),
            "ts": float(_g("created_at", 0.0) or 0.0),
            "kind": kind,
            "level": level,
            "action": action,
            "task_id": task_id,
            "task_name": self._event_task_name(task_id),
            "site_id": self._event_site_of(task_id),
            "site_name": self._event_site_name(task_id),
            "state": str(_g("state", "") or ""),
            "count": len(items),
            "reason": "；".join(reasons[:2]),
            "items": raw_items,
            "metrics": {
                "bonus_per_hour": round(sum(d["bonus_per_hour"] for d in raw_items), 3),
                "size_gb": round(sum(d["size_gb"] for d in raw_items), 3),
            },
            "error": error,
        }

    # ------------------------------------------------------------
    # 名字映射
    # ------------------------------------------------------------

    def _event_task(self, task_id: str) -> Any:
        try:
            return (getattr(self, "_task_configs", {}) or {}).get(str(task_id or ""))
        except Exception:  # noqa: BLE001
            return None

    def _event_task_name(self, task_id: str) -> str:
        t = self._event_task(task_id)
        return str(getattr(t, "name", "") or "") if t else ""

    def _event_site_of(self, task_id: str) -> Any:
        t = self._event_task(task_id)
        return getattr(t, "site_id", None) if t else None

    def _event_site_name(self, task_id: str) -> str:
        t = self._event_task(task_id)
        return str(getattr(t, "site_name", "") or "") if t else ""

    # ------------------------------------------------------------
    # 端点
    # ------------------------------------------------------------

    def get_events(
        self,
        since: Any = 0,
        limit: Any = 200,
        kind: Any = "",
        task_id: Any = "",
        level: Any = "",
        min_level: Any = "",
        include_open: Any = 0,
    ) -> Response:
        """功能端点：结构化事件流（默认升序，便于前端用 ``since`` 增量拉取）。"""
        try:
            try:
                limit = max(1, min(int(limit or 200), 1000))
            except Exception:  # noqa: BLE001
                limit = 200
            try:
                since_ts = float(since or 0)
                if since_ts > 1e11:      # 传的是毫秒
                    since_ts /= 1000.0
            except Exception:  # noqa: BLE001
                since_ts = 0.0
            kinds = {k.strip() for k in str(kind or "").split(",") if k.strip()}
            levels = {k.strip() for k in str(level or "").split(",") if k.strip()}
            min_rank = _LEVEL_RANK.get(str(min_level or "").strip(), 0)
            want_task = str(task_id or "").strip()
            show_open = str(include_open or "0").strip() not in ("", "0", "false", "False")

            events = self._journal_events(limit=min(1000, max(limit * 3, 200)))
            # 本地补充事件（已升序按 append 顺序）
            events.extend(dict(r) for r in (self._eventlog_data().get("rows") or []))

            picked: List[Dict[str, Any]] = []
            for ev in events:
                if float(ev.get("ts") or 0) <= since_ts:
                    continue
                if not show_open and str(ev.get("state") or "") in ("submitting", "accepted"):
                    continue
                if kinds and str(ev.get("kind") or "") not in kinds:
                    continue
                if levels and str(ev.get("level") or "") not in levels:
                    continue
                if min_rank and _LEVEL_RANK.get(str(ev.get("level") or ""), 1) < min_rank:
                    continue
                if want_task and str(ev.get("task_id") or "") != want_task:
                    continue
                picked.append(ev)
            picked.sort(key=lambda e: (float(e.get("ts") or 0), str(e.get("id") or "")))
            picked = picked[-limit:]
            latest = max([float(e.get("ts") or 0) for e in picked], default=since_ts)
            return Response(success=True, data={
                "events": picked,
                "count": len(picked),
                "since": since_ts,
                "latest_ts": latest,
                "server_ts": time.time(),
            })
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"读取事件流失败：{err}")

    def debug_events(self) -> Response:
        """只读诊断：事件数量（分 kind / level）与本地缓冲状态。"""
        try:
            local = self._eventlog_data()
            try:
                n_journal = len(self._store.journal.list_recent(limit=1000) or []) if self._store else 0
            except Exception:  # noqa: BLE001
                n_journal = 0
            by_kind: Dict[str, int] = {}
            by_level: Dict[str, int] = {}
            for ev in self._journal_events(limit=1000):
                by_kind[ev["kind"]] = by_kind.get(ev["kind"], 0) + 1
                by_level[ev["level"]] = by_level.get(ev["level"], 0) + 1
            for row in local.get("rows") or []:
                k = str(row.get("kind") or "")
                lv = str(row.get("level") or "")
                by_kind[k] = by_kind.get(k, 0) + 1
                by_level[lv] = by_level.get(lv, 0) + 1
            return Response(success=True, data={
                "journal_records": n_journal,
                "local_rows": len(local.get("rows") or []),
                "local_seq": int(local.get("seq") or 0),
                "by_kind": by_kind,
                "by_level": by_level,
                "kinds_known": sorted(KIND_META.keys()),
            })
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"事件流诊断失败：{err}")
