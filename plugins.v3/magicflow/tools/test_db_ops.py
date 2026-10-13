#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_db_ops.py —— 账本 CRUD 边界行为（2026-10-11 修 P1/P2）

覆盖：
  1. ``_site_id(name, create=False)`` 不自动建 mf_site 行（噪声行根因）
  2. ``_member_same`` 只比较落库字段（「跳过优化失效」修复）
  3. ``gc_empty_groups`` 清空壳 grouped 资源行、留裸行/有成员组
  4. 未登记站名 → 站名兜底进 ``origin_site``，读回不丢（来源一致性）

真库测试（真 PG 连接 / 真 schema），只写 ``dbop*`` 前缀行，跑完清场。
"""
from __future__ import annotations

import sys
import time
import uuid

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


def _load_plugin():
    from app.db.plugin.registry import get_database

    try:
        from app.runtime.extensions.plugin.manager import PluginManager

        running = PluginManager().running_plugins or {}
        p = running.get("MagicFlow")
        if p is not None:
            mod_name = type(p).__module__
            pkg = sys.modules.get(mod_name) or sys.modules.get(mod_name.rsplit(".", 1)[0])
            if pkg is not None:
                return p, pkg
    except Exception:  # noqa: BLE001
        pass

    handle = get_database("MagicFlow")

    class _Shim:
        plugin_id = "MagicFlow"

        def get_database(self):
            return handle

        def _log(self, msg, level="info"):  # noqa: ANN001
            pass

    import importlib

    return _Shim(), importlib.import_module("app.plugins.magicflow")


def main() -> int:
    p, pkg = _load_plugin()
    import importlib

    ledger = importlib.import_module(pkg.__name__ + ".ledger")
    mfdb = importlib.import_module(pkg.__name__ + ".db")
    from sqlalchemy import delete, func, select

    be = ledger.get_backend(p)
    if be is None or not be.ensure_schema():
        raise SystemExit("✗ 账本后端/建表失败")

    def site_count() -> int:
        sess = be._session()
        try:
            return int(sess.execute(select(func.count()).select_from(mfdb.SiteRow)).scalar() or 0)
        finally:
            sess.close()

    print("== 账本 CRUD 边界测试 ==")

    # ---- 1) create=False 不建站行 ----
    before = site_count()
    sid = be._site_id("dbop.no.such.site", create=False)
    _ok(sid is None, "未知站名 create=False → None")
    _ok(site_count() == before, "create=False 未新建 mf_site 行")

    # ---- 2) _member_same 只比落库字段 ----
    a = {"site": "A", "completed_at": 1.0, "added_at": 2.0, "reused": False, "origin_site": "A"}
    b = dict(a, downloaded=True, progress=1.0, added=3.0, downloader="qb", dl_bytes=0.0)
    _ok(be._member_same(a, b) is True, "_member_same：额外内存字段不影响相等")
    _ok(be._member_same(a, {"site": "B", "completed_at": 1.0}) is False, "_member_same：site 不同 → 不等")
    _ok(be._member_same(None, {"site": "A", "completed_at": 1.0}) is False, "_member_same：prev None → 不等")

    # ---- 3) gc_empty_groups ----
    eid = uuid.uuid4().hex                    # 空壳 grouped（应删）
    nid = uuid.uuid4().hex                    # 裸行 grouped=false（应留）
    gid = uuid.uuid4().hex                    # 有成员 grouped（应留）
    shash = uuid.uuid4().hex + uuid.uuid4().hex[:8]   # 40-hex
    now = time.time()
    sess = be._session()
    try:
        sess.merge(mfdb.ResourceRow(resource_id=eid, grouped=True, updated=now))
        sess.merge(mfdb.ResourceRow(resource_id=nid, grouped=False, updated=now))
        sess.merge(mfdb.ResourceRow(resource_id=gid, grouped=True, updated=now))
        sess.merge(mfdb.SeedRow(hash=shash, resource_id=gid, site_id=None, updated=now))
        sess.commit()
    finally:
        sess.close()
    n = be.gc_empty_groups()
    _ok(n >= 1, f"gc_empty_groups 清掉空壳（{n}）")
    sess = be._session()
    try:
        def _has(rid: str) -> bool:
            return sess.execute(select(mfdb.ResourceRow).where(
                mfdb.ResourceRow.resource_id == rid)).scalars().first() is not None
        _e = _has(eid)
        _n = _has(nid)
        _g = _has(gid)
    finally:
        sess.close()
    _ok(_e is False, "空壳 grouped 已删")
    _ok(_n is True, "裸行（grouped=false）保留")
    _ok(_g is True, "有成员的 grouped 保留")

    # ---- 4) 未登记站名 → origin_site 兜底，读回不丢 ----
    h2 = "dbop" + uuid.uuid4().hex[:24]
    st = ledger.SeedLedgerStore(be)
    st.put(h2, {"site": "dbop.ghost.site", "state": "静默", "sub": "普通"})
    _ok(site_count() == before, "put 未登记站名的种子 → 不建 mf_site 行")
    be2 = ledger.LedgerBackend(p)
    be2.ensure_schema()
    st2 = ledger.SeedLedgerStore(be2)
    _ok(st2.get(h2).get("site") == "dbop.ghost.site", "fresh 回读：站名经 origin_site 兜底不丢")

    # ---- 清场 ----
    sess = be._session()
    try:
        sess.execute(delete(mfdb.SeedRow).where(mfdb.SeedRow.hash.in_([shash, h2])))
        sess.execute(delete(mfdb.ResourceRow).where(mfdb.ResourceRow.resource_id.in_([eid, nid, gid])))
        sess.commit()
    finally:
        sess.close()

    print(f"\n✅ PASS —— 共 {_OK} 断言，{_FAIL} 失败")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
