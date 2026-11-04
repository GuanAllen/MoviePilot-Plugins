#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · API 路由表检查器（preflight 第 25 步，纯 AST，不 import 插件）。

`features/api.py` 的 `_ROUTES` 是 146 条路由的唯一真值源，`get_api` 只是把
handler 名绑成实例方法。表是**数据**，编译器不会替你发现「两条路由抢同一个
path」「handler 早被改名了」「通配路由把后面的字面量吃掉」——这三类都只在
运行时表现为 404 或「怎么调都是别人的处理函数」，所以必须静态拦。

检测项：
  R1 每条必须是 4 元组 ``(path, handler, methods, summary)``，全 str；
     methods 用逗号分隔，成员必须属于 GET/POST/PUT/DELETE/PATCH/HEAD。
  R2 path 规范：``/`` 开头、不以 ``/`` 结尾、无空段、无空格。
  R3 同一 ``(path, method)`` 不得注册两次（后者会被前者遮蔽，且没人知道）。
  R4 handler 必须是某个 ``*Mixin`` 类的方法（改了名/搬了家这里就红）。
  R5 顺序安全：按表的书写顺序模拟「首次匹配」，每条路由拿自己路径的样例 URL
     去匹配，命中的必须还是它自己（通配路由排在字面量前面就会红）。
  R6 不得与 ``AgentApiMixin`` 追加的 ``/agent*`` 路由撞 ``(path, method)``。

为什么用「模拟首次匹配」而不是两两比对通配/字面量：
    真实框架按注册顺序取第一个匹配项，两两比对分不清先后，会漏掉
    「窄路由写在宽路由后面」这种只有部分方法被吃掉的情况。

