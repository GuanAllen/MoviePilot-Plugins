# -*- coding: utf-8 -*-
"""魔流 · reportview —— **报表唯一口径**（★ 17.3.0）。

回答问题：**「我们手上到底有哪些种、各是什么身份、欠不欠债、能不能动？」**
一句话口径：**台账一行 = 一颗种；真值源 = 账本；下载器快照只补传输态并用于互校。**

三层真值源（只读，全部现读，不新增/不缓存真值）：

1. **种子账本**（``ledger.SeedLedgerStore``）——职务轴 ``state``（刷流/魔力/保种/静默，
   由 ``task_id`` 推导，见 ``ledger.py:496-522``）、身份轴 ``sub``（新/资源/普通）、
   站点、体积、库内资产标记；
2. **H&R 账单账本**（``hr_bills.json``）——``rule`` ∈ {site_hr, hit_and_run, unknown}；
   ★ ``unknown``（backfill 影子账）**必须出现在视图里**，归「未定性」一类，不许静默丢弃；
3. **资源账本**（``mf_resource``）——资源组与 ``in_library``（库内资产判定）。

**下载器快照不再是真值域**：它只补 ``transport``（做种中/暂停/未完成/不在下载器），
并用于互校（账本有而下载器没有 = ``ledger_only`` 幽灵；下载器有而账本没有 = ``qb_only`` 未纳管）。
保护结论唯一来自 ``ProtectionMixin._protection_sets``（hard/soft/incomplete + 理由）。

三个视图 = **同一台账的三种投影**（数字从此必然一致）：

- ``view=site``   按站聚合全量（收口旧 ``GET /agent/site/seeds``）
- ``view=silent`` ``bucket=静默`` 的行（收口旧 ``GET /agent/silent``）
- ``view=hr``     有 H&R 义务/账单的行（收口旧 ``GET /agent/hr/bills``；``unknown`` 显式归「未定性」）
- ``view=rows``   通用台账（可选过滤：site/state/bucket/sub/origin/transport/hr/protected）

互校：``GET /agent/report/drift``（账本 × 下载器 × MP 站点清单 × 账单四向对齐）。

设计约束：本模块**只读**——不写下载器、不写账本、不写热层；所有外部调用都包 try/except，
任何一路取不到只是少一列，不许让整个报表 500。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.schemas import Response

from ..tags import (
    EXTERNAL_TAG,
    RESCUE_TAG,
    STATE_BONUS,
    STATE_BRUSH,
    STATE_HR,
    STATE_SILENT,
    SUB_NEW,
    SUB_PLAIN,
    SUB_RESOURCE,
    identity_of,
    is_reuse_copy,
)
from .hrbills import (
    BILL_STATE_ACTIVE,
    BILL_STATE_BREACHED,
    RULE_HIT_AND_RUN,
    RULE_SITE_HR,
)
from .sitereport import (
    BUCKET_BONUS,
    BUCKET_BRUSH,
    BUCKET_EXTERNAL,
    BUCKET_HR,
    BUCKET_RESCUE,
    BUCKET_SILENT,
    MAX_ITEMS,
    ORIGIN_NONE,
    ORIGIN_POOL,
    ORIGIN_RESEED,
    SILENT_SUBS,
    TRANSPORT_DOWNLOADING,
    TRANSPORT_PAUSED,
    TRANSPORT_SEEDING,
    _BUCKET_ORDER,
    _ORIGIN_ORDER,
)

#: 账本有、下载器没有（幽灵行）的传输态标签——不是真实的传输状态，单独命名，避免冒充「暂停」
TRANSPORT_ABSENT = "不在下载器"
#: 账单分类（★ 17.3.0）：有 H&R 义务 vs 未定性（rule=unknown，多为 backfill 影子账）
BILL_CLASS_HR = "hr"
BILL_CLASS_UNCLASSIFIED = "未定性"

#: 统一入口支持的视图 + 参数（非法值一律报错，**不再静默忽略**）
RV_VIEWS = ("site", "silent", "hr", "rows")
RV_PARAMS = ("view", "site", "state", "bucket", "sub", "origin", "transport",
             "hr", "protected", "limit", "offset")
RV_HR_FILTERS = ("1", "0", "欠", "有", "hr", "unclassified", "未定性")

_HR_RULES = (RULE_SITE_HR, RULE_HIT_AND_RUN)
_ALL_TRANSPORT = (TRANSPORT_SEEDING, TRANSPORT_PAUSED, TRANSPORT_DOWNLOADING, TRANSPORT_ABSENT)


# --------------------------------------------------------------------------- 小工具


def _as_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _as_int(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def _truthy(v: Any) -> bool:
    """参数里的「真」：1/true/yes/on/欠/有/是 都算，其余（含空）算假。"""
    s = str(v if v is not None else "").strip().lower()
    return s in ("1", "true", "yes", "y", "on", "欠", "有", "是", "true")


def _opt_bool(v: Any) -> Optional[bool]:
    """参数里的三态：空 = 不过滤；否则按 ``_truthy``。"""
    s = str(v if v is not None else "").strip()
    return None if not s else _truthy(s)


def _norm_dom(s: Any) -> str:
    """域名归一：剥 scheme / 路径 / 端口 / 尾斜杠，再剥 ``www.`` 前缀。

    ★ 17.3.0 实测：``_list_sites()`` 给的 ``domain`` 是**完整 URL**（如
    ``https://pt.btschool.club/``），账本给的是**短域名**（``btschool.club``）、
    账单/标签给的又可能是中文短名（``红豆饭``）。不归一就会把同一个站拆成多行，
    所以这里只认「host 形态」，并保留 ``_site_lookup`` 做逐级后缀回退。
    """
    t = str(s or "").strip().lower()
    if "://" in t:
        t = t.split("://", 1)[1]
    t = t.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if ":" in t:
        t = t.split(":", 1)[0]
    t = t.strip().strip(".")
    while t.startswith("www."):
        t = t[4:]
    return t


def _site_lookup(idx: Dict[str, Any], raw: Any) -> Dict[str, Any]:
    """站点索引查询：原样 → 归一 host → 逐级去掉最左标签 → 中文名。

    ★ 17.3.0：MP 域名是 ``pt.btschool.club``、账本短名是 ``btschool.club``，
    两者只有靠「去掉最左标签」才能落到同一条目。
    """
    s = str(raw or "").strip()
    if not s:
        return {}
    low = s.lower()
    dom = _norm_dom(s)
    for k in (low, dom):
        if k and k in idx:
            return idx[k]
    parts = dom.split(".") if dom else []
    for i in range(1, max(0, len(parts) - 1)):
        k = ".".join(parts[i:])
        if k in idx:
            return idx[k]
    return {}


def _norm_sub(v: Any) -> str:
    """身份轴归一：账本 ``sub`` 可能是 ``('财神', '普通')`` 这类 tuple / JSON 串（可嵌套）。

    ★ 17.3.0 实测：``mf_resource.identity`` 有时整条元组被存成字符串（甚至嵌套一层），
    直接计数会出现 ``('财神', '普通')`` 这种脏键；逐层取**最后一个非空元素**、最多解 4 层。
    """
    cur: Any = v
    for _ in range(4):
        if cur is None:
            return ""
        if isinstance(cur, (list, tuple)):
            parts = [x for x in cur if str(x or "").strip()]
            if not parts:
                return ""
            cur = parts[-1]
            continue
        s = str(cur).strip()
        if s.startswith("(") and s.endswith(")"):
            try:
                import ast as _ast
                val = _ast.literal_eval(s)
            except Exception:  # noqa: BLE001
                val = None
            if isinstance(val, (list, tuple)):
                parts = [x for x in val if str(x or "").strip()]
                if not parts:
                    return ""
                cur = parts[-1]
                continue
            parts = [p.strip().strip("'\"") for p in s.strip("()").split(",") if p.strip()]
            return parts[-1] if parts else ""
        return s
    return str(cur).strip().strip("'\"")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _site_key(s: Any) -> str:
    """站点键归一：域名优先（账本短名与 MP 域名都能落到同一键）。"""
    return _norm_dom(s)


def _bucket_from_ledger(lb_state: str, is_hr: bool, tags: List[str]) -> str:
    """账本职务 → 六桶（优先级与 ``_site_report_bucket`` 一致，账本优先）。"""
    if RESCUE_TAG in tags:
        return BUCKET_RESCUE
    if is_hr or lb_state == STATE_HR:
        return BUCKET_HR
    if lb_state == STATE_BRUSH:
        return BUCKET_BRUSH
    if lb_state == STATE_BONUS:
        return BUCKET_BONUS
    if EXTERNAL_TAG in tags:
        return BUCKET_EXTERNAL
    return BUCKET_SILENT


def _transport_of(t: Any, tr_fn: Any = None) -> str:
    if t is None:
        return TRANSPORT_ABSENT
    if callable(tr_fn):
        try:
            return str(tr_fn(str(getattr(t, "state", "") or ""),
                             _as_float(getattr(t, "progress", 0))) or TRANSPORT_ABSENT)
        except Exception:  # noqa: BLE001
            pass
    prog = _as_float(getattr(t, "progress", 0))
    st = str(getattr(t, "state", "") or "").lower()
    if prog < 0.999 or "download" in st:
        return TRANSPORT_DOWNLOADING
    if "paused" in st or "stop" in st or "queued" in st and "up" not in st:
        return TRANSPORT_PAUSED
    return TRANSPORT_SEEDING


def _bucket_by_order() -> Dict[str, int]:
    return {b: i for i, b in enumerate(_BUCKET_ORDER)}


# --------------------------------------------------------------------------- 台账


def build_rows(ctx: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """**唯一台账**：hash → 行（账本 ∪ 下载器快照 ∪ 账单 ∪ 站点欠账）。

    纯函数（只吃 ``ctx``），便于离线断言口径。行字段见模块 docstring。
    """
    ledger: Dict[str, Any] = ctx.get("ledger") or {}
    snap: Dict[str, Any] = ctx.get("snap") or {}
    bills: Dict[str, Any] = ctx.get("bills") or {}
    owed: Dict[str, str] = ctx.get("owed") or {}
    prot: Dict[str, Any] = ctx.get("protected") or {}
    hard = set(prot.get("hard") or ())
    soft = set(prot.get("soft") or ())
    inc = set(prot.get("incomplete") or ())
    why: Dict[str, str] = dict(prot.get("why") or {})
    legacy = set(prot.get("legacy") or ())
    idx: Dict[str, Any] = ctx.get("site_index") or {}
    sd: Dict[str, Any] = ctx.get("site_deleted") or {}
    known = set(ctx.get("known_sites") or ())
    reseed = set(ctx.get("reseed") or ())
    cssrc: Dict[str, Any] = ctx.get("crossseed") or {}
    tr_fn = ctx.get("transport_fn")
    sub_fn = ctx.get("sub_fn")
    bucket_fn = ctx.get("bucket_fn")
    reuse_fn = ctx.get("reuse_fn") or is_reuse_copy
    site_of_fn = ctx.get("site_of_fn")
    deadline_fn = ctx.get("deadline_fn")
    oblig_fn = ctx.get("hr_obligation_fn")
    now = _as_float(ctx.get("now"), time.time())

    out: Dict[str, Dict[str, Any]] = {}
    keys = [str(k) for k in ledger] + [str(k) for k in snap] + \
           [str(k) for k in bills] + [str(k) for k in owed]
    for raw in keys:
        h = str(raw or "").strip().lower()
        if not h or h in out:
            continue
        rec = dict(ledger.get(raw) or ledger.get(h) or {})
        t = snap.get(raw) if raw in snap else snap.get(h)
        bill = dict(bills.get(raw) or bills.get(h) or {})
        tags = [str(x) for x in (getattr(t, "tags", None) or [])] if t is not None else []
        # ---- 站点归属：账本 > 标签/tracker > 账单
        site_raw = str(rec.get("site") or "").strip()
        if not site_raw and t is not None and callable(site_of_fn):
            try:
                site_raw = str(site_of_fn(t, known) or "").strip()
            except Exception:  # noqa: BLE001
                site_raw = ""
        if not site_raw:
            site_raw = str(bill.get("site") or "").strip()
        info = _site_lookup(idx, site_raw)
        site_name = str(info.get("name") or site_raw or "")
        site_dom = _norm_dom(info.get("domain") or site_raw)
        in_qb = t is not None
        state = str(getattr(t, "state", "") or "") if in_qb else ""
        progress = _as_float(getattr(t, "progress", 0)) if in_qb else 0.0
        size_gb = _as_float(rec.get("size_gb"))
        if not size_gb and in_qb:
            size_gb = _as_float(getattr(t, "size_gb", 0))
        if not size_gb:
            size_gb = _as_float(bill.get("size_gb"))
        # ---- 义务/账单
        bill_state = str(bill.get("state") or "")
        bill_rule = str(bill.get("rule") or "")
        bill_class = BILL_CLASS_HR if bill_rule in _HR_RULES else (
            BILL_CLASS_UNCLASSIFIED if bill else "")
        is_reuse = bool(reuse_fn(tags)) if in_qb else False
        is_hr = (not is_reuse) and (
            h in owed or (bill_state == BILL_STATE_ACTIVE and bill_rule in _HR_RULES))
        is_prot = (h in hard) or (h in soft) or (h in legacy)
        p_class = ("hard" if h in hard else ("soft" if h in soft else
                                             ("incomplete" if h in inc else "")))
        if not p_class and h in legacy:
            p_class = "hard"   # 只在 legacy 里（旧 store 保护）→ 按硬保护归类
        # ---- 六桶：账本职务优先（账本即真值），无账本才退回标签判定
        lb_state = str(rec.get("state") or "")
        bucket = ""
        if lb_state:
            bucket = _bucket_from_ledger(lb_state, is_hr, tags)
        elif in_qb and callable(bucket_fn):
            try:
                bucket = str(bucket_fn(t, state, progress, is_hr, is_prot) or "")
            except Exception:  # noqa: BLE001
                bucket = ""
        if not bucket:
            bucket = _bucket_from_ledger(lb_state, is_hr, tags)
        sub = _norm_sub(rec.get("sub"))
        if not sub and in_qb and callable(sub_fn):
            try:
                sub = _norm_sub(sub_fn(t, bucket))
            except Exception:  # noqa: BLE001
                sub = ""
        if not sub:
            # ★ 17.3.0 实测：``identity_of(tags)`` 可能回 2 元组 (站点, 身份)，
            #   ``str()`` 一包就成 ``('财神', '普通')`` 脏键 → 必须过 ``_norm_sub``。
            sub = _norm_sub(identity_of(tags)) if tags else ""
        if not sub and bucket == BUCKET_SILENT:
            sub = SUB_PLAIN
        origin = (ORIGIN_POOL if rec else (ORIGIN_RESEED if h in reseed else ORIGIN_NONE))
        # ---- 静默池运营字段（跨站来源份：剩余/需做种/已做种/进池时长）
        cs = cssrc.get(h) or {}
        remain_min: Optional[float] = None
        need_hours = 0.0
        seeded_h = 0.0
        if cs:
            try:
                until = _as_float(cs.get("seed_until"))
            except Exception:  # noqa: BLE001
                until = 0.0
            if until:
                remain_min = round(max(0.0, (until - now) / 60.0), 1)
            need_hours = _as_float(cs.get("need_hours"))
            seeded_h = round(_as_float(cs.get("seeded_sec")) / 3600.0, 2)
        _ts = rec.get("ts") or rec.get("since") or rec.get("taken_at") or 0
        _tsf = _as_float(_ts)
        if _tsf > 1e11:
            _tsf = _tsf / 1000.0
        age_h = round(max(0.0, now - _tsf) / 3600.0, 2) if _tsf > 0 else None
        # ---- 静默池的 H&R 义务（真值：_hr_obligation / 账单 / 站点欠账）
        owed_hr = is_hr
        if callable(oblig_fn) and in_qb:
            try:
                owed_hr = bool(oblig_fn(site_name or site_dom, t, snap=snap)[0])
            except Exception:  # noqa: BLE001
                owed_hr = is_hr
        deadline = {}
        if bill and callable(deadline_fn):
            try:
                deadline = dict(deadline_fn(bill) or {})
            except Exception:  # noqa: BLE001
                deadline = {}
        ledger_only = bool(rec) and not in_qb
        qb_only = in_qb and not rec
        # ★ 17.5.0：与 H8 / 通知 / /agent/sites/deleted 共用「已删站真值源」——
        #   站点引用还在（账单/账本残留），而 MP 站点表里已没有它。
        _sd_key = _norm_dom(site_dom or site_raw)
        site_deleted = bool(site_raw) and (not info or bool(_sd_key and _sd_key in sd))
        out[h] = {
            "hash": h,
            "site": site_dom or site_raw,
            "site_raw": site_raw,
            "site_name": site_name,
            "site_deleted": site_deleted,
            "title": str(rec.get("title") or getattr(t, "title", "") or
                         bill.get("title") or "")[:160],
            "size_gb": round(size_gb, 3),
            "save_path": str(getattr(t, "save_path", "") or "") if in_qb else "",
            "state": state,
            "lb_state": lb_state,
            "progress": round(progress, 4),
            "ratio": round(_as_float(getattr(t, "ratio", 0)), 3) if in_qb else 0.0,
            "uploaded": round(_as_float(getattr(t, "uploaded", 0))) if in_qb else 0,
            "bucket": bucket,
            "sub": sub,
            "origin": origin,
            "transport": _transport_of(t, tr_fn),
            "in_qb": in_qb,
            "in_library": bool(rec.get("in_library")) if rec.get("in_library") is not None else None,
            "protected": is_prot,
            "protected_legacy": h in legacy,
            "protect_class": p_class,
            "protect_reason": str(why.get(h) or ""),
            "hr": {
                "owed": bool(is_hr),
                "owed_hr": bool(owed_hr),
                "need_left": str(owed.get(h) or ""),
            },
            "bill": ({
                "state": bill_state,
                "rule": bill_rule,
                "class": bill_class,
                "need_h": round(_as_float(bill.get("need_h")), 2),
                "seeded_h": round(_as_float(bill.get("seeded_h")), 2),
                "opened_by": str(bill.get("opened_by") or ""),
                "breached_at": bill.get("breached_at") or 0,
                **deadline,
            } if bill else None),
            "crossseed": bool(cs),
            "remain_min": remain_min,
            "need_hours": need_hours,
            "seeded_h": seeded_h,
            "age_h": age_h,
            "source": "crossseed" if (rec.get("crossseed") or cs) else "task",
            "taken_by": str(rec.get("taken_by") or ""),
            "reason": str(rec.get("reason") or ""),
            "fp": str(rec.get("fp") or ""),
            "rating": rec.get("rating"),
            "ledger_only": ledger_only,
            "qb_only": qb_only,
            # 便于消费方一次取齐（与 docs/AGENT-API.md §3.28 的 items 示例一致）
            "flags": {"site_deleted": site_deleted, "ledger_only": ledger_only,
                      "qb_only": qb_only},
        }
    return out


def default_bucket(bucket: str, sub: str, origin: str, transport: str,
                   row: Dict[str, Any]) -> str:
    """给一行算出「落进哪个视图」（供过滤/汇总复用，避免各处重算）。"""
    if bucket:
        return bucket
    if transport == TRANSPORT_ABSENT:
        return BUCKET_SILENT
    return BUCKET_SILENT


# --------------------------------------------------------------------------- 视图


def _rows_all(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = ctx.get("rows")
    if rows is None:
        rows = build_rows(ctx)
        ctx["rows"] = rows
    return list(rows.values())


def _site_list(ctx: Dict[str, Any], site: str) -> Dict[str, Any]:
    """站点解析：id/短名/域名 都能命中；空 = 未指定。"""
    s = str(site or "").strip()
    if not s:
        return {}
    idx = ctx.get("site_index") or {}
    return dict(idx.get(s.lower()) or {})


def _available_sites(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"id": it.get("id"), "name": it.get("name"), "domain": it.get("domain")}
            for it in (ctx.get("sites") or [])]


def _hr_block(ctx: Dict[str, Any], dom: str, live: int) -> Dict[str, Any]:
    rep: Dict[str, Any] = {}
    fn = ctx.get("site_hr_fn")
    if callable(fn) and dom:
        try:
            rep = dict(fn(dom, live, ctx.get("snap") or {}) or {})
        except Exception:  # noqa: BLE001
            rep = {}
    recs = list(rep.get("records") or [])
    missing = list(rep.get("missing_local") or [])
    return {
        "source": "live" if live else "cache",
        "ok": bool(rep.get("ok")),
        "partial": bool(rep.get("partial")),
        "error": str(rep.get("error") or ""),
        "records_total": int(rep.get("records_total") or 0),
        "missing": len(missing),
        "present_no_bill": len(rep.get("present_no_bill") or []),
        "hash_coverage_complete": bool(rep.get("hash_coverage_complete")),
        "records": recs,
        "_rep": rep,
    }


def _summary_of(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_bucket: Dict[str, int] = {}
    by_transport: Dict[str, int] = {}
    by_sub: Dict[str, int] = {}
    by_origin: Dict[str, int] = {}
    bucket_transport: Dict[str, Dict[str, int]] = {}
    silent_by_sub: Dict[str, int] = {}
    silent_origin: Dict[str, int] = {}
    total_size = 0.0
    prot_n = 0
    prot_hard = 0
    prot_soft = 0
    prot_any = 0
    for it in rows:
        b = str(it.get("bucket") or BUCKET_SILENT)
        tr = str(it.get("transport") or TRANSPORT_ABSENT)
        by_bucket[b] = by_bucket.get(b, 0) + 1
        by_transport[tr] = by_transport.get(tr, 0) + 1
        _bt = bucket_transport.setdefault(b, {})
        _bt[tr] = _bt.get(tr, 0) + 1
        sub = str(it.get("sub") or "")
        if sub:
            by_sub[sub] = by_sub.get(sub, 0) + 1
        org = str(it.get("origin") or ORIGIN_NONE)
        by_origin[org] = by_origin.get(org, 0) + 1
        if b == BUCKET_SILENT:
            s = sub or SUB_PLAIN
            silent_by_sub[s] = silent_by_sub.get(s, 0) + 1
            silent_origin[org] = silent_origin.get(org, 0) + 1
        total_size += _as_float(it.get("size_gb"))
        _pc = str(it.get("protect_class") or "")
        if _pc == "hard":
            prot_hard += 1
        elif _pc == "soft":
            prot_soft += 1
        if it.get("protected"):
            prot_any += 1
        if it.get("protected_legacy"):
            prot_n += 1
    return {
        "total": len(rows),
        "size_gb": round(total_size, 2),
        # ★ 17.3.0：``protected`` 与旧站点报表**逐位同口径**（= ``_site_report_protected()``）；
        #   硬/软分类单列（软保护 = 库内资产 / 同站纳管，可换出不可删）。
        "protected": prot_n,
        "protected_hard": prot_hard,
        "protected_soft": prot_soft,
        "protected_any": prot_any,
        "in_qb": sum(1 for r in rows if r.get("in_qb")),
        "ledger_only": sum(1 for r in rows if r.get("ledger_only")),
        "qb_only": sum(1 for r in rows if r.get("qb_only")),
        "hr_owed": sum(1 for r in rows if (r.get("hr") or {}).get("owed")),
        "hr": sum(1 for r in rows if (r.get("hr") or {}).get("owed_hr")),
        "non_hr": sum(1 for r in rows if not (r.get("hr") or {}).get("owed_hr")),
        "by_bucket": by_bucket,
        "by_transport": by_transport,
        "bucket_transport": bucket_transport,
        "by_sub": by_sub,
        "by_origin": by_origin,
        "silent_by_sub": silent_by_sub,
        "silent_origin": silent_origin,
    }


def view_site(ctx: Dict[str, Any], site: str = "", live: int = 0,
              limit: int = 0, offset: int = 0) -> Dict[str, Any]:
    """``view=site``：按站聚合全量（旧 ``/agent/site/seeds`` 口径，台账已收口）。"""
    at = str(ctx.get("at") or _now_iso())
    available = _available_sites(ctx)
    if not str(site or "").strip():
        return {"site": {}, "at": at, "live": bool(live), "summary": {"total": 0},
                "items": [], "hr": {}, "available_sites": available}
    info = _site_list(ctx, site)
    dom = _norm_dom(info.get("domain") or site)
    name = str(info.get("name") or "")
    rows = [r for r in _rows_all(ctx)
            if _norm_dom(r.get("site")) == dom or str(r.get("site_raw") or "").lower() == str(site).lower()
            or (name and _norm_dom(r.get("site")) == _norm_dom(name))]
    rows.sort(key=lambda x: (_bucket_by_order().get(str(x.get("bucket")), 99),
                             -_as_float(x.get("size_gb"))))
    summary = _summary_of(rows)
    hr = _hr_block(ctx, dom, live)
    rep = hr.pop("_rep", {})
    recs = list(rep.get("records") or [])
    hr_owed = len(recs) if recs else int(rep.get("records_total") or 0)
    # 账单侧（账本真值）：该站按 rule 分类的账单数
    bills_site: Dict[str, int] = {}
    for r in rows:
        b = r.get("bill") or {}
        if b:
            k = str(b.get("class") or BILL_CLASS_UNCLASSIFIED)
            bills_site[k] = bills_site.get(k, 0) + 1
    summary.update({
        "hr_owed": hr_owed,
        "hr_in_qb": sum(1 for r in recs if isinstance(r, dict) and r.get("in_qb")),
        "hr_missing": len(rep.get("missing_local") or []),
        "bills": bills_site,
    })
    hr.update({"bills": bills_site, "bills_total": sum(bills_site.values())})
    items = rows[:MAX_ITEMS]
    shown = items if _as_int(limit, 0) <= 0 else items[:_as_int(limit, 0)]
    return {
        "site": {"id": info.get("id"), "name": name, "domain": dom},
        "at": at, "live": bool(live), "summary": summary,
        "items": shown[_as_int(offset, 0):] if _as_int(offset, 0) else shown,
        "items_total": len(items), "items_truncated": max(0, len(items) - len(shown)),
        "hr": hr, "available_sites": available,
    }


def view_silent(ctx: Dict[str, Any], limit: int = 0, offset: int = 0) -> Dict[str, Any]:
    """``view=silent``：``bucket=静默`` 的行（旧 ``/agent/silent`` 的统计口径）。"""
    rows = [r for r in _rows_all(ctx) if str(r.get("bucket")) == BUCKET_SILENT]
    # 未下完排前面，其次按进池时间倒序（与旧实现一致）
    rows.sort(key=lambda x: (0 if _as_float(x.get("progress")) < 0.999 else 1,
                             -_as_float(x.get("age_h"))))
    by_sub: Dict[str, int] = {}
    sites: Dict[str, Dict[str, Any]] = {}
    hr_n = 0
    total_gb = 0.0
    incomplete = 0
    for it in rows:
        sub = str(it.get("sub") or SUB_NEW)
        site = str(it.get("site_name") or it.get("site") or "未知")
        ishr = bool((it.get("hr") or {}).get("owed_hr"))
        if _as_float(it.get("progress")) < 0.999:
            incomplete += 1
        hr_n += 1 if ishr else 0
        total_gb += _as_float(it.get("size_gb"))
        by_sub[sub] = int(by_sub.get(sub) or 0) + 1
        d = sites.setdefault(site, {"site": site, "total": 0, "hr": 0, "size_gb": 0.0})
        d["total"] += 1
        d["hr"] += 1 if ishr else 0
        d["size_gb"] = round(_as_float(d["size_gb"]) + _as_float(it.get("size_gb")), 2)
    sub_labels = {SUB_NEW: "静默-新", SUB_RESOURCE: "静默-资源", SUB_PLAIN: "静默-普通"}
    shown = rows if _as_int(limit, 0) <= 0 else rows[:_as_int(limit, 0)]
    if _as_int(offset, 0):
        shown = shown[_as_int(offset, 0):]
    summary = {
        "total": len(rows),
        "hr": hr_n,
        "non_hr": max(0, len(rows) - hr_n),
        "incomplete": incomplete,
        "size_gb": round(total_gb, 2),
        "protected": sum(1 for r in rows if r.get("protected_legacy")),
        "protected_hard": sum(1 for r in rows if str(r.get("protect_class")) == "hard"),
        "protected_soft": sum(1 for r in rows if str(r.get("protect_class")) == "soft"),
        "protected_any": sum(1 for r in rows if r.get("protected")),
        "in_qb": sum(1 for r in rows if r.get("in_qb")),
        "ledger_only": sum(1 for r in rows if r.get("ledger_only")),
        "qb_only": sum(1 for r in rows if r.get("qb_only")),
        "subs": [{"key": k, "label": sub_labels.get(k, k), "count": v}
                 for k, v in sorted(by_sub.items(), key=lambda kv: -kv[1])],
        "sites": sorted(sites.values(), key=lambda x: -int(x.get("total") or 0)),
    }
    return {"summary": summary, "items": shown,
            "items_truncated": max(0, len(rows) - len(shown)),
            "generated_at": _as_float(ctx.get("now"), time.time())}


def view_hr(ctx: Dict[str, Any], site: str = "", live: int = 0,
            limit: int = 0) -> Dict[str, Any]:
    """``view=hr``：H&R 账单按站分组（旧 ``/agent/hr/bills``，**未知规则不再丢弃**）。"""
    info = _site_list(ctx, site)
    dom_filter = _norm_dom(info.get("domain") or site) if str(site or "").strip() else ""
    snap = ctx.get("snap") or {}
    bills = ctx.get("bills") or {}
    idx = ctx.get("site_index") or {}
    sd: Dict[str, Any] = ctx.get("site_deleted") or {}
    reconcile = ctx.get("reconcile") or {}
    totals = {"sites": 0, "bills": 0, "total_bills": 0, "hr_rule": 0, "unclassified": 0,
              "active": 0, "pending": 0, "settled": 0, "void": 0, "breached": 0,
              "owed": 0, "missing": 0, "at_risk": 0}
    by_site: Dict[str, Dict[str, Any]] = {}

    def _bucket(dom: str) -> Dict[str, Any]:
        if dom in by_site:
            return by_site[dom]
        ent = idx.get(dom) or {}
        need_h = _as_float(ent.get("need_h"), 24.0)
        by_site[dom] = {
            "domain": dom, "name": str(ent.get("name") or dom),
            "per_torrent_hr": bool(ent.get("per_torrent_hr")),
            "hr_flag": ent.get("hr_flag"),
            "rule_source": str(ent.get("rule_source") or ""),
            "need_h": round(need_h, 1),
            "window_h": round(_as_float(ent.get("window_h")), 1),
            "site_deleted": (not bool(ent)) or bool(dom and dom in sd),
            "bills": {"total": 0, "hr_rule": 0, "unclassified": 0, "active": 0,
                      "pending": 0, "settled": 0, "void": 0, "breached": 0},
            "owed": 0, "in_qb": 0, "missing": 0, "at_risk": 0, "items": [],
        }
        return by_site[dom]

    for h, b in bills.items():
        if not isinstance(b, dict):
            continue
        dom = _norm_dom(b.get("site"))
        if not dom:
            dom = "(未知站点)"
        if dom_filter and dom != dom_filter:
            continue
        g = _bucket(dom)
        st = str(b.get("state") or "")
        rule = str(b.get("rule") or "")
        hh = str(h or "").strip().lower()
        in_qb = hh in snap
        cls = BILL_CLASS_HR if rule in _HR_RULES else BILL_CLASS_UNCLASSIFIED
        g["bills"]["total"] += 1
        totals["total_bills"] += 1
        totals["bills"] += 1
        if cls == BILL_CLASS_UNCLASSIFIED:
            g["bills"]["unclassified"] += 1
            totals["unclassified"] += 1
        else:
            g["bills"]["hr_rule"] += 1
            totals["hr_rule"] += 1
        if st in g["bills"]:
            g["bills"][st] += 1
        if st in totals:
            totals[st] += 1
        if in_qb:
            g["in_qb"] += 1
        if cls == BILL_CLASS_HR and st in (BILL_STATE_ACTIVE, BILL_STATE_BREACHED):
            g["owed"] += 1
            totals["owed"] += 1
        item = {
            "hash": hh, "title": str(b.get("title") or "")[:120],
            "state": st, "rule": rule, "class": cls,
            "seeded_h": round(_as_float(b.get("seeded_h")), 2),
            "need_h": round(_as_float(b.get("need_h")), 2),
            "in_qb": in_qb, "opened_by": str(b.get("opened_by") or ""),
            "breached_at": b.get("breached_at") or 0,
        }
        dfn = ctx.get("deadline_fn")
        if callable(dfn):
            try:
                item.update(dict(dfn(b) or {}))
            except Exception:  # noqa: BLE001
                pass
        g["items"].append(item)
        if item.get("at_risk"):
            g["at_risk"] += 1
            totals["at_risk"] += 1
    for dom in list(by_site.keys()):
        rep = {}
        get_report = getattr(reconcile, "get_report", None)
        if callable(get_report):
            try:
                rep = dict(get_report(dom) or {})
            except Exception:  # noqa: BLE001
                rep = {}
        missing = len(rep.get("missing_local") or [])
        by_site[dom]["missing"] = missing
        totals["missing"] += missing
        by_site[dom]["items"] = sorted(
            by_site[dom]["items"],
            key=lambda x: (0 if x["state"] in (BILL_STATE_ACTIVE, BILL_STATE_BREACHED) else 1),
        )
        if _as_int(limit, 0) > 0:
            by_site[dom]["items"] = by_site[dom]["items"][:_as_int(limit, 0)]
        else:
            by_site[dom]["items"] = by_site[dom]["items"][:200]
    sites = [by_site[k] for k in sorted(
        by_site, key=lambda d: (-by_site[d]["owed"], -by_site[d]["bills"]["total"]))]
    totals["sites"] = len(sites)
    margin_fn = ctx.get("margin_fn")
    warn_fn = ctx.get("warn_fn")
    return {
        "at": str(ctx.get("at") or _now_iso()),
        "live": bool(live),
        "totals": totals,
        "sites": sites,
        "policy": {
            "seed_margin_hours": round(_as_float(margin_fn() if callable(margin_fn) else 0.0), 2),
            "deadline_warn_hours": round(_as_float(warn_fn() if callable(warn_fn) else 0.0), 2),
            "settle_rule": "seeded_h >= need_h + seed_margin_hours",
            "at_risk_rule": "未达标 且 距站点考核窗口到期 ≤ deadline_warn_hours",
        },
        "source_of_truth": ["seed_ledger(mf_seed)", "hr_bills.json", "mf_resource",
                            "_tag_all_torrents()", "_site_rules()"],
        "write": {
            "void": "GET /tags?action=hrbills_void&hash=<h>&reason=..&confirm=1",
            "reconcile": "GET /agent/hr/reconcile?site=<dom>&live=1",
            "reseed_missing": "GET /tags?action=hr_reconcile&site=<dom>&confirm=1",
        },
    }


def view_rows(ctx: Dict[str, Any], view: str = "rows", site: str = "", state: str = "",
              bucket: str = "", sub: str = "", origin: str = "", transport: str = "",
              hr: str = "", protected: str = "", limit: int = 200,
              offset: int = 0) -> Dict[str, Any]:
    """``view=rows``：通用台账（过滤 + 汇总），是 site/silent/hr 的共同底座。"""
    info = _site_list(ctx, site)
    dom = _norm_dom(info.get("domain") or site) if str(site or "").strip() else ""
    hr_f = str(hr or "").strip().lower()
    prot_f = _opt_bool(protected)
    rows: List[Dict[str, Any]] = []
    for r in _rows_all(ctx):
        if dom and _norm_dom(r.get("site")) != dom:
            continue
        if state and str(r.get("lb_state") or r.get("state") or "") != state:
            continue
        if bucket and str(r.get("bucket") or "") != bucket:
            continue
        if sub and str(r.get("sub") or "") != sub:
            continue
        if origin and str(r.get("origin") or "") != origin:
            continue
        if transport and str(r.get("transport") or "") != transport:
            continue
        if prot_f is not None and bool(r.get("protected")) is not prot_f:
            continue
        if hr_f:
            bill = r.get("bill") or {}
            if hr_f in ("1", "欠", "hr"):
                if not (r.get("hr") or {}).get("owed"):
                    continue
            elif hr_f in ("unclassified", "未定性", "unknown"):
                if str(bill.get("class") or "") != BILL_CLASS_UNCLASSIFIED:
                    continue
            elif hr_f == "0":
                if (r.get("hr") or {}).get("owed"):
                    continue
            elif hr_f in ("有",):
                if not bill:
                    continue
            else:
                continue
        rows.append(r)
    rows.sort(key=lambda x: (_bucket_by_order().get(str(x.get("bucket")), 99),
                             -_as_float(x.get("size_gb"))))
    total = len(rows)
    shown = rows if _as_int(limit, 0) <= 0 else rows[:_as_int(limit, 0)]
    if _as_int(offset, 0):
        shown = shown[_as_int(offset, 0):]
    return {
        "view": "rows",
        "at": str(ctx.get("at") or _now_iso()),
        "filters": {"site": info.get("domain") or site, "state": state, "bucket": bucket,
                    "sub": sub, "origin": origin, "transport": transport,
                    "hr": hr, "protected": protected},
        "summary": _summary_of(rows),
        "items": shown,
        "items_total": total,
        "items_truncated": max(0, total - len(shown)),
    }


def view_any(ctx: Dict[str, Any], view: str = "site", **kw: Any) -> Dict[str, Any]:
    """统一入口分派（``site`` / ``silent`` / ``hr`` / ``rows``）。"""
    v = str(view or "site").strip().lower()
    if v == "site":
        return view_site(ctx, site=kw.get("site", ""), live=_as_int(kw.get("live"), 0),
                         limit=_as_int(kw.get("limit"), 0), offset=_as_int(kw.get("offset"), 0))
    if v == "silent":
        return view_silent(ctx, limit=_as_int(kw.get("limit"), 0),
                           offset=_as_int(kw.get("offset"), 0))
    if v == "hr":
        return view_hr(ctx, site=kw.get("site", ""), live=_as_int(kw.get("live"), 0),
                       limit=_as_int(kw.get("limit"), 0))
    return view_rows(ctx, view=v, site=kw.get("site", ""), state=kw.get("state", ""),
                     bucket=kw.get("bucket", ""), sub=kw.get("sub", ""),
                     origin=kw.get("origin", ""), transport=kw.get("transport", ""),
                     hr=kw.get("hr", ""), protected=kw.get("protected", ""),
                     limit=_as_int(kw.get("limit"), 200), offset=_as_int(kw.get("offset"), 0))


# --------------------------------------------------------------------------- 互校


def drift(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """**互校报告**：账本 × 下载器 × MP 站点清单 × 账单 四向对齐（只读，只报不改）。"""
    ledger = ctx.get("ledger") or {}
    snap = ctx.get("snap") or {}
    bills = ctx.get("bills") or {}
    rows = ctx.get("rows")
    if rows is None:
        rows = build_rows(ctx)
        ctx["rows"] = rows
    led_h = {str(h).lower() for h in ledger}
    qb_h = {str(h).lower() for h in snap}
    ledger_only = sorted(led_h - qb_h)
    qb_only = sorted(qb_h - led_h)
    idx = ctx.get("site_index") or {}
    sd: Dict[str, Any] = ctx.get("site_deleted") or {}
    by_site: Dict[str, Dict[str, Any]] = {}
    missing_sites: Dict[str, Dict[str, Any]] = {}
    for h, r in rows.items():
        key = _norm_dom(r.get("site")) or "(无站点)"
        d = by_site.setdefault(key, {"rows": 0, "size_gb": 0.0, "ledger_only": 0,
                                     "qb_only": 0, "protected": 0, "protected_hard": 0,
                                     "protected_soft": 0, "protected_any": 0})
        d["rows"] += 1
        d["size_gb"] = round(_as_float(d["size_gb"]) + _as_float(r.get("size_gb")), 2)
        d["ledger_only"] += 1 if r.get("ledger_only") else 0
        d["qb_only"] += 1 if r.get("qb_only") else 0
        # ★ 与 summary 同一口径：protected = 旧站点报表口径（legacy），另三档才是新分档
        d["protected"] += 1 if r.get("protected_legacy") else 0
        d["protected_any"] += 1 if r.get("protected") else 0
        _pc = str(r.get("protect_class") or "")
        d["protected_hard"] += 1 if _pc == "hard" else 0
        d["protected_soft"] += 1 if _pc == "soft" else 0
        if key not in idx and key != "(无站点)":
            m = missing_sites.setdefault(key, {**d, "site": key, "site_deleted": True})
            m.update(d)
    # ★ 17.5.0：只剩残留（账单/账本）而**台账行已经没了**的已删站也要进互校——
    #   旧口径只遍历台账行 ⇒ 这类站完全隐形（现场：hdfans.org 台账行已删、账单剩 46 条，
    #   旧互校/旧 /agent/sites/deleted 都报 0）。
    for _dom, _ent in (sd or {}).items():
        if not _dom or _dom == "(无站点)" or _dom in by_site or _dom in missing_sites:
            continue
        missing_sites[_dom] = {
            "rows": 0, "size_gb": 0.0, "ledger_only": 0, "qb_only": 0,
            "protected": 0, "protected_hard": 0, "protected_soft": 0, "protected_any": 0,
            "site": _dom, "site_deleted": True,
            "reason": str((_ent or {}).get("reason") or ""),
            "bills": int((_ent or {}).get("bills") or 0),
            "has_row": bool((_ent or {}).get("has_row")),
            "refs": list((_ent or {}).get("refs") or []),
        }
    mp_sites = {_norm_dom(it.get("domain") or it.get("name"))
                for it in (ctx.get("sites") or []) if (it.get("domain") or it.get("name"))}
    silent_n = sum(1 for r in rows.values() if str(r.get("bucket")) == BUCKET_SILENT)
    hr_rule = sum(1 for b in bills.values()
                  if isinstance(b, dict) and str(b.get("rule") or "") in _HR_RULES)
    checks: List[Dict[str, Any]] = []

    def _chk(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    _chk("账单全覆盖", sum(1 for b in bills.values() if isinstance(b, dict)) == hr_rule + (
        sum(1 for b in bills.values() if isinstance(b, dict)) - hr_rule),
         f"账单 {len(bills)} = 有义务 {hr_rule} + 未定性 {len(bills) - hr_rule}")
    _chk("视图总数 = 台账", len(rows) == sum(d["rows"] for d in by_site.values()),
         f"台账 {len(rows)} 行")
    _chk("静默视图 = 静默桶", silent_n == sum(
        1 for r in rows.values() if str(r.get("bucket")) == BUCKET_SILENT),
         f"静默 {silent_n} 行")
    _chk("幽灵行不带传输态", all(str(r.get("transport")) == TRANSPORT_ABSENT
                                for r in rows.values() if r.get("ledger_only")),
         f"ledger_only {len(ledger_only)} 行")
    _chk("下载器未纳管可枚举", True, f"qb_only {len(qb_only)} 行")
    return {
        "at": str(ctx.get("at") or _now_iso()),
        "ledger": {"rows": len(rows), "in_qb": len(qb_h & led_h), "ghost": len(ledger_only),
                   "sites": len(by_site)},
        "downloader": {"tagged": len(qb_h)},
        "drift": {"counts": {"ledger_only": len(ledger_only), "qb_only": len(qb_only)},
                  "ledger_only": ledger_only[:200], "qb_only": qb_only[:200]},
        "sites": {
            "by_site": sorted(by_site.items(), key=lambda kv: -kv[1]["rows"]),
            "missing_from_mp": sorted(missing_sites.values(), key=lambda x: -x["rows"]),
            "mp_only": sorted(s for s in mp_sites if s and s not in by_site),
        },
        "views": {
            "ledger_rows": len(rows),
            "silent": silent_n,
            "hr_bills": len(bills),
            "site_views": len(by_site),
            "checks": checks,
        },
        "hr": {"bills": len(bills), "hr_rule": hr_rule,
               "unclassified": len(bills) - hr_rule,
               "sites": len({_norm_dom(b.get("site")) for b in bills.values()
                             if isinstance(b, dict) and b.get("site")})},
        "generated_at": _as_float(ctx.get("now"), time.time()),
    }


# --------------------------------------------------------------------------- 端点


class ReportViewMixin:
    """报表唯一口径（★ 17.3.0）：``/agent/report`` + ``/agent/report/drift``。

    三个旧端点（``/agent/site/seeds``、``/agent/silent``、``/agent/hr/bills``）
    全部改为调用本 mixin 的投影，字段结构不变、数字从此一致。
    """

    # ------------------------------------------------- 采集（只读，一次）
    def _rv_call(self, name: str, *a: Any, **kw: Any) -> Any:
        fn = getattr(self, name, None)
        if not callable(fn):
            return None
        try:
            return fn(*a, **kw)
        except Exception:  # noqa: BLE001
            return None

    def _rv_context(self) -> Dict[str, Any]:
        """采集一次（全部只读）：账本 / 快照 / 账单 / 站点 / 保护 / 辅助账。"""
        snap = self._rv_call("_site_report_snapshot") or {}
        if not isinstance(snap, dict):
            snap = {}
        ledger: Dict[str, Any] = {}
        try:
            store = self._rv_call("_tag_state")
            ledger = dict(store.items() or {}) if store is not None else {}
        except Exception:  # noqa: BLE001
            ledger = {}
        bills: Dict[str, Any] = {}
        try:
            bstore = self._rv_call("_site_report_bills_store")
            bills = dict(bstore.all() or {}) if bstore is not None else {}
        except Exception:  # noqa: BLE001
            bills = {}
        try:
            rules = self._rv_call("_site_rules") or {}
            rule_items = dict((rules.get("items") or {})) if isinstance(rules, dict) else {}
        except Exception:  # noqa: BLE001
            rule_items = {}
        sites: List[Dict[str, Any]] = []
        try:
            sites = list((self._rv_call("_site_report_resolve", "") or {}).get("sites") or [])
        except Exception:  # noqa: BLE001
            sites = []
        site_index: Dict[str, Dict[str, Any]] = {}
        site_rows: List[Dict[str, Any]] = []
        for it in sites:
            if not isinstance(it, dict):
                continue
            dom = _norm_dom(it.get("domain"))
            name = str(it.get("name") or "")
            rec = dict(rule_items.get(dom) or {})
            ent = {
                "id": it.get("id"), "name": name, "domain": dom,
                "hr_flag": self._rv_call("_site_hr_flag", dom),
                "per_torrent_hr": bool(self._rv_call("_site_per_torrent_hr", dom) or False),
                "need_h": _as_float(rec.get("seed_hours"), 24.0),
                "window_h": _as_float(self._rv_call("_hr_window_hours", dom), 0.0),
                "rule_source": str(rec.get("source") or ""),
            }
            site_rows.append(ent)
            for k in (dom, name, str(it.get("id") or "")):
                if k:
                    site_index.setdefault(str(k).lower(), ent)
            # ★ 17.3.0：账本短名常是「注册域」（``btschool.club``），MP 域名带子域
            #   （``pt.btschool.club``）——把逐级后缀也注册进来，两个名字才落到同一行。
            _parts = dom.split(".") if dom else []
            for _i in range(1, max(0, len(_parts) - 1)):
                site_index.setdefault(".".join(_parts[_i:]), ent)
        reseed: set = set()
        try:
            for k in (self._rv_call("_reseed_ledger") or {}):
                reseed.add(str(k).split(":", 1)[-1].lower())
        except Exception:  # noqa: BLE001
            reseed = set()
        cssrc: Dict[str, Any] = {}
        try:
            cssrc = dict(self._rv_call("_crossseed_sources") or {})
        except Exception:  # noqa: BLE001
            cssrc = {}
        # ★ 17.3.0：保护是**每任务一份**（protection.py 契约），报表要的是并集。
        #   只传 None 会退化成「历史空 task_id 桶」→ 实测 protected=0
        #   （旧站点报表同期显示 dstudio 19 / 财神 12 / March 12 / CARPT 4）。
        prot: Dict[str, Any] = {"hard": set(), "soft": set(), "incomplete": set(), "why": {}}
        try:
            _tasks: List[Any] = list((getattr(self, "_task_configs", None) or {}).values()) + [None]
            for _task in _tasks:
                wired = self._rv_call("_protection_sets", _task, None, None, snap) or {}
                for _k in ("hard", "soft", "incomplete"):
                    prot[_k] |= {str(x).strip().lower() for x in (wired.get(_k) or ()) if x}
                for _h, _w in dict(wired.get("why") or {}).items():
                    if _h:
                        prot["why"].setdefault(str(_h).strip().lower(), str(_w))
        except Exception:  # noqa: BLE001
            pass
        if not prot["hard"] and not prot["soft"]:
            try:  # 兜底：与旧站点报表同源（store 层保护集合，跨任务并集）
                prot["hard"] = {str(x).strip().lower()
                                for x in (self._rv_call("_site_report_protected") or ()) if x}
            except Exception:  # noqa: BLE001
                pass
        # ★ 17.3.0 兼容：旧 ``/agent/site/seeds.protected`` 的口径就是
        #   ``_site_report_protected()``（手动保留 ∪ H&R ∪ 未完成 ∪ 认领），
        #   与 ``_protection_sets`` 的 hard 差一个「同站纳管（已移入 soft）」；
        #   这里单独留一份 legacy 集合，保证旧数字**逐位不变**。
        try:
            prot["legacy"] = {str(x).strip().lower()
                              for x in (self._rv_call("_site_report_protected") or ()) if x}
        except Exception:  # noqa: BLE001
            prot["legacy"] = set()
        # 站点级欠账（对账缓存只读）：infohash → need_left
        owed: Dict[str, str] = {}
        reconcile = self._rv_call("_hr_reconcile_cache")
        get_report = getattr(reconcile, "get_report", None)
        if callable(get_report):
            for ent in site_rows:
                try:
                    rep = dict(get_report(ent.get("domain")) or {})
                except Exception:  # noqa: BLE001
                    rep = {}
                for r in (rep.get("records") or []):
                    if not isinstance(r, dict):
                        continue
                    hh = str(r.get("infohash") or "").strip().lower()
                    if hh:
                        owed[hh] = str(r.get("need_left") or "")
        try:
            known = set(self._rv_call("_tag_site_names") or ())
        except Exception:  # noqa: BLE001
            known = set()
        # ★ 17.5.0：已删站真值源（与 H8 / 通知 / /agent/sites/deleted 共用**同一份**，不再各算各的）
        try:
            from .siteops import site_deleted_domains
            site_deleted = site_deleted_domains(self)
        except Exception:  # noqa: BLE001
            site_deleted = {}
        return {
            "at": _now_iso(), "now": time.time(),
            "ledger": ledger, "snap": snap, "bills": bills,
            "sites": sites, "site_rows": site_rows, "site_index": site_index,
            "protected": prot, "reseed": reseed, "crossseed": cssrc,
            "owed": owed, "known_sites": known, "reconcile": reconcile,
            "site_deleted": site_deleted,
            "transport_fn": getattr(self, "_site_report_transport", None),
            "sub_fn": getattr(self, "_site_report_sub", None),
            "bucket_fn": getattr(self, "_site_report_bucket", None),
            "reuse_fn": getattr(self, "_site_report_reuse", None),
            "site_of_fn": getattr(self, "_site_report_torrent_site", None),
            "deadline_fn": getattr(self, "_hr_deadline", None),
            "hr_obligation_fn": getattr(self, "_hr_obligation", None),
            "site_hr_fn": getattr(self, "_site_report_hr", None),
            "margin_fn": getattr(self, "_hr_margin_hours", None),
            "warn_fn": getattr(self, "_hr_warn_hours", None),
        }

    def _rv_ctx(self) -> Dict[str, Any]:
        """带缓存的采集（同一次请求内多视图复用）。"""
        ctx = getattr(self, "_rv_ctx_cache", None)
        if not isinstance(ctx, dict):
            ctx = self._rv_context()
            self._rv_ctx_cache = ctx
        return ctx

    def _rv_reset(self) -> None:
        """让下一次 ``_rv_ctx`` 重新采集（写动作后调用；报表本身不写）。"""
        self._rv_ctx_cache = None

    def _rv_rows(self) -> Dict[str, Dict[str, Any]]:
        ctx = self._rv_ctx()
        rows = ctx.get("rows")
        if rows is None:
            rows = build_rows(ctx)
            ctx["rows"] = rows
        return rows

    # ------------------------------------------------- 旧三面兼容投影
    def _rv_site_data(self, site: str = "", live: int = 0, limit: int = 0) -> Dict[str, Any]:
        return view_site(self._rv_ctx(), site=site, live=live, limit=limit)

    def _rv_hr_data(self, site: str = "", live: int = 0, limit: int = 0) -> Dict[str, Any]:
        return view_hr(self._rv_ctx(), site=site, live=live, limit=limit)

    def _rv_silent_data(self, limit: Any = 400, records: Any = 60) -> Dict[str, Any]:
        """旧静默池视图（统计口径来自台账；host/records/settings 仍为运营细节）。"""
        # 「显式 0」与「缺省」分开（2026-10-14）：limit=0 → 全部；records=0 → 不带明细。
        _raw = str(limit if limit is not None else "").strip()
        _limit = _as_int(_raw, 400) if _raw else 400
        if _limit < 0:
            _limit = 400
        _rraw = str(records if records is not None else "").strip()
        _rlimit = _as_int(_rraw, 60) if _rraw else 60
        if _rlimit < 0:
            _rlimit = 60
        ctx = self._rv_ctx()
        data = view_silent(ctx, limit=_limit)
        now = _as_float(ctx.get("now"), time.time())
        try:
            host_min = float(getattr(self, "_tags_cfg", {}).get("host_interval")
                             or getattr(self, "SILENT_HOST_INTERVAL_MINUTES", 0) or 0)
        except Exception:  # noqa: BLE001
            host_min = 0.0
        try:
            new_timeout_h = float(self._tags_cfg.get("new_timeout") or 0) / 3600.0
        except Exception:  # noqa: BLE001
            new_timeout_h = 0.0
        last = float(getattr(self, "_silent_host_last", 0) or 0)
        recs: List[Dict[str, Any]] = []
        if _rlimit > 0:
            try:
                rows = self._store.journal.list_by_task(
                    getattr(self, "SILENT_HOST_TASK_ID", ""), limit=_rlimit) or []
                for r in rows:
                    try:
                        d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
                    except Exception:  # noqa: BLE001
                        continue
                    ts = float(d.get("ts") or d.get("created_at") or d.get("resolved_at") or 0)
                    if ts > last:
                        last = ts
                    recs.append({
                        "ts": ts, "kind": str(d.get("kind") or ""),
                        "count": int(d.get("count") or len(d.get("items") or []) or 0),
                        "reason": str(d.get("reason") or d.get("message") or ""),
                        "duration_ms": d.get("duration_ms") or d.get("duration") or 0,
                        "items": (d.get("items") or [])[:6],
                    })
            except Exception:  # noqa: BLE001
                recs = []
        hr_default = 0.0
        try:
            hr_default = float(getattr(self, "_cs_cfg", {}).get("seed_hours_default") or 0.0)
        except Exception:  # noqa: BLE001
            hr_default = 0.0
        data["records"] = recs
        data["host"] = {
            "interval_minutes": round(host_min, 1),
            "last_run": (time.strftime("%m-%d %H:%M", time.localtime(last)) if last else "—"),
            "last_run_ts": last,
        }
        data["settings"] = {"new_timeout_hours": round(new_timeout_h, 2),
                            "hr_default_hours": hr_default}
        data["generated_at"] = now
        return data

    # ------------------------------------------------- 统一入口
    def _rv_validate(self, view: str, state: str, bucket: str, sub: str, origin: str,
                     transport: str, hr: str, protected: str) -> tuple:
        """校验入参：返回 ``(错误说明, 字段名)``；通过 = ``("", "")``。

        ★ 17.3.0：非法参数一律**报错**（旧三面里 ``site``/``state`` 被静默忽略，模型据此
        以为「查了 A 站」其实是全站——这是最误导的一类偏差）。
        """
        if str(view or "site").strip().lower() not in RV_VIEWS:
            return f"view 只支持 {'|'.join(RV_VIEWS)}", "view"
        if bucket and bucket not in _BUCKET_ORDER:
            return f"bucket 只支持 {'|'.join(_BUCKET_ORDER)}", "bucket"
        if sub and sub not in SILENT_SUBS:
            return f"sub 只支持 {'|'.join(SILENT_SUBS)}", "sub"
        if origin and origin not in _ORIGIN_ORDER:
            return f"origin 只支持 {'|'.join(_ORIGIN_ORDER)}", "origin"
        if transport and transport not in _ALL_TRANSPORT:
            return f"transport 只支持 {'|'.join(_ALL_TRANSPORT)}", "transport"
        if hr and str(hr).strip().lower() not in RV_HR_FILTERS:
            return f"hr 只支持 {'|'.join(RV_HR_FILTERS)}", "hr"
        if protected not in ("", None) and str(protected).strip().lower() not in (
                "0", "1", "true", "false", "yes", "no", "欠", "有"):
            return "protected 只支持 0|1", "protected"
        if state and state not in (STATE_BRUSH, STATE_BONUS, STATE_HR, STATE_SILENT):
            return f"state 只支持 {STATE_BRUSH}|{STATE_BONUS}|{STATE_HR}|{STATE_SILENT}", "state"
        return "", ""

    def get_report(self, view: str = "site", site: str = "", state: str = "", bucket: str = "",
                   sub: str = "", origin: str = "", transport: str = "", hr: str = "",
                   protected: str = "", limit: Any = 200, offset: Any = 0,
                   live: Any = 0) -> Response:
        """``GET /agent/report`` —— ★ **报表统一入口**（只读）。

        一行 = 一颗种；真值源 = 账本；下载器只补传输态。``view`` 选投影：
        ``site``（按站全量）/ ``silent``（静默池）/ ``hr``（H&R 账单）/ ``rows``（通用台账）。
        参数非法一律报错（不再静默忽略）；``limit=0`` = 全部。
        """
        try:
            bad, field = self._rv_validate(view, state, bucket, sub, origin, transport,
                                           hr, protected)
            if bad:
                return Response(success=False, message=bad,
                                data={"bad_param": True, "field": field})
            limit_i = _as_int(limit, 200)
            offset_i = max(0, _as_int(offset, 0))
            data = view_any(self._rv_ctx(), view=view, site=site, state=state, bucket=bucket,
                            sub=sub, origin=origin, transport=transport, hr=hr,
                            protected=protected, limit=limit_i, offset=offset_i,
                            live=_as_int(live, 0))
            data["params"] = {"view": str(view or "site").lower(), "site": site,
                              "state": state, "bucket": bucket, "sub": sub, "origin": origin,
                              "transport": transport, "hr": hr, "protected": protected,
                              "limit": limit_i, "offset": offset_i}
            return Response(success=True, message="ok", data=data)
        except Exception as e:  # noqa: BLE001
            self._log(f"统一报表失败: {e}", "error")
            return Response(success=False, message=str(e))

    def get_report_drift(self) -> Response:
        """``GET /agent/report/drift`` —— 台账 × 下载器 × MP 站点 × 账单 互校（只读）。"""
        try:
            data = drift(self._rv_ctx())
            return Response(success=True, message="ok", data=data)
        except Exception as e:  # noqa: BLE001
            self._log(f"报表互校失败: {e}", "error")
            return Response(success=False, message=str(e))
