"""
MagicFlow 魔流插件

根据站点魔力公式自动优化做种,最大化魔力产出。
与 BrushFlow(优化分享率/容量)目标互斥,必须独立运行。
"""


from .common import (
    BROWSE_PAGES,
    BRUSH_SEED_UP_LIMIT_KBPS_DEFAULT,
    CLAIM_BATCH,
    CLAIM_DAILY_PER_SITE,
    CLAIM_INTERVAL_SEC,
    CLOUD_INTERVAL_MINUTES,
    CLOUD_SCAN_MAX,
    MagicFlowTaskConfig,
    __version__,
)

import re
import threading
from datetime import datetime
from typing import Any, Dict, Optional


from app.plugins import _PluginBase
from app.scheduler import Scheduler
from app.schemas.types import EventType

from .bonus import (
    DEFAULT_CANDIDATE_REF_WEEKS,
    candidate_ref_weeks,
)
from .iyuu_cloud import IyuuCloud
from .persistence import MagicFlowStore


from .features.core import CoreMixin
from .features.runtime import RuntimeMixin
from .features.api import ApiMixin
from .features.agentapi import AgentApiMixin
from .features.agentledger import AgentLedgerMixin
from .features.rescue import RescueMixin
from .features.settings import SettingsMixin
from .features.status import StatusMixin
from .features.tasks import TasksMixin
from .features.brush import BrushMixin
from .features.formula import FormulaMixin
from .features.protection import ProtectionMixin
from .features.deletegate import DeleteGateMixin
from .features.hr import HrMixin
from .features.hrbills import HrBillsMixin
from .features.yema import YemaHrMixin
from .features.assets import AssetsMixin
from .features.services import ServicesMixin
from .features.reseed import ReSeedMixin
from .features.reuse import ReuseMixin
from .features.cleanup import CleanupMixin
from .features.swap import SwapMixin
from .features.crossseed import CrossSeedMixin
from .features.tags import TagsMixin
from .features.silent import SilentMixin
from .features.recommend import RecommendMixin
from .features.live import LiveMixin
from .features.exam import ExamMixin
from .features.pool import PoolMixin
from .features.cloud import CloudMixin
from .features.siteops import SiteOpsMixin
from .features.events import EventsMixin
from .features.actions import ActionsMixin
from .features.deck import DeckMixin
from .features.ondemand import OnDemandMixin
from .features.debug import DebugMixin
from .features.registry import RegistryMixin
from .features.migrate import MigrateMixin
from .features.claim import ClaimMixin
from .features.trend import TrendMixin
from .features.health import HealthMixin
from .features.eventlog import EventLogMixin

from .dupgate import DupGateMixin


