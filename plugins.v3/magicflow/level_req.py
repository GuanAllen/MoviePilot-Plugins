# -*- coding: utf-8 -*-
"""魔流 · 站点等级与升级要求（★ 19.11.18，④ 的第二半）。

抄 **PT-depiler**（https://github.com/pt-plugins/PT-depiler，master）的站点等级模型：
  * 每站一张 ``levelRequirements`` 表（从 PTD 站点定义原样搬运，见文件尾部数据段）；
  * 当前等级 → 等级 id 用「名字清洗后精确 → 包含」两级匹配（PTD guessUserLevelId 口径）；
  * 「距下一级还差什么」= PTD levelRequirementUnMet 的**算得出的子集**。

与 PTD 的两处刻意不同：
  1. **认不出当前等级就不给升级建议**（返回 ``None``）。PTD 会拿用户体量去倒推等级
     （guessUserLevelId 第三段），那是浏览器插件的展示口径；魔流这里等级是事实，
     推出来的值冒充事实违反铁律 6 —— UI 有「未知」的位子。
  2. **输入缺哪个字段就把它列进 ``unknown``**，不猜 0 顶上（PTD 里缺省按 0 比），
     宁可写「做种积分未知」也不给一个看起来算好了的差值。

数据维护：站点改了升级阈值 → 重跑 ``tools/ptd_extract_lr.py``（从 PTD 定义重抽）
或手工改文件尾部数据段。表只覆盖魔流已知站点；**没表的站一律不套默认表**（不猜）。
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

__all__ = [
    "clean_level_name",
    "guess_level_id",
    "api_level_name",
    "reqs_for_domain",
    "next_level_unmet",
    "LEVEL_REQS",
    "XIAOMLOVE_DEFAULT",
]


# ============================================================
# 名字清洗（PTD utils/level.ts cleanLevelName）
# ============================================================
def clean_level_name(name: Any) -> str:
    """去掉空格/下划线并小写 —— 「Power User」和「power_user」等价。"""
    return re.sub(r"[\s _]+", "", str(name or "")).lower()


# ============================================================
# 体积 / 时长（本文件自带，不外借 —— L0 纯函数零依赖）
# ============================================================
_UNITS = {
    "B": 1.0, "K": 1024.0, "KB": 1024.0, "KIB": 1024.0,
    "M": 1024.0 ** 2, "MB": 1024.0 ** 2, "MIB": 1024.0 ** 2,
    "G": 1024.0 ** 3, "GB": 1024.0 ** 3, "GIB": 1024.0 ** 3,
    "T": 1024.0 ** 4, "TB": 1024.0 ** 4, "TIB": 1024.0 ** 4,
    "P": 1024.0 ** 5, "PB": 1024.0 ** 5, "PIB": 1024.0 ** 5,
}


def _size_to_bytes(v: Any) -> Optional[float]:
    """'50GB' / '1.5 TB' / 123456 → 字节。认不出返回 ``None``（不猜 0）。"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v) if v >= 0 else None
    s = str(v or "").strip().replace(",", "").replace(" ", "")
    m = re.match(r"^([0-9]*\.?[0-9]+)([KMGTP]?I?B?)$", s, re.IGNORECASE)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except (TypeError, ValueError):  # pragma: no cover
        return None
    unit = (m.group(2) or "B").upper()
    mult = _UNITS.get(unit) or _UNITS.get(unit.rstrip("B")) or 1.0
    return val * mult


