# -*- coding: utf-8 -*-
"""魔流 · cleanup —— 清理执行（低效种删除，唯一删除入口之一）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


from ..bonus import (
    aggregate_breakdown,
    decide_deletions,
)
from ..downloader_ops import (
    DownloaderAdapter,
    TorrentInfo,
    QB_DOWNLOADING_STATES,
)
from ..persistence import OperationItem
from ..sites.formula_fetch import (
    _norm_title as normalize_title,
)


from ..common import (
    MEDIA_ASSET_TAGS,
    MagicFlowTaskConfig,
)


class CleanupMixin:
    """cleanup 功能集（原 MagicFlow 方法原样搬入）。"""

    def _cleanup_round(self, task: MagicFlowTaskConfig, downloader: DownloaderAdapter) -> Dict[str, Any]:
        """清理一轮:自动恢复暂停做种 + 清理无进度种子 + 删除低效种子。

        抽出供两处复用:
          - ``_brush_impl``:放在**入口检查之前**(池满时先清理腾空间,再决定抓取);
          - ``_run_check_impl``:独立的 check 任务。

        返回计数 {resumed, no_progress, low_eff, deleted, kept, total_before, total_after}。
        """
        out: Dict[str, Any] = {
            "resumed": 0, "no_progress": 0, "slow": 0, "unfree": 0, "no_upload": 0, "low_eff": 0, "deleted": 0,
            "kept": 0, "total_before": 0.0, "total_after": 0.0,
        }
        if not downloader or not downloader.is_available:
            return out
        protected = self._store.get_protected_torrents(task.id) if self._store else set()
        _is_brush = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"

        # 把「保护 / 同站纳管」记录与下载器真实种子对齐:已从下载器消失的种子会留下陈旧
        # hash(历史误删 / 手动删除),导致「受保护」计数虚高、同一资源不再被重新纳管。
        if self._store:
            try:
                live_all, _live_err = downloader.get_torrents()
                if live_all:
                    cleaned = self._store.reconcile_protected(
                        task.id, [(t.hash or "") for t in live_all if t.hash]
                    )
                    if cleaned:
                        self._log(f"魔流 [{task.name}] 清理陈旧保护/纳管记录 {cleaned} 条")
                        protected = self._store.get_protected_torrents(task.id)
            except Exception as _rec_err:
                self._log(f"魔流 [{task.name}] 保护记录校准失败: {_rec_err}", "warning")

        # ★ 本任务名下的种：站点×职务（标签/归属已退役），只清理本站本职务的种
        all_tagged: List[Any] = self._task_managed_torrents(task)
        _tag_err = None

        # ★ 媒体资产价值闸门:把「已整理 / 辅种 / 下载历史命中」的种子并入保护集合,
        #   本轮所有清理(无进度 / 过慢 / 非免费 / 无上传 / 到期 / 低效)都跳过它们。
        try:
            _asset_hashes = self._media_asset_hashes(list(all_tagged or []), task)
            if _asset_hashes:
                protected = set(protected) | set(_asset_hashes)
                self._dbg(
                    f"[{task.name}] 媒体资产保护 {len(_asset_hashes)} 个"
                    f"(标签 {'/'.join(MEDIA_ASSET_TAGS)} 或命中下载历史)"
                )
        except Exception as _asset_err:
            self._log(f"魔流 [{task.name}] 媒体资产保护计算失败: {_asset_err}", "warning")

        # ★ 跨站来源份（H&R 保种期内）：它们是**别的站点**的保种责任种，
        #   不是本任务的资产，但绝不能被本任务（或任何任务）删掉。
        try:
            _cs_src = self._crossseed_source_hashes()
            if _cs_src:
                protected = set(protected) | set(_cs_src)
                self._dbg(f"[{task.name}] 跨站来源份 H&R 保护 {len(_cs_src)} 个")
        except Exception as _cs_err:  # noqa: BLE001
            self._log(f"魔流 [{task.name}] 跨站来源份保护计算失败: {_cs_err}", "warning")

        # 看门狗:与上一轮对比,检测「种子还在、标签却被抹掉」(托管骤降但本轮无删种)
        if not _tag_err:
            try:
                self._watch_tag_integrity(task, len(all_tagged or []))
            except Exception as _wd_err:
                self._log(f"魔流 [{task.name}] 标签看门狗异常: {_wd_err}", "warning")

        # 1 自动恢复被暂停的已完成种子(暂停 → tracker 不计做种 → 0 产出)
        if getattr(task, "auto_resume_paused", True) and all_tagged:
            try:
                out["resumed"] = self._resume_paused_managed(task, downloader, list(all_tagged))
            except Exception as _resume_err:
                self._log(f"魔流 [{task.name}] 自动恢复暂停种子异常: {_resume_err}", "warning")

        # 2 清理「没进度」的种子(进度为 0 且停滞/出错/暂停,挂了够久)
        if all_tagged:
            try:
                np_deleted, _np_removed = self._cleanup_no_progress(
                    task, downloader, list(all_tagged), protected
                )
                out["no_progress"] = np_deleted
            except Exception as _cleanup_err:
                self._log(f"魔流 [{task.name}] 清理无进度种子异常: {_cleanup_err}", "warning")

        # 2b 清理「下载过慢」的种子(用「下载速度 ÷ 体积」估算 ETA,长期下不完的腾名额)
        #     刷流模式不做:刷流只要「有上传」就保留,哪怕下得慢(没完整下完也会有上传)。
        if all_tagged and not _is_brush:
            try:
                slow_deleted, _slow_removed = self._cleanup_slow_progress(
                    task, downloader, list(all_tagged), protected
                )
                out["slow"] = slow_deleted
            except Exception as _slow_err:
                self._log(f"魔流 [{task.name}] 清理过慢种子异常: {_slow_err}", "warning")

        # 2c 清理「促销失效」的种子(下载中但站点已不再免费 → 删,避免白拉流量)
        if all_tagged and getattr(task, "purge_unfree_incomplete", True):
            try:
                out["unfree"] = self._cleanup_unfree_incomplete(
                    task, downloader, list(all_tagged), protected
                )
            except Exception as _unfree_err:
                self._log(f"魔流 [{task.name}] 清理「已非免费」种子异常: {_unfree_err}", "warning")

        # 2d 刷流模式:清理到期/无上传的托管种
        #    设计:**下载中**的种过了宽限期后,每次 check(每 check_interval 分钟)都按上传速率
        #    考核,连续 need 次「无上传」即杀(它们要一直上传才能活过整个下载周期);
        #    **已下完**的种走「满 brush_seed_days 天」轮换(挂种 N 天换新)。
        #    brush_seed_days=0 时回退:不分状态,统一按「无上传」判定。
        if _is_brush:
            _seed_days = int(getattr(task, "brush_seed_days", 0) or 0)
            if all_tagged:
                try:
                    # ★ 产出换种优先:单种已上传/分享率达标 → 换新(先于时间/无上传判定)
                    out["rotated"] = self._cleanup_rotated(
                        task, downloader, list(all_tagged), protected
                    )
                    # 本轮流转掉的(已达产出阈值)不再参与时间/无上传判定,避免重复处理
                    _still = [t for t in all_tagged if not self._rotate_reason(task, t)]
                    if _seed_days > 0:
                        # 下载中:上传考核(每 check 一次,无上传即杀)
                        _incomplete = [
                            t for t in _still
                            if float(getattr(t, "progress", 0) or 0) < 0.999
                        ]
                        # 已下完:满 N 天轮换
                        _complete = [
                            t for t in _still
                            if float(getattr(t, "progress", 0) or 0) >= 0.999
                        ]
                        out["no_upload"] = self._cleanup_no_upload(
                            task, downloader, _incomplete, protected
                        )
                        out["aged"] = self._cleanup_aged(
                            task, downloader, _complete, protected
                        )
                    else:
                        # 未设天数:不分状态统一按「无上传」判定
                        out["no_upload"] = self._cleanup_no_upload(
                            task, downloader, _still, protected
                        )
                except Exception as _nu_err:
                    self._log(f"魔流 [{task.name}] 刷流清理异常: {_nu_err}", "warning")
            # 刷流模式不套用魔力门槛删种;直接收尾返回。
            try:
                _st, _st_err = downloader.get_seeding_torrents(tag=task.brush_tag)
            except Exception:
                _st = []
            _tt = [t for t in (_st or []) if task.brush_tag in t.tags]
            _aged = int(out.get("aged", 0))
            _noupl = int(out.get("no_upload", 0))
            _rot = int(out.get("rotated", 0))
            out["deleted"] = int(out["no_progress"]) + _aged + _noupl + _rot
            out["kept"] = len(_tt)
            self._log(
                f"魔流 [{task.name}] 刷流完成:"
                f"恢复 {out['resumed']} / 无进度 {out['no_progress']} / 到期 {_aged} / 产出 {_rot} / 无上传 {_noupl};"
                f"保留 {out['kept']} 个"
            )
            return out

        # 3 删低效种子(零魔 / 做种人数过多 / 低于门槛 / 超保种上限)
        try:
            seeding_torrents, error = downloader.get_seeding_torrents(tag=task.brush_tag)
        except Exception as _seed_exc:
            seeding_torrents, error = [], str(_seed_exc)
        if error or not seeding_torrents:
            self._log(f"做种列表为空或获取失败: {error}", "warning")
            return out

        task_torrents = [t for t in seeding_torrents if task.brush_tag in t.tags]
        if not task_torrents:
            self._log(f"任务 [{task.name}] 没有管理的种子", "info")
            return out

        torrent_bonus_list = self._convert_to_bonus_list(
            task_torrents,
            self._build_formula_params(task),
            self._task_pub_dates(task),
            getattr(task, "ti_source", "publish"),
            self._site_ni_map(task.site_id, task_torrents),
            self._site_official_titles(task.site_id),
        )
        policy = self._build_magic_policy(task, torrent_bonus_list)
        result = decide_deletions(
            seeding_torrents=torrent_bonus_list,
            policy=policy,
            protected_hashes=protected,
        )

        deleted_count = 0
        if result.to_delete:
            delete_hashes = [d.torrent.hash for d in result.to_delete]
            success_count, error = downloader.delete_torrents(
                hashes=delete_hashes,
                delete_file=task.delete_files,
            )
            deleted_count = success_count
            if self._store:
                operation_items = [
                    OperationItem(
                        hash=d.torrent.hash,
                        title=d.torrent.title,
                        reason=d.reason,
                        bonus_per_hour=d.torrent.bonus_per_hour,
                    )
                    for d in result.to_delete[:success_count]
                ]
                self._store.journal.record(
                    task_id=task.id,
                    kind="deletion",
                    items=operation_items,
                )
                # 已删种子从「保护 / 同站纳管」集合中清理,避免陈旧 hash 虚高计数
                self._store.forget_torrents(task.id, delete_hashes[: max(0, int(success_count or 0))])

        out["low_eff"] = deleted_count
        out["deleted"] = int(out["no_progress"]) + int(out["slow"]) + deleted_count
        out["kept"] = len(result.to_keep)
        # ★ 站点口径合计时魔(对合计 A 只取一次 arctan + 做种固定奖励),使数值与站点上报对齐。
        # 原来把每颗种子各自的时魔简单相加 → 漏掉「做种数 × 每种子」固定奖励,只有站点值的 ~1/3。
        # 「做种固定奖励」按**站点账号去重后的做种数**计(非本任务托管数),否则会比站点整号值偏低。
        try:
            _agg_params = self._build_formula_params(task)
            try:
                _harem_hourly = float((self._site_reported(task) or {}).get("harem_hourly") or 0.0)
            except Exception:
                _harem_hourly = 0.0
            _deleted_hashes = {d.torrent.hash for d in result.to_delete}
            _kept_list = [t for t in torrent_bonus_list if t.hash not in _deleted_hashes]
            _site_seed_count = self._site_seeding_count(task.site_id)
            _before_count = _site_seed_count or len(torrent_bonus_list)
            _after_count = max(_site_seed_count - len(result.to_delete), 0) if _site_seed_count else len(_kept_list)
            out["total_before"] = aggregate_breakdown(
                torrent_bonus_list, _agg_params,
                seeding_count=_before_count, harem_hourly=_harem_hourly,
            )["total"]
            out["total_after"] = aggregate_breakdown(
                _kept_list, _agg_params,
                seeding_count=_after_count, harem_hourly=_harem_hourly,
            )["total"]
        except Exception as _agg_err:
            self._log(f"魔流 [{task.name}] 站点口径时魔汇总失败,回落逐种相加:{_agg_err}", "warning")
            out["total_before"] = result.total_bonus_before
            out["total_after"] = result.total_bonus_after
        self._log(
            f"魔流 [{task.name}] 完成:"
            f"恢复 {out['resumed']} / 无进度 {out['no_progress']} / 过慢 {out['slow']} / 低效 {deleted_count};"
            f"保留 {out['kept']} 个,"
            f"站点口径时魔 {out['total_before']:.2f} -> {out['total_after']:.2f}/h"
        )
        return out

    def _cleanup_no_upload(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> int:
        """刷流模式:清理「无上传」的种子,返回删除数。

        每次检查比对 uploaded 增量:连续 ``need`` 次平均上传速率 < ``upload_min_kbps`` → 判定「无上传」→ 删。
        * 新种在 ``brush_grace_minutes`` 宽限期内不判(给起步时间);
        * 「没完整下完也会有上传」:只看上传,不管进度/速度;
        * protected / 手动保留的种子只记录快照、永不删。
        """
        if not managed:
            return 0
        protected_hashes = protected_hashes or set()
        now = time.time()
        need, thr, grace = self._brush_idle_params(task)

        prev = self._store.get_brush_upload(task.id) if self._store else {}
        new_state: Dict[str, dict] = {}
        to_delete: List[TorrentInfo] = []
        for t in managed:
            h = (t.hash or "").lower()
            if not h:
                continue
            try:
                up = float(getattr(t, "uploaded", 0) or 0)
            except (TypeError, ValueError):
                up = 0.0
            if h in protected_hashes:
                new_state[h] = {"up": up, "idle": 0, "ts": now}
                continue
            try:
                added = float(getattr(t, "added_on", 0) or 0)
            except (TypeError, ValueError):
                added = 0.0
            age = (now - added) if added > 0 else 0.0
            p = prev.get(h)
            if p is None:
                new_state[h] = {"up": up, "idle": 0, "ts": now}
                continue
            delta = up - float(p.get("up", 0) or 0)
            idle = int(p.get("idle", 0) or 0)
            idle = 0 if delta >= thr else idle + 1
            new_state[h] = {"up": up, "idle": idle, "ts": now}
            if added > 0 and age < grace:
                continue
            if idle >= need:
                to_delete.append(t)

        deleted = 0
        if to_delete:
            hashes = [t.hash for t in to_delete if t.hash]
            try:
                success, error = downloader.delete_torrents(
                    hashes=hashes, delete_file=bool(getattr(task, "delete_files", True))
                )
            except Exception:
                success, error = 0, "删除异常"
            deleted = int(success or 0)
            if deleted and self._store:
                items = [
                    OperationItem(
                        hash=t.hash,
                        title=str(getattr(t, "title", "") or ""),
                        reason="刷流:无上传",
                        bonus_per_hour=0.0,
                    )
                    for t in to_delete[:deleted]
                ]
                self._store.journal.record(task_id=task.id, kind="deletion", items=items)
                self._store.forget_torrents(task.id, [t.hash for t in to_delete[:deleted]])
                for t in to_delete[:deleted]:
                    new_state.pop((t.hash or "").lower(), None)
            _ci = max(int(getattr(task, "check_interval", 1) or 1), 1) * 60
            _kbps = int(round(thr / 1024 / _ci)) if _ci else 0
            self._log(
                f"魔流 [{task.name}] 刷流清理「无上传」种子 {deleted} 个"
                f"(连续 {need} 次检查平均上传 < {_kbps} KB/s)"
            )
        if self._store:
            self._store.set_brush_upload(task.id, new_state)
        return deleted

    def _cleanup_aged(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> int:
        """刷流模式:已下完的种子按做种时长满 ``brush_seed_days`` 天清理(轮换腾位),返回删除数。

        * **只处理已下完的种**(progress>=0.999);未下完的交给「无上传」判定(_cleanup_no_upload)。
        * 完成种按**做种时长**(qB seeding_time)计;拿不到时用「加入下载器时长」兜底。
        * protected / 手动保留的种子只记录快照、永不删。
        保种期内(< 天数)一律保留,不按上传速率判。
        """
        days = int(getattr(task, "brush_seed_days", 0) or 0)
        if days <= 0 or not managed:
            return 0
        thr = days * 86400
        now = time.time()
        protected_hashes = protected_hashes or set()

        to_delete: List[TorrentInfo] = []
        for t in managed:
            h = (t.hash or "").lower()
            if not h or h in protected_hashes:
                continue
            try:
                seed_secs = float(getattr(t, "seed_time", 0) or 0)
            except (TypeError, ValueError):
                seed_secs = 0.0
            try:
                added = float(getattr(t, "added_on", 0) or 0)
            except (TypeError, ValueError):
                added = 0.0
            try:
                prog = float(getattr(t, "progress", 0) or 0)
            except (TypeError, ValueError):
                prog = 0.0
            age = (now - added) if added > 0 else 0.0
            if prog >= 0.999:
                eff = seed_secs if seed_secs > 0 else age
            else:
                eff = age
            if eff >= thr:
                to_delete.append(t)

        deleted = 0
        if to_delete:
            hashes = [t.hash for t in to_delete if t.hash]
            try:
                success, error = downloader.delete_torrents(
                    hashes=hashes, delete_file=bool(getattr(task, "delete_files", True))
                )
            except Exception:
                success, error = 0, "删除异常"
            deleted = int(success or 0)
            if deleted and self._store:
                items = [
                    OperationItem(
                        hash=t.hash,
                        title=str(getattr(t, "title", "") or ""),
                        reason=f"刷流:做种满 {days} 天",
                        bonus_per_hour=0.0,
                    )
                    for t in to_delete[:deleted]
                ]
                self._store.journal.record(task_id=task.id, kind="deletion", items=items)
                self._store.forget_torrents(task.id, [t.hash for t in to_delete[:deleted]])
            self._log(
                f"魔流 [{task.name}] 刷流清理「做种满 {days} 天」种子 {deleted} 个"
            )
        return deleted

    @staticmethod
    def _rotate_reason(task: MagicFlowTaskConfig, t: TorrentInfo) -> Optional[str]:
        """单种是否达到「产出换种」阈值(返回理由,未达标返回 None)。"""
        try:
            up_gb = float(getattr(task, "rotate_upload_gb", None) or 0.0)
        except (TypeError, ValueError):
            up_gb = 0.0
        try:
            ratio_thr = float(getattr(task, "rotate_ratio", None) or 0.0)
        except (TypeError, ValueError):
            ratio_thr = 0.0
        if up_gb <= 0 and ratio_thr <= 0:
            return None
        try:
            uploaded = float(getattr(t, "uploaded", 0) or 0)
        except (TypeError, ValueError):
            uploaded = 0.0
        try:
            ratio = float(getattr(t, "ratio", 0) or 0)
        except (TypeError, ValueError):
            ratio = 0.0
        if up_gb > 0 and uploaded >= up_gb * (1024 ** 3):
            return f"刷流:单种上传达标 {uploaded / (1024 ** 3):.1f} GB"
        if ratio_thr > 0 and ratio >= ratio_thr:
            return f"刷流:分享率达标 {ratio:.2f}"
        return None

    def _cleanup_rotated(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> int:
        """刷流模式:按「产出」换种 -- 单种已上传 ≥ ``rotate_upload_gb`` GB 或 分享率 ≥ ``rotate_ratio`` → 清理换新。

        * 只作用于纯刷流临时种;protected / 资产闸门命中的种子永不删。
        * 两个阈值都留空时不做任何事(返回 0)。
        """
        if not managed:
            return 0
        protected_hashes = protected_hashes or set()
        to_delete: List[TorrentInfo] = []
        reasons: Dict[str, str] = {}
        for t in managed:
            h = (t.hash or "").lower()
            if not h or h in protected_hashes:
                continue
            reason = self._rotate_reason(task, t)
            if reason:
                to_delete.append(t)
                reasons[h] = reason
        if not to_delete:
            return 0
        deleted = 0
        hashes = [t.hash for t in to_delete if t.hash]
        try:
            success, error = downloader.delete_torrents(
                hashes=hashes, delete_file=bool(getattr(task, "delete_files", True))
            )
        except Exception:
            success, error = 0, "删除异常"
        deleted = int(success or 0)
        if deleted and self._store:
            items = [
                OperationItem(
                    hash=t.hash,
                    title=str(getattr(t, "title", "") or ""),
                    reason=reasons.get((t.hash or "").lower(), "刷流:产出换新"),
                    bonus_per_hour=0.0,
                )
                for t in to_delete[:deleted]
            ]
            self._store.journal.record(task_id=task.id, kind="deletion", items=items)
            self._store.forget_torrents(task.id, [t.hash for t in to_delete[:deleted]])
        _sample = next(iter(reasons.values()), "")
        self._log(
            f"魔流 [{task.name}] 刷流清理「产出达标换新」种子 {deleted} 个"
            + (f"(如:{_sample})" if _sample else "")
        )
        return deleted

    def _cleanup_no_progress(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> Tuple[int, List[TorrentInfo]]:
        """清理「没进度」的种子,返回 (删除数量, 被删种子列表)。"""
        if not task.cleanup_no_progress or not managed:
            return 0, []
        protected_hashes = protected_hashes or set()
        now = time.time()
        dead = [
            t for t in managed
            if t.hash and t.hash not in protected_hashes and self._is_no_progress(t, task, now)
        ]
        if not dead:
            return 0, []
        hashes = [t.hash for t in dead]
        deleted, err = downloader.delete_torrents(hashes=hashes, delete_file=task.delete_files)
        if deleted <= 0:
            if err:
                self._log(f"魔流 [{task.name}] 清理无进度种子失败:{err}", "warning")
            return 0, []
        removed = dead[:deleted]
        for t in removed:
            self._dead_hashes[(t.hash or "").lower()] = now
        if self._store:
            self._store.dead.mark(
                task.id,
                [f"hash:{(t.hash or '').lower()}" for t in removed if t.hash],
                ts=now,
            )
            self._store.journal.record(
                task_id=task.id,
                kind="deletion",
                items=[
                    OperationItem(hash=t.hash, title=t.title, reason="无进度(停滞)", bonus_per_hour=0.0)
                    for t in removed
                ],
            )
            self._store.forget_torrents(task.id, [t.hash for t in removed])
        self._log(
            f"魔流 [{task.name}] 清理无进度种子 {deleted} 个"
            f"(进度为 0 且 {task.no_progress_minutes} 分钟未动)"
        )
        return deleted, removed

    def _is_too_slow(self, torrent: TorrentInfo, task: MagicFlowTaskConfig, now: float) -> bool:
        """判断种子是否「下载过慢」(用「下载速度 ÷ 体积」估算)。

        口径(Master 指定):value = 下载速度 / 体积 → 每小时完成比例,
        再算 ETA = 剩余比例 / value;超过 slow_progress_max_hours 小时才下得完 → 过慢。

        只判「正在下载」的种子(paused 的交给自动恢复/无进度规则,不在此列):
          - 加入不足 slow_progress_grace_minutes 分钟的新种不判(给新种起步时间);
          - 速度为 0(含 stalledDL)= 完全不动 → 过慢;
          - 否则按 ETA 超过阈值 → 过慢。
        """
        try:
            state = str(getattr(torrent, "state", "") or "").strip().lower()
            size = float(getattr(torrent, "size", 0) or 0)
            progress = float(getattr(torrent, "progress", 0) or 0)
            added_on = float(getattr(torrent, "added_on", 0) or 0)
            speed = float(getattr(torrent, "download_speed", 0) or 0)
        except (TypeError, ValueError):
            return False
        if state not in QB_DOWNLOADING_STATES:
            return False
        if size <= 0:
            return False
        grace = max(int(getattr(task, "slow_progress_grace_minutes", 60) or 60), 1) * 60
        if added_on > 0 and (now - added_on) < grace:
            return False
        remaining_ratio = max(1.0 - min(max(progress, 0.0), 1.0), 0.0)
        if remaining_ratio <= 0:
            return False
        if speed <= 0:
            return True
        max_hours = float(getattr(task, "slow_progress_max_hours", 48.0) or 48.0)
        rate_per_hour = speed / size * 3600.0  # 「速度 ÷ 体积」→ 每小时完成比例
        eta_hours = remaining_ratio / rate_per_hour if rate_per_hour > 0 else float("inf")
        return eta_hours > max_hours

    def _cleanup_slow_progress(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> Tuple[int, List[TorrentInfo]]:
        """清理「下载过慢」的种子(速度÷体积 → ETA 超过阈值),返回 (删除数, 列表)。

        过慢种子长期霸占下载名额、把入口堵死 → 清掉腾位,并记 dead 防止下轮重复选到。
        """
        if not getattr(task, "cleanup_slow_progress", True) or not managed:
            return 0, []
        protected_hashes = protected_hashes or set()
        now = time.time()
        slow = [
            t for t in managed
            if t.hash and t.hash not in protected_hashes and self._is_too_slow(t, task, now)
        ]
        if not slow:
            return 0, []
        deleted, err = downloader.delete_torrents(
            hashes=[t.hash for t in slow], delete_file=task.delete_files
        )
        if deleted <= 0:
            if err:
                self._log(f"魔流 [{task.name}] 清理过慢种子失败:{err}", "warning")
            return 0, []
        removed = slow[:deleted]
        for t in removed:
            self._dead_hashes[(t.hash or "").lower()] = now
        if self._store:
            self._store.dead.mark(
                task.id,
                [f"hash:{(t.hash or '').lower()}" for t in removed if t.hash],
                ts=now,
            )
            self._store.journal.record(
                task_id=task.id,
                kind="deletion",
                items=[
                    OperationItem(hash=t.hash, title=t.title, reason="下载过慢(占名额)", bonus_per_hour=0.0)
                    for t in removed
                ],
            )
            self._store.forget_torrents(task.id, [t.hash for t in removed])
        self._log(
            f"魔流 [{task.name}] 清理下载过慢种子 {deleted} 个"
            f"(速度÷体积估算 > {float(getattr(task, 'slow_progress_max_hours', 48.0) or 48.0):g}h 才下完)"
        )
        return deleted, removed

    def _promo_guard_on(self) -> bool:
        """★ 流量兜底**总开关**（docs/MODULES.md X2）。

        一个系统、三条证据，共用这一个开关：
          ① 任务内回种子详情页核对促销（`purge_unfree_incomplete`）
          ② 全局用站点「正在下载」列表核对（`live_kill_unfree`）
          ③ 跨站取种期间核对来源站（`crossseed_guard`）
        关掉它 = 三条证据全部停用（只告警、不动手）。
        """
        return bool(getattr(self, "_live_cfg", {}).get("promo_guard", True))

    def _cleanup_unfree_incomplete(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> int:
        """清理「已不再免费且尚未下完」的种子,返回删除数。

        逐个回站点详情页核对「下载中」种子的当前促销:已非全免(促销过期 / 本来非免费)
        → 删除,避免白拉流量拉低分享率。「unknown」(拿不到页面/无法解析)时**保守跳过**,不误删。
        """
        if (
            not self._promo_guard_on()
            or not getattr(task, "purge_unfree_incomplete", True)
            or not managed
            or not downloader
        ):
            return 0
        protected_hashes = protected_hashes or set()
        site = self._get_site(task.site_id) if getattr(task, "site_id", 0) else None
        pages = dict(self._store.get_torrent_pages(task.id) if self._store else {})
        if self._store:
            for h, u in self._seen_page_pairs(task.id).items():
                pages.setdefault(h, u)
        mode = (getattr(task, "freeleech", "") or "").strip().lower()
        acceptable = {"2xfree"} if mode == "2xfree" else {"free", "2xfree"}

        # 兜底:缺失详情页链接的「下载中」种子 → 用站点「我的种子」列表按标题回填 URL
        need = [
            t for t in managed
            if (t.hash or "").lower() and (t.hash or "").lower() not in protected_hashes
            and (t.hash or "").lower() not in pages
            and float(getattr(t, "progress", 0) or 0) < 0.999
        ]
        if need and site:
            umap = self._title_url_map(task, site)
            for t in need:
                u = umap.get(normalize_title(t.title or ""))
                if u:
                    pages[(t.hash or "").lower()] = u

        pending: List[Tuple[TorrentInfo, str]] = []
        now_ts = time.time()
        free_until_map = dict(self._store.get_torrent_free_until(task.id) if self._store else {})
        recorded_hits = 0
        for t in managed:
            h = (t.hash or "").lower()
            if not h or h in protected_hashes:
                continue
            # 只处理「还没下完」的种子(已完成/做种中的交给魔力规则管)
            if float(getattr(t, "progress", 0) or 0) >= 0.999:
                continue
            if self._is_dead_cached(task.id, h):
                continue
            # ★ 优先用入种时记下的「促销到期时刻」:到点直接清(免回详情页);未到期则确认仍有效 → 也不必回详情页。
            _fu = float(free_until_map.get(h) or 0.0)
            if _fu > 0:
                if now_ts >= _fu:
                    recorded_hits += 1
                    pending.append(
                        (t, "记录到期 " + time.strftime("%m-%d %H:%M", time.localtime(_fu)))
                    )
                continue
            page = pages.get(h) or ""
            if not page:
                continue
            info = self._promotion_of(task, site, h, page)
            promo = info.get("promotion")
            if promo == "unknown":
                self._log(
                    f"魔流 [{task.name}] 促销核对失败(跳过):{t.title}"
                    f"({info.get('error') or '无标题区'})",
                    "info",
                )
                continue
            if promo in acceptable:
                continue
            pending.append((t, str(info.get("raw") or promo)))

        if not pending:
            return 0
        deleted, err = downloader.delete_torrents(
            hashes=[t.hash for t, _ in pending], delete_file=task.delete_files
        )
        if deleted <= 0:
            if err:
                self._log(f"魔流 [{task.name}] 清理「已非免费」种子失败:{err}", "warning")
            return 0
        removed = pending[:deleted]
        now = time.time()
        for t, _ in removed:
            self._dead_hashes[(t.hash or "").lower()] = now
        if self._store:
            self._store.dead.mark(
                task.id,
                [f"hash:{(t.hash or '').lower()}" for t, _ in removed if t.hash],
                ts=now,
            )
            self._store.journal.record(
                task_id=task.id,
                kind="deletion",
                items=[
                    OperationItem(
                        hash=t.hash, title=t.title,
                        reason=f"已非免费(促销={promo})且未下完", bonus_per_hour=0.0,
                    )
                    for t, promo in removed
                ],
            )
            self._store.forget_torrents(task.id, [t.hash for t, _ in removed])
        self._log(
            f"魔流 [{task.name}] 清理「已非免费」未下完种子 {deleted} 个:"
            + "、".join(f"{t.title[:24]}({promo})" for t, promo in removed[:6])
            + ("..." if len(removed) > 6 else "")
            + (f"(其中按期记录到期 {recorded_hits} 个)" if recorded_hits else "")
        )
        return deleted
