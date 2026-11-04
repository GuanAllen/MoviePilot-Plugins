#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点播：片名相关性闸门 + 降级识别 + 「没身份就不自动选源」（19.11.6）。

现场（2026-11-02，Master 报「点播搜欢迎来到龙餐馆全是别的剧」）：
  - 正片名是《欢迎来龙餐馆》（TMDB 1391021，2026-08-08），输入多打一个「到」→ ``recognize`` 认不出；
  - 认不出就把**原串**丢给站点搜，站点按「欢迎来到」前缀命中一堆《IT 欢迎来到德里镇》；
  - ``_ondemand_pick`` 只按「免费 → 做种数 → 体积」排，**完全不看是不是同一部片** →
    自动选中 53GB 的《IT 欢迎来到德里镇》，点「下载」就下错剧。
  - 附带发现：财神（site 8）对任何中文关键词都返回满页 100 条 —— 没有相关性闸门就必然被它淹掉。

断言（全部纯函数，离线可跑）：
  [1] 降级片名能想出「龙餐馆 / 欢迎龙餐馆」，且相似度过闸
  [2] 别名表拆出「中文全名 + 英文特征词」，welcome/to/the 这类词不进特征集
  [3] 相关性分级：本剧=2，同前缀的别的剧=0，拼音名=0（不猜翻译）
  [4] 没认出片名（names=[]）→ **不自动选源**；给了身份但全是噪音 → 也不选源
  [5] 有身份且有真候选 → 选中真候选，噪声再大也不选
  [6] ``names=None`` 保持旧行为（只按免费/做种/体积），供内部兼容调用
  [7] 候选排序：强相关在前，并打 ``rel`` 标；不再只按免费/做种排

用法：``python3 tools/test_ondemand_relevance.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_od_rel_test"


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

_app = types.ModuleType("app")
_app_schemas = types.ModuleType("app.schemas")
_app_schemas.Response = type("Response", (), {})
sys.modules.setdefault("app", _app)
sys.modules["app.schemas"] = _app_schemas

_rec = types.ModuleType(PKG + ".recommend")
_rec.recognize = lambda *a, **k: None
sys.modules[PKG + ".recommend"] = _rec
_site = types.ModuleType(PKG + ".sitestore")
_site.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
sys.modules[PKG + ".sitestore"] = _site

_load(PKG + ".tags", "tags.py")
_load(PKG + ".persistence", "persistence.py")
ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")

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


def row(title, size_gb=10.0, free=True, seeders=10, desc="", site="财神"):
    return {
        "title": title,
        "description": desc,
        "size": size_gb * 1024 ** 3,
        "downloadvolumefactor": 0.0 if free else 1.0,
        "seeders": seeders,
        "peers": 0,
        "site": 8,
        "site_name": site,
        "enclosure": "https://example.invalid/d?id=%d" % (abs(hash(title)) % 100000),
        "hit_and_run": False,
    }


print("[1] 降级片名 + 相似度闸门")
vs = ondemand._od_title_variants("欢迎来到龙餐馆")
ok("龙餐馆" in vs, "尾词「龙餐馆」在降级候选里")
ok("欢迎龙餐馆" in vs, "去虚词「欢迎龙餐馆」在降级候选里")
ok(ondemand._od_name_sim("欢迎来龙餐馆", "欢迎来到龙餐馆") >= ondemand._OD_FUZZY_MIN,
   "认出《欢迎来龙餐馆》与输入相似度过闸")
ok(ondemand._od_name_sim("金龙餐馆圣诞夜", "欢迎来到龙餐馆") < ondemand._OD_FUZZY_MIN,
   "《金龙餐馆圣诞夜》过不了闸（宁可认不出，不可认错）")

print("\n[2] 别名表拆解")
cn, en = ondemand._od_profile(["小城良方", "Small Town Remedy"])
ok(cn == ["小城良方"], "中文全名单独成表")
ok({"small", "town", "remedy"} in en, "英文别名整组拆出 small/town/remedy")
_cn2, _en2 = ondemand._od_profile(["欢迎来龙餐馆", "Welcome to the Dragon Restaurant"])
ok(_en2 == [{"dragon", "restaurant"}], "welcome/to/the 不进特征集（本次踩的坑）")

print("\n[3] 相关性分级")
names = ["欢迎来龙餐馆", "Welcome to the Dragon Restaurant"]
cn, en = ondemand._od_profile(names)
derry = row("IT Welcome to Derry S01 2025 2160p MAX WEB-DL DDP5.1 Atmos",
            desc="小丑回魂：欢迎来到德里镇 第一季 / Welcome to Derry 【全8集】")