用法：``python3 tools/check_api_routes.py [--verbose]``
退出码：0 = 通过；1 = 有违规。
"""
from __future__ import annotations

import ast
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

API_FILE = "features/api.py"
AGENT_FILE = "features/agentapi.py"
FEATURES_DIR = ROOT / "features"

ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"}
SAMPLE_SEG = "mfcheck"

_ERRORS: list = []


def _fail(msg: str) -> None:
    _ERRORS.append(msg)


# ---------------------------------------------------------------- 读取路由表
def _read_routes() -> list:
    """解析 `_ROUTES`，返回 [(path, handler, methods_str, summary, lineno)]。"""
    src = (ROOT / API_FILE).read_text(encoding="utf-8")
    tree = ast.parse(src)
    table = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if names == ["_ROUTES"]:
                table = node.value
                break
    if table is None:
        _fail(f"{API_FILE}: 找不到模块级 _ROUTES 表")
        return []
    if not isinstance(table, (ast.Tuple, ast.List)):
        _fail(f"{API_FILE}: _ROUTES 必须是字面量元组/列表")
        return []

    routes = []
    for elt in table.elts:
        if not (isinstance(elt, ast.Tuple) and len(elt.elts) == 4):
            _fail(f"{API_FILE}:{getattr(elt, 'lineno', '?')} 不是 4 元组 → {ast.unparse(elt)[:60]}")
            continue
        vals = []
        for sub in elt.elts:
            if not isinstance(sub, ast.Constant) or not isinstance(sub.value, str):
                _fail(f"{API_FILE}:{elt.lineno} 元组成员必须是字符串字面量 → {ast.unparse(sub)[:40]}")
                vals.append(None)
            else:
                vals.append(sub.value)
        if None in vals:
            continue
        routes.append((vals[0], vals[1], vals[2], vals[3], elt.lineno))
    return routes


# ------------------------------------------------------------ 收集 Mixin 方法
def _collect_mixin_methods() -> dict:
    """{方法名: [所在文件]}，只收 `*Mixin` 类的直接方法。"""
    out: dict = {}
    for p in sorted(FEATURES_DIR.glob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as err:
            _fail(f"{p.name}: 语法错误 {err}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Mixin"):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        out.setdefault(item.name, []).append(p.name)
    return out


# -------------------------------------------------------------- agent 路由
def _read_agent_routes() -> list:
    """从 `_agent_endpoints()` 的返回字面量里取 (path, method)。"""
    src = (ROOT / AGENT_FILE).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_agent_endpoints":
            fn = node
            break
    if fn is None:
        _fail(f"{AGENT_FILE}: 找不到 _agent_endpoints()（agent 路由登记表）")
        return []
    ret = None
    for stmt in fn.body:
        if isinstance(stmt, ast.Return):
            ret = stmt.value
            break
    if not isinstance(ret, (ast.List, ast.Tuple)):
        _fail(f"{AGENT_FILE}: _agent_endpoints() 必须直接 return 字面量列表")
        return []
    out = []
    for elt in ret.elts:
        if not isinstance(elt, ast.Dict):
            continue
        d = {k.value: v for k, v in zip(elt.keys, elt.values) if isinstance(k, ast.Constant)}
        path, method = d.get("path"), d.get("method")
        if isinstance(path, ast.Constant) and isinstance(method, ast.Constant):
            out.append((path.value, method.value.upper()))
    return out


# ------------------------------------------------------------------ 匹配规则
def _compile(path: str) -> re.Pattern:
    """把 ``/tasks/{task_id}/run`` 变成正则；``{x}`` 只吃一段。"""
    parts = []
    for seg in path.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            parts.append(r"[^/]+")
        else:
            parts.append(re.escape(seg))
    return re.compile("^/" + "/".join(parts) + "$")


def _sample_url(path: str) -> str:
    """用占位段替换 `{x}`，得到一个一定会命中该路由的具体 URL。"""
    segs = []
    for seg in path.strip("/").split("/"):
        segs.append(SAMPLE_SEG if (seg.startswith("{") and seg.endswith("}")) else seg)
    return "/" + "/".join(segs)


def _check_route_specs(routes: list) -> None:
    for path, handler, methods, _summary, line in routes:
        if not path.startswith("/"):
            _fail(f"{API_FILE}:{line} path 必须以 / 开头 → {path}")
        if len(path) > 1 and path.endswith("/"):
            _fail(f"{API_FILE}:{line} path 不能以 / 结尾 → {path}")
        if "//" in path or " " in path:
            _fail(f"{API_FILE}:{line} path 有空段或空格 → {path}")
        if not handler.isidentifier():
            _fail(f"{API_FILE}:{line} handler 不是合法标识符 → {handler}")
        if not _summary.strip():
            _fail(f"{API_FILE}:{line} summary 为空 → {path}")
        parts = [m.strip() for m in methods.split(",") if m.strip()]
        if not parts:
            _fail(f"{API_FILE}:{line} methods 为空 → {path}")
        for m in parts:
            if m not in ALLOWED_METHODS:
                _fail(f"{API_FILE}:{line} 未知 method {m!r} → {path}"
                      f"（必须大写，且只能是 {'/'.join(sorted(ALLOWED_METHODS))}）")


def _check_duplicates(routes: list) -> None:
    seen: dict = {}
    for path, _handler, methods, _summary, line in routes:
        for m in [x.strip().upper() for x in methods.split(",") if x.strip()]:
            key = (path, m)
            if key in seen:
                _fail(f"{API_FILE}:{line} 重复路由 {m} {path}（首次出现在第 {seen[key]} 行，"
                      f"后者会被遮蔽）")
            else:
                seen[key] = line


def _check_handlers(routes: list, methods: dict) -> None:
    for path, handler, _methods, _summary, line in routes:
        if handler not in methods:
            _fail(f"{API_FILE}:{line} handler {handler!r}（{path}）在 features/*.py 的 "
                  f"*Mixin 类里不存在 —— 改名或搬走后路由表没跟上")


def _check_first_match(routes: list) -> None:
    """按书写顺序模拟首次匹配：每条路由必须匹配到自己。"""
    compiled = [(_compile(p), {m.strip().upper() for m in ms.split(",") if m.strip()}, p, line)
                for p, _h, ms, _s, line in routes]
    for path, _handler, methods, _summary, line in routes:
        mine = {m.strip().upper() for m in methods.split(",") if m.strip()}
        url = _sample_url(path)
        for rx, meths, other_path, other_line in compiled:
            if not (meths & mine) or not rx.match(url):
                continue
            if other_line != line:
                _fail(f"{API_FILE}:{line} 路由 {path} 被第 {other_line} 行更早注册的 "
                      f"{other_path} 遮蔽（首次匹配落到它）")
            break


def _check_agent_conflict(routes: list) -> None:
    agent = _read_agent_routes()
    if not agent:
        _fail(f"{AGENT_FILE}: _agent_endpoints() 没有解析到任何路由")
        return
    mine = {(p, m.strip().upper()) for p, _h, ms, _s, _l in routes
            for m in ms.split(",") if m.strip()}
    for path, method in agent:
        if (path, method) in mine:
            _fail(f"{AGENT_FILE}: /agent 路由 {method} {path} 与 {API_FILE} 撞车")


def main() -> int:
    verbose = "--verbose" in sys.argv
    routes = _read_routes()
    if not routes:
        _report(routes, verbose)
        return 1

    _check_route_specs(routes)
    _check_duplicates(routes)
    _check_handlers(routes, _collect_mixin_methods())
    _check_first_match(routes)
    _check_agent_conflict(routes)

    _report(routes, verbose)
    return 0 if not _ERRORS else 1


def _report(routes: list, verbose: bool) -> None:
    if _ERRORS:
        print("❌ API 路由表检查未通过：")
        for e in _ERRORS:
            print("   -", e)
        return
    paths = {r[0] for r in routes}
    wild = sum(1 for r in routes if "{" in r[0])
    print(f"✅ API 路由表 OK：{len(routes)} 条 / {len(paths)} 个 path / "
          f"{wild} 条含路径参数 / handler 全部可达 / 无重复、无遮蔽")
    if verbose:
        for path, handler, methods, _s, line in routes:
            print(f"   {line:>4}  {methods:<9} {path:<44} {handler}")


if __name__ == "__main__":
    sys.exit(main())
