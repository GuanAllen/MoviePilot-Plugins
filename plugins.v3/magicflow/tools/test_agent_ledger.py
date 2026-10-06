#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · AI 只读门面 P1.5b（agentledger）离线回归测试（真跑，无需 MoviePilot）。

覆盖：
  (a) 信封与错误码（not_found / bad_param）
  (b) 真值表分页 limit/cursor 语义（limit=0 全量、无重叠、末页 next_cursor=None）
  (c) 过滤（filter k=v / 显式 site/state/rule）
  (d) 列字典结构（name/type/unit/enum/nullable）
  (e) 字段投影（fields）
  (f) schema 端点结构（types + tables）
  (g) 报表层 overview/tasks/task_detail/operations/pool/trend/rules/settings/health 响应形状
  (h) check_agent_parity.py 自身的抽取/归一化/分类/白名单逻辑

用法：``python3 tools/test_agent_ledger.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_agent_ledger_test"

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


# ------------------------------------------------------------------ 离线加载
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
    agentledger = _load(PKG + ".features.agentledger", "features/agentledger.py")
    return agentapi, agentledger


agentapi, agentledger = _load_modules()
AgentApiMixin = agentapi.AgentApiMixin
AgentLedgerMixin = agentledger.AgentLedgerMixin
LEDGER_TABLES = agentledger.LEDGER_TABLES


# ------------------------------------------------------------------ 假对象
def _hex(i: int) -> str:
    return format(i, "x").rjust(40, "0")


class FakeTagState:
    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)


class FakeFileGroups:
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


class FakeResp:
    def __init__(self, data=None, message="OK", success=True):
        self.data = data
        self.message = message
        self.success = success


class FakeJournal:
    def __init__(self, records):
        self.records = list(records)

    def list_recent(self, limit=100, kind=None):
        return list(self.records)

    def list_by_task(self, task_id, kind=None, limit=50):
        return [r for r in self.records if r["task_id"] == task_id][:limit]


class FakeTaskStates:
    def __init__(self, states):
        self.states = list(states)

    def list_all(self):
        return list(self.states)


class FakeStore:
    def __init__(self, journal=None, task_states=None, data_dir=None):
        self.journal = journal
        self.task_states = task_states
        self.data_dir = data_dir

    def get_task_stats(self, task_id):
        return {"seeding_count": 3, "last_candidate_total": 12, "last_candidate_passed": 5}


