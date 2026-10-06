#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 静默池「清理（删除）」离线回归（★ 13.0.0，真跑 silent.py，不需 MoviePilot）。

复用 ``tools/test_silent_hr_split.py`` 的加载脚手架（stub app.* + 真 silent.py）。

覆盖 ``_silent_purge(confirm, batch, site)``：
  1) 干跑（confirm=0）：只出计划，**零写入**（下载器无 pause/delete、账本不动）；
  2) 真写（confirm=1）：① 先补 pause 违背不变量的；② 只删「闸门放行」的清理候选
     （**删条目 + 删文件**，``delete_file=True``）；③ 被闸门拦的（如库内资产）**不删**且单列；
     ④ 删成功的从账本摘掉（``drop``）；
  3) ``site`` 过滤：只动指定站的种；
  4) ``batch`` 上限：每批最多删 N 个；
  5) ``sub`` 过滤：只动指定身份；
  6) Release 目录共用：同 save_path/name 另有完成种 → ``delete_file=False``（只删条目，计 ``torrent_only``）；
     无共用 → ``delete_file=True``。

用法：``python3 tools/test_silent_purge.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_silent_purge_test"


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


def _torrent(h, site="", state="pausedUP", size=1 << 30, title=None):
    import types
    # ★ 与真 TorrentInfo 同形：**没有 name 字段**（qB 的 name → title），数据路径走 content_path
    _nm = title or h
    return types.SimpleNamespace(hash=h, title=_nm, state=state, size=size, tags=[],
                                 progress=1.0, save_path="/x", content_path=f"/x/{_nm}")


class _Ledger:
    """最小种子账本桩（items/get/put/drop）。"""

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


class Harness(silent.SilentMixin):
    """在真 SilentMixin 上挂桩：分类与闸门的输入可控，测「清理（删除）」编排。"""

    def __init__(self, audit_items, gate_blocked=None, snap=None):
        self._audit_items = list(audit_items)
        self._gate_blocked = dict(gate_blocked or {})
        self.torrents = dict(snap or {})
        self.ledger = {str(h): {} for h in (snap or {})}
        self._tags_cfg = {"host_interval": 60}
        self.paused_calls = []
        self.delete_calls = []

    # —— 覆盖：分类结果固定（测清理编排，不测分类本身）——
    def _silent_audit(self, limit: int = 0):
        return {"items": list(self._audit_items)}

    # —— 覆盖：闸门只拦指定 hash ——
    def _delete_gate_detail(self, hashes, force_error=None, snap=None):
        return {h: self._gate_blocked[h] for h in hashes if h in self._gate_blocked}

    # —— 桩依赖 ——
    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _tag_state(self):
        return _Ledger(self.ledger)

    def _get_downloader(self, name="qbittorrent"):
        return _DL(self)

    def _silent_pause_gate(self, hashes):
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        self.paused_calls.extend(hs)
        return {"paused": len(hs)}

    def _journal_deletions(self, by_task, log_prefix=""):
        self.journal = by_task

    def _log(self, msg, level=None):
        pass

    def get_data_path(self):
        return ROOT

    def _torrent_site_name(self, tags, fallback=""):
        return "s1"

    def _hrbills_store(self):
        return None

    def _hr_obligation(self, site, torrent, snap=None):
        return (False, 24.0, 100.0, "test")

    def _tag_groups(self):
        class _G:
            def group_of(self, h):
                return ""

            def items(self):
                return {}
        return _G()

    def _crossseed_source_hashes(self):
        return set()

    def _claim_protected_hashes(self):
        return set()

    def _site_domain_by_name(self, name):
        return ""

    def _deletions_log_path(self):
        return ROOT / "deletions.jsonl"


class _DL:
    def __init__(self, h):
        self.h = h

    def pause_torrents(self, hs):
        self.h.paused_calls.extend(list(hs))
        return len(list(hs)), None

    def delete_torrents(self, hashes, delete_file=False, reason="", source=""):
        hs = [hashes] if isinstance(hashes, str) else list(hashes or [])
        self.h.delete_calls.append((list(hs), bool(delete_file)))
        return len(hs), None


def _items():
    return [
        {"hash": "aaa1", "site": "s1", "class": "relocate", "stalled_violation": True},
        {"hash": "aaa2", "site": "s1", "class": "relocate", "stalled_violation": False},
        {"hash": "bbb1", "site": "s2", "class": "relocate", "stalled_violation": False},
        {"hash": "ccc1", "site": "s1", "class": "library_asset", "stalled_violation": False},
        {"hash": "ddd1", "site": "s1", "class": "owed_hr", "stalled_violation": True},
        {"hash": "eee1", "site": "s1", "class": "relocate", "stalled_violation": False},  # 不在下载器
    ]


def _snap():
    d = {h: _torrent(h) for h in ("aaa1", "aaa2", "bbb1", "ccc1", "ddd1")}
    return d


