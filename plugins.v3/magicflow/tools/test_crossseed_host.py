#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 跨站取种 host 化离线回归（★ 14.0.0-2）。

背景：14.0.0 把「跨站取种」做成真任务 ``__crossseed__`` → H2 卡死误报（Check
走 ``_crossseed_tick`` 不写 ``task_states``）。14.0.0-2 改造：

  ① 真任务 __crossseed__ 退役（``tasks._retire_crossseed_task``）→ 幂等清理；
  ② 改由常驻 worker（``core.py::get_service`` 的 CrossSeed worker）承载；
  ③ status/agent 走 host 卡片（``task_type="host"`` / ``is_host=True``）→ agent 不当任务操作；
  ④ H2 加 ``task_type != "host"`` 防御。

本测试直接加载真模块（合成父包解相对导入），断言：
  1) ``_retire_crossseed_task`` 幂等（重复调用副作用清除 _Task_configs、task_states、journal）；
  2) ``_retire_crossseed_task`` 把 ``__crossseed__`` journal 老流水批量改指 ``__silent_host__``；
  3) ``_crossseed_host_card`` 字段对齐 ``_hr_host_card``（task_type=host / is_host=True）；
  4) ``core.get_service()`` 含 CrossSeed worker + 不含 Task___crossseed__Check/Brush；
  5) ``_crossseed_feature_enabled`` 判据改成 pending/items：空 + 无发起任务 → False；
     有 items → True；空 + 有发起任务在岗 → True；
  6) H2：``task_type="host"`` 任务**永不**出现在 issues；
  7) ``_crossseed_tick`` 早退：feature_disabled=True 时返回 ``skipped=feature_disabled``；
  8) 源码级护栏（防回归）。

用法：``python3 tools/test_crossseed_host.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_cs_host"


# ----------------------------------------------------------------- 桩加载器
def _stub_pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


class _Stub(types.ModuleType):
    """万能桩模块：任何属性/调用都是另一个 _Stub（嵌套取值不报 AttributeError）。"""

    def __init__(self, name: str = "_stub"):
        super().__init__(name)

    def __getattr__(self, name):
        return _Stub(name)

    def __call__(self, *a, **k):
        return _Stub("_call")


def _stub_sibling(modname: str) -> _Stub:
    m = _Stub(PKG + "." + modname)
    sys.modules[PKG + "." + modname] = m
    return m


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------- 1. stub app.*
for n, attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": _Stub("EventType")}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": _Stub("eventmanager"),
                        "Event": type("Event", (), {})}),
    ("app.sdk.logging", {"logger": _Stub("logger")}),
    ("app.scheduler", {"Scheduler": type("Scheduler", (), {})}),
    ("app.api", {}),
    ("app.api.endpoints", {}),
    ("app.api.endpoints.plugin", {"register_plugin_api": lambda *a, **k: None}),
    ("app.db", {}),
    ("app.db.oper", {}),
    ("app.db.oper.site", {"SiteOper": type("SiteOper", (), {})}),
    ("app.sdk.network", {"SitesHelper": type("SitesHelper", (), {})}),
    ("app.sdk.services", {"DownloaderHelper": type("DownloaderHelper", (), {})}),
):
    m = sys.modules.get(n)
    if m is None:
        m = types.ModuleType(n)
        sys.modules[n] = m
    for k, v in attrs.items():
        setattr(m, k, v)

# 2. 桩 magicflow 顶层包及其兄弟模块
_stub_pkg(PKG, ROOT)
_stub_pkg(PKG + ".features", ROOT / "features")
_stub_pkg(PKG + ".sites", ROOT / "sites")
for modname in ("bonus", "fetcher", "recommend", "models", "fingerprint",
                "persistence", "downloader_ops", "live_stats", "dtier",
                "tags", "formulas", "hubs",
                "fallback", "collect", "cloud_archive", "kvstore",
                "signin", "sitestore"):
    _stub_sibling(modname)

