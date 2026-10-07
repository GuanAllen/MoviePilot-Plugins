"""
MagicFlow qBittorrent 增量同步（``/api/v2/sync/maindata?rid=``）

背景（2026-10-07 实测）：qB 的 ``torrents_info()`` 每次返回**全量**——
本机 1368 条 ≈ 2.27MB / 0.51s，而插件每 20~30s 就要一份最新快照 → 绝大多数字节是重复的。
qB 原生提供增量接口：``GET /api/v2/sync/maindata?rid=<上次 rid>`` 只回**变化的条目**
（实测无关键字段变动时 ≈ 8~10KB / 0.03s，约省 250× 流量、20× 时间）。

本模块把「增量合并」做成**纯内存**的进程级单例：
  · **不写 Redis、不落盘**（Master 2026-10-07 12:19 定：「减少磁盘写入」）；
  · 走 ``persistence._shared()`` 注册表 → 热重载不丢（插件进程本来就不重启）；
  · 首次 / ``full_update`` / rid 回退（qB 重启）→ 全量建表；
    否则把 delta 合并进内存表 + ``torrents_removed`` 删除；
  · **任何异常都返回 None** → 调用方回退到原来的全量拉取（fail-open，行为不变）。

注意：增量 payload 里的 torrent 行**只有变化的字段**，且没有 ``hash`` 字段（它是字典键），
所以建表时把 ``hash`` 注入每一行，返回的仍是「字段齐全的全量行」——对上层完全透明。
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional

from .persistence import _shared

# 总开关：False = 完全回退到旧的全量 ``torrents_info()``（用于排障 / 一键回滚）
QB_SYNC_INCREMENTAL = True

# 单例注册键前缀（挂在 persistence._shared().singletons 上）
_KEY_PREFIX = "qbsync::"


class QbSyncStore:
    """qB 增量快照（纯内存，进程级单例）。"""

    def __init__(self, name: str = "qbittorrent"):
        self.name = str(name or "qbittorrent")
        self._lock = threading.Lock()
        self._rid: Optional[int] = None
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._views: List[Dict[str, Any]] = []  # 返回用的列表缓存（成员变动才重建）
        self._server_state: Dict[str, Any] = {}
        self._stats: Dict[str, Any] = {
            "full_pulls": 0,
            "delta_pulls": 0,
            "unchanged_pulls": 0,
            "errors": 0,
            "last_delta_n": 0,
            "last_delta_bytes": 0,
            "last_at": 0.0,
            "last_full_at": 0.0,
            "last_error": "",
        }

    # ------------------------------------------------------------------ 观测
    def stats(self) -> Dict[str, Any]:
        """只读观测（给 ``/agent/qb/snapshot``）：全量/增量/无变化次数 + 上次增量规模。"""
        with self._lock:
            now = time.time()
            out: Dict[str, Any] = {
                "downloader": self.name,
                "rid": self._rid,
                "torrents": len(self._rows),
                "server_state_keys": sorted(self._server_state.keys()),
            }
            out.update(
                {
                    "full_pulls": self._stats["full_pulls"],
                    "delta_pulls": self._stats["delta_pulls"],
                    "unchanged_pulls": self._stats["unchanged_pulls"],
                    "errors": self._stats["errors"],
                    "last_delta_n": self._stats["last_delta_n"],
                    "last_delta_bytes": self._stats["last_delta_bytes"],
                    "age_s": (round(now - self._stats["last_at"], 1) if self._stats["last_at"] else None),
                }
            )
            if self._stats["last_full_at"]:
                out["last_full_age_s"] = round(now - self._stats["last_full_at"], 1)
            if self._stats["last_error"]:
                out["last_error"] = self._stats["last_error"]
            return out

    # ------------------------------------------------------------------ 拉取
    def torrents(self, qbc: Any, force: bool = False) -> Optional[List[Dict[str, Any]]]:
        """拉一次（增量优先），返回**字段齐全的全量种子行**（每行含 ``hash``）。

        返回 ``None`` = 本次拿不到（调用方应回退到旧的全量拉取）。
        """
        if qbc is None:
            return None
        fn = getattr(qbc, "sync_maindata", None)
        if not callable(fn):
            return None
        with self._lock:
            rid = 0 if (force or self._rid is None) else self._rid
            try:
                md = fn(rid=rid)
            except Exception as err:  # noqa: BLE001
                self._stats["errors"] += 1
                self._stats["last_error"] = f"sync_maindata 失败:{err}"
                return None
            if not isinstance(md, dict):
                self._stats["errors"] += 1
                self._stats["last_error"] = "sync_maindata 返回非 dict"
                return None

            new_rid = md.get("rid")
            delta = md.get("torrents") or {}
            # rid 回退（qB 重启）/ full_update / 首次 → 全量重建
            full = bool(md.get("full_update")) or self._rid is None or (
                isinstance(new_rid, int) and isinstance(self._rid, int) and new_rid <= self._rid
            )
            now = time.time()
            if full:
                rows: Dict[str, Dict[str, Any]] = {}
                for h, row in delta.items():
                    if not isinstance(row, dict):
                        continue
                    key = str(h).lower()
                    row["hash"] = key
                    rows[key] = row
                self._rows = rows
                self._views = list(rows.values())
                self._stats["full_pulls"] += 1
                self._stats["last_full_at"] = now
            elif delta or md.get("torrents_removed"):
                rebuilt = False
                for h, patch in delta.items():
                    if not isinstance(patch, dict):
                        continue
                    key = str(h).lower()
                    row = self._rows.get(key)
                    if row is None:
                        patch["hash"] = key
                        self._rows[key] = patch
                        rebuilt = True
                    else:
                        row.update(patch)
                for h in md.get("torrents_removed") or []:
                    if self._rows.pop(str(h).lower(), None) is not None:
                        rebuilt = True
                if rebuilt:
                    self._views = list(self._rows.values())
                self._stats["delta_pulls"] += 1
            else:
                # rid 前进但没有任何 torrent 变化 → 连列表都不用重建
                self._stats["unchanged_pulls"] += 1

            if isinstance(new_rid, int):
                self._rid = new_rid
            st = md.get("server_state")
            if isinstance(st, dict):
                self._server_state.update(st)
            self._stats["last_at"] = now
            self._stats["last_delta_n"] = len(delta) if isinstance(delta, dict) else 0
            if not full:
                try:
                    self._stats["last_delta_bytes"] = len(json.dumps(md, default=str))
                except Exception:  # noqa: BLE001
                    self._stats["last_delta_bytes"] = 0
            self._stats["last_error"] = ""
            return list(self._views)


def get_qb_sync_store(name: str = "qbittorrent") -> QbSyncStore:
    """取/建 qB 增量快照单例（按下载器名；走 ``persistence._shared()`` → 热重载不丢）。"""
    key = _KEY_PREFIX + str(name or "qbittorrent")
    sh = _shared()
    with sh.lock:
        store = sh.singletons.get(key)
        if store is None:
            store = QbSyncStore(name)
            sh.singletons[key] = store
    return store
