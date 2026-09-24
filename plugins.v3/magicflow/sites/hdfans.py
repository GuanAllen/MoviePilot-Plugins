"""
HDFans 魔力计算器

魔力公式：
  A = Σ((1 - 10^(-Ti/T0)) × Si × (1 + √2 × 10^(-(Ni-1)/(N0-1))) × Wi)
  B = B0 × 2/π × arctan(A/L)

参数：
  Ti: 种子生存时间（周）
  T0: 生存时间参数，固定 5
  Si: 种子大小（GB）
  Ni: 当前做种人数
  N0: 做种人数参数，固定 7
  Wi: 权重（普通=1，零魔=0.2）
  B0: 小时魔力上限，固定 100
  L: 曲线参数，固定 300
"""

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import BonusCalculator, SiteBonusInfo, TorrentBonusInfo


class HDFansBonusCalculator(BonusCalculator):
    """HDFans 魔力计算器"""

    site_schema = "Nexus"
    site_name = "HDFans"

    # 魔力公式常数
    T0 = 5     # 生存时间参数
    N0 = 7     # 做种人数参数
    B0 = 100   # 小时魔力上限
    L = 300    # 曲线参数

    def calc_bonus_per_hour(
        self,
        size: float,
        seeders: int,
        leechers: int = 0,
        age_weeks: float = 0,
        volume_factor: float = 1.0,
        is_zero_bonus: bool = False,
        **kwargs
    ) -> float:
        """
        计算 HDFans 单个种子的每小时魔力产出

        Args:
            size: 种子大小（GB）
            seeders: 当前做种人数
            leechers: 当前下载人数（未使用）
            age_weeks: 种子生存时间（周）
            volume_factor: 体积因子（免费=0.5, 2xfree=0.25）
            is_zero_bonus: 是否为零魔种子

        Returns:
            float: 每小时魔力产出
        """
        # 避免除零
        Ni = max(seeders, 1)

        # 计算生存时间因子 (1 - 10^(-Ti/T0))
        time_factor = 1 - math.pow(10, -age_weeks / self.T0)

        # 计算人数因子 (1 + √2 × 10^(-(Ni-1)/(N0-1)))
        people_factor = 1 + math.sqrt(2) * math.pow(10, -(Ni - 1) / (self.N0 - 1))

        # 计算当前种子的 A 值
        A_i = time_factor * size * people_factor * volume_factor

        # 权重：零魔种子为 0.2，普通为 1.0
        Wi = 0.2 if is_zero_bonus else 1.0
        A_i *= Wi

        # 计算魔力值 B = B0 × 2/π × arctan(A/L)
        B = self.B0 * (2 / math.pi) * math.atan(A_i / self.L)

        return round(B, 4)

    def parse_bonus_page(
        self,
        html: str,
        cookies: Dict[str, str],
        ua: str,
    ) -> SiteBonusInfo:
        """
        解析 HDFans 魔力页面

        页面 URL: /mybonus.php
        需要提取：
        - 当前魔力值
        - 每小时魔力产出
        - 做种数量和总体积
        - 当前 A 值
        """
        info = SiteBonusInfo(
            site_id=0,
            site_name=self.site_name,
            current_bonus=0.0,
            bonus_per_hour=0.0,
            raw_html=html,
        )

        # 提取当前魔力值
        # 格式如: <font class = 'color_bonus'>魔力值 </font>[<a href="mybonus.php">使用</a>]: 1,060.0
        bonus_match = re.search(
            r"魔力值.*?</a>\]:\s*([\d,]+\.?\d*)",
            html
        )
        if bonus_match:
            info.current_bonus = float(bonus_match.group(1).replace(',', ''))

        # 提取每小时魔力产出
        # 格式如: 你的服务器预计每小时产出魔力: 91.857
        hourly_match = re.search(
            r"预计每小时产出魔力[：:]\s*([\d,]+\.?\d*)",
            html
        )
        if hourly_match:
            info.bonus_per_hour = float(hourly_match.group(1).replace(',', ''))

        # 提取当前 A 值
        # 格式如: 当前 A 值：357.542
        a_match = re.search(r"当前\s*A\s*值[：:]\s*([\d,]+\.?\d*)", html)
        if a_match:
            info._a_value = float(a_match.group(1).replace(',', ''))

        # 提取做种统计
        # 格式如: 当前做种: <img ... />121  <img ... />0
        seeding_match = re.search(
            r"当前做种.*?<img[^>]*>\s*(\d+)",
            html,
            re.DOTALL
        )
        if seeding_match:
            info._seeding_count = int(seeding_match.group(1))

        return info

    def calc_age_weeks_from_pubdate(self, pubdate_str: Optional[str]) -> float:
        """
        从发行时间计算生存周数

        HDFans 页面显示格式可能包含中文，需要特殊处理
        """
        if not pubdate_str:
            return 0.0

        # 尝试多种格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ]

        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(pubdate_str.strip(), fmt)
                break
            except ValueError:
                continue

        if dt is None:
            # 尝试解析中文格式 "2024年1月15日 12:34:56"
            cn_match = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2}):(\d{2})", pubdate_str)
            if cn_match:
                dt = datetime(
                    int(cn_match.group(1)),
                    int(cn_match.group(2)),
                    int(cn_match.group(3)),
                    int(cn_match.group(4)),
                    int(cn_match.group(5)),
                    int(cn_match.group(6)),
                )

        if dt is None:
            return 0.0

        # 转换为 UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_seconds = (now - dt).total_seconds()
        age_weeks = age_seconds / (7 * 24 * 3600)

        return max(0.0, age_weeks)

    def get_torrent_list_url(self, site: Any, page: int = 1) -> str:
        """
        获取做种列表页面 URL

        HDFans 使用 NexusPHP，下载管理页包含做种种子的发行时间
        """
        return f"{site.domain}/torrents.php?page={page}&inclbookmarked=0&incldead=0"
