#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 标签**卫生**契约（下发前必须拆成干净 list）离线回归。

背景（2026-10-30）：qB 里存在 21 个种带着 ``␠魔流-CARPT-音乐`` 这种**前导空格**的
脏标签（最久的挂了 22 天）。溯源并实测确认：

  * ``torrents/add`` 的 ``tags`` 参数**只按 ``,`` 拆、不 trim**
    —— 实测注入 ``"ZZPROBE-AAA, ZZPROBE-BBB"``，新种 tags 变成
    ``' ZZPROBE-BBB, ZZPROBE-AAA'``（第二个带前导空格）；
  * 而 ``torrents/addTags`` 会 trim（实测 ``" ZZSP"`` → ``ZZSP``）。两个接口行为不一致；
  * 于是 qB 4.6.4 的 ``removeTags`` / ``deleteTags``（都先 trim 入参）此后**永远删不掉**
    那个脏标签 —— 返回 200、什么都不做。

插件侧的源头：``tags.py`` 的媒体加种用 ``", ".join([静默-资源, 职务])`` 拼成一个**字符串**
（逗号后带空格），一路传到 ``downloader_ops._add_torrent_qbittorrent``，那里又把它当成
**单个标签**（``[tag]``）下发 —— qB 拆开后第二个就脏了。这也解释了为什么脏标签清一色是
「音乐 / 点播 / 魔力」（= 第二个元素 state），而「静默-资源」（第一个元素）从来没脏过。

本文件钉住的契约：
  [1] ``_split_tags`` 把 ", " / "," / list 一律规整为无空白 list；
  [2] ``add_torrent``（magnet 分支）下发给下载器的是**拆好的 list**，不是整串；
  [3] 按 qB 的真实解析方式复算一遍（``",".join`` → ``split(",")``）→ **零前导空格**；
  [4] 单个标签的行为不变（不因为改造而丢掉标签）；
  [5] 无标签 / 空串 → 空 list（不产生空标签）；
  [6] ``add_torrent_reuse`` 同样拆开，且「辅种」标记仍然保留。

用法：``python3 tools/test_tag_hygiene.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_taghygiene_test"

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
dlops = _load(PKG + ".downloader_ops", "downloader_ops.py")

DownloaderAdapter = dlops.DownloaderAdapter
_split_tags = dlops._split_tags

H = "b" * 40
MAGNET = "magnet:?xt=urn:btih:" + H + "&dn=probe"

# 现场同形：第一个是「静默-资源」，第二个是「职务」（旧代码 ", ".join 的产物）
DIRTY_ARG = "魔流-CARPT-静默-资源, 魔流-CARPT-音乐"
WANT = ["魔流-CARPT-静默-资源", "魔流-CARPT-音乐"]


def _qb_parse(names) -> list:
    """完全复刻 qB 的解析：接收逗号串，只按 ``,`` 拆，**不 trim**。"""
    joined = ",".join(names)
    return [x for x in joined.split(",") if x]


def _dirty(names) -> list:
    return [x for x in _qb_parse(names) if x != x.strip()]


class _AddDl:
    """MP 的 Qbittorrent 适配器桩：只记录 add_torrent 收到的 tag。"""

    def __init__(self):
        self.calls: list = []

    def add_torrent(self, content=None, download_dir=None, category=None, tag=None,
                    upload_limit=None, download_limit=None, **kw):
        self.calls.append(tag)
        return True, [H]

    def get_torrents(self, ids=None, tags=None):
        return [], None


def _adapter(dl) -> object:
    a = object.__new__(DownloaderAdapter)
    a.downloader_name = "qbittorrent"
    a._downloader = dl
    a._service = None
    a.tags_enabled = True
    return a


# ---------------------------------------------------------------- [1] _split_tags

