#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 孤儿站点（任务绑的站点已被 MP 删除）离线回归（★ 15.8.9，真跑 features/*.py）。

背景（Master 2026-10-09）：「魔流删除 mp 的红豆饭站点后一直报站点2不存在」。
真相：``site`` 表里 id=2 已删，但 ``plugininstance.config_data['tasks']`` 里那条
「红豆饭刷魔」还在（站点是在 MP 界面删的，魔流没有删站能力）。状态统计每轮枚举**全部**
任务（含 run_mode=stopped），于是 ``formula._schedule_formula_fetch`` 每轮都
``_get_site() → None`` 重排一次抓取、刷一条 ``站点公式:未找到站点 2,本轮跳过``。

本版把「站点没了」变成**一等状态**（判定收在叶子层 ``common.SiteGuard``，各 feature 用
模块级 ``site_guard(self)`` 取用，不新增 ``self._`` 跨文件互调）：
  * ``SiteGuard.exists``（60s 记忆化；查库异常保守按「存在」）；
  * ``SiteGuard.missing`` / ``warn``（同 task+site 只提示一次）/ ``clear``（复位）；
  * status 统计出 ``site_missing`` 并**跳过**站点相关块（站点上报 / 上限公式）；
  * formula 先判站点再判 PV 闸门（不存在的站点不该占预算）。

断言：
  1) ``exists`` 60s 记忆化：同 sid 只查一次库；不存在的 sid 返回 False；
  2) 查库抛异常 → 保守 True + 一条 warning（不把整排任务误判成孤儿）；
  3) ``missing``：存在→False；已删→True；无 site_id(0)→False 且不查库；非数字→False；
  4) ``warn`` 按 (task.id, site_id) 去重：连报 5 次只出 1 条；换任务要各报一次；
  5) ``clear`` 复位后（站点回来过）能再报；``site_guard`` 同一 host 复用同一实例；
  6) status：孤儿任务 ``site_missing=True``、**不**调站点上报/公式参数/上限（旧版每轮都抓）、
     连算 3 轮只 1 条告警、其余字段照旧返回；
  7) status：正常任务 ``site_missing=False`` 且站点上报/上限照旧；
  8) status：``_runtime_stats_bulk`` 预热只预热正常任务（孤儿跳过）；
  9) formula：孤儿任务不占 PV 预算、不抓公式；正常任务照旧走 PV 闸门 + 抓公式；
 10) ``_build_task_detail`` 带 ``site_missing``；
 11) 源码护栏：判定在 common（叶子层）+ formula 站点判定在 PV 闸门之前（防回归）。

用法：``python3 tools/test_orphan_site.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_orphan_test"

FAILS: list[str] = []


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


def _stub_pkg(name: str, path: Path | None = None) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        sys.modules[name] = m
    if path is not None:
        m.__path__ = [str(path)]
    return m


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- 站点表桩
SITE_DB = {"ids": {9}}  # 现存站点 id（真实环境：1,3,4,5,7..16；2 与 6 已删）
SITE_CALLS = {"n": 0}
RAISE_SITE = {"on": False}


class _FakeSite:
    def __init__(self, sid: int):
        self.id = sid
        self.name = f"站点{sid}"
        self.domain = f"s{sid}.test"


class _FakeSiteOper:
    def get(self, sid):
        SITE_CALLS["n"] += 1
        if RAISE_SITE["on"]:
            raise RuntimeError("db boom")
        try:
            sid = int(sid or 0)
        except (TypeError, ValueError):
            return None
        return _FakeSite(sid) if sid in SITE_DB["ids"] else None


# --------------------------------------------------- 1. 桩 app.* 与兄弟模块
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

_stub_pkg(PKG, ROOT)
_stub_pkg(PKG + ".features", ROOT / "features")
_sites_pkg = _Stub(PKG + ".sites")
_sites_pkg.__path__ = [str(ROOT / "sites")]
sys.modules[PKG + ".sites"] = _sites_pkg
_sites_pkg.get_formula_params = lambda *a, **k: {}
_sites_pkg.register_formula_preset = lambda *a, **k: None

