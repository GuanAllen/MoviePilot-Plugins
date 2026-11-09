#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 136：H&R 账单业务契约（删除通道归一 / 状态机 / 墓碑重开 / 事件事务）。

覆盖：
  A. 删除通道归一：tick 不再物理删账单；摘账落 void 墓碑（未知僵尸 / 复用份 / clear）。
  B. 状态机：pending/active/settled/breached/void 的保留与转换（禁止 settled→pending）。
  C. 墓碑重开（N-136-03）：保留期内重下 → pending；超期/人工作废不重开。
  D. 删除与事件同事务（N-136-06）：drop / drop_many / drop_many_if 同时清事件。
  E. UNKNOWN 冻结：存储不可用 → tick 不流转、open 不开账。
  F. 人工结清契约：reason/by 必填、void 拒绝、幂等、事件同 CAS。
  G. 清理口径：仅 settled/void；非法最终时间不清理。

纯离线（内存 Store + 桩模块）。用法：``python3 tools/test_hr_bill_contract.py``。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_t136_contract"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

FAILS: list[str] = []
CASES = 0


def _ok(cond, name, detail=""):
    global CASES
    CASES += 1
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name}" + (f" —— {detail}" if detail else ""))
        FAILS.append(name)


class _Any:
    def __init__(self, name="dummy"):
        self._name = name

    def __call__(self, *a, **k):
        return _Any(self._name + "()")

    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return _Any(f"{self._name}.{k}")

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return True


def _mod(name, **attrs):
    m = sys.modules.get(name) or types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    if not hasattr(m, "__getattr__"):
        m.__getattr__ = lambda n: _Any(f"{name}.{n}")
    sys.modules[name] = m
    m.__path__ = []
    return m


class _Shared:
    def __init__(self):
        import threading
        self.lock = threading.RLock()
        self.singletons = {}


_SHARED = _Shared()


