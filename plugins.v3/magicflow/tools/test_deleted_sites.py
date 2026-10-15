#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 「站点已删除」离线回归（★ 16.0.0 起，17.4.0 扩三档口径，真跑 common.py + features/siteops.py）。

背景（Master 2026-10-10）：「目前站点2 红豆饭已经被删了」→ 借这个活案例把
「MP 侧删站之后魔流怎么办」做成完整功能：

  1) **识别**（``common.SiteGuard.mp_sites`` 60s 记忆化；异常 → 判不出、不硬判）；
  2) **牵连面**（只数不写）：qB 标签前缀 ``魔流-<站名>-`` 的种数/体积/暂停/复用副本、
     ``mf_seed``（按台账 site_id）/ ``mf_reseed``（按 iyuu_sid）行数、站内任务；
  3) **处置**（``deleted_site_act``）：pause / resume / remove（★ 17.4.0 三档），默认干跑；
  4) **自动化**（★ 17.4.0）：通知告警（``notify_sweep`` → ``notify_check_site_deleted``）
     + 健康自检 ``H8`` —— **两处都只报不做**，摘种必须显式下令。

★ 17.4.0 remove 三档（Master 2026-10-15 口径）：
  ① 复用副本（``魔流-辅种``）→ **只摘种、文件保留**；
  ② 本体 / 库内资产 → **只摘种、文件保留**（此前是「保留不动」，改为摘种）；
  ③ 自有非本体 → **连文件删**。
  ①②走具名闸门通道 ``gate_strip``（只跳「库内资产」第 5 类），③走严格 ``gate``
  （``force_asset=1`` 时才改走 ``gate_manual``）；**两条通道互不代偿**。

断言：
  [1] SiteGuard.mp_sites 60s 记忆化（同进程只查一次库）；查库异常 → None（判不出不硬判）；
      mp_ids 派生；
  [2] deleted_sites_rows：MP 已无的站被列出（按 mp_site_id 判）、MP 仍在的不列出、
      无 mp_site_id 的按域名判、台账排序按种子数降序；
  [3] 牵连面正确：qB 种数/体积/暂停/运行/复用副本 + 账本行数 + 站内任务；
  [4] 站点已删但 MP 表读不到 → 返回空（保守）；
  [5] deleted_site_act：默认干跑不动下载器；pause/resume 真做；remove 三档分档正确、
      **先连文件删再摘种**、摘种批恒带 ``allow_strip_asset`` 且**永不**带 ``allow_library_asset``、
      干跑预览按各自通道算；reuse_only 只取复用副本；站点不在清单 / 未知动作 → ok=False；
  [6] 源码护栏：三档 delete_file 取值、``_dk_strip`` 不含 allow_library_asset、本体判据三腿、
      具名通道 ``_delete_gate_strip``、``delete_torrents`` 已接 allow_strip_asset；
  [7] ★本体识别三腿（身份后缀 -资源 / MP「已整理」/ 账本 in_library）+ fail-closed
      （判据抛异常 → 一律按本体只摘种，绝不连文件删）；
  [8] ★自动化接线：notify 新检查函数 + kind 登记 + 按站去重 + 上限 5；health H8 已接；
      **两处都不调用处置函数**（只报不做）。

用法：``python3 tools/test_deleted_sites.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_sitedel_test"

FAILS: list = []


