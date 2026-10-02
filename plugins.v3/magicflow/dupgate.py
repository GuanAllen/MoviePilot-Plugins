# -*- coding: utf-8 -*-
"""魔流 · dupgate —— 全局（**跨任务**）资源「下载占用」闸门（公共模块）。

任何「往下载器加**新种**」的路径（刷流 / 跨站取种 / 换种 …）都应在落种前先经本模块
``claim`` 占用，成功登记 ``finish``、失败 ``release``，从源头保证：

    **同一资源（同一 infohash 或同一完整特征码）在插件内只被下载一次**，无论哪个任务发起。
    （落实 docs/MODEL.md「一个资源只从一个站下载」）

为什么需要它：各任务各自刷站、并发执行，「本机已有」检查在**并发**下会同时通过，
且「清理掉之后又下」会把同一资源反复拉回来。本闸门用**全插件共享**的占用表封住这两条路。

分工（避免重复实现）：
  · 真正存储 = ``persistence.AddGateStore``（冷备 ``add_gate.json`` / 热键 region ``addgate``）；
  · 取实例 = ``persistence.get_gate_store(data_dir, kv)``（**进程级单例**，跨热重载存活）；
  · 本模块只提供**统一入口** + 供各 mixin 复用的 :class:`DupGateMixin`，不重复写存储逻辑。

语义（三级身份，见 :func:`common.dup_gate_keys`）：
  · ① 同 infohash      → 冲突（复用/跳过，零下载）
  · ② 同完整特征码 fp  → 冲突（跨站辅种复用，零下载）
  · ③ 仅内层特征码同（打包/根目录名不同）→ **不算冲突**，允许下载（两侧都能刷）
"""

from typing import Any, Dict, List, Optional

from .common import ADD_GATE_DONE_TTL, ADD_GATE_INFLIGHT_TTL, dup_gate_keys
from .persistence import AddGateStore, get_gate_store

__all__ = [
    "gate_for",
    "keys_of",
    "DupGateMixin",
]


def gate_for(data_dir: Any, kv: Any = None) -> AddGateStore:
    """取/建全局闸门实例（进程级单例，见 ``persistence.get_gate_store``）。"""
    return get_gate_store(data_dir, kv)


def keys_of(info_hash: Any = None, fingerprint: Any = None) -> List[str]:
    """资源身份的去重键（``h:<infohash>`` / ``fp:<完整特征码>``，只取非空者）。"""
    return dup_gate_keys(info_hash, fingerprint)


class DupGateMixin:
    """给插件类用的便捷方法（``self._dup_claim(...)`` 等）。

    任何 mixin 都可直接调用；取不到闸门时一律「放行」（返回空/无操作），
    保证闸门故障**绝不**阻塞正常下载。
    """

    # ---------------------------------------------------------- 实例
    def _dup_gate(self) -> Optional[AddGateStore]:
        """取全局闸门（结果缓存到实例，避免每候选重复取；失败返回 None）。"""
        gate = getattr(self, "_gate_obj", None)
        if gate is not None:
            return gate
        try:
            gate = get_gate_store(self.get_data_path(), getattr(self, "_hot", None))
        except Exception:  # noqa: BLE001
            gate = None
        self._gate_obj = gate
        return gate

    def _dup_keys(self, info_hash: Any = None, fingerprint: Any = None) -> List[str]:
        """资源身份键（供调用方提前算好、claim/finish 复用）。"""
        return dup_gate_keys(info_hash, fingerprint)

    # ---------------------------------------------------------- 占用 / 释放
    def _dup_claim(self, task_id: str, *, keys: List[str]) -> List[str]:
        """尝试占用一批资源键（**全有或全无**）。

        Returns:
            被**别的任务**在 TTL 内占用/下过的冲突键列表；非空 = 未占用，调用方应放弃；
            空列表 = 已成功占用（正在下载中），或闸门不可用（放行）。
        """
        ks = [k for k in (keys or []) if k]
        if not ks:
            return []
        gate = self._dup_gate()
        if not gate:
            return []
        try:
            return gate.claim(ks, task_id, ADD_GATE_INFLIGHT_TTL, ADD_GATE_DONE_TTL)
        except Exception:  # noqa: BLE001
            return []

    def _dup_peek(self, task_id: str, *, keys: List[str]) -> List[str]:
        """只看冲突、不占用（用于提前跳过，避免占用下载槽/无效请求）。"""
        ks = [k for k in (keys or []) if k]
        if not ks:
            return []
        gate = self._dup_gate()
        if not gate:
            return []
        try:
            return gate.peek(ks, task_id, ADD_GATE_INFLIGHT_TTL, ADD_GATE_DONE_TTL)
        except Exception:  # noqa: BLE001
            return []

    def _dup_conflict_states(self, task_id: str, *, keys: List[str]) -> Dict[str, str]:
        """返回冲突键 → 状态（``inflight``/``done``）。

        用于区分「对方正在下（让位本轮，下轮本机有副本可辅种）」与「对方已下过（本机无副本 → 终局跳过）」。
        """
        ks = [k for k in (keys or []) if k]
        if not ks:
            return {}
        gate = self._dup_gate()
        if not gate:
            return {}
        try:
            return gate.conflict_states(ks, task_id, ADD_GATE_INFLIGHT_TTL, ADD_GATE_DONE_TTL)
        except Exception:  # noqa: BLE001
            return {}

    def _dup_finish(self, task_id: str, *, keys: List[str]) -> None:
        """标记下载**完成**（登记后续 ``ADD_GATE_DONE_TTL`` 内不再重复下载）。"""
        ks = [k for k in (keys or []) if k]
        if not ks:
            return
        gate = self._dup_gate()
        if not gate:
            return
        try:
            gate.finish(ks, task_id)
        except Exception:  # noqa: BLE001
            pass

    def _dup_release(self, task_id: str, *, keys: List[str]) -> None:
        """释放**本任务**尚未完成的占用（下载失败时调用，允许重试）。"""
        ks = [k for k in (keys or []) if k]
        if not ks:
            return
        gate = self._dup_gate()
        if not gate:
            return
        try:
            gate.release(ks, task_id)
        except Exception:  # noqa: BLE001
            pass
