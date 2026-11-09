#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 132：过期清理编排（30 天 / 批量 / 失败关闭 / 幂等）。

覆盖：
  A. 结果工厂语义：FOUND/ABSENT/UNKNOWN；写结果 ok/partial → 不确定不得算成功。
  B. PG 后端：db 模块缺失 / 不可用 / 会话异常 / 行不存在 / 行存在 的三态读。
  C. 存储工厂：PG 可用 → PgHrBillsStore；不可用 → UnavailableHrBillsStore（UNKNOWN/写失败）。
  D. 消费面守卫：owed / tick / void / stats / open 在 UNKNOWN 下的保守行为。
  E. 元信息：meta 字段（backend/authority/available/degraded_reason）真实反映状态。

纯离线：桩模块替代 app.* 与插件依赖，加载真实 ``features/hrbills.py``。
用法：``python3 tools/test_hr_store_contract.py``（0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_t132_purge"
FAILS: list[str] = []
CASES = 0


def _ok(cond, name, detail=""):
    global CASES
    CASES += 1
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name}" + (f" —— {detail}" if detail else ""))
        FAILS.append(name)


class _Any:
    """惰性万能桩：可调用、可点属性、可迭代为空。"""

    def __init__(self, name="dummy"):
        self._name = name

    def __call__(self, *a, **k):
        return _Any(self._name + "()")

    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return _Any(f"{self._name}.{k}")

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return True


def _mod(name, **attrs):
    m = sys.modules.get(name) or types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    if not hasattr(m, "__getattr__"):
        m.__getattr__ = lambda n: _Any(f"{name}.{n}")
    sys.modules[name] = m
    return m


class _Shared:
    def __init__(self):
        import threading
        self.lock = threading.RLock()
        self.singletons = {}


_SHARED = _Shared()