def ok(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ✓ {msg}")
    else:
        FAILS.append(msg)
        print(f"  ✗ {msg}")


class _Stub(types.ModuleType):
    """万能桩模块：任何属性/调用都是另一个 _Stub。"""

    def __getattr__(self, name):
        return _Stub(name)

    def __call__(self, *a, **k):
        return _Stub("_call")


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ MP 站点表桩
MP_INFO = {1: ("学校", "btschool.club"), 3: ("咖啡", "ptcafe.club"),
           9: ("馒头", "kp.m-team.cc"), 13: ("CARPT", "carpt.net"),
           16: ("YemaPT", "yemapt.org")}
MP_STATE = {"raise": False, "n": 0}


class _MPSite:
    def __init__(self, sid, name, domain):
        self.id = sid
        self.name = name
        self.domain = domain


class _FakeSiteOper:
    def list(self):
        MP_STATE["n"] += 1
        if MP_STATE["raise"]:
            raise RuntimeError("db boom")
        return [_MPSite(i, n, d) for i, (n, d) in sorted(MP_INFO.items())]

    def get(self, sid):
        return _MPSite(sid, *MP_INFO[sid]) if int(sid or 0) in MP_INFO else None


# ------------------------------------------------- 桩 app.* 与兄弟模块
for _n, _attrs in (
    ("app", {}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": _Stub("EventType")}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": _Stub("eventmanager"), "Event": type("Event", (), {})}),
    ("app.sdk.logging", {"logger": _Stub("logger")}),
    ("app.sdk.network", {"SitesHelper": _Stub("SitesHelper")}),
    ("app.db", {}),
    ("app.db.oper", {}),
    ("app.db.oper.site", {"SiteOper": _FakeSiteOper}),
):
    _m = sys.modules.get(_n)
    if _m is None:
        _m = types.ModuleType(_n)
        sys.modules[_n] = _m
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)

sys.modules[PKG] = types.ModuleType(PKG)
sys.modules[PKG].__path__ = [str(ROOT)]
_feat = types.ModuleType(PKG + ".features")
_feat.__path__ = [str(ROOT / "features")]
sys.modules[PKG + ".features"] = _feat
_sites = _Stub(PKG + ".sites")
_sites.__path__ = [str(ROOT / "sites")]
sys.modules[PKG + ".sites"] = _sites
_rules = types.ModuleType(PKG + ".sites.rules")
_rules.BUILTIN_RULES = {}
_rules.SiteRules = _Stub("SiteRules")
_rules.framework_note = lambda *a, **k: ""
_rules.parse_hr_from_mail = lambda *a, **k: None
_rules.parser_for_framework = lambda *a, **k: None
sys.modules[PKG + ".sites.rules"] = _rules
_ff = _Stub(PKG + ".sites.formula_fetch")
_ff.fetch_site_formula = lambda *a, **k: _Stub("cap")
sys.modules[PKG + ".sites.formula_fetch"] = _ff
_fetcher = _Stub(PKG + ".fetcher")
sys.modules[PKG + ".fetcher"] = _fetcher
sys.modules[PKG + ".recommend"] = _Stub(PKG + ".recommend")
_ss = _Stub(PKG + ".sitestore")
_ss.get_site_store = lambda *a, **k: _Stub("store")
sys.modules[PKG + ".sitestore"] = _ss
_tags = types.ModuleType(PKG + ".tags")
_tags.MARK_REUSE = "魔流-辅种"
_tags.SUB_RESOURCE = "资源"
# ★ 17.4.0：本体（库内资产）判据三腿必须与 tags.py 一致（真值源 tags.py:80/92/97）
_tags.ASSET_TAGS = ("已整理", "辅种")
_tags.is_asset_tags = lambda t: any(str(x) in _tags.ASSET_TAGS for x in (t or []))
_tags.is_library_asset = lambda rec: (bool((rec or {}).get("in_library"))
                                      or str((rec or {}).get("sub") or "") == _tags.SUB_RESOURCE)
sys.modules[PKG + ".tags"] = _tags
sys.modules[PKG + ".fingerprint"] = _Stub(PKG + ".fingerprint")

common = _load(PKG + ".common", "common.py")
siteops = _load(PKG + ".features.siteops", "features/siteops.py")

GB = 1024 ** 3

# ------------------------------------------------------------------ 台账 / qB / 账本
SITE_ROWS = [
    {"site_id": 2, "name": "红豆饭", "domain": "hdfans.org", "mp_site_id": 2, "iyuu_sid": 57},
    {"site_id": 1, "name": "学校", "domain": "btschool.club", "mp_site_id": 1, "iyuu_sid": 8},
    {"site_id": 16, "name": "YemaPT", "domain": "yemapt.org", "mp_site_id": 16, "iyuu_sid": 109},
    {"site_id": 17, "name": "www.yemapt.org", "domain": "www.yemapt.org", "mp_site_id": None, "iyuu_sid": None},
    {"site_id": 19, "name": "hdfans.org", "domain": "", "mp_site_id": None, "iyuu_sid": None},
    {"site_id": 20, "name": "手工", "domain": "", "mp_site_id": None, "iyuu_sid": None},
]


