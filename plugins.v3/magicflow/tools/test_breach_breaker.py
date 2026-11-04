#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 11.12.0 删除断言/熔断 + 违约自动核对 离线回归测试。

覆盖：
  A. 删除前「账单直查断言」``_delete_bill_assert``：state∈{active,breached} → 拦；settled/void/无账单 → 放。
  B. 删除熔断 ``_delete_breaker_check``：滚动窗口内累计超阈 → tripped（阻断整批）。
  C. 违约自动核对 ``_hrbills_breach_reconcile``：
     - 站点仍欠（hash 在 records）→ will_reseed；站点不欠 → will_void；
     - confirm=False 只出计划不落库；confirm=True 真清账 + 真补种；
     - **fail-closed**：站点对账 ok=False / 覆盖不完整 → 不动（unverified）。

用法：``python3 tools/test_breach_breaker.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_breach_breaker_test"


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
    """stub app.* + 叶子模块 → 再加载 common/deletegate/hrbills（与 test_silent_hr_split 同法）。"""
    for name, attr_map in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
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
            _load(PKG + ".features.deletegate", "features/deletegate.py"),
            _load(PKG + ".features.hrbills", "features/hrbills.py"))


common, persistence, deletegate, hrbills = _stub_and_load()

DeleteGateMixin = deletegate.DeleteGateMixin
HrBillsMixin = hrbills.HrBillsMixin
BILL_STATE_ACTIVE = hrbills.BILL_STATE_ACTIVE
BILL_STATE_BREACHED = hrbills.BILL_STATE_BREACHED
BILL_STATE_SETTLED = hrbills.BILL_STATE_SETTLED
BILL_STATE_VOID = hrbills.BILL_STATE_VOID

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


class Harness(HrBillsMixin, DeleteGateMixin):
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._hot = None
        self.reports = {}
        self.applied = []

    def get_data_path(self):
        return self._data_dir

    def _hr_reconcile_site(self, domain: str, snap=None):
        return self.reports.get(domain, {"site": domain, "ok": False, "error": "n/a"})

    def _hr_reconcile_apply(self, site, tids=None, confirm=None, save_path=""):
        self.applied.append({"site": site, "tids": list(tids or []), "confirm": bool(confirm)})
        return {"ok": True, "added": len(list(tids or []))}


def _bill(h, site, state):
    return {"site": site, "rule": "site_hr", "state": state, "need_h": 24.0, "seeded_h": 0.0,
            "fp": "", "title": "t", "opened_at": time.time(), "last_progress": 1.0,
            "last_progress_at": time.time(), "progress": 1.0, "opened_by": "open"}


