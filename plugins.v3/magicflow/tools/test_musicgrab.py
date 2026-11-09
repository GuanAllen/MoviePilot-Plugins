#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 音乐线离线回归（★ 16.0.0：只留 AI 选种链路相关纯函数）。真跑 features/musicgrab.py。

16.0.0 已移除「歌单程序选种」legacy（plan / public_plan / grab 一族方法）：
音乐线只保留 `search → AI 选 → download(cids)`；本文件只测留下的纯函数。

断言：
  [1] 歌单解析：`艺人 - 歌名` / `歌名` / `歌名@站id,站id` / 空行与 `#` 注释；
  [2] 硬过滤：分辨率/编码/容器/演唱会 → 排除（score=0, excluded=True）；
  [3] 打分：无损 > 有损；24bit 高解析加分；免费加分；
  [4] 打分：做种数折算封顶（>=50 拿满 10）；
  [16] 护栏：`self._agent_ok` 只接 2 参（AST 扫描）；
  [17] 保存目录 `_music_save_path`（方法/属性同名坑）；
  [19] 音乐线判定 `_is_music_line`；[20] 摘职务标签；[21] 交回 stripped。

用法：``python3 tools/test_musicgrab.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_musicgrab_test"


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
musicgrab = _load(PKG + ".features.musicgrab", "features/musicgrab.py")
MusicGrabMixin = musicgrab.MusicGrabMixin
_fake_ih = lambda b: ("H:" + (b.decode("utf-8", "ignore") if isinstance(b, (bytes, bytearray)) else str(b))).lower()
musicgrab.info_hash = _fake_ih
# ★ 19.10.11：加种核心收归 tags.media_grab → info_hash 补丁要打在 tags 上
sys.modules[PKG + ".tags"].info_hash = _fake_ih

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


def _hit(title, size_gb=0.5, seeders=10, site=10, site_name="聆音", dv=1.0, uv=1.0):
    return SimpleNamespace(
        title=title, size=int(size_gb * 1024 ** 3), seeders=seeders, site=site,
        site_name=site_name, enclosure=f"https://x/download.php?id={abs(hash(title)) % 99999}",
        downloadvolumefactor=dv, uploadvolumefactor=uv, hit_and_run=True,
    )


