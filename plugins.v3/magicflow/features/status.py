# -*- coding: utf-8 -*-
"""魔流 · status —— 状态汇总（status / summary / 诊断）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional


from app.schemas import Response

from ..bonus import (
    site_ceiling,
)
from ..downloader_ops import (
    QB_SEEDING_STATES,
    QB_DOWNLOADING_STATES,
    QB_PAUSED_STATES,
)

from ..common import __version__  # noqa: F401

from ..common import (
    BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT,
    CROSSSEED_SEED_HOURS_DEFAULT,
    MagicFlowTaskConfig,
    SEED_UP_LIMIT_KBPS_DEFAULT,
    SILENT_HOST_TASK_ID,
    STATS_TTL,
    STATUS_TTL,
    run_mode_of,
    task_is_participating,
    task_is_running,
)


class StatusMixin:
    """status 功能集（原 MagicFlow 方法原样搬入）。"""

    # ---------------------------------------------------------
    # 任务数据构建
    # ---------------------------------------------------------

    def _task_runtime_stats(self, task: MagicFlowTaskConfig, force: bool = False) -> Dict[str, Any]:
        """计算单个任务的实时托管种子数与魔力产出。

        带 STATS_TTL 短缓存:同一轮 /status 内「总览」与「任务列表」各算一次,
        缓存后只查一次下载器(去重),并让前端轮询/二次进入更快。
        """
        now = time.time()
        cache = getattr(self, "_stats_cache", None)
        if cache is None:
            cache = self._stats_cache = {}
        if not force:
            hit = cache.get(task.id)
            if hit and (now - float(hit.get("ts", 0))) < STATS_TTL:
                return hit["data"]
        stats = {
            "seeding_count": 0,
            "active_seeding_count": 0,
            "paused_count": 0,
            "downloading_count": 0,
            "bonus_per_hour": 0.0,
            "site_bonus_per_hour": 0.0,
            "site_bonus_a": 0.0,
            "site_bonus_ok": False,
            "site_current_bonus": 0.0,
            "site_ceiling": 0.0,
            "site_seed_cap": 0,
            "ceiling_pct": 0.0,
            "state": "idle",
            "protected_count": 0,
            "site_user": {},
            "task_uploaded": 0,
            "task_upload_active": 0,
            "hr_owed": 0,
            "hr_need_hours": 0.0,
            "bonus_day_delta": None,
            "attention": None,
        }
        # 站点上报(黑盒:不再自算模型值)
        try:
            rep = self._site_reported(task)
            stats["bonus_per_hour"] = round(rep["bonus_per_hour"], 4)
            stats["site_bonus_per_hour"] = round(rep["bonus_per_hour"], 4)
            stats["site_bonus_a"] = round(rep["a"], 2)
            stats["site_bonus_ok"] = bool(rep["ok"])
            # 该站点自己的「当前魔力存量」(不能跨站相加:各站魔力不可通约)
            stats["site_current_bonus"] = round(float(rep.get("current_bonus") or 0.0), 2)
            # 站点账号真实数据(上传/下载/分享率/做种/下载数)
            stats["site_user"] = rep.get("user") or {}
        except Exception as err:
            self._log(f"统计任务 [{task.name}] 站点魔力失败: {err}", "warning")
        # 站点上限感知:时魔天花板(B0 + 固定奖励封顶)+ 距上限占用
        try:
            params = self._build_formula_params(task)
            ceiling = float(site_ceiling(params))
            stats["site_ceiling"] = round(ceiling, 2)
            stats["site_seed_cap"] = int(getattr(params, "seeding_count_cap", 0) or 0)
            if ceiling > 0:
                stats["ceiling_pct"] = round(min(stats["site_bonus_per_hour"] / ceiling * 100.0, 999.0), 1)
        except Exception:
            pass
        try:
            managed = self._task_owned_torrents(
                task, self._tag_snapshot(task.downloader).get(task.brush_tag, []))
            from collections import Counter
            state_dist = dict(Counter(str(getattr(t, "state", "") or "?") for t in managed))
            self._log(
                f"统计任务 [{task.name}] tag=「{task.brush_tag}」→ 托管 {len(managed)} 个,状态分布 {state_dist}"
            )
            seeding = [
                t for t in managed
                if str(getattr(t, "state", "") or "").lower() in QB_SEEDING_STATES
            ]
            stats["seeding_count"] = len(managed)
            stats["active_seeding_count"] = len(seeding)
            # 本任务在下载器的累计上传量 / 有上传的种子数(刷流视角)
            uploaded_sum = 0.0
            upload_active = 0
            for t in managed:
                up = float(getattr(t, "uploaded", 0) or 0)
                uploaded_sum += up
                if up > 0:
                    upload_active += 1
            stats["task_uploaded"] = round(uploaded_sum)
            stats["task_upload_active"] = upload_active
            stats["paused_count"] = sum(
                1 for t in managed
                if str(getattr(t, "state", "") or "").lower() in QB_PAUSED_STATES
            )
            stats["downloading_count"] = sum(
                1 for t in managed
                if str(getattr(t, "state", "") or "").lower() in QB_DOWNLOADING_STATES
            )
            # ★ H&R 欠账（站点级口径，含静默池 / 跨站来源份）
            try:
                _hr = (self._hr_owed_by_site() or {}).get(str(task.site_name or "").strip()) or {}
                stats["hr_owed"] = int(_hr.get("n") or 0)
                stats["hr_need_hours"] = float(_hr.get("h") or 0.0)
            except Exception:
                pass
            if seeding:
                stats["state"] = "seeding"
            elif managed:
                stats["state"] = "downloading"
        except Exception as err:
            self._log(f"统计任务 [{task.name}] 运行时数据失败: {err}", "warning")

        store_stats: Dict[str, Any] = {}
        if self._store:
            store_stats = self._store.get_task_stats(task.id) or {}
            stats["protected_count"] = store_stats.get("protected_count", 0)
            if store_stats.get("last_error"):
                stats["state"] = "error"

        # ★ 「需要你管」：真实可操作信号（不是只看颜色）
        try:
            store_stats = store_stats if isinstance(store_stats, dict) else {}
            mode = run_mode_of(task)
            ttype = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower()
            lerr = str(store_stats.get("last_error") or "").strip()
            att = None
            if lerr:
                att = {"level": "error", "text": "上次运行出错",
                       "detail": lerr[:160], "action": "诊断"}
            elif ttype == "bonus" and mode in ("running", "seeding") and not stats.get("site_bonus_ok"):
                att = {"level": "warning", "text": "站点魔力读不到",
                       "detail": "站点账号/实时页抓取异常，魔力数字不可信", "action": "诊断"}
            elif stats.get("hr_owed"):
                att = {"level": "warning",
                       "text": "%d 个种子欠 H&R" % int(stats.get("hr_owed") or 0),
                       "detail": "还需约 %gh 做种才能结清" % float(stats.get("hr_need_hours") or 0.0),
                       "action": "诊断"}
            elif (bool(getattr(task, "enabled", False)) and mode != "stopped"
                  and self._store and not store_stats.get("last_success_at")):
                att = {"level": "warning", "text": "尚未成功运行过",
                       "detail": "等待首轮执行完成", "action": "诊断"}
            stats["attention"] = att
        except Exception:
            stats["attention"] = None

        # ★ 今日魔力增量（按站点记当日基线；不跨站相加，仅取增量）
        try:
            cb = float(stats.get("site_current_bonus") or 0.0)
            if cb > 0:
                today = time.strftime("%Y-%m-%d")
                base = getattr(self, "_bonus_day_base", None)
                if base is None:
                    base = self._bonus_day_base = {}
                skey = str(task.site_domain or task.site_id or "").lower()
                rec = base.get(skey)
                if not isinstance(rec, dict) or rec.get("d") != today:
                    rec = {"d": today, "v": cb, "ts": time.time()}
                    base[skey] = rec
                if (time.time() - float(rec.get("ts") or 0.0)) > 300:
                    stats["bonus_day_delta"] = round(cb - float(rec.get("v") or cb), 2)
        except Exception:
            pass

        started = self._task_runs.get(task.id)
        if started is not None and (time.time() - started) < self._task_run_timeout:
            stats["state"] = "running"
        cache[task.id] = {"ts": time.time(), "data": stats}
        return stats

    def _runtime_stats_bulk(self, tasks: List[MagicFlowTaskConfig]) -> Dict[str, Dict[str, Any]]:
        """并发计算多任务实时统计(线程池);异常时回退串行。

        * 并发仅跨「不同任务」;单任务内部仍串行;
        * 命中 STATS_TTL 缓存的任务不会重复查询下载器;
        * 站点公式先在主线程预热(6h 缓存;冷启动只串行抓一次,避免并发重复请求站点页)。
        """
        result: Dict[str, Dict[str, Any]] = {}
        tasks = list(tasks or [])
        if not tasks:
            return result
        prewarm: Dict[str, MagicFlowTaskConfig] = {}
        for t in tasks:
            d = (getattr(t, "site_domain", "") or "").strip().lower()
            if d and d not in prewarm:
                prewarm[d] = t
        for t in prewarm.values():
            try:
                self._acquire_site_formula(t)
            except Exception:
                pass
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
                stats_list = list(pool.map(self._task_runtime_stats, tasks))
            for task, st in zip(tasks, stats_list):
                result[task.id] = st
        except Exception as err:
            self._log(f"并发统计失败,回退串行:{err}", "warning")
            for task in tasks:
                result[task.id] = self._task_runtime_stats(task)
        return result

    def _phase_info(self, task_id: str) -> Dict[str, Any]:
        """当前运行阶段 + 是否在跑(供前端「运行诊断」流程链转圈)。"""
        info: Dict[str, Any] = {
            "last_phase": "",
            "last_phase_label": "",
            "last_phase_at": 0.0,
            "page_cursor": 0,
            "run_active": False,
        }
        if self._store:
            try:
                info.update(self._store.get_phase(task_id))
                info["page_cursor"] = self._store.get_page_cursor(task_id)
            except Exception:
                pass
        started = self._task_runs.get(task_id)
        info["run_active"] = bool(started and (time.time() - started) < self._task_run_timeout)
        return info

    def _build_task_detail(self, task_id: str) -> Optional[Dict[str, Any]]:
        """构建任务详情(含统计信息)。"""
        if str(task_id or "") == SILENT_HOST_TASK_ID:
            return self._silent_host_card()
        task = self._get_task_config(task_id)
        if not task:
            return None
        store_stats = self._store.get_task_stats(task_id) if self._store else {}
        return {
            **task.to_dict(),
            **store_stats,
            **self._phase_info(task_id),
            **self._task_goal_status(task),
        }

    def _compute_summary(self) -> Dict[str, Any]:
        """计算总览统计(20 秒缓存)。"""
        now = time.time()
        if self._summary_cache and (now - self._summary_cache_at) < 20:
            return self._summary_cache

        total_tasks = len(self._task_configs)
        enabled_tasks = sum(1 for t in self._task_configs.values() if task_is_running(t))
        seeding_count = 0
        bonus_per_hour = 0.0
        current_bonus = 0.0
        ceiling = 0.0
        site_upload = 0.0
        site_download = 0.0

        # 站点上报魔力按「站点」去重(同一站点多任务不重复计)
        site_tasks: Dict[int, MagicFlowTaskConfig] = {}
        # 预热「全部任务」统计(含未启用):任务列表随后直接命中缓存,避免串行补算。
        all_tasks = list(self._task_configs.values())
        # 运行状态分布(唯一真源 run_mode;历史配置缺字段时按 enabled 回退)
        mode_counts = {"running": 0, "seeding": 0, "stopped": 0}
        for _t in all_tasks:
            mode_counts[run_mode_of(_t)] += 1
        active_tasks = total_tasks - mode_counts["stopped"]
        stats_by_id = self._runtime_stats_bulk(all_tasks)
        for task in all_tasks:
            # 运行中的任务 + 「做种中」的任务都在做种(后者只是不跑刷流流程)
            if not task_is_participating(task):
                continue
            seeding_count += int((stats_by_id.get(task.id) or {}).get("seeding_count", 0) or 0)
            site_tasks.setdefault(int(task.site_id or 0), task)
        for task in site_tasks.values():
            rep = self._site_reported(task)
            bonus_per_hour += rep["bonus_per_hour"]
            current_bonus += rep["current_bonus"]
            user = rep.get("user") or {}
            site_upload += float(user.get("upload") or 0)
            site_download += float(user.get("download") or 0)
            try:
                ceiling += float(site_ceiling(self._build_formula_params(task)))
            except Exception:
                pass

        summary = {
            "total_tasks": total_tasks,
            "enabled_tasks": enabled_tasks,
            "running_tasks": mode_counts["running"],
            "seeding_tasks": mode_counts["seeding"],
            "stopped_tasks": mode_counts["stopped"],
            "active_tasks": active_tasks,
            "seeding_count": seeding_count,
            "bonus_per_hour": round(bonus_per_hour, 4),
            "current_bonus": round(current_bonus, 2),
            "ceiling": round(ceiling, 2),
            "ceiling_pct": round(min(bonus_per_hour / ceiling * 100.0, 999.0), 1) if ceiling > 0 else 0.0,
            "site_upload": round(site_upload),
            "site_download": round(site_download),
            "site_ratio": round(site_upload / site_download, 3) if site_download > 0 else 0.0,
        }
        self._summary_cache = summary
        self._summary_cache_at = now
        return summary

    def _build_task_list(self) -> List[Dict[str, Any]]:
        """构建任务列表(含实时统计)。"""
        tasks: List[Dict[str, Any]] = []
        stats_by_id = self._runtime_stats_bulk(list(self._task_configs.values()))
        for task in self._task_configs.values():
            runtime = stats_by_id.get(task.id, {})
            tasks.append({
                **task.to_dict(),
                **runtime,
                **self._phase_info(task.id),
                **self._task_goal_status(task, light=True),
            })
        try:
            tasks.append(self._silent_host_card())
        except Exception:  # noqa: BLE001
            pass
        return tasks

    # ---------------------------------------------------------
    # API:全局
    # ---------------------------------------------------------

    def _build_status_heavy(self) -> Dict[str, Any]:
        """构建总览的重数据(统计 + 任务列表 + 选项)。"""
        import time as _t
        _bsh0 = _t.time()
        summary = self._compute_summary()
        _t1 = _t.time()
        self._log(
            f"API 总览:任务 {summary.get('total_tasks')} 启用 {summary.get('enabled_tasks')} "
            f"托管 {summary.get('seeding_count')} 魔力 {summary.get('bonus_per_hour')}/h"
        )
        _bsh_ms = round((_t.time() - _bsh0) * 1000)
        _summary_ms = round((_t1 - _bsh0) * 1000)
        _tasks_ms = round((_t.time() - _t1) * 1000)
        if _bsh_ms > 3000:
            self._log(f"_build_status_heavy slow: {_bsh_ms}ms summary={_summary_ms}ms tasks={_tasks_ms}ms", "warning")
        return {
            "summary": summary,
            "tasks": self._build_task_list(),
            "options": self._cached_options(),
        }

    def _light_status(self) -> Dict[str, Any]:
        """轻量壳:冷启动首屏用。任务配置/阶段都算(本地快)，目标进度仅补“配置面”(轻量)。

        供后台构建重数据期间先返回,避免首屏卡 7~10s；前端见到 warming 会快速重拉。
        """
        try:
            total = len(self._task_configs)
            enabled = sum(1 for t in self._task_configs.values() if task_is_running(t))
            tasks = []
            for task in self._task_configs.values():
                try:
                    tasks.append({
                        **task.to_dict(),
                        **self._phase_info(task.id),
                        **self._task_goal_status(task, light=True),
                    })
                except Exception:
                    tasks.append(task.to_dict())
        except Exception as err:
            self._log(f"构建轻量总览失败:{err}", "warning")
            total, enabled, tasks = 0, 0, []
        try:
            tasks.append(self._silent_host_card())
        except Exception:  # noqa: BLE001
            pass
        summary = {
            "total_tasks": total,
            "enabled_tasks": enabled,
            "seeding_count": 0,
            "bonus_per_hour": 0.0,
            "current_bonus": 0.0,
            "ceiling": 0.0,
            "ceiling_pct": 0.0,
            "site_upload": 0,
            "site_download": 0,
            "site_ratio": 0.0,
        }
        return {"summary": summary, "tasks": tasks, "options": self._cached_options()}

    def _refresh_status_async(self) -> None:
        """后台异步刷新总览重数据(stale-while-revalidate,不阻塞请求)。"""
        if getattr(self, "_status_refreshing", False):
            return

        def _worker() -> None:
            self._status_refreshing = True
            try:
                heavy = self._build_status_heavy()
                self._status_heavy = heavy
                self._status_heavy_at = time.time()
                self._status_warm_fails = 0
            except Exception as err:
                self._status_warm_fails = int(getattr(self, "_status_warm_fails", 0) or 0) + 1
                self._log(f"后台刷新总览失败:{err}", "warning")
            finally:
                self._status_refreshing = False

        try:
            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            pass

    def get_status(self) -> Response:
        """获取插件总览状态(重数据带 STATUS_TTL 缓存 + 后台静默刷新)。

        冷启动不再同步阻塞:首次调用立即返回**轻量壳**(配置/阶段/目标,不算下载器
        实时统计)并后台构建重数据,前端见 `warming=true` 会快速重拉;后台连续失败
        时才同步兜底(正确性优先)。
        """
        now = time.time()
        heavy = getattr(self, "_status_heavy", None)
        warming = False
        if heavy is None:
            if int(getattr(self, "_status_warm_fails", 0) or 0) >= 2:
                # 后台反复失败:同步兜底,保证拿到真实数据
                heavy = self._build_status_heavy()
                self._status_heavy = heavy
                self._status_heavy_at = now
            else:
                if not getattr(self, "_status_refreshing", False):
                    self._refresh_status_async()
                warming = True
                heavy = self._light_status()
        elif (now - float(getattr(self, "_status_heavy_at", 0.0))) >= STATUS_TTL:
            self._refresh_status_async()
        data = dict(heavy)
        data.update({
            "enabled": self.get_state(),
            "version": __version__,
            "warming": warming,
            "show_sidebar_nav": bool(getattr(self, "_show_sidebar_nav", True)),
            "debug_log": bool(getattr(self, "_debug_log", False)),
            "compact_mode": bool(getattr(self, "_compact_mode", False)),
            "journal_keep": int(getattr(self, "_journal_keep", 200) or 0),
            "request_interval": float(getattr(self, "_request_interval", 0) or 0),
            "bonus_upload_limit_kbps": float(getattr(self, "_bonus_upload_limit_kbps", 200.0) or 0),
            "brush_upload_limit_kbps": float(getattr(self, "_brush_upload_limit_kbps", 10240.0) or 0),
            "seed_up_limit_kbps": float(getattr(self, "_seed_up_limit_kbps", SEED_UP_LIMIT_KBPS_DEFAULT) or 0),
            "brush_seed_up_limit_kbps": float(getattr(self, "_brush_seed_up_limit_kbps", BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT) or 0),
            "tag_model_enabled": bool(self._tags_cfg.get("enabled", True)),
            "tag_silent_new_timeout_hours": round(float(self._tags_cfg.get("new_timeout") or 0) / 3600.0, 3),
            "tag_snapshot_interval_hours": round(float(self._tags_cfg.get("snapshot_interval") or 0) / 3600.0, 3),
            "sort_rules": [dict(r) for r in (self._tags_cfg.get("rules") or [])],
            "iyuu_token": str(getattr(self, "_iyuu_token", "") or ""),
            "iyuu_sites": dict(getattr(self, "_iyuu_sites", {}) or {}),
            "store": self.store_stats(),
            "recommend": dict(getattr(self, "_recommend_cfg", {}) or {}),
            "crossseed": {
                "guard": bool(getattr(self, "_cs_cfg", {}).get("guard", True)),
                "guard_pct": float(getattr(self, "_cs_cfg", {}).get("guard_pct") or 5.0),
                "guard_min_mb": float(getattr(self, "_cs_cfg", {}).get("guard_min_mb") or 50.0),
                "guard_interval_min": float(getattr(self, "_cs_cfg", {}).get("guard_interval_min") or 15.0),
                "keep_seed": bool(getattr(self, "_cs_cfg", {}).get("keep_seed", True)),
                "seed_hours_default": float(getattr(self, "_cs_cfg", {}).get("seed_hours_default") or CROSSSEED_SEED_HOURS_DEFAULT),
                "site_hours": [f"{d}={h:g}" for d, h in sorted((getattr(self, "_cs_cfg", {}).get("site_hours") or {}).items())],
                "reclaim": bool(getattr(self, "_cs_cfg", {}).get("reclaim", False)),
                "rules_auto_refresh": bool(getattr(self, "_rules_cfg", {}).get("auto_refresh", True)),
            },
            "fallback": dict(getattr(self, "_fallback_cfg", {}) or {}),
            "live": dict(getattr(self, "_live_cfg", {}) or {}),
            "signin": self._signin_cfg_view(),
            "cloud": self._cloud_cfg_view(),
            "defaults": dict(getattr(self, "_defaults", {}) or {}),
        })
        return Response(success=True, data=data)
