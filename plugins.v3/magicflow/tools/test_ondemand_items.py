#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播清单（★ 15.4.0）离线回归 —— 真跑 features/ondemand.py，不需 MoviePilot / qB。

背景（Master 2026-10-07 15:13「点播下载的任务看不到进度和历史」）：
  点播只有「搜索 → 选源 → 下载」，下完弹窗只回一句「已下载：hash」——
  下载到哪了、有没有转资源、历史上点播过什么，全无处置信。

本版在点播弹窗里加「点播清单」：**进行中（带进度）+ 已完成（历史）**。
真值源（只读，不新造）：
  · 进行中 = ``ondemand_pending``（``mf_seed.pending``）× qB 快照（progress/state/dl_speed）；
  · 历史 = journal（``items[].source == "ondemand"``）＋ 种子账本（state/sub/in_library/identity_at）。

断言：
  [1] 进行中：下载中 → stage=downloading + 进度/剩余/速度/ETA；
  [2] 进行中：已下完但账本身份还没转 → stage=pending_settle；
  [3] 进行中：账本身份已是「资源」→ stage=resource；
  [4] 进行中：不在 qB → stage=gone（不报错）；
  [5] 历史：标题去「点播」前缀；结果**现况回查**（已转资源·已入库 / 已移出）；
  [6] 历史：与「进行中」同 hash 去重（同一条不会两处都出现）；
  [7] totals：inflight/downloading/history/left_gb 统计；
  [8] limit 上限（>200 截到 200）。

用法：``python3 tools/test_ondemand_items.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_ondemand_test"


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

# 真 tags.py（纯函数）
tags = _load(PKG + ".tags", "tags.py")

# 桩：app.schemas.Response
_app = types.ModuleType("app")
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = type("Response", (), {})
sys.modules.setdefault("app", _app)
sys.modules["app.schemas"] = _app_schemas

# 桩：..recommend（只用 recognize）+ ..sitestore（只用 slot_callbacks）
_rec = types.ModuleType(PKG + ".recommend")
_rec.recognize = lambda *a, **k: None
sys.modules[PKG + ".recommend"] = _rec
_site = types.ModuleType(PKG + ".sitestore")
_site.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
sys.modules[PKG + ".sitestore"] = _site

# 真 persistence.py（stdlib，提供 OperationItem）
_load(PKG + ".persistence", "persistence.py")

ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")
OnDemandMixin = ondemand.OnDemandMixin
SUB_RESOURCE = tags.SUB_RESOURCE

FAILS = []
N = 0


def ok(cond, label):
    global N
    N += 1
    if not cond:
        FAILS.append(label)
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


class _Journal:
    def __init__(self, recs):
        self._recs = list(recs)

    def list_recent(self, limit=100, kind=None):
        return self._recs[:limit]


class Fake(OnDemandMixin):
    """只提供清单路径要用的真值源。"""

    def __init__(self, pend=None, snap=None, ledger=None, journal=None):
        self._pend = dict(pend or {})
        self._snap = dict(snap or {})
        self._ledger = dict(ledger or {})
        self._store = SimpleNamespace(journal=_Journal(journal or []))

    # --- 真值源桩
    def _ondemand_all(self):
        return dict(self._pend)

    def _tag_all_torrents(self):
        return dict(self._snap)

    def _tag_state(self):
        return _Ledger(self._ledger)


class _Ledger:
    def __init__(self, d):
        self._d = d

    def get(self, h):
        return self._d.get(str(h or "").lower())


def _qbt(progress=0.0, state="downloading", size_gb=10.0, speed=0.0, ratio=0.0):
    return SimpleNamespace(progress=progress, state=state, size_gb=size_gb,
                           download_speed=speed, ratio=ratio)


def _op(h, title, source="ondemand", ts=1000.0, reason="源 财神·免费", size_gb=3.0):
    return SimpleNamespace(operation_id=h[:8], created_at=ts,
                           items=[SimpleNamespace(hash=h, title=title, reason=reason,
                                                  source=source, size_gb=size_gb)])


H1 = "a" * 40
H2 = "b" * 40
H3 = "c" * 40
H4 = "d" * 40

# ---------------------------------------------------------------- [1] 下载中
print("[1] 进行中：下载中（进度/剩余/速度/ETA）")
f = Fake(
    pend={H1: {"title": "流浪地球", "year": "2019", "site": "聆音", "free": True, "ts": 1000.0}},
    snap={H1: _qbt(progress=0.42, size_gb=10.0, speed=2 * 1024 ** 2)},
)
rows = f._ondemand_items()["inflight"]
ok(len(rows) == 1, "1 条进行中")
r = rows[0]
ok(r["stage"] == "downloading" and r["stage_text"] == "下载中", f"stage=downloading（{r['stage_text']}）")
ok(abs(r["progress"] - 0.42) < 1e-9, "progress 0.42 透传")
ok(abs(r["left_gb"] - 5.8) < 0.01, f"剩余 = 10×(1-0.42)=5.8 GB（{r['left_gb']}）")
ok(abs(r["speed"] - 2 * 1024 ** 2) < 1, "速度透传")
ok(r["eta_s"] and 2900 < r["eta_s"] < 3000, f"ETA≈5.8GB/2MBps≈2969s（{r['eta_s']}）")
ok(r["site"] == "聆音" and r["free"] is True and r["in_qb"] is True, "站点/免费/在 qB 标记")

# ---------------------------------------------------------------- [2]/[3]/[4] 阶段
print("[2] 进行中：已下完待转「资源」")
f2 = Fake(pend={H2: {"title": "葫芦娃", "ts": 1.0}}, snap={H2: _qbt(progress=1.0, state="pausedUP")},
          ledger={H2: {"sub": "", "in_library": False}})