FF = _Stub(PKG + ".sites.formula_fetch")
FF.__path__ = [str(ROOT / "sites" / "formula_fetch")]
FETCHED: list = []
FF.fetch_site_formula = lambda site, timeout=15, force=False: (FETCHED.append((site, force)), None)[1]
FF.fetch_seeding_list = lambda *a, **k: []
FF.fetch_official_titles = lambda *a, **k: []
FF._norm_title = lambda s: s
sys.modules[PKG + ".sites.formula_fetch"] = FF

for _sub in (
    "fetcher", "recommend", "models", "persistence", "downloader_ops", "dtier",
    "tags", "kvstore", "signin", "sitestore", "fallback", "collect",
    "cloud_archive",
):
    sys.modules.setdefault(PKG + "." + _sub, _Stub(PKG + "." + _sub))

# site_ceiling 给个真函数：才能断言「正常任务算了上限、孤儿任务没算」
_bonus = _Stub(PKG + ".bonus")
_bonus.site_ceiling = lambda params: 12.0
sys.modules[PKG + ".bonus"] = _bonus
_formulas = _Stub(PKG + ".formulas")
_formulas.site_ceiling = lambda params: 12.0
sys.modules[PKG + ".formulas"] = _formulas

common = _load(PKG + ".common", "common.py")
formula = _load(PKG + ".features.formula", "features/formula.py")
status_mod = _load(PKG + ".features.status", "features/status.py")


# --------------------------------------------------------------------- 假任务
class _Task:
    def __init__(self, tid: str, sid, domain: str = ""):
        self.id = tid
        self.name = f"任务{tid}"
        self.site_id = sid
        self.site_domain = domain
        self.site_name = ""
        self.downloader = "qbittorrent"
        self.brush_tag = f"魔流-{tid}"
        self.task_type = "bonus"
        self.run_mode = "running"
        self.enabled = True
        self.brush_interval = 30
        self.check_interval = 30
        self.protected_count = 0

    def to_dict(self):
        return {"id": self.id, "name": self.name, "site_id": self.site_id,
                "site_domain": self.site_domain, "site_name": self.site_name}