class _T:
    def __init__(self, tags, size, state):
        self.tags = tags
        self.size = size
        self.state = state


QBT = {
    ("a" * 40): _T(["魔流-红豆饭-静默-普通"], int(1.5 * GB), "pausedUP"),
    ("b" * 40): _T(["魔流-红豆饭-静默-资源", "魔流-辅种"], int(2.5 * GB), "uploading"),
    ("e" * 40): _T(["魔流-红豆饭-静默-资源"], int(1 * GB), "pausedUP"),
    ("c" * 40): _T(["魔流-学校-静默-普通"], int(3 * GB), "pausedUP"),
    ("d" * 40): _T(["魔流-手工-静默-普通"], int(1 * GB), "pausedUP"),
}
SEED_ROWS = [types.SimpleNamespace(site_id=2), types.SimpleNamespace(site_id=1),
             types.SimpleNamespace(site_id=2)]
RESEED_ROWS = [types.SimpleNamespace(site_id=57), types.SimpleNamespace(site_id=8)]


class _FakeDL:
    def __init__(self):
        self.calls: list = []

    def pause_torrents(self, hashes):
        self.calls.append(("pause", sorted(hashes)))
        return len(hashes), None

    def resume_torrents(self, hashes):
        self.calls.append(("resume", sorted(hashes)))
        return len(hashes), None

    def delete_torrents(self, hashes=None, delete_file=False, reason="", source="", **kw):
        self.calls.append(("delete", sorted(hashes or []), bool(delete_file), source,
                           bool(kw.get("allow_library_asset")), bool(kw.get("allow_strip_asset"))))
        return len(hashes or []), None


class Host:
    def __init__(self):
        self._task_configs = {
            "t1": types.SimpleNamespace(id="t1", site_id=2),
            "t2": types.SimpleNamespace(id="t2", site_id=1),
        }
        self._dl = _FakeDL()
        self.gate_calls: list = []

    def _agent_db_site_rows(self):
        return [dict(r) for r in SITE_ROWS]

    def _tag_all_torrents(self):
        return dict(QBT)

    def _tag_state(self):
        return {}

    def _agent_db_rows(self, model):
        if model == "SeedRow":
            return list(SEED_ROWS)
        if model == "ReseedRow":
            return list(RESEED_ROWS)
        return []

    def _get_downloader(self):
        return self._dl

    def _delete_gate_detail(self, hashes, **kw):
        self.gate_calls.append(dict(kw))
        return {}

    def _log(self, msg, level="info"):
        _ = (msg, level)


print("魔流 · 「站点已删除」离线回归（★ 16.0.0）")

# ------------------------------------------------- [1] mp_sites 记忆化 / 异常
h = Host()
g = common.site_guard(h)
sites = g.mp_sites()
ok(isinstance(sites, dict) and set(sites.keys()) == {1, 3, 9, 13, 16}, "[1] mp_sites 返回 MP 站点 id 集")
ok(sites[1]["name"] == "学校" and sites[1]["domain"] == "btschool.club", "[1] mp_sites 带 name/domain")
ok(MP_STATE["n"] == 1, f"[1] 60s 内只查一次库（实际 {MP_STATE['n']}）")
g.mp_sites()
ok(MP_STATE["n"] == 1, "[1] 二次调用命中缓存")
ok(g.mp_ids() == {1, 3, 9, 13, 16}, "[1] mp_ids 派生正确")
h_boom = Host()
g_boom = common.site_guard(h_boom)
MP_STATE["raise"] = True
g_boom2 = common.site_guard(Host())
ok(g_boom2.mp_sites() is None, "[1] 查库异常 → None（判不出）")
ok(g_boom2.mp_ids() is None, "[1] 异常时 mp_ids = None")
MP_STATE["raise"] = False
_ = (g_boom,)