def main() -> int:
    print("=" * 64)
    print("魔流 · 13.0.0 静默池清理（删除）回归测试")
    print("=" * 64)

    # ---- ① 干跑：零写入 ----
    print("\n[1] 干跑（confirm=0）：只出计划、零写入")
    h = Harness(_items(), gate_blocked={"aaa2": "库内资产（已入库，永不删）"}, snap=_snap())
    rep = h._silent_purge(confirm=0)
    _ok(rep["counts"]["delete"] == 3, f"清理候选 3（{rep['counts']}）")
    _ok(rep["counts"]["keep"] == 2, "保护类 2（library_asset + owed_hr）")
    _ok(rep["counts"]["missing"] == 1, "不在下载器 1（eee1）")
    _ok(rep["counts"]["pause"] == 2, "补 pause 计数 2（aaa1 + ddd1）")
    _ok(h.delete_calls == [] and h.paused_calls == [], "干跑：下载器零调用")
    _ok("plan_truncated" in rep, "带 plan_truncated 字段")
    _ok(rep["blocked"] == 1 and any(b["hash"].startswith("aaa2") for b in rep["blocked_items"]),
        "干跑也预检闸门（拦下的单列，供干跑评审）")

    # ---- ② 真写：补 pause + 删条目删文件 + 闸门拦截单列 ----
    print("\n[2] 真写（confirm=1）：补 pause + 删条目删文件 + 闸门拦截单列")
    h = Harness(_items(), gate_blocked={"aaa2": "库内资产（已入库，永不删）"}, snap=_snap())
    rep = h._silent_purge(confirm=1)
    _ok(sorted(h.paused_calls) == ["aaa1", "ddd1"], f"补 pause 覆盖全部 stalled（{h.paused_calls}）")
    _del = [x[0][0] for x in h.delete_calls]
    _ok(sorted(_del) == ["aaa1", "bbb1"], f"只删闸门放行的 2 个（{_del}）")
    _ok(all(x[1] is True for x in h.delete_calls), "全部 delete_file=True（删条目+删文件，无共用目录）")
    _ok(rep["torrent_only"] == 0, f"无共用目录 → torrent_only=0（{rep['torrent_only']}）")
    _ok(rep["deleted"] == 2 and rep["blocked"] == 1, f"deleted=2 / blocked=1（{rep['deleted']}/{rep['blocked']}）")
    _ok(any(b["hash"].startswith("aaa2") for b in rep["blocked_items"]), "被拦的 aaa2 单列在 blocked_items")
    _ok("aaa1" not in h.ledger and "bbb1" not in h.ledger, "删成功的从账本摘掉（drop）")
    _ok("ccc1" in h.ledger, "被拦的仍在账本里")

    # ---- ③ site 过滤 ----
    print("\n[3] site 过滤：只动指定站")
    h = Harness(_items(), snap=_snap())
    rep = h._silent_purge(confirm=1, site="s2")
    _ok(rep["counts"]["delete"] == 1, f"只 s2 的 1 个候选（{rep['counts']}）")
    _ok([x[0][0] for x in h.delete_calls] == ["bbb1"], "只删 s2 的 bbb1")

    # ---- ④ batch 上限 ----
    print("\n[4] batch 上限")
    h = Harness(_items(), snap=_snap())
    rep = h._silent_purge(confirm=1, batch=1)
    _ok(len(h.delete_calls) == 1, f"batch=1 → 只删 1 个（实删 {len(h.delete_calls)}）")
    _ok(rep["plan_truncated"] == 2, f"计划被截断 2 个（{rep['plan_truncated']}）")

    # ---- ⑤ sub 过滤 ----
    print("\n[5] sub 过滤：只动指定身份")
    h = Harness([
        {"hash": "p1", "site": "s1", "class": "relocate", "sub": "普通"},
        {"hash": "n1", "site": "s1", "class": "relocate", "sub": "新"},
    ], snap={"p1": _torrent("p1"), "n1": _torrent("n1")})
    rep = h._silent_purge(confirm=1, sub="普通")
    _ok([x[0][0] for x in h.delete_calls] == ["p1"], "sub=普通 只删 p1（静默-新不碰）")
    _ok(rep["counts"]["delete"] == 1 and rep["counts"]["keep"] == 0, "范围外的静默-新不算候选/保护")

    # ---- ⑥ Release 目录共用：只删条目 vs 删文件 ----
    print("\n[6] Release 目录共用：同 path 另有完成种 → 只删条目；无共用 → 删文件")
    h = Harness([
        {"hash": "aaa2", "site": "s1", "class": "relocate", "sub": "普通"},
        {"hash": "bbb1", "site": "s1", "class": "relocate", "sub": "普通"},
    ], snap={
        "aaa1": _torrent("aaa1", title="same"),   # 已完成、同 path 的另一个种
        "aaa2": _torrent("aaa2", title="same"),   # 待删、同 path
        "bbb1": _torrent("bbb1", title="diff"),   # 待删、无共用
    })
    rep = h._silent_purge(confirm=1)
    _ok(rep["deleted"] == 2 and rep["torrent_only"] == 1,
        f"删 2 个、只删条目 1 个（{rep['deleted']}/{rep['torrent_only']}）")
    dmap = {x[0][0]: x[1] for x in h.delete_calls}
    _ok(dmap.get("aaa2") is False, "同 path 另有完成种 → delete_file=False（只删条目）")
    _ok(dmap.get("bbb1") is True, "无共用 → delete_file=True（删条目+删文件）")

    # ---- ⑦ 边界：候选先于同 path 活动种出现（snap 顺序无关）→ 仍只删条目 ----
    print("\n[7] 边界：候选先于同 path 活动种出现，仍只删条目（set 判据不受顺序影响）")
    h = Harness([
        {"hash": "aaa2", "site": "s1", "class": "relocate", "sub": "普通"},
    ], snap={
        "aaa2": _torrent("aaa2", title="same"),   # 待删（先出现）
        "aaa1": _torrent("aaa1", title="same"),   # 同 path 的活动种（后出现，不在候选）
    })
    rep = h._silent_purge(confirm=1)
    _ok(rep["deleted"] == 1 and rep["torrent_only"] == 1,
        f"删 1 个、只删条目 1 个（{rep['deleted']}/{rep['torrent_only']}）")
    _ok(h.delete_calls[0][1] is False, "候选先出现，同 path 另有完成种 → delete_file=False（不砸活动种数据）")

    print("\n" + "=" * 64)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
