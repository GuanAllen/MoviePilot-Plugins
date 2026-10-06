#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 11.11.1 H&R 口径修正（辅种不判 H&R / 救援独立分类 / 手动种打标）离线回归测试。

覆盖（对应 11.11.1 Master 拍板）：
  A. 辅种不判 H&R：
     - ``_hrbills_open`` / ``_hrbills_backfill`` 跳过 复用(魔流-辅种)/跨站(魔流-跨站)/补源(魔流-补源)；
     - ``_hr_obligation`` / ``_hr_obligation_by_seed`` 对复用/补源副本返回「不欠」；
     - ``_hrbills_void_reuse``：存量 active 辅种账单作废（干跑 + confirm）。
  B. 站点真实要求时间：``_hr_need_hours`` 取值链（seed_need_hours → 保守默认 24h）。
  C. 救援独立分类：``RESCUE_TAG`` 常量 + ``is_reuse_copy``（复用/补源归「非真实下载」）。
  D. 手动/MP 加的种打「预期标记」：``EXTERNAL_TAG`` + ``is_external_candidate``（纯函数）。

用法：``python3 tools/test_hr_reuse.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PKG = "mf_hr_reuse_test"


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

tags = _load(PKG + ".tags", "tags.py")
fingerprint = _load(PKG + ".fingerprint", "fingerprint.py")
crossseed = _load(PKG + ".crossseed", "crossseed.py")
persistence = _load(PKG + ".persistence", "persistence.py")
downloader_ops = _load(PKG + ".downloader_ops", "downloader_ops.py")
hrbills = _load(PKG + ".features.hrbills", "features/hrbills.py")
hr = _load(PKG + ".features.hr", "features/hr.py")

HrMixin = hr.HrMixin
HrBillsMixin = hrbills.HrBillsMixin
HrBillsStore = hrbills.HrBillsStore
MARK_REUSE = tags.MARK_REUSE
RESCUE_TAG = tags.RESCUE_TAG
EXTERNAL_TAG = tags.EXTERNAL_TAG
CROSSSEED_TAG = crossseed.CROSSSEED_TAG
is_reuse_copy = tags.is_reuse_copy
is_external_candidate = tags.is_external_candidate

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _torrent(hash_string="", progress=1.0, seed_time=0.0, title="test", tracker="hdfans.org",
             tags=None, hit_and_run=False):
    return types.SimpleNamespace(
        hash=str(hash_string).lower(), title=title, progress=progress,
        seed_time=seed_time, hit_and_run=hit_and_run, tags=list(tags or []),
        tracker=tracker, completion_on=0.0,
    )


def _torrent_bytes(name="test") -> bytes:
    info = {b"name": name.encode("utf-8"), b"length": 1000, b"piece length": 16384,
            b"pieces": b"0" * 20}
    meta = {b"info": info, b"announce": b"http://hdfans.org/announce"}
    return fingerprint.bencode(meta)


class _Ledger:
    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)


class _Groups:
    def __init__(self, data=None, group_of_map=None):
        self._data = data or {}
        self._group_of_map = group_of_map or {}

    def items(self):
        return dict(self._data)

    def group_of(self, hash_string):
        return self._group_of_map.get(str(hash_string).lower(), "")


class Harness(HrMixin, HrBillsMixin):
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._hot = None
        self.site_hr: dict = {}
        self.need_hours: dict = {}
        self.torrents: dict = {}
        self.ledger: dict = {}
        self.name2dom: dict = {}
        self.groups_data: dict = {}
        self.group_of_map: dict = {}

    def get_data_path(self):
        return self._data_dir

    def _site_hr_flag(self, dom):
        return self.site_hr.get(dom)

    def _crossseed_seed_need_hours(self, dom):
        return self.need_hours.get(dom, 0.0)

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _tag_state(self):
        return _Ledger(self.ledger)

    def _tag_groups(self):
        return _Groups(self.groups_data, self.group_of_map)

    def _site_domain_by_name(self, name):
        if not name:
            return ""
        if "." in name and " " not in name:
            return name.lower()
        return self.name2dom.get(name, "")

    def _resource_source_index(self):
        return {}


