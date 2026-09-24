"""
MagicFlow 魔力管家插件

根据站点魔力公式自动优化做种，最大化魔力产出。
与 BrushFlow（优化分享率/容量）目标互斥，必须独立运行。
"""

import bisect
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse

from apscheduler.triggers.cron import CronTrigger

from app.api.endpoints.plugin import register_plugin_api
from app.plugins import _PluginBase
from app.scheduler import Scheduler
from app.schemas import Response
from app.schemas.types import EventType
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger

from .bonus import (
    BonusParams,
    MagicPolicy,
    TorrentBonusInfo,
    DEFAULT_CANDIDATE_REF_WEEKS,
    calc_candidate_bonus_per_hour,
    calc_aggregate_bonus_per_hour,
    aggregate_breakdown,
    site_ceiling,
    seeds_for_coverage,
    marginal_bonus_per_hour,
    score_candidate,
    CandidateScore,
    select_optimal,
    calc_torrent_bonus,
    decide_deletions,
    preview_deletions,
    rank_candidates,
)
from .downloader_ops import (
    DownloaderAdapter,
    TorrentInfo,
    TorrentFetchFlowControl,
    _kv,
    QB_SEEDING_STATES,
    QB_DEAD_STATES,
    QB_DOWNLOADING_STATES,
    QB_PAUSED_STATES,
)
from .fingerprint import fingerprint, info_hash
from .fetcher import (
    SITE_TZ_OFFSET_HOURS,
    FilterPolicy,
    SiteCandidateTorrent,
    SiteFetcher,
    filter_candidates,
    get_default_filter_policy,
    pubdate_to_ts,
    ts_to_age_weeks,
)
from .models import (
    MagicFlowSettingsPayload,
    MagicFlowTaskPayload,
    MagicFlowTaskStatePayload,
)
from .persistence import MagicFlowStore, OperationItem
from .sites import BonusCalculator, get_calculator, get_formula_params
from .sites.formula_fetch import (
    fetch_site_formula,
    refresh_site_preset,
    fetch_seeding_pubdates,
    fetch_seeding_list,
    fetch_official_titles,
    _norm_title as normalize_title,
)

__version__ = "1.0.82"

# 候选扩充：站点列表页翻页数（拿更多、更老的种子）。
# 注意：是否能翻页取决于 fork 的 TorrentsChain.browse 是否支持 page 参数（启动时会记日志探测）。
BROWSE_PAGES = 3
# 游标深翻：翻页游标上限；超过则回到首页重扫（避免越翻越深拿到无效/超老页面）。
MAX_PAGE_CURSOR = 60
# 分类阶段并发预取 .torrent 的线程数（原为逐个串行，TopN=100 会耗时数分钟）。
# 注意：部分站点（如 PT时间）对下载接口有流控（429），并发过高会大面积失败，
# 故并发与最小间隔共同限速（见 TORRENT_DL_MIN_INTERVAL）。
TORRENT_FETCH_WORKERS = 3
# 下载 .torrent 的最小间隔（秒，全局串行限速）与单种子重试次数。
TORRENT_DL_MIN_INTERVAL = 1.0
TORRENT_DL_RETRIES = 3
# 站点魔力公式抓取缓存 TTL（秒）；抓取失败时只缓存 SHORT 秒后重试。
SITE_FORMULA_TTL = 6 * 3600
SITE_FORMULA_RETRY = 30 * 60
# 官种（official）列表抓取：缓存 TTL 与翻页数。
# 官种加成是「单种自身」的加成，会影响选种/删种排序，值得缓存抓取；
# 后宫加成依赖他人种子（用户级），与「选哪一颗」无关，不参与决策，故不抓取。
SITE_OFFICIAL_TTL = 12 * 3600
OFFICIAL_PAGES = 2

# 下载限速：已下沉到 downloader_ops 的「自适应限速闸门」（_dl_gate / _dl_note_flow_control）。
# 命中流控时间隔指数加大、成功则回落；所有 .torrent 下载（含 SDK 与回落路径）统一走它。
# 旧的 _torrent_dl_throttle 已废弃（保留常量供参考）。


# ============================================================
# 复用：按「体积接近」预筛本机种子
# ============================================================

class _SizeIndex:
    """本机种子按体积索引，支持「邻近体积」查询。

    站点列表页给出的体积是**显示文本**（如 "67.93 GB"），经 `parse_size` 转成
    「四舍五入到 0.01GB」的近似字节，而下载器里的是**精确字节** → 原来用「精确相等」
    预筛几乎永远命中不了，导致跨站存量辅种恒为 0。这里改成按容差取邻近体积，
    真正是否同一资源仍由**文件列表特征码**精确判定（放宽预筛不会误辅种）。
    """

    __slots__ = ("_items", "_sizes", "_tol")

    def __init__(self, torrents: List[Any], tol: float = 0.05):
        self._tol = max(float(tol or 0.0), 0.0)
        items = []
        for t in torrents or []:
            try:
                s = int(getattr(t, "size", 0) or 0)
            except (TypeError, ValueError):
                s = 0
            if s > 0:
                items.append((s, t))
        items.sort(key=lambda x: x[0])
        self._items = items
        self._sizes = [s for s, _ in items]

    def near(self, size: int) -> List[Any]:
        """返回本机「体积与 size 相差在容差内」的种子列表（可能为空）。"""
        try:
            size = int(size or 0)
        except (TypeError, ValueError):
            return []
        if size <= 0 or not self._sizes:
            return []
        tol = self._tol
        lo = int(size * (1.0 - tol))
        hi = int(size * (1.0 + tol)) + 1
        a = bisect.bisect_left(self._sizes, lo)
        b = bisect.bisect_right(self._sizes, hi)
        return [t for _, t in self._items[a:b]]

    def __len__(self) -> int:
        return len(self._items)


# ============================================================
# 任务配置模型
# ============================================================

@dataclass
class MagicFlowTaskConfig:
    """魔力管家任务配置。"""
    id: str = ""
    name: str = ""
    enabled: bool = True
    site_id: int = 0
    site_domain: str = ""
    site_name: str = ""
    downloader: str = "qbittorrent"
    brush_tag: str = ""
    save_path: str = ""

    # 调度配置
    brush_interval: int = 5      # 刷流间隔（分钟）
    check_interval: int = 1      # 检查间隔（分钟）
    cron_expression: str = ""    # Cron 表达式（可选）
    active_time_range: str = ""  # 活跃时间段，如 "00:00-23:59"

    # 魔力配置（None = 自动推算）
    min_bonus_per_hour: Optional[float] = None   # 每小时最低魔力产出（None=按种子分布自动）
    max_keep_torrents: Optional[int] = None      # 最多保留种子数（None=按保种体积推算/不限）
    bonus_protect_threshold: Optional[float] = None  # 魔力保护阈值（None=站点当前魔力）
    min_bonus_to_keep: float = 0.0               # 最低魔力保留值（保底）
    disk_size_gb: Optional[float] = None         # 保种体积上限（GB，None=不限）
    refill_when_empty: bool = True               # 清理后主动补种
    max_add_per_run: int = 10                    # 单轮最多新增种子数（无总量上限时的每轮名额）
    max_download_concurrent: int = 10            # 本任务同时「下载中」上限（queued 不计）
    top_n: int = 30                              # 每轮参与排序处理的候选上限（≈ 每轮新增名额的 3 倍）
    browse_pages: int = 3                        # 每轮站点列表翻页数（游标深翻）

    # 存量复用（辅种）
    reuse_existing: bool = True                  # 复用本机已有资源，避免重复下载
    reuse_verify: bool = True                    # 辅种前先校验，不匹配自动撤销

    # 无进度清理
    cleanup_no_progress: bool = True             # 每次运行清理「没进度」的种子
    no_progress_minutes: int = 30                # 加入下载器超过该分钟数仍无进度才清理

    # 慢速清理（用「下载速度 ÷ 体积」估算，长期下不完的种子占着下载名额）
    cleanup_slow_progress: bool = True           # 清理「下载过慢」的种子
    slow_progress_grace_minutes: int = 60        # 加入后多少分钟内不判「慢」（给新种起步时间）
    slow_progress_max_hours: float = 48.0        # 按当前速度预计还要超过该小时数才下完 → 判「过慢」

    # 自动恢复被暂停的已完成种子（暂停 = 0 产出）
    auto_resume_paused: bool = True

    # Ti 口径：publish（默认，= 自发布时间，站点文档口径；配合站点真实 Ni 与站点 A 吻合）
    #          seed_time（= qB 做种时长；无发布时间时的回落值）
    ti_source: str = "publish"

    # 已处理去重
    seen_cooldown_hours: float = 24.0            # 同一候选在多少小时内不重复拉取（0=不跳过）

    # 魔力公式参数（高级，None=用站点默认 / NexusPHP 标准式）
    bonus_t0: Optional[float] = None       # 生存时间参数 T0
    bonus_n0: Optional[int] = None         # 做种人数参数 N0
    bonus_b0: Optional[float] = None       # 每小时魔力上限 B0
    bonus_l: Optional[float] = None        # 曲线参数 L
    bonus_zero_weight: Optional[float] = None  # 零魔种子权重 Wi

    # 选种配置
    size: str = ""        # 大小范围，如 "1-50"（GB）
    seeder: str = ""      # 做种人数范围，如 "1-20"
    pubtime: str = ""     # 发布时间范围（分钟）
    include: str = ""     # 包含正则
    exclude: str = ""     # 排除正则
    freeleech: str = ""   # 免费过滤
    hr: str = ""          # H&R 过滤

    # 删除配置
    min_seed_time: int = 0      # 最低做种时间（小时）
    min_ratio: float = 0.0      # 最低分享率
    delete_files: bool = True   # 删除时是否删除文件
    exclude_zero_bonus: bool = True  # 排除零魔种子

    # RSS 配置
    rss_support: bool = False   # 是否使用 RSS 模式

    # 限速配置
    up_speed: Optional[int] = None   # 上传限速（KB/s）
    dl_speed: Optional[int] = None   # 下载限速（KB/s）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "site_id": self.site_id,
            "site_domain": self.site_domain,
            "site_name": self.site_name,
            "downloader": self.downloader,
            "brush_tag": self.brush_tag,
            "save_path": self.save_path,
            "brush_interval": self.brush_interval,
            "check_interval": self.check_interval,
            "cron_expression": self.cron_expression,
            "active_time_range": self.active_time_range,
            "min_bonus_per_hour": self.min_bonus_per_hour,
            "max_keep_torrents": self.max_keep_torrents,
            "bonus_protect_threshold": self.bonus_protect_threshold,
            "min_bonus_to_keep": self.min_bonus_to_keep,
            "disk_size_gb": self.disk_size_gb,
            "refill_when_empty": self.refill_when_empty,
            "max_add_per_run": self.max_add_per_run,
            "max_download_concurrent": self.max_download_concurrent,
            "top_n": self.top_n,
            "browse_pages": self.browse_pages,
            "reuse_existing": self.reuse_existing,
            "reuse_verify": self.reuse_verify,
            "cleanup_no_progress": self.cleanup_no_progress,
            "no_progress_minutes": self.no_progress_minutes,
            "cleanup_slow_progress": self.cleanup_slow_progress,
            "slow_progress_grace_minutes": self.slow_progress_grace_minutes,
            "slow_progress_max_hours": self.slow_progress_max_hours,
            "auto_resume_paused": self.auto_resume_paused,
            "ti_source": self.ti_source,
            "seen_cooldown_hours": self.seen_cooldown_hours,
            "bonus_t0": self.bonus_t0,
            "bonus_n0": self.bonus_n0,
            "bonus_b0": self.bonus_b0,
            "bonus_l": self.bonus_l,
            "bonus_zero_weight": self.bonus_zero_weight,
            "size": self.size,
            "seeder": self.seeder,
            "pubtime": self.pubtime,
            "include": self.include,
            "exclude": self.exclude,
            "freeleech": self.freeleech,
            "hr": self.hr,
            "min_seed_time": self.min_seed_time,
            "min_ratio": self.min_ratio,
            "delete_files": self.delete_files,
            "exclude_zero_bonus": self.exclude_zero_bonus,
            "rss_support": self.rss_support,
            "up_speed": self.up_speed,
            "dl_speed": self.dl_speed,
        }

    @staticmethod
    def from_dict(d: dict) -> "MagicFlowTaskConfig":
        config = MagicFlowTaskConfig()
        for key, value in (d or {}).items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config


