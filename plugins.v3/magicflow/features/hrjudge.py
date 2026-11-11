# -*- coding: utf-8 -*-
"""H&R 判定**唯一入口**（任务 120 / 121 / 124）。

## 一条契约

**账本是欠账清单，不是全量台账。**

- 账本里**有**这笔债 → 欠：按已挂工时 + 站端结论判还清没有
- 账本里**没有** → 不欠：不需要再推断一遍站点规则

于是整个判定只有一棵树、两个分支：

```text
1  复用副本 / 未下载完成              → NONE    （结构上无义务）
2  本 hash 的账单
     结清 / 作废                      → CLEAR
     未结清（active / pending / 脏态） → 按工时 + 站端判
3  账本里没有                          → CLEAR   （不欠）
```

规则推断只在**开账那一刻**（``skip_bill=True``）使用 —— 那时问的是「这笔债
该不该有」，账本里必然还没有，只能靠站点规则 + 种子标记。

## 为什么收成一个

同一问题曾有四份实现：9.0.0 跨站（``_crossseed_hr_decision``）、11.0.0 判债
（``_hr_obligation`` 四路）、19.12.33 开账（``_hr_obligation_rule``）、静默池
（``_silent_hr_done``）。每次都在旁边加一个新的，从没把旧的收进去。

后果是馒头 3 颗种：开账判「不该记」（账本 0 张），判债自己推出「未知 →
保守 24h → 欠」，静默池又说「不许清」。**账本说没有，代码不信账本** ——
这就是假欠的来源，也是四份实现必然的结果。

现在四个入口都是本文件的薄包装，只选方向，不各自推断。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

try:  # 与 hr.py / hrbills.py 同一个来源，保证「已挂小时」口径唯一
    from ..downloader_ops import seed_hours_for_hr as _seed_hours_for_hr
except Exception:  # pragma: no cover - 仅单测/离线环境
    def _seed_hours_for_hr(_t: Any) -> float:  # type: ignore[misc]
        return 0.0

# ---- 判定态 ----
ST_OWE = "owe"           # 确定欠
ST_CLEAR = "clear"       # 确定不欠
ST_UNKNOWN = "unknown"   # 未探明（不判欠）
ST_NONE = "none"         # 结构上无义务

# ---- 依据来源（用于审计与排障，替代过去五花八门的 reason 串） ----
BAS_REUSE = "reuse"
BAS_INCOMPLETE = "incomplete"
BAS_BILL = "bill"
BAS_BILL_SITE = "bill_site"
BAS_BILL_SRC = "bill_src"
BAS_RULE = "rule"
BAS_SEED = "seed"
BAS_STORE_ERR = "store_error"
BAS_NONE = "none"

# 是否允许「降级采信」台账里非权威来源的 hr 值（见 ``_rule_degraded``）。
# 关掉即回到 3.41.0 的严格口径：非 manual/welcome 一律当未探明。
HR_JUDGE_ALLOW_DEGRADED = True

# 影子模式：新判定与旧判定并行跑，**只记差异不改变行为**。验收后置 False。
HR_JUDGE_SHADOW = True

# 未探明时是否沿用旧的保守方向（当欠处理）。
# True = 与现状完全一致（NovaHD 这类从没探明的站继续被保护）；False = 放行。
HR_UNKNOWN_CONSERVATIVE = True


@dataclass
class Verdict:
    """一次判定的完整结论。调用方只读，不改判。"""

    state: str
    need_hours: float = 0.0
    seeded_hours: float = 0.0
    basis: str = BAS_NONE
    reason: str = ""

    @property
    def owed(self) -> bool:
        """只有**确定欠**才算欠。UNKNOWN 不算 —— 这是与旧实现最大的差别。"""
        return self.state == ST_OWE

    @property
    def cleared(self) -> bool:
        return self.state == ST_CLEAR

    @property
    def undecided(self) -> bool:
        """未探明：没有证据说欠，也没有证据说不欠。

        调用方按动作可逆性决定方向：
        删除 / 清理 / 接管 → 不动（当欠处理）
        记账 → 不记（避免僵尸账）
        展示 → 单列「待确认」，不进欠账数字
        """
        return self.state == ST_UNKNOWN

    def as_tuple(self, conservative_unknown: bool = True) -> Tuple[bool, float, float, str]:
        """兼容旧 ``_hr_obligation`` 的四元组返回值。

        ``conservative_unknown=True``（默认，保护方向）：未探明也按「欠」返回，
        与 11.0.0 以来的行为一致 —— 删除闸门、暂停、接管都靠这个方向保命。
        ``False``（记账/展示方向）：只有确定欠才返回 True。

        ★ 这里不产生账单、不改状态，只决定「调用方看见的布尔值」。
        """
        owed = self.owed or (conservative_unknown and self.undecided)
        reason = self.reason or ""
        if self.undecided and conservative_unknown:
            reason = "未探明(保守按欠)/%s" % (reason or "no-basis")
        return (owed, float(self.need_hours), float(self.seeded_hours), reason)

    def should_open_bill(self) -> bool:
        """开账口径：只给**确定要求 H&R** 的种建账。

        19.12.33 的裁决（不重复踩僵尸账）+ 一条补充：站点明确写「不要求做种时长」
        （``need_hours == 0`` 且已判定不欠）→ 也没有可还的债，不开账。
        """
        if self.state not in (ST_OWE, ST_CLEAR):
            return False
        if self.basis not in (BAS_RULE, BAS_SEED, BAS_BILL, BAS_BILL_SITE, BAS_BILL_SRC):
            return False
        if self.state == ST_CLEAR and self.need_hours <= 0:
            return False
        return True

    def bill_rule(self) -> Optional[str]:
        """开账时要写的 ``rule`` 字段；不该开账返回 ``None``。"""
        if not self.should_open_bill():
            return None
        return "hit_and_run" if self.basis == BAS_SEED else "site_hr"

    def holds_protection(self) -> bool:
        """保护方向：确定欠 + 未探明都算（不可逆动作不动）。结构上无义务不算。"""
        return self.state in (ST_OWE, ST_UNKNOWN)


# ---- 影子模式记账（只用于验收期，正式切换后可整段删除）----
_SHADOW: Dict[str, int] = {}
_SHADOW_TOTAL = 0
_SHADOW_VERBOSE = 30          # 前 N 条逐条打，其余只计数
_SHADOW_FLUSH_AT = 500


def _shadow_log(host: Any, msg: str) -> None:
    fn = getattr(host, "_log", None)
    if callable(fn):
        try:
            fn(msg, "info")
            return
        except Exception:  # noqa: BLE001
            pass
    try:  # 兜底：直接进标准日志，别因为 host 没有 _log 就丢掉证据
        import logging
        logging.getLogger("magicflow.hrjudge").info(msg)
    except Exception:  # noqa: BLE001
        pass


def shadow_note(host: Any, hash_: str, site: str, old: str, new: str,
                reason: str = "") -> None:
    """记录一次「新旧判定不一致」。去重计数 + 定量明细，避免刷爆日志。"""
    global _SHADOW_TOTAL
    _SHADOW_TOTAL += 1
    try:
        key = "%s→%s" % (str(old).split("/")[0], str(new).split("/")[0])
        _SHADOW[key] = _SHADOW.get(key, 0) + 1
    except Exception:  # noqa: BLE001
        pass
    if _SHADOW_TOTAL <= _SHADOW_VERBOSE:
        _shadow_log(host, "[HR-JUDGE-DIFF] %s %s old=%s new=%s %s" % (
            hash_, site, old, new, reason))
    if _SHADOW_TOTAL % _SHADOW_FLUSH_AT == 0:
        _shadow_log(host, "[HR-JUDGE-SUM] total=%d %s" % (_SHADOW_TOTAL, dict(_SHADOW)))


def shadow_summary() -> Dict[str, Any]:
    """当前影子差异快照（供健康自检/状态接口读取）。"""
    return {"total": _SHADOW_TOTAL, "by_kind": dict(_SHADOW)}


def _safe(host: Any, name: str, *args: Any, default: Any = None) -> Any:
    """调 host 上的老方法；不存在或抛错一律回落到 default（绝不因探测失败而改判）。"""
    fn = getattr(host, name, None)
    if not callable(fn):
        return default
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001
        return default


def _rule_degraded(host: Any, dom: str) -> Tuple[Optional[bool], str]:
    """**降级采信**：权威来源（``manual`` / ``welcome``）缺失时，台账里若仍留着一个
    明确的 ``hr`` 值（来源是 ``builtin`` / ``retired`` / ``framework``），就用它。

    为什么需要这一层：3.41.0 把非权威来源的 hr 结论「退役」了，``hr_of()`` 一律返回
    ``None``。于是馒头（台账 ``hr=f``、来源 builtin）变成「未探明」，被老规则判欠 24h；
    学校（台账 ``hr=t``、来源 builtin）也变成「未探明」。**两站的事实相反，却都掉进
    unknown** —— 这正是「规则里明明标了无，判定却说不知道」的直接原因。

    降级采信不是恢复旧权威：返回值只用于**判定方向**，并标记 ``degraded`` 让它可被
    审计区分；对外展示与「权威确认」语义仍走 ``hr_of()``。想退回旧行为：关
    ``HR_JUDGE_ALLOW_DEGRADED``。

    Returns: ``(True/False/None, 来源说明)``
    """
    if not HR_JUDGE_ALLOW_DEGRADED:
        return None, ""
    try:
        from ..sites.rules import _norm_domain, _same_domain  # noqa: WPS433
    except Exception:  # noqa: BLE001
        # 离线/单测环境：用等价的本地实现，不因导入失败而丢掉降级能力
        def _norm_domain(x: Any) -> str:  # type: ignore[misc]
            return str(x or "").strip().lower().replace("www.", "")

        def _same_domain(a: Any, b: Any) -> bool:  # type: ignore[misc]
            return _norm_domain(a) == _norm_domain(b)
    getter = getattr(host, "_site_rules", None)
    if not callable(getter):
        return None, ""
    try:
        obj = getter()
        items = obj.items() or {}
    except Exception:  # noqa: BLE001
        return None, ""
    d = _norm_domain(dom)
    rec: Dict[str, Any] = {}
    try:
        rec = dict(items.get(d) or {})
        if not rec:
            for k, v in items.items():
                if _same_domain(k, d):
                    rec = dict(v or {})
                    break
    except Exception:  # noqa: BLE001
        return None, ""
    if rec.get("hr") is None:
        return None, ""
    since = "%s/%s" % (rec.get("source") or "?", rec.get("hr_src") or "-")
    return bool(rec.get("hr")), since


def _rule_tristate(host: Any, dom: str) -> Tuple[Optional[bool], float, str, str, bool]:
    """站点规则三态 + 要求工时 + 来源说明 + 置信档 + 工时是否已定论。

    返回 ``(True/False/None, need_hours, since, tier, need_known)``，``tier`` ∈
    ``authoritative`` / ``degraded`` / ``unknown``。``None`` 表示确实未探明。

    ``need_known``：站点是否**明确**写了做种时长（含真实 ``0``）。
    ``True`` 且 ``need_hours == 0`` 表示「站点不要求做种时长」——这不是未知，
    不该被兜底成 24h，也不该开账。
    """
    d = str(dom or "").strip()
    if not d:
        return None, 0.0, "no-domain", "unknown", False
    flag = _safe(host, "_site_hr_flag", d, default=None)
    tier = "authoritative"
    src = "site"
    if isinstance(flag, bool):
        try:
            _h, _s = _safe(host, "_crossseed_seed_hours_detail", d, default=(0.0, "site"))
            if _s:
                src = str(_s)
        except Exception:  # noqa: BLE001
            pass
    else:
        flag, src = _rule_degraded(host, d)
        tier = "degraded" if isinstance(flag, bool) else "unknown"
    if not isinstance(flag, bool):
        return None, 0.0, src or "unknown", "unknown", False
    need_known = False
    hours = 0.0
    _known = _safe(host, "_hr_need_hours_known", d, default="__missing__")
    if _known != "__missing__" and _known is not None:
        try:
            hours = float(_known)
            need_known = True
        except (TypeError, ValueError):
            need_known = False
    if not need_known:
        try:
            hours = float(_safe(host, "_hr_need_hours_or_default", d, default=0.0) or 0.0)
        except (TypeError, ValueError):
            hours = 0.0
    return flag, hours, src, tier, need_known


def _judge_seed_hours(host: Any, need: float, seeded: float) -> bool:
    """是否真欠：``seeded < need + margin``。margin 与账单状态机同源（14.0.0 血泪）。"""
    try:
        due = float(_safe(host, "_hr_due_hours", float(need), default=float(need)) or 0.0)
    except (TypeError, ValueError):
        due = float(need)
    return float(seeded) + 1e-6 < due


def _seed_hours(t: Any) -> float:
    """已挂小时。单一来源（``downloader_ops.seed_hours_for_hr``），不允许各算各的。"""
    if t is None:
        return 0.0
    try:
        return float(_seed_hours_for_hr(t) or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _read_one_bill(host: Any, hash_: str) -> Tuple[Any, bool]:
    """读一条本地账单。返回 ``(bill, store_ok)``。

    ``store_ok=False`` 表示**存储不可用**，不是「没有账单」——调用方必须按欠处理。
    这与旧实现（``_hr_read_confirmed`` 失败即保守）方向一致。
    """
    try:
        from .hrbills import _hr_read_confirmed, _hr_read_ok  # noqa: WPS433
    except Exception:  # noqa: BLE001
        return None, True
    getter = getattr(host, "_hrbills_store", None)
    store = None
    if callable(getter):
        try:
            store = getter()
        except Exception:  # noqa: BLE001
            store = None
    if store is None or not hasattr(store, "get_result"):
        return None, True
    try:
        res = store.get_result(hash_)
    except Exception:  # noqa: BLE001
        return None, True
    if _hr_read_ok is None or not _hr_read_confirmed(res):
        return None, False
    return (res or {}).get("value"), True


def _bill_verdict(host: Any, bill: Any, hash_: str) -> Optional[Verdict]:
    """按一张本地账单给结论。返回 ``None`` **仅**表示「账本里没有这张账单」。

    ``bill`` 形态与 ``mf_bills`` 一致：``state`` / ``rule`` / ``need_h`` / ``seeded_h``。

    ★ 2026-11-09：账本是**欠账清单** —— 只要这里有记录，它就是一笔「欠」。
    任何未结清状态（``pending`` / 认不出的脏状态）都按欠处理，**绝不返回 None**：
    否则上层会把「账本有账但读不懂」读成「不欠」，直接把种放行。
    """
    if not isinstance(bill, dict):
        return None
    state = str(bill.get("state") or "").strip().lower()
    try:
        need = float(bill.get("need_h") or 0.0)
    except (TypeError, ValueError):
        need = 0.0
    try:
        seeded = float(bill.get("seeded_h") or 0.0)
    except (TypeError, ValueError):
        seeded = 0.0
    if state in ("void", "settled", "done", "cancelled", "canceled"):
        # 已结清 / 已作废：账单说了算。但站端翻案要等下一轮 tick 才重开，
        # 这段空窗期不能让种被 pause → 再问一次站端（19.12.4 的同一条教训）。
        if state == "settled":
            sv, left = _safe(host, "_hr_site_verdict", hash_,
                             str(bill.get("site") or ""), default=("unknown", 0.0)) \
                or ("unknown", 0.0)
            if sv == "owed":
                left_h = float(left or 0.0) / 3600.0
                return Verdict(ST_OWE, need or 24.0, seeded, BAS_BILL_SITE,
                               "账单(站端还需%.1fh)" % left_h)
        return Verdict(ST_CLEAR, need, seeded, BAS_BILL, "账单已结清(%s)" % state)
    # —— 以下都是「账本里有账且未结清」——
    if need > 0 and _judge_seed_hours(host, need, seeded):
        return Verdict(ST_OWE, need, seeded, BAS_BILL, "账单(未挂满)")
    sv, left = _safe(host, "_hr_site_verdict", hash_,
                     str(bill.get("site") or ""), default=("unknown", 0.0)) \
        or ("unknown", 0.0)
    if sv == "owed":
        left_h = float(left or 0.0) / 3600.0
        return Verdict(ST_OWE, need or 24.0, seeded, BAS_BILL_SITE,
                       "账单(站端还需%.1fh)" % left_h)
    if state in ("active", "open"):
        return Verdict(ST_CLEAR, need, seeded, BAS_BILL, "账单(已挂满)")
    # pending / 认不出的状态：债已建、还没开始计 → 按欠，不动
    return Verdict(ST_OWE, need or 24.0, seeded, BAS_BILL,
                   "账单(未结清:%s)" % (state or "?"))


def judge(host: Any, site: str, torrent: Any = None, snap: Any = None,
          bills: Optional[Dict[str, Dict[str, Any]]] = None,
          seed_hours_fn: Any = None, hr_flag: Any = None,
          skip_bill: bool = False) -> Verdict:
    """**唯一判定入口**：这颗种欠不欠 H&R。

    Args:
        host: 插件实例（提供 ``_hr_is_reuse`` / ``_hr_site_verdict`` 等既有能力）。
        site: MP 站点名或域名（展示 / 规则查询用）。
        torrent: 种子对象（需 ``hash`` / ``hit_and_run`` / ``progress`` 等）。
            **可以为 None** —— 跨站选源、开账门槛这类场景只有「域名 + 种子标记」，
            没有种子对象；此时跳过第 1 步（无结构信息），其余照常。
        snap: 本轮已拉好的 qB 全量快照，避免逐种重拉。
        bills: 本轮已读好的全量账单 ``{hash: bill}``，避免逐条 DB 会话。
        seed_hours_fn: 已挂小时取值函数，默认 ``downloader_ops.seed_hours_for_hr``。
        hr_flag: ``torrent`` 为 None 时的种子级 H&R 标记（True/False/None）。
        skip_bill: 决定这次问的是**哪个问题**：

            - ``False``（默认，保护 / 删除 / 暂停 / 静默清出 / 接管）：
              问「这笔债还清没有」—— **只查账本**。账本里没有 = 不欠，
              不再推断站点规则。
            - ``True``（开账 / 跨站选源）：问「这笔债该不该有」——
              账本里必然还没有，只能靠站点规则 + 种子标记推断。
    """
    _sfn = seed_hours_fn or _seed_hours_for_hr

    def _sh(t: Any) -> float:
        if t is None:
            return 0.0
        try:
            return float(_sfn(t) or 0.0)
        except Exception:  # noqa: BLE001
            return 0.0

    h = str(getattr(torrent, "hash", "") or "").strip().lower()

    # ---- 1 结构上无义务（纯内存，必须最先跑；否则 1549 个复用副本各付 6ms）----
    if torrent is not None:
        if _safe(host, "_hr_is_reuse", torrent, default=False):
            return Verdict(ST_NONE, basis=BAS_REUSE, reason="复用/补源副本(非真实下载)")
        if _safe(host, "_hr_incomplete_of", site, torrent, default=False):
            return Verdict(ST_NONE, basis=BAS_INCOMPLETE, reason="未下载完成(无 H&R 义务)")

    # ---- 2 本 hash 的账单：事实优先 ----
    if not skip_bill and h and bills is not None:
        v = _bill_verdict(host, bills.get(h), h)
        if v is not None:
            return v
    elif not skip_bill and h:
        res, store_ok = _read_one_bill(host, h)
        if not store_ok:
            # 存储不可用 ≠ 无账单。旧实现按欠处理，方向保持不变（fail-safe）。
            return Verdict(ST_OWE, basis=BAS_STORE_ERR, reason="账单存储不可用(保守按欠 H&R)")
        v = _bill_verdict(host, res, h)
        if v is not None:
            return v

    # ---- 2.5 账本没有这笔债 → 不欠（★ 2026-11-09 裁决，判定的全部）----
    #   账本是**欠账清单**，不是全量台账：只记判定为欠的种。
    #   「账本里没有」就是「不欠」，不需要再把站点规则推断一遍。
    #   旧实现让非开账路径也去推规则，于是账本说没有、代码推出「欠 24h」，
    #   这就是那 3 条假欠的成因。
    #   规则推断只在开账那一刻（``skip_bill=True``）使用 —— 那时问的是
    #   「这笔债该不该有」，账本里必然还没有。
    if not skip_bill:
        return Verdict(ST_CLEAR, basis=BAS_NONE, reason="账本无此债(不欠)")

    # ---- 3 开账门槛：这笔债该不该有（仅 skip_bill=True 会到这里）----
    if torrent is not None:
        dom = _safe(host, "_hr_domain", site, torrent, default="") or ""
        thr = bool(getattr(torrent, "hit_and_run", False))
    else:
        # 无种子对象（跨站选源 / 开账门槛）：site 已是域名，标记由调用方显式给。
        dom = str(site or "").strip().lower()
        thr = bool(hr_flag)
    flag, need, rsrc, rtier, need_known = _rule_tristate(host, dom)
    if _safe(host, "_site_per_torrent_hr", dom, default=False):
        # 逐种站：只认这颗种自己的标记
        if not thr:
            return Verdict(ST_CLEAR, basis=BAS_RULE, reason="逐种站未标H&R(%s)" % rsrc)
        need = need or 24.0
    if flag is False and not _safe(host, "_site_per_torrent_hr", dom, default=False):
        # ★ 19.12.36：站点**明确无 H&R** 且非逐种站 → 种子级标记一律不采信。
        #   线上实证：馒头列表页解析出的 hit_and_run 是误读，旧的「标记优先」会判欠 24h。
        #   （逐种站豁免：它本来就只认种子标记，上面已单独处理。）
        return Verdict(ST_CLEAR, basis=BAS_RULE, reason="站点明确无H&R(%s)" % rsrc)
    if flag is True or thr:
        if need <= 0:
            if need_known and not thr:
                # 站点明确「不要求做种时长」→ 无工时义务（不是未知，别兜底成 24h）
                return Verdict(ST_CLEAR, 0.0, _sh(torrent), BAS_RULE,
                               "站点明确不要求做种时长(%s)" % rsrc)
            need = 24.0
        seeded = _sh(torrent)
        if _judge_seed_hours(host, need, seeded):
            basis = BAS_SEED if (thr and flag is None) else BAS_RULE
            return Verdict(ST_OWE, need, seeded, basis, "站点规则(%s)" % rsrc)
        return Verdict(ST_CLEAR, need, seeded, BAS_RULE, "站点规则已挂满(%s)" % rsrc)

    # ---- 4 兜底：未探明 → 不猜（开账侧不记；保护侧已在 2.5 早退）----
    return Verdict(ST_UNKNOWN, basis=BAS_NONE,
                   reason="未探明(规则未知·不判欠)")
