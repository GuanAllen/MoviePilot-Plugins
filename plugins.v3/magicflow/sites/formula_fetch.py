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
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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


# ★ 3.38.0：站点请求唯一出口 = 采集模块。这里注入；未注入（离线单测）退回 SDK。
_COLLECT = None


def set_collect(ref: Any) -> None:
    """注入采集模块（由插件 init 调用）。"""
    global _COLLECT
    _COLLECT = ref


def _mk_client(site: Any, base: str, kind: str, cookie: Any = None, ua: Any = None,
               timeout: int = 20, force: bool = False):
    """造一个 ``.get_res(url)`` 客户端：优先采集模块（配额/缓存/观测），否则 SDK。

    ``force=True`` → 采集侧 ``ttl=0``（既不读缓存也不写缓存），用于零值重抓。
    """
    sid = int(getattr(site, "id", 0) or 0)
    if _COLLECT is not None and sid:
        try:
            return _COLLECT.http.client(sid, kind=kind, referer=f"{base}/",
                                        ttl=0.0 if force else None)
        except Exception:  # noqa: BLE001
            pass
    from app.sdk.network import RequestUtils  # noqa: WPS433
    return RequestUtils(cookies=cookie, ua=ua, timeout=timeout, referer=f"{base}/")



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


# ★ 7.4.0：各站把「魔力」叫法不同——NexusPHP 默认「魔力值」，
#   财神(cspt.top) 叫「金元宝」，个别站叫「魔力/金币/积分」。解析必须按站点措辞放宽，
#   否则该站页面里明明写着「你当前每小时能获取X个金元宝 (A = Y)」也解析不出时魔。
# ★ 19.10.47：还有站点**自造货币名**（蟹黄堡 crabpt.vip 叫「蟹币值」，
#   原文「你当前每小时能获取 131.273 个蟹币值 (A = 1542.7)」）——
#   硬编码词表永远追不上站点改名，故追加一条通用形状「N 个汉字 + 值」兜底。
_CUR_WORDS = r"魔力值|金元宝|元宝|魔力|金币|银币|积分|煤块|Karma"
_CUR_GENERIC = r"[\u4e00-\u9fa5]{1,6}值"
_CUR = rf"(?:{_CUR_WORDS}|{_CUR_GENERIC})"

# 顶部状态栏的货币单位可能**不带「值」**（「蟹币值(131.27蟹币/小时)」的左值是「蟹币」）
_CUR_UNIT = rf"(?:{_CUR_WORDS}|[\u4e00-\u9fa5]{{1,6}})"

# 「每小时获得的合计<货币>」表的锚点（找不到就退回页首）
_TABLE_ANCHOR = re.compile(rf"合计\s*{_CUR}")

# ★ 19.10.48：各站把「魔力」叫成自己的名字（蟹币值 / 金元宝 / 积分 / 煤块…），
#   界面上统一写「魔力」会让两套互不通兑的经济系统看起来像同一个东西。
#   这里把**站点原文里的货币名**捞出来，往下透传到 API，前端按站点显示。
#   三级优先：表头「合计<货币>」最权威 → 「每小时能获取 N 个<货币>」→ 顶部状态栏「<货币>(N/h)」。
_CUR_NAME_ANCHOR = re.compile(rf"合计\s*({_CUR})")
_CUR_NAME_HOURLY = re.compile(
    rf"当前每小时[能可]?\s*(?:获取|获得)\s*[\d,.]+\s*个\s*({_CUR})"
)
_CUR_NAME_BAR = re.compile(rf"({_CUR})\s*[（(]\s*[\d,.]+\s*(?:{_CUR_WORDS}|[\u4e00-\u9fa5]{{1,6}})?\s*/\s*小时")


def detect_currency_name(text: str) -> str:
    """从 mybonus 页面文本里认出该站对「魔力」的**自称**（纯函数）。

    站点各自命名：默认 NexusPHP「魔力值」、财神「金元宝」、蟹黄堡「蟹币值」、
    野马PT「积分」。认不出返回空串（调用方兜底「魔力值」），绝不编造。
    """
    if not text:
        return ""
    for pat in (_CUR_NAME_ANCHOR, _CUR_NAME_HOURLY, _CUR_NAME_BAR):
        m = pat.search(text)
        if not m:
            continue
        name = (m.group(1) or "").strip()
        # 粗筛：2~8 个字符、不含「的」（避免从句子中间截出残片）
        if 2 <= len(name) <= 8 and "的" not in name:
            return name
    return ""


