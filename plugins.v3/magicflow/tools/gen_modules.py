#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模块登记表生成 / 校验 —— 硬护栏 #2（登记制）。

规则：
  * 插件内每个 .py **必须**有模块 docstring（说明职责）；
  * 每个模块必须出现在 `docs/MODULES-REGISTRY.md`（本工具生成，勿手改）；
  * 新增/删除模块后跑 `python3 tools/gen_modules.py` 重新生成，然后 `--check` 必须通过。

用法：
  python3 tools/gen_modules.py           # 生成/更新 docs/MODULES-REGISTRY.md
  python3 tools/gen_modules.py --check   # 校验是否已同步（CI/提交前跑）
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_deps import L0, L1, L2_PREFIX, L3, ROOT, SELF, collect, layer_of, mod_name  # noqa: E402

OUT = ROOT / "docs" / "MODULES-REGISTRY.md"
SKIP_DIRS = {"_backup", "tools", "__pycache__", "dist", "node_modules", ".git"}

LAYER_NAME = {0: "L0 叶子/基础设施", 1: "L1 领域", 2: "L2 features(mixin)", 3: "L3 组装"}


def modules() -> list[str]:
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return out


def describe(rel: str) -> dict:
    src = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc = ast.get_docstring(tree) or ""
    brief = doc.strip().split("\n")[0].strip() if doc else ""
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    funcs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    methods = sum(
        len([x for x in n.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))])
        for n in tree.body
        if isinstance(n, ast.ClassDef)
    )
    return {
        "rel": rel,
        "lines": src.count("\n") + 1,
        "layer": layer_of(rel),
        "brief": brief,
        "classes": classes,
        "top_funcs": funcs,
        "methods": methods,
        "has_doc": bool(brief),
    }


def render() -> str:
    data = collect()
    graph = {k: sorted(v) for k, v in data["graph"].items()}
    rows = [describe(r) for r in modules()]
    rows.sort(key=lambda r: (r["layer"] if r["layer"] is not None else 9, r["rel"]))
    total = sum(r["lines"] for r in rows)

    L = []
    L.append("# 魔流 · 模块登记表（自动生成，勿手改）")
    L.append("")
    L.append("> 由 `python3 tools/gen_modules.py` 生成；提交前用 `--check` 校验。")
    L.append("> 硬护栏：**插件内每个 .py 必须有模块 docstring**，且必须出现在本表。")
    L.append(f"> 模块 {len(rows)} 个 / 合计 {total} 行。")
    L.append("")
    L.append("| 层级 | 模块 | 行数 | 职责（模块 docstring 首行） | 依赖 |")
    L.append("| ---- | ---- | ---- | ---------------------------- | ---- |")
    for r in rows:
        lay = LAYER_NAME.get(r["layer"], "未登记")
        deps = graph.get(mod_name(r["rel"]), [])
        deps_txt = f"{len(deps)}" if deps else "-"
        brief = r["brief"].replace("|", "\\|") or "⚠️ 缺 docstring"
        L.append(f"| {lay} | `{r['rel']}` | {r['lines']} | {brief} | {deps_txt} |")
    L.append("")
    L.append("## 缺 docstring 的模块（必须先补）")
    L.append("")
    missing = [r["rel"] for r in rows if not r["has_doc"]]
    L.append("无。" if not missing else "\n".join(f"- `{m}`" for m in missing))
    L.append("")
    return "\n".join(L)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur.strip() != text.strip():
            print("❌ docs/MODULES-REGISTRY.md 与代码不一致 → 跑 python3 tools/gen_modules.py 重新生成")
            return 1
        print("✅ 模块登记表已同步")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)}（{len(text.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
