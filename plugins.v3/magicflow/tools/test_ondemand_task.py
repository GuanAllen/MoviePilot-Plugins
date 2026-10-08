#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播伪任务（★ 15.8.4）离线回归 —— 真跑 features/ondemand.py + tags.py，不需 MoviePilot / qB。

背景（Master 2026-10-08 18:40 拍板 B 方案）：
  点播在途的种（``ondemand_pending``）账本 ``task_id`` 天生为空 ⇒ 账本 ``state=静默`` ⇒
  没下完就被静默池的**清理闸**（``_silent_purge_incomplete``）当「静默半成品」删掉
  （实锤：2026-10-08 17:31:41 删掉 SEED / SEED Freedom / 鬼灭 S05 三颗）。

  15.8.3 只给**暂停闸**（``_silent_audit``）加了 ``_od_inflight`` 过滤，漏了清理闸。

  15.8.4 = 把「点播在途」挂成**真伪任务** ``__ondemand__``（仿 ``__crossseed__`` / ``__hr_host__``）：
    · 加种即 ``_od_assign`` → 贴职务标签 ``魔流-<站>-点播`` + 账本 ``taken_by=__ondemand__``、``task=点播``；
    · 账本 ``state=点播`` ≠ 静默 ⇒ **暂停闸 + 清理闸两条路一起天然免疫**；
    · 结算转资源即 ``_od_release`` → 退职务、回静默闸管辖。

断言：
  [1] tags.py：STATE_ONDEMAND 存在、进 STATES/DUTY_STATES、retag 出「点播」职务标签；
  [2] _od_assign：贴标签 + 写账本（state=点播 / taken_by=__ondemand__ / task=点播）；幂等；
  [3] _od_release：退标签回「静默-资源」+ 清账本占用 + 触发静默暂停闸；
  [4] _ondemand_duty_reconcile：pending 未挂→补挂；挂了但已不 pending→释放；
  [5] 服务端接线：_ondemand_download 调 _od_assign；_ondemand_settle 调 reconcile + release；
  [6] 真值源锚点：common.py 常量、ledger.py 的 _task_state/_task_name/_task_id、agentledger 状态枚举；
  [7] 静默两闸都以 state==静默 为前提（点播 state≠静默 ⇒ 免疫）；
  [8] ★ 15.8.5：删除闸门的「库内资产」硬拦豁免「在途点播」（state=点播 / taken_by=__ondemand__）——
      否则 ``_od_assign`` 打的 ``sub=资源`` 会让「点播移除」被自己硬拦（死结）；结算后仍照常保护；
  [9] ★ 15.8.6：_od_assign 幂等改为「账本已挂 **且** qB 职务标签在位」；对账把
      「账本挂了但标签缺」（加种抢先于 qB 登记）也纳入补挂。

用法：``python3 tools/test_ondemand_task.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_ondemand_task_test"


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
STATE_SILENT = tags.STATE_SILENT
STATE_ONDEMAND = tags.STATE_ONDEMAND
SUB_RESOURCE = tags.SUB_RESOURCE

# 桩：app.schemas.Response
_app = types.ModuleType("app")
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = type("Response", (), {})
sys.modules.setdefault("app", _app)
sys.modules["app.schemas"] = _app_schemas

# 桩：..recommend / ..sitestore
_rec = types.ModuleType(PKG + ".recommend")
_rec.recognize = lambda *a, **k: None
sys.modules[PKG + ".recommend"] = _rec
_site = types.ModuleType(PKG + ".sitestore")
_site.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
sys.modules[PKG + ".sitestore"] = _site

# 桩：..common（只暴露 15.8.4 用到的新常量；真 common.py 依赖 app.* 无法离线加载）
_common = types.ModuleType(PKG + ".common")
_common.ONDEMAND_TASK_ID = "__ondemand__"
_common.ONDEMAND_TASK_NAME = "点播"
# [8] 删除闸门（deletegate）离线所需的最小桩：
_common.begin_decision_round = lambda *a, **k: None
_common.note_snapshot_pull = lambda *a, **k: 0
_common.DELETE_BREAKER_ENABLED = True
_common.DELETE_BREAKER_MAX = 30
_common.DELETE_BREAKER_WINDOW_S = 600.0
_common.DELETE_BILL_ASSERT = True
_common.hr_incomplete = lambda *a, **k: False
_common.hr_complete_ratio_of = lambda *a, **k: 1.0
sys.modules[PKG + ".common"] = _common

