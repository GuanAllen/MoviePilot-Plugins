#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 105 / HR-04 H&R 临期通知准入闸门 离线回归测试。

覆盖（全部离线、纯函数、不连库、不 import 插件主类）：
  A. 幽灵账单：settled / void / breached / 未知 state 一律不进临期通知。
  B. 达标闸门：active 但 ``seeded_h >= need_h + margin`` → 不进；余量边界。
  C. 真实临期：active 的 at_risk、或 ``hours_left <= 阈值`` → 必须进（不放宽）。
  D. pending：只有后端明确 at_risk 才进；否则不拿默认窗口算出的 hours_left 报警。
  E. 数据缺失：字段缺/不可转数字时不擅自抑制（保守保留）；state 缺失按未知排除。
  F. 排序与截断：hours_left 升序、None 排最后、上限 20。
  G. 只读性：不修改入参账单，输出字段与原 notify 一致。

用法：``python3 tools/test_hr_notify_gate.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import copy
import importlib.util
import sys
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


def _load_gate():
    spec = importlib.util.spec_from_file_location("mf_hrnotify_gate", ROOT / "features/hrnotify_gate.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def bill(state, seeded, need, hours_left, risk=False, title="t", **extra):
    d = {"state": state, "seeded_h": seeded, "need_h": need, "hours_left": hours_left,
         "at_risk": risk, "title": title}
    d.update(extra)
    return d


def main() -> int:
    g = _load_gate()
    print("── A. 幽灵/终态账单不进临期通知 ──")
    ghosts = [bill("settled", 881.71, 24.0, -238.33) for _ in range(13)]
    ghosts += [bill("settled", 458.56, 20.0, -22.33) for _ in range(5)]
    _ok(len(ghosts) == 18, "用例构造：18 条 settled 已结清账单", str(len(ghosts)))
    got = g.deadline_candidates(ghosts, "carpt.net", limit_hours=24.0, margin_hours=2.0)
    _ok(got == [], "18 条 settled 幽灵全部被拦", str(len(got)))
    _ok(g.deadline_candidate(bill("void", 0.0, 24.0, -100.0), "x", 24.0, 2.0) is None, "void 被拦")
    _ok(g.deadline_candidate(bill("breached", 1.0, 24.0, -5.0, risk=True), "x", 24.0, 2.0) is None,
        "breached 被拦（已违约语义走账单面板，不混进临期）")
    _ok(g.deadline_candidate(bill("", 0.0, 24.0, 1.0), "x", 24.0, 2.0) is None, "state 缺失按未知排除")
    _ok(g.deadline_candidate(bill("settled", 0.0, 24.0, 1.0, risk=True), "x", 24.0, 2.0) is None,
        "settled 即使 at_risk=True 也不进")

    print("── B. 达标闸门（seeded >= need + margin） ──")
    _ok(g.deadline_candidate(bill("active", 26.0, 24.0, -1.0), "x", 24.0, 2.0) is None, "刚好达标 24+2 被拦")
    _ok(g.deadline_candidate(bill("active", 25.9, 24.0, 0.5), "x", 24.0, 2.0) is not None,
        "25.9h < 26h 且剩 0.5h → 进（达标闸门没放宽）")
    _ok(g.deadline_candidate(bill("active", 26.0, 24.0, 100.0), "x", 24.0, 2.0) is None,
        "达标 + 还早 → 拦（双闸门同时成立也只会被拦一次）")

    print("── C. 真实临期必须进（不能为了压噪音放宽） ──")
    active_real = bill("active", 22.60, 24.0, 0.04, risk=True, title="真临期")
    _ok(g.deadline_candidate(active_real, "carpt.net", 24.0, 2.0) is not None, "active at_risk 进")
    _ok(g.deadline_candidate(bill("active", 10.0, 24.0, 20.0), "x", 24.0, 2.0) is not None,
        "active 未达标且 hours_left=20<=24 进（阈值逻辑保持）")
    _ok(g.deadline_candidate(bill("active", 10.0, 24.0, 24.0), "x", 24.0, 2.0) is not None,
        "边界 hours_left == 阈值 进（原逻辑 <= 才 continue）")
    _ok(g.deadline_candidate(bill("active", 10.0, 24.0, 25.0), "x", 24.0, 2.0) is None,
        "active 未达标但 25h > 24h → 不进（原逻辑继续）")
    _ok(g.deadline_candidate(bill("active", 10.0, 24.0, None, risk=True), "x", 24.0, 2.0) is not None,
        "at_risk 且 hours_left=None → 进（原逻辑：risk 优先）")

    print("── D. pending 只信 at_risk ──")
    _ok(g.deadline_candidate(bill("pending", 0.0, 24.0, 5.0, risk=False), "x", 24.0, 2.0) is None,
        "pending 未 at_risk（默认窗口算出的 hours_left）→ 不进")
    _ok(g.deadline_candidate(bill("pending", 0.0, 24.0, 5.0, risk=True), "x", 24.0, 2.0) is not None,
        "pending at_risk → 进")
    _ok(g.deadline_candidate(bill("pending", 30.0, 24.0, -50.0, risk=True), "x", 24.0, 2.0) is None,
        "pending 已达标（进度没刷新）→ 不进")

    print("── E. 数据缺失保守处理 ──")
    _ok(g.deadline_candidate(bill("active", None, 24.0, 3.0), "x", 24.0, 2.0) is not None,
        "seeded_h 缺失不擅自抑制（无法证明达标）")
    _ok(g.deadline_candidate(bill("active", 30.0, None, 3.0), "x", 24.0, 2.0) is not None,
        "need_h 缺失不擅自抑制")
    _ok(g.deadline_candidate({"state": "active", "seeded_h": "abc", "need_h": "x", "hours_left": "1"},
                             "x", 24.0, 2.0) is not None, "字段不可转数字不抛异常、保守保留")
    _ok(g.deadline_candidate(bill("active", 0.0, 24.0, "bad"), "x", 24.0, 2.0) is None,
        "hours_left 不可转数字且非 at_risk → 不进（原逻辑同口径）")

    print("── F. 排序 / 截断 / 只读 ──")
    many = [bill("active", 0.0, 24.0, float(i), risk=True, title=f"b{i}") for i in range(25)]
    picked = g.deadline_candidates(many, "x", 24.0, 2.0)
    _ok(len(picked) == 20, "25 条候选截断到 20", str(len(picked)))
    _ok(picked[0]["title"] == "b0" and picked[-1]["title"] == "b19", "按 hours_left 升序")
    mixed = [bill("active", 0.0, 24.0, None, risk=True, title="none"),
             bill("active", 0.0, 24.0, 3.0, risk=True, title="three")]
    ranked = g.rank_candidates(mixed)
    _ok([x["title"] for x in ranked] == ["three", "none"], "None 排最后")
    snapshot = copy.deepcopy(many)
    g.deadline_candidates(many, "x", 24.0, 2.0)
    _ok(many == snapshot, "不修改入参账单（只读）")
    one = g.deadline_candidate(active_real, "carpt.net", 24.0, 2.0)
    _ok(set(one) == {"site", "title", "hours_left", "need_h", "seeded_h", "state"},
        "输出字段与 notify_check_hr 原口径一致", str(sorted(one)))

    print(f"\n{'✅ PASS' if not FAILS else '❌ FAIL'} —— {CASES - len(FAILS)}/{CASES} 通过")
    if FAILS:
        print("失败项：" + "；".join(FAILS))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
