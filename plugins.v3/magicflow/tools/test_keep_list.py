#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 「手动保种」名单接口离线回归（★ 19.10.41，真跑 features/tags.py）。

背景：手动保种落的是 ``taken_by=__keep__`` 伪任务 —— 它**不是真任务**，所以这批种
既不在任何任务的种子池里、也不进 ``status.tasks``。挂上之后就「界面上哪儿都看不见」，
只能自己记 hash 才能解除（2026-10-30 实测存量 18 个）。``action=hold_list`` 就是给
前端「手动保种」列表用的只读名单。

本文件钉住的契约：
  A. **只挑 ``taken_by=__keep__``** —— 刷流/魔力/静默/H&R 的种一个都不能混进来；
  B. **异常优先排序**：不在下载器（幽灵行）→ 没在做种 → 正常做种，组内体积降序；
     （打开列表第一屏就该是「该处理的」，而不是按 hash 随机）
  C. ``seeding`` 判定 = 在下载器 + ``progress>=0.999`` + 状态在上传侧；
     ``stalledUP`` 算（有人在连、只是暂没流量），``pausedUP`` / 没下完 都不算；
  D. ``site`` / ``size_gb`` 在账本缺字段时能回退（站点名从标签反推、体积从实况取）；
  E. **纯只读** —— 不 put / 不 claim / 不 release / 不改 qB 标签。

用法：``python3 tools/test_keep_list.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_keep_list_test"

CHECKS = 0


def _ok(cond, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


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


class _Resp:
    """``app.schemas.Response`` 桩：只记 kwargs，字段名与真 Response 一致。"""

    def __init__(self, success=True, message="", data=None, **kw):
        self.success = success
        self.message = message
        self.data = data


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

for _name, _attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": _Resp}),
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
                         ("fetcher", ("SiteCandidateTorrent",)),
                         ("fingerprint", ("Entry", "entries_fingerprint", "info_hash", "load_torrent_entries",
                                          "total_size", "inner_fingerprint", "fingerprint")),
                         ("qbsync", ("QB_SYNC_INCREMENTAL", "get_qb_sync_store"))):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    _m.get_qb_sync_store = lambda: None  # noqa: E731
    sys.modules[PKG + "." + _modname] = _m

_m = types.ModuleType(PKG + ".models")
_m.MagicFlowAssetActPayload = object
_m.MagicFlowAssetDeletePayload = object
_m.MagicFlowTagStatePayload = object
sys.modules[PKG + ".models"] = _m
_m = types.ModuleType(PKG + ".persistence")
_m.OperationItem = object
sys.modules[PKG + ".persistence"] = _m
_m = types.ModuleType(PKG + ".ledger")
_m.get_backend = lambda: None  # noqa: E731
_m.ResourceLedgerStore = object
_m.SeedLedgerStore = object
sys.modules[PKG + ".ledger"] = _m
_m = types.ModuleType(PKG + ".recommend")
_m.episode_info = lambda *a, **k: None  # noqa: E731
_m.recognize = lambda *a, **k: None  # noqa: E731
sys.modules[PKG + ".recommend"] = _m

tagmod = _load(PKG + ".tags", "tags.py")
common = _load(PKG + ".common", "common.py")
feature_tags = _load(PKG + ".features.tags", "features/tags.py")

STATE_BRUSH = tagmod.STATE_BRUSH
STATE_BONUS = tagmod.STATE_BONUS
STATE_SILENT = tagmod.STATE_SILENT
STATE_KEEP = tagmod.STATE_HR   # 手动保种账面 state="保种"（与 __hr_host__ 同轴，靠 taken_by 区分）
tag_for = tagmod.tag_for
KEEP_TASK_ID = common.KEEP_TASK_ID

SITE = "YemaPT"
KEEP_TAG = tag_for(SITE, STATE_KEEP)

print("魔流 · 手动保种名单回归（★ 19.10.41）")
print(f"\n[0] 常量：KEEP_TASK_ID={KEEP_TASK_ID!r} · STATE_KEEP={STATE_KEEP!r}")


