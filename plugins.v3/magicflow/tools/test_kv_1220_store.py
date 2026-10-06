#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 12.2.0 剩余 kv 收口（SiteStore 新槽）离线单测。

验什么：
  1. 纯映射函数：``by_date_to_by_site`` / ``by_site_to_by_date``（pv_usage/signin_records
     的「按日期 ↔ 按站点」重组，无损往返）；
  2. SiteStore 新槽的 get/save 真往返（桩 backend + 内存假 session，**不连任何真库**）：
       reseed_ledger / signin_last_full(标量) / signin_retry / signin_keepalive /
       claim_profile / rescue_stall / ondemand_pending / crossseed_pending /
       pv_budget / live_pv_block / live_alerts / pv_usage / signin_records /
       iyuu_sites / reseed_passkeys；
  3. ``slot_callbacks(plugin, slot)`` 的按槽缓存语义。

纯标准库 + 本地 stub，离线可跑。用法：``python3 tools/test_kv_1220_store.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_kv1220_test"

_OK = 0
_FAIL = 0


def _ok(cond: bool, msg: str) -> None:
    global _OK, _FAIL
    if cond:
        _OK += 1
        print(f"  ✅ {msg}")
    else:
        _FAIL += 1
        print(f"  ❌ {msg}")


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


class _Col:
    def __init__(self, tablename: str, name: str):
        self.tablename = tablename
        self.name = name

    def __eq__(self, other):
        return _Eq(self, other)

    def __hash__(self):
        return id(self)


class _Eq:
    def __init__(self, col, val):
        self.col = col
        self.val = val


class _MaxMarker:
    def __init__(self, tablename, colname):
        self.tablename = tablename
        self.colname = colname


def _select(model):
    return _Sel(model)


class _Sel:
    def __init__(self, model):
        self.model = model
        self.wheres = []

    def where(self, *conds):
        self.wheres.extend(conds)
        return self


def _stub_sqlalchemy():
    sa = types.ModuleType("sqlalchemy")
    sa.delete = object
    sa.select = _select
    sa.update = object
    sa.text = object
    sa.inspect = lambda *a, **k: None

    class _Func:
        def max(self, col):
            return _MaxMarker(getattr(col, "tablename", ""), getattr(col, "name", ""))

    sa.func = _Func()

    def _col(*a, **k):
        return None
    sa.JSON = _col
    sa.Boolean = _col
    sa.Float = _col
    sa.Integer = _col
    sa.String = _col
    sa.Text = _col
    orm = types.ModuleType("sqlalchemy.orm")

    class _DeclarativeBase:
        pass
    orm.DeclarativeBase = _DeclarativeBase
    orm.Mapped = object

    def _mapped_column(*a, **k):
        return None
    orm.mapped_column = _mapped_column
    sa.orm = orm
    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.orm"] = orm
    return sa


class _NullLogger:
    def __getattr__(self, _name):
        return lambda *a, **k: None


