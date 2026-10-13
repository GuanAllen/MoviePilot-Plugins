#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 删除台账「实际值」离线回归（2026-10-10 Master「按实际值来」）。

背景：``deletions.jsonl`` 的 ``delete_file`` 原本记的是**请求值** —— 共享文件护栏把
「连文件删」降级成「只摘种」时，台账仍写 ``delete_file=True``，看着像删了文件、其实没删
（2026-10-10 红豆饭清理实测：请求 42 个连文件删，实际 0 个真删）。

本次口径：
  A. 台账 ``delete_file`` = 该行**真实生效值**（被共享护栏降级写 ``False``）；
  B. 同批里「连文件删」与「只摘种」**分开发**（各自一行/一组）；
  C. 与删除闸门/账单断言无关的四类硬拦路径行为不变（``blocked`` 行照发，不重复）；
  D. ``delete_file=False`` 的请求整批都写 ``False``（不误升成 True）。

用法：``python3 tools/test_delete_log_effective.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_dellog_test"
CHECKS = 0


def ok(cond, msg):
    global CHECKS
    CHECKS += 1
    if cond:
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        raise SystemExit(1)


def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

# 桩 MoviePilot（common.py / downloader_ops.py 顶部依赖）
for _name, _attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": type("EventType", (), {})}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
):
    _m = sys.modules.get(_name)
    if _m is None:
        _m = types.ModuleType(_name)
        sys.modules[_name] = _m
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)

for _modname, _attrs in (
    ("bonus", ("TorrentBonusInfo",)),
    ("fingerprint", ("Entry", "entries_fingerprint", "info_hash", "load_torrent_entries",
                     "total_size", "inner_fingerprint", "fingerprint")),
    ("fetcher", ("SiteCandidateTorrent",)),
    ("qbsync", ("QB_SYNC_INCREMENTAL", "get_qb_sync_store")),
):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    _m.get_qb_sync_store = lambda: None  # noqa: E731
    sys.modules[PKG + "." + _modname] = _m

_load(PKG + ".common", "common.py")
_load(PKG + ".tags", "tags.py")
dops = _load(PKG + ".downloader_ops", "downloader_ops.py")


class _FakeDownloader:
    """假下载器：记录每个 hash 的 ``delete_file`` 实参，恒成功。"""

    def __init__(self):
        self.calls = []

    def delete_torrents(self, ids=None, delete_file=False, **_kw):
        self.calls.append((list(ids or []), bool(delete_file)))
        return True


class Host(dops.DownloaderAdapter):
    """最小宿主：只覆写 ``delete_torrents`` 依赖的那几个钩子。"""

    def __init__(self, ledger_rows=(), shared=None, blocked=None):
        self._downloader = _FakeDownloader()
        self._shared = set(shared or set())
        self._blocked = set(blocked or set())
        self.rows = []
        self.gate = lambda hs: set(self._blocked)  # noqa: E731
        self.reannounce = lambda hs: (len(hs), None)  # noqa: E731

    # 共享文件护栏：直接给定「哪些 hash 的文件被别人共用」（不再真查下载器）
    def _shared_file_hashes(self, hashes):  # noqa: ANN001
        return {str(h).lower() for h in (hashes or [])} & self._shared

    # 台账回调：收集 (hashes, delete_file, blocked)，与 deletegate._delete_log_cb 同签名
    def deletion_log(self, hashes, delete_file, reason, source, error, blocked, blocked_by=""):
        self.rows.append((list(hashes or []), bool(delete_file), list(blocked or [])))


def main() -> int:
    # ---------------- A. 连文件删 + 共享护栏降级 → 台账记实际值 ----------------
    print("-- A. 请求连文件删、其中 1 个被护栏降级 → 分开发 + 记实际值 --")
    h = Host(shared={"h2"})
    n, err = h.delete_torrents(["h1", "h2"], delete_file=True,
                               reason="r", source="sitedeleted")
    ok(n == 2 and err is None, f"两个都摘掉成功（n={n} err={err}）")
    ok(h._downloader.calls == [(["h1"], True), (["h2"], False)],
       f"下载器实参：h1 连文件、h2 只摘种（实际 {h._downloader.calls}）")
    ok(len(h.rows) == 2, f"台账分两组发（实际 {h.rows}）")
    d = {tuple(r[0]): r[1] for r in h.rows}
    ok(d.get(("h1",)) is True, "★台账 h1 delete_file=True（真删了文件）")
    ok(d.get(("h2",)) is False, "★台账 h2 delete_file=False（被护栏降级 → 记实际值，不再骗人）")

    # ---------------- B. 请求不删文件 → 整批都记 False ----------------
    print("-- B. delete_file=False（只摘种）→ 整批记 False --")
    h = Host()
    h.delete_torrents(["x1", "x2"], delete_file=False, reason="r", source="sitedeleted")
    ok(all(r[1] is False for r in h.rows), f"全部 False（实际 {h.rows}）")
    ok(len(h.rows) == 1, "同批同档只发一组，不拆行")

    # ---------------- C. 硬保护拦截：blocked 行照发、不重复 ----------------
    print("-- C. 闸门硬拦 1 个 → blocked 只随第一组发 --")
    h = Host(shared={"k1"}, blocked={"k2"})
    n, err = h.delete_torrents(["k1", "k2"], delete_file=True, reason="r", source="sitedeleted")
    ok(n == 1, f"仅 1 个成功（n={n}）")
    blk = [r for r in h.rows if r[2]]
    ok(len(blk) == 1 and blk[0][2] == ["k2"], f"blocked 只出现一次且为 k2（实际 {h.rows}）")

    # ---------------- D. 源码护栏：记的是生效值，不是请求值 ----------------
    print("-- D. 源码护栏（_ok_df / _ok_keep 分流）--")
    src = (ROOT / "downloader_ops.py").read_text(encoding="utf-8")
    ok("_ok_df" in src and "_ok_keep" in src, "源码含 _ok_df / _ok_keep 分流")
    ok("(_ok_df if _df else _ok_keep)" in src, "★按 **实际生效值 _df** 分档入账")

    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
