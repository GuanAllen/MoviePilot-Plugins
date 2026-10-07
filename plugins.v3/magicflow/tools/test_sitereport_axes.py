#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 站点报表「两轴分级」离线回归（★ 14.1.0，真跑 features/sitereport.py，不需 MoviePilot）。

背景：站点报表原「按状态分桶」把 职务/身份/传输/债务 四个轴搅在一起（在岗种被并进
「保护」、债务单列「欠H&R」桶）。本版改成**两轴分级**：
  第一级（职务/身份轴）六桶 —— 刷流 / 魔力 / 保种（欠 H&R 挂补）/ 静默（含新/资源/普通三子桶）
    / 补源 / 外部；
  第二级（传输轴）三态 —— 未完成 / 暂停 / 做种中（每桶内统计，不单独成桶）；
  债务/账本只作列字段（``bill``/``hr``），不再当桶。

本测试直接加载真 ``features/sitereport.py``（合成父包解相对导入，``tags.py`` 用真实现），断言：
  1) 六桶归类逐条正确（刷流/魔力/保种/静默/补源/外部）；
  2) 债务不混桶：欠 H&R（无保种职务）→ 归「保种」桶，summary 不再有「欠H&R」键；
  3) 外部+职务：职务优先（外部种子若在岗 → 归职务桶）；
  4) 静默三子桶：新 / 资源 / 普通（``_site_report_sub``）；
  5) 传输三态：未完成 / 暂停 / 做种中（``_site_report_transport``）；
  6) 完整报表 summary：by_bucket(6) + by_transport(3) + bucket_transport + silent_by_sub(3)，
     item 带 bucket/sub/transport 字段，无旧桶（欠H&R/保护/普通/未完成/暂停）。

用法：``python3 tools/test_sitereport_axes.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_sitereport_test"


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

# 真 tags.py（纯函数，无 app 依赖）
tags = _load(PKG + ".tags", "tags.py")

# 桩 hrbills：sitereport.py 只从它 import 4 个常量
_hrbills = types.ModuleType(PKG + ".features.hrbills")
_hrbills.BILL_STATE_ACTIVE = "active"
_hrbills.BILL_STATE_BREACHED = "breached"
_hrbills.RULE_SITE_HR = "site_hr"
_hrbills.RULE_HIT_AND_RUN = "hit_and_run"
sys.modules[PKG + ".features.hrbills"] = _hrbills

# 桩 app.schemas
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = type("Response", (), {})
sys.modules["app.schemas"] = _app_schemas

sitereport = _load(PKG + ".features.sitereport", "features/sitereport.py")

SR = sitereport
BUCKET_BRUSH = SR.BUCKET_BRUSH
BUCKET_BONUS = SR.BUCKET_BONUS
BUCKET_HR = SR.BUCKET_HR
BUCKET_SILENT = SR.BUCKET_SILENT
BUCKET_RESCUE = SR.BUCKET_RESCUE
BUCKET_EXTERNAL = SR.BUCKET_EXTERNAL
TRANSPORT_DOWNLOADING = SR.TRANSPORT_DOWNLOADING
TRANSPORT_PAUSED = SR.TRANSPORT_PAUSED
TRANSPORT_SEEDING = SR.TRANSPORT_SEEDING


class FakeTorrent:
    def __init__(self, hash, title, state="stalledUP", progress=1.0, size_gb=1.0,
                 tags=None, tracker=""):
        self.hash = hash
        self.title = title
        self.state = state
        self.progress = progress
        self.size_gb = size_gb
        self.ratio = 0.0
        self.uploaded = 0
        self.save_path = ""
        self.tags = list(tags or [])
        self.tracker = tracker


class _WriteGuard:
    def __init__(self):
        self.write_log = []

    def __getattr__(self, name):
        def _rec(*a, **k):
            self.write_log.append(name)
            return None
        return _rec


class FakeBills(_WriteGuard):
    def __init__(self, bills=None):
        super().__init__()
        self._bills = dict(bills or {})

    def get(self, h):
        return self._bills.get(h)

    def all(self):
        return dict(self._bills)


class FakeStore(_WriteGuard):
    def __init__(self, protected=None):
        super().__init__()
        self._protected = dict(protected or {})

    def get_protected_torrents(self, tid):
        return set(self._protected.get(tid, set()))


class _EmptyCache:
    def get_report(self, dom):
        return {}


class Plug(sitereport.SiteReportMixin):
    def __init__(self, snap=None, bills=None, protected=None, site_map=None, sites=None):
        self._snap = dict(snap or {})
        self._bills = FakeBills(bills) if bills is not None else FakeBills()
        self._store = FakeStore(protected) if protected is not None else FakeStore()
        self._task_configs = {}
        self._site_map = dict(site_map or {})
        self._sites = list(sites or [])

    def _list_sites(self):
        return self._sites

    def _tag_snapshot_view(self):
        raise RuntimeError("no stale view in test → 走 _tag_all_torrents 回退")

    def _tag_all_torrents(self):
        return self._snap

    def _hrbills_store(self):
        return self._bills

    def _tag_site_names(self):
        return list(self._site_map.keys())

    def _hrbills_norm_domain(self, dom):
        return str(dom or "").strip().lower().replace("http://", "").replace("https://", "").rstrip("/")

    def _hr_reconcile_site(self, dom, snap):
        return {}

    def _hr_reconcile_cache(self):
        return _EmptyCache()

    def _log(self, msg, level="info"):
        pass


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


