#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 任务 111 / HR-03：六条危险消费面故障注入（F7–F12 独立验证）。

F7 crossseed 完成判定 / F8 永久 drop 来源份 / F9 保护集合收缩 /
F10 deletegate 删除闸门 / F11 hr.py 义务判定 / F12 protection 保护集合。

每条都在「账单存储 UNKNOWN」下断言**保守方向**（不放行、不缩小、不静默）。
纯离线：桩依赖 + 加载真实模块。
用法：python3 tools/test_hr_consumer_guards.py
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_t111_cons"
FAILS: list = []
CASES = 0


def _ok(cond, name, detail=""):
    global CASES
    CASES += 1
    print(("  ✅ " if cond else "  ❌ ") + name + (f" —— {detail}" if (detail and not cond) else ""))
    if not cond:
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


class _Shared:
    def __init__(self):
        import threading
        self.lock = threading.RLock()
        self.singletons = {}


_SHARED = _Shared()


def _mod(name, **attrs):
    m = sys.modules.get(name) or types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    if "__getattr__" not in m.__dict__:
        m.__getattr__ = lambda n: _Any(f"{name}.{n}")
    sys.modules[name] = m
    # ★ ``from .. import x`` 会先取包属性；必须把子模块显式挂到包上，
    #   否则包的 __getattr__ 会先返回万能桩（曾导致 cacheops 变成 _Any）。
    if name.startswith(PKG + "."):
        pkg_mod = sys.modules.get(PKG)
        if pkg_mod is not None:
            setattr(pkg_mod, name[len(PKG) + 1:], m)
    return m


