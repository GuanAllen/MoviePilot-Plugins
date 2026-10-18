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

# 同族「种子认领」插件的统一写入口（2026-10-18 逐站实测：详情页 #add-claim +
# 前端 jQuery.post("/ajax.php", {action:"addClaim", params:{torrent_id:N}})）。
_CLAIM_PLUGIN_ENDPOINT: Dict[str, Any] = {
    "method": "POST",
    "path": "/ajax.php",
    "body": {"action": "addClaim", "params": {"torrent_id": "{id}"}},
}


def _nexus_claim_preset(
    per_user_cap: int,
    *,
    min_age_days: int = 7,
    max_claimers: int = 10,
    target_seed_hours: int = 500,
    target_upload_ratio: int = 5,
    penalty_unsatisfied: int = 0,
    penalty_abandon: int = 0,
    exempt_days: int = 30,
    verified: bool = False,
    benefit_desc: str = "达标种子魔力奖励 = 正常值 ×2",
    claim_page: str = "/claim.php?torrent_id={id}",
    claim_list: str = "/claim.php?uid={uid}",
    detail_selector: str = "#add-claim",
    note: str = "",
) -> Dict[str, Any]:
    """同族认领插件的一站一套能力（``verified=False`` = 站点规则页没公布数值）。

    ★ 未核对的站用**同族插件默认值**（7 天 / 每颗 10 人 / 达标 500h 或 ×5）；
      这些数字只影响扫描展示与排序，真写时站点侧仍会按自己的规则校验，
      UI 会按 ``rules_unverified`` 标「规则未核对」（docs/认领.md §2）——
      **绝不把猜的值当成已核对**。
    """
    return {
        "supported": True,
        "min_age_days": int(min_age_days),
        "max_claimers": int(max_claimers),
        "per_user_cap": int(per_user_cap),
        "benefit": "bonus_x2",
        "benefit_desc": benefit_desc,
        "penalty": {
            "unsatisfied": int(penalty_unsatisfied),
            "abandon": int(penalty_abandon),
            "exempt_days": int(exempt_days),
        },
        "settlement": {
            "cycle": "natural_month",
            "cycle_text": "每月结算（自然月）",
            "target_seed_hours": int(target_seed_hours),
            "target_upload_ratio": int(target_upload_ratio),
            "payout_hours": 720,
            "payout_multiplier": 2,
        },
        "claim_page": claim_page,
        "claim_list": claim_list,
        "detail_selector": detail_selector,
        "endpoint": dict(_CLAIM_PLUGIN_ENDPOINT),
        "rules_unverified": not bool(verified),
        "rules_note": note or (
            "站点已公布认领规则（2026-10-18 核对）"
            if verified
            else "站点规则页未公布数值：本表为同族插件默认值，真写前需逐站核对"
        ),
    }

CLAIM_PRESETS: Dict[str, Dict[str, Any]] = {
    "carpt.net": {
        "supported": True,
        "min_age_days": 7,        # 发布满 7 天可认领（rules.php 种子认领规则）
        "max_claimers": 20,       # 每颗种子最多 20 个用户认领
        "per_user_cap": 1000,     # 单用户认领总数上限（userbar「认领: [n/1000]」）
        "benefit": "bonus_x2",    # ★ 达标种子魔力奖励 = 正常值 ×2
        "benefit_desc": "达标种子魔力奖励 = 正常值 ×2",
        "penalty": {"unsatisfied": 100, "abandon": 500, "exempt_days": 30},
        # ★ 结算口径（2026-10-17 抓 rules.php「种子认领规则」原文核对）：
        #   达标标准 = 每月做种 ≥300 小时，或上传量 ≥ 体积 ×5；
        #   魔力奖励 = 达标种子时魔 × (达标种子总做种小时数 / 达标种子数) × 倍数（×2）——按自然月结算。
        "settlement": {
            "cycle": "natural_month",
            "cycle_text": "每月结算（自然月）",
            "target_seed_hours": 300,
            "target_upload_ratio": 5,
            "payout_hours": 720,        # 满月 = 30 天 × 24h，用于「满月预计」
            "payout_multiplier": 2,
        },
        "claim_page": "/claim.php?torrent_id={id}",
        "claim_list": "/claim.php?uid={uid}",
        "detail_selector": "#add-claim",
        "endpoint": {
            "method": "POST",
            "path": "/ajax.php",
            "body": {"action": "addClaim", "params": {"torrent_id": "{id}"}},
        },
        "rules_unverified": False,
        "rules_note": "CARPT rules.php「种子认领规则」已核对（2026-10-17）",
    },
    # ---- 2026-10-18「其他站点纳入」：同族 NexusPHP 认领插件（详情页 #add-claim）
    "ptcafe.club": _nexus_claim_preset(
        3000, min_age_days=7, max_claimers=10, target_seed_hours=500,
        target_upload_ratio=10, penalty_unsatisfied=3000, penalty_abandon=1000,
        verified=True, benefit_desc="达标种子魔力奖励 = 正常值 ×2（规则页「认领规则」）",
        note="咖啡 rules.php：7 天 / 每颗 10 人 / 达标 500h 或 上传×10 / 首月未达标免罚",
    ),
    "dstudio.me": _nexus_claim_preset(
        500, min_age_days=7, max_claimers=30, target_seed_hours=500,
        target_upload_ratio=5, penalty_unsatisfied=1000, penalty_abandon=200,
        verified=True, benefit_desc="达标种子魔力奖励 = 正常值 ×2（规则 §13）",
        note="Depth Studio 规则 §13：7 天 / 每颗 30 人 / 单用户 500 / 达标 500h 或 ×5",
    ),
    "cyanbug.net": _nexus_claim_preset(
        1000, note="大青虫：用户上限 1000（userbar 认领 [0/1000]）；规则页未公布数值"),
    "hdtime.org": _nexus_claim_preset(
        1000, note="高清时间：用户上限 1000（userbar）；规则页未公布数值"),
    "pt.soulvoice.club": _nexus_claim_preset(
        1000, note="聆音：用户上限 1000（userbar）；规则页未公布数值"),
    "duckboobee.org": _nexus_claim_preset(
        1000, note="March：用户上限 1000（userbar）；规则页未公布数值"),
    "novahd.top": _nexus_claim_preset(
        2000, note="NovaHD：用户上限 2000（userbar）；规则页未公布数值"),
    "crabpt.vip": _nexus_claim_preset(
        2000, note="蟹黄堡：用户上限 2000（userbar）；规则页未公布数值"),
    "cspt.top": _nexus_claim_preset(
        1000, benefit_desc="达标种子魔力奖励 = 正常值 ×2（以站点「预计奖励」为准）",
        note="财神：用户上限 1000（userbar）；claim 页显示自然月结算，规则页未公布数值"),
    "pt.btschool.club": _nexus_claim_preset(
        0, claim_page="/torrents.php", claim_list="/viewclaims.php",
        benefit_desc="站点按自然月结算发放（认领页显示 500 魔力/种）",
        note="学校：viewclaims.php 有「下次结账/获得魔力值」；认领接口按同族 ajax.php 推断"),
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
