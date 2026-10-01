"""魔流 5 表结构定义（目标版本 6.0.0）

设计定稿（Master 2026-09-30 16:1x~16:3x）：
    站点表 site / 种子表 seed / 资源表 resource / 身份表 identity / 任务表 task

**物理落点**：仍是 MP 插件账本 ``save_data``，但**按行存**（不再整包读写）：

    site:<site_id>        站点一行
    seed:<hash>           种子一行
    res:<resource_id>     资源一行（resource_id = 文件特征码）
    ident:<code>          身份一行
    task:<task_id>        任务一行

本模块只描述「表 / 字段 / 行键 / 老键→新表映射」，**不含业务逻辑**，
供迁移 worker 与后续读写层共同引用。老键在新表落地后仍保留，由未来版本清理。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

# ---------------------------------------------------------------- 版本 / 标记

SCHEMA_VERSION = "5"                      # 账本结构世代（与插件版本号无关）
MARKER_KEY = "schema_v5_done"             # 迁移完成戳（存在即不再迁移）
CURSOR_KEY = "schema_v5_cursor"           # 迁移游标（断点续跑）
BACKUP_PREFIX = "schema_v5_backup:"       # 迁移前旧键原样备份

# ---------------------------------------------------------------- 表名 / 行键

TABLE_SITE = "site"
TABLE_SEED = "seed"
TABLE_RESOURCE = "res"
TABLE_IDENTITY = "ident"
TABLE_TASK = "task"

TABLES: Tuple[str, ...] = (TABLE_SITE, TABLE_SEED, TABLE_RESOURCE, TABLE_IDENTITY, TABLE_TASK)
_PREFIX: Dict[str, str] = {
    TABLE_SITE: "site:",
    TABLE_SEED: "seed:",
    TABLE_RESOURCE: "res:",
    TABLE_IDENTITY: "ident:",
    TABLE_TASK: "task:",
}


def row_key(table: str, pk: Any) -> str:
    """行键：``<前缀><主键>``。"""
    pfx = _PREFIX.get(table)
    if not pfx:
        raise ValueError(f"未知表: {table}")
    return f"{pfx}{pk}"


def row_prefix(table: str) -> str:
    return _PREFIX[table]


# ---------------------------------------------------------------- 字段（真值源）

# 站点表：接入 / 取种 / 规则 / 免费 / 魔力参数 / 运维 / 证据链
SITE_FIELDS: Tuple[str, ...] = (
    # 接入
    "name", "domain", "domains", "mp_site_id", "iyuu_sid", "base_url", "is_https",
    # 取种
    "framework", "api_channel", "credential", "tz_offset",
    # 规则
    "hr", "hr_src", "seed_hours", "seed_hours_retired", "seed_need_hours",
    "seed_cap", "seed_window_hours", "exam_avg_hours",
    # 免费
    "free_over_gb", "free_original", "free_ep1", "free_index", "free_spstates",
    "promo_in_list", "page_param",
    # 魔力参数（BonusParams）
    "t0", "n0", "b0", "l", "zero_weight", "normal_weight", "official_coef",
    "harem_coef", "per_torrent_flat", "seeding_count_cap",
    # 运维
    "pv_budget", "pv_usage", "pv_block", "bday", "signin", "alerts",
    # 证据链
    "source", "confidence", "evidence", "probed_at", "probe_ver",
    "rule_url", "rule_label", "rule_src", "rule_mail_id", "rule_mail_subject",
)

# 种子表：**很薄** —— 只留「这一站的这颗种」的关联与站点口径字段
SEED_FIELDS: Tuple[str, ...] = (
    "site_id",        # FK -> site
    "resource_id",    # FK -> res（身份 / H&R / 体积 全顺这里查）
    "task_id",        # FK -> task；空 = 静默（不在岗）
    "published_at",   # 站点口径发布时间（Ti=publish 用）
    "vfy_miss",       # 巡检连续未命中计数（运维小字段）
)
# ★ 不落库：体积（→ res）/ 进度·标题·状态·做种时长·上传量（下载器实况）
#           / 身份（→ res）/ H&R（→ res）/ 占用 taken_by·lease_until（删）

# 资源表：中心表
RESOURCE_FIELDS: Tuple[str, ...] = (
    "size_gb", "files_shared",
    "source_site_id", "source_hash",       # H&R 账单归属（来源站/来源种）
    "identity", "identity_at", "identity_by",
    "hrs",                                 # 列表：[{site_id,hash,required_hours,settled,settled_at,checked_at}]
    "library",                             # {in_library, media_id, path, first_at, updated}
    "rating", "created", "updated",
)
# ★ 不再内嵌 members：成员由种子表反查 resource_id
# ★ 欠时 = required_hours - seed_time_hours(hrs[].hash 在 hrs[].site_id 上的实况)

# 身份表
IDENTITY_FIELDS: Tuple[str, ...] = (
    "code", "is_asset", "need_observe", "can_cleanup", "order", "label",
)

# 身份枚举（现为硬编码字面量，收敛到这张表）
IDENT_NEW = "新"          # 新来观察期
IDENT_RESOURCE = "资源"   # 合格资源（推荐认证 / 辅种落户）
IDENT_PLAIN = "普通"      # 普通存量
DEFAULT_IDENTITIES: Tuple[Dict[str, Any], ...] = (
    {"code": IDENT_NEW, "is_asset": False, "need_observe": True, "can_cleanup": True, "order": 1, "label": "新"},
    {"code": IDENT_RESOURCE, "is_asset": True, "need_observe": False, "can_cleanup": False, "order": 0, "label": "资源"},
    {"code": IDENT_PLAIN, "is_asset": False, "need_observe": False, "can_cleanup": True, "order": 2, "label": "普通"},
)

# 任务表：字段 = models.MagicFlowTaskPayload（原样）+ 运行状态列
TASK_EXTRA_FIELDS: Tuple[str, ...] = ("run_mode",)   # 状态：running / seeding / stopped
# ★ 限速按「任务类型」给：task_type=brush -> 刷流档(5120)，否则 挂种档(200)

# ---------------------------------------------------------------- 老键 → 新表

# 老单键（整包）→ 需要拆成的表
MIGRATION_SOURCES: Tuple[str, ...] = (
    "tag_state",      # 种子表 + 资源表补丁
    "tag_groups",     # 资源表 + 种子表补丁
    "site_rules",     # 站点表
    "site_caps",      # 站点表
    "crossseed_sources",  # 资源表 H&R / 来源
)

# 散在各处、但语义属于站点表的运维键（值按 site_id 或域名做子键）
SITE_SCOPED_KEYS: Tuple[str, ...] = (
    "pv_usage", "pv_budget", "live_pv_block", "live_alerts", "collect_day", "signin_records",
)

# 上线后应删的死键（迁移时可原样备份，不搬运）
DEAD_KEYS: Tuple[str, ...] = (
    "tag_state_snapshot", "live_samples",
)

# 老种子记录里**属于资源表**的字段（老键 → 新表字段）
SEED_TO_RESOURCE: Dict[str, str] = {
    "fp": "resource_id",
    "size_gb": "size_gb",
    "origin": "identity",        # 旧「身份」来源（资源）
    "origin_sub": "identity",    # 旧名兼容
    "sub": "identity",           # 5.0.0 起的身份（资源唯一）
    "asset": "identity",         # 库内资产 = 身份「资源」
}
# 老种子记录里**属于种子表**的字段
SEED_TO_SEED: Dict[str, str] = {
    "site": "site_id",
    "task": "task_id",
    "state": "_duty_derived",    # 职务由 task 派生，不落种子表
    "taken_by": "_drop",         # 占用：删
    "lease_until": "_drop",
    "title": "_drop",            # 实况（下载器给）
    "downloader": "_drop",
    "progress": "_drop",
}
# 老记录里直接丢弃的字段（实况 / 占用 / 死字段）
DROP_FIELDS: Tuple[str, ...] = (
    "taken_by", "taken_at", "lease_until", "title", "downloader", "progress",
    "origin_state", "migrated", "mp_promoted_at", "rehomed_at",
    "magicized", "magicized_at", "asset_recheck", "asset_recheck_at",
    "miss", "verify_at", "verify_n", "reason", "ts", "free", "approx", "rating",
)


# ---------------------------------------------------------------- 辅助

def new_site_row(**kw: Any) -> Dict[str, Any]:
    return {k: kw.get(k) for k in SITE_FIELDS if k in kw}


def new_seed_row(**kw: Any) -> Dict[str, Any]:
    return {k: kw.get(k) for k in SEED_FIELDS if k in kw}


def new_resource_row(**kw: Any) -> Dict[str, Any]:
    return {k: kw.get(k) for k in RESOURCE_FIELDS if k in kw}


def new_identity_row(**kw: Any) -> Dict[str, Any]:
    return {k: kw.get(k) for k in IDENTITY_FIELDS if k in kw}


def split_legacy_seed(rec: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """老 ``tag_state[hash]`` 记录 → ``(seed_patch, resource_patch)``。

    只做字段归位，不做业务判断；主键由调用方补。
    """
    seed: Dict[str, Any] = {}
    res: Dict[str, Any] = {}
    for old_key, value in (rec or {}).items():
        if old_key in DROP_FIELDS:
            continue
        if old_key in SEED_TO_RESOURCE:
            tgt = SEED_TO_RESOURCE[old_key]
            if tgt != "_drop":
                res.setdefault(tgt, value)
            continue
        if old_key in SEED_TO_SEED:
            tgt = SEED_TO_SEED[old_key]
            if not tgt.startswith("_"):
                seed.setdefault(tgt, value)
            continue
        # 站点口径字段（发布时间等）留在种子表
        if old_key == "published_at":
            seed["published_at"] = value
    return seed, res


def iter_tables() -> Iterable[str]:
    return TABLES


def field_names(table: str) -> List[str]:
    return {
        TABLE_SITE: list(SITE_FIELDS),
        TABLE_SEED: list(SEED_FIELDS),
        TABLE_RESOURCE: list(RESOURCE_FIELDS),
        TABLE_IDENTITY: list(IDENTITY_FIELDS),
        TABLE_TASK: [],  # 见 models.MagicFlowTaskPayload + TASK_EXTRA_FIELDS
    }[table]
