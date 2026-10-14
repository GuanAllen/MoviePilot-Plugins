#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · H7「H&R 三源交叉」离线回归（★ 17.2.2，真跑 features/health.py，不需 MoviePilot）。

背景：H&R 有三处事实/判据来源，各说一件事——
  · 首页页头计数（``H&R: [考核中/未完成/上限]``，**上限＝达到该数即禁用账号**）
    = **站点口径的事实**（本来就在抓，零新增 PV）；
  · myhr 对账缓存 ``records_total`` = **逐条明细的事实**（6h 轮询/触发式）；
  · 站点规则库 ``hr`` / ``per_torrent_hr`` = **我们在用的判据**。
健康检查只做交叉校验，**只报不改**（不写规则库、不碰账单状态、不抓页面）。

断言：
  1) 页头欠 1 条 + myhr ok 但 0 条 → error（对账通道失灵，欠账会漏保护）；
  2) 页头欠 2 条 + 规则表 hr=False → warning（规则与事实冲突）；
  3) 规则标 hr=True（非逐种）+ 页头 0 + myhr 0 条 → info（口径一致，仅提示）；
  4) 有 H&R 栏但数字没读懂 → warning（不冒充 0）；
  5) 缓存里没有 ``hr`` 键（升级前旧快照/该站没这栏）→ 静默，不刷屏；
  6) 页头有欠条但规则库无判据（hr=None）→ info（该补规则）；
  7) 逐种站（per_torrent_hr=True）标 hr=True 且页头 0 → 不报「标有 H&R 但无记录」；
  8) **零外部请求 / 零写**：桩对象只暴露只读方法，任何未定义调用都会 AttributeError；
  9) 已达禁用线（**未完成 y ≥ 上限 z**）→ error（**优先于**①对账失灵）；
  10) 差 1 条到禁用线（y ＝ z-1）→ warning（**优先于**②规则冲突；考核中只作缓冲提示）；
  11) 有欠条但离线还远、站点不给禁用线（学校形态）、只读到单个数 → 都不报禁用线；
  12) **封号判据只看 y**：x=考核中 堆到 9/10 也不算禁用线。

用法：``python3 tools/test_health_hr_crosscheck.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_hr_cross_test"
FAILED: list = []


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

for _name, _attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": type("EventType", (), {})}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
):
    _m = sys.modules.get(_name)
    if _m is None:
        _m = types.ModuleType(_name)
        sys.modules[_name] = _m
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)
for _modname, _attrs in (
    ("bonus", ("TorrentBonusInfo",)),
    ("fingerprint", ("fingerprint", "inner_fingerprint", "info_hash", "Entry",
                     "entries_fingerprint", "load_torrent_entries", "total_size")),
    ("fetcher", ("SiteCandidateTorrent",)),
):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    sys.modules[PKG + "." + _modname] = _m

_load(PKG + ".common", "common.py")

_hrbills = types.ModuleType(PKG + ".features.hrbills")
_hrbills.BILL_STATE_ACTIVE = "active"
_hrbills.BILL_STATE_BREACHED = "breached"
_hrbills.RULE_SITE_HR = "site_hr"
_hrbills.RULE_HIT_AND_RUN = "hit_and_run"
sys.modules[PKG + ".features.hrbills"] = _hrbills

health = _load(PKG + ".features.health", "features/health.py")


