#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · tracker 归属缓存（★ 15.3.1）离线回归 —— 真跑 downloader_ops.py，不需 MoviePilot / qB。

背景（2026-10-07 12:5x 复盘）：每次插件 hot reload 后第一次 ``_build_status_heavy`` 要 20~50s。
根因两条：
  ① ``_parse_torrent_info()`` 构造 ``TorrentInfo(...)`` 时**根本没传 ``tracker``**
     （字段是有的，qB 实测 1190/1368 条非空）→ ``_same_site_torrents()`` 里
     ``getattr(t,'tracker','')`` 恒空 → 对**每个种**兜底调一次 ``torrents_trackers``（~1368 × 20ms ≈ 27s）；
  ② 兜底缓存 ``_TRACKER_DOMAIN_CACHE`` 是**模块级 dict**，reload 即清空 → 每次都从头来一遍。

修法：
  ① ``_parse_torrent_info`` 带上 ``tracker``（有值就用，省掉逐 hash 兜底）；
  ② 缓存挪到 ``persistence._shared().singletons``（进程级单例 → 热重载不丢；仍是纯内存，
     **不写 Redis、不落盘**）。外加软上限淘汰防跨重载长期膨胀。

用法：``python3 tools/test_tracker_cache.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_trackercache_test"


def _load_pkg(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg = types.ModuleType(PKG)
_pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = _pkg

persistence = _load_pkg(PKG + ".persistence", "persistence.py")
_load_pkg(PKG + ".fingerprint", "fingerprint.py")
_load_pkg(PKG + ".qbsync", "qbsync.py")
do = _load_pkg(PKG + ".downloader_ops", "downloader_ops.py")

FAILS = []
N = 0


def ok(cond, label):
    global N
    N += 1
    if not cond:
        FAILS.append(label)
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


# ---------------------------------------------------------------- [1] 解析带 tracker
print("[1] _parse_torrent_info 带上 tracker 字段")
_row = {
    "hash": "AA11",
    "name": "Some.Release.2026.1080p",
    "size": 5 * 1024 ** 3,
    "state": "uploading",
    "tracker": "https://tracker.cyanbug.net/announce.php?passkey=deadbeef",
}
info = do.DownloaderAdapter._parse_torrent_info(None, _row)
ok(getattr(info, "tracker", None) == _row["tracker"], "tracker 原样带出（含 query）")
ok(info.hash == "AA11" and info.title.startswith("Some.Release"), "其余字段未受影响")
empty = do.DownloaderAdapter._parse_torrent_info(None, {"hash": "BB22", "name": "x", "size": 1, "state": "paused"})
ok(empty.tracker == "", "缺 tracker 字段 → 空串（不报错）")
_pkg_list = do.DownloaderAdapter._parse_torrent_info(
    None, {"hash": "CC33", "name": "x", "size": 1, "state": "paused", "tracker": None}
)
ok(_pkg_list.tracker == "", "tracker=None → 空串")

# ---------------------------------------------------------------- [2] 缓存是进程级单例
print("[2] _tracker_domain_cache() 幂等 + 挂在 _shared().singletons")
c1 = do._tracker_domain_cache()
c2 = do._tracker_domain_cache()
ok(isinstance(c1, dict) and c1 is c2, "两次调用返回同一 dict 对象")
shared = persistence._shared()
ok(shared.singletons.get(do._TRACKER_DOMAIN_KEY) is c1, "注册在 persistence._shared().singletons")
ok(do._TRACKER_DOMAIN_KEY.startswith("tracker"), f"注册键名合理：{do._TRACKER_DOMAIN_KEY}")

# ---------------------------------------------------------------- [3] 暖值写缓存
print("[3] tracker_domain() 写缓存 + 二次命中不打 qB")


class _FakeDL:
    def __init__(self):
        self.calls = 0

    def _qb_client(self):
        return object()

    def _qb_call(self, name, torrent_hash=None):
        self.calls += 1
        return [{"url": "https://tracker.example.net/announce"}, {"url": "** [DHT] **"}]


fdl = _FakeDL()
h1 = "1111222233334444555566667777888899990000"
h1 = h1[:40]
host = do.DownloaderAdapter.tracker_domain(fdl, h1)
ok(host == "example.net", f"归一化去 tracker. 前缀 → {host!r}")
ok(fdl.calls == 1, "首次查 qB 1 次")
ok(c1.get(h1) is not None and c1[h1][1] == host, "缓存已写入该 hash（值=归一化域名）")
again = do.DownloaderAdapter.tracker_domain(fdl, h1.upper())
ok(again == "example.net", "大写 hash 也命中（大小写归一）")
ok(fdl.calls == 1, "二次命中缓存：qB 调用数仍为 1")

# ---------------------------------------------------------------- [4] 模拟热重载后仍在
print("[4] 模拟插件热重载（重跑模块）→ 缓存不丢")
before = dict(c1)
do2 = _load_pkg(PKG + ".downloader_ops_reload", "downloader_ops.py")
c3 = do2._tracker_domain_cache()
ok(c3 is c1, "重载后拿到的是同一个共享 dict")
ok(c3.get(h1) == before.get(h1), "重载后暖值仍在（不会重新逐 hash 拉 qB）")
ok(do2._TRACKER_DOMAIN_KEY == do._TRACKER_DOMAIN_KEY, "重载后注册键名一致")

# ---------------------------------------------------------------- [5] 软上限淘汰
print("[5] 软上限淘汰（防跨重载长期膨胀）")
c1.clear()
_old_max = do._TRACKER_DOMAIN_MAX
do._TRACKER_DOMAIN_MAX = 10
for i in range(12):
    do._tracker_domain_store(c1, f"h{i:04d}", i, "example.net")
ok(len(c1) < 12, f"超过上限后触发淘汰（现 {len(c1)} < 12）")
ok(len(c1) >= 5, f"保留多数条目（现 {len(c1)}）")
ok(c1.get("h0011") is not None, "最新的条目一定还在")
do._TRACKER_DOMAIN_MAX = _old_max
c1.clear()

# ---------------------------------------------------------------- [6] 源码级护栏
print("[6] 源码级护栏（防回退）")
src = (ROOT / "downloader_ops.py").read_text(encoding="utf-8")
ok("persistence._shared()" in src and "_TRACKER_DOMAIN_KEY" in src, "缓存走 _shared() 单例（非模块级裸 dict）")
ok(re.search(r"tracker=str\(_kv\(torrent,\s*\"tracker\"", src) is not None, "_parse_torrent_info 传了 tracker=")
ok("_TRACKER_DOMAIN_CACHE: Dict[str, Tuple[float, str]] = {}" in src, "仍保留模块级兜底 dict（_shared 不可用时退化）")
brush_src = (ROOT / "features" / "brush.py").read_text(encoding="utf-8")
ok('for _pre in ("tracker.", "www."):' in brush_src, "_same_site_torrents 内联 host 与 tracker_domain 同口径归一化")

# ---------------------------------------------------------------- 汇总
print()
if FAILS:
    print(f"❌ FAIL：{len(FAILS)}/{N} 断言失败")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print(f"✅ PASS：{N}/{N} 断言全过")