class _Store:
    """只读账本桩：**故意不实现 put/claim/release** —— 名单接口一旦写账本就 AttributeError。"""

    def __init__(self, d):
        self._d = {k: dict(v) for k, v in (d or {}).items()}

    def items(self):
        return {k: dict(v) for k, v in self._d.items()}

    def get(self, h):
        return dict(self._d.get(str(h or "").lower()) or {})


class _DL:
    """下载器桩：只读路径不该碰它，碰了就记下来。"""

    def __init__(self):
        self.is_available = True
        self.writes = []

    def replace_torrent_tags(self, h, tags):
        self.writes.append((str(h or "").lower(), list(tags)))
        return True

    def set_torrent_tags(self, h, tags):
        return self.replace_torrent_tags(h, tags)


class _Fake(feature_tags.TagsMixin):
    def __init__(self, snap, ledger, dl=None):
        self._snap = snap
        self._store = _Store(ledger)
        self._dl = dl or _DL()
        self.dbg = []
        self._task_configs = {}

    def _list_sites(self):
        return [{"name": SITE}]

    def _tag_all_torrents(self):
        return self._snap

    def _tag_state(self):
        return self._store

    def _get_downloader(self, name=""):
        return self._dl

    def _log(self, msg, level="info"):
        self.dbg.append(("log", level, msg))

    def _dbg(self, msg):
        self.dbg.append(("dbg", "debug", msg))


def _t(h, tags_list, *, state="stalledUP", progress=1.0, size_gb=1.0):
    return types.SimpleNamespace(
        hash=h, title=f"T-{h[:4]}", state=state, tags=list(tags_list),
        size=1 << 30, size_gb=size_gb, progress=progress, category="", save_path="/media",
    )


def _req(limit=""):
    """TagReq 桩：``_tag_act_hold_list`` 只读 ``req.limit``。"""
    return types.SimpleNamespace(act="hold_list", limit=limit, hash="", state="",
                                 site="", confirm="", reason="", tids="",
                                 adopt_reseed="", store=None, groups=None)


H_A = "a71de8a45d2783e944d563cb4f89bcdcc1368649"   # 正常做种
H_B = "b4d55c2434515ac98eb451fa24c3dcfe4f6f9af2"   # pausedUP（没在做种）
H_C = "c60839e4ffd1146a47a0f3f7b59000f39798e4d4"   # 不在下载器（幽灵行）
H_D = "dc00e81f025d2b0f9623873dbc333908a29cc392"   # pausedDL（没下完）
H_E = "e5b0d0e3f5c9de2e3e9bd9a1e0a5e6f00d1c2b3a"   # 别人名下的刷流种（不该进名单）
H_F = "f6c1e1f4a6daea8f4f0a0e4b1b7e5a011234abcd"   # 静默池种（不该进名单）

LEDGER = {
    H_A: {"site": SITE, "state": STATE_KEEP, "sub": "资源", "taken_by": KEEP_TASK_ID,
          "task": "手动保种", "size_gb": 12.5},
    H_B: {"site": SITE, "state": STATE_KEEP, "sub": "资源", "taken_by": KEEP_TASK_ID,
          "task": "手动保种", "size_gb": 30.0},
    H_C: {"site": SITE, "state": STATE_KEEP, "sub": "资源", "taken_by": KEEP_TASK_ID,
          "task": "手动保种", "size_gb": 8.0},
    H_D: {"site": SITE, "state": STATE_KEEP, "sub": "资源", "taken_by": KEEP_TASK_ID,
          "task": "手动保种", "size_gb": 50.0},
    H_E: {"site": SITE, "state": STATE_BRUSH, "sub": "资源", "taken_by": "f9fbf57ab9ce",
          "task": "YemaPT·刷流"},
    H_F: {"site": SITE, "state": STATE_SILENT, "sub": "资源"},
}
SNAP = {
    H_A: _t(H_A, [KEEP_TAG], state="uploading", size_gb=12.5),
    H_B: _t(H_B, [KEEP_TAG], state="pausedUP", size_gb=30.0),
    H_D: _t(H_D, [KEEP_TAG], state="pausedDL", progress=0.42, size_gb=50.0),
    H_E: _t(H_E, [tag_for(SITE, STATE_BRUSH)], size_gb=3.0),
    H_F: _t(H_F, [tag_for(SITE, STATE_SILENT, "资源")], size_gb=4.0),
}

