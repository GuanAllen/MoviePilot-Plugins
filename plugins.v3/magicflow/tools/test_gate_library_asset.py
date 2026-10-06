#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 删除闸门「库内资产硬拦」离线回归（★ 12.3.0，真跑 deletegate，不需 MoviePilot）。

背景：静默池「阶段2 清旧」的前置条件是 —— **库内资产（已入库）必须被闸门硬拦**，
否则清理路径一旦误判，媒体库里的文件会失去宿主。

本测试直接加载真 ``features/deletegate.py``（合成父包解相对导入），断言：
  1) 种子账本 ``in_library=True`` → 拦；
  2) 种子账本身份「资源」(``sub=资源``) → 拦；
  3) 种子账本无标记、但其资源组 ``library.in_library=True`` → 拦（兜底链）；
  4) 普通种（无标记、无资源）→ 不拦；
  5) 账本读取抛异常 → 不崩、不误拦（与既有闸门各项同口径）；
  6) ``_delete_gate`` 与 ``_delete_gate_detail`` 口径一致（返回集合 = 明细键集）。

用法：``python3 tools/test_gate_library_asset.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_gate_lib_test"
NL = "normal-hash"


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
    """桩 app.*（common.py 顶部 import MoviePilot 依赖）。"""
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
        ("fingerprint", ("fingerprint", "inner_fingerprint", "info_hash", "Entry", "entries_fingerprint", "load_torrent_entries", "total_size")),
        ("fetcher", ("SiteCandidateTorrent",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    return _load(PKG + ".common", "common.py")


common = _load_common()
_tags = _load(PKG + ".tags", "tags.py")
dg = _load(PKG + ".features.deletegate", "features/deletegate.py")


class _Store:
    """最小账本桩：``items()`` + ``group_of()``。"""

    def __init__(self, items, group_of=None):
        self._it = dict(items or {})
        self._gf = group_of

    def items(self):
        return dict(self._it)

    def group_of(self, h):
        return self._gf(h) if callable(self._gf) else None


class Plug(dg.DeleteGateMixin):
    def __init__(self, led, groups=None, group_of=None, boom=False):
        self._led = led
        self._grp = groups or {}
        self._gof = group_of
        self._boom = boom
        self._store = None
        self._task_configs = {}

    def _tag_state(self):
        if self._boom:
            raise RuntimeError("ledger boom")
        return _Store(self._led)

    def _tag_groups(self):
        if self._boom:
            raise RuntimeError("groups boom")
        return _Store(self._grp, self._gof)

    def _crossseed_source_hashes(self):
        return set()

    def _claim_protected_hashes(self):
        return set()

    def _tag_all_torrents(self):
        return {}

    def _resource_source_index(self):
        return {}

    def _hr_obligation(self, site, t, snap=None):  # noqa: ANN001
        return (False, 0.0, 0.0, "")


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _why(p, hs):
    return dict(p._delete_gate_detail(hs))


def main() -> int:
    print("== 删除闸门「库内资产」硬拦（12.3.0）==")

    # 1) in_library=True
    p = Plug({"h-inlib": {"site": "s", "sub": "普通", "in_library": True, "state": "静默"}})
    w = _why(p, ["h-inlib"])
    _ok("h-inlib" in w and "库内资产" in w["h-inlib"], f"种子账本 in_library=True → 拦（{w.get('h-inlib','')}）")

    # 2) 身份「资源」
    p = Plug({"h-res": {"site": "s", "sub": "资源", "state": "魔力"}})
    w = _why(p, ["h-res"])
    _ok("h-res" in w and "库内资产" in w["h-res"], "身份「资源」→ 拦")

    # 3) 资源组 library.in_library=True（种子账本没带标记 → 兜底链命中）
    p = Plug({"h-grp": {"site": "s", "sub": "普通", "state": "静默"}},
             groups={"fp:abc": {"library": {"in_library": True}, "members": {"h-grp": {}}}},
             group_of=lambda h: "fp:abc" if h == "h-grp" else None)
    w = _why(p, ["h-grp"])
    _ok("h-grp" in w and "库内资产" in w["h-grp"], "资源组 library.in_library=True → 拦（兜底链）")

    # 4) 普通种不拦
    p = Plug({NL: {"site": "s", "sub": "普通", "state": "静默", "in_library": False}},
             groups={"fp:x": {"library": {"in_library": False}}},
             group_of=lambda h: "fp:x")
    w = _why(p, [NL])
    _ok(NL not in w, "普通种（无标记/无入库）→ 不拦")

    # 5) 账本读取异常 → 不崩、不误拦
    p = Plug({}, boom=True)
    w = _why(p, ["h-any"])
    _ok(w == {}, "账本读取抛异常 → 不崩、不误拦")

    # 6) _delete_gate == _delete_gate_detail.keys()
    p = Plug({"h-inlib": {"site": "s", "sub": "资源"}, "h-ok": {"site": "s", "sub": "普通"}})
    hs = ["h-inlib", "h-ok"]
    _ok(p._delete_gate(hs) == set(_why(p, hs).keys()), "_delete_gate 与 _delete_gate_detail 口径一致")

    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
