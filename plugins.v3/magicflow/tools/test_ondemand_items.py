#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播干净清单（15.9.0 单列表换皮 + 17.1.0 落盘记录）离线回归 —— 真跑 features/ondemand.py。

背景：
  · 15.9.0（Master 2026-10-10）：单列表 items[]（进行中+历史同构）+ totals；
  · 17.1.0（Master 2026-10-13「没必要动态，做个记录就好」）：历史改为**落盘记录**
    （ondemand_history 槽；点播时写、结算/撤单时更新）—— 不再动态拼 journal + 现况回查。

真值源：
  · 进行中 = ondemand_pending（mf_seed.pending）× qB 快照（progress/state/dl_speed）；
  · 历史   = ondemand_history 槽（落盘记录；stage ∈ downloading/resource/gone/removed）。

用法：python3 tools/test_ondemand_items.py（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_ondemand_test"


def _pkg(name, path):
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

tags = _load(PKG + ".tags", "tags.py")

# 桩：app.schemas.Response + app.sdk.logging.logger
_app = types.ModuleType("app")
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = type("Response", (), {})
sys.modules.setdefault("app", _app)
sys.modules["app.schemas"] = _app_schemas

_app_sdk = types.ModuleType("app.sdk")
_app_sdk_logging = types.ModuleType("app.sdk.logging")


class _Logger:
    def __getattr__(self, _n):
        return lambda *a, **k: None


_app_sdk_logging.logger = _Logger()
sys.modules.setdefault("app.sdk", _app_sdk)
sys.modules["app.sdk.logging"] = _app_sdk_logging

# 桩：..recommend（只用 recognize）+ ..sitestore（只用 slot_callbacks，内存槽）
_rec = types.ModuleType(PKG + ".recommend")
_rec.recognize = lambda *a, **k: None
sys.modules[PKG + ".recommend"] = _rec

_SLOTS = {}


def _slot_cbs(_plugin, slot):
    def _get(*a, **k):
        return dict(_SLOTS.get(slot) or {})
    def _save(*a, **k):
        val = k.get("value")
        if val is None and len(a) > 1:
            val = a[1]
        _SLOTS[slot] = val
    return _get, _save


_site = types.ModuleType(PKG + ".sitestore")
_site.slot_callbacks = _slot_cbs
sys.modules[PKG + ".sitestore"] = _site

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
        print("  x " + label)
    else:
        print("  v " + label)


class Fake(OnDemandMixin):
    def __init__(self, pend=None, snap=None, ledger=None, hist=None, downloader=None):
        self._pend = dict(pend or {})
        self._snap = dict(snap or {})
        self._ledger = dict(ledger or {})
        self._dl = downloader
        _SLOTS["ondemand_pending"] = dict(self._pend)
        _SLOTS["ondemand_history"] = {"seeded": True, "rows": list(hist or [])}

    def _ondemand_all(self):
        return dict(_SLOTS.get("ondemand_pending") or {})

    def _tag_all_torrents(self):
        return dict(self._snap)

    def _tag_state(self):
        return _Ledger(self._ledger)

    def _get_downloader(self, kind="qbittorrent"):
        return self._dl

    def _ondemand_unmark(self, h):
        rows = dict(_SLOTS.get("ondemand_pending") or {})
        rows.pop(str(h or "").lower(), None)
        _SLOTS["ondemand_pending"] = rows

    def _log(self, *a, **k):
        pass


class _Ledger:
    def __init__(self, d):
        self._d = d

    def get(self, h):
        return self._d.get(str(h or "").lower())


def _qbt(progress=0.0, state="downloading", size_gb=10.0, speed=0.0, ratio=0.0, tags=None):
    return SimpleNamespace(progress=progress, state=state, size_gb=size_gb,
                           download_speed=speed, ratio=ratio, save_path="/downloads",
                           tags=list(tags or []))


