"""魔流 · 标签模型（Tag Model）—— 命名 / 解析 / 常量 / 纯函数。

设计见 ``docs/PLAN-tags.md``（Master 2026-09-27 评审后冻结）。

本模块只保留**纯函数与常量**（命名、解析、身份/职务、重贴标签、资产判据等），
**不依赖插件其它部分**，可离线单测（见文件末尾 ``__main__``）。

★ 12.0.0：账本对象（旧 kv 标签账本）已整体迁往 ``ledger.py``（5 表后端），
  本模块不再有 kv 账本 / 键 / 快照。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

__all__ = [
    "PREFIX",
    "STATE_BRUSH",
    "STATE_BONUS",
    "STATE_SILENT",
    "STATE_RECOMMEND",
    "STATE_HR",
    "DUTY_STATES",
    "SUB_NEW",
    "SUB_RESOURCE",
    "SUB_PLAIN",
    "STATES",
    "SUBS",
    "SILENT_NEW_TIMEOUT",
    "LEASE_TTL",
    "MARK_REUSE",
    "MARK_HR",
    "RESCUE_TAG",
    "EXTERNAL_TAG",
    "NON_DOWNLOAD_TAGS",
    "tag_for",
    "parse_tag",
    "is_magicflow_tag",
    "identity_of",
    "duty_of",
    "is_reuse_copy",
    "is_external_candidate",
    "KEEP_FOREIGN_TAGS",
    "retag",
    "DEFAULT_SORT_RULES",
]

# ---------------------------------------------------------------- 常量

PREFIX = "魔流"

STATE_BRUSH = "刷流"
STATE_BONUS = "魔力"
STATE_SILENT = "静默"
STATE_RECOMMEND = "推荐"
STATE_HR = "保种"  # ★ 11.11.0：H&R 保种职务（归 __hr_host__ 伪任务；只由 _hr_obligation 派生，不可手动设）

SUB_NEW = "新"
SUB_RESOURCE = "资源"
SUB_PLAIN = "普通"

STATES = (STATE_BRUSH, STATE_BONUS, STATE_SILENT, STATE_RECOMMEND, STATE_HR)
# 职务轴（上班贴 / 下班摘）：辅种不单列职务 —— 它只给**身份**，之后由该站任务照常让它上班。
# 保种也是职务（__hr_host__ 的「上班」= 保挂 H&R），但**不可手动设**（set_tag_state 不含它）。
DUTY_STATES = (STATE_BRUSH, STATE_BONUS, STATE_HR)
SUBS = (SUB_NEW, SUB_RESOURCE, SUB_PLAIN)

# 只有「静默」有子类
STATES_WITH_SUB = (STATE_SILENT,)

# ★ 「库内资产」标记：MP 整理完会给种子打 已整理/辅种（transfer 链写的，不是我们写的），
#   同时文件已移到媒体库目录。这两个标签是**唯一可靠的库内证据**（本部署 MP 的
#   downloadhistory / transferhistory / downloadfiles 三张表都是 0 行，不能依赖）。
ASSET_TAGS = ("已整理", "辅种")

# ★ 「其他标签」白名单：MP 自己的标记（属我方系统）→ 清理时不摘。
#   Master 2026-09-29 23:41「减少其他 tag，确保所有种子的行为都在我们管控下」。
KEEP_FOREIGN_TAGS = ("MOVIEPILOT",)

SILENT_NEW_TIMEOUT = 24 * 3600.0    # 静默-新 超时自动归 静默-普通
LEASE_TTL = 600.0                   # 占用租约（秒），超时视为可抢占

# 状态 → 限速档位（KB/s 由插件配置提供；这里只分档）


def is_asset_tags(tags: Any) -> bool:
    """种子上是否有 MP 写的「已整理 / 辅种」标记。"""
    return any(str(x).strip() in ASSET_TAGS for x in (tags or []))


def is_library_asset(rec: Any) -> bool:
    """库内资产真值（★ 12.0.0）：资源库记 ``in_library``，或身份「资源」。

    旧判据 ``rec["asset"]`` 是 7.0.0 已退役的**幽灵字段**（``mf_seed`` 无该列、读写都不经它，恒空）；
    判定库内资产一律走本函数（唯一口径）。
    """
    r = rec or {}
    return bool(r.get("in_library")) or str(r.get("sub") or "").strip() == SUB_RESOURCE


def resource_of_hash(groups: Any, hash_string: str) -> str:
    """种子所属的资源 id（``ResourceLedgerStore.group_of``）；查不到 → ``""``。"""
    if groups is None:
        return ""
    try:
        return _clean(groups.group_of(hash_string))
    except Exception:  # noqa: BLE001
        return ""


def resource_is_asset(groups: Any, group_id: str) -> bool:
    """资源级「库内资产」真值：``mf_resource.in_library`` 或资源身份「资源」。"""
    gid = _clean(group_id)
    if not gid or groups is None:
        return False
    try:
        rec = dict(((groups.items() or {}).get(gid) or {}))
    except Exception:  # noqa: BLE001
        return False
    if _clean(rec.get("asset_recheck")) == "fail":
        return False                      # 推荐复核不达标（已降级）不再享受资产保护
    if bool((rec.get("library") or {}).get("in_library")):
        return True
    return _clean(rec.get("identity")) == SUB_RESOURCE


def resource_asset_hash(groups: Any, hash_string: str, rec: Any = None) -> bool:
    """★ 13.0.0（Master「辅种应该按资源的身份打标签」）：**副本跟随资源身份**。

    真值源 = 资源账本：同一份内容（同特征码/同数据）的多个种共享一条资源；只要该资源是
    库内资产（``in_library``）或身份「资源」，它的**每个副本**都按「资源」对待 ——
    打资源身份标签、**不参与静默池清理/删除**。

    只看种子自己的记录（``rec``）会漏掉副本：副本的 ``sub`` 往往还是「新」（它进池时
    资源还没入库，或它压根没进资源成员表），但它的资源早就是库内资产了
    —— 2026-10-07 凌晨误删 10 个他站辅种份就是这么来的。
    """
    if is_library_asset(rec):
        return True
    return resource_is_asset(groups, resource_of_hash(groups, hash_string))


def asset_member_hashes(groups: Any) -> Set[str]:
    """所有「库内资产」资源的成员 hash 集合（清理/删除路径的统一保护清单）。

    覆盖两类：① 资源库记 ``in_library``；② 资源身份「资源」（含刚推荐入库、还没落库记的）。
    """
    out: Set[str] = set()
    if groups is None:
        return out
    try:
        items = groups.items() or {}
    except Exception:  # noqa: BLE001
        return out
    for _gid, rec in items.items():
        try:
            _r = dict(rec or {})
            if _clean(_r.get("asset_recheck")) == "fail":
                continue                      # 推荐复核不达标（已降级）不再享受资产保护
            lib = bool((_r.get("library") or {}).get("in_library"))
            ident = _clean(_r.get("identity")) == SUB_RESOURCE
            if not (lib or ident):
                continue
            for h in (dict(rec or {}).get("members") or {}):
                hh = _clean(h).lower()
                if hh:
                    out.add(hh)
        except Exception:  # noqa: BLE001
            continue
    return out


# ---------------------------------------------------------------- 命名

def _clean(text: Any) -> str:
    return str(text or "").strip()


def tag_for(site: str, state: str, sub: str = "") -> str:
    """拼标签：``魔流-<站点>-<状态>[-<子类>]``。

    ``site`` 为空时退化成 ``魔流-<状态>``（无站点信息，尽量别用）。
    """
    site = _clean(site)
    state = _clean(state)
    sub = _clean(sub)
    parts = [PREFIX]
    if site:
        parts.append(site)
    parts.append(state or STATE_SILENT)
    if sub and state in STATES_WITH_SUB:
        parts.append(sub)
    return "-".join(parts)


# 站点短名表由插件启动时注入（避免本模块依赖插件配置）
_SITE_NAMES: List[str] = []


def set_site_names(names: Any) -> None:
    """注入已知站点短名（用于解析带连字符的站点名）。"""
    global _SITE_NAMES
    out: List[str] = []
    for n in names or []:
        s = _clean(n)
        if s and s not in out:
            out.append(s)
    _SITE_NAMES = out


def parse_tag(tag: str) -> Optional[Dict[str, str]]:
    """解析魔流标签 → ``{site, state, sub}``；不是魔流标签返回 ``None``。

    站点名可能自带连字符，因此优先用「已注入站点表」匹配，再退回按段猜测。
    """
    raw = _clean(tag)
    if not raw or not raw.startswith(PREFIX):
        return None
    body = raw[len(PREFIX):].lstrip("-")
    if not body:
        return None
    segs = [s for s in body.split("-") if s]
    if not segs:
        return None

    site = ""
    rest = segs
    # ① 站点表优先（最长匹配）
    for name in sorted(_SITE_NAMES, key=len, reverse=True):
        if body == name:
            site, rest = name, []
            break
        if body.startswith(name + "-"):
            site, rest = name, [s for s in body[len(name) + 1:].split("-") if s]
            break
    if not site:
        # ② 回退：状态词之前的部分当站点
        idx = None
        for i, s in enumerate(segs):
            if s in STATES:
                idx = i
                break
        if idx is None:
            return None
        # 最后一段是状态（推荐/刷流/魔力/静默），之前的都是站点
        site = "-".join(segs[:idx])
        rest = segs[idx:]
    if not rest:
        # 只有站点没有状态（老格式 ``魔流-财神``）→ 视为魔力的老标签
        return {"site": site, "state": "", "sub": ""}
    state = rest[0] if rest[0] in STATES else ""
    sub = rest[1] if len(rest) > 1 and rest[1] in SUBS else ""
    if not state:
        return {"site": site, "state": "", "sub": ""}
    return {"site": site, "state": state, "sub": sub}


def is_magicflow_tag(tag: str) -> bool:
    return _clean(tag).startswith(PREFIX)


# ★ 辅种/复用标记：**存量复用加进来的种**（含跨站辅种）打这个标。
#   它表示「这颗种是指向已有文件的复用种，可能停在 pausedDL 等校验」，不是「没下完的下载」，
#   因此**任何自动清理都不能删它**（Master 2026-09-28：「所有跨站辅种都是 pausedDL」）。
MARK_REUSE = "魔流-辅种"
# ★ H&R 统一管理标记（Master 2026-09-28 01:37：「tag 打上 h&r 统一管理
#   没到时间暂停强行拉起来」）：欠 H&R 的种统一打这个标 → 由插件统一保挂/结清。
MARK_HR = "魔流-H&R"
# ★ 11.11.1 死种补源副本标记：从「无 H&R 的他站」补下的同 Release 副本（区别于 复用辅种 MARK_REUSE）。
#   来源站被 rescue_source_blocked 保证 ``hr != False`` 一律禁用 → 副本自己**不涉及站点 H&R**。
RESCUE_TAG = "魔流-补源"
# ★ 11.11.1 外部来源标记：插件外（手动 / MP 下载器 / 订阅）加进来的种，已被归流纳管。
#   「预期标记」：表明这是已知纳管的外部来源，不是异常。只打标，不做别的处置。
EXTERNAL_TAG = "魔流-外部"

# ★ 「全局特殊标签」：不属于某站点某状态，重贴标签时必须保留（否则会打断其它子系统）
SPECIAL_TAGS = ("魔流-推荐", "魔流-跨站", MARK_REUSE, MARK_HR, RESCUE_TAG, EXTERNAL_TAG)

# ★ 11.11.1：复用/补源副本（指向已有文件、非真实下载）→ H&R 一律不判。
#   （跨站来源份 CROSSSEED_TAG 是真实下载，H&R 由 assets.py 资源账记，不在此列）
NON_DOWNLOAD_TAGS = (MARK_REUSE, RESCUE_TAG)


def is_reuse_copy(tags: Any) -> bool:
    """复用/补源副本（非真实下载）→ 不判 H&R（不继承资源的来源站 H&R 债）。"""
    return any(str(x).strip() in NON_DOWNLOAD_TAGS for x in (tags or []))


def is_external_candidate(tags: Any) -> bool:
    """★ 11.11.1「非插件加进来的种」判据（纯函数）：

    带 MP 下载器标记 ``MOVIEPILOT``（= 走 MP 下载接口/订阅加进来，非插件 add_torrent 路径）
    且已被归流纳管（有魔流标签）且尚未打 ``魔流-外部`` 标 → 应打「预期标记」识别其来源。
    """
    ts = [str(x).strip() for x in (tags or [])]
    if "MOVIEPILOT" not in ts:
        return False
    if EXTERNAL_TAG in ts:
        return False
    return any(is_magicflow_tag(x) for x in ts)


def identity_of(tags: Any) -> Tuple[str, str]:
    """取出种子的**身份**（静默态标签）→ ``(站点, 子类)``；没有则 ``("", "")``。

    ★ 5.0.0「身份/职务分离」：
    - **身份** = ``魔流-<站点>-静默-<新|资源|普通>`` —— 每个种永远带着，**上班/下班都不改**；
      只有分拣（判资源/普通）与推荐确认才会改它。
    - **职务** = ``魔流-<站点>-<刷流|魔力>`` —— 上班贴、下班摘。
    """
    for t in tags or []:
        p = parse_tag(t)
        if p and p.get("state") == STATE_SILENT and p.get("sub"):
            return _clean(p.get("site")), _clean(p.get("sub"))
    return "", ""


def duty_of(tags: Any) -> Tuple[str, str]:
    """取出种子的**职务**（刷流/魔力）→ ``(站点, 状态)``；没有职务则 ``("", "")``。"""
    for t in tags or []:
        p = parse_tag(t)
        if p and p.get("state") in DUTY_STATES:
            return _clean(p.get("site")), _clean(p.get("state"))
    return "", ""


def retag(
    tags: Any,
    *,
    site: str = "",
    state: str = "",
    sub: str = "",
    keep_foreign: bool = True,
    keep: Sequence[str] = SPECIAL_TAGS,
) -> List[str]:
    """按新状态重算标签集合 —— **身份与职务两条轴**（5.0.0）。

    - **身份轴**（``魔流-<站点>-静默-<子类>``）：**永久保留**。``sub`` 给定 → 换成新身份
      （站点取 ``site``，为空则沿用原身份站点）；``sub`` 为空 → 沿用原身份；都没有 → ``新``。
    - **职务轴**（``魔流-<站点>-<刷流|魔力>``）：``state`` 是职务时重贴；``state`` 为静默/空 → **摘掉**职务。
    - ``keep`` 里的特殊标签（推荐/跨站/辅种/H&R）原样保留；``keep_foreign`` → 非魔流标签保留。
    """
    keep_set = {_clean(x) for x in (keep or ())}
    out: List[str] = []
    ident_site, ident_sub = "", ""
    for t in tags or []:
        s = _clean(t)
        if not s:
            continue
        if s in keep_set:
            if s not in out:
                out.append(s)
            continue
        if is_magicflow_tag(s):
            p = parse_tag(s)
            if p and p.get("state") == STATE_SILENT and p.get("sub") and not ident_sub:
                ident_site, ident_sub = _clean(p.get("site")), _clean(p.get("sub"))
            continue  # 其它魔流标签（职务/老格式）丢弃，下面按新状态重贴
        if keep_foreign and s not in out:
            out.append(s)
    _site = _clean(site) or ident_site
    _sub = _clean(sub) or ident_sub or (SUB_NEW if (_clean(state) or _site) else "")
    if _sub:
        it = tag_for(_site, STATE_SILENT, _sub)
        if it not in out:
            out.append(it)
    _st = _clean(state)
    if _st in DUTY_STATES:
        dt = tag_for(_site, _st)
        if dt not in out:
            out.append(dt)
    elif _st == STATE_RECOMMEND and "魔流-推荐" not in out:
        out.append("魔流-推荐")
    return out


# ---------------------------------------------------------------- 分拣规则（默认值）

DEFAULT_SORT_RULES: List[Dict[str, Any]] = [
    {"type": "subscribe", "weight": 100, "enabled": True, "desc": "命中订阅"},
    {"type": "library_asset", "weight": 90, "enabled": True, "desc": "库内资产(已整理/辅种)"},
    {"type": "douban_rating", "min": 7.5, "weight": 70, "enabled": True, "desc": "豆瓣评分≥7.5"},
    {"type": "year", "min": 2000, "weight": 20, "enabled": False, "desc": "年份≥2000"},
    {"type": "site", "sites": [], "weight": 10, "enabled": False, "desc": "指定站点"},
    {"type": "category", "categories": [], "weight": 10, "enabled": False, "desc": "指定分类"},
]


# ---------------------------------------------------------------- 离线自测

if __name__ == "__main__":  # pragma: no cover
    set_site_names(["财神", "咖啡", "学校", "高清时间", "馒头"])
    assert tag_for("财神", STATE_SILENT, SUB_RESOURCE) == "魔流-财神-静默-资源"
    assert tag_for("高清时间", STATE_BRUSH) == "魔流-高清时间-刷流"
    assert parse_tag("魔流-高清时间-刷流") == {"site": "高清时间", "state": "刷流", "sub": ""}
    assert parse_tag("魔流-财神-静默-资源") == {"site": "财神", "state": "静默", "sub": "资源"}
    assert parse_tag("魔流-财神") == {"site": "财神", "state": "", "sub": ""}
    assert parse_tag("刷流-咖啡") is None
    assert retag(["已整理", "魔流-财神"], site="财神", state=STATE_SILENT, sub=SUB_PLAIN) == [
        "已整理", "魔流-财神-静默-普通"]
    # ★ 5.0.0 身份/职务两轴：上班只贴职务，身份不动；下班只摘职务
    assert retag(["魔流-财神-静默-资源"], site="财神", state=STATE_BRUSH) == [
        "魔流-财神-静默-资源", "魔流-财神-刷流"], "上班必须保住身份"
    assert retag(["魔流-财神-静默-资源", "魔流-财神-刷流"], site="财神", state=STATE_SILENT) == [
        "魔流-财神-静默-资源"], "下班只摘职务"
    assert retag(["魔流-财神-静默-普通", "魔流-财神-魔力", "魔流-H&R"], state=STATE_SILENT) == [
        "魔流-H&R", "魔流-财神-静默-普通"]
    assert identity_of(["魔流-财神-静默-资源", "魔流-财神-魔力"]) == ("财神", "资源")
    assert duty_of(["魔流-财神-静默-资源", "魔流-财神-魔力"]) == ("财神", "魔力")
    print("tags.py 命名/解析自测通过 ✓")
