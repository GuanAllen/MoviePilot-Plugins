"""
MagicFlow 站点候选获取模块

封装 TorrentsChain 站点抓取，配合魔力规则初筛候选种子。

复用 brushflow 的站点抓取逻辑，适配 MagicFlow 的魔力评分需求。
"""

import inspect
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# 运行时导入（在 MoviePilot 环境才导入）
logger = logging.getLogger("magicflow")
TorrentsChain = None


def _ensure_sdk():
    """延迟导入 MoviePilot SDK。"""
    global logger, TorrentsChain
    if TorrentsChain is None:
        try:
            from app.sdk.logging import logger as _logger
            logger = _logger
        except ImportError:
            pass
        try:
            # fork v3：TorrentsChain 在 app.chain.torrents（包根 app.chain 仅剩兼容层）
            from app.chain.torrents import TorrentsChain as _tc
            TorrentsChain = _tc
        except ImportError:
            try:
                from app.chain import TorrentsChain as _tc
                TorrentsChain = _tc
            except ImportError:
                TorrentsChain = None


# ============================================================
# 数据模型
# ============================================================

@dataclass
class SiteCandidateTorrent:
    """站点候选种子。"""
    hash: str
    title: str
    size: float              # 大小（字节）
    size_gb: float = 0.0
    seeders: int = 0
    leechers: int = 0
    pubdate: Optional[str] = None  # 发布时间 ISO 字符串
    age_weeks: float = 0.0   # 生存周数
    page_url: str = ""       # 种子页面 URL
    enclosure: str = ""      # 下载链接
    site_name: str = ""      # 站点名称
    site_domain: str = ""    # 站点域名
    is_zero_bonus: bool = False
    is_free: bool = False
    is_double_free: bool = False
    hit_and_run: bool = False
    volume_factor: float = 1.0
    site_proxy: bool = False
    site_cookie: Optional[str] = None
    site_ua: Optional[str] = None
    downloadvolumefactor: float = 1.0
    uploadvolumefactor: float = 1.0

    def __post_init__(self):
        if self.size_gb <= 0:
            self.size_gb = self.size / (1024 ** 3) if self.size else 0.0


@dataclass
class FetchResult:
    """站点抓取结果。"""
    site_name: str
    total_count: int         # 总候选数
    eligible_count: int      # 符合初筛条件的数量
    candidates: List[SiteCandidateTorrent] = field(default_factory=list)
    reason_counts: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


# ============================================================
# 站点候选获取
# ============================================================