class Fake(MusicGrabMixin):
    """只提供计划/加种路径要用的真值源（搜索/PV/站点/下载器）。"""

    def __init__(self, hits_by_kw=None, add_ok=True):
        self._hits = dict(hits_by_kw or {})
        self.logs = []
        self.spent = 0
        self._add_ok = add_ok
        self._exist = set()
        self.calls = []
        self.journal = []
        self._dl = self
        self.tag_calls = []
        self.lib_marks = []
        self.asset_marks = []
        self._qb_index = {}
        self.queued = []

    # --- 19.12.0 入库改为后台队列（JobQueue）：桩返回 job id 即视为已入队
    def _music_import_submit(self, key, title="", reason=""):
        self.queued.append((key, title))
        return {"id": "job-" + str(key)[:8]}

    def _music_import_done(self, key):
        return False

    # --- 库记桩（_music_mark_library）
    def _tag_groups(self):
        outer = self

        class _G:
            def queue_library(self, h, path="", media_id=""):
                outer.lib_marks.append((h, path))
                return "g" + h[:4]

        return _G()

    def _tag_state(self):
        outer = self

        class _S2:
            def set_asset(self, h, sub=None):
                outer.asset_marks.append((h, sub))

        return _S2()

    # --- 下载器桩
    @property
    def is_available(self):
        return True

    def add_torrent(self, **kw):
        self.calls.append(kw)
        if not self._add_ok:
            return None, "boom"
        return ["h" + str(len(self.calls)).zfill(39)], None

    def _get_downloader(self, name):
        return self._dl

    def _crossseed_torrent_bytes(self, row):
        return ("T:" + str(row.title)).encode("utf-8")

    def fetch_torrent_bytes(self, url, cookie=None, user_agent=None, referer=None):
        # ★ 19.10.11：media_grab 走宿主 SDK 取种（与 _crossseed_torrent_bytes 同一条链）
        return ("T:" + str(url)).encode("utf-8")

    def _tag_all_torrents(self):
        return {h: {} for h in self._exist}

    def get_all_torrents_index(self):
        return dict(self._qb_index)

    def replace_torrent_tags(self, h, tags):
        self.tag_calls.append((h, list(tags)))
        _t = self._qb_index.get(h)          # 真下载器会改标签 → 桩也改（否则幂等测不出来）
        if _t is not None:
            _t.tags = list(tags)
        return True

    def set_torrent_tags(self, h, tags):
        self.tag_calls.append((h, list(tags)))
        _t = self._qb_index.get(h)
        if _t is not None:
            _t.tags = list(tags)
        return bool(self._tag_ok) if hasattr(self, "_tag_ok") else True

    def _site_domain_by_name(self, name):
        return "soulvoice.club"

    def normalize_path(self, path):
        """宿主路径 → MP 视角路径（与 downloader path_mapping 同向）。"""
        p = str(path or "")
        for host, mp in (("/vol6/1000/movie", "/movie"), ("/vol3/1000/media", "/media"),
                         ("/vol6/1000/music", "/music")):
            if p == host or p.startswith(host + "/"):
                return mp + p[len(host):]
        return p

    @property
    def _store(self):
        class _J:
            def __init__(self, sink):
                self.sink = sink

            def record(self, **kw):
                self.sink.append(kw)
        return SimpleNamespace(journal=_J(self.journal))

    # ---- 真值源桩
    def _mp_search_title(self, kw, sites, mtype=""):
        assert mtype == "music", f"必须传 mtype=music，实际 {mtype!r}"
        return list(self._hits.get(str(kw).strip(), []))

    def _ondemand_sites(self, task=None, site_ids=""):
        ids = [int(x) for x in str(site_ids).split(",") if str(x).strip().isdigit()]
        return ids or [10, 11]

    def _pv_block_reason(self, i):
        return ""

    def _pv_allow(self, i, kind, want=1):
        return True

    def _pv_spend(self, i, kind, n=1):
        self.spent += int(n)

    def _log(self, *a, **k):
        self.logs.append(" ".join(str(x) for x in a))

    def _agent_now(self):
        return "2026-10-07T20:00:00+08:00"


# ---------------------------------------------------------------- [1] 解析
print("[1] 歌单解析")
f = Fake()
ents = f._music_parse("周杰伦 - 晴天\n七里香\n五月天 - 倔强@10,12\n\n# 注释\n")
ok(len(ents) == 3, "空行/注释被跳过（3 条）")
ok(ents[0] == {"raw": "周杰伦 - 晴天", "artist": "周杰伦", "title": "晴天", "sites": ""}, "艺人 - 歌名 拆分")
ok(ents[1]["artist"] == "" and ents[1]["title"] == "七里香", "无艺人 → title 原文")
ok(ents[2]["sites"] == "10,12" and ents[2]["title"] == "倔强", "@站id 解析")

# ---------------------------------------------------------------- [2] 硬过滤
print("[2] 硬过滤（视频/MV）")
f = Fake()
s = f._music_score({"title": "Maroon 5-Sugar 1080p WEB-DL H264 AAC", "size": 10 ** 9, "seeders": 30})
ok(s["excluded"] is True and s["score"] == 0, "1080p/H264 被排除")
s2 = f._music_score({"title": "周杰伦 晴天 MV 官方", "size": 10 ** 8, "seeders": 3})
ok(s2["excluded"] is True, "含 MV 被排除")
s3 = f._music_score({"title": "某演唱会 Live 现场 1080p", "size": 10 ** 9, "seeders": 9})
ok(s3["excluded"] is True, "演唱会/录像被排除")
s4 = f._music_score({"title": "周杰伦 - 叶惠美 [CD FLAC分轨]", "size": 3 * 10 ** 8, "seeders": 120})
ok(s4["excluded"] is False, "纯音频 FLAC 不排除")

