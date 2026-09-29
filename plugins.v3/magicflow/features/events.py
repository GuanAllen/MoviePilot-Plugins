# -*- coding: utf-8 -*-
"""魔流 · events —— 事件订阅（传输完成等，外部事件入口）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import time
from datetime import datetime
from typing import Any, List


from .. import common  # noqa: F401
from ..common import (
    _mf_eventmanager,
    _mf_on_event,
)


class EventsMixin:
    """events 功能集（原 MagicFlow 方法原样搬入）。"""

    @_mf_on_event("TransferComplete")
    def _on_transfer_complete(self, event: Any = None) -> None:
        """★ 整理完成 → 写「库记」。

        权威来源：MP 广播的 ``transfer.complete``（payload 带 ``download_hash`` 与
        ``transferinfo`` 最终路径/整理方式），**不靠路径猜目录**。
        """
        try:
            _ev0 = getattr(self, "_lib_events", None)
            if not isinstance(_ev0, dict):
                _ev0 = {}
            _ev0["received"] = int(_ev0.get("received") or 0) + 1
            _ev0["last_hash"] = str((getattr(event, "event_data", None) or {}).get("download_hash") or "")[:16]
            _ev0["last_ts"] = time.time()
            self._lib_events = _ev0
        except Exception:  # noqa: BLE001
            pass
        if not common._mf_active_is(self):
            try:
                self._log("库记:忽略整理完成事件(非活跃实例)")
            except Exception:  # noqa: BLE001
                pass
            return
        if not getattr(self, "_enabled", False):
            return
        try:
            data = getattr(event, "event_data", None) or {}
            h = str((data or {}).get("download_hash") or "").strip().lower()
            if not h:
                return
            ti = (data or {}).get("transferinfo")
            if ti is not None and not bool(getattr(ti, "success", True)):
                return
            item = getattr(ti, "target_diritem", None) or getattr(ti, "target_item", None)
            path = str(getattr(item, "path", "") or "")
            if not path:
                path = str(getattr((data or {}).get("fileitem"), "path", "") or "")
            mi = (data or {}).get("mediainfo")
            media_id = str(getattr(mi, "tmdb_id", "") or getattr(mi, "media_id", "") or "")
            ttype = str(getattr(ti, "transfer_type", "") or "")
            groups = self._tag_groups()
            gid = groups.queue_library(h, path=path, media_id=media_id)
            try:
                self._tag_state().set_asset(h, True, sub="资源")
            except Exception:  # noqa: BLE001
                pass
            if gid:
                self._log(f"库记:整理完成 {h[:12]} → 资源 {gid[:46]} 路径 {path or '-'} 方式 {ttype or '-'}")
                # ★ 入库即转「静默-资源」（不等下一轮分拣）
                try:
                    self._promote_resource(gid)
                except Exception as err:  # noqa: BLE001
                    self._log(f"库记:入库即转失败 {h[:12]}:{err}", "warning")
            else:
                self._log(f"库记:整理完成 {h[:12]} 尚未纳管,已记待办(路径 {path or '-'})")
        except Exception as err:  # noqa: BLE001
            self._log(f"库记:处理整理完成事件失败:{err}", "warning")

    @staticmethod
    def _event_handlers(etype: Any) -> List[Any]:
        """从事件总线内部取出某事件的订阅列表（诊断用，尽力而为）。"""
        em = _mf_eventmanager
        if em is None:
            return []
        cands = []
        for attr in ("_EventManager__dispatcher", "_dispatcher"):
            obj = getattr(em, attr, None)
            if obj is not None:
                cands.append(obj)
        cands.append(em)
        for obj in cands:
            for rattr in ("_registry", "registry", "_EventRegistry__registry"):
                reg = getattr(obj, rattr, None)
                if reg is None:
                    continue
                for m in ("broadcast_snapshot", "snapshot"):
                    fn = getattr(reg, m, None)
                    if callable(fn):
                        try:
                            return list(fn(etype))
                        except Exception:  # noqa: BLE001
                            continue
        return []
