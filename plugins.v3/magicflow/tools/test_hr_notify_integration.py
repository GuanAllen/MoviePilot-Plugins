#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 105 / HR-04 集成回归：``notify_check_hr`` 必须走准入闸门。

纯离线：用桩模块替代 ``app.*`` / kvstore / models / trend，加载真实 ``features/notify.py``，
用合成账单验证：
  A. settled / void / breached / 未达标之外的 pending 幽灵不进通知。
  B. 真实 active 临期仍被发现（at_risk 或 hours_left ≤ 阈值）。
  C. 只读：不修改账单 dict、不回写状态。
  D. 输出 shape 与历史一致（site/title/hours_left/need_h/seeded_h/state），供消息拼装使用。

用法：``python3 tools/test_hr_notify_integration.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import copy
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_t105_notify"
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


def _mod(name, **attrs):
    m = sys.modules.get(name) or types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _load_notify():
    # app.* 桩
    _mod("app")
    _mod("app.schemas", Response=type("Response", (), {"__init__": lambda self, success=True,
                                                       message="", data=None: (
        setattr(self, "success", success), setattr(self, "message", message),
        setattr(self, "data", data))[-1]}))
    _mod("app.sdk")
    _mod("app.sdk.logging", logger=type("L", (), {"warning": staticmethod(lambda *a, **k: None),
                                                  "info": staticmethod(lambda *a, **k: None),
                                                  "error": staticmethod(lambda *a, **k: None)})())
    # 插件包桩
    pkg = _mod(PKG)
    pkg.__path__ = []
    _mod(PKG + ".kvstore", cache_get=lambda *a, **k: None, cache_set=lambda *a, **k: None)
    _mod(PKG + ".models", MagicFlowNotifyActPayload=type("P", (), {}))
    feats = _mod(PKG + ".features")
    feats.__path__ = [str(ROOT / "features")]
    _mod(PKG + ".features.trend", daily_load=lambda self: {})
    spec = importlib.util.spec_from_file_location(PKG + ".features.notify", ROOT / "features/notify.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG + ".features.notify"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def bill(state, seeded, need, hours_left, risk=False, title="t"):
    return {"title": title, "state": state, "seeded_h": seeded, "need_h": need,
            "hours_left": hours_left, "at_risk": risk}


def main() -> int:
    notify = _load_notify()
    print(f"加载 notify.py 成功（{len(dir(notify))} 个模块级名字）")

    items = [bill("settled", 881.71, 24.0, -238.33, title=f"ghost{i}") for i in range(13)]
    items += [bill("settled", 458.56, 20.0, -22.33, title=f"ghostb{i}") for i in range(5)]
    items += [bill("void", 0.0, 24.0, -100.0, title="void1")]
    items += [bill("breached", 1.0, 24.0, -5.0, risk=True, title="breach1")]
    items += [bill("pending", 0.0, 24.0, 5.0, risk=False, title="pend-no-risk")]
    items += [bill("pending", 0.0, 24.0, 5.0, risk=True, title="pend-risk")]
    items += [bill("active", 22.60, 24.0, 0.04, risk=True, title="real-active")]
    items += [bill("active", 10.0, 24.0, 20.0, title="active-20h")]
    items += [bill("active", 10.0, 24.0, 100.0, title="active-far")]
    items += [bill("active", 30.0, 24.0, -2.0, title="active-attained")]

    class Stub:
        _hr_seed_margin_hours = 2.0

        def get_hr_bills(self, site="", live=0):
            return types.SimpleNamespace(data={"sites": [
                {"name": "carpt.net", "items": items},
                {"name": "btschool.club", "items": []},
            ]})

    stub = Stub()
    snapshot = copy.deepcopy(items)
    out = notify.NotifyMixin.notify_check_hr(stub, {"hr_hours": 24})

    print("── A. 幽灵/终态不进 ──")
    titles = [r["title"] for r in out]
    _ok(not any(t.startswith("ghost") for t in titles), "18 条 settled 幽灵全部被拦", str(titles))
    _ok("void1" not in titles, "void 被拦")
    _ok("breach1" not in titles, "breached 被拦（已违约走账单面板）")
    _ok("pend-no-risk" not in titles, "pending 且无 at_risk 被拦")
    _ok("active-attained" not in titles, "已达标 active 被拦")

    print("── B. 真实临期仍被发现 ──")
    _ok("real-active" in titles, "active at_risk 被发现")
    _ok("active-20h" in titles, "active hours_left=20 ≤ 24 被发现")
    _ok("pend-risk" in titles, "pending 但后端 at_risk → 保留（不误杀真实风险）")
    _ok("active-far" not in titles, "active 且 100h 远 → 不进")

    print("── C. 只读 ──")
    _ok(items == snapshot, "不修改账单 dict / 状态 / 结清证据")

    print("── D. 输出口径 ──")
    _ok(all(set(r) == {"site", "title", "hours_left", "need_h", "seeded_h", "state"} for r in out),
        "每条输出字段与消息拼装口径一致")
    _ok(all(r["site"] == "carpt.net" for r in out), "site 名透传")
    _ok([r["hours_left"] for r in out][:2] == sorted(r["hours_left"] for r in out)[:2],
        "hours_left 升序（消息取前 10 才是最紧急的）")

    print(f"\n{'✅ PASS' if not FAILS else '❌ FAIL'} —— {CASES - len(FAILS)}/{CASES} 通过")
    if FAILS:
        print("失败项：" + "；".join(FAILS))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
