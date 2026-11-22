#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FE-03 回归：趋势弹窗的「上传增量」链路必须保持完整（任务 110 复核 → 19.14.0 反转）。

背景（2026-11-07 任务 106/108 复核 → 19.12.44 曾删除 → 19.12.65 同步复活）
-------------------------------------------------------------------------
任务 110 曾把 `trendUploadIncrement` 当作死链路整条删除（当时 useTrend 不返回、
后端无字段、卡片永不显示）；本测试旧版断言「它必须保持已删除」。
但 58cefcf（19.12.65 同步运行副本）起开发树与运行副本带回了**活的链路**：
后端 `features/trend.py:334` 按序列窗口计算 `uploaded_increment`（19.11.0 就有），
`useTrend.loadTrendUploadIncrement` 真实取数并返回，`TrendDialog` 在任务口径下
渲染「该窗口本任务实际上传」卡。旧断言与活实现矛盾，preflight 32/38 从
58cefcf 起一直红（直至 19.13.5）。Master 于 2026-11-20 拍板：**A. 更新断言
匹配活链路**（19.14.0 反转本测试）。

检查项
------
  T1 index.vue 必须引用 `trendUploadIncrement` 并传 `:upload-increment=`；
  T2 useTrend.js 必须声明并返回 `trendUploadIncrement`；
  T3 index.vue 从 useTrend 解构的名字 == useTrend 返回的名字（不多不少）；
  T4 TrendDialog.js 必须声明 `uploadIncrement` prop，且仅在任务口径渲染该卡；
  T5 趋势弹窗核心契约仍在：7 个 props、5 个 emits、why/delta/metrics 渲染；
  T6 （可选）设置 `MF_TREND_DIST=构建产物 JS` 时，产物必须包含该链路。

退出码：0 = 通过；1 = 有回归。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "src" / "views" / "magicflow" / "index.vue"
USE = ROOT / "src" / "views" / "magicflow" / "composables" / "useTrend.js"
DIALOG = ROOT / "src" / "views" / "magicflow" / "components" / "dialogs" / "TrendDialog.js"

OK: list[str] = []
BAD: list[str] = []


def _ok(cond: bool, msg: str) -> None:
    (OK if cond else BAD).append(msg)


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _destructured(src: str) -> set[str]:
    m = re.search(r"const\s*\{([^}]*)\}\s*=\s*useTrend\(", src)
    if not m:
        return set()
    return {x.strip() for x in m.group(1).replace("\n", " ").split(",") if x.strip()}


def _returned(src: str) -> set[str]:
    m = re.search(r"return\s*\{([^}]*)\}\s*;?\s*\}\s*$", src, re.S)
    if not m:
        return set()
    return {x.strip() for x in m.group(1).replace("\n", " ").split(",") if x.strip()}


def main() -> int:
    for p in (INDEX, USE, DIALOG):
        _ok(p.is_file(), f"{p.name} 存在")
    if BAD:
        print("❌ 缺少文件：" + ", ".join(BAD))
        return 1

    idx = _text(INDEX)
    use = _text(USE)
    dlg = _text(DIALOG)

    _ok("trendUploadIncrement" in idx, "T1 index.vue 引用 trendUploadIncrement")
    _ok(":upload-increment=" in idx or ":upload-increment" in idx,
        "T1 index.vue 传 :upload-increment")
    _ok("trendUploadIncrement" in use, "T2 useTrend.js 声明/返回该字段")
    _ok("uploadIncrement" in dlg, "T4 TrendDialog.js 声明/读取 uploadIncrement")

    used, returned = _destructured(idx), _returned(use)
    _ok(bool(used) and bool(returned), "T3 可解析出解构名与返回名")
    _ok(used == returned, f"T3 解构名与返回名一致（解构 {len(used)} / 返回 {len(returned)}）")
    _ok("loadTrendReport" in used and "openTrend" in used, "T3 趋势入口函数仍在解构列表")
    _ok("trendUploadIncrement" in used and "trendUploadIncrement" in returned,
        "T3 上传增量在解构列表与返回列表中")

    for prop in ("modelValue", "scope", "ident", "hours", "why", "daily",
                 "loading", "scopeItems"):
        _ok(re.search(rf"{prop}:\s*\{{", dlg) is not None, f"T5 弹窗仍有 prop {prop}")
    for ev in ("update:modelValue", "update:scope", "update:ident",
               "update:hours", "refresh"):
        _ok(ev in dlg, f"T5 弹窗仍 emit {ev}")
    _ok("__props.why?.verdict" in dlg, "T5 结论卡片渲染仍在")
    _ok("deltaLine.value" in dlg, "T5 差分行渲染仍在")
    _ok("metrics.value.length" in dlg, "T5 指标列表渲染仍在")
    _ok("formatBytes" in dlg, "T5 体积格式化仍在（其它卡片仍在用）")
    _ok("__props.scope === 'task' && __props.uploadIncrement != null" in dlg,
        "T4 该卡仅在任务口径且有增量时渲染")

    # T6：产物验证。默认扫 dist/assets 全部 JS 分片（构建产物 hash 化，不能写死文件名）；
    # 显式设 MF_TREND_DIST（pathsep 分隔）可改扫指定文件，方便只验单个分片。
    dist = os.environ.get("MF_TREND_DIST", "").strip()
    if dist:
        paths = [Path(x) for x in dist.split(os.pathsep) if x]
    else:
        assets = ROOT / "dist" / "assets"
        paths = sorted(assets.glob("*.js")) if assets.is_dir() else []
        if not paths:
            _ok(False, "T6 未找到 dist/assets/*.js 分片（先跑 npm run build）")
    if paths:
        blobs = [(p, p.read_text(encoding="utf-8", errors="ignore")) for p in paths]
        joined = "\n".join(b for _, b in blobs)
        _ok("uploadIncrement" in joined, f"T6 产物含 uploadIncrement（扫 {len(blobs)} 个分片）")
        _ok("本任务实际上传" in joined, f"T6 产物含该卡片文案（扫 {len(blobs)} 个分片）")

    for msg in OK:
        print(f"✅ {msg}")
    for msg in BAD:
        print(f"❌ {msg}")
    if BAD:
        print(f"\n❌ FAIL —— {len(BAD)} 项断言失败（共 {len(OK) + len(BAD)} 项）")
        return 1
    print(f"\n✅ PASS —— {len(OK)} 项断言全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())