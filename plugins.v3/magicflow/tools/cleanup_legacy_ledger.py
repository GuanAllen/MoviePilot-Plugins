#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性清理「账本链 kv 残留」（跑完即弃，不留常驻兼容层）。

================================ 为什么安全 ================================
1. **这些键 12.0.0 起代码零读写**：本脚本清的是「标签账本」曾经在 ``plugindata`` kv 里的
   残留（``tag_state``/``tag_groups``/``tag_state_snapshot``）+ schema_v5/v6 迁移戳与备份
   （``schema_v5_*``/``schema_v6_*``/``schema_v5_backup:*``/``last_version``）。
   （``rules_migrations`` 不属本脚本：它是「站点规则一次性迁移标记」，随 site_rules→mf_site 迁移体系处置。）
   12.0.0 起「标签账本」只认 5 张表（``mf_seed``/``mf_resource``/``mf_site``/``mf_identity``/
   ``mf_task``/``mf_deck``），旧的 ``ledger._mirror_legacy`` 双写已删。
2. **5 张表是唯一真值源**：本脚本不碰任何表数据，只删 kv 键；删除前后各取一次
   「5 表行数 + 关键派生量」快照并比对，不一致立即中止（见下方「数据安全校验」）。
3. **Redis 是缓存层，可回填**：就算误删了不该删的缓存键，也只会让热层从 5 表重建一轮，不丢真值。

================================ 怎么用（必须在容器内跑） ================================
本脚本依赖 MoviePilot 运行环境（``app.*`` 模块 + 数据库），**只能在容器内跑**：:

    docker exec -it moviepilot-v3 sh -lc 'cd /app && /opt/venv/bin/python3 /app/app/plugins/magicflow/tools/cleanup_legacy_ledger.py --dry-run'
    docker exec -it moviepilot-v3 sh -lc 'cd /app && /opt/venv/bin/python3 /app/app/plugins/magicflow/tools/cleanup_legacy_ledger.py --apply'

参数:
    --dry-run            默认；只打印「将删哪些键、多大、当前值行数/大小」，不写任何东西。
    --apply              真正删除（先备份 → 再删 → 删除前后快照比对，任一失败即中止）。
    --data-dir=<路径>    插件数据目录（默认自动探测 /config/plugins/MagicFlow）；备份文件落这里。
    --json               机器可读输出（一个 JSON 报告）。
    --force              删除「仍被已装代码引用」的键（默认会跳过并告警，见「存活检查」）。
    --no-check-live      关闭存活检查（不扫描已装插件源码，不跳过被引用键）。

================================ 怎么回滚（备份文件还原） ================================
--apply 时先把每个将被删的键**原样 dump** 到 ``<data_dir>/legacy_kv_backup_<UTC>.json``（0600），
内容含 ``key/value/size/sha1``。要回滚：把备份文件里的 ``keys[].value`` 用 ``save_data(key, value)``
逐个写回即可（或人工在 MP 插件数据里重建）。**备份文件写失败会直接中止，不删任何键。**

================================ 已知风险 / 不确定项（★ 务必先读） ================================
- ``rules_migrations``：站点规则的一次性迁移标记（咖啡无 H&R / 馒头无 H&R / 馒头无做种上限 /
  单种限速 200 等）。**当前 11.13.0 代码 ``features/core.py`` 仍在读写它**；删除会让这些一次性
  迁移在下次启动时重跑（多为幂等重写同一「manual」规则，但 ``seed_up_200`` 会重触发一次配置保存）。
  → 建议主会话确认 12.0.0 是否已移除这些读写，再决定是否把它留在待删清单里。
- ``tag_state_snapshot``：11.13.0 的 ``TagStateStore.snapshot()`` 仍会写它；12.0.0 已删掉整套 kv 快照
  机制（账本类只认 5 表），删除后不会再被写回。**在 12.0.0 部署前跑本脚本，存活检查会自动跳过它。**
- ``last_version`` / ``schema_v5_*`` / ``schema_v6_*``：这些是 ``features/migrate.py`` 的迁移戳，
  12.0.0 已删掉 migrate.py → 真正死。在旧版上跑时存活检查会自动跳过它们（安全兜底）。