# ============================================================
# 插件主类
# ============================================================

class MagicFlow(_PluginBase):
    """魔力管家插件主类。"""

    plugin_name = "魔力管家"
    plugin_desc = "按站点魔力公式自动养护做种，最大化魔力产出。与 BrushFlow 目标互斥。"
    plugin_icon = "mdi-magnet"
    plugin_version = __version__
    plugin_label = "站点,做种,魔力"
    plugin_author = "IronOx"
    author_url = "https://github.com/ironox"
    plugin_config_prefix = "magicflow_"
    plugin_order = 50
    auth_level = 1

    DATA_SCHEMA_VERSION = 1

    # 运行状态
    _enabled: bool = False
    _show_sidebar_nav: bool = True
    _task_configs: Dict[str, MagicFlowTaskConfig] = {}
    _task_locks: Dict[str, Any] = {}
    _task_runs: Dict[str, float] = {}
    _task_run_timeout: float = 600.0
    _dead_hashes: Dict[str, float] = {}          # 近期判定「没进度」的 hash -> 时间戳
    _dead_cooldown: float = 6 * 3600.0           # 6 小时内不再重复添加
    _store: Optional[MagicFlowStore] = None

    def init_plugin(self, config: dict = None) -> None:
        """初始化全局开关、任务配置与持久化存储。"""
        raw_config = config or {}
        self._task_locks: Dict[str, threading.Lock] = {}
        self._task_runs: Dict[str, float] = {}
        self._dead_hashes: Dict[str, float] = {}
        self._last_run_times: Dict[str, float] = {}
        self._summary_cache: Optional[Dict[str, Any]] = None
        self._summary_cache_at: float = 0.0
        self._enabled = bool(raw_config.get("enabled", False))
        self._show_sidebar_nav = bool(raw_config.get("show_sidebar_nav", True))

        self._store = MagicFlowStore(self.get_data_path())

        # 任务配置：优先从 config 读取，兼容旧版 plugindata
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
            if not task.brush_tag:
                task.brush_tag = f"魔力管家-{task.name or task.id}"
            self._task_configs[task.id] = task

        # 回写规范化配置
        self._save_config()

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
        """向主界面整理分组注册魔力管家入口"""
        if not self.get_state() or not getattr(self, "_show_sidebar_nav", True):
            return []
        return [
            {
                "nav_key": "main",
                "title": "魔力管家",
                "icon": "mdi-magnet",
                "section": "organize",
                "permission": "manage",
                "order": 46,
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        """注册 Vue 工作台使用的魔力管家任务 API"""
        return [
            {
                "path": "/status",
                "endpoint": self.get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取魔力管家总览",
            },
            {
                "path": "/settings",
                "endpoint": self.update_settings,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "更新魔力管家插件设置",
            },
            {
                "path": "/tasks",
                "endpoint": self.create_task,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "创建魔力管家任务",
            },
            {
                "path": "/tasks/{task_id}",
                "endpoint": self.get_task_detail,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取魔力管家任务详情",
            },
            {
                "path": "/tasks/{task_id}",
                "endpoint": self.update_task,
                "methods": ["PUT"],
                "auth": "bear",
                "summary": "更新魔力管家任务",
            },
            {
                "path": "/tasks/{task_id}",
                "endpoint": self.delete_task,
                "methods": ["DELETE"],
                "auth": "bear",
                "summary": "删除魔力管家任务",
            },
            {
                "path": "/tasks/{task_id}/state",
                "endpoint": self.update_task_state,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "启用或暂停魔力管家任务",
            },
            {
                "path": "/tasks/{task_id}/run",
                "endpoint": self.run_task,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行一轮魔力优化",
            },
            {
                "path": "/tasks/{task_id}/bonus",
                "endpoint": self.get_task_bonus,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取任务做种魔力明细",
            },
            {
                "path": "/tasks/{task_id}/candidates",
                "endpoint": self.get_task_candidates,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取站点候选种子及魔力评分",
            },
            {
                "path": "/tasks/{task_id}/preview",
                "endpoint": self.preview_cleanup,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "预览一轮删种名单",
            },
            {
                "path": "/tasks/{task_id}/operations",
                "endpoint": self.get_operations,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取任务操作记录",
            },
            {
                "path": "/tasks/{task_id}/torrents/{hash}/protect",
                "endpoint": self.protect_torrent,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "手动保留种子",
            },
            {
                "path": "/tasks/{task_id}/torrents/{hash}/unprotect",
                "endpoint": self.unprotect_torrent,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "取消保留种子",
            },
            {
                "path": "/tasks/{task_id}/torrents/{hash}/delete",
                "endpoint": self.manual_delete_torrent,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "手动删除种子",
            },
            {
                "path": "/sites/{site_id}/bonus-formula",
                "endpoint": self.probe_site_formula,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "抓取站点魔力公式与参数（诊断）",
            },
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """Vue 配置组件只需要接收当前配置模型"""
        return [], self._current_config()

    def get_page(self) -> List[dict]:
        """Vue 详情组件自行通过插件 API 获取页面数据"""
        return []

    def get_dashboard(self, key: str, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], None]]:
        """注册魔力管家仪表板卡片，由 Vue 组件渲染"""
        if not self.get_state():
            return None
        return (
            {"cols": 12, "sm": 6, "md": 6},
            {
                "title": "魔力管家",
                "subtitle": "魔力产出概览",
                "refresh": 30,
                "border": True,
            },
            None,
        )

    def get_service(self) -> List[Dict[str, Any]]:
        """为每个启用任务注册独立的刷流与检查服务"""
        if not self.get_state():
            return []
        services: List[Dict[str, Any]] = []
        for task in self._task_configs.values():
            if not task.enabled:
                continue

            if task.cron_expression:
                try:
                    brush_trigger: Union[str, CronTrigger] = CronTrigger.from_crontab(task.cron_expression)
                    brush_kwargs: Dict[str, Any] = {}
                except ValueError as err:
                    logger.error(f"魔力管家任务 [{task.name}] CRON 表达式无效：{str(err)}")
                    brush_trigger = "interval"
                    brush_kwargs = {"minutes": task.brush_interval}
            else:
                brush_trigger = "interval"
                brush_kwargs = {"minutes": task.brush_interval}

            services.append(
                {
                    "id": f"Task_{task.id}_Brush",
                    "name": f"魔力管家 - {task.name}",
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
                    "kwargs": {"minutes": task.check_interval},
                    "func_kwargs": {"task_id": task.id},
                }
            )
        return services

    def stop_service(self) -> None:
        """插件不维护私有调度器，公共服务由宿主统一停止"""
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
            "tasks": [task.to_dict() for task in self._task_configs.values()],
        }

    def _save_config(self) -> None:
        """保存全局设置和全部任务配置"""
        self.update_config(self._current_config())

    def _refresh_scheduler(self) -> None:
        """通知宿主按最新任务列表重建插件服务"""
        try:
            Scheduler().update_plugin_job(self.__class__.__name__)
        except Exception as err:
            logger.error(f"更新魔力管家调度失败：{str(err)}")

    def _invalidate_summary(self) -> None:
        self._summary_cache = None
        self._summary_cache_at = 0.0

    # ---------------------------------------------------------
    # 站点 / 下载器辅助
    # ---------------------------------------------------------

    def _log(self, message: str, level: str = "info") -> None:
        """写插件日志。"""
        text = f"魔力管家：{message}"
        getattr(logger, level if hasattr(logger, level) else "info")(text)

    # 运行阶段（供前端「运行诊断」流程链转圈）
    PHASE_LABELS = {
        "entry": "入口检查",
        "fetch": "抓取候选",
        "wash": "洗池过滤",
        "classify": "分类排序",
        "process": "处理入库",
        "done": "本轮结束",
        "error": "执行出错",
    }

    def _set_phase(self, task_id: str, phase: str) -> None:
        """上报当前运行阶段。"""
        if not self._store:
            return
        try:
            self._store.record_phase(task_id, phase, self.PHASE_LABELS.get(phase, phase))
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

    def _get_task_lock(self, task_id: str) -> Optional[threading.Lock]:
        """获取任务锁。"""
        if task_id not in self._task_locks:
            self._task_locks[task_id] = threading.Lock()
        return self._task_locks.get(task_id)

    def _try_begin_run(self, task_id: str) -> bool:
        """尝试开始一轮运行。

        不用不可超时的锁（一旦某轮卡死会永久堵死后续调度），
        改用「运行时间戳 + 超时」。超过 _task_run_timeout 视为僵尸轮，
        自动放行新一轮并告警。
        """
        now = time.time()
        started = self._task_runs.get(task_id, 0.0)
        if started and (now - started) < self._task_run_timeout:
            return False
        if started:
            self._log(
                f"魔力管家：检测到任务 {task_id} 上一轮已运行 "
                f"{int(now - started)} 秒仍未结束，判定为卡死，放行新一轮"
            )
        self._task_runs[task_id] = now
        return True

    def _end_run(self, task_id: str) -> None:
        """结束一轮运行，释放运行槽。"""
        self._task_runs.pop(task_id, None)

    def _get_task_config(self, task_id: str) -> Optional[MagicFlowTaskConfig]:
        """获取任务配置。"""
        return self._task_configs.get(task_id)

    def _get_downloader(self, downloader_name: str = "qbittorrent") -> Optional[DownloaderAdapter]:
        """获取下载器适配器。"""
        try:
            return DownloaderAdapter(downloader_name=downloader_name)
        except Exception as e:
            self._log(f"获取下载器失败: {e}", "error")
            return None

    def _get_site_calculator(self, site_domain: str) -> Optional[BonusCalculator]:
        """获取站点魔力计算器。"""
        return get_calculator(site_domain)

    # ---------------------------------------------------------
    # 调度与服务实现
    # ---------------------------------------------------------

    def brush(self, task_id: str) -> None:
        """抓取站点候选并补充优质魔力种子（刷流，带并发保护）。"""
        task = self._get_task_config(task_id)
        if not self._try_begin_run(task_id):
            if task:
                self._log(f"魔力管家 [{task.name}] 上一轮仍在执行，跳过本轮")
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
                        items=[OperationItem(hash="", title=self._run_summary_text(summary), reason=f"耗时 {duration:.1f}s")],
                        duration=duration,
                        error_message=summary.get("reason") if summary.get("status") == "failed" else None,
                    )
                self._store.record_run_summary(
                    task_id,
                    summary.get("status", ""),
                    summary.get("reason", ""),
                    duration,
                )
        except Exception as e:
            import traceback
            logger.error(f"魔力管家 brush 异常: {e}\n{traceback.format_exc()}")
            if self._store:
                if record:
                    self._store.journal.finalize(
                        record.operation_id, "failed", error_message=str(e), duration=time.time() - started
                    )
                self._store.record_run_summary(task_id, "failed", str(e), time.time() - started)
        finally:
            self._end_run(task_id)

    @staticmethod
    def _run_summary_text(summary: Dict[str, Any]) -> str:
        """把一轮刷流结果概括成一句话（用于操作流水）。"""
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
            return f"{flow}本轮无需动作：{summary.get('reason', '')}"
        if status == "skipped":
            return f"跳过：{summary.get('reason', '')}"
        if status == "failed":
            return f"失败：{summary.get('reason', '')}"
        return "本轮结束"

    def _same_site_keys(self, task: MagicFlowTaskConfig) -> Set[str]:
        """本站的 tracker 域名匹配键（用于「同站纳管」）。"""
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
        # 去掉常见前缀后也能匹配（www. / tracker. / pt.）
        for prefix in ("www.", "tracker.", "pt.", "t."):
            if dom.startswith(prefix) and len(dom) > len(prefix):
                keys.add(dom[len(prefix):])
        return {k for k in keys if k}

    def _adopt_same_site(self, task: MagicFlowTaskConfig, downloader: DownloaderAdapter) -> Dict[str, int]:
        """同站纳管：把下载器中「属于本站」的已有种子补打本任务 tag。

        MagicFlow 只在站点**候选列表**里找新种，会漏掉本机早已在做的同站种子
        （IYUU / 其它插件 / 手动添加）。这些种子同样为该站产出魔力，理应纳入托管
        （计入容量与保护），否则既不计魔力、又可能被重复下载。

        识别方式：种子的 tracker（announce）域名与本站 domain 匹配。
        只**追加**标签（不覆盖其它标签），不下载、不校验、不改动其它站点。

        ★ 保护策略：本插件自己下载/复用的（刷流用）照常按效率清理；
          本机**早已存在**的同站种子（IYUU / 其它插件 / 手动添加 / 自己下载的影视资源）
          一律纳入「自有资源」集合并 **永久保护**（不参与任何删种）。
        """
        keys = self._same_site_keys(task)
        if not keys:
            return {"matched": 0, "adopted": 0, "already": 0, "protected": 0}
        store = self._store
        adopted_set = store.get_adopted(task.id) if store else set()
        matched = adopted = already = 0
        to_tag: List[str] = []
        to_adopt: List[str] = []
        for t in downloader.get_raw_torrents():
            tr = str(_kv(t, "tracker", "") or "").strip()
            if not tr:
                continue
            try:
                host = (urlparse(tr).hostname or "").lower()
            except Exception:
                host = ""
            if not host or not any(k in host for k in keys):
                continue
            h = str(_kv(t, "hash", "") or "").lower()
            if not h:
                continue
            matched += 1
            tags = _kv(t, "tags", "") or []
            if isinstance(tags, str):
                tags = [x.strip() for x in tags.split(",") if x.strip()]
            if task.brush_tag not in list(tags):
                to_tag.append(h)

            if h in adopted_set:
                # 已纳管的自有资源：不重复保护（尊重用户在 UI 上的手动「取消保护」）
                already += 1
                continue
            # 本插件自己下载/复用的种子（刷流）→ 不保护，正常按效率清理
            if store and store.is_self_added(task.id, h):
                continue
            # 本机早已存在的同站种子 → 纳管并永久保护（用户自有资源）
            to_adopt.append(h)
            adopted += 1

        for h in to_tag:
            downloader.set_torrent_tags(h, [task.brush_tag])
        protected = 0
        if store and to_adopt:
            store.note_adopted(task.id, to_adopt)
            for h in to_adopt:
                if store.protect_torrent(task.id, h):
                    protected += 1

        if adopted:
            self._log(
                f"魔力管家 [{task.name}] 同站纳管：本站 tracker 种子 {matched} 个，"
                f"新纳管并保护 {adopted} 个（已在管 {already}）"
            )
        return {"matched": matched, "adopted": adopted, "already": already, "protected": protected}

    def _brush_impl(self, task_id: str) -> None:
        """抓取站点候选并补充优质魔力种子（刷流，v5 流程）。"""
        task = self._get_task_config(task_id)
        if not task or not task.enabled:
            return {"status": "skipped", "reason": "任务未启用"}
        self._log(f"魔力管家 [{task.name}] brush 开始（任务 {task_id}）")
        if self._store:
            self._store.record_run_start(task.id)
        if task.active_time_range and not self._is_in_active_time(task.active_time_range):
            self._log(f"魔力管家 [{task.name}] 当前不在活跃时间段，跳过")
            return {"status": "skipped", "reason": "不在活跃时间段"}

        downloader = self._get_downloader(task.downloader)
        if not downloader or not downloader.is_available:
            self._log(f"下载器不可用: {task.downloader}", "error")
            return {"status": "failed", "reason": "下载器不可用"}

        # ---------- ⓪ 先清理（放在**入口检查之前**）----------
        # 池满时不再直接 noop，而是先清掉零魔 / 做种人数过多 / 低于门槛 / 无进度的种子
        # 腾出空间与名额，再进入入口检查决定是否抓取。Master 口径：清理任务前置。
        try:
            _cl = self._cleanup_round(task, downloader)
            if _cl.get("deleted"):
                self._log(
                    f"魔力管家 [{task.name}] 入口前清理：删 {_cl['deleted']} 个"
                    f"（无进度 {_cl.get('no_progress', 0)} / 低效 {_cl.get('low_eff', 0)}）"
                )
        except Exception as _cle:
            self._log(f"魔力管家 [{task.name}] 入口前清理异常: {_cle}", "warning")

        # ---------- ⓪b 同站纳管：把本机上「属于本站」的已有种子补打 tag ----------
        # 本插件自己刷流加的照常按效率清理；本机早已存在的同站种子（IYUU/其它插件/
        # 手动添加/自己下载的影视资源）纳管并**永久保护**，绝不被删种。
        try:
            self._adopt_same_site(task, downloader)
        except Exception as _ade:
            self._log(f"魔力管家 [{task.name}] 同站纳管异常: {_ade}", "warning")

        try:
            # ---------- 本任务托管（tag）快照 ----------
            try:
                all_tagged, _terr = downloader.get_torrents(tags=[task.brush_tag])
            except Exception:
                all_tagged, _terr = None, None
            if all_tagged is None:
                seeding_torrents, _terr = downloader.get_seeding_torrents(tag=task.brush_tag)
                all_tagged = [t for t in (seeding_torrents or []) if task.brush_tag in (t.tags or [])]
            managed = [t for t in (all_tagged or []) if task.brush_tag in (t.tags or [])]
            managed_hashes = {(t.hash or "").lower() for t in managed if t.hash}
            base_cnt = len(managed)
            base_size = round(sum(float(getattr(t, "size_gb", 0) or 0) for t in managed), 3)
            dl_concurrent = sum(
                1 for t in managed
                if str(getattr(t, "state", "") or "").lower() in QB_DOWNLOADING_STATES
            )
            dl_limit = max(int(task.max_download_concurrent or 10), 1)
            self._log(
                f"魔力管家 [{task.name}] 托管 {base_cnt} 个 / {base_size:.2f}GB"
                f"（下载中 {dl_concurrent} 个），标签「{task.brush_tag}」"
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

            # ---------- ① 入口前置检查（不抓取、游标不推进）----------
            self._set_phase(task.id, "entry")
            # 下载并发满：仍然抓取候选——存量复用(A 类)不占下载名额，理应放行；
            # 但本轮若一个都没复用成功 → 判定为空转，不推进游标，等现有下载完成后再重试同一批。
            concurrency_full = dl_concurrent >= dl_limit
            if concurrency_full:
                self._log(
                    f"魔力管家 [{task.name}] 下载并发已达上限（{dl_concurrent}/{dl_limit}），"
                    "本轮仍抓取候选以尝试存量复用（复用通常不占下载名额；本地未完成/未校验辅种会补下载，按名额计）"
                )
            if (max_keep and base_cnt >= max_keep) or (disk_gb and base_size >= disk_gb):
                reason = "保种池容量/数量已满，本轮停止抓取，等待 check 任务清理低效种子释放空间"
                self._log(f"魔力管家 [{task.name}] {reason}")
                if self._store:
                    self._store.record_run_summary(task.id, "noop", reason)
                    self._store.record_run_success(task.id, added=0, deleted=0, kept=base_cnt)
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": reason, "added": 0, "reused": 0, "deleted": 0, "kept": base_cnt}
            if not task.refill_when_empty:
                if self._store:
                    self._store.record_run_summary(task.id, "noop", "未开启补种")
                    self._store.record_run_success(task.id, added=0, deleted=0, kept=base_cnt)
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

            # ---------- ② 抓取候选（游标深翻，成功才推进游标）----------
            self._set_phase(task.id, "fetch")
            fetcher = SiteFetcher()
            if not fetcher.is_available:
                self._log("站点抓取不可用，跳过刷流", "warning")
                return {"status": "failed", "reason": "站点抓取不可用"}

            pages = max(int(task.browse_pages or BROWSE_PAGES), 1)
            cursor = self._store.get_page_cursor(task.id) if self._store else 0
            candidates = fetcher.browse_site(
                task.site_domain,
                rss_support=task.rss_support,
                pages=pages,
                start_page=cursor,
            )
            if not candidates:
                self._log(f"魔力任务 [{task.name}] 未获取到候选种子（游标 {cursor}）")
                return {"status": "noop", "reason": "未获取到候选种子", "candidates": 0, "filtered": 0}

            next_cursor = cursor + pages
            if next_cursor > MAX_PAGE_CURSOR:
                next_cursor = 0
            # 非并发满：沿用原行为，抓取成功即推进游标；
            # 并发满：先不推进，待处理完按「本轮是否复用成功」再决定（零复用=空转不推进）。
            if self._store and not concurrency_full:
                self._store.set_page_cursor(task.id, next_cursor)
            self._log(
                f"魔力管家 [{task.name}] 抓取返回 {len(candidates)} 个候选"
                f"（游标 {cursor}，本次翻 {pages} 页）"
            )

            # ---------- ③ 洗池（尚无 infohash，仅用列表字段）----------
            self._set_phase(task.id, "wash")
            filter_policy = self._build_filter_policy(task)
            filtered, reason_counts = filter_candidates(candidates, filter_policy)
            wash_reasons: Dict[str, int] = dict(reason_counts)
            # ★ 最优解算法（做种人数 Ni × 体积 Si）：真实边际时魔。
            # a_current = 现有池子合计 A；边际增益 B(A+a)−B(A) 才能反映「再加一颗」的真实收益。
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

            # ★ 存量复用索引提前建立：辅种(复用)要在「全量候选」里找，不受 TopN 魔力排名限制。
            local_index: Dict[str, TorrentInfo] = {}
            local_by_size: "_SizeIndex" = _SizeIndex([])
            fp_cache: Dict[str, Optional[str]] = {}
            if task.reuse_existing:
                try:
                    local_index, local_by_size = self._local_reuse_index(downloader)
                    self._log(f"魔力管家 [{task.name}] 本机已有种子 {len(local_index)} 个，启用存量复用")
                except Exception as e:
                    self._log(f"建立本机资源索引失败：{e}", "warning")

            scored: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent]] = []
            reuse_pool: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent]] = []
            skipped_seen = 0
            skipped_dead = 0
            skipped_low = 0
            skipped_nosrc = 0
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
                    age_weeks=max(c.age_weeks, DEFAULT_CANDIDATE_REF_WEEKS),
                    volume_factor=c.volume_factor,
                    is_zero_bonus=c.is_zero_bonus,
                    is_free=c.is_free,
                    is_double_free=c.is_double_free,
                    hit_and_run=c.hit_and_run,
                    is_official=_is_off,
                    params=formula_params,
                )
                bonus.age_weeks = c.age_weeks
                # ★ 做种人数 Ni × 体积 Si → 最优解评分（边际时魔 + 每 GB 效率 + 可下性）
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
                    # 无做种源 ≠ 不能辅种：本机已有同一资源就能直接辅（免下载）。
                    if task.reuse_existing and local_by_size.near(int(getattr(c, "size", 0) or 0)):
                        reuse_pool.append((bonus, c))
                    continue
                setattr(c, "_score", sc)
                setattr(c, "_value", sc.value)
                setattr(c, "_eff", sc.efficiency)
                if min_bonus and bonus.bonus_per_hour < min_bonus:
                    skipped_low += 1
                    # 魔力偏低 ≠ 不能辅种；免下载的依然是白得的魔力。
                    if task.reuse_existing and local_by_size.near(int(getattr(c, "size", 0) or 0)):
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
                self._log(f"魔力任务 [{task.name}] 洗池后无可用候选（过滤通过 {len(filtered)}）")
                if self._store:
                    self._store.record_run_success(task.id, added=0, deleted=0, kept=base_cnt)
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": "洗池后无可用候选", "candidates": len(candidates), "filtered": 0}

            # ★ 最优解排序：名额受限（保种数上限）→ 按边际 value 降序；
            # 仅磁盘受限 → 按每 GB 效率 efficiency 降序（把每 GB 收益最大的先装）。
            _disk_left = (float(disk_gb) - base_size) if disk_gb else None
            _count_left = (int(max_keep) - base_cnt) if max_keep else None
            if _disk_left is not None and _count_left is None:
                scored.sort(key=lambda pair: (getattr(pair[1], "_eff", 0.0), getattr(pair[1], "_value", 0.0)), reverse=True)
            else:
                scored.sort(key=lambda pair: (getattr(pair[1], "_value", 0.0), getattr(pair[1], "_eff", 0.0)), reverse=True)
            top_n = max(int(task.top_n or 0), 1)
            topn = scored[:top_n]

            # ★ 辅种不参与魔力排名：非 TopN（魔力排不进前 N）但「体积邻近本机种子」的候选
            #   也一并纳入复用扫描——TopN 只决定「要下载哪些」，可复用的候选无需参与竞争。
            if task.reuse_existing and local_by_size:
                _have = {self._candidate_key(p[1]) for p in reuse_pool}
                for _pair in scored[top_n:]:
                    _c = _pair[1]
                    _k = self._candidate_key(_c)
                    if _k in _have:
                        continue
                    if local_by_size.near(int(getattr(_c, "size", 0) or 0)):
                        reuse_pool.append(_pair)
                        _have.add(_k)

            # ---------- ④ 分类：辅种(复用) 全量扫描 + 下载候选 TopN ----------
            self._set_phase(task.id, "classify")
            group_a: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent, str, TorrentInfo]] = []
            group_b: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent]] = []

            # ★ 辅种不参与魔力排名：只要「体积邻近本机种子」就纳入扫描（免下载 = 白得的魔力）。
            #   TopN 只决定「要下载哪些」；可复用的额外候选即便魔力排不进 TopN 也一起取回判定。
            REUSE_SCAN_MAX = 60

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
            if task.reuse_existing and reuse_pool:
                _pool = []
                for pair in reuse_pool:
                    sz = int(getattr(pair[1], "size", 0) or 0)
                    near = local_by_size.near(sz)
                    if not near:
                        continue
                    diff = min(abs(sz - int(getattr(t, "size", 0) or 0)) for t in near)
                    _pool.append((diff, pair))
                _pool.sort(key=lambda x: x[0])
                for _diff, pair in _pool:
                    if len(_fetch_map) >= top_n + REUSE_SCAN_MAX:
                        break
                    k = _ckey_of(pair)
                    if k in _fetch_map:
                        continue
                    _fetch_map[k] = pair
                    _reuse_extra += 1
            fetch_list = list(_fetch_map.values())

            # 并发预取 .torrent（TopN + 可复用候选）。
            # 每个请求各自新建 RequestUtils 会话，无共享状态，可安全并发。
            # 站点流控早停标志：一旦命中，本轮剩余候选不再请求（避免继续加剧限流）。
            _fc_hit = [False]

            def _prefetch(pair: Any) -> None:
                _b, _c = pair
                _raw = None
                _err = ""
                if _fc_hit[0]:
                    _c.raw = None
                    _c.fetch_error = "站点流控（本轮跳过）"
                    _c.real_hash = ""
                    return
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
                            # 站点流控：本轮直接放弃（重试只会加剧），且不记 dead。
                            _raw = None
                            _err = f"站点流控：{_e}"[:200]
                            _fc_hit[0] = True
                            break
                        except Exception as _e:  # noqa: BLE001
                            _raw = None
                            _err = f"{type(_e).__name__}: {_e}"[:200]
                        if _raw:
                            break
                        _err = _err or "返回空"
                        # 疑似流控/限速：退避后再试，避免连续打。
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

            if len(fetch_list) > 1:
                with ThreadPoolExecutor(max_workers=min(TORRENT_FETCH_WORKERS, len(fetch_list))) as _ex:
                    list(_ex.map(_prefetch, fetch_list))
            else:
                for _p in fetch_list:
                    _prefetch(_p)

            # 分类诊断：本轮取回多少 .torrent；没拿到时打样本原因
            _raw_ok = sum(1 for _p in fetch_list if getattr(_p[1], "raw", None))
            if _raw_ok < len(fetch_list):
                _sample = fetch_list[0][1]
                self._log(
                    f"魔力管家 [{task.name}] 种子文件获取 {_raw_ok}/{len(fetch_list)}；"
                    f"示例 enclosure={getattr(_sample, 'enclosure', '')[:90]!r} "
                    f"err={getattr(_sample, 'fetch_error', '')!r}",
                    "warning",
                )

            _cross_near = 0
            _cross_hit = 0
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
                # 半成品：本机同 hash 但仍在下载 → 不能做种，跳过
                if local and str(getattr(local, "state", "") or "").lower() in QB_DOWNLOADING_STATES:
                    continue
                mode, linfo = "", None
                if task.reuse_existing and local is not None:
                    mode, linfo = "hash", local
                elif task.reuse_existing:
                    if local_by_size.near(int(getattr(cand, "size", 0) or 0)):
                        _cross_near += 1
                    mode, linfo = self._detect_crosssite_reuse(
                        downloader, cand, local_by_size, fp_cache, raw=getattr(cand, "raw", None)
                    )
                    if mode == "cross":
                        _cross_hit += 1
                if mode and linfo is not None:
                    group_a.append((bonus, cand, mode, linfo))
                elif _in_topn:
                    # 仅 TopN 候选参与「下载」排队；为复用而额外取回的候选不可复用则丢弃。
                    group_b.append((bonus, cand))
            if task.reuse_existing:
                self._log(
                    f"魔力管家 [{task.name}] 存量复用扫描：复用命中 {len(group_a)} 个"
                    f"（体积邻近比对 {_cross_near} / 特征码命中 {_cross_hit}，另扫非 TopN {_reuse_extra} 个）"
                )

            # ★ 与洗池同一套排序键：名额受限→边际 value 降序；仅磁盘受限→每 GB 效率 efficiency 降序。
            # （修 bug：原此处用旧的「单种魔力」bonus_per_hour 重排，把洗池的边际排序又覆盖回去了）
            _disk_bound = _disk_left is not None and _count_left is None

            def _rank_key(pair: Any):
                _c = pair[1]
                if _disk_bound:
                    return (getattr(_c, "_eff", 0.0), getattr(_c, "_value", 0.0))
                return (getattr(_c, "_value", 0.0), getattr(_c, "_eff", 0.0))

            # ★ 辅种不参与魔力排名：group_a 保持发现顺序直接加（免下载）
            group_b.sort(key=_rank_key, reverse=True)
            ordered: List[Any] = list(group_a) + list(group_b)
            self._log(
                f"魔力管家 [{task.name}] Top{len(topn)} 排序：复用 {len(group_a)} / 下载 {len(group_b)}"
            )

            # ---------- ⑤ 处理循环（A 复用优先，其后 B 下载）----------
            self._set_phase(task.id, "process")
            added = 0
            reused = 0
            new_pub: Dict[str, float] = {}
            add_failed = 0
            skipped_dup = 0
            skipped_quota = 0
            skipped_reuse_limit = 0
            skipped_rate = 0
            for item in ordered:
                is_reuse = len(item) == 4
                if is_reuse:
                    bonus, cand, mode, linfo = item
                else:
                    bonus, cand = item
                h = (getattr(cand, "real_hash", "") or "").lower()
                ckey = self._candidate_key(cand)

                # 兜底去重（fetch 后二次检查）
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
                    if "流控" in _err:
                        # 临时限流：不记 dead（下轮重试），单独计数。
                        skipped_rate += 1
                        self._log(
                            f"跳过·站点流控，本轮不处理，下轮重试：{cand.title}",
                            "warning",
                        )
                        continue
                    add_failed += 1
                    if self._store and ckey:
                        self._store.dead.mark(task.id, [f"cand:{ckey}"])
                    self._log(f"跳过·无法获取种子：{cand.title}（{_err or '未知原因'}）", "warning")
                    continue

                size_gb = float(cand.size_gb or 0)
                over_quota = (
                    (max_keep and (base_cnt + add_cnt + 1) > max_keep)
                    or (disk_gb and (base_size + add_size + size_gb) > disk_gb)
                )

                if is_reuse:
                    # 辅种/复用并不总是「零下载」：本地同 hash 但未完成、或跨站辅种未开校验时，
                    # 都会触发补下载 → 这类按下载名额（并发/单轮名额）计，避免并发被绕过。
                    if mode == "hash":
                        local_progress = float(getattr(linfo, "progress", 0) or 0)
                        reuse_downloads = local_progress < 0.999
                    else:
                        reuse_downloads = not task.reuse_verify
                    # ★ 辅种（免下载）不参与配额/排名限制：直接加（白得的魔力）。
                    #   （仅当确需补下载时才受下载名额/预算约束，见下）
                    if over_quota:
                        self._log(
                            f"辅种超出配额仍直接复用（免下载）：{cand.title}"
                        )
                    if reuse_downloads:
                        if dl_concurrent >= dl_limit:
                            skipped_reuse_limit += 1
                            self._log(
                                f"复用跳过·下载并发已满（{dl_concurrent}/{dl_limit}）：{cand.title}"
                            )
                            continue
                        if dl_budget <= 0:
                            break
                    ok = False
                    if mode == "hash":
                        ok = downloader.set_torrent_tags(h, [task.brush_tag])
                        st = str(getattr(linfo, "state", "") or "").lower()
                        if st in (QB_PAUSED_STATES | {"error", "missingfiles"}):
                            downloader.resume_torrent(h)
                    else:  # 跨站辅种
                        hs, err = downloader.add_torrent_reuse(
                            torrent_bytes=cand.raw,
                            save_path=(getattr(linfo, "save_path", "") or task.save_path or ""),
                            tag=task.brush_tag,
                            verify=task.reuse_verify,
                        )
                        ok = bool(hs)
                        if ok and hs:
                            h = hs.lower()
                        if not ok and err:
                            self._log(f"辅种失败：{cand.title}（{err}）", "warning")
                    if not ok:
                        if self._store and ckey:
                            self._store.dead.mark(task.id, [f"cand:{ckey}"])
                        continue
                    reused += 1
                    add_cnt += 1
                    add_size += size_gb
                    pub_ts = self._pubdate_ts(getattr(cand, "pubdate", None))
                    if pub_ts and h:
                        new_pub[h] = pub_ts
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
                    self._log(f"复用入库{'（补下载）' if reuse_downloads else ''}：{cand.title}")
                    continue

                # B：需下载
                if dl_concurrent >= dl_limit:
                    continue
                if dl_budget <= 0:
                    break
                if over_quota:
                    skipped_quota += 1
                    continue
                hash_string, error = downloader.add_torrent(
                    content=cand.raw,
                    download_dir=task.save_path or "",
                    tag=task.brush_tag,
                    cookie=cand.site_cookie,
                    user_agent=cand.site_ua,
                    upload_limit=task.up_speed,
                    download_limit=task.dl_speed,
                )
                if hash_string:
                    added += 1
                    add_cnt += 1
                    add_size += size_gb
                    dl_budget -= 1
                    dl_concurrent += 1
                    nh = (hash_string or h).lower()
                    managed_hashes.add(nh)
                    pub_ts = self._pubdate_ts(getattr(cand, "pubdate", None))
                    if pub_ts and nh:
                        new_pub[nh] = pub_ts
                    if self._store:
                        keys = [f"hash:{nh}"]
                        if ckey:
                            keys.append(f"cand:{ckey}")
                        self._store.seen.mark(task.id, keys)
                    self._log(f"新增：{cand.title}")
                else:
                    add_failed += 1
                    if self._store and ckey:
                        self._store.dead.mark(task.id, [f"cand:{ckey}"])
                    self._log(f"添加失败：{cand.title}（{error}）", "warning")

            if self._store and new_pub:
                self._store.note_pub_dates(task.id, new_pub, tz=SITE_TZ_OFFSET_HOURS)

            if reused and self._store:
                self._store.journal.record(
                    task_id=task.id,
                    kind="reuse",
                    items=[OperationItem(hash="", title=f"存量复用 {reused} 个", reason="辅种")],
                )

            # 游标推进判定：并发满时，只有本轮复用成功才推进；零复用视为空转不推进。
            if concurrency_full:
                if reused > 0:
                    if self._store:
                        self._store.set_page_cursor(task.id, next_cursor)
                    self._log(
                        f"魔力管家 [{task.name}] 并发满但本轮复用 {reused} 个，游标 {cursor}→{next_cursor}"
                    )
                else:
                    self._log(
                        f"魔力管家 [{task.name}] 并发满且本轮无复用产出，判定空转，游标保持 {cursor} 不推进"
                    )
            cursor_note = (
                f"{cursor}→{next_cursor}"
                if (not concurrency_full or reused > 0)
                else f"{cursor}（空转未推进）"
            )

            if self._store:
                self._store.record_run_success(
                    task.id, added=added, deleted=0, kept=len(managed_hashes), reused=reused
                )
            self._invalidate_summary()
            self._set_phase(task.id, "done")
            detail = (
                f"（复用 {reused} / 新增 {added} / 去重 {skipped_dup}"
                f" / 配额满 {skipped_quota} / 复用限并发 {skipped_reuse_limit} / 流控 {skipped_rate} / 失败 {add_failed}）"
            )
            self._log(
                f"魔力管家 [{task.name}] 候选 {len(candidates)}→洗池 {len(scored)}→Top{len(topn)} | "
                f"新增 {added} / 复用 {reused}（当前托管 {len(managed_hashes)}，游标 {cursor_note}）{detail}"
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
            }

        except Exception as e:
            import traceback
            self._log(f"魔力管家 [{task.name}] 刷流失败: {e}\n{traceback.format_exc()}", "error")
            self._set_phase(task.id, "error")
            if self._store:
                try:
                    self._store.record_run_summary(task.id, "failed", str(e))
                except Exception:
                    pass
            return {"status": "failed", "reason": str(e)}

    def check(self, task_id: str) -> None:
        """执行魔力优化一轮（评估并删除低魔力产出种子）。"""
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

    def _should_run(self, task: MagicFlowTaskConfig) -> bool:
        """检查任务是否应该执行。"""
        last_run = self._last_run_times.get(task.id, 0)
        return (time.time() - last_run) >= task.check_interval * 60

    def _run_check(self, task_id: str) -> None:
        """执行魔力管家核心流程（带并发保护）。"""
        task = self._get_task_config(task_id)
        if not task:
            return
        if not self._try_begin_run(task_id):
            return
        try:
            self._run_check_impl(task)
        finally:
            self._end_run(task_id)

    def _run_check_impl(self, task: MagicFlowTaskConfig) -> None:
        """执行魔力管家核心流程（内部实现）。"""
        self._last_run_times[task.id] = time.time()
        self._store.record_run_start(task.id)

        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                self._log(f"下载器不可用: {task.downloader}", "error")
                self._store.record_run_error(task.id, "下载器不可用")
                return

            r = self._cleanup_round(task, downloader)
            self._store.record_run_success(
                task.id,
                added=0,
                deleted=int(r.get("deleted", 0) or 0),
                kept=int(r.get("kept", 0) or 0),
            )
            self._invalidate_summary()

        except Exception as e:
            self._log(f"魔力管家 [{task.name}] 执行失败: {e}", "error")
            self._store.record_run_error(task.id, str(e))

    def _cleanup_round(self, task: MagicFlowTaskConfig, downloader: DownloaderAdapter) -> Dict[str, Any]:
        """清理一轮：自动恢复暂停做种 + 清理无进度种子 + 删除低效种子。

        抽出供两处复用：
          - ``_brush_impl``：放在**入口检查之前**（池满时先清理腾空间，再决定抓取）；
          - ``_run_check_impl``：独立的 check 任务。

        返回计数 {resumed, no_progress, low_eff, deleted, kept, total_before, total_after}。
        """
        out: Dict[str, Any] = {
            "resumed": 0, "no_progress": 0, "slow": 0, "low_eff": 0, "deleted": 0,
            "kept": 0, "total_before": 0.0, "total_after": 0.0,
        }
        if not downloader or not downloader.is_available:
            return out
        protected = self._store.get_protected_torrents(task.id) if self._store else set()

        # 拉一次标签内全部种子（任意状态）：用于「自动恢复暂停」+「清理无进度」
        try:
            all_tagged, _tag_err = downloader.get_torrents(tags=[task.brush_tag])
        except Exception as _tag_exc:
            all_tagged, _tag_err = [], str(_tag_exc)

        # ① 自动恢复被暂停的已完成种子（暂停 → tracker 不计做种 → 0 产出）
        if getattr(task, "auto_resume_paused", True) and all_tagged:
            try:
                out["resumed"] = self._resume_paused_managed(task, downloader, list(all_tagged))
            except Exception as _resume_err:
                self._log(f"魔力管家 [{task.name}] 自动恢复暂停种子异常: {_resume_err}", "warning")

        # ② 清理「没进度」的种子（进度为 0 且停滞/出错/暂停，挂了够久）
        if all_tagged:
            try:
                np_deleted, _np_removed = self._cleanup_no_progress(
                    task, downloader, list(all_tagged), protected
                )
                out["no_progress"] = np_deleted
            except Exception as _cleanup_err:
                self._log(f"魔力管家 [{task.name}] 清理无进度种子异常: {_cleanup_err}", "warning")

        # ②b 清理「下载过慢」的种子（用「下载速度 ÷ 体积」估算 ETA，长期下不完的腾名额）
        if all_tagged:
            try:
                slow_deleted, _slow_removed = self._cleanup_slow_progress(
                    task, downloader, list(all_tagged), protected
                )
                out["slow"] = slow_deleted
            except Exception as _slow_err:
                self._log(f"魔力管家 [{task.name}] 清理过慢种子异常: {_slow_err}", "warning")

        # ③ 删低效种子（零魔 / 做种人数过多 / 低于门槛 / 超保种上限）
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

        out["low_eff"] = deleted_count
        out["deleted"] = int(out["no_progress"]) + int(out["slow"]) + deleted_count
        out["kept"] = len(result.to_keep)
        # ★ 站点口径合计时魔（对合计 A 只取一次 arctan + 做种固定奖励），使数值与站点上报对齐。
        # 原来把每颗种子各自的时魔简单相加 → 漏掉「做种数 × 每种子」固定奖励，只有站点值的 ~1/3。
        try:
            _agg_params = self._build_formula_params(task)
            try:
                _harem_hourly = float((self._site_reported(task) or {}).get("harem_hourly") or 0.0)
            except Exception:
                _harem_hourly = 0.0
            _deleted_hashes = {d.torrent.hash for d in result.to_delete}
            _kept_list = [t for t in torrent_bonus_list if t.hash not in _deleted_hashes]
            out["total_before"] = aggregate_breakdown(
                torrent_bonus_list, _agg_params,
                seeding_count=len(torrent_bonus_list), harem_hourly=_harem_hourly,
            )["total"]
            out["total_after"] = aggregate_breakdown(
                _kept_list, _agg_params,
                seeding_count=len(_kept_list), harem_hourly=_harem_hourly,
            )["total"]
        except Exception as _agg_err:
            self._log(f"魔力管家 [{task.name}] 站点口径时魔汇总失败，回落逐种相加：{_agg_err}", "warning")
            out["total_before"] = result.total_bonus_before
            out["total_after"] = result.total_bonus_after
        self._log(
            f"魔力管家 [{task.name}] 完成："
            f"恢复 {out['resumed']} / 无进度 {out['no_progress']} / 过慢 {out['slow']} / 低效 {deleted_count}；"
            f"保留 {out['kept']} 个，"
            f"站点口径时魔 {out['total_before']:.2f} -> {out['total_after']:.2f}/h"
        )
        return out

    def _pubdate_ts(self, pubdate: Any) -> float:
        """把候选的发布时间转为 unix 秒（与候选排序同一套口径）。"""
        return pubdate_to_ts(pubdate)

    def _task_pub_dates(self, task) -> Dict[str, float]:
        """取本任务已记录的「种子发布时间」表（hash→unix 秒）。

        按当前站点时区口径校验：时区变了 → 旧值作废，回退到「做种时长」。
        """
        try:
            if self._store and task and getattr(task, "id", None):
                return self._store.get_pub_dates(task.id, tz=SITE_TZ_OFFSET_HOURS)
        except Exception:
            pass
        return {}

    def _site_official_titles(self, site_id: int) -> set:
        """站点官种标题集合（规范化），带 TTL 缓存。

        官种加成是「单种自身」的加成（站点对官种单独再算一遍基础公式 × 官种系数），
        会影响单颗种子的产出 → 影响选种/删种排序，因此纳入内部打分；
        后宫加成是用户级（依赖他人的种子），不影响「选哪一颗」，故不参与。
        """
        site = self._get_site(site_id)
        domain = (getattr(site, "domain", "") or "").strip().lower() if site else ""
        if not domain:
            return set()
        cache = getattr(self, "_site_official_cache", None)
        if cache is None:
            cache = self._site_official_cache = {}
        now = time.time()
        hit = cache.get(domain)
        if hit and (now - hit[0]) < SITE_OFFICIAL_TTL:
            return hit[1]
        try:
            titles = set(fetch_official_titles(site, pages=OFFICIAL_PAGES))
        except Exception as err:
            self._log(f"抓取官种列表失败 [{domain}]: {err}", "warning")
            return hit[1] if hit else set()
        cache[domain] = (now, titles)
        self._log(f"官种列表 [{domain}]：{len(titles)} 个官种")
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
        """将下载器种子转换为魔力信息列表（可按站点公式参数计算）。

        ti_source：Ti 口径。``publish``（默认，= 自发布时间，站点文档口径）或
        ``seed_time``（= qB 做种时长，无发布时间时回落）。
        ni_map：hash→站点真实做种人数 Ni（可选，优先于 qB）。
        official_titles：官种标题集合（规范化），命中则标记 ``is_official``。
        """
        use_pub = str(ti_source or "publish").lower() == "publish"
        pub_dates = pub_dates or {}
        ni_map = ni_map or {}
        official_titles = official_titles or set()
        result = []
        for t in torrents:
            # Ni 优先用站点真实值；否则用 qB（做种中 → 至少 1，
            # qB 的 num_complete 对私种常为 0，不可信）。
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
            result.append(bonus_info)
        return result

    def _build_formula_params(self, task: MagicFlowTaskConfig) -> BonusParams:
        """
        解析任务对应的魔力公式参数。

        顺序：**站点自动抓取（mybonus.php，TTL 缓存）** → 站点预设（按域名）
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

    def _acquire_site_formula(self, task: MagicFlowTaskConfig):
        """
        自动抓取站点魔力公式（带 TTL 缓存）。

        命中缓存直接返回；否则用 MoviePilot SDK 抓 ``mybonus.php`` 解析。
        失败也短暂缓存（``SITE_FORMULA_RETRY``）以避免频繁打网络。
        返回 ``FormulaCapture`` 或 None。
        """
        domain = (getattr(task, "site_domain", "") or "").strip().lower()
        if not domain:
            return None
        now = time.time()
        cache = getattr(self, "_site_formula_cache", None)
        if cache is None:
            cache = self._site_formula_cache = {}
        cached = cache.get(domain)
        if cached and (now - float(cached.get("ts", 0))) < SITE_FORMULA_TTL:
            return cached.get("cap")

        site = self._get_site(task.site_id) if getattr(task, "site_id", 0) else None
        cap = None
        if site is None:
            # 站点未就绪时不缓存失败（否则会 30 分钟不再重试）
            self._log(f"站点公式：未找到站点 {getattr(task, 'site_id', 0)}，本轮跳过", "warning")
            return None
        try:
            cap = fetch_site_formula(site, timeout=15)
        except Exception as err:
            self._log(f"站点公式抓取失败 [{domain}]: {err}", "warning")
            cap = None
        if cap and cap.ok:
            try:
                refresh_site_preset(site)
                self._log(
                    f"站点公式已获取 [{domain}] {cap.note} params={cap.params} extra={cap.extra}"
                )
            except Exception:
                pass
            cache[domain] = {"ts": now, "cap": cap}
        else:
            # 失败：短缓存，稍后自动重试
            cache[domain] = {"ts": now - SITE_FORMULA_TTL + SITE_FORMULA_RETRY, "cap": cap}
        return cap

    def _bonus_formula_block(self, task: MagicFlowTaskConfig, torrent_list, seeding_count: Optional[int] = None) -> Dict[str, Any]:
        """组装「魔力计算」页所需的公式信息 + 本轮汇总推导链。"""
        params = self._build_formula_params(task)
        cap = self._acquire_site_formula(task)
        extra = dict(getattr(cap, "extra", {}) or {}) if cap else {}
        age = None
        cache = getattr(self, "_site_formula_cache", None)
        domain = (getattr(task, "site_domain", "") or "").strip().lower()
        if cache and domain in cache:
            age = max(0, int(time.time() - float(cache[domain].get("ts", 0))))
        if seeding_count is None:
            seeding_count = len(torrent_list or [])
        bd = aggregate_breakdown(torrent_list, params, seeding_count=seeding_count, harem_hourly=float(extra.get("harem_hourly") or 0))
        site_reported = extra.get("current_bonus_per_hour")
        site_reported_a = extra.get("current_a")
        deviation = None
        if site_reported:
            try:
                deviation = round((bd["total"] - float(site_reported)) / float(site_reported) * 100, 1)
            except (TypeError, ValueError, ZeroDivisionError):
                deviation = None
        return {
            "site_domain": getattr(task, "site_domain", ""),
            "site_name": getattr(task, "site_name", ""),
            "source": (getattr(cap, "source", "") if cap else "") or "default",
            "ok": bool(getattr(cap, "ok", False)) if cap else False,
            "note": getattr(cap, "note", "") if cap else "",
            "age_seconds": age,
            "expr_a": getattr(cap, "expr_a", None) if cap else None,
            "expr_b": getattr(cap, "expr_b", None) if cap else None,
            "params": {
                "t0": params.t0, "n0": params.n0, "b0": params.b0, "l": params.l,
                "zero_weight": params.zero_weight, "normal_weight": params.normal_weight,
                "official_coef": params.official_coef, "harem_coef": params.harem_coef,
                "per_torrent_flat": params.per_torrent_flat, "seeding_count_cap": params.seeding_count_cap,
            },
            "extra": extra,
            "seeding_count": int(seeding_count or 0),
            "sum_a": round(bd["a_total"], 4),
            "a_official": round(bd["a_official"], 4),
            "b_base": round(bd["b_base"], 4),
            "b_flat": round(bd["b_flat"], 4),
            "b_official": round(bd["b_official"], 4),
            "b_harem": round(bd["b_harem"], 4),
            "total": round(bd["total"], 4),
            "site_reported_a": site_reported_a,
            "site_reported_bonus": site_reported,
            "deviation_pct": deviation,
        }

    def _site_user_id(self, site) -> Optional[str]:
        """读取站点用户 UID（做种列表页需要）。优先从 cookie 的 c_secure_uid（NexusPHP = base64(uid)）解析。"""
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
            from app.db.oper.site import SiteOper
            dom = (getattr(site, "domain", "") or "").strip().lower()
            sid = getattr(site, "id", None)
            for row in SiteOper().get_userdata_latest() or []:
                if not isinstance(row, dict):
                    continue
                if (row.get("domain", "") or "").lower() == dom or (sid is not None and row.get("id") == sid):
                    uid = row.get("userid")
                    return str(uid) if uid else None
        except Exception:
            pass
        return None

    def _backfill_pub_dates(self, task, managed=None, ttl: int = 3600) -> int:
        """用站点做种列表页回填每个种子的「发布时间」（Ti 发布时长口径）。TTL 内不重复抓取。"""
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
            self._log("回填发布时间：站点不存在，跳过", "warning")
            return 0
        uid = self._site_user_id(site)
        if not uid:
            self._log("回填发布时间：未取到站点 UID，跳过", "warning")
            return 0
        try:
            rows = fetch_seeding_list(site, uid, timeout=25)
        except Exception as err:
            self._log(f"回填发布时间失败：{err}", "warning")
            return 0
        if not rows:
            self._log(f"回填发布时间：做种页为空（uid={uid}），跳过", "warning")
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
            self._log(f"回填发布时间：{len(mapping)} 个种子改用「发布时长」计算 Ti")
        else:
            self._log(f"回填发布时间：未匹配（做种页 {len(rows)} 条）", "warning")
        return len(mapping)

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
        """找到指定站点最新的用户数据行（dict 或 ORM 对象均可）。"""
        try:
            from app.db.oper.site import SiteOper
            rows = SiteOper().get_userdata_latest() or []
        except Exception:
            return None
        site = self._get_site(site_id)
        want_domain = (getattr(site, "domain", "") or "").strip() if site else ""
        for row in rows:
            if want_domain and str(self._ud_get(row, "domain", "") or "").strip() == want_domain:
                return row
            if self._ud_get(row, "id") == site_id:
                return row
        return None

    def _site_ni_map(self, site_id: int, managed) -> Dict[str, int]:
        """从站点用户数据取每颗种子的真实做种人数 Ni（按体积 1% 容差匹配）。

        站点公式的 Ni 是「当前做种者数」，qB 的 num_complete 对私种常为 0，
        不可用；seeding_info 为 [[seeders, size_bytes], ...]。
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

    def _site_reported(self, task: MagicFlowTaskConfig) -> Dict[str, Any]:
        """站点上报的魔力数据（黑盒：不展示自算值）。

        来源：抓取的 ``mybonus.php``——每小时魔力、当前 A、当前魔力值。
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
        out["current_bonus"] = self._site_current_bonus(task.site_id)
        return out

    def _site_current_bonus(self, site_id: int) -> float:
        """读取指定站点当前魔力值（用于自动保护阈值）。"""
        row = self._userdata_row(site_id)
        if row is None:
            return 0.0
        try:
            return float(self._ud_get(row, "bonus", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _site_current_bonus_old(self, site_id: int) -> float:
        """（已弃用）旧实现：依赖 row 为 dict，实际 ORM 对象会全部跳过。"""

    def _build_magic_policy(
        self,
        task: MagicFlowTaskConfig,
        torrents: Optional[List[TorrentBonusInfo]] = None,
    ) -> MagicPolicy:
        """
        从任务配置构建魔力策略。

        留空（None）的字段会自动推算：
          - min_bonus_per_hour　→ 当前种子魔力中位数 × 0.5（无数据时为 0，不删）
          - bonus_protect_threshold → 站点当前魔力（读不到则不限）
          - max_keep_torrents　 → 保种体积上限 ÷ 平均种子大小（无保种体积时为 None=不限）
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

        # 站点上限感知（很多站点有上限）：站点对「做种数」有计入上限（超过后固定奖励
        # 不再增长，纯白占硬盘）。把它作为**硬天花板**：无论用户是否显式设置保种上限，
        # 保种数都不得超过站点做种数计入上限（留空时直接取该上限）。对 Master 口径：
        # 「不展示，但必须要有这个限制」。
        params = None
        try:
            params = self._build_formula_params(task)
        except Exception:
            params = None
        cap_n = int(getattr(params, "seeding_count_cap", 0) or 0)
        if cap_n > 0:
            if max_keep is None or max_keep > cap_n:
                if max_keep not in (None, cap_n):
                    self._log(
                        f"任务 [{task.name}] 保种上限受站点限制：{max_keep} → {cap_n}"
                        f"（{getattr(task, 'site_domain', '') or task.site_id} 做种数计入上限）"
                    )
                max_keep = cap_n

        return MagicPolicy(
            min_bonus_per_hour=threshold,
            bonus_protect_threshold=protect,
            min_bonus_to_keep=task.min_bonus_to_keep or 0.0,
            max_keep_torrents=max_keep,
            min_seed_time_hours=float(task.min_seed_time or 0),
            weight_time_factor=1.0,
            weight_people_factor=1.0,
            weight_size=0.5,
            weight_zero_penalty=2.0,
            prefer_delete_zero_bonus=True,
            prefer_delete_high_ratio=False,
            prefer_delete_large=False,
        )

    # ---------------------------------------------------------
    # 无进度清理（每次运行清一次「没进度」的种子）
    # ---------------------------------------------------------

    def _is_no_progress(self, torrent: TorrentInfo, task: MagicFlowTaskConfig, now: float) -> bool:
        """
        判断种子是否「没进度」：
          - 下载进度为 0（未下载出任何数据）
          - 处于停滞/出错/暂停状态（stalledDL / metaDL / error / missingFiles / pausedDL / pausedUP）
          - 已加入下载器超过 no_progress_minutes 分钟
        三者同时满足才判定为可清理，避免误删刚添加/正在下载的种子。

        ⚠️ 只删「进度=0」的：**在涨的慢种绝不删**（慢 ≠ 差，魔力是长期费率，
        下完就一直产），只有下不动的（0% 且无进度）才占着硬盘白吃饭。
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

        被暂停 = tracker 不再计入做种 = 0 魔力产出，与魔力养护目标直接冲突；
        只恢复进度已完成（>=99.9%）的，半成品暂停（人工断点/待下载）不动。
        """
        resumed = 0
        skipped = 0
        for t in managed or []:
            state = str(getattr(t, "state", "") or "").lower()
            if state not in QB_PAUSED_STATES:
                continue
            if float(getattr(t, "progress", 0) or 0) < 0.999:
                skipped += 1
                continue
            h = getattr(t, "hash", "") or ""
            if not h:
                continue
            try:
                if downloader.resume_torrent(h):
                    resumed += 1
                    self._log(f"恢复做种：{str(getattr(t, 'title', '') or '')[:40]}")
            except Exception as err:
                self._log(f"恢复做种失败 {h[:8]}: {err}", "warning")
        if resumed or skipped:
            self._log(
                f"魔力管家 [{task.name}] 自动恢复暂停种子：恢复 {resumed} 个（跳过未完成 {skipped} 个）"
            )
        return resumed

    def _cleanup_no_progress(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> Tuple[int, List[TorrentInfo]]:
        """清理「没进度」的种子，返回 (删除数量, 被删种子列表)。"""
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
                self._log(f"魔力管家 [{task.name}] 清理无进度种子失败：{err}", "warning")
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
                    OperationItem(hash=t.hash, title=t.title, reason="无进度（停滞）", bonus_per_hour=0.0)
                    for t in removed
                ],
            )
        self._log(
            f"魔力管家 [{task.name}] 清理无进度种子 {deleted} 个"
            f"（进度为 0 且 {task.no_progress_minutes} 分钟未动）"
        )
        return deleted, removed

    def _is_too_slow(self, torrent: TorrentInfo, task: MagicFlowTaskConfig, now: float) -> bool:
        """判断种子是否「下载过慢」（用「下载速度 ÷ 体积」估算）。

        口径（Master 指定）：value = 下载速度 / 体积 → 每小时完成比例，
        再算 ETA = 剩余比例 / value；超过 slow_progress_max_hours 小时才下得完 → 过慢。

        只判「正在下载」的种子（paused 的交给自动恢复/无进度规则，不在此列）：
          - 加入不足 slow_progress_grace_minutes 分钟的新种不判（给新种起步时间）；
          - 速度为 0（含 stalledDL）= 完全不动 → 过慢；
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
        """清理「下载过慢」的种子（速度÷体积 → ETA 超过阈值），返回 (删除数, 列表)。

        过慢种子长期霸占下载名额、把入口堵死 → 清掉腾位，并记 dead 防止下轮重复选到。
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
                self._log(f"魔力管家 [{task.name}] 清理过慢种子失败：{err}", "warning")
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
                    OperationItem(hash=t.hash, title=t.title, reason="下载过慢（占名额）", bonus_per_hour=0.0)
                    for t in removed
                ],
            )
        self._log(
            f"魔力管家 [{task.name}] 清理下载过慢种子 {deleted} 个"
            f"（速度÷体积估算 > {float(getattr(task, 'slow_progress_max_hours', 48.0) or 48.0):g}h 才下完）"
        )
        return deleted, removed

    def _is_dead_cached(self, task_id: str, torrent_hash: str) -> bool:
        """近期刚被判定「没进度」并清掉的种子，短时间内不再重复添加。"""
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
        """候选种子的稳定标识（优先详情页链接，其次下载链接，避免带 passkey 变动）。"""
        for attr in ("page_url", "enclosure", "hash", "title"):
            value = getattr(cand, attr, None)
            if value:
                return str(value).strip()
        return ""

    def _local_reuse_index(
        self, downloader: DownloaderAdapter
    ) -> Tuple[Dict[str, TorrentInfo], "_SizeIndex"]:
        """本机（下载器）全部种子索引：hash(小写) -> info；体积邻近索引（含容差）。"""
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

        仅当「文件列表特征码」（路径 + 大小，含根目录名）完全一致时才辅种，
        避免误指向导致下载器白下载。返回 (是否成功, 信息)；信息为 "skip" 表示未命中。
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
                self._log(f"辅种成功：{cand.title} ← 复用「{local.title}」")
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
        跨站辅种**匹配判定**（只判定，不添加）。

        候选与本机某种子「文件列表特征码」完全一致时返回 ("cross", 本机种子)，
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

    def _build_filter_policy(self, task: MagicFlowTaskConfig) -> FilterPolicy:
        """从任务配置构建过滤策略。"""
        policy = get_default_filter_policy()

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

        policy.include_pattern = task.include
        policy.exclude_pattern = task.exclude
        policy.exclude_zero_bonus = task.exclude_zero_bonus
        return policy

    # ---------------------------------------------------------
    # 任务数据构建
    # ---------------------------------------------------------

    def _task_runtime_stats(self, task: MagicFlowTaskConfig) -> Dict[str, Any]:
        """计算单个任务的实时托管种子数与魔力产出。"""
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
        }
        # 站点上报（黑盒：不再自算模型值）
        try:
            rep = self._site_reported(task)
            stats["bonus_per_hour"] = round(rep["bonus_per_hour"], 4)
            stats["site_bonus_per_hour"] = round(rep["bonus_per_hour"], 4)
            stats["site_bonus_a"] = round(rep["a"], 2)
            stats["site_bonus_ok"] = bool(rep["ok"])
            # 该站点自己的「当前魔力存量」（不能跨站相加：各站魔力不可通约）
            stats["site_current_bonus"] = round(float(rep.get("current_bonus") or 0.0), 2)
        except Exception as err:
            self._log(f"统计任务 [{task.name}] 站点魔力失败: {err}", "warning")
        # 站点上限感知：时魔天花板（B0 + 固定奖励封顶）+ 距上限占用
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
            downloader = self._get_downloader(task.downloader)
            if downloader and downloader.is_available:
                all_tagged, _ = downloader.get_torrents(tags=[task.brush_tag])
                managed = list(all_tagged or [])
                from collections import Counter
                state_dist = dict(Counter(str(getattr(t, "state", "") or "?") for t in managed))
                self._log(
                    f"统计任务 [{task.name}] tag=「{task.brush_tag}」→ 托管 {len(managed)} 个，状态分布 {state_dist}"
                )
                seeding = [
                    t for t in managed
                    if str(getattr(t, "state", "") or "").lower() in QB_SEEDING_STATES
                ]
                stats["seeding_count"] = len(managed)
                stats["active_seeding_count"] = len(seeding)
                stats["paused_count"] = sum(
                    1 for t in managed
                    if str(getattr(t, "state", "") or "").lower() in QB_PAUSED_STATES
                )
                stats["downloading_count"] = sum(
                    1 for t in managed
                    if str(getattr(t, "state", "") or "").lower() in QB_DOWNLOADING_STATES
                )
                if seeding:
                    stats["state"] = "seeding"
                elif managed:
                    stats["state"] = "downloading"
        except Exception as err:
            self._log(f"统计任务 [{task.name}] 运行时数据失败: {err}", "warning")

        if self._store:
            store_stats = self._store.get_task_stats(task.id) or {}
            stats["protected_count"] = store_stats.get("protected_count", 0)
            if store_stats.get("last_error"):
                stats["state"] = "error"

        started = self._task_runs.get(task.id)
        if started is not None and (time.time() - started) < self._task_run_timeout:
            stats["state"] = "running"
        return stats

    def _phase_info(self, task_id: str) -> Dict[str, Any]:
        """当前运行阶段 + 是否在跑（供前端「运行诊断」流程链转圈）。"""
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
        """构建任务详情（含统计信息）。"""
        task = self._get_task_config(task_id)
        if not task:
            return None
        store_stats = self._store.get_task_stats(task_id) if self._store else {}
        return {**task.to_dict(), **store_stats, **self._phase_info(task_id)}

    def _compute_summary(self) -> Dict[str, Any]:
        """计算总览统计（20 秒缓存）。"""
        now = time.time()
        if self._summary_cache and (now - self._summary_cache_at) < 20:
            return self._summary_cache

        total_tasks = len(self._task_configs)
        enabled_tasks = sum(1 for t in self._task_configs.values() if t.enabled)
        seeding_count = 0
        bonus_per_hour = 0.0
        current_bonus = 0.0
        ceiling = 0.0

        # 站点上报魔力按「站点」去重（同一站点多任务不重复计）
        site_tasks: Dict[int, MagicFlowTaskConfig] = {}
        for task in self._task_configs.values():
            if not task.enabled:
                continue
            stats = self._task_runtime_stats(task)
            seeding_count += stats["seeding_count"]
            site_tasks.setdefault(int(task.site_id or 0), task)
        for task in site_tasks.values():
            rep = self._site_reported(task)
            bonus_per_hour += rep["bonus_per_hour"]
            current_bonus += rep["current_bonus"]
            try:
                ceiling += float(site_ceiling(self._build_formula_params(task)))
            except Exception:
                pass

        summary = {
            "total_tasks": total_tasks,
            "enabled_tasks": enabled_tasks,
            "seeding_count": seeding_count,
            "bonus_per_hour": round(bonus_per_hour, 4),
            "current_bonus": round(current_bonus, 2),
            "ceiling": round(ceiling, 2),
            "ceiling_pct": round(min(bonus_per_hour / ceiling * 100.0, 999.0), 1) if ceiling > 0 else 0.0,
        }
        self._summary_cache = summary
        self._summary_cache_at = now
        return summary

    def _build_task_list(self) -> List[Dict[str, Any]]:
        """构建任务列表（含实时统计）。"""
        tasks: List[Dict[str, Any]] = []
        for task in self._task_configs.values():
            runtime = self._task_runtime_stats(task)
            tasks.append({**task.to_dict(), **runtime, **self._phase_info(task.id)})
        return tasks

    # ---------------------------------------------------------
    # API：全局
    # ---------------------------------------------------------

    def get_status(self) -> Response:
        """获取插件总览状态。"""
        summary = self._compute_summary()
        self._log(
            f"API 总览：任务 {summary.get('total_tasks')} 启用 {summary.get('enabled_tasks')} "
            f"托管 {summary.get('seeding_count')} 魔力 {summary.get('bonus_per_hour')}/h"
        )
        return Response(
            success=True,
            data={
                "enabled": self.get_state(),
                "version": __version__,
                "show_sidebar_nav": bool(getattr(self, "_show_sidebar_nav", True)),
                "summary": summary,
                "tasks": self._build_task_list(),
                "options": {
                    "sites": self._list_sites(),
                    "downloaders": self._list_downloaders(),
                },
            },
        )

    def probe_site_formula(self, site_id: int, persist: bool = False) -> Response:
        """诊断：抓取站点 mybonus.php 并解析魔力公式与参数。

        Args:
            site_id: 站点 ID。
            persist: 是否同时把结果写入站点公式预设缓存（供内核命中）。
        """
        site = self._get_site(site_id)
        if not site:
            return Response(success=False, message="站点不存在")
        try:
            cap = fetch_site_formula(site)
            if persist and cap.ok:
                refresh_site_preset(site)
        except Exception as err:
            return Response(success=False, message=f"抓取失败: {err}")
        self._log(
            f"公式探测：site={site_id} ({getattr(site, 'domain', '')}) {cap.note} "
            f"ok={cap.ok} params={cap.params} extra={cap.extra} persist={persist}"
        )
        data = {"site_id": site_id, "domain": getattr(site, "domain", ""), "persisted": bool(persist and cap.ok)}
        data.update(cap.as_dict())
        return Response(success=True, data=data)

    def update_settings(self, payload: MagicFlowSettingsPayload) -> Response:
        """更新插件全局设置。"""
        self._enabled = bool(payload.enabled)
        self._show_sidebar_nav = bool(payload.show_sidebar_nav)
        self._save_config()
        self._refresh_scheduler()
        return Response(success=True, message="设置已保存", data=self._current_config())

    # ---------------------------------------------------------
    # API：任务 CRUD
    # ---------------------------------------------------------

    def create_task(self, payload: MagicFlowTaskPayload) -> Response:
        """创建魔力管家任务。"""
        task_id = payload.id or uuid.uuid4().hex[:12]
        if task_id in self._task_configs:
            return Response(success=False, message="任务 ID 已存在")

        site = self._get_site(payload.site_id)
        if not site:
            return Response(success=False, message="站点不存在")

        task = MagicFlowTaskConfig(
            id=task_id,
            name=payload.name,
            enabled=payload.enabled,
            site_id=payload.site_id,
            site_domain=payload.site_domain or getattr(site, "domain", "") or "",
            site_name=payload.site_name or getattr(site, "name", "") or "",
            downloader=payload.downloader,
            brush_tag=payload.brush_tag or f"魔力管家-{payload.name}",
            save_path=payload.save_path or "",
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
            cleanup_no_progress=payload.cleanup_no_progress,
            no_progress_minutes=payload.no_progress_minutes,
            cleanup_slow_progress=getattr(payload, "cleanup_slow_progress", True) is not False,
            slow_progress_grace_minutes=int(getattr(payload, "slow_progress_grace_minutes", 60) or 60),
            slow_progress_max_hours=float(getattr(payload, "slow_progress_max_hours", 48.0) or 48.0),
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
            exclude_zero_bonus=payload.exclude_zero_bonus,
            rss_support=payload.rss_support,
            up_speed=int(payload.up_speed) if payload.up_speed else None,
            dl_speed=int(payload.dl_speed) if payload.dl_speed else None,
        )

        self._task_configs[task.id] = task
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary()
        return Response(success=True, message="任务创建成功", data=self._build_task_detail(task.id))

    def get_task_detail(self, task_id: str) -> Response:
        """获取任务详情。"""
        detail = self._build_task_detail(task_id)
        if not detail:
            return Response(success=False, message="任务不存在")
        return Response(success=True, data=detail)

    def update_task(self, task_id: str, payload: MagicFlowTaskPayload) -> Response:
        """更新魔力管家任务。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        site = self._get_site(payload.site_id)
        if not site:
            return Response(success=False, message="站点不存在")

        task.name = payload.name
        task.enabled = payload.enabled
        task.site_id = payload.site_id
        task.site_domain = payload.site_domain or getattr(site, "domain", "") or ""
        task.site_name = payload.site_name or getattr(site, "name", "") or ""
        task.downloader = payload.downloader
        task.brush_tag = payload.brush_tag or task.brush_tag or f"魔力管家-{payload.name}"
        task.save_path = payload.save_path or ""
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
        task.cleanup_no_progress = payload.cleanup_no_progress
        task.no_progress_minutes = payload.no_progress_minutes
        task.cleanup_slow_progress = getattr(payload, "cleanup_slow_progress", True) is not False
        task.slow_progress_grace_minutes = int(getattr(payload, "slow_progress_grace_minutes", 60) or 60)
        task.slow_progress_max_hours = float(getattr(payload, "slow_progress_max_hours", 48.0) or 48.0)
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
        task.exclude_zero_bonus = payload.exclude_zero_bonus
        task.rss_support = payload.rss_support
        task.up_speed = int(payload.up_speed) if payload.up_speed else None
        task.dl_speed = int(payload.dl_speed) if payload.dl_speed else None

        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary()
        return Response(success=True, message="任务已更新", data=self._build_task_detail(task_id))

    def delete_task(self, task_id: str) -> Response:
        """删除魔力管家任务。"""
        if task_id not in self._task_configs:
            return Response(success=False, message="任务不存在")

        del self._task_configs[task_id]
        if self._store:
            self._store.task_states.delete(task_id)
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary()
        return Response(success=True, message="任务已删除")

    def update_task_state(self, task_id: str, payload: MagicFlowTaskStatePayload) -> Response:
        """启用或暂停任务。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        task.enabled = payload.enabled
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary()
        return Response(success=True, data=self._build_task_detail(task_id))

    def run_task(self, task_id: str) -> Response:
        """异步执行一轮魔力优化（清理低效种子并补充优质种子）。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        thread = threading.Thread(target=self.brush, args=(task_id,), daemon=True)
        thread.start()
        return Response(success=True, message="魔力优化已启动")

    # ---------------------------------------------------------
    # API：魔力明细
    # ---------------------------------------------------------

    def get_task_bonus(self, task_id: str) -> Response:
        """获取任务魔力统计及种子列表。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                self._log(f"API 做种明细：下载器不可用（{task.downloader}）", "warning")
                return Response(success=False, message="下载器不可用")

            seeding_torrents, error = downloader.get_seeding_torrents(tag=task.brush_tag)
            all_tagged, _ = downloader.get_torrents(tags=[task.brush_tag])
            task_torrents = list(all_tagged or [])
            self._log(
                f"API 做种明细：task={task_id} tag=「{task.brush_tag}」 "
                f"seeding={len(seeding_torrents or [])} err={error} tagged={len(task_torrents)}"
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

            # 黑盒：不展示自算魔力/评分/排名，只展示托管状态与进度。
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
                "protected_count": len(protected_hashes),
                "site": rep,
            })

        except Exception as e:
            self._log(f"获取魔力统计失败: {e}", "error")
            return Response(success=False, message=str(e))

    def get_task_candidates(self, task_id: str) -> Response:
        """获取候选种子（黑盒：不对外暴露自算魔力评分，仅返回名次与基础属性）。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        try:
            fetcher = SiteFetcher()
            if not fetcher.is_available:
                return Response(success=False, message="站点抓取不可用")

            candidates = fetcher.browse_site(
                task.site_domain,
                rss_support=task.rss_support,
                pages=max(int(task.browse_pages or BROWSE_PAGES), 1),
            )
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

            policy = self._build_magic_policy(task, bonus_list)
            ranked = rank_candidates(bonus_list, policy)

            candidates_data = []
            for rc in ranked:
                t = rc.torrent
                candidates_data.append({
                    "hash": t.hash,
                    "title": t.title,
                    "size_gb": round(t.size_gb, 2),
                    "seeders": t.seeders,
                    "leechers": t.leechers,
                    "age_weeks": round(t.age_weeks, 2),
                    "is_zero_bonus": t.is_zero_bonus,
                    "is_official": bool(t.is_official),
                    "rank": rc.rank,
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
            policy = self._build_magic_policy(task, torrent_bonus_list)

            preview = preview_deletions(torrent_bonus_list, policy, protected_hashes)
            return Response(success=True, data=preview)

        except Exception as e:
            self._log(f"预览删种失败: {e}", "error")
            return Response(success=False, message=str(e))

    def get_operations(self, task_id: str) -> Response:
        """获取任务操作记录。"""
        if not self._store:
            return Response(success=True, data={"operations": [], "total": 0})
        records = self._store.journal.list_by_task(task_id, limit=50)
        operations = [r.to_dict() for r in records]
        return Response(success=True, data={"operations": operations, "total": len(operations)})

    # ---------------------------------------------------------
    # API：种子操作
    # ---------------------------------------------------------

    def protect_torrent(self, task_id: str, hash: str) -> Response:
        """手动保留种子。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        if self._store:
            self._store.protect_torrent(task_id, hash)
            self._store.journal.record(
                task_id=task_id,
                kind="protection",
                items=[OperationItem(hash=hash, title="", reason="手动保留")],
            )
        self._invalidate_summary()
        return Response(success=True, message="种子已保留")

    def unprotect_torrent(self, task_id: str, hash: str) -> Response:
        """取消保留种子。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        if self._store:
            self._store.unprotect_torrent(task_id, hash)
            self._store.journal.record(
                task_id=task_id,
                kind="unprotection",
                items=[OperationItem(hash=hash, title="", reason="取消保留")],
            )
        self._invalidate_summary()
        return Response(success=True, message="已取消保留")

    def manual_delete_torrent(self, task_id: str, hash: str) -> Response:
        """手动删除种子。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                return Response(success=False, message="下载器不可用")

            success_count, error = downloader.delete_torrents(
                hashes=[hash],
                delete_file=task.delete_files,
            )
            if success_count > 0:
                if self._store:
                    self._store.journal.record(
                        task_id=task_id,
                        kind="deletion",
                        items=[OperationItem(hash=hash, title="", reason="手动删除")],
                    )
                self._invalidate_summary()
                return Response(success=True, message="种子已删除")

            return Response(success=False, message=error or "删除失败")

        except Exception as e:
            self._log(f"手动删除种子失败: {e}", "error")
            return Response(success=False, message=str(e))
