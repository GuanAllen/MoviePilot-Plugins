#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 歌单→选种计划（★ 15.7.0）离线回归 —— 真跑 features/musicgrab.py，不需 MoviePilot / qB。

背景（Master 2026-10-07 20:44）：**歌曲也是资源** → 音乐走 PT 规则（H&R / 账本），
而「选种」是最难的一环。本版只做**计划（干跑）**：歌单 → 搜候选 → 硬过滤视频 →
可解释打分 → 选中 + 逐条依据链。

断言：
  [1] 歌单解析：`艺人 - 歌名` / `歌名` / `歌名@站id,站id` / 空行与 `#` 注释；
  [2] 硬过滤：分辨率/编码/容器/演唱会 → 排除（score=0, excluded=True）；
  [3] 打分：无损 > 有损；24bit 高解析加分；免费加分；
  [4] 打分：做种数折算封顶（>=50 拿满 10）；
  [5] 选中：取最高分（并列时做种多者）；空候选 → chosen=None + empty_reason；
  [6] 全被过滤 → chosen=None 且 empty_reason 指明「视频/MV」；
  [7] 汇总：entries/chosen/empty/excluded_video/per_item；
  [8] 依据链：每条含 rule/verdict/inputs/source_of_truth/at；
  [9] per_item 截断候选条数；[10] limit 截断歌单条数。

用法：``python3 tools/test_musicgrab.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
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
musicgrab.info_hash = lambda b: ("H:" + (b.decode("utf-8", "ignore") if isinstance(b, (bytes, bytearray)) else str(b))).lower()

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
        self._qb_index = {}

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

    def _tag_all_torrents(self):
        return {h: {} for h in self._exist}

    def get_all_torrents_index(self):
        return dict(self._qb_index)

    def replace_torrent_tags(self, h, tags):
        self.tag_calls.append((h, list(tags)))
        return True

    def _site_domain_by_name(self, name):
        return "soulvoice.club"

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

# ---------------------------------------------------------------- [5] 选中
print("[5] 选中（最高分；并列取做种多）")
f = Fake({"周杰伦 晴天": [
    _hit("Jay Chou - Ye Hui Mei FLAC分轨", size_gb=0.30, seeders=120),
    _hit("Jay Chou - Ye Hui Mei MP3", size_gb=0.10, seeders=200),
]})
plan = f._music_plan("周杰伦 - 晴天")
it = plan["items"][0]
ok(it["chosen"] and "FLAC" in it["chosen"]["title"], "选中无损而非有损")
ok(it["candidates_total"] == 2 and it["audio_total"] == 2, "候选计数 2/2")
f2 = Fake({})
plan2 = f2._music_plan("无此歌")
ok(plan2["items"][0]["chosen"] is None, "无候选 → chosen=None")
ok("没搜到" in plan2["items"][0]["empty_reason"], "empty_reason 说明没搜到")

# ---------------------------------------------------------------- [6] 全被过滤
print("[6] 全被过滤")
f = Fake({"X 某歌": [_hit("X 某歌 1080p MV", size_gb=1.0, seeders=5)]})
plan = f._music_plan("X - 某歌")
ok(plan["items"][0]["chosen"] is None, "全被过滤 → chosen=None")
ok("视频" in plan["items"][0]["empty_reason"], "empty_reason 指明视频/MV")

# ---------------------------------------------------------------- [7] 汇总
print("[7] 汇总")
f = Fake({"A 歌1": [_hit("A - 歌1 FLAC分轨", size_gb=0.3)], "B 歌2": [_hit("B - 歌2 1080p MV", size_gb=1.0)]})
plan = f._music_plan("A - 歌1\nB - 歌2")
sm = plan["summary"]
ok(sm["entries"] == 2 and sm["chosen"] == 1 and sm["empty"] == 1, "entries/chosen/empty")
ok(sm["excluded_video"] == 1, "excluded_video 计数")
ok(plan["policy"] and "mtype=music" in plan["policy"]["search"], "policy 说明搜索口径")

# ---------------------------------------------------------------- [8] 依据链
print("[8] 依据链")
f = Fake({"A 歌1": [_hit("A - 歌1 FLAC分轨", size_gb=0.3, seeders=10)]})
plan = f._music_plan("A - 歌1")
rs = plan["items"][0]["chosen_reasons"]
ok(len(rs) >= 4, f"选中项至少 4 条依据（实际 {len(rs)}）")
keys = {"rule", "verdict", "inputs", "source_of_truth", "at"}
ok(all(keys <= set(r) for r in rs), "每条依据含 rule/verdict/inputs/source_of_truth/at")

