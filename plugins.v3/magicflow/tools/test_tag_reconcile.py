#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 标签 ↔ 账本对账（★ 15.2.0）离线回归 —— 真跑 features/tags.py，不需 MoviePilot。

背景（Master 2026-10-07 11:08「行吧」批准的「身份不齐」清理）：
  真值源是**种子账本**（`mf_seed`：谁在岗 / 职务 / 身份），qB 标签只是它的**镜像**。
  实测有 47 个 `魔流-<站>-魔力` 缺身份轴（`魔流-<站>-静默-<子>`）、2 个账本说「保种」标签却没职务。
  `_tag_ledger_reconcile()` 按账本把标签补回（自愈），口径：

  1) 干跑默认**零写入**；`apply=True` 才写，且**只写 qB 标签**；
  2) 账本在岗（魔力/刷流/保种）+ qB 有 → 期望 = ``retag(cur, site, state, sub)``，不一致才补；
  3) 标的种**不删、不暂停、不 resume、不改种子账本**；
  4) 幂等：补齐后再跑 = 0 待补；
  5) `adopt_reseed=True`：有 `魔流-辅种`、两本账都没登记、能解出 IYUU sid 的「无主辅种副本」→ 补登 `mf_reseed`；
  6) 只带静默身份、不在账本（`tag_only`）→ **一律不动**（15.1.0 口径：不定罪、不写账本）。

用法：``python3 tools/test_tag_reconcile.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_tag_reconcile_test"


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

# app.* 桩
for _name, _attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": type("EventType", (), {})}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
):
    _m = sys.modules.get(_name) or types.ModuleType(_name)
    sys.modules[_name] = _m
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)

# 兄弟模块桩（features/tags.py 需要）
_mod_pkg = _pkg(PKG + ".models", ROOT / "models")  # 仅占位，下面覆盖
_m = types.ModuleType(PKG + ".models")
_m.MagicFlowTagStatePayload = object
sys.modules[PKG + ".models"] = _m

_ledger = types.ModuleType(PKG + ".ledger")
_ledger.ResourceLedgerStore = type("ResourceLedgerStore", (), {})
_ledger.SeedLedgerStore = type("SeedLedgerStore", (), {})
_ledger.get_backend = lambda *a, **k: None
sys.modules[PKG + ".ledger"] = _ledger

for _modname, _attrs in (("bonus", ("calc_bonus_per_hour", "TorrentBonusInfo")),
                         ("fetcher", ("SiteCandidateTorrent",))):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    sys.modules[PKG + "." + _modname] = _m

tags_root = _load(PKG + ".tags", "tags.py")
_load(PKG + ".fingerprint", "fingerprint.py")
_load(PKG + ".persistence", "persistence.py")
common = _load(PKG + ".common", "common.py")
_load(PKG + ".downloader_ops", "downloader_ops.py")
ftags = _load(PKG + ".features.tags", "features/tags.py")

MARK_REUSE = tags_root.MARK_REUSE
STATE_BONUS = tags_root.STATE_BONUS
STATE_HR = tags_root.STATE_HR
STATE_SILENT = tags_root.STATE_SILENT

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _torrent(h, tags, state="stalledUP", category=""):
    return types.SimpleNamespace(hash=h, title=h, state=state, size=1 << 30,
                                 tags=list(tags), progress=1.0, category=category,
                                 save_path="/x", content_path=f"/x/{h}")


class _Store:
    def __init__(self, d):
        self._d = d
        self.released = []

    def items(self):
        return dict(self._d)

    def get(self, h):
        return self._d.get(str(h or "").lower()) or {}

    # ★ 15.8.11 同版补丁：``_music_asset_pin`` 要用；语义对齐真 ``SeedLedgerStore.put``
    #   （``None`` 跳过、只 merge 值）。
    def put(self, h, patch):
        k = str(h or "").lower()
        rec = dict(self._d.get(k) or {})
        rec.update({str(a): b for a, b in dict(patch or {}).items() if b is not None})
        self._d[k] = rec
        return rec

    # ★ 15.8.11：``_music_ledger_release`` 要用；语义对齐真 ``SeedLedgerStore.release``
    #   （属主保护 + 清 task/taken_by），否则测不出「release 把归属一起带走」。
    def release(self, h, *, task_id=""):
        k = str(h or "").lower()
        rec = dict(self._d.get(k) or {})
        if not rec:
            return None
        owner = str(rec.get("taken_by") or "")
        if task_id and owner and owner != str(task_id):
            return None
        rec.pop("task", None)
        rec.pop("taken_by", None)
        rec["state"] = STATE_SILENT
        self._d[k] = rec
        self.released.append((k, str(task_id)))
        return "魔流-静默"