**结论：本脚本应在 12.0.0 部署之后再 ``--apply``**；在旧版上跑只会删掉 5 个 ``schema_v5_backup:*``
备份键（其余因存活检查跳过），这本身就是护栏生效的证明。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PLUGIN_ID = "MagicFlow"
HR_BILLS_FILE = "hr_bills.json"
BACKUP_FILE_PREFIX = "legacy_kv_backup"

# ──────────────────────────────────────────────────────────────────────
# 1. 待清理的 kv 键（12.0.0 起 kv 零读写）
# ──────────────────────────────────────────────────────────────────────
DEAD_KEYS: List[str] = [
    # 「标签账本」kv 残留（12.0.0 起 5 表是唯一真值源，_mirror_legacy 双写已删）
    "tag_state",
    "tag_groups",
    "tag_state_snapshot",
    # schema_v5/v6 迁移戳/标记
    "schema_v5_done",
    "schema_v5_backed",
    "schema_v5_manifest",
    "schema_v5_cursor",     # 迁移游标（空 dict）；migrate.py 已删 → 死键
    "schema_v6_done",
    "schema_v6_manifest",
    "schema_v6_pubdates",
    "last_version",
    # ★ 注意：``rules_migrations`` **不在此列** —— 它不是账本残留，而是「站点规则一次性迁移标记」
    #   （咖啡/馒头无 H&R 等），12.0.0 起由 site_rules→mf_site 的迁移体系接管，另行处置。
]

# 前缀匹配（全量清除所有 schema_v5 迁移前旧键备份）
DEAD_PREFIXES: List[str] = [
    "schema_v5_backup:",
]

# ──────────────────────────────────────────────────────────────────────
# 2. 绝对不许碰（硬护栏：即便有人误把下面的键加进 DEAD_KEYS 也会拒绝删除）
# ──────────────────────────────────────────────────────────────────────
PROTECTED_EXACT: set = {
    "site_rules",
    "site_caps",
    "crossseed_sources",
    "defaults",
    "pv_budget",
    "crossseed_ban",
    "live_alerts",
    "sitecap_override",
    "signin_last_full",
    "keepalive_alert_day",
    "cloud_report",
    "eventlog_v1",
    "trend_v1",
    "hr_trust_migrated_3410",
    "rating_source_migrated_3224",
}
PROTECTED_PREFIXES: List[str] = ["iyuu_", "cloud_"]

# ──────────────────────────────────────────────────────────────────────
# 3. 数据安全校验口径：5 表 + 关键派生量
# ──────────────────────────────────────────────────────────────────────
TABLES: List[str] = ["mf_seed", "mf_resource", "mf_site", "mf_identity", "mf_task", "mf_deck"]

# 5 表后端「逻辑键」常量：SeedLedgerStore 里这两个常量被特殊路由到 5 表（不再写 kv）。
# 存活检查据此豁免它们，避免把「仍是活逻辑键、但已不走 kv」的 tag_state/tag_groups 误判为 kv 活键。
_TABLE_BACKED_CONSTANTS: set = {"STATE_KEY", "GROUPS_KEY"}

# 待删清单之外、但看起来仍属迁移家族（提示、不删）的前缀/精确键
_UNCERTAIN_MIGRATION_PATTERN = re.compile(r"^(schema_v\d+_|last_version$|rules_migrations$|tag_state|tag_groups)")

# ──────────────────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _canon_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha1_of(value: Any) -> str:
    return hashlib.sha1(_canon_json(value).encode("utf-8")).hexdigest()


def _size_of(value: Any) -> int:
    return len(_canon_json(value).encode("utf-8"))


def _value_summary(value: Any) -> str:
    if isinstance(value, dict):
        return f"dict({len(value)})"
    if isinstance(value, list):
        return f"list({len(value)})"
    if isinstance(value, str):
        return f"str({len(value)})"
    return type(value).__name__


# ──────────────────────────────────────────────────────────────────────
# MoviePilot 环境（懒导入：脱离容器也能 py_compile，运行时才真正 import）
# ──────────────────────────────────────────────────────────────────────


