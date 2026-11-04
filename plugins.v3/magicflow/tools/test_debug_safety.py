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
_SKIP = 0


def _ok(cond: bool, msg: str) -> None:
    global _OK, _FAIL
    if cond:
        _OK += 1
        print(f"  ✅ {msg}")
    else:
        _FAIL += 1
        print(f"  ❌ {msg}")


def _skip(msg: str) -> None:
    """显式跳过：不计入 ✅ 也不计入 ❌，但必须可见（不静默混过）。"""
    global _SKIP
    _SKIP += 1
    print(f"  ⏭ 跳过 {msg}")


# `_dbg_safe_read_path` 的白名单判定写的是 `rp == r or rp.startswith(r + "/")`，
# 只对 POSIX 绝对路径成立。Windows 上 cwd 是 UNC 时 `/config/app.env` 会被
# realpath 解析成 `\\\\host\\share\\config\\app.env`，`/app/../../etc/passwd` 同理
# —— 这类断言在 Windows 上必然假红。插件实际运行在容器（Linux），故仅在 POSIX
# 上跑这些用例；Windows 上显式跳过并留痕，不伪装成通过。
_POSIX_ONLY = os.name != "nt"


def _okp(cond: bool, msg: str) -> None:
    """POSIX-only 断言：Windows 上跳过，其余平台正常判定。"""
    if _POSIX_ONLY:
        _ok(cond, msg)
    else:
        _skip(f"{msg}（Windows 无 POSIX 绝对路径语义）")


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
    # 先归一：Windows 的 tempdir 可能是 8.3 短名（ADMINI~1），而 `_dbg_real` 返回
    # 长名，直接用会让「白名单根 = td」永远匹配不上（假红）。
    td = os.path.realpath(td)
    os.makedirs(os.path.join(td, "logs"))
    log = os.path.join(td, "logs", "app.log")
    open(log, "w").write("hello\n")
    secret = os.path.join(td, "app.env")
    open(secret, "w").write("API_TOKEN='x'\n")
    tok = os.path.join(td, "logs", "token.json")
    open(tok, "w").write("{}\n")

    _ns["_DBG_READ_ROOTS"] = (td,)          # 测试里把白名单根指向临时目录

    # ⚠ 以下三条同样依赖 POSIX 分隔符：生产代码用 `rp.startswith(r + "/")`，
    #   Windows 上 rp 是反斜杠路径，正常文件也会被判「不在白名单」→ 必须跳过而非判红。
    rp, why = _safe(log)
    _okp(rp == os.path.realpath(log), "白名单内普通文件 → 放行")
    rp2, why2 = _safe(os.path.join(td, "logs", "..", "logs", "app.log"))
    _okp(rp2 == os.path.realpath(log), "带 `..` 但归一后仍在白名单内 → 放行")

    # 核心：`..` 穿越到白名单之外
    esc = os.path.join(td, "logs", "..", "..", "etc", "passwd")
    rp3, why3 = _safe(esc)
    _okp(rp3 is None and "白名单" in why3, f"`..` 穿越出根 → 拒绝（{why3}）")

    # 经典攻击串（白名单根 = 真实 /app 时）—— POSIX 绝对路径语义，见 _okp 说明
    _ns["_DBG_READ_ROOTS"] = ("/app", "/config", "/core")
    rp4, why4 = _safe("/app/../../etc/passwd")
    _okp(rp4 is None, "`/app/../../etc/passwd` → 拒绝（老实现会读出来）")
    rp5, why5 = _safe("/config/app.env")
    _okp(rp5 is None and "敏感" in why5, f"`/config/app.env`（API_TOKEN）→ 拒绝（{why5}）")
    rp6, why6 = _safe("/etc/passwd")
    _okp(rp6 is None, "白名单外绝对路径 → 拒绝")
    rp7, why7 = _safe("/app")          # 目录（非普通文件）
    _okp(rp7 is None and "不是文件" in why7, "白名单根目录本身（非文件）→ 拒绝")
    _ns["_DBG_READ_ROOTS"] = ("/app",)
    rp8, _w8 = _safe("/application/secret.txt")
    _okp(rp8 is None, "`/application/...` 不因前缀误命中根 `/app`（按路径边界判）")

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
# 19.10.29 起路由表是 features/api.py 里的 _ROUTES 元组：
#   _ROUTES = ((path, handler, methods, summary), ...)
# 不再是 {"path": ..., "endpoint": ...} 字典，所以这里按元组取前两位。
api_src = open(os.path.join(_ROOT, "features", "api.py"), encoding="utf-8").read()
_api_tree = ast.parse(api_src)
_routes: list[tuple[str, str]] = []
for _node in _api_tree.body:
    if (isinstance(_node, ast.Assign)
            and [t.id for t in _node.targets if isinstance(t, ast.Name)] == ["_ROUTES"]):
        for _elt in getattr(_node.value, "elts", []):
            if isinstance(_elt, ast.Tuple) and len(_elt.elts) == 4:
                _p, _h = _elt.elts[0], _elt.elts[1]
                if isinstance(_p, ast.Constant) and isinstance(_h, ast.Constant):
                    _routes.append((_p.value, _h.value))
