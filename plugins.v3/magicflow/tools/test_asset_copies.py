#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 「副本跟随资源身份」离线回归（★ 13.0.0，真跑 tags.py / silent.py / assets.py）。

背景（Master 2026-10-07 00:24「辅种应该按资源的身份打标签啊，资源的就应该打资源标签啊」）：
同一份内容多站各挂一份（辅种副本），副本**自己的**种子记录往往是「新」，但它的**资源**
早就是库内资产 —— 只看种子记录会把这些副本当垃圾清掉（当晚实测误删 10 个他站辅种份）。

本测试锁三件事：
  1) ``tags.asset_member_hashes`` / ``resource_asset_hash`` / ``resource_is_asset``：
     资源成员/资源身份 → 资产判定；``asset_recheck=fail``（已降级）不再享受；
  2) ``SilentMixin._silent_audit``：副本（成员 或 同保存目录/种名）→ 归类 ``library_asset``（永不删），
     无关的静默-新 仍是 ``cleanup``；
  3) ``AssetsMixin.sync_tag_assets``：副本的 qB 标签被改写成「静默-资源」。

用法：``python3 tools/test_asset_copies.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_asset_copies_test"


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

fingerprint = _load(PKG + ".fingerprint", "fingerprint.py")
persistence = _load(PKG + ".persistence", "persistence.py")
tags = _load(PKG + ".tags", "tags.py")
common = _load(PKG + ".common", "common.py")
downloader_ops = _load(PKG + ".downloader_ops", "downloader_ops.py")
silent = _load(PKG + ".features.silent", "features/silent.py")
assets = _load(PKG + ".features.assets", "features/assets.py")

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


ASSET_HASH = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"   # 资产份（财神）
COPY_HASH = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"   # 副本（聆音）：自己的记录是「新」
OTHER_HASH = "cccccccccccccccccccccccccccccccccccccccc"  # 无关的静默-新
DIR = "/media/Some.Release.2026.1080p-GRP"


class _Groups:
    """最小资源账本桩（ResourceLedgerStore 的 items/group_of）。"""

    def __init__(self, data, fail=()):
        self._d = dict(data or {})
        self._fail = set(fail or ())

    def items(self):
        return {k: dict(v) for k, v in self._d.items()}

    def group_of(self, h):
        hh = str(h or "").strip().lower()
        for gid, rec in self._d.items():
            if hh in ((rec.get("members") or {})):
                return gid
        return ""

    def members_of(self, gid):
        return list(((self._d.get(gid) or {}).get("members") or {}).keys())


def _groups_asset(fail: bool = False) -> _Groups:
    rec = {"identity": "资源", "library": {"in_library": True},
           "members": {ASSET_HASH: {"fp": "f" * 40}}}
    if fail:
        rec["asset_recheck"] = "fail"
    return _Groups({"fp:" + "f" * 40: rec})


def _torrent(h, name=DIR.rsplit("/", 1)[-1], save="/media", state="pausedUP", tags=None):
    # ★ 与真 TorrentInfo 同形：**没有 name 字段**；数据路径 = content_path
    return types.SimpleNamespace(hash=h, title=name, state=state, tags=list(tags or []),
                                 size=1 << 30, progress=1.0, save_path=save,
                                 content_path=f"{save}/{name}")


class _Ledger:
    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)

    def get(self, h):
        return self._d.get(str(h or "").lower()) or {}

    def put(self, h, patch):
        self._d[str(h or "").lower()] = dict(patch or {})

    def drop(self, h):
        self._d.pop(str(h or "").lower(), None)

    def set_asset(self, h, *, sub=""):
        hh = str(h or "").lower()
        rec = dict(self._d.get(hh) or {})
        if rec.get("sub") == sub:
            return False
        rec["sub"] = sub
        self._d[hh] = rec
        return True


class _DL:
    def __init__(self, h):
        self.h = h

    def replace_torrent_tags(self, hh, new_tags):
        self.h.tag_writes.append((hh, list(new_tags)))
        return True


class H(silent.SilentMixin, assets.AssetsMixin):
    """静默分拣 + 资产标记两套逻辑的桩宿主（分类输入可控）。"""

    def __init__(self, groups, snap, ledger):
        self._groups = groups
        self.torrents = dict(snap)
        self.ledger = dict(ledger)
        self.tag_writes = []
        self._tags_cfg = {"enabled": True, "host_interval": 60}

    # —— 桩依赖 ——
    def _tag_groups(self):
        return self._groups

    def _tag_state(self):
        return _Ledger(self.ledger)

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _get_downloader(self, name="qbittorrent"):
        return _DL(self)

    def _crossseed_source_hashes(self):
        return set()

    def _claim_protected_hashes(self):
        return set()

    def _torrent_site_name(self, tg, fallback=""):
        return "聆音"

    def _hr_obligation(self, site, torrent, snap=None):
        return (False, 24.0, 0.0, "test")

    def _log(self, msg, level=None):
        pass

    def get_data_path(self):
        return ROOT


def _silent_rec(state="静默", sub="新", site="聆音"):
    return {"state": state, "sub": sub, "site": site, "size_gb": 100.0}


