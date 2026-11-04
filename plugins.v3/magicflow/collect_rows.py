"""魔流 · 站点列表页 → 候选种子（L0 解析层）。

**这是什么**：把站点「有哪些种可以下」这一层的**纯解析**收在一处 —— 列表页 HTML
/ API 返回的行 → ``SiteCandidateTorrent``。产物是「事实」（页面写了什么），不含任何
「要不要下」的裁决。

**为什么单独一层**（19.10.35）
- 原来这些散在 ``fetcher.py`` 里，和「翻页抓取 / SDK 调用 / 限流」混在一起。两者改的
  理由不同源：解析改是因为**站点换了皮肤**（NexusPHP 至少三套行结构，实测每加一站就要
  补一条正则），抓取改是因为**网络/配额策略变了**。放一起时每次调皮肤都得先绕开
  ``SiteFetcher`` 的构造与 ``_ensure_sdk()``。
- 只 import 标准库 → **能离线测**（``tools/test_collect_rows.py``）：喂一段真实列表页
  HTML，断言解析出的标题/促销/H&R/到期时间，不用起 MoviePilot、不用真站点。
- ``fetcher.py`` 反过来显式 re-export 本模块的公开名字，所有调用点零改动。

**边界**：这里只做「页面 → 候选」，不发请求、不看配额、不做筛选（筛选在
``fetcher.filter_candidates``，那是裁决）。
"""

import re
import time
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

# 站点页面上的「发布时间」是站点本地时间（国内 PT 站均为 UTC+8）。
# MoviePilot 容器时区同为 Asia/Shanghai，解析出的 naive 时间即本地时间，
# 因此换算 unix 秒时按 +8 处理（否则 Ti 会凭空年轻 8 小时，站点 A 严重偏低）。
SITE_TZ_OFFSET_HOURS = 8.0
SITE_TZ = timezone(timedelta(hours=SITE_TZ_OFFSET_HOURS))

# ============================================================
# 候选事实结构
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
    # ★ 3.44.0 API 站（馒头）：站点 id + API 端种子 id（下载直链入选时现取）
    site_id: int = 0
    api_tid: str = ""
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

# ============================================================
# 促销到期
# ============================================================


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

# ============================================================
# 促销词表（API 站）
# ============================================================


# ── M-Team（API 站）候选解析 ★ 3.44.0 ────────────────────────────
# ``discount`` 词表 → (下载系数, 上传系数)。实测馒头：FREE / PERCENT_50 / NORMAL。
MT_DISCOUNT: Dict[str, Tuple[float, float]] = {
    "FREE": (0.0, 1.0),
    "2X_FREE": (0.0, 2.0),
    "_2X_FREE": (0.0, 2.0),
    "PERCENT_50": (0.5, 1.0),
    "PERCENT_70": (0.7, 1.0),
    "2X": (1.0, 2.0),
    "_2X": (1.0, 2.0),
    "2X_PERCENT_50": (0.5, 2.0),
    "_2X_PERCENT_50": (0.5, 2.0),
    "NORMAL": (1.0, 1.0),
}


def mteam_promo(discount: Any) -> Tuple[float, float]:
    """M-Team ``discount`` → ``(downloadvolumefactor, uploadvolumefactor)``。

    ★ 3.44.0：词表为主，字符串兜底（含 ``FREE`` → 免费；含 ``2X`` → 双倍上传；
    含 ``PERCENT_50/70`` → 打折），未知取值一律当普通（1.0/1.0）——宁可少算免费。
    """
    key = str(discount or "").strip().upper()
    if key in MT_DISCOUNT:
        return MT_DISCOUNT[key]
    dvf, uvf = 1.0, 1.0
    if "PERCENT_50" in key:
        dvf = 0.5
    elif "PERCENT_70" in key:
        dvf = 0.7
    if "FREE" in key:
        dvf = 0.0
    if key.startswith("2X") or key.startswith("_2X"):
        uvf = 2.0
    return dvf, uvf