def _rec(h, title, stage="resource", ts=1000.0, site="财神", size_gb=3.0, inlib=True):
    return {"hash": h, "title": title, "stage": stage, "added_at": ts, "site": site,
            "size_gb": size_gb, "in_library": inlib, "free": False, "hit_and_run": False,
            "year": "", "site_id": 0, "settled_at": ts if stage == "resource" else 0.0,
            "source_note": "源 " + site}


def _rows(f, limit=50):
    return f._ondemand_items(limit=limit)["items"]


def _by_stage(f, stage, limit=50):
    return [r for r in _rows(f, limit=limit) if r["stage"] == stage]


def _iso_ts(s):
    try:
        return datetime.fromisoformat(str(s)).timestamp()
    except Exception:
        return None


H1 = "a" * 40
H2 = "b" * 40
H3 = "c" * 40
H4 = "d" * 40

FIELDS = (
    "hash", "module", "stage", "stage_text", "title", "year", "site", "progress", "percent",
    "size_gb", "downloaded_gb", "left_gb", "speed", "eta_s", "ratio", "free", "hit_and_run",
    "in_qb", "in_library", "save_path", "added_at", "settled_at", "source_note",
)

# ---------------------------------------------------------------- [1] 下载中
print("[1] 进行中：下载中（progress/percent/剩余/速度/ETA/downloaded）")
f = Fake(pend={H1: {"title": "流浪地球", "year": "2019", "site": "聆音", "free": True, "ts": 1000.0}},
         snap={H1: _qbt(progress=0.42, size_gb=10.0, speed=2 * 1024 ** 2)})
rows = _rows(f)
ok(len(rows) == 1, "单列表 1 条")
r = rows[0]
ok(all(k in r for k in FIELDS), "进行中行含全部约定字段")
ok(r["module"] == "ondemand", "module=ondemand")
ok(r["stage"] == "downloading" and r["stage_text"] == "下载中", "stage=downloading")
ok(abs(r["progress"] - 0.42) < 1e-9 and abs(r["percent"] - 42.0) < 1e-6, "progress/percent")
ok(abs(r["left_gb"] - 5.8) < 0.01 and abs(r["downloaded_gb"] - 4.2) < 0.01, "剩余/已下 = 5.8 / 4.2 GB")
ok(abs(r["speed"] - 2 * 1024 ** 2) < 1, "速度透传")
ok(r["eta_s"] and 2900 < r["eta_s"] < 3000, "ETA≈2969s")
ok(r["site"] == "聆音" and r["free"] is True and r["in_qb"] is True, "站点/免费/在 qB")
ok(_iso_ts(r["added_at"]) is not None and r["settled_at"] is None, "added_at ISO / settled_at None")

# ---------------------------------------------------------------- [2]/[3]/[4] 阶段
print("[2] 进行中：已下完待转「资源」")
f2 = Fake(pend={H2: {"title": "葫芦娃", "ts": 1.0}}, snap={H2: _qbt(progress=1.0, state="pausedUP")},
          ledger={H2: {"sub": "", "in_library": False}})
r2 = _by_stage(f2, "settling")[0]
ok(r2["stage"] == "settling" and "待转" in r2["stage_text"], "stage=settling")

print("[3] 进行中：账本身份已是「资源」")
f3 = Fake(pend={H3: {"title": "x", "ts": 1.0}}, snap={H3: _qbt(progress=1.0, state="pausedUP")},
          ledger={H3: {"sub": SUB_RESOURCE, "in_library": True}})
r3 = _by_stage(f3, "resource")[0]
ok(r3["stage"] == "resource" and r3["stage_text"] == "已转「资源」", "stage=resource")
ok(r3["in_library"] is True, "in_library 回查（进行中）")

print("[4] 进行中：不在 qB（不报错）")
f4 = Fake(pend={H4: {"title": "y", "ts": 1.0}}, snap={})
r4 = _by_stage(f4, "gone")[0]
ok(r4["stage"] == "gone" and r4["in_qb"] is False and r4["progress"] == 0.0, "stage=gone")