# 真 persistence.py（stdlib，提供 OperationItem）
_load(PKG + ".persistence", "persistence.py")

ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")
OnDemandMixin = ondemand.OnDemandMixin

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


H1 = "a" * 40
H2 = "b" * 40
H3 = "c" * 40
SITE = "红豆饭"


class _Store:
    def __init__(self, d=None):
        self._d = {str(k).lower(): dict(v) for k, v in (d or {}).items()}

    def get(self, h):
        return self._d.get(str(h or "").lower())

    def items(self):
        return {k: dict(v) for k, v in self._d.items()}

    def put(self, h, patch):
        hh = str(h or "").lower()
        rec = self._d.setdefault(hh, {})
        for k, v in (patch or {}).items():
            if v is not None:
                rec[k] = v
        return rec


class _DL:
    is_available = True

    def __init__(self, snap=None):
        self.calls = []
        self.snap = snap

    def replace_torrent_tags(self, h, new):
        self.calls.append((str(h).lower(), list(new)))
        # 回写快照，模拟 qB 真的改了标签（否则幂等判定看不到第一次的结果）
        if self.snap is not None:
            hh = str(h).lower()
            t = self.snap.get(hh)
            if t is not None:
                t.tags = list(new)
        return True


class Fake(OnDemandMixin):
    def __init__(self, pend=None, snap=None, ledger=None):
        self._pend = dict(pend or {})
        self._snap = dict(snap or {})
        self._store = _Store(ledger)
        self._dl = _DL(self._snap)
        self.logs = []
        self.gate = None

    def _ondemand_all(self):
        return dict(self._pend)

    def _tag_all_torrents(self):
        return dict(self._snap)

    def _tag_state(self):
        return self._store

    def _get_downloader(self):
        return self._dl

    def _torrent_site_name(self, cur_tags=None, default=""):
        return SITE

    def _log(self, msg, level="info"):
        self.logs.append(str(msg))

    def _silent_pause_gate(self, hashes):
        self.gate = [str(h or "").lower() for h in (hashes or [])]


def _bt(tags_list, title="咒术回战 S02"):
    return SimpleNamespace(tags=list(tags_list), title=title, progress=0.1)


# ---------------------------------------------------------------- [1] tags 常量/retag
print("[1] tags.py：STATE_ONDEMAND 常量 + retag 出「点播」职务")
ok(STATE_ONDEMAND == "点播", "STATE_ONDEMAND == 点播")
ok(STATE_ONDEMAND in tags.STATES, "点播 ∈ STATES")
ok(STATE_ONDEMAND in tags.DUTY_STATES, "点播 ∈ DUTY_STATES（职务轴）")
ok(STATE_ONDEMAND not in tags.STATES_WITH_SUB, "点播 ∉ STATES_WITH_SUB（不当身份，别冲掉 sub）")
_rt = tags.retag(["魔流-红豆饭-静默-资源"], site=SITE, state=STATE_ONDEMAND, sub=SUB_RESOURCE)
ok(tags.tag_for(SITE, STATE_ONDEMAND) in _rt, f"retag 出职务标签 {tags.tag_for(SITE, STATE_ONDEMAND)}")
ok(tags.tag_for(SITE, STATE_SILENT, SUB_RESOURCE) in _rt, "retag 保留身份标签 魔流-红豆饭-静默-资源")

# ---------------------------------------------------------------- [2] _od_assign
print("[2] _od_assign：贴标签 + 写账本（state=点播 / taken_by=__ondemand__）")
f = Fake(pend={H1: {"title": "咒术回战", "site": SITE, "ts": 1.0}},
         snap={H1: _bt(["魔流-红豆饭-静默-资源"])})
n = f._od_assign([H1], site=SITE, sub=SUB_RESOURCE, reason="加种")
ok(n == 1, f"_od_assign 返回 1（{n}）")
_t = f._dl.calls[-1][1] if f._dl.calls else []
ok(tags.tag_for(SITE, STATE_ONDEMAND) in _t, "贴了 魔流-红豆饭-点播")
ok(tags.tag_for(SITE, STATE_SILENT, SUB_RESOURCE) in _t, "保留 魔流-红豆饭-静默-资源")
_r = f._store.get(H1)
ok(_r and _r.get("state") == STATE_ONDEMAND, f"账本 state=点播（{_r.get('state') if _r else None}）")
ok(_r and _r.get("taken_by") == "__ondemand__", "账本 taken_by=__ondemand__")
ok(_r and _r.get("task") == "点播", "账本 task=点播")
ok(_r and _r.get("sub") == SUB_RESOURCE, "账本 sub 未被冲掉（=资源）")
ok(not f.gate, "挂载时不触发静默暂停闸（不 pause 正在下的种）")

