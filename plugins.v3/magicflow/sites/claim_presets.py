# -*- coding: utf-8 -*-
"""魔流 · 站点认领预设表（claim presets）。

站点差异极大（天数 / 名额上限 / 权益 / 罚则 / 接口都不同）→ 一律按站存 ``ClaimProfile``，
代码里**不出现**「7」「20」「1000」这类字面量（docs/认领.md §1）。

本表是**探测顺序**的第 3 档：

    ① 规则页文本「种子认领规则」段落解析
    ② 详情页 selector（``detail_selector``，如 ``#add-claim``）命中 → 支持
    ③ 本表（已知站整套能力，零探测）
    ④ 兜底 → ``supported=False``，不浪费请求

字段口径见 docs/认领.md §1；``endpoint`` 用**模板**描述写动作（不写死某站）：

    {"method":"POST","path":"/ajax.php",
     "body":{"action":"addClaim","params":{"torrent_id":"{id}"}}}

``{id}`` / ``{uid}`` 是唯一两个占位符。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------- 预设
# ★ 只放**已核对过**的站；宁可探测也不要写猜的。
CLAIM_PRESETS: Dict[str, Dict[str, Any]] = {
    "carpt.net": {
        "supported": True,
        "min_age_days": 7,        # 发布满 7 天可认领（rules.php 种子认领规则）
        "max_claimers": 20,       # 每颗种子最多 20 个用户认领
        "per_user_cap": 1000,     # 单用户认领总数上限（userbar「认领: [n/1000]」）
        "benefit": "bonus_x2",    # ★ 达标种子魔力奖励 = 正常值 ×2
        "benefit_desc": "达标种子魔力奖励 = 正常值 ×2",
        "penalty": {"unsatisfied": 100, "abandon": 500, "exempt_days": 30},
        "claim_page": "/claim.php?torrent_id={id}",
        "claim_list": "/claim.php?uid={uid}",
        "detail_selector": "#add-claim",
        "endpoint": {
            "method": "POST",
            "path": "/ajax.php",
            "body": {"action": "addClaim", "params": {"torrent_id": "{id}"}},
        },
    },
}


def _norm(domain: Any) -> str:
    """域名归一：小写、去协议/路径/端口/前导 www。"""
    d = str(domain or "").strip().lower()
    if not d:
        return ""
    for pre in ("https://", "http://"):
        if d.startswith(pre):
            d = d[len(pre):]
    d = d.split("/")[0].split("?")[0]
    if ":" in d:
        d = d.split(":")[0]
    return d[4:] if d.startswith("www.") else d


def preset_for(domain: Any) -> Optional[Dict[str, Any]]:
    """按域名取预设（命中返回**副本**，调用方可安全改写）。"""
    d = _norm(domain)
    if not d:
        return None
    if d in CLAIM_PRESETS:
        return dict(CLAIM_PRESETS[d])
    for key, val in CLAIM_PRESETS.items():
        if d.endswith("." + key) or key.endswith("." + d):
            return dict(val)
    return None