# ------------------------------------------------- [2] deleted_sites_rows 识别
rows = siteops.deleted_sites_rows(h)
names = sorted(str(r.get("name") or r.get("domain")) for r in rows)
ok("红豆饭" in names, "[2] MP 已删的「红豆饭」被列出（按 mp_site_id 判）")
ok("学校" not in names, "[2] MP 仍在的「学校」不列出")
ok("YemaPT" not in names, "[2] MP 仍存的 YemaPT（域名对得上）不列出")
ok("www.yemapt.org" in names, "[2] 无 mp_site_id 的行按域名判（www.yemapt.org 不在 MP → 列出）")
ok("手工" in names, "[2] 无 mp_site_id 且无域名 → 按名字判（列出）")
ok("hdfans.org" in names, "[2] 残留行 hdfans.org（无 id 无域名）也被拾出")
ok(len(rows) == 4, f"[2] 共 4 行（实际 {len(rows)}）")
rd0 = [r for r in rows if r.get("name") == "红豆饭"][0]
ok(rd0.get("reason") == "mp_deleted", "[2] 红豆饭 reason=mp_deleted")
ok([r for r in rows if r.get("name") == "手工"][0].get("reason") == "no_binding", "[2] 手工 reason=no_binding")
ok(int((rows[0].get("seeds") or {}).get("count") or 0) >= int((rows[1].get("seeds") or {}).get("count") or 0),
   "[2] 按种子数降序")

# ------------------------------------------------- [3] 牵连面
rd = [r for r in rows if r.get("name") == "红豆饭"][0]
s = rd["seeds"]
ok(s["count"] == 3, f"[3] 红豆饭 qB 种数=3（实际 {s['count']}）")
ok(abs(s["size_gb"] - 5.0) < 0.01, f"[3] 体积≈5.0GB（实际 {s['size_gb']}）")
ok(s["paused"] == 2 and s["running"] == 1, f"[3] 暂停2/运行1（实际 {s['paused']}/{s['running']}）")
ok(s["reuse"] == 1, f"[3] 复用副本=1（实际 {s['reuse']}）")
ok(rd["ledger"]["seed_rows"] == 2, f"[3] mf_seed 行数=2（实际 {rd['ledger']['seed_rows']}）")
ok(rd["ledger"]["reseed_rows"] == 1, f"[3] mf_reseed 行数=1（按 iyuu_sid=57，实际 {rd['ledger']['reseed_rows']}）")
ok(rd["tasks"] == ["t1"], f"[3] 站内任务=[t1]（实际 {rd['tasks']}）")

# ------------------------------------------------- [4] MP 表读不到 → 空
MP_STATE["raise"] = True
g_x = common.site_guard(Host())
ok(siteops.deleted_sites_rows(Host()) == [], "[4] MP 站点表读不到 → 返回空（保守）")
MP_STATE["raise"] = False
_ = g_x

# ------------------------------------------------- [5] deleted_site_act
h5 = Host()
rep = siteops.deleted_site_act(h5, 2, "pause")
ok(rep["ok"] is True and rep.get("dry_run") is True, "[5] 默认干跑（dry_run=True）")
ok(rep.get("planned") == 3, f"[5] pause 干跑 planned=3（实际 {rep.get('planned')}）")
ok(h5._dl.calls == [], "[5] 干跑不动下载器")

rep = siteops.deleted_site_act(h5, 2, "pause", dry_run=0)
ok(rep["ok"] is True and rep["affected"] == 3, "[5] pause 真做：affected=3")
ok(h5._dl.calls and h5._dl.calls[0][0] == "pause" and len(h5._dl.calls[0][1]) == 3, "[5] 调 pause_torrents(3 个)")

# remove（★ 17.4.0 三档）：复用副本 + 本体/资源 **只摘种** / 自有非本体 **连文件删**
h5d = Host()
rep = siteops.deleted_site_act(h5d, 2, "remove")
pl = rep.get("planned") or {}
ok(rep["ok"] is True and pl.get("strip") == 2 and pl.get("full") == 1 and pl.get("keep") == 0,
   f"[5] remove 干跑分档 strip/full/keep = 2/1/0（实际 {pl}）")
ok(pl.get("strip_reuse") == 1 and pl.get("strip_asset") == 1,
   f"[5] ★摘种档细分：复用副本 1 + 本体/资源 1（实际 {pl.get('strip_reuse')}/{pl.get('strip_asset')}）")
