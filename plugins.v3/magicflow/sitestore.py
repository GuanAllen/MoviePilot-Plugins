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
from .ledger import get_backend
from .persistence import _shared

# ---------------------------------------------------------------------------
# 槽名（内部标识，与旧 kv 键同名）
# ---------------------------------------------------------------------------
SLOT_SITE_RULES = "site_rules"
SLOT_SITE_CAPS = "site_caps"
SLOT_SITECAP_OVERRIDE = "sitecap_override"
SLOT_CROSSSEED_SOURCES = "crossseed_sources"
SLOTS: Tuple[str, ...] = (
    SLOT_SITE_RULES, SLOT_SITE_CAPS, SLOT_SITECAP_OVERRIDE, SLOT_CROSSSEED_SOURCES,
)

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
# SiteStore
# ---------------------------------------------------------------------------
class SiteStore:
    """三套站点/来源 kv 账本 → 表。``get/save`` 语义与 kv 槽一一对应。"""

    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def bind(self, backend: Any) -> None:
        """重绑后端（热重载后拿到新 backend，仍是同一个 store 实例）。"""
        self._backend = backend

    @property
    def _lock(self):
        return getattr(self._backend, "_lock", None)

    @property
    def _session(self):
        return self._backend._session()

    # ---------------------------------------------------------- 公开接口
    def get(self, slot: str) -> Dict[str, Any]:
        """读一个槽（``site_rules``/``site_caps``/``sitecap_override``/``crossseed_sources``）。"""
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
        except Exception:  # noqa: BLE001
            return {}
        return {}

    def save(self, slot: str, value: Dict[str, Any]) -> None:
        """写一个槽。``value`` 与旧 kv 键同构（``{主键: rec}``）。"""
        slot = str(slot or "").strip()
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
            if not isinstance(value, dict):
                return
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
    return store
