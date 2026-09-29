#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""未定义全局名检查（护栏④）—— 用 symtable 做真作用域解析。

抓的是「代码里用了、但本模块没导入也没定义、也不是内置」的名字（= 运行时 NameError）。
典型来源：机械拆分/精简 import 时误删，或新增调用忘了 import。

用法：python3 tools/check_names.py [--json]
退出码：0 通过；1 有嫌疑。
"""
from __future__ import annotations

import builtins
import json
import symtable
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"_backup", "tools", "__pycache__", "dist", "node_modules", ".git"}
BUILTINS = set(dir(builtins)) | {"__name__", "__file__", "__doc__", "__package__", "__all__", "__builtins__", "__class__", "_"}


def module_symbols(table: symtable.SymbolTable) -> set[str]:
    return {s.get_name() for s in table.get_symbols()}


def bound_names(table: symtable.SymbolTable) -> set[str]:
    """本作用域**绑定**的名字（赋值/参数/import/def/class），不含仅被引用的名字。"""
    return {
        s.get_name()
        for s in table.get_symbols()
        if s.is_assigned() or s.is_parameter() or s.is_imported() or s.is_namespace()
    }


def scan_scope(
    table: symtable.SymbolTable, module_names: set[str], enclosing: set[str], out: list[str]
) -> None:
    local = bound_names(table)
    for sym in table.get_symbols():
        name = sym.get_name()
        if not sym.is_referenced():
            continue
        if sym.is_assigned() or sym.is_parameter() or sym.is_imported() or sym.is_namespace():
            continue
        if name in local or name in enclosing or name in module_names or name in BUILTINS:
            continue
        if sym.is_free() or sym.is_global():
            out.append(name)
    child_scope_names = local | enclosing | module_names
    for child in table.get_children():
        if child.get_type() == "class":
            scan_scope(child, module_names, child_scope_names, out)
        else:
            # 函数作用域：闭包可捕获外层；模块名始终可见
            scan_scope(child, module_names, local | enclosing, out)


def files() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        out.append(p)
    return out


def main() -> int:
    problems: list[dict] = []
    for p in files():
        src = p.read_text(encoding="utf-8")
        table = symtable.symtable(src, str(p), "exec")
        names = module_symbols(table)
        found: list[str] = []
        for child in table.get_children():
            scan_scope(child, names, set(), found)
        for name in sorted(set(found)):
            # 类作用域内的注解/装饰器等偶发命中，用源码行号无法精确定位 → 只报名字
            problems.append({"file": str(p.relative_to(ROOT)), "name": name})
    if "--json" in sys.argv:
        print(json.dumps(problems, ensure_ascii=False, indent=1))
    elif problems:
        by_file: dict[str, list[str]] = {}
        for it in problems:
            by_file.setdefault(it["file"], []).append(it["name"])
        for f, ns in by_file.items():
            print(f"❌ {f}: {', '.join(ns)}")
        print(f"\n未定义名检查失败：{len(problems)} 处（这些名字在运行时大概率 NameError）")
    else:
        print("✅ 未定义名检查通过")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
