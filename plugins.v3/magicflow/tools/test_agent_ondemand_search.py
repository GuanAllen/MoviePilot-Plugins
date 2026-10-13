#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播搜索自描述（★ 15.9.0 §3）离线回归 —— 真跑 features/ondemand.py，不需 MoviePilot / 网络。

背景（Master 2026-10-10）：「新版本支持翻页了么」——MP v3.1.2 自带**原生单页分页 + 来源自描述**
（``app/chain/search/manual.py::SearchManualOwner.events``，经 ``SearchChain().search_page_events``）。
我们**不做第二真值源**，只透传：

  · 客户端指定单页（``page``），MP 不自留进度；``source`` 是续页令牌；
  · 每来源事实 ``{source, site_name, page, can_continue, error}`` → 归一为统一的 ``sources[]``（§3.3）。

断言：
  [1] `_od_source_fact`：正常 → outcome=ok + can_continue；站点 id 从令牌解出；
  [2] `_od_source_fact`：error → outcome=error / 含「超时」→ timeout；
  [3] `_od_row_from_ti`：dict 有 enclosure → 归一；无 enclosure → None；
  [4] `_ondemand_search_sources`（首页）：透传 params{keyword,sites,page} → sources/candidates/totals；
  [5] 续页：带 source → 透传 params{source,page}（不再带 keyword/sites），站点从令牌解出；
  [6] MP 回 error 事件 → 抛错（由 handler 转 upstream_error，不私吞）；
  [7] PV 闸：站点全被拦 → 空结果且不调 MP；
  [8] 登记：`/agent/ondemand/search` 在清单里 + handler 是协程。

用法：``python3 tools/test_agent_ondemand_search.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_od_search_test"

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
    tags = _load(PKG + ".tags", "tags.py")
    rec = types.ModuleType(PKG + ".recommend")
    rec.recognize = lambda *a, **k: None
    sys.modules[PKG + ".recommend"] = rec
    site = types.ModuleType(PKG + ".sitestore")
    site.slot_callbacks = lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)
    sys.modules[PKG + ".sitestore"] = site
    _load(PKG + ".persistence", "persistence.py")
    ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")
    return tags, ondemand


