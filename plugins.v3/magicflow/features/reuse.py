# -*- coding: utf-8 -*-
"""魔流 · reuse —— 复用取种（本机/IYUU/MP 搜索，统一入口 _acquire_existing）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


from app.sdk.logging import logger

from ..downloader_ops import (
    DownloaderAdapter,
    TorrentInfo,
    TorrentFetchFlowControl,
    QB_DOWNLOADING_STATES,
    QB_PAUSED_STATES,
)
from ..fingerprint import fingerprint, info_hash
from ..fetcher import (
    SiteFetcher,
    filter_candidates,
)
from ..persistence import OperationItem, WorkReport
from ..sites.formula_fetch import (
    fetch_torrent_promotion,
    fetch_user_torrent_urls,
)


from ..common import (
    BROWSE_PAGES,
    MagicFlowTaskConfig,
    REUSE_WORKER_BATCH,
    _SizeIndex,
    task_is_running,
)


class ReuseMixin:
    """reuse 功能集（原 MagicFlow 方法原样搬入）。"""

    # ------------------------------------------------------------------ 辅种慢扫
    def reuse_scan(self) -> None:
        """辅种慢扫(插件级**单 worker**,低频)。

        不再每任务注册服务,而是**一个插件级服务**遍历所有符合条件的魔力任务,
        每轮只处理其中**一个**(round-robin)→ 服务数不随任务数增长,天然错峰/限流,
        避免几十个任务在同一时刻一起取种、撞站点流控。
        刷流任务只辅助「排名内」的种子(主流程顺带做),不纳入。
        """
        eligible = [
            t for t in self._task_configs.values()
            if getattr(t, "enabled", False) and getattr(t, "reuse_existing", False)
            and str(getattr(t, "task_type", "bonus") or "bonus").strip().lower() != "brush"
        ]
        if not eligible:
            return
        eligible.sort(key=lambda t: str(t.id))
        ids = [str(t.id) for t in eligible]
        last = str(getattr(self, "_reuse_cursor", "") or "")
        start = (ids.index(last) + 1) % len(eligible) if last in ids else 0
        task = eligible[start]
        self._reuse_cursor = str(task.id)
        if not self._acquire_worker_slot("辅种慢扫"):
            return
        try:
            try:
                self._reuse_scan_task(task)
            except Exception as e:  # noqa: BLE001
                import traceback
                logger.error(f"魔流 辅种慢扫 调度异常: {e}\n{traceback.format_exc()}")
        finally:
            self._release_worker_slot()

    def _reuse_scan_task(self, task: MagicFlowTaskConfig) -> None:
        """对单个任务做一轮辅种慢扫(内部实现)。"""
        task_id = str(task.id)
        if not task_is_running(task) or not task.reuse_existing:
            return
        if str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush":
            return
        if not self._try_begin_run(task_id):
            self._log(f"魔流 [{task.name}] 辅种慢扫:上一轮仍在执行,跳过")
            return
        started = time.time()
        reused = 0
        scanned = 0
        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                self._log(f"魔流 [{task.name}] 辅种慢扫:下载器不可用", "warning")
                return
            if not task.site_domain:
                site = self._get_site(task.site_id)
                if site:
                    task.site_domain = getattr(site, "domain", "") or task.site_domain
            try:
                local_index, local_by_size = self._local_reuse_index(downloader)
            except Exception as _le:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 辅种慢扫:建本机索引失败 {_le}", "warning")
                return
            if not local_index:
                return

            fetcher = SiteFetcher()
            if not fetcher.is_available:
                return
            pages = max(int(task.browse_pages or BROWSE_PAGES), 1)
            # 站点级共享抓取:同站多任务共用一份候选(single-flight + 短 TTL)
            candidates = self._fetch_site_candidates(task, pages=pages, start_page=0)
            if not candidates:
                return
            filter_policy = self._build_filter_policy(task)
            filtered, _rc = filter_candidates(candidates, filter_policy)

            # 选「体积邻近本机」且尚未由本 worker 处理过的候选
            pool = []
            for c in filtered:
                if not getattr(c, "enclosure", "") and not getattr(c, "api_tid", ""):
                    continue
                ckey = self._candidate_key(c)
                if not ckey:
                    continue
                if self._store and self._store.seen.is_seen(task.id, f"reuse:{ckey}", 0):
                    continue
                if not local_by_size.near(int(getattr(c, "size", 0) or 0)):
                    continue
                pool.append(c)
            if not pool:
                return
            pool = pool[: max(int(REUSE_WORKER_BATCH), 1)]
            scanned = len(pool)

            fp_cache: Dict[str, Optional[str]] = {}
            tag = task.brush_tag
            for c in pool:
                ckey = self._candidate_key(c)
                raw = None
                # ★ 3.44.0 API 站候选：现场取签名直链
                if not getattr(c, "enclosure", ""):
                    try:
                        self._cand_enclosure(c)
                    except Exception:  # noqa: BLE001
                        pass
                if not getattr(c, "enclosure", ""):
                    continue
                try:
                    raw = downloader.fetch_torrent_bytes(
                        c.enclosure,
                        cookie=getattr(c, "site_cookie", None),
                        user_agent=getattr(c, "site_ua", None),
                        referer=getattr(c, "page_url", "") or None,
                    )
                except TorrentFetchFlowControl as _fe:
                    self._log(f"魔流 [{task.name}] 辅种慢扫:站点流控,本轮中止({_fe})", "warning")
                    break
                except Exception:  # noqa: BLE001
                    raw = None
                if self._store and ckey:
                    self._store.seen.mark(task.id, [f"reuse:{ckey}"])
                if not raw:
                    continue
                try:
                    c.raw = raw
                    h = (info_hash(raw) or "").lower()
                except Exception:  # noqa: BLE001
                    h = ""

                mode, linfo = "", None
                if h and h in local_index:
                    _loc = local_index[h]
                    if str(getattr(_loc, "state", "") or "").lower() not in QB_DOWNLOADING_STATES:
                        mode, linfo = "hash", _loc
                if not mode:
                    mode, linfo = self._detect_crosssite_reuse(downloader, c, local_by_size, fp_cache, raw=raw)
                if not mode or linfo is None:
                    continue

                if mode == "hash":
                    ok = downloader.set_torrent_tags(h, [tag])
                    st = str(getattr(linfo, "state", "") or "").lower()
                    if ok and st in (QB_PAUSED_STATES | {"error", "missingfiles"}):
                        downloader.resume_torrent(h)
                    if ok:
                        reused += 1
                        self._log(f"魔流 [{task.name}] 辅种慢扫·复用(本机同 hash):{c.title}")
                else:
                    hs, err = downloader.add_torrent_reuse(
                        torrent_bytes=raw,
                        save_path=(getattr(linfo, "save_path", "") or task.save_path or ""),
                        tag=tag,
                        verify=task.reuse_verify,
                    )
                    if hs:
                        reused += 1
                        self._log(f"魔流 [{task.name}] 辅种慢扫·跨站辅种:{c.title}")
                    elif err:
                        self._log(f"魔流 [{task.name}] 辅种慢扫·辅种失败:{c.title}({err})", "warning")

            self._log(
                f"魔流 [{task.name}] 辅种慢扫完成:命中 {reused} 个(本轮扫 {scanned} 个候选,"
                f"耗时 {time.time() - started:.1f}s)"
            )
            # 分账:慢扫走独立命名空间(slow_reused),不碰刷流/检查的 last_* 字段
            self._settle(WorkReport(
                task_id=task_id,
                source="reuse",
                status="done",
                slow_reused=reused,
                scanned=scanned,
                duration=time.time() - started,
            ))
            if self._store:
                self._store.journal.add(
                    task_id=task_id,
                    kind="reuse",
                    items=[OperationItem(
                        hash="", title=f"辅种慢扫:命中 {reused} / 扫 {scanned}",
                        reason="复用(本机已有资源)", source="reuse",
                    )],
                )
        except Exception as e:  # noqa: BLE001
            import traceback
            logger.error(f"魔流 辅种慢扫异常: {e}\n{traceback.format_exc()}")
            self._log(f"魔流 [{task.name}] 辅种慢扫异常:{e}", "warning")
        finally:
            self._end_run(task_id)

    def _seen_page_pairs(self, task_id: str) -> Dict[str, str]:
        """从 seen 记录重建 hash→详情页 URL。

        插件写入 seen 时会把 ``hash:<h>`` 与 ``cand:<url>`` 用**同一时间戳**批量写入,
        故可按时间戳配对得到历史种子的详情页链接(老数据无 torrent_pages 时的回摆)。
        """
        if not self._store:
            return {}
        bucket = self._store.seen.get_bucket(task_id)
        if not bucket:
            return {}
        by_ts: Dict[float, List[str]] = {}
        for key, ts in bucket.items():
            try:
                by_ts.setdefault(round(float(ts), 3), []).append(str(key))
            except (TypeError, ValueError):
                continue
        pages: Dict[str, str] = {}
        for keys in by_ts.values():
            h = u = ""
            for k in keys:
                if k.startswith("hash:"):
                    h = k[5:]
                elif k.startswith("h:"):
                    h = k[2:]
                elif k.startswith("cand:"):
                    u = k[5:]
                elif k.startswith("http"):
                    u = k
            if h and u:
                pages[h.lower()] = u
        return pages

    def _title_url_map(self, task: MagicFlowTaskConfig, site: Any) -> Dict[str, str]:
        """站点「我的种子」列表(下载中+做种)→ {规范化标题: 详情页URL}(带缓存)。"""
        cache = getattr(self, "_title_url_cache", None)
        if cache is None:
            cache = self._title_url_cache = {}
        now = time.time()
        hit = cache.get(task.id)
        if hit and (now - hit[1]) < self._TITLE_URL_TTL:
            return hit[0]
        mapping: Dict[str, str] = {}
        try:
            uid = self._site_user_id(site)
            if uid:
                for ttype in ("leeching", "seeding"):
                    mapping.update(fetch_user_torrent_urls(site, uid, ttype))
        except Exception as err:
            self._log(f"魔流 [{task.name}] 回填详情页链接失败: {err}", "info")
        cache[task.id] = (mapping, now)
        return mapping

    def _promotion_of(self, task: MagicFlowTaskConfig, site: Any, hash_string: str, page_url: str) -> Dict[str, Any]:
        """回站点抗取种子当前促销状态(带内存缓存)。"""
        cache = getattr(self, "_promo_cache", None)
        if cache is None:
            cache = self._promo_cache = {}
        key = (hash_string or "").lower()
        now = time.time()
        hit = cache.get(key)
        if hit and (now - hit[1]) < self._PROMO_TTL:
            return hit[0]
        if not site or not page_url:
            return {"promotion": "unknown", "raw": ""}
        try:
            info = fetch_torrent_promotion(site, page_url)
        except Exception as err:
            info = {"promotion": "unknown", "raw": "", "error": str(err)}
        cache[key] = (info, now)
        return info

    def _is_dead_cached(self, task_id: str, torrent_hash: str) -> bool:
        """近期刚被判定「没进度」并清掉的种子,短时间内不再重复添加。"""
        if not torrent_hash:
            return False
        key = (torrent_hash or "").lower()
        if self._store and self._store.dead.is_dead(task_id, f"hash:{key}", self._dead_cooldown):
            return True
        ts = self._dead_hashes.get(key)
        if not ts:
            return False
        if time.time() - ts > self._dead_cooldown:
            self._dead_hashes.pop(key, None)
            return False
        return True

    @staticmethod
    def _candidate_key(cand: Any) -> str:
        """候选种子的稳定标识(优先详情页链接,其次下载链接,避免带 passkey 变动)。"""
        for attr in ("page_url", "enclosure", "hash", "title"):
            value = getattr(cand, attr, None)
            if value:
                return str(value).strip()
        return ""

    def _local_reuse_index(
        self, downloader: DownloaderAdapter
    ) -> Tuple[Dict[str, TorrentInfo], "_SizeIndex"]:
        """本机(下载器)全部种子索引:hash(小写) -> info;体积邻近索引(含容差)。"""
        index = downloader.get_all_torrents_index()
        return index, _SizeIndex(list(index.values()), tol=0.05)

    def _try_reuse_candidate(
        self,
        downloader: DownloaderAdapter,
        cand: Any,
        local_by_size: "_SizeIndex",
        fp_cache: Dict[str, Optional[str]],
        task: MagicFlowTaskConfig,
        raw: Optional[bytes] = None,
    ) -> Tuple[bool, str]:
        """
        尝试把候选种子辅到本机已有文件上。

        仅当「文件列表特征码」(路径 + 大小,含根目录名)完全一致时才辅种,
        避免误指向导致下载器白下载。返回 (是否成功, 信息);信息为 "skip" 表示未命中。
        """
        size = int(cand.size or 0)
        if size <= 0:
            return False, "skip"
        same_size = local_by_size.near(size)
        if not same_size:
            return False, "skip"

        if raw is None:
            try:
                raw = downloader.fetch_torrent_bytes(
                    cand.enclosure, cookie=cand.site_cookie, user_agent=cand.site_ua
                )
            except TorrentFetchFlowControl:
                return "", None
        if not raw:
            return False, "skip"
        cand_fp = fingerprint(raw)
        if not cand_fp:
            return False, "skip"

        for local in same_size:
            local_hash = (local.hash or "").lower()
            if not local_hash:
                continue
            if local_hash not in fp_cache:
                fp_cache[local_hash] = downloader.get_torrent_fingerprint(local.hash)
            if fp_cache.get(local_hash) != cand_fp:
                continue

            hash_string, error = downloader.add_torrent_reuse(
                torrent_bytes=raw,
                save_path=local.save_path or task.save_path or "",
                tag=task.brush_tag,
                verify=task.reuse_verify,
            )
            if hash_string:
                self._log(f"辅种成功:{cand.title} ← 复用「{local.title}」")
                return True, ""
            return False, error or "辅种失败"
        return False, "skip"

    def _detect_crosssite_reuse(
        self,
        downloader: DownloaderAdapter,
        cand: Any,
        local_by_size: "_SizeIndex",
        fp_cache: Dict[str, Optional[str]],
        raw: Optional[bytes] = None,
    ) -> Tuple[str, Optional[TorrentInfo]]:
        """
        跨站辅种**匹配判定**(只判定,不添加)。

        候选与本机某种子「文件列表特征码」完全一致时返回 ("cross", 本机种子),
        否则返回 ("", None)。真正的添加在后续处理循环里执行。
        """
        size = int(getattr(cand, "size", 0) or 0)
        raw = getattr(cand, "raw", None)
        if size <= 0 or not raw:
            return "", None
        same = local_by_size.near(size)
        if not same:
            return "", None
        cand_fp = fingerprint(raw)
        if not cand_fp:
            return "", None
        for local in same:
            lh = (local.hash or "").lower()
            if not lh:
                continue
            if lh not in fp_cache:
                fp_cache[lh] = downloader.get_torrent_fingerprint(local.hash)
            if fp_cache.get(lh) == cand_fp:
                return "cross", local
        return "", None

    # ---------------------------------------------------------- 取种（存量复用）统一入口（3.37.4 / docs/MODULES.md X7）
    #  一个职责 = 一个模块 = 一个入口。此前刷流循环、换种各自内联一套「找本机同资源」，
    #  口径容易漂。现统一走 _acquire_existing：本机同 hash → 本机同 Release → IYUU 云端，
    #  命中即返回（**只做零下载复用**，任何「下载」都由调用方在成本闸门之后自行执行）。

    def _acquire_existing(
        self,
        task: MagicFlowTaskConfig,
        cand: Any,
        downloader: DownloaderAdapter,
        *,
        local_index: Optional[Dict[str, TorrentInfo]] = None,
        local_by_size: Optional["_SizeIndex"] = None,
        fp_cache: Optional[Dict[str, Optional[str]]] = None,
        iyuu_map: Optional[Dict[str, List[str]]] = None,
        raw: Optional[bytes] = None,
        stats: Optional[Dict[str, int]] = None,
        respect_task_flag: bool = True,
    ) -> Tuple[str, Optional[TorrentInfo]]:
        """★ **取种统一入口**：按成本从低到高找「本机已有的同一 Release」。

        阶梯（命中即返回）：
          ① 本机同 hash（不限标签）→ 改标签复用，零下载；
          ② 本机同 Release（完整特征码，含根目录名）→ 指向其目录辅种；
          ③ IYUU 云端（配了 token 时）→ 云端反查的兄弟站同资源 infohash 若本机已完成 → 复用。

        返回 (mode, info)：mode ∈ {"hash", "cross", ""}；info 为命中的本机种子。
        `stats`（可选）累计 {"near","fp","iyuu"} 供调用方日志。
        `respect_task_flag=False` 用于「换种」这类**本就以复用为先**的场景（不受任务 reuse_existing 约束）。
        """
        if cand is None or downloader is None:
            return "", None
        if respect_task_flag and not bool(getattr(task, "reuse_existing", True)):
            return "", None
        if fp_cache is None:
            fp_cache = {}
        iyuu_map = iyuu_map or {}
        h = str(
            getattr(cand, "real_hash", "")
            or getattr(cand, "hash", "")
            or ""
        ).strip().lower()
        # ① 本机同 hash
        if local_index and h:
            local = local_index.get(h)
            if local is not None and str(
                getattr(local, "state", "") or ""
            ).lower() not in QB_DOWNLOADING_STATES:
                return "hash", local
        if local_by_size is None:
            return "", None
        size = int(getattr(cand, "size", 0) or 0)
        if size <= 0:
            return "", None
        # ② 本机同 Release（特征码）
        if local_by_size.near(size):
            if stats is not None:
                stats["near"] = int(stats.get("near", 0)) + 1
            mode, info = self._detect_crosssite_reuse(
                downloader, cand, local_by_size, fp_cache, raw=raw
            )
            if mode and info is not None:
                if stats is not None:
                    stats["fp"] = int(stats.get("fp", 0)) + 1
                return mode, info
        # ③ IYUU 云端补齐
        if local_index and iyuu_map and h:
            for sib in (iyuu_map.get(h) or []):
                loc = local_index.get(str(sib or "").lower())
                if loc is None:
                    continue
                if str(getattr(loc, "state", "") or "").lower() in QB_DOWNLOADING_STATES:
                    continue
                if stats is not None:
                    stats["iyuu"] = int(stats.get("iyuu", 0)) + 1
                return "cross", loc
        return "", None

    # ---------------------------------------------------------- 契约② AcquireSource：取种「唯一入口」
    #  一个职责 = 一个模块 = 一个入口（docs/CONTRACTS.md 契约②）。
    #  来源链（按成本从低到高，命中即止）：
    #    ① hash     本机下载器已有同 hash（不限 tag）→ 改标签复用（零下载）
    #    ② cross    本机同 Release（完整特征码，含根目录名）→ 指向其目录辅种（零下载）
    #    ③ iyuu     IYUU 云端反查的兄弟站同资源、且本机已完成 → 复用（零下载）
    #    ④ crossseed 兄弟站「免费且同一 Release」副本 → 下回来回辅本站（**仅免费**；拿不到免费额就整单跳过）
    #  ★ 铁律：任何「真下载」只能由第 ④ 跳发起，且**必须先确认免费**；否则返回空、由调用方跳过。
    #  ★ 调用方（刷流 / 换种 / 跨站 / 调试）**只能**走本入口，不得再直接调 `_crossseed_start`

    def _acquire_source(
        self,
        task: MagicFlowTaskConfig,
        cand: Any,
        downloader: DownloaderAdapter,
        *,
        local_index: Optional[Dict[str, TorrentInfo]] = None,
        local_by_size: Optional["_SizeIndex"] = None,
        fp_cache: Optional[Dict[str, Optional[str]]] = None,
        iyuu_map: Optional[Dict[str, List[str]]] = None,
        raw: Optional[bytes] = None,
        stats: Optional[Dict[str, int]] = None,
        respect_task_flag: bool = True,
        allow_cross_site: bool = False,
        cross_site_guard: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """★ 取种统一入口（契约②）。返回 ``{"source", "info", "sib_hash", "reason"}``。

        - ``source`` ∈ ``{"hash", "cross", "iyuu", "crossseed", ""}``（空 = 没拿到）。
        - ``info``：命中的**本机**种子（① ② ③）；``sib_hash``：第 ④ 跳新加的**兄弟站**种子 hash。
        - ``allow_cross_site``：是否允许第 ④ 跳（跨站免费取种）。默认关；**只有**已过成本闸门的
          调用方（刷流下载分支 / 换种 / 跨站功能页）才置 True。
        - ``cross_site_guard``：可选闸门回调 ``() -> bool``，返回 False 则**不做**第 ④ 跳
          （调用方用来表达「名额/预算/体积上限不满足」）。
        """
        result: Dict[str, Any] = {"source": "", "info": None, "sib_hash": "", "reason": ""}
        mode, info = self._acquire_existing(
            task, cand, downloader,
            local_index=local_index, local_by_size=local_by_size, fp_cache=fp_cache,
            iyuu_map=iyuu_map, raw=raw, stats=stats, respect_task_flag=respect_task_flag,
        )
        if mode and info is not None:
            result.update({"source": mode, "info": info})
            return result
        if not allow_cross_site:
            result["reason"] = "本机/IYUU 未命中，且未开启跨站取种"
            return result
        if cross_site_guard is not None:
            try:
                if not bool(cross_site_guard()):
                    result["reason"] = "跨站闸门未放行（名额/预算/体积）"
                    return result
            except Exception:  # noqa: BLE001
                result["reason"] = "跨站闸门异常 → 保守跳过"
                return result
        sib = None
        try:
            sib = self._crossseed_start(task, cand, downloader)
        except Exception as err:  # noqa: BLE001
            result["reason"] = f"跨站取种异常:{err}"
            return result
        if sib:
            result.update({"source": "crossseed", "sib_hash": str(sib)})
        else:
            result["reason"] = "跨站无「免费同 Release」副本 → 跳过（绝不付费下载）"
        return result
