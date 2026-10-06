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

# 默认框架（其余常量在文件后半段从规则包读取；这里先定，避免前向引用）
_NEXUS = "nexusphp"

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
    "cspt.top": {
        "hr": False,
        # ★ 主人 2026-09-28 06:08 确认：财神 **没有 H&R**。
        #   （之前 probe(myhr.php/rules.php) 抓不到条款 → 一直按未知保守 24h，现改为明确「无 H&R」。）
        "seed_hours": 0.0,
        "seed_cap": None,
        "note": "财神：**无 H&R**（主人确认）→ 不做 H&R 保种保护、不计欠 H&R。",
    },
    "cspt.cc": {
        "hr": False,
        "seed_hours": 0.0,
        "seed_cap": None,
        "note": "财神（备用域名 cspt.cc）：同 cspt.top，**无 H&R**。",
    },
    # ★ 11.7.0：逐种 H&R 站（无站点级规则，H&R 由发布者逐种开关）。
    #   站点级无法评估具体种子的标记 ⇒ 补源（站点级预筛）必须**保守排除**。
    "yemapt.org": {
        "hr": False,
        "seed_hours": None,
        "seed_cap": None,
        "per_torrent_hr": True,
        "note": "野马PT：**无站点级 H&R**；H&R 由**发布者逐种开关**（openApi `hrPunishEnable`），"
                "未达标会被罚（>10 个未达标种自动 ban），可去站点 HR 列表**花积分免罪**（罚分部分返还发布者）。"
                "依据：https://wiki.yemapt.org/torrent/hit-and-run （2026-10-05 Master 引原文）。"
                "⇒ 逐种标记站：补源禁用（保守排除）。",
    },
    "www.yemapt.org": {
        "hr": False,
        "seed_hours": None,
        "seed_cap": None,
        "per_torrent_hr": True,
        "note": "野马PT（别名域名 www.）：同 yemapt.org，无站点级 H&R、H&R 逐种开关 ⇒ 补源禁用。",
    },
    "kp.m-team.cc": {
        "hr": False,
        "seed_hours": None,
        "seed_cap": None,
        "note": "馒头：**无 H&R**（官方 wiki 规则页 0 处提及，2026-09-29 全站扫描确认）；"
                "**无做种数上限**。曾误记的「100」出自官方魔力公式参数 ``torrentMsSum``"
                "（= **计入魔力的做种数上限**，超过后时魔不再增长——是收益口径，不是禁令）。",
    },
    "m-team.cc": {
        "hr": False,
        "seed_hours": None,
        "seed_cap": None,
        "note": "馒头（备用域名）：同 kp.m-team.cc，无 H&R、无做种数上限。",
    },
}


# ============================================================
# 类型级规则（框架默认 + 按框架选解析器）★ 3.39.0
# ============================================================
# 分层原则（别越界）：
#   · **类型级只提供「怎么读」+ 兜底默认**，永远**不给站点阈值结论**——
#     同一框架下站点差异很大（财神明确无 H&R，而其它 NexusPHP 站有；学校 20h vs 红豆饭 24h）。
#   · 阈值结论（有无 H&R / 保种小时 / 上限 / 免费体积阈值）一律**站点级**（探测或手填）。
#   · 兜底默认里 ``hr/seed_hours/...`` 一律 **None = 未知**，交给既有「未知保守」逻辑，
#     因此**不改变任何既有行为**，只是把「未知」这层写明白、可看。
FRAMEWORK_RULE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "nexusphp": {
        "hr": None,
        "seed_hours": None,
        "seed_need_hours": None,
        "seed_cap": None,
        "probe_paths": ("myhr.php", "rules.php"),
        "note": "NexusPHP 家族：H&R/保种以站点 myhr.php / rules.php 为准；"
                "促销（体积自动免费/原盘/首集）见站点规则页。同类站结构一致，解析走同一套。",
    },
    "gazelle": {
        "hr": None,
        "seed_hours": None,
        "seed_need_hours": None,
        "seed_cap": None,
        "probe_paths": ("rules.php", "wiki.php"),
        "note": "Gazelle 家族：规则多为 wiki/rules 页面，关键词解析（低可信），"
                "探到明确 H&R 条款才落库。",
    },
    "unit3d": {
        "hr": None,
        "seed_hours": None,
        "seed_need_hours": None,
        "seed_cap": None,
        "probe_paths": ("rules", "pages/1"),
        "note": "UNIT3D 家族：规则在 /rules 等页面；H&R 与免费政策各站自定。",
    },
    "mteam": {
        "hr": None,
        "seed_hours": None,
        "seed_need_hours": None,
        "seed_cap": None,
        "probe_paths": ("rules.php",),
        "note": "M-Team 系：站点参数走 API，网页规则页信息少；阈值仍按站点判断。",
    },
    "custom": {
        "hr": None,
        "seed_hours": None,
        "seed_need_hours": None,
        "seed_cap": None,
        "probe_paths": ("rules.php", "myhr.php"),
        "note": "自有/魔改框架：结构不可假定，用通用关键词解析，宁可判「未知」。",
    },
    "unknown": {
        "hr": None,
        "seed_hours": None,
        "seed_need_hours": None,
        "seed_cap": None,
        "probe_paths": ("rules.php", "myhr.php"),
        "note": "框架未识别：只做通用关键词解析，不猜。",
    },
}