class Host(status_mod.StatusMixin, formula.FormulaMixin):
    def __init__(self):
        self.logs: list = []
        self.reported: list = []
        self.params_calls: list = []
        self.pv_calls: list = []
        self.prewarm: list = []
        self._store = None
        self._task_runs: dict = {}
        self._task_run_timeout = 60.0
        self._stats_cache: dict = {}
        self._task_configs: dict = {}

    # ---- 观测点
    def _log(self, msg, level="info"):
        self.logs.append((str(level), str(msg)))

    def warn_lines(self, needle="已不存在"):
        return [m for lv, m in self.logs if lv == "warning" and needle in m]

    # ---- 站点/统计依赖
    def _get_site(self, site_id):
        sid = int(site_id or 0)
        return _FakeSite(sid) if sid in SITE_DB["ids"] else None

    def _site_reported(self, task):
        self.reported.append(task.id)
        return {"bonus_per_hour": 1.25, "a": 2.5, "ok": True, "current_bonus": 100.0,
                "user": {"up": 1}, "age_s": 5, "stale": False}

    def _build_formula_params(self, task):
        self.params_calls.append(task.id)
        return types.SimpleNamespace(seeding_count_cap=4)

    def _task_managed_torrents(self, task, view=True):
        return []

    def _hr_owed_by_site(self):
        return {}

    def _acquire_site_formula(self, task):
        self.prewarm.append(task.id)

    def _pv_block_reason(self, sid):
        self.pv_calls.append(("block", sid))
        return None

    def _pv_allow(self, sid, kind, want=1):
        self.pv_calls.append(("allow", sid))
        return True

    def _get_task_config(self, task_id):
        return self._task_configs.get(task_id)

    def _task_goal_status(self, task):
        return {}

    def _wait_flights(self, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not getattr(self, "_formula_flights", None):
                return True
            time.sleep(0.02)
        return not getattr(self, "_formula_flights", None)


print("魔流 · 孤儿站点离线回归（★ 15.8.9）")

# ------------------------------------------------- [1] exists 记忆化
h = Host()
g = common.site_guard(h)
ok(g.exists(9) is True, "站点存在 → True")
ok(g.exists(9) is True, "同 sid 二次判定仍 True（命中缓存）")
ok(SITE_CALLS["n"] == 1, f"60s 内同 sid 只查一次库（实际 {SITE_CALLS['n']} 次）")
ok(g.exists(2) is False, "站点已删 → False")
ok(SITE_CALLS["n"] == 2, "不同 sid 各查一次")
ok(g.exists(2) is False and SITE_CALLS["n"] == 2, "已删结论同样被缓存")
ok(g.exists(0) is False and SITE_CALLS["n"] == 2, "site_id=0 → False 且不查库")
ok(common.SITE_EXISTS_TTL == 60.0, "SITE_EXISTS_TTL = 60s")
ok(common.site_guard(h) is g, "同一 host 复用同一 SiteGuard 实例")

# ------------------------------------------------- [2] 查库异常 → 保守 True
h2 = Host()
g2 = common.site_guard(h2)
RAISE_SITE["on"] = True
try:
    got = g2.exists(7)
finally:
    RAISE_SITE["on"] = False
ok(got is True, "查库异常 → 保守按「存在」")
ok(len(h2.warn_lines("站点存在性检查失败")) == 1, "查库异常留一条 warning 便于排查")

# ------------------------------------------------- [3] missing
h3 = Host()
g3 = common.site_guard(h3)
ok(g3.missing(_Task("a", 9)) is False, "站点存在 → 不是孤儿")
ok(g3.missing(_Task("b", 2)) is True, "站点已删 → 孤儿")
n_before = SITE_CALLS["n"]
ok(g3.missing(_Task("c", 0)) is False, "无 site_id → 不是孤儿")
ok(g3.missing(_Task("d", None)) is False, "site_id=None → 不是孤儿")
ok(SITE_CALLS["n"] == n_before, "无 site_id / None 不查库")

# ------------------------------------------------- [4][5] 告警去重 + 复位
h4 = Host()
g4 = common.site_guard(h4)
t_bad = _Task("b54b279a22c0", 2)
for _ in range(5):
    g4.warn(t_bad, 2)
ok(len(h4.warn_lines()) == 1, f"同一孤儿任务连报 5 次只出 1 条（实际 {len(h4.warn_lines())}）")
g4.warn(_Task("other", 2), 2)
ok(len(h4.warn_lines()) == 2, "换任务各有一次提示")
g4.clear(t_bad, 2)
g4.warn(t_bad, 2)
ok(len(h4.warn_lines()) == 3, "站点回来复位后再删 → 能再报一次")

# ------------------------------------------------- [6][7] status 统计
h6 = Host()
t_orphan = _Task("orphan", 2, domain="hdfans.org")
for _ in range(3):
    st = h6._task_runtime_stats(t_orphan, force=True)
ok(st.get("site_missing") is True, "孤儿任务 stats['site_missing'] = True")
ok(h6.reported == [], "孤儿任务不调站点上报（旧版每轮都抓）")
ok(h6.params_calls == [], "孤儿任务不算上限/公式参数")
ok(float(st.get("site_ceiling") or 0.0) == 0.0, "孤儿任务 site_ceiling 保持 0")
ok(len(h6.warn_lines()) == 1, f"连算 3 轮只 1 条孤儿告警（实际 {len(h6.warn_lines())}）")
ok(st.get("seeding_count") == 0 and st.get("state") == "idle", "其余统计字段照旧返回")

h7 = Host()
t_ok_task = _Task("good", 9, domain="s9.test")
st7 = h7._task_runtime_stats(t_ok_task, force=True)
ok(st7.get("site_missing") is False, "正常任务 site_missing=False")
ok(h7.reported == ["good"], "正常任务照旧读站点上报")
ok(float(st7.get("site_ceiling") or 0.0) == 12.0, "正常任务照旧算上限")
ok(h7.warn_lines() == [], "正常任务不产生孤儿告警")

# ------------------------------------------------- [8] 预热只预热正常任务
h8 = Host()
bulk = h8._runtime_stats_bulk([t_orphan, t_ok_task])
ok(h8.prewarm == ["good"], f"预热只覆盖正常任务（实际 {h8.prewarm}）")
ok(sorted(bulk.keys()) == ["good", "orphan"], "并发统计两个任务都返回")
ok(bulk["orphan"]["site_missing"] is True and bulk["good"]["site_missing"] is False,
   "并发统计里孤儿标记正确")

# ------------------------------------------------- [9] formula 调度
h9 = Host()
FETCHED.clear()
h9._schedule_formula_fetch(t_orphan, "hdfans.org", None)
h9._wait_flights()
ok(FETCHED == [], "孤儿任务不抓公式")
ok(h9.pv_calls == [], "孤儿任务不占 PV 预算（站点判定在闸门之前）")
ok(len(h9.warn_lines()) == 1, "孤儿任务在公式路径也提示一次")

h9b = Host()
FETCHED.clear()
h9b._schedule_formula_fetch(t_ok_task, "s9.test", _Stub("cache"))
h9b._wait_flights()
ok(len(FETCHED) == 1, f"正常任务照旧抓一次公式（实际 {len(FETCHED)}）")
ok(("allow", 9) in h9b.pv_calls, "正常任务仍走 PV 闸门")
ok(h9b.warn_lines() == [], "正常任务无孤儿告警")

# ------------------------------------------------- [10] 任务详情带标记
h10 = Host()
h10._task_configs["orphan"] = t_orphan
det = h10._build_task_detail("orphan")
ok(isinstance(det, dict) and det.get("site_missing") is True, "详情接口带 site_missing=True")
h10._task_configs["good"] = t_ok_task
ok(h10._build_task_detail("good").get("site_missing") is False, "详情接口正常任务 site_missing=False")

# ------------------------------------------------- [11] 源码护栏
status_src = (ROOT / "features" / "status.py").read_text(encoding="utf-8")
formula_src = (ROOT / "features" / "formula.py").read_text(encoding="utf-8")
common_src = (ROOT / "common.py").read_text(encoding="utf-8")
core_src = (ROOT / "features" / "core.py").read_text(encoding="utf-8")
ok('"site_missing": False' in status_src, "status 默认字段含 site_missing")
ok("if site_guard(self).missing(t):" in status_src and "continue" in status_src,
   "status 预热循环带孤儿跳过")
ok('"site_missing": site_guard(self).missing(task)' in status_src, "详情返回 site_missing")
ok("class SiteGuard" in common_src and "SITE_EXISTS_TTL" in common_src
   and "def site_guard" in common_src, "判定收在叶子层 common.SiteGuard")
ok("def _site_exists" not in core_src, "core 不再自持站点判定（避免跨文件 self._ 互调）")
_pv_at = formula_src.find("if self._pv_block_reason(sid)")
_site_at = formula_src.find("site = self._get_site(sid) if sid else None")
_warn_at = formula_src.find("site_guard(self).warn(task, sid)")
ok(0 <= _site_at < _warn_at < _pv_at, "formula 站点判定在 PV 闸门之前")

print()
if FAILS:
    print(f"❌ FAIL（{len(FAILS)} 项）")
    for f in FAILS:
        print("   - " + f)
    sys.exit(1)
print("✅ PASS：孤儿站点识别 / 只提示一次 / 统计与公式跳过 / 详情标记 全部符合预期")
sys.exit(0)
