"""魔流 · 采集模块（collect）—— **唯一**外部取数/取网出口。

设计（Master 2026-09-29 定稿，见 ``docs/PLAN-collect.md``）：

    采集（传输）  →  事实  →  裁决（规则/标签/评分）  →  决策（各功能）
    collect.py        facts        rules/tags/bonus         brush/swap/crossseed

五条铁律：

1. **采集就一个人干**：抓 + **解析** + 配额 + 缓存 + 事实库，全归这里；别人只拿。
2. **采集也是唯一的手**：全仓只有它碰网络（拿数据 + 执行动作都经它）。
3. **不判断**：促销免不免费是事实；该不该删 / 今天签不签是判断（留在各功能模块）。
4. **每一次站点请求都过闸门**（预算不足/被熔断 → 直接不发请求）。
5. **采集者必须登记**（``observe()``：谁在抓、抓什么、花了几 PV、命中率）。

省 PV 三原则：

- **一次抓全**：一个页面能拿的事实，绝不为不同字段再抓一次（解析出整份事实）。
- **一轮一抓**：缓存键 = 规范化 URL + 全局 single-flight；同轮同 URL 只允许 1 次真实请求。
- **一个出口**：站点请求只能出自本模块的 ``Http``；一个页面只有一个采集器。

边界（不做什么）：任务配置 / 标签账本 / 评分公式 / H&R 义务 / 换种收益 / 删除暂停动作 /
任何「该不该」的结论 —— 一律不进这里。本模块只吃一个 plugin 引用，**不反向依赖业务模块**。
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── 采集类型白名单（配额分账用；新增类型必须显式登记）────────────────────────
SCOPE_SITE = "site"        # 吃站点 PV
SCOPE_SERVICE = "service"  # 外部服务配额（豆瓣/IYUU/OpenList）
SCOPE_LOCAL = "local"      # 本机（MP / 下载器 / 磁盘），不吃 PV

KIND_TTL: Dict[str, float] = {
    "browse": 240.0,      # 候选列表
    "live": 240.0,        # 站点实时值（用户栏页）
    "leeching": 120.0,    # 「正在下载」列表
    "signin": 60.0,       # 签到页（当日结果与页面文案）
    "passkey": 0.0,       # 抽到就落 durable，不走 TTL 缓存
    "sitecap": 86400.0,   # 框架/能力识别
    "rules": 604800.0,    # 站点规则页
    "official": 604800.0, # 官方规则说明页
    "promo": 60.0,        # 单种促销状态页（变化快）
    "seeding": 120.0,     # 用户做种列表
    "formula": 604800.0,  # 魔力公式页
    "exam": 3600.0,       # 考核页
    "debug": 0.0,         # 调试抓页（不缓存）
    # ★ 3.42.0：API 鉴权站（馒头 x-api-key）—— 不抓网页，走站点后台 API
    "api": 300.0,
    # ★ 3.41.0：收件箱 / 欢迎短讯（H&R 的**唯一自动来源**，Master 定调）
    "inbox": 21600.0,     # 收件箱列表（6h）
    "welcome": 604800.0,  # 欢迎短讯正文（7d，基本不变）
}
# 每站每日硬上限（0 = 不限，交给站点 PV 预算管）；签到一天最多一次是事实
KIND_DAY_CAP: Dict[str, int] = {"signin": 2}

# 站点「每日访问次数已达上限」拦截页特征
PV_LIMIT_MARKERS = ("访问次数已达上限", "访问次数已达", "今日访问次数")
PV_BLOCK_GRACE = 600.0

INBOX_PAGE = "/messages.php"
MAIL_PAGE = "/messages.php?action=viewmessage&id={mid}"
# 「欢迎来**」主题特征（NexusPHP 注册欢迎短讯）
_WELCOME_SUBJ_RE = re.compile(r"欢迎|welcome|注册成功|新人", re.I)
_MAIL_ROW_RE = re.compile(
    r"viewmessage(?:&amp;|&)id=(\d+)[^>]*>\s*([^<]{0,80})", re.I
)
# 邮件正文的**结束**标记（注意：不能把紧随主题的「收件箱/发件箱」表头当结尾）
_MAIL_FOOT_RE = re.compile(r"删除.*转发|转发短讯|短讯箱|\[\s*删除\s*\]")
# 邮件页面里的界面噪声行（表头/时间戳），正文里不该有
_MAIL_NOISE = {"收件箱", "发件箱", "自", "日期", "系统", "搜索短讯", "短讯箱", "MESSAGES", "短讯"}
_MAIL_TIME_RE = re.compile(
    r"^(?:\d+\s*(?:天|日|小时|時|分钟|分|秒))+\s*前$|^信息来自|^\d+\s*分钟前$"
)


# ── API 鉴权站（通道表驱动）────────────────────────────────────────────
# ★ 3.42.0 馒头接入；★ 3.45.0 抽成「通道表」（conf/frameworks.yml → api_channels）。
API_SITE_MARKERS = ("m-team",)  # 兼容旧调用；真值源是通道表


def _api_channels() -> Dict[str, Any]:
    """通道表：优先 YAML（``conf/frameworks.yml`` → ``api_channels``），读不到用代码兜底。"""
    try:
        try:
            from . import rulepack as _rp  # noqa: WPS433
        except ImportError:
            import rulepack as _rp  # type: ignore  # noqa: WPS433

        ch = _rp.api_channels()
        if isinstance(ch, dict) and ch:
            return ch
        fb = _rp.api_channels_fallback()
        if isinstance(fb, dict) and fb:
            return fb
    except Exception:  # noqa: BLE001
        pass
    return dict(_API_CHANNELS_FALLBACK)


def _site_domain(site: Any) -> str:
    dom = str(getattr(site, "domain", "") or "").strip().lower()
    if not dom:
        try:
            from urllib.parse import urlsplit  # noqa: WPS433

            dom = str(urlsplit(str(getattr(site, "url", "") or "")).hostname or "").lower()
        except Exception:  # noqa: BLE001
            dom = ""
    return dom


def api_channel(site: Any) -> Tuple[str, Dict[str, Any]]:
    """★ 3.45.0 命中哪个 API 通道 → ``(通道名, 通道配置)``；没命中返回 ``("", {})``。

    只看「域名 / URL / 站名」里的 markers，不做别的判断（采集层不判断）。
    """
    try:
        blob = " ".join(
            [
                str(getattr(site, "domain", "") or ""),
                str(getattr(site, "url", "") or ""),
                str(getattr(site, "name", "") or ""),
            ]
        ).lower()
        for cname, cfg in (_api_channels() or {}).items():
            if not isinstance(cfg, dict):
                continue
            mk = cfg.get("markers") or []
            if any(str(m).strip().lower() in blob for m in mk if str(m).strip()):
                return str(cname).strip().lower(), cfg
    except Exception:  # noqa: BLE001
        pass
    return "", {}


def is_api_site(site: Any) -> bool:
    """★ 3.42.0：这个站是「API 鉴权站」吗（走 API 通道，不靠网页 cookie）。"""
    try:
        tname, cfg = api_channel(site)
        if not tname or not cfg:
            return False
        field = str(((cfg.get("auth") or {}).get("field")) or "apikey")
        return bool(str(getattr(site, field, "") or "").strip())
    except Exception:  # noqa: BLE001
        return False


def api_base(site: Any) -> str:
    """API 根地址（按通道模板渲染）：馒头 ``https://api.<domain>/api``；叶PT 固定域名。"""
    _tname, cfg = api_channel(site)
    tmpl = str((cfg or {}).get("base") or "")
    if not tmpl:
        return ""
    dom = _site_domain(site)
    su = str(getattr(site, "url", "") or "").rstrip("/")
    try:
        return tmpl.format(domain=dom, host=dom, site_url=su).rstrip("/")
    except Exception:  # noqa: BLE001
        return tmpl.rstrip("/")


def api_endpoint(site: Any, key: str) -> Dict[str, Any]:
    """★ 3.45.0 取通道里某个逻辑端点的配置（``profile`` / ``list`` / ``search`` / ``dl`` …）。"""
    _tname, cfg = api_channel(site)
    eps = (cfg or {}).get("endpoints") or {}
    ep = eps.get(str(key or "").strip().lower())
    return dict(ep) if isinstance(ep, dict) else {}


def exam_rule(site: Any) -> Dict[str, Any]:
    """★ 5.8.0：通道表里的「规则式考核」（站点不给考核区块，但官方标准是固定阈值）。

    形如 ``{"window_days": 30, "metrics": [{"field": "upload", "target": 32212254720, ...}]}``；
    数据取自**官方 API 白名单字段**，没配返回 ``{}``。
    """
    _tname, cfg = api_channel(site)
    ep = (cfg or {}).get("exam_rule") or {}
    return dict(ep) if isinstance(ep, dict) else {}