def framework_rule_defaults(framework: str) -> Dict[str, Any]:
    """取某框架的兜底默认（**优先规则包** conf/frameworks.yml；缺 → 代码内置表）。

    注意：值恒为 ``None``（未知）——阈值结论只能来自站点级探测/手填。
    """
    fw = str(framework or "").strip().lower() or "unknown"
    if _rp is not None:
        try:
            d = _rp.framework_defaults(fw)
            if isinstance(d, dict) and d:
                return d
        except Exception:  # noqa: BLE001
            pass
    return dict(FRAMEWORK_RULE_DEFAULTS.get(fw) or FRAMEWORK_RULE_DEFAULTS["unknown"])


def framework_note(framework: str) -> str:
    """该框架「怎么读」的说明（来自规则包，供界面展示）。"""
    if _rp is not None:
        try:
            note = _rp.framework_note(framework)
            if note:
                return note
        except Exception:  # noqa: BLE001
            pass
    fw = str(framework or "").strip().lower() or "unknown"
    return str((FRAMEWORK_RULE_DEFAULTS.get(fw) or {}).get("note") or "")


def framework_probe_paths(framework: str) -> Tuple[str, ...]:
    """该框架优先探测哪些页面（优先规则包；未知 → 通用两条）。"""
    if _rp is not None:
        try:
            paths = _rp.framework_probe_paths(framework)
            if paths:
                return tuple(paths)
        except Exception:  # noqa: BLE001
            pass
    d = framework_rule_defaults(framework)
    paths = d.get("probe_paths") or ("rules.php", "myhr.php")
    return tuple(str(p) for p in paths if str(p).strip())


def _fw_masks(fw: str):
    """按框架取（H&R / 排除 / 允许撤种 / 保种动作）四个正则；规则包缺项 → 兜底默认。"""
    fw = str(fw or "unknown").strip().lower() or "unknown"

    def _m(kind: str, fallback: str):
        return _rx(f"{fw}:{kind}", _tok_alt(fw, kind, fallback))

    return (
        _m("hr", _D_HR_TOKENS),
        _m("exclude", _D_EXCLUDE),
        _m("permit_withdraw", _D_PERMIT_WITHDRAW),
        _m("seed", _D_SEED_TOKENS),
    )


def _hours_in(seg: str, fw: str = "nexusphp"):
    """按**该框架**的时长写法解析小时数（天 → ×24）。"""
    h = _rx(f"{fw}:hours", str(_fire(fw, "hours") or _D_HOURS)).search(seg)
    if h:
        try:
            return float(h.group(1))
        except (TypeError, ValueError):
            return None
    d = _rx(f"{fw}:days", str(_fire(fw, "days") or _D_DAYS)).search(seg)
    if d:
        try:
            return float(d.group(1)) * 24.0
        except (TypeError, ValueError):
            return None
    return None


