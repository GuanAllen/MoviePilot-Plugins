#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播可读标题 + 多选一并下载（★ 19.11.0）离线回归 —— 真跑源码，不需 MoviePilot / qB。

背景（Master 2026-11-01）：
  1. 「搜出的内容显示目前都是拼音或者英文，要求要不能看懂要不副标题」
     —— 站点把中文名写在 ``torrent_info.description``（实测 1262/1264 条含中文），
        候选行原来只取 ``title``（站点原文拼音/英文），于是整屏看不懂。
  2. 「能够多选一并下载」
     —— 点播原来一次一条，补 8 季要点 8 次。

真值源：
  · 可读标题 = ``tags.display_title(description)`` → ``cn_title`` / ``cn_alt`` / ``spec``；
  · 批量落种 = ``OnDemandMixin.on_demand_batch`` → 逐条走**同一个** ``_ondemand_download``
    （所以标签 / 伪任务 / H&R 台账口径与单条完全一致，不存在绕开纳管的第二条路径）。

断言：
  [1] display_title：真实站点副标题 → 中文主名 / 别名 / 规格串；
  [2] 边界：空副标题、纯英文副标题、地区括注、别名收敛、片名段夹规格词；
  [3] media_row_from_ti：新字段齐全（原字段 + 派生），老字段一个没丢；
  [4] on_demand_batch：缺参 / 超上限 / 池未命中 / 部分成功 / 去重 / already 标记。

  [6] ★ 19.11.7：认不出片名时后端 `success=false` **但带 data.candidates**，前端不得
      用 `unwrapResponse` 把它连 data 一起丢掉（否则搜「欢迎来到龙餐馆」时那 20 条
      粗筛结果用户一条也看不见）；候选行按 `rel` 打标（片名对得上 / 名称未匹配）。

用法：``python3 tools/test_ondemand_ux.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_ondemand_ux_test"


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
    """替身 Response：真 MP 的 Response 在测试环境不存在，这里只保留「带字段」这一件事。"""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def get(self, k, d=None):
        return self.__dict__.get(k, d)


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")
tags = _load(PKG + ".tags", "tags.py")

_app = types.ModuleType("app")
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = _Resp
sys.modules.setdefault("app", _app)
sys.modules["app.schemas"] = _app_schemas
_rec = types.ModuleType(PKG + ".recommend")
_rec.recognize = lambda *a, **k: None
sys.modules[PKG + ".recommend"] = _rec
_site = types.ModuleType(PKG + ".sitestore")
_site.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
sys.modules[PKG + ".sitestore"] = _site
_load(PKG + ".persistence", "persistence.py")

ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")
ondemand.Response = _Resp          # 模块级名字绑到替身（源码里 `from app.schemas import Response`）
OnDemandMixin = ondemand.OnDemandMixin

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


# ---------------------------------------------------------------- [1] 真实副标题
print("[1] display_title：真实站点副标题")
_d = tags.display_title(
    "小猪佩奇 第九季 / 粉红猪小妹 第九季 (台湾) | 国英双语 内嵌简中 | 全63集 | 类型：儿童")
ok(_d["cn_title"] == "小猪佩奇 第九季", "中文主名取片名段第一段")
ok("粉红猪小妹" in _d["cn_alt"], "别名留在 cn_alt（不丢台湾译名）")
ok("(台湾)" not in _d["cn_alt"], "地区括注被去掉")
ok("全63集" in _d["spec"], "规格串含集数")
ok("国英双语" in _d["spec"], "规格串含语言")
ok(_d["subtitle"].startswith("小猪佩奇 第九季"), "subtitle 保留原文（hover 用）")

_d = tags.display_title("小猪佩奇第八季 全45集 国语中字")
ok(_d["cn_title"] == "小猪佩奇第八季", "无竖线：片名段夹带的规格词被剥出")
ok("全45集" in _d["spec"] and "国语中字" in _d["spec"], "剥出的规格进 spec")

_d = tags.display_title("咖喱辣椒（Curry & Pepper / Curry and Pepper）")
ok(_d["cn_title"] == "咖喱辣椒", "中文名后面的纯英文别名不收进 cn_alt")
ok(_d["cn_alt"] == "", "英文别名不留（切了也看不懂，反而占位置）")

