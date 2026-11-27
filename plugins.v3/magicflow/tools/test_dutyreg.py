#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 岗位注册表（dutyreg）离线回归 —— 纯数据校验，不需 MoviePilot / qB。

背景（2026-10-28）：职务派生原来散成 4 份 if 串（``_task_state`` / ``_task_id`` /
``_task_name`` / 各处「别抢它」），每加一个岗位都要回头改 4 处，漏一处就互相拉锯。
收进 ``dutyreg.py`` 一张表后，本文件钉住这张表的**契约**：

  [1] 表结构：id / 展示名唯一；state 必须是合法职务；
  [2] 落库值快照：8 个岗位的 id 字符串**不可变**（改了旧账本就认不回岗位）；
  [3] 派生：id → 职务 / id → 展示名 / 名字·别名 → id（八种叫法全覆盖）；
  [4] 抢占序：保种池三岗同级 95 > 任务(0)（19.12.39 起不再分 95/90/80）；
  [5] 可设白名单：认领/刷流/魔力/静默/推荐 可；保种（义务派生）不可；
  [6] 类别：host 岗位要能被 worker 找到；静默托管/辅种不进上下班名单；
  [7] 占位口径：默认只招没人岗位的，特殊岗位才跨岗挑人；
  [8] ★ 保种池同级回归（19.12.39）：手动保种 / 认领 / H&R 三岗**双向互不抢**，
      归属「先到先得」保留现状，且判定幂等 —— 修「认领单向吸走 H&R 的种」。

用法：``python3 tools/test_dutyreg.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_dutyreg_test"

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
dr = _load(PKG + ".dutyreg", "dutyreg.py")


# ---------------------------------------------------------------- [1] 表结构
print("[1] 表结构：唯一性 / 职务合法性")
ok(len({d.name for d in dr.DUTIES}) == len(dr.DUTIES), "岗位展示名唯一")
_ids = [d.id for d in dr.DUTIES if d.id]
ok(len(set(_ids)) == len(_ids), f"固定 id 唯一（{len(_ids)} 个）")
ok(all(d.state in tags.STATES for d in dr.DUTIES),
   "每个岗位的 state 都是合法职务")
ok(all(d.kind in (dr.KIND_TASK, dr.KIND_HOST, dr.KIND_PIPE, dr.KIND_IDENT)
       for d in dr.DUTIES), "kind 取值合法")
ok(all(d.priority > 0 for d in dr.DUTIES), "每个岗位都有正优先级")

# ---------------------------------------------------------------- [2] 落库值快照
print("[2] 落库值快照：id 字符串不可变（改了就认不回旧账本）")
_SNAPSHOT = {
    "__keep__": "手动保种",
    "__claim__": "认领保种",
    "__hr_host__": "H&R保种",
    "__music__": "音乐线",
    "__ondemand__": "点播",
    "__crossseed__": "跨站取种",
    "__silent_host__": "静默托管",
}
for _id, _name in _SNAPSHOT.items():
    spec = dr.duty_spec(_id)
    ok(spec is not None and spec.name == _name, f"{_id} → {_name}")
ok(len(_SNAPSHOT) == len(dr.DUTY_BY_ID), f"固定 id 数量 = 快照数量（{len(_SNAPSHOT)}）")

# ---------------------------------------------------------------- [3] 派生
print("[3] 派生：id→职务 / id→展示名 / 名字·别名→id")
_EXPECT_STATE = {
    "__keep__": tags.STATE_KEEP,   # ★ 19.12.38：保种职务归 keep
    "__claim__": tags.STATE_CLAIM,
    "__hr_host__": tags.STATE_HR,
    "__music__": tags.STATE_MUSIC,
    "__ondemand__": tags.STATE_ONDEMAND,
    "__crossseed__": tags.STATE_SILENT,   # 承接下载，职务仍归静默
    "__silent_host__": tags.STATE_SILENT,
}
for _id, _st in _EXPECT_STATE.items():
    ok(dr.duty_state(_id) == _st, f"duty_state({_id}) = {_st}")
ok(dr.duty_state("some-dynamic-task-id") == "", "未登记的真任务 id → 空串（回落 task_type）")
ok(dr.duty_state("") == "", "空 id → 空串")

# 八种叫法：每个岗位至少能被「展示名」和「id」反查到
for d in dr.DUTIES:
    if not d.id:
        continue
    ok(dr.duty_id_of(d.name) == d.id, f"展示名「{d.name}」→ {d.id}")
    ok(dr.duty_id_of(d.id) == d.id, f"id「{d.id}」反查自身")
