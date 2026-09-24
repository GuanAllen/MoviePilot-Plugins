"""
站点魔力公式获取（通用 NexusPHP）

从站点 ``mybonus.php`` 抓取魔力公式与参数：

* 公式表达式：``<img title="A = ...">`` / ``<img title="B = ...">``
* 参数（legend）：``T0 / N0 / B0 / L / Wi``
* 附加系数：官种加成 / 后宫加成 / 做种数上限 / 每做种基础 / 当前时魔与 A 值

标准 NexusPHP 站零配置即可命中；改过公式的站再用
``sites.register_formula_preset`` 单独覆盖。

设计：
* ``parse_nexusphp_formula`` 是**纯函数**（无 MoviePilot 依赖），可离线单测；
* ``fetch_site_formula`` 才惰性 import MoviePilot SDK（``RequestUtils``），
  cookie 直接取自 MoviePilot 站点配置，**不用手动管理 cookie**。
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..bonus import BonusParams

# legend 里的参数键 → BonusParams 字段
_PARAM_KEYS = (
    ("T0", "t0"),
    ("N0", "n0"),
    ("B0", "b0"),
    ("L", "l"),
)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
)


@dataclass
class FormulaCapture:
    """一次公式抓取的完整结果。"""

    expr_a: Optional[str] = None          # A 公式原始表达式
    expr_b: Optional[str] = None          # B 公式原始表达式
    params: Dict[str, float] = field(default_factory=dict)   # t0/n0/b0/l/zero_weight/normal_weight
    extra: Dict[str, Any] = field(default_factory=dict)      # 官种/后宫/上限/基础/当前时魔
    source: str = ""                      # 来源（mybonus.php / default）
    ok: bool = False                      # 是否成功解析到有效内容
    note: str = ""                        # 诊断说明

    def to_params(self, base: Optional[BonusParams] = None) -> BonusParams:
        """把抓取到的参数叠加到 base（默认标准 NexusPHP 参数）上。"""
        base = base or BonusParams()
        overrides = {
            key: self.params[key]
            for key in ("t0", "n0", "b0", "l", "zero_weight", "normal_weight")
            if key in self.params
        }
        for extra_key, param_key in (
            ("official_coef", "official_coef"),
            ("harem_coef", "harem_coef"),
            ("per_torrent_flat", "per_torrent_flat"),
            ("seeding_count_cap", "seeding_count_cap"),
        ):
            if extra_key in self.extra and self.extra[extra_key] is not None:
                overrides[param_key] = self.extra[extra_key]
        return base.merged(**overrides)

    def as_dict(self) -> Dict[str, Any]:
        """转为可 JSON 序列化的字典（供诊断端点返回）。"""
        return {
            "ok": self.ok,
            "source": self.source,
            "note": self.note,
            "expr_a": self.expr_a,
            "expr_b": self.expr_b,
            "params": dict(self.params),
            "extra": dict(self.extra),
            "resolved": {
                "t0": self.to_params().t0,
                "n0": self.to_params().n0,
                "b0": self.to_params().b0,
                "l": self.to_params().l,
                "zero_weight": self.to_params().zero_weight,
                "normal_weight": self.to_params().normal_weight,
                "official_coef": self.to_params().official_coef,
                "harem_coef": self.to_params().harem_coef,
            },
        }


def _strip_tags(text: str) -> str:
    """去标签 + 实体解码 + 折叠空白，用于 legend 文本抽取。"""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    return re.sub(r"[ \t\r\n\u00a0]+", " ", text)


def _to_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_nexusphp_formula(html_text: str) -> FormulaCapture:
    """从 NexusPHP ``mybonus.php`` 页面文本解析公式与参数（纯函数）。"""
    cap = FormulaCapture(source="mybonus.php")
    if not html_text:
        cap.note = "空页面"
        return cap

    # 1) 公式表达式：<img title="A = ..."> / <img title="B = ...">
    m_a = re.search(r'title\s*=\s*"(A\s*=\s*[^"]+)"', html_text, re.I)
    if m_a:
        cap.expr_a = m_a.group(1).strip()
    m_b = re.search(r'title\s*=\s*"(B\s*=\s*[^"]+)"', html_text, re.I)
    if m_b:
        cap.expr_b = m_b.group(1).strip()

    text = _strip_tags(html_text)

    # 2) legend 参数：T0 / N0 / B0 / L
    for key, fld in _PARAM_KEYS:
        m = re.search(rf"\b{re.escape(key)}\b\s*=\s*([\d.]+)", text)
        val = _to_float(m.group(1)) if m else None
        if val is not None:
            cap.params[fld] = val

    # 3) 权重：普通 Wi 默认 1，零魔 0.2
    m_norm = re.search(r"权重系数[^。]{0,40}?默认为\s*([\d.]+)", text) or re.search(
        r"\bWi\b[^。]{0,40}?默认为\s*([\d.]+)", text
    )
    norm = _to_float(m_norm.group(1)) if m_norm else None
    if norm is not None:
        cap.params["normal_weight"] = norm
    m_zero = re.search(r"零魔[^0-9]{0,12}?([\d.]+)", text)
    zero = _to_float(m_zero.group(1)) if m_zero else None
    if zero is not None:
        cap.params["zero_weight"] = zero

    # 4) 附加系数
    extra: Dict[str, Any] = {}
    m = re.search(r"官种系数[:：为]*\s*([\d.]+)", text)
    if m:
        extra["official_coef"] = _to_float(m.group(1))
    m = re.search(r"后宫加成系数[:：为，,、\s]*当前[值为:：]*\s*([\d.]+)", text)
    if m:
        extra["harem_coef"] = _to_float(m.group(1))
    m = re.search(r"做种数最多计\s*(\d+)\s*个", text)
    if m:
        extra["seeding_count_cap"] = int(m.group(1))
    m = re.search(r"([\d.]+)\s*个魔力值\s*\*\s*你的做种数", text)
    if m:
        extra["per_torrent_flat"] = _to_float(m.group(1))
    m = re.search(
        r"当前每小时能获取\s*([\d,.]+)\s*个魔力值\s*\(\s*A\s*=\s*([\d,.]+)\s*\)",
        text,
    )
    if m:
        extra["current_bonus_per_hour"] = _to_float(m.group(1))
        extra["current_a"] = _to_float(m.group(2))
    cap.extra = {k: v for k, v in extra.items() if v is not None}

    cap.ok = bool(cap.expr_a or cap.expr_b or cap.params)
    if not cap.ok:
        cap.note = "未解析到公式或参数（可能非标准 NexusPHP 页面）"
    return cap


def fetch_site_formula(site: Any, timeout: int = 30) -> FormulaCapture:
    """
    用 MoviePilot SDK 抓取站点 ``mybonus.php`` 并解析公式。

    cookie/UA 直接取自 MoviePilot 站点配置（``Site``），无需手动管理。

    Args:
        site: MoviePilot ``Site`` 对象（含 domain/url/cookie/ua）。
        timeout: 请求超时（秒）。

    Returns:
        FormulaCapture
    """
    domain = (getattr(site, "domain", "") or "").strip()
    base = (getattr(site, "url", "") or (f"https://{domain}" if domain else "")).rstrip("/")
    cookie = getattr(site, "cookie", None)
    ua = getattr(site, "ua", None) or _DEFAULT_UA

    if not base:
        return FormulaCapture(source="mybonus.php", note="站点缺少 url/domain")

    url = f"{base}/mybonus.php"
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433 (惰性导入)
    except Exception as err:  # MoviePilot SDK 不可用（如离线单测）
        return FormulaCapture(source="mybonus.php", note=f"SDK 不可用: {err}")

    try:
        req = RequestUtils(cookies=cookie, ua=ua, timeout=timeout, referer=f"{base}/")
        resp = req.get_res(url)
    except Exception as err:
        return FormulaCapture(source="mybonus.php", note=f"请求失败: {err}")

    if resp is None or not getattr(resp, "ok", False):
        code = getattr(resp, "status_code", "?")
        return FormulaCapture(source="mybonus.php", note=f"HTTP {code}")

    try:
        raw = resp.content
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", "ignore")
    finally:
        try:
            resp.close()
        except Exception:
            pass

    cap = parse_nexusphp_formula(text)
    cap.note = f"{domain} mybonus.php ({len(text)} bytes)"
    return cap


def acquire_site_params(site: Any, base: Optional[BonusParams] = None) -> BonusParams:
    """抓取站点公式并返回解析后的 ``BonusParams``（失败则回落 base/默认）。"""
    cap = fetch_site_formula(site)
    return cap.to_params(base) if cap.ok else (base or BonusParams())


# ============================================================
# 用户做种列表 → 每种子「发布时间」（用于 Ti 发布时长口径 / 存量回填）
# ============================================================

_TITLE_ATTR_RE = re.compile(r'details\.php\?id=\d+[^>]*title="([^"]+)"', re.I)
_TITLE_TEXT_RE = re.compile(r'<a[^>]+details\.php\?id=\d+[^>]*>(.*?)</a>', re.I | re.S)
_DT_RE = re.compile(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})')
_SIZE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB|PB)\b', re.I)
_SIZE_UNIT = {'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'TB': 1024 ** 4, 'PB': 1024 ** 5}


def _norm_title(title: str) -> str:
    """标题规范化（供做种页标题与下载器标题匹配）。"""
    t = (title or '').lower()
    t = re.sub(r'^\[[^\]]*\]', '', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def parse_seeding_list(html_text: str) -> list:
    """解析 ``getusertorrentlistajax.php?type=seeding`` 页面。

    返回 ``[{'title':..., 'title_norm':..., 'size_bytes':int, 'pubdate':'YYYY-MM-DD HH:MM:SS'}, ...]``。
    """
    out = []
    if not html_text:
        return out
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.S):
        if 'details.php' not in row:
            continue
        m = _TITLE_ATTR_RE.search(row) or _TITLE_TEXT_RE.search(row)
        if not m:
            continue
        title = _html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', row))
        md = _DT_RE.search(text)
        ms = _SIZE_RE.search(text)
        if not (title and md):
            continue
        size_bytes = 0
        if ms:
            size_bytes = int(float(ms.group(1)) * _SIZE_UNIT.get(ms.group(2).upper(), 0))
        out.append({
            'title': title,
            'title_norm': _norm_title(title),
            'size_bytes': size_bytes,
            'pubdate': f"{md.group(1)} {md.group(2)}",
        })
    return out


def parse_seeding_list_pubdates(html_text: str) -> Dict[str, str]:
    """兼容旧接口：返回 {规范化标题: 'YYYY-MM-DD HH:MM:SS'}。"""
    return {r['title_norm']: r['pubdate'] for r in parse_seeding_list(html_text)}


def fetch_seeding_list(site: Any, userid: Any, timeout: int = 25) -> list:
    """抓取用户做种列表页，返回 ``parse_seeding_list`` 的结果。cookie/UA 取自站点配置。"""
    domain = (getattr(site, "domain", "") or "").strip()
    base = (getattr(site, "url", "") or (f"https://{domain}" if domain else "")).rstrip("/")
    cookie = getattr(site, "cookie", None)
    ua = getattr(site, "ua", None) or _DEFAULT_UA
    if not base or not userid:
        return []
    url = f"{base}/getusertorrentlistajax.php?userid={int(userid)}&type=seeding"
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433
    except Exception:
        return []
    try:
        req = RequestUtils(cookies=cookie, ua=ua, timeout=timeout, referer=f"{base}/")
        resp = req.get_res(url)
    except Exception:
        return []
    if resp is None or not getattr(resp, "ok", False):
        try:
            resp and resp.close()
        except Exception:
            pass
        return []
    try:
        raw = resp.content
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", "ignore")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    return parse_seeding_list(text)


def fetch_seeding_pubdates(site: Any, userid: Any, timeout: int = 25) -> Dict[str, str]:
    """兼容旧接口：抓取并返回 {规范化标题: 发布时间字符串}。"""
    return {r['title_norm']: r['pubdate'] for r in fetch_seeding_list(site, userid, timeout)}


def refresh_site_preset(site: Any) -> FormulaCapture:
    """
    抓取站点公式并写入 ``sites`` 参数预设缓存（供 ``get_formula_params`` 命中）。

    以域名（及名称）为键注册，后续 ``get_formula_params(domain=...)`` 即返回本站参数。
    """
    cap = fetch_site_formula(site)
    if cap.ok:
        from . import register_formula_preset

        keys = {
            (getattr(site, "domain", "") or "").strip().lower(),
            (getattr(site, "name", "") or "").strip().lower(),
        }
        overrides = {
            k: cap.params[k]
            for k in ("t0", "n0", "b0", "l", "zero_weight", "normal_weight")
            if k in cap.params
        }
        for key in keys:
            if key:
                register_formula_preset(key, **overrides)
    return cap