r2 = f2._ondemand_items()["inflight"][0]
ok(r2["stage"] == "pending_settle" and "待转" in r2["stage_text"], f"stage=pending_settle（{r2['stage_text']}）")

print("[3] 进行中：账本身份已是「资源」")
f3 = Fake(pend={H3: {"title": "x", "ts": 1.0}}, snap={H3: _qbt(progress=1.0, state="pausedUP")},
          ledger={H3: {"sub": SUB_RESOURCE, "in_library": True}})
r3 = f3._ondemand_items()["inflight"][0]
ok(r3["stage"] == "resource" and r3["stage_text"] == "已转「资源」", f"stage=resource（{r3['stage_text']}）")

print("[4] 进行中：不在 qB（不报错）")
f4 = Fake(pend={H4: {"title": "y", "ts": 1.0}}, snap={})
r4 = f4._ondemand_items()["inflight"][0]
ok(r4["stage"] == "gone" and r4["in_qb"] is False and r4["progress"] == 0.0, "stage=gone")

# ---------------------------------------------------------------- [5] 历史
print("[5] 历史：标题去前缀 + 结果现况回查")
f5 = Fake(
    pend={},
    snap={H1: _qbt(progress=1.0, state="pausedUP"), H2: _qbt(progress=0.3)},
    ledger={H1: {"sub": SUB_RESOURCE, "in_library": True, "site": "聆音", "identity_at": 1234.0},
            H2: {"sub": "", "in_library": False}},
    journal=[_op(H1, "点播 流浪地球", ts=2000.0), _op(H2, "点播 葫芦娃", ts=1000.0)],
)
data = f5._ondemand_items()
hist = {(h["hash"]): h for h in data["history"]}
ok(len(hist) == 2, "2 条历史")
ok(hist[H1]["title"] == "流浪地球", f"标题去「点播」前缀（{hist[H1]['title']}）")
ok(hist[H1]["result"] == "resource" and hist[H1]["result_text"] == "已转「资源」·已入库",
   f"结果=已转资源·已入库（{hist[H1]['result_text']}）")
ok(hist[H1]["in_library"] is True and abs(hist[H1]["settled_at"] - 1234.0) < 1e-9, "入库/结算时间回查")
ok(hist[H2]["result"] == "downloading" and hist[H2]["result_text"] == "下载中", "未下完 → 下载中")
ok(hist[H1]["ts"] == 2000.0 and abs(hist[H1]["size_gb"] - 3.0) < 1e-9, "点播时间/size 来自 journal")

print("[5.1] 历史：已移出下载器")
f5b = Fake(pend={}, snap={}, ledger={}, journal=[_op(H3, "点播 老片", ts=1.0)])
h3 = f5b._ondemand_items()["history"][0]
ok(h3["result"] == "gone" and h3["result_text"] == "已移出下载器", f"移出（{h3['result_text']}）")

print("[5.2] 历史：站点回填（账本优先 → reason 兜底）")
f5c = Fake(pend={}, snap={}, ledger={}, journal=[_op(H4, "点播 老片", ts=1.0, reason="源 财神·免费")])
ok(f5c._ondemand_items()["history"][0]["site"] == "财神", "账本无行 → 从 reason「源 财神·免费」回填")
f5d = Fake(pend={}, snap={}, ledger={H4: {"site": "聆音"}},
           journal=[_op(H4, "点播 老片", ts=1.0, reason="源 财神·免费")])
ok(f5d._ondemand_items()["history"][0]["site"] == "聆音", "账本有站 → 优先账本")

# ---------------------------------------------------------------- [6] 去重
print("[6] 与「进行中」同 hash 去重")
f6 = Fake(
    pend={H1: {"title": "流浪地球", "ts": 1.0}},
    snap={H1: _qbt(progress=0.1)},
    ledger={},
    journal=[_op(H1, "点播 流浪地球", ts=1000.0), _op(H2, "点播 别的", ts=500.0)],
)
d6 = f6._ondemand_items()
ok(len(d6["inflight"]) == 1 and [x["hash"] for x in d6["history"]] == [H2], "同 hash 只在进行中（不从历史重复出现）")

# ---------------------------------------------------------------- [7] totals
print("[7] totals 统计")
f7 = Fake(
    pend={H1: {"title": "a", "ts": 2.0}, H2: {"title": "b", "ts": 1.0}},
    snap={H1: _qbt(progress=0.5, size_gb=4.0), H2: _qbt(progress=1.0, size_gb=2.0)},
    ledger={H2: {"sub": SUB_RESOURCE}},
)
t = f7._ondemand_items()["totals"]
ok(t["inflight"] == 2 and t["downloading"] == 1, f"inflight=2 / downloading=1（{t}）")
ok(abs(t["left_gb"] - 2.0) < 0.01, f"left_gb = 4×0.5 = 2.0（{t['left_gb']}）")

# ---------------------------------------------------------------- [8] limit
print("[8] limit 上限（>200 截到 200）")
recs = [_op(f"{i:040x}"[:40], f"点播 片{i}", ts=float(i)) for i in range(300)]
f8 = Fake(pend={}, snap={}, ledger={}, journal=recs)
d8 = f8._ondemand_items(limit=999)
ok(len(d8["history"]) == 200, f"截到 200（{len(d8['history'])}）")
d8b = f8._ondemand_items(limit=5)
ok(len(d8b["history"]) == 5, f"limit=5 生效（{len(d8b['history'])}）")

# ---------------------------------------------------------------- 汇总
print()
if FAILS:
    print(f"❌ FAIL：{len(FAILS)}/{N} 断言失败")
    for x in FAILS:
        print("   -", x)
    sys.exit(1)
print(f"✅ PASS：{N}/{N} 断言全过")
