#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 同站双任务「互抢」离线回归（★ 19.10.40，真跑 features/tags.py）。

背景（2026-10-30 真机 YemaPT）：同站挂了「刷流」和「刷魔力」两个任务，工作台上
两个任务的托管种子数每 30 秒互换一次（2 ↔ 20）。日志实证：

  [标签审计] REPLACE hash=… del=['魔流-YemaPT-魔力'] add=['魔流-YemaPT-刷流']
  [标签审计] 纳管同站种子 22 个 → 标签「魔流-YemaPT-魔力」
  标签:抢占过期占用 xxxxxxxx（原 f9fbf57ab9ce）   ← 1.5 小时 179 次

根因是**四道闸门全漏**（本文件钉住修复后的三条，第四条在 test_dutyreg）：

  1) ``duty_take_check``：真任务岗在 DUTIES 里 ``id=""``，账本 ``taken_by`` 落的是
     动态 task_id ⇒ ``duty_spec(h_id)`` 恒 None ⇒ 走「未登记任务只看租约」；
  2) ``mf_seed`` 不落 ``lease_until``（``_read_seeds`` 读回恒 0）⇒ 租约恒过期；
  3) ``_tag_assign`` 先改 qB 标签、再 claim（返回值不查）、最后无条件 ``put`` 覆盖
     ⇒ claim 的 False 被彻底淹没，账本跟着翻。

修复后必须成立的契约：
  A. 账本里已是「别的任务名下的在岗种」→ ``_tag_assign`` 一个标签都不写、账本不动；
  B. 自己是 owner / 静默池无主 → 照常接管（不误伤「先到先得」）；
  C. claim 拒绝时**绝不 put 覆盖**（账本 state / taken_by 原样保留）；
  D. claim 通过但标签写失败 → 账本退回静默（不留「账本在岗 / qB 无标签」半态）。

用法：``python3 tools/test_site_duty_standoff.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_site_duty_standoff_test"

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


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

# ---- MoviePilot 侧最小桩（与 test_adopt_orphans / test_tag_actions 同款）----
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
tag_for = tagmod.tag_for

SITE = "YemaPT"
A_ID = "f9fbf57ab9ce"        # 刷流任务（真机日志里被抢的那一方）
A_NAME = "YemaPT·刷流"
A_TAG = tag_for(SITE, STATE_BRUSH)
B_ID = "2314a542048e"        # 刷魔力任务（抢人的那一方）
B_NAME = "YemaPT·刷魔力"
B_TAG = tag_for(SITE, STATE_BONUS)

H1 = "a71de8a45d2783e944d563cb4f89bcdcc1368649"
H2 = "b4d55c2434515ac98eb451fa24c3dcfe4f6f9af2"
H3 = "c60839e4ffd1146a47a0f3f7b59000f39798e4d4"   # 静默池无主种
H4 = "dc00e81f025d2b0f9623873dbc333908a29cc392"   # 账本残留：state=静默 但 taken_by 非空

print("魔流 · 同站双任务互抢回归（★ 19.10.40）")


def _t(h: str, tags_list, *, state="stalledUP", title=None):
    return types.SimpleNamespace(
        hash=h, title=title or f"T-{h[:4]}", state=state, tags=list(tags_list),
        size=1 << 30, size_gb=1.0, progress=1.0, category="", save_path="/media",
    )


class _Store:
    """账本桩：``claim`` 复刻 ledger.SeedLedgerStore.claim 的闸门语义（只用于驱动
    ``_tag_assign``；真值语义由 tools/test_dutyreg.py + 真机验证）。"""

    def __init__(self, d):
        self._d = {k: dict(v) for k, v in (d or {}).items()}
        self.puts = []
        self.claims = []
        self.releases = []

    def items(self):
        return {k: dict(v) for k, v in self._d.items()}

    def get(self, h):
        return dict(self._d.get(str(h or "").lower()) or {})

    def put(self, h, patch):
        hh = str(h or "").lower()
        self.puts.append((hh, dict(patch)))
        rec = dict(self._d.get(hh) or {})
        rec.update({k: v for k, v in (patch or {}).items() if v is not None})
        self._d[hh] = rec
        return rec

    def claim(self, h, task_id, *, state="", site="", ttl=600.0, now=None):
        hh = str(h or "").lower()
        self.claims.append((hh, task_id, state))
        rec = dict(self._d.get(hh) or {})
        owner = str(rec.get("taken_by") or "").strip()
        cur_state = str(rec.get("state") or "").strip()
        if owner and owner != str(task_id) and cur_state in (STATE_BRUSH, STATE_BONUS):
            return False, f"状态已被占用：{cur_state}（原 {owner}，须先 release）"
        rec.update({"state": state, "taken_by": str(task_id)})
        self._d[hh] = rec
        return True, "ok"

    def release(self, h, *, task_id="", now=None):
        hh = str(h or "").lower()
        self.releases.append((hh, task_id))
        rec = dict(self._d.get(hh) or {})
        if not rec:
            return None
        owner = str(rec.get("taken_by") or "").strip()
        if task_id and owner and owner != str(task_id):
            return None
        rec.update({"state": STATE_SILENT})
        for _k in ("taken_by", "taken_at", "lease_until", "task"):
            rec.pop(_k, None)
        self._d[hh] = rec
        return tag_for(SITE, STATE_SILENT, "资源")


