#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pg_bills_store.py —— 19.0.0 PgHrBillsStore 真库回环测试（容器内跑）

覆盖：
  1. 工厂选型：db 句柄已绑定 → PgHrBillsStore（mf_bills 表）
  2. put/get/patch/drop/drop_many/drop_void/all/stats 全 API 回环
  3. put 幂等（同 hash 不重复开）
  4. fp 强制填：bill 不带 fp → 反查 mf_seed[hash].resource_id
  5. patch 未知字段安全忽略、None 值可清列
  6. 离线降级：unbind 后工厂回退 JSON 版
  7. ★ 19.12.43 P0：5 个新列（src/missing_since/stalled_at/settle_block/settle_block_at）
     真 PG 写读一致 + 旧数据兼容（缺省 → 键在、值 None）

只写 pgbill* 前缀行，跑完清场。
"""
from __future__ import annotations

import sys
import time
import uuid

sys.path.insert(0, "/tmp/mfpkg")  # 包目录父级
pass

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


def main() -> int:
    from app.db.plugin.registry import get_database

    import magicflow.db as mfdb
    import magicflow.features.hrbills as hrb

    handle = get_database("MagicFlow")
    mfdb.bind_database(handle)
    _ok(mfdb.db_available(), "bind_database 后 db_available()=True")

    from sqlalchemy import inspect as _sa_inspect
    from sqlalchemy import text as _sa_text

    # ---- ★ 19.12.43：真实数据库版本（报告用，必须来自真 PG）----
    sess = mfdb.db_session()
    with sess:
        ver = str(sess.execute(_sa_text("SELECT version()")).scalar() or "")
    print(f"  · 数据库版本：{ver[:120]}")
    _ok(bool(ver), f"SELECT version() 有输出（{ver[:40]}…）")

    # ---- ★ 19.12.43：真迁移验证（ensure_schema 建表 + _ensure_columns 补列）----
    #   路径 = 生产首次触及账本的同一条代码（ledger.LedgerBackend.ensure_schema）。
    #   这里补 5 新列是**纯增量 DDL**（nullable ADD COLUMN），不改任何既有行；
    #   测试行只写 pgbill* 前缀并在结尾清场。
    NEW_FIELDS = ("src", "missing_since", "stalled_at", "settle_block", "settle_block_at")

    sess = mfdb.db_session()
    with sess:
        cols_before = {c["name"] for c in _sa_inspect(sess.connection()).get_columns("mf_bills")}
    print(f"  · 迁移前 mf_bills 列数 {len(cols_before)}，缺 5 新列："
          f"{sorted(set(NEW_FIELDS) - cols_before) or '（已齐）'}")

    import magicflow.ledger as mfled

    class _Host:
        """LedgerBackend 要的最小插件面（get_database + _log）。"""

        def __init__(self, h):
            self._h = h

        def get_database(self):
            return self._h

        def _log(self, msg, level="info"):
            print(f"    [ledger:{level}] {str(msg)[:140]}")

    be = mfled.LedgerBackend(_Host(handle))
    _ok(be.ensure_schema() is True, "ensure_schema 建表+补列走通（真迁移代码）")

    sess = mfdb.db_session()
    with sess:
        cols_after = {c["name"] for c in _sa_inspect(sess.connection()).get_columns("mf_bills")}
    _missing = sorted(set(NEW_FIELDS) - cols_after)
    _ok(not _missing, f"迁移后 mf_bills 含 5 新列（缺 {_missing or '无'}，总列数 {len(cols_after)}）")

    be2 = mfled.LedgerBackend(_Host(handle))
    _ok(be2.ensure_schema() is True, "ensure_schema 幂等（二次跑不炸、不撞 DuplicateColumn）")

    data_dir = "/tmp/pgbill_data"
    import os
    os.makedirs(data_dir, exist_ok=True)
    from pathlib import Path

    store = hrb.get_hr_bills_store(Path(data_dir), kv=None)
    _ok(isinstance(store, hrb.PgHrBillsStore), f"工厂选型 → PgHrBillsStore（实际 {type(store).__name__}）")

    # 测试行标识
    tag = "pgbill" + uuid.uuid4().hex[:16]
    h1 = tag + "a" * (40 - len(tag) - 1) + "1"
    h2 = tag + "a" * (40 - len(tag) - 1) + "2"
    h3 = tag + "a" * (40 - len(tag) - 1) + "3"
    fp1 = uuid.uuid4().hex  # 40-hex

    # mf_seed 里预埋一行，让 fp 反查有源
    sess = mfdb.db_session()
    with sess:
        sess.merge(mfdb.SeedRow(hash=h1, resource_id=fp1, site_id=None, updated=time.time()))
        sess.commit()

    now = time.time()
    # ---- 2/4) put：不带 fp → 反查 mf_seed 强制填 ----
    b1 = store.put(h1, {"site": "pgbill.test", "rule": "site_hr", "state": "pending",
                        "need_h": 24.0, "seeded_h": 0.0, "title": "pgbill t1",
                        "opened_at": now, "progress": 0.0, "opened_by": "open"})
    _ok(b1 is not None, "put 返回账单 dict")
    _ok(str(b1.get("fp") or "") == fp1, f"fp 强制填：空 fp → 反查 mf_seed（{str(b1.get('fp'))[:12]}…）")

    # ---- 3) put 幂等 ----
    again = store.put(h1, {"site": "pgbill.test", "rule": "site_hr", "state": "active"})
    _ok(str(again.get("state")) == "pending", "put 幂等：同 hash 返回已有账单（state 未被覆盖）")

    # ---- get / patch ----
    g = store.get(h1)
    _ok(g is not None and g.get("title") == "pgbill t1", "get 回读")
    p = store.patch(h1, save=False, seeded_h=5.5, settled_at=None, bogus_field="x")
    _ok(p is not None and p.get("seeded_h") == 5.5, "patch 修改已知列")
    p2 = store.patch(h1, save=False, breached_at=None)
    _ok(p2 is not None, "patch None 值安全（清列）")
    g2 = store.get(h1)
    _ok(g2 is not None and g2.get("seeded_h") == 5.5, "patch 持久化（get 复读一致）")

    # ---- ★ 19.12.43 P0：5 个新列（src/missing_since/stalled_at/settle_block/settle_block_at）
    #      写读一致 + 旧数据兼容（缺省 → 键在、值 None）----
    h4 = tag + "a" * (40 - len(tag) - 1) + "4"
    _t = time.time()
    b4 = store.put(h4, {"site": "pgbill.test", "rule": "site_hr", "state": "active",
                        "need_h": 24.0, "title": "pgbill t4", "opened_at": _t,
                        "src": "manual", "missing_since": _t - 3600.0,
                        "stalled_at": _t - 7200.0,
                        "settle_block": "site_unknown", "settle_block_at": _t - 1800.0})
    _ok(b4 is not None and b4.get("src") == "manual"
        and b4.get("settle_block") == "site_unknown"
        and abs(float(b4.get("missing_since") or 0) - (_t - 3600.0)) < 1e-6,
        "5 新列 put 写读一致（真 PG 列投影不再丢字段）")
    g4 = store.get(h4)
    _ok(g4.get("stalled_at") is not None and g4.get("settle_block_at") is not None,
        "stalled_at / settle_block_at 落库")
    p4 = store.patch(h4, save=False, stalled_at=None, settle_block="site_owed")
    g4b = store.get(h4)
    _ok(g4b.get("stalled_at") is None and g4b.get("settle_block") == "site_owed",
        "patch 清列 None + 改 settle_block 持久化")
    # ---- ★ 旧数据兼容（真实旧行，只读）：迁移前就在 mf_bills 里的行，
    #      补列后整行可读、5 新列键在值 None。不挑不改，仅 get。----
    sess = mfdb.db_session()
    with sess:
        old_hash = (sess.execute(_sa_text(
            "SELECT hash FROM mf_bills WHERE hash NOT LIKE 'pgbill%' LIMIT 1"
        )).scalar() or "")
    if old_hash:
        g_old = store.get(str(old_hash))
        _ok(g_old is not None and all(k in g_old for k in NEW_FIELDS),
            f"真实旧行（…{str(old_hash)[-8:]}）补列后可读、5 新列键在")
        vals = {k: g_old.get(k) for k in NEW_FIELDS}
        _ok(all(v is None for v in vals.values()),
            f"真实旧行 5 新列值全 NULL（迁移前无此列，实测 {vals}）")
    else:
        print("  ·（无非 pgbill 旧行，跳过真实旧行兼容检查）")

    # ---- void / drop_many / all / stats ----
    store.put(h2, {"site": "pgbill.test", "rule": "site_hr", "state": "void",
                   "need_h": 24.0, "title": "pgbill t2", "opened_at": now})
    # ★ 旧数据兼容：h2 只写老字段开账 → 5 新列键在值 None。
    #   （19.12.43 初版把本检查放在 put(h2) 之前 → get 到空、误报 1 败，已修顺序。）
    g5 = store.get(h2)
    _ok(g5 is not None and all(k in g5 and g5.get(k) is None
                               for k in ("src", "missing_since", "stalled_at",
                                         "settle_block", "settle_block_at")),
        "旧数据兼容：老字段开的行，5 新列键在值 None")
    store.put(h3, {"site": "pgbill.test2", "rule": "hit_and_run", "state": "pending",
                   "need_h": 48.0, "title": "pgbill t3", "opened_at": now})
    all1 = store.all()
    _ok(all1.get(h2) is not None and all1.get(h3) is not None, "all() 含新开两张")
    n_void = store.drop_void()
    _ok(n_void >= 1 and store.get(h2) is None, f"drop_void 删 void 行（n={n_void}）")
    n_many = store.drop_many([h3, "pgbill.nonexistent"])
    _ok(n_many == 1 and store.get(h3) is None, f"drop_many 只删存在的（n={n_many}）")
    st = store.stats()
    _ok(int(st.get("total") or 0) >= 1, f"stats total={st.get('total')}")

    # ---- drop ----
    _ok(store.drop(h1) is True and store.get(h1) is None, "drop 单删")
    _ok(store.drop(h1) is False, "drop 幂等（不存在 → False）")

    # ---- 6) 离线降级：unbind → 新 data_dir 工厂回退 JSON 版 ----
    mfdb.unbind_database()
    data_dir2 = "/tmp/pgbill_data2"
    os.makedirs(data_dir2, exist_ok=True)
    store2 = hrb.get_hr_bills_store(Path(data_dir2), kv=None)
    _ok(type(store2).__name__ == "HrBillsStore", f"unbind 后工厂回退 JSON 版（实际 {type(store2).__name__}）")

    # ---- 清场 ----
    mfdb.bind_database(handle)
    sess = mfdb.db_session()
    with sess:
        sess.query(mfdb.BillRow).filter(mfdb.BillRow.hash.like(f"{tag}%")).delete(synchronize_session=False)
        sess.query(mfdb.SeedRow).filter(mfdb.SeedRow.hash == h1).delete(synchronize_session=False)
        sess.commit()

    print(f"\n== 结果：{_OK} ok / {_FAIL} fail ==")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