def _cell_text(raw: str) -> str:
    """单元格文本：去标签 + 实体解码 + 折叠空白。"""
    return re.sub(r"[ \t\r\n\u00a0]+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def parse_bonus_table(html_text: str) -> Dict[str, Any]:
    """解析 mybonus「每小时获得的合计魔力值」表（纯函数）。

    表头：奖励类型 | 数量 | 体积 | A 值 | 基础魔力 | 系数 | 获得魔力 | 合计(rowspan)
    行例：``基本奖励 | 36 | 397.52 GB | 24.462 | 15.980 | 1 | 15.980``。

    返回 ``{'rows': [...], 'total': float|None, 'base': row|None,
    'official': row|None, 'harem': row|None}``。
    """
    out: Dict[str, Any] = {"rows": [], "total": None, "base": None, "official": None, "harem": None}
    if not html_text:
        return out
    _am = _TABLE_ANCHOR.search(html_text)
    anchor = _am.start() if _am else 0
    seg = html_text[anchor:anchor + 4000]
    m = re.search(r"<table[^>]*>(.*?)</table>", seg, re.S | re.I)
    if not m:
        return out
    table = m.group(1)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
    for row in rows:
        cells = [_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        if not cells:
            continue
        if "奖励类型" in cells[0] or cells[0].startswith("奖励"):
            continue
        item = {
            "label": cells[0],
            "count": cells[1] if len(cells) > 1 else "",
            "size_text": cells[2] if len(cells) > 2 else "",
            "a_value": _to_float(cells[3]) if len(cells) > 3 else None,
            "base_bonus": _to_float(cells[4]) if len(cells) > 4 else None,
            "coef": _to_float(cells[5]) if len(cells) > 5 else None,
            "earned": _to_float(cells[6]) if len(cells) > 6 else None,
        }
        if len(cells) > 7:
            tot = _to_float(cells[7])
            if tot is not None:
                out["total"] = tot
        out["rows"].append(item)
        label = item["label"]
        if "基本" in label and out["base"] is None:
            out["base"] = item
        elif "官种" in label and out["official"] is None:
            out["official"] = item
        elif "后宫" in label and out["harem"] is None:
            out["harem"] = item
    if out["total"] is None and out["rows"]:
        earned = [r["earned"] for r in out["rows"] if r.get("earned") is not None]
        if earned:
            out["total"] = round(sum(earned), 6)
    return out


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
    # 站点对该货币的自称（界面按站点显示，不统一叫「魔力」）
    _cur_name = detect_currency_name(text)
    if _cur_name:
        extra["currency"] = _cur_name
    m = re.search(r"官种系数[:：为]*\s*([\d.]+)", text)
    if m:
        extra["official_coef"] = _to_float(m.group(1))
    m = re.search(r"后宫加成系数[:：为，,、\s]*当前[值为:：]*\s*([\d.]+)", text)
    if m:
        extra["harem_coef"] = _to_float(m.group(1))
    m = re.search(r"做种数最多计\s*(\d+)\s*个", text)
    if m:
        extra["seeding_count_cap"] = int(m.group(1))
    m = re.search(rf"([\d.]+)\s*个{_CUR}\s*\*\s*你的做种数", text)
    if m:
        extra["per_torrent_flat"] = _to_float(m.group(1))
    # 时魔：「你当前每小时能获取15个魔力值 (A = 59.7，每小时魔力详情)」
    # 各站措辞/标点不一（能获取/获得、半/全角括号、A 值后可能跟说明文字），故放宽：
    #   - 动词：当前每小时[能可]?(获取|获得)
    #   - 括号：半角 ( ) 或全角 （ ）
    #   - A 值之后允许任意非括号字符（如「，每小时魔力详情」）再到右括号
    m = re.search(
        rf"当前每小时[能可]?\s*(?:获取|获得)\s*([\d,.]+)\s*个{_CUR}\s*[（(]\s*A\s*=\s*([\d,.]+)[^)）]*[)）]",
        text,
    )
    if m:
        extra["current_bonus_per_hour"] = _to_float(m.group(1))
        extra["current_a"] = _to_float(m.group(2))
    else:
        # 兜底：顶部状态栏「魔力值(15魔力/小时)」/「蟹币值(131.27蟹币/小时)」
        m2 = re.search(rf"{_CUR}\s*[（(]\s*([\d,.]+)\s*{_CUR_UNIT}\s*/\s*小时\s*[)）]", text)
        if m2:
            extra["current_bonus_per_hour"] = _to_float(m2.group(1))

    # 5) 「每小时获得的合计魔力值」表（数量/体积/A值/基础魔力/系数/获得/合计）
    bt = parse_bonus_table(html_text)
    if bt["rows"]:
        extra["bonus_table"] = bt["rows"]
        if bt["total"] is not None:
            extra["total_bonus_per_hour"] = bt["total"]
        base = bt.get("base") or {}
        if base:
            extra["base_count"] = base.get("count")
            extra["base_size_text"] = base.get("size_text")
            extra["base_a"] = base.get("a_value")
            extra["base_bonus"] = base.get("earned")
        off = bt.get("official") or {}
        if off:
            extra["official_bonus"] = off.get("earned")
        harem = bt.get("harem") or {}
        if harem:
            extra["harem_bonus"] = harem.get("earned")
            hc = _to_float(str(harem.get("coef"))) if harem.get("coef") is not None else None
            he = harem.get("earned")
            if hc and hc > 0 and he is not None:
                extra["harem_hourly"] = round(he / hc, 6)
    cap.extra = {k: v for k, v in extra.items() if v is not None}

    cap.ok = bool(cap.expr_a or cap.expr_b or cap.params)
    if not cap.ok:
        cap.note = "未解析到公式或参数（可能非标准 NexusPHP 页面）"
    return cap


# ============================================================
# M-Team（馒头）：SPA 站点，无 mybonus.php HTML，改走 x-api-key 接口
# ============================================================

_MTEAM_HOSTS = ("m-team.cc", "m-team.io")
_MTEAM_API_BASES = (
    "https://api.m-team.cc/api",
    "https://api2.m-team.cc/api",
    "https://api.m-team.io/api",
)


def is_mteam_domain(domain: Optional[str]) -> bool:
    """是否为 M-Team（馒头）站点。"""
    d = (domain or "").strip().lower()
    return any(h in d for h in _MTEAM_HOSTS)


def parse_mteam_bonus(payload: Optional[dict]) -> FormulaCapture:
    """解析 M-Team ``/api/tracker/mybonus`` 响应（纯函数）。

    关键字段（``data.formulaParams``）：
      * ``tzeroBonus/nzeroBonus/bzeroBonus/lbonus`` → T0/N0/B0/L
      * ``finalBs``（= ``allBonus``）→ **时魔（每小时魔力值）**
      * ``a`` → 当前 A 值
      * ``torrentMsSum`` → 做种数上限；``perseedingBonus`` → 每做种基础
    """
    cap = FormulaCapture(source="mteam-api")
    data = ((payload or {}).get("data") or {}) if isinstance(payload, dict) else {}
    fp = data.get("formulaParams") or {}
    if not fp:
        cap.note = "M-Team 返回缺少 formulaParams"
        return cap

    def _f(key: str) -> Optional[float]:
        return _to_float(fp.get(key))

    for fld, key in (("t0", "tzeroBonus"), ("n0", "nzeroBonus"), ("b0", "bzeroBonus"), ("l", "lbonus")):
        val = _f(key)
        if val is not None:
            cap.params[fld] = val

    extra: Dict[str, Any] = {}
    # M-Team 对该货币自称「魔力值」（与 NexusPHP 默认同名，但这里显式写明以便透传）
    extra["currency"] = "魔力值"
    hourly = _f("finalBs")
    if hourly is None:
        hourly = _f("allBonus")
    if hourly is not None:
        extra["current_bonus_per_hour"] = hourly
    a_val = _f("a")
    if a_val is not None:
        extra["current_a"] = a_val
    cap_n = _f("torrentMsSum")
    if cap_n is not None:
        extra["seeding_count_cap"] = int(cap_n)
    flat = _f("perseedingBonus")
    if flat is not None:
        extra["per_torrent_flat"] = flat
    # 明细（等级/捐赠/2FA/两步加成/每做种上限），供诊断与后续校准
    for key in ("userClassBs", "donorBs", "tfaBs", "h24UpBs", "callBonus", "twoStepBonus", "maxseedingBonus"):
        val = _f(key)
        if val is not None:
            extra[f"mteam_{key}"] = val
    cap.extra = {k: v for k, v in extra.items() if v is not None}
    # M-Team 与 NexusPHP 同形公式，补齐表达式以便前端展示
    cap.expr_a = (
        "A = sigma( ( 1 - 10 ^ ( - Ti / T0 ) ) * Si * "
        "( 1 + sqrt( 2 ) * 10 ^ ( - ( Ni - 1 ) / ( N0 - 1 ) ) ) * Wi"
    )
    cap.expr_b = "B = B0 * 2 / pi * arctan( A / L )"
    cap.ok = bool(cap.params or extra)
    if cap.ok:
        cap.note = "M-Team tracker/mybonus API"
    return cap


# ★ M-Team 官方魔力公式常量（来源：官方 wiki「官方種子魔力獎勵公式」+
#   ``/api/tracker/mybonus`` 实测）。用于 API 拿不到参数时**离线兜底**（不依赖会话/网络）：
#     B = B0 * 2/pi * arctan( A / L )
#     A = Σ_{i=1..min(n,cap)} ( 1 - 10^(-Ti/T0) ) * Si * ( 1 + sqrt(2) * 10^(-(Ni-1)/(N0-1)) )
# 注：站点**无做种数上限**；``cap`` 只是「**计入魔力**」的收益上限（超过后时魔不再增长）。
_MTEAM_WIKI_PARAMS: Dict[str, Any] = {"t0": 4.0, "n0": 7.0, "b0": 50.0, "l": 300.0}
_MTEAM_WIKI_EXTRA: Dict[str, Any] = {"seeding_count_cap": 100, "per_torrent_flat": 0.1}


def mteam_builtin_formula() -> FormulaCapture:
    """M-Team 内置公式常量（官方 wiki 公开）—— API 失败时的离线兜底。"""
    cap = FormulaCapture(source="mteam-wiki", note="M-Team 官方公式常量（wiki + API 实测）")
    cap.params = dict(_MTEAM_WIKI_PARAMS)
    cap.extra = dict(_MTEAM_WIKI_EXTRA)
    cap.expr_a = (
        "A = sigma_{i=1..min(n,cap)}( ( 1 - 10 ^ ( - Ti / T0 ) ) * Si * "
        "( 1 + sqrt( 2 ) * 10 ^ ( - ( Ni - 1 ) / ( N0 - 1 ) ) ) )"
    )
    cap.expr_b = "B = B0 * 2 / pi * arctan( A / L )"
    cap.ok = True
    return cap


def fetch_mteam_bonus(site: Any, timeout: int = 30) -> FormulaCapture:
    """用站点 API Key（``x-api-key``）抓 M-Team 的魔力公式与时魔。"""
    apikey = (getattr(site, "apikey", None) or "").strip()
    ua = getattr(site, "ua", None) or _DEFAULT_UA
    if not apikey:
        return FormulaCapture(source="mteam-api", note="站点未配置 API Key")
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433 (惰性导入)
    except Exception as err:  # MoviePilot SDK 不可用（如离线单测）
        return FormulaCapture(source="mteam-api", note=f"SDK 不可用: {err}")

    headers = {
        "User-Agent": ua,
        "x-api-key": apikey,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": "https://kp.m-team.cc/",
    }
    note = ""
    for base in _MTEAM_API_BASES:
        url = f"{base}/tracker/mybonus"
        try:
            req = RequestUtils(headers=headers, timeout=timeout)
            resp = req.post_res(url, json={})
        except Exception as err:
            note = f"{url} 请求异常: {err}"
            continue
        if resp is None or not getattr(resp, "ok", False):
            note = f"{url} HTTP {getattr(resp, 'status_code', '?')}"
            continue
        try:
            payload = resp.json()
        except Exception as err:
            note = f"{url} 非 JSON: {err}"
            continue
        finally:
            try:
                resp.close()
            except Exception:
                pass
        cap = parse_mteam_bonus(payload)
        if cap.ok:
            return cap
        note = cap.note
    # ★ 3.46.0：API 拿不到（如 x-api-key 无权限 / 站点收紧）→ 回退官方 wiki 常量，
    #   保证馒头时魔估算仍按官方公式（T0=4/N0=7/B0=50/L=300），零网络依赖。
    fallback = mteam_builtin_formula()
    fallback.note = f"{note or 'M-Team API 全部失败'} → 已回退官方 wiki 常量"
    return fallback


# ============================================================
# YemaPT（野马PT）：SPA 站点，无 mybonus.php
#   时魔只在**前端私有接口** ``/api/consumer/fetchPointPageInfo`` 里，
#   取 ``data.currentHourPoint`` 的「做种贡献 + 基础 + 发布人奖励」**三项之和**
#   （站点「每小时产出」卡片就是这么算的）
#   ⚠ 该接口只认 **cookie**；``/openApi/*`` 只认 apikey 且**不提供任何速率字段**，
#     两条通道互斥（官方 wiki：Cookie 中的登录 auth 不能用于开放 API，反之亦然）。
# ============================================================

_YEMA_HOSTS = ("yemapt.org",)


def is_yema_domain(domain: Optional[str]) -> bool:
    """是否为 YemaPT（野马PT）站点。"""
    d = (domain or "").strip().lower()
    return any(h in d for h in _YEMA_HOSTS)


def parse_yema_point(payload: Optional[dict]) -> FormulaCapture:
    """解析 YemaPT ``/api/consumer/fetchPointPageInfo``（纯函数）。

    ⚠ 时魔 = **三项之和**，不是 ``hourPoint`` 一项。站点前端（growth 页 chunk）原文：

        hourlyPoints = hourPoint + hourBasePoint + hourOwnerPoint

    这个和渲染在标题为「每小时产出」的卡片上，tooltip 拆解为
    「做种贡献积分 + 基础积分 + 发布人奖励积分」。只取 ``hourPoint`` 会少算
    基础积分那一块（实测 25 vs 站点显示 47）。

    关键字段：
      * ``currentHourPoint.hourPoint`` → 做种贡献积分（**不是**总时魔）
      * ``currentHourPoint.hourBasePoint`` → 基础积分（登录即有的保底）
      * ``currentHourPoint.hourOwnerPoint`` → 发布人奖励积分（自己发的种）
      * ``currentHourPoint.hourA`` → 当前 A 值
      * ``seedPointRule`` 的 ``t0/n0/b0/l`` → 与 NexusPHP 同形的公式参数
      * ``seedPointRule.seedMaxTorrentNum`` → 计入积分的最多种子数
      * ``seedPointRule.torrentBasePoint`` → 每个种子的基础分
    """
    cap = FormulaCapture(source="yemapt-point")
    data = ((payload or {}).get("data") or {}) if isinstance(payload, dict) else {}
    if not data:
        cap.note = "YemaPT 返回缺少 data"
        return cap
    rule = data.get("seedPointRule") or {}
    for fld in ("t0", "n0", "b0", "l"):
        val = _to_float(rule.get(fld))
        if val is not None:
            cap.params[fld] = val
    hourly = data.get("currentHourPoint") or {}
    extra: Dict[str, Any] = {}
    # 站点自称是「积分」（前端原文：「每小时能获取 X 个积分」）
    extra["currency"] = "积分"
    # 三项求和 —— 与站点「每小时产出」卡片同口径
    parts: Dict[str, float] = {}
    for key in ("hourPoint", "hourBasePoint", "hourOwnerPoint"):
        val = _to_float(hourly.get(key))
        if val is not None:
            parts[key] = val
            extra[f"yema_{key}"] = val
    rate: Optional[float] = None
    if parts:
        rate = round(sum(parts.values()), 3)
        extra["total_bonus_per_hour"] = rate
        # 只算了做种贡献、不含基础分的旧口径，留作诊断对照
        if "hourPoint" in parts and len(parts) > 1:
            extra["yema_seed_only"] = parts["hourPoint"]
    a_val = _to_float(hourly.get("hourA"))
    if a_val is not None:
        extra["current_a"] = a_val
    bonus = _to_float(data.get("bonus"))
    if bonus is not None:
        extra["yema_bonus"] = bonus
    cap_n = _to_float(rule.get("seedMaxTorrentNum"))
    if cap_n is not None:
        extra["seeding_count_cap"] = int(cap_n)
    flat = _to_float(rule.get("torrentBasePoint"))
    if flat is not None:
        extra["per_torrent_flat"] = flat
    cap.extra = extra
    cap.ok = bool(rate is not None or cap.params)
    if cap.ok:
        cap.note = "YemaPT consumer/fetchPointPageInfo"
    return cap


def fetch_yema_bonus(site: Any, timeout: int = 30) -> FormulaCapture:
    """用站点 **cookie** 抓 YemaPT 积分页，取站点自报时魔。

    返回 ``FormulaCapture``；``ok=False`` 时 ``note`` 带诊断（缺 cookie / 未授权 /
    HTTP 码），调用方按既有降级链继续（实测折算 → 趋势值）。
    """
    domain = (getattr(site, "domain", "") or "").strip()
    base = (getattr(site, "url", "") or "").strip().rstrip("/")
    if not base and domain:
        base = f"https://{domain}"
    cookie = getattr(site, "cookie", None)
    ua = getattr(site, "ua", None) or _DEFAULT_UA
    if not base:
        return FormulaCapture(source="yemapt-point", note="站点缺少 url/domain")
    if not cookie:
        return FormulaCapture(source="yemapt-point", note="站点未配置 Cookie（该接口只认 cookie）")

    url = f"{base}/api/consumer/fetchPointPageInfo"
    try:
        req = _mk_client(site, base, "formula", cookie=cookie, ua=ua, timeout=timeout)
        resp = req.get_res(url)
    except Exception as err:  # noqa: BLE001（采集层绝不抛，这里只兜 SDK 通道）
        return FormulaCapture(source="yemapt-point", note=f"请求失败: {err}")
    if resp is None:
        return FormulaCapture(source="yemapt-point", note="无响应")
    if not getattr(resp, "ok", False):
        return FormulaCapture(source="yemapt-point", note=f"HTTP {getattr(resp, 'status_code', '?')}")
    raw = getattr(resp, "text", "") or ""
    try:
        resp.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        payload = json.loads(raw)
    except Exception as err:  # noqa: BLE001
        return FormulaCapture(source="yemapt-point", note=f"非 JSON: {err}")
    if not isinstance(payload, dict) or not payload.get("success"):
        # 未登录的典型形态：{"success":false,"showType":2,"errorMessage":"","errorCode":400}
        code = ""
        if isinstance(payload, dict):
            code = str(payload.get("errorCode") or payload.get("errorMessage") or "")
        return FormulaCapture(source="yemapt-point", note=f"接口未授权（Cookie 可能已失效）{code}")
    cap = parse_yema_point(payload)
    if cap.ok:
        cap.note = f"{domain or base} consumer/fetchPointPageInfo"
    return cap


def fetch_site_formula(site: Any, timeout: int = 60, force: bool = False) -> FormulaCapture:
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

    # M-Team（馒头）是 SPA，mybonus.php 无 HTML 可解析 → 走官方 API。
    if is_mteam_domain(domain):
        return fetch_mteam_bonus(site, timeout=timeout)

    # ★ 19.10.47：YemaPT 同样是 SPA（``/mybonus.php`` 返回文档站首页，仅 30 字节），
    #   时魔只在 cookie 侧的 ``/api/consumer/fetchPointPageInfo`` 里 → 走专用通道。
    if is_yema_domain(domain):
        return fetch_yema_bonus(site, timeout=timeout)

    url = f"{base}/mybonus.php"
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433 (惰性导入)
    except Exception as err:  # MoviePilot SDK 不可用（如离线单测）
        return FormulaCapture(source="mybonus.php", note=f"SDK 不可用: {err}")

    try:
        req = _mk_client(site, base, "formula", cookie=cookie, ua=ua, timeout=timeout, force=force)
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


def parse_torrent_promotion(html_text: str) -> Dict[str, Any]:
    """从 NexusPHP / PTT-NP 详情页解析促销状态。

    详情页标题行（``<h1 id='top'>``）内含促销括号，如：
      ``标题 [免费 57分钟][0个做种者]`` / ``标题 [50%免费][2个做种者]`` / ``标题 [2X免费][1个做种者]``
    非免费种子只有 ``[N个做种者]``。

    返回 ``{"promotion": ..., "raw": ...}``，promotion 取值：
      - ``free``     全站免费（下载不计量）
      - ``2xfree``   2X 免费（下载不计，上传 2X）
      - ``partial``  部分免费（50% / 30% 等，下载仍计一部分量）
      - ``twoup``    仅 2X 上传（下载照常计费，**非免费**）
      - ``none``     无促销（非免费）
      - ``unknown``  无法解析（未找到标题区 / 页面异常）→ 调用方应跳过，不删种
    """
    if not html_text:
        return {"promotion": "unknown", "raw": ""}
    # ★ 促销信息的位置**因皮肤而异**，不能只看 <h1>：
    #   ① 经典 NexusPHP：``<h1 id='top'>标题 [免费 57分钟][0个做种者]</h1>``
    #   ② 新版（dstudio 等）：``<header id="top">…<h1 class="details-title">标题</h1>
    #      <div class="details-title-statuses"><span>[ <font class='free'>免费</font> ]
    #      剩余时间：…</span></div>…</header>`` → 促销在 h1 **之后**的兄弟块里
    _anchor = re.search(r"id=['\"]?top['\"]?[^>]*>", html_text, re.I)
    if not _anchor:
        return {"promotion": "unknown", "raw": ""}
    _start = _anchor.end()
    raw = ""
    _scope_htmls: List[str] = []
    _h1end = html_text.find("</h1>", _start)
    if 0 <= _h1end and (_h1end - _start) <= 20000:
        _scope_htmls.append(html_text[_start:_h1end])          # ① 经典
    _tail = html_text[_start:_start + 20000]
    _hend = _tail.lower().find("</header>")
    _hdrend = _tail.lower().find("</div>", 0, 4000)
    _scope_htmls.append(_tail[:_hend] if 0 <= _hend <= 4000 else _tail[:2500])   # ② 新版
    for _sh in _scope_htmls:
        _txt = re.sub(r"<[^>]+>", " ", _sh).replace("&nbsp;", " ")
        for bracket in re.findall(r"\[([^\[\]]{1,40})\]", _txt):
            txt = bracket.strip()
            if "免费" in txt or "2x" in txt.lower() or "%" in txt or "半价" in txt:
                raw = txt
                break
        if raw:
            break
    # ③ 蓝图兜底：促销用 <img class="pro_free"> 标、括号文本不在标题区
    if not raw and _scope_htmls:
        _blk = _scope_htmls[-1]
        if re.search(r'class=["\']pro_free2up["\']', _blk):
            raw = "2X免费"
        elif re.search(r'class=["\']pro_free["\']', _blk):
            raw = "免费"
        elif re.search(r'class=["\']pro_(?:50|30|25)pctdown["\']', _blk):
            raw = "50%"
    # 免费到期（限时）→ 供调用方参考
    _fu = ""
    if _scope_htmls:
        _fm = re.search(
            r"剩余时间[：:]\s*<span[^>]*title=[\"'](\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[\"']",
            _scope_htmls[-1],
        )
        if _fm:
            _fu = _fm.group(1)
    if not raw:
        return {"promotion": "none", "raw": "", "free_until": _fu}
    low = raw.lower()
    if "50%" in raw or "30%" in raw or "25%" in raw or "半价" in raw:
        promo = "partial"
    elif "免费" in raw:
        promo = "2xfree" if "2x" in low else "free"
    elif "2x" in low:
        promo = "twoup"
    else:
        promo = "none"
    return {"promotion": promo, "raw": raw, "free_until": _fu}


def fetch_torrent_promotion(site: Any, page_url: str, timeout: int = 20) -> Dict[str, Any]:
    """抓取单个种子详情页并解析促销/免费状态。cookie/UA 取自站点配置。

    返回 ``{"promotion": ..., "raw": ..., "length"?: int, "error"?: str}``。
    任何异常都返回 ``promotion=unknown``（调用方据此跳过，不误删）。
    """
    if not page_url:
        return {"promotion": "unknown", "raw": "", "error": "缺少页面 URL"}
    domain = (getattr(site, "domain", "") or "").strip()
    base = (getattr(site, "url", "") or (f"https://{domain}" if domain else "")).rstrip("/")
    cookie = getattr(site, "cookie", None)
    ua = getattr(site, "ua", None) or _DEFAULT_UA
    url = page_url.strip()
    if url.startswith("//"):
        url = "https:" + url
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433 (惰性导入)
    except Exception as err:
        return {"promotion": "unknown", "raw": "", "error": f"SDK 不可用: {err}"}
    try:
        req = _mk_client(site, base, "promo", cookie=cookie, ua=ua, timeout=timeout)
        resp = req.get_res(url)
    except Exception as err:
        return {"promotion": "unknown", "raw": "", "error": f"请求失败: {err}"}
    if resp is None or not getattr(resp, "ok", False):
        code = getattr(resp, "status_code", "?")
        try:
            resp and resp.close()
        except Exception:
            pass
        return {"promotion": "unknown", "raw": "", "error": f"HTTP {code}"}
    try:
        raw_bytes = resp.content
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("gbk", "ignore")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    out = parse_torrent_promotion(text)
    out["length"] = len(text)
    return out


def _list_page_text(
    site: Any, base: str, userid: Any, ttype: str, page: int,
    cookie: Any, ua: Any, timeout: int,
) -> str:
    """抓「我的种子」列表的第 ``page`` 页，返回解码后的 HTML（失败返回空串）。

    ★ 分页参数必须与 ``userid``/``type`` 一起发：裸 ``?page=1`` 站点会返回空
    （NexusPHP 靠这两个参数定位用户，缺了就当未登录）。
    """
    url = f"{base}/getusertorrentlistajax.php?userid={int(userid)}&type={ttype}"
    if page:
        url += f"&page={int(page)}"
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433,F401
    except Exception:  # pragma: no cover - 离线环境
        return ""
    try:
        req = _mk_client(site, base, "seeding", cookie=cookie, ua=ua, timeout=timeout)
        resp = req.get_res(url)
    except Exception:
        return ""
    if resp is None or not getattr(resp, "ok", False):
        try:
            resp and resp.close()
        except Exception:
            pass
        return ""
    try:
        raw = resp.content
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("gbk", "ignore")
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _has_next_page(text: str, page: int) -> bool:
    """页面里是否还有「第 page+1 页」的链接（翻页终止判据，纯函数）。"""
    if not text:
        return False
    return bool(re.search(r"[?&]page=%d(?!\d)" % (int(page) + 1), text))


def fetch_user_torrent_rows(
    site: Any, userid: Any, ttype: str = "seeding",
    max_pages: int = 20, timeout: int = 25,
) -> Dict[str, Any]:
    """**分页**抓取用户种子列表，返回结构化行（认领判定的事实源）。

    NexusPHP 每页 100 条；只抓第一页是 19.10.48 前「认领扫描恒 0」的根因之一
    （咖啡 160 条只拿到 100 条）。

    返回 ``{'rows': [...], 'declared_total': int|None, 'pages': int, 'error': str}``，
    每行见 :func:`parse_user_torrent_rows`。任一页失败立即返回已拿到的部分。
    """
    domain = (getattr(site, "domain", "") or "").strip()
    base = (getattr(site, "url", "") or (f"https://{domain}" if domain else "")).rstrip("/")
    if not base or not userid:
        return {"rows": [], "declared_total": None, "pages": 0, "error": "no base/uid"}
    cookie = getattr(site, "cookie", None)
    ua = getattr(site, "ua", None) or _DEFAULT_UA
    rows: list = []
    seen_tid: set = set()
    declared = None
    pages = 0
    for page in range(max(1, min(int(max_pages or 1), 40))):
        text = _list_page_text(site, base, userid, ttype, page, cookie, ua, timeout)
        if not text.strip():
            break
        pages += 1
        if declared is None:
            mt = re.search(r"<b>(\d+)</b>\s*条记录", text)
            if mt:
                declared = int(mt.group(1))
        got = parse_user_torrent_rows(text)
        fresh = 0
        for r in got:
            key = r.get("tid") or r.get("title_norm")
            if not key or key in seen_tid:
                continue
            seen_tid.add(key)
            rows.append(r)
            fresh += 1
        if not got or not _has_next_page(text, page):
            break
        if not fresh:
            break
    return {"rows": rows, "declared_total": declared, "pages": pages, "error": ""}


def selector_marker(selector: str) -> str:
    """从 CSS selector 里取出可直接搜 HTML 的标记子串（离线纯函数）。

    详情页判定不引第三方选择器库，改用「站点自己声明的关键字」在页面里搜：

    - ``a[href*='add_torrent_id']`` → ``add_torrent_id``（学校这类 viewclaims 站）
    - ``button[data-action='addClaim']`` → ``addClaim``（新版认领插件）
    - ``#add-claim`` → ``add-claim``

    取不到就返回空串，调用方必须跳过详情页判定（宁可不判，不可猜）。
    """
    s = str(selector or "").strip()
    if not s:
        return ""
    m = re.search(r"\[[a-zA-Z-]+\*?=?['\"]?([^'\"]+)['\"]?\]", s)
    if m:
        return m.group(1).strip()
    m = re.search(r"[#.]([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1).strip()
    return ""


def fetch_claim_open_by_details(
    site: Any, tids: Any, claim_page: str, detail_selector: str,
    limit: int = 30, timeout: int = 20,
) -> Dict[str, bool]:
    """**逐个开种子详情页**判定「这颗能不能认领」—— viewclaims 型站专用通道。

    学校（pt.btschool.club）这类老式认领站，做种列表行里**没有** ``data-claim_id``
    （实测整页连 ``claim`` 字样都没有），所以 :func:`parse_user_torrent_rows` 对它
    只能给出 ``claim_state='none'``。它的认领入口只出现在种子详情页：

    - 未认领：详情页有 ``<a href="viewclaims.php?add_torrent_id={id}">[ 认领种子 ]</a>``
    - 已认领：整行消失，页面里搜不到 ``add_torrent_id``

    代价：一颗一次请求。所以**只对有限候选**（本站在做种的种子）跑，绝不拿它扫
    全站（学校 2274 页 ≈ 25 万颗，且实测新种也带按钮 → 可认领率 ~100%，
    扫全站既无筛选价值也会打爆站点）。

    返回 ``{tid: 是否可认领}``；取不到标记/无候选/整页失败都返回空表。
    """
    marker = selector_marker(detail_selector)
    if not marker:
        return {}
    ids = [str(t) for t in (tids or []) if str(t).isdigit()]
    if not ids:
        return {}
    domain = (getattr(site, "domain", "") or "").strip()
    base = (getattr(site, "url", "") or (f"https://{domain}" if domain else "")).rstrip("/")
    tpl = str(claim_page or "").strip()
    if not base or "{id}" not in tpl:
        return {}
    cookie = getattr(site, "cookie", None)
    ua = getattr(site, "ua", None) or _DEFAULT_UA
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433,F401
    except Exception:  # pragma: no cover - 离线环境
        return {}
    out: Dict[str, bool] = {}
    for tid in ids[: max(1, int(limit or 1))]:
        path = tpl.replace("{id}", tid)
        url = base + (path if path.startswith("/") else "/" + path)
        try:
            req = _mk_client(site, base, "details", cookie=cookie, ua=ua, timeout=timeout)
            resp = req.get_res(url)
        except Exception:
            continue
        if resp is None or not getattr(resp, "ok", False):
            try:
                resp and resp.close()
            except Exception:
                pass
            continue
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
        out[tid] = marker in text
    return out


def fetch_user_torrent_urls(
    site: Any, userid: Any, ttype: str = "leeching", timeout: int = 25
) -> Dict[str, str]:
    """抓取用户种子列表（``type=leeching/seeding``），返回 ``{规范化标题: 详情页URL}``。

    用于给「没记录详情页链接」的种子回填站点链接（由下载中/做种列表反查）。
    ★ 19.10.49 起分页抓全（原先只抓第一页，>100 条的站会漏）。
    """
    domain = (getattr(site, "domain", "") or "").strip()
    base = (getattr(site, "url", "") or (f"https://{domain}" if domain else "")).rstrip("/")
    data = fetch_user_torrent_rows(site, userid, ttype=ttype, timeout=timeout)
    out: Dict[str, str] = {}
    for r in data.get("rows") or []:
        tid = str(r.get("tid") or "").strip()
        norm = str(r.get("title_norm") or "")
        if tid and norm:
            out.setdefault(norm, f"{base}/details.php?id={tid}")
    return out


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


# 集数标记：站点侧与本地侧写法不一致，是认亲失败的最大单一来源（★ 19.10.51）。
#   站点「我的种子」列表常把整季折叠成单集：
#     S01.Complete / S01 Complete / S01E16 / S01E07-S01E08 / S01.E01-E12
#   本地下载器标题通常是发布名原样（S01.Complete 或 S01E01-E12）。
# 两边都归一到「季号」，差异即消失。
_EP_MARK_RE = re.compile(
    r'\b(s\d{1,2})'                                    # S01（**保留原数字**，别 int：对上要跟 s01 字面相等）
    r'(?:\s*[.\-_]?\s*e\d{1,3})'                       # 首集：E16 / .E16 / - E16
    # 可选区间尾。⚠ 分隔符必须含空格 —— ``_norm_title`` 已把 ``-``/``.`` 折成空格，
    # 进来的是 ``s01e07 s01e08``，只认连字符会漏掉（★ 19.10.51）。
    r'(?:[\s\-_]+(?:s\d{1,2}\s*[.\-_]?\s*)?e\d{1,3})?',
    re.I,
)
# S01.Complete / S01 Complete / S01-Complete
_EP_COMPLETE_RE = re.compile(r'\b(s\d{1,2})\s*[.\-_]?\s*complete\b', re.I)
# 游离的 complete（如 "...2026 Complete 2160p..."，没有季号可依附）
_LOOSE_COMPLETE_RE = re.compile(r'\bcomplete\b', re.I)


def _norm_title_loose(title: str) -> str:
    """标题**松**规范化：在 :func:`_norm_title` 之上再抹平集数写法差异。

    只在精确匹配失败时做**等值**兜底，绝不用于模糊比分 —— 松 key 会丢掉集数信息，
    拿它算相似度必然引入假阳性（实测「Pokémon 日月」vs「Dogul.Wang」模糊比 0.67）。
    """
    t = _norm_title(title)
    if not t:
        return t
    t = _EP_MARK_RE.sub(lambda m: m.group(1), t)
    t = _EP_COMPLETE_RE.sub(lambda m: m.group(1), t)
    t = _LOOSE_COMPLETE_RE.sub(' ', t)
    return re.sub(r'\s+', ' ', t).strip()


# ---------------------------------------------------------------- 标题摘要
#
# ★ 19.10.53：认领列表此前**只有站点原文标题**，而站点标题长这样：
#     「Battle of Britain 1969 AUS UHD BluRay 2160p REMUX HEVC DTS-HD MA 5.1 DoVi
#       HDR 2Audio-UBits」
#   用户在「可认领」里认不出这是哪部片，也就判断不了「这颗值不值得我承诺保种」
#   （咖啡不达标 −3000 魔力）。认领是用户行为，看不懂 = 没有决策依据。
#
#   这里只做**零成本的结构化**（不联网、不猜片名）：把年份/分辨率/来源/季集/压制组/
#   标题里自带的中文拆成独立字段，让界面能排成一行规格。
#   ★ 试过让识别链给中文名，实测**不可用**：MP 识别链一次 32s 还返空，媒体库转移
#     历史 0 行 → 已撤。界面改为「原文标题 + 本地规格 + 站点详情页直达」，
#     认片靠点开站点页看原名与简介，不猜。
_DIGEST_YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b(?!\s*[xXpP])')
_DIGEST_RES_RE = re.compile(r'\b(4320p|2160p|1080[pi]|720p|576[pi]|480p)\b', re.I)
# ★ 来源按**具体度**排序取第一个命中，不是按出现位置 —— 发布名常写成
#   "UHD BluRay 2160p REMUX"，按位置会取到 BLURAY 而丢掉更具体的 REMUX。
_DIGEST_SRC_ORDER = (
    ('REMUX', re.compile(r'\bremux\b', re.I)),
    ('BDRIP', re.compile(r'\b(?:bd|br)rip\b', re.I)),
    ('BLURAY', re.compile(r'\bblu-?ray\b', re.I)),
    ('WEB-DL', re.compile(r'\bweb-?dl\b', re.I)),
    ('WEBRip', re.compile(r'\bweb-?rip\b', re.I)),
    ('HDTV', re.compile(r'\bhdtv\b', re.I)),
    ('DVDRip', re.compile(r'\bdvdrip\b', re.I)),
    ('HDRip', re.compile(r'\bhdrip\b', re.I)),
)
_DIGEST_TAG_RE = re.compile(r'(?<![a-z0-9])s(\d{1,2})(?:\s*[.\-_]?\s*e(\d{1,3}))?', re.I)
_DIGEST_RANGE_RE = re.compile(r'e(\d{1,3})\s*-\s*(?:s\d{1,2}\s*)?e(\d{1,3})', re.I)
_DIGEST_GROUP_RE = re.compile(r'-([A-Za-z0-9@._]{2,20})$')
_DIGEST_CJK_RE = re.compile(r'[\u4e00-\u9fff][\u4e00-\u9fff0-9：:·、（）()！!？?\s]{0,40}')


def title_digest(title: str) -> dict:
    """把发布标题拆成结构化规格。**纯函数、零网络、恒有返回**。

    返回::

        {'year': 1969, 'res': '2160p', 'src': 'REMUX',
         'season': 1, 'ep': '01-12', 'pack': True, 'group': 'UBits', 'cn': ''}

    字段缺失一律 ``None`` / ``''``，不做猜测填充 —— 「未识别」必须可在界面上看出来，
    不能拿默认值冒充解析结果（铁律 8：算不出来要可见）。
    """
    raw = str(title or '')
    out = {'year': None, 'res': '', 'src': '', 'season': None,
           'ep': '', 'pack': False, 'group': '', 'cn': ''}
    if not raw.strip():
        return out
    m = _DIGEST_YEAR_RE.search(raw)
    if m:
        try:
            out['year'] = int(m.group(1))
        except (TypeError, ValueError):
            out['year'] = None
    m = _DIGEST_RES_RE.search(raw)
    if m:
        out['res'] = m.group(1).lower()
    for _label, _rx in _DIGEST_SRC_ORDER:
        if _rx.search(raw):
            out['src'] = _label
            break
    # 中文名：国内站常见「[字幕组]中文名.English.2024...」，取最长的一段 CJK。
    best = ''
    for seg in _DIGEST_CJK_RE.findall(raw):
        seg = seg.strip(' ·、：:')
        if len(seg) > len(best):
            best = seg
    out['cn'] = best[:40]
    m = _DIGEST_TAG_RE.search(raw)
    if m:
        try:
            out['season'] = int(m.group(1))
        except (TypeError, ValueError):
            out['season'] = None
        ep = m.group(2) or ''
        rng = _DIGEST_RANGE_RE.search(raw)
        if ep and rng:
            # S01E01-E12 / S01E01-E12 这类区间：保留首尾，用户才知道是整季还是单集
            ep = f'{ep}-{rng.group(2)}'
        out['ep'] = ep
        low = raw.lower()
        # 整季判定：显式 complete / 有区间 / 只给季号不给集号
        out['pack'] = bool(
            not ep or rng or 'complete' in low or '全集' in raw or '全季' in raw)
    m = _DIGEST_GROUP_RE.search(raw.strip())
    if m:
        out['group'] = m.group(1)
    return out


_ROW_TR_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S)
_ROW_TID_RE = re.compile(r'data-torrent_id="(\d+)"')
_ROW_DETAIL_RE = re.compile(r'details\.php\?id=(\d+)')
_ROW_CLAIM_ID_RE = re.compile(r'data-claim_id="(\d+)"')
_ROW_ADD_CLAIM_RE = re.compile(r'data-action="addClaim"', re.I)
_ROW_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2}:\d{2})?')
_SEED_DAY_RE = re.compile(r'(\d+)\s*天\s*(\d{1,2}):(\d{2}):(\d{2})')
_SEED_HMS_RE = re.compile(r'(?<![\d:-])(\d{1,2}):(\d{2}):(\d{2})(?![\d])')


