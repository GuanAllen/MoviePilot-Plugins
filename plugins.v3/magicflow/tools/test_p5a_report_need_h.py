#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · P5a 回归：``/agent/report?view=hr`` 站点行 ``need_h`` 拆义。

原缺陷（P5a）：同名 ``need_h`` 一名两义——
站点行取的是**保护窗口**（``seed_hours``，学校站 240h），
账单行取的却是**义务工时**（``seed_need_hours``，学校站 20h）。

本测试锁死新契约（离线 / 纯 stdlib / stub 宿主，真跑 ``features/reportview.py``）：

  A. 站点行 ``need_h`` 与账单行/``items[].need_h`` **同名同义** = 义务工时；
  B. 学校站（``seed_hours=240`` / ``seed_need_hours=20``）：站点行 ``need_h=20``、
     ``protect_h=240``，且**字段名不同**（保护窗口不再占 ``need_h``）；
  C. 规则缺失（未知）→ 义务工时保守落 ``24.0``；规则**明确写 0**（已知不要求）→ 保留 ``0``，
     两者不许混同；
  D. ``_site_need_hours`` 取值的边界（None / "" / "abc" / 0 / 20）。

用法：``python3 tools/test_p5a_report_need_h.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_p5a_needh_test"
FAILED: list = []
CHECKS = 0


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


class _Resp:
    def __init__(self, success: bool = True, message: str = "", data=None):
        self.success = success
        self.message = message
        self.data = data


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")
for _name, _attrs in (("app", {}), ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
                      ("app.schemas", {"Response": _Resp}),
                      ("app.schemas.types", {"EventType": object}), ("app.sdk", {}),
                      ("app.sdk.events", {"eventmanager": types.SimpleNamespace()})):
    _m = sys.modules.get(_name)
    if _m is None:
        _m = types.ModuleType(_name)
        sys.modules[_name] = _m
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)

for _modname, _attrs in (
    ("bonus", ("TorrentBonusInfo",)),
    ("fingerprint", ("fingerprint", "inner_fingerprint", "info_hash", "Entry",
                     "entries_fingerprint", "load_torrent_entries", "total_size")),
    ("fetcher", ("SiteCandidateTorrent",)),
):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    sys.modules[PKG + "." + _modname] = _m

_load(PKG + ".common", "common.py")

_tags = types.ModuleType(PKG + ".tags")
_tags.EXTERNAL_TAG = "魔流-外部"
_tags.RESCUE_TAG = "魔流-补源"
_tags.STATE_BRUSH, _tags.STATE_BONUS = "刷流", "魔力"
_tags.STATE_HR, _tags.STATE_SILENT = "保种", "静默"
_tags.SUB_NEW, _tags.SUB_RESOURCE, _tags.SUB_PLAIN = "新", "资源", "普通"
_tags.identity_of = lambda tags: ("资源" if "资源" in [str(t) for t in (tags or [])] else "")
_tags.is_reuse_copy = lambda tags: "魔流-辅种" in [str(t) for t in (tags or [])]
_tags.duty_of = lambda tags: next((s for s in (_tags.STATE_BRUSH, _tags.STATE_BONUS,
                                               _tags.STATE_HR, _tags.STATE_SILENT)
                                   if s in [str(t) for t in (tags or [])]), "")
_tags.parse_tag = lambda tag: tuple(str(tag).split("-", 1))
sys.modules[PKG + ".tags"] = _tags

_hrbills = types.ModuleType(PKG + ".features.hrbills")
_hrbills.BILL_STATE_ACTIVE, _hrbills.BILL_STATE_BREACHED = "active", "breached"
_hrbills.RULE_SITE_HR, _hrbills.RULE_HIT_AND_RUN = "site_hr", "hit_and_run"
sys.modules[PKG + ".features.hrbills"] = _hrbills

_sr = _load(PKG + ".features.sitereport", "features/sitereport.py")
rv = _load(PKG + ".features.reportview", "features/reportview.py")


def chk(name, cond, got=""):
    global CHECKS
    CHECKS += 1
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ← {got}"))
    if not cond:
        FAILED.append(name)


class _T:
    def __init__(self, h, state="uploading", progress=1.0, tags=(), size_gb=0.0):
        self.hash, self.state, self.progress = h, state, progress
        self.tags, self.size_gb = list(tags), size_gb
        self.title = "T-" + h[:6]
        self.save_path = "/dl/" + h[:6]
        self.ratio, self.uploaded = 1.5, 1024


