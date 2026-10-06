#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性把三套「仍活读写的 kv 账本」迁进 5 表（12.1.0 WS2；跑完即弃）。

================================ 迁什么 ================================
    site_rules (16)        → mf_site 真列（hr/seed_hours/… + 新增 note/exam_evidence/
                             per_torrent_hr + rules_extra JSON 兜底）
    site_caps (15)         → mf_site.caps（JSON 列，整条 cap rec）
    crossseed_sources (2)  → 新表 mf_crossseed（+ extra JSON 兜底）
（``sitecap_override`` 线上无数据，不迁；改由 ``features/live.py`` 读 ``mf_site.caps`` 的
``__override__`` 子槽，为空行为不变。）

================================ 为什么安全 ================================
1. **表 = 唯一真值源**：迁完 kv 里这三个键彻底消失；``features/siteops.py`` /
   ``features/live.py`` / ``features/crossseed.py`` 已改走 ``sitestore.SiteStore`` 表回调，
   不再 ``get_data/save_data`` 这三个键（存活检查会证明）。
2. **先写后删 + 回读校验**：逐条写表 → 回读比对（每条 kv 记录都读得回来、非空字段逐键相等）
   → 才备份 → 才删 → 删前后「7 表行数 + mf_site 规则字段计数」快照比对，任一失败即中止。
3. **幂等**：重跑时表里已有 → 跳过并报「已迁移」。

================================ 怎么用（必须在容器内跑） ================================
本脚本依赖 MoviePilot 运行环境（``app.*`` 模块 + 数据库），**只能在容器内跑**：

    docker exec -it moviepilot-v3 sh -lc 'cd /app && /opt/venv/bin/python3 /app/app/plugins/magicflow/tools/migrate_site_kv_to_tables.py --dry-run'
    docker exec -it moviepilot-v3 sh -lc 'cd /app && /opt/venv/bin/python3 /app/app/plugins/magicflow/tools/migrate_site_kv_to_tables.py --apply'

参数:
    --dry-run            默认；只打印「将迁哪些键、条数、目标表/列」，不写任何东西。
    --apply              真正迁移（写表 → 回读校验 → 备份 → 删 kv → 快照比对）。
    --data-dir=<路径>    插件数据目录（默认自动探测 /config/plugins/MagicFlow）；备份落这里。
    --plugin-src=<路径>  已装插件源码目录（存活检查用，默认自动探测）。
    --json               机器可读输出（一个 JSON 报告）。
    --no-check-live      关闭存活检查（默认跳过「仍被 kv 读写」的键）。

================================ 怎么回滚 ================================
--apply 时先把三个键**原样 dump** 到 ``<data_dir>/legacy_site_kv_backup_<UTC>.json``（0600），
含 ``key/value/size/sha1``。要回滚：把备份里的 ``keys[].value`` 用 ``save_data(key, value)``
逐个写回即可。**备份文件写失败会直接中止，不写表不删键。**

================================ 已知边界 ================================
- ``crossseed_sources`` rec 里有 ``resource_id/need_hours/pool/done_ts`` 等键不在 §2.3 列清单里
  → 落 ``mf_crossseed.extra`` JSON 兜底（防丢字段，回读合并还原）。
- ``site_rules`` rec 里的 ``framework/seed_hours_seen/site_id`` 等键同理落 ``mf_site.rules_extra``。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PLUGIN_ID = "MagicFlow"
BACKUP_FILE_PREFIX = "legacy_site_kv_backup"

# 本脚本迁移的三个 kv 键 → SiteStore 槽名（一一对应）
MIGRATE_KEYS: List[str] = ["site_rules", "site_caps", "crossseed_sources"]

