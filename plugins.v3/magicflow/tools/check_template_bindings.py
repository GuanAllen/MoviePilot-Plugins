#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · Vue 模板「用了但没声明」护栏（★ 2026-10-08，护栏⑦）。

背景（真实血泪）：
  `index.vue` 的模板里写了 `v-model="invariantOpen"` / `@click="invariantOpen = true"`，
  但 `<script setup>` 里**从来没有声明过 invariantOpen** →
  - 读：`_ctx.invariantOpen` = undefined（弹窗永远打不开）
  - 写：`invariantOpen = true` 落到 render 代理上，**非响应式**，界面毫无反应
  症状 = 「按钮点了没反应 / 弹窗空白」，且**构建不报错、控制台不报错**。

口径：扫 `.vue` 的 `<template>` 区，把「表达式里出现、但既不是脚本区声明、
也不是模板局部绑定（v-for / v-slot / 内联箭头参数）、也不是 JS 内置」的标识符报出来。

用法：python3 tools/check_template_bindings.py [文件...]（0=PASS / 1=FAIL）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

BUILTINS = set("""Math Number String Boolean Array Object JSON Date Map Set WeakMap WeakSet
Promise RegExp URLSearchParams URL isFinite isNaN parseInt parseFloat window document console
setTimeout clearTimeout setInterval clearInterval navigator localStorage sessionStorage
undefined NaN Infinity null true false this encodeURIComponent decodeURIComponent Error Symbol
arguments Infinity BigInt globalThis Intl structuredClone queueMicrotask""".split())

KEYWORDS = set("""const let var function return if else for while switch case break continue try
catch finally new typeof instanceof await async of in do throw delete void yield this class
extends super static get set import export default""".split())


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def split_sfc(text: str):
    """取顶格 <template>…</template> 与 <script setup>…</script>。"""
    lines = text.split("\n")
    ti = next((i for i, l in enumerate(lines) if l.startswith("<template")), None)
    tj = max((i for i, l in enumerate(lines) if l.startswith("</template>")), default=None)
    si = next((i for i, l in enumerate(lines) if l.startswith("<script")), None)
    sj = next((i for i, l in enumerate(lines) if l.startswith("</script>")), None)
    tpl = "\n".join(lines[ti:tj + 1]) if ti is not None and tj is not None else ""
    scr = "\n".join(lines[si:sj + 1]) if si is not None and sj is not None else ""
    return tpl, scr


def script_declared(scr: str) -> set:
    names = set()
    for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)", scr):
        names.add(m.group(1))
    for m in re.finditer(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", scr):
        names.add(m.group(1))
    # const { a, b: c, d = 1 } = ...
    for m in re.finditer(r"\b(?:const|let|var)\s*\{([^}]*)\}\s*=", scr):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            part = part.split(":")[-1] if ":" in part else part
            part = part.split("=")[0].strip()
            if part:
                names.add(part)
    for m in re.finditer(r"import\s*\{([^}]*)\}", scr, re.S):
        for part in m.group(1).split(","):
            part = part.strip().split(" as ")[-1].strip()
            if part:
                names.add(part)
    for m in re.finditer(r"^\s*import\s+([A-Za-z_$][\w$]*)\s", scr, re.M):
        names.add(m.group(1))
    # defineProps / defineEmits（★ 平衡括号取实参，避免 default: () => [] 里的 ')' 提前截断）
    for macro, kind in (("defineProps", "props"), ("defineEmits", "emits")):
        for m in re.finditer(r"\b%s\s*(?:<[^>]*>)?\s*\(" % macro, scr):
            depth = 1
            k = m.end()
            while k < len(scr) and depth:
                if scr[k] in "([{":
                    depth += 1
                elif scr[k] in ")]}":
                    depth -= 1
                k += 1
            body = scr[m.end():k - 1].strip()
            if body.startswith("["):
                for part in body.strip("[]").split(","):
                    part = part.strip().strip("'\"")
                    if part:
                        names.add(part)
            elif body.startswith("{"):
                for part in re.finditer(r"(?:^|[,{])\s*([A-Za-z_$][\w$]*)\s*:", body):
                    names.add(part.group(1))
    return names


PROP_RE = re.compile(
    r"""(?:^|\s)(?::|@|v-)(?:[A-Za-z0-9_.:-]*)\s*=\s*"([^"]*)\"""", re.S)
INTERP_RE = re.compile(r"\{\{(.*?)\}\}", re.S)


def template_local_bindings(tpl: str) -> set:
    """模板自己的局部绑定：v-for 变量、v-slot 名、按名字取的 slot prop。"""
    local = set()
    for m in re.finditer(r"v-for\s*=\s*\"\s*\(?([^\"=)]*?)\)?\s+(?:in|of)\s", tpl):
        for part in m.group(1).split(","):
            part = part.strip()
            if part:
                local.add(part)
    for m in re.finditer(r"(?:v-slot(?::[A-Za-z0-9_-]+)?|#[A-Za-z0-9_-]*)\s*=\s*\"([^\"]*)\"", tpl):
        body = m.group(1).strip()
        if body.startswith("{"):
            for part in body.strip("{}").split(","):
                part = part.strip().split(":")[-1].split("=")[0].strip()
                if part:
                    local.add(part)
        elif re.fullmatch(r"[A-Za-z_$][\w$]*", body):
            local.add(body)
    return local


def clean_expr(e: str) -> str:
    e = re.sub(r"//[^\n]*", "", e)
    e = re.sub(r"`[^`]*`", "``", e)
    e = re.sub(r"'[^']*'", "''", e)
    e = re.sub(r'"[^"]*"', '""', e)
    return e


def expr_idents(e: str) -> set:
    out = set()
    # 内联箭头参数
    for m in re.finditer(r"\(([^()]*)\)\s*=>", e):
        for part in m.group(1).split(","):
            part = part.strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                out.add(part)
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*=>", e):
        out.add(m.group(1))
    found = set()
    for m in re.finditer(r"([A-Za-z_$][\w$]*)", e):
        w = m.group(1)
        if e[max(0, m.start() - 1)] == ".":      # 属性访问
            continue
        if m.end() < len(e) and e[m.end()] == ":" and not w.isdigit():
            continue                             # 对象字面量键 { title: ... }
        found.add(w)
    return found - out


def check(path: Path):
    text = read(path)
    tpl, scr = split_sfc(text)
    if not tpl:
        return []
    declared = script_declared(scr) | template_local_bindings(tpl)
    # v-for 的表达式本身也要扫（"x in list" 里 list 必须声明）
    exprs = list(INTERP_RE.findall(tpl)) + [m.group(1) for m in PROP_RE.finditer(tpl)]
    unknown = {}
    for e in exprs:
        e = clean_expr(e)
        for w in expr_idents(e):
            if w in declared or w in KEYWORDS or w in BUILTINS or w.startswith("$"):
                continue
            unknown[w] = unknown.get(w, 0) + 1
    return sorted(unknown.items(), key=lambda x: -x[1])


def main():
    targets = [Path(a) for a in sys.argv[1:]] or sorted(SRC.rglob("*.vue"))
    bad = 0
    for p in targets:
        if p.name in ("vite.config.js",) or p.suffix != ".vue":
            continue
        hits = check(p)
        if hits:
            bad += 1
            rel = p.relative_to(ROOT)
            print("❌ %s：模板引用了未声明的标识符" % rel)
            for name, n in hits:
                print("     - %s（%d 次）" % (name, n))
    if bad:
        return 1
    print("✅ 模板绑定护栏通过（%d 个 .vue，无未声明标识符）" % len([t for t in targets if t.suffix == ".vue"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
