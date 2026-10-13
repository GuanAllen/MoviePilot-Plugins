#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 音乐线（★ 15.9.0）离线回归 —— 真跑 features/musicgrab.py，不需 MoviePilot / qB。

覆盖（Master 2026-10-10 14:29 转向后的新流程：**search(cid) → AI 选 → download(cids)**）：
  [1] ``_music_cid``：稳定 12 位 hex；站点/链接不同 → 不同；
  [2] 候选缓存 put/get + TTL 过期；
  [3] ``_music_cand_public``：带 cid，**不带** enclosure/cookie/ua/page_url；dv=0.0→free，dv=1.0→非 free；
  [4] ``_music_row_from_ti``：对象归一（含 uploadvolumefactor）；无 enclosure → None；
  [5] ``_music_item_row``：downloading / resource / settling / gone 四态 + percent/downloaded_gb/eta；
  [6] ``_music_items``：在库+历史单列表、同 hash 去重、totals、limit 上限；
  [7] ``_music_act``：缺 hash / 未知动作 / 不在下载器 / 非音乐线 拒绝；pause 走 dl；remove 被闸门拦 → blocked；
  [8] ``_music_download_cids``：未知 cid → failed；已知 cid → 按选择加种（回执/汇总）。

用法：``python3 tools/test_agent_music.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_music_test"


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
_load(PKG + ".persistence", "persistence.py")
# fingerprint 可能依赖 MP；只提供 info_hash 桩
_fp = types.ModuleType(PKG + ".fingerprint")
_fp.info_hash = lambda *_a, **_k: ""
sys.modules[PKG + ".fingerprint"] = _fp

musicgrab = _load(PKG + ".features.musicgrab", "features/musicgrab.py")
MusicMixin = musicgrab.MusicGrabMixin
SUB_RESOURCE = tags.SUB_RESOURCE

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


class _Journal:
    def __init__(self, recs):
        self._recs = list(recs)

    def list_recent(self, limit=100, kind=None):
        return self._recs[:limit]


class _Ledger:
    def __init__(self, d):
        self._d = d

    def get(self, h):
        return self._d.get(str(h or "").lower())


class Fake(MusicMixin):
    def __init__(self, snap=None, ledger=None, journal=None, downloader=None):
        self._snap = dict(snap or {})
        self._ledger = dict(ledger or {})
        self._store = SimpleNamespace(journal=_Journal(journal or []))
        self._dl = downloader
        self._music_line_hashes = None  # None=按 _is_music_line；set=白名单

    def _tag_all_torrents(self):
        return dict(self._snap)

    def _tag_state(self):
        return _Ledger(self._ledger)

    def _ondemand_seed_rec(self, h):
        return self._ledger.get(str(h or "").lower()) or {}

    def _is_music_line(self, obj):
        if self._music_line_hashes is not None:
            return bool(getattr(obj, "is_music", True))
        return bool(getattr(obj, "is_music", True))

    def _get_downloader(self, kind="qbittorrent"):
        return self._dl

    def _log(self, *a, **k):
        pass

    def _music_grab_one(self, row, save_path, existing=None):
        h = str(row.get("hash") or ("h" * 40))
        return {"ok": True, "hash": h}


class _DL:
    is_available = True

    def __init__(self):
        self.calls = []

    def pause_torrents(self, hashes):
        self.calls.append(("pause", list(hashes)))
        return (len(hashes), None)

    def resume_torrents(self, hashes):
        self.calls.append(("resume", list(hashes)))
        return (len(hashes), None)

    def delete_torrents(self, hashes=None, delete_file=True, reason="", source=""):
        self.calls.append(("delete", list(hashes or [])))
        return (0, "blocked: 欠 H&R")


def _qbt(progress=0.0, state="downloading", size_gb=10.0, speed=0.0, ratio=1.0,
         title="t", is_music=True, dv=None, save_path="/vol6/1000/music"):
    kw = dict(progress=progress, state=state, size_gb=size_gb, download_speed=speed,
              ratio=ratio, title=title, is_music=is_music, save_path=save_path,
              hit_and_run=False)
    if dv is not None:
        kw["downloadvolumefactor"] = dv
    return SimpleNamespace(**kw)


def _op(h, title, ts=1000.0, reason="源 馒头·免费", source="music"):
    return SimpleNamespace(operation_id=h[:8], created_at=ts,
                           items=[SimpleNamespace(hash=h, title=title, reason=reason,
                                                  source=source, size_gb=3.0)])


def _item(h, title, reason="\u6e90 \u9992\u5934\u00b7\u514d\u8d39", source="music"):
    return SimpleNamespace(hash=h, title=title, reason=reason, source=source, size_gb=3.0)


def _rec(ts):
    return SimpleNamespace(created_at=ts, items=[])


