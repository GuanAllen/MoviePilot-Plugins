#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播 add「按 pick 分页续搜」（★ 17.1.1）离线回归 —— 真跑 features/ondemand.py，不需 MoviePilot / 网络。

背景（Master 报）：``/agent/ondemand/add`` 加不进**排在第 2 页**的候选
（实例：2010 版 720p CMCT id=6782）—— 根因是 add 只在 ``_ondemand_search`` 的**第 1 页**里逐条比
``enclosure``，而 MP ``search_by_title(page=)`` **一次只给一页** ⇒「搜索翻页看得到、add 加不进去」。

本版修法（三处）：
  · 新增 ``_ondemand_find_pick``：逐页续搜到**命中 / 页尾 / 上限** ``_OD_ADD_MAX_PAGES=3``（有界，逐页过 PV 闸）；
  · ``_mp_search_title(..., page=N)`` + ``_ondemand_search(..., page=N)``：把页号透传给 MP（老版无 ``page`` 形参则不传）；
  · ``_ondemand_search_sources`` 把本轮候选写进 ``_od_last``：让 ``/agent/ondemand/search → /agent/ondemand/add`` 真正衔接。

断言：
  [1] 第 2 页命中：page0 无 → page1 有 → **命中即停**（不再多搜第 3 页）；
  [2] 第 1 页命中：只搜 1 页（不白翻页烧 PV）；
  [3] 全页无命中：搜满 ``_OD_ADD_MAX_PAGES`` 页即停（有界，不会无限续）；
  [4] 某页空 → 判**页尾**停（不再试下一页）；
  [5] 第一个关键词有货 → 不试「片名+年份」；第一个关键词全空 → 才试（**老行为保留**）；
  [6] ``_ondemand_search(page=N)`` 把 N 透传给 ``_mp_search_title``，且每页各自按站计 PV；
  [7] ``_ondemand_add`` 干跑：命中即回计划；第二次同 query 吃缓存**不再重搜**；
  [8] 静态护栏：``features/crossseed.py::_mp_search_title`` 必须带 ``page`` 形参并真透传（删掉会**静默退化**成只搜第 1 页）；
  [9] ``_ondemand_search_sources`` 把候选写进 ``_od_last``（add 的 ``_ondemand_cache_get`` 同口径可取）。

用法：``python3 tools/test_ondemand_add_pages.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import ast
import asyncio
import base64
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_od_add_pages_test"

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


def _stub_app():
    for name, attrs in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {}),
                               "MediaType": type("MediaType", (), {"MUSIC": "music"})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attrs.items():
            setattr(m, k, v)


