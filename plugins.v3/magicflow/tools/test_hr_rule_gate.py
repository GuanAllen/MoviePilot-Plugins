#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · H&R 规则闸「三口径归一」离线回归测试（2026-10-10 拍板）。

覆盖：
  A. 开账 ``_hrbills_open``：
     - 站点规则明确 **无 H&R**（hr=False）→ **不开账**；
     - 明确有（hr=True）→ rule=site_hr；逐种 hit_and_run → rule=hit_and_run；
     - 未探明（None）→ rule=unknown（影子，pending）。
  B. 回填 ``_hrbills_backfill``：明确无 H&R 的站**不回填开账**（防「凭空欠债」）。
  C. tick 规则闸 + 自愈 ``_hrbills_tick``：
     - 只有 rule∈{site_hr,hit_and_run} 才 **激活/算欠**；
     - unknown 完成 → 仍 pending（不激活）；
     - 存量 unknown-active → 自愈降回 pending；unknown-breach → 降回 pending。
  D. 删除断言 ``_delete_bill_assert``：unknown-active/breached → **不拦**；site_hr-active → 拦。

用法：``python3 tools/test_hr_rule_gate.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_hr_rule_gate_test"


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


def _stub_and_load():
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
        ("bonus", ("TorrentBonusInfo", "calc_bonus_per_hour")),
        ("fetcher", ("SiteCandidateTorrent",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    _load(PKG + ".fingerprint", "fingerprint.py")
    return (_load(PKG + ".common", "common.py"),
            _load(PKG + ".persistence", "persistence.py"),
            _load(PKG + ".features.deletegate", "features/deletegate.py"),
            _load(PKG + ".features.hrbills", "features/hrbills.py"))


common, persistence, deletegate, hrbills = _stub_and_load()

HrBillsMixin = hrbills.HrBillsMixin
DeleteGateMixin = deletegate.DeleteGateMixin
BILL_STATE_ACTIVE = hrbills.BILL_STATE_ACTIVE
BILL_STATE_PENDING = hrbills.BILL_STATE_PENDING
BILL_STATE_BREACHED = hrbills.BILL_STATE_BREACHED
RULE_SITE_HR = hrbills.RULE_SITE_HR
RULE_HIT_AND_RUN = hrbills.RULE_HIT_AND_RUN
RULE_UNKNOWN = hrbills.RULE_UNKNOWN

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _torrent(title="t", progress=1.0, seed_time=0.0, hit_and_run=False, tracker=""):
    return types.SimpleNamespace(
        hash="", title=title, progress=progress, seed_time=seed_time,
        hit_and_run=hit_and_run, tags=[], tracker=tracker, completion_on=0.0, downloaded=1e9,
    )


class _Groups:
    def items(self):
        return {}

    def group_of(self, h):
        return ""


class _Rules:
    def __init__(self, d):
        self._d = d

    def get(self, dom):
        return self._d.get(str(dom or "").strip().lower())


class Harness(HrBillsMixin, DeleteGateMixin):
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._hot = None
        self.site_hr: dict = {}       # dom -> True/False/None
        self.need_hours: dict = {}    # dom -> float
        self.torrents: dict = {}      # hash -> SimpleNamespace
        self.ledger: dict = {}        # hash -> rec
        self.name2dom: dict = {}
        self._hr_seed_margin_hours = 0.0
        self._hr_deadline_warn_hours = 48.0

    def get_data_path(self):
        return self._data_dir

    def _site_hr_flag(self, dom):
        return self.site_hr.get(dom)

    def _site_per_torrent_hr(self, dom):
        return False

    def _crossseed_seed_window_hours(self, dom):
        return 0.0

    def _crossseed_seed_need_hours(self, dom):
        return self.need_hours.get(dom, 0.0)

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _tag_state(self):
        class _S:
            def __init__(self, d):
                self._d = d

            def items(self):
                return dict(self._d)
        return _S(self.ledger)

    def _tag_groups(self):
        return _Groups()

    def _site_rules(self):
        return _Rules({})

    def _site_domain_by_name(self, name):
        if not name:
            return ""
        if "." in name and " " not in name:
            return name.lower()
        return self.name2dom.get(name, "")


def main() -> int:
    print("=" * 64)
    print("魔流 · H&R 规则闸（三口径归一）回归测试")
    print("=" * 64)
    tmp = tempfile.mkdtemp(prefix="hr_rule_gate_")
    h = Harness(Path(tmp))
    store = h._hrbills_store()

    # ---- A) 开账规则闸 ----
    print("\n[A] 开账规则闸")
    h.site_hr["hr.site"] = True
    h.site_hr["nohr.site"] = False
    h.need_hours["hr.site"] = 20.0
    h.need_hours["nohr.site"] = 20.0
    raw = b"x"

    t = _torrent("A1", progress=0.0, tracker="hr.site")
    t.hash = "aaaa"
    h.torrents["aaaa"] = t
    b = h._hrbills_open("aaaa", "hr.site", "魔流-hr-刷流", raw)
    _ok(b is not None and b["rule"] == RULE_SITE_HR, f"hr=True → 开账 rule=site_hr（{b and b['rule']}）")

    t = _torrent("A2", progress=0.0, tracker="nohr.site")
    t.hash = "bbbb"
    h.torrents["bbbb"] = t
    b = h._hrbills_open("bbbb", "nohr.site", "魔流-nohr-刷流", raw)
    _ok(b is None, "★ hr=False（明确无 H&R）→ **不开账**")

    t = _torrent("A3", progress=0.0, tracker="unknown.site", hit_and_run=True)
    t.hash = "cccc"
    h.torrents["cccc"] = t
    b = h._hrbills_open("cccc", "unknown.site", "魔流-u-刷流", raw, hit_and_run=True)
    _ok(b is not None and b["rule"] == RULE_HIT_AND_RUN, f"逐种 hit_and_run → rule=hit_and_run（{b and b['rule']}）")

    t = _torrent("A4", progress=0.0, tracker="unknown.site")
    t.hash = "dddd"
    h.torrents["dddd"] = t
    b = h._hrbills_open("dddd", "unknown.site", "魔流-u-刷流", raw)
    _ok(b is None, "未探明（None）→ 不开账")

    # ---- B) 回填规则闸 ----
    print("\n[B] 回填规则闸")
    h.torrents["e1"] = _torrent("B1", progress=1.0, tracker="nohr.site")
    h.ledger["e1"] = {"site": "nohr.site"}
    h.torrents["e2"] = _torrent("B2", progress=1.0, tracker="hr.site")
    h.ledger["e2"] = {"site": "hr.site"}
    h.torrents["e3"] = _torrent("B3", progress=1.0, tracker="unknown.site")
    h.ledger["e3"] = {"site": "unknown.site"}
    bf = h._hrbills_backfill(store, h._tag_all_torrents(), limit=200)
    _ok(store.get("e1") is None, "★ hr=False 的站 → 不回填开账")
    _ok((store.get("e2") or {}).get("rule") == RULE_SITE_HR, "hr=True 的站 → 回填 rule=site_hr")
    _ok(store.get("e3") is None, "未探明 → 不回填开账")

    # ---- C) tick 规则闸 + 自愈 ----
    print("\n[C] tick 规则闸 + 自愈")
    # 干净起：清掉 A/B 的账单，只留待测
    for k in list(store.all().keys()):
        store.delete(k) if hasattr(store, "delete") else None
    try:
        store._d.clear()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    # unknown 完成 → 不激活
    h.torrents["p1"] = _torrent("P1", progress=1.0, tracker="unknown.site")
    _put(store, "p1", rule=RULE_UNKNOWN, state=BILL_STATE_PENDING, progress=1.0)
    # unknown active（存量凭空欠债）→ 自愈
    h.torrents["p2"] = _torrent("P2", progress=1.0, tracker="unknown.site")
    _put(store, "p2", rule=RULE_UNKNOWN, state=BILL_STATE_ACTIVE, progress=1.0)
    # unknown breached → 降回
    h.torrents["p3"] = _torrent("P3", progress=1.0, tracker="unknown.site")
    _put(store, "p3", rule=RULE_UNKNOWN, state=BILL_STATE_BREACHED, progress=1.0)
    # site_hr pending + 完成 → 激活
    h.torrents["p4"] = _torrent("P4", progress=1.0, tracker="hr.site")
    _put(store, "p4", rule=RULE_SITE_HR, state=BILL_STATE_PENDING, progress=1.0, site="hr.site")
    h._hrbills_backfill = lambda *a, **k: {"opened": 0, "no_site": 0}  # 关掉回填干扰
    h._hrbills_tick()
    _ok(store.get("p1")["state"] == BILL_STATE_PENDING, "★ unknown + 完成 → 仍 pending（不激活）")
    _ok(store.get("p2")["state"] == BILL_STATE_PENDING, "★ 存量 unknown-active → 自愈降回 pending")
    _ok(store.get("p3")["state"] == BILL_STATE_PENDING, "★ unknown-breach → 降回 pending")
    _ok(store.get("p4")["state"] == BILL_STATE_ACTIVE, "site_hr + 完成 → 激活 active")

    # ---- D) 删除断言对齐 ----
    print("\n[D] 删除断言对齐 _hr_obligation")
    why = h._delete_bill_assert(["p2", "p4"])
    _ok("p2" not in why, "★ unknown-active → **不拦**")
    _ok("p4" in why, "site_hr-active → 拦")

    print(f"\n✅✅ 全部通过（{CHECKS} 项断言）")
    return 0


def _put(store, h, **fields):
    rec = {"site": fields.get("site", "unknown.site"), "rule": fields.get("rule", RULE_UNKNOWN),
           "state": fields.get("state", BILL_STATE_PENDING), "need_h": 24.0, "seeded_h": 0.0,
           "fp": "", "title": h, "opened_at": time.time(), "opened_by": "test",
           "last_progress": fields.get("progress", 0.0), "last_progress_at": time.time(),
           "progress": fields.get("progress", 0.0)}
    store.put(h, rec)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(str(e))
        sys.exit(1)