# 3. 先加载 common.py（它是字典 key，所有 features 都依赖）
_common = _load(PKG + ".common", "common.py")

# 4. 加载所有 features ——relative import 会被 __package__ 解析到 stub
_tasks = _load(PKG + ".features.tasks", "features/tasks.py")
_status = _load(PKG + ".features.status", "features/status.py")
_core = _load(PKG + ".features.core", "features/core.py")
_registry = _load(PKG + ".features.registry", "features/registry.py")
_crossseed = _load(PKG + ".features.crossseed", "features/crossseed.py")
_hrbills_stub = _Stub(PKG + ".features.hrbills")
sys.modules[PKG + ".features.hrbills"] = _hrbills_stub
_hrbills_stub.BILL_STATE_ACTIVE = "active"
_hrbills_stub.BILL_STATE_BREACHED = "breached"
_hrbills_stub.RULE_SITE_HR = "site_hr"
_hrbills_stub.RULE_HIT_AND_RUN = "hit_and_run"
_health = _load(PKG + ".features.health", "features/health.py")


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1


# -----------------------------------------------------------------------
# [1] 退役幂等
# -----------------------------------------------------------------------
class _FakeTask:
    def __init__(self, tid):
        self.id = tid
        self.name = "跨站取种"
        self.task_type = "crossseed"
        self.run_mode = "running"
        self.enabled = True
        self.brush_tag = "魔流-跨站"
        self.brush_interval = 30
        self.check_interval = 30
        self.site_id = 0
        self.site_name = ""
        self.site_domain = ""

    def to_dict(self):
        return {"id": self.id, "name": self.name, "task_type": self.task_type,
                "run_mode": self.run_mode, "enabled": self.enabled}


class _FakeJournal:
    def __init__(self, records):
        self._operations = dict(records)
        self._lock = threading.RLock()
        self._kv_written = {}

    def list_by_task(self, tid, kind=None, limit=50):
        rows = [op for op in self._operations.values() if op.task_id == tid
                and (kind is None or op.kind == kind)]
        rows.sort(key=lambda x: x.created_at, reverse=True)
        return rows[:limit]

    def _save(self):
        pass


class _OpRec:
    def __init__(self, tid):
        self.task_id = tid
        self.operation_id = "op_" + tid
        self.kind = "reseed"
        self.state = "completed"
        self.created_at = 1.0
        self.resolved_at = 1.0
        self.items = []


class _FakeTaskStates:
    def __init__(self):
        self._states = {"__crossseed__": types.SimpleNamespace(task_id="__crossseed__", last_run_at=0.0)}

    def delete(self, tid):
        if tid in self._states:
            self._states.pop(tid, None)
            return True
        return False

    def get(self, tid):
        return self._states.get(tid)


class _FakeStore:
    def __init__(self):
        self.task_states = _FakeTaskStates()
        self.journal = _FakeJournal({
            "op_1": _OpRec("__crossseed__"),
            "op_2": _OpRec("__crossseed__"),
            "op_3": _OpRec("__silent_host__"),
        })


class _Plug(_tasks.TasksMixin):
    def __init__(self):
        self._task_configs = {"__crossseed__": _FakeTask("__crossseed__")}
        self._store = _FakeStore()
        self._did_refresh = False

    def _save_config(self):
        pass

    def _refresh_scheduler(self):
        self._did_refresh = True

    def _log(self, msg, level="info"):
        pass


_plug = _Plug()
_plug._retire_crossseed_task()
_ok("__crossseed__" not in _plug._task_configs,
    "退役：_task_configs 已不含 __crossseed__")
_ok(_plug._store.task_states.get("__crossseed__") is None,
    "退役：task_states.get('__crossseed__') → None")
_ok(_plug._did_refresh, "退役：触发了 _refresh_scheduler")
moved = [op for op in _plug._store.journal._operations.values()
         if op.task_id == "__silent_host__"]
