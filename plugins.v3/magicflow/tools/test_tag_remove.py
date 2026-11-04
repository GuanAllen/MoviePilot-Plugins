#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 标签替换的**删除**契约（``DownloaderAdapter.replace_torrent_tags``）离线回归。

背景（2026-10-30）：音乐在途职务 8 个每小时报「摘职务标签 8 个」，连续 14 轮，
逐个回读仍在；同一个种上的「已整理」5 小时被要求删 291 次，一次都没删掉。
根因不是「摘完又贴回来」，而是 ``replace_torrent_tags`` 里那条删除分支写成了
``if drop and hasattr(self._downloader, "remove_torrents_tag")`` —— MP 的 Qbittorrent
适配器**没有**这个方法，``hasattr`` 为假 → 整段删除被静默跳过，``ok`` 仍是 True。
于是每轮都「报成功」，标签一动没动。

本文件钉住的契约：
  [1] 适配器有删除方法 → 走它，标签真删；
  [2] 适配器没有、但底层有 qbittorrentapi → 走 ``torrents_remove_tags``，标签真删；
  [3] 两边都没有 → **必须返回 False**（不许假成功），标签保持原样；
  [4] 调过删除但标签没变（写失败/静默吞掉）→ **回读校验抓出来，返回 False**；
  [5] 只有新增（无差集要删）→ 不需要删除能力，返回 True；
  [6] 删除 + 新增混合 → 最终标签恰好等于目标集合；
  [7] ``tags_enabled=False``（纯账本模式）→ 一律不写，返回 False。

用法：``python3 tools/test_tag_remove.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_tagremove_test"

_fails: list[str] = []
_n = 0


def ok(cond, msg: str) -> None:
    global _n
    _n += 1
    if cond:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        _fails.append(msg)


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
for _rel in ("fingerprint.py", "qbsync.py"):
    _load(PKG + "." + _rel.removesuffix(".py"), _rel)
dlops_mod = _load(PKG + ".downloader_ops", "downloader_ops.py")

DownloaderAdapter = dlops_mod.DownloaderAdapter

H = "a" * 40


# ---------------------------------------------------------------- 桩

class _Raw:
    """MP 的 TorrentInfo：tags 是逗号串（qB 原生形态，``", ".join``）。"""

    def __init__(self, tags):
        self.tags = ", ".join(tags)


class _Qbc:
    """qbittorrentapi.Client 的最小桩：只实现删标签。"""

    def __init__(self, dl, works: bool = True):
        self._dl = dl
        self._works = works
        self.calls: list = []

    def torrents_remove_tags(self, torrent_hashes=None, tags=None):
        self.calls.append((torrent_hashes, list(tags or [])))
        if not self._works:
            return None
        # ★ 真实 qB：输入先 trim 再精确匹配 → 名字自带空白的脏标签永远删不到
        for name in (tags or []):
            clean = str(name).strip()
            if clean in self._dl.tags:
                self._dl.tags.remove(clean)
        return None


class _Dl:
    """MP 的 Qbittorrent 适配器桩：**默认没有** remove_torrents_tag（现场就是这样）。"""

    def __init__(self, tags, *, has_adapter_remove: bool = False,
                 adapter_remove_works: bool = True, adapter_remove_silent: bool = False,
                 qbc=None):
        self.tags = list(tags)
        self.qbc = qbc
        self.adapter_calls: list = []
        self._adapter_works = adapter_remove_works
        self._adapter_silent = adapter_remove_silent
        if has_adapter_remove:
            self.remove_torrents_tag = self._remove_torrents_tag

    def _remove_torrents_tag(self, h, tags):
        self.adapter_calls.append((h, list(tags)))
        if self._adapter_silent:
            # ★ 现场真相：方法存在、返回成功，标签一动没动
            return True
        if not self._adapter_works:
            return False
        self.tags = [t for t in self.tags if t not in tags]
        return True

    def get_torrents(self, ids=None):
        return [_Raw(self.tags)], None

    def set_torrents_tag(self, ids=None, tags=None):
        for t in (tags or []):
            if t not in self.tags:
                self.tags.append(t)


def _adapter(dl) -> object:
    a = object.__new__(DownloaderAdapter)
    a.downloader_name = "qbittorrent"
    a._downloader = dl
    a._service = None
    a.tags_enabled = True
    return a


# ---------------------------------------------------------------- [1] 适配器有删除方法

print("\n[1] 适配器自带 remove_torrents_tag")
_dl = _Dl(["魔流-CARPT-音乐", "魔流-CARPT-静默-资源"], has_adapter_remove=True)
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-CARPT-静默-资源"])
ok(_r is True, "返回 True")
ok(_dl.tags == ["魔流-CARPT-静默-资源"], f"标签真的删掉了（{_dl.tags}）")
ok(len(_dl.adapter_calls) == 1, "走的是适配器方法")

# ---------------------------------------------------------------- [2] 只有 qbittorrentapi

