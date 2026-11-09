#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 测试用内存账单存储（三态契约 + CAS）。

任务 134：``HrBillsStore``（JSON 后端）随 PG 单一权威退役后，只依赖「账单内存」的
业务回归测试改用本夹具。它**不是**运行时代码，也不允许被 features/ 引用。

契约与 ``PgHrBillsStore`` 对齐：
  - 读：``get_result`` / ``all_result`` / ``events_result`` / ``all_events_result``
        → FOUND / ABSENT / UNKNOWN（本夹具不会产生 UNKNOWN）。
  - 写：``put_result`` / ``patch_result`` / ``drop_result`` / ``drop_many_result``
        → ``_hr_store_write`` 形状的 dict；``patch_if`` 返回 ``{ok,reason,row,events}``。
  - 兼容面：``get/all/put/patch/patch_if/drop/drop_many/drop_many_if/drop_void/
        events_for/stats/flush``。

用法（测试内）::

    from _hr_mem_store import MemHrBillsStore
    store = MemHrBillsStore()
    h._hrbills_store = lambda: store
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

_FIELDS = ("site", "rule", "state", "fp", "need_h", "seeded_h", "progress",
           "last_progress", "last_progress_at", "title", "opened_at", "opened_by",
           "settled_at", "breached_at", "voided_at", "void_reason",
           "alive", "last_seen", "seen_by", "src", "missing_since", "stalled_at",
           "settle_block", "settle_block_at", "settlement_method", "settled_by",
           "settlement_reason")


def _read(status: str, value: Any, source: str = "mem") -> Dict[str, Any]:
    return {"status": status, "value": value, "error": "" if status != "unknown" else "mem",
            "source": source, "checked_at": time.time()}


def _write(ok: bool, reason: str = "", row: Any = None) -> Dict[str, Any]:
    return {"ok": bool(ok), "partial": False, "status": "found" if ok else "unknown",
            "reason": "" if ok else reason, "value": row, "source": "mem",
            "checked_at": time.time()}