_ok(len(moved) == 3, f"退役：journal 迁移后 __silent_host__ 共 3 条（实际 {len(moved)}）")

_plug._did_refresh = False
_plug._retire_crossseed_task()
_ok(not _plug._did_refresh,
    "退役幂等：第二次调用不应再触发 _refresh_scheduler")
_ok(len(_plug._store.journal._operations) == 3,
    "退役幂等：journal 记录数不变")


# -----------------------------------------------------------------------
# [2] _crossseed_host_card 字段对齐
# -----------------------------------------------------------------------
class _CSPlug(_crossseed.CrossSeedMixin):
    def __init__(self):
        self._cs_cfg = {}
        self._crossseed_host_last = 0.0
        self._store = types.SimpleNamespace(journal=types.SimpleNamespace(
            list_by_task=lambda *a, **kw: []))
        self._crossseed_pending = lambda: types.SimpleNamespace(items=lambda: {
            "h1": {"progress": 0.5, "title": "x"},
            "h2": {"progress": 1.0, "title": "y"},
            "h3": {"progress": None, "title": "z"},
        })
        self._cs_ban_map = lambda: {"a.com": {}, "b.com": {}, "c.com": {}}

    def _log(self, msg, level="info"):
        pass


card = _CSPlug()._crossseed_host_card()
_ok(card.get("id") == "__crossseed__", "host 卡片 id=__crossseed__")
_ok(card.get("task_type") == "host", "host 卡片 task_type=host")
_ok(card.get("run_mode") == "running", "host 卡片 run_mode=running")
_ok(card.get("enabled") is True, "host 卡片 enabled=True")
_ok(card.get("site_id") == 0, "host 卡片 site_id=0")
cls = card.get("classify") or {}
_ok(cls.get("pending_total") == 3, f"host 卡片 pending_total=3（实际 {cls.get('pending_total')}）")
_ok(cls.get("pending_inflight") == 2, f"host 卡片 pending_inflight=2（实际 {cls.get('pending_inflight')}）")
_ok(cls.get("violations") == 3, f"host 卡片 violations=3（实际 {cls.get('violations')}）")
_ok("downloading_count" in card and card["downloading_count"] == 2,
    "host 卡片 downloading_count=2（inflight）")
_ok("host_interval_minutes" in card and abs(card["host_interval_minutes"] - 30.0) < 0.5,
    "host 卡片 host_interval_minutes≈30")
_ok("host_last_run" in card, "host 卡片含 host_last_run 字段")


