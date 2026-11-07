"""魔流 · 标签编解码 —— 纯函数（命名 / 解析 / 身份·职务 / 重贴 / 资产判据 / 媒体格式）。

★ 19.10.27 从 ``tags.py`` 下沉：原先 1050 行文件里「无 host、不碰 app、可离线单测」的前半
（约 500 行），外加全部常量。带 ``host`` 的媒体加种编排仍留在 ``tags.py``，它 import 本模块。

装什么：
  · 常量：前缀 / 职务·身份词表 / 标记标签 / 媒体分类 / 站点短名表 / 沿用超时与租约；
  · 命名：``tag_for``（身份 + 职务拼一个标签）、``retag``（上班贴 / 下班只摘职务）；
  · 解析：``parse_tag``（标签 → site/state/sub）、``identity_of`` / ``duty_of``；
  · 判据：``is_magicflow_tag`` / ``is_managed_tag`` / ``needs_magicize`` / ``is_reuse_copy`` /
    ``is_external_candidate`` / ``is_asset_tags`` / ``is_library_asset`` /
    资源副本三件套 ``resource_of_hash`` / ``resource_is_asset`` / ``resource_asset_hash``；
  · 媒体格式（不含 IO）：``MEDIA_KINDS`` / ``media_kind_spec`` / ``fmt_iso_ts`` /
    ``is_freeleech`` / ``strip_media_prefix`` / ``is_music_line``。

★ 本模块是 **L0**：只 import 标准库，不碰 ``app.*``、不碰 ``host``、不调下载器/账本/缓存。
  没有 MoviePilot 也能跑：``python3 tagspec.py``（文件末尾有离线自测）。

⚠ ``_SITE_NAMES`` 与 ``set_site_names`` **必须都在本模块**：前者是可变 global，后者是
  **rebind**（``_SITE_NAMES = out``）而不是原地改。若 ``set_site_names`` 留在 ``tags.py``，
  启动注入会写 tags 的那份，而 ``parse_tag`` 读本模块这份空表 → 带连字符的站点名
  （``魔流-高清时间-刷流``）退化成「按状态词猜站点」→ **静默解析错，不报错、测试可能全绿**。
  因此 ``tags.py`` 只 re-export 本模块的 ``set_site_names``，**不得**自己再写一份。

设计见 ``docs/PLAN-tags.md``（Master 2026-09-27 评审后冻结）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

__all__ = [
    "PREFIX",
    "STATE_BRUSH",
    "STATE_BONUS",
    "STATE_SILENT",
    "STATE_RECOMMEND",
    "STATE_HR",
    "STATE_KEEP",
    "STATE_ONDEMAND",
    "STATE_MUSIC",
    "STATE_CLAIM",
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
    "is_managed_tag",
    "needs_magicize",
    "identity_of",
    "duty_of",
    "is_reuse_copy",
    "is_external_candidate",
    "KEEP_FOREIGN_TAGS",
    "retag",
    "DEFAULT_SORT_RULES",
    "MEDIA_KINDS",
    "media_kind_spec",
    "fmt_iso_ts",
    "is_freeleech",
    "strip_media_prefix",
]

# ---------------------------------------------------------------- 常量

PREFIX = "魔流"

STATE_BRUSH = "刷流"
STATE_BONUS = "魔力"
STATE_SILENT = "静默"
STATE_RECOMMEND = "推荐"
STATE_KEEP = "保种"  # ★ 19.12.38：手动保留职务（归 __keep__；人工点名长期做种，只能人工解除）
STATE_HR = "H&R"  # ★ 11.11.0/19.12.38：H&R 保种职务（归 __hr_host__；只由欠债派生，结清即释放）
#   ★ 19.12.38（用户指出「保种是 keep，H&R 有自己的标签啊」）：这两个职务此前共用
#   ``STATE_HR="保种"``，于是「保种」这个标签同时表示人工保留和欠 H&R，统计只能靠
#   ``taken_by`` 区分（漏一处就把 keep 的种算成「H&R 还欠着」）。现在拆开：
#     保种 → __keep__（标签 ``魔流-<站>-保种``）
#     H&R  → __hr_host__（标签 ``魔流-<站>-H&R``）
#   ``state`` 不是落库字段（``ledger._task_state`` 由 ``task_id`` 现推），所以拆开零迁移；
#   只有 qB 标签名要重贴，而线上 hr_host 名下此刻为 0 颗，实际零动作。
STATE_ONDEMAND = "点播"  # ★ 15.8.4：点播在途职务（归 __ondemand__ 伪任务；加种即挂、settle 摘）。
STATE_CLAIM = "认领"  # ★ 19.10.11：站点认领职务（归 __claim__ 宿主；**名单驱动**）。
#   与刷流/魔力同构（贴职务轴 + 账本占位 + 到期退出），差别只在「名单」来源：
#   刷流/魔力来自任务分派，认领来自 ``mf_claim`` 账本 st∈{ok,already}。
#   作用：账本 state=认领 ≠ 静默 → 天然免疫静默池的暂停闸/清理闸/审计，
#   不再依赖「静默池唯一例外 = 音乐下载中」那条补丁，也不再与 __claim__ 拉锯。
STATE_MUSIC = "音乐"  # ★ 19.9.0：音乐在途职务（归 __music__ 伪任务；加种即挂、下完/入库摘）。
#   作用同点播：账本 state=音乐 ≠ 静默 → 免疫静默池的暂停闸与清理闸（不再靠「progress<1 例外」打补丁）。
#   作用：账本 state≠静默 → 免疫静默池的暂停闸与清理闸（未下完不再被当「静默半成品」删）。不可手动设。

SUB_NEW = "新"
SUB_RESOURCE = "资源"
SUB_PLAIN = "普通"

STATES = (STATE_BRUSH, STATE_BONUS, STATE_SILENT, STATE_RECOMMEND, STATE_HR,
          STATE_KEEP, STATE_ONDEMAND, STATE_MUSIC, STATE_CLAIM)
# 职务轴（上班贴 / 下班摘）：辅种不单列职务 —— 它只给**身份**，之后由该站任务照常让它上班。
# 保种（__keep__）与 H&R（__hr_host__）是**两个**职务，都不可手动设（set_tag_state 不含它们）：
#   保种 = 人工点名长期做种，只由 action=hold/unhold 进出；
#   H&R  = 欠债派生，结清/规则不欠即释放。
# 点播（__ondemand__ 的在途职务）：只为了把「下没下完」的种**划出静默池**，同样不可手动设。
DUTY_STATES = (STATE_BRUSH, STATE_BONUS, STATE_HR, STATE_KEEP, STATE_ONDEMAND, STATE_MUSIC,
               STATE_CLAIM)
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


# ---------------------------------------------------------------------------
# ★ 15.8.0 音乐线（Master 2026-10-07：「音乐单独一条线，不与刷流抢」）
#   音乐种（qB 分类 = 「音乐」）**不进魔力/刷流任务**（不打任务标签、不参与任务清理与账本），
#   但仍走 PT 规则（H&R / 静默池 / 唯一删除闸门 / 站点报表）。
#   放在本模块：纯 stdlib → 离线单测（无 MoviePilot）也能加载。
# ---------------------------------------------------------------------------
MUSIC_CATEGORY = "音乐"
ONDEMAND_CATEGORY = "点播"

# 候选缓存有效期（秒）。★ 19.10.11：音乐与点播共用的**同一个**候选有效期 ——
# 人和 AI 是同一个挑选入口（对话框选种下单），候选过期时间本就不该有两套口径。
# 取 2h：候选要活过「先比体积、比做种、过一会儿再回来点」的人的决策窗口，
# 且底座是落盘缓存（跨 reload 存活），不再是「进程内存 reload 即清」的 30 分钟。
MEDIA_CAND_TTL = 7200


def is_music_line(torrent: Any) -> bool:
    """该种是否属于「音乐线」（qB 分类 = ``音乐``）。

    ★ 纯函数（不依赖 ``self``）——清理 / 纳管 / 任务种子集都要用；
    兼容 ``TorrentInfo`` 对象与 qB 原始 dict。
    """
    try:
        if isinstance(torrent, dict):
            return str(torrent.get("category") or "").strip() == MUSIC_CATEGORY
        if hasattr(torrent, "category"):
            return str(getattr(torrent, "category", "") or "").strip() == MUSIC_CATEGORY
    except Exception:  # noqa: BLE001
        return False
    return False


def parse_tag(tag: str) -> Optional[Dict[str, str]]:
    """解析魔流标签 → ``{site, state, sub}``；不是魔流标签返回 ``None``。

    站点名可能自带连字符，因此优先用「已注入站点表」匹配，再退回按段猜测。
    """
    raw = _clean(tag)
    if not raw or not raw.startswith(PREFIX):
        return None
    # ★ 19.12.38：``魔流-H&R`` 是**种子级标记**（``MARK_HR``，7.0.0 起已退役、老种可能残留），
    #   不是「站点为空 + 职务 H&R」。职务标签一定带站点：``魔流-<站>-H&R``。
    #   不加这条，``parse_tag("魔流-H&R")`` 会返回 ``{"site": "", "state": "H&R"}``，
    #   于是 ``duty_of(["魔流-H&R"])`` 返回 H&R —— 历史老标会被当成「正在挂 H&R」。
    if raw == MARK_HR:
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

# ★ 15.8.13：已知的「非身份」魔流标记（解析不出身份，但确实证明归我们管）。
_MARK_TAGS = frozenset(_clean(x) for x in SPECIAL_TAGS)


def is_managed_tag(tag: str) -> bool:
    """该 ``魔流-*`` 标签能否**证明「这颗种归魔流管」** —— 解析得出身份，或是已知魔流标记。

    ★ 15.8.13：解析不出、又不在标记表里的 ``魔流-`` 标签是**孤儿标签**。
    2026-10-10 实证：工作区临时脚本给 10 颗音乐种打了 ``魔流-手动``，于是
      * ``_magicize_scope`` 只按前缀看「已有魔流标签」→ 永远不接管（归流闸门被占位）；
      * ``traffic_audit`` 也只按前缀判 ``managed`` → 它们从不进「未知流量」名单，
        巡逻告警不响 ⇒ 永久孤儿（无账本行、无身份、无 H&R 账）。
    所以「归我们管」必须由**能认出来的标签**证明：孤儿标签既不该挡住归流接管，
    也不该让未知流量审计漏报（归流重贴标签时会把它丢弃 —— 见 ``retag`` / ``_magicize_plan``）。
    """
    s = _clean(tag)
    if not s.startswith(PREFIX):
        return False
    if parse_tag(s):
        return True
    return s in _MARK_TAGS


def needs_magicize(tags: Any) -> bool:
    """**归流判定**（纯函数）：该种是否该被归流接管 → 重贴成 ``魔流-<站>-静默-<子>``。

    - 一个**已知**魔流标签都没有 → 是（含「只有孤儿 ``魔流-`` 标签」与「标签为空」）；
    - 只有「无站点名的老式静默身份」（如 ``魔流-静默-普通``）→ 是（靠 tracker 补齐站点）；
    - 已有带站点的魔流标签、或只有 ``魔流-辅种/H&R/补源/外部/推荐/跨站`` 这类标记 → 否，不动。
    """
    parsed = [parse_tag(x) for x in (tags or []) if is_managed_tag(x)]
    if not parsed:
        return True
    _hassite = any(p and p.get("site") for p in parsed)
    _sitelss = any(
        p and not p.get("site") and p.get("state") == STATE_SILENT and p.get("sub")
        for p in parsed
    )
    return not (_hassite or not _sitelss)


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



# ---------------------------------------------------------------- 媒体通用（★ 19.10.11）
#
# 音乐（musicgrab）与点播（ondemand）是**同一条流水线**：搜 → 挑 → 下 → 挂职务 → 入库。
# 历史上两个模块各写了一份挂职务（各 60 行）、一份 ISO 格式化、一份免费判定 —— 差异其实
# 只有媒体 type。这里把差异收敛成一张 `MEDIA_KINDS`，流水线只此一套；
# 模块侧只留 `_music_assign` / `_od_assign` 薄委托（调用点与测试不动）。
#
# 为什么放本模块：`tags.py` 是纯函数/常量层，三个离线测试都真加载它（common.py 有一个
# 测试只给桩），且 `is_music_line` / `MUSIC_CATEGORY` 这类媒体判定本就在这。
# `duty_assign` 通过 `host` 协作对象干活（`_get_downloader` / `_tag_state` / …），
# 不 import 插件其它部分，离线可测。

#: 媒体类型表 —— 职务/日志/展示的 type 差异全在这。
#:   task_id / task_name 属任务域常量（真值源 `common.py`），由调用方带入，不在本表。
MEDIA_KINDS: Dict[str, Dict[str, str]] = {
    "music": {
        "state": STATE_MUSIC,
        "label": "音乐线",        # 日志前缀（原「音乐线:挂 __music__ …」）
        "hist_prefix": "音乐",    # journal 标题前缀（strip_media_prefix 用）
        "category": MUSIC_CATEGORY,
    },
    "ondemand": {
        "state": STATE_ONDEMAND,
        "label": "点播",
        "hist_prefix": "点播",
        "category": ONDEMAND_CATEGORY,
    },
}


def media_kind_spec(kind: Any) -> Dict[str, str]:
    """查媒体类型表；未知 type 抛 ``ValueError``（别静默兜底，免得悄悄挂错伪任务）。"""
    key = str(kind or "").strip().lower()
    spec = MEDIA_KINDS.get(key)
    if not spec:
        raise ValueError("未知媒体类型: %r（可选：%s）" % (kind, sorted(MEDIA_KINDS)))
    return spec


def fmt_iso_ts(ts: Any) -> Optional[str]:
    """裸 epoch 秒 → ISO8601（带本地时区）；缺/非法/``<=0`` → ``None``（留值不留空洞）。

    干净清单口径：时间一律 ISO8601 字符串（AI 免换算）。
    """
    try:
        v = float(ts or 0.0)
    except (TypeError, ValueError):
        return None
    if v <= 0.0:
        return None
    try:
        return (datetime.fromtimestamp(v, tz=timezone.utc).astimezone()
                .isoformat(timespec="seconds"))
    except (OverflowError, OSError, ValueError):
        return None


def is_freeleech(dv: Any) -> bool:
    """下载因子是否「免费」（``downloadvolumefactor <= 0``）。

    ★ 坑：不能写成 ``float(dv or 1) <= 0`` —— ``dv=0``（免费）会被 ``or`` 吃成 1。
    ``None``/异常 = 未知 → 按「不免费」处理（宁可把免费当收费记账，也不把收费当免费白嫖）。
    """
    try:
        v = 1.0 if dv is None else float(dv)
    except Exception:  # noqa: BLE001
        v = 1.0
    return v <= 0.0


def strip_media_prefix(title: Any, kind: Any) -> str:
    """历史行展示名：把 journal 的「``<媒体类型>`` xxx」前缀去掉。"""
    t = str(title or "").strip()
    try:
        prefix = str(media_kind_spec(kind).get("hist_prefix") or "")
    except ValueError:
        prefix = ""
    if prefix and t.startswith(prefix):
        t = t[len(prefix):].strip()
    return t


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
    print("tagspec.py 命名/解析自测通过 ✓")
