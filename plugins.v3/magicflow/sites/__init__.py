"""
魔力计算器基类

各站点需实现 BonusCalculator 子类，并在 calc_bonus_per_hour 方法中实现站点魔力公式
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TorrentBonusInfo:
    """种子的魔力相关信息"""
    hash: str
    title: str
    size: float  # GB
    seeders: int
    leechers: int
    pubdate: Optional[str] = None  # 发行时间 YYYY-MM-DD HH:MM:SS
    uploaded: float = 0  # 已上传量 GB
    downloaded: float = 0  # 已下载量 GB
    ratio: float = 0  # 分享率
    seeding_time: float = 0  # 做种时间 秒
    volume_factor: float = 1.0  # 体积因子（免费=0.5, 2xfree=0.25等）

    # 以下由计算器填充
    age_weeks: float = 0  # 种子生存时间（周）
    bonus_per_hour: float = 0  # 每小时魔力产出
    bonus_weight: float = 1.0  # 魔力权重（普通=1，零魔=0.2）


@dataclass
class SiteBonusInfo:
    """站点的魔力总体信息"""
    site_id: int
    site_name: str
    current_bonus: float  # 当前魔力值
    bonus_per_hour: float  # 当前每小时魔力产出
    torrents: List[TorrentBonusInfo] = field(default_factory=list)
    raw_html: str = ""  # 原始页面内容，用于调试


class BonusCalculator(ABC):
    """魔力计算器抽象基类"""

    # 站点标识，用于匹配 MoviePilot 站点配置
    site_schema: str = ""  # 如 "Nexus", "Gazelle", "UNIT3D" 等
    site_name: str = ""  # 站点显示名称

    @abstractmethod
    def calc_bonus_per_hour(
        self,
        size: float,          # GB
        seeders: int,         # 当前做种人数
        leechers: int,        # 当前下载人数
        age_weeks: float,     # 种子生存时间（周）
        volume_factor: float, # 体积因子
        **kwargs
    ) -> float:
        """
        计算单个种子的每小时魔力产出

        Args:
            size: 种子大小（GB）
            seeders: 当前做种人数
            leechers: 当前下载人数
            age_weeks: 种子发行到现在经过的周数
            volume_factor: 体积因子（普通=1.0, 免费=0.5, 2xfree=0.25）

        Returns:
            float: 每小时魔力产出
        """
        pass

    def parse_bonus_page(
        self,
        html: str,
        cookies: Dict[str, str],
        ua: str,
    ) -> SiteBonusInfo:
        """
        解析魔力页面，提取当前魔力值和每小时产出

        默认实现尝试从页面中提取魔力值，子类可覆盖实现站点特定的解析逻辑

        Args:
            html: 页面 HTML 内容
            cookies: 站点 cookies
            ua: User-Agent

        Returns:
            SiteBonusInfo: 站点魔力信息
        """
        import re

        # 提取当前魔力值
        bonus_match = re.search(r'魔力值.*?:\s*([\d,]+\.?\d*)', html)
        current_bonus = 0.0
        if bonus_match:
            current_bonus = float(bonus_match.group(1).replace(',', ''))

        # 提取每小时产出
        hourly_match = re.search(r'每小时.*?魔力.*?[:：]\s*([\d,]+\.?\d*)', html)
        bonus_per_hour = 0.0
        if hourly_match:
            bonus_per_hour = float(hourly_match.group(1).replace(',', ''))

        return SiteBonusInfo(
            site_id=0,
            site_name=self.site_name,
            current_bonus=current_bonus,
            bonus_per_hour=bonus_per_hour,
        )

    def get_bonus_page_url(self, site: Any) -> str:
        """
        获取魔力页面 URL

        Args:
            site: MoviePilot 站点对象

        Returns:
            str: 魔力页面 URL
        """
        return f"{site.domain}/mybonus.php"

    def get_bonus_page_headers(self, ua: str) -> Dict[str, str]:
        """
        获取魔力页面请求头

        Args:
            ua: User-Agent

        Returns:
            Dict[str, str]: 请求头
        """
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "",
        }

    def get_torrent_list_url(self, site: Any, page: int = 1) -> str:
        """
        获取做种列表页面 URL（用于抓取种子发行时间）

        Args:
            site: MoviePilot 站点对象
            page: 页码

        Returns:
            str: 种子列表页 URL
        """
        return f"{site.domain}/torrents.php?page={page}"

    def parse_torrent_pubdates(self, html: str) -> Dict[str, str]:
        """
        解析种子列表页面，提取种子的发行时间

        默认实现解析 NexusPHP 格式的种子列表
        子类可覆盖实现站点特定的解析逻辑

        Args:
            html: 页面 HTML 内容

        Returns:
            Dict[str, str]: key=info_hash(小写), value=发行时间字符串
        """
        import re
        from urllib.parse import parse_qs, urlparse

        result = {}

        # NexusPHP 种子行格式
        # 查找所有种子行，包含详情链接和添加时间
        rows = re.findall(
            r'<tr[^>]*class="[^\"]*torrent[^\"]*"[^>]*>(.*?)</tr>',
            html,
            re.DOTALL
        )

        for row in rows:
            # 提取详情页链接和 info_hash
            link_match = re.search(
                r'<a[^>]+href="([^"]*details\.php\?id=\d+[^\"]*)"[^>]*>',
                row
            )
            if not link_match:
                continue

            detail_url = link_match.group(1)

            # 从 URL 中提取 info_hash
            hash_match = re.search(r'[&?]hash=([a-fA-F0-9]{40})', detail_url)
            if not hash_match:
                continue
            info_hash = hash_match.group(1).lower()

            # 提取添加时间
            # 格式: <td ...>2024-01-15 12:34:56</td>
            date_match = re.search(
                r'添加日期</td><td[^>]*>([^<]+)</td>',
                row
            )
            if date_match:
                result[info_hash] = date_match.group(1).strip()

        return result

    def calc_torrent_bonus(self, torrent: TorrentBonusInfo, **kwargs) -> float:
        """
        计算单个种子的魔力产出

        Args:
            torrent: 种子魔力信息

        Returns:
            float: 每小时魔力产出
        """
        return self.calc_bonus_per_hour(
            size=torrent.size,
            seeders=torrent.seeders,
            leechers=torrent.leechers,
            age_weeks=torrent.age_weeks,
            volume_factor=torrent.volume_factor,
            **kwargs
        )

    def calc_total_bonus(self, torrents: List[TorrentBonusInfo], **kwargs) -> float:
        """
        计算所有种子的每小时魔力总和

        Args:
            torrents: 种子列表

        Returns:
            float: 每小时魔力总和
        """
        total = 0.0
        for t in torrents:
            t.bonus_per_hour = self.calc_torrent_bonus(t, **kwargs)
            total += t.bonus_per_hour
        return total

    @staticmethod
    def calc_age_weeks(pubdate_str: Optional[str]) -> float:
        """
        从发行时间字符串计算经过的周数

        Args:
            pubdate_str: 发行时间字符串，格式如 "2024-01-15 12:34:56" 或 "2024-01-15"

        Returns:
            float: 经过的周数
        """
        if not pubdate_str:
            return 0.0

        from datetime import datetime

        # 尝试多种日期格式
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
            return 0.0

        # 转换为周
        from datetime import timezone, timedelta

        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        age_seconds = (now - dt).total_seconds()
        age_weeks = age_seconds / (7 * 24 * 3600)

        # 不能为负数
        return max(0.0, age_weeks)


# ============================================================
# 站点魔力计算器注册表
# ============================================================

_CALCULATORS: Dict[str, type] = {}


def register_calculator(site_schema: str):
    """
    装饰器：注册站点魔力计算器

    用法：
        @register_calculator("Nexus")
        class NexusPHPBonusCalculator(BonusCalculator):
            ...
    """
    def decorator(cls):
        _CALCULATORS[site_schema] = cls
        return cls
    return decorator


def get_calculator(site_domain: str = "", site_schema: str = "") -> Optional[BonusCalculator]:
    """
    根据站点域名/类型获取魔力计算器。

    Args:
        site_domain: 站点域名（如 "hdfans.org"）
        site_schema: 站点类型（如 "Nexus"、"UNIT3D"），优先按域名匹配

    Returns:
        BonusCalculator 实例，或 None
    """
    # 延迟导入，避免循环依赖
    from . import hdfans

    # 如果已注册，直接返回
    if site_domain and site_domain in _CALCULATORS:
        return _CALCULATORS[site_domain]()
    if site_schema and site_schema in _CALCULATORS:
        return _CALCULATORS[site_schema]()

    # 根据域名模式匹配
    domain_lower = (site_domain or "").lower()

    # HDFans 及其同类 NexusPHP 站点
    nexusphp_domains = ['hdfans', 'hdarea', 'hdchina', 'ourbits', 'ttg', 'ptchina']
    if any(d in domain_lower for d in nexusphp_domains):
        return hdfans.HDFansBonusCalculator()

    # 默认返回 HDFans 计算器（NexusPHP 通用）
    return hdfans.HDFansBonusCalculator()


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
    from ..bonus import BonusParams

    for key in (domain, schema):
        if not key:
            continue
        lowered = str(key).strip().lower()
        if lowered in _FORMULA_PRESETS:
            return BonusParams(**_FORMULA_PRESETS[lowered])
    return BonusParams()


def register_default_calculators():
    """注册默认的计算器。"""
    from . import hdfans
    _CALCULATORS['hdfans'] = hdfans.HDFansBonusCalculator
    _CALCULATORS['NexusPHP'] = hdfans.HDFansBonusCalculator
    _CALCULATORS['Nexus'] = hdfans.HDFansBonusCalculator


# 注册默认计算器
register_default_calculators()