# ---------------------------------------------------------------- [3] 打分
print("[3] 打分（格式/位深/免费）")
fig = f._music_score({"title": "X - A [CD FLAC分轨]", "size": 3 * 10 ** 8, "seeders": 100})
mp3 = f._music_score({"title": "X - A [MP3 320]", "size": 10 ** 8, "seeders": 100})
ok(fig["score"] > mp3["score"], "无损 > 有损")
hi = f._music_score({"title": "X - A [24bit 96kHz FLAC]", "size": 10 ** 9, "seeders": 100})
lo = f._music_score({"title": "X - A [16bit FLAC]", "size": 10 ** 9, "seeders": 100})
ok(hi["score"] > lo["score"], "24bit/96kHz 高解析加分")
free = f._music_score({"title": "X - A [FLAC]", "size": 3 * 10 ** 8, "seeders": 10, "downloadvolumefactor": 0.0})
paid = f._music_score({"title": "X - A [FLAC]", "size": 3 * 10 ** 8, "seeders": 10, "downloadvolumefactor": 1.0})
ok(free["score"] == paid["score"] + musicgrab._MUSIC_W_FREE, "免费 +20")

s_hi_only = f._music_score({"title": "X - A [24bit96khz]", "size": 10 ** 9, "seeders": 10})
ok(s_hi_only["score"] >= musicgrab._MUSIC_W_LOSSLESS + musicgrab._MUSIC_W_HIRES,
   "只写 24bit96khz 也按无损算")

# ---------------------------------------------------------------- [4] 做种封顶
print("[4] 做种折算封顶")
a = f._music_score({"title": "X - A [FLAC]", "size": 3 * 10 ** 8, "seeders": 50, "downloadvolumefactor": 1.0})
b = f._music_score({"title": "X - A [FLAC]", "size": 3 * 10 ** 8, "seeders": 500, "downloadvolumefactor": 1.0})
ok(a["score"] == b["score"], ">=50 做种拿满，不再涨")

# ---------------------------------------------------------------- [16] 护栏：_agent_ok 参数个数
print("[16] 护栏：self._agent_ok 只接 2 参（曾把 source 误传进来 → 运行时 4 参报错）")
import ast as _ast
_bad = []
for _f in ("features/agentapi.py", "features/musicgrab.py"):
    _tree = _ast.parse((ROOT / _f).read_text(encoding="utf-8"))
    for _n in _ast.walk(_tree):
        if (isinstance(_n, _ast.Call) and isinstance(_n.func, _ast.Attribute)
                and _n.func.attr == "_agent_ok"
                and (len(_n.args) != 2 or _n.keywords)):
            _bad.append(f"{_f}:{_n.lineno}")
ok(not _bad, f"所有 _agent_ok 调用都是 (data, t0)（违规：{_bad}）")

# ---------------------------------------------------------------- [17] 保存目录（方法/属性同名坑）
print("[17] _music_save_path 返回字符串（不同名撞车）")
f6 = Fake()
v = f6._music_save_path()
ok(isinstance(v, str) and v == musicgrab.MUSIC_SAVE_PATH_DEFAULT, f"默认目录（{v}）")
ok(f6._music_save_path("/tmp/x") == "/tmp/x", "入参覆盖")
f6._music_save_dir = "/vol6/1000/mymusic"
ok(f6._music_save_path() == "/vol6/1000/mymusic", "设置项生效（属性名 _music_save_dir）")

# ---------------------------------------------------------------- [19] 音乐线判定
print("[19] _is_music_line（qB 分类「音乐」）")