def _parse_seed_seconds(text: str):
    """从一行文本里取「做种时长」（秒）；取不到返回 ``None``。

    先剔除完整日期时间（``YYYY-MM-DD HH:MM:SS``，含只到日期的形态），否则发布时间
    ``2026-09-17 23:17:41`` 里的 ``23:17:41`` 会被当成做种时长。剔除后仍有多段
    ``HH:MM:SS`` 时取**最后一段**（做种时间列总在发布时间列之后）。
    """
    clean = _ROW_DATE_RE.sub(' ', text or '')
    m = _SEED_DAY_RE.search(clean)
    if m:
        return int(m.group(1)) * 86400 + int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4))
    hits = _SEED_HMS_RE.findall(clean)
    if not hits:
        return None
    h, mi, s = hits[-1]
    return int(h) * 3600 + int(mi) * 60 + int(s)


def parse_user_torrent_rows(html_text: str) -> list:
    """解析「我的种子」列表（``getusertorrentlistajax.php``）的每一行。**纯函数**。

    每行返回::

        {'tid': '126817', 'title': ..., 'title_norm': ...,
         'pubdate': 'YYYY-MM-DD HH:MM:SS' | '',
         'size_bytes': int, 'seed_seconds': int | None,
         'claim_id': int | None, 'claim_state': 'open' | 'claimed' | 'none'}

    ``claim_state`` 语义（**站点为准，不做本地推断**）：

    - ``open``    —— 站点给了认领按钮且 ``data-claim_id="0"``，即「可认领、尚未认领」
    - ``claimed`` —— ``data-claim_id`` 非 0，即「已认领」
    - ``none``    —— 该行没有认领按钮（站点未开放认领：期限未到 / 不在认领范围）

    ``none`` 一律**不**当作可认领：站点没给入口就是不能领，别用本地「满 N 天」
    去补，那是 19.10.48 前「认领扫描恒 0」的另一半根因。
    """
    out = []
    if not html_text:
        return out
    for row in _ROW_TR_RE.findall(html_text):
        if 'details.php' not in row:
            continue
        m = _TITLE_ATTR_RE.search(row) or _TITLE_TEXT_RE.search(row)
        if not m:
            continue
        title = _html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        if not title:
            continue
        mid = _ROW_TID_RE.search(row) or _ROW_DETAIL_RE.search(row)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', row))
        md = _DT_RE.search(text)
        ms = _SIZE_RE.search(text)
        size_bytes = 0
        if ms:
            size_bytes = int(float(ms.group(1)) * _SIZE_UNIT.get(ms.group(2).upper(), 0))
        cids = _ROW_CLAIM_ID_RE.findall(row)
        if not cids:
            claim_state, claim_id = 'none', None
        else:
            non_zero = [c for c in cids if c != '0']
            claim_id = int(non_zero[0]) if non_zero else 0
            claim_state = 'claimed' if non_zero else 'open'
        out.append({
            'tid': mid.group(1) if mid else '',
            'title': title,
            'title_norm': _norm_title(title),
            'pubdate': f"{md.group(1)} {md.group(2)}" if md else '',
            'size_bytes': size_bytes,
            'seed_seconds': _parse_seed_seconds(text),
            'claim_id': claim_id,
            'claim_state': claim_state,
        })
    return out