# =====================================================================
# [A] 只挑 taken_by=__keep__
# =====================================================================
print("\n[A] 只挑 taken_by=__keep__，别的岗位一个都不混进来")
host = _Fake(SNAP, LEDGER)
resp = host._tag_act_hold_list(_req())
rows = resp.data["items"]
hs = [r["hash"] for r in rows]
_ok(resp.success is True, "success=True")
_ok(len(rows) == 4, f"名单 4 个（账本 6 个里 2 个非保种；实得 {len(rows)}）")
_ok(H_E not in hs, "刷流名下的种不在名单里")
_ok(H_F not in hs, "静默池无主种不在名单里")
_ok(all(r["hash"] in (H_A, H_B, H_C, H_D) for r in rows), "名单里只有 4 个保种 hash")
_ok(resp.data["total"] == 4, "total 与 items 一致")

# =====================================================================
# [B] 异常优先排序 + not_seeding 计数
# =====================================================================
print("\n[B] 排序：幽灵行 → 没在做种（体积降序）→ 正常做种")
_ok(hs[0] == H_C, f"第一个是不在下载器的幽灵行（实得 {hs[0][:8]}）")
_ok(hs[1] == H_D and hs[2] == H_B,
    f"中间两个没在做种、按体积降序 50GB → 30GB（实得 {hs[1][:8]}/{hs[2][:8]}）")
_ok(hs[3] == H_A, f"最后是正常做种的（实得 {hs[3][:8]}）")
_ok(resp.data["not_seeding"] == 3, f"未在做种 3 个（幽灵+暂停+没下完；实得 {resp.data['not_seeding']}）")
_ok("未在做种 3" in resp.message, f"message 带告警数（实得 {resp.message!r}）")

# =====================================================================
# [C] seeding 判定口径
# =====================================================================
print("\n[C] seeding = 在下载器 + progress>=0.999 + 状态在上传侧")
by_h = {r["hash"]: r for r in rows}
_ok(by_h[H_A]["seeding"] is True and by_h[H_A]["in_qb"] is True, "uploading + 100% → 在做种")
_ok(by_h[H_B]["seeding"] is False and by_h[H_B]["in_qb"] is True,
    "pausedUP + 100% → 在下载器但没在做种（暂停）")
_ok(by_h[H_C]["seeding"] is False and by_h[H_C]["in_qb"] is False,
    "不在下载器 → in_qb=False 且 seeding=False")
_ok(by_h[H_D]["seeding"] is False and by_h[H_D]["in_qb"] is True,
    "pausedDL + 42% → 没在做种")

for _st, _want in (("stalledUP", True), ("queuedUP", True), ("forcedUP", True),
                   ("checkingUP", True), ("uploading", True),
                   ("pausedUP", False), ("stoppedUP", False), ("error", False)):
    hh = "0123456789abcdef0123456789abcdef01234567"
    r2 = _Fake({hh: _t(hh, [KEEP_TAG], state=_st)},
               {hh: {"site": SITE, "state": STATE_KEEP, "taken_by": KEEP_TASK_ID}}
               )._tag_act_hold_list(_req()).data["items"][0]
    _ok(r2["seeding"] is _want, f"state={_st} → seeding={_want}")

# stalledUP 有人连也算「在做种」—— 否则它会天天出现在「该处理」里
hh2 = "1123456789abcdef0123456789abcdef01234567"
r3 = _Fake({hh2: _t(hh2, [KEEP_TAG], state="stalledUP")},
           {hh2: {"site": SITE, "state": STATE_KEEP, "taken_by": KEEP_TASK_ID}}
           )._tag_act_hold_list(_req()).data["items"][0]