_api_paths: set[str] = {p for p, _h in _routes if p.startswith("/debug")}
_ok(bool(_routes), f"解析到路由 {len(_routes)} 条")
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
_ep_by_path: dict[str, str] = {p: h for p, h in _routes if p.startswith("/debug")}
_write_funcs = {_ep_by_path.get(p, "") for p in _WRITE_PATHS}
for f in sorted(_guard_funcs):
    _ok(f in _write_funcs, f"用写门的 {f} 已在写标记表登记")

print("── C2. 写门真调用（清单 → 代码，反向校验）──")
# 反向：DEBUG_WRITE_PATHS 登记的**每一条**，其 endpoint 函数必须**真的**调了写门
#       （直接调，或经同仓封装函数间接调）。防「登记了但没调」——如 /debug/retag。
# 只补这一段，不动 C 段已有的「代码 → 清单」校验，两个方向合起来才是双向。
_GUARD_NAME = "_dbg_guard_write"
_srcs: dict[str, str] = {}
for _fn in ("debug.py", "runtime.py", "live.py", "crossseed.py", "services.py"):
    _p = os.path.join(_ROOT, "features", _fn)
    if os.path.exists(_p):
        _srcs[_fn] = open(_p, encoding="utf-8").read()

_direct: set[str] = set()          # 函数体内出现 _dbg_guard_write(...) 调用的
_calls: dict[str, set[str]] = {}   # 函数 → 它调用的（本仓）函数名，用于算间接调用
for _name, _s in _srcs.items():
    for _node in ast.walk(ast.parse(_s)):
        if not isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        _callee: set[str] = set()
        _hit = False
        for _c in ast.walk(_node):
            if not isinstance(_c, ast.Call):
                continue
            _f = _c.func
            if isinstance(_f, ast.Name):
                if _f.id == _GUARD_NAME:
                    _hit = True
                else:
                    _callee.add(_f.id)
            elif isinstance(_f, ast.Attribute):
                _callee.add(_f.attr)
        _calls.setdefault(_node.name, set()).update(_callee)
        if _hit:
            _direct.add(_node.name)

# ★ 防误报 ①：传递闭包。A 调 B、B 调了写门 → A 也算过了门（guard 被封装函数包一层也不误报）
_closure = set(_direct)
_changed = True
while _changed:
    _changed = False
    for _fn, _callee in _calls.items():
        if _fn not in _closure and (_callee & _closure):
            _closure.add(_fn)
            _changed = True

# ★ 防误报 ②：只要函数体里出现过写门调用就算过门，不判断它在哪个分支。
#   debug_retag（只在 dry=0 时调）、debug_crossseed（只在 add=true 时调）这类
#   「条件守卫」是**正确的**写法，不能因为不在主路径就判失败。
# ★ 防误报 ③：guard 允许跨模块 import 后调用（runtime.py 里 `from .debug import
#   _dbg_guard_write`）—— ast 上仍是 Name('_dbg_guard_write')，名字匹配即可命中。
# ★ 防误报 ④：用非 _dbg_guard_write 自有闸门的端点不进 DEBUG_WRITE_PATHS 就不会被
#   本段点名；将来若登记，把它实际用的闸门函数名加进下面这个别名集合。
_GUARD_ALIAS: set[str] = set()  # 例：{"_as_bool_arg"} —— 目前为空，保持严格
_closure |= {_fn for _fn, _callee in _calls.items() if _callee & _GUARD_ALIAS}

for _p in sorted(_WRITE_PATHS):
    _ep = _ep_by_path.get(_p, "")
    if not _ep:
        _ok(False, f"写标记 {_p} 在 api.py 里找不到 endpoint（路径写错了？）")
        continue
    _ok(_ep in _closure, f"写标记 {_p} → endpoint `{_ep}` 真的调了写门（直接/间接）")

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
if _SKIP:
    print(f"⏭ 跳过 {_SKIP} 项（Windows 路径语义；插件运行在 Linux 容器，须在容器内跑才能全覆盖）")
if _FAIL:
    print(f"❌ FAIL —— {_FAIL} 项失败 / {_OK + _FAIL} 项")
    sys.exit(1)
print(f"✅ PASS —— 共 {_OK} 项全过")