def parse_seeding_list(html_text: str) -> list:
    """解析 ``getusertorrentlistajax.php?type=seeding`` 页面。

    返回 ``[{'title':..., 'title_norm':..., 'size_bytes':int, 'pubdate':'YYYY-MM-DD HH:MM:SS'}, ...]``。
    19.10.49 起由 :func:`parse_user_torrent_rows` 派生（单一解析实现），
    只保留「有发布时间」的行以维持原契约。
    """
    return [
        {k: r[k] for k in ('title', 'title_norm', 'size_bytes', 'pubdate')}
        for r in parse_user_torrent_rows(html_text)
        if r.get('pubdate')
    ]


def fetch_seeding_list(site: Any, userid: Any, timeout: int = 25) -> list:
    """抓取用户做种列表页，返回 ``parse_seeding_list`` 的结果。cookie/UA 取自站点配置。

    ★ 19.10.49：改为分页抓全（经 :func:`fetch_user_torrent_rows`）。原先只抓第一页，
    做种数 >100 的站（咖啡 160 / 高清时间 117）后半段永远「无发布时间」。
    """
    data = fetch_user_torrent_rows(site, userid, ttype="seeding", timeout=timeout)
    return [
        {k: r[k] for k in ('title', 'title_norm', 'size_bytes', 'pubdate')}
        for r in (data.get('rows') or [])
        if r.get('pubdate')
    ]


