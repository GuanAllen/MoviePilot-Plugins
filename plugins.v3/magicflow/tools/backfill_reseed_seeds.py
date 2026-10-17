#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_reseed_seeds.py —— 19.0.1 存量回填：drift qb_only 收敛。

背景：辅种线（reseed）挂种只写 mf_reseed 台账、从不登记 mf_seed 种子账本，
魔流化扫描又只收「无魔流标签」的种 → 辅种挂上即带完整标签、永远无人登记。
实测累积 358 颗「qB 带魔流标签但账本无行」（drift qb_only 红名）。

增量侧已修（features/reseed.py 挂种成功即 put）；本脚本收**存量**：
  目标 = qB 在线 ∧ 带魔流标签（身份或职务）∧ mf_seed 无行
  动作 = 按标签解析 site/sub/职务，put 登记进 mf_seed（幂等）

用法（容器内）：
  python3 /tmp/backfill_reseed_seeds.py            # 干跑（只报数）
  python3 /tmp/backfill_reseed_seeds.py --apply    # 真写
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

_APPLY = "--apply" in sys.argv


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


def _qb_client() -> tuple:
    """从 MoviePilot systemconfig 拿 qbittorrent 凭据 → (host, cookie)。"""
    from sqlalchemy import text

    p, pkg = _load_plugin.__globals__.get("_plugin_ctx") or (None, None)
    handle = _load_plugin.__globals__.get("_db_handle")
    sess = handle.session()
    try:
        rows = sess.execute(text(
            "SELECT value FROM public.systemconfig WHERE key = 'Downloaders'"
        )).scalars().all()
    finally:
        sess.close()
    for raw in rows:
        try:
            arr = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:  # noqa: BLE001
            continue
        for it in arr or []:
            if str(it.get("type") or "").lower() != "qbittorrent":
                continue
            host = str(it.get("host") or "").rstrip("/")
            user = str(it.get("username") or "")
            pwd = str(it.get("password") or "")
            if not host:
                continue
            # 登录拿 cookie
            body = urllib.parse.urlencode({"username": user, "password": pwd}).encode()
            req = urllib.request.Request(host + "/api/v2/auth/login", data=body, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                cookie = resp.headers.get("Set-Cookie", "")
            if "SID" not in cookie:
                continue
            return host, cookie.split(";")[0]
    raise SystemExit("✗ 未找到可用 qbittorrent 凭据（systemconfig Downloaders）")


def main() -> int:
    p, pkg = _load_plugin()
    import importlib

    ledger_mod = importlib.import_module(pkg.__name__ + ".ledger")
    tags_mod = importlib.import_module(pkg.__name__ + ".tags")
    mfdb = importlib.import_module(pkg.__name__ + ".db")
    from sqlalchemy import select

    _load_plugin.__globals__["_plugin_ctx"] = (p, pkg)
    _load_plugin.__globals__["_db_handle"] = p.get_database()

    be = ledger_mod.get_backend(p)
    if be is None or not be.ensure_schema():
        raise SystemExit("✗ 账本后端/建表失败")
    st = ledger_mod.SeedLedgerStore(be, log=None)

    # 1) 账本现有 hash 集
    sess = be._session()
    try:
        seed_hashes = {str(r.hash or "").lower()
                       for r in sess.execute(select(mfdb.SeedRow)).scalars()}
    finally:
        sess.close()

    # 2) qB 全量
    host, cookie = _qb_client()
    req = urllib.request.Request(host + "/api/v2/torrents/info")
    req.add_header("Cookie", cookie)
    with urllib.request.urlopen(req, timeout=30) as resp:
        torrents = json.loads(resp.read().decode())

    # 3) 目标：带魔流标签 ∧ 账本无行
    identity_of = tags_mod.identity_of
    duty_of = tags_mod.duty_of
    targets = []
    for t in torrents or []:
        h = str(t.get("hash") or "").lower()
        if not h or h in seed_hashes:
            continue
        tags = [str(x).strip() for x in (t.get("tags") or "").split(",") if str(x).strip()]
        site_i, sub = identity_of(tags)
        site_d, state = duty_of(tags)
        if not (site_i or site_d):
            continue  # 无魔流标签（MOVIEPILOT/外部种）——不归本脚本管
        targets.append({
            "hash": h,
            "site": site_i or site_d,
            "sub": sub,
            "state": state or tags_mod.STATE_SILENT,
            "title": str(t.get("name") or "")[:200],
            "size_gb": round(float(t.get("size") or 0) / 1024 ** 3, 3),
            "tags": tags,
        })

    print(f"qB 总数 {len(torrents or [])}｜账本行 {len(seed_hashes)}｜待回填 {len(targets)}")
    if not targets:
        print("无需回填。")
        return 0

    by_state: dict = {}
    for it in targets:
        by_state[it["state"]] = by_state.get(it["state"], 0) + 1
    print(f"按职务分布：{by_state}")
    for it in targets[:10]:
        print(f"  样例 {it['hash'][:12]} site={it['site']} sub={it['sub'] or '-'} "
              f"state={it['state']} {it['size_gb']}GB")

    if not _APPLY:
        print("\n（干跑：加 --apply 真写）")
        return 0

    n = 0
    for it in targets:
        try:
            st.put(it["hash"], {
                "site": it["site"],
                "state": it["state"],
                "sub": it["sub"] or "",
                "title": it["title"],
                "size_gb": it["size_gb"] or None,
                "reason": "19.0.1 回填:辅种账本缺口收敛",
            })
            n += 1
        except Exception as err:  # noqa: BLE001
            print(f"  ✗ {it['hash'][:12]}: {err}")
    print(f"\n已登记 {n}/{len(targets)} 行。")

    # 复核
    sess = be._session()
    try:
        after = {str(r.hash or "").lower()
                 for r in sess.execute(select(mfdb.SeedRow)).scalars()}
    finally:
        sess.close()
    miss = [it["hash"] for it in targets if it["hash"] not in after]
    print(f"复核：登记后账本 {len(after)} 行，仍未命中 {len(miss)} 颗"
          + (f"：{[m[:12] for m in miss[:5]]}" if miss else ""))
    return 0 if not miss else 1


if __name__ == "__main__":
    sys.exit(main())