SITE = "财神"


def _t(tags, **kw):
    kw.setdefault("state", "stalledUP")
    kw.setdefault("progress", 1.0)
    return FakeTorrent(hash=kw.pop("hash", "h-" + str(len(tags))), title=kw.pop("title", "x"),
                       tags=tags, **kw)


def main() -> int:
    print("== 站点报表 · 两轴分级（14.1.0）==")

    plug = Plug()
    bucket = plug._site_report_bucket
    transport = plug._site_report_transport
    sub = plug._site_report_sub

    # 1) 六桶归类（直接测 _site_report_bucket）
    _ok(bucket(_t(["魔流-财神-静默-普通", "魔流-财神-刷流"]), "stalledUP", 1.0, False, False) == BUCKET_BRUSH,
        "刷流桶（职务=刷流）")
    _ok(bucket(_t(["魔流-财神-静默-普通", "魔流-财神-魔力"]), "stalledUP", 1.0, False, False) == BUCKET_BONUS,
        "魔力桶（职务=魔力）")
    _ok(bucket(_t(["魔流-财神-静默-资源", "魔流-财神-保种"]), "stalledUP", 1.0, False, False) == BUCKET_HR,
        "保种桶（职务=保种）")
    _ok(bucket(_t(["魔流-财神-静默-新"]), "stalledUP", 1.0, False, False) == BUCKET_SILENT,
        "静默桶（无职务·新）")
    _ok(bucket(_t(["魔流-补源", "魔流-财神-静默-资源"]), "stalledUP", 1.0, False, False) == BUCKET_RESCUE,
        "补源桶（RESCUE_TAG）")
    _ok(bucket(_t(["魔流-外部", "魔流-财神-静默-普通"]), "stalledUP", 1.0, False, False) == BUCKET_EXTERNAL,
        "外部桶（EXTERNAL_TAG，无职务）")

    # 2) 债务不混桶：欠 H&R（无保种职务）→ 归「保种」桶
    _ok(bucket(_t(["魔流-财神-静默-资源"]), "stalledUP", 1.0, True, False) == BUCKET_HR,
        "欠 H&R（无保种职务）归「保种」桶，不再有独立「欠H&R」桶")

    # 3) 外部+职务：职务优先
    _ok(bucket(_t(["魔流-外部", "魔流-财神-静默-普通", "魔流-财神-刷流"]), "stalledUP", 1.0, False, False) == BUCKET_BRUSH,
        "外部种子若在岗（有刷流职务）→ 归「刷流」桶（职务优先）")

    # 3b) 补源优先于职务/债务（补源副本不判 H&R、也不算职务）
    _ok(bucket(_t(["魔流-补源", "魔流-财神-静默-资源", "魔流-财神-刷流"]), "stalledUP", 1.0, True, False) == BUCKET_RESCUE,
        "补源优先（即使有职务/债务）")

    # 4) 静默三子桶
    _ok(sub(_t(["魔流-财神-静默-新"]), BUCKET_SILENT) == "新", "静默-新")
    _ok(sub(_t(["魔流-财神-静默-资源"]), BUCKET_SILENT) == "资源", "静默-资源")
    _ok(sub(_t(["魔流-财神-静默-普通"]), BUCKET_SILENT) == "普通", "静默-普通")
    _ok(sub(_t(["魔流-财神-静默-普通", "魔流-财神-刷流"]), BUCKET_BRUSH) == "",
        "非静默桶 sub 为空（不混身份子桶）")
    _ok(sub(_t(["魔流-财神-刷流"]), BUCKET_SILENT) == "普通",
        "静默桶但无身份标签 → 默认「普通」")

    # 5) 传输三态
    _ok(transport("downloading", 0.5) == TRANSPORT_DOWNLOADING, "传输·未完成（progress<0.999）")
    _ok(transport("pausedDL", 1.0) == TRANSPORT_PAUSED, "传输·暂停（paused）")
    _ok(transport("stoppedUP", 1.0) == TRANSPORT_PAUSED, "传输·暂停（stopped）")
    _ok(transport("stalledUP", 1.0) == TRANSPORT_SEEDING, "传输·做种中（stalledUP）")
    _ok(transport("forcedUP", 1.0) == TRANSPORT_SEEDING, "传输·做种中（forcedUP）")

    # 6) 完整报表：summary + item 字段
    sites = [{"id": 1, "name": SITE, "domain": "cspt.top"}]
    snap = {
        "brush": _t(["魔流-财神-静默-普通", "魔流-财神-刷流"], hash="brush", size_gb=10.0, state="forcedUP"),
        "bonus": _t(["魔流-财神-静默-普通", "魔流-财神-魔力"], hash="bonus", size_gb=20.0, state="stalledUP"),
        "hr-dut": _t(["魔流-财神-静默-资源", "魔流-财神-保种"], hash="hr-dut", size_gb=5.0, state="stalledUP"),
        "hr-debt": _t(["魔流-财神-静默-资源"], hash="hr-debt", size_gb=6.0, state="stalledUP"),
        "silent-new": _t(["魔流-财神-静默-新"], hash="silent-new", size_gb=1.0, state="pausedDL"),
        "silent-res": _t(["魔流-财神-静默-资源"], hash="silent-res", size_gb=2.0, state="stalledUP"),
        "silent-plain": _t(["魔流-财神-静默-普通"], hash="silent-plain", size_gb=3.0, state="downloading", progress=0.4),
        "rescue": _t(["魔流-补源", "魔流-财神-静默-资源"], hash="rescue", size_gb=4.0, state="stalledUP"),
        "ext": _t(["魔流-外部", "魔流-财神-静默-普通"], hash="ext", size_gb=7.0, state="stalledUP"),
    }
    bills = {
        "hr-debt": {"state": "active", "rule": "site_hr", "site": "cspt.top", "need_h": 24.0, "seeded_h": 0.0},
    }
    protected = {"": {"silent-res"}}
    p = Plug(snap=snap, bills=bills, protected=protected, site_map={SITE: "cspt.top"}, sites=sites)
    data = p._site_seed_report(SITE, 0)

    s = data["summary"]
    _ok(s["total"] == 9, f"total=9（实际 {s['total']}）")

    # by_bucket：6 桶，无旧桶键
    bb = s["by_bucket"]
    _ok(bb.get(BUCKET_BRUSH) == 1 and bb.get(BUCKET_BONUS) == 1 and bb.get(BUCKET_HR) == 2
        and bb.get(BUCKET_SILENT) == 3 and bb.get(BUCKET_RESCUE) == 1 and bb.get(BUCKET_EXTERNAL) == 1,
        f"by_bucket 六桶计数（实际 {bb}）")
    for old in ("欠H&R", "保护", "普通", "未完成", "暂停"):
        _ok(old not in bb, f"旧桶「{old}」不再出现在 by_bucket")

    # by_transport + bucket_transport + silent_by_sub
    bt = s["by_transport"]
    _ok(bt.get(TRANSPORT_DOWNLOADING) == 1 and bt.get(TRANSPORT_PAUSED) == 1
        and bt.get(TRANSPORT_SEEDING) == 7,
        f"by_transport 三态（实际 {bt}）")
    _ok(s["bucket_transport"][BUCKET_SILENT][TRANSPORT_DOWNLOADING] == 1,
        "bucket_transport：静默桶内「未完成」=1")
    _ok(s["bucket_transport"][BUCKET_HR][TRANSPORT_SEEDING] == 2,
        "bucket_transport：保种桶内「做种中」=2（债务并入保种，不单列）")
    ss = s["silent_by_sub"]
    _ok(ss.get("新") == 1 and ss.get("资源") == 1 and ss.get("普通") == 1,
        f"silent_by_sub 三子桶（实际 {ss}）")

    # item 字段
    items = {it["hash"]: it for it in data["items"]}
    _ok(items["brush"]["bucket"] == BUCKET_BRUSH and items["brush"]["transport"] == TRANSPORT_SEEDING
        and items["brush"]["sub"] == "", "item（刷流）bucket/transport/sub")
    _ok(items["silent-res"]["bucket"] == BUCKET_SILENT and items["silent-res"]["sub"] == "资源"
        and items["silent-res"]["protected"] is True, "item（静默-资源）sub=资源 + protected")
    _ok(items["silent-plain"]["transport"] == TRANSPORT_DOWNLOADING,
        "item（静默-普通）transport=未完成")
    _ok(items["hr-debt"]["bucket"] == BUCKET_HR and items["hr-debt"]["hr"] is not None
        and items["hr-debt"]["hr"]["owed"] is True,
        "item（欠 H&R）bucket=保种 + hr 列字段（债务不再当桶）")
    _ok(items["hr-dut"]["hr"] is None, "item（保种职务未违约）hr 列为 None")

    # 排序：保种（桶序 1）应排在刷流/魔力（桶序 2/3）之前
    ordered = [it["bucket"] for it in data["items"]]
    _ok(ordered.index(BUCKET_RESCUE) < ordered.index(BUCKET_SILENT),
        "排序按 _BUCKET_ORDER（补源在静默前）")

    # 零写调用
    _ok(p._bills.write_log == [] and p._store.write_log == [],
        f"零写调用（bills={p._bills.write_log} store={p._store.write_log}）")

    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
