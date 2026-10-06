# -*- coding: utf-8 -*-
"""魔流 · settings —— 设置读写（全局配置唯一入口）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

from datetime import datetime
from typing import Any, Dict, List


from app.schemas import Response
from app.sdk.logging import logger

from ..iyuu_cloud import IyuuCloud
from ..models import (
    MagicFlowDefaultsPayload,
    MagicFlowDownloaderPathsPayload,
    MagicFlowDownloaderPrefsPayload,
    MagicFlowSettingsPayload,
    DOWNLOADER_PREF_RECOMMENDED,
)
from ..fallback import DEFAULT_SOURCES as FALLBACK_SOURCES
from ..cloud_archive import DEFAULT_TARGET_TEMPLATE as CLOUD_TARGET_TEMPLATE
from ..signin import SigninEngine
from ..tags import (
    DEFAULT_SORT_RULES,
)


from ..common import (
    BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT,
    CLAIM_CFG_KEY,
    CLOUD_INTERVAL_MINUTES,
    CLOUD_SCAN_MAX,
    CROSSSEED_SEED_HOURS_DEFAULT,
    CROSSSEED_SITE_HOURS_DEFAULT,
    FALLBACK_SCAN_MAX,
    LIVE_DOWNLOAD_ALERT_MB,
    LIVE_INTERVAL_MINUTES,
    LIVE_RATIO_TARGET,
    RESEED_CFG_KEY,
    SEED_UP_LIMIT_KBPS_DEFAULT,
    SIGNIN_INTERVAL_MINUTES,
    SIGNIN_QUEUE,
    SIGNIN_RETRY_KEYWORD,
    _cs_parse_site_hours,
)


class SettingsMixin:
    """settings 功能集（原 MagicFlow 方法原样搬入）。"""

    def update_settings(self, payload: MagicFlowSettingsPayload) -> Response:
        """更新插件全局设置。"""
        self._enabled = bool(payload.enabled)
        self._show_sidebar_nav = bool(payload.show_sidebar_nav)
        self._debug_log = bool(payload.debug_log)
        self._compact_mode = bool(payload.compact_mode)
        try:
            self._journal_keep = max(0, int(payload.journal_keep or 0))
        except (TypeError, ValueError):
            self._journal_keep = 200
        try:
            self._request_interval = max(0.0, float(payload.request_interval or 0))
        except (TypeError, ValueError):
            self._request_interval = 0.0
        try:
            self._bonus_upload_limit_kbps = max(0.0, float(payload.bonus_upload_limit_kbps or 0))
        except (TypeError, ValueError):
            self._bonus_upload_limit_kbps = 200.0
        try:
            self._brush_upload_limit_kbps = max(0.0, float(payload.brush_upload_limit_kbps or 0))
        except (TypeError, ValueError):
            self._brush_upload_limit_kbps = 10240.0
        try:
            self._seed_up_limit_kbps = max(0.0, float(payload.seed_up_limit_kbps or 0))
        except (TypeError, ValueError):
            self._seed_up_limit_kbps = SEED_UP_LIMIT_KBPS_DEFAULT
        try:
            self._brush_seed_up_limit_kbps = max(0.0, float(payload.brush_seed_up_limit_kbps or 0))
        except (TypeError, ValueError):
            self._brush_seed_up_limit_kbps = BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT
        # IYUU 云端辅种配置
        # ★ Token 空 = 保持原值（+ 落 save_data 备份、init 时回落）：
        #   旧前端 chunk / 别的标签页保存设置时 payload 可能不带 iyuu_token，
        #   之前无条件赋值会把已填好的 Token 抹掉（「填完后来没了」的真凶）。
        #   真要清空 → 前端传 iyuu_clear=true。
        _new_iyuu = str(getattr(payload, "iyuu_token", "") or "").strip()
        if bool(getattr(payload, "iyuu_clear", False)):
            self._iyuu_token = ""
            self.save_data(key="iyuu_token", value="")
        elif _new_iyuu:
            self._iyuu_token = _new_iyuu
            self.save_data(key="iyuu_token", value=_new_iyuu)
        raw_sites = getattr(payload, "iyuu_sites", None)
        if isinstance(raw_sites, dict):
            self._iyuu_sites = {
                str(k).strip().lower(): {str(vk): str(vv) for vk, vv in dict(v).items()}
                for k, v in raw_sites.items()
                if isinstance(v, dict) and str(k).strip()
            }
        self.save_data(key="iyuu_sites", value=dict(self._iyuu_sites))
        if self._iyuu_client is None:
            self._iyuu_client = self._build_iyuu_client(self._iyuu_token)
        else:
            self._iyuu_client.set_token(self._iyuu_token)
        # 刷流种甄别与推荐(价值生命周期)
        def _rf(v: Any, d: float) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return d

        self._recommend_cfg = {
            "enabled": bool(getattr(payload, "recommend_enabled", True)),
            "min_rating": _rf(getattr(payload, "recommend_min_rating", 7.5), 7.5),
            "require_chart": bool(getattr(payload, "recommend_require_chart", True)),
            "expire_days": _rf(getattr(payload, "recommend_expire_days", 7.0), 7.0),
            "tag": str(getattr(payload, "recommend_tag", "") or "魔流-推荐").strip() or "魔流-推荐",
            "auto_import": bool(getattr(payload, "recommend_auto_import", True)),
            "notify": bool(getattr(payload, "recommend_notify", True)),
            "temp_ttl_days": _rf(getattr(payload, "recommend_temp_ttl_days", 7.0), 7.0),
            "disk_min_free_gb": _rf(getattr(payload, "recommend_disk_min_free_gb", 50.0), 50.0),
        }
        # 跨站辅种：兄弟站流量兜底
        self._cs_cfg = {
            "guard": bool(getattr(payload, "crossseed_guard", True)),
            "guard_pct": _rf(getattr(payload, "crossseed_guard_pct", 5.0), 5.0),
            "guard_min_mb": _rf(getattr(payload, "crossseed_guard_min_mb", 50.0), 50.0),
            "guard_interval_min": _rf(getattr(payload, "crossseed_guard_interval_min", 15.0), 15.0),
            "keep_seed": bool(getattr(payload, "crossseed_guard_keep_seed", True)),
            "seed_hours_default": _rf(getattr(payload, "crossseed_seed_hours_default", CROSSSEED_SEED_HOURS_DEFAULT), CROSSSEED_SEED_HOURS_DEFAULT),
            "site_hours": _cs_parse_site_hours(
                getattr(payload, "crossseed_site_hours", None) or CROSSSEED_SITE_HOURS_DEFAULT
            ),
            "reclaim": bool(getattr(payload, "crossseed_reclaim", False)),
        }
        self._rules_cfg = {
            "auto_refresh": bool(getattr(payload, "rules_auto_refresh", True)),
        }
        # ★ 全站辅种（本机驱动）：本机已有资源 → 去各站落户（零下载）
        try:
            self._reseed_enabled = bool(getattr(payload, "reseed_enabled", False))
            _rs_sites = getattr(payload, "reseed_sites", None)
            self._reseed_sites = [str(x).strip() for x in (_rs_sites or []) if str(x).strip()]
            self._reseed_daily = int(_rf(getattr(payload, "reseed_daily_per_site", 30.0), 30.0))
            self._reseed_batch = int(_rf(getattr(payload, "reseed_batch", 10.0), 10.0))
            self._reseed_min_size_gb = _rf(getattr(payload, "reseed_min_size_gb", 1.0), 1.0)
            self._reseed_dry = bool(getattr(payload, "reseed_dry", True))
            # ★ 设置面是权威：清掉历史遗留的 plugin-data 覆盖（旧 reseed_cfg 会盖住这里的值）
            self.save_data(key=RESEED_CFG_KEY, value={})
        except Exception:  # noqa: BLE001
            pass
        # ★ 11.13.0 H&R 安全垫 + 临近到期预警（设置面为权威）
        try:
            self._hr_seed_margin_hours = _rf(getattr(payload, "hr_seed_margin_hours", 2.0), 2.0)
            self._hr_deadline_warn_hours = _rf(getattr(payload, "hr_deadline_warn_hours", 48.0), 48.0)
        except Exception:  # noqa: BLE001
            pass
        # ★ 认领（claim，7.14.0）：设置面为权威，同样清掉 plugin-data 覆盖
        try:
            self._claim_enabled = bool(getattr(payload, "claim_enabled", False))
            self._claim_dry = bool(getattr(payload, "claim_dry", True))
            _cl_sites = getattr(payload, "claim_sites", None)
            self._claim_sites = [str(x).strip().lower() for x in (_cl_sites or []) if str(x).strip()]
            self._claim_daily = int(_rf(getattr(payload, "claim_daily_per_site", 20.0), 20.0))
            self._claim_batch = int(_rf(getattr(payload, "claim_batch", 5.0), 5.0))
            self._claim_interval_sec = _rf(getattr(payload, "claim_interval_sec", 8.0), 8.0)
            self._claim_min_age_days = _rf(getattr(payload, "claim_min_age_days", 0.0), 0.0)
            self._claim_require_seeders = int(_rf(getattr(payload, "claim_require_seeders", 0.0), 0.0))
            self._claim_min_size_gb = _rf(getattr(payload, "claim_min_size_gb", 0.0), 0.0)
            self._claim_exclude_zero_bonus = bool(getattr(payload, "claim_exclude_zero_bonus", True))
            self.save_data(key=CLAIM_CFG_KEY, value={})
        except Exception:  # noqa: BLE001
            pass
        # 标签模型（3.13.0）
        _sr = getattr(payload, "sort_rules", None)
        self._tags_cfg = {
            "enabled": bool(getattr(payload, "tag_model_enabled", True)),
            "show_qb_tags": bool(getattr(payload, "show_qb_tags", True)),
            "new_timeout": max(0.0, _rf(getattr(payload, "tag_silent_new_timeout_hours", 24.0), 24.0)) * 3600.0,
            "snapshot_interval": max(0.0, _rf(getattr(payload, "tag_snapshot_interval_hours", 6.0), 6.0)) * 3600.0,
            "rules": [dict(r) for r in _sr if isinstance(r, dict)] if isinstance(_sr, list) and _sr else [dict(r) for r in DEFAULT_SORT_RULES],
        }
        self._sync_free_rules()
        # 元数据兜底(多源识别 + 补 NFO)
        _fsrc = getattr(payload, "fallback_sources", None)
        _fpaths = getattr(payload, "fallback_paths", None)
        self._fallback_cfg = {
            "enabled": bool(getattr(payload, "fallback_enabled", True)),
            "sources": [str(s).strip().lower() for s in (_fsrc or FALLBACK_SOURCES) if str(s or "").strip()]
            or list(FALLBACK_SOURCES),
            "paths": [str(p).strip() for p in (_fpaths or []) if str(p or "").strip()],
            "interval": max(5.0, _rf(getattr(payload, "fallback_interval_minutes", 30.0), 30.0)),
            "scan_max": max(1, int(_rf(getattr(payload, "fallback_scan_max", FALLBACK_SCAN_MAX), FALLBACK_SCAN_MAX))),
            "sp_to_s00": bool(getattr(payload, "fallback_sp_to_s00", False)),
            "after_import": bool(getattr(payload, "fallback_after_import", True)),
            "dry_run": bool(getattr(payload, "fallback_dry_run", False)),
        }
        if getattr(self, "_fallback_engine", None) is not None:
            self._fallback_engine.set_cfg(dict(self._fallback_cfg))
        # 站点实时数据 + 流量监控
        self._live_cfg = {
            "enabled": bool(getattr(payload, "live_enabled", True)),
            "interval": _rf(getattr(payload, "live_interval_minutes", LIVE_INTERVAL_MINUTES), float(LIVE_INTERVAL_MINUTES)),
            "download_alert_mb": _rf(getattr(payload, "live_download_alert_mb", LIVE_DOWNLOAD_ALERT_MB), LIVE_DOWNLOAD_ALERT_MB),
            "ratio_target": _rf(getattr(payload, "live_ratio_target", LIVE_RATIO_TARGET), LIVE_RATIO_TARGET),
            "auto_stop": bool(getattr(payload, "live_auto_stop", False)),
            "kill_unfree": bool(getattr(payload, "live_kill_unfree", True)),
            "kill_delete_files": bool(getattr(payload, "live_kill_delete_files", True)),
            "promo_guard": bool(getattr(payload, "promo_guard", True)),
            "notify": bool(getattr(payload, "live_notify", True)),
            "exam_enabled": bool(getattr(payload, "exam_enabled", False)),
            "exam_include_pass": bool(getattr(payload, "exam_include_pass", False)),
            "exam_sites": [str(x) for x in (getattr(payload, "exam_sites", None) or []) if str(x or "").strip()],
        }
        if getattr(self, "_live", None) is not None:
            self._live.ttl = max(60.0, float(self._live_cfg.get("interval") or LIVE_INTERVAL_MINUTES) * 60.0)
            self._live.exam_enabled = bool(self._live_cfg.get("exam_enabled", False))
        # 站点签到 / 模拟登录(借鉴「站点自动签到」插件:多选站点 + GET attendance.php)
        self._signin_cfg = {
            "enabled": bool(getattr(payload, "signin_enabled", False)),
            "sites": [str(x) for x in (getattr(payload, "signin_sites", None) or []) if str(x or "").strip()],
            "login_sites": [str(x) for x in (getattr(payload, "signin_login_sites", None) or []) if str(x or "").strip()],
            "retry_keyword": str(getattr(payload, "signin_retry_keyword", "") or SIGNIN_RETRY_KEYWORD),
            "queue": max(1, int(_rf(getattr(payload, "signin_queue", SIGNIN_QUEUE), SIGNIN_QUEUE))),
            "notify": bool(getattr(payload, "signin_notify", True)),
            "interval": max(10.0, _rf(getattr(payload, "signin_interval_minutes", SIGNIN_INTERVAL_MINUTES), float(SIGNIN_INTERVAL_MINUTES))),
            "window_start": int(_rf(getattr(payload, "signin_window_start", 9), 9)),
            "window_end": int(_rf(getattr(payload, "signin_window_end", 23), 23)),
        }
        if getattr(self, "_signin", None) is None:
            self._signin = SigninEngine(self)
        # 云盘归档(token 空 = 保持原值;避免前端未带该字段时把 token 抹掉)
        _new_token = str(getattr(payload, "cloud_openlist_token", "") or "").strip()
        if _new_token:
            self.save_data(key="cloud_token", value=_new_token)
        _c_paths = getattr(payload, "cloud_paths", None)
        _c_excl = getattr(payload, "cloud_exclude_paths", None)
        _c_tags = getattr(payload, "cloud_exclude_tags", None)
        self._cloud_cfg = {
            "enabled": bool(getattr(payload, "cloud_enabled", False)),
            "url": str(getattr(payload, "cloud_openlist_url", "") or "http://192.168.0.61:12022").strip(),
            "token": _new_token or str(self._cloud_cfg.get("token") or ""),
            "source_mount": str(getattr(payload, "cloud_source_mount", "") or "/quark").strip() or "/quark",
            "strm_mount": str(getattr(payload, "cloud_strm_mount", "") or "/movie").strip() or "/movie",
            "library_root": "/movie",
            "paths": [str(p).strip() for p in (_c_paths or []) if str(p or "").strip()]
            if isinstance(_c_paths, (list, tuple)) else list(self._cloud_cfg.get("paths") or []),
            "target_template": str(getattr(payload, "cloud_target_template", "") or CLOUD_TARGET_TEMPLATE).strip(),
            "interval": max(5.0, _rf(getattr(payload, "cloud_interval_minutes", CLOUD_INTERVAL_MINUTES), float(CLOUD_INTERVAL_MINUTES))),
            "scan_max": max(1, int(_rf(getattr(payload, "cloud_scan_max", CLOUD_SCAN_MAX), float(CLOUD_SCAN_MAX)))),
            "min_size_gb": max(0.0, _rf(getattr(payload, "cloud_min_size_gb", 2.0), 2.0)),
            "max_size_gb": max(0.0, _rf(getattr(payload, "cloud_max_size_gb", 200.0), 200.0)),
            "min_age_days": max(0.0, _rf(getattr(payload, "cloud_min_age_days", 30.0), 30.0)),
            "exclude_paths": [str(p).strip() for p in (_c_excl or []) if str(p or "").strip()]
            if isinstance(_c_excl, (list, tuple)) else list(self._cloud_cfg.get("exclude_paths") or []),
            "exclude_tags": [str(t).strip() for t in (_c_tags or []) if str(t or "").strip()]
            if isinstance(_c_tags, (list, tuple)) else list(self._cloud_cfg.get("exclude_tags") or []),
            "upload_limit_mbps": max(0.0, _rf(getattr(payload, "cloud_upload_limit_mbps", 0.0), 0.0)),
            "verify": str(getattr(payload, "cloud_verify", "size") or "size").strip() or "size",
            "dry_run": bool(getattr(payload, "cloud_dry_run", True)),
            "delete_local": bool(getattr(payload, "cloud_delete_local", False)),
            "remove_torrent": bool(getattr(payload, "cloud_remove_torrent", False)),
            "notify": bool(getattr(payload, "cloud_notify", True)),
        }
        if getattr(self, "_cloud_engine", None) is not None:
            self._cloud_engine.set_cfg(dict(self._cloud_cfg))
        # 顶栏功能磁贴显隐（纯界面层）：存「隐藏」白名单，空 = 全部显示
        self._hidden_tiles = [
            str(x).strip() for x in (getattr(payload, "hidden_tiles", None) or []) if str(x or "").strip()
        ]
        self._save_config()
        self._apply_runtime_settings()
        self._refresh_scheduler()
        self._apply_task_traffic_limit(force=True)
        self._apply_seed_upload_limit(True)
        self._dbg(
            f"全局设置已更新:enabled={self._enabled} sidebar={self._show_sidebar_nav} "
            f"debug={self._debug_log} compact={self._compact_mode} "
            f"journal_keep={self._journal_keep} req_interval={self._request_interval}"
        )
        return Response(success=True, message="设置已保存", data=self._current_config())

    def get_downloader_prefs(self) -> Response:
        """读取下载器(qBittorrent)全局参数 + 推荐值。"""
        downloader = self._get_downloader()
        if downloader is None:
            return Response(success=False, message="下载器不可用")
        prefs, error = downloader.get_app_preferences()
        if error:
            return Response(success=False, message=error)
        data = {
            "available": True,
            "downloader": getattr(downloader, "downloader_name", "qbittorrent"),
            "download_limit_kbps": self._bps_to_kbps(prefs.get("dl_limit")),
            "upload_limit_kbps": self._bps_to_kbps(prefs.get("up_limit")),
            "max_connec": prefs.get("max_connec"),
            "max_connec_per_torrent": prefs.get("max_connec_per_torrent"),
            "max_uploads": prefs.get("max_uploads"),
            "max_uploads_per_torrent": prefs.get("max_uploads_per_torrent"),
            "max_active_downloads": prefs.get("max_active_downloads"),
            "max_active_torrents": prefs.get("max_active_torrents"),
            "queueing_enabled": bool(prefs.get("queueing_enabled")),
            "save_path": prefs.get("save_path") or "",
            "temp_path": prefs.get("temp_path") or "",
            "temp_path_enabled": bool(prefs.get("temp_path_enabled")),
            "raw": prefs,
            "recommended": dict(DOWNLOADER_PREF_RECOMMENDED),
        }
        return Response(success=True, data=data)

    def update_downloader_prefs(self, payload: MagicFlowDownloaderPrefsPayload) -> Response:
        """写入下载器(qBittorrent)全局参数。"""
        downloader = self._get_downloader()
        if downloader is None:
            return Response(success=False, message="下载器不可用")
        target = {
            "dl_limit": self._kbps_to_bps(payload.download_limit_kbps),
            "up_limit": self._kbps_to_bps(payload.upload_limit_kbps),
            "max_connec": int(payload.max_connec),
            "max_connec_per_torrent": int(payload.max_connec_per_torrent),
            "max_uploads": int(payload.max_uploads),
            "max_uploads_per_torrent": int(payload.max_uploads_per_torrent),
            "max_active_downloads": int(payload.max_active_downloads),
            "max_active_torrents": int(payload.max_active_torrents),
            "queueing_enabled": bool(payload.queueing_enabled),
        }
        ok, error = downloader.set_app_preferences(target)
        if not ok:
            return Response(success=False, message=error or "写入失败")
        self._log(
            f"下载器全局参数已更新:下载限速={payload.download_limit_kbps}KB/s "
            f"上传限速={payload.upload_limit_kbps}KB/s 连接={payload.max_connec}/"
            f"{payload.max_connec_per_torrent} 上传连接={payload.max_uploads}/"
            f"{payload.max_uploads_per_torrent} 活动下载/种子={payload.max_active_downloads}/"
            f"{payload.max_active_torrents} 队列={payload.queueing_enabled}"
        )
        return Response(success=True, message="下载器参数已保存", data=self.get_downloader_prefs().data)

    def update_downloader_paths(self, payload: MagicFlowDownloaderPathsPayload) -> Response:
        """写入下载器(qBittorrent)全局路径。"""
        downloader = self._get_downloader()
        if downloader is None:
            return Response(success=False, message="下载器不可用")
        target = {
            "save_path": str(payload.save_path or "").strip(),
            "temp_path": str(payload.temp_path or "").strip(),
            "temp_path_enabled": bool(payload.temp_path_enabled),
        }
        ok, error = downloader.set_app_preferences(target)
        if not ok:
            return Response(success=False, message=error or "写入失败")
        self._log(
            f"下载器目录已更新:保存路径={target['save_path'] or '(空)'} "
            f"临时路径={target['temp_path'] or '(空)'} 启用临时={target['temp_path_enabled']}"
        )
        return Response(success=True, message="下载目录已保存", data=self.get_downloader_prefs().data)

    # ---------------------------------------------------------
    # API:默认任务模板 + 维护
    # ---------------------------------------------------------

    def get_defaults(self) -> Response:
        """读取「默认任务模板」。"""
        data = MagicFlowDefaultsPayload(**(getattr(self, "_defaults", {}) or {})).model_dump()
        return Response(success=True, data=data)

    def update_defaults(self, payload: MagicFlowDefaultsPayload) -> Response:
        """保存「默认任务模板」(仅用于新建任务时预填,不影响已存在任务)。"""
        self._defaults = payload.model_dump()
        self.save_data(key="defaults", value=dict(self._defaults))
        self._save_config()
        return Response(success=True, message="默认任务模板已保存", data=dict(self._defaults))

    # ---------------------------------------------------------
    # API:IYUU 云端辅种(可选)
    # ---------------------------------------------------------

    def _iyuu_enabled(self) -> bool:
        """IYUU 云端辅种是否启用(填了 Token 才算)。"""
        return bool(self._iyuu_client is not None and self._iyuu_client.enabled)

    def _build_iyuu_client(self, token: str) -> IyuuCloud:
        """构造 IYUU 云端客户端,并挂上「站点表 / sid_sha1」磁盘缓存(避免热重载后重复撞限流)。"""
        return IyuuCloud(
            token,
            logger=self._log,
            cache_loader=lambda: self.get_data("iyuu_cache"),
            cache_saver=lambda cache: self.save_data(key="iyuu_cache", value=cache),
        )

    def get_iyuu_sites(self) -> Response:
        """列出 MoviePilot 已配置站点(供「IYUU 密钥表」)+ 当前 IYUU 设置。"""
        client = self._iyuu_client
        rows: List[Dict[str, Any]] = []
        try:
            from app.db.oper.site import SiteOper
            for site in SiteOper().list() or []:
                domain = str(getattr(site, "domain", "") or "")
                rows.append({
                    "id": getattr(site, "id", None),
                    "name": getattr(site, "name", "") or domain,
                    "domain": domain,
                    "url": getattr(site, "url", "") or "",
                    "is_active": bool(getattr(site, "is_active", True)),
                    "has_apikey": bool(str(getattr(site, "apikey", "") or "").strip()),
                    "has_cookie": bool(str(getattr(site, "cookie", "") or "").strip()),
                    "iyuu_sid": client.sid_by_domain(domain) if (client and client.enabled) else None,
                    "fill": dict(self._iyuu_sites.get(domain.lower(), {})),
                })
        except Exception as err:  # noqa: BLE001
            self._log(f"列出已配置站点失败:{err}", "warning")
        return Response(success=True, data={
            "token_set": bool(self._iyuu_token),
            "token": self._iyuu_token,
            "enabled": self._iyuu_enabled(),
            "sites": sorted(rows, key=lambda r: str(r.get("name") or "")),
        })

    def test_iyuu(self) -> Response:
        """测试已保存的 IYUU Token(拉一次账号信息)。"""
        if not self._iyuu_token:
            return Response(success=False, message="未填写 IYUU Token")
        probe = IyuuCloud(self._iyuu_token, logger=self._log)
        profile = probe.profile()
        if not profile:
            return Response(success=False, message="Token 无效或云端不可达")
        return Response(success=True, message="Token 有效", data={
            "id": profile.get("id"),
            "username": profile.get("username"),
            "sid": profile.get("sid"),
            "sites": len(probe.sites()),
        })