ok(h5d._dl.calls == [], "[5] remove 干跑不动下载器")
ok((rep.get("gate") or {}).get("would_delete") == 1,
   f"[5] ★干跑闸门预览（连文件删档 / 自有非本体）= 1（实际 {rep.get('gate')}）")
ok((rep.get("gate_strip") or {}).get("would_delete") == 2,
   f"[5] ★干跑闸门预览（只摘种档）= 2（实际 {rep.get('gate_strip')}）")
ok({} in h5d.gate_calls and {"allow_strip_asset": True} in h5d.gate_calls,
   f"[5] ★预览按各自通道算：严格 gate（连文件删）+ gate_strip（只摘种）（实际 {h5d.gate_calls}）")
ok(not any(kw.get("allow_library_asset") for kw in h5d.gate_calls),
   "[5] ★干跑预览绝不带 allow_library_asset（不传 force_asset 时）")

h5r = Host()
rep = siteops.deleted_site_act(h5r, 2, "remove", dry_run=0)
calls = h5r._dl.calls
ok(rep["ok"] is True and rep["stripped"] == 2 and rep["deleted_with_file"] == 1 and rep["kept"] == 0,
   f"[5] remove 真做：摘种2 / 连文件删1 / 保留0（实际 {rep.get('stripped')}/{rep.get('deleted_with_file')}/{rep.get('kept')}）")
strip_call = [c for c in calls if c[0] == "delete" and c[2] is False]
full_call = [c for c in calls if c[0] == "delete" and c[2] is True]
ok(strip_call and strip_call[0][1] == [("b" * 40), ("e" * 40)],
   "[5] ★复用副本 + 本体/资源 一起走 delete_file=False（只摘种）")
ok(full_call and full_call[0][1] == [("a" * 40)], "[5] ★自有非本体走 delete_file=True（连文件）")
ok(len(full_call) == 1 and len(strip_call) == 1, f"[5] 恰好两批（实际 strip/full = {len(strip_call)}/{len(full_call)}）")
ok(calls[0][0] == "delete" and calls[0][2] is True,
   "[5] ★★顺序：先「连文件删」再「摘种」（反了会让共享护栏看不见仍在的辅种副本）")
ok(strip_call[0][3] == "sitedeleted" and full_call[0][3] == "sitedeleted",
   "[5] 两批都带 source=sitedeleted（统一台账口径）")

# ★ 17.4.0 红线：摘种档恒走具名 gate_strip，**永不带** allow_library_asset
ok(strip_call[0][5] is True and strip_call[0][4] is False,
   f"[5] ★★摘种批：allow_strip_asset=True 且 allow_library_asset=False（实际 {strip_call[0][4:]}")
ok(full_call[0][4] is False and full_call[0][5] is False,
   f"[5] 连文件删批（默认）：两个豁免都不带（实际 {full_call[0][4:]}）")

h5c = Host()
rep = siteops.deleted_site_act(h5c, 2, "remove", reuse_only=1, dry_run=0)
ok(rep["ok"] is True and rep["stripped"] == 1 and rep["deleted_with_file"] == 0, "[5] reuse_only=1 → 只摘 1 个复用副本")
ok([c for c in h5c._dl.calls if c[0] == "delete"][0][1] == [("b" * 40)], "[5] reuse_only 只取带 魔流-辅种 的副本")
ok([c for c in h5c._dl.calls if c[0] == "delete"][0][4] is False, "[5] ★reuse_only 也不带 allow_library_asset")

h5f = Host()
rep = siteops.deleted_site_act(h5f, 2, "remove", dry_run=0, force_asset=1)
fc = [c for c in h5f._dl.calls if c[0] == "delete"]
fc_full = [c for c in fc if c[2] is True]
fc_strip = [c for c in fc if c[2] is False]
ok(fc_full and all(c[4] is True for c in fc_full),
   f"[5] ★force_asset=1 → 连文件删批带 allow_library_asset=True（实际 {[c[4] for c in fc_full]}）")
ok(fc_strip and all(c[4] is False and c[5] is True for c in fc_strip),
   f"[5] ★★force_asset=1 **不影响**摘种批：仍 allow_strip_asset=True / allow_library_asset=False"
   f"（实际 {[(c[4], c[5]) for c in fc_strip]}）")
