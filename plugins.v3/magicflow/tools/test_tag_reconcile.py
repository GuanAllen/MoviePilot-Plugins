#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 标签 ↔ 账本对账（★ 15.2.0）离线回归 —— 真跑 features/tags.py，不需 MoviePilot。

背景（Master 2026-10-07 11:08「行吧」批准的「身份不齐」清理）：
  真值源是**种子账本**（`mf_seed`：谁在岗 / 职务 / 身份），qB 标签只是它的**镜像**。
  实测有 47 个 `魔流-<站>-魔力` 缺身份轴（`魔流-<站>-静默-<子>`）、2 个账本说「保种」标签却没职务。
  `_tag_ledger_reconcile()` 按账本把标签补回（自愈），口径：

  1) 干跑默认**零写入**；`apply=True` 才写，且**只写 qB 标签**；
  2) 账本在岗（魔力/刷流/保种）+ qB 有 → 期望 = ``retag(cur, site, state, sub)``，不一致才补；
  3) 标的种**不删、不暂停、不 resume、不改种子账本**；
  4) 幂等：补齐后再跑 = 0 待补；
  5) `adopt_reseed=True`：有 `魔流-辅种`、两本账都没登记、能解出 IYUU sid 的「无主辅种副本」→ 补登 `mf_reseed`；
  6) 只带静默身份、不在账本（`tag_only`）→ **一律不动**（15.1.0 口径：不定罪、不写账本）。

用法：``python3 tools/test_tag_reconcile.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_tag_reconcile_test"


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

# app.* 桩
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

# 兄弟模块桩（features/tags.py 需要）
_mod_pkg = _pkg(PKG + ".models", ROOT / "models")  # 仅占位，下面覆盖
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

tags_root = _load(PKG + ".tags", "tags.py")
_load(PKG + ".fingerprint", "fingerprint.py")
_load(PKG + ".persistence", "persistence.py")
common = _load(PKG + ".common", "common.py")
_load(PKG + ".downloader_ops", "downloader_ops.py")
ftags = _load(PKG + ".features.tags", "features/tags.py")

MARK_REUSE = tags_root.MARK_REUSE
STATE_BONUS = tags_root.STATE_BONUS
STATE_HR = tags_root.STATE_HR
STATE_SILENT = tags_root.STATE_SILENT

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _torrent(h, tags, state="stalledUP"):
    return types.SimpleNamespace(hash=h, title=h, state=state, size=1 << 30,
                                 tags=list(tags), progress=1.0,
                                 save_path="/x", content_path=f"/x/{h}")


class _Store:
    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)

    def get(self, h):
        return self._d.get(str(h or "").lower()) or {}


class _DL:
    is_available = True

    def __init__(self, snap):
        self._snap = snap
        self.calls = []
        self.deletes = []

    def replace_torrent_tags(self, h, tags):
        self.calls.append((str(h).lower(), list(tags)))
        t = self._snap.get(str(h).lower())
        if t is not None:
            t.tags = list(tags)
        return True

    def set_torrent_tags(self, h, tags):
        return self.replace_torrent_tags(h, tags)

    def delete_torrents(self, *a, **k):
        self.deletes.append((a, k))
        return 0, None

    def pause_torrents(self, *a, **k):  # pragma: no cover
        raise AssertionError("对账绝不应 pause")

    def resume_torrents(self, *a, **k):  # pragma: no cover
        raise AssertionError("对账绝不应 resume")


class Harness(ftags.TagsMixin):
    """真 TagsMixin + 桩依赖；`_tag_ledger_reconcile` 走**真实现**。"""

    def __init__(self, seed=None, snap=None, reseed=None, site_map=None):
        self.seed = dict(seed or {})
        self.snap = dict(snap or {})
        self.reseed = dict(reseed or {})
        self.site_map = dict(site_map or {})
        self.dl = _DL(self.snap)
        self.logs = []

    def _get_downloader(self, name="qbittorrent"):
        return self.dl

    def _tag_state(self):
        return _Store(self.seed)

    def _tag_all_torrents(self):
        return dict(self.snap)

    def _reseed_ledger(self):
        return dict(self.reseed)

    def _reseed_site_map(self):
        return {int(v): {"sid": int(v), "name": k} for k, v in self.site_map.items()}

    def _reseed_ledger_put(self, key, st, note):
        self.reseed[str(key)] = {"st": st, "note": note}

    def _log(self, msg, level=None):
        self.logs.append(str(msg))


