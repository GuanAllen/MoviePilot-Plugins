#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 静默池「清理（删除）」离线回归（★ 13.0.1，真跑 silent.py，不需 MoviePilot）。

★ 13.0.1：撤掉 13.0.0 新造的 ``_silent_purge``（那是多余的第二套删除口径），
   本套测试改为直接测**原来的清除程序** ``_silent_purge_incomplete``（未下完直接删）
   —— 它是静默池唯一自动执行的「删除」步（``silent_host`` 每轮 ``_s1``），
   ``_silent_plain_sweep``（低效普通清扫）另见 ``test_silent_hr_split.py``。

覆盖：
  1) 数据路径口径 ``common.torrent_data_key``（content_path 优先 / 退回 save_path+title）
     + 真 ``TorrentInfo`` 护栏（**无 name 字段**、有 content_path —— 取 .name 恒空曾致共用判据失效）；
  2) 共用判定 ``silent._shared_key_hits``（相等 / 互为上下级目录 / 不相关）；
  3) ``_silent_purge_incomplete`` 干跑：只列计划、**零写入**；
  4) 真写：删条目+删文件；**同数据另有完成种 → 只删条目**（``torrent_only``）；
  5) 保护类（跨站来源 / 推荐中 / 辅种复用 / 库内资产）**不删**；
  6) 已完成种（progress≈1 且非 DL 态）**不在**「未下完」范围。

用法：``python3 tools/test_silent_cleanup.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_silent_cleanup_test"


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

# 桩 app.*（common.py 顶部 import MoviePilot 依赖）
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

# 叶子模块桩（silent.py 顶层 import 的符号；bonus 需 app 环境 → 不载真模块）
for _modname, _attrs in (("bonus", ("calc_bonus_per_hour", "TorrentBonusInfo")),
                         ("fetcher", ("SiteCandidateTorrent",))):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    sys.modules[PKG + "." + _modname] = _m

fingerprint = _load(PKG + ".fingerprint", "fingerprint.py")
persistence = _load(PKG + ".persistence", "persistence.py")
tags = _load(PKG + ".tags", "tags.py")
common = _load(PKG + ".common", "common.py")
downloader_ops = _load(PKG + ".downloader_ops", "downloader_ops.py")
silent = _load(PKG + ".features.silent", "features/silent.py")

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _torrent(h, state="pausedDL", progress=0.5, title=None, save="/x", tags=None, cp=None):
    """★ 与真 TorrentInfo 同形：**没有 name 字段**（qB 的 name → title），数据路径走 content_path。"""
    import types as _t
    _nm = title or h
    return _t.SimpleNamespace(hash=h, title=_nm, state=state, size=1 << 30,
                              tags=list(tags or []), progress=progress,
                              save_path=save, content_path=(cp if cp is not None else f"{save}/{_nm}"))


class _Ledger:
    """最小静默账本桩（items/get/put/drop）。"""

    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)

    def get(self, h):
        return self._d.get(str(h or "").lower()) or {}

    def put(self, h, rec):
        self._d[str(h or "").lower()] = dict(rec or {})

    def drop(self, h):
        self._d.pop(str(h or "").lower(), None)


class Harness(silent.SilentMixin):
    """在真 SilentMixin 上挂桩：真跑 `_silent_purge_incomplete` 的编排（分类输入可控）。"""

    def __init__(self, ledger, snap):
        self.ledger = {str(k).lower(): dict(v or {}) for k, v in (ledger or {}).items()}
        self.torrents = {str(k).lower(): v for k, v in (snap or {}).items()}
        self.delete_calls = []
        self.journal = None

    def _tag_state(self):
        return _Ledger(self.ledger)

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _get_downloader(self, name="qbittorrent"):
        return _DL(self)

    def _journal_deletions(self, by_task, log_prefix=""):
        self.journal = by_task

    def _log(self, msg, level=None):
        pass

    def get_data_path(self):
        return ROOT


class _DL:
    def __init__(self, h):
        self.h = h

    def delete_torrents(self, hashes, delete_file=False, reason="", source=""):
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        self.h.delete_calls.append((list(hs), bool(delete_file)))
        return len(hs), None


SIL = tags.STATE_SILENT


def _rec(**kw):
    d = {"state": SIL}
    d.update(kw)
    return d


