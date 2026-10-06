#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 决策路径「一轮只拉一次 qB 全量快照」离线回归测试（真跑，无需 MoviePilot）。

覆盖 P0 性能重构的两个硬指标：
  1. 决策函数 ``_hr_obligation`` / ``_hr_guard_tick`` 接受 ``snap=None`` 显式传参：
     传了 → 复用（同一轮内**不再**重拉 ``_tag_all_torrents``）；不传 → 照旧自拉（向后兼容）。
  2. 可观测：``common`` 里的快照轮跟踪器（``begin_decision_round`` / ``note_snapshot_pull`` /
     ``decision_round_stats``）正确计数 + 每轮归零；注入的 ``_decision_round_note_pull``
     钩子能计数「回退拉取」，据此断言「同一轮内快照只拉 1 次」。

用法：``python3 tools/test_snapshot_once.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PKG = "mf_snapshot_once_test"


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

fingerprint = _load(PKG + ".fingerprint", "fingerprint.py")
crossseed = _load(PKG + ".crossseed", "crossseed.py")
persistence = _load(PKG + ".persistence", "persistence.py")
tags = _load(PKG + ".tags", "tags.py")
hrbills = _load(PKG + ".features.hrbills", "features/hrbills.py")
hr = _load(PKG + ".features.hr", "features/hr.py")

HrMixin = hr.HrMixin
HrBillsMixin = hrbills.HrBillsMixin