def _tok(site, keyword, sid="x" * 8):
    raw = json.dumps([str(site), keyword, sid], ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_source(source: str):
    s = str(source) + "=" * (-len(source) % 4)
    site, keyword, sid = json.loads(base64.urlsafe_b64decode(s))
    if not keyword or not sid:
        raise ValueError("bad")
    return site, keyword, sid


class FakeSearchChain:
    events: list = []
    last_params: dict = {}

    def __init__(self):
        pass

    async def search_page_events(self, *, params):
        FakeSearchChain.last_params = dict(params)
        for e in list(FakeSearchChain.events):
            yield e


def _install_chain_stub():
    """给 ondemand 注入假 ``app.chain.search``（真 SearchChain 需整机 MP）。"""
    app = sys.modules["app"]
    chain = types.ModuleType("app.chain")
    search = types.ModuleType("app.chain.search")
    manual = types.ModuleType("app.chain.search.manual")
    manual.decode_source = _decode_source
    search.manual = manual
    search.SearchChain = FakeSearchChain
    chain.search = search
    setattr(app, "chain", chain)
    sys.modules["app.chain"] = chain
    sys.modules["app.chain.search"] = search
    sys.modules["app.chain.search.manual"] = manual


def _load_ondemand():
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    _load(PKG + ".tags", "tags.py")
    rec = types.ModuleType(PKG + ".recommend")
    rec.recognize = lambda *a, **k: None
    sys.modules[PKG + ".recommend"] = rec
    site = types.ModuleType(PKG + ".sitestore")
    site.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
    sys.modules[PKG + ".sitestore"] = site
    _load(PKG + ".persistence", "persistence.py")
    return _load(PKG + ".features.ondemand", "features/ondemand.py")


def _row(enclosure: str, title: str = "T") -> dict:
    return {"title": title, "size": 1024, "seeders": 5, "peers": 1, "enclosure": enclosure,
            "site": 1, "site_name": "A", "downloadvolumefactor": 1, "hit_and_run": False}


def _crossseed_source() -> str:
    return (ROOT / "features/crossseed.py").read_text(encoding="utf-8")


def main() -> int:
    ondemand = _load_ondemand()
    _install_chain_stub()
    maxp = int(ondemand._OD_ADD_MAX_PAGES)

    class Fake(ondemand.OnDemandMixin):
        """``_mp_search_title`` 换成「按 (关键词, 页) 回话」的假 MP；其余走真实现。"""

        def __init__(self, pages=None, sites=(1, 2)):
            self._sites = list(sites)
            self.pages = dict(pages or {})
            self.calls = []
            self.spent = []

        def _list_sites(self):
            return [{"id": i, "name": f"s{i}"} for i in self._sites]

        def _log(self, *a, **k):
            pass

        def _pv_block_reason(self, i):
            return ""

        def _pv_allow(self, i, kind, want=1):
            return True

        def _pv_spend(self, i, kind, n=1):
            self.spent.append((i, kind, n))

        def _mp_search_title(self, keyword, sites, mtype="", page=0):
            self.calls.append((keyword, page))
            return [dict(r) for r in (self.pages.get((keyword, page)) or [])]

        def get_downloader_prefs(self):
            return types.SimpleNamespace(data={"save_path": "/tmp/dl"})

    print(f"[0] 续页上限常量：_OD_ADD_MAX_PAGES = {maxp}")
    ok(maxp >= 2, "上限至少 2 页（否则修不了第 2 页命中的缺口）")

    print("[1] 第 2 页命中 → 续页拿到 pick，且命中即停")
    pick = "http://a/p2.torrent"
    f = Fake({("流浪地球", 0): [_row("http://a/p0.torrent")],
              ("流浪地球", 1): [_row(pick)],
              ("流浪地球", 2): [_row("http://a/p2x.torrent")]})
    rows = f._ondemand_find_pick("流浪地球", "", [1, 2], pick)
    ok(any(r["enclosure"] == pick for r in rows), "第 2 页的 pick 被找到（原来报「候选未命中」）")
    ok(f.calls == [("流浪地球", 0), ("流浪地球", 1)], f"命中即停，不多搜第 3 页（{f.calls}）")

    print("[2] 第 1 页命中 → 只搜 1 页")
    p1 = "http://a/p1.torrent"
    f = Fake({("流浪地球", 0): [_row(p1)]})
    rows = f._ondemand_find_pick("流浪地球", "", [1, 2], p1)
    ok(any(r["enclosure"] == p1 for r in rows) and len(f.calls) == 1, f"1 次搜索（{f.calls}）")

    print("[3] 全页无命中 → 搜满上限即停（有界）")
    f = Fake({("流浪地球", i): [_row(f"http://a/x{i}.torrent")] for i in range(maxp + 3)})
    rows = f._ondemand_find_pick("流浪地球", "", [1, 2], "http://a/none.torrent")
    ok(len(f.calls) == maxp, f"恰好 {maxp} 页（{f.calls}）")
    ok(len(rows) == maxp, f"返回「到此为止已见过的候选」{len(rows)} 条（干跑也能列出）")

    print("[4] 某页空 → 页尾即停")
    f = Fake({("流浪地球", 0): [_row("http://a/p0.torrent")]})
    f._ondemand_find_pick("流浪地球", "", [1, 2], "http://a/none.torrent")
    ok(f.calls == [("流浪地球", 0), ("流浪地球", 1)], f"第 1 页空就停（{f.calls}）")

    print("[5] 关键词回退口径与改前一致（有货不试年份 / 全空才试）")
    f = Fake({("流浪地球", 0): [_row("http://a/p0.torrent")]})
    f._ondemand_find_pick("流浪地球", "2019", [1, 2], "http://a/none.torrent")
    ok(not any(k == "流浪地球 2019" for k, _ in f.calls), f"第一个关键词有货 → 不试年份（{f.calls}）")
    f = Fake({("流浪地球 2019", 0): [_row("http://a/y.torrent")]})
    rows = f._ondemand_find_pick("流浪地球", "2019", [1, 2], "http://a/y.torrent")
    ok(("流浪地球 2019", 0) in f.calls and any(r["enclosure"] == "http://a/y.torrent" for r in rows),
       f"全空才试「片名+年份」（{f.calls}）")

    print("[6] _ondemand_search(page=N) 透传页号 + 每页各站计 PV")
    f = Fake({("kw", 2): [_row("http://a/p2.torrent")]})
    rows = f._ondemand_search("kw", [1, 2], page=2)
    ok(len(rows) == 1 and f.calls == [("kw", 2)], f"page 透传（{f.calls}）")
    ok(f.spent == [(1, "ondemand", 1), (2, "ondemand", 1)], f"PV 按站计 1（{f.spent}）")
    f2 = Fake({("kw", 0): [_row("http://a/p0.torrent")]})
    f2._ondemand_search("kw", [1, 2])
    ok(f2.calls == [("kw", 0)], "缺省仍是第 0 页（老调用点行为不变）")

    print("[7] _ondemand_add 干跑：命中即回计划 + 第二次吃缓存不重搜")
    pick7 = "http://a/pick7.torrent"
    f = Fake({("流浪地球", 0): [_row("http://a/other.torrent")],
              ("流浪地球", 1): [_row(pick7)]})
    r1 = f._ondemand_add("流浪地球", site_ids="1,2", pick=pick7, apply=False)
    ok(r1.get("ok") is True and r1.get("applied") is False, f"干跑 ok（{r1.get('message', '')}）")
    ok((r1.get("plan") or {}).get("title") == "T", "干跑计划含选中的那条（title=T）")
    ok(f.calls == [("流浪地球", 0), ("流浪地球", 1)], f"add 续页找到第 2 页的 pick（{f.calls}）")
    n_before = len(f.calls)
    r2 = f._ondemand_add("流浪地球", site_ids="1,2", pick=pick7, apply=False)
    ok(r2.get("ok") is True and len(f.calls) == n_before, "第二次同 query → 吃 _od_last，不再重搜")
    r3 = f._ondemand_add("流浪地球", site_ids="1,2", pick="http://a/never.torrent", apply=False)
    ok(r3.get("ok") is False and "候选未命中" in str(r3.get("message") or ""), "缓存里没有的 pick → 如实回报未命中")

    print("[8] 静态护栏：crossseed._mp_search_title 带 page 形参并真透传")
    tree = ast.parse(_crossseed_source())
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_mp_search_title"), None)
    ok(fn is not None, "找到 features/crossseed.py::_mp_search_title")
    a = fn.args if fn is not None else None
    ok(a is not None and "page" in [x.arg for x in a.args], "形参含 page（否则 ondemand 的 page= 会 TypeError → 静默搜不到）")
    subs = [t for n in ast.walk(fn) if isinstance(n, ast.Assign) for t in n.targets
            if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "page"]
    ok(bool(subs), "函数体真把 page 塞进 kwargs（防「收下参数不转发」）")

    print("[9] _ondemand_search_sources：候选写进 _od_last（search → add 衔接）")
    items = [{"torrent_info": _row("http://a/1.torrent", "T1")},
             {"torrent_info": _row("http://a/2.torrent", "T2")}]
    FakeSearchChain.events = [
        {"type": "append", "items": []},
        {"type": "replace", "items": items, "total_items": 2, "candidate_items": 2,
         "sources": [{"source": _tok(1, "kw"), "site_name": "A", "page": 0,
                      "can_continue": True, "error": None}]},
        {"type": "done", "sources": []},
    ]
    f = Fake()
    out = asyncio.run(f._ondemand_search_sources("kw", [1, 2], page=0, source=""))
    ok(len(out["candidates"]) == 2, f"候选 2 条（{len(out['candidates'])}）")
    cached = f._ondemand_cache_get("kw", [1, 2])
    ok(cached is not None and len(cached) == 2, "search 后 _od_last 里有这两条（add 可直接命中，不再重搜）")
    ok(f._ondemand_cache_get("kw", [1, 2, 3]) is None, "站点集合不一致 → 不吃缓存（不串味）")

    print()
    if FAILS:
        print(f"❌ FAIL：{len(FAILS)}/{N} 断言未过")
        for x in FAILS:
            print("   -", x)
        return 1
    print(f"✅ PASS：{N}/{N} 断言全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