def chk(name, cond, got=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ← {got}"))
    if not cond:
        FAILED.append(name)


class _Live:
    """LiveStats 只读桩：``cached(sid)`` 不抓页。"""

    def __init__(self, rows):
        self.rows = dict(rows or {})

    def cached(self, sid):
        return dict(self.rows.get(int(sid)) or {})


class _HrCache:
    def __init__(self, reports):
        self._reports = dict(reports or {})

    def reports(self):
        return dict(self._reports)


class Fake(health.HealthMixin):
    """只暴露 H7 需要的只读方法（任何写调用都会 AttributeError）。"""

    def __init__(self, *, rules=None, sites=None, flags=None, per_torrent=None,
                 reports=None, live=None):
        self._rules = dict(rules or {})
        self._sites = list(sites or [])
        self._flags = dict(flags or {})
        self._pt = dict(per_torrent or {})
        self._reports = dict(reports or {})
        self._live = _Live(live)

    def _site_rules(self):
        return dict(self._rules)

    def _list_sites(self):
        return list(self._sites)

    def _site_hr_flag(self, dom):
        return self._flags.get(dom)

    def _site_per_torrent_hr(self, dom):
        return bool(self._pt.get(dom, False))

    def _hr_reconcile_cache(self):
        return _HrCache(self._reports)


def _find(issues, key):
    for i in issues:
        if str(i.get("key")) == key:
            return i
    return None


# 1) 页头欠 1 条 + myhr ok 但 0 条 → error
p = Fake(
    rules={"cspt.top": {"hr": False, "source": "manual"}},
    sites=[{"id": 8, "domain": "cspt.top", "name": "财神"}],
    flags={"cspt.top": False},
    reports={"cspt.top": {"ok": True, "records_total": 0}},
    live={8: {"hr": {"raw": "H&R: [1/0/10]", "assessing": 1, "unfinished": 0, "limit": 10}}},
)
r = p._health_hr_crosscheck()
_i = _find(r, "H7:8")
chk("①对账失灵→error", bool(_i) and _i["level"] == "error", r)

# 2) 页头欠 2 条 + 规则 hr=False（myhr 也有 2 条）→ warning
p = Fake(
    rules={"ptcafe.club": {"hr": False, "hr_src": "manual"}},
    sites=[{"id": 3, "domain": "ptcafe.club", "name": "咖啡"}],
    flags={"ptcafe.club": False},
    reports={"ptcafe.club": {"ok": True, "records_total": 2}},
    live={3: {"hr": {"raw": "H&R: [2/0/20]", "assessing": 2, "unfinished": 0, "limit": 20}}},
)
r = p._health_hr_crosscheck()
_i = _find(r, "H7:3")
chk("②规则冲突→warning", bool(_i) and _i["level"] == "warning", r)
chk("②冲突详情带来源", bool(_i) and "manual" in str(_i.get("detail")), _i)

# 3) 规则 hr=True（非逐种）+ 页头 0 + myhr 0 → info
p = Fake(
    rules={"pt.btschool.club": {"hr": True, "hr_src": "welcome"}},
    sites=[{"id": 1, "domain": "pt.btschool.club", "name": "学校"}],
    flags={"pt.btschool.club": True},
    reports={"pt.btschool.club": {"ok": True, "records_total": 0}},
    live={1: {"hr": {"raw": "H&R: 0/ 0", "assessing": 0, "unfinished": 0, "limit": None}}},
)
r = p._health_hr_crosscheck()
_i = _find(r, "H7:1")
chk("③口径一致→info", bool(_i) and _i["level"] == "info", r)

# 4) 有栏但没读懂数字 → warning（不冒充 0）
p = Fake(
    rules={"dstudio.me": {"hr": True}},
    sites=[{"id": 15, "domain": "dstudio.me", "name": "Depth Studio"}],
    flags={"dstudio.me": True},
    live={15: {"hr": {"raw": "H&R: 详见规则页", "assessing": None, "unfinished": None, "limit": None}}},
)
r = p._health_hr_crosscheck()
_i = _find(r, "H7:15")
chk("④没读懂→warning", bool(_i) and _i["level"] == "warning", r)

# 5) 缓存没有 hr 键（升级前旧快照）→ 静默
p = Fake(
    rules={"duckboobee.org": {"hr": False}},
    sites=[{"id": 11, "domain": "duckboobee.org", "name": "March"}],
    flags={"duckboobee.org": False},
    live={11: {"seeding": 3, "upload": 1.0}},
)
chk("⑤旧快照→静默", p._health_hr_crosscheck() == [], p._health_hr_crosscheck())

# 6) 页头有欠条但规则库无判据（hr=None）→ info
p = Fake(
    rules={"crabpt.vip": {}},
    sites=[{"id": 14, "domain": "crabpt.vip", "name": "蟹黄堡"}],
    flags={"crabpt.vip": None},
    live={14: {"hr": {"raw": "H&R: [3/1/15]", "assessing": 3, "unfinished": 1, "limit": 15}}},
)
r = p._health_hr_crosscheck()
_i = _find(r, "H7:14")
chk("⑥规则库该补→info", bool(_i) and _i["level"] == "info", r)

# 7) 逐种站（per_torrent_hr=True）：hr=True + 页头 0 → 不报「标有 H&R 但无记录」
p = Fake(
    rules={"www.yemapt.org": {"hr": False, "per_torrent_hr": True}},
    sites=[{"id": 16, "domain": "www.yemapt.org", "name": "YemaPT"}],
    flags={"www.yemapt.org": False},
    per_torrent={"www.yemapt.org": True},
    reports={"www.yemapt.org": {"ok": True, "records_total": 0}},
    live={16: {"hr": {"raw": "H&R: [0/0/5]", "assessing": 0, "unfinished": 0, "limit": 5}}},
)
chk("⑦逐种站静默", p._health_hr_crosscheck() == [], p._health_hr_crosscheck())

# 9) 已达禁用线（未完成 10 ＝ 上限 10）→ error，且**优先于**①对账失灵
p = Fake(
    rules={"dstudio.me": {"hr": False, "hr_src": "rules_php"}},
    sites=[{"id": 15, "domain": "dstudio.me", "name": "Depth Studio"}],
    flags={"dstudio.me": False},
    reports={"dstudio.me": {"ok": True, "records_total": 0}},
    live={15: {"hr": {"raw": "H&R: [0/10/10]", "assessing": 0, "unfinished": 10, "limit": 10}}},
)
r = p._health_hr_crosscheck()
_i = _find(r, "H7:15")
chk("⑨已达禁用线→error", bool(_i) and _i["level"] == "error", r)
chk("⑨优先于对账失灵", bool(_i) and "禁用线" in str(_i.get("title")), _i)
chk("⑨详情带口径与上限", bool(_i) and "10" in str(_i.get("detail")) and "未完成" in str(_i.get("detail")), _i)

# 10) 差 1 条到禁用线（未完成 9/10）→ warning，且**优先于**②规则冲突；考核中只作缓冲提示
p = Fake(
    rules={"cspt.top": {"hr": False, "hr_src": "manual"}},
    sites=[{"id": 8, "domain": "cspt.top", "name": "财神"}],
    flags={"cspt.top": False},
    reports={"cspt.top": {"ok": True, "records_total": 9}},
    live={8: {"hr": {"raw": "H&R: [2/9/10]", "assessing": 2, "unfinished": 9, "limit": 10}}},
)
r = p._health_hr_crosscheck()
_i = _find(r, "H7:8")
chk("⑩差 1 条→warning", bool(_i) and _i["level"] == "warning", r)
chk("⑩优先于规则冲突", bool(_i) and "禁用线" in str(_i.get("title")), _i)
chk("⑩考核中只作缓冲提示", bool(_i) and "考核中 2" in str(_i.get("detail")), _i)

# 11a) 有欠条但离线还远（未完成 0/10）→ 不报禁用线（走别的规则或静默）
p = Fake(
    rules={"dstudio.me": {"hr": True}},
    sites=[{"id": 15, "domain": "dstudio.me", "name": "Depth Studio"}],
    flags={"dstudio.me": True},
    reports={"dstudio.me": {"ok": True, "records_total": 1}},
    live={15: {"hr": {"raw": "H&R: [1/0/10]", "assessing": 1, "unfinished": 0, "limit": 10}}},
)
chk("⑪a 离线还远→不报禁用线", "禁用线" not in str(p._health_hr_crosscheck()), p._health_hr_crosscheck())

# 11b) 站点不给禁用线（学校形态：H&R 0/0，limit=None）→ 永不报禁用线
p = Fake(
    rules={"pt.btschool.club": {"hr": True, "hr_src": "welcome"}},
    sites=[{"id": 1, "domain": "pt.btschool.club", "name": "学校"}],
    flags={"pt.btschool.club": True},
    reports={"pt.btschool.club": {"ok": True, "records_total": 0}},
    live={1: {"hr": {"raw": "H&R: 0/ 0", "assessing": 0, "unfinished": 0, "limit": None}}},
)
chk("⑪b 无禁用线→不报禁用线", "禁用线" not in str(p._health_hr_crosscheck()), p._health_hr_crosscheck())

# 11c) 单数形态（只读到未完成 3，limit=None）→ 只走规则库补齐提示，不报禁用线
p = Fake(
    rules={"crabpt.vip": {}},
    sites=[{"id": 14, "domain": "crabpt.vip", "name": "蟹黄堡"}],
    flags={"crabpt.vip": None},
    live={14: {"hr": {"raw": "H&R: 3", "assessing": None, "unfinished": 3, "limit": None}}},
)
r = p._health_hr_crosscheck()
_i = _find(r, "H7:14")
chk("⑪c 单数→info 不报禁用线", bool(_i) and _i["level"] == "info" and "禁用线" not in str(_i.get("title")), r)

# 11d) **封号判据只看 y（未完成）**：x 堆到 9/10 也不算禁用线
p = Fake(
    rules={"dstudio.me": {"hr": True}},
    sites=[{"id": 15, "domain": "dstudio.me", "name": "Depth Studio"}],
    flags={"dstudio.me": True},
    reports={"dstudio.me": {"ok": True, "records_total": 9}},
    live={15: {"hr": {"raw": "H&R: [9/0/10]", "assessing": 9, "unfinished": 0, "limit": 10}}},
)
r = p._health_hr_crosscheck()
chk("⑪d 考核中不算封号数", "禁用线" not in str(r), r)

# 8) 站点清单为空 / 规则库为空 → 不炸
p = Fake()
chk("⑧空世界不炸", p._health_hr_crosscheck() == [], p._health_hr_crosscheck())

print()
if FAILED:
    print(f"❌ 合计 {len(FAILED)} 项失败：{FAILED}")
    sys.exit(1)
print("✅ 全部通过（H7 H&R 三源交叉）")