class _T:
    def __init__(self, cat, tags=None):
        self.category = cat
        self.tags = tags or []


f8 = Fake()
ok(f8._is_music_line(_T("音乐")), "对象：分类音乐 → True")
ok(not f8._is_music_line(_T("电影")), "对象：其它分类 → False")
ok(f8._is_music_line({"category": "音乐"}), "dict：分类音乐 → True")
ok(not f8._is_music_line({"category": ""}), "dict：空分类 → False")

# ---------------------------------------------------------------- [20] 摘「魔力/刷流」职务标签
print("[20] _music_untag_duty 只摘魔力/刷流职务标签")
f9 = Fake()
f9._qb_index = {
    "a" * 40: _T("音乐", ["魔流-馒头-静默-资源", "魔流-馒头-魔力", "魔流-手动"]),
    "b" * 40: _T("音乐", ["魔流-CARPT-静默-新", "魔流-CARPT-刷流"]),
    "c" * 40: _T("电影", ["魔流-馒头-魔力"]),
}
dry = f9._music_untag_duty(apply=False)
ok(dry["scanned"] == 2 and dry["candidates"] == 2 and dry["cleaned"] == 0, "干跑：命中但不动 qB")
ok(f9.tag_calls == [], "干跑：零写入")
app = f9._music_untag_duty(apply=True)
ok(app["cleaned"] == 2 and app["failed"] == 0, "执行：两个音乐种都摘了")
_calls = dict(f9.tag_calls)
ok(_calls["a" * 40] == ["魔流-馒头-静默-资源", "魔流-手动"], "只摘 魔力，其它标签保留")
ok(_calls["b" * 40] == ["魔流-CARPT-静默-新"], "只摘 刷流")
ok("c" * 40 not in _calls, "非音乐种一律不动")

# ------------------------------------------------- [21] 交回本轮真摘掉的 hash（★15.8.11）
print("[21] _music_untag_duty 交回 stripped（账本那一半在 TagsMixin，见 test_tag_reconcile ⑨）")
f10 = Fake()
f10._qb_index = {
    "d" * 40: _T("音乐", ["魔流-CARPT-静默-新"]),                 # 没职务标签 → 不在本方法职责内
    "g" * 40: _T("音乐", ["魔流-馒头-刷流", "魔流-馒头-静默-资源"]),  # 有职务标签 → 摘 + 交回
    "e" * 40: _T("音乐", ["魔流-CARPT-保种"]),                     # 保种不算魔力/刷流 → 不动
}
dry2 = f10._music_untag_duty(apply=False)
ok(dry2["candidates"] == 1 and dry2["stripped"] == [], "干跑：只认 1 个待摘、stripped 为空")
app2 = f10._music_untag_duty(apply=True)
ok(app2["cleaned"] == 1 and app2["stripped"] == ["g" * 40], "执行：交回本轮真摘掉的整串 hash")
ok(dict(f10.tag_calls).get("g" * 40) == ["魔流-馒头-静默-资源"], "g：只摘职务轴")
ok(dict(f10.tag_calls).get("d" * 40) is None, "d：标签没职务轴 → 不动 qB（账本另由 TagsMixin 收）")
again = f10._music_untag_duty(apply=True)
ok(again["candidates"] == 0 and again["cleaned"] == 0 and again["stripped"] == [], "幂等：再跑零动作")

# --------------------------------------------- [22] 音乐结算：下完 → 直调 MP 整理（★17.2.0）
print("[22] _music_settle_import：下完的音乐种直调 manual_transfer，幂等/限流/失败不阻断")

class _S:
    def __init__(self, cat, prog, content="/vol6/1000/music/下载/Album X/t01.flac", title="Album X - Artist",
                 added_on=None):
        self.category, self.progress, self.content_path = cat, prog, content
        self.save_path, self.title, self.tags = "/vol6/1000/music/下载", title, []
        self.added_on = time.time() if added_on is None else added_on