ok(rep.get("gate", {}).get("blocked") == 0, "[5] ★force_asset=1 干跑预览不再把库内资产算拦（allow_asset）")
ok({"allow_asset": True} in h5f.gate_calls and {"allow_strip_asset": True} in h5f.gate_calls,
   f"[5] ★force_asset=1 预览：连文件删档 allow_asset、摘种档仍 allow_strip_asset（实际 {h5f.gate_calls}）")

h5g = Host()
rep = siteops.deleted_site_act(h5g, 2, "remove", dry_run=0)
ng = [c for c in h5g._dl.calls if c[0] == "delete"]
ok(ng and all(c[4] is False for c in ng), "[5] 默认（不传 force_asset）→ 严格闸门（allow_library_asset 不传）")

h5e2 = Host()
rep = siteops.deleted_site_act(h5e2, 999, "pause", dry_run=0)
ok(rep["ok"] is False and rep["message"], "[5] 站点不在「已删除」清单 → ok=False")

h5f = Host()
rep = siteops.deleted_site_act(h5f, 2, "boom", dry_run=0)
ok(rep["ok"] is False and "未知动作" in rep["message"], "[5] 未知动作 → ok=False")

# ------------------------------- [7] ★17.4.0 本体（库内资产）识别三腿 + fail-closed
print("-- [7] 本体识别：三腿判据 + 取不到判据按本体算 --")
_H1, _H2, _H3, _H4 = ("1" * 40), ("2" * 40), ("3" * 40), ("4" * 40)
QBT_BODY = {
    _H1: _T(["魔流-红豆饭-静默-资源"], int(GB), "pausedUP"),            # 腿① 魔流身份后缀 -资源
    _H2: _T(["魔流-红豆饭-静默-普通", "已整理"], int(GB), "pausedUP"),   # 腿② MP 写的「已整理」
    _H3: _T(["魔流-红豆饭-静默-普通"], int(GB), "pausedUP"),            # 腿③ 账本 in_library
    _H4: _T(["魔流-红豆饭-静默-普通"], int(GB), "pausedUP"),            # 三腿都不命中 → 自有非本体
}


class HostBody(Host):
    """红豆饭只剩 4 个种（H1~H4），账本只给 H3 记 in_library。"""

    def _tag_all_torrents(self):
        return dict(QBT_BODY)

    def _tag_state(self):
        return {_H3: {"in_library": True}}


h7 = HostBody()
rep7 = siteops.deleted_site_act(h7, 2, "remove")
pl7 = rep7.get("planned") or {}
ok(pl7.get("strip") == 3 and pl7.get("full") == 1,
   f"[7] 三腿各自判出的本体都进「只摘种」档（strip=3 / full=1，实际 {pl7}）")
siteops.deleted_site_act(h7, 2, "remove", dry_run=0)
c7 = [c for c in h7._dl.calls if c[0] == "delete"]
st7 = [c for c in c7 if c[2] is False]
fu7 = [c for c in c7 if c[2] is True]
ok(st7 and st7[0][1] == sorted([_H1, _H2, _H3]),
   f"[7] ★腿①②③（身份后缀 / MP「已整理」/ 账本 in_library）全进摘种批（实际 {st7[0][1] if st7 else None}）")
ok(fu7 and fu7[0][1] == [_H4], f"[7] 三腿都不命中的 H4 才连文件删（实际 {fu7[0][1] if fu7 else None}）")
ok(all(c[4] is False for c in c7), "[7] 默认两批都不带 allow_library_asset")

# fail-closed：本体判据链自身抛异常 → 一律按本体算（只摘种，绝不连文件删）
_orig_lib = siteops.is_library_asset
siteops.is_library_asset = lambda rec: (_ for _ in ()).throw(RuntimeError("ledger boom"))
try:
    h7b = HostBody()
    siteops.deleted_site_act(h7b, 2, "remove", dry_run=0)
    c7b = [c for c in h7b._dl.calls if c[0] == "delete"]
    st7b = [c for c in c7b if c[2] is False]
    ok(st7b and st7b[0][1] == sorted([_H1, _H2, _H3, _H4]),
       f"[7] ★fail-closed：判据抛异常 → 全部按本体只摘种（实际 {st7b[0][1] if st7b else None}）")
    ok(not [c for c in c7b if c[2] is True], "[7] ★fail-closed：没有任何一批是「连文件删」")