# -----------------------------------------------------------------------
# [3] core.get_service 含 CrossSeed worker
# -----------------------------------------------------------------------
class _CorePlug(_core.CoreMixin):
    def __init__(self):
        self._enabled = True
        self._task_configs = {}
        self._reseed_enabled = False
        self._recommend_cfg = {"enabled": True}
        self._fallback_cfg = {"enabled": False, "interval": 30.0}
        self._live_cfg = {"enabled": False}
        self._rules_cfg = {"auto_refresh": False}
        self._signin_cfg = {"enabled": False, "sites": [], "login_sites": []}
        self._tags_cfg = {"host_interval": 60.0, "hr_host_interval": 15.0}
        self._show_sidebar_nav = True

    def __getattr__(self, name):
        # get_service() 会引用大量 self.<method>（worker 的 func 引用、以及来自其它
        # mixin 的 _xxx 私有方法，本测试只挂了 CoreMixin）→ 未定义的一律给 no-op。
        return lambda *a, **k: None

    def get_data(self, key=None, default=None):
        return default if default is not None else {}

    def save_data(self, **kwargs):
        return None

    def _jitter_seconds(self, n):
        return min(60, max(0, int(n) * 60 // 10))

    def _list_sites(self):
        return []

    def _normalize_run_mode(self, mode, enabled=True):
        return mode or "running"

    def _log(self, msg, level="info"):
        pass


services = _CorePlug().get_service()
_ids = [str(s.get("id") or "") for s in services]
_ok("CrossSeed" in _ids, f"get_service 含 CrossSeed worker（实际 ids={_ids}）")
_ok(not any(s.startswith("Task___crossseed__") for s in _ids),
    f"get_service 不再含 Task___crossseed__*（实际 ids={_ids}）")
cs_i = _ids.index("CrossSeed") if "CrossSeed" in _ids else -1
hr_i = _ids.index("HrHost") if "HrHost" in _ids else -1
_ok(hr_i >= 0 and cs_i == hr_i + 1,
    f"CrossSeed 紧挨 HrHost 后注册（HrHost={hr_i} / CrossSeed={cs_i}）")


# -----------------------------------------------------------------------
# [4] registry._crossseed_feature_enabled 判据改成 pending/items
# -----------------------------------------------------------------------
class _RegPlug(_registry.RegistryMixin):
    def __init__(self, *, pending_items=None, tasks=None):
        self._task_configs = tasks or {}
        self._crossseed_pending = lambda: types.SimpleNamespace(
            items=lambda: pending_items or {})


r = _RegPlug(pending_items={}, tasks={})
_ok(not r._crossseed_feature_enabled(),
    "feature_enabled: 空 pending + 无 crossseed_enabled 任务 → False")

r = _RegPlug(pending_items={"h1": {}}, tasks={})
_ok(r._crossseed_feature_enabled(),
    "feature_enabled: 有 items（无 crossseed_enabled 任务）→ True")

t = types.SimpleNamespace(crossseed_enabled=True, run_mode="running", enabled=True)
r = _RegPlug(pending_items={}, tasks={"t1": t})
_ok(r._crossseed_feature_enabled(),
    "feature_enabled: 空 pending + crossseed_enabled 且在岗 → True")

t2 = types.SimpleNamespace(crossseed_enabled=True, run_mode="stopped", enabled=False)
r = _RegPlug(pending_items={}, tasks={"t1": t2})
_ok(not r._crossseed_feature_enabled(),
    "feature_enabled: 空 pending + crossseed_enabled 但 stopped → False")


# -----------------------------------------------------------------------
# [5] H2 排除 host
# -----------------------------------------------------------------------
class _HPlug(_health.HealthMixin):
    def __init__(self, tasks):
        self._task_configs = dict(tasks)
        self._store = None

    def _trend_data(self):
        return {}

    def _trend_label(self, scope, ident):
        return f"{scope}/{ident}"

    def _log(self, msg, level="info"):
        pass


t_run = types.SimpleNamespace(id="t1", name="t1", task_type="bonus",
                              check_interval=30, run_mode="running", enabled=True)
issues = _HPlug({"t1": t_run})._health_issues()
_ok(any(i.get("key") == "H2:t1" for i in issues),
    "H2: 普通 running 任务无 stats → 报 H2:t1")

t_host = types.SimpleNamespace(id="__silent_host__", name="静默托管", task_type="host",
                               check_interval=30, run_mode="running", enabled=True)
issues = _HPlug({"__silent_host__": t_host})._health_issues()
_ok(not any("__silent_host__" in str(i.get("key") or "") for i in issues),
    "H2: __silent_host__（task_type=host）不报卡死")

t_cs_host = types.SimpleNamespace(id="__crossseed__", name="跨站取种", task_type="host",
                                  check_interval=30, run_mode="running", enabled=True)
issues = _HPlug({"__crossseed__": t_cs_host})._health_issues()
_ok(not any("__crossseed__" in str(i.get("key") or "") for i in issues),
    "H2: __crossseed__（task_type=host）不报卡死（即使被错放进 _task_configs）")


# -----------------------------------------------------------------------
# [6] _crossseed_tick 早退
# -----------------------------------------------------------------------
class _FakePending:
    def items(self):
        return {}

    def prune(self):
        return []


class _TickPlug(_crossseed.CrossSeedMixin):
    def __init__(self, enabled: bool):
        self._cs_cfg = {}
        self._enabled = enabled
        self._task_configs = {}
        self._crossseed_pending = lambda: _FakePending()
        self._log_calls = []

    def _crossseed_feature_enabled(self):
        return self._enabled

    def _log(self, msg, level="info"):
        self._log_calls.append((msg, level))

    def _cs_ban_map(self):
        return {}

    def _crossseed_guard(self):
        return {"enabled": False, "checked_sites": [], "violations": []}


res = _TickPlug(False)._crossseed_tick()
_ok(res.get("skipped") == "feature_disabled",
    f"_crossseed_tick 早退：feature_disabled=True → skipped=feature_disabled（实际 {res}）")

res2 = _TickPlug(True)._crossseed_tick()
_ok(res2.get("skipped") is None,
    f"_crossseed_tick 启用：无 skipped 字段（实际 {res2}）")
_ok("checked" in res2 and "waiting" in res2 and "settled" in res2 and "violations" in res2,
    "_crossseed_tick 启用：返回 res 含 checked/waiting/settled/violations")


# -----------------------------------------------------------------------
# [7] 源码级护栏
# -----------------------------------------------------------------------
_src = lambda f: open(os.path.join(ROOT, "features", f), encoding="utf-8").read()
_cs_src = _src("crossseed.py")
_tasks_src = _src("tasks.py")
_core_src = _src("core.py")
_status_src = _src("status.py")
_registry_src = _src("registry.py")
_health_src = _src("health.py")
_brush_src = _src("brush.py")

_ok("def _retire_crossseed_task" in _tasks_src
    and "def _ensure_crossseed_task" not in _tasks_src,
    "tasks.py：_ensure_crossseed_task 已退役，_retire_crossseed_task 接手")

_ok('"id": "CrossSeed"' in _core_src and '"func": self._crossseed_tick' in _core_src,
    "core.py：get_service 注册 CrossSeed worker（func=_crossseed_tick）")
_ok("self._retire_crossseed_task" in _core_src
    and "self._ensure_crossseed_task" not in _core_src,
    "core.py：init_plugin 调 _retire_crossseed_task（不再调 _ensure_crossseed_task）")

_ok("def _crossseed_host_card" in _cs_src,
    "crossseed.py：新增 _crossseed_host_card")
_ok("SILENT_HOST_TASK_ID" in _cs_src and "task_id=SILENT_HOST_TASK_ID" in _cs_src,
    "crossseed.py：settle 流水 task_id=SILENT_HOST_TASK_ID")

_ok("def _crossseed_feature_enabled" in _registry_src
    and "pend.items()" in _registry_src,
    "registry.py：_crossseed_feature_enabled 走 pend.items()（不再依赖 _task_configs[__crossseed__]）")

_ok("task_type" in _health_src and '"host"' in _health_src
    and '!= "host"' in _health_src,
    'health.py：H2 running 过滤含 task_type != "host" 防御')

_ok("self._crossseed_host_card" in _status_src
    and 'str(task_id or "") == CROSSSEED_TASK_ID' in _status_src,
    "status.py：_build_task_detail / _build_task_list / _light_status 三处加 _crossseed_host_card")

_chk_body = _brush_src[_brush_src.index("def check(self, task_id: str)"):]
_chk_body = _chk_body[:_chk_body.index("\n    def ", 10)]
_ok("self._crossseed_tick" not in _chk_body,
    "brush.py：check() 函数体内不再直接调 self._crossseed_tick")
_ok("warning" in _chk_body,
    "brush.py：check() 若收到残留 crossseed 任务会 warning 告警")


print("\n" + "=" * 64)
print(f"✅ PASS —— 共 {CHECKS} 项全过")
sys.exit(0)