class _Store:
    def __init__(self, rows):
        self._rows = dict(rows or {})

    def items(self):
        return dict(self._rows)

    def all(self):
        return dict(self._rows)


class _HrCache:
    def __init__(self, reports=None):
        self._r = dict(reports or {})

    def get_report(self, dom):
        return dict(self._r.get(dom) or {})


#: 学校站规则（真值源 sites/rules.py:43-48）：保护窗口 240h / 义务工时 20h
BTSCHOOL_RULE = {"seed_hours": 240.0, "seed_need_hours": 20.0, "source": "builtin"}
#: 明确「不要求工时」的站：真实 0（已知），与「规则缺失（未知）」是两种语义
ZERO_RULE = {"seed_hours": 168.0, "seed_need_hours": 0.0, "source": "manual"}


def _mkfake():
    class Fake(rv.ReportViewMixin):
        def __init__(self, *, ledger, snap, bills, sites, rules, protected, reseed):
            self._ledger, self._snap, self._bills = _Store(ledger), dict(snap), _Store(bills)
            self._sites, self._rules, self._prot, self._reseed = (
                list(sites), dict(rules), dict(protected), set(reseed))
            self.logs = []

        def _tag_state(self):
            return self._ledger

        def _site_report_bills_store(self):
            return self._bills

        def _site_report_snapshot(self):
            return dict(self._snap)

        def _site_rules(self):
            return {"items": dict(self._rules)}

        def _site_report_resolve(self, site=""):
            return {"sites": list(self._sites)}

        def _site_hr_flag(self, dom):
            return True

        def _site_per_torrent_hr(self, dom):
            return False

        def _hr_window_hours(self, dom):
            return 240.0

        def _reseed_ledger(self):
            return {h: {} for h in self._reseed}

        def _crossseed_sources(self):
            return {}

        def _protection_sets(self, task=None, bonus_list=None, managed=None, snap=None):
            return dict(self._prot)

        def _hr_reconcile_cache(self):
            return _HrCache()

        def _tag_site_names(self):
            return {"pt.btschool.club", "zerohr.top", "norule.top"}

        def _hr_obligation(self, site, t, snap=None):
            return (True, "")

        def _hr_deadline(self, bill):
            return {"due_h": 26.0, "at_risk": False}

        def _hr_margin_hours(self):
            return 2.0

        def _hr_warn_hours(self):
            return 48.0

        def _site_report_hr(self, dom, live=0, snap=None):
            return {"ok": True, "records_total": 0, "records": [], "missing_local": []}

        def _site_report_transport(self, state, progress):
            return _sr.TRANSPORT_SEEDING

        def _site_report_sub(self, t, bucket):
            return _tags.identity_of(getattr(t, "tags", None))

        def _site_report_bucket(self, t, state, progress, is_hr, is_prot):
            return _sr.BUCKET_HR

        def _site_report_reuse(self, tags):
            return _tags.is_reuse_copy(tags)

        def _site_report_torrent_site(self, t, known):
            return ""

        def _log(self, msg, level="info"):
            self.logs.append((level, str(msg)))

    return Fake


def _dataset():
    h_bts = "b" * 40
    h_zer = "c" * 40
    h_nor = "d" * 40
    ledger = {
        h_bts: {"site": "pt.btschool.club", "state": "保种", "size_gb": 10.0},
        h_zer: {"site": "zerohr.top", "state": "保种", "size_gb": 4.0},
        h_nor: {"site": "norule.top", "state": "保种", "size_gb": 2.0},
    }
    snap = {h: _T(h, tags=["魔流-保种"]) for h in ledger}
    bills = {
        # 账单义务工时 = 20h（学校站达标线）
        h_bts: {"site": "pt.btschool.club", "state": "active", "rule": "site_hr",
                "need_h": 20, "seeded_h": 3},
        h_zer: {"site": "zerohr.top", "state": "active", "rule": "site_hr",
                "need_h": 0, "seeded_h": 0},
        h_nor: {"site": "norule.top", "state": "active", "rule": "site_hr",
                "need_h": 24, "seeded_h": 1},
    }
    sites = [{"id": 1, "name": "BTSchool", "domain": "pt.btschool.club"},
             {"id": 2, "name": "ZeroHR", "domain": "zerohr.top"},
             {"id": 3, "name": "NoRule", "domain": "norule.top"}]
    rules = {"pt.btschool.club": BTSCHOOL_RULE, "zerohr.top": ZERO_RULE}
    return dict(ledger=ledger, snap=snap, bills=bills, sites=sites, rules=rules,
                protected={"hard": set(), "soft": set(), "incomplete": set(), "why": {}},
                reseed=set(), hashes=(h_bts, h_zer, h_nor))