def parse_hr_generic(html_text: str, framework: str = "unknown") -> Dict[str, Any]:
    """**通用**（非 NexusPHP）H&R/保种解析：关键词 + 数字，**低可信**。

    保守纪律：
      · 只有「同一句里同时出现 H&R 关键词 + 明确时长」才判 ``hr=True``；
      · 其余一律 ``hr=None``（未知）——**绝不返回 False**（「没解析到」≠「没有 H&R」）。
    """
    text = str(html_text or "")
    if not text:
        return {"hr": None, "confidence": "low", "evidence": ""}
    fw = str(framework or "unknown").strip().lower() or "unknown"
    _hr_re, _ex_re, _pw_re, _seed_re = _fw_masks(fw)
    need_re = _rx(f"{fw}:need", _tok_alt(fw, "need", _D_RULE_NEED))
    out: Dict[str, Any] = {"hr": None, "confidence": "low", "evidence": ""}
    for seg in _segments(text):
        if not _hr_re.search(seg) or _ex_re.search(seg) or _pw_re.search(seg):
            continue
        hours = _hours_in(seg, fw)
        if hours is None or not _seed_re.search(seg):
            continue
        out["hr"] = True
        out["seed_hours"] = float(hours)
        out["evidence"] = seg[:120]
        out["confidence"] = "medium" if need_re.search(seg) else "low"
        break
    if out["hr"] is None:
        # 促销/上限是「有就采」的良性信息，与 H&R 无关，单独扫
        _fs = _free_size_pats(fw)
        _fs0 = _rx(f"{fw}:free_size0", _fs[0])
        _fs1 = _rx(f"{fw}:free_size1", _fs[1])
        for seg in _segments(text):
            if _ex_re.search(seg):
                continue
            m = _fs0.search(seg) or _fs1.search(seg)
            if m:
                try:
                    out["free_over_gb"] = float(m.group(1))
                except (TypeError, ValueError):
                    pass
    return out


def parser_for_framework(framework: str):
    """按框架取解析器：**nexus 引擎** 或 **通用引擎（绑定该框架的 token）**。

    解析器名叫什么由规则包决定（``frameworks.<fw>.parser``），代码里只认两类引擎。
    """
    fw = str(framework or "").strip().lower() or "unknown"
    name = "generic"
    if _rp is not None:
        try:
            name = _rp.framework_parser_name(fw)
        except Exception:  # noqa: BLE001
            name = "generic"
    if name == "nexus" or (fw == _NEXUS and name != "generic"):
        return parse_hr_from_html
    if name == "nexus":
        return parse_hr_from_html

    def _bound(html_text: str, _fw: str = fw) -> Dict[str, Any]:
        return parse_hr_generic(html_text, framework=_fw)

    return _bound


# ★ 3.41.0 定调（Master）：「**所有 H&R 规则都从收件箱的欢迎邮件进，外面的是假规则**」。
#    → 只有这两个来源的 H&R 结论算数；公开页/内置表推出来的 H&R 一律**作废**。
HR_TRUSTED_SOURCES = ("manual", "welcome")

# ============================================================
# 页面解析
# ============================================================
# ★ 3.40.0：**规则数据在 conf/frameworks.yml（rulepack），这里只留兜底默认值。**
#   加站类型 = 改 YAML；YAML 读不到 = 用下面这些默认值（行为与旧版一致）。
try:  # 离线单测/独立导入时可能没有包上下文
    from .. import rulepack as _rp
except Exception:  # noqa: BLE001
    _rp = None

# 兜底默认（YAML 缺失/缺项时使用；与 3.39.x 的常量完全一致）
_D_HOURS = r"(\d+(?:\.\d+)?)\s*(?:个)?\s*(?:小时|小時|個小時|hours?|hrs?|h\b)"
_D_DAYS = r"(\d+(?:\.\d+)?)\s*(?:天|日|days?)"
_D_CAP = r"(?:最多|上限|同时|做种数|seeding)[^\d]{0,12}(\d{1,4})\s*(?:个|個|条|種|种)?"
_D_EXCLUDE = (
    r"考核|达标|魔力|奖励|捐赠|申诉|免罪|警告|相册|邀请|邮箱|注册|每月|月做种|新人|"
    r"上传者|发布者|发种|候选|认领"
)
_D_HR_TOKENS = r"H\s*&\s*R|hit\s*[&a]nd\s*run|hit and run"
_D_SEED_TOKENS = r"做种|保种|挂种|seeding|seed"
_D_RULE_NEED = (
    r"必须|需|要求|不得少于|不少于|至少|达到|以内|之内|at least|must|minimum"
)
_D_PERMIT_WITHDRAW = r"可撤种|可以撤种|允许撤种|可撤除|即可撤|可删除种子|撤种条件不适用"