class MemHrBillsStore:
    """内存账单存储：单进程线程内使用，CAS 语义与 PG 版一致。"""

    _FIELDS = _FIELDS

    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.bills: Dict[str, Dict[str, Any]] = {}
        self.events: List[Dict[str, Any]] = []
        self.generation = 0

    # ------------------------------------------------------------ 读
    def get_result(self, hash_string: str) -> Dict[str, Any]:
        h = str(hash_string or "").strip().lower()
        b = self.bills.get(h)
        return _read("found", dict(b)) if b is not None else _read("absent", None)

    def all_result(self) -> Dict[str, Any]:
        return _read("found", {k: dict(v) for k, v in self.bills.items()})

    def events_result(self, hash_string: str = "", limit: int = 0) -> Dict[str, Any]:
        h = str(hash_string or "").strip().lower()
        rows = [dict(e) for e in self.events if not h or e.get("hash") == h]
        rows.sort(key=lambda e: float(e.get("at") or 0.0))
        if limit and int(limit) > 0:
            rows = rows[-int(limit):]
        return _read("found", rows)

    def all_events_result(self) -> Dict[str, Any]:
        rows = sorted((dict(e) for e in self.events), key=lambda e: float(e.get("at") or 0.0))
        return _read("found", rows)

    # ------------------------------------------------------------ 写
    def put_result(self, hash_string: str, bill: Dict[str, Any],
                   save: bool = True) -> Dict[str, Any]:
        h = str(hash_string or "").strip().lower()
        if not h:
            return _write(False, "missing")
        if h in self.bills:
            return _write(True, row=dict(self.bills[h]))
        row = {k: (bill or {}).get(k) for k in _FIELDS}
        row["hash"] = h
        row.setdefault("opened_at", time.time())
        self.bills[h] = row
        self.generation += 1
        return _write(True, row=dict(row))

    def patch_result(self, hash_string: str, save: bool = True,
                     **fields: Any) -> Dict[str, Any]:
        h = str(hash_string or "").strip().lower()
        row = self.bills.get(h)
        if row is None:
            return _write(False, "missing")
        for k, v in (fields or {}).items():
            if k in _FIELDS:
                row[k] = v
        row["updated"] = time.time()
        self.generation += 1
        return _write(True, row=dict(row))

    def patch_if(self, hash_string: str, expect: Any = None,
                 events: Any = None, **fields: Any) -> Dict[str, Any]:
        h = str(hash_string or "").strip().lower()
        row = self.bills.get(h)
        if row is None:
            return {"ok": False, "reason": "missing", "row": None}
        for k, v in (expect or {}).items():
            if row.get(k) != v:
                return {"ok": False, "reason": "conflict", "row": dict(row)}
        for k, v in (fields or {}).items():
            if k in _FIELDS:
                row[k] = v
        row["updated"] = time.time()
        evs = [dict(e) for e in (events or []) if isinstance(e, dict)]
        for e in evs:
            e.setdefault("hash", h)
            e.setdefault("at", time.time())
        self.events.extend(evs)
        self.generation += 1
        return {"ok": True, "reason": "", "row": dict(row), "events": len(evs)}

    def drop_result(self, hash_string: str) -> Dict[str, Any]:
        h = str(hash_string or "").strip().lower()
        existed = self.bills.pop(h, None) is not None
        if existed:
            self.generation += 1
        return _write(True, row={"dropped": existed, "hash": h})

    def drop_many_result(self, hashes: Any) -> Dict[str, Any]:
        hs = [str(h or "").strip().lower() for h in (hashes or [])]
        n = 0
        for h in hs:
            if self.bills.pop(h, None) is not None:
                n += 1
        if n:
            self.generation += 1
        return {"ok": True, "partial": False, "status": "found",
                "reason": "", "value": {"dropped": n, "requested": len(hs)},
                "source": "mem", "checked_at": time.time()}

    # ------------------------------------------------------------ 兼容面
    def get(self, hash_string: str) -> Optional[Dict[str, Any]]:
        return self.get_result(hash_string).get("value")

    def all(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.all_result().get("value") or {})

    def events_for(self, hash_string: str = "", limit: int = 0) -> List[Dict[str, Any]]:
        return list(self.events_result(hash_string, limit).get("value") or [])

    def put(self, hash_string: str, bill: Dict[str, Any],
            save: bool = True) -> Optional[Dict[str, Any]]:
        res = self.put_result(hash_string, bill, save=save)
        return res.get("value") if res.get("ok") else None

    def patch(self, hash_string: str, save: bool = True, **fields: Any) -> Optional[Dict[str, Any]]:
        res = self.patch_result(hash_string, save=save, **fields)
        return res.get("value") if res.get("ok") else None

    def drop(self, hash_string: str) -> bool:
        h = str(hash_string or "").strip().lower()
        existed = self.bills.pop(h, None) is not None
        if existed:
            # ★ 任务 136（N-136-06）：与 PG 同步——账单删除必须同事务删事件。
            self.events = [e for e in self.events if e.get("hash") != h]
            self.generation += 1
        return existed

    def drop_many(self, hashes: Any) -> int:
        hs = [str(h or "").strip().lower() for h in (hashes or [])]
        n = sum(1 for h in hs if self.bills.pop(h, None) is not None)
        if n:
            self.events = [e for e in self.events if e.get("hash") not in set(hs)]
        return n

    def drop_void(self) -> int:
        hs = [h for h, b in self.bills.items() if b.get("state") == "void"]
        for h in hs:
            self.bills.pop(h, None)
        return len(hs)

    def drop_many_if(self, items: Any) -> Dict[str, Any]:
        out: Dict[str, Any] = {"dropped": [], "skipped": []}
        for item in items or ():
            try:
                h = str(item[0] if not isinstance(item, dict) else item.get("hash") or "").lower()
                exp = item[1] if not isinstance(item, dict) else None
            except Exception:  # noqa: BLE001
                continue
            row = self.bills.get(h)
            if row is None:
                out["skipped"].append(h)
                continue
            if exp and any(row.get(k) != v for k, v in exp.items()):
                out["skipped"].append(h)
                continue
            self.bills.pop(h, None)
            self.events = [e for e in self.events if e.get("hash") != h]
            out["dropped"].append(h)
        return out

    def flush(self) -> None:
        return None

    def stats(self) -> Dict[str, Any]:
        by_state: Dict[str, int] = {}
        for b in self.bills.values():
            st = str(b.get("state") or "")
            by_state[st] = by_state.get(st, 0) + 1
        return {"total": len(self.bills), "by_state": by_state, "by_rule": {},
                "by_site": {}, "no_site": 0, "opened_by": {},
                "store_status": "found", "store_error": "", "checked_at": time.time()}

    def purge_expired(self, retention_days: float = 30.0, batch: int = 200) -> Dict[str, Any]:
        return {"ok": True, "cutoff": time.time() - retention_days * 86400.0,
                "scanned": 0, "eligible": 0, "deleted_bills": 0, "deleted_events": 0,
                "batches": 0, "retention_days": retention_days, "invalid_times": 0,
                "skipped_invalid": 0}