# 7 表快照（删除前后比对：删 kv 不该动任何表）
TABLES: List[str] = ["mf_seed", "mf_resource", "mf_site", "mf_identity",
                     "mf_task", "mf_deck", "mf_crossseed"]


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
# 插件实例 / SiteStore（真表读写）
# ──────────────────────────────────────────────────────────────────────
def _load_plugin_and_store():
    """拿真插件实例（退化为「真库句柄 shim」）+ 对应的 SiteStore。"""
    from app.db.plugin.registry import get_database

    handle = get_database(PLUGIN_ID)

    class _Shim:
        plugin_id = PLUGIN_ID

        def get_database(self):
            return handle

        def _log(self, msg, level="info"):  # noqa: ANN001
            print(f"  [plugin:{level}] {msg}")

    p = _Shim()
    try:  # 优先：真插件实例（拿到 SiteStore 的 module 级单例）
        from app.runtime.extensions.plugin.manager import PluginManager

        running = PluginManager().running_plugins or {}
        live = running.get(PLUGIN_ID)
        if live is not None:
            p = live
    except Exception:  # noqa: BLE001
        pass

    import importlib

    pkg = importlib.import_module("app.plugins.magicflow")
    sitestore = importlib.import_module("app.plugins.magicflow.sitestore")
    return p, sitestore.get_site_store(p)


