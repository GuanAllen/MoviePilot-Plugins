# -*- coding: utf-8 -*-
"""魔流 · 认领写动作：CARPT（carpt.net）。

站点机制（2026-10-02 实测对照详情页 / 规则页）：

  · 详情页在可认领时渲染 ``<input id="add-claim" data-torrent_id=NNN>`` +
    「已被 N 个用户认领，剩余 M 个名额」；字面文案带 ``claim.php?torrent_id=NNN``。
  · 前端 JS 触发 **``POST {base}/ajax.php``，body ``{"action":"addClaim",
    "params":{"torrent_id":NNN}}``**（cookie 鉴权，非 token）。
  · 规则：发布满 **7 天**可认领；每颗最多 **20** 人；单用户上限 **1000**；
    **达标种子魔力奖励 = 正常值 ×2**；不达标 −100（认领首月豁免）；主动放弃 −500。

本处理器走 ``profile.endpoint`` 模板（值来自 ``sites/claim_presets.py``），
只负责「发一次 + 如实解析」，限速/配额/幂等在 ``features/claim.py``。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from . import ClaimSiteHandler as _ClaimSiteHandler


class Carpt(_ClaimSiteHandler):
    """CARPT 认领（ajax.php addClaim）。"""

    site_url = "carpt.net"

    def match(self, url: str) -> bool:
        return super().match(url)

    def claim(self, site_info: Dict[str, Any], torrent_id: Any, profile: Dict[str, Any]) -> Tuple[bool, str, str]:
        """认领一颗种子。"""
        return self.post_endpoint(site_info, profile, torrent_id)

    def abandon(self, site_info: Dict[str, Any], torrent_id: Any, profile: Dict[str, Any]) -> Tuple[bool, str, str]:
        """放弃认领：仅在 profile 显式给出 ``abandon_endpoint`` 时才发（否则 unsupported）。

        ★ 放弃 = 主动丢权益 + 可能 −500 魔力，**绝不猜接口**。
        """
        ep = (profile or {}).get("abandon_endpoint")
        if not ep:
            return False, "unsupported", "CARPT 未提供「放弃认领」接口模板，未执行（本地账本保留）"
        return self.post_endpoint(site_info, profile, torrent_id, endpoint=ep)
