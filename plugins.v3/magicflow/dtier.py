"""魔流 · 数据分层（3.7.1）。

三层职责，一次说清「什么进库、什么进缓存、什么只留内存」：

  ┌ 持久层  durable() / save_data / get_data
  │   落在 MP 的 ``PluginData`` 表（JSON 列）。装了 PG 就进 PG，否则 SQLite。
  │   放「权威状态 / 要查的历史」：PV 账本、站点 PV 封禁、公式静态参数、任务游标。
  │   随卸载保留、重装继承（MP 卸载只停用不删行；数据目录也不动）。
  │
  ├ 缓存层  TierCache
  │   ``FileCache``（配了 Redis 走 Redis，没有落文件）+ 进程内存热层。值 JSON 编码、自带 ts。
  │   放「可重取的副本」：候选列表、站点实时值……丢了最多多抓一次，绝不影响正确性。
  │
  └ 进程态  锁 / 单飞 / 快照
      只留内存，不进任何持久层（热重载会重建，本来也只是瞬时协调用）。

铁律：
  1. 缓存的 miss 永远等于「再抓一次」，绝不等于「功能坏」。
  2. 不缓存空/失败结果（否则自己把自己冻住）。
  3. 无 Redis / 无 PG 也照跑：FileCache 工厂缺失自动退化纯内存，save_data 由 MP 兜底。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Callable, Dict, Optional


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


# ============================================================
# 持久层：PV 账本
# ============================================================

class PvLedger:
    """站点 PV（页面访问）账本：按「天 / 站点 / 类型」累计，落 save_data。

    kind：browse（列表抓取）/ live（实时数据）/ formula（魔力公式）/ signin（签到）/ other。
    用途：① 看「每站每天耗了多少 PV」；② 抓取前查预算，超了就不再打站点（主动限流）。
    """

    def __init__(
        self,
        getter: Callable[[str], Any],
        setter: Callable[[str, Any], None],
        key: str = "pv_usage",
        keep_days: int = 21,
    ) -> None:
        self._get = getter or _noop
        self._set = setter or _noop
        self._key = str(key)
        self._keep_days = max(int(keep_days), 2)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def today(now: Optional[float] = None) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(now if now is not None else time.time()))

    def _load(self) -> Dict[str, Any]:
        try:
            data = self._get(self._key)
        except Exception:  # noqa: BLE001
            data = None
        return dict(data) if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ 写入
    def bump(self, site_id: Any, kind: str = "other", n: int = 1) -> int:
        """记 n 次站点请求，返回该站点**今日累计**（含本次）。"""
        sid = str(int(site_id or 0))
        kind = str(kind or "other")
        inc = max(int(n or 1), 1)
        day = self.today()
        with self._lock:
            data = self._load()
            bucket = data.get(day)
            if not isinstance(bucket, dict):
                bucket = {}
                data[day] = bucket
            site = bucket.get(sid)
            if not isinstance(site, dict):
                site = {}
                bucket[sid] = site
            site[kind] = int(site.get(kind, 0) or 0) + inc
            # 只保留最近 N 天，防无界增长
            if len(data) > self._keep_days:
                for stale in sorted(data.keys())[: len(data) - self._keep_days]:
                    data.pop(stale, None)
            try:
                self._set(self._key, data)
            except Exception:  # noqa: BLE001
                pass
            return int(sum(int(v or 0) for v in site.values()))

    # ------------------------------------------------------------------ 读取
    def today_total(self, site_id: Any) -> int:
        sid = str(int(site_id or 0))
        site = (self._load().get(self.today()) or {}).get(sid)
        if not isinstance(site, dict):
            return 0
        return int(sum(int(v or 0) for v in site.values()))

    def today_kind(self, site_id: Any, kind: str = "other") -> int:
        """某站点今日**某类型**的累计次数（用于「单站单类日上限」，如取种 crossseed）。"""
        sid = str(int(site_id or 0))
        site = (self._load().get(self.today()) or {}).get(sid)
        if not isinstance(site, dict):
            return 0
        return int(site.get(str(kind or "other"), 0) or 0)

    def snapshot(self, days: int = 7, name_of: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
        """返回最近若干天的账本快照，供 `/pv` 端点与看板使用。"""
        data = self._load()
        keep = sorted(data.keys())[-max(int(days), 1):]
        rows = []
        totals: Dict[str, int] = {}
        for day in keep:
            bucket = data.get(day) or {}
            site_rows: Dict[str, Any] = {}
            for sid, kinds in bucket.items():
                if not isinstance(kinds, dict):
                    continue
                total = int(sum(int(v or 0) for v in kinds.values()))
                site_rows[sid] = {
                    "name": (name_of(sid) if name_of else sid),
                    "total": total,
                    "kinds": {k: int(v or 0) for k, v in kinds.items()},
                }
                totals[sid] = totals.get(sid, 0) + total
            rows.append({"day": day, "sites": site_rows})
        return {"days": rows, "totals": totals, "today": self.today()}


# ============================================================
# 缓存层：内存热层 + FileCache 冷层
# ============================================================

class TierCache:
    """内存热层 + ``FileCache`` 冷层（Redis→文件），值 JSON 编码、自带 ts 判 TTL。

    - ``encode`` / ``decode``：可选的编解码器（把领域对象 ↔ 可 JSON 化的数据）。
    - 冷层 key 用 sha1 哈希，避免原 key 里的 ``|`` 等字符落成奇怪文件名；原文 key 存在信封里。
    - 文件后端没有原生 TTL，读出时按信封里的 ``ts`` 判过期；Redis 后端额外带 ttl。
    """

    def __init__(
        self,
        region: str,
        base: Optional[Any] = None,
        encode: Optional[Callable[[Any], Any]] = None,
        decode: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        self.region = str(region)
        self._hot: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._encode = encode
        self._decode = decode
        self._backend: Any = None
        try:
            from app.sdk.cache import FileCache  # noqa: WPS433

            self._backend = FileCache(base=base) if base is not None else FileCache()
        except Exception:  # noqa: BLE001  工厂缺失 / 无后端 → 退化纯内存
            self._backend = None

    # ------------------------------------------------------------------ 冷层
    @staticmethod
    def _fname(key: str) -> str:
        return hashlib.sha1(str(key).encode("utf-8")).hexdigest()

    def _cold_get(self, key: str) -> Optional[Dict[str, Any]]:
        if self._backend is None:
            return None
        try:
            raw = self._backend.get(self._fname(key), region=self.region)
        except Exception:  # noqa: BLE001
            return None
        if not raw:
            return None
        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8")
            env = json.loads(raw)
        except Exception:  # noqa: BLE001
            return None
        return env if isinstance(env, dict) else None

    def _cold_set(self, key: str, env: Dict[str, Any], ttl: Optional[float]) -> None:
        if self._backend is None:
            return
        try:
            body = json.dumps(env, ensure_ascii=False, default=str).encode("utf-8")
            ttl_int = int(ttl) if ttl and ttl > 0 else None
            try:
                if ttl_int:
                    self._backend.set(self._fname(key), body, region=self.region, ttl=ttl_int)
                else:
                    self._backend.set(self._fname(key), body, region=self.region)
            except TypeError:
                self._backend.set(self._fname(key), body, region=self.region)
        except Exception:  # noqa: BLE001
            pass

    def _cold_delete(self, key: str) -> None:
        if self._backend is None:
            return
        try:
            self._backend.delete(self._fname(key), region=self.region)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 公开
    def get(self, key: str, ttl: float) -> Any:
        """命中返回解码后的值；未命中/已过期返回 ``None``。"""
        key = str(key)
        now = time.time()
        with self._lock:
            hot = self._hot.get(key)
        if hot is not None and (now - float(hot.get("ts", 0.0))) < ttl:
            return self._decode(hot.get("v")) if self._decode else hot.get("v")
        env = self._cold_get(key)
        if env is not None and (now - float(env.get("ts", 0.0))) < ttl:
            val = env.get("v")
            with self._lock:
                self._hot[key] = {"ts": float(env.get("ts", now)), "v": val}
            return self._decode(val) if self._decode else val
        return None

    def age(self, key: str) -> Optional[float]:
        """返回该键的年龄（秒）；不存在返回 None（不受 TTL 限制）。"""
        key = str(key)
        with self._lock:
            hot = self._hot.get(key)
        env = hot if hot is not None else self._cold_get(key)
        if env is None:
            return None
        try:
            return max(0.0, time.time() - float(env.get("ts", 0.0)))
        except (TypeError, ValueError):
            return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        key = str(key)
        enc = self._encode(value) if self._encode else value
        env = {"ts": time.time(), "v": enc}
        with self._lock:
            self._hot[key] = env
        self._cold_set(key, env, ttl)

    def delete(self, key: str) -> None:
        key = str(key)
        with self._lock:
            self._hot.pop(key, None)
        self._cold_delete(key)

    def clear_hot(self) -> None:
        """只清内存热层（热重载后调用可强制回源冷层）。"""
        with self._lock:
            self._hot.clear()
