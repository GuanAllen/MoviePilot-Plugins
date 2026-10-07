#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播行内操作（★ 15.5.0）离线回归 —— 真跑 features/ondemand.py，不需 MoviePilot / qB。

背景（Master 2026-10-07 16:16「没有操作按钮，而且历史和下载的在一起不能筛选，我不能把下载慢的去掉」）：
  点播清单行内要能操作：**暂停 / 继续 / 移除**。移除必须走**唯一删除闸门**
  （``DownloaderAdapter.delete_torrents``）——欠 H&R / 跨站来源份 / 已认领 / 手动保留 一律硬拦，
  **不绕过**（fail-closed）；被拦时如实回传 ``ok=false`` + ``blocked=true`` + 原因。

断言：
  [1] 参数校验：缺 hash / 未知 action / 不在 pending → ok=false；
  [2] pause → 调 pause_torrents，ok=true；
  [3] resume → 调 resume_torrents；
  [4] remove → 调 delete_torrents(delete_file=True) + 取消 pending 标记；
  [5] remove 被闸门拦（返回 0）→ ok=false + blocked=true + **不取消标记**（fail-closed）；
  [6] 下载器不可用 → ok=false，不误删；
  [7] 源码级护栏：remove 走 delete_torrents（唯一入口），不得直调底层 `_downloader.delete_torrents`。

用法：``python3 tools/test_ondemand_act.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_ondemand_act_test"


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
tags = _load(PKG + ".tags", "tags.py")

_app = types.ModuleType("app")
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = type("Response", (), {})
sys.modules.setdefault("app", _app)
sys.modules["app.schemas"] = _app_schemas
_rec = types.ModuleType(PKG + ".recommend")
_rec.recognize = lambda *a, **k: None
sys.modules[PKG + ".recommend"] = _rec
_site = types.ModuleType(PKG + ".sitestore")
_site.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
sys.modules[PKG + ".sitestore"] = _site
_load(PKG + ".persistence", "persistence.py")

ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")
OnDemandMixin = ondemand.OnDemandMixin

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


class FakeDl:
    def __init__(self, available=True, delete_result=(1, None)):
        self.is_available = available
        self._delete_result = delete_result
        self.calls = []

    def pause_torrents(self, hs):
        self.calls.append(("pause", list(hs)))
        return (len(hs), None)

    def resume_torrents(self, hs):
        self.calls.append(("resume", list(hs)))
        return (len(hs), None)

    def delete_torrents(self, hashes=None, delete_file=False, reason="", source=""):
        self.calls.append(("delete", list(hashes or []), delete_file, reason, source))
        return self._delete_result


class Fake(OnDemandMixin):
    def __init__(self, pend=None, dl=None):
        self._pend = dict(pend or {})
        self._dl = dl if dl is not None else FakeDl()
        self.unmarked = []
        self.logs = []

    def _ondemand_all(self):
        return dict(self._pend)

    def _get_downloader(self, name=""):
        return self._dl

    def _ondemand_unmark(self, h):
        self.unmarked.append(str(h))
        self._pend.pop(str(h), None)

    def _log(self, msg, level="info"):
        self.logs.append(msg)


H = "a" * 40
PEND = {H: {"title": "高达00", "site": "CARPT", "ts": 1.0}}

# ---------------------------------------------------------------- [1] 校验
print("[1] 参数校验")
f = Fake(pend=PEND)
ok(f._ondemand_act(hash="", action="pause").get("ok") is False, "缺 hash → ok=false")
ok(f._ondemand_act(hash=H, action="nope").get("ok") is False, "未知 action → ok=false")
ok(f._ondemand_act(hash="b" * 40, action="pause").get("ok") is False, "不在 pending → ok=false")

# ---------------------------------------------------------------- [2] pause
print("[2] pause")
f = Fake(pend=PEND)
r = f._ondemand_act(hash=H, action="pause")
ok(r.get("ok") is True and r.get("action") == "pause", "pause ok=true")
ok(f._dl.calls[0][0] == "pause", "调 pause_torrents")

# ---------------------------------------------------------------- [3] resume
print("[3] resume")
f = Fake(pend=PEND)
r = f._ondemand_act(hash=H, action="resume")
ok(r.get("ok") is True and f._dl.calls[0][0] == "resume", "resume → resume_torrents")

# ---------------------------------------------------------------- [4] remove
print("[4] remove（走唯一删除闸门，删文件，取消标记）")
f = Fake(pend=PEND)
r = f._ondemand_act(hash=H, action="remove")
ok(r.get("ok") is True and r.get("action") == "remove", "remove ok=true")
ca = f._dl.calls[0]
ok(ca[0] == "delete" and ca[1] == [H], "调 delete_torrents(hashes=[H])")
ok(ca[2] is True, "delete_file=True（删种+删文件）")
ok(f.unmarked == [H], "取消点播 pending 标记")
ok(H not in f._pend, "pending 已清")

# ---------------------------------------------------------------- [5] 被闸门拦
print("[5] remove 被闸门拦 → fail-closed（不取消标记）")
f = Fake(pend=PEND, dl=FakeDl(delete_result=(0, "欠 H&R 账单（直查 state=active·site=carpt.net）")))
r = f._ondemand_act(hash=H, action="remove")
ok(r.get("ok") is False and r.get("blocked") is True, "ok=false + blocked=true")
ok("H&R" in str(r.get("message")), f"回传原因（{r.get('message')}）")
ok(f.unmarked == [], "被拦时**不**取消标记")
ok(H in f._pend, "pending 保留")

# ---------------------------------------------------------------- [6] 下载器不可用
print("[6] 下载器不可用")
f = Fake(pend=PEND, dl=FakeDl(available=False))
r = f._ondemand_act(hash=H, action="remove")
ok(r.get("ok") is False and f._dl.calls == [], "不可用 → ok=false 且不动下载器")

# ---------------------------------------------------------------- [7] 源码护栏
print("[7] 源码护栏：remove 不绕过闸门")
src = (ROOT / "features" / "ondemand.py").read_text(encoding="utf-8")
seg = src.split("def _ondemand_act", 1)[1].split("\n    def ", 1)[0]
ok("dl.delete_torrents(" in seg, "走 DownloaderAdapter.delete_torrents")
ok("_downloader.delete_torrents" not in seg, "无底层 _downloader.delete_torrents 直调（不绕过闸门）")

print()
if FAILS:
    print(f"❌ FAIL：{len(FAILS)}/{N} 断言失败")
    for x in FAILS:
        print("   -", x)
    sys.exit(1)
print(f"✅ PASS：{N}/{N} 断言全过")