def _load_agentapi():
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    for modname, attrs in (
        ("bonus", ("TorrentBonusInfo",)),
        ("fingerprint", ("fingerprint", "inner_fingerprint", "load_torrent_entries", "total_size")),
        ("fetcher", ("SiteCandidateTorrent",)),
        ("recommend", ("recognize",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    _load(PKG + ".common", "common.py")
    _load(PKG + ".features.pool", "features/pool.py")
    _load(PKG + ".features.api", "features/api.py")
    return _load(PKG + ".features.agentapi", "features/agentapi.py")


def main() -> int:
    tags, ondemand = _load_ondemand()
    _install_chain_stub()

    class Fake(ondemand.OnDemandMixin):
        def __init__(self, sites=(1, 2), blocked=(), allowed=True):
            self._sites = list(sites)
            self._blocked = set(blocked)
            self._allowed = allowed
            self.spent = []

        def _list_sites(self):
            return [{"id": i, "name": f"s{i}"} for i in self._sites]

        def _log(self, *a, **k):
            pass

        def _pv_block_reason(self, i):
            return "blocked" if i in self._blocked else ""

        def _pv_allow(self, i, kind, want=1):
            return self._allowed

        def _pv_spend(self, i, kind, n=1):
            self.spent.append((i, kind, n))

    print("[1] _od_source_fact：正常归一 + 站点从令牌解出")
    tok = _tok(3, "流浪地球")
    fact = Fake._od_source_fact({"source": tok, "site_name": "咖啡", "page": 0,
                                 "can_continue": True, "error": None})
    ok(fact["site"] == 3, f"site 从令牌解出（{fact['site']}）")
    ok(fact["site_name"] == "咖啡" and fact["page"] == 0, "site_name/page")
    ok(fact["can_continue"] is True and fact["outcome"] == "ok" and fact["error"] is None, "can_continue/outcome=ok")
    ok(fact["source"] == tok, "source 令牌原样透传（续页用）")

    print("[2] _od_source_fact：error / timeout")
    f_err = Fake._od_source_fact({"source": tok, "site_name": "x", "page": 1,
                                  "can_continue": False, "error": "连接被拒绝"})
    ok(f_err["outcome"] == "error" and f_err["error"] == "连接被拒绝" and f_err["can_continue"] is False, "error → outcome=error")
    f_to = Fake._od_source_fact({"source": tok, "site_name": "x", "page": 1,
                                 "can_continue": True, "error": "请求超时"})
    ok(f_to["outcome"] == "timeout", "含「超时」→ outcome=timeout")
    ok(Fake._od_source_fact({})["site"] is None, "空事实不炸")

    print("[3] _od_row_from_ti：dict 归一 / 无 enclosure → None")
    row = Fake._od_row_from_ti({"title": "T", "size": 1024, "seeders": "5", "peers": 1,
                                "enclosure": "http://x/1.torrent", "site": "2", "site_name": "聆音",
                                "downloadvolumefactor": 0, "hit_and_run": True})
    ok(row and row["enclosure"].endswith(".torrent") and row["seeders"] == 5 and row["site"] == 2, "dict 归一")
    ok(row["downloadvolumefactor"] == 0.0 and row["hit_and_run"] is True, "免费/HR 透传")
    ok(Fake._od_row_from_ti({"title": "no encl"}) is None, "无 enclosure → None")

    print("[4] _ondemand_search_sources：首页透传 MP（params{keyword,sites,page}）")
    items = [{"torrent_info": {"title": "T1", "size": 100, "seeders": 9, "enclosure": "http://a/1.torrent",
                               "site": 1, "site_name": "A", "downloadvolumefactor": 1}},
             {"torrent_info": {"title": "T2", "size": 200, "seeders": 3, "enclosure": "http://b/2.torrent",
                               "site": 2, "site_name": "B", "downloadvolumefactor": 0}}]
    FakeSearchChain.events = [
        {"type": "append", "items": []},
        {"type": "replace", "items": items, "total_items": 2, "candidate_items": 7,
         "sources": [{"source": _tok(1, "kw"), "site_name": "A", "page": 0, "can_continue": True, "error": None},
                     {"source": _tok(2, "kw"), "site_name": "B", "page": 0, "can_continue": False, "error": None}]},
        {"type": "done", "sources": []},
    ]
    f = Fake()
    out = asyncio.run(f._ondemand_search_sources("kw", [1, 2], page=0, source=""))
    ok(out["sources"] and len(out["sources"]) == 2, f"2 个来源事实（{len(out['sources'])}）")
    ok(out["total_items"] == 2 and out["candidate_items"] == 7, "total_items/candidate_items")
    ok([c["site"] for c in out["candidates"]] == [2, 1], "候选按「免费优先」排序（B 免费在前）")
    p = FakeSearchChain.last_params
    ok(p == {"keyword": "kw", "sites": [1, 2], "page": 0}, f"透传 params（{p}）")
    ok(f.spent == [(1, "ondemand", 1), (2, "ondemand", 1)], "PV 按站计 1")

    print("[5] 续页：带 source → 透传 {source,page}（不带 keyword/sites）")
    FakeSearchChain.events = [{"type": "replace", "items": [], "total_items": 0, "candidate_items": 0,
                               "sources": [{"source": tok, "site_name": "咖啡", "page": 1,
                                            "can_continue": True, "error": None}]}]
    f5 = Fake()
    out5 = asyncio.run(f5._ondemand_search_sources("", [], page=1, source=tok))
    p5 = FakeSearchChain.last_params
    ok("source" in p5 and "sites" not in p5 and p5.get("keyword") == "流浪地球", f"续页 params = source + 令牌里的 keyword（{p5}）")
    ok(p5["page"] == 1 and out5["sources"][0]["site"] == 3, "页面/站点正确")
    ok(f5.spent == [(3, "ondemand", 1)], "续页只对令牌里的站计 PV")

    print("[6] MP 回 error 事件 → 抛错（不私吞）")
    FakeSearchChain.events = [{"type": "error", "message": "搜索来源无效，请重新搜索"}]
    raised = False
    try:
        asyncio.run(Fake()._ondemand_search_sources("kw", [1], page=0))
    except Exception as e:  # noqa: BLE001
        raised = "搜索来源无效" in str(e)
    ok(raised, "error 事件 → RuntimeError")

    print("[7] PV 闸：全被拦 → 空且不调 MP")
    FakeSearchChain.last_params = {}
    f7 = Fake(allowed=False)
    out7 = asyncio.run(f7._ondemand_search_sources("kw", [1, 2], page=0))
    ok(out7["sources"] == [] and FakeSearchChain.last_params == {}, "被拦 → 空结果 + 未调 MP")
    f7b = Fake(blocked=(1, 2))
    ok(asyncio.run(f7b._ondemand_search_sources("kw", [1, 2], page=0))["sources"] == [], "站点封禁 → 空结果")

    print("[8] 登记：/agent/ondemand/search 在清单里 + handler 是协程")
    agentapi = _load_agentapi()
    entries = {e["path"]: e for e in agentapi._agent_endpoints()}
    ent = entries.get("/agent/ondemand/search")
    ok(ent is not None, "清单含 /agent/ondemand/search")
    if ent:
        ok(ent["method"] == "POST" and ent["write"] is False, "POST + 只读")
        ok(ent["handler"] == "agent_ondemand_search" and ent["returns"] == "OnDemandSearch", "handler/returns")
    h = getattr(agentapi.AgentApiMixin, "agent_ondemand_search", None)
    ok(h is not None and inspect.iscoroutinefunction(h), "handler 存在且为协程")

    print()
    if FAILS:
        print(f"❌ FAIL：{len(FAILS)}/{N} 断言失败")
        for x in FAILS:
            print("   -", x)
        return 1
    print(f"✅ PASS：{N}/{N} 断言全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
