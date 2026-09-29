#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""契约检查（硬护栏）：把「一个职责 = 一个真值源」变成可以跑的规则。

R1 运行状态：`.enabled` 只能由 `common.py` 的访问器读写
   - 允许出现的文件：`common.py`（真值源本体）、`models.py`（对外 payload/schema 定义）
   - 任何文件里允许的行内例外：`payload.enabled` / `self._enabled` /
     `client.enabled` / `iyuu_client.enabled`（都不是任务运行状态）
R2 运行状态：不得拿 run_mode 与字面量做比较（== / !=），一律用访问器

用法：python3 tools/check_contracts.py [--json]
退出码：0 通过；1 有违规。
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"_backup", "tools", "__pycache__", "dist", "node_modules", ".git", "tests"}

# ---- R1 -------------------------------------------------------------------
ENABLED_OWNERS = {"common.py", "models.py"}
ENABLED_LINE_ALLOW = re.compile(
    r"\b(payload|req|request|body|client|self|[a-z_]*client)\.enabled\b"
    r"|\.enabled\s*=\s*enabled_of_run_mode\("
)
# ---- R3 -------------------------------------------------------------------
# 契约②：取种只能走 `_acquire_source`（唯一入口）；`_crossseed_start` 只能被
# reuse.py 的入口和自己在 crossseed.py 里的定义引用。
CROSSSEED_CALL = re.compile(r"_crossseed_start\s*\(")
CROSSSEED_ALLOW = {"features/reuse.py", "features/crossseed.py"}
# ---- R2 -------------------------------------------------------------------
RUNMODE_LITERAL_CMP = re.compile(
    r"run_mode[^\n]{0,40}?(==|!=)\s*[\"'](running|seeding|stopped)[\"']"
    r"|[\"'](running|seeding|stopped)[\"'][^\n]{0,20}?(==|!=)[^\n]{0,20}run_mode"
)
RUNMODE_LITERAL_OWNERS = {"common.py"}


def modules() -> list[str]:
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        out.append(str(rel))
    return out


def check() -> dict:
    problems: list[dict] = []
    for rel in modules():
        text = (ROOT / rel).read_text(encoding="utf-8")
        lines = text.split("\n")
        for i, ln in enumerate(lines, 1):
            code = ln.split("#", 1)[0]
            if re.search(r"\.enabled\b", code):
                if rel in ENABLED_OWNERS or ENABLED_LINE_ALLOW.search(code):
                    pass
                else:
                    problems.append(
                        {"rule": "R1", "file": rel, "line": i,
                         "text": ln.strip()[:120],
                         "fix": "改用 common 的 run_mode_of / task_is_running / enabled_of_run_mode"}
                    )
            if rel not in RUNMODE_LITERAL_OWNERS and RUNMODE_LITERAL_CMP.search(code):
                problems.append(
                    {"rule": "R2", "file": rel, "line": i,
                     "text": ln.strip()[:120],
                     "fix": "改用 common 的 RUN_MODE_* 常量或 task_is_* 访问器"}
                )
            if rel not in CROSSSEED_ALLOW and CROSSSEED_CALL.search(code):
                problems.append(
                    {"rule": "R3", "file": rel, "line": i,
                     "text": ln.strip()[:120],
                     "fix": "契约②：取种只能走 self._acquire_source(...)（唯一入口）"}
                )
    return {"problems": problems}


def main() -> int:
    result = check()
    probs = result["problems"]
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        for p in probs:
            print(f"❌ [{p['rule']}] {p['file']}:{p['line']}  {p['text']}\n     → {p['fix']}")
        if probs:
            print(f"\n契约检查失败：{len(probs)} 处违规")
        else:
            print("✅ 契约检查通过（R1 运行状态真值源 / R2 不比较字面量 / R3 取种唯一入口）")
    return 1 if probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
