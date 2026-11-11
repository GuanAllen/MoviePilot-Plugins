"""
MagicFlow 魔流插件

根据站点魔力公式自动优化做种,最大化魔力产出。
与 BrushFlow(优化分享率/容量)目标互斥,必须独立运行。
"""


from .common import (
    CLAIM_BATCH,
    CLAIM_DAILY_PER_SITE,
    CLAIM_INTERVAL_SEC,
    MagicFlowTaskConfig,
    __version__,
    _mf_on_event,
)

import re
from datetime import datetime
from typing import Any, Dict, Optional


from app.plugins import _PluginBase

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
from .features.hrreconcile import HrReconcileMixin
from .features.yema import YemaHrMixin
from .features.assets import AssetsMixin
from .features.jobs import JobsMixin
from .features.notify import NotifyMixin
from .features.services import ServicesMixin
from .features.reseed import ReSeedMixin
from .features.reuse import ReuseMixin
from .features.cleanup import CleanupMixin
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
from .features.claim import ClaimMixin
from .features.rss import RssMixin
from .features.creds import CredsMixin
from .features.trend import TrendMixin
from .features.health import HealthMixin
from .features.eventlog import EventLogMixin
from .features.sitereport import SiteReportMixin
from .features.recon import ReconMixin
from .features.reportview import ReportViewMixin
from .features.musicgrab import MusicGrabMixin
from .features.plan import PlanMixin

from .dupgate import DupGateMixin


class MagicFlow(DupGateMixin, CoreMixin, RuntimeMixin, AgentApiMixin, AgentLedgerMixin, PlanMixin, ApiMixin, RescueMixin, SettingsMixin, StatusMixin, TasksMixin, BrushMixin, FormulaMixin, ProtectionMixin, DeleteGateMixin, HrMixin, HrBillsMixin, HrReconcileMixin, YemaHrMixin, AssetsMixin, JobsMixin, NotifyMixin, ServicesMixin, ReuseMixin, ReSeedMixin, CleanupMixin, CrossSeedMixin, TagsMixin, SilentMixin, RecommendMixin, LiveMixin, ExamMixin, PoolMixin, CloudMixin, SiteOpsMixin, EventsMixin, ActionsMixin, DeckMixin, OnDemandMixin, DebugMixin, RegistryMixin, ClaimMixin, RssMixin, CredsMixin, TrendMixin, HealthMixin, EventLogMixin, SiteReportMixin, ReconMixin, ReportViewMixin, MusicGrabMixin, _PluginBase):
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

    # ============================================================
    # ★ 19.12.51 事件入口 —— **必须声明在插件主类上，不能留在 mixin 里**
    #
    # MP v3.2.2 的事件绑定按 handler 的**声明类名**去运行实例表取实例：
    #   runtime/extensions/plugin/manager.py:resolve_event_handler_instance
    #       plugin_id = owner_class.__name__
    #       if self._plugins.get(plugin_id) is not owner_class: return None
    # 声明在 EventsMixin / CoreMixin 上时 owner_class 是 mixin 名，插件表里没有
    # ⇒ resolver 返回 None ⇒ binding 报一行
    #   「事件处理器未绑定显式 resolver，已跳过：...EventsMixin._on_xxx」
    # 然后**永不执行**，且不抛异常、不影响插件启停，只在宿主日志里留一行 WARNING。
    #
    # 现场证据（2026-11-10 查 moviepilot-v3 日志）：拆 mixin 之后
    #   TransferComplete（库记入口）、PluginReload（重载后重注册 API/调度）
    # 一直是死的，站点事件自然也是死的。修法是「声明上浮」：
    # 装饰器与入口只留在主类，实现仍在各 mixin 里（显式传 self，不走 super）。
    # ============================================================

    @_mf_on_event("TransferComplete")
    def _on_transfer_complete(self, event: Any = None) -> None:
        """整理完成 → 写库记（实现在 ``features/events.py``）。"""
        return EventsMixin._on_transfer_complete(self, event)

    @_mf_on_event("SiteUpdated")
    def _on_site_updated(self, event: Any = None) -> None:
        """MP 站点新增/修改/CookieCloud 同步（建站复用 site.updated）。"""
        return EventsMixin._on_site_updated(self, event)

    @_mf_on_event("SiteDeleted")
    def _on_site_deleted(self, event: Any = None) -> None:
        """MP 站点删除（载荷只有 site_id，域名要靠台账反查）。"""
        return EventsMixin._on_site_deleted(self, event)

    @_mf_on_event("SiteRefreshed")
    def _on_site_refreshed(self, event: Any = None) -> None:
        """MP 站点用户数据刷新（做种量/分享率）。"""
        return EventsMixin._on_site_refreshed(self, event)

    @_mf_on_event("PluginReload")
    def reload(self, event: Any = None) -> None:
        """插件重载后重新注册动态 API 与任务调度（实现在 ``features/core.py``）。"""
        return CoreMixin.reload(self, event)


    def get_agent_tools(self) -> list:
        """★ 15.11.0：把魔流 AI 入口注册进 MoviePilot Agent / MCP。

        Master：「我说的就是我们 agent 里面的东西可以注册到这个 mcp 里面，点播什么的」
        MP 的 MCP server（``POST /api/v1/mcp``）会把这里返回的工具列进 ``tools/list``。
        """
        try:
            if not bool(getattr(self, "_agent_mcp", True)):
                return []
            from .features.mcptools import build_agent_tools
            return build_agent_tools(scope=str(getattr(self, "_agent_mcp_scope", "core") or "core"))
        except Exception as err:  # noqa: BLE001
            from app.sdk.logging import logger as _lg
            _lg.warning(f"魔流 MCP 工具注册失败（忽略）：{err}")
            return []

    def get_database_models(self) -> list:
        """声明插件自有库的 5 张表（MP 启动时一并建立，见 db.py）。"""
        from . import db as _db
        return list(_db.ALL_MODELS)

    # 运行状态
    _enabled: bool = False
    _show_sidebar_nav: bool = True
    _agent_mcp: bool = True                 # ★ 15.11.0：把 AI 入口注册进 MP Agent / MCP
    _agent_mcp_scope: str = "core"          # core=常用业务工具 / all=全部端点
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