# ---------------------------------------------------------------- [2] 边界
print("[2] 边界：空 / 纯英文 / 别名收敛")
ok(tags.display_title("")["cn_title"] == "", "空副标题 → cn_title 空（前端退回站点原名）")
ok(tags.display_title(None)["spec"] == "", "None 副标题不炸")
_e = tags.display_title("Peppa Pig Season 8 1080p WEB-DL")
ok(_e["cn_title"] == "", "纯英文副标题 → 不猜、不翻译，cn_title 留空")
ok(_e["subtitle"] == "Peppa Pig Season 8 1080p WEB-DL", "原文仍保留")
_many = tags.display_title("小猪佩奇第1季 | 全52集 | 主演: 某某")
ok(_many["cn_title"] == "小猪佩奇第1季", "主名不受别名收敛影响")
_alt = tags.display_title(
    "小猪佩奇第1季 / 小猪佩琦 / 粉红猪小妹 / 萌萌小猪佩奇 / 佩佩猪 / 小猪佩琪小猪佩琪")["cn_alt"]
ok(_alt.count("/") <= 1, "别名最多留 2 个（再多就把主标题挤没了）")

# ---------------------------------------------------------------- [3] 候选行字段
print("[3] media_row_from_ti：可读面齐全，老字段不丢")
_ti = {
    "title": "Peppa Pig 2004 S01 1080p WEB-DL H.264 AAC 2Audio-CHDWEB",
    "description": "小猪佩奇 第一季 | 全52集 | 国英双语 中英字幕",
    "enclosure": "https://site/download?id=1",
    "size": 5800000000.0, "seeders": 128, "site": 7, "site_name": "March",
    "downloadvolumefactor": 0.0, "hit_and_run": True,
    "category": "电视剧", "labels": ["国语", "中字"], "volume_factor": "免费",
}
_r = tags.media_row_from_ti(_ti)
ok(_r is not None, "有 enclosure → 行不为 None")
ok(_r["cn_title"] == "小猪佩奇 第一季", "候选行带 cn_title")
ok("全52集" in _r["spec"], "候选行带 spec")
ok(_r["description"] == _ti["description"], "原样保留 description")
ok(_r["category"] == "电视剧" and _r["labels"] == ["国语", "中字"], "category / labels 透出")
ok(_r["title"] == _ti["title"], "站点原标题仍叫 title（前端当小字展示）")
ok(_r["free"] is True and _r["seeders"] == 128 and _r["site_name"] == "March", "老字段一个没丢")
ok(tags.media_row_from_ti({"title": "x"}) is None, "缺 enclosure → None（口径不变）")

# ---------------------------------------------------------------- [4] 批量点播
print("[4] on_demand_batch")


class Fake(OnDemandMixin):
    def __init__(self, pool=None, pend=None):
        self._pool = dict(pool or {})
        self._pend = dict(pend or {})
        self.downloaded = []
        self.logs = []
        self._store = types.SimpleNamespace(
            journal=types.SimpleNamespace(record=lambda **k: None))

    def _od_pool_get(self, pick):
        return self._pool.get(str(pick or "").strip())

    def _ondemand_all(self):
        return dict(self._pend)

    def _ondemand_sites(self, task=None, site_ids=""):
        return [7]

    def _get_task_config(self, task_id):
        return None

    def _ondemand_download(self, row, task=None, title="", year="", content=None):
        if str(row.get("enclosure")) == "bad":
            return {"ok": False, "code": "add_failed", "message": "添加失败: 站点 503"}
        h = "h" + str(len(self.downloaded)).zfill(3)
        self.downloaded.append((h, row.get("enclosure"), title))
        return {"ok": True, "hash": h, "save_path": "/d"}

    def _log(self, msg, level="info"):
        self.logs.append(msg)


A = "https://s/dl?id=A"
B = "https://s/dl?id=B"
BAD = "bad"
POOL = {
    A: {"enclosure": A, "title": "Peppa Pig S01", "cn_title": "小猪佩奇 第一季", "site_name": "March"},
    B: {"enclosure": B, "title": "Peppa Pig S02", "cn_title": "小猪佩奇 第二季", "site_name": "March"},
    BAD: {"enclosure": BAD, "title": "x", "cn_title": "坏种", "site_name": "March"},
}

f = Fake(pool=POOL)
ok(f.on_demand_batch(picks="").success is False, "缺 picks → success=false")
ok(f.on_demand_batch(picks=",,\n\n ").success is False, "全是分隔符 → success=false")
_overflow = "\n".join([f"https://s/dl?id={i}" for i in range(ondemand._OD_BATCH_MAX + 1)])
ok(f.on_demand_batch(picks=_overflow).success is False, "超过上限 → 直接拒绝（不放行）")

