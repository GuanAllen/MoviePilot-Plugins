#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""功能页对齐检查（护栏⑤）—— 契约③：后端 `FEATURES` ≥ 前端 `MF_PAGES`，且 key 一字不差。

前端 `MF_PAGES` 是展示层（改版只动它），后端 `FEATURES` 是真值源（状态/端点）。
两边漂移 = 页面点了 404 或后端功能没入口，所以提交前必须对齐。

用法：python3 tools/check_pages.py
退出码：0 通过；1 不一致。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "features" / "registry.py"
VUE = ROOT / "src" / "components" / "MagicFlowWorkbench.vue"


def backend_keys() -> list[str]:
    src = REGISTRY.read_text(encoding="utf-8")
    block = re.search(r"FEATURES:\s*tuple\s*=\s*\((.*?)\n\)", src, re.S)
    if not block:
        raise SystemExit("❌ 未能在 features/registry.py 里找到 FEATURES 表")
    return re.findall(r'FeatureSpec\(\s*"([a-z0-9_]+)"', block.group(1))


def frontend_keys() -> list[str]:
    src = VUE.read_text(encoding="utf-8")
    block = re.search(r"const MF_PAGES = \[(.*?)\n\]", src, re.S)
    if not block:
        raise SystemExit("❌ 未能在 MagicFlowWorkbench.vue 里找到 MF_PAGES")
    return re.findall(r"key:\s*'([a-z0-9_]+)'", block.group(1))


def main() -> int:
    be, fe = backend_keys(), frontend_keys()
    only_be = [k for k in be if k not in fe]
    only_fe = [k for k in fe if k not in be]
    dup_be = sorted({k for k in be if be.count(k) > 1})
    print(f"后端 FEATURES {len(be)} 项：{', '.join(be)}")
    print(f"前端 MF_PAGES {len(fe)} 项：{', '.join(fe)}")
    bad = False
    if dup_be:
        print(f"❌ 后端重复 key：{', '.join(dup_be)}")
        bad = True
    if only_be:
        print(f"❌ 后端有、前端没有（页面缺入口）：{', '.join(only_be)}")
        bad = True
    if only_fe:
        print(f"❌ 前端有、后端没登记：{', '.join(only_fe)}")
        bad = True

    # 元数据真实性：tick 方法必须存在；api 路径必须在路由表里注册
    src_all = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted((ROOT / "features").glob("*.py"))
    )
    api_src = (ROOT / "features" / "api.py").read_text(encoding="utf-8")
    registered = set(re.findall(r'"path":\s*"([^"]+)"', api_src))
    reg_src = REGISTRY.read_text(encoding="utf-8")
    for sp in re.finditer(
        r'FeatureSpec\(\s*"([a-z0-9_]+)"(.*?)\)\s*,\s*\n', reg_src, re.S
    ):
        key, body = sp.group(1), sp.group(2)
        tick = re.search(r'tick="([A-Za-z0-9_]+)"', body)
        probe = re.search(r'enabled_probe="([A-Za-z0-9_]+)"', body)
        api = re.search(r'api="([^"]+)"', body)
        for label, name in (("tick", tick), ("enabled_probe", probe)):
            if name and f"def {name.group(1)}(" not in src_all:
                print(f"❌ 功能 {key}: {label}={name.group(1)} 在代码里找不到定义")
                bad = True
        if api and api.group(1) not in registered:
            print(f"❌ 功能 {key}: api={api.group(1)} 未在 features/api.py 注册")
            bad = True

    if bad:
        print("\n契约③ 检查失败：两个注册表必须一字不差（改功能页只改这两处）")
        return 1
    print("\n✅ 功能页对齐（后端 FEATURES ↔ 前端 MF_PAGES，且 tick/api 元数据真实）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
