#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 站点清单回落离线回归（★ 15.8.10）。

背景（Master 2026-10-09）：「魔流站点报表无数据」。真相在 MP 侧：MP「用户认证」失效
（日志 ``hdfans认证出错：User: 64613 is not enabled.`` → ``auth_level < 2``），
``SitesHelper().get_indexers()`` 返回空表；魔流站点清单 ``_list_sites()`` 随之空掉，
于是任务编辑器站点下拉、``/status`` 的 ``options.sites``、站点报表选择器
（``/site/seeds`` 不带 site 时的 ``available_sites``）全空 → 报表页面无站点可选中。

修法：``_list_sites()`` **SitesHelper 优先（健康路径行为不变）**，空表/异常时回落
MP 站点登记表 ``app.db.oper.site.SiteOper``（它不过用户认证闸门，且是
``features/reseed.py::_reseed_mp_sites`` 已在用的口径）。

断言：
  1) SitesHelper 有数据 → 原样返回，**不**碰 SiteOper（健康路径零回归）；
  2) SitesHelper 空表 → 回落 ``SiteOper().list()`` 并记一条回落日志；
  3) SitesHelper 抛异常 → 记 error 后回落 SiteOper；
  4) 两处都空 → 返回 ``[]``（不抛）；
  5) 归一化：domain 统一 ``strip().lower()``、name 缺失回落 domain、
     「无 id 且无 domain」的行丢弃（SitesHelper 与 SiteOper 两侧同口径）；
  6) 回落告警按「状态变化」去重（重复调用不刷日志；认证恢复后再失效要重新告警一次）；
  7) 源码护栏：``_list_sites`` 函数体内 ``SitesHelper`` 出现在 ``SiteOper`` 之前
     （防回落被改写成主路径，把认证闸门又架回站点清单上）。

用法：``python3 tools/test_site_fallback.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_site_fallback"


# ----------------------------------------------------------------- 桩加载器
def _stub_pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


class _Stub(types.ModuleType):
    """万能桩模块：任何属性/调用都是另一个 _Stub。"""

    def __init__(self, name: str = "_stub"):
        super().__init__(name)

    def __getattr__(self, name):
        return _Stub(name)

    def __call__(self, *a, **k):
        return _Stub("_call")


def _stub_sibling(modname: str) -> _Stub:
    m = _Stub(PKG + "." + modname)
    sys.modules[PKG + "." + modname] = m
    return m


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------- 1. 站点表假实现
class _SiteRow:
    """SiteOper().list() 返回的站点行（真实环境是 MP 的 Site 模型）。"""

    def __init__(self, sid, name, domain):
        self.id = sid
        self.name = name
        self.domain = domain


HELPER = {"rows": [], "raise": False}
OPER = {"rows": [], "raise": False, "calls": 0}


class _SitesHelper:
    def get_indexers(self):
        if HELPER["raise"]:
            raise RuntimeError("sites boom")
        return HELPER["rows"]


class _SiteOper:
    def list(self):
        OPER["calls"] += 1
        if OPER["raise"]:
            raise RuntimeError("db boom")
        return OPER["rows"]


# ---------------------------------------------------------- 2. 桩 app.*
for n, attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": _Stub("EventType")}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": _Stub("eventmanager"),
                        "Event": type("Event", (), {})}),
    ("app.sdk.logging", {"logger": _Stub("logger")}),
    ("app.scheduler", {"Scheduler": type("Scheduler", (), {})}),
    ("app.api", {}),
    ("app.api.endpoints", {}),
    ("app.api.endpoints.plugin", {"register_plugin_api": lambda *a, **k: None}),
    ("app.db", {}),
    ("app.db.oper", {}),
    ("app.db.oper.site", {"SiteOper": _SiteOper}),
    ("app.sdk.network", {"SitesHelper": _SitesHelper}),
    ("app.sdk.services", {"DownloaderHelper": type("DownloaderHelper", (), {})}),
):
    m = sys.modules.get(n)
    if m is None:
        m = types.ModuleType(n)
        sys.modules[n] = m
    for k, v in attrs.items():
        setattr(m, k, v)

# 3. 桩魔流顶层包及兄弟模块（core.py 的相对导入全部落桩）
_stub_pkg(PKG, ROOT)
_stub_pkg(PKG + ".features", ROOT / "features")
_stub_pkg(PKG + ".sites", ROOT / "sites")
for modname in ("bonus", "fetcher", "recommend", "models", "fingerprint",
                "persistence", "downloader_ops", "live_stats", "dtier",
                "tags", "formulas", "hubs",
                "fallback", "collect", "cloud_archive", "kvstore",
                "signin", "sitestore", "ledger", "qbsync", "dupgate",
                "rulepack", "iyuu_cloud", "db", "codedict"):
    _stub_sibling(modname)

# 4. 先加载 common.py（叶子），再加载真 features/core.py
_load(PKG + ".common", "common.py")
_core = _load(PKG + ".features.core", "features/core.py")


CHECKS = 0


def _ok(cond: bool, msg) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1


class _Plug(_core.CoreMixin):
    """只借用 CoreMixin._list_sites 的最小宿主。"""

    def __init__(self):
        self.logs = []

    def _log(self, msg, level="info"):
        self.logs.append((str(msg), str(level)))


def _reset(helper_rows=None, oper_rows=None, helper_raise=False, oper_raise=False):
    HELPER["rows"] = list(helper_rows or [])
    HELPER["raise"] = helper_raise
    OPER["rows"] = list(oper_rows or [])
    OPER["raise"] = oper_raise
    OPER["calls"] = 0
    return _Plug()


