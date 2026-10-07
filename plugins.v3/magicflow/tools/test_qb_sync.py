#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · qB 增量同步（★ 15.3.0）离线回归 —— 真跑 qbsync.py，不需 MoviePilot / qB。

背景（Master 2026-10-07 12:04「请求 qb 的这个数据大多时候不会变为什么不能增量更新」）：
  qB 的 ``torrents_info()`` 每次全量（实测 1368 条 ≈ 2.27MB / 0.51s），插件每 20~30s 要一份
  → 重复字节极多。改用 ``/sync/maindata?rid=`` 增量（实测无关键变动 ≈ 8~10KB / 0.03s）。

``qbsync.QbSyncStore`` 口径（本测试逐条钉死）：
  1) 首次调用 rid=0 → **全量建表**（``full_pulls``++），每行注入 ``hash`` 字段；
  2) 之后带上次 rid → **增量合并**：``torrents`` 打补丁字段 + ``torrents_removed`` 删行；
  3) rid 前进但无任何 torrent 变化 → **不重建列表**（``unchanged_pulls``++）；
  4) ``full_update`` / rid 回退（qB 重启）/ 首次 → 全量重建（旧行清掉）；
  5) **任何异常 / 客户端无 sync_maindata / qbc=None → 返回 None**（调用方回退全量拉取）；
  6) 纯内存：不写 Redis、不落盘；按下载器名走 ``persistence._shared()`` 单例。

用法：``python3 tools/test_qb_sync.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_qbsync_test"


def _load_pkg(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg = types.ModuleType(PKG)
_pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = _pkg

_load_pkg(PKG + ".persistence", "persistence.py")
qbsync = _load_pkg(PKG + ".qbsync", "qbsync.py")

QbSyncStore = qbsync.QbSyncStore
get_qb_sync_store = qbsync.get_qb_sync_store

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


class FakeQb:
    """按脚本依次返回 sync_maindata 的结果（dict / Exception）。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def sync_maindata(self, rid=0):
        self.calls.append(rid)
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def row(name, **extra):
    d = {"name": name, "size": 100, "state": "uploading", "tags": "a, b", "seeding_time": 10}
    d.update(extra)
    return d


def main() -> int:
    print("【1】首次调用 → 全量建表（rid=0，注入 hash）")
    s = QbSyncStore("qbittorrent")
    qb = FakeQb([
        {"rid": 1, "full_update": True, "torrents": {
            "AA" * 20: row("t1"), "BB" * 20: row("t2")}},
    ])
    rows = s.torrents(qb)
    ok(qb.calls == [0], "首次用 rid=0（强制全量）")
    ok(len(rows) == 2, "全量返回 2 行")
    ok(all(r.get("hash") == r["hash"].lower() and r["hash"] for r in rows), "每行注入了小写 hash")
    st = s.stats()
    ok(st["full_pulls"] == 1 and st["delta_pulls"] == 0, "full_pulls=1 / delta_pulls=0")
    ok(st["torrents"] == 2 and st["rid"] == 1, "stats.torrents=2 / rid=1")

    print("【2】增量合并（只改字段）")
    qb.script = [{"rid": 2, "torrents": {"AA" * 20: {"seeding_time": 999, "ratio": 1.5}}}]
    rows = s.torrents(qb)
    ok(qb.calls[-1] == 1, "第二次带上 rid=1")
    d = {r["hash"]: r for r in rows}
    ok(d["aa" * 20]["seeding_time"] == 999 and d["aa" * 20]["ratio"] == 1.5, "补丁字段已合并")
    ok(d["aa" * 20]["name"] == "t1", "未变字段保留（name=t1）")
    ok(len(rows) == 2, "行数不变")
    ok(s.stats()["delta_pulls"] == 1, "delta_pulls=1")
    ok(s.stats()["last_delta_n"] == 1, "last_delta_n=1")

    print("【3】增量新增 + 删除（torrents_removed）")
    qb.script = [{"rid": 3, "torrents": {"CC" * 20: row("t3")},
                  "torrents_removed": ["BB" * 20]}]
    rows = s.torrents(qb)
    hs = {r["hash"] for r in rows}
    ok(hs == {"aa" * 20, "cc" * 20}, "删掉 bb、加上 cc")
    ok(len(rows) == 2, "行数=2")

    print("【4】无变化（torrents 空）→ 不重建，计数 unchanged")
    before = s.stats()["unchanged_pulls"]
    before_delta = s.stats()["delta_pulls"]
    qb.script = [{"rid": 4, "torrents": {}, "server_state": {"up_info_speed": 123}}]
    rows = s.torrents(qb)
    ok(len(rows) == 2, "内容不变")
    ok(s.stats()["unchanged_pulls"] == before + 1, "unchanged_pulls++")
    ok(s.stats()["delta_pulls"] == before_delta, "delta_pulls 未增加（空增量不算合并）")

    print("【5】rid 回退 / full_update → 全量重建（旧行清掉）")
    qb.script = [{"rid": 1, "full_update": True, "torrents": {"DD" * 20: row("t4")}}]
    rows = s.torrents(qb)
    ok([r["hash"] for r in rows] == ["dd" * 20], "全量重建后只剩 dd")
    ok(s.stats()["full_pulls"] == 2, "full_pulls=2")

    print("【6】异常 → 返回 None（调用方回退全量），errors++")
    err_before = s.stats()["errors"]
    qb.script = [RuntimeError("boom")]
    ok(s.torrents(qb) is None, "抛异常返回 None")
    ok(s.stats()["errors"] == err_before + 1, "errors++")
    ok("sync_maindata 失败" in s.stats().get("last_error", ""), "last_error 记下原因")

    print("【7】客户端无 sync_maindata → None")

    class NoSyncQb:
        pass

    ok(QbSyncStore("x").torrents(NoSyncQb()) is None, "无该方法返回 None")

    print("【8】qbc=None → None")
    ok(QbSyncStore("x").torrents(None) is None, "None 客户端返回 None")

    print("【9】单例注册表（按下载器名；跨调用同一对象）")
    a = get_qb_sync_store("qbittorrent")
    b = get_qb_sync_store("qbittorrent")
    c = get_qb_sync_store("transmission")
    ok(a is b, "同名返回同一实例")
    ok(a is not c, "不同名返回不同实例")
    ok(isinstance(a.stats(), dict) and "full_pulls" in a.stats(), "stats() 可读")

    print()
    if FAILS:
        print(f"FAIL：{len(FAILS)}/{N} 项未过 → {FAILS}")
        return 1
    print(f"PASS：{N}/{N} 断言全过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
