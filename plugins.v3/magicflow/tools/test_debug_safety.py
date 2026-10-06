#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""12.7.0 安全面离线测试（宿主可直接跑，不依赖 app.*）。

覆盖：
  A. 读路径安全 —— realpath 归一（防 `..` 穿越）+ 白名单根 + 敏感文件黑名单
  B. 写操作门 —— `_dbg_guard_write`：缺 confirm 拒绝 / confirm=1 放行 / 非法值拒绝
  C. 写标记表自洽 —— `DEBUG_WRITE_PATHS` 的每个键都真在 `features/api.py` 路由表里，
     且每个「调了写门」的端点都在表里（登记制：加了忘了登记 → 失败）
  D. AI 入口登记 —— `/agent/debug/surface` 在 `_agent_endpoints()` 清单里（只读）

用法：python3 tools/test_debug_safety.py
"""
from __future__ import annotations

import ast
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_OK = 0
_FAIL = 0


def _ok(cond: bool, msg: str) -> None:
    global _OK, _FAIL
    if cond:
        _OK += 1
        print(f"  ✅ {msg}")
    else:
        _FAIL += 1
        print(f"  ❌ {msg}")


# ── 只加载 features/debug.py 的模块级纯函数（不 import 插件包，避开 app.*）──
_src = open(os.path.join(_ROOT, "features", "debug.py"), encoding="utf-8").read()


class _FakeResp:  # noqa: D101
    """Response 的哑替身（只保留 success/message/data）。"""

    def __init__(self, success=True, message="", data=None):
        self.success = success
        self.message = message
        self.data = data


from typing import Any, Dict, List  # noqa: E402

_ns: dict = {"re": re, "Response": _FakeResp, "Any": Any, "Dict": Dict,
             "List": List, "__name__": "_dbg_probe"}
_start = _src.index("# ── ★ 12.7.0")
_end = _src.index("class DebugMixin")
exec(compile(_src[_start:_end], "debug_probe", "exec"), _ns)

_safe = _ns["_dbg_safe_read_path"]
_guard = _ns["_dbg_guard_write"]
_sens = _ns["_dbg_sensitive"]
_WRITE_PATHS = _ns["DEBUG_WRITE_PATHS"]

print("── A. 读路径安全（防穿越 + 白名单 + 敏感文件）──")
with tempfile.TemporaryDirectory() as td:
    os.makedirs(os.path.join(td, "logs"))
    log = os.path.join(td, "logs", "app.log")
    open(log, "w").write("hello\n")
    secret = os.path.join(td, "app.env")
    open(secret, "w").write("API_TOKEN='x'\n")
    tok = os.path.join(td, "logs", "token.json")
    open(tok, "w").write("{}\n")

    _ns["_DBG_READ_ROOTS"] = (td,)          # 测试里把白名单根指向临时目录

    rp, why = _safe(log)
    _ok(rp == os.path.realpath(log), "白名单内普通文件 → 放行")
    rp2, why2 = _safe(os.path.join(td, "logs", "..", "logs", "app.log"))
    _ok(rp2 == os.path.realpath(log), "带 `..` 但归一后仍在白名单内 → 放行")

    # 核心：`..` 穿越到白名单之外
    esc = os.path.join(td, "logs", "..", "..", "etc", "passwd")
    rp3, why3 = _safe(esc)
    _ok(rp3 is None and "白名单" in why3, f"`..` 穿越出根 → 拒绝（{why3}）")

    # 经典攻击串（白名单根 = 真实 /app 时）
    _ns["_DBG_READ_ROOTS"] = ("/app", "/config", "/core")
    rp4, why4 = _safe("/app/../../etc/passwd")
    _ok(rp4 is None, "`/app/../../etc/passwd` → 拒绝（老实现会读出来）")
    rp5, why5 = _safe("/config/app.env")
    _ok(rp5 is None and "敏感" in why5, f"`/config/app.env`（API_TOKEN）→ 拒绝（{why5}）")
    rp6, why6 = _safe("/etc/passwd")
    _ok(rp6 is None, "白名单外绝对路径 → 拒绝")
    rp7, why7 = _safe("/app")          # 目录（非普通文件）
    _ok(rp7 is None and "不是文件" in why7, "白名单根目录本身（非文件）→ 拒绝")
    _ns["_DBG_READ_ROOTS"] = ("/app",)
    rp8, _w8 = _safe("/application/secret.txt")
    _ok(rp8 is None, "`/application/...` 不因前缀误命中根 `/app`（按路径边界判）")

    _ok(_sens("/config/plugins/MagicFlow/cookie.json"), "cookie.json 判为敏感")
    _ok(_sens("/x/id_rsa"), "id_rsa 判为敏感")
    _ok(_sens("/x/server.pem"), "server.pem 判为敏感")
    _ok(not _sens("/config/logs/moviepilot.log"), "普通日志不误伤")
    _ok(not _sens("/app/app/plugins/magicflow/features/debug.py"), "源码不误伤")

print("── B. 写操作门 ──")
_g0 = _guard("unit_test", 0)
_ok(_g0 is not None and _g0.success is False, "confirm 缺省 → 拒绝")
_ok(bool(_g0 and _g0.data.get("requires_confirm")), "拒绝体带 requires_confirm")
_ok("confirm=1" in str(getattr(_g0, "message", "")), "拒绝提示说明要 confirm=1")
_ok(_guard("unit_test", 1) is None, "confirm=1 → 放行")
_ok(_guard("unit_test", "1") is None, "confirm='1'（查询串字符串）→ 放行")
_ok(_guard("unit_test", 0) is not None, "confirm=0 → 拒绝")
_ok(_guard("unit_test", "yes") is not None, "confirm 非法值 → 拒绝")

print("── C. 写标记表自洽（登记制）──")
api_src = open(os.path.join(_ROOT, "features", "api.py"), encoding="utf-8").read()
_api_tree = ast.parse(api_src)
_api_paths: set[str] = set()
for node in ast.walk(_api_tree):
    if isinstance(node, ast.Dict):
        kv = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                kv[k.value] = v
        p = kv.get("path")
        if isinstance(p, ast.Constant) and isinstance(p.value, str) and p.value.startswith("/debug"):
            _api_paths.add(p.value)
_ok(bool(_api_paths), f"解析到 /debug 路由 {len(_api_paths)} 条")
for p in sorted(_WRITE_PATHS):
    _ok(p in _api_paths, f"写标记 {p} 在路由表里（有登记）")

# 反向：调了 `_dbg_guard_write` 的函数 → 其路由路径必须在写标记表里
_guard_funcs: set[str] = set()
for fn in ("debug.py", "runtime.py"):
    src = open(os.path.join(_ROOT, "features", fn), encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            called = any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name)
                and c.func.id == "_dbg_guard_write"
                for c in ast.walk(node)
            )
            if called:
                _guard_funcs.add(node.name)
_ok(bool(_guard_funcs), f"扫描到用写门的端点 {len(_guard_funcs)} 个：{sorted(_guard_funcs)}")
# 路径 → 端点名
_ep_by_path: dict[str, str] = {}
for node in ast.walk(_api_tree):
    if isinstance(node, ast.Dict):
        kv = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                kv[k.value] = v
        p, ep = kv.get("path"), kv.get("endpoint")
        if (isinstance(p, ast.Constant) and isinstance(p.value, str)
                and p.value.startswith("/debug")):
            name = ""
            if isinstance(ep, ast.Attribute):
                name = ep.attr
            _ep_by_path[p.value] = name
_write_funcs = {_ep_by_path.get(p, "") for p in _WRITE_PATHS}
for f in sorted(_guard_funcs):
    _ok(f in _write_funcs, f"用写门的 {f} 已在写标记表登记")

print("── D. AI 入口登记 ──")
_ag = open(os.path.join(_ROOT, "features", "agentapi.py"), encoding="utf-8").read()
_ok('"/agent/debug/surface"' in _ag, "`/agent/debug/surface` 进了 _agent_endpoints() 清单")
_ok("def agent_debug_surface" in _ag, "handler `agent_debug_surface` 已实现")
_ok('"write": False' in _ag.split('"/agent/debug/surface"')[1][:400],
    "surface 端点自己声明 write=False（只读）")

print("── E. 死代码已清 ──")
_dg = open(os.path.join(_ROOT, "dupgate.py"), encoding="utf-8").read()
_ok("def _dup_peek" not in _dg, "`_dup_peek`（死代码）已删")
_ok("def _dup_conflict_states" in _dg, "`_dup_conflict_states` 仍在（未误删）")

print("=" * 60)
if _FAIL:
    print(f"❌ FAIL —— {_FAIL} 项失败 / {_OK + _FAIL} 项")
    sys.exit(1)
print(f"✅ PASS —— 共 {_OK} 项全过")