# 历史别名（老代码/老账本/人肉输入都这么叫）
_ALIAS = {
    "保种": "__keep__",          # ★ 19.12.38：职务拆分后「保种」= 手动保种；
    #   拆开前这里指向 __hr_host__（两岗共用职务名，按职务查必然歧义）
    "h&r保种": "__hr_host__",
    "hr保种": "__hr_host__",
    "手动保种": "__keep__",
    "keep": "__keep__",
    "认领": "__claim__",
    "认领保种": "__claim__",
    "claim": "__claim__",
    "点播": "__ondemand__",
    "点播下载": "__ondemand__",
    "音乐": "__music__",
    "音乐线": "__music__",
    "跨站取种": "__crossseed__",
}
for _k, _v in _ALIAS.items():
    ok(dr.duty_id_of(_k) == _v, f"别名「{_k}」→ {_v}")
ok(dr.duty_id_of("不存在的岗位") == "", "未知名字 → 空串")
ok(dr.duty_name("__claim__") == "认领保种", "duty_name(__claim__) 有值（旧实现漏了这条）")

# ---------------------------------------------------------------- [4] 抢占序
print("[4] 抢占序：保种池同级 95 > 任务(0)")
ok(dr.duty_rank("__keep__") == dr.duty_rank("__claim__") == dr.duty_rank("__hr_host__") == 95,
   f"★ 保种池三岗同级 95（keep={dr.duty_rank('__keep__')} "
   f"claim={dr.duty_rank('__claim__')} hr={dr.duty_rank('__hr_host__')}）")
ok(dr.duty_rank("__keep__") > dr.duty_rank("__music__"),
   f"保种池({dr.duty_rank('__keep__')}) > 在途/绩效岗({dr.duty_rank('__music__')})")
ok(dr.duty_rank("__hr_host__") > dr.duty_rank("dynamic-task-id"),
   "H&R > 任务(未登记=0) → 任务不抢 H&R")
ok(dr.duty_rank("dynamic-task-id") == 0, "未登记岗位 rank=0")

# ---------------------------------------------------------------- [5] 可设白名单
print("[5] 可设职务白名单（set_tag_state）")
_allow = dr.duty_manual_states()
for _st in (tags.STATE_CLAIM, tags.STATE_BRUSH, tags.STATE_BONUS,
            tags.STATE_SILENT, tags.STATE_RECOMMEND):
    ok(_st in _allow, f"「{_st}」可手动设")
ok(tags.STATE_HR not in _allow,
   "「H&R」不可手动设（义务派生，设了会被 hr_host 收回）")
ok(tags.STATE_KEEP not in _allow,
   "「保种」不可手动设（人工点名走 action=hold，不走职务接口）")
ok(len(set(_allow)) == len(_allow), "白名单无重复")

# ---------------------------------------------------------------- [6] 类别
print("[6] 类别：worker 名单 / 默认落点")
_hosts = dr.duty_host_ids()
for _h in ("__keep__", "__claim__", "__hr_host__"):
    ok(_h in _hosts, f"{_h} 是常驻岗位（需要上下班驱动）")
ok("__silent_host__" not in _hosts, "静默托管不进上下班名单（它是默认落点）")
ok("__music__" not in _hosts and "__ondemand__" not in _hosts,
   "在途管道（音乐/点播）不按名单驱动上下班")
ok(len(dr.duty_by_kind(dr.KIND_IDENT)) == 1, "「辅种」登记为纯身份岗位（不占职务）")

# ---------------------------------------------------------------- [7] 占位口径
print("[7] 占位口径：默认只招「没岗位」的，特殊岗位才跨岗挑人")
_POACH = {"__keep__", "__claim__", "__hr_host__"}
ok(set(dr.duty_poach_ids()) == _POACH,
   f"可跨岗挑人 = 手动保种/认领/H&R（实为 {sorted(dr.duty_poach_ids())}）")
ok(not any(d.poach for d in dr.DUTIES if d.kind in (dr.KIND_TASK, dr.KIND_PIPE)),
   "绩效岗（刷流/魔力/点播/音乐/跨站）一律 poach=False → 只能招没人岗位的")

_future = 9e9      # 未到期租约
_past = 1.0        # 过期租约
ok(dr.duty_take_check("__claim__", "")[0], "空缺 → 谁都能接")
ok(dr.duty_take_check("__music__", "__silent_host__")[0],
   "静默托管不算占岗（静默=没岗位）→ 绩效岗也能接")
