#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 站点上报时魔「直读缓存 + 抓取写回」离线回归（★ 15.2.1，真跑 features/formula.py）。

背景（Master 2026-10-07）：「这里的数量读的哪里……总是有缺时魔的情况，为什么不取到了再更新缓存」。
真相：MP 是 Redis（``CACHE_BACKEND_TYPE=redis``）；魔流的站点公式缓存 = ``TierCache``
（进程内热层 + Redis 冷层，region=``formula``）**本来就落在 Redis**。会「缺」是因为
读路径用 1h TTL 卡：过期瞬间 ``cache.get(domain, 3600)`` 返回 None → UI 显示 0，直到后台
抓完写回。本版改成 **stale-while-revalidate**：缓存（Redis）里的最近值**直接读**（STALE_MAX
窗口内先给 UI），过旧才后台重抓并**写回 Redis**。

断言：
  1) 常量口径：``SITE_FORMULA_STALE_MAX > SITE_FORMULA_TTL``、``ZERO_TTL`` 短窗口；
  2) fresh 非零值 → 直接返回、**不**触发重抓；
  3) stale 非零值（TTL 外、STALE_MAX 内）→ **仍返回旧值**（不再显示 0/缺）+ 触发后台重抓；
  4) 超出 STALE_MAX → 当作无（返回 None）+ 触发重抓；
  5) 近期零值（< ZERO_TTL）→ 返回该 0 值、不重抓；
  6) 过旧零值（> ZERO_TTL 且任务启用）→ 当作无（None）+ 尽快重抓（别钉 0）；
  7) 停用任务遇 stale 非零 → 返回旧值但**不**打站点；
  8) 完全无值 → None + 触发重抓（非阻塞）；
  9) 源码护栏：写回用 ``SITE_FORMULA_STALE_MAX``（Redis 键才活得够久）。

用法：``python3 tools/test_formula_stale.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_formula_test"

FAILS: list[str] = []


def ok(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)
        print(f"  ✗ {msg}")
    else:
        print(f"  ✓ {msg}")


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


# ---- 桩 app.*（无 MoviePilot；FileCache 缺失 → TierCache 退化纯内存热层，够测读路径）----
for _n in ("app", "app.schemas", "app.sdk"):
    if _n not in sys.modules:
        sys.modules[_n] = types.ModuleType(_n)
_types = types.ModuleType("app.schemas.types")
_types.EventType = type("EventType", (), {})
sys.modules["app.schemas.types"] = _types
_events = types.ModuleType("app.sdk.events")
_events.eventmanager = types.SimpleNamespace()
sys.modules["app.sdk.events"] = _events
# 注意：**不**提供 app.sdk.cache → TierCache._backend=None → 纯内存热层

_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

# ---- 真模块：fingerprint / common / dtier ----
_load(PKG + ".fingerprint", "fingerprint.py")
common = _load(PKG + ".common", "common.py")
dtier = _load(PKG + ".dtier", "dtier.py")

# ---- 桩兄弟模块（formula.py 的 import 依赖）----
for _sub, _attrs in {
    "bonus": ["BonusParams", "TorrentBonusInfo", "calc_torrent_bonus"],
    "downloader_ops": ["TorrentInfo"],
    "fetcher": ["SITE_TZ_OFFSET_HOURS", "pubdate_to_ts", "ts_to_age_weeks"],
    "persistence": ["OperationItem"],
    "recommend": ["_norm"],
}.items():
    m = types.ModuleType(PKG + "." + _sub)
    for a in _attrs:
        setattr(m, a, type(a, (), {}))
    sys.modules[PKG + "." + _sub] = m

_sites = types.ModuleType(PKG + ".sites")
_sites.get_formula_params = lambda *a, **k: {}
_sites.register_formula_preset = lambda *a, **k: None
sys.modules[PKG + ".sites"] = _sites
_ff = types.ModuleType(PKG + ".sites.formula_fetch")
_ff.fetch_site_formula = lambda *a, **k: None
_ff.fetch_seeding_list = lambda *a, **k: []
_ff.fetch_official_titles = lambda *a, **k: []
_ff._norm_title = lambda s: s
sys.modules[PKG + ".sites.formula_fetch"] = _ff

formula = _load(PKG + ".features.formula", "features/formula.py")

STALE_MAX = common.SITE_FORMULA_STALE_MAX
TTL = common.SITE_FORMULA_TTL
ZERO_TTL = common.SITE_FORMULA_ZERO_TTL