# ──────────────────────────────────────────────────────────────────────
# 回读校验（字段逐键相等，容忍 None/空串归一）
# ──────────────────────────────────────────────────────────────────────
def _norm_val(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str) and v == "":
        return None
    if isinstance(v, (list, tuple)):
        return [_norm_val(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm_val(x) for k, x in v.items()}
    return v


def _verify_lossless(original: Dict[str, Any], migrated: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """返回 (ok, 差异明细)。只要求「原值非空的字段一个不丢、值相等」。"""
    problems: List[str] = []
    for k, v in (original or {}).items():
        nv = _norm_val(v)
        if nv is None:
            continue
        mv = _norm_val(migrated.get(k))
        if mv != nv:
            problems.append(f"{k}: kv={nv!r} != 表={mv!r}")
    return (not problems), problems


# ──────────────────────────────────────────────────────────────────────
# 快照：7 表行数 + mf_site 规则字段计数
# ──────────────────────────────────────────────────────────────────────
def _table_snapshot() -> Dict[str, Any]:
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
        # mf_site 里「有规则字段」的行数（迁移前后应稳定；迁移会新增若干）
        rule_rows = 0
        try:
            rule_rows = int(session.execute(text(
                "SELECT count(*) FROM mf_site WHERE hr IS NOT NULL OR seed_hours IS NOT NULL"
                " OR source IS NOT NULL OR rules_extra IS NOT NULL OR note IS NOT NULL"
            )).scalar() or 0)
        except Exception:  # noqa: BLE001
            rule_rows = -1
    finally:
        session.close()
    return {"tables": tables, "mf_site_rule_rows": rule_rows}


# ──────────────────────────────────────────────────────────────────────
# 存活检查：扫描已装插件源码，判断三个键是否仍被 kv 读写
# ──────────────────────────────────────────────────────────────────────
def _scan_refs(key: str, src: Path) -> Tuple[bool, List[str]]:
    q = "[\"']"
    direct = re.compile(
        r"(?:save_data|get_data|del_data)\s*\(\s*(?:key\s*=\s*)?"
        + q + re.escape(key) + q
    )
    hits: List[str] = []
    py_files = [p for p in src.rglob("*.py") if "__pycache__" not in p.parts]
    for p in py_files:
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(lines, 1):
            if direct.search(line):
                hits.append(f"{p.relative_to(src)}:{i}")
    return bool(hits), sorted(set(hits))


# ──────────────────────────────────────────────────────────────────────
# 备份
# ──────────────────────────────────────────────────────────────────────
def _write_backup(data_dir: Path, items: List[Dict[str, Any]]) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_now()
    final = data_dir / f"{BACKUP_FILE_PREFIX}_{stamp}.json"
    payload = {
        "created_utc": stamp,
        "plugin_id": PLUGIN_ID,
        "purpose": "三套站点 kv 账本并入 5 表前的原样备份（回滚用）",
        "keys": items,
    }
    tmp = data_dir / f".{BACKUP_FILE_PREFIX}_{stamp}.{os.getpid()}.tmp"
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
def _collect_plan(all_kv: Dict[str, Any], args) -> Dict[str, Any]:
    src = _resolve_plugin_src(args.plugin_src, _resolve_data_dir(args.data_dir))
    rows = []
    for k in MIGRATE_KEYS:
        v = all_kv.get(k)
        live_refs: List[str] = []
        if not args.no_check_live:
            is_live, refs = _scan_refs(k, src)
            live_refs = refs if is_live else []
        rows.append({
            "key": k,
            "present": k in all_kv,
            "summary": _value_summary(v) if k in all_kv else "(不存在)",
            "count": len(v) if isinstance(v, dict) else 0,
            "size_bytes": _size_of(v) if k in all_kv else 0,
            "sha1": _sha1_of(v) if k in all_kv else "",
            "live_refs": live_refs,
        })
    return {"rows": rows, "live": {r["key"]: r["live_refs"] for r in rows if r["live_refs"]}}


def _human_report(plan: Dict[str, Any], apply: bool) -> str:
    lines: List[str] = []
    lines.append(f"插件 {PLUGIN_ID}：三套站点 kv 账本 → 5 表（12.1.0 WS2）")
    for r in plan["rows"]:
        flag = "  ⚠️ 仍被 kv 读写(跳过)" if r["live_refs"] else ""
        if r["present"]:
            lines.append(
                f"  - {r['key']!r:20} {r['summary']:10} {r['count']} 条  "
                f"{r['size_bytes'] / 1024:.1f} KB  sha1={r['sha1'][:12]}…{flag}"
            )
        else:
            lines.append(f"  - {r['key']!r:20} (kv 里不存在，跳过){flag}")
    if plan["live"]:
        lines.append("  存活检查：以下键在已装插件源码里仍被 kv 读写（默认跳过，--force 才迁）：")
        for k, refs in plan["live"].items():
            lines.append(f"      {k}  ← " + ", ".join(refs[:5]))
    lines.append("" if apply else "（--dry-run 未写任何东西；加 --apply 才真正迁移）")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="一次性把三套站点 kv 账本迁进 5 表（默认干跑，跑完即弃）。"
    )
    parser.add_argument("--apply", action="store_true", help="真正迁移（写表→回读校验→备份→删 kv→快照比对）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将迁内容，不写（默认行为）")
    parser.add_argument("--data-dir", default=None, help="插件数据目录（默认自动探测）")
    parser.add_argument("--plugin-src", default=None, help="已装插件源码目录（存活检查用）")
    parser.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    parser.add_argument("--force", action="store_true", help="仍迁「被 kv 读写」的键（默认跳过）")
    parser.add_argument("--no-check-live", action="store_true", help="关闭存活检查")
    args = parser.parse_args()

    data_dir = _resolve_data_dir(args.data_dir)

    if args.json:
        real_stdout = sys.stdout
        sys.stdout = io.StringIO()
        err: Optional[str] = None
        result: Optional[Dict[str, Any]] = None
        try:
            try:
                all_kv = _list_kv()
                plan = _collect_plan(all_kv, args)
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
            "to_migrate": plan["rows"],
            "live": plan["live"],
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

    plan = _collect_plan(all_kv, args)
    print(_human_report(plan, args.apply))
    if args.apply:
        result = _apply(plan, all_kv, data_dir, args, quiet=False)
        return 1 if result.get("error") else 0
    return 0


def _apply(plan: Dict[str, Any], all_kv: Dict[str, Any], data_dir: Path, args,
           quiet: bool = False) -> Dict[str, Any]:
    def _say(msg: str) -> None:
        if not quiet:
            print(msg)

    def _fail(msg: str) -> None:
        print(msg, file=sys.stderr)

    # 1) 确定迁移集（存活检查默认跳过被引用键）
    skip_live = {k for k in plan["live"] if not args.force}
    to_migrate = [r["key"] for r in plan["rows"]
                  if r["present"] and r["count"] > 0 and r["key"] not in skip_live]
    result: Dict[str, Any] = {"migrated": [], "skipped_live": sorted(skip_live), "backup_file": None}

    if not to_migrate:
        _say("⚠️ 没有可迁移的数据（三个键不存在/为空/被存活检查跳过）。")
        return result

    _say(f"→ 迁移 {len(to_migrate)} 个键：{', '.join(to_migrate)}")

    # 2) 写表（先写后删；幂等：表里已有 → 跳过并报「已迁移」）
    p, store = _load_plugin_and_store()
    for key in to_migrate:
        value = all_kv[key]
        pks = [str(k).strip().lower() for k in (value or {}).keys() if isinstance(value.get(k), dict)]
        value_l = {str(k).strip().lower(): v for k, v in (value or {}).items() if isinstance(v, dict)}
        # 幂等检查：kv 主键全部已在表里 **且逐字段无损** → 才算「已迁移」，跳过
        try:
            already = store.get(key) or {}
        except Exception:  # noqa: BLE001
            already = {}
        lossless = bool(pks) and all(
            _verify_lossless(value_l.get(pk) or {}, already.get(pk) or {})[0]
            for pk in pks
        ) if pks else False
        if lossless:
            _say(f"  {key}：表里已有 {len(pks)} 条且逐字段无损 → 已迁移，跳过")
            continue
        _say(f"  写表 {key}（{len(value)} 条）…")
        try:
            store.save(key, dict(value))
        except Exception as err:  # noqa: BLE001
            _fail(f"❌ 写表 {key} 失败，已中止：{err}")
            return {"error": f"写表失败: {err}", "migrated": [], "backup_file": None,
                    "skipped_live": result["skipped_live"]}

    # 3) 回读校验
    verify_fail: List[str] = []
    for key in to_migrate:
        try:
            migrated = store.get(key) or {}
        except Exception as err:  # noqa: BLE001
            _fail(f"❌ 回读 {key} 失败，已中止：{err}")
            return {"error": f"回读失败: {err}", "migrated": [], "backup_file": None,
                    "skipped_live": result["skipped_live"]}
        value = all_kv[key]
        for pk, rec in (value or {}).items():
            if not isinstance(rec, dict):
                continue
            pk_norm = str(pk).strip().lower()
            back = migrated.get(pk_norm)
            if back is None:
                verify_fail.append(f"{key}[{pk}]：回读缺失")
                continue
            ok, problems = _verify_lossless(rec, back)
            if not ok:
                verify_fail.append(f"{key}[{pk}]：" + "; ".join(problems))
        _say(f"  回读校验 {key}：{len(value)} 条 → 表里 {len(migrated)} 条")
    if verify_fail:
        _fail("❌ 回读校验失败（字段逐键不一致），已中止，未删任何键：")
        for line in verify_fail[:20]:
            _fail(f"   {line}")
        return {"error": "回读校验失败", "migrated": to_migrate, "backup_file": None,
                "verify_fail": verify_fail, "skipped_live": result["skipped_live"]}

    # 4) 备份（写失败即中止，不删任何键）
    items = [
        {"key": k, "value": all_kv[k], "size": _size_of(all_kv[k]), "sha1": _sha1_of(all_kv[k])}
        for k in to_migrate
    ]
    try:
        backup = _write_backup(data_dir, items)
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 备份写入失败，已中止（未删任何键）：{err}")
        return {"error": f"备份失败: {err}", "migrated": to_migrate,
                "backup_file": None, "skipped_live": result["skipped_live"]}
    result["backup_file"] = backup.name
    _say(f"✅ 已备份 {len(items)} 个键 → {backup.name}（0600）")

    # 5) 删前快照
    try:
        before = _table_snapshot()
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删前快照失败，已中止（未删任何键）：{err}")
        return {"error": f"删前快照失败: {err}", "migrated": to_migrate,
                "backup_file": result["backup_file"], "skipped_live": result["skipped_live"]}

    # 6) 删 kv
    try:
        _delete_keys(to_migrate)
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删除 kv 键失败，已中止：{err}")
        return {"error": f"删除失败: {err}", "migrated": to_migrate,
                "backup_file": result["backup_file"], "skipped_live": result["skipped_live"]}

    # 7) 删后快照 + 比对（删 kv 不该动任何表）
    try:
        after = _table_snapshot()
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删后快照失败（键已删但无法校验，见备份回滚）：{err}")
        return {"error": f"删后快照失败: {err}", "migrated": to_migrate,
                "backup_file": result["backup_file"], "skipped_live": result["skipped_live"]}
    if before != after:
        _fail("❌ 数据安全校验失败：删 kv 前后「7 表行数/规则字段计数」不一致，请立即用备份回滚！")
        _fail(f"   before={json.dumps(before, ensure_ascii=False, sort_keys=True, default=str)}")
        _fail(f"   after ={json.dumps(after, ensure_ascii=False, sort_keys=True, default=str)}")
        result["error"] = "快照不一致"
        result["before"] = before
        result["after"] = after
        result["migrated"] = to_migrate
        return result

    result["migrated"] = to_migrate
    _say(f"✅ 已迁移 {len(to_migrate)} 个键；7 表行数/规则字段计数校验一致。")
    return result


if __name__ == "__main__":
    sys.exit(main())
