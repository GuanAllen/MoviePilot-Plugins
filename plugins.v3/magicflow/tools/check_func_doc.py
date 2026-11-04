#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流（MagicFlow）函数注释护栏 —— 硬护栏 #23（19.10.18 新增）。

背景（2026-10-28 Master 定的约束）
----------------------------------
「在函数构造的时候必须在**固定位置**写注释」——Python 的固定位置就是
**第一行语句处的 docstring**（``ast.get_docstring`` 只认这个位置；写在函数体
上面的 ``#`` 注释不算，它随时会和代码脱节）。

为什么是棘轮（只冻结存量、不管历史）
------------------------------------
实测 2026-10-29：全仓 2456 个函数，去掉函数内嵌套 def（140）与 dunder（59）后
剩 2257 个模块级/方法；按「函数体 ≥4 行」算必写注释的有 1876 个，其中
**353 个缺失（18.8%）**。一次补齐会产生 353 处噪声 diff，把真正的改动淹没，
所以采用方案 A：

  · 存量函数：指纹进 ``tools/.func_doc_baseline.json``，**不再检查**；
  · 新函数：不在基线里 → 必须过下面 4 条；
  · 改动过的函数：函数体指纹变了 → 视同新函数，必须过下面 4 条
    （「代码动过就得把注释补上」，这正是约束的落点）。

4 条坏模式（针对「有注释但不构成信息」）
--------------------------------------
  B1 空话：``初始化``/``工具函数``/``TODO``/``xxx`` 这类占位词，去掉标点后整句命中；
  B2 太薄：首行 ≤ ``MIN_DOC_CHARS``(8) 字，且整个 docstring 只有一行（没有补充）；
  B3 复读：同一个文件里，本步管辖的两个函数 docstring 首行完全相同（复制粘贴）；
  B4 换名：首行把函数名的下划线/驼峰换成空格就完事（``_hr_need`` → "hr need"）。

不查（有意为之）
----------------
  · 函数内嵌套 def（闭包是调用方的一部分，注释应该写在外层）；
  · dunder（``__init__`` 之类名字已自明）；
  · ``tools/`` 与 ``tests/`` 下的脚本（它们是工具，不是产品代码）。

用法
----
  python3 tools/check_func_doc.py              # 检查（preflight 第 23 步）
  python3 tools/check_func_doc.py --verbose    # 顺带打印统计口径
  python3 tools/check_func_doc.py --regen      # 重写基线（只在大规模改动后手工跑）
  python3 tools/check_func_doc.py --list       # 列出当前全部必写集合（排查用）

退出码：0 = 通过；1 = 有违规。
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT
BASELINE = Path(__file__).resolve().parent / ".func_doc_baseline.json"
DEFAULT_BASELINE = BASELINE

SKIP_DIRS = {"tools", "tests", "_backup", "dist", ".build-fe", "node_modules",
             "__pycache__", ".git"}

MIN_BODY_LINES = 4    # 函数体（剥 docstring 后）≥4 行才要求写注释：3 行的转发壳自明
MIN_DOC_CHARS = 8     # 首行 ≤8 字且无补充 → 说不清做什么

BANNED_EXACT = {
    "初始化", "构造函数", "初始化函数", "工具函数", "辅助函数", "工具方法",
    "处理方法", "入口函数", "主函数", "执行", "处理", "获取", "设置",
    "todo", "fixme", "xxx", "无", "暂无", "同上", "略",
}
FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


# ────────────────────────────── 采集 ──────────────────────────────
def _body_lines(node: ast.AST) -> int:
    """函数体行数（剥掉 docstring 后，首语句到末语句的跨度）。"""
    body = list(getattr(node, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return 0
    return body[-1].end_lineno - body[0].lineno + 1


def _fingerprint(node: ast.AST) -> str:
    """函数体指纹（含参数与装饰器；不含行号，所以纯搬运不会变）。"""
    clone = ast.Module(body=node.body, type_ignores=[])
    payload = ast.dump(clone, annotate_fields=False) + "|" + ast.dump(node.args, annotate_fields=False)
    return hashlib.md5(payload.encode()).hexdigest()[:12]


def _walk_functions(tree: ast.AST):
    """产出 (node, in_func)；in_func=True 表示定义在另一个函数体内（真嵌套）。"""
    def rec(parent, in_func):
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, FUNC_NODES):
                yield child, in_func
                yield from rec(child, True)
            else:
                yield from rec(child, in_func)
    yield from rec(tree, False)


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _first_line(doc: str) -> str:
    for line in (doc or "").strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def _bare(text: str) -> str:
    """去掉标点空白与尾缀，用于和占位词表比对。"""
    out = text.strip().lower()
    for ch in "。，,.!！:：;；~～ 　":
        out = out.replace(ch, "")
    return out


def collect() -> list[dict]:
    """扫描全仓，返回全部「必写注释」函数（未做基线过滤）。"""
    rows: list[dict] = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue            # 语法问题由 preflight 第 1 步 py_compile 报
        posix = rel.as_posix()
        for node, in_func in _walk_functions(tree):
            if in_func or _is_dunder(node.name):
                continue
            if _body_lines(node) < MIN_BODY_LINES:
                continue
            doc = ast.get_docstring(node) or ""
            rows.append({
                "file": posix,
                "line": node.lineno,
                "name": node.name,
                "doc": doc,
                "first": _first_line(doc),
                "fp": _fingerprint(node),
            })
    # 键里带同文件同名函数的出现序号（两个类里各有一个 _run 是可能的）
    seen: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["file"], row["name"])
        seen[key] = seen.get(key, 0) + 1
        row["key"] = f"{row['file']}::{row['name']}::{seen[key]}"
    return rows


