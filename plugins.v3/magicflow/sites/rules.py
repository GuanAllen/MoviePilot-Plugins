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
        # 保守：按**规则窗口**保护（10 天），而不是最低做种线（20h）。
        # 因为我们的账本按「墙钟」计时，暂停/无 peer 时墙钟≠实际做种时长。
        "seed_hours": 240.0,
        "seed_need_hours": 20.0,
        "seed_cap": None,
        "note": "学校：10 天内做种≥20 小时（rules.php 原文）；保护期取满窗口 10 天（保守）",
    },
    "ptcafe.club": {
        "hr": False,
        "seed_hours": 0.0,
        "seed_cap": None,
        "note": "咖啡：**无 H&R**（rules.php 无 H&R 条款，主人确认）。另有「撤种规定」(≤10集 10 天 / 10-50集 15 天 / >50集 1 个月) 与随机促销 90% FREE、>20GB 自动免费。",
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


def _segments(text: str) -> List[str]:
    """把正文切成「句子/行」——解析规则必须**同句**命中，不然满页数字全中。"""
    parts = re.split(r"[\n\r。！？；;!?]+", text)
    return [p.strip() for p in parts if p.strip()]


# 明确**不属于** H&R 的上下文（考核/达标/魔力/上传者规则/发布者/捐赠 等）
_EXCLUDE_RE = re.compile(
    r"考核|达标|魔力|奖励|捐赠|申诉|免罪|警告|相册|邀请|邮箱|注册|每月|月做种|新人|"
    r"上传者|发布者|发种|候选|认领",
    re.I,
)
# 「同一句里」的 H&R 关键词
_HR_TOKENS = re.compile(r"H\s*&\s*R|hit\s*[&a]nd\s*run|hit and run", re.I)
# 「同一句里」的保种动作词
_SEED_TOKENS = re.compile(r"做种|保种|挂种|seeding|seed", re.I)
# 促销规则：「文件总体积大于20GB的种子将自动成为免费」/「原盘免费」/「每季第一集免费」
_FREE_SIZE_RE = re.compile(
    r"(?:总体积|文件体积|体积|大小)[^。\n]{0,12}?大于\s*([\d.]+)\s*(?:G|GB|GiB)[^。\n]{0,30}免费",
    re.I,
)
_FREE_SIZE_RE2 = re.compile(r"大于\s*([\d.]+)\s*(?:G|GB|GiB)[^。\n]{0,20}自动[^。\n]{0,10}免费", re.I)
_FREE_ORIG_RE = re.compile(
    r"(?:Blu-?ray\s*Disk|HD\s*DVD|原盘)[^。\n]{0,40}(?:免费|free)", re.I
)
_FREE_EP1_RE = re.compile(r"每季的第?一集|第1集[^。\n]{0,20}免费|第一集[^。\n]{0,20}免费", re.I)

# 「考核指标」句式：指标N：平均做种时间, 要求：30 Hour —— 这是**新人考核的达标线**，
# 不是 H&R 规则，必须分开存（否则会把考核要求误当成保种义务）。
_EXAM_RE = re.compile(r"指标|平均做种时间|考核|达标线|要求\s*[:：]", re.I)
# 明确的规则句式（最可信）：必须/需/要求/至少 ...
_RULE_NEED_RE = re.compile(
    r"必须|需|要求|不得少于|不少于|至少|达到|以内|之内|at least|must|minimum", re.I
)


def _parse_hours_in(seg: str):
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
    """从站点页面文本里尽力解析 H&R 规则（**保守 + 分级可信度**）。

    Returns:
        ``{"hr": bool|None, "seed_hours": float|None, "confidence": "high"|"low",
           "seed_cap": int|None, "evidence": str, "hits": int}``

    规则：
      * ``hr``：出现 H&R 关键词 → True（站点有 H&R 制度）；否则看「做种…小时」句式 → True；都没有 → None。
      * ``seed_hours`` **只在 ``confidence="high"`` 时可信**：
        - 同一句里既有 H&R/做种 关键词，又有明确的「必须/至少/需」+ 小时数；
        - 且该句**不含**考核/达标/魔力/上传者/发布者/每月 等排除词（那些是别处的数字）。
        - 解析到的值 > 336h（14 天）一律降级为 low（H&R 极少要求挂两周以上，
          多半是「考核时长/月度达标」被误读）。
      * ``confidence="low"`` 的值**只作展示证据**，不参与生效时长计算。
    """
    out: Dict[str, Any] = {
        "hr": None, "seed_hours": None, "confidence": "low",
        "seed_cap": None, "evidence": "", "hits": 0,
        "exam_avg_hours": None,
        "free_over_gb": None, "free_original": None, "free_ep1": None,
        "seed_need_hours": None, "seed_window_hours": None,
    }
    if not html_text:
        return out
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html_text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>|</td>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = text.replace("&#x2022;", " ")

    best_high = None
    best_low = None
    ev_high = ev_low = ""
    hits = 0
    for seg in _segments(text):
        has_hr = bool(_HR_TOKENS.search(seg))
        has_seed = bool(_SEED_TOKENS.search(seg))
        if has_hr:
            hits += 1
        if not (has_hr or has_seed):
            continue
        hours = _parse_hours_in(seg)
        if hours is None:
            continue
        # 「10天内做种达到20小时」= 窗口10天 + 达到线20h → **保守取窗口**
        _dm = _DAYS_RE.search(seg)
        _hm = _HOURS_RE.search(seg)
        if _dm and _hm:
            try:
                _win = float(_dm.group(1)) * 24.0
                _need = float(_hm.group(1))
                if _win > _need >= 0:
                    out["seed_need_hours"] = _need
                    out["seed_window_hours"] = _win
                    hours = _win
            except (TypeError, ValueError):
                pass
        excluded = bool(_EXCLUDE_RE.search(seg))
        strong = bool(_RULE_NEED_RE.search(seg))
        if _EXAM_RE.search(seg) and not re.search(r"认领|达标标准", seg):
            # 考核达标线（例：指标2：平均做种时间，要求 30 Hour）→ 单独存，不当 H&R
            ev = (out.get("exam_evidence") or "")
            if not ev:
                out["exam_evidence"] = seg[:300]
            if out["exam_avg_hours"] is None or hours > float(out["exam_avg_hours"]):
                out["exam_avg_hours"] = hours
            if has_hr:
                hits += 0
            continue
        if strong and not excluded and hours <= 336.0:
            if best_high is None or hours > best_high:
                best_high = hours
                ev_high = seg
        elif not excluded:
            if best_low is None or hours > best_low:
                best_low = hours
                ev_low = seg
    if hits or best_high is not None or best_low is not None:
        out["hr"] = True
    out["hits"] = hits
    if best_high is not None:
        out["seed_hours"] = float(best_high)
        out["confidence"] = "high"
        out["evidence"] = ev_high[:300]
    elif best_low is not None:
        out["seed_hours"] = float(best_low)
        out["confidence"] = "low"
        out["evidence"] = ev_low[:300]
    elif ev_low or ev_high:
        out["evidence"] = (ev_high or ev_low)[:300]
    # 促销规则（整页散文，不按句切）
    for rx in (_FREE_SIZE_RE, _FREE_SIZE_RE2):
        m = rx.search(text)
        if m:
            try:
                out["free_over_gb"] = float(m.group(1))
                break
            except (TypeError, ValueError):
                pass
    if _FREE_ORIG_RE.search(text):
        out["free_original"] = True
    if _FREE_EP1_RE.search(text):
        out["free_ep1"] = True

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
        """把探测结果并入。

        * 手填记录（``source=manual``）：**H&R / 保种时长 / 证据** 一律不动（手填为准），
          但**促销规则**（与 H&R 无关）照常并入 —— 不能因为手填了「无 H&R」就丢掉体积自动免费。
        """
        d = _norm_domain(domain)
        cur = dict(self.items().get(d) or {})
        out = dict(cur)
        manual = str(cur.get("source") or "") == "manual"
        conf = str((probed or {}).get("confidence") or "low")
        if not manual:
            for key in ("hr", "seed_cap", "evidence"):
                val = (probed or {}).get(key)
                if val is not None:
                    out[key] = val
            out["confidence"] = conf
        else:
            if (probed or {}).get("seed_cap") is not None and out.get("seed_cap") is None:
                out["seed_cap"] = (probed or {}).get("seed_cap")
        # 促销规则：与 H&R 无关，总是并入
        for key in ("free_over_gb", "free_original", "free_ep1", "seed_need_hours", "seed_window_hours"):
            val = (probed or {}).get(key)
            if val is not None:
                out[key] = val
        if not manual:
            if (probed or {}).get("exam_avg_hours") is not None:
                out["exam_avg_hours"] = (probed or {}).get("exam_avg_hours")
                if (probed or {}).get("exam_evidence"):
                    out["exam_evidence"] = (probed or {}).get("exam_evidence")
            val = (probed or {}).get("seed_hours")
            if val is not None and conf == "high":
                out["seed_hours"] = val
            elif val is not None:
                # 低可信：只留证据，不参与生效时长（宁保守勿乐观）
                out["seed_hours_seen"] = val
                out.pop("seed_hours", None)
        if not manual:
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

    def free_rules(self, domain: str) -> Dict[str, Any]:
        """取该站的「促销规则」（体积自动免费阈值/原盘免费/第一集免费）。"""
        d = _norm_domain(domain)
        rec: Dict[str, Any] = {}
        for k, v in (self.items() or {}).items():
            if _same_domain(k, d):
                rec = dict(v or {})
                break
        b: Dict[str, Any] = {}
        for k, v in BUILTIN_RULES.items():
            if _same_domain(k, d):
                b = dict(v or {})
                break
        out: Dict[str, Any] = {}
        for key in ("free_over_gb", "free_original", "free_ep1"):
            val = rec.get(key)
            if val is None:
                val = b.get(key)
            if val is not None:
                out[key] = val
        return out

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
                if _same_domain(key, d):
                    try:
                        h = float(val)
                    except (TypeError, ValueError):
                        continue
                    if h >= 0:
                        return h, "manual"
        rec = dict(self.items().get(d) or {})
        if not rec:
            for k, v in self.items().items():
                if _same_domain(k, d):
                    rec = dict(v or {})
                    break
        h = rec.get("seed_hours")
        if h is not None and str(rec.get("source") or "") == "probe" and str(rec.get("confidence") or "") != "high":
            h = None
        if h is not None:
            try:
                hv = float(h)
                if hv >= 0:
                    return hv, str(rec.get("source") or "store")
            except (TypeError, ValueError):
                pass
        b = BUILTIN_RULES.get(d) or {}
        if not b:
            for k, v in BUILTIN_RULES.items():
                if _same_domain(k, d):
                    b = v or {}
                    break
        bh = b.get("seed_hours")
        if bh is not None:
            return float(bh), "builtin"
        if b.get("hr") is False:
            # 内置明确「无 H&R」→ 没有保种义务，不用保护（例：馒头）
            return 0.0, "builtin"
        return float(default), "default"


def _norm_domain(domain: str) -> str:
    return str(domain or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")


def _same_domain(a: str, b: str) -> bool:
    """域名等价：相等，或一个是另一个的后缀（``btschool.club`` ≡ ``pt.btschool.club``）。"""
    a = _norm_domain(a)
    b = _norm_domain(b)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.endswith("." + b) or b.endswith("." + a)
