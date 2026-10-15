#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · P5b 隔离区 H&R 真值源 + ``settled`` 口径收敛 —— 离线回归测试。

背景（缺陷核实）：
  A. ``features/silent.py`` 的隔离区计数（``_silent_host_card`` 的 ``hr_count``）原先读
     ``MARK_HR`` 标签；而 ``features/hr.py:551`` 明写 7.0.0 起标签退役、H&R 状态账本化
     ⇒ 该标签不再有人写，老种身上的旧标签会把「账本已不欠」的种永远算进隔离区。
  B. ``ledger.py`` 的 ``mf_resource.hrs[*].settled`` 唯一推进方 ``note_hr_progress``
     全仓零调用、``set_hr`` 只写默认 ``False`` ⇒ 该字段恒假，读它就是「永远未结清」（过保护）。

本测试只覆盖 P5b 改动面（纯 stdlib、全 stub、离线、不联网、不碰数据库）：
  ① 有 ``MARK_HR`` 标签但账本不欠 → **不计入**隔离区；
  ② 账本/账单欠 H&R 但无标签 → **计入**；
  ③ 缺数据 / 判定异常 → **计入**（fail-safe，绝不因缺数据少算）；
  ④ ``settled`` 语义：账单**未结清**（live active）判「欠」；已结清判「不欠」；
     且「历史只读」的 ``mf_resource.hrs[*].settled`` 不参与判定（结构性锁死零调用方）。
  ⑤ 前端在用的字段名 ``hr_count`` / ``nonhr_count`` 保持不变。

用法：``python3 tools/test_p5b_hr_truth.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_p5b_test"

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


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


# ---- stub MoviePilot 宿主模块（silent/common 需要 app.schemas / app.sdk） ----
_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")
for _n, _attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": type("EventType", (), {})}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
):
    _m = sys.modules.get(_n)
    if _m is None:
        _m = types.ModuleType(_n)
        sys.modules[_n] = _m
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)
for _modname, _attrs2 in (
    ("bonus", ("TorrentBonusInfo", "calc_bonus_per_hour")),
    ("fetcher", ("SiteCandidateTorrent",)),
    ("recommend", ("recognize",)),
):
    _m2 = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs2:
        setattr(_m2, _a, object)
    sys.modules[PKG + "." + _modname] = _m2

tags = _load(PKG + ".tags", "tags.py")
silent = _load(PKG + ".features.silent", "features/silent.py")

MARK_HR = tags.MARK_HR          # "魔流-H&R"（7.0.0 起退役、不再有人写）
STATE_SILENT = tags.STATE_SILENT


def _torrent(h: str, tgs=None, **kw):
    t = types.SimpleNamespace(
        hash=h, title=f"种-{h}", tags=list(tgs or []), progress=1.0,
        seed_time=0.0, hit_and_run=False, tracker="hdfans.org",
        downloaded=1e9, category="电影", size_gb=10.0,
    )
    for k, v in kw.items():
        setattr(t, k, v)
    return t


class _State:
    """账本桩（``_tag_state().items()``）。"""

    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)


class Harness(silent.SilentMixin):
    """最小静默 mixin 桩：覆盖 ``_silent_host_card`` + ``_hr_obligated_truth`` 依赖。"""

    def __init__(self):
        self.torrents = {}
        self.ledger = {}
        self._tags_cfg = {"host_interval": 60}
        self.bills = {}            # hash -> {"state","need_h","seeded_h","rule"}（模型 hr_bills.json）
        self.oblig = {}            # hash -> (欠?, need, seeded, src)（显式覆盖，优先）
        self.owed = set()          # 站点 myhr 对账仍欠的 infohash
        self.oblig_raises = False
        self.all_raises = False
        self.recon_raises = False

    # ---- 静默 mixin 依赖 ----
    def _tag_all_torrents(self):
        if self.all_raises:
            raise RuntimeError("qB 快照不可用")
        return dict(self.torrents)

    def _tag_state(self):
        return _State(self.ledger)

    def _torrent_site_name(self, tgs, fallback=""):
        return "hdfans.org"

    def _hr_reconcile_cache(self):
        if self.recon_raises:
            raise RuntimeError("对账缓存不可用")
        cache = types.SimpleNamespace()
        cache.reports = lambda: {
            "hdfans.org": {"records": [{"infohash": h} for h in sorted(self.owed)]},
        }
        return cache

    # ---- H&R 真值桩（与 features/hr.py:339-348 第三来源同构）----
    def _hr_obligation(self, site, torrent, snap=None):
        if self.oblig_raises:
            raise RuntimeError("H&R 判定异常")
        h = str(getattr(torrent, "hash", "") or "").strip().lower()
        if h in self.oblig:
            return self.oblig[h]
        bill = self.bills.get(h)
        if isinstance(bill, dict) and str(bill.get("state") or "") == "active":
            need = float(bill.get("need_h") or 24.0)
            seeded = float(bill.get("seeded_h") or 0.0)
            return (seeded + 1e-6 < need, need, seeded, "hrbill")
        if isinstance(bill, dict):
            return (False, 0.0, 0.0, f"bill:{bill.get('state')}")
        return (False, 0.0, 0.0, "无账单")


