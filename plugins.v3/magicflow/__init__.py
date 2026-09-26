"""
MagicFlow 魔流插件

根据站点魔力公式自动优化做种，最大化魔力产出。
与 BrushFlow（优化分享率/容量）目标互斥，必须独立运行。
"""

import bisect
import copy
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
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
    set_dl_gate_base,
    _kv,
    QB_SEEDING_STATES,
    QB_DEAD_STATES,
    QB_DOWNLOADING_STATES,
    QB_PAUSED_STATES,
)
from .fingerprint import fingerprint, info_hash
from .iyuu_cloud import IyuuCloud, build_download_url, resolve_link_vars
from .fetcher import (
    SITE_TZ_OFFSET_HOURS,
    FilterPolicy,
    SiteCandidateTorrent,
    SiteFetcher,
    filter_candidates,
    free_time_ok,
    get_default_brush_filter_policy,
    get_default_filter_policy,
    pubdate_to_ts,
    set_request_interval,
    ts_to_age_weeks,
)
from .models import (
    MagicFlowDefaultsPayload,
    MagicFlowDownloaderPathsPayload,
    MagicFlowDownloaderPrefsPayload,
    MagicFlowSettingsPayload,
    MagicFlowTaskPayload,
    MagicFlowTaskStatePayload,
    MagicFlowTorrentBatchPayload,
    DOWNLOADER_PREF_RECOMMENDED,
)
from .persistence import MagicFlowStore, OperationItem, WorkReport
from .recommend import RecommendEngine
from .sites import BonusCalculator, get_calculator, get_formula_params
from .sites.formula_fetch import (
    fetch_site_formula,
    refresh_site_preset,
    fetch_seeding_pubdates,
    fetch_seeding_list,
    fetch_official_titles,
    fetch_torrent_promotion,
    fetch_user_torrent_urls,
    _norm_title as normalize_title,
)

__version__ = "3.0.11"

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
# 分类阶段「取种」整段时长上限（秒）：超过则不再等待剩余候选（个别请求可能卡死），
# 本轮跳过、下轮重试；避免把整轮拖到运行超时（600s）而触发「判定为卡死」。
TORRENT_FETCH_DEADLINE = 120.0
# 分类阶段「单次取种」硬超时（秒）：若在飞请求连续这么久都没有任何完成（典型=请求卡死/站点限速），
# 则放弃等待剩余候选、立即进入处理阶段，避免个别慢请求把整段拖满。
TORRENT_FETCH_PER_TIMEOUT = 20.0
# 复用扫描上限：TopN 之外额外取回「体积邻近本机」候选做辅种判定的最大数量。
# 原为 60，会让单轮取种数达到 TopN+60（如 30+55≈85），叠加站点 .torrent 限速后
# 单轮分类阶段动辄上百秒，正是「任务卡在分类排序」的主因之一；收敛到 15。
REUSE_SCAN_MAX = 15
# ★ 辅种慢扫（独立 worker）：把「复用/辅种」从主刷流流程里切出来，单独低频跑。
#   - 间隔（分钟）：比刷流间隔长很多，慢慢扫，避免短时间大量取种触发站点流控。
#   - 每轮批量：一次只取这么多个候选的 .torrent 做辅种判定。
REUSE_INTERVAL_MINUTES = 15
REUSE_WORKER_BATCH = 5
# ★ 推荐甄别（刷流种价值生命周期）：独立低频 worker，同样插件级单 worker + 轮转。
RECOMMEND_INTERVAL_MINUTES = 60
RECOMMEND_SCAN_MAX = 15
# 推荐/已在库检查：是否额外实时查媒体服务器（链）；默认可关（trimemedia 实现会报错刷日志）
RECOMMEND_LIVE_LIBRARY_CHECK = False
# 站点级候选抓取共享缓存 TTL（秒）：同站点的多个任务在此时窗内只抓**一份**候选，
# 避免 N 个任务重复打同一站点 → 触发流控（这正是「几十个任务」的主要压力来源）。
SITE_FETCH_TTL = 240.0
# ★ 全局并发闸门：插件级限制「同时在飞」的 worker 数（刷流/检查/辅种慢扫合计）。
#   几十个任务若同刻开火，会一起抢线程池 + 集中打站点 → 撞流控；这里做全局封顶。
GLOBAL_WORKER_LIMIT = 6
# 站点抓取失败后的冷却（秒）：失败站点在此时窗内不再重试抓取（共享给同站所有任务）。
SITE_FETCH_BACKOFF = 180.0
# 站点魔力公式抓取缓存 TTL（秒）；抓取失败时只缓存 SHORT 秒后重试。
SITE_FORMULA_TTL = 6 * 3600
SITE_FORMULA_RETRY = 30 * 60
# /status 实时统计（每任务一次下载器查询）缓存 TTL（秒）：
# 同一请求内「总览」与「任务列表」会各算一次，缓存可去重；也令 30s 轮询与二次进入更廉价。
STATS_TTL = 6
# 下载器「全部种子按标签分组」快照 TTL（秒）：一次拉取全部种子（qB 一次 torrents_info），
# 供所有任务共用（替代「每任务各拉一次全量」）。冷启动 /status 由 N 次全量 → 1 次。
TAG_SNAPSHOT_TTL = 6.0
# 站点/下载器「下拉选项」缓存 TTL（秒）：站点表/下载器表几乎不变，随 /status 重复拉取很浪费。
OPTIONS_TTL = 300.0
# ── 媒体资产价值闸门（2026-09-26）───────────────────────────────────────
#  我们是「影视管理」类插件：下了的资源除了刷魔力/刷流，还有「看 / 收藏」的价值。
#  命中下列标签的种子 = 已整理入库 / 跨站辅种（撑分享率）的「真·资产」
#  → 删种时**永不删除**，绝不为提效把主人真正要看/收藏的资源连文件一起删（delete_files 默认 True！）。
MEDIA_ASSET_TAGS: Tuple[str, ...] = ("已整理", "辅种")
#  另外，命中「下载历史」的种子也视为资产（覆盖“手动下的、还没被整理”的情况）。
#  历史集合按任务托管种批量查询，结果在此时长内缓存（秒），避免每轮都打 DB。
MEDIA_ASSET_HISTORY_TTL = 120.0
# ── 限时免费（促销到期）闸门（2026-09-26）──────────────────────────────
#  Pttime 等站的「免费/2X免费」是**限时**促销，到期后继续下按原价计流量。
#  候选已带出剩余免费时间（`SiteCandidateTorrent.free_remaining_sec`）：
#  剩余 < 预估下载耗时 + 余量 → 不下（下了就是白送流量/魔力）。
#  参数（速度/余量）在 fetcher.FREE_ASSUMED_SPEED_MBPS / FREE_MIN_MARGIN_SEC。
#  被跳过的候选进 dead 冷却（沿用 `_dead_cooldown`，6h），避免反复评估同一颗。
# /status 整包重数据缓存 TTL（秒）——stale-while-revalidate：命中秒回，过期后台静默刷新。
STATUS_TTL = 15
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

def _has_media_asset_tag(torrent: Any, extra_tags: Any = None) -> bool:
    """种子是否带「媒体资产」标签（已整理 / 辅种，或任务自定义排除标签）→ 删种时永不删除。"""
    tags = getattr(torrent, "tags", None) or []
    if not tags:
        return False
    if any(t in MEDIA_ASSET_TAGS for t in tags):
        return True
    if extra_tags and any(t in extra_tags for t in tags):
        return True
    return False


def _torrent_hash(torrent: Any) -> str:
    """取种子 infohash（小写）。"""
    return str(getattr(torrent, "hash", "") or "").strip().lower()


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
    """魔流任务配置。"""
    id: str = ""
    name: str = ""
    enabled: bool = True
    site_id: int = 0
    site_domain: str = ""
    site_name: str = ""
    downloader: str = "qbittorrent"
    brush_tag: str = ""
    save_path: str = ""
    # 任务类型：bonus=刷魔力（默认）；brush=刷流
    task_type: str = "bonus"
    # 运行状态（三态）：running=运行中（调度开、种子正常下载/做种）
    #   seeding=做种中（停调度 + 未完成种暂停 + 已完成种继续做种）
    #   stopped=已停止（停调度 + 全部托管种暂停，保文件可逆）
    # enabled 为其派生值：enabled = (run_mode == "running")
    run_mode: str = "running"

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

    # 促销失效清理：下载中的种子若站点已不再免费（促销过期/非免费）→ 删，避免白拉流量
    purge_unfree_incomplete: bool = True         # 下载中但站点已不再免费 → 清理（回站点核对促销）

    # 自动恢复被暂停的已完成种子（暂停 = 0 产出）
    auto_resume_paused: bool = True

    # 刷流模式（task_type=brush）：以「上传产出」为准的清理
    brush_grace_minutes: int = 15    # 新种加入后多少分钟内不判「无上传」
    upload_idle_minutes: int = 10    # 连续多少分钟上传低于门槛 → 清理（0=自动≈2×检查间隔）
    upload_min_kbps: int = 200       # 平均上传速率门槛（KB/s）：低于此值视为「无上传」
    brush_min_leechers: int = 1      # 刷流选种标准：最小下载人数（有下载需求才下）
    brush_seed_days: int = 2         # 刷流：做种满 N 天清理换新（0=回退「无上传」判定）
    # 产出换种（刷流）：单种已上传达标 / 分享率达标 → 清理换新（None=不看）
    rotate_upload_gb: Optional[float] = None
    rotate_ratio: Optional[float] = None
    # 选种排除订阅命中（刷流）
    except_subscribe: bool = True

    # 完美种保护：非零魔 ∧ 站内做种人数≤上限 ∧ 做种周数≥下限 的优质老种永久保留
    protect_perfect: bool = True
    perfect_max_seeders: int = 3
    perfect_min_weeks: float = 4.0

    # 任务目标：达到后任务自动停止（bonus=站点魔力值；brush=站点上传量 GB；None=未设）
    goal_value: Optional[float] = None

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
    delete_except_tags: str = ""  # 永不删除的标签（逗号分隔，叠加「已整理/辅种」之上）

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
            "task_type": self.task_type,
            "run_mode": self.run_mode,
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
            "purge_unfree_incomplete": self.purge_unfree_incomplete,
            "auto_resume_paused": self.auto_resume_paused,
            "brush_grace_minutes": self.brush_grace_minutes,
            "upload_idle_minutes": self.upload_idle_minutes,
            "upload_min_kbps": self.upload_min_kbps,
            "brush_min_leechers": self.brush_min_leechers,
            "brush_seed_days": self.brush_seed_days,
            "rotate_upload_gb": self.rotate_upload_gb,
            "rotate_ratio": self.rotate_ratio,
            "except_subscribe": self.except_subscribe,
            "protect_perfect": self.protect_perfect,
            "perfect_max_seeders": self.perfect_max_seeders,
            "perfect_min_weeks": self.perfect_min_weeks,
            "goal_value": self.goal_value,
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
            "delete_except_tags": self.delete_except_tags,
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
        # run_mode 为「运行状态」唯一真源；历史配置缺该字段时按 enabled 回退。
        raw = d or {}
        mode = str(raw.get("run_mode") or "").strip().lower()
        if mode not in ("running", "seeding", "stopped"):
            mode = "running" if bool(raw.get("enabled", True)) else "stopped"
        config.run_mode = mode
        config.enabled = (mode == "running")
        return config


# ============================================================
# 插件主类
# ============================================================

