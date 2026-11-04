#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 站点规则自动探测节拍离线回归（★ 19.10.9，真跑 common.py + features/siteops.py）。

背景（Master 2026-10-27「自动获取规则好像有问题」）：
  规则服务原先直接挂 ``interval = 7*24*60`` 分钟。APScheduler 的 interval 首轮 =
  「注册时刻 + 一整个周期」，而魔流每次部署/热重载都会「移除 + 重新注册」服务 →
  定时器被反复归零。实测 17 小时内 **157 次重载、0 次探测**，规则库永远停在旧值
  （CARPT 一直「无 H&R 判据」就是这么来的）。

修法：调度只负责**节拍**（每 ``RULES_TICK_MINUTES`` 醒一次），是否真探由持久化的
``rules_probe_state['at']`` 门控；失败按 30min→6h 指数退避。

断言：
  [1] 从未探测过 → 探一次并记账（at>0、fail 清零）；
  [2] 刚成功过（未到周期）→ 不再探；
  [3] 超过一个周期 → 再探；
  [4] 一轮 0 站有结果（全是 skipped）→ **算失败**，不写 at（否则误记「已刷新」干等一周）；
  [5] 返回 success=False → 算失败；
  [6] 无站点结果（results 为空）→ 算失败；
  [7] 失败后退避期内 → 不再探；
  [8] 退避到期 → 会再探；
  [9] 失败次数累加，退避时长按 30min×2^(n-1) 增长且封顶 6h；
  [10] auto_refresh=False → 一次都不探；
  [11] 拿不到 worker 槽 → 不探、不记账（不能把「跳过」记成「已刷新」）；
  [11b] 并发互斥：进程内跨实例只有一把探测锁（实测 8 个重载并发探测 → 写库 deadlock）；
  [12] 源码护栏：core 服务注册用的是 RULES_TICK_MINUTES（不是 RULES_INTERVAL_MINUTES），
       且注册处调了 _rules_bootstrap_async。

用法：``python3 tools/test_rules_watch.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_ruleswatch_test"

FAILS: list = []


def ok(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ✓ {msg}")
    else:
        FAILS.append(msg)
        print(f"  ✗ {msg}")


class _Stub(types.ModuleType):
    """万能桩模块：任何属性/调用都是另一个 _Stub。"""

    def __getattr__(self, name):
        return _Stub(name)

    def __call__(self, *a, **k):
        return _Stub("_call")


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------- 桩 app.* 与兄弟模块
def _pkg(name: str) -> types.ModuleType:
    """建一个可当包的模块（带 __path__，子模块 import 才认）。"""
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = []
        sys.modules[name] = m
    return m


_pkg("app")
_pkg("app.schemas")
_pkg("app.sdk")
_pkg("app.db")
_pkg("app.db.oper")

for _n, _attrs in (
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": _Stub("EventType")}),
    ("app.sdk.logging", {"logger": _Stub("logger")}),
    ("app.sdk.events", {"eventmanager": _Stub("eventmanager"), "Event": type("Event", (), {})}),
    ("app.sdk.network", {"SitesHelper": _Stub("SitesHelper")}),
    ("app.db.oper.site", {"SiteOper": _Stub("SiteOper")}),
):
    _m = _pkg(_n)
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)

sys.modules[PKG] = types.ModuleType(PKG)
sys.modules[PKG].__path__ = [str(ROOT)]
_feat = types.ModuleType(PKG + ".features")
_feat.__path__ = [str(ROOT / "features")]
sys.modules[PKG + ".features"] = _feat

_rules = types.ModuleType(PKG + ".sites.rules")
_rules.BUILTIN_RULES = {}
_rules.SiteRules = _Stub("SiteRules")
_rules.framework_note = lambda *a, **k: ""
_rules.parse_hr_from_mail = lambda *a, **k: None
_rules.parser_for_framework = lambda *a, **k: None
sys.modules[PKG + ".sites.rules"] = _rules

_ff = _Stub(PKG + ".sites.formula_fetch")
_ff.fetch_site_formula = lambda *a, **k: _Stub("cap")
sys.modules[PKG + ".sites.formula_fetch"] = _ff