def main() -> int:
    print("=" * 64)
    print("魔流 · 13.0.1 静默池清理（原清除程序 _silent_purge_incomplete）回归")
    print("=" * 64)

    # ---- ① 数据路径口径 ----
    print("\n[1] 数据路径口径 torrent_data_key + 真 TorrentInfo 护栏")
    _ok(common.torrent_data_key(_torrent("h1", cp="/media/A/B")) == "/media/A/B",
        "content_path 优先作为数据路径 key")
    _ok(common.torrent_data_key(_torrent("h2", save="/media/X", title="Y")) == "/media/X/Y",
        "无 content_path → 退回 save_path/title")
    from dataclasses import fields as _fields
    _cols = {f.name for f in _fields(downloader_ops.TorrentInfo)}
    _ok("name" not in _cols, "真 TorrentInfo 无 name 字段（取 .name 恒空 → 曾致共用判据失效）")
    _ok("content_path" in _cols, "真 TorrentInfo 有 content_path（共用/同数据判据的真值字段）")

    # ---- ② 共用判定 ----
    print("\n[2] 共用判定 _shared_key_hits（相等 / 互为上下级 / 不相关）")
    done = {"/media/D": {"a"}, "/media/E/child": {"b"}}
    _ok(silent._shared_key_hits("/media/D", done, "h") is True, "同路径 → 共用")
    _ok(silent._shared_key_hits("/media/D/x.mkv", done, "h") is True, "目标在别人目录内（子级）→ 共用")
    _ok(silent._shared_key_hits("/media/E", done, "h") is True, "目标目录包含别人的目录（父级）→ 共用")
    _ok(silent._shared_key_hits("/media/Z", done, "h") is False, "路径无关 → 不共用")
    _ok(silent._shared_key_hits("/media/D", {"/media/D": {"h"}}, "h") is False, "只有自己占着 → 不算共用")

    # ---- ③ 干跑：零写入 ----
    print("\n[3] 干跑（apply=False）：只列计划、零写入")
    h = Harness(
        {"a1": _rec(), "a2": _rec(), "c1": _rec()},
        {"a1": _torrent("a1", progress=0.3, title="A"),
         "a2": _torrent("a2", progress=0.8, state="pausedDL", title="B"),
         "c1": _torrent("c1", progress=1.0, state="pausedUP", title="C")},
    )
    rep = h._silent_purge_incomplete(apply=False)
    _ok(rep["pending"] == 2, f"未下完 2 个（{rep['pending']}）")
    _ok(h.delete_calls == [], "干跑：下载器零调用")
    _ok(rep["deleted"] == 0, "干跑：deleted=0")

    # ---- ④ 真写：删条目+删文件 / 同数据 → 只删条目 ----
    print("\n[4] 真写（apply=True）：删条目+删文件；同数据另有完成种 → 只删条目")
    h = Harness(
        {"a1": _rec(), "a2": _rec()},
        {"a1": _torrent("a1", progress=0.3, title="solo", save="/media/solo"),
         "a2": _torrent("a2", progress=0.2, title="shared", save="/media/sh"),
         "a9": _torrent("a9", progress=1.0, state="pausedUP", title="shared", save="/media/sh")},
    )
    rep = h._silent_purge_incomplete(apply=True)
    dmap = {x[0][0]: x[1] for x in h.delete_calls}
    _ok(rep["deleted"] == 2, f"删 2 个（{rep['deleted']}）")
    _ok(dmap.get("a1") is True, "独享数据 → delete_file=True（删条目+删文件）")
    _ok(dmap.get("a2") is False, "同 save_path/标题 另有完成种 → delete_file=False（只删条目）")
    _ok(rep["torrent_only"] == 1, f"torrent_only=1（{rep['torrent_only']}）")
    _ok("a1" not in h.ledger and "a2" not in h.ledger, "删成功的从账本摘掉（drop）")

    # ---- ⑤ 保护类不删 ----
    print("\n[5] 保护类（跨站来源 / 推荐中 / 辅种复用 / 库内资产）不删")
    h = Harness(
        {"p1": _rec(), "p2": _rec(), "p3": _rec(), "p4": _rec(in_library=True)},
        {"p1": _torrent("p1", progress=0.4, tags=["魔流-跨站"], title="x1"),
         "p2": _torrent("p2", progress=0.4, tags=["魔流-推荐"], title="x2"),
         "p3": _torrent("p3", progress=0.4, tags=["魔流-辅种"], title="x3"),
         "p4": _torrent("p4", progress=0.4, title="x4")},
    )
    rep = h._silent_purge_incomplete(apply=True)
    _ok(rep["pending"] == 0 and h.delete_calls == [],
        "跨站/推荐/辅种复用/库内资产 都不在「未下完直接删」范围")

    # ---- ⑥ 已完成种不在范围 ----
    print("\n[6] 已完成种（progress≈1 且非 DL 态）不在「未下完」范围")
    h = Harness({"d1": _rec()}, {"d1": _torrent("d1", progress=1.0, state="pausedUP", title="done")})
    rep = h._silent_purge_incomplete(apply=True)
    _ok(rep["pending"] == 0 and h.delete_calls == [], "已完成且非 DL → 不处理（归 plain_sweep/分拣管）")

    print("\n" + "=" * 64)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
