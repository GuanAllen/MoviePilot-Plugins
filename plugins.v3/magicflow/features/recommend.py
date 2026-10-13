# -*- coding: utf-8 -*-
"""魔流 · recommend —— 推荐（找值得入库的片 + 通知 + 可选整理）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import re
import threading
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple


from app.schemas import Response
from app.sdk.logging import logger

from ..downloader_ops import (
    DownloaderAdapter,
)
from ..persistence import OperationItem
from ..recommend import (
    RecommendEngine,
    _norm,
    episode_info,
    episode_info_files,
    recognize,
)


from ..common import (
    MagicFlowTaskConfig,
    RECOMMEND_FILES_MAX,
    RECOMMEND_FILES_TTL,
    RECOMMEND_LIVE_LIBRARY_CHECK,
    RECOMMEND_SCAN_MAX,
    task_is_participating,
)


def _rec_group_key(media_key: str, info: Dict[str, Any]) -> str:
    """「作品+季」分组键（★ 15.8.21）：同作品不同季分开；无季信息则等于作品键。"""
    if not media_key:
        return ""
    se = str((info or {}).get("season") or "").strip().upper()
    return "%s@%s" % (media_key, se) if se else media_key


class RecommendMixin:
    """recommend 功能集（原 MagicFlow 方法原样搬入）。"""

    # ---------------------------------------------------------
    # 推荐甄别(刷流种价值生命周期)
    # ---------------------------------------------------------

    def _get_recommend_engine(self) -> RecommendEngine:
        engine = getattr(self, "_recommend_engine", None)
        if engine is None:
            engine = self._recommend_engine = RecommendEngine(self)
        return engine

    def _exclude_subscribed(self, candidates: List[Any]) -> List[Any]:
        """刷流选种:剔除命中「当前订阅标题」的候选。

        用归一化标题**子串**匹配(订阅标题 ⊆ 候选标题);识别不出 / 订阅为空 → 原样返回,
        不误杀。订阅标题过短(<2 字符)不参与匹配,避免误伤。
        """
        engine = self._get_recommend_engine()
        if not engine:
            return candidates
        try:
            subs = engine.subscribed_titles()
        except Exception:
            return candidates
        subs = {s for s in subs if len(s) >= 2}
        if not subs:
            return candidates
        # "_norm/recognize" 已提到模块顶层导入：worker 运行时不再碰 import 机制，
        # 避免热重载期间与 loader 形成「循环导入死锁」（详见 README 存储/重载章节）。
        out: List[Any] = []
        for c in candidates:
            nt = _norm(getattr(c, "title", ""))
            if nt and any(s in nt for s in subs):
                continue
            out.append(c)
        return out

    @staticmethod
    def _recommend_media_key(media: Optional[Dict[str, Any]], info: Dict[str, Any]) -> str:
        """作品级去重 key:优先「数据源_原生ID」,否则回退「标题(+年份)」。"""
        if media and media.get("source") and media.get("id"):
            return f"{media.get('source')}_{media.get('id')}"
        title = str(info.get("title") or "").strip().lower()
        if not title:
            return ""
        year = info.get("year")
        return f"t:{title}:{year}" if year else f"t:{title}"

    def _recommend_in_library(self, info: Dict[str, Any]) -> bool:
        """识别结果是否**已在影视库**中。

        主路:``MediaServerOper().exists``(MoviePilot 同步的媒体库 DB 表,也是官方
        「/mediaserver/exists 查询本地是否存在」用的口径)。
        可选:``MediaServerChain().media_exists`` 实时查媒体服务器(默认关,因
        trimemedia/FileManagerModule 的实现会报错刷日志)。
        任何异常都视为「未知」→ False(不阻断)。结果按 media_key 短缓存(600s)。
        """
        if not info.get("recognized"):
            return False
        key = self._recommend_media_key(
            {"source": info.get("media_source"), "id": info.get("media_id")}, info
        ) or (str(info.get("title") or "").strip().lower())
        if key:
            cache = getattr(self, "_lib_cache", None)
            if cache is None:
                cache = self._lib_cache = {}
            hit = cache.get(key)
            if hit and (time.time() - float(hit[0])) < 600.0:
                return bool(hit[1])
        result = False
        # 1) 主路:MoviePilot 同步的媒体库 DB 表(稳定、无副作用)
        try:
            from app.db.oper.mediaserver import MediaServerOper  # noqa: WPS433
            oper = MediaServerOper()
            mtype = info.get("type") or None
            year = str(info.get("year") or "") or None
            title = info.get("title") or None
            item = None
            if info.get("media_source") and info.get("media_id"):
                item = oper.exists(
                    media_source=info.get("media_source"), media_id=info.get("media_id"),
                    mtype=mtype, title=title, year=year,
                )
            if not item and title:
                item = oper.exists(title=title, mtype=mtype, year=year)
            result = bool(item)
        except Exception as err:  # noqa: BLE001
            self._dbg(f"影视库DB查询失败(忽略): {err}")
        # 2) 可选:实时查媒体服务器(能发现尚未同步进 DB 的条目)
        if not result and RECOMMEND_LIVE_LIBRARY_CHECK:
            try:
                from app.schemas.types import MediaSource  # noqa: WPS433
                from app.schemas.context import MediaInfo  # noqa: WPS433
                from app.chain.mediaserver import MediaServerChain  # noqa: WPS433
                ms = info.get("media_source")
                mid = info.get("media_id")
                mi = MediaInfo(
                    type=info.get("type"),
                    title=info.get("title"),
                    year=str(info.get("year") or "") or None,
                    media_source=(MediaSource(ms) if ms else None),
                    media_id=(str(mid) if mid else None),
                )
                if MediaServerChain().media_exists(mi):
                    result = True
            except Exception as err:  # noqa: BLE001
                self._dbg(f"影视库实时查询失败(忽略): {err}")
        if key:
            try:
                self._lib_cache[key] = (time.time(), result)
            except Exception:  # noqa: BLE001
                pass
        return result

    def _recommend_dup(
        self,
        store: Any,
        media_key: str,
        exclude_hash: str,
        statuses: tuple = ("recommended", "confirmed"),
    ) -> Optional[str]:
        """同一部「作品+季」是否已有指定状态的记录;返回命中的 hash(用于跨 hash 去重)。

        ``media_key`` 实为 **分组键**（``作品@季``，见 ``_rec_group_key``）。
        """
        if not media_key:
            return None
        try:
            items = store.all() or {}
        except Exception:  # noqa: BLE001
            return None
        for h, rec in items.items():
            if h == exclude_hash:
                continue
            if str(rec.get("status")) not in statuses:
                continue
            if str(rec.get("group_key") or rec.get("media_key") or "") == media_key:
                return str(h)
        return None

    @staticmethod
    def _recommend_dup_group(store: Any, group_id: str,
                             hashes: Any) -> str:
        """★ 资源级去重：同一**资源**（文件组）是否已有推荐记录 → 返回命中的 hash。

        Master 2026-09-28：「推荐推的是资源，不是种」——所以判重按资源（组）来，
        同组的任何成员命中推荐，整组都不再重复推荐。
        """
        if store is None:
            return ""
        try:
            items = store.all() or {}
        except Exception:  # noqa: BLE001
            return ""
        gid = str(group_id or "").strip()
        hs = {str(x or "").lower() for x in (hashes or [])}
        for h, rec in items.items():
            if str(rec.get("status") or "") not in ("recommended", "pending", "confirmed"):
                continue
            if gid and str(rec.get("group_id") or "") == gid:
                return str(h)
            if str(h).lower() in hs:
                return str(h)
            for m in (rec.get("members") or []):
                if str(m or "").lower() in hs:
                    return str(h)
        return ""

    def _recommend_subscribe_season(
        self, info: Dict[str, Any], media: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, str]:
        """★ 15.8.24：给 MP 加「整季订阅」（MP 按 标题+年份+季 自行识别媒体）。

        幂等：MP 的订阅写入按「媒体身份+季」查重，命中既有订阅会**原样返回**其 id
        （说明「订阅已存在」）。返回 ``(sid, msg)``；sid 为 0 = 没订上（识别不出 / 无季号 / 异常）。
        """
        media = media or {}
        title = str(media.get("title") or info.get("title") or "").strip()
        year = str(media.get("year") or info.get("year") or "").strip()
        if not title:
            return 0, "无标题"
        season = int("".join(ch for ch in str(info.get("season") or "") if ch.isdigit()) or 0)
        if season <= 0:
            return 0, "无季号"
        try:
            from app.chain.subscribe import SubscribeChain  # noqa: WPS433
            from app.schemas.types import MediaType  # noqa: WPS433

            sid, msg = SubscribeChain().add(
                title=title,
                year=year,
                mtype=MediaType.TV,
                season=season,
                source="魔流",
                message=True,
                exist_ok=False,
            )
            return int(sid or 0), str(msg or "")
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流 整季订阅失败 {title} S{season}: {err}")
            return 0, str(err)

    @staticmethod
    def _recommend_worth(info: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
        """是否够格推荐:评分 > 门槛 且(按需)叠加 榜单/热映/订阅。"""
        if not info.get("recognized"):
            return False
        try:
            min_rating = float(cfg.get("min_rating", 7.5) or 0)
        except (TypeError, ValueError):
            min_rating = 7.5
        try:
            rating = float(info.get("rating") or 0)
        except (TypeError, ValueError):
            rating = 0.0
        if rating > min_rating:
            return True
        # 或关系:命中「榜单 / 热映 / 订阅」也算达标(叠加豆瓣评分)
        if bool(cfg.get("require_chart", True)) and (
            info.get("in_chart") or info.get("in_subscribe")
        ):
            return True
        return False

    def _recommend_low_disk(self, torrents: List[Any]) -> bool:
        """当前任务保存卷是否「磁盘不足」(低于阈值即视为过期)。"""
        try:
            min_free_gb = float(self._recommend_cfg.get("disk_min_free_gb", 50.0) or 0)
        except (TypeError, ValueError):
            min_free_gb = 50.0
        if min_free_gb <= 0:
            return False
        path = ""
        for t in torrents:
            p = str(getattr(t, "save_path", "") or getattr(t, "content_path", "") or "")
            if p:
                path = p
                break
        if not path:
            return False
        # ★ 5.10.2:下载器返回的是**宿主路径**(如 /vol6/1000/movie/刷流),容器里 statvfs 不到 →
        #   改为按「目录分池」映射到容器目录再算(见 features/pool.py)。
        try:
            dirs = self._pool_dirs()
            _pool_name, container = self._match_pool(path, dirs)
            info = self._usage(container) if container else {}
            if not info:
                return False
            return (float(info.get("free") or 0) / (1024 ** 3)) < min_free_gb
        except Exception:  # noqa: BLE001
            return False

    def recommend_scan(self) -> None:
        """推荐甄别(插件级**单 worker**,低频)。每轮只处理一个任务(round-robin)。"""
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        if not cfg.get("enabled", True):
            return
        eligible = [t for t in self._task_configs.values() if task_is_participating(t)]
        if not eligible:
            # ★ 观测：不再静默空跑——无启用任务时每 6h 记一条（不刷屏）
            _now = time.time()
            if _now - float(getattr(self, "_recommend_idle_log_at", 0) or 0) >= 6 * 3600:
                self._recommend_idle_log_at = _now
                self._log("推荐甄别:无启用任务 → 本轮跳过（静默池分拣与推荐渲染不受影响）")
            return
        eligible.sort(key=lambda t: str(t.id))
        ids = [str(t.id) for t in eligible]
        last = str(getattr(self, "_recommend_cursor", "") or "")
        start = (ids.index(last) + 1) % len(eligible) if last in ids else 0
        task = eligible[start]
        self._recommend_cursor = str(task.id)
        if not self._acquire_worker_slot("推荐甄别"):
            return
        try:
            try:
                self._recommend_scan_task(task)
            except Exception as e:  # noqa: BLE001
                import traceback
                logger.error(f"魔流 推荐甄别 调度异常: {e}\n{traceback.format_exc()}")
        finally:
            self._release_worker_slot()

    def _recommend_backfill_file_episodes(
        self, store: Any, downloader: Any, limit: int = 0
    ) -> int:
        """★ 15.8.23：给**存量推荐记录**补「单集/整季」判定（不依赖本任务名下的种）。

        为什么：推荐扫描只遍历**本任务名下的种**（站点匹配 + 任务启用），所以
        「已在库」「别的站」「已移走」的种永远轮不到 → 卡片一直停在「集数未知」。
        这里按**记录**遍历：凡下载器里还在、且没查过文件列表（``files_at`` 空）的就查一次，
        每轮封顶 ``limit``（默认 RECOMMEND_FILES_MAX）条。幂等：查过即写 ``files_at``。
        """
        n = 0
        try:
            items = store.all() or {}
        except Exception:  # noqa: BLE001
            return 0
        cap = int(limit or RECOMMEND_FILES_MAX)
        for h, rec in list(items.items()):
            if n >= cap:
                break
            if not isinstance(rec, dict) or rec.get("files_at"):
                continue
            if rec.get("episode"):
                continue
            if str(rec.get("kind") or "") not in ("season", "multi", ""):
                continue
            # ★ 逐条**新建**预算（复用同一个 list 会让第二条起全被挡掉）
            fi = self._recommend_episode_probe(
                downloader, str(h), str(rec.get("title") or ""), rec, [1]
            )
            if not fi:
                continue
            upd = {k: v for k, v in fi.items() if v not in (None, "")}
            if not upd:
                continue
            try:
                store.upsert(str(h), **upd)
                n += 1
            except Exception:  # noqa: BLE001
                pass
        return n

    def _recommend_episode_probe(
        self, downloader: Any, h: str, name: str, rec: Dict[str, Any], budget: List[int]
    ) -> Dict[str, Any]:
        """★ 15.8.22：种名**只有季、没有集号**时，用下载器**文件列表**判定单集/整季。

        为什么：DepWeb/ADWeb 这类发布把集号藏在文件名里（`X.2022.S02.…` 里只有
        `X.2022.S02E01.…mkv`）→ 只按种名会误判「整季」，其实是单集。
        花销：每个种一次 `get_files`；**每轮封顶** ``RECOMMEND_FILES_MAX``，
        查过写 ``files_at`` 缓存 ``RECOMMEND_FILES_TTL``（空结果 3 天后重试）。
        """
        try:
            info = episode_info(name)
        except Exception:  # noqa: BLE001
            return {}
        if info.get("episode"):
            return {}
        if not info.get("kind") or info.get("kind") == "movie":
            return {}
        now = time.time()
        if rec:
            _ttl = float(RECOMMEND_FILES_TTL) if rec.get("files_n") else 3 * 86400
            try:
                if rec.get("files_at") and now - float(rec.get("files_at") or 0) < _ttl:
                    return {}
            except (TypeError, ValueError):
                pass
        if budget[0] <= 0:
            return {}
        budget[0] -= 1
        try:
            entries = downloader.get_file_entries(h) or []
        except Exception:  # noqa: BLE001
            entries = []
        fi = episode_info_files(entries)
        out = dict(fi)
        out["files_at"] = now
        out.setdefault("files_n", len(entries) if entries else 0)
        if not fi.get("season") and info.get("season"):
            out["season"] = str(info.get("season") or "")
        return out

    def _recommend_merge_episode(
        self, store: Any, h: str, rec: Dict[str, Any], fi: Dict[str, Any]
    ) -> Dict[str, Any]:
        """把文件列表推出的季/集**就地补写**到存量推荐记录（覆盖种名推出的）。"""
        upd: Dict[str, Any] = {}
        for k in ("kind", "season", "episode", "ep_begin", "ep_end"):
            v = fi.get(k)
            if v not in (None, ""):
                upd[k] = v
        if fi.get("files_at"):
            upd["files_at"] = float(fi.get("files_at") or 0)
        if "files_n" in fi:
            upd["files_n"] = int(fi.get("files_n") or 0)
        if not upd:
            return rec
        try:
            store.upsert(h, **upd)
        except Exception:  # noqa: BLE001
            return rec
        return store.get(h) or rec

    def _recommend_backfill_episodes(self, store: Any) -> int:
        """★ 15.8.21：给存量推荐记录补「季/集」（纯本地解析，幂等）。

        老记录只有作品名 → 卡片分不清「单集 / 整季」；这里按种子名补 season/
        episode/kind/group_key。返回补写条数。
        """
        n = 0
        try:
            items = store.all() or {}
        except Exception:  # noqa: BLE001
            return 0
        for h, rec in list(items.items()):
            if not isinstance(rec, dict) or rec.get("kind"):
                continue
            title = str(rec.get("title") or "")
            if not title:
                continue
            info = episode_info(title)
            if not info.get("kind") or info.get("kind") == "movie":
                continue
            try:
                store.upsert(
                    h, season=info.get("season") or "", episode=info.get("episode") or "",
                    ep_begin=int(info.get("ep_begin") or 0), ep_end=int(info.get("ep_end") or 0),
                    kind=str(info.get("kind") or ""),
                    group_key=_rec_group_key(str(rec.get("media_key") or ""), info),
                )
                n += 1
            except Exception:  # noqa: BLE001
                pass
        return n

    def _recommend_scan_task(self, task: MagicFlowTaskConfig) -> None:
        """对单个任务做一轮推荐甄别(识别 + 推荐/临时判定 + 生命周期清理)。"""
        task_id = str(task.id)
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        if not cfg.get("enabled", True) or not task_is_participating(task):
            return
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return
        # ★ 15.8.21：存量记录补季/集（幂等，只补缺 kind 的）
        try:
            self._recommend_backfill_episodes(store)
        except Exception:  # noqa: BLE001
            pass
        downloader = self._get_downloader(task.downloader)
        if not downloader or not downloader.is_available:
            return
        # ★ 15.8.23：再按**记录**补「单集/整季」（覆盖库里/别的站/已移走的种）
        try:
            self._recommend_backfill_file_episodes(store, downloader)
        except Exception:  # noqa: BLE001
            pass
        if not self._try_begin_run(task_id):
            self._log(f"魔流 [{task.name}] 推荐甄别:上一轮仍在执行,跳过")
            return
        try:
            self._get_recommend_engine().begin_round(int(cfg.get("douban_max_per_run") or 0))
            torrents = self._task_managed_torrents(task)
            if not torrents:
                return
            asset = self._media_asset_hashes(torrents, task)
            protected = self._store.get_protected_torrents(task_id) if self._store else set()
            rec_tag = str(cfg.get("tag") or "魔流-推荐")
            engine = self._get_recommend_engine()
            now = time.time()
            try:
                expire_sec = float(cfg.get("expire_days", 7.0) or 0) * 86400
            except (TypeError, ValueError):
                expire_sec = 7 * 86400
            try:
                temp_sec = float(cfg.get("temp_ttl_days", 7.0) or 0) * 86400
            except (TypeError, ValueError):
                temp_sec = 7 * 86400
            low_disk = self._recommend_low_disk(torrents)

            scanned = recommended = expired = evaluated = 0
            to_downgrade: List[str] = []
            budget = max(int(RECOMMEND_SCAN_MAX), 1)
            # ★ 15.8.22：文件列表探针预算（每轮封顶）
            _files_budget: List[int] = [max(int(RECOMMEND_FILES_MAX), 0)]
            for t in torrents:
                h = str(getattr(t, "hash", "") or "").lower()
                if not h:
                    continue
                # ★ 15.8.22：凡**有推荐记录**的种（含「已在库」被跳过的）都先用
                #   文件列表校正季/集 —— 否则这些「整季」会永远停在「集数未知」。
                _rec_early = store.get(h)
                _epi_early: Dict[str, Any] = {}
                if _rec_early:
                    _epi_early = self._recommend_episode_probe(
                        downloader, h, str(getattr(t, "title", "") or ""),
                        _rec_early, _files_budget,
                    )
                    if _epi_early:
                        self._recommend_merge_episode(store, h, _rec_early, _epi_early)
                if h in asset:
                    continue
                rec = store.get(h) or {}
                status = rec.get("status")
                # ★ 15.8.22：季/集已在上方按文件列表校正（_epi_early）
                _epi = _epi_early
                if status in ("confirmed", "dismissed", "deleted", "subscribed"):
                    continue
                # 手动保护的种子(无推荐记录)跳过;推荐/待确认由本 worker 管理(才能走到过期删)
                if h in protected and status not in ("recommended", "pending"):
                    continue
                first_seen = float(rec.get("first_seen") or 0) or now
                scanned += 1
                if status == "recommended":
                    # ★ 15.8.22：文件列表证明是**单集**（DepWeb 那类）→ 不计入推荐，转普通（不删）
                    if (str(rec.get("kind") or "") == "single"
                            and str(cfg.get("episode_policy") or "season_first") != "all"):
                        store.set_status(h, "downgraded", note="单集（非整季）→转普通",
                                         downgraded_at=now)
                        to_downgrade.append(h)
                        expired += 1
                        continue
                    if low_disk or (expire_sec > 0 and now - first_seen > expire_sec):
                        # ★ Master 01:17：推荐过期**不删** → **转普通**
                        store.set_status(
                            h, "downgraded",
                            note="磁盘不足→转普通" if low_disk else "过期未确认→转普通",
                            downgraded_at=now,
                        )
                        to_downgrade.append(h)
                        expired += 1
                    continue
                if status == "pending" and rec.get("evaluated_at"):
                    # ★ 15.8.21：老记录缺季/集 → 本地补一次（不打网络）
                    if not rec.get("kind"):
                        _e2 = episode_info(str(rec.get("title") or ""))
                        if _e2.get("kind") and _e2.get("kind") != "movie":
                            try:
                                store.upsert(
                                    h, season=_e2.get("season") or "",
                                    episode=_e2.get("episode") or "",
                                    ep_begin=int(_e2.get("ep_begin") or 0),
                                    ep_end=int(_e2.get("ep_end") or 0),
                                    kind=str(_e2.get("kind") or ""),
                                    group_key=_rec_group_key(
                                        str(rec.get("media_key") or ""), _e2),
                                )
                                rec = store.get(h) or rec
                            except Exception:  # noqa: BLE001
                                pass
                    # ★ 15.8.21：单集在 season_first 下**不升级**为推荐（只做 TTL 复查）
                    if (str(rec.get("kind") or "") == "single"
                            and str(cfg.get("episode_policy") or "season_first") != "all"):
                        if temp_sec > 0 and now - first_seen > temp_sec:
                            store.set_status(h, "downgraded", note="临时种到期→转普通",
                                             downgraded_at=now)
                            to_downgrade.append(h)
                            expired += 1
                        continue
                    # 已评估过:1 口径变化后可能升级为推荐(用已存字段,免重复识别)2 复查 TTL
                    _like = {
                        "recognized": bool(rec.get("media")),
                        "rating": rec.get("rating"),
                        "in_chart": rec.get("in_chart"),
                        "in_subscribe": rec.get("in_subscribe"),
                    }
                    if self._recommend_worth(_like, cfg) and not self._recommend_dup(
                        store, str(rec.get("group_key") or rec.get("media_key") or ""), h,
                        ("recommended", "confirmed")
                    ):
                        store.upsert(
                            h, status="recommended",
                            reason=("评分 %s" % (rec.get("rating") or 0))
                            + ("·在榜" if rec.get("in_chart") else "")
                            + ("·订阅" if rec.get("in_subscribe") else ""),
                        )
                        self._recommend_tag(downloader, task_id, rec_tag, h)
                        if self._store:
                            try:
                                self._store.protect_torrent(task_id, h)
                            except Exception as _pe:  # noqa: BLE001
                                self._log(f"推荐保护失败 {h}: {_pe}", "warning")
                        recommended += 1
                        try:
                            self._recommend_notify(
                                task,
                                SimpleNamespace(
                                    size_gb=rec.get("size_gb"), title=rec.get("title")
                                ),
                                {
                                    "title": (rec.get("media") or {}).get("title")
                                    or rec.get("title"),
                                    "year": (rec.get("media") or {}).get("year"),
                                    "rating": rec.get("rating"),
                                    "in_chart": rec.get("in_chart"),
                                    "in_subscribe": rec.get("in_subscribe"),
                                },
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        continue
                    if temp_sec > 0 and now - first_seen > temp_sec:
                        store.set_status(h, "downgraded", note="临时种到期→转普通",
                                         downgraded_at=now)
                        to_downgrade.append(h)
                        expired += 1
                    continue
                # 首次见到 → 甄别(每轮封顶,分摊识别开销)
                if budget <= 0:
                    continue
                budget -= 1
                evaluated += 1
                info = engine.evaluate(str(getattr(t, "title", "") or ""))
                if _epi:
                    # ★ 15.8.22：文件列表（单集/多集）**覆盖**种名的「整季」判定
                    info = dict(info)
                    for _k in ("kind", "season", "episode", "ep_begin", "ep_end"):
                        if _epi.get(_k) not in (None, ""):
                            info[_k] = _epi[_k]
                media = None
                if info.get("recognized"):
                    media = {
                        "source": info.get("media_source"),
                        "id": info.get("media_id"),
                        "type": info.get("type"),
                        "title": info.get("title"),
                        "year": info.get("year"),
                    }
                base: Dict[str, Any] = {
                    "title": getattr(t, "title", ""),
                    "size_gb": float(getattr(t, "size_gb", 0) or 0),
                    "first_seen": first_seen,
                    "media": media,
                    "poster": info.get("poster") or "",
                    "overview": info.get("overview") or "",
                    "rating": info.get("rating"),
                    "in_chart": bool(info.get("in_chart")),
                    "in_subscribe": bool(info.get("in_subscribe")),
                    # ★ 15.8.21：季/集（单集 vs 整季）
                    "season": str(info.get("season") or ""),
                    "episode": str(info.get("episode") or ""),
                    "ep_begin": int(info.get("ep_begin") or 0),
                    "ep_end": int(info.get("ep_end") or 0),
                    "kind": str(info.get("kind") or ""),
                    "evaluated_at": now,
                }
                media_key = self._recommend_media_key(media, info)
                base["media_key"] = media_key
                base["group_key"] = _rec_group_key(media_key, info)
                # 未识别(非影视/识别不出)→ 不入推荐库
                if not info.get("recognized"):
                    continue
                # 已在影视库 → 不入推荐库(资源已在库,无需跟踪/推荐)
                if self._recommend_in_library(info):
                    continue
                # ★ 15.8.21 单集策略：season_first（默认）下「单集」不自动推荐——
                #   记为普通临时种（受 TTL 回收，**不删**，仍可在「显示全部候选」里手动确认）。
                if (str(info.get("kind") or "") == "single"
                        and str(cfg.get("episode_policy") or "season_first") != "all"):
                    store.upsert(h, status="pending", **base,
                                 reason="单集（非整季）·不自动推荐")
                    if temp_sec > 0 and now - first_seen > temp_sec:
                        store.set_status(h, "downgraded", note="临时种到期→转普通",
                                         downgraded_at=now)
                        to_downgrade.append(h)
                        expired += 1
                    continue
                worth = self._recommend_worth(info, cfg)
                # 同片已有同类记录 → 不重复建档(避免同名多条)
                _dup_statuses = ("recommended", "confirmed") if worth else ("pending",)
                if self._recommend_dup(store, base["group_key"], h, _dup_statuses):
                    continue
                if worth:
                    store.upsert(
                        h, status="recommended", **base,
                        reason=("评分 %.1f" % float(info.get("rating") or 0))
                        + ("·在榜" if info.get("in_chart") else "")
                        + ("·订阅" if info.get("in_subscribe") else ""),
                    )
                    self._recommend_tag(downloader, task_id, rec_tag, h)
                    if self._store:
                        try:
                            self._store.protect_torrent(task_id, h)
                        except Exception as _pe:  # noqa: BLE001
                            self._log(f"推荐保护失败 {h}: {_pe}", "warning")
                    recommended += 1
                    self._recommend_notify(task, t, info)
                else:
                    # 识别出但未达门槛 → 记为临时种(仅供 TTL 回收 + 去重记忆,列表默认不展示)
                    store.upsert(
                        h, status="pending", **base,
                        reason=(f"评分 {info.get('rating')}" if info.get("rating") else "未达门槛"),
                    )
                    if temp_sec > 0 and now - first_seen > temp_sec:
                        store.set_status(h, "downgraded", note="临时种到期→转普通",
                                         downgraded_at=now)
                        to_downgrade.append(h)
                        expired += 1
            # ★ 过期/临时种到期 → **降级转普通**（不再删；Master 01:17）
            if to_downgrade:
                items = []
                for h in to_downgrade:
                    rec2 = store.get(h) or {}
                    _ok = self._recommend_downgrade_one(downloader, h)
                    items.append(OperationItem(
                        hash=h, title=str(rec2.get("title") or ""),
                        size_gb=float(rec2.get("size_gb") or 0),
                        reason=f"推荐过期→静默-普通{'✓' if _ok else '(非静默池:仅摘推荐标签)'}",
                        source="recommend",
                    ))
                self._store.journal.record(task_id=task_id, kind="recommend", items=items)
            if scanned or to_downgrade:
                _prot = len(self._store.get_protected_torrents(task_id)) if self._store else 0
                self._log(
                    f"魔流 [{task.name}] 推荐甄别:扫 {scanned} · 新评估 {evaluated} · "
                    f"新推荐 {recommended} · 过期清理 {expired} · 保护集合 {_prot}"
                    + ("(磁盘不足)" if low_disk else "")
                )
        except Exception as e:  # noqa: BLE001
            import traceback
            logger.error(f"魔流 推荐甄别异常: {e}\n{traceback.format_exc()}")
            self._log(f"魔流 [{task.name}] 推荐甄别异常:{e}", "warning")
        finally:
            self._end_run(task_id)

    def _recommend_tag(self, downloader: DownloaderAdapter, task_id: str,
                       rec_tag: str, h: str) -> bool:
        """给推荐种子补上「推荐」标签(append 语义,不动其它标签)。"""
        try:
            ok = bool(downloader.set_torrent_tags(h, [rec_tag]))
        except Exception as err:  # noqa: BLE001
            self._log(f"推荐标签失败 {h}: {err}", "warning")
            ok = False
        if ok and self._store:
            self._store.journal.record(
                task_id=task_id, kind="tag",
                items=[OperationItem(hash=h, title="",
                                     reason=f"推荐纳管·补标签 {rec_tag}", source="recommend")],
            )
        return ok

    def _recommend_notify(self, task: MagicFlowTaskConfig, torrent: Any, info: Dict[str, Any]) -> None:
        """命中推荐时推送通知(可关)。"""
        if not bool(self._recommend_cfg.get("notify", True)):
            return
        try:
            title = str(info.get("title") or getattr(torrent, "title", "") or "")
            year = info.get("year") or ""
            rating = info.get("rating") or 0
            mark = "在榜" if info.get("in_chart") else ("订阅" if info.get("in_subscribe") else "")
            self.post_message(
                title="魔流·推荐",
                text=(
                    f"发现值得收藏的资源:{title} {year}\n"
                    f"评分 {rating} · {mark}\n"
                    f"体积 {float(getattr(torrent, 'size_gb', 0) or 0):.2f} GB · 任务「{task.name}」\n"
                    f"已打「{self._recommend_cfg.get('tag')}」标签并保护;过期未确认将自动清理。\n"
                    f"在工作台 →「推荐」确认入库,或按需忽略。"
                ),
            )
        except Exception as err:  # noqa: BLE001
            self._log(f"推荐通知发送失败:{err}", "warning")

    @staticmethod
    def _transfer_already_done(msg: Any) -> bool:
        """★ 识别「MP 整理返回的错误其实只是『已整理过』」。

        MP 的 ``TransferChain.manual_transfer`` 对**已经整理过**的文件返回
        ``ok=False`` + ``msg="<文件> 已整理过（成功记录 #N…）、…，等N个文件错误！"``，
        但文件其实早在库里（硬链接都在）→ 应当视作**成功**。
        规则：消息里出现「已整理过」，且拆开后**没有**其它实质错误（忽略「等N个文件错误！」这种汇总）。
        """
        s = str(msg or "").strip()
        if not s or "已整理过" not in s:
            return False
        for _p in re.split(r"[、,，;；]", s):
            _p = _p.strip()
            if not _p or "已整理过" in _p:
                continue
            if re.fullmatch(r"等\s*\d+\s*个文件错误[!！]?", _p):
                continue
            return False
        return True

    def _recommend_import(self, h: str, rec: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """确认后自动整理入库:识别 → 用 TransferChain 手动整理该资源。"""
        try:
            from app.chain.transfer import TransferChain  # type: ignore  # noqa: WPS433
            from app.schemas.file import FileItem  # type: ignore  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return False, f"MoviePilot 整理接口不可用:{err}"
        title = str((rec or {}).get("title") or "")
        torrent = None
        try:
            downloader = self._get_downloader("qbittorrent")
            if downloader and downloader.is_available:
                tl, _err = downloader.get_torrents()
                for t in tl:
                    if str(getattr(t, "hash", "")).lower() == str(h).lower():
                        torrent = t
                        break
        except Exception:  # noqa: BLE001
            torrent = None
        if torrent is not None and not title:
            title = str(getattr(torrent, "title", "") or "")
        if not title:
            return False, "缺少资源标题,无法识别"
        try:
            mi = recognize(title)
        except Exception:  # noqa: BLE001
            mi = None
        if not mi:
            return False, "未能识别媒体信息,无法自动整理"
        save_path = ""
        if torrent is not None:
            # 优先「内容路径」(单种文件 / 多种目录),回退 save_path;
            # 绝不能直接拿共享下载根目录(如 /movie/刷流)去整理。
            save_path = str(
                getattr(torrent, "content_path", "")
                or getattr(torrent, "path", "")
                or getattr(torrent, "save_path", "")
                or ""
            )
        if not save_path:
            return False, "缺少保存路径,无法自动整理"
        try:
            # 下载器给的是宿主机路径,需映射成 MoviePilot(容器)可访问的路径
            save_path = downloader.normalize_path(save_path)
        except Exception:  # noqa: BLE001
            pass
        try:
            import os as _os
            clean = save_path.rstrip("/")
            _is_dir = _os.path.isdir(save_path)
            fileitem = FileItem(
                path=save_path, storage="local", type="dir" if _is_dir else "file",
                name=_os.path.basename(clean) or _os.path.basename(save_path),
            )
            ok, msg = TransferChain().manual_transfer(
                fileitem=fileitem,
                media_source=getattr(mi, "media_source", None),
                media_id=getattr(mi, "media_id", None),
                mtype=getattr(mi, "type", None),
                downloader="qbittorrent",
                download_hash=str(h).lower(),
            )
            _note = ""
            if not ok and self._transfer_already_done(msg):
                # ★ MP 把「已整理过（成功记录 #N）」的重复文件当**错误**返回（ok=False），
                #   但文件早已在库 → 等价成功（Master 2026-09-28 08:19 报的「等39个文件错误」）
                ok = True
                _note = "文件已在库（已整理过）"
            self._log(f"推荐整理「{title}」→ ok={ok} msg={msg}" + (f" [{_note}]" if _note else ""))
            if ok:
                if _note:
                    # MP 对「已整理过」不广播 TransferComplete → 自己补库记（否则转不了「静默-资源」）
                    try:
                        _gidq = self._tag_groups().queue_library(
                            str(h).lower(), media_id=str(getattr(mi, "media_id", "") or ""))
                        if _gidq:
                            self._log(f"库记:整理完成(已整理过) {h[:12]} → 资源 {_gidq[:46]}")
                    except Exception as err:  # noqa: BLE001
                        self._log(f"库记:补写失败(已整理过) {h[:12]}:{err}", "warning")
                # ★ 入库即转「静默-资源」（不等下一轮分拣）
                try:
                    _gid1 = ""
                    try:
                        _gid1 = str((rec or {}).get("group_id") or "")
                    except Exception:  # noqa: BLE001
                        _gid1 = ""
                    if not _gid1:
                        _gid1 = self._tag_groups().group_of(h)
                    self._promote_resource(_gid1)
                except Exception as err:  # noqa: BLE001
                    self._log(f"推荐整理:入库即转失败 {h[:12]}:{err}", "warning")
                # 整理入库后顺带做一次元数据兜底(异步,不阻塞确认请求)
                self._fallback_after_import(str(getattr(mi, "title", "") or title))
            return bool(ok), str(_note or msg)
        except Exception as err:  # noqa: BLE001
            import traceback
            logger.error(f"魔流 推荐整理异常: {err}\n{traceback.format_exc()}")
            return False, f"整理异常:{err}"

    def _run_items(self, summary: Dict[str, Any], duration: float) -> List[OperationItem]:
        """一轮刷流的操作明细:首行摘要 + 逐条「新增 / 复用 / 失败」明细。"""
        items = [OperationItem(
            hash="",
            title=self._run_summary_text(summary),
            reason=f"耗时 {duration:.1f}s",
            source="run",
        )]
        items.extend([it for it in (summary.get("items") or []) if isinstance(it, OperationItem)])
        return items

    @staticmethod
    def _run_summary_text(summary: Dict[str, Any]) -> str:
        """把一轮刷流结果概括成一句话(用于操作流水)。"""
        status = summary.get("status")
        flow = ""
        if summary.get("candidates") is not None:
            flow = f"候选 {summary.get('candidates', 0)}→通过 {summary.get('filtered', 0)} · "
        if status == "done":
            return (
                f"{flow}"
                f"新增 {summary.get('added', 0)} / 复用 {summary.get('reused', 0)}"
                f" / 删除 {summary.get('deleted', 0)} / 当前托管 {summary.get('kept', 0)}"
            )
        if status == "noop":
            return f"{flow}本轮无需动作:{summary.get('reason', '')}"
        if status == "skipped":
            return f"跳过:{summary.get('reason', '')}"
        if status == "failed":
            return f"失败:{summary.get('reason', '')}"
        return "本轮结束"

    # ---------------------------------------------------------
    # API:推荐(刷流种价值生命周期)
    # ---------------------------------------------------------

    def _recommend_backfill_titles(self, limit: int = 200) -> int:
        """★ 补录「资源名」：早期记录里 media 只有 source/id/type/year（没 title），

        列表只能退回显示**种子名**（Master 2026-09-28 07:08 报的问题）。
        这里用推荐引擎（带缓存）重新识别这些条目，把 media.title 补上（后台跑，不阻塞接口）。
        """
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return 0
        n = 0
        try:
            for it in (store.list() or []):
                if n >= int(limit or 0):
                    break
                media = it.get("media") or {}
                if not media.get("id") or media.get("title"):
                    continue
                name = str(it.get("title") or "")
                if not name:
                    continue
                try:
                    info = self._get_recommend_engine().evaluate(name, with_poster=False)
                except Exception:  # noqa: BLE001
                    continue
                if not info.get("title"):
                    continue
                m2 = dict(media)
                m2["title"] = info.get("title")
                m2["year"] = m2.get("year") or info.get("year") or ""
                try:
                    store.upsert(str(it.get("hash") or ""), media=m2)
                except Exception:  # noqa: BLE001
                    continue
                n += 1
        except Exception as err:  # noqa: BLE001
            self._log(f"推荐资源名补录异常:{err}", "warning")
        if n:
            self._log(f"推荐资源名补录 {n} 条")
        return n

    def get_recommend_list(self) -> Response:
        """列出推荐甄别结果(供工作台「推荐」标签页)。"""
        store = getattr(self._store, "recommend", None) if self._store else None
        items = store.list() if store else []
        # 有「缺资源名」的旧记录 → 起后台线程补录（列表接口不阻塞）
        try:
            _miss = sum(1 for i in items
                        if (i.get("media") or {}).get("id") and not (i.get("media") or {}).get("title"))
        except Exception:  # noqa: BLE001
            _miss = 0
        if _miss and not getattr(self, "_rec_backfill_busy", False):
            self._rec_backfill_busy = True

            def _bg() -> None:
                try:
                    self._recommend_backfill_titles(limit=300)
                finally:
                    self._rec_backfill_busy = False

            try:
                threading.Thread(target=_bg, daemon=True).start()
            except Exception:  # noqa: BLE001
                self._rec_backfill_busy = False
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        return Response(success=True, data={
            "enabled": bool(cfg.get("enabled", True)),
            "min_rating": float(cfg.get("min_rating", 7.5) or 0),
            "require_chart": bool(cfg.get("require_chart", True)),
            "expire_days": float(cfg.get("expire_days", 7.0) or 0),
            "temp_ttl_days": float(cfg.get("temp_ttl_days", 7.0) or 0),
            "tag": str(cfg.get("tag") or "魔流-推荐"),
            "auto_import": bool(cfg.get("auto_import", True)),
            "notify": bool(cfg.get("notify", True)),
            "disk_min_free_gb": float(cfg.get("disk_min_free_gb", 50.0) or 0),
            "items": items,
            "total": len(items),
            "recommended": len([i for i in items if i.get("status") == "recommended"]),
        })

    def _recommend_unsubscribe_season(
        self, sid: int, title: str, season: int
    ) -> Tuple[bool, str]:
        """★ 15.8.25：退订「作品+季」（优先按 sub_id，否则按 标题+季 反查）。"""
        try:
            from app.chain.subscribe import SubscribeChain  # noqa: WPS433
            from app.db.oper.subscribe import SubscribeOper  # noqa: WPS433

            if not sid and title:
                try:
                    for sub in (SubscribeOper().list() or []):
                        _t = _norm(getattr(sub, "name", "") or getattr(sub, "title", ""))
                        _s = int(getattr(sub, "season", 0) or 0)
                        if _t and _t == _norm(title) and (not season or not _s or _s == season):
                            sid = int(getattr(sub, "id", 0) or 0)
                            break
                except Exception as err:  # noqa: BLE001
                    logger.warning(f"魔流 订阅反查失败 {title}: {err}")
            if not sid:
                return False, "未找到对应订阅（可能已被 MP 清理）"
            ok = bool(SubscribeChain()._delete_subscription(sid))  # noqa: SLF001
            return (ok, "已退订整季 id=%s" % sid) if ok else (False, "退订失败")
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流 退订失败 {title} S{season}: {err}")
            return False, str(err)

    def subscribe_recommend(self, hash: str) -> Response:
        """★ 15.8.25：**手动**给该记录的「作品+季」加 MP 整季订阅（标记了才订阅，不自动）。

        单集（一集一个文件）如果只有这一集，标它「订阅整季」→ MP 去抓齐其余集并整理到一起。
        """
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return Response(success=False, message="推荐存储不可用")
        rec = store.get(hash) or {}
        if not rec:
            return Response(success=False, message="未找到该推荐记录")
        if str(rec.get("status") or "") == "subscribed":
            return Response(success=True, message="已订阅整季", data=rec)
        sid, msg = self._recommend_subscribe_season(rec, rec.get("media"))
        if not sid:
            return Response(success=False, message=f"订阅失败：{msg}", data=rec)
        store.upsert(
            hash, status="subscribed", subscribed_at=time.time(), sub_id=int(sid or 0),
            reason=("手动 · 已订阅整季（%s）" % (msg or ""))[:80],
            note=("已订阅整季 id=%s" % sid)[:80],
        )
        return Response(success=True, message=f"已订阅整季（{msg}）", data=store.get(hash))

    def unsubscribe_recommend(self, hash: str) -> Response:
        """★ 15.8.25：退订该记录的「作品+季」并把记录复位为待核实（**不动种子**）。"""
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return Response(success=False, message="推荐存储不可用")
        rec = store.get(hash) or {}
        if not rec:
            return Response(success=False, message="未找到该推荐记录")
        ok, msg = self._recommend_unsubscribe_season(
            int(rec.get("sub_id") or 0),
            str((rec.get("media") or {}).get("title") or ""),
            int("".join(ch for ch in str(rec.get("season") or "") if ch.isdigit()) or 0),
        )
        store.upsert(hash, status="pending", sub_id=0, subscribed_at=0,
                     reason="单集（非整季）·不自动推荐", note=msg[:80])
        return Response(success=ok, message=msg, data=store.get(hash))

    def confirm_recommend(self, hash: str) -> Response:
        """确认推荐:标记 confirmed;开启自动入库时尝试整理入库。"""
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return Response(success=False, message="推荐存储不可用")
        rec = store.get(hash)
        if not rec:
            return Response(success=False, message="未找到该推荐记录")
        store.set_status(hash, "confirmed", confirmed_at=time.time())
        msg = "已确认"
        if bool(self._recommend_cfg.get("auto_import", True)):
            ok, imsg = self._recommend_import(hash, rec)
            msg = "已确认并提交整理入库" if ok else f"已确认;自动整理未成功:{imsg}"
            if ok:
                store.upsert(hash, import_result=str(imsg)[:200])
        return Response(success=True, message=msg, data=store.get(hash))

    def dismiss_recommend(self, hash: str) -> Response:
        """忽略推荐:删除该资源(不入影视库)。"""
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return Response(success=False, message="推荐存储不可用")
        rec = store.get(hash)
        if not rec:
            return Response(success=False, message="未找到该推荐记录")
        ok, err = True, None
        try:
            downloader = self._get_downloader("qbittorrent")
            if downloader and downloader.is_available:
                n, err = downloader.delete_torrents(hashes=[hash], delete_file=True)
                ok = bool(n)
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
        store.set_status(hash, "dismissed", note="手动忽略")
        if self._store:
            self._store.journal.record(
                task_id="", kind="recommend",
                items=[OperationItem(hash=hash, title=str(rec.get("title") or ""),
                                     reason="忽略并删除", source="recommend")],
            )
        return Response(success=bool(ok),
                        message="已忽略并删除" if ok else f"已忽略;删除失败:{err}")

    def import_recommend(self, hash: str) -> Response:
        """手动触发整理入库。"""
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return Response(success=False, message="推荐存储不可用")
        rec = store.get(hash)
        if not rec:
            return Response(success=False, message="未找到该推荐记录")
        ok, msg = self._recommend_import(hash, rec)
        if ok:
            store.upsert(hash, status="confirmed", confirmed_at=time.time(),
                         import_result=str(msg)[:200])
        return Response(success=ok, message=msg)

    def import_recommend_batch(self, hashes: str = "", all: str = "", status: str = "") -> Response:
        """★ **批量整理入库**（Master 2026-09-28 07:00：「批量入库的功能加一下」）。

        - ``hashes``：逗号分隔的种子 hash（工作台勾选的）；
        - ``all=1``：把当前所有**待确认**（``recommended``）记录一起入库；``status=pending`` 可把「待核实」也带上；
        - 逐个走 ``_recommend_import``（识别 → TransferChain 手动整理），单个失败不影响其余。
        Python 侧参数从 **query string** 取（MP 插件 API 的 POST 不吃 JSON body）。
        """
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return Response(success=False, message="推荐存储不可用")
        want: List[str] = [h.strip().lower() for h in str(hashes or "").replace(" ", "").split(",") if h.strip()]
        # `all=1` 默认只收「真·待确认(recommended)」；要连「待核实(pending)」一起，显式传 status=pending
        _want_status = {x.strip().lower() for x in str(status or "").split(",") if x.strip()} or {"recommended"}
        if not want and str(all or "").strip().lower() in ("1", "true", "yes", "on"):
            for it in (store.list() or []):
                _st = str(it.get("status") or "").lower()
                if _st in _want_status:
                    _h = str(it.get("hash") or "").strip().lower()
                    if _h:
                        want.append(_h)
        # 去重保序
        _seen: set = set()
        want = [h for h in want if not (h in _seen or _seen.add(h))]
        if not want:
            return Response(success=False, message="没有可入库的推荐（未勾选，或没有待确认项）")
        ok_n, fail_n = 0, 0
        details: List[Dict[str, Any]] = []
        for h in want:
            rec = store.get(h)
            if not rec:
                fail_n += 1
                details.append({"hash": h, "ok": False, "message": "未找到推荐记录"})
                continue
            try:
                ok, msg = self._recommend_import(h, rec)
            except Exception as err:  # noqa: BLE001
                ok, msg = False, f"整理异常:{err}"
            if ok:
                ok_n += 1
                store.upsert(h, status="confirmed", confirmed_at=time.time(), import_result=str(msg)[:200])
            else:
                fail_n += 1
                store.upsert(h, import_result=str(msg)[:200])
            details.append({"hash": h, "ok": bool(ok), "title": str(rec.get("title") or ""), "message": str(msg)[:200]})
        # 操作记录（推荐类，task_id 空 = 全局）
        try:
            self._store.journal.record(
                task_id="", kind="recommend",
                items=[OperationItem(hash=d["hash"], title=str(d.get("title") or d["hash"]),
                                     reason=("批量入库：" + str(d.get("message") or "")),
                                     source="recommend", tags=("ok" if d["ok"] else "fail"))
                       for d in details],
            )
        except Exception:  # noqa: BLE001
            pass
        self._log(f"批量入库：成功 {ok_n} · 失败 {fail_n}（共 {len(want)}）")
        return Response(
            success=ok_n > 0,
            message=f"批量入库：成功 {ok_n} · 失败 {fail_n}（共 {len(want)}）",
            data={"ok": ok_n, "failed": fail_n, "total": len(want), "details": details},
        )
