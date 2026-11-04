#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流（MagicFlow）数据清洗重复实现检查器 —— 硬护栏 #20（19.10.16 新增）。

背景：
    生产代码 490 个模块级短函数里，完全重复集中在「文本归一 / 取第一个数字 /
    数值有效性 / 当前时间」四类，分散在 8 个文件。它们各自重写的原因不是语义
    不同，而是**不知道别处已经有**。19.10.16 已收敛到 L0 ``norm.py``。

本护栏只管**增量**，不管存量（存量已清空，故基线为空）：

  R1 同名：``norm.py`` 之外，任何文件（含函数内嵌套 def）不得定义与公共 API
           同名的函数——同名会造成遮蔽，读起来像在用公共实现，实际是局部的
           （★ 19.10.16 实测：features/formula.py 就踩过，且改名时差点把
            调用方解析到公共版，静默改变归一规则）。
  R2 同实现：任何文件的函数体（剥 docstring 后）与 ``norm.py`` 某个公共函数
            AST 完全相同 → 换名字重写一遍也算重复，照抓。

不抓（有意为之）：
  - ``set_collect`` 之类**依赖注入口**（改模块全局量，不是数据清洗）；
  - 语义域已分化的归一（如 ``_title_norm`` 保留空格 + 剥方括号前缀，
    与 ``norm_key`` 删除分隔符 + 保留中文是两个东西）。

用法：python3 tools/check_norm_dup.py [--verbose] [--json]
退出码：0 = 通过；1 = 有违规。
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"tools", "tests", "dist", ".build-fe", "node_modules", "__pycache__", ".git"}

# norm.py 的公共 API（R1 依据）
PUBLIC_API = ("norm_key", "first_num", "float_ok", "now_iso")


def _strip_doc(body):
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _fingerprint(body):
    return ast.dump(ast.Module(body=_strip_doc(list(body)), type_ignores=[]),
                    annotate_fields=False)


def _norm_api_fingerprints():
    """读 norm.py，取公共函数的实现指纹。"""
    src = (ROOT / "norm.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            out[_fingerprint(node.body)] = node.name
    return out


def _iter_py():
    for p in sorted(ROOT.rglob("*.py")):
        if set(p.parts) & SKIP_DIRS:
            continue
        yield p


def run(verbose: bool = False):
    fp2api = _norm_api_fingerprints()
    if not fp2api:
        print("❌ norm.py 未找到或无公共函数")
        return 1

    r1, r2 = [], []
    for p in _iter_py():
        rel = p.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as e:
            print(f"❌ {rel} 语法错误: {e}")
            return 1
        if rel == "norm.py":
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            where = "嵌套" if node.col_offset > 0 else "模块级"
            # R1 同名
            if node.name in PUBLIC_API:
                r1.append({"file": rel, "line": node.lineno, "name": node.name,
                           "where": where})
            # R2 同实现
            api = fp2api.get(_fingerprint(node.body))
            if api and node.name != api:
                r2.append({"file": rel, "line": node.lineno, "name": node.name,
                           "where": where, "same_as": api})

    total = len(r1) + len(r2)
    if verbose or total:
        print(f"norm.py 公共 API {len(PUBLIC_API)} 个: {', '.join(PUBLIC_API)}")
    for it in r1:
        print(f"  [R1 同名] {it['file']}:{it['line']} {it['where']} def {it['name']}() "
              f"—— 会遮蔽 norm.norm_key 等公共实现，改名或改用 import")
    for it in r2:
        print(f"  [R2 同实现] {it['file']}:{it['line']} {it['where']} def {it['name']}() "
              f"—— 与 norm.{it['same_as']} 一字不差，改为 from .norm import {it['same_as']}")

    if total == 0:
        if verbose:
            print("✅ 无本地重复实现（基线为空）")
        return 0
    print(f"\n❌ 共 {total} 处重复实现（R1 {len(r1)} / R2 {len(r2)}）")
    return 1


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    verbose = "--verbose" in args
    if as_json:
        fp2api = _norm_api_fingerprints()
        r1, r2 = [], []
        for p in _iter_py():
            rel = p.relative_to(ROOT).as_posix()
            if rel == "norm.py":
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                where = "嵌套" if node.col_offset > 0 else "模块级"
                if node.name in PUBLIC_API:
                    r1.append({"file": rel, "line": node.lineno, "name": node.name, "where": where})
                api = fp2api.get(_fingerprint(node.body))
                if api and node.name != api:
                    r2.append({"file": rel, "line": node.lineno, "name": node.name,
                               "where": where, "same_as": api})
        print(json.dumps({"r1_same_name": r1, "r2_same_body": r2}, ensure_ascii=False, indent=2))
        return 1 if (r1 or r2) else 0
    return run(verbose=verbose)


if __name__ == "__main__":
    sys.exit(main())
