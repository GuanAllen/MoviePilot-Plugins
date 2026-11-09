#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 107 / 场景 10：设置映射与后端字段语义一致性（离线）。

跨四种「口径来源」做静态断言，防止前后端再次各说各话：

  1. ``models.py::MagicFlowSettingsPayload`` —— 请求模型里真正存在的 fallback_* 字段与默认值
  2. ``features/settings.py::update_settings`` —— 实际消费的 fallback 键（`_fb_take` / `setdefault`）
  3. ``src/views/magicflow/composables/settingsMap.js`` —— 新前端短键→长键映射产出的键
  4. ``src/utils.js::normalizeSettings`` —— 保存草稿里保留的 fallback_* 键（闭集）

外加 ``useTasks.js`` 的接线守卫（必须用显式映射，不得复活旧 spread）。

只做只读静态分析，不导入插件、不碰网络/数据目录。
用法：``python3 tools/test_settings_contract.py``（0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS: list[str] = []
CASES = 0

KEYS = [
    "fallback_enabled",
    "fallback_sources",
    "fallback_paths",
    "fallback_interval_minutes",
    "fallback_scan_max",
    "fallback_sp_to_s00",
    "fallback_after_import",
    "fallback_dry_run",
]


def _ok(cond, name, detail=""):
    global CASES
    CASES += 1
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name}" + (f" —— {detail}" if detail else ""))
        FAILS.append(name)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _model_default(src: str, key: str):
    """从 models.py 抽 ``key: T = Field(<default...>`` / ``key: T = <literal>`` 的默认值。"""
    m = re.search(rf"^\s{{4}}{key}:\s*[^=\n]+=\s*([^\n]+)$", src, re.M)
    if not m:
        return None
    rhs = m.group(1).strip()
    fm = re.match(r"Field\(\s*([^,)]+)", rhs)
    if fm:
        return fm.group(1).strip()
    return rhs.split(",", 1)[0].strip()


def main() -> int:
    models = read("models.py")
    settings = read("features/settings.py")
    smap = read("src/views/magicflow/composables/settingsMap.js")
    utils = read("src/utils.js")
    use_tasks = read("src/views/magicflow/composables/useTasks.js")
    common = read("common.py")

    print("── 1. 请求模型：8 个 fallback_* 字段齐全 ──")
    for k in KEYS:
        _ok(_model_default(models, k) is not None, f"models.py 定义 {k}")

    print("── 2. 后端消费键集（_fb_take）与模型键集完全相同 ──")
    take = set(re.findall(r'_fb_take\("([^"]+)"\)', settings))
    _ok(take == set(KEYS), "_fb_take 键集 == 8 个模型字段", f"缺={sorted(set(KEYS) - take)} 多={sorted(take - set(KEYS))}")

    print("── 3. 后端补默认（setdefault）只补这 8 个短键 ──")
    sd = set(re.findall(r'_fb\.setdefault\("([^"]+)"', settings))
    short = {"enabled", "sources", "paths", "interval", "scan_max",
             "sp_to_s00", "after_import", "dry_run"}
    _ok(sd == short, "setdefault 短键集 == 8 个（与模型长键一一对应）", f"实际={sorted(sd)}")

    print("── 4. 新前端映射：产出键集与后端一致，且绝不产出 enabled ──")
    produced = set(re.findall(r"^\s{4}(fallback_[a-z0-9_]+):", smap, re.M))
    _ok(produced == set(KEYS), "settingsMap 产出 8 个 fallback_* 键", f"缺={sorted(set(KEYS) - produced)} 多={sorted(produced - set(KEYS))}")
    _ok(not re.search(r"^\s{4}enabled\s*:", smap, re.M), "settingsMap 不产出裸 enabled（总开关独立）")
    _ok("export function fallbackSettingsFrom" in smap, "settingsMap 导出 fallbackSettingsFrom")

    print("── 5. 保存草稿闭集：normalizeSettings 保留全部 8 键 ──")
    for k in KEYS:
        _ok(bool(re.search(rf"\b{k}\s*:", utils)), f"utils.js normalizeSettings 含 {k}")

    print("── 6. 默认值三方一致（模型 / 映射 / 后端）──")
    _ok(_model_default(models, "fallback_interval_minutes") == "30.0",
        "模型 interval 默认 30.0")
    _ok("DEFAULT_INTERVAL_MINUTES = 30" in smap, "映射 interval 默认 30")
    _ok(re.search(r"fallback_interval_minutes\",\s*_fb\.get\(\"interval\",\s*30\.0\)\),\s*30\.0\)", settings) is not None,
        "后端 interval 兜底 30.0")
    _ok(_model_default(models, "fallback_scan_max") == "30", "模型 scan_max 默认 30")
    _ok("DEFAULT_SCAN_MAX = 30" in smap, "映射 scan_max 默认 30")
    _ok(re.search(r"^FALLBACK_SCAN_MAX\s*=\s*30\b", common, re.M) is not None, "common.FALLBACK_SCAN_MAX == 30")

    print("── 7. 开关默认语义一致（True/False 方向）──")
    _ok(_model_default(models, "fallback_enabled") == "True", "模型 fallback_enabled 默认 True")
    _ok("fallback_enabled: fb.enabled !== false" in smap, "映射 fallback_enabled 缺省视为 True")
    _ok(_model_default(models, "fallback_sp_to_s00") == "False", "模型 sp_to_s00 默认 False")
    _ok("fallback_sp_to_s00: fb.sp_to_s00 === true" in smap, "映射 sp_to_s00 缺省视为 False")
    _ok(_model_default(models, "fallback_after_import") == "True", "模型 after_import 默认 True")
    _ok("fallback_after_import: fb.after_import !== false" in smap, "映射 after_import 缺省视为 True")
    _ok(_model_default(models, "fallback_dry_run") == "False", "模型 dry_run 默认 False")
    _ok("fallback_dry_run: fb.dry_run === true" in smap, "映射 dry_run 缺省视为 False")
    _ok('_fb.setdefault("enabled", True)' in settings, "后端兜底 enabled 默认 True")
    _ok('_fb.setdefault("after_import", True)' in settings, "后端兜底 after_import 默认 True")

    print("── 8. 前端接线：useTasks 用显式映射，旧 spread 未复活 ──")
    _ok("import { fallbackSettingsFrom } from './settingsMap'" in use_tasks,
        "useTasks 导入 fallbackSettingsFrom")
    _ok("...fallbackSettingsFrom(status.value.fallback)" in use_tasks,
        "useTasks 使用 fallbackSettingsFrom(...)")
    _ok("...(status.value.fallback || {})" not in use_tasks,
        "旧 spread 已被移除")

    print(f"\n{'✅ PASS' if not FAILS else '❌ FAIL'} —— {CASES - len(FAILS)}/{CASES} 通过")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
