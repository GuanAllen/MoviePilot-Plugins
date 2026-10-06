#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 11.13.0 H&R 安全垫 + 临近到期预警 离线回归测试。

覆盖：
  A. 常量默认：``HR_SEED_MARGIN_HOURS_DEFAULT`` / ``HR_DEADLINE_WARN_HOURS_DEFAULT``。
  B. 策略旋钮 ``_hr_margin_hours`` / ``_hr_warn_hours``：默认值 / 覆盖 / 负数钳 0。
  C. 到期推导 ``_hr_deadline``：无窗口 → 不预警；临近 → at_risk；还早 → 不预警；
     已达标（≥ need+margin）→ 不预警；settled/void → 不预警；逾期 → 仍预警。
  D. 结清判定接入安全垫：``_hrbills_tick`` 用 ``need_h + _hr_margin_hours()``（AST 守卫）。
  E. 站点窗口取值链 ``_crossseed_seed_window_hours``（规则库 seed_window_hours → seed_hours）。

用法：``python3 tools/test_hr_margin_deadline.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_hr_margin_test"


def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")


def _stub_and_load():
    for name, attr_map in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
        ("app.sdk.logging", {"logger": types.SimpleNamespace(**{k: (lambda *a, **kw: None) for k in
            ("info", "warning", "error", "debug", "exception")})}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        m.__path__ = []  # 允许其子模块继续 import
        for k, v in attr_map.items():
            setattr(m, k, v)
    for modname, attrs in (
        ("bonus", ("TorrentBonusInfo", "calc_bonus_per_hour")),
        ("fetcher", ("SiteCandidateTorrent",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    _load(PKG + ".fingerprint", "fingerprint.py")
    return (_load(PKG + ".common", "common.py"),
            _load(PKG + ".persistence", "persistence.py"),
            _load(PKG + ".features.hrbills", "features/hrbills.py"))


common, persistence, hrbills = _stub_and_load()

HrBillsMixin = hrbills.HrBillsMixin
BILL_STATE_ACTIVE = hrbills.BILL_STATE_ACTIVE
BILL_STATE_PENDING = hrbills.BILL_STATE_PENDING
BILL_STATE_SETTLED = hrbills.BILL_STATE_SETTLED
BILL_STATE_VOID = hrbills.BILL_STATE_VOID

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


class Harness(HrBillsMixin):
    """只测纯推导：窗口固定 240h（不依赖 crossseed 模块）。"""

    def __init__(self, data_dir: Path, window: float = 240.0):
        self._data_dir = data_dir
        self._hot = None
        self._window = window

    def get_data_path(self):
        return self._data_dir

    def _hr_window_hours(self, dom: str) -> float:
        return float(self._window)


def _bill(site, state, *, opened_h_ago=0.0, need_h=24.0, seeded_h=0.0, margin=2.0):
    return {"site": site, "rule": "site_hr", "state": state, "need_h": need_h,
            "seeded_h": seeded_h, "opened_at": time.time() - opened_h_ago * 3600.0,
            "title": "t", "progress": 1.0, "last_progress": 1.0,
            "last_progress_at": time.time()}


def main() -> int:
    print("=" * 64)
    print("魔流 · 11.13.0 H&R 安全垫 + 临近到期预警 回归测试")
    print("=" * 64)
    tmp = tempfile.mkdtemp(prefix="hr_margin_")
    h = Harness(Path(tmp))

    # ---- 0) 常量 ----
    print("\n[0] 常量默认")
    _ok(float(common.HR_SEED_MARGIN_HOURS_DEFAULT) == 2.0,
        f"HR_SEED_MARGIN_HOURS_DEFAULT={common.HR_SEED_MARGIN_HOURS_DEFAULT}")
    _ok(float(common.HR_DEADLINE_WARN_HOURS_DEFAULT) == 48.0,
        f"HR_DEADLINE_WARN_HOURS_DEFAULT={common.HR_DEADLINE_WARN_HOURS_DEFAULT}")

    # ---- A) 策略旋钮 ----
    print("\n[A] 策略旋钮（默认/覆盖/钳位）")
    _ok(h._hr_margin_hours() == 2.0, "margin 默认 2.0")
    _ok(h._hr_warn_hours() == 48.0, "warn 默认 48.0")
    h._hr_seed_margin_hours = 6.5
    h._hr_deadline_warn_hours = 12.0
    _ok(h._hr_margin_hours() == 6.5, "margin 覆盖生效")
    _ok(h._hr_warn_hours() == 12.0, "warn 覆盖生效")
    h._hr_seed_margin_hours = -3.0
    h._hr_deadline_warn_hours = "abc"
    _ok(h._hr_margin_hours() == 0.0, "margin 负数 → 钳 0")
    _ok(h._hr_warn_hours() == 48.0, "warn 非数 → 回默认")
    h._hr_seed_margin_hours = 2.0
    h._hr_deadline_warn_hours = 48.0

    # ---- B) 到期推导 ----
    print("\n[B] 到期推导 _hr_deadline")
    d = h._hr_deadline(_bill("x.net", BILL_STATE_ACTIVE, opened_h_ago=1.0))
    _ok(d["due_h"] == 26.0, f"due_h = need 24 + margin 2 = {d['due_h']}")
    _ok(d["at_risk"] is False, "刚开账（剩 ~239h）→ 不预警")
    _ok(238.9 < float(d["hours_left"]) <= 240.0, f"hours_left≈239（实际 {d['hours_left']}）")

    d = h._hr_deadline(_bill("x.net", BILL_STATE_ACTIVE, opened_h_ago=239.0))
    _ok(d["at_risk"] is True, "距到期 1h 且未达标 → at_risk")
    d = h._hr_deadline(_bill("x.net", BILL_STATE_ACTIVE, opened_h_ago=193.0))
    _ok(d["at_risk"] is True, "距到期 47h（<48）→ at_risk")
    d = h._hr_deadline(_bill("x.net", BILL_STATE_ACTIVE, opened_h_ago=250.0))
    _ok(d["at_risk"] is True and float(d["hours_left"]) < 0, "已逾期且未达标 → 仍预警")

    d = h._hr_deadline(_bill("x.net", BILL_STATE_ACTIVE, opened_h_ago=239.0, seeded_h=26.5))
    _ok(d["at_risk"] is False, "已达标（seeded 26.5 ≥ due 26）→ 不预警")
    d = h._hr_deadline(_bill("x.net", BILL_STATE_ACTIVE, opened_h_ago=239.0, seeded_h=25.0))
    _ok(d["at_risk"] is True, "差一点（25 < 26）→ 预警（安全垫生效）")
    for st in (BILL_STATE_SETTLED, BILL_STATE_VOID):
        d = h._hr_deadline(_bill("x.net", st, opened_h_ago=239.0))
        _ok(d["at_risk"] is False, f"state={st} → 不预警")
    d = h._hr_deadline(_bill("x.net", BILL_STATE_PENDING, opened_h_ago=239.0))
    _ok(d["at_risk"] is True, "pending 也会预警")
    h2 = Harness(Path(tmp), window=0.0)
    d = h2._hr_deadline(_bill("x.net", BILL_STATE_ACTIVE, opened_h_ago=239.0))
    _ok(d["at_risk"] is False and d["deadline_at"] is None, "无窗口信息 → 不预警")

    # ---- C) 结清判定接入安全垫（AST 守卫）----
    print("\n[C] 结清判定接入安全垫（源码守卫）")
    src = (ROOT / "features" / "hrbills.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found_due = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_hrbills_tick":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Compare):
                    seg = ast.get_source_segment(src, sub) or ""
                    if "due_h" in seg:
                        found_due.append(seg)
    _ok(any("seeded_h >= due_h" in s for s in found_due),
        f"tick 结清用 seeded_h >= due_h（实际 {found_due}）")
    _ok("_hr_margin_hours()" in src, "hrbills 定义/使用 _hr_margin_hours()")
    _ok("need_h + self._hr_margin_hours()" in src, "due_h = need_h + margin")

    # ---- D) 站点窗口取值链 ----
    print("\n[D] 站点窗口取值链 _crossseed_seed_window_hours")
    import re as _re
    _src = (ROOT / "features" / "crossseed.py").read_text(encoding="utf-8")
    _tree = ast.parse(_src)
    _fn = next(n for n in ast.walk(_tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_crossseed_seed_window_hours")
    _builtin = {"zzz-builtin.net": {"seed_window_hours": 336.0},
                "zzz-builtin2.net": {"seed_hours": 72.0}}
    _ns: dict = {"re": _re, "BUILTIN_RULES": _builtin}
    exec(compile(ast.Module(body=[_fn], type_ignores=[]), "<x>", "exec"), _ns)
    _win_of = _ns["_crossseed_seed_window_hours"]

    class CS:
        def __init__(self, rules):
            self._rules = rules or {}

        def _site_rules(self):
            return self._rules

    class _Rules(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)

    _ok(_win_of(CS(_Rules({"a.net": {"seed_window_hours": 240.0, "seed_hours": 999.0}})), "a.net") == 240.0,
        "优先 seed_window_hours")
    _ok(_win_of(CS(_Rules({"b.net": {"seed_hours": 120.0}})), "b.net") == 120.0, "回退 seed_hours")
    _ok(_win_of(CS(_Rules({"c.net": {"seed_hours": 0.0}})), "c.net") == 0.0, "无窗口 → 0")
    _ok(_win_of(CS(_Rules({})), "zzz-builtin.net") == 336.0, "内置表 seed_window_hours 回退")
    _ok(_win_of(CS(_Rules({})), "zzz-builtin2.net") == 72.0, "内置表 seed_hours 回退")
    _ok(_win_of(CS(_Rules({})), "zzz-nope.net") == 0.0, "未知域 → 0")

    print("\n" + "=" * 64)
    print(f"✅ PASS（{CHECKS} 项断言）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)
