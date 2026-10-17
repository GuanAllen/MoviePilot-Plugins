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

    # ---- void / drop_many / all / stats ----
    store.put(h2, {"site": "pgbill.test", "rule": "site_hr", "state": "void",
                   "need_h": 24.0, "title": "pgbill t2", "opened_at": now})
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
