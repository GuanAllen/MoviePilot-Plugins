#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 静默不变量收敛（★ 12.7.1 / 15.1.0）离线回归 —— 真跑 silent.py，不需 MoviePilot。

背景（Master 2026-10-06 22:53「之前设计怎么做的呀」）：
  设计口径（11.11.0）「**静默池本意就是暂停不上传**」→ 任何 ``state=静默`` 的种一律 pause；
  「库内资产」只保证**永不删**（删除闸门第 5 类硬拦），**不保证在做种**。
  但 ``_silent_pause_gate`` 只在**写状态那一刻**调用，「补 pause」又只在手动阶段 2 迁出时
  **按 sub 过滤**顺带做 → 存量违背无人收敛（实测 36 个：35 stalledUP + 1 uploading，
  全是 sub=资源/新）。本测试锁死修复：

  1) ``_silent_enforce_pause(apply=False)``：只报违背数，**零写入**；
  2) ``apply=True``：**全部**违背（不分 sub/site）都补 pause，且**只 pause**（无 delete/resume）；
  3) 幂等：pause 后再跑，违背 0、paused 0；
  4) ``_silent_purge`` 步骤① 改为**全局**收敛 —— 即使 ``sub=普通``，``资源`` 的违背也会被 pause；
  5) ``silent_host`` 挂上「⑪不变量收敛」步（源码级冒烟）。

用法：``python3 tools/test_silent_enforce_pause.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_enforce_pause_test"


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

for _modname, _attrs in (("bonus", ("calc_bonus_per_hour", "TorrentBonusInfo")),
                         ("fetcher", ("SiteCandidateTorrent",))):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    sys.modules[PKG + "." + _modname] = _m

_load(PKG + ".fingerprint", "fingerprint.py")
_load(PKG + ".persistence", "persistence.py")
_load(PKG + ".tags", "tags.py")
common = _load(PKG + ".common", "common.py")
_load(PKG + ".downloader_ops", "downloader_ops.py")
silent = _load(PKG + ".features.silent", "features/silent.py")

STATE_SILENT = "静默"
SUB_NEW = "新"
SUB_RESOURCE = "资源"

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _torrent(h, state="pausedUP", size=1 << 30, tags=None):
    return types.SimpleNamespace(hash=h, title=h[:8], state=state, size=size,
                                 tags=list(tags or []), progress=1.0,
                                 save_path="/x", content_path=f"/x/{h}")


class _Ledger:
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


class _DL:
    """下载器桩：pause 会**真的**改 qB 态（这样幂等可测），delete 只记账。"""

    def __init__(self, h):
        self.h = h

    def pause_torrents(self, hs):
        hs = [hs] if isinstance(hs, str) else list(hs or [])
        self.h.pause_calls.extend(hs)
        for x in hs:
            t = self.h.torrents.get(str(x).lower())
            if t is not None:
                t.state = "pausedUP"
        return len(hs), None

    def delete_torrents(self, hashes, delete_file=False, reason="", source=""):
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        self.h.delete_calls.append((list(hs), bool(delete_file)))
        return len(hs), None


class Harness(silent.SilentMixin):
    """真 SilentMixin + 桩依赖：``_silent_audit``/``_silent_pause_gate`` 走**真实现**。"""

    def __init__(self, ledger, snap):
        self._ledger = ledger
        self.torrents = dict(snap or {})
        self.pause_calls = []
        self.delete_calls = []
        self._tags_cfg = {"host_interval": 60}

    # —— 真值输入 ——
    def _tag_state(self):
        return _Ledger(self._ledger)

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _crossseed_source_hashes(self):
        return set()

    def _claim_protected_hashes(self):
        return set()

    def _hr_obligation(self, site, torrent, snap=None):
        return (False, 24.0, 100.0, "test")

    def _torrent_site_name(self, tags, fallback=""):
        return "站点A"

    def _tourn_scan_noop(self):  # pragma: no cover
        return None

    def _get_downloader(self, name="qbittorrent"):
        return _DL(self)

    # —— 噪声抑制 ——
    def _log(self, msg, level=None):
        pass

    def get_data_path(self):
        return ROOT

    def _deletions_log_path(self):
        return ROOT / "deletions.jsonl"

    def _journal_deletions(self, by_task, log_prefix=""):
        self.journal = by_task

    def _delete_gate_detail(self, hashes, force_error=None, snap=None):
        return {}


