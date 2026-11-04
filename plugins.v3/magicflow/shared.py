# -*- coding: utf-8 -*-
"""魔流 · shared —— 跨热重载存活的**进程级共享槽**（L0，只 import 标准库）。

为什么要有这个模块
------------------
插件热重载（``PLUGIN_AUTO_RELOAD=True``）换的是**模块与实例**，进程不退出：旧实例的
线程还在跑、新实例已经接活。凡是要「两边看到同一份」的东西（账本单例、互斥锁、计数器）
都不能挂 ``self``，只能挂在一个热重载不会重建的地方 —— 约定就是
``sys.modules["__magicflow_shared__"]`` 这个动态模块（与 ``kvstore`` / ``persistence``
原先各写一份的是同一个槽）。

**为什么不用 Redis 做锁**（2026-10-29 定，别再改回去）
------------------------------------------------------
生产是单进程（``API_WORKERS=1``），跨进程互斥根本不存在；而此时 Redis 锁是纯退化：

· 开销：``threading.Lock`` ~100ns，Redis ``SET NX`` 同 docker 网络 ~0.5ms（差 5000 倍），
  而签到 / 规则探测这类是**每轮都要抢**的路径；
· 可靠性：Redis 锁必须有 TTL（否则进程崩了永不释放），TTL 到期而任务还没跑完 = 锁
  凭空消失，第二个执行者直接进临界区；要防就得写续期线程，复杂度翻倍；
· 可丢性：MP 里「清空缓存」会 ``flushdb()``、内存吃紧会淘汰 key —— 锁被淘汰的后果是
  **两个线程同时进临界区**，比缓存被淘汰严重得多。``kvstore`` 自己的原则就是
  「Redis 可丢、可回灌」，可丢的东西能当缓存，不能当锁。

分工：**缓存/状态 → Redis（TierCache，可丢可重建）；锁/单例 → 进程内存（这里，绝不丢）**。

为什么收敛（原来的问题）
------------------------
这段「取槽 + 幂等补齐属性」原先抄了 7 遍（cacheops / common / siteops×2 / tags×2 /
kvstore / persistence），每处都要重新踩同一个坑，并各自在注释里记一遍「踩过」：

· **坑①：属性补齐不幂等** —— 某入口只建了 ``instances`` / ``counters``，另一个入口
  直接读 ``mod.lock`` → ``AttributeError`` → **插件加载失败**。所以 ``module()`` 每次
  都补齐全部属性，任何入口先建都不缺。
· **坑②：热重载后「类是新的、单例是旧实例」** —— 旧实例没有本次新增的方法，
  ``AttributeError`` 被 ``init_plugin`` 的 try 吞掉 → 功能静默失效（实测：H&R 判定整块
  落到「未知保守」、删除闸门漏洞在重载后依旧生效）。``singleton()`` 用类型校验挡这个。

★ ``singleton()`` **只覆盖「不匹配就重建」这一种策略**。``persistence.MagicFlowStore``
  必须用「只换 ``__class__``、不重新 ``__init__``」（重建会丢未落盘的改动并再起一个
  落盘线程），那类对象自己管，别硬套进来。
"""

from __future__ import annotations

import sys
import threading
import types
from typing import Any, Callable, Dict, Optional

# 热重载不重建的模块槽（插件约定名，``kvstore`` / ``persistence`` 用的是同一个）
KEY = "__magicflow_shared__"

# ``_thread.lock`` 是 C 类型，跨热重载是同一个对象 —— 用它做锁的类型校验，
# 而不是自定义包装类（自定义类在 reload 后是新类，``isinstance(旧实例, 新类)`` 为 False，
# 于是「校验」会亲手把锁重建掉，互斥悄悄失效）。
_LOCK_TYPE = type(threading.Lock())


def module() -> Any:
    """取（必要时创建）共享槽，并**幂等补齐**全部属性。

    ★ 每次都补齐，不依赖「谁先建」：历史上因为某入口只建了部分属性，
      另一个入口直接读 ``mod.lock`` 就 ``AttributeError``，整插件加载失败。
    """
    mod = sys.modules.get(KEY)
    if mod is None:
        mod = types.ModuleType(KEY)
        sys.modules[KEY] = mod
    for attr, factory in (("instances", dict), ("counters", dict),
                          ("singletons", dict), ("lock", threading.Lock)):
        if not hasattr(mod, attr):
            setattr(mod, attr, factory())
    return mod


