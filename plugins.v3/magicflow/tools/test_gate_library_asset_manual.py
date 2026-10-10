#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 库内资产「手动删除」专用闸门离线回归（★ 15.8.15，真跑 deletegate + downloader_ops）。

背景：Master「希望增加魔流库内资产手动删除的入口」。口径：
  - **只破第 5 类「库内资产（已入库，永不删）」**这一道闸；
  - 手动保留 / 跨站来源份（H&R 保种期）/ 已认领（保种承诺）/ 欠 H&R 义务 **四类照旧硬拦**；
  - 在途点播、音乐线（未下完）两条豁免不变；
  - **默认路径零变化**：不传 ``allow_library_asset=True`` 的一切调用方走的还是严格闸门。

断言：
  A. ``_delete_gate_detail(allow_asset=True)`` 跳过库内资产（种子账本 ``in_library`` / 身份「资源」/
     资源组兜底链三条全跳过），而严格闸门照拦；
  B. ``_delete_gate_manual`` 与 ``_delete_gate_detail(allow_asset=True)`` 口径一致；
  C. ``allow_asset=True`` **不**放行其余 4 类（手动保留 / 跨站来源份 / 已认领 / 欠 H&R）；
  D. ``allow_asset=True`` **不**破坏两条豁免（在途点播 / 未下完音乐线仍放行；下完音乐线仍按资产拦）；
  E. ``delete_torrents`` 闸门选边：默认取严格 ``gate``；``allow_library_asset=True`` 取 ``gate_manual``；
     **取不到 ``gate_manual`` 时回退严格 ``gate``**（绝不退化成「无闸门」）。

用法：``python3 tools/test_gate_library_asset_manual.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_gate_manual_test"


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

# 桩 MoviePilot（common.py / downloader_ops.py 顶部依赖）
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
    ("fingerprint", ("Entry", "entries_fingerprint", "info_hash", "load_torrent_entries",
                     "total_size", "inner_fingerprint", "fingerprint")),
    ("fetcher", ("SiteCandidateTorrent",)),
    ("qbsync", ("QB_SYNC_INCREMENTAL", "get_qb_sync_store")),
):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    _m.get_qb_sync_store = lambda: None  # noqa: E731
    sys.modules[PKG + "." + _modname] = _m

common = _load(PKG + ".common", "common.py")
_tags = _load(PKG + ".tags", "tags.py")
dg = _load(PKG + ".features.deletegate", "features/deletegate.py")
dops = _load(PKG + ".downloader_ops", "downloader_ops.py")


class _Store:
    """最小账本桩：``items()`` / ``group_of()`` / ``get_protected_torrents()``。"""

    def __init__(self, items=None, group_of=None, protected=None):
        self._it = dict(items or {})
        self._gf = group_of
        self._pt = set(protected or set())

    def items(self):
        return dict(self._it)

    def group_of(self, h):
        return self._gf(h) if callable(self._gf) else None

    def get_protected_torrents(self, _tid):
        return set(self._pt)

    # 兼容闸门里可能用到的其它读法
    def __iter__(self):
        return iter(self._it)


class Plug(dg.DeleteGateMixin):
    def __init__(self, led, groups=None, group_of=None, snap=None, protected=None,
                 crossseed=None, claim=None, hr_owed=False, boom=False):
        self._led = dict(led or {})
        self._grp = dict(groups or {})
        self._gof = group_of
        self._snap = dict(snap or {})
        self._protected = set(protected or set())
        self._crossseed = set(crossseed or set())
        self._claim = set(claim or set())
        self._hr_owed = bool(hr_owed)
        self._boom = bool(boom)
        self._task_configs = {}
        self._store = _Store(self._led, self._gof, self._protected)

    def _tag_state(self):
        if self._boom:
            raise RuntimeError("ledger boom")
        return _Store(self._led, self._gof, self._protected)

    def _tag_groups(self):
        if self._boom:
            raise RuntimeError("groups boom")
        return _Store(self._grp, self._gof)

    def _crossseed_source_hashes(self):
        return set(self._crossseed)

    def _claim_protected_hashes(self):
        return set(self._claim)

    def _tag_all_torrents(self):
        return dict(self._snap)

    def _resource_source_index(self):
        return {}

    def _hr_obligation(self, site, t, snap=None):  # noqa: ANN001
        if self._hr_owed:
            return (True, 72.0, 12.0, "hdsky")
        return (False, 0.0, 0.0, "")


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _strict(p, hs):
    return dict(p._delete_gate_detail(hs))


