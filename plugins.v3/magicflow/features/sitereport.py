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

# ★ 15.2.0 静默桶再拆「出身轴」（与身份轴正交，仅静默桶使用）：
#   池 = 种子账本（mf_seed）在册；辅种副本 = 全站辅种账（mf_reseed）在册；无主 = 两本都没有。
ORIGIN_POOL = "池"
ORIGIN_RESEED = "辅种副本"
ORIGIN_NONE = "无主"
_ORIGIN_ORDER = (ORIGIN_POOL, ORIGIN_RESEED, ORIGIN_NONE)

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
        """★ 17.3.0：报表**唯一口径**在 ``features/reportview.py``。

        本方法保留为兼容入口（``/site/seeds`` 与 ``/agent/site/seeds`` 都走它）：
        真值源改为**账本**（种子账本 ∪ hr_bills ∪ 资源账本），下载器快照只补传输态；
        与 ``/agent/silent``、``/agent/hr/bills`` 三个视图共用同一台账，数字必然一致。
        旧签名/旧字段组不变（新增字段只增不改）。
        """
        return self._rv_site_data(site, live)

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
        """★ 17.3.0：改调统一口径（``reportview.view_hr``）。

        与旧版的差别（都是修口径）：``rule=unknown`` 的影子账（backfill）**不再被丢弃**，
        归入显式的「未定性」一类并在 ``totals.unclassified`` 单列；站点清单也随之为全量。
        旧字段组（``totals`` / ``sites[].bills`` / ``items`` / ``policy`` / ``write``）保持不变。
        """
        return self._rv_hr_data(site, live)

    def get_hr_bills(self, site: str = "", live: int = 0) -> Response:
        """``GET /hr/bills``：H&R 账单按站分组（只读）。"""
        try:
            data = self._hr_bills_by_site(site, live)
            return Response(success=True, message="ok", data=data)
        except Exception as e:  # noqa: BLE001
            self._log(f"H&R账单报表失败: {e}", "error")
            return Response(success=False, message=str(e))