def _iso(s):
    try:
        return datetime.fromisoformat(str(s)).timestamp()
    except Exception:  # noqa: BLE001
        return None


H1 = "a" * 40
H2 = "b" * 40
H3 = "c" * 40


print("[1] cid 稳定性")
c1 = MusicMixin._music_cid({"site": 16, "enclosure": "http://x/1.torrent"})
c2 = MusicMixin._music_cid({"site": 16, "enclosure": "http://x/1.torrent"})
c3 = MusicMixin._music_cid({"site": 16, "enclosure": "http://x/2.torrent"})
c4 = MusicMixin._music_cid({"site": 7, "enclosure": "http://x/1.torrent"})
ok(c1 == c2, "同站同链接 → cid 稳定")
ok(len(c1) == 12 and all(ch in "0123456789abcdef" for ch in c1), "cid=12 位 hex")
ok(c1 != c3 and c1 != c4, "链接/站点不同 → cid 不同")

print("[2] 候选缓存 put/get + TTL")
f = Fake()
f._music_cand_put("aa", {"title": "x", "site": 1})
ok(f._music_cand_get("aa") == {"title": "x", "site": 1}, "put→get 命中")
ok(f._music_cand_get("zz") is None, "不存在 → None")
_ttl = musicgrab.MUSIC_CAND_TTL
musicgrab.MUSIC_CAND_TTL = -1
ok(f._music_cand_get("aa") is None, "过期 → None（并清键）")
musicgrab.MUSIC_CAND_TTL = _ttl

print("[3] 候选对外投影（防凭据外泄 + 免费真值）")
pub = MusicMixin._music_cand_public({
    "cid": "abc123", "title": "T", "site": 16, "site_name": "YemaPT",
    "size": 1073741824.0, "seeders": 2, "downloadvolumefactor": 0.0, "uploadvolumefactor": 1.0,
    "hit_and_run": False, "score": 75, "excluded": False, "exclude_reason": "",
    "enclosure": "SECRET", "site_cookie": "COOKIE", "site_ua": "UA", "page_url": "P",
})
ok(pub["cid"] == "abc123" and pub["free"] is True, "dv=0.0 → free=True")
ok(pub["size_gb"] == 1.0, "size_gb 换算")
for k in ("enclosure", "site_cookie", "site_ua", "page_url"):
    ok(k not in pub, f"投影不含 {k}")
pub2 = MusicMixin._music_cand_public({"downloadvolumefactor": 1.0, "title": ""})
ok(pub2["free"] is False and pub2["downloadvolumefactor"] == 1.0, "dv=1.0 → free=False（且不误显 1.0）")
pub3 = MusicMixin._music_cand_public({"downloadvolumefactor": 0.0})
ok(pub3["downloadvolumefactor"] == 0.0, "dv=0.0 原样保留")

print("[4] _music_row_from_ti 归一")
ti = SimpleNamespace(title="Song", size=100.0, seeders=3, site=16, site_name="YemaPT",
                     downloadvolumefactor=0.0, uploadvolumefactor=2.0, hit_and_run=True,
                     enclosure="http://x/1.torrent", page_url="pu", site_cookie="ck",
                     site_ua="ua", site_proxy=False)
r = MusicMixin._music_row_from_ti(ti)
ok(r and r["title"] == "Song" and r["seeders"] == 3, "_row_from_ti 基本字段")
ok(r["uploadvolumefactor"] == 2.0 and r["hit_and_run"] is True, "_row_from_ti uv/hnr")
ok(r["enclosure"] == "http://x/1.torrent" and r["site"] == 16, "_row_from_ti 保留下载真值")
ok(MusicMixin._music_row_from_ti(SimpleNamespace(title="x")) is None, "无 enclosure → None")
rd = MusicMixin._music_row_from_ti({"title": "D", "enclosure": "u", "site": 1, "size": 10})
ok(rd["title"] == "D" and rd["site"] == 1, "dict 输入也吃")

print("[5] _music_item_row 四态")
f = Fake()
row = f._music_item_row(H1, _qbt(progress=0.5, speed=100.0, size_gb=10.0), {}, None, None)
ok(row["stage"] == "downloading" and row["percent"] == 50.0, "progress<1 → downloading")
ok(row["downloaded_gb"] == 5.0 and row["left_gb"] == 5.0, "downloaded/left 换皮")
ok(isinstance(row["eta_s"], int) and row["eta_s"] > 0, "有速度 → ETA")
row = f._music_item_row(H1, _qbt(progress=1.0), {"sub": SUB_RESOURCE, "in_library": True}, None, None)
ok(row["stage"] == "resource" and "已入库" in row["stage_text"], "下完+账本=资源 → resource·已入库")
row = f._music_item_row(H1, _qbt(progress=1.0), {}, None, None)
ok(row["stage"] == "settling", "下完未转 → settling")
row = f._music_item_row(H1, None, {}, _item(H1, "音乐 某歌"), _rec(1234.0))
ok(row["stage"] == "gone" and row["in_qb"] is False, "不在 qB → gone")
ok(row["title"] == "某歌", "历史标题去「音乐」前缀")
ok(row["added_at"] and _iso(row["added_at"]) == 1234.0, "added_at → ISO")
ok(row["source_note"] == "源 馒头·免费", "source_note=原 reason")

