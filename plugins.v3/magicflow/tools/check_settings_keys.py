#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 设置键集护栏（P1：认领 / H&R 13 项存不进去的回归闸门）

背景（真值源：`src/utils.js::normalizeSettings`）
------------------------------------------------
`normalizeSettings()` 的返回值被保存路径**直接当请求体**用：
    useSettings.js:191  saveIyuu()     -> api.settings.saveSettings(normalizeSettings(settingsDraft.value))
    useSettings.js:339  saveSettings() -> 同上
它以前是**闭集**（返回恰好 107 个字面量键），于是 SettingsDialog 绑定的
`claim_*`（10 个）与 `hr_*`（3 个）在提交前被静默丢掉，UI 却提示「设置已保存」。

P1 修复把 normalizeSettings 改成「已知键做类型归一 + **未知键原样透传**」，
所以本护栏断言的真实不变量是：

    SettingsDialog 里被绑定的每个 `settingsDraft.<键>`，
    要么在 normalizeSettings 的字面量里**显式归一化**，
    要么被 normalizeSettings 的**透传机制**兜住。

字面量键集从 `normalizeSettings` 内部那个对象字面量的 `^键:` 行解析（只扫函数体内，
不做全文件扫描）；绑定键集从 SettingsDialog.vue 的 `settingsDraft.<键>` 解析。

★ 为什么不直接断言「绑定键集 ⊆ 字面量键集」：透传的键（claim_*/hr_*）本来就不在
  字面量里 —— 那样断言在修复后反而会 13 项全红，是个永远红的假护栏。透传机制本身
  才是被保护的对象：一旦有人把它删掉/改写，passthrough 信号消失，本护栏立刻把
  「绑了但既不归一化、又没透传」的键逐条打出来并退出 1。

离线 · 纯 stdlib · 退出码 0（通过）/ 1（失败）。不联网、不写文件。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UTILS = ROOT / "src" / "utils.js"
DIALOG = (
    ROOT / "src" / "views" / "magicflow" / "components" / "dialogs" / "SettingsDialog.vue"
)

FUNC_RE = re.compile(r"^\s*export\s+function\s+normalizeSettings\b")
# 字面量起点：`const result = {`（当前实现）或 `return {`（历史/回退写法）
LIT_RE = re.compile(r"^\s*(?:const\s+result\s*=\s*|return\s*)\{\s*$")
KEY_RE = re.compile(r"^\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*:")
BIND_RE = re.compile(r"settingsDraft\.([A-Za-z_$][A-Za-z0-9_$]*)")

# 透传机制的「源码指纹」：枚举入参自身键 + 跳过 undefined。
# 两个信号缺一不可 —— 少一个就不再认为未知键会被原样保留。
PASSTHROUGH_SIGNALS = ("Object.keys(settings)", "settings[key] === undefined")

# 防解析腐化（parser rot）：这些键必须出现在各自集合里，否则说明正则解析失效，
# 绝不能因为「解析不到」而静默变成空集、让护栏假绿。
ANCHOR_LITERAL_KEYS = {"enabled", "hidden_tiles", "sort_rules", "iyuu_sites", "cloud_paths"}
ANCHOR_BINDING_KEYS = {
    "claim_enabled",
    "claim_sites",
    "hr_complete_ratio",
    "hr_seed_margin_hours",
    "notify_enabled",
}


def _strip_line_comment(line: str) -> str:
    """去掉行尾 `//` 注释（不碰字符串内的 //），避免注释里的花括号/冒号干扰解析。"""
    out = []
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                out.append(ch)
                i += 1
                if i < len(line):
                    out.append(line[i])
                    i += 1
                continue
            if ch == quote:
                quote = ""
            out.append(ch)
        else:
            if ch in "'\"`":
                quote = ch
                out.append(ch)
            elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - 环境错误直接暴露
        print(f"[FAIL] 读不到 {path}: {exc}")
        sys.exit(1)


