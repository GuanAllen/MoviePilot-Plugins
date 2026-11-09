#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FE-03 回归：趋势弹窗的「上传增量」死链路必须保持已删除（任务 110）。

背景（2026-11-07 任务 106/108 复核）
------------------------------------
`useTrend()` 从来不返回 `trendUploadIncrement`，后端也不存在该字段；但
`index.vue` 曾把它从解构里取出并作为 `:upload-increment` 传给趋势弹窗，
弹窗再按 `!== null` 渲染「本任务实际上传」卡片 —— 该卡片因此永远不显示。
任务 110 删除整条死链路（index.vue / TrendDialog.js），本测试防止它被
复制粘贴回来，同时确认趋势弹窗的其余能力没有被误删。

检查项
------
  T1 index.vue 不再出现 `trendUploadIncrement` / `:upload-increment=`；
  T2 useTrend.js 不再出现 `trendUploadIncrement`；
  T3 index.vue 从 useTrend 解构的名字 == useTrend 返回的名字（不多不少）；
  T4 TrendDialog.js 不再声明 / 读取 `uploadIncrement`；
  T5 趋势弹窗核心契约仍在：7 个 props、5 个 emits、why/delta/metrics 渲染；
  T6 （可选）设置 `MF_TREND_DIST=构建产物 JS` 时，产物里不得出现该字段或文案。

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

    _ok("trendUploadIncrement" not in idx, "T1 index.vue 不再引用 trendUploadIncrement")
    _ok(":upload-increment" not in idx and "upload-increment=" not in idx,
        "T1 index.vue 不再传 :upload-increment")
    _ok("trendUploadIncrement" not in use, "T2 useTrend.js 不再声明/返回该字段")
    _ok("uploadIncrement" not in dlg, "T4 TrendDialog.js 不再声明/读取 uploadIncrement")

    used, returned = _destructured(idx), _returned(use)
    _ok(bool(used) and bool(returned), "T3 可解析出解构名与返回名")
    _ok(used == returned, f"T3 解构名与返回名一致（解构 {len(used)} / 返回 {len(returned)}）")
    _ok("loadTrendReport" in used and "openTrend" in used, "T3 趋势入口函数仍在解构列表")

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

    dist = os.environ.get("MF_TREND_DIST", "").strip()
    if dist:
        for path in [x for x in dist.split(os.pathsep) if x]:
            p = Path(path)
            blob = p.read_text(encoding="utf-8", errors="ignore")
            _ok("uploadIncrement" not in blob, f"T6 产物无 uploadIncrement：{p.name}")
            _ok("本任务实际上传" not in blob, f"T6 产物无该卡片文案：{p.name}")

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
