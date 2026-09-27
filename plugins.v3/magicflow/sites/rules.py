"""站点规则库：H&R（Hit and Run）/ 最短保种时长 / 做种数上限。

**为什么需要**：跨站免费取种会从兄弟站「下回来一份」——那份种在兄弟站仍然背着
H&R 保种义务（例：学校 BTSchool 要求挂种 10 小时）。这个义务**只跟站点有关**，
所以必须有一张**按站点**的规则表，否则只能靠人肉硬编码。

**来源优先级**（高 → 低）：

1. ``manual`` —— 设置面板「跨站 → 站点保种时长（域名=小时）」手填；
2. ``probe`` —— 抓站点页面（``/myhr.php``、``/rules.php``）解析出来的；
3. ``builtin`` —— 本模块内置的已知规则（人工核对过的常识）；
4. 全局默认（``CROSSSEED_SEED_HOURS_DEFAULT``）。

**保守原则**：抓不到就当 ``unknown``，**绝不**把「没解析到」当成「没有 H&R」。
抓错的代价是不对称的 —— 多挂几小时只是多占一点盘（免费种不花流量），
少挂就是实打实的 H&R 惩罚。

本模块只依赖 stdlib，不反向依赖插件主模块（避免热重载循环导入）。
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

RULES_KEY = "site_rules"


# ============================================================
# 内置已知规则（人工核对过的「常识」，可被 probe / manual 覆盖）
# ============================================================
# 字段说明：
#   hr          : 是否有 H&R 制度（None = 未知）
#   seed_hours  : H&R 要求的最短保种时长（小时；None = 未知）
#   seed_cap    : 同时在册做种数上限（None = 未知/不限）
#   note        : 人话备注
BUILTIN_RULES: Dict[str, Dict[str, Any]] = {
    "pt.btschool.club": {
        "hr": True,
        "seed_hours": 10.0,
        "seed_cap": None,
        "note": "学校：H&R 需挂种 10 小时（主人确认）",
    },
    "hdfans.org": {
        "hr": True,
        "seed_hours": 24.0,
        "seed_cap": None,
        "note": "红豆饭：有 H&R（默认按 24h 保守保种，待探测核实）",
    },
    "kp.m-team.cc": {
        "hr": False,
        "seed_hours": None,
        "seed_cap": 100,
        "note": "馒头：无 H&R；做种数上限 100（bonus seeding_count_cap）",
    },
    "m-team.cc": {
        "hr": False,
        "seed_hours": None,
        "seed_cap": 100,
        "note": "馒头（备用域名）",
    },
}


# ============================================================
# 页面解析
# ============================================================
# 小时数：中文/英文两种写法。允许「10 个 小时」「10小時」「10 hours」「10h」。
_HOURS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:个)?\s*(?:小时|小時|個小時|hours?|hrs?|h\b)",
    re.I,
)
_DAYS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:天|日|days?)", re.I)
# H&R 关键词
_HR_WORD_RE = re.compile(r"H\s*&\s*R|hit\s*[&a]nd\s*run|Hit\s*and\s*Run|做种率|H&R", re.I)
# 「需要做种/挂种 ... 」的上下文
_SEED_CTX_RE = re.compile(
    r"(?:做种|保种|挂种|seeding|seed|share\s*time)[^\u4e00-\u9fffA-Za-z0-9]{0,12}",
    re.I,
)
# 做种数上限
_CAP_RE = re.compile(
    r"(?:最多|上限|同时|做种数|seeding)[^\d]{0,12}(\d{1,4})\s*(?:个|個|条|種|种)?",
    re.I,
)


def _clip(text: str, start: int, end: int, pad: int = 60) -> str:
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def _hours_near(text: str, idx: int, window: int = 120) -> Optional[float]:
    """在 idx 附近 window 字符内找「X 小时 / X 天」。"""
    lo = max(0, idx - window)
    seg = text[lo: idx + window]
    m = _HOURS_RE.search(seg)
    if m:
        try:
            return float(m.group(1))
        except (TypeError, ValueError):
            return None
    m = _DAYS_RE.search(seg)
    if m:
        try:
            return float(m.group(1)) * 24.0
        except (TypeError, ValueError):
            return None
    return None


def parse_hr_from_html(html_text: str) -> Dict[str, Any]:
    """从站点页面文本里尽力解析 H&R 规则。

    Returns:
        ``{"hr": bool|None, "seed_hours": float|None, "seed_cap": int|None,
           "evidence": str, "hits": int}``

    保守：只有「H&R 关键词 + 上下文里的小时数」同时命中，才认为 ``hr=True``。
        只命中 H&R 关键词（没解析出小时数）→ ``hr=True, seed_hours=None``。
        完全没命中 → ``hr=None``（未知），由上层用内置/默认值兜底。
    """
    out: Dict[str, Any] = {"hr": None, "seed_hours": None, "seed_cap": None, "evidence": "", "hits": 0}
    if not html_text:
        return out
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html_text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"\s+", " ", text)

    best: Optional[float] = None
    ev = ""
    hits = 0
    for m in _HR_WORD_RE.finditer(text):
        hits += 1
        h = _hours_near(text, m.start())
        if h and (best is None or h > best):
            best = h
            ev = _clip(text, m.start(), m.end())
    # 没有 H&R 关键词时，退一步看「做种 … 小时」这种表述（很多站规则页这么写）
    if hits == 0:
        for m in _SEED_CTX_RE.finditer(text):
            hits += 1
            h = _hours_near(text, m.start(), window=60)
            if h and (best is None or h > best):
                best = h
                ev = _clip(text, m.start(), m.end())
    out["hits"] = hits
    if hits:
        out["hr"] = True
    if best is not None:
        out["seed_hours"] = float(best)
    # 做种数上限：只在「上限/最多」这类词附近取，且限制在合理区间
    cap = None
    for m in _CAP_RE.finditer(text):
        try:
            v = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if 1 <= v <= 5000 and (cap is None or v < cap):
            cap = v
    if cap is not None:
        out["seed_cap"] = cap
    out["evidence"] = ev[:300]
    return out


# ============================================================
# 规则账本
# ============================================================
class SiteRules:
    """站点规则账本（``save_data`` 持久化，重装不丢）。

    记录形如::

        {"domain": "pt.btschool.club", "site_id": 1, "name": "学校",
         "hr": true, "seed_hours": 10.0, "seed_cap": null,
         "source": "probe", "updated": 1758000000,
         "evidence": "...", "note": "..."}
    """

    def __init__(
        self,
        get_data: Callable[[str], Any],
        save_data: Callable[..., Any],
        log: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._get = get_data
        self._save = save_data
        self._log = log
        self._cache: Optional[Dict[str, Dict[str, Any]]] = None

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            raw = self._get(RULES_KEY) or {}
        except Exception:  # noqa: BLE001
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in raw.items():
            if isinstance(v, dict):
                out[str(k).strip().lower()] = v
        return out

    def items(self) -> Dict[str, Dict[str, Any]]:
        if self._cache is None:
            self._cache = self._load()
        return self._cache

    def _write(self) -> None:
        try:
            self._save(key=RULES_KEY, value=self.items())
        except Exception as err:  # noqa: BLE001
            if self._log:
                self._log(f"站点规则:写入失败:{err}", "warning")

    def get(self, domain: str) -> Dict[str, Any]:
        d = _norm_domain(domain)
        return dict(self.items().get(d) or {})

    def put(self, domain: str, rec: Dict[str, Any], source: str = "") -> Dict[str, Any]:
        d = _norm_domain(domain)
        if not d:
            return {}
        cur = dict(self.items().get(d) or {})
        cur.update(rec or {})
        cur["domain"] = d
        if source:
            cur["source"] = source
        cur["updated"] = float(time.time())
        self.items()[d] = cur
        self._write()
        return cur

    def merge_probe(self, domain: str, probed: Dict[str, Any]) -> Dict[str, Any]:
        """把探测结果并入（**不覆盖**手填 source=manual 的字段）。"""
        d = _norm_domain(domain)
        cur = dict(self.items().get(d) or {})
        if str(cur.get("source") or "") == "manual":
            cur["probed_at"] = float(time.time())
            self.items()[d] = cur
            self._write()
            return cur
        out = dict(cur)
        for key in ("hr", "seed_hours", "seed_cap", "evidence"):
            val = (probed or {}).get(key)
            if val is not None:
                out[key] = val
        out["source"] = "probe"
        out["probed_at"] = float(time.time())
        out["domain"] = d
        out["updated"] = float(time.time())
        self.items()[d] = out
        self._write()
        return out

    def ensure_builtin(self, domain: str = "", name: str = "") -> Dict[str, Any]:
        """没记录时用内置表补一条（source=builtin）。"""
        d = _norm_domain(domain)
        if not d:
            return {}
        cur = self.items().get(d)
        if cur:
            return dict(cur)
        b = BUILTIN_RULES.get(d)
        if not b:
            return {}
        return self.put(d, dict(b, name=name or ""), source="builtin")

    def clear(self, domain: str = "") -> int:
        d = _norm_domain(domain)
        if d:
            n = 1 if self.items().pop(d, None) is not None else 0
        else:
            n = len(self.items())
            self.items().clear()
        self._write()
        return n

    def effective_hours(
        self,
        domain: str,
        manual_map: Optional[Dict[str, float]] = None,
        default: float = 24.0,
    ) -> float:
        """算「该站来源份要保种多少小时」：manual > probe > builtin > default。"""
        hours, _src = self.resolve(domain, manual_map, default)
        return hours

    def resolve(
        self,
        domain: str,
        manual_map: Optional[Dict[str, float]] = None,
        default: float = 24.0,
    ) -> Any:
        """返回 ``(hours, source)``。"""
        d = _norm_domain(domain)
        if d and manual_map:
            for key, val in (manual_map or {}).items():
                if _norm_domain(key) == d:
                    try:
                        h = float(val)
                    except (TypeError, ValueError):
                        continue
                    if h >= 0:
                        return h, "manual"
        rec = dict(self.items().get(d) or {})
        h = rec.get("seed_hours")
        if h is not None:
            try:
                hv = float(h)
                if hv >= 0:
                    return hv, str(rec.get("source") or "store")
            except (TypeError, ValueError):
                pass
        b = BUILTIN_RULES.get(d) or {}
        bh = b.get("seed_hours")
        if bh is not None:
            return float(bh), "builtin"
        return float(default), "default"


def _norm_domain(domain: str) -> str:
    return str(domain or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
