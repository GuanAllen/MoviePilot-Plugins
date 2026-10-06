# -*- coding: utf-8 -*-
"""魔流 · 5 张自有表（MP 官方插件数据库）

设计（Master 2026-09-30 16:51 定稿）：用 MP 官方 `get_database_models()` 建**插件专属库**，
不再把账本塞进 ``plugindata`` 的 kv 行。

    mf_site      站点表
    mf_seed      种子表（很薄：只做关联）
    mf_resource  资源表（中心：身份 + H&R + 体积）
    mf_identity  身份表
    mf_task      任务表（任务类型 / 任务状态）
    mf_deck      满魔套牌存档表（§5.2）

- 模型基类由 ``plugin_declarative_base()`` 产出：插件热重载会重新执行本模块 → 每次拿到
  干净的 ``MetaData``，不会重复定义表；
- 表由 MP 在插件启动时一并建立（我们声明了 migrations 目录时才会改走 alembic，这里不用）；
- 所有 JSON 列走 SQLAlchemy ``JSON``（sqlite/postgres 通吃）。
"""

from __future__ import annotations

from typing import Any, List

from sqlalchemy import JSON as _JSON
from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

try:  # 生产：走 MP 官方声明式基类（独立 MetaData）
    from app.sdk.database import plugin_declarative_base
except Exception:  # noqa: BLE001  # 本地/离线（无 app.*）时退化为标准基类，便于单测
    from sqlalchemy.orm import DeclarativeBase as _DeclarativeBase

    def plugin_declarative_base():  # type: ignore[misc]
        return _DeclarativeBase

Base = plugin_declarative_base()


class SiteRow(Base):
    """站点表。运维/证据链字段一并落在这里（原来散在 site_rules/site_caps/pv_*/bday*）。"""

    __tablename__ = "mf_site"

    site_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120))
    domain: Mapped[str | None] = mapped_column(String(200), index=True)
    domains: Mapped[Any | None] = mapped_column(_JSON, default=list)      # 别名
    mp_site_id: Mapped[int | None] = mapped_column(Integer)
    iyuu_sid: Mapped[int | None] = mapped_column(Integer)
    base_url: Mapped[str | None] = mapped_column(String(300))
    is_https: Mapped[bool | None] = mapped_column(Boolean)
    tz_offset: Mapped[float | None] = mapped_column(Float)
    # 取种
    framework: Mapped[str | None] = mapped_column(String(40))
    api_channel: Mapped[str | None] = mapped_column(String(40))
    credential: Mapped[Any | None] = mapped_column(_JSON, default=dict)    # 口令/apikey/cookie(密文)
    # 站点规则
    hr: Mapped[bool | None] = mapped_column(Boolean)
    hr_src: Mapped[str | None] = mapped_column(String(40))
    seed_hours: Mapped[float | None] = mapped_column(Float)
    seed_hours_retired: Mapped[float | None] = mapped_column(Float)
    seed_need_hours: Mapped[float | None] = mapped_column(Float)
    seed_cap: Mapped[int | None] = mapped_column(Integer)
    seed_window_hours: Mapped[float | None] = mapped_column(Float)
    exam_avg_hours: Mapped[float | None] = mapped_column(Float)
    # 免费规则
    free_over_gb: Mapped[float | None] = mapped_column(Float)
    free_original: Mapped[bool | None] = mapped_column(Boolean)
    free_ep1: Mapped[bool | None] = mapped_column(Boolean)
    free_index: Mapped[bool | None] = mapped_column(Boolean)
    free_spstates: Mapped[Any | None] = mapped_column(_JSON, default=list)
    promo_in_list: Mapped[bool | None] = mapped_column(Boolean)
    page_param: Mapped[str | None] = mapped_column(String(40))
    # 魔力公式参数
    t0: Mapped[float | None] = mapped_column(Float)
    n0: Mapped[int | None] = mapped_column(Integer)
    b0: Mapped[float | None] = mapped_column(Float)
    l: Mapped[float | None] = mapped_column(Float)
    zero_weight: Mapped[float | None] = mapped_column(Float)
    normal_weight: Mapped[float | None] = mapped_column(Float)
    official_coef: Mapped[float | None] = mapped_column(Float)
    harem_coef: Mapped[float | None] = mapped_column(Float)
    per_torrent_flat: Mapped[float | None] = mapped_column(Float)
    seeding_count_cap: Mapped[int | None] = mapped_column(Integer)
    # 运维
    pv_budget: Mapped[int | None] = mapped_column(Integer)
    pv_usage: Mapped[Any | None] = mapped_column(_JSON, default=dict)
    pv_block: Mapped[float | None] = mapped_column(Float)
    bday: Mapped[str | None] = mapped_column(String(20))
    signin: Mapped[Any | None] = mapped_column(_JSON, default=dict)
    alerts: Mapped[Any | None] = mapped_column(_JSON, default=dict)
    # 证据链
    source: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[str | None] = mapped_column(String(20))
    evidence: Mapped[str | None] = mapped_column(Text)
    probed_at: Mapped[float | None] = mapped_column(Float)
    probe_ver: Mapped[int | None] = mapped_column(Integer)
    rule_url: Mapped[str | None] = mapped_column(String(300))
    rule_label: Mapped[str | None] = mapped_column(String(200))
    rule_src: Mapped[str | None] = mapped_column(String(200))
    rule_mail_id: Mapped[str | None] = mapped_column(String(80))
    rule_mail_subject: Mapped[str | None] = mapped_column(String(300))
    # ★ 12.1.0 WS2：site_rules kv → mf_site 真列（新增 3 列 + 兜底 JSON）
    note: Mapped[str | None] = mapped_column(Text)
    exam_evidence: Mapped[str | None] = mapped_column(Text)
    per_torrent_hr: Mapped[bool | None] = mapped_column(Boolean)
    rules_extra: Mapped[Any | None] = mapped_column(_JSON, default=dict)  # 映射后仍未覆盖的键（防丢字段）
    caps: Mapped[Any | None] = mapped_column(_JSON, default=dict)         # site_caps 探测缓存（整条 rec）
    created: Mapped[float | None] = mapped_column(Float)
    updated: Mapped[float | None] = mapped_column(Float)


