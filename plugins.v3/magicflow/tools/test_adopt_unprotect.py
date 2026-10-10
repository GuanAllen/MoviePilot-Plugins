#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 15.8.12「纳管 ≠ 手动保留」离线单测。

验什么（纯标准库 + 临时目录，不连任何真库 / 真下载器）：
  1. ``MagicFlowStore.note_adopted``：纳管只进 ``adopted_hashes``，
     同一 hash 若已在 ``protected_torrents``（历史遗留 / 并发写）→ 顺手摘除；
  2. ``MagicFlowStore.purge_adopted_protected``：一次性清理历史残留
     （各任务 `protected ∩ adopted` 全摘），纳管身份保留、幂等（二次调用 0 条）；
  3. 大小写不敏感（protected 存大写、adopted 存小写也能对上）；
  4. 热重载换代：注册表里的**旧类**实例（MP 清模块缓存后）在新代码下自动换成
     新类（同一对象、内存状态保留）—— 否则新方法永远调不到。

用法：``python3 tools/test_adopt_unprotect.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
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
    print("== 15.8.12 纳管 ≠ 手动保留 ==")
    p = _load("mf_adopt_unprotect_test_persistence", "persistence.py")
    tmp = Path(tempfile.mkdtemp(prefix="mf_adopt_"))
    store = p.MagicFlowStore(tmp, kv=None)

    H_A = "a" * 40
    H_B = "b" * 40
    H_C = "c" * 40

    # --- 1) note_adopted 顺手摘掉同 hash 的硬保护 ---
    store.protect_torrent("t1", H_A)
    store.protect_torrent("t1", H_B)
    store.protect_torrent("t1", H_C)
    _n = store.note_adopted("t1", [H_A, H_B])
    _ok(_n == 2, "note_adopted 返回新增 2 条纳管")
    _ok(store.get_adopted("t1") == {H_A, H_B}, "纳管集合 = {A,B}")
    _ok(store.get_protected_torrents("t1") == {H_C}, "纳管 hash 已从 protected 摘除，只剩 C")

    # --- 2) 幂等：重复纳管不再重复计数、也不动 protected ---
    _n2 = store.note_adopted("t1", [H_A, H_B])
    _ok(_n2 == 0, "重复纳管 → 新增 0（幂等）")
    _ok(store.get_protected_torrents("t1") == {H_C}, "重复纳管不影响 protected")

    # --- 3) 历史残留：模拟旧代码「纳管 + protect 同写」，purge 一次清掉 ---
    store.protect_torrent("t1", H_A)          # 旧行为留下的（纳管 hash 又在 protected 里）
    store.note_adopted("t2", [H_B])
    store.protect_torrent("t2", H_B)
    store.protect_torrent("t3", H_C)          # 真·手动保留（无纳管）→ 不该被动
    _ok(store.get_protected_torrents("t1") == {H_A, H_C}, "残留已就位：t1 protected={A,C}")
    _purged = store.purge_adopted_protected()
    _ok(_purged == 2, f"purge 摘除 2 条（实际 {_purged}）")
    _ok(store.get_protected_torrents("t1") == {H_C}, "t1: 纳管残留 A 已摘，手动 C 保留")
    _ok(store.get_protected_torrents("t2") == set(), "t2: 纳管残留 B 已摘")
    _ok(store.get_protected_torrents("t3") == {H_C}, "t3: 纯手动保留不受影响")
    _ok(store.get_adopted("t1") == {H_A, H_B} and store.get_adopted("t2") == {H_B},
        "纳管身份照旧保留（软保护）")

    # --- 4) 幂等：二次 purge 无残留 ---
    _ok(store.purge_adopted_protected() == 0, "二次 purge → 0 条（幂等）")

    # --- 5) 大小写：protected 存大写、adopted 存小写 ---
    store.protect_torrent("t4", H_A.upper())
    store.note_adopted("t4", [H_A])
    _ok(store.get_protected_torrents("t4") == set(), "大小写不同的同一 hash 也能摘除")

    # --- 6) 热重载换代：旧类实例（注册表里跨重载留着）自动升到新类 ---
    store.marker_v2 = "kept"                       # 假装是换代前写进去的内存状态
    p2 = _load("mf_adopt_unprotect_test_persistence_v2", "persistence.py")
    store2 = p2.MagicFlowStore(tmp, kv=None)
    _ok(store2 is store, "热重载后仍是同一实例（单例按 data_dir，避免快照互覆）")
    _ok(type(store2) is p2.MagicFlowStore, "旧类实例已换代到新类（新方法可调用）")
    _ok(getattr(store2, "marker_v2", None) == "kept", "换代不重建对象：内存状态保留")
    _ok(store2.get_protected_torrents("t3") == {H_C}, "换代后既有数据仍可读")
    store2.protect_torrent("t5", H_A.upper())
    store2.note_adopted("t5", [H_A])
    _ok(store2.get_protected_torrents("t5") == set(), "换代后的新方法体真实生效")

    print(f"\n{'✅ PASS' if _FAIL == 0 else '❌ FAIL'}  （{_OK} 通过 / {_FAIL} 失败）")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
