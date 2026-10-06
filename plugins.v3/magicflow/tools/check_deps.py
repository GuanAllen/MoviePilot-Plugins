#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流（MagicFlow）依赖方向检查器 —— 硬护栏 #1。

规则（契约）：
  层级 L0  leaf/基础设施：kvstore.py, fingerprint.py, models.py, persistence.py, utils 等
  层级 L1  领域模块：bonus.py, collect.py, fetcher.py, sites/*, rulepack.py, live_stats.py ...
  层级 L2  features/*（mixin）
  层级 L3  __init__.py（组装）

  允许：L(n) → L(m)，m <= n（同层允许，但不能成环）。
  禁止：
    - 任何模块 import `magicflow` 包本身（= `__init__.py`），会成环；
    - L0/L1 模块 import features/*；
    - 模块级（顶层）import 成环。

用法：python3 tools/check_deps.py [--verbose] [--json]
退出码：0 = 通过；1 = 有违规。
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = "magicflow"

# 层级定义：文件（相对 ROOT 的 POSIX 路径）→ 层号
L0 = {
    "kvstore.py", "fingerprint.py", "models.py", "persistence.py",
    "douban.py", "rulepack.py", "sitecap.py", "dtier.py",
    "db.py", "tables.py",   # 插件自有表（SQLAlchemy 模型）—— 纯基础设施
    "codedict.py",          # 代码字典：纯 ast 解析自身源码（11.12.0）
}
L1 = {
    "bonus.py", "collect.py", "fetcher.py", "live_stats.py", "fallback.py",
    "downloader_ops.py", "cloud_archive.py", "crossseed.py", "iyuu_cloud.py",
    "recommend.py", "signin.py", "tags.py",
    "ledger.py",   # 种子/资源台账（SQLAlchemy 后端，依赖 tags/common）
}
L2_PREFIX = "features/"
L1_PREFIXES = ("sites/", "signin_sites/", "claim_sites/")   # L1 域的包（站点解析 / 站点签到适配器 / 站点认领写动作）
L3 = {"__init__.py", "common.py", "dupgate.py"}


def layer_of(rel: str) -> int | None:
    """层级查询；未登记 → None（登记制硬护栏）。"""
    if rel in L3:
        return 3
    if rel in L0:
        return 0
    if rel in L1:
        return 1
    if rel.startswith(L2_PREFIX):
        return 2
    if rel.startswith(L1_PREFIXES):
        return 1
    return None


def mod_name(rel: str) -> str:
    """文件 → 逻辑模块名（用于依赖图）：features/x.py → features.x；x.py → x"""
    rel = rel[:-3] if rel.endswith(".py") else rel
    rel = rel.replace("/__init__", "")
    return rel.replace("/", ".")


def module_of_rel(rel: str) -> str:
    """相对路径 → 可以被 import 的点号名（相对 magicflow 包）：features/x.py → magicflow.features.x"""
    base = rel[:-3] if rel.endswith(".py") else rel
    if base.endswith("/__init__"):
        base = base[: -len("/__init__")]
    return SELF + "." + base.replace("/", ".")


def resolve(cur_mod: str, target: str, level: int, is_pkg: bool = False) -> str | None:
    """把相对 import 解析成绝对模块名（以 magicflow 为根）。

    Python 语义：`from .x import y` 的 level=1 表示「当前包」；
    对 `pkg/__init__.py` 来说「当前包」= pkg 自身（is_pkg=True 时层级要少减 1）。
    """
    if level == 0:
        return target if target else None
    cur = cur_mod.split(".")
    eff = level - (1 if is_pkg else 0)
    if eff > len(cur):
        return None
    base = cur[: len(cur) - eff] if eff else cur
    parts = base + ([target] if target else [])
    return ".".join(parts)


def collect() -> dict:
    files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*.py")
        if "node_modules" not in p.parts
        and "_backup" not in p.parts
        and "__pycache__" not in p.parts
        and not p.relative_to(ROOT).as_posix().startswith("tools/")
    )
    known = {
        SELF + "." + (m if m != "__init__" else "")
        for m in (mod_name(f) for f in files)
    }
    known = {k.rstrip(".") for k in known}
    known |= {SELF}
    graph: dict[str, set[str]] = {mod_name(f): set() for f in files}
    raw: list[tuple[str, str, int, int]] = []
    for f in files:
        try:
            tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
        except SyntaxError as e:  # noqa: PERF203
            print(f"❌ 语法错误 {f}: {e}")
            continue
        cur = SELF + "." + (f[:-3] if f.endswith(".py") else f).replace("/", ".")
        is_pkg = f.endswith("/__init__.py") or f == "__init__.py"
        if is_pkg:
            cur = cur[: -len(".__init__")]
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = resolve(cur, node.module or "", node.level, is_pkg)
                if not base:
                    continue
                if node.module:
                    cands = [base]
                else:
                    # `from . import A, B`：逐个名字判断是不是本插件模块
                    cands = [base + "." + a.name for a in node.names]
                for c in cands:
                    c = c.rstrip(".")
                    if c in known:
                        raw.append((f, c.replace(SELF + ".", "") if c != SELF else "__init__", 0, node.lineno))
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == SELF or a.name.startswith(SELF + "."):
                        raw.append((f, a.name[len(SELF) + 1:] or "__init__", 0, node.lineno))
    for f, dep, _lvl, _ln in raw:
        graph.setdefault(mod_name(f), set()).add(dep)
    return {"files": files, "graph": graph, "raw": raw}


def main() -> int:
    verbose = "--verbose" in sys.argv
    data = collect()
    files, graph = data["files"], data["graph"]
    rel_of = {mod_name(f): f for f in files}
    violations: list[str] = []

    # 1) 禁止 import 包本身（__init__）
    for mod, deps in graph.items():
        if "__init__" in deps:
            violations.append(f"[包自引用] {rel_of.get(mod, mod)} import 了 magicflow 包本身（→ __init__），会成环")

    # 1b) 登记制：每个模块必须在层级表里登记
    for f in files:
        if layer_of(f) is None:
            violations.append(
                f"[未登记] {f} 不在 L0/L1/L2/L3 层级表 —— 新模块必须先登记（tools/check_deps.py）"
            )

    # 2) L0/L1 不得 import features/*
    for mod, deps in graph.items():
        lay = layer_of(rel_of.get(mod, mod + ".py"))
        if lay is not None and lay <= 1:
            for d in deps:
                if d == "features" or d.startswith("features."):
                    violations.append(f"[层级倒挂] L{lay} 模块 {rel_of.get(mod, mod)} import 了 {d}")

    # 3) 环检测（模块级）
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for v in sorted(graph.get(u, ())):
            if v not in graph and "." in v:
                # 直接指向子模块名（如 sites.rules 存在时 ok；不存在则跳过）
                continue
            if v not in graph:
                continue
            if color.get(v, 0) == 1:
                cyc = stack[stack.index(v):] + [v]
                violations.append("[循环依赖] " + " → ".join(cyc))
            elif color.get(v, 0) == 0:
                dfs(v)
        stack.pop()
        color[u] = 2

    for m in sorted(graph):
        if color.get(m, 0) == 0:
            dfs(m)

    print(f"检查模块 {len(files)} 个；依赖边 {sum(len(v) for v in graph.values())} 条")
    if verbose:
        for m in sorted(graph):
            print(f"  {m:28s} → {', '.join(sorted(graph[m])) or '-'}")
    if violations:
        print(f"\n❌ 发现 {len(violations)} 处违规：")
        for v in violations:
            print("  " + v)
        return 1
    print("\n✅ 依赖方向检查通过")
    return 0


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps({k: sorted(v) for k, v in collect()["graph"].items()}, ensure_ascii=False, indent=1, sort_keys=True))
        raise SystemExit(0)
    raise SystemExit(main())