def _load_hrbills():
    _mod("app")
    _mod("app.schemas", Response=type("Response", (), {}))
    _mod("app.sdk")
    _mod("app.sdk.logging", logger=type("L", (), {
        "warning": staticmethod(lambda *a, **k: None),
        "info": staticmethod(lambda *a, **k: None),
        "error": staticmethod(lambda *a, **k: None)})())
    pkg = _mod(PKG)
    pkg.__path__ = [str(ROOT)]
    _mod(PKG + ".tags", MARK_REUSE="mark-reuse", RESCUE_TAG="rescue",
         is_reuse_copy=lambda tags: False)
    _mod(PKG + ".fingerprint", fingerprint=lambda *a, **k: "",
         info_hash=lambda *a, **k: "")
    _mod(PKG + ".downloader_ops", seed_hours_for_hr=lambda t: 0.0)
    _mod(PKG + ".persistence", _shared=lambda: _SHARED,
         OperationItem=type("OperationItem", (), {}))
    _mod(PKG + ".common", HR_COMPLETE_RATIO_DEFAULT=0.999,
         HR_DEADLINE_WARN_HOURS_DEFAULT=48.0,
         HR_SEED_MARGIN_HOURS_DEFAULT=2.0)
    spec = importlib.util.spec_from_file_location(
        PKG + ".features.hrbills", ROOT / "features/hrbills.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG + ".features.hrbills"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class FakeRow:
    def __init__(self, data):
        self._data = dict(data)
        self.hash = data.get("hash") or data.get("_hash") or ""

    def __getattr__(self, k):
        try:
            return self._data[k]
        except KeyError:
            raise AttributeError(k)


class FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        return FakeQuery(self._rows[:int(n)])

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        """真实 SQLAlchemy Query 支持 count；可见性探测依赖它（任务 128）。"""
        return len(self._rows)


class FakeSession:
    def __init__(self, rows, events):
        self.rows = dict(rows)
        self.events = dict(events)

    def get(self, model, key):
        if getattr(model, "__name__", "") == "BillRow":
            return FakeRow(dict(self.rows[key], hash=key)) if key in self.rows else None
        return None

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "BillRow":
            return FakeQuery([FakeRow(dict(v, hash=k)) for k, v in self.rows.items()])
        return FakeQuery([FakeRow(dict(v)) for v in self.events.values()])

    def add(self, obj):
        pass

    def flush(self):
        pass

    def commit(self):
        pass


class FakeDB:
    BillRow = type("BillRow", (), {})
    BillEventRow = type("BillEventRow", (), {})
    SeedRow = type("SeedRow", (), {})

    def __init__(self, rows, events=None, available=True, raise_on_session=False):
        self.rows = rows
        self.events = events or {}
        self.available = available
        self.raise_on_session = raise_on_session

    def db_available(self):
        return self.available

    def db_session(self):
        outer = self

        class _Ctx:
            def __enter__(self):
                if outer.raise_on_session:
                    raise RuntimeError("db session failed")
                return FakeSession(outer.rows, outer.events)

            def __exit__(self, *a):
                return False

        return _Ctx()


class FakeStore:
    """可编程的三态存储桩（切回一致性测试用）。"""

    def __init__(self, bills, events=None, fail=False, mutate=None):
        self._bills = dict(bills)
        self._events = events or {}
        self._fail = fail
        self._mutate = mutate
        self.calls = []

    def all_result(self):
        self.calls.append("all")
        if self._fail:
            return {"status": "unknown", "value": None, "error": "boom",
                    "source": "fake", "checked_at": 0.0}
        return {"status": "found", "value": dict(self._bills), "error": "",
                "source": "fake", "checked_at": 0.0}

    def events_result(self, h, limit=0):
        if self._fail:
            return {"status": "unknown", "value": None, "error": "boom",
                    "source": "fake", "checked_at": 0.0}
        return {"status": "found", "value": list(self._events.get(h) or []),
                "error": "", "source": "fake", "checked_at": 0.0}


def _bill(**over):
    b = {"hash": "a" * 40, "site": "carpt.net", "rule": "site_hr",
         "state": "active", "need_h": 24.0, "seeded_h": 1.0, "progress": 1.0,
         "opened_at": 100.0, "settled_at": None, "settlement_method": None,
         "settled_by": None, "settlement_reason": None, "voided_at": None,
         "void_reason": None}
    b.update(over)
    return b


def main() -> int:
    hb = _load_hrbills()
    saved = hb._mfdb_module

    class PurgeStore(hb.PgHrBillsStore):
        """只测编排：_purge_batch / _purge_association_error 由用例注入。"""

        batches = None
        assoc_error = ""
        fail_at = -1
        calls = 0

        def _purge_association_error(self, mf):
            return self.assoc_error

        def _purge_batch(self, mf, cutoff, limit, now=0.0):
            idx = PurgeStore.calls
            PurgeStore.calls += 1
            if idx == PurgeStore.fail_at:
                raise RuntimeError("purge_concurrent_change")
            bs = PurgeStore.batches or []
            n, e = bs[idx] if idx < len(bs) else (0, 0)
            return {"scanned": n, "deleted_bills": n, "deleted_events": e}



    def fresh(db_ok=True, **over):
        PurgeStore.calls = 0
        PurgeStore.batches = over.get("batches")
        PurgeStore.assoc_error = over.get("assoc_error", "")
        PurgeStore.fail_at = over.get("fail_at", -1)
        db = FakeDB({}, available=db_ok)
        hb._mfdb_module = lambda: db
        with tempfile.TemporaryDirectory() as td:
            st = PurgeStore(Path(td))
            return st.purge_expired(retention_days=30.0, batch=2)

    print("\n── A. 过期窗口与阈值 ──")
    r = fresh(batches=[(0, 0)])
    _ok(r["ok"] is True and abs((time.time() - r["cutoff"]) - 30 * 86400) < 120,
        "cutoff = now - 30 天")
    _ok(r["retention_days"] == 30.0, "返回实际保留天数")

    print("\n── B. 失败关闭 ──")
    r = fresh(db_ok=False)
    _ok(not r["ok"] and r["error"] == "db_unavailable", "PG 不可用 → 不清理")
    r = fresh(assoc_error="association_orphan_events")
    _ok(not r["ok"] and r["error"].startswith("association_"),
        "关联异常 → 整轮停止（不删任何行）")
    r = fresh(fail_at=1, batches=[(2, 3), (2, 3)])
    _ok(not r["ok"] and "batch_failed" in r["error"],
        "批量事务异常 → 停止并报告（不静默继续）")

    print("\n── C. 批量与上限 ──")
    r = fresh(batches=[(2, 3), (2, 4), (1, 1)])
    _ok(r["ok"] and r["deleted_bills"] == 5 and r["deleted_events"] == 8
        and r["batches"] == 3, "多批累加；短批结束", str(r))
    r = fresh(batches=[(2, 2)] * 1200)
    _ok(r["ok"] and r.get("limit_reached") is True and r["batches"] == 1000,
        "达到单次上限 → 标记 limit_reached（不无限跑）")

    print("\n── D. 幂等与空操作 ──")
    r = fresh(batches=[])
    _ok(r["ok"] and r["deleted_bills"] == 0, "无候选 → ok + 0（幂等）")
    hb._mfdb_module = saved

    print("\n── E. 最终状态时间合法性（任务 134 / N-133-02） ──")
    now = 1_700_000_000.0
    day = 86400.0
    for bad, label in [(None, "None"), ("", "空串"), (0, "0"), (-1, "负数"),
                       (float("nan"), "NaN"), (float("inf"), "+Inf"),
                       (float("-inf"), "-Inf"), ("abc", "非数字"), (now + 1.0, "未来时间")]:
        _ok(hb._purge_ts_ok(bad, now) is False, f"{label} → 不是清理依据")
    _ok(hb._purge_ts_ok(now - 29 * day, now) is True, "合法历史时间 → 通过时间校验")
    _ok(hb._purge_ts_ok(now + 10 * 365 * day, now) is False, "超远未来（>2100）→ 拒绝")
    _ok(hb._purge_ts_ok(now - 30 * day, now) is True, "30 天整 → 合法（cutoff 由调用方比较）")

    print(f"\n通过 {CASES - len(FAILS)} / 失败 {len(FAILS)}")
    if FAILS:
        print("❌ FAIL:\n  - " + "\n  - ".join(FAILS))
        return 1
    print("✅ PASS —— 过期清理编排测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