class SiteFetcher:
    """
    站点候选获取器。

    从站点抓取候选种子，按魔力规则初筛。
    """

    def __init__(self):
        """初始化站点获取器。"""
        _ensure_sdk()
        self._torrents_chain = TorrentsChain() if TorrentsChain else None

    @property
    def is_available(self) -> bool:
        """检查是否可用。"""
        return self._torrents_chain is not None

    # 只记录一次 browse 签名，便于确认 fork 是否支持翻页 / 分类 / 关键词
    _browse_sig_logged = False

    def browse_site(
        self,
        site_domain: str,
        rss_support: bool = False,
        pages: int = 1,
        cat: Optional[str] = None,
        keyword: Optional[str] = None,
        start_page: int = 0,
    ) -> List[SiteCandidateTorrent]:
        """
        从站点抓取候选种子。

        Args:
            site_domain: 站点域名（如 "hdfans.org"）
            rss_support: 是否使用 RSS 模式
            pages: 列表页翻页数（>1 时尽量向后翻，拿更多更老的种子）
            cat: 站点分类（若 SDK 支持）
            keyword: 关键词（若 SDK 支持）
            start_page: 起始页（游标深翻：从该页开始向后抓 pages 页）

        Returns:
            候选种子列表
        """
        if not self._torrents_chain:
            logger.warning("TorrentsChain 不可用")
            return []

        try:
            if rss_support:
                raw = list(self._torrents_chain.rss(domain=site_domain) or [])
                logger.info(f"站点 {site_domain} RSS 获取到 {len(raw)} 条原始种子")
            else:
                raw = self._browse_paged(
                    site_domain, pages=pages, cat=cat, keyword=keyword, start_page=start_page
                )

            result = []
            seen = set()
            for torrent in raw:
                candidate = self._parse_torrent(torrent, site_domain)
                if not candidate:
                    continue
                key = candidate.page_url or candidate.hash or candidate.title
                if key in seen:
                    continue
                seen.add(key)
                result.append(candidate)

            logger.info(f"站点 {site_domain} 获取到 {len(result)} 个候选种子（原始 {len(raw)} 条，翻页 {pages}）")
            return result

        except Exception as e:
            logger.error(f"站点 {site_domain} 抓取失败: {e}")
            return []

    def _browse_paged(
        self,
        site_domain: str,
        pages: int = 1,
        cat: Optional[str] = None,
        keyword: Optional[str] = None,
        start_page: int = 0,
    ) -> List[Any]:
        """按页抓取站点列表，自动探测 SDK browse 支持的参数。"""
        chain = self._torrents_chain
        browse = getattr(chain, "browse", None)
        if browse is None:
            logger.warning("TorrentsChain 无 browse 方法")
            return []

        # 一次性记录签名，确认 fork 是否支持 page / cat / keyword
        try:
            params = inspect.signature(browse).parameters
        except (TypeError, ValueError):
            params = None
        if not SiteFetcher._browse_sig_logged:
            SiteFetcher._browse_sig_logged = True
            try:
                logger.info(f"[探测] TorrentsChain.browse 签名: {inspect.signature(browse)}")
            except Exception:
                logger.info("[探测] TorrentsChain.browse 签名不可读")

        param_names = set(params.keys()) if params else set()
        var_kw = bool(params) and any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        can_page = ("page" in param_names) or var_kw

        total = max(1, int(pages or 1))
        base_page = max(int(start_page or 0), 0)
        collected: List[Any] = []
        for p in range(total):
            page_no = base_page + p
            if p and not can_page:
                logger.warning("[探测] browse 不支持 page 参数，无法翻页（仅取首页）")
                break
            kwargs: Dict[str, Any] = {"domain": site_domain}
            if page_no and can_page:
                kwargs["page"] = page_no
            if cat and ("cat" in param_names or var_kw):
                kwargs["cat"] = cat
            if keyword and ("keyword" in param_names or var_kw):
                kwargs["keyword"] = keyword
            try:
                batch = list(browse(**kwargs) or [])
            except TypeError as err:
                if p == 0:
                    logger.warning(f"browse 参数不被支持（{err}），退回最简调用")
                    batch = list(browse(site_domain) or [])
                else:
                    logger.warning(f"browse 第 {p} 页调用失败（{err}），停止翻页")
                    break
            except Exception as err:
                logger.warning(f"browse 第 {p} 页异常：{err}")
                break
            logger.info(f"[探测] browse page={p} 返回 {len(batch)} 条")
            collected.extend(batch)
            if not batch:
                break
        return collected

    def browse_all_sites(
        self,
        sites: List[Dict[str, Any]],
    ) -> Dict[str, FetchResult]:
        """
        从多个站点抓取候选种子。

        Args:
            sites: 站点配置列表，每个包含 domain、name 等

        Returns:
            按站点分组的抓取结果
        """
        results = {}
        for site in sites:
            domain = site.get("domain", "")
            name = site.get("name", domain)
            rss_support = site.get("rss_support", False)

            if not domain:
                continue

            candidates = self.browse_site(domain, rss_support=rss_support)

            results[domain] = FetchResult(
                site_name=name,
                total_count=len(candidates),
                eligible_count=len(candidates),
                candidates=candidates,
            )

        return results

    def _parse_torrent(
        self,
        torrent: Any,
        site_domain: str,
    ) -> Optional[SiteCandidateTorrent]:
        """
        解析站点种子为候选种子。

        Args:
            torrent: TorrentsChain 返回的种子对象
            site_domain: 站点域名

        Returns:
            候选种子或 None
        """
        try:
            # 提取基本信息
            hash_string = getattr(torrent, "hash", "") or ""
            title = getattr(torrent, "title", "") or ""
            size = float(getattr(torrent, "size", 0) or 0)
            seeders = int(getattr(torrent, "seeders", 0) or 0)
            leechers = int(getattr(torrent, "peers", 0) or getattr(torrent, "leechers", 0) or 0)
            pubdate = getattr(torrent, "pubdate", None)
            page_url = getattr(torrent, "page_url", "") or ""
            enclosure = getattr(torrent, "enclosure", "") or ""

            # 站点信息
            site_name = getattr(torrent, "site_name", "") or site_domain
            site_cookie = getattr(torrent, "site_cookie", None)
            site_ua = getattr(torrent, "site_ua", None)
            site_proxy = bool(getattr(torrent, "site_proxy", False) or False)

            # 站点列出页通常不给 infohash，退化为页面/下载链接作为去重标识
            if not hash_string:
                hash_string = page_url or enclosure or title

            # 免费/零魔检测
            downloadvolumefactor = float(getattr(torrent, "downloadvolumefactor", 1.0) or 1.0)
            uploadvolumefactor = float(getattr(torrent, "uploadvolumefactor", 1.0) or 1.0)

            is_free = downloadvolumefactor == 0
            is_double_free = downloadvolumefactor == 0 and uploadvolumefactor == 2
            is_zero_bonus = getattr(torrent, "is_zero_bonus", False)

            # H&R 检测
            hit_and_run = getattr(torrent, "hit_and_run", False)

            # 体积因子
            volume_factor = downloadvolumefactor

            # 计算年龄
            age_weeks = 0.0
            if pubdate:
                age_weeks = self._calc_age_weeks(pubdate)

            return SiteCandidateTorrent(
                hash=hash_string,
                title=title,
                size=size,
                size_gb=size / (1024 ** 3) if size else 0.0,
                seeders=seeders,
                leechers=leechers,
                pubdate=pubdate,
                age_weeks=age_weeks,
                page_url=page_url,
                enclosure=enclosure,
                site_name=site_name,
                site_domain=site_domain,
                is_zero_bonus=is_zero_bonus,
                is_free=is_free,
                is_double_free=is_double_free,
                hit_and_run=hit_and_run,
                volume_factor=volume_factor,
                site_cookie=site_cookie,
                site_ua=site_ua,
                site_proxy=site_proxy,
                downloadvolumefactor=downloadvolumefactor,
                uploadvolumefactor=uploadvolumefactor,
            )

        except Exception as e:
            logger.warning(f"解析种子失败: {e}")
            return None

    def _calc_age_weeks(self, pubdate: Any) -> float:
        """计算发布时间到现在的周数。"""
        if not pubdate:
            return 0.0

        try:
            # 尝试解析 ISO 格式
            if isinstance(pubdate, datetime):
                dt = pubdate
            elif isinstance(pubdate, str):
                text = pubdate.strip().replace('Z', '+00:00')
                try:
                    dt = datetime.fromisoformat(text)
                except ValueError:
                    dt = None
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                        try:
                            dt = datetime.strptime(text, fmt)
                            break
                        except ValueError:
                            continue
                    if dt is None:
                        return 0.0
            elif isinstance(pubdate, (int, float)):
                # 可能是时间戳
                dt = datetime.fromtimestamp(pubdate, tz=timezone.utc)
            else:
                return 0.0

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_hours = (now - dt).total_seconds() / 3600
            return max(0.0, age_hours / (7 * 24))

        except Exception:
            return 0.0


