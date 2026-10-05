#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · AI 友好接口（P1.5a 只读半边）离线回归测试（真跑，无需 MoviePilot）。

覆盖：
  (a) 统一信封结构（ok/code/message/data/meta；成功与 bad_param 两条路径）
  (b) 清单 ↔ 路由表一致（get_api() 的 /agent* 子集 vs GET /agent 清单）
  (c) reason_chain 合成逻辑（假对象注入：手动保留 / 欠 H&R / 账单）
  (d) 分页 cursor（limit + 游标，无重叠、末页 next_cursor=None）

用法：``python3 tools/test_agent_api.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_agent_api_test"

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
    _load(PKG + ".common", "common.py")
    _load(PKG + ".features.pool", "features/pool.py")
    _load(PKG + ".features.api", "features/api.py")
    agentapi = _load(PKG + ".features.agentapi", "features/agentapi.py")
    return agentapi


agentapi = _load_modules()
AgentApiMixin = agentapi.AgentApiMixin
ApiMixin = sys.modules[PKG + ".features.api"].ApiMixin


# ------------------------------------------------------------------ 假对象
def _hex(i: int) -> str:
    return format(i, "x").rjust(40, "0")


def _torrent(hash_string, progress=1.0, state="uploading", title="test"):
    return types.SimpleNamespace(
        hash=str(hash_string).lower(), title=title, progress=progress,
        state=state, seed_time=0.0, tags=[], tracker="",
    )


class _Ledger:
    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)


class FakeBillsStore:
    def __init__(self, bills):
        self.bills = {str(k).lower(): dict(v) for k, v in (bills or {}).items()}

    def all(self):
        return dict(self.bills)

    def get(self, h):
        return self.bills.get(str(h).lower())

    def stats(self):
        out = {"total": len(self.bills), "by_state": {}, "by_rule": {}, "by_site": {}, "opened_by": {}}
        for b in self.bills.values():
            st = b.get("state") or ""
            out["by_state"][st] = out["by_state"].get(st, 0) + 1
            ru = b.get("rule") or ""
            out["by_rule"][ru] = out["by_rule"].get(ru, 0) + 1
        return out


class Harness(AgentApiMixin):
    """带桩的最小插件实例（只读真值源全部可注入）。"""

    def __init__(self):
        self.snap = {}
        self.ledger = {}
        self.manual = set()
        self.crossseed = set()
        self.claim = set()
        self.bills = {}
        self.hr_result = (False, 0.0, 0.0, "")
        self.task_configs = []

    # ---- 只读真值源（注入点） ----
    def _tag_all_torrents(self):
        return dict(self.snap)

    def _tag_state(self):
        return _Ledger(self.ledger)

    def _agent_manual_hashes(self):
        return set(self.manual)

    def _agent_crossseed_hashes(self):
        return set(self.crossseed)

    def _agent_claim_hashes(self):
        return set(self.claim)

    def _hr_obligation(self, site, torrent, snap=None):
        return self.hr_result

    def _hrbills_store(self):
        return FakeBillsStore(self.bills)

    def _pool_dirs(self):
        return []

    def _list_sites(self):
        return []

    def _task_configs(self_):
        return {}

    def get_data_path(self):
        return Path("/tmp/mf_agent_api_test")