def exam_api(site: Any) -> Dict[str, Any]:
    """★ 5.7.0：通道表里的「考核接口」（JS 单页站的考核只能从后台接口读）。

    形如 ``{"path": "/api/user/profile", "field": "examTask", "metrics": {...}}``；
    没配就返回 ``{}``（**不猜** —— 读不到就是读不到，绝不编造考核）。
    """
    _tname, cfg = api_channel(site)
    ep = (cfg or {}).get("exam_api") or {}
    return dict(ep) if isinstance(ep, dict) else {}


def api_dl_url(site: Any, payload: Any) -> str:
    """★ 3.45.0 下载凭证 → 直链：有 ``dl_url`` 模板就套模板（叶PT），否则凭证本身就是直链（馒头）。"""
    _tname, cfg = api_channel(site)
    tmpl = str((cfg or {}).get("dl_url") or "")
    token = str(payload or "").strip()
    if not token:
        return ""
    if not tmpl:
        return token
    try:
        from urllib.parse import quote  # noqa: WPS433

        return tmpl.format(key=quote(token, safe=""))
    except Exception:  # noqa: BLE001
        return tmpl.replace("{key}", token)


_API_CHANNELS_FALLBACK: Dict[str, Any] = {
    "mteam": {
        "markers": ["m-team", "mteam"],
        "base": "https://api.{domain}/api",
        "auth": {"header": "x-api-key", "field": "apikey", "prefix": ""},
        "envelope": {"ok_field": "code", "ok_value": "0", "err_field": "message"},
        "body": "json",
        "endpoints": {
            "profile": {"path": "/member/profile", "body": "json"},
            "search": {"path": "/torrent/search", "body": "json"},
            "detail": {"path": "/torrent/detail", "body": "form", "param": "id"},
            "dl": {"path": "/torrent/genDlToken", "body": "form", "param": "id"},
        },
    },
    "yemapt": {
        "markers": ["yemapt"],
        "base": "https://www.yemapt.org/openApi",
        "auth": {"header": "Authorization", "field": "apikey", "prefix": ""},
        "envelope": {"ok_field": "success", "ok_value": True, "err_field": "errorMessage"},
        "body": "json",
        "endpoints": {
            "profile": {"path": "/user/fetchBasicInfo.json", "body": "json"},
            "list": {"path": "/torrent/fetchOpenTorrentList.json", "body": "json"},
            "dl": {"path": "/torrent/generateDownloadKey.json", "body": "json", "param": "id"},
            "hash": {"path": "/torrent/fetchTorrentIdWithPiecesHash.json", "body": "json"},
        },
        "dl_url": "https://www.yemapt.org/api/torrent/download1?token={key}",
    },
}


def _num(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_mail_list(html_text: Any) -> List[Tuple[str, str]]:
    """收件箱列表 → ``[(短讯 id, 主题), …]``（事实，不做判断）。"""
    t = str(html_text or "")
    if not t:
        return []
    out: List[Tuple[str, str]] = []
    seen = set()
    for mid, subj in _MAIL_ROW_RE.findall(t):
        mid = str(mid).strip()
        subj = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(subj))).strip()
        if not mid or mid in seen or not subj:
            continue
        seen.add(mid)
        out.append((mid, subj))
    return out


def pick_welcome_mail(rows: Any) -> Optional[Tuple[str, str]]:
    """从短讯列表里挑「欢迎短讯」（挑不到 → None；**不猜**）。"""
    for mid, subj in (rows or []):
        if _WELCOME_SUBJ_RE.search(str(subj or "")):
            return str(mid), str(subj)
    return None


_MAIL_LINK_RE = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)


def parse_mail_links(html_text: Any) -> List[Dict[str, str]]:
    """短讯页面里的链接 → ``[{"href","label"}]``（去重保序；**事实**，不挑不筛）。"""
    t = str(html_text or "")
    if not t:
        return []
    out: List[Dict[str, str]] = []
    seen = set()
    for href, label in _MAIL_LINK_RE.findall(t):
        href = str(href or "").strip()
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(label or ""))).replace("&nbsp;", " ").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript"):
            continue
        key = (href, label)
        if key in seen:
            continue
        seen.add(key)
        out.append({"href": href, "label": label[:60]})
    return out


def parse_mail_body(html_text: Any, subject: str = "") -> str:
    """短讯正文（去掉站点导航/用户栏/页脚 —— 用户栏里的「H&R 0/0/10」是**假的**）。"""
    t = str(html_text or "")
    if not t:
        return ""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>|</td>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&nbsp;", " ").replace("&#039;", "'")
          .replace("&amp;", "&").replace("&quot;", '"').replace("&#x2022;", " "))
    lines = [re.sub(r"[ \t]+", " ", x).strip() for x in t.split("\n")]
    lines = [x for x in lines if x]
    start = 0
    key = str(subject or "")[:12].strip()
    if key:
        idxs = [i for i, x in enumerate(lines) if key in x]
        if len(idxs) >= 2:
            start = idxs[1] + 1
        elif idxs:
            start = idxs[0] + 1
        else:
            # 标题行被截断/变形时：退到「短讯箱 / 收件箱」表头之后
            for i, x in enumerate(lines):
                if x in ("短讯箱", "收件箱") and i + 1 < len(lines):
                    start = i + 1
    end = len(lines)
    for i in range(start, len(lines)):
        if _MAIL_FOOT_RE.search(lines[i]) or lines[i].startswith("(c) "):
            end = i
            break
    body = [x for x in lines[start:end] if x not in _MAIL_NOISE and not _MAIL_TIME_RE.search(x)]
    return "\n".join(body)[:4000]


DEFAULT_PAGE = "/index.php"
LEECH_PAGE = "/getusertorrentlist.php?type=leeching&userid={uid}"
LEECH_PAGE_ALT = "/userdetails.php?id={uid}"


def sanitize_site_headers(site: Any) -> Tuple[Optional[str], Optional[str]]:
    """站点 UA / Cookie 去空白（尤其 **UA 前导空格**）。

    踩过（2026-09-29，蟹黄堡）：站点配置里 ua 带一个前导空格 →
    httpx 直接判「非法 header」→ 请求在 0.9ms 内返回 None，
    表现成「无响应」，规则页永远抓不到。UA/Cookie 统一 strip 兜底。
    """
    try:
        ua = str(getattr(site, "ua", "") or "").strip() or None
    except Exception:  # noqa: BLE001
        ua = None
    try:
        cookie = str(getattr(site, "cookie", "") or "").strip() or None
    except Exception:  # noqa: BLE001
        cookie = None
    return ua, cookie


def is_pv_limited(text: Any) -> bool:
    """页面是否就是「今日访问次数已达上限」的拦截页。"""
    t = str(text or "")
    if not t or len(t) > 2000:
        return False
    return ("访问次数已达上限" in t) or ("访问次数已达" in t and "上限" in t)


def next_day_ts(now: Optional[float] = None) -> float:
    """下一个本地凌晨（+宽限）的时间戳。"""
    t = float(now if now is not None else time.time())
    local = time.localtime(t)
    nxt = time.mktime(
        (local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0, local.tm_wday, local.tm_yday, -1)
    ) + 86400.0
    return nxt + PV_BLOCK_GRACE


@dataclass
class Fetched:
    """一次抓取的结果（绝不抛异常）。"""

    ok: bool = False
    text: str = ""
    error: str = ""
    status: int = 0
    cached: bool = False
    stale: bool = False
    cost: int = 0
    pv_limited: bool = False

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


# ============================================================
# 闸门：唯一配额入口
# ============================================================

