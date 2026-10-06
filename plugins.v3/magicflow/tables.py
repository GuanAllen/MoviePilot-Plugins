"""魔流 · 身份枚举（12.0.0 起 tables.py 只保留身份真值源）

12.0.0 口径（Master 定）：**表是唯一真值源**，账本链（kv 账本 + 一次性迁移层）一根毛不留。
本模块曾经的「schema_v5 按行存进 ``save_data``」整套表结构描述（行键 / 字段清单 /
老键→新表映射 / 迁移辅助函数）随 ``features/migrate.py`` 一次性迁移模块一并退役——
迁移三戳已在生产落定、``migrate_pending()`` 恒 False，属死代码。

本模块只保留**身份枚举** ``DEFAULT_IDENTITIES``：
- 它是 ``features/agentledger.py`` 的离线兜底真值源（``mf_identity`` 空表时回退）；
- 也是新装库灌 ``mf_identity`` 表的种子（见 ``features/core.py`` init 的幂等播种 ``_seed_identities``）。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

# 身份枚举（硬编码字面量，收敛到 mf_identity 表）
IDENT_NEW = "新"          # 新来观察期
IDENT_RESOURCE = "资源"   # 合格资源（推荐认证 / 辅种落户）
IDENT_PLAIN = "普通"      # 普通存量

DEFAULT_IDENTITIES: Tuple[Dict[str, Any], ...] = (
    {"code": IDENT_NEW, "is_asset": False, "need_observe": True, "can_cleanup": True, "order": 1, "label": "新"},
    {"code": IDENT_RESOURCE, "is_asset": True, "need_observe": False, "can_cleanup": False, "order": 0, "label": "资源"},
    {"code": IDENT_PLAIN, "is_asset": False, "need_observe": False, "can_cleanup": True, "order": 2, "label": "普通"},
)