def _silent_entry(h, site="hdfans.org", sub="普通"):
    return {h: {"state": STATE_SILENT, "site": site, "sub": sub}}


def _fn_missing(h: Harness) -> Harness:
    """把实例上的 ``_hr_obligation`` 遮蔽成 None（模拟判定函数缺失）。"""
    h._hr_obligation = None
    return h


def _count_call_sites(needle: str) -> int:
    """全仓 ``.py`` 里 ``needle(`` 的**调用**点数（排除 ``def`` 定义行与 ``callable(...)``）。

    ★ 修正：旧实现只查 ``needle in s``，把**单纯提到名字**的行也算成调用点
    （本文件自己的文档字符串/断言文案、``ledger.py`` 里的说明与 ``def`` 相邻行），
    于是「全仓零调用」永远判不出真值。真正的调用必然紧随左括号 ⇒ 以 ``needle(`` 为准。
    """
    n = 0
    for p in ROOT.rglob("*.py"):
        if ".worktrees" in p.parts or ".git" in p.parts:
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                s = line.strip()
                if f"{needle}(" not in s:
                    continue
                if s.startswith("def ") or s.startswith("async def "):
                    continue
                if s.startswith("#") or s.startswith('"') or s.startswith("'"):
                    continue
                if "getattr(" in s or "callable(" in s:
                    continue
                n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def main() -> int:
    print("=" * 68)
    print("魔流 · P5b 隔离区 H&R 真值源 + settled 口径收敛 离线回归")
    print("=" * 68)

    # ---- ① 有 MARK_HR 标签但账本不欠 → 不计入隔离区 ----
    print("\n[1] 有 MARK_HR 标签但账本不欠 → 不计入隔离区")
    h1 = Harness()
    h1.torrents["h1"] = _torrent("h1", [tags.tag_for("hdfans", STATE_SILENT, "普通"), MARK_HR])
    h1.ledger.update(_silent_entry("h1"))
    h1.bills["h1"] = {"state": "settled", "need_h": 24.0, "seeded_h": 24.0, "rule": "site_hr"}
    card1 = h1._silent_host_card()
    _ok(card1["seeding_count"] == 1, f"池内 1 个（{card1['seeding_count']}）")
    _ok(card1["hr_count"] == 0, f"★ 带退役 MARK_HR 标签但不欠 → hr_count=0（{card1['hr_count']}）")
    _ok(card1["nonhr_count"] == 1, f"nonhr_count=1（{card1['nonhr_count']}）")
    _ok(card1["classify"]["by_site"]["hdfans.org"]["hr"] == 0, "by_site.hr 同步为 0")

    # ---- ② 账本/账单欠 H&R 但无标签 → 计入 ----
    print("\n[2] 账本/账单欠 H&R 但无标签 → 计入")
    h2 = Harness()
    h2.torrents["h2"] = _torrent("h2", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h2.ledger.update(_silent_entry("h2"))
    h2.bills["h2"] = {"state": "active", "need_h": 24.0, "seeded_h": 0.0, "rule": "hit_and_run"}
    card2 = h2._silent_host_card()
    _ok(card2["hr_count"] == 1, f"★ 欠 H&R 无标签 → hr_count=1（{card2['hr_count']}）")
    _ok(card2["nonhr_count"] == 0, f"nonhr_count=0（{card2['nonhr_count']}）")
    _ok(card2["classify"]["by_site"]["hdfans.org"]["hr"] == 1, "by_site.hr 同步为 1")

    # ---- ②b 对账缓存 owed 命中（live 不欠）→ 仍计入（只增保护）----
    print("\n[2b] 站点对账 owed 命中 → 计入（OR，只增保护）")
    h2b = Harness()
    h2b.torrents["h2b"] = _torrent("h2b", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h2b.ledger.update(_silent_entry("h2b"))
    h2b.bills["h2b"] = {"state": "settled", "need_h": 24.0, "seeded_h": 24.0}
    h2b.owed = {"h2b"}
    _ok(h2b._silent_host_card()["hr_count"] == 1, "★ 对账说仍欠 → 计入（与 reportview owed 同源）")

    # ---- ③ fail-safe：判定异常 / 判定函数缺失 / hash 缺失 → 计入 ----
    print("\n[3] fail-safe：拿不准 → 计入")
    h3a = Harness()
    h3a.torrents["h3a"] = _torrent("h3a", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h3a.ledger.update(_silent_entry("h3a"))
    h3a.oblig_raises = True
    _ok(h3a._silent_host_card()["hr_count"] == 1, "★ _hr_obligation 抛异常 → 计入（不吞成 0）")

    h3b = _fn_missing(Harness())
    h3b.torrents["h3b"] = _torrent("h3b", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h3b.ledger.update(_silent_entry("h3b"))
    _ok(h3b._silent_host_card()["hr_count"] == 1, "★ 判定函数缺失 → 计入")

    h3c = Harness()
    h3c.torrents["h3c"] = _torrent("", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h3c.ledger.update(_silent_entry("h3c"))
    _ok(h3c._silent_host_card()["hr_count"] == 1, "★ 种 hash 缺失 → 计入")

    h3d = Harness()
    h3d.torrents["h3d"] = _torrent("h3d", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h3d.ledger.update(_silent_entry("h3d"))
    h3d.all_raises = True
    card3d = h3d._silent_host_card()
    _ok(card3d["seeding_count"] == 1 and card3d["hr_count"] == 1,
        f"★ qB 快照不可用（外层降级）→ 全部计入（{card3d['seeding_count']}/{card3d['hr_count']}）")

    # ---- ④ settled 语义：未结清 → 欠；已结清 → 不欠；退役字段不参与 ----
    print("\n[4] settled 语义（live hr_bills state 判结清）")
    h4a = Harness()   # active（未结清）
    h4a.torrents["h4a"] = _torrent("h4a", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h4a.ledger.update(_silent_entry("h4a"))
    h4a.bills["h4a"] = {"state": "active", "need_h": 24.0, "seeded_h": 23.0}
    _ok(h4a._silent_host_card()["hr_count"] == 1, "★ 账单未结清(active，挂 23h/24h) → 判「欠」")

    h4b = Harness()   # settled（已结清）
    h4b.torrents["h4b"] = _torrent("h4b", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h4b.ledger.update(_silent_entry("h4b"))
    h4b.bills["h4b"] = {"state": "settled", "need_h": 24.0, "seeded_h": 24.0}
    _ok(h4b._silent_host_card()["hr_count"] == 0, "★ 账单已结清(settled) → 判「不欠」")

    h4c = Harness()   # active 但已挂够（结清条件达成）
    h4c.torrents["h4c"] = _torrent("h4c", [tags.tag_for("hdfans", STATE_SILENT, "普通")])
    h4c.ledger.update(_silent_entry("h4c"))
    h4c.bills["h4c"] = {"state": "active", "need_h": 24.0, "seeded_h": 24.0}
    _ok(h4c._silent_host_card()["hr_count"] == 0, "★ 挂够 24h/24h → 不欠（时长达标）")

    # 退役字段「零调用方」结构性锁死：mf_resource.hrs[*].settled 无推进方 → 不得参与判定
    _sites = _count_call_sites("note_hr_progress")
    _ok(_sites == 0, f"★ note_hr_progress 全仓调用点 = 0（settled 无推进方 → 历史只读，实测 {_sites}）")
    _ledger_src = (ROOT / "ledger.py").read_text(encoding="utf-8")
    _ok("历史只读" in _ledger_src, "ledger.py 已标注 settled「历史只读」")

    # ---- ⑤ 前端字段名保持不变 ----
    print("\n[5] 前端在用的字段名保持不变")
    for _k in ("hr_count", "nonhr_count"):
        _ok(_k in card1 and _k in card2, f"返回体保留字段 {_k}")
    _ok(card1["hr_count"] + card1["nonhr_count"] == card1["seeding_count"],
        "hr_count + nonhr_count == seeding_count（不重不漏）")

    print("\n" + "=" * 68)
    print(f"✅ 全部通过：{CHECKS} 项断言")
    return 0


if __name__ == "__main__":
    sys.exit(main())
