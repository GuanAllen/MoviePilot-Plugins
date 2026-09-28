import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .tags import DEFAULT_SORT_RULES

# 云盘归档默认远端落点模板（{rel} = 库内相对路径，与本地库结构同构）
DEFAULT_CLOUD_TEMPLATE = "/quark/movie/{rel}"


def _normalize_optional_positive_number(value):
    """把历史配置中的空值和 0 统一转换为未设置。"""
    if value is None or value == "":
        return None
    try:
        if float(value) == 0:
            return None
    except (TypeError, ValueError):
        return value
    return value


class MagicFlowTaskPayload(BaseModel):
    """魔流任务新增与更新请求模型"""

    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=80)
    enabled: bool = True
    site_id: int = Field(..., gt=0)
    site_domain: Optional[str] = None
    site_name: Optional[str] = None
    downloader: str = Field(..., min_length=1, max_length=80)
    brush_tag: Optional[str] = Field(None, max_length=60)
    save_path: Optional[str] = None

    # 调度配置
    brush_interval: int = Field(5, ge=1, le=1440)
    check_interval: int = Field(1, ge=1, le=1440)
    cron_expression: Optional[str] = None
    active_time_range: Optional[str] = None

    # 魔力配置
    min_bonus_per_hour: Optional[float] = Field(None, ge=0, description="每小时最低魔力产出，低于此值将被删除；留空=自动（当前种子魔力中位数×0.5）")
    max_keep_torrents: Optional[int] = Field(None, gt=0, description="最多保留种子数量，留空=自动（按保种体积推算）/不限")
    bonus_protect_threshold: Optional[float] = Field(None, ge=0, description="魔力保护阈值，高于此值时不删除任何种子；留空=自动（站点当前魔力）")
    min_bonus_to_keep: Optional[float] = Field(None, ge=0, description="最低魔力值，魔力低于此值时停止删种保底")
    disk_size_gb: Optional[float] = Field(None, gt=0, description="保种体积上限（GB），留空不限，用于自动推算最多保留种子数")
    protect_perfect: bool = Field(True, description="完美种保护：满足（非零魔 · 做种人数≤上限 · 做种周数≥下限）的优质老种永久保留，不参与清理")
    perfect_max_seeders: int = Field(3, ge=0, le=100000, description="完美种判定：站内做种人数上限（0=不限制）")
    perfect_min_weeks: float = Field(4.0, ge=0, le=520, description="完美种判定：做种周数下限（0=不限制）")
    refill_when_empty: bool = Field(True, description="清理低效种子后主动补种，保持任务做种量")
    max_add_per_run: int = Field(10, ge=1, description="单轮最多新增种子数（未设「最多保留 / 保种体积」时，每轮就按这个名额补种）")
    max_download_concurrent: int = Field(10, ge=1, le=100, description="本任务同时「下载中」上限（queued 排队不计入），复用/辅种不受此限制")
    top_n: int = Field(30, ge=1, le=1000, description="每轮参与排序处理的候选上限（TopN，超过即裁剪）")
    browse_pages: int = Field(3, ge=1, le=50, description="每轮站点列表翻页数（游标深翻，从上次游标处继续）")

    # 存量复用（辅种）：优先复用下载器/本机已有资源，避免重复下载
    reuse_existing: bool = Field(True, description="复用本机已有资源（辅种）：同 hash 直接打标签、同文件列表直接做种，不重复下载")
    reuse_verify: bool = Field(True, description="辅种前先校验已有文件；校验不通过自动撤销（避免误下载）")

    # 跨站免费取种（3.9.0）：目标站的种子若不免费（下载要烧流量），去任意他站找「免费且同一 Release」的副本下回来，再回辅目标站——对目标站是零下载纯做种
    crossseed_enabled: bool = Field(False, description="跨站免费取种：目标站不免费的种子，改从他站免费副本下载后回辅（默认关）")
    crossseed_max_per_round: int = Field(3, ge=1, le=50, description="每轮最多发起几个跨站取种")
    crossseed_max_size_gb: float = Field(20.0, gt=0, le=2000, description="跨站取种的单个种子大小上限（GB）")
    crossseed_max_sites: int = Field(6, ge=1, le=50, description="每个候选最多探测几个站（PV 上限）")

    # 无进度清理：每次运行清掉「没进度」的种子（进度为 0 且停滞/出错），避免占位却不产魔力
    cleanup_no_progress: bool = Field(True, description="每次运行清理「没进度」的种子（下载进度为 0 且停滞/出错）")
    no_progress_minutes: int = Field(30, ge=1, le=1440, description="加入下载器超过该分钟数仍无进度才判定为可清理")

    # 慢速清理：用「下载速度 ÷ 体积」估算 ETA，长期下不完的种子会霸占下载名额 → 清掉腾位
    cleanup_slow_progress: bool = Field(True, description="清理「下载过慢」的种子（速度÷体积估算下不完），腾出下载名额")
    slow_progress_grace_minutes: int = Field(60, ge=1, le=1440, description="种子加入后多少分钟内不判「慢」（给新种起步时间）")
    slow_progress_max_hours: float = Field(48.0, gt=0, le=8760, description="按当前速度预计还要超过该小时数才下完 → 判「过慢」")

    # 促销失效清理：下载中的种子若站点已不再免费（促销过期 / 非免费）→ 删除，避免白拉流量拉低分享率
    purge_unfree_incomplete: bool = Field(True, description="下载中但站点已不再免费的种子自动清理（回站点核对促销状态）")

    # 自动恢复：被暂停的已完成种子自动重新做种（暂停 = tracker 不计做种 = 0 魔力）
    auto_resume_paused: bool = Field(True, description="自动恢复被暂停的已完成种子（重新开始做种），保证魔力产出")

    # Ti 口径：publish（默认，自发布时间）| seed_time（qB 做种时长）
    ti_source: str = Field("publish", description="Ti 口径：publish（发布时长，默认）或 seed_time（做种时长）")

    # 任务类型：bonus=刷魔力（默认）；brush=刷流（按上传产出，无上传即清理）
    task_type: Literal["bonus", "brush"] = Field("bonus", description="任务类型：bonus=刷魔力；brush=刷流")
    # 运行状态：running=运行中；seeding=做种中（停调度、未完成种暂停、已完成种继续做种）；stopped=已停止（全部暂停，保文件）
    run_mode: Optional[Literal["running", "seeding", "stopped"]] = Field(None, description="运行状态；留空则按 enabled 推算（True→running / False→stopped）")
    brush_grace_minutes: int = Field(15, ge=0, le=1440, description="刷流模式：新种加入后多少分钟内不判「无上传」")
    upload_idle_minutes: int = Field(10, ge=0, le=1440, description="刷流模式：连续多少分钟无上传则清理（0=自动≈2×检查间隔）")
    upload_min_kbps: int = Field(200, ge=1, le=102400, description="刷流模式：平均上传速率门槛（KB/s），低于此值视为「无上传」")
    brush_min_leechers: int = Field(1, ge=0, le=100000, description="刷流模式：最小下载人数（有下载需求才值得下）")
    brush_seed_days: int = Field(2, ge=0, le=365, description="刷流模式：做种满多少天后清理换新（默认 2 天；0=不按天数，改回「无上传」判定）")

    # 产出换种（刷流）：以「产出」而非「时间」为口径换新 —— 单种已上传达标 / 分享率达标即清理
    rotate_upload_gb: Optional[float] = Field(None, ge=0, description="刷流：单种已上传达到该 GB 数即清理换新（留空=不看上传量）")
    rotate_ratio: Optional[float] = Field(None, ge=0, description="刷流：单种分享率达到该值即清理换新（留空=不看分享率）")

    # 选种排除订阅命中（刷流）：候选命中当前订阅标题 → 不选，避免抢主人要看的片
    except_subscribe: bool = Field(True, description="刷流选种：排除命中当前订阅标题的候选")

    # 删除排除标签（任务级，叠加在「已整理/辅种」硬保护之上）：逗号分隔，命中者永不删除
    delete_except_tags: str = Field("", max_length=200, description="永不删除的标签（逗号分隔，叠加在「已整理/辅种」之上）")

    # 任务目标：达到后任务自动停止（bonus=站点魔力值；brush=站点上传量 GB）
    goal_value: Optional[float] = Field(None, ge=0, description="任务目标：bonus=站点魔力值达到多少；brush=站点上传量（GB）。达到后任务自动停止；留空=未设目标（前端会提醒）")
    download_target_gb: Optional[float] = Field(None, ge=0, description="考核下载模式：本站「下载增量」目标（GB）。>0 且允许非免费时，刷流会下非免费种凑够该增量后自动转「做种中」")
    allow_unfree_download: bool = Field(False, description="考核下载模式：允许下载非免费种（默认关；仅在有下载目标时生效）")

    # 已处理去重：站点列表页每次都返回同一批最新种子，记录已处理候选避免重复拉取
    seen_cooldown_hours: float = Field(24.0, ge=0, le=8760, description="同一候选在多少小时内不重复拉取（0=不跳过）")

    # 魔力公式参数（高级，留空即用站点默认 / NexusPHP 标准式）
    bonus_t0: Optional[float] = Field(None, gt=0, description="生存时间参数 T0（默认 5）")
    bonus_n0: Optional[int] = Field(None, gt=1, description="做种人数参数 N0（默认 7）")
    bonus_b0: Optional[float] = Field(None, gt=0, description="每小时魔力上限 B0（默认 100）")
    bonus_l: Optional[float] = Field(None, gt=0, description="曲线参数 L（默认 300）")
    bonus_zero_weight: Optional[float] = Field(None, ge=0, description="零魔种子权重（默认 0.2）")

    # 选种过滤
    size: Optional[str] = None
    seeder: Optional[str] = None
    pubtime: Optional[str] = None
    include: Optional[str] = None
    exclude: Optional[str] = None
    freeleech: Literal["", "free", "2xfree"] = ""
    hr: Optional[str] = None

    # 删除配置
    min_seed_time: Optional[float] = Field(None, ge=0)
    min_ratio: Optional[float] = Field(None, ge=0)
    delete_files: bool = True
    exclude_zero_bonus: bool = True

    # RSS / 限速
    rss_support: bool = False
    up_speed: Optional[float] = Field(None, gt=0)
    dl_speed: Optional[float] = Field(None, gt=0)

    @field_validator(
        "min_bonus_per_hour", "max_keep_torrents", "bonus_protect_threshold",
        "min_bonus_to_keep", "min_seed_time", "min_ratio", "up_speed", "dl_speed",
        "bonus_t0", "bonus_n0", "bonus_b0", "bonus_l", "disk_size_gb",
        "rotate_upload_gb", "rotate_ratio",
        mode="before",
    )
    @classmethod
    def normalize_optional_positive_number(cls, value):
        return _normalize_optional_positive_number(value)

    @field_validator("name", "downloader")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("字段不能为空")
        return cleaned

    @field_validator(
        "site_domain", "site_name", "brush_tag", "save_path", "cron_expression",
        "active_time_range", "include", "exclude", "size", "seeder", "pubtime", "hr",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("brush_tag")
    @classmethod
    def validate_tag(cls, value: Optional[str]) -> Optional[str]:
        if value and "," in value:
            raise ValueError("下载器标签不能包含逗号")
        return value

    @field_validator("size", "seeder")
    @classmethod
    def validate_number_range(cls, value: Optional[str]) -> Optional[str]:
        if value and not re.fullmatch(r"\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?", value):
            raise ValueError("请输入数字或数字范围，例如 10 或 10-80")
        return value

    @field_validator("active_time_range")
    @classmethod
    def validate_active_time_range(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if not re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", value):
            raise ValueError("开启时间段格式应为 HH:MM-HH:MM")
        from datetime import datetime as _dt
        start, end = value.split("-", 1)
        _dt.strptime(start, "%H:%M")
        _dt.strptime(end, "%H:%M")
        return value

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            from apscheduler.triggers.cron import CronTrigger
            CronTrigger.from_crontab(value)
        except Exception as err:
            raise ValueError(f"CRON 表达式无效：{err}")
        return value

    @model_validator(mode="after")
    def validate_magic_bonus_config(self):
        """魔力保护阈值和最低魔力值需要配合使用"""
        if self.min_bonus_to_keep is not None and self.bonus_protect_threshold is not None:
            if self.min_bonus_to_keep >= self.bonus_protect_threshold:
                raise ValueError("最低魔力保留值应小于魔力保护阈值")
        return self


class MagicFlowTaskStatePayload(BaseModel):
    """魔流任务启停请求模型

    - ``mode``：running（运行中）/ seeding（做种中）/ stopped（已停止）；
    - ``enabled``：兼容旧调用（True→running / False→stopped）；两者同传时以 mode 为准。
    """

    enabled: Optional[bool] = None
    mode: Optional[Literal["running", "seeding", "stopped"]] = None


class MagicFlowHandoverPayload(BaseModel):
    """任务删除前处理名下种子：交棒给其它任务 / 退回静默池。"""

    target_task_id: str = Field("", max_length=32, description="交棒目标任务 id（留空 = 退回静默池）")
    mode: str = Field("handover", max_length=12, description="handover=交棒 / idle=退回静默池")
    hashes: List[str] = Field(default_factory=list, description="只转移这些 hash（留空 = 该任务名下全部）")


class MagicFlowTagStatePayload(BaseModel):
    """手动设置某个种子的状态（标签模型）。"""

    hash: str = Field(..., max_length=64, description="种子 hash")
    state: str = Field(..., max_length=12, description="刷流 / 魔力 / 静默 / 推荐")
    sub: str = Field("", max_length=12, description="静默子类：新 / 资源 / 普通（非静默可空）")
    site: str = Field("", max_length=60, description="站点短名（通常自动识别）")


class MagicFlowTagMigratePayload(BaseModel):
    """老标签 → 新命名（魔流-<站点>-<状态>）迁移。"""

    apply: bool = Field(False, description="false = 只预演(dry-run)，true = 真正改标签")


class MagicFlowSettingsPayload(BaseModel):
    """魔流插件全局设置请求模型"""

    # 基础
    enabled: bool = True
    show_sidebar_nav: bool = True

    # 运行
    debug_log: bool = False
    journal_keep: int = Field(200, ge=0, le=5000, description="每个任务保留的操作记录上限，0 = 不限")
    request_interval: float = Field(0.0, ge=0, le=600, description="站点翻页请求之间的最小间隔（秒），0 = 不限速")

    # 任务流量（qB 全局上传限速，按「在跑的任务类型」自动切档；只限上传）
    bonus_upload_limit_kbps: float = Field(200.0, ge=0, le=1048576, description="魔力任务在跑时的 qB 全局上传限速 KB/s（无刷流任务时生效），0 = 不限")
    brush_upload_limit_kbps: float = Field(10240.0, ge=0, le=1048576, description="刷流任务在跑时的 qB 全局上传限速 KB/s（刷流优先），0 = 不限")
    seed_up_limit_kbps: float = Field(200.0, ge=0, le=1048576, description="挂种（魔力/来源份/推荐）单种上传限速 KB/s，0 = 不限")
    brush_seed_up_limit_kbps: float = Field(5120.0, ge=0, le=1048576, description="刷流单种上传限速 KB/s（刷流的种子给足速度），0 = 不限")

    # 界面
    compact_mode: bool = False

    # IYUU 云端辅种（可选）：Token 留空 = 不启用，退回内置跨站复用
    iyuu_token: str = Field("", max_length=200, description="IYUU 云端 Token，留空 = 不启用 IYUU 辅种")
    iyuu_clear: bool = Field(False, description="置 true 则清空已存的 IYUU Token（否则空值=保持原值）")
    iyuu_sites: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="站点密钥表：domain -> {passkey/uid/downhash...}（用户手填，优先于自动获取）",
    )

    # ── 刷流种甄别与推荐（价值生命周期）────────────────────────────────────
    #  影视管理类插件：下了的资源除了刷流，还有「看/收藏」价值。
    #  刷流/魔力任务会把「同 hash 的库内资源」复用进来；对**非资产**的刷流种：
    #  识别→豆瓣评分+榜单/订阅→值得则打「推荐」tag、保护并通知；过期未确认则删。
    recommend_enabled: bool = Field(True, description="启用「刷流种甄别与推荐」")
    recommend_min_rating: float = Field(
        7.5, ge=0, le=10,
        description="推荐门槛：评分需大于该值（默认 TMDB 评分；可切换为豆瓣优先）"
    )
    recommend_rating_source: str = Field(
        "tmdb", max_length=20,
        description="评分源：douban=豆瓣优先(取不到回退 TMDB) / tmdb=只用 TMDB"
    )
    recommend_douban_max_per_run: int = Field(
        0, ge=0,
        description="每轮最多新增多少次豆瓣查询（防風控；默认 30，0=不限）"
    )
    recommend_douban_service_url: str = Field(
        "", max_length=200,
        description="豆瓣评分服务地址（magicflow-douban），留空用默认 http://magicflow-douban:18789"
    )
    recommend_require_chart: bool = Field(True, description="榜单/热映/命中订阅时也算达标（与评分为「或」关系）")
    recommend_expire_days: float = Field(7.0, ge=0, le=3650, description="推荐待确认窗口（天）；磁盘不足则立即视为过期")
    recommend_tag: str = Field("魔流-推荐", max_length=60, description="推荐资源单独 tag（同时受价值闸门保护）")
    recommend_auto_import: bool = Field(True, description="确认后自动整理入库")
    recommend_notify: bool = Field(True, description="命中推荐时推送通知")
    recommend_temp_ttl_days: float = Field(7.0, ge=0, le=3650, description="识别不出/不推荐的纯刷流临时种 TTL（天），0=不按此清")
    recommend_disk_min_free_gb: float = Field(50.0, ge=0, description="磁盘剩余低于该值(GB)即视为「磁盘不足」：推荐种立即按过期处理")

    # ── 跨站辅种（兄弟站取种 → 回辅，3.11.0 流量兜底）──────────────────────
    #  跨站取种依赖「他站这个种免费」的判断。判断可能错（程序解析错 / 站点促销变了），
    #  一旦误判就会白烧兄弟站的下载流量。这里做**双重兜底**：
    #   ① 核对来源站「正在下载」列表里的免费标记（不免费 → 立即删种 + 拉黑该站）；
    #   ② 对比取种前后来源站的下载量增量（超阈值 → 同样删种 + 拉黑）。
    crossseed_guard: bool = Field(True, description="启用兄弟站「流量兜底」：跨站取种期间核对来源站免费状态与下载量增量，发现其实不免费立即删种并拉黑该站")
    crossseed_guard_pct: float = Field(5.0, ge=0, le=100, description="流量兜底阈值：来源站下载增量 > 目标体积 × 该百分比 即视为「不免费」")
    crossseed_guard_min_mb: float = Field(50.0, ge=0, description="流量兜底最小判定增量(MB)，避免统计抖动误判")
    crossseed_guard_interval_min: float = Field(15.0, ge=0, le=1440, description="同一来源站的兜底核对间隔(分钟)")
    #  ★ H&R 保护：他站免费下载到的数据，那份来源种在来源站的保种义务还没结束
    #  （例：学校 BTSchool 要求挂种 10h）。保种期内任何任务不得删它/改它的标签。
    crossseed_guard_keep_seed: bool = Field(True, description="来源站着 H&R 保种要求：来源份在保种期内永久保护、不回收（默认开）")
    crossseed_seed_hours_default: float = Field(24.0, ge=0, le=720, description="来源站未单独指定时的最短保种时长(小时)")
    crossseed_site_hours: List[str] = Field(default_factory=lambda: ["pt.btschool.club=10"], description="站点保种时长覆盖：格式 域名=小时（例：pt.btschool.club=10 学校要10h）")
    crossseed_reclaim: bool = Field(False, description="H&R 保种期满后自动回收来源份：只删种子不删文件（默认关，继续做种）")
    rules_auto_refresh: bool = Field(True, description="每周自动逐站探测站点规则（H&R/最短保种时长/做种上限）并入库")

    # ── 标签模型（3.13.0）：种子状态=标签，账本=真值源 ─────────────────────
    #  命名：魔流-<站点>-<状态>[-<子类>]；状态 刷流/魔力/静默(新|资源|普通)/推荐。
    #  账本记 hash→状态/来源子类/占用者，标签可被改坏而账本自愈。
    tag_model_enabled: bool = Field(True, description="启用标签模型（状态账本 + 魔流-<站点>-<状态> 标签）")
    tag_silent_new_timeout_hours: float = Field(24.0, ge=0, le=720, description="「静默-新」超过该小时数未分拣自动归「静默-普通」，0 = 不超时")
    tag_snapshot_interval_hours: float = Field(6.0, ge=0, le=168, description="状态账本快照间隔（小时），0 = 不快照")
    sort_rules: List[Dict[str, Any]] = Field(
        default_factory=lambda: [dict(r) for r in DEFAULT_SORT_RULES],
        description="静默分拣规则（订阅/库内资产/豆瓣评分/年份/站点/分类），支持 dry-run 预演",
    )

    # ── 元数据兜底（多源识别 + 补 NFO）────────────────────────────────────
    #  TMDB 对中日番剧的特别篇/前传/国漫经常「没有」，离了 TMDB 就无元数据可用。
    #  这里做：多源识别（tmdb→bangumi→douban）→ 给库里缺 NFO 的集补最小 NFO；
    #  可选把「所有源里都不存在」的集改归 Season 0 特别篇。只写 NFO，不动媒体文件。
    fallback_enabled: bool = Field(True, description="启用「元数据兜底」（多源识别 + 补 NFO）")
    fallback_sources: List[str] = Field(
        default_factory=lambda: ["themoviedb", "bangumi", "douban"],
        description="识别来源顺序（MP 内置源：themoviedb/bangumi/douban/anilist/tvdb/imdb）",
    )
    fallback_paths: List[str] = Field(
        default_factory=list,
        description="兜底扫描的库根目录；留空 = 自动取 MoviePilot 目录配置里的 library_path",
    )
    fallback_interval_minutes: float = Field(30.0, ge=5, le=1440, description="兜底扫描周期（分钟）")
    fallback_scan_max: int = Field(30, ge=1, le=500, description="每轮最多处理的剧集目录数（其余下轮继续）")
    fallback_sp_to_s00: bool = Field(False, description="把「所有源里都不存在」的集改归 Season 0 特别篇（S00EXX）")
    fallback_after_import: bool = Field(True, description="整理入库后立即对该剧做一次兜底")
    fallback_dry_run: bool = Field(False, description="演练模式：只报告不写 NFO")

    # ── 站点实时数据 + 站点流量监控 ────────────────────────────────────
    #  MoviePilot 的站点账号数据走它自己的「站点数据刷新」（默认 6h）→ 对魔流的**决策**太滞后。
    #  这里直连站点用户栏页拿实时值（上传/下载/分享率/魔力/做种数），并监控「下载量在涨」
    #  （唯一真危险信号：免费种不吃下载，涨下载 = 吃到促销尾巴）。抓不到自动回退 MP 数据。
    live_enabled: bool = Field(True, description="启用「站点实时数据 + 流量监控」")
    live_interval_minutes: float = Field(4.0, ge=1, le=120, description="采样周期（分钟）：60s 太频繁，站点吃不消，默认 240s")
    live_download_alert_mb: float = Field(50.0, ge=1, description="下载量增长告警阈值（MB/分钟，超过则告警）")
    live_ratio_target: float = Field(0.5, ge=0, le=100, description="分享率目标线（低于则告警并算缺口），0 = 不检查")
    live_auto_stop: bool = Field(False, description="自动止损：下载量异常增长时把该站「运行中」任务切「做种中」（停调度、不删种）")
    live_kill_unfree: bool = Field(True, description="下载量异常增长时：取站点「正在下载」列表，把非免费的种从下载器干掉")
    live_kill_delete_files: bool = Field(True, description="干掉非免费下载种时是否连文件一起删（只对「下载中」且名称+体积匹配的种生效）")
    live_notify: bool = Field(True, description="站点监控命中时推送通知")

    # ── 新手考核（各站 index.php 首页的考核块；魔流本就抓 index.php → 零额外 PV）────
    #  开启后：解析各站考核进度（上传/下载增量、平均做种时间、魔力/做种积分增量），
    #  支持「一键起任务」；**关闭则不解析、不展示**（默认关）。
    exam_enabled: bool = Field(False, description="启用「新手考核」：抓取考核进度 + 一键起任务（关闭则不解析、不显示）")
    exam_include_pass: bool = Field(False, description="显示「已通过」的考核（默认只显示未通过的）")
    exam_sites: List[str] = Field(default_factory=list, description="只监控这些站点的考核（留空 = 全部已配置 Cookie 的站点）")

    # ── 站点签到 / 模拟登录（借鉴 MoviePilot「站点自动签到」插件）────────────
    #  通用签到 = 带 Cookie GET attendance.php；想签几个签几个（多选站点）。
    signin_enabled: bool = Field(False, description="启用「站点签到 / 模拟登录」")
    signin_sites: List[str] = Field(default_factory=list, description="签到站点（多选，选多少有多少）")
    signin_login_sites: List[str] = Field(default_factory=list, description="模拟登录站点（多选，保活 Cookie 并刷新站点数据）")
    signin_retry_keyword: str = Field("错误|失败", description="失败文案命中该正则则重试一次（留空 = 不重试）")
    signin_queue: int = Field(5, description="并发数（同时处理几个站点）")
    signin_notify: bool = Field(True, description="签到/登录结果推送通知")
    signin_interval_minutes: float = Field(360, description="签到 worker 间隔（分钟；同站当天已成功则自动跳过，故一天只需跑几次）")
    signin_window_start: int = Field(9, description="只在几点之后跑（默认 9 点）")
    signin_window_end: int = Field(23, description="几点之后不再跑（默认 23 点）")

    # ── 云盘归档（夸克冷库）────────────────────────────────────────────
    #  本地当热区、夸克当冷库：把库内成品大文件上传到夸克（经 OpenList HTTP API），
    #  本地腾空；OpenList 的 Strm 视图自动生成播放指针，影视照常能看。
    #  安全默认：dry_run=True、delete_local=False、remove_torrent=False。
    cloud_enabled: bool = Field(False, description="启用「云盘归档」（上传到夸克冷库）")
    cloud_openlist_url: str = Field(
        "http://192.168.0.61:12022", max_length=300, description="OpenList 地址"
    )
    cloud_openlist_token: str = Field(
        "", max_length=400, description="OpenList API 令牌（留空 = 保持原值不变）"
    )
    cloud_source_mount: str = Field("/quark", max_length=200, description="写入用的挂载点（cookie 版夸克，可写）")
    cloud_strm_mount: str = Field("/movie", max_length=200, description="Strm 视图挂载点（用于校验 strm 生成）")
    cloud_paths: List[str] = Field(
        default_factory=list, description="扫描的库根目录；留空 = /movie"
    )
    cloud_target_template: str = Field(
        DEFAULT_CLOUD_TEMPLATE, max_length=400, description="远端落点模板（{rel} 为库内相对路径）"
    )
    cloud_interval_minutes: float = Field(360.0, ge=5, le=10080, description="归档轮询周期（分钟）")
    cloud_scan_max: int = Field(50, ge=1, le=1000, description="每轮最多处理的文件数")
    cloud_min_size_gb: float = Field(2.0, ge=0, description="体积门槛（GB），小于此值不归档")
    cloud_max_size_gb: float = Field(200.0, ge=0, description="单文件上限（GB），0 = 不限")
    cloud_min_age_days: float = Field(30.0, ge=0, description="最后修改距今需超过该天数才归档（0 = 不限）")
    cloud_exclude_paths: List[str] = Field(
        default_factory=lambda: ["/movie/刷流", "/movie/下载"],
        description="排除路径（前缀匹配）",
    )
    cloud_exclude_tags: List[str] = Field(
        default_factory=lambda: ["魔流-推荐"], description="排除标签（命中即不归档）"
    )
    cloud_upload_limit_mbps: float = Field(0.0, ge=0, description="上传限速 MB/s，0 = 不限")
    cloud_verify: str = Field("size", max_length=20, description="校验方式：size / sha1")
    cloud_dry_run: bool = Field(True, description="演练模式：只出计划，不上传")
    cloud_delete_local: bool = Field(False, description="上传校验通过后删除本地文件（危险）")
    cloud_remove_torrent: bool = Field(False, description="归档后同时删种（危险，会停种）")
    cloud_notify: bool = Field(True, description="归档完成/失败推送通知")

class MagicFlowDownloaderPrefsPayload(BaseModel):
    """魔流「下载器全局参数」请求模型

    直接写入 qBittorrent 应用级偏好，会影响所有使用该下载器的插件，请谨慎调整。
    速度类字段单位 **KB/s**，0 = 不限。
    """

    download_limit_kbps: float = Field(0.0, ge=0, le=1048576, description="最大下载速度 KB/s，0 = 不限")
    upload_limit_kbps: float = Field(0.0, ge=0, le=1048576, description="最大上传速度 KB/s，0 = 不限")
    max_connec: int = Field(500, ge=0, le=100000, description="全局最大连接数")
    max_connec_per_torrent: int = Field(100, ge=0, le=100000, description="每个种子最大连接数")
    max_uploads: int = Field(50, ge=-1, le=100000, description="全局最大上传连接数，-1 = 不限")
    max_uploads_per_torrent: int = Field(10, ge=-1, le=100000, description="每个种子最大上传连接数，-1 = 不限")
    max_active_downloads: int = Field(3, ge=-1, le=100000, description="最大活动下载数，-1 = 不限")
    max_active_torrents: int = Field(5, ge=-1, le=100000, description="最大活动种子数，-1 = 不限")
    queueing_enabled: bool = Field(False, description="启用队列限制（活动数上限生效的前提）")


# 「恢复推荐值」的推荐取值（速度 KB/s）
DOWNLOADER_PREF_RECOMMENDED = {
    "download_limit_kbps": 0.0,
    "upload_limit_kbps": 0.0,
    "max_connec": 500,
    "max_connec_per_torrent": 100,
    "max_uploads": 50,
    "max_uploads_per_torrent": 10,
    "max_active_downloads": 3,
    "max_active_torrents": 5,
    "queueing_enabled": True,
}


class MagicFlowDownloaderPathsPayload(BaseModel):
    """魔流「下载目录」请求模型（写入 qBittorrent 全局路径）。"""

    save_path: str = Field("", max_length=500, description="默认保存路径")
    temp_path: str = Field("", max_length=500, description="临时下载路径")
    temp_path_enabled: bool = Field(False, description="启用临时下载路径（下载中放临时目录，完成后移入保存路径）")


class MagicFlowDefaultsPayload(BaseModel):
    """魔流「默认任务模板」请求模型（新建任务时的预填默认值）。"""

    downloader: str = Field("", max_length=80, description="默认下载器")
    save_path: str = Field("", max_length=500, description="任务保存目录（新建任务默认保存路径）")
    brush_interval: int = Field(5, ge=1, le=1440, description="选种周期（分钟）")
    check_interval: int = Field(1, ge=1, le=1440, description="检查周期（分钟）")
    max_add_per_run: int = Field(10, ge=1, le=1000, description="单轮最多新增种子数")
    max_download_concurrent: int = Field(10, ge=1, le=100, description="同时下载数上限")
    top_n: int = Field(30, ge=1, le=1000, description="每轮处理候选上限 TopN")
    browse_pages: int = Field(3, ge=1, le=50, description="每轮站点翻页数")
    seen_cooldown_hours: float = Field(24.0, ge=0, le=8760, description="候选去重冷却（小时）")
    brush_seed_days: int = Field(2, ge=0, le=365, description="默认刷流保种天数（0=按无上传判定）")
    refill_when_empty: bool = True
    reuse_existing: bool = True
    reuse_verify: bool = True
    crossseed_enabled: bool = False
    crossseed_max_per_round: int = 3
    crossseed_max_size_gb: float = 20.0
    crossseed_max_sites: int = 6
    cleanup_no_progress: bool = True
    cleanup_slow_progress: bool = True
    purge_unfree_incomplete: bool = True
    auto_resume_paused: bool = True
    delete_files: bool = True


class MagicFlowTorrentBatchPayload(BaseModel):
    """托管种子批量操作请求模型"""

    action: Literal["protect", "unprotect", "pause", "resume", "recheck", "delete"]
    hashes: List[str] = Field(default_factory=list, description="待操作的种子 infohash 列表")
