#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 术语护栏（禁用词表）——保护「四个时长概念」不再被统称「保种」。

保护什么
--------
做种时长有**四个**语义完全不同的概念，历史上 UI 把它们统统叫「保种」：

    达标期限   站点给多久之内做完   seed_hours / seed_window_hours
    义务工时   站点要求做满多少小时 seed_need_hours / crossseed_seed_hours_default
    本地保护期 本机「不足 N 小时不许删」 min_seed_time
    轮转周期   刷流「满 N 天就删」腾位   brush_seed_days

混用的代价是**可量化的误配置**：用户把「保种 24h」填进 `min_seed_time`（本该是 168h）
或把站点 240h 的达标期限填进本机保护期 → 磁盘撑爆 / 来源份被本机清理逻辑删掉 →
触发他站 H&R 罚款。四个词定名见 `codedict.py` 的 GLOSSARY「做种时长四类口径」。

为什么只扫 label / hint / placeholder
------------------------------------
Vuetify 组件 95% 的用户可见文案都走这三个属性（本轮 24 条改名里 19 条命中）。
不扫整个 `<template>`：正文里的「保种中」「挂 H&R」是状态描述，全量扫描会产生大量
噪音，反而让护栏被 `# noqa` 淹没。也不做语义级检查（判断某 label 对应哪个字段）：
要把 `v-model` 绑定链路、`defineModel` 名、父组件 props 全解析一遍，代价高且脆，
收益与「禁用词表」几乎一样。

合法残留（A.4，**不要**一刀切）
------------------------------
「保种体积」「保种上限」是**体积**语义不是时长，保留（`models.py` 原文即「保种体积上限(GB)」）。
职务名「保种」（`HR_HOST_TASK_ID` 的宿主岗位）同理，不在本护栏范围。

用法
----
    python tools/check_ui_terms.py        # 退出码 0=干净 / 1=有命中
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 只认属性字面量（label= / hint= / placeholder= 后的双引号串）
ATTR_RE = re.compile(r'\b(label|hint|placeholder)="([^"]*)"')

# 禁用词（作为**时长语义**时一律禁用）
BANNED = (
    "保种天数", "最短做种", "最短保种", "默认保种", "刷流保种",
    "保种时长", "保种(h)", "保种期",
)

# 合法残留：体积语义（A.4）
ALLOW = ("保种体积", "保种上限")


def main() -> int:
    hits: list[str] = []
    for p in sorted((ROOT / "src").rglob("*.vue")):
        if ".bak." in p.name:          # 历史备份不动、不扫
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in ATTR_RE.finditer(line):
                s = m.group(2)
                banned_hit = any(b in s for b in BANNED)
                bare_hit = ("保种" in s) and not any(a in s for a in ALLOW)
                if banned_hit or bare_hit:
                    hits.append(f"{p.relative_to(ROOT)}:{i}: {m.group(1)}=\"{s}\"")

    if hits:
        print("── UI 术语护栏：命中禁用词 ──")
        print("\n".join(hits))
        print(f"\n❌ FAIL —— {len(hits)} 处。四个定名见 GLOSSARY「做种时长四类口径」：")
        print("   达标期限 / 义务工时 / 本地保护期 / 轮转周期")
        return 1
    print("✅ UI 术语护栏：label/hint/placeholder 无禁用词")
    return 0


if __name__ == "__main__":
    sys.exit(main())
