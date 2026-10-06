#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""护栏：补源**来源站**禁用规则不得被绕过/删除（11.5.0 新增，preflight 第 10 步）。

背景（踩过，2026-10-05）
------------------------
为救一个欠 H&R 的停滞种，我**手动走 MP 下载接口**从 `pt.btschool.club`
（hr=true / 20h）拉了一份同 Release → 结果既没救成，又**凭空多了一笔学校 H&R 欠账**
（而且没进账本、完全不可见）。

插件自己的 rescue 路径本来就有「来源站 ``hr == False`` 才许当补源」的硬过滤，
问题在于：① 规则散落在多处内联判断，容易被改掉；② 旁路加种（手动/MP 接口）根本不经过它。

本工具把这条规则钉成**静态棘轮**：
  1. `features/rescue.py` 必须导出唯一判定 `rescue_source_blocked`，且语义为
     `hr is not False`（False 才放行，True/None/其它一律禁）；
  2. `_rescue_candidates` / `_rescue_iyuu_candidates` / `_rescue_candidates_mp`
     （候选检索：IYUU 指纹索引优先 + MP 名称回退）与 `_rescue_skipped_sites`（站点排除清单）
     必须**调用**它——不许再写内联的 `flag is not False` / `flag is False` 判断；
  3. `features/agentapi.py` 的能力清单必须登记 `GET /agent/blindspot`
     （H&R 盲区 = 旁路加种的可见性出口）。

纯标准库（ast + 正则），零网络零写。

用法：``python3 tools/check_rescue_guard.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import ast
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESCUE = os.path.join(ROOT, "features", "rescue.py")
AGENTAPI = os.path.join(ROOT, "features", "agentapi.py")

GUARD_FN = "rescue_source_blocked"


def _fail(msg: str) -> int:
    print(f"❌ {msg}")
    return 1


def main() -> int:
    print("── 补源来源站护栏（hr != False 一律禁用）──")
    try:
        with open(RESCUE, encoding="utf-8") as fh:
            src = fh.read()
    except OSError as e:
        return _fail(f"读不到 features/rescue.py: {e}")
    tree = ast.parse(src)

    # 1) 唯一判定函数存在，且是模块级 def
    fn = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == GUARD_FN:
            fn = node
    if fn is None:
        return _fail(f"features/rescue.py 缺少模块级判定函数 {GUARD_FN}()（护栏被删？）")
    rets = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    try:
        fsrc = ast.unparse(fn)
    except Exception:  # noqa: BLE001
        fsrc = ast.dump(fn)
    if not rets or "is not False" not in fsrc:
        return _fail(f"{GUARD_FN}() 语义必须为「hr is not False」（False 才放行）")
    # 1b) 11.7.0：必须支持「逐种 H&R 站」保守排除参（per_torrent_hr）
    _args = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    if "per_torrent_hr" not in _args:
        return _fail(f"{GUARD_FN}() 缺少 per_torrent_hr 参（逐种 H&R 站保守排除不再生效？）")
    if "is not False" not in fsrc or "per_torrent_hr" not in fsrc:
        return _fail(f"{GUARD_FN}() 必须同时判 hr 与 per_torrent_hr（两道闸）")
    print(f"✅ {GUARD_FN}() 存在且语义正确（hr is not False → True/None 一律禁用；per_torrent_hr 兜底）")

    # 2) 两处过滤必须调用它，且不许再有内联等同判断
    need_callers = ("_rescue_iyuu_siblings", "_rescue_candidates_mp", "_rescue_skipped_sites")
    methods: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[sub.name] = sub
    for name in need_callers:
        m = methods.get(name)
        if m is None:
            return _fail(f"features/rescue.py 找不到 {name}()（改名了？同步本工具）")
        _calls = [n for n in ast.walk(m)
                  if isinstance(n, ast.Call) and
                  ((isinstance(n.func, ast.Name) and n.func.id == GUARD_FN) or
                   (isinstance(n.func, ast.Attribute) and n.func.attr == GUARD_FN))]
        if not _calls:
            return _fail(f"{name}() 没有调用 {GUARD_FN}()（来源站过滤被绕过？）")
        # 11.7.0：调用必须带上逐种 H&R 站参（否则逐种站又会被当干净源放行）
        if not any((len(c.args) >= 2) or any(k.arg == "per_torrent_hr" for k in c.keywords)
                   for c in _calls):
            return _fail(f"{name}() 调用 {GUARD_FN}() 未传 per_torrent_hr（逐种 H&R 站会被放行）")
        print(f"✅ {name}() 走统一判定 {GUARD_FN}()（含逐种站参）")

    # 2b) 编排/分层必须成链（不许新写一个不过护栏的旁路）
    for owner, need in (("_rescue_candidates", "_rescue_iyuu_candidates"),
                        ("_rescue_candidates", "_rescue_candidates_mp"),
                        ("_rescue_iyuu_candidates", "_rescue_iyuu_siblings")):
        fn2 = methods.get(owner)
        if fn2 is None:
            return _fail(f"features/rescue.py 找不到 {owner}()（改名了？同步本工具）")
        calls = {n.func.attr for n in ast.walk(fn2)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        if need not in calls:
            return _fail(f"{owner}() 未走 {need}()（候选/校验路径被改道？）")
    print("✅ 候选链完整：_rescue_candidates → IYUU/MP → _rescue_iyuu_siblings（过护栏）")

    inline = re.findall(r"(?<![A-Za-z0-9_])flag\s+is\s+not\s+False", src)
    if len(inline) > 0:
        return _fail(f"features/rescue.py 仍有 {len(inline)} 处内联 `flag is not False`"
                     f"（应统一走 {GUARD_FN}()）")
    print("✅ 无内联 `flag is not False` 残留（单一真值源）")

    # 3) 盲区可见性出口必须登记（AI 入口）
    try:
        with open(AGENTAPI, encoding="utf-8") as fh:
            api_src = fh.read()
    except OSError as e:
        return _fail(f"读不到 features/agentapi.py: {e}")
    if "/agent/blindspot" not in api_src:
        return _fail("能力清单里没有 /agent/blindspot（H&R 盲区出口未登记）")
    print("✅ GET /agent/blindspot 已登记（H&R 盲区可见）")

    print("\n✅✅ 补源护栏检查通过（来源站 hr != False 一律禁用；旁路加种可见）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