def main() -> int:
    print("=" * 64)
    print("魔流 · 11.12.0 删除断言/熔断 + 违约自动核对 回归测试")
    print("=" * 64)
    tmp = tempfile.mkdtemp(prefix="breach_breaker_")
    h = Harness(Path(tmp))
    store = h._hrbills_store()

    # ---- 0) 常量 ----
    print("\n[0] 常量")
    _ok(common.DELETE_BREAKER_ENABLED is True, "DELETE_BREAKER_ENABLED 默认开")
    _ok(int(common.DELETE_BREAKER_MAX) > 0, f"DELETE_BREAKER_MAX={common.DELETE_BREAKER_MAX}")
    _ok(common.DELETE_BILL_ASSERT is True, "DELETE_BILL_ASSERT 默认开")
    _ok(common.HR_BREACH_RECONCILE_ENABLED is True, "HR_BREACH_RECONCILE_ENABLED 默认开")

    # ---- A) 账单直查断言 ----
    print("\n[A] 删除前账单直查断言")
    store.put("a1", _bill("a1", "assert.net", BILL_STATE_ACTIVE))
    store.put("b1", _bill("b1", "assert.net", BILL_STATE_BREACHED))
    store.put("s1", _bill("s1", "assert.net", BILL_STATE_SETTLED))
    store.put("v1", _bill("v1", "assert.net", BILL_STATE_VOID))
    why = h._delete_bill_assert(["a1", "b1", "s1", "v1", "none"])
    _ok("a1" in why, "active 账单 → 拦")
    _ok("b1" in why, "breached 账单 → 拦")
    _ok("s1" not in why, "settled 账单 → 放")
    _ok("v1" not in why, "void 账单 → 放")
    _ok("none" not in why, "无账单 → 放")
    _ok(h._delete_bill_assert([]) == {}, "空输入 → {}")

    # ---- B) 删除熔断 ----
    print("\n[B] 删除滚动窗口熔断")
    deletegate._DELETE_WINDOW.clear()
    mx = int(common.DELETE_BREAKER_MAX)
    blocked, info = h._delete_breaker_check([f"x{i}" for i in range(mx)], reason="t", source="test")
    _ok(blocked == set() and info.get("tripped") is False, f"首批 {mx} 个（≤上限）→ 放行")
    blocked2, info2 = h._delete_breaker_check(["y0"], reason="t", source="test")
    _ok(blocked2 == {"y0"} and info2.get("tripped") is True,
        f"窗口内再删 1 个（累计 {mx + 1} > {mx}）→ 熔断，整批拦")
    deletegate._DELETE_WINDOW.clear()
    blocked3, _ = h._delete_breaker_check(["z0"], reason="t", source="test")
    _ok(blocked3 == set(), "清空窗口后 → 恢复放行")

    # ---- B2) ★ 19.10.5 熔断补记：预占 → 按实删数归还 ----
    print("\n[B2] 熔断补记（预占 / 归还 / 幂等）")
    _W = deletegate._DELETE_WINDOW
    _T = deletegate._DELETE_WINDOW_TICKETS
    _W.clear()
    _T.clear()

    # 1) 预占后窗口 = 申请量，且拿到票根
    _b0, _i0 = h._delete_breaker_check([f"p{i}" for i in range(10)], reason="t", source="test")
    _ok(len(_W) == 10, "预占 10 → 窗口=10")
    _ok(int(_i0.get("ticket") or 0) > 0, "通过时返回 ticket（供事后归还）")

    # 2) 实删满额 → 归还 0
    _ok(h._delete_breaker_settle(_i0["ticket"], 10) == 0, "实删 10/10 → 归还 0")
    _ok(len(_W) == 10, "实删满额 → 窗口不变")

    # 3) 整批被拦（settle(...,0)）→ 全额归还
    _b1, _i1 = h._delete_breaker_check([f"q{i}" for i in range(8)], reason="t", source="test")
    _ok(len(_W) == 18, "再预占 8 → 窗口=18")
    _ok(h._delete_breaker_settle(_i1["ticket"], 0) == 8, "整批被 gate/bill 拦下 → 归还 8")
    _ok(len(_W) == 10, "归还后窗口回到 10（不再虚高）")

    # 4) 部分失败：预占 8、实删 5 → 只占 5
    _b2, _i2 = h._delete_breaker_check([f"r{i}" for i in range(8)], reason="t", source="test")
    _ok(h._delete_breaker_settle(_i2["ticket"], 5) == 3, "预占 8 实删 5 → 归还 3")
    _ok(len(_W) == 15, "窗口=10+5（只记实删）")

    # 5) 幂等：同一 ticket 重复结算不得多还
    _ok(h._delete_breaker_settle(_i2["ticket"], 5) == 0, "重复结算 → 幂等（归还 0）")
    _ok(len(_W) == 15, "幂等后窗口不变")

    # 6) 非法 / 未知 ticket 容错
    _ok(h._delete_breaker_settle(0, 0) == 0, "ticket=0 → 无操作")
    _ok(h._delete_breaker_settle(999999, 0) == 0, "未知 ticket → 无操作")
    _ok(h._delete_breaker_settle("bad", 0) == 0, "非法 ticket → 无操作")

    # 7) ★ 缺陷 A 核心回归：整批申请但实删 0 → 下一批不该被误熔断
    _W.clear()
    _T.clear()
    _b3, _i3 = h._delete_breaker_check([f"s{i}" for i in range(mx)], reason="t", source="test")
    h._delete_breaker_settle(_i3["ticket"], 0)          # 一个都没真删
    _b4, _i4 = h._delete_breaker_check(["slast"], reason="t", source="test")
    _ok(_b4 == set() and _i4.get("tripped") is False,
        "★ 缺陷 A 回归：整批申请实删 0 → 下一批不被误熔断")

    # 8) ★ 反向：实删满额后仍然会熔断（补记不能削弱保护）
    _W.clear()
    _T.clear()
    _b5, _i5 = h._delete_breaker_check([f"t{i}" for i in range(mx)], reason="t", source="test")
    h._delete_breaker_settle(_i5["ticket"], mx)         # 全部真删
    _b6, _i6 = h._delete_breaker_check(["tlast"], reason="t", source="test")
    _ok(_b6 == {"tlast"} and _i6.get("tripped") is True,
        "★ 反向：实删满额 → 仍然熔断（补记不得削弱保护）")

    # 9) 并发：两线程各申请 mx 个，至少一个被熔断（check-and-reserve 原子）
    import threading as _th
    _W.clear()
    _T.clear()
    _res = []

    def _race():
        _bb, _ii = h._delete_breaker_check([f"c{i}" for i in range(mx)], reason="t", source="test")
        _res.append(bool(_ii.get("tripped")))

    _ths = [_th.Thread(target=_race) for _ in range(2)]
    for _x in _ths:
        _x.start()
    for _x in _ths:
        _x.join()
    _ok(sum(1 for _r in _res if _r) >= 1,
        "并发下至少一批被熔断（check-and-reserve 原子）")
    _W.clear()
    _T.clear()

    # ---- C) 违约自动核对 ----
    print("\n[C] 违约自动核对（站点不欠→清账 / 站点欠→补种）")
    store.put("w1", _bill("w1", "carpt.net", BILL_STATE_BREACHED))   # 站点不欠 → 清账
    store.put("w2", _bill("w2", "carpt.net", BILL_STATE_BREACHED))   # 站点仍欠 → 补种
    h.reports["carpt.net"] = {
        "site": "carpt.net", "ok": True, "hash_coverage_complete": True,
        "records": [{"tid": "209930", "infohash": "w2", "resolved": True, "in_qb": False}],
    }
    dry = h._hrbills_breach_reconcile(site="carpt.net")
    _ok(dry["dry_run"] is True, "默认干跑")
    _ok(dry["totals"]["breached"] == 2, f"识别 2 张 breached（实际 {dry['totals']['breached']}）")
    s0 = dry["sites"][0]
    _ok(set(s0["will_void"]) == {"w1"} and set(s0["will_reseed"]) == {"w2"},
        "站点不欠 w1 → 清账；站点仍欠 w2 → 补种")
    _ok(store.get("w1")["state"] == BILL_STATE_BREACHED, "干跑不落库（w1 仍 breached）")

    res = h._hrbills_breach_reconcile(site="carpt.net", confirm=True)
    _ok(res["totals"]["voided"] == 1, f"confirm 清账 1 张（实际 {res['totals']['voided']}）")
    _ok(store.get("w1") is None, "w1 清账 → 账单已删除（作废即删）")
    _ok(any(a["site"] == "carpt.net" and a["tids"] == ["209930"] and a["confirm"]
            for a in h.applied), "站点仍欠 w2 → 调 _hr_reconcile_apply(tids=[209930], confirm=True)")

    # fail-closed：站点对账失败/覆盖不完整 → 不动
    print("\n[C2] fail-closed（站点数据不可信 → 不动）")
    store.put("w3", _bill("w3", "hdtime.org", BILL_STATE_BREACHED))
    h.reports["hdtime.org"] = {"site": "hdtime.org", "ok": False, "error": "网络超时"}
    r2 = h._hrbills_breach_reconcile(site="hdtime.org", confirm=True)
    _ok(r2["sites"][0]["verified"] is False and r2["totals"]["unverified"] == 1,
        "对账 ok=False → verified=False（unverified=1）")
    _ok(store.get("w3")["state"] == BILL_STATE_BREACHED, "站点不可信 → 绝不动账（w3 仍 breached）")
    h.reports["hdtime.org"] = {"site": "hdtime.org", "ok": True, "hash_coverage_complete": False,
                               "records": []}
    r3 = h._hrbills_breach_reconcile(site="hdtime.org", confirm=True)
    _ok(r3["sites"][0]["verified"] is False, "覆盖不完整 → verified=False（不误判「站点不欠」）")
    _ok(store.get("w3")["state"] == BILL_STATE_BREACHED, "覆盖不完整 → 绝不动账")

    print("\n" + "=" * 64)
    print(f"PASS：{CHECKS} 项断言全部通过 ✅")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"\n{e}")
        raise SystemExit(1)