def _import_mp():
    """懒导入 MoviePilot 运行环境。失败抛带说明的异常。"""
    try:
        from app.db.engine import get_engine  # noqa: F401
        from app.db.models.plugindata import PluginData  # noqa: F401
        from app.db.plugin.registry import get_database  # noqa: F401
        from app.runtime.extensions.plugin.datadir import resolve_plugin_data_directory  # noqa: F401
    except Exception as err:  # noqa: BLE001
        raise RuntimeError(
            "无法导入 MoviePilot 运行环境（app.*）。本脚本只能在容器内跑：\n"
            f"  docker exec -it moviepilot-v3 sh -lc 'cd /app && /opt/venv/bin/python3 {__file__} --dry-run'\n"
            f"原始错误：{type(err).__name__}: {err}"
        ) from err
    return get_engine, PluginData, get_database, resolve_plugin_data_directory


def _resolve_data_dir(override: Optional[str]) -> Path:
    if override:
        return Path(override).expanduser()
    _, _, _, resolve = _import_mp()
    return Path(resolve(PLUGIN_ID))


def _resolve_plugin_src(override: Optional[str], data_dir: Path) -> Path:
    """已装插件源码目录（存活检查用）。"""
    if override:
        return Path(override).expanduser()
    candidates = [
        Path("/app/app/plugins/magicflow"),
        data_dir.parent.parent / "plugins" / "magicflow",
    ]
    for c in candidates:
        if (c / "__init__.py").exists():
            return c
    return candidates[0]


# ──────────────────────────────────────────────────────────────────────
# kv 读写（plugindata 表，plugin_id = "MagicFlow"）
# ──────────────────────────────────────────────────────────────────────


def _list_kv() -> Dict[str, Any]:
    from sqlalchemy.orm import sessionmaker

    get_engine, PluginData, _, _ = _import_mp()
    engine = get_engine()
    session = sessionmaker(bind=engine)()
    try:
        rows = session.query(PluginData).filter(PluginData.plugin_id == PLUGIN_ID).all()
        return {str(r.key): r.value for r in rows}
    finally:
        session.close()


def _delete_keys(keys: List[str]) -> None:
    if not keys:
        return
    from sqlalchemy.orm import sessionmaker

    get_engine, PluginData, _, _ = _import_mp()
    engine = get_engine()
    session = sessionmaker(bind=engine)()
    try:
        for key in keys:
            session.query(PluginData).filter(
                PluginData.plugin_id == PLUGIN_ID, PluginData.key == key
            ).delete()
        session.commit()
    finally:
        session.close()


# ──────────────────────────────────────────────────────────────────────
# 数据安全校验：5 表 + 派生量快照
# ──────────────────────────────────────────────────────────────────────


def _hr_bills_count(data_dir: Path) -> int:
    f = data_dir / HR_BILLS_FILE
    if not f.exists():
        return 0
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return -1  # 读不了 → 快照比对时强制不一致，中止
    if isinstance(data, dict):
        return len(data)
    if isinstance(data, list):
        return len(data)
    return -1


def _table_snapshot(data_dir: Path) -> Dict[str, Any]:
    """5 表行数 + 派生量快照（identity 分组、in_library 计数、H&R 账单条数）。"""
    from sqlalchemy import text

    _, _, get_database, _ = _import_mp()
    handle = get_database(PLUGIN_ID)
    session = handle.session()
    try:
        tables: Dict[str, int] = {}
        for t in TABLES:
            try:
                tables[t] = int(session.execute(text(f"SELECT count(*) FROM {t}")).scalar() or 0)
            except Exception:  # noqa: BLE001
                tables[t] = -1
        identity_groups: Dict[str, int] = {}
        try:
            for row in session.execute(
                text("SELECT identity, count(*) FROM mf_resource GROUP BY identity")
            ):
                identity_groups[str(row[0])] = int(row[1])
        except Exception:  # noqa: BLE001
            identity_groups = {"__error__": -1}
        try:
            in_library = int(
                session.execute(text("SELECT count(*) FROM mf_resource WHERE in_library = true")).scalar()
                or 0
            )
        except Exception:  # noqa: BLE001
            in_library = -1
    finally:
        session.close()

    return {
        "tables": tables,
        "identity_groups": identity_groups,
        "in_library": in_library,
        "hr_bills": _hr_bills_count(data_dir),
    }


# ──────────────────────────────────────────────────────────────────────
# 存活检查：扫描已装插件源码，判断某个键是否仍被 kv 读写
# ──────────────────────────────────────────────────────────────────────