# ============================================================
# 官种（official）识别：抓站点「官方」标签页，收集官种标题
# ============================================================

_TORRENTNAME_SPLIT = re.compile(r'<table[^>]*class="torrentname"', re.I)
_OFFICIAL_TAG_RE = re.compile(
    r'href="\?tag_id=(\d+)"[^>]*>\s*<span[^>]*>\s*官方\s*</span>', re.I
)


def detect_official_tag_id(html_text: str):
    """从 torrents.php 的标签导航中找出「官方」标签的 tag_id（找不到返回 None）。"""
    if not html_text:
        return None
    m = _OFFICIAL_TAG_RE.search(html_text)
    return int(m.group(1)) if m else None


def parse_official_titles(html_text: str) -> list:
    """解析站点列表页，抽取每行种子标题（规范化）。纯函数。

    用于「官方」标签页：该页所列种子即官种。
    """
    out = []
    if not html_text:
        return out
    for blk in _TORRENTNAME_SPLIT.split(html_text)[1:]:
        seg = blk[:3000]
        m = re.search(r'title="([^"]+)"[^>]*href="details\.php\?id=\d+', seg)
        if not m:
            m = re.search(r'href="details\.php\?id=\d+[^"]*"[^>]*>(.*?)</a>', seg, re.S)
        if not m:
            continue
        title = _html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        title = re.sub(r"\s+", " ", title)
        if title:
            out.append(_norm_title(title))
    return out


