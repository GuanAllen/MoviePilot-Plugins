# -*- coding: utf-8 -*-
"""魔流 · crossseed —— 跨站免费取种 + 回辅本站。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import re
import threading
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple


from app.schemas import Response
from app.sdk.logging import logger

from ..downloader_ops import (
    DownloaderAdapter,
    QB_DOWNLOADING_STATES,
    QB_PAUSED_STATES,
)
from ..fingerprint import fingerprint, info_hash
from ..live_stats import title_match
from ..persistence import OperationItem
from ..crossseed import (
    CROSSSEED_TAG,
    CrossSeedPending,
    CrossSeedSources,
    pick_source,
    search_key,
)
from ..dtier import TierCache
from ..sites.rules import (
    BUILTIN_RULES,
)
from ..tags import (
    SPECIAL_TAGS,
    STATE_SILENT,
    SUB_NEW,
    SUB_RESOURCE,
    is_magicflow_tag,
    tag_for,
)


from ..common import (
    SILENT_HOST_TASK_ID,
    CROSSSEED_CACHE_TTL,
    CROSSSEED_EXTRA_SCAN,
    CROSSSEED_SEED_HOURS_DEFAULT,
    MagicFlowTaskConfig,
    _torrent_entries_digest,
)


class CrossSeedMixin:
    """crossseed 功能集（原 MagicFlow 方法原样搬入）。"""

    # ---------------------------------------------------------- 跨站免费取种（3.9.0）
    #  目标站 A 上「下载量大」的种子若在 A **不免费**（下载要烧流量/拉低分享率），
    #  就去**任意他站**（B/C/D/E…）找「免费且同一 Release」的副本下回来，再回辅到 A：
    #  对 A 是「零下载纯做种」→ 白赚 A 站上传与魔力。
    #  红线：① 同一 Release（fingerprint 完整特征码，含根目录名）才算命中；
    #        ② 免费是硬门槛（只从他站的**免费视图**取候选）；③ 每次取种都过 PV 闸门。

    def _crossseed_sources(self) -> CrossSeedSources:
        """来源站份的保护账本（H&R 保种期内不得被任何任务删除/改标签）。"""
        obj = getattr(self, "_crossseed_src_obj", None)
        if obj is None:
            obj = self._crossseed_src_obj = CrossSeedSources(
                get_data=self.get_data,
                save_data=self.save_data,
                log=self._log,
            )
        return obj

    def _crossseed_source_hashes(self) -> Set[str]:
        """当前受 H&R 保护的来源份 hash 集合（并入清理保护集合）。

        ★ 排除「义务已履行」（实测做种时长达标）的条目 —— 挂够就能撤，不必再占位。
        ★ 30s TTL 缓存：统计/总览路径会逐任务调它，避免每任务都读一次来源份 kv。
        """
        cached = getattr(self, "_cs_src_hashes_cache", None)
        if cached is not None:
            _ts, _val = cached
            if time.time() - float(_ts) < 30.0:
                return _val
        try:
            val = self._crossseed_sources().active()
        except Exception:  # noqa: BLE001
            val = set()
        self._cs_src_hashes_cache = (time.time(), val)
        return val

    def _crossseed_seed_hours(self, domain: str) -> float:
        """该来源站要求的 H&R 最短保种时长(小时)：站点覆盖 > 全局默认。

        优先采信本站「正在下载」列表 / MP 搜索给出的信号（若有），否则用配置。
        """
        hours, _src = self._crossseed_seed_hours_detail(domain)
        return hours

    def _crossseed_seed_need_hours(self, domain: str) -> float:
        """站点要求的「**实际做种**达标小时数」（如学校 20h）；没有则 0（只看窗口）。"""
        dom = str(domain or "").strip().lower()
        dom = re.sub(r"^https?://", "", dom).split("/")[0].strip()
        try:
            rec = dict(self._site_rules().get(dom) or {})
        except Exception:  # noqa: BLE001
            rec = {}
        for key in ("seed_need_hours",):
            try:
                val = float(rec.get(key) or 0.0)
            except (TypeError, ValueError):
                val = 0.0
            if val > 0:
                return val
        try:
            builtin = dict(BUILTIN_RULES.get(dom) or {})
            return float(builtin.get("seed_need_hours") or 0.0)
        except Exception:  # noqa: BLE001
            return 0.0

    def _crossseed_hr_decision(
        self, domain: str, torrent_hr: Any = None
    ) -> Tuple[bool, float, str]:
        """★ H&R 判定优先级：**种子里有 H&R 信息 → 以种子为准；没有 → 兜底站点规则库**。

        - ``torrent_hr is True``：种子自带 H&R 标记 → 一定保护（时长取站点库/默认）。
        - ``torrent_hr is False``：**只有当站点库也明确说「无 H&R」时才采信**（因为 MP 侧
          字段默认 False，站点适配器没配 ``hr`` 选择器时全是 False，不能当「无 H&R」用）。
        - 其余（无种子级信息 / 站点库未知）：按站点库 → 未知则保守保护 24h。

        Returns: ``(是否保护, 保种小时数, 来源说明)``
        """
        hours, hsrc = self._crossseed_seed_hours_detail(domain)
        site_hr = self._site_hr_flag(domain)
        if torrent_hr is True:
            use = float(hours) if float(hours or 0.0) > 0 else float(CROSSSEED_SEED_HOURS_DEFAULT)
            return True, use, f"种子标记/{hsrc}"
        if torrent_hr is False and site_hr is False:
            return False, 0.0, "种子未标H&R+站点无H&R"
        if site_hr is False:
            return False, 0.0, f"站点规则({hsrc})无H&R"
        if site_hr is None:
            return True, float(hours or 0.0), f"未知保守/{hsrc}"
        return True, float(hours or 0.0), f"站点规则/{hsrc}"

    def _crossseed_seed_hours_detail(self, domain: str) -> Tuple[float, str]:
        """返回 ``(保种小时数, 来源)``。来源: manual > 规则库(probe/builtin) > 全局默认。"""
        dom = str(domain or "").strip().lower()
        dom = re.sub(r"^https?://", "", dom).split("/")[0].strip()
        cfg = getattr(self, "_cs_cfg", {}) or {}
        manual = cfg.get("site_hours") or {}
        if not isinstance(manual, dict):
            manual = {}
        try:
            default = float(cfg.get("seed_hours_default") or CROSSSEED_SEED_HOURS_DEFAULT)
        except (TypeError, ValueError):
            default = CROSSSEED_SEED_HOURS_DEFAULT
        try:
            return self._site_rules().resolve(dom, manual, default)
        except Exception:  # noqa: BLE001
            return max(0.0, default), "default"

    def _crossseed_pending(self) -> CrossSeedPending:
        """待回辅账本（PluginData 持久化 + 目标站 .torrent 落盘）。"""
        obj = getattr(self, "_crossseed_obj", None)
        if obj is None:
            try:
                base = self.get_data_path() / "crossseed"
            except Exception:  # noqa: BLE001
                base = None
            obj = self._crossseed_obj = CrossSeedPending(
                get_data=self.get_data,
                save_data=self.save_data,
                dir_path=base if base is not None else "crossseed",
                log=self._log,
            )
        return obj

    def _crossseed_lock(self) -> threading.Lock:
        """跨站取种专用锁（低频率，一把全局锁即可，避免同刻重复打同一站）。"""
        lock = getattr(self, "_crossseed_lock_obj", None)
        if lock is None:
            lock = self._crossseed_lock_obj = threading.Lock()
        return lock

    def _crossseed_cache(self) -> TierCache:
        """跨站检索结果缓存（内存热层 + FileCache 冷层，跨热重载不丢）。

        存的是「站点无关的普通 dict 行」（MP 搜索结果的精简快照），所以编解码就是恒等。
        """
        cache = getattr(self, "_tier_cross_obj", None)
        if cache is None:
            cache = self._tier_cross_obj = TierCache("cross", base=self._cache_base())
        return cache

    def _mp_search_title(self, keyword: str, sites: List[int]) -> List[Any]:
        """调 MoviePilot 自带搜索（`SearchChain.search_by_title`），**兼容不同版签名**。

        只搜指定的站（`sites`）；若该版本不支持 `sites` 就不搜（不能限制就宁可不动 —— 不然会搜到全站、白烧 PV）。
        """
        from app.chain.search import SearchChain  # noqa: WPS433

        chain = SearchChain()
        fn = getattr(chain, "search_by_title", None)
        if fn is None:
            return []
        kwargs: Dict[str, Any] = {}
        try:
            import inspect  # noqa: WPS433

            params = set(inspect.signature(fn).parameters.keys())
        except Exception:  # noqa: BLE001
            params = set()
        if "sites" not in params:
            self._log("跨站:当前 MP 版本搜索不支持限定站点,放弃(避免搜全站烧 PV)", "warning")
            return []
        kwargs["sites"] = sites
        if "rule_groups" in params:
            kwargs["rule_groups"] = []      # ★ 空列表 = 不套用用户的搜索过滤规则
        if "cache_local" in params:
            kwargs["cache_local"] = False
        res = fn(keyword, **kwargs) or []
        out: List[Any] = []
        for ctx in res:
            ti = getattr(ctx, "torrent_info", None)
            if ti is not None:
                out.append(ti)
        return out

    def _crossseed_search_rows(self, keyword: str, site_ids: List[int]) -> List[Any]:
        """用 **MoviePilot 自带搜索**跨站找候选（`SearchChain.search_by_title`）。

        一次调用覆盖多个站；返回的 `torrent_info` 天然带
        `downloadvolumefactor`(免不免费) / `seeders`(有没有源) / `freedate` / `enclosure` / cookie
        —— 免不免费不用再单独查。这里只保留「**免费且在做种**」的行。
        带 6h 缓存；按站计 PV（搜 N 个站 = N PV）。
        """
        kw = str(keyword or "").strip()
        ids: List[int] = []
        for x in site_ids or []:
            try:
                _i = int(x)
            except Exception:  # noqa: BLE001
                continue
            if _i and _i not in ids:
                ids.append(_i)
        if not kw or not ids:
            return []
        cache = self._crossseed_cache()
        ckey = f"mpsearch|{kw}|{','.join(str(i) for i in sorted(ids))}"
        hit = cache.get(ckey, CROSSSEED_CACHE_TTL)
        if hit is not None:
            return [SimpleNamespace(**dict(r)) for r in hit]
        with self._crossseed_lock():
            hit = cache.get(ckey, CROSSSEED_CACHE_TTL)
            if hit is not None:
                return [SimpleNamespace(**dict(r)) for r in hit]
            allowed = [
                i for i in ids
                if not self._pv_block_reason(i) and self._pv_allow(i, "crossseed", want=1)
            ]
            if not allowed:
                self._log("跨站:所有候选源站 PV 预算不足/已封,跳过检索", "warning")
                return []
            hits: List[Any] = []
            try:
                hits = self._mp_search_title(kw, allowed)
            except Exception as err:  # noqa: BLE001
                self._log(f"跨站:MP 搜索失败:{err}", "warning")
                hits = []
            finally:
                for i in allowed:
                    self._pv_spend(i, "crossseed", 1)
            rows: List[Dict[str, Any]] = []
            for ti in hits:
                _dv = getattr(ti, "downloadvolumefactor", None)
                try:
                    dv = 1.0 if _dv is None else float(_dv)
                except Exception:  # noqa: BLE001
                    dv = 1.0
                if dv > 0.0:
                    continue          # 不免费 → 下了就烧流量，跨站的意义就没了
                try:
                    seeders = int(getattr(ti, "seeders", 0) or 0)
                except Exception:  # noqa: BLE001
                    seeders = 0
                if seeders <= 0:
                    continue          # 没源 → 拿不下来
                url = str(getattr(ti, "enclosure", "") or "")
                if not url:
                    continue
                rows.append({
                    "title": str(getattr(ti, "title", "") or ""),
                    "size": float(getattr(ti, "size", 0.0) or 0.0),
                    "seeders": seeders,
                    "peers": int(getattr(ti, "peers", 0) or 0),
                    "enclosure": url,
                    "page_url": str(getattr(ti, "page_url", "") or ""),
                    "site": int(getattr(ti, "site", 0) or 0),
                    "site_name": str(getattr(ti, "site_name", "") or ""),
                    "site_cookie": getattr(ti, "site_cookie", None),
                    "site_ua": getattr(ti, "site_ua", None),
                    "site_proxy": bool(getattr(ti, "site_proxy", False)),
                    "downloadvolumefactor": dv,
                    "uploadvolumefactor": float(getattr(ti, "uploadvolumefactor", 1.0) or 1.0),
                    "freedate": str(getattr(ti, "freedate", "") or ""),
                    "hit_and_run": bool(getattr(ti, "hit_and_run", False)),
                })
            if rows:
                cache.set(ckey, rows, CROSSSEED_CACHE_TTL)
            self._log(
                f"跨站:MP 搜索「{kw}」{len(allowed)} 站 → 免费且有源 {len(rows)} 条"
            )
            return [SimpleNamespace(**dict(r)) for r in rows]

    def _crossseed_torrent_bytes(self, row: Any) -> Optional[bytes]:
        """取候选行的 .torrent 字节（用于特征码校验）——走 PV 闸门与原子记账。"""
        sid = int(getattr(row, "site", 0) or 0)
        url = str(getattr(row, "enclosure", "") or "")
        if not url:
            return None
        if sid and (self._pv_block_reason(sid) or not self._pv_allow(sid, "crossseed", want=1)):
            self._log(f"跨站:站点 {sid} PV 预算不足/已封,放弃取种 {url[:80]}", "warning")
            return None
        downloader = self._get_downloader(getattr(self, "_crossseed_downloader", "") or "qbittorrent")
        if downloader is None or not downloader.is_available:
            return None
        try:
            return downloader.fetch_torrent_bytes(
                url,
                cookie=getattr(row, "site_cookie", None),
                user_agent=getattr(row, "site_ua", None),
                referer=getattr(row, "page_url", "") or None,
            )
        finally:
            if sid:
                self._pv_spend(sid, "crossseed", 1)

    def _crossseed_order(self, task: MagicFlowTaskConfig, cand_hash: str) -> List[str]:
        """优先域名列表：IYUU 反查「该资源确实存在的站」（省 PV）；没有就返回空。"""
        if not (self._iyuu_enabled() and cand_hash):
            return []
        try:
            table = self._iyuu_client.sites() or {}
            sid2base: Dict[str, str] = {}
            for meta in table.values():
                base = str((meta or {}).get("base_url") or "").strip().lower()
                sid = str((meta or {}).get("id") or "")
                if base and sid:
                    sid2base[sid] = base
            rows = (self._iyuu_client.query([cand_hash]) or {}).get(str(cand_hash).lower()) or []
            out: List[str] = []
            for row in rows:
                base = sid2base.get(str((row or {}).get("sid") or ""))
                if base and base not in out:
                    out.append(base)
            return out
        except Exception as err:  # noqa: BLE001
            self._log(f"跨站:IYUU 反查失败:{err}", "warning")
        return []

    def _crossseed_site_ids(self, task: MagicFlowTaskConfig, cand_hash: str = "") -> List[int]:
        """候选源站 id 列表（**不含目标站自己**）。IYUU 开着就只留「确实有这资源」的站。"""
        try:
            from app.db.oper.site import SiteOper  # noqa: WPS433

            sites = list(SiteOper().list() or [])
        except Exception as err:  # noqa: BLE001
            self._log(f"跨站:列出站点失败:{err}", "warning")
            return []
        a_id = int(getattr(task, "site_id", 0) or 0)
        a_dom = str(getattr(task, "site_domain", "") or "").strip().lower()
        _banned = set(self._cs_ban_map().keys())        # ★ 被流量兜底拉黑的站不再作为来源
        pool: List[int] = []
        dom_by_id: Dict[int, str] = {}
        for site in sites:
            sid = int(getattr(site, "id", 0) or 0)
            dom = str(getattr(site, "domain", "") or "").strip().lower()
            if not sid or sid == a_id or (a_dom and dom == a_dom):
                continue          # 目标站自己不能当源（不然还是在 A 下）
            if dom and dom in _banned:
                continue          # 已被流量兜底拉黑
            if getattr(site, "is_active", True) is False:
                continue
            pool.append(sid)
            dom_by_id[sid] = dom
        if not pool:
            return []
        pref = [d for d in self._crossseed_order(task, cand_hash) if d]
        if not pref:
            return pool
        narrowed: List[int] = []
        for sid in pool:
            dom = dom_by_id.get(sid, "")
            for base in pref:
                if base == dom or (dom and base.endswith("." + dom)) or dom.endswith("." + base):
                    narrowed.append(sid)
                    break
        return narrowed or pool

    def _crossseed_find(
        self, task: MagicFlowTaskConfig, cand: Any, downloader: DownloaderAdapter
    ) -> Optional[Dict[str, Any]]:
        """为「本站不免费的候选」找一个他站的免费同 Release 源。

        路径：MP 搜索（一次搜多站，自带免不免费/有源信息）→ 标题+体积预筛
        → 取他站 .torrent 用**完整特征码**定论。
        """
        raw = getattr(cand, "raw", None)
        if not raw:
            return None
        try:
            fp = fingerprint(raw)
        except Exception:  # noqa: BLE001
            fp = None
        if not fp:
            return None
        kw = search_key(str(getattr(cand, "title", "") or ""))
        if not kw:
            return None
        limit_sites = max(int(getattr(task, "crossseed_max_sites", 6) or 6), 1)
        ids = self._crossseed_site_ids(
            task, str(getattr(cand, "real_hash", "") or "")
        )[:limit_sites]
        if not ids:
            self._log("跨站:没有可用的候选源站", "warning")
            return None
        self._crossseed_downloader = str(getattr(task, "downloader", "") or "qbittorrent")
        return pick_source(
            title=getattr(cand, "title", ""),
            size_bytes=int(getattr(cand, "size", 0) or 0),
            fp=fp,
            rows_provider=lambda _kw: self._crossseed_search_rows(_kw, ids),
            torrent_bytes=self._crossseed_torrent_bytes,
            log=self._log,
        )

    def _crossseed_round(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        pool: List[Any],
        limit: int,
    ) -> List[Tuple[str, str, float]]:
        """把「仅因非免费被洗掉」的候选拿去跨站取种（独立小相位，**绝不从本站下**）。

        每个候选要在本站取一次 `.torrent`（1 PV）才能拿到特征码，再让他站免费取种；
        没命中就进 dead 冷却（6h），不会每轮反复取种。

        Returns: 已发起跨站的 `[(他站 hash, 标题, 体积GB), ...]`。
        """
        started: List[Tuple[str, str, float]] = []
        if not pool or limit <= 0:
            return started
        scanned = 0
        sid = int(getattr(task, "site_id", 0) or 0)
        dom = str(getattr(task, "site_domain", "") or "")
        max_size = float(getattr(task, "crossseed_max_size_gb", 20.0) or 20.0)
        seen_cd = float(getattr(task, "seen_cooldown_hours", 0) or 0) * 3600
        for cand in list(pool):
            if len(started) >= limit or scanned >= CROSSSEED_EXTRA_SCAN:
                break
            size_gb = float(getattr(cand, "size_gb", 0.0) or 0.0)
            if size_gb > max_size:
                continue
            ckey = self._candidate_key(cand)
            if ckey and self._store:
                if self._store.seen.is_seen(task.id, f"cand:{ckey}", seen_cd):
                    continue
                if self._store.dead.is_dead(task.id, f"cand:{ckey}", self._dead_cooldown):
                    continue
            url = str(getattr(cand, "enclosure", "") or "")
            if not url:
                continue
            # ★ 本站取一次 .torrent（1 PV）→ 拿特征码（判「同一 Release」的硬标准）
            if sid and (self._pv_block_reason(sid) or not self._pv_allow(sid, "crossseed", want=1)):
                self._log(f"跨站:{dom} PV 预算不足/已封,本轮不再跨站取种", "warning")
                break
            scanned += 1
            raw = None
            try:
                raw = downloader.fetch_torrent_bytes(
                    url,
                    cookie=getattr(cand, "site_cookie", None),
                    user_agent=getattr(cand, "site_ua", None),
                    referer=str(getattr(cand, "page_url", "") or "") or None,
                )
            except Exception as err:  # noqa: BLE001
                self._dbg(f"跨站:本站取种失败 {url[:80]}: {err}")
            finally:
                if sid:
                    self._pv_spend(sid, "crossseed", 1)
            if not raw:
                if ckey and self._store:
                    self._store.dead.mark(task.id, [f"cand:{ckey}"])
                continue
            cand.raw = raw
            try:
                cand.real_hash = (info_hash(raw) or "").lower()
            except Exception:  # noqa: BLE001
                cand.real_hash = ""
            sib: Optional[str] = None
            try:
                # 契约②：只走取种统一入口
                sib = (self._acquire_source(
                    task, cand, downloader, allow_cross_site=True,
                ).get("sib_hash") or None)
            except Exception as err:  # noqa: BLE001
                self._log(f"跨站:取种异常:{getattr(cand, 'title', '')}({err})", "warning")
            if sib:
                started.append((str(sib), str(getattr(cand, "title", "") or ""), size_gb))
                if self._store:
                    keys = [f"hash:{sib}"]
                    if ckey:
                        keys.append(f"cand:{ckey}")
                    self._store.seen.mark(task.id, keys)
            elif ckey and self._store:
                self._store.dead.mark(task.id, [f"cand:{ckey}"])
        if started:
            self._log(
                f"魔流 [{task.name}] 跨站免费取种:本轮发起 {len(started)} 个（探测 {scanned} 个候选）"
            )
        return started

    # ---------------------------------------------------------- 跨站:流量兜底 / 黑名单

    def _site_id_by_domain(self, domain: str) -> int:
        """域名 → MoviePilot 站点 id（用于取该站实时数据 / 正在下载列表）。"""
        dom = str(domain or "").strip().lower()
        if not dom:
            return 0
        cache = getattr(self, "_dom2sid", None)
        if cache is None:
            cache = self._dom2sid = {}
        if dom in cache:
            return int(cache[dom] or 0)
        sid = 0
        try:
            from app.db.oper.site import SiteOper  # noqa: WPS433

            for site in (SiteOper().list() or []):
                d = str(getattr(site, "domain", "") or "").strip().lower()
                if not d:
                    continue
                cache[d] = int(getattr(site, "id", 0) or 0)
                if d == dom:
                    sid = int(getattr(site, "id", 0) or 0)
        except Exception as err:  # noqa: BLE001
            self._log(f"跨站:站点域名表构建失败:{err}", "warning")
            return 0
        return sid

    def _cs_ban_map(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = self.get_data("crossseed_ban") or {}
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def _cs_ban_add(self, domain: str, reason: str) -> None:
        dom = str(domain or "").strip().lower()
        if not dom:
            return
        data = self._cs_ban_map()
        data[dom] = {"ts": time.time(), "reason": str(reason or "")[:200]}
        try:
            self.save_data(key="crossseed_ban", value=data)
        except Exception as err:  # noqa: BLE001
            self._log(f"跨站:黑名单写入失败:{err}", "error")

    def _cs_ban_clear(self, domain: str = "") -> int:
        dom = str(domain or "").strip().lower()
        data = self._cs_ban_map()
        if dom:
            n = 1 if data.pop(dom, None) is not None else 0
        else:
            n = len(data)
            data = {}
        try:
            self.save_data(key="crossseed_ban", value=data)
        except Exception as err:  # noqa: BLE001
            self._log(f"跨站:黑名单清理失败:{err}", "error")
        return n

    def _crossseed_protect_source(self, sib_hash: str, rec: Dict[str, Any], a_hash: str = "") -> None:
        """把来源份移交到「H&R 保护」账本。

        它已经**不归任何任务管**——若放任不管，来源站的同站纳管逻辑会抢走它的标签（实测
        ``SET tags=['魔流-财神']``），任务清理再把它带上文件一起删 → 既踩来源站 H&R，
        又可能连累目标站正在做种的同一批文件。
        """
        h = str(sib_hash or "").lower()
        if not h:
            return
        dom = str(rec.get("site_b_domain") or "").strip().lower()
        # ★ 该种无 H&R 义务（种子未标 + 站点库说无 H&R）→ 不登记保护账本，免费做种随便清
        if rec.get("hit_and_run") is False and self._site_hr_flag(dom) is False:
            self._log(
                f"跨站:{rec.get('site_b', '') or dom} 该种无 H&R 义务 → 不登记保种账本",
                "info",
            )
            self._crossseed_sources().drop(h)
            return
        try:
            hours = float(rec.get("seed_hours") or 0.0)
        except (TypeError, ValueError):
            hours = 0.0
        if hours <= 0:
            hours, _src = self._crossseed_seed_hours_detail(dom)
        else:
            _src = str(rec.get("seed_hours_src") or "")
        try:
            until = float(rec.get("seed_until") or 0.0) or (time.time() + hours * 3600.0)
        except (TypeError, ValueError):
            until = time.time() + hours * 3600.0
        self._crossseed_sources().add({
            "sib_hash": h,
            "resource_id": str(rec.get("resource_id") or ""),
            "title": str(rec.get("title") or ""),
            "size_gb": float(rec.get("size_gb") or 0.0),
            "site_a": str(rec.get("site_a") or ""),
            "site_b": str(rec.get("site_b") or ""),
            "site_b_domain": dom,
            "a_hash": str(a_hash or rec.get("a_hash") or "").lower(),
            "hit_and_run": bool(rec.get("hit_and_run")),
            "hours": hours,
            "hours_src": _src,
            "need_hours": float(rec.get("need_hours") or 0.0),
            "created": float(rec.get("created") or time.time()),
            "seed_until": until,
            "downloader": str(rec.get("downloader") or "qbittorrent"),
            "files_shared": bool(a_hash),
            "task_id": str(rec.get("task_id") or ""),
            "task_name": str(rec.get("task_name") or ""),
        })
        self._log(
            f"跨站:H&R 保护 {rec.get('site_b', '') or dom} 「{str(rec.get('title') or '')[:50]}」"
            f" → 保种至 {time.strftime('%m-%d %H:%M', time.localtime(until))}（{hours:g}h，期内任何任务不得删/改）"
        )

    def _crossseed_guard(self) -> Dict[str, Any]:
        """★ 兄弟站流量兜底：跨站取种期间核对来源站「是否真免费」。

        判「免费」可能错（解析错 / 促销变了）→ 一旦错了就是白烧兄弟站流量。
        两重核对（任一命中即止损）：
          ① 来源站「正在下载」列表里，我们这个种子**不免费**；
          ② 来源站**下载量增量** > 目标体积 × 阈值百分比。
        止损：立即从下载器删除该跨站种（含文件）+ 拉黑来源站 + 通知。
        """
        if not self._promo_guard_on():
            return {"ok": False, "skipped": "流量兜底总开关已关", "killed": [], "banned": []}
        out: Dict[str, Any] = {"enabled": False, "checked_sites": [], "violations": [], "errors": []}
        _by_task: Dict[str, List[Any]] = {}
        cfg = getattr(self, "_cs_cfg", {}) or {}
        # ★ H&R：来源份的保种监督（标签确权 / 清无效 / 到期回收 / 历史回填）
        #   必须**先**跑：它跟「有没有待回辅」无关，guard 关闭时也要维护。
        try:
            out.update(self._crossseed_sources_tick())
        except Exception as err:  # noqa: BLE001
            out["errors"].append(f"H&R 保护核对异常:{err}")
        if not bool(cfg.get("guard", True)):
            return out
        out["enabled"] = True
        pend = self._crossseed_pending()
        items = pend.items()
        if not items:
            return out
        by_site: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for h, rec in items.items():
            dom = str(rec.get("site_b_domain") or "").strip().lower()
            by_site.setdefault(dom, []).append((h, rec))
        interval = max(60.0, float(cfg.get("guard_interval_min") or 15.0) * 60.0)
        now = time.time()
        guard_at = getattr(self, "_cs_guard_at", None)
        if guard_at is None:
            guard_at = self._cs_guard_at = {}
        dl_cache: Dict[str, Any] = {}
        for dom, group in by_site.items():
            if dom and now - float(guard_at.get(dom, 0) or 0) < interval:
                continue
            if dom:
                guard_at[dom] = now
            sid = self._site_id_by_domain(dom) if dom else 0
            site_name = str(group[0][1].get("site_b") or dom or "")
            entry: Dict[str, Any] = {
                "site": site_name, "domain": dom, "site_id": sid, "inflight": len(group),
                "delta_gb": None, "threshold_gb": None, "status": "",
            }
            out["checked_sites"].append(entry)
            if not sid:
                entry["status"] = "无法核对(MP 里未配置该站)"
                continue
            # ② 下载量增量（取种时记的基线）
            cur_dl: Optional[float] = None
            try:
                if getattr(self, "_live", None) is not None:
                    live = self._live.get(int(sid))
                    if isinstance(live, dict) and live.get("ok") and live.get("download") is not None:
                        cur_dl = float(live.get("download") or 0.0)
            except Exception:  # noqa: BLE001
                cur_dl = None
            # ① 来源站「正在下载」列表里的免费标记
            leech: Dict[str, Any] = {}
            try:
                if getattr(self, "_live", None) is not None:
                    leech = self._live.leeching(int(sid)) or {}
            except Exception as err:  # noqa: BLE001
                out["errors"].append(f"{site_name}:取正在下载列表失败:{err}")
                leech = {}
            rows = list((leech or {}).get("rows") or [])
            victims: List[Tuple[str, Dict[str, Any], str]] = []
            for h, rec in group:
                title = str(rec.get("title") or "")
                try:
                    size_gb = float(rec.get("size_gb") or 0.0)
                except (TypeError, ValueError):
                    size_gb = 0.0
                reason = ""
                for row in rows:
                    rn = str(row.get("name") or "")
                    if not rn or not title or not title_match(rn, title):
                        continue
                    try:
                        rs = float(row.get("size") or 0) / (1024 ** 3)
                    except (TypeError, ValueError):
                        rs = 0.0
                    if size_gb > 0 and rs > 0 and abs(rs - size_gb) / max(rs, 0.001) > 0.05:
                        continue
                    if not bool(row.get("free")):
                        reason = "来源站列表显示该种其实**不免费**（会烧下载量）"
                    break
                if not reason and cur_dl is not None:
                    try:
                        base = float(rec.get("base_dl") or 0.0)
                    except (TypeError, ValueError):
                        base = 0.0
                    delta_gb = cur_dl - base
                    thr = max(
                        size_gb * float(cfg.get("guard_pct") or 5.0) / 100.0,
                        float(cfg.get("guard_min_mb") or 50.0) / 1024.0,
                    )
                    entry["delta_gb"] = round(delta_gb, 4)
                    entry["threshold_gb"] = round(thr, 4)
                    if base > 0 and delta_gb > thr:
                        reason = f"来源站下载量增长 {delta_gb:.2f}GB（超阈值 {thr:.2f}GB）"
                if reason:
                    victims.append((h, rec, reason))
            if not victims:
                entry["status"] = "正常(免费)"
                continue
            entry["status"] = f"异常 → 已止损 {len(victims)} 个"
            dl_name = str(victims[0][1].get("downloader") or "qbittorrent")
            downloader = dl_cache.get(dl_name)
            if downloader is None:
                downloader = self._get_downloader(dl_name)
                dl_cache[dl_name] = downloader
            for h, rec, reason in victims:
                if downloader is not None and getattr(downloader, "is_available", False):
                    try:
                        _no, err = downloader.delete_torrents(hashes=[h], delete_file=True)
                        if err:
                            out["errors"].append(f"{site_name}:删种失败:{err}")
                    except Exception as err:  # noqa: BLE001
                        out["errors"].append(f"{site_name}:删种异常:{err}")
                pend.drop(h)
                pend.cleanup_torrent(str(rec.get("a_torrent") or ""))
                if dom:
                    self._cs_ban_add(dom, reason)
                try:
                    _sz = float(rec.get("size_gb") or 0.0)
                except (TypeError, ValueError):
                    _sz = 0.0
                _by_task.setdefault(str(rec.get("task_id") or SILENT_HOST_TASK_ID), []).append(OperationItem(
                    hash=h,
                    title=str(rec.get("title") or ""),
                    reason=f"跨站兜底止损[{rec.get('site_b', '') or dom}]：{reason}（连文件删除；文件被共用时自动降级为只删种）",
                    size_gb=round(_sz, 3),
                    source="crossseed",
                ))
                out["violations"].append({
                    "hash": h, "title": rec.get("title", ""), "site_b": rec.get("site_b", ""),
                    "domain": dom, "size_gb": rec.get("size_gb", 0), "reason": reason,
                })
                self._log(
                    f"跨站兜底 [{site_name}] 「{str(rec.get('title') or '')[:60]}」{reason}"
                    f" → 已删除跨站种并拉黑该站（需人工确认后解除）",
                    "error",
                )
            try:
                names = "、".join(str(v.get("site_b") or "") for v in out["violations"][:3])
                self.post_message(
                    title="【魔流】跨站取种被流量兜底拦截",
                    text=(
                        f"判定「免费」但实际产生了下载流量：{names}\n"
                        "已删除跨站种并拉黑该来源站，请到工作台「跨站」页确认后解除。"
                    ),
                )
            except Exception:  # noqa: BLE001
                pass
        self._journal_deletions(_by_task, log_prefix="跨站兜底止损")
        return out

    def _crossseed_to_silent(self, h: str, rec: Dict[str, Any], info: Any,
                             downloader: Any) -> bool:
        """★ 跨站来源份**下完** → 转入静默池（Master 2026-09-28）。

        Master：「跨站来的下完直接静默池挂 h&r，跨站下载进跨站池」。
        即：**未下完的**留在跨站池（跨站面板/队列）；**下完的**进静默池，由静默池负责
        继续挂种、结 H&R 义务、期满后走静默分拣（推荐 / 普通 / 资源）。
        """
        hh = str(h or "").strip().lower()
        if not hh or downloader is None:
            return False
        try:
            ts = self._tag_state()
            cur = ts.get(hh) or {}
        except Exception:  # noqa: BLE001
            cur = {}
        # 已有「资源」身份（库内资产/辅种）→ 保留资源子类，只做「入静默池」这件事
        _sub = SUB_RESOURCE if (str(cur.get("sub") or "") == SUB_RESOURCE
                                or bool(cur.get("asset"))) else SUB_NEW
        #（已在静默池的判定见下方：账本 + 标签双就位才算）
        tags = getattr(info, "tags", None) or []
        if isinstance(tags, str):
            tags = [x.strip() for x in tags.split(",") if x.strip()]
        cur_tags = [str(x).strip() for x in tags]
        site = str(rec.get("site_b") or "").strip()
        if not site:
            site, _dom = self._guess_site_of_torrent(cur_tags, rec.get("title"))
        if (str(cur.get("state") or "") == STATE_SILENT
                and str(cur.get("sub") or "") == _sub):
            return False  # 已在静默池（账本已就位；标签只作投影，不看）
        # 保留非魔流标签（站点名/已整理/辅种/其它插件），去掉旧的任务态标签
        keep = [t for t in cur_tags
                if t and t not in SPECIAL_TAGS and not is_magicflow_tag(t)]
        want = keep + [CROSSSEED_TAG]
        if site:
            want.append(tag_for(site, STATE_SILENT, _sub))
        final: List[str] = []
        for t in want:
            if t not in final:
                final.append(t)
        ok = False
        try:
            fn = getattr(downloader, "replace_torrent_tags", None)
            ok = bool(fn(hh, final)) if callable(fn) else False
        except Exception as err:  # noqa: BLE001
            self._log(f"跨站:来源份入静默池打标失败 {hh[:12]}:{err}", "warning")
            ok = False
        if not ok:
            return False
        now = time.time()
        try:
            ts.put(hh, {
                "site": site, "state": STATE_SILENT, "sub": _sub,
                "title": str(rec.get("title") or getattr(info, "title", "") or ""),
                "size_gb": float(rec.get("size_gb") or getattr(info, "size_gb", 0) or 0.0),
                "downloader": str(rec.get("downloader") or "qbittorrent"),
                "taken_by": "", "lease_until": 0,
                "crossseed": True, "ts": now,
                "reason": "跨站来源份下完→静默池挂H&R",
            })
            try:
                self._crossseed_sources().put(hh, {"pool": "silent"})
            except Exception:  # noqa: BLE001
                pass
        except Exception as err:  # noqa: BLE001
            self._dbg(f"跨站:来源份入静默池记账失败:{err}")
        # 必须在挂种（静默池要它继续挂满 H&R）
        try:
            if "pause" in str(getattr(info, "state", "") or "").lower():
                downloader.resume_torrents([hh])
        except Exception as err:  # noqa: BLE001
            self._dbg(f"跨站:来源份恢复做种失败:{err}")
        self._log(
            f"跨站:来源份已下完 → 进静默池挂 H&R（{site or '未知站'}）"
            f"「{str(rec.get('title') or '')[:40]}」"
        )
        return True

    def _crossseed_sources_tick(self) -> Dict[str, Any]:
        """来源份保种监督：① 标签确权 ② 清掉已消失的 ③ 到期回收(可选)。

        来源份不归任何任务管——不理它，来源站的同站纳管就会抢走它的标签，
        任务清理再把它连文件一起删 → 既踩来源站 H&R，又可能连累目标站正在做种的同一批文件。
        """
        store = self._crossseed_sources()
        items = store.items()
        res: Dict[str, Any] = {"protected": len(items), "retagged": 0, "reclaimed": 0}
        if not items:
            # 账本为空时也要跑「历史回填」（升级前的遗留来源份），否则它们永远没人保护
            try:
                res["backfilled"] = self._crossseed_sources_backfill()
            except Exception:  # noqa: BLE001
                pass
            res["protected"] = len(store.items())
            return res
        dl_cache: Dict[str, Any] = {}
        now = time.time()
        live: Set[str] = set()
        reclaim = bool((getattr(self, "_cs_cfg", {}) or {}).get("reclaim", False))
        for h, rec in list(items.items()):
            dl_name = str(rec.get("downloader") or "qbittorrent")
            downloader = dl_cache.get(dl_name)
            if downloader is None:
                downloader = self._get_downloader(dl_name)
                dl_cache[dl_name] = downloader
            if downloader is None or not getattr(downloader, "is_available", False):
                live.add(h)
                continue
            info = downloader.get_torrent_info(h)
            if info is None:
                continue  # 已不在下载器（手动删了？）→ 交给 prune
            live.add(h)
            # ★ 下完 → 转静默池（未下完的留在跨站池）
            try:
                _prog = float(getattr(info, "progress", 0) or 0)
            except (TypeError, ValueError):
                _prog = 0.0
            if _prog >= 0.999:
                try:
                    if self._crossseed_to_silent(h, rec, info, downloader):
                        res["to_silent"] = int(res.get("to_silent") or 0) + 1
                except Exception as err:  # noqa: BLE001
                    res.setdefault("errors", []).append(f"跨站来源份入静默池失败:{err}")
            # ★ ② 实际做种时长（qB seeding_time）：达标线一到 = H&R 义务完成 → 可撤种
            #   （Master：连挂挂满就行 —— 用真实做种秒数判，不看墙钟）
            try:
                seeded = float(getattr(info, "seed_time", 0) or 0.0)
            except (TypeError, ValueError):
                seeded = 0.0
            try:
                need = float(rec.get("need_hours") or 0.0)
            except (TypeError, ValueError):
                need = 0.0
            done = bool(rec.get("done"))
            if seeded > float(rec.get("seeded_sec") or 0.0) + 1.0 or (need and not done):
                store.put(h, {"seeded_sec": seeded})
                rec["seeded_sec"] = seeded
                try:
                    self._tag_groups().note_hr_progress(
                        self._resource_gid(rec.get("title"), rec.get("size_gb")), seeded_seconds=seeded
                    )
                except Exception:  # noqa: BLE001
                    pass
            if need > 0 and seeded >= need * 3600.0 and not done:
                store.put(h, {"done": True, "done_ts": now, "seeded_sec": seeded})
                rec["done"] = True
                res["completed"] = int(res.get("completed") or 0) + 1
                # ★ 挂够时长 = 来源站种子的义务还完 → 给「资源」结清 H&R 账单
                try:
                    _gid = self._resource_gid(rec.get("title"), rec.get("size_gb"))
                    hr = self._tag_groups().note_hr_progress(_gid, seeded_seconds=seeded)
                    if hr.get("settled"):
                        self._log(f"资源:H&R 账单已结清 —— 资源「{str(rec.get('title') or '')[:50]}」"
                                  f"（来源站 {hr.get('site') or rec.get('site_b', '')} 已挂 {seeded / 3600.0:.1f}h）")
                except Exception as err:  # noqa: BLE001
                    self._log(f"资源:H&R 结清记录失败:{err}", "warning")
                self._log(
                    f"跨站:H&R 义务完成 —— {rec.get('site_b', '') or rec.get('site_b_domain', '')} "
                    f"「{str(rec.get('title') or '')[:50]}」已实际做种 {seeded / 3600.0:.1f}h ≥ {need:g}h，可撤种"
                )
                if reclaim and str(rec.get("pool") or "") != "silent":
                    try:
                        _n, err = downloader.delete_torrents(hashes=[h], delete_file=False)
                        if not err:
                            store.drop(h)
                            res["reclaimed"] = int(res.get("reclaimed") or 0) + 1
                            self._journal_deletions({str(rec.get("task_id") or SILENT_HOST_TASK_ID): [
                                OperationItem(
                                    hash=h, title=str(rec.get("title") or ""),
                                    reason=(f"H&R 义务已完成（做种 {seeded / 3600.0:.1f}h ≥ {need:g}h）"
                                            "→ 回收来源份（只删种子不删文件）"),
                                    size_gb=float(rec.get("size_gb") or 0.0),
                                    source="crossseed",
                                )]}, log_prefix="跨站回收")
                    except Exception as rerr:  # noqa: BLE001
                        res.setdefault("errors", []).append(f"回收失败:{rerr}")
                    continue
            if rec.get("done"):
                continue  # 已履行义务 → 不再保护、不再强制标签
            # ① 标签确权：来源份只属于「魔流-跨站」，被任务抢走就改回来
            tags = list(getattr(info, "tags", None) or [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            if CROSSSEED_TAG not in tags:
                try:
                    if downloader.set_torrent_tags(h, [CROSSSEED_TAG]):
                        res["retagged"] += 1
                        self._dbg(f"跨站:来源份标签确权 {h[:12]} → {CROSSSEED_TAG}")
                except Exception:  # noqa: BLE001
                    pass
            # ③ 到期回收（默认关）：只删种子、不删文件（A 端还在用同一批文件）
            try:
                until = float(rec.get("seed_until") or 0.0)
            except (TypeError, ValueError):
                until = 0.0
            if (until and now >= until and reclaim
                    and str(rec.get("pool") or "") != "silent"
                    and not bool(rec.get("files_shared"))):
                try:
                    _n, err = downloader.delete_torrents(hashes=[h], delete_file=False)
                    if not err:
                        store.drop(h)
                        res["reclaimed"] += 1
                        self._journal_deletions({str(rec.get("task_id") or SILENT_HOST_TASK_ID): [
                            OperationItem(
                                hash=h, title=str(rec.get("title") or ""),
                                reason="跨站保种期满 → 回收来源份（只删种子不删文件）",
                                size_gb=float(rec.get("size_gb") or 0.0),
                                source="crossseed",
                            )]}, log_prefix="跨站回收")
                        self._log(
                            "跨站:H&R 保种期满，回收来源份（只删种子不删文件）:"
                            f"{str(rec.get('title') or '')[:50]}"
                        )
                except Exception as rerr:  # noqa: BLE001
                    res.setdefault("errors", []).append(f"回收失败:{rerr}")
        dead = store.prune(live)
        if dead:
            self._dbg(f"跨站:清理已消失的来源份保护记录 {len(dead)} 条")
        # ★ 自愈回填：下载器里带「魔流-跨站」标签、但账本里没有的种（升级前的遗留 / 账本丢了）
        #   → 按默认保种时长登记保护，避免被来源站的任务顺手删掉。
        try:
            res["backfilled"] = self._crossseed_sources_backfill()
        except Exception:  # noqa: BLE001
            pass
        res["protected"] = len(store.items())
        return res

    def _guess_site_of_torrent(self, tags: Any, title: Any = "") -> Tuple[str, str]:
        """从种子的标签 / 标题后缀（``@HDFans``、``-WGXC@HDFans``）猜它的站点（名, 域名）。"""
        try:
            sites = self._list_sites() or []
        except Exception:  # noqa: BLE001
            sites = []
        site = self._torrent_site_name(tags) or ""
        if site:
            for it in sites:
                if str(it.get("name") or "") == site:
                    return site, str(it.get("domain") or "")
            return site, ""
        m = re.search(r"@\s*([A-Za-z0-9_.-]{2,30})\s*$", str(title or "").strip())
        tail = m.group(1).lower() if m else ""
        for it in sites:
            nm = str(it.get("name") or "")
            dom = str(it.get("domain") or "")
            if tail and (tail in dom.lower() or tail in nm.lower().replace(" ", "")):
                return nm, dom
        return (tail, "") if tail else ("", "")

    def _crossseed_sources_backfill(self) -> int:
        """把「下载器里有 魔流-跨站 标签、账本里没有」的种回填进 H&R 保护账本。"""
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return 0
        groups, err = downloader.get_torrents_by_tag()
        if err and not groups:
            return 0
        tagged = list((groups or {}).get(CROSSSEED_TAG, []) or [])
        if not tagged:
            return 0
        store = self._crossseed_sources()
        known = store.hashes() | set(self._crossseed_pending().items().keys())
        hours = self._crossseed_seed_hours("")
        now = time.time()
        added = 0
        for t in tagged:
            h = str(getattr(t, "hash", "") or "").lower()
            if not h or h in known:
                continue
            _tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            _title = str(getattr(t, "title", "") or getattr(t, "name", "") or "")
            # ★ 来源站：老记录可能是空的 → 用种子标签/标题里的站点信息补上（H&R 账单要记在资源上）
            _site, _dom = self._guess_site_of_torrent(_tags, _title)
            store.add({
                "sib_hash": h,
                "title": _title,
                "size_gb": float(getattr(t, "size", 0) or 0) / (1024 ** 3),
                "site_a": "", "site_b": _site, "site_b_domain": _dom,
                "a_hash": "", "hit_and_run": False,
                "hours": hours,
                "created": now,
                "seed_until": now + hours * 3600.0,
                "downloader": "qbittorrent",
                "files_shared": True,   # 来源份文件常与目标站共用 → 回收一律不删文件
                "task_id": "", "task_name": "",
                "backfilled": True,
            })
            added += 1
        if added:
            self._log(f"跨站:H&R 保护回填 {added} 个历史来源份（{hours:g}h）")
        return added

    def _crossseed_start(
        self,
        task: MagicFlowTaskConfig,
        cand: Any,
        downloader: DownloaderAdapter,
    ) -> Optional[str]:
        """发起一次跨站免费取种：在他站下（免费）→ 记账 → 等下载完回辅 A。

        Returns: 成功时返回他站种子 hash。
        """
        src = self._crossseed_find(task, cand, downloader)
        if not src:
            return None
        sib_bytes = src.get("torrent")
        sname = str(src.get("site_name") or src.get("site_domain") or "")
        if not sib_bytes:
            return None
        # ★ 全局（跨任务）资源去重：该兄弟种（同 infohash / 同完整特征码）已被别的任务下过/在飞 → 跳过
        _gkeys = self._dup_keys(info_hash(sib_bytes), fingerprint(sib_bytes))
        if _gkeys and self._dup_claim(task.id, keys=_gkeys):
            self._log(f"跨站:跳过·重复资源（其它任务已下载/在飞）:{cand.title}")
            return None
        hs, err = downloader.add_torrent(
            content=sib_bytes,
            download_dir=task.save_path or "",
            tag=CROSSSEED_TAG,
        )
        if not hs:
            self._log(f"跨站:在他站 {sname} 添加失败:{cand.title}({err or '未知'})", "warning")
            self._dup_release(task.id, keys=_gkeys)
            return None
        self._dup_finish(task.id, keys=_gkeys)
        sib_hash = str(hs).lower()
        a_key = str(getattr(cand, "real_hash", "") or "").lower() or f"sib-{sib_hash}"
        a_path = self._crossseed_pending().put_torrent(a_key, getattr(cand, "raw", b"") or b"")
        # ★ 资源 id（文件特征码）= 辅种流水归组键
        try:
            _fp = fingerprint(getattr(cand, "raw", b"") or b"")
        except Exception:  # noqa: BLE001
            _fp = ""
        # ★ 流量兜底基线：记下来源站此刻的下载量（后结增量超阈值 = 其实不免费）
        _b_dom = str(src.get("site_domain") or "").strip().lower()
        # ★ 种子里有 H&R 信息 → 以种子为准；没有 → 兜底站点规则库（见 _crossseed_hr_decision）
        _t_hr = getattr(src.get("row"), "hit_and_run", None)
        _hr_flag, _hr_use, _hr_origin = self._crossseed_hr_decision(_b_dom, _t_hr)
        _hr_hours, _hr_src = _hr_use, _hr_origin
        if not _hr_flag:
            self._log(
                f"跨站:{sname or _b_dom} 该种无 H&R 义务（{_hr_origin}）→ 不做 H&R 保种保护",
                "info",
            )
        _b_dl = 0.0
        try:
            _b_sid = self._site_id_by_domain(_b_dom)
            if _b_sid and getattr(self, "_live", None) is not None:
                _b_live = self._live.get(int(_b_sid))
                if isinstance(_b_live, dict) and _b_live.get("ok") and _b_live.get("download") is not None:
                    _b_dl = float(_b_live.get("download") or 0.0)
        except Exception:  # noqa: BLE001
            _b_dl = 0.0
        self._crossseed_pending().add({
            "sib_hash": sib_hash,
            "a_hash": str(getattr(cand, "real_hash", "") or "").lower(),
            "resource_id": _fp or "",
            "title": str(getattr(cand, "title", "") or ""),
            "size_gb": float(getattr(cand, "size_gb", 0.0) or 0.0),
            "site_a": str(getattr(task, "site_name", "") or getattr(task, "site_domain", "") or ""),
            "site_b": sname,
            "site_b_domain": _b_dom,
            "base_dl": _b_dl,
            "base_ts": time.time(),
            # ★ H&R：来源站保种义务（种子级标记 > 站点规则库）。取种时就把「保种到什么时候」算好。
            "hit_and_run": bool(_hr_flag),
            "seed_hours": _hr_hours,
            "seed_hours_src": _hr_src,
            # ★ 实际做种达标线（学校 20h）：qB seeding_time 挂够 → 义务完成，可撤种
            "need_hours": self._crossseed_seed_need_hours(_b_dom),
            "seed_until": time.time() + _hr_hours * 3600.0,
            "task_id": str(getattr(task, "id", "") or ""),
            "task_name": str(getattr(task, "name", "") or ""),
            "downloader": str(getattr(task, "downloader", "") or "qbittorrent"),
            "tag": str(getattr(task, "brush_tag", "") or ""),
            "verify": bool(getattr(task, "reuse_verify", True)),
            "save_path": str(task.save_path or ""),
            "a_torrent": a_path,
            "created": time.time(),
        })
        if self._store:
            self._store.journal.record(
                task_id=str(getattr(task, "id", "") or ""),
                kind="reseed",
                items=[OperationItem(
                    hash=sib_hash,
                    title=str(getattr(cand, "title", "") or ""),
                    reason=f"跨站取种:{sname}（免费）→ 待回辅 {task.site_name or task.site_domain}",
                    size_gb=float(getattr(cand, "size_gb", 0.0) or 0.0),
                    source="crossseed",
                )],
            )
        self._log(
            f"跨站取种 [{task.name}] {cand.title} → 从他站 {sname} 免费下载(待下载完回辅)"
        )
        return sib_hash

    def _crossseed_info(self) -> Dict[str, Any]:
        """给接口/日志用的快照。"""
        pend = self._crossseed_pending()
        items = pend.items()
        cfg = getattr(self, "_cs_cfg", {}) or {}
        # 每条：补上「下载器里的实时进度/状态」（前端表格要用）
        dl_cache: Dict[str, Any] = {}
        pending: List[Dict[str, Any]] = []
        now = time.time()
        for k, v in items.items():
            dl_name = str(v.get("downloader") or "qbittorrent")
            progress = None
            state = ""
            try:
                downloader = dl_cache.get(dl_name)
                if downloader is None:
                    downloader = self._get_downloader(dl_name)
                    dl_cache[dl_name] = downloader
                if downloader is not None and getattr(downloader, "is_available", False):
                    info = downloader.get_torrent_info(k)
                    if info is not None:
                        progress = round(float(getattr(info, "progress", 0) or 0), 4)
                        state = str(getattr(info, "state", "") or "")
                        if not v.get("size_gb"):
                            try:
                                v["size_gb"] = float(getattr(info, "size", 0) or 0) / (1024 ** 3)
                            except Exception:  # noqa: BLE001
                                pass
            except Exception:  # noqa: BLE001
                pass
            try:
                base = float(v.get("base_dl") or 0.0)
            except (TypeError, ValueError):
                base = 0.0
            rec = {
                "sib_hash": k,
                "title": v.get("title", ""),
                "site_a": v.get("site_a", ""),
                "site_b": v.get("site_b", ""),
                "site_b_domain": v.get("site_b_domain", ""),
                "size_gb": round(float(v.get("size_gb") or 0.0), 3),
                "task_name": v.get("task_name", ""),
                "progress": progress,
                "state": state,
                "base_dl": base,
                "age_min": round(max(0.0, (now - float(v.get("created") or 0)) / 60.0), 1),
            }
            pending.append(rec)
        pending.sort(key=lambda x: float(x.get("age_min") or 0))
        # ★ 来源份（H&R 保种中）：距保种期满还剩多久
        sources: List[Dict[str, Any]] = []
        try:
            for h, rec in self._crossseed_sources().items().items():
                try:
                    until = float(rec.get("seed_until") or 0.0)
                except (TypeError, ValueError):
                    until = 0.0
                age_min = round(max(0.0, (now - float(rec.get("created") or 0)) / 60.0), 1)
                sources.append({
                    "sib_hash": h,
                    "title": rec.get("title", ""),
                    "site_a": rec.get("site_a", ""),
                    "site_b": rec.get("site_b", ""),
                    "site_b_domain": rec.get("site_b_domain", ""),
                    "size_gb": round(float(rec.get("size_gb") or 0.0), 3),
                    "hours": float(rec.get("hours") or 0.0),
                    "hours_src": str(rec.get("hours_src") or ""),
                    "need_hours": float(rec.get("need_hours") or 0.0),
                    "seeded_h": round(float(rec.get("seeded_sec") or 0.0) / 3600.0, 2),
                    "fulfilled": bool(rec.get("done")),
                    "hit_and_run": bool(rec.get("hit_and_run")),
                    "seed_until": until,
                    "remain_min": round(max(0.0, (until - now) / 60.0), 1),
                    "done": bool(until and now >= until),
                    "files_shared": bool(rec.get("files_shared")),
                    "age_min": age_min,
                    "task_name": rec.get("task_name", ""),
                })
        except Exception:  # noqa: BLE001
            sources = []
        sources.sort(key=lambda x: float(x.get("remain_min") or 0), reverse=True)
        return {
            "enabled_tasks": [
                {"id": t.id, "name": t.name,
                 "max_per_round": getattr(t, "crossseed_max_per_round", 3),
                 "max_size_gb": getattr(t, "crossseed_max_size_gb", 20.0),
                 "max_sites": getattr(t, "crossseed_max_sites", 6)}
                for t in self._task_configs.values()
                if getattr(t, "enabled", False) and getattr(t, "crossseed_enabled", False)
            ],
            "pending": pending,
            "count": len(items),
            "tag": CROSSSEED_TAG,
            # ★ 已回辅完成 / 回辅失败的「来源份」：正在来源站履行 H&R 保种义务
            "sources": sources,
            "sources_count": len(sources),
            # ★ 流量兜底状态（前端「跨站」页展示 / 一键解除拉黑）
            "guard": {
                "enabled": bool(cfg.get("guard", True)),
                "pct": float(cfg.get("guard_pct") or 5.0),
                "min_mb": float(cfg.get("guard_min_mb") or 50.0),
                "interval_min": float(cfg.get("guard_interval_min") or 15.0),
                "keep_seed": bool(cfg.get("keep_seed", True)),
                "seed_hours_default": float(cfg.get("seed_hours_default") or CROSSSEED_SEED_HOURS_DEFAULT),
                "site_hours": [
                    f"{d}={h:g}" for d, h in sorted((cfg.get("site_hours") or {}).items())
                ],
                "reclaim": bool(cfg.get("reclaim", False)),
                "banned": [
                    {"domain": d, "reason": v.get("reason", ""),
                     "age_min": round(max(0.0, (now - float(v.get("ts") or 0)) / 60.0), 1)}
                    for d, v in self._cs_ban_map().items()
                ],
            },
        }

    # ---------------------------------------------------------- 回辅轮询(插件级单 worker)

    def crossseed_scan(self) -> None:
        """跨站回辅轮询：他站下完 → 把目标站的种子指向同一批文件辅种（校验通过才保留）。"""
        pend = self._crossseed_pending()
        dead = pend.prune()
        if dead:
            self._log(f"跨站回辅:清理超时/失效记录 {len(dead)} 条")
        # ★ 流量兜底（先于回辅）：核对来源站「是否真免费」，错了立即止损（删种+拉黑）
        try:
            gres = self._crossseed_guard()
            if gres.get("violations"):
                self._log(
                    f"跨站兜底:本轮拦截 {len(gres['violations'])} 个（来源站判「免费」实际不免费）",
                    "error",
                )
            elif gres.get("enabled") and gres.get("checked_sites"):
                self._dbg(f"跨站兜底:核对 {len(gres['checked_sites'])} 个来源站，均正常")
        except Exception as err:  # noqa: BLE001
            self._log(f"跨站兜底异常:{err}", "warning")
        items = pend.items()
        if not items:
            return
        if not self._acquire_worker_slot("跨站回辅"):
            return
        done = failed = waiting = 0
        try:
            dl_cache: Dict[str, Any] = {}
            for sib_hash, rec in list(items.items()):
                dl_name = str(rec.get("downloader") or "qbittorrent")
                downloader = dl_cache.get(dl_name)
                if downloader is None:
                    downloader = self._get_downloader(dl_name)
                    dl_cache[dl_name] = downloader
                if downloader is None or not downloader.is_available:
                    self._log(f"跨站回辅:下载器 {dl_name} 不可用,本轮跳过", "warning")
                    continue
                info = downloader.get_torrent_info(sib_hash)
                if info is None:
                    # 他站种子没了：超过 6h 视为放弃，删记录（避免无限等）
                    age = time.time() - float(rec.get("created") or 0)
                    if age > 6 * 3600:
                        pend.drop(sib_hash)
                        self._log(f"跨站回辅:他站种子已不存在,删除待回辅记录:{rec.get('title', '')}")
                    else:
                        waiting += 1
                    continue
                state = str(getattr(info, "state", "") or "").lower()
                progress = float(getattr(info, "progress", 0) or 0)
                if state in QB_DOWNLOADING_STATES and progress < 0.999:
                    waiting += 1
                    continue
                if state in (QB_PAUSED_STATES | {"error", "missingfiles"}):
                    if time.time() - float(rec.get("created") or 0) > 6 * 3600:
                        pend.drop(sib_hash)
                        self._log(
                            f"跨站回辅:他站种子停滞/出错({state}),放弃:{rec.get('title', '')}",
                            "warning",
                        )
                    else:
                        waiting += 1
                    continue
                # 已下完 → 回辅目标站
                a_bytes = pend.read_torrent(str(rec.get("a_torrent") or ""))
                if not a_bytes:
                    pend.drop(sib_hash)
                    self._log(f"跨站回辅:目标站种子文件缺失,放弃:{rec.get('title', '')}", "warning")
                    continue
                save_path = str(getattr(info, "save_path", "") or rec.get("save_path") or "")
                hs, err = downloader.add_torrent_reuse(
                    torrent_bytes=a_bytes,
                    save_path=save_path,
                    tag=str(rec.get("tag") or ""),
                    verify=bool(rec.get("verify", True)),
                )
                if hs:
                    done += 1
                    pend.drop(sib_hash)
                    pend.cleanup_torrent(str(rec.get("a_torrent") or ""))
                    self._crossseed_protect_source(sib_hash, rec, a_hash=str(hs).lower())
                    if self._store:
                        self._store.journal.record(
                            task_id=str(rec.get("task_id") or ""),
                            kind="reseed",
                            items=[OperationItem(
                                hash=str(hs).lower(),
                                title=str(rec.get("title") or ""),
                                reason=f"跨站回辅完成：{rec.get('site_b', '')} → {rec.get('site_a', '')}（零下载做种）",
                                size_gb=float(rec.get("size_gb") or 0.0),
                                source="crossseed",
                            )],
                        )
                    self._log(
                        f"跨站回辅完成:{rec.get('title', '')}"
                        f"({rec.get('site_b', '')} 下载 → {rec.get('site_a', '')} 做种)"
                    )
                else:
                    failed += 1
                    pend.drop(sib_hash)
                    # ★ 回辅失败也要保护：数据已从来源站下下来了，H&R 义务照样存在。
                    self._crossseed_protect_source(sib_hash, rec, a_hash="")
                    # 诊断：打印两边文件清单摘要，下次遇到「特征码不同/校验 0%」能直接定位
                    try:
                        _da = _torrent_entries_digest(a_bytes)
                        _ent = downloader.get_file_entries(sib_hash) or []
                        _dbg_root = str(_ent[0][0] if _ent else "").replace("\\", "/").split("/")[0]
                        _dbg_fp = downloader.get_torrent_fingerprint(sib_hash) or ""
                        self._log(
                            f"跨站回辅失败诊断:{rec.get('title', '')[:40]}"
                            f" A端 n={_da.get('n')} root={str(_da.get('root'))[:40]} fp={str(_da.get('fp'))[:12]}"
                            f" | B端 n={len(_ent)} root={_dbg_root[:40]} fp={str(_dbg_fp)[:12]}"
                            f" | 完整特征码相同={_dbg_fp == str(_da.get('fp') or '')}",
                            "warning",
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    self._log(
                        f"跨站回辅失败:{rec.get('title', '')}({err or '校验不通过/未匹配'})"
                        f" → 来源份转入 H&R 保种保护({rec.get('site_b', '')})",
                        "warning",
                    )
            if done or failed:
                self._invalidate_summary()
            self._log(
                f"跨站回辅:完成 {done} / 失败 {failed} / 等待下载 {waiting}"
            )
        except Exception as e:  # noqa: BLE001
            import traceback
            logger.error(f"跨站回辅 异常: {e}\n{traceback.format_exc()}")
        finally:
            self._release_worker_slot()

    def get_crossseed(self, action: str = "", hash: str = "", site: str = "") -> Response:
        """跨站免费取种：待回辅队列 + 启用该功能的任务。

        - ``action=clear``：清空待回辅队列；
        - ``action=drop&hash=<sib_hash>``：删除单个跨站种（下载器 + 记录）；
        - ``action=unban&site=<domain>``：解除来源站黑名单（``site`` 空 = 全部解除）；
        - ``action=guard``：立即跑一次流量兜底核对。
        """
        try:
            act = str(action or "").strip().lower()
            if act in ("clear", "flush"):
                n = self._crossseed_pending().clear()
                return Response(success=True, message=f"已清空待回辅队列 {n} 条", data=self._crossseed_info())
            if act == "drop":
                h = str(hash or "").strip().lower()
                if not h:
                    return Response(success=False, message="缺少 hash", data=self._crossseed_info())
                pend = self._crossseed_pending()
                rec = (pend.items() or {}).get(h) or {}
                dl_name = str(rec.get("downloader") or "qbittorrent")
                msg = "已删除跨站种"
                _n = 0
                try:
                    downloader = self._get_downloader(dl_name)
                    if downloader is not None and getattr(downloader, "is_available", False):
                        _n, err = downloader.delete_torrents(hashes=[h], delete_file=True)
                        if err:
                            msg = f"记录已删，但下载器删除失败:{err}"
                except Exception as err:  # noqa: BLE001
                    msg = f"记录已删，但下载器删除异常:{err}"
                if _n:
                    self._journal_deletions({str(rec.get("task_id") or SILENT_HOST_TASK_ID): [
                        OperationItem(
                            hash=h, title=str(rec.get("title") or ""),
                            reason="手动删除跨站待回辅种（连文件删除；文件被共用时自动降级为只删种）",
                            size_gb=float(rec.get("size_gb") or 0.0),
                            source="crossseed",
                        )]}, log_prefix="跨站手动删除")
                pend.drop(h)
                pend.cleanup_torrent(str(rec.get("a_torrent") or ""))
                return Response(success=True, message=msg, data=self._crossseed_info())
            if act == "unban":
                n = self._cs_ban_clear(str(site or ""))
                return Response(success=True, message=f"已解除来源站黑名单 {n} 个", data=self._crossseed_info())
            if act == "guard":
                g = self._crossseed_guard()
                v = len(g.get("violations") or [])
                return Response(
                    success=True,
                    message=(f"流量兜底核对完成：检查 {len(g.get('checked_sites') or [])} 个来源站" + (
                        f"，拦截 {v} 个" if v else "，均正常")),
                    data=self._crossseed_info(),
                )
            return Response(success=True, message="OK", data=self._crossseed_info())
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=str(e), data={})
