#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 删除闸门 fail-closed 离线回归测试（真跑，不需要 MoviePilot 环境）。

覆盖 ``DownloaderAdapter.delete_torrents`` 的两个历史洞：
  - **fail-silent**：闸门取值链拿不到任何回调（含热重载后类属性归零 + 裸构造）
    → 旧代码整段跳过、照样删；
  - **fail-open**：闸门回调抛异常 → 旧代码 ``_blk=set()`` 照样删。

安全性验证（fail-closed 默认开）：
  1) 闸门抛异常 → 假下载器 **零调用**、返回 0；关掉 fail-closed → 恢复放行（调用发生）；
  2) 闸门为 None（fail-closed 开）→ 零调用；
  3) 闸门正常返回空集 → 正常删除（调用发生）。
  额外：``set_gate_installer`` 注册后，**裸构造** ``DownloaderAdapter(...)`` 会自动挂闸门
  （用 ``object.__new__`` 绕过 ``__init__``，并 monkeypatch ``_init_downloader`` 避开 MP 环境）。

用法：``python3 tools/test_gate_failclosed.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 以「合成包」加载 downloader_ops —— 它顶部用相对导入 `from .fingerprint import ...`，
# 直接 `import downloader_ops` 会因「无父包」而失败。这里给它造一个父包，让相对导入可解析。
# ---------------------------------------------------------------------------
_PKG = "_mf_gate_test_pkg"
if _PKG not in sys.modules:
    _pkg = types.ModuleType(_PKG)
    _pkg.__path__ = [str(ROOT)]
    sys.modules[_PKG] = _pkg

_spec = importlib.util.spec_from_file_location(_PKG + ".downloader_ops", ROOT / "downloader_ops.py")
downloader_ops = importlib.util.module_from_spec(_spec)
sys.modules[_PKG + ".downloader_ops"] = downloader_ops
_spec.loader.exec_module(downloader_ops)

DownloaderAdapter = downloader_ops.DownloaderAdapter


class FakeDownloader:
    """假下载器：记录每次 delete_torrents 调用。"""

    def __init__(self) -> None:
        self.calls: list = []

    def delete_torrents(self, ids=None, delete_file=False):  # noqa: D401
        self.calls.append((list(ids or []), bool(delete_file)))
        return True


def _make_adapter(gate):
    """绕过 __init__ 造一个只带删除相关属性的适配器。"""
    obj = object.__new__(DownloaderAdapter)
    obj._downloader = FakeDownloader()
    obj.gate = gate
    obj.deletion_log = None
    # 桩掉报到（离线无下载器）
    obj.reannounce = lambda hashes: (0, None)
    return obj


def _boom(_hashes):
    raise RuntimeError("gate boom")


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def main() -> int:
    print("=" * 64)
    print("魔流 · 删除闸门 fail-closed 回归测试")
    print("=" * 64)

    # ---- 前置：默认应为 fail-closed（安全默认） ----
    print("\n[0] 默认策略")
    _ok(downloader_ops._GATE_FAIL_CLOSED is True, "默认 fail-closed = True（安全默认）")

    # ---- 1) 闸门抛异常：fail-closed 开 → 零调用 ----
    print("\n[1] 闸门抛异常 + fail-closed 开 → 全部阻断")
    downloader_ops.set_gate_fail_closed(True)
    ad = _make_adapter(_boom)
    n, err = ad.delete_torrents(["aa", "bb"], delete_file=False, reason="t", source="t")
    _ok(n == 0, f"返回 0（实际 {n}）")
    _ok(ad._downloader.calls == [], f"假下载器零调用（实际 {ad._downloader.calls}）")
    _ok(bool(err) and "fail-closed" in (err or ""), f"错误说明含 fail-closed（{err!r}）")

    # ---- 2) 闸门抛异常：fail-closed 关 → 恢复放行 ----
    print("\n[2] 闸门抛异常 + fail-closed 关 → 恢复旧行为（放行）")
    downloader_ops.set_gate_fail_closed(False)
    try:
        ad = _make_adapter(_boom)
        n, _err = ad.delete_torrents(["aa"], delete_file=False, reason="t", source="t")
        _ok(n == 1, f"返回 1（放行，实际 {n}）")
        _ok(len(ad._downloader.calls) == 1, f"假下载器被调用 1 次（实际 {len(ad._downloader.calls)}）")
    finally:
        downloader_ops.set_gate_fail_closed(True)

    # ---- 3) 闸门为 None：fail-closed 开 → 零调用 ----
    print("\n[3] 闸门为 None + fail-closed 开 → 全部阻断（堵 fail-silent）")
    downloader_ops.set_gate_fail_closed(True)
    ad = _make_adapter(None)
    n, err = ad.delete_torrents(["aa", "bb", "cc"], delete_file=False, reason="t", source="t")
    _ok(n == 0, f"返回 0（实际 {n}）")
    _ok(ad._downloader.calls == [], f"假下载器零调用（实际 {ad._downloader.calls}）")
    _ok(bool(err) and "fail-closed" in (err or ""), f"错误说明含 fail-closed（{err!r}）")

    # ---- 4) 闸门正常返回空集 → 正常删除 ----
    print("\n[4] 闸门正常返回空集 → 正常删除")
    ad = _make_adapter(lambda h: set())
    n, err = ad.delete_torrents(["aa", "bb"], delete_file=False, reason="t", source="t")
    _ok(n == 2, f"返回 2（实际 {n}）")
    _ok(len(ad._downloader.calls) == 2, f"假下载器被调用 2 次（实际 {len(ad._downloader.calls)}）")
    _ok(err is None, f"无错误（实际 {err!r}）")

    # ---- 5) 闸门返回受保护子集 → 只删未受保护部分 ----
    print("\n[5] 闸门返回受保护子集 → 只删未受保护部分")
    ad = _make_adapter(lambda h: {"bb"})
    n, _err = ad.delete_torrents(["aa", "bb"], delete_file=False, reason="t", source="t")
    _ok(n == 1, f"返回 1（只删 aa，实际 {n}）")
    _ok(len(ad._downloader.calls) == 1 and ad._downloader.calls[0][0] == ["aa"],
        f"仅删 aa（实际 {ad._downloader.calls}）")

    # ---- 6) 安装器：裸构造自动挂闸门（消除「至少设过一次」的顺序依赖） ----
    print("\n[6] set_gate_installer → 裸构造 DownloaderAdapter(...) 自动挂闸门")
    hit = {"n": 0}

    def _installer(dl):
        hit["n"] += 1
        dl.gate = lambda h: set()
        dl.deletion_log = None

    downloader_ops.set_gate_installer(_installer)
    _orig_init = DownloaderAdapter._init_downloader
    DownloaderAdapter._init_downloader = lambda self: None  # 避开 MP 环境
    try:
        dl = DownloaderAdapter("qbittorrent")
    finally:
        DownloaderAdapter._init_downloader = _orig_init
        downloader_ops.set_gate_installer(None)
    _ok(hit["n"] == 1, f"安装器被调用 1 次（实际 {hit['n']}）")
    _ok(callable(getattr(dl, "gate", None)), "裸构造的适配器已自动带 gate")

    print("\n" + "=" * 64)
    print(f"PASS：{CHECKS} 项断言全部通过 ✅")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"\n{e}")
        raise SystemExit(1)
