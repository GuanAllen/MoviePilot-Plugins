#!/usr/bin/env python3
"""第 22 步：import 名字可达性校验（护栏⑫）。

背景（2026-10-28 事故）：把 ``recommend._norm`` 收进 ``norm.py`` 后，只正则扫了
单行 ``import _norm``，漏掉多行括号形式的 ``from ..recommend import (..., _norm, ...)``。
``ast.parse`` 通过、``py_compile`` 通过、语法检查全绿，但生产 ``import`` 时直接
``ImportError: cannot import name '_norm'``，插件连续 8 次加载失败，下线约 13 分钟。

这条护栏补的就是这个盲区：**语法正确 ≠ 符号存在**。

判据（只查项目内模块，外部包放行）：
  R1  ``from X import a, b`` 里每个名字，必须在 X 的**模块级作用域**能取到
  R2  模块级作用域包括 ``try:`` / ``if:`` 块内的定义（``common.py`` 的
      ``_MFEventType`` 就在 ``try`` 里，不是漏写）
  R3  ``from pkg import sub`` 若 ``pkg/sub.py`` 或 ``pkg/sub/`` 存在，视为子模块放行
  R4  ``import *`` 不校验（无法静态判定导出面）

用法::

    python3 tools/check_import_names.py            # 只报错
    python3 tools/check_import_names.py --verbose  # 打印统计
"""

from __future__ import annotations

import ast
import pathlib
import sys
import typing

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 不参与校验的目录（测试桩/构建产物/依赖）
SKIP_DIRS = frozenset({
    "tools", "dist", ".build-fe", "node_modules", "__pycache__", ".git", "tests",
})

# 模块级作用域会下钻的复合语句（块内定义在模块级可见）
_SCOPE_NODES = (ast.Try, ast.If)


def module_name(path: pathlib.Path) -> str:
    """项目内文件 → 点分模块名（``features/api.py`` → ``features.api``）。"""
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def collect_top_names(tree: ast.Module) -> set[str]:
    """收集模块级可访问的名字，含 try/if 块内的定义。"""
    names: set[str] = set()

    def walk(stmts: typing.Sequence[ast.stmt]) -> None:
        for node in stmts:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, _SCOPE_NODES):
                walk(node.body)
                for handler in getattr(node, "handlers", []) or []:
                    walk(handler.body)
                walk(getattr(node, "orelse", []) or [])
                walk(getattr(node, "finalbody", []) or [])

    walk(tree.body)
    return names


def resolve_target(current: str, node: ast.ImportFrom) -> str | None:
    """把 ``from ..x import y`` 解析为绝对模块名。"""
    if not node.level:
        return node.module
    parts = current.split(".")
    # features.api → from ..norm  ⇒ level=2, 去掉 features + api 两层里的 1 层（包）
    base = parts[: len(parts) - node.level] if node.level <= len(parts) else []
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base) if base else None


def is_submodule(pkg: str, name: str) -> bool:
    """``from pkg import name`` 中 name 是否为 pkg 下的子模块。"""
    base = ROOT.joinpath(*pkg.split("."), name)
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def main() -> int:
    global ROOT
    verbose = "--verbose" in sys.argv
    if "--root" in sys.argv:
        ROOT = pathlib.Path(sys.argv[sys.argv.index("--root") + 1]).resolve()

    defined: dict[str, set[str]] = {}
    trees: dict[str, ast.Module] = {}
    files: dict[str, pathlib.Path] = {}

    for path in sorted(ROOT.rglob("*.py")):
        if set(path.relative_to(ROOT).parts) & SKIP_DIRS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue  # 语法错误由别的步骤负责
        mod = module_name(path)
        defined[mod] = collect_top_names(tree)
        trees[mod] = tree
        files[mod] = path

    problems: list[str] = []
    checked = 0
    for mod, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = resolve_target(mod, node)
            if not target or target not in defined:
                continue  # 外部包或项目内不存在的模块
            for alias in node.names:
                if alias.name == "*":
                    continue
                checked += 1
                if alias.name in defined[target] or is_submodule(target, alias.name):
                    continue
                rel = "." * (node.level or 0) + (node.module or "")
                problems.append(
                    f"  ❌ {files[mod].relative_to(ROOT)}:{node.lineno}\n"
                    f"       from {rel} import {alias.name}\n"
                    f"       → 目标模块 {target} 的模块级作用域里没有 {alias.name}"
                )

    if problems:
        print(f"发现 {len(problems)} 处 import 指向不存在的名字（生产会 ImportError）：")
        print("\n".join(problems))
        print("\n修法：删掉该名字的 import，或把调用方改到新位置（如 norm.py）。")
        return 1

    if verbose:
        print(f"校验 {len(defined)} 个模块 / {checked} 个 import 名字，全部可达。")
    else:
        print(f"import 名字可达性：{len(defined)} 个模块 / {checked} 个名字，全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
