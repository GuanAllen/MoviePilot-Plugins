"""站点类型 / 能力识别（site capability）。

为什么要单独一个库
------------------
「免费怎么拿」在不同 PT 框架里差别很大，直接决定候选抓取策略与 PV 花费：

- **NexusPHP**：有免费索引（``torrents.php?incldead=1&spstate=2|4``），可以**只抓免费**，
  一次 1~2 个请求就够；主列表（最新 N 页）反而会漏掉较早的免费种。
- **Gazelle / UNIT3D / M-Team(API)**：没有 ``spstate`` 这种入口，
  只能抓完整列表再本地按促销字段筛「免费」，PV 花得多。
- 各站 ``page`` 参数语义、促销字段、限速行为也不一样（实测 hdtime 的 ``page=1`` 会返回半页/限速页）。

所以需要一个「这个站是什么框架、有哪些能力」的判定库，供抓取/筛选/预算共用。

识别优先级（高 → 低）
--------------------
1. **人工覆盖**（设置里的覆盖表，永远最优先）
2. **已知域名表**（内置少量 + 运行期学到的）
3. **探针**：抓一次站点页面，按特征串判定（消耗 1 次请求，结果长期缓存）

结果持久化在插件数据 ``site_caps``（走 MoviePilot 的 ``save_data`` → ``PluginData`` 表，
卸载保留、重装继承），进程内另有热缓存；冷层拿不到就退化为「仅内存」，不影响功能。
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 框架常量
# ---------------------------------------------------------------------------

FW_NEXUS = "nexusphp"
FW_GAZELLE = "gazelle"
FW_UNIT3D = "unit3d"
FW_MTEAM = "mteam"
FW_CUSTOM = "custom"      # 自有框架 / 魔改（判不出但已知不是上面几个）
FW_UNKNOWN = "unknown"    # 还没识别过

# 特征串（小写匹配）。命中即判定，多个命中取第一个命中的框架。
try:  # ★ 3.40.0：类型规则包（conf/frameworks.yml）——数据驱动，代码里只留兜底
    from .rulepack import (
        builtin_capabilities as _rp_caps_fb,
        builtin_domains_fallback as _rp_doms_fb,
        builtin_markers as _rp_markers_fb,
        capabilities as _rp_caps,
        builtin_domains as _rp_doms,
        markers as _rp_markers,
        pack_ok as _rp_ok,
    )
except Exception:  # noqa: BLE001
    _rp_caps = _rp_doms = _rp_markers = None  # type: ignore[assignment]
    _rp_caps_fb = _rp_doms_fb = _rp_markers_fb = None  # type: ignore[assignment]

    def _rp_ok() -> bool:  # type: ignore[misc]
        return False


_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (_rp_markers() if _rp_markers else ()) or (_rp_markers_fb() if _rp_markers_fb else ())
)

# 框架默认能力。free_index = 能不能「只要免费就只抓免费」，是省 PV 的关键。
# ★ 3.40.0：数据在 conf/frameworks.yml → frameworks.<fw>.capabilities（下面只是兜底）
def _load_framework_defaults() -> Dict[str, Dict[str, Any]]:
    """按规则包构造能力表（含 YAML 里没列出的框架 → 用通用兜底）。"""
    fb = dict(_rp_caps_fb() if _rp_caps_fb else {})
    out: Dict[str, Dict[str, Any]] = {}
    names: List[str] = []
    if _rp_markers is not None and _rp_caps is not None:
        try:
            from .rulepack import framework_names as _rp_names

            names = list(_rp_names())
        except Exception:  # noqa: BLE001
            names = []
    for fw in names:
        try:
            got = _rp_caps(fw) if _rp_caps else {}
        except Exception:  # noqa: BLE001
            got = {}
        if not got:
            got = dict(fb.get(fw) or fb.get("unknown") or {})
        out[fw] = got
    for fw, val in fb.items():          # 代码兜底项补齐（YAML 缺项也能跑）
        out.setdefault(fw, dict(val))
    return out


FRAMEWORK_DEFAULTS: Dict[str, Dict[str, Any]] = _load_framework_defaults()

# 内置已知域名（可被覆盖表/探针更新；只是省一次探测）
def _load_builtin_domains() -> Dict[str, str]:
    """已知域名 → 框架（数据在 conf/frameworks.yml → builtin_domains）。"""
    out: Dict[str, str] = {}
    if _rp_doms_fb is not None:
        out.update(dict(_rp_doms_fb()))
    if _rp_doms is not None:
        try:
            out.update(dict(_rp_doms()))
        except Exception:  # noqa: BLE001
            pass
    return out


BUILTIN_DOMAINS: Dict[str, str] = _load_builtin_domains()

# 探针缓存有效期：识别一次能用很久（框架基本不变）
PROBE_TTL = 30 * 86400.0
# ★ 识别/解析逻辑版本：一旦改动会推翻旧结论（如解析器兼容新皮肤）就 +1，
#   旧记录会在下次 needs_probe 时被判为过期、重新探测。
PROBE_VER = 3
# 探针最多抓几页（首页判框架失败时依次再试这些路径）
PROBE_PATHS: Tuple[str, ...] = ("/torrents.php", "/")


def norm_domain(domain: str) -> str:
    """规范化域名：小写、去掉协议/端口/路径/www 前缀。"""
    d = str(domain or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split(":")[0]
    return d[4:] if d.startswith("www.") else d


def detect_framework(html: str, domain: str = "") -> Tuple[str, str]:
    """纯函数：按页面内容判定框架，返回 ``(framework, evidence)``。

    Args:
        html: 页面前若干字节的文本（大小写不敏感）。
        domain: 站点域名，用于已知域名表兜底。

    Returns:
        ``(framework, evidence)``；判不出时 ``(FW_UNKNOWN, "")``。
    """
    dom = norm_domain(domain)
    if dom in BUILTIN_DOMAINS:
        return BUILTIN_DOMAINS[dom], f"known-domain:{dom}"
    low = (html or "").lower()
    if low:
        for fw, marks in _MARKERS:
            for m in marks:
                if m in low:
                    return fw, f"marker:{m}"
    return FW_UNKNOWN, ""


@dataclass
class SiteCap:
    """一个站点的能力画像。"""

    domain: str
    framework: str = FW_UNKNOWN
    source: str = "default"          # builtin | marker | manual | default
    evidence: str = ""
    ts: float = 0.0
    free_index: bool = False
    free_spstates: Tuple[int, ...] = ()
    page_param: str = "unknown"      # works | ignored | ratelimited | unknown
    promo_in_list: bool = False
    probe_ver: int = 0              # 当时用的识别/解析逻辑版本（<PROBE_VER 视为过期）
    notes: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------ 便捷
    @property
    def age(self) -> float:
        return max(0.0, time.time() - float(self.ts or 0.0))

    def free_url(self, base: str, sp: int, page: int = 0) -> str:
        """拼免费索引 URL（仅 NexusPHP 系有效）。"""
        b = (base or f"https://{self.domain}").rstrip("/")
        return f"{b}/torrents.php?incldead=1&spstate={int(sp)}&page={int(page)}"

    def apply_defaults(self) -> "SiteCap":
        """按框架套用默认能力（不清空已有的人工覆盖）。"""
        d = FRAMEWORK_DEFAULTS.get(self.framework) or {}
        for k, v in d.items():
            if k == "free_url":       # 只是模板，按需拼
                continue
            if getattr(self, k, None) in (None, False, (), "unknown"):
                setattr(self, k, v)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "framework": self.framework,
            "source": self.source,
            "evidence": self.evidence,
            "ts": self.ts,
            "free_index": self.free_index,
            "free_spstates": list(self.free_spstates or ()),
            "page_param": self.page_param,
            "promo_in_list": self.promo_in_list,
            "probe_ver": int(self.probe_ver or 0),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SiteCap":
        cap = cls(domain=str(d.get("domain") or ""))
        cap.framework = str(d.get("framework") or FW_UNKNOWN)
        cap.source = str(d.get("source") or "default")
        cap.evidence = str(d.get("evidence") or "")
        cap.ts = float(d.get("ts") or 0.0)
        cap.free_index = bool(d.get("free_index"))
        cap.free_spstates = tuple(int(x) for x in (d.get("free_spstates") or ()))
        cap.page_param = str(d.get("page_param") or "unknown")
        cap.promo_in_list = bool(d.get("promo_in_list"))
        cap.probe_ver = int(d.get("probe_ver") or 0)
        cap.notes = [str(x) for x in (d.get("notes") or [])]
        return cap


def _known_fw(fw: str) -> bool:
    """框架是否算「认识」（unknown / 空 = 不认识）。"""
    f = str(fw or "").strip().lower()
    return bool(f) and f != FW_UNKNOWN and f != "-"


class SiteCapRegistry:
    """站点能力注册表：查表 + 探针 + 持久化。

    典型用法::

        caps = SiteCapRegistry(plugin)
        cap = caps.get(site.domain)          # 只查表，不联网
        cap = caps.ensure(site, probe=True)  # 缺失才探一次（联网）
    """

    DATA_KEY = "site_caps"

    def __init__(self, plugin: Any = None, override: Optional[Dict[str, Any]] = None) -> None:
        self._plugin = plugin
        self._override: Dict[str, Dict[str, Any]] = dict(override or {})
        self._caps: Dict[str, SiteCap] = {}
        self._lock = threading.Lock()
        self._loaded = False

    # ------------------------------------------------------------- 持久化
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        raw = None
        if self._plugin is not None:
            try:
                raw = self._plugin.get_data(self.DATA_KEY)
            except Exception:  # noqa: BLE001
                raw = None
        if isinstance(raw, dict):
            for dom, item in raw.items():
                if isinstance(item, dict):
                    cap = SiteCap.from_dict({**item, "domain": item.get("domain") or dom})
                    self._caps[norm_domain(dom)] = cap

    def _save(self) -> None:
        if self._plugin is None:
            return
        try:
            self._plugin.save_data(
                key=self.DATA_KEY,
                value={k: v.to_dict() for k, v in self._caps.items()},
            )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------- 查询
    def get(self, domain: str) -> SiteCap:
        """查表（不联网）。命中顺序：人工覆盖 > 已识别 > 内置域名表 > 未知。"""
        dom = norm_domain(domain)

        def _alias(a: str, b: str) -> bool:
            # ★ 3.39.0：别名域也要认得（kp.m-team.cc ≙ m-team.cc / pt.soulvoice.club ≙ soulvoice.club）
            a, b = norm_domain(a), norm_domain(b)
            if not a or not b:
                return False
            return a == b or a.endswith("." + b) or b.endswith("." + a)

        with self._lock:
            self._load()
            if dom in self._override:
                cap = SiteCap.from_dict({**self._override[dom], "domain": dom})
                cap.source = "manual"
                return cap.apply_defaults()
            # ★ 3.40.0：识别成「未知」的历史记录**不压过**内置域名表
            #   （踩过：carpt.net 早前那次探测 200 但没抓到特征 → 记成 unknown，之后一直 unknown）
            if dom in self._caps and _known_fw(self._caps[dom].framework):
                return self._caps[dom]
            if dom:
                for k, item in self._override.items():
                    if _alias(dom, k):
                        cap = SiteCap.from_dict({**item, "domain": norm_domain(k)})
                        cap.source = "manual"
                        return cap.apply_defaults()
                for k, cap in self._caps.items():
                    if _alias(dom, k) and _known_fw(cap.framework):
                        return cap
        if dom in BUILTIN_DOMAINS:
            cap = SiteCap(domain=dom, framework=BUILTIN_DOMAINS[dom],
                          source="builtin", evidence=f"known-domain:{dom}", ts=time.time())
            return cap.apply_defaults()
        for k, fw in BUILTIN_DOMAINS.items():
            if _alias(dom, k):
                cap = SiteCap(domain=dom, framework=fw,
                              source="builtin", evidence=f"known-domain:{k}", ts=time.time())
                return cap.apply_defaults()
        if dom in self._caps:
            return self._caps[dom]        # 兜底：仍是那条 unknown 记录（可见）
        return SiteCap(domain=dom)

    def all(self) -> Dict[str, SiteCap]:
        with self._lock:
            self._load()
            out = dict(self._caps)
        for dom, fw in BUILTIN_DOMAINS.items():
            if dom not in out:
                out[dom] = self.get(dom)
        for dom, item in self._override.items():
            out[dom] = SiteCap.from_dict({**item, "domain": dom}).apply_defaults()
        return out

    # ------------------------------------------------------------- 写入
    def record(self, domain: str, cap: SiteCap, persist: bool = True) -> SiteCap:
        dom = norm_domain(domain or cap.domain)
        cap.domain = dom
        cap.ts = time.time()
        cap.probe_ver = PROBE_VER
        with self._lock:
            self._load()
            self._caps[dom] = cap
        if persist:
            self._save()
        return cap

    def learn(self, domain: str, framework: str, evidence: str = "",
              source: str = "marker", **flags: Any) -> SiteCap:
        """学到/更新一个站点的框架（+可选能力覆盖）。

        ★ 顺序要紧：先 apply_defaults 补默认，再上 flags —— 否则「显式学到的 False」
        （如 free_index=False）会被框架默认值又盖回 True。
        """
        cap = SiteCap(domain=norm_domain(domain), framework=framework,
                      source=source, evidence=evidence)
        cap.apply_defaults()
        for k, v in (flags or {}).items():
            if hasattr(cap, k):
                setattr(cap, k, v)
        return self.record(cap.domain, cap)

    def override(self, domain: str, **flags: Any) -> SiteCap:
        """人工覆盖（优先级最高，不落 site_caps，由调用方持久化覆盖表）。"""
        dom = norm_domain(domain)
        self._override[dom] = {k: v for k, v in flags.items() if v is not None}
        return self.get(dom)

    def forget(self, domain: str) -> None:
        with self._lock:
            self._load()
            self._caps.pop(norm_domain(domain), None)
        self._save()

    # ------------------------------------------------------------- 探针
    def needs_probe(self, domain: str) -> bool:
        dom = norm_domain(domain)
        if dom in self._override:
            return False
        with self._lock:
            self._load()
            cap = self._caps.get(dom)
        if cap is None:
            return True
        if int(cap.probe_ver or 0) < PROBE_VER:
            return True                        # 识别逻辑升级过 → 旧结论作废，重探一次
        if cap.framework == FW_UNKNOWN:
            return cap.age > 6 * 3600.0        # 判不出 → 6h 后再试
        return cap.age > PROBE_TTL

    def ensure(self, site: Any, probe: bool = False, fetch=None, gate=None) -> SiteCap:
        """取能力；缺失/过期且 ``probe=True`` 时联网探一次。

        Args:
            site: MoviePilot ``Site`` 对象（需要 ``domain``/``url``/``cookie``/``ua``）。
            probe: 是否允许联网探测。
            fetch: 可注入的抓取函数 ``(url) -> str``（测试用；默认用 SDK RequestUtils）。
            gate: 可选的 ``() -> bool`` 闸门；返回 False 则不探测（
                调用方用来接 PV 预算/站点封禁，保证探针不绕过配额）。
        """
        dom = norm_domain(getattr(site, "domain", "") or "")
        cap = self.get(dom)
        if not probe or not self.needs_probe(dom):
            return cap
        if gate is not None:
            try:
                if not gate():
                    cap.notes = list(dict.fromkeys(list(cap.notes) + ["probe-skipped:gate"]))
                    return cap
            except Exception:  # noqa: BLE001
                return cap
        if fetch is None:
            fetch = self._make_fetcher(site)
        if fetch is None:
            return cap
        base = (getattr(site, "url", "") or f"https://{dom}").rstrip("/")
        for path in PROBE_PATHS:
            try:
                text = fetch(base + path)
            except Exception:  # noqa: BLE001
                text = ""
            fw, ev = detect_framework(text, dom)
            if fw != FW_UNKNOWN:
                return self.learn(dom, fw, ev, source="marker")
            if text:
                break       # 有响应但认不出 → 不再试后面路径
        # 都不行：记一条「未知 + 时间戳」，避免每次都重试
        return self.record(dom, SiteCap(domain=dom, framework=FW_UNKNOWN,
                                        source="probe", evidence="no-marker")) 

    def _make_fetcher(self, site: Any):
        """造一个 ``(url) -> text`` 抓取器（仅本站域名）。

        ★ 3.38.0：优先走采集模块（唯一出口 + 配额闸门）；未注入时退回 SDK。
        """
        base = (getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}").rstrip("/")
        cookie = str(getattr(site, "cookie", None) or "").strip() or None
        ua = str(getattr(site, "ua", None) or "").strip() or None   # ★ 前导空白 → httpx 判非法头

        _c = getattr(getattr(self, "_plugin", None), "collect", None)
        _sid = int(getattr(site, "id", 0) or 0)
        if _c is not None and _sid:
            try:
                req = _c.http.client(_sid, kind="sitecap", referer=f"{base}/")
            except Exception:  # noqa: BLE001
                return None
        else:
            try:
                from app.sdk.network import RequestUtils  # noqa: WPS433
            except Exception:  # noqa: BLE001
                return None
            try:
                req = RequestUtils(cookies=cookie, ua=ua, timeout=20, referer=f"{base}/")
            except Exception:  # noqa: BLE001
                return None

        def _fetch(url: str) -> str:
            if not url.lower().startswith(base.lower()):
                return ""
            resp = req.get_res(url)
            if resp is None:
                return ""
            try:
                txt = resp.text or ""
            except Exception:  # noqa: BLE001
                txt = ""
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
            return txt or ""

        return _fetch


# ---------------------------------------------------------------------------
# 自测：直接用本机保存的页面文本验证判定函数（不联网）
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import glob
    import os

    cases = [
        ("/tmp/freepages/hdtime.org_sp2_p0.html", "hdtime.org", FW_NEXUS),
        ("/tmp/freepages/cspt.top_sp2_p0.html", "cspt.top", FW_NEXUS),
    ]
    ok = True
    for path, dom, want in cases:
        if not os.path.exists(path):
            print(f"[skip] {path} 不存在")
            continue
        text = open(path, encoding="utf-8", errors="ignore").read()
        got, ev = detect_framework(text, dom)
        flag = "OK " if got == want else "FAIL"
        ok = ok and got == want
        print(f"[{flag}] {dom}: {got} ({ev})  期望 {want}")
    for f in sorted(glob.glob("/tmp/freepages/*.html")):
        text = open(f, encoding="utf-8", errors="ignore").read()
        print(f"  {os.path.basename(f):34s} -> {detect_framework(text)[0]}")
    print("SELFTEST", "PASS" if ok else "FAIL")
