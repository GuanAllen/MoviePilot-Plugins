#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · H3/H4 趋势新鲜度回归（★ 19.12.84，真跑 features/health.py，不需 MoviePilot）。

背景（实测事故）：`site:17` 的最后采样点是 11-02 06:00（站点早已不在 MP 站点表、
也不在账本里），17 天后健康检查仍报「时魔下滑 52% · 24 小时前 30.5/h → 现在 14.8/h」。
读者会以为「现在正在掉」，实际是「那一天掉过一次，之后没有数据」。根因：H3/H4 拿
**序列末点**当「现在」，却没检查末点是不是还在更新（采样 1h/点）。

判据：末点年龄 > ``TREND_STALE_HOURS``（6h）→ 该序列不参与下滑/贴上限判定。

断言：
  1) 陈旧序列（375h）即便跌幅 52% → **不报**（这就是 site:17 的形态）；
  2) 新鲜序列（0.5h）同样跌幅 → warning，标题带百分比；
  3) 新鲜但跌幅不足（11%，未到 25%）→ 不报；
  4) 边界：5.9h 仍算新鲜 → 报；6.1h 已过期 → 不报；
  5) 单点/空序列 → 不报（H3 本来就要 ≥2 点）；
  6) 时魔为 0 的陈旧序列 → 不炸、不报。

用法：``python3 tools/test_health_trend_stale.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_trend_stale_test"
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
    """最小 Response 桩：trend.py 会构造 ``Response(success=..., data=...)``。"""

    def __init__(self, success: bool = True, message: str = "", data=None):
        self.success = success
        self.message = message
        self.data = data


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

for _name, _attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": _Resp}),
    ("app.schemas.types", {"EventType": type("EventType", (), {})}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
):
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

_dutyreg = types.ModuleType(PKG + ".dutyreg")
for _k, _v in (("ID_KEEP", "__keep__"), ("ID_CLAIM", "__claim__"),
               ("ID_HR_HOST", "__hr_host__"), ("ID_MUSIC", "__music__"),
               ("ID_ONDEMAND", "__ondemand__"), ("ID_CROSSSEED", "__crossseed__"),
               ("ID_SILENT_HOST", "__silent_host__")):
    setattr(_dutyreg, _k, _v)
_dutyreg.duty_name = lambda tid: str(tid or "")
sys.modules[PKG + ".dutyreg"] = _dutyreg

_norm = types.ModuleType(PKG + ".norm")
_norm.now_iso = lambda: "2026-11-19 00:00:00"
sys.modules[PKG + ".norm"] = _norm

_load(PKG + ".common", "common.py")

_hrbills = types.ModuleType(PKG + ".features.hrbills")
_hrbills.BILL_STATE_ACTIVE = "active"
_hrbills.BILL_STATE_BREACHED = "breached"
_hrbills.RULE_SITE_HR = "site_hr"
_hrbills.RULE_HIT_AND_RUN = "hit_and_run"
sys.modules[PKG + ".features.hrbills"] = _hrbills

health = _load(PKG + ".features.health", "features/health.py")

_kv = types.ModuleType(PKG + ".kvstore")
_kv.cache_get = lambda *a, **k: None
_kv.cache_set = lambda *a, **k: True
sys.modules[PKG + ".kvstore"] = _kv
trend = _load(PKG + ".features.trend", "features/trend.py")