f = Fake(pool=POOL)
r = f.on_demand_batch(picks=A)
ok(r.success is True and r.data["ok_count"] == 1, "单条批量 → 成功 1 条")
ok(f.downloaded[0][2] == "小猪佩奇 第一季", "台账标题用中文名（不是站点拼音原名）")

f = Fake(pool=POOL)
r = f.on_demand_batch(picks=f"{A}\n{B},\n{A}")
ok(r.data["ok_count"] == 2, "重复的 enclosure 只下一次（A 给了两次 → 共 2 条）")
ok(len(f.downloaded) == 2, "落种次数 = 去重后条数")

f = Fake(pool=POOL)
GONE = "https://s/dl?id=GONE"
r = f.on_demand_batch(picks=f"{A}\n{GONE}")
ok(r.data["ok_count"] == 1 and r.data["fail_count"] == 1, "池未命中 → 该条记失败，其余照下")
ok("过期" in r.data["fail"][0]["message"], "失败原因写明「候选已过期」（不静默）")
ok(r.success is True, "部分成功 → success=true（让前端能展示失败明细）")

f = Fake(pool=POOL)
r = f.on_demand_batch(picks=f"{A}\n{BAD}")
ok(r.data["ok_count"] == 1 and r.data["fail_count"] == 1, "一条落种失败不影响另一条")
ok("503" in r.data["fail"][0]["message"], "失败原因原样透出")

f = Fake(pool=POOL, pend={"h000": {"title": "小猪佩奇 第一季"}})
r = f.on_demand_batch(picks=A)
ok(r.data["ok"][0]["already"] is True, "已在点播中的 hash → 标 already（前端可区分）")

f = Fake(pool={BAD: POOL[BAD]})
r = f.on_demand_batch(picks=BAD)
ok(r.success is False and "全部失败" in r.message, "全失败 → success=false + 说明")

# ---------------------------------------------------------------- [5] 识别结果贯穿
print("[5] 识别结果贯穿：下载期身份 → 台账 → 整理（不再重识别）")


class _M:
    """替身 MediaInfo：只带贯穿所需的三件事。"""

    def __init__(self, mid="12225", src="themoviedb", mtype="电视剧"):
        self.media_id = mid
        self.media_source = src
        self.type = mtype


_ident = OnDemandMixin._media_identity(_M())
ok(_ident == {"media_id": "12225", "media_source": "themoviedb", "media_type": "电视剧"},
   "_media_identity：压成三元组（来源取 value / 类型取中文值）")
ok(OnDemandMixin._media_identity(None)["media_id"] == "", "media=None → 全空，不炸")
ok(OnDemandMixin._media_identity(_M(mid=""))["media_id"] == "", "media_id 缺失 → 空（不写台账）")

_rows = [{"enclosure": A}, {"enclosure": B}]
OnDemandMixin._ondemand_stamp_media(f, _rows, _M())
ok(all(r.get("media_id") == "12225" for r in _rows), "stamp：每条候选行都盖上（批量也吃得到）")
ok(_rows[0].get("media_type") == "电视剧", "stamp：类型一起盖")

_rows2 = [{"enclosure": A}]
OnDemandMixin._ondemand_stamp_media(f, _rows2, None)
ok("media_id" not in _rows2[0], "media=None → 不动行（老路径行为不变）")

_rows3 = [{"enclosure": A}]
OnDemandMixin._ondemand_stamp_media(f, _rows3, _M(mid=""))
ok("media_id" not in _rows3[0], "media_id 空 → 不盖空值（免得覆盖已有身份）")


class FakeChain(Fake):
    """带台账的替身：验证「身份从台账流到整理」。"""

    def __init__(self, hist=None):
        super().__init__()
        self._hist = hist if hist is not None else [{
            "hash": "aa", "media_id": "12225", "media_source": "themoviedb",
            "media_type": "电视剧", "title": "小猪佩奇"}]
        self.seen = None

    def _ondemand_history_read(self, limit=0):
        return list(self._hist)

    def _recommend_import(self, h, rec=None, media_hint=None):
        self.seen = {"h": h, "hint": media_hint, "rec": rec}
        return True, "ok"

    def _ondemand_import_retry(self, force=False):
        return {}