_D_FREE_SIZE0 = (
    r"(?:总体积|文件体积|体积|大小)[^。\n]{0,12}?大于\s*([\d.]+)\s*(?:G|GB|GiB)[^。\n]{0,30}免费"
)
_D_FREE_SIZE1 = r"大于\s*([\d.]+)\s*(?:G|GB|GiB)[^。\n]{0,20}自动[^。\n]{0,10}免费"
_D_FREE_ORIG = r"(?:Blu-?ray\s*Disk|HD\s*DVD|原盘)[^。\n]{0,40}(?:免费|free)"
_D_FREE_EP1 = r"每季的第?一集|第1集[^。\n]{0,20}免费|第一集[^。\n]{0,20}免费"


def _fire(fw: str, patch: str) -> Any:
    """按框架取「数据里的值」（字符串或列表）；空则返回默认。"""
    if _rp is None:
        return patch
    try:
        got = _rp.pattern(fw, patch)
    except Exception:  # noqa: BLE001
        got = None
    return got if got else patch


def _tok_alt(fw: str, kind: str, default: str) -> str:
    """按框架取 token 列表拼成正则；列表空 → 默认。"""
    if _rp is None:
        return default
    try:
        alt = _rp.alternation(_rp.tokens(fw, kind))
    except Exception:  # noqa: BLE001
        alt = ""
    return alt or default


def _rx(key: str, text: str) -> Any:
    if _rp is not None:
        try:
            return _rp.rx(key, text)
        except Exception:  # noqa: BLE001
            pass
    return re.compile(text, re.I)


# 小时数：中文/英文两种写法。允许「10 个 小时」「10小時」「10 hours」「10h」。
# ★ 3.41.2：用户栏统计 / 促销句**不是 H&R 规则**，先排除（踩过：用户栏 "H&R: [0/0/10]" 被判成有 H&R；
#   红豆饭「盒子做种的，72小时内只享受种子体积*3的上传量」是盒子促销）
_D_SEG_USERBAR = r"可连接|连接数|认领\s*[:：]|H\s*&\s*R\s*[:：]|种子区\s*[:：]|上传量\s*[:：]|下载量\s*[:：]"
_D_SEG_PROMO = r"盒子|上传速度|下载速度|[Kk]B/s|上传量|优惠|种子体积|免费区"
_SEG_REJECT_USERBAR_RE = _rx(f"{_NEXUS}:seg_reject_userbar", str(_fire(_NEXUS, "seg_reject_userbar") or _D_SEG_USERBAR))
_SEG_REJECT_PROMO_RE = _rx(f"{_NEXUS}:seg_reject_promo", str(_fire(_NEXUS, "seg_reject_promo") or _D_SEG_PROMO))

_HOURS_RE = _rx(f"{_NEXUS}:hours", str(_fire(_NEXUS, "hours") or _D_HOURS))
_DAYS_RE = _rx(f"{_NEXUS}:days", str(_fire(_NEXUS, "days")))
# 做种数上限
_CAP_RE = _rx(f"{_NEXUS}:cap", str(_fire(_NEXUS, "cap") or _D_CAP))


def _segments(text: str) -> List[str]:
    """把正文切成「句子/行」——解析规则必须**同句**命中，不然满页数字全中。"""
    parts = re.split(r"[\n\r。！？；;!?]+", text)
    return [p.strip() for p in parts if p.strip()]