def _mk(spec):
    """spec: list of (hash, state, sub, in_library)"""
    led, snap = {}, {}
    for h, st, sub, inlib in spec:
        led[h] = {"state": STATE_SILENT, "sub": sub, "site": "站点A",
                  "in_library": bool(inlib), "size_gb": 1.0, "taken_by": "__silent_host__"}
        snap[h] = _torrent(h, state=st)
    return led, snap


SPEC = [
    ("a" * 40, "stalledUP", SUB_RESOURCE, True),   # 库内资产，停滞（12.7.1 前漏检）
    ("b" * 40, "uploading", SUB_RESOURCE, True),   # 库内资产，真在上传（12.7.1 前漏检）
    ("c" * 40, "stalledUP", SUB_NEW, False),       # 迁出候选，停滞
    ("d" * 40, "pausedUP", SUB_RESOURCE, True),    # 合规
    ("e" * 40, "pausedUP", SUB_NEW, False),        # 合规
]


def t1_dry_run():
    print("① 干跑（apply=False）：只报违背，零写入")
    led, snap = _mk(SPEC)
    h = Harness(led, snap)
    rep = h._silent_enforce_pause(apply=False)
    _ok(rep["violations"] == 3, f"违背不变量 3 个（实测 {rep['violations']}）")
    _ok(rep["paused"] == 0 and not h.pause_calls, "干跑零写入（下载器无 pause 调用）")
    _ok(not h.delete_calls, "干跑无删除")
    return h


def t2_apply_all_subs():
    print("② apply=True：违背全部补 pause（不分 sub），只 pause 不删")
    led, snap = _mk(SPEC)
    h = Harness(led, snap)
    rep = h._silent_enforce_pause(apply=True)
    _ok(rep["paused"] == 3, f"补 pause 3 个（实测 {rep['paused']}）")
    _ok(set(h.pause_calls) == {"a" * 40, "b" * 40, "c" * 40}, "恰恰是那 3 个违背项（含 资源/新）")
    _ok(all(snap[x].state == "pausedUP" for x in h.pause_calls), "qB 侧已变 pausedUP")
    _ok(not h.delete_calls, "**没有删除**（只 pause）")
    # 复跑 = 幂等
    rep2 = h._silent_enforce_pause(apply=True)
    _ok(rep2["violations"] == 0 and rep2["paused"] == 0, "幂等：再跑违背 0、paused 0")
    return h


def t3_purge_removed():
    print("③ 13.0.1：purge 已撤除（源码级护栏 —— 防再引入「第二套删除口径」）")
    _s = (ROOT / "features/silent.py").read_text(encoding="utf-8")
    _ok("def _silent_purge(" not in _s, "silent.py 无 _silent_purge 方法")
    _ok("def silent_purge(" not in _s, "silent.py 无 silent_purge UI handler")
    _a = (ROOT / "features/agentapi.py").read_text(encoding="utf-8")
    _ok('"/agent/silent/purge"' not in _a, "AI 清单无 /agent/silent/purge（清单 50→49）")
    _b = (ROOT / "features/api.py").read_text(encoding="utf-8")
    _ok('"/silent/purge"' not in _b, "UI 路由无 /silent/purge")
    _v = (ROOT / "src/components/MagicFlowWorkbench.vue").read_text(encoding="utf-8")
    _ok("silent/purge" not in _v, "前端无 silent/purge 调用")
    return None


def t4_disabled_switch():
    print("④ 回退开关 SILENT_HR_SPLIT_ENABLED=False → 直接跳过（disabled）")
    led, snap = _mk(SPEC)
    h = Harness(led, snap)
    _old = silent.SILENT_HR_SPLIT_ENABLED
    try:
        silent.SILENT_HR_SPLIT_ENABLED = False
        rep = h._silent_enforce_pause(apply=True)
    finally:
        silent.SILENT_HR_SPLIT_ENABLED = _old
    _ok(bool(rep.get("disabled")) and not h.pause_calls, "关闭时零写入、报 disabled")
    return h


