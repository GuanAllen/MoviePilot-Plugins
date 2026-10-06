# -*- coding: utf-8 -*-
"""魔流 · 站点/能力/跨站来源 三套账本 → 5 表（12.1.0 WS2 桥接层）。

把仅剩的三套「账本型 kv」迁进表，让 **表 = 唯一真值源**，kv 里这三个键彻底消失：

    site_rules (16)        → mf_site 现有真列 + 3 新列（note/exam_evidence/per_torrent_hr）
                             + rules_extra(JSON) 兜底（映射后仍未覆盖的键）
    site_caps (15)         → mf_site.caps（新 JSON 列，整条 cap rec）
    sitecap_override       → mf_site.caps 的 ``__override__`` 子槽（人工覆盖，空=无覆盖）
    crossseed_sources (2)  → 新表 mf_crossseed（+ extra JSON 兜底）

对外只暴露一个**同签名**的存储对象 ``SiteStore``，``get(slot)/save(slot, value)`` 的
槽名语义与旧 kv 键一一对应，供 `sites/rules.py::SiteRules`、`sitecap.py::SiteCapRegistry`、
`crossseed.py::CrossSeedSources` 把 kv 回调换成表回调。

★ 单例：用模块级工厂 `get_site_store(plugin)`（照 `persistence.get_gate_store` 那套
``_shared()`` 注册表模式），**不要**挂到 ``stores()`` 上 —— 热重载不重建，会拿到旧类。
只经 `ledger.LedgerBackend` 拿 session；写操作沿用 ``backend._lock`` 加锁。
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from . import db as mfdb
from .kvstore import cache_get
from .common import CACHE_TTL_REPORT
from .ledger import get_backend
from .persistence import _shared

# ---------------------------------------------------------------------------
# 槽名（内部标识，与旧 kv 键同名）
# ---------------------------------------------------------------------------
SLOT_SITE_RULES = "site_rules"
SLOT_SITE_CAPS = "site_caps"
SLOT_SITECAP_OVERRIDE = "sitecap_override"
SLOT_CROSSSEED_SOURCES = "crossseed_sources"
# ★ 12.2.0：剩余 kv 收口（站点面 + 种子面 + 运行态）
SLOT_RESEED_LEDGER = "reseed_ledger"
SLOT_SIGNIN_LAST_FULL = "signin_last_full"
SLOT_SIGNIN_RETRY = "signin_retry"
SLOT_SIGNIN_KEEPALIVE = "signin_keepalive"
SLOT_CLAIM_PROFILE = "claim_profile"
SLOT_RESCUE_STALL = "rescue_stall"
SLOT_ONDEMAND_PENDING = "ondemand_pending"
SLOT_CROSSSEED_PENDING = "crossseed_pending"
SLOT_PV_BUDGET = "pv_budget"
SLOT_LIVE_PV_BLOCK = "live_pv_block"
SLOT_LIVE_ALERTS = "live_alerts"
SLOT_PV_USAGE = "pv_usage"
SLOT_SIGNIN_RECORDS = "signin_records"
SLOT_IYUU_SITES = "iyuu_sites"
SLOT_RESEED_PASSKEYS = "reseed_passkeys"
# ★ 12.2.0 subG：漏网的运行账本/状态（claim 账本 + 全局运行标量）
SLOT_CLAIM_LEDGER = "claim_ledger"
SLOT_KEEPALIVE_ALERT_DAY = "keepalive_alert_day"
SLOT_CROSSSEED_BAN = "crossseed_ban"
SLOTS: Tuple[str, ...] = (
    SLOT_SITE_RULES, SLOT_SITE_CAPS, SLOT_SITECAP_OVERRIDE, SLOT_CROSSSEED_SOURCES,
    SLOT_RESEED_LEDGER, SLOT_SIGNIN_LAST_FULL, SLOT_SIGNIN_RETRY, SLOT_SIGNIN_KEEPALIVE,
    SLOT_CLAIM_PROFILE, SLOT_RESCUE_STALL, SLOT_ONDEMAND_PENDING, SLOT_CROSSSEED_PENDING,
    SLOT_PV_BUDGET, SLOT_LIVE_PV_BLOCK, SLOT_LIVE_ALERTS, SLOT_PV_USAGE,
    SLOT_SIGNIN_RECORDS, SLOT_IYUU_SITES, SLOT_RESEED_PASSKEYS,
    SLOT_CLAIM_LEDGER, SLOT_KEEPALIVE_ALERT_DAY, SLOT_CROSSSEED_BAN,
)

# mf_site.credential 里保留的子槽键（密文/凭据；不以 ``_`` 开头是站点自填字段，避免撞名）
_CRED_IYUU = "__iyuu__"
_CRED_RESEED_PK = "__reseed_passkey__"
# mf_site.caps 里保留的「认领能力」子槽键
_CAPS_CLAIM = "__claim__"

# ---------------------------------------------------------------------------
# 映射表（rec 键 → 列名；键名 = 列名，此处只列「能映射到真列」的键）
# ---------------------------------------------------------------------------
# site_rules → mf_site 真列（§2.1；``domain``=行键、``updated``=now/rec 值，不在此列）
_RULE_COLUMNS: Tuple[str, ...] = (
    "hr", "hr_src", "framework", "seed_hours", "seed_hours_retired", "seed_need_hours",
    "seed_cap", "seed_window_hours", "exam_avg_hours", "free_over_gb",
    "free_original", "free_ep1", "source", "confidence", "evidence",
    "probed_at", "rule_url", "rule_label", "rule_src", "rule_mail_id",
    "rule_mail_subject", "name", "note", "exam_evidence", "per_torrent_hr",
)

# 判断「这一行是不是规则记录」的标记列（不含 name/domain/updated，避免把纯站点/纯预算行当规则）
_RULE_MARKER_COLUMNS: Tuple[str, ...] = (
    "hr", "hr_src", "seed_hours", "seed_hours_retired", "seed_need_hours",
    "seed_cap", "seed_window_hours", "exam_avg_hours", "free_over_gb",
    "free_original", "free_ep1", "source", "confidence", "evidence",
    "probed_at", "rule_url", "rule_label", "rule_src", "rule_mail_id",
    "rule_mail_subject", "note", "exam_evidence", "per_torrent_hr",
)

# crossseed_sources → mf_crossseed 真列（§2.3；``sib_hash``=主键、``updated``=now/rec）
_CROSSSEED_COLUMNS: Tuple[str, ...] = (
    "site_b_domain", "site_a", "site_b", "a_hash", "title", "size_gb",
    "hit_and_run", "hours", "seed_until", "downloader", "seeded_sec",
    "files_shared", "task_id", "task_name", "backfilled", "done", "created",
)

# mf_site.caps 里保留的「override 子槽」键（人工覆盖；不以 ``_`` 开头，避免与 cap 字段撞名）
_OVERRIDE_SUBKEY = "__override__"


def _norm_domain(domain: str) -> str:
    """域名归一（与旧 kv 键口径一致：小写、去协议、去尾斜杠）。"""
    s = str(domain or "").strip().lower()
    s = s.replace("https://", "").replace("http://", "").strip("/")
    return s


def _norm_hash(hash_string: str) -> str:
    return str(hash_string or "").strip().lower()


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# 纯映射函数（离线单测直接验这层，不必连真库）
# ---------------------------------------------------------------------------
def rec_to_site_columns(domain: str, rec: Dict[str, Any], now: float) -> Dict[str, Any]:
    """``site_rules`` 一条 rec → mf_site 列值（含 ``rules_extra`` 兜底）。"""
    cols: Dict[str, Any] = {"domain": _norm_domain(domain)}
    extra: Dict[str, Any] = {}
    for k, v in (rec or {}).items():
        if k == "domain" or k == "updated":
            continue
        if k in _RULE_COLUMNS:
            cols[k] = v
        else:
            extra[k] = v
    cols["rules_extra"] = extra if extra else None
    cols["updated"] = rec.get("updated") if rec.get("updated") is not None else now
    return cols


def site_columns_to_rec(domain: str, cols: Dict[str, Any]) -> Dict[str, Any]:
    """mf_site 列值 → ``site_rules`` rec（反向拼回 dict，含 ``domain``/``updated``）。"""
    rec: Dict[str, Any] = {"domain": _norm_domain(domain)}
    for k in _RULE_COLUMNS:
        v = cols.get(k)
        if v is not None:
            rec[k] = v
    extra = cols.get("rules_extra")
    if isinstance(extra, dict) and extra:
        for k, v in extra.items():
            rec.setdefault(k, v)
    if cols.get("updated") is not None:
        rec["updated"] = cols["updated"]
    return rec


def rec_to_crossseed_columns(sib_hash: str, rec: Dict[str, Any], now: float) -> Dict[str, Any]:
    """``crossseed_sources`` 一条 rec → mf_crossseed 列值（含 ``extra`` 兜底）。"""
    cols: Dict[str, Any] = {"sib_hash": _norm_hash(sib_hash)}
    extra: Dict[str, Any] = {}
    for k, v in (rec or {}).items():
        if k == "sib_hash" or k == "updated":
            continue
        if k in _CROSSSEED_COLUMNS:
            cols[k] = v
        else:
            extra[k] = v
    cols["extra"] = extra if extra else None
    cols["updated"] = rec.get("updated") if rec.get("updated") is not None else now
    return cols


def crossseed_columns_to_rec(sib_hash: str, cols: Dict[str, Any]) -> Dict[str, Any]:
    """mf_crossseed 列值 → ``crossseed_sources`` rec（反向拼回 dict）。"""
    rec: Dict[str, Any] = {"sib_hash": _norm_hash(sib_hash)}
    for k in _CROSSSEED_COLUMNS:
        v = cols.get(k)
        if v is not None:
            rec[k] = v
    extra = cols.get("extra")
    if isinstance(extra, dict) and extra:
        for k, v in extra.items():
            rec.setdefault(k, v)
    if cols.get("updated") is not None:
        rec["updated"] = cols["updated"]
    return rec


# ---------------------------------------------------------------------------
# 纯映射函数（12.2.0）：pv_usage / signin_records 的「按日期 ↔ 按站点」重组
# ---------------------------------------------------------------------------
def by_date_to_by_site(value: Dict[str, Any]) -> Dict[str, Any]:
    """``{date: {site_id: {...}}}`` → ``{site_id: {date: {...}}}``（无损，含未知子键）。

    site_id 键原样保留（字符串）；非 dict 的叶子按原样带上。
    """
    out: Dict[str, Any] = {}
    for date, bucket in (value or {}).items():
        if not isinstance(bucket, dict):
            continue
        for sid, rec in bucket.items():
            out.setdefault(str(sid), {})[str(date)] = rec
    return out


def by_site_to_by_date(value: Dict[str, Any]) -> Dict[str, Any]:
    """``{site_id: {date: {...}}}`` → ``{date: {site_id: {...}}}``（``by_date_to_by_site`` 的逆）。"""
    out: Dict[str, Any] = {}
    for sid, days in (value or {}).items():
        if not isinstance(days, dict):
            continue
        for date, rec in days.items():
            out.setdefault(str(date), {})[str(sid)] = rec
    return out


def _int_ok(v: Any) -> bool:
    try:
        return int(v) > 0
    except (TypeError, ValueError):
        return False


def _float_ok(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False




# ---------------------------------------------------------------------------
# SiteStore
# ---------------------------------------------------------------------------
class SiteStore:
    """三套站点/来源 kv 账本 → 表。``get/save`` 语义与 kv 槽一一对应。"""

    def __init__(self, backend: Any) -> None:
        self._backend = backend
        self._plugin: Any = None
        self._site_hints: Dict[str, Any] = {}

    def bind(self, backend: Any) -> None:
        """重绑后端（热重载后拿到新 backend，仍是同一个 store 实例）。"""
        self._backend = backend

    def bind_plugin(self, plugin: Any) -> None:
        """记住 plugin（★ 站点 id → 名称/域名 解析用，避免造无名垃圾站点行）。"""
        if plugin is not None:
            self._plugin = plugin

    @property
    def _lock(self):
        return getattr(self._backend, "_lock", None)

    @property
    def _session(self):
        return self._backend._session()

    # ---------------------------------------------------------- 公开接口
    def get(self, slot: str) -> Dict[str, Any]:
        """读一个槽（site_rules/site_caps/…/reseed_ledger/pv_budget/…）。"""
        slot = str(slot or "").strip()
        try:
            if slot == SLOT_SITE_RULES:
                return self._get_site_rules()
            if slot == SLOT_SITE_CAPS:
                return self._get_site_caps()
            if slot == SLOT_SITECAP_OVERRIDE:
                return self._get_sitecap_override()
            if slot == SLOT_CROSSSEED_SOURCES:
                return self._get_crossseed()
            # ---- 12.2.0 新槽 ----
            if slot == SLOT_RESEED_LEDGER:
                return self._get_reseed_ledger()
            if slot == SLOT_SIGNIN_LAST_FULL:
                return self._get_run(SLOT_SIGNIN_LAST_FULL)
            if slot == SLOT_SIGNIN_RETRY:
                return self._get_run(SLOT_SIGNIN_RETRY)
            if slot == SLOT_SIGNIN_KEEPALIVE:
                return self._get_run(SLOT_SIGNIN_KEEPALIVE)
            if slot == SLOT_CLAIM_PROFILE:
                return self._get_claim_profile()
            if slot == SLOT_RESCUE_STALL:
                return self._get_seed_json("rescue")
            if slot == SLOT_ONDEMAND_PENDING:
                return self._get_seed_json("pending")
            if slot == SLOT_CROSSSEED_PENDING:
                return self._get_crossseed_pending()
            if slot == SLOT_PV_BUDGET:
                return self._get_site_scalar("pv_budget", "int")
            if slot == SLOT_LIVE_PV_BLOCK:
                return self._get_site_scalar("pv_block", "float")
            if slot == SLOT_LIVE_ALERTS:
                return self._get_live_alerts()
            if slot == SLOT_PV_USAGE:
                return by_site_to_by_date(self._get_site_json("pv_usage"))
            if slot == SLOT_SIGNIN_RECORDS:
                return by_site_to_by_date(self._get_site_json("signin"))
            if slot == SLOT_IYUU_SITES:
                return self._get_iyuu_sites()
            if slot == SLOT_RESEED_PASSKEYS:
                return self._get_reseed_passkeys()
            if slot == SLOT_CLAIM_LEDGER:
                return self._get_claim_ledger()
            if slot == SLOT_KEEPALIVE_ALERT_DAY:
                return self._get_run(SLOT_KEEPALIVE_ALERT_DAY)
            if slot == SLOT_CROSSSEED_BAN:
                return self._get_run(SLOT_CROSSSEED_BAN)
        except Exception:  # noqa: BLE001
            return {}
        return {}

    def save(self, slot: str, value: Any) -> None:
        """写一个槽。``value`` 与旧 kv 键同构（``signin_last_full`` 为浮点标量，
        ``keepalive_alert_day`` 为字符串日期，其余为 dict）。"""
        slot = str(slot or "").strip()
        if slot in (SLOT_SIGNIN_LAST_FULL, SLOT_KEEPALIVE_ALERT_DAY):
            # 标量槽：值不是 dict（旧 kv 就是 float / 字符串日期）
            self._save_run(slot, value)
            return
        if not isinstance(value, dict):
            return
        if slot == SLOT_SITE_RULES:
            self._save_site_rules(value)
        elif slot == SLOT_SITE_CAPS:
            self._save_site_caps(value)
        elif slot == SLOT_SITECAP_OVERRIDE:
            self._save_sitecap_override(value)
        elif slot == SLOT_CROSSSEED_SOURCES:
            self._save_crossseed(value)
        elif slot == SLOT_RESEED_LEDGER:
            self._save_reseed_ledger(value)
        elif slot == SLOT_SIGNIN_LAST_FULL:
            self._save_run(SLOT_SIGNIN_LAST_FULL, value)
        elif slot == SLOT_SIGNIN_RETRY:
            self._save_run(SLOT_SIGNIN_RETRY, value)
        elif slot == SLOT_SIGNIN_KEEPALIVE:
            self._save_run(SLOT_SIGNIN_KEEPALIVE, value)
        elif slot == SLOT_CLAIM_PROFILE:
            self._save_claim_profile(value)
        elif slot == SLOT_RESCUE_STALL:
            self._save_seed_json("rescue", value)
        elif slot == SLOT_ONDEMAND_PENDING:
            self._save_seed_json("pending", value)
        elif slot == SLOT_CROSSSEED_PENDING:
            self._save_crossseed_pending(value)
        elif slot == SLOT_PV_BUDGET:
            self._save_site_scalar("pv_budget", value, "int")
        elif slot == SLOT_LIVE_PV_BLOCK:
            self._save_site_scalar("pv_block", value, "float")
        elif slot == SLOT_LIVE_ALERTS:
            self._save_live_alerts(value)
        elif slot == SLOT_PV_USAGE:
            self._save_site_json("pv_usage", by_date_to_by_site(value))
        elif slot == SLOT_SIGNIN_RECORDS:
            self._save_site_json("signin", by_date_to_by_site(value))
        elif slot == SLOT_IYUU_SITES:
            self._save_iyuu_sites(value)
        elif slot == SLOT_RESEED_PASSKEYS:
            self._save_reseed_passkeys(value)
        elif slot == SLOT_CLAIM_LEDGER:
            self._save_claim_ledger(value)
        elif slot == SLOT_CROSSSEED_BAN:
            self._save_run(SLOT_CROSSSEED_BAN, value)

    def callbacks(self, slot: str) -> Tuple[Any, Any]:
        """返回 ``(get, save)`` 回调对，签名兼容旧 ``get_data/save_data``。

        兼容两种调用姿势：
          - ``get_data(key)`` / ``save_data(key=..., value=...)``（SiteRules / SiteCapRegistry）
          - ``save_data(key, value)``（CrossSeedSources 位置传参）
        """
        slot = str(slot or "").strip()

        def _get(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
            return self.get(slot)

        def _save(*args: Any, **kwargs: Any) -> None:
            value = kwargs.get("value")
            if value is None:
                value = args[1] if len(args) > 1 else None
            self.save(slot, value)

        return _get, _save

    # ---------------------------------------------------------- site_rules
    def _get_site_rules(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            rows = sess.execute(select(mfdb.SiteRow)).scalars().all()
            for r in rows:
                dom = getattr(r, "domain", None)
                if not dom:
                    continue
                if not self._row_has_rules(r):
                    continue
                cols = {k: getattr(r, k, None) for k in _RULE_COLUMNS}
                cols["rules_extra"] = getattr(r, "rules_extra", None)
                cols["updated"] = getattr(r, "updated", None)
                rec = site_columns_to_rec(str(dom), cols)
                out[_norm_domain(dom)] = rec
        finally:
            sess.close()
        return out

    def _row_has_rules(self, row: Any) -> bool:
        if any(getattr(row, k, None) is not None for k in _RULE_MARKER_COLUMNS):
            return True
        extra = getattr(row, "rules_extra", None)
        return isinstance(extra, dict) and bool(extra)

    def _save_site_rules(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                for domain, rec in (value or {}).items():
                    if not isinstance(rec, dict):
                        continue
                    dom = _norm_domain(domain)
                    if not dom:
                        continue
                    cols = rec_to_site_columns(dom, rec, now)
                    row = sess.execute(
                        select(mfdb.SiteRow).where(mfdb.SiteRow.domain == dom)
                    ).scalars().first()
                    if row is None:
                        row = mfdb.SiteRow(
                            site_id=self._next_site_id(sess),
                            domain=dom,
                            created=now,
                        )
                        sess.add(row)
                    for k, v in cols.items():
                        if k != "domain":
                            setattr(row, k, v)
                    row.domain = dom
                    # ★ 不允许「无名站点行」：rec 里没 name（如别名域名 www.yemapt.org）就用域名顶着，
                    #   否则 ``ledger._site_names`` 认不出来（按 name 索引）→ 报表里出现无名行。
                    if not getattr(row, "name", None):
                        row.name = dom
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    def _next_site_id(self, sess: Any) -> int:
        from sqlalchemy import func, select

        try:
            top = sess.execute(
                select(func.max(mfdb.SiteRow.site_id))
            ).scalar()
        except Exception:  # noqa: BLE001
            top = None
        return int(top or 0) + 1

    # ---------------------------------------------------------- site_caps / override
    def _get_site_caps(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            rows = sess.execute(select(mfdb.SiteRow)).scalars().all()
            for r in rows:
                dom = getattr(r, "domain", None)
                caps = getattr(r, "caps", None)
                if not dom or not isinstance(caps, dict) or not caps:
                    continue
                rec = {k: v for k, v in caps.items() if k != _OVERRIDE_SUBKEY}
                if not rec:
                    continue
                rec.setdefault("domain", _norm_domain(dom))
                out[_norm_domain(dom)] = rec
        finally:
            sess.close()
        return out

    def _get_sitecap_override(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            rows = sess.execute(select(mfdb.SiteRow)).scalars().all()
            for r in rows:
                dom = getattr(r, "domain", None)
                caps = getattr(r, "caps", None)
                if not dom or not isinstance(caps, dict):
                    continue
                ov = caps.get(_OVERRIDE_SUBKEY)
                if isinstance(ov, dict) and ov:
                    out[_norm_domain(dom)] = ov
        finally:
            sess.close()
        return out

    def _save_site_caps(self, value: Dict[str, Any]) -> None:
        self._save_caps(value, override=False)

    def _save_sitecap_override(self, value: Dict[str, Any]) -> None:
        self._save_caps(value, override=True)

    def _save_caps(self, value: Dict[str, Any], *, override: bool) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                for domain, rec in (value or {}).items():
                    if not isinstance(rec, dict):
                        continue
                    dom = _norm_domain(domain)
                    if not dom:
                        continue
                    row = sess.execute(
                        select(mfdb.SiteRow).where(mfdb.SiteRow.domain == dom)
                    ).scalars().first()
                    if row is None:
                        row = mfdb.SiteRow(
                            site_id=self._next_site_id(sess),
                            domain=dom,
                            created=now,
                        )
                        sess.add(row)
                    caps = dict(getattr(row, "caps", None) or {})
                    if override:
                        caps[_OVERRIDE_SUBKEY] = dict(rec)
                    else:
                        kept = caps.get(_OVERRIDE_SUBKEY)
                        caps = {k: v for k, v in rec.items() if k != _OVERRIDE_SUBKEY}
                        caps.setdefault("domain", dom)
                        if isinstance(kept, dict):
                            caps[_OVERRIDE_SUBKEY] = kept
                    row.caps = caps
                    # ★ 不碰 row.updated：``updated`` 是「规则账本」的书签（由 site_rules 槽按 rec 写），
                    #   caps 自己的时间戳在同一条 JSON 里的 ``ts`` 字段（12.1.0 实迁时发现：
                    #   这里擅自写 now 会把 rules 的 updated 抹掉 → 回读校验丢字段）。
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- crossseed_sources
    def _get_crossseed(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            rows = sess.execute(select(mfdb.CrossSeedRow)).scalars().all()
            for r in rows:
                h = getattr(r, "sib_hash", None)
                if not h:
                    continue
                cols = {k: getattr(r, k, None) for k in _CROSSSEED_COLUMNS}
                cols["extra"] = getattr(r, "extra", None)
                cols["updated"] = getattr(r, "updated", None)
                out[_norm_hash(h)] = crossseed_columns_to_rec(str(h), cols)
        finally:
            sess.close()
        return out

    def _save_crossseed(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                for sib, rec in (value or {}).items():
                    if not isinstance(rec, dict):
                        continue
                    h = _norm_hash(sib)
                    if not h:
                        continue
                    cols = rec_to_crossseed_columns(h, rec, now)
                    row = sess.execute(
                        select(mfdb.CrossSeedRow).where(mfdb.CrossSeedRow.sib_hash == h)
                    ).scalars().first()
                    if row is None:
                        row = mfdb.CrossSeedRow(sib_hash=h, created=cols.get("created") or now)
                        sess.add(row)
                    for k, v in cols.items():
                        if k != "sib_hash":
                            setattr(row, k, v)
                    row.sib_hash = h
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ============================================================ 12.2.0 新槽
    # 站点行辅助（按 mp_site_id / iyuu_sid / domain 三个键空间命中）
    # ★ 12.2.0 收口：**先解析真名/真域名**，能对上已有「域名行」就复用（顺手补 id 列），
    #   对不上才建行 —— 绝不凭空造 `iyuu:131` 这类无名垃圾站点行污染站表。
    #   ★★ 同一个数字 id 可能属于 MP 命名空间或 IYUU 命名空间（kv 里两者混用）→
    #   解析顺序 hint → MP → IYUU；查找时**两个列都查**（去重，避免同 id 两行）。
    def bind_site_hints(self, mapping: Any) -> None:
        """注入「数字 id → {name, domain}」提示表（脚本/无 plugin.get_data 时用）。"""
        if isinstance(mapping, dict):
            self._site_hints = dict(mapping)

    def _hint_info(self, sid: int) -> Dict[str, str]:
        """提示表：数字 id → {name, domain}（默认空；由 ``bind_site_hints`` 注入）。"""
        h = getattr(self, "_site_hints", None) or {}
        rec = (h.get(str(int(sid))) or h.get(int(sid))) if isinstance(h, dict) else None
        if isinstance(rec, dict):
            return {"name": str(rec.get("name") or ""), "domain": str(rec.get("domain") or "")}
        return {}

    @staticmethod
    def _row_sid(row: Any) -> Any:
        """行上的「站点 id」（优先 mp_site_id，否则 iyuu_sid）——读侧不要漏掉 iyuu-only 行。"""
        sid = getattr(row, "mp_site_id", None)
        return sid if sid is not None else getattr(row, "iyuu_sid", None)

    def _mp_site_info(self, mp_id: int) -> Dict[str, str]:
        """MP 站点登记表：id → {name, domain}（拿不到返回 {}）。"""
        try:
            from app.sdk.network import SitesHelper
            for item in SitesHelper().get_indexers() or []:
                if isinstance(item, dict) and str(item.get("id")) == str(int(mp_id)):
                    return {
                        "name": str(item.get("name") or ""),
                        "domain": str(item.get("domain") or ""),
                    }
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _iyuu_site_info(self, sid: int) -> Dict[str, str]:
        """IYUU 站点表：sid → {name, domain}（读 ``iyuu_cache`` 缓存；拿不到返回 {}）。"""
        cache = None
        try:
            plugin = getattr(self, "_plugin", None)
            cache = cache_get(plugin, "iyuu", "iyuu_cache", CACHE_TTL_REPORT) if plugin is not None else None
        except Exception:  # noqa: BLE001
            cache = None
        for nick, item in ((cache or {}).get("sites") or {}).items():
            if isinstance(item, dict) and str(item.get("id")) == str(int(sid)):
                base = str(item.get("base_url") or "")
                host = base.split("//")[-1].split("/")[0].strip() if base else ""
                return {"name": str(item.get("nickname") or nick or ""), "domain": host}
        return {}

    def _site_row_by_id(self, sess: Any, sid: int, now: float, prefer: str = "mp_site_id") -> Any:
        """按数字 id 取/建站点行（id ∈ MP 命名空间或 IYUU 命名空间）。

        规则（★ 12.2.0）：
        1. 两列（``mp_site_id`` / ``iyuu_sid``）任一命中 → 直接复用（同一个 id）。
        2. 否则先解析出域名/真名（hint → MP 站点表 → IYUU 站点表）→ 命中已有「域名行」→
           复用 **并只补与之匹配的那一列**（从 MP 解析来的补 ``mp_site_id``，从 IYUU 解析来的补
           ``iyuu_sid``）——**绝不互相覆写**（MP id 与 IYUU sid 是两套号，同一个数字不一定是同一站）。
        3. 都解析不到 → 建行；列由解析来源决定，无解析时用 ``prefer``（调用方声明的键空间）。
        """
        from sqlalchemy import select

        sid = int(sid)
        row = sess.execute(
            select(mfdb.SiteRow).where(getattr(mfdb.SiteRow, prefer) == sid)
        ).scalars().first()
        other_col = "iyuu_sid" if prefer == "mp_site_id" else "mp_site_id"
        if row is None:
            row = sess.execute(
                select(mfdb.SiteRow).where(getattr(mfdb.SiteRow, other_col) == sid)
            ).scalars().first()
        if row is not None:
            return row
        info = self._hint_info(sid)
        col = prefer
        if not info:
            mp_info = self._mp_site_info(sid)
            if mp_info:
                info, col = mp_info, "mp_site_id"
        if not info:
            iy_info = self._iyuu_site_info(sid)
            if iy_info:
                info, col = iy_info, "iyuu_sid"
        dom = _norm_domain(info.get("domain"))
        if dom:
            row = sess.execute(
                select(mfdb.SiteRow).where(mfdb.SiteRow.domain == dom)
            ).scalars().first()
            if row is not None:  # 复用同一物理站点的域名行（只补对应列，不覆写另一列）
                if getattr(row, col, None) is None:
                    setattr(row, col, sid)
                if not str(getattr(row, "name", "") or "").strip():
                    row.name = info.get("name") or dom
                return row
        row = mfdb.SiteRow(
            site_id=self._next_site_id(sess), domain=dom or None,
            name=(info.get("name") or dom or f"site:{sid}"), created=now,
        )
        setattr(row, col, sid)
        sess.add(row)
        return row

    def _site_row_by_mp_id(self, sess: Any, mp_id: int, now: float) -> Any:
        return self._site_row_by_id(sess, mp_id, now, "mp_site_id")

    def _site_row_by_iyuu_sid(self, sess: Any, sid: int, now: float) -> Any:
        return self._site_row_by_id(sess, sid, now, "iyuu_sid")

    def _site_row_by_domain(self, sess: Any, domain: str, now: float) -> Any:
        from sqlalchemy import select

        dom = _norm_domain(domain)
        row = sess.execute(
            select(mfdb.SiteRow).where(mfdb.SiteRow.domain == dom)
        ).scalars().first()
        if row is None:
            row = mfdb.SiteRow(
                site_id=self._next_site_id(sess), domain=dom, name=dom, created=now,
            )
            sess.add(row)
        return row

    # ---------------------------------------------------------- mf_run（全局运行标量）
    def _get_run(self, key: str) -> Any:
        from sqlalchemy import select

        sess = self._session
        try:
            row = sess.execute(
                select(mfdb.RunRow).where(mfdb.RunRow.key == key)
            ).scalars().first()
            return getattr(row, "value", None) if row is not None else None
        finally:
            sess.close()

    def _save_run(self, key: str, value: Any) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                row = sess.execute(
                    select(mfdb.RunRow).where(mfdb.RunRow.key == key)
                ).scalars().first()
                if row is None:
                    row = mfdb.RunRow(key=key, created=now)
                    sess.add(row)
                row.value = value
                row.updated = now
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_reseed（全站辅种账本）
    def _get_reseed_ledger(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            rows = sess.execute(select(mfdb.ReseedRow)).scalars().all()
            for r in rows:
                k = getattr(r, "key", None)
                if not k:
                    continue
                out[str(k)] = {
                    "st": getattr(r, "st", None),
                    "ts": getattr(r, "updated", None),
                    "note": getattr(r, "note", None),
                }
        finally:
            sess.close()
        return out

    def _save_reseed_ledger(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                existing: Dict[str, Any] = {
                    str(r.key): r for r in sess.execute(select(mfdb.ReseedRow)).scalars().all()
                }
                for k, row in existing.items():
                    if k not in value:
                        sess.delete(row)
                for key, rec in (value or {}).items():
                    k = str(key or "").strip()
                    if not k:
                        continue
                    rec = rec if isinstance(rec, dict) else {}
                    ts = float(rec.get("ts") or now)
                    row = existing.get(k)
                    if row is None:
                        sid: Optional[int] = None
                        h: Optional[str] = None
                        if ":" in k:
                            _sid, _h = k.split(":", 1)
                            try:
                                sid = int(_sid)
                            except (TypeError, ValueError):
                                sid = None
                            h = str(_h).strip().lower() or None
                        row = mfdb.ReseedRow(key=k, site_id=sid, hash=h, created=ts)
                        sess.add(row)
                    row.st = str(rec.get("st") or "")[:24] or None
                    row.note = str(rec.get("note") or "")[:200] or None
                    row.updated = ts
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_claim（认领账本）
    def _get_claim_ledger(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            rows = sess.execute(select(mfdb.ClaimRow)).scalars().all()
            for r in rows:
                k = getattr(r, "key", None)
                if not k:
                    continue
                out[str(k)] = {
                    "tid": getattr(r, "tid", None),
                    "ts": getattr(r, "updated", None),
                    "st": getattr(r, "st", None),
                    "benefit": getattr(r, "benefit", None),
                    "note": getattr(r, "note", None),
                    "task": getattr(r, "task_id", None),
                    "title": getattr(r, "title", None),
                }
        finally:
            sess.close()
        return out

    def _save_claim_ledger(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                existing: Dict[str, Any] = {
                    str(r.key): r for r in sess.execute(select(mfdb.ClaimRow)).scalars().all()
                }
                for k, row in existing.items():
                    if k not in value:
                        sess.delete(row)
                for key, rec in (value or {}).items():
                    k = str(key or "").strip()
                    if not k:
                        continue
                    rec = rec if isinstance(rec, dict) else {}
                    ts = float(rec.get("ts") or now)
                    row = existing.get(k)
                    if row is None:
                        sid: Optional[int] = None
                        h: Optional[str] = None
                        if ":" in k:
                            _sid, _h = k.split(":", 1)
                            try:
                                sid = int(_sid)
                            except (TypeError, ValueError):
                                sid = None
                            h = str(_h).strip().lower() or None
                        row = mfdb.ClaimRow(key=k, site_id=sid, hash=h, created=ts)
                        sess.add(row)
                    row.tid = str(rec.get("tid") or "")[:64] or None
                    row.st = str(rec.get("st") or "")[:16] or None
                    row.benefit = str(rec.get("benefit") or "")[:200] or None
                    row.note = str(rec.get("note") or "")[:200] or None
                    row.task_id = str(rec.get("task") or "")[:64] or None
                    row.title = str(rec.get("title") or "")[:300] or None
                    row.updated = ts
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_seed JSON 列（rescue/pending）
    def _get_seed_json(self, col: str) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            for r in sess.execute(select(mfdb.SeedRow)).scalars().all():
                h = getattr(r, "hash", None)
                data = getattr(r, col, None)
                if not h or not isinstance(data, dict) or not data:
                    continue
                for k, v in data.items():
                    out[_norm_hash(k)] = v
        finally:
            sess.close()
        return out

    def _save_seed_json(self, col: str, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                keys = {_norm_hash(k) for k in (value or {}).keys() if _norm_hash(k)}
                for r in sess.execute(select(mfdb.SeedRow)).scalars().all():
                    h = getattr(r, "hash", None)
                    data = getattr(r, col, None)
                    if isinstance(data, dict) and data and h and _norm_hash(h) not in keys:
                        setattr(r, col, {})
                for h, v in (value or {}).items():
                    hh = _norm_hash(h)
                    if not hh:
                        continue
                    row = sess.execute(
                        select(mfdb.SeedRow).where(mfdb.SeedRow.hash == hh)
                    ).scalars().first()
                    if row is None:
                        row = mfdb.SeedRow(hash=hh)
                        sess.add(row)
                    setattr(row, col, {hh: v})
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_crossseed.pending
    def _get_crossseed_pending(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            for r in sess.execute(select(mfdb.CrossSeedRow)).scalars().all():
                h = getattr(r, "sib_hash", None)
                data = getattr(r, "pending", None)
                if not h or not isinstance(data, dict) or not data:
                    continue
                for k, v in data.items():
                    out[_norm_hash(k)] = v
        finally:
            sess.close()
        return out

    def _save_crossseed_pending(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                keys = {_norm_hash(k) for k in (value or {}).keys() if _norm_hash(k)}
                for r in sess.execute(select(mfdb.CrossSeedRow)).scalars().all():
                    h = getattr(r, "sib_hash", None)
                    data = getattr(r, "pending", None)
                    if isinstance(data, dict) and data and h and _norm_hash(h) not in keys:
                        setattr(r, "pending", {})
                for h, v in (value or {}).items():
                    hh = _norm_hash(h)
                    if not hh or not isinstance(v, dict):
                        continue
                    row = sess.execute(
                        select(mfdb.CrossSeedRow).where(mfdb.CrossSeedRow.sib_hash == hh)
                    ).scalars().first()
                    if row is None:
                        row = mfdb.CrossSeedRow(sib_hash=hh, created=now)
                        sess.add(row)
                    setattr(row, "pending", {hh: v})
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_site 标量（pv_budget/pv_block，按 mp_site_id）
    def _get_site_scalar(self, col: str, kind: str) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                sid = self._row_sid(r)
                v = getattr(r, col, None)
                if sid is None or v is None:
                    continue
                out[str(int(sid))] = int(v) if kind == "int" else float(v)
        finally:
            sess.close()
        return out

    def _save_site_scalar(self, col: str, value: Dict[str, Any], kind: str) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                keys = {int(k) for k in (value or {}).keys() if _int_ok(k)}
                for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                    sid = self._row_sid(r)
                    if sid is not None and int(sid) not in keys and getattr(r, col, None) is not None:
                        setattr(r, col, None)
                for k, v in (value or {}).items():
                    if not _int_ok(k):
                        continue
                    row = self._site_row_by_mp_id(sess, int(k), now)
                    if kind == "int":
                        setattr(row, col, int(v or 0) if v is not None else 0)
                    else:
                        setattr(row, col, float(v))
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_site JSON 列（pv_usage/signin，按 mp_site_id）
    def _get_site_json(self, col: str) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                sid = self._row_sid(r)
                data = getattr(r, col, None)
                if sid is None or not isinstance(data, dict) or not data:
                    continue
                out[str(int(sid))] = data
        finally:
            sess.close()
        return out

    def _save_site_json(self, col: str, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                keys = {int(k) for k in (value or {}).keys() if _int_ok(k)}
                for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                    sid = self._row_sid(r)
                    data = getattr(r, col, None)
                    if sid is not None and int(sid) not in keys and isinstance(data, dict) and data:
                        setattr(r, col, {})
                for k, v in (value or {}).items():
                    if not _int_ok(k) or not isinstance(v, dict):
                        continue
                    row = self._site_row_by_mp_id(sess, int(k), now)
                    setattr(row, col, dict(v))
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_site.alerts（live_alerts，键 = "sid:kind"）
    def _get_live_alerts(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                sid = self._row_sid(r)
                alerts = getattr(r, "alerts", None)
                if sid is None or not isinstance(alerts, dict):
                    continue
                for kind, ts in alerts.items():
                    out[f"{int(sid)}:{kind}"] = ts
        finally:
            sess.close()
        return out

    def _save_live_alerts(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        per_site: Dict[int, Dict[str, Any]] = {}
        for key, ts in (value or {}).items():
            sid_s, _, kind = str(key).partition(":")
            if not sid_s or not kind or not _int_ok(sid_s):
                continue
            per_site.setdefault(int(sid_s), {})[kind] = ts
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                    sid = self._row_sid(r)
                    if sid is not None and int(sid) not in per_site:
                        alerts = getattr(r, "alerts", None)
                        if isinstance(alerts, dict) and alerts:
                            setattr(r, "alerts", {})
                for sid, alerts in per_site.items():
                    row = self._site_row_by_mp_id(sess, sid, now)
                    row.alerts = dict(alerts)
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_site.credential（iyuu_sites / reseed_passkeys）
    def _get_iyuu_sites(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                dom = _norm_domain(getattr(r, "domain", None))
                cred = getattr(r, "credential", None)
                if not dom or not isinstance(cred, dict):
                    continue
                sub = cred.get(_CRED_IYUU)
                if isinstance(sub, dict) and sub:
                    out[dom] = sub
        finally:
            sess.close()
        return out

    def _save_iyuu_sites(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                    dom = _norm_domain(getattr(r, "domain", None))
                    cred = getattr(r, "credential", None)
                    if dom and isinstance(cred, dict) and _CRED_IYUU in cred and dom not in value:
                        cred.pop(_CRED_IYUU, None)
                        r.credential = cred
                for dom, sub in (value or {}).items():
                    d = _norm_domain(dom)
                    if not d or not isinstance(sub, dict):
                        continue
                    row = self._site_row_by_domain(sess, d, now)
                    cred = dict(getattr(row, "credential", None) or {})
                    cred[_CRED_IYUU] = dict(sub)
                    row.credential = cred
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    def _get_reseed_passkeys(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                sid = getattr(r, "iyuu_sid", None)
                cred = getattr(r, "credential", None)
                if sid is None or not isinstance(cred, dict):
                    continue
                sub = cred.get(_CRED_RESEED_PK)
                if sub is not None and str(sub) != "":
                    out[str(int(sid))] = str(sub)
        finally:
            sess.close()
        return out

    def _save_reseed_passkeys(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                keys = {int(k) for k in (value or {}).keys() if _int_ok(k)}
                for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                    sid = getattr(r, "iyuu_sid", None)
                    cred = getattr(r, "credential", None)
                    if sid is not None and int(sid) not in keys and isinstance(cred, dict) \
                            and _CRED_RESEED_PK in cred:
                        cred.pop(_CRED_RESEED_PK, None)
                        r.credential = cred
                for k, pk in (value or {}).items():
                    if not _int_ok(k):
                        continue
                    row = self._site_row_by_iyuu_sid(sess, int(k), now)
                    cred = dict(getattr(row, "credential", None) or {})
                    cred[_CRED_RESEED_PK] = str(pk)
                    row.credential = cred
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()

    # ---------------------------------------------------------- mf_site.caps.__claim__（claim_profile）
    def _get_claim_profile(self) -> Dict[str, Any]:
        from sqlalchemy import select

        out: Dict[str, Any] = {}
        sess = self._session
        try:
            for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                sid = self._row_sid(r)
                caps = getattr(r, "caps", None)
                if sid is None or not isinstance(caps, dict):
                    continue
                sub = caps.get(_CAPS_CLAIM)
                if isinstance(sub, dict) and sub:
                    out[str(int(sid))] = sub
        finally:
            sess.close()
        return out

    def _save_claim_profile(self, value: Dict[str, Any]) -> None:
        from sqlalchemy import select

        now = _now()
        lock = self._lock
        if lock is not None:
            lock.acquire()
        try:
            sess = self._session
            try:
                keys = {int(k) for k in (value or {}).keys() if _int_ok(k)}
                for r in sess.execute(select(mfdb.SiteRow)).scalars().all():
                    sid = self._row_sid(r)
                    caps = getattr(r, "caps", None)
                    if sid is not None and int(sid) not in keys and isinstance(caps, dict) \
                            and _CAPS_CLAIM in caps:
                        caps.pop(_CAPS_CLAIM, None)
                        r.caps = caps
                for k, sub in (value or {}).items():
                    if not _int_ok(k) or not isinstance(sub, dict):
                        continue
                    row = self._site_row_by_mp_id(sess, int(k), now)
                    caps = dict(getattr(row, "caps", None) or {})
                    caps[_CAPS_CLAIM] = dict(sub)
                    row.caps = caps
                sess.commit()
            finally:
                sess.close()
        finally:
            if lock is not None:
                lock.release()


# ---------------------------------------------------------------------------
# 单例工厂（模块级，跨热重载存活）
# ---------------------------------------------------------------------------
def get_site_store(plugin: Any) -> SiteStore:
    """取/建进程级 SiteStore（按 plugin_id 单例；热重载后重绑新 backend）。

    照 `persistence.get_gate_store` 的 ``_shared()`` 注册表模式，**不**挂 ``stores()``。
    """
    key = f"site_store:{getattr(plugin, 'plugin_id', 'MagicFlow')}"
    sh = _shared()
    with sh.lock:
        store = sh.singletons.get(key)
        if store is None:
            store = SiteStore(get_backend(plugin))
            sh.singletons[key] = store
        else:
            try:
                store.bind(get_backend(plugin))
            except Exception:  # noqa: BLE001
                pass
        try:
            store.bind_plugin(plugin)
        except Exception:  # noqa: BLE001
            pass
    return store


def slot_callbacks(plugin: Any, slot: str) -> Tuple[Any, Any]:
    """按 ``(plugin, slot)`` 缓存 ``(get, save)`` 回调对（消费点用，避免每次重建闭包）。

    ``get(slot)/save(slot, value)`` 保持与 ``SiteStore.callbacks`` 同语义；
    缓存挂在 plugin 实例上（照 ``self._site_cap_reg`` 那套实例属性缓存）。
    """
    store = get_site_store(plugin)
    cache = getattr(plugin, "_kv_slot_cbs", None)
    if cache is None:
        cache = {}
        try:
            plugin._kv_slot_cbs = cache
        except Exception:  # noqa: BLE001
            pass
    key = str(slot or "").strip()
    cb = cache.get(key)
    if cb is None:
        cb = store.callbacks(key)
        cache[key] = cb
    return cb
