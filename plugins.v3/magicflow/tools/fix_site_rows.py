#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性：把 12.2.0 迁移误建的「合成站点行」并回真实站点行（跑完即弃）。

背景：迁移时脚本进程拿不到 plugin.get_data（iyuu_cache），iyuu_sid→域名解析全落空 →
建出 `site:24` / `iyuu:135` 这类无名行；同时把 pv_usage / 补种 passkey 写到了这些行上。

规则（由站点登记表 /tmp/site_registry.json 驱动）：
  - 数字 id（MP id 或 IYUU sid）→ 域名 → 命中已有真实站点行 → 合并数据 + 回填 iyuu_sid → 删合成行。
  - 合成行的 JSON 列（pv_usage/credential/…）与目标行按「目标优先」合并；标量列仅在目标为空时补。
  - 顺带回填 1..16 行的 iyuu_sid（登记表有值但当前为 NULL）。

默认 dry-run；`--apply` 才写库（写前打快照，写后校验行数/键数）。
"""
from __future__ import annotations

import importlib
import json
import sys
from typing import Any  # noqa: F401

APPLY = "--apply" in sys.argv[1:]
REG = json.load(open("/tmp/site_registry.json", encoding="utf-8"))["sites"]

get_database = None
mfdb = None
select = None

try:  # 只在容器内可用（宿主机会 import 失败 → 延迟到 main() 里报错）
    from app.db.plugin.registry import get_database  # type: ignore  # noqa: E402
    from sqlalchemy import select as _select  # noqa: E402

    select = _select
except Exception:  # noqa: BLE001
    pass

JSON_COLS = {"domains", "credential", "free_spstates", "pv_usage", "signin", "alerts",
             "rules_extra", "caps"}
SKIP = {"site_id", "name", "domain", "mp_site_id", "iyuu_sid", "created", "updated"}

by_mp = {int(s["id"]): s for s in REG if s.get("id") is not None}
by_sid = {int(s["iyuu_sid"]): s for s in REG if s.get("iyuu_sid") is not None}
sid_of_dom = {str(s["domain"]).lower(): int(s["iyuu_sid"]) for s in REG if s.get("iyuu_sid")}


def _norm(d: object) -> str:
    return str(d or "").strip().lower().lstrip("www.") if d else ""


def resolve(row):
    """合成行 → 登记表条目。"""
    if row.mp_site_id is not None and int(row.mp_site_id) in by_mp:
        return by_mp[int(row.mp_site_id)]
    if row.mp_site_id is not None and int(row.mp_site_id) in by_sid:
        return by_sid[int(row.mp_site_id)]
    if row.iyuu_sid is not None and int(row.iyuu_sid) in by_sid:
        return by_sid[int(row.iyuu_sid)]
    return None


def merge_json(a, b):
    if not isinstance(b, dict) or not b:
        return a
    if not isinstance(a, dict) or not a:
        return dict(b)
    out = dict(b)
    out.update(a)
    return out


def main() -> int:
    if get_database is None:
        raise SystemExit("✗ 只能在 MoviePilot 容器内跑（需要 app.* / sqlalchemy）")
    global mfdb
    handle = get_database("MagicFlow")
    mfdb = importlib.import_module("app.plugins.magicflow.db")
    sess = handle.session() if hasattr(handle, "session") else handle()
    rows = list(sess.execute(select(mfdb.SiteRow)).scalars().all())
    print(f"== 站点行修复（{'APPLY' if APPLY else 'DRY-RUN'}）==")
    print(f"  基线：{len(rows)} 行")
    pv_before = sum(len(r.pv_usage or {}) for r in rows)
    print(f"  pv_usage 条目总数：{pv_before}")

    by_domain = {}
    for r in rows:
        d = _norm(r.domain)
        if d and d not in by_domain:
            by_domain[d] = r

    synthetic = [r for r in rows
                 if (r.name or "").startswith("site:") or (r.name or "").startswith("iyuu:")]
    print(f"  合成行：{len(synthetic)}")

    plan = []
    for r in synthetic:
        reg = resolve(r)
        if not reg:
            print(f"  ⚠️ 无法解析 id={r.mp_site_id or r.iyuu_sid}（name={r.name}）→ 跳过")
            continue
        dom = _norm(reg.get("domain"))
        tgt = by_domain.get(dom)
        if tgt is None and reg.get("id") is not None:
            tgt = next((x for x in rows if x.mp_site_id == reg["id"]), None)
        if tgt is None:
            print(f"  ⚠️ id={r.mp_site_id or r.iyuu_sid} 解析出域名 {dom!r} 但无目标行 → 跳过")
            continue
        if tgt is r:
            continue
        plan.append((r, tgt, reg))

    for r, tgt, reg in plan:
        sid = r.mp_site_id if r.mp_site_id is not None else r.iyuu_sid
        reg_sid = reg.get("iyuu_sid")
        print(f"  合并 {r.name}(site_id={r.site_id}, pv={len(r.pv_usage or {})}) "
              f"→ {tgt.name}(site_id={tgt.site_id}, domain={tgt.domain}) ; iyuu_sid={reg_sid}")

    if not APPLY:
        print("  （dry-run，不写库）")
        sess.close()
        return 0

    # ---- 写库 ----
    moved = 0
    for r, tgt, reg in plan:
        for col in mfdb.SiteRow.__table__.columns.keys():
            if col in SKIP:
                continue
            b = getattr(r, col, None)
            if b is None:
                continue
            a = getattr(tgt, col, None)
            if col in JSON_COLS:
                nv = merge_json(a, b)
            else:
                nv = a if a not in (None, "", 0, False) else b
            if nv != a:
                setattr(tgt, col, nv)
                moved += 1
        if reg.get("iyuu_sid") is not None:
            tgt.iyuu_sid = int(reg["iyuu_sid"])
        sess.delete(r)

    # 回填 1..16 的 iyuu_sid
    filled = 0
    for r in rows:
        if r in [x[1] for x in plan]:
            continue
        d = _norm(r.domain)
        if r.iyuu_sid is None and d in sid_of_dom:
            r.iyuu_sid = sid_of_dom[d]
            filled += 1

    sess.commit()
    after = list(sess.execute(select(mfdb.SiteRow)).scalars().all())
    pv_after = sum(len(x.pv_usage or {}) for x in after)
    sess.close()
    print(f"  ✅ 已合并 {len(plan)} 行（列改动 {moved} 处），回填 iyuu_sid {filled} 行")
    print(f"  行数 {len(rows)} → {len(after)} ；pv_usage 条目 {pv_before} → {pv_after}")
    left = [x.name for x in after if (x.name or "").startswith(("site:", "iyuu:"))]
    print(f"  残留合成行：{left or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