class MagicFlow(_PluginBase):
    """魔流插件主类。"""

    plugin_name = "魔流"
    plugin_desc = "PT 自动选种与做种管理：魔力养护 + 刷流双模式。"
    plugin_icon = "https://raw.githubusercontent.com/GuanAllen/MoviePilot-Plugins/main/icons/magicflow.png"
    plugin_version = __version__
    plugin_label = "站点,做种,魔力,刷流"
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
    _defaults: Dict[str, Any] = {}
    # 任务流量（qB 全局上传限速，按在跑任务类型自动切档）
    _bonus_upload_limit_kbps: float = 200.0
    _brush_upload_limit_kbps: float = 10240.0
    _last_up_limit_bps: Optional[int] = None
    # IYUU 云端辅种（可选）
    _iyuu_token: str = ""
    _iyuu_sites: Dict[str, Dict[str, str]] = {}
    _iyuu_client: Optional[IyuuCloud] = None

    def init_plugin(self, config: dict = None) -> None:
        """初始化全局开关、任务配置与持久化存储。"""
        raw_config = config or {}
        self._task_locks: Dict[str, threading.Lock] = {}
        self._task_runs: Dict[str, float] = {}
        self._dead_hashes: Dict[str, float] = {}
        self._last_run_times: Dict[str, float] = {}
        self._summary_cache: Optional[Dict[str, Any]] = None
        self._summary_cache_at: float = 0.0
        self._stats_cache: Dict[str, Dict[str, Any]] = {}
        # /status 重数据（总览+任务列表+选项）stale-while-revalidate 缓存
        self._status_heavy: Optional[Dict[str, Any]] = None
        self._status_heavy_at: float = 0.0
        self._status_refreshing: bool = False
        self._enabled = bool(raw_config.get("enabled", False))
        self._show_sidebar_nav = bool(raw_config.get("show_sidebar_nav", True))
        self._debug_log = bool(raw_config.get("debug_log", False))
        self._compact_mode = bool(raw_config.get("compact_mode", False))
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
        self._last_up_limit_bps = None
        # IYUU 云端辅种配置（Token 为空 = 不启用）
        self._iyuu_token = str(raw_config.get("iyuu_token") or "").strip()
        _iyuu_sites = raw_config.get("iyuu_sites")
        if not isinstance(_iyuu_sites, dict):
            _iyuu_sites = self.get_data("iyuu_sites") or {}
        self._iyuu_sites = {
            str(k).strip().lower(): dict(v)
            for k, v in (_iyuu_sites or {}).items()
            if isinstance(v, dict)
        }
        self._iyuu_client = self._build_iyuu_client(self._iyuu_token)
        rows_defaults = raw_config.get("defaults")
        if not isinstance(rows_defaults, dict):
            rows_defaults = self.get_data("defaults") or {}
            if not isinstance(rows_defaults, dict):
                rows_defaults = {}
        try:
            self._defaults = MagicFlowDefaultsPayload(**rows_defaults).model_dump()
        except Exception:
            self._defaults = MagicFlowDefaultsPayload().model_dump()

        # 刷流种甄别与推荐（价值生命周期）
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
        }
        self._recommend_engine = RecommendEngine(self)
        self._recommend_cursor = ""

        self._store = MagicFlowStore(self.get_data_path())
        self._apply_runtime_settings()

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
                task.brush_tag = f"魔流-{task.name or task.id}"
            self._task_configs[task.id] = task

        # 回写规范化配置
        self._save_config()

        # 预热总览重数据（后台）：让用户首次打开工作台时缓存已就绪、秒显。
        try:
            self._refresh_status_async()
        except Exception:
            pass

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

    def get_api(self) -> List[Dict[str, Any]]:
        """注册 Vue 工作台使用的魔流任务 API"""
        return [
            {
                "path": "/status",
                "endpoint": self.get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取魔流总览",
            },
            {
                "path": "/debug/torrents",
                "endpoint": self.debug_qb_torrents,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "诊断：列出下载器全部种子并按标签分组（只读）",
            },
            {
                "path": "/debug/fetch",
                "endpoint": self.debug_fetch_page,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "诊断：用站点 cookie 抓取页面片段（只读）",
            },
            {
                "path": "/debug/recognize",
                "endpoint": self.debug_recognize,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "诊断：识别种子名（评分/榜单/订阅）",
            },
            {
                "path": "/debug/recommend-run",
                "endpoint": self.debug_recommend_run,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "诊断：立即跑一轮推荐甄别",
            },
            {
                "path": "/debug/recommend-reset",
                "endpoint": self.debug_recommend_reset,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "诊断：清空推荐甄别结果",
            },
            {
                "path": "/settings",
                "endpoint": self.update_settings,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "更新魔流插件设置",
            },
            {
                "path": "/downloader/prefs",
                "endpoint": self.get_downloader_prefs,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "读取下载器全局参数",
            },
            {
                "path": "/downloader/prefs",
                "endpoint": self.update_downloader_prefs,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "写入下载器全局参数",
            },
            {
                "path": "/downloader/paths",
                "endpoint": self.update_downloader_paths,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "写入下载器全局目录",
            },
            {
                "path": "/defaults",
                "endpoint": self.get_defaults,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "读取默认任务模板",
            },
            {
                "path": "/defaults",
                "endpoint": self.update_defaults,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存默认任务模板",
            },
            {
                "path": "/iyuu/sites",
                "endpoint": self.get_iyuu_sites,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "列出 MoviePilot 已配置站点 + 当前 IYUU 设置（供密钥表）",
            },
            {
                "path": "/iyuu/test",
                "endpoint": self.test_iyuu,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "测试 IYUU Token 连通性",
            },
            {
                "path": "/recommend",
                "endpoint": self.get_recommend_list,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "列出推荐甄别结果",
            },
            {
                "path": "/recommend/{hash}/confirm",
                "endpoint": self.confirm_recommend,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "确认推荐（自动整理入库）",
            },
            {
                "path": "/recommend/{hash}/dismiss",
                "endpoint": self.dismiss_recommend,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "忽略推荐并删除",
            },
            {
                "path": "/recommend/{hash}/import",
                "endpoint": self.import_recommend,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "手动整理入库",
            },
            {
                "path": "/tasks",
                "endpoint": self.create_task,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "创建魔流任务",
            },
            {
                "path": "/tasks/{task_id}",
                "endpoint": self.get_task_detail,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取魔流任务详情",
            },
            {
                "path": "/tasks/{task_id}",
                "endpoint": self.update_task,
                "methods": ["PUT"],
                "auth": "bear",
                "summary": "更新魔流任务",
            },
            {
                "path": "/tasks/{task_id}",
                "endpoint": self.delete_task,
                "methods": ["DELETE"],
                "auth": "bear",
                "summary": "删除魔流任务",
            },
            {
                "path": "/tasks/{task_id}/state",
                "endpoint": self.update_task_state,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "启用或暂停魔流任务",
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
                "path": "/tasks/{task_id}/backfill-pages",
                "endpoint": self.backfill_torrent_pages,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "回填存量托管种子的详情页链接（供促销核对）",
            },
            {
                "path": "/backfill-pages",
                "endpoint": self.backfill_batch,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "对所有任务批量回填详情页链接",
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
                "path": "/tasks/{task_id}/torrents/{hash}/pause",
                "endpoint": self.pause_torrent,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "暂停种子",
            },
            {
                "path": "/tasks/{task_id}/torrents/{hash}/resume",
                "endpoint": self.resume_torrent,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "恢复做种",
            },
            {
                "path": "/tasks/{task_id}/torrents/{hash}/recheck",
                "endpoint": self.recheck_torrent,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "强制校验种子",
            },
            {
                "path": "/tasks/{task_id}/torrents/batch",
                "endpoint": self.batch_torrents,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "批量操作托管种子",
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
        """注册魔流仪表板卡片，由 Vue 组件渲染"""
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
                    logger.error(f"魔流任务 [{task.name}] CRON 表达式无效：{str(err)}")
                    brush_trigger = "interval"
                    brush_kwargs = {"minutes": task.brush_interval}
            else:
                brush_trigger = "interval"
                brush_kwargs = {
                    "minutes": task.brush_interval,
                    "jitter": self._jitter_seconds(task.brush_interval),
                }

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
        # ★ 辅种慢扫：插件级**单 worker**（在循环外注册一次；一个服务，遍历所有符合条件的魔力任务）。
        #   每轮只处理一个任务 → 服务数不随任务数增长，天然错峰/限流，避免几十个任务
        #   同时取种撞站点流控。刷流任务只辅助「排名内」的种子（主流程顺带做），不纳入。
        if any(
            getattr(t, "enabled", False) and getattr(t, "reuse_existing", False)
            and str(getattr(t, "task_type", "bonus") or "bonus").strip().lower() != "brush"
            for t in self._task_configs.values()
        ):
            services.append(
                {
                    "id": "Reuse",
                    "name": "辅种慢扫",
                    "trigger": "interval",
                    "func": self.reuse_scan,
                    "kwargs": {
                        "minutes": REUSE_INTERVAL_MINUTES,
                        "jitter": self._jitter_seconds(REUSE_INTERVAL_MINUTES),
                    },
                }
            )
        # ★ 推荐甄别：插件级单 worker（每轮只处理一个任务 → 服务数不随任务数增长）。
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
            "debug_log": bool(getattr(self, "_debug_log", False)),
            "compact_mode": bool(getattr(self, "_compact_mode", False)),
            "journal_keep": int(getattr(self, "_journal_keep", 200) or 0),
            "request_interval": float(getattr(self, "_request_interval", 0) or 0),
            "bonus_upload_limit_kbps": float(getattr(self, "_bonus_upload_limit_kbps", 200.0) or 0),
            "brush_upload_limit_kbps": float(getattr(self, "_brush_upload_limit_kbps", 10240.0) or 0),
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
            "defaults": dict(getattr(self, "_defaults", {}) or {}),
            "tasks": [task.to_dict() for task in self._task_configs.values()],
        }

    def _apply_runtime_settings(self) -> None:
        """把全局设置下推到运行时组件（操作记录裁剪 / 站点请求节流）。"""
        if self._store is not None:
            try:
                self._store.journal.set_keep(getattr(self, "_journal_keep", 0))
            except Exception as err:
                self._log(f"应用操作记录上限失败：{err}")
        try:
            set_request_interval(getattr(self, "_request_interval", 0))
            set_dl_gate_base(getattr(self, "_request_interval", 0))
        except Exception as err:
            self._log(f"应用站点请求间隔失败：{err}")

    # ---------------------------------------------------------
    # 任务流量：qB 全局上传限速（按在跑任务类型自动切档，只限上传）
    # ---------------------------------------------------------

    def _resolve_task_upload_limit_kbps(self) -> Tuple[float, str]:
        """按「在跑的任务类型」解析应设的全局上传限速（KB/s）。

        优先级：刷流 > 魔力 > 无（清除）。插件全局未启用时一律清除。
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
        """把 qB 全局上传限速写成「按在跑任务类型」的值（刷流>魔力>清除）。

        - 只限上传（up_limit），不动下载；
        - 值未变化时跳过写入（force=True 强制写）；
        - 无启用任务 / 插件未启用 → 清除（0=不限）。
        """
        kbps, label = self._resolve_task_upload_limit_kbps()
        bps = self._kbps_to_bps(kbps)
        if not force and bps == getattr(self, "_last_up_limit_bps", None):
            return
        # 选一个在跑任务的下载器（缺省 qbittorrent）
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
            self._dbg(f"任务流量：qB 全局上传限速 → {kbps:g} KB/s（按{label}）")
            self._log(f"任务流量：qB 全局上传限速 → {kbps:g} KB/s（按{label}）")
        else:
            self._log(f"任务流量：设置全局上传限速失败：{err}", "warning")

    def _spawn_run_mode_apply(self, task: MagicFlowTaskConfig, mode: str) -> None:
        """异步应用运行状态对应的种子操作（暂停/恢复），并在「运行中」时立即跑一轮 check。"""
        def _worker():
            try:
                self._apply_run_mode(task, mode)
            except Exception as err:
                self._log(f"魔流 [{task.name}] 应用运行状态失败：{err}", "warning")
        threading.Thread(target=_worker, daemon=True).start()

    def _apply_run_mode(self, task: MagicFlowTaskConfig, mode: str) -> Dict[str, int]:
        """按运行状态操作托管种子（只动本任务标签内的种子，保文件、可逆）。

        - ``running``：恢复所有被暂停的托管种（尊重手动暂停），随后立刻跑一轮 check；
        - ``seeding``：暂停「未完成」种（防非免费偷下），已完成种继续做种；
        - ``stopped``：暂停全部托管种（保文件）。

        返回 {paused, resumed}。
        """
        mode = self._normalize_run_mode(mode)
        out = {"paused": 0, "resumed": 0}
        downloader = self._get_downloader(task.downloader)
        if not downloader or not downloader.is_available:
            if mode == "running":
                self._run_check(task.id)
            return out
        try:
            all_tagged, _err = downloader.get_torrents(tags=[task.brush_tag])
        except Exception as exc:
            self._log(f"魔流 [{task.name}] 读取托管种子失败：{exc}", "warning")
            all_tagged = []
        managed = list(all_tagged or [])
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
        mode_label = {"running": "运行中", "seeding": "做种中", "stopped": "已停止"}.get(mode, mode)
        self._log(
            f"魔流 [{task.name}] 运行状态 → {mode_label}"
            f"（暂停 {out['paused']} / 恢复 {out['resumed']}）"
        )
        if self._store:
            try:
                self._store.journal.record(
                    task_id=task.id,
                    kind="state",
                    items=[OperationItem(
                        hash="",
                        title=f"运行状态 → {mode_label}",
                        reason=f"暂停 {out['paused']} / 恢复 {out['resumed']}",
                    )],
                )
            except Exception as err:
                self._log(f"记录运行状态变更失败：{err}", "warning")
        if mode == "running":
            self._run_check(task.id)
        return out

    def _save_config(self) -> None:
        """保存全局设置和全部任务配置"""
        self.update_config(self._current_config())

    def _refresh_scheduler(self) -> None:
        """通知宿主按最新任务列表重建插件服务"""
        try:
            Scheduler().update_plugin_job(self.__class__.__name__)
        except Exception as err:
            logger.error(f"更新魔流调度失败：{str(err)}")

    def _invalidate_summary(self, drop: bool = False) -> None:
        self._summary_cache = None
        self._summary_cache_at = 0.0
        self._stats_cache = {}
        # 默认保留旧快照（_status_heavy），仅标记过期：下次 /status 秒回旧值
        # 并后台刷新（stale-while-revalidate），避免每轮任务结束后首屏退化为轻量壳。
        self._status_heavy_at = 0.0
        if drop:
            # 结构性变更（增/删/改任务、切换状态）：丢弃旧快照 → 下次请求先返回
            # 轻量壳（由最新任务配置构建，立即含新增/删除的任务）再后台补统计。
            self._status_heavy = None

    # ---------------------------------------------------------
    # 站点 / 下载器辅助
    # ---------------------------------------------------------

    def _log(self, message: str, level: str = "info") -> None:
        """写插件日志。"""
        text = f"魔流：{message}"
        getattr(logger, level if hasattr(logger, level) else "info")(text)

    def _dbg(self, message: str) -> None:
        """调试日志：仅在全局「调试日志」开启时输出。"""
        if getattr(self, "_debug_log", False):
            self._log(f"[调试] {message}")

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

    def _set_phase(self, task_id: str, phase: str, detail: str = "") -> None:
        """上报当前运行阶段（detail 为阶段内细粒度进度，供前端显示）。"""
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
                f"魔流：检测到任务 {task_id} 上一轮已运行 "
                f"{int(now - started)} 秒仍未结束，判定为卡死，放行新一轮"
            )
        self._task_runs[task_id] = now
        return True

    def _end_run(self, task_id: str) -> None:
        """结束一轮运行，释放运行槽。"""
        self._task_runs.pop(task_id, None)

    # ---------------------------------------------------------
    # 全局并发闸门（插件级）：限制同时在飞的 worker 数
    # ---------------------------------------------------------

    def _acquire_worker_slot(self, label: str = "") -> bool:
        """非阻塞抢一个全局 worker 槽；抢不到就跳过本轮（不排队，避免堆积）。"""
        sem = getattr(self, "_worker_sem", None)
        if sem is None:
            sem = self._worker_sem = threading.Semaphore(int(GLOBAL_WORKER_LIMIT))
        if sem.acquire(blocking=False):
            return True
        self._log(
            f"魔流 全局并发闸门已满（上限 {GLOBAL_WORKER_LIMIT}），[{label or 'worker'}] 本轮跳过"
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
        """统一分账入口：把 worker 的 WorkReport 交给 store.settle（无 store 则忽略）。"""
        if not self._store:
            return
        try:
            self._store.settle(report)
        except Exception as e:  # noqa: BLE001
            logger.error(f"魔流 分账失败：{e}")

    @staticmethod
    def _jitter_seconds(minutes: Any) -> int:
        """interval 抖动（秒）：取间隔的 ~15%，夹在 [3, 90]，错开几十个任务的同刻开火。"""
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
            return DownloaderAdapter(downloader_name=downloader_name)
        except Exception as e:
            self._log(f"获取下载器失败: {e}", "error")
            return None

    def _media_asset_hashes(self, torrents: List[Any], task: Optional["MagicFlowTaskConfig"] = None) -> Set[str]:
        """媒体资产价值闸门：返回「删种时永不删除」的种子 hash 集合。

        两层判据（并集）：
          1. 标签命中 ``MEDIA_ASSET_TAGS``（已整理 / 辅种）——最直接；
          2. 命中 MoviePilot「下载历史」（覆盖手动下的、尚未整理入库的资源）。
        下载历史集合按任务托管种**批量**查询并短缓存（``MEDIA_ASSET_HISTORY_TTL``），
        避免每轮都打 DB。任何查询失败都只记 debug、不阻断删种流程。
        """
        hashes: Set[str] = set()
        cand: List[str] = []
        # 任务级自定义「永不删除标签」（叠加在 MEDIA_ASSET_TAGS 之上）
        extra_tags: Set[str] = set()
        if task is not None:
            _extra_raw = str(getattr(task, "delete_except_tags", "") or "")
            extra_tags = {s.strip() for s in _extra_raw.replace("，", ",").split(",") if s.strip()}
        for t in torrents or []:
            h = _torrent_hash(t)
            if not h:
                continue
            cand.append(h)
            if _has_media_asset_tag(t, extra_tags):
                hashes.add(h)
        if not cand:
            return hashes
        now = time.time()
        cache = getattr(self, "_asset_hist_cache", None)
        if cache is None:
            cache = self._asset_hist_cache = {}
        uniq = sorted(set(cand))
        key = str(len(uniq)) + ":" + ":".join(uniq[:200])
        hit = cache.get("__data__")
        if not (hit and (now - float(hit.get("ts", 0))) < MEDIA_ASSET_HISTORY_TTL and hit.get("key") == key):
            hist: Set[str] = set()
            try:
                from app.db.oper.downloadhistory import DownloadHistoryOper  # noqa: WPS433
                recs = DownloadHistoryOper().get_by_hashes(uniq) or {}
                for h in recs:
                    if h:
                        hist.add(str(h).lower())
            except Exception as err:
                self._dbg(f"下载历史查询失败（忽略）: {err}")
            hit = cache["__data__"] = {"ts": time.time(), "key": key, "hist": hist}
        hashes |= set(hit.get("hist") or set())
        # 只统计「本任务托管范围内」的资产（避免把无关 hash 也算进去）
        return {h for h in hashes if h in set(uniq)}

    def _tag_snapshot(self, downloader_name: str = "qbittorrent") -> Dict[str, List[Any]]:
        """下载器「全部种子按标签分组」快照（tag -> [TorrentInfo]），带短 TTL 缓存。

        **一次拉取全部种子**（qB 一次 torrents_info）供所有任务共用，替代旧的
        「每任务各调 get_torrents(tags=[tag])（= 各自全量拉取）」。总览、任务列表、
        做种明细都读这一份，冷启动 /status 的下载器查询由 N 次 → 1 次。
        """
        now = time.time()
        cache = getattr(self, "_tag_snapshot_cache", None)
        lock = getattr(self, "_tag_snapshot_lock", None)
        if cache is None or lock is None:
            cache = self._tag_snapshot_cache = {}
            lock = self._tag_snapshot_lock = threading.Lock()
        hit = cache.get(downloader_name)
        if hit and (now - float(hit.get("ts", 0))) < TAG_SNAPSHOT_TTL:
            return hit.get("groups") or {}
        with lock:
            hit = cache.get(downloader_name)
            if hit and (time.time() - float(hit.get("ts", 0))) < TAG_SNAPSHOT_TTL:
                return hit.get("groups") or {}
            groups: Dict[str, List[Any]] = {}
            try:
                dl = self._get_downloader(downloader_name)
                if dl and dl.is_available:
                    groups, _err = dl.get_torrents_by_tag()
            except Exception as err:
                self._log(f"标签快照获取失败: {err}", "warning")
            cache[downloader_name] = {"ts": time.time(), "groups": groups}
            return groups

    def _cached_options(self) -> Dict[str, Any]:
        """站点/下载器下拉选项（带 TTL 缓存）。几乎不变，无需随每次 /status 重拉。"""
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

    def _get_site_calculator(self, site_domain: str) -> Optional[BonusCalculator]:
        """获取站点魔力计算器。"""
        return get_calculator(site_domain)

    def _fetch_site_candidates(
        self,
        task: "MagicFlowTaskConfig",
        pages: int = 1,
        start_page: int = 0,
        np_free: bool = False,
    ) -> List[Any]:
        """站点级共享抓取（single-flight + 短 TTL）。

        **同一站点只抓一份候选列表**，刷流与魔力任务共用——二者只是**排序/筛选**不同，
        数据源是同一份（把「N 个任务 × 每任务一次抓取」压成「1 次」），避免几十个任务
        同站重复取列表触发流控。
          - 缓存 key 只含 **站点 + 翻页数**（不含任务/免费标志/起始页）→ 同站所有任务共享；
          - 同 key 并发时用锁「单飞」：先到的抓，后到的等它填缓存再复用；
          - 返回**浅拷贝**（每任务各自改 _score/raw/real_hash，互不串味）。

        ``np_free`` 保留仅为兼容：现在统一抓**完整列表**，刷流侧自行筛免费
        （见 _brush_impl），以保证魔力任务也能用同一份数据。

        注意：站点「最新 N 页」是**按发布时间的窗口**，会**漏掉较早的免费种**
        （实测 Pttime：最新 150 条只有 5 个免费，而免费种散落在前 400 条里共 15 个）。
        故本函数在最新页之外**额外并上 NexusPHP 免费定向视图**（spstate=2/4，一页即全），
        去重后作为同站唯一一份候选——这样刷流筛免费能拿全、魔力也能吃到这批免费种。
        """
        site_key = (
            str(getattr(task, "site_domain", "") or "") or f"site:{getattr(task, 'site_id', '')}"
        ).strip().lower()
        # 一份数据：同站（同翻页）共享同一 key；刷流/魔力只是用不同的排序/筛选消费它。
        cache_key = f"{site_key}|{int(pages)}"
        now = time.time()
        cache = getattr(self, "_site_fetch_cache", None)
        if cache is None:
            cache = self._site_fetch_cache = {}
        # 顺手清理过期项，防无界增长
        if len(cache) > 64:
            for _k in [k for k, v in cache.items() if (now - float(v[0])) >= SITE_FETCH_TTL]:
                cache.pop(_k, None)
        hit = cache.get(cache_key)
        if hit and (now - float(hit[0])) < SITE_FETCH_TTL:
            return [copy.copy(c) for c in hit[1]]

        locks = getattr(self, "_site_fetch_locks", None)
        if locks is None:
            locks = self._site_fetch_locks = {}
        lock = locks.setdefault(cache_key, threading.Lock())
        with lock:
            # double-check：可能已被同站的其他任务填充
            hit = cache.get(cache_key)
            if hit and (time.time() - float(hit[0])) < SITE_FETCH_TTL:
                return [copy.copy(c) for c in hit[1]]
            # 站点级失败冷却（共享给同站所有任务）：上次没抓到 → 冷却期内不再重试，避免反复空打
            backoff = getattr(self, "_site_backoff", None)
            if backoff is None:
                backoff = self._site_backoff = {}
            until = float(backoff.get(site_key, 0.0) or 0.0)
            if time.time() < until:
                self._log(
                    f"魔流 [{task.name}] 站点 {site_key} 冷却中"
                    f"（剩余 {int(until - time.time())}s），本轮跳过抓取"
                )
                return []
            fetcher = SiteFetcher()
            if not fetcher.is_available:
                return []
            cands: List[Any] = []
            try:
                cands = fetcher.browse_site(
                    task.site_domain,
                    rss_support=getattr(task, "rss_support", False),
                    pages=pages,
                    start_page=start_page,
                ) or []
            except Exception as err:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 站点抓取失败：{err}", "warning")
                cands = []
            cands = list(cands)
            # 补充：NexusPHP 免费定向视图（最新页窗口天生漏免费种，见上）。
            # 失败/非 NexusPHP 站点返回空，静默忽略，不影响最新页结果。
            try:
                site = self._get_site(int(getattr(task, "site_id", 0) or 0))
                if site and getattr(site, "cookie", None):
                    np_free = fetcher.browse_site_np_free(site, pages=1) or []
                    if np_free:
                        def _ck(c: Any) -> str:
                            return (
                                getattr(c, "page_url", "")
                                or getattr(c, "hash", "")
                                or getattr(c, "title", "")
                            )

                        by_key = {_ck(c): c for c in cands if _ck(c)}
                        added = 0
                        upgraded = 0
                        for c in np_free:
                            k = _ck(c)
                            if not k:
                                continue
                            old = by_key.get(k)
                            if old is None:
                                by_key[k] = c
                                cands.append(c)
                                added += 1
                                continue
                            # ★ 同一种：把「限时免费到期时间」等促销信息并进已有候选。
                            # 最新页走 SDK（不含到期时间），免费定向视图才有 → 必须回填，
                            # 否则「免费即将到期」闸门对最新页那批种失效。
                            try:
                                if float(getattr(c, "free_remaining_sec", -1.0) or -1.0) >= 0:
                                    old.free_until = getattr(c, "free_until", "") or ""
                                    old.free_remaining_sec = c.free_remaining_sec
                                    if getattr(c, "is_free", False):
                                        old.is_free = True
                                        old.is_double_free = bool(
                                            getattr(c, "is_double_free", False)
                                        )
                                        old.downloadvolumefactor = getattr(
                                            c, "downloadvolumefactor", 0.0
                                        )
                                        old.uploadvolumefactor = getattr(
                                            c, "uploadvolumefactor", 1.0
                                        )
                                        old.volume_factor = getattr(c, "volume_factor", 0.0)
                                    upgraded += 1
                            except Exception:  # noqa: BLE001
                                pass
                        if added or upgraded:
                            self._log(
                                f"魔流 [{task.name}] 站点共享列表补充免费定向 {added} 个"
                                f"（最新页窗口漏掉的免费种）"
                                + (f"，回填到期时间 {upgraded} 个" if upgraded else "")
                            )
            except Exception as err:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 免费定向补充失败（忽略）：{err}", "warning")
            if cands:
                cache[cache_key] = (time.time(), cands)
                backoff.pop(site_key, None)
            else:
                # 没抓到（失败/空）：不缓存空表（免得把站点“冻”满 TTL），改用显式冷却
                backoff[site_key] = time.time() + SITE_FETCH_BACKOFF
                self._log(
                    f"魔流 [{task.name}] 站点 {site_key} 未取到候选，冷却 "
                    f"{int(SITE_FETCH_BACKOFF)}s 后重试",
                    "warning",
                )
            return [copy.copy(c) for c in cands]

    # ---------------------------------------------------------
    # 调度与服务实现
    # ---------------------------------------------------------

    def brush(self, task_id: str) -> None:
        """抓取站点候选并补充优质魔力种子（刷流，带并发保护）。"""
        task = self._get_task_config(task_id)
        self._apply_task_traffic_limit()
        if task and self._maybe_autostop_for_goal(task):
            return
        if not self._acquire_worker_slot(f"刷流·{task.name if task else task_id}"):
            return
        if not self._try_begin_run(task_id):
            if task:
                self._log(f"魔流 [{task.name}] 上一轮仍在执行，跳过本轮")
            self._release_worker_slot()
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
                        items=self._run_items(summary, duration),
                        duration=duration,
                        error_message=summary.get("reason") if summary.get("status") == "failed" else None,
                    )
                self._settle(WorkReport(
                    task_id=task_id,
                    source="brush",
                    status=summary.get("status", ""),
                    reason=summary.get("reason", ""),
                    duration=duration,
                    added=summary.get("added"),
                    deleted=summary.get("deleted"),
                    kept=summary.get("kept"),
                    reused=summary.get("reused"),
                ))
        except Exception as e:
            import traceback
            logger.error(f"魔流 brush 异常: {e}\n{traceback.format_exc()}")
            if self._store:
                if record:
                    self._store.journal.finalize(
                        record.operation_id, "failed", error_message=str(e), duration=time.time() - started
                    )
                self._settle(WorkReport(
                    task_id=task_id, source="brush", status="failed",
                    reason=str(e), duration=time.time() - started,
                ))
        finally:
            self._end_run(task_id)
            self._release_worker_slot()

    def reuse_scan(self) -> None:
        """辅种慢扫（插件级**单 worker**，低频）。

        不再每任务注册服务，而是**一个插件级服务**遍历所有符合条件的魔力任务，
        每轮只处理其中**一个**（round-robin）→ 服务数不随任务数增长，天然错峰/限流，
        避免几十个任务在同一时刻一起取种、撞站点流控。
        刷流任务只辅助「排名内」的种子（主流程顺带做），不纳入。
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
        """对单个任务做一轮辅种慢扫（内部实现）。"""
        task_id = str(task.id)
        if not task.enabled or not task.reuse_existing:
            return
        if str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush":
            return
        if not self._try_begin_run(task_id):
            self._log(f"魔流 [{task.name}] 辅种慢扫：上一轮仍在执行，跳过")
            return
        started = time.time()
        reused = 0
        scanned = 0
        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                self._log(f"魔流 [{task.name}] 辅种慢扫：下载器不可用", "warning")
                return
            if not task.site_domain:
                site = self._get_site(task.site_id)
                if site:
                    task.site_domain = getattr(site, "domain", "") or task.site_domain
            try:
                local_index, local_by_size = self._local_reuse_index(downloader)
            except Exception as _le:  # noqa: BLE001
                self._log(f"魔流 [{task.name}] 辅种慢扫：建本机索引失败 {_le}", "warning")
                return
            if not local_index:
                return

            fetcher = SiteFetcher()
            if not fetcher.is_available:
                return
            pages = max(int(task.browse_pages or BROWSE_PAGES), 1)
            # 站点级共享抓取：同站多任务共用一份候选（single-flight + 短 TTL）
            candidates = self._fetch_site_candidates(task, pages=pages, start_page=0)
            if not candidates:
                return
            filter_policy = self._build_filter_policy(task)
            filtered, _rc = filter_candidates(candidates, filter_policy)

            # 选「体积邻近本机」且尚未由本 worker 处理过的候选
            pool = []
            for c in filtered:
                if not getattr(c, "enclosure", ""):
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
                try:
                    raw = downloader.fetch_torrent_bytes(
                        c.enclosure,
                        cookie=getattr(c, "site_cookie", None),
                        user_agent=getattr(c, "site_ua", None),
                        referer=getattr(c, "page_url", "") or None,
                    )
                except TorrentFetchFlowControl as _fe:
                    self._log(f"魔流 [{task.name}] 辅种慢扫：站点流控，本轮中止（{_fe}）", "warning")
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
                        self._log(f"魔流 [{task.name}] 辅种慢扫·复用（本机同 hash）：{c.title}")
                else:
                    hs, err = downloader.add_torrent_reuse(
                        torrent_bytes=raw,
                        save_path=(getattr(linfo, "save_path", "") or task.save_path or ""),
                        tag=tag,
                        verify=task.reuse_verify,
                    )
                    if hs:
                        reused += 1
                        self._log(f"魔流 [{task.name}] 辅种慢扫·跨站辅种：{c.title}")
                    elif err:
                        self._log(f"魔流 [{task.name}] 辅种慢扫·辅种失败：{c.title}（{err}）", "warning")

            self._log(
                f"魔流 [{task.name}] 辅种慢扫完成：命中 {reused} 个（本轮扫 {scanned} 个候选，"
                f"耗时 {time.time() - started:.1f}s）"
            )
            # 分账：慢扫走独立命名空间（slow_reused），不碰刷流/检查的 last_* 字段
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
                        hash="", title=f"辅种慢扫：命中 {reused} / 扫 {scanned}",
                        reason="复用（本机已有资源）", source="reuse",
                    )],
                )
        except Exception as e:  # noqa: BLE001
            import traceback
            logger.error(f"魔流 辅种慢扫异常: {e}\n{traceback.format_exc()}")
            self._log(f"魔流 [{task.name}] 辅种慢扫异常：{e}", "warning")
        finally:
            self._end_run(task_id)

    # ---------------------------------------------------------
    # 推荐甄别（刷流种价值生命周期）
    # ---------------------------------------------------------

    def _get_recommend_engine(self) -> RecommendEngine:
        engine = getattr(self, "_recommend_engine", None)
        if engine is None:
            engine = self._recommend_engine = RecommendEngine(self)
        return engine

    def _exclude_subscribed(self, candidates: List[Any]) -> List[Any]:
        """刷流选种：剔除命中「当前订阅标题」的候选。

        用归一化标题**子串**匹配（订阅标题 ⊆ 候选标题）；识别不出 / 订阅为空 → 原样返回，
        不误杀。订阅标题过短（<2 字符）不参与匹配，避免误伤。
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
        from .recommend import _norm  # noqa: WPS433
        out: List[Any] = []
        for c in candidates:
            nt = _norm(getattr(c, "title", ""))
            if nt and any(s in nt for s in subs):
                continue
            out.append(c)
        return out

    @staticmethod
    def _recommend_media_key(media: Optional[Dict[str, Any]], info: Dict[str, Any]) -> str:
        """作品级去重 key：优先「数据源_原生ID」，否则回退「标题(+年份)」。"""
        if media and media.get("source") and media.get("id"):
            return f"{media.get('source')}_{media.get('id')}"
        title = str(info.get("title") or "").strip().lower()
        if not title:
            return ""
        year = info.get("year")
        return f"t:{title}:{year}" if year else f"t:{title}"

    def _recommend_in_library(self, info: Dict[str, Any]) -> bool:
        """识别结果是否**已在影视库**中。

        主路：``MediaServerOper().exists``（MoviePilot 同步的媒体库 DB 表，也是官方
        「/mediaserver/exists 查询本地是否存在」用的口径）。
        可选：``MediaServerChain().media_exists`` 实时查媒体服务器（默认关，因
        trimemedia/FileManagerModule 的实现会报错刷日志）。
        任何异常都视为「未知」→ False（不阻断）。结果按 media_key 短缓存（600s）。
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
        # 1) 主路：MoviePilot 同步的媒体库 DB 表（稳定、无副作用）
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
            self._dbg(f"影视库DB查询失败（忽略）: {err}")
        # 2) 可选：实时查媒体服务器（能发现尚未同步进 DB 的条目）
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
                self._dbg(f"影视库实时查询失败（忽略）: {err}")
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
        """同一部作品是否已有指定状态的记录；返回命中的 hash（用于跨 hash 去重）。"""
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
            if str(rec.get("media_key") or "") == media_key:
                return str(h)
        return None

    @staticmethod
    def _recommend_worth(info: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
        """是否够格推荐：评分 > 门槛 且（按需）叠加 榜单/热映/订阅。"""
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
        # 或关系：命中「榜单 / 热映 / 订阅」也算达标（叠加豆瓣评分）
        if bool(cfg.get("require_chart", True)) and (
            info.get("in_chart") or info.get("in_subscribe")
        ):
            return True
        return False

    def _recommend_low_disk(self, torrents: List[Any]) -> bool:
        """当前任务保存卷是否「磁盘不足」（低于阈值即视为过期）。"""
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
        try:
            import shutil
            return (shutil.disk_usage(path).free / (1024 ** 3)) < min_free_gb
        except Exception:  # noqa: BLE001
            return False

    def recommend_scan(self) -> None:
        """推荐甄别（插件级**单 worker**，低频）。每轮只处理一个任务（round-robin）。"""
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        if not cfg.get("enabled", True):
            return
        eligible = [t for t in self._task_configs.values() if getattr(t, "enabled", False)]
        if not eligible:
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

    def _recommend_scan_task(self, task: MagicFlowTaskConfig) -> None:
        """对单个任务做一轮推荐甄别（识别 + 推荐/临时判定 + 生命周期清理）。"""
        task_id = str(task.id)
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        if not cfg.get("enabled", True) or not getattr(task, "enabled", False):
            return
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return
        downloader = self._get_downloader(task.downloader)
        if not downloader or not downloader.is_available:
            return
        if not self._try_begin_run(task_id):
            self._log(f"魔流 [{task.name}] 推荐甄别：上一轮仍在执行，跳过")
            return
        try:
            tag = task.brush_tag
            groups = self._tag_snapshot(getattr(task, "downloader", None) or "qbittorrent")
            torrents = list(groups.get(tag, []) or [])
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
            to_delete: List[str] = []
            budget = max(int(RECOMMEND_SCAN_MAX), 1)
            for t in torrents:
                h = str(getattr(t, "hash", "") or "").lower()
                if not h or h in asset:
                    continue
                rec = store.get(h) or {}
                status = rec.get("status")
                if status in ("confirmed", "dismissed", "deleted"):
                    continue
                # 手动保护的种子（无推荐记录）跳过；推荐/待确认由本 worker 管理（才能走到过期删）
                if h in protected and status not in ("recommended", "pending"):
                    continue
                first_seen = float(rec.get("first_seen") or 0) or now
                scanned += 1
                if status == "recommended":
                    if low_disk or (expire_sec > 0 and now - first_seen > expire_sec):
                        store.set_status(
                            h, "expired", note="磁盘不足" if low_disk else "过期未确认"
                        )
                        to_delete.append(h)
                        expired += 1
                    continue
                if status == "pending" and rec.get("evaluated_at"):
                    # 已评估过：① 口径变化后可能升级为推荐（用已存字段，免重复识别）② 复查 TTL
                    _like = {
                        "recognized": bool(rec.get("media")),
                        "rating": rec.get("rating"),
                        "in_chart": rec.get("in_chart"),
                        "in_subscribe": rec.get("in_subscribe"),
                    }
                    if self._recommend_worth(_like, cfg) and not self._recommend_dup(
                        store, str(rec.get("media_key") or ""), h, ("recommended", "confirmed")
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
                        store.set_status(h, "expired", note="临时种到期")
                        to_delete.append(h)
                        expired += 1
                    continue
                # 首次见到 → 甄别（每轮封顶，分摊识别开销）
                if budget <= 0:
                    continue
                budget -= 1
                evaluated += 1
                info = engine.evaluate(str(getattr(t, "title", "") or ""))
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
                    "evaluated_at": now,
                }
                media_key = self._recommend_media_key(media, info)
                base["media_key"] = media_key
                # 未识别（非影视/识别不出）→ 不入推荐库
                if not info.get("recognized"):
                    continue
                # 已在影视库 → 不入推荐库（资源已在库，无需跟踪/推荐）
                if self._recommend_in_library(info):
                    continue
                worth = self._recommend_worth(info, cfg)
                # 同片已有同类记录 → 不重复建档（避免同名多条）
                _dup_statuses = ("recommended", "confirmed") if worth else ("pending",)
                if self._recommend_dup(store, media_key, h, _dup_statuses):
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
                    # 识别出但未达门槛 → 记为临时种（仅供 TTL 回收 + 去重记忆，列表默认不展示）
                    store.upsert(
                        h, status="pending", **base,
                        reason=(f"评分 {info.get('rating')}" if info.get("rating") else "未达门槛"),
                    )
                    if temp_sec > 0 and now - first_seen > temp_sec:
                        store.set_status(h, "expired", note="临时种到期")
                        to_delete.append(h)
                        expired += 1
            # 执行删除（过期未确认 / 临时种到期）
            if to_delete:
                success, error = downloader.delete_torrents(hashes=to_delete, delete_file=True)
                if error:
                    self._log(f"魔流 [{task.name}] 推荐甄别：删除失败 {error}", "warning")
                items = []
                for h in to_delete:
                    rec2 = store.get(h) or {}
                    items.append(OperationItem(
                        hash=h, title=str(rec2.get("title") or ""),
                        size_gb=float(rec2.get("size_gb") or 0),
                        reason=str(rec2.get("note") or "过期未确认"), source="recommend",
                    ))
                    if success:
                        store.set_status(h, "deleted")
                self._store.journal.record(task_id=task_id, kind="recommend", items=items)
            if scanned or to_delete:
                _prot = len(self._store.get_protected_torrents(task_id)) if self._store else 0
                self._log(
                    f"魔流 [{task.name}] 推荐甄别：扫 {scanned} · 新评估 {evaluated} · "
                    f"新推荐 {recommended} · 过期清理 {expired} · 保护集合 {_prot}"
                    + ("（磁盘不足）" if low_disk else "")
                )
        except Exception as e:  # noqa: BLE001
            import traceback
            logger.error(f"魔流 推荐甄别异常: {e}\n{traceback.format_exc()}")
            self._log(f"魔流 [{task.name}] 推荐甄别异常：{e}", "warning")
        finally:
            self._end_run(task_id)

    def _recommend_tag(self, downloader: DownloaderAdapter, task_id: str,
                       rec_tag: str, h: str) -> bool:
        """给推荐种子补上「推荐」标签（append 语义，不动其它标签）。"""
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
        """命中推荐时推送通知（可关）。"""
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
                    f"发现值得收藏的资源：{title} {year}\n"
                    f"评分 {rating} · {mark}\n"
                    f"体积 {float(getattr(torrent, 'size_gb', 0) or 0):.2f} GB · 任务「{task.name}」\n"
                    f"已打「{self._recommend_cfg.get('tag')}」标签并保护；过期未确认将自动清理。\n"
                    f"在工作台 →「推荐」确认入库，或按需忽略。"
                ),
            )
        except Exception as err:  # noqa: BLE001
            self._log(f"推荐通知发送失败：{err}", "warning")

    def _recommend_import(self, h: str, rec: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """确认后自动整理入库：识别 → 用 TransferChain 手动整理该资源。"""
        try:
            from app.chain.transfer import TransferChain  # type: ignore  # noqa: WPS433
            from app.schemas.file import FileItem  # type: ignore  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return False, f"MoviePilot 整理接口不可用：{err}"
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
            return False, "缺少资源标题，无法识别"
        try:
            from .recommend import recognize  # noqa: WPS433
            mi = recognize(title)
        except Exception:  # noqa: BLE001
            mi = None
        if not mi:
            return False, "未能识别媒体信息，无法自动整理"
        save_path = ""
        if torrent is not None:
            save_path = str(
                getattr(torrent, "content_path", "") or getattr(torrent, "save_path", "") or ""
            )
        if not save_path:
            return False, "缺少保存路径，无法自动整理"
        try:
            import os as _os
            clean = save_path.rstrip("/")
            fileitem = FileItem(
                path=save_path, storage="local", type="dir",
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
            self._log(f"推荐整理「{title}」→ ok={ok} msg={msg}")
            return bool(ok), str(msg)
        except Exception as err:  # noqa: BLE001
            import traceback
            logger.error(f"魔流 推荐整理异常: {err}\n{traceback.format_exc()}")
            return False, f"整理异常：{err}"

    def _run_items(self, summary: Dict[str, Any], duration: float) -> List[OperationItem]:
        """一轮刷流的操作明细：首行摘要 + 逐条「新增 / 复用 / 失败」明细。"""
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

        if to_tag:
            # 🔎 标签审计：纳管同站种子（打任务标签）
            self._log(
                f"[标签审计] 纳管同站种子 {len(to_tag)} 个 → 标签「{task.brush_tag}」"
            )
        for h in to_tag:
            downloader.set_torrent_tags(h, [task.brush_tag])
        if to_tag and self._store:
            try:
                self._store.journal.record(
                    task_id=task.id,
                    kind="tag",
                    items=[OperationItem(
                        hash="",
                        title=f"同站纳管·补标签 {len(to_tag)} 个",
                        reason=f"→「{task.brush_tag}」",
                        source="adopt",
                        tags=f"→{task.brush_tag}",
                    )],
                )
            except Exception as _jerr:
                self._log(f"记录纳管标签事件失败：{_jerr}", "warning")
        protected = 0
        if store and to_adopt:
            store.note_adopted(task.id, to_adopt)
            for h in to_adopt:
                if store.protect_torrent(task.id, h):
                    protected += 1

        if adopted:
            self._log(
                f"魔流 [{task.name}] 同站纳管：本站 tracker 种子 {matched} 个，"
                f"新纳管并保护 {adopted} 个（已在管 {already}）"
            )
        return {"matched": matched, "adopted": adopted, "already": already, "protected": protected}

    def _watch_tag_integrity(self, task: MagicFlowTaskConfig, count: int) -> None:
        """托管数看门狗：与上一轮对比，骤降至一半以下 → 记「标签疑似被外部清除」。

        专用于捕捉“种子还在、标签却被抹掉”这类**不产生删种记录**的异常
        （如 MoviePilot 核心 get_torrent_id_by_tag → delete_torrents_tags 删全局标签定义）。
        正常清理会带来 deleted>0，本看门狗只看“无删种却骤降”。
        """
        if not self._store or count is None:
            return
        try:
            c = int(count)
        except (TypeError, ValueError):
            return
        prev = self._store.get_last_tagged_count(task.id)
        if prev >= 3 and c < prev * 0.5:
            self._log(
                f"魔流 [{task.name}] ⚠️ 托管数骤降 {prev} → {c}（本轮未见删种，疑似标签被外部清除）",
                "warning",
            )
            try:
                self._store.journal.record(
                    task_id=task.id,
                    kind="tag",
                    items=[OperationItem(
                        hash="", source="watchdog",
                        title=f"⚠️ 托管数骤降 {prev} → {c}",
                        reason="本轮未见删种，疑似标签被外部工具清除",
                    )],
                )
            except Exception:
                pass
        # 记“较高值”：一次骤降后不被低值覆盖，保证下次仍能对比出新的骤降
        self._store.set_last_tagged_count(task.id, max(prev, c))

    def _brush_impl(self, task_id: str) -> None:
        """抓取站点候选并补充优质魔力种子（刷流，v5 流程）。"""
        task = self._get_task_config(task_id)
        if not task or not task.enabled:
            return {"status": "skipped", "reason": "任务未启用"}
        self._log(f"魔流 [{task.name}] brush 开始（任务 {task_id}）")
        if self._store:
            self._store.record_run_start(task.id)
        if task.active_time_range and not self._is_in_active_time(task.active_time_range):
            self._log(f"魔流 [{task.name}] 当前不在活跃时间段，跳过")
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
                    f"魔流 [{task.name}] 入口前清理：删 {_cl['deleted']} 个"
                    f"（无进度 {_cl.get('no_progress', 0)} / 低效 {_cl.get('low_eff', 0)}）"
                )
        except Exception as _cle:
            self._log(f"魔流 [{task.name}] 入口前清理异常: {_cle}", "warning")

        # ---------- ⓪b 同站纳管：把本机上「属于本站」的已有种子补打 tag ----------
        # 本插件自己刷流加的照常按效率清理；本机早已存在的同站种子（IYUU/其它插件/
        # 手动添加/自己下载的影视资源）纳管并**永久保护**，绝不被删种。
        try:
            self._adopt_same_site(task, downloader)
        except Exception as _ade:
            self._log(f"魔流 [{task.name}] 同站纳管异常: {_ade}", "warning")

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
                f"魔流 [{task.name}] 托管 {base_cnt} 个 / {base_size:.2f}GB"
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
                _reason = (
                    f"下载并发已达上限（{dl_concurrent}/{dl_limit}），无空闲槽位，"
                    "本轮不抓取不下种（避免无效请求），等待槽位释放"
                )
                self._log(f"魔流 [{task.name}] {_reason}")
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": _reason, "added": 0, "reused": 0, "deleted": 0, "kept": base_cnt}
            if (max_keep and base_cnt >= max_keep) or (disk_gb and base_size >= disk_gb):
                reason = "保种池容量/数量已满，本轮停止抓取，等待 check 任务清理低效种子释放空间"
                self._log(f"魔流 [{task.name}] {reason}")
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": reason, "added": 0, "reused": 0, "deleted": 0, "kept": base_cnt}
            if not task.refill_when_empty:
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
            # 刷流有自己的「翻页口径」：只看**最新**几页（免费热种永远在最新页），
            # 不做游标深翻（深翻只会翻到促销早已过期的老种）。刷魔力才需要深翻老种。
            _brush_crawl = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"
            cursor = 0 if _brush_crawl else (self._store.get_page_cursor(task.id) if self._store else 0)
            candidates = None
            # 站点级共享：同站只抓一份**完整**候选列表，刷流与魔力共用
            # （二者只是排序/筛选不同；谁先抓谁填缓存，其余在 TTL 内复用）。
            candidates = self._fetch_site_candidates(
                task, pages=pages, start_page=(0 if _brush_crawl else cursor)
            )
            if _brush_crawl and candidates:
                # 刷流只吃免费/2X免费：从共享的完整列表里筛（不动共享数据本体）。
                candidates = [
                    c for c in candidates
                    if getattr(c, "is_free", False) or getattr(c, "is_double_free", False)
                ]
                self._log(f"魔流 [{task.name}] 刷流·免费筛选 命中 {len(candidates)} 个")
            if not candidates:
                self._log(f"魔力任务 [{task.name}] 未获取到候选种子（游标 {cursor}）")
                return {"status": "noop", "reason": "未获取到候选种子", "candidates": 0, "filtered": 0}

            next_cursor = 0 if _brush_crawl else (cursor + pages)
            if next_cursor > MAX_PAGE_CURSOR:
                next_cursor = 0
            # 非并发满：沿用原行为，抓取成功即推进游标；
            # 并发满：先不推进，待处理完按「本轮是否复用成功」再决定（零复用=空转不推进）。
            if self._store and not concurrency_full:
                self._store.set_page_cursor(task.id, next_cursor)
            self._log(
                f"魔流 [{task.name}] 抓取返回 {len(candidates)} 个候选"
                f"（游标 {cursor}，本次翻 {pages} 页）"
            )

            # ---------- ③ 洗池（尚无 infohash，仅用列表字段）----------
            self._set_phase(task.id, "wash")
            filter_policy = self._build_filter_policy(task)
            filtered, reason_counts = filter_candidates(candidates, filter_policy)
            wash_reasons: Dict[str, int] = dict(reason_counts)
            # ★ 限时免费闸门（洗池级）：促销剩的免费时间不够下完 → 直接洗掉。
            # 常见于 Pttime 这类「12 分钟～6 天」的限时免费；到期后下载按原价计流量。
            if filtered:
                _keep_c: List[Any] = []
                _expiring = 0
                _expiring_sample = ""
                for _c in filtered:
                    _ok, _need, _remain = free_time_ok(_c)
                    if _ok:
                        _keep_c.append(_c)
                    else:
                        _expiring += 1
                        if not _expiring_sample:
                            _expiring_sample = (
                                f"{getattr(_c, 'title', '')}（剩余 {int(_remain / 60)} 分 "
                                f"< 需 {int(_need / 60)} 分）"
                            )
                if _expiring:
                    filtered = _keep_c
                    wash_reasons["免费即将到期"] = _expiring
                    self._log(
                        f"魔流 [{task.name}] 洗掉「免费即将到期」{_expiring} 个"
                        f"（如：{_expiring_sample}）",
                        "warning",
                    )
            # ★ 订阅排除（刷流选种）：命中当前订阅标题的候选直接剔除，避免抢主人要看的片。
            if filtered and getattr(task, "except_subscribe", True):
                try:
                    _before = len(filtered)
                    filtered = self._exclude_subscribed(filtered)
                    _excl = _before - len(filtered)
                    if _excl:
                        wash_reasons["订阅命中"] = _excl
                        self._log(f"魔流 [{task.name}] 排除订阅命中 {_excl} 个")
                except Exception as _sub_err:
                    self._dbg(f"订阅排除失败（忽略）: {_sub_err}")
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
                    self._log(f"魔流 [{task.name}] 本机已有种子 {len(local_index)} 个，启用存量复用")
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
                    # 但刷流任务只辅助「排名内」的种子，不做非 TopN 的额外复用扫描。
                    if not _brush_crawl and task.reuse_existing and local_by_size.near(int(getattr(c, "size", 0) or 0)):
                        reuse_pool.append((bonus, c))
                    continue
                setattr(c, "_score", sc)
                setattr(c, "_value", sc.value)
                setattr(c, "_eff", sc.efficiency)
                if min_bonus and bonus.bonus_per_hour < min_bonus:
                    skipped_low += 1
                    # 魔力偏低 ≠ 不能辅种；免下载的依然是白得的魔力。
                    # 刷流任务不做非 TopN 的额外复用扫描。
                    if not _brush_crawl and task.reuse_existing and local_by_size.near(int(getattr(c, "size", 0) or 0)):
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
                self._invalidate_summary()
                self._set_phase(task.id, "done")
                return {"status": "noop", "reason": "洗池后无可用候选", "candidates": len(candidates), "filtered": 0, "added": 0, "reused": 0, "deleted": 0, "kept": base_cnt}

            # ★ 最优解排序：名额受限（保种数上限）→ 按边际 value 降序；
            # 仅磁盘受限 → 按每 GB 效率 efficiency 降序（把每 GB 收益最大的先装）。
            _disk_left = (float(disk_gb) - base_size) if disk_gb else None
            _count_left = (int(max_keep) - base_cnt) if max_keep else None
            _is_brush_task = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"
            if _is_brush_task:
                # 刷流模式：按「上传潜力」排序 —— leechers（下载需求）优先，其次体积大、更新鲜。
                scored.sort(
                    key=lambda pair: (
                        int(getattr(pair[1], "leechers", 0) or 0),
                        float(getattr(pair[1], "size_gb", 0.0) or 0.0),
                        -float(getattr(pair[1], "age_weeks", 0.0) or 0.0),
                    ),
                    reverse=True,
                )
            elif _disk_left is not None and _count_left is None:
                scored.sort(key=lambda pair: (getattr(pair[1], "_eff", 0.0), getattr(pair[1], "_value", 0.0)), reverse=True)
            else:
                scored.sort(key=lambda pair: (getattr(pair[1], "_value", 0.0), getattr(pair[1], "_eff", 0.0)), reverse=True)
            top_n = max(int(task.top_n or 0), 1)
            topn = scored[:top_n]
            self._dbg(
                f"[{task.name}] 洗池 {len(candidates)}→通过 {len(scored)}→Top{len(topn)}"
                f"（disk_left={_disk_left} count_left={_count_left}）"
            )

            # ★ 复用/辅种已从主流程切出，交给独立的「辅种慢扫」worker 处理（见 reuse_scan）。
            #   主流程只针对 TopN 取种下单；已取回的 TopN 种仍会「顺带」做一次复用判定（零额外请求）。

            # ---------- ④ 分类：下载候选 TopN（顺带复用已取回的种）----------
            self._set_phase(task.id, "classify")
            group_a: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent, str, TorrentInfo]] = []
            group_b: List[Tuple[TorrentBonusInfo, SiteCandidateTorrent]] = []

            # ★ 辅种不参与魔力排名：只要「体积邻近本机种子」就纳入扫描（免下载 = 白得的魔力）。
            #   TopN 只决定「要下载哪些」；可复用的额外候选即便魔力排不进 TopN 也一起取回判定。
            #   （扫描上限 REUSE_SCAN_MAX 见模块顶部常量）

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
            fetch_list = list(_fetch_map.values())
            # ★ 只为「能真正用上的名额」取种：空闲槽位不足时，多余取种是纯无效请求（还会触发站点流控）。
            #   刷流任务尤其重要：有 N 个空位就只取 N 个，不再一次取满 TopN。
            if _brush_crawl:
                _free_slots = max(int(dl_limit) - int(dl_concurrent), 0)
                if _free_slots and len(fetch_list) > _free_slots:
                    _before_n = len(fetch_list)
                    fetch_list = fetch_list[:_free_slots]
                    self._log(
                        f"魔流 [{task.name}] 取种数按空闲槽位封顶：{_before_n} → {len(fetch_list)}"
                        f"（空位 {_free_slots}/{dl_limit}）"
                    )

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

            _t_pref = time.time()
            _pref_done = 0
            if len(fetch_list) > 1:
                _ex = ThreadPoolExecutor(max_workers=min(TORRENT_FETCH_WORKERS, len(fetch_list)))
                _futs = {_ex.submit(_prefetch, _p): _p for _p in fetch_list}
                _pending = set(_futs.keys())
                _batch_deadline = _t_pref + TORRENT_FETCH_DEADLINE
                _last_prog = _t_pref
                try:
                    # 边完成边推进：同时受「整段上限」与「单次硬超时」双重约束。
                    # 单次硬超时 = 连续 TORRENT_FETCH_PER_TIMEOUT 秒内没有任何一个请求完成
                    # （典型=在飞请求全部卡死/站点限速）→ 放弃等待剩余候选，立即进入处理阶段。
                    while _pending:
                        _remain = _batch_deadline - time.time()
                        if _remain <= 0:
                            break
                        _done, _pending = wait(
                            _pending,
                            timeout=min(TORRENT_FETCH_PER_TIMEOUT, _remain),
                            return_when=FIRST_COMPLETED,
                        )
                        for _fut in _done:
                            try:
                                _fut.result()
                            except Exception:
                                pass
                            _pref_done += 1
                        if not _done:
                            # 单次硬超时：在飞请求全部无响应，放弃等待，避免整段被拖满。
                            self._log(
                                f"魔流 [{task.name}] 分类取种单次超时"
                                f"（{TORRENT_FETCH_PER_TIMEOUT:.0f}s 无进展，已取 {_pref_done}/{len(fetch_list)}）"
                            )
                            break
                        # 细粒度进度（限流，避免频繁写盘）：供前端显示，避免「像卡住」
                        _now = time.time()
                        if _now - _last_prog >= 5.0:
                            _last_prog = _now
                            self._set_phase(task.id, "classify", f"取种 {_pref_done}/{len(fetch_list)}")
                finally:
                    _ex.shutdown(wait=False, cancel_futures=True)
                # 未完成（被取消/未执行）的候选标记「超时跳过」，供处理循环安全跳过（不记 dead）
                for _p in fetch_list:
                    if getattr(_p[1], "raw", None) is None and not getattr(_p[1], "fetch_error", ""):
                        _p[1].raw = None
                        _p[1].fetch_error = "分类取种超时（本轮跳过）"
                        try:
                            _p[1].real_hash = ""
                        except Exception:
                            pass
            else:
                for _p in fetch_list:
                    _prefetch(_p)
                _pref_done = len(fetch_list)
            self._log(
                f"魔流 [{task.name}] 分类取种 {_pref_done}/{len(fetch_list)} 个"
                f"（耗时 {time.time() - _t_pref:.1f}s）"
            )

            # 分类诊断：本轮取回多少 .torrent；没拿到时打样本原因
            _raw_ok = sum(1 for _p in fetch_list if getattr(_p[1], "raw", None))
            if _raw_ok < len(fetch_list):
                _sample = fetch_list[0][1]
                self._log(
                    f"魔流 [{task.name}] 种子文件获取 {_raw_ok}/{len(fetch_list)}；"
                    f"示例 enclosure={getattr(_sample, 'enclosure', '')[:90]!r} "
                    f"err={getattr(_sample, 'fetch_error', '')!r}",
                    "warning",
                )

            # ★ IYUU 云端辅种：一次批量查询本轮候选 → 他站同资源 infohash（补齐本地匹配；
            #   只在填了 Token 时启用，否则完全退回内置特征码方案）。
            _iyuu_map: Dict[str, List[str]] = {}
            if task.reuse_existing and self._iyuu_enabled() and fetch_list:
                _cand_hashes = [c.real_hash for _, c in fetch_list if getattr(c, "real_hash", None)]
                if _cand_hashes and self._iyuu_client is not None:
                    try:
                        _iyuu_map = self._iyuu_client.sibling_hashes(_cand_hashes)
                    except Exception as err:  # noqa: BLE001
                        self._log(f"魔流 [{task.name}] IYUU 查询失败：{err}", "warning")
                    if _iyuu_map:
                        self._log(
                            f"魔流 [{task.name}] IYUU 云端命中：{len(_iyuu_map)}/{len(_cand_hashes)} "
                            f"个候选存在他站同资源"
                        )

            _cross_near = 0
            _cross_hit = 0
            _iyuu_hit = 0
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
                    # IYUU 补齐：候选在他站的同资源 infohash 若本机已完成 → 直接复用（免下）
                    if not mode and _iyuu_map and h:
                        for _sib in _iyuu_map.get(str(h).lower(), []):
                            _loc = local_index.get(_sib)
                            if _loc is None:
                                continue
                            if str(getattr(_loc, "state", "") or "").lower() in QB_DOWNLOADING_STATES:
                                continue
                            mode, linfo = "cross", _loc
                            _iyuu_hit += 1
                            break
                if mode and linfo is not None:
                    group_a.append((bonus, cand, mode, linfo))
                elif _in_topn:
                    # 仅 TopN 候选参与「下载」排队；为复用而额外取回的候选不可复用则丢弃。
                    group_b.append((bonus, cand))
            if task.reuse_existing:
                self._log(
                    f"魔流 [{task.name}] 存量复用扫描：复用命中 {len(group_a)} 个"
                    f"（体积邻近比对 {_cross_near} / 特征码命中 {_cross_hit} / IYUU 命中 {_iyuu_hit}，"
                    f"另扫非 TopN {_reuse_extra} 个）"
                )

            # ★ 与洗池同一套排序键：名额受限→边际 value 降序；仅磁盘受限→每 GB 效率 efficiency 降序。
            # （修 bug：原此处用旧的「单种魔力」bonus_per_hour 重排，把洗池的边际排序又覆盖回去了）
            _disk_bound = _disk_left is not None and _count_left is None

            def _rank_key(pair: Any):
                _c = pair[1]
                # 刷流：下载优先序按「上传潜力」——下载人数↓、体积↓、新鲜度↑
                # （与洗池排序一致；此前无分支，刷流被魔力 value/eff 覆盖）。
                if _is_brush_task:
                    return (
                        int(getattr(_c, "leechers", 0) or 0),
                        float(getattr(_c, "size_gb", 0.0) or 0.0),
                        -float(getattr(_c, "age_weeks", 0.0) or 0.0),
                    )
                if _disk_bound:
                    return (getattr(_c, "_eff", 0.0), getattr(_c, "_value", 0.0))
                return (getattr(_c, "_value", 0.0), getattr(_c, "_eff", 0.0))

            # ★ 辅种不参与魔力排名：group_a 保持发现顺序直接加（免下载）
            group_b.sort(key=_rank_key, reverse=True)
            ordered: List[Any] = list(group_a) + list(group_b)
            self._log(
                f"魔流 [{task.name}] Top{len(topn)} 排序：复用 {len(group_a)} / 下载 {len(group_b)}"
            )

            # ---------- ⑤ 处理循环（A 复用优先，其后 B 下载）----------
            self._set_phase(task.id, "process")
            added = 0
            reused = 0
            new_pub: Dict[str, float] = {}
            new_pages: Dict[str, str] = {}  # hash→详情页 URL（供「已非免费→清理」核对）
            new_free: Dict[str, float] = {}  # hash→促销到期时刻(unix)，供「到期即清」
            add_failed = 0
            skipped_dup = 0
            skipped_quota = 0
            skipped_expiring = 0
            skipped_reuse_limit = 0
            skipped_rate = 0
            tagged_reuse = 0
            detail_items: List[OperationItem] = []  # 逐条明细（供操作流水展开）
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
                    if "流控" in _err or "超时" in _err:
                        # 临时限流 / 取种超时：不记 dead（下轮重试），单独计数。
                        skipped_rate += 1
                        self._log(
                            f"跳过·站点流控/取种超时，本轮不处理，下轮重试：{cand.title}",
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
                    # ★ 兜底闸门：确需补下载时，若促销快到期也不补（下不完=白烧流量）。
                    if reuse_downloads and not free_time_ok(cand)[0]:
                        _ok, _need, _remain = free_time_ok(cand)
                        skipped_expiring += 1
                        self._log(
                            f"跳过·免费剩余不足（{int(_remain / 60)}分 < 需 "
                            f"{int(_need / 60)}分）：{cand.title}",
                            "warning",
                        )
                        if self._store and ckey:
                            self._store.dead.mark(task.id, [f"cand:{ckey}"])
                        continue
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
                    _rerr = ""
                    if mode == "hash":
                        ok = downloader.set_torrent_tags(h, [task.brush_tag])
                        st = str(getattr(linfo, "state", "") or "").lower()
                        if st in (QB_PAUSED_STATES | {"error", "missingfiles"}):
                            downloader.resume_torrent(h)
                        if ok:
                            tagged_reuse += 1
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
                            _rerr = str(err)
                            self._log(f"辅种失败：{cand.title}（{err}）", "warning")
                    if not ok:
                        detail_items.append(OperationItem(
                            hash=h or "", title=cand.title,
                            reason=f"辅种失败：{_rerr or '校验不通过/未匹配'}",
                            size_gb=size_gb, source="reuse-fail",
                        ))
                        if self._store and ckey:
                            self._store.dead.mark(task.id, [f"cand:{ckey}"])
                        continue
                    reused += 1
                    add_cnt += 1
                    add_size += size_gb
                    pub_ts = self._pubdate_ts(getattr(cand, "pubdate", None))
                    if pub_ts and h:
                        new_pub[h] = pub_ts
                    if h and getattr(cand, "page_url", ""):
                        new_pages[h] = str(cand.page_url)
                    _fu = float(getattr(cand, "free_remaining_sec", -1.0) or -1.0)
                    if h and _fu >= 0:
                        new_free[h] = time.time() + _fu
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
                    detail_items.append(OperationItem(
                        hash=h or "", title=cand.title,
                        reason="复用·补下载" if reuse_downloads else "复用",
                        size_gb=size_gb, source="reuse",
                        seeders=int(getattr(cand, "seeders", 0) or 0),
                    ))
                    continue

                # B：需下载
                if dl_concurrent >= dl_limit:
                    continue
                if dl_budget <= 0:
                    break
                if over_quota:
                    skipped_quota += 1
                    continue
                # ★ 兜底闸门：限时免费剩的免费时间不够下完 → 不下（洗池阶段拦不到时）。
                _ok_t, _need_t, _remain_t = free_time_ok(cand)
                if not _ok_t:
                    skipped_expiring += 1
                    self._log(
                        f"跳过·免费剩余不足（{int(_remain_t / 60)}分 < 需 "
                        f"{int(_need_t / 60)}分）：{cand.title}",
                        "warning",
                    )
                    if self._store and ckey:
                        self._store.dead.mark(task.id, [f"cand:{ckey}"])
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
                    if nh and getattr(cand, "page_url", ""):
                        new_pages[nh] = str(cand.page_url)
                    _fu2 = float(getattr(cand, "free_remaining_sec", -1.0) or -1.0)
                    if nh and _fu2 >= 0:
                        new_free[nh] = time.time() + _fu2
                    if self._store:
                        keys = [f"hash:{nh}"]
                        if ckey:
                            keys.append(f"cand:{ckey}")
                        self._store.seen.mark(task.id, keys)
                    self._log(f"新增：{cand.title}")
                    detail_items.append(OperationItem(
                        hash=nh, title=cand.title, reason="新增",
                        size_gb=size_gb, source="add",
                        seeders=int(getattr(cand, "seeders", 0) or 0),
                    ))
                else:
                    add_failed += 1
                    if self._store and ckey:
                        self._store.dead.mark(task.id, [f"cand:{ckey}"])
                    self._log(f"添加失败：{cand.title}（{error}）", "warning")
                    detail_items.append(OperationItem(
                        hash=h or "", title=cand.title,
                        reason=f"添加失败：{error or '未知原因'}",
                        size_gb=size_gb, source="add-fail",
                    ))

            if self._store and new_pub:
                self._store.note_pub_dates(task.id, new_pub, tz=SITE_TZ_OFFSET_HOURS)

            if self._store and new_pages:
                self._store.note_torrent_pages(task.id, new_pages)
            if self._store and new_free:
                self._store.note_torrent_free_until(task.id, new_free)

            if reused and self._store:
                self._store.journal.record(
                    task_id=task.id,
                    kind="reuse",
                    items=[OperationItem(hash="", title=f"存量复用 {reused} 个", reason="辅种")],
                )
            if tagged_reuse and self._store:
                try:
                    self._store.journal.record(
                        task_id=task.id,
                        kind="tag",
                        items=[OperationItem(
                            hash="", title=f"复用·补标签 {tagged_reuse} 个",
                            reason=f"→「{task.brush_tag}」", source="reuse",
                            tags=f"→{task.brush_tag}",
                        )],
                    )
                except Exception as _jerr:
                    self._log(f"记录复用标签事件失败：{_jerr}", "warning")

            # 游标推进判定：并发满时，只有本轮复用成功才推进；零复用视为空转不推进。
            if concurrency_full:
                if reused > 0:
                    if self._store:
                        self._store.set_page_cursor(task.id, next_cursor)
                    self._log(
                        f"魔流 [{task.name}] 并发满但本轮复用 {reused} 个，游标 {cursor}→{next_cursor}"
                    )
                else:
                    self._log(
                        f"魔流 [{task.name}] 并发满且本轮无复用产出，判定空转，游标保持 {cursor} 不推进"
                    )
            cursor_note = (
                f"{cursor}→{next_cursor}"
                if (not concurrency_full or reused > 0)
                else f"{cursor}（空转未推进）"
            )

            self._invalidate_summary()
            self._set_phase(task.id, "done")
            detail = (
                f"（复用 {reused} / 新增 {added} / 去重 {skipped_dup}"
                f" / 配额满 {skipped_quota} / 复用限并发 {skipped_reuse_limit} / 流控 {skipped_rate}"
                f" / 免费到期 {skipped_expiring} / 失败 {add_failed}）"
            )
            self._log(
                f"魔流 [{task.name}] 候选 {len(candidates)}→洗池 {len(scored)}→Top{len(topn)} | "
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
                "items": detail_items,
            }

        except Exception as e:
            import traceback
            self._log(f"魔流 [{task.name}] 刷流失败: {e}\n{traceback.format_exc()}", "error")
            self._set_phase(task.id, "error")
            return {"status": "failed", "reason": str(e)}

    def check(self, task_id: str) -> None:
        """执行魔力优化一轮（评估并删除低魔力产出种子）。"""
        self._apply_task_traffic_limit()
        task = self._get_task_config(task_id)
        if task and self._maybe_autostop_for_goal(task):
            return
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
        """执行魔流核心流程（带并发保护）。"""
        task = self._get_task_config(task_id)
        if not task:
            return
        if not self._acquire_worker_slot(f"检查·{task.name}"):
            return
        if not self._try_begin_run(task_id):
            self._release_worker_slot()
            return
        try:
            self._run_check_impl(task)
        finally:
            self._end_run(task_id)
            self._release_worker_slot()

    def _run_check_impl(self, task: MagicFlowTaskConfig) -> None:
        """执行魔流核心流程（内部实现）。"""
        self._last_run_times[task.id] = time.time()
        self._store.record_run_start(task.id)

        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                self._log(f"下载器不可用: {task.downloader}", "error")
                self._store.record_run_error(task.id, "下载器不可用")
                return

            r = self._cleanup_round(task, downloader)
            self._settle(WorkReport(
                task_id=task.id,
                source="check",
                status="done",
                added=0,
                deleted=int(r.get("deleted", 0) or 0),
                kept=int(r.get("kept", 0) or 0),
            ))
            self._invalidate_summary()

        except Exception as e:
            self._log(f"魔流 [{task.name}] 执行失败: {e}", "error")
            self._store.record_run_error(task.id, str(e))

    def _cleanup_round(self, task: MagicFlowTaskConfig, downloader: DownloaderAdapter) -> Dict[str, Any]:
        """清理一轮：自动恢复暂停做种 + 清理无进度种子 + 删除低效种子。

        抽出供两处复用：
          - ``_brush_impl``：放在**入口检查之前**（池满时先清理腾空间，再决定抓取）；
          - ``_run_check_impl``：独立的 check 任务。

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

        # 把「保护 / 同站纳管」记录与下载器真实种子对齐：已从下载器消失的种子会留下陈旧
        # hash（历史误删 / 手动删除），导致「受保护」计数虚高、同一资源不再被重新纳管。
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

        # 拉一次标签内全部种子（任意状态）：用于「自动恢复暂停」+「清理无进度」
        try:
            all_tagged, _tag_err = downloader.get_torrents(tags=[task.brush_tag])
        except Exception as _tag_exc:
            all_tagged, _tag_err = [], str(_tag_exc)

        # ★ 媒体资产价值闸门：把「已整理 / 辅种 / 下载历史命中」的种子并入保护集合，
        #   本轮所有清理（无进度 / 过慢 / 非免费 / 无上传 / 到期 / 低效）都跳过它们。
        try:
            _asset_hashes = self._media_asset_hashes(list(all_tagged or []), task)
            if _asset_hashes:
                protected = set(protected) | set(_asset_hashes)
                self._dbg(
                    f"[{task.name}] 媒体资产保护 {len(_asset_hashes)} 个"
                    f"（标签 {'/'.join(MEDIA_ASSET_TAGS)} 或命中下载历史）"
                )
        except Exception as _asset_err:
            self._log(f"魔流 [{task.name}] 媒体资产保护计算失败: {_asset_err}", "warning")

        # 看门狗：与上一轮对比，检测「种子还在、标签却被抹掉」（托管骤降但本轮无删种）
        if not _tag_err:
            try:
                self._watch_tag_integrity(task, len(all_tagged or []))
            except Exception as _wd_err:
                self._log(f"魔流 [{task.name}] 标签看门狗异常: {_wd_err}", "warning")

        # ① 自动恢复被暂停的已完成种子（暂停 → tracker 不计做种 → 0 产出）
        if getattr(task, "auto_resume_paused", True) and all_tagged:
            try:
                out["resumed"] = self._resume_paused_managed(task, downloader, list(all_tagged))
            except Exception as _resume_err:
                self._log(f"魔流 [{task.name}] 自动恢复暂停种子异常: {_resume_err}", "warning")

        # ② 清理「没进度」的种子（进度为 0 且停滞/出错/暂停，挂了够久）
        if all_tagged:
            try:
                np_deleted, _np_removed = self._cleanup_no_progress(
                    task, downloader, list(all_tagged), protected
                )
                out["no_progress"] = np_deleted
            except Exception as _cleanup_err:
                self._log(f"魔流 [{task.name}] 清理无进度种子异常: {_cleanup_err}", "warning")

        # ②b 清理「下载过慢」的种子（用「下载速度 ÷ 体积」估算 ETA，长期下不完的腾名额）
        #     刷流模式不做：刷流只要「有上传」就保留，哪怕下得慢（没完整下完也会有上传）。
        if all_tagged and not _is_brush:
            try:
                slow_deleted, _slow_removed = self._cleanup_slow_progress(
                    task, downloader, list(all_tagged), protected
                )
                out["slow"] = slow_deleted
            except Exception as _slow_err:
                self._log(f"魔流 [{task.name}] 清理过慢种子异常: {_slow_err}", "warning")

        # ②c 清理「促销失效」的种子（下载中但站点已不再免费 → 删，避免白拉流量）
        if all_tagged and getattr(task, "purge_unfree_incomplete", True):
            try:
                out["unfree"] = self._cleanup_unfree_incomplete(
                    task, downloader, list(all_tagged), protected
                )
            except Exception as _unfree_err:
                self._log(f"魔流 [{task.name}] 清理「已非免费」种子异常: {_unfree_err}", "warning")

        # ②d 刷流模式：清理到期/无上传的托管种
        #    设计：**下载中**的种过了宽限期后，每次 check（每 check_interval 分钟）都按上传速率
        #    考核，连续 need 次「无上传」即杀（它们要一直上传才能活过整个下载周期）；
        #    **已下完**的种走「满 brush_seed_days 天」轮换（挂种 N 天换新）。
        #    brush_seed_days=0 时回退：不分状态，统一按「无上传」判定。
        if _is_brush:
            _seed_days = int(getattr(task, "brush_seed_days", 0) or 0)
            if all_tagged:
                try:
                    # ★ 产出换种优先：单种已上传/分享率达标 → 换新（先于时间/无上传判定）
                    out["rotated"] = self._cleanup_rotated(
                        task, downloader, list(all_tagged), protected
                    )
                    # 本轮流转掉的（已达产出阈值）不再参与时间/无上传判定，避免重复处理
                    _still = [t for t in all_tagged if not self._rotate_reason(task, t)]
                    if _seed_days > 0:
                        # 下载中：上传考核（每 check 一次，无上传即杀）
                        _incomplete = [
                            t for t in _still
                            if float(getattr(t, "progress", 0) or 0) < 0.999
                        ]
                        # 已下完：满 N 天轮换
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
                        # 未设天数：不分状态统一按「无上传」判定
                        out["no_upload"] = self._cleanup_no_upload(
                            task, downloader, _still, protected
                        )
                except Exception as _nu_err:
                    self._log(f"魔流 [{task.name}] 刷流清理异常: {_nu_err}", "warning")
            # 刷流模式不套用魔力门槛删种；直接收尾返回。
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
                f"魔流 [{task.name}] 刷流完成："
                f"恢复 {out['resumed']} / 无进度 {out['no_progress']} / 到期 {_aged} / 产出 {_rot} / 无上传 {_noupl}；"
                f"保留 {out['kept']} 个"
            )
            return out

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
                # 已删种子从「保护 / 同站纳管」集合中清理，避免陈旧 hash 虚高计数
                self._store.forget_torrents(task.id, delete_hashes[: max(0, int(success_count or 0))])

        out["low_eff"] = deleted_count
        out["deleted"] = int(out["no_progress"]) + int(out["slow"]) + deleted_count
        out["kept"] = len(result.to_keep)
        # ★ 站点口径合计时魔（对合计 A 只取一次 arctan + 做种固定奖励），使数值与站点上报对齐。
        # 原来把每颗种子各自的时魔简单相加 → 漏掉「做种数 × 每种子」固定奖励，只有站点值的 ~1/3。
        # 「做种固定奖励」按**站点账号去重后的做种数**计（非本任务托管数），否则会比站点整号值偏低。
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
            self._log(f"魔流 [{task.name}] 站点口径时魔汇总失败，回落逐种相加：{_agg_err}", "warning")
            out["total_before"] = result.total_bonus_before
            out["total_after"] = result.total_bonus_after
        self._log(
            f"魔流 [{task.name}] 完成："
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
            try:
                bonus_info.ratio = float(getattr(t, "ratio", 0) or 0)
            except (TypeError, ValueError):
                bonus_info.ratio = 0.0
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
        # 未命中/已过期：不阻塞当前请求——后台单飞抓取，本次先返回旧值（可能为 None）。
        # 这样 /status、总览等永远不会因站点 mybonus.php 卡顿/超时而拖慢。
        self._schedule_formula_fetch(task, domain, cache)
        return cached.get("cap") if cached else None

    def _schedule_formula_fetch(self, task: MagicFlowTaskConfig, domain: str, cache: Dict[str, Any]) -> None:
        """后台抓取站点公式（每域名单飞，避免并发重复请求；不阻塞调用方）。"""
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
                site = self._get_site(task.site_id) if getattr(task, "site_id", 0) else None
                if site is None:
                    self._log(f"站点公式：未找到站点 {getattr(task, 'site_id', 0)}，本轮跳过", "warning")
                    return
                try:
                    cap = fetch_site_formula(site, timeout=15)
                except Exception as err:
                    self._log(f"站点公式抓取失败 [{domain}]: {err}", "warning")
                    cap = None
                ts = time.time()
                if cap and cap.ok:
                    try:
                        refresh_site_preset(site)
                        self._log(f"站点公式已获取 [{domain}] {cap.note} params={cap.params} extra={cap.extra}")
                    except Exception:
                        pass
                    cache[domain] = {"ts": ts, "cap": cap}
                else:
                    cache[domain] = {"ts": ts - SITE_FORMULA_TTL + SITE_FORMULA_RETRY, "cap": cap}
                # 公式就绪后让统计/总览失算失效；保留旧 heavy 供下次请求秒回并后台刷新。
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
            seeding_count = self._site_seeding_count(task.site_id) or len(torrent_list or [])
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

    def _site_seeding_count(self, site_id: int) -> int:
        """站点账号「去重后」的做种数（站点「0.5×做种数」固定奖励用的就是这个口径）。

        注意：部分站点（如 Pttime）userdata 的 ``seeding`` 会含重复条目，而站点计算
        「做种固定奖励」时按去重后的做种数计（实测 Pttime seeding=32、去重后=23，站点
        B 恰按 23 算）。故以 ``seeding_info`` 去重为准，取不到时回落 ``seeding`` 字段，
        再取不到返回 0（调用方回落到本任务托管数）。
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

    def _site_user_stats(self, site_id: int) -> Dict[str, Any]:
        """站点账号「真实数据」（来自 MoviePilot 站点用户数据）——上传/下载/分享率/做种/下载数/魔力。

        字节量（upload/download/seeding_size/leeching_size）与积分（bonus）原样返回，
        另带数据更新时间，供前端展示「站点侧真实情况」（区别于下载器本地统计）。
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
        # 部分站点（如 PTT）不在用户数据里写分享率，用上传/下载兜底算一个。
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
        """读取指定站点当前魔力值（用于自动保护阈值）。"""
        row = self._userdata_row(site_id)
        if row is None:
            return 0.0
        try:
            return float(self._ud_get(row, "bonus", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    # ---------------------------------------------------------
    # 任务目标（达到后自动停止任务）
    # ---------------------------------------------------------

    def _task_goal_status(self, task: MagicFlowTaskConfig) -> Dict[str, Any]:
        """任务目标完成情况（用于展示与自动停止判定）。

        目标口径随任务类型：
          - bonus：站点魔力值（SiteUserData.bonus）达到 ``goal_value``；
          - brush：站点上传量（SiteUserData.upload，字节）达到 ``goal_value`` GB。
        返回以 ``goal_`` 前缀的字段，避免与任务其它字段冲突。
        """
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
            return out
        out["goal_has"] = True
        out["goal_target"] = tgt
        stats = self._site_user_stats(task.site_id) or {}
        if is_brush:
            cur = float(stats.get("upload") or 0.0) / (1024 ** 3)   # 字节 → GB
        else:
            cur = float(stats.get("bonus") or 0.0)
        out["goal_current"] = cur
        out["goal_reached"] = bool(stats.get("ok")) and cur >= tgt - 1e-9
        return out

    def _maybe_autostop_for_goal(self, task: MagicFlowTaskConfig) -> bool:
        """任务达到目标则自动停用（仅停调度：不搬种、不撤种、不删种）。返回是否因此停用。"""
        if not getattr(task, "enabled", False):
            return False
        st = self._task_goal_status(task)
        if not (st.get("goal_has") and st.get("goal_reached")):
            return False
        task.run_mode = "stopped"
        task.enabled = False
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary()
        self._apply_task_traffic_limit()
        self._log(
            f"魔流 [{task.name}] 已达任务目标（{st['goal_current']:.4g}/{st['goal_target']:.4g} "
            f"{st['goal_unit']}）→ 自动停止任务"
        )
        # 异步暂停全部托管种（保文件、可逆），避免达标后继续非免费下载
        self._spawn_run_mode_apply(task, "stopped")
        if self._store:
            try:
                self._store.journal.record(
                    task_id=task.id,
                    kind="goal",
                    items=[OperationItem(
                        hash="",
                        title="已达目标，自动停止",
                        reason=f"{st['goal_current']:.4g}/{st['goal_target']:.4g} {st['goal_unit']}",
                    )],
                )
            except Exception as err:
                self._log(f"记录达标停止失败：{err}", "warning")
        return True

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
            min_ratio=float(getattr(task, "min_ratio", 0) or 0),
            weight_time_factor=1.0,
            weight_people_factor=1.0,
            weight_size=0.5,
            weight_zero_penalty=2.0,
            prefer_delete_zero_bonus=True,
            prefer_delete_high_ratio=False,
            prefer_delete_large=False,
            protect_perfect=bool(getattr(task, "protect_perfect", True)),
            perfect_max_seeders=int(getattr(task, "perfect_max_seeders", 3) or 0),
            perfect_min_weeks=float(getattr(task, "perfect_min_weeks", 4.0) or 0.0),
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
        manual_paused = self._store.get_manual_paused(task.id) if self._store else set()
        for t in managed or []:
            state = str(getattr(t, "state", "") or "").lower()
            if state not in QB_PAUSED_STATES:
                continue
            h = getattr(t, "hash", "") or ""
            # 用户手动暂停的种子不自动恢复（尊重人工干预，需界面上点「恢复做种」）
            if h and (h or "").lower() in manual_paused:
                skipped += 1
                continue
            if float(getattr(t, "progress", 0) or 0) < 0.999:
                skipped += 1
                continue
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
                f"魔流 [{task.name}] 自动恢复暂停种子：恢复 {resumed} 个"
                f"（跳过未完成 {skipped} 个）"
            )
        return resumed

    def _brush_idle_params(self, task: MagicFlowTaskConfig) -> Tuple[int, float, float]:
        """刷流「无上传」判定参数 → (需连续低于门槛的次数 need, 单次检查上传字节门槛 thr, 宽限秒 grace)。

        门槛按「平均上传速率」折算：``thr = upload_min_kbps × 1024 × 检查间隔秒``。
        每次检查比对 uploaded 增量，增量 < thr（即平均速率低于门槛）即累加一次「冷」。
        """
        ci = max(int(getattr(task, "check_interval", 1) or 1), 1) * 60
        grace = max(int(getattr(task, "brush_grace_minutes", 15) or 0), 0) * 60
        idle_min = int(getattr(task, "upload_idle_minutes", 10) or 0)
        if idle_min <= 0:
            idle_min = max((2 * ci) // 60, 1)  # 自动：约 2×检查间隔
        need = max(int(round(idle_min * 60 / ci)), 1)
        kbps = float(getattr(task, "upload_min_kbps", 200) or 0)
        thr = kbps * 1024 * ci
        return need, thr, grace

    def _cleanup_no_upload(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> int:
        """刷流模式：清理「无上传」的种子，返回删除数。

        每次检查比对 uploaded 增量：连续 ``need`` 次平均上传速率 < ``upload_min_kbps`` → 判定「无上传」→ 删。
        * 新种在 ``brush_grace_minutes`` 宽限期内不判（给起步时间）；
        * 「没完整下完也会有上传」：只看上传，不管进度/速度；
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
                        reason="刷流：无上传",
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
                f"（连续 {need} 次检查平均上传 < {_kbps} KB/s）"
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
        """刷流模式：已下完的种子按做种时长满 ``brush_seed_days`` 天清理（轮换腾位），返回删除数。

        * **只处理已下完的种**（progress>=0.999）；未下完的交给「无上传」判定（_cleanup_no_upload）。
        * 完成种按**做种时长**（qB seeding_time）计；拿不到时用「加入下载器时长」兜底。
        * protected / 手动保留的种子只记录快照、永不删。
        保种期内（< 天数）一律保留，不按上传速率判。
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
                        reason=f"刷流：做种满 {days} 天",
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
        """单种是否达到「产出换种」阈值（返回理由，未达标返回 None）。"""
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
            return f"刷流：单种上传达标 {uploaded / (1024 ** 3):.1f} GB"
        if ratio_thr > 0 and ratio >= ratio_thr:
            return f"刷流：分享率达标 {ratio:.2f}"
        return None

    def _cleanup_rotated(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> int:
        """刷流模式：按「产出」换种 —— 单种已上传 ≥ ``rotate_upload_gb`` GB 或 分享率 ≥ ``rotate_ratio`` → 清理换新。

        * 只作用于纯刷流临时种；protected / 资产闸门命中的种子永不删。
        * 两个阈值都留空时不做任何事（返回 0）。
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
                    reason=reasons.get((t.hash or "").lower(), "刷流：产出换新"),
                    bonus_per_hour=0.0,
                )
                for t in to_delete[:deleted]
            ]
            self._store.journal.record(task_id=task.id, kind="deletion", items=items)
            self._store.forget_torrents(task.id, [t.hash for t in to_delete[:deleted]])
        _sample = next(iter(reasons.values()), "")
        self._log(
            f"魔流 [{task.name}] 刷流清理「产出达标换新」种子 {deleted} 个"
            + (f"（如：{_sample}）" if _sample else "")
        )
        return deleted

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
                self._log(f"魔流 [{task.name}] 清理无进度种子失败：{err}", "warning")
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
            self._store.forget_torrents(task.id, [t.hash for t in removed])
        self._log(
            f"魔流 [{task.name}] 清理无进度种子 {deleted} 个"
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
                self._log(f"魔流 [{task.name}] 清理过慢种子失败：{err}", "warning")
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
            self._store.forget_torrents(task.id, [t.hash for t in removed])
        self._log(
            f"魔流 [{task.name}] 清理下载过慢种子 {deleted} 个"
            f"（速度÷体积估算 > {float(getattr(task, 'slow_progress_max_hours', 48.0) or 48.0):g}h 才下完）"
        )
        return deleted, removed

    def _seen_page_pairs(self, task_id: str) -> Dict[str, str]:
        """从 seen 记录重建 hash→详情页 URL。

        插件写入 seen 时会把 ``hash:<h>`` 与 ``cand:<url>`` 用**同一时间戳**批量写入，
        故可按时间戳配对得到历史种子的详情页链接（老数据无 torrent_pages 时的回摆）。
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

    _PROMO_TTL = 600  # 促销状态内存缓存（秒），避免每轮检查都回站点逐个抗详情页
    _TITLE_URL_TTL = 600  # 「我的种子」列表回填 URL 的缓存时长（秒）

    def _title_url_map(self, task: MagicFlowTaskConfig, site: Any) -> Dict[str, str]:
        """站点「我的种子」列表（下载中+做种）→ {规范化标题: 详情页URL}（带缓存）。"""
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
        """回站点抗取种子当前促销状态（带内存缓存）。"""
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

    def _cleanup_unfree_incomplete(
        self,
        task: MagicFlowTaskConfig,
        downloader: DownloaderAdapter,
        managed: List[TorrentInfo],
        protected_hashes: Optional[Set[str]] = None,
    ) -> int:
        """清理「已不再免费且尚未下完」的种子，返回删除数。

        逐个回站点详情页核对「下载中」种子的当前促销：已非全免（促销过期 / 本来非免费）
        → 删除，避免白拉流量拉低分享率。「unknown」（拿不到页面/无法解析）时**保守跳过**，不误删。
        """
        if not getattr(task, "purge_unfree_incomplete", True) or not managed or not downloader:
            return 0
        protected_hashes = protected_hashes or set()
        site = self._get_site(task.site_id) if getattr(task, "site_id", 0) else None
        pages = dict(self._store.get_torrent_pages(task.id) if self._store else {})
        if self._store:
            for h, u in self._seen_page_pairs(task.id).items():
                pages.setdefault(h, u)
        mode = (getattr(task, "freeleech", "") or "").strip().lower()
        acceptable = {"2xfree"} if mode == "2xfree" else {"free", "2xfree"}

        # 兜底：缺失详情页链接的「下载中」种子 → 用站点「我的种子」列表按标题回填 URL
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
            # 只处理「还没下完」的种子（已完成/做种中的交给魔力规则管）
            if float(getattr(t, "progress", 0) or 0) >= 0.999:
                continue
            if self._is_dead_cached(task.id, h):
                continue
            # ★ 优先用入种时记下的「促销到期时刻」：到点直接清（免回详情页）；未到期则确认仍有效 → 也不必回详情页。
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
                    f"魔流 [{task.name}] 促销核对失败（跳过）：{t.title}"
                    f"（{info.get('error') or '无标题区'}）",
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
                self._log(f"魔流 [{task.name}] 清理「已非免费」种子失败：{err}", "warning")
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
                        reason=f"已非免费（促销={promo}）且未下完", bonus_per_hour=0.0,
                    )
                    for t, promo in removed
                ],
            )
            self._store.forget_torrents(task.id, [t.hash for t, _ in removed])
        self._log(
            f"魔流 [{task.name}] 清理「已非免费」未下完种子 {deleted} 个："
            + "、".join(f"{t.title[:24]}({promo})" for t, promo in removed[:6])
            + ("…" if len(removed) > 6 else "")
            + (f"（其中按期记录到期 {recorded_hits} 个）" if recorded_hits else "")
        )
        return deleted

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
        _is_brush = str(getattr(task, "task_type", "bonus") or "bonus").strip().lower() == "brush"
        # 刷流有自己的选种标准（不看魔力口径）：不设人数上限、体积/年龄不限、不排除零魔、
        # 只要求「有下载需求」（下载人数 ≥ min_leechers）。
        policy = get_default_brush_filter_policy() if _is_brush else get_default_filter_policy()

        if _is_brush:
            try:
                policy.min_leechers = max(int(getattr(task, "brush_min_leechers", 1) or 0), 0)
            except (TypeError, ValueError):
                policy.min_leechers = 1

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

        # 发布时间范围（分钟）：单值或「最小-最大」
        if getattr(task, "pubtime", ""):
            try:
                parts = str(task.pubtime).split("-")
                if len(parts) == 1:
                    policy.pub_minutes_max = float(parts[0])
                elif len(parts) == 2:
                    policy.pub_minutes_min = float(parts[0])
                    policy.pub_minutes_max = float(parts[1])
            except Exception:
                pass

        policy.include_pattern = task.include
        policy.exclude_pattern = task.exclude
        policy.exclude_zero_bonus = task.exclude_zero_bonus
        # 「免费」选项真正生效（历史上只存了任务字段、没接进筛选 → 照下非免费）
        mode = (task.freeleech or "").strip().lower()
        if mode == "2xfree":
            policy.double_free_only = True
        elif mode == "free":
            policy.free_only = True
        # 「排除 H&R」选项（hr=yes → 过滤掉 H&R 种子）
        if str(getattr(task, "hr", "") or "").strip().lower() in ("yes", "y", "1", "true", "是"):
            policy.exclude_hnr = True
        return policy

    # ---------------------------------------------------------
    # 任务数据构建
    # ---------------------------------------------------------

    def _task_runtime_stats(self, task: MagicFlowTaskConfig, force: bool = False) -> Dict[str, Any]:
        """计算单个任务的实时托管种子数与魔力产出。

        带 STATS_TTL 短缓存：同一轮 /status 内「总览」与「任务列表」各算一次，
        缓存后只查一次下载器（去重），并让前端轮询/二次进入更快。
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
            # 站点账号真实数据（上传/下载/分享率/做种/下载数）
            stats["site_user"] = rep.get("user") or {}
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
            managed = list(self._tag_snapshot(task.downloader).get(task.brush_tag, []))
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
            # 本任务在下载器的累计上传量 / 有上传的种子数（刷流视角）
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
        cache[task.id] = {"ts": time.time(), "data": stats}
        return stats

    def _runtime_stats_bulk(self, tasks: List[MagicFlowTaskConfig]) -> Dict[str, Dict[str, Any]]:
        """并发计算多任务实时统计（线程池）；异常时回退串行。

        * 并发仅跨「不同任务」；单任务内部仍串行；
        * 命中 STATS_TTL 缓存的任务不会重复查询下载器；
        * 站点公式先在主线程预热（6h 缓存；冷启动只串行抓一次，避免并发重复请求站点页）。
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
            self._log(f"并发统计失败，回退串行：{err}", "warning")
            for task in tasks:
                result[task.id] = self._task_runtime_stats(task)
        return result

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
        return {
            **task.to_dict(),
            **store_stats,
            **self._phase_info(task_id),
            **self._task_goal_status(task),
        }

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
        site_upload = 0.0
        site_download = 0.0

        # 站点上报魔力按「站点」去重（同一站点多任务不重复计）
        site_tasks: Dict[int, MagicFlowTaskConfig] = {}
        # 预热「全部任务」统计（含未启用）：任务列表随后直接命中缓存，避免串行补算。
        all_tasks = list(self._task_configs.values())
        stats_by_id = self._runtime_stats_bulk(all_tasks)
        for task in all_tasks:
            if not task.enabled:
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
        """构建任务列表（含实时统计）。"""
        tasks: List[Dict[str, Any]] = []
        stats_by_id = self._runtime_stats_bulk(list(self._task_configs.values()))
        for task in self._task_configs.values():
            runtime = stats_by_id.get(task.id, {})
            tasks.append({
                **task.to_dict(),
                **runtime,
                **self._phase_info(task.id),
                **self._task_goal_status(task),
            })
        return tasks

    # ---------------------------------------------------------
    # API：全局
    # ---------------------------------------------------------

    def _build_status_heavy(self) -> Dict[str, Any]:
        """构建总览的重数据（统计 + 任务列表 + 选项）。"""
        summary = self._compute_summary()
        self._log(
            f"API 总览：任务 {summary.get('total_tasks')} 启用 {summary.get('enabled_tasks')} "
            f"托管 {summary.get('seeding_count')} 魔力 {summary.get('bonus_per_hour')}/h"
        )
        return {
            "summary": summary,
            "tasks": self._build_task_list(),
            "options": self._cached_options(),
        }

    def _light_status(self) -> Dict[str, Any]:
        """轻量壳：冷启动首屏用。任务配置/阶段/目标都算（本地快），**不算下载器实时统计**。

        供后台构建重数据期间先返回，避免首屏卡 2~3s；前端见到 warming 会快速重拉。
        """
        try:
            total = len(self._task_configs)
            enabled = sum(1 for t in self._task_configs.values() if t.enabled)
            tasks = []
            for task in self._task_configs.values():
                try:
                    tasks.append({
                        **task.to_dict(),
                        **self._phase_info(task.id),
                        **self._task_goal_status(task),
                    })
                except Exception:
                    tasks.append(task.to_dict())
        except Exception as err:
            self._log(f"构建轻量总览失败：{err}", "warning")
            total, enabled, tasks = 0, 0, []
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
        """后台异步刷新总览重数据（stale-while-revalidate，不阻塞请求）。"""
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
                self._log(f"后台刷新总览失败：{err}", "warning")
            finally:
                self._status_refreshing = False

        try:
            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            pass

    def get_status(self) -> Response:
        """获取插件总览状态（重数据带 STATUS_TTL 缓存 + 后台静默刷新）。

        冷启动不再同步阻塞：首次调用立即返回**轻量壳**（配置/阶段/目标，不算下载器
        实时统计）并后台构建重数据，前端见 `warming=true` 会快速重拉；后台连续失败
        时才同步兜底（正确性优先）。
        """
        now = time.time()
        heavy = getattr(self, "_status_heavy", None)
        warming = False
        if heavy is None:
            if int(getattr(self, "_status_warm_fails", 0) or 0) >= 2:
                # 后台反复失败：同步兜底，保证拿到真实数据
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
            "iyuu_token": str(getattr(self, "_iyuu_token", "") or ""),
            "iyuu_sites": dict(getattr(self, "_iyuu_sites", {}) or {}),
            "recommend": dict(getattr(self, "_recommend_cfg", {}) or {}),
            "defaults": dict(getattr(self, "_defaults", {}) or {}),
        })
        return Response(success=True, data=data)

    def debug_recognize(self, name: str = "") -> Response:
        """诊断：识别一个种子名并返回评分/榜单/订阅命中 + 是否已在影视库（只读）。"""
        try:
            info = self._get_recommend_engine().evaluate(name or "")
            try:
                info["in_library"] = self._recommend_in_library(info)
                info["media_key"] = self._recommend_media_key(
                    {"source": info.get("media_source"), "id": info.get("media_id")}, info
                )
            except Exception:  # noqa: BLE001
                pass
            return Response(success=True, data=info)
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=str(e))

    def debug_recommend_run(self, task_id: str = "") -> Response:
        """诊断：立即对一个任务跑一轮推荐甄别（不指定则 round-robin 一个）。"""
        try:
            if task_id:
                task = self._get_task_config(task_id)
                if not task:
                    return Response(success=False, message="任务不存在")
                self._recommend_scan_task(task)
            else:
                self.recommend_scan()
            store = getattr(self._store, "recommend", None)
            items = store.list() if store else []
            return Response(success=True, data={"total": len(items), "items": items})
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=str(e))

    def debug_qb_torrents(self, downloader: str = "qbittorrent") -> Response:
        """诊断：列出指定下载器的全部种子并按标签分组（只读）。"""
        try:
            dl = self._get_downloader(downloader or "qbittorrent")
            if not dl or not dl.is_available:
                return Response(success=False, message=f"下载器不可用: {downloader}")
            torrents, error = dl.get_torrents()
            if error:
                return Response(success=False, message=str(error))
            from collections import Counter
            tag_count: Counter = Counter()
            by_tag: Dict[str, List[Dict[str, Any]]] = {}
            rows: List[Dict[str, Any]] = []
            for t in (torrents or []):
                tags = getattr(t, "tags", None) or []
                if isinstance(tags, str):
                    tags = [x.strip() for x in tags.split(",") if x.strip()]
                tags = list(tags)
                state = str(getattr(t, "state", "") or "")
                item = {
                    "hash": getattr(t, "hash", ""),
                    "name": getattr(t, "title", ""),
                    "tags": tags,
                    "state": state,
                    "size_gb": round(float(getattr(t, "size_gb", 0) or 0), 2),
                    "progress": round(float(getattr(t, "progress", 0) or 0), 3),
                }
                rows.append(item)
                for tg in (tags or ["<无标签>"]):
                    tag_count[tg] += 1
                    by_tag.setdefault(tg, []).append(item)
            return Response(success=True, data={
                "total": len(rows),
                "tag_counts": dict(tag_count.most_common()),
                "by_tag": by_tag,
            })
        except Exception as err:
            return Response(success=False, message=str(err))

    @staticmethod
    def _url_host(value: str) -> str:
        """从未必带 scheme 的地址中取出主机名（小写）。"""
        try:
            from urllib.parse import urlsplit
            raw = value if "://" in value else f"https://{value}"
            return (urlsplit(raw).hostname or "").lower()
        except Exception:  # noqa: BLE001
            return ""

    def _url_allowed_for_site(self, url: str, site: Any) -> bool:
        """仅允许抓取该站点自身域名下的地址（防 cookie 外带 / SSRF）。"""
        try:
            from urllib.parse import urlsplit
        except Exception:  # noqa: BLE001
            return False
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        site_hosts = set()
        for cand in (getattr(site, "url", "") or "", getattr(site, "domain", "") or ""):
            h = self._url_host(cand)
            if h:
                site_hosts.add(h)
        for sh in site_hosts:
            if host == sh or host.endswith("." + sh) or sh.endswith("." + host):
                return True
        return False

    def debug_fetch_page(self, site_id: int = 0, url: str = "", limit: int = 8000) -> Response:
        """诊断：用站点 cookie 抓取**该站点域名下**的页面，返回文本片段（只读）。

        安全：必须指定 ``site_id``，且请求地址必须属于该站点域名，防止
        cookie 被带到外站（cookie 外带 / SSRF）。
        """
        if not url:
            return Response(success=False, message="缺少 url")
        if not site_id:
            return Response(success=False, message="必须指定 site_id（仅允许抓取该站点域名）")
        site = self._get_site(int(site_id))
        if not site:
            return Response(success=False, message="站点不存在")
        if not self._url_allowed_for_site(url, site):
            return Response(success=False, message="仅允许抓取该站点域名下的页面")
        try:
            from app.sdk.network import RequestUtils  # noqa: WPS433
        except Exception as err:
            return Response(success=False, message=f"SDK 不可用: {err}")
        cookie = getattr(site, "cookie", None)
        ua = getattr(site, "ua", None)
        base = (getattr(site, "url", "") or (f"https://{getattr(site, 'domain', '')}")).rstrip("/")
        referer = f"{base}/"
        try:
            req = RequestUtils(cookies=cookie, ua=ua, timeout=30, referer=referer)
            resp = req.get_res(url)
        except Exception as err:
            return Response(success=False, message=f"请求失败: {err}")
        if resp is None:
            return Response(success=False, message="无响应")
        status = getattr(resp, "status_code", 0)
        try:
            raw = resp.content
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", "ignore")
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return Response(success=True, data={
            "url": url, "status": status, "length": len(text),
            "text": text[: max(0, int(limit))],
        })

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
        # IYUU 云端辅种配置
        self._iyuu_token = str(getattr(payload, "iyuu_token", "") or "").strip()
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
        # 刷流种甄别与推荐（价值生命周期）
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
        self._save_config()
        self._apply_runtime_settings()
        self._refresh_scheduler()
        self._apply_task_traffic_limit(force=True)
        self._dbg(
            f"全局设置已更新：enabled={self._enabled} sidebar={self._show_sidebar_nav} "
            f"debug={self._debug_log} compact={self._compact_mode} "
            f"journal_keep={self._journal_keep} req_interval={self._request_interval}"
        )
        return Response(success=True, message="设置已保存", data=self._current_config())

    # ---------------------------------------------------------
    # API：下载器全局参数（qBittorrent 应用级偏好）
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_run_mode(mode: Any, enabled: Any = None) -> str:
        """规整运行状态：running / seeding / stopped。

        - 传了合法 mode → 直接用；
        - 否则按 enabled 回退（True→running / False→stopped）。
        """
        m = str(mode or "").strip().lower()
        if m in ("running", "seeding", "stopped"):
            return m
        return "running" if bool(enabled) else "stopped"

    @staticmethod
    def _kbps_to_bps(kbps: Any) -> int:
        """KB/s → 字节/秒（qbittorrentapi 用字节/秒）。负数/非法值规整为 0。"""
        try:
            v = float(kbps or 0)
        except (TypeError, ValueError):
            v = 0.0
        return max(0, int(round(v * 1024)))

    @staticmethod
    def _bps_to_kbps(bps: Any) -> float:
        """字节/秒 → KB/s（保留 1 位小数）。"""
        try:
            v = float(bps or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v <= 0:
            return 0.0
        return round(v / 1024.0, 1)

    def get_downloader_prefs(self) -> Response:
        """读取下载器（qBittorrent）全局参数 + 推荐值。"""
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
        """写入下载器（qBittorrent）全局参数。"""
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
            f"下载器全局参数已更新：下载限速={payload.download_limit_kbps}KB/s "
            f"上传限速={payload.upload_limit_kbps}KB/s 连接={payload.max_connec}/"
            f"{payload.max_connec_per_torrent} 上传连接={payload.max_uploads}/"
            f"{payload.max_uploads_per_torrent} 活动下载/种子={payload.max_active_downloads}/"
            f"{payload.max_active_torrents} 队列={payload.queueing_enabled}"
        )
        return Response(success=True, message="下载器参数已保存", data=self.get_downloader_prefs().data)

    def update_downloader_paths(self, payload: MagicFlowDownloaderPathsPayload) -> Response:
        """写入下载器（qBittorrent）全局路径。"""
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
            f"下载器目录已更新：保存路径={target['save_path'] or '(空)'} "
            f"临时路径={target['temp_path'] or '(空)'} 启用临时={target['temp_path_enabled']}"
        )
        return Response(success=True, message="下载目录已保存", data=self.get_downloader_prefs().data)

    # ---------------------------------------------------------
    # API：默认任务模板 + 维护
    # ---------------------------------------------------------

    def get_defaults(self) -> Response:
        """读取「默认任务模板」。"""
        data = MagicFlowDefaultsPayload(**(getattr(self, "_defaults", {}) or {})).model_dump()
        return Response(success=True, data=data)

    def update_defaults(self, payload: MagicFlowDefaultsPayload) -> Response:
        """保存「默认任务模板」（仅用于新建任务时预填，不影响已存在任务）。"""
        self._defaults = payload.model_dump()
        self.save_data(key="defaults", value=dict(self._defaults))
        self._save_config()
        return Response(success=True, message="默认任务模板已保存", data=dict(self._defaults))

    # ---------------------------------------------------------
    # API：IYUU 云端辅种（可选）
    # ---------------------------------------------------------

    def _iyuu_enabled(self) -> bool:
        """IYUU 云端辅种是否启用（填了 Token 才算）。"""
        return bool(self._iyuu_client is not None and self._iyuu_client.enabled)

    def _build_iyuu_client(self, token: str) -> IyuuCloud:
        """构造 IYUU 云端客户端，并挂上「站点表 / sid_sha1」磁盘缓存（避免热重载后重复撞限流）。"""
        return IyuuCloud(
            token,
            logger=self._log,
            cache_loader=lambda: self.get_data("iyuu_cache"),
            cache_saver=lambda cache: self.save_data(key="iyuu_cache", value=cache),
        )

    def get_iyuu_sites(self) -> Response:
        """列出 MoviePilot 已配置站点（供「IYUU 密钥表」）+ 当前 IYUU 设置。"""
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
            self._log(f"列出已配置站点失败：{err}", "warning")
        return Response(success=True, data={
            "token_set": bool(self._iyuu_token),
            "token": self._iyuu_token,
            "enabled": self._iyuu_enabled(),
            "sites": sorted(rows, key=lambda r: str(r.get("name") or "")),
        })

    def test_iyuu(self) -> Response:
        """测试已保存的 IYUU Token（拉一次账号信息）。"""
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

    def create_task(self, payload: MagicFlowTaskPayload) -> Response:
        """创建魔流任务。"""
        task_id = payload.id or uuid.uuid4().hex[:12]
        if task_id in self._task_configs:
            return Response(success=False, message="任务 ID 已存在")

        site = self._get_site(payload.site_id)
        if not site:
            return Response(success=False, message="站点不存在")

        run_mode = self._normalize_run_mode(getattr(payload, "run_mode", None), payload.enabled)
        task = MagicFlowTaskConfig(
            id=task_id,
            name=payload.name,
            enabled=(run_mode == "running"),
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
        # 运行状态：编辑器「启用」开关优先（开启→运行中；关闭→已停止；做种中 保持不变）
        _req_mode = str(getattr(payload, "run_mode", None) or "").strip().lower()
        _prev_mode = str(getattr(task, "run_mode", "running") or "running")
        if payload.enabled and _req_mode != "running":
            _run_mode = "running"
        elif (not payload.enabled) and _req_mode == "running":
            _run_mode = "stopped"
        else:
            _run_mode = self._normalize_run_mode(_req_mode or _prev_mode, payload.enabled)
        task.run_mode = _run_mode
        task.enabled = (_run_mode == "running")
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
        if _run_mode != _prev_mode:
            self._spawn_run_mode_apply(task, _run_mode)
        return Response(success=True, message="任务已更新", data=self._build_task_detail(task_id))

    def delete_task(self, task_id: str) -> Response:
        """删除魔流任务。"""
        if task_id not in self._task_configs:
            return Response(success=False, message="任务不存在")

        del self._task_configs[task_id]
        if self._store:
            self._store.task_states.delete(task_id)
            # 同步清掉去重（seen）与操作记录，避免残留孤儿数据（每个任务都有独立桶）。
            try:
                self._store.seen.delete(task_id)
            except Exception as err:
                self._log(f"清理任务去重记录失败：{err}", "warning")
            try:
                self._store.journal.delete_task(task_id)
            except Exception as err:
                self._log(f"清理任务操作记录失败：{err}", "warning")
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary(drop=True)
        self._apply_task_traffic_limit()
        return Response(success=True, message="任务已删除")

    def update_task_state(self, task_id: str, payload: MagicFlowTaskStatePayload) -> Response:
        """切换任务运行状态（running / seeding / stopped）。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        mode = self._normalize_run_mode(
            getattr(payload, "mode", None), getattr(payload, "enabled", None)
        )
        task.run_mode = mode
        task.enabled = (mode == "running")
        self._save_config()
        self._refresh_scheduler()
        self._invalidate_summary(drop=True)
        self._apply_task_traffic_limit()
        # 异步应用种子操作（暂停/恢复）；「运行中」时立即跑一轮 check，避免非免费偷下空窗
        self._spawn_run_mode_apply(task, mode)
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

    def backfill_torrent_pages(self, task_id: str) -> Response:
        """回填存量托管种子的详情页链接（供「已非免费→清理」核对促销）。

        对当前托管（标签内）但未记录详情页链接的种子，依次尝试：
          ① seen 记录（hash↔cand 同时间戳配对）；② 站点「我的种子」列表按标题回填。
        只写本地记录，**不删任何种子**。
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
            # ① seen 记录（hash↔cand 同时间戳配对）→ 只保留当前托管的
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
                f"魔流 [{task.name}] 回填详情页链接：托管 {len(managed)} 个，"
                f"本次解析 {len(mapping)}，未匹配 {unresolved}，当前已知 {total_known}"
            )
            return Response(
                success=True,
                message=f"已回填 {len(mapping)} 个详情页链接（{unresolved} 个未能匹配）",
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
        """对所有任务批量回填详情页链接（只写记录，不删种）。"""
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
            message=f"已回填 {total_resolved} 个链接（{total_unresolved} 个未能匹配）",
            data={"managed": total_managed, "resolved": total_resolved, "unresolved": total_unresolved},
        )

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

            # 与总览共用同一份「全部种子按标签分组」快照（避免再单独全量拉一次 qB）
            task_torrents = list(self._tag_snapshot(task.downloader).get(task.brush_tag, []))
            error = None
            self._log(
                f"API 做种明细：task={task_id} tag=「{task.brush_tag}」 tagged={len(task_torrents)} err={error}"
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
                "protected_count": sum(1 for t in torrents_data if t["is_protected"]),
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

            candidates = None
            _pages = max(int(task.browse_pages or BROWSE_PAGES), 1)
            # 站点级共享：同站一份完整列表，刷流侧再筛免费（与主流程一致）。
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
                # 刷流：候选排行按「上传潜力」——下载人数↓、体积↓、新鲜度↑
                # （与 _brush_impl 选种/下载序一致；此前统一走魔力排序，与卡片标题矛盾）。
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
            # 媒体资产价值闸门：预览也排除已整理/辅种/历史命中的种子
            try:
                _asset = self._media_asset_hashes(list(task_torrents or []), task)
                if _asset:
                    protected_hashes = set(protected_hashes) | set(_asset)
            except Exception:
                pass

            # 刷流模式：预览「无上传将被清理」的种子（只读，不删）
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
                    "message": f"刷流模式：预计清理「无上传」种子 {len(would)} 个",
                })

            policy = self._build_magic_policy(task, torrent_bonus_list)

            preview = preview_deletions(torrent_bonus_list, policy, protected_hashes)
            return Response(success=True, data=preview)

        except Exception as e:
            self._log(f"预览删种失败: {e}", "error")
            return Response(success=False, message=str(e))

    # ---------------------------------------------------------
    # API：推荐（刷流种价值生命周期）
    # ---------------------------------------------------------

    def get_recommend_list(self) -> Response:
        """列出推荐甄别结果（供工作台「推荐」标签页）。"""
        store = getattr(self._store, "recommend", None) if self._store else None
        items = store.list() if store else []
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

    def confirm_recommend(self, hash: str) -> Response:
        """确认推荐：标记 confirmed；开启自动入库时尝试整理入库。"""
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
            msg = "已确认并提交整理入库" if ok else f"已确认；自动整理未成功：{imsg}"
            if ok:
                store.upsert(hash, import_result=str(imsg)[:200])
        return Response(success=True, message=msg, data=store.get(hash))

    def dismiss_recommend(self, hash: str) -> Response:
        """忽略推荐：删除该资源（不入影视库）。"""
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
                        message="已忽略并删除" if ok else f"已忽略；删除失败：{err}")

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

    def debug_recommend_reset(self) -> Response:
        """诊断：清空推荐甄别结果（仅测试/重置用）。"""
        store = getattr(self._store, "recommend", None) if self._store else None
        if store is None:
            return Response(success=False, message="推荐存储不可用")
        try:
            return Response(success=True, data={"cleared": store.clear()})
        except Exception as e:  # noqa: BLE001
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

    _TORRENT_CONTROL_ACTIONS = {
        "pause": ("暂停种子", "stop"),
        "resume": ("恢复运行", "start"),
        "recheck": ("强制校验", "recheck"),
    }

    def _control_torrent(self, task_id: str, hash: str, action: str) -> Response:
        """托管种子控制：暂停 / 恢复做种 / 强制校验。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")
        label = self._TORRENT_CONTROL_ACTIONS.get(action, (action, action))[0]
        try:
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                return Response(success=False, message="下载器不可用")

            func = {
                "pause": downloader.pause_torrents,
                "resume": downloader.resume_torrents,
                "recheck": downloader.recheck_torrents,
            }.get(action)
            if not func:
                return Response(success=False, message=f"不支持的操作：{action}")

            success_count, error = func([hash])
            if success_count <= 0:
                return Response(success=False, message=error or f"{label}失败")

            if self._store:
                # 手动暂停/恢复要落盘，避免「自动恢复暂停做种」把人工作废
                if action == "pause":
                    self._store.mark_manual_paused(task_id, [hash])
                elif action == "resume":
                    self._store.clear_manual_paused(task_id, [hash])
                self._store.journal.record(
                    task_id=task_id,
                    kind=action,
                    items=[OperationItem(hash=hash, title="", reason=f"手动{label}")],
                )
            self._invalidate_summary()
            return Response(success=True, message=f"已{label}")

        except Exception as e:
            self._log(f"种子操作({action})失败: {e}", "error")
            return Response(success=False, message=str(e))

    def pause_torrent(self, task_id: str, hash: str) -> Response:
        """暂停一个托管种子（并标记，防止被自动恢复）。"""
        return self._control_torrent(task_id, hash, "pause")

    def resume_torrent(self, task_id: str, hash: str) -> Response:
        """恢复做种。"""
        return self._control_torrent(task_id, hash, "resume")

    def recheck_torrent(self, task_id: str, hash: str) -> Response:
        """强制重新校验。"""
        return self._control_torrent(task_id, hash, "recheck")

    def batch_torrents(self, task_id: str, payload: MagicFlowTorrentBatchPayload) -> Response:
        """批量操作托管种子（保留 / 取消保留 / 暂停 / 恢复 / 强制校验 / 删除）。"""
        task = self._get_task_config(task_id)
        if not task:
            return Response(success=False, message="任务不存在")

        action = (payload.action or "").strip().lower()
        hashes = [h for h in (payload.hashes or []) if h]
        if not hashes:
            return Response(success=False, message="未选择种子")
        label = {
            "protect": "手动保留", "unprotect": "取消保留", "pause": "暂停种子",
            "resume": "恢复运行", "recheck": "强制校验", "delete": "批量删除",
        }.get(action, action)

        try:
            # ① 保护类：仅落盘，不碰下载器
            if action in ("protect", "unprotect"):
                if not self._store:
                    return Response(success=False, message="存储不可用")
                for h in hashes:
                    if action == "protect":
                        self._store.protect_torrent(task_id, h)
                    else:
                        self._store.unprotect_torrent(task_id, h)
                self._store.journal.record(
                    task_id=task_id,
                    kind="protection" if action == "protect" else "unprotection",
                    items=[OperationItem(hash=h, title="", reason=f"批量{label}") for h in hashes],
                )
                self._invalidate_summary()
                return Response(
                    success=True,
                    message=f"已批量{label} {len(hashes)} 个",
                    data={"success_count": len(hashes), "failed": 0, "total": len(hashes)},
                )

            # ② 下载器类
            downloader = self._get_downloader(task.downloader)
            if not downloader or not downloader.is_available:
                return Response(success=False, message="下载器不可用")

            if action == "delete":
                ok, error = downloader.delete_torrents(hashes=hashes, delete_file=task.delete_files)
                done = hashes[:max(0, int(ok or 0))]
            else:
                func = {
                    "pause": downloader.pause_torrents,
                    "resume": downloader.resume_torrents,
                    "recheck": downloader.recheck_torrents,
                }.get(action)
                if not func:
                    return Response(success=False, message=f"不支持的操作：{action}")
                ok, error = func(hashes)
                done = hashes[:max(0, int(ok or 0))]

            if self._store and done:
                if action == "pause":
                    self._store.mark_manual_paused(task_id, done)
                elif action == "resume":
                    self._store.clear_manual_paused(task_id, done)
                if action == "delete":
                    self._store.forget_torrents(task_id, done)
                self._store.journal.record(
                    task_id=task_id,
                    kind=action,
                    items=[OperationItem(hash=h, title="", reason=f"批量{label}") for h in done],
                )
            self._invalidate_summary()

            if not done:
                return Response(success=False, message=error or f"{label}失败")
            msg = f"已批量{label} {len(done)} 个"
            if len(done) < len(hashes):
                msg += f"（{len(hashes) - len(done)} 个失败）"
            return Response(
                success=True,
                message=msg,
                data={"success_count": len(done), "failed": len(hashes) - len(done), "total": len(hashes)},
            )

        except Exception as e:
            self._log(f"批量种子操作({action})失败: {e}", "error")
            return Response(success=False, message=str(e))