def _load(rel: str, modname: str):
    spec = importlib.util.spec_from_file_location(modname, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _stubs():
    _mod("app")
    _mod("app.schemas", Response=type("Response", (), {}))
    _mod("app.sdk")
    _mod("app.sdk.logging", logger=type("L", (), {
        "warning": staticmethod(lambda *a, **k: None),
        "info": staticmethod(lambda *a, **k: None),
        "error": staticmethod(lambda *a, **k: None),
        "debug": staticmethod(lambda *a, **k: None)})())
    pkg = _mod(PKG)
    pkg.__path__ = [str(ROOT)]
    _mod(PKG + ".common", HR_COMPLETE_RATIO_DEFAULT=0.999,
         HR_DEADLINE_WARN_HOURS_DEFAULT=48.0, HR_SEED_MARGIN_HOURS_DEFAULT=2.0,
         HR_OWED_TTL=3600, HR_NEED_HOURS_DEFAULT=24.0,
         hr_incomplete=lambda t, r: False, hr_complete_ratio_of=lambda host, site: 0.999,
         is_secret_blank=lambda v: not v)
    _mod(PKG + ".tags", MARK_REUSE="mark", MARK_HR="hr", SUB_PLAIN="plain",
         SUB_RESOURCE="res", SUB_NEW="new", DUTY_STATES=(), STATE_HR="H&R",
         STATE_KEEP="keep", STATE_SILENT="silent", STATE_ONDEMAND="ondemand",
         is_library_asset=lambda t: False, is_reuse_copy=lambda tags: False,
         is_music_line=lambda t: False)
    _mod(PKG + ".dutyops", claim_hashes=lambda host, site: set(),
         assign=lambda *a, **k: None, release=lambda *a, **k: None)
    _mod(PKG + ".downloader_ops", seed_hours_for_hr=lambda t: 0.0,
         DownloaderAdapter=type("DownloaderAdapter", (), {}),
         QB_DOWNLOADING_STATES=(), QB_PAUSED_STATES=())
    _mod(PKG + ".fingerprint", fingerprint=lambda *a, **k: "",
         info_hash=lambda *a, **k: "")
    _mod(PKG + ".live_stats", title_match=lambda a, b: False)
    _mod(PKG + ".persistence", _shared=lambda: _SHARED,
         OperationItem=type("OperationItem", (), {}))
    _mod(PKG + ".crossseed", CROSSSEED_TAG="cs", CrossSeedPending=type("P", (), {}),
         CrossSeedSources=type("S", (), {}))
    _mod(PKG + ".dtier", TierCache=type("TierCache", (), {}))
    _mod(PKG + ".cacheops", value=lambda env, ttl: None,
         entry=lambda v: v, SingleFlight=type("SF", (), {}))
    _mod(PKG + ".envops", env_float=lambda *a, **k: 0.0,
         env_int=lambda *a, **k: 0)
    _mod(PKG + ".sitestore", get_site_store=lambda *a, **k: _Any(),
         slot_callbacks=lambda *a, **k: [None, lambda **kk: None])


def main() -> int:
    _stubs()
    hb = _load("features/hrbills.py", PKG + ".features.hrbills")
    dg = _load("features/deletegate.py", PKG + ".features.deletegate")
    hrm = _load("features/hr.py", PKG + ".features.hr")
    cs = _load("features/crossseed.py", PKG + ".features.crossseed")
    pr = _load("features/protection.py", PKG + ".features.protection")
    print("模块加载成功：deletegate / hr / crossseed / protection")

    class UnknownStore:
        def get_result(self, h):
            return hb._hr_unknown("db_unavailable", "pg")

        def all_result(self):
            return hb._hr_unknown("db_unavailable", "pg")

        def get(self, h):
            return None

        def all(self):
            return {}

        def drop(self, h):
            return False

        def drop_many(self, hs):
            return 0

    class FoundStore:
        def __init__(self, bills, fail=False):
            self.bills = dict(bills)
            self.fail = fail

        def get_result(self, h):
            if self.fail:
                return hb._hr_unknown("db_unavailable", "pg")
            b = self.bills.get(h)
            return hb._hr_found(b, "pg") if isinstance(b, dict) else hb._hr_absent("pg")

        def all_result(self):
            if self.fail:
                return hb._hr_unknown("db_unavailable", "pg")
            return hb._hr_found(dict(self.bills), "pg")

        def get(self, h):
            return self.bills.get(h)

        def all(self):
            return dict(self.bills)

    b_active = {"hash": "a" * 40, "site": "carpt.net", "rule": "site_hr",
                "state": "active", "need_h": 24.0, "seeded_h": 1.0, "progress": 1.0}
    b_settled = dict(b_active, state="settled", settlement_method="auto")

    print("\n── F10 deletegate：UNKNOWN 必须 fail-closed 拦删除 ──")
    class GateHost(dg.DeleteGateMixin):
        pass

    g = GateHost()
    g._tag_state = lambda: {}
    g._tag_all_torrents = lambda: {}
    g._hrbills_store = lambda: UnknownStore()
    why = g._delete_bill_assert(["a" * 40])
    _ok(why.get("a" * 40) == "账单存储不可用（保守拦截 H&R）",
        "存储 UNKNOWN → 拦（不再 continue 放行）", str(why))

    def _raise():
        raise RuntimeError("store accessor boom")

    g._hrbills_store = _raise
    why2 = g._delete_bill_assert(["b" * 40])
    _ok("b" * 40 in why2, "取不到 store（异常）→ 同样拦（F10 第二分支）", str(why2))

    g._hrbills_store = lambda: FoundStore({"a" * 40: b_active})
    why3 = g._delete_bill_assert(["a" * 40])
    _ok("a" * 40 in why3 and "欠 H&R 账单" in why3["a" * 40], "FOUND active/site_hr → 拦")
    g._hrbills_store = lambda: FoundStore({"a" * 40: b_settled})
    _ok(not g._delete_bill_assert(["a" * 40]), "FOUND settled → 不拦")

    print("\n── F11 hr.py：读取异常不得当作「无义务」 ──")
    class HrHost(hrm.HrMixin):
        pass

    h = HrHost()
    h._hr_incomplete_of = lambda site, t: False
    h._hr_is_reuse = lambda t: False
    h._resource_source_index = lambda: {}
    h._hr_due_hours = lambda need: float(need) + 2.0
    h._hrbills_store = lambda: UnknownStore()
    t = types.SimpleNamespace(hash="c" * 40, progress=1.0)
    owed, need, seeded, src = h._hr_obligation("carpt.net", t)
    _ok(owed is True and src == "账单存储不可用(保守按欠 H&R)",
        "UNKNOWN → 保守按欠 H&R（不跳过保护）", f"{owed}/{src}")
    h._hrbills_store = lambda: FoundStore({})
    owed2, _, _, src2 = h._hr_obligation("carpt.net", t)
    _ok(owed2 is False, "FOUND 且无账单（ABSENT）→ 按原口径判不欠", f"{owed2}/{src2}")

    print("\n── F7/F8 crossseed：UNKNOWN 不放行、不 drop ──")
    class CsHost(cs.CrossSeedMixin):
        pass

    c = CsHost()
    c._hrbills_store = lambda: UnknownStore()
    _ok(c._cs_bill_verdict("d" * 40)[0] == "unknown", "UNKNOWN → verdict=unknown")
    _ok(c._cs_bill_settled("d" * 40) is False, "UNKNOWN → 不放行（False）")
    c._hrbills_store = lambda: FoundStore({"d" * 40: b_settled})
    _ok(c._cs_bill_verdict("d" * 40)[0] == "settled", "FOUND settled → verdict=settled")
    _ok(c._cs_bill_settled("d" * 40) is True, "settled → 放行")
    c._hrbills_store = lambda: FoundStore({})
    _ok(c._cs_bill_verdict("d" * 40)[0] == "absent", "FOUND 无行 → verdict=absent")
    _ok(c._cs_bill_settled("d" * 40) is True, "无账单（确认不存在）→ 放行")

    print("\n── F9 crossseed：保护集合不得因读失败收缩 ──")
    class RawSrc:
        def active(self):
            return {"x" * 40, "y" * 40}

    c._crossseed_sources = lambda: RawSrc()
    c._cs_src_hashes_cache = None
    c._hrbills_store = lambda: UnknownStore()
    got = c._crossseed_source_hashes()
    _ok(got == {"x" * 40, "y" * 40}, "UNKNOWN → 保护集合保留全部（不缩小）", str(got))
    c._cs_src_hashes_cache = None
    c._hrbills_store = lambda: FoundStore(
        {"x" * 40: b_settled, "y" * 40: dict(b_active, site="btschool.club")})
    got2 = c._crossseed_source_hashes()
    _ok(got2 == {"y" * 40}, "FOUND + x 已结清、y 仍欠 → 只放行 x（y 仍保护）", str(got2))

    print("\n── F12 protection：读失败用 last-good，不清空 ──")
    class PrHost(pr.ProtectionMixin):
        _store = None

    p = PrHost()
    p._media_asset_hashes = lambda managed, task: []
    p._hr_bill_owed_hashes = lambda: (_ for _ in ()).throw(RuntimeError("db down"))
    hb._HR_OWED_CACHE["hashes"] = {"z" * 40}
    hb._HR_OWED_CACHE["at"] = hb.time.time()
    task = types.SimpleNamespace(id="t1", site_id="s1")
    out = p._protection_sets(task, managed=[])
    _ok("z" * 40 in out["hard"], "读失败 → 硬保护仍含 last-good 欠账单", str(out["hard"]))
    _ok(out["why"].get("z" * 40) == "欠 H&R 义务（账单）", "理由保留（不静默消失）")

    print("\n" + ("✅ PASS" if not FAILS else f"❌ FAIL（{len(FAILS)} 项）"))
    for f in FAILS:
        print("   -", f)
    print(f"共 {CASES} 项断言")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
