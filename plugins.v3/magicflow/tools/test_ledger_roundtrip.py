#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 真 5 表往返测试（12.0.0 清算专用；**只能容器内跑**）

为什么单开一个：本轮的教训是「子代理用 stub 内存账本做的单测，掩盖了真 5 表
『任务名→task_id→state』推导链的 bug」。这个测试**不桩任何东西**——直接拿
线上插件实例的真 ``LedgerBackend``（真 PG 连接、真 schema），走一趟
「写 → 换 fresh backend 回读（绕开内存缓存）→ 删 → 行数回到基线」，
证明新旧字段（含 12.0.0 新增真列 ``asset_recheck``）**真的落库、真的读得回来**。

用法（容器内）：
    docker exec -w /tmp/mf1200 moviepilot-v3 /opt/venv/bin/python3 \
        tools/test_ledger_roundtrip.py

安全：只写一条 ``rt*`` 前缀的测试行（seed + resource），跑完立即删除并比对行数；
不碰任何真实 hash。任一步失败 → 退出码 1（并在 finally 里尽力清场）。
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
    """拿真插件实例（拿不到就退化为「真库句柄 shim」）。

    容器内独立进程拉不起 ``PluginManager()``（Runtime 工厂需启动组合根装配），
    所以直接用 MP 官方的插件库句柄注册表 ``app.db.plugin.registry.get_database``
    —— 同一个 engine、同一个 schema（``search_path`` 已限定），仍是「真 5 表」。
    """
    from app.db.plugin.registry import get_database

    try:  # 优先：真插件实例（插件包模块与线上一致，最保真）
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
            print(f"  [plugin:{level}] {msg}")

    import importlib

    pkg = importlib.import_module("app.plugins.magicflow")
    return _Shim(), pkg


