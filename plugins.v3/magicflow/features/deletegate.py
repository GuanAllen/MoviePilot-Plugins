# -*- coding: utf-8 -*-
"""魔流 · deletegate —— 删除唯一入口（Master 2026-10-05：「删除令出一门」）。

背景：删种调用点原本散布在 cleanup / silent / crossseed / swap / recommend / actions…
多个模块，各写各的日志；每次排障都得回各模块翻，且保护口径容易分叉（实测事故：CARPT 37 个
H&R 补种被任务「超保留上限」路径删掉，因为该路径的保护集合与删除候选口径不一致）。

这里把「删种」收成**一个物理入口 + 一份统一台账**：

- 物理入口：``DownloaderAdapter.delete_torrents``（插件内所有删种都经它）挂上本闸门的
  ``gate`` 回调 —— 任何路径要删种，先过它。
- 统一台账：``<data_dir>/deletions.jsonl``，每行一条（**含被拦截的、含失败的**）：
  ``ts / hash / site / title / source / reason / delete_file / ok / blocked / err``。
  排查「谁删了 X」→ 只读这一个文件，按 hash grep。

闸门硬拦（**任何路径都不得删**，全局口径、不依赖单任务）：
  手动保留 / 跨站来源份（H&R 保种期）/ 已认领（保种承诺）/ 欠 H&R 义务。

（「未下完」「库内资产」「推荐中」属于各清理路径的**策略性**保护，仍由各行其责；
  换种（暂停不删）也走这里做硬拦，但台账记 ``delete_file`` 与来源。）

要新增一类「永不删」→ 只改本文件的 ``_delete_gate``。
"""

import json as _json
import sys as _sys
import time as _time
from typing import Any, Dict, Iterable, Set

from ..common import (
    begin_decision_round,
    note_snapshot_pull,
)