def _manual(p, hs):
    return dict(p._delete_gate_detail(hs, allow_asset=True))


def _music(h, progress=1.0):
    return types.SimpleNamespace(hash=h, title=h, state="pausedUP", size=1 << 30,
                                 tags=[], progress=progress, category="音乐",
                                 save_path="/vol6/1000/music", content_path=f"/vol6/1000/music/{h}")


def _normal(h):
    return types.SimpleNamespace(hash=h, title=h, state="pausedUP", size=1 << 30,
                                 tags=[], progress=1.0, category="",
                                 save_path="/x", content_path=f"/x/{h}")


def _fake_adapter(strict_block=None, manual_block=None, with_manual=True):
    """裸造 DownloaderAdapter（不过 __init__），只保留闸门选边所需的最小面。"""
    calls = []
    dl = object.__new__(dops.DownloaderAdapter)
    dl._downloader = object()          # truthy：过 `if not self._downloader`
    dl._emit_delete_log = lambda *a, **k: None
    dl._shared_file_hashes = lambda hs: set()
    dl.reannounce = lambda hs: (0, None)

    def _strict(hs):
        calls.append("strict")
        return set(strict_block or set())

    def _manual(hs):
        calls.append("manual")
        return set(manual_block or set())

    dl.gate = _strict
    if with_manual:
        dl.gate_manual = _manual
    return dl, calls


