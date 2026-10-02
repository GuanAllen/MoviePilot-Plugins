# -*- coding: utf-8 -*-
"""魔流 · formula —— 魔力公式与任务目标（公式计算、目标达成自动停）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


from ..bonus import (
    BonusParams,
    TorrentBonusInfo,
    aggregate_breakdown,
    calc_torrent_bonus,
)
from ..downloader_ops import (
    TorrentInfo,
)
from ..fetcher import (
    SITE_TZ_OFFSET_HOURS,
    pubdate_to_ts,
    ts_to_age_weeks,
)
from ..persistence import OperationItem
from ..recommend import _norm
from ..dtier import TierCache
from ..sites import get_formula_params, register_formula_preset
from ..sites.formula_fetch import (
    FormulaCapture,
    fetch_site_formula,
    fetch_seeding_list,
    fetch_official_titles,
    _norm_title as normalize_title,
)


from ..common import (
    MagicFlowTaskConfig,
    OFFICIAL_PAGES,
    SITE_FORMULA_RETRY,
    SITE_FORMULA_TTL,
    SITE_FORMULA_ZERO_TTL,
    SITE_OFFICIAL_STALE_TTL,
    SITE_OFFICIAL_TTL,
    USERDATA_ROW_TTL,
    enabled_of_run_mode,
    RUN_MODE_STOPPED,
    task_is_running,
)


class FormulaMixin:
    """formula 功能集（原 MagicFlow 方法原样搬入）。"""

    def _pubdate_ts(self, pubdate: Any) -> float:
        """把候选的发布时间转为 unix 秒(与候选排序同一套口径)。"""
        return pubdate_to_ts(pubdate)

    def _task_pub_dates(self, task) -> Dict[str, float]:
        """取本任务已记录的「种子发布时间」表(hash→unix 秒)。

        按当前站点时区口径校验:时区变了 → 旧值作废,回退到「做种时长」。
        """
        try:
            if self._store and task and getattr(task, "id", None):
                return self._store.get_pub_dates(task.id, tz=SITE_TZ_OFFSET_HOURS)
        except Exception:
            pass
        return {}

    def _site_official_titles(self, site_id: int) -> set:
        """站点官种标题集合(规范化),带 TTL 缓存。

        官种加成是「单种自身」的加成(站点对官种单独再算一遍基础公式 × 官种系数),
        会影响单颗种子的产出 → 影响选种/删种排序,因此纳入内部打分;
        后宫加成是用户级(依赖他人的种子),不影响「选哪一颗」,故不参与。
        """
        site = self._get_site(site_id)
        domain = (getattr(site, "domain", "") or "").strip().lower() if site else ""
        if not domain:
            return set()
        tc = self._cache_official()
        fresh = tc.get(domain, SITE_OFFICIAL_TTL)
        if isinstance(fresh, list):
            return set(fresh)
        # ★ PV 闸门:官种列表 = OFFICIAL_PAGES 页真实请求。被封/超预算时不打站点,
        #   但绝不能返回空集 —— 它参与打分与删种,空集会低估魔力 → 误删。
        if self._pv_block_reason(site_id) or not self._pv_allow(site_id, "official", want=OFFICIAL_PAGES):
            stale = tc.get(domain, SITE_OFFICIAL_STALE_TTL)
            return set(stale) if isinstance(stale, list) else set()
        try:
            titles = set(fetch_official_titles(site, pages=OFFICIAL_PAGES))
        except Exception as err:
            self._log(f"抓取官种列表失败 [{domain}]: {err}", "warning")
            stale = tc.get(domain, SITE_OFFICIAL_STALE_TTL)
            return set(stale) if isinstance(stale, list) else set()
        # ★ 3.38.0：PV 记账改由采集层按**实际请求页数**记（这里不再重复记）；
        #   并且空结果 = 抓取失败（预算/风控/改版）→ 回退旧值，绝不返回空集（防误删）
        if not titles:
            stale = tc.get(domain, SITE_OFFICIAL_STALE_TTL)
            if isinstance(stale, list) and stale:
                return set(stale)
            return set()
        tc.set(domain, sorted(titles), SITE_OFFICIAL_TTL)
        self._log(f"官种列表 [{domain}]:{len(titles)} 个官种")
        return titles

    def _convert_to_bonus_list(
        self,
        torrents: List[TorrentInfo],
        params: Optional[BonusParams] = None,
        pub_dates: Optional[Dict[str, float]] = None,
        ti_source: str = "publish",
        ni_map: Optional[Dict[str, int]] = None,
        official_titles: Optional[set] = None,
    ) -> List[TorrentBonusInfo]:
        """将下载器种子转换为魔力信息列表(可按站点公式参数计算)。

        ti_source:Ti 口径。``publish``(默认,= 自发布时间,站点文档口径)或
        ``seed_time``(= qB 做种时长,无发布时间时回落)。
        ni_map:hash→站点真实做种人数 Ni(可选,优先于 qB)。
        official_titles:官种标题集合(规范化),命中则标记 ``is_official``。
        """
        use_pub = str(ti_source or "publish").lower() == "publish"
        pub_dates = pub_dates or {}
        ni_map = ni_map or {}
        official_titles = official_titles or set()
        result = []
        for t in torrents:
            # Ni 优先用站点真实值;否则用 qB(做种中 → 至少 1,
            # qB 的 num_complete 对私种常为 0,不可信)。
            h = (t.hash or "").lower()
            ni = int(ni_map.get(h) or 0) or max(int(t.seeder or 0), 1)
            age_weeks = t.age_weeks
            if use_pub:
                ts = pub_dates.get(h)
                if ts and ts > 0:
                    age_weeks = ts_to_age_weeks(ts)
            is_official = bool(official_titles) and (normalize_title(t.title) in official_titles)
            bonus_info = calc_torrent_bonus(
                hash=t.hash,
                title=t.title,
                size_gb=t.size_gb,
                seeders=ni,
                leechers=t.leecher,
                age_weeks=age_weeks,
                volume_factor=t.volume_factor,
                is_zero_bonus=t.is_zero_bonus,
                is_free=t.is_free,
                is_double_free=t.is_double_free,
                hit_and_run=t.hit_and_run,
                is_official=is_official,
                params=params,
            )
            try:
                bonus_info.ratio = float(getattr(t, "ratio", 0) or 0)
            except (TypeError, ValueError):
                bonus_info.ratio = 0.0
            result.append(bonus_info)
        return result

    def _build_formula_params(self, task: MagicFlowTaskConfig) -> BonusParams:
        """
        解析任务对应的魔力公式参数。

        顺序:**站点自动抓取(mybonus.php,TTL 缓存)** → 站点预设(按域名)
              → 任务级覆盖 → NexusPHP 标准默认。
        """
        cap = self._acquire_site_formula(task)
        base = get_formula_params(task.site_domain, None)
        if cap and cap.ok:
            base = cap.to_params(base)
        return base.merged(
            t0=task.bonus_t0,
            n0=task.bonus_n0,
            b0=task.bonus_b0,
            l=task.bonus_l,
            zero_weight=task.bonus_zero_weight,
        )

    @staticmethod
    def _formula_report_empty(cap: Any) -> bool:
        """站点上报的时魔是否为 0 / 缺失。

        True 表示「这份页面里站点还没把我们的种算进魔力页」（刚建号 / 刚下种 / 站点缓存），
        调用方据此放宽缓存窗口、尽快重抓。
        """
        try:
            extra = getattr(cap, "extra", None) or {}
            total = extra.get("total_bonus_per_hour")
            if total is None:
                total = extra.get("current_bonus_per_hour")
            if total is None:
                return True
            return float(total or 0.0) <= 0.0
        except Exception:  # noqa: BLE001
            return False

    def _acquire_site_formula(self, task: MagicFlowTaskConfig):
        """
        自动抓取站点魔力公式(带 TTL 缓存)。

        命中缓存直接返回;否则用 MoviePilot SDK 抓 ``mybonus.php`` 解析。
        失败也短暂缓存(``SITE_FORMULA_RETRY``)以避免频繁打网络。
        返回 ``FormulaCapture`` 或 None。
        """
        domain = (getattr(task, "site_domain", "") or "").strip().lower()
        if not domain:
            return None
        cache = self._cache_formula()
        cached = cache.get(domain, SITE_FORMULA_TTL)
        if cached is not None and not self._formula_report_empty(cached):
            # 顺手把命中的参数回注预设(纯内存、零请求),否则热重载后预设会空一轮。
            self._register_formula_params(domain, cached, getattr(task, "site_name", "") or "")
            return cached
        # ★ 7.8.1：站点上报「时魔 = 0」不认 1h 长缓存，只认 ZERO_TTL 短缓存；
        #   过短窗口就后台重抓（单飞 + 失败冷却）——否则刚下种后 UI 会钉 0 一个小时。
        # 只有**启用中**的任务才值得为零值重抓（停用任务没在跑，白打站点请求）。
        _zero_ok = bool(getattr(task, "enabled", False))
        if cached is not None and _zero_ok:
            _short = cache.get(domain, SITE_FORMULA_ZERO_TTL)
            if _short is not None and not self._formula_report_empty(_short):
                self._register_formula_params(domain, _short, getattr(task, "site_name", "") or "")
                return _short
        if cached is not None and not _zero_ok:
            self._register_formula_params(domain, cached, getattr(task, "site_name", "") or "")
            return cached
        # 未命中/已过期:不阻塞当前请求--后台单飞抓取,本次先返回旧值(可能为 None)。
        # 这样 /status、总览等永远不会因站点 mybonus.php 卡顿/超时而拖慢。
        self._schedule_formula_fetch(task, domain, cache)
        return (cache.get(domain, SITE_FORMULA_ZERO_TTL) if (cached is not None and _zero_ok) else None) or cached

    def _register_formula_params(self, domain: str, cap: Any, name: str = "") -> None:
        """把公式参数注册进站点预设（纯内存、零请求）。

        旧版叫 refresh_site_preset，它会**再 fetch 一次**（双倍站点请求）；这里改成只
        消费已经拿到的 cap，不再触网。
        """
        overrides = {
            k: cap.params[k]
            for k in ("t0", "n0", "b0", "l", "zero_weight", "normal_weight")
            if isinstance(getattr(cap, "params", None), dict) and k in cap.params
        }
        if not overrides:
            return
        for key in {(domain or "").strip().lower(), (name or "").strip().lower()}:
            if key:
                try:
                    register_formula_preset(key, **overrides)
                except Exception:  # noqa: BLE001
                    pass

    def _schedule_formula_fetch(self, task: MagicFlowTaskConfig, domain: str, cache: TierCache) -> None:
        """后台抓取站点公式(每域名单飞;失败短冷却;不阻塞调用方)。"""
        fails = getattr(self, "_formula_fail_at", None)
        if fails is None:
            fails = self._formula_fail_at = {}
        if time.time() < float(fails.get(domain, 0.0) or 0.0):
            return
        flights = getattr(self, "_formula_flights", None)
        lock = getattr(self, "_formula_flight_lock", None)
        if flights is None or lock is None:
            lock = self._formula_flight_lock = threading.Lock()
            flights = self._formula_flights = set()
        with lock:
            if domain in flights:
                return
            flights.add(domain)

        def _worker() -> None:
            try:
                sid = int(getattr(task, "site_id", 0) or 0)
                # ★ 3.7.1 PV 闸门:被封 / 预算将尽时不再抓公式
                #   (旧版确实漏了这层 → PTT 被封后仍打了 98 次)
                if self._pv_block_reason(sid) or not self._pv_allow(sid, "formula", want=1):
                    return
                site = self._get_site(sid) if sid else None
                if site is None:
                    self._log(f"站点公式:未找到站点 {sid},本轮跳过", "warning")
                    return
                try:
                    # ★ 7.8.1：强制绕过采集页缓存——零值重抓时若命中旧的 0 页面就白跑了。
                    cap = fetch_site_formula(site, timeout=15, force=True)
                except Exception as err:
                    self._log(f"站点公式抓取失败 [{domain}]: {err}", "warning")
                    cap = None
                if cap and cap.ok:
                    self._register_formula_params(domain, cap, getattr(site, "name", "") or "")
                    cache.set(domain, cap, SITE_FORMULA_TTL)
                    self._log(f"站点公式已获取 [{domain}] {cap.note} params={cap.params} extra={cap.extra}")
                else:
                    fails[domain] = time.time() + SITE_FORMULA_RETRY
                # 公式就绪后让统计/总览失算失效;保留旧 heavy 供下次请求秒回并后台刷新。
                self._summary_cache = None
                self._summary_cache_at = 0.0
                self._stats_cache = {}
                self._status_heavy_at = 0.0
            finally:
                with lock:
                    flights.discard(domain)

        try:
            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            with lock:
                flights.discard(domain)


    def _site_user_id(self, site) -> Optional[str]:
        """读取站点用户 UID(做种列表页需要)。优先从 cookie 的 c_secure_uid(NexusPHP = base64(uid))解析。

        ★ 6.1.5/6.1.6：兑底走 ``_userdata_row`` + ``_ud_get``（已有 60s 缓存、且**已兼容 ORM 对象**）。
        以前这里手写了一版用 ``isinstance(row, dict)`` 的判断，而 MP 的
        ``SiteOper().get_userdata_latest()`` 返回的是 **ORM 对象**（已对照官方 BrushFlow 的
        ``getattr(row,'domain')`` 写法证实）→ 整条兑底成了**死代码**：15 个站里 9 个 cookie
        没有 ``c_secure_uid``（馒头/咖啡/大青虫/聆音/March/NovaHD/蟹黄堡/Depth Studio/YemaPT）
        → 天天「未取到站点 UID,跳过」，站点做种页永远拉不到。
        """
        cookie = getattr(site, "cookie", "") or ""
        try:
            m = re.search(r"c_secure_uid=([^;]+)", cookie)
            if m:
                import base64
                import urllib.parse
                v = urllib.parse.unquote(m.group(1)).strip()
                v += "=" * (-len(v) % 4)
                uid = base64.b64decode(v).decode("utf-8", "ignore").strip()
                if uid.isdigit():
                    return uid
        except Exception:
            pass
        try:
            row = self._userdata_row(int(getattr(site, "id", 0) or 0))
            if row is not None:
                uid = self._ud_get(row, "userid")
                if uid:
                    return str(uid).strip()
        except Exception:
            pass
        return None

    def _backfill_pub_dates(self, task, managed=None, ttl: int = 3600) -> int:
        """用站点做种列表页回填每个种子的「发布时间」(Ti 发布时长口径)。TTL 内不重复抓取。"""
        if not self._store or not task:
            return 0
        now = time.time()
        cache = getattr(self, "_pub_backfill_at", None)
        if cache is None:
            cache = {}
            self._pub_backfill_at = cache
        if now - float(cache.get(task.id, 0)) < ttl:
            return 0
        cache[task.id] = now
        site = self._get_site(task.site_id)
        if not site:
            self._log("回填发布时间:站点不存在,跳过", "warning")
            return 0
        uid = self._site_user_id(site)
        if not uid:
            self._log(
                f"回填发布时间:未取到站点 UID,跳过({getattr(site, 'name', '') or ''}/{getattr(site, 'domain', '') or ''})",
                "warning",
            )
            return 0
        try:
            rows = fetch_seeding_list(site, uid, timeout=25)
        except Exception as err:
            self._log(f"回填发布时间失败:{err}", "warning")
            return 0
        if not rows:
            self._log(f"回填发布时间:做种页为空(uid={uid}),跳过", "warning")
            return 0

        def _norm(s: str) -> str:
            t = (s or "").lower()
            t = re.sub(r"^\[[^\]]*\]", "", t)
            t = re.sub(r"[^a-z0-9]+", " ", t)
            return re.sub(r"\s+", " ", t).strip()

        by_title = {r["title_norm"]: r["pubdate"] for r in rows if r.get("title_norm")}
        by_size = [(r["size_bytes"], r["pubdate"]) for r in rows if r.get("size_bytes")]

        old = self._store.get_pub_dates(task.id, tz=SITE_TZ_OFFSET_HOURS)
        mapping: Dict[str, float] = {}
        for t in (managed or []):
            h = (getattr(t, "hash", "") or "").lower()
            if not h or h in old:
                continue
            dtstr = by_title.get(_norm(getattr(t, "title", "")))
            if not dtstr and by_size:
                sz = float(getattr(t, "size_gb", 0) or 0) * (1024 ** 3)
                if sz > 0:
                    best_dt = None
                    best_d = 1e18
                    for s, dt in by_size:
                        dd = abs(s - sz)
                        if dd < best_d:
                            best_d, best_dt = dd, dt
                    if best_dt and best_d <= 0.01 * sz:
                        dtstr = best_dt
            if not dtstr:
                continue
            ts = pubdate_to_ts(dtstr)
            if ts > 0:
                mapping[h] = ts
        if mapping:
            self._store.note_pub_dates(task.id, mapping, tz=SITE_TZ_OFFSET_HOURS)
            self._sync_seed_pub_dates(mapping)
            self._log(
                f"回填发布时间[{getattr(task, 'name', '') or ''}]:"
                f"{len(mapping)} 个种子改用「发布时长」计算 Ti"
            )
        else:
            # ★ 6.1.6：区分「没什么可补」（正常，已记录过）与「真没匹上」（异常）。
            #   旧版一律 warning「未匹配(做种页 N 条)」→ 一天 26 条噪音，且看不出原因；
            #   实测真相：March 的 43 条 pub_dates 早就在，做种页那 6 条全在里面 → 全被
            #   ``if h in old: continue`` 跳过 → 根本不是「没匹配上」。
            _mg = list(managed or [])
            _known = sum(
                1 for t in _mg
                if (getattr(t, "hash", "") or "").lower() in old
            )
            if _known and _known >= len(_mg):
                self._dbg(
                    f"回填发布时间[{getattr(task, 'name', '') or ''}]:"
                    f"本轮无新增(做种页 {len(rows)} 条,{_known} 个已记录)"
                )
            else:
                self._log(
                    f"回填发布时间[{getattr(task, 'name', '') or ''}]:未匹配"
                    f"(做种页 {len(rows)} 条/托管 {len(_mg)} 个/已记录 {_known}/"
                    f"{getattr(site, 'name', '') or ''})",
                    "warning",
                )
        return len(mapping)

    def _sync_seed_pub_dates(self, mapping: Dict[str, float]) -> int:
        """把「发布时间」落进**种子表 published_at**（5 表契约）。

        Ti 的真值仍在 TaskState.pub_dates（老 kv / Redis），这里只是镜像——
        否则 ``mf_seed.published_at`` 永远是空的（线上 913 行全空、Ti 只活在边上）。
        """
        if not mapping:
            return 0
        try:
            store = self._tag_state()
            patches = {
                str(h).lower(): {"published_at": float(ts)}
                for h, ts in mapping.items()
                if ts and float(ts) > 0
            }
            if not patches:
                return 0
            return int(store.put_many(patches) or 0)
        except Exception as err:  # noqa: BLE001
            self._dbg(f"发布时间落表失败:{err}")
            return 0

    @staticmethod
    def _ud_get(row, key, default=None):
        """兼容 dict / ORM 对象两种形态读取用户数据字段。"""
        if row is None:
            return default
        if isinstance(row, dict):
            v = row.get(key, default)
        else:
            v = getattr(row, key, default)
        return default if v is None else v

    def _userdata_row(self, site_id: int):
        """找到指定站点最新的用户数据行(dict 或 ORM 对象均可)。

        带 60s 内存缓存(按 site_id):_status_heavy 一次会调 N 次(N 任务数),
        原版每次都 ``SiteOper().get_userdata_latest()`` 走 DB + 循环找域名,
        单次 8s 重建里 DB 占大头。缓存后同 site_id TTL 内复用=0 网络。
        """
        cache = getattr(self, "_userdata_row_cache", None)
        if cache is None:
            cache = self._userdata_row_cache = {}
        now = time.time()
        cached_hit = cache.get(site_id)
        if cached_hit is not None:
            ts, row = cached_hit
            if (now - ts) < USERDATA_ROW_TTL:
                return row
        try:
            from app.db.oper.site import SiteOper
            rows = SiteOper().get_userdata_latest() or []
        except Exception:
            cache[site_id] = (now, None)
            return None
        site = self._get_site(site_id)
        want_domain = (getattr(site, "domain", "") or "").strip() if site else ""
        match = None
        # ★ 先按域名精确匹配（主键）。
        #   旧写法在同一个循环里「域名不中就比 id」，而 siteuserdata.id 与 site.id
        #   **不是同一个序列** → 两个小整数撞上就会拿别的站的用户行（跟着污染魔力/做种数/Ti）。
        if want_domain:
            for row in rows:
                if str(self._ud_get(row, "domain", "") or "").strip() == want_domain:
                    match = row
                    break
        if match is None:      # 没域名才退而求其次：按站名（同样来自 site 表，不会错站）
            want_name = str(getattr(site, "name", "") or "").strip() if site else ""
            if want_name:
                for row in rows:
                    if str(self._ud_get(row, "name", "") or "").strip() == want_name:
                        match = row
                        break
        cache[site_id] = (now, match)
        return match

    def _site_seeding_count(self, site_id: int) -> int:
        """站点账号「去重后」的做种数(站点「0.5×做种数」固定奖励用的就是这个口径)。

        注意:部分站点(如 Pttime)userdata 的 ``seeding`` 会含重复条目,而站点计算
        「做种固定奖励」时按去重后的做种数计(实测 Pttime seeding=32、去重后=23,站点
        B 恰按 23 算)。故以 ``seeding_info`` 去重为准,取不到时回落 ``seeding`` 字段,
        再取不到返回 0(调用方回落到本任务托管数)。
        """
        row = self._userdata_row(site_id)
        if row is None:
            return 0
        si = self._ud_get(row, "seeding_info")
        if si:
            uniq = set()
            for it in si or []:
                try:
                    uniq.add((int(it[0]), float(it[1])))
                except (TypeError, ValueError, IndexError):
                    continue
            if uniq:
                return len(uniq)
        try:
            return int(self._ud_get(row, "seeding", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _site_ni_map(self, site_id: int, managed) -> Dict[str, int]:
        """从站点用户数据取每颗种子的真实做种人数 Ni(按体积 1% 容差匹配)。

        站点公式的 Ni 是「当前做种者数」,qB 的 num_complete 对私种常为 0,
        不可用;seeding_info 为 [[seeders, size_bytes], ...]。
        """
        out: Dict[str, int] = {}
        if not managed:
            return out
        row = self._userdata_row(site_id)
        si = self._ud_get(row, "seeding_info") if row is not None else None
        if not si:
            return out
        entries = []
        for it in si:
            try:
                n, s = int(it[0]), float(it[1])
            except (TypeError, ValueError, IndexError):
                continue
            if s > 0:
                entries.append((s, n))
        if not entries:
            return out
        for t in managed or []:
            h = (getattr(t, "hash", "") or "").lower()
            sz = float(getattr(t, "size_gb", 0) or 0) * (1024 ** 3)
            if not h or sz <= 0:
                continue
            best = None
            bd = 1e18
            for s, n in entries:
                dd = abs(s - sz)
                if dd < bd:
                    bd, best = dd, n
            if best is not None and bd <= 0.01 * sz:
                out[h] = int(best)
        return out

    def _site_user_stats(self, site_id: int) -> Dict[str, Any]:
        """站点账号「真实数据」(来自 MoviePilot 站点用户数据)--上传/下载/分享率/做种/下载数/魔力。

        字节量(upload/download/seeding_size/leeching_size)与积分(bonus)原样返回,
        另带数据更新时间,供前端展示「站点侧真实情况」(区别于下载器本地统计)。
        """
        out: Dict[str, Any] = {
            "ok": False,
            "upload": 0.0,
            "download": 0.0,
            "ratio": 0.0,
            "seeding": 0,
            "leeching": 0,
            "seeding_size": 0.0,
            "leeching_size": 0.0,
            "bonus": 0.0,
            "user_level": "",
            "join_at": "",
            "updated_at": "",
        }
        try:
            row = self._userdata_row(site_id)
        except Exception:
            row = None
        if row is None:
            return out

        def _f(key: str) -> float:
            try:
                return float(self._ud_get(row, key, 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        def _i(key: str) -> int:
            try:
                return int(self._ud_get(row, key, 0) or 0)
            except (TypeError, ValueError):
                return 0

        _upload = _f("upload")
        _download = _f("download")
        _ratio = _f("ratio")
        # 部分站点(如 PTT)不在用户数据里写分享率,用上传/下载兜底算一个。
        if _ratio <= 0 and _download > 0:
            _ratio = round(_upload / _download, 3)
        out.update({
            "ok": True,
            "upload": _upload,
            "download": _download,
            "ratio": _ratio,
            "seeding": _i("seeding"),
            "leeching": _i("leeching"),
            "seeding_size": _f("seeding_size"),
            "leeching_size": _f("leeching_size"),
            "bonus": _f("bonus"),
            "user_level": str(self._ud_get(row, "user_level", "") or ""),
            "join_at": str(self._ud_get(row, "join_at", "") or ""),
            "updated_at": " ".join(
                str(x).strip() for x in (
                    self._ud_get(row, "updated_day", ""),
                    self._ud_get(row, "updated_time", ""),
                ) if x
            ),
        })
        return out

    def _site_reported(self, task: MagicFlowTaskConfig) -> Dict[str, Any]:
        """站点上报的魔力数据(黑盒:不展示自算值)。

        来源:抓取的 ``mybonus.php``--每小时魔力、当前 A、当前魔力值。
        """
        out: Dict[str, Any] = {
            "ok": False,
            "bonus_per_hour": 0.0,
            "a": 0.0,
            "current_bonus": 0.0,
            "base_bonus": 0.0,
            "base_count": None,
            "base_size_text": "",
            "official_bonus": 0.0,
            "harem_bonus": 0.0,
            "harem_hourly": 0.0,
            "table": [],
            "source": "",
            "site_domain": getattr(task, "site_domain", "") or "",
            "site_name": getattr(task, "site_name", "") or "",
            "user": {},
        }
        try:
            cap = self._acquire_site_formula(task)
            if cap and getattr(cap, "ok", False):
                extra = getattr(cap, "extra", {}) or {}
                total = extra.get("total_bonus_per_hour")
                if total is None:
                    total = extra.get("current_bonus_per_hour")
                out["ok"] = True
                out["bonus_per_hour"] = float(total or 0)
                out["a"] = float(extra.get("current_a") or extra.get("base_a") or 0)
                out["base_bonus"] = float(extra.get("base_bonus") or 0)
                out["base_count"] = extra.get("base_count")
                out["base_size_text"] = extra.get("base_size_text") or ""
                out["official_bonus"] = float(extra.get("official_bonus") or 0)
                out["harem_bonus"] = float(extra.get("harem_bonus") or 0)
                out["harem_hourly"] = float(extra.get("harem_hourly") or 0)
                out["table"] = extra.get("bonus_table") or []
                out["source"] = getattr(cap, "source", "") or ""
        except Exception as err:
            self._log(f"读取站点上报魔力失败: {err}", "warning")
        user = self._site_user_stats(task.site_id)
        out["user"] = user
        out["current_bonus"] = float(user.get("bonus") or 0.0)
        return out

    def _site_current_bonus(self, site_id: int) -> float:
        """读取指定站点当前魔力值(用于自动保护阈值)。"""
        row = self._userdata_row(site_id)
        if row is None:
            return 0.0
        try:
            return float(self._ud_get(row, "bonus", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    # ---------------------------------------------------------
    # 任务目标(达到后自动停止任务)
    # ---------------------------------------------------------

    def _task_goal_status(self, task: MagicFlowTaskConfig, light: bool = False) -> Dict[str, Any]:
        """任务目标完成情况(用于展示与自动停止判定)。

        目标口径随任务类型:
          - bonus:站点魔力值(SiteUserData.bonus)达到 ``goal_value``;
          - brush:站点上传量(SiteUserData.upload,字节)达到 ``goal_value`` GB。
        返回以 ``goal_`` 前缀的字段,避免与任务其它字段冲突。

        30s 内存缓存（按 task_id+light 分别缓存）：
        - light=False 缓存：全量（包含 live 真实值）；
        - light=True 缓存：仅配置面（warming 期点用）。
        """
        cache = getattr(self, "_task_goal_status_cache", None)
        if cache is None:
            cache = self._task_goal_status_cache = {}
        ckey = (str(getattr(task, "id", "") or ""), bool(light))
        hit = cache.get(ckey)
        now = time.time()
        if hit is not None and (now - float(hit.get("ts", 0))) < 30:
            return dict(hit.get("data") or {})
        is_brush = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"
        unit = "GB" if is_brush else "魔力值"
        out: Dict[str, Any] = {
            "goal_has": False,
            "goal_reached": False,
            "goal_current": 0.0,
            "goal_target": 0.0,
            "goal_unit": unit,
        }
        try:
            tgt = float(getattr(task, "goal_value", None) or 0)
        except (TypeError, ValueError):
            tgt = 0.0
        if tgt <= 0:
            cache[ckey] = {"ts": now, "data": out}
            return out
        out["goal_has"] = True
        out["goal_target"] = tgt
        if light:
            out["goal_source"] = "pending"
            cache[ckey] = {"ts": now, "data": out}
            return out
        stats = self._site_user_stats(task.site_id) or {}
        # ★ 优先用「站点实时数据」(直连站点用户栏,240s 缓存),拿不到才回退 MP 的 6h 快照。
        live: Dict[str, Any] = {}
        try:
            if getattr(self, "_live", None) is not None and int(task.site_id or 0):
                live = self._live.get(int(task.site_id))
        except Exception:  # noqa: BLE001
            live = {}
        live_ok = bool(isinstance(live, dict) and live.get("ok"))
        out["goal_source"] = "live" if live_ok else "mp"
        if is_brush:
            base = float(live.get("upload") or 0.0) if live_ok else 0.0
            if base <= 0:
                base = float(stats.get("upload") or 0.0)
            cur = base / (1024 ** 3)   # 字节 → GB
        else:
            base = float(live.get("bonus") or 0.0) if live_ok else 0.0
            if base <= 0:
                base = float(stats.get("bonus") or 0.0)
            cur = base
        out["goal_current"] = cur
        out["goal_reached"] = bool(stats.get("ok")) and cur >= tgt - 1e-9
        cache[ckey] = {"ts": now, "data": out}
        return out

    def _maybe_autostop_for_goal(self, task: MagicFlowTaskConfig) -> bool:
        """任务达到目标则自动停用(仅停调度:不搬种、不撤种、不删种)。返回是否因此停用。"""
        if not task_is_running(task):
            return False
        st = self._task_goal_status(task)
        if not (st.get("goal_has") and st.get("goal_reached")):
            return False
        task.run_mode = RUN_MODE_STOPPED
        task.enabled = enabled_of_run_mode(RUN_MODE_STOPPED)
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary()
        self._apply_task_traffic_limit()
        self._apply_seed_upload_limit()
        self._log(
            f"魔流 [{task.name}] 已达任务目标({st['goal_current']:.4g}/{st['goal_target']:.4g} "
            f"{st['goal_unit']})→ 自动停止任务"
        )
        # 异步暂停全部托管种(保文件、可逆),避免达标后继续非免费下载
        self._spawn_run_mode_apply(task, "stopped")
        if self._store:
            try:
                self._store.journal.record(
                    task_id=task.id,
                    kind="goal",
                    items=[OperationItem(
                        hash="",
                        title="已达目标,自动停止",
                        reason=f"{st['goal_current']:.4g}/{st['goal_target']:.4g} {st['goal_unit']}",
                    )],
                )
            except Exception as err:
                self._log(f"记录达标停止失败:{err}", "warning")
        return True

