"""
MagicFlow 站点候选获取模块

封装 TorrentsChain 站点抓取，配合魔力规则初筛候选种子。

复用 brushflow 的站点抓取逻辑，适配 MagicFlow 的魔力评分需求。
"""

import inspect
import logging
import re
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

# 站点页面上的「发布时间」是站点本地时间（国内 PT 站均为 UTC+8）。
# MoviePilot 容器时区同为 Asia/Shanghai，解析出的 naive 时间即本地时间，
# 因此换算 unix 秒时按 +8 处理（否则 Ti 会凭空年轻 8 小时，站点 A 严重偏低）。
SITE_TZ_OFFSET_HOURS = 8.0
SITE_TZ = timezone(timedelta(hours=SITE_TZ_OFFSET_HOURS))

# 运行时导入（在 MoviePilot 环境才导入）
logger = logging.getLogger("magicflow")
TorrentsChain = None

# 站点请求最小间隔（秒），由插件全局设置注入；0 = 不限速。
_REQUEST_INTERVAL = 0.0


def promo_remaining_sec(until: str) -> float:
    """促销到期时间（站点本地时间字符串）距现在的秒数；解析失败返回 -1（视为未知）。

    PT 站（如 Pttime）的「免费/2X免费」普遍是**限时**促销，列表页在促销标记后紧跟
    ``<span title="YYYY-MM-DD HH:MM:SS">剩余</span>``。到期后继续下载会按原价计流量，
    所以必须把「还剩多久」带出来，供下载前判断够不够下完。
    """
    try:
        dt = datetime.strptime(str(until).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=SITE_TZ)
        return dt.timestamp() - time.time()
    except Exception:  # noqa: BLE001
        return -1.0


# ── 限时免费（促销到期）闸门参数 ─────────────────────────────
# PT 站的「免费/2X免费」多为**限时**促销（Pttime 实测：12 分钟～6 天不等）。
# 到期后继续下载会按原价计流量 → 得判断「剩余免费时间够不够下完」。
FREE_ASSUMED_SPEED_MBPS = 20.0   # 预估下载速度（MB/s），用于估算下载耗时
FREE_MIN_MARGIN_SEC = 1800.0     # 安全余量（秒）：再留 30 分钟缓冲


def free_time_ok(cand) -> Tuple[bool, float, float]:
    """限时免费种子的剩余免费时间是否足够下完。

    返回 ``(是否放行, 预估需要秒数, 剩余秒数)``。
    剩余时间未知（-1）→ 放行（不误杀：非限时/非 NexusPHP 站点本就没有该字段）。
    """
    try:
        remain = float(getattr(cand, "free_remaining_sec", -1.0) or -1.0)
    except (TypeError, ValueError):
        remain = -1.0
    if remain < 0:
        return True, 0.0, -1.0
    try:
        size_gb = float(getattr(cand, "size_gb", 0.0) or 0.0)
    except (TypeError, ValueError):
        size_gb = 0.0
    need = (size_gb * 1024.0 / max(FREE_ASSUMED_SPEED_MBPS, 1.0)) + FREE_MIN_MARGIN_SEC
    return (remain >= need), need, remain


def set_request_interval(seconds: float) -> None:
    """设置站点翻页请求之间的最小间隔（秒）。0 表示不限速。"""
    global _REQUEST_INTERVAL
    try:
        _REQUEST_INTERVAL = max(0.0, float(seconds or 0))
    except (TypeError, ValueError):
        _REQUEST_INTERVAL = 0.0


# 翻页调试日志：默认关。之前这四条 logger.warning 是**无条件**打的，
# 每次抓取 × 每页都刷一遍 → 日志被淹、真问题看不见。
_BROWSE_DEBUG = False


def set_browse_debug(flag: Any) -> None:
    """开关 browse 翻页的调试日志（由插件全局 debug_log 注入）。"""
    global _BROWSE_DEBUG
    _BROWSE_DEBUG = bool(flag)