earth = row("Welcome to Earth S01 2021 2160p WEB-DL HDR H.265")
real = row("Welcome to the Dragon Restaurant 2026 2160p WEB-DL H.265",
           desc="欢迎来龙餐馆")
ok(ondemand._od_relevance(derry, cn, en) == 0, "《IT 欢迎来到德里镇》判 0（只共享「欢迎来到/welcome to」）")
ok(ondemand._od_relevance(earth, cn, en) == 0, "《Welcome to Earth》判 0")
ok(ondemand._od_relevance(real, cn, en) == 2, "本剧判 2")

print("\n[4] 没有身份就不自动选源")
junk = [derry, earth]
ok(ondemand.OnDemandMixin._ondemand_pick(None, junk, []) is None,
   "认不出片名（names=[]）→ 不自动选源")
ok(ondemand.OnDemandMixin._ondemand_pick(None, junk, names) is None,
   "给了身份但候选全是噪音 → 不自动选源")

print("\n[5] 有真候选时只选真候选")
noisy = [row("IT Welcome to Derry S01 Complete", size_gb=53.0, seeders=99),
         row("Small Town Remedy S01 2160p", size_gb=20.0, seeders=3, free=True),
         row("Xiao Cheng Liang Fang S01E25-S01E26 2160p", size_gb=2.0, seeders=50, free=True)]
_names5 = ["小城良方", "Small Town Remedy"]
picked = ondemand.OnDemandMixin._ondemand_pick(None, noisy, _names5)
ok(picked is not None and "Small Town Remedy" in str(picked.get("title")),
   "选中《Small Town Remedy》而不是做种数更高的别的剧")

print("\n[6] names=None 保持旧行为")
legacy = ondemand.OnDemandMixin._ondemand_pick(None, [derry, earth], None)
ok(legacy is not None, "不给身份时仍按旧口径选一条（兼容内部调用）")

print("\n[7] 候选排序 + rel 标记")
ranked = ondemand.OnDemandMixin._ondemand_rank(None, [derry, real, earth], names)
ok(int(ranked[0].get("rel") or 0) == 2 and "Dragon" in str(ranked[0].get("title")),
   "强相关排第一")
ok(all("rel" in r for r in ranked), "每行都带 rel")
ok([int(r["rel"]) for r in ranked][1:] == [0, 0], "噪音全部标 0")

print("\n[9] 降级识别：短名走 search_medias 拿列表后再比相似度")
from types import SimpleNamespace  # noqa: E402


class _Stub(ondemand.OnDemandMixin):
    """只带降级识别需要的最小上下文（不跑 __init__）。"""

    def __init__(self, cands):
        self.cands = cands
        self.logs = []

    def _od_search_medias(self, name):          # noqa: D401 - 覆盖真实网络调用
        return list(self.cands)

    def _log(self, msg, level="info"):
        self.logs.append((level, msg))


ondemand.recognize = lambda *a, **k: None       # 真实识别一律失败（模拟线上）
right = SimpleNamespace(title="欢迎来龙餐馆", original_title="欢迎来龙餐馆", media_id="1391021")
wrong = SimpleNamespace(title="金龙餐馆圣诞夜", original_title="金龙餐馆圣诞夜", media_id="1028186")
got = _Stub([wrong, right])._ondemand_media_fuzzy("欢迎来到龙餐馆")
ok(getattr(got, "media_id", "") == "1391021", "降级后挑中《欢迎来龙餐馆》，不挑《金龙餐馆圣诞夜》")
ok(_Stub([wrong])._ondemand_media_fuzzy("欢迎来到龙餐馆") is None,
   "只有沾边的片子时宁可不认（不出错片）")

print("\n[10] 静态护栏：候选列表不再绕过 rank 直排")
src = (ROOT / "features/ondemand.py").read_text(encoding="utf-8")
ok('"candidates": self._ondemand_rank(rows, _names)[:20]' in src,
   "on_demand 的 candidates 走 _ondemand_rank")
ok("def _ondemand_media_fuzzy" in src, "降级识别入口存在")
ok("def _od_search_medias" in src and "search_medias(MetaInfo" in src,
   "降级识别有 search_medias 兜底（短名靠它拿候选列表）")
ok("_ondemand_pick(rows, None if not rows else _names)" in src,
   "on_demand 把身份传给 _ondemand_pick")

print()
if FAILS:
    print("FAILED %d / %d" % (len(FAILS), N))
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("PASS %d / %d" % (N, N))