# 明确**不属于** H&R 的上下文（考核/达标/魔力/上传者规则/发布者/捐赠 等）
_EXCLUDE_RE = _rx(f"{_NEXUS}:exclude", _tok_alt(_NEXUS, "exclude", _D_EXCLUDE))
# ★ 3.39.1/3.40.0：「可撤种 / 允许撤种」= 允许你停（撤种规定），**不是** H&R 义务。
#   （踩过：咖啡 rules.php「10集以下剧集需要保种10天以上可撤种」被判成 hr=True/240h/high）
_PERMIT_WITHDRAW_RE = _rx(
    f"{_NEXUS}:permit_withdraw", _tok_alt(_NEXUS, "permit_withdraw", _D_PERMIT_WITHDRAW)
)
# 「同一句里」的 H&R 关键词
_HR_TOKENS = _rx(f"{_NEXUS}:hr_tokens", _tok_alt(_NEXUS, "hr", _D_HR_TOKENS))
# 「同一句里」的保种动作词
_SEED_TOKENS = _rx(f"{_NEXUS}:seed_tokens", _tok_alt(_NEXUS, "seed", _D_SEED_TOKENS))
# 促销规则：「文件总体积大于20GB的种子将自动成为免费」/「原盘免费」/「每季第一集免费」
def _free_size_pats(fw: str) -> List[str]:
    """体积自动免费正则（YAML 可给单条字符串或列表）→ 至少两条（主/备）。"""
    got = _fire(fw, "free_size")
    if isinstance(got, str):
        pats = [got]
    elif isinstance(got, (list, tuple)):
        pats = [str(x) for x in got if str(x).strip()]
    else:
        pats = []
    if not pats:
        pats = [_D_FREE_SIZE0]
    while len(pats) < 2:
        pats.append(_D_FREE_SIZE1)
    return pats


_FREE_SIZE_PATS = _free_size_pats(_NEXUS)
_FREE_SIZE_RE = _rx(f"{_NEXUS}:free_size0", _FREE_SIZE_PATS[0])
_FREE_SIZE_RE2 = _rx(f"{_NEXUS}:free_size1", _FREE_SIZE_PATS[1])
_FREE_ORIG_RE = _rx(f"{_NEXUS}:free_original", str(_fire(_NEXUS, "free_original") or _D_FREE_ORIG))
_FREE_EP1_RE = _rx(f"{_NEXUS}:free_ep1", str(_fire(_NEXUS, "free_ep1") or _D_FREE_EP1))

# 「考核指标」句式：指标N：平均做种时间, 要求：30 Hour —— 这是**新人考核的达标线**，
# 不是 H&R 规则，必须分开存（否则会把考核要求误当成保种义务）。
_EXAM_RE = _rx(f"{_NEXUS}:exam", str(_fire(_NEXUS, "exam") or r"指标|平均做种时间|考核|达标线|要求\s*[:：]"))
# 明确的规则句式（最可信）：必须/需/要求/至少 ...
_RULE_NEED_RE = _rx(f"{_NEXUS}:rule_need", _tok_alt(_NEXUS, "need", _D_RULE_NEED))


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
    ev_hit = ""          # ★ 3.40.1：只凭关键词判「有 H&R」时用它当证据（否则界面上一片空）
    hits = 0
    for seg in _segments(text):
        if _SEG_REJECT_USERBAR_RE.search(seg) or _SEG_REJECT_PROMO_RE.search(seg):
            continue      # 用户栏统计 / 促销（盒子、上传速度、上传量）≠ H&R
        has_hr = bool(_HR_TOKENS.search(seg))
        has_seed = bool(_SEED_TOKENS.search(seg))
        if has_hr:
            hits += 1
            if not ev_hit:
                ev_hit = seg
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
        excluded = bool(_EXCLUDE_RE.search(seg)) or bool(_PERMIT_WITHDRAW_RE.search(seg))  # ★ 3.39.1 撤种规定≠H&R
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
    # ★ 3.41.2：判「有 H&R」要**硬证据** —— 明确 H&R 关键词，或「必须/至少 + 小时」的强义务句。
    #   仅「出现做种+小时」的弱句（如论坛功能说明）不算，避免 PTT「动态刷新」那类误判。
    if hits or best_high is not None:
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
    elif ev_hit:
        out["evidence"] = ev_hit[:300]
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
    # ★ 3.40.1：上限要排除「角色词/集数/考核」上下文
    #   （踩过：咖啡「10集以下剧集需要保种10天…」里的 10 被当成做种数上限 10）
    _cap_reject: Tuple[str, ...] = ("集",)
    if _rp is not None:
        try:
            _got = _rp.cap_reject(_NEXUS)
            if _got:
                _cap_reject = tuple(_got)
        except Exception:  # noqa: BLE001
            pass
    for m in _CAP_RE.finditer(text):
        try:
            v = int(m.group(1))
        except (TypeError, ValueError):
            continue
        _ls = text.rfind("\n", 0, m.start()) + 1
        _le = text.find("\n", m.end())
        if _le < 0:
            _le = len(text)
        _line = text[_ls:_le]
        if any(w and w in _line for w in _cap_reject):
            continue
        if 1 <= v <= 5000 and (cap is None or v < cap):
            cap = v
    if cap is not None:
        out["seed_cap"] = cap
    return out