# ============================================================
# 候选初筛
# ============================================================

@dataclass
class FilterPolicy:
    """魔力管家选种过滤策略。"""
    # 做种人数范围
    min_seeders: int = 0       # 最少做种人数（魔力角度，人越少越好）
    max_seeders: int = 99999   # 最多做种人数（过滤掉太热门的）

    # 种子大小范围（GB）
    min_size_gb: float = 0.0
    max_size_gb: float = 99999.0

    # 发布年龄范围（周）
    min_age_weeks: float = 0.0   # 最少发布多少周
    max_age_weeks: float = 999.0 # 最多发布多少周

    # 零魔处理
    exclude_zero_bonus: bool = True  # 排除零魔种子
    exclude_free: bool = False       # 排除免费种子

    # H&R 处理
    exclude_hnr: bool = False  # 排除 H&R 种子

    # 正则过滤
    include_pattern: str = ""   # 必须包含的正则
    exclude_pattern: str = ""   # 必须排除的正则

    # 数量限制
    max_candidates: int = 1000  # 最多返回候选数（仅防病态；过大不必要，但太小会把新种截掉）


def filter_candidates(
    candidates: List[SiteCandidateTorrent],
    policy: FilterPolicy,
) -> Tuple[List[SiteCandidateTorrent], Dict[str, int]]:
    """
    按魔力规则初筛候选种子。

    过滤逻辑（与 BrushFlow 相反）：
        - 做种人数：Ni 越少越好（魔力高），但太少可能不健康
        - 零魔种子：排除（魔力产出极低）
        - 做种时间：Ti 越长越好（魔力高）
        - 大小：适中（魔力与大小非线性）

    Args:
        candidates: 候选种子列表
        policy: 过滤策略

    Returns:
        (过滤后的候选, 过滤原因统计)
    """
    if not candidates:
        return [], {}

    reason_counts: Dict[str, int] = {}
    filtered: List[SiteCandidateTorrent] = []

    for torrent in candidates:
        reason = None

        # 做种人数过滤
        if torrent.seeders < policy.min_seeders:
            reason = "做种人数低于下限"
        elif torrent.seeders > policy.max_seeders:
            reason = "做种人数超过上限"

        # 大小过滤
        elif torrent.size_gb < policy.min_size_gb:
            reason = "种子大小低于下限"
        elif torrent.size_gb > policy.max_size_gb:
            reason = "种子大小超过上限"

        # 年龄过滤（MagicFlow 偏好老种子）
        elif torrent.age_weeks < policy.min_age_weeks:
            reason = "种子太新"
        elif torrent.age_weeks > policy.max_age_weeks:
            reason = "种子太老"

        # 零魔排除
        elif policy.exclude_zero_bonus and torrent.is_zero_bonus:
            reason = "零魔种子"

        # 免费排除
        elif policy.exclude_free and torrent.is_free:
            reason = "免费种子"

        # H&R 排除
        elif policy.exclude_hnr and torrent.hit_and_run:
            reason = "H&R 种子"

        # 包含正则
        elif policy.include_pattern:
            if not re.search(policy.include_pattern, torrent.title, re.I):
                reason = "不符合包含规则"

        # 排除正则
        elif policy.exclude_pattern:
            if re.search(policy.exclude_pattern, torrent.title, re.I):
                reason = "符合排除规则"

        if reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        else:
            filtered.append(torrent)

    # 按魔力产出排序（魔力高的优先）
    filtered.sort(
        key=lambda t: (
            -t.age_weeks,           # 老种子优先
            t.seeders,              # 人少优先
            -t.size_gb,             # 大文件优先（但非线性）
        )
    )

    # 数量限制
    if len(filtered) > policy.max_candidates:
        filtered = filtered[:policy.max_candidates]

    return filtered, reason_counts


