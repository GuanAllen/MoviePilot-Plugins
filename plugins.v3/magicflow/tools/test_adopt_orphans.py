#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 「孤儿种纳管」离线回归（★ 19.8.0，真跑 features/assets.py）。

背景（2026-10-25 真机）：插件库被 DROP 重建后，qB 里仍有 229 个只带
``魔流-<站>-静默-<身份>`` 标签、账本 ``mf_seed`` 里没有行的种（3.67TB）。
标签是账本的镜像 ⇒ 账本被清后标签就是唯一幸存的现场事实，
``AssetsMixin.adopt_tag_only_seeds`` 按它把账本补回来（补行 → 补特征码 →
sync_resources 建资源 → 身份回写资源）。本测试锁：

  1) 只认**静默**标签：在岗（刷流/魔力/保种/点播）的种一律跳过、账本已有行不动；
  2) 干跑（apply=False）**一个写调用都不能有**；
  3) apply 时：账本补行拿到 site/state=静默/身份；强特征码才写 fp（弱码计 fp_fail）；
  4) ``sync_resources`` 只调一次（复用唯一实现，不另造真值源）；
  5) 身份回写：资源/普通 走 ``set_identity``；新 走 ``store.put`` 触发的资源真列；
     音乐线（分类=音乐）身份恒为「资源」（15.8.11）；
  6) 找不到资源组（无强特征码）→ 计 ``no_group``，不抛异常。

用法：``python3 tools/test_adopt_orphans.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_adopt_orphans_test"


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
                         ("fetcher", ("SiteCandidateTorrent",)),
                         ("fingerprint", ("Entry", "entries_fingerprint", "info_hash", "load_torrent_entries",
                                    "total_size", "inner_fingerprint", "fingerprint")),
                         ("qbsync", ("QB_SYNC_INCREMENTAL", "get_qb_sync_store"))):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    _m.get_qb_sync_store = lambda: None  # noqa: E731
    sys.modules[PKG + "." + _modname] = _m

# assets.py 的其它模块级依赖：只用到不动行为的符号，桩掉以免拉起 pydantic / sqlalchemy
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
assets = _load(PKG + ".features.assets", "features/assets.py")

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


RES = "a" * 40      # 静默-资源（强特征码）
PLAIN = "b" * 40    # 静默-普通（强特征码）
NEW = "c" * 40      # 静默-新（强特征码）
NFP = "d" * 40      # 静默-资源但取不到特征码
DUTY = "e" * 40     # 在岗（魔力）→ 必须跳过
MUSIC = "f" * 40    # 音乐线：标签写普通，身份必须钉成资源
KNOWN = "9" * 40    # 账本已有行 → 必须不动


def _t(h, tags_list, *, category="", size=1.5):
    return types.SimpleNamespace(hash=h, title=f"T-{h[:4]}", state="pausedUP",
                                 tags=list(tags_list), size=int(size * (1 << 30)),
                                 size_gb=size, progress=1.0, category=category,
                                 save_path="/media", content_path=f"/media/T-{h[:4]}")


class _Store:
    def __init__(self, d):
        self._d = {k: dict(v) for k, v in (d or {}).items()}
        self.puts = []

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


class _Groups:
    def __init__(self, m):
        self._m = dict(m or {})
        self.ids = []

    def group_of(self, h):
        return self._m.get(str(h or "").lower(), "")

    def set_identity(self, gid, sub, by=""):
        self.ids.append((gid, sub, by))
        return True


class _DL:
    def __init__(self, fps):
        self._fps = dict(fps or {})

    def get_torrent_fingerprint(self, h):
        return self._fps.get(str(h or "").lower(), "")


class _Fake(feature_tags.TagsMixin, assets.AssetsMixin):
    def __init__(self, snap, ledger, groups, dl):
        self._snap = snap
        self._store = _Store(ledger)
        self._groups = groups
        self._dl = dl
        self.synced = 0
        self.backfilled = 0

    def _tag_all_torrents(self):
        return self._snap

    def _tag_state(self):
        return self._store

    def _tag_groups(self):
        return self._groups

    def _get_downloader(self):
        return self._dl

    def backfill_fingerprints(self, *, limit=0):
        """桩：真实现只补「账本里有、缺强码」的种，并在补到码时 sync_resources。"""
        self.backfilled += 1
        got = fail = 0
        led = self._store.items()
        for h in self._snap:
            if h not in led or led[h].get("fp"):
                continue
            fp = self._dl.get_torrent_fingerprint(h)
            if fp and not self._store.get(h).get("fp"):
                self._store.put(h, {"fp": fp})
                got += 1
            elif not fp:
                fail += 1
        if got:
            self.sync_resources(apply=True)
        return {"ok": True, "checked": got + fail, "got": got, "failed": fail}

    def sync_resources(self, *, apply=False):
        self.synced += 1
        return {"resources": 3, "apply": bool(apply)}


