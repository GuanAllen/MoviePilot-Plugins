#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · Vue 模板 ref 误用护栏（★ 14.0.0-2 / 2026-10-07）。

背景：`MagicFlowWorkbench.vue` 的「挂种健康」弹窗白屏，根因是模板里写了
`seedHealth.value.items` —— Vue 3 `<script setup>` 模板会**自动 unwrap** 顶层 ref，
所以模板里再访问 `.value` 得到的是 `undefined` 属性访问 → `undefined.items`
抛 `TypeError` → 整个卡片渲染失败（白屏）。

护栏口径（保守、低误报）：
  1. 只在 `.vue` 的 `<template>` 区域扫；`<script>` 区合法，不扫。
  2. 只对「本文件 `<script setup>` 顶层用 ref()/shallowRef()/computed()/customRef()
     /toRef() 声明的标识符」判「模板里又写了 `.value`」。
     —— 这样 `display.mdAndUp.value`（对象上的 ref 属性，模板**不** unwrap）、
     `tab.value`（普通对象的 value 字段）都不会误报。

命中即失败。用法：`python3 tools/check_vue_template_refs.py`（0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "components"

TEMPLATE_RE = re.compile(r"<template[^>]*>(.*?)</template>", re.S | re.I)
SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.S | re.I)
REF_DECL_RE = re.compile(
    r"^[ \t]*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:ref|shallowRef|computed|customRef|toRef)\s*[<(]",
    re.M,
)
USE_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\.value\b")


def refs_declared(script_text: str) -> set:
    return set(REF_DECL_RE.findall(script_text))


def scan(path: Path):
    text = path.read_text(encoding="utf-8")
    script = "\n".join(m.group(1) for m in SCRIPT_RE.finditer(text))
    refs = refs_declared(script)
    if not refs:
        return []
    hits = []
    for m in TEMPLATE_RE.finditer(text):
        block = m.group(1)
        base_line = text[: m.start(1)].count("\n") + 1
        for i, line in enumerate(block.splitlines()):
            for mm in USE_RE.finditer(line):
                if mm.group(1) in refs:
                    hits.append((base_line + i, mm.group(0)))
    return hits


def main() -> int:
    files = sorted(SRC.glob("*.vue")) if SRC.exists() else []
    if not files:
        print(f"⚠️ 未找到 .vue 文件（{SRC}）")
        return 0
    total = 0
    for f in files:
        for lineno, snip in scan(f):
            print(f"❌ {f.relative_to(ROOT)}:{lineno}  模板里出现 `{snip}`"
                  f"（该 ref 在 <script setup> 顶层声明，模板已自动 unwrap，勿再写 .value）")
        total += len(scan(f))
    if total:
        print(f"\n❌ 模板 ref 误用：{total} 处")
        return 1
    print(f"✅ 模板 ref 护栏通过（扫描 {len(files)} 个 .vue）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