def t1_dry_run():
    print("① 干跑：只报「缺身份轴」，零写入")
    seed = {"h1": {"state": STATE_BONUS, "site": "Depth Studio", "sub": "新"}}
    snap = {"h1": _torrent("h1", ["魔流-Depth Studio-魔力"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=False)
    _ok(rep["checked"] == 1, f"查了 1 个在岗种（实际 {rep['checked']}）")
    _ok(len(rep["items"]) == 1, "报 1 个待补")
    it = rep["items"][0]
    _ok(it["missing_identity"] is True and it["missing_duty"] is False,
        "判据：缺身份轴、不缺职务")
    _ok("魔流-Depth Studio-静默-新" in it["will"], f"期望标签含身份轴（{it['will']}）")
    _ok(not h.dl.calls, "干跑零写入（下载器无 set_tag）")
    _ok(h.seed and not h.reseed, "种子账本 / 辅种账本都没动")


def t2_apply():
    print("② apply=True：按账本补标签，只写 qB 标签")
    seed = {"h1": {"state": STATE_BONUS, "site": "Depth Studio", "sub": "新"}}
    snap = {"h1": _torrent("h1", ["魔流-Depth Studio-魔力"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(rep["repaired"] == 1, f"补了 1 个（实际 {rep['repaired']}）")
    _ok(len(h.dl.calls) == 1, "恰 1 次写标签")
    _h, new = h.dl.calls[0]
    _ok("魔流-Depth Studio-静默-新" in new and "魔流-Depth Studio-魔力" in new,
        f"新标签含身份轴 + 保留职务（{new}）")
    _ok(not h.dl.deletes, "没有删除")
    # 幂等
    rep2 = h._tag_ledger_reconcile(apply=True)
    _ok(not rep2["items"] and rep2["repaired"] == 0, "幂等：复跑 0 待补、0 补写")
    return h


def t3_identity_drift():
    print("③ 身份与账本打架：账本=保种、标签=静默身份（缺职务）→ 补职务")
    seed = {"h2": {"state": STATE_HR, "site": "学校", "sub": "资源"}}
    snap = {"h2": _torrent("h2", ["魔流-学校-静默-资源"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(rep["repaired"] == 1, "补了 1 个")
    it = rep["items"][0]
    _ok(it["missing_duty"] is True and it["missing_identity"] is False,
        "判据：缺职务、不缺身份")
    _h, new = h.dl.calls[0]
    _ok("魔流-学校-保种" in new, f"补回保种职务（{new}）")


def t4_skips():
    print("④ 只管在岗：静默账本 / 无站点 / qB 里没有 → 跳过")
    seed = {
        "s1": {"state": STATE_SILENT, "site": "聆音", "sub": "资源"},   # 静默身份，不归对账管
        "s2": {"state": STATE_BONUS, "site": "", "sub": "新"},          # 无站点
        "s3": {"state": STATE_BONUS, "site": "聆音", "sub": "新"},      # qB 里没有
        "s4": {"state": tags_root.STATE_BRUSH, "site": "聆音", "sub": "新"},  # 唯一该处理的
    }
    snap = {"s1": _torrent("s1", ["魔流-聆音-静默-资源"]),
            "s2": _torrent("s2", ["魔流-聆音-魔力"]),
            "s4": _torrent("s4", ["魔流-聆音-刷流"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(rep["checked"] == 1, f"只查到 1 个在岗且 qB 存在的（实际 {rep['checked']}）")
    _ok(len(rep["items"]) == 1 and rep["items"][0]["hash"] == "s4", "只报 s4")
    _ok([c[0] for c in h.dl.calls] == ["s4"], "只写 s4 的标签")


def t5_adopt_reseed():
    print("⑤ 无主辅种副本：adopt_reseed → 补登 mf_reseed（干跑不写）")
    snap = {"h3": _torrent("h3", [MARK_REUSE, "魔流-聆音-静默-资源"], state="pausedUP")}
    h = Harness(seed={}, snap=snap, site_map={"聆音": 7})
    rep = h._tag_ledger_reconcile(apply=False, adopt_reseed=True)
    _ok(len(rep["adopt_items"]) == 1, "报 1 个无主辅种副本")
    _ok(rep["adopt_items"][0]["key"] == "7:h3", f"键 = sid:hash（{rep['adopt_items'][0]['key']}）")
    _ok(rep["adopted"] == 0 and not h.reseed, "干跑不落盘")
    # apply
    rep2 = h._tag_ledger_reconcile(apply=True, adopt_reseed=True)
    _ok(rep2["adopted"] == 1 and "7:h3" in h.reseed, "apply 补登进辅种账")
    # 再跑：已在册 → 不再报
    rep3 = h._tag_ledger_reconcile(apply=False, adopt_reseed=True)
    _ok(not rep3["adopt_items"], "已在册 → 不重复报")


def t6_tag_only_untouched():
    print("⑥ 只带静默身份、不在账本（tag_only）→ 一律不动（不写账本）")
    snap = {"h4": _torrent("h4", ["魔流-聆音-静默-资源"])}
    h = Harness(seed={}, snap=snap, site_map={"聆音": 7})
    rep = h._tag_ledger_reconcile(apply=True, adopt_reseed=True)
    _ok(not rep["items"], "不把 tag_only 当在岗种补标签")
    _ok(not rep["adopt_items"], "没带 魔流-辅种 → 不补登")
    _ok(not h.dl.calls and not h.reseed, "零写入")


def t7_sub_drift_only_reported():
    print("⑦ 纯身份子桶漂移（身份/职务都在，sub 与账本不同）→ 只报不写")
    seed = {"h5": {"state": STATE_BONUS, "site": "聆音", "sub": "资源"}}
    snap = {"h5": _torrent("h5", ["魔流-聆音-静默-普通", "魔流-聆音-魔力"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(not rep["items"] and rep["items_total"] == 0, "不进「待补」（不自动改写 sub）")
    _ok(rep["drift_total"] == 1 and rep["drift"][0]["kind"] == "sub_drift", "归入 drift（只报）")
    _ok(not h.dl.calls, "零写入")


def main() -> int:
    print("== 标签 ↔ 账本对账（15.2.0）==")
    t1_dry_run()
    h = t2_apply()
    t3_identity_drift()
    t4_skips()
    t5_adopt_reseed()
    t6_tag_only_untouched()
    t7_sub_drift_only_reported()
    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:  # noqa: BLE001
        print(str(e))
        sys.exit(1)
