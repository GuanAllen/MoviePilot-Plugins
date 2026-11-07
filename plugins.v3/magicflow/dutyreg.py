# -*- coding: utf-8 -*-
"""魔流 · 岗位注册表（Duty Registry）—— **岗位是单一真值**。

设计对齐 ``features/registry.py``（FeatureSpec + FEATURES）：
**加岗位 = 改这张表**（+ 前端职务色板），不再回头改 ``ledger._task_state`` /
``_task_id`` / ``status._build_task_detail`` / 各岗位的「别抢它」判断。

────────────────────────────────────────────────────────────────────────
为什么需要它（历史债）
────────────────────────────────────────────────────────────────────────
职务（state）与岗位（谁在管）是两件事，但旧代码里混在 if-else 里：

  · ``_task_state``：task_id → 职务，一串 if 堆，加岗位必改
  · ``_task_id``：职务名/岗位名 → task_id，一串 if 堆，且「保种」已被
    ``__hr_host__`` 占用，``__keep__`` 只能叫「手动保种」（命名债）
  · 抢占：散落 20+ 处 ``taken_by == XXX_TASK_ID``，每加岗位都要给**所有**
    既有岗位补一行「跳过它」，漏一处就互相拉锯（2026-10-28 实测过）
  · 展示名：``status.py`` 又一份 if 串

本模块把「有哪些岗位、各自占哪个职务、谁优先、能不能人工设」收成一张表，
上述四处全部从表派生。

────────────────────────────────────────────────────────────────────────
四类岗位（kind）
────────────────────────────────────────────────────────────────────────
  task  真任务（TaskState 驱动）。在岗 = participating；职务由 task_type 决定。
        没有一个固定的「伪 id」，所以不进 ``DUTY_BY_ID``，只进 ``TASK_DUTY``。
  host  常驻伪任务（名单驱动）。名单里才在岗，名单外即下班 → 归静默。
        例：H&R 保种（名单=欠债）、认领（名单=认领账本）、手动保种（名单=人工）。
  pipe  在途管道伪任务。加种即挂、下完/入库即摘，不做长期占位。
        例：点播在途、音乐线。
  ident 不占职务，只给身份标签。例：全站辅种（``reseed`` 明确不造职务）。

────────────────────────────────────────────────────────────────────────
优先级（priority）
────────────────────────────────────────────────────────────────────────
数字大 = 更强势：**低优先级不得抢高优先级的在岗种**。原来是硬编码的
``if taken_by == CLAIM_TASK_ID: continue``，现在统一成一次 ``duty_rank`` 比较。
只有「人工」高于「认领」高于「义务派生」，其余按在途/在岗递减。

────────────────────────────────────────────────────────────────────────
占位口径（poach）—— **默认只从「没人」的池子里招人**
────────────────────────────────────────────────────────────────────────
惯例：一个种同时只归一个岗位（``taken_by`` 唯一）。那**能不能从别人名下拿走**？

  默认（``poach=False``）：**不能**。刷流/魔力/点播/音乐/跨站都是「谁来干都行」的
    绩效/在途岗 —— 抢别人的只会两边每轮互贴标签（2026-10-28 实测拉锯）。
  特殊（``poach=True``）：**能**，且只能从**优先级更低**的岗位挑人。只有「不做就
    违约 / 人工点名」这三类：手动保种（人工点名）、认领（站点承诺）、H&R（欠债）。
    例：认领名单里有、此刻挂在刷流名下 → 认领把它收过来（90 > 60）；
        但挂在手动保种名下 → 不收（95 ≥ 90，人工点名更强，且它照样在种、时长照算）。

判据只有一处：``duty_take_check()``。**各岗位不要再自己写**
``if taken_by == XXX``，加岗位时也不要回头给别人补「跳过它」。

本模块**只依赖 tags.py（纯常量）**，可离线单测（见文件末尾 ``__main__``）；
不 import common（那边顶部依赖 ``app.*``，会把离线测试拖崩）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .tags import (
    STATE_BONUS,
    STATE_BRUSH,
    STATE_CLAIM,
    STATE_HR,
    STATE_KEEP,
    STATE_MUSIC,
    STATE_ONDEMAND,
    STATE_RECOMMEND,
    STATE_SILENT,
)

__all__ = [
    "ID_KEEP",
    "ID_CLAIM",
    "ID_HR_HOST",
    "ID_MUSIC",
    "ID_ONDEMAND",
    "ID_CROSSSEED",
    "ID_SILENT_HOST",
    "KIND_TASK",
    "KIND_HOST",
    "KIND_PIPE",
    "KIND_IDENT",
    "DutySpec",
    "DUTIES",
    "DUTY_BY_ID",
    "TASK_DUTY",
    "DEFAULT_TASK_STATE",
    "duty_spec",
    "duty_state",
    "duty_id_of",
    "duty_name",
    "duty_rank",
    "duty_ids",
    "duty_by_kind",
    "duty_task_spec",
    "duty_take_check",
    "duty_poach_ids",
    "duty_manual_states",
    "duty_host_ids",
]

# ---------------------------------------------------------------- 岗位类别

KIND_TASK = "task"    # 真任务（TaskState 驱动）
KIND_HOST = "host"    # 常驻伪任务（名单驱动）
KIND_PIPE = "pipe"    # 在途管道伪任务（下完即摘）
KIND_IDENT = "ident"  # 不占职务，只给身份标签

# ---------------------------------------------------------------- 岗位 id（单一真值）
#
# ★ 这里是**唯一**定义处；``common.py`` 只做转发（``KEEP_TASK_ID = ID_KEEP`` 等），
#   别再回头往 common 里写字符串字面量。
# ★ 落库值：账本 ``taken_by`` / ``task_id`` 存的就是这些串，**发布后不可改**。
ID_KEEP = "__keep__"              # 手动保种（人工点名）
ID_CLAIM = "__claim__"            # 认领保种（站点认领名单）
ID_HR_HOST = "__hr_host__"        # H&R 保种（欠债派生）
ID_MUSIC = "__music__"            # 音乐线（在途管道）
ID_ONDEMAND = "__ondemand__"      # 点播（在途管道）
ID_CROSSSEED = "__crossseed__"    # 跨站取种（真任务，承接下载）
ID_SILENT_HOST = "__silent_host__"  # 静默托管（默认落点，非名单驱动）


@dataclass(frozen=True)
class DutySpec:
    """一个岗位的登记项。"""

    id: str = ""               # 伪任务 id（KIND_TASK 为空：真任务 id 是动态的）
    name: str = ""             # 展示名（唯一；职务名 ≠ 岗位名，别混用）
    state: str = STATE_SILENT  # 它名下的种算哪个职务
    kind: str = KIND_HOST
    priority: int = 0          # 占位优先级（大者不让）
    lease_days: int = 0        # 占位租约（天）；0 = 不设租约
    poach: bool = False        # ★ 能否从**别的岗位**名下挑人（默认只能招没岗位的）
    settable: bool = False     # 允许人工把**职务**设成它（set_tag_state 白名单）
    driven: bool = True        # 名单驱动、需要 worker 维护上下班
    aliases: Tuple[str, ...] = ()  # 反查别名（不含 id / name 本身）
    desc: str = ""             # 一句话说明（codedict / 自检报错用）

    @property
    def occupancy(self) -> bool:
        """是否**占着岗位**（决定别人能不能把它当「有人在岗」来跳过）。

        身份岗（辅种，只贴标签）与默认落点（静默托管）都不算占岗 ——
        静默的语义就是「没有岗位」，所以谁都可以从静默池招人。
        """
        return self.kind != KIND_IDENT and self.id != ID_SILENT_HOST

    def matches(self, key: str) -> bool:
        """id / 展示名 / 别名 任一命中（大小写不敏感）。"""
        k = str(key or "").strip().lower()
        if not k:
            return False
        if k == str(self.id or "").lower() or k == str(self.name or "").lower():
            return True
        return any(k == str(a).strip().lower() for a in self.aliases)


# ---------------------------------------------------------------- 岗位表
#
# ★ 加岗位只改这里。顺序 = 文档展示顺序；实际抢占看 priority。
# ★ id 是账本 ``taken_by`` / ``task_id`` 的落库值，**一旦发布不可改**
#   （改了旧账本的行就认不回岗位）。
DUTIES: Tuple[DutySpec, ...] = (
    # ---- 常驻岗位（host）：名单驱动，进出即上下班 ----
    # ★ 这三个 poach=True：名单/义务是硬承诺，允许从**优先级更低**的岗位挑人。
    DutySpec(
        id=ID_KEEP, name="手动保种", state=STATE_KEEP, kind=KIND_HOST,
        priority=95, lease_days=0, poach=True, settable=False,
        aliases=("keep", "保种"),
        desc="人工点名长期做种；只能人工解除（入口 action=hold/unhold，不走职务接口）",
    ),
    DutySpec(
        id=ID_CLAIM, name="认领保种", state=STATE_CLAIM, kind=KIND_HOST,
        priority=90, lease_days=3650, poach=True, settable=True,
        aliases=("claim", "认领"),
        desc="站点认领名单驱动；名单在才在岗，退出走账本移除或人工改职务",
    ),
    DutySpec(
        id=ID_HR_HOST, name="H&R保种", state=STATE_HR, kind=KIND_HOST,
        priority=80, lease_days=0, poach=True, settable=False,
        aliases=("hr保种", "h&r保种", "h&r", "hr"),
        desc="由「欠 H&R」派生；结清/作废即释放，不可手动设职务",
    ),
    # ---- 在途管道（pipe）：加种即挂、下完/入库即摘 —— 绩效岗，默认不抢 ----
    DutySpec(
        id=ID_MUSIC, name="音乐线", state=STATE_MUSIC, kind=KIND_PIPE,
        priority=70, lease_days=0,
        aliases=("music", "音乐"),
        desc="音乐加种即挂；下完/入库摘职务回静默池",
    ),
    DutySpec(
        id=ID_ONDEMAND, name="点播", state=STATE_ONDEMAND, kind=KIND_PIPE,
        priority=70, lease_days=0,
        aliases=("ondemand", "点播下载"),
        desc="点播加种即挂；settle 摘职务回静默池",
    ),
    # ---- 真任务（task）：职务由 task_type 派生，无固定 id —— 默认不抢 ----
    DutySpec(
        id="", name="刷流", state=STATE_BRUSH, kind=KIND_TASK,
        priority=60, lease_days=0, settable=True,
        desc="真任务，task_type=brush；在岗 = participating",
    ),
    DutySpec(
        id="", name="魔力", state=STATE_BONUS, kind=KIND_TASK,
        priority=60, lease_days=0, settable=True,
        desc="真任务，非 brush 类型；在岗 = participating",
    ),
    # ---- 特殊：有伪 id 的真任务（承接下载，职务仍归静默） ----
    DutySpec(
        id=ID_CROSSSEED, name="跨站取种", state=STATE_SILENT, kind=KIND_TASK,
        priority=50, lease_days=0,
        aliases=("crossseed",),
        desc="本机没有→去他站免费下；承接下载，下完交全站辅种挂回",
    ),
    # ---- 默认池 / 身份 ----
    DutySpec(
        id=ID_SILENT_HOST, name="静默托管", state=STATE_SILENT, kind=KIND_HOST,
        priority=10, lease_days=0, driven=False,
        aliases=("silent",),
        desc="默认落点：无职务即在此，冻结不占带宽",
    ),
    DutySpec(
        id="", name="辅种", state=STATE_SILENT, kind=KIND_IDENT,
        priority=5, lease_days=0, driven=False,
        desc="全站辅种（reseed）：只给身份标签，明确不另造职务",
    ),
)

#: id → 登记项（只有带固定 id 的岗位进得来）
DUTY_BY_ID: Dict[str, DutySpec] = {
    d.id: d for d in DUTIES if d.id
}

#: 真任务的 task_type → 职务（缺省走 DEFAULT_TASK_STATE）
TASK_DUTY: Dict[str, str] = {"brush": STATE_BRUSH}
DEFAULT_TASK_STATE = STATE_BONUS


# ---------------------------------------------------------------- 查询

def duty_spec(task_id: object) -> Optional[DutySpec]:
    """按 id 取登记项（不做别名解析，别名走 ``duty_id_of``）。"""
    return DUTY_BY_ID.get(str(task_id or "").strip())


def duty_state(task_id: object) -> str:
    """task_id → 职务；**未登记返回空串**（调用方据此回落真任务逻辑）。"""
    spec = duty_spec(task_id)
    return spec.state if spec is not None else ""


def duty_id_of(key: object) -> str:
    """id / 展示名 / 别名 → 岗位 id；查不到返回空串。

    替代旧 ``_task_id`` 里的一串 if。**不按职务名查**——「保种」这种
    被两个岗位共享的职务名，按职务查必然歧义（正是旧代码的坑）。
    """
    k = str(key or "").strip()
    if not k:
        return ""
    spec = DUTY_BY_ID.get(k)
    if spec is not None:
        return spec.id
    low = k.lower()
    for d in DUTIES:
        if d.id and d.matches(low):
            return d.id
    return ""


def duty_name(task_id: object) -> str:
    """task_id → 展示名；未登记返回空串。"""
    spec = duty_spec(task_id)
    return spec.name if spec is not None else ""


def duty_rank(task_id: object, default: int = 0) -> int:
    """占位优先级；未登记（含真任务 id）返回 ``default``。

    抢占判据统一成：``duty_rank(现任) > duty_rank(想抢的)`` → 不许抢。
    """
    spec = duty_spec(task_id)
    return spec.priority if spec is not None else int(default)


def duty_task_spec(state: object) -> Optional[DutySpec]:
    """按**职务**反查真任务岗（刷流/魔力这类没有固定 id 的岗位）。

    只认 ``kind=task``：其余职务名存在多岗共享（「保种」= 手动保种 / H&R），
    按职务查必然歧义 —— 这正是旧 ``_task_id`` 的坑。
    """
    s = str(state or "").strip()
    if not s:
        return None
    best: Optional[DutySpec] = None
    for d in DUTIES:
        if d.kind == KIND_TASK and d.state == s:
            if best is None or d.priority > best.priority:
                best = d
    return best


def duty_poach_ids() -> Tuple[str, ...]:
    """允许「从别的岗位挑人」的特殊岗位（其余一律只从没人岗位招人）。"""
    return tuple(d.id or d.name for d in DUTIES if d.poach)


def _as_spec(who: object) -> Optional[DutySpec]:
    """id / 展示名 / 别名 / DutySpec → 登记项；查不到返回 ``None``（= 未登记真任务）。"""
    if isinstance(who, DutySpec):
        return who
    k = str(who or "").strip()
    if not k:
        return None
    spec = DUTY_BY_ID.get(k)
    if spec is not None:
        return spec
    return duty_spec(duty_id_of(k))


def duty_take_check(taker: object, holder: object, *,
                    lease_until: float = 0.0, now: float = 0.0,
                    holder_state: str = "", taker_id: str = "") -> Tuple[bool, str]:
    """★ **占位唯一判据**：``taker`` 能不能把 ``holder`` 名下的种接过来。

    返回 ``(能否, 拒绝原因)``；原因串只用于日志/干跑说明，判定只看第一个值。

    规则（顺序即优先级）：
      ① 没人占（``holder`` 空）/ 本岗自己 / **本任务自己** → 能（重贴幂等）
      ② 现任岗位**不占岗**（静默托管 / 辅种身份） → 能（静默=没岗位）
      ③ 现任是**未登记的真任务**（动态 task_id）→ 租约过期或没有租约才算空缺
      ④ 现任是登记岗位 → **只有 ``poach=True`` 且优先级更高**才能接手
         （默认口径就是这里：绩效/在途岗一律只能招没岗位的）

    ★ 19.10.40 ``holder_state``：真任务岗（刷流/魔力）在 ``DUTIES`` 里 ``id=""``，
      账本 ``taken_by`` 落的却是**动态 task_id** → ``duty_spec(h_id)`` 恒 None，
      于是同站两个任务相互之间永远走 ③「未登记任务看租约」。而 5 表后端的
      ``mf_seed`` **不落 ``lease_until`` 列**（``_read_seeds`` 读回恒 0）⇒ 租约恒过期
      ⇒ 刷流/魔力每轮互相抢光对方（2026-10-30 YemaPT 实证）。调用方把账本记录的
      ``state`` 传进来，这里按职务反查登记项，让 ④ 生效。

    ★ 19.10.40 ``taker_id``：同一个闸门还要认得「这本来就是我」。真任务岗的
      ``DutySpec.id`` 是空串，``h_id == t_spec.id`` 对真实 task_id 永远不成立 ——
      不传 ``taker_id`` 的话，补上 ④ 之后**自己重贴自己的种也会被拒**。
    """
    t_spec = _as_spec(taker)
    h_id = str(getattr(holder, "id", "") or holder or "").strip()
    if not h_id:
        return True, ""
    if taker_id and h_id == str(taker_id).strip():
        return True, ""
    if t_spec is not None and h_id == t_spec.id:
        return True, ""
    h_spec = duty_spec(h_id)
    if h_spec is None and holder_state:
        # 动态 task_id 反查不到登记项 → 按职务反查（刷流/魔力这类真任务岗）。
        # ★ 只在**真职务**上反查：``STATE_SILENT`` 在 DUTIES 里被「跨站取种」
        #   （kind=task）占着，按职务查会把它认成在岗 → 违背「静默 = 没岗位」铁律。
        _hs = duty_task_spec(holder_state)
        if _hs is not None and _hs.state != STATE_SILENT:
            h_spec = _hs
    if h_spec is not None and not h_spec.occupancy:
        return True, ""
    _name = (h_spec.name if h_spec is not None else h_id)
    if t_spec is None or not t_spec.poach:
        if h_spec is None:
            # 未登记的真任务占位：租约过期 = 残留，可以接手（旧 `_tag_assign` 的租约语义）
            try:
                _expired = float(lease_until or 0.0) <= float(now or time.time())
            except (TypeError, ValueError):
                _expired = True
            return (True, "") if _expired else (False, f"{_name} 租约未到期")
        return False, f"{_name} 在岗（本岗非特殊岗位，不跨岗挑人）"
    if duty_rank(h_id) >= t_spec.priority:
        return False, f"{_name}({duty_rank(h_id)}) 不低于本岗({t_spec.priority})"
    return True, ""


def duty_ids() -> Tuple[str, ...]:
    """所有带固定 id 的岗位（伪任务列表用）。"""
    return tuple(d.id for d in DUTIES if d.id)


def duty_by_kind(kind: str) -> Tuple[DutySpec, ...]:
    """按类别取岗位（host / pipe / task / ident）。"""
    k = str(kind or "").strip().lower()
    return tuple(d for d in DUTIES if d.kind == k)


def duty_host_ids() -> Tuple[str, ...]:
    """常驻岗位（名单驱动，需要 worker 维护上下班）。

    不含「静默托管」（``driven=False``）：它是默认落点，无名单也无上下班。
    """
    return tuple(d.id for d in DUTIES if d.id and d.kind == KIND_HOST and d.driven)


def duty_manual_states() -> Tuple[str, ...]:
    """允许人工设置的职务（``set_tag_state`` 白名单）。

    ★ 只收 ``settable=True`` 的岗位职务 + 静默/推荐。保种不在此列：
      保种只由「欠 H&R」派生，手动设会被下一轮 ``_hr_host_release`` 收回
      （``__keep__`` 虽为人工点名，但走 ``action=hold``，不走职务接口）。
    """
    out = [d.state for d in DUTIES if d.settable and d.state]
    for extra in (STATE_SILENT, STATE_RECOMMEND):
        if extra not in out:
            out.append(extra)
    return tuple(out)


if __name__ == "__main__":  # 离线自检：python -m magicflow.dutyreg
    assert len({d.name for d in DUTIES}) == len(DUTIES), "岗位展示名必须唯一"
    assert len({d.id for d in DUTIES if d.id}) == len([d for d in DUTIES if d.id]), "岗位 id 必须唯一"
    assert duty_state("__claim__") == STATE_CLAIM
    assert duty_state("__hr_host__") == STATE_HR
    assert duty_state("__keep__") == STATE_HR
    assert duty_state("__nope__") == ""
    assert duty_id_of("认领保种") == "__claim__"
    assert duty_id_of("保种") == "__keep__"          # ★ 19.12.38 职务拆分：保种=keep
    assert duty_id_of("手动保种") == "__keep__"
    assert duty_rank("__keep__") > duty_rank("__claim__") > duty_rank("__hr_host__")
    assert set(duty_manual_states()) >= {STATE_CLAIM, STATE_SILENT, STATE_RECOMMEND}
    assert STATE_HR not in duty_manual_states(), "保种=义务派生，不能人工设"

    # ---- 占位口径：默认只招没人岗位的，特殊岗位才能跨岗挑人 ----
    assert set(duty_poach_ids()) == {ID_KEEP, ID_CLAIM, ID_HR_HOST}, "只有人工/承诺/义务三类可跨岗挑人"
    _free = duty_take_check(ID_CLAIM, "")
    assert _free[0], "没人占的种谁都能接"
    assert duty_take_check(ID_CLAIM, ID_SILENT_HOST)[0], "静默=没岗位 → 能接"
    assert duty_take_check(ID_MUSIC, ID_SILENT_HOST)[0], "静默=没岗位 → 绩效岗也能接"
    assert duty_take_check(ID_CLAIM, "__brush_task_1", lease_until=time.time() + 600)[0], \
        "认领是特殊岗位：未登记任务+未到期租约也能挑（跨岗）"
    assert not duty_take_check(ID_MUSIC, "__brush_task_1", lease_until=time.time() + 600)[0], \
        "音乐不是特殊岗位：别人租约未到期 → 不抢"
    assert duty_take_check(ID_MUSIC, "__brush_task_1", lease_until=time.time() - 1)[0], \
        "租约过期 = 残留占位 → 可以接手（仅限不知道职务的未登记任务）"
    # ★ 19.10.40：同站两个真任务（刷流/魔力）之间绝不能互抢。账本 taken_by 是动态
    #   task_id（duty_spec 恒 None），5 表后端又不落 lease_until（读回恒 0）→ 只靠租约
    #   就是「谁跑谁抢」。传 holder_state 后必须走 ④ 拒绝（2026-10-30 YemaPT 实证 179 次）。
    assert not duty_take_check(duty_task_spec(STATE_BONUS), "f9fbf57ab9ce",
                              lease_until=0.0, holder_state=STATE_BRUSH)[0], \
        "★ 魔力不抢刷流名下的种（租约恒 0 也不行）"
    assert not duty_take_check(duty_task_spec(STATE_BRUSH), "2314a542048e",
                              lease_until=0.0, holder_state=STATE_BONUS)[0], \
        "★ 刷流不抢魔力的种（反向）"
    assert duty_take_check(duty_task_spec(STATE_BONUS), "f9fbf57ab9ce",
                           lease_until=0.0, holder_state=STATE_SILENT)[0], \
        "职务=静默的残留占位不算在岗 → 可以接手"
    assert duty_take_check(ID_CLAIM, ID_MUSIC)[0], "认领(90) 可从音乐(70)挑人"
    assert duty_take_check(duty_task_spec(STATE_BRUSH), ID_MUSIC)[0] is False, \
        "刷流(非特殊岗) 不从音乐挑人"
    assert duty_take_check(duty_task_spec(STATE_BONUS), ID_HR_HOST)[0] is False, \
        "魔力(非特殊岗) 不从 H&R 挑人"
    assert not duty_take_check(ID_CLAIM, ID_KEEP)[0], "认领(90) 不抢手动保种(95)"
    assert not duty_take_check(ID_HR_HOST, ID_CLAIM)[0], "H&R(80) 不抢认领(90)"
    assert not duty_take_check(ID_MUSIC, ID_ONDEMAND)[0], "同级在途岗互不抢（先到先得）"
    assert duty_take_check(ID_CLAIM, ID_CLAIM)[0], "本岗重贴幂等"
    assert not duty_spec(ID_SILENT_HOST).occupancy, "静默托管不算占岗（它就是「没岗位」）"
    assert not duty_by_kind(KIND_IDENT)[0].occupancy, "辅种是纯身份，不算占岗"
    assert duty_spec(ID_CLAIM).occupancy and duty_spec(ID_CROSSSEED).occupancy, "认领/跨站在岗占位"
    print(f"dutyreg OK: {len(DUTIES)} 个岗位 / {len(DUTY_BY_ID)} 个固定 id / "
          f"可跨岗挑人 {len(duty_poach_ids())} 个")
