# -*- coding: utf-8 -*-
"""魔流 · 岗位操作（占岗 / 退岗 / 让位）—— 「纳管」中台。

────────────────────────────────────────────────────────────────────────
分工：注册表 vs 操作层
────────────────────────────────────────────────────────────────────────
  · ``dutyreg.py`` —— **岗位表**：有哪些岗位、各占哪个职务、谁优先、能不能跨岗挑人。
    纯数据 + 纯判据，不碰账本、不碰 qB、不写标签。
  · 本模块 —— **交接动作**：读账本 → 判能不能接 → 贴职务标签 → 写账本 →
    告诉调用方「哪些该拉起 / 哪些该暂停」。不定义岗位，只按 ``taker`` 干活。

为什么需要它：同一段流程原来在**四处各写一遍** ——

    ``tags.duty_assign``        音乐 / 点播（在途管道）
    ``hr._hr_host_assign``      欠 H&R 的保种
    ``tags._manual_hold``       人工点名保种
    ``claim._claim_host_status`` 认领（名单驱动）

差异其实只有五个开关：职务名、租约多长、要不要记 ``prev_state``、退出回落到哪、
谁负责拉起。其余（取账本 / 认站点 / 认身份 / 让位判断 / 贴标签 / 写账本 / 幂等）
逐字相同 —— 每加一个岗位就要再抄一遍，抄漏一处就互相拉锯（2026-10-28 实测）。
现在收敛成 :func:`assign` + :func:`release`，差异全部走关键字参数。

────────────────────────────────────────────────────────────────────────
两个不变量
────────────────────────────────────────────────────────────────────────
  ① **一个种同一时刻只归一个岗位**。能不能从别人手里接，只问
     ``dutyreg.duty_take_check``（默认：只招「没岗位」的种；特殊岗位才能跨岗挑人）。
  ② **职务标签与账本必须同源**。贴标签成功才写账本；账本 ``taken_by`` 是 qB 标签的
     镜像，不是另一个真值 —— 标签掉了会被下一轮审计判「静默」并暂停（认领拉锯的成因）。

★ 只通过 ``host`` 协作对象干活（``_get_downloader`` / ``_tag_state`` /
  ``_tag_all_torrents`` / ``_torrent_site_name`` / ``_log``），不 import ``features/*``，
  也不 import ``common``（那边顶部依赖 ``app.*``，会把离线测试拖崩）。
  依赖方向：``dutyops`` → ``dutyreg`` → ``tags``（纯函数层）。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .dutyreg import duty_take_check
from .tags import (
    STATE_SILENT,
    SUB_PLAIN,
    SUB_RESOURCE,
    duty_of,
    identity_of,
    parse_tag,
    retag,
    tag_for,
)

__all__ = [
    "normalize_hashes",
    "holder",
    "lease_of",
    "free_for",
    "has_duty_tag",
    "claim_hashes",
    "resolve_identity",
    "assign",
    "release",
]

_DEFAULT_SUB = SUB_RESOURCE


# ---------------------------------------------------------------- 小工具

def normalize_hashes(hashes: Any) -> List[str]:
    """``str`` / 可迭代 → 去空、去重、小写。"""
    hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
    out: List[str] = []
    for h in hs:
        hh = str(h or "").strip().lower()
        if hh and hh not in out:
            out.append(hh)
    return out


def holder(rec: Any) -> str:
    """账本记录 → 现任岗位 id（空串 = 没人在岗）。"""
    return str((rec or {}).get("taken_by") or "").strip()


def lease_of(rec: Any) -> float:
    """账本记录的租约到期时间；坏值按 0（= 无租约）处理。"""
    try:
        return float((rec or {}).get("lease_until") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def free_for(rec: Any, taker: Any, *, now: float = 0.0, taker_id: str = "") -> Tuple[bool, str]:
    """**占岗判定的唯一入口**：``taker`` 能不能接手 ``rec`` 这个种。

    包装 ``dutyreg.duty_take_check``，把「从账本记录里抠 taken_by / lease_until」
    这段样板收进来 —— 调用方不必再手写 ``float(rec.get("lease_until") or 0)``。

    ★ 19.10.40：一并把 ``rec["state"]`` 当 ``holder_state`` 递下去 —— 真任务岗
      （刷流/魔力）的 ``taken_by`` 是动态 task_id，单靠 id 反查不到登记项，会被
      误判成「未登记任务只看租约」而互相抢光（见 ``duty_take_check`` 的说明）。

    ``taker_id``：调用方自己的**真实任务 id**（不是岗位 spec）。传了才能让
    「自己重贴自己名下的种」保持幂等 —— 真任务岗的 ``DutySpec.id`` 是空串，
    拿它跟 ``taken_by`` 比永远不相等。
    """
    return duty_take_check(
        taker, holder(rec),
        lease_until=lease_of(rec), now=now,
        holder_state=str((rec or {}).get("state") or ""),
        taker_id=taker_id,
    )


def has_duty_tag(cur: Any, state: Any) -> bool:
    """qB 当前标签里**有没有**该职务轴（不看顺序 —— 多处残留职务标签是常态）。"""
    st = str(state or "")
    if not st:
        return False
    tags = [str(x).strip() for x in (cur or [])]
    try:
        return any((parse_tag(t) or {}).get("state") == st for t in tags)
    except Exception:  # noqa: BLE001
        try:
            return duty_of(tags)[1] == st
        except Exception:  # noqa: BLE001
            return False


def claim_hashes(host: Any, site_id: Any = None) -> Set[str]:
    """认领名单（小写集合）；取不到 = 空集（不因为认领接口异常就把整轮拦下）。

    只看名单、不看账本 —— 站点侧承诺是**站外真值**，账本被清过也不该放行删除/暂停。
    """
    try:
        raw = (host._claim_protected_hashes(site_id) if site_id is not None
               else host._claim_protected_hashes()) or set()
    except Exception:  # noqa: BLE001
        return set()
    return {str(x).strip().lower() for x in raw if str(x or "").strip()}


def resolve_identity(host: Any, rec: Any, cur: Any, *, site: str = "", sub: str = "",
                     default_sub: Any = _DEFAULT_SUB) -> Tuple[str, str]:
    """站点 / 子类身份归一 —— 优先级：显式入参 > 账本 > qB 标签 > 站点反查 > 缺省。

    ``default_sub`` 可给 ``callable(rec) -> str``（H&R 保种按「库内资产 ? 资源 : 新」推导）。
    """
    rec = rec or {}
    try:
        _i_site, _i_sub = identity_of([str(x).strip() for x in (cur or [])])
    except Exception:  # noqa: BLE001
        _i_site, _i_sub = "", ""
    if callable(default_sub):
        try:
            _fallback = str(default_sub(rec) or SUB_PLAIN)
        except Exception:  # noqa: BLE001
            _fallback = SUB_PLAIN
    else:
        _fallback = str(default_sub or _DEFAULT_SUB)
    _sub = str(sub or "") or str(rec.get("sub") or "") or _i_sub or _fallback
    _site = str(site or "") or str(rec.get("site") or "") or _i_site
    if not _site:
        try:
            _site = host._torrent_site_name([str(x).strip() for x in (cur or [])], "")
        except Exception:  # noqa: BLE001
            _site = ""
    return str(_site or ""), str(_sub or _fallback)


def _prepare(host: Any) -> Tuple[Any, Any, Dict[str, Any], Any, Optional[Callable]]:
    """取 (downloader, store, snapshot, tag_fn)；拿不到账本返回 store=None。"""
    try:
        downloader = host._get_downloader("qbittorrent")
    except Exception:  # noqa: BLE001
        downloader = None
    try:
        store = host._tag_state()
        snap = host._tag_all_torrents() or {}
    except Exception:  # noqa: BLE001
        return downloader, None, {}, None
    fn = getattr(downloader, "replace_torrent_tags", None)
    return downloader, store, dict(snap), fn


def _write_tags(downloader: Any, fn: Optional[Callable], hh: str, tags: Sequence[str]) -> bool:
    """写一次标签；``replace_torrent_tags`` 优先（可整组替换），否则退回逐条设置。"""
    try:
        if callable(fn):
            return bool(fn(hh, list(tags)))
        if downloader is None:
            return False
        return bool(downloader.set_torrent_tags(hh, list(tags)))
    except Exception:  # noqa: BLE001
        return False


def _live_tags(live: Any) -> List[str]:
    if live is None:
        return []
    return [str(x).strip() for x in (getattr(live, "tags", None) or [])]


# ---------------------------------------------------------------- 占岗

def assign(host: Any, hashes: Any, *, taker: Any, state: Any, name: str = "",
           site: str = "", sub: str = "", default_sub: Any = _DEFAULT_SUB,
           lease_until: float = 0.0, prev_from: Iterable[str] = (),
           apply: bool = True, require_live: bool = False, require_site: bool = False,
           resume_when: str = "none", extra: Optional[Dict[str, Any]] = None,
           label: str = "") -> Dict[str, Any]:
    """把 ``hashes`` 交到 ``taker`` 手上（贴职务标签 + 写账本 ``taken_by``）。

    参数（= 四个老实现之间的全部差异）：

      taker / state    占位者 id / 它名下的种算哪个职务
      name             账本 ``task`` 展示名
      site / sub       显式覆盖站点 / 子类（缺省从账本与标签推导）
      default_sub      推不出子类时的兜底；可给 ``callable(rec)``
      lease_until      账本租约到期绝对时间；0 = 长期持有不设租约
      prev_from        记录 ``prev_state`` 的来源职务集合（只记这里列出的，
                       退出时才能还原成刷流/魔力；不在列的一律回静默）
      apply            ``False`` = 干跑（只算 ``would``，零写入零贴标）
      require_live     True = qB 里没有这个种就跳过（人工点名；不凭空造记录）
      require_site     True = 认不出站点就跳过（认领；免得写出无站身份被当孤儿标签）
      resume_when      ``none`` / ``new``（只新纳管）/ ``all``（在岗的也进 resume）
      extra            额外写进账本的字段

    返回 ``{candidates, adopted, holding, blocked, blocked_hashes, skipped,
    failed, samples, would, resume}``：

      · ``holding`` 已在岗且标签在位（幂等跳过；账本职务漂移时只补账本、不重贴标签）
      · ``blocked`` 别的岗位在岗、本岗不让抢（**不是故障**，正常让位）
      · ``would``   ``apply=False`` 时「真写会纳管哪些」
      · ``resume``  按 ``resume_when`` 给出该拉起/检查的 hash 列表
    """
    rep: Dict[str, Any] = {
        "candidates": 0, "adopted": 0, "holding": 0, "blocked": 0,
        "blocked_hashes": [], "skipped": 0, "failed": 0,
        "samples": [], "would": [], "resume": [],
    }
    hs = normalize_hashes(hashes)
    if not hs:
        return rep
    downloader, store, snap, fn = _prepare(host)
    if store is None:
        rep["error"] = "账本不可用"
        return rep
    st = str(state or "")
    _taker = str(taker or "")
    _now = time.time()
    _prev_set = tuple(str(x) for x in (prev_from or ()) if str(x or ""))

    for hh in hs:
        live = snap.get(hh)
        if live is None and require_live:
            rep["skipped"] = int(rep["skipped"]) + 1
            continue
        cur = _live_tags(live)
        rec = store.get(hh) or {}
        _site, _sub = resolve_identity(host, rec, cur, site=site, sub=sub,
                                       default_sub=default_sub)
        if require_site and not _site:
            rep["skipped"] = int(rep["skipped"]) + 1
            continue
        # ① 已在岗：账本归本岗 + 标签在位 → 只对齐账本职务（不重贴标签）
        if holder(rec) == _taker and has_duty_tag(cur, st):
            rep["holding"] = int(rep["holding"]) + 1
            if str(rec.get("state") or "") != st:
                try:
                    store.put(hh, {"state": st})
                except Exception:  # noqa: BLE001
                    pass
            if resume_when in ("all", "new"):
                rep["resume"].append(hh)
            continue
        # ② 让位：别的岗位在岗（谁能不能抢只看注册表）
        _free, _why = free_for(rec, _taker, now=_now, taker_id=_taker)
        if not _free:
            rep["blocked"] = int(rep["blocked"]) + 1
            if len(rep["blocked_hashes"]) < 10:
                rep["blocked_hashes"].append(hh)
            continue
        rep["candidates"] = int(rep["candidates"]) + 1
        if len(rep["samples"]) < 10:
            rep["samples"].append({"hash": hh[:12], "site": _site, "sub": _sub})
        if not apply:
            rep["would"].append(hh)
            continue
        # ③ 贴标签（成功才写账本：标签是 qB 真值，账本是镜像）
        new_tags = (retag(cur, site=_site, state=st, sub=_sub) if cur
                    else [tag_for(_site, STATE_SILENT, _sub), tag_for(_site, st)])
        if not _write_tags(downloader, fn, hh, new_tags):
            rep["failed"] = int(rep["failed"]) + 1
            continue
        patch: Dict[str, Any] = {
            "site": _site, "state": st, "sub": _sub,
            "taken_by": _taker, "task": str(name or ""),
            "taken_at": _now, "lease_until": float(lease_until or 0),
        }
        if live is not None:
            patch["title"] = str(getattr(live, "title", "") or "")
        _prev = str(rec.get("state") or "")
        if _prev_set and _prev in _prev_set:
            patch["prev_state"] = _prev
        if extra:
            patch.update(extra)
        try:
            store.put(hh, patch)
        except Exception:  # noqa: BLE001
            rep["failed"] = int(rep["failed"]) + 1
            continue
        rep["adopted"] = int(rep["adopted"]) + 1
        if resume_when in ("all", "new"):
            rep["resume"].append(hh)

    if label:
        if int(rep["adopted"]):
            _log(host, f"{label}:挂 {_taker} {rep['adopted']} 个")
        if int(rep["blocked"]):
            _log(host, f"{label}:跳过 {rep['blocked']} 个（在别的岗位名下，本岗不跨岗挑人）",
                 "debug")
    return rep


def _log(host: Any, msg: str, level: str = "") -> None:
    """打日志；离线桩没有 ``_log`` 时静默（岗位操作不该因为日志不可用而失败）。"""
    fn = getattr(host, "_log", None)
    if not callable(fn):
        return
    try:
        fn(msg, level) if level else fn(msg)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 退岗

def release(host: Any, hashes: Any, *, taker: Any, state: Any = STATE_SILENT,
            restore_prev: Iterable[str] = (), pause: bool = False,
            allow_untaken: bool = False, extra: Optional[Dict[str, Any]] = None,
            default_sub: Any = SUB_PLAIN, apply: bool = True,
            label: str = "") -> Dict[str, Any]:
    """把 ``taker`` 名下的种交回池子（摘职务标签 + 清账本占位，可选暂停）。

      taker           只放**自己**占的种（``allow_untaken=True`` 时连空占用也放，
                      用于清洗「账本职务在岗但 taken_by 空」的历史行）
      state           退回到哪个职务（默认静默）
      restore_prev    账本 ``prev_state`` 落在这些职务里 → 还原成它（认领：刷流/魔力）
      pause           True = 当场暂停（静默池语义就是不上传；不等下一轮收敛）
      extra           额外写进账本的字段（H&R 的 ``hr_released_at`` 等）
      default_sub     推不出子类时的兜底（H&R 用「普通」，其余「资源」）

    返回 ``{candidates, released, released_hashes, skipped, failed, samples}``。
    """
    rep: Dict[str, Any] = {"candidates": 0, "released": 0, "released_hashes": [],
                           "skipped": 0, "failed": 0, "samples": []}
    hs = normalize_hashes(hashes)
    if not hs:
        return rep
    downloader, store, snap, fn = _prepare(host)
    if store is None:
        rep["error"] = "账本不可用"
        return rep
    _taker = str(taker or "")
    _restore = tuple(str(x) for x in (restore_prev or ()) if str(x or ""))
    for hh in hs:
        rec = store.get(hh) or {}
        _own = holder(rec)
        if _own and _own != _taker:
            rep["skipped"] = int(rep["skipped"]) + 1
            continue
        if not _own and not allow_untaken:
            rep["skipped"] = int(rep["skipped"]) + 1
            continue
        rep["candidates"] = int(rep["candidates"]) + 1
        if len(rep["samples"]) < 10:
            rep["samples"].append({"hash": hh[:12], "site": str(rec.get("site") or "")})
        if not apply:
            continue
        live = snap.get(hh)
        cur = _live_tags(live)
        _site, _sub = resolve_identity(host, rec, cur, default_sub=default_sub)
        _prev = str(rec.get("prev_state") or "")
        target = _prev if (_prev and _prev in _restore) else str(state or STATE_SILENT)
        if cur:
            if not _write_tags(downloader, fn, hh, retag(cur, site=_site, state=target, sub=_sub)):
                rep["failed"] = int(rep["failed"]) + 1
                continue
        patch: Dict[str, Any] = {"prev_state": ""}
        if target != STATE_SILENT:
            # 还原到在岗职务（刷流/魔力）：职务留在账本里，占位清空后由任务重新认领
            patch.update({"state": target, "taken_by": "", "task": "", "lease_until": 0})
        if extra:
            patch.update(extra)
        try:
            if target == STATE_SILENT:
                store.release(hh, task_id=_taker)
                store.put(hh, patch)
            else:
                store.put(hh, patch)
        except Exception:  # noqa: BLE001
            rep["failed"] = int(rep["failed"]) + 1
            continue
        if pause and target == STATE_SILENT and downloader is not None:
            try:
                _pz = getattr(downloader, "pause_torrents", None)
                if callable(_pz):
                    _pz([hh])
            except Exception:  # noqa: BLE001
                pass
        rep["released"] = int(rep["released"]) + 1
        rep["released_hashes"].append(hh)
    if label and int(rep["released"]):
        _log(host, f"{label}:退出 {rep['released']} 个")
    return rep


if __name__ == "__main__":  # 离线自检：python -m magicflow.dutyops
    assert normalize_hashes(["A", " a ", "", None]) == ["a"]
    assert holder({"taken_by": "__claim__"}) == "__claim__"
    assert holder({}) == ""
    assert lease_of({"lease_until": 123}) == 123.0 and lease_of({"lease_until": "x"}) == 0.0

    # 占位判定仍只由注册表说了算
    assert free_for({}, "__music__")[0]
    assert free_for({"taken_by": "__claim__"}, "__music__")[0] is False
    assert free_for({"taken_by": "__claim__"}, "__claim__")[0]
    assert free_for({"taken_by": "__claim__"}, "__keep__")[0]
    assert free_for({"taken_by": "__keep__"}, "__claim__")[0] is False
    assert free_for({"taken_by": "", "lease_until": 1}, "__music__")[0]

    # 标签职务判定不看顺序（残留职务标签是常态）
    assert has_duty_tag(["魔流-馒头-魔力", "魔流-馒头-认领"], "认领")
    assert not has_duty_tag(["魔流-馒头-静默-资源"], "认领")
    assert not has_duty_tag([], "认领")
    print("dutyops OK")