def _row_by_dom(v_hr, dom):
    for s in v_hr["sites"]:
        if s.get("domain") == dom:
            return s
    return {}


def main() -> int:
    d = _dataset()
    Fake = _mkfake()
    fake = Fake(ledger=d["ledger"], snap=d["snap"], bills=d["bills"], sites=d["sites"],
                rules=d["rules"], protected=d["protected"], reseed=d["reseed"])
    ctx = fake._rv_ctx()

    print("\nA. 站点行 need_h 与账单行 need_h 同名同义（义务工时）")
    v_hr = rv.view_hr(ctx, limit=0)
    bts = _row_by_dom(v_hr, "pt.btschool.club")
    bts_items = [i for i in (bts.get("items") or []) if i.get("hash") == d["hashes"][0]]
    chk("A1 站点行 need_h = 账单行 need_h = 20（学校站达标线）",
        bts.get("need_h") == 20.0 and bts_items and bts_items[0].get("need_h") == 20.0,
        (bts.get("need_h"), bts_items[:1]))

    print("\nB. 保护窗口换名 protect_h，不再占 need_h")
    chk("B1 站点行 protect_h = 240（规则窗口 seed_hours）",
        bts.get("protect_h") == 240.0, bts)
    chk("B2 义务工时 ≠ 保护窗口，且字段名不同",
        bts.get("need_h") != bts.get("protect_h") and
        ("need_h" in bts) and ("protect_h" in bts),
        {"need_h": bts.get("need_h"), "protect_h": bts.get("protect_h")})
    chk("B3 旧语义没有残留（need_h 不再等于 seed_hours=240）",
        bts.get("need_h") != 240.0, bts.get("need_h"))
    chk("B4 window_h 保留（实测考核窗口=240）", bts.get("window_h") == 240.0, bts.get("window_h"))

    print("\nC. 未知 vs 已知 0 不许混同")
    nor = _row_by_dom(v_hr, "norule.top")
    zer = _row_by_dom(v_hr, "zerohr.top")
    chk("C1 规则缺失（未知）→ 义务工时保守 24.0",
        nor.get("need_h") == 24.0, nor)
    chk("C2 规则明确写 0（已知不要求）→ 保留 0，不落 24.0",
        zer.get("need_h") == 0.0, zer)
    chk("C3 未知与已知 0 是两种结果", nor.get("need_h") != zer.get("need_h"),
        (nor.get("need_h"), zer.get("need_h")))

    print("\nD. _site_need_hours 取值边界")
    chk("D1 空规则 → 24.0", rv._site_need_hours({}) == 24.0, rv._site_need_hours({}))
    chk("D2 seed_need_hours=None → 24.0",
        rv._site_need_hours({"seed_need_hours": None}) == 24.0,
        rv._site_need_hours({"seed_need_hours": None}))
    chk("D3 seed_need_hours='' → 24.0",
        rv._site_need_hours({"seed_need_hours": ""}) == 24.0,
        rv._site_need_hours({"seed_need_hours": ""}))
    chk("D4 seed_need_hours='abc' → 24.0",
        rv._site_need_hours({"seed_need_hours": "abc"}) == 24.0,
        rv._site_need_hours({"seed_need_hours": "abc"}))
    chk("D5 seed_need_hours=0 → 0.0",
        rv._site_need_hours({"seed_need_hours": 0}) == 0.0,
        rv._site_need_hours({"seed_need_hours": 0}))
    chk("D6 seed_need_hours=20 → 20.0",
        rv._site_need_hours({"seed_need_hours": 20}) == 20.0,
        rv._site_need_hours({"seed_need_hours": 20}))
    chk("D7 保守默认与 hrbills.HR_NEED_HOURS_DEFAULT 同值",
        rv.NEED_HOURS_DEFAULT == 24.0, rv.NEED_HOURS_DEFAULT)
    chk("D8 _site_protect_hours 取 seed_hours（学校站 240）",
        rv._site_protect_hours(BTSCHOOL_RULE) == 240.0,
        rv._site_protect_hours(BTSCHOOL_RULE))

    print()
    if FAILED:
        print(f"❌ {len(FAILED)} 项失败：" + "；".join(FAILED))
        return 1
    print(f"✅ P5a need_h 拆义回归全部通过（{CHECKS} 断言）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