def get_default_filter_policy() -> FilterPolicy:
    """
    获取默认过滤策略。

    MagicFlow 的默认策略（与 BrushFlow 相反）：
        - 做种人数上限 20（排除太热门的）
        - 做种人数下限 1（排除完全没人的）
        - 最小年龄 0（不排除新种子）
        - 排除零魔
    """
    return FilterPolicy(
        min_seeders=1,        # 最少 1 人做种
        max_seeders=20,       # 最多 20 人做种（排除太热门的）
        min_size_gb=0.5,      # 最小 500MB
        max_size_gb=100.0,    # 最大 100GB
        min_age_weeks=0.0,    # 不限制最小年龄（但老种子排序会更靠前）
        max_age_weeks=999.0,  # 不限制最大年龄
        exclude_zero_bonus=True,  # 排除零魔
        exclude_free=False,       # 免费可以
        exclude_hnr=False,        # 不排除 H&R（魔力公式里 H&R 种子可能魔力更高）
        # 数量限制：只做病态保护，不能太小——否则「按年龄排序+截断」会把新种全裁掉，
        # 只剩老种反复被去重拦下，导致永远新增 0。
        max_candidates=1000,
    )


# ============================================================
# 发行时间抓取
# ============================================================

def fetch_torrent_pubdates(
    site_domain: str,
    torrents: List[SiteCandidateTorrent],
    site_cookie: Optional[str] = None,
    site_ua: Optional[str] = None,
) -> Dict[str, float]:
    """
    批量抓取种子的发行时间。

    Args:
        site_domain: 站点域名
        torrents: 种子列表
        site_cookie: 站点 Cookie
        site_ua: User-Agent

    Returns:
        {hash: age_weeks} 字典
    """
    _ensure_sdk()

    if not TorrentsChain:
        return {}

    result = {}
    # 限制批量抓取数量
    for torrent in torrents[:20]:
        if not torrent.page_url:
            continue

        try:
            # 使用站点详情页获取精确发布时间
            # 这里简化处理，实际可能需要解析页面
            if torrent.pubdate:
                # 已有 pubdate，直接计算
                fetcher = SiteFetcher()
                age = fetcher._calc_age_weeks(torrent.pubdate)
                result[torrent.hash] = age
            else:
                result[torrent.hash] = 0.0

        except Exception as e:
            logger.warning(f"抓取 {torrent.title} 发行时间失败: {e}")
            result[torrent.hash] = 0.0

    return result


