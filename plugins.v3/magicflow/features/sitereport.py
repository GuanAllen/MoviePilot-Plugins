# -*- coding: utf-8 -*-
"""魔流 · sitereport —— 站点级种子报表（AI 入口 + UI 共用）。

回答一类问题：**「某站点上，我们现在挂着的各种种子分别处于什么状态？」**
一次调用给出：逐条种子（hash / 标题 / 体积 / 保存目录 / qB 状态 / 进度 / 比例 /
保护 / 账单 / H&R 需做种时间）+ **两轴分级**分类汇总 + H&R 对账摘要。

★ 两轴分级（见 ``docs/DESIGN-CURRENT.md`` 与 ``docs/AGENT-API.md``）：
  - **第一级（职务 / 身份轴）**：六桶 —— 刷流 / 魔力 / 保种（欠 H&R 挂补）/ 静默
    （含 新 / 资源 / 普通 三子桶）/ 补源 / 外部；
  - **第二级（传输轴）**：每桶内按 未完成 / 暂停 / 做种中 三态统计，不单独成桶；
  - **账本 / 债务只作列字段**（``bill`` / ``hr``），不再当桶。

只读真值源（**不新增 / 不缓存真值**，全部现读）：
  - 下载器快照：``_tag_all_torrents()``（按标签 / tracker 归属站点）
  - 保护：各任务 ``store.get_protected_torrents``（= 手动保留 ∪ H&R ∪ 未完成 ∪ 认领）
  - 账本：``_hrbills_store()``（账单 state / rule）
  - H&R 对账：``_hr_reconcile_site()``（``live=1`` 现抓）或
    ``_hr_reconcile_cache().get_report()``（默认读上一轮缓存）

契约：见 ``docs/AGENT-API.md``（``GET /agent/site/seeds``）+ ``GET /site/seeds``。
本模块**只读**：不写下载器 / 账本 / 热层，不含任何写动作。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from app.schemas import Response

from ..tags import (
    RESCUE_TAG,
    EXTERNAL_TAG,
    STATE_BRUSH,
    STATE_BONUS,
    STATE_HR,
    SUB_NEW,
    SUB_RESOURCE,
    SUB_PLAIN,
    duty_of,
    identity_of,
    is_reuse_copy,
    parse_tag,
)
from .hrbills import (
    BILL_STATE_ACTIVE,
    BILL_STATE_BREACHED,
    RULE_HIT_AND_RUN,
    RULE_SITE_HR,
)

# 第一级分类桶（职务 / 身份轴，互斥；优先级见 ``_site_report_bucket``）
BUCKET_BRUSH = "刷流"
BUCKET_BONUS = "魔力"
BUCKET_HR = "保种"          # 欠 H&R 挂补（__hr_host__ 保种 ∪ 仍欠债）
BUCKET_SILENT = "静默"      # 无职务（身份轴：新 / 资源 / 普通 三子桶）
BUCKET_RESCUE = "补源"      # 死种补源副本（``魔流-补源``）
BUCKET_EXTERNAL = "外部"    # 插件外来源、已纳管（``魔流-外部``）

_BUCKET_ORDER = (BUCKET_RESCUE, BUCKET_HR, BUCKET_BRUSH, BUCKET_BONUS,
                 BUCKET_EXTERNAL, BUCKET_SILENT)

# 静默三子桶（身份轴，仅静默桶使用）
SILENT_SUBS = (SUB_NEW, SUB_RESOURCE, SUB_PLAIN)

# 第二级传输轴（每桶内三态，不单独成桶）
TRANSPORT_DOWNLOADING = "未完成"
TRANSPORT_PAUSED = "暂停"
TRANSPORT_SEEDING = "做种中"

_HR_RULES = (RULE_SITE_HR, RULE_HIT_AND_RUN)

# 分页/裁剪上限（逐条列表）
MAX_ITEMS = 4000


class SiteReportMixin:
    """站点级种子报表（只读）。"""

    # ------------------------------------------------------------------ 站点解析
    def _site_report_resolve(self, site: str) -> Dict[str, Any]:
        """把 ``site``（域名 / 短名 / id）解析成 ``{id, name, domain, sites}``。

        ``sites`` 始终带上（供前端选择器）；解析不到就按原样当 name/domain 用。
        """
        raw = str(site or "").strip()
        try:
            sites = self._list_sites() or []
        except Exception:  # noqa: BLE001
            sites = []
        if not raw:
            return {"id": 0, "name": "", "domain": "", "sites": sites}
        needle = raw.lower()
        for it in sites:
            iid = str(it.get("id") or "")
            name = str(it.get("name") or "")
            dom = str(it.get("domain") or "")
            if needle in (iid.lower(), name.lower(), dom.lower()):
                return {"id": it.get("id") or 0, "name": name, "domain": dom, "sites": sites}
        for t in (getattr(self, "_task_configs", None) or {}).values():
            name = str(getattr(t, "site_name", "") or "")
            dom = str(getattr(t, "site_domain", "") or "")
            if needle in (name.lower(), dom.lower()):
                return {"id": getattr(t, "site_id", 0) or 0, "name": name, "domain": dom, "sites": sites}
        return {"id": 0, "name": raw, "domain": raw if "." in raw else "", "sites": sites}

    # ------------------------------------------------------------------ 只读小助手
    def _site_report_protected(self) -> set:
        """保护 hash 并集（跨所有任务 + 历史空 task_id），与 ``_delete_gate_detail`` 同源。"""
        out: set = set()
        try:
            store = getattr(self, "_store", None)
            if store is None:
                return out
            tids = list((getattr(self, "_task_configs", None) or {}).keys())
            tids.append("")
            for tid in tids:
                try:
                    out |= set(store.get_protected_torrents(tid) or set())
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        return {str(h).strip().lower() for h in out}

    def _site_report_bills_store(self):
        try:
            return self._hrbills_store()
        except Exception:  # noqa: BLE001
            return None

    def _site_report_snapshot(self) -> Dict[str, Any]:
        """展示用下载器快照（hash→TorrentInfo）。

        走 ``_tag_snapshot_view``（stale-while-revalidate）——报表是**只读展示**，
        不该为 qB 全量拉取买单；实在拿不到再回退阻塞式。
        """
        try:
            groups = self._tag_snapshot_view()
        except Exception:  # noqa: BLE001
            try:
                return self._tag_all_torrents() or {}
            except Exception:  # noqa: BLE001
                return {}
        out: Dict[str, Any] = {}
        for rows in (groups or {}).values():
            for t in rows or []:
                h = str(getattr(t, "hash", "") or "").lower()
                if h:
                    out[h] = t
        return out

    @staticmethod
    def _site_report_is_paused(state: str) -> bool:
        st = str(state or "").strip().lower()
        return st.startswith("paused") or st.startswith("stopped")

    @staticmethod
    def _site_report_torrent_site(t: Any, known: set) -> str:
        """单种站点短名（不自调 ``_tag_site_names()``，由调用方预算好 ``known`` 集合）。"""
        tagset = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
        for x in tagset:
            if x in known:
                return x
        for x in tagset:
            p = parse_tag(x)
            if p and p.get("site"):
                return str(p["site"])
        return ""

    def _site_report_match(self, info: Dict[str, Any], t: Any, known: set) -> bool:
        """种子是否属于该站：标签站点短名匹配 或 tracker 域名匹配。"""
        name = str(info.get("name") or "").strip().lower()
        dom = ""
        try:
            dom = self._hrbills_norm_domain(str(info.get("domain") or ""))
        except Exception:  # noqa: BLE001
            dom = str(info.get("domain") or "").strip().lower()
        tsn = self._site_report_torrent_site(t, known).strip().lower()
        if name and tsn == name:
            return True
        tr = str(getattr(t, "tracker", "") or "").strip().lower()
        if dom and (dom in tr or tr.endswith(dom)):
            return True
        return False

    @staticmethod
    def _site_report_transport(state: str, progress: float) -> str:
        """第二级传输轴（三态互斥）：未完成 / 暂停 / 做种中。"""
        if progress < 0.999:
            return TRANSPORT_DOWNLOADING
        if SiteReportMixin._site_report_is_paused(state):
            return TRANSPORT_PAUSED
        return TRANSPORT_SEEDING

    @staticmethod
    def _site_report_sub(t: Any, bucket: str) -> str:
        """静默桶的「身份子桶」→ 新 / 资源 / 普通；非静默桶返回 ``""``。"""
        if bucket != BUCKET_SILENT:
            return ""
        try:
            _isite, sub = identity_of(getattr(t, "tags", None) or [])
        except Exception:  # noqa: BLE001
            return SUB_PLAIN
        return sub if sub in SILENT_SUBS else SUB_PLAIN

    def _site_report_bucket(self, t: Any, state: str, progress: float,
                            is_hr: bool, is_prot: bool) -> str:
        """第一级桶（职务 / 身份轴，6 桶互斥）。

        优先级：补源（特殊持有）→ 保种（欠 H&R 挂补：职务=保种 或 仍欠债）→ 刷流 →
        魔力 → 外部（特殊来源，无职务时）→ 静默（无职务）。
        账本 / 债务不再当桶（``is_hr`` 只并入「保种」，明细看 item 的 ``bill``/``hr`` 列）；
        传输三态（未完成/暂停/做种中）也**不单独成桶**（见 ``_site_report_transport``）。
        """
        try:
            _tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
        except Exception:  # noqa: BLE001
            _tags = []
        if RESCUE_TAG in _tags:
            return BUCKET_RESCUE
        _dsite, duty = duty_of(_tags)
        if duty == STATE_HR or is_hr:
            return BUCKET_HR
        if duty == STATE_BRUSH:
            return BUCKET_BRUSH
        if duty == STATE_BONUS:
            return BUCKET_BONUS
        if EXTERNAL_TAG in _tags:
            return BUCKET_EXTERNAL
        return BUCKET_SILENT

    def _site_report_hr(self, domain: str, live: int, snap: Any) -> Dict[str, Any]:
        """H&R 对账结果：``live=1`` 现抓一轮；否则读上一轮缓存。"""
        dom = ""
        try:
            dom = self._hrbills_norm_domain(domain or "")
        except Exception:  # noqa: BLE001
            dom = str(domain or "").strip().lower()
        if not dom:
            return {}
        if live:
            try:
                return self._hr_reconcile_site(dom, snap) or {}
            except Exception:  # noqa: BLE001
                return {}
        try:
            return self._hr_reconcile_cache().get_report(dom) or {}
        except Exception:  # noqa: BLE001
            return {}

    # ------------------------------------------------------------------ 报表主体
    def _site_seed_report(self, site: str = "", live: int = 0) -> Dict[str, Any]:
        info = self._site_report_resolve(site)
        available = [
            {"id": it.get("id"), "name": it.get("name"), "domain": it.get("domain")}
            for it in (info.get("sites") or [])
        ]
        at = datetime.now().astimezone().isoformat(timespec="seconds")
        if not str(site or "").strip():
            # 无参 = 只回站点清单（供选择器）
            return {"site": {}, "at": at, "live": bool(live),
                    "summary": {"total": 0}, "items": [], "hr": {},
                    "available_sites": available}

        name = str(info.get("name") or "")
        dom = str(info.get("domain") or "")
        try:
            snap = self._site_report_snapshot()
        except Exception:  # noqa: BLE001
            snap = {}
        protected = self._site_report_protected()
        store = self._site_report_bills_store()
        hr_rep = self._site_report_hr(dom, live, snap)

        # 站点 H&R 欠账：tid→infohash→need_left（reconcile 逐条 records，见 hrbills 11.10.0）
        owed: Dict[str, str] = {}
        for rec in (hr_rep.get("records") or []):
            if not isinstance(rec, dict):
                continue
            hh = str(rec.get("infohash") or "").strip().lower()
            if hh:
                owed[hh] = str(rec.get("need_left") or "")

        # 归属筛选：标签/tracker 命中该站 或 在站点 H&R 欠账名单里
        try:
            known = set(self._tag_site_names())
        except Exception:  # noqa: BLE001
            known = set()
        scope: Dict[str, Any] = {}
        for h, t in (snap or {}).items():
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            if hh in owed or self._site_report_match(info, t, known):
                scope[hh] = t

        items: List[Dict[str, Any]] = []
        for hh, t in scope.items():
            bill = None
            if store is not None:
                try:
                    bill = store.get(hh)
                except Exception:  # noqa: BLE001
                    bill = None
            bill_state = str((bill or {}).get("state") or "")
            bill_rule = str((bill or {}).get("rule") or "")
            state = str(getattr(t, "state", "") or "")
            progress = round(float(getattr(t, "progress", 0) or 0), 4)
            is_prot = hh in protected
            # ★ 11.11.1：复用/补源副本（非真实下载）不判 H&R（不把辅种算进「欠H&R」桶）。
            _reuse_copy = is_reuse_copy(getattr(t, "tags", None))
            is_hr = (not _reuse_copy) and ((hh in owed) or (bill_state == BILL_STATE_ACTIVE and bill_rule in _HR_RULES))
            bucket = self._site_report_bucket(t, state, progress, is_hr, is_prot)
            items.append({
                "hash": hh,
                "title": str(getattr(t, "title", "") or "")[:160],
                "size_gb": round(float(getattr(t, "size_gb", 0) or 0), 3),
                "save_path": str(getattr(t, "save_path", "") or ""),
                "state": state,
                "progress": progress,
                "ratio": round(float(getattr(t, "ratio", 0) or 0), 3),
                "uploaded": round(float(getattr(t, "uploaded", 0) or 0)),
                "bucket": bucket,
                "sub": self._site_report_sub(t, bucket),
                "transport": self._site_report_transport(state, progress),
                "protected": bool(is_prot),
                "bill": ({"state": bill_state, "rule": bill_rule} if bill else None),
                "hr": ({"owed": True, "need_left": owed.get(hh, "")} if is_hr else None),
            })

        order = {b: i for i, b in enumerate(_BUCKET_ORDER)}
        items.sort(key=lambda x: (order.get(x["bucket"], 99), -float(x["size_gb"] or 0)))
        items = items[:MAX_ITEMS]

        # 汇总（两轴：第一级桶 6 + 第二级传输 3 + 静默三子桶；账本/债务不进桶）
        by_bucket: Dict[str, int] = {}
        by_transport: Dict[str, int] = {}
        bucket_transport: Dict[str, Dict[str, int]] = {}
        silent_by_sub: Dict[str, int] = {}
        total_size = 0.0
        prot_n = 0
        for it in items:
            b = it["bucket"]
            tr = it["transport"]
            by_bucket[b] = by_bucket.get(b, 0) + 1
            by_transport[tr] = by_transport.get(tr, 0) + 1
            _bt = bucket_transport.setdefault(b, {})
            _bt[tr] = _bt.get(tr, 0) + 1
            if b == BUCKET_SILENT:
                s = it["sub"] or SUB_PLAIN
                silent_by_sub[s] = silent_by_sub.get(s, 0) + 1
            total_size += float(it["size_gb"] or 0)
            if it["protected"]:
                prot_n += 1
        recs = list(hr_rep.get("records") or [])
        hr_owed = len(recs) if recs else int(hr_rep.get("records_total") or 0)
        hr_missing = len(hr_rep.get("missing_local") or [])
        summary = {
            "total": len(items),
            "size_gb": round(total_size, 2),
            "protected": prot_n,
            "by_bucket": by_bucket,
            "by_transport": by_transport,
            "bucket_transport": bucket_transport,
            "silent_by_sub": silent_by_sub,
            "hr_owed": hr_owed,
            "hr_in_qb": sum(1 for r in recs if isinstance(r, dict) and r.get("in_qb")),
            "hr_missing": hr_missing,
        }
        return {
            "site": {"id": info.get("id"), "name": name, "domain": dom},
            "at": at,
            "live": bool(live),
            "summary": summary,
            "items": items,
            "hr": {
                "source": "live" if live else "cache",
                "ok": bool(hr_rep.get("ok")),
                "partial": bool(hr_rep.get("partial")),
                "error": str(hr_rep.get("error") or ""),
                "records_total": int(hr_rep.get("records_total") or 0),
                "missing": hr_missing,
                "present_no_bill": len(hr_rep.get("present_no_bill") or []),
                "hash_coverage_complete": bool(hr_rep.get("hash_coverage_complete")),
            },
            "available_sites": available,
        }

    # ------------------------------------------------------------------ 端点
    def get_site_seeds(self, site: str = "", live: int = 0) -> Response:
        """``GET /site/seeds``：站点级种子报表（只读）。"""
        try:
            data = self._site_seed_report(site, live)
            return Response(success=True, message="ok", data=data)
        except Exception as e:  # noqa: BLE001
            self._log(f"站点报表失败: {e}", "error")
            return Response(success=False, message=str(e))

    # ------------------------------------------------------------------ 11.11.0 H&R 账单按站
    def _hr_bills_by_site(self, site: str = "", live: int = 0) -> Dict[str, Any]:
        """★ H&R 账单按站分组（只读）：欠债/状态分布/need_left/in_qb/missing/per_torrent_hr/规则来源。

        真值源：账单 store + 下载器快照 + 站点规则 + 对账缓存（只读，不缓存新真值）。
        """
        store = self._site_report_bills_store()
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        hr_cache = None
        try:
            hr_cache = self._hr_reconcile_cache()
        except Exception:  # noqa: BLE001
            hr_cache = None
        try:
            _norm = self._hrbills_norm_domain
        except Exception:  # noqa: BLE001
            _norm = lambda d: str(d or "").strip().lower()  # noqa: E731
        filter_dom = _norm(site) if site else ""
        by_site: Dict[str, Dict[str, Any]] = {}
        totals = {"sites": 0, "bills": 0, "active": 0, "pending": 0, "settled": 0,
                  "void": 0, "breached": 0, "owed": 0, "missing": 0, "at_risk": 0}

        def _bucket(dom: str) -> Dict[str, Any]:
            if dom in by_site:
                return by_site[dom]
            per_torrent = False
            hr_flag = None
            rule_source = ""
            need_h = 24.0
            try:
                per_torrent = bool(self._site_per_torrent_hr(dom))
            except Exception:  # noqa: BLE001
                per_torrent = False
            try:
                hr_flag = self._site_hr_flag(dom)
            except Exception:  # noqa: BLE001
                hr_flag = None
            try:
                _rules = self._site_rules() or {}
                _rec = dict((_rules.items() or {}).get(dom) or {})
                rule_source = str(_rec.get("source") or "")
                need_h = float(_rec.get("seed_hours") or 24.0)
            except Exception:  # noqa: BLE001
                rule_source = ""
                need_h = 24.0
            by_site[dom] = {
                "domain": dom, "name": dom, "per_torrent_hr": per_torrent,
                "hr_flag": hr_flag, "rule_source": rule_source, "need_h": round(need_h, 1),
                "bills": {"total": 0, "active": 0, "pending": 0, "settled": 0,
                          "void": 0, "breached": 0},
                "owed": 0, "in_qb": 0, "missing": 0, "at_risk": 0, "items": [],
            }
            # ★ 11.13.0 考核窗口（小时；取不到 = 无窗口信息，不预警）
            try:
                by_site[dom]["window_h"] = round(float(self._hr_window_hours(dom) or 0.0), 1)
            except Exception:  # noqa: BLE001
                by_site[dom]["window_h"] = 0.0
            return by_site[dom]

        bills = store.all() if store is not None else {}
        for h, b in bills.items():
            if not isinstance(b, dict):
                continue
            dom = _norm(str(b.get("site") or ""))
            if not dom:
                continue
            if filter_dom and dom != filter_dom:
                continue
            g = _bucket(dom)
            st = str(b.get("state") or "")
            hh = str(h or "").strip().lower()
            in_qb = hh in snap
            g["bills"]["total"] += 1
            totals["bills"] += 1
            if st in g["bills"]:
                g["bills"][st] += 1
            if st in totals:
                totals[st] += 1
            if in_qb:
                g["in_qb"] += 1
            if st in (BILL_STATE_ACTIVE, BILL_STATE_BREACHED):
                g["owed"] += 1
                totals["owed"] += 1
            g["items"].append({
                "hash": hh, "title": str(b.get("title") or "")[:120],
                "state": st, "rule": str(b.get("rule") or ""),
                "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                "need_h": round(float(b.get("need_h") or 0.0), 2),
                "in_qb": in_qb, "opened_by": str(b.get("opened_by") or ""),
                "breached_at": b.get("breached_at") or 0,
                # ★ 11.13.0 到期/预警（只读推导）：due_h = need_h + 安全垫
                **(self._hr_deadline(b) or {}),
            })
            if g["items"][-1].get("at_risk"):
                g["at_risk"] += 1
                totals["at_risk"] += 1
        # 站点视角 missing_local（对账缓存，只读）
        for dom in list(by_site.keys()):
            rep = {}
            if hr_cache is not None:
                try:
                    rep = hr_cache.get_report(dom) or {}
                except Exception:  # noqa: BLE001
                    rep = {}
            missing = int(len(rep.get("missing_local") or []))
            by_site[dom]["missing"] = missing
            totals["missing"] += missing
            by_site[dom]["items"] = sorted(
                by_site[dom]["items"],
                key=lambda x: (0 if x["state"] in (BILL_STATE_ACTIVE, BILL_STATE_BREACHED) else 1),
            )[:200]
        sites = [by_site[k] for k in sorted(by_site, key=lambda d: -by_site[d]["owed"])]
        totals["sites"] = len(sites)
        return {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "live": bool(live),
            "totals": totals,
            "sites": sites,
            "policy": {  # ★ 11.13.0 H&R 策略旋钮（设置面板可改）
                "seed_margin_hours": round(float(self._hr_margin_hours() or 0.0), 2),
                "deadline_warn_hours": round(float(self._hr_warn_hours() or 0.0), 2),
                "settle_rule": "seeded_h >= need_h + seed_margin_hours",
                "at_risk_rule": "未达标 且 距站点考核窗口到期 ≤ deadline_warn_hours",
            },
            "source_of_truth": ["hr_bills.json", "myhr.php(对账)", "_tag_all_torrents()", "_site_rules()"],
            "write": {
                "void": "GET /tags?action=hrbills_void&hash=<h>&reason=..&confirm=1",
                "reconcile": "GET /agent/hr/reconcile?site=<dom>&live=1",
                "reseed_missing": "GET /tags?action=hr_reconcile&site=<dom>&confirm=1",
            },
        }

    def get_hr_bills(self, site: str = "", live: int = 0) -> Response:
        """``GET /hr/bills``：H&R 账单按站分组（只读）。"""
        try:
            data = self._hr_bills_by_site(site, live)
            return Response(success=True, message="ok", data=data)
        except Exception as e:  # noqa: BLE001
            self._log(f"H&R账单报表失败: {e}", "error")
            return Response(success=False, message=str(e))