# ---------------------------------------------------------------- [9] per_item
print("[9] per_item 截断")
f = Fake({"A 歌1": [_hit(f"A - 歌1 FLAC v{i}", size_gb=0.3, seeders=10 + i) for i in range(6)]})
plan = f._music_plan("A - 歌1", per_item=2)
ok(len(plan["items"][0]["candidates"]) == 2, "candidates 截到 per_item")
ok(plan["items"][0]["candidates_total"] == 6, "candidates_total 保留全量")

# ---------------------------------------------------------------- [10] limit
print("[10] limit 截断歌单")
f = Fake()
plan = f._music_plan("\n".join(f"艺人 - 歌{i}" for i in range(10)), limit=3)
ok(len(plan["items"]) == 3, "歌单截到 limit")

# ---------------------------------------------------------------- [11] 加种
print("[11] 加种（tag/category/save_path/site_domain/hit_and_run）")
f = Fake({"A 歌1": [_hit("A - 歌1 FLAC分轨", size_gb=0.3, seeders=30)]})
res = f._music_grab("A - 歌1", save_path="/tmp/music")
ok(res["applied"] is True and len(res["added"]) == 1, "加种成功 1 条")
ok(res["save_path"] == "/tmp/music" and res["category"] == "音乐", "save_path 覆盖 + 分类=音乐")
c = f.calls[0]
ok(c["download_dir"] == "/tmp/music", "下载器收到 download_dir")
ok(c["tag"] == "魔流-聆音-静默-资源", f"标签 = 魔流-聆音-静默-资源（实际 {c['tag']}）")
ok(c["category"] == "音乐", "下载器收到 category")
ok(c["site_domain"] == "soulvoice.club", "下载器收到站点域名（开账真值源）")
ok(c["hit_and_run"] is True, "带 hit_and_run（H&R 开账）")
ok(len(f.journal) == 1 and f.journal[0]["items"][0].source == "music", "journal 记 source=music")

# ---------------------------------------------------------------- [12] 幂等
print("[12] 幂等（同歌单再跑）")
f._exist.add("h" + "1".zfill(39))
f2 = Fake({"A 歌1": [_hit("A - 歌1 FLAC分轨", size_gb=0.3)]})
f2._exist = {"h:" + "t:a - 歌1 flac分轨"}
r2 = f2._music_grab("A - 歌1")
ok(len(r2["added"]) == 0 and len(r2["skipped"]) == 1, "已在下载器 → added=0 / skipped=1")
ok("已在下载器" in (r2["skipped"][0].get("reason") or ""), "skip 原因=已在下载器")
ok(len(f2.calls) == 0, "已在下载器 → 不再调 add_torrent")

# ---------------------------------------------------------------- [13] 无候选
print("[13] 无候选 → skipped")
f3 = Fake({})
r3 = f3._music_grab("无此歌")
ok(len(r3["added"]) == 0 and len(r3["skipped"]) == 1, "无候选 → skipped 1")

# ---------------------------------------------------------------- [14] 失败
print("[14] 添加失败 → failed")
f4 = Fake({"A 歌1": [_hit("A - 歌1 FLAC分轨", size_gb=0.3)]}, add_ok=False)
r4 = f4._music_grab("A - 歌1")
ok(len(r4["added"]) == 0 and len(r4["failed"]) == 1, "add 失败 → failed 1")
ok("boom" in (r4["failed"][0].get("message") or ""), "带失败原因")

# ---------------------------------------------------------------- [15] 对外剔除内部行
print("[15] 对外计划剔除 _chosen_row")
f5 = Fake({"A 歌1": [_hit("A - 歌1 FLAC分轨", size_gb=0.3)]})
r5 = f5._music_grab("A - 歌1")
ok(all("_chosen_row" not in it for it in r5["plan"]["items"]), "plan.items 不含 _chosen_row")
ok(r5["summary"]["added"] == 1, "summary.added")

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

# ---------------------------------------------------------------- [18] 被过滤候选可见
print("[18] 全部被过滤时给出 excluded 明细")
f7 = Fake({"A 歌1": [_hit("A - 歌1 1080p MV", size_gb=1.0, seeders=5)]})
plan7 = f7._music_plan("A - 歌1")
ex = plan7["items"][0]["excluded"]
ok(len(ex) == 1 and "1080p" in ex[0]["title"], "excluded 带标题")
ok(ex and ex[0]["reason"], "excluded 带原因")
ok(plan7["items"][0]["candidates"] == [], "candidates 为空")

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

print()
if FAILS:
    print(f"❌ 失败 {len(FAILS)}/{N}：")
    for x in FAILS:
        print("   -", x)
    sys.exit(1)
print(f"✅ 全部通过（{N} 断言）")
