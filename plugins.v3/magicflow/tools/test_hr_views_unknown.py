#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 113（N-04）：视图层 UNKNOWN 不得折成「正常空表」。

纯离线：桩掉 tags / hrbills / sitereport / norm，加载真实 ``features/reportview.py``。
覆盖：
  - ``hr_store_state_of``：FOUND / UNKNOWN 的字段与 degraded_reason；
  - ``view_hr``：payload 必带 store_status / store_error / store_backend / degraded_reason，
    UNKNOWN 时仍返回结构完整的数据（视图不 500、不改变账单）；
  - 静态约束：reportview 用 ``all_result``（不直接 ``all()`` 折空）、agentapi 用 ``get_result``。

用法：``python3 tools/test_hr_views_unknown.py``（0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_t113_views"
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


def _load():
    _mod("app")
    _mod("app.schemas", Response=type("Response", (), {}))
    _mod("app.sdk")
    _mod("app.sdk.logging", logger=type("L", (), {
        "warning": staticmethod(lambda *a, **k: None),
        "info": staticmethod(lambda *a, **k: None),
        "error": staticmethod(lambda *a, **k: None)})())
    pkg = _mod(PKG)
    pkg.__path__ = [str(ROOT)]
    _mod(PKG + ".tags",
         EXTERNAL_TAG="外部", RESCUE_TAG="救援",
         STATE_BONUS="魔力", STATE_BRUSH="刷流", STATE_CLAIM="认领",
         STATE_HR="保种", STATE_KEEP="保种", STATE_SILENT="静默",
         STATES=("刷流", "魔力", "保种", "静默"),
         SUB_NEW="新", SUB_PLAIN="普通", SUB_RESOURCE="资源",
         identity_of=lambda *a, **k: "", is_reuse_copy=lambda *a, **k: False)
    _mod(PKG + ".features.hrbills",
         BILL_STATE_ACTIVE="active", BILL_STATE_BREACHED="breached",
         BILL_STATE_PENDING="pending", BILL_STATE_SETTLED="settled",
         BILL_STATE_VOID="void", HR_MANUAL_SETTLE="manual",
         RULE_HIT_AND_RUN="hit_and_run", RULE_SITE_HR="site_hr")
    _mod(PKG + ".features.sitereport",
         BUCKET_BONUS="魔力", BUCKET_BRUSH="刷流", BUCKET_EXTERNAL="外部",
         BUCKET_HR="保种", BUCKET_RESCUE="救援", BUCKET_SILENT="静默",
         MAX_ITEMS=500, ORIGIN_NONE="", ORIGIN_POOL="pool", ORIGIN_RESEED="reseed",
         SILENT_SUBS=("静默",), TRANSPORT_DOWNLOADING="下载中",
         TRANSPORT_PAUSED="暂停", TRANSPORT_SEEDING="做种中",
         _BUCKET_ORDER=("魔力", "刷流", "保种", "静默"), _ORIGIN_ORDER=("",))
    _mod(PKG + ".norm", now_iso=lambda: "2026-11-07T21:00:00+08:00")
    _mod(PKG + ".features")
    spec = importlib.util.spec_from_file_location(
        PKG + ".features.reportview", ROOT / "features/reportview.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG + ".features.reportview"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    rv = _load()

    print("── A. hr_store_state_of ──")
    st = rv.hr_store_state_of({})
    _ok(st["store_status"] == "found", "A1 无三态信息 → 向后兼容按 found", str(st))
    st = rv.hr_store_state_of({"bill_store_status": "unknown",
                               "bill_store_error": "OperationalError: boom"})
    _ok(st["store_status"] == "unknown" and st["degraded_reason"] == "store_unknown",
        "A2 UNKNOWN → degraded_reason=store_unknown", str(st))
    _ok("boom" in st["store_error"], "A3 UNKNOWN → 保留错误文本（截断）", str(st))
    st = rv.hr_store_state_of({"bill_store_status": "found",
                               "store_meta_fn": lambda: {"backend": "pg",
                                                         "degraded_reason": ""}})
    _ok(st["store_backend"] == "pg" and st["degraded_reason"] == "",
        "A4 found → 带后端信息", str(st))
    st = rv.hr_store_state_of({"bill_store_status": "unknown",
                               "store_meta_fn": lambda: {"backend": "json",
                                                         "degraded_reason": "json_has_unmerged_data"}})
    _ok(st["degraded_reason"] == "json_has_unmerged_data", "A5 降级原因优先用 meta", str(st))

    print("── B. view_hr payload 带三态 ──")
    ctx = {"sites": [], "bills": {}, "bill_events": [], "bill_store_status": "unknown",
           "bill_store_error": "db down",
           "store_meta_fn": lambda: {"backend": "json", "degraded_reason": "probe:db down"}}
    out = rv.view_hr(ctx)
    _ok(out.get("store_status") == "unknown", "B1 view_hr 暴露 store_status=unknown", str(out.get("store_status")))
    _ok(out.get("store_error") == "db down", "B2 view_hr 暴露 store_error")
    _ok(out.get("store_backend") == "json", "B3 view_hr 暴露 store_backend")
    _ok(out.get("degraded_reason") == "probe:db down", "B4 view_hr 暴露 degraded_reason")
    _ok(out.get("totals", {}).get("sites") == 0 and isinstance(out.get("sites"), list),
        "B5 UNKNOWN 时仍返回结构完整的数据（不 500）")
    _ok(rv.view_hr({"sites": [], "bills": {}}).get("store_status") == "found",
        "B6 无三态 ctx（旧夹具）→ found，向后兼容")

    print("── C. 源码静态约束 ──")
    src = (ROOT / "features/reportview.py").read_text(encoding="utf-8")
    _ok("bstore.all_result()" in src, "C1 reportview 用 all_result 取账单")
    _ok('"store_status": _store_status' in src, "C2 view_hr 返回 store_status")
    _ok("hr_store_state_of" in src, "C3 三态转换集中在 hr_store_state_of")
    ag = (ROOT / "features/agentapi.py").read_text(encoding="utf-8")
    _ok("_bstore.get_result(h)" in ag, "C4 agentapi 删除解释用 get_result")
    _ok('entry["verdict"] = "degraded"' in ag, "C5 UNKNOWN 不给 delete_candidate")
    _ok('"rule": "hr/bill_store"' in ag or '"hr/bill_store_invisible"' in ag,
        "C6 解释链带 hr/bill_store 证据")

    print()
    if FAILS:
        print(f"❌ FAIL —— {len(FAILS)}/{CASES} 条失败：")
        for f in FAILS:
            print("   -", f)
        return 1
    print(f"✅ PASS —— {CASES} 项断言全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