f11 = Fake()
f11._qb_index = {}
_F11_TORRENTS = {
    "m" * 40: _S("音乐", 1.0),
    "n" * 40: _S("音乐", 0.5, title="还在下"),
    "o" * 40: _S("音乐", 1.0, title="已整理过"),
    "p" * 40: _S("电影", 1.0, title="影视种不动"),
    "x" * 40: _S("音乐", 1.0, content="/vol6/1000/movie/下载/Old Album/t01.flac", title="老下载目录里的种"),
    "y" * 40: _S("音乐", 1.0, title="三周前的老种", added_on=time.time() - 21 * 86400),
}
f11._tag_all_torrents = lambda: _F11_TORRENTS
_done = {"o" * 40}
f11._music_transferred = lambda h: h in _done
_calls = []


def _f11_tr(h, t, p):
    _calls.append((h, p))
    return True, ""


f11._music_transfer_now = _f11_tr
r = f11._music_settle_import(apply=False)
ok(r["scanned"] == 5 and r["pending"] == 2 and r["settled"] == 0,
   f"干跑：扫 5（音乐线；非音乐下载目录/老种不算）= 待转 2（{r}）")
ok(_calls == [], "干跑：零动作")
r = f11._music_settle_import(apply=True)
ok(r["settled"] == 1 and r["queued"] == 1 and f11.queued and f11.queued[0][0] == "m" * 40,
   f"执行：只把下完未整理的那颗入队（{f11.queued}）")
ok(all(w[0] != "x" * 40 for w in _calls), "不在音乐下载目录的种（老 movie 目录）不整理")
ok(all(w[0] != "y" * 40 for w in _calls), "3 周前的老种不重复结算")
ok(f11.tag_calls == [], "直调路线不再打 MOVIEPILOT 标签（否则 MP 定时任务重复扫描）")
_done.add("m" * 40)  # 模拟整理成功（transferhistory 已记）
_calls.clear()
r = f11._music_settle_import(apply=True)
ok(r["settled"] == 0 and f11.queued == [("m" * 40, "Album X - Artist")], "幂等：已整理过的不再重复入队")
ok(any(h == "o" * 40 for h, _p in f11.lib_marks),
   f"已整理过的种补写库记（事件偶发收不到；{f11.lib_marks}）")

f12 = Fake()
f12._qb_index = {}
f12._tag_all_torrents = lambda: {"q%d" % i * 40: _S("音乐", 1.0) for i in range(5)}
f12._music_transferred = lambda h: False
f12._music_transfer_now = lambda h, t, p: (True, "")
r = f12._music_settle_import(apply=True, limit=2)
ok(r["settled"] == 2 and r["pending"] == 5, f"限流：一轮最多处理 2 张（{r['settled']}）")

f13 = Fake()
f13._qb_index = {}
f13._tag_all_torrents = lambda: {"z" * 40: _S("音乐", 1.0)}
f13._music_transferred = lambda h: False
f13._music_import_submit = lambda key, title="", reason="": {}   # 入队失败（JobQueue 拒绝）
r = f13._music_settle_import(apply=True)
ok(r["failed"] == 1 and r["settled"] == 0, "入队失败只计数，不抛异常（下轮再试）")
ok(f11._music_mp_path("/vol6/1000/music/下载/X").startswith("/"), "宿主路径 → MP 路径兜底可用")

# ------------------------ [23] 19.9.2 relocate 防抖（空转修复）
print("[23] _music_settle_import 19.9.2：save_path 已等值目标 / 冷却期内不再 relocate（防空转刷屏）")


class _SP(_S):
    def __init__(self, cat, prog, content, save_path, title="Album SP"):
        super().__init__(cat, prog, content=content, title=title)
        self.save_path = save_path