class Harness(AgentApiMixin, AgentLedgerMixin):
    """带桩的最小插件实例（只读真值源全部可注入）。"""

    def __init__(self):
        self.seed = {}
        self.groups = {}
        self.bills = {}
        self.journal_records = []
        self.task_states = []
        self._store = FakeStore()
        self._task_configs = {}

    # ---- 真值源注入点 ----
    def _tag_state(self):
        return FakeTagState(self.seed)

    def _tag_groups(self):
        return FakeFileGroups(self.groups)

    def _hrbills_store(self):
        return FakeBillsStore(self.bills)

    def _deck_rows(self, **kw):
        return [{"deck_id": "d1-1", "seed_id": _hex(0), "site_id": 1,
                 "task_type_id": "bonus", "task_id": "t1", "a_contrib": 1.5,
                 "size_gb": 2.0, "frozen": False, "frozen_at": None,
                 "created": 1.0, "updated": 2.0}]

    def get_data_path(self):
        return Path("/tmp/mf_agent_ledger_test")

    # ---- 报表层复用点（UI 同源）注入 ----
    def get_status(self):
        return FakeResp({"summary": {"total_tasks": 2}, "tasks": [], "options": {},
                         "enabled": True, "version": "11.2.1"})

    def agent_state(self):
        return {"ok": True, "code": "ok", "data": {"tasks": {"total": 2}},
                "meta": {}}

    def _build_task_list(self):
        return [{"id": "t1", "name": "任务一", "run_mode": "running", "enabled": True}]

    def _build_task_detail(self, task_id):
        if task_id == "t1":
            return {"id": "t1", "name": "任务一", "run_mode": "running",
                    "site_name": "carpt", "task_type": "bonus"}
        return None

    def pool_info(self, path=""):
        return FakeResp({"name": "movie", "path": "/movie", "total": 100,
                         "used": 70, "free": 30, "pct": 70.0, "threshold": 0.8,
                         "budget_gb": 10.0, "pools": []})

    def get_trend(self, scope="all", id="", hours=72):
        return FakeResp({"hours": 72, "keep": 168, "series": {}, "names": {}})

    def get_site_rules(self, action="", site="", hours="", hr=""):
        return FakeResp({"rules": [{"domain": "carpt.net", "hr": True,
                                    "seed_hours": 24.0, "source": "builtin"}],
                         "rulepack": {"ok": True}})

    def get_defaults(self):
        return FakeResp({"name": "默认模板", "task_type": "bonus"})

    def get_downloader_prefs(self):
        return FakeResp({"available": True, "download_limit_kbps": 0})

    def get_health(self):
        return FakeResp({"level": "ok", "ok": True, "counts": {"error": 0},
                         "issues": [], "checked_at": 1.0})

    # ---- P1.5c 功能域只读 handler（UI 同源）注入 ----
    def get_task_bonus(self, task_id):
        return FakeResp({"torrents": [{"hash": _hex(1), "title": "t1", "is_protected": False}],
                         "total_bonus": 12.5, "torrent_count": 1, "protected_count": 0,
                         "site": {"domain": "carpt.net"}})

    def get_task_candidates(self, task_id):
        return FakeResp({"candidates": [{"hash": _hex(2), "title": "c1"}], "total": 1,
                         "reason_counts": {"free": 1}})

    def get_task_handover(self, task_id):
        return FakeResp({"handover": [{"hash": _hex(3), "to_task": "t2"}], "total": 1})

    def get_recommend_list(self):
        return FakeResp({"items": [{"media": {"title": "x"}, "state": "pending"}], "total": 1})

    def get_crossseed(self, action="", hash="", site=""):
        return FakeResp({"pending": [{"hash": _hex(4)}], "sources": [], "tasks": []})

    def get_reseed(self):
        return FakeResp({"sites": [], "enabled": True, "last": {"ok": True}})

    def douban_service_status(self, action=""):
        return FakeResp({"count": 3, "progress": 0.5, "running": True})

    def get_live_state(self, force=False, site_id=0):
        return FakeResp({"sites": [{"site_id": 1, "live": {}}], "traffic": {}})

    def get_signin_state(self, days=7):
        return FakeResp({"sites": [{"domain": "carpt.net"}], "records": []})

    def get_exam_state(self, force=False, site_id=0, include_pass=False):
        return FakeResp({"sites": [], "count": 0, "enabled": True, "ts": 1.0})

    def silent_pool(self, limit=400, records=60):
        return FakeResp({"torrents": [], "stats": {"total": 0}})

    def get_claim_state(self, site_id=None):
        return FakeResp({"sites": [], "cap_total": 0, "records": []})

    def get_cloud_state(self):
        return FakeResp({"enabled": False, "plan": {}, "records": []})

    def test_cloud(self):
        return FakeResp({"ok": True, "storage": "openlist"})

    def get_fallback_state(self, resolve_paths=False):
        return FakeResp({"enabled": False, "last": {}})

    def get_iyuu_sites(self):
        return FakeResp({"sites": [{"domain": "carpt.net"}], "total": 1})

    def test_iyuu(self):
        return FakeResp({"ok": True, "latency_ms": 12})

    def get_events(self, since=0, limit=200, kind="", task_id="", level="",
                   min_level="", include_open=0):
        return FakeResp({"events": [{"ts": 1.0, "kind": "deletion"}], "total": 1})

    def get_tag_model(self, action="status", hash="", state="", site="",
                      limit=20, confirm=""):
        return FakeResp({"enabled": True, "ledger_count": 5, "rules": []})


def _make_harness() -> Harness:
    h = Harness()
    h._store = FakeStore(
        journal=FakeJournal(h.journal_records),
        task_states=FakeTaskStates(h.task_states),
        data_dir=Path("/tmp/mf_agent_ledger_test"),
    )
    return h


def _seed_rec(i: int, state="bonus", site="carpt.net"):
    return {"site": site, "state": state, "sub": "资源", "size_gb": float(i + 1),
            "fp": _hex(i), "task": f"t{i % 3}"}


def _bill(i: int, site="carpt.net", state="active", rule="site_hr"):
    return {"site": site, "rule": rule, "state": state, "need_h": 24.0,
            "seeded_h": float(i), "opened_by": "open"}


