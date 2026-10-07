#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 静默池「清理（删除）」离线回归（★ 13.0.1，真跑 silent.py，不需 MoviePilot）。

★ 13.0.1：撤掉 13.0.0 新造的 ``_silent_purge``（那是多余的第二套删除口径），
   本套测试改为直接测**原来的清除程序** ``_silent_purge_incomplete``（未下完直接删）
   —— 它是静默池唯一自动执行的「删除」步（``silent_host`` 每轮 ``_s1``），
   ``_silent_plain_sweep``（低效普通清扫）另见 ``test_silent_hr_split.py``。

★ 13.0.2（Master「统一成身份就好」）：静默池保护的判据**统一成身份**口径
   （`_silent_identity_ctx` / `_silent_identity_protected`：跨站来源账本 / 已认领 / 资源成员 /
   库内资源 / 同数据副本），**不再看 `魔流-跨站`/`魔流-辅种`/`已整理·辅种` 标签**。

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
import os
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


class _Groups:
    """资源账本桩：`items()`（gid → 资源记录）+ `group_of(hash)`。"""

    def __init__(self, items=None):
        self._items = dict(items or {})

    def items(self):
        return dict(self._items)

    def group_of(self, h):
        for gid, rec in self._items.items():
            if str(h or "").lower() in {str(k).lower() for k in (rec.get("members") or {})}:
                return gid
        return ""


class Harness(silent.SilentMixin):
    """在真 SilentMixin 上挂桩：真跑 `_silent_purge_incomplete` 的编排（分类输入可控）。"""

    def __init__(self, ledger, snap, groups=None, crossseed=None, claim=None):
        self.ledger = {str(k).lower(): dict(v or {}) for k, v in (ledger or {}).items()}
        self.torrents = {str(k).lower(): v for k, v in (snap or {}).items()}
        self.groups = groups
        self.cs_src = set(crossseed or ())
        self.claim = set(claim or ())
        self.delete_calls = []
        self.journal = None

    # ---- 身份真值源桩（★ 13.0.2：清理只在「身份」上判，不再看标签）----
    def _tag_groups(self):
        return self.groups

    def _crossseed_source_hashes(self):
        return set(self.cs_src)

    def _claim_protected_hashes(self):
        return set(self.claim)

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

    # ---- 入池即判 所需桩 ----
    def _hr_obligation(self, site, t, snap=None):
        return (bool(getattr(self, "hr_owed", False)), 0.0, 0.0, "test")

    def _torrent_site_name(self, tags, fallback=""):
        return fallback or "site"

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
SUB_PLAIN = tags.SUB_PLAIN
SUB_NEW = tags.SUB_NEW
SUB_RESOURCE = tags.SUB_RESOURCE


