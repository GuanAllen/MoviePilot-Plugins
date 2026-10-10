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
  6) ``_delete_gate`` 与 ``_delete_gate_detail`` 口径一致（返回集合 = 明细键集）；
  7) ★ 15.8.11 同版补丁：**音乐线**（qB 分类=音乐）身份=「资源」（同点播），按 Master 口径
     「身份标签的要求要跟点播的资源一样 / 支持手动删除**未下完**的种子」→ **只豁免「下载中」
     （progress<1）**，与 15.8.5 的在途点播一一对应：在途音乐种的身份轴 / 派生库记 / 兜底资源组
     库记都不拦（手删得掉）；**下完**（progress=1）即身份=资源，与其它资源同口径仍拦；
     非音乐同形仍拦；音乐种不在快照里仍拦（fail-closed）。

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
    def __init__(self, led, groups=None, group_of=None, boom=False, snap=None):
        self._led = led
        self._grp = groups or {}
        self._gof = group_of
        self._boom = boom
        self._snap = dict(snap or {})
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
        return dict(self._snap)

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

    # ★ 15.8.11 同版补丁：音乐线（qB 分类=音乐）身份=「资源」，口径「跟点播的资源一样」——
    #   点播只豁免**在途**，所以音乐线也只豁免**下载中**：未下完的手删得掉，下完的按资源硬拦。
    def _music(h, progress=1.0):
        return types.SimpleNamespace(hash=h, title=h, state="pausedUP", size=1 << 30,
                                     tags=[], progress=progress, category="音乐",
                                     save_path="/vol6/1000/music", content_path=f"/vol6/1000/music/{h}")

    def _normal(h):
        return types.SimpleNamespace(hash=h, title=h, state="pausedUP", size=1 << 30,
                                     tags=[], progress=1.0, category="",
                                     save_path="/x", content_path=f"/x/{h}")

    # 7) 音乐线「下载中」+ 账本 sub=资源 + in_library=True（⑨资产刷新按身份派生的库记）→ 不拦
    p = Plug({"h-mus": {"site": "CARPT", "sub": "资源", "state": "静默", "in_library": True}},
             snap={"h-mus": _music("h-mus", progress=0.4)})
    w = _why(p, ["h-mus"])
    _ok("h-mus" not in w, "音乐线「下载中」+ 身份=资源 + 派生库记 → 不拦（未下完手删得掉）")

    # 8) 音乐线「下载中」+ 资源组 library.in_library=True（兜底链）→ 也不拦
    p = Plug({"h-mus2": {"site": "CARPT", "sub": "资源", "state": "静默"}},
             groups={"fp:m": {"library": {"in_library": True}, "members": {"h-mus2": {}}}},
             group_of=lambda h: "fp:m" if h == "h-mus2" else None,
             snap={"h-mus2": _music("h-mus2", progress=0.4)})
    w = _why(p, ["h-mus2"])
    _ok("h-mus2" not in w, "音乐线「下载中」兜底链（资源组库记）→ 不拦")

    # 9) ★ 关键边界：音乐线**下完**（progress=1，身份=资源）→ 与其它资源同口径**仍拦**
    p = Plug({"h-musdone": {"site": "CARPT", "sub": "资源", "state": "静默", "in_library": True}},
             snap={"h-musdone": _music("h-musdone", progress=1.0)})
    w = _why(p, ["h-musdone"])
    _ok("h-musdone" in w and "库内资产" in w["h-musdone"],
        "音乐线「下完」（身份=资源）→ 仍拦（豁免只限未下完）")

    # 10) 对照：同样在途形态但**非音乐** → 仍拦
    p = Plug({"h-lib": {"site": "s", "sub": "资源", "state": "静默", "in_library": True}},
             snap={"h-lib": _normal("h-lib")})
    w = _why(p, ["h-lib"])
    _ok("h-lib" in w and "库内资产" in w["h-lib"], "对照：非音乐同形 → 仍拦（豁免只对音乐线）")

    # 11) 音乐线 qB 里没有（snap 缺失 / 取不到 progress）→ 按原口径拦（不能靠「看不见」放行）
    p = Plug({"h-mus3": {"site": "CARPT", "sub": "资源", "state": "静默"}})
    w = _why(p, ["h-mus3"])
    _ok("h-mus3" in w and "库内资产" in w["h-mus3"], "音乐种不在快照里 → 仍按库内资产拦（fail-closed）")

    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
