#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · `GET /agent/sites/types`（站点「分类类型」映射）离线回归测试（真跑，无需 MoviePilot）。

覆盖（★ 类型真值一律用 MP，Master 2026-10-10）：
  (a) 纯函数 ``common.site_type_rows``：归一 / 排序 / 容错（缺字段、非法项、list 型 media_type）
  (b) handler ``agent_sites_types``：统一信封 + reason_chain + 空索引 → ``empty`` 错误码
  (c) 登记制：端点进 ``GET /agent`` 清单，且 ``get_api()`` 路由表里有它

用法：``python3 tools/test_agent_sites_types.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_agent_sites_types_test"

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


# ------------------------------------------------------------------ 离线加载（同 check_agent_manifest.py 套路）
def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub_app() -> None:
    for name, attr_map in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attr_map.items():
            setattr(m, k, v)


def _load_modules():
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
    common = _load(PKG + ".common", "common.py")
    _load(PKG + ".features.pool", "features/pool.py")
    apimod = _load(PKG + ".features.api", "features/api.py")
    agentapi = _load(PKG + ".features.agentapi", "features/agentapi.py")
    agentledger = _load(PKG + ".features.agentledger", "features/agentledger.py")
    return common, apimod, agentapi, agentledger


common, apimod, agentapi, agentledger = _load_modules()
AgentApiMixin = agentapi.AgentApiMixin
AgentLedgerMixin = agentledger.AgentLedgerMixin
ApiMixin = apimod.ApiMixin


class Harness(AgentApiMixin, AgentLedgerMixin):
    pass


# ------------------------------------------------------------------ 假站点索引器
_FAKE_INDEXERS = [
    {"id": 9, "name": "馒头", "domain": "M-Team.Club", "media_type": "movie",
     "category": {"movie": [{"id": 434, "cat": "Movie", "desc": "电影"}],
                  "tv": [],
                  "music": [{"id": 406, "cat": "MusicVideo", "desc": "MV"},
                            {"id": 434, "cat": "Audio", "desc": "无损音频"}]}},
    {"id": 1, "name": "学校", "domain": "btschool.club",
     "category": {"movie": [{"id": 405, "cat": "Movie"}],
                  "tv": [{"id": 406, "cat": "TV"}],
                  "music": [{"id": 409, "cat": "Music"}]}},
    {"id": 16, "name": "YemaPT", "domain": "yemapt.org", "media_type": ["movie", "tv"],
     "category": {"movie": [{"id": 4, "cat": "A"}, {"id": 14, "cat": "B"}],
                  "tv": [{"id": 5, "cat": "C"}],
                  "music": [{"id": 8, "cat": "M"}, {"id": 16, "cat": "N"}]}},
    "garbage",  # 非 dict → 跳过
    {"id": None, "name": "无id", "category": {"music": [{"id": 406}]}},  # 缺 id → 排后
    {"id": 7, "name": "PT时间", "domain": "pttime.org",
     "category": {"movie": [], "tv": [], "music": [{"id": 408, "cat": "Music"}]}},
]


class _FakeSitesHelper:
    def __init__(self, indexers):
        self._indexers = indexers

    def get_indexers(self):
        return list(self._indexers)


def _install_sites_helper(indexers):
    """注入假 ``app.sdk.network.SitesHelper``（handler 内 ``from app.sdk.network import SitesHelper``）。"""
    mod = sys.modules.get("app.sdk.network")
    if mod is None:
        mod = types.ModuleType("app.sdk.network")
        sys.modules["app.sdk.network"] = mod
        setattr(sys.modules["app.sdk"], "network", mod)
    mod.SitesHelper = lambda: _FakeSitesHelper(indexers)


# ------------------------------------------------------------------ 用例
def test_pure_normalize():
    rows = common.site_type_rows(_FAKE_INDEXERS)
    ids = [r["id"] for r in rows]
    _ok(ids[:3] == [1, 7, 9], f"按站点 id 升序（缺 id 排后）: {ids}")
    _ok(ids[-1] is None, "缺 id 的站点排在最后")
    by = {r["id"]: r for r in rows if r["id"] is not None}
    _ok(by[9]["domain"] == "m-team.club", "domain 转小写")
    _ok([c["id"] for c in by[16]["music"]] == [8, 16], "YemaPT 音乐 id = [8,16]（各站不统一）")
    _ok(by[16]["declared_media_type"] == "movie,tv", "list 型 media_type 归一为逗号串")
    _ok(by[7]["supports"] == {"movie": False, "tv": False, "music": True}, "supports 按类目有无")
    _ok(by[16]["category_count"] == 5, "category_count 合计")
    _ok(all(isinstance(r["movie"], list) for r in rows), "每个站点恒有 movie/tv/music 三个列表")
    # 空 / 非法输入不炸
    _ok(common.site_type_rows(None) == [], "None → []")
    _ok(common.site_type_rows([]) == [], "空列表 → []")


def test_handler_ok():
    _install_sites_helper(_FAKE_INDEXERS)
    resp = Harness().agent_sites_types()
    _ok(resp["ok"] is True and resp["code"] == "ok", "信封 ok")
    d = resp["data"]
    _ok(d["count"] == 5, f"count=5（跳过非 dict）: {d['count']}")
    _ok(d["with_music"] == 5, f"with_music=5: {d['with_music']}")
    _ok(isinstance(d["sites"], list) and len(d["sites"]) == 5, "sites 列表")
    rc = resp["meta"].get("reason_chain") or []
    _ok(bool(rc) and "SitesHelper" in rc[0]["source_of_truth"], "reason_chain.source_of_truth 指向 MP")


def test_handler_empty():
    _install_sites_helper([])
    resp = Harness().agent_sites_types()
    _ok(resp["ok"] is False and resp["code"] == "empty", "空索引 → code=empty（如实上报，不私回退）")


def test_registered():
    eps = agentapi._agent_endpoints()
    paths = [e["path"] for e in eps]
    _ok("/agent/sites/types" in paths, "清单含 /agent/sites/types（登记制）")
    ep = next(e for e in eps if e["path"] == "/agent/sites/types")
    _ok(ep["method"] == "GET" and ep.get("write") is False, "GET 且只读")
    _ok(ep["handler"] == "agent_sites_types" and callable(getattr(Harness, "agent_sites_types", None)),
       "handler 名 ↔ 方法存在")
    # 路由注册表 ↔ 清单一致性由 tools/check_agent_manifest.py 兜底（此处不重复造桩）。


def main() -> int:
    print("=" * 66)
    print("魔流 · GET /agent/sites/types 离线回归")
    print("=" * 66)
    test_pure_normalize()
    test_handler_ok()
    test_handler_empty()
    test_registered()
    print("\n" + "=" * 66)
    print(f"PASS：{CHECKS} 项断言全部通过 ✅")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"\n{e}")
        raise SystemExit(1)
