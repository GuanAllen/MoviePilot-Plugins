# -*- coding: utf-8 -*-
"""魔流 · 下载器写操作唯一出口（dlops）—— 「谁停的」必须能一眼答出来。

────────────────────────────────────────────────────────────────────────
为什么要有这一层（2026-10-28 实测债）
────────────────────────────────────────────────────────────────────────
每 60 分钟，qB 里固定有 **930 个种被暂停、紧接着 911 个被恢复**（18:21/19:22/…），
`pause` 与 `resume` 精确对消，同一批种一天被拉锯 80+ 次。其中一半以上账本是「魔力」
（在岗），还夹着 9 个认领种 —— 在岗不该停，这是铁律。

排查时逐个排除了插件内**全部四个** ``pause_torrents`` 调用点：

    core._apply_run_mode        无「应用运行状态」日志 → 排除
    silent._silent_pause_gate   干跑 violations=0 → 排除
    siteops                     人工运维入口，非周期 → 排除
    tags.set_tag_state          单 hash → 排除

—— 但 930 个暂停**真实发生**，且**没有任何一行日志**。结论：在当前结构下
「谁停的」这个问题**不可回答**。原因有三：

  ① **写操作散落**：``pause_torrents`` 4 处、``resume_torrents`` 12 处，横跨 9 个
     文件；成功路径**全部不打日志**（只在失败时 warning）。
  ② **守卫各管一段**：``_silent_pause_gate`` 会查账本（在岗不暂停），但只有走它的
     路径受保护；``_apply_run_mode`` / cleanup 的恢复直接调适配器，一路无阻。
  ③ **没有归因**：调用方是谁、为什么、批量多大，事后无法还原。

────────────────────────────────────────────────────────────────────────
本模块做四件事
────────────────────────────────────────────────────────────────────────
  1. **归因** —— 每个写操作必须带 ``by``（调用方）+ ``reason``，成功也打一行日志。
  2. **守卫** —— 一处判据，所有路径自动生效（不只静默闸那一条）：
       · ``pause``：账本 state 非静默（在别的生命周期）或 ``taken_by`` 占岗 → 拒
       · ``resume``：账本 state=静默 且 无人占岗（休息区）→ 拒
     拒因进 ``reasons``，可对账「这一轮谁被谁挡住」。
  3. **防抖** —— 同一 hash 在 :data:`FLAP_WINDOW` 秒内被**反向**操作 → 拒绝并计
     ``flapped``。这一条直接掐死「停 930 → 起 911 → 再停」的对消，不必先定位凶手。
  4. **干跑** —— ``dry=True`` 只算不写，用于上线前比对「会拒多少」。

★ 与「静默是不是岗位」正交：静默不需要升格成岗位，它只需要一条**明确的**
  「谁能让它停 / 谁能让它起」的规则 —— 那规则就是本模块的守卫，一处代码。

★ 只管得住「插件自己人」，管不住外部进程（另一个容器/脚本直连 qB）。若某轮日志显示
  「本插件一次 pause 都没发」而 qB 仍在停，即可反证是外部调用方。

★ 只通过 ``host`` 协作对象干活（``_get_downloader`` / ``_tag_state`` / ``_log``），
  不 import ``features/*``，也不 import ``common``（顶部依赖 ``app.*``，会拖崩离线测试）。
  依赖方向：``dlops`` → ``dutyreg`` → ``tags``（纯函数层）。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .dutyreg import duty_spec
from .tags import STATE_SILENT

__all__ = [
    "FLAP_WINDOW",
    "normalize",
    "veto_of",
    "pause",
    "resume",
    "recheck",
    "stats",
    "reset",
]

#: 防抖窗口（秒）：同一 hash 在窗口内被反向操作 → 判「抖」
FLAP_WINDOW = 90.0

#: 最近操作表上限（超了先清过期项）
_FLAP_MAX = 20000

#: hash → (最后一次成功动作, 时间戳)
_FLAP: Dict[str, Tuple[str, float]] = {}
_FLAP_LOCK = threading.Lock()

#: 累计计数（进程内自增，供 /debug 或 stats() 查）
_STAT: Dict[str, int] = {}

_ACT = {"pause": "pause_torrents", "resume": "resume_torrents", "recheck": "recheck_torrents"}


# ---------------------------------------------------------------- 小工具

def normalize(hashes: Any) -> List[str]:
    """规整成去重、小写、非空的 hash 列表（保持入参顺序）。"""
    if isinstance(hashes, str):
        hashes = [hashes]
    out: List[str] = []
    seen = set()
    for h in hashes or ():
        hh = str(h or "").strip().lower()
        if hh and hh not in seen:
            seen.add(hh)
            out.append(hh)
    return out


def _bump(key: str, n: int = 1) -> None:
    try:
        _STAT[key] = int(_STAT.get(key) or 0) + int(n)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 守卫

def veto_of(rec: Any, act: str) -> str:
    """判「这个动作对这条账本记录该不该放行」→ 拒因（空串 = 放行）。

    **只读账本**，不看 qB 标签 —— 标签会掉、会双写（一个种同时挂「静默-资源」和
    「魔力」是常态，2026-10-28 实测 1339/1990），账本 ``state`` 才是单值真值。

    返回的字符串同时进 ``reasons`` 计数，所以保持短、稳定：
      ``on_duty``    ``taken_by`` 是占岗岗位（认领/保种/点播/音乐…）
      ``other_state`` 账本职务不是静默（在别的生命周期）
      ``silent_rest`` 静默且无人占岗（休息区）
    """
    r = rec if isinstance(rec, dict) else {}
    st = str(r.get("state") or "").strip()
    own = str(r.get("taken_by") or "").strip()
    on_duty = False
    if own:
        try:
            spec = duty_spec(own)
            on_duty = bool(spec is not None and spec.occupancy)
        except Exception:  # noqa: BLE001
            on_duty = False
    if act == "pause":
        # 停一个在岗种 = 白丢做种时长（H&R 按墙钟计时，认领算承诺）
        if on_duty:
            return "on_duty"
        if st and st != STATE_SILENT:
            return "other_state"
        return ""
    if act == "resume":
        # 起来会被静默闸下一轮再停 → 对消；静默就该歇着
        if st == STATE_SILENT and not on_duty:
            return "silent_rest"
        return ""
    return ""


# ---------------------------------------------------------------- 防抖

def _flapped(hh: str, act: str, now: float) -> bool:
    prev = _FLAP.get(hh)
    if not prev:
        return False
    p_act, p_ts = prev
    return p_act != act and (now - p_ts) <= FLAP_WINDOW


def _note(hashes: List[str], act: str, now: float) -> None:
    with _FLAP_LOCK:
        for hh in hashes:
            _FLAP[hh] = (act, now)
        if len(_FLAP) > _FLAP_MAX:
            for k, (_a, ts) in list(_FLAP.items()):
                if now - ts > FLAP_WINDOW:
                    _FLAP.pop(k, None)


def reset() -> None:
    """清空防抖表与计数（测试用，线上别调）。"""
    with _FLAP_LOCK:
        _FLAP.clear()
    _STAT.clear()


def stats() -> Dict[str, Any]:
    """当前防抖表规模 + 累计计数（只读，给 /debug 用）。"""
    with _FLAP_LOCK:
        n = len(_FLAP)
    return {"flap_table": n, "window_s": FLAP_WINDOW, "counters": dict(_STAT)}


# ---------------------------------------------------------------- 主流程

def _say(host: Any, rep: Dict[str, Any]) -> None:
    """一行归因日志 —— 成功也打（这是本次改造的核心诉求）。"""
    fn = getattr(host, "_log", None)
    if not callable(fn):
        return
    try:
        parts = [
            f"dlops:{rep['act']}",
            f"by={rep['by']}",
            f"请={rep['asked']}",
            f"成={rep['done']}",
        ]
        if rep["vetoed"]:
            detail = ",".join(f"{k}:{v}" for k, v in sorted(rep["reasons"].items()))
            parts.append(f"拒={rep['vetoed']}({detail})")
        if rep["flapped"]:
            parts.append(f"抖={rep['flapped']}")
        if rep["reason"]:
            parts.append(f"因={str(rep['reason'])[:48]}")
        if rep["error"]:
            parts.append(f"错={str(rep['error'])[:60]}")
        if rep["dry"]:
            parts.append("(干跑)")
        fn("魔流:" + " ".join(parts))
    except Exception:  # noqa: BLE001
        pass


def _run(
    host: Any,
    hashes: Any,
    *,
    act: str,
    by: Any,
    reason: str = "",
    force: bool = False,
    dry: bool = False,
    downloader: str = "qbittorrent",
) -> Dict[str, Any]:
    hs = normalize(hashes)
    rep: Dict[str, Any] = {
        "act": act,
        "by": str(by or "?"),
        "reason": str(reason or ""),
        "asked": len(hs),
        "done": 0,
        "vetoed": 0,
        "flapped": 0,
        "planned": 0,
        "vetoed_hashes": [],
        "reasons": {},
        "error": "",
        "dry": bool(dry),
    }
    if not hs:
        return rep
    now = time.time()

    # 1) 守卫（账本）：force=True 整段跳过（结清/遣散这类「必须停」的场景）
    allow: List[str] = []
    if force:
        allow = list(hs)
    else:
        try:
            led = host._tag_state()
        except Exception:  # noqa: BLE001
            led = None
        for hh in hs:
            try:
                rec = (led.get(hh) if led is not None else None) or {}
            except Exception:  # noqa: BLE001
                rec = {}
            why = veto_of(rec, act)
            if why:
                rep["reasons"][why] = int(rep["reasons"].get(why) or 0) + 1
                rep["vetoed"] = int(rep["vetoed"]) + 1
                _bump(f"veto_{why}")
                if len(rep["vetoed_hashes"]) < 20:
                    rep["vetoed_hashes"].append(hh)
            else:
                allow.append(hh)

    # 2) 防抖：窗口内反向操作 → 拒（这是掐死「停 930 / 起 911」对消的那一刀）
    keep: List[str] = []
    for hh in allow:
        if _flapped(hh, act, now):
            rep["flapped"] = int(rep["flapped"]) + 1
            _bump("flapped")
        else:
            keep.append(hh)

    _bump(f"asked_{act}", len(hs))
    if dry:
        rep["planned"] = len(keep)
        _say(host, rep)
        return rep
    if not keep:
        _say(host, rep)
        return rep

    # 3) 真做
    try:
        dl = host._get_downloader(downloader)
    except Exception as err:  # noqa: BLE001
        rep["error"] = f"下载器不可用:{err}"
        _say(host, rep)
        return rep
    if dl is None:
        rep["error"] = "下载器不可用"
        _say(host, rep)
        return rep
    fn = getattr(dl, _ACT.get(act, ""), None)
    if not callable(fn):
        rep["error"] = f"下载器不支持 {act}"
        _say(host, rep)
        return rep
    try:
        n, err = fn(keep)
        rep["done"] = int(n or 0)
        if err:
            rep["error"] = str(err)
    except Exception as err:  # noqa: BLE001
        rep["error"] = f"{act} 异常:{err}"
        _say(host, rep)
        return rep
    if rep["done"]:
        _note(keep, act, now)
        _bump(f"done_{act}", rep["done"])
    _say(host, rep)
    return rep


# ---------------------------------------------------------------- 公开入口

def pause(
    host: Any,
    hashes: Any,
    *,
    by: Any,
    reason: str = "",
    force: bool = False,
    dry: bool = False,
    downloader: str = "qbittorrent",
) -> Dict[str, Any]:
    """暂停种子（唯一出口）。

    Args:
        by: 调用方标识（写进日志，如 ``"silent_enforce"`` /
            ``"run_mode:stopped"`` / ``"claim_release"``）。**必填** —— 这一栏就是
            排查「谁停的」的答案。
        force: 跳过账本守卫。只给「结清/遣散」这类**必须停**的路径用。
        dry: 只算不写。
    """
    return _run(host, hashes, act="pause", by=by, reason=reason,
                force=force, dry=dry, downloader=downloader)


def resume(
    host: Any,
    hashes: Any,
    *,
    by: Any,
    reason: str = "",
    force: bool = False,
    dry: bool = False,
    downloader: str = "qbittorrent",
) -> Dict[str, Any]:
    """恢复做种（唯一出口）。守卫会挡住「静默休息区」的种 —— 那是拉锯的另一半。"""
    return _run(host, hashes, act="resume", by=by, reason=reason,
                force=force, dry=dry, downloader=downloader)


def recheck(
    host: Any,
    hashes: Any,
    *,
    by: Any,
    reason: str = "",
    dry: bool = False,
    downloader: str = "qbittorrent",
) -> Dict[str, Any]:
    """强制校验（唯一出口）。不涉职务语义，故不设 veto，但同样归因 + 记抖。"""
    return _run(host, hashes, act="recheck", by=by, reason=reason,
                force=True, dry=dry, downloader=downloader)