# ---------------------------------------------------------------- [5] 历史（落盘记录）
print("[5] 历史 = 落盘记录（不拼 journal、不回查）")
f5 = Fake(hist=[_rec(H1, "流浪地球", ts=2000.0), _rec(H2, "葫芦娃", stage="gone", ts=1000.0, inlib=False)])
items5 = _rows(f5)
byh = {r["hash"]: r for r in items5}
ok(len(byh) == 2, "2 条历史")
ok(all(k in byh[H1] for k in FIELDS), "历史行含全部约定字段")
ok(byh[H1]["title"] == "流浪地球", "标题 = 记录")
ok(byh[H1]["stage"] == "resource" and byh[H1]["stage_text"] == "已转「资源」·已入库", "resource·已入库")
ok(byh[H2]["stage"] == "gone" and byh[H2]["stage_text"] == "已结案", "未转资源 → 已结案")
ok(all(x["stage"] != "downloading" for x in items5), "历史行绝不 downloading（进行中只认 pending）")
ok(abs((_iso_ts(byh[H1]["added_at"]) or 0) - 2000.0) < 1.0, "added_at ISO（来自记录）")
ok(byh[H1]["size_gb"] == 3.0, "size 来自记录")
ok(byh[H1]["source_note"] == "源 财神", "source_note 来自记录")

print("[5.1] 历史行不看 qB 现况（记录说啥就啥）")
f5b = Fake(snap={H1: _qbt(progress=0.157, state="pausedDL", size_gb=58.6)},
           hist=[_rec(H1, "高达00", stage="gone", ts=1000.0, size_gb=58.6)])
h_ = _rows(f5b)[0]
ok(h_["stage"] == "gone" and h_["in_qb"] is False and h_["percent"] == 0.0, "qB 挂着未完成也不回「下载中」")

print("[5.2] 撤单（removed）→ 点播窗口不展示")
f5c = Fake(hist=[_rec(H1, "高达00", stage="removed", ts=1000.0)])
ok(_rows(f5c) == [], "removed 记录被剔除")

print("[5.3] 写/更新记录（put / update，真值源）")
f5d = Fake()
f5d._ondemand_history_put(H3, {"title": "新片", "stage": "downloading", "added_at": 500.0})
rr = _SLOTS["ondemand_history"]["rows"]
ok(len(rr) == 1 and rr[0]["hash"] == H3 and rr[0]["stage"] == "downloading", "put 落一条")
f5d._ondemand_history_update(H3, stage="resource", settled_at=600.0, in_library=True)
rr = _SLOTS["ondemand_history"]["rows"]
ok(rr[0]["stage"] == "resource" and rr[0]["in_library"] is True, "update 改 stage/in_library")
r3b = _rows(f5d)[0]
ok(r3b["hash"] == H3 and r3b["stage"] == "resource"
   and abs((_iso_ts(r3b["settled_at"]) or 0) - 600.0) < 1.0, "读回落盘记录")

print("[5.4] 一次性迁移：槽空 + journal 有点播 → 灌成落盘记录（只跑一次）")


class _J:
    def __init__(self, recs):
        self._recs = list(recs)

    def list_recent(self, limit=100, kind=None):
        return self._recs[:limit]


def _op(h, title, ts=1000.0, reason="源 财神·免费", size_gb=3.0):
    return SimpleNamespace(operation_id=h[:8], created_at=ts,
                           items=[SimpleNamespace(hash=h, title=title, reason=reason,
                                                  source="ondemand", size_gb=size_gb)])


