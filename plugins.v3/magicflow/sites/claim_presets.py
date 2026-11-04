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

``{id}`` / ``{uid}`` / ``{claim_id}`` 是全部占位符（``{claim_id}`` 只用于放弃认领：
站点 JS 是 ``params.id = data-claim_id``，即**认领记录 id**，不是种子 id）。
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

# ★ 19.10.58「放弃认领」：同族插件的反向动作，**参数完全不同**。
#
#   站点前端 js/nexus.js 原文（2026-10-31 抓 ptcafe.club/js/nexus.js）：
#       let claimId = _this.attr("data-claim_id");          // 认领记录 id
#       if (claimId > 0) { params.id = claimId }
#       else { params.torrent_id = torrentId }
#       jQuery.post("ajax.php", {"action": action, params: params})
#   按钮 data-action="removeClaim" + data-confirm="确认要放弃认领？"
#   → 放弃传的是 **claim_id**（认领页 ID 列，如咖啡 147033），不是 torrent_id。
#
#   2026-10-31 逐站探测（POST action=removeClaim, params[id]=999999999：
#   站点回 `{"ret":-1,"msg":"No query results for model [App\\Models\\Claim] 999999999"}`
#   = 动作存在、参数名正确、无副作用）：咖啡 / CARPT / 大青虫 / 高清时间 / 财神 /
#   March / NovaHD / 蟹黄堡 / Depth Studio 共 9 站一致。
#   聆音与学校**未核对**（探测时代理 502）→ 这两站显式传 None，不提供放弃。
_CLAIM_PLUGIN_ABANDON: Dict[str, Any] = {
    "method": "POST",
    "path": "/ajax.php",
    "body": {"action": "removeClaim", "params": {"id": "{claim_id}"}},
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
    claim_entry: str = "/userdetails.php?id={uid}",
    detail_selector: str = "#add-claim",
    endpoint: Optional[Dict[str, Any]] = None,
    abandon_endpoint: Optional[Dict[str, Any]] = _CLAIM_PLUGIN_ABANDON,
    reward_min_age_days: int = 0,
    reward_min_size_gb: float = 0.0,
    note: str = "",
) -> Dict[str, Any]:
    """同族认领插件的一站一套能力（``verified=False`` = 站点规则页没公布数值）。

    ★ 未核对的站用**同族插件默认值**（7 天 / 每颗 10 人 / 达标 500h 或 ×5）；
      这些数字只影响扫描展示与排序，真写时站点侧仍会按自己的规则校验，
      UI 会按 ``rules_unverified`` 标「规则未核对」（docs/认领.md §2）——
      **绝不把猜的值当成已核对**。

    ★ ``abandon_endpoint`` 默认给同族插件的 removeClaim 模板（9 站实测一致）；
      **没实测过该动作的站必须显式传 None**，宁可不提供也不能乱发写请求。

    ★ 19.10.60：``min_age_days`` 与 ``reward_min_age_days`` 是**两件事**，别混：
      · ``min_age_days``       = 站点**给不给认领按钮**（认领条件）。站点规则页
        「种子发布 N 天后可以认领」那种才是它。**0 = 无门槛**。
      · ``reward_min_age_days`` / ``reward_min_size_gb`` = 领了**这个月发不发魔力**
        （发奖条件，规则页一般写在「奖励标准」里）。
      混用的代价实测过：学校把发奖条件「发布满 30 天」当成认领门槛填了 30，
      结果所有新种在插件里都像"不能领"，而站点详情页其实早就有认领按钮。
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
        # ★ 认领「入口」随站点而变（2026-10-18 Master 指出）：
        #   同族插件站：个人详情页 userdetails.php 的「认领: [n/N]」配额 → claim.php
        #   学校：种子详情页 details.php 的「认领」→ viewclaims.php?add_torrent_id=
        "claim_entry": claim_entry,
        "detail_selector": detail_selector,
        "endpoint": dict(endpoint or _CLAIM_PLUGIN_ENDPOINT),
        # 放弃认领：None = 该站未核对 → 适配器回 unsupported，UI 不显示可点的「放弃」。
        "abandon_endpoint": dict(abandon_endpoint) if abandon_endpoint else None,
        # 发奖门槛（≠ 认领门槛）：领了也要满足这两条，本月才发魔力；0 = 站点没声明。
        "reward_min_age_days": float(reward_min_age_days or 0),
        "reward_min_size_gb": float(reward_min_size_gb or 0),
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
        "claim_entry": "/userdetails.php?id={uid}",
        "detail_selector": "#add-claim",
        "endpoint": {
            "method": "POST",
            "path": "/ajax.php",
            "body": {"action": "addClaim", "params": {"torrent_id": "{id}"}},
        },
        "abandon_endpoint": dict(_CLAIM_PLUGIN_ABANDON),  # 2026-10-31 探测确认（同上）
        # ★ 19.10.60：发奖门槛。CARPT 规则页达标标准只有「月做种 ≥300h 或上传 ≥体积×5」，
        #   没有发布天数 / 体积下限 → 0（站点没声明，不代填）。
        "reward_min_age_days": 0.0,
        "reward_min_size_gb": 0.0,
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
        1000, min_age_days=30, claim_entry="/userdetails.php?id={uid}",
        detail_selector="button[data-action='addClaim']",
        # ★ 2026-10-31 探测放弃接口时代理持续 502（该站域名本机直连 DNS 不解析）
        #   → **没核对就不提供**：宁可 UI 说「该站未提供放弃」，也不发没验证过的写请求。
        abandon_endpoint=None,
        note="聆音：用户上限 1000；2026-10-18 实机：userdetails 的正在做种/已完成列表都有认领按钮，"
             "按钮只在发布满 30 天后出现（30.0 天无、30.5 天有）；放弃接口未核对（代理 502）"),
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
        # ★ 19.10.60 纠正：``min_age_days`` 曾填 30 —— 那是**发奖**条件，不是认领门槛。
        #   学校 rules.php「认领种子规则」原文（2026-10-31 重读）：
        #     1. 所有会员，无论等级，均能认领种子
        #     2. 每个种子最多允许 20 名会员认领，每位会员最多可认领 100 个种子！
        #   → 认领条件里**没有任何发布天数要求**。
        #   「发布时间超过一个月（30天）」出现在第 5 条与「奖励标准」：
        #     「发布时间少于一个月的种子，即使达到认领要求依然没有魔力值奖励。
        #       如果种子的大小不到 1GB，达到认领要求同样没有魔力值奖励」
        #   → 这是 reward 门槛，走 ``reward_min_*``，不能拿来卡「能不能领」。
        #   实测佐证（同日）：346723 于 2026-10-30 17:47 发布，详情页已有
        #     [ 认领种子 ] + [查看认领详情:0] —— 发布 1 天就能领。
        100, min_age_days=0, max_claimers=20,
        target_seed_hours=300, target_upload_ratio=10,
        penalty_abandon=300,
        reward_min_age_days=30, reward_min_size_gb=1,
        claim_page="/details.php?id={id}", claim_list="/viewclaims.php",
        claim_entry="/viewclaims.php", detail_selector="a[href*='add_torrent_id']",
        endpoint={"method": "GET", "path": "/viewclaims.php?add_torrent_id={id}"},
        # ★ 学校（viewclaims）是另一套老式认领页：行里**没有**认领记录 id，
        #   也没有 removeClaim 动作（2026-10-31 复核：探测时代理 502 未能实测；
        #   其页面从未出现 data-action 按钮）→ 不提供放弃，UI 如实标注。
        abandon_endpoint=None,
        benefit_desc="站点按自然月结算发放（常规 500 / 官方 1000 魔力·种）",
        verified=True,
        note="学校 rules.php「认领种子规则」已核对（2026-10-18 首读、2026-10-31 复核）："
             "**认领无发布天数门槛**（所有会员均可领）/ 每颗 20 人 / 每人 100 个 / "
             "月做种 ≥300h 或上传 ≥体积×10 / 放弃扣 300 魔力；"
             "「发布满 30 天 + 体积 >1G」是**发奖**条件（发布不满一月即使达标也不计魔力）",
    ),
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