_ok(r3["seeding"] is True, "stalledUP（暂没流量但有人在连）仍算在做种，不误报")

# =====================================================================
# [D] 字段回退 + limit
# =====================================================================
print("\n[D] 站点名/体积回退，limit 生效")
_ok(all(r["site"] == SITE for r in rows), "site 取账本值")
_ok(by_h[H_C]["size_gb"] == 8.0, f"幽灵行体积回退到账本 record（实得 {by_h[H_C]['size_gb']}）")
_ok(by_h[H_D]["size_gb"] == 50.0, f"在下载器的取实况体积（实得 {by_h[H_D]['size_gb']}）")

_led_nosite = {H_A: {"state": STATE_KEEP, "taken_by": KEEP_TASK_ID}}  # 无 site 字段
r4 = _Fake({H_A: _t(H_A, [KEEP_TAG])}, _led_nosite)._tag_act_hold_list(_req()).data["items"][0]
_ok(r4["site"] == SITE, f"账本无 site → 从标签反推（实得 {r4['site']!r}）")

_n5 = len(host._tag_act_hold_list(_req(limit="2")).data["items"])
_ok(_n5 == 2, f"limit=2 截断（实得 {_n5}）")
_ok(host._tag_act_hold_list(_req(limit="abc")).data["total"] == 4, "limit 非法值不炸、返回全量")
_ok(host._tag_act_hold_list(_req(limit="0")).data["total"] == 4, "limit=0 = 不限")

# =====================================================================
# [E] 空账本 / 全空快照 / 纯只读
# =====================================================================
print("\n[E] 边界：空账本、下载器不可用；接口纯只读")
empty = _Fake({}, {})._tag_act_hold_list(_req())
_ok(empty.success is True and empty.data["total"] == 0, "空账本 → total=0、不报错")

# 下载器快照拿不到（_tag_all_torrents 抛异常）→ 全部按幽灵行，不当成「在做种」
class _Broken(_Fake):
    def _tag_all_torrents(self):
        raise RuntimeError("qB 掉了")

    def _tag_state(self):
        return _Store({H_A: {"site": SITE, "state": STATE_KEEP, "taken_by": KEEP_TASK_ID}})

br = _Broken({}, {})._tag_act_hold_list(_req())
_ok(br.success is True and br.data["total"] == 1, "qB 快照不可用 → 仍返回账本名单，不炸")
_ok(br.data["items"][0]["in_qb"] is False and br.data["items"][0]["seeding"] is False,
    "qB 不可用时标 in_qb=False / seeding=False（不谎报在做种）")

host2 = _Fake(SNAP, LEDGER)
host2._tag_act_hold_list(_req())
_ok(host2._dl.writes == [], f"一个 qB 标签都没改（实得 {len(host2._dl.writes)} 次）")

# =====================================================================
# [F] 源码护栏：别名注册 + 不得出现写操作
# =====================================================================
print("\n[F] 源码护栏：动作已注册、实现里不写账本")
_alias_src = (ROOT / "features" / "tags.py").read_text(encoding="utf-8")
_ok('"hold_list"' in _alias_src, "动作别名表里有 hold_list")
_ok('TagsMixin._tag_act_hold_list, "hold_list"' in _alias_src,
    "别名表指向 _tag_act_hold_list（不是绑错函数）")
_ok("_tag_act_hold_list" in _alias_src and "keep_list" not in _alias_src.split("_ACT_ALIASES")[1][:4000],
    "别名集合内无拼写分叉（keep_list 未注册）")

_src = _alias_src.split("def _tag_act_hold_list")[1].split("\n    def ")[0]
for _bad in (".put(", ".claim(", ".release(", "set_torrent_tags", "replace_torrent_tags"):
    _ok(_bad not in _src, f"实现内不含写操作 {_bad!r}")

print(f"\n✅ 全部通过：{CHECKS} 项")