def main() -> int:
    snap = {
        RES: _t(RES, ["魔流-财神-静默-资源", "魔流-辅种"]),
        PLAIN: _t(PLAIN, ["魔流-聆音-静默-普通"]),
        NEW: _t(NEW, ["魔流-学校-静默-新"]),
        NFP: _t(NFP, ["魔流-财神-静默-资源"]),
        DUTY: _t(DUTY, ["魔流-财神-魔力", "魔流-财神-静默-资源"]),
        MUSIC: _t(MUSIC, ["魔流-CARPT-静默-普通"], category="音乐"),
        KNOWN: _t(KNOWN, ["魔流-财神-静默-资源"]),
        "8" * 40: _t("8" * 40, ["MOVIEPILOT"]),          # 非魔流种 → 不猜
    }
    ledger = {KNOWN: {"site": "财神", "state": "静默", "sub": "资源"}}
    groups = _Groups({RES: "fp:" + "1" * 40, PLAIN: "fp:" + "2" * 40, NEW: "fp:" + "3" * 40,
                      MUSIC: "fp:" + "4" * 40})
    dl = _DL({RES: "1" * 40, PLAIN: "2" * 40, NEW: "3" * 40, MUSIC: "4" * 40})

    print("① 干跑：只统计候选，不写账本、不建资源")
    dry = _Fake(snap, ledger, groups, dl)
    d = dry.adopt_tag_only_seeds(apply=False)
    _ok(d["candidates"] == 5, f"候选 5（资源/普通/新/无码/音乐）→ {d['candidates']}")
    _ok(d["skipped_duty"] == 1, f"在岗（魔力）跳过 1 → {d['skipped_duty']}")
    _ok(d["tag_only"] == 5, f"带静默身份的孤儿 5 → {d['tag_only']}")
    _ok(not dry._store.puts, "干跑没有一次账本写")
    _ok(dry.synced == 0, "干跑不建资源")

    print("② apply：补行 → 补特征码 → 建资源 → 身份回写")
    f = _Fake(snap, ledger, groups, dl)
    r = f.adopt_tag_only_seeds(apply=True)
    _ok(r["adopted"] == 5, f"补行 5 → {r['adopted']}")
    _ok(f.synced == 1, f"sync_resources 恰好 1 次 → {f.synced}")
    _ok(r["fp_ok"] == 4 and r["fp_fail"] == 2,
        f"特征码 4 成功 / 2 失败（含账本既有的缺码行）→ {r['fp_ok']}/{r['fp_fail']}")
    _ok(all(h != KNOWN for h, _ in f._store.puts), "账本已有行不动（不覆盖）")
    _ok(all(h != DUTY for h, _ in f._store.puts), "在岗种不接管")

    row = [p for h, p in f._store.puts if h == RES][0]
    _ok(row.get("site") == "财神" and row.get("state") == "静默" and row.get("sub") == "资源",
        f"资源行补成 财神/静默/资源 → {row.get('site')}/{row.get('state')}/{row.get('sub')}")
    _ok(any(h == RES and p.get("fp") == "1" * 40 for h, p in f._store.puts),
        "强特征码落进 fp（→ mf_seed.resource_id）")
    _ok(not any(h == NFP and p.get("fp") for h, p in f._store.puts),
        "取不到特征码的种不写 fp（弱身份不冒充）")

    ids = dict((gid, sub) for gid, sub, _by in f._groups.ids)
    _ok(ids.get("fp:" + "1" * 40) == "资源", f"资源身份回写 → {ids.get('fp:' + '1' * 40)}")
    _ok(ids.get("fp:" + "2" * 40) == "普通", f"普通身份回写 → {ids.get('fp:' + '2' * 40)}")
    _ok(ids.get("fp:" + "4" * 40) == "资源", "音乐线身份恒为资源（15.8.11）")
    _ok(all(by == "recover" for _g, _s, by in f._groups.ids), "身份来源标记为 recover")
    _ok(any(h == NEW and p.get("sub") == "新" for h, p in f._store.puts),
        "「新」走 put（由 _touch_resource 落资源真列）")
    _ok(r["identity_resource"] == 2 and r["identity_plain"] == 1 and r["identity_new"] == 1,
        f"身份计数 资源{r['identity_resource']}/普通{r['identity_plain']}/新{r['identity_new']}")

    print("③ 无资源组（弱码 / 取不到特征码）只计数，不抛异常")
    g2 = _Groups({})
    f2 = _Fake({NFP: snap[NFP]}, {}, g2, _DL({}))
    r2 = f2.adopt_tag_only_seeds(apply=True)
    _ok(r2["no_group"] == 1, f"无组计 1 → {r2['no_group']}")
    _ok(not r2["errors"], f"无异常 → {r2['errors']}")

    print("④ limit 只处理前 N 个")
    f3 = _Fake(snap, ledger, groups, dl)
    r3 = f3.adopt_tag_only_seeds(apply=True, limit=2)
    _ok(r3["adopted"] == 2 and len(f3._store.puts) >= 2, f"limit=2 只补 2 行 → {r3['adopted']}")

    print(f"\n✅ PASS（{CHECKS} 项断言）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as err:  # noqa: BLE001
        print(str(err))
        sys.exit(1)