f14 = Fake()
f14._qb_index = {}
_relocs = []
f14._music_relocate = lambda h, d: (_relocs.append(h) or True)
f14._tag_all_torrents = lambda: {
    # 真实数据在 movie 目录，qB 记的 save_path 也还是 movie 目录 → 该搬（一次）
    "r" * 40: _SP("音乐", 1.0, "/vol6/1000/movie/下载/A/t01.flac", "/vol6/1000/movie/下载/A"),
    # 2026-10-25 现场：数据在 movie 目录，qB 记的 save_path 已是音乐目录 → 搬不动，必须跳过
    "s" * 40: _SP("音乐", 1.0, "/vol6/1000/movie/下载/B/t01.flac", "/vol6/1000/music/下载"),
}
r = f14._music_settle_import(apply=True)
ok(r["relocated"] == 1 and _relocs == ["r" * 40], f"路径不同 → 只搬一次（{r} / {_relocs}）")
ok(int(r["reloc_skip"]) >= 1, f"save_path 已等值目标 → 直接跳过、不空搬（{r['reloc_skip']}）")
_relocs.clear()
r2 = f14._music_settle_import(apply=True)
ok(r2["relocated"] == 0 and _relocs == [], "冷却期内同一 hash 不重试（不再每轮刷屏）")
ok(int(r2["reloc_skip"]) >= 2, f"跳过计数可见（{r2['reloc_skip']}）")

# ------------------- [24] 19.8.1 音乐清单：交棒后只留下载记录（★19.8.1 参照点播）
print("[24] _music_items 19.8.1：交棒静默池后只留静态下载记录，不取 qB 现况")


class _ST(_S):
    def __init__(self, cat, prog, state="pausedUP", size_gb=1.0, title="Album X"):
        super().__init__(cat, prog, title=title)
        self.state = state
        self.size_gb = size_gb


class _RecFake(Fake):
    def __init__(self, snap, recs, journal=()):
        super().__init__()
        self._snap = snap
        self._seed_recs = recs
        self.journal = list(journal)
        self._tag_all_torrents = lambda: dict(self._snap)

    def _ondemand_seed_rec(self, h):
        return self._seed_recs.get(h) or {}

    def _music_deleted_hashes(self):
        return set()

    @property
    def _store(self):
        class _J:
            def __init__(self, rows):
                self.rows = rows

            def list_recent(self, limit=5000):
                return list(self.rows)[:limit]

        return SimpleNamespace(journal=_J(self.journal))


_H1, _H2, _H3, _H4 = "a" * 40, "b" * 40, "c" * 40, "d" * 40
_snap = {
    _H1: _ST("音乐", 1.0, title="已交棒专辑"),      # sub=资源 + pausedUP
    _H2: _ST("音乐", 0.5, title="还在下"),          # 下到一半
    _H3: _ST("音乐", 1.0, title="下完待转"),        # 下完未交棒
}
_recs = {
    _H1: {"sub": "资源", "site": "聆音", "in_library": True, "identity_at": 1.0},
    _H2: {"sub": "新", "site": "聆音"},
    _H3: {"sub": "新", "site": "聆音"},
}
_jrec = SimpleNamespace(
    created_at=99.0,
    items=[SimpleNamespace(source="music", hash=_H1, title="音乐 已交棒专辑", reason="源 聆音"),
           SimpleNamespace(source="music", hash=_H4, title="音乐 已结案专辑", reason="源 CARPT")],
)
f14 = _RecFake(_snap, _recs, [_jrec])
_rep = f14._music_items(limit=50)
_rows = {r["hash"]: r for r in _rep["items"]}
ok(len(_rows) == 4 and _rep["totals"]["count"] == 4, f"清单 4 行（{list(_rows)}）")
ok(_rows[_H1]["stage"] == "resource" and _rows[_H1]["stage_text"] == "已转「资源」·已入库",
   f"交棒行 = 已转「资源」·已入库（{_rows[_H1]['stage_text']}）")