sys.modules[PKG + ".recommend"] = _Stub(PKG + ".recommend")
_ss = _Stub(PKG + ".sitestore")
_ss.get_site_store = lambda *a, **k: _Stub("store")
_ss.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
sys.modules[PKG + ".sitestore"] = _ss

_tags = types.ModuleType(PKG + ".tags")
_tags.MARK_REUSE = "魔流-辅种"
_tags.SUB_RESOURCE = "资源"
_tags.is_asset_tags = lambda *a, **k: False
_tags.is_library_asset = lambda *a, **k: False
sys.modules[PKG + ".tags"] = _tags

sys.modules[PKG + ".fingerprint"] = _Stub(PKG + ".fingerprint")

# 真跑 common.py（RULES_* 常量要真值），siteops 的 `..common` 指向它
common = _load(PKG + ".common", "common.py")
sys.modules[PKG + ".common"] = common
siteops = _load(PKG + ".features.siteops", "features/siteops.py")
SiteOpsMixin = siteops.SiteOpsMixin


class _Resp:
    def __init__(self, success=True, data=None, message=""):
        self.success = success
        self.data = data if data is not None else {}
        self.message = message


class Host(SiteOpsMixin):
    """最小宿主：只提供 rules_watch 用到的依赖。"""

    def __init__(self, state=None, resp=None, auto=True, slot=True):
        self._rules_cfg = {"auto_refresh": auto}
        self._state = dict(state or {})
        self._resp = resp if resp is not None else _Resp(
            data={"results": [{"domain": "carpt.net", "stored": {"hr": True}}]}
        )
        self._slot_free = slot
        self.calls = 0
        self.logs = []

    # --- 依赖桩 ---
    def get_data(self, key):
        return dict(self._state) if key == self.RULES_PROBE_STATE_KEY else None

    def save_data(self, key=None, value=None):
        if key == self.RULES_PROBE_STATE_KEY and isinstance(value, dict):
            self._state = dict(value)

    def _acquire_worker_slot(self, label=""):
        if not self._slot_free:
            return False
        self._slot_free = False
        return True

    def _release_worker_slot(self):
        self._slot_free = True

    def _log(self, msg, level="info"):
        self.logs.append((level, str(msg)))

    def probe_site_rules(self, site_id=0, persist=True):
        self.calls += 1
        return self._resp


NOW = time.time()
PERIOD = float(common.RULES_INTERVAL_MINUTES) * 60.0
print("魔流 · 站点规则探测节拍（★ 19.10.9）")

print("\n[1] 从未探测过 → 探一次并记账")
h = Host()
h.rules_watch()
ok(h.calls == 1, f"调用了 1 次探测（实际 {h.calls}）")
ok(float(h._state.get("at") or 0) > 0, "成功时间戳已落盘")
ok(int(h._state.get("fail") or 0) == 0, "失败计数清零")
ok(any("自动刷新完成" in m for _lv, m in h.logs), "记了「自动刷新完成」日志")

print("\n[2] 刚成功过（未到周期）→ 不再探")
h2 = Host(state={"at": NOW - 60, "fail": 0})
h2.rules_watch()
ok(h2.calls == 0, "周期内不探测")

print("\n[3] 超过一个周期 → 再探")
h3 = Host(state={"at": NOW - PERIOD - 60, "fail": 0})
h3.rules_watch()
ok(h3.calls == 1, "超过 7 天 → 重新探测")

print("\n[4] 一轮 0 站有结果 → 算失败（不写 at）")
h4 = Host(resp=_Resp(data={"results": [{"domain": "a", "skipped": "PV 预算不足"},
                                       {"domain": "b", "skipped": "未配置 cookie"}]}))
h4.rules_watch()
ok(h4.calls == 1, "确实尝试了")
ok(float(h4._state.get("at") or 0) == 0, "**没有**写成功时间戳（不会干等一周）")
ok(int(h4._state.get("fail") or 0) == 1, "失败计数 = 1")
ok(any(lv == "warning" for lv, _m in h4.logs), "按 warning 记日志")

