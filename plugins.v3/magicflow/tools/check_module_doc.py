#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模块职责护栏 —— 大模块的 docstring 首行必须说清「装的是什么」。

为什么需要它
------------
``GET /agent/code-dict?section=modules`` 的「职责」字段是**摘模块 docstring 首行**现算的。
所以字典准不准 == docstring 准不准。而 2026-10-10 拍板砍掉「代码字典同步」检查
（``tools/gen_code_dict.py --check``）之后，再没有任何东西强制 docstring 跟上代码，
于是出现**职责写着 A、实际装着 A+B**：

    persistence.py    3104 行  「MagicFlow 持久化模块」                    ← 零信息
    downloader_ops.py 2630 行  「MagicFlow 下载器操作模块」                ← 零信息
    fetcher.py        1493 行  「MagicFlow 站点候选获取模块」              ← 零信息
    tags.py           1042 行  「标签模型 —— 命名 / 解析 / 常量 / 纯函数」
                               ← 实际后半还有 440 行媒体加种编排（调下载器/账本/候选缓存）
    features/core.py  2047 行  「生命周期与调度」
                               ← 实际还兼 log/下载器/站点/任务配置 的入口（全库 700+ 次调用）

后果不是「文档不好看」：判分层时唯一可查的「文件 → 作用」就是它，描述少一半就会判错。
（2026-10-28 争论 tags.py 到底算不算纯函数模块，就是一路错在这里。）

规则（只查大模块；小模块由 ``gen_modules.py`` 的「必须有 docstring」兜住）
------------------------------------------------------------------
  · 行数 ≥ ``LARGE_LINES``(300) 的 .py，模块 docstring **首行非空**；
  · 首行去空白后 ≥ ``MIN_CHARS``(12) 字（防「持久化」「工具」这类单词应付）；
  · 首行不以「模块」/「模块。」结尾（"MagicFlow 持久化模块" 是空话，不是职责）；
  · 首行不能只是文件名本身（如 "downloader_ops"）。

豁免：``ADAPTORS`` 里的路径前缀 —— 留空。站点签到适配器（``signin_sites/*``）这类
"函数签名自明"的文件当前都在 300 行以下，不需要豁免；将来若超线，在此登记并写明理由。

用法：python3 tools/check_module_doc.py [--list]
退出码：0 = 通过；1 = 有违规。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"_backup", "tools", "__pycache__", "dist", "node_modules", ".git"}

LARGE_LINES = 300   # 只有大模块才强制「说清职责」：小文件的首行基本能自明
MIN_CHARS = 12      # 「持久化」「工具」「utils」这类短语不构成职责
ADAPTORS: tuple[str, ...] = ()   # 豁免的路径前缀（如 "signin_sites/"），当前无

BANNED_TAIL = ("模块", "模块。", "module", "module.")


def first_line(text: str) -> str:
    """与 ``codedict._first_line`` 同口径：取第一个非空行。"""
    for ln in (text or "").strip().splitlines():
        if ln.strip():
            return ln.strip()
    return ""


def scan() -> tuple[list[dict], list[str]]:
    """返回（大模块清单, 违规说明）。"""
    rows: list[dict] = []
    violations: list[str] = []
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        posix = rel.as_posix()
        if any(posix.startswith(pre) for pre in ADAPTORS):
            continue
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue          # 语法问题由 preflight 第 1 步 py_compile 报
        lines = src.count("\n") + 1
        if lines < LARGE_LINES:
            continue
        brief = first_line(ast.get_docstring(tree) or "")
        rows.append({"file": posix, "lines": lines, "brief": brief})

        stem = Path(posix).stem
        why = ""
        if not brief:
            why = "缺模块 docstring（字典里的「职责」会是空）"
        elif len(brief) < MIN_CHARS:
            why = f"首行只有 {len(brief)} 字，说不清装的是什么"
        elif brief.rstrip("。").endswith("模块") or brief.lower().rstrip(".").endswith("module"):
            why = "首行是「…模块」这类空话（等于没写职责）"
        elif brief.lower().strip("。") == stem.lower():
            why = "首行只是文件名，没有职责"
        if why:
            violations.append(f"{posix}（{lines} 行）：{why} → 「{brief or '<空>'}」")
    return rows, violations


def main() -> int:
    rows, violations = scan()
    if "--list" in sys.argv:
        for r in rows:
            print(f"{r['lines']:5d}  {r['file']:32s} {r['brief'][:80]}")
        return 0
    print(f"检查大模块（≥{LARGE_LINES} 行）{len(rows)} 个；职责首行不合格 {len(violations)} 个")
    if violations:
        print("\n❌ 职责首行不合格（字典的 modules 节会照抄这些字）：")
        for v in violations:
            print("  " + v)
        print("\n改法：把 docstring 首行写成「装什么 + 还兼了什么」，一行内说完；")
        print("      描述与实际不符的，先改描述（本检查不过就是它在提醒该拆文件了）。")
        return 1
    print("\n✅ 模块职责检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