ok(_rows[_H1]["state"] == "" and _rows[_H1]["in_qb"] is False,
   f"交棒行**不取 qB 现况**（state={_rows[_H1]['state']!r} in_qb={_rows[_H1]['in_qb']}）")
ok(_rows[_H1]["progress"] == 1.0 and _rows[_H1]["percent"] == 100.0 and _rows[_H1]["save_path"] == "",
   "交棒行按记录写死 100%（不回查下载器）")
ok(_rows[_H2]["stage"] == "downloading" and _rows[_H2]["state"] == "pausedUP"
   and _rows[_H2]["in_qb"] is True and _rows[_H2]["percent"] == 50.0,
   "未交棒行仍带 qB 现况（下载中）")
ok(_rows[_H3]["stage"] == "settling" and _rows[_H3]["stage_text"] == "已下完，待转「资源」",
   f"下完未交棒 = 待转资源（{_rows[_H3]['stage_text']}）")
ok(_rows[_H4]["stage"] == "gone" and _rows[_H4]["stage_text"] == "已结案"
   and _rows[_H4]["in_qb"] is False and _rows[_H4]["state"] == "",
   f"只剩 journal 的行 = 已结案记录（{_rows[_H4]['stage_text']}）")
ok(all(not r["state"] for h, r in _rows.items() if h in (_H1, _H4)),
   "回归：交棒/结案行绝不暴露 pausedUP（静默池状态不再串进音乐任务）")

# ---------------------------------------------------------------- [25] 19.9.0 在途职务「音乐」
print("[25] 19.9.0 音乐在途挂 __music__：加种即带职务标签、下完才摘")


class _TP(_T):
    def __init__(self, cat, tags=None, prog=0.0):
        super().__init__(cat, tags)
        self.progress = prog
        self.title = "x"


f11 = Fake()
f11._qb_index = {
    "d" * 40: _TP("音乐", ["魔流-聆音-静默-资源", "魔流-聆音-音乐"], 0.4),
    "e" * 40: _TP("音乐", ["魔流-聆音-静默-资源", "魔流-聆音-音乐"], 1.0),
    "f" * 40: _TP("音乐", ["魔流-聆音-静默-资源"], 0.5),
}
_r25 = f11._music_untag_duty(apply=True)
_c25 = dict(f11.tag_calls)
ok(_r25["cleaned"] == 1, f"下完的才摘（{_r25['cleaned']}）")
ok("d" * 40 not in _c25 and "魔流-聆音-音乐" in f11._qb_index["d" * 40].tags,
   "下载中：音乐职务保留（免疫静默池的唯一凭据）")
ok(_c25["e" * 40] == ["魔流-聆音-静默-资源"], "下完：摘掉音乐职务，回到纯身份")
ok("f" * 40 not in _c25, "没有音乐职务的种不动")

f12 = Fake()
f12.assign_calls = []
f12._music_assign = lambda hs, **kw: f12.assign_calls.append((list(hs), kw)) or len(hs)
f12._music_relocate = lambda h, p: None
_out = f12._music_grab_one({"title": "Album X", "site": 0, "site_name": "聆音",
                            "size": 1 << 30, "hit_and_run": False,
                            "enclosure": "https://pt.soulvoice.club/download.php?id=1"},
                           "/vol6/1000/music/下载")
_tag25 = str((f12.calls[-1] or {}).get("tag") or "") if f12.calls else ""
ok("魔流-聆音-音乐" in _tag25 and "魔流-聆音-静默-资源" in _tag25,
   f"加种即打「身份+职务」两个标签（{_tag25}）")
ok(bool(f12.assign_calls) and f12.assign_calls[0][1].get("sub") == "资源",
   "加种后立刻挂 __music__（sub=资源）")

print()
if FAILS:
    print(f"❌ 失败 {len(FAILS)}/{N}：")
    for x in FAILS:
        print("   -", x)
    sys.exit(1)
print(f"✅ 全部通过（{N} 断言）")
