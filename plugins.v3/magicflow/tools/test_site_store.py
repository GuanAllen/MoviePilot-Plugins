#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · SiteStore（三套站点 kv 账本 → 表）离线单测（12.1.0 WS2）。

验什么：
  1. §2.1/§2.3 的**纯映射往返**：``rec → 列 → rec`` 无损（已知列 + ``rules_extra``/``extra``
     兜底未知键 + ``None`` 值不丢语义）；
  2. SiteStore 的 **slot 分派**（未知槽 → 空/无操作，不抛）；
  3. SiteStore 的 **get/save 真往返**（用桩 backend + 内存假 session + 假 select，
     **不连任何真库**），覆盖 ``site_rules`` / ``site_caps`` / ``sitecap_override`` /
     ``crossseed_sources`` 四个槽；
  4. ``callbacks()`` 适配器（兼容 ``get_data(key)`` / ``save_data(key=, value=)`` /
     ``save_data(key, value)`` 三种旧姿势）。

纯标准库 + 本地 stub，离线可跑。用法：``python3 tools/test_site_store.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_site_store_test"

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


# ---------------------------------------------------------------------------
# 桩：app.*（db.py 顶部 try/except 退化）+ sqlalchemy（db/ledger 顶层 import 用）
# ---------------------------------------------------------------------------
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


def _stub_app():
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
    _stub_sqlalchemy()
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    _pkg(PKG + ".sites", ROOT / "sites")
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
    return sitestore


# ---------------------------------------------------------------------------
# 假 sqlalchemy select / 假表 / 假 session（供 SiteStore.get/save 真往返）
# ---------------------------------------------------------------------------
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

    def commit(self):
        pass

    def close(self):
        pass


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


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeBackend:
    """桩 backend：只提供 SiteStore 需要的 ``_lock`` 与 ``_session()``。"""

    def __init__(self, db):
        self.db = db
        self._lock = threading.RLock()

    def _session(self):
        return _FakeSession(self.db)


def _build_fake_db(sitestore) -> dict:
    """按 sitestore 的列映射造两个假表类 + 内存库。"""
    site_cols = ["site_id", "domain"] + list(sitestore._RULE_COLUMNS) + [
        "rules_extra", "caps", "updated", "created"]
    cross_cols = ["sib_hash"] + list(sitestore._CROSSSEED_COLUMNS) + [
        "extra", "updated", "created"]

    class FakeSiteRow(_Row):
        __tablename__ = "mf_site"

        def __init__(self, **kw):
            defaults = {c: None for c in site_cols}
            defaults.update(kw)
            super().__init__(**defaults)

    class FakeCrossRow(_Row):
        __tablename__ = "mf_crossseed"

        def __init__(self, **kw):
            defaults = {c: None for c in cross_cols}
            defaults.update(kw)
            super().__init__(**defaults)

    for c in site_cols:
        setattr(FakeSiteRow, c, _Col("mf_site", c))
    for c in cross_cols:
        setattr(FakeCrossRow, c, _Col("mf_crossseed", c))

    # 替换 sitestore 里的 mfdb 指向，让 SiteStore 用假表类
    fake_db = types.ModuleType("mf_fake_db")
    fake_db.SiteRow = FakeSiteRow
    fake_db.CrossSeedRow = FakeCrossRow
    return {"mf_site": [], "mf_crossseed": []}, FakeSiteRow, FakeCrossRow, fake_db