def normalize_function_lines(lines):
    """返回 normalizeSettings 的函数体行（含首行签名），找不到返回 None。"""
    start = None
    for i, line in enumerate(lines):
        if FUNC_RE.match(line):
            start = i
            break
    if start is None:
        return None, "src/utils.js 里找不到 `export function normalizeSettings`"
    body = []
    depth = 0
    for i in range(start, len(lines)):
        line = lines[i]
        body.append(line)
        code = _strip_line_comment(line)
        depth += code.count("{") - code.count("}")
        if depth <= 0 and i > start:
            break
    if depth != 0:
        return None, "normalizeSettings 花括号不平衡（解析失败）"
    return body, ""


def extract_literal_keys(body):
    """从函数体内的对象字面量提取顶层键（只认 depth==1 的 `^键:` 行）。"""
    lit = None
    for i, line in enumerate(body):
        if i == 0:
            continue  # 首行的 `settings = {}` 默认值不算字面量
        if LIT_RE.match(_strip_line_comment(line)):
            lit = i
            break
    if lit is None:
        return None, "normalizeSettings 里找不到返回对象字面量（`const result = {` / `return {`）"
    keys = []
    seen = set()
    depth = 0
    for i in range(lit, len(body)):
        code = _strip_line_comment(body[i])
        if depth == 1:
            m = KEY_RE.match(code)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                keys.append(m.group(1))
        depth += code.count("{") - code.count("}")
        if depth == 0 and i > lit:
            break
    if not keys:
        return None, "对象字面量里一个键都没解析到（正则失效？）"
    return keys, ""


def main() -> int:
    print("== MagicFlow check_settings_keys ==")

    utils_text = _read(UTILS)
    body, err = normalize_function_lines(utils_text.splitlines())
    if body is None:
        print(f"[FAIL] {err}")
        return 1

    literal_keys, err = extract_literal_keys(body)
    if literal_keys is None:
        print(f"[FAIL] {err}")
        return 1
    literal = set(literal_keys)

    dialog_text = _read(DIALOG)
    dialog_code = "\n".join(_strip_line_comment(ln) for ln in dialog_text.splitlines())
    binding_keys = sorted(set(BIND_RE.findall(dialog_code)))

    # ── 防解析腐化 ──────────────────────────────────────────────
    rot = []
    miss_lit = sorted(ANCHOR_LITERAL_KEYS - literal)
    if miss_lit:
        rot.append(f"字面量锚点键缺失（解析腐化）: {', '.join(miss_lit)}")
    miss_bind = sorted(ANCHOR_BINDING_KEYS - set(binding_keys))
    if miss_bind:
        rot.append(f"SettingsDialog 绑定锚点键缺失（解析腐化/UI 语义被改）: {', '.join(miss_bind)}")
    if rot:
        for line in rot:
            print(f"[FAIL] {line}")
        return 1

    # ── 透传机制是否还在 ────────────────────────────────────────
    body_text = "\n".join(body)
    signals = {sig: (sig in body_text) for sig in PASSTHROUGH_SIGNALS}
    passthrough_ok = all(signals.values())

    typed = [k for k in binding_keys if k in literal]
    passthrough = [k for k in binding_keys if k not in literal]

    print(f"normalizeSettings 字面量归一化键: {len(literal_keys)} 个")
    print(f"SettingsDialog 绑定键:          {len(binding_keys)} 个")
    print(f"  ├─ 已在字面量里归一化:         {len(typed)} 个")
    print(f"  └─ 依赖未知键透传:             {len(passthrough)} 个")
    if passthrough:
        print(f"     透传键: {', '.join(passthrough)}")
    for sig, ok in signals.items():
        print(f"  透传信号 {sig!r}: {'OK' if ok else 'MISSING'}")

    if not passthrough_ok:
        print(
            "[FAIL] normalizeSettings 的未知键透传机制缺失/被改写 —— "
            "下列绑定键既不归一化、也不会被透传，保存时会被静默丢弃："
        )
        for key in passthrough:
            print(f"  - {key}")
        return 1

    print("[OK] 所有 SettingsDialog 绑定键都被 normalizeSettings 保留（归一化 或 透传）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
