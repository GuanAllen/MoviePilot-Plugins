#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 「未完成下载无 H&R 义务」离线回归（★ 15.5.0，真跑 common/deletegate，不需 MoviePilot）。

背景（Master 2026-10-07 16:19「没有下完的内容没有 h&r 我可以删除」）：
  点播清单里两个慢种（CARPT / 学校）想移除却被删种闸门拦下 —— 因为插件是**下载即开账**，
  账单 state=active → `_delete_bill_assert` 硬拦。但**未下载完成**的种在站上不计 H&R
  （未达触发阈），所以口径应为：**未完成 ⇒ 无 H&R 义务 ⇒ 不拦**。

落点（单一真值源）：
  · ``common.hr_incomplete(torrent)``：progress < 0.999 → True（读不到 / None / 非法 → False，fail-safe）；
  · ``features/hr.py::_hr_obligation[_by_seed]`` 顶部短路（未完成 → 不欠）；
  · ``features/deletegate.py::_delete_bill_assert`` 跳过未完成的种（有 qB 行且未完成才豁免）。

断言：
  [1] hr_incomplete：0.42/0.999/1.0/None/缺字段/非数值 六种输入的正确取值；
  [2] _delete_bill_assert：未完成 + active 账单 → **不拦**；
  [3] _delete_bill_assert：已完成（progress=1.0）+ active 账单 → **拦**（规则不变）；
  [4] _delete_bill_assert：不在 qB（快照无该 hash）→ **照拦**（fail-safe，不豁免）；
  [5] 源码护栏：hr 两处都短路、deletegate 走 hr_incomplete。

用法：``python3 tools/test_hr_incomplete.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_hr_incomplete_test"


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