class _Cap:
    """最小 FormulaCapture 形状：``_formula_report_empty`` 只看 ``extra``。"""

    def __init__(self, total):
        self.ok = True
        self.note = "test"
        self.params = {}
        self.extra = {"total_bonus_per_hour": total}


class _Task:
    def __init__(self, domain="hdfans.org", enabled=True):
        self.site_domain = domain
        self.site_name = "测试站"
        self.site_id = 1
        self.enabled = enabled


class Host(formula.FormulaMixin):
    def __init__(self):
        self._cache = dtier.TierCache("formula")
        self.fetches = []

    def _cache_formula(self):
        return self._cache

    def _log(self, *a, **k):
        pass

    def _schedule_formula_fetch(self, task, domain, cache):
        self.fetches.append(domain)

    def _put(self, domain, cap, age_s):
        """写入一份 caption 并把热层时间戳回拨 ``age_s`` 秒（模拟陈旧）。"""
        self._cache.set(domain, cap, STALE_MAX)
        self._cache._hot[domain]["ts"] = time.time() - float(age_s)


print("== ① 常量口径 ==")
ok(STALE_MAX > TTL, f"STALE_MAX({STALE_MAX}) > TTL({TTL})")
ok(0 < ZERO_TTL < TTL, f"ZERO_TTL({ZERO_TTL}) 是短窗口")

print("== ② fresh 非零 → 返回且不重抓 ==")
h = Host()
task = _Task()
h._put("hdfans.org", _Cap(10.0), 10)
got = h._acquire_site_formula(task)
ok(got is not None and got.extra["total_bonus_per_hour"] == 10.0, "返回 fresh 值")
ok(h.fetches == [], "未触发重抓")

print("== ③ stale 非零（TTL 外 / STALE_MAX 内）→ 仍返回旧值 + 重抓 ==")
h = Host()
h._put("hdfans.org", _Cap(20.0), TTL + 300)
got = h._acquire_site_formula(task)
ok(got is not None and got.extra["total_bonus_per_hour"] == 20.0, "★ 返回 stale 旧值（不再缺/0）")
ok(h.fetches == ["hdfans.org"], "触发后台重抓")

print("== ④ 超出 STALE_MAX → 当作无 + 重抓 ==")
h = Host()
h._put("hdfans.org", _Cap(30.0), STALE_MAX + 300)
got = h._acquire_site_formula(task)
ok(got is None, "超出窗口返回 None")
ok(h.fetches == ["hdfans.org"], "触发后台重抓")

print("== ⑤ 近期零值（< ZERO_TTL）→ 返回、不重抓 ==")
h = Host()
h._put("hdfans.org", _Cap(0.0), ZERO_TTL - 60)
got = h._acquire_site_formula(task)
ok(got is not None, "返回近期 0 值")
ok(h.fetches == [], "未重抓")

print("== ⑥ 过旧零值（> ZERO_TTL 且启用）→ None + 尽快重抓 ==")
h = Host()
h._put("hdfans.org", _Cap(0.0), ZERO_TTL + 300)
got = h._acquire_site_formula(task)
ok(got is None, "过旧 0 值当作无（不钉 0）")
ok(h.fetches == ["hdfans.org"], "尽快重抓")

print("== ⑦ 停用任务遇 stale 非零 → 返回旧值、不打站点 ==")
h = Host()
h._put("hdfans.org", _Cap(40.0), TTL + 300)
got = h._acquire_site_formula(_Task(enabled=False))
ok(got is not None and got.extra["total_bonus_per_hour"] == 40.0, "停用任务返回旧值")
ok(h.fetches == [], "停用任务不重抓")

print("== ⑧ 完全无值 → None + 重抓 ==")
h = Host()
got = h._acquire_site_formula(_Task())
ok(got is None, "无值返回 None")
ok(h.fetches == ["hdfans.org"], "触发后台重抓")

print("== ⑨ 源码护栏：写回用 STALE_MAX ==")
src = (ROOT / "features" / "formula.py").read_text(encoding="utf-8")
ok("cache.set(domain, cap, SITE_FORMULA_STALE_MAX)" in src, "抓取写回按 STALE_MAX（Redis 键活得够久）")
ok("cache.get(domain, SITE_FORMULA_STALE_MAX)" in src, "读路径按 STALE_MAX 直读最近值")

print()
if FAILS:
    print(f"FAIL：{len(FAILS)} 条不达预期")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("PASS：全部断言通过")
