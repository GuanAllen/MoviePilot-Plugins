import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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

    # 任务目标：达到后任务自动停止（bonus=站点魔力值；brush=站点上传量 GB）
    goal_value: Optional[float] = Field(None, ge=0, description="任务目标：bonus=站点魔力值达到多少；brush=站点上传量（GB）。达到后任务自动停止；留空=未设目标（前端会提醒）")

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

    # 界面
    compact_mode: bool = False

    # IYUU 云端辅种（可选）：Token 留空 = 不启用，退回内置跨站复用
    iyuu_token: str = Field("", max_length=200, description="IYUU 云端 Token，留空 = 不启用 IYUU 辅种")
    iyuu_sites: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="站点密钥表：domain -> {passkey/uid/downhash...}（用户手填，优先于自动获取）",
    )


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
    cleanup_no_progress: bool = True
    cleanup_slow_progress: bool = True
    purge_unfree_incomplete: bool = True
    auto_resume_paused: bool = True
    delete_files: bool = True


class MagicFlowTorrentBatchPayload(BaseModel):
    """托管种子批量操作请求模型"""

    action: Literal["protect", "unprotect", "pause", "resume", "recheck", "delete"]
    hashes: List[str] = Field(default_factory=list, description="待操作的种子 infohash 列表")
