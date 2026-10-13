#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · AI 计划审批（★ 15.17.0）离线回归 —— 真跑 `features/plan.py`，不需 MoviePilot / 网络 / 下载器。

审批的本质是「**人批准的是他看到的那个计划**」，所以凭据不是时间戳而是**内容哈希**
（``plan_id``）：池内状态一变，重新生成的哈希就变，旧批准自动作废。

断言：
  [1] `_plan_id` 稳定：逐条顺序无关（排序后取哈希）；
  [2] `_plan_id` 敏感：体积变 / 增删条目 / 换预算 → 哈希必变；
  [3] apply 无 plan_id → bad_param；
  [4] apply plan_id 不匹配 → plan_stale（**且绝不调删除**）；
  [5] apply 匹配 + confirm=0 → 干跑（dry_run=true，零删除）；
  [6] apply 匹配 + confirm=1 → 只删闸门放行的 hash，被拦的如实回报；
  [7] delete_files：-1 取任务配置；1 强制删文件（透传到唯一删种出口）。

用法：``python3 tools/test_plan.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_plan_test"

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


def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")
plan_mod = _load(PKG + ".features.plan", "features/plan.py")
PlanMixin = plan_mod.PlanMixin

HA, HB = "a" * 40, "b" * 40
GATE_BLOCK = {HB: "库内资产（已入库，永不删）"}


class FakeTask:
    name = "测试任务"
    task_type = "bonus"
    site_id = 4
    downloader = None
    delete_files = False


class FakeDL:
    is_available = True

    def __init__(self):
        self.calls = []

    def delete_torrents(self, hashes, delete_file, reason=None, source=None):
        self.calls.append({"hashes": list(hashes), "delete_file": delete_file,
                           "reason": reason, "source": source})
        return len(list(hashes)), ""


class Harness(PlanMixin):
    def __init__(self, plan):
        self._plan = plan
        self.dl = FakeDL()

    # --- agentapi 信封（真实现需 MoviePilot）---
    def _agent_now(self):
        return "2026-10-12T07:30:00+08:00"

    def _agent_meta(self, t0):
        return {"elapsed_ms": 0}

    def _agent_ok(self, data, t0):
        return {"ok": True, "code": "ok", "message": "", "data": data, "meta": self._agent_meta(t0)}

    def _agent_err(self, code, message, t0=None, field=None, trace_id=None, data=None):
        if data is None and (field is not None or trace_id is not None):
            data = {}
            if field is not None:
                data["field"] = field
            if trace_id is not None:
                data["trace_id"] = trace_id
        return {"ok": False, "code": code, "message": message, "data": data,
                "meta": self._agent_meta(t0)}

    # --- 被测依赖（真实现读 qB/账本）---
    def _plan_build(self, action, task_id, budget_gb=""):
        return dict(self._plan), ""

    def _get_task_config(self, tid):
        return FakeTask()

    def _get_downloader(self, name=None):
        return self.dl

    def _delete_gate_detail(self, hashes, snap=None):
        return {h: GATE_BLOCK[h] for h in hashes if h in GATE_BLOCK}


def _plan(items, action="cleanup", tid="t1", budget=""):
    return {"plan_id": PlanMixin._plan_id(action, tid, budget, items),
            "action": action, "task_id": tid, "items": items}


ITEMS = [
    {"hash": HA, "op": "delete", "size_gb": 1.0},
    {"hash": HB, "op": "delete", "size_gb": 2.0},
]
PID = PlanMixin._plan_id("cleanup", "t1", "", ITEMS)

print("── 1) _plan_id 稳定性 ──")
ok(PlanMixin._plan_id("cleanup", "t1", "", list(reversed(ITEMS))) == PID,
   "顺序无关：颠倒条目哈希不变")
ok(PlanMixin._plan_id("cleanup", "t1", "", ITEMS).__len__() == 12, "长度 12 位")

print("── 2) _plan_id 敏感性 ──")
ok(PlanMixin._plan_id("cleanup", "t1", "", ITEMS[:1]) != PID, "少一条 → 变")
_alt = [dict(ITEMS[0], size_gb=1.5), ITEMS[1]]
ok(PlanMixin._plan_id("cleanup", "t1", "", _alt) != PID, "体积变 → 变")
ok(PlanMixin._plan_id("cleanup", "t2", "", ITEMS) != PID, "换任务 → 变")
ok(PlanMixin._plan_id("optimize", "t1", "", ITEMS) != PID, "换动作 → 变")
ok(PlanMixin._plan_id("optimize", "t1", "50", ITEMS) != PlanMixin._plan_id("optimize", "t1", "", ITEMS),
   "换预算 → 变")

print("── 3) apply：参数校验 ──")
h = Harness(_plan(ITEMS))
r = h.agent_plan_apply(plan_id="", action="cleanup", task_id="t1")
ok(r["ok"] is False and r["code"] == "bad_param", "缺 plan_id → bad_param")
ok(not h.dl.calls, "校验失败不调删除")

print("── 4) apply：计划过期 ──")
h = Harness(_plan(ITEMS))
r = h.agent_plan_apply(plan_id="deadbeef0000", action="cleanup", task_id="t1", confirm=1)
ok(r["ok"] is False and r["code"] == "plan_stale", "哈希不符 → plan_stale")
ok(r["data"].get("current") == PID and "field" not in (r["data"] or {}), "回报当前哈希")
ok(not h.dl.calls, "过期绝不调删除")

print("── 5) apply：干跑（confirm=0）──")
h = Harness(_plan(ITEMS))
r = h.agent_plan_apply(plan_id=PID, action="cleanup", task_id="t1")
ok(r["ok"] is True and r["data"]["dry_run"] is True, "confirm!=1 → dry_run")
ok(r["data"]["would_delete"] == 2, "would_delete=2")
ok(not h.dl.calls, "干跑零删除")

print("── 6) apply：真执行（confirm=1，闸门在处）──")
h = Harness(_plan(ITEMS))
r = h.agent_plan_apply(plan_id=PID, action="cleanup", task_id="t1", confirm=1)
ok(r["ok"] is True and r["data"]["deleted"] == 1, "只删闸门放行的那条")
ok(len(h.dl.calls) == 1 and h.dl.calls[0]["hashes"] == [HA], "唯一删种出口只收到 HA")
ok(h.dl.calls[0]["source"] == "plan/apply" and "plan=" in h.dl.calls[0]["reason"],
   "审计带 plan/apply + plan_id")
blk = r["data"]["blocked"]
ok(len(blk) == 1 and blk[0]["hash"] == HB and "库内资产" in blk[0]["reason"], "被拦的如实回报")

print("── 7) apply：delete_files 透传 ──")
h = Harness(_plan(ITEMS))
h.agent_plan_apply(plan_id=PID, action="cleanup", task_id="t1", confirm=1, delete_files=-1)
ok(h.dl.calls[0]["delete_file"] is False, "-1 → 取任务配置(False)")
h = Harness(_plan(ITEMS))
h.agent_plan_apply(plan_id=PID, action="cleanup", task_id="t1", confirm=1, delete_files=1)
ok(h.dl.calls[0]["delete_file"] is True, "1 → 强制删文件")

print()
if FAILS:
    print(f"❌ FAIL {len(FAILS)}/{N}：")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print(f"✅ PASS {N}/{N}")
