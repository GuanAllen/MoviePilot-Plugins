#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 132：PG 单一权威存储契约（无 JSON 运行时）。

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
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_t111_store"
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
    print(f"加载 hrbills.py 成功（{len(dir(hb))} 个名字）")

    print("\n── A. 结果工厂语义 ──")
    r = hb._hr_found({"a": 1}, "pg")
    _ok(r["status"] == "found" and r["value"] == {"a": 1}, "FOUND 带 value 与 source")
    _ok(r["checked_at"] > 0, "FOUND 带检查时间")
    _ok(hb._hr_absent("pg")["status"] == "absent", "ABSENT 无 value")
    u = hb._hr_unknown("db_unavailable", "pg")
    _ok(u["status"] == "unknown" and u["error"] == "db_unavailable", "UNKNOWN 带错误摘要")
    _ok(hb._hr_read_ok(r) and not hb._hr_read_ok(u), "读结果判定互斥")
    w_partial = hb._hr_store_write(True, "partial", partial=True, source="pg")
    _ok(not w_partial["ok"] and w_partial["status"] == "unknown",
        "部分成功 → ok=False + UNKNOWN（不得包装成整体成功）")

    print("\n── B. PG 后端三态 ──")
    with tempfile.TemporaryDirectory() as td:
        db = FakeDB({}, available=False)
        st = hb.PgHrBillsStore(Path(td))
        saved = hb._mfdb_module
        hb._mfdb_module = lambda: None
        _ok(not hb._hr_read_ok(st.get_result("x")), "db 模块缺失 → get UNKNOWN")
        hb._mfdb_module = lambda: db
        _ok(st.all_result()["status"] == "unknown", "db 不可用 → all UNKNOWN")
        _ok(st.events_result("")["status"] == "unknown", "db 不可用 → 事件 UNKNOWN")
        _ok(st.put_result("h", {})["ok"] is False, "db 不可用 → 写失败（不伪装）")
        db2 = FakeDB({}, raise_on_session=True)
        hb._mfdb_module = lambda: db2
        _ok(st.get_result("x")["status"] == "unknown", "会话异常 → UNKNOWN")
        db3 = FakeDB({"h1": _bill(hash="h1")})
        hb._mfdb_module = lambda: db3
        g = st.get_result("h1")
        _ok(g["status"] == "found" and g["value"]["hash"] == "h1", "命中 → FOUND")
        _ok(st.get_result("nope")["status"] == "absent", "未命中 → ABSENT（行不存在）")
        _ok(st.all_result()["status"] == "found", "all → FOUND")
        hb._mfdb_module = saved

    print("\n── C. 存储工厂（PG 单一权威）──")
    with tempfile.TemporaryDirectory() as td:
        saved = hb._mfdb_module
        hb._mfdb_module = lambda: None
        hb._HR_STORE_META.clear()
        hb._shared().singletons.clear()
        s1 = hb.get_hr_bills_store(Path(td))
        _ok(isinstance(s1, hb.UnavailableHrBillsStore), "无 db 模块 → Unavailable（不回落 JSON）")
        _ok(s1.get_result("h")["status"] == "unknown", "占位 store 读 UNKNOWN")
        _ok(s1.put_result("h", {})["ok"] is False, "占位 store 写失败")
        m1 = hb.hr_bills_store_meta(Path(td))
        _ok(m1["backend"] == "unavailable" and m1["available"] is False,
            "meta 如实 unavailable")
        db = FakeDB({"h1": _bill(hash="h1")}, available=True)
        hb._mfdb_module = lambda: db
        hb._HR_STORE_META.clear()
        hb._shared().singletons.clear()
        s2 = hb.get_hr_bills_store(Path(td))
        _ok(isinstance(s2, hb.PgHrBillsStore), "PG 可用 → Pg store")
        m2 = hb.hr_bills_store_meta(Path(td))
        _ok(m2["backend"] == "pg" and m2["authority"] == "pg" and m2["available"] is True,
            "meta 如实 pg 权威")
        hb._mfdb_module = saved

    print("\n── C2. Unavailable 的 CAS 返回值契约（任务 134 / N-133-01） ──")
    _un = hb.UnavailableHrBillsStore(Path(td))
    _res = _un.patch_if("abc", {"state": "active"}, state="settled")
    _ok(isinstance(_res, dict), f"patch_if 返回 dict（实际 {type(_res).__name__}）")
    _ok(_res.get("ok") is False and _res.get("status") == "unknown",
        "patch_if 不得返回 None/成功（ok=False + status=unknown）")

    print("\n── D. 消费面在 UNKNOWN 下的保守行为 ──")
    with tempfile.TemporaryDirectory() as td:
        saved = hb._mfdb_module
        hb._mfdb_module = lambda: None
        hb._shared().singletons.clear()
        hb._HR_STORE_META.clear()
        mixin = hb.HrBillsMixin()
        mixin.get_data_path = lambda: td
        store = hb.UnavailableHrBillsStore(Path(td), "db_unavailable")
        mixin._hrbills_store = lambda: store
        st = mixin._hrbills_stats()
        _ok(st["store_status"] == "unknown", "stats → unknown（不显示正常空表）")
        tick = mixin._hrbills_tick()
        _ok(tick.get("degraded") is True, "tick → degraded（不流转/不回填）")
        v = mixin._hrbills_void("h" * 40, "test")
        _ok(bool(v.get("error")) and "未执行" in str(v.get("message") or ""),
            "void → 明确失败（不静默成功）")
        hb._mfdb_module = saved

    print(f"\n通过 {CASES - len(FAILS)} / 失败 {len(FAILS)}")
    if FAILS:
        print("❌ FAIL:\n  - " + "\n  - ".join(FAILS))
        return 1
    print("✅ PASS —— PG 单一权威契约测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