def main() -> int:
    print("== 库内资产「手动删除」专用闸门（15.8.15）==")

    # ---------------- A. 只破第 5 类 ----------------
    print("-- A. allow_asset=True 跳过「库内资产」，严格闸门照拦 --")
    p = Plug({"h-inlib": {"site": "s", "sub": "普通", "in_library": True, "state": "静默"}})
    _ok("h-inlib" in _strict(p, ["h-inlib"]), "严格闸门：账本 in_library=True → 拦")
    _ok("h-inlib" not in _manual(p, ["h-inlib"]), "手动闸门：账本 in_library=True → 放行（唯一豁免）")

    p = Plug({"h-res": {"site": "s", "sub": "资源", "state": "魔力"}})
    _ok("h-res" in _strict(p, ["h-res"]) and "h-res" not in _manual(p, ["h-res"]),
        "身份「资源」：严格拦 / 手动放行")

    p = Plug({"h-grp": {"site": "s", "sub": "普通", "state": "静默"}},
             groups={"fp:abc": {"library": {"in_library": True}, "members": {"h-grp": {}}}},
             group_of=lambda h: "fp:abc" if h == "h-grp" else None)
    _ok("h-grp" in _strict(p, ["h-grp"]) and "h-grp" not in _manual(p, ["h-grp"]),
        "资源组兜底链 library.in_library=True：严格拦 / 手动放行")

    p = Plug({"h-plain": {"site": "s", "sub": "普通", "state": "静默", "in_library": False}})
    _ok(_strict(p, ["h-plain"]) == {} and _manual(p, ["h-plain"]) == {},
        "普通种：两个闸门都不拦（行为不变）")

    # ---------------- B. 两个入口口径一致 ----------------
    print("-- B. _delete_gate_manual 与 detail(allow_asset=True) 口径一致 --")
    p = Plug({"h-inlib": {"site": "s", "sub": "资源", "in_library": True},
              "h-ok": {"site": "s", "sub": "普通"}},
             protected={"h-prot"}, crossseed={"h-cs"}, claim={"h-cl"}, hr_owed=True,
             snap={"h-prot": _normal("h-prot"), "h-cs": _normal("h-cs"),
                   "h-cl": _normal("h-cl"), "h-inlib": _normal("h-inlib"),
                   "h-ok": _normal("h-ok")})
    hs = ["h-inlib", "h-ok", "h-prot", "h-cs", "h-cl"]
    _ok(p._delete_gate_manual(hs) == set(_manual(p, hs).keys()),
        "_delete_gate_manual == detail(allow_asset=True).keys()")

    # ---------------- C. 其余 4 类照旧硬拦 ----------------
    print("-- C. allow_asset=True 不放行其余 4 类 --")
    _ok("h-prot" in _manual(p, ["h-prot"]), "手动保留：手动闸门**照拦**")
    _ok("h-cs" in _manual(p, ["h-cs"]), "跨站来源份（H&R 保种期）：手动闸门**照拦**")
    _ok("h-cl" in _manual(p, ["h-cl"]), "已认领（保种承诺）：手动闸门**照拦**")
    _ok("欠 H&R" in str(_manual(p, ["h-ok"]).get("h-ok", "")), "欠 H&R 义务：手动闸门**照拦**")

    # 四条理由逐字保留（前端原样透传 block，改文案会破坏既有 UI 契约）
    _ok(_manual(p, ["h-prot"])["h-prot"] == "手动保留", "理由逐字：手动保留")
    _ok(_manual(p, ["h-cs"])["h-cs"] == "跨站来源份（H&R 保种期）", "理由逐字：跨站来源份")
    _ok(_manual(p, ["h-cl"])["h-cl"] == "已认领（保种承诺）", "理由逐字：已认领")

    # ---------------- D. 两条豁免不变 ----------------
    print("-- D. 两条豁免不变（在途点播 / 未下完音乐线）--")
    p = Plug({"h-od": {"site": "s", "sub": "资源", "state": "点播", "in_library": True,
                       "taken_by": "__ondemand__"}})
    _ok("h-od" not in _manual(p, ["h-od"]), "在途点播：手动闸门仍豁免")

    p = Plug({"h-mus": {"site": "CARPT", "sub": "资源", "state": "静默", "in_library": True}},
             snap={"h-mus": _music("h-mus", progress=0.4)})
    _ok("h-mus" not in _manual(p, ["h-mus"]), "音乐线「下载中」：手动闸门仍豁免")

    p = Plug({"h-musdone": {"site": "CARPT", "sub": "资源", "state": "静默", "in_library": True}},
             snap={"h-musdone": _music("h-musdone", progress=1.0)})
    _ok("h-musdone" in _strict(p, ["h-musdone"]) and "h-musdone" not in _manual(p, ["h-musdone"]),
        "音乐线「下完」= 库内资产：严格闸门照拦 / **手动闸门放行**（这正是本入口要删的那一类）")

    # ---------------- E. delete_torrents 闸门选边 ----------------
    print("-- E. delete_torrents：默认严格 / True 取 gate_manual / 缺 gate_manual 回退严格 --")
    h = "aaaa"
    dl, calls = _fake_adapter(strict_block={h}, manual_block=set())
    try:
        res = dl.delete_torrents([h], allow_library_asset=True)
    except Exception:  # noqa: BLE001  （闸门之后无真下载器，尾部失败与本题无关）
        res = None
    _ok(calls == ["manual"], f"allow_library_asset=True → 只问 gate_manual（calls={calls}）")
    _ok(not (isinstance(res, tuple) and "闸门" in str(res[1])),
        "allow_library_asset=True → 未被严格闸门拦（res=%r）" % (res,))

    dl, calls = _fake_adapter(strict_block={h}, manual_block=set())
    try:
        res2 = dl.delete_torrents([h])
    except Exception:  # noqa: BLE001
        res2 = None
    _ok(calls == ["strict"], f"默认（不传 allow_library_asset）→ 只问严格 gate（calls={calls}）")
    _ok(res2 == (0, None), "默认路径：被严格闸门拦 → 返回 (0, None)（既有行为零变化）")

    dl, calls = _fake_adapter(strict_block={h}, with_manual=False)
    try:
        res3 = dl.delete_torrents([h], allow_library_asset=True)
    except Exception:  # noqa: BLE001
        res3 = None
    _ok(calls == ["strict"], f"缺 gate_manual → 回退严格 gate（calls={calls}）")
    _ok(res3 == (0, None), "缺 gate_manual + 库内资产被严格闸门拦 → (0, None)（绝不退化成无闸门）")

    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