# -----------------------------------------------------------------------
# [1] 健康路径：SitesHelper 有数据 → 不碰 SiteOper
# -----------------------------------------------------------------------
p = _reset(helper_rows=[{"id": 9, "name": "馒头", "domain": "M-Team.CC"}],
           oper_rows=[_SiteRow(1, "学校", "btschool.club")])
rows = p._list_sites()
_ok(rows == [{"id": 9, "name": "馒头", "domain": "m-team.cc"}],
    f"SitesHelper 有数据 → 用它且归一化 domain（实际 {rows}）")
_ok(OPER["calls"] == 0,
    f"健康路径不查站点登记表（SiteOper 调用次数 {OPER['calls']}，应 0）")
_ok(not any(lv == "error" for _, lv in p.logs),
    f"健康路径无 error 日志（实际 {p.logs}）")


# -----------------------------------------------------------------------
# [2] SitesHelper 空表 → 回落 SiteOper
# -----------------------------------------------------------------------
p = _reset(helper_rows=[],
           oper_rows=[_SiteRow(1, "学校", "btschool.club"),
                      _SiteRow(3, "咖啡", " ptcafe.club ")])
rows = p._list_sites()
_ok(rows == [{"id": 1, "name": "学校", "domain": "btschool.club"},
             {"id": 3, "name": "咖啡", "domain": "ptcafe.club"}],
    f"空表回落站点登记表且归一化（实际 {rows}）")
_ok(OPER["calls"] == 1, f"回落时查一次站点登记表（实际 {OPER['calls']}）")
_ok(any("站点登记表" in m for m, _ in p.logs),
    f"回落记一条可诊断日志（实际 {p.logs}）")

# 告警去重：_list_sites 被多条 worker 线每轮调用，不能每轮刷一条
_n1 = sum(1 for m, _ in p.logs if "站点登记表" in m)
p._list_sites()
p._list_sites()
_n2 = sum(1 for m, _ in p.logs if "站点登记表" in m)
_ok(_n2 == _n1,
    f"回落告警按状态变化去重：重复调用不再刷日志（{_n1} → {_n2}）")

HELPER["rows"] = [{"id": 9, "name": "馒头", "domain": "m-team.cc"}]
_ok(len(p._list_sites()) == 1, "认证恢复 → 用回 SitesHelper")
HELPER["rows"] = []
p._list_sites()
_n3 = sum(1 for m, _ in p.logs if "站点登记表" in m)
_ok(_n3 == _n2 + 1,
    f"认证恢复后再次失效 → 重新告警一次（{_n2} → {_n3}）")


# -----------------------------------------------------------------------
# [3] SitesHelper 抛异常 → 记 error 后回落
# -----------------------------------------------------------------------
p = _reset(helper_raise=True, oper_rows=[_SiteRow(5, "高清时间", "hdtime.org")])
rows = p._list_sites()
_ok(rows == [{"id": 5, "name": "高清时间", "domain": "hdtime.org"}],
    f"SitesHelper 抛异常 → 回落站点登记表（实际 {rows}）")
_ok(any(lv == "error" for _, lv in p.logs),
    f"SitesHelper 异常记 error 日志（实际 {p.logs}）")


# -----------------------------------------------------------------------
# [4] 两处都空 → []（不抛）
# -----------------------------------------------------------------------
p = _reset(helper_rows=[], oper_rows=[])
_ok(p._list_sites() == [], "两处都空 → 返回 []")
p = _reset(helper_rows=[], oper_raise=True)
_ok(p._list_sites() == [],
    "回落也抛异常 → 吞掉并返回 []（不冒泡给调用方）")
_ok(any("站点登记表回落也失败" in m for m, _ in p.logs),
    f"回落失败也记 error 日志（实际 {p.logs}）")


# -----------------------------------------------------------------------
# [5] 归一化 / 丢脏行（两侧同口径）
# -----------------------------------------------------------------------
p = _reset(helper_rows=[{"id": None, "name": None, "domain": None},
                        {"id": 7, "domain": "PTTime.ORG"},
                        "not-a-dict",
                        {"id": 12, "name": "NovaHD", "domain": ""}])
rows = p._list_sites()
_ok(rows == [{"id": 7, "name": "pttime.org", "domain": "pttime.org"},
             {"id": 12, "name": "NovaHD", "domain": ""}],
    f"无 id 且无 domain 的空行 + 非 dict 行被丢弃、name 回落 domain（实际 {rows}）")

p = _reset(helper_rows=[], oper_rows=[_SiteRow(None, "无名", ""),
                                      _SiteRow(11, "", " Example.COM ")])
rows = p._list_sites()
_ok(rows == [{"id": 11, "name": "example.com", "domain": "example.com"}],
    f"站点登记表侧同样丢弃坏行、name 回落 domain（实际 {rows}）")


# -----------------------------------------------------------------------
# [6] 源码级护栏：SitesHelper 必须先于 SiteOper
# -----------------------------------------------------------------------
_core_src = (ROOT / "features" / "core.py").read_text(encoding="utf-8")
_body = _core_src[_core_src.index("def _list_sites"):]
_body = _body[:_body.index("\n    def ", 10)]
_ok("SiteOper" in _body and "SitesHelper" in _body,
    "core.py::_list_sites 同时含 SitesHelper 与 SiteOper（回落实现）")
_ok(_body.index("SitesHelper") < _body.index("SiteOper"),
    "core.py::_list_sites：SitesHelper 在主路径、SiteOper 只做回落（顺序护栏）")
_ok("或 []" in _body or "or []" in _body,
    "core.py::_list_sites：遍历两侧都做了 None 保护（or []）")


print("\n" + "=" * 64)
print(f"✅ PASS —— 共 {CHECKS} 项全过")