# ── 叶PT（YemaPT）开放 API 词表（3.45.0）────────────────────────────
# downloadPromotion：none / half / free；uploadPromotion：none / one_half / double_upload
YEMA_DOWN: Dict[str, float] = {"FREE": 0.0, "HALF": 0.5, "NONE": 1.0}
YEMA_UP: Dict[str, float] = {"DOUBLE_UPLOAD": 2.0, "ONE_HALF": 1.5, "NONE": 1.0}


def yema_promo(download: Any, upload: Any) -> Tuple[float, float]:
    """叶PT 促销文案 → ``(downloadvolumefactor, uploadvolumefactor)``。

    词表为主，字符串兜底；未知值一律当普通（1.0/1.0）——宁可少算免费。
    """
    dk = str(download or "").strip().upper()
    uk = str(upload or "").strip().upper()
    dvf = YEMA_DOWN.get(dk)
    if dvf is None:
        dvf = 0.0 if ("FREE" in dk or "免费" in dk) else (0.5 if "HALF" in dk else 1.0)
    uvf = YEMA_UP.get(uk)
    if uvf is None:
        uvf = 2.0 if "DOUBLE" in uk else (1.5 if "HALF" in uk else 1.0)
    return float(dvf), float(uvf)

# ============================================================
# API 站行 → 候选
# ============================================================


def _age_weeks_from_text(created: Any) -> float:
    """任意时间文本 → 做种周数（容错多种格式；解析不了返回 0）。"""
    raw = str(created or "").strip()
    if not raw:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            text = raw.replace("Z", "+0000") if "%z" in fmt else raw
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SITE_TZ)
            return max((time.time() - dt.timestamp()) / (7 * 86400.0), 0.0)
        except Exception:  # noqa: BLE001, PERF203
            continue
    return 0.0


def parse_yema_rows(
    rows: Any,
    *,
    site_name: str = "",
    domain: str = "",
    site_url: str = "",
    site_id: int = 0,
    site_proxy: bool = False,
) -> List[SiteCandidateTorrent]:
    """叶PT（YemaPT）``fetchOpenTorrentList`` 的行 → 候选项。

    ★ 3.45.0：与馒头一样留空 hash/直链（下载凭证入选时现取）。
    额外好处：``hrPunishEnable`` 是该站的**权威 H&R 标记**，直接照抄事实。
    """
    out: List[SiteCandidateTorrent] = []
    base = str(site_url or "").rstrip("/")

    def _i(v: Any) -> int:
        try:
            return int(float(v or 0))
        except (TypeError, ValueError):
            return 0

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("id") or "").strip()
        if not tid:
            continue
        dvf, uvf = yema_promo(row.get("downloadPromotion"), row.get("uploadPromotion"))
        listing = str(row.get("listingTime") or "")
        free_until = str(row.get("downloadPromotionEndTime") or "") if dvf == 0.0 else ""
        try:
            size = float(row.get("fileSize") or 0)
        except (TypeError, ValueError):
            size = 0.0
        out.append(
            SiteCandidateTorrent(
                hash="",
                title=str(row.get("showName") or "").strip(),
                size=size,
                seeders=_i(row.get("seedNum")),
                leechers=_i(row.get("leechNum")),
                pubdate=listing,
                age_weeks=_age_weeks_from_text(listing),
                page_url=f"{base}/torrent/{tid}" if base else "",
                enclosure="",
                site_name=str(site_name or ""),
                site_domain=str(domain or ""),
                site_id=int(site_id or 0),
                api_tid=tid,
                is_free=(dvf == 0.0),
                is_double_free=(dvf == 0.0 and uvf == 2.0),
                hit_and_run=bool(row.get("hrPunishEnable")),
                volume_factor=dvf,
                downloadvolumefactor=dvf,
                uploadvolumefactor=uvf,
                site_proxy=bool(site_proxy),
                free_until=free_until,
                free_remaining_sec=promo_remaining_sec(free_until) if free_until else -1.0,
            )
        )
    return out