def main() -> int:
    print("=" * 66)
    print("魔流 · AI 友好接口（P1.5a 只读）离线回归测试")
    print("=" * 66)

    # =====================================================================
    # (a) 信封结构
    # =====================================================================
    print("\n[a] 统一信封结构")
    h = Harness()
    resp = h.agent_manifest()
    for k in ("ok", "code", "message", "data", "meta"):
        _ok(k in resp, f"成功信封含字段 {k!r}")
    _ok(resp["ok"] is True and resp["code"] == "ok", f"成功 → ok=True, code=ok")
    meta = resp["meta"]
    _ok("schema_version" in meta and meta["schema_version"] == "1.0",
        f"meta.schema_version == 1.0（{meta.get('schema_version')!r}）")
    _ok("plugin_version" in meta and str(meta["plugin_version"]), f"meta.plugin_version 非空（{meta.get('plugin_version')!r}）")
    _ok(isinstance(meta.get("took_ms"), int) and meta["took_ms"] >= 0, f"meta.took_ms 为非负 int（{meta.get('took_ms')!r}）")
    _ok(isinstance(resp["data"], dict) and "endpoints" in resp["data"], "data.endpoints 存在（清单）")

    bad = h.agent_decide("")
    _ok(bad["ok"] is False and bad["code"] == "bad_param", f"非法参数 → ok=False, code=bad_param（{bad['code']}）")
    _ok(bad["data"] is not None and bad["data"].get("field") == "hashes",
        f"bad_param 附 field=hashes（{bad.get('data')}）")
    _ok("meta" in bad and "schema_version" in bad["meta"], "失败信封同样带 meta")

    # =====================================================================
    # (b) 清单 ↔ 路由表一致
    # =====================================================================
    print("\n[b] 清单 ↔ 路由表一致")
    class H2(AgentApiMixin, ApiMixin):
        def __getattr__(self, name):
            def _dummy(*a, **k):
                return None
            return _dummy
    h2 = H2()
    routes = h2.get_api() or []
    agent_routes = [r for r in routes if str(r.get("path") or "").startswith("/agent")]
    manifest = (h2.agent_manifest() or {}).get("data") or {}
    pub = manifest.get("endpoints") or []
    reg_keys = {(r["path"], (r["methods"] or [None])[0]) for r in agent_routes}
    pub_keys = {(e["path"], e["method"]) for e in pub}
    _ok(reg_keys == pub_keys, f"路由表 {len(reg_keys)} 个 == 清单 {len(pub_keys)} 个（无多/少）")
    for e in pub:
        for key in ("path", "method", "write", "params", "returns", "version"):
            _ok(key in e, f"清单项 {e['path']} 含字段 {key!r}")

    # =====================================================================
    # (c) reason_chain 合成逻辑（假对象注入）
    # =====================================================================
    print("\n[c] reason_chain 合成逻辑")
    hh = Harness()
    ha = _hex(1)          # 手动保留 + 欠 H&R + 有账单
    hb = _hex(2)          # 跨站来源份
    hc = _hex(3)          # 已认领
    hd = _hex(4)          # 无保护 → delete_candidate
    hh.snap = {
        ha: _torrent(ha, progress=0.01, state="downloading", title="征途 2160p"),
        hb: _torrent(hb, progress=1.0, state="uploading", title="b"),
        hc: _torrent(hc, progress=1.0, state="uploading", title="c"),
        hd: _torrent(hd, progress=1.0, state="uploading", title="d"),
    }
    hh.ledger = {ha: {"site": "carpt.net", "title": "征途 2160p"}, hd: {"site": "x.org"}}
    hh.manual = {ha}
    hh.crossseed = {hb}
    hh.claim = {hc}
    hh.hr_result = (True, 24.0, 5.0, "hrbill")   # 所有种都欠 H&R（但只在 t 存在时触发）
    hh.bills = {ha: {"site": "carpt.net", "rule": "site_hr", "state": "active",
                     "seeded_h": 5.0, "need_h": 24.0, "opened_by": "open"}}

    resp = hh.agent_decide(",".join([ha, hb, hc, hd]))
    _ok(resp["ok"] is True, "decide 成功")
    items = {it["hash"]: it for it in resp["data"]["items"]}
    _ok(len(items) == 4, f"返回 4 个 hash（{len(items)}）")

    a = items[ha]
    _ok(a["verdict"] == "blocked", f"ha 手动+欠H&R → blocked（{a['verdict']}）")
    rules = [rc["rule"] for rc in a["reason_chain"]]
    _ok("delete_gate/manual_protect" in rules, f"ha 含 manual_protect 规则（{rules}）")
    _ok("hr/bill" in rules, f"ha 含 hr/bill 规则（{rules}）")
    _ok(any(rc["rule"] == "hr/bill" and rc["source_of_truth"] == "hr_bills.json" for rc in a["reason_chain"]),
        "hr/bill 真值源 = hr_bills.json（src=hrbill）")
    _ok(any(rc.get("inputs", {}).get("seeded_h") == 5.0 and rc.get("inputs", {}).get("need_h") == 24.0
            for rc in a["reason_chain"]), "hr/bill inputs 带 seeded_h=5.0/need_h=24.0")
    scopes = {p["scope"] for p in a["protection"]}
    _ok("manual" in scopes and "hr_bill" in scopes, f"ha protection 含 manual+hr_bill（{scopes}）")
    _ok(len(a["bills"]) == 1 and a["bills"][0]["rule"] == "site_hr", "ha bills 含 1 条 site_hr 账单")
    _ok(a["progress"] == 0.01, f"ha progress=0.01（{a['progress']}）")
    # 每条 reason_chain 都有 rule/verdict/inputs/source_of_truth/at
    for rc in a["reason_chain"]:
        for k in ("rule", "verdict", "inputs", "source_of_truth", "at"):
            _ok(k in rc, f"reason_chain 单条含 {k!r}（rule={rc.get('rule')}）")

    _ok(items[hb]["verdict"] == "blocked" and any(rc["rule"] == "delete_gate/crossseed_source"
        for rc in items[hb]["reason_chain"]), "hb 跨站来源份 → blocked")
    _ok(items[hc]["verdict"] == "blocked" and any(rc["rule"] == "delete_gate/claim"
        for rc in items[hc]["reason_chain"]), "hc 已认领 → blocked")

    # hd：无保护但 hd.hr_result 是欠债 → 也会 blocked？hd 的 t 存在 → hr_obligation=True → blocked
    # 为测「delete_candidate」，单独给一个不欠债的种：
    hx = _hex(9)
    hh.snap[hx] = _torrent(hx, progress=1.0, state="uploading", title="x")
    hh.ledger[hx] = {"site": "x.org"}
    hh.hr_result = (False, 0.0, 0.0, "")
    resp2 = hh.agent_decide(hx)
    x = resp2["data"]["items"][0]
    _ok(x["verdict"] == "delete_candidate", f"无保护且已知种 → delete_candidate（{x['verdict']}）")
    _ok(x["reason_chain"] == [] and x["protection"] == [], "无保护 → reason_chain/protection 空")

    # 未知 hash（不在 snap 也不在 ledger）→ keep
    hh.hr_result = (False, 0.0, 0.0, "")
    hy = _hex(10)
    resp3 = hh.agent_decide(hy)
    y = resp3["data"]["items"][0]
    _ok(y["verdict"] == "keep", f"未知 hash → keep（{y['verdict']}）")

    # =====================================================================
    # (d) 分页 cursor
    # =====================================================================
    print("\n[d] 分页 cursor")
    hp = Harness()
    hp.bills = {f"h{i}": {"site": "s", "rule": "site_hr", "state": "active",
                          "need_h": 24.0, "seeded_h": i} for i in range(5)}
    p1 = hp.agent_bills(limit=2)
    _ok(p1["ok"] and p1["data"]["total"] == 5, f"第 1 页 total=5（{p1['data']['total']}）")
    _ok(len(p1["data"]["items"]) == 2, f"第 1 页 2 条（{len(p1['data']['items'])}）")
    _ok(p1["data"]["next_cursor"] == "h1", f"第 1 页 next_cursor=h1（{p1['data']['next_cursor']}）")
    p2 = hp.agent_bills(limit=2, cursor=p1["data"]["next_cursor"])
    _ok([i["hash"] for i in p2["data"]["items"]] == ["h2", "h3"], "第 2 页 = h2,h3（无重叠、顺序稳定）")
    p3 = hp.agent_bills(limit=2, cursor="h3")
    _ok([i["hash"] for i in p3["data"]["items"]] == ["h4"], "第 3 页 = h4")
    _ok(p3["data"]["next_cursor"] is None, "末页 next_cursor=None")

    # 过滤 site/state/rule
    hp.bills["h9"] = {"site": "other", "rule": "unknown", "state": "void", "need_h": 0.0, "seeded_h": 0.0}
    f = hp.agent_bills(site="other")
    _ok(f["data"]["total"] == 1 and f["data"]["items"][0]["hash"] == "h9", "按 site 过滤命中 1 条")
    f2 = hp.agent_bills(state="void", rule="unknown")
    _ok(f2["data"]["total"] == 1 and f2["data"]["items"][0]["hash"] == "h9", "按 state+rule 过滤命中 1 条")

    # 单条（hash 需 40/64 位 hex）
    hp.bills[_hex(0)] = {"site": "s", "rule": "site_hr", "state": "active",
                         "need_h": 24.0, "seeded_h": 0.0}
    one = hp.agent_bill(_hex(0))
    _ok(one["ok"] and one["data"]["hash"] == _hex(0) and one["data"]["seeded_h"] == 0,
        f"单条账单 {_hex(0)[:8]}…（seeded_h=0）")
    nf = hp.agent_bill(_hex(99))
    _ok(nf["ok"] is False and nf["code"] == "not_found", f"单条不存在 → not_found（{nf['code']}）")
    bp = hp.agent_bill("h0")
    _ok(bp["ok"] is False and bp["code"] == "bad_param", f"单条非法 hash → bad_param（{bp['code']}）")

    # =====================================================================
    # ★ 不泄密：出口统一剥密（_agent_scrub）
    _scrub = agentapi._agent_scrub
    scrubbed = _scrub({
        "token": "abc123", "iyuu_token": "xyz", "cookie": "ck",
        "nested": {"credential": "secret!", "keep": 1},
        "list": [{"passkey": "pk"}, {"apikey": ""}],
        "token_set_flag": False, "token_flag": False, "empty": "",
    })
    _ok(scrubbed["token"] == "***" and scrubbed["token_set"] is True, "token → *** + token_set")
    _ok(scrubbed["iyuu_token"] == "***" and scrubbed["cookie"] == "***", "iyuu_token/cookie 被遮")
    _ok(scrubbed["nested"]["credential"] == "***" and scrubbed["nested"]["keep"] == 1, "嵌套 dict 递归剥密")
    _ok(scrubbed["list"][0]["passkey"] == "***" and scrubbed["list"][1]["apikey"] == "", "list 递归；空串不遮")
    _ok(scrubbed["empty"] == "" and scrubbed["token_flag"] is False, "空串/False 原样保留")
    _ok(_scrub("plain") == "plain" and _scrub(7) == 7, "标量原样")

    # =====================================================================
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