def _interval_seconds(v: Any) -> Optional[float]:
    """ISO 8601 时长（``P4W`` / ``P1Y2M`` / ``P100W``）→ 秒。认不出 ``None``。

    PTD 用 date-fns 的 interval 换算；这里只吃 NPHP 等级表实际出现的形态
    （年/月/周/天 —— 月按 30 天、年按 365 天，够用且不引入依赖）。
    """
    s = str(v or "").strip().upper()
    m = re.match(r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?$", s)
    if not m or not any(m.groups()):
        return None
    y, mo, w, d = (int(x or 0) for x in m.groups())
    return float(y * 365 + mo * 30 + w * 7 + d) * 86400.0


# ============================================================
# 当前等级 → 等级 id（PTD guessUserLevelId 的前两段，**不做体量倒推**）
# ============================================================
_GROUP_HINTS = (
    ("vip", ("vip", "贵宾", "honor", "荣誉")),
    ("manager", ("retiree", "养老", "退休", "uploader", "发布", "发种",
                 "helper", "助手", "助理", "seeder", "保种", "transferrer", "转载",
                 "forum", "版主", "moderator", "admin", "管理", "sys", "coder",
                 "开发", "staff", "主管")),
)


def _group_type(level_name: str) -> str:
    """等级名 → 组别（user/vip/manager），按 PTD 的关键词表认；认不出归 user。"""
    low = level_name.lower()
    for g, words in _GROUP_HINTS:
        if any(w in low for w in words):
            return g
    return "user"


def guess_level_id(level_name: Any, reqs: Optional[List[Dict[str, Any]]]) -> Optional[int]:
    """等级名 → 表里的等级 id。认不出 ``None``（不倒推）。

    匹配顺序（PTD 同款，加两级防误判）：
      ① 清洗后**全等**（「校长」不会命中「名誉校长」）
      ② 表名包含用户名（"(连长)Elite User" 表项命中页面上的 "Elite User"）——
         **长名优先**："(小学)Power User" 不许被短名 "user" 抢成 User
         （"user" 是 "poweruser" 的子串，按表序短名先命中就错了）
      ③ groupType 关键词（贵宾/版主…）→ 该组最小 id（表里没这一组 → PTD 兜底 100/200）
    """
    if not level_name or not reqs:
        return None
    cleaned = clean_level_name(level_name)
    if not cleaned:
        return None
    names = []
    for r in reqs:
        cand = [r.get("name")] + list(r.get("nameAka") or [])
        names.append((r, [clean_level_name(x) for x in cand if x]))
    for r, cleaned_cands in names:
        if any(c == cleaned for c in cleaned_cands):
            return _as_id(r.get("id"))
    # ② 包含匹配：全局取**最长**命中候选（同表短名是长名子串时长名赢）；
    #    等长按表序先到先得（表内 id 递增，小 id 优先）。
    best_len = -1
    best_r = None
    for r, cleaned_cands in names:
        for c in cleaned_cands:
            if c and cleaned and (c in cleaned or cleaned in c) and len(c) > best_len:
                best_len = len(c)
                best_r = r
    if best_r is not None:
        return _as_id(best_r.get("id"))
    g = _group_type(str(level_name))
    if g != "user":
        for r in reqs:
            if str(r.get("groupType") or "user") == g:
                return _as_id(r.get("id"))
        return 100 if g == "vip" else 200  # PTD MinVipLevelId / MinManagerLevelId
    return None


def _as_id(v: Any) -> Optional[int]:
    """宽松转 int，转不动返回 ``None``（等级 id 缺失时不冒充 0）。"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def api_level_name(level: Any, reqs: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """API 站返回的**数字等级 id** → 等级名（PTD yemapt/mteam 口径）。

    ``levelId``（站点私有编号，如馒头 VIP=10）优先，其次 ``id``。
    表里没有 → ``None``（数字不当名字展示）。
    """
    if level is None or level == "" or not reqs:
        return None
    key = str(level).strip()
    if key.endswith(".0"):
        key = key.removesuffix(".0")
    if not key:
        return None
    for r in reqs:
        if str(r.get("levelId") or "") == key:
            return str(r.get("name") or "") or None
    for r in reqs:
        if str(r.get("id") or "") == key:
            return str(r.get("name") or "") or None
    return None


def reqs_for_domain(domain: Any) -> Optional[List[Dict[str, Any]]]:
    """域名 → 升级表。没表的站返回 ``None``（**不套 xiaomlove 默认表**，不猜）。

    ``LEVEL_REQS[dom] is None`` 表示 PTD 站点定义显式引用 xiaomlove 默认表（如大青虫），
    这时候才用 ``XIAOMLOVE_DEFAULT``。
    """
    dom = str(domain or "").strip().lower()
    if dom.startswith("www."):
        dom = dom[4:]
    if dom in LEVEL_REQS:
        t = LEVEL_REQS[dom]
        return XIAOMLOVE_DEFAULT if t is None else t
    return None


# ============================================================
# 距下一级还差什么（PTD levelRequirementUnMet 的算得出子集）
# ============================================================
#: 升级要求里的字段 → 现况事实里的键（对不上的进 unknown）
_FACT_KEY = {
    "downloaded": "download",
    "trueDownloaded": "download",
    "uploaded": "upload",
    "trueUploaded": "upload",
    "seedingSize": "seeding_size",
    "seeding": "seeding",
    "seedingBonus": "seeding_bonus",
    "bonus": "bonus",
    "snatches": "snatches",
    "uploads": "uploads",
    "posts": "posts",
    "totalTraffic": "total_traffic",
}
#: 这些字段只在同名现况事实里查
_TIME_KEYS = ("interval", "seedingTime", "averageSeedingTime")
#: 「越大越好」的计数类（差值 = 要求 - 现况）
_CNT_KEYS = ("seedingBonus", "bonus", "seeding", "snatches", "uploads", "posts")


def next_level_unmet(
    facts: Dict[str, Any],
    reqs: Optional[List[Dict[str, Any]]],
    level_name: Any,
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """当前等级名 + 现况 → 下一级要求与差值。给不出 → ``None``（不猜）。

    ``facts`` 约定键（缺哪个，哪个进 ``unknown``）：
      ``upload`` / ``download`` 字节、``ratio`` 分享率、``ratio_inf`` 下载 0 → ∞、
      ``bonus`` 魔力、``seeding_bonus`` 做种积分、``seeding`` 做种数、
      ``join_time`` 入站时间（unix 秒或可解析串）、``seeding_size`` 做种体积。

    返回 ``{"id", "name", "req", "unmet", "unknown"}``：
      ``req`` 原样要求（前端想展示门槛用它）；``unmet`` 键与 ``req`` 同名、值是**还差的量**
      （体积字节 / 分享率 / 秒 / 计数）；``unknown`` 是算不出的输入字段名。
    """
    if not reqs or not level_name:
        return None
    cur_id = guess_level_id(level_name, reqs)
    if cur_id is None:
        return None
    user_reqs = [r for r in reqs if str(r.get("groupType") or "user") == "user"]
    nxt = None
    for r in user_reqs:  # 表内 id 递增
        rid = _as_id(r.get("id"))
        if rid is not None and rid > cur_id:
            nxt = r
            break
    if nxt is None:
        return None  # 已是最高用户级
    ts = float(now if now is not None else time.time())
    unmet: Dict[str, Any] = {}
    unknown: List[str] = []
    for key, val in nxt.items():
        if key in ("id", "name", "nameAka", "groupType", "isKept", "privilege",
                   "levelId", "alternative"):
            continue
        if key == "interval":
            sec = _interval_seconds(val)
            join = _to_ts(facts.get("join_time"))
            if sec is None:
                unknown.append(key)
            elif join is None:
                unknown.append(key)
            elif join + sec > ts:
                unmet[key] = round(join + sec - ts, 1)
            continue
        if key in ("ratio", "trueRatio"):
            if facts.get("ratio_inf"):
                continue  # 下载 0 → 分享率 ∞，任何门槛都过
            cur = _to_float(facts.get("ratio"))
            if cur is None:
                unknown.append(key)
                continue
            need = val
            if isinstance(need, (list, tuple)) and len(need) == 2:
                need = min(float(x) for x in need)  # 区间取下限（常见形态就是单值门槛）
            need_f = _to_float(need)
            if need_f is None:
                unknown.append(key)
            elif cur < need_f:
                unmet[key] = need_f
            continue
        fkey = _FACT_KEY.get(key)
        if fkey is None:
            unknown.append(key)  # 表里有、现况没有这个概念（工时/发帖…）
            continue
        cur = _to_float(facts.get(fkey))
        need = _size_to_bytes(val) if key not in _CNT_KEYS else _to_float(val)
        if cur is None or need is None:
            unknown.append(key)
            continue
        if key in _CNT_KEYS:
            if cur < need:
                unmet[key] = round(need - cur, 2)
        else:
            if cur < need:
                unmet[key] = round(need - cur, 1)
    return {
        "id": _as_id(nxt.get("id")),
        "name": str(nxt.get("name") or ""),
        "req": {k: v for k, v in nxt.items()
                if k not in ("id", "nameAka", "groupType", "isKept", "privilege",
                             "levelId", "alternative")},
        "unmet": unmet,
        "unknown": unknown,
    }


def _to_float(v: Any) -> Optional[float]:
    """宽松转 float，None / 空串 / 布尔 / 非数字一律 ``None``（缺输入要能和 0 区分）。"""
    if isinstance(v, bool) or v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_ts(v: Any) -> Optional[float]:
    """入站时间 → unix 秒。吃 float / 数字串 / ``YYYY-MM-DD[ HH:MM[:SS]]``。"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        pass
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?", s)
    if not m:
        return None
    import calendar
    y, mo, d, h, mi, sec = m.groups()
    return float(calendar.timegm((int(y), int(mo), int(d),
                                  int(h or 0), int(mi or 0), int(sec or 0), 0, 0, 0)))


# ============================================================
# 数据：LEVEL_REQS / XIAOMLOVE_DEFAULT
# —— 从 PT-depiler master 的 src/packages/site/definitions/*.ts 抽取，
#    见 tools/ptd_extract_lr.py（重抽）与文件头说明。
# ============================================================
LEVEL_REQS = {
    'btschool.club': [
        {'id': 1, 'name': 'User'},
        {'id': 2, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 2.0, 'seedingBonus': 40000},
        {'id': 3, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '100GB', 'ratio': 2.5, 'seedingBonus': 80000},
        {'id': 4, 'name': 'Crazy User', 'interval': 'P15W', 'downloaded': '300GB', 'ratio': 3.0, 'seedingBonus': 150000},
        {'id': 5, 'name': 'Insane User', 'interval': 'P25W', 'downloaded': '500GB', 'ratio': 3.5, 'seedingBonus': 250000},
        {'id': 6, 'name': 'Veteran User', 'interval': 'P40W', 'downloaded': '1TB', 'ratio': 4.0, 'seedingBonus': 400000},
        {'id': 7, 'name': 'Extreme User', 'isKept': True, 'interval': 'P60W', 'downloaded': '2TB', 'ratio': 4.5, 'seedingBonus': 600000},
        {'id': 8, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P80W', 'downloaded': '5TB', 'ratio': 5.0, 'seedingBonus': 800000},
        {'id': 9, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P100W', 'downloaded': '10TB', 'ratio': 5.5, 'seedingBonus': 1000000},
        {'id': 100, 'name': '贵宾(VIP)', 'groupType': 'vip'},
        {'id': 101, 'name': '其他', 'groupType': 'vip'},
        {'id': 200, 'name': '养老族(Retiree)', 'groupType': 'manager'},
        {'id': 201, 'name': '发布员(Uploader)', 'groupType': 'manager'},
        {'id': 202, 'name': '总版主(Moderator)', 'groupType': 'manager'},
        {'id': 203, 'name': '管理员(Administrator)', 'groupType': 'manager'},
        {'id': 204, 'name': '维护开发员(Sysop)', 'groupType': 'manager'},
        {'id': 205, 'name': '主管(Staff Leader)', 'groupType': 'manager'},
    ],
    'carpt.net': [
        {'id': 0, 'name': 'User'},
        {'id': 1, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '200GB', 'ratio': 2.0, 'seedingBonus': 40000},
        {'id': 2, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '500GB', 'ratio': 3.0, 'seedingBonus': 80000},
        {'id': 3, 'name': 'Crazy User', 'interval': 'P15W', 'downloaded': '1TB', 'ratio': 4.0, 'seedingBonus': 150000},
        {'id': 4, 'name': 'Insane User', 'interval': 'P25W', 'downloaded': '2TB', 'ratio': 5.0, 'seedingBonus': 250000},
        {'id': 5, 'name': 'Veteran User', 'interval': 'P40W', 'downloaded': '4TB', 'ratio': 6.0, 'seedingBonus': 400000},
        {'id': 6, 'name': 'Extreme User', 'isKept': True, 'interval': 'P60W', 'downloaded': '6TB', 'ratio': 7.0, 'seedingBonus': 600000},
        {'id': 7, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P80W', 'downloaded': '8TB', 'ratio': 8.0, 'seedingBonus': 800000},
        {'id': 8, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P100W', 'downloaded': '10TB', 'ratio': 9.0, 'seedingBonus': 1000000},
    ],
    'crabpt.vip': [
        {'id': 0, 'name': 'User'},
        {'id': 1, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05, 'seedingBonus': 60000},
        {'id': 2, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '120GB', 'ratio': 1.55, 'seedingBonus': 120000},
        {'id': 3, 'name': 'Crazy User', 'interval': 'P15W', 'downloaded': '300GB', 'ratio': 2.05, 'seedingBonus': 200000},
        {'id': 4, 'name': 'Insane User', 'interval': 'P25W', 'downloaded': '500GB', 'ratio': 2.55, 'seedingBonus': 400000},
        {'id': 5, 'name': 'Veteran User', 'isKept': True, 'interval': 'P40W', 'downloaded': '750GB', 'ratio': 3.05, 'seedingBonus': 600000},
        {'id': 6, 'name': 'Extreme User', 'isKept': True, 'interval': 'P60W', 'downloaded': '1TB', 'ratio': 3.55, 'seedingBonus': 800000},
        {'id': 7, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P80W', 'downloaded': '1.5TB', 'ratio': 4.05, 'seedingBonus': 1200000},
        {'id': 8, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P100W', 'downloaded': '3TB', 'ratio': 4.55, 'seedingBonus': 1800000},
    ],
    'cspt.top': [
        {'id': 0, 'name': 'User'},
        {'id': 1, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05, 'seedingBonus': 80000},
        {'id': 2, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '120GB', 'ratio': 1.55, 'seedingBonus': 160000},
        {'id': 3, 'name': 'Crazy User', 'interval': 'P15W', 'downloaded': '512GB', 'ratio': 2.05, 'seedingBonus': 300000},
        {'id': 4, 'name': 'Insane User', 'interval': 'P25W', 'downloaded': '1TB', 'ratio': 2.55, 'seedingBonus': 600000},
        {'id': 5, 'name': 'Veteran User', 'isKept': True, 'interval': 'P40W', 'downloaded': '2TB', 'ratio': 3.05, 'seedingBonus': 1000000},
        {'id': 6, 'name': 'Extreme User', 'isKept': True, 'interval': 'P60W', 'downloaded': '4TB', 'ratio': 3.55, 'seedingBonus': 1500000},
        {'id': 7, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P80W', 'downloaded': '8TB', 'ratio': 4.05, 'seedingBonus': 2200000},
        {'id': 8, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P100W', 'downloaded': '16TB', 'ratio': 4.55, 'seedingBonus': 3000000},
    ],
    # cyanbug.net：站点定义直接引用 xiaomlove 默认表
    'cyanbug.net': None,  # → XIAOMLOVE_DEFAULT
    'dstudio.me': [
        {'id': 1, 'name': 'Peasant'},
        {'id': 2, 'name': 'User'},
        {'id': 3, 'name': 'Power User', 'interval': 'P5W', 'downloaded': '50GB', 'ratio': 1.05, 'seedingBonus': 25000},
        {'id': 4, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '120GB', 'ratio': 1.55, 'seedingBonus': 60000},
        {'id': 5, 'name': 'Crazy User', 'interval': 'P15W', 'downloaded': '300GB', 'ratio': 2.05, 'seedingBonus': 120000},
        {'id': 6, 'name': 'Insane User', 'interval': 'P25W', 'downloaded': '500GB', 'ratio': 2.55, 'seedingBonus': 200000},
        {'id': 7, 'name': 'Veteran User', 'interval': 'P40W', 'downloaded': '750GB', 'ratio': 3.05, 'seedingBonus': 350000},
        {'id': 8, 'name': 'Extreme User', 'interval': 'P60W', 'downloaded': '1TB', 'ratio': 3.55, 'seedingBonus': 500000},
        {'id': 9, 'name': 'Ultimate User', 'interval': 'P80W', 'downloaded': '1.5TB', 'ratio': 4.05, 'seedingBonus': 700000},
        {'id': 10, 'name': 'Nexus Master', 'interval': 'P100W', 'downloaded': '3TB', 'ratio': 4.55, 'seedingBonus': 1000000},
        {'id': 100, 'name': '贵宾(VIP)', 'groupType': 'vip'},
        {'id': 200, 'name': '养老族(Retiree)', 'groupType': 'manager'},
        {'id': 201, 'name': '发布员(Uploader)', 'groupType': 'manager'},
        {'id': 202, 'name': '总版主(Moderator)', 'groupType': 'manager'},
        {'id': 203, 'name': '管理员(Administrator)', 'groupType': 'manager'},
        {'id': 204, 'name': '维护开发员(Sysop)', 'groupType': 'manager'},
        {'id': 205, 'name': '主管(Staff Leader)', 'groupType': 'manager'},
    ],
    'duckboobee.org': [
        {'id': 1, 'name': 'Peasant'},
        {'id': 2, 'name': 'User'},
        {'id': 3, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05},
        {'id': 4, 'name': 'Elite User', 'interval': 'P4W', 'downloaded': '120GB', 'ratio': 1.55},
        {'id': 5, 'name': 'Crazy User', 'interval': 'P8W', 'downloaded': '300GB', 'ratio': 2.05},
        {'id': 6, 'name': 'Insane User', 'interval': 'P15W', 'downloaded': '500GB', 'ratio': 2.55},
        {'id': 7, 'name': 'Veteran User', 'isKept': True, 'interval': 'P25W', 'downloaded': '1024GB', 'ratio': 3.05},
        {'id': 8, 'name': 'Extreme User', 'isKept': True, 'interval': 'P40W', 'downloaded': '1TB', 'ratio': 3.55},
        {'id': 9, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P60W', 'downloaded': '1.5TB', 'ratio': 4.05},
        {'id': 10, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P80W', 'downloaded': '4TB', 'ratio': 5.05},
        {'id': 100, 'name': '贵宾(VIP)', 'groupType': 'vip'},
        {'id': 200, 'name': '养老族(Retiree)', 'groupType': 'manager'},
        {'id': 201, 'name': '发布员(Uploader)', 'groupType': 'manager'},
        {'id': 202, 'name': '总版主(Moderator)', 'groupType': 'manager'},
        {'id': 203, 'name': '管理员(Administrator)', 'groupType': 'manager'},
        {'id': 204, 'name': '维护开发员(Sysop)', 'groupType': 'manager'},
        {'id': 205, 'name': '主管(Staff Leader)', 'groupType': 'manager'},
    ],
    'hdtime.org': [
        {'id': 1, 'name': 'User', 'nameAka': ['未烧']},
        {'id': 2, 'name': 'Power User', 'nameAka': ['感冒'], 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05, 'seedingBonus': 40000},
        {'id': 3, 'name': 'Elite User', 'nameAka': ['发热'], 'interval': 'P8W', 'downloaded': '150GB', 'ratio': 1.55, 'seedingBonus': 80000},
        {'id': 4, 'name': 'Crazy User', 'nameAka': ['低烧'], 'interval': 'P15W', 'downloaded': '500GB', 'ratio': 2.05, 'seedingBonus': 150000},
        {'id': 5, 'name': 'Insane User', 'nameAka': ['中烧'], 'interval': 'P25W', 'downloaded': '750GB', 'ratio': 2.55, 'seedingBonus': 250000},
        {'id': 6, 'name': 'Veteran User', 'nameAka': ['高烧'], 'isKept': True, 'interval': 'P40W', 'downloaded': '1.5TB', 'ratio': 3.05, 'seedingBonus': 400000},
        {'id': 7, 'name': 'Extreme User', 'nameAka': ['烧糊涂'], 'isKept': True, 'interval': 'P60W', 'downloaded': '3TB', 'ratio': 3.55, 'seedingBonus': 600000},
        {'id': 8, 'name': 'Ultimate User', 'nameAka': ['走火入魔'], 'isKept': True, 'interval': 'P80W', 'downloaded': '5TB', 'ratio': 4.05, 'seedingBonus': 800000},
        {'id': 9, 'name': 'HDtime Master', 'nameAka': ['骨灰'], 'isKept': True, 'interval': 'P100W', 'downloaded': '10TB', 'ratio': 4.55, 'seedingBonus': 1000000},
    ],
    'm-team.cc': [
        {'id': 1, 'name': 'User'},
        {'id': 2, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '200GB', 'ratio': 2},
        {'id': 3, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '400GB', 'ratio': 3},
        {'id': 4, 'name': 'Crazy User', 'interval': 'P12W', 'downloaded': '500GB', 'ratio': 4},
        {'id': 5, 'name': 'Insane User', 'interval': 'P16W', 'downloaded': '800GB', 'ratio': 5},
        {'id': 6, 'name': 'Veteran User', 'interval': 'P20W', 'downloaded': '1000GB', 'ratio': 6},
        {'id': 7, 'name': 'Extreme User', 'isKept': True, 'interval': 'P24W', 'downloaded': '2000GB', 'ratio': 7},
        {'id': 8, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P28W', 'downloaded': '2500GB', 'ratio': 8},
        {'id': 9, 'name': 'mTorrent Master', 'isKept': True, 'interval': 'P32W', 'downloaded': '3000GB', 'ratio': 9},
        {'id': 100, 'name': 'VIP', 'groupType': 'vip', 'levelId': '10'},
    ],
    'novahd.top': [
        {'id': 0, 'name': 'User'},
        {'id': 1, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05, 'seedingBonus': 30000},
        {'id': 2, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '120GB', 'ratio': 1.55, 'seedingBonus': 60000},
        {'id': 3, 'name': 'Crazy User', 'interval': 'P15W', 'downloaded': '300GB', 'ratio': 2.05, 'seedingBonus': 80000},
        {'id': 4, 'name': 'Insane User', 'interval': 'P25W', 'downloaded': '500GB', 'ratio': 2.55, 'seedingBonus': 120000},
        {'id': 5, 'name': 'Veteran User', 'isKept': True, 'interval': 'P40W', 'downloaded': '750GB', 'ratio': 3.05, 'seedingBonus': 160000},
        {'id': 6, 'name': 'Extreme User', 'isKept': True, 'interval': 'P60W', 'downloaded': '1TB', 'ratio': 3.55, 'seedingBonus': 200000},
        {'id': 7, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P80W', 'downloaded': '1.5TB', 'ratio': 4.05, 'seedingBonus': 250000},
        {'id': 8, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P100W', 'downloaded': '3TB', 'ratio': 4.55, 'seedingBonus': 300000},
    ],
    'ptcafe.club': [
        {'id': 1, 'name': 'User 咖啡新人'},
        {'id': 2, 'name': 'Power User 速溶小白', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05, 'seedingBonus': 40000},
        {'id': 3, 'name': 'Elite User 风味达人', 'interval': 'P8W', 'downloaded': '120GB', 'ratio': 1.55, 'seedingBonus': 80000},
        {'id': 4, 'name': 'Crazy User 资深玩家', 'interval': 'P15W', 'downloaded': '300GB', 'ratio': 2.05, 'seedingBonus': 150000},
        {'id': 5, 'name': 'Insane User 专业老饕', 'interval': 'P25W', 'downloaded': '500GB', 'ratio': 2.55, 'seedingBonus': 250000},
        {'id': 6, 'name': 'Veteran User 烘焙高手', 'isKept': True, 'interval': 'P40W', 'downloaded': '750GB', 'ratio': 3.05, 'seedingBonus': 400000},
        {'id': 7, 'name': 'Extreme User 精英玩家', 'isKept': True, 'interval': 'P60W', 'downloaded': '1TB', 'ratio': 3.55, 'seedingBonus': 600000},
        {'id': 8, 'name': 'Ultimate User 咖啡巨星', 'isKept': True, 'interval': 'P80W', 'downloaded': '1.5TB', 'ratio': 4.05, 'seedingBonus': 800000},
        {'id': 9, 'name': 'Nexus Master 咖啡王者', 'isKept': True, 'interval': 'P100W', 'downloaded': '3TB', 'ratio': 4.55, 'seedingBonus': 1000000},
    ],
    'pttime.org': [
        {'id': 0, 'name': 'Peasant', 'nameAka': ['婴儿']},
        {'id': 1, 'name': 'User', 'nameAka': ['幼儿园']},
        {'id': 2, 'name': 'Power User', 'nameAka': ['小学'], 'interval': 'P4W', 'downloaded': '512GB', 'ratio': 1.05},
        {'id': 3, 'name': 'Elite User', 'nameAka': ['初中'], 'interval': 'P8W', 'downloaded': '2048GB', 'ratio': 1.55},
        {'id': 4, 'name': 'Crazy User', 'nameAka': ['高中'], 'interval': 'P15W', 'downloaded': '4096GB', 'ratio': 2.05},
        {'id': 5, 'name': 'Insane User', 'nameAka': ['专科'], 'interval': 'P25W', 'downloaded': '8192GB', 'ratio': 2.55},
        {'id': 6, 'name': 'Veteran User', 'nameAka': ['本科'], 'interval': 'P52W', 'downloaded': '16384GB', 'ratio': 3.05},
        {'id': 7, 'name': 'Extreme User', 'nameAka': ['研究生'], 'interval': 'P80W', 'downloaded': '25000GB', 'ratio': 3.55},
        {'id': 8, 'name': 'Ultimate User', 'nameAka': ['博士生'], 'interval': 'P104W', 'downloaded': '45000GB', 'ratio': 4.05},
        {'id': 9, 'name': 'Nexus Master', 'nameAka': ['博士后'], 'interval': 'P130W', 'downloaded': '90000GB', 'ratio': 4.55},
    ],
    'soulvoice.club': [
        {'id': 1, 'name': 'Peasant'},
        {'id': 2, 'name': 'User'},
        {'id': 3, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05},
        {'id': 4, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '120GB', 'ratio': 1.55},
        {'id': 5, 'name': 'Crazy User', 'interval': 'P15W', 'downloaded': '300GB', 'ratio': 2.05},
        {'id': 6, 'name': 'Insane User', 'interval': 'P25W', 'downloaded': '500GB', 'ratio': 2.55},
        {'id': 7, 'name': 'Veteran User', 'isKept': True, 'interval': 'P40W', 'downloaded': '750GB', 'ratio': 3.05},
        {'id': 8, 'name': 'Extreme User', 'isKept': True, 'interval': 'P60W', 'downloaded': '1TB', 'ratio': 3.55},
        {'id': 9, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P80W', 'downloaded': '1.5TB', 'ratio': 4.05},
        {'id': 10, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P100W', 'downloaded': '3TB', 'ratio': 4.55},
    ],
    'uhddolby.com': [
        {'id': 1, 'name': 'User'},
        {'id': 2, 'name': 'Power User', 'interval': 'P2W', 'downloaded': '120GB', 'ratio': 2.0, 'seedingBonus': 60000},
        {'id': 3, 'name': '(连长)Elite User', 'interval': 'P4W', 'downloaded': '256GB', 'ratio': 2.5, 'seedingBonus': 120000},
        {'id': 4, 'name': 'Crazy User', 'interval': 'P8W', 'downloaded': '512GB', 'ratio': 3.0, 'seedingBonus': 240000},
        {'id': 5, 'name': 'Insane User', 'interval': 'P12W', 'downloaded': '768GB', 'ratio': 3.5, 'seedingBonus': 360000},
        {'id': 6, 'name': 'Veteran User', 'interval': 'P20W', 'downloaded': '1TB', 'ratio': 4.0, 'seedingBonus': 600000},
        {'id': 7, 'name': 'Extreme User', 'isKept': True, 'interval': 'P28W', 'downloaded': '2TB', 'ratio': 4.5, 'seedingBonus': 720000},
        {'id': 8, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P40W', 'downloaded': '4TB', 'ratio': 5.0, 'seedingBonus': 1200000},
        {'id': 9, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P56W', 'downloaded': '8TB', 'ratio': 5.5, 'seedingBonus': 1680000},
    ],
    'yemapt.org': [
        {'id': 0, 'name': '乱民', 'ratio': 0.3},
        {'id': 1, 'name': '小卒', 'ratio': 0.5},
        {'id': 2, 'name': '教谕', 'ratio': 0.6},
        {'id': 3, 'name': '登仕郎', 'downloaded': '100GB', 'ratio': 1},
        {'id': 4, 'name': '修职郎', 'interval': 'P4W', 'downloaded': '200GB', 'ratio': 2},
        {'id': 5, 'name': '文林郎', 'interval': 'P8W', 'downloaded': '400GB', 'ratio': 3},
        {'id': 6, 'name': '忠武校尉', 'interval': 'P12W', 'downloaded': '500GB', 'ratio': 4},
        {'id': 7, 'name': '承信将军', 'interval': 'P16W', 'downloaded': '800GB', 'ratio': 5},
        {'id': 8, 'name': '武毅将军', 'interval': 'P20W', 'downloaded': '1TB', 'ratio': 6},
        {'id': 9, 'name': '武节将军', 'isKept': True, 'interval': 'P24W', 'downloaded': '2TB', 'ratio': 7},
        {'id': 10, 'name': '显威将军', 'isKept': True, 'interval': 'P28W', 'downloaded': '2.5TB', 'ratio': 8},
        {'id': 11, 'name': '宣武将军', 'isKept': True, 'interval': 'P32W', 'downloaded': '3TB', 'ratio': 9},
    ],
    'zmpt.cc': [
        {'id': 0, 'name': 'User'},
        {'id': 1, 'name': '中级训练家(PU)', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05, 'seedingBonus': 30000},
        {'id': 2, 'name': '高级训练家(eu)', 'interval': 'P8W', 'downloaded': '120GB', 'ratio': 1.55, 'seedingBonus': 80000},
        {'id': 3, 'name': '精英训练家(CU)', 'interval': 'P16W', 'downloaded': '300GB', 'ratio': 2.05, 'seedingBonus': 150000},
        {'id': 4, 'name': '道馆训练家(IU)', 'interval': 'P28W', 'downloaded': '500GB', 'ratio': 2.55, 'seedingBonus': 250000},
        {'id': 5, 'name': '专家训练家(VU)', 'interval': 'P40W', 'downloaded': '750GB', 'ratio': 3.05, 'seedingBonus': 400000},
        {'id': 6, 'name': '冠军训练家(EU)', 'interval': 'P56W', 'downloaded': '1TB', 'ratio': 3.55, 'seedingBonus': 600000},
        {'id': 7, 'name': '大师训练家(UU)', 'interval': 'P76W', 'downloaded': '1.5TB', 'ratio': 4.05, 'seedingBonus': 900000},
        {'id': 8, 'name': '传说训练家(NM)', 'isKept': True, 'interval': 'P100W', 'downloaded': '3TB', 'ratio': 4.55, 'seedingBonus': 1500000},
    ],
}

#: NexusPHP（xiaomlove 主线）默认等级表；PTD 里没写 levelRequirements 的 NPHP 站
#: 通常就是这套（cyanbug 显式引用它）。**非 NPHP / 有自定义表的站不要套这套**。
XIAOMLOVE_DEFAULT = [
        {'id': 1, 'name': 'Peasant'},
        {'id': 2, 'name': 'User'},
        {'id': 3, 'name': 'Power User', 'interval': 'P4W', 'downloaded': '50GB', 'ratio': 1.05, 'seedingBonus': 40000},
        {'id': 4, 'name': 'Elite User', 'interval': 'P8W', 'downloaded': '120GB', 'ratio': 1.55, 'seedingBonus': 80000},
        {'id': 5, 'name': 'Crazy User', 'interval': 'P15W', 'downloaded': '300GB', 'ratio': 2.05, 'seedingBonus': 150000},
        {'id': 6, 'name': 'Insane User', 'interval': 'P25W', 'downloaded': '500GB', 'ratio': 2.55, 'seedingBonus': 250000},
        {'id': 7, 'name': 'Veteran User', 'isKept': True, 'interval': 'P40W', 'downloaded': '750GB', 'ratio': 3.05, 'seedingBonus': 400000},
        {'id': 8, 'name': 'Extreme User', 'isKept': True, 'interval': 'P60W', 'downloaded': '1024GB', 'ratio': 3.55, 'seedingBonus': 600000},
        {'id': 9, 'name': 'Ultimate User', 'isKept': True, 'interval': 'P80W', 'downloaded': '1536GB', 'ratio': 4.05, 'seedingBonus': 800000},
        {'id': 10, 'name': 'Nexus Master', 'isKept': True, 'interval': 'P100W', 'downloaded': '3072GB', 'ratio': 4.55, 'seedingBonus': 1000000},
        {'id': 100, 'name': 'VIP', 'nameAka': ['贵宾', '贵宾(VIP)'], 'groupType': 'vip'},
        {'id': 200, 'name': 'Retiree', 'nameAka': ['养老族', '养老族(Retiree)'], 'groupType': 'manager'},
        {'id': 201, 'name': 'Uploader', 'nameAka': ['发布员', '发布员(Uploader)'], 'groupType': 'manager'},
        {'id': 202, 'name': 'Moderator', 'nameAka': ['总版主', '总版主(Moderator)'], 'groupType': 'manager'},
        {'id': 203, 'name': 'Administrator', 'nameAka': ['管理员', '管理员(Administrator)'], 'groupType': 'manager'},
        {'id': 204, 'name': 'Sysop', 'nameAka': ['维护开发员', '维护开发员(Sysop)'], 'groupType': 'manager'},
        {'id': 205, 'name': 'Staff Leader', 'nameAka': ['主管', '主管(Staff Leader)'], 'groupType': 'manager'},
]