print("[2b] _od_assign 幂等：已挂的不重复贴")
_before = len(f._dl.calls)
n2 = f._od_assign([H1], site=SITE, sub=SUB_RESOURCE)
ok(n2 == 0 and len(f._dl.calls) == _before, "重复 _od_assign 不动手")

# ---------------------------------------------------------------- [3] _od_release
print("[3] _od_release：退标签 + 清账本 + 触发静默暂停闸")
f._snap[H1] = _bt(["魔流-红豆饭-静默-资源", tags.tag_for(SITE, STATE_ONDEMAND)])
nr = f._od_release([H1], reason="结算转资源")
ok(nr == 1, f"_od_release 返回 1（{nr}）")
_t2 = f._dl.calls[-1][1]
ok(tags.tag_for(SITE, STATE_ONDEMAND) not in _t2, "摘掉 魔流-红豆饭-点播")
ok(tags.tag_for(SITE, STATE_SILENT, SUB_RESOURCE) in _t2, "回 魔流-红豆饭-静默-资源")
_r2 = f._store.get(H1)
ok(_r2.get("state") == STATE_SILENT, f"账本 state=静默（{_r2.get('state')}）")
ok(_r2.get("taken_by") == "" and _r2.get("task") == "", "账本占用已清（taken_by/task 空）")
ok(f.gate == [H1], f"释放后触发静默暂停闸（{f.gate}）")

# ---------------------------------------------------------------- [4] reconcile
print("[4] _ondemand_duty_reconcile：补挂漏的 / 释放已结算的")
f2 = Fake(pend={H1: {"title": "x", "site": SITE}},
          snap={H1: _bt(["魔流-红豆饭-静默-资源"]), H2: _bt(["魔流-红豆饭-静默-资源"])},
          ledger={H2: {"state": STATE_ONDEMAND, "taken_by": "__ondemand__", "sub": SUB_RESOURCE}})
rc = f2._ondemand_duty_reconcile()
ok(rc.get("assigned") == 1, f"pending 未挂→补挂 1（{rc}）")
ok(rc.get("released") == 1, f"挂了但不 pending→释放 1（{rc}）")
ok(f2._store.get(H1).get("taken_by") == "__ondemand__", "H1 补挂成功")
ok(f2._store.get(H2).get("taken_by") == "", "H2 已释放")

# ---------------------------------------------------------------- [5] 服务端接线
print("[5] 服务端接线：download→assign / settle→reconcile+release")
_src = (ROOT / "features" / "ondemand.py").read_text()
ok("self._od_assign([h], site=site_name" in _src, "_ondemand_download 调 _od_assign")
ok("_rc = self._ondemand_duty_reconcile()" in _src, "_ondemand_settle 调 _ondemand_duty_reconcile")
ok('self._od_release([h], reason="结算转资源")' in _src, "_ondemand_settle 调 _od_release")

# ---------------------------------------------------------------- [6] 真值源锚点
print("[6] 真值源锚点：common / ledger / agentledger")
_c = (ROOT / "common.py").read_text()
ok('ONDEMAND_TASK_ID = "__ondemand__"' in _c, "common.py ONDEMAND_TASK_ID 常量")
_l = (ROOT / "ledger.py").read_text()
ok("if tid == ONDEMAND_TASK_ID:\n            return STATE_ONDEMAND" in _l or
   "return STATE_ONDEMAND" in _l, "ledger._task_state 特判 __ondemand__→点播")
ok("return ONDEMAND_TASK_NAME" in _l, "ledger._task_name 特判 __ondemand__→点播")
ok('if key in ("__ondemand__", "ondemand", "点播", "点播下载"):' in _l, "ledger._task_id 反查 __ondemand__")
_al = (ROOT / "features" / "agentledger.py").read_text()
ok('"点播"' in _al and '"保种", "点播"' in _al, "agentledger state 枚举含 点播")