class _DL:
    is_available = True

    def __init__(self, snap):
        self._snap = snap
        self.calls = []
        self.deletes = []

    def replace_torrent_tags(self, h, tags):
        self.calls.append((str(h).lower(), list(tags)))
        t = self._snap.get(str(h).lower())
        if t is not None:
            t.tags = list(tags)
        return True

    def set_torrent_tags(self, h, tags):
        return self.replace_torrent_tags(h, tags)

    def delete_torrents(self, *a, **k):
        self.deletes.append((a, k))
        return 0, None

    def pause_torrents(self, *a, **k):  # pragma: no cover
        raise AssertionError("对账绝不应 pause")

    def resume_torrents(self, *a, **k):  # pragma: no cover
        raise AssertionError("对账绝不应 resume")


class _Groups:
    """资源组库桩（★ 15.8.11 同版补丁：``_music_asset_pin`` 会写身份）。"""

    def __init__(self, gid_of=None):
        self._gof = gid_of
        self.identities = []

    def group_of(self, h):
        return self._gof(str(h or "").lower()) if callable(self._gof) else ""

    def set_identity(self, gid, sub, by=""):
        self.identities.append((str(gid), str(sub), str(by)))
        return True


class Harness(ftags.TagsMixin):
    """真 TagsMixin + 桩依赖；`_tag_ledger_reconcile` 走**真实现**。"""

    def __init__(self, seed=None, snap=None, reseed=None, site_map=None, groups=None):
        self.seed = dict(seed or {})
        self.snap = dict(snap or {})
        self.reseed = dict(reseed or {})
        self.site_map = dict(site_map or {})
        self.groups = _Groups(groups)
        self.dl = _DL(self.snap)
        self.logs = []
        self.forgotten = []
        self._store = types.SimpleNamespace(forget_torrents=self._forget)

    def _forget(self, task_id, hashes):
        self.forgotten.append((str(task_id), [str(x) for x in (hashes or [])]))
        return len(hashes or [])

    def _get_downloader(self, name="qbittorrent"):
        return self.dl

    def _tag_state(self):
        return _Store(self.seed)

    def _tag_all_torrents(self):
        return dict(self.snap)

    def _tag_groups(self):
        return self.groups

    def _reseed_ledger(self):
        return dict(self.reseed)

    def _reseed_site_map(self):
        return {int(v): {"sid": int(v), "name": k} for k, v in self.site_map.items()}

    def _reseed_ledger_put(self, key, st, note):
        self.reseed[str(key)] = {"st": st, "note": note}

    def _log(self, msg, level=None):
        self.logs.append(str(msg))


