"""魔流 · 标签模型（Tag Model）与状态账本。

设计见 ``docs/PLAN-tags.md``（Master 2026-09-27 评审后冻结）。

三层：

1. **命名**：``魔流-<站点>-<状态>[-<子类>]``（如 ``魔流-财神-静默-资源``）
2. **状态账本** ``tag_state``：``hash -> {站点/状态/来源子类/占用者/租约/…}``
   —— 标签只是**表象**，账本才是**真相**（标签被别的插件或手滑改坏也能自愈）。
3. **文件组账本** ``tag_groups``：``group_id(文件特征码) -> {members: {hash: {站点…}}}``
   —— 同一批文件可能在 A/B/C/D 多站各有一个种。**摘成员只删种**，
   只有**最后一个成员**离开时才连文件一起清。

本模块**不依赖插件其它部分**，可离线单测（见文件末尾 ``__main__``）。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "PREFIX",
    "STATE_BRUSH",
    "STATE_BONUS",
    "STATE_SILENT",
    "STATE_RECOMMEND",
    "DUTY_STATES",
    "SUB_NEW",
    "SUB_RESOURCE",
    "SUB_PLAIN",
    "STATES",
    "SUBS",
    "STATE_KEY",
    "GROUPS_KEY",
    "SNAPSHOT_KEY",
    "SORT_RULES_KEY",
    "SILENT_NEW_TIMEOUT",
    "LEASE_TTL",
    "SNAPSHOT_KEEP",
    "state_tier",
    "tag_for",
    "parse_tag",
    "is_magicflow_tag",
    "identity_of",
    "duty_of",
    "KEEP_FOREIGN_TAGS",
    "retag",
    "TagStateStore",
    "FileGroupStore",
    "DEFAULT_SORT_RULES",
]

# ---------------------------------------------------------------- 常量

PREFIX = "魔流"

STATE_BRUSH = "刷流"
STATE_BONUS = "魔力"
STATE_SILENT = "静默"
STATE_RECOMMEND = "推荐"

SUB_NEW = "新"
SUB_RESOURCE = "资源"
SUB_PLAIN = "普通"

STATES = (STATE_BRUSH, STATE_BONUS, STATE_SILENT, STATE_RECOMMEND)
# 职务轴（上班贴 / 下班摘）：辅种不单列职务 —— 它只给**身份**，之后由该站任务照常让它上班。
DUTY_STATES = (STATE_BRUSH, STATE_BONUS)
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

STATE_KEY = "tag_state"
GROUPS_KEY = "tag_groups"
SNAPSHOT_KEY = "tag_state_snapshot"
SORT_RULES_KEY = "sort_rules"
LIB_PENDING_KEY = "tag_lib_pending"

SILENT_NEW_TIMEOUT = 24 * 3600.0    # 静默-新 超时自动归 静默-普通
LEASE_TTL = 600.0                   # 占用租约（秒），超时视为可抢占
SNAPSHOT_KEEP = 3                   # 快照滚动保留份数

# 状态 → 限速档位（KB/s 由插件配置提供；这里只分档）
_TIER = {
    STATE_BRUSH: "brush",
    STATE_BONUS: "seed",
    STATE_SILENT: "seed",
    STATE_RECOMMEND: "seed",
}


def is_asset_tags(tags: Any) -> bool:
    """种子上是否有 MP 写的「已整理 / 辅种」标记。"""
    return any(str(x).strip() in ASSET_TAGS for x in (tags or []))


def asset_origin_sub(tags: Any) -> str:
    """库内资产 → 静默-资源；否则 静默-新。"""
    return SUB_RESOURCE if is_asset_tags(tags) else SUB_NEW


def state_tier(state: str) -> str:
    """返回该状态使用的限速档：``brush``（刷流档）或 ``seed``（挂种档）。"""
    return _TIER.get(str(state or "").strip(), "seed")


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

# ★ 「全局特殊标签」：不属于某站点某状态，重贴标签时必须保留（否则会打断其它子系统）
SPECIAL_TAGS = ("魔流-推荐", "魔流-跨站", MARK_REUSE, MARK_HR)


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


# ---------------------------------------------------------------- 状态账本

class TagStateStore:
    """种子状态账本（真值源）。

    记录：``hash -> {site, state, sub, origin_state, origin_sub, taken_by,
    taken_at, lease_until, free, size_gb, title, group_id, approx, …}``
    """

    def __init__(
        self,
        get_data: Callable[[str], Any],
        save_data: Callable[..., Any],
        log: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._get_data = get_data
        self._save_data = save_data
        self._log = log

    # ---- 读写
    def items(self) -> Dict[str, Dict[str, Any]]:
        # 缓存 items() 返回接口状态（状态账本写入后会调 _invalidate 失效）
        cached = getattr(self, "_items_cache", None)
        if cached is not None:
            return cached
        try:
            data = self._get_data(STATE_KEY) or {}
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        out = {str(k).lower(): v for k, v in data.items() if isinstance(v, dict)}
        self._items_cache = out
        return out

    def _invalidate(self) -> None:
        try:
            self._items_cache = None
        except Exception:
            pass

    def _write(self, data: Dict[str, Any]) -> None:
        try:
            self._save_data(STATE_KEY, data)
            self._invalidate()
        except Exception as err:  # noqa: BLE001
            self._log and self._log(f"标签:状态账本写入失败:{err}", "error")

    def set_asset(self, hash_string: str, asset: bool, *, sub: str = "", origin_sub: str = "") -> bool:
        """固化「库内资产」标记（清理闸门读它，而不是每次去看标签）。

        ★ 5.0.0：库内资产 = **身份**「资源」 → 直接写 ``sub``（``origin_sub`` 为旧名，兼容保留）。
        """
        h = _clean(hash_string).lower()
        if not h:
            return False
        sub = _clean(sub) or _clean(origin_sub)
        data = self.items()
        rec = dict(data.get(h) or {})
        if not rec:
            return False
        if bool(rec.get("asset")) == bool(asset) and not sub:
            return False
        rec["asset"] = bool(asset)
        if sub:
            rec["sub"] = sub
        rec["updated"] = time.time()
        data[h] = rec
        self._write(data)
        return True

    def assets(self) -> List[str]:
        return [h for h, r in self.items().items() if r.get("asset")]

    def get(self, hash_string: str) -> Dict[str, Any]:
        return dict(self.items().get(_clean(hash_string).lower()) or {})

    def state_of(self, hash_string: str) -> Tuple[str, str]:
        rec = self.get(hash_string)
        return _clean(rec.get("state")), _clean(rec.get("sub"))

    def put(self, hash_string: str, patch: Dict[str, Any], *, now: Optional[float] = None) -> Dict[str, Any]:
        """写入/合并一条记录（``state`` = 职务，``sub`` = 身份；不再记 origin）。"""
        h = _clean(hash_string).lower()
        if not h:
            return {}
        data = self.items()
        rec = dict(data.get(h) or {})
        ts = float(now if now is not None else time.time())
        _old_sub = _clean(rec.get("sub"))
        new_state = _clean(patch.get("state", rec.get("state")))
        new_sub = _clean(patch.get("sub", rec.get("sub")))
        _state_given = bool(_clean(patch.get("state")))
        rec.update({k: v for k, v in patch.items() if v is not None})
        if new_state:
            rec["state"] = new_state
        if new_state in STATES_WITH_SUB:
            rec["sub"] = new_sub
        elif new_state in (STATE_BRUSH, STATE_BONUS) and not _state_given and "sub" in patch:
            # ★ 5.0.0 铁律：在岗（职务轴）期间**不接**「顺手改身份」的写
            #   （分拣/推荐只能改池内种子的身份；在岗的等回池再过站）
            if _old_sub:
                rec["sub"] = _old_sub
            else:
                rec.pop("sub", None)
        elif "sub" in patch and not patch.get("sub"):
            rec.pop("sub", None)
        rec.setdefault("created", ts)
        rec["updated"] = ts
        data[h] = rec
        self._write(data)
        return rec

    def put_many(self, patches: Dict[str, Dict[str, Any]], *, now: Optional[float] = None) -> int:
        """批量写入（一次落盘）。语义与 :meth:`put` 一致。"""
        ts = float(now if now is not None else time.time())
        data = self.items()
        n = 0
        for h, patch in (patches or {}).items():
            hh = _clean(h).lower()
            if not hh or not isinstance(patch, dict):
                continue
            rec = dict(data.get(hh) or {})
            _old_sub = _clean(rec.get("sub"))
            new_state = _clean(patch.get("state", rec.get("state")))
            new_sub = _clean(patch.get("sub", rec.get("sub")))
            _state_given = bool(_clean(patch.get("state")))
            rec.update({k: v for k, v in patch.items() if v is not None})
            if new_state:
                rec["state"] = new_state
            if new_state in STATES_WITH_SUB:
                rec["sub"] = new_sub
            elif new_state in (STATE_BRUSH, STATE_BONUS) and not _state_given and "sub" in patch:
                # ★ 在岗不动身份（同 put）
                if _old_sub:
                    rec["sub"] = _old_sub
                else:
                    rec.pop("sub", None)
            elif "sub" in patch and not patch.get("sub"):
                rec.pop("sub", None)
            rec.setdefault("created", ts)
            rec["updated"] = ts
            data[hh] = rec
            n += 1
        if n:
            self._write(data)
        return n

    def reconcile(self, live_hashes: Any, *, keep_miss: int = 3, min_live: int = 50) -> Dict[str, int]:
        """账本对账：连续 ``keep_miss`` 轮不在下载器里 → 销账（防僵尸记录）。

        ★ 安全阀：``live`` 少于 ``min_live`` 视为「快照异常」直接跳过，
        绝不因为一次抓取失败把账本清空。
        """
        try:
            live = {_clean(h).lower() for h in (live_hashes or []) if _clean(h)}
        except Exception:  # noqa: BLE001
            live = set()
        if len(live) < int(min_live):
            return {"skipped": 1, "live": len(live), "dropped": 0, "pending": 0}
        data = self.items()
        dropped = 0
        pending = 0
        for h, rec in list(data.items()):
            if h in live:
                if rec.get("miss"):
                    rec.pop("miss", None)
                continue
            miss = int(rec.get("miss") or 0) + 1
            if miss >= int(keep_miss):
                data.pop(h, None)
                dropped += 1
                try:
                    self._log and self._log(f"账本:销账僵尸记录 {h[:8]}（{miss} 轮未见）")
                except Exception:  # noqa: BLE001
                    pass
            else:
                rec["miss"] = miss
                pending += 1
        if dropped or pending:
            self._write(data)
        return {"live": len(live), "dropped": dropped, "pending": pending}

    def stale_count(self) -> int:
        """账本里「本轮未见」的待销账记录数（看板用）。"""
        try:
            return sum(1 for r in self.items().values() if r.get("miss"))
        except Exception:  # noqa: BLE001
            return 0

    def drop(self, hash_string: str) -> bool:
        h = _clean(hash_string).lower()
        data = dict(self.items())   # ★ 拷贝再改：直接改缓存会让快照与账本别名（5.0.0 修）
        if h not in data:
            return False
        data.pop(h, None)
        self._write(data)
        return True

    def clear(self, *, keep_observed: bool = False) -> int:
        """清空账本。``keep_observed=True`` 时保留带 ``observed`` 标记的记录。"""
        data = dict(self.items())   # ★ 同上：拷贝再改
        if not keep_observed:
            self._write({})
            return len(data)
        kept = {k: v for k, v in data.items() if v.get("observed")}
        self._write(kept)
        return len(data) - len(kept)

    # ---- 查询
    def hashes_by_state(self, state: str = "", sub: str = "", *, site: str = "") -> List[str]:
        state = _clean(state)
        sub = _clean(sub)
        site = _clean(site)
        out: List[str] = []
        for h, rec in self.items().items():
            if site and _clean(rec.get("site")) != site:
                continue
            if state and _clean(rec.get("state")) != state:
                continue
            if sub and _clean(rec.get("sub")) != sub:
                continue
            out.append(h)
        return out

    def stats(self) -> Dict[str, int]:
        """按 ``站点|状态[-子类]`` 计数（看板用）。"""
        out: Dict[str, int] = {}
        for rec in self.items().values():
            key = f"{_clean(rec.get('site')) or '-'}|{_clean(rec.get('state')) or '-'}"
            sub = _clean(rec.get("sub"))
            if sub:
                key += f"-{sub}"
            out[key] = out.get(key, 0) + 1
        return out

    def expire_new(self, *, now: Optional[float] = None, timeout: float = SILENT_NEW_TIMEOUT,
                   skip: Optional[Any] = None) -> List[str]:
        """``静默-新`` 超时未分拣 → 归 ``静默-普通``；返回被改动的 hash。

        ``skip``：这些 hash 不参与超时降级（例如 H&R 义务还没挂满，仍要留在「新」等分拣）。
        """
        ts = float(now if now is not None else time.time())
        _skip = {str(x).strip().lower() for x in (skip or [])}
        moved: List[str] = []
        for h, rec in self.items().items():
            if _skip and str(h).strip().lower() in _skip:
                continue
            if _clean(rec.get("state")) == STATE_SILENT and _clean(rec.get("sub")) == SUB_NEW:
                born = float(rec.get("created") or 0)
                if born and (ts - born) >= timeout:
                    self.put(h, {"sub": SUB_PLAIN, "reason": "静默-新超时自动归普通"}, now=ts)
                    moved.append(h)
        return moved

    # ---- 占用（并发安全：先写账本再改标签，带租约）
    def claim(
        self,
        hash_string: str,
        task_id: str,
        *,
        state: str,
        site: str = "",
        ttl: float = LEASE_TTL,
        now: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """占用一个静默种（贴**职务**：``静默-*`` → ``刷流``/``魔力``）。

        返回 ``(是否成功, 原因)``。已有**未过期**占用者时拒绝（刷流/魔力互不接管）。
        ★ 只写职务，**身份（``sub``）原样保留**。
        """
        h = _clean(hash_string).lower()
        if not h:
            return False, "空 hash"
        ts = float(now if now is not None else time.time())
        data = self.items()
        rec = dict(data.get(h) or {})
        cur_state = _clean(rec.get("state"))
        owner = _clean(rec.get("taken_by"))
        lease = float(rec.get("lease_until") or 0)
        if owner and owner != _clean(task_id) and lease > ts:
            return False, f"已被任务 {owner} 占用（租约到 {int(lease)}）"
        if owner and owner != _clean(task_id) and cur_state in (STATE_BRUSH, STATE_BONUS) and lease <= ts:
            # 租约过期的孤儿占用：允许抢占，但记一笔
            self._log and self._log(f"标签:抢占过期占用 {h[:8]}（原 {owner}）", "warning")
        if cur_state in (STATE_BRUSH, STATE_BONUS) and owner and owner != _clean(task_id):
            return False, f"状态已被占用：{cur_state}"
        # ★ 5.0.0：``state`` 只表达**职务**；``sub`` 是**身份** —— 占用不改写、不清空，
        #   也就没有「回退目标 origin」这个字段了（旧记录里残留的无害，可忽略）。
        rec.update({
            "state": state,
            "taken_by": _clean(task_id),
            "taken_at": ts,
            "lease_until": ts + float(ttl),
            "updated": ts,
        })
        if site:
            rec["site"] = _clean(site)
        rec.setdefault("created", ts)
        data[h] = rec
        self._write(data)
        return True, "ok"

    def release(self, hash_string: str, *, task_id: str = "", now: Optional[float] = None) -> Optional[str]:
        """下班：**只摘职务** —— 身份（``sub``）原样保留，返回回到的标签串。

        ★ 5.0.0：不再有「按 origin 退回」这一步 —— 上班前是资源/普通，下班还是资源/普通。
        只有账本里没有身份的老记录才兜底（库内资产 → 资源，其余 → 普通）。
        """
        h = _clean(hash_string).lower()
        data = self.items()
        rec = dict(data.get(h) or {})
        if not rec:
            return None
        owner = _clean(rec.get("taken_by"))
        if task_id and owner and owner != _clean(task_id):
            return None  # 不是本任务占用的，别乱放
        state = STATE_SILENT
        sub = _clean(rec.get("sub"))
        if not sub:
            sub = SUB_RESOURCE if bool(rec.get("asset")) else SUB_PLAIN
        rec.update({"state": state, "sub": sub, "updated": float(now if now is not None else time.time())})
        rec.pop("taken_by", None)
        rec.pop("taken_at", None)
        rec.pop("lease_until", None)
        rec.pop("origin_state", None)
        rec.pop("origin_sub", None)
        data[h] = rec
        self._write(data)
        return tag_for(_clean(rec.get("site")), state, sub)

    def renew(self, hashes: Any, *, task_id: str, ttl: float = LEASE_TTL, now: Optional[float] = None) -> int:
        """续租（任务还在跑但本轮没重新 claim）。"""
        ts = float(now if now is not None else time.time())
        n = 0
        for h in [_clean(x).lower() for x in (hashes or []) if _clean(x)]:
            rec = self.get(h)
            if _clean(rec.get("taken_by")) == _clean(task_id):
                self.put(h, {"lease_until": ts + float(ttl)}, now=ts)
                n += 1
        return n

    # ---- 快照 / 重建
    def snapshot(self, *, now: Optional[float] = None, keep: int = SNAPSHOT_KEEP) -> Dict[str, Any]:
        """落一份滚动快照（只保留最近 ``keep`` 份）。"""
        ts = float(now if now is not None else time.time())
        snaps = self.snapshots()
        snaps.append({"ts": ts, "count": len(self.items()),
                      "items": {k: dict(v) for k, v in self.items().items()}})
        snaps = snaps[-max(1, int(keep)):]
        try:
            self._save_data(SNAPSHOT_KEY, snaps)
        except Exception as err:  # noqa: BLE001
            self._log and self._log(f"标签:快照写入失败:{err}", "error")
        return {"ts": ts, "count": len(self.items())}

    def snapshots(self) -> List[Dict[str, Any]]:
        try:
            raw = self._get_data(SNAPSHOT_KEY) or []
        except Exception:  # noqa: BLE001
            raw = []
        return [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []

    def restore_latest(self) -> int:
        """用最近一份快照回滚（精确恢复）；返回恢复条数。"""
        snaps = self.snapshots()
        if not snaps:
            return 0
        items = snaps[-1].get("items") or {}
        if not isinstance(items, dict):
            return 0
        self._write(items)
        return len(items)

    def rebuild_from_tags(
        self,
        torrents: Any,
        *,
        state_of_tag: Optional[Callable[[str], Tuple[str, str]]] = None,
        now: Optional[float] = None,
    ) -> int:
        """账本丢失时的降级重建：从种子标签反推（**近似**，标记 ``approx=True``）。

        ``torrents``：``[{hash, tags, site, size_gb, title, state, progress, downloaded}]``
        """
        ts = float(now if now is not None else time.time())
        data = self.items()
        n = 0
        for t in torrents or []:
            h = _clean((t or {}).get("hash")).lower()
            if not h or h in data:
                continue
            site = _clean((t or {}).get("site"))
            state, sub = "", ""
            for tg in (t or {}).get("tags") or []:
                parsed = parse_tag(tg)
                if parsed and parsed.get("state"):
                    site = site or parsed.get("site", "")
                    state, sub = parsed["state"], parsed.get("sub", "")
                    break
                if parsed and parsed.get("site"):
                    site = site or parsed["site"]
            if not state and state_of_tag is not None:
                for tg in (t or {}).get("tags") or []:
                    st, sb = state_of_tag(_clean(tg))
                    if st:
                        state, sub = st, sb
                        break
            if not state:
                continue
            data[h] = {
                "site": site,
                "state": state,
                "sub": sub if state in STATES_WITH_SUB else (SUB_NEW if state else ""),
                "approx": True,
                "created": ts,
                "updated": ts,
                "size_gb": float((t or {}).get("size_gb") or 0),
                "title": _clean((t or {}).get("title")),
            }
            n += 1
        if n:
            self._write(data)
        return n


# ---------------------------------------------------------------- 文件组（多站引用计数）

class FileGroupStore:
    """★ 资源账本（Resource）：一份内容 = 一条资源，多站各挂一个种。

    Master 的模型（2026-09-27 20:38）：

    - **资源 : 种子 = 1 : N**，同一个资源可以有多个种子（多站/多版本）
    - 资源有 **来源站**（谁把它下回来的）—— 资源的 **H&R 账单挂在资源上**，不是种子上
    - 资源要**靠来源站的那个种子挂种**来结清 H&R（挂够时长 → 给资源结清账单）
    - 资源有 **库记**（是否已整理入库）
    - **只有「下完」的才有资源**；没下完的只有种子

    存储：``group_id -> {size_gb, files_shared, members:{hash:{site,downloader,added,
    downloaded,progress,state}}, source_site, source_hash,
    hr:{site,required_hours,need_hours,seeded_seconds,settled,settled_at,checked_at,by_hash},
    library:{in_library,first_at,media_id,path}, created, updated}``

    删除纪律（Master 18:54）：
    - 摘掉一个成员 → **只删该站的种**（``delete_files=False``）
    - 成员清零 → **连文件一起清**（``delete_files=True``）
    """

    def __init__(
        self,
        get_data: Callable[[str], Any],
        save_data: Callable[..., Any],
        log: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._get_data = get_data
        self._save_data = save_data
        self._log = log

    def items(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = self._get_data(GROUPS_KEY) or {}
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for gid, rec in data.items():
            if isinstance(rec, dict):
                members = rec.get("members")
                if not isinstance(members, dict):
                    rec = dict(rec)
                    rec["members"] = {}
                out[str(gid)] = rec
        return out

    def _write(self, data: Dict[str, Any]) -> None:
        try:
            self._save_data(GROUPS_KEY, data)
        except Exception as err:  # noqa: BLE001
            self._log and self._log(f"标签:文件组账本写入失败:{err}", "error")

    def group_of(self, hash_string: str) -> str:
        h = _clean(hash_string).lower()
        for gid, rec in self.items().items():
            if h in (rec.get("members") or {}):
                return gid
        return ""

    def group_with_fp(self, fp: str) -> str:
        """按特征码找资源组（辅种配对用）。"""
        _fp = _clean(fp)
        if not _fp:
            return ""
        for gid, rec in self.items().items():
            for m in (rec.get("members") or {}).values():
                if _clean((m or {}).get("fp")) == _fp:
                    return gid
        return ""

    def fp_index(self) -> Dict[str, Dict[str, Any]]:
        """``fp -> {hash, site, group_id}``（多站辅种速查表）。"""
        out: Dict[str, Dict[str, Any]] = {}
        for gid, rec in self.items().items():
            for h, m in (rec.get("members") or {}).items():
                fp = _clean((m or {}).get("fp"))
                if fp and fp not in out:
                    out[fp] = {"hash": h, "site": (m or {}).get("site") or "",
                               "group_id": gid, "members": len(rec.get("members") or {})}
        return out

    def members(self, group_id: str) -> Dict[str, Dict[str, Any]]:
        return dict((self.items().get(_clean(group_id)) or {}).get("members") or {})

    def add_member(
        self,
        group_id: str,
        hash_string: str,
        *,
        site: str = "",
        downloader: str = "",
        size_gb: float = 0.0,
        files_shared: Optional[bool] = None,
        downloaded: bool = True,
        progress: float = 1.0,
        state: str = "",
        fp: str = "",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        gid = _clean(group_id)
        h = _clean(hash_string).lower()
        if not gid or not h:
            return {}
        ts = float(now if now is not None else time.time())
        data = self.items()
        rec = dict(data.get(gid) or {"members": {}})
        members = dict(rec.get("members") or {})
        # ★ 只有「下完」的种才建立资源/成为资源成员（没下完的只有种子，没有资源）
        if not downloaded and not members:
            return {"group_id": gid, "members": 0, "skipped": "not_downloaded"}
        prev = dict(members.get(h) or {})
        members[h] = {"site": _clean(site), "downloader": _clean(downloader), "added": prev.get("added") or ts,
                      "downloaded": bool(downloaded), "progress": round(float(progress or 0), 4)}
        if state:
            members[h]["state"] = _clean(state)
        _fp = _clean(fp) or _clean(prev.get("fp"))
        if _fp:
            members[h]["fp"] = _fp
        # 资源级的「来源站」= 真正把它下回来的那个站（H&R 义务所在）
        if downloaded and not _clean(rec.get("source_site")):
            rec["source_site"] = _clean(site)
            rec["source_hash"] = h
        rec["members"] = members
        # ★ 同一 hash 只能属于一个资源：从其它组里摘掉（fp 计算出来后从「关键词组」搬进「特征码组」）
        for other_gid in [k for k in data if k != gid and h in (data[k].get("members") or {})]:
            orec = dict(data.get(other_gid) or {})
            omembers = dict(orec.get("members") or {})
            omembers.pop(h, None)
            if omembers:
                orec["members"] = omembers
                orec["files_shared"] = True
                orec["updated"] = ts
                data[other_gid] = orec
            else:
                data.pop(other_gid, None)
        if size_gb:
            rec["size_gb"] = float(size_gb)
        rec["files_shared"] = bool(len(members) > 1 if files_shared is None else files_shared)
        rec.setdefault("created", ts)
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return {"group_id": gid, "members": len(members)}

    # ---------------------------------------------------------------- 资源级：来源站 / H&R / 库记
    def set_hr(
        self,
        group_id: str,
        *,
        site: str = "",
        required_hours: float = 0.0,
        need_hours: float = 0.0,
        by_hash: str = "",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """挂/更新资源上的 H&R 账单（义务靠来源站那个种子挂种结清）。"""
        gid = _clean(group_id)
        data = self.items()
        rec = dict(data.get(gid) or {})
        if not gid or not rec:
            return {}
        ts = float(now if now is not None else time.time())
        hr = dict(rec.get("hr") or {})
        hr.update({
            "site": _clean(site) or hr.get("site", ""),
            "required_hours": float(required_hours or hr.get("required_hours") or 0.0),
            "need_hours": float(need_hours or hr.get("need_hours") or 0.0),
            "by_hash": _clean(by_hash) or hr.get("by_hash", ""),
            "checked_at": ts,
        })
        hr.setdefault("settled", False)
        rec["hr"] = hr
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return hr

    def note_hr_progress(
        self,
        group_id: str,
        *,
        seeded_seconds: float = 0.0,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """记录来源种挂种进度；挂够要求 → **给资源结清 H&R 账单**。"""
        gid = _clean(group_id)
        data = self.items()
        rec = dict(data.get(gid) or {})
        hr = dict(rec.get("hr") or {})
        if not gid or not rec or not hr:
            return {}
        ts = float(now if now is not None else time.time())
        seeded = float(seeded_seconds or 0.0)
        hr["seeded_seconds"] = round(seeded, 1)
        hr["checked_at"] = ts
        need = max(float(hr.get("required_hours") or 0.0), float(hr.get("need_hours") or 0.0))
        if not hr.get("settled") and need > 0 and seeded >= need * 3600.0:
            hr["settled"] = True
            hr["settled_at"] = ts
        rec["hr"] = hr
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return hr

    def set_library(
        self,
        group_id: str,
        in_library: bool,
        *,
        media_id: str = "",
        path: str = "",
        now: Optional[float] = None,
    ) -> bool:
        """资源级「库记」：这份内容是否已整理入库。"""
        gid = _clean(group_id)
        data = self.items()
        rec = dict(data.get(gid) or {})
        if not gid or not rec:
            return False
        ts = float(now if now is not None else time.time())
        lib = dict(rec.get("library") or {})
        if bool(lib.get("in_library")) == bool(in_library) and not media_id and not path:
            return False
        lib["in_library"] = bool(in_library)
        if in_library:
            lib.setdefault("first_at", ts)
        if media_id:
            lib["media_id"] = str(media_id)
        if path:
            lib["path"] = str(path)
        lib["updated"] = ts
        rec["library"] = lib
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return True

    # ------------------------------------------------------------ 资源级：身份
    #   Master 2026-09-30：**资源表(资源id, 身份) + 种子表(资源id, 站点id, 身份)**。
    #   资源身份 = 已认证（入库 / 推荐过）→ 「资源」；否则「普通」。
    #   种子身份**继承**资源身份：一资源变「资源」，旗下各站种子一起变（不用各站重算）。
    def identity(self, group_id: str) -> str:
        """资源身份：``资源`` / ``普通``（无此资源返回空串）。"""
        rec = self.items().get(_clean(group_id)) or {}
        if not rec:
            return ""
        ident = _clean(rec.get("identity"))
        if ident in (SUB_RESOURCE, SUB_PLAIN):
            return ident
        if bool((rec.get("library") or {}).get("in_library")):
            return SUB_RESOURCE
        return SUB_PLAIN

    def identity_of_hash(self, hash_string: str) -> str:
        """该种子所属**资源**的身份（种子身份应跟它走）。"""
        h = _clean(hash_string).lower()
        gid = self.group_of(h) if h else ""
        return self.identity(gid) if gid else ""

    def set_identity(self, group_id: str, identity: str, *, by: str = "",
                     now: Optional[float] = None) -> bool:
        """写资源身份（``资源``/``普通``）。"""
        gid = _clean(group_id)
        ident = _clean(identity)
        if not gid or ident not in (SUB_RESOURCE, SUB_PLAIN):
            return False
        data = self.items()
        rec = dict(data.get(gid) or {})
        if not rec:
            return False
        if _clean(rec.get("identity")) == ident:
            return False
        ts = float(now if now is not None else time.time())
        rec["identity"] = ident
        rec["identity_by"] = _clean(by)
        rec["identity_at"] = ts
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return True

    def queue_library(
        self,
        hash_string: str,
        *,
        path: str = "",
        media_id: str = "",
        now: Optional[float] = None,
    ) -> str:
        """整理完成事件到达时登记「库记」。

        - 该 hash 已在账本里 → 直接写所属资源的 ``library``，返回 group_id；
        - 还没纳管（事件早于我们的扫描）→ 记进**待办**，等 ``sync_resources`` 补齐。

        事件是进程内广播、只能往后接，所以「先到事件、后到成员」是常态。
        """
        h = _clean(hash_string).lower()
        gid = _clean(self.group_of(h)) if h else ""
        if gid:
            self.set_library(gid, True, media_id=media_id, path=path, now=now)
            return gid
        if not h:
            return ""
        try:
            pend = dict(self._get_data(LIB_PENDING_KEY) or {})
        except Exception:  # noqa: BLE001
            pend = {}
        ts = float(now if now is not None else time.time())
        rec = dict(pend.get(h) or {})
        rec["path"] = _clean(path) or rec.get("path") or ""
        if media_id:
            rec["media_id"] = str(media_id)
        rec.setdefault("first_at", ts)
        rec["updated"] = ts
        pend[h] = rec
        try:
            self._save_data(LIB_PENDING_KEY, pend)
        except Exception as err:  # noqa: BLE001
            self._log and self._log(f"标签:库记待办写入失败:{err}", "error")
        return ""

    def pending_library(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = self._get_data(LIB_PENDING_KEY) or {}
        except Exception:  # noqa: BLE001
            return {}
        return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}

    def flush_pending_library(self, *, now: Optional[float] = None) -> int:
        """把「已纳管」的库记待办落到资源上；返回落地条数。"""
        pend = self.pending_library()
        if not pend:
            return 0
        done = 0
        left: Dict[str, Dict[str, Any]] = {}
        for h, rec in pend.items():
            gid = self.group_of(h)
            if gid:
                if self.set_library(gid, True, media_id=str(rec.get("media_id") or ""),
                                    path=str(rec.get("path") or ""), now=now):
                    done += 1
                continue
            left[h] = rec
        if done or len(left) != len(pend):
            try:
                self._save_data(LIB_PENDING_KEY, left)
            except Exception:  # noqa: BLE001
                pass
        return done

    def due_hr(self, *, now: Optional[float] = None) -> List[Tuple[str, Dict[str, Any]]]:
        """还没结清、且记了来源种 hash 的 H&R 账单（交给来源站挂种去还）。"""
        out: List[Tuple[str, Dict[str, Any]]] = []
        for gid, rec in self.items().items():
            hr = rec.get("hr") or {}
            if not hr or hr.get("settled"):
                continue
            if not _clean(hr.get("by_hash")):
                continue
            out.append((gid, hr))
        return out

    def resources(self, *, limit: int = 0) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for gid, rec in self.items().items():
            members = rec.get("members") or {}
            hr = dict(rec.get("hr") or {})
            lib = dict(rec.get("library") or {})
            _fps = sorted({_clean((m or {}).get("fp")) for m in members.values() if _clean((m or {}).get("fp"))})
            out.append({
                "group_id": gid,
                "fp": _fps[0] if _fps else "",
                "size_gb": round(float(rec.get("size_gb") or 0), 2),
                "members": len(members),
                "sites": sorted({str((m or {}).get("site") or "") for m in members.values() if (m or {}).get("site")}),
                "source_site": rec.get("source_site") or "",
                "hr": hr,
                "library": lib,
            })
        out.sort(key=lambda x: x["members"], reverse=True)
        return out[: max(1, int(limit))] if limit else out

    def remove_member(self, hash_string: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        """摘掉一个成员；返回 ``{found, group_id, remaining, delete_files}``。

        ``delete_files=True`` 仅当**组内再无成员**（最后一个站也不要了）。
        找不到组 = 独立种，按 ``remaining=0`` 处理（可以删文件）。
        """
        h = _clean(hash_string).lower()
        data = self.items()
        gid = ""
        for key, rec in data.items():
            if h in (rec.get("members") or {}):
                gid = key
                break
        if not gid:
            return {"found": False, "group_id": "", "remaining": 0, "delete_files": True}
        rec = dict(data.get(gid) or {})
        members = dict(rec.get("members") or {})
        members.pop(h, None)
        if members:
            rec["members"] = members
            rec["files_shared"] = True
            rec["updated"] = float(now if now is not None else time.time())
            data[gid] = rec
            self._write(data)
            return {"found": True, "group_id": gid, "remaining": len(members), "delete_files": False}
        data.pop(gid, None)
        self._write(data)
        return {"found": True, "group_id": gid, "remaining": 0, "delete_files": True}

    def stats(self) -> Dict[str, int]:
        items = self.items()
        multi = sum(1 for rec in items.values() if len(rec.get("members") or {}) > 1)
        with_fp = sum(1 for rec in items.values()
                      if any(_clean((m or {}).get("fp")) for m in (rec.get("members") or {}).values()))
        return {"groups": len(items), "multi_site_groups": multi, "groups_with_fp": with_fp}


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
    store: Dict[str, Any] = {}

    def _get(key: str) -> Any:
        return store.get(key)

    def _save(key: str, value: Any) -> None:
        store[key] = value

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

    st = TagStateStore(_get, _save, log=lambda *a, **k: None)
    st.put("aaa", {"site": "财神", "state": STATE_SILENT, "sub": SUB_RESOURCE, "size_gb": 10})
    assert st.state_of("aaa") == (STATE_SILENT, SUB_RESOURCE)
    ok, why = st.claim("aaa", "task1", state=STATE_BRUSH)
    assert ok, why
    # ★ 5.0.0：占用只改职务，身份（sub）保留
    assert st.state_of("aaa") == (STATE_BRUSH, SUB_RESOURCE)
    ok2, why2 = st.claim("aaa", "task2", state=STATE_BONUS)
    assert not ok2, "刷流/魔力互不接管必须拦住"
    back = st.release("aaa", task_id="task1")
    assert back == "魔流-财神-静默-资源", back
    # ★ 5.0.0 铁律：在岗（职务轴）期间**不接**「顺手改身份」的写（分拣只在池内改）
    _ok3, _why3 = st.claim("aaa", "task1", state=STATE_BRUSH)
    assert _ok3, _why3
    st.put("aaa", {"sub": SUB_PLAIN, "reason": "静默分拣:想改身份"})
    assert st.state_of("aaa") == (STATE_BRUSH, SUB_RESOURCE), "在岗期间身份被顺手改了！"
    st.put("aaa", {"sub": SUB_PLAIN, "state": STATE_SILENT})
    assert st.state_of("aaa") == (STATE_SILENT, SUB_PLAIN), "回池后应能改身份"
    st.release("aaa", task_id="task1")
    assert st.state_of("aaa") == (STATE_SILENT, SUB_PLAIN)
    # 静默-新 超时 → 普通
    st.put("bbb", {"site": "咖啡", "state": STATE_SILENT, "sub": SUB_NEW, "created": time.time() - 90_000})
    assert st.expire_new() == ["bbb"]
    assert st.state_of("bbb") == (STATE_SILENT, SUB_PLAIN)
    # 快照 / 回滚
    st.snapshot(keep=2)
    st.drop("aaa")
    assert st.get("aaa") == {}
    assert st.restore_latest() >= 1 and st.get("aaa")

    fg = FileGroupStore(_get, _save, log=lambda *a, **k: None)
    fg.add_member("g1", "h1", site="财神", size_gb=5)
    fg.add_member("g1", "h2", site="学校")
    fg.add_member("g1", "h3", site="咖啡")
    r = fg.remove_member("h1")
    assert (r["remaining"], r["delete_files"]) == (2, False), r
    r = fg.remove_member("h2")
    assert (r["remaining"], r["delete_files"]) == (1, False), r
    r = fg.remove_member("h3")
    assert (r["remaining"], r["delete_files"]) == (0, True), r
    assert fg.group_of("h1") == ""
    r = fg.remove_member("h9")   # 独立种
    assert r["found"] is False and r["delete_files"] is True
    print("tags.py 自测通过 ✓", st.stats(), fg.stats())
