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
# ★ 19.12.43：``_site_seed_report`` 已委托给 ``reportview._rv_site_data``（报表唯一口径），
#   该模块还从 hrbills 取 PENDING —— 桩补齐，否则真跑 reportview 会 ImportError。
_hrbills.BILL_STATE_PENDING = "pending"
_hrbills.RULE_SITE_HR = "site_hr"
_hrbills.RULE_HIT_AND_RUN = "hit_and_run"
# ★ 19.12.46（任务 89）：reportview 顶部 import 新增该常量（人工结清判据），桩补齐。
_hrbills.HR_MANUAL_SETTLE = "manual"
# ★ 任务 102：reportview 顶部 import 新增这两个状态常量（已结清/已作废行的
#   结清轨迹注入），桩补齐 —— 只补常量，不放宽任何断言。
_hrbills.BILL_STATE_SETTLED = "settled"
_hrbills.BILL_STATE_VOID = "void"
sys.modules[PKG + ".features.hrbills"] = _hrbills

# 桩 app.schemas
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = type("Response", (), {})
sys.modules["app.schemas"] = _app_schemas

sitereport = _load(PKG + ".features.sitereport", "features/sitereport.py")
# ★ 19.12.43：站点报表的真实口径已收到 ``reportview._rv_site_data``；要真跑它，
#   必须把同一条链上的 ``norm`` 与 ``reportview`` 也装上（纯 stdlib + 已桩模块）。
_load(PKG + ".norm", "norm.py")
reportview = _load(PKG + ".features.reportview", "features/reportview.py")

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
        self.read_log = []

    def get(self, h):
        return self._bills.get(h)

    def all(self):
        return dict(self._bills)

    def events_for(self, hash_string="", limit=0):
        # ★ 任务 98：append-only 事件档案查询是**只读**（reportview._rv_hr_data
        #   用它拼「结清 / 纠错历史」）。显式声明成读，别让 _WriteGuard 的兜底
        #   __getattr__ 把它当成写；write_log 仍然盯着所有真正的写入口。
        self.read_log.append("events_for")
        return []


class FakeStore(_WriteGuard):
    def __init__(self, protected=None):
        super().__init__()
        self._protected = dict(protected or {})

    def get_protected_torrents(self, tid):
        return set(self._protected.get(tid, set()))


class _EmptyCache:
    def get_report(self, dom):
        return {}


class Plug(sitereport.SiteReportMixin, reportview.ReportViewMixin):
    # ★ 19.12.43：``SiteReportMixin._site_seed_report`` 现在只做委托
    #   （``return self._rv_site_data(site, live)``），两轴口径实体在 ReportViewMixin 里。
    #   同时继承两个 mixin 才等于线上真实继承链，断言对象不变。
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

    # ★ 15.2.0 出身轴真值源（池=种子账本 / 辅种副本=mf_reseed）
    def _tag_state(self):
        return {"silent-new": {"state": "静默", "site": SITE, "sub": "新"}}

    def _reseed_ledger(self):
        return {"7:silent-res": {"st": "ok"}}

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

    # ★ 15.2.0：静默桶「出身轴」池 / 辅种副本 / 无主
    so = s["silent_origin"]
    _ok(so.get(SR.ORIGIN_POOL) == 1 and so.get(SR.ORIGIN_RESEED) == 1
        and so.get(SR.ORIGIN_NONE) == 1,
        f"silent_origin 出身轴三桶（实际 {so}）")

    # item 字段
    items = {it["hash"]: it for it in data["items"]}
    # ★ 19.12.43 契约对齐：item.sub / item.origin 是**身份/出身元数据**（17.3.0 统一台账
    #   reportview.build_rows 的 identity_of 回退），任何桶都携带 —— 前端
    #   siteReportItemSub() 按「传输/身份子桶/出身/…」渲染**每行**副标题即依赖这一点；
    #   「不混身份子桶」不变量只约束 _site_report_sub 分桶器（上文已单独断言：非静默桶返回 ""），
    #   且 sub/出身过滤 chips 只在 filter=静默 时渲染（SiteReportDialog.vue v-if）→ 不会混淆桶轴。
    #   旧断言写于站点报表独立算行（sub/origin 仅静默桶）的年代，与合并台账契约漂移；
    #   这里是**钉住合并契约的精确值**（不是放宽）：bucket/transport 仍严格断言。
    _ok(items["brush"]["bucket"] == BUCKET_BRUSH and items["brush"]["transport"] == TRANSPORT_SEEDING
        and items["brush"]["sub"] == "普通", "item（刷流）bucket=刷流/transport=做种中/sub=身份(普通)")
    _ok(items["silent-res"]["bucket"] == BUCKET_SILENT and items["silent-res"]["sub"] == "资源"
        and items["silent-res"]["protected"] is True, "item（静默-资源）sub=资源 + protected")
    _ok(items["silent-plain"]["transport"] == TRANSPORT_DOWNLOADING,
        "item（静默-普通）transport=未完成")
    _ok(items["hr-debt"]["bucket"] == BUCKET_HR and items["hr-debt"]["hr"] is not None
        and items["hr-debt"]["hr"]["owed"] is True,
        "item（欠 H&R）bucket=保种 + hr 列字段（债务不再当桶）")
    # ★ 19.12.43 契约对齐：hr 列在合并台账里是**恒在结构列**（{owed, owed_hr, need_left}），
    #   「未违约」用 owed=False 表达（不是 hr=None）；前端 siteReportItemSub 也按 dict 消费。
    _ok(items["hr-dut"]["hr"] == {"owed": False, "owed_hr": False, "need_left": ""},
        "item（保种职务未违约）hr 列恒在结构列：owed=False")
    _ok(items["silent-new"]["origin"] == SR.ORIGIN_POOL
        and items["silent-res"]["origin"] == SR.ORIGIN_RESEED
        and items["silent-plain"]["origin"] == SR.ORIGIN_NONE,
        "item.origin：静默桶逐条出身（池/辅种副本/无主）")
    # ★ 19.12.43 同上：origin 是出身轴元数据（build_rows 不按桶裁剪），刷流种若无账本/辅种
    #   出身即「无主」——与静默桶同口径（SR.ORIGIN_NONE），不再断言空串。
    _ok(items["brush"]["origin"] == SR.ORIGIN_NONE, "非静默桶 origin 也按出身轴记（无主）")

    # 排序：保种（桶序 1）应排在刷流/魔力（桶序 2/3）之前
    ordered = [it["bucket"] for it in data["items"]]
    _ok(ordered.index(BUCKET_RESCUE) < ordered.index(BUCKET_SILENT),
        "排序按 _BUCKET_ORDER（补源在静默前）")

    # 零写调用
    _ok(p._bills.write_log == [] and p._store.write_log == [],
        f"零写调用（bills={p._bills.write_log} store={p._store.write_log}）")
    _ok("events_for" in p._bills.read_log,
        "任务 98：报表只读事件档案（events_for 被真实调用，读分类不是空转）")

    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
