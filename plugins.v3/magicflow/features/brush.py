# -*- coding: utf-8 -*-
"""魔流 · brush —— 刷流主流程（候选筛选 → 复用/补种 → 清理低效）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import copy
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import fields
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse


from app.sdk.logging import logger

from ..bonus import (
    MagicPolicy,
    TorrentBonusInfo,
    candidate_ref_weeks,
    site_ceiling,
    score_candidate,
    calc_torrent_bonus,
)
from ..downloader_ops import (
    DownloaderAdapter,
    TorrentInfo,
    TorrentFetchFlowControl,
    _kv,
    QB_DEAD_STATES,
    QB_DOWNLOADING_STATES,
    QB_PAUSED_STATES,
)
from ..fingerprint import fingerprint, info_hash
from ..fetcher import (
    SITE_TZ_OFFSET_HOURS,
    NP_FREE_SPSTATES,
    FilterPolicy,
    SiteCandidateTorrent,
    SiteFetcher,
    filter_candidates,
    free_time_ok,
    parse_mteam_rows,
    parse_yema_rows,
    get_default_brush_filter_policy,
    get_default_filter_policy,
)
from ..collect import api_channel as _api_channel_of
from ..persistence import OperationItem, WorkReport
from ..dtier import TierCache
from ..sitecap import (
    FW_UNKNOWN,
    FW_MTEAM,
    FW_GAZELLE,
    FW_UNIT3D,
    norm_domain,
)
from ..tags import (
    MARK_REUSE,
    STATE_BONUS,
    STATE_BRUSH,
    parse_tag,
)
from ..sites.formula_fetch import (
    FormulaCapture,
    _norm_title as normalize_title,
)


from ..common import (
    BROWSE_PAGES,
    CROSSSEED_POOL_MAX,
    FREE_INDEX_PAGES,
    MAX_PAGE_CURSOR,
    MagicFlowTaskConfig,
    SITE_FETCH_BACKOFF,
    SITE_FETCH_TTL,
    TORRENT_DL_RETRIES,
    TORRENT_FETCH_DEADLINE,
    TORRENT_FETCH_PER_TIMEOUT,
    TORRENT_FETCH_WORKERS,
    _SizeIndex,
    task_is_participating,
    task_is_running,
    enabled_of_run_mode,
    RUN_MODE_SEEDING,
)


class BrushMixin:
    """brush 功能集（原 MagicFlow 方法原样搬入）。"""


    def _cache_cands(self) -> TierCache:
        """候选列表缓存(内存热层 + FileCache 冷层)。编解码 = SiteCandidateTorrent ↔ dict。"""
        cache = getattr(self, "_tier_cand_obj", None)
        if cache is None:
            cache = self._tier_cand_obj = TierCache(
                "cand",
                base=self._cache_base(),
                encode=lambda lst: [x.to_dict() for x in (lst or []) if hasattr(x, "to_dict")],
                decode=lambda rows: [
                    c for c in (SiteCandidateTorrent.from_dict(r) for r in (rows or []))
                    if c is not None
                ],
            )
        return cache

    def _cache_official(self) -> TierCache:
        """站点官种标题缓存(内存热层 + FileCache 冷层)。

        旧版是纯内存 dict → 每次热重载清空 → 又真抓 2 页(实测站点已被 PV 封禁后
        仍在 07:57 抓了一次);且不走 PV 闸门。
        """
        cache = getattr(self, "_tier_official_obj", None)
        if cache is None:
            cache = self._tier_official_obj = TierCache("official", base=self._cache_base())
        return cache

    def _cache_formula(self) -> TierCache:
        """站点公式缓存(内存热层 + FileCache 冷层)。编解码 = FormulaCapture ↔ dict。"""
        cache = getattr(self, "_tier_formula_obj", None)
        if cache is None:
            def _decode(data):
                if not isinstance(data, dict):
                    return None
                names = {f.name for f in fields(FormulaCapture)}
                try:
                    return FormulaCapture(**{k: v for k, v in data.items() if k in names})
                except Exception:  # noqa: BLE001
                    return None

            cache = self._tier_formula_obj = TierCache(
                "formula",
                base=self._cache_base(),
                encode=lambda cap: cap.as_dict() if hasattr(cap, "as_dict") else cap,
                decode=_decode,
            )
        return cache

    def _fetch_site_candidates(
        self,
        task: "MagicFlowTaskConfig",
        pages: int = 1,
        start_page: int = 0,
        np_free: bool = False,
        force_main: bool = False,
    ) -> List[Any]:
        """站点级共享抓取(single-flight + 短 TTL)。

        **同一站点只抓一份候选列表**,刷流与魔力任务共用--二者只是**排序/筛选**不同,
        数据源是同一份(把「N 个任务 × 每任务一次抓取」压成「1 次」),避免几十个任务
        同站重复取列表触发流控。
          - 缓存 key 只含 **站点 + 翻页数**(不含任务/免费标志/起始页)→ 同站所有任务共享;
          - 同 key 并发时用锁「单飞」:先到的抓,后到的等它填缓存再复用;
          - 返回**浅拷贝**(每任务各自改 _score/raw/real_hash,互不串味)。

        ``np_free`` 保留仅为兼容:现在统一抓**完整列表**,刷流侧自行筛免费
        (见 _brush_impl),以保证魔力任务也能用同一份数据。

        注意:站点「最新 N 页」是**按发布时间的窗口**,会**漏掉较早的免费种**
        (实测 Pttime:最新 150 条只有 5 个免费,而免费种散落在前 400 条里共 15 个)。
        故本函数在最新页之外**额外并上 NexusPHP 免费定向视图**(spstate=2/4,一页即全),
        去重后作为同站唯一一份候选--这样刷流筛免费能拿全、魔力也能吃到这批免费种。
        """
        site_key = (
            str(getattr(task, "site_domain", "") or "") or f"site:{getattr(task, 'site_id', '')}"
        ).strip().lower()
        # 一份数据:同站(同翻页)共享同一 key;刷流/魔力只是用不同的排序/筛选消费它。
        # ★ 3.7.1:key 含 start_page(旧版漏了它 → 游标深翻永远命中第 0 页);
        #   缓存由 TierCache 托管(内存热层 + FileCache 冷层),热重载/重启不丢,不再烧 PV。
        # ★ 站点能力（sitecap）：只要免费的站（NexusPHP 有 spstate 免费索引）→ 只抓免费索引。
        #   主列表「最新 N 页」天生漏老免费种、而且要把 3 页；免费索引 1~2 个请求就够。
        try:
            _policy = self._build_filter_policy(task)
        except Exception:  # noqa: BLE001
            _policy = None
        _want_free = bool(
            _policy is not None and (getattr(_policy, "free_only", False) or getattr(_policy, "double_free_only", False))
        )
        _cap = self.sitecaps().get(str(getattr(task, "site_domain", "") or ""))
        # ★ 3.10.0 统一选种路由：开了跨站且**主列表能读到促销列**（promo_in_list）时，
        #   不再抓「免费索引」——一份主列表就够：免费的直接下、非免费的走跨站，
        #   既省掉一次抓取（1 PV/站/轮），也省掉「免费索引 + 主列表」两套数据的分歧。
        _cs_route = bool(
            getattr(task, "crossseed_enabled", False)
            and getattr(_cap, "promo_in_list", False)
        )
        _use_free = bool(
            (not force_main)
            and _want_free
            and (not _cs_route)
            and getattr(_cap, "free_index", False)
        )
        _free_tried = False
        cache_key = f"{site_key}|{'free' if _use_free else 'main2'}|{int(pages)}|{int(start_page)}"
        cache = self._cache_cands()
        hit = cache.get(cache_key, SITE_FETCH_TTL)
        if hit is not None:
            return [copy.copy(c) for c in hit]

        locks = getattr(self, "_site_fetch_locks", None)
        if locks is None:
            locks = self._site_fetch_locks = {}
        lock = locks.setdefault(cache_key, threading.Lock())
        with lock:
            # double-check:可能已被同站的其他任务填充
            hit = cache.get(cache_key, SITE_FETCH_TTL)
            if hit is not None:
                return [copy.copy(c) for c in hit]
            # 站点级失败冷却(共享给同站所有任务):上次没抓到 → 冷却期内不再重试,避免反复空打
            backoff = getattr(self, "_site_backoff", None)
            if backoff is None:
                backoff = self._site_backoff = {}
            until = float(backoff.get(site_key, 0.0) or 0.0)
            if time.time() < until:
                self._log(
                    f"魔流 [{task.name}] 站点 {site_key} 冷却中"
                    f"(剩余 {int(until - time.time())}s),本轮跳过抓取"
                )
                return []
            # ★ 站点「每日访问次数已达上限」→ 今日内不再抓(避免继续空打;实测 PTT 300PV/天)
            _sid = int(getattr(task, "site_id", 0) or 0)
            _pv_until = self._pv_block_reason(_sid)
            if _pv_until:
                self._log(
                    f"魔流 [{task.name}] 站点 {site_key} 今日访问次数已达上限,暂停抓取至 {_pv_until}"
                )
                return []
            # ★ 3.44.0 API 鉴权站（馒头）：不走页面抓取，走官方 API（促销/热度齐全，无需 cookie）
            _api_site = False
            _cref = None
            try:
                _cref = self._collect_ref()
                _api_site = bool(_cref is not None and _cref.is_api_site(_sid))
            except Exception:  # noqa: BLE001
                _api_site = False
            # ★ 只抓免费：NexusPHP 免费索引（spstate）——两个任务类型需求相同，共用这一份
            if _use_free:
                _sp = tuple(getattr(_cap, "free_spstates", ()) or NP_FREE_SPSTATES)
                # ★ 免费索引每轮只翻 FREE_INDEX_PAGES 页：免费池每小时才动几条，
                #   深翻是用任务里的 browse_pages 那个量（主列表口径），对免费池是浪费 PV。
                _fpages = max(int(FREE_INDEX_PAGES or 1), 1)
                _fwant = max(len(_sp) * _fpages, 1)
                _free_tried = True
                if not self._pv_allow(_sid, "browse", want=_fwant):
                    self._log(
                        f"魔流 [{task.name}] 站点 {site_key} PV 预算将尽"
                        f"(今日 {self._pv_ledger().today_total(_sid)}/{self._pv_budget(_sid)}),本轮跳过抓取",
                        "warning",
                    )
                    return []
                fetcher = SiteFetcher()
                if not fetcher.is_available:
                    return []
                _site = self._get_site(_sid)
                _fc: List[Any] = []
                if _site is not None and getattr(_site, "cookie", None):
                    self._pv_spend(_sid, "browse", _fwant)
                    _sp_stats: Dict[int, int] = {}
                    try:
                        _fc = fetcher.browse_site_np_free(
                            _site, spstates=_sp, pages=_fpages, stats=_sp_stats
                        ) or []
                    except Exception as err:  # noqa: BLE001
                        self._log(f"魔流 [{task.name}] 站点 {site_key} 免费索引抓取失败:{err}", "warning")
                        _fc = []
                    # ★ 自适应：某个 spstate 一条新种都没带回（站点把 2/4 当同一视图）→
                    #   记下有效集合，下轮少打一次，直接省 PV
                    _dup_sp = [int(x) for x, n in _sp_stats.items() if not n]
                    if _dup_sp and len(_sp) > 1:
                        _keep = tuple(int(x) for x in _sp if int(x) not in _dup_sp)
                        if _keep and len(_keep) < len(_sp):
                            try:
                                self.sitecaps().learn(
                                    norm_domain(str(getattr(task, "site_domain", "") or "")),
                                    getattr(_cap, "framework", FW_UNKNOWN) or FW_UNKNOWN,
                                    f"free-spstate-dedup:{list(_keep)}",
                                    source="probe",
                                    free_index=True,
                                    free_spstates=_keep,
                                )
                                self._log(
                                    f"魔流 [{task.name}] 站点 {site_key} 免费索引 spstate={_dup_sp}"
                                    f" 无新增（与 {list(_keep)} 同视图），后续只抓 {list(_keep)}"
                                )
                            except Exception:  # noqa: BLE001
                                pass
                _fc = list(_fc)
                if _fc:
                    self._log(
                        f"魔流 [{task.name}] 站点 {site_key} 免费索引返回 {len(_fc)} 个候选"
                        f"(spstate={'/'.join(str(x) for x in _sp)}, {_fpages} 页)"
                    )
                    cache.set(cache_key, _fc, SITE_FETCH_TTL)
                    backoff.pop(site_key, None)
                    return [copy.copy(c) for c in _fc]
                # 免费索引拿不到（不是 NexusPHP / 无 Cookie / 被封）→ 学一次，本轮回退主列表
                try:
                    self.sitecaps().learn(
                        norm_domain(str(getattr(task, "site_domain", "") or "")),
                        getattr(_cap, "framework", FW_UNKNOWN) or FW_UNKNOWN,
                        "free-index-empty",
                        source="probe",
                        free_index=False,
                        free_spstates=(),
                    )
                except Exception:  # noqa: BLE001
                    pass
                self._log(
                    f"魔流 [{task.name}] 站点 {site_key} 免费索引为空，本轮回退主列表抓取",
                    "warning",
                )
                cache_key = f"{site_key}|main2|{int(pages)}|{int(start_page)}"
            # ★ 3.7.1 PV 预算闸门(主动):今日已用接近预算 → 提前收手,比「被封后才停」更靠前
            _want = max(int(pages), 1) + len(NP_FREE_SPSTATES)
            if not self._pv_allow(_sid, "browse", want=_want):
                self._log(
                    f"魔流 [{task.name}] 站点 {site_key} PV 预算将尽"
                    f"(今日 {self._pv_ledger().today_total(_sid)}/{self._pv_budget(_sid)}),本轮跳过抓取",
                    "warning",
                )
                return []
            fetcher = SiteFetcher()
            if not fetcher.is_available:
                return []
            cands: List[Any] = []
            if not _api_site:
                self._pv_spend(_sid, "browse", max(int(pages), 1))  # PV 账本:主列表翻 pages 页
            _np_main = False
            if _api_site:
                # ★ 3.44.0 馒头：官方 API 取候选（含 discount 促销 + seeders/leechers）
                cands = self._api_site_candidates(task, _cref, pages=pages, start_page=start_page)
                _np_main = True
            # ★ 主列表优先走「NexusPHP 直连 + 自解析」：SDK browse 经常拿不到促销列，
            #   downloadvolumefactor 恒为 0.0（**所有种都被当成免费**）→ 魔力/跨站判定全错。
            #   自解析 `_parse_np_rows` 读的是页面真实促销标记（pro_free / promotion free）。
            _m_site = self._get_site(_sid)
            _m_fw = str(getattr(_cap, "framework", FW_UNKNOWN) or FW_UNKNOWN)
            # 非 NexusPHP 家族（馒头 / Gazelle / UNIT3D 等）的列表页不是 NexusPHP 皮肤，
            # 硬套自解析只会白跑一次请求；这类站（如馒头走官方 API）SDK 反而能拿到真实促销列。
            _m_try_np = _m_fw not in (FW_MTEAM, FW_GAZELLE, FW_UNIT3D)
            if (
                _m_try_np
                and _m_site is not None
                and getattr(_m_site, "cookie", None)
                and (force_main or bool(getattr(_cap, "free_index", False)))
            ):
                try:
                    _mc = fetcher.browse_site_np_free(
                        _m_site,
                        pages=(1 if force_main else max(int(pages), 1)),
                        start_page=start_page,
                        main=True,
                    ) or []
                except Exception as _merr:  # noqa: BLE001
                    self._log(
                        f"魔流 [{task.name}] 站点 {site_key} 主列表直连抓取失败:{_merr}",
                        "warning",
                    )
                    _mc = []
                if _mc:
                    cands = list(_mc)
                    _np_main = True
                    _nf_mc = sum(1 for _c in cands if not getattr(_c, "is_free", False))
                    self._log(
                        f"魔流 [{task.name}] 站点 {site_key} 主列表(自解析)返回 {len(cands)} 个候选"
                        f"(非免费 {_nf_mc})"
                    )
            if not _np_main:
                try:
                    cands = fetcher.browse_site(
                        task.site_domain,
                        rss_support=getattr(task, "rss_support", False),
                        pages=pages,
                        start_page=start_page,
                    ) or []
                except Exception as err:  # noqa: BLE001
                    self._log(f"魔流 [{task.name}] 站点抓取失败:{err}", "warning")
                    cands = []
            cands = list(cands)
            self._log(
                f"魔流 [{task.name}] 站点 {site_key} browse_site 返回 {len(cands)} 个候选"
                f"(site_id={_sid})",
                "debug",
            )
            # 补充：NexusPHP 免费定向视图（最新页窗口天生漏免费种，见上）。
            # 失败/非 NexusPHP 站点返回空，静默忽略，不影响最新页结果。
            try:
                _can_free = bool(getattr(_cap, "free_index", False)) and not _free_tried and not force_main
                site = self._get_site(int(getattr(task, "site_id", 0) or 0)) if _can_free else None
                if site and getattr(site, "cookie", None):
                    self._pv_spend(_sid, "browse", len(NP_FREE_SPSTATES))  # PV 账本:免费定向视图
                    np_free = fetcher.browse_site_np_free(site, pages=1) or []
                    if np_free:
                        def _ck(c: Any) -> str:
                            return (
                                getattr(c, "page_url", "")
                                or getattr(c, "hash", "")
                                or getattr(c, "title", "")
                            )

                        by_key = {_ck(c): c for c in cands if _ck(c)}
                        added = 0
                        upgraded = 0
                        for c in np_free:
                            k = _ck(c)
                            if not k:
                                continue
                            old = by_key.get(k)
                            if old is None:
                                by_key[k] = c
                                cands.append(c)
                                added += 1
                        else:
                            # ★ 同一种：把「限时免费到期时间」等促销信息并进已有候选。
                            # 最新页走 SDK（不含到期时间），免费定向视图才有 → 必须回填，
                            # 否则「免费即将到期」闸门对最新页那批种失效。
                            try:
                                if float(getattr(c, "free_remaining_sec", -1.0) or -1.0) >= 0:
                                    old.free_until = getattr(c, "free_until", "") or ""
                                    old.free_remaining_sec = c.free_remaining_sec
                                    if getattr(c, "is_free", False):
                                        old.is_free = True
                                        old.is_double_free = bool(
                                            getattr(c, "is_double_free", False)
                                        )
                                        old.downloadvolumefactor = getattr(
                                            c, "downloadvolumefactor", 0.0
                                        )
                                        old.uploadvolumefactor = getattr(
                                            c, "uploadvolumefactor", 1.0
                                        )
                                        old.volume_factor = getattr(c, "volume_factor", 0.0)
                                    upgraded += 1
                            except Exception:  # noqa: BLE001
                                pass
                    if added or upgraded:
                        self._log(
                            f"魔流 [{task.name}] 站点共享列表补充免费定向 {added} 个"
                            f"（最新页窗口漏掉的免费种）"
                            + (f"，回填到期时间 {upgraded} 个" if upgraded else "")
                        )
            except Exception as err:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 免费定向补充失败（忽略）：{err}", "warning")
            if cands:
                cache.set(cache_key, cands, SITE_FETCH_TTL)
                backoff.pop(site_key, None)
            else:
                # 没抓到（失败/空）：不缓存空表（免得把站点"冻"满 TTL），改用显式冷却
                backoff[site_key] = time.time() + SITE_FETCH_BACKOFF
                self._log(
                    f"魔流 [{task.name}] 站点 {site_key} 未取到候选，冷却 "
                    f"{int(SITE_FETCH_BACKOFF)}s 后重试",
                    "warning",
                )
            return [copy.copy(c) for c in cands]

    # ---------------------------------------------------------
    # 调度与服务实现
    # ---------------------------------------------------------

    def _api_site_candidates(
        self,
        task: "MagicFlowTaskConfig",
        collect_ref: Any,
        *,
        pages: int = 1,
        start_page: int = 0,
    ) -> List[Any]:
        """★ 3.44.0 API 站（馒头）候选：走官方 API（促销 / 热度 / 无需 cookie）。

        下载直链不在这里取（那是 1 条种 1 次请求）——留到候选**入选**时由
        :meth:`_cand_enclosure` 现取，见 ``_prefetch``。
        """
        sid = int(getattr(task, "site_id", 0) or 0)
        cands = self._api_candidates_for_site(sid, pages=pages, start_page=start_page)
        self._log(
            f"魔流 [{task.name}] API 候选 {len(cands)} 个"
            f"(免费 {sum(1 for _c in cands if getattr(_c, 'is_free', False))})"
        )
        return cands

    def _api_candidates_for_site(
        self,
        site_id: Any,
        *,
        pages: int = 1,
        start_page: int = 0,
        quiet: bool = False,
    ) -> List[Any]:
        """★ 3.44.0/3.45.0 API 站候选（可被诊断端点直接调用）。

        ★ 3.45.0：按**通道表**分流 —— 馒头走 ``search``（JSON 体），
        叶PT走 ``list``（JSON 体，``downloadPromotionType=free``，单页上限 40）。
        """
        sid = int(site_id or 0)
        site = self._get_site(sid)
        c = self._collect_ref()
        if site is None or c is None:
            return []
        tname = ""
        try:
            tname = str(_api_channel_of(site)[0] or "")
        except Exception:  # noqa: BLE001
            tname = ""
        sv = c.site(sid)
        page = int(start_page or 0) + 1
        if tname == "yemapt":
            size = min(40, max(20, int(pages) * 20))
            res = sv.api_list(page=page, size=size, promo="free")
            rows = res.get("rows") or []
            parser = parse_yema_rows
        else:
            size = min(200, max(50, int(pages) * 100))
            res = sv.api_search("", page=page, size=size)
            rows = res.get("rows") or []
            parser = parse_mteam_rows
        if not res.get("ok"):
            if not quiet:
                self._log(f"魔流 [API] 站点 {sid} 候选抓取失败:{res.get('error')}", "warning")
            return []
        return parser(
            rows,
            site_name=str(getattr(site, "name", "") or ""),
            domain=str(getattr(site, "domain", "") or ""),
            site_url=str(getattr(site, "url", "") or ""),
            site_id=sid,
            site_proxy=bool(getattr(site, "proxy", 0)),
        )

    def _cand_enclosure(self, cand: Any) -> str:
        """★ 3.44.0 取候选的下载链接；API 站（馒头）候选现场换签名直链。

        * 普通站：返回候选自带的 ``enclosure``；
        * API 站：候选没有 enclosure → 调 ``/torrent/genDlToken`` 现取（**只为已入选的
          候选花这 1 次请求**），取到后写回候选，供后续复用。
        """
        url = str(getattr(cand, "enclosure", "") or "")
        if url:
            return url
        tid = str(getattr(cand, "api_tid", "") or "")
        if not tid:
            return ""
        sid = int(getattr(cand, "site_id", 0) or 0)
        if not sid:
            sid = self._site_id_by_domain(str(getattr(cand, "site_domain", "") or ""))
        c = self._collect_ref()
        if not sid or c is None:
            return ""
        try:
            r = c.site(sid).api_dl_token(tid)
        except Exception as err:  # noqa: BLE001
            self._dbg(f"馒头:取下载直链异常 {tid}: {err}")
            return ""
        if not r.get("ok"):
            self._dbg(f"馒头:取下载直链失败 {tid}: {r.get('error')}")
            return ""
        url = str(r.get("url") or "")
        if url:
            try:
                cand.enclosure = url
            except Exception:  # noqa: BLE001
                pass
        return url

    def brush(self, task_id: str) -> None:
        """抓取站点候选并补充优质魔力种子(刷流,带并发保护)。"""
        task = self._get_task_config(task_id)
        self._apply_task_traffic_limit()
        self._apply_seed_upload_limit()
        if task and self._maybe_autostop_for_goal(task):
            return
        if not self._acquire_worker_slot(f"刷流·{task.name if task else task_id}"):
            return
        if not self._try_begin_run(task_id):
            if task:
                self._log(f"魔流 [{task.name}] 上一轮仍在执行,跳过本轮")
            self._release_worker_slot()
            return
        started = time.time()
        record = None
        if self._store:
            record = self._store.journal.add(
                task_id=task_id,
                kind="run",
                items=[OperationItem(hash="", title="开始执行", reason="")],
            )
        try:
            summary = self._brush_impl(task_id) or {}
            duration = time.time() - started
            if self._store:
                if record:
                    self._store.journal.finalize(
                        record.operation_id,
                        "completed" if summary.get("status") != "failed" else "failed",
                        items=self._run_items(summary, duration),
                        duration=duration,
                        error_message=summary.get("reason") if summary.get("status") == "failed" else None,
                    )
                self._settle(WorkReport(
                    task_id=task_id,
                    source="brush",
                    status=summary.get("status", ""),
                    reason=summary.get("reason", ""),
                    duration=duration,
                    added=summary.get("added"),
                    deleted=summary.get("deleted"),
                    kept=summary.get("kept"),
                    reused=summary.get("reused"),
                ))
        except Exception as e:
            import traceback
            logger.error(f"魔流 brush 异常: {e}\n{traceback.format_exc()}")
            if self._store:
                if record:
                    self._store.journal.finalize(
                        record.operation_id, "failed", error_message=str(e), duration=time.time() - started
                    )
                self._settle(WorkReport(
                    task_id=task_id, source="brush", status="failed",
                    reason=str(e), duration=time.time() - started,
                ))
        finally:
            self._end_run(task_id)
            self._release_worker_slot()

    def _same_site_keys(self, task: MagicFlowTaskConfig) -> Set[str]:
        """本站的 tracker 域名匹配键(用于「同站纳管」)。"""
        dom = (getattr(task, "site_domain", "") or "").strip().lower()
        if not dom:
            try:
                site = self._get_site(task.site_id)
                if site:
                    dom = (getattr(site, "domain", "") or "").strip().lower()
                    if dom and not task.site_domain:
                        task.site_domain = dom
            except Exception:
                dom = dom or ""
        if not dom:
            return set()
        keys = {dom}
        # 去掉常见前缀后也能匹配(www. / tracker. / pt.)
        for prefix in ("www.", "tracker.", "pt.", "t."):
            if dom.startswith(prefix) and len(dom) > len(prefix):
                keys.add(dom[len(prefix):])
        return {k for k in keys if k}

    def _same_site_torrents(self, task: MagicFlowTaskConfig, *, snap: Optional[Dict[str, Any]] = None) -> List[str]:
        """本任务名下的种子 hash：按「站点 + 职务」识别（取代「标签命中 ∪ taken_by」双源）。

        - 站点：种子 tracker(announce) 域名匹配本站 domain（与 ``_adopt_same_site`` 同口径）。
        - 职务：账本 ``state`` == 本任务的职务态（刷流任务→刷流 / 其余→魔力），
          **撞站（同站多任务）时靠它区分**，取代 taken_by 租约。
        - qB 快照 tracker 常为空 → 逐 hash 兜底 ``tracker_domain``。
        - 跨站来源份（H&R 保种期内）不属于任何任务 → 排除。
        """
        keys = self._same_site_keys(task)
        if not keys:
            return []
        try:
            _, state = self._task_site_state(task)
        except Exception:  # noqa: BLE001
            state = STATE_BRUSH if str(getattr(task, "task_type", "bonus") or "bonus").lower() == "brush" else STATE_BONUS
        if snap is None:
            try:
                snap = self._tag_all_torrents()
            except Exception:  # noqa: BLE001
                return []
        try:
            _cs_src_hashes = self._crossseed_source_hashes() or set()
        except Exception:  # noqa: BLE001
            _cs_src_hashes = set()
        store = self._tag_state()
        dl = None
        out: List[str] = []
        seen: Set[str] = set()
        for h, t in (snap or {}).items():
            hh = str(h or "").strip().lower()
            if not hh or hh in seen:
                continue
            if hh in _cs_src_hashes:
                continue
            # 职务过滤：只认本任务的职务态（撞站时刷流/魔力各归各）
            try:
                rec = store.get(hh) or {}
            except Exception:  # noqa: BLE001
                rec = {}
            st = str(rec.get("state") or "")
            if st != state:
                continue
            tr = str(getattr(t, "tracker", "") or "").strip()
            host = ""
            try:
                host = str((urlparse(tr).hostname or "") or "").lower()
            except Exception:  # noqa: BLE001
                host = ""
            if not host and tr:
                try:
                    import re as _re
                    _m = _re.search(r"([a-z0-9.-]+\.[a-z]{2,})", tr.lower())
                    host = _m.group(1) if _m else ""
                except Exception:  # noqa: BLE001
                    host = ""
            if not host:
                # 逐 hash 兜底（qB tracker 字段常为空）
                try:
                    if dl is None:
                        dl = self._get_downloader()
                    if dl is not None:
                        host = str(dl.tracker_domain(hh) or "").strip().lower()
                except Exception:  # noqa: BLE001
                    host = ""
            if host and any(k in host for k in keys):
                out.append(hh)
                seen.add(hh)
        return out

    def _adopt_same_site(self, task: MagicFlowTaskConfig, downloader: DownloaderAdapter) -> Dict[str, int]:
        """同站纳管:把下载器中「属于本站」的已有种子补打本任务 tag。

        MagicFlow 只在站点**候选列表**里找新种,会漏掉本机早已在做的同站种子
        (IYUU / 其它插件 / 手动添加)。这些种子同样为该站产出魔力,理应纳入托管
        (计入容量与保护),否则既不计魔力、又可能被重复下载。

        识别方式:种子的 tracker(announce)域名与本站 domain 匹配。
        只**追加**标签(不覆盖其它标签),不下载、不校验、不改动其它站点。

        ★ 保护策略:本插件自己下载/复用的(刷流用)照常按效率清理;
          本机**早已存在**的同站种子(IYUU / 其它插件 / 手动添加 / 自己下载的影视资源)
          一律纳入「自有资源」集合并 **永久保护**(不参与任何删种)。
        """
        keys = self._same_site_keys(task)
        if not keys:
            return {"matched": 0, "adopted": 0, "already": 0, "protected": 0}
        store = self._store
        adopted_set = store.get_adopted(task.id) if store else set()
        matched = adopted = already = 0
        to_tag: List[str] = []
        to_adopt: List[str] = []
        # ★ 跨站来源份（H&R 保种期内）不属于任何任务：不纳管、不改标签、不保护
        try:
            _cs_src_hashes = self._crossseed_source_hashes()
        except Exception:  # noqa: BLE001
            _cs_src_hashes = set()
        for t in downloader.get_raw_torrents():
            tr = str(_kv(t, "tracker", "") or "").strip()
            h = str(_kv(t, "hash", "") or "").lower()
            host = ""
            if tr:
                try:
                    host = (urlparse(tr).hostname or "").lower()
                except Exception:
                    host = ""
            if not host and h:
                # ★ 7.16.1 兜底：qB 的 tracker 字段对「暂停 / 未汇报」的种**常为空**
                #   （本机实测 250/726），但逐 hash 的 torrents_trackers 能拿到真实
                #   announce 域名。旧代码 `if not tr: continue` 直接把这类种排除 →
                #   做种中任务永远纳管不到它们（PT时间 27 个种全被漏掉的实际 bug）。
                try:
                    host = str(downloader.tracker_domain(h) or "").strip().lower()
                except Exception:  # noqa: BLE001
                    host = ""
            if not host or not any(k in host for k in keys):
                continue
            if not h:
                continue
            matched += 1
            tags = _kv(t, "tags", "") or []
            if isinstance(tags, str):
                tags = [x.strip() for x in tags.split(",") if x.strip()]
            # ★ 跨站来源份（H&R 保种期内）不属于任何任务：不纳管、不改标签
            if h in _cs_src_hashes:
                continue
            if task.brush_tag not in list(tags):
                to_tag.append(h)

            if h in adopted_set:
                # 已纳管的自有资源:不重复保护(尊重用户在 UI 上的手动「取消保护」)
                already += 1
                continue
            # 本插件自己下载/复用的种子(刷流)→ 不保护,正常按效率清理
            if store and store.is_self_added(task.id, h):
                continue
            # 本机早已存在的同站种子 → 纳管并永久保护(用户自有资源)
            to_adopt.append(h)
            adopted += 1

        if to_tag:
            # 🔎 标签审计:纳管同站种子(打任务标签)
            self._log(
                f"[标签审计] 纳管同站种子 {len(to_tag)} 个 → 标签「{task.brush_tag}」"
            )
        if to_tag:
            self._tag_assign(task, to_tag, reason="同站纳管")
        if to_tag and self._store:
            try:
                self._store.journal.record(
                    task_id=task.id,
                    kind="tag",
                    items=[OperationItem(
                        hash="",
                        title=f"同站纳管·补标签 {len(to_tag)} 个",
                        reason=f"→「{task.brush_tag}」",
                        source="adopt",
                        tags=f"→{task.brush_tag}",
                    )],
                )
            except Exception as _jerr:
                self._log(f"记录纳管标签事件失败:{_jerr}", "warning")
        protected = 0
        if store and to_adopt:
            store.note_adopted(task.id, to_adopt)
            for h in to_adopt:
                if store.protect_torrent(task.id, h):
                    protected += 1

        if adopted:
            self._log(
                f"魔流 [{task.name}] 同站纳管:本站 tracker 种子 {matched} 个,"
                f"新纳管并保护 {adopted} 个(已在管 {already})"
            )
        return {"matched": matched, "adopted": adopted, "already": already, "protected": protected}

    def _watch_tag_integrity(self, task: MagicFlowTaskConfig, count: int) -> None:
        """托管数看门狗:与上一轮对比,骤降至一半以下 → 记「托管种异常丢失」。

        专用于捕捉"**种子还在、却不再算作本任务托管**"这类异常
        （如账本职务/身份被误算、标签被外部工具清除）。

        ★ 修复（原逻辑会**永久误报**）：
          ① 先扣掉「可解释的降幅」：上一轮正常删种（``last_deleted``）+
             本任务跟踪过、但**已从下载器消失**的种（``pub_dates`` 不在快照里）。
             真被删掉的种让托管数合理下降，不该报警；**种还在 qB 却掉出托管集**才是异常。
          ② 基线改为**跟随实况**（写当前值），不再 ``max(prev, c)`` 只升不降 ——
             否则一次真实下降后会**每一轮都刷同一条警告**（每 60s 一条，淹没真异常）。
        """
        if not self._store or count is None:
            return
        try:
            c = int(count)
        except (TypeError, ValueError):
            return
        prev = self._store.get_last_tagged_count(task.id)
        if prev >= 3 and c < prev * 0.5:
            # ① 上一轮本任务删了多少种（正常清理导致的下降）
            try:
                prev_del = int(getattr(self._store.task_states.get(task.id), "last_deleted", 0) or 0)
            except Exception:  # noqa: BLE001
                prev_del = 0
            # ② 本任务跟踪过、但已从下载器消失的种（被删 → 托管数下降属正常）
            _gone = 0
            try:
                _pd = self._store.get_pub_dates(task.id) or {}
                _snap_all = self._tag_all_torrents() or {}
                _gone = sum(1 for _h in _pd if str(_h).lower() not in _snap_all)
            except Exception:  # noqa: BLE001
                _gone = 0
            # ③ 同站其它任务的标签接手（正常归属转移）
            _moved = 0
            try:
                _site = str(getattr(task, "site_name", "") or "")
                _groups = self._tag_snapshot(getattr(task, "downloader", "qbittorrent") or "qbittorrent")
                _seen: set = set()
                for _tg, _rows in (_groups or {}).items():
                    if str(_tg) == str(getattr(task, "brush_tag", "")):
                        continue
                    _p = parse_tag(str(_tg))
                    if _p and str(_p.get("site") or "") == _site:
                        # ★ 5.0.0：身份 + 职务两条标签 → 同一颗种会在两个组里出现，按 hash 去重
                        for _row in (_rows or []):
                            _rh = str(getattr(_row, "hash", "") or "").lower()
                            if _rh:
                                _seen.add(_rh)
                _moved = len(_seen)
            except Exception:  # noqa: BLE001
                _moved = 0
            if _moved + _gone + prev_del + c >= prev * 0.8:
                self._log(
                    f"魔流 [{task.name}] 托管数变化 {prev} → {c}"
                    f"（删种 {prev_del} / 已从下载器消失 {_gone} / 同站其它标签 {_moved}，非异常）"
                )
            else:
                self._log(
                    f"魔流 [{task.name}] ⚠️ 托管数骤降 {prev} → {c}"
                    f"(可解释 删种 {prev_del}+消失 {_gone}+同站它标 {_moved} 仍不足,疑似种子还在却掉出托管集)",
                    "warning",
                )
                try:
                    self._store.journal.record(
                        task_id=task.id,
                        kind="tag",
                        items=[OperationItem(
                            hash="", source="watchdog",
                            title=f"⚠️ 托管数骤降 {prev} → {c}",
                            reason=f"删种 {prev_del}+消失 {_gone}+同站它标 {_moved} 不足以解释,疑似种子还在却掉出托管集",
                        )],
                    )
                except Exception:
                    pass
        # ★ 基线跟随实况：不再 max(prev,c)（只升不降 → 一次下降后永久误报）
        self._store.set_last_tagged_count(task.id, c)

    def _brush_impl(self, task_id: str) -> None:
        """抓取站点候选并补充优质魔力种子(刷流,v5 流程)。"""
        task = self._get_task_config(task_id)
        if not task or not task_is_running(task):
            return {"status": "skipped", "reason": "任务未启用"}
        self._log(f"魔流 [{task.name}] brush 开始(任务 {task_id})")
        if self._store:
            self._store.record_run_start(task.id)
        if task.active_time_range and not self._is_in_active_time(task.active_time_range):
            self._log(f"魔流 [{task.name}] 当前不在活跃时间段,跳过")
            return {"status": "skipped", "reason": "不在活跃时间段"}

        downloader = self._get_downloader(task.downloader)
        if not downloader or not downloader.is_available:
            self._log(f"下载器不可用: {task.downloader}", "error")
            return {"status": "failed", "reason": "下载器不可用"}

        # ---------- 0c 考核下载模式:目标达成 → 转「做种中」(停下载、保种) ----------
        try:
            ex = self._exam_download_state(task)
            if ex.get("on"):
                if ex.get("done"):
                    note = (
                        f"考核下载目标已达(本站下载增量 {ex['delta_gb']:.2f}/{ex['target_gb']:.2f}GB)"
                        "→ 转「做种中」保种(不再下载、不删种)"
                    )
                    self._log(f"魔流 [{task.name}] {note}")
                    task.run_mode = RUN_MODE_SEEDING
                    task.enabled = enabled_of_run_mode(RUN_MODE_SEEDING)
                    try:
                        self._save_config()
                        self._refresh_scheduler()
                        self._invalidate_summary()
                        self._spawn_run_mode_apply(task, "seeding")
                    except Exception as err:  # noqa: BLE001
                        self._log(f"魔流 [{task.name}] 考核下载达标后切换失败:{err}", "warning")
                    return {"status": "noop", "reason": note, "added": 0, "reused": 0, "deleted": 0, "kept": 0}
                self._log(
                    f"魔流 [{task.name}] 考核下载模式:本站下载增量 {ex['delta_gb']:.2f}/"
                    f"{ex['target_gb']:.2f}GB(还差 {ex['remain_gb']:.2f}GB)→ 本轮允许非免费种",
                    "warning",
                )
        except Exception as _exe:  # noqa: BLE001
            self._log(f"魔流 [{task.name}] 考核下载模式检查异常:{_exe}", "warning")

        # ---------- 0a 保存目录守卫 ----------
        # 保存目录为空时若继续加种,下载器会回落到「默认目录」(历史上是 /vol3 下载盘),
        # 刷流会一路把默认盘灌满。这里直接拒绝,避免误伤。
        if not str(task.save_path or "").strip():
            self._log(
                f"魔流 [{task.name}] 未配置保存目录(save_path),已跳过--"
                f"避免种子落到下载器默认目录把盘灌满",
                "error",
            )
            return {"status": "skipped", "reason": "未配置保存目录"}

        # ---------- 0 先清理(放在**入口检查之前**)----------
        # 池满时不再直接 noop,而是先清掉零魔 / 做种人数过多 / 低于门槛 / 无进度的种子
        # 腾出空间与名额,再进入入口检查决定是否抓取。Master 口径:清理任务前置。
        try:
            _cl = self._cleanup_round(task, downloader)
            self._note_decision(task.id, (_cl or {}).get("decision"))
            self._trend_sample_task(task, _cl)
            if _cl.get("deleted"):
                self._log(
                    f"魔流 [{task.name}] 入口前清理:删 {_cl['deleted']} 个"
                    f"(无进度 {_cl.get('no_progress', 0)} / 低效 {_cl.get('low_eff', 0)})"
                )
        except Exception as _cle:
            self._log(f"魔流 [{task.name}] 入口前清理异常: {_cle}", "warning")

        # ---------- 0b 同站纳管:把本机上「属于本站」的已有种子补打 tag ----------
        # 本插件自己刷流加的照常按效率清理;本机早已存在的同站种子(IYUU/其它插件/
        # 手动添加/自己下载的影视资源)纳管并**永久保护**,绝不被删种。
        try:
            _ad = self._adopt_same_site(task, downloader) or {}
            if int(_ad.get("adopted") or 0) > 0:
                self._emit_event(
                    "tag", action="同站纳管", level="info", task_id=task.id,
                    reason=f"新接管 {int(_ad.get('adopted') or 0)} 个（匹配 {int(_ad.get('matched') or 0)}）",
                    metrics={"count": int(_ad.get("adopted") or 0), "matched": int(_ad.get("matched") or 0)},
                    dedup_key=f"adopt:{task.id}:{int(_ad.get('adopted') or 0)}",
                )
        except Exception as _ade:
            self._log(f"魔流 [{task.name}] 同站纳管异常: {_ade}", "warning")

        try:
            # ---------- 本任务托管(tag)快照 ----------
            # ★ 全量快照:从下载器一次拉取全部种子,按本任务 tag 过滤。
            #   不走 get_torrents(tags=[tag])--qB 对「正在下载」的种子有时会漏掉,
            #   导致 dl_concurrent 偏小 → concurrency_full 永远 False → 持续抓取。
            #   用 get_raw_torrents() 全量取,本地 filter tag + state,不依赖 qB 过滤逻辑。
            # ★ 下载器全量快照:用 get_torrents_by_tag() 一次性拉解析好的 TorrentInfo,
            #   避免 get_torrents(tags=[tag]) 对 downloading 状态漏计,也保证 managed 有完整属性。
            # ★ 本任务名下的种：站点×职务（标签/归属已退役，不再按 tag+claim）
            managed = self._task_managed_torrents(task)
            managed_hashes = {(t.hash or "").lower() for t in managed if t.hash}
            base_cnt = len(managed)
            base_size = round(sum(float(getattr(t, "size_gb", 0) or 0) for t in managed), 3)
            # ★ 下载中计数:走同一份全量快照,不依赖 qB tags 过滤(已验证 downloading 状态会漏)
            dl_concurrent = sum(
                1 for t in managed
                if str(getattr(t, "state", "") or "").lower() in QB_DOWNLOADING_STATES
            )
            dl_limit = max(int(task.max_download_concurrent or 10), 1)
            self._log(
                f"魔流 [{task.name}] 托管 {base_cnt} 个 / {base_size:.2f}GB"
                f"(下载中 {dl_concurrent} 个),标签「{task.brush_tag}」"
            )

            formula_params = self._build_formula_params(task)
            official_titles = self._site_official_titles(task.site_id)
            protected_hashes = self._store.get_protected_torrents(task.id) if self._store else set()
            self._backfill_pub_dates(task, managed)
            managed_bonus = self._convert_to_bonus_list(managed, formula_params, self._task_pub_dates(task), getattr(task, "ti_source", "publish"), self._site_ni_map(task.site_id, managed), official_titles)
            policy = self._build_magic_policy(task, managed_bonus)
            max_keep = policy.max_keep_torrents
            disk_gb = task.disk_size_gb
            min_bonus = policy.min_bonus_per_hour

            # ---------- 1 入口前置检查(不抓取、游标不推进)----------
            self._set_phase(task.id, "entry")
            # 下载并发满:仍然抓取候选--存量复用(A 类)不占下载名额,理应放行;
            # 但本轮若一个都没复用成功 → 判定为空转,不推进游标,等现有下载完成后再重试同一批。
            concurrency_full = dl_concurrent >= dl_limit
            if concurrency_full:
                _reason = (
                    f"下载并发已达上限({dl_concurrent}/{dl_limit}),无空闲槽位,"
                    "本轮不抓取不下种(避免无效请求),等待槽位释放"
                )
                self._log(f"魔流 [{task.name}] {_reason}")
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": _reason, "added": 0, "reused": 0, "deleted": 0, "kept": base_cnt}
            if (max_keep and base_cnt >= max_keep) or (disk_gb and base_size >= disk_gb):
                reason = "保种池容量/数量已满,本轮停止抓取,等待 check 任务清理低效种子释放空间"
                self._log(f"魔流 [{task.name}] {reason}")
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": reason, "added": 0, "reused": 0, "deleted": 0, "kept": base_cnt}
            if not task.refill_when_empty:
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": "未开启补种", "added": 0, "reused": 0, "deleted": 0, "kept": base_cnt}

            add_cnt = 0
            add_size = 0.0
            dl_budget = int(task.max_add_per_run or 0)
            seen_cooldown = max(float(task.seen_cooldown_hours or 0), 0.0) * 3600

            if not task.site_domain:
                site = self._get_site(task.site_id)
                if site:
                    task.site_domain = getattr(site, "domain", "") or task.site_domain
                    task.site_name = getattr(site, "name", "") or task.site_name

            # ---------- 2 抓取候选(游标深翻,成功才推进游标)----------
            self._set_phase(task.id, "fetch")
            fetcher = SiteFetcher()
            if not fetcher.is_available:
                self._log("站点抓取不可用,跳过刷流", "warning")
                return {"status": "failed", "reason": "站点抓取不可用"}

            pages = max(int(task.browse_pages or BROWSE_PAGES), 1)
            # 刷流有自己的「翻页口径」:只看**最新**几页(免费热种永远在最新页),
            # 不做游标深翻(深翻只会翻到促销早已过期的老种)。刷魔力才需要深翻老种。
            _brush_crawl = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"
            cursor = 0
            candidates = None
            # 站点级共享:同站只抓一份**完整**候选列表,刷流与魔力共用
            # (二者只是排序/筛选不同;谁先抓谁填缓存,其余在 TTL 内复用)。
            candidates = self._fetch_site_candidates(task, pages=pages, start_page=0)
            # 刷流只吃免费/2X免费:从共享的完整列表里筛(不动共享数据本体)。
            # ★ 7.9.0：刷魔力任务**不在这里筛** —— 非免费候选要留给洗池阶段的「跨站路由」
            #   （本站绝不下，只走跨站）；真正保证「本站只下免费」的是 _build_filter_policy
            #   里强制 free_only=True（任务字段已无法绕过）。
            if _brush_crawl and candidates:
                _free_all = len(candidates)
                candidates = [
                    c for c in candidates
                    if getattr(c, "is_free", False) or getattr(c, "is_double_free", False)
                ]
                self._log(f"魔流 [{task.name}] 刷流·免费筛选 命中 {len(candidates)}/{_free_all} 个")
            if not candidates:
                self._log(f"魔力任务 [{task.name}] 未获取到候选种子(游标 {cursor})")
                return {"status": "noop", "reason": "未获取到候选种子", "candidates": 0, "filtered": 0}

            next_cursor = 0
            if next_cursor > MAX_PAGE_CURSOR:
                next_cursor = 0
            # 非并发满:沿用原行为,抓取成功即推进游标;
            # 并发满:先不推进,待处理完按「本轮是否复用成功」再决定(零复用=空转不推进)。
            if self._store and not concurrency_full:
                self._store.set_page_cursor(task.id, next_cursor)
            self._log(
                f"魔流 [{task.name}] 抓取返回 {len(candidates)} 个候选"
                f"(游标 {cursor},本次翻 {pages} 页)"
            )

            # ---------- 3 洗池(尚无 infohash,仅用列表字段)----------
            self._set_phase(task.id, "wash")
            filter_policy = self._build_filter_policy(task)
            _want_free_now = bool(
                getattr(filter_policy, "free_only", False)
                or getattr(filter_policy, "double_free_only", False)
            )
            # ★ 3.10.0 统一路由：开了跨站 + 任务只要免费（且不是「双倍免费」这种更严口径）时，
            #   洗池**不再因非免费丢种** —— 非免费候选改走跨站（本站绝不下），
            #   免费与否只决定「走哪条路」，不决定「要不要」。排序/优先级仍由后面的
            #   目标因子（魔力/上传潜力）统一决定。
            _cs_on = bool(getattr(task, "crossseed_enabled", False))
            _cs_split = bool(
                _cs_on
                and getattr(filter_policy, "free_only", False)
                and not getattr(filter_policy, "double_free_only", False)
            )
            _wash_policy = filter_policy
            if _cs_split:
                _wash_policy = copy.copy(filter_policy)
                _wash_policy.free_only = False
            filtered, reason_counts = filter_candidates(candidates, _wash_policy)
            wash_reasons: Dict[str, int] = dict(reason_counts)
            # ★ 限时免费闸门(洗池级):促销剩的免费时间不够下完 → 直接洗掉。
            # 常见于 Pttime 这类「12 分钟~6 天」的限时免费;到期后下载按原价计流量。
            if filtered:
                _keep_c: List[Any] = []
                _expiring = 0
                _expiring_sample = ""
                for _c in filtered:
                    _ok, _need, _remain = free_time_ok(_c)
                    if _ok:
                        _keep_c.append(_c)
                    else:
                        _expiring += 1
                        if not _expiring_sample:
                            _expiring_sample = (
                                f"{getattr(_c, 'title', '')}(剩余 {int(_remain / 60)} 分 "
                                f"< 需 {int(_need / 60)} 分)"
                            )
                if _expiring:
                    filtered = _keep_c
                    wash_reasons["免费即将到期"] = _expiring
                    self._log(
                        f"魔流 [{task.name}] 洗掉「免费即将到期」{_expiring} 个"
                        f"(如:{_expiring_sample})",
                        "warning",
                    )
            # ★ 订阅排除(刷流选种):命中当前订阅标题的候选直接剔除,避免抢主人要看的片。
            if filtered and getattr(task, "except_subscribe", True):
                try:
                    _before = len(filtered)
                    filtered = self._exclude_subscribed(filtered)
                    _excl = _before - len(filtered)
                    if _excl:
                        wash_reasons["订阅命中"] = _excl
                        self._log(f"魔流 [{task.name}] 排除订阅命中 {_excl} 个")
                except Exception as _sub_err:
                    self._dbg(f"订阅排除失败(忽略): {_sub_err}")
            # ★ 3.10.0 跨站路由：把「本站不免费」的候选从主流程分出去（只跨站，绝不在本站下）。
            #   数据来源就是刚抓的这份列表（开了跨站时 task 抓的已是主列表，带真实促销列）。
            _cs_pool: List[Any] = []
            if _cs_split and filtered:
                _free_keep: List[Any] = []
                _nf_keep: List[Any] = []
                for _c in filtered:
                    (_free_keep if bool(getattr(_c, "is_free", False)) else _nf_keep).append(_c)
                filtered = _free_keep
                if _nf_keep:
                    try:
                        _nf_keep.sort(
                            key=lambda c: (
                                int(getattr(c, "leechers", 0) or 0),
                                float(getattr(c, "size_gb", 0.0) or 0.0),
                            ),
                            reverse=True,
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    for _c in _nf_keep[:CROSSSEED_POOL_MAX]:
                        _c.crossseed_only = True
                        _cs_pool.append(_c)
                    self._log(
                        f"魔流 [{task.name}] 跨站候选池 {len(_cs_pool)} 个"
                        f"(本站非免费 {len(_nf_keep)} 个 → 只跨站取种，不在本站下载)"
                    )
            # ★ 最优解算法(做种人数 Ni × 体积 Si):真实边际时魔。
            # a_current = 现有池子合计 A;边际增益 B(A+a)-B(A) 才能反映「再加一颗」的真实收益。
            a_current = 0.0
            for _b in managed_bonus:
                try:
                    a_current += float(getattr(_b, "bonus_score", 0.0) or 0.0)
                except Exception:
                    pass
            _cap_n = int(getattr(formula_params, "seeding_count_cap", 0) or 0)
            _flat = float(getattr(formula_params, "per_torrent_flat", 0.0) or 0.0)
            flat_gain = _flat if (not _cap_n or base_cnt < _cap_n) else 0.0
            _min_seeders = max(int(getattr(filter_policy, "min_seeders", 0) or 0), 1)

            # ★ 存量复用索引提前建立:辅种(复用)要在「全量候选」里找,不受 TopN 魔力排名限制。
            local_index: Dict[str, TorrentInfo] = {}
            local_by_size: "_SizeIndex" = _SizeIndex([])
            fp_cache: Dict[str, Optional[str]] = {}
            if task.reuse_existing:
                try:
                    local_index, local_by_size = self._local_reuse_index(downloader)
                    self._log(f"魔流 [{task.name}] 本机已有种子 {len(local_index)} 个,启用存量复用")
                except Exception as e:
                    self._log(f"建立本机资源索引失败:{e}", "warning")

            scored: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent]] = []
            reuse_pool: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent]] = []
            skipped_seen = 0
            skipped_dead = 0
            skipped_low = 0
            skipped_nosrc = 0
            skipped_dup_global = 0  # ★ 跨任务重复资源（同一 infohash / 同一完整特征码已被其它任务下过）
            for c in filtered:
                ckey = self._candidate_key(c)
                if ckey and self._store and self._store.seen.is_seen(task.id, f"cand:{ckey}", seen_cooldown):
                    skipped_seen += 1
                    continue
                if ckey and self._store and self._store.dead.is_dead(task.id, f"cand:{ckey}", self._dead_cooldown):
                    skipped_dead += 1
                    continue
                _is_off = bool(official_titles) and (normalize_title(c.title) in official_titles)
                bonus = calc_torrent_bonus(
                    hash=c.hash or uuid.uuid4().hex[:12],
                    title=c.title,
                    size_gb=c.size_gb,
                    seeders=c.seeders,
                    leechers=c.leechers,
                    age_weeks=max(c.age_weeks, candidate_ref_weeks(formula_params)),
                    volume_factor=c.volume_factor,
                    is_zero_bonus=c.is_zero_bonus,
                    is_free=c.is_free,
                    is_double_free=c.is_double_free,
                    hit_and_run=c.hit_and_run,
                    is_official=_is_off,
                    params=formula_params,
                )
                bonus.age_weeks = c.age_weeks
                # ★ 做种人数 Ni × 体积 Si → 最优解评分(边际时魔 + 每 GB 效率 + 可下性)
                sc = score_candidate(
                    size_gb=c.size_gb,
                    seeders=c.seeders,
                    age_weeks=c.age_weeks,
                    a_current=a_current,
                    is_zero_bonus=c.is_zero_bonus,
                    is_official=_is_off,
                    params=formula_params,
                    min_seeders=_min_seeders,
                    flat_gain=flat_gain,
                )
                if not sc.viable:
                    skipped_nosrc += 1
                    # 无做种源 ≠ 不能辅种:本机已有同一资源就能直接辅(免下载)。
                    # 但刷流任务只辅助「排名内」的种子,不做非 TopN 的额外复用扫描。
                    if not _brush_crawl and task.reuse_existing and local_by_size.near(int(getattr(c, "size", 0) or 0)):
                        reuse_pool.append((bonus, c))
                    continue
                setattr(c, "_score", sc)
                setattr(c, "_value", sc.value)
                setattr(c, "_eff", sc.efficiency)
                if min_bonus and bonus.bonus_per_hour < min_bonus:
                    skipped_low += 1
                    # 魔力偏低 ≠ 不能辅种;免下载的依然是白得的魔力。
                    # 刷流任务不做非 TopN 的额外复用扫描。
                    if not _brush_crawl and task.reuse_existing and local_by_size.near(int(getattr(c, "size", 0) or 0)):
                        reuse_pool.append((bonus, c))
                    continue
                scored.append((bonus, c))

            wash_reasons["近期已处理"] = skipped_seen
            wash_reasons["死种缓存"] = skipped_dead
            wash_reasons["无做种源"] = skipped_nosrc
            wash_reasons["低于魔力门槛"] = skipped_low
            if self._store:
                self._store.record_filter_stats(
                    task.id,
                    {k: v for k, v in wash_reasons.items() if v},
                    len(candidates),
                    len(scored),
                )
            if not scored and not (task.reuse_existing and reuse_pool):
                self._log(f"魔力任务 [{task.name}] 洗池后无可用候选(过滤通过 {len(filtered)})")
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": "洗池后无可用候选", "candidates": len(candidates), "filtered": 0, "added": 0, "reused": 0, "deleted": 0, "kept": base_cnt}

            # ★ 最优解排序:名额受限(保种数上限)→ 按边际 value 降序;
            # 仅磁盘受限 → 按每 GB 效率 efficiency 降序(把每 GB 收益最大的先装)。
            _disk_left = (float(disk_gb) - base_size) if disk_gb else None
            _count_left = (int(max_keep) - base_cnt) if max_keep else None
            _is_brush_task = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"
            if _is_brush_task:
                # 刷流模式:按「上传潜力」排序 -- leechers(下载需求)优先,其次体积大、更新鲜。
                scored.sort(
                    key=lambda pair: (
                        int(getattr(pair[1], "leechers", 0) or 0),
                        float(getattr(pair[1], "size_gb", 0.0) or 0.0),
                        -float(getattr(pair[1], "age_weeks", 0.0) or 0.0),
                    ),
                    reverse=True,
                )
            elif _disk_left is not None and _count_left is None:
                scored.sort(key=lambda pair: (getattr(pair[1], "_eff", 0.0), getattr(pair[1], "_value", 0.0)), reverse=True)
            else:
                scored.sort(key=lambda pair: (getattr(pair[1], "_value", 0.0), getattr(pair[1], "_eff", 0.0)), reverse=True)
            top_n = max(int(task.top_n or 0), 1)
            topn = scored[:top_n]
            self._dbg(
                f"[{task.name}] 洗池 {len(candidates)}→通过 {len(scored)}→Top{len(topn)}"
                f"(disk_left={_disk_left} count_left={_count_left})"
            )

            # ★ 复用/辅种已从主流程切出,交给独立的「辅种慢扫」worker 处理(见 reuse_scan)。
            #   主流程只针对 TopN 取种下单;已取回的 TopN 种仍会「顺带」做一次复用判定(零额外请求)。

            # ---------- 4 分类:下载候选 TopN(顺带复用已取回的种)----------
            self._set_phase(task.id, "classify")
            group_a: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent, str, TorrentInfo]] = []
            group_b: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent]] = []

            # ★ 辅种不参与魔力排名:只要「体积邻近本机种子」就纳入扫描(免下载 = 白得的魔力)。
            #   TopN 只决定「要下载哪些」;可复用的额外候选即便魔力排不进 TopN 也一起取回判定。

            def _ckey_of(pair: Any) -> str:
                c = pair[1]
                return self._candidate_key(c) or getattr(c, "hash", "") or getattr(c, "title", "")

            _fetch_map: Dict[str, Tuple[TorrentBonusInfo, SiteCandidateTorrent]] = {}
            _topn_keys: Set[str] = set()
            for pair in topn:
                k = _ckey_of(pair)
                _topn_keys.add(k)
                _fetch_map[k] = pair
            _reuse_extra = 0
            fetch_list = list(_fetch_map.values())
            # ★ 只为「能真正用上的名额」取种:空闲槽位不足时,多余取种是纯无效请求(还会触发站点流控)。
            #   刷流任务尤其重要:有 N 个空位就只取 N 个,不再一次取满 TopN。
            if _brush_crawl:
                _free_slots = max(int(dl_limit) - int(dl_concurrent), 0)
                if _free_slots and len(fetch_list) > _free_slots:
                    _before_n = len(fetch_list)
                    fetch_list = fetch_list[:_free_slots]
                    self._log(
                        f"魔流 [{task.name}] 取种数按空闲槽位封顶:{_before_n} → {len(fetch_list)}"
                        f"(空位 {_free_slots}/{dl_limit})"
                    )

            # 并发预取 .torrent(TopN + 可复用候选)。
            # 每个请求各自新建 RequestUtils 会话,无共享状态,可安全并发。
            # 站点流控早停标志:一旦命中,本轮剩余候选不再请求(避免继续加剧限流)。
            _fc_hit = [False]

            def _prefetch(pair: Any) -> None:
                _b, _c = pair
                _raw = None
                _err = ""
                if _fc_hit[0]:
                    _c.raw = None
                    _c.fetch_error = "站点流控(本轮跳过)"
                    _c.real_hash = ""
                    return
                # ★ 3.44.0 API 站（馒头）：候选没有 enclosure → 入选时现取签名直链
                if not _c.enclosure:
                    try:
                        self._cand_enclosure(_c)
                    except Exception as _ee:  # noqa: BLE001
                        _err = f"取下载直链异常: {_ee}"[:200]
                if _c.enclosure:
                    for _attempt in range(max(int(TORRENT_DL_RETRIES), 1)):
                        try:
                            _raw = downloader.fetch_torrent_bytes(
                                _c.enclosure,
                                cookie=_c.site_cookie,
                                user_agent=_c.site_ua,
                                referer=getattr(_c, "page_url", "") or None,
                            )
                        except TorrentFetchFlowControl as _e:
                            # 站点流控:本轮直接放弃(重试只会加剧),且不记 dead。
                            _raw = None
                            _err = f"站点流控:{_e}"[:200]
                            _fc_hit[0] = True
                            break
                        except Exception as _e:  # noqa: BLE001
                            _raw = None
                            _err = f"{type(_e).__name__}: {_e}"[:200]
                        if _raw:
                            break
                        _err = _err or "返回空"
                        # 疑似流控/限速:退避后再试,避免连续打。
                        if _attempt < max(int(TORRENT_DL_RETRIES), 1) - 1:
                            time.sleep(1.5 * (_attempt + 1))
                else:
                    _err = "enclosure 为空"
                _c.raw = _raw
                _c.fetch_error = _err
                try:
                    _c.real_hash = (info_hash(_raw) or "").lower() if _raw else ""
                except Exception:
                    _c.real_hash = ""

            _t_pref = time.time()
            _pref_done = 0
            if len(fetch_list) > 1:
                _ex = ThreadPoolExecutor(max_workers=min(TORRENT_FETCH_WORKERS, len(fetch_list)))
                _futs = {_ex.submit(_prefetch, _p): _p for _p in fetch_list}
                _pending = set(_futs.keys())
                _batch_deadline = _t_pref + TORRENT_FETCH_DEADLINE
                _last_prog = _t_pref
                try:
                    # 边完成边推进:同时受「整段上限」与「单次硬超时」双重约束。
                    # 单次硬超时 = 连续 TORRENT_FETCH_PER_TIMEOUT 秒内没有任何一个请求完成
                    # (典型=在飞请求全部卡死/站点限速)→ 放弃等待剩余候选,立即进入处理阶段。
                    while _pending:
                        _remain = _batch_deadline - time.time()
                        if _remain <= 0:
                            break
                        _done, _pending = wait(
                            _pending,
                            timeout=min(TORRENT_FETCH_PER_TIMEOUT, _remain),
                            return_when=FIRST_COMPLETED,
                        )
                        for _fut in _done:
                            try:
                                _fut.result()
                            except Exception:
                                pass
                            _pref_done += 1
                        if not _done:
                            # 单次硬超时:在飞请求全部无响应,放弃等待,避免整段被拖满。
                            self._log(
                                f"魔流 [{task.name}] 分类取种单次超时"
                                f"({TORRENT_FETCH_PER_TIMEOUT:.0f}s 无进展,已取 {_pref_done}/{len(fetch_list)})"
                            )
                            break
                        # 细粒度进度(限流,避免频繁写盘):供前端显示,避免「像卡住」
                        _now = time.time()
                        if _now - _last_prog >= 5.0:
                            _last_prog = _now
                            self._set_phase(task.id, "classify", f"取种 {_pref_done}/{len(fetch_list)}")
                finally:
                    _ex.shutdown(wait=False, cancel_futures=True)
                # 未完成(被取消/未执行)的候选标记「超时跳过」,供处理循环安全跳过(不记 dead)
                for _p in fetch_list:
                    if getattr(_p[1], "raw", None) is None and not getattr(_p[1], "fetch_error", ""):
                        _p[1].raw = None
                        _p[1].fetch_error = "分类取种超时(本轮跳过)"
                        try:
                            _p[1].real_hash = ""
                        except Exception:
                            pass
            else:
                for _p in fetch_list:
                    _prefetch(_p)
                _pref_done = len(fetch_list)
            self._log(
                f"魔流 [{task.name}] 分类取种 {_pref_done}/{len(fetch_list)} 个"
                f"(耗时 {time.time() - _t_pref:.1f}s)"
            )

            # 分类诊断:本轮取回多少 .torrent;没拿到时打样本原因
            _raw_ok = sum(1 for _p in fetch_list if getattr(_p[1], "raw", None))
            if _raw_ok < len(fetch_list):
                _sample = fetch_list[0][1]
                self._log(
                    f"魔流 [{task.name}] 种子文件获取 {_raw_ok}/{len(fetch_list)};"
                    f"示例 enclosure={getattr(_sample, 'enclosure', '')[:90]!r} "
                    f"err={getattr(_sample, 'fetch_error', '')!r}",
                    "warning",
                )

            # ★ IYUU 云端辅种:一次批量查询本轮候选 → 他站同资源 infohash(补齐本地匹配;
            #   只在填了 Token 时启用,否则完全退回内置特征码方案)。
            _iyuu_map: Dict[str, List[str]] = {}
            if task.reuse_existing and self._iyuu_enabled() and fetch_list:
                _cand_hashes = [c.real_hash for _, c in fetch_list if getattr(c, "real_hash", None)]
                if _cand_hashes and self._iyuu_client is not None:
                    try:
                        _iyuu_map = self._iyuu_client.sibling_hashes(_cand_hashes)
                    except Exception as err:  # noqa: BLE001
                        self._log(f"魔流 [{task.name}] IYUU 查询失败:{err}", "warning")
                    if _iyuu_map:
                        self._log(
                            f"魔流 [{task.name}] IYUU 云端命中:{len(_iyuu_map)}/{len(_cand_hashes)} "
                            f"个候选存在他站同资源"
                        )

            _cross_near = 0
            _cross_hit = 0
            _iyuu_hit = 0
            for bonus, cand in fetch_list:
                ckey = _ckey_of((bonus, cand))
                _in_topn = ckey in _topn_keys
                raw = getattr(cand, "raw", None)
                if not raw:
                    if _in_topn:
                        group_b.append((bonus, cand))
                    continue
                h = cand.real_hash
                local = local_index.get(h) if (h and h in local_index) else None
                # 半成品:本机同 hash 但仍在下载 → 不能做种,跳过
                if local and str(getattr(local, "state", "") or "").lower() in QB_DOWNLOADING_STATES:
                    continue
                # ★ 取种统一入口（docs/MODULES.md X7）：本机同 hash → 本机同 Release → IYUU
                _astats: Dict[str, int] = {"near": 0, "fp": 0, "iyuu": 0}
                mode, linfo = self._acquire_existing(
                    task, cand, downloader,
                    local_index=local_index, local_by_size=local_by_size,
                    fp_cache=fp_cache, iyuu_map=_iyuu_map,
                    raw=getattr(cand, "raw", None), stats=_astats,
                )
                _cross_near += int(_astats.get("near", 0))
                _cross_hit += int(_astats.get("fp", 0))
                _iyuu_hit += int(_astats.get("iyuu", 0))
                if mode and linfo is not None:
                    group_a.append((bonus, cand, mode, linfo))
                elif _in_topn:
                    # 仅 TopN 候选参与「下载」排队;为复用而额外取回的候选不可复用则丢弃。
                    # ★ 全局（跨任务）去重：该资源已被其它任务下载/在飞 → 不再排队下载。
                    #   · 对方「在飞」→ 只让位本轮（**不打 seen**）：下轮本机有副本 → 走辅种；
                    #   · 对方「已下过」且本机无副本 → 真没得辅，终局跳过（记 seen 防反复抓）。
                    _gkeys = self._dup_keys(h, fingerprint(raw) if raw else None)
                    _cst = self._dup_conflict_states(task.id, keys=_gkeys) if _gkeys else {}
                    if _cst:
                        skipped_dup_global += 1
                        if ckey and all(v == "done" for v in _cst.values()):
                            self._store.seen.mark(task.id, [f"cand:{ckey}"])
                        continue
                    group_b.append((bonus, cand))
            if task.reuse_existing:
                self._log(
                    f"魔流 [{task.name}] 存量复用扫描:复用命中 {len(group_a)} 个"
                    f"(体积邻近比对 {_cross_near} / 特征码命中 {_cross_hit} / IYUU 命中 {_iyuu_hit},"
                    f"另扫非 TopN {_reuse_extra} 个)"
                )

            # ★ 与洗池同一套排序键:名额受限→边际 value 降序;仅磁盘受限→每 GB 效率 efficiency 降序。
            # (修 bug:原此处用旧的「单种魔力」bonus_per_hour 重排,把洗池的边际排序又覆盖回去了)
            _disk_bound = _disk_left is not None and _count_left is None

            def _rank_key(pair: Any):
                _c = pair[1]
                # 刷流:下载优先序按「上传潜力」--下载人数↓、体积↓、新鲜度↑
                # (与洗池排序一致;此前无分支,刷流被魔力 value/eff 覆盖)。
                if _is_brush_task:
                    return (
                        int(getattr(_c, "leechers", 0) or 0),
                        float(getattr(_c, "size_gb", 0.0) or 0.0),
                        -float(getattr(_c, "age_weeks", 0.0) or 0.0),
                    )
                if _disk_bound:
                    return (getattr(_c, "_eff", 0.0), getattr(_c, "_value", 0.0))
                return (getattr(_c, "_value", 0.0), getattr(_c, "_eff", 0.0))

            # ★ 辅种不参与魔力排名:group_a 保持发现顺序直接加(免下载)
            group_b.sort(key=_rank_key, reverse=True)
            ordered: List[Any] = list(group_a) + list(group_b)
            self._log(
                f"魔流 [{task.name}] Top{len(topn)} 排序:复用 {len(group_a)} / 下载 {len(group_b)}"
            )

            # ---------- 5 处理循环(A 复用优先,其后 B 下载)----------
            self._set_phase(task.id, "process")
            added = 0
            reused = 0
            new_pub: Dict[str, float] = {}
            new_pages: Dict[str, str] = {}  # hash→详情页 URL(供「已非免费→清理」核对)
            new_free: Dict[str, float] = {}  # hash→促销到期时刻(unix),供「到期即清」
            add_failed = 0
            skipped_dup = 0
            skipped_quota = 0
            skipped_expiring = 0
            skipped_reuse_limit = 0
            skipped_rate = 0
            tagged_reuse = 0
            crossseed_started = 0  # ★ 3.9.0 跨站免费取种发起数
            _cs_max = max(int(getattr(task, "crossseed_max_per_round", 3) or 3), 1)
            _cs_max_size = float(getattr(task, "crossseed_max_size_gb", 20.0) or 20.0)
            detail_items: List[OperationItem] = []  # 逐条明细(供操作流水展开)
            for item in ordered:
                is_reuse = len(item) == 4
                if is_reuse:
                    bonus, cand, mode, linfo = item
                else:
                    bonus, cand = item
                h = (getattr(cand, "real_hash", "") or "").lower()
                _cand_h = h  # 原始候选 hash（跨站辅种后 h 会被换成兄弟种 hash）
                ckey = self._candidate_key(cand)

                # 兜底去重(fetch 后二次检查)
                if h and h in managed_hashes:
                    skipped_dup += 1
                    if self._store:
                        self._store.seen.mark(task.id, [f"hash:{h}"])
                    continue
                if self._store and h and self._store.dead.is_dead(task.id, f"hash:{h}", self._dead_cooldown):
                    skipped_dead += 1
                    continue
                if not getattr(cand, "raw", None):
                    _err = str(getattr(cand, "fetch_error", "") or "")
                    if "流控" in _err or "超时" in _err:
                        # 临时限流 / 取种超时:不记 dead(下轮重试),单独计数。
                        skipped_rate += 1
                        self._log(
                            f"跳过·站点流控/取种超时,本轮不处理,下轮重试:{cand.title}",
                            "warning",
                        )
                        continue
                    add_failed += 1
                    if self._store and ckey:
                        self._store.dead.mark(task.id, [f"cand:{ckey}"])
                    self._log(f"跳过·无法获取种子:{cand.title}({_err or '未知原因'})", "warning")
                    continue

                size_gb = float(cand.size_gb or 0)
                over_quota = (
                    (max_keep and (base_cnt + add_cnt + 1) > max_keep)
                    or (disk_gb and (base_size + add_size + size_gb) > disk_gb)
                )

                if is_reuse:
                    # 辅种/复用并不总是「零下载」:本地同 hash 但未完成、或跨站辅种未开校验时,
                    # 都会触发补下载 → 这类按下载名额(并发/单轮名额)计,避免并发被绕过。
                    if mode == "hash":
                        local_progress = float(getattr(linfo, "progress", 0) or 0)
                        reuse_downloads = local_progress < 0.999
                    else:
                        reuse_downloads = not task.reuse_verify
                    # ★ 兜底闸门:确需补下载时,若促销快到期也不补(下不完=白烧流量)。
                    if reuse_downloads and not free_time_ok(cand)[0]:
                        _ok, _need, _remain = free_time_ok(cand)
                        skipped_expiring += 1
                        self._log(
                            f"跳过·免费剩余不足({int(_remain / 60)}分 < 需 "
                            f"{int(_need / 60)}分):{cand.title}",
                            "warning",
                        )
                        if self._store and ckey:
                            self._store.dead.mark(task.id, [f"cand:{ckey}"])
                        continue
                    # ★ 辅种(免下载)不参与配额/排名限制:直接加(白得的魔力)。
                    #   (仅当确需补下载时才受下载名额/预算约束,见下)
                    if over_quota:
                        self._log(
                            f"辅种超出配额仍直接复用(免下载):{cand.title}"
                        )
                    if reuse_downloads:
                        if dl_concurrent >= dl_limit:
                            skipped_reuse_limit += 1
                            self._log(
                                f"复用跳过·下载并发已满({dl_concurrent}/{dl_limit}):{cand.title}"
                            )
                            continue
                        if dl_budget <= 0:
                            break
                    ok = False
                    _rerr = ""
                    if mode == "hash":
                        ok = self._tag_assign(task, [h], reason="同 hash 复用") > 0
                        st = str(getattr(linfo, "state", "") or "").lower()
                        if st in (QB_PAUSED_STATES | {"error", "missingfiles"}):
                            downloader.resume_torrent(h)
                        if ok:
                            tagged_reuse += 1
                    else:  # 跨站辅种
                        hs, err = downloader.add_torrent_reuse(
                            torrent_bytes=cand.raw,
                            save_path=(getattr(linfo, "save_path", "") or task.save_path or ""),
                            tag=self._task_tag(task),
                            verify=task.reuse_verify,
                        )
                        ok = bool(hs)
                        if ok and hs:
                            h = hs.lower()
                            self._tag_assign(task, [h], reason="跨站辅种")
                        if not ok and err:
                            _rerr = str(err)
                            self._log(f"辅种失败:{cand.title}({err})", "warning")
                    if not ok:
                        detail_items.append(OperationItem(
                            hash=h or "", title=cand.title,
                            reason=f"辅种失败:{_rerr or '校验不通过/未匹配'}",
                            size_gb=size_gb, source="reuse-fail",
                        ))
                        if self._store and ckey:
                            self._store.dead.mark(task.id, [f"cand:{ckey}"])
                        continue
                    reused += 1
                    # ★ 复用/辅种成功 = 资源已在本地 → 登记闸门 done，免得别的任务再从零下一份
                    self._dup_finish(
                        task.id,
                        keys=self._dup_keys(
                            _cand_h, fingerprint(cand.raw) if getattr(cand, "raw", None) else None
                        ),
                    )
                    add_cnt += 1
                    add_size += size_gb
                    pub_ts = self._pubdate_ts(getattr(cand, "pubdate", None))
                    if pub_ts and h:
                        new_pub[h] = pub_ts
                    if h and getattr(cand, "page_url", ""):
                        new_pages[h] = str(cand.page_url)
                    _fu = float(getattr(cand, "free_remaining_sec", -1.0) or -1.0)
                    if h and _fu >= 0:
                        new_free[h] = time.time() + _fu
                    if reuse_downloads:
                        dl_budget -= 1
                        dl_concurrent += 1
                    if h:
                        managed_hashes.add(h)
                    if self._store:
                        keys = [f"hash:{h}"] if h else []
                        if ckey:
                            keys.append(f"cand:{ckey}")
                        if keys:
                            self._store.seen.mark(task.id, keys)
                    self._log(f"复用入库{'(补下载)' if reuse_downloads else ''}:{cand.title}")
                    detail_items.append(OperationItem(
                        hash=h or "", title=cand.title,
                        reason="复用·补下载" if reuse_downloads else "复用",
                        size_gb=size_gb, source="reuse",
                        seeders=int(getattr(cand, "seeders", 0) or 0),
                    ))
                    continue

                # B:需下载
                if dl_concurrent >= dl_limit:
                    continue
                if dl_budget <= 0:
                    break
                if over_quota:
                    skipped_quota += 1
                    continue
                # ★ 兜底闸门:限时免费剩的免费时间不够下完 → 不下(洗池阶段拦不到时)。
                _ok_t, _need_t, _remain_t = free_time_ok(cand)
                if not _ok_t:
                    skipped_expiring += 1
                    self._log(
                        f"跳过·免费剩余不足({int(_remain_t / 60)}分 < 需 "
                        f"{int(_need_t / 60)}分):{cand.title}",
                        "warning",
                    )
                    if self._store and ckey:
                        self._store.dead.mark(task.id, [f"cand:{ckey}"])
                    continue
                # ★ 3.9.0 跨站免费取种：A 站这颗**不免费**（下了就烧流量/拉低分享率）
                #   → 先去任意他站（B/C/D…）找「免费且同一 Release」的副本下回来，
                #   下完由「跨站回辅」worker 把它辅回 A（零下载纯做种）。
                if (
                    getattr(task, "crossseed_enabled", False)
                    and not bool(getattr(cand, "is_free", False))
                    and crossseed_started < _cs_max
                    and size_gb <= _cs_max_size
                ):
                    _sib = None
                    try:
                        # 契约②：取种只走统一入口（本机/IYUU 已在前面试过 → 这里等价于只发第 ④ 跳）
                        _sib = (self._acquire_source(
                            task, cand, downloader, allow_cross_site=True,
                        ).get("sib_hash") or None)
                    except Exception as _cse:  # noqa: BLE001
                        self._log(f"跨站取种异常:{cand.title}({_cse})", "warning")
                    if _sib:
                        crossseed_started += 1
                        add_cnt += 1
                        add_size += size_gb
                        dl_budget -= 1
                        dl_concurrent += 1
                        managed_hashes.add(_sib)
                        if self._store:
                            keys = [f"hash:{_sib}"]
                            if ckey:
                                keys.append(f"cand:{ckey}")
                            self._store.seen.mark(task.id, keys)
                        detail_items.append(OperationItem(
                            hash=_sib, title=cand.title,
                            reason="跨站免费取种（他站下→回辅 A）",
                            size_gb=size_gb, source="crossseed",
                        ))
                        continue
                # ★ 全局（跨任务）资源去重闸门：同一资源（同 infohash / 同完整特征码）只下一次。
                #   先原子占用；被其它任务占用/近期下过 → 跳过（不重复下载）。
                _gkeys = self._dup_keys(
                    h, fingerprint(cand.raw) if getattr(cand, "raw", None) else None
                )
                _gconf = self._dup_claim(task.id, keys=_gkeys)
                if _gconf:
                    _cst = self._dup_conflict_states(task.id, keys=_gkeys) or {}
                    _terminal = bool(_cst) and all(v == "done" for v in _cst.values())
                    skipped_dup_global += 1
                    self._log(f"跳过·重复资源（其它任务{'已下载' if _terminal else '在飞'}）:{cand.title}")
                    # 仅「已下过且本机无副本」才记 seen；「在飞」让位本轮，留给下轮辅种
                    if _terminal and self._store:
                        _sk = [f"hash:{h}"] if h else []
                        if ckey:
                            _sk.append(f"cand:{ckey}")
                        if _sk:
                            self._store.seen.mark(task.id, _sk)
                    continue
                hash_string, error = downloader.add_torrent(
                    content=cand.raw,
                    download_dir=task.save_path or "",
                    tag=self._task_tag(task),
                    cookie=cand.site_cookie,
                    user_agent=cand.site_ua,
                    upload_limit=task.up_speed,
                    download_limit=task.dl_speed,
                    site_domain=getattr(cand, "site_domain", "") or "",
                    hit_and_run=bool(getattr(cand, "hit_and_run", False)),
                )
                if hash_string:
                    added += 1
                    add_cnt += 1
                    add_size += size_gb
                    dl_budget -= 1
                    dl_concurrent += 1
                    self._dup_finish(task.id, keys=_gkeys)
                    nh = (hash_string or h).lower()
                    managed_hashes.add(nh)
                    pub_ts = self._pubdate_ts(getattr(cand, "pubdate", None))
                    if pub_ts and nh:
                        new_pub[nh] = pub_ts
                    if nh and getattr(cand, "page_url", ""):
                        new_pages[nh] = str(cand.page_url)
                    if nh:
                        self._tag_assign(task, [nh], reason="新增下载")
                    # ★ 生产即带特征码：资源按特征码归并、跨站辅种直接配对（零额外请求，用候选 .torrent 字节算）
                    if nh:
                        try:
                            _fp = fingerprint(getattr(cand, "raw", None)) if getattr(cand, "raw", None) else None
                            if _fp:
                                self._tag_state().put(nh, {"fp": _fp})
                        except Exception as _ferr:  # noqa: BLE001
                            self._dbg(f"特征码记录失败 {nh[:8]}:{_ferr}")
                    _fu2 = float(getattr(cand, "free_remaining_sec", -1.0) or -1.0)
                    if nh and _fu2 >= 0:
                        new_free[nh] = time.time() + _fu2
                    if self._store:
                        keys = [f"hash:{nh}"]
                        if ckey:
                            keys.append(f"cand:{ckey}")
                        self._store.seen.mark(task.id, keys)
                    self._log(f"新增:{cand.title}")
                    detail_items.append(OperationItem(
                        hash=nh, title=cand.title, reason="新增",
                        size_gb=size_gb, source="add",
                        seeders=int(getattr(cand, "seeders", 0) or 0),
                    ))
                else:
                    add_failed += 1
                    self._dup_release(task.id, keys=_gkeys)
                    if self._store and ckey:
                        self._store.dead.mark(task.id, [f"cand:{ckey}"])
                    self._log(f"添加失败:{cand.title}({error})", "warning")
                    detail_items.append(OperationItem(
                        hash=h or "", title=cand.title,
                        reason=f"添加失败:{error or '未知原因'}",
                        size_gb=size_gb, source="add-fail",
                    ))

            if self._store and new_pub:
                self._store.note_pub_dates(task.id, new_pub, tz=SITE_TZ_OFFSET_HOURS)
                self._sync_seed_pub_dates(new_pub)      # 5 表契约：同步进种子表 published_at

            if self._store and new_pages:
                self._store.note_torrent_pages(task.id, new_pages)
            if self._store and new_free:
                self._store.note_torrent_free_until(task.id, new_free)

            if reused and self._store:
                self._store.journal.record(
                    task_id=task.id,
                    kind="reseed",
                    items=[OperationItem(hash="", title=f"存量复用 {reused} 个", reason="辅种")],
                )
            if tagged_reuse and self._store:
                try:
                    self._store.journal.record(
                        task_id=task.id,
                        kind="tag",
                        items=[OperationItem(
                            hash="", title=f"复用·补标签 {tagged_reuse} 个",
                            reason=f"→「{task.brush_tag}」", source="reuse",
                            tags=f"→{task.brush_tag}",
                        )],
                    )
                except Exception as _jerr:
                    self._log(f"记录复用标签事件失败:{_jerr}", "warning")

            # 游标推进判定:并发满时,只有本轮复用成功才推进;零复用视为空转不推进。
            if concurrency_full:
                if reused > 0:
                    if self._store:
                        self._store.set_page_cursor(task.id, next_cursor)
                    self._log(
                        f"魔流 [{task.name}] 并发满但本轮复用 {reused} 个,游标 {cursor}→{next_cursor}"
                    )
                else:
                    self._log(
                        f"魔流 [{task.name}] 并发满且本轮无复用产出,判定空转,游标保持 {cursor} 不推进"
                    )
            cursor_note = (
                f"{cursor}→{next_cursor}"
                if (not concurrency_full or reused > 0)
                else f"{cursor}(空转未推进)"
            )

            # ---------- 5.5 跨站免费取种：本站不免费的候选 → 去他站免费下 → 下完回辅本站 ----------
            if _cs_pool and crossseed_started < _cs_max:
                try:
                    _cs_started = self._crossseed_round(
                        task, downloader, _cs_pool, _cs_max - crossseed_started
                    )
                except Exception as _csr_err:  # noqa: BLE001
                    _cs_started = []
                    self._log(f"跨站取种相位异常:{_csr_err}", "warning")
                for _ch, _ct, _csz in _cs_started:
                    crossseed_started += 1
                    detail_items.append(OperationItem(
                        hash=_ch, title=_ct,
                        reason="跨站免费取种（他站下→回辅本站）",
                        size_gb=_csz, source="crossseed",
                    ))

            self._invalidate_summary()
            self._set_phase(task.id, "done")
            detail = (
                f"(复用 {reused} / 新增 {added} / 跨站 {crossseed_started} / 去重 {skipped_dup}"
                f" / 跨任务去重 {skipped_dup_global}"
                f" / 配额满 {skipped_quota} / 复用限并发 {skipped_reuse_limit} / 流控 {skipped_rate}"
                f" / 免费到期 {skipped_expiring} / 失败 {add_failed})"
            )
            self._log(
                f"魔流 [{task.name}] 候选 {len(candidates)}→洗池 {len(scored)}→Top{len(topn)} | "
                f"新增 {added} / 复用 {reused}(当前托管 {len(managed_hashes)},游标 {cursor_note}){detail}"
            )
            return {
                "status": "done",
                "reason": f"候选 {len(candidates)}→洗池 {len(scored)}",
                "added": added,
                "reused": reused,
                "deleted": 0,
                "kept": len(managed_hashes),
                "candidates": len(candidates),
                "filtered": len(scored),
                "items": detail_items,
            }

        except Exception as e:
            import traceback
            self._log(f"魔流 [{task.name}] 刷流失败: {e}\n{traceback.format_exc()}", "error")
            self._set_phase(task.id, "error")
            return {"status": "failed", "reason": str(e)}

    def check(self, task_id: str) -> None:
        """执行魔力优化一轮(评估并删除低魔力产出种子)。"""
        self._apply_task_traffic_limit()
        self._apply_seed_upload_limit()
        task = self._get_task_config(task_id)
        if task and self._maybe_autostop_for_goal(task):
            return
        self._run_check(task_id)

    def _is_in_active_time(self, time_range: str) -> bool:
        """检查当前时间是否在活跃时间段内。"""
        if not time_range:
            return True
        try:
            now = datetime.now()
            current_minutes = now.hour * 60 + now.minute
            start_str, end_str = time_range.split("-")
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m
            if start_minutes <= end_minutes:
                return start_minutes <= current_minutes <= end_minutes
            return current_minutes >= start_minutes or current_minutes <= end_minutes
        except Exception:
            return True


    def _note_decision(self, task_id: str, dec: Optional[Dict[str, Any]]) -> None:
        """★ 7.15.0 可观测：把「本轮决策轨迹」记到任务状态对象上。

        为何不直接改 ``store.settle``：``MagicFlowStore`` 是**进程级单例**（热重载不重建，
        老实例仍挂老类）→ 新增的 store 方法要重启 MP 才生效。这里走 mixin（热重载必重建）
        直写内存对象，详情接口同口径读取，免重启即时可见。
        """
        if not dec or not self._store:
            return
        try:
            st = self._store.task_states.get(task_id)
            if st is not None:
                setattr(st, "last_decision", dict(dec))
        except Exception:  # noqa: BLE001
            pass

    def _run_check(self, task_id: str) -> None:
        """执行魔流核心流程(带并发保护)。"""
        task = self._get_task_config(task_id)
        if not task:
            return
        if not self._acquire_worker_slot(f"检查·{task.name}"):
            return
        if not self._try_begin_run(task_id):
            self._release_worker_slot()
            return
        try:
            self._run_check_impl(task)
        finally:
            self._end_run(task_id)
            self._release_worker_slot()

    def _run_check_impl(self, task: MagicFlowTaskConfig) -> None:
        """执行魔流核心流程(内部实现)。"""
        self._last_run_times[task.id] = time.time()
        self._store.record_run_start(task.id)

        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                self._log(f"下载器不可用: {task.downloader}", "error")
                self._store.record_run_error(task.id, "下载器不可用")
                return

            # ★ 3.25.0: Check 也要纳管同站已有种。
            #   - running 任务:已有 brush() 入口纳管,这里重复做不会被 seed 计息(已有种判断保护);
            #   - seeding 任务:没有 brush() 入口,这是**唯一纳管点**——手动添加/IYUU
            #     回来的同站种靠这里纳管并保护。复用 brush() 入口的同名逻辑(2026-09-26
            #     设计:已纳管 / 跨站来源份 / 本插件自己刷的种三路分流)——一律跳过误纳管。
            try:
                _ad2 = self._adopt_same_site(task, downloader) or {}
                if int(_ad2.get("adopted") or 0) > 0:
                    self._emit_event(
                        "tag", action="同站纳管", level="info", task_id=task.id,
                        reason=f"新接管 {int(_ad2.get('adopted') or 0)} 个（匹配 {int(_ad2.get('matched') or 0)}）",
                        metrics={"count": int(_ad2.get("adopted") or 0), "matched": int(_ad2.get("matched") or 0)},
                        dedup_key=f"adopt:{task.id}:{int(_ad2.get('adopted') or 0)}",
                    )
            except Exception as _adopt_exc:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] Check 同站纳管异常: {_adopt_exc}", "warning")

            # ★ §1 点播：已形成资源组的点播种**直接转「资源」**（不观察、不分拣）
            try:
                _od = self._ondemand_settle(task)
                if _od.get("settled"):
                    self._dbg(f"魔流 [{task.name}] 点播转资源 {_od.get('settled')} 个")
            except Exception as _ode:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 点播结算异常: {_ode}", "warning")

            # ★ 3.43.0: 标签主权巡检 —— 别的插件/人私下挂的种立即归流、
            #   其他标签一律摘掉（先记账本再摘），MP 来源（订阅/自下）直接进资源。
            #   频控在 _tag_hygiene_round 内部（默认 900s），每轮 Check 都调无负担。
            try:
                _hy = self._tag_hygiene_round()
                if _hy.get("cleaned") or _hy.get("adopted") or _hy.get("promoted"):
                    self._dbg(f"魔流 [{task.name}] 标签巡检: {_hy}")
            except Exception as _hy_exc:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 标签巡检异常: {_hy_exc}", "warning")

            # ★ 7.6.0: 空壳种（文件已不在）认出即清 —— 既不产魔力也不产上传，
            #   以前只靠「恢复做种」白折腾（Master 2026-10-01 17:43）。
            try:
                _mf = self._missing_files_tick(apply=True)
                if _mf.get("deleted"):
                    self._dbg(f"魔流 [{task.name}] 空壳种清理 {_mf.get('deleted')} 个（待处理 {_mf.get('pending')}）")
            except Exception as _mfe:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 空壳种清理异常: {_mfe}", "warning")

            r = self._cleanup_round(task, downloader)
            _dec = dict((r or {}).get("decision") or {})
            # ★ 自动换种：名额/磁盘/站点上限吃紧时，按边际魔力换掉低价值种（程序自主决策）
            _sw: Dict[str, Any] = {}
            try:
                _sw = self._swap_round(task, downloader)
                if _sw.get("applied"):
                    r = dict(r or {})
                    r["swapped"] = int(_sw.get("applied", 0) or 0)
                    r["deleted"] = int(r.get("deleted", 0) or 0) + int(_sw.get("applied") or 0)
                elif _sw.get("reason") and _sw.get("trigger"):
                    self._dbg(f"魔流 [{task.name}] 换种未执行：{_sw.get('reason')}")
            except Exception as _swe:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 自动换种异常: {_swe}", "warning")
            try:
                _dec["swap"] = {
                    "triggered": bool(_sw.get("triggered")),
                    "trigger": str(_sw.get("trigger", "") or ""),
                    "reason": str(_sw.get("reason", "") or ""),
                    "applied": int(_sw.get("applied", 0) or 0),
                    "net": round(float(_sw.get("net") or 0.0), 2),
                }
            except Exception:  # noqa: BLE001
                pass
            self._note_decision(task.id, _dec)
            self._trend_sample_task(task, {**(r or {}), "decision": _dec})
            # ★ §5.2 满魔套牌存档：把当前在岗套牌写回（变了就更新；连续 N 轮不变 → 满魔冻结）
            try:
                _dk = self._deck_sync(task)
                if _dk.get("frozen") and not _dk.get("added") and not _dk.get("removed"):
                    self._dbg(f"魔流 [{task.name}] 套牌已冻结（满魔）：{_dk.get('total')} 张")
            except Exception as _dke:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 套牌维护异常: {_dke}", "warning")
            self._settle(WorkReport(
                task_id=task.id,
                source="check",
                status="done",
                added=0,
                deleted=int(r.get("deleted", 0) or 0),
                kept=int(r.get("kept", 0) or 0),
                decision=_dec,
            ))
            self._invalidate_summary()

        except Exception as e:
            self._log(f"魔流 [{task.name}] 执行失败: {e}", "error")
            self._emit_event("run", action="任务执行失败", level="error", task_id=task.id,
                             reason=str(e)[:300], dedup_key=f"runfail:{task.id}:{str(e)[:60]}")
            self._store.record_run_error(task.id, str(e))

    # ============================================================
    # ★ 自动换种（魔力口径）
    # ============================================================

    def _site_ceiling_pct(self, task: MagicFlowTaskConfig) -> float:
        """站点魔力占其理论上限的百分比（与总览口径一致，用于「接近上限」判断）。"""
        try:
            rep = self._site_reported(task) or {}
            b = float(rep.get("bonus_per_hour") or 0.0)
            ceil = float(site_ceiling(self._build_formula_params(task)) or 0.0)
            if ceil > 0:
                return min(b / ceil * 100.0, 999.0)
        except Exception:  # noqa: BLE001
            pass
        return 0.0

    def _build_magic_policy(
        self,
        task: MagicFlowTaskConfig,
        torrents: Optional[List[TorrentBonusInfo]] = None,
        debug: Optional[Dict[str, Any]] = None,
    ) -> MagicPolicy:
        """
        从任务配置构建魔力策略。

        留空(None)的字段会自动推算:
          - min_bonus_per_hour → 当前种子魔力中位数 × 0.5(无数据时为 0,不删)
          - bonus_protect_threshold → 站点当前魔力(读不到则不限)
          - max_keep_torrents  → 保种体积上限 ÷ 平均种子大小(无保种体积时为 None=不限)

        ★ 7.15.0 可观测：传 ``debug`` 字典时，把「本轮闸门判定」填进去
        （at_cap / 做种数 / 体积含辅种剔除 / 门槛 / 保护阈值 / max_keep），
        供上层汇入 WorkReport.decision，回答「为什么没换种」。
        """
        torrents = torrents or []

        threshold = task.min_bonus_per_hour
        if threshold is None:
            values = [t.bonus_per_hour for t in torrents if t.bonus_per_hour > 0]
            threshold = round(sorted(values)[len(values) // 2] * 0.5, 4) if values else 0.0

        protect = task.bonus_protect_threshold
        if protect is None:
            site_bonus = self._site_current_bonus(task.site_id)
            protect = site_bonus if site_bonus > 0 else float("inf")

        max_keep = task.max_keep_torrents
        if max_keep is None and task.disk_size_gb:
            sizes = [t.size_gb for t in torrents if t.size_gb > 0]
            avg_size = (sum(sizes) / len(sizes)) if sizes else 0.0
            if avg_size > 0:
                max_keep = max(int(task.disk_size_gb / avg_size), 1)

        # ★ 3.46.0 语义修正：「计入魔力的做种数上限」(``seeding_count_cap``，馒头=100)
        #   是**收益口径**，不是站点数量禁令——过去误当硬天花板，导致馒头挂着 131 个时
        #   直接「保种池已满」停摆。现在：
        #     ① 硬上限只认**站点规则**的 ``seed_cap``（站点禁令；馒头=不限）；
        #     ② 收益上限仅用于**提示**：超过后时魔不再增长，交给换种优化，不硬停。
        params = None
        try:
            params = self._build_formula_params(task)
        except Exception:
            params = None
        cap_n = int(getattr(params, "seeding_count_cap", 0) or 0)
        if cap_n > 0 and max_keep is not None and max_keep > cap_n:
            _seen = getattr(self, "_pool_cap_notice", None)
            if _seen is None:
                _seen = self._pool_cap_notice = {}
            if time.time() - float(_seen.get(task.id, 0.0) or 0.0) > 3600.0:
                _seen[task.id] = time.time()
                self._log(
                    f"任务 [{task.name}] 保种 {max_keep} 个 > 站点时魔计入上限 {cap_n}"
                    f"({getattr(task, 'site_domain', '') or task.site_id})：超出部分时魔不再增长"
                    f"（非禁令，不再硬限；由换种优化收益）"
                )

        # ★ 7.14.2 Master 口径（2026-10-02 09:16 / 09:57）：
        #   **「换种」只在到达上限之后才有意义**。两个上限口径，任一命中就算「满」：
        #     ① **做种数达站点「计入魔力的做种数上限」**(``seeding_count_cap``)；
        #     ② **达到任务设定的存储上限**(``task.disk_size_gb``)。
        #   都没到 → 「多挂 = 多产」，此时按门槛淘汰低效种 = 纯浪费
        #   （删掉了产出，又没换来更好的名额，因为名额/磁盘根本没用满）。
        #   ⇒ **未达上限 → 关闭「低效淘汰」（门槛 / 零魔 / 大文件）**，
        #     只清「0 产出垃圾」（无进度 / 过慢 / 非免费，走各自通道）；
        #     磁盘体积超限的强制淘汰保留（那是磁盘硬约束）。
        _managed_n = len(torrents)
        _site_n = 0
        try:
            _site_n = int(self._site_seeding_count(getattr(task, "site_id", 0)) or 0)
        except Exception:  # noqa: BLE001
            _site_n = 0
        _cur_n = max(_site_n, _managed_n)  # 站点账号数可能滞后/偏低，取与本任务托管数的较大者
        _count_at_cap = bool(cap_n > 0 and _cur_n >= cap_n)

        # ★ 7.14.2 Master 口径（09:57 补齐 / 10:15 修正）：**“满”有两个口径**——
        #   ① 做种数达站点「计入魔力的做种数上限」；② **达到任务设定的存储上限**（task.disk_size_gb）。
        #   任一命中 → 名额/磁盘已用满，此时「换种（淘汰低效、换入更优）」才有意义。
        #   ⚠️ **体积只算「本任务自己下载占用」的种**：**辅种（存量复用 / 跨站辅种，标 ``MARK_REUSE``）
        #   复用已有文件、不占新增磁盘，不计入**（Master 10:15：辅来的种不算自己体积）。
        _disk_gb = float(getattr(task, "disk_size_gb", 0) or 0)
        _cur_gb = 0.0
        _reuse_gb = 0.0
        try:
            _mgr = self._task_managed_torrents(task)
        except Exception:  # noqa: BLE001
            _mgr = []
        if _mgr:
            for _t in _mgr:
                _sz = float(getattr(_t, "size_gb", 0) or 0)
                if _sz <= 0:
                    _sz = float(getattr(_t, "size", 0) or 0) / (1024 ** 3)
                if _sz <= 0:
                    continue
                _tg = [str(x) for x in (getattr(_t, "tags", None) or [])]
                if MARK_REUSE in _tg:
                    _reuse_gb += _sz
                else:
                    _cur_gb += _sz
        else:
            _cur_gb = sum(float(getattr(t, "size_gb", 0) or 0) for t in torrents)
        _disk_at_cap = bool(_disk_gb > 0 and _cur_gb >= _disk_gb)

        at_cap = _count_at_cap or _disk_at_cap
        if debug is not None:
            debug.update({
                "at_cap": bool(at_cap),
                "cap_n": cap_n,
                "cur_n": _cur_n,
                "cur_gb": round(_cur_gb, 1),
                "reuse_gb": round(_reuse_gb, 1),
                "disk_gb": round(_disk_gb, 1),
                "at_cap_reason": ("站点做种数上限" if _count_at_cap else "存储上限" if _disk_at_cap else "未达上限"),
                "threshold": round(float(threshold or 0.0), 4),
                "protect": (None if protect == float("inf") else round(float(protect or 0.0), 2)),
                "max_keep": (int(max_keep) if max_keep is not None else None),
                "managed": _managed_n,
            })
        if not at_cap:
            if threshold and threshold > 0:
                self._dbg(
                    f"魔流 [{task.name}] 未达上限（做种 {_cur_n}/{cap_n or '∞'} · "
                    f"体积 {_cur_gb:.0f}/{_disk_gb:.0f}GB，辅种 {_reuse_gb:.0f}GB 不计）"
                    f" → 本轮不做低效换种（只清 0 产出垃圾）"
                )
            threshold = 0.0

        return MagicPolicy(
            min_bonus_per_hour=threshold,
            bonus_protect_threshold=protect,
            min_bonus_to_keep=task.min_bonus_to_keep or 0.0,
            max_keep_torrents=max_keep,
            min_seed_time_hours=float(task.min_seed_time or 0),
            min_ratio=float(getattr(task, "min_ratio", 0) or 0),
            weight_time_factor=1.0,
            weight_people_factor=1.0,
            weight_size=0.5,
            weight_zero_penalty=2.0,
            prefer_delete_zero_bonus=at_cap,
            prefer_delete_crowded=False,
            prefer_delete_high_ratio=False,
            prefer_delete_large=False,
            protect_perfect=bool(getattr(task, "protect_perfect", True)),
            perfect_max_seeders=int(getattr(task, "perfect_max_seeders", 3) or 0),
            perfect_min_weeks=float(getattr(task, "perfect_min_weeks", 4.0) or 0.0),
        )

    # ---------------------------------------------------------
    # 无进度清理(每次运行清一次「没进度」的种子)
    # ---------------------------------------------------------

    def _is_no_progress(self, torrent: TorrentInfo, task: MagicFlowTaskConfig, now: float) -> bool:
        """
        判断种子是否「没进度」:
          - 下载进度为 0(未下载出任何数据)
          - 处于停滞/出错/暂停状态(stalledDL / metaDL / error / missingFiles / pausedDL / pausedUP)
          - 已加入下载器超过 no_progress_minutes 分钟
        三者同时满足才判定为可清理,避免误删刚添加/正在下载的种子。

        ⚠️ 只删「进度=0」的:**在涨的慢种绝不删**(慢 ≠ 差,魔力是长期费率,
        下完就一直产),只有下不动的(0% 且无进度)才占着硬盘白吃饭。
        """
        try:
            state = str(getattr(torrent, "state", "") or "").strip().lower()
            progress = float(getattr(torrent, "progress", 0) or 0)
            downloaded = float(getattr(torrent, "downloaded", 0) or 0)
            added_on = float(getattr(torrent, "added_on", 0) or 0)
        except (TypeError, ValueError):
            return False
        if progress > 0.0001 or downloaded > 0:
            return False
        if state not in (QB_DEAD_STATES | QB_PAUSED_STATES):
            return False
        min_age = max(int(task.no_progress_minutes or 0), 1) * 60
        if added_on <= 0 or (now - added_on) < min_age:
            return False
        return True

    def _resume_paused_managed(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
    ) -> int:
        """
        自动恢复「带标签但被暂停」的**已完成**种子。

        被暂停 = tracker 不再计入做种 = 0 魔力产出,与魔力养护目标直接冲突;
        只恢复进度已完成(>=99.9%)的,半成品暂停(人工断点/待下载)不动。
        """
        resumed = 0
        skipped = 0
        manual_paused = self._store.get_manual_paused(task.id) if self._store else set()
        swap_paused = self._store.get_swap_paused(task.id) if self._store else set()
        for t in managed or []:
            state = str(getattr(t, "state", "") or "").lower()
            if state not in QB_PAUSED_STATES:
                continue
            h = getattr(t, "hash", "") or ""
            # 用户手动暂停的种子不自动恢复(尊重人工干预,需界面上点「恢复做种」)
            if h and (h or "").lower() in manual_paused:
                skipped += 1
                continue
            # 换种下线的种子同理：换出只是不再拉它做种，等站点腾出空间时由换回逻辑恢复
            if h and (h or "").lower() in swap_paused:
                skipped += 1
                continue
            if float(getattr(t, "progress", 0) or 0) < 0.999:
                skipped += 1
                continue
            if not h:
                continue
            try:
                if downloader.resume_torrent(h):
                    resumed += 1
                    self._log(f"恢复做种:{str(getattr(t, 'title', '') or '')[:40]}")
            except Exception as err:
                self._log(f"恢复做种失败 {h[:8]}: {err}", "warning")
        if resumed or skipped:
            self._log(
                f"魔流 [{task.name}] 自动恢复暂停种子:恢复 {resumed} 个"
                f"(跳过未完成 {skipped} 个)"
            )
        return resumed

    def _brush_idle_params(self, task: MagicFlowTaskConfig) -> Tuple[int, float, float]:
        """刷流「无上传」判定参数 → (需连续低于门槛的次数 need, 单次检查上传字节门槛 thr, 宽限秒 grace)。

        门槛按「平均上传速率」折算:``thr = upload_min_kbps × 1024 × 检查间隔秒``。
        每次检查比对 uploaded 增量,增量 < thr(即平均速率低于门槛)即累加一次「冷」。
        """
        ci = max(int(getattr(task, "check_interval", 1) or 1), 1) * 60
        grace = max(int(getattr(task, "brush_grace_minutes", 15) or 0), 0) * 60
        idle_min = int(getattr(task, "upload_idle_minutes", 10) or 0)
        if idle_min <= 0:
            idle_min = max((2 * ci) // 60, 1)  # 自动:约 2×检查间隔
        need = max(int(round(idle_min * 60 / ci)), 1)
        kbps = float(getattr(task, "upload_min_kbps", 200) or 0)
        thr = kbps * 1024 * ci
        return need, thr, grace

    def _build_filter_policy(self, task: MagicFlowTaskConfig) -> FilterPolicy:
        """从任务配置构建过滤策略。"""
        _is_brush = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"
        # 刷流有自己的选种标准(不看魔力口径):不设人数上限、体积/年龄不限、不排除零魔、
        # 只要求「有下载需求」(下载人数 ≥ min_leechers)。
        policy = get_default_brush_filter_policy() if _is_brush else get_default_filter_policy()

        if _is_brush:
            try:
                policy.min_leechers = max(int(getattr(task, "brush_min_leechers", 1) or 0), 0)
            except (TypeError, ValueError):
                policy.min_leechers = 1

        if task.seeder:
            try:
                parts = task.seeder.split("-")
                if len(parts) == 1:
                    policy.max_seeders = int(float(parts[0]))
                elif len(parts) == 2:
                    policy.min_seeders = int(float(parts[0]))
                    policy.max_seeders = int(float(parts[1]))
            except Exception:
                pass

        if task.size:
            try:
                parts = task.size.split("-")
                if len(parts) == 2:
                    policy.min_size_gb = float(parts[0])
                    policy.max_size_gb = float(parts[1])
            except Exception:
                pass

        # 发布时间范围(分钟):单值或「最小-最大」
        if getattr(task, "pubtime", ""):
            try:
                parts = str(task.pubtime).split("-")
                if len(parts) == 1:
                    policy.pub_minutes_max = float(parts[0])
                elif len(parts) == 2:
                    policy.pub_minutes_min = float(parts[0])
                    policy.pub_minutes_max = float(parts[1])
            except Exception:
                pass

        policy.include_pattern = task.include
        policy.exclude_pattern = task.exclude
        policy.exclude_zero_bonus = task.exclude_zero_bonus
        # ★ 7.9.0 系统硬规则：**只下免费**（非免费一概不碰——下几百 G 非免费流量靠刷流补不回来）。
        #   任务字段 freeleech 只用于**进一步收窄**：""/ "free" → 免费(含 2X免费)；
        #   "2xfree" → 只 2X 免费。（历史坑：字段留空 = 不判断 → 会照下非免费，且新任务默认就是空。）
        mode = (task.freeleech or "").strip().lower()
        policy.free_only = True
        policy.double_free_only = mode == "2xfree"
        # 「排除 H&R」选项(hr=yes → 过滤掉 H&R 种子)
        if str(getattr(task, "hr", "") or "").strip().lower() in ("yes", "y", "1", "true", "是"):
            policy.exclude_hnr = True
        # 考核下载模式:目的就是凑「下载增量」→ 放开免费限制(只在该模式下)
        try:
            if self._exam_download_active(task):
                policy.free_only = False
                policy.double_free_only = False
        except Exception:  # noqa: BLE001
            pass
        return policy

    def _same_site_state_live(self, task: Any) -> str:
        """同站同状态是否有**在岗（运行中/做种中）**的任务（有则那批种归它，已停止的任务不用退静默）。"""
        try:
            pair = self._task_site_state(task)
        except Exception:  # noqa: BLE001
            return ""
        tid = str(getattr(task, "id", "") or "")
        for other in self._task_configs.values():
            if str(getattr(other, "id", "") or "") == tid:
                continue
            if not task_is_participating(other):
                continue
            try:
                if self._task_site_state(other) == pair:
                    return str(getattr(other, "name", "") or "")
            except Exception:  # noqa: BLE001
                continue
        return ""