# ============================================================
# 便捷函数
# ============================================================

def browse_site(domain: str, rss: bool = False) -> List[SiteCandidateTorrent]:
    """
    从站点抓取候选种子（便捷函数）。

    Args:
        domain: 站点域名
        rss: 是否使用 RSS 模式

    Returns:
        候选种子列表
    """
    fetcher = SiteFetcher()
    return fetcher.browse_site(domain, rss_support=rss)


def browse_and_filter(
    domain: str,
    policy: Optional[FilterPolicy] = None,
    rss: bool = False,
) -> Tuple[List[SiteCandidateTorrent], Dict[str, int]]:
    """
    抓取并过滤站点候选（便捷函数）。

    Args:
        domain: 站点域名
        policy: 过滤策略（默认使用 MagicFlow 策略）
        rss: 是否使用 RSS 模式

    Returns:
        (过滤后的候选, 过滤原因统计)
    """
    fetcher = SiteFetcher()
    candidates = fetcher.browse_site(domain, rss_support=rss)

    if not policy:
        policy = get_default_filter_policy()

    return filter_candidates(candidates, policy)


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MagicFlow 站点候选获取模块测试")
    print("=" * 60)

    # 测试过滤策略
    print("\n1. 测试默认过滤策略：")
    policy = get_default_filter_policy()
    print(f"   min_seeders: {policy.min_seeders}")
    print(f"   max_seeders: {policy.max_seeders}")
    print(f"   exclude_zero_bonus: {policy.exclude_zero_bonus}")
    print(f"   max_candidates: {policy.max_candidates}")

    # 模拟候选数据
    print("\n2. 测试候选过滤（模拟数据）：")
    mock_candidates = [
        SiteCandidateTorrent(
            hash="hash_1", title="热门新种.mkv",
            size=5 * 1024**3, seeders=100, age_weeks=1,
            site_domain="test.org"
        ),
        SiteCandidateTorrent(
            hash="hash_2", title="冷门老种.mkv",
            size=5 * 1024**3, seeders=1, age_weeks=10,
            site_domain="test.org"
        ),
        SiteCandidateTorrent(
            hash="hash_3", title="零魔种子.mkv",
            size=5 * 1024**3, seeders=5, age_weeks=5,
            site_domain="test.org", is_zero_bonus=True
        ),
        SiteCandidateTorrent(
            hash="hash_4", title="普通种子.mkv",
            size=5 * 1024**3, seeders=10, age_weeks=3,
            site_domain="test.org"
        ),
        SiteCandidateTorrent(
            hash="hash_5", title="无人种子.mkv",
            size=5 * 1024**3, seeders=0, age_weeks=8,
            site_domain="test.org"
        ),
    ]

    filtered, reasons = filter_candidates(mock_candidates, policy)

    print(f"   原始候选数: {len(mock_candidates)}")
    print(f"   过滤后候选数: {len(filtered)}")
    print(f"   过滤原因统计: {reasons}")
    print(f"\n   过滤后排序（魔力从高到低）：")
    for i, t in enumerate(filtered, 1):
        print(f"   {i}. {t.title} - 做种{t.seeders}人, {t.age_weeks:.1f}周", end="")
        if t.is_zero_bonus:
            print(" [零魔]", end="")
        print()

    # 测试年龄计算
    print("\n3. 测试年龄计算：")
    fetcher = SiteFetcher()
    test_dates = [
        "2026-09-01T00:00:00Z",  # 约 3 周前
        "2026-09-20T00:00:00Z",  # 约 3 天前
        None,                     # 无日期
    ]
    for date in test_dates:
        age = fetcher._calc_age_weeks(date)
        print(f"   {date} -> {age:.2f} 周")

    print("\n" + "=" * 60)
    print("测试完成（TorrentsChain 测试需要 MoviePilot 环境）")
    print("=" * 60)