fc = FakeChain()
_idx = fc._ondemand_media_index()
ok(_idx.get("aa", {}).get("media_id") == "12225", "_ondemand_media_index：台账 → hash 索引")
ok(fc._ondemand_media_hint("aa")["media_source"] == "themoviedb", "单条查索引命中")
ok(fc._ondemand_media_hint("zz") is None, "台账没这条 → None（退回按名称识别）")

fc.seen = None
_ok, _ = fc._ondemand_import_ex("aa", "", "小猪佩奇")
ok(_ok is True, "_ondemand_import_ex：整理调用返回成功")
ok((fc.seen or {}).get("hint", {}).get("media_id") == "12225",
   "台账里的身份传到了 _recommend_import（整理不再重识别）")

fc.seen = None
fc._ondemand_import_ex("bb", "", "x")
ok((fc.seen or {}).get("hint") is None, "台账没身份 → hint=None（老逻辑照跑，不更坏）")

fc2 = FakeChain(hist=[{"hash": "cc", "title": "无身份的老行"}])
ok(fc2._ondemand_media_index() == {}, "老台账行没 media_id → 索引为空（不误报）")
fc2._ondemand_import_ex("cc", "", "无身份的老行")
ok((fc2.seen or {}).get("hint") is None, "老行整理仍走名称识别（向后兼容）")

# ---------------------------------------------------------------- [6] 整理侧
print("[6] _recommend_import：有身份就跳过 recognize")

import enum  # noqa: E402


class _MediaType(enum.Enum):
    MOVIE = "电影"
    TV = "电视剧"
    MUSIC = "音乐"
    COLLECTION = "系列"
    UNKNOWN = "未知"


class _MediaSource(str, enum.Enum):
    TMDB = "themoviedb"
    Douban = "douban"


_app_types = types.ModuleType("app.schemas.types")
_app_types.MediaType = _MediaType
_app_types.MediaSource = _MediaSource
sys.modules["app.schemas.types"] = _app_types
_app_schemas.types = _app_types

_sdklog = types.ModuleType("app.sdk.logging")
_sdklog.logger = types.SimpleNamespace(
    info=lambda *a, **k: None, warning=lambda *a, **k: None,
    error=lambda *a, **k: None, debug=lambda *a, **k: None)
_sdk = types.ModuleType("app.sdk")
_sdk.logging = _sdklog
sys.modules["app.sdk"] = _sdk
sys.modules["app.sdk.logging"] = _sdklog

_rec.RecommendEngine = object
_rec.episode_info = lambda *a, **k: {}
_rec.episode_info_files = lambda *a, **k: []
_do = types.ModuleType(PKG + ".downloader_ops")
_do.DownloaderAdapter = object
sys.modules[PKG + ".downloader_ops"] = _do
_norm = types.ModuleType(PKG + ".norm")
_norm.norm_key = lambda s: str(s or "")
sys.modules[PKG + ".norm"] = _norm
_common = types.ModuleType(PKG + ".common")
_common.MagicFlowTaskConfig = object
_common.RECOMMEND_FILES_MAX = 10
_common.RECOMMEND_FILES_TTL = 60
_common.RECOMMEND_LIVE_LIBRARY_CHECK = False
_common.RECOMMEND_SCAN_MAX = 10
_common.task_is_participating = lambda *a, **k: True
sys.modules[PKG + ".common"] = _common

_transferred = []


class _FakeTransfer:
    def manual_transfer(self, **kw):
        _transferred.append(kw)
        return True, "整理完成"


_tf = types.ModuleType("app.chain.transfer")
_tf.TransferChain = _FakeTransfer
_chain = types.ModuleType("app.chain")
_chain.transfer = _tf
sys.modules["app.chain"] = _chain
sys.modules["app.chain.transfer"] = _tf
_fschemas = types.ModuleType("app.schemas.file")
_fschemas.FileItem = lambda **kw: types.SimpleNamespace(**kw)
sys.modules["app.schemas.file"] = _fschemas

rec_mod = _load(PKG + ".features.recommend", "features/recommend.py")


def _no_recognize(*a, **k):
    raise AssertionError("有 media_hint 时不该再调 recognize")


ok(rec_mod._media_type_of("电视剧") is _MediaType.TV,
   "_media_type_of：'电视剧' → MediaType.TV 成员（不是裸字符串）")
ok(rec_mod._media_type_of("TV") is _MediaType.TV, "_media_type_of：成员名也认")
ok(rec_mod._media_type_of("") is None, "空类型 → None")
ok(rec_mod._media_type_of("乱码") is None, "认不出 → None（退回按名称识别）")
ok(rec_mod._media_source_of("themoviedb") is _MediaSource.TMDB,
   "_media_source_of：还原成 MediaSource 成员")