def chk(name, cond, got=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ← {got}"))
    if not cond:
        FAILED.append(name)


def _series(age_h: float, bonus_now: float, bonus_prev: float):
    """末点 age_h 小时前，另给一个 24h 之前（更早）的点。"""
    now = time.time()
    t_last = now - age_h * 3600.0
    return [
        {"t": t_last - 26 * 3600.0, "bonus": bonus_prev},
        {"t": t_last - 24 * 3600.0, "bonus": bonus_prev},
        {"t": t_last, "bonus": bonus_now},
    ]


def issues_for(series_map):
    class Fake(health.HealthMixin):
        _task_configs = {}
        _store = None

        def _trend_data(self):
            return series_map

        def _list_sites(self):
            return []

        def _health_hr_crosscheck(self):
            return []

    return Fake()._health_issues()


def _h3(res):
    return [i for i in res if str(i.get("key", "")).startswith("H3:")]


# 1) site:17 的真实形态：末点 17 天前，跌幅 55% → 不该报
r = issues_for({"site:17": _series(375.0, 14.7806, 32.68)})
chk("①陈旧序列(375h)即便跌 55%→不报", _h3(r) == [], r)

# 2) 新鲜序列，同样跌幅 → 报，标题带百分比
r = issues_for({"site:1": _series(0.5, 14.78, 32.68)})
_i = _h3(r)
chk("②新鲜序列跌 55%→warning", bool(_i) and _i[0]["level"] == "warning", r)
chk("②标题带跌幅", bool(_i) and "%" in str(_i[0].get("title")), _i)
chk("②详情是「24 小时前→现在」", bool(_i) and "24 小时前" in str(_i[0].get("detail")), _i)

# 3) 新鲜但只跌 11%（未到 25% 阈值）→ 不报
r = issues_for({"site:1": _series(0.5, 29.0, 32.68)})
chk("③跌幅不足→不报", _h3(r) == [], r)

# 4) 边界：5.9h 新鲜 / 6.1h 过期
r = issues_for({"site:1": _series(5.9, 14.78, 32.68)})
chk("④5.9h 仍新鲜→报", len(_h3(r)) == 1, r)
r = issues_for({"site:1": _series(6.1, 14.78, 32.68)})
chk("④6.1h 已过期→不报", _h3(r) == [], r)

# 5) 单点 / 空序列
r = issues_for({"site:2": [{"t": time.time(), "bonus": 9.9}], "site:3": []})
chk("⑤单点/空序列→不报", _h3(r) == [], r)

# 6) 陈旧且时魔为 0 → 不炸
r = issues_for({"site:9": _series(500.0, 0.0, 0.0)})
chk("⑥陈旧+零时魔→不炸", _h3(r) == [], r)

# 7) 多序列混合：只报新鲜的那条
r = issues_for({
    "site:17": _series(375.0, 14.78, 32.68),
    "site:1": _series(0.2, 14.78, 32.68),
    "site:5": _series(0.3, 29.0, 32.68),
})
_i = _h3(r)
chk("⑦混合场景只报 1 条且是新鲜那条",
    len(_i) == 1 and "site:1" in str(_i[0].get("key")), _i)

# 8) 反向验证：把闸放宽到无限大，同一条陈旧序列**就会**报 —— 证明静默来自这道闸，
#    而不是别的条件恰好不满足（否则这个修复可能是假绿）
_old = health.TREND_STALE_SEC
try:
    health.TREND_STALE_SEC = 1e12
    r = issues_for({"site:17": _series(375.0, 14.7806, 32.68)})
    chk("⑧闸放宽后同一序列会报（证明闸在起作用）", len(_h3(r)) == 1, r)
finally:
    health.TREND_STALE_SEC = _old

# ------------------------------------------- 趋势序列清理（口径：这个 key 还能不能续写）
# ★ 19.12.85：判据从「末点超 7 天」改成「对象还在不在」。任务停掉 → 序列断是正常的
#   （主人 2026-11-19 10:12），恢复后会续写同一个 key，不能当垃圾清掉。
_NOW = time.time()
_prune_data = {
    "site:17": [{"t": _NOW - 375 * 3600, "bonus": 14.78}],       # 站点已删 → 清
    "site:?": [{"t": _NOW - 1037 * 3600, "bonus": 0.0}],         # 非法 key → 清
    "task:dead": [{"t": _NOW - 200 * 3600, "bonus": 1.0}],       # 任务已删 → 清
    "task:stopped01": [{"t": _NOW - 240 * 3600, "bonus": 3.0}],  # 任务停着（还在）→ 留
    "site:3": [{"t": _NOW - 240 * 3600, "bonus": 8.0}],          # 站点还在、只是没采样 → 留
    "site:1": [{"t": _NOW - 0.2 * 3600, "bonus": 50.0}],         # 新鲜
    "task:live": [{"t": _NOW - 0.3 * 3600, "bonus": 2.0}],       # 新鲜
    "task:__crossseed__": [{"t": _NOW - 1038 * 3600, "bonus": 0.0}],  # host 伪任务（不在任务表）→ 留
}
_TASKS = {"live": {}, "stopped01": {}}
_MP = {1, 3}


class _Guard:
    def __init__(self, mp):
        self._mp = mp

    def mp_ids(self):
        return None if self._mp is None else set(self._mp)


class _FakeTrend(trend.TrendMixin):
    def __init__(self, data, tasks=None, mp=None):
        self._d = data
        self._trend_dirty = False
        self.flushed = 0
        self._task_configs = dict(_TASKS if tasks is None else tasks)
        self._g = _Guard(_MP if mp is None else mp)

    def _trend_data(self):
        return self._d

    def _trend_flush(self):
        self.flushed += 1
        return True

    def _log(self, *a, **k):
        pass


_orig_guard = trend.site_guard
trend.site_guard = lambda host: host._g

_f = _FakeTrend(dict(_prune_data))
_r = _f._trend_prune(apply=False)
_dd = _r.data or {}
_why = {x["key"]: x["why"] for x in (_dd.get("dead") or [])}
chk("⑨干跑只列 3 条「再也写不回来」的", _dd.get("count") == 3, _dd.get("keys"))
chk("⑨站点已删归 site_gone", _why.get("site:17") == "site_gone", _why)
chk("⑨任务已删归 task_gone", _why.get("task:dead") == "task_gone", _why)
chk("⑨非法 key 归 invalid_key", _why.get("site:?") == "invalid_key", _why)
_idle = {x["key"] for x in (_dd.get("idle") or [])}
chk("⑨停掉的任务不删（序列能续写）",
    "task:stopped01" in _idle and "task:stopped01" not in _why, (_idle, _why))
chk("⑨站点还在、只是停采样也不删",
    "site:3" in _idle and "site:3" not in _why, (_idle, _why))
chk("⑨新鲜序列两边都不列",
    "site:1" not in _why and "site:1" not in _idle, (_idle, _why))
chk("⑨host 伪任务不在任务表也不能清",
    "task:__crossseed__" in _idle and "task:__crossseed__" not in _why, (_idle, _why))
chk("⑨干跑不删任何 key", len(_f._d) == len(_prune_data) and _f.flushed == 0, _f._d.keys())

_f2 = _FakeTrend(dict(_prune_data))
_r2 = _f2._trend_prune(apply=True)
chk("⑩apply 只删 3 条、保留 5 条",
    sorted(_f2._d) == sorted(["task:stopped01", "site:3", "site:1", "task:live",
                              "task:__crossseed__"]),
    sorted(_f2._d))
chk("⑩apply 落盘一次", _f2.flushed == 1, _f2.flushed)
chk("⑩回报 kept=5", (_r2.data or {}).get("kept") == 5, _r2.data)

# 判不出就不清：站点表查不到 → site_gone 一律不成立（宁可留垃圾也别误删）
_f3 = _FakeTrend(dict(_prune_data), mp=None)
_f3._g._mp = None
_r3 = _f3._trend_prune(apply=False)
_why3 = {x["key"]: x["why"] for x in ((_r3.data or {}).get("dead") or [])}
chk("⑪查库失败→站点口径不清", "site:17" not in _why3, _why3)
chk("⑪查库失败不影响任务口径", _why3.get("task:dead") == "task_gone", _why3)
chk("⑪回报标记 mp_sites_ok=False", (_r3.data or {}).get("mp_sites_ok") is False, _r3.data)

# 任务表为空（插件没热起来）→ 任务口径也不清
_f4 = _FakeTrend(dict(_prune_data), tasks={})
_r4 = _f4._trend_prune(apply=False)
_why4 = {x["key"]: x["why"] for x in ((_r4.data or {}).get("dead") or [])}
chk("⑫任务表空→任务口径不清", "task:dead" not in _why4, _why4)
chk("⑫任务表空仍清非法 key", _why4.get("site:?") == "invalid_key", _why4)

trend.site_guard = _orig_guard

print()
if FAILED:
    print(f"❌ 合计 {len(FAILED)} 项失败：{FAILED}")
    sys.exit(1)
print("✅ 全部通过（H3/H4 趋势新鲜度）")
