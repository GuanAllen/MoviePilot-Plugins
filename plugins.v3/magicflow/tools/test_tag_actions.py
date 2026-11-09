#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 标签动作表（★ 19.10.28）离线回归 —— 真跑 features/tags.py，不需 MoviePilot。

背景：`get_tag_model` 原先是 443 行、37 个平铺 `if act == ...` 的长链，99 个动作别名
散落在条件里，没有任何地方能一次说清「/tags 支持哪些 action」。19.10.28 改成表驱动：
别名集中在 `_ACT_ALIASES`，落到 38 个 `_tag_act_*` 处理函数，分发器只剩 4 行。

这里钉住四件事（都不需要真账本/真下载器）：
  1) 别名总数 85、无重复、每个都指向真实存在的 `_tag_act_*`；
  2) 反向不遗漏：类上每个 `_tag_act_*` 都被表引用（没有孤儿处理函数）；
  3) 同组别名（xxx / xxx_plan / xxx_apply）指向同一个处理函数；
  4) 分发器：`act` 先 lower/strip、未知动作落到 status、入参原样进 `TagReq`。

用法：``python3 tools/test_tag_actions.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_tag_actions_test"


def _pkg(name, path):
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name, rel):
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
    _m = sys.modules.get(_name) or types.ModuleType(_name)
    sys.modules[_name] = _m
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)

_m = types.ModuleType(PKG + ".models")
_m.MagicFlowTagStatePayload = object
sys.modules[PKG + ".models"] = _m

_ledger = types.ModuleType(PKG + ".ledger")
_ledger.ResourceLedgerStore = type("ResourceLedgerStore", (), {})
_ledger.SeedLedgerStore = type("SeedLedgerStore", (), {})
_ledger.get_backend = lambda *a, **k: None
sys.modules[PKG + ".ledger"] = _ledger

for _modname, _attrs in (("bonus", ("calc_bonus_per_hour", "TorrentBonusInfo")),
                         ("fetcher", ("SiteCandidateTorrent",))):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    sys.modules[PKG + "." + _modname] = _m

_load(PKG + ".tags", "tags.py")
_load(PKG + ".fingerprint", "fingerprint.py")
_load(PKG + ".persistence", "persistence.py")
_load(PKG + ".common", "common.py")
_load(PKG + ".downloader_ops", "downloader_ops.py")
ftags = _load(PKG + ".features.tags", "features/tags.py")

CHECKS = 0


def _ok(cond, msg):
    global CHECKS
    assert cond, "❌ " + msg
    CHECKS += 1
    print("  ✅ " + msg)


TABLE = ftags.TAG_ACTIONS
ALIASES = ftags._ACT_ALIASES
MIXIN = ftags.TagsMixin


def main() -> int:
    print("== 1. 表结构 ==")
    _ok(len(TABLE) == 99, f"别名 99 个（实际 {len(TABLE)}；19.12.38 起 keep/claim 职务别名并入）")
    _ok(len(ALIASES) == 44, f"分组 44 组（实际 {len(ALIASES)}；19.12.38/19.12.x 新增 keep/claim 等）")
    _ok(len(TABLE) == sum(len(n) for _f, *n in ALIASES), "组内别名数之和 == 表条目数（无撞车）")
    handlers = [fn for fn, *_n in ALIASES]
    _ok(len(set(handlers)) == 44, "44 个处理函数互不重复")
    _ok(all(getattr(fn, "__name__", "").startswith("_tag_act_") for fn in handlers),
        "表里挂的都是 _tag_act_* 函数对象")
    _ok(all(getattr(MIXIN, fn.__name__, None) is fn for fn in handlers),
        "表里的函数对象就是 TagsMixin 上的同名属性")

    print("== 2. 反向：没有孤儿处理函数 ==")
    on_class = {n for n in dir(MIXIN) if n.startswith("_tag_act_")}
    named = {fn.__name__ for fn in handlers}
    _ok(on_class == named, f"类上 {len(on_class)} 个 _tag_act_* 全部登记（差集 {on_class ^ named or '空'}）")

    print("== 3. 同组别名指向同一处理函数 ==")
    for a, b in (("triage", "triage_apply"), ("magicize", "magicize_plan"),
                 ("clean", "clean_apply"), ("hold", "unhold"),
                 ("hr_void", "hrbills_void"), ("yema", "yemaapply")):
        _ok(TABLE[a] is TABLE[b], f"{a} 与 {b} 同一处理函数")

    print("== 4. 分发器语义 ==")
    seen = {}

    def _probe(req_self, req):
        seen["self"] = req_self
        seen["req"] = req
        return "PROBE"

    fake_self = types.SimpleNamespace(
        _tag_sync_names=lambda: None,
        _tag_state=lambda: "STORE",
        _tag_groups=lambda: "GROUPS",
    )
    saved = TABLE["triage_apply"]
    TABLE["triage_apply"] = _probe
    try:
        out = MIXIN.get_tag_model(fake_self, action="  TRIAGE_Apply ", hash="AbC", limit=7,
                                  confirm="1", site="s1", reason="r1", tids="t1", adopt_reseed="2")
    finally:
        TABLE["triage_apply"] = saved
    _ok(out == "PROBE", "命中 triage_apply 的分发")
    _ok(seen["self"] is fake_self, "处理函数收到的 self 就是调用者")
    req = seen["req"]
    _ok(req.act == "triage_apply", f"act 已 lower/strip（得到 {req.act!r}）")
    _ok((req.hash, req.limit, req.confirm) == ("AbC", 7, "1"), "入参原样进 TagReq")
    _ok((req.site, req.reason, req.tids, req.adopt_reseed) == ("s1", "r1", "t1", "2"),
        "site/reason/tids/adopt_reseed 原样进 TagReq")
    _ok((req.store, req.groups) == ("STORE", "GROUPS"), "两个账本句柄由分发器取好再传")

    saved = TABLE["status"]
    TABLE["status"] = _probe
    try:
        _ok(MIXIN.get_tag_model(fake_self, action="no-such-action") == "PROBE",
            "未知动作回落到 status")
        _ok(MIXIN.get_tag_model(fake_self, action="") == "PROBE", "空 action 回落到 status（act=status）")
        _ok(seen["req"].act == "status", "空 action 归一成 'status'")
    finally:
        TABLE["status"] = saved
    _ok(TABLE["status"] is MIXIN._tag_act_status, "status 指向 _tag_act_status")

    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