class CrossSeedRow(Base):
    """跨站来源份（他站那份）的 H&R 保种保护账本表（★ 12.1.0 WS2）。

    原来持久化在 plugindata kv ``crossseed_sources``；12.1.0 起并入表（唯一真值源）。
    不复用 ``mf_seed``（避免「来源份」被当成种子账本成员 → 污染静默池/审计）。
    """

    __tablename__ = "mf_crossseed"

    sib_hash: Mapped[str] = mapped_column(String(64), primary_key=True)   # 他站那份的 infohash
    site_b_domain: Mapped[str | None] = mapped_column(String(200), index=True)  # 来源站域名
    site_a: Mapped[str | None] = mapped_column(String(40))          # 目标站名
    site_b: Mapped[str | None] = mapped_column(String(40))          # 来源站名
    a_hash: Mapped[str | None] = mapped_column(String(64))          # 目标站那份 hash
    title: Mapped[str | None] = mapped_column(String(400))
    size_gb: Mapped[float | None] = mapped_column(Float)
    hit_and_run: Mapped[bool | None] = mapped_column(Boolean)
    hours: Mapped[float | None] = mapped_column(Float)
    seed_until: Mapped[float | None] = mapped_column(Float)
    downloader: Mapped[str | None] = mapped_column(String(80))
    seeded_sec: Mapped[float | None] = mapped_column(Float)
    files_shared: Mapped[bool | None] = mapped_column(Boolean)
    task_id: Mapped[str | None] = mapped_column(String(64))
    task_name: Mapped[str | None] = mapped_column(String(200))
    backfilled: Mapped[bool | None] = mapped_column(Boolean)
    done: Mapped[bool | None] = mapped_column(Boolean)
    extra: Mapped[Any | None] = mapped_column(_JSON, default=dict)   # 映射后仍未覆盖的键（resource_id/need_hours/pool 等）
    created: Mapped[float | None] = mapped_column(Float)
    updated: Mapped[float | None] = mapped_column(Float)


class ResourceRow(Base):
    """资源表（中心）：身份唯一、H&R 唯一、体积唯一。"""

    __tablename__ = "mf_resource"

    resource_id: Mapped[str] = mapped_column(String(64), primary_key=True)   # 文件特征码
    size_gb: Mapped[float | None] = mapped_column(Float)
    files_shared: Mapped[bool | None] = mapped_column(Boolean)
    source_site_id: Mapped[int | None] = mapped_column(Integer, index=True)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    identity: Mapped[str | None] = mapped_column(String(20), index=True)
    identity_at: Mapped[float | None] = mapped_column(Float)
    identity_by: Mapped[str | None] = mapped_column(String(40))
    hrs: Mapped[Any | None] = mapped_column(_JSON, default=list)   # 变长集合：保持 JSON
    grouped: Mapped[bool | None] = mapped_column(Boolean, default=False)  # 是否「下完成组」（账本口径的资源）
    source_site_name: Mapped[str | None] = mapped_column(String(120))     # 站点关联不上时的兜底（原 extra）
    # --- 入库真列（6.1.0 由 library 收敛）---
    in_library: Mapped[bool | None] = mapped_column(Boolean)
    lib_first_at: Mapped[float | None] = mapped_column(Float)
    lib_updated: Mapped[float | None] = mapped_column(Float)
    lib_path: Mapped[str | None] = mapped_column(String(500))
    lib_media_id: Mapped[str | None] = mapped_column(String(64))
    # --- 评分（豆瓣，活列）---
    rating: Mapped[float | None] = mapped_column(Float)
    # --- 推荐复核结论（★ 12.0.0 由幽灵字段转真列：随资源记，重启不丢）---
    #    旧写法只 put 进种子内存 rec（seed_row 不落它）→ 重启即丢。
    asset_recheck: Mapped[str | None] = mapped_column(String(20))
    asset_recheck_at: Mapped[float | None] = mapped_column(Float)
    created: Mapped[float | None] = mapped_column(Float)
    updated: Mapped[float | None] = mapped_column(Float)