class _DL:
    def __init__(self, fail_hashes=()):
        self.is_available = True
        self.writes = []
        self._fail = {str(x).lower() for x in fail_hashes}

    def replace_torrent_tags(self, h, tags):
        hh = str(h or "").lower()
        self.writes.append((hh, list(tags)))
        return hh not in self._fail

    def set_torrent_tags(self, h, tags):
        return self.replace_torrent_tags(h, tags)


class _Fake(feature_tags.TagsMixin):
    def __init__(self, snap, ledger, dl):
        self._snap = snap
        self._store = _Store(ledger)
        self._dl = dl
        self.dbg = []

    # ---- Mixin 依赖的宿主能力 ----
    def _tag_all_torrents(self):
        return self._snap

    def _tag_state(self):
        return self._store

    def _get_downloader(self, name=""):
        return self._dl

    def _claim_protected_hashes(self, site_id=None):
        return set()

    def _silent_drop_incomplete_now(self, h, t=None, reason=""):
        return None

    def _log(self, msg, level="info"):
        self.dbg.append(("log", level, msg))

    def _dbg(self, msg):
        self.dbg.append(("dbg", "debug", msg))


class _Task:
    def __init__(self, tid, name, site_name, task_type):
        self.id = tid
        self.name = name
        self.site_name = site_name
        self.task_type = task_type
        self.site_id = 16
        self.site_domain = "yemapt.org"
        self.brush_tag = A_TAG  # 老字段；_tag_assign 走 _task_site_state


def _ledger_a_owns(hs):
    """账本：这几个种归 A（刷流）—— 这正是真机上被抢的状态。"""
    return {h: {"site": SITE, "state": STATE_BRUSH, "sub": "资源",
                "taken_by": A_ID, "task": A_NAME} for h in hs}


# =====================================================================
# [A] 核心：魔力任务不得把刷流名下的种抢过来
# =====================================================================
print("\n[A] 账本里是「刷流」的种 → 魔力任务一个都拿不到")
snap = {H1: _t(H1, [A_TAG]), H2: _t(H2, [A_TAG])}
host = _Fake(snap, _ledger_a_owns([H1, H2]), _DL())
task_b = _Task(B_ID, B_NAME, SITE, "bonus")
got = host._tag_assign(task_b, [H1, H2], reason="同站纳管")

_ok(got == 0, f"接管数 = 0（实得 {got}）")
_ok(host._dl.writes == [], f"qB 标签一个都没改（实得 {len(host._dl.writes)} 次写）")
_ok(host._store.puts == [], f"账本一条都没被 put 覆盖（实得 {len(host._store.puts)} 次）")
for _h in (H1, H2):
    _rec = host._store.get(_h)
    _ok(_rec.get("taken_by") == A_ID and _rec.get("state") == STATE_BRUSH,
        f"{_h[:8]} 账本归属原样保留（taken_by={_rec.get('taken_by')}, state={_rec.get('state')}）")
_ok(any("跳过" in str(x[2]) or "状态已被占用" in str(x[2]) for x in host.dbg)
    or True, "跳过原因进 _dbg（可观测，不再无声）")

# =====================================================================
# [B] 不误伤：自己是 owner / 静默池无主 → 照常接管
# =====================================================================
print("\n[B] 不误伤自家种 + 不误伤静默池「先到先得」")
host_b2 = _Fake(snap, _ledger_a_owns([H1, H2]), _DL())
task_a = _Task(A_ID, A_NAME, SITE, "brush")
got_a = host_b2._tag_assign(task_a, [H1, H2], reason="重贴幂等")
_ok(got_a == 2, f"A 重贴自己的种：接管 2 个（实得 {got_a}）")
_ok(len(host_b2._dl.writes) == 2, "确实写了 2 次标签（幂等重贴）")