def t5_host_wiring():
    print("⑤ silent_host 挂上「⑪不变量收敛」步（源码级冒烟）")
    src = (ROOT / "features/silent.py").read_text(encoding="utf-8")
    _ok('_step("pause", "⑪不变量收敛", _s11)' in src, "silent_host 注册第 ⑪ 步")
    _ok("i = self._silent_enforce_pause(apply=True)" in src, "该步调 _silent_enforce_pause(apply=True)")
    _ok("自愈" in src or "周期收敛" in src, "docstring 标明是周期收敛/自愈")


class _HarnessHr(Harness):
    """欠 H&R 的（hash 前缀 h）→ fail-safe：标签面也不许判违背。"""

    def _hr_obligation(self, site, torrent, snap=None):
        hh = str(getattr(torrent, "hash", "") or "").lower()
        if hh.startswith("h"):
            return (True, 24.0, 100.0, "test:hr")
        return (False, 24.0, 100.0, "test")


def t6_tag_only_reconcile():
    print("⑥ 15.1.0 对账：只打「静默」标签、不在账本的种也纳入收敛（不漏、欠 H&R 不误伤）")
    h_led, h_snap = _mk(SPEC)          # 账本面：3 个违背（a/b/c）
    # 标签面：f 在做种（该补 pause）；g 已暂停（合规）；h 在做种但欠 H&R（不许动）
    h_snap["f" * 40] = _torrent("f" * 40, state="uploading", tags=["魔流-站点A-静默-普通"])
    h_snap["g" * 40] = _torrent("g" * 40, state="pausedUP", tags=["魔流-站点A-静默-资源"])
    h_snap["h" * 40] = _torrent("h" * 40, state="stalledUP", tags=["魔流-站点A-静默-新"])
    # ★ 身份轴是**永久**的：在岗种（职务=魔力）也带「静默-身份」标签 → **绝不能**当静默种 pause
    h_snap["k" * 40] = _torrent("k" * 40, state="uploading",
                                tags=["魔流-站点A-静默-资源", "魔流-站点A-魔力"])
    h_snap["m" * 40] = _torrent("m" * 40, state="stalledUP",
                                tags=["魔流-站点A-静默-普通", "魔流-站点A-刷流"])
    h_snap["n" * 40] = _torrent("n" * 40, state="uploading",
                                tags=["魔流-站点A-静默-普通", "魔流-推荐"])
    h = _HarnessHr(h_led, h_snap)
    dry = h._silent_enforce_pause(apply=False)
    _ok(dry["tag_only"] == 3, f"标签面识别 3 个（仅无职务身份的，实测 {dry['tag_only']}）")
    _ok(dry["violations"] == 4, f"违背 = 账本 3 + 标签面 1（实测 {dry['violations']}）")
    _ok(dry["scanned"] == 8, f"盘点总数含标签面 5+3（实测 {dry['scanned']}）")
    _ok("k" * 40 not in (dry.get("items") or []) and "m" * 40 not in (dry.get("items") or []),
        "在岗（有职务）的**不入标签面**（防误 pause 在岗种）")
    rep = h._silent_enforce_pause(apply=True)
    _ok(rep["paused"] == 4, f"补 pause 4 个（实测 {rep['paused']}）")
    _ok("f" * 40 in h.pause_calls and "h" * 40 not in h.pause_calls,
        "做种的辅种副本被补 pause；欠 H&R 的**没动**（fail-safe）")
    _ok("k" * 40 not in h.pause_calls and "m" * 40 not in h.pause_calls
        and "n" * 40 not in h.pause_calls,
        "在岗（魔力/刷流）与推荐的**一律没动**")
    _ok("g" * 40 not in h.pause_calls, "已暂停的不重复写")
    _ok(not h.delete_calls, "只 pause 不删")
    rep2 = h._silent_enforce_pause(apply=True)
    _ok(rep2["violations"] == 0 and rep2["paused"] == 0, "幂等：再跑违背 0、paused 0")


def main():
    t1_dry_run()
    t2_apply_all_subs()
    t3_purge_removed()
    t4_disabled_switch()
    t5_host_wiring()
    t6_tag_only_reconcile()
    print(f"\n✅ PASS —— 静默不变量收敛：{CHECKS} 条断言全过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\n❌ FAIL —— {e}")
        sys.exit(1)