# ---------------------------------------------------------------------------
# 以「stub app.*」加载 common.py（它顶部 import app.plugins/app.schemas 等 MoviePilot 依赖）
# ---------------------------------------------------------------------------
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
        ("fingerprint", ("fingerprint", "inner_fingerprint", "load_torrent_entries", "total_size")),
        ("fetcher", ("SiteCandidateTorrent",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    return _load(PKG + ".common", "common.py")


common = _load_common()


def _torrent(hash_string="", progress=0.0, seed_time=0.0, hit_and_run=False,
             title="test", tracker=""):
    return types.SimpleNamespace(
        hash=str(hash_string).lower(), title=title, progress=progress,
        seed_time=seed_time, hit_and_run=hit_and_run, tags=[], tracker=tracker,
    )


class _Ledger:
    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)


class _Groups:
    def __init__(self, data, group_of_map):
        self._data = data
        self._group_of_map = group_of_map

    def items(self):
        return dict(self._data)

    def group_of(self, hash_string):
        return self._group_of_map.get(str(hash_string).lower(), "")


class Harness(HrMixin, HrBillsMixin):
    """带桩的最小插件实例：计数 ``_tag_all_torrents`` 真实拉取 + 注入 core 的观测钩子。"""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._hot = None
        self.torrents: dict = {}        # hash -> SimpleNamespace
        self.ledger: dict = {}          # hash -> rec
        self.pulls = 0                  # _tag_all_torrents 真实调用次数
        self.note_pulls = 0             # 注入的 _decision_round_note_pull 计数
        self.rounds_begun = 0           # _decision_round_begin 计数
        self.rounds_ended = 0           # _decision_round_end 计数
        self.ridx: dict = {}            # _resource_source_index 返回值

    # ---- 计数快照 ----
    def _tag_all_torrents(self):
        self.pulls += 1
        return dict(self.torrents)

    def _tag_state(self):
        return _Ledger(self.ledger)

    def _tag_groups(self):
        return _Groups({}, {})

    def _crossseed_sources(self):
        return {}

    def _crossseed_source_hashes(self):
        return set()

    def get_data_path(self):
        return self._data_dir

    # ---- 让 _hr_obligation 的资源级分支触发（需要 src_hash） ----
    def _resource_source_index(self):
        return dict(self.ridx)

    def _hr_obligation_by_seed(self, site, torrent):
        return (False, 0.0, 0.0, "")

    def _site_domain_by_name(self, name):
        return str(name or "").strip().lower()

    def _crossseed_hr_decision(self, domain, torrent_hr=None):
        return (True, 24.0, "site")

    def _crossseed_seed_need_hours(self, domain):
        return 24.0

    def _torrent_site_name(self, tags, fallback=""):
        return str(fallback or "")

    # ---- 注入 core.py 的观测钩子（生产里由 CoreMixin 提供） ----
    def _decision_round_begin(self, label=""):
        self.rounds_begun += 1

    def _decision_round_note_pull(self):
        self.note_pulls += 1

    def _decision_round_end(self):
        self.rounds_ended += 1


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _build_harness() -> Harness:
    """构造一个「资源级欠债可触发」的场景：bbbb 的资源来源种是 aaaa。"""
    h = Harness(Path(tempfile.mkdtemp(prefix="snapshot_once_")))
    src = _torrent(hash_string="aaaa", progress=1.0, seed_time=100.0 * 3600.0)
    tgt = _torrent(hash_string="bbbb", progress=1.0, seed_time=5.0 * 3600.0)
    h.torrents["aaaa"] = src
    h.torrents["bbbb"] = tgt
    h.ledger["bbbb"] = {"site": "hdfans.org", "state": "保种", "sub": "resource", "taken_by": "__hr_host__"}
    h.ridx["bbbb"] = ("hdfans.org", "aaaa", False, [])
    return h


def main() -> int:
    print("=" * 64)
    print("魔流 · 决策路径「一轮只拉一次 qB 全量快照」回归测试")
    print("=" * 64)

    # =====================================================================
    # 0) common 快照轮跟踪器（模块级工厂，纯观测）
    # =====================================================================
    print("\n[0] common 快照轮跟踪器")
    sr = common.SnapshotRound()
    r0 = sr.begin()
    sr.note_pull(3)
    st0 = sr.stats()
    _ok(st0["pulls"] == 3, f"note_pull(3) → pulls=3（{st0['pulls']}）")
    _ok(st0["round_id"] == r0, f"round_id={r0}（{st0['round_id']}）")
    sr.begin()   # 已在轮内 → 不重置（嵌套保护：一轮里再进闸门不会把计数清零）
    _ok(sr.stats()["pulls"] == 3, f"轮内重复 begin() 不重置（{sr.stats()['pulls']}）")
    sr.end()
    r1 = sr.begin()   # 收尾后新轮归零
    _ok(sr.stats()["pulls"] == 0, f"收尾后 begin() 归零 pulls=0（{sr.stats()['pulls']}）")
    _ok(r1 == r0 + 1, f"round_id 自增（{r1}）")

    print("\n[0b] common 模块级工厂（跨热重载单例语义）")
    a = common._get_snapshot_round()
    b = common._get_snapshot_round()
    _ok(a is b, "两次 _get_snapshot_round() 返回同一实例（模块级单例）")
    common.begin_decision_round()
    common.note_snapshot_pull(1)
    common.note_snapshot_pull(1)
    _ok(common.decision_round_stats()["pulls"] == 2,
        f"begin + note×2 → pulls=2（{common.decision_round_stats()['pulls']}）")
    common.end_decision_round()
    common.begin_decision_round()
    _ok(common.decision_round_stats()["pulls"] == 0, "收尾后新轮归零")

    # =====================================================================
    # 1) _hr_obligation 显式传 snap → 复用，不再拉
    # =====================================================================
    print("\n[1] _hr_obligation(snap=...) 复用快照")
    h = _build_harness()
    snap = h._tag_all_torrents()          # 模拟「轮入口已拉好」的快照
    h.pulls = 0
    tgt = h.torrents["bbbb"]
    r1 = h._hr_obligation("hdfans.org", tgt, snap=snap)
    _ok(h.pulls == 0, f"传 snap → _tag_all_torrents 重拉 0 次（{h.pulls}）")
    _ok(h.note_pulls == 0, f"传 snap → 回退计数钩子未触发（{h.note_pulls}）")
    _ok(r1[0] is False, f"判定不欠（资源来源种已挂够，{r1}）")

    print("\n[2] _hr_obligation() 不传 snap → 照旧自拉一次（向后兼容）")
    h.pulls = 0
    h.note_pulls = 0
    r2 = h._hr_obligation("hdfans.org", tgt)
    _ok(h.pulls == 1, f"不传 snap → 自拉 1 次（{h.pulls}）")
    _ok(h.note_pulls == 1, f"不传 snap → 回退计数钩子触发 1 次（{h.note_pulls}）")
    _ok(r2[0] is False, f"判定一致（不欠，{r2}）")

    # =====================================================================
    # 2) _hr_guard_tick 一轮只拉一次
    # =====================================================================
    print("\n[3] _hr_guard_tick(snap=...) 一轮内复用快照")
    h = _build_harness()
    snap = h._tag_all_torrents()
    h.pulls = 0
    rep3 = h._hr_guard_tick(apply=False, snap=snap)
    _ok(h.pulls == 0, f"传 snap → 巡检整轮重拉 0 次（{h.pulls}）")
    _ok(h.note_pulls == 0, f"传 snap → 回退计数 0 次（{h.note_pulls}）")
    _ok(rep3["checked"] == 1, f"巡检扫描 1 个完成种（{rep3['checked']}）")
    _ok(h.rounds_begun == 1 and h.rounds_ended == 1,
        f"begin/end 各触发 1 次（{h.rounds_begun}/{h.rounds_ended}）")

    print("\n[4] _hr_guard_tick() 不传 snap → 入口自拉一次 + 传下复用（一轮仍 1 次）")
    h = _build_harness()
    rep4 = h._hr_guard_tick(apply=False)
    _ok(h.pulls == 1, f"入口自拉 1 次，下游 _hr_obligation 复用不重拉（{h.pulls}）")
    _ok(h.note_pulls == 1, f"回退计数 1 次（{h.note_pulls}）")
    _ok(rep4["checked"] == 1, f"巡检扫描 1 个完成种（{rep4['checked']}）")
    _ok(h.rounds_begun == 1 and h.rounds_ended == 1,
        f"begin/end 各触发 1 次（{h.rounds_begun}/{h.rounds_ended}）")

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
