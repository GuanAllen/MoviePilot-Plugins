# -*- coding: utf-8 -*-
"""魔流 · cacheops —— 进程内缓存的**惯用法**（信封 / 过期判定 / 有界容器 / 冷却）。

★ 本模块**不是**缓存底座：要跨热重载存活、且值可 JSON 化的，走 ``dtier.TierCache``
  （内存热层 + FileCache/Redis 冷层）。这里只收「重算便宜的派生值」—— 不序列化、
  不落盘、不进 Redis，见 ``docs/ADR-0001-cacheops.md``。

为什么需要它（2026-10-29 实测）
------------------------------
仓库里有 30 个 mixin 手写缓存（``self._x_cache`` + 时间戳）与 5 个模块级缓存，语义只有
三种（值缓存 / stale-while-revalidate / 冷却），惯用法却有五种（``{"ts":…,"v":…}`` /
``(ts, val)`` / 值与时间戳分两个属性 / 信封里带校验键 / 裸值 + None），过期判定被
**手写 23 处** —— 改一处漏一处；另有 **9 处手写单飞锁**（防并发重复回源，写法各不相同）。
本模块把前者收敛成一个信封 + 三个入口；后者按「并发单位」分成四个容器：

· ``KeyLocks`` —— 按 key 发锁（每个站点/URL 各跑各的）；
· ``SingleFlight`` —— 缓存 + 按 key 单飞（回源贵、并发会打爆）；
· ``Solo`` —— 全局单锁（同一时刻全库只该跑一个，可阻塞也可「抢不到就跳过」）；
· ``Inflight`` —— 在飞名额（丢给后台线程前先占位，重入直接跳过，不等结果）。

跨热重载存活的锁不在本模块：见 ``shared.lock(name)``（槽在 ``__magicflow_shared__``，
热重载换实例也管得住旧实例的线程）。

判据（ADR-0001）
----------------
重算成本 ≫ 序列化成本 → TierCache 冷层；否则 → 这里（内存、有界、可枚举）。
反例（千万别搬进冷层的）：``_tag_snapshot_cache`` 装 ``Dict[str, List[TorrentInfo]]``，
不可序列化，``json.dumps(default=str)`` 会把它静默变成字符串 repr —— 语法全绿、业务静默变错。

边界
----
· 只 import 标准库，不 import ``features.*``、不 import ``app.*``（L0，可离线加载）；
· 本模块不持有业务状态：容器由调用方持有（挂 ``self`` 或模块级都行）；
· 容器创建时登记进模块级注册表，供 ``runtime.cache_status()`` 枚举（阶段二接入）。
"""
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

# 注册表：name -> 容器（同名后者覆盖，用于诊断，不参与业务逻辑）
_REGISTRY: "OrderedDict[str, Any]" = OrderedDict()


def entry(value: Any, key: Optional[Any] = None, ts: Optional[float] = None) -> Dict[str, Any]:
    """造一个缓存信封 ``{"ts": 时刻, "v": 值, "key": 可选校验键}``。

    ``key`` 用于「入参变了就该重算」：调用方把影响结果的入参拼成字符串传进来，
    ``fresh`` 会同时校验它（``tags._asset_hist_cache`` 就是这么用的）。
    """
    env: Dict[str, Any] = {"ts": float(ts if ts is not None else time.time()), "v": value}
    if key is not None:
        env["key"] = str(key)
    return env


def fresh(env: Any, ttl: float, key: Optional[Any] = None, now: Optional[float] = None) -> bool:
    """信封是否新鲜：未过期；传了 ``key`` 还要求 key 与信封里的一致。"""
    if not isinstance(env, dict):
        return False
    if key is not None and str(env.get("key")) != str(key):
        return False
    stamp = float(env.get("ts", 0.0) or 0.0)
    return (float(now if now is not None else time.time()) - stamp) < float(ttl)