def main() -> int:
    print("=" * 68)
    print("魔流 · AI 只读门面 P1.5b（agentledger）离线回归测试")
    print("=" * 68)

    # =====================================================================
    # (a) 信封与错误码
    # =====================================================================
    print("\n[a] 信封与错误码")
    h = _make_harness()
    r = h.agent_ledger(table="nope")
    _ok(r["ok"] is False and r["code"] == "not_found", f"未知表 → not_found（{r['code']}）")
    _ok(r["data"] is not None and r["data"].get("field") == "table", "not_found 附 field=table")

    r = h.agent_ledger(table="seed", limit="abc")
    _ok(r["ok"] is False and r["code"] == "bad_param", f"非法 limit → bad_param（{r['code']}）")
    _ok(r["data"].get("field") == "limit", "bad_param 附 field=limit")

    r = h.agent_ledger(table="seed", limit=-1)
    _ok(r["ok"] is False and r["code"] == "bad_param", "负数 limit → bad_param")

    h.seed = {_hex(i): _seed_rec(i) for i in range(5)}
    r = h.agent_ledger(table="seed")
    _ok(r["ok"] is True and r["code"] == "ok", "合法调用 → ok")
    for k in ("table", "columns", "rows", "total", "next_cursor"):
        _ok(k in r["data"], f"LedgerPage 含字段 {k!r}")
    _ok("meta" in r and "schema_version" in r["meta"], "信封带 meta.schema_version")

    # =====================================================================
    # (b) 分页 limit/cursor
    # =====================================================================
    print("\n[b] 分页 limit/cursor")
    p1 = h.agent_ledger(table="seed", limit=2)
    _ok(p1["data"]["total"] == 5, f"total=5（{p1['data']['total']}）")
    _ok(len(p1["data"]["rows"]) == 2, f"第 1 页 2 行（{len(p1['data']['rows'])}）")
    _ok(p1["data"]["next_cursor"] == _hex(1), f"第 1 页 next_cursor={_hex(1)[:8]}…")
    p2 = h.agent_ledger(table="seed", limit=2, cursor=p1["data"]["next_cursor"])
    _ok([r["hash"] for r in p2["data"]["rows"]] == [_hex(2), _hex(3)],
        "第 2 页 = h2,h3（无重叠、顺序稳定）")
    p3 = h.agent_ledger(table="seed", limit=0)
    _ok(len(p3["data"]["rows"]) == 5 and p3["data"]["next_cursor"] is None,
        "limit=0 → 全量 5 行、末页 next_cursor=None")

    # =====================================================================
    # (c) 过滤
    # =====================================================================
    print("\n[c] 过滤")
    h.seed = {_hex(i): _seed_rec(i, state=("bonus" if i % 2 == 0 else "brush"))
              for i in range(6)}
    f1 = h.agent_ledger(table="seed", filter="state=bonus")
    _ok(f1["data"]["total"] == 3 and all(r["state"] == "bonus" for r in f1["data"]["rows"]),
        f"filter=state=bonus 命中 3 行（{f1['data']['total']}）")
    f2 = h.agent_ledger(table="seed", state="brush")
    _ok(f2["data"]["total"] == 3, f"显式 state=brush 命中 3 行（{f2['data']['total']}）")

    h.bills = {_hex(i): _bill(i) for i in range(3)}
    h.bills[_hex(9)] = _bill(9, site="other.net", rule="unknown", state="void")
    fb = h.agent_ledger(table="bills", site="other.net")
    _ok(fb["data"]["total"] == 1 and fb["data"]["rows"][0]["hash"] == _hex(9),
        "bills 按 site 过滤命中 1 行")
    fr = h.agent_ledger(table="bills", rule="site_hr")
    _ok(fr["data"]["total"] == 3, f"bills 按 rule=site_hr 命中 3 行（{fr['data']['total']}）")

    # =====================================================================
    # (d) 列字典
    # =====================================================================
    print("\n[d] 列字典")
    cols = h.agent_ledger(table="seed")["data"]["columns"]
    _ok(isinstance(cols, list) and len(cols) > 0, "columns 为非空列表")
    for c in cols:
        for k in ("name", "type", "nullable"):
            _ok(k in c, f"列条目含 {k!r}（{c.get('name')}）")
    by_name = {c["name"]: c for c in cols}
    _ok(by_name["hash"]["type"] == "hex40", "seed.hash 类型 hex40")
    bcols = {c["name"]: c for c in h.agent_ledger(table="bills")["data"]["columns"]}
    _ok("active" in bcols["state"].get("enum", []), "bills.state 枚举含 active")
    _ok(bcols["need_h"].get("unit") == "h", "bills.need_h 单位 h")

    # =====================================================================
    # (e) 字段投影
    # =====================================================================
    print("\n[e] 字段投影")
    proj = h.agent_ledger(table="seed", fields="hash,site")
    _ok(all(set(r.keys()) == {"hash", "site"} for r in proj["data"]["rows"]),
        "fields=hash,site → 每行只有这两个键")

    # =====================================================================
    # (f) schema 端点
    # =====================================================================
    print("\n[f] schema 端点")
    s = h.agent_schema()
    _ok(s["ok"] and "types" in s["data"] and "tables" in s["data"], "schema 含 types+tables")
    _ok(all(t in s["data"]["tables"] for t in LEDGER_TABLES),
        f"tables 覆盖全部 {len(LEDGER_TABLES)} 张真值表")
    _ok("LedgerPage" in s["data"]["types"], "types 含 LedgerPage")
    lp = s["data"]["types"]["LedgerPage"]
    for k in ("table", "columns", "rows", "total", "next_cursor"):
        _ok(k in lp, f"LedgerPage 字段字典含 {k!r}")
    _ok(lp["rows"].get("type") == "array", "LedgerPage.rows 类型 array")

    # =====================================================================
    # (g) 报表层形状
    # =====================================================================
    print("\n[g] 报表层形状")
    ov = h.agent_overview()
    _ok(ov["ok"] and "status" in ov["data"] and "state" in ov["data"],
        "overview 含 status + state")

    tl = h.agent_tasks()
    _ok(tl["ok"] and isinstance(tl["data"]["tasks"], list) and tl["data"]["total"] == 1,
        "tasks 返回 1 个任务")

    td = h.agent_task_detail(id="t1")
    _ok(td["ok"] and "task" in td["data"] and "operations" in td["data"]
        and "summary" in td["data"], "task_detail 含 task+operations+summary")
    _ok(td["data"]["summary"].get("seeding_count") == 3, "summary.seeding_count=3")
    nf = h.agent_task_detail(id="zzz")
    _ok(nf["ok"] is False and nf["code"] == "not_found", "task_detail 不存在 → not_found")
    bp = h.agent_task_detail(id="")
    _ok(bp["ok"] is False and bp["code"] == "bad_param", "task_detail 空 id → bad_param")

    h.journal_records = [
        {"operation_id": "op1", "task_id": "t1", "kind": "deletion", "state": "completed",
         "created_at": 10.0, "items": []},
        {"operation_id": "op2", "task_id": "t2", "kind": "selection", "state": "completed",
         "created_at": 20.0, "items": []},
        {"operation_id": "op3", "task_id": "t1", "kind": "rescue", "state": "completed",
         "created_at": 30.0, "items": []},
    ]
    h._store = FakeStore(journal=FakeJournal(h.journal_records),
                         task_states=FakeTaskStates(h.task_states),
                         data_dir=Path("/tmp/mf_agent_ledger_test"))
    ops = h.agent_operations()
    _ok(ops["ok"] and ops["data"]["total"] == 3 and len(ops["data"]["items"]) == 3,
        "operations 返回 3 条")
    oa = h.agent_operations(action="rescue")
    _ok(oa["data"]["total"] == 1 and oa["data"]["items"][0]["operation_id"] == "op3",
        "operations 按 action=rescue 过滤命中 1 条")
    ot = h.agent_operations(task="t1")
    _ok(ot["data"]["total"] == 2, "operations 按 task=t1 过滤命中 2 条")
    obl = h.agent_operations(limit="x")
    _ok(obl["ok"] is False and obl["code"] == "bad_param", "operations 非法 limit → bad_param")

    pool = h.agent_pool()
    _ok(pool["ok"] and pool["data"].get("path") == "/movie" and "budget_gb" in pool["data"],
        "pool 含 path + budget_gb")

    tr = h.agent_trend()
    _ok(tr["ok"] and "series" in tr["data"] and tr["data"]["hours"] == 72,
        "trend 含 series + hours=72")

    rl = h.agent_rules()
    _ok(rl["ok"] and rl["data"]["total"] == 1 and rl["data"]["rules"][0]["hr"] is True,
        "rules 返回 1 条且 hr=True")

    st = h.agent_settings()
    _ok(st["ok"] and "defaults" in st["data"] and "downloader" in st["data"]
        and "settings" in st["data"], "settings 含 defaults+downloader+settings")

    he = h.agent_health()
    _ok(he["ok"] and he["data"]["level"] == "ok" and "issues" in he["data"],
        "health 含 level + issues")

    # =====================================================================
    # (h) check_agent_parity 自身逻辑
    # =====================================================================
    print("\n[h] check_agent_parity 逻辑")
    cp_spec = importlib.util.spec_from_file_location("mf_parity_tool", ROOT / "tools" / "check_agent_parity.py")
    cp = importlib.util.module_from_spec(cp_spec)
    sys.modules["mf_parity_tool"] = cp
    cp_spec.loader.exec_module(cp)

    _ok(cp.classify("get", "/status") == ("covered", "/agent/overview"),
        "parity: GET /status → covered /agent/overview")
    _ok(cp.classify("get", "/recommend") == ("covered", "/agent/recommend"),
        "parity: GET /recommend → covered /agent/recommend")
    _ok(cp.classify("get", "/site/icon/{x}")[0] == "whitelisted",
        "parity: GET /site/icon/{x} → 仍白名单（非插件端点）")
    _ok(cp.classify("post", "/tasks")[0] == "write", "parity: POST /tasks → 写豁免")
    _ok(cp.classify("get", "/nonexistent")[0] == "uncovered", "parity: 未知 GET → uncovered")
    _ok("/tasks/{x}" in cp.COVERED.values() or "/agent/tasks/{x}" in cp.COVERED.values(),
        "parity: COVERED 含 /agent/tasks/{x}")
    # 19 个功能域全部收编进 COVERED（不再白名单）
    for fp, ap in (
        ("/tasks/{x}/bonus", "/agent/tasks/{x}/bonus"),
        ("/tasks/{x}/candidates", "/agent/tasks/{x}/candidates"),
        ("/tasks/{x}/handover", "/agent/tasks/{x}/handover"),
        ("/recommend", "/agent/recommend"), ("/crossseed", "/agent/crossseed"),
        ("/reseed", "/agent/reseed"), ("/douban_service", "/agent/douban"),
        ("/live", "/agent/live"), ("/signin", "/agent/signin"), ("/exam", "/agent/exam"),
        ("/silent/pool", "/agent/silent"), ("/claim", "/agent/claim"),
        ("/tags", "/agent/tags"), ("/cloud", "/agent/cloud"), ("/cloud/test", "/agent/cloud"),
        ("/fallback", "/agent/fallback"), ("/iyuu/sites", "/agent/iyuu"),
        ("/iyuu/test", "/agent/iyuu"), ("/events", "/agent/events"),
    ):
        _ok(cp.classify("get", fp) == ("covered", ap), f"parity: GET {fp} → covered {ap}")

    calls = cp.extract_calls('props.api.get(`${pluginBase.value}/tasks/${taskId}/operations${opsQuery()}`)')
    _ok(calls == [("get", "{x}/tasks/{x}/operations{x}")], f"parity 抽取模板调用（{calls}）")
    _ok(cp.normalize_path("{x}/tasks/{x}/operations{x}") == "/tasks/{x}/operations",
        "parity 归一化剥 pluginBase 前缀 + 尾部查询变量")
    _ok(cp.normalize_path("{x}/recommend/{x}/{x}") == "/recommend/{x}/{x}",
        "parity 保留 / 引导的路径参数")
    _ok(cp.normalize_path("{x}/pool?path=x") == "/pool", "parity 剥查询串")

    # 真值源覆盖：11 张表全在 REQUIRED_TABLES 且都被 agentledger.LEDGER_TABLES 覆盖
    _ok(set(cp.REQUIRED_TABLES) == set(LEDGER_TABLES),
        f"parity REQUIRED_TABLES == LEDGER_TABLES（{len(LEDGER_TABLES)} 张）")

    # =====================================================================
    # (i) 19 个功能域只读端点（P1.5c，AI ⊇ 前端）
    # =====================================================================
    print("\n[i] 功能域只读端点（P1.5c）")
    hh = _make_harness()

    # —— 12 个「非任务级」域端点：统一信封 + 判定依据链（reason_chain）——
    flat_cases = [
        ("agent_recommend", {}, "items"),
        ("agent_crossseed", {}, "pending"),
        ("agent_reseed", {}, "enabled"),
        ("agent_douban", {}, "count"),
        ("agent_live", {}, "sites"),
        ("agent_signin", {}, "sites"),
        ("agent_exam", {}, "enabled"),
        ("agent_silent", {}, "stats"),
        ("agent_claim", {}, "cap_total"),
        ("agent_fallback", {}, "enabled"),
        ("agent_events", {}, "events"),
        ("agent_tags", {}, "enabled"),
    ]
    for meth, kw, key in flat_cases:
        r = getattr(hh, meth)(**kw)
        _ok(r["ok"] is True, f"{meth} ok=True")
        _ok(r["code"] == "ok", f"{meth} code=ok")
        _ok(key in r["data"], f"{meth} data 含 {key}")
        rc = r["meta"].get("reason_chain")
        _ok(isinstance(rc, list) and len(rc) == 1, f"{meth} meta.reason_chain 是单条")
        _ok(rc[0]["rule"] == "agent/proxy" and rc[0]["verdict"] == "report",
            f"{meth} reason_chain rule/verdict")
        _ok(bool(rc[0].get("source_of_truth")), f"{meth} reason_chain.source_of_truth 非空")
        _ok(bool(rc[0].get("at")), f"{meth} reason_chain.at 非空")

    # —— 云盘 / IYUU 组合端点：state+test / sites+test ——
    cl = hh.agent_cloud()
    _ok(cl["ok"] and "state" in cl["data"] and "test" in cl["data"],
        "agent_cloud 含 state + test")
    _ok(cl["data"]["test"].get("ok") is True, "agent_cloud.test.ok=True")
    _ok(cl["meta"]["reason_chain"][0]["source_of_truth"], "agent_cloud 有 source_of_truth")
    iy = hh.agent_iyuu()
    _ok(iy["ok"] and "sites" in iy["data"] and "test" in iy["data"],
        "agent_iyuu 含 sites + test")
    _ok(iy["data"]["test"].get("ok") is True, "agent_iyuu.test.ok=True")
    _ok(iy["meta"]["reason_chain"][0]["source_of_truth"], "agent_iyuu 有 source_of_truth")

    # —— 任务级三端点：带 id ——
    task_cases = [
        ("agent_task_bonus", "torrents", "total_bonus"),
        ("agent_task_candidates", "candidates", "total"),
        ("agent_task_handover", "handover", "total"),
    ]
    for meth, key1, key2 in task_cases:
        r = getattr(hh, meth)(id="t1")
        _ok(r["ok"] and key1 in r["data"], f"{meth}(t1) 含 {key1}")
        _ok(key2 in r["data"], f"{meth}(t1) 含 {key2}")
        _ok(r["meta"]["reason_chain"][0]["source_of_truth"], f"{meth} 有 source_of_truth")
        bp = getattr(hh, meth)(id="")
        _ok(bp["ok"] is False and bp["code"] == "bad_param", f"{meth} 空 id → bad_param")
        _ok(bp["data"].get("field") == "id", f"{meth} bad_param 附 field=id")

    # —— 参数透传 / 强转 ——
    sn = hh.agent_signin(days="3")
    _ok(sn["ok"], "agent_signin(days='3') 强转 ok")
    ex = hh.agent_exam(site_id="0", include_pass="true")
    _ok(ex["ok"], "agent_exam(include_pass='true') 强转 ok")
    lv = hh.agent_live(site_id="2")
    _ok(lv["ok"], "agent_live(site_id='2') 强转 ok")
    ev = hh.agent_events(limit="10")
    _ok(ev["ok"], "agent_events(limit='10') 强转 ok")
    fb = hh.agent_fallback(resolve_paths="true")
    _ok(fb["ok"], "agent_fallback(resolve_paths='true') 强转 ok")

    # —— 底层 handler 失败 → internal（只读降级，不崩）——
    hh.get_recommend_list = lambda: FakeResp(data=None, message="boom", success=False)
    r = hh.agent_recommend()
    _ok(r["ok"] is False and r["code"] == "internal", "handler success=False → internal")
    _ok("boom" in r["message"] or "读取失败" in r["message"], "internal 带底层 message")

    def _raise(**kw):
        raise RuntimeError("x")
    hh.get_signin_state = _raise
    r = hh.agent_signin()
    _ok(r["ok"] is False and r["code"] == "internal", "handler 抛异常 → internal")
    _ok("读取失败" in r["message"], "internal message 带「读取失败」")

    # =====================================================================
    print("\n" + "=" * 68)
    print(f"PASS：{CHECKS} 项断言全部通过 ✅")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"\n{e}")
        raise SystemExit(1)
