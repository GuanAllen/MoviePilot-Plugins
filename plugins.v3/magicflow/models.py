import re
from typing import Literal, Optional

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
    """魔力管家任务新增与更新请求模型"""

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
    refill_when_empty: bool = Field(True, description="清理低效种子后主动补种，保持任务做种量")
    max_add_per_run: int = Field(10, ge=1, description="单轮最多新增种子数（未设「最多保留 / 保种体积」时，每轮就按这个名额补种）")
    max_download_concurrent: int = Field(10, ge=1, le=100, description="本任务同时「下载中」上限（queued 排队不计入），复用/辅种不受此限制")
    top_n: int = Field(100, ge=1, le=1000, description="每轮参与排序处理的候选上限（TopN，超过即裁剪）")
    browse_pages: int = Field(3, ge=1, le=50, description="每轮站点列表翻页数（游标深翻，从上次游标处继续）")

    # 存量复用（辅种）：优先复用下载器/本机已有资源，避免重复下载
    reuse_existing: bool = Field(True, description="复用本机已有资源（辅种）：同 hash 直接打标签、同文件列表直接做种，不重复下载")
    reuse_verify: bool = Field(True, description="辅种前先校验已有文件；校验不通过自动撤销（避免误下载）")

    # 无进度清理：每次运行清掉「没进度」的种子（进度为 0 且停滞/出错），避免占位却不产魔力
    cleanup_no_progress: bool = Field(True, description="每次运行清理「没进度」的种子（下载进度为 0 且停滞/出错）")
    no_progress_minutes: int = Field(30, ge=1, le=1440, description="加入下载器超过该分钟数仍无进度才判定为可清理")

    # 自动恢复：被暂停的已完成种子自动重新做种（暂停 = tracker 不计做种 = 0 魔力）
    auto_resume_paused: bool = Field(True, description="自动恢复被暂停的已完成种子（重新开始做种），保证魔力产出")

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
    """魔力管家任务启停请求模型"""

    enabled: bool


class MagicFlowSettingsPayload(BaseModel):
    """魔力管家插件全局设置请求模型"""

    enabled: bool = True
    show_sidebar_nav: bool = True
