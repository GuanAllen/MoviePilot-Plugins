"""站点「账号保活」规则表：多久不登入会被删号。

**为什么需要**：部分站点对「多久没登入」有硬性删号规则，而**规则口径往往把
做种 / 第三方工具排除在「登入」之外**——馒头官方 wiki 原文：

    登入指用浏览器存取网站网页进行登入或存取，**单纯做种不算登入，
    使用第三方工具间接存取也不算登入**。

→ 结论：插件（第三方工具）**帮不了保活**，只能**如实显示**站点记录的最后登入时间，
  按规则算「距删号还有几天」，到点提醒主人用浏览器（或官方 App）亲自登一次。

数据来源：站点官方规则页（人工核对，出处写在 ``rule_url`` / ``note``）。
本模块只依赖 stdlib，不发任何请求、不反向依赖插件主模块。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# key = 站点域名片段（小写、包含匹配）
KEEPALIVE_PRESETS: Dict[str, Dict[str, Any]] = {
    "m-team.cc": {
        "name": "馒头",
        "keep_days": 40,       # 未封存账号：连续 N 天不登入 → 删号
        "archived_days": 90,   # 已封存账号：连续 N 天不登入 → 删号
        "warn_days": 7,        # 剩余 ≤ N 天开始提醒
        "exempt": "府丞/Veteran 及以上「封存」后永久保号；府尹/Extreme 及以上永久保留",
        "agent": "用浏览器打开站点网页（或官方 App）——做种 / 第三方工具一律不算登入",
        "rule_url": "https://wiki.m-team.cc/zh-tw/account-rules",
        "note": "官方口径：登入指用浏览器存取网站网页进行登入或存取；单纯做种不算登入，使用第三方工具间接存取也不算登入",
    },
}


def keepalive_rule(domain: str) -> Optional[Dict[str, Any]]:
    """按域名取保活规则（无规则 → None）。"""
    d = str(domain or "").strip().lower()
    if not d:
        return None
    for key, rule in KEEPALIVE_PRESETS.items():
        if key in d:
            return dict(rule)
    return None