def _stub_app():
    for name, attr_map in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
        ("app.sdk.logging", {"logger": _NullLogger()}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attr_map.items():
            setattr(m, k, v)


def _load_modules():
    _stub_sqlalchemy()
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    _pkg(PKG + ".sites", ROOT / "sites")
    _cp = types.ModuleType(PKG + ".sites.claim_presets")
    _cp.preset_for = lambda domain: None  # noqa: E731
    sys.modules[PKG + ".sites.claim_presets"] = _cp
    for modname, attrs in (
        ("bonus", ("TorrentBonusInfo", "calc_bonus_per_hour")),
        ("fetcher", ("SiteCandidateTorrent",)),
        ("recommend", ("recognize",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    _load(PKG + ".common", "common.py")
    _load(PKG + ".tables", "tables.py")
    _load(PKG + ".db", "db.py")
    _load(PKG + ".tags", "tags.py")
    _load(PKG + ".ledger", "ledger.py")
    _load(PKG + ".persistence", "persistence.py")
    sitestore = _load(PKG + ".sitestore", "sitestore.py")
    claim = _load(PKG + ".features.claim", "features/claim.py")
    return sitestore, claim


# ---------------------------------------------------------------------------
# 假表 / 假 session
# ---------------------------------------------------------------------------
class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return _ScalarResult(self._rows)

    def scalar(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, db):
        self.db = db

    def execute(self, stmt):
        model = stmt.model
        if isinstance(model, _MaxMarker):
            rows = self.db.get(model.tablename, [])
            vals = [getattr(r, model.colname, None) for r in rows]
            vals = [v for v in vals if v is not None]
            return _FakeResult([max(vals) if vals else 0])
        rows = list(self.db.get(model.__tablename__, []))
        for w in stmt.wheres:
            rows = [r for r in rows if getattr(r, w.col.name, None) == w.val]
        return _FakeResult(rows)

    def add(self, obj):
        self.db.setdefault(obj.__tablename__, []).append(obj)

    def delete(self, obj):
        rows = self.db.get(obj.__tablename__, [])
        if obj in rows:
            rows.remove(obj)

    def commit(self):
        pass

    def close(self):
        pass


class _FakeBackend:
    def __init__(self, db):
        self.db = db
        self._lock = threading.RLock()

    def _session(self):
        return _FakeSession(self.db)


_SITE_COLS = [
    "site_id", "domain", "name", "mp_site_id", "iyuu_sid", "credential", "caps",
    "pv_budget", "pv_usage", "pv_block", "signin", "alerts", "created", "updated",
]
_SEED_COLS = ["hash", "rescue", "pending", "updated"]
_CROSS_COLS = ["sib_hash", "pending", "created", "updated"]
_RESEED_COLS = ["key", "site_id", "hash", "st", "note", "created", "updated"]
_RUN_COLS = ["key", "value", "created", "updated"]
_CLAIM_COLS = ["key", "site_id", "hash", "tid", "st", "benefit", "note", "task_id", "title", "created", "updated"]


def _build_fake_db(sitestore) -> dict:
    def _mk(name, cols):
        cls = type(name, (_Row,), {})
        cls.__tablename__ = name.lower()
        def _init(self, **kw):  # noqa: ANN202
            d = {c: None for c in cols}
            d.update(kw)
            _Row.__init__(self, **d)
        cls.__init__ = _init
        for c in cols:
            setattr(cls, c, _Col(name.lower(), c))
        return cls

    FakeSite = _mk("mf_site", _SITE_COLS)
    FakeSeed = _mk("mf_seed", _SEED_COLS)
    FakeCross = _mk("mf_crossseed", _CROSS_COLS)
    FakeReseed = _mk("mf_reseed", _RESEED_COLS)
    FakeRun = _mk("mf_run", _RUN_COLS)
    FakeClaim = _mk("mf_claim", _CLAIM_COLS)

    fake_db = types.ModuleType("mf_fake_db")
    fake_db.SiteRow = FakeSite
    fake_db.SeedRow = FakeSeed
    fake_db.CrossSeedRow = FakeCross
    fake_db.ReseedRow = FakeReseed
    fake_db.RunRow = FakeRun
    fake_db.ClaimRow = FakeClaim
    db = {"mf_site": [], "mf_seed": [], "mf_crossseed": [], "mf_reseed": [], "mf_run": [], "mf_claim": []}
    return db, fake_db


def test_pure_mapping(sitestore) -> None:
    print("\n[1] 纯映射：pv_usage / signin_records 按日期 ↔ 按站点")
    by_date = {
        "2026-10-01": {"7": {"browse": 3, "signin": 1}, "9": {"live": 2}},
        "2026-10-02": {"7": {"browse": 1}},
    }
    by_site = sitestore.by_date_to_by_site(by_date)
    _ok(by_site == {
        "7": {"2026-10-01": {"browse": 3, "signin": 1}, "2026-10-02": {"browse": 1}},
        "9": {"2026-10-01": {"live": 2}},
    }, "by_date_to_by_site 正确重组")
    back = sitestore.by_site_to_by_date(by_site)
    _ok(back == by_date, "by_site_to_by_date 逆变换无损往返")


def test_store_roundtrip(sitestore) -> None:
    print("\n[2] SiteStore 新槽 get/save 真往返（桩 backend + 内存假 session）")
    db, fake_db = _build_fake_db(sitestore)
    sitestore.mfdb = fake_db
    try:
        store = sitestore.SiteStore(_FakeBackend(db))

        # ---- reseed_ledger → mf_reseed ----
        store.save("reseed_ledger", {
            "12:abcdef1234": {"st": "ok", "ts": 1758000000.0, "note": "已挂"},
            "12:bbbbbb2222": {"st": "miss", "ts": 1758000001.0, "note": "特征码不一致"},
        })
        got = store.get("reseed_ledger")
        _ok(len(got) == 2, f"reseed_ledger 写 2 条 → 读回 {len(got)} 条")
        _ok(got["12:abcdef1234"]["st"] == "ok" and got["12:abcdef1234"]["ts"] == 1758000000.0
            and got["12:abcdef1234"]["note"] == "已挂", "reseed_ledger 字段无损（st/ts/note）")

        # ---- signin_last_full（标量 float）→ mf_run ----
        store.save("signin_last_full", 1758000100.0)
        _ok(store.get("signin_last_full") == 1758000100.0, "signin_last_full 标量往返")

        # ---- signin_retry / signin_keepalive（dict）→ mf_run ----
        store.save("signin_retry", {"2026-10-06": {"7": 2, "9": 1}})
        _ok(store.get("signin_retry") == {"2026-10-06": {"7": 2, "9": 1}}, "signin_retry dict 往返")
        store.save("signin_keepalive", {"ts": 1758000000.0, "sites": [{"site_id": 7}], "warnings": []})
        _ok(store.get("signin_keepalive")["ts"] == 1758000000.0, "signin_keepalive dict 往返")

        # ---- rescue_stall → mf_seed.rescue ----
        store.save("rescue_stall", {"abcd": 1758000000.0, "ef12": 1758000100.0})
        _ok(store.get("rescue_stall") == {"abcd": 1758000000.0, "ef12": 1758000100.0},
            "rescue_stall {hash: ts} 往返")

        # ---- ondemand_pending → mf_seed.pending ----
        store.save("ondemand_pending", {"abcd": {"title": "X", "year": 2026, "site_id": 7}})
        _ok(store.get("ondemand_pending")["abcd"]["title"] == "X", "ondemand_pending 往返")

        # ---- crossseed_pending → mf_crossseed.pending ----
        store.save("crossseed_pending", {"cdef": {"sib_hash": "cdef", "title": "Y", "a_torrent": "/tmp/x.torrent"}})
        _ok(store.get("crossseed_pending")["cdef"]["title"] == "Y", "crossseed_pending 往返")

        # ---- pv_budget → mf_site.pv_budget（mp_site_id 键）----
        store.save("pv_budget", {"7": 30, "9": 10})
        _ok(store.get("pv_budget") == {"7": 30, "9": 10}, "pv_budget 往返")

        # ---- live_pv_block → mf_site.pv_block ----
        store.save("live_pv_block", {"7": 1759000000.0})
        _ok(store.get("live_pv_block") == {"7": 1759000000.0}, "live_pv_block 往返")

        # ---- live_alerts → mf_site.alerts（"sid:kind" 拆分）----
        store.save("live_alerts", {"7:download_rising": 1758000000.0, "7:traffic_drop": 1758000001.0})
        _ok(store.get("live_alerts") == {"7:download_rising": 1758000000.0, "7:traffic_drop": 1758000001.0},
            "live_alerts 按 sid:kind 拆分/合并往返")

        # ---- pv_usage → mf_site.pv_usage（按 site 重组）----
        store.save("pv_usage", {"2026-10-01": {"7": {"browse": 3}, "9": {"live": 2}}})
        _ok(store.get("pv_usage") == {"2026-10-01": {"7": {"browse": 3}, "9": {"live": 2}}},
            "pv_usage 按日期↔按站点无损往返")

        # ---- signin_records → mf_site.signin（按 site 重组）----
        store.save("signin_records", {"2026-10-01": {"7": {"ok": True}}})
        _ok(store.get("signin_records") == {"2026-10-01": {"7": {"ok": True}}},
            "signin_records 按日期↔按站点无损往返")

        # ---- iyuu_sites → mf_site.credential.__iyuu__（domain 键）----
        store.save("iyuu_sites", {"hdtime.org": {"passkey": "PK1", "uid": "U1"}})
        _ok(store.get("iyuu_sites") == {"hdtime.org": {"passkey": "PK1", "uid": "U1"}},
            "iyuu_sites credential 子槽往返")

        # ---- reseed_passkeys → mf_site.credential.__reseed_passkey__（iyuu_sid 键）----
        store.save("reseed_passkeys", {"12": "passkey-string-12"})
        _ok(store.get("reseed_passkeys") == {"12": "passkey-string-12"},
            "reseed_passkeys credential 子槽往返")

        # ---- claim_profile → mf_site.caps.__claim__（mp_site_id 键）----
        store.save("claim_profile", {"7": {"profile": {"supported": True}, "at": 1758000000.0}})
        _ok(store.get("claim_profile") == {"7": {"profile": {"supported": True}, "at": 1758000000.0}},
            "claim_profile caps 子槽往返")

        # ---- claim_ledger → mf_claim ----
        store.save("claim_ledger", {
            "7:aaaa1111": {"tid": "101", "ts": 1758000000.0, "st": "ok", "benefit": "×2",
                            "note": "已认领", "task": "", "title": "T1"},
            "7:bbbb2222": {"tid": "102", "ts": 1758000100.0, "st": "fail", "benefit": "",
                            "note": "超时", "task": "t1", "title": "T2"},
        })
        got = store.get("claim_ledger")
        _ok(len(got) == 2, f"claim_ledger 写 2 条 → 读回 {len(got)} 条")
        _ok(got["7:aaaa1111"]["st"] == "ok" and got["7:aaaa1111"]["ts"] == 1758000000.0
            and got["7:aaaa1111"]["benefit"] == "×2" and got["7:aaaa1111"]["note"] == "已认领"
            and got["7:aaaa1111"]["tid"] == "101",
            "claim_ledger 字段无损（tid/ts/st/benefit/note/task/title）")
        _ok(got["7:bbbb2222"]["task"] == "t1" and got["7:bbbb2222"]["title"] == "T2",
            "claim_ledger 第二条字段无损")

        # ---- keepalive_alert_day（标量字符串日期）→ mf_run ----
        store.save("keepalive_alert_day", "2026-10-06")
        _ok(store.get("keepalive_alert_day") == "2026-10-06", "keepalive_alert_day 裸串往返")
        store.save("keepalive_alert_day", {"day": "2026-10-07"})
        _ok(store.get("keepalive_alert_day") == {"day": "2026-10-07"}, "keepalive_alert_day dict 形态往返")

        # ---- crossseed_ban → mf_run ----
        store.save("crossseed_ban", {"hdtime.org": {"ts": 1758000000.0, "reason": "H&R 未清"}})
        _ok(store.get("crossseed_ban") == {"hdtime.org": {"ts": 1758000000.0, "reason": "H&R 未清"}},
            "crossseed_ban {domain:{ts,reason}} 往返")

        # ---- 未知槽 / 非 dict ----
        _ok(store.get("no_such_slot") == {}, "未知槽 get → {}")
        store.save("reseed_ledger", "not-a-dict")  # 不抛
        _ok(True, "非 dict save：不抛")

        # ---- slot_callbacks 按槽缓存 ----
        p = _FakePlugin()
        cb1 = sitestore.slot_callbacks(p, "pv_budget")
        cb2 = sitestore.slot_callbacks(p, "pv_budget")
        _ok(cb1 is cb2, "slot_callbacks 同 plugin+slot 返回同一回调对（缓存）")
    finally:
        sitestore.mfdb = sys.modules[PKG + ".db"]


class _FakePlugin:
    plugin_id = "MagicFlow"


def test_claim_ttl(claimmod) -> None:
    """claim_ledger 读侧 TTL 过滤语义（ok/already 永久，fail/full/unmet 过期丢弃）。"""
    print("\n[3] claim_ledger 读侧 TTL 过滤（ok 永久 / fail 过期丢弃）")
    import time as _t

    now = _t.time()
    ttl = float(getattr(claimmod, "CLAIM_FAIL_TTL", 24 * 3600.0))
    raw = {
        "7:aaaa": {"tid": "1", "ts": now - 10, "st": "ok", "benefit": "", "note": "", "task": "", "title": "T1"},
        "7:bbbb": {"tid": "2", "ts": now - 10, "st": "already", "benefit": "", "note": "", "task": "", "title": "T2"},
        "7:cccc": {"tid": "3", "ts": now - (ttl + 100), "st": "fail", "benefit": "", "note": "", "task": "", "title": "T3"},
        "7:dddd": {"tid": "4", "ts": now - (ttl + 100), "st": "full", "benefit": "", "note": "", "task": "", "title": "T4"},
        "7:eeee": {"tid": "5", "ts": now - 10, "st": "fail", "benefit": "", "note": "", "task": "", "title": "T5"},
        "7:ffff": {"tid": "6", "ts": now - (ttl + 100), "st": "unmet", "benefit": "", "note": "", "task": "", "title": "T6"},
    }
    real = claimmod.slot_callbacks

    def _fake_slot_callbacks(plugin, slot):  # noqa: ANN001
        return (lambda *a, **k: raw, lambda *a, **k: None)

    claimmod.slot_callbacks = _fake_slot_callbacks
    try:
        out = claimmod.ClaimMixin._claim_ledger(_FakePlugin())
    finally:
        claimmod.slot_callbacks = real
    _ok("7:aaaa" in out and "7:bbbb" in out, "ok/already 永久保留")
    _ok("7:cccc" not in out, "fail 过期丢弃")
    _ok("7:dddd" not in out, "full 过期丢弃")
    _ok("7:ffff" not in out, "unmet 过期丢弃")
    _ok("7:eeee" in out, "fresh fail 保留")


def test_site_identity(sitestore) -> None:
    """★ 12.2.0 收口：站点 id → 真名/真域名，能对上域名行就复用，绝不造无名垃圾行。"""
    print("\n[4] 站点行身份：id → 真名/真域名（不造垃圾行）")
    db, fake_db = _build_fake_db(sitestore)
    sitestore.mfdb = fake_db
    try:
        backend = _FakeBackend(db)
        store = sitestore.SiteStore(backend)
        sess = backend._session()
        row0 = fake_db.SiteRow(site_id=13, domain="carpt.net", name="CARPT", created=1.0, updated=1.0)
        db["mf_site"].append(row0)

        # ① mp_site_id 解析到已有域名行同名站点 → 复用该行 + 补 mp_site_id，不新增行
        store._mp_site_info = lambda mid: {"name": "CARPT", "domain": "carpt.net"}  # noqa: E731
        r = store._site_row_by_mp_id(sess, 13, 2.0)
        _ok(r is row0 and getattr(r, "mp_site_id", None) == 13, "mp_site_id 命中已有域名行 → 复用")
        _ok(len(db["mf_site"]) == 1, "复用后站点行数不变（未造新行）")
        _ok(r.name == "CARPT", "复用行 name 未被覆写")

        # ② iyuu_sid 解析出真名/域名且无同行 → 建有真名的行（不是 iyuu:131）
        store._mp_site_info = lambda sid: {}  # noqa: E731  （MP 里没有这个 id）
        store._iyuu_site_info = lambda sid: {"name": "朋友", "domain": "pt.keepfrds.com"}  # noqa: E731
        r2 = store._site_row_by_iyuu_sid(sess, 131, 3.0)
        _ok(r2.name == "朋友" and r2.domain == "pt.keepfrds.com"
            and r2.iyuu_sid == 131 and r2.mp_site_id is None,
            "id 无同行 → 建行带真名/域名（不是 iyuu:131），只填对应列")

        # ③ iyuu_sid 命中已有行（跨列去重：那个 id 的行已存在）→ 复用，不另建行
        store._iyuu_site_info = lambda sid: {"name": "CARPT", "domain": "carpt.net"}  # noqa: E731
        r3 = store._site_row_by_iyuu_sid(sess, 13, 4.0)
        _ok(r3 is row0, "同 id 跨列命中 → 复用（不建第二行）")

        # ④ 解析不到 → 兜底命名（不崩、不为空）
        store._iyuu_site_info = lambda sid: {}  # noqa: E731
        r4 = store._site_row_by_iyuu_sid(sess, 999, 5.0)
        _ok(r4.name == "site:999", "无解析信息 → 兜底名 site:999（不为空）")

        # ⑤ 注入提示表（脚本无 plugin.get_data 时的真名来源）
        store.bind_site_hints({"24": {"name": "春天", "domain": "springsunday.net"}})
        r5 = store._site_row_by_mp_id(sess, 24, 6.0)
        _ok(r5.name == "春天" and r5.domain == "springsunday.net",
            "提示表命中 → 建行带真名/域名（不是 site:24）")
        r6 = store._site_row_by_iyuu_sid(sess, 24, 7.0)
        _ok(r6 is r5, "同 id 两个命名空间跨列去重 → 同一行（不重复建行）")
    finally:
        sitestore.mfdb = sys.modules[PKG + ".db"]


def main() -> int:
    print("=" * 64)
    print("魔流 · 12.2.0 剩余 kv 收口（SiteStore 新槽）离线单测")
    print("=" * 64)
    sitestore, claimmod = _load_modules()
    test_pure_mapping(sitestore)
    test_store_roundtrip(sitestore)
    test_site_identity(sitestore)
    test_claim_ttl(claimmod)
    print("\n" + "=" * 64)
    if _FAIL == 0:
        print(f"✅ PASS —— 共 {_OK} 项全过")
        return 0
    print(f"❌ FAIL —— {_FAIL} 项失败 / {_OK} 项通过")
    return 1


if __name__ == "__main__":
    sys.exit(main())