print("\n[1] _split_tags 规整")
ok(_split_tags(DIRTY_ARG) == WANT, f"『, 』拼串 → 无空白 list（{_split_tags(DIRTY_ARG)}）")
ok(_split_tags("魔流-A,魔流-B") == ["魔流-A", "魔流-B"], "『,』无空格也正确")
ok(_split_tags([" 魔流-A ", "魔流-B"]) == ["魔流-A", "魔流-B"], "list 里的空白也被剥掉")
ok(_split_tags("  ") == [], "纯空白 → 空 list")
ok(_split_tags(None) == [], "None → 空 list")

# ---------------------------------------------------------------- [2] 下发形态

print("\n[2] add_torrent（magnet）下发给下载器的是拆好的 list")
_dl = _AddDl()
_a = _adapter(_dl)
_h, _err = _a.add_torrent(content=MAGNET, download_dir="/tmp/x", tag=DIRTY_ARG)
ok(_err is None and _h == H, "加种成功")
ok(len(_dl.calls) == 1, "调了一次 add_torrent")
ok(_dl.calls[0] == WANT, f"★ 传的是 list 而非整串（{_dl.calls[0]}）")
ok(_dirty(_dl.calls[0]) == [], f"★ 按 qB 解析方式复算 → 零脏标签（{_dirty(_dl.calls[0])}）")

# ---------------------------------------------------------------- [3] 对照：旧写法必然脏

print("\n[3] 对照实验：旧写法（整串当单元素）在 qB 侧必然产生脏标签")
_old = [_split_tags(DIRTY_ARG) and DIRTY_ARG]      # 旧实现 `[tag] if tag else []`
ok(_dirty(_old) == [" 魔流-CARPT-音乐"],
   f"旧写法 → {_dirty(_old)}（与现场 qB 数据逐字节一致，故必须改）")

# ---------------------------------------------------------------- [4] 单个标签不变

print("\n[4] 单个标签行为不变")
_dl = _AddDl()
_adapter(_dl).add_torrent(content=MAGNET, download_dir="/tmp/x", tag="魔流-财神-静默-资源")
ok(_dl.calls[0] == ["魔流-财神-静默-资源"], "单标签仍是单元素 list")

# ---------------------------------------------------------------- [5] 无标签

print("\n[5] 无标签 / 空串")
for _case, _label in ((None, "None"), ("", "空串"), ("   ", "纯空白")):
    _dl = _AddDl()
    _adapter(_dl).add_torrent(content=MAGNET, download_dir="/tmp/x", tag=_case)
    ok(_dl.calls[0] == [], f"{_label} → 空 list（不产生空标签）")

# ---------------------------------------------------------------- [6] 辅种路径

print("\n[6] add_torrent_reuse 也拆开，且保留「辅种」标记")
_source = (ROOT / "downloader_ops.py").read_text(encoding="utf-8")
_reuse = _source.split("def add_torrent_reuse", 1)[1].split("def add_torrent(", 1)[0]
ok("tag_list = _split_tags(tag)" in _reuse,
   "★ 构造处用 _split_tags(tag)（旧写法 [tag] 会把整串当单元素）")
ok("[tag] if tag else" not in _reuse, "不再出现 `[tag] if tag else`")
ok("if REUSE_MARK not in tag_list" in _reuse, "「辅种」标记逻辑保留")

# ---------------------------------------------------------------- [7] 源头不再拼空格

print("\n[7] tags.py 的媒体加种源头")
_tags_src = (ROOT / "tags.py").read_text(encoding="utf-8")
ok('", ".join([tag_for(site_name' not in _tags_src,
   "★ 不再用 『, 』拼两个标签（这是脏标签的产地）")
ok('",".join([tag_for(site_name' in _tags_src, "改用『,』无空格拼接")

# ---------------------------------------------------------------- 汇总

print("\n" + "=" * 56)
if _fails:
    print(f"❌ FAIL —— {len(_fails)} / {_n} 项未通过")
    for f in _fails:
        print("   -", f)
    sys.exit(1)
print(f"✅ PASS —— {_n} / {_n} 项全通过")
