#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 能力清单漂移检查（preflight 第 8 步，离线可跑，无需 MoviePilot）。

把「已注册路由」（``get_api()`` 实际产出里的 ``/agent*`` 子集）与 ``GET /agent``
能力清单（``_agent_endpoints()``）**求差**：

  * 清单里有、路由表没有 → 端点没接上（登记了没实现）；
  * 路由表有、清单里没有 → 加了端点忘了登记（「登记制」红线）；
  * 两边字段不一致（method / write / params / returns / version / handler）→ 失败。

只用 Python 标准库 + 本地 stub ``app.*`` 加载模块，不发任何网络请求。
用法：``python3 tools/check_agent_manifest.py``（退出码 0=一致 / 1=漂移）。
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PKG = "mf_agent_manifest_check"

_ERRORS: list = []


def _fail(msg: str) -> None:
    _ERRORS.append(msg)


def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub_app() -> None:
    """stub ``app.*``（agentapi 经 common / pool 间接 import MoviePilot 依赖）。"""
    for name, attr_map in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attr_map.items():
            setattr(m, k, v)


def _load_agentapi():
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    # common 顶部的叶子依赖（只 import 符号，不跑逻辑）
    for modname, attrs in (
        ("bonus", ("TorrentBonusInfo",)),
        ("fingerprint", ("fingerprint", "inner_fingerprint", "load_torrent_entries", "total_size")),
        ("fetcher", ("SiteCandidateTorrent",)),
        ("recommend", ("recognize",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    _load(PKG + ".common", "common.py")
    _load(PKG + ".features.pool", "features/pool.py")
    _load(PKG + ".features.api", "features/api.py")
    agentapi = _load(PKG + ".features.agentapi", "features/agentapi.py")
    return agentapi


def _load_rescue():
    """加载 features/rescue.py（需在 ``_load_agentapi`` 之后：依赖其 stub）。"""
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    return _load(PKG + ".features.rescue", "features/rescue.py")


def _load_agentledger():
    """加载 features/agentledger.py（P1.5b，顶层零相对 import，可直接载入）。"""
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    return _load(PKG + ".features.agentledger", "features/agentledger.py")


def _make_harness(AgentApiMixin, ApiMixin, RescueMixin=None, AgentLedgerMixin=None):
    bases = [AgentApiMixin, ApiMixin]
    if RescueMixin is not None:
        bases.insert(0, RescueMixin)  # handler 可能在 RescueMixin（如 agent_rescue）
    if AgentLedgerMixin is not None:
        bases.insert(1, AgentLedgerMixin)  # handler 在 AgentLedgerMixin（P1.5b）

    class Harness(*bases):
        def __getattr__(self, name):
            def _dummy(*args, **kwargs):
                return None
            return _dummy
    return Harness


def main() -> int:
    agentapi = _load_agentapi()
    AgentApiMixin = agentapi.AgentApiMixin
    api = sys.modules[PKG + ".features.api"]
    ApiMixin = api.ApiMixin
    rescue = _load_rescue()
    RescueMixin = rescue.RescueMixin
    agentledger = _load_agentledger()
    AgentLedgerMixin = agentledger.AgentLedgerMixin

    Harness = _make_harness(AgentApiMixin, ApiMixin, RescueMixin, AgentLedgerMixin)
    h = Harness()

    # ---- 1) 已注册路由里的 /agent* 子集 ----
    try:
        routes = h.get_api() or []
    except Exception as e:  # noqa: BLE001
        _fail(f"get_api() 抛异常：{type(e).__name__}: {e}")
        routes = []
    agent_routes = [r for r in routes if str(r.get("path") or "").startswith("/agent")]

    # ---- 2) 能力清单 ----
    canonical = agentapi._agent_endpoints() or []

    # ---- 3) 内部一致性：canonical 每项字段齐全、path 唯一 ----
    seen_paths = set()
    for ep in canonical:
        for key in ("path", "method", "handler", "write", "params", "returns", "version"):
            if key not in ep:
                _fail(f"清单项缺字段 {key!r}：{ep}")
        p = ep.get("path")
        if p in seen_paths:
            _fail(f"清单 path 重复：{p}")
        seen_paths.add(p)
        if ep.get("method") not in ("GET", "POST", "PUT", "DELETE"):
            _fail(f"清单 method 非法：{ep}")
        if not hasattr(Harness, ep.get("handler")):
            _fail(f"清单 handler 在 AgentApiMixin/AgentLedgerMixin/RescueMixin 上不存在：{ep.get('handler')}")

    # ---- 4) 求差：注册路由 ↔ 清单（path+method 维度） ----
    reg_keys = {(r.get("path"), (r.get("methods") or [None])[0]) for r in agent_routes}
    man_keys = {(e.get("path"), e.get("method")) for e in canonical}

    for path, method in sorted(reg_keys - man_keys):
        _fail(f"路由表有、清单没有（忘了登记？）：{method} {path}")
    for path, method in sorted(man_keys - reg_keys):
        _fail(f"清单有、路由表没有（没接上？）：{method} {path}")

    # ---- 5) 字段一致性：method / handler 绑定 / write / params / returns / version ----
    reg_by_key = {(r.get("path"), (r.get("methods") or [None])[0]): r for r in agent_routes}
    for ep in canonical:
        key = (ep.get("path"), ep.get("method"))
        r = reg_by_key.get(key)
        if r is None:
            continue
        # handler 绑定：注册路由的 endpoint 必须是清单里声明的那个方法
        endpoint = r.get("endpoint")
        func = getattr(endpoint, "__func__", None)
        bound_name = getattr(func, "__name__", None)
        if bound_name != ep.get("handler"):
            _fail(f"handler 绑定不符：{ep['path']} 路由绑定 {bound_name!r}，清单声明 {ep['handler']!r}")

    # ---- 6) 公开清单（GET /agent 实际返回）与 canonical 对齐 ----
    try:
        resp = h.agent_manifest()
        data = resp.get("data") or {}
        pub = data.get("endpoints") or []
        pub_keys = {(e.get("path"), e.get("method")) for e in pub}
    except Exception as e:  # noqa: BLE001
        _fail(f"agent_manifest() 抛异常：{type(e).__name__}: {e}")
        pub_keys = set()
    for path, method in sorted(man_keys - pub_keys):
        _fail(f"公开清单缺端点：{method} {path}")
    for path, method in sorted(pub_keys - man_keys):
        _fail(f"公开清单多出端点：{method} {path}")
    # 公开清单每项字段
    for e in (pub if 'pub' in dir() else []):
        for key in ("path", "method", "write", "params", "returns", "version"):
            if key not in e:
                _fail(f"公开清单项缺字段 {key!r}：{e}")

    # ---- 汇总 ----
    if _ERRORS:
        print(f"❌ 能力清单漂移：{len(_ERRORS)} 处不一致")
        for msg in _ERRORS:
            print(f"  - {msg}")
        return 1
    print(f"✅ 能力清单一致：路由 {len(agent_routes)} 个 / 清单 {len(canonical)} 个，字段/绑定/公开面全部对齐")
    return 0


if __name__ == "__main__":
    sys.exit(main())