def parse_hr_from_mail(body_text: str, framework: str = "nexusphp") -> Dict[str, Any]:
    """从**收件箱欢迎短讯正文**里解析 H&R（唯一自动来源）。

    正文通常是通用欢迎语 → 解析不到就 ``hr=None``（**保守**，不臆断成「无 H&R」）。
    """
    out = parse_hr_from_html(str(body_text or ""))
    if str(framework or "").strip().lower() not in ("", "nexusphp"):
        try:
            alt = parse_hr_generic(str(body_text or ""), framework=framework)
            if out.get("hr") is None and alt.get("hr") is not None:
                out = alt
        except Exception:  # noqa: BLE001
            pass
    ev = str(out.get("evidence") or "").strip()
    out["evidence"] = ("欢迎短讯: " + ev) if ev else "欢迎短讯（未提到 H&R）"
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
        framework_of: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._get = get_data
        self._save = save_data
        self._log = log
        # ★ 3.39.0：类型级兜底用——「域名 → 框架」查询（由插件注入 sitecap）
        self._fw_of = framework_of
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
        manual = str(cur.get("source") or "") in HR_TRUSTED_SOURCES   # 手填 / 欢迎短讯 = 权威
        conf = str((probed or {}).get("confidence") or "low")
        if not manual:
            for key in ("hr", "seed_cap", "evidence"):
                val = (probed or {}).get(key)
                if val is not None:
                    out[key] = val
            out["confidence"] = conf
            _psrc = str((probed or {}).get("source") or "")
            if _psrc:
                out["source"] = _psrc
            _phsrc = str((probed or {}).get("hr_src") or "")
            if _phsrc:
                out["hr_src"] = _phsrc
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
            # ★ 3.41.0：来源以「探测结果自带来源」为准（欢迎短讯链路 = ``welcome``），不要硬写 probe
            out["source"] = str((probed or {}).get("source") or "probe")
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
            for k, v in BUILTIN_RULES.items():
                if _same_domain(k, d):
                    b = v or {}
                    break
        if b:
            return self.put(d, dict(b, name=name or ""), source="builtin")
        # ★ 3.39.0：没内置记录 → 用**类型级兜底**补一条。
        #   注意：这里**只写「未知」**（阈值全 None）→ 行为与旧版完全一致（未知保守），
        #   好处是「这站按哪个框架、为什么还没探」在规则库里一眼可见。
        fw = "unknown"
        try:
            if self._fw_of:
                fw = str(self._fw_of(d) or "unknown").strip().lower() or "unknown"
        except Exception:  # noqa: BLE001
            fw = "unknown"
        dflt = framework_rule_defaults(fw)
        rec = {k: dflt.get(k) for k in ("hr", "seed_hours", "seed_need_hours", "seed_cap")}
        rec["framework"] = fw
        rec["note"] = dflt.get("note", "")
        return self.put(d, rec, source="framework")

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

    def retire_untrusted_hr(self) -> int:
        """★ 3.41.0：把**非权威来源**推出来的 H&R 结论作废（置 ``None`` = 未知）。

        「外面的是假规则」——公开页/内置表推出的 ``hr=True/False``/保种时长全部作废；
        生效时长随之回落到「未知 → 默认 24h」（保守：宁可多挂）。返回作废条数。
        """
        n = 0
        data = self.items()
        for dom, rec in list((data or {}).items()):
            r = dict(rec or {})
            src = str(r.get("source") or "")
            if src in HR_TRUSTED_SOURCES:
                continue
            if r.get("hr") is None and r.get("seed_hours") is None:
                continue
            if r.get("hr") is not None:
                r["hr"] = None
            if r.get("seed_hours") is not None:
                r["seed_hours_retired"] = r.get("seed_hours")
                r["seed_hours"] = None
            r["hr_src"] = "retired"
            note = str(r.get("note") or "").strip()
            tag = "H&R 来源非权威（外部页面），已作废"
            if tag not in note:
                r["note"] = (note + " / " + tag).strip(" /")
            data[dom] = r
            n += 1
        if n:
            self._write()
        return n

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

    def hr_of(self, domain: str) -> Optional[bool]:
        """该站 H&R 判定：``True`` 有 / ``False`` 无 / ``None`` 未知（未探明）。"""
        d = _norm_domain(domain)
        rec = dict(self.items().get(d) or {})
        if not rec:
            for k, v in self.items().items():
                if _same_domain(k, d):
                    rec = dict(v or {})
                    break
        if rec.get("hr") is not None and str(rec.get("source") or "") in HR_TRUSTED_SOURCES:
            return bool(rec.get("hr"))
        if "builtin" in HR_TRUSTED_SOURCES:      # ★ 3.41.0：默认**不信**内置表
            b = BUILTIN_RULES.get(d) or {}
            if not b:
                for k, v in BUILTIN_RULES.items():
                    if _same_domain(k, d):
                        b = v or {}
                        break
            if b.get("hr") is not None:
                return bool(b.get("hr"))
        return None

    def per_torrent_hr_of(self, domain: str) -> bool:
        """该站 H&R 是否为**逐种开关**（如 YemaPT ``hrPunishEnable``）。

        站点级无法评估具体种子的标记 ⇒ 需要「站点级预筛」的场景（补源）必须**保守排除**。
        取值：账本记录里的 ``per_torrent_hr``（若有）→ 内置表 → 默认 ``False``。
        """
        d = _norm_domain(domain)
        rec = dict(self.items().get(d) or {})
        if not rec:
            for k, v in self.items().items():
                if _same_domain(k, d):
                    rec = dict(v or {})
                    break
        if rec.get("per_torrent_hr") is not None:
            return bool(rec.get("per_torrent_hr"))
        b: Dict[str, Any] = {}
        for k, v in BUILTIN_RULES.items():
            if _same_domain(k, d):
                b = dict(v or {})
                break
        return bool(b.get("per_torrent_hr"))

    def seed_cap_of(self, domain: str) -> Optional[int]:
        """该站「同时在册做种数上限」（``None`` = 未知 / 不限）。

        None 时调用方会按「不限制」处理；已知有上限的站（如 馒头/m-team）返回具体值，
        供「静默保挂」等逻辑**保守跳过**，避免超过站点上限被罚。
        """
        d = _norm_domain(domain)
        rec = dict(self.items().get(d) or {})
        if not rec:
            for k, v in self.items().items():
                if _same_domain(k, d):
                    rec = dict(v or {})
                    break
        cap = rec.get("seed_cap")
        if cap is None:
            b = BUILTIN_RULES.get(d) or {}
            if not b:
                for k, v in BUILTIN_RULES.items():
                    if _same_domain(k, d):
                        b = v or {}
                        break
            cap = b.get("seed_cap")
        try:
            return int(cap) if cap is not None else None
        except (TypeError, ValueError):
            return None

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
        src = str(rec.get("source") or "")
        h = rec.get("seed_hours")
        if h is not None and src not in HR_TRUSTED_SOURCES:
            h = None            # ★ 3.41.0：非权威来源的保种时长不参与生效
        if h is not None and src == "probe" and str(rec.get("confidence") or "") != "high":
            h = None
        if h is not None:
            try:
                hv = float(h)
                if hv >= 0:
                    return hv, src or "store"
            except (TypeError, ValueError):
                pass
        if "builtin" in HR_TRUSTED_SOURCES:
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