fB = Fake(ledger={H1: {"sub": SUB_RESOURCE, "in_library": True}, H2: {"sub": "", "in_library": False}})
fB._store = SimpleNamespace(journal=_J([_op(H1, "点播 流浪地球", ts=2000.0), _op(H2, "点播 葫芦娃", ts=1000.0)]))
_SLOTS["ondemand_history"] = {"rows": []}   # 无 seeded → 触发迁移
rb = {r["hash"]: r for r in _rows(fB)}
ok(len(rb) == 2, "迁移出 2 条记录")
ok(rb[H1]["stage"] == "resource" and rb[H1]["title"] == "流浪地球", "resource + 去「点播」前缀")
ok(rb[H2]["stage"] == "gone", "未转资源 → 已结案")
ok(_SLOTS["ondemand_history"].get("seeded") is True, "写回置 seeded")
ok(len(_rows(fB)) == 2, "再读不重复灌")

# ---------------------------------------------------------------- [6] 去重
print("[6] 与「进行中」同 hash 去重")
f6 = Fake(pend={H1: {"title": "流浪地球", "ts": 1.0}}, snap={H1: _qbt(progress=0.1)},
          hist=[_rec(H1, "流浪地球", ts=1000.0), _rec(H2, "别的", ts=500.0)])
d6 = _rows(f6)
hashes = [x["hash"] for x in d6]
ok(len(hashes) == 2 and hashes.count(H1) == 1 and H2 in hashes, "H1 只出现一次")

# ---------------------------------------------------------------- [7] totals
print("[7] totals 统计")
f7 = Fake(pend={H1: {"title": "a", "ts": 2.0}, H2: {"title": "b", "ts": 1.0}},
          snap={H1: _qbt(progress=0.5, size_gb=4.0), H2: _qbt(progress=1.0, size_gb=2.0)},
          ledger={H2: {"sub": SUB_RESOURCE}})
t = f7._ondemand_items()["totals"]
ok(t["count"] == 2 and t["downloading"] == 1 and t["resource"] == 1, "count/downloading/resource")
ok(abs(t["left_gb"] - 2.0) < 0.01, "left_gb = 4x0.5 = 2.0")

# ---------------------------------------------------------------- [8] limit
print("[8] limit 上限（>200 截到 200）")
recs = [_rec(("%040x" % i)[:40], "片%d" % i, ts=float(i)) for i in range(300)]
f8 = Fake(hist=recs)
d8 = _rows(f8, limit=999)
ok(len(d8) == 200, "截到 200")
d8b = _rows(f8, limit=5)
ok(len(d8b) == 5, "limit=5 生效")

# ---------------------------------------------------------------- [9] 回执统一
print("[9] _ondemand_act 回执恒 5 键")
for rep in (
    f._ondemand_act(hash="", action="pause"),
    f._ondemand_act(hash=H1, action="bogus"),
    f._ondemand_act(hash="f" * 40, action="pause"),
    f._ondemand_act(hash=H1, action="pause"),
):
    ok(set(rep) == {"ok", "hash", "action", "message", "blocked"}, "5 键齐全")


class _DL:
    is_available = True

    def pause_torrents(self, hashes):
        return len(hashes), None

    def delete_torrents(self, hashes=None, delete_file=False, reason="", source=""):
        return 0, "被删除闸门拦下（欠 H&R）"


f9 = Fake(pend={H1: {"title": "x", "ts": 1.0}}, downloader=_DL())
rep_ok = f9._ondemand_act(hash=H1, action="pause")
ok(rep_ok["ok"] is True and rep_ok["action"] == "pause" and rep_ok["blocked"] is False, "pause 成功回执")
rep_blk = f9._ondemand_act(hash=H1, action="remove")
ok(rep_blk["ok"] is False and rep_blk["blocked"] is True and rep_blk["action"] == "remove", "remove 被拦 → blocked")

print()
if FAILS:
    print("FAIL: %d/%d 断言失败" % (len(FAILS), N))
    for x in FAILS:
        print("   -", x)
    sys.exit(1)
print("PASS: %d/%d 断言全过" % (N, N))
