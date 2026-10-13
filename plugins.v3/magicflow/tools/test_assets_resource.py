#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 库内资产「资源粒度」离线回归（2026-10-10 Master 口径）。

Master 口径（2026-10-10 17:45）：
  「库内资产这里删的是**资产**——显示的应该是 **resource（资源）的名称**，不是种子的名称；
    删除操作操作的是：**删文件 + 删种 + 包括所有的辅种**。」

本次口径：
  A. ``_asset_rows`` 一行 = **一份资源**（``name`` 是资源名、``members`` 是本体 + 各站全部辅种）；
  B. 资源名优先取「本体（``source_hash``）」那种的标题，否则任一在库种的标题；
  C. ``members_in_qb == 0``（仅账本残留）默认不返回；``include_stale=1`` 才带上（标 ``stale``）；
  D. 资源里**任一**在库成员被硬拦 → 整条 ``deletable=False`` + ``block`` 写明理由（不做「删一半」）；
  E. ``assets_delete`` 收 ``resource_ids``，删除 = 该资源**全部在库成员一次批量删**（不是逐个删）；
  F. 只给了 ``hashes``（旧口径）时，自动反查所属资源（向后兼容）；
  G. 非库内资产的 resource_id 一律拒收；``confirm != 1`` 干跑零写入。

用法：``python3 tools/test_assets_resource.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_assets_test"
CHECKS = 0


def ok(cond, msg):
    global CHECKS
    CHECKS += 1
    if cond:
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        raise SystemExit(1)


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

# 桩 MoviePilot
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

for _modname, _attrs in (
    ("bonus", ("TorrentBonusInfo",)),
    ("fingerprint", ("Entry", "entries_fingerprint", "info_hash", "load_torrent_entries",
                     "total_size", "inner_fingerprint", "fingerprint")),
    ("fetcher", ("SiteCandidateTorrent",)),
    ("qbsync", ("QB_SYNC_INCREMENTAL", "get_qb_sync_store")),
):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    _m.get_qb_sync_store = lambda: None  # noqa: E731
    sys.modules[PKG + "." + _modname] = _m


class _Resp:
    def __init__(self, success=True, message="", data=None):
        self.success = success
        self.message = message
        self.data = data or {}


class _Payload:
    def __init__(self, resource_ids=None, hashes=None, delete_files=0, confirm=0, reason=""):
        self.resource_ids = list(resource_ids or [])
        self.hashes = list(hashes or [])
        self.delete_files = delete_files
        self.confirm = confirm
        self.reason = reason


class _Item:
    def __init__(self, hash="", title="", reason=""):
        self.hash = hash
        self.title = title
        self.reason = reason


_m = types.ModuleType(PKG + ".models")
_m.MagicFlowAssetDeletePayload = _Payload
sys.modules[PKG + ".models"] = _m

_m = types.ModuleType(PKG + ".persistence")
_m.OperationItem = _Item
sys.modules[PKG + ".persistence"] = _m

_load(PKG + ".common", "common.py")
_load(PKG + ".tags", "tags.py")
sys.modules.setdefault("app.schemas", sys.modules["app.schemas"])
# Response：assets.py `from app.schemas import Response` → 用 _Resp 覆盖
sys.modules["app.schemas"].Response = _Resp  # type: ignore[attr-defined]

_t = types.ModuleType(PKG + ".assets_mod")
assets = _load(PKG + ".features.assets", "features/assets.py")


class _FakeGroups(dict):
    def group_of(self, h):
        for gid, rec in self.items():
            if str(h).lower() in {str(x).lower() for x in (rec.get("members") or {})}:
                return gid
        return None


class _FakeDownloader:
    def __init__(self):
        self.calls = []
        self.is_available = True

    def delete_torrents(self, hashes=None, delete_file=False, **_kw):
        self.calls.append((list(hashes or []), bool(delete_file)))
        return len(hashes or []), ""


class _Journal:
    def __init__(self):
        self.rows = []

    def record(self, task_id="", kind="", items=()):
        self.rows.append((task_id, kind, list(items)))


class _Store:
    def __init__(self):
        self.journal = _Journal()


class _Snap:
    """假 qB 快照记录：只有 hash/title/size_gb/state/progress/tags。"""

    def __init__(self, title="", size_gb=0.0, state="uploading", progress=1.0, tags=()):
        self.title = title
        self.size_gb = size_gb
        self.state = state
        self.progress = progress
        self.tags = list(tags)


class Host(assets.AssetsMixin):
    def __init__(self, groups=None, snap=None, ledger=None, gate=None):
        self._groups = _FakeGroups(groups or {})
        self._snap = dict(snap or {})
        self._ledger = dict(ledger or {})
        self._gate = dict(gate or {})
        self._downloader = _FakeDownloader()
        self._store = _Store()
        self.deleted = []

    def _log(self, *_a, **_k):
        return None

    def _tag_groups(self):
        return self._groups

    def _tag_all_torrents(self):
        return self._snap

    def _tag_state(self):
        return self._ledger

    def _delete_gate_detail(self, hashes, snap=None, allow_asset=False):
        return {h: self._gate[h] for h in hashes if h in self._gate}

    def _get_downloader(self, name=""):
        return self._downloader

    def _note_deleted(self, tid, hashes):
        self.deleted.append((tid, list(hashes)))

    def _invalidate_summary(self):
        return None