def _load_common():
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
        ("bonus", ("TorrentBonusInfo",)),
        ("fingerprint", ("fingerprint", "inner_fingerprint", "info_hash", "Entry",
                         "entries_fingerprint", "load_torrent_entries", "total_size")),
        ("fetcher", ("SiteCandidateTorrent",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    return _load(PKG + ".common", "common.py")


common = _load_common()
tags = _load(PKG + ".tags", "tags.py")
dg = _load(PKG + ".features.deletegate", "features/deletegate.py")
hr_incomplete = common.hr_incomplete

FAILS = []
N = 0


def ok(cond, label):
    global N
    N += 1
    if not cond:
        FAILS.append(label)
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


# ---------------------------------------------------------------- [1] hr_incomplete
print("[1] hr_incomplete 取值")
ok(hr_incomplete(SimpleNamespace(progress=0.42)) is True, "0.42 → 未完成")
ok(hr_incomplete(SimpleNamespace(progress=0.999)) is False, "0.999 → 已完成（阈值含）")
ok(hr_incomplete(SimpleNamespace(progress=1.0)) is False, "1.0 → 已完成")
ok(hr_incomplete(SimpleNamespace(progress=0.9989)) is True, "0.9989 → 未完成")
ok(hr_incomplete(SimpleNamespace(progress=None)) is False, "progress=None → 不豁免（fail-safe）")
ok(hr_incomplete(SimpleNamespace()) is False, "缺字段 → 不豁免（fail-safe）")
ok(hr_incomplete(SimpleNamespace(progress="bad")) is False, "非数值 → 不豁免（fail-safe）")

# ---------------------------------------------------------------- [1b] 可设置完成度阈值
print("[1b] 完成度阈值可设置")
ok(hr_incomplete(SimpleNamespace(progress=0.6), 0.5) is False, "ratio=0.5：0.6 → 算完成")
ok(hr_incomplete(SimpleNamespace(progress=0.4), 0.5) is True, "ratio=0.5：0.4 → 未完成")
ok(hr_incomplete(SimpleNamespace(progress=0.6), None) is True, "ratio=None → 用默认 0.999：0.6 未完成")
ok(common.hr_complete_ratio_of(SimpleNamespace()) == common.HR_COMPLETE_RATIO_DEFAULT,
   "hr_complete_ratio_of：无设置 → 默认常量")


class _Ratio:
    def _hr_complete_ratio(self):
        return 0.5


ok(common.hr_complete_ratio_of(_Ratio()) == 0.5, "hr_complete_ratio_of：读 _hr_complete_ratio(dom)")


class _RatioDom:
    def _hr_complete_ratio(self, dom=""):
        return 0.2 if dom else 0.999


ok(common.hr_complete_ratio_of(_RatioDom(), "cspt.top") == 0.2, "站点覆盖：cspt.top → 0.2")
ok(common.hr_complete_ratio_of(_RatioDom(), "") == 0.999, "无站点 → 全局默认")
ok(common.HR_COMPLETE_RATIO_DEFAULT == 0.999, "默认阈值常量 = 0.999")


class _Bills:
    def __init__(self, d):
        self._d = d

    def get(self, h):
        return self._d.get(str(h or "").lower())


class Fake(dg.DeleteGateMixin):
    """只提供 `_delete_bill_assert` 需要的最小依赖。"""

    def __init__(self, snap, bills, ratio=None):
        self._snap = dict(snap or {})
        self._bills = _Bills(bills or {})
        self._ratio = ratio

    def _tag_all_torrents(self):
        return dict(self._snap)

    def _hrbills_store(self):
        return self._bills

    def _hr_complete_ratio(self, dom=""):
        if self._ratio is None:
            raise AttributeError("no ratio")
        return self._ratio


ACTIVE = {"state": "active", "rule": "site_hr", "site": "carpt.net"}
HB = "a" * 40
HC = "b" * 40
HD = "c" * 40

# ---------------------------------------------------------------- [2] 未完成 → 不拦
print("[2] 未完成 + active 账单 → 不拦")
f = Fake(snap={HB: SimpleNamespace(progress=0.023, hash=HB)}, bills={HB: dict(ACTIVE)})
why = f._delete_bill_assert([HB])
ok(why == {}, f"未完成放行（{why}）")

# ---------------------------------------------------------------- [3] 已完成 → 拦
print("[3] 已完成 + active 账单 → 拦")
f = Fake(snap={HC: SimpleNamespace(progress=1.0, hash=HC)}, bills={HC: dict(ACTIVE)})
why = f._delete_bill_assert([HC])
ok(HC in why and "H&R" in str(why[HC]), f"已完成照拦（{why.get(HC)}）")

# ---------------------------------------------------------------- [4] 不在 qB → 照拦
print("[4] 不在 qB（快照无该 hash）→ 照拦（fail-safe）")
f = Fake(snap={}, bills={HD: dict(ACTIVE)})
why = f._delete_bill_assert([HD])
ok(HD in why, "不可验证 → 不豁免、照拦")

# ---------------------------------------------------------------- [5] 源码护栏
print("[5] 源码护栏")
hr_src = (ROOT / "features" / "hr.py").read_text(encoding="utf-8")
ok(hr_src.count("self._hr_incomplete_of(site, torrent)") >= 2, "hr.py 两处（_hr_obligation / _by_seed）都短路")
ok("from ..common import hr_incomplete, hr_complete_ratio_of" in hr_src, "hr.py 走 common 同一真值源")
dg_src = (ROOT / "features" / "deletegate.py").read_text(encoding="utf-8")
ok("hr_incomplete(_t, hr_complete_ratio_of(self, str(b.get(\"site\") or \"\")))" in dg_src,
   "deletegate 账单断言走 hr_incomplete（按账单站点取阈值）")
hb_src = (ROOT / "features" / "hrbills.py").read_text(encoding="utf-8")
ok("def _hr_complete_ratio" in hb_src, "hrbills 提供 _hr_complete_ratio(dom) 读取设置")
ok('get("complete_ratio")' in hb_src, "★ 站点级覆盖：读规则库 complete_ratio")
ok("0.999" not in hb_src.split("def _hrbills_tick")[1].split("def ")[0], "tick 不再硬编码 0.999")
so_src = (ROOT / "features" / "siteops.py").read_text(encoding="utf-8")
ok('act in ("set_ratio", "ratio")' in so_src, "siteops 提供 /rules?action=set_ratio")

# ---------------------------------------------------------------- [6] 阈值生效于断言
print("[6] 完成度阈值生效于删除断言")
f = Fake(snap={HB: SimpleNamespace(progress=0.6, hash=HB)}, bills={HB: dict(ACTIVE)}, ratio=0.5)
ok(f._delete_bill_assert([HB]) != {}, "ratio=0.5 + progress=0.6 → 算完成 → 照拦")
f = Fake(snap={HB: SimpleNamespace(progress=0.4, hash=HB)}, bills={HB: dict(ACTIVE)}, ratio=0.5)
ok(f._delete_bill_assert([HB]) == {}, "ratio=0.5 + progress=0.4 → 未完成 → 放行")

print()
if FAILS:
    print(f"❌ FAIL：{len(FAILS)}/{N} 断言失败")
    for x in FAILS:
        print("   -", x)
    sys.exit(1)
print(f"✅ PASS：{N}/{N} 断言全过")