# ---------------------------------------------------------------- [7] 静默两闸以 state==静默 为前提
print("[7] 静默两闸：都以 rec.state==静默 为前提 → 点播(非静默)天然免疫")
_sl = (ROOT / "features" / "silent.py").read_text()
ok("STATE_SILENT" in _sl and "_silent_purge_incomplete" in _sl, "silent.py 有 _silent_purge_incomplete")
_tg = (ROOT / "features" / "tags.py").read_text()
ok("_silent_drop_incomplete_now" in _tg, "tags.py 有 _silent_drop_incomplete_now")

# ---------------------------------------------------------------- [8] 删除闸门：在途点播不算「库内资产」
print("[8] 删除闸门：在途点播(state=点播)豁免「库内资产」硬拦 → 点播移除不被自己卡死")
_dg = _load(PKG + ".features.deletegate", "features/deletegate.py")


class GateFake(Fake):
    def _crossseed_source_hashes(self):
        return set()

    def _claim_protected_hashes(self, site_id=None):
        return set()

    def _resource_source_index(self):
        return {}

    def _hr_obligation(self, *a, **k):
        return (False, 0.0, 0.0, "")

    def _tag_groups(self):
        return SimpleNamespace(group_of=lambda h: "", items=lambda: {})

    _delete_gate_detail = _dg.DeleteGateMixin._delete_gate_detail


g = GateFake(ledger={
    H1: {"state": STATE_ONDEMAND, "taken_by": "__ondemand__", "sub": SUB_RESOURCE},
    H2: {"state": STATE_SILENT, "sub": SUB_RESOURCE},
    H3: {"state": STATE_SILENT, "taken_by": "任务A", "sub": ""},
})
_why = g._delete_gate_detail([H1, H2, H3])
ok(H1 not in _why, "在途点播(state=点播) 不再被「库内资产」硬拦")
ok(_why.get(H2) == "库内资产（已入库，永不删）", "已结算资源(静默-资源) 仍受库内资产硬保护")
ok(H3 not in _why, "普通静默种(非资源) 不误伤")

_src_g = (ROOT / "features" / "deletegate.py").read_text()
ok("== STATE_ONDEMAND" in _src_g and "== ONDEMAND_TASK_ID" in _src_g,
   "deletegate 源码含 在途点播豁免（STATE_ONDEMAND / ONDEMAND_TASK_ID）")

# ---------------------------------------------------------------- [9] 加种抢跑：缺标签补挂
print("[9] ★ 15.8.6：账本已挂但 qB 缺「点播」职务标签 → 补挂（治加种抢先于 qB 登记）")
_PEND = {H1: {"title": "x", "site": SITE}}
_LED = {H1: {"state": STATE_ONDEMAND, "taken_by": "__ondemand__", "site": SITE,
             "sub": SUB_RESOURCE}}
f3 = Fake(pend=dict(_PEND), snap={H1: _bt(["魔流-红豆饭-静默-资源"])}, ledger=dict(_LED))
n3 = f3._od_assign([H1], site=SITE, sub=SUB_RESOURCE, reason="补挂")
ok(n3 == 1, f"账本已挂但标签缺 → 补挂（返回 {n3}）")
_t3 = f3._dl.calls[-1][1]
ok(tags.tag_for(SITE, STATE_ONDEMAND) in _t3, "补上了 魔流-红豆饭-点播")

f4 = Fake(pend=dict(_PEND),
          snap={H1: _bt(["魔流-红豆饭-静默-资源", tags.tag_for(SITE, STATE_ONDEMAND)])},
          ledger=dict(_LED))
_b4 = len(f4._dl.calls)
n4 = f4._od_assign([H1], site=SITE, sub=SUB_RESOURCE)
ok(n4 == 0 and len(f4._dl.calls) == _b4, "标签已在位 → 幂等不动作")

f5 = Fake(pend=dict(_PEND), snap={H1: _bt(["魔流-红豆饭-静默-资源"])}, ledger=dict(_LED))
rc5 = f5._ondemand_duty_reconcile()
ok(rc5.get("assigned") == 1, f"reconcile 把「账本挂了但标签缺」纳入补挂（{rc5}）")

print()
if FAILS:
    print(f"❌ FAIL：{len(FAILS)}/{N} 断言未过")
    for x in FAILS:
        print(f"   - {x}")
    sys.exit(1)
print(f"✅ PASS：{N}/{N} 断言全过")
