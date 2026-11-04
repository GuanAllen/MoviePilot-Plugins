#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流（MagicFlow）固定偏移切片检查器 —— 硬护栏 #21（19.10.16 新增）。

规则来源（用户 2026-10-28 定的硬约束）：

  1. 字符串 / 行文本处理**禁止**用固定偏移切片（``s[:-1]``、``s[:-2]``）删换行符。
     删换行只能用 ``removesuffix("\\n")`` / ``rstrip("\\r\\n")``。
  2. 按行读取文件时要区分【行内容】和【行终止符】。
  3. 固定切片只允许在「明确知道长度、业务上确定要截断有效内容」时用，
     **使用前必须加注释说明**。
  4. 逐行注释、代码不能跨行粘连，不能出现下一行代码被合并进上一行注释。

为什么要机械拦：
    19.10.16 实踩过——用 ``old[:-2]`` 削掉集合字面量的 ``\\n}`` 时，新行被拼进
    上一行的**注释尾部**，语法仍然通过、AST 仍然合法，但集合里就是没有那个元素
    （``check_deps.py`` 的 ``norm.py`` L0 登记因此静默失效）。
    这类错误**不会报错**，只能靠护栏。

检测项：
  R1 固定负偏移切片（``x[:-N]``，N=1..9）必须在本行或紧邻上一行有注释说明，
     否则报错——要么改用 removesuffix/rstrip，要么写明业务截断意图。
  R2 若切片对象名/上下文指向文本（line/text/s/src/content/row/ln 等），
     额外提示「删换行只能用 removesuffix/rstrip」。

用法：python3 tools/check_slice_guard.py [--verbose]
退出码：0 = 通过；1 = 有违规。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"tests", "dist", ".build-fe", "node_modules", "__pycache__", ".git"}

# 名字里含这些片段 → 大概率是文本/行，删尾部应走 removesuffix/rstrip
TEXT_HINTS = ("line", "text", "content", "lines", "src", "source", "row", "ln",
              "doc", "desc", "msg", "message", "title", "body")


def _is_fixed_neg_slice(node):
    """识别 x[:-N]（N 为正整数常量，无 lower、无 step）。"""
    if not isinstance(node, ast.Subscript):
        return None
    sl = node.slice
    if not isinstance(sl, ast.Slice) or sl.lower is not None or sl.step is not None:
        return None
    up = sl.upper
    if isinstance(up, ast.UnaryOp) and isinstance(up.op, ast.USub) \
            and isinstance(up.operand, ast.Constant) and isinstance(up.operand.value, int):
        return up.operand.value
    return None


def _base_name(node):
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.value if isinstance(node, ast.Attribute) else \
            (node.func if isinstance(node, ast.Call) else node.value)
    return node.id.lower() if isinstance(node, ast.Name) else ""


def run(verbose: bool = False) -> int:
    hits = []
    scanned = 0
    for p in sorted(ROOT.rglob("*.py")):
        if set(p.parts) & SKIP_DIRS:
            continue
        rel = p.relative_to(ROOT).as_posix()
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"❌ {rel} 无法解析: {e}")
            return 1
        scanned += 1
        lines = src.splitlines()
        commented = set()   # 已经带注释的行号（1-based）
        for i, ln in enumerate(lines, 1):
            if "#" in ln:
                commented.add(i)
        for node in ast.walk(tree):
            n = _is_fixed_neg_slice(node)
            if not n:
                continue
            ln = node.lineno
            # 本行有注释、或紧邻上一行有注释 → 视为已说明
            if ln in commented or (ln - 1) in commented:
                continue
            base = _base_name(node.value)
            is_text = any(h in base for h in TEXT_HINTS)
            hits.append({"file": rel, "line": ln, "n": n, "base": base or "?",
                         "is_text": is_text})

    for h in hits:
        tag = "R2 文本" if h["is_text"] else "R1"
        tip = ("删换行/后缀只能用 removesuffix(\"\\n\") 或 rstrip(\"\\r\\n\")"
               if h["is_text"] else
               "若为业务截断，请在使用前加注释说明；删后缀请用 removesuffix")
        print(f"  [{tag}] {h['file']}:{h['line']}  {h['base']}[:-{h['n']}]  —— {tip}")

    if not hits:
        if verbose:
            print(f"✅ 固定偏移切片护栏通过（扫描 {scanned} 个文件，均带注释或已用 removesuffix）")
        return 0
    print(f"\n❌ 共 {len(hits)} 处未加说明的固定偏移切片")
    return 1


if __name__ == "__main__":
    sys.exit(run(verbose="--verbose" in sys.argv))
