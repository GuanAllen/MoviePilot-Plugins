# -*- coding: utf-8 -*-
"""魔流 · 报表快照失效信号（★ 19.12.48 / 任务 96）。

零依赖的**进程内**共享状态，只做一件事：告诉 ``reportview._rv_ctx()``
「账单/账本已被写过，旧的采集快照不能再用了」。

为什么单独一个模块：

- ``features/hrbills.py`` 的两个账单存储（JSON / PG）是**唯一**的公共写入路径；
- ``features/reportview.py`` 反过来 ``from .hrbills import ...``（模块级），
  若把计数器放进 reportview，hrbills 只能运行时反向导入 → 循环依赖 + 离线测试全崩；
- 因此把状态放到谁都不依赖的小模块里，两边各取一次。

跨进程说明：本信号**只在同一进程内有效**。多进程/多实例下靠
``RV_CTX_TTL_SECONDS`` 的短 TTL 兜底（最长陈旧窗口 = TTL），不假装跨进程一致。
``sys.modules`` 别名让「测试里以假包名加载」与「生产里以真包名加载」拿到的是
同一个模块对象（否则两边各持一个计数器，写失效会静默失灵）。
"""
from __future__ import annotations

import sys
import threading

#: 同一份状态在 sys.modules 里的规范别名（跨包名加载时共用）
ALIAS = "magicflow_rv_state_v1"

#: 报表快照短 TTL（秒）。正常读最多陈旧这么久；写动作另有即时失效信号。
RV_CTX_TTL_SECONDS = 8.0

_lock = threading.RLock()
_generation = 0


def generation() -> int:
    """当前写入代次（单调递增）。"""
    with _lock:
        return _generation


def bump() -> int:
    """任何会改变报表快照的写动作**成功之后**调用一次。返回新代次。"""
    global _generation
    with _lock:
        _generation += 1
        return _generation


def ttl() -> float:
    return RV_CTX_TTL_SECONDS


# 无论本模块被以哪个包名 import，都把同一对象登记到规范别名上。
sys.modules.setdefault(ALIAS, sys.modules[__name__])
