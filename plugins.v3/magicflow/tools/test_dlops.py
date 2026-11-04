#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 下载器写操作中台（dlops）离线回归 —— 用桩对象跑守卫 / 防抖 / 归因，不需 qB。

背景（2026-10-28）：每 60 分钟 qB 里固定 930 个被暂停、911 个被恢复，精确对消；
逐个排除插件内四个 ``pause_torrents`` 调用点后仍**定位不到**，因为写操作散落
9 个文件、成功路径全都不打日志。本文件钉住 ``dlops.py`` 的契约：

  [1] 守卫看**账本**不看标签：静默且无岗 → 可停不可起；在岗（任何职务）→ 不可停；
  [2] ``taken_by`` 是占岗岗位（认领/保种…）→ 不可停，即使 state 写着静默；
  [3] ``force=True`` 跳过守卫（结清/遣散这类「必须停」）；
  [4] 防抖：同一 hash 在窗口内被反向操作 → 拒绝并计 ``flapped``（掐死对消）；
  [5] 干跑零写入；
  [6] 归因：成功也打一行日志，带 ``by`` 与拒因计数；
  [7] 无账本记录（tag_only，如全站辅种副本）→ 不拦（不变量要守，不能因缺数据放过）；
  [8] 下载器不可用 → 落 ``error``，不抛异常。

用法：``python3 tools/test_dlops.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_dlops_test"

_fails: list[str] = []
_n = 0


def ok(cond, msg: str) -> None:
    global _n
    _n += 1
    if cond:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        _fails.append(msg)


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
tags = _load(PKG + ".tags", "tags.py")
dutyreg = _load(PKG + ".dutyreg", "dutyreg.py")
dlops = _load(PKG + ".dlops", "dlops.py")

STATE_SILENT = tags.STATE_SILENT
STATE_BONUS = tags.STATE_BONUS


# ---------------------------------------------------------------- 桩

class _DL:
    def __init__(self, alive: bool = True):
        self.is_available = alive
        self.calls: list = []

    def pause_torrents(self, hs):
        self.calls.append(("pause", list(hs)))
        return len(hs), None

    def resume_torrents(self, hs):
        self.calls.append(("resume", list(hs)))
        return len(hs), None

    def recheck_torrents(self, hs):
        self.calls.append(("recheck", list(hs)))
        return len(hs), None


class _Host:
    def __init__(self, led: dict, alive: bool = True):
        self.led = led
        self.dl = _DL(alive)
        self.logs: list = []

    def _tag_state(self):
        return self.led

    def _get_downloader(self, _n="qbittorrent"):
        if not self.dl.is_available:
            return None
        return self.dl

    def _log(self, msg, level=""):
        self.logs.append(str(msg))


H_REST = "a" * 40      # 静默、无岗
H_DUTY = "b" * 40      # 在岗（魔力）
H_CLAIM = "c" * 40     # 静默但 taken_by 占岗
H_NOLED = "d" * 40     # 账本里没有

LED = {
    H_REST: {"state": STATE_SILENT},
    H_DUTY: {"state": STATE_BONUS, "taken_by": "__brush_1__"},
    H_CLAIM: {"state": STATE_SILENT, "taken_by": "__claim__"},
}

print("\n[1] 静默且无岗 → 可停、不可起")
dlops.reset()
h = _Host(LED)
r = dlops.pause(h, [H_REST], by="t1")
ok(r["done"] == 1 and not r["vetoed"], "pause 放行")
dlops.reset()
h = _Host(LED)
r = dlops.resume(h, [H_REST], by="t1")
ok(r["done"] == 0 and r["reasons"].get("silent_rest") == 1, "resume 被拒（silent_rest）")

print("\n[2] 在岗 → 不可停、可起")
dlops.reset()
h = _Host(LED)
r = dlops.pause(h, [H_DUTY], by="t2")
ok(r["done"] == 0 and r["vetoed"] == 1, "pause 被拒")
ok(set(r["reasons"]) <= {"on_duty", "other_state"}, f"拒因合法: {r['reasons']}")
r = dlops.resume(h, [H_DUTY], by="t2")
ok(r["done"] == 1 and not r["vetoed"], "resume 放行")

print("\n[3] state=静默但 taken_by 占岗（认领）→ 不可停")
dlops.reset()
h = _Host(LED)
r = dlops.pause(h, [H_CLAIM], by="t3")
ok(r["done"] == 0 and r["reasons"].get("on_duty") == 1, "认领种被守卫挡住")

print("\n[4] force 跳过守卫")
dlops.reset()
h = _Host(LED)
r = dlops.pause(h, [H_DUTY], by="t4", force=True)
ok(r["done"] == 1 and not r["vetoed"], "force 停掉在岗种")

print("\n[5] 防抖：窗口内反向操作被拒")
dlops.reset()
h = _Host(LED)
dlops.pause(h, [H_DUTY], by="t5", force=True)
r = dlops.resume(h, [H_DUTY], by="t5", force=True)
ok(r["done"] == 0 and r["flapped"] == 1, "pause 后立刻 resume → 判抖")
ok(h.dl.calls == [("pause", [H_DUTY])], f"只有第一次真的下发: {h.dl.calls}")
r2 = dlops.pause(h, [H_DUTY], by="t5", force=True)
ok(r2["done"] == 1, "同向重复操作不判抖")

print("\n[6] 干跑零写入")
dlops.reset()
h = _Host(LED)
r = dlops.pause(h, [H_REST], by="t6", dry=True)
ok(r["planned"] == 1 and r["done"] == 0 and not h.dl.calls, "dry 只算不写")

print("\n[7] 归因日志：成功也打，且带 by / 拒因")
ok(any("dlops:pause" in x and "by=t6" in x for x in h.logs), f"日志: {h.logs[-1:]}")
dlops.reset()
h = _Host(LED)
dlops.pause(h, [H_REST, H_DUTY, H_CLAIM], by="silent_enforce", reason="周期收敛")
line = h.logs[-1] if h.logs else ""
ok("请=3" in line and "成=1" in line and "拒=2" in line, f"计数对得上: {line}")

print("\n[8] 去重 / 空值")
dlops.reset()
h = _Host(LED)
r = dlops.pause(h, [H_REST.upper(), H_REST, "", None], by="t8")
ok(r["asked"] == 1 and r["done"] == 1, "大小写归一 + 去重 + 丢空")

print("\n[9] 无账本记录（tag_only）→ 不拦")
dlops.reset()
h = _Host(LED)
r = dlops.pause(h, [H_NOLED], by="t9")
ok(r["done"] == 1 and not r["vetoed"], "静默不变量优先，缺记录照停")
r = dlops.resume(h, ["e" * 40], by="t9")   # 换一条没操作过的，避开防抖
ok(r["done"] == 1, "缺记录恢复也放行（不猜）")

print("\n[10] 下载器不可用 → 落 error 不抛")
dlops.reset()
h = _Host(LED, alive=False)
r = dlops.pause(h, [H_REST], by="t10")
ok(r["error"] and r["done"] == 0, f"error={r['error']}")

print("\n[11] 统计可读")
s = dlops.stats()
ok("flap_table" in s and "counters" in s, f"stats={s}")

print()
if _fails:
    print(f"FAIL：{len(_fails)} 项未过（共 {_n} 项）")
    for f in _fails:
        print("  -", f)
    raise SystemExit(1)
print(f"PASS：{_n}/{_n} 项")