print("\n[5] 返回 success=False → 算失败")
h5 = Host(resp=_Resp(success=False, message="没有可探测的站点"))
h5.rules_watch()
ok(int(h5._state.get("fail") or 0) == 1 and float(h5._state.get("at") or 0) == 0,
   "success=False → 记失败、不写 at")
ok(any("没有可探测的站点" in m for _lv, m in h5.logs), "失败原因进日志（可见）")

print("\n[6] results 为空 → 算失败")
h6 = Host(resp=_Resp(data={"results": []}))
h6.rules_watch()
ok(int(h6._state.get("fail") or 0) == 1, "空结果集 → 记失败")

print("\n[7] 失败退避期内 → 不再探")
h7 = Host(state={"fail": 1, "fail_at": NOW - 5 * 60})
h7.rules_watch()
ok(h7.calls == 0, "5 分钟前刚失败过（退避 30min）→ 不探")

print("\n[8] 退避到期 → 会再探")
h8 = Host(state={"fail": 1, "fail_at": NOW - 31 * 60})
h8.rules_watch()
ok(h8.calls == 1, "超过 30min → 重试")

print("\n[9] 退避时长按 30min×2^(n-1) 增长，封顶 6h")
_waits = [min(float(common.RULES_RETRY_MAX_MINUTES),
              float(common.RULES_RETRY_MIN_MINUTES) * (2 ** (n - 1)))
          for n in (1, 2, 3, 4, 5, 6)]
ok(_waits[:5] == [30.0, 60.0, 120.0, 240.0, 360.0], f"1..5 次退避 = {_waits[:5]}")
ok(_waits[5] == float(common.RULES_RETRY_MAX_MINUTES) == 360.0, "第 6 次起封顶 360min")
h9 = Host(state={"fail": 5, "fail_at": NOW - 359 * 60})
h9.rules_watch()
ok(h9.calls == 0, "第 5 次失败（退避 6h）未到期 → 不探")

print("\n[10] auto_refresh=False → 一次都不探")
h10 = Host(auto=False)
h10.rules_watch()
ok(h10.calls == 0, "开关关掉就完全不探")

print("\n[11] 拿不到 worker 槽 → 不探、不记账")
h11 = Host(slot=False)
h11.rules_watch()
ok(h11.calls == 0, "没抢到槽就不探")
ok(h11._state == {}, "**不**写任何状态（跳过 ≠ 已刷新）")

print("\n[11b] 并发互斥：同一时刻只允许一轮探测（19.10.10）")
h11b = Host()
_lk1 = h11b._rules_probe_guard()
ok(_lk1 is not None, "第一次拿到探测锁")
ok(h11b._rules_probe_guard() is None, "锁被占时第二次拿不到（跨实例同一把锁）")
_lk1.release()
ok(h11b._rules_probe_guard() is not None, "释放后可再拿")


class HostLocked(Host):
    def _rules_probe_guard(self):
        return None


h11c = HostLocked()
h11c.rules_watch()
ok(h11c.calls == 0, "锁被占 → 本轮直接跳过、不探测")

print("\n[12] 源码护栏：服务注册用节拍常量 + 接了启动补跑")
_core_src = (ROOT / "features" / "core.py").read_text(encoding="utf-8")
ok('"minutes": RULES_TICK_MINUTES' in _core_src, "Rules 服务用 RULES_TICK_MINUTES")
ok("self._rules_bootstrap_async()" in _core_src, "注册处调了启动补跑")
ok("def _rules_bootstrap_async" in _core_src, "_rules_bootstrap_async 已定义")
ok(common.RULES_TICK_MINUTES < common.RULES_INTERVAL_MINUTES,
   f"节拍({common.RULES_TICK_MINUTES}min) 远小于目标周期({common.RULES_INTERVAL_MINUTES}min)")

print()
if FAILS:
    print(f"❌ FAIL（{len(FAILS)} 项）")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("✅ PASS：站点规则探测节拍回归全部通过")