print("[6] _music_items 单列表/totals/去重/上限")
snap = {H1: _qbt(progress=0.5, title="A", is_music=True),
        H2: _qbt(progress=1.0, title="B", is_music=True, dv=0.0),
        H3: _qbt(progress=1.0, title="C", is_music=False)}
led = {H1: {"site": "馒头"}, H2: {"sub": SUB_RESOURCE, "site": "CARPT"}}
jr = [_op(H1, "音乐 A", ts=2000.0), _op(H2, "音乐 B", ts=1000.0),
      _op("d" * 40, "音乐 历史", ts=1500.0)]
fi = Fake(snap=snap, ledger=led, journal=jr)
data = fi._music_items(limit=50)
rows = data["items"]
hashes = [r["hash"] for r in rows]
ok(hashes[0] == H1, "按 _ts(added_at) 倒序：H1 最新在前")
ok(sorted(hashes) == sorted([H1, H2, "d" * 40]), "单列表=在库 2 + 历史 1（非音乐线不入）")
ok(len(hashes) == len(set(hashes)), "无重复 hash")
ok("d" * 40 in hashes and next(r for r in rows if r["hash"] == "d" * 40)["stage"] == "gone", "历史行 stage=gone")
t = data["totals"]
ok(t["count"] == 3 and t["downloading"] == 1 and t["resource"] == 1 and t["gone"] == 1, "totals 分态计数")
ok(fi._music_items(limit=999)["items"] and len(fi._music_items(limit=999)["items"]) == 3, "limit 上限不越界")

print("[7] _music_act 守卫")
fd = Fake(snap={H1: _qbt(is_music=True), H2: _qbt(is_music=False)}, downloader=_DL())
rep = fd._music_act(hash="", action="pause")
ok(rep["ok"] is False and "hash" in rep["message"], "缺 hash → 拒")
rep = fd._music_act(hash=H1, action="frob")
ok(rep["ok"] is False and "未知操作" in rep["message"], "未知动作 → 拒")
rep = fd._music_act(hash="e" * 40, action="pause")
ok(rep["ok"] is False and "不在下载器" in rep["message"], "不在下载器 → 拒")
rep = fd._music_act(hash=H2, action="pause")
ok(rep["ok"] is False and "音乐线" in rep["message"], "非音乐线种 → 拒")
rep = fd._music_act(hash=H1, action="pause")
ok(rep["ok"] is True and rep["message"] == "已暂停", "pause 命中 → ok")
ok({"ok", "hash", "action", "message", "blocked"} <= set(rep), "回执 5 键齐全")
rep = fd._music_act(hash=H1, action="remove")
ok(rep["ok"] is False and rep["blocked"] is True, "remove 被闸门拦 → blocked=True")

print("[8] _music_download_cids 按选择下载")
f2 = Fake()
f2._music_cand_put("known", {"hash": H1, "site": 16, "site_name": "YemaPT",
                             "title": "T", "size": 1073741824.0, "downloadvolumefactor": 0.0})
f2._tag_all_torrents = lambda: {}
out = f2._music_download_cids(["known", "nope"])
ok(out["summary"]["picked"] == 2, "picked=2")
ok(len(out["added"]) == 1 and out["added"][0]["hash"] == H1, "已知 cid → added")
ok(len(out["failed"]) == 1 and "过期或不存在" in out["failed"][0]["message"], "未知 cid → failed")
ok(out["added"][0]["free"] is True, "回执带 free")

print("[9] 标题相关度（排序键）")
ok(MusicMixin._music_relevance("Jay Chou 周杰伦 FLAC", "周杰伦") > 1.0, "整串命中 → >1.0")
ok(MusicMixin._music_relevance("Jay Chou 15 Album", "周杰伦") == 0.0, "无命中 → 0")
ok(0 < MusicMixin._music_relevance("周杰伦", "周杰伦 无损") < 1.0, "部分 token 命中 ∈ (0,1)")
ok("relevance" in pub, "候选投影带 relevance")

print()
print(f"共 {N} 断言，失败 {len(FAILS)}")
if FAILS:
    for x in FAILS:
        print("  FAIL:", x)
    sys.exit(1)
print("PASS")