class DeleteGateMixin:
    """删除唯一入口：闸门判定 + 统一台账。"""

    # -------------------- 闸门：谁绝不能删 --------------------

    def _delete_gate(self, hashes: Iterable[str], snap: Any = None) -> Set[str]:
        """返回 ``hashes`` 中**受硬保护、绝不能删**的子集（全局口径）。

        与 ``_protection_sets`` 的 ``hard`` 同源，但**不需要单任务上下文**，因此可以在
        唯一的物理删种入口处无条件执行 —— 无论调用方是谁、保护集合算得对不对。

        ``snap``：本轮已拉好的 qB 全量快照（可选，同一轮内复用）。
        拦截理由见 ``_delete_gate_detail``（诊断 / 排查用）。
        """
        return set(self._delete_gate_detail(hashes, snap=snap).keys())

    def _delete_gate_detail(self, hashes: Iterable[str], force_error: bool = False, snap: Any = None) -> "Dict[str, str]":
        """返回 ``{hash: 拦截理由}``；未拦截的不出现。理由取值：

        手动保留 / 跨站来源份（H&R 保种期）/ 已认领（保种承诺）/ 欠 H&R 义务。

        ``force_error=True``：**故障注入**——强制抛异常，供离线测试与线上自检
        验证删除入口的 fail-closed 兜底（见模块级 ``gate_self_test``）。
        """
        # ★ 故障注入入口（仅用于测试 / 自检，不影响正常调用）：
        #   删种入口拿到闸门异常 → fail-closed 会全阻断。用它可验证「拦得住」。
        if force_error:
            raise RuntimeError("delete gate self-test forced error")
        hs = [str(h or "").strip().lower() for h in (hashes or []) if str(h or "").strip()]
        if not hs:
            return {}
        why: Dict[str, str] = {}

        # 1) 手动保留（跨所有任务取并集）
        try:
            store = getattr(self, "_store", None)
            if store is not None:
                _tids = list((getattr(self, "_task_configs", None) or {}).keys())
                _tids.append("")  # 兼容历史按空 task_id 存的保留
                _man: set = set()
                for _tid in _tids:
                    try:
                        _man |= set(store.get_protected_torrents(_tid) or set())
                    except Exception:  # noqa: BLE001
                        continue
                for h in hs:
                    if h in {str(x).strip().lower() for x in _man}:
                        why.setdefault(h, "手动保留")
        except Exception:  # noqa: BLE001
            pass

        # 2) 跨站来源份（别的站的 H&R 保种责任种）
        try:
            _cs = {str(x).strip().lower() for x in (self._crossseed_source_hashes() or set())}
            for h in hs:
                if h in _cs:
                    why.setdefault(h, "跨站来源份（H&R 保种期）")
        except Exception:  # noqa: BLE001
            pass

        # 3) 已认领（保种承诺：删了 → 站点判不达标 → 扣魔力）
        try:
            _cl = {str(x).strip().lower() for x in (self._claim_protected_hashes() or set())}
            for h in hs:
                if h in _cl:
                    why.setdefault(h, "已认领（保种承诺）")
        except Exception:  # noqa: BLE001
            pass

        # 4) 欠 H&R 义务（★ 9.0.0：**按资源判** —— 债挂在资源上，用「来源站那个种」的做种时长判；
        #    没有资源 / 来源站无 H&R / 账单已结清 → 不拦。不再要求「站点可确定」。）
        _rest = [h for h in hs if h not in why]
        if _rest:
            begin_decision_round()
            if snap is None:
                try:
                    snap = self._tag_all_torrents() or {}
                except Exception:  # noqa: BLE001
                    snap = {}
                note_snapshot_pull(1)
            try:
                _ridx = self._resource_source_index()
            except Exception:  # noqa: BLE001
                _ridx = {}
            for h in _rest:
                t = snap.get(h)
                if t is None:
                    continue
                try:
                    owed, _need, _seeded, _src = self._hr_obligation("", t, snap=snap)
                except Exception:  # noqa: BLE001
                    owed, _need, _seeded, _src = False, 0.0, 0.0, ""
                if owed:
                    why[h] = f"欠 H&R 义务（{_src or '来源站未知'}·未挂满 {_seeded:.1f}/{_need:.1f}h）"
        return why

    # -------------------- 统一台账 --------------------

    def _deletions_log_path(self):
        try:
            store = getattr(self, "_store", None)
            d = getattr(store, "data_dir", None)
            if d is None:
                d = self.get_data_path()
            return (d / "deletions.jsonl") if d is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _delete_log_cb(
        self,
        hashes: Iterable[str],
        delete_file: bool,
        reason: str,
        source: str,
        error: Any,
        blocked: Iterable[str],
        blocked_by: str = "",
    ) -> None:
        """统一删除台账回调（由 ``DownloaderAdapter.delete_torrents`` 调用）。

        只写一个文件：``deletions.jsonl``。每行一条 JSON。失败静默 —— 记账不能影响删种本身。
        ``blocked_by``：阻断原因分类（如 ``"gate_error"`` = 闸门缺失/异常触发的 fail-closed 全阻断）。
        """
        try:
            _path = self._deletions_log_path()
            if _path is None:
                return
            try:
                _path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:  # noqa: BLE001
                pass
            ts = _time.strftime("%Y-%m-%d %H:%M:%S")
            _src = str(source or "").strip() or self._delete_caller_source()
            _rsn = str(reason or "").strip()
            _err = str(error or "").strip()
            _bby = str(blocked_by or "").strip()
            title = ""
            rows = []
            _hs = [str(h or "").strip().lower() for h in (hashes or []) if str(h or "").strip()]
            _blk = [str(h or "").strip().lower() for h in (blocked or []) if str(h or "").strip()]
            # 标题/站点：顺带补上，方便直接读
            _meta = {}
            try:
                snap = self._tag_all_torrents() or {}
                ledger = dict(self._tag_state().items() or {})
                for h in set(_hs) | set(_blk):
                    t = snap.get(h)
                    if t is not None:
                        title = str(getattr(t, "title", "") or getattr(t, "name", "") or "")
                    rec = ledger.get(h) or {}
                    _meta[h] = {
                        "site": str(rec.get("site") or ""),
                        "title": title[:80],
                    }
            except Exception:  # noqa: BLE001
                pass
            for h in _hs:
                rows.append({
                    "ts": ts, "hash": h, "site": (_meta.get(h) or {}).get("site", ""),
                    "title": (_meta.get(h) or {}).get("title", ""),
                    "source": _src, "reason": _rsn, "delete_file": bool(delete_file),
                    "ok": True, "blocked": False, "err": _err, "blocked_by": _bby,
                })
            for h in _blk:
                rows.append({
                    "ts": ts, "hash": h, "site": (_meta.get(h) or {}).get("site", ""),
                    "title": (_meta.get(h) or {}).get("title", ""),
                    "source": _src, "reason": _rsn, "delete_file": bool(delete_file),
                    "ok": False, "blocked": True, "err": "", "blocked_by": _bby,
                })
            if rows:
                with open(_path, "a", encoding="utf-8") as f:
                    f.write("\n".join(_json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _delete_caller_source() -> str:
        """从调用栈推断删除来源 ``模块.函数``（调用方没传 source 时的兜底）。

        跳过 downloader_ops 自身与 threading 包装帧，取第一个「魔流插件内」的调用帧。
        """
        try:
            f = _sys._getframe(1)  # noqa: SLF001
            _skip = ("downloader_ops", "deletegate")
            while f is not None:
                mod = str(f.f_globals.get("__name__", ""))
                fn = str(f.f_code.co_name)
                if "magicflow" in mod and not any(s in mod for s in _skip):
                    short = mod.split("magicflow")[-1].lstrip(".")
                    return f"{short or 'magicflow'}.{fn}"
                f = f.f_back
        except Exception:  # noqa: BLE001
            pass
        return "unknown"


# ---------------------------------------------------------------------------
# 闸门故障注入自检（模块级；供离线测试与线上自检使用，**不新增任何写动作路由**）
# ---------------------------------------------------------------------------
def gate_self_test(owner) -> "Dict[str, Any]":
    """闸门「故障注入」自检：确认 ``owner._delete_gate_detail(..., force_error=True)``
    确实会抛异常 —— 据此可验证删除入口的 fail-closed 兜底是否真的拦得住。

    Args:
        owner: 插件实例（需带 DeleteGateMixin 的 ``_delete_gate_detail``）。

    Returns:
        ``{"ok": bool, "raised": str}``（ok=True 表示故障可被注入）。
    """
    detail = getattr(owner, "_delete_gate_detail", None)
    if not callable(detail):
        return {"ok": False, "raised": "", "reason": "owner 无 _delete_gate_detail"}
    try:
        detail(["__gate_self_test__"], force_error=True)
    except Exception as e:  # noqa: BLE001
        return {"ok": True, "raised": f"{type(e).__name__}: {e}"}
    return {"ok": False, "raised": "", "reason": "force_error 未触发异常"}