# ---------------------------------------------------------------------------
def test_pure_mapping(sitestore) -> None:
    print("\n[1] 纯映射往返：site_rules → mf_site 列 → 回读")
    rec = {
        "domain": "PT.BTSCHOOL.CLUB", "hr": True, "hr_src": "welcome",
        "seed_hours": 240.0, "seed_need_hours": 20.0, "seed_cap": None,
        "seed_window_hours": 240.0, "exam_avg_hours": 30.0,
        "free_over_gb": 20.0, "free_original": True, "free_ep1": False,
        "source": "welcome", "confidence": "high", "evidence": "rules.php 原文",
        "probed_at": 1758000000.0, "rule_url": "https://x/rules.php",
        "rule_label": "H&R", "rule_src": "rules.php", "rule_mail_id": "m1",
        "rule_mail_subject": "欢迎", "name": "学校", "note": "学校 10 天",
        "exam_evidence": "指标2", "per_torrent_hr": False, "updated": 1758000001.0,
        # framework 落真列；其余未知键 → rules_extra 兜底
        "framework": "nexusphp", "seed_hours_seen": 10.0, "site_id": 7,
    }
    cols = sitestore.rec_to_site_columns(rec["domain"], rec, 123.0)
    _ok(cols["domain"] == "pt.btschool.club", "domain 归一（小写）")
    _ok(cols["hr"] is True and cols["seed_hours"] == 240.0, "已知列逐字段落列")
    _ok(cols["framework"] == "nexusphp", "framework 落 mf_site 真列（不是兜底 JSON）")
    _ok(cols["rules_extra"] == {"seed_hours_seen": 10.0, "site_id": 7},
        "未知键进 rules_extra 兜底")
    back = sitestore.site_columns_to_rec(cols["domain"], cols)
    _ok(back["hr"] is True and back["seed_hours"] == 240.0, "回读：已知列还原")
    _ok(back.get("framework") == "nexusphp" and back.get("seed_hours_seen") == 10.0
        and back.get("site_id") == 7, "回读：rules_extra 合并还原未知键")
    _ok(back.get("domain") == "pt.btschool.club" and back.get("updated") == 1758000001.0,
        "回读：domain/updated 还原")

    print("\n[2] 纯映射往返：crossseed_sources → mf_crossseed 列 → 回读")
    crec = {
        "sib_hash": "ABCDEF1234", "title": "某 Release", "size_gb": 12.5,
        "site_a": "目标站", "site_b": "来源站", "site_b_domain": "pt.x.club",
        "a_hash": "1234ABCDEF", "hit_and_run": True, "hours": 240.0,
        "seed_until": 1758000000.0, "downloader": "qbittorrent",
        "files_shared": True, "task_id": "t1", "task_name": "任务A",
        "seeded_sec": 72000.0, "backfilled": False, "done": False,
        "created": 1757000000.0, "updated": 1757000001.0,
        # 未知键 → extra 兜底（实际 rec 里有这些：resource_id/need_hours/pool/done_ts）
        "resource_id": "fp:abc", "need_hours": 20.0, "pool": "silent", "done_ts": 0.0,
    }
    ccols = sitestore.rec_to_crossseed_columns(crec["sib_hash"], crec, 123.0)
    _ok(ccols["sib_hash"] == "abcdef1234", "sib_hash 归一（小写）")
    _ok(ccols["hours"] == 240.0 and ccols["downloader"] == "qbittorrent", "已知列逐字段落列")
    _ok(ccols["extra"] == {"resource_id": "fp:abc", "need_hours": 20.0, "pool": "silent", "done_ts": 0.0},
        "未知键进 extra 兜底")
    cback = sitestore.crossseed_columns_to_rec(ccols["sib_hash"], ccols)
    _ok(cback["hours"] == 240.0 and cback.get("need_hours") == 20.0
        and cback.get("pool") == "silent", "回读：已知列 + extra 合并还原")
    _ok(cback.get("sib_hash") == "abcdef1234", "回读：sib_hash 还原")