def _groups_two_members():
    """一份资源：本体 hsrc（site A）+ 辅种 hrep（site B），都在下载器。"""
    return {
        "res-1": {
            "identity": "资源",
            "library": {"in_library": True},
            "source_hash": "hsrc",
            "source_site": "A站",
            "size_gb": 10.0,
            "members": {
                "hsrc": {"site": "A站", "title": "原始种子名"},
                "hrep": {"site": "B站", "title": "辅种名"},
            },
        },
    }


def _snap_two():
    return {"hsrc": _Snap("原始种子名", 10.0), "hrep": _Snap("辅种名", 10.0)}


def main():
    print("A/B/C. 资源粒度归组 + 资源名取本体 + 残留默认隐藏")
    h = Host(groups=_groups_two_members(), snap=_snap_two())
    rows = h._asset_rows()
    ok(len(rows) == 1, "一份资源 → 一行")
    r = rows[0]
    ok(r["resource_id"] == "res-1", "resource_id = group id")
    ok(r["name"] == "原始种子名", "资源名取本体(source_hash)那种的标题")
    ok(r["member_count"] == 2 and r["members_in_qb"] == 2, "members=本体+辅种（2）")
    ok(r["sites"] == ["A站", "B站"], "sites 列出去重站点")
    ok(r["source_site"] == "A站", "source_site = 来源站（供筛选）")
    ok(r["size_gb"] == 10.0, "体积 = 资源体积（一份，不把多站副本相加）")
    ok(r["deletable"] is True, "无闸门 → 可删")

    # 残留：成员不在下载器 → 默认不返回
    h2 = Host(groups=_groups_two_members(), snap={})
    ok(h2._asset_rows() == [], "残留资源默认不返回")
    rows2 = h2._asset_rows(include_stale=True)
    ok(len(rows2) == 1 and rows2[0]["stale"] is True, "include_stale=1 才带上（标 stale）")
    ok("不在下载器" in rows2[0]["block"], "残留行 block 写明理由")

    print("C2. 资源账本没记体积 → 兜底取最大成员体积（不是求和）")
    _g = _groups_two_members()
    _g["res-1"]["size_gb"] = 0
    h2b = Host(groups=_g, snap=_snap_two())
    ok(h2b._asset_rows()[0]["size_gb"] == 10.0, "无 resource 体积 → 取最大成员（10）而非求和（20）")

    print("D. 任一成员被硬拦 → 整条不可删")
    h3 = Host(groups=_groups_two_members(), snap=_snap_two(),
              gate={"hrep": "跨站来源份（H&R 保种期）"})
    r3 = h3._asset_rows()[0]
    ok(r3["deletable"] is False, "含被拦成员 → deletable=False")
    ok("H&R" in r3["block"], "block = 被拦理由")

    print("E. 删除 = 整组一次性批量删（不是逐个）")
    h4 = Host(groups=_groups_two_members(), snap=_snap_two(),
              ledger={"hsrc": {"downloader": "qbittorrent"}, "hrep": {}})
    resp = h4.assets_delete(_Payload(resource_ids=["res-1"], delete_files=1, confirm=1))
    ok(resp.success is True, "删除成功")
    ok(len(h4._downloader.calls) == 1, "只调下载器一次（整组批量）")
    ok(sorted(h4._downloader.calls[0][0]) == ["hrep", "hsrc"], "一次传全部成员 hash")
    ok(h4._downloader.calls[0][1] is True, "delete_file=True 透传")
    ok(resp.data["deleted"] == 1, "按资源计数 deleted=1")

    print("F. 兼容：只给 hashes → 反查所属资源")
    h5 = Host(groups=_groups_two_members(), snap=_snap_two(),
              ledger={"hsrc": {"downloader": "qbittorrent"}, "hrep": {}})
    resp5 = h5.assets_delete(_Payload(hashes=["hrep"], delete_files=0, confirm=1))
    ok(resp5.data["deleted"] == 1, "hash 反查资源并删除")
    ok(sorted(h5._downloader.calls[0][0]) == ["hrep", "hsrc"], "反查后仍是整组删")

    print("G. 非库内资产拒收 / 干跑零写入")
    h6 = Host(groups=_groups_two_members(), snap=_snap_two())
    resp6 = h6.assets_delete(_Payload(resource_ids=["nope"], confirm=1))
    ok(resp6.data["results"][0]["block"] == "不是库内资产", "未知 resource_id 拒收")
    ok(h6._downloader.calls == [], "拒收 → 不碰下载器")

    h7 = Host(groups=_groups_two_members(), snap=_snap_two())
    resp7 = h7.assets_delete(_Payload(resource_ids=["res-1"], delete_files=1, confirm=0))
    ok(h7._downloader.calls == [], "干跑零写入")
    ok(h7.deleted == [], "干跑不写冷却账")
    ok(h7._store.journal.rows == [], "干跑不写 journal")
    ok("将删除该资源全部 2 个种及文件" in resp7.data["results"][0]["message"], "干跑回执按资源描述")

    print(f"\n全部通过（{CHECKS} 断言）")


if __name__ == "__main__":
    main()
