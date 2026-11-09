# -*- coding: utf-8 -*-
"""魔流 · H&R 临期通知准入闸门（纯函数，无外部依赖）。

任务 105 / HR-04：19.12.43 的 ``notify_check_hr`` 只按 ``at_risk`` / ``hours_left``
阈值筛选，不看账单状态、也不看「是否已达标」。于是 51 条 settled 账单
（seeded_h 远超 need_h）被算出的负 hours_left 全部当成「临近考核窗口」——
2026-11-07 08:00 / 14:08 两次实测告警各 19 条，其中 18 条是已结清幽灵。

本模块把「哪些账单允许进入临期通知」抽成纯函数，原因：
- 通知规则要能离线回归（``tools/test_hr_notify_gate.py`` 不连库、不起插件）；
- ``notify.py`` 顶部依赖 ``app.sdk`` / ``kvstore`` 等，测试不能直接 import。

准入语义（与 ``features/hrbills.py`` 的状态机/``at_risk`` 口径一致）：
- ``settled`` / ``void``：终态（已结清/已作废），绝不进「临期」；
- ``breached``：已违约（欠种消失、保护不解除），处理路径是账单面板补种/申诉，
  不属于「临近到期」，也不进临期通知（``at_risk`` 口径本就不含 breached）；
- ``active`` / ``pending``：仍在考核中，才允许进入；其中 ``pending`` 还要求后端
  已给出 ``at_risk``（尚未开始做种/规则未知的 pending 只有按默认窗口算出的
  hours_left，直接按阈值发「临近考核」就是幽灵告警）；
- 已达标（``seeded_h >= need_h + margin``）一律排除——这是幽灵通知的根因，
  余量口径与结清规则 ``seeded_h >= need_h + seed_margin_hours`` 相同；
- ``at_risk`` / ``hours_left`` 阈值判断保持 19.12.43 原样：``at_risk`` 为真，或
  ``hours_left <= 阈值``。不因为压噪音而放宽真实临期。
"""

from typing import Any, Dict, Iterable, List, Optional

#: 仍处于「考核中」、允许进入临期通知的账单状态
HR_NOTIFY_OPEN_STATES = ("active", "pending")

#: 单次通知最多携带的候选条数（与原 notify_check_hr 的 [:20] 一致）
HR_NOTIFY_KEEP = 20


def _float_or_none(value: Any) -> Optional[float]:
    """安全转 float；None/空/非法一律返回 None（调用方据此走「未知」而非 0）。"""
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def is_open_bill(state: Any) -> bool:
    """账单是否仍处于「考核中」（只有 open 状态才可能进临期通知）。"""
    return str(state or "").strip().lower() in HR_NOTIFY_OPEN_STATES


def is_attained(item: Dict[str, Any], margin_hours: float = 0.0) -> bool:
    """是否已达到结清条件（``seeded_h >= need_h + margin``）。

    字段缺失/不可转数字时返回 False（不擅自抑制告警，宁可多报不可漏报）。
    """
    seeded = _float_or_none(item.get("seeded_h"))
    need = _float_or_none(item.get("need_h"))
    if seeded is None or need is None:
        return False
    margin = _float_or_none(margin_hours) or 0.0
    return seeded >= need + max(0.0, margin)


def deadline_candidate(item: Dict[str, Any], site: str, limit_hours: float = 24.0,
                       margin_hours: float = 0.0) -> Optional[Dict[str, Any]]:
    """判断单条账单是否应进入「临期」通知；是则返回通知用 dict，否则 None。"""
    state = str(item.get("state") or "").strip().lower()
    if not is_open_bill(state):
        return None
    if is_attained(item, margin_hours):
        return None
    risk = bool(item.get("at_risk"))
    if state == "pending" and not risk:
        # pending = 已下载未起种：还没有真实做种进度，只信后端明确的 at_risk，
        # 不拿「按默认窗口算出来的 hours_left」去报临近考核（幽灵告警的一类）。
        return None
    hl = _float_or_none(item.get("hours_left"))
    if not risk and hl is None:
        return None
    if not risk and hl is not None and hl > float(limit_hours or 0):
        return None
    return {
        "site": str(site or ""),
        "title": str(item.get("title") or "")[:80],
        "hours_left": (round(hl, 1) if hl is not None else None),
        "need_h": item.get("need_h"),
        "seeded_h": item.get("seeded_h"),
        "state": str(item.get("state") or ""),
    }


def rank_candidates(candidates: Iterable[Dict[str, Any]],
                    keep: int = HR_NOTIFY_KEEP) -> List[Dict[str, Any]]:
    """按「剩余小时升序」排序（无 hours_left 的排最后），截取前 keep 条。"""
    out = list(candidates or [])
    out.sort(key=lambda x: (x.get("hours_left") is None,
                            x.get("hours_left") if x.get("hours_left") is not None else 0.0))
    if keep and keep > 0:
        return out[:keep]
    return out


def deadline_candidates(items: Iterable[Dict[str, Any]], site: str,
                        limit_hours: float = 24.0, margin_hours: float = 0.0,
                        keep: int = HR_NOTIFY_KEEP) -> List[Dict[str, Any]]:
    """把一个站点的账单列表筛成临期候选（已排序、已截断，只读、不改入参）。"""
    out = []
    for item in items or []:
        picked = deadline_candidate(item, site, limit_hours, margin_hours)
        if picked is not None:
            out.append(picked)
    return rank_candidates(out, keep)