def fetch_official_titles(site: Any, pages: int = 2, timeout: int = 25) -> list:
    """抓取站点「官方」标签页，返回官种标题（规范化）列表。

    先探测 tag_id（找不到回落 1，HDFans 官种 tag_id=1），再翻若干页收集标题。
    cookie/UA 直接取自站点配置。
    """
    domain = (getattr(site, "domain", "") or "").strip()
    base = (getattr(site, "url", "") or (f"https://{domain}" if domain else "")).rstrip("/")
    cookie = getattr(site, "cookie", None)
    ua = getattr(site, "ua", None) or _DEFAULT_UA
    if not base:
        return []
    try:
        from app.sdk.network import RequestUtils  # noqa: WPS433
    except Exception:
        return []

    try:
        req = _mk_client(site, base, "official", cookie=cookie, ua=ua, timeout=timeout)
    except Exception:
        return []

    def _get(url: str):
        try:
            resp = req.get_res(url)
        except Exception:
            return None
        if resp is None or not getattr(resp, "ok", False):
            try:
                resp and resp.close()
            except Exception:
                pass
            return None
        try:
            raw = resp.content
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("gbk", "ignore")
        finally:
            try:
                resp.close()
            except Exception:
                pass

    first = _get(f"{base}/torrents.php")
    tag_id = detect_official_tag_id(first) if first else None
    if tag_id is None:
        tag_id = 1

    seen = set()
    titles = []
    for page in range(max(int(pages), 1)):
        text = _get(f"{base}/torrents.php?tag_id={tag_id}&page={page}")
        if not text:
            if page == 0:
                continue
            break
        for t in parse_official_titles(text):
            if t and t not in seen:
                seen.add(t)
                titles.append(t)
    return titles