def _rec(**kw):
    d = {"state": SIL, "sub": SUB_PLAIN}
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

    # ---- ⑤ 身份保护（★ 13.0.2 统一口径）----
    print("\n[5] 身份保护：跨站来源账本 / 资源成员 / 库内资源 / 同数据副本 / 推荐在途 不删")
    h = Harness(
        {"s1": _rec(), "s2": _rec(), "s3": _rec(), "s4": _rec(in_library=True),
         "s5": _rec(), "s6": _rec()},
        {"s1": _torrent("s1", progress=0.4, title="cs", tags=["魔流-跨站"]),
         "s2": _torrent("s2", progress=0.4, title="mem", tags=["魔流-辅种"]),
         "s3": _torrent("s3", progress=0.4, title="copy", save="/lib"),
         "s4": _torrent("s4", progress=0.4, title="lib"),
         "s5": _torrent("s5", progress=0.4, title="rec", tags=["魔流-推荐"]),
         "s6": _torrent("s6", progress=0.4, title="bare")},
        groups=_Groups({"g1": {"library": {"in_library": True}, "members": {"s2": {}}}}),
        crossseed={"s1"},
    )
    # s3 与库内成员 s2 同一个 content_path → 同数据副本（副本跟随资源身份）
    h.torrents["s2"].content_path = "/lib/copy"
    rep = h._silent_purge_incomplete(apply=True)
    deleted = [x[0][0] for x in h.delete_calls]
    _ok(rep["pending"] == 1, f"只有 1 个进「未下完」范围（实测 {rep['pending']}）")
    _ok(deleted == ["s6"], f"只删 s6（无身份/无推荐）；实测删 {deleted}")
    _ok(h.delete_calls[0][1] is True, "s6 独享数据 → 删条目+删文件")
    _ok("s6" not in h.ledger and "s1" in h.ledger, "删成功的（s6）摘掉；被保护的（s1）保留")

    # ---- ⑥ 标签不再是判据（对照：只有标签、没有身份 → 不再豁免）----
    print("\n[6] ★ 标签判据已删：只有 `魔流-辅种`/`已整理` 标签、无身份 → 照删")
    h = Harness({"t9": _rec()},
                {"t9": _torrent("t9", progress=0.4, title="z", tags=["魔流-辅种", "已整理"])})
    rep = h._silent_purge_incomplete(apply=True)
    _ok(rep["pending"] == 1 and [x[0][0] for x in h.delete_calls] == ["t9"],
        "裸标签不再豁免（旧版按 MARK_REUSE/is_asset_tags 放行 —— 已统一成身份）")

    # ---- ⑦ 周期兜底：未下完的不分 sub 都删（身份保护者除外）----
    print("\n[7] 周期兜底：未下完的不分身份都删（「资源」等由**身份保护**挡住）")
    h = Harness({"n1": _rec(sub=SUB_NEW), "r1": _rec(sub=SUB_RESOURCE), "p1": _rec()},
                {"n1": _torrent("n1", progress=0.3, title="new"),
                 "r1": _torrent("r1", progress=0.3, title="res"),
                 "p1": _torrent("p1", progress=0.3, title="plain")})
    rep = h._silent_purge_incomplete(apply=True)
    _ok(sorted(x[0][0] for x in h.delete_calls) == ["n1", "p1"],
        "「新/普通」没下完都删（不限 sub）；「资源」被身份保护挡住（实测 "
        f"{sorted(x[0][0] for x in h.delete_calls)}）")

    # ---- ⑧ 已完成种不在范围 ----
    print("\n[8] 已完成种（progress≈1 且非 DL 态）不在「未下完」范围")
    h = Harness({"d1": _rec()}, {"d1": _torrent("d1", progress=1.0, state="pausedUP", title="done")})
    rep = h._silent_purge_incomplete(apply=True)
    _ok(rep["pending"] == 0 and h.delete_calls == [], "已完成且非 DL → 不处理（归 plain_sweep/分拣管）")

    # ---- ⑧ 身份口径助手自检 ----
    print("\n[9] `_silent_identity_ctx` 口径自检")
    h = Harness({"a": _rec(in_library=True), "b": _rec()},
                {"a": _torrent("a", title="A"), "b": _torrent("b", title="B")},
                groups=_Groups({"g1": {"identity": "资源", "members": {"b": {}}}}),
                crossseed={"c1"}, claim={"c2"})
    ctx = h._silent_identity_ctx(h.torrents)
    _ok({"a", "b"} <= ctx["members"] or {"b"} <= ctx["members"],
        "资源成员（identity=资源）进 members")
    _ok(ctx["crossseed"] == {"c1"} and ctx["claim"] == {"c2"}, "跨站来源/已认领 真值源透传")
    _ok("/x/A" in ctx["asset_keys"] and "/x/B" in ctx["asset_keys"],
        "库内/成员份的 content_path 进 asset_keys（同数据副本判据）")

    # ---- ⑩ 入池即判（Master 01:30）----
    print("\n[10] 入池即判 `_silent_drop_incomplete_now`：没下完的刚入池就删")
    h = Harness({"i1": _rec(sub=SUB_NEW)}, {"i1": _torrent("i1", progress=0.3, title="inc")})
    _ok(h._silent_drop_incomplete_now("i1") is True
        and [x[0][0] for x in h.delete_calls] == ["i1"] and h.delete_calls[0][1] is True,
        "没下完的「新」当场删（删条目+删文件）")
    h = Harness({"i2": _rec(sub=SUB_NEW)}, {"i2": _torrent("i2", progress=1.0, state="pausedUP", title="ok")})
    _ok(h._silent_drop_incomplete_now("i2") is False and not h.delete_calls, "已完成的入池不动")
    h = Harness({"i3": _rec(sub=SUB_NEW)}, {"i3": _torrent("i3", progress=0.4, title="cs")},
                crossseed={"i3"})
    _ok(h._silent_drop_incomplete_now("i3") is False, "身份保护（跨站来源）→ 不删")
    h = Harness({"i4": _rec(sub=SUB_NEW), "j4": _rec()},
                {"i4": _torrent("i4", progress=0.4, title="cp"),
                 "j4": _torrent("j4", progress=1.0, state="pausedUP", title="cp")})
    _ok(h._silent_drop_incomplete_now("i4") is False, "同数据另有种（辅种副本等校验）→ 不删")
    h = Harness({"i5": _rec(sub=SUB_NEW)}, {"i5": _torrent("i5", progress=0.4, title="hr")})
    h.hr_owed = True
    _ok(h._silent_drop_incomplete_now("i5") is False, "欠 H&R（保种义务）→ 不删")
    h = Harness({"i6": _rec(sub=SUB_NEW, manual_paused=True)}, {"i6": _torrent("i6", progress=0.4, title="m")})
    _ok(h._silent_drop_incomplete_now("i6") is False, "手动保护 → 不删")

    # ---- ⑪ 源码级护栏：入池前先过 H&R 分诊 + 入池即判钩子在位 ----
    print("\n[11] 源码级护栏：所有入池口都先过 H&R 分诊；未下完的入池即判")
    import re as _re
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _src = lambda f: open(os.path.join(_root, "features", f), encoding="utf-8").read()
    _tags, _tasks, _sil = _src("tags.py"), _src("tasks.py"), _src("silent.py")
    _settle = _tasks[_tasks.index("def _tag_settle_idle"):]
    _settle = _settle[:_settle.index("def ", 10)]
    _ok("_split_release(" in _settle and "_tag_release(" not in _settle,
        "`_tag_settle_idle`（停止旁路/删任务退回静默）走 `_split_release` 先过 H&R 分诊")
    _rel = _tags[_tags.index("def _tag_release"):]
    _rel = _rel[:_rel.index("def ", 10)]
    _ok("_silent_drop_incomplete_now(" in _rel, "`_tag_release`（退回静默=入池）挂入池即判")
    _asm = _tags[_tags.index("def _tag_assign"):]
    _asm = _asm[:_asm.index("def ", 10)]
    _ok("_silent_drop_incomplete_now(" in _asm, "`_tag_assign`（归入静默）挂入池即判")
    _pc = _sil[(_sil.index("def _silent_purge_incomplete")):]
    _pc = _pc[:_pc.index("\n    def ", 10)]
    _ok("SUB_PLAIN" not in _pc, "`_silent_purge_incomplete` 不再有 sub=普通 限定（未下完不分身份都删）")
    _ok("_silent_identity_protected(" in _pc, "周期兜底仍走身份保护（不再用标签判据）")

    print("\n[12] 源码级护栏：14.0.0 收线 / 判据同源 / 全局真任务")
    _hr = _src("hr.py")
    _common = open(os.path.join(_root, "common.py"), encoding="utf-8").read()
    _cs = _src("crossseed.py")
    _sr = _src("sitereport.py")
    _reg = _src("registry.py")
    _ob = _hr[_hr.index("def _hr_obligation"):]
    _ob = _ob[:_ob.index("\n    def ", 10)]
    _ok("_hr_due_hours(" in _ob,
        "`_hr_obligation` 与账单同源：用 `_hr_due_hours`（need+margin）而非裸 need_h")
    _ok("def _hr_due_hours" in _hr and "_hr_margin_hours(" in _hr.split("def _hr_due_hours", 1)[1][:900],
        "`_hr_due_hours` = need + margin（唯一口径）")
    _ok("duty_of(" in _sr and "identity_of(" in _sr and "STATE_HR" in _sr,
        "站点报表两轴分级 = 职务轴 duty_of + 身份轴 identity_of（sitereport）")
    _ok('"stage"' not in _sil and "pool_cleanup" not in _sil,
        "静默盘点已去观测残留（无 stage / pool_cleanup）")
    _ok('"relocate"' not in _sil and '"cleanup"' in _sil,
        "清理候选分类改名 relocate → cleanup")
    _ok("CROSSSEED_TASK_ID" in _common and "CROSSSEED_PV_DAILY_CAP_DEFAULT" in _common,
        "全局真任务「跨站取种」常量 + 单站 PV 上限已入 common")
    _ok("def _crossseed_tick" in _cs and "def crossseed_scan" not in _cs,
        "跨站线：worker `crossseed_scan` 已删，改 `_crossseed_tick`（全局任务 Check）")
    _ok("CROSSSEED_TASK_ID" in _reg,
        "registry 特性开关把全局「跨站取种」任务算作启用中")

    print("\n" + "=" * 64)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