def value(env: Any, ttl: float, key: Optional[Any] = None,
          default: Any = None, now: Optional[float] = None) -> Any:
    """信封新鲜就取值，否则回 ``default``（不回源、不抛异常）。"""
    if fresh(env, ttl, key=key, now=now):
        return env.get("v")
    return default


class TTLCache:
    """有界 TTL 内存容器：LRU 淘汰（超 max 丢最旧）+ 可选 stale 宽限。

    给「重算便宜但调用频繁」的派生值用（统计汇总、owed 集合、uid 映射…）。
    要跨热重载存活的别放这里 —— 用 ``dtier.TierCache``。
    """

    def __init__(self, name: str, ttl: float = 60.0, max_entries: int = 256,
                 stale_max: Optional[float] = None) -> None:
        self.name = str(name)
        self.ttl = float(ttl)
        self.max_entries = max(int(max_entries), 1)
        self.stale_max = float(stale_max) if stale_max else None
        self._data: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        _REGISTRY[self.name] = self

    # ------------------------------------------------------------------ 读
    def get(self, key: Any, ttl: Optional[float] = None) -> Any:
        """命中且新鲜 → 值；否则 ``None``（不回源，调用方自己算）。"""
        val, ok = self.peek(key, ttl=ttl)
        return val if ok else None

    def peek(self, key: Any, ttl: Optional[float] = None) -> Tuple[Any, bool]:
        """返回 ``(值, 是否新鲜)``：陈旧但落在 ``stale_max`` 宽限内也返回值。

        stale-while-revalidate 用：先把旧值给前端，同时后台重算。没配 ``stale_max``
        时行为同 ``get``（过期即视为未命中）。
        """
        k = str(key)
        limit = float(ttl) if ttl is not None else self.ttl
        with self._lock:
            env = self._data.get(k)
            if env is None:
                return None, False
            if fresh(env, limit):
                self._data.move_to_end(k)
                return env.get("v"), True
            if self.stale_max is not None and fresh(env, self.stale_max):
                self._data.move_to_end(k)
                return env.get("v"), False
        return None, False

    # ------------------------------------------------------------------ 写
    def set(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        """写入并顺带淘汰：超 ``max_entries`` 丢最旧的几条（防无界增长）。"""
        k = str(key)
        with self._lock:
            self._data[k] = entry(value)
            self._data.move_to_end(k)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def invalidate(self, key: Optional[Any] = None) -> None:
        """失效某个键；不传键则整容器清空（结构性变更后调用）。"""
        with self._lock:
            if key is None:
                self._data.clear()
            else:
                self._data.pop(str(key), None)

    # ------------------------------------------------------------------ 诊断
    def stats(self) -> Dict[str, Any]:
        """当前规模与最旧条目年龄（秒），供 ``cache_status`` 枚举。"""
        with self._lock:
            n = len(self._data)
            oldest: Optional[float] = None
            if n:
                first = next(iter(self._data.values()))
                oldest = max(0.0, time.time() - float(first.get("ts", 0.0) or 0.0))
        return {"name": self.name, "kind": "ttl", "n": n, "max": self.max_entries,
                "ttl": self.ttl, "oldest_sec": oldest}


class KeyLocks:
    """按 key 分发锁（单飞用），**有界**：超上限只丢「最久未用且当前没人持有」的。

    为什么要它（**不是在修已发生的泄漏**）：实测两处手写版（``brush._fetch_site_candidates``
    / ``claim._claim_state_refresh``）目前都没真的溢出 —— brush 的三个调用点都传
    ``start_page=0``，key 只按「站点 × 变体 × pages」分，本来就有界。收它的理由是：
      ① 「有上限 + 只丢空闲锁」只实现一份，六个单飞点不用各写各的；
      ② 手写版换成容器后要防**热重载残留的旧裸 dict**：``dict.get()`` 返回 ``None``，
         接着 ``with None:`` 就是 TypeError。有类型判定可依赖，比 ``is None`` 稳。

    只管「发锁」，**不管缓存**：调用方自己决定是 ``with lock``（阻塞等同键结果），还是
    ``acquire(blocking=False)``（抢不到就跳过，如 ``claim`` 的后台刷新）。

    ★ **不登记进 ``_REGISTRY``**：那张表是「缓存位清单」，锁表不是缓存位（单飞容器的
      锁数已经由 ``SingleFlight.stats()['locks']`` 报出来了）。
    """

    def __init__(self, name: str, max_entries: int = 256) -> None:
        self.name = str(name)
        self.max_entries = max(int(max_entries), 1)
        self._locks: "OrderedDict[str, threading.Lock]" = OrderedDict()
        self._guard = threading.Lock()

    def get(self, key: Any) -> threading.Lock:
        """取该键的锁（没有就建）；新建时顺手把最久未用的**空闲**锁清掉。"""
        k = str(key)
        with self._guard:
            lk = self._locks.get(k)
            if lk is not None:
                self._locks.move_to_end(k)
                return lk
            lk = threading.Lock()
            self._locks[k] = lk
            self._prune_locked(keep=k)      # ★ 别把刚建出来这把当「空闲」删掉
            return lk

    def _prune_locked(self, keep: Optional[str] = None) -> None:
        """裁到上限内，保证不会削掉 ``keep`` 这一把。

        ★ 只丢 ``locked() == False`` 的：把一把正被持有的锁从表里删掉，下一个同键线程
          会造出**第二把锁** → 两把同时放行 → 单飞失效（比无界增长糟得多）。
        ★ 刚建出来那把必须显式排除：它此刻也 ``locked() == False``，按「空闲」筛就会被
          自己删掉 —— 于是本次返回的锁不在表里，下一次同键又造一把，同样破单飞。
        两者叠加的兜底：全都在用/都是新建时，宁可暂时超上限，下次 ``get`` 再裁。
        """
        if len(self._locks) <= self.max_entries:
            return
        for k in [x for x, lk in self._locks.items()
                  if not lk.locked() and x != keep]:
            if len(self._locks) <= self.max_entries:
                return
            self._locks.pop(k, None)

    def drop(self, key: Any) -> None:
        """丢掉某键的锁（对应缓存已被淘汰时用）；正被持有的不丢。"""
        with self._guard:
            k = str(key)
            lk = self._locks.get(k)
            if lk is not None and not lk.locked():
                self._locks.pop(k, None)

    def stats(self) -> Dict[str, Any]:
        """当前锁数量与上限，供诊断（锁表不参与业务判定）。"""
        with self._guard:
            n = len(self._locks)
        return {"name": self.name, "kind": "locks", "n": n, "max": self.max_entries}


class Solo:
    """全局单锁：**同一时刻只允许一个执行者**，不按 key 分（对比 ``KeyLocks``）。

    三种用法，看你要哪种语义：
      · ``with solo:``          —— 阻塞排队，前一个跑完才轮到你（跨站检索、刷标签）
      · ``solo.try_enter()``    —— 抢不到立刻返回 ``False``（"已在跑了，本轮跳过"，如签到）
        拿到 ``True`` 后**必须** ``solo.leave()``（放 ``finally`` 里）

    ★ 与 ``KeyLocks`` 的选择标准：**并发单位是「整件事」还是「某个人」**。
      同一时刻全库只该跑一个 → 这里；每个站点/URL 各跑各的 → ``KeyLocks``。
      「抢不到就跳过」但又不按 key 分的（签到、规则探测）用 ``try_enter``。
    ★ 与 ``Inflight`` 的区别：这里给的是**锁**（可阻塞等），那里给的是**名额**
      （只有抢/让，没有等）。同一 key 要「等前一个的结果」就用锁，要「别重复起」用名额。

    ★ **不登记进 ``_REGISTRY``**：锁不是缓存位（同 ``KeyLocks``）。
    ★ 实例级的别指望跨热重载 —— 热重载换实例就换锁。要跨重载存活，锁从
      ``shared.lock(name)`` 取来再塞进来（``Solo(name, lock=shared.lock(name))``）。
    """

    def __init__(self, name: str, lock: Optional[Any] = None) -> None:
        self.name = str(name)
        # 允许外部塞一把共享锁进来（跨热重载场景：shared.lock(name)）
        self._lock = lock if lock is not None else threading.Lock()

    def __enter__(self) -> "Solo":
        self._lock.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self._lock.release()
        return False

    def try_enter(self) -> bool:
        """非阻塞抢锁：抢到 ``True``（用完要 ``leave()``），已被占 ``False``。"""
        return bool(self._lock.acquire(blocking=False))

    def leave(self) -> None:
        """归还 ``try_enter`` 抢到的锁；已释放时重复调用不抛异常（``finally`` 友好）。"""
        try:
            self._lock.release()
        except Exception:  # noqa: BLE001
            pass

    @property
    def busy(self) -> bool:
        """当前是否有人持有（只用于诊断/日志，别拿它做并发判定——判完到动手之间会被抢走）。"""
        return bool(self._lock.locked())

    def stats(self) -> Dict[str, Any]:
        """当前是否被占用，供诊断。"""
        return {"name": self.name, "kind": "solo", "busy": self.busy}


class Inflight:
    """在飞集合：同一 key 同时只允许一个执行者，**抢不到立刻返回、不等结果**。

    语义是「**名额**」而不是「锁」（对比 ``Solo`` / ``KeyLocks``）：典型场景是
    「先记上我要去抓这个域名，然后丢给后台线程」，重入就直接跳过 ——
    调用方不需要（也不能）等前一个的结果。

    用法（**必须** try/finally 配对，否则这个 key 永远进不去）::

        if not box.try_enter(domain):
            return                      # 已经在飞了
        try:
            do_the_work()
        finally:
            box.leave(domain)

    ★ 满了（超 ``max_entries``）**只拒绝新进入，绝不淘汰在飞的**：淘汰一个在飞的 key
      会让后来的同名任务再起一份，正是这个容器要防的重复。
    ★ 不登记进 ``_REGISTRY``（名额表不是缓存位）。
    """

    def __init__(self, name: str, max_entries: int = 512) -> None:
        self.name = str(name)
        self.max_entries = max(int(max_entries), 1)
        self._flying: "OrderedDict[str, float]" = OrderedDict()   # key -> 进入时刻
        self._guard = threading.Lock()

    def try_enter(self, key: Any) -> bool:
        """占一个名额：拿到 ``True``，该 key 已在飞或名额已满 ``False``。"""
        k = str(key)
        with self._guard:
            if k in self._flying:
                return False
            if len(self._flying) >= self.max_entries:
                return False          # 满了只拒绝，不淘汰在飞的（同键重复比排队更糟）
            self._flying[k] = time.time()
            return True

    def leave(self, key: Any) -> None:
        """让出名额；没占过也不抛（后台线程 ``finally`` 里可以无脑调）。"""
        with self._guard:
            self._flying.pop(str(key), None)

    def has(self, key: Any) -> bool:
        """该 key 是否在飞（诊断/日志用；判完到动手之间状态会变，别拿它做并发判定）。"""
        with self._guard:
            return str(key) in self._flying

    def keys(self) -> List[str]:
        """当前在飞的 key 列表（诊断用，最多报 32 个）。"""
        with self._guard:
            return list(self._flying)[:32]

    def stats(self) -> Dict[str, Any]:
        """在飞数量与上限，供诊断。"""
        with self._guard:
            n = len(self._flying)
        return {"name": self.name, "kind": "inflight", "n": n, "max": self.max_entries}


class SingleFlight:
    """单飞容器：TTL 信封 + **每键一把锁**，过期瞬间同键并发只回源一次。

    与 ``TTLCache`` 的分工：那是「有界 + LRU」，解决**容量**；这是「回源贵且并发会打爆」，
    解决**惊群**——缓存过期的那一瞬，N 个线程同时发现未命中，若各算一份就是 N 倍重复
    劳动（``hr._hr_owed_by_site`` 曾有 9 个统计线程各算一遍）。

    流程：快路径读信封 → 未命中才取该键的锁 → 拿到锁后**再查一次**（前一个线程可能
    刚算完）→ 仍未命中才真回源 → 写回信封。

    边界
    ----
    · **只覆盖阻塞语义**：回源期间同键的其他线程在锁上等着，拿到的是新值。
      要「过期先返回旧值 + 后台线程补齐」的（stale-while-revalidate，如
      ``tags._tag_snapshot_view`` / ``formula`` 的后台抓取）**别用这里**——
      那需要线程池，语义不同。
    · ``compute`` 抛异常时**不写缓存**，异常照常向外抛（下次还能重试，不会把失败固化）。
    · 不要在 ``compute`` 里回调**同一容器的同一键**：锁不可重入，会自锁。
    """

    def __init__(self, name: str, ttl: float = 60.0, max_entries: int = 64,
                 stale_max: Optional[float] = None) -> None:
        self.name = str(name)
        self.ttl = float(ttl)
        self.max_entries = max(int(max_entries), 1)
        # 过期后仍可「先给旧值」的宽限（见 peek）；None = 过期即未命中
        self.stale_max = float(stale_max) if stale_max else None
        self._data: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        # 锁表复用 KeyLocks —— 「有界 + 只丢空闲锁」只写一份，别在这类里再抄一遍
        self._keys = KeyLocks(self.name + "#locks", max_entries=self.max_entries)
        # 只保护 _data 的结构（回源本身在它外面，避免把不同键串行化）
        self._guard = threading.Lock()
        _REGISTRY[self.name] = self

    def _lock_of(self, k: str) -> threading.Lock:
        """取该键的锁；锁表的有界回收由 ``KeyLocks`` 负责。"""
        return self._keys.get(k)

    # ------------------------------------------------------------------ 读
    def get(self, key: Any, ttl: Optional[float] = None) -> Any:
        """新鲜就返回值，否则 ``None``（不回源、不阻塞、不抛异常）。"""
        limit = float(ttl) if ttl is not None else self.ttl
        with self._guard:
            env = self._data.get(str(key))
        return value(env, limit)

    def peek(self, key: Any, ttl: Optional[float] = None,
             stale_max: Optional[float] = None) -> Tuple[Any, bool]:
        """返回 ``(值, 是否新鲜)``：陈旧但落在 ``stale_max`` 宽限内也把旧值交出来。

        给 stale-while-revalidate 用（``tags._tag_snapshot_view``）：容器只管
        「值 + 单飞」，**后台刷新线程仍由调用方起**——容器不碰线程池；
        调用方拿到 ``fresh=False`` 时自己决定是阻塞重算还是先回旧值 + 异步补。
        """
        limit = float(ttl) if ttl is not None else self.ttl
        grace = float(stale_max) if stale_max is not None else self.stale_max
        with self._guard:
            env = self._data.get(str(key))
        if not isinstance(env, dict):
            return None, False
        if fresh(env, limit):
            return env.get("v"), True
        if grace is not None and fresh(env, grace):
            return env.get("v"), False
        return None, False

    def run(self, key: Any, compute: Any, ttl: Optional[float] = None) -> Any:
        """新鲜 → 直接返回；过期 → 同键单飞回源一次，其余线程等这次的结果。

        ``compute`` 无参可调用对象，返回值即新值（回源期间**持有该键的锁**）。
        """
        k = str(key)
        limit = float(ttl) if ttl is not None else self.ttl
        with self._guard:
            env = self._data.get(k)
        if fresh(env, limit):                       # ① 快路径：新鲜直接返回
            return env.get("v")
        with self._lock_of(k):                      # ② 同键串行
            with self._guard:
                env = self._data.get(k)
            if fresh(env, limit):                   # ③ 双重检查：前一个线程刚算完
                return env.get("v")
            val = compute()                         # ④ 真回源（抛异常 → 不写缓存）
            with self._guard:
                self._data[k] = entry(val)
                self._data.move_to_end(k)
                while len(self._data) > self.max_entries:
                    evicted, _ = self._data.popitem(last=False)
                    self._keys.drop(evicted)        # 淘汰的键顺手回收锁（正被持有的不丢）
            return val

    def invalidate(self, key: Optional[Any] = None) -> None:
        """丢弃某键的缓存值与它那把锁（下一轮强制重新回源）；不传键 = 整容器复位。

        与 ``TTLCache.invalidate`` 同名同义，差别在这里**连锁一起回收**；而锁由
        ``KeyLocks`` 只丢空闲的 —— 正被别的线程持有的锁删不得（删了同键会造出第二把）。
        """
        with self._guard:
            if key is None:
                self._data.clear()
            else:
                self._data.pop(str(key), None)
        if key is not None:
            self._keys.drop(key)

    def stats(self) -> Dict[str, Any]:
        """当前规模 / 在飞锁数，供诊断（锁数取自 ``KeyLocks``，在 _guard 外面取以免锁序纠缠）。"""
        with self._guard:
            n = len(self._data)
            oldest: Optional[float] = None
            if n:
                first = next(iter(self._data.values()))
                oldest = max(0.0, time.time() - float(first.get("ts", 0.0) or 0.0))
        return {"name": self.name, "kind": "flight", "n": n, "max": self.max_entries,
                "ttl": self.ttl, "locks": self._keys.stats()["n"], "oldest_sec": oldest}


class Cooldown:
    """负缓存 / 冷却：某键在 TTL 内「刚失败过」，别再试（防反复打站点 / 反复重算）。

    与 ``TTLCache`` 的分工：那是「成功了缓存结果」，这是「失败了记一笔、暂时不重试」。
    """

    def __init__(self, name: str, ttl: float = 180.0, max_entries: int = 512) -> None:
        self.name = str(name)
        self.ttl = float(ttl)
        self.max_entries = max(int(max_entries), 1)
        # 值 = (标记时刻, 该条自己的冷却时长)：允许按条覆盖默认 ttl
        self._data: "OrderedDict[str, Tuple[float, float]]" = OrderedDict()
        self._lock = threading.Lock()
        _REGISTRY[self.name] = self

    def hot(self, key: Any) -> bool:
        """该键是否仍在冷却中（True = 先别试）；已过冷却的条目顺手清掉。"""
        k = str(key)
        with self._lock:
            pair = self._data.get(k)
            if pair is None:
                return False
            ts, span = float(pair[0]), float(pair[1])
            if (time.time() - ts) < span:
                return True
            self._data.pop(k, None)
            return False

    def mark(self, key: Any, ttl: Optional[float] = None) -> None:
        """标记该键「刚失败过」；``ttl`` 可覆盖默认冷却时长（按条生效）。"""
        k = str(key)
        span = float(ttl) if ttl is not None else self.ttl
        with self._lock:
            self._data[k] = (time.time(), span)
            self._data.move_to_end(k)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def clear(self, key: Optional[Any] = None) -> None:
        """解除某个键的冷却；不传键则全部解除（如「站点认证恢复了」）。"""
        with self._lock:
            if key is None:
                self._data.clear()
            else:
                self._data.pop(str(key), None)

    def stats(self) -> Dict[str, Any]:
        """当前冷却中的键数量，供诊断。"""
        with self._lock:
            n = len(self._data)
        return {"name": self.name, "kind": "cooldown", "n": n, "max": self.max_entries,
                "ttl": self.ttl}


def snapshot() -> List[Dict[str, Any]]:
    """列出全部已登记容器（给 ``runtime.cache_status()`` 用，阶段二接入）。"""
    out: List[Dict[str, Any]] = []
    for box in list(_REGISTRY.values()):
        try:
            out.append(box.stats())
        except Exception:  # noqa: BLE001
            continue
    return out