class MagicFlow(DupGateMixin, CoreMixin, RuntimeMixin, AgentApiMixin, AgentLedgerMixin, ApiMixin, RescueMixin, SettingsMixin, StatusMixin, TasksMixin, BrushMixin, FormulaMixin, ProtectionMixin, DeleteGateMixin, HrMixin, HrBillsMixin, YemaHrMixin, AssetsMixin, ServicesMixin, ReuseMixin, ReSeedMixin, CleanupMixin, SwapMixin, CrossSeedMixin, TagsMixin, SilentMixin, RecommendMixin, LiveMixin, ExamMixin, PoolMixin, CloudMixin, SiteOpsMixin, EventsMixin, ActionsMixin, DeckMixin, OnDemandMixin, DebugMixin, RegistryMixin, MigrateMixin, ClaimMixin, TrendMixin, HealthMixin, EventLogMixin, _PluginBase):
    """魔流插件主类。"""

    plugin_name = "魔流"
    plugin_desc = "PT 自动选种与做种管理:魔力养护 + 刷流双模式。"
    plugin_icon = "https://raw.githubusercontent.com/GuanAllen/MoviePilot-Plugins/main/icons/magicflow.png"
    plugin_version = __version__
    plugin_label = "站点,做种,魔力,刷流"
    plugin_author = "GuanAllen"
    author_url = "https://github.com/GuanAllen"
    plugin_config_prefix = "magicflow_"
    plugin_order = 50
    auth_level = 1

    DATA_SCHEMA_VERSION = 1

    def get_database_models(self) -> list:
        """声明插件自有库的 5 张表（MP 启动时一并建立，见 db.py）。"""
        from . import db as _db
        return list(_db.ALL_MODELS)

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
    # 任务流量(qB 全局上传限速,按在跑任务类型自动切档)
    _bonus_upload_limit_kbps: float = 200.0
    _brush_upload_limit_kbps: float = 10240.0
    _seed_up_limit_kbps: float = 200.0      # 挂种(魔力/来源份/推荐)单种上传限速(KB/s)，0=不限
    _brush_seed_up_limit_kbps: float = 5120.0  # 刷流单种上传限速(KB/s)，0=不限
    _seed_up_limit_last: Any = None         # (值签名, ts) 上次应用，值没变就跳过
    _last_up_limit_bps: Optional[int] = None
    # 标签模型
    _tags_cfg: Dict[str, Any] = {}
    _tag_last_snapshot: float = 0.0
    # IYUU 云端辅种(可选)
    _iyuu_token: str = ""
    _iyuu_sites: Dict[str, Dict[str, str]] = {}
    _iyuu_client: Optional[IyuuCloud] = None
    # 认领(claim):把「我们在做种」的种在站点侧认领掉,换站点权益(CARPT:达标种魔力×2)。
    #   ★ 写动作有真实代价(不达标 −100 / 放弃 −500) → 默认关 + 默认干跑 + 写动作必须 confirm。
    _claim_enabled: bool = False
    _claim_dry: bool = True                 # True=只预览不写
    _claim_sites: list = []                 # 白名单(域名);空=全部支持的站
    _claim_daily: int = CLAIM_DAILY_PER_SITE
    _claim_batch: int = CLAIM_BATCH
    _claim_interval_sec: float = CLAIM_INTERVAL_SEC
    _claim_min_age_days: float = 0.0        # 0=按站点 profile
    _claim_require_seeders: int = 0         # 安全阀:做种人数下限,0=不限
    _claim_min_size_gb: float = 0.0         # 安全阀:体积下限,0=不限
    _claim_exclude_zero_bonus: bool = True  # 零魔种不认领(无收益)
    # 元数据兜底(多源识别 + 补 NFO)
    _fallback_cfg: Dict[str, Any] = {}
    _fallback_engine: Optional[Any] = None

    # 运行阶段(供前端「运行诊断」流程链转圈)
    PHASE_LABELS = {
        "entry": "入口检查",
        "fetch": "抓取候选",
        "wash": "洗池过滤",
        "classify": "分类排序",
        "process": "处理入库",
        "done": "本轮结束",
        "error": "执行出错",
    }

    _PROMO_TTL = 600  # 促销状态内存缓存(秒),避免每轮检查都回站点逐个抗详情页
    _TITLE_URL_TTL = 600  # 「我的种子」列表回填 URL 的缓存时长(秒)

    # ★ 3.41.2：只认「规则」类地址；faq/常见问题/帮助 是**通用模板**（各站一字不差），不当站规
    _RULE_LINK_HARD = re.compile(r"规则|rules|版规|wiki", re.I)
    _RULE_LINK_STRONG = re.compile(r"规则|rules|版规|wiki", re.I)
    _RULE_LINK_BAD = re.compile(
        r"myhr|viewmessage|messages\.php|adredir|login|logout|signup|takeconfirm|sendmessage"
        r"|usercp|torrents\.php|getusertorrentlist|viewforum",
        re.I,
    )

    # 存量地址里可能混着旧的 faq/userdetails（通用模板/个人信息），读之前先清洗
    _RULE_URL_BAD = re.compile(
        r"faq|常见|help\.php|userdetails|messages\.php|myhr|adredir|login|logout|usercp", re.I
    )

    _TORRENT_CONTROL_ACTIONS = {
        "pause": ("暂停种子", "stop"),
        "resume": ("恢复运行", "start"),
        "recheck": ("强制校验", "recheck"),
    }