def test_store_roundtrip(sitestore) -> None:
    print("\n[3] SiteStore get/save 真往返（桩 backend + 内存假 session）")
    db, FakeSiteRow, FakeCrossRow, fake_db = _build_fake_db(sitestore)
    sitestore.mfdb = fake_db
    try:
        store = sitestore.SiteStore(_FakeBackend(db))

        # ---- site_rules 槽 ----
        store.save("site_rules", {
            "pt.btschool.club": {
                "hr": True, "seed_hours": 240.0, "source": "welcome",
                "confidence": "high", "name": "学校", "note": "10 天",
                "framework": "nexusphp",
            },
            "ptcafe.club": {"hr": False, "seed_hours": 0.0, "source": "manual"},
        })
        got = store.get("site_rules")
        _ok(len(got) == 2, f"site_rules 写入 2 条 → 读回 {len(got)} 条")
        _ok(got["pt.btschool.club"]["hr"] is True
            and got["pt.btschool.club"]["seed_hours"] == 240.0
            and got["pt.btschool.club"]["framework"] == "nexusphp", "site_rules 回读字段一致")
        _ok(got["ptcafe.club"]["hr"] is False, "site_rules 第二条回读一致")
        _ok("updated" in got["pt.btschool.club"], "site_rules 回读带 updated")

        # 空值/未知键兜底：再存一个全 None + 纯未知键的记录
        store.save("site_rules", {"weird.site": {"hr": None, "custom_zzz": "hello"}})
        got2 = store.get("site_rules")
        _ok(got2["weird.site"].get("custom_zzz") == "hello", "site_rules 未知键兜底可回读")

        # ---- site_caps 槽 ----
        store.save("site_caps", {
            "hdtime.org": {"framework": "nexusphp", "free_index": True,
                           "free_spstates": [2, 4], "probe_ver": 3},
        })
        caps = store.get("site_caps")
        _ok(caps.get("hdtime.org", {}).get("framework") == "nexusphp", "site_caps 回读 framework")
        _ok(caps.get("hdtime.org", {}).get("free_spstates") == [2, 4], "site_caps 回读 free_spstates")

        # ---- sitecap_override 槽（空 → {}；写后回读）----
        _ok(store.get("sitecap_override") == {}, "sitecap_override 初始为空 dict")
        store.save("sitecap_override", {"hdtime.org": {"free_index": False}})
        _ok(store.get("sitecap_override") == {"hdtime.org": {"free_index": False}},
            "sitecap_override 写后回读一致")

        # ---- crossseed_sources 槽 ----
        store.save("crossseed_sources", {
            "abcdef1234": {"title": "X", "hours": 240.0, "downloader": "qbittorrent",
                           "need_hours": 20.0, "pool": "silent"},
        })
        cs = store.get("crossseed_sources")
        _ok(len(cs) == 1 and cs["abcdef1234"]["hours"] == 240.0
            and cs["abcdef1234"]["need_hours"] == 20.0, "crossseed 回读已知列 + extra")

        # ---- 未知槽 / 非 dict value：不抛、空/无操作 ----
        _ok(store.get("no_such_slot") == {}, "未知槽 get → {}（不抛）")
        store.save("no_such_slot", {"a": 1})  # 不抛
        store.save("site_rules", "not-a-dict")  # 不抛
        _ok(True, "未知槽 save / 非 dict value：不抛")

        # ---- callbacks 适配器：三种旧姿势 ----
        _get, _save = store.callbacks("site_rules")
        _ok(_get("site_rules") == store.get("site_rules"), "callbacks._get(key) 忽略 key 回槽")
        _save(key="site_rules", value={"ptcafe.club": {"hr": True, "source": "manual"}})
        _ok(store.get("site_rules")["ptcafe.club"]["hr"] is True, "callbacks._save(key=, value=) 落槽")
        _save("site_rules", {"ptcafe.club": {"hr": False, "source": "manual"}})
        _ok(store.get("site_rules")["ptcafe.club"]["hr"] is False, "callbacks._save(key, value) 位置传参落槽")
    finally:
        sitestore.mfdb = sys.modules[PKG + ".db"]


def main() -> int:
    print("=" * 64)
    print("魔流 · SiteStore（三套站点 kv 账本 → 表）离线单测")
    print("=" * 64)
    sitestore = _load_modules()
    test_pure_mapping(sitestore)
    test_store_roundtrip(sitestore)
    print("\n" + "=" * 64)
    if _FAIL == 0:
        print(f"✅ PASS —— 共 {_OK} 项全过")
        return 0
    print(f"❌ FAIL —— {_FAIL} 项失败 / {_OK} 项通过")
    return 1


if __name__ == "__main__":
    sys.exit(main())