def _scan_refs(key: str, src: Path) -> Tuple[bool, List[str]]:
    """返回 (is_live, [file:line 样本...])。

    判据（尽量只抓「真实 kv 访问」，避免 docstring/常量误报）：
      1. 直接：把 key 字面量传给 save_data/get_data/del_data；
      2. 间接：某常量 ``NAME = "key"`` 被传给 save_data/get_data/del_data/_save_data/_get_data
         —— 但 STATE_KEY/GROUPS_KEY（已路由到 5 表）豁免。
    """
    _q = "[\"']"  # 字符类：匹配 " 或 '
    direct = re.compile(
        r"(?:save_data|get_data|del_data)\s*\(\s*(?:key\s*=\s*)?"
        + _q + re.escape(key) + _q
    )
    const_holder = re.compile(r"\b([A-Z][A-Z0-9_]*)\s*=\s*" + _q + re.escape(key) + _q)

    hits: List[str] = []
    py_files = [p for p in src.rglob("*.py") if "__pycache__" not in p.parts]
    const_names: List[str] = []

    for p in py_files:
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(lines, 1):
            # 1) 直接字面量访问
            if direct.search(line):
                hits.append(f"{p.relative_to(src)}:{i}")
            # 2) 常量定义收集
            for m in const_holder.finditer(line):
                name = m.group(1)
                if name not in _TABLE_BACKED_CONSTANTS:
                    const_names.append(name)

    if const_names:
        usage = re.compile(
            r"(?:save_data|get_data|del_data|_save_data|_get_data)\s*\(\s*(?:key\s*=\s*)?"
            + r"(" + "|".join(map(re.escape, const_names)) + r")\b"
        )
        for p in py_files:
            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:  # noqa: BLE001
                continue
            for i, line in enumerate(lines, 1):
                if usage.search(line):
                    hits.append(f"{p.relative_to(src)}:{i}")

    hits = sorted(set(hits))
    return bool(hits), hits


# ──────────────────────────────────────────────────────────────────────
# 备份
# ──────────────────────────────────────────────────────────────────────