# ────────────────────────────── 规则 ──────────────────────────────
def rule_violations(rows: list[dict], enforced: list[dict]) -> list[str]:
    """对 enforced（新函数 + 改动过的函数）跑 B1–B4，返回违规说明。"""
    problems: list[str] = []

    for row in enforced:
        where = f"{row['file']}:{row['line']} {row['name']}()"
        first = row["first"]
        if not first:
            problems.append(f"{where} —— 缺 docstring（函数体 ≥{MIN_BODY_LINES} 行必须有，"
                            f"写在 def 下一行的第一句）")
            continue
        bare = _bare(first)
        if bare in BANNED_EXACT:
            problems.append(f"{where} —— B1 空话：「{first}」不含任何信息")
            continue
        lines = [ln for ln in row["doc"].strip().splitlines() if ln.strip()]
        if len(first) <= MIN_DOC_CHARS and len(lines) <= 1:
            problems.append(f"{where} —— B2 太薄：首行只有 {len(first)} 字且无补充说明")
            continue
        name_norm = row["name"].strip("_").replace("_", " ").lower()
        if bare.replace(" ", "") == name_norm.replace(" ", "") and name_norm:
            problems.append(f"{where} —— B4 换名：首行只是函数名换成空格，等于没写")
            continue

    # B3 同文件首行重复（只在 enforced 内部比，避免历史噪声）
    by_file: dict[str, list[dict]] = {}
    for row in enforced:
        if row["first"]:
            by_file.setdefault(row["file"], []).append(row)
    for posix, group in by_file.items():
        buckets: dict[str, list[dict]] = {}
        for row in group:
            buckets.setdefault(row["first"], []).append(row)
        for first, same in buckets.items():
            if len(same) < 2:
                continue
            names = "、".join(f"{r['name']}({r['line']})" for r in same)
            problems.append(f"{posix} —— B3 复读：{names} 的注释首行完全相同「{first}」")

    return problems


# ────────────────────────────── 基线 ──────────────────────────────
def load_baseline() -> dict[str, str]:
    if not BASELINE.is_file():
        return {}
    try:
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    funcs = data.get("functions")
    return funcs if isinstance(funcs, dict) else {}


def save_baseline(rows: list[dict], total_all: int) -> None:
    payload = {
        "_note": "函数注释棘轮基线：这些函数体指纹被冻结，不再检查 docstring。"
                 "重写用 python3 tools/check_func_doc.py --regen",
        "min_body_lines": MIN_BODY_LINES,
        "functions": {r["key"]: r["fp"] for r in rows},
    }
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8", newline="")
    print(f"基线已写入 {BASELINE.name}：{len(rows)} 个函数（全仓必写集合 {total_all} 个）")


# ────────────────────────────── 主流程 ──────────────────────────────
def main() -> int:
    global ROOT, BASELINE
    args = sys.argv[1:]
    if "--root" in args:
        ROOT = Path(args[args.index("--root") + 1]).resolve()   # 仅用于负样本自测
    if "--baseline" in args:
        BASELINE = Path(args[args.index("--baseline") + 1]).resolve()   # 同上
    rows = collect()

    if "--regen" in args:
        if ROOT != DEFAULT_ROOT and BASELINE == DEFAULT_BASELINE:
            print("❌ 沙盒（--root）不得改写真实基线；请同时给 --baseline 指定沙盒路径")
            return 1
        save_baseline(rows, len(rows))
        return 0

    if "--list" in args:
        for row in rows:
            flag = "" if row["first"] else "  ★缺"
            print(f"{row['file']}:{row['line']} {row['name']:34s} {row['first'][:60]}{flag}")
        print(f"\n共 {len(rows)} 个必写注释的函数")
        return 0

    baseline = load_baseline()
    if not baseline:
        print("❌ 基线缺失（tools/.func_doc_baseline.json）")
        print("   首次启用请跑：python3 tools/check_func_doc.py --regen")
        return 1

    enforced, frozen, changed = [], [], []
    for row in rows:
        old = baseline.get(row["key"])
        if old is None:
            enforced.append(row)                 # 新函数
        elif old != row["fp"]:
            changed.append(row)                  # 函数体改过，视同新函数
            enforced.append(row)
        else:
            frozen.append(row)

    stale = sorted(set(baseline) - {r["key"] for r in rows})

    if "--verbose" in args:
        print(f"必写集合 {len(rows)} 个 = 冻结 {len(frozen)} + 新增 {len(enforced) - len(changed)} "
              f"+ 改动 {len(changed)}")
        print(f"基线 {len(baseline)} 条，已失效（函数被删/降级）{len(stale)} 条")

    problems = rule_violations(rows, enforced)
    if problems:
        print(f"❌ 函数注释违规 {len(problems)} 处（新增/改动过的函数必须写清楚 docstring）")
        for item in problems:
            print("  " + item)
        print("\n改法：在 def 的下一行第一句写「做什么 + 为什么」，不要复述函数名。")
        print("      存量函数不在此步范围（已冻结进基线）。")
        return 1

    if stale and "--verbose" in args:
        print(f"ℹ 基线里 {len(stale)} 条已不存在（函数被删或函数体缩到 {MIN_BODY_LINES} 行以下）：")
        for key in stale[:10]:
            print(f"    {key}")
        if len(stale) > 10:
            print(f"    …… 另 {len(stale) - 10} 条")

    print(f"✅ 函数注释检查通过（必写 {len(rows)} 个，本次检查 {len(enforced)} 个新增/改动）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
