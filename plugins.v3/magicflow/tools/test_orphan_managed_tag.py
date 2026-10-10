#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 15.8.13「孤儿魔流标签不再证明归我们管」离线单测。

背景（2026-10-10 线上实证）：工作区临时脚本给 10 颗音乐种打了 ``魔流-手动``
（``parse_tag("魔流-手动") → None``、也不在 ``SPECIAL_TAGS`` 标记表里）。因为旧判据只看
``魔流`` 前缀：

  * ``_magicize_scope`` 认为「已是魔流」→ 永远不接管（归流闸门被占位）；
  * ``traffic_audit`` 认为 ``managed`` → 从不进「未知流量」名单，巡逻告警不响；
  ⇒ 永久孤儿（无账本行 / 无身份 / 无 H&R 账），且我手工补的带站点静默标签同样被跳过。

验什么（纯标准库，只加载 ``tags.py`` 纯函数模块，不连任何真库 / 真下载器）：
  1. ``is_managed_tag``：能解析出身份 or 在标记表里 → True；孤儿标签 / 非魔流 → False；
  2. ``needs_magicize``：空标签、**只有孤儿标签**、无站点老式静默身份 → 要归流；
     带站点身份 / 职务 / 只有已知标记 → 不动；
  3. ``retag`` 重贴会丢掉孤儿标签（不会带进新身份）；
  4. 模拟 ``traffic_audit`` 新判据：孤儿标签不再算 ``managed``、且能被孤儿计数抓到。

用法：``python3 tools/test_orphan_managed_tag.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_OK = 0
_FAIL = 0


def _ok(cond: bool, msg: str) -> None:
    global _OK, _FAIL
    if cond:
        _OK += 1
        print(f"  ✅ {msg}")
    else:
        _FAIL += 1
        print(f"  ❌ {msg}")


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("== 15.8.13 孤儿魔流标签不再算「已管控」 ==")
    t = _load("mf_orphan_tag_test_tags", "tags.py")

    # --- 1) is_managed_tag：能认出来才算归我们管 ---
    print("[1] is_managed_tag")
    for tag in ("魔流-聆音-静默-资源", "魔流-聆音-静默-普通", "魔流-聆音-魔力",
                "魔流-静默-普通", "魔流-推荐", "魔流-跨站", "魔流-辅种",
                "魔流-H&R", "魔流-补源", "魔流-外部"):
        _ok(t.is_managed_tag(tag) is True, f"已识别魔流标签 → True：{tag}")
    for tag in ("魔流-手动", "魔流-乱七八糟", "魔流-", "魔流", "MOVIEPILOT", "聆音", ""):
        _ok(t.is_managed_tag(tag) is False, f"孤儿/非魔流标签 → False：{tag!r}")
    _ok(t.parse_tag("魔流-手动") is None, "前提：parse_tag('魔流-手动') 确实是 None")

    # --- 2) needs_magicize：孤儿标签不再挡归流闸门 ---
    print("[2] needs_magicize")
    _ok(t.needs_magicize([]) is True, "无标签 → 要归流")
    _ok(t.needs_magicize(["MOVIEPILOT", "PT站"]) is True, "只有非魔流标签 → 要归流")
    _ok(t.needs_magicize(["魔流-手动"]) is True,
        "★ 只有孤儿标签 → 要归流（旧逻辑在这里被挡死，15.8.13 修复）")
    _ok(t.needs_magicize(["魔流-手动", "MOVIEPILOT"]) is True,
        "★ 孤儿标签 + MP 标记 → 要归流")
    _ok(t.needs_magicize(["魔流-乱七八糟"]) is True, "未知魔流标签同样孤儿 → 要归流")
    _ok(t.needs_magicize(["魔流-聆音-静默-资源"]) is False, "带站点身份 → 不动")
    _ok(t.needs_magicize(["魔流-聆音-静默-普通", "魔流-聆音-魔力"]) is False,
        "带站点身份 + 职务 → 不动")
    _ok(t.needs_magicize(["魔流-静默-普通"]) is True,
        "无站点老式静默身份 → 要归流（靠 tracker 补站点）")
    _ok(t.needs_magicize(["魔流-辅种"]) is False, "只有已知标记 → 不动")
    _ok(t.needs_magicize(["魔流-辅种", "魔流-手动"]) is False,
        "标记在场 → 不动（孤儿标签随下次重贴被丢弃，且它已证明归我们管）")

    # --- 3) retag：重贴丢弃孤儿标签 ---
    print("[3] retag 丢孤儿")
    out = t.retag(["魔流-手动", "PT站", "魔流-聆音-静默-资源", "魔流-辅种"],
                  site="聆音", state="静默", sub="资源")
    _ok("魔流-手动" not in out, f"孤儿标签被丢弃：{out}")
    _ok("魔流-聆音-静默-资源" in out, "身份标签保留")
    _ok("魔流-辅种" in out, "已知标记保留")
    _ok("PT站" in out, "非魔流标签保留")
    out2 = t.retag(["魔流-手动"], site="聆音", state="静默", sub="资源")
    _ok(out2 == ["魔流-聆音-静默-资源"], f"只有孤儿标签 → 重贴成正常身份：{out2}")

    # --- 4) 模拟 traffic_audit 新判据 ---
    print("[4] traffic_audit 判据（模拟）")
    def _audit(tags):
        managed = any(t.is_managed_tag(x) for x in tags)
        orphan = [x for x in tags if t.is_magicflow_tag(x)] if not managed else []
        return managed, bool(orphan)

    _ok(_audit(["魔流-手动"]) == (False, True), "★ 孤儿标签：不算 managed，计入 orphan")
    _ok(_audit(["魔流-聆音-静默-资源"]) == (True, False), "真魔流标签：managed，非 orphan")
    _ok(_audit(["MOVIEPILOT"]) == (False, False), "非魔流标签：既非 managed 也非 orphan")

    print(f"\n{'✅ PASS' if _FAIL == 0 else '❌ FAIL'}  （{_OK} 通过 / {_FAIL} 失败）")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