def _mteam_age_weeks(created: Any) -> float:
    """M-Team ``createdDate`` → 做种周数（解析不了返回 0）。

    为什么不复用 ``_age_weeks_from_text``：馒头这个字段**恒**是 ``YYYY-MM-DD HH:MM:SS``
    （无时区后缀、无 ISO 变体），单格式直取比多格式回退快；多格式那张表用在叶PT 那种
    各家自己发挥的时间文本上。两者语义相同，取样路径不同。
    """
    try:
        dt = datetime.strptime(str(created).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=SITE_TZ)
        return max((time.time() - dt.timestamp()) / (7 * 86400.0), 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def parse_mteam_rows(
    rows: Any,
    *,
    site_name: str = "",
    domain: str = "",
    site_url: str = "",
    site_id: int = 0,
    site_proxy: bool = False,
) -> List[SiteCandidateTorrent]:
    """M-Team ``/torrent/search`` 的行 → 候选项。

    ★ 3.44.0：API 站没有 RSS/enclosure，**下载直链留到入选时**用
    ``/torrent/genDlToken`` 现取（插件 ``_cand_enclosure``），这里只放 ``api_tid``；
    ``infoHash`` 在 API 里为 null，故 ``hash`` 留空（真 hash 由取回的 .torrent 算）。
    """
    out: List[SiteCandidateTorrent] = []
    base = str(site_url or "").rstrip("/")

    def _i(v: Any) -> int:
        try:
            return int(float(v or 0))
        except (TypeError, ValueError):
            return 0

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("id") or "").strip()
        if not tid:
            continue
        st = row.get("status") if isinstance(row.get("status"), dict) else {}
        dvf, uvf = mteam_promo(st.get("discount"))
        created = str(row.get("createdDate") or "")
        free_until = str(st.get("discountEndTime") or "") if dvf == 0.0 else ""
        try:
            size = float(row.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        out.append(
            SiteCandidateTorrent(
                hash="",
                title=str(row.get("name") or "").strip(),
                size=size,
                seeders=_i(st.get("seeders")),
                leechers=_i(st.get("leechers")),
                pubdate=created,
                age_weeks=_mteam_age_weeks(created),
                page_url=f"{base}/detail/{tid}" if base else "",
                enclosure="",
                site_name=str(site_name or ""),
                site_domain=str(domain or ""),
                site_id=int(site_id or 0),
                api_tid=tid,
                is_free=(dvf == 0.0),
                is_double_free=(dvf == 0.0 and uvf == 2.0),
                hit_and_run=False,
                volume_factor=dvf,
                downloadvolumefactor=dvf,
                uploadvolumefactor=uvf,
                site_proxy=bool(site_proxy),
                free_until=free_until,
                free_remaining_sec=promo_remaining_sec(free_until) if free_until else -1.0,
            )
        )
    return out

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

# ============================================================
# NexusPHP 列表页 → 候选（三套皮肤自适应）
# ============================================================


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

# ★ 皮肤差异：CHD / 新版 Tailwind 系（hdtime、cspt 等）不用 promotion class，
#   而是 <img class="pro_free"> / <img class="pro_free2up"> 标促销 —— 映射到同一套系数。
_NP_PRO_CLASSES: Dict[str, Tuple[float, float]] = {
    "pro_free": (0.0, 1.0),       # 免费
    "pro_free2up": (0.0, 2.0),    # 免费 + 2X 上传
    "pro_2up": (1.0, 2.0),        # 2X 上传
    "pro_2up50pct": (0.5, 2.0),   # 2X 上传 + 50% 下载
    "pro_halfdown": (0.5, 1.0),
    "pro_50pct": (0.5, 1.0),
    "pro_50pctdown": (0.5, 1.0),   # dstudio 等：50% 下载（非免费，别当免费）
    "pro_30pctdown": (0.7, 1.0),
    "pro_25pctdown": (0.75, 1.0),
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

def parse_np_rows(
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
        # ★ 19.7.67 文字促销兜底：HDDolby 一类皮肤把「50%」写在文字里、
        #   class 仍给 pro_free（或干脆没有促销 class）——只看 class 会误判为免费。
        #   只要这一行出现 25%~75% 的百分比促销，就以文字为准（下载仍计费）。
        if dv == 0.0:
            _pm = re.search(r"(?<!\d)(25|30|50|70|75)\s*%", chunk)
            if _pm:
                dv = {"75": 0.25, "70": 0.3, "50": 0.5, "30": 0.7, "25": 0.75}[_pm.group(1)]
                uv = max(uv, 1.0)

        # ★ 17.2.2：逐种 H&R 标签（carpt / dstudio 同皮肤）——
        #   ``<img class="hitandrun" src="pic/trans.gif" alt="H&R" title="H&R" />``。
        #   实测（2026-10-14）：carpt.net 每行都带（站点级 H&R，102/102 行）；
        #   dstudio.me 只在少数种子带（rules.php：「本站很少有种子存在 H&R，
        #   有 H&R 的种子，会显示黑色标签」）。
        #   这里只读**页面事实**：读到 → True；读不到 → False（不推断、不补默认）。
        hit_and_run = bool(re.search(r"class=['\"]hitandrun['\"]", chunk))

        # ★ 促销到期（限时免费）：紧跟在促销标记后的 <span title="YYYY-MM-DD HH:MM:SS">
        free_until = ""
        free_remaining_sec = -1.0
        if promo:
            _em = re.search(
                r"promotion\s+%s['\"]\s*>[^<]*</font>\s*<span\s+title=[\"']"
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[\"']" % re.escape(promo),
                chunk,
            )
            if not _em:
                # ★ 皮肤差异（dstudio 等）：到期时间不在促销标记后，而是单独一行
                #   ``<font color=...>剩余时间：<span title="YYYY-MM-DD HH:MM:SS">2天0时</span></font>``
                #   读不到 → 「限时免费闸门」失效 → 会把马上到期的免费种下回来（下了就白烧流量）。
                _em = re.search(
                    r"剩余时间[：:]\s*<span[^>]*title=[\"']"
                    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[\"']",
                    chunk,
                )
            if _em:
                free_until = _em.group(1)
                free_remaining_sec = promo_remaining_sec(free_until)

        # 添加时间（列表页 <span title="YYYY-MM-DD HH:MM:SS">）
        # ★ 皮肤差异：dstudio 等把「免费到期时间」也写成同样的 span 且排在前面 →
        #   必须优先取明确的「时间单元格」，并排除「剩余时间」旁边那个，
        #   否则免费种会被算成刚发布（age_weeks=0 → 魔力公式 Ti 全按 0 算）。
        pubdate = None
        _dm = re.search(
            r'class=["\'][^"\']*(?:torrent-cell-time|torrent-info-text-added)[^"\']*["\'][^>]*>'
            r'\s*<span[^>]*title=["\'](\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})["\']',
            chunk,
        )
        if not _dm:
            _expiry_dates = set(
                re.findall(
                    r"剩余时间[：:]\s*<[^>]*>?\s*<span[^>]*title=[\"']"
                    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[\"']",
                    chunk,
                )
            )
            if promo:
                _em2 = re.search(
                    r"promotion\s+%s['\"]\s*>[^<]*</font>\s*<span\s+title=[\"']"
                    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[\"']" % re.escape(promo),
                    chunk,
                )
                if _em2:
                    _expiry_dates.add(_em2.group(1))
            for _dm in re.finditer(
                r'<span\s+title=["\'](\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})["\']', chunk
            ):
                if _dm.group(1) not in _expiry_dates:
                    pubdate = _dm.group(1)
                    break
        else:
            pubdate = _dm.group(1)

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
            hit_and_run=hit_and_run,
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

# ============================================================
# 时间换算
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