print("\n[2] 适配器没有删除方法 → 走 qbittorrentapi")
_dl = _Dl(["魔流-CARPT-音乐", "魔流-CARPT-静默-资源"])
_qbc = _Qbc(_dl)
_dl.qbc = _qbc
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-CARPT-静默-资源"])
ok(_r is True, "返回 True")
ok(_dl.tags == ["魔流-CARPT-静默-资源"], f"标签真的删掉了（{_dl.tags}）")
ok(_qbc.calls and _qbc.calls[0][0] == H, "调了 torrents_remove_tags 且带对 hash")
ok(_qbc.calls[0][1] == ["魔流-CARPT-音乐"], "只传了差集，不误删别的标签")

# ---------------------------------------------------------------- [3] 两边都没有

print("\n[3] 适配器和 qbittorrentapi 都没有删除能力")
_dl = _Dl(["魔流-CARPT-音乐", "魔流-CARPT-静默-资源"])
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-CARPT-静默-资源"])
ok(_r is False, "★ 必须返回 False（旧实现假成功 → 每轮重复报摘）")
ok("魔流-CARPT-音乐" in _dl.tags, "标签保持原样（确实没删掉）")

# ---------------------------------------------------------------- [4] 调了但没删掉

print("\n[4] 调过删除但标签没变（写失败被吞）")
_dl = _Dl(["已整理", "魔流-CARPT-静默-资源"])
_dl.qbc = _Qbc(_dl, works=False)
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-CARPT-静默-资源"])
ok(_r is False, "回读校验抓出「说删了但还在」→ False")
ok("已整理" in _dl.tags, "标签仍在（与现场 291 次删不掉一致）")

# ---------------------------------------------------------------- [5] 只新增

print("\n[5] 只有新增、没有要删的")
_dl = _Dl(["魔流-财神-静默-资源"])
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-财神-静默-资源", "魔流-财神-保种"])
ok(_r is True, "无删除能力也返回 True（不需删）")
ok("魔流-财神-保种" in _dl.tags, "新标签加上了")

# ---------------------------------------------------------------- [6] 删 + 加

print("\n[6] 删除与新增同时发生")
_dl = _Dl(["魔流-财神-魔力", "魔流-财神-静默-资源"])
_dl.qbc = _Qbc(_dl)
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-财神-静默-资源", "魔流-财神-保种"])
ok(_r is True, "返回 True")
ok(sorted(_dl.tags) == sorted(["魔流-财神-静默-资源", "魔流-财神-保种"]),
   f"最终标签恰好等于目标集合（{sorted(_dl.tags)}）")

# ---------------------------------------------------------------- [7] 标签写关闭

print("\n[7] tags_enabled=False（纯账本模式）")
_dl = _Dl(["魔流-CARPT-音乐"])
_dl.qbc = _Qbc(_dl)
_a = _adapter(_dl)
_a.tags_enabled = False
ok(_a.replace_torrent_tags(H, ["魔流-CARPT-静默-资源"]) is False, "不写、返回 False")
ok(_dl.tags == ["魔流-CARPT-音乐"], "标签未变")

# ---------------------------------------------------------------- [8] 适配器假成功

print("\n[8] 适配器方法存在且返回成功，但标签没动 → 必须继续试原生路径")
_dl = _Dl(["魔流-CARPT-音乐", "魔流-CARPT-静默-资源"],
          has_adapter_remove=True, adapter_remove_silent=True)
_dl.qbc = _Qbc(_dl)
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-CARPT-静默-资源"])
ok(_r is True, "最终返回 True（原生路径真删掉了）")
ok(_dl.tags == ["魔流-CARPT-静默-资源"], f"标签真的删掉了（{_dl.tags}）")
ok(len(_dl.adapter_calls) == 1, "先试过适配器那条假成功的路")

# ---------------------------------------------------------------- [9] 脏标签

print("\n[9] 标签名自带空白（qB 服务端 trim 输入，永远删不掉）→ 不空转")
_dl = _Dl([" 魔流-CARPT-音乐", "魔流-CARPT-静默-资源"])
_qbc = _Qbc(_dl)
_dl.qbc = _qbc
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-CARPT-静默-资源"])
ok(_r is False, "返回 False（如实报告删不掉）")
ok(not _qbc.calls, "不再调 qB 删除接口（调了也是 200 空转）")
ok(" 魔流-CARPT-音乐" in _dl.tags, "脏标签仍在（服务端限制，非本插件能解）")

# 干净形态同时存在时，仍然照常去删（不能因为脏的就整体放弃）
print("\n[9b] 干净形态与脏形态并存 → 照常删干净的那个")
_dl = _Dl([" 魔流-CARPT-音乐", "魔流-CARPT-音乐", "魔流-CARPT-静默-资源"])
_dl.qbc = _Qbc(_dl)
_r = _adapter(_dl).replace_torrent_tags(H, ["魔流-CARPT-静默-资源"])
ok(_r is False, "脏形态删不掉 → False")
ok(" 魔流-CARPT-音乐" in _dl.tags and "魔流-CARPT-音乐" not in _dl.tags,
   "干净形态已删、脏形态残留")

# ---------------------------------------------------------------- 汇总

print(f"\n{'=' * 52}")
if _fails:
    print(f"FAIL · {len(_fails)}/{_n} 项不通过")
    for m in _fails:
        print("   -", m)
    sys.exit(1)
print(f"PASS · {_n}/{_n} 项全部通过")
sys.exit(0)