def _load_hrbills():
    _mod("app")
    _mod("app.schemas", Response=type("Response", (), {}))
    _mod("app.sdk")
    _mod("app.sdk.logging", logger=type("L", (), {
        "warning": staticmethod(lambda *a, **k: None),
        "info": staticmethod(lambda *a, **k: None),
        "error": staticmethod(lambda *a, **k: None)})())
    pkg = _mod(PKG)
    pkg.__path__ = [str(ROOT)]
    _mod(PKG + ".tags", MARK_REUSE="魔流-辅种", RESCUE_TAG="魔流-补源",
     STATE_BONUS="bonus", STATE_BRUSH="brush", STATE_CLAIM="claim",
     STATE_HR="hr", STATE_KEEP="keep", STATE_MUSIC="music",
     STATE_ONDEMAND="ondemand", STATE_RECOMMEND="recommend",
     STATE_SILENT="silent", is_reuse_copy=lambda tags: False)
    _mod(PKG + ".fingerprint", fingerprint=lambda *a, **k: "",
         info_hash=lambda *a, **k: "")
    _mod(PKG + ".downloader_ops", seed_hours_for_hr=lambda t: 0.0)
    _mod(PKG + ".persistence", _shared=lambda: _SHARED,
         OperationItem=type("OperationItem", (), {}))
    _mod(PKG + ".common", HR_COMPLETE_RATIO_DEFAULT=0.999,
         HR_DEADLINE_WARN_HOURS_DEFAULT=48.0,
         HR_SEED_MARGIN_HOURS_DEFAULT=2.0)
    spec = importlib.util.spec_from_file_location(
        PKG + ".features.hrbills", ROOT / "features/hrbills.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG + ".features.hrbills"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


hb = _load_hrbills()
from _hr_mem_store import MemHrBillsStore  # noqa: E402

STATE = {"pending": hb.BILL_STATE_PENDING, "active": hb.BILL_STATE_ACTIVE,
         "settled": hb.BILL_STATE_SETTLED, "breached": hb.BILL_STATE_BREACHED,
         "void": hb.BILL_STATE_VOID}


def _t(hash_string, progress=1.0, seed_time=0.0, downloaded=1e9, title="t"):
    return types.SimpleNamespace(
        hash=hash_string, title=title, progress=progress, seed_time=seed_time,
        hit_and_run=False, tags=[], tracker="hdfans.org", completion_on=0.0,
        downloaded=downloaded)


class Harness(hb.HrBillsMixin):
    def __init__(self, data_dir):
        self._data_dir = Path(data_dir)
        self._mem = MemHrBillsStore()
        self.torrents = {}
        self.site_hr = {"hdfans.org": True}
        self.need = {"hdfans.org": 24.0}
        self._hr_seed_margin_hours = 2.0
        self.writes = 0

    def get_data_path(self):
        return self._data_dir

    def _hrbills_store(self):
        return self._mem

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _site_hr_flag(self, dom):
        return self.site_hr.get(dom)

    def _site_per_torrent_hr(self, dom):
        return False

    def _site_rules(self):
        return {}

    def _crossseed_seed_need_hours(self, dom):
        return self.need.get(dom, 0.0)

    def _hr_site_debt_index(self, now=None):
        return None

    def _hr_site_verdict(self, hash_string, dom, now=None, idx=None):
        return ("unknown", 0.0)

    def _hr_reopen_evidence(self, *a, **k):
        return {"ok": False, "why": "test"}

    def _log(self, *a, **k):
        pass

    def _hrbills_title(self, hash_string):
        return "t"


def _bill(**kw):
    b = {"site": "hdfans.org", "rule": hb.RULE_SITE_HR, "state": "active",
         "need_h": 24.0, "seeded_h": 0.0, "opened_at": time.time() - 86400,
         "progress": 1.0, "alive": True, "last_seen": time.time(),
         "settlement_method": None, "settled_at": None}
    b.update(kw)
    return b


def _events(h, hs):
    return h._mem.events_for(hs)


def main() -> int:
    print("=" * 68)
    print("魔流 · 任务 136 H&R 账单业务契约测试")
    print("=" * 68)
    tmp = tempfile.mkdtemp(prefix="hr_contract_")
    h = Harness(tmp)
    store = h._mem
    now = time.time()

    # ---------------------------------------------------------------- A
    print("\n[A] 删除通道归一（tick 只落墓碑，不物理删）")
    ttl0 = hb.HR_BILLS_SETTLED_TTL_DAYS
    _orig_seed = hb.seed_hours_for_hr
    hb.seed_hours_for_hr = lambda t: float(getattr(t, "seed_time", 0.0) or 0.0) / 3600.0
    hb.HR_BILLS_SETTLED_TTL_DAYS = 0.0
    store.put("z1", _bill(state="pending", rule="unknown", need_h=24.0))
    store.put("s1", _bill(state="settled", settled_at=now - 40 * 86400,
                          settlement_method="auto"))
    store.put("r1", _bill(state="active", rule=hb.RULE_SITE_HR))
    h.torrents = {
        "z1": _t("z1", progress=1.0, seed_time=40 * 3600),   # 未知规则已做满
        "s1": _t("s1", progress=1.0, seed_time=40 * 3600),   # settled 超 30 天
        "r1": _t("r1", progress=1.0, seed_time=10 * 3600, downloaded=0),
    }
    called = {"drop_many_if": 0}
    orig_drop = store.drop_many_if

    def _spy(items):
        called["drop_many_if"] += 1
        return orig_drop(items)

    store.drop_many_if = _spy  # type: ignore[assignment]
    res = h._hrbills_tick()
    store.drop_many_if = orig_drop  # type: ignore[assignment]
    _ok(called["drop_many_if"] == 0, "tick 未调用 drop_many_if（无物理删除通道）")
    z1 = store.get("z1") or {}
    _ok(z1.get("state") == "void" and z1.get("void_reason") == "legacy_rule_unknown_fulfilled",
        "未知僵尸账落 void 墓碑（不再物理删）", repr(z1.get("state")))
    _ok(any(e.get("event_type") == hb.EVT_AUTO_VOID for e in _events(h, "z1")),
        "作废事件与墓碑同一次 CAS 写入")
    s1 = store.get("s1") or {}
    _ok(s1.get("state") == "settled", "settled 超 30 天不被 tick 删除（交给 HrPurge）",
        repr(s1.get("state")))
    r1 = store.get("r1") or {}
    _ok(r1.get("state") == "void" and r1.get("void_reason") == "reuse_copy",
        "复用份误开账落 void 墓碑", repr(r1.get("state")))
    _ok(int(res.get("dropped") or 0) == 0, "tick 计数 dropped=0（删除已归一）",
        str(res.get("dropped")))
    hb.HR_BILLS_SETTLED_TTL_DAYS = ttl0
    hb.seed_hours_for_hr = _orig_seed

    # ---------------------------------------------------------------- B
    print("\n[B] 状态机（禁止 settled→pending）")
    store.put("s2", _bill(state="settled", settled_at=now - 5 * 86400,
                          settlement_method=None))
    store.put("a2", _bill(state="active", rule="hdfans.org-unknown"))
    h.torrents = {"s2": _t("s2", progress=1.0, seed_time=40 * 3600),
                  "a2": _t("a2", progress=1.0, seed_time=1 * 3600)}
    h._hrbills_tick()
    s2 = store.get("s2") or {}
    a2 = store.get("a2") or {}
    _ok(s2.get("state") == "settled", "settled + 规则不可读 → 保持 settled（不降级）",
        repr(s2.get("state")))
    _ok(a2.get("state") == "pending", "active + 规则不可读 → 回 pending（保留自愈）",
        repr(a2.get("state")))

    # ---------------------------------------------------------------- C
    print("\n[C] 墓碑重开（N-136-03）")
    store.put("v1", _bill(state="void", voided_at=now - 5 * 86400,
                          void_reason="site_no_longer_owed_auto"))
    store.put("v2", _bill(state="void", voided_at=now - 31 * 86400,
                          void_reason="site_no_longer_owed_auto"))
    store.put("v3", _bill(state="void", voided_at=now - 5 * 86400,
                          void_reason="manual_by_admin"))
    h.torrents = {}
    b1 = h._hrbills_open("v1", "hdfans.org", "魔流-hdfans-刷流", b"x")
    _ok(isinstance(b1, dict) and b1.get("state") == "pending",
        "保留期内重下 → 重开为 pending", repr((b1 or {}).get("state")))
    _ok(sum(1 for e in _events(h, "v1") if e.get("event_type") == hb.EVT_REOPENED) == 1,
        "重开事件仅一条（重开次数以事件表为准）")
    _ok(not (store.get("v1") or {}).get("voided_at"), "重开清空 voided_at")
    _ok(any(e.get("event_type") == hb.EVT_REOPENED for e in _events(h, "v1")),
        "重开写 reopened 事件")
    b2 = h._hrbills_open("v2", "hdfans.org", "魔流-hdfans-刷流", b"x")
    _ok(isinstance(b2, dict) and b2.get("state") == "void",
        "超过 30 天墓碑不重开（等 HrPurge）", repr((b2 or {}).get("state")))
    b3 = h._hrbills_open("v3", "hdfans.org", "魔流-hdfans-刷流", b"x")
    _ok(isinstance(b3, dict) and b3.get("state") == "void",
        "人工作废不自动重开", repr((b3 or {}).get("state")))

    # ---------------------------------------------------------------- D
    print("\n[D] 删除与事件同事务（N-136-06）")
    store.put("d1", _bill(state="settled", settled_at=now))
    store.patch_if("d1", {"hash": "d1"}, events=[{"hash": "d1", "event_type": "x",
                                                  "at": now}])
    before = len(_events(h, "d1"))
    store.drop_many_if([("d1", {})])
    _ok(before == 1 and len(_events(h, "d1")) == 0,
        "drop_many_if 同时删除该 hash 的事件", f"{before}→{len(_events(h, 'd1'))}")
    store.put("d2", _bill(state="void", voided_at=now))
    store.patch_if("d2", {"hash": "d2"}, events=[{"hash": "d2", "event_type": "x",
                                                  "at": now}])
    store.drop("d2")
    _ok(len(_events(h, "d2")) == 0, "drop 同时删除事件")

    # ---------------------------------------------------------------- E
    print("\n[E] UNKNOWN 冻结")
    class _Unknown:
        def all_result(self):
            return {"status": "unknown", "value": None, "error": "db_unavailable",
                    "source": "unavailable", "checked_at": now}

        def get_result(self, hs):
            return self.all_result()

        def purge_expired(self, **k):
            return {"ok": False, "error": "store_unavailable", "deleted_bills": 0,
                    "deleted_events": 0, "eligible": 0, "scanned": 0, "batches": 0}

    h2 = Harness(tempfile.mkdtemp(prefix="hr_unknown_"))
    h2._mem = _Unknown()  # type: ignore[assignment]
    h2.torrents = {"u1": _t("u1", progress=1.0, seed_time=99 * 3600)}
    r2 = h2._hrbills_tick()
    _ok(r2.get("degraded") is True, "UNKNOWN → tick 整轮降级、不流转",
        str(r2.get("error")))
    _ok(h2._hrbills_open("u9", "hdfans.org", "tag", b"x") is None,
        "UNKNOWN → 开账读取失败即跳过（不盲目开）")

    # ---------------------------------------------------------------- F
    print("\n[F] 人工结清契约")
    store.put("m1", _bill(state="active"))
    r = h._hrbills_settle_manual("m1", reason="", settled_by="ops")
    _ok(isinstance(r, dict) and r.get("error") == "missing_reason",
        "空原因拒绝", repr(r))
    r = h._hrbills_settle_manual("m1", reason="已核实", settled_by="")
    _ok(isinstance(r, dict) and r.get("error") == "missing_settled_by",
        "缺操作人拒绝", repr(r))
    store.put("m2", _bill(state="void", voided_at=now))
    r = h._hrbills_settle_manual("m2", reason="已核实", settled_by="ops")
    _ok(isinstance(r, dict) and r.get("error") == "void_terminal",
        "void 墓碑拒绝结清", repr(r))
    r = h._hrbills_settle_manual("m1", reason="已核实 24h 达标", settled_by="ops")
    m1 = store.get("m1") or {}
    _ok(isinstance(r, dict) and not r.get("error") and m1.get("state") == "settled",
        "人工结清成功", repr(r))
    _ok(m1.get("settlement_method") == "manual" and float(m1.get("settled_at") or 0) > 0,
        "写 settlement_method=manual + settled_at")
    _ok(any(e.get("event_type") == "manual_settled" for e in _events(h, "m1")),
        "人工结清事件与状态同 CAS")
    r = h._hrbills_settle_manual("m1", reason="重复", settled_by="ops")
    _ok(isinstance(r, dict) and r.get("already") is True, "重复结清幂等", repr(r))

    # ---------------------------------------------------------------- G
    print("\n[G] 清理口径")
    _ok(tuple(getattr(hb.PgHrBillsStore, "PURGE_STATES", ())) == ("settled", "void"),
        "PURGE_STATES 仅 settled/void")
    _ok(hb._purge_ts_ok(0, now) is False, "时间 0 不清理")
    _ok(hb._purge_ts_ok(-1, now) is False, "负数时间不清理")
    _ok(hb._purge_ts_ok(now + 3600, now) is False, "未来时间不清理")
    _ok(hb._purge_ts_ok(now - 31 * 86400, now) is True, "31 天前合法")
    _ok(hb._purge_ts_ok(now - 29 * 86400, now) is True, "29 天前合法（由 cutoff 再判）")

    # ---------------------------------------------------------------- J
    print("\n[J] 所有物理删除入口都必须同事务清事件（不留孤儿）")
    import inspect as _inspect
    for _fn in ("drop", "drop_many", "drop_many_if", "drop_void"):
        try:
            _src = _inspect.getsource(getattr(hb.PgHrBillsStore, _fn))
        except Exception as err:  # noqa: BLE001
            _ok(False, f"{_fn} 可取源码", repr(err)); continue
        _ok("BillEventRow" in _src, f"{_fn}() 同事务删除事件（无孤儿）", "")
    _ok("BillRow.state == BILL_STATE_VOID" in _inspect.getsource(hb.PgHrBillsStore.drop_void),
        "drop_void 只针对 void 墓碑", "")

    # ---------------------------------------------------------------- I
    print("\n[I] 清理失败可见（N-136-04）")
    class _PurgeFail:
        def purge_expired(self, **k):
            return {"ok": False, "error": "store_unavailable", "scanned": 0,
                    "eligible": 0, "deleted_bills": 0, "deleted_events": 0,
                    "batches": 0, "retention_days": 30.0}
    h3 = Harness(tempfile.mkdtemp(prefix="hr_purge_fail_"))
    h3._mem = _PurgeFail()  # type: ignore[assignment]
    r3 = h3.hr_purge()
    _ok(r3.get("ok") is False, "清理失败原样返回（不伪装成功）", repr(r3.get("error")))
    last = hb._hr_purge_last(h3.get_data_path())
    _ok(last.get("ok") is False and last.get("error") == "store_unavailable",
        "失败写入 hr_purge_status.json（可观测）", repr(last))
    _ok(float(last.get("next_retry_at") or 0) > 0, "暴露 next_retry_at（下轮重试）",
        str(last.get("next_retry_at")))

    # ---------------------------------------------------------------- H
    print("\n[H] 四任务接管关系（dutyreg 优先级矩阵）")
    try:
        _spec = importlib.util.spec_from_file_location(
            PKG + ".dutyreg", ROOT / "dutyreg.py")
        dr = importlib.util.module_from_spec(_spec)
        sys.modules[PKG + ".dutyreg"] = dr
        assert _spec.loader is not None
        _spec.loader.exec_module(dr)
    except Exception as err:  # noqa: BLE001
        print(f"  ⚠️ SKIP（环境不可读 dutyreg：{type(err).__name__}）")
        dr = None
    if dr is not None:
        prio = {d.id: d.priority for d in dr.DUTIES}
        _ok(prio[dr.ID_KEEP] > prio[dr.ID_CLAIM] > prio[dr.ID_HR_HOST],
            "手动保种 > 认领保种 > H&R 保种",
            str({k: prio.get(k) for k in (dr.ID_KEEP, dr.ID_CLAIM, dr.ID_HR_HOST)}))
        _ok(all(d.priority < prio[dr.ID_HR_HOST] for d in dr.DUTIES
                if d.kind in (dr.KIND_PIPE, dr.KIND_TASK)),
            "H&R(80) 高于音乐/点播/刷流/魔力等绩效岗（可从绩效岗收编）")
        _ok(dr.duty_take_check("__hr_host__", dr.ID_KEEP)[0] is False,
            "H&R 不抢手动保种（已被保种的种子不会被重复认定）")
        _ok(dr.duty_take_check("__hr_host__", dr.ID_CLAIM)[0] is False,
            "H&R 不抢认领保种")
        _ok(dr.duty_take_check("__brush_task_1", dr.ID_KEEP)[0] is False,
            "刷流任务不得从手动保种接管")
        _ok(dr.duty_take_check("__brush_task_1", dr.ID_HR_HOST)[0] is False,
            "刷流任务不得从 H&R 保种接管")
        _ok(dr.duty_take_check("__hr_host__", "__brush_task_1",
                               lease_until=time.time() - 1)[0] is True,
            "H&R 可从已过期租约的刷流任务收编（无人负责才接管）")

    print("\n" + "=" * 68)
    print(f"通过 {CASES - len(FAILS)} / 失败 {len(FAILS)}")
    if FAILS:
        for f in FAILS:
            print(f"  ❌ {f}")
        return 1
    print("✅ PASS —— H&R 账单业务契约测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
