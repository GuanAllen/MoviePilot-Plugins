"""
魔流 · 在线热层（走 MoviePilot 缓存适配器；JSON 文件作冷备份/权威副本）

Master 2026-09-27 09:16 定调：
  这是**开源插件**，不能假设用户装了 Redis、更不能假设他们会单独建库。
  所以**必须走 MoviePilot 自己的缓存配置**：
    · MP 配了 Redis → 我们拿到 `RedisBackend`，热层生效（增量写、不落盘、快）；
    · MP 没配 Redis（文件/内存后端）→ **判定"无热层"**，完全走原来的 JSON 文件（不重复写、行为不变）；
    · 用户想启用 → 在 MP 里改缓存配置 + 重载插件即可（我们不需要任何自己的 Redis 配置项）。

  · **JSON 文件 = 权威冷备份**：每 60s（脏了才写）+ 插件 stop 时落一次。
  · Redis 数据丢了（重启/清缓存/LRU 淘汰）→ 重载时从 JSON **回灌**热层。

为什么不用自建 Redis 连接：用户不一定有 Redis、也不一定愿意建库（Master 定）。
代价（认了）：走 MP 的 Redis 就得接受 MP 的 `maxmemory=256mb + allkeys-lru`（key 可能被淘汰）
和「清空缓存」的 `flushdb()` —— 所以**权威永远在 JSON 文件**，热层只是加速。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

REGION = "magicflow"
# 我们自己的 key 有效期（秒）：一年。JSON 文件才是权威，这里过期最多让热层回灌一次。
KEY_TTL = 365 * 24 * 60 * 60
# 逻辑名前缀（用于从 items() 里挑出属于某个 Store 的键）
_PREFIX = "mf:"
# ★ 跨热重载共享计数器（放独立模块，MP 清模块缓存时不会丢）
_SHARED_KEY = "__magicflow_shared__"


def _counters() -> Dict[str, Any]:
    """取跨热重载的共享计数器容器。"""
    import sys as _sys
    import types as _types

    mod = _sys.modules.get(_SHARED_KEY)
    if mod is None:
        mod = _types.ModuleType(_SHARED_KEY)
        _sys.modules[_SHARED_KEY] = mod
    for _attr, _factory in (("instances", dict), ("counters", dict), ("lock", threading.Lock)):
        if not hasattr(mod, _attr):
            setattr(mod, _attr, _factory())
    return mod.counters


class MpHotStore:
    """基于 MoviePilot 缓存适配器的热层（只在后端为 Redis 时启用）。"""

    def __init__(
        self,
        base: Any = None,
        log: Optional[Callable[[str, str], None]] = None,
        region: str = REGION,
    ) -> None:
        self.base = base
        self.region = str(region or REGION)
        self._log = log
        self._backend: Any = None
        self._resolved = False
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ 基础
    def _info(self, msg: str, level: str = "info") -> None:
        if self._log:
            try:
                self._log(msg, level)
            except Exception:  # noqa: BLE001
                pass

    def backend(self) -> Any:
        """懒建后端：MP 的 `FileCache` 会按 MP 配置返回 RedisBackend 或 FileBackend。"""
        with self._lock:
            if self._resolved:
                return self._backend
            self._resolved = True
            try:
                from app.sdk.cache import FileCache  # noqa: WPS433

                backend = FileCache(base=self.base, ttl=KEY_TTL) if self.base is not None else FileCache(ttl=KEY_TTL)
                self._backend = backend
            except Exception as err:  # noqa: BLE001
                self._backend = None
                self._info(f"热层不可用({err})，状态走 JSON 文件", "debug")
        return self._backend

    def is_redis(self) -> bool:
        backend = self.backend()
        if backend is None:
            return False
        try:
            probe = getattr(backend, "is_redis", None)
            return bool(probe()) if callable(probe) else False
        except Exception:  # noqa: BLE001
            return False

    def available(self) -> bool:
        """热层是否可用（**只有 MP 后端是 Redis 才算**；文件后端直接走 JSON）。"""
        return self.is_redis()

    def describe(self) -> str:
        backend = self.backend()
        name = type(backend).__name__ if backend is not None else "none"
        return f"{name}({'redis' if self.is_redis() else 'fallback-json'}) region={self.region}"

    # ------------------------------------------------------------- 键值操作
    @staticmethod
    def key(name: str) -> str:
        name = str(name or "").lstrip(":")
        return name if name.startswith(_PREFIX) else f"{_PREFIX}{name}"

    def get(self, name: str) -> Any:
        if not self.available():
            return None
        try:
            return self.backend().get(self.key(name), region=self.region)
        except Exception as err:  # noqa: BLE001
            self._info(f"热层读失败({err})，回退 JSON", "debug")
            return None

    def set(self, name: str, value: Any) -> bool:
        if not self.available():
            return False
        try:
            self.backend().set(self.key(name), value, ttl=KEY_TTL, region=self.region)
            self._writes = int(getattr(self, "_writes", 0)) + 1
            self._bump_writes()
            return True
        except Exception as err:  # noqa: BLE001
            self._info(f"热层写失败({err})，回退 JSON", "debug")
            return False

    def delete(self, name: str) -> bool:
        if not self.available():
            return False
        try:
            self.backend().delete(self.key(name), region=self.region)
            self._writes = int(getattr(self, "_writes", 0)) + 1
            self._bump_writes()
            return True
        except Exception as err:  # noqa: BLE001
            self._info(f"热层删失败({err})，回退 JSON", "debug")
            return False

    def _bump_writes(self) -> None:
        try:
            c = _counters()
            c["hot_writes"] = int(c.get("hot_writes", 0)) + 1
        except Exception:  # noqa: BLE001
            pass

    def writes(self) -> int:
        """累计热层写次数（即「老逻辑会落盘多少次」的等价量）。"""
        try:
            return int(_counters().get("hot_writes", 0) or 0)
        except Exception:  # noqa: BLE001
            return int(getattr(self, "_writes", 0) or 0)

    def items(self, prefix: str = "") -> Dict[str, Any]:
        """列出热层里我们自己的键值对：{逻辑名（不含 mf:）: 值}。"""
        if not self.available():
            return {}
        want = self.key(prefix) if prefix else _PREFIX
        out: Dict[str, Any] = {}
        try:
            rows = self.backend().items(region=self.region)
            for raw_key, value in rows or []:
                full = str(raw_key or "")
                # MP 不同后端可能带/不带 region 前缀，统一裁掉
                for prefix_head in (f"region:{self.region}:key:", f"{self.region}:", "region:"):
                    if full.startswith(prefix_head):
                        full = full[len(prefix_head):]
                        break
                if not full.startswith(want):
                    continue
                out[full[len(_PREFIX):] if full.startswith(_PREFIX) else full] = value
        except Exception as err:  # noqa: BLE001
            self._info(f"热层枚举失败({err})", "debug")
            return {}
        return out

    def count(self) -> int:
        return len(self.items())

    def stats(self, groups_ttl: float = 30.0) -> Dict[str, Any]:
        """热层概况。**键分布枚举开销大（每键一次 GET）→ 30s 缓存**，/status 高频轮询不会打 Redis。"""
        backend = self.backend()
        out: Dict[str, Any] = {
            "enabled": self.is_redis(),
            "backend": type(backend).__name__ if backend is not None else "none",
            "region": self.region,
            "keys": 0,
        }
        if not out["enabled"]:
            return out
        now = time.time()
        with self._lock:
            cached = getattr(self, "_stats_cache", None)
            cached_at = float(getattr(self, "_stats_at", 0.0) or 0.0)
            if cached and (now - cached_at) < max(groups_ttl, 1.0):
                return dict(cached)
        groups: Dict[str, int] = {}
        try:
            for name in self.items():
                head = str(name).split(":", 1)[0] or "other"
                groups[head] = groups.get(head, 0) + 1
        except Exception:  # noqa: BLE001
            pass
        out["groups"] = dict(sorted(groups.items(), key=lambda kv: -kv[1]))
        out["keys"] = sum(groups.values())
        out["hot_writes"] = self.writes()
        with self._lock:
            self._stats_cache = dict(out)
            self._stats_at = now
        return out

    def selftest(self) -> Dict[str, Any]:
        """自检：写/读/删一个临时键，把真实异常原样报出（诊断用）。"""
        out: Dict[str, Any] = {"redis": self.is_redis(), "backend": type(self.backend()).__name__}
        name = "selftest:probe"
        try:
            backend = self.backend()
            out["key"] = self.key(name)
            backend.set(self.key(name), {"t": time.time()}, ttl=KEY_TTL, region=self.region)
            out["get"] = backend.get(self.key(name), region=self.region)
            backend.delete(self.key(name), region=self.region)
            out["ok"] = True
        except Exception as err:  # noqa: BLE001
            out["ok"] = False
            out["error"] = f"{type(err).__name__}: {err}"
        try:
            rows = list(self.backend().items(region=self.region) or [])
            out["items_sample"] = [str(k) for k, _ in rows[:5]]
            out["items_count"] = len(rows)
        except Exception as err:  # noqa: BLE001
            out["items_error"] = f"{type(err).__name__}: {err}"
        return out

    def drop_all_own_keys(self) -> Dict[str, Any]:
        """只删我们自己的键（验证「热层丢了 → 从 JSON 回灌」）。"""
        if not self.available():
            return {"success": False, "message": "热层不可用（未启用 Redis）"}
        keys = list(self.items().keys())
        ok = True
        for name in keys:
            ok = self.delete(name) and ok
        return {"success": ok, "deleted": len(keys)}
