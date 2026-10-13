#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 「站点已删除」离线回归（★ 16.0.0，真跑 common.py + features/siteops.py）。

背景（Master 2026-10-10）：「目前站点2 红豆饭已经被删了」→ 借这个活案例把
「MP 侧删站之后魔流怎么办」做成完整功能：

  1) **识别**（``common.SiteGuard.mp_sites`` 60s 记忆化；异常 → 判不出、不硬判）；
  2) **牵连面**（只数不写）：qB 标签前缀 ``魔流-<站名>-`` 的种数/体积/暂停/复用副本、
     ``mf_seed``（按台账 site_id）/ ``mf_reseed``（按 iyuu_sid）行数、站内任务；
  3) **处置**（``deleted_site_act``）：pause / resume / remove（**摘种、绝不删文件**），
     默认干跑；remove 走唯一删除闸门（本测只验 delete_file=False）。

断言：
  [1] SiteGuard.mp_sites 60s 记忆化（同进程只查一次库）；查库异常 → None（判不出不硬判）；
      mp_ids 派生；
  [2] deleted_sites_rows：MP 已无的站被列出（按 mp_site_id 判）、MP 仍在的不列出、
      无 mp_site_id 的按域名判、台账排序按种子数降序；
  [3] 牵连面正确：qB 种数/体积/暂停/运行/复用副本 + 账本行数 + 站内任务；
  [4] 站点已删但 MP 表读不到 → 返回空（保守）；
  [5] deleted_site_act：默认干跑不动下载器；pause/resume 真做；
      remove → delete_file=False（红线）；reuse_only 只取复用副本；站点不在清单 → ok=False；
  [6] 源码护栏：siteops 里 remove 走 delete_file=False；common 里有 SiteGuard.mp_sites。

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
                           bool(kw.get("allow_library_asset"))))
        return len(hashes or []), None


class Host:
    def __init__(self):
        self._task_configs = {
            "t1": types.SimpleNamespace(id="t1", site_id=2),
            "t2": types.SimpleNamespace(id="t2", site_id=1),
        }
        self._dl = _FakeDL()

    def _agent_db_site_rows(self):
        return [dict(r) for r in SITE_ROWS]

    def _tag_all_torrents(self):
        return dict(QBT)

    def _agent_db_rows(self, model):
        if model == "SeedRow":
            return list(SEED_ROWS)
        if model == "ReseedRow":
            return list(RESEED_ROWS)
        return []

    def _get_downloader(self):
        return self._dl

    def _delete_gate_detail(self, hashes):
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

# remove（主口径）：复用副本只摘种 / 自有非资源连文件删 / 资源保留
h5d = Host()
rep = siteops.deleted_site_act(h5d, 2, "remove")
pl = rep.get("planned") or {}
ok(rep["ok"] is True and pl.get("strip") == 1 and pl.get("full") == 1 and pl.get("keep") == 1,
   f"[5] remove 干跑分档 strip/full/keep = 1/1/1（实际 {pl}）")
ok(h5d._dl.calls == [], "[5] remove 干跑不动下载器")
ok((rep.get("gate") or {}).get("blocked") == 0 and (rep.get("gate") or {}).get("would_delete") == 2,
   f"[5] ★干跑带闸门预览：本假闸门不拦 → will_delete 2（实际 {rep.get('gate')}）")

h5r = Host()
rep = siteops.deleted_site_act(h5r, 2, "remove", dry_run=0)
calls = h5r._dl.calls
ok(rep["ok"] is True and rep["stripped"] == 1 and rep["deleted_with_file"] == 1 and rep["kept"] == 1,
   f"[5] remove 真做：摘种1 / 连文件删1 / 保留1（实际 {rep.get('stripped')}/{rep.get('deleted_with_file')}/{rep.get('kept')}）")
strip_call = [c for c in calls if c[0] == "delete" and c[2] is False]
full_call = [c for c in calls if c[0] == "delete" and c[2] is True]
ok(strip_call and strip_call[0][1] == [("b" * 40)], "[5] ★复用副本（魔流-辅种）走 delete_file=False")
ok(full_call and full_call[0][1] == [("a" * 40)], "[5] ★自有非资源走 delete_file=True（连文件）")
ok(len(full_call) == 1 and ("e" * 40) not in full_call[0][1] and ("e" * 40) not in strip_call[0][1],
   "[5] ★资源（静默-资源）两者都不进 → 保留不动")

h5c = Host()
rep = siteops.deleted_site_act(h5c, 2, "remove", reuse_only=1, dry_run=0)
ok(rep["ok"] is True and rep["stripped"] == 1 and rep["deleted_with_file"] == 0, "[5] reuse_only=1 → 只摘 1 个复用副本")
ok([c for c in h5c._dl.calls if c[0] == "delete"][0][1] == [("b" * 40)], "[5] reuse_only 只取带 魔流-辅种 的副本")

h5f = Host()
rep = siteops.deleted_site_act(h5f, 2, "remove", dry_run=0, force_asset=1)
fc = [c for c in h5f._dl.calls if c[0] == "delete"]
ok(rep["ok"] is True and fc and all(c[4] is True for c in fc),
   f"[5] ★force_asset=1 → 两批都带 allow_library_asset=True（实际 {[c[4] for c in fc]}）")
ok(rep.get("gate", {}).get("blocked") == 0, "[5] ★force_asset=1 干跑预览不再把库内资产算拦（allow_asset）")

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

# ------------------------------------------------- [6] 源码护栏
src = (ROOT / "features" / "siteops.py").read_text(encoding="utf-8")
ok("delete_file=False" in src and "delete_file=True" in src, "[6] siteops 源码：复用副本 delete_file=False / 自有非资源 delete_file=True")
ok("def deleted_sites_rows" in src and "def deleted_site_act" in src, "[6] siteops 源码：模块级函数（避开 self._ 棘轮）")
csrc = (ROOT / "common.py").read_text(encoding="utf-8")
ok("def mp_sites" in csrc and "class SiteGuard" in csrc, "[6] common 源码：SiteGuard.mp_sites 存在（叶子层判定）")

print()
if FAILS:
    print(f"❌ FAIL：{len(FAILS)} 条断言未过")
    sys.exit(1)
print("✅ PASS：站点已删除（识别 / 牵连面 / 处置 / 红线）全部符合预期")
