#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 报表唯一口径离线回归（★ 17.3.0，真跑 features/reportview.py，不需 MoviePilot）。

口径契约（本测试就是它的可执行版）：
  **台账一行 = 一颗种；真值源 = 账本；下载器快照只补 transport 并用于互校。**

断言分组：
  A. 台账合流：账本有而下载器没有（幽灵行）、下载器有而账本没有（未纳管）、
     账单有而两者都没有——三类都必须成行，不许静默消失；
  B. 判定优先级：账本站点 > 标签站点；账本职务 > 标签职务；复用副本不判 H&R；
  C. 三视图一致：site / silent / hr 是**同一台账的投影**，总数可对账；
  D. H&R 视图**不丢 rule=unknown**（归「未定性」，且不计入 owed）；
  E. 互校 drift：ledger_only / qb_only / missing_from_mp 与集合一致，自检全绿；
  F. 端点层：get_report 返回 Response；非法参数报 bad_param 并带字段名。

用法：``python3 tools/test_reportview.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_reportview_test"
FAILED: list = []


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

# 顶层宿主依赖（reportview 不直接用，但 features 包内其它模块 import 时会碰）
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

# ---- 标签常量桩（只给 reportview 用到的符号）
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

# 真跑 sitereport（常量真值源）与 reportview
_sr = _load(PKG + ".features.sitereport", "features/sitereport.py")
rv = _load(PKG + ".features.reportview", "features/reportview.py")