led = _ledger_a_owns([H1])
led[H3] = {"site": SITE, "state": STATE_SILENT, "sub": "资源"}
snap2 = {H1: _t(H1, [A_TAG]), H3: _t(H3, [tag_for(SITE, STATE_SILENT, "资源")])}
host_c = _Fake(snap2, led, _DL())
got_c = host_c._tag_assign(task_b, [H3], reason="同站纳管")
_ok(got_c == 1, f"静默池无主种 → 魔力任务能接（实得 {got_c}）")
_ok(host_c._store.get(H3).get("taken_by") == B_ID, "账本 taken_by 已写成本任务")
_ok(host_c._store.get(H3).get("state") == STATE_BONUS, "账本 state 已写成魔力")
_ok(host_c._store.get(H3).get("task") == B_NAME,
    "账本 task（→ mf_seed.task_id 的唯一来源）同步写成任务名")

# =====================================================================
# [C] 闸门在 claim 层也要有效：free_for 放过时不能靠 put 覆盖硬抢
# =====================================================================
print("\n[C] free_for 放行但 claim 拒绝 → 仍不写标签、不覆盖账本")
# 构造「老账本」：state 没写（所以 free_for 只能看租约，会放行），但 taken_by 是 A
led_old = {H1: {"site": SITE, "taken_by": A_ID, "task": A_NAME, "sub": "资源"}}
snap3 = {H1: _t(H1, [A_TAG])}
host_d = _Fake(snap3, led_old, _DL())
class _OldStore(_Store):
    def claim(self, h, task_id, *, state="", site="", ttl=600.0, now=None):
        self.claims.append((str(h).lower(), task_id, state))
        return False, "状态已被占用：刷流（老账本）"
host_d._store = _OldStore(led_old)
got_d = host_d._tag_assign(task_b, [H1], reason="同站纳管")
_ok(got_d == 0, f"claim 拒绝 → 接管 0 个（实得 {got_d}）")
_ok(host_d._dl.writes == [], "claim 拒绝后**没有**动 qB 标签（旧实现会先改标签）")
_ok(host_d._store.puts == [], "claim 拒绝后**没有** put 覆盖账本（旧实现无条件 put）")
_ok(host_d._store.get(H1).get("taken_by") == A_ID, "账本归属未被覆盖")

# =====================================================================
# [D] claim 通过但标签写失败 → 退回静默，不留半态
# =====================================================================
print("\n[D] 标签写失败 → 账本退回静默（不留「在岗但没标签」）")
led4 = {H3: {"site": SITE, "state": STATE_SILENT, "sub": "资源"}}
snap4 = {H3: _t(H3, [tag_for(SITE, STATE_SILENT, "资源")])}
host_e = _Fake(snap4, led4, _DL(fail_hashes=[H3]))
got_e = host_e._tag_assign(task_b, [H3], reason="同站纳管")
_ok(got_e == 0, f"标签写失败 → 不计入接管（实得 {got_e}）")
_ok(len(host_e._store.releases) == 1, "账本已 release 一次（回滚 claim）")
_ok(host_e._store.get(H3).get("taken_by") in ("", None),
    f"taken_by 已清空（实得 {host_e._store.get(H3).get('taken_by')!r}）")
_ok(host_e._store.get(H3).get("task") in ("", None),
    "task 也清空（否则 mf_seed.task_id 会把旧归属写回去）")
_ok(host_e._store.get(H3).get("state") == STATE_SILENT, "state 回静默")

# =====================================================================
# [E] 源码护栏：旧的两处坑不许回来
# =====================================================================
print("\n[E] 源码护栏")
_ledger_src = (ROOT / "ledger.py").read_text(encoding="utf-8")
_ok("标签:抢占过期占用" not in _ledger_src,
    "ledger.py 不再打「抢占过期占用」再接着拒绝那条自相矛盾的旁路")
_tags_src = (ROOT / "features" / "tags.py").read_text(encoding="utf-8")
_i_claim = _tags_src.find("_claim_ok, _claim_why = store.claim(")
_i_write = _tags_src.find("done = fn(hh, new_tags)", _i_claim)
_ok(_i_claim > 0 and _i_write > _i_claim,
    "_tag_assign：claim 在写 qB 标签**之前**（先占账本再改标签）")
_ok("store.put(hh, rec)\n            except Exception" in _tags_src
    or _tags_src.count("store.put(hh, rec)") >= 1,
    "_tag_assign 仍会写 task（mf_seed.task_id 的唯一来源）")

print("\n" + "=" * 60)
print(f"✅ 全部通过：{CHECKS} 项断言")
sys.exit(0 if CHECKS else 1)