def main() -> int:
    print("=" * 64)
    print("魔流 · 11.11.1 H&R 口径修正（辅种/救援/手动种）回归测试")
    print("=" * 64)

    tmp = tempfile.mkdtemp(prefix="hr_reuse_test_")
    h = Harness(Path(tmp))
    h.site_hr["hdfans.org"] = True
    h.need_hours["hdfans.org"] = 20.0

    # ---- 0) 常量 / 纯函数 ----
    print("\n[0] 常量 / 纯函数")
    _ok(MARK_REUSE == "魔流-辅种", f"MARK_REUSE = {MARK_REUSE!r}")
    _ok(RESCUE_TAG == "魔流-补源", f"RESCUE_TAG = {RESCUE_TAG!r}")
    _ok(EXTERNAL_TAG == "魔流-外部", f"EXTERNAL_TAG = {EXTERNAL_TAG!r}")
    _ok(RESCUE_TAG in tags.SPECIAL_TAGS and EXTERNAL_TAG in tags.SPECIAL_TAGS,
        "RESCUE_TAG / EXTERNAL_TAG 已登记进 SPECIAL_TAGS（retag 会保留）")
    _ok(is_reuse_copy([MARK_REUSE]) is True, "is_reuse_copy(魔流-辅种) = True")
    _ok(is_reuse_copy([RESCUE_TAG]) is True, "is_reuse_copy(魔流-补源) = True")
    _ok(is_reuse_copy(["魔流-跨站"]) is False, "is_reuse_copy(魔流-跨站) = False（跨站是真实下载）")
    _ok(is_reuse_copy(["魔流-hdfans-刷流"]) is False, "is_reuse_copy(刷流标签) = False")
    _ok(is_external_candidate(["MOVIEPILOT", "魔流-hdfans-静默-资源"]) is True,
        "is_external_candidate(MOVIEPILOT + 已纳管) = True")
    _ok(is_external_candidate(["MOVIEPILOT"]) is False, "is_external_candidate(仅 MOVIEPILOT 未纳管) = False")
    _ok(is_external_candidate(["MOVIEPILOT", "魔流-hdfans-静默-资源", EXTERNAL_TAG]) is False,
        "is_external_candidate(已打标) = False")
    _ok(is_external_candidate(["魔流-hdfans-刷流"]) is False, "is_external_candidate(无 MOVIEPILOT) = False")

    # ---- 1) 开账跳过辅种（复用/跨站/补源）----
    print("\n[1] 开账跳过辅种")
    store = h._hrbills_store()
    n0 = len(store.all())
    t_reuse = _torrent(hash_string="r1", tags=[MARK_REUSE])
    h.torrents["r1"] = t_reuse
    b_reuse = h._hrbills_open("r1", "hdfans.org", MARK_REUSE, _torrent_bytes("a"))
    _ok(b_reuse is None, "复用辅种(MARK_REUSE) 开账被跳过")
    b_rescue = h._hrbills_open("r2", "hdfans.org", RESCUE_TAG, _torrent_bytes("b"))
    _ok(b_rescue is None, "补源副本(RESCUE_TAG) 开账被跳过")
    b_cross = h._hrbills_open("r3", "hdfans.org", CROSSSEED_TAG, _torrent_bytes("c"))
    _ok(b_cross is None, "跨站(CROSSSEED_TAG) 开账被跳过")
    _ok(len(store.all()) == n0, "账单数不变（辅种一律不开账）")

    # ---- 2) 回填跳过辅种 ----
    print("\n[2] 回填跳过辅种")
    h.ledger = {
        "r1": {"site": "hdfans.org", "state": "静默", "sub": "资源"},
        "r2": {"site": "hdfans.org", "state": "静默", "sub": "资源"},
        "r3": {"site": "hdfans.org", "state": "静默", "sub": "资源"},
        "real": {"site": "hdfans.org", "state": "静默", "sub": "资源"},
    }
    h.torrents["real"] = _torrent(hash_string="real", tags=["魔流-hdfans-静默-资源"])
    h.torrents["r1"] = _torrent(hash_string="r1", tags=[MARK_REUSE, "魔流-hdfans-静默-资源"])
    h.torrents["r2"] = _torrent(hash_string="r2", tags=[RESCUE_TAG])
    h.torrents["r3"] = _torrent(hash_string="r3", tags=[CROSSSEED_TAG])
    bf = h._hrbills_backfill(store, h.torrents, limit=200)
    _ok(store.get("real") is not None, "真实下载种照常开账")
    _ok(store.get("r1") is None, "复用辅种回填跳过")
    _ok(store.get("r2") is None, "补源副本回填跳过")
    _ok(store.get("r3") is None, "跨站种回填跳过")
    _ok(int(bf.get("opened") or 0) == 1, f"回填只开 1 张（实际 {bf.get('opened')}）")

    # ---- 3) _hr_obligation / _hr_obligation_by_seed：辅种不判 H&R ----
    print("\n[3] 辅种不判 H&R")
    t_ob = _torrent(hash_string="ob1", tags=[MARK_REUSE], progress=1.0)
    owed, need, seeded, src = h._hr_obligation("hdfans.org", t_ob)
    _ok(owed is False, f"复用辅种 _hr_obligation → 不欠（owed={owed}）")
    _ok(src == "复用/补源副本(非真实下载)", f"来源串 = {src!r}")
    t_ob2 = _torrent(hash_string="ob2", tags=[RESCUE_TAG], progress=1.0)
    owed2, _, _, src2 = h._hr_obligation_by_seed("hdfans.org", t_ob2)
    _ok(owed2 is False and "补源" in str(src2), "补源副本 _hr_obligation_by_seed → 不欠")
    t_real = _torrent(hash_string="ob3", tags=["魔流-hdfans-刷流"], progress=1.0)
    _ok(h._hr_obligation("hdfans.org", t_real)[0] is True,
        "真实下载种仍正常判 H&R（资源级/种子级照常）")

    # ---- 4) 存量 active 辅种账单作废（干跑 + confirm）----
    print("\n[4] 存量 active 辅种账单作废")
    for hs, tgs in (("v1", [MARK_REUSE]), ("v2", [RESCUE_TAG]), ("v3", ["魔流-hdfans-刷流"])):
        h.torrents[hs] = _torrent(hash_string=hs, tags=tgs, progress=1.0)
    for hs in ("v1", "v2", "v3"):
        store.put(hs, {"site": "hdfans.org", "rule": "site_hr", "state": "active",
                       "need_h": 20.0, "seeded_h": 1.0, "fp": "", "title": "x",
                       "opened_at": time.time(), "last_progress": 1.0,
                       "last_progress_at": time.time(), "progress": 1.0,
                       "opened_by": "backfill"})
    dry = h._hrbills_void_reuse(confirm=False)
    _ok(dry["dry_run"] is True, "默认干跑")
    _ok(dry["count"] == 2, f"干跑识别 2 张辅种账单（实际 {dry['count']}）")
    _ok({x["hash"] for x in dry["targets"]} == {"v1", "v2"}, "干跑只圈 复用/补源，不碰真实下载")
    _ok(store.get("v1")["state"] == "active", "干跑不改账单状态")
    res = h._hrbills_void_reuse(confirm=True)
    _ok(res["voided"] == 2, f"confirm 作废 2 张（实际 {res['voided']}）")
    _ok(store.get("v1")["state"] == "void" and store.get("v1")["void_reason"] == "reuse_not_hr",
        "作废后 state=void + void_reason=reuse_not_hr")
    _ok(store.get("v3")["state"] == "active", "真实下载种账单不动（仍 active）")

    # ---- 5) _hr_need_hours 取值链 ----
    print("\n[5] _hr_need_hours 取值链（不再写死 24）")
    _ok(abs(h._hr_need_hours("hdfans.org") - 20.0) < 1e-9, "seed_need_hours=20 → need=20")
    _ok(abs(h._hr_need_hours("carpt.net") - 24.0) < 1e-9, "未配 seed_need_hours → 保守默认 24")
    h.need_hours["hdfans.org"] = 0.0
    _ok(abs(h._hr_need_hours("hdfans.org") - 24.0) < 1e-9, "seed_need_hours=0 → 保守默认 24")

    # ---- 6) limit 口径（11.12.0：0=不限；路由默认不再截断）----
    #   背景：`get_tag_model(..., limit=20)` 的默认把「不限」暗中变成「限 20」→
    #   `hrbills_void_reuse` dry-run 只报 20（真实 246），曾被误判为「漏检 bug」。
    print("\n[6] limit 口径（0=不限；路由默认不再截断）")
    for i in range(25):
        hh = f"lim{i:02d}"
        h.torrents[hh] = _torrent(hash_string=hh, tags=[MARK_REUSE], progress=1.0)
        store.put(hh, {"site": "hdfans.org", "rule": "site_hr", "state": "active",
                       "need_h": 20.0, "seeded_h": 1.0, "fp": "", "title": "x",
                       "opened_at": time.time(), "last_progress": 1.0,
                       "last_progress_at": time.time(), "progress": 1.0,
                       "opened_by": "backfill"})
    full = h._hrbills_void_reuse(confirm=False, limit=0)
    _ok(full["count"] >= 25 and full["capped"] is False,
        f"limit=0 → 不限（count={full['count']}, capped={full['capped']}）")
    capped = h._hrbills_void_reuse(confirm=False, limit=10)
    _ok(capped["count"] == 10 and capped["capped"] is True,
        f"limit=10 → 截断到 10 且 capped=True（count={capped['count']}）")
    _ok(int(capped.get("limit") or 0) == 10, f"回显 limit=10（实际 {capped.get('limit')}）")
    # 静态护栏：路由 `get_tag_model` 的 limit 默认必须是 0（防回退成 20 再吞掉「不限」）
    import ast as _ast
    _src = (ROOT / "features" / "tags.py").read_text(encoding="utf-8")
    _default = None
    for _n in _ast.walk(_ast.parse(_src)):
        if isinstance(_n, _ast.FunctionDef) and _n.name == "get_tag_model":
            _args = _n.args.args
            _defs = _n.args.defaults
            for _a, _d in zip(_args[len(_args) - len(_defs):], _defs):
                if _a.arg == "limit" and isinstance(_d, _ast.Constant):
                    _default = _d.value
    _ok(_default == 0, f"get_tag_model(limit=…) 路由默认 = 0（实际 {_default}）")

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