def get_request_interval() -> float:
    """读取当前站点请求最小间隔（秒）。"""
    return _REQUEST_INTERVAL


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
    # ★ 促销到期（限时免费）：站点本地时间字符串 + 距现在剩余秒数（-1=未知/不限期）
    free_until: str = ""
    free_remaining_sec: float = -1.0

    def __post_init__(self):
        if self.size_gb <= 0:
            self.size_gb = self.size / (1024 ** 3) if self.size else 0.0

    # ---- 序列化（供缓存层持久化：候选列表落 FileCache，跨重载/重启不丢）----
    def to_dict(self) -> Dict[str, Any]:
        """转为可 JSON 序列化的普通字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["SiteCandidateTorrent"]:
        """从字典还原；字段缺失/多余均容错，非法输入返回 None。"""
        if not isinstance(data, dict):
            return None
        names = {f.name for f in fields(cls)}
        try:
            return cls(**{k: v for k, v in data.items() if k in names})
        except Exception:  # noqa: BLE001
            return None


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
# NexusPHP 直连索引：按「促销状态」直接拿免费种
# ============================================================
# NexusPHP 标准 spstate 促销筛选值（站点列表页 / 顶部的促销快捷筛选）。
#   1=普通  2=免费  3=2X上传  4=2X免费  5=50%免费
#   6=2X上传&50%免费  7=30%免费  8=0流量
# 刷流只关心「下载免费」→ 取 2(免费) + 4(2X免费)。
NP_FREE_SPSTATES: Tuple[int, ...] = (2, 4)

# NexusPHP 促销 class → (下载系数 dv, 上传系数 uv)，用于换算免费/双倍。
_NP_PROMO_FACTORS: Dict[str, Tuple[float, float]] = {
    "free": (0.0, 1.0),
    "twoupfree": (0.0, 2.0),
    "zeroupzerodown": (0.0, 0.0),
    "halfdown": (0.5, 1.0),
    "twouphalfdown": (0.5, 2.0),
    "thirtypercent": (0.7, 1.0),
    "twoup": (1.0, 2.0),
}

_NP_ROW_RE = re.compile(r"<tr\s+data=(\d+)>", re.IGNORECASE)

# ★ 皮肤差异：CHD / 新版 Tailwind 系（hdtime、cspt 等）不用 promotion class，
#   而是 <img class="pro_free"> / <img class="pro_free2up"> 标促销 —— 映射到同一套系数。
_NP_PRO_CLASSES: Dict[str, Tuple[float, float]] = {
    "pro_free": (0.0, 1.0),       # 免费
    "pro_free2up": (0.0, 2.0),    # 免费 + 2X 上传
    "pro_2up": (1.0, 2.0),        # 2X 上传
    "pro_2up50pct": (0.5, 2.0),   # 2X 上传 + 50% 下载
    "pro_halfdown": (0.5, 1.0),
    "pro_50pct": (0.5, 1.0),
    "pro_75pct": (0.25, 1.0),
    "pro_30pct": (0.7, 1.0),
    "pro_25pct": (0.75, 1.0),
    "pro_0up0down": (0.0, 0.0),
}

# 详情页链接（用作「行」的锚点；(?<![A-Za-z]) 排除 userdetails.php?id= 这种误命中）
_NP_ID_RE = re.compile(r"(?<![A-Za-z])details\.php\?id=(\d+)", re.IGNORECASE)
_NP_TR_RE = re.compile(r"<tr\b[^>]*>|</tr\s*>", re.IGNORECASE)


def _np_row_chunks(html_text: str) -> List[Tuple[str, str]]:
    """表格型皮肤：把 ``<tr>`` 按嵌套配对切块，只留「恰好一个详情 id」的块（= 一条种子行）。

    嵌套的标题小表行只有一个 id 也会命中，但无大小/人数，由调用方的兜底校验刷掉。
    包裹行/页头页脚含多个 id 或无 id，自然被排除。
    """
    stack: List[int] = []
    out: List[Tuple[str, str]] = []
    for m in _NP_TR_RE.finditer(html_text):
        if m.group(0)[1] != "/":
            stack.append(m.start())
            continue
        if not stack:
            continue
        s = stack.pop()
        chunk = html_text[s:m.end()]
        ids = {mm.group(1) for mm in _NP_ID_RE.finditer(chunk)}
        if len(ids) == 1:
            out.append((next(iter(ids)), chunk))
    return out


def _np_id_windows(html_text: str) -> List[Tuple[str, str]]:
    """div 型皮肤（cspt 等）：按「详情 id 首现顺序」切窗口（同 id 连发归同一行）。

    窗口起点回退到所在标签头（``<a`` 之前），否则会把锚点切断、标题取成同行的人数值。
    """
    spans: List[Tuple[int, str]] = []
    seen: set = set()
    for m in _NP_ID_RE.finditer(html_text):
        tid = m.group(1)
        if tid in seen:
            continue
        seen.add(tid)
        spans.append((m.start(), tid))
    out: List[Tuple[str, str]] = []
    for i, (pos, tid) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(html_text)
        s = html_text.rfind("<", 0, pos)
        out.append((tid, html_text[(s if s >= 0 else pos):end]))
    return out
_NP_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}


def _np_size_to_bytes(num: str, unit: str) -> float:
    """把列表页的大小（如 ``83.28`` + ``GB``）换算为字节。"""
    try:
        val = float(str(num).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0
    return val * _NP_SIZE_UNITS.get((unit or "GB").upper(), 1024 ** 3)


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
        site_obj: Any = None,
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
            site_obj: 站点对象（用于传递 cookie 给 TorrentsChain）
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
        if _BROWSE_DEBUG:
            logger.warning(f"[DEBUG] _browse_paged called: site_domain={site_domain!r} pages={pages} start_page={start_page}")
        for p in range(total):
            # 站点请求节流：翻页之间按全局设置休眠，降低被站点限速/封禁的风险
            if p and _REQUEST_INTERVAL > 0:
                time.sleep(_REQUEST_INTERVAL)
            page_no = base_page + p
            if p and not can_page:
                logger.warning("[探测] browse 不支持 page 参数，无法翻页（仅取首页）")
                break
            kwargs: Dict[str, Any] = {"domain": site_domain}
            if _BROWSE_DEBUG:
                logger.warning(f"[DEBUG] browse call page={p} kwargs={kwargs}")
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
            if _BROWSE_DEBUG:
                logger.warning(f"[DEBUG] browse page={p} kwargs={kwargs} raw result={len(batch)} items, first={batch[0] if batch else None}")
            collected.extend(batch)
            if not batch:
                break
        if _BROWSE_DEBUG:
            logger.warning(f"[DEBUG] _browse_paged total collected={len(collected)}")
        return collected

    def _parse_np_rows(
        self,
        html_text: str,
        site_domain: str,
        base_url: str,
        cookie: Optional[str],
        ua: Optional[str],
    ) -> List[SiteCandidateTorrent]:
        """解析 NexusPHP 列表页（torrents.php）为候选种子列表。

        只依赖列表页可见字段：标题 / 促销 class / 添加时间 / 大小 / 做种人数 / 下载人数 /
        下载链接。行内无 infohash，故 hash 退化为详情页 URL（与 SDK 路径一致）。

        ★ 皮肤自适应（2026-09-27）：NexusPHP 各站/各皮肤的行结构与 class 名差别很大，实测至少三套：
          ① 官方经典：``<tr data="id">`` + ``class="torrentname_title"`` + ``class="promotion free"``
          ② CHD/torrentname 系（hdtime/hdfans…）：无 ``<tr data=>``，标题在
             ``<table class="torrentname">`` 里、促销是 ``<img class="pro_free">``、
             人数/大小在 ``<td class="rowfollow">``
          ③ 新版 Tailwind 系（cspt…）：标题带 ``torrent-info-text-name``、促销 ``<img class="pro_free">``、
             字段用 ``torrent-info-text-{size,seeders,leechers,added}``
        原先死认 ①，导致 ②③ 解析结果恒为 0 条（免费定向视图/直连免费索引长期空转）。
        现改为**按「详情页 id 出现的先后」切行**（同一 id 的标题/评论/做种等多个链接必属同一行，
        出现新 id 即下一行开始），再逐行做多皮肤字段提取。
        """
        out: List[SiteCandidateTorrent] = []
        if not html_text:
            return out
        base = base_url.rstrip("/")

        # 行切分（多皮肤）：先试表格型（<tr> 配对且只含一个详情 id），没有则退到 div 型
        _rows = _np_row_chunks(html_text)
        if not _rows:
            _rows = _np_id_windows(html_text)
        for _tid, chunk in _rows:

            # 标题：① 官方经典 ② 通用——本行首个指向 details.php?id=<本行 id> 的 <a>
            #   优先 title 属性，否则取锚点内文本（兼容新版 torrent-info-text-name）
            tm = re.search(
                r'class=["\']torrentname_title["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                chunk, re.DOTALL,
            )
            if not tm:
                tm = re.search(
                    r'href=["\']([^"\']*details\.php\?id=[^"\']+)["\'][^>]*class=["\']torrentname_title["\'][^>]*>(.*?)</a>',
                    chunk, re.DOTALL,
                )
            href = inner = ""
            if tm:
                href, inner = tm.group(1), tm.group(2)
            else:
                for _am in re.finditer(r"<a\b([^>]*)>(.*?)</a>", chunk, re.DOTALL | re.IGNORECASE):
                    _attrs, _inner_raw = _am.group(1), _am.group(2)
                    _hm = re.search(
                        r'href=["\']([^"\']*details\.php\?id=%s[^"\']*)["\']' % re.escape(_tid), _attrs
                    )
                    if not _hm:
                        continue
                    _inner_txt = re.sub(r"<[^>]+>", "", _inner_raw).strip()
                    _ttl = re.search(r'title=["\']([^"\']+)["\']', _attrs)
                    if (_ttl and _ttl.group(1).strip()) or _inner_txt:
                        href = _hm.group(1)
                        inner = (_ttl.group(1).strip() if _ttl else "") or _inner_txt
                        break
            title = re.sub(r"<[^>]+>", "", inner).strip()
            title = re.sub(r"\s*\[[^\]]{0,12}\]\s*$", "", title).strip()  # 去掉 [热门] 之类尾巴
            if not title or not href:
                continue
            page_url = urljoin(base + "/", href)

            # 促销状态：① 官方经典 class="promotion free" ② CHD/新版 <img class="pro_free">
            #   （跳过 promotion bb=字幕/附件 之类非促销标记）
            promo = ""
            for pm in re.finditer(r"class=['\"]promotion\s+(\w+)['\"]", chunk):
                cls = pm.group(1).lower()
                if cls in _NP_PROMO_FACTORS:
                    promo = cls
                    break
            if not promo:
                for pm in re.finditer(r"class=['\"]pro_(\w+)['\"]", chunk):
                    cls = "pro_" + pm.group(1).lower()
                    if cls in _NP_PRO_CLASSES:
                        promo = cls
                        break
            dv, uv = _NP_PROMO_FACTORS.get(promo) or _NP_PRO_CLASSES.get(promo) or (1.0, 1.0)

            # ★ 促销到期（限时免费）：紧跟在促销标记后的 <span title="YYYY-MM-DD HH:MM:SS">
            free_until = ""
            free_remaining_sec = -1.0
            if promo:
                _em = re.search(
                    r"promotion\s+%s['\"]\s*>[^<]*</font>\s*<span\s+title=[\"']"
                    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[\"']" % re.escape(promo),
                    chunk,
                )
                if _em:
                    free_until = _em.group(1)
                    free_remaining_sec = promo_remaining_sec(free_until)

            # 添加时间（列表页 <span title="YYYY-MM-DD HH:MM:SS">）
            pubdate = None
            dm = re.search(r'<span title=["\'](\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})["\']', chunk)
            if dm:
                pubdate = dm.group(1)

            # 大小：① 经典/CHD <td class="rowfollow">83.28<br>GB</td>
            #      ② 新版 <div class="torrent-info-text-size">1.01 GB</div>
            #      ③ 兜底：本行最后一个「数字+单位」片段（标题里的分辨率/体积在前，真值在后）
            size = 0.0
            sm = re.search(r'class="rowfollow">\s*([\d.,]+)\s*<br\s*/?>\s*([KMGT]?i?B)', chunk)
            if sm:
                size = _np_size_to_bytes(sm.group(1), sm.group(2).upper().replace("I", ""))
            if not size:
                sm = re.search(
                    r'torrent-info-text-size["\'][^>]*>\s*([\d.,]+)\s*([KMGT]?i?B)', chunk
                )
                if sm:
                    size = _np_size_to_bytes(sm.group(1), sm.group(2).upper().replace("I", ""))
            if not size:
                _all_sz = re.findall(r"([\d]+(?:[.,]\d+)?)\s*(?:<[^>]*>\s*)*([KMGT]i?B)\b", chunk)
                if _all_sz:
                    _n, _u = _all_sz[-1]
                    size = _np_size_to_bytes(_n, _u.upper().replace("I", ""))

            # 做种/下载人数：① 官方/CHD 用 dllist 锚点的 #seeders / #leechers
            #                ② 新版用 torrent-info-text-seeders/-leechers
            #                ③ 兜底：大小单元格之后的第 1/2 个纯数字单元格
            seeders = leechers = 0
            s1 = re.search(r'#seeders["\']>(\d+)<', chunk) or re.search(
                r'torrent-info-text-seeders["\'][^>]*>\s*(?:<[^>]+>\s*)*(\d+)', chunk
            )
            if s1:
                seeders = int(s1.group(1))
            s2 = re.search(r'#leechers["\']>(\d+)<', chunk) or re.search(
                r'torrent-info-text-leechers["\'][^>]*>\s*(?:<[^>]+>\s*)*(\d+)', chunk
            )
            if s2:
                leechers = int(s2.group(1))
            if not seeders and not leechers:
                _cells = [
                    re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                    for c in re.findall(
                        r'<td[^>]*class="[^"]*rowfollow[^"]*"[^>]*>(.*?)</td>', chunk, re.DOTALL
                    )
                ]
                _sz_idx = next(
                    (k for k, c in enumerate(_cells) if re.fullmatch(r"[\d.,]+\s*[KMGT]?i?B", c)), -1
                )
                if _sz_idx >= 0:
                    _pure = [c for c in _cells[_sz_idx + 1:] if re.fullmatch(r"[\d,]+", c or "")]
                    if len(_pure) >= 2:
                        seeders = int(_pure[0].replace(",", "") or 0)
                        leechers = int(_pure[1].replace(",", "") or 0)

            # 下载链接（enclosure）
            enclosure = ""
            em = re.search(r'href=["\']([^"\']*download\.php[^"\']*)["\']', chunk)
            if em:
                enclosure = urljoin(base + "/", em.group(1))

            # 至少要有「大小 / 人数 / 下载链接」之一，否则视为页头页脚噪声行
            if not (size or seeders or leechers or enclosure):
                continue

            out.append(SiteCandidateTorrent(
                hash=page_url,
                title=title,
                size=size,
                size_gb=size / (1024 ** 3) if size else 0.0,
                seeders=seeders,
                leechers=leechers,
                pubdate=pubdate,
                age_weeks=ts_to_age_weeks(pubdate_to_ts(pubdate)) if pubdate else 0.0,
                page_url=page_url,
                enclosure=enclosure,
                site_name=site_domain,
                site_domain=site_domain,
                is_free=(dv == 0),
                is_double_free=(dv == 0 and uv == 2),
                hit_and_run=False,
                volume_factor=dv,
                site_cookie=cookie,
                site_ua=ua,
                downloadvolumefactor=dv,
                uploadvolumefactor=uv,
                free_until=free_until,
                free_remaining_sec=free_remaining_sec,
            ))

        # 去重：嵌套块（内层标题小表）也会命中一次但字段少，保留字段最全的那份
        def _score(row: "SiteCandidateTorrent") -> int:
            return sum(
                1 for v in (row.size, row.seeders, row.leechers, row.pubdate, row.enclosure) if v
            )

        best: Dict[str, SiteCandidateTorrent] = {}
        for row in out:
            cur = best.get(row.page_url)
            if cur is None or _score(row) > _score(cur):
                best[row.page_url] = row
        return list(best.values())

    def browse_site_np_free(
        self,
        site: Any,
        pages: int = 1,
        spstates: Tuple[int, ...] = NP_FREE_SPSTATES,
        start_page: int = 0,
        stats: Optional[Dict[int, int]] = None,
    ) -> List[SiteCandidateTorrent]:
        """NexusPHP 直连：用站点 cookie 按 spstate 直接抓「免费」列表页。

        绕开 SDK ``browse``（它不暴露 spstate），自己拼 ``torrents.php?incldead=1&spstate=…``
        直接只取免费种 —— 免费是硬门槛，直接抓比「全抓回来再筛」省请求、也不易触发站内流控。

        安全：cookie 仍来自站点配置，且**只发给该站点自己的域名**，不落盘、不外传。
        任何异常 / 无结果时返回 ``[]``，由调用方回退到 SDK ``browse_site``。
        """
        out: List[SiteCandidateTorrent] = []
        seen: set = set()
        base = (getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}").rstrip("/")
        domain = getattr(site, "domain", "") or base
        cookie = getattr(site, "cookie", None)
        ua = getattr(site, "ua", None)
        if not base:
            return out
        try:
            from app.sdk.network import RequestUtils  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            logger.warning(f"NexusPHP 直连需要 SDK：{err}")
            return out

        req = RequestUtils(cookies=cookie, ua=ua, timeout=30, referer=f"{base}/")
        total_pages = max(int(pages or 1), 1)
        for sp in spstates:
            _sp_before = len(out)
            for p in range(total_pages):
                if out and _REQUEST_INTERVAL > 0:
                    time.sleep(_REQUEST_INTERVAL)
                url = f"{base}/torrents.php?incldead=1&spstate={sp}&page={int(start_page) + p}"
                try:
                    resp = req.get_res(url)
                except Exception as err:  # noqa: BLE001
                    logger.warning(f"NexusPHP 直连请求失败 {url}: {err}")
                    continue
                if resp is None:
                    continue
                try:
                    try:
                        text = resp.text or ""
                    except Exception:  # noqa: BLE001
                        text = ""
                    if not text:
                        raw = getattr(resp, "content", b"") or b""
                        try:
                            text = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            text = raw.decode("gbk", "ignore")
                finally:
                    try:
                        resp.close()
                    except Exception:  # noqa: BLE001
                        pass
                batch = self._parse_np_rows(text, domain, base, cookie, ua)
                for cand in batch:
                    key = cand.page_url or cand.title
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(cand)
                logger.info(
                    f"NexusPHP 直连 spstate={sp} page={int(start_page) + p} 本页 {len(batch)} 个，累计 {len(out)} 个"
                )
                # 空页即到底：免费列表通常只有 1 页，提前止步，不浪费请求。
                if not batch:
                    break
            if stats is not None:
                try:
                    stats[int(sp)] = len(out) - _sp_before
                except Exception:  # noqa: BLE001
                    pass
        return out

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
            # 注意：免费种子的 downloadvolumefactor 就是 0.0，不能用 `x or 1.0` 兜底
            # （0.0 是 falsy，会被错误地抬成 1.0 → 所有免费种子都被当成非免费）。
            _dv = getattr(torrent, "downloadvolumefactor", None)
            try:
                downloadvolumefactor = float(_dv) if _dv not in (None, "") else 1.0
            except (TypeError, ValueError):
                downloadvolumefactor = 1.0
            _uv = getattr(torrent, "uploadvolumefactor", None)
            try:
                uploadvolumefactor = float(_uv) if _uv not in (None, "") else 1.0
            except (TypeError, ValueError):
                uploadvolumefactor = 1.0

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
        return ts_to_age_weeks(pubdate_to_ts(pubdate))


# ============================================================
# 时间工具
# ============================================================

def pubdate_to_ts(pubdate: Any) -> float:
    """把发布时间（ISO 字符串 / 本地字符串 / datetime / 时间戳）转为 unix 秒；无效返回 0.0。

    口径：naive 时间按站点本地时区（UTC+8，``SITE_TZ``）处理，
    与候选 ``age_weeks`` 一致，保证「做种明细」与「候选排序」同一套 Ti。
    """
    if not pubdate:
        return 0.0
    try:
        if isinstance(pubdate, datetime):
            dt = pubdate if pubdate.tzinfo else pubdate.replace(tzinfo=SITE_TZ)
            return dt.timestamp()
        if isinstance(pubdate, (int, float)):
            v = float(pubdate)
            return v / 1000.0 if v > 1e12 else v
        text = str(pubdate).strip().replace('Z', '+00:00')
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
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SITE_TZ)
        return dt.timestamp()
    except Exception:
        return 0.0


def ts_to_age_weeks(ts: float) -> float:
    """unix 秒 → 距现在的周数（负数归 0）。"""
    if not ts:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc).timestamp() - float(ts)) / (7 * 86400))


# ============================================================
# 候选初筛
# ============================================================

@dataclass
class FilterPolicy:
    """魔流选种过滤策略。"""
    # 做种人数范围
    min_seeders: int = 0       # 最少做种人数（魔力角度，人越少越好）
    max_seeders: int = 99999   # 最多做种人数（过滤掉太热门的）
    min_leechers: int = 0      # 最少下载人数（刷流角度：有下载需求才值得下）

    # 种子大小范围（GB）
    min_size_gb: float = 0.0
    max_size_gb: float = 99999.0

    # 发布年龄范围（周）
    min_age_weeks: float = 0.0   # 最少发布多少周
    max_age_weeks: float = 999.0 # 最多发布多少周

    # 零魔处理
    exclude_zero_bonus: bool = True  # 排除零魔种子
    exclude_free: bool = False       # 排除免费种子

    # 免费要求（来自任务「免费」选项）
    free_only: bool = False          # 仅保留免费种子
    double_free_only: bool = False   # 仅保留双倍免费种子

    # H&R 处理
    exclude_hnr: bool = False  # 排除 H&R 种子

    # 发布时间范围（分钟，来自任务「发布时间（分钟）」；0=不限）
    pub_minutes_min: float = 0.0
    pub_minutes_max: float = 0.0

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

        # 下载人数过滤（刷流标准：下载者太少说明没需求，不值得下）
        elif policy.min_leechers > 0 and torrent.leechers < policy.min_leechers:
            reason = "下载人数低于下限"

        # 年龄过滤（MagicFlow 偏好老种子）
        elif torrent.age_weeks < policy.min_age_weeks:
            reason = "种子太新"
        elif torrent.age_weeks > policy.max_age_weeks:
            reason = "种子太老"

        # 零魔排除
        elif policy.exclude_zero_bonus and torrent.is_zero_bonus:
            reason = "零魔种子"

        # 免费排除 / 仅免费
        elif policy.exclude_free and torrent.is_free:
            reason = "免费种子"
        elif policy.double_free_only and not torrent.is_double_free:
            reason = "非双倍免费"
        elif policy.free_only and not torrent.is_free:
            reason = "非免费种子"

        # H&R 排除
        elif policy.exclude_hnr and torrent.hit_and_run:
            reason = "H&R 种子"

        # 发布时间范围（分钟）。年龄未知（age_weeks<=0）时不做限制，避免误杀。
        elif policy.pub_minutes_min > 0 and torrent.age_weeks > 0 and torrent.age_weeks * 10080 < policy.pub_minutes_min:
            reason = "发布时间过短"
        elif policy.pub_minutes_max > 0 and torrent.age_weeks > 0 and torrent.age_weeks * 10080 > policy.pub_minutes_max:
            reason = "发布时间过长"

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


def get_default_brush_filter_policy() -> FilterPolicy:
    """
    刷流模式的默认过滤策略（“刷流自己的标准”，与刷魔力的魔力口径相反）：

        - **不设做种人数上限**：热门大种正是上传主力，不能按“人少=魔力高”排除；
        - 做种人数下限 0（无做种也能抢流量）；
        - 体积、年龄不限；不排除零魔（零魔与上传无关）；
        - **要求有下载需求**：下载人数 ≥ min_leechers（默认 1）；
        - 免费要求仍由任务 `freeleech` 选项决定（free_only / double_free_only）。
    """
    return FilterPolicy(
        min_seeders=0,
        max_seeders=99999,
        min_leechers=1,
        min_size_gb=0.0,
        max_size_gb=99999.0,
        min_age_weeks=0.0,
        max_age_weeks=999.0,
        exclude_zero_bonus=False,
        exclude_free=False,
        exclude_hnr=False,
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
