# -*- coding: utf-8 -*-
"""魔流 · core —— 生命周期与调度（init/service/scheduler/运行状态落地）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from apscheduler.triggers.cron import CronTrigger

from app.api.endpoints.plugin import register_plugin_api
from app.scheduler import Scheduler
from app.schemas.types import EventType
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger

from ..downloader_ops import (
    DownloaderAdapter,
    set_dl_gate_base,
    QB_PAUSED_STATES,
)
from .. import downloader_ops
from ..fetcher import (
    set_request_interval,
    set_browse_debug,
)
from ..models import (
    MagicFlowDefaultsPayload,
)
from ..fallback import FallbackEngine, DEFAULT_SOURCES as FALLBACK_SOURCES
from ..live_stats import LiveStats
from ..collect import Collect
from ..cloud_archive import ArchiveEngine, DEFAULT_TARGET_TEMPLATE as CLOUD_TARGET_TEMPLATE
from ..persistence import MagicFlowStore, OperationItem, WorkReport, KV_FILE_FLUSH_SEC
from ..kvstore import MpHotStore
from ..signin import SigninEngine
from ..sitestore import slot_callbacks
from ..recommend import RecommendEngine
from ..tags import (
    DEFAULT_SORT_RULES,
    STATE_BRUSH,
    is_magicflow_tag,
)


from .. import common  # noqa: F401
from ..common import (
    BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT,
    CLOUD_INTERVAL_MINUTES,
    CLOUD_SCAN_MAX,
    CROSSSEED_SEED_HOURS_DEFAULT,
    CROSSSEED_SITE_HOURS_DEFAULT,
    DELETE_GATE_FAIL_CLOSED,
    CLAIM_BATCH,
    CLAIM_DAILY_PER_SITE,
    CLAIM_INTERVAL_SEC,
    FALLBACK_SCAN_MAX,
    GLOBAL_WORKER_LIMIT,
    HR_DEADLINE_WARN_HOURS_DEFAULT,
    HR_SEED_MARGIN_HOURS_DEFAULT,
    LIVE_DEFAULT_TTL,
    LIVE_DOWNLOAD_ALERT_MB,
    LIVE_INTERVAL_MINUTES,
    LIVE_RATIO_TARGET,
    MagicFlowTaskConfig,
    OPTIONS_TTL,
    RECOMMEND_INTERVAL_MINUTES,
    RESEED_BATCH,
    RESEED_DAILY_PER_SITE,
    RESEED_INTERVAL_MINUTES,
    RESEED_MIN_SIZE_GB,
    RULES_INTERVAL_MINUTES,
    SEED_UP_LIMIT_APPLY_INTERVAL,
    SEED_UP_LIMIT_KBPS_DEFAULT,
    SIGNIN_INTERVAL_MINUTES,
    SIGNIN_QUEUE,
    SIGNIN_RETRY_KEYWORD,
    SIGNIN_TICK_MINUTES,
    HR_HOST_INTERVAL_MINUTES,
    SILENT_HOST_INTERVAL_MINUTES,
    SILENT_HR_SPLIT_ENABLED,
    _MF_ACTIVE,
    _cs_parse_site_hours,
    RUN_MODE_STOPPED,
    begin_decision_round,
    run_mode_of,
    decision_round_stats,
    end_decision_round,
    note_snapshot_pull,
    task_is_participating,
)


class CoreMixin:
    """core 功能集（原 MagicFlow 方法原样搬入）。"""

    def init_plugin(self, config: dict = None) -> None:
        """初始化全局开关、任务配置与持久化存储。"""
        global _MF_ACTIVE
        common._mf_set_active(self)
        raw_config = config or {}
        self._task_locks: Dict[str, threading.Lock] = {}
        self._task_runs: Dict[str, float] = {}
        self._dead_hashes: Dict[str, float] = {}
        self._last_run_times: Dict[str, float] = {}
        self._summary_cache: Optional[Dict[str, Any]] = None
        self._summary_cache_at: float = 0.0
        self._stats_cache: Dict[str, Dict[str, Any]] = {}
        # /status 重数据(总览+任务列表+选项)stale-while-revalidate 缓存
        self._status_heavy: Optional[Dict[str, Any]] = None
        self._status_heavy_at: float = 0.0
        self._status_refreshing: bool = False
        self._enabled = bool(raw_config.get("enabled", False))
        # ★ 12.0.0：升级闸门（migrate_gate / migrate_record_version）随 features/migrate.py 一并退役。
        #   表是唯一真值源；新装库在此幂等灌入身份表种子（原 migrate worker 的 _stage_identity 职责）。
        self._seed_identities()
        self._show_sidebar_nav = bool(raw_config.get("show_sidebar_nav", True))
        self._debug_log = bool(raw_config.get("debug_log", False))
        self._compact_mode = bool(raw_config.get("compact_mode", False))
        # 顶栏功能磁贴显隐（纯界面层）：存「隐藏」白名单，空 = 全部显示
        self._hidden_tiles = [
            str(x).strip() for x in (raw_config.get("hidden_tiles") or []) if str(x or "").strip()
        ]
        try:
            self._journal_keep = int(raw_config.get("journal_keep", 200) or 0)
        except (TypeError, ValueError):
            self._journal_keep = 200
        try:
            self._request_interval = float(raw_config.get("request_interval", 0) or 0)
        except (TypeError, ValueError):
            self._request_interval = 0.0
        try:
            self._bonus_upload_limit_kbps = max(0.0, float(raw_config.get("bonus_upload_limit_kbps", 200.0) or 0))
        except (TypeError, ValueError):
            self._bonus_upload_limit_kbps = 200.0
        try:
            self._brush_upload_limit_kbps = max(0.0, float(raw_config.get("brush_upload_limit_kbps", 10240.0) or 0))
        except (TypeError, ValueError):
            self._brush_upload_limit_kbps = 10240.0
        try:
            self._seed_up_limit_kbps = max(0.0, float(raw_config.get("seed_up_limit_kbps", SEED_UP_LIMIT_KBPS_DEFAULT) or 0))
        except (TypeError, ValueError):
            self._seed_up_limit_kbps = SEED_UP_LIMIT_KBPS_DEFAULT
        try:
            self._brush_seed_up_limit_kbps = max(0.0, float(raw_config.get("brush_seed_up_limit_kbps", BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT) or 0))
        except (TypeError, ValueError):
            self._brush_seed_up_limit_kbps = BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT
        self._seed_up_limit_last = None
        self._last_up_limit_bps = None
        try:
            _sr = raw_config.get("sort_rules")
            _sr = [dict(r) for r in _sr if isinstance(r, dict)] if isinstance(_sr, list) else []
        except Exception:  # noqa: BLE001
            _sr = []
        self._tags_cfg = {
            "enabled": bool(raw_config.get("tag_model_enabled", True)),
            "show_qb_tags": bool(raw_config.get("show_qb_tags", True)),
            "new_timeout": max(0.0, float(raw_config.get("tag_silent_new_timeout_hours", 24.0) or 0)) * 3600.0,
            "host_interval": max(5.0, float(raw_config.get("silent_host_interval_minutes", 60.0) or 60.0)),
            "hr_host_interval": max(5.0, float(raw_config.get("hr_host_interval_minutes", HR_HOST_INTERVAL_MINUTES) or HR_HOST_INTERVAL_MINUTES)),
            "rules": _sr or [dict(r) for r in DEFAULT_SORT_RULES],
        }
        # IYUU 云端辅种配置(Token 为空 = 不启用)
        self._iyuu_token = str(raw_config.get("iyuu_token") or "").strip()
        if not self._iyuu_token:
            # 配置里没有 → 回落插件数据(前端/手滑增删设置也不会丢密)
            try:
                self._iyuu_token = str(self.get_data("iyuu_token") or "").strip()
            except Exception:  # noqa: BLE001
                self._iyuu_token = ""
        _iyuu_sites = raw_config.get("iyuu_sites")
        if not isinstance(_iyuu_sites, dict):
            _iyuu_sites = slot_callbacks(self, "iyuu_sites")[0]() or {}
        self._iyuu_sites = {
            str(k).strip().lower(): dict(v)
            for k, v in (_iyuu_sites or {}).items()
            if isinstance(v, dict)
        }
        self._iyuu_client = self._build_iyuu_client(self._iyuu_token)
        # PV 预算(3.7.1):0=不限。「站点覆盖」优先于全局默认;存 save_data(跨重装保留)。
        _pv_budget = raw_config.get("pv_budget")
        if not isinstance(_pv_budget, dict):
            _pv_budget = slot_callbacks(self, "pv_budget")[0]() or {}
        _pv_cfg: Dict[str, int] = {}
        for _k, _v in (_pv_budget or {}).items():
            try:
                _sid = str(int(_k))
                _num = max(0, int(_v or 0))
            except (TypeError, ValueError):
                continue
            if _num > 0:
                _pv_cfg[_sid] = _num
        self._pv_budget_cfg = _pv_cfg
        try:
            self._pv_default_budget = max(0, int(raw_config.get("pv_default_budget", 0) or 0))
        except (TypeError, ValueError):
            self._pv_default_budget = 0
        rows_defaults = raw_config.get("defaults")
        if not isinstance(rows_defaults, dict):
            rows_defaults = self.get_data("defaults") or {}
            if not isinstance(rows_defaults, dict):
                rows_defaults = {}
        try:
            self._defaults = MagicFlowDefaultsPayload(**rows_defaults).model_dump()
        except Exception:
            self._defaults = MagicFlowDefaultsPayload().model_dump()

        # 刷流种甄别与推荐(价值生命周期)
        def _rf(v: Any, d: float) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return d

        self._recommend_cfg = {
            "enabled": bool(raw_config.get("recommend_enabled", True)),
            "min_rating": _rf(raw_config.get("recommend_min_rating"), 7.5),
            "require_chart": bool(raw_config.get("recommend_require_chart", True)),
            "expire_days": _rf(raw_config.get("recommend_expire_days"), 7.0),
            "tag": str(raw_config.get("recommend_tag") or "魔流-推荐").strip() or "魔流-推荐",
            "auto_import": bool(raw_config.get("recommend_auto_import", True)),
            "notify": bool(raw_config.get("recommend_notify", True)),
            "temp_ttl_days": _rf(raw_config.get("recommend_temp_ttl_days"), 7.0),
            "disk_min_free_gb": _rf(raw_config.get("recommend_disk_min_free_gb"), 50.0),
            # ★ 评分源：douban=豆瓣优先(取不到回退 TMDB) / tmdb（Master 2026-09-28 09:06 选 A）
            "rating_source": str(raw_config.get("recommend_rating_source") or "tmdb").strip().lower(),
            "douban_max_per_run": int(_rf(raw_config.get("recommend_douban_max_per_run"), 30.0)),
            "douban_service_url": str(raw_config.get("recommend_douban_service_url") or "").strip(),
        }
        # ★ 11.2.1 死种补源（rescue）：停滞阈值 / 候选上限（设置面板可调）
        self._rescue_cfg = {
            "stall_hours": _rf(raw_config.get("rescue_stall_hours"), 6.0),
            "max_candidates": int(_rf(raw_config.get("rescue_max_candidates"), 3.0)),
        }
        # ★ 11.13.0 H&R 安全垫 + 临近到期预警（设置面可改；常量在 common.py）
        self._hr_seed_margin_hours = _rf(raw_config.get("hr_seed_margin_hours"),
                                         HR_SEED_MARGIN_HOURS_DEFAULT)
        self._hr_deadline_warn_hours = _rf(raw_config.get("hr_deadline_warn_hours"),
                                           HR_DEADLINE_WARN_HOURS_DEFAULT)
        # ★ 3.22.4 一次性迁移：Master 2026-09-28 09:42「还是别走豆瓣了吧」→ 默认回到 TMDB。
        #   存量配置里若还写着 douban（旧默认被自动落盘的），只在这一版强制改回 tmdb 并落盘；
        #   之后 Master 在设置里手动选「豆瓣优先」不会再被覆盖（标记已置位）。
        try:
            if not self.get_data("rating_source_migrated_3224"):
                if str(self._recommend_cfg.get("rating_source") or "").strip().lower() == "douban":
                    self._recommend_cfg["rating_source"] = "tmdb"
                    self._log("设置迁移:评分源 douban → tmdb（默认不走豆瓣）")
                    threading.Thread(target=self._save_config, daemon=True).start()
                self.save_data(key="rating_source_migrated_3224", value=True)
        except Exception as err:  # noqa: BLE001
            self._log(f"评分源迁移失败:{err}", "warning")
        # 静默-普通清理（Master 01:17：「普通考核魔力产出…在魔力产出够的情况下普通的直接干」）
        self._silent_cfg = {
            "sweep": bool(raw_config.get("silent_sweep_enabled", True)),
            "ratio": _rf(raw_config.get("silent_plain_ratio"), 0.5),
            # ★ 7.20.0：磁盘压力触发「静默-普通」清理 —— 池用量 ≥ 水位时不再等站点魔力达标
            "disk_pressure": bool(raw_config.get("silent_plain_disk_pressure", True)),
            "watermark": _rf(raw_config.get("silent_plain_watermark"), 0.85),
            # ★ 7.21.0：水位驱动 · 清到目标线（Master 08:33「上限 85% 一直清到 75% 才合格」）
            "target_pct": _rf(raw_config.get("silent_plain_target_pct"), 0.75),
            # 高产护线（产出 > 中位 × max_ratio → 留，不再往下清）
            "max_ratio": _rf(raw_config.get("silent_plain_max_ratio"), 2.0),
        }
        self._recommend_engine = RecommendEngine(self)
        self._recommend_cursor = ""

        # ★ 全站辅种（本机驱动：本机已有资源 → 去各站落户，零下载）Master 2026-09-30
        try:
            _rs_sites = raw_config.get("reseed_sites")
            if isinstance(_rs_sites, str):
                _rs_sites = [x.strip() for x in _rs_sites.replace("，", ",").split(",") if x.strip()]
            if not isinstance(_rs_sites, list):
                _rs_sites = []
            self._reseed_enabled = bool(raw_config.get("reseed_enabled", False))
            self._reseed_sites = [str(x).strip() for x in _rs_sites if str(x).strip()]
            self._reseed_daily = int(_rf(raw_config.get("reseed_daily_per_site"),
                                        float(RESEED_DAILY_PER_SITE)))
            self._reseed_batch = int(_rf(raw_config.get("reseed_batch"), float(RESEED_BATCH)))
            self._reseed_min_size_gb = _rf(raw_config.get("reseed_min_size_gb"), RESEED_MIN_SIZE_GB)
            self._reseed_dry = bool(raw_config.get("reseed_dry", True))
        except Exception as err:  # noqa: BLE001
            self._log(f"全站辅种:配置读取失败 {err}", "warning")

        # ★ 认领（claim，7.14.0）：把「我们在做种」的种在站点侧认领掉，换站点权益
        try:
            _cl_sites = raw_config.get("claim_sites")
            if isinstance(_cl_sites, str):
                _cl_sites = [x.strip() for x in _cl_sites.replace("，", ",").split(",") if x.strip()]
            if not isinstance(_cl_sites, list):
                _cl_sites = []
            self._claim_enabled = bool(raw_config.get("claim_enabled", False))
            self._claim_dry = bool(raw_config.get("claim_dry", True))
            self._claim_sites = [str(x).strip().lower() for x in _cl_sites if str(x).strip()]
            self._claim_daily = int(_rf(raw_config.get("claim_daily_per_site"),
                                        float(CLAIM_DAILY_PER_SITE)))
            self._claim_batch = int(_rf(raw_config.get("claim_batch"), float(CLAIM_BATCH)))
            self._claim_interval_sec = _rf(raw_config.get("claim_interval_sec"), CLAIM_INTERVAL_SEC)
            self._claim_min_age_days = _rf(raw_config.get("claim_min_age_days"), 0.0)
            self._claim_require_seeders = int(_rf(raw_config.get("claim_require_seeders"), 0.0))
            self._claim_min_size_gb = _rf(raw_config.get("claim_min_size_gb"), 0.0)
            self._claim_exclude_zero_bonus = bool(raw_config.get("claim_exclude_zero_bonus", True))
        except Exception as err:  # noqa: BLE001
            self._log(f"认领:配置读取失败 {err}", "warning")

        # 跨站辅种：兄弟站「流量兜底」（判「免费」可能错 → 必须实时核对，错了立刻止损）
        self._cs_cfg = {
            "guard": bool(raw_config.get("crossseed_guard", True)),
            "guard_pct": _rf(raw_config.get("crossseed_guard_pct"), 5.0),
            "guard_min_mb": _rf(raw_config.get("crossseed_guard_min_mb"), 50.0),
            "guard_interval_min": _rf(raw_config.get("crossseed_guard_interval_min"), 15.0),
            "keep_seed": bool(raw_config.get("crossseed_guard_keep_seed", True)),
            "seed_hours_default": _rf(raw_config.get("crossseed_seed_hours_default"), CROSSSEED_SEED_HOURS_DEFAULT),
            "site_hours": _cs_parse_site_hours(
                raw_config.get("crossseed_site_hours") or CROSSSEED_SITE_HOURS_DEFAULT
            ),
            "reclaim": bool(raw_config.get("crossseed_reclaim", False)),
        }
        self._cs_guard_at: Dict[str, float] = {}
        # ★ 迁移：学校历史上的 10h（把「平均每天做种10小时」当成 H&R）/ 20h（只取达到线）
        #   都是保守不足的。rules.php 原文：**10 天内做种≥20 小时**（窗口 10 天）。
        #   保守做法 = 保护期取满**窗口**（240h）——我们的账本按墙钟计时，
        #   暂停 / 无 peer 时墙钟 ≠ 实际做种时长，取窗口才不出事。
        try:
            _sh = self._cs_cfg.get("site_hours") or {}
            if isinstance(_sh, dict):
                _changed = False
                for _k in ("pt.btschool.club", "btschool.club"):
                    if _k in _sh and float(_sh.get(_k) or 0) in (10.0, 20.0):
                        _sh[_k] = 240.0
                        _changed = True
                if _changed:
                    self.save_data(key="crossseed_cfg", value=dict(self._cs_cfg))
                    logger.info("跨站:学校保种时长迁移 →240h（保守：取满 10 天窗口）")
        except Exception:  # noqa: BLE001
            pass
        # ★ 咖啡(ptcafe.club)：rules.php **没有 H&R 条款**（主人确认）→ 手填「无 H&R」，
        #   免得被 myhr.php 页面里的 H&R 字样探测成「有」。一次性写入，之后可手动恢复。
        try:
            _mig = dict(self.get_data("rules_migrations") or {})
            if not _mig.get("ptcafe_nohr_v1"):
                _st = self._site_rules()
                _st.put("ptcafe.club", {
                    "hr": False, "seed_hours": 0.0, "source": "manual", "confidence": "high",
                    "evidence": "手填：咖啡无 H&R 条款（rules.php 原文无），不做 H&R 保护",
                })
                _mig["ptcafe_nohr_v1"] = True
                self.save_data(key="rules_migrations", value=_mig)
                logger.info("站点规则:咖啡已标记为「无 H&R」（手填，不做保种保护）")
        except Exception:  # noqa: BLE001
            pass
        # ★ 馒头(m-team.cc)：Master 2026-09-29「馒头规则里没有 H&R，也没发现他有 H&R」→ 手填「无 H&R」。
        #   一次写入；手填记录受 merge_probe 保护，之后探测不会把它改回去。
        try:
            _mig3 = dict(self.get_data("rules_migrations") or {})
            if not _mig3.get("mteam_nohr_v1"):
                _st3 = self._site_rules()
                _st3.put("m-team.cc", {
                    "hr": False, "seed_hours": 0.0, "source": "manual", "confidence": "high",
                    "evidence": "手填：馒头无 H&R（Master 2026-09-29：规则里没有 H&R）",
                })
                _mig3["mteam_nohr_v1"] = True
                self.save_data(key="rules_migrations", value=_mig3)
                logger.info("站点规则:馒头已标记为「无 H&R」（手填，不做 H&R 保种保护）")
        except Exception:  # noqa: BLE001
            pass
        # ★ 3.46.0：馒头「做种数上限 100」是**误读** —— 官方公式里 ``torrentMsSum`` 是
        #   「**计入魔力**的做种数上限」（超过后时魔不再增长），**不是站点数量禁令**。
        #   官方 wiki 规则页也全站无「做种数上限」条款 → 清掉规则库里存的 seed_cap 值。
        try:
            _mig5 = dict(self.get_data("rules_migrations") or {})
            if not _mig5.get("mteam_nocap_v1"):
                _st5 = self._site_rules()
                _touched = []
                for _dom in ("m-team.cc", "kp.m-team.cc"):
                    if (_st5.get(_dom) or {}).get("seed_cap") is not None:
                        _st5.put(_dom, {
                            "seed_cap": None,
                            "source": "manual",
                            "evidence": "官方 wiki/API：馒头无做种数上限；100 只是魔力公式「计入上限」"
                                        "(torrentMsSum) —— 收益口径，非禁令",
                        })
                        _touched.append(_dom)
                _mig5["mteam_nocap_v1"] = True
                self.save_data(key="rules_migrations", value=_mig5)
                if _touched:
                    logger.info(
                        "站点规则:馒头「做种数上限」已作废(%s) —— 100 实为魔力计入上限，非禁令",
                        ",".join(_touched),
                    )
        except Exception:  # noqa: BLE001
            pass
        # ★ 单种上传限速默认值迁移(3.12.0)：旧默认 100 KB/s 正好压在
        #   咖啡「恶意限速判定：单人做种 6h 内稳定 <100Kb/s」线上 → 抬到 200。
        #   只迁移「恰好等于旧默认值」的配置，且只跑一次（用户手填 100 不会被反复改回去）。
        try:
            _mig2 = dict(self.get_data("rules_migrations") or {})
            if not _mig2.get("seed_up_200_v1"):
                try:
                    _cur_up = float(getattr(self, "_seed_up_limit_kbps", 0) or 0)
                except (TypeError, ValueError):
                    _cur_up = 0.0
                if abs(_cur_up - 100.0) < 1e-6:
                    self._seed_up_limit_kbps = SEED_UP_LIMIT_KBPS_DEFAULT
                    threading.Thread(target=self._save_config, daemon=True).start()
                    logger.info("挂种限速:单种上传限速旧默认 100 已迁移为 200 KB/s")
                _mig2["seed_up_200_v1"] = True
                self.save_data(key="rules_migrations", value=_mig2)
        except Exception:  # noqa: BLE001
            pass
        # ★ 站点规则库(H&R/保种/做种上限)：自动刷新开关(3.12.0)
        self._rules_cfg: Dict[str, Any] = {
            "auto_refresh": bool(raw_config.get("rules_auto_refresh", True)),
        }
        # 把规则库里的「促销规则」注入选种器（体积自动免费等），启动即生效
        self._sync_free_rules()

        # 元数据兜底(多源识别 + 补 NFO):TMDB 没有的(番剧特别篇/前传/国漫)自动兜底
        def _fsources(v: Any) -> List[str]:
            if isinstance(v, (list, tuple)) and v:
                out = [str(x).strip().lower() for x in v if str(x or "").strip()]
                if out:
                    return out
            return list(FALLBACK_SOURCES)

        self._fallback_cfg = {
            "enabled": bool(raw_config.get("fallback_enabled", True)),
            "sources": _fsources(raw_config.get("fallback_sources")),
            "paths": [
                str(p).strip() for p in (raw_config.get("fallback_paths") or [])
                if str(p or "").strip()
            ] if isinstance(raw_config.get("fallback_paths"), (list, tuple)) else [],
            "interval": _rf(raw_config.get("fallback_interval_minutes"), 30.0),
            "scan_max": int(raw_config.get("fallback_scan_max") or FALLBACK_SCAN_MAX),
            "sp_to_s00": bool(raw_config.get("fallback_sp_to_s00", False)),
            "after_import": bool(raw_config.get("fallback_after_import", True)),
            "dry_run": bool(raw_config.get("fallback_dry_run", False)),
        }
        if getattr(self, "_fallback_engine", None) is None:
            self._fallback_engine = FallbackEngine(self, self._fallback_cfg)
        else:
            self._fallback_engine.set_cfg(self._fallback_cfg)

        # 站点实时数据 + 流量监控(不依赖 MP 的 6 小时站点数据快照)
        self._live_cfg = {
            "enabled": bool(raw_config.get("live_enabled", True)),
            "interval": _rf(raw_config.get("live_interval_minutes"), float(LIVE_INTERVAL_MINUTES)),
            "download_alert_mb": _rf(raw_config.get("live_download_alert_mb"), LIVE_DOWNLOAD_ALERT_MB),
            "ratio_target": _rf(raw_config.get("live_ratio_target"), LIVE_RATIO_TARGET),
            "auto_stop": bool(raw_config.get("live_auto_stop", False)),
            "kill_unfree": bool(raw_config.get("live_kill_unfree", True)),
            "kill_delete_files": bool(raw_config.get("live_kill_delete_files", True)),
            # ★ 流量兜底总开关(3.37.4)：一个系统、三条证据(任务内/全局列表/取种期间)，见 docs/MODULES.md X2
            "promo_guard": bool(raw_config.get("promo_guard", True)),
            "notify": bool(raw_config.get("live_notify", True)),
            "exam_enabled": bool(raw_config.get("exam_enabled", False)),
            "exam_include_pass": bool(raw_config.get("exam_include_pass", False)),
            "exam_sites": [str(x) for x in (raw_config.get("exam_sites") or []) if str(x or "").strip()]
            if isinstance(raw_config.get("exam_sites"), (list, tuple)) else [],
        }
        # ★ 采集模块（唯一外部取数/取网出口；见 docs/PLAN-collect.md）
        if getattr(self, "collect", None) is None:
            try:
                self.collect = Collect(self, tier=self._cache_collect())
            except Exception as _c_err:  # noqa: BLE001
                self._log(f"魔流:采集模块初始化失败:{_c_err}", "error")
                self.collect = None
            if getattr(self, "collect", None) is not None:
                try:
                    from ..fetcher import set_collect as _fetcher_set_collect
                    _fetcher_set_collect(self.collect)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    from ..sites.formula_fetch import set_collect as _formula_set_collect
                    _formula_set_collect(self.collect)
                except Exception:  # noqa: BLE001
                    pass
                # 采集者登记：外部服务 + 本地下载器（实现仍在原处，这里只登记，让它"看得见"）
                for _svc_name in ("豆瓣评分", "IYUU 云端", "云盘归档"):
                    try:
                        self.collect.register_service(_svc_name)
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    if getattr(self, "_downloader_ops", None) is not None:
                        self.collect.register_service("下载器", self._downloader_ops)
                except Exception:  # noqa: BLE001
                    pass
        if getattr(self, "_live", None) is None:
            self._live = LiveStats(self, ttl=LIVE_DEFAULT_TTL)
        self._live.exam_enabled = bool(self._live_cfg.get("exam_enabled", False))
        # 缓存 TTL 跟随采样周期(Master 定调:60s 太频繁,240s)
        self._live.ttl = max(60.0, float(self._live_cfg.get("interval") or LIVE_INTERVAL_MINUTES) * 60.0)

        # 站点签到 / 模拟登录(借鉴「站点自动签到」插件:多选站点 + GET attendance.php)
        self._signin_cfg = {
            "enabled": bool(raw_config.get("signin_enabled", False)),
            "sites": [str(x) for x in (raw_config.get("signin_sites") or []) if str(x or "").strip()]
            if isinstance(raw_config.get("signin_sites"), (list, tuple)) else [],
            "login_sites": [str(x) for x in (raw_config.get("signin_login_sites") or []) if str(x or "").strip()]
            if isinstance(raw_config.get("signin_login_sites"), (list, tuple)) else [],
            "retry_keyword": str(raw_config.get("signin_retry_keyword") or SIGNIN_RETRY_KEYWORD),
            "queue": int(raw_config.get("signin_queue") or SIGNIN_QUEUE),
            "notify": bool(raw_config.get("signin_notify", True)),
            "interval": _rf(raw_config.get("signin_interval_minutes"), float(SIGNIN_INTERVAL_MINUTES)),
            "window_start": int(raw_config.get("signin_window_start") if raw_config.get("signin_window_start") is not None else 9),
            "window_end": int(raw_config.get("signin_window_end") if raw_config.get("signin_window_end") is not None else 23),
        }
        if getattr(self, "_signin", None) is None:
            self._signin = SigninEngine(self)

        # 云盘归档(夸克冷库):本地当热区、夸克当冷库
        #  Token 优先用配置;配置为空时回落插件数据(前端/手滑增删设置也不会丢密)
        _cloud_token = str(raw_config.get("cloud_openlist_token") or "").strip()
        if not _cloud_token:
            try:
                _cloud_token = str(self.get_data("cloud_token") or "").strip()
            except Exception:  # noqa: BLE001
                _cloud_token = ""
        _cloud_paths = raw_config.get("cloud_paths")
        _cloud_excl = raw_config.get("cloud_exclude_paths")
        _cloud_tags = raw_config.get("cloud_exclude_tags")
        self._cloud_cfg = {
            "enabled": bool(raw_config.get("cloud_enabled", False)),
            "url": str(raw_config.get("cloud_openlist_url") or "http://192.168.0.61:12022").strip(),
            "token": _cloud_token,
            "source_mount": str(raw_config.get("cloud_source_mount") or "/quark").strip() or "/quark",
            "strm_mount": str(raw_config.get("cloud_strm_mount") or "/movie").strip() or "/movie",
            "library_root": "/movie",
            "paths": [str(p).strip() for p in (_cloud_paths or []) if str(p or "").strip()]
            if isinstance(_cloud_paths, (list, tuple)) else [],
            "target_template": str(raw_config.get("cloud_target_template") or CLOUD_TARGET_TEMPLATE).strip(),
            "interval": _rf(raw_config.get("cloud_interval_minutes"), float(CLOUD_INTERVAL_MINUTES)),
            "scan_max": int(_rf(raw_config.get("cloud_scan_max"), float(CLOUD_SCAN_MAX))),
            "min_size_gb": _rf(raw_config.get("cloud_min_size_gb"), 2.0),
            "max_size_gb": _rf(raw_config.get("cloud_max_size_gb"), 200.0),
            "min_age_days": _rf(raw_config.get("cloud_min_age_days"), 30.0),
            "exclude_paths": [str(p).strip() for p in (_cloud_excl or []) if str(p or "").strip()]
            if isinstance(_cloud_excl, (list, tuple)) else ["/movie/刷流", "/movie/下载"],
            "exclude_tags": [str(t).strip() for t in (_cloud_tags or []) if str(t or "").strip()]
            if isinstance(_cloud_tags, (list, tuple)) else ["魔流-推荐"],
            "upload_limit_mbps": _rf(raw_config.get("cloud_upload_limit_mbps"), 0.0),
            "verify": str(raw_config.get("cloud_verify") or "size").strip() or "size",
            "dry_run": bool(raw_config.get("cloud_dry_run", True)),
            "delete_local": bool(raw_config.get("cloud_delete_local", False)),
            "remove_torrent": bool(raw_config.get("cloud_remove_torrent", False)),
            "notify": bool(raw_config.get("cloud_notify", True)),
        }
        if getattr(self, "_cloud_engine", None) is None:
            self._cloud_engine = ArchiveEngine(self, self._cloud_cfg)
        else:
            self._cloud_engine.set_cfg(self._cloud_cfg)

        # 在线热层：走 MoviePilot 自己的缓存配置（配了 Redis 就用，没配就纯文件）
        # 开源插件不能假设用户装了 Redis / 会单独建库（Master 2026-09-27 定）。
        self._hot = self._build_hot()
        self._store = MagicFlowStore(self.get_data_path(), kv=self._hot)
        try:
            # 重载后让落盘间隔/热层跟上新代码（单例跨重载存在）
            self._store.set_flush_sec(KV_FILE_FLUSH_SEC)
        except Exception as err:  # noqa: BLE001
            self._log(f"状态落盘间隔设置失败:{err}", "debug")

        # ★ 删除唯一入口（Master 2026-10-05「删除令出一门」补洞）：把「硬保护闸门 + 统一台账」
        #   注册成**进程级安装器** —— 之后任何 ``DownloaderAdapter(...)``（含不经 _get_downloader
        #   的裸构造）在 __init__ 末尾都会自动挂闸门，消除「类属性 _global_gate 至少被设过一次」
        #   的顺序依赖（热重载后类属性归零 → 裸构造先跑 → 删种无闸门）。
        #   同时设定 fail-closed 策略（默认开）：闸门取不到 / 抛异常时一律阻断删除，不放行。
        #   注：用 ``self._delete_gate`` / ``self._delete_log_cb`` 在调用时解析（不捕获 stale 绑定）。
        try:
            def _install_delete_gate(_dl) -> None:
                _dl.gate = self._delete_gate
                _dl.deletion_log = self._delete_log_cb
                type(_dl)._global_gate = self._delete_gate
                type(_dl)._global_dlog = self._delete_log_cb
            downloader_ops.set_gate_installer(_install_delete_gate)
            downloader_ops.set_gate_fail_closed(bool(DELETE_GATE_FAIL_CLOSED))
            logger.info(
                "魔流删除闸门:安装器已注册（裸构造自动挂闸门）；fail-closed=%s"
                % bool(DELETE_GATE_FAIL_CLOSED)
            )
        except Exception as _wire_err:  # noqa: BLE001
            logger.error(f"魔流删除闸门:安装器注册失败:{_wire_err}")

        # ★ 10.2.0 下载即开账（影子记账）：注册 H&R 开账钩子 + 初始化账单 store。
        #   钩子用「调用时解析 self._hrbills_open」的闭包（不捕获 stale 绑定，热重载安全）。
        #   11.0.0 第二阶段起 HR_BILLS_ENFORCE=True：账单作为 _hr_obligation 的第三来源（只增保护）。
        try:
            from .. import downloader_ops as _dlops  # noqa: WPS433

            def _hr_open_hook(_hs, _site_domain, _tag, _content, _hit_and_run=False):
                _fn = getattr(self, "_hrbills_open", None)
                if callable(_fn):
                    _fn(_hs, _site_domain, _tag, _content, hit_and_run=_hit_and_run)
            _dlops.set_hr_open_hook(_hr_open_hook)
            self._hrbills_store()
            logger.info("魔流H&R账单:开账钩子已注册（账单已生效，接入 _hr_obligation 第三来源）")
        except Exception as _hr_wire_err:  # noqa: BLE001
            logger.error(f"魔流H&R账单:注册失败:{_hr_wire_err}")

        self._apply_runtime_settings()

        # 任务配置:优先从 config 读取,兼容旧版 plugindata
        rows = raw_config.get("tasks")
        if not isinstance(rows, list):
            rows = self.get_data("task_configs") or []
            if not isinstance(rows, list):
                rows = []

        self._task_configs = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            task = MagicFlowTaskConfig.from_dict(row)
            if not task.id:
                task.id = uuid.uuid4().hex[:12]
            # ★ 标签模型（3.13.0）：任务的标签改为「站点级状态标签」自动派生
            #   brush 任务 → 魔流-<站点>-刷流；其余 → 魔流-<站点>-魔力
            #   仅当为空 / 看起来是自动生成的魔流标签时才改写；用户自定义的标签保持不动。
            try:
                _derived = self._task_tag(task)
            except Exception:  # noqa: BLE001
                _derived = ""
            _cur = str(task.brush_tag or "").strip()
            if _derived and (not _cur or is_magicflow_tag(_cur) or _cur.startswith("刷流-")):
                task.brush_tag = _derived
            elif not _cur:
                task.brush_tag = f"魔流-{task.name or task.id}"
            self._task_configs[task.id] = task

        # ★ 14.0.0：确保存在「跨站取种」全局真任务（承接刷流任务发起的取种下载）
        try:
            self._ensure_crossseed_task()
        except Exception as _cst_err:  # noqa: BLE001
            logger.error(f"魔流:创建「跨站取种」任务失败:{_cst_err}")

        # 回写规范化配置
        self._save_config()

        # 预热总览重数据(后台):让用户首次打开工作台时缓存已就绪、秒显。
        try:
            self._refresh_status_async()
        except Exception:
            pass

    def _seed_identities(self) -> None:
        """幂等灌入身份表种子（12.0.0：migrate worker 退役后由这里兜底）。

        只在 ``mf_identity`` 空表时插入一次 ``tables.DEFAULT_IDENTITIES``；
        已迁移的库（含线上 3 行）不受影响。原职责在 ``features/migrate.py::_stage_identity``。
        """
        try:
            from sqlalchemy import func, select as _select
            from .. import db as _db
            from .. import tables as _tables
            _db.Base.metadata.create_all(self.get_database().engine)  # 幂等：缺表才建
            with self.get_database().session() as _sess:
                if int(_sess.execute(_select(func.count()).select_from(_db.IdentityRow)).scalar() or 0) > 0:
                    return
                for _row in _tables.DEFAULT_IDENTITIES:
                    _sess.add(_db.IdentityRow(**dict(_row)))
                _sess.commit()
        except Exception as _seed_err:  # noqa: BLE001
            logger.warning(f"魔流身份表种子灌入失败:{_seed_err}")

    # ---------------------------------------------------------
    # 插件契约
    # ---------------------------------------------------------

    def get_state(self) -> bool:
        """返回插件全局启用状态"""
        return bool(getattr(self, "_enabled", False))

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """当前插件不注册远程命令"""
        return []

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        """声明使用 Vue 联邦组件渲染插件界面"""
        return "vue", "dist/assets"

    def get_sidebar_nav(self) -> List[Dict[str, Any]]:
        """向主界面整理分组注册魔流入口"""
        if not self.get_state() or not getattr(self, "_show_sidebar_nav", True):
            return []
        return [
            {
                "nav_key": "main",
                "title": "魔流",
                "icon": "mdi-magnet",
                "section": "organize",
                "permission": "manage",
                "order": 46,
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """Vue 配置组件只需要接收当前配置模型"""
        return [], self._current_config()

    def get_page(self) -> List[dict]:
        """Vue 详情组件自行通过插件 API 获取页面数据"""
        return []

    def get_dashboard(self, key: str, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], None]]:
        """注册魔流仪表板卡片,由 Vue 组件渲染"""
        if not self.get_state():
            return None
        return (
            {"cols": 12, "sm": 6, "md": 6},
            {
                "title": "魔流",
                "subtitle": "魔力产出概览",
                "refresh": 30,
                "border": True,
            },
            None,
        )

    def get_service(self) -> List[Dict[str, Any]]:
        """为每个任务注册独立的服务。

        - ``running``:注册 Brush（刷流/补种）+ Check（清理/纳管/H&R）双 worker;
        - ``seeding``:只挂 Check（停调度、已完成种继续做种;纳管同站已有种）;
        - ``stopped``:完全不挂。
        """
        if not self.get_state():
            return []
        services: List[Dict[str, Any]] = []
        for task in self._task_configs.values():
            _mode = self._normalize_run_mode(task.run_mode)
            if _mode == "stopped":
                continue

            if task.cron_expression:
                try:
                    brush_trigger: Union[str, CronTrigger] = CronTrigger.from_crontab(task.cron_expression)
                    brush_kwargs: Dict[str, Any] = {}
                except ValueError as err:
                    logger.error(f"魔流任务 [{task.name}] CRON 表达式无效:{str(err)}")
                    brush_trigger = "interval"
                    brush_kwargs = {"minutes": task.brush_interval}
            else:
                brush_trigger = "interval"
                brush_kwargs = {
                    "minutes": task.brush_interval,
                    "jitter": self._jitter_seconds(task.brush_interval),
                }

            # ★ 3.25.0: seeding 模式只挂 Check,不挂 Brush
            # - running: 补种 + 魔力优化(Brush + Check 双 worker)
            # - seeding: 仅做已完成种继续做种 + 同站纳管 + 清理无进度/挂 H&R(只 Check,不下载、不刷魔力)
            if _mode == "running":
                services.append(
                    {
                        "id": f"Task_{task.id}_Brush",
                        "name": f"魔流 - {task.name}",
                        "trigger": brush_trigger,
                        "func": self.brush,
                        "kwargs": brush_kwargs,
                        "func_kwargs": {"task_id": task.id},
                    }
                )
            services.append(
                {
                    "id": f"Task_{task.id}_Check",
                    "name": f"魔力检查 - {task.name}",
                    "trigger": "interval",
                    "func": self.check,
                    "kwargs": {
                        "minutes": task.check_interval,
                        "jitter": self._jitter_seconds(task.check_interval),
                    },
                    "func_kwargs": {"task_id": task.id},
                }
            )
        # ★ 14.0.0：删除「辅种慢扫」(Reuse worker) 服务——与「全站辅种」(ReSeed) 效果重复。
        # ★ 全站辅种（本机驱动）：插件级单 worker。开关在设置里；没开就不注册。
        if bool(getattr(self, "_reseed_enabled", False)) or bool(
                (self.get_data("reseed_cfg") or {}).get("enabled")):
            services.append(
                {
                    "id": "ReSeed",
                    "name": "全站辅种",
                    "trigger": "interval",
                    "func": self.reseed_scan,
                    "kwargs": {
                        "minutes": RESEED_INTERVAL_MINUTES,
                        "jitter": self._jitter_seconds(RESEED_INTERVAL_MINUTES),
                    },
                }
            )
        # ★ 12.0.0：「账本迁移」一次性 worker 已随 features/migrate.py 退役（三戳已落、migrate_pending 恒 False）。
        # ★ 3.7.1:删除「候选预取」worker。
        #   实测它**不省 PV**——省 PV 靠的是站点级缓存 TTL(已拉长到 1h)+ 缓存持久化;
        #   预取只是把「同一份抓取」换个时间点做,任务数×频率并没有下降,反而多一条线程。
        #   且它调用的 get_cached() 从来没人调(死代码)。一并删除,靠 _fetch_site_candidates
        #   自己的 single-flight + TierCache 就够。
        # ★ 推荐甄别:插件级单 worker(每轮只处理一个任务 → 服务数不随任务数增长)。
        if bool(getattr(self, "_recommend_cfg", {}).get("enabled", True)):
            services.append(
                {
                    "id": "Recommend",
                    "name": "推荐甄别",
                    "trigger": "interval",
                    "func": self.recommend_scan,
                    "kwargs": {
                        "minutes": RECOMMEND_INTERVAL_MINUTES,
                        "jitter": self._jitter_seconds(RECOMMEND_INTERVAL_MINUTES),
                    },
                }
            )
        # ★ 14.0.0：跨站「回辅」worker 已删（挂回 A 站交「全站辅种」）。
        #   取种的「承接 + 生命周期分诊」改由全局真任务「跨站取种」的 Check 周期执行
        #   （features/crossseed.py::_crossseed_tick，30min，见下面任务循环自动注册）。
        # ★ 元数据兜底:插件级单 worker(多源识别 + 给缺 NFO 的集补最小 NFO)。
        if bool(getattr(self, "_fallback_cfg", {}).get("enabled", True)):
            _fb_min = float(getattr(self, "_fallback_cfg", {}).get("interval", 30.0) or 30.0)
            services.append(
                {
                    "id": "Fallback",
                    "name": "元数据兜底",
                    "trigger": "interval",
                    "func": self.fallback_scan,
                    "kwargs": {
                        "minutes": _fb_min,
                        "jitter": self._jitter_seconds(_fb_min),
                    },
                }
            )
        # ★ 站点实时数据 + 流量监控:插件级单 worker(采样所有「运行中 + 做种中」任务的站点)。
        #   主人在意「下载量在涨」这一唯一真危险信号(免费种不吃下载)。
        #   ★ X11(3.37.7):以前这里看派生字段 enabled(= 运行中),导致「做种中」的站在监控外;
        #     改看真源 run_mode——做种中也要盯站(保种/流量/可达性),只有 stopped 才跳过。
        _mw_live_on = bool(getattr(self, "_live_cfg", {}).get("enabled", True)) and any(
            self._normalize_run_mode(getattr(t, "run_mode", ""), getattr(t, "enabled", True))
            != "stopped"
            for t in self._task_configs.values()
        )
        if self._collect_ref() is not None:
            self._collect_ref().mark_worker(
                "站点流量监控",
                registered=_mw_live_on,
                reason="有运行中/做种中任务" if _mw_live_on else "无在跑任务(全 stopped) 或开关关闭",
            )
        if _mw_live_on:
            _live_min = float(getattr(self, "_live_cfg", {}).get("interval", LIVE_INTERVAL_MINUTES) or LIVE_INTERVAL_MINUTES)
            services.append(
                {
                    "id": "LiveWatch",
                    "name": "站点流量监控",
                    "trigger": "interval",
                    "func": self.live_watch,
                    "kwargs": {
                        "minutes": _live_min,
                        "jitter": self._jitter_seconds(_live_min),
                    },
                }
            )
        # ★ 站点规则库:插件级单 worker。低频(默认每周)逐站探测 H&R/保种规则并入库。
        #    启动即把已有规则（含手填/内置）同步给选种器，供促销补判。
        #   规则只影响「来源份要保种多久」——多挂几小时不花钱，少挂是实打实惩罚，
        #   所以这里**宁慢勿缺**，一周一次足够。
        if bool(getattr(self, "_rules_cfg", {}).get("auto_refresh", True)) and (self._list_sites() or []):
            services.append(
                {
                    "id": "Rules",
                    "name": "站点规则刷新",
                    "trigger": "interval",
                    "func": self.rules_watch,
                    "kwargs": {
                        "minutes": RULES_INTERVAL_MINUTES,
                        "jitter": self._jitter_seconds(RULES_INTERVAL_MINUTES),
                    },
                }
            )
        # ★ 标签模型维护（低频 hourly）：静默-新超时归位 + 状态账本快照。
        services.append(
            {
                "id": "Tags",
                "name": "标签账本维护",
                "trigger": "interval",
                "func": self.tags_watch,
                "kwargs": {
                    "minutes": 60,
                    "jitter": self._jitter_seconds(60),
                },
            }
        )
        # ★ 静默托管（**常驻 worker**，Master 2026-09-28 06:30）：静默池的负责人——
        #   清理未下完 / 保挂（恢复做种）/ H&R 统一管理 / 辅种校验 / 分拣 / 静默-新超时 / 资产刷新。
        #   常驻（reload 即注册，不随任务增减开关），低频（默认 60min，可用 silent_host_interval_minutes 调）。
        _sh_min = float(getattr(self, "_tags_cfg", {}).get("host_interval") or SILENT_HOST_INTERVAL_MINUTES)
        # ★ 14.0.0：H&R 保种宿主周期单独可调（默认 15min；不跟随静默托管的 60min）
        _hr_min = float(getattr(self, "_tags_cfg", {}).get("hr_host_interval") or HR_HOST_INTERVAL_MINUTES)
        services.append(
            {
                "id": "SilentHost",
                "name": "静默托管",
                "trigger": "interval",
                "func": self.silent_host,
                "kwargs": {
                    "minutes": _sh_min,
                    "jitter": self._jitter_seconds(_sh_min),
                },
            }
        )
        # ★ H&R 保种宿主（__hr_host__ 常驻 worker，11.11.0）：保挂欠 H&R 的种 + 结清释放。
        #   ★ 14.0.0：周期 60→15min（`hr_host_interval_minutes` 可调）。SILENT_HR_SPLIT_ENABLED=False 时直接 no-op。
        services.append(
            {
                "id": "HrHost",
                "name": "H&R保种",
                "trigger": "interval",
                "func": self.hr_host,
                "kwargs": {
                    "minutes": _hr_min,
                    "jitter": self._jitter_seconds(_hr_min),
                },
            }
        )
        # ★ 站点签到 / 模拟登录:插件级单 worker(借鉴「站点自动签到」插件,多选站点)。
        #   ★ 调度节拍 = min(签到间隔, 15min)：全量跑仍由「签到间隔」把关（signin_last_full），
        #     多出来的轻量 tick 只为了「按 PV 节奏补失败重试」（空闲 tick 不发请求）。
        if bool(getattr(self, "_signin_cfg", {}).get("enabled", False)) and (
            (getattr(self, "_signin_cfg", {}) or {}).get("sites") or (getattr(self, "_signin_cfg", {}) or {}).get("login_sites")
        ):
            _si_min = float(getattr(self, "_signin_cfg", {}).get("interval") or SIGNIN_INTERVAL_MINUTES)
            _si_min = max(1.0, min(_si_min, SIGNIN_TICK_MINUTES))
            services.append(
                {
                    "id": "Signin",
                    "name": "站点签到",
                    "trigger": "interval",
                    "func": self.signin_watch,
                    "kwargs": {
                        "minutes": _si_min,
                        "jitter": self._jitter_seconds(_si_min),
                    },
                }
            )
        return services

    def _build_hot(self):
        """构建在线热层（走 MP 缓存适配器；非 Redis 后端自动退化为纯文件）。"""
        try:
            base = None
            try:
                base = self.get_data_path() / "hotcache"
            except Exception:  # noqa: BLE001
                base = None
            hot = MpHotStore(base=base, log=self._log)
            if hot.is_redis():
                self._log("状态热层已启用:" + hot.describe())
            else:
                self._log("状态热层未启用(MP 未配 Redis)，状态全部走 JSON 文件", "debug")
            return hot
        except Exception as err:  # noqa: BLE001
            self._log(f"状态热层构建失败，退回 JSON 文件:{err}", "debug")
            return None

    def stop_service(self) -> None:
        """插件卸载/停止：停后台落盘线程 + 落一次盘（JSON 才是权威）。"""
        try:
            if getattr(self, "_store", None) is not None:
                written = self._store.flush_all()
                self._store.stop_flusher()
                if written:
                    self._log("状态已落盘:" + ",".join(written), "debug")
        except Exception as err:  # noqa: BLE001
            self._log(f"状态落盘失败:{err}", "debug")
        return None

    @eventmanager.register(EventType.PluginReload)
    def reload(self, event: Event) -> None:
        """插件重载后重新注册动态 API 和任务调度"""
        if event and event.event_data.get("plugin_id") == self.__class__.__name__:
            register_plugin_api(plugin_id=self.__class__.__name__)
            Scheduler().update_plugin_job(self.__class__.__name__)

    # ---------------------------------------------------------
    # 配置持久化
    # ---------------------------------------------------------

    def _current_config(self) -> Dict[str, Any]:
        """返回插件当前可持久化配置快照"""
        return {
            "schema_version": self.DATA_SCHEMA_VERSION,
            "enabled": bool(getattr(self, "_enabled", False)),
            "show_sidebar_nav": bool(getattr(self, "_show_sidebar_nav", True)),
            "debug_log": bool(getattr(self, "_debug_log", False)),
            "compact_mode": bool(getattr(self, "_compact_mode", False)),
            "hidden_tiles": list(getattr(self, "_hidden_tiles", None) or []),
            "journal_keep": int(getattr(self, "_journal_keep", 200) or 0),
            "request_interval": float(getattr(self, "_request_interval", 0) or 0),
            "bonus_upload_limit_kbps": float(getattr(self, "_bonus_upload_limit_kbps", 200.0) or 0),
            "brush_upload_limit_kbps": float(getattr(self, "_brush_upload_limit_kbps", 10240.0) or 0),
            "seed_up_limit_kbps": float(getattr(self, "_seed_up_limit_kbps", SEED_UP_LIMIT_KBPS_DEFAULT) or 0),
            "brush_seed_up_limit_kbps": float(getattr(self, "_brush_seed_up_limit_kbps", BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT) or 0),
            "tag_model_enabled": bool(self._tags_cfg.get("enabled", True)),
            "show_qb_tags": bool(self._tags_cfg.get("show_qb_tags", True)),
            "tag_silent_new_timeout_hours": round(float(self._tags_cfg.get("new_timeout") or 0) / 3600.0, 3),
            "sort_rules": [dict(r) for r in (self._tags_cfg.get("rules") or [])],
            "iyuu_token": str(getattr(self, "_iyuu_token", "") or ""),
            "iyuu_sites": dict(getattr(self, "_iyuu_sites", {}) or {}),
            "recommend_enabled": bool(self._recommend_cfg.get("enabled", True)),
            "recommend_min_rating": float(self._recommend_cfg.get("min_rating", 7.5)),
            "recommend_require_chart": bool(self._recommend_cfg.get("require_chart", True)),
            "recommend_expire_days": float(self._recommend_cfg.get("expire_days", 7.0)),
            "recommend_tag": str(self._recommend_cfg.get("tag", "魔流-推荐")),
            "recommend_auto_import": bool(self._recommend_cfg.get("auto_import", True)),
            "recommend_notify": bool(self._recommend_cfg.get("notify", True)),
            "recommend_temp_ttl_days": float(self._recommend_cfg.get("temp_ttl_days", 7.0)),
            "recommend_disk_min_free_gb": float(self._recommend_cfg.get("disk_min_free_gb", 50.0)),
            "recommend_rating_source": str(self._recommend_cfg.get("rating_source", "tmdb")),
            "recommend_douban_max_per_run": int(self._recommend_cfg.get("douban_max_per_run", 30) or 0),
            "recommend_douban_service_url": str(self._recommend_cfg.get("douban_service_url", "") or ""),
            "rescue_stall_hours": float(getattr(self, "_rescue_cfg", {}).get("stall_hours") or 6.0),
            "hr_seed_margin_hours": float(getattr(self, "_hr_seed_margin_hours",
                                                  HR_SEED_MARGIN_HOURS_DEFAULT) or 0.0),
            "hr_deadline_warn_hours": float(getattr(self, "_hr_deadline_warn_hours",
                                                    HR_DEADLINE_WARN_HOURS_DEFAULT) or 0.0),
            "rescue_max_candidates": int(getattr(self, "_rescue_cfg", {}).get("max_candidates") or 3),
            "crossseed_guard": bool(getattr(self, "_cs_cfg", {}).get("guard", True)),
            "crossseed_guard_pct": float(getattr(self, "_cs_cfg", {}).get("guard_pct") or 5.0),
            "crossseed_guard_min_mb": float(getattr(self, "_cs_cfg", {}).get("guard_min_mb") or 50.0),
            "crossseed_guard_interval_min": float(getattr(self, "_cs_cfg", {}).get("guard_interval_min") or 15.0),
            "crossseed_guard_keep_seed": bool(getattr(self, "_cs_cfg", {}).get("keep_seed", True)),
            "crossseed_seed_hours_default": float(getattr(self, "_cs_cfg", {}).get("seed_hours_default") or CROSSSEED_SEED_HOURS_DEFAULT),
            "crossseed_site_hours": [f"{d}={h:g}" for d, h in sorted((getattr(self, "_cs_cfg", {}).get("site_hours") or {}).items())],
            "crossseed_reclaim": bool(getattr(self, "_cs_cfg", {}).get("reclaim", False)),
            # ★ 全站辅种（本机驱动）
            "reseed_enabled": bool(getattr(self, "_reseed_enabled", False)),
            "reseed_sites": list(getattr(self, "_reseed_sites", None) or []),
            "reseed_daily_per_site": int(getattr(self, "_reseed_daily", RESEED_DAILY_PER_SITE) or 0),
            "reseed_batch": int(getattr(self, "_reseed_batch", RESEED_BATCH) or 1),
            "reseed_min_size_gb": float(getattr(self, "_reseed_min_size_gb", RESEED_MIN_SIZE_GB) or 0.0),
            "reseed_dry": bool(getattr(self, "_reseed_dry", True)),
            # ★ 认领（claim）
            "claim_enabled": bool(getattr(self, "_claim_enabled", False)),
            "claim_dry": bool(getattr(self, "_claim_dry", True)),
            "claim_sites": list(getattr(self, "_claim_sites", None) or []),
            "claim_daily_per_site": int(getattr(self, "_claim_daily", CLAIM_DAILY_PER_SITE) or 0),
            "claim_batch": int(getattr(self, "_claim_batch", CLAIM_BATCH) or 1),
            "claim_interval_sec": float(getattr(self, "_claim_interval_sec", CLAIM_INTERVAL_SEC) or 0.0),
            "claim_min_age_days": float(getattr(self, "_claim_min_age_days", 0.0) or 0.0),
            "claim_require_seeders": int(getattr(self, "_claim_require_seeders", 0) or 0),
            "claim_min_size_gb": float(getattr(self, "_claim_min_size_gb", 0.0) or 0.0),
            "claim_exclude_zero_bonus": bool(getattr(self, "_claim_exclude_zero_bonus", True)),
            "rules_auto_refresh": bool(getattr(self, "_rules_cfg", {}).get("auto_refresh", True)),
            "fallback_enabled": bool(self._fallback_cfg.get("enabled", True)),
            "fallback_sources": list(self._fallback_cfg.get("sources") or FALLBACK_SOURCES),
            "fallback_paths": list(self._fallback_cfg.get("paths") or []),
            "fallback_interval_minutes": float(self._fallback_cfg.get("interval", 30.0) or 30.0),
            "fallback_scan_max": int(self._fallback_cfg.get("scan_max", FALLBACK_SCAN_MAX) or FALLBACK_SCAN_MAX),
            "fallback_sp_to_s00": bool(self._fallback_cfg.get("sp_to_s00", False)),
            "fallback_after_import": bool(self._fallback_cfg.get("after_import", True)),
            "fallback_dry_run": bool(self._fallback_cfg.get("dry_run", False)),
            "live_enabled": bool(getattr(self, "_live_cfg", {}).get("enabled", True)),
            "live_interval_minutes": float(getattr(self, "_live_cfg", {}).get("interval") or LIVE_INTERVAL_MINUTES),
            "live_download_alert_mb": float(getattr(self, "_live_cfg", {}).get("download_alert_mb") or LIVE_DOWNLOAD_ALERT_MB),
            "live_ratio_target": float(getattr(self, "_live_cfg", {}).get("ratio_target") or LIVE_RATIO_TARGET),
            "live_auto_stop": bool(getattr(self, "_live_cfg", {}).get("auto_stop", False)),
            "live_kill_unfree": bool(getattr(self, "_live_cfg", {}).get("kill_unfree", True)),
            "live_kill_delete_files": bool(getattr(self, "_live_cfg", {}).get("kill_delete_files", True)),
            "promo_guard": bool(getattr(self, "_live_cfg", {}).get("promo_guard", True)),
            "live_notify": bool(getattr(self, "_live_cfg", {}).get("notify", True)),
            "exam_enabled": bool(self._live_cfg.get("exam_enabled", False)),
            "exam_include_pass": bool(self._live_cfg.get("exam_include_pass", False)),
            "exam_sites": list(self._live_cfg.get("exam_sites") or []),
            # 站点签到 / 模拟登录(借鉴「站点自动签到」插件:多选站点 + GET attendance.php)
            "signin_enabled": bool(getattr(self, "_signin_cfg", {}).get("enabled", False)),
            "signin_sites": list(getattr(self, "_signin_cfg", {}).get("sites") or []),
            "signin_login_sites": list(getattr(self, "_signin_cfg", {}).get("login_sites") or []),
            "signin_retry_keyword": str(getattr(self, "_signin_cfg", {}).get("retry_keyword") or SIGNIN_RETRY_KEYWORD),
            "signin_queue": int(getattr(self, "_signin_cfg", {}).get("queue") or SIGNIN_QUEUE),
            "signin_notify": bool(getattr(self, "_signin_cfg", {}).get("notify", True)),
            "signin_interval_minutes": float(getattr(self, "_signin_cfg", {}).get("interval") or SIGNIN_INTERVAL_MINUTES),
            "signin_window_start": int(getattr(self, "_signin_cfg", {}).get("window_start", 9)),
            "signin_window_end": int(getattr(self, "_signin_cfg", {}).get("window_end", 23)),
            # 云盘归档(token 不写回配置,单独存插件数据,避免明文进主配置)
            "cloud_enabled": bool(self._cloud_cfg.get("enabled", False)),
            "cloud_openlist_url": str(self._cloud_cfg.get("url") or ""),
            "cloud_openlist_token": str(self._cloud_cfg.get("token") or ""),
            "cloud_source_mount": str(self._cloud_cfg.get("source_mount") or "/quark"),
            "cloud_strm_mount": str(self._cloud_cfg.get("strm_mount") or "/movie"),
            "cloud_paths": list(self._cloud_cfg.get("paths") or []),
            "cloud_target_template": str(self._cloud_cfg.get("target_template") or CLOUD_TARGET_TEMPLATE),
            "cloud_interval_minutes": float(self._cloud_cfg.get("interval") or CLOUD_INTERVAL_MINUTES),
            "cloud_scan_max": int(self._cloud_cfg.get("scan_max") or CLOUD_SCAN_MAX),
            "cloud_min_size_gb": float(self._cloud_cfg.get("min_size_gb") or 0),
            "cloud_max_size_gb": float(self._cloud_cfg.get("max_size_gb") or 0),
            "cloud_min_age_days": float(self._cloud_cfg.get("min_age_days") or 0),
            "cloud_exclude_paths": list(self._cloud_cfg.get("exclude_paths") or []),
            "cloud_exclude_tags": list(self._cloud_cfg.get("exclude_tags") or []),
            "cloud_upload_limit_mbps": float(self._cloud_cfg.get("upload_limit_mbps") or 0),
            "cloud_verify": str(self._cloud_cfg.get("verify") or "size"),
            "cloud_dry_run": bool(self._cloud_cfg.get("dry_run", True)),
            "cloud_delete_local": bool(self._cloud_cfg.get("delete_local", False)),
            "cloud_remove_torrent": bool(self._cloud_cfg.get("remove_torrent", False)),
            "cloud_notify": bool(self._cloud_cfg.get("notify", True)),
            "defaults": dict(getattr(self, "_defaults", {}) or {}),
            "tasks": [task.to_dict() for task in self._task_configs.values()],
        }

    def _apply_runtime_settings(self) -> None:
        """把全局设置下推到运行时组件(操作记录裁剪 / 站点请求节流)。"""
        if self._store is not None:
            try:
                self._store.journal.set_keep(getattr(self, "_journal_keep", 0))
            except Exception as err:
                self._log(f"应用操作记录上限失败:{err}")
        try:
            set_request_interval(getattr(self, "_request_interval", 0))
            set_browse_debug(getattr(self, "_debug_log", False))
            set_dl_gate_base(getattr(self, "_request_interval", 0))
        except Exception as err:
            self._log(f"应用站点请求间隔失败:{err}")

    # ---------------------------------------------------------
    # 任务流量:qB 全局上传限速(按在跑任务类型自动切档,只限上传)
    # ---------------------------------------------------------

    def _resolve_task_upload_limit_kbps(self) -> Tuple[float, str]:
        """按「在跑的任务类型」解析应设的全局上传限速(KB/s)。

        优先级:刷流 > 魔力 > 无(清除)。插件全局未启用时一律清除。
        返回 (限速KB/s, 来源说明)。
        """
        if not self.get_state():
            return 0.0, "插件未启用"
        has_brush = False
        has_bonus = False
        for task in self._task_configs.values():
            if not getattr(task, "enabled", False):
                continue
            ttype = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower()
            if ttype == "brush":
                has_brush = True
            else:
                has_bonus = True
        if has_brush:
            return float(getattr(self, "_brush_upload_limit_kbps", 10240.0) or 0), "刷流"
        if has_bonus:
            return float(getattr(self, "_bonus_upload_limit_kbps", 200.0) or 0), "魔力"
        return 0.0, "无启用任务"

    def _apply_task_traffic_limit(self, force: bool = False) -> None:
        """把 qB 全局上传限速写成「按在跑任务类型」的值(刷流>魔力>清除)。

        - 只限上传(up_limit),不动下载;
        - 值未变化时跳过写入(force=True 强制写);
        - 无启用任务 / 插件未启用 → 清除(0=不限)。
        """
        kbps, label = self._resolve_task_upload_limit_kbps()
        bps = self._kbps_to_bps(kbps)
        if not force and bps == getattr(self, "_last_up_limit_bps", None):
            return
        # 选一个在跑任务的下载器(缺省 qbittorrent)
        dl_name = "qbittorrent"
        for task in self._task_configs.values():
            if getattr(task, "enabled", False) and getattr(task, "downloader", ""):
                dl_name = task.downloader
                break
        dl = self._get_downloader(dl_name)
        if not dl:
            return
        try:
            ok, err = dl.set_app_preferences({"up_limit": bps})
        except Exception as exc:
            ok, err = False, str(exc)
        if ok:
            self._last_up_limit_bps = bps
            self._dbg(f"任务流量:qB 全局上传限速 → {kbps:g} KB/s(按{label})")
            self._log(f"任务流量:qB 全局上传限速 → {kbps:g} KB/s(按{label})")
        else:
            self._log(f"任务流量:设置全局上传限速失败:{err}", "warning")

    def _apply_seed_upload_limit(self, force: bool = False) -> None:
        """给**我们管控的**种子套「单种上传限速」（按账本职务态，不再按标签）。

        - 只动上传（``torrents/setUploadLimit``），不动下载；
        - 档位：state=刷流 → 刷流档；其余（魔力/静默/推荐/跨站来源份）→ 挂种档；
        - **不在账本（无职务态）的种一律不动**；
        - 值没变且 10 分钟内扫过 → 跳过（避免频繁写）。
        """
        try:
            brush_kbps = float(getattr(self, "_brush_seed_up_limit_kbps", BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT) or 0)
        except (TypeError, ValueError):
            brush_kbps = BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT
        try:
            seed_kbps = float(getattr(self, "_seed_up_limit_kbps", SEED_UP_LIMIT_KBPS_DEFAULT) or 0)
        except (TypeError, ValueError):
            seed_kbps = SEED_UP_LIMIT_KBPS_DEFAULT
        last = getattr(self, "_seed_up_limit_last", None)
        if not force and last is not None:
            try:
                _lts = float(last[1])
            except Exception:  # noqa: BLE001
                _lts = 0.0
            if (time.time() - _lts) < SEED_UP_LIMIT_APPLY_INTERVAL:
                return
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return
        try:
            snap = self._tag_all_torrents()
        except Exception as exc:  # noqa: BLE001
            self._log(f"单种限速:读取种子列表失败:{exc}", "warning")
            return
        store = self._tag_state()
        by_kbps: Dict[float, set] = {}
        for h, t in (snap or {}).items():
            try:
                rec = store.get(h) or {}
            except Exception:  # noqa: BLE001
                rec = {}
            state = str(rec.get("state") or "").strip()
            if not state:
                continue  # 不在账本（无职务态）→ 不管控
            kbps = brush_kbps if state == STATE_BRUSH else seed_kbps
            by_kbps.setdefault(kbps, set()).add(h)
        # 跨站来源份（账本 state 可能为空，单独挂种档）
        try:
            for h in (self._crossseed_source_hashes() or set()):
                if h in snap:
                    by_kbps.setdefault(seed_kbps, set()).add(h)
        except Exception:  # noqa: BLE001
            pass
        self._seed_up_limit_last = (None, time.time())
        if not by_kbps:
            return
        parts = []
        for kbps, hashes in sorted(by_kbps.items()):
            try:
                n, serr = downloader.set_upload_limit(sorted(hashes), kbps)
            except Exception as exc:  # noqa: BLE001
                n, serr = 0, str(exc)
            label = f"{kbps:g} KB/s" if kbps > 0 else "不限速"
            if serr:
                self._log(f"单种限速:写入部分失败({label}):{serr}", "warning")
            elif n:
                parts.append(f"{label}×{n}")
        if parts:
            msg = f"单种限速:我们管控的种 → {' / '.join(parts)}"
            self._dbg(msg)
            self._log(msg)

    # ============================================================
    # ★ 决策路径「一轮只拉一次 qB 全量快照」—— 观测钩子（P0）
    # ============================================================
    def _decision_round_begin(self, label: str = "") -> None:
        """标记新一轮决策开始（归零快照计数 + 记时）。"""
        begin_decision_round()
        self._decision_round_label = label

    def _decision_round_note_pull(self) -> None:
        """供「没拿到传入 snap、自行回退拉取」的决策函数计数（本轮第 2+ 次会告警）。

        hr.py 等不能 import common 的 mixin 用 ``getattr(self, "_decision_round_note_pull",
        None)`` 钩子调用本方法，缺失时静默降级（离线单测无 core 实例）。
        """
        note_snapshot_pull(1)
        stats = decision_round_stats()
        if int(stats.get("pulls", 0)) > 1:
            self._dbg(
                f"决策轮[{getattr(self, '_decision_round_label', '') or '?'}] "
                f"快照已拉取 {stats['pulls']} 次（应只拉 1 次：上游决策函数未复用 snap）"
            )

    def _decision_round_end(self) -> None:
        """决策轮收尾：打印本轮快照拉取次数 / 耗时。"""
        stats = end_decision_round()
        self._dbg(
            f"决策轮[{getattr(self, '_decision_round_label', '') or '?'}] "
            f"快照拉取 {stats.get('pulls', 0)} 次 / 耗时 {stats.get('elapsed_ms', 0)}ms"
        )

    def _spawn_run_mode_apply(self, task: MagicFlowTaskConfig, mode: str) -> None:
        """异步应用运行状态对应的种子操作(暂停/恢复),并在「运行中」时立即跑一轮 check。"""
        def _worker():
            try:
                self._apply_run_mode(task, mode)
            except Exception as err:
                self._log(f"魔流 [{task.name}] 应用运行状态失败:{err}", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def _split_release(self, task: MagicFlowTaskConfig, hashes: Any, *, reason: str = "") -> int:
        """★ 11.11.0 遣散分诊：欠 H&R → 保种(__hr_host__)；否则 → 静默（退标签 + pause）。

        退回旧行为：``SILENT_HR_SPLIT_ENABLED=False`` → 直接 ``_tag_release``。
        只清本任务的占用，不影响其它任务的保护集。
        """
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        hs = [str(h or "").strip().lower() for h in hs if str(h or "").strip()]
        if not hs:
            return 0
        if not SILENT_HR_SPLIT_ENABLED:
            return int(self._tag_release(task, hs, reason=reason) or 0)
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        hr_hashes: List[str] = []
        silent_hashes: List[str] = []
        for h in hs:
            t = snap.get(h)
            if t is None:
                silent_hashes.append(h)
                continue
            try:
                owed = bool(self._hr_obligation("", t, snap=snap)[0])
            except Exception:  # noqa: BLE001
                owed = False
            if owed:
                hr_hashes.append(h)
            else:
                silent_hashes.append(h)
        n = 0
        if hr_hashes:
            try:
                n += int(self._hr_host_assign(hr_hashes, reason=reason) or 0)
            except Exception as err:  # noqa: BLE001
                self._log(f"魔流 [{getattr(task, 'name', '')}] 遣散分诊:保种失败:{err}", "warning")
        if silent_hashes:
            n += int(self._tag_release(task, silent_hashes, reason=reason) or 0)
        # ★ 释放本任务对这些已退出种的陈旧保护/纳管记录（只清本任务）
        try:
            if self._store is not None:
                self._store.forget_torrents(str(getattr(task, "id", "") or ""), hs)
        except Exception:  # noqa: BLE001
            pass
        return n

    def _apply_run_mode(self, task: MagicFlowTaskConfig, mode: str) -> Dict[str, int]:
        """按运行状态操作托管种子(只动本任务标签内的种子,保文件、可逆)。

        - ``running``(上班+招人):恢复所有被暂停的托管种(尊重手动暂停),随后立刻跑一轮 check;
        - ``seeding``(上班):暂停「未完成」种(防非免费偷下),已完成种继续做种;
        - ``stopped``(遣散):名下种子**退回静默仓库**(释放账本占用) + 暂停(保文件)。

        ★ 口径来源（Master 2026-09-30 00:37）：
          停止=遣散大家、做种=叫大家来上班、运行=上班+招人。

        返回 {paused, resumed, released}。
        """
        mode = self._normalize_run_mode(mode)
        out = {"paused": 0, "resumed": 0, "released": 0}
        downloader = self._get_downloader(task.downloader)
        if not downloader or not downloader.is_available:
            if mode == "running":
                self._run_check(task.id)
            return out
        managed = self._task_managed_torrents(task)
        manual_paused = self._store.get_manual_paused(task.id) if self._store else set()
        pause_hashes: List[str] = []
        resume_hashes: List[str] = []
        for t in managed:
            h = getattr(t, "hash", "") or ""
            if not h:
                continue
            state = str(getattr(t, "state", "") or "").lower()
            paused = state in QB_PAUSED_STATES
            try:
                progress = float(getattr(t, "progress", 0) or 0)
            except (TypeError, ValueError):
                progress = 0.0
            if mode == "stopped":
                if not paused:
                    pause_hashes.append(h)
            elif mode == "seeding":
                if progress >= 0.999:
                    if paused and (h or "").lower() not in manual_paused:
                        resume_hashes.append(h)
                else:
                    if not paused:
                        # ★ 欠 H&R 的种**不暂停**：它本就需要先下完、再做满义务时长，
                        #   暂停只会让它更下不完、更容易被清理淘汰（H&R 违约）。
                        try:
                            _owed = bool(
                                self._hr_obligation(
                                    getattr(task, "site_name", "")
                                    or getattr(task, "site_domain", ""),
                                    t,
                                )[0]
                            )
                        except Exception:  # noqa: BLE001
                            _owed = False
                        if not _owed:
                            pause_hashes.append(h)
            else:  # running
                if paused and (h or "").lower() not in manual_paused:
                    resume_hashes.append(h)
        if pause_hashes:
            n, _e = downloader.pause_torrents(pause_hashes)
            out["paused"] = int(n or 0)
        if resume_hashes:
            n, _e = downloader.resume_torrents(resume_hashes)
            out["resumed"] = int(n or 0)
        # ★ 4.6.0 遣散：停止 → 名下种子**立刻**退回静默仓库（释放账本占用），
        #   不等 hourly 的「标签账本维护」worker（那是兜底）。
        if mode == "stopped":
            try:
                _rls = [h for h in (getattr(t, "hash", "") or "" for t in managed) if h]
                out["released"] = int(
                    self._split_release(task, _rls, reason="任务已停止→遣散（退回静默仓库）") or 0
                )
            except Exception as err:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 遣散退回静默失败:{err}", "warning")
            # ★ 11.11.0：欠 H&R 的种已由 _split_release 交给 __hr_host__（保种 + 强挂），
            #   不再在静默托管里过 H&R 闸门（hr_host worker 兜底）。
        mode_label = {
            "running": "运行中（上班+招人）",
            "seeding": "做种中（上班）",
            "stopped": "已停止（遣散）",
        }.get(mode, mode)
        self._log(
            f"魔流 [{task.name}] 运行状态 → {mode_label}"
            f"(暂停 {out['paused']} / 恢复 {out['resumed']} / 遣散 {out.get('released', 0)})"
        )
        if self._store:
            try:
                self._store.journal.record(
                    task_id=task.id,
                    kind="state",
                    items=[OperationItem(
                        hash="",
                        title=f"运行状态 → {mode_label}",
                        reason=f"暂停 {out['paused']} / 恢复 {out['resumed']} / 遣散 {out.get('released', 0)}",
                    )],
                )
            except Exception as err:
                self._log(f"记录运行状态变更失败:{err}", "warning")
        if mode == "running":
            self._run_check(task.id)
        elif mode == "seeding":
            # ★ 3.25.0: seeding 模式主动纳管同站已有种(IYUU 回来/手动添加/本机已有的同站资源)
            # 不以 _run_check 启动,只调度一次同站纳管 + 按 check_interval 由 Check worker 后续接力。
            try:
                _dl2 = self._get_downloader(task.downloader)
                if _dl2 and _dl2.is_available:
                    _ad = self._adopt_same_site(task, _dl2)
                    if _ad.get("matched", 0) or _ad.get("adopted", 0) or _ad.get("already", 0):
                        self._log(
                            f"魔流 [{task.name}] 切做种中 → 同站纳管"
                            f" 匹配 {_ad.get('matched', 0)} / 新接管 {_ad.get('adopted', 0)} / 已纳管 {_ad.get('already', 0)}",
                            "info",
                        )
            except Exception as _adopt_exc:  # noqa: BLE001
                self._log(
                    f"魔流 [{task.name}] seeding 切状态同站纳管异常:{_adopt_exc}",
                    "warning",
                )
        # ★ 5.0.3：状态切换会**贴/摘职务标签** → 限速档位跟着变。
        #   而 `update_task_state` 里那次限速是在标签写盘**之前**跑的（拿到的是旧档），
        #   任务又停着不会再有 Check → 限速会**停在旧档**（实测：刷流的种被限成 200KB/s）。
        #   所以在异步应用完成后**强制重算一次**。
        try:
            self._apply_seed_upload_limit(force=True)
        except Exception as _lim_exc:  # noqa: BLE001
            self._log(f"魔流 [{task.name}] 切状态后单种限速重算失败:{_lim_exc}", "warning")
        return out

    def _save_config(self) -> None:
        """保存全局设置和全部任务配置"""
        self.update_config(self._current_config())

    def _refresh_scheduler(self) -> None:
        """通知宿主按最新任务列表重建插件服务"""
        try:
            Scheduler().update_plugin_job(self.__class__.__name__)
        except Exception as err:
            logger.error(f"更新魔流调度失败:{str(err)}")

    def _invalidate_summary(self, drop: bool = False) -> None:
        self._summary_cache = None
        self._summary_cache_at = 0.0
        self._stats_cache = {}
        # 默认保留旧快照(_status_heavy),仅标记过期:下次 /status 秒回旧值
        # 并后台刷新(stale-while-revalidate),避免每轮任务结束后首屏退化为轻量壳。
        self._status_heavy_at = 0.0
        if drop:
            # 结构性变更(增/删/改任务、切换状态):丢弃旧快照 → 下次请求先返回
            # 轻量壳(由最新任务配置构建,立即含新增/删除的任务)再后台补统计。
            self._status_heavy = None

    # ---------------------------------------------------------
    # 站点 / 下载器辅助
    # ---------------------------------------------------------

    def _log(self, message: str, level: str = "info") -> None:
        """写插件日志。"""
        text = f"魔流:{message}"
        getattr(logger, level if hasattr(logger, level) else "info")(text)

    def _dbg(self, message: str) -> None:
        """调试日志:仅在全局「调试日志」开启时输出。"""
        if getattr(self, "_debug_log", False):
            self._log(f"[调试] {message}")

    def _set_phase(self, task_id: str, phase: str, detail: str = "") -> None:
        """上报当前运行阶段(detail 为阶段内细粒度进度,供前端显示)。"""
        if not self._store:
            return
        try:
            self._store.record_phase(task_id, phase, self.PHASE_LABELS.get(phase, phase), detail)
        except Exception:
            pass

    def _get_site(self, site_id: int):
        """通过站点 ID 获取站点对象。"""
        try:
            from app.db.oper.site import SiteOper
            return SiteOper().get(site_id)
        except Exception as err:
            self._log(f"获取站点失败: {err}", "error")
            return None

    def _list_sites(self) -> List[Dict[str, Any]]:
        """列出可选站点。"""
        try:
            from app.sdk.network import SitesHelper
            out: List[Dict[str, Any]] = []
            for item in SitesHelper().get_indexers() or []:
                if not isinstance(item, dict):
                    continue
                out.append({
                    "id": item.get("id"),
                    "name": item.get("name") or item.get("domain") or "",
                    "domain": item.get("domain") or "",
                })
            return out
        except Exception as err:
            self._log(f"列出站点失败: {err}", "error")
            return []

    def _list_downloaders(self) -> List[Dict[str, Any]]:
        """列出可选下载器。"""
        out: List[Dict[str, Any]] = []
        try:
            from app.sdk.services import DownloaderHelper
            configs = DownloaderHelper().get_configs() or {}
            for name in configs.keys():
                out.append({"title": str(name), "value": str(name)})
        except Exception as err:
            self._log(f"列出下载器失败: {err}", "error")
        if not out:
            out = [
                {"title": "qBittorrent", "value": "qbittorrent"},
                {"title": "Transmission", "value": "transmission"},
            ]
        return out


    def _try_begin_run(self, task_id: str) -> bool:
        """尝试开始一轮运行。

        不用不可超时的锁(一旦某轮卡死会永久堵死后续调度),
        改用「运行时间戳 + 超时」。超过 _task_run_timeout 视为僵尸轮,
        自动放行新一轮并告警。
        """
        now = time.time()
        started = self._task_runs.get(task_id, 0.0)
        if started and (now - started) < self._task_run_timeout:
            return False
        if started:
            self._log(
                f"魔流:检测到任务 {task_id} 上一轮已运行 "
                f"{int(now - started)} 秒仍未结束,判定为卡死,放行新一轮"
            )
        self._task_runs[task_id] = now
        return True

    def _end_run(self, task_id: str) -> None:
        """结束一轮运行,释放运行槽。"""
        self._task_runs.pop(task_id, None)

    # ---------------------------------------------------------
    # 全局并发闸门(插件级):限制同时在飞的 worker 数
    # ---------------------------------------------------------

    def _acquire_worker_slot(self, label: str = "") -> bool:
        """非阻塞抢一个全局 worker 槽;抢不到就跳过本轮(不排队,避免堆积)。"""
        sem = getattr(self, "_worker_sem", None)
        if sem is None:
            sem = self._worker_sem = threading.Semaphore(int(GLOBAL_WORKER_LIMIT))
        if sem.acquire(blocking=False):
            return True
        self._log(
            f"魔流 全局并发闸门已满(上限 {GLOBAL_WORKER_LIMIT}),[{label or 'worker'}] 本轮跳过"
        )
        return False

    def _release_worker_slot(self) -> None:
        """归还全局 worker 槽。"""
        sem = getattr(self, "_worker_sem", None)
        if sem is not None:
            try:
                sem.release()
            except Exception:  # noqa: BLE001
                pass

    def _settle(self, report: WorkReport) -> None:
        """统一分账入口:把 worker 的 WorkReport 交给 store.settle(无 store 则忽略)。"""
        if not self._store:
            return
        try:
            self._store.settle(report)
        except Exception as e:  # noqa: BLE001
            logger.error(f"魔流 分账失败:{e}")

    @staticmethod
    def _jitter_seconds(minutes: Any) -> int:
        """interval 抖动(秒):取间隔的 ~15%,夹在 [3, 90],错开几十个任务的同刻开火。"""
        try:
            sec = float(minutes) * 60.0 * 0.15
        except (TypeError, ValueError):
            sec = 10.0
        return int(max(3.0, min(90.0, sec)))

    def _get_task_config(self, task_id: str) -> Optional[MagicFlowTaskConfig]:
        """获取任务配置。"""
        return self._task_configs.get(task_id)

    def _get_downloader(self, downloader_name: str = "qbittorrent") -> Optional[DownloaderAdapter]:
        """获取下载器适配器。"""
        try:
            dl = DownloaderAdapter(downloader_name=downloader_name)
            dl.tags_enabled = self._show_qb_tags()
            # ★ 删除唯一入口（Master 2026-10-05「删除令出一门」）：挂上硬保护闸门 + 统一台账。
            #   同时打到类属性上，覆盖不走本方法而直接 `DownloaderAdapter(...)` 的调用点。
            try:
                dl.gate = self._delete_gate
                dl.deletion_log = self._delete_log_cb
                type(dl)._global_gate = self._delete_gate
                type(dl)._global_dlog = self._delete_log_cb
            except Exception:  # noqa: BLE001
                pass
            return dl
        except Exception as e:
            self._log(f"获取下载器失败: {e}", "error")
            return None

    def _show_qb_tags(self) -> bool:
        """是否往 qB 写标签（show_qb_tags 开关，默认开=纯投影）。"""
        try:
            return bool(self._tags_cfg.get("show_qb_tags", True))
        except Exception:  # noqa: BLE001
            return True

    def _cached_options(self) -> Dict[str, Any]:
        """站点/下载器下拉选项(带 TTL 缓存)。几乎不变,无需随每次 /status 重拉。"""
        now = time.time()
        cache = getattr(self, "_options_cache", None)
        if cache and (now - float(cache.get("ts", 0))) < OPTIONS_TTL:
            return cache.get("data") or {"sites": [], "downloaders": []}
        data = {
            "sites": self._list_sites(),
            "downloaders": self._list_downloaders(),
        }
        self._options_cache = {"ts": now, "data": data}
        return data


    # ---------------------------------------------------------
    # API:下载器全局参数(qBittorrent 应用级偏好)
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_run_mode(mode: Any, enabled: Any = None) -> str:
        """规整运行状态:running / seeding / stopped。

        ★ 契约①：实现只有一处 —— `common.normalize_run_mode`；这里只是历史调用点的转发壳。
        """
        return common.normalize_run_mode(mode, enabled)

    @staticmethod
    def _kbps_to_bps(kbps: Any) -> int:
        """KB/s → 字节/秒(qbittorrentapi 用字节/秒)。负数/非法值规整为 0。"""
        try:
            v = float(kbps or 0)
        except (TypeError, ValueError):
            v = 0.0
        return max(0, int(round(v * 1024)))

    @staticmethod
    def _bps_to_kbps(bps: Any) -> float:
        """字节/秒 → KB/s(保留 1 位小数)。"""
        try:
            v = float(bps or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v <= 0:
            return 0.0
        return round(v / 1024.0, 1)

    def _settle_task_idle_safe(self, task_id: str) -> None:
        """任务被**停止**（`run_mode=stopped`）→ 名下种子退回静默（保文件、可逆）。

        ★ 14.0.0：守卫改用真源 `run_mode`——「做种中」(seeding) = **在岗**，不退静默。
        （旧代码看派生字段 `enabled`，会把 seeding 任务误判为「已停止」而遣散其种。）
        """
        try:
            task = self._get_task_config(task_id)
            if not task or run_mode_of(task) != RUN_MODE_STOPPED:
                return
            _keeper = self._same_site_state_live(task)
            if _keeper:
                self._log(f"魔流 [{task.name}] 已停止：同站同状态任务「{_keeper}」在跑 → 种子归它，不退静默")
                return
            res = self._tag_settle_idle(task)
            if res.get("settled"):
                self._log(f"魔流 [{task.name}] 任务已停止 → 名下 {res.get('settled')} 个种子退回静默")
            # ★ 停止时顺手清掉「没下完」的半成品（不计 H&R，Master 2026-09-28）：
            #   不删的话它们既不产上传、也永远结不清 H&R，还白占盘。
            try:
                pinfo = self._silent_purge_incomplete(apply=True, limit=200)
                if pinfo.get("deleted"):
                    self._log(f"魔流 [{task.name}] 停止清理:未下完直接删 {pinfo.get('deleted')} 个（不计 H&R）")
            except Exception as err:  # noqa: BLE001
                self._log(f"停止清理半成品失败:{err}", "warning")
        except Exception as err:  # noqa: BLE001
            self._log(f"停止任务退回静默失败:{err}", "warning")

    def _settle_disabled_tasks(self, apply: bool = False) -> Dict[str, Any]:
        """★ 「已停止」的任务 = 遣散：名下种子一律退回「静默仓库」。

        口径（Master 2026-09-30 00:37）：运行=上班+招人 / 做种=上班 / 停止=遣散走人。
        静默＝不刷流、不做魔力优化，只是挂着保种/攒魔力，限速走静默档 200KB/s。
        同站同状态若有**在岗（运行中/做种中）**的任务，则不动（那批种归它）。
        """
        report: Dict[str, Any] = {"tasks": [], "settled": 0, "skipped_live": 0, "pending": 0}
        for t in list(self._task_configs.values()):
            # ★ 4.6.0 口径：只有 run_mode=stopped 才「遣散」；「做种中」(enabled 派生为 False) 不退。
            if task_is_participating(t):
                continue
            tid = str(getattr(t, "id", "") or "")
            try:
                hs = list(self._task_managed_hashes(t))
            except Exception:  # noqa: BLE001
                hs = []
            # ★ 11.11.0 释放陈旧保护：stopped 任务名下种早已退回静默，职务态对不上 → managed 空。
            #   直接取 store 里的陈旧占用（protected ∪ adopted），并入遣散 + forget（释放 611 陈旧保护）。
            stale: List[str] = []
            try:
                if self._store is not None:
                    stale = sorted({str(x).strip().lower() for x in (
                        set(self._store.get_protected_torrents(tid) or set())
                        | set(self._store.get_adopted(tid) or set())
                    ) if str(x).strip()})
            except Exception:  # noqa: BLE001
                stale = []
            hs = sorted(set(hs) | set(stale))
            if not hs:
                continue
            _keeper = self._same_site_state_live(t)
            if _keeper and not stale:
                report["skipped_live"] += 1
                report["tasks"].append({"task": str(getattr(t, "name", "") or ""),
                                        "hashes": len(hs), "keeper": _keeper})
                continue
            if not apply:
                report["pending"] += len(hs)
                report["tasks"].append({"task": str(getattr(t, "name", "") or ""), "hashes": len(hs)})
                continue
            n = self._split_release(t, hs, reason="任务已停止→遣散（退回静默仓库）")
            report["settled"] += n
            report["tasks"].append({"task": str(getattr(t, "name", "") or ""), "settled": n})
        # ★ 11.11.0：欠 H&R 的种已由 _split_release 交给 __hr_host__，不再在遣散后过 H&R 闸门
        #   （hr_host worker 兜底）。
        # ★ 5.0.3：遣散改变了职务标签 → 单种限速要按新档位重算（否则停在刷流 5120）
        if apply and report.get("settled"):
            try:
                self._apply_seed_upload_limit(force=True)
            except Exception as err:  # noqa: BLE001
                self._log(f"遣散后单种限速重算失败:{err}", "warning")
        return report
