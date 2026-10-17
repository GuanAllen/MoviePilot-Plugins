#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pg_journal_store.py —— 19.0.0 PgOperationJournal 真库回环测试（容器内跑）

覆盖：
  1. add → submitting 行落 mf_journal；finalize → state/items/duration/resolved_at 回写
  2. record（即时完成）一次落库 completed
  3. get / list_by_task / list_recent（kind 过滤 + 逗号多类型 + 时间降序）
  4. update_state / delete_task / delete_old
  5. set_keep + add 触发 _pg_prune_task（PG 侧裁剪）
  6. MagicFlowStore 装配：绑定后 _new_journal → PgOperationJournal；rebind_journal 幂等
  7. 离线降级：unbind → add/finalize 走父类 JSON 路径

只写 pgjr 前缀 task_id，跑完清场。
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "/tmp/mfpkg")

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
    import magicflow.persistence as ps

    handle = get_database("MagicFlow")
    mfdb.bind_database(handle)

    data_dir = Path("/tmp/pgjr_data")
    import os
    os.makedirs(data_dir, exist_ok=True)
    jf_file = data_dir / "operations.json"
    if jf_file.exists():
        jf_file.unlink()

    # ---- 装配选型 ----
    jr = ps.MagicFlowStore._new_journal(data_dir, kv=None)
    _ok(isinstance(jr, ps.PgOperationJournal), f"_new_journal → PgOperationJournal（实际 {type(jr).__name__}）")

    task = "pgjr" + uuid.uuid4().hex[:10]

    # ---- 1) add → finalize ----
    it = ps.OperationItem(hash="pgjrhash1", title="pgjr条目", reason="测试", bonus_per_hour=1.5,
                          size_gb=2.0, seeders=3, source="test", tags="")
    rec = jr.add(task_id=task, kind="deletion", items=[it])
    _ok(rec.state == "submitting", "add → submitting")
    g = jr.get(rec.operation_id)
    _ok(g is not None and g.kind == "deletion" and len(g.items) == 1, "get 读回（含 items）")
    _ok(g.items[0].title == "pgjr条目" and g.items[0].bonus_per_hour == 1.5,
        "items 字段回读不丢（中文/浮点）")
    ok = jr.finalize(rec.operation_id, "completed", items=[it], duration=12.5)
    _ok(ok is True, "finalize 成功")
    g2 = jr.get(rec.operation_id)
    _ok(g2.state == "completed" and g2.duration == 12.5 and g2.resolved_at is not None,
        "finalize 回写 state/duration/resolved_at")

    # ---- 2) record 即时完成 ----
    rec2 = jr.record(task_id=task, kind="selection", items=[it], duration=3.0)
    _ok(rec2.state == "completed", "record → 一次落库 completed")
    _ok(jr.finalize("pgjr.nonexistent", "completed") is False, "finalize 未知 id → False")

    # ---- 3) 读 API ----
    jr.record(task_id=task, kind="protection", items=[])
    jr.record(task_id=task, kind="reseed", items=[])
    bt = jr.list_by_task(task, limit=10)
    _ok(len(bt) == 4, f"list_by_task 全量 4 条（实际 {len(bt)}）")
    _ok(all(r.task_id == task for r in bt), "list_by_task 只含本任务")
    _ok(bt[0].created_at >= bt[-1].created_at, "list_by_task 时间降序")
    bdk = jr.list_by_task(task, kind="deletion", limit=10)
    _ok(len(bdk) == 1 and bdk[0].kind == "deletion", "list_by_task kind 过滤")
    lr = jr.list_recent(limit=3)
    _ok(len(lr) == 3 and lr[0].created_at >= lr[-1].created_at, "list_recent 限量+降序")
    lrm = jr.list_recent(limit=10, kind="deletion,protection")
    _ok({r.kind for r in lrm} == {"deletion", "protection"}, "list_recent 逗号多 kind")

    # ---- 4) update_state / delete ----
    rec3 = jr.add(task_id=task, kind="selection", items=[])
    jr.update_state(rec3.operation_id, "accepted")
    _ok(jr.get(rec3.operation_id).state == "accepted", "update_state → accepted")
    jr.update_state(rec3.operation_id, "failed", error_message="boom")
    g3 = jr.get(rec3.operation_id)
    _ok(g3.state == "failed" and g3.error_message == "boom" and g3.resolved_at is not None,
        "update_state failed + error_message + resolved_at")
    n = jr.delete_task(task + "_none")
    _ok(n == 0, "delete_task 不存在的任务 → 0")
    n2 = jr.delete_task(task)
    _ok(n2 == 5, f"delete_task 删 5 条（实际 {n2}）")
    _ok(jr.list_by_task(task, limit=10) == [], "delete_task 后读空")

    # ---- 5) keep 裁剪（PG 侧） ----
    jr.set_keep(2)
    for i in range(4):
        jr.record(task_id=task, kind="selection", items=[],
                  duration=float(i))
    btk = jr.list_by_task(task, limit=10)
    _ok(len(btk) <= 2, f"keep=2 裁剪后 ≤2 条（实际 {len(btk)}）")
    jr.set_keep(0)

    # ---- 6) MagicFlowStore 装配/rebind ----
    # （构造真 MagicFlowStore 会起 flusher 线程；只验证 rebind_journal 分支语义）
    class _FakeOld:
        kv = None
    store = object.__new__(ps.MagicFlowStore)
    store.journal = jr
    _ok(store.rebind_journal() is False, "rebind_journal 幂等（已是 PG 版 → False）")
    store.journal = _FakeOld()  # 模拟旧版
    store.data_dir = data_dir
    _ok(store.rebind_journal() is True, "rebind_journal 旧版 → 换 PG 版")
    _ok(isinstance(store.journal, ps.PgOperationJournal), "换绑后类型正确")

    # ---- 7) 离线降级 ----
    mfdb.unbind_database()
    off = ps.PgOperationJournal.__new__(ps.PgOperationJournal)
    ps.OperationJournal.__init__(off, data_dir, kv=None)
    rec4 = off.add(task_id=task, kind="deletion", items=[])
    _ok(rec4.state == "submitting" and jf_file.exists(), "离线 add 回退父类 JSON 路径")
    off.finalize(rec4.operation_id, "completed", duration=1.0)
    _ok(off.get(rec4.operation_id).state == "completed", "离线 finalize 回退 JSON")

    # ---- 清场 ----
    mfdb.bind_database(handle)
    sess = mfdb.db_session()
    with sess:
        sess.query(mfdb.JournalRow).filter(mfdb.JournalRow.task_id == task).delete(
            synchronize_session=False)
        sess.commit()
    if jf_file.exists():
        jf_file.unlink()
    import shutil
    shutil.rmtree(data_dir, ignore_errors=True)

    print(f"\n== 结果：{_OK} ok / {_FAIL} fail ==")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
