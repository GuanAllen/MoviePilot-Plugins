# -*- coding: utf-8 -*-
"""魔流 · 认领写动作：同族 NexusPHP「种子认领」插件（通用处理器）。

2026-10-18 逐站实测（只读探测）：

  · 咖啡 / 大青虫 / 高清时间 / 聆音 / March / NovaHD / 蟹黄堡 / 财神 /
    Depth Studio 的种子详情页在可认领时都渲染 ``<input id="add-claim" data-torrent_id=N>``；
  · 前端统一发 ``POST {base}/ajax.php``，body
    ``{"action":"addClaim","params":{"torrent_id":N}}``（cookie 鉴权，非 token）；
  · 学校（BTSCHOOL）用 ``viewclaims.php`` 展示「种子认领」，页面字段
    （认领时间 / 下次结账 / 获得魔力值）与同族插件一致，写入口按同族推断。

本处理器**不写死站点**：能力与接口模板全部来自 ``sites/claim_presets.py`` 的
preset（``endpoint`` 模板 + ``rules_unverified``）。未收录的站 ``match()`` 返回
False → 调用方报「未收录适配器」。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from . import ClaimSiteHandler as _ClaimSiteHandler
from ..sites.claim_presets import preset_for


class NexusPhpClaim(_ClaimSiteHandler):
    """同族认领插件：按 preset 的 ``endpoint`` 模板发一次写请求。"""

    site_url = ""  # 不按单站匹配，交给 preset 判断

    def match(self, url: str) -> bool:
        """preset 命中且带 endpoint 模板 → 支持认领写动作。"""
        prof = preset_for(url)
        return bool(prof and prof.get("supported") and (prof.get("endpoint") or {}).get("path"))

    def claim(self, site_info: Dict[str, Any], torrent_id: Any, profile: Dict[str, Any]) -> Tuple[bool, str, str]:
        """认领一颗种子（请求体模板来自 preset）。"""
        return self.post_endpoint(site_info, profile, torrent_id)

    def abandon(self, site_info: Dict[str, Any], torrent_id: Any, profile: Dict[str, Any]) -> Tuple[bool, str, str]:
        """放弃认领：仅当 preset 显式给出 ``abandon_endpoint`` 时才发（否则 unsupported）。

        ★ 放弃 = 主动丢权益 + 可能扣分，**绝不猜接口**。
        """
        ep = (profile or {}).get("abandon_endpoint")
        if not ep:
            return False, "unsupported", "该站未提供「放弃认领」接口模板，未执行（本地账本保留）"
        return self.post_endpoint(site_info, profile, torrent_id, endpoint=ep)
