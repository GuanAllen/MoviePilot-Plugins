# -*- coding: utf-8 -*-
"""魔流 · tasks —— 任务 CRUD 与运行状态切换（API 层）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set


from app.schemas import Response

from ..bonus import (
    DEFAULT_CANDIDATE_REF_WEEKS,
    calc_torrent_bonus,
    preview_deletions,
    rank_candidates,
)
from ..fetcher import (
    SiteFetcher,
    filter_candidates,
)
from ..models import (
    MagicFlowHandoverPayload,
    MagicFlowTaskPayload,
    MagicFlowTaskStatePayload,
)
from ..crossseed import (
    CROSSSEED_TAG,
)
from ..tags import (
    LEASE_TTL,
    STATE_BONUS,
    STATE_SILENT,
    SUB_NEW,
    retag,
    tag_for,
)
from ..sites.formula_fetch import (
    _norm_title as normalize_title,
)


from ..common import (
    BROWSE_PAGES,
    MagicFlowTaskConfig,
    SILENT_HOST_TASK_ID,
    normalize_run_mode,
    enabled_of_run_mode,
    RUN_MODE_RUNNING,
    RUN_MODE_STOPPED,
)


class TasksMixin:
    """tasks 功能集（原 MagicFlow 方法原样搬入）。"""

    def create_task(self, payload: MagicFlowTaskPayload) -> Response:
        """创建魔流任务。"""
        task_id = payload.id or uuid.uuid4().hex[:12]
        if task_id in self._task_configs:
            return Response(success=False, message="任务 ID 已存在")

        site = self._get_site(payload.site_id)
        if not site:
            return Response(success=False, message="站点不存在")

        run_mode = normalize_run_mode(getattr(payload, "run_mode", None), payload.enabled)
        task = MagicFlowTaskConfig(
            id=task_id,
            name=payload.name,
            enabled=enabled_of_run_mode(run_mode),
            site_id=payload.site_id,
            site_domain=payload.site_domain or getattr(site, "domain", "") or "",
            site_name=payload.site_name or getattr(site, "name", "") or "",
            downloader=payload.downloader,
            brush_tag=payload.brush_tag or f"魔流-{payload.name}",
            save_path=payload.save_path or "",
            task_type=getattr(payload, "task_type", "bonus") or "bonus",
            run_mode=run_mode,
            brush_grace_minutes=int(getattr(payload, "brush_grace_minutes", 15) or 0),
            upload_idle_minutes=int(getattr(payload, "upload_idle_minutes", 10) or 0),
            upload_min_kbps=int(getattr(payload, "upload_min_kbps", 200) or 0),
            brush_min_leechers=int(getattr(payload, "brush_min_leechers", 1) or 0),
            brush_seed_days=int(getattr(payload, "brush_seed_days", 2) if getattr(payload, "brush_seed_days", 2) is not None else 2),
            rotate_upload_gb=float(payload.rotate_upload_gb) if getattr(payload, "rotate_upload_gb", None) not in (None, "") else None,
            rotate_ratio=float(payload.rotate_ratio) if getattr(payload, "rotate_ratio", None) not in (None, "") else None,
            except_subscribe=getattr(payload, "except_subscribe", True) is not False,
            protect_perfect=getattr(payload, "protect_perfect", True) is not False,
            perfect_max_seeders=int(getattr(payload, "perfect_max_seeders", 3) or 0),
            perfect_min_weeks=float(getattr(payload, "perfect_min_weeks", 4.0) or 0.0),
            goal_value=float(payload.goal_value) if getattr(payload, "goal_value", None) not in (None, "") else None,
            download_target_gb=(
                float(payload.download_target_gb)
                if getattr(payload, "download_target_gb", None) not in (None, "")
                else None
            ),
            allow_unfree_download=bool(getattr(payload, "allow_unfree_download", False)),
            brush_interval=payload.brush_interval,
            check_interval=payload.check_interval,
            cron_expression=payload.cron_expression or "",
            active_time_range=payload.active_time_range or "",
            min_bonus_per_hour=payload.min_bonus_per_hour,
            max_keep_torrents=payload.max_keep_torrents,
            bonus_protect_threshold=payload.bonus_protect_threshold,
            min_bonus_to_keep=payload.min_bonus_to_keep if payload.min_bonus_to_keep is not None else 0.0,
            disk_size_gb=payload.disk_size_gb,
            refill_when_empty=payload.refill_when_empty,
            max_add_per_run=getattr(payload, "max_add_per_run", 10) or 10,
            max_download_concurrent=getattr(payload, "max_download_concurrent", 10) or 10,
            top_n=getattr(payload, "top_n", 30) or 30,
            browse_pages=getattr(payload, "browse_pages", 3) or 3,
            reuse_existing=payload.reuse_existing,
            reuse_verify=payload.reuse_verify,
            auto_swap=bool(getattr(payload, "auto_swap", False)),
            swap_allow_download=bool(getattr(payload, "swap_allow_download", False)),
            swap_ceiling_pct=float(getattr(payload, "swap_ceiling_pct", 70.0) or 70.0),
            swap_min_gain_pct=float(getattr(payload, "swap_min_gain_pct", 25.0) or 25.0),
            swap_max_in_gb=(
                float(payload.swap_max_in_gb)
                if getattr(payload, "swap_max_in_gb", None) not in (None, "")
                else None
            ),
            swap_daily_dl_gb=float(getattr(payload, "swap_daily_dl_gb", 20.0) or 0.0),
            swap_min_gain_per_gb=float(getattr(payload, "swap_min_gain_per_gb", 0.05) or 0.0),
            swap_min_in_seeders=int(getattr(payload, "swap_min_in_seeders", 3) or 3),
            crossseed_enabled=bool(getattr(payload, "crossseed_enabled", False)),
            crossseed_max_per_round=int(getattr(payload, "crossseed_max_per_round", 3) or 3),
            crossseed_max_size_gb=float(getattr(payload, "crossseed_max_size_gb", 20.0) or 20.0),
            crossseed_max_sites=int(getattr(payload, "crossseed_max_sites", 6) or 6),
            cleanup_no_progress=payload.cleanup_no_progress,
            no_progress_minutes=payload.no_progress_minutes,
            cleanup_slow_progress=getattr(payload, "cleanup_slow_progress", True) is not False,
            slow_progress_grace_minutes=int(getattr(payload, "slow_progress_grace_minutes", 60) or 60),
            slow_progress_max_hours=float(getattr(payload, "slow_progress_max_hours", 48.0) or 48.0),
            purge_unfree_incomplete=getattr(payload, "purge_unfree_incomplete", True) is not False,
            auto_resume_paused=getattr(payload, "auto_resume_paused", True) is not False,
            seen_cooldown_hours=payload.seen_cooldown_hours,
            bonus_t0=payload.bonus_t0,
            bonus_n0=payload.bonus_n0,
            bonus_b0=payload.bonus_b0,
            bonus_l=payload.bonus_l,
            bonus_zero_weight=payload.bonus_zero_weight,
            size=payload.size or "",
            seeder=payload.seeder or "",
            pubtime=payload.pubtime or "",
            include=payload.include or "",
            exclude=payload.exclude or "",
            freeleech=payload.freeleech or "",
            hr=payload.hr or "",
            min_seed_time=int(payload.min_seed_time or 0),
            min_ratio=payload.min_ratio or 0.0,
            delete_files=payload.delete_files,
            delete_except_tags=str(getattr(payload, "delete_except_tags", "") or "").strip(),
            exclude_zero_bonus=payload.exclude_zero_bonus,
            rss_support=payload.rss_support,
            up_speed=int(payload.up_speed) if payload.up_speed else None,
            dl_speed=int(payload.dl_speed) if payload.dl_speed else None,
        )

        self._task_configs[task.id] = task
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary(drop=True)
        self._apply_task_traffic_limit()
        self._apply_seed_upload_limit()
        return Response(success=True, message="任务创建成功", data=self._build_task_detail(task.id))

    def get_task_detail(self, task_id: str) -> Response:
        """获取任务详情。"""
        detail = self._build_task_detail(task_id)
        if not detail:
            return Response(success=False, message="任务不存在")
        return Response(success=True, data=detail)

    def update_task(self, task_id: str, payload: MagicFlowTaskPayload) -> Response:
        """更新魔流任务。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        site = self._get_site(payload.site_id)
        if not site:
            return Response(success=False, message="站点不存在")

        task.name = payload.name
        # 运行状态:编辑器「启用」开关优先(开启→运行中;关闭→已停止;做种中 保持不变)
        _req_mode = str(getattr(payload, "run_mode", None) or "").strip().lower()
        _prev_mode = str(getattr(task, "run_mode", "running") or "running")
        if payload.enabled and _req_mode != "running":
            _run_mode = "running"
        elif (not payload.enabled) and _req_mode == "running":
            _run_mode = "stopped"
        else:
            _run_mode = self._normalize_run_mode(_req_mode or _prev_mode, payload.enabled)
        task.run_mode = _run_mode
        task.enabled = enabled_of_run_mode(_run_mode)
        task.site_id = payload.site_id
        task.site_domain = payload.site_domain or getattr(site, "domain", "") or ""
        task.site_name = payload.site_name or getattr(site, "name", "") or ""
        task.downloader = payload.downloader
        task.brush_tag = payload.brush_tag or task.brush_tag or f"魔流-{payload.name}"
        task.save_path = payload.save_path or ""
        task.task_type = getattr(payload, "task_type", "bonus") or "bonus"
        task.brush_grace_minutes = int(getattr(payload, "brush_grace_minutes", 15) or 0)
        task.upload_idle_minutes = int(getattr(payload, "upload_idle_minutes", 10) or 0)
        task.upload_min_kbps = int(getattr(payload, "upload_min_kbps", 200) or 0)
        task.brush_min_leechers = int(getattr(payload, "brush_min_leechers", 1) or 0)
        task.brush_seed_days = int(getattr(payload, "brush_seed_days", 2) if getattr(payload, "brush_seed_days", 2) is not None else 2)
        task.rotate_upload_gb = float(payload.rotate_upload_gb) if getattr(payload, "rotate_upload_gb", None) not in (None, "") else None
        task.rotate_ratio = float(payload.rotate_ratio) if getattr(payload, "rotate_ratio", None) not in (None, "") else None
        task.except_subscribe = getattr(payload, "except_subscribe", True) is not False
        task.protect_perfect = getattr(payload, "protect_perfect", True) is not False
        task.perfect_max_seeders = int(getattr(payload, "perfect_max_seeders", 3) or 0)
        task.perfect_min_weeks = float(getattr(payload, "perfect_min_weeks", 4.0) or 0.0)
        task.goal_value = float(payload.goal_value) if getattr(payload, "goal_value", None) not in (None, "") else None
        task.download_target_gb = (
            float(payload.download_target_gb)
            if getattr(payload, "download_target_gb", None) not in (None, "")
            else None
        )
        task.allow_unfree_download = bool(getattr(payload, "allow_unfree_download", False))
        task.brush_interval = payload.brush_interval
        task.check_interval = payload.check_interval
        task.cron_expression = payload.cron_expression or ""
        task.active_time_range = payload.active_time_range or ""
        task.min_bonus_per_hour = payload.min_bonus_per_hour
        task.max_keep_torrents = payload.max_keep_torrents
        task.bonus_protect_threshold = payload.bonus_protect_threshold
        task.min_bonus_to_keep = payload.min_bonus_to_keep if payload.min_bonus_to_keep is not None else 0.0
        task.disk_size_gb = payload.disk_size_gb
        task.refill_when_empty = payload.refill_when_empty
        task.max_add_per_run = getattr(payload, "max_add_per_run", 10) or 10
        task.max_download_concurrent = getattr(payload, "max_download_concurrent", 10) or 10
        task.top_n = getattr(payload, "top_n", 30) or 30
        task.browse_pages = getattr(payload, "browse_pages", 3) or 3
        task.reuse_existing = payload.reuse_existing
        task.reuse_verify = payload.reuse_verify
        # ★ 3.35.0 自动换种（同样必须显式赋值，漏一个前端开关就白开）；3.36.0 默认关 + 默认只做零下载辅种
        task.auto_swap = bool(getattr(payload, "auto_swap", False))
        task.swap_allow_download = bool(getattr(payload, "swap_allow_download", False))
        _scp = getattr(payload, "swap_ceiling_pct", None)
        task.swap_ceiling_pct = float(_scp) if _scp not in (None, "") else 70.0
        _smg = getattr(payload, "swap_min_gain_pct", None)
        task.swap_min_gain_pct = float(_smg) if _smg not in (None, "") else 25.0
        _smi = getattr(payload, "swap_max_in_gb", None)
        task.swap_max_in_gb = float(_smi) if _smi not in (None, "") else None
        task.swap_daily_dl_gb = float(getattr(payload, "swap_daily_dl_gb", 20.0) or 0.0)
        task.swap_min_gain_per_gb = float(getattr(payload, "swap_min_gain_per_gb", 0.05) or 0.0)
        task.swap_min_in_seeders = int(getattr(payload, "swap_min_in_seeders", 3) or 3)
        # ★ 3.9.0 跨站免费取种（EditForm 显式赋值；漏一个就等于前端开关不生效）
        task.crossseed_enabled = bool(getattr(payload, "crossseed_enabled", False))
        task.crossseed_max_per_round = max(int(getattr(payload, "crossseed_max_per_round", 3) or 3), 1)
        task.crossseed_max_size_gb = float(getattr(payload, "crossseed_max_size_gb", 20.0) or 20.0)
        task.crossseed_max_sites = max(int(getattr(payload, "crossseed_max_sites", 6) or 6), 1)
        task.cleanup_no_progress = payload.cleanup_no_progress
        task.no_progress_minutes = payload.no_progress_minutes
        task.cleanup_slow_progress = getattr(payload, "cleanup_slow_progress", True) is not False
        task.slow_progress_grace_minutes = int(getattr(payload, "slow_progress_grace_minutes", 60) or 60)
        task.slow_progress_max_hours = float(getattr(payload, "slow_progress_max_hours", 48.0) or 48.0)
        task.purge_unfree_incomplete = getattr(payload, "purge_unfree_incomplete", True) is not False
        task.auto_resume_paused = getattr(payload, "auto_resume_paused", True) is not False
        task.seen_cooldown_hours = payload.seen_cooldown_hours
        task.bonus_t0 = payload.bonus_t0
        task.bonus_n0 = payload.bonus_n0
        task.bonus_b0 = payload.bonus_b0
        task.bonus_l = payload.bonus_l
        task.bonus_zero_weight = payload.bonus_zero_weight
        task.size = payload.size or ""
        task.seeder = payload.seeder or ""
        task.pubtime = payload.pubtime or ""
        task.include = payload.include or ""
        task.exclude = payload.exclude or ""
        task.freeleech = payload.freeleech or ""
        task.hr = payload.hr or ""
        task.min_seed_time = int(payload.min_seed_time or 0)
        task.min_ratio = payload.min_ratio or 0.0
        task.delete_files = payload.delete_files
        task.delete_except_tags = str(getattr(payload, "delete_except_tags", "") or "").strip()
        task.exclude_zero_bonus = payload.exclude_zero_bonus
        task.rss_support = payload.rss_support
        task.up_speed = int(payload.up_speed) if payload.up_speed else None
        task.dl_speed = int(payload.dl_speed) if payload.dl_speed else None

        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary(drop=True)
        self._apply_task_traffic_limit()
        self._apply_seed_upload_limit()
        if _run_mode != _prev_mode:
            self._spawn_run_mode_apply(task, _run_mode)
            if not enabled_of_run_mode(_run_mode):
                # ★ 停止＝退回静默（保文件、可逆；重新启用会被同站纳管再接管回来）
                threading.Thread(
                    target=self._settle_task_idle_safe, args=(task.id,), daemon=True
                ).start()
        return Response(success=True, message="任务已更新", data=self._build_task_detail(task_id))

    # ---------------------------------------------------------
    # 任务删除前的「种子交棒 / 退回静默」
    # ---------------------------------------------------------

    def _task_owns(self, task: Any, h: str, *, now: Optional[float] = None) -> bool:
        """★ 归属判定：账本占用优先于标签命中（同站标签会被多个任务共享）。

        - 账本 ``taken_by`` 是**别人**且租约**未过期** → 不归我（即使标签一样）
        - 归我 / 没人占用 / 占用者租约已过期 → 归我
        """
        hh = str(h or "").strip().lower()
        if not hh:
            return False
        tid = str(getattr(task, "id", "") or "")
        try:
            rec = self._tag_state().get(hh) or {}
        except Exception:  # noqa: BLE001
            return True
        owner = str(rec.get("taken_by") or "")
        if not owner or owner == tid:
            return True
        ts = float(now if now is not None else time.time())
        return float(rec.get("lease_until") or 0) <= ts

    def _task_owned_torrents(self, task: Any, torrents: Any, *, claim: bool = False) -> List[Any]:
        """按**归属**过滤任务名下的种（标签命中的种里剔除「别人租约未过期」的）。

        ``claim=True`` 时顺手把「标签命中但账本无主」的种占为己有并续租（一次落盘），
        两个同站同状态任务因此会在第一轮就分出唯一归属，不再互相重复计入。
        """
        tid = str(getattr(task, "id", "") or "")
        name = str(getattr(task, "name", "") or "")
        try:
            site, state = self._task_site_state(task)
        except Exception:  # noqa: BLE001
            site, state = str(getattr(task, "site_name", "") or ""), STATE_BONUS
        store = self._tag_state()
        now = time.time()
        out: List[Any] = []
        patches: Dict[str, Dict[str, Any]] = {}
        for t in list(torrents or []):
            h = str(getattr(t, "hash", "") or "").strip().lower()
            if not h:
                continue
            rec = store.get(h) or {}
            owner = str(rec.get("taken_by") or "")
            lease = float(rec.get("lease_until") or 0)
            if owner and owner != tid and lease > now:
                continue  # 归别人（租约未过期）
            out.append(t)
            if claim and (owner != tid or lease <= now):
                patches[h] = {
                    "site": site, "state": state,
                    "sub": str(rec.get("sub") or "") or SUB_NEW,
                    "taken_by": tid, "task": name,
                    "taken_at": now, "lease_until": now + float(LEASE_TTL),
                    "title": str(getattr(t, "title", "") or "")[:200],
                    "size_gb": float(getattr(t, "size_gb", 0) or 0),
                }
        if patches:
            try:
                n = store.put_many(patches, now=now)
                self._dbg(f"归属:「{name}」认领/续租 {n} 个")
            except Exception as err:  # noqa: BLE001
                self._log(f"归属:占用写入失败:{err}", "warning")
        return out

    def _task_managed_hashes(self, task: Any) -> List[str]:
        """任务名下种子 hash：标签命中（剔除别人占用的）∪ 账本里显式占用（taken_by）。"""
        out: List[str] = []
        seen: Set[str] = set()
        tags = set(self._task_tags(task))
        try:
            snap = self._tag_all_torrents()
        except Exception:  # noqa: BLE001
            snap = {}
        _now = time.time()
        for h, t in (snap or {}).items():
            tt = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if any(x in tags for x in tt) and h not in seen and self._task_owns(task, h, now=_now):
                out.append(h)
                seen.add(h)
        try:
            tid = str(getattr(task, "id", "") or "")
            for h, rec in (self._tag_state().items() or {}).items():
                if str((rec or {}).get("taken_by") or "") == tid and h not in seen:
                    out.append(h)
                    seen.add(h)
        except Exception:  # noqa: BLE001
            pass
        return out

    def _task_handover_plan(self, task: Any) -> Dict[str, Any]:
        """算出「删掉这个任务，名下种子能交给谁」：同站其它任务 + 各自会接管多少。"""
        hashes = self._task_managed_hashes(task)
        size_gb = 0.0
        try:
            snap = self._tag_all_torrents()
            for h in hashes:
                size_gb += float(getattr(snap.get(h), "size_gb", 0) or 0)
        except Exception:  # noqa: BLE001
            pass
        same_tag = self._task_tag(task)
        cs_tag = CROSSSEED_TAG
        try:
            rec_tag = str(self._recommend_cfg.get("tag", "魔流-推荐") or "魔流-推荐")
        except Exception:  # noqa: BLE001
            rec_tag = "魔流-推荐"
        protected = 0
        try:
            cs_hashes = set(self._crossseed_source_hashes() or set())
        except Exception:  # noqa: BLE001
            cs_hashes = set()
        for h in hashes:
            if h in cs_hashes:
                protected += 1
        cands: List[Dict[str, Any]] = []
        for other in self._task_configs.values():
            if str(getattr(other, "id", "")) == str(getattr(task, "id", "")):
                continue
            site_o, state_o = self._task_site_state(other)
            cands.append({
                "id": str(getattr(other, "id", "") or ""),
                "name": str(getattr(other, "name", "") or ""),
                "site": site_o,
                "state": state_o,
                "enabled": bool(getattr(other, "enabled", False)),
                "tag": tag_for(site_o, state_o),
                "same_tag": tag_for(site_o, state_o) == same_tag,
                "same_site": site_o == str(getattr(task, "site_name", "") or ""),
            })
        cands.sort(key=lambda c: (not c["same_tag"], not c["same_site"], not c["enabled"], c["name"]))
        return {
            "task": {"id": str(getattr(task, "id", "") or ""), "name": str(getattr(task, "name", "") or "")},
            "managed": len(hashes),
            "size_gb": round(size_gb, 2),
            "protected": protected,
            "tag": same_tag,
            "auto_handover": [c for c in cands if c["same_tag"]],
            "candidates": cands,
            "recommend_tag": rec_tag,
        }

    def _tag_handover(self, src: Any, dst: Any, hashes: Any = None) -> Dict[str, Any]:
        """把 src 名下的种子交给 dst：重贴标签（按 dst 的站点/状态）+ 改账本占用。

        ``hashes`` 给定时只处理这些（批量转移用），否则处理 src 名下全部。
        """
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return {"ok": False, "error": "下载器不可用"}
        store = self._tag_state()
        site, state = self._task_site_state(dst)
        sub = ""
        target = tag_for(site, state, sub)
        dst_id = str(getattr(dst, "id", "") or "")
        dn = str(getattr(dst, "name", "") or "")
        fn = getattr(downloader, "replace_torrent_tags", None)
        snap = self._tag_all_torrents()
        moved = failed = skipped = 0
        _targets = (list(hashes) if hashes else self._task_managed_hashes(src))
        for h in [str(x or "").strip().lower() for x in _targets]:
            if not h:
                continue
            live = snap.get(h)
            cur = [str(x).strip() for x in (getattr(live, "tags", None) or [])] if live is not None else []
            # 跨站来源份 / 不归任务管的：跳过
            if CROSSSEED_TAG in cur:
                skipped += 1
                continue
            new_tags = retag(cur, site=site, state=state, sub=sub) if cur else [target]
            try:
                done = fn(h, new_tags) if callable(fn) else downloader.set_torrent_tags(h, new_tags)
            except Exception:  # noqa: BLE001
                done = False
            if not done:
                failed += 1
                continue
            rec = dict(store.get(h) or {})
            rec.update({
                "site": site, "state": state, "sub": sub or str(rec.get("sub") or "") or SUB_NEW,
                "taken_by": dst_id, "task": dn,
            })
            if live is not None:
                rec.setdefault("title", str(getattr(live, "title", "") or "")[:200])
                rec.setdefault("size_gb", float(getattr(live, "size_gb", 0) or 0))
            try:
                store.put(h, rec)
            except Exception:  # noqa: BLE001
                pass
            moved += 1
        try:
            self._apply_seed_upload_limit(force=True)
        except Exception:  # noqa: BLE001
            pass
        if moved:
            self._log(f"标签模型:任务「{getattr(src, 'name', '')}」名下 {moved} 个种子交棒给「{dn}」（{target}）")
        return {"ok": True, "moved": moved, "failed": failed, "skipped": skipped, "target_tag": target}

    def _tag_settle_idle(self, task: Any, hashes: Any = None) -> Dict[str, Any]:
        """把任务名下种子退回静默池（保文件、可逆），并清掉账本占用。"""
        _targets = (list(hashes) if hashes else self._task_managed_hashes(task))
        n = self._tag_release(task, _targets, reason="退回静默")
        return {"ok": True, "settled": n}

    def get_task_handover(self, task_id: str) -> Response:
        """预览：删掉该任务时名下种子能交给谁 / 有多少要处理。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        return Response(success=True, message="ok", data=self._task_handover_plan(task))

    def post_task_handover(self, task_id: str, payload: MagicFlowHandoverPayload) -> Response:
        """执行：交棒给目标任务 或 退回静默池。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        mode = str(getattr(payload, "mode", "") or "handover").strip().lower()
        tid = str(getattr(payload, "target_task_id", "") or "").strip()
        _hs = [str(x).strip().lower() for x in (getattr(payload, "hashes", None) or []) if str(x).strip()]
        if mode == "idle" or not tid:
            res = self._tag_settle_idle(task, _hs or None)
            return Response(success=True, message=f"已退回静默池 {res.get('settled')} 个", data=res)
        dst = self._get_task_config(tid)
        if not dst:
            return Response(success=False, message="目标任务不存在")
        res = self._tag_handover(task, dst, _hs or None)
        if not res.get("ok"):
            return Response(success=False, message=str(res.get("error") or "交棒失败"), data=res)
        return Response(success=True, message=f"已交棒 {res.get('moved')} 个给「{getattr(dst, 'name', '')}」", data=res)

    def delete_task(self, task_id: str, handover_to: str = "", settle: str = "") -> Response:
        """删除魔流任务。

        - ``handover_to=<任务id>``：先把名下种子整体交棒给该任务，再删任务；
        - ``settle=idle``：名下种子退回静默池（保文件），再删任务；
        - 都不传：只删配置（种子会变孤儿，不推荐）。
        """
        if task_id not in self._task_configs:
            return Response(success=False, message="任务不存在")

        _handled: Dict[str, Any] = {}
        if str(handover_to or "").strip():
            dst = self._get_task_config(str(handover_to).strip())
            if not dst:
                return Response(success=False, message="目标任务不存在，未删除")
            _handled = self._tag_handover(self._task_configs[task_id], dst)
        elif str(settle or "").strip().lower() == "idle":
            _handled = self._tag_settle_idle(self._task_configs[task_id])

        del self._task_configs[task_id]
        if self._store:
            self._store.task_states.delete(task_id)
            # 同步清掉去重(seen)与操作记录,避免残留孤儿数据(每个任务都有独立桶)。
            try:
                self._store.seen.delete(task_id)
            except Exception as err:
                self._log(f"清理任务去重记录失败:{err}", "warning")
            try:
                self._store.journal.delete_task(task_id)
            except Exception as err:
                self._log(f"清理任务操作记录失败:{err}", "warning")
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary(drop=True)
        self._apply_task_traffic_limit()
        self._apply_seed_upload_limit()
        _msg = "任务已删除"
        if _handled:
            if "moved" in _handled:
                _msg = f"任务已删除（种子交棒 {_handled.get('moved')} 个）"
            elif "settled" in _handled:
                _msg = f"任务已删除（退回静默 {_handled.get('settled')} 个）"
        return Response(success=True, message=_msg, data=_handled or None)

    def update_task_state(self, task_id: str, payload: MagicFlowTaskStatePayload) -> Response:
        """切换任务运行状态(running / seeding / stopped)。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        mode = normalize_run_mode(
            getattr(payload, "mode", None), getattr(payload, "enabled", None)
        )
        task.run_mode = mode
        task.enabled = enabled_of_run_mode(mode)
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary(drop=True)
        self._apply_task_traffic_limit()
        self._apply_seed_upload_limit()
        # 异步应用种子操作(暂停/恢复);「运行中」时立即跑一轮 check,避免非免费偷下空窗
        self._spawn_run_mode_apply(task, mode)
        return Response(success=True, data=self._build_task_detail(task_id))

    def run_task(self, task_id: str) -> Response:
        """异步执行一轮魔力优化(清理低效种子并补充优质种子)。"""
        if str(task_id or "") == SILENT_HOST_TASK_ID:
            threading.Thread(target=self.silent_host, daemon=True).start()
            return Response(success=True, message="静默托管已启动")
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        thread = threading.Thread(target=self.brush, args=(task_id,), daemon=True)
        thread.start()
        return Response(success=True, message="魔力优化已启动")

    # ---------------------------------------------------------
    # API:魔力明细
    # ---------------------------------------------------------

    def backfill_torrent_pages(self, task_id: str) -> Response:
        """回填存量托管种子的详情页链接(供「已非免费→清理」核对促销)。

        对当前托管(标签内)但未记录详情页链接的种子,依次尝试:
          1 seen 记录(hash↔cand 同时间戳配对);2 站点「我的种子」列表按标题回填。
        只写本地记录,**不删任何种子**。
        """
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        if not self._store:
            return Response(success=False, message="存储不可用")
        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                return Response(success=False, message="下载器不可用")
            tagged, error = downloader.get_torrents(tags=[task.brush_tag])
            if error:
                return Response(success=False, message=str(error))
            managed = list(tagged or [])
            site = self._get_site(task.site_id)

            pages = dict(self._store.get_torrent_pages(task.id) or {})
            managed_hashes = {(t.hash or "").lower() for t in managed if t.hash}
            mapping: Dict[str, str] = {}
            # 1 seen 记录(hash↔cand 同时间戳配对)→ 只保留当前托管的
            for h, u in self._seen_page_pairs(task.id).items():
                if h in managed_hashes and not pages.get(h):
                    mapping[h] = u
            pages.update(mapping)

            # 强制刷新「我的种子」列表缓存后按标题回填
            cache = getattr(self, "_title_url_cache", None)
            if cache:
                cache.pop(task.id, None)
            umap = self._title_url_map(task, site) if site else {}

            unresolved = 0
            for t in managed:
                h = (t.hash or "").lower()
                if not h or pages.get(h):
                    continue
                url = umap.get(normalize_title(t.title or ""))
                if url:
                    mapping[h] = url
                    pages[h] = url
                else:
                    unresolved += 1
            if mapping:
                self._store.note_torrent_pages(task.id, mapping)
            total_known = len(self._store.get_torrent_pages(task.id) or {})
            self._log(
                f"魔流 [{task.name}] 回填详情页链接:托管 {len(managed)} 个,"
                f"本次解析 {len(mapping)},未匹配 {unresolved},当前已知 {total_known}"
            )
            return Response(
                success=True,
                message=f"已回填 {len(mapping)} 个详情页链接({unresolved} 个未能匹配)",
                data={
                    "managed": len(managed),
                    "resolved": len(mapping),
                    "unresolved": unresolved,
                    "total_known": total_known,
                },
            )
        except Exception as err:
            self._log(f"回填详情页链接失败: {err}", "error")
            return Response(success=False, message=str(err))

    def backfill_batch(self) -> Response:
        """对所有任务批量回填详情页链接(只写记录,不删种)。"""
        total_managed = total_resolved = total_unresolved = 0
        for task_id in list(self._task_configs.keys()):
            try:
                resp = self.backfill_torrent_pages(task_id)
                data = resp.data or {}
                total_managed += int(data.get("managed") or 0)
                total_resolved += int(data.get("resolved") or 0)
                total_unresolved += int(data.get("unresolved") or 0)
            except Exception:
                continue
        return Response(
            success=True,
            message=f"已回填 {total_resolved} 个链接({total_unresolved} 个未能匹配)",
            data={"managed": total_managed, "resolved": total_resolved, "unresolved": total_unresolved},
        )

    def get_task_bonus(self, task_id: str) -> Response:
        """获取任务魔力统计及种子列表。"""
        if str(task_id or "") == SILENT_HOST_TASK_ID:
            return Response(success=True, message="ok", data={
                "torrents": [], "total_bonus": 0.0, "torrent_count": 0, "protected_count": 0})
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                self._log(f"API 做种明细:下载器不可用({task.downloader})", "warning")
                return Response(success=False, message="下载器不可用")

            # 与总览共用同一份「全部种子按标签分组」快照(避免再单独全量拉一次 qB)
            task_torrents = self._task_owned_torrents(
                task, self._tag_snapshot_view(task.downloader).get(task.brush_tag, []))
            error = None
            self._log(
                f"API 做种明细:task={task_id} tag=「{task.brush_tag}」 tagged={len(task_torrents)} err={error}"
            )
            if error:
                return Response(success=True, data={"torrents": [], "total_bonus": 0, "torrent_count": 0, "protected_count": 0, "site": self._site_reported(task)})
            if not task_torrents:
                return Response(success=True, data={"torrents": [], "total_bonus": 0, "torrent_count": 0, "protected_count": 0, "site": self._site_reported(task)})
            rep = self._site_reported(task)
            protected_hashes = self._store.get_protected_torrents(task_id) if self._store else set()
            state_by_hash = {
                (t.hash or "").lower(): str(getattr(t, "state", "") or "")
                for t in task_torrents
            }
            progress_by_hash = {
                (t.hash or "").lower(): round(float(getattr(t, "progress", 0) or 0), 4)
                for t in task_torrents
            }
            uploaded_by_hash = {
                (t.hash or "").lower(): round(float(getattr(t, "uploaded", 0) or 0))
                for t in task_torrents
            }
            ratio_by_hash = {
                (t.hash or "").lower(): round(float(getattr(t, "ratio", 0) or 0), 3)
                for t in task_torrents
            }

            # 黑盒:不展示自算魔力/评分/排名,只展示托管状态与进度。
            torrents_data = []
            for t in task_torrents:
                hkey = (t.hash or "").lower()
                torrents_data.append({
                    "hash": t.hash,
                    "title": t.title,
                    "size_gb": round(t.size_gb, 2),
                    "is_protected": t.hash in protected_hashes,
                    "state": state_by_hash.get(hkey, ""),
                    "progress": progress_by_hash.get(hkey, 0.0),
                    "uploaded": uploaded_by_hash.get(hkey, 0),
                    "ratio": ratio_by_hash.get(hkey, 0.0),
                })

            return Response(success=True, data={
                "torrents": torrents_data,
                "total_bonus": round(rep["bonus_per_hour"], 4),
                "torrent_count": len(torrents_data),
                "protected_count": sum(1 for t in torrents_data if t["is_protected"]),
                "site": rep,
            })

        except Exception as e:
            self._log(f"获取魔力统计失败: {e}", "error")
            return Response(success=False, message=str(e))

    def get_task_candidates(self, task_id: str) -> Response:
        """获取候选种子(黑盒:不对外暴露自算魔力评分,仅返回名次与基础属性)。"""
        if str(task_id or "") == SILENT_HOST_TASK_ID:
            return Response(success=True, message="ok", data={
                "candidates": [], "total": 0, "reason_counts": {}})
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        try:
            fetcher = SiteFetcher()
            if not fetcher.is_available:
                return Response(success=False, message="站点抓取不可用")

            candidates = None
            _pages = max(int(task.browse_pages or BROWSE_PAGES), 1)
            # 站点级共享:同站一份完整列表,刷流侧再筛免费(与主流程一致)。
            candidates = self._fetch_site_candidates(task, pages=_pages, start_page=0)
            if str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush" and candidates:
                candidates = [
                    c for c in candidates
                    if getattr(c, "is_free", False) or getattr(c, "is_double_free", False)
                ]
            if not candidates:
                return Response(success=True, data={"candidates": [], "total": 0, "reason_counts": {}})

            filter_policy = self._build_filter_policy(task)
            filtered, reason_counts = filter_candidates(candidates, filter_policy)

            official_titles = self._site_official_titles(task.site_id)
            bonus_list = []
            for c in filtered:
                bonus_info = calc_torrent_bonus(
                    hash=c.hash or uuid.uuid4().hex[:8],
                    title=c.title,
                    size_gb=c.size_gb,
                    seeders=c.seeders,
                    leechers=c.leechers,
                    age_weeks=max(c.age_weeks, DEFAULT_CANDIDATE_REF_WEEKS),
                    volume_factor=c.volume_factor,
                    is_zero_bonus=c.is_zero_bonus,
                    is_free=c.is_free,
                    is_double_free=c.is_double_free,
                    is_official=bool(official_titles) and (normalize_title(c.title) in official_titles),
                    params=self._build_formula_params(task),
                )
                bonus_info.age_weeks = c.age_weeks
                bonus_list.append(bonus_info)

            _is_brush = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"
            if _is_brush:
                # 刷流:候选排行按「上传潜力」--下载人数↓、体积↓、新鲜度↑
                # (与 _brush_impl 选种/下载序一致;此前统一走魔力排序,与卡片标题矛盾)。
                ordered = sorted(
                    bonus_list,
                    key=lambda _t: (
                        int(getattr(_t, "leechers", 0) or 0),
                        float(getattr(_t, "size_gb", 0.0) or 0.0),
                        -float(getattr(_t, "age_weeks", 0.0) or 0.0),
                    ),
                    reverse=True,
                )
            else:
                policy = self._build_magic_policy(task, bonus_list)
                ordered = [rc.torrent for rc in rank_candidates(bonus_list, policy)]

            candidates_data = []
            for _idx, t in enumerate(ordered, 1):
                candidates_data.append({
                    "hash": t.hash,
                    "title": t.title,
                    "size_gb": round(t.size_gb, 2),
                    "seeders": t.seeders,
                    "leechers": t.leechers,
                    "age_weeks": round(t.age_weeks, 2),
                    "is_zero_bonus": t.is_zero_bonus,
                    "is_official": bool(t.is_official),
                    "rank": _idx,
                })

            return Response(success=True, data={
                "candidates": candidates_data,
                "total": len(candidates_data),
                "reason_counts": reason_counts,
            })

        except Exception as e:
            self._log(f"获取候选失败: {e}", "error")
            return Response(success=False, message=str(e))

    def preview_cleanup(self, task_id: str) -> Response:
        """预览删种名单。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                return Response(success=False, message="下载器不可用")

            seeding_torrents, error = downloader.get_seeding_torrents(tag=task.brush_tag)
            if error or not seeding_torrents:
                return Response(success=True, data={"preview": {}, "message": "没有做种种子"})

            task_torrents = [t for t in seeding_torrents if task.brush_tag in t.tags]
            torrent_bonus_list = self._convert_to_bonus_list(task_torrents, self._build_formula_params(task), self._task_pub_dates(task), getattr(task, "ti_source", "publish"), self._site_ni_map(task.site_id, task_torrents), self._site_official_titles(task.site_id))
            protected_hashes = self._store.get_protected_torrents(task_id) if self._store else set()
            # 媒体资产价值闸门:预览也排除已整理/辅种/历史命中的种子
            try:
                _asset = self._media_asset_hashes(list(task_torrents or []), task)
                if _asset:
                    protected_hashes = set(protected_hashes) | set(_asset)
            except Exception:
                pass

            # 刷流模式:预览「无上传将被清理」的种子(只读,不删)
            if str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush":
                try:
                    all_t, _ = downloader.get_torrents(tags=[task.brush_tag])
                except Exception:
                    all_t = []
                tt = [t for t in (all_t or []) if task.brush_tag in t.tags]
                prev = self._store.get_brush_upload(task_id) if self._store else {}
                need, thr, _grace = self._brush_idle_params(task)
                would = []
                for t in tt:
                    h = (t.hash or "").lower()
                    if not h or h in protected_hashes:
                        continue
                    p = prev.get(h)
                    if not p:
                        continue
                    up = float(getattr(t, "uploaded", 0) or 0)
                    idle = int(p.get("idle", 0) or 0)
                    if up - float(p.get("up", 0) or 0) < thr:
                        idle += 1
                    if idle >= need:
                        would.append({
                            "hash": t.hash,
                            "title": str(getattr(t, "title", "") or ""),
                            "reason": "无上传",
                        })
                return Response(success=True, data={
                    "mode": "brush",
                    "preview": {"to_delete": would, "count": len(would)},
                    "message": f"刷流模式:预计清理「无上传」种子 {len(would)} 个",
                })

            policy = self._build_magic_policy(task, torrent_bonus_list)

            preview = preview_deletions(torrent_bonus_list, policy, protected_hashes)
            return Response(success=True, data=preview)

        except Exception as e:
            self._log(f"预览删种失败: {e}", "error")
            return Response(success=False, message=str(e))
