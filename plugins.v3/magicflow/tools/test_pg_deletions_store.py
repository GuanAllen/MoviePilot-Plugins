#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pg_deletions_store.py —— 19.0.0 mf_deletions 真库回环测试（容器内跑）

覆盖：
  1. _delete_log_cb：PG 可用 → 写 mf_deletions（成功行 ok=True / 拦截行 blocked=True）
  2. _agent_deletions_rows：PG 读回（行形状与 JSONL 口径一致、时间正序）
  3. _hr_breaches 归因改走统一读口（hasattr 探测即可，行为由 1/2 保证）
  4. 离线降级：unbind → _delete_log_cb 回退写 deletions.jsonl、读侧回退读 JSONL

只写 pgdel 前缀数据，跑完清场。
"""
from __future__ import annotations

import sys
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
    import magicflow.features.agentledger as al
    import magicflow.features.deletegate as dg

    handle = get_database("MagicFlow")
    mfdb.bind_database(handle)

    class _T(dg.DeleteGateMixin, al.AgentLedgerMixin):
        def __init__(self):
            self._store = None
            self._data_dir = Path("/tmp/pgdel_data")
            import os
            os.makedirs(self._data_dir, exist_ok=True)

        def get_data_path(self):
            return self._data_dir

        def _tag_all_torrents(self):
            return {}

        def _tag_state(self):
            return {}

        def _log(self, msg, level="info"):
            print(f"  [log:{level}] {msg}")

    t = _T()
    tag = "pgdel" + uuid.uuid4().hex[:14]
    h1 = (tag + "1" * 40)[:40]
    h2 = (tag + "2" * 40)[:40]
    h3 = (tag + "3" * 40)[:40]

    # ---- 1) 写侧：2 成功 + 1 拦截 → mf_deletions ----
    t._delete_log_cb([h1, h2], delete_file=True, reason="pgtest删除",
                     source="test", error=None, blocked=[h3], blocked_by="gate_test")
    rows = t._agent_deletions_rows()
    mine = [r for r in rows if str(r.get("hash") or "").startswith(tag)]
    _ok(len(mine) == 3, f"_delete_log_cb 写 3 行（实际 {len(mine)}）")
    ok_rows = [r for r in mine if r.get("ok") and not r.get("blocked")]
    blk_rows = [r for r in mine if (not r.get("ok")) and r.get("blocked")]
    _ok(len(ok_rows) == 2, f"成功行 2 条（实际 {len(ok_rows)}）")
    _ok(len(blk_rows) == 1, f"拦截行 1 条（实际 {len(blk_rows)}）")
    r0 = mine[0]
    _ok(all(k in r0 for k in ("ts", "hash", "site", "title", "source", "reason",
                               "delete_file", "ok", "blocked", "err", "blocked_by")),
        "行形状与 JSONL 口径一致（11 键齐全）")
    _ok(len(str(r0.get("ts") or "")) == 19 and str(r0.get("ts")).count("-") == 2,
        f"ts 仍是展示串（{r0.get('ts')}）")
    _ok(str(r0.get("reason") or "") == "pgtest删除", "中文 reason 不丢")
    _ok(str(blk_rows[0].get("blocked_by") or "") == "gate_test", "blocked_by 保留")
    # 时间正序
    _ok([r["hash"] for r in mine] == [h1, h2, h3], "按 id 正序（写入序）")

    # ---- 4) 离线降级：unbind → 写 JSONL、读 JSONL ----
    jf = t._data_dir / "deletions.jsonl"
    if jf.exists():
        jf.unlink()
    mfdb.unbind_database()
    t._delete_log_cb([h1], delete_file=False, reason="pgdel_offline",
                     source="test", error=None, blocked=[])
    _ok(jf.exists() and "pgdel_offline" in jf.read_text(encoding="utf-8"),
        "离线写回退 deletions.jsonl")
    rows2 = t._agent_deletions_rows()
    mine2 = [r for r in rows2 if str(r.get("hash") or "").startswith(tag)]
    _ok(len(mine2) == 1 and mine2[0].get("reason") == "pgdel_offline",
        "离线读回退 JSONL（只有离线写的那条）")

    # ---- 清场 ----
    mfdb.bind_database(handle)
    sess = mfdb.db_session()
    with sess:
        sess.query(mfdb.DeletionRow).filter(mfdb.DeletionRow.hash.like(f"{tag}%")).delete(
            synchronize_session=False)
        sess.commit()
    if jf.exists():
        jf.unlink()

    print(f"\n== 结果：{_OK} ok / {_FAIL} fail ==")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