finally:
    siteops.is_library_asset = _orig_lib

# ------------------------------- [8] ★17.4.0 自动化接线：通知告警 + 健康自检 H8
print("-- [8] 自动化接线：notify_sweep 告警 + health H8 --")
psrc = (ROOT / "features" / "notify.py").read_text(encoding="utf-8")
ok("def notify_check_site_deleted" in psrc and "deleted_sites_rows" in psrc,
   "[8] notify：新检查函数存在且与盘点同源（deleted_sites_rows）")
ok("self.notify_check_site_deleted(cfg)" in psrc, "[8] notify_sweep 里真的调了它（不是死代码）")
ok('"site_deleted": "站点已删除"' in psrc, "[8] notify：kind 已登记进 NOTIFY_KIND_TEXT（否则前端显示空）")
ok('dedup=f"sitedel:{r.get(\'site_id\')}"' in psrc, "[8] notify：按「站」去重（一个站一条，不互相顶掉）")
ok("dels[:5]" in psrc, "[8] notify：一次最多告警 5 个站（整排站被删不刷屏）")
ok('"site_deleted": len(dels)' in psrc, "[8] notify_sweep 的 checked 回报 site_deleted 计数")

hsrc = (ROOT / "features" / "health.py").read_text(encoding="utf-8")
ok('f"H8:{row.get(\'site_id\')}"' in hsrc and "deleted_sites_rows" in hsrc,
   "[8] health：H8 已接进 _health_issues（与盘点同源）")
_hi = hsrc.find("H8:{row.get")
_hr = hsrc.find("H5:global")
ok(0 < _hi < _hr, "[8] health：H8 段落在 H5 之前（结构位置正确）")

# 只报不做：三处都不得出现「自动摘种」的调用
ok("deleted_site_act" not in psrc and "deleted_site_act" not in hsrc,
   "[8] ★★只报不做：notify / health 都不调用处置函数（摘种必须显式下令）")

# ------------------------------------------------- [6] 源码护栏
src = (ROOT / "features" / "siteops.py").read_text(encoding="utf-8")
ok("delete_file=False" in src and "delete_file=True" in src, "[6] siteops 源码：复用副本/本体 delete_file=False / 自有非本体 delete_file=True")
ok('_dk_strip: Dict[str, Any] = {"allow_strip_asset": True}' in src,
   "[6] ★siteops 源码：摘种档固定走具名 allow_strip_asset 通道")
ok("allow_library_asset" not in src.split("_dk_strip")[1].split("try:")[0],
   "[6] ★★siteops 源码：_dk_strip 定义处**不含** allow_library_asset（两条豁免不互相代偿）")
ok("def _is_body_like" in src and "is_asset_tags" in src and "is_library_asset" in src,
   "[6] siteops 源码：本体判据三腿（身份后缀 / is_asset_tags / is_library_asset）")
ok("def deleted_sites_rows" in src and "def deleted_site_act" in src, "[6] siteops 源码：模块级函数（避开 self._ 棘轮）")
csrc = (ROOT / "common.py").read_text(encoding="utf-8")
ok("def mp_sites" in csrc and "class SiteGuard" in csrc, "[6] common 源码：SiteGuard.mp_sites 存在（叶子层判定）")
dsrc = (ROOT / "features" / "deletegate.py").read_text(encoding="utf-8")
ok("def _delete_gate_strip" in dsrc and "allow_strip_asset" in dsrc,
   "[6] deletegate 源码：具名「只摘种」通道 _delete_gate_strip 存在")
opsrc = (ROOT / "downloader_ops.py").read_text(encoding="utf-8")
ok("allow_strip_asset" in opsrc and "gate_strip" in opsrc,
   "[6] downloader_ops 源码：delete_torrents 已接 allow_strip_asset / gate_strip")

print()
if FAILS:
    print(f"❌ FAIL：{len(FAILS)} 条断言未过")
    sys.exit(1)
print("✅ PASS：站点已删除（识别 / 牵连面 / 处置 / 红线）全部符合预期")
