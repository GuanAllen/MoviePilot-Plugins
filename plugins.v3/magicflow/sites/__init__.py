# -*- coding: utf-8 -*-
"""
站点魔力**公式参数**预设（供 ``features/formula.py`` 用）。

★ 12.0.0 淘汰：原「魔力计算器」抽象基类（``BonusCalculator`` ABC）、HDFans 计算器
（``sites/hdfans.py``）、``_CALCULATORS`` / ``get_calculator`` / ``register_default_calculators``
整条链路 **0 消费者**（魔力计算真值源早已是 ``bonus.py`` 的 ``TorrentBonusInfo`` /
``BonusParams`` / 公式函数），已整体删除，避免「翻到旧代码又按旧架构扩容」。

本模块只保留：站点级公式参数预设 + 解析函数。
"""

from typing import Any, Dict, Optional

# 顶层导入（不在函数体内懒导入）：worker 运行时不再触发 import 机制，
# 避免热重载期间与 loader 形成「循环导入死锁」。
from ..bonus import BonusParams


# ============================================================
# 站点魔力公式参数（NexusPHP 标准式可调项）
# ============================================================

# 站点级公式参数预设：键为域名关键字（小写）或站点 schema。
# 未命中时使用 NexusPHP 标准公式；可用 register_formula_preset 扩展。
_FORMULA_PRESETS: Dict[str, Dict[str, Any]] = {}


def register_formula_preset(key: str, **params: Any) -> None:
    """注册/覆盖站点级公式参数预设（t0/n0/b0/l/zero_weight/normal_weight）。"""
    _FORMULA_PRESETS[str(key).strip().lower()] = dict(params)


def get_formula_params(domain: Optional[str] = None, schema: Optional[str] = None):
    """
    解析站点对应的魔力公式参数。

    命中顺序：域名关键字 → 站点类型 → NexusPHP 标准默认。
    返回对象可继续用 .merged(**overrides) 叠加任务级覆盖。
    """
    for key in (domain, schema):
        if not key:
            continue
        lowered = str(key).strip().lower()
        if lowered in _FORMULA_PRESETS:
            return BonusParams(**_FORMULA_PRESETS[lowered])
    return BonusParams()