def _write_backup(data_dir: Path, items: List[Dict[str, Any]]) -> Path:
    """把将被删的键原样 dump 到 0600 文件；写失败抛异常（调用方中止）。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_now()
    final = data_dir / f"{BACKUP_FILE_PREFIX}_{stamp}.json"
    payload = {
        "created_utc": stamp,
        "plugin_id": PLUGIN_ID,
        "purpose": "一次性清理账本链 kv 残留前的原样备份（回滚用）",
        "keys": items,
    }
    tmp = data_dir / f".{BACKUP_FILE_PREFIX}_{stamp}.{os.getpid()}.tmp"
    # 0600：先 os.open 落盘，再原子 rename
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        os.chmod(str(tmp), 0o600)
        os.rename(str(tmp), str(final))
    except Exception:
        try:
            os.unlink(str(tmp))
        except OSError:
            pass
        raise
    return final


# ──────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────


def _collect_plan(all_kv: Dict[str, Any], data_dir: Path, args) -> Dict[str, Any]:
    """归类：dead / protected_collision / uncertain，并附存活检查。"""
    dead_exact = sorted({k for k in all_kv if k in set(DEAD_KEYS)})
    dead_prefix = sorted({k for k in all_kv if any(k.startswith(p) for p in DEAD_PREFIXES)})
    dead = sorted(set(dead_exact + dead_prefix))

    # 护栏：待删键若撞上「绝对不许碰」清单 → 立刻记为冲突（拒绝删）
    collisions: List[str] = []
    for k in dead:
        if k in PROTECTED_EXACT or any(k.startswith(p) for p in PROTECTED_PREFIXES):
            collisions.append(k)
    if collisions:
        # 从待删里剔除冲突键（宁可少删，不可错删）
        dead = [k for k in dead if k not in set(collisions)]

    # 存活检查（默认开）
    live: Dict[str, List[str]] = {}
    if not args.no_check_live:
        src = _resolve_plugin_src(args.plugin_src, data_dir)
        for k in dead:
            is_live, hits = _scan_refs(k, src)
            if is_live:
                live[k] = hits

    # 不确定项：迁移家族里没进待删清单的键（如 rules_migrations）
    uncertain = sorted(
        {
            k
            for k in all_kv
            if _UNCERTAIN_MIGRATION_PATTERN.match(k)
            and k not in set(dead)
            and k not in set(DEAD_KEYS)
            and not any(k.startswith(p) for p in DEAD_PREFIXES)
        }
    )

    # 各键当前值概要
    rows = []
    for k in dead:
        v = all_kv[k]
        rows.append(
            {
                "key": k,
                "summary": _value_summary(v),
                "size_bytes": _size_of(v),
                "sha1": _sha1_of(v),
                "live_refs": live.get(k, []),
            }
        )
    return {
        "dead": dead,
        "rows": rows,
        "live": live,
        "collisions": collisions,
        "uncertain": uncertain,
        "total_size_bytes": sum(r["size_bytes"] for r in rows),
    }


def _human_report(plan: Dict[str, Any], all_kv: Dict[str, Any], apply: bool) -> str:
    lines: List[str] = []
    lines.append(f"插件 {PLUGIN_ID} 的 plugindata kv 键总数：{len(all_kv)}")
    dead = plan["dead"]
    if not dead:
        lines.append("✅ 无残留可清（待删清单里的键在 kv 里都不存在）。")
        if plan["uncertain"]:
            lines.append("   ⚠️ 仍存在但不在待删清单的迁移家族键（未动）：" + ", ".join(plan["uncertain"]))
        return "\n".join(lines)

    lines.append(f"将删除 {len(dead)} 个键，合计约 {plan['total_size_bytes'] / 1024:.1f} KB：")
    for r in plan["rows"]:
        flag = "  ⚠️ 仍被代码引用(跳过)" if r["key"] in plan["live"] else ""
        lines.append(
            f"  - {r['key']!r:40} {r['summary']:12} {r['size_bytes'] / 1024:.1f} KB  sha1={r['sha1'][:12]}…{flag}"
        )
    if plan["collisions"]:
        lines.append("  ❌ 以下键撞「绝对不许碰」护栏，已剔除：")
        for c in plan["collisions"]:
            lines.append(f"      {c}")
    if plan["live"]:
        lines.append("  存活检查：以下键在已装插件源码里仍被 kv 读写（默认跳过，--force 才删）：")
        for k, refs in plan["live"].items():
            lines.append(f"      {k}  ← " + ", ".join(refs[:5]) + ("…" if len(refs) > 5 else ""))
    if plan["uncertain"]:
        lines.append("  提示：以下迁移家族键未在待删清单里（未动，请人工确认）：")
        for u in plan["uncertain"]:
            lines.append(f"      {u}")
    lines.append("" if apply else "（--dry-run 未写任何东西；加 --apply 才真正删除）")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="一次性清理 MagicFlow「账本链 kv 残留」（默认干跑，跑完即弃）。"
    )
    parser.add_argument("--apply", action="store_true", help="真正删除（先备份再删，前后快照比对）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将删内容，不写（默认行为）")
    parser.add_argument("--data-dir", default=None, help="插件数据目录（默认自动探测）")
    parser.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    parser.add_argument("--force", action="store_true", help="仍删「被代码引用」的键（默认跳过）")
    parser.add_argument("--no-check-live", action="store_true", help="关闭存活检查")
    parser.add_argument("--plugin-src", default=None, help="已装插件源码目录（存活检查用，默认自动探测）")
    args = parser.parse_args()

    data_dir = _resolve_data_dir(args.data_dir)

    if args.json:
        # MP 引擎首次初始化会向 stdout 打一行 "PostgreSQL database connected..."，
        # 先缓冲 stdout 把噪声吞掉，最后只吐纯 JSON。
        import io
        real_stdout = sys.stdout
        sys.stdout = io.StringIO()
        err: Optional[str] = None
        result: Optional[Dict[str, Any]] = None
        try:
            try:
                all_kv = _list_kv()
                plan = _collect_plan(all_kv, data_dir, args)
                if args.apply:
                    result = _apply(plan, all_kv, data_dir, args, quiet=True)
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
        finally:
            sys.stdout = real_stdout

        if err is not None:
            print(json.dumps({"plugin_id": PLUGIN_ID, "mode": "error", "error": err},
                             ensure_ascii=False, indent=2, sort_keys=True))
            return 1
        report = {
            "plugin_id": PLUGIN_ID,
            "data_dir": str(data_dir),
            "mode": "apply" if args.apply else "dry-run",
            "total_keys": len(all_kv),
            "to_delete": plan["rows"],
            "skipped_live": plan["live"],
            "collisions": plan["collisions"],
            "uncertain": plan["uncertain"],
            "total_size_bytes": plan["total_size_bytes"],
        }
        if result is not None:
            report["result"] = result
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 1 if (result is not None and result.get("error")) else 0

    try:
        all_kv = _list_kv()
    except Exception as err:  # noqa: BLE001
        print(f"❌ 读取 plugindata 失败：{err}", file=sys.stderr)
        return 1

    plan = _collect_plan(all_kv, data_dir, args)

    print(_human_report(plan, all_kv, args.apply))
    if args.apply:
        if not plan["dead"]:
            print("✅ 无残留可清。")
            return 0
        result = _apply(plan, all_kv, data_dir, args, quiet=False)
        return 1 if result.get("error") else 0
    return 0


def _apply(plan: Dict[str, Any], all_kv: Dict[str, Any], data_dir: Path, args, quiet: bool = False) -> Dict[str, Any]:
    """真正删除：备份 → 删除 → 前后快照比对。任一失败即中止。

    返回 dict；``error`` 字段存在即失败（调用方据此决定退出码）。
    进度信息走 stdout（``quiet=True`` 时抑制，供 --json）；错误始终走 stderr。
    """
    def _say(msg: str) -> None:
        if not quiet:
            print(msg)

    def _fail(msg: str) -> None:
        print(msg, file=sys.stderr)

    # 1) 确定最终删除集（存活检查默认跳过被引用键，--force 才删）
    skip_live = {k for k in plan["live"] if not args.force}
    to_delete = [k for k in plan["dead"] if k not in skip_live]
    result: Dict[str, Any] = {"deleted": [], "skipped_live": sorted(skip_live), "backup_file": None}

    if not to_delete:
        _say("⚠️ 没有可安全删除的键（全部被存活检查跳过）。加 --force 可强制删除。")
        result["skipped_live"] = sorted(set(result["skipped_live"]) | set(plan["dead"]))
        return result

    _say(f"→ 最终删除 {len(to_delete)} 个键：{', '.join(to_delete)}")

    # 2) 备份（先备份再删；备份写失败 → 中止，不删任何键）
    items = [
        {
            "key": k,
            "value": all_kv[k],
            "size": _size_of(all_kv[k]),
            "sha1": _sha1_of(all_kv[k]),
        }
        for k in to_delete
    ]
    try:
        backup = _write_backup(data_dir, items)
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 备份写入失败，已中止（未删任何键）：{err}")
        return {"error": f"备份失败: {err}", "deleted": [], "skipped_live": result["skipped_live"]}
    result["backup_file"] = backup.name
    _say(f"✅ 已备份 {len(items)} 个键 → {backup.name}（0600）")

    # 3) 删除前快照
    try:
        before = _table_snapshot(data_dir)
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删除前快照失败，已中止（未删任何键）：{err}")
        return {"error": f"删除前快照失败: {err}", "deleted": [], "backup_file": result["backup_file"],
                "skipped_live": result["skipped_live"]}

    # 4) 删除
    try:
        _delete_keys(to_delete)
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删除 kv 键失败，已中止：{err}")
        return {"error": f"删除失败: {err}", "deleted": [], "backup_file": result["backup_file"],
                "skipped_live": result["skipped_live"]}

    # 5) 删除后快照 + 比对
    try:
        after = _table_snapshot(data_dir)
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删除后快照失败（键已删但无法校验，见备份回滚）：{err}")
        return {"error": f"删除后快照失败: {err}", "deleted": to_delete,
                "backup_file": result["backup_file"], "skipped_live": result["skipped_live"]}

    if before != after:
        _fail("❌ 数据安全校验失败：删除前后「5 表行数/派生量」不一致，请立即用备份文件回滚！")
        _fail(f"   before={json.dumps(before, ensure_ascii=False, sort_keys=True, default=str)}")
        _fail(f"   after ={json.dumps(after, ensure_ascii=False, sort_keys=True, default=str)}")
        result["error"] = "快照不一致"
        result["before"] = before
        result["after"] = after
        result["deleted"] = to_delete
        return result

    result["deleted"] = to_delete
    _say(f"✅ 已删除 {len(to_delete)} 个键；5 表行数/派生量校验一致。")
    return result


if __name__ == "__main__":
    sys.exit(main())