def lock(name: str, legacy: str = "") -> Any:
    """取一把**跨热重载存活**的裸锁（同名全进程唯一）。

    用于「热重载会换实例、旧实例线程还在跑」的互斥：实例属性上的锁管不住旧线程。
    实测必要的场景：``siteops._rules_probe_guard`` —— 8 次重载各起一条补跑线程 →
    同时探测 8 轮 → 同批 ``mf_site`` 行互相覆盖 + ``psycopg2 DeadlockDetected``。

    调用方自己决定 ``with lock:``（阻塞）还是 ``acquire(blocking=False)``（抢不到就跳过）。

    ``legacy``：**一次性迁移用**。把共享槽从散装实现收进本模块的那一次部署，旧代码
    往 ``instances[legacy]`` 里放过同一把锁；不改名直接取新槽的话，热重载瞬间新旧实例
    各拿一把不同的锁 —— 正是这个锁要防的事。传入旧槽名后，第一次取会把它搬过来。
    迁移完成（旧实例退场）后这个参数可以留着不管，也可以删掉。
    """
    mod = module()
    slot = "lock:" + str(name)
    with mod.lock:
        obj = mod.instances.get(slot)
        if not isinstance(obj, _LOCK_TYPE) and legacy:
            old = mod.instances.get(str(legacy))
            if isinstance(old, _LOCK_TYPE):
                mod.instances[slot] = old       # 就地迁移：同一把锁换个槽名
                return old
        if not isinstance(obj, _LOCK_TYPE):
            obj = threading.Lock()
            mod.instances[slot] = obj
        return obj


def singleton(name: str, factory: Callable[[], Any], cls: Optional[type] = None) -> Any:
    """取（必要时创建）**进程级单例**；``cls`` 给了就校验类型，不匹配则重建。

    ``factory`` 只在需要时调用，且**在注册表锁之外**执行（它可能读库/建连接，
    持锁做 IO 会把其它取槽的线程一起堵住）。

    ``cls`` 的作用是坑②：热重载后模块里的类是新的，注册表里却是旧类的实例 ——
    旧实例没有本次新增的方法。校验到不匹配就重建（账本类对象重建会从后端表重新加载，
    安全）。★ 有未落盘状态 / 后台线程的对象**不能**用这个（重建会丢数据 + 起双份线程），
    见 ``persistence.MagicFlowStore.__new__`` 的换类写法。
    """
    key = str(name)
    mod = module()
    with mod.lock:
        obj = mod.instances.get(key)
        if obj is not None:
            if cls is None or isinstance(obj, cls):
                return obj
        # 走到这里：没有，或是旧类实例 → 需要（重新）创建
    # 「建」这一步按名字串行化，避免两个线程各建一个、后写的把先写的顶掉（双单例）
    with lock("build:" + key):
        with mod.lock:
            obj = mod.instances.get(key)
            if obj is not None and (cls is None or isinstance(obj, cls)):
                return obj
        obj = factory()
        with mod.lock:
            mod.instances[key] = obj
        return obj


def peek(name: str) -> Any:
    """只读看单例当前是什么（不创建、不校验），诊断用。"""
    mod = module()
    with mod.lock:
        return mod.instances.get(str(name))


def bump(name: str, n: int = 1) -> int:
    """计数器原子自增，返回新值（跨热重载不丢）。"""
    mod = module()
    key = str(name)
    with mod.lock:
        val = int(mod.counters.get(key) or 0) + int(n)
        mod.counters[key] = val
        return val


def counters() -> Dict[str, Any]:
    """计数器字典**本身**（不是副本）。

    ★ 返回原对象是兼容性要求：``kvstore._bump_writes`` 直接往里写增量。
    新代码请用 ``bump()``（它持锁），别自己 ``c[k] = c[k] + 1``。
    """
    return module().counters


def instances() -> Dict[str, Any]:
    """单例注册表**本身**（诊断用；读写请走 ``singleton`` / ``peek``）。"""
    return module().instances