class _FakeTorrent:
    hash = "abc123"
    title = "Peppa Pig 2004 S09 1080p WEB-DL"
    content_path = "/downloads/peppa-s09"
    path = "/downloads/peppa-s09"
    save_path = "/downloads"


class _FakeDl:
    is_available = True

    def get_torrents(self):
        return ([_FakeTorrent()], None)

    def normalize_path(self, p):
        return p


class FakeRec(rec_mod.RecommendMixin):
    def __init__(self):
        self.logs = []

    def _get_downloader(self, name):
        return _FakeDl()

    def _log(self, msg, level="info"):
        self.logs.append(msg)

    def _tag_groups(self):
        return types.SimpleNamespace(queue_library=lambda *a, **k: "", group_of=lambda h: "")

    def _promote_resource(self, gid):
        return None

    def _fallback_after_import(self, title):
        return None

    def _transfer_already_done(self, msg):
        return False


rec_mod.recognize = _no_recognize
fr = FakeRec()
_ok2, _m2 = fr._recommend_import("abc123", {"title": "小猪佩奇"},
                                 media_hint={"media_id": "12225", "media_source": "themoviedb",
                                             "media_type": "电视剧"})
ok(_ok2 is True, "有 media_hint → 整理直接成功（recognize 未被调用）")
ok("未能识别" not in str(_m2), "没有走到名称识别分支")
ok(bool(_transferred), "manual_transfer 被调用")
_last = _transferred[-1] if _transferred else {}
ok(str(_last.get("media_id")) == "12225", "media_id 原样传给 MP 整理")
ok(_last.get("mtype") is _MediaType.TV, "mtype 传的是枚举成员（剧集不会被当电影建目录）")
ok(_last.get("media_source") is _MediaSource.TMDB, "media_source 传的是成员")

# 没 hint → 仍然走名称识别（这里 recognize 已换成会抛的桩 → 应报「未能识别」）
_ok3, _m3 = fr._recommend_import("def456", {"title": "小猪佩奇"})
ok(_ok3 is False and "未能识别" in _m3, "无 hint → 退回名称识别（向后兼容）")

# ── [6] 认不出片名时，候选必须真的到得了前端（★ 19.11.7）───────────────────
# 背景：搜「欢迎来到龙餐馆」→ TMDB 认不出 → 后端 success=false + data.candidates 20 条；
# 前端原来用 unwrapResponse 包着，它在 success===false 时直接抛错、把 data 整块丢掉
# → 用户只看见一句报错、一条候选也没有（等于搜了白搜）。两边的口径一起钉住。
_compose = (ROOT / "src/views/magicflow/composables/useOndemand.js").read_text(encoding="utf-8")
_dialog = (ROOT / "src/views/magicflow/components/dialogs/OndemandDialog.vue").read_text(encoding="utf-8")
_od_src = (ROOT / "features/ondemand.py").read_text(encoding="utf-8")
ok("unwrapResponse(await api.features.ondemandSearch" not in _compose,
   "点播搜索不得用 unwrapResponse 包（失败会把 data.candidates 一起丢掉）")
ok("Array.isArray(data.candidates)) ondemandResult.value = data" in _compose,
   "失败返回里的 candidates 仍然赋给 ondemandResult")
ok("raw?.success === false) ondemandError.value" in _compose,
   "失败原因仍写进 ondemandError（用户要知道为什么没自动选源）")
ok("row.rel >= 2" in _dialog and "名称未匹配" in _dialog,
   "候选行按 rel 打标（片名对得上 / 名称未匹配）")
ok(':type="ondemandCandidates.length ? \'warning\' : \'error\'"' in _dialog,
   "有候选时提示降级为 warning（不是红错：候选本身可用）")
ok("return Response(success=False, message=self._od_no_pick_reason(rows, media, title, sites), data=out)"
   in _od_src, "后端「没自动选源」= success False **但带 data**（前端靠它渲染粗筛结果）")
ok('"candidates": self._ondemand_rank(rows, _names)[:20]' in _od_src,
   "out.candidates 是 rank 后的（rel 标记随行下发）")

print()
if FAILS:
    print(f"❌ FAIL：{len(FAILS)} 项断言未过（共 {N} 项）")
    for x in FAILS:
        print("   -", x)
    sys.exit(1)
print(f"✅ PASS：{N} 项断言全部通过")