def main() -> None:
    from dataclasses import fields as _fields
    _cols = {f.name for f in _fields(downloader_ops.TorrentInfo)}
    _ok("name" not in _cols, "真 TorrentInfo 无 name 字段（取 .name 必空 → 曾致共用判据失效）")
    _ok("content_path" in _cols, "真 TorrentInfo 有 content_path（共用/同数据判据的真值字段）")

    print("== 1) 判据：副本跟随资源身份 ==")
    g = _groups_asset()
    _ok(tags.resource_is_asset(g, "fp:" + "f" * 40) is True, "资源（in_library）→ 资产")
    _ok(tags.resource_asset_hash(g, ASSET_HASH) is True, "资产份本身 → 资产")
    _ok(tags.resource_asset_hash(g, COPY_HASH) is False, "非成员 → 不是资产（靠成员表判不了的就别判）")
    _ok(tags.resource_asset_hash(g, COPY_HASH, {"sub": "新"}) is False, "副本自己不写资产标也不算")
    _ok(tags.asset_member_hashes(g) == {ASSET_HASH}, "成员表 = {资产份}")
    gf = _groups_asset(fail=True)
    _ok(tags.resource_is_asset(gf, "fp:" + "f" * 40) is False, "asset_recheck=fail（已降级）→ 不再享受")
    _ok(tags.asset_member_hashes(gf) == set(), "降级资源的成员不进保护清单")

    print("== 2) 静默盘点：副本 → library_asset（永不删） ==")
    h = H(g, {ASSET_HASH: _torrent(ASSET_HASH),
              COPY_HASH: _torrent(COPY_HASH),
              OTHER_HASH: _torrent(OTHER_HASH, name="Unrelated.Release", save="/movie/刷流")},
          {ASSET_HASH: _silent_rec(sub="资源"),
           COPY_HASH: _silent_rec(sub="新"),                     # ★ 副本自己的身份是「新」
           OTHER_HASH: _silent_rec(sub="新")})
    audit = h._silent_audit(limit=0)
    cls = {it["hash"]: it["class"] for it in audit["items"]}
    _ok(cls.get(ASSET_HASH) == "library_asset", "资产份 → library_asset")
    _ok(cls.get(COPY_HASH) == "library_asset", "★ 副本（同资源成员）→ library_asset（不再当清理候选）")
    _ok(cls.get(OTHER_HASH) == "cleanup", "无关静默-新 → 仍是清理候选")
    _ok(audit["counts"]["library_asset"] == 2, "库内资产计数 2（资产份 + 副本）")

    print("== 2b) 同保存目录/种名（成员表没记上）也按资产 ==")
    g2 = _Groups({})                                            # 空资源账本：成员表看不到副本
    h2 = H(g2, {ASSET_HASH: _torrent(ASSET_HASH),
                COPY_HASH: _torrent(COPY_HASH)},                # 两份同目录同名
          {ASSET_HASH: _silent_rec(sub="资源"), COPY_HASH: _silent_rec(sub="新")})
    tags.asset_member_hashes  # noqa: B018  （保持引用，便于阅读）
    h2._groups = _Groups({})                                    # 不给成员表
    # 没有成员表时，用「资产份的目录」兜底：资产份自己仍然是资产 → 其目录进 key 集合
    audit2 = h2._silent_audit(limit=0)
    cls2 = {it["hash"]: it["class"] for it in audit2["items"]}
    _ok(cls2.get(ASSET_HASH) == "library_asset", "资产份（sub=资源）→ 资产")
    _ok(cls2.get(COPY_HASH) == "library_asset", "★ 同目录副本 → 资产（目录/种名兜底）")

    print("== 3) 资产标记刷新：副本标签改成「静默-资源」 ==")
    h3 = H(_groups_asset(),
           {ASSET_HASH: _torrent(ASSET_HASH, tags=["魔流-财神-静默-资源"]),
            COPY_HASH: _torrent(COPY_HASH, tags=["魔流-聆音-静默-新"])},
           {ASSET_HASH: _silent_rec(sub="资源"), COPY_HASH: _silent_rec(sub="新")})
    rep = h3.sync_tag_assets(apply=True)
    written = {hh: tg for hh, tg in h3.tag_writes}
    _ok(COPY_HASH in written, "★ 副本的 qB 标签被改写")
    _ok("魔流-聆音-静默-资源" in (written.get(COPY_HASH) or []), "副本标签 = 魔流-聆音-静默-资源")
    _ok("魔流-聆音-静默-新" not in (written.get(COPY_HASH) or []), "旧「静默-新」已摘掉")
    _ok(rep.get("tag_synced", 0) >= 1, "报表记 tag_synced ≥ 1")
    _ok(h3.ledger.get(COPY_HASH, {}).get("sub") == "资源", "账本身份同步为「资源」")
    _ok(ASSET_HASH not in written, "已是「资源」的份不重复写 qB")

    print(f"\n✅ PASS —— 共 {CHECKS} 项全过")


if __name__ == "__main__":
    main()