def t1_dry_run():
    print("① 干跑：只报「缺身份轴」，零写入")
    seed = {"h1": {"state": STATE_BONUS, "site": "Depth Studio", "sub": "新"}}
    snap = {"h1": _torrent("h1", ["魔流-Depth Studio-魔力"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=False)
    _ok(rep["checked"] == 1, f"查了 1 个在岗种（实际 {rep['checked']}）")
    _ok(len(rep["items"]) == 1, "报 1 个待补")
    it = rep["items"][0]
    _ok(it["missing_identity"] is True and it["missing_duty"] is False,
        "判据：缺身份轴、不缺职务")
    _ok("魔流-Depth Studio-静默-新" in it["will"], f"期望标签含身份轴（{it['will']}）")
    _ok(not h.dl.calls, "干跑零写入（下载器无 set_tag）")
    _ok(h.seed and not h.reseed, "种子账本 / 辅种账本都没动")


def t2_apply():
    print("② apply=True：按账本补标签，只写 qB 标签")
    seed = {"h1": {"state": STATE_BONUS, "site": "Depth Studio", "sub": "新"}}
    snap = {"h1": _torrent("h1", ["魔流-Depth Studio-魔力"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(rep["repaired"] == 1, f"补了 1 个（实际 {rep['repaired']}）")
    _ok(len(h.dl.calls) == 1, "恰 1 次写标签")
    _h, new = h.dl.calls[0]
    _ok("魔流-Depth Studio-静默-新" in new and "魔流-Depth Studio-魔力" in new,
        f"新标签含身份轴 + 保留职务（{new}）")
    _ok(not h.dl.deletes, "没有删除")
    # 幂等
    rep2 = h._tag_ledger_reconcile(apply=True)
    _ok(not rep2["items"] and rep2["repaired"] == 0, "幂等：复跑 0 待补、0 补写")
    return h


def t3_identity_drift():
    print("③ 身份与账本打架：账本=保种、标签=静默身份（缺职务）→ 补职务")
    seed = {"h2": {"state": STATE_HR, "site": "学校", "sub": "资源"}}
    snap = {"h2": _torrent("h2", ["魔流-学校-静默-资源"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(rep["repaired"] == 1, "补了 1 个")
    it = rep["items"][0]
    _ok(it["missing_duty"] is True and it["missing_identity"] is False,
        "判据：缺职务、不缺身份")
    _h, new = h.dl.calls[0]
    _ok("魔流-学校-保种" in new, f"补回保种职务（{new}）")


def t4_skips():
    print("④ 只管在岗：静默账本 / 无站点 / qB 里没有 → 跳过")
    seed = {
        "s1": {"state": STATE_SILENT, "site": "聆音", "sub": "资源"},   # 静默身份，不归对账管
        "s2": {"state": STATE_BONUS, "site": "", "sub": "新"},          # 无站点
        "s3": {"state": STATE_BONUS, "site": "聆音", "sub": "新"},      # qB 里没有
        "s4": {"state": tags_root.STATE_BRUSH, "site": "聆音", "sub": "新"},  # 唯一该处理的
    }
    snap = {"s1": _torrent("s1", ["魔流-聆音-静默-资源"]),
            "s2": _torrent("s2", ["魔流-聆音-魔力"]),
            "s4": _torrent("s4", ["魔流-聆音-刷流"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(rep["checked"] == 1, f"只查到 1 个在岗且 qB 存在的（实际 {rep['checked']}）")
    _ok(len(rep["items"]) == 1 and rep["items"][0]["hash"] == "s4", "只报 s4")
    _ok([c[0] for c in h.dl.calls] == ["s4"], "只写 s4 的标签")


def t5_adopt_reseed():
    print("⑤ 无主辅种副本：adopt_reseed → 补登 mf_reseed（干跑不写）")
    snap = {"h3": _torrent("h3", [MARK_REUSE, "魔流-聆音-静默-资源"], state="pausedUP")}
    h = Harness(seed={}, snap=snap, site_map={"聆音": 7})
    rep = h._tag_ledger_reconcile(apply=False, adopt_reseed=True)
    _ok(len(rep["adopt_items"]) == 1, "报 1 个无主辅种副本")
    _ok(rep["adopt_items"][0]["key"] == "7:h3", f"键 = sid:hash（{rep['adopt_items'][0]['key']}）")
    _ok(rep["adopted"] == 0 and not h.reseed, "干跑不落盘")
    # apply
    rep2 = h._tag_ledger_reconcile(apply=True, adopt_reseed=True)
    _ok(rep2["adopted"] == 1 and "7:h3" in h.reseed, "apply 补登进辅种账")
    # 再跑：已在册 → 不再报
    rep3 = h._tag_ledger_reconcile(apply=False, adopt_reseed=True)
    _ok(not rep3["adopt_items"], "已在册 → 不重复报")


def t6_tag_only_untouched():
    print("⑥ 只带静默身份、不在账本（tag_only）→ 一律不动（不写账本）")
    snap = {"h4": _torrent("h4", ["魔流-聆音-静默-资源"])}
    h = Harness(seed={}, snap=snap, site_map={"聆音": 7})
    rep = h._tag_ledger_reconcile(apply=True, adopt_reseed=True)
    _ok(not rep["items"], "不把 tag_only 当在岗种补标签")
    _ok(not rep["adopt_items"], "没带 魔流-辅种 → 不补登")
    _ok(not h.dl.calls and not h.reseed, "零写入")


def t7_sub_drift_only_reported():
    print("⑦ 纯身份子桶漂移（身份/职务都在，sub 与账本不同）→ 只报不写")
    seed = {"h5": {"state": STATE_BONUS, "site": "聆音", "sub": "资源"}}
    snap = {"h5": _torrent("h5", ["魔流-聆音-静默-普通", "魔流-聆音-魔力"])}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(not rep["items"] and rep["items_total"] == 0, "不进「待补」（不自动改写 sub）")
    _ok(rep["drift_total"] == 1 and rep["drift"][0]["kind"] == "sub_drift", "归入 drift（只报）")
    _ok(not h.dl.calls, "零写入")


def t8_music_exempt():
    print("⑧ ★15.8.11 音乐线豁免：账本说「魔力」+ qB 分类=音乐 → 不把职务标签补回去")
    seed = {"m1": {"state": STATE_BONUS, "site": "CARPT", "sub": "新"},
            "m2": {"state": STATE_HR, "site": "CARPT", "sub": "资源"}}   # 保种照旧补
    snap = {"m1": _torrent("m1", ["魔流-CARPT-静默-新"], category="音乐"),
            "m2": _torrent("m2", ["魔流-CARPT-静默-资源"], category="音乐")}
    h = Harness(seed=seed, snap=snap)
    rep = h._tag_ledger_reconcile(apply=True)
    _ok(rep["skipped_music"] == 1, f"跳过 1 个音乐魔力/刷流种（实际 {rep['skipped_music']}）")
    _ok([c[0] for c in h.dl.calls] == ["m2"], "只写音乐「保种」种，不写音乐「魔力」种")
    _ok("魔流-CARPT-保种" in h.dl.calls[0][1], "音乐也要走 H&R → 保种职务照补")


def t9_music_ledger_release():
    print("⑨ ★15.8.11 账本归还：账本=魔力/刷流 + qB 分类=音乐 → release（保种/非音乐/已静默不动）")
    seed = {
        # 现场那一格：标签早就只剩静默身份了，账本 task_id 还指着 CARPT 任务
        "m1": {"state": STATE_BONUS, "site": "CARPT", "sub": "新",
               "task": "CARPT·自定义", "taken_by": "af8177e6dfa2"},
        "m2": {"state": STATE_HR, "site": "CARPT", "sub": "资源",
               "taken_by": "__hr_host__"},                      # 保种：音乐也要走 H&R → 不动
        "m3": {"state": STATE_BONUS, "site": "馒头", "sub": "资源",
               "taken_by": "6cb4fe6f3f13"},                      # 非音乐：不是音乐线的事
        "m4": {"state": STATE_SILENT, "site": "CARPT", "sub": "资源"},  # 已静默：真干净
    }
    snap = {"m1": _torrent("m1", ["魔流-CARPT-静默-新"], category="音乐"),
            "m2": _torrent("m2", ["魔流-CARPT-保种"], category="音乐"),
            "m3": _torrent("m3", ["魔流-馒头-魔力"]),
            "m4": _torrent("m4", ["魔流-CARPT-静默-资源"], category="音乐")}
    h = Harness(seed=seed, snap=snap)
    dry = h._music_ledger_release(apply=False)
    _ok(dry["candidates"] == 1, f"干跑：只认 1 个「账本在岗的音乐种」（实际 {dry['candidates']}）")
    _ok(dry["samples"][0]["owner"] == "af8177e6dfa2", "样本带出占用任务 id")
    _ok(not h._tag_state().released and not h.forgotten, "干跑：账本/qB 零写入")
    app = h._music_ledger_release(apply=True)
    _ok(app["released"] == 1 and app["failed"] == 0, "执行：归还 1 笔")
    st = h._tag_state()
    _ok(st.get("m1").get("state") == STATE_SILENT, "m1 账本回静默")
    _ok(not st.get("m1").get("task") and not st.get("m1").get("taken_by"),
        "m1 归属清空（★ task 名也要清，否则 task_id 会被写回）")
    _ok(st.get("m2").get("state") == STATE_HR, "m2 保种：一分不动（音乐也走 H&R）")
    _ok(st.get("m3").get("state") == STATE_BONUS, "m3 非音乐：不动")
    _ok(h.forgotten == [("af8177e6dfa2", ["m1"])], "任务侧忘种 protected/adopted")
    again = h._music_ledger_release(apply=True)
    _ok(again["candidates"] == 0 and again["released"] == 0, "幂等：再跑零动作")
    # 属主保护：账本说 owner-A，按 owner-B 退 → 不放（return None）
    h2 = Harness(seed={"z": {"state": STATE_BONUS, "site": "CARPT", "sub": "新",
                             "taken_by": "owner-A"}},
                 snap={"z": _torrent("z", ["魔流-CARPT-魔力"], category="音乐")})
    st2 = h2._tag_state()
    _ok(st2.release("z", task_id="owner-B") is None, "release 属主不符 → None（不放）")
    _ok(st2.release("z", task_id="owner-A") is not None, "release 属主相符 → 放行")


def t10_music_asset_pin():
    print("⑩ ★15.8.11 同版补丁 身份钉「资源」：音乐种 → 账本 sub=资源 + 标签静默-资源 + 资源组库记")
    seed = {
        "m1": {"state": STATE_SILENT, "site": "CARPT", "sub": "新"},     # 该钉
        "m2": {"state": STATE_SILENT, "site": "CARPT", "sub": "普通"},   # 该钉（被 ⑦分拣降级的那格）
        "m3": {"state": STATE_BONUS, "site": "CARPT", "sub": "新"},      # 职务态：不抢
        "m4": {"state": STATE_SILENT, "site": "馒头", "sub": "资源"},    # 已是资源 → 幂等跳过
        "m5": {"state": STATE_SILENT, "site": "聆音", "sub": "新"},      # 非音乐 → 不动
    }
    snap = {"m1": _torrent("m1", ["魔流-CARPT-静默-新", "魔流-推荐"], category="音乐"),
            "m2": _torrent("m2", ["魔流-CARPT-静默-普通"], category="音乐"),
            "m3": _torrent("m3", ["魔流-CARPT-魔力"], category="音乐"),
            "m4": _torrent("m4", ["魔流-馒头-静默-资源"], category="音乐"),
            "m5": _torrent("m5", ["魔流-聆音-静默-新"])}
    h = Harness(seed=seed, snap=snap, groups=lambda g: "fp:" + g)
    dry = h._music_asset_pin(apply=False)
    _ok(dry["candidates"] == 2, f"干跑：2 个待钉身份（实际 {dry['candidates']}）")
    _ok(dry["skipped_duty"] == 1, f"职务态（魔力）不抢 → skipped_duty=1（实际 {dry['skipped_duty']}）")
    _ok(dry["pinned"] == 0 and not h.dl.calls, "干跑零写入（qB / 账本 / 资源组库都不动）")
    app = h._music_asset_pin(apply=True)
    _ok(app["pinned"] == 2 and app["failed"] == 0, f"执行：钉 2 个（实际 {app['pinned']}）")
    st = h._tag_state()
    _ok(st.get("m1").get("sub") == "资源" and st.get("m2").get("sub") == "资源",
        "账本身份 sub → 资源")
    new = dict(h.dl.calls)
    _ok("魔流-CARPT-静默-资源" in new.get("m1", []), f"m1 标签重算成静默-资源（{new.get('m1')}）")
    _ok("魔流-推荐" not in new.get("m1", []),
        "归资源时「魔流-推荐」生命周期结束（与 _silent_to_resource 同构）")
    _ok(h.groups.identities == [("fp:m1", "资源", "music"), ("fp:m2", "资源", "music")],
        f"资源组库记 identity=资源（{h.groups.identities}）")
    _ok(st.get("m3").get("sub") == "新" and st.get("m5").get("sub") == "新",
        "职务态 / 非音乐：账本一分不动")
    again = h._music_asset_pin(apply=True)
    _ok(again["candidates"] == 0 and again["pinned"] == 0, "幂等：再跑零动作")


def main() -> int:
    print("== 标签 ↔ 账本对账（15.2.0）==")
    t1_dry_run()
    h = t2_apply()
    t3_identity_drift()
    t4_skips()
    t5_adopt_reseed()
    t6_tag_only_untouched()
    t7_sub_drift_only_reported()
    t8_music_exempt()
    t9_music_ledger_release()
    t10_music_asset_pin()
    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:  # noqa: BLE001
        print(str(e))
        sys.exit(1)