ok(dr.duty_take_check("__music__", "__brush_task_1", lease_until=_future)[0] is False,
   "绩效岗：未登记任务租约未到期 → 不抢")
ok(dr.duty_take_check("__music__", "__brush_task_1", lease_until=_past)[0],
   "绩效岗：租约过期 = 残留占位 → 可以接手")
ok(dr.duty_take_check("__music__", "__ondemand__")[0] is False,
   "同级在途岗互不抢（先到先得）")
ok(dr.duty_take_check("__claim__", "__music__")[0], "认领(95) 可从音乐(70) 挑人")
ok(dr.duty_take_check("__claim__", "__brush_task_1", lease_until=_future)[0],
   "认领是特殊岗：未到期租约也照挑")
ok(dr.duty_take_check("__claim__", "__keep__")[0] is False,
   "认领(95) 不抢手动保种(95：同级)")
ok(dr.duty_take_check("__hr_host__", "__claim__")[0] is False, "H&R(95) 不抢认领(95：同级)")
ok(dr.duty_take_check("__hr_host__", "__ondemand__")[0], "H&R(95) 可从点播(70) 挑人")
ok(dr.duty_take_check("__keep__", "__claim__")[0] is False,
   "★ 手动保种(95) 也不再从认领挑人（同级先到先得；19.12.39 前是 95>90 允许）")
ok(dr.duty_take_check("__claim__", "__claim__")[0], "本岗重贴幂等")
_bs = dr.duty_task_spec(tags.STATE_BRUSH)
ok(_bs is not None and _bs.name == "刷流", "按职务反查真任务岗：刷流")
ok(dr.duty_task_spec(tags.STATE_BONUS).name == "魔力", "按职务反查真任务岗：魔力")
ok(dr.duty_task_spec(tags.STATE_HR) is None, "「H&R」不按职务反查（host 岗必歧义）")
ok(dr.duty_take_check(_bs, "__hr_host__")[0] is False, "刷流不抢 H&R")
_reason = dr.duty_take_check("__music__", "__hr_host__")[1]
ok(bool(_reason) and "在岗" in _reason, f"拒绝时给出可读原因（{_reason}）")

# ---------------------------------------------------------------- [8] 保种池同级
print("[8] ★ 保种池同级回归（19.12.39）：三岗双向互不抢，归属保留现状")
_POOL = (("__keep__", "手动保种"), ("__claim__", "认领"), ("__hr_host__", "H&R"))
for _t, _tn in _POOL:
    for _h, _hn in _POOL:
        _r = dr.duty_take_check(_t, _h)
        if _t == _h:
            ok(_r[0], f"{_tn} 重贴自己 → 幂等放行")
        else:
            ok(_r[0] is False, f"{_tn} 不抢 {_hn}（同级保留当前归属）")
# 这条是本次修复的**病灶**：旧 90>80，认领每轮把 H&R 名下的种收走
_r = dr.duty_take_check("__claim__", "__hr_host__")
ok(_r[0] is False, "★ 认领不再吸走 H&R 的种（旧 90>80 的病灶）")
ok("同级" in _r[1] and "保留当前归属" in _r[1], f"拒绝原因说明是同级（{_r[1]}）")
ok(dr.duty_take_check("__hr_host__", "__claim__")[0] is False, "★ 反向：H&R 也不抢认领")
# 归属稳定性：同一输入连跑两次结论一致（不是每轮重新选主）
ok([dr.duty_take_check("__claim__", "__hr_host__")[0] for _ in range(3)] == [False] * 3,
   "同级判定幂等 → 不会两岗每轮互搬")
# 红线：L0 不许改变「下完即判、欠则接管」——H&R 仍能从刷流/魔力/点播/音乐接管
for _h, _st, _hn in (("__brush_task_1", tags.STATE_BRUSH, "刷流"),
                     ("__bonus_task_1", tags.STATE_BONUS, "魔力"),
                     ("__ondemand__", "", "点播"),
                     ("__music__", "", "音乐")):
    ok(dr.duty_take_check("__hr_host__", _h, lease_until=_past, holder_state=_st)[0],
       f"★ 红线：H&R 仍能从{_hn}名下接管（账目与做种不能脱节）")

# ---------------------------------------------------------------- 汇总
print("\n" + "=" * 60)
if _fails:
    print(f"❌ FAIL：{len(_fails)}/{_n} 断言未过")
    for f in _fails:
        print("   -", f)
    sys.exit(1)
print(f"✅ 全部通过：{_n} 项断言")
sys.exit(0)
