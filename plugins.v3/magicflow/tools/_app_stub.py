#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 离线测试用 MoviePilot ``app.*`` 最小桩。

部分历史测试直接 ``exec_module`` 加载插件模块，而 ``common.py`` 会
``from app.schemas.types import EventType``。本桩只给离线测试用，
**不进入生产运行时**：提供 ``app`` / ``app.schemas`` / ``app.schemas.types``
以及惰性兜底属性（避免每个导出都要手写）。

用法（测试脚本最顶部，早于任何插件模块加载）::

    import _app_stub  # noqa: F401
    _app_stub.install()
"""
from __future__ import annotations

import sys
import types


class _Any:
    """惰性万能桩：可调用、可点属性、可迭代为空。"""

    def __init__(self, name: str = "stub") -> None:
        self._name = name

    def __call__(self, *a, **k):
        return _Any(self._name + "()")

    def __getattr__(self, k: str):
        if k.startswith("__"):
            raise AttributeError(k)
        return _Any(self._name + "." + k)

    def __iter__(self):
        return iter(())

    def __bool__(self) -> bool:
        return True


def _mod(name: str, **attrs) -> types.ModuleType:
    m = sys.modules.get(name) or types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    if not hasattr(m, "__getattr__"):
        setattr(m, "__getattr__", lambda n: _Any(name + "." + n))
    sys.modules[name] = m
    return m


def install() -> None:
    """安装 ``app.*`` 桩（幂等）。"""
    if "app" in sys.modules and getattr(sys.modules["app"], "_mf_stub", False):
        return
    app = _mod("app")
    app._mf_stub = True
    schemas = _mod("app.schemas", Response=type("Response", (), {}))
    _mod("app.schemas.types", EventType=type("EventType", (), {}))
    sdk = _mod("app.sdk")
    _mod("app.sdk.logging", logger=type("Logger", (), {
        "info": staticmethod(lambda *a, **k: None),
        "warning": staticmethod(lambda *a, **k: None),
        "error": staticmethod(lambda *a, **k: None),
        "debug": staticmethod(lambda *a, **k: None)})())
    _mod("app.sdk.plugin", PluginBase=type("PluginBase", (), {}))
    _mod("app.sdk.events", eventmanager=type("EventManager", (), {
        "register": staticmethod(lambda *a, **k: None),
        "send_event": staticmethod(lambda *a, **k: None),
        "async_send_event": staticmethod(lambda *a, **k: None)})())
    _mod("app.sdk.config", settings=type("Settings", (), {})())
    setattr(app, "schemas", schemas)
    setattr(app, "sdk", sdk)


def fill_tags(mod, root):
    """给测试自建的 ``.tags`` 桩补齐 tagspec.py 里的真实常量/纯函数（只补缺，不覆盖）。

    19.10.27 起标签常量下沉到 ``tagspec.py``（L0、纯标准库）。历史测试常只手写
    几个常量（如 ``STATE_BRUSH/STATE_BONUS``），插件模块一 import 新常量（``STATE_KEEP``
    /``STATE_MUSIC``/``STATES``）就 ImportError。这里按「缺什么补什么」从真值源加载，
    测试自己的假函数仍优先。读不到 tagspec（工作区 65 个文件属主不可读）时静默跳过。
    """
    try:
        import importlib.util as _u
        from pathlib import Path as _P
        p = _P(root) / "tagspec.py"
        spec = _u.spec_from_file_location("_mf_tagspec_helper", str(p))
        ts = _u.module_from_spec(spec)
        spec.loader.exec_module(ts)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        return mod
    for n in dir(ts):
        if n.startswith("_") or hasattr(mod, n):
            continue
        setattr(mod, n, getattr(ts, n))
    return mod