def main() -> int:
    p, pkg = _load_plugin()
    import importlib

    ledger = importlib.import_module(pkg.__name__ + ".ledger")
    mfdb = importlib.import_module(pkg.__name__ + ".db")
    from sqlalchemy import delete, func, select

    be = ledger.get_backend(p)
    if be is None or not be.ensure_schema():
        raise SystemExit("✗ 账本后端/建表失败")

    def counts() -> dict:
        sess = be._session()
        try:
            out = {}
            for model in mfdb.ALL_MODELS:
                out[model.__tablename__] = int(
                    sess.execute(select(func.count()).select_from(model)).scalar() or 0
                )
            return out
        finally:
            sess.close()

    print("== 真 5 表往返测试（12.0.0）==")
    base = counts()
    print("  基线行数:", base)

    H = "rt" + uuid.uuid4().hex * 2          # 66 位里取 40 也行，这里给足
    H = H[:40]
    FP = "rtfp" + uuid.uuid4().hex[:20]
    NOW = time.time()
    seed_patch = {
        "site": "roundtrip.test",
        "state": "静默",
        "sub": "普通",
        "task": "__roundtrip__",
        "fp": FP,
        "size_gb": 1.0,
        "asset_recheck": "keep",
        "asset_recheck_at": NOW,
    }

    rid = ""
    try:
        # ---- 1) 写（走真 store API，不桩）----
        st = ledger.SeedLedgerStore(be)
        st.put(H, seed_patch)
        # ---- 2) 同一进程回读（缓存层）----
        rec_cached = st.get(H) or {}
        _ok(rec_cached.get("site") == "roundtrip.test", "put → get：site 落地")
        _ok(rec_cached.get("state") == "静默", "put → get：state 落地")
        _ok(rec_cached.get("asset_recheck") == "keep", "put → get：asset_recheck 落地")

        # ---- 3) fresh backend 回读（绕开内存缓存 → 真打库）----
        be2 = ledger.LedgerBackend(p)
        be2.ensure_schema()
        st2 = ledger.SeedLedgerStore(be2)
        rec_db = st2.get(H) or {}
        _ok(rec_db.get("site") == "roundtrip.test", "fresh backend 回读：site（真 mf_seed+join）")
        _ok(str(rec_db.get("state") or "") == "静默", "fresh backend 回读：state")
        _ok(str(rec_db.get("sub") or "") == "普通", "fresh backend 回读：sub（mf_resource.identity）")
        _ok(
            str(rec_db.get("asset_recheck") or "") == "keep",
            "fresh backend 回读：asset_recheck（★ 12.0.0 新真列）",
        )
        _ok(
            abs(float(rec_db.get("asset_recheck_at") or 0) - NOW) < 2.0,
            "fresh backend 回读：asset_recheck_at（浮点真列）",
        )

        # ---- 4) 资源表直查：确认真的是列不是内存影子 ----
        rid = ledger.norm_res_id(FP).lower()
        sess = be._session()
        try:
            row = sess.execute(
                select(mfdb.ResourceRow).where(mfdb.ResourceRow.resource_id == rid)
            ).scalars().first()
        finally:
            sess.close()
        _ok(row is not None, f"mf_resource 有行（resource_id={rid}）")
        if row is not None:
            _ok(str(row.asset_recheck or "") == "keep", "直查 mf_resource.asset_recheck == keep")
            _ok(str(row.identity or "") == "普通", "直查 mf_resource.identity == 普通")
            _ok(abs(float(row.size_gb or 0) - 1.0) < 1e-9, "直查 mf_resource.size_gb == 1.0")

        # ---- 5) 计数增量符合预期（seed +1、resource +1）----
        mid = counts()
        _ok(mid["mf_seed"] == base["mf_seed"] + 1, f"mf_seed 行数 +1（{base['mf_seed']}→{mid['mf_seed']}）")
        _ok(
            mid["mf_resource"] == base["mf_resource"] + 1,
            f"mf_resource 行数 +1（{base['mf_resource']}→{mid['mf_resource']}）",
        )

        # ---- 6) 删（走 store API）----
        st.drop(H)
        if rid:
            sess = be._session()
            try:
                sess.execute(
                    delete(mfdb.ResourceRow).where(mfdb.ResourceRow.resource_id == rid)
                )
                sess.commit()
            finally:
                sess.close()
        rid = ""   # 已清
    finally:
        # 清场（尽力而为，失败也要把行数报出来）
        try:
            if rid:
                sess = be._session()
                try:
                    sess.execute(
                        delete(mfdb.ResourceRow).where(mfdb.ResourceRow.resource_id == rid)
                    )
                    sess.commit()
                finally:
                    sess.close()
        except Exception as err:  # noqa: BLE001
            print(f"  ⚠️ 资源清场失败: {err}")
        # 站点行：_site_id(create=True) 会顺手建一行测试站 → 一并发删
        try:
            sess = be._session()
            try:
                sess.execute(
                    delete(mfdb.SiteRow).where(
                        (mfdb.SiteRow.name == "roundtrip.test")
                        | (mfdb.SiteRow.domain == "roundtrip.test")
                    )
                )
                sess.commit()
            finally:
                sess.close()
        except Exception as err:  # noqa: BLE001
            print(f"  ⚠️ 站点清场失败: {err}")

    # ---- 7) 回读：行数回到基线 ----
    be3 = ledger.LedgerBackend(p)
    be3.ensure_schema()
    st3 = ledger.SeedLedgerStore(be3)
    _ok(not st3.get(H), "删除后 fresh backend 回读：种子已消失")
    after = counts()
    for t in sorted(set(base) | set(after)):
        if base.get(t) != after.get(t):
            _ok(False, f"{t} 行数未回到基线：{base.get(t)} → {after.get(t)}")
        else:
            _ok(True, f"{t} 行数回到基线（{after.get(t)}）")

    print(f"\n{'=' * 60}")
    if _FAIL == 0:
        print(f"✅ PASS —— 共 {_OK} 项全过（真 5 表往返，无桩）")
        return 0
    print(f"❌ FAIL —— {_FAIL} 项失败 / {_OK} 项通过")
    return 1


if __name__ == "__main__":
    sys.exit(main())