class SeedRow(Base):
    """种子表（很薄）：只做关联；身份/H&R/体积全顺 resource_id 查。"""

    __tablename__ = "mf_seed"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[int | None] = mapped_column(Integer, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), index=True)   # 空 = 静默（不在岗）
    published_at: Mapped[float | None] = mapped_column(Float)             # 站点口径发布时间
    vfy_miss: Mapped[int] = mapped_column(Integer, default=0)             # 巡检连续未命中
    # ★ 7.0.0 标签退役：之前 6.1.0 的台账/组员/影子真列（state/title/reason/asset/taken_*/verify_*/
    #   crossseed/downloader/ts/created/in_group/m_*/mmbr/rt）统一退役 → 状态走 resource.identity，
    #   体积/H&R 走 resource，发布进度/算职/状态走下载器实况。老库残留列 ORM 不声明 → 不 SELECT，
    #   无害（需清理跑 tools/cleanup_legacy_ledger.py）。
    updated: Mapped[float | None] = mapped_column(Float)


class IdentityRow(Base):
    """身份表：新 / 资源 / 普通（现为硬编码字面量，收敛到这张表）。"""

    __tablename__ = "mf_identity"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    is_asset: Mapped[bool] = mapped_column(Boolean, default=False)     # 是不是「合格资源」
    need_observe: Mapped[bool] = mapped_column(Boolean, default=False)  # 要不要走观察期
    can_cleanup: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str | None] = mapped_column(String(40))


class TaskRow(Base):
    """任务表：核心列 + 其余参数进 ``params`` JSON（字段太多且常变）。"""

    __tablename__ = "mf_task"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120))
    site_id: Mapped[int | None] = mapped_column(Integer, index=True)
    task_type: Mapped[str | None] = mapped_column(String(20))       # bonus | brush
    run_mode: Mapped[str | None] = mapped_column(String(20))        # running | seeding | stopped
    enabled: Mapped[bool | None] = mapped_column(Boolean)
    downloader: Mapped[str | None] = mapped_column(String(80))
    brush_tag: Mapped[str | None] = mapped_column(String(60))
    save_path: Mapped[str | None] = mapped_column(String(500))
    params: Mapped[Any | None] = mapped_column(_JSON, default=dict)        # 其余全部任务参数
    updated: Mapped[float | None] = mapped_column(Float)


class DeckRow(Base):
    """满魔套牌存档表（§5.2）：一套牌 = 同 ``deck_id`` 的所有行；**单位是「种子」(hash)**。

    生命周期：打磨期表在动（换种增删行）→ 满魔期冻结打标记（``frozen``）→ 复用期开任务读表、
    按种子 hash 重新标职务（零下载、零重排）。主键 ``(deck_id, seed_id)``。
    """

    __tablename__ = "mf_deck"

    deck_id: Mapped[str] = mapped_column(String(80), primary_key=True)       # 套牌标识（同站同类型可存多套版本）
    seed_id: Mapped[str] = mapped_column(String(64), primary_key=True)       # 牌 = 种子 hash
    site_id: Mapped[int | None] = mapped_column(Integer, index=True)         # 这套牌给哪个站用
    task_type_id: Mapped[str | None] = mapped_column(String(20), index=True)  # bonus | brush
    task_id: Mapped[str | None] = mapped_column(String(64), index=True)      # 哪个任务打出来的
    a_contrib: Mapped[float | None] = mapped_column(Float)                   # 该牌的 A 贡献（复查用）
    size_gb: Mapped[float | None] = mapped_column(Float)
    frozen: Mapped[bool | None] = mapped_column(Boolean, default=False)      # 满魔期冻结标记
    frozen_at: Mapped[float | None] = mapped_column(Float)
    created: Mapped[float | None] = mapped_column(Float)
    updated: Mapped[float | None] = mapped_column(Float)


ALL_MODELS: List[type] = [SiteRow, ResourceRow, SeedRow, IdentityRow, TaskRow, DeckRow, CrossSeedRow]