class Budget:
    """配额闸门。站点 PV 走插件的 PvLedger（``/pv/ledger`` 的唯一真值源），
    另外维护「按 kind 的当日计数」以支持 KIND_DAY_CAP（如签到一天一次）。"""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        self._lock = threading.Lock()
        self._mem: Dict[str, Dict[str, int]] = {}

    # ------------------------------------------------------------ 内部计数
    @staticmethod
    def _day() -> str:
        return time.strftime("%Y-%m-%d", time.localtime())

    def day_used(self, site_id: Any, kind: str) -> int:
        sid = str(int(site_id or 0))
        day = self._day()
        try:
            data = self._p.get_data("collect_day") or {}
        except Exception:  # noqa: BLE001
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.update(self._mem)
        site = (data.get(day) or {}).get(sid) or {}
        try:
            return int(site.get(str(kind), 0) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _bump_day(self, site_id: Any, kind: str, n: int = 1) -> None:
        sid = str(int(site_id or 0))
        day = self._day()
        with self._lock:
            bucket = self._mem.setdefault(day, {}).setdefault(sid, {})
            bucket[str(kind)] = int(bucket.get(str(kind), 0) or 0) + max(int(n), 1)
            # 只保留两天，防无界
            for stale in sorted(self._mem.keys())[:-2]:
                self._mem.pop(stale, None)
        try:
            data = self._p.get_data("collect_day") or {}
            if not isinstance(data, dict):
                data = {}
            for stale in sorted(data.keys())[:-7]:
                data.pop(stale, None)
            site = data.setdefault(day, {}).setdefault(sid, {})
            site[str(kind)] = int(site.get(str(kind), 0) or 0) + max(int(n), 1)
            self._p.save_data(key="collect_day", value=data)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 查询
    def blocked(self, site_id: Any) -> str:
        """该站是否被熔断（每日访问上限）。返回原因，未封返回 ""。"""
        try:
            return str(self._p._pv_block_reason(site_id) or "")
        except Exception:  # noqa: BLE001
            return ""

    def used(self, site_id: Any) -> int:
        try:
            return int(self._p._pv_ledger().today_total(site_id))
        except Exception:  # noqa: BLE001
            return 0

    def budget(self, site_id: Any) -> int:
        try:
            return int(self._p._pv_budget(site_id))
        except Exception:  # noqa: BLE001
            return 0

    def allow(self, site_id: Any, kind: str, want: int = 1) -> Tuple[bool, str]:
        """能不能发这次请求。返回 (允许?, 拒绝原因)。"""
        reason = self.blocked(site_id)
        if reason:
            return False, reason
        cap = int(KIND_DAY_CAP.get(kind, 0) or 0)
        if cap > 0 and self.day_used(site_id, kind) >= cap:
            return False, f"当日 {kind} 次数已达上限({cap})"
        try:
            if not self._p._pv_allow(site_id, kind, want=int(want)):
                return False, "PV 预算不足"
        except Exception:  # noqa: BLE001
            pass
        return True, ""

    def spend(self, site_id: Any, kind: str, n: int = 1) -> int:
        """记一笔（PV 账本 + 本模块的按 kind 计数）。"""
        self._bump_day(site_id, kind, n)
        try:
            return int(self._p._pv_spend(site_id, kind, n))
        except Exception:  # noqa: BLE001
            return 0


# ============================================================
# 解析器：页面 → 规整事实（★ 解析也归采集）
# ============================================================

_SIZE_UNITS = {
    "B": 1.0, "K": 1024.0, "KB": 1024.0, "KIB": 1024.0,
    "M": 1024.0 ** 2, "MB": 1024.0 ** 2, "MIB": 1024.0 ** 2,
    "G": 1024.0 ** 3, "GB": 1024.0 ** 3, "GIB": 1024.0 ** 3,
    "T": 1024.0 ** 4, "TB": 1024.0 ** 4, "TIB": 1024.0 ** 4,
    "P": 1024.0 ** 5, "PB": 1024.0 ** 5, "PIB": 1024.0 ** 5,
}
_TAG_RE = re.compile(r"<[^>]+>")


def parse_size(text: Any) -> float:
    """'100.91GB' / '1,024.5 MB' → 字节数（float）。解析不出来返回 0.0。"""
    if text is None:
        return 0.0
    s = str(text).strip().replace(",", "").replace(" ", "")
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([KMGTP]?I?B?)$", s, re.IGNORECASE)
    if not m:
        return 0.0
    try:
        val = float(m.group(1))
    except (TypeError, ValueError):
        return 0.0
    unit = (m.group(2) or "B").strip().upper()
    mult = _SIZE_UNITS.get(unit)
    if mult is None:
        mult = _SIZE_UNITS.get(unit.rstrip("B")) if unit.endswith("B") else None
    if mult is None:
        mult = 1.0
    return val * mult


def _to_text(raw: Any) -> str:
    """去标签 + HTML 实体 → 纯文本（保留原换行结构成空格）。"""
    s = str(raw or "")
    s = _TAG_RE.sub(" ", s)
    s = (
        s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
        .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    )
    return re.sub(r"[ \t\r\f\v]+", " ", s)


def _first_num(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return float(str(m.group(1)).replace(",", ""))
    except (TypeError, ValueError, IndexError):
        return None


def parse_uid(raw: Any) -> Optional[int]:
    """从页面里抠 uid（NexusPHP 通用：userdetails.php?id=123 / userid=123）。"""
    s = str(raw or "")
    for pat in (r"userdetails\.php\?id=(\d+)", r"userid=(\d+)", r"/user/(\d+)"):
        m = re.search(pat, s)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _is_free_promotion(cls: str, text: str) -> bool:
    blob = f"{cls} {text}".lower()
    if any(k in blob for k in ("pro_free2up", "twoupfree", "2xfree", "free2up")):
        return True
    return bool(re.search(r"\bfree\b|免费", blob))


def parse_leeching_rows(raw: Any) -> List[Dict[str, Any]]:
    """解析「正在下载」列表 → [{name, size, progress, free, ...}]。"""
    rows: List[Dict[str, Any]] = []
    try:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", str(raw or ""), re.S | re.I):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
            if len(cells) < 3:
                continue
            link = re.search(r'href="(details\.php\?id=\d+|/details\.php\?id=\d+)[^"]*"[^>]*>(.*?)</a>', tr, re.S | re.I)
            name = _to_text(link.group(2)) if link else ""
            if not name or len(name) < 2:
                continue
            cls = " ".join(re.findall(r'class="([^"]*)"', tr)) + tr
            size = 0.0
            progress = None
            for c in cells:
                txt = _to_text(c)
                if not size:
                    m = re.search(r"([0-9][0-9.,]*\s*[KMGTP]?i?B)\b", txt)
                    if m:
                        size = parse_size(m.group(1))
                m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", txt)
                if m and progress is None:
                    try:
                        progress = float(m.group(1))
                    except ValueError:
                        progress = None
            rows.append({
                "name": name.strip(),
                "size": size,
                "progress": progress,
                "free": _is_free_promotion(cls, tr),
            })
    except Exception:  # noqa: BLE001
        return []
    return rows


def parse_user_bar(raw: Any) -> Dict[str, Any]:
    """解析站点用户栏页（NexusPHP ``index.php``）→ 规整事实。

    一次抓全：分享率 / 上传 / 下载 / 当前做种 / 当前下载 / 时魔 / 现魔力 / uid / 登录态。
    """
    text = _to_text(raw)
    raw_s = str(raw or "")
    out: Dict[str, Any] = {
        "ratio": None,
        "upload": None,
        "download": None,
        "seeding": None,
        "leeching": None,
        "bonus_per_hour": None,
        "bonus": None,
        "uid": parse_uid(raw_s),
        "logged_in": bool(
            re.search(r"logout\.php|退出|我的分享率|魔力值", raw_s)
        ) and not re.search(r'name="password"', raw_s),
    }
    val = _first_num(r"分享率[：:]\s*([0-9]+(?:\.[0-9]+)?)", text)
    if val is not None:
        out["ratio"] = val
    m = re.search(r"上传(?:量)?[：:]\s*([0-9][0-9.,]*\s*[KMGTP]?I?B)", text, re.IGNORECASE)
    if m:
        out["upload"] = parse_size(m.group(1))
    m = re.search(r"下载(?:量)?[：:]\s*([0-9][0-9.,]*\s*[KMGTP]?I?B)", text, re.IGNORECASE)
    if m:
        out["download"] = parse_size(m.group(1))
    val = _first_num(r"魔力值?\(?\s*([0-9][0-9.,]*)\s*魔力?\s*/\s*(?:小时|時|h)", text)
    if val is None:
        val = _first_num(r"每小时\s*([0-9][0-9.,]*)\s*个?魔力", text)
    if val is not None:
        out["bonus_per_hour"] = val
    _m = re.search(r"魔力值?\([^)]*\)", text)
    val = None
    if _m:
        val = _first_num(r"[^0-9]{0,40}?([0-9][0-9,]*(?:\.[0-9]+)?)", text[_m.end():])
    if val is None:
        val = _first_num(r"魔力值[^0-9]{0,30}?([0-9][0-9,]*(?:\.[0-9]+)?)", text)
    if val is not None:
        out["bonus"] = val
    m = re.search(r"title\s*=\s*[\"']?(?:当前做种|做种中|做种)[\"']?[^>]*>[^<]*</font>?\s*([0-9]+)", raw_s)
    if m:
        out["seeding"] = int(m.group(1))
    m = re.search(r"title\s*=\s*[\"']?(?:当前下载|下载中)[\"']?[^>]*>[^<]*</font>?\s*([0-9]+)", raw_s)
    if m:
        out["leeching"] = int(m.group(1))
    if out["seeding"] is None:
        val = _first_num(r"⬆\s*([0-9]+)", text)
        if val is None:
            val = _first_num(r"(?:做种中|正在做种|做种)[：:]?\s*([0-9]+)\s*(?:个|条)?", text)
        if val is not None:
            out["seeding"] = int(val)
    if out["leeching"] is None:
        val = _first_num(r"⬇\s*([0-9]+)", text)
        if val is None:
            val = _first_num(r"(?:下载中|正在下载)[：:]?\s*([0-9]+)\s*(?:个|条)?", text)
        if val is not None:
            out["leeching"] = int(val)
    if out["ratio"] in (None, 0.0) and (out["upload"] or 0) > 0 and (out["download"] or 0) > 0:
        out["ratio"] = round(float(out["upload"]) / float(out["download"]), 3)
    return out


# 签到结果特征
SIGNED_RE = re.compile(r"已得\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:个)?魔力")
SIGNED_TEXTS = ("签到成功", "已签到", "已签", "签到已得", "每日签到", "签到已得魔力")
LOGIN_HINT_RE = re.compile(r"login\.php|name=\"password\"|登录|登陆")
PV_LIMIT_RE = re.compile(r"访问次数已达上限|今日访问次数")


def parse_signin(raw: Any) -> Dict[str, Any]:
    """解析签到页 → {ok, signed, already, bonus, cookie_dead, pv_limited, message}。"""
    text = str(raw or "")
    flat = _to_text(text)
    if PV_LIMIT_RE.search(flat):
        return {"ok": False, "pv_limited": True, "message": "站点每日访问次数已达上限"}
    m = SIGNED_RE.search(flat)
    bonus = None
    if m:
        try:
            bonus = float(m.group(1).replace(",", ""))
        except ValueError:
            bonus = None
    hit = bool(m) or any(t in flat for t in SIGNED_TEXTS)
    cookie_dead = bool(re.search(r'name="password"', text)) or (
        bool(LOGIN_HINT_RE.search(flat)) and "logout.php" not in text
    )
    if cookie_dead:
        return {"ok": False, "cookie_dead": True, "message": "Cookie 已失效或未登录"}
    if hit:
        return {
            "ok": True,
            "signed": True,
            "already": ("已签" in flat) or bool(m),
            "bonus": bonus,
            "message": "今日已签到",
        }
    return {"ok": True, "signed": True, "already": False, "bonus": bonus, "message": "已执行（未识别到结果文案）"}


_PASSKEY_RE = re.compile(r"passkey=([0-9a-fA-F]{16,64})")
_HASH_RE = re.compile(r"(?:downhash|hash)=([0-9a-zA-Z]{8,64})")
_UID_RE = re.compile(r"[?&]id=(\d+)")


def parse_passkey(raw: Any) -> Dict[str, Any]:
    """从浏览页/个人页抽 passkey / uid / downhash（长期事实）。"""
    s = str(raw or "")
    pk = _PASSKEY_RE.search(s)
    dh = _HASH_RE.search(s)
    uid = _UID_RE.search(s)
    return {
        "passkey": pk.group(1) if pk else "",
        "downhash": dh.group(1) if dh else "",
        "uid": uid.group(1) if uid else "",
    }


def detect_framework(html: str, domain: str = "") -> Tuple[str, str]:
    """框架识别（NexusPHP / Gazelle / UNIT3D / M-Team …）→ (framework, evidence)。

    识别表本体在 ``sitecap``（站点能力库，属于「数据」），这里只做流水线调用，
    避免把能力表复制两份。
    """
    try:
        from .sitecap import detect_framework as _df  # noqa: WPS433

        return _df(html, domain)
    except Exception:  # noqa: BLE001
        return "", ""


# ============================================================
# 事实库
# ============================================================

@dataclass
class Fact:
    value: Any
    at: float = field(default_factory=time.time)
    source: str = ""
    cost: int = 0

    @property
    def age(self) -> float:
        return max(0.0, time.time() - float(self.at or 0.0))

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "at": self.at, "source": self.source, "cost": self.cost}


class Facts:
    """事实库：``(scope, key) -> Fact``。

    - 短期事实：内存 + 插件分层缓存（TierCache），TTL 由调用方给；
    - **长期事实**（passkey / 站点规则 / 站点能力）：落 durable（``save_data``），不吃 TTL。
    红线：只存「原始事实 + 时间 + 来源 + 花费」，**不存结论**。
    """

    def __init__(self, plugin: Any, tier: Any = None) -> None:
        self._p = plugin
        self._tier = tier
        self._mem: Dict[str, Fact] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _k(scope: str, key: Any) -> str:
        return f"{scope}|{key}"

    def put(self, scope: str, key: Any, value: Any, *, source: str = "", cost: int = 0) -> Fact:
        fact = Fact(value=value, source=source, cost=cost)
        with self._lock:
            self._mem[self._k(scope, key)] = fact
        return fact

    def get(self, scope: str, key: Any, ttl: float = 0.0) -> Optional[Fact]:
        k = self._k(scope, key)
        with self._lock:
            fact = self._mem.get(k)
        if fact is not None and (ttl <= 0 or fact.age < ttl):
            return fact
        if self._tier is not None and ttl > 0:
            val = self._tier.get(k, ttl)
            if isinstance(val, dict) and "value" in val:
                fact = Fact(
                    value=val.get("value"),
                    at=float(val.get("at") or 0.0),
                    source=str(val.get("source") or ""),
                    cost=int(val.get("cost") or 0),
                )
                with self._lock:
                    self._mem[k] = fact
                return fact
        return fact

    def put_cached(self, scope: str, key: Any, value: Any, ttl: float, *, source: str = "", cost: int = 0) -> None:
        fact = self.put(scope, key, value, source=source, cost=cost)
        if self._tier is not None and ttl > 0:
            try:
                self._tier.set(self._k(scope, key), fact.to_dict(), ttl)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ durable
    def durable_get(self, key: str) -> Any:
        try:
            return self._p.get_data(f"fact_{key}")
        except Exception:  # noqa: BLE001
            return None

    def durable_put(self, key: str, value: Any) -> None:
        try:
            self._p.save_data(key=f"fact_{key}", value=value)
        except Exception:  # noqa: BLE001
            pass


# ============================================================
# 观测
# ============================================================

class Observe:
    """采集者登记簿：谁在抓、抓什么、多久一次、花了几 PV、命中率。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._last: List[Dict[str, Any]] = []
        self.workers: Dict[str, Any] = {}

    def register(self, key: str, *, scope: str, ttl: float = 0.0, cost: int = 0, note: str = "") -> None:
        with self._lock:
            st = self._stats.setdefault(key, {})
            st.update({"scope": scope, "ttl": ttl, "cost": cost, "note": note})

    def record(
        self, key: str, *, ok: bool, cached: bool = False, ms: float = 0.0,
        cost: int = 0, site: Any = None, detail: str = "",
    ) -> None:
        with self._lock:
            st = self._stats.setdefault(key, {})
            st["calls"] = int(st.get("calls", 0)) + 1
            if cached:
                st["cache_hits"] = int(st.get("cache_hits", 0)) + 1
            elif ok:
                st["ok"] = int(st.get("ok", 0)) + 1
            else:
                st["fail"] = int(st.get("fail", 0)) + 1
            st["cost_total"] = int(st.get("cost_total", 0)) + int(cost or 0)
            st["last_at"] = time.time()
            st["last_ms"] = round(float(ms), 1)
            if ok and not cached:
                _n = int(st.get("_n", 0)) + 1
                st["_n"] = _n
                st["avg_ms"] = round(
                    (float(st.get("avg_ms", 0.0)) * (_n - 1) + float(ms)) / _n, 1
                )
            if not ok and detail:
                st["last_error"] = str(detail)[:200]
            self._last.append({
                "key": key, "site": site, "ok": bool(ok), "cached": bool(cached),
                "ms": round(float(ms), 1), "cost": int(cost or 0),
                "at": time.time(), "detail": str(detail)[:120],
            })
            if len(self._last) > 60:
                self._last = self._last[-60:]

    def mark_worker(self, name: str, *, registered: bool, reason: str = "") -> None:
        with self._lock:
            self.workers[name] = {"registered": bool(registered), "reason": reason, "at": time.time()}

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            stats = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in self._stats.items()}
            for k, v in self._stats.items():
                calls = int(v.get("calls", 0) or 0)
                hits = int(v.get("cache_hits", 0) or 0)
                stats[k]["hit_rate"] = round(hits / calls, 3) if calls else 0.0
            last = list(self._last)[-20:][::-1]
            workers = dict(self.workers)
        return {"registry": stats, "recent": last, "workers": workers}


# ============================================================
# 唯一 HTTP 出口
# ============================================================

class Http:
    """站点网页抓取（唯一出口）。

    负责：cookie 域绑定校验 / 编码回退 / PV 拦截页识别 / 熔断 / 配额闸门 /
        "规范化 URL" 缓存 + 全局 single-flight。
    """

    def __init__(self, plugin: Any, budget: Budget, facts: Facts, observe: Observe, tier: Any = None) -> None:
        self._p = plugin
        self._b = budget
        self._facts = facts
        self._obs = observe
        self._tier = tier
        self._locks: Dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    # ------------------------------------------------------------ 工具
    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            lk = self._locks.get(key)
            if lk is None:
                lk = self._locks[key] = threading.Lock()
            return lk

    @staticmethod
    def _norm_url(url: str) -> str:
        """规范化 URL：小写 host、去空 query 值、排序 query —— 保证同一页只有一个键。"""
        try:
            from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

            p = urlsplit(str(url))
            q = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True))
            return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(q), ""))
        except Exception:  # noqa: BLE001
            return str(url)

    def _base(self, site: Any) -> str:
        return (getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}").rstrip("/")

    # ------------------------------------------------------------ 主流程
    def fetch(
        self,
        site_id: Any,
        page: str,
        *,
        kind: str = "browse",
        ttl: Optional[float] = None,
        force: bool = False,
        absolute_url: str = "",
        return_error_page: bool = False,
    ) -> Fetched:
        sid = int(site_id or 0)
        site = self._p._get_site(sid)
        if not site:
            return Fetched(ok=False, error="站点不存在")
        base = self._base(site)
        url = str(absolute_url or "").strip() or f"{base}/{str(page or DEFAULT_PAGE).lstrip('/')}"
        if not self._p._url_allowed_for_site(url, site):
            return Fetched(ok=False, error="仅允许抓取该站点域名下的页面")
        ttl = float(KIND_TTL.get(kind, 240.0) if ttl is None else ttl)
        key = f"http|{sid}|{self._norm_url(url)}"

        if not force and ttl > 0 and self._tier is not None:
            hit = self._tier.get(key, ttl)
            if isinstance(hit, dict) and hit.get("text"):
                self._obs.record(f"{kind}:{sid}", ok=True, cached=True, site=sid, detail=url)
                return Fetched(ok=True, text=str(hit.get("text") or ""), status=int(hit.get("status") or 200), cached=True)

        with self._lock_for(key):
            if not force and ttl > 0 and self._tier is not None:
                hit = self._tier.get(key, ttl)
                if isinstance(hit, dict) and hit.get("text"):
                    self._obs.record(f"{kind}:{sid}", ok=True, cached=True, site=sid, detail=url)
                    return Fetched(ok=True, text=str(hit.get("text") or ""), status=int(hit.get("status") or 200), cached=True)
            allow, why = self._b.allow(sid, kind, 1)
            if not allow:
                self._obs.record(f"{kind}:{sid}", ok=False, site=sid, detail=why)
                return Fetched(ok=False, error=why)
            started = time.time()
            text, err, status = self._request(site, base, url)
            ms = (time.time() - started) * 1000.0
            if err:
                pvlim = err == "站点每日访问次数已达上限"
                self._obs.record(f"{kind}:{sid}", ok=False, ms=ms, site=sid, detail=err)
                return Fetched(ok=False, error=err, status=status, pv_limited=pvlim)
            self._b.spend(sid, kind, 1)
            self._obs.record(f"{kind}:{sid}", ok=True, ms=ms, cost=1, site=sid, detail=url)
            if ttl > 0 and self._tier is not None:
                try:
                    self._tier.set(key, {"text": text, "status": status, "url": url}, ttl)
                except Exception:  # noqa: BLE001
                    pass
            return Fetched(ok=True, text=text, status=status, cost=1)

    # ------------------------------------------------------------ 单次请求
    def _request(self, site: Any, base: str, url: str) -> Tuple[str, str, int]:
        try:
            from app.sdk.network import RequestUtils  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return "", f"SDK 不可用: {err}", 0
        try:
            _ua, _cookie = sanitize_site_headers(site)
            req = RequestUtils(
                cookies=_cookie,
                ua=_ua,
                timeout=30,
                referer=f"{base}/",
            )
            resp = req.get_res(url)
        except Exception as err:  # noqa: BLE001
            return "", f"请求失败: {err}", 0
        if resp is None:
            return "", "无响应", 0
        status = int(getattr(resp, "status_code", 0) or 0)
        try:
            raw = resp.content or b""
        except Exception:  # noqa: BLE001
            raw = b""
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", "ignore")
        if status >= 400 or not text:
            return "", f"HTTP {status}", status
        if is_pv_limited(text):
            self._mark_pv_blocked(int(site.id if getattr(site, "id", None) else 0))
            return "", "站点每日访问次数已达上限", status
        return text, "", status

    def is_api_site(self, site_id: Any) -> bool:
        """该站是否走 API 鉴权（馒头）。"""
        try:
            return is_api_site(self._p._get_site(int(site_id)))
        except Exception:  # noqa: BLE001
            return False

    def api(
        self,
        site_id: Any,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        body: Optional[Dict[str, Any]] = None,
        kind: str = "api",
        ttl: Optional[float] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """★ 3.42.0/3.43.0 调站点后台 API（``x-api-key`` 鉴权，馒头）。

        ★ 3.43.0：**参数默认走 query（``params=``），不是 JSON body** —— 这是 MP
        ``iyuuautoseed`` 实测可用的调法（``/torrent/genDlToken?id=…``）；馒头后端对
        JSON body 一律回「參數錯誤」。需要 body 的端点显式给 ``body=``。

        与网页抓取同规矩：过**唯一出口**（本模块）、过配额闸门、规范化缓存 + single-flight、
        观测登记。返回 ``{"ok": bool, "data": dict, "cached": bool, "cost": int, "error": str}``。
        """
        import json as _json  # noqa: WPS433

        sid = int(site_id or 0)
        site = self._p._get_site(sid)
        if not site:
            return {"ok": False, "error": "站点不存在"}
        # ★ 3.45.0：鉴权头 / 根地址 / 提交形态 / 成功判定 全部来自「通道表」
        tname, cfg = api_channel(site)
        _auth = cfg.get("auth") or {}
        field = str(_auth.get("field") or "apikey")
        key = str(getattr(site, field, "") or "").strip()
        if not key:
            return {"ok": False, "error": "站点未配置 API Key"}
        hname = str(_auth.get("header") or "Authorization")
        hprefix = str(_auth.get("prefix") or "")
        _env = cfg.get("envelope") or {}
        ok_field = str(_env.get("ok_field") or "code")
        ok_value = _env.get("ok_value", "0")
        err_field = str(_env.get("err_field") or "message")
        # 端点名 → 实际路径 + 该端点的提交形态/参数名
        ep = api_endpoint(site, path)
        body_mode = str(ep.get("body") or cfg.get("body") or "json").strip().lower()
        path = str(ep.get("path") or path or "")
        if ep.get("param") and not params and not body:
            params = {}
        base = api_base(site)
        if not base:
            return {"ok": False, "error": "无法推导 API 域名"}
        url = f"{base}/{str(path or '').lstrip('/')}"
        if body is not None:
            body_mode = "json"
        elif ep.get("body"):
            body_mode = str(ep.get("body")).strip().lower()
        ttl = float(KIND_TTL.get(kind, 300.0) if ttl is None else ttl)
        _q = {k: v for k, v in (params or {}).items() if v is not None}
        ckey = f"api|{sid}|{url}|{_json.dumps(_q, sort_keys=True, ensure_ascii=False)}|{_json.dumps(body or {}, sort_keys=True, ensure_ascii=False)}"

        def _hit() -> Optional[Dict[str, Any]]:
            if force or ttl <= 0 or self._tier is None:
                return None
            got = self._tier.get(ckey, ttl)
            if isinstance(got, dict) and got.get("data") is not None:
                return got
            return None

        cached = _hit()
        if cached is not None:
            self._obs.record(f"{kind}:{sid}", ok=True, cached=True, site=sid, detail=url)
            return {"ok": True, "data": cached.get("data"), "cached": True, "cost": 0}
        with self._lock_for(ckey):
            cached = _hit()
            if cached is not None:
                self._obs.record(f"{kind}:{sid}", ok=True, cached=True, site=sid, detail=url)
                return {"ok": True, "data": cached.get("data"), "cached": True, "cost": 0}
            allow, why = self._b.allow(sid, kind, 1)
            if not allow:
                self._obs.record(f"{kind}:{sid}", ok=False, site=sid, detail=why)
                return {"ok": False, "error": why}
            ua, _ck = sanitize_site_headers(site)
            started = time.time()
            raw: Any = None
            try:
                from app.sdk.network import RequestUtils  # noqa: WPS433

                # ★ 关键：馒头 API 的两种形态
                #   * `body=`  → JSON 体（`/member/profile`、`/torrent/search`）
                #   * `params=`→ **form 体**（`Content-Type: application/x-www-form-urlencoded`）
                #     （`/torrent/detail`、`/torrent/genDlToken`）。带 JSON 头 + params 会被拒
                #     「請求參數錯誤」—— 实测（对齐 MP `iyuuautoseed` 的可用调法）。
                _is_json = body_mode == "json"
                _ct = "application/json" if _is_json else "application/x-www-form-urlencoded"
                _hdr = {
                    hname: f"{hprefix}{key}",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": _ct,
                    "User-Agent": ua or "Mozilla/5.0",
                }
                req = RequestUtils(headers=_hdr, timeout=25)
                if _is_json:
                    resp = req.post_res(url, json=dict(body or {}), params=dict(_q) or None)
                else:
                    resp = req.post_res(url, params=dict(_q))
                if resp is not None:
                    try:
                        raw = resp.json()
                    finally:
                        try:
                            resp.close()
                        except Exception:  # noqa: BLE001
                            pass
            except Exception as err:  # noqa: BLE001
                self._obs.record(f"{kind}:{sid}", ok=False, site=sid, detail=f"API 失败: {err}")
                return {"ok": False, "error": f"API 失败: {err}"}
            ms = (time.time() - started) * 1000.0
            if not isinstance(raw, dict):
                self._obs.record(f"{kind}:{sid}", ok=False, ms=ms, site=sid, detail="API 无响应")
                return {"ok": False, "error": "API 无响应"}
            _okv = raw.get(ok_field)
            if isinstance(ok_value, bool):
                _good = (bool(_okv) is ok_value) or str(_okv).strip().lower() == str(ok_value).lower()
            else:
                _good = str(_okv) == str(ok_value)
            if not _good:
                msg = str(raw.get(err_field) or raw.get("message") or "鉴权失败")
                self._obs.record(f"{kind}:{sid}", ok=False, ms=ms, site=sid, detail=f"API: {msg}")
                return {"ok": False, "error": f"API: {msg}"}
            self._b.spend(sid, kind, 1)
            data = raw.get("data")
            self._obs.record(f"{kind}:{sid}", ok=True, ms=ms, cost=1, site=sid, detail=url)
            if ttl > 0 and self._tier is not None:
                try:
                    self._tier.set(ckey, {"data": data, "url": url}, ttl)
                except Exception:  # noqa: BLE001
                    pass
            return {"ok": True, "data": data, "cost": 1}

    def client(self, site_id: Any, *, kind: str = "browse", ttl: Optional[float] = None, referer: str = "") -> "Client":
        """返回鸭子型客户端（``.get_res(url)``），供"还在别处"的采集点一行接进来。"""
        return Client(self, site_id, kind=kind, ttl=ttl, referer=referer)

    def text(self, site_id: Any, url: str, *, kind: str = "browse", ttl: Optional[float] = None) -> Fetched:
        """按绝对 URL 取正文（仍受同域校验 / 闸门约束）。"""
        return self.fetch(site_id, "", kind=kind, ttl=ttl, absolute_url=url)

    def _mark_pv_blocked(self, site_id: int) -> None:
        """命中「每日访问上限」→ 熔断该站至次日凌晨（走插件既有的落盘实现）。"""
        try:
            live = getattr(self._p, "_live", None)
            if live is not None and hasattr(live, "_pv_block_site"):
                live._pv_block_site(int(site_id))
        except Exception:  # noqa: BLE001
            pass


# ============================================================
# 鸭子型客户端：让「还在别处」的采集点一行接进来
# ============================================================

class _Resp:
    """RequestUtils 响应的最小鸭子型（text/content/status_code/ok/close）。"""

    def __init__(self, f: Fetched) -> None:
        self._f = f
        self.status_code = int(f.status or (200 if f.ok else 0))
        self.text = str(f.text or "")
        self.content = (self.text.encode("utf-8") if self.text else b"")
        self.ok = bool(f.ok)
        self.cached = bool(f.cached)
        self.error = f.error

    def close(self) -> None:
        return None

    def __bool__(self) -> bool:
        return bool(self.ok and self.text)


class Client:
    """RequestUtils 的替代品：**同样**的 ``.get_res(url)`` 用法，但请求经过采集模块
    （唯一出口 + 配额闸门 + 规范化 URL 缓存 + 观测）。

    典型接法（只改一行）::

        # 旧：req = RequestUtils(cookies=cookie, ua=ua, timeout=30, referer=base + "/")
        req = collect.http.client(site_id, kind="formula", referer=base + "/")
        resp = req.get_res(url)      # 后面代码不用动
    """

    def __init__(self, http: "Http", site_id: Any, *, kind: str, ttl: Optional[float] = None, referer: str = "") -> None:
        self._http = http
        self._sid = int(site_id or 0)
        self._kind = str(kind)
        self._ttl = ttl
        self.referer = referer

    def get_res(self, url: str = "", **kw: Any) -> Optional[_Resp]:
        target = str(url or kw.get("url") or "").strip()
        if not target:
            return None
        f = self._http.fetch(self._sid, "", kind=self._kind, ttl=self._ttl, absolute_url=target)
        return _Resp(f)


# ============================================================
# 站点视图：拿事实的门（别人只读这里）
# ============================================================

class SiteView:
    """某个站点的采集面。所有方法**只返回事实**，不含任何判断。"""

    def __init__(self, c: "Collect", site_id: Any) -> None:
        self._c = c
        self.sid = int(site_id or 0)

    # -------------------------------------------------- 传输层（只给需要原文的解析器用）
    def page(self, path: str = DEFAULT_PAGE, *, kind: str = "browse", ttl: Optional[float] = None, force: bool = False) -> Fetched:
        return self._c.http.fetch(self.sid, path, kind=kind, ttl=ttl, force=force)

    def url(self, absolute_url: str, *, kind: str = "debug", ttl: Optional[float] = None) -> Fetched:
        return self._c.http.fetch(self.sid, "", kind=kind, ttl=ttl, absolute_url=absolute_url)

    # -------------------------------------------------- 事实层
    def is_api(self) -> bool:
        """本站是否 API 鉴权站（馒头）。"""
        return self._c.http.is_api_site(self.sid)

    def api(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        body: Optional[Dict[str, Any]] = None,
        kind: str = "api",
        ttl: Optional[float] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """调站点后台 API。★ 3.45.0：``path`` 可传**逻辑端点名**（``profile``/``list``/…）。"""
        return self._c.http.api(self.sid, path, payload, body=body, kind=kind, ttl=ttl, force=force)

    def api_site(self) -> Any:
        """★ 3.45.0 拿到本站的站点记录（给通道表 / 直链模板用；只读）。"""
        try:
            return self._c._p._get_site(self.sid)
        except Exception:  # noqa: BLE001
            return None

    def api_run(
        self,
        key: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        force: bool = False,
        ttl: Optional[float] = None,
    ) -> Dict[str, Any]:
        """★ 3.45.0 按**通道表端点名**调一次 API，返回原信封的 ``data``。"""
        ttl = float(KIND_TTL["api"] if ttl is None else ttl)
        res = self._c.http.api(self.sid, key, params, body=body, kind="api", ttl=ttl, force=force)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error"), "source": "api"}
        return {"ok": True, "source": "api", "data": res.get("data"), "cached": bool(res.get("cached"))}

    def api_list(
        self,
        page: int = 1,
        size: int = 20,
        *,
        promo: str = "free",
        keyword: str = "",
        force: bool = False,
        ttl: Optional[float] = None,
    ) -> Dict[str, Any]:
        """★ 3.45.0 叶PT（YemaPT）公开种子列表（含 ``hrPunishEnable`` 权威 H&R 标记）。"""
        body: Dict[str, Any] = {
            "pageParam": {"current": int(page or 1), "pageSize": int(size or 20)},
            "sorter": {"field": "listingTime", "order": "descend"},
        }
        if str(keyword or "").strip():
            body["keyword"] = str(keyword).strip()
        if str(promo or "").strip():
            body["downloadPromotionType"] = str(promo).strip()
        res = self.api_run("list", body=body, force=force, ttl=ttl)
        if not res.get("ok"):
            return res
        d = res.get("data")
        if isinstance(d, dict):
            rows = d.get("records") or d.get("list") or d.get("data") or []
            total = d.get("total")
        else:
            rows, total = (d if isinstance(d, list) else []), None
        return {
            "ok": True,
            "source": "api",
            "total": total,
            "page": int(page or 1),
            "rows": rows if isinstance(rows, list) else [],
            "cached": bool(res.get("cached")),
        }

    def api_hashes(self, hashes: List[str], *, force: bool = False) -> Dict[str, Any]:
        """★ 3.45.0 按 piecesHash 批量反查种子 ID（叶PT ``fetchTorrentIdWithPiecesHash``）。"""
        lst = [str(h).strip() for h in (hashes or []) if str(h).strip()][:100]
        if not lst:
            return {"ok": True, "source": "api", "map": {}}
        res = self.api_run("hash", body={"piecesHashList": lst}, force=force, ttl=60.0)
        if not res.get("ok"):
            return res
        d = res.get("data")
        return {"ok": True, "source": "api", "map": d if isinstance(d, dict) else {}}

    def api_search(
        self,
        keyword: str = "",
        page: int = 1,
        size: int = 50,
        *,
        force: bool = False,
        ttl: Optional[float] = None,
    ) -> Dict[str, Any]:
        """★ 3.43.0 馒头候选检索（含 ``status.discount`` 促销与 seeders/leechers）。"""
        ttl = float(KIND_TTL["api"] if ttl is None else ttl)
        # ★ `/torrent/search` 与 `/member/profile` 一样要 **JSON body**；
        #   只有 `/torrent/detail`、`/torrent/genDlToken` 要 **query**。（馒头后端两种混着）
        res = self._c.http.api(
            self.sid,
            "search",
            None,
            body={"keyword": str(keyword or ""), "pageNumber": int(page or 1), "pageSize": int(size or 50)},
            kind="api",
            ttl=ttl,
            force=force,
        )
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error"), "source": "api"}
        d = res.get("data") or {}
        rows = d.get("data") if isinstance(d.get("data"), list) else []
        return {
            "ok": True,
            "source": "api",
            "total": d.get("total"),
            "page": d.get("pageNumber"),
            "rows": rows if isinstance(rows, list) else [],
            "cached": bool(res.get("cached")),
        }

    def api_detail(self, tid: Any, *, force: bool = False, ttl: Optional[float] = None) -> Dict[str, Any]:
        """★ 3.43.0 馒头种子详情（含 ``status.discount`` / seeders / leechers / descr）。"""
        ttl = float(KIND_TTL["api"] if ttl is None else ttl)
        res = self._c.http.api(self.sid, "detail", {"id": tid}, kind="api", ttl=ttl, force=force)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error"), "source": "api"}
        d = res.get("data") or {}
        return {"ok": True, "source": "api", "data": d, "cached": bool(res.get("cached"))}

    def api_dl_token(self, tid: Any, *, force: bool = False, ttl: Optional[float] = None) -> Dict[str, Any]:
        """★ 3.43.0 馒头签名下载直链（``/torrent/genDlToken``，无需 cookie）。

        签名带时间戳 ``t``，**短缓存**（默认 120s）。
        """
        ttl = 120.0 if ttl is None else float(ttl)
        res = self._c.http.api(self.sid, "dl", {"id": tid}, kind="api", ttl=ttl, force=force)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error"), "source": "api"}
        # ★ 3.45.0：有 ``dl_url`` 模板的通道（叶PT）= 凭证→拼直链；否则凭证本身就是直链（馒头）
        site = self.api_site()
        url = api_dl_url(site, res.get("data")) if site is not None else str(res.get("data") or "")
        return {"ok": bool(url), "source": "api", "url": url, "cached": bool(res.get("cached"))}

    def api_profile(self, *, force: bool = False, ttl: Optional[float] = None) -> Dict[str, Any]:
        """★ API 站档案：魔力 / 上传 / 下载 / 分享率 / uid（馒头 ``/member/profile``）。"""
        ttl = float(KIND_TTL["api"] if ttl is None else ttl)
        cached = self._c.facts.get("site", f"{self.sid}|api_profile", ttl)
        if cached is not None and not force and isinstance(cached.value, dict):
            v = dict(cached.value)
            v["cached"] = True
            return v
        # ★ 3.45.0：端点名走通道表（馒头 ``profile`` = ``/member/profile``，JSON body）
        res = self._c.http.api(self.sid, "profile", None, body={}, kind="api", ttl=ttl, force=force)
        if not res.get("ok"):
            if cached is not None and isinstance(cached.value, dict):
                v = dict(cached.value)
                v.update({"cached": True, "stale": True, "ok": True, "error": res.get("error")})
                return v
            return {"ok": False, "error": res.get("error"), "source": "api"}
        d = res.get("data") or {}
        cnt = d.get("memberCount") if isinstance(d.get("memberCount"), dict) else {}
        st = d.get("memberStatus") if isinstance(d.get("memberStatus"), dict) else {}
        # ★ 字段归一：馒头 memberCount{bonus,uploaded,downloaded,shareRate}；叶PT data{id,bonus,level,...}
        bar = {
            "ok": True,
            "source": "api",
            "uid": str(st.get("id") or d.get("id") or ""),
            "ratio": _num(cnt.get("shareRate") if cnt.get("shareRate") is not None else d.get("shareRate")),
            "upload": _num(cnt.get("uploaded") if cnt.get("uploaded") is not None else d.get("uploaded")),
            "download": _num(cnt.get("downloaded") if cnt.get("downloaded") is not None else d.get("downloaded")),
            "bonus": _num(cnt.get("bonus") if cnt.get("bonus") is not None else d.get("bonus")),
            "seeding": _num(d.get("seeding")),
            "leeching": _num(d.get("leeching")),
            "bonus_per_hour": None,
            "level": _num(d.get("level")),
            "name": str(d.get("name") or ""),
            "created": str(d.get("createdDate") or st.get("createdDate") or ""),
            "logged_in": str(d.get("status") or st.get("status") or "").upper()
            in ("CONFIRMED", "ENABLE", "ENABLED", "ACTIVE", "")
            and (bool(d) or bool(st)),
            "vip": bool(st.get("vip")),
            "warned": bool(st.get("warned") or st.get("leechWarn")),
        }
        try:
            self._c.facts.set("site", f"{self.sid}|api_profile", bar, ttl)
        except Exception:  # noqa: BLE001
            pass
        return bar

    def user_bar(self, *, force: bool = False, ttl: Optional[float] = None) -> Dict[str, Any]:
        """站点用户栏（一次抓全）：分享率/上传/下载/做种/下载中/时魔/魔力/uid/登录态。"""
        if self.is_api():
            # ★ 3.42.0：API 站（馒头）没有用户栏网页 → 走 API 档案
            return self.api_profile(force=force, ttl=ttl)
        ttl = float(KIND_TTL["live"] if ttl is None else ttl)
        cached = self._c.facts.get("site", f"{self.sid}|user_bar", ttl)
        if cached is not None and not force and isinstance(cached.value, dict):
            v = dict(cached.value)
            v["cached"] = True
            return v
        res = self.page(DEFAULT_PAGE, kind="live", ttl=ttl, force=force)
        if not res.ok:
            # 抓不到 → 回退上次成功值（标 stale），保底不阻断
            if cached is not None and isinstance(cached.value, dict):
                v = dict(cached.value)
                v.update({"cached": True, "stale": True, "ok": True, "error": res.error})
                return v
            return {"ok": False, "error": res.error, "source": "site"}
        facts = parse_user_bar(res.text)
        facts.update({"ok": True, "cached": bool(res.cached), "source": "site", "at": time.time()})
        self._c.facts.put_cached("site", f"{self.sid}|user_bar", facts, ttl, source=f"site:{self.sid}:{DEFAULT_PAGE}", cost=res.cost)
        return facts

    def inbox(self, *, force: bool = False) -> Fetched:
        """收件箱列表页（一次抓全；6h 缓存）。"""
        return self.page(INBOX_PAGE, kind="inbox", ttl=float(KIND_TTL["inbox"]), force=force)

    def welcome(self, *, force: bool = False) -> Dict[str, Any]:
        """★ 3.41.0：**欢迎短讯**（H&R 的唯一自动来源）。

        一次抓列表 → 挑「欢迎」主题 → 再一次抓正文；7 天缓存，**不重复花 PV**。
        返回事实：``{ok, id, subject, body, cached, error}``；挑不到就是 ``ok=False``（不猜）。
        """
        cached = self._c.facts.get("site", f"{self.sid}|welcome", float(KIND_TTL["welcome"]))
        if cached is not None and not force and isinstance(cached.value, dict):
            v = dict(cached.value)
            v["cached"] = True
            return v
        res = self.inbox(force=force)
        if not res.ok:
            return {"ok": False, "error": res.error or "收件箱抓取失败"}
        rows = parse_mail_list(res.text)
        pick = pick_welcome_mail(rows)
        if not pick:
            out = {"ok": False, "error": "收件箱没有欢迎短讯", "mail_count": len(rows)}
            self._c.facts.put_cached("site", f"{self.sid}|welcome", out, float(KIND_TTL["welcome"]),
                                     source=f"site:{self.sid}:inbox", cost=res.cost)
            return out
        mid, subj = pick
        res2 = self.page(MAIL_PAGE.format(mid=int(mid)), kind="welcome", ttl=float(KIND_TTL["welcome"]), force=force)
        if not res2.ok:
            return {"ok": False, "error": res2.error or "短讯正文抓取失败", "id": mid, "subject": subj}
        body = parse_mail_body(res2.text, subj)
        out = {
            "ok": True, "id": mid, "subject": subj, "body": body,
            "links": parse_mail_links(res2.text),
            "cached": bool(res2.cached), "cost": int(res.cost or 0) + int(res2.cost or 0),
        }
        self._c.facts.put_cached("site", f"{self.sid}|welcome", out, float(KIND_TTL["welcome"]),
                                 source=f"site:{self.sid}:mail", cost=out["cost"])
        return out

    def leeching(self, *, force: bool = False) -> Dict[str, Any]:
        """「正在下载」列表（一次抓全 + 促销标记）。"""
        uid = None
        ub = self.user_bar()
        if isinstance(ub, dict):
            uid = ub.get("uid")
        if not uid:
            return {"ok": False, "error": "未解析出 uid"}
        ttl = float(KIND_TTL["leeching"])
        cached = self._c.facts.get("site", f"{self.sid}|leeching", ttl)
        if cached is not None and not force and isinstance(cached.value, dict):
            v = dict(cached.value)
            v["cached"] = True
            return v
        page = LEECH_PAGE.format(uid=int(uid))
        res = self.page(page, kind="leeching", ttl=ttl, force=force)
        rows: List[Dict[str, Any]] = []
        if res.ok:
            rows = parse_leeching_rows(res.text)
        if res.ok and not rows:
            alt = LEECH_PAGE_ALT.format(uid=int(uid))
            res2 = self.page(alt, kind="leeching", ttl=ttl, force=force)
            if res2.ok:
                rows = parse_leeching_rows(res2.text)
                if rows:
                    page = alt
        if not res.ok and not rows:
            return {"ok": False, "error": res.error, "uid": int(uid), "pv_limited": res.pv_limited}
        out = {"ok": True, "uid": int(uid), "page": page, "rows": rows, "cache_hit": bool(res.cached), "at": time.time()}
        self._c.facts.put_cached("site", f"{self.sid}|leeching", out, ttl, source=f"site:{self.sid}:{page}", cost=res.cost)
        return dict(out)

    def signin_page(self, *, force: bool = False) -> Fetched:
        """签到页（访问即签到；一天最多 2 次 = 首次 + 一次失败重试，由闸门 KIND_DAY_CAP 保证）。"""
        return self.page("attendance.php", kind="signin", ttl=KIND_TTL["signin"], force=force)

    def signin(self, *, force: bool = False) -> Dict[str, Any]:
        res = self.signin_page(force=force)
        if not res.ok:
            return {
                "ok": False, "error": res.error, "pv_limited": res.pv_limited,
                "cached": bool(res.cached), "cost": res.cost,
            }
        facts = parse_signin(res.text)
        facts.update({"cached": bool(res.cached), "cost": res.cost, "at": time.time()})
        return facts

    def passkey(self, *, page: str = "torrents.php", force: bool = False) -> Dict[str, Any]:
        """抽 passkey/uid/downhash：抽到即落 durable（长期事实，下次不抓）。"""
        key = f"passkey|{self.sid}"
        if not force:
            saved = self._c.facts.durable_get(key)
            if isinstance(saved, dict) and saved.get("passkey"):
                out = dict(saved)
                out["cached"] = True
                return out
        res = self.page(page, kind="passkey", ttl=0.0, force=True)
        if not res.ok:
            return {"ok": False, "error": res.error, "pv_limited": res.pv_limited}
        facts = parse_passkey(res.text)
        facts.update({"ok": True, "cached": False, "cost": res.cost, "at": time.time()})
        if facts.get("passkey"):
            self._c.facts.durable_put(key, facts)
        return facts

    def framework(self, *, force: bool = False) -> Dict[str, Any]:
        """框架/能力识别（一次抓全 + 识别；识别表在 sitecap）。"""
        ttl = float(KIND_TTL["sitecap"])
        key = f"framework|{self.sid}"
        if not force:
            saved = self._c.facts.durable_get(key)
            if isinstance(saved, dict) and saved.get("framework"):
                out = dict(saved)
                out["cached"] = True
                return out
        for path in ("/index.php", "/torrents.php", "/"):
            res = self.page(path, kind="sitecap", ttl=ttl)
            if not res.ok:
                continue
            fw, ev = detect_framework(res.text, str(getattr(self._c._p._get_site(self.sid), "domain", "") or ""))
            if fw:
                out = {"ok": True, "framework": fw, "evidence": ev, "path": path, "at": time.time(), "cost": res.cost}
                self._c.facts.durable_put(key, out)
                return out
            if res.text:
                break
        return {"ok": True, "framework": "", "evidence": "no-marker"}

    def exam(self, *, force: bool = False) -> Dict[str, Any]:
        """考核页原文（解析交 exam 功能，属裁决）。"""
        res = self.page(DEFAULT_PAGE, kind="exam", ttl=KIND_TTL["exam"], force=force)
        return {"ok": res.ok, "text": res.text, "error": res.error, "cached": res.cached, "cost": res.cost}


# ============================================================
# 门面
# ============================================================

class Collect:
    """采集门面：``plugin.collect``。

    只有一扇门：``site(sid).<事实名>()`` / ``mp()`` / ``svc(name)`` / ``dl()`` / ``observe()``。
    """

    def __init__(self, plugin: Any, tier: Any = None) -> None:
        self._p = plugin
        self.budget = Budget(plugin)
        self.observe_registry = Observe()
        self.facts = Facts(plugin, tier)
        self.http = Http(plugin, self.budget, self.facts, self.observe_registry, tier)
        self._obs = self.observe_registry
        self._svc: Dict[str, Any] = {}
        # 预登记（观测里能看见"有这些采集者"）
        for kind, ttl in KIND_TTL.items():
            self._obs.register(f"site.{kind}", scope=SCOPE_SITE, ttl=ttl, cost=1, note="站点网页")

    # ------------------------------------------------------------ 站点
    def site(self, site_id: Any) -> SiteView:
        return SiteView(self, site_id)

    def is_api_site(self, site_id: Any) -> bool:
        """该站是否「API 鉴权站」（馒头：x-api-key，无 cookie）。★ 3.42.0"""
        return self.http.is_api_site(site_id)

    # ------------------------------------------------------------ 服务/本地（登记 + 计时）
    def svc(self, name: str) -> Any:
        """外部服务采集器（豆瓣 / IYUU 云端 / OpenList）。只登记与计时，实现仍在其模块。"""
        self._obs.register(f"svc.{name}", scope=SCOPE_SERVICE, note="外部服务")
        return self._svc.get(name)

    def register_service(self, name: str, obj: Any = None) -> None:
        """登记一个外部服务采集者（豆瓣/IYUU/云盘…），只为「看得见」。"""
        if obj is not None:
            self._svc[name] = obj
        self._obs.register(f"svc.{name}", scope=SCOPE_SERVICE, note="外部服务")

    def dl(self) -> Any:
        """下载器采集器（实现仍在 ``downloader_ops``，这里只登记）。"""
        self._obs.register("local.downloader", scope=SCOPE_LOCAL, note="下载器 API")
        return getattr(self._p, "_downloader_ops", None)

    def timer(self, key: str, site: Any = None) -> "_Timer":
        """给「实现仍在别处」的采集点用的计时上下文（登记进观测，不改实现）。"""
        return _Timer(self._obs, key, site)

    def observe(self) -> Dict[str, Any]:
        """``/debug/collect`` 的数据：注册表 + 最近抓取 + 配额 + worker 注册原因。"""
        snap = self._obs.snapshot()
        snap["budget"] = self._budget_snapshot()
        snap["day_caps"] = dict(KIND_DAY_CAP)
        snap["kinds"] = dict(KIND_TTL)
        return snap

    def _budget_snapshot(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"sites": {}}
        try:
            sites = {int(t.site_id): t for t in self._p._task_configs.values() if int(getattr(t, "site_id", 0) or 0)}
        except Exception:  # noqa: BLE001
            sites = {}
        for sid in sites:
            try:
                out["sites"][str(sid)] = {
                    "name": self._p._live_site_name(sid) if hasattr(self._p, "_live_site_name") else str(sid),
                    "used": self.budget.used(sid),
                    "budget": self.budget.budget(sid),
                    "blocked": self.budget.blocked(sid),
                    "by_kind": {
                        k: self.budget.day_used(sid, k)
                        for k in KIND_TTL
                        if self.budget.day_used(sid, k)
                    },
                }
            except Exception:  # noqa: BLE001
                continue
        out["default"] = int(getattr(self._p, "_pv_default_budget", 0) or 0)
        return out

    def mark_worker(self, name: str, *, registered: bool, reason: str = "") -> None:
        self._obs.mark_worker(name, registered=registered, reason=reason)

    def log(self, msg: str, level: str = "info") -> None:
        try:
            self._p._log(msg, level)
        except Exception:  # noqa: BLE001
            pass


class _Timer:
    """``with collect.timer("local.downloader", site=1):`` —— 只登记耗时，不改实现。"""

    def __init__(self, obs: Observe, key: str, site: Any = None) -> None:
        self._obs = obs
        self._key = key
        self._site = site
        self._t0 = 0.0

    def __enter__(self) -> "_Timer":
        self._t0 = time.time()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._obs.record(
            self._key, ok=exc is None, ms=(time.time() - self._t0) * 1000.0,
            site=self._site, detail=str(exc or ""),
        )
        return False