def chk(name, cond, got=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ← {got}"))
    if not cond:
        FAILED.append(name)


class _T:
    """下载器种子桩（只读属性）。"""

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


def _mkfake(rv_mod):
    """最小只读宿主：只暴露报表需要的读方法（任何写调用都会 AttributeError）。"""

    class Fake(rv_mod.ReportViewMixin):
        def __init__(self, *, ledger, snap, bills, sites, protected, reseed, crossseed,
                     owed_rep=None, oblig=None):
            self._ledger, self._snap, self._bills = _Store(ledger), dict(snap), _Store(bills)
            self._sites, self._prot, self._reseed = list(sites), dict(protected), set(reseed)
            self._cs, self._oblig = dict(crossseed), (oblig or (lambda *a, **k: (False, "")))
            self._hrc = _HrCache(owed_rep or {})
            self.logs = []

        # ---- 只读真值源
        def _tag_state(self):
            return self._ledger

        def _site_report_bills_store(self):
            return self._bills

        def _site_report_snapshot(self):
            return dict(self._snap)

        def _site_rules(self):
            return {"items": {"dstudio.me": {"seed_hours": 48, "source": "manual"},
                              "cspt.top": {"seed_hours": 24, "source": "manual"}}}

        def _site_report_resolve(self, site=""):
            return {"sites": list(self._sites)}

        def _site_hr_flag(self, dom):
            return {"dstudio.me": True, "cspt.top": False}.get(dom)

        def _site_per_torrent_hr(self, dom):
            return dom == "dstudio.me"

        def _hr_window_hours(self, dom):
            return 240.0

        def _reseed_ledger(self):
            return {h: {} for h in self._reseed}

        def _crossseed_sources(self):
            return dict(self._cs)

        def _protection_sets(self, task=None, bonus_list=None, managed=None, snap=None):
            return dict(self._prot)

        def _hr_reconcile_cache(self):
            return self._hrc

        def _tag_site_names(self):
            return {"dstudio.me", "cspt.top", "pt.soulvoice.club", "carpt.net", "crabpt.vip"}

        def _hr_obligation(self, site, t, snap=None):
            return self._oblig(site, t, snap)

        def _hr_deadline(self, bill):
            return {"due_h": 26.0, "at_risk": False}

        def _hr_margin_hours(self):
            return 2.0

        def _hr_warn_hours(self):
            return 48.0

        def _site_report_hr(self, dom, live=0, snap=None):
            return {"ok": True, "records_total": 0, "records": [], "missing_local": []}

        def _site_report_transport(self, state, progress):
            st = str(state or "").lower()
            if float(progress or 0) < 0.999:
                return _sr.TRANSPORT_DOWNLOADING
            if "paused" in st or "stop" in st:
                return _sr.TRANSPORT_PAUSED
            return _sr.TRANSPORT_SEEDING

        def _site_report_sub(self, t, bucket):
            return _tags.identity_of(getattr(t, "tags", None))

        def _site_report_bucket(self, t, state, progress, is_hr, is_prot):
            tags = [str(x) for x in (getattr(t, "tags", None) or [])]
            if _tags.RESCUE_TAG in tags:
                return _sr.BUCKET_RESCUE
            if is_hr or _tags.STATE_HR in tags:
                return _sr.BUCKET_HR
            if _tags.STATE_BRUSH in tags:
                return _sr.BUCKET_BRUSH
            if _tags.STATE_BONUS in tags:
                return _sr.BUCKET_BONUS
            if _tags.EXTERNAL_TAG in tags:
                return _sr.BUCKET_EXTERNAL
            return _sr.BUCKET_SILENT

        def _site_report_reuse(self, tags):
            return _tags.is_reuse_copy(tags)

        def _site_report_torrent_site(self, t, known):
            return {"qbonly0000000000000000000000000000000000": "crabpt.vip"}.get(t.hash, "")

        def _log(self, msg, level="info"):
            self.logs.append((level, str(msg)))

    return Fake


def _dataset(now: float):
    h_ghost = "a" * 40
    h_pool = "b" * 40
    h_hr = "c" * 40
    h_reuse = "d" * 40
    h_unk = "e" * 40
    h_billonly = "f" * 40
    h_qbonly = "qbonly0000000000000000000000000000000000"
    ledger = {
        h_ghost: {"site": "dstudio.me", "state": "静默", "sub": "资源", "size_gb": 10.0,
                  "ts": now - 3600 * 5, "title": "幽灵种"},
        h_pool: {"site": "cspt.top", "state": "魔力", "sub": "资源", "size_gb": 20.0},
        h_hr: {"site": "pt.soulvoice.club", "state": "保种", "sub": "资源", "size_gb": 30.0},
        h_unk: {"site": "hdfans.org", "state": "静默", "size_gb": 7.0},
    }
    # h_reuse 刻意**不在**种子账本里：只出现在下载器 + 辅种账 + 账单，
    # 用于验证「辅种副本」出身轴与「复用副本不判 H&R」两条规则。
    snap = {
        h_pool: _T(h_pool, tags=["魔流-魔力"], size_gb=20.0),
        h_hr: _T(h_hr, tags=["魔流-保种"], size_gb=30.0),
        h_reuse: _T(h_reuse, tags=["魔流-辅种"], size_gb=5.0),
        h_qbonly: _T(h_qbonly, state="pausedUP", tags=[], size_gb=3.0),
    }
    bills = {
        h_hr: {"site": "pt.soulvoice.club", "state": "active", "rule": "site_hr",
               "need_h": 24, "seeded_h": 3, "title": "欠债种"},
        h_reuse: {"site": "carpt.net", "state": "active", "rule": "site_hr",
                  "need_h": 24, "seeded_h": 0},
        h_unk: {"site": "hdfans.org", "state": "pending", "rule": "unknown",
                "opened_by": "backfill"},
        h_billonly: {"site": "cspt.top", "state": "settled", "rule": "site_hr"},
    }
    sites = [{"id": 15, "name": "Depth Studio", "domain": "dstudio.me"},
             {"id": 8, "name": "财神", "domain": "cspt.top"},
             {"id": 10, "name": "聆音", "domain": "pt.soulvoice.club"},
             {"id": 13, "name": "CARPT", "domain": "carpt.net"},
             {"id": 14, "name": "蟹黄堡", "domain": "crabpt.vip"}]
    protected = {"hard": {h_hr}, "soft": {h_pool}, "incomplete": set(),
                 "why": {h_hr: "欠 H&R", h_pool: "库内资产（已整理/下载历史）"}}
    return dict(ledger=ledger, snap=snap, bills=bills, sites=sites, protected=protected,
                reseed={h_reuse}, crossseed={}, hashes=(h_ghost, h_pool, h_hr, h_reuse,
                                                       h_unk, h_billonly, h_qbonly), now=now)


def main() -> int:
    d = _dataset(time.time())
    h_ghost, h_pool, h_hr, h_reuse, h_unk, h_billonly, h_qbonly = d["hashes"]
    Fake = _mkfake(rv)
    fake = Fake(ledger=d["ledger"], snap=d["snap"], bills=d["bills"], sites=d["sites"],
                protected=d["protected"], reseed=d["reseed"], crossseed=d["crossseed"])
    ctx = fake._rv_ctx()
    rows = rv.build_rows(ctx)
    ctx["rows"] = rows

    print("\nA. 台账合流（三类都要成行）")
    chk("A1 账本有/下载器没有 → 幽灵行", h_ghost in rows and rows[h_ghost]["ledger_only"] is True,
        rows.get(h_ghost, {}).get("ledger_only"))
    chk("A2 幽灵行传输态=不在下载器",
        rows[h_ghost]["transport"] == rv.TRANSPORT_ABSENT, rows[h_ghost]["transport"])
    chk("A3 下载器有/账本没有 → 未纳管", rows[h_qbonly]["qb_only"] is True and
        rows[h_qbonly]["in_qb"] is True, rows[h_qbonly])
    chk("A4 只有账单 → 也成行", h_billonly in rows and rows[h_billonly]["in_qb"] is False and
        rows[h_billonly]["bill"]["state"] == "settled", rows.get(h_billonly))
    chk("A5 台账行数 = 账本∪下载器∪账单", len(rows) == len(d["hashes"]), len(rows))

    print("\nB. 判定优先级")
    chk("B1 账本站点优先（幽灵行站点=dstudio.me）", rows[h_ghost]["site"] == "dstudio.me",
        rows[h_ghost]["site"])
    chk("B2 账本职务优先（静默≠魔力标签）", rows[h_ghost]["bucket"] == _sr.BUCKET_SILENT,
        rows[h_ghost]["bucket"])
    chk("B3 欠 H&R → 保种桶", rows[h_hr]["bucket"] == _sr.BUCKET_HR and
        rows[h_hr]["hr"]["owed"] is True, rows[h_hr]["bucket"])
    chk("B4 复用副本不判 H&R（有 active 账单也不欠）",
        rows[h_reuse]["hr"]["owed"] is False, rows[h_reuse]["hr"])
    chk("B5 保护档位/理由落到行上", rows[h_hr]["protect_class"] == "hard" and
        rows[h_hr]["protect_reason"] == "欠 H&R", rows[h_hr]["protect_class"])
    chk("B6 未纳管行 sub 兜底=普通",
        rows[h_qbonly]["bucket"] == _sr.BUCKET_SILENT and
        rows[h_qbonly]["sub"] == _tags.SUB_PLAIN, rows[h_qbonly]["sub"])
    chk("B7 出身轴：账本=池 / 辅种账=辅种副本",
        rows[h_ghost]["origin"] == _sr.ORIGIN_POOL and
        rows[h_reuse]["origin"] == _sr.ORIGIN_RESEED, (rows[h_ghost]["origin"],
                                                       rows[h_reuse]["origin"]))

    print("\nC. 三视图同源（数字可对账）")
    v_silent = rv.view_silent(ctx, limit=0)
    n_silent = sum(1 for r in rows.values() if r["bucket"] == _sr.BUCKET_SILENT)
    chk("C1 silent 视图总数 = 静默桶行数", v_silent["summary"]["total"] == n_silent,
        (v_silent["summary"]["total"], n_silent))
    v_rows = rv.view_rows(ctx, limit=0)
    chk("C2 rows 视图总数 = 台账行数", v_rows["summary"]["total"] == len(rows),
        (v_rows["summary"]["total"], len(rows)))
    v_site = rv.view_site(ctx, site="dstudio.me", limit=0)
    n_ds = sum(1 for r in rows.values() if r["site"] == "dstudio.me")
    chk("C3 site 视图总数 = 该站行数（含幽灵行）",
        v_site["summary"]["total"] == n_ds and n_ds == 1, (v_site["summary"]["total"], n_ds))
    chk("C4 幽灵行进 site 视图 items",
        any(i["hash"] == h_ghost for i in v_site["items"]), v_site["summary"])
    chk("C5 silent 视图 subs 聚合（资源）",
        any(s["key"] == _tags.SUB_RESOURCE and s["count"] >= 1
            for s in v_silent["summary"]["subs"]), v_silent["summary"]["subs"])

    print("\nD. H&R 视图不丢 rule=unknown")
    v_hr = rv.view_hr(ctx, limit=0)
    hr_rule = sum(1 for b in d["bills"].values() if b["rule"] in ("site_hr", "hit_and_run"))
    chk("D1 账单总数 = 全部账单（含 unknown）",
        v_hr["totals"]["total_bills"] == len(d["bills"]), v_hr["totals"])
    chk("D2 unknown 单列「未定性」",
        v_hr["totals"]["unclassified"] == len(d["bills"]) - hr_rule and
        v_hr["totals"]["unclassified"] == 1, v_hr["totals"])
    chk("D3 owed 只数 HR 规则（unknown 不计）", v_hr["totals"]["owed"] == 2,
        v_hr["totals"]["owed"])
    _unk_items = [i for s in v_hr["sites"] for i in s["items"] if i["hash"] == h_unk]
    chk("D4 unknown 行带 class=未定性", bool(_unk_items) and
        _unk_items[0]["class"] == rv.BILL_CLASS_UNCLASSIFIED, _unk_items)

    print("\nE. 互校 drift")
    dr = rv.drift(ctx)
    chk("E1 ledger_only 计数与集合一致",
        dr["drift"]["counts"]["ledger_only"] == 2 and
        sorted(dr["drift"]["ledger_only"]) == sorted([h_ghost, h_unk]),
        dr["drift"]["counts"])
    chk("E2 qb_only = 下载器有/账本没有（h_reuse 只走辅种账，也算未纳管）",
        dr["drift"]["counts"]["qb_only"] == 2 and
        sorted(dr["drift"]["qb_only"]) == sorted([h_qbonly, h_reuse]),
        dr["drift"]["counts"])
    chk("E3 账本有挂但 MP 清单没有 → missing_from_mp",
        any(s["site"] == "hdfans.org" for s in dr["sites"]["missing_from_mp"]),
        dr["sites"]["missing_from_mp"])
    chk("E4 自检项全绿", all(c["ok"] for c in dr["views"]["checks"]),
        [c for c in dr["views"]["checks"] if not c["ok"]])

    print("\nF. 端点层")
    r_ok = fake.get_report(view="site", site="dstudio.me")
    chk("F1 get_report 返回 success/数据", bool(getattr(r_ok, "success", False)) and
        isinstance(getattr(r_ok, "data", None), dict), getattr(r_ok, "message", ""))
    r_bad = fake.get_report(view="nope")
    chk("F2 非法 view → bad_param + 字段名",
        getattr(r_bad, "success", True) is False and
        (getattr(r_bad, "data", None) or {}).get("field") == "view",
        (getattr(r_bad, "data", None), getattr(r_bad, "message", "")))
    r_bad2 = fake.get_report(view="rows", transport="飞")
    chk("F3 非法 transport → bad_param(transport)",
        getattr(r_bad2, "success", True) is False and
        (getattr(r_bad2, "data", None) or {}).get("field") == "transport",
        getattr(r_bad2, "message", ""))
    r_hr = fake.get_report(view="hr")
    chk("F4 统一入口 hr 视图 = view_hr 口径",
        getattr(r_hr, "data", {}).get("totals", {}).get("total_bills") == len(d["bills"]),
        getattr(r_hr, "data", {}).get("totals"))
    r_dr = fake.get_report_drift()
    chk("F5 drift 端点可用", bool(getattr(r_dr, "success", False)) and
        "drift" in (getattr(r_dr, "data", None) or {}), getattr(r_dr, "message", ""))

    print("\nG. 归一化（★ 17.3.0 真机缺陷回归）")
    chk("G1 _norm_dom 剥 scheme/路径/端口",
        rv._norm_dom("https://pt.btschool.club/") == "pt.btschool.club" and
        rv._norm_dom("http://cyanbug.net:8080/x?y=1") == "cyanbug.net" and
        rv._norm_dom("www.yemapt.org") == "yemapt.org",
        [rv._norm_dom(x) for x in ("https://pt.btschool.club/", "http://cyanbug.net:8080/x?y=1",
                                   "www.yemapt.org")])
    chk("G2 _norm_sub 取 tuple/字符串化元组的最后一段",
        rv._norm_sub(("财神", "普通")) == "普通" and
        rv._norm_sub("('聆音', '普通')") == "普通" and
        rv._norm_sub("资源") == "资源" and rv._norm_sub(None) == "" and
        rv._norm_sub("('', '')") == "",
        [rv._norm_sub(("财神", "普通")), rv._norm_sub("('聆音', '普通')"), rv._norm_sub("('', '')")])
    _ent = {"name": "BTSchool", "domain": "pt.btschool.club"}
    _idx = {"pt.btschool.club": _ent, "btschool.club": _ent}
    chk("G3 _site_lookup 账本短名 ↔ MP 子域互相命中",
        rv._site_lookup(_idx, "pt.btschool.club") is _ent and
        rv._site_lookup(_idx, "btschool.club") is _ent and
        rv._site_lookup(_idx, "https://pt.btschool.club/") is _ent and
        rv._site_lookup(_idx, "红豆饭") == {},
        [rv._site_lookup(_idx, k) for k in ("pt.btschool.club", "btschool.club", "红豆饭")])
    _prot = fake._rv_ctx()["protected"]
    chk("G4 保护并集非空（曾因只传 task=None → protected=0）",
        bool(_prot.get("hard") or _prot.get("soft")) and "legacy" in _prot, _prot)
    chk("G4b 嵌套 sub 也能解到底（('财神','普通') 里再套一层）",
        rv._norm_sub((("财神", "普通"),)) == "普通" and
        rv._norm_sub([["", "资源"]]) == "资源",
        [rv._norm_sub((("财神", "普通"),)), rv._norm_sub([["", "资源"]])])
    _rows = fake._rv_rows()
    _sm = rv._summary_of(list(_rows.values()))
    chk("G5 脏 sub 不再出现在 by_sub（无元组脏键）",
        not [k for k in _sm.get("by_sub", {}) if "(" in k],
        [k for k in _sm.get("by_sub", {}) if "(" in k])
    chk("G6 _summary_of 补齐 hr / non_hr 键",
        "hr" in _sm and "non_hr" in _sm, sorted(_sm.keys()))
    chk("G7 保护三档分列且 protected = legacy 口径",
        all(k in _sm for k in ("protected", "protected_hard", "protected_soft",
                               "protected_any")) and
        _sm["protected"] == sum(1 for r in _rows.values() if r.get("protected_legacy")),
        {k: _sm[k] for k in ("protected", "protected_hard", "protected_soft", "protected_any")})

    print()
    if FAILED:
        print(f"❌ {len(FAILED)} 项失败：" + "；".join(FAILED))
        return 1
    print("✅ 报表唯一口径离线回归全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
