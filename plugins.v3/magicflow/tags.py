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
SUBS = (SUB_NEW, SUB_RESOURCE, SUB_PLAIN)

# 只有「静默」有子类
STATES_WITH_SUB = (STATE_SILENT,)

STATE_KEY = "tag_state"
GROUPS_KEY = "tag_groups"
SNAPSHOT_KEY = "tag_state_snapshot"
SORT_RULES_KEY = "sort_rules"

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


def _official_sites() -> List[str]:
    """交给插件注入的站点短名表（用于把 ``魔流-财神-静默`` 解析成 (站点, 状态)）。"""
    return list(_SITE_NAMES)


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


# ★ 「全局特殊标签」：不属于某站点某状态，重贴标签时必须保留（否则会打断其它子系统）
SPECIAL_TAGS = ("魔流-推荐", "魔流-跨站")


def retag(
    tags: Any,
    *,
    site: str = "",
    state: str = "",
    sub: str = "",
    keep_foreign: bool = True,
    keep: Sequence[str] = SPECIAL_TAGS,
) -> List[str]:
    """按新状态重算标签集合：去掉旧的魔流标签，加上新的；外来标签保留。

    ``keep`` 里的特殊标签（推荐/跨站）即便带 ``魔流-`` 前缀也**保留**。
    """
    keep_set = {_clean(x) for x in (keep or ())}
    out: List[str] = []
    for t in tags or []:
        s = _clean(t)
        if not s:
            continue
        if s in keep_set:
            if s not in out:
                out.append(s)
            continue
        if is_magicflow_tag(s):
            continue
        if keep_foreign and s not in out:
            out.append(s)
    if state:
        new = tag_for(site, state, sub)
        if new not in out:
            out.append(new)
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
        try:
            data = self._get_data(STATE_KEY) or {}
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k).lower(): v for k, v in data.items() if isinstance(v, dict)}

    def _write(self, data: Dict[str, Any]) -> None:
        try:
            self._save_data(STATE_KEY, data)
        except Exception as err:  # noqa: BLE001
            self._log and self._log(f"标签:状态账本写入失败:{err}", "error")

    def get(self, hash_string: str) -> Dict[str, Any]:
        return dict(self.items().get(_clean(hash_string).lower()) or {})

    def state_of(self, hash_string: str) -> Tuple[str, str]:
        rec = self.get(hash_string)
        return _clean(rec.get("state")), _clean(rec.get("sub"))

    def put(self, hash_string: str, patch: Dict[str, Any], *, now: Optional[float] = None) -> Dict[str, Any]:
        """写入/合并一条记录（``state``/``sub`` 变化时自动记 origin）。"""
        h = _clean(hash_string).lower()
        if not h:
            return {}
        data = self.items()
        rec = dict(data.get(h) or {})
        ts = float(now if now is not None else time.time())
        new_state = _clean(patch.get("state", rec.get("state")))
        new_sub = _clean(patch.get("sub", rec.get("sub")))
        # origin 只在「非占用态」之间变化时更新（占用态由 claim/release 管）
        if new_state in (STATE_SILENT, STATE_RECOMMEND) and new_state != rec.get("state"):
            rec["origin_state"] = new_state
            rec["origin_sub"] = new_sub
        rec.update({k: v for k, v in patch.items() if v is not None})
        if new_state:
            rec["state"] = new_state
        if new_state in STATES_WITH_SUB:
            rec["sub"] = new_sub
        elif "sub" in patch and not patch.get("sub"):
            rec.pop("sub", None)
        rec.setdefault("created", ts)
        rec["updated"] = ts
        data[h] = rec
        self._write(data)
        return rec

    def drop(self, hash_string: str) -> bool:
        h = _clean(hash_string).lower()
        data = self.items()
        if h not in data:
            return False
        data.pop(h, None)
        self._write(data)
        return True

    def clear(self, *, keep_observed: bool = False) -> int:
        """清空账本。``keep_observed=True`` 时保留带 ``observed`` 标记的记录。"""
        data = self.items()
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

    def expire_new(self, *, now: Optional[float] = None, timeout: float = SILENT_NEW_TIMEOUT) -> List[str]:
        """``静默-新`` 超时未分拣 → 归 ``静默-普通``；返回被改动的 hash。"""
        ts = float(now if now is not None else time.time())
        moved: List[str] = []
        for h, rec in self.items().items():
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
        """占用一个静默种（``静默-*`` → ``刷流``/``魔力``）。

        返回 ``(是否成功, 原因)``。已有**未过期**占用者时拒绝（刷流/魔力互不接管）。
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
        origin_state = _clean(rec.get("origin_state")) or cur_state or STATE_SILENT
        origin_sub = _clean(rec.get("origin_sub")) or _clean(rec.get("sub"))
        rec.update({
            "state": state,
            "taken_by": _clean(task_id),
            "taken_at": ts,
            "lease_until": ts + float(ttl),
            "origin_state": origin_state,
            "origin_sub": origin_sub,
            "updated": ts,
        })
        if site:
            rec["site"] = _clean(site)
        rec.pop("sub", None)  # 占用态没有子类
        rec.setdefault("created", ts)
        data[h] = rec
        self._write(data)
        return True, "ok"

    def release(self, hash_string: str, *, task_id: str = "", now: Optional[float] = None) -> Optional[str]:
        """释放占用 → 按 ``origin`` 退回原静默子类；返回退回到的标签状态串。"""
        h = _clean(hash_string).lower()
        data = self.items()
        rec = dict(data.get(h) or {})
        if not rec:
            return None
        owner = _clean(rec.get("taken_by"))
        if task_id and owner and owner != _clean(task_id):
            return None  # 不是本任务占用的，别乱放
        state = _clean(rec.get("origin_state")) or STATE_SILENT
        sub = _clean(rec.get("origin_sub"))
        if state == STATE_SILENT and not sub:
            sub = SUB_PLAIN
        rec.update({"state": state, "updated": float(now if now is not None else time.time())})
        rec.pop("taken_by", None)
        rec.pop("taken_at", None)
        rec.pop("lease_until", None)
        if state in STATES_WITH_SUB:
            rec["sub"] = sub
        else:
            rec.pop("sub", None)
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
        snaps.append({"ts": ts, "count": len(self.items()), "items": self.items()})
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
                "sub": sub if state in STATES_WITH_SUB else "",
                "origin_state": state,
                "origin_sub": sub,
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
    """文件组账本：同一批文件在多站各有一个种。

    ``group_id -> {members: {hash: {site, downloader, added}}, size_gb, files_shared}``

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
        members[h] = {"site": _clean(site), "downloader": _clean(downloader), "added": ts}
        rec["members"] = members
        if size_gb:
            rec["size_gb"] = float(size_gb)
        rec["files_shared"] = bool(len(members) > 1 if files_shared is None else files_shared)
        rec.setdefault("created", ts)
        rec["updated"] = ts
        data[gid] = rec
        self._write(data)
        return {"group_id": gid, "members": len(members)}

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
        return {"groups": len(items), "multi_site_groups": multi}


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

    st = TagStateStore(_get, _save, log=lambda *a, **k: None)
    st.put("aaa", {"site": "财神", "state": STATE_SILENT, "sub": SUB_RESOURCE, "size_gb": 10})
    assert st.state_of("aaa") == (STATE_SILENT, SUB_RESOURCE)
    ok, why = st.claim("aaa", "task1", state=STATE_BRUSH)
    assert ok, why
    assert st.state_of("aaa") == (STATE_BRUSH, "")
    ok2, why2 = st.claim("aaa", "task2", state=STATE_BONUS)
    assert not ok2, "刷流/魔力互不接管必须拦住"
    back = st.release("aaa", task_id="task1")
    assert back == "魔流-财神-静默-资源", back
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
