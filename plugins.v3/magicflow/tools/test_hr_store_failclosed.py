#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 132：存储失败关闭（N-129-03 + PG 单一权威边界）。

覆盖：
  A. 占位 store（PG 不可用）：读 UNKNOWN / 写失败 / purge 明确失败。
  B. N-129-03：`_decide_one` 在存储读异常时返回 degraded，**不抛 UnboundLocalError**。
  C. 静态边界：运行时不再 import hrstorage、不再出现 JSON 账单落盘/切换符号。

纯离线：A 直接加载 hrbills.py；B 用 ast 抽取真实 `_decide_one` 源码执行。
用法：`python3 tools/test_hr_store_failclosed.py`（0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
PKG = "mf_t132_failclosed"


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
    spec.loader.exec_module(mod)
    return mod


def _extract_decide_one():
    """把真实 `_decide_one` 源码抽出来执行（不 import 整个 agentapi）。"""
    tree = ast.parse((ROOT / "features/agentapi.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_decide_one")
    src = ast.unparse(fn)
    ns: dict = {"Dict": dict, "Any": object, "Optional": object}
    exec(compile(ast.Module(body=[ast.parse(src).body[0]], type_ignores=[]),
                 "<decide_one>", "exec"), ns)
    return ns["_decide_one"]


class _RaisingStore:
    def get_result(self, h):
        raise RuntimeError("db down")


class _UnknownStore:
    def get_result(self, h):
        return {"status": "unknown", "error": "db_unavailable"}


class _FoundStore:
    def get_result(self, h):
        return {"status": "found", "value": {"hash": h, "state": "active"},
                "error": ""}


def main() -> int:
    hb = _load_hrbills()

    print("\n── A. 占位 store 失败关闭 ──")
    with tempfile.TemporaryDirectory() as td:
        st = hb.UnavailableHrBillsStore(Path(td), "db_unavailable")
        _ok(st.get_result("h")["status"] == "unknown", "get → UNKNOWN")
        _ok(st.all_result()["error"].startswith("db_unavailable"), "all → UNKNOWN 带原因")
        _ok(st.events_result("")["status"] == "unknown", "events → UNKNOWN")
        _ok(st.all_events_result()["status"] == "unknown", "all_events → UNKNOWN")
        _ok(st.put_result("h", {})["ok"] is False, "put → 失败")
        _ok(st.drop_result("h")["ok"] is False, "drop → 失败")
        p = st.purge_expired()
        _ok(p["ok"] is False and p["error"] == "store_unavailable", "purge → 明确失败")

    print("\n── B. N-129-03：存储异常不得崩溃 ──")
    fn = _extract_decide_one()

    class S:
        pass

    s = S()
    s._agent_now = lambda: 1700000000.0
    s._agent_bill_view = lambda h, b: {"hash": h, "state": b.get("state")}
    s._hr_obligation = lambda *a, **k: (False, 0.0, 0.0, "")
    s._hrbills_store = lambda: _RaisingStore()
    it = fn(s, "a" * 40, {}, {"a" * 40: {"state": "seeding"}}, set(), set(), set())
    _ok(it["bill_store_status"] == "unknown", "读异常 → bill_store_status=unknown")
    _ok(it["verdict"] == "degraded", "读异常 → verdict=degraded（绝不 delete_candidate）")
    _ok(any("bill_store" in str(step.get("rule", "")) for step in it["reason_chain"]),
        "原因链带 hr/bill_store 证据")

    s._hrbills_store = lambda: _UnknownStore()
    it2 = fn(s, "b" * 40, {}, {}, set(), set(), set())
    _ok(it2["verdict"] == "degraded", "UNKNOWN（无异常）→ degraded")

    s._hrbills_store = lambda: _FoundStore()
    it3 = fn(s, "c" * 40, {}, {"c" * 40: {"state": "seeding"}}, set(), set(), set())
    _ok(it3["verdict"] == "delete_candidate", "FOUND → 正常走删除候选")

    print("\n── C. 静态边界（JSON 退出运行时）──")
    src = (ROOT / "features/hrbills.py").read_text(encoding="utf-8")
    _ok("hrstorage" not in src, "hrbills 不再 import hrstorage")
    _ok("committed_invisible" not in src, "不再有 committed_invisible 分层")
    _ok('self.file = self.data_dir / "hr_bills.json"' not in src,
        "不再持有 JSON 账单文件句柄（无运行时写入）")
    _ok("def _hr_switch" not in src, "不再有切回状态机")
    _ok("select_initial" not in src, "不再有冷启动存储选择")
    core = (ROOT / "features/core.py").read_text(encoding="utf-8")
    _ok("HrPurge" in core, "每日清理服务已注册")
    db_src = (ROOT / "db.py").read_text(encoding="utf-8")
    tree = ast.parse(db_src)
    bill = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "BillRow")
    cols = {n.target.id for n in bill.body
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    fields = (set(hb.PgHrBillsStore._FIELDS) | {"hash", "created"})
    _ok(cols - {"updated"} == fields, "账单投影字段与 db.BillRow 列逐一对齐",
        "多：%s 缺：%s" % (sorted(fields - cols), sorted(cols - fields)))

    print(f"\n通过 {CASES - len(FAILS)} / 失败 {len(FAILS)}")
    if FAILS:
        print("❌ FAIL:\n  - " + "\n  - ".join(FAILS))
        return 1
    print("✅ PASS —— 存储失败关闭测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
