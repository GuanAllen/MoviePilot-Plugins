#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性把剩余 kv 账本/状态并入表（12.2.0；跑完即弃）。

================================ 迁什么 ================================
    组 A（站点面 → mf_site）：
        pv_budget        → mf_site.pv_budget（Integer，按 mp_site_id）
        live_pv_block    → mf_site.pv_block（Float，按 mp_site_id）
        live_alerts      → mf_site.alerts（JSON，键 "sid:kind" 拆 site）
        pv_usage         → mf_site.pv_usage（JSON，按 site 重组 {date:{site:{..}}}→{site:{date:{..}}}）
        signin_records   → mf_site.signin（JSON，同上按 site 重组）
        iyuu_sites       → mf_site.credential.__iyuu__（domain 键，密文）
        reseed_passkeys  → mf_site.credential.__reseed_passkey__（iyuu_sid 键，密文）
    组 B（种子面 → mf_seed / mf_crossseed）：
        rescue_stall     → mf_seed.rescue（JSON {hash: ts}）
        ondemand_pending → mf_seed.pending（JSON {hash: {…}}）
        crossseed_pending→ mf_crossseed.pending（JSON {hash: rec}）
    组 C（新表 / caps 子槽）：
        reseed_ledger    → 新表 mf_reseed（key="<iyuu_sid>:<hash>"）
        signin_last_full → 新表 mf_run（key="signin_last_full"，标量 float）
        signin_retry     → 新表 mf_run（key="signin_retry"）
        signin_keepalive → 新表 mf_run（key="signin_keepalive"）
        claim_profile    → mf_site.caps.__claim__（mp_site_id 键）
    组 C'（subG：漏网的运行账本/状态）：
        claim_ledger        → 新表 mf_claim（key="<site_id>:<hash>"）
        keepalive_alert_day → 新表 mf_run（key="keepalive_alert_day"，标量字符串日期）
        crossseed_ban       → 新表 mf_run（key="crossseed_ban"，{domain:{ts,reason}}）
    组 D（死键 / 一次性迁移标记 → 直接删）：
        bday:cspt.top / bday:hdfans.org / bday:hdtime.org / bday:m-team.cc /
        bday:pttime.org / bday:soulvoice.club / rules_migrations /
        hr_trust_migrated_3410 / rating_source_migrated_3224

================================ 为什么安全 ================================
1. **表 = 唯一真值源**：迁完这些键在代码里失去 kv 读写入口（存活检查会证明）。
2. **先写后删 + 回读校验**：逐槽写表 → 回读比对（逐字段无损）→ 才备份 → 才删 → 前后快照比对。
3. **幂等**：重跑时表里已有且逐字段无损 → 跳过并报「已迁移」。

================================ 怎么用（必须在容器内跑） ================================
    docker exec -it moviepilot-v3 sh -lc 'cd /app && /opt/venv/bin/python3 /app/app/plugins/magicflow/tools/migrate_kv_1220.py --dry-run'
    docker exec -it moviepilot-v3 sh -lc 'cd /app && /opt/venv/bin/python3 /app/app/plugins/magicflow/tools/migrate_kv_1220.py --apply'

参数同 `migrate_site_kv_to_tables.py`：--dry-run / --apply / --data-dir / --plugin-src /
--json / --force / --no-check-live。
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
BACKUP_FILE_PREFIX = "legacy_kv_1220_backup"

# 组 A/B/C：有表落点的键（迁入表）
MIGRATE_KEYS: List[str] = [
    # 组 A
    "pv_budget", "live_pv_block", "live_alerts", "pv_usage", "signin_records",
    "iyuu_sites", "reseed_passkeys",
    # 组 B
    "rescue_stall", "ondemand_pending", "crossseed_pending",
    # 组 C
    "reseed_ledger", "signin_last_full", "signin_retry", "signin_keepalive", "claim_profile",
    # 组 C'（subG：漏网的运行账本/状态）
    "claim_ledger", "keepalive_alert_day", "crossseed_ban",
]

# 组 D：死键 / 一次性迁移标记（只删，不迁表）。
# ★ 注意：rules_migrations / hr_trust_migrated_3410 / rating_source_migrated_3224 仍是
#   代码里的「一次性迁移标记」（features/core.py / features/siteops.py 仍在读/写），
#   盲删会重跑非幂等迁移（例：rating_source_migrated_3224 会把用户后来手选的「豆瓣优先」
#   又强改回 tmdb）。存活检查默认跳过它们（--force 才删）。
DELETE_KEYS: List[str] = [
    "bday:cspt.top", "bday:hdfans.org", "bday:hdtime.org", "bday:m-team.cc",
    "bday:pttime.org", "bday:soulvoice.club",
    "rules_migrations", "hr_trust_migrated_3410", "rating_source_migrated_3224",
]

# 标量槽（值不是 dict）
SCALAR_KEYS = {"signin_last_full", "keepalive_alert_day"}

# 10 表快照（删除前后比对）
TABLES: List[str] = ["mf_seed", "mf_resource", "mf_site", "mf_identity",
                     "mf_task", "mf_deck", "mf_crossseed", "mf_reseed", "mf_run", "mf_claim"]


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
# MoviePilot 环境（懒导入）
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
# kv 读写（plugindata）
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
# 插件实例 / SiteStore
# ──────────────────────────────────────────────────────────────────────
def _load_plugin_and_store():
    from app.db.plugin.registry import get_database

    handle = get_database(PLUGIN_ID)

    class _Shim:
        plugin_id = PLUGIN_ID

        def get_database(self):
            return handle

        def _log(self, msg, level="info"):  # noqa: ANN001
            print(f"  [plugin:{level}] {msg}")

    p = _Shim()
    try:
        from app.runtime.extensions.plugin.manager import PluginManager

        running = PluginManager().running_plugins or {}
        live = running.get(PLUGIN_ID)
        if live is not None:
            p = live
    except Exception:  # noqa: BLE001
        pass

    import importlib

    importlib.import_module("app.plugins.magicflow")
    sitestore = importlib.import_module("app.plugins.magicflow.sitestore")
    return p, sitestore.get_site_store(p)


# ──────────────────────────────────────────────────────────────────────
# 回读校验
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


def _verify_lossless(original: Any, migrated: Any) -> Tuple[bool, List[str]]:
    """返回 (ok, 差异明细)。dict 逐键比对；标量直接比。

    ★ 12.2.0 修：``original`` 是**空 dict**（如 ``signin_retry={"d": {}}`` 的条目）时，
    旧实现会因「零键循环」空真判无损；现在先要求 ``migrated`` 必须是 dict，缺条目直接算差异。
    """
    problems: List[str] = []
    if isinstance(original, dict):
        if not isinstance(migrated, dict):
            return False, [f"表里缺该条目（kv={original!r} 表={migrated!r}）"]
        for k, v in (original or {}).items():
            nv = _norm_val(v)
            if nv is None:
                continue
            mv = _norm_val((migrated or {}).get(k))
            if mv != nv:
                problems.append(f"{k}: kv={nv!r} != 表={mv!r}")
    else:
        if _norm_val(migrated) != _norm_val(original):
            problems.append(f"kv={original!r} != 表={migrated!r}")
    return (not problems), problems


# ──────────────────────────────────────────────────────────────────────
# 快照
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
# 存活检查
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
        "purpose": "剩余 kv 账本/状态并入表前的原样备份（回滚用）",
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
def _has_data(key: str, value: Any) -> bool:
    if key in SCALAR_KEYS:
        return value is not None
    return isinstance(value, dict) and len(value) > 0


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
            "has_data": _has_data(k, v) if k in all_kv else False,
            "summary": _value_summary(v) if k in all_kv else "(不存在)",
            "count": (1 if (k in SCALAR_KEYS and k in all_kv and v is not None)
                      else (len(v) if (k in all_kv and isinstance(v, dict)) else 0)),
            "size_bytes": _size_of(v) if k in all_kv else 0,
            "sha1": _sha1_of(v) if k in all_kv else "",
            "live_refs": live_refs,
        })
    # 组 D 死键（含存活检查：仍被代码读/写的一次性迁移标记默认跳过）
    dead_rows = []
    for k in DELETE_KEYS:
        live_refs: List[str] = []
        if not args.no_check_live:
            is_live, refs = _scan_refs(k, src)
            live_refs = refs if is_live else []
        dead_rows.append({"key": k, "present": k in all_kv, "live_refs": live_refs})
    return {"rows": rows, "dead": dead_rows,
            "live": {r["key"]: r["live_refs"] for r in rows if r["live_refs"]}}


def _human_report(plan: Dict[str, Any], apply: bool) -> str:
    lines: List[str] = [f"插件 {PLUGIN_ID}：剩余 kv 账本/状态 → 表（12.2.0）"]
    for r in plan["rows"]:
        flag = "  ⚠️ 仍被 kv 读写(跳过)" if r["live_refs"] else ""
        if r["present"] and r["has_data"]:
            lines.append(
                f"  - {r['key']!r:20} {r['summary']:10} {r['count']} 条  "
                f"{r['size_bytes'] / 1024:.1f} KB  sha1={r['sha1'][:12]}…{flag}"
            )
        else:
            lines.append(f"  - {r['key']!r:20} (kv 里无数据，跳过){flag}")
    if plan["dead"]:
        dead_present = [d["key"] for d in plan["dead"] if d["present"]]
        dead_skip = [d["key"] for d in plan["dead"] if d["present"] and d["live_refs"]]
        lines.append("  组 D 死键（删）：" + (", ".join(dead_present) if dead_present else "（线上均已不存在）"))
        if dead_skip:
            lines.append("     ⚠️ 仍被代码读写，默认跳过（--force 才删）：" + ", ".join(dead_skip))
    if plan["live"]:
        lines.append("  存活检查：以下键仍被 kv 读写（默认跳过，--force 才迁）：")
        for k, refs in plan["live"].items():
            lines.append(f"      {k}  ← " + ", ".join(refs[:5]))
    lines.append("" if apply else "（--dry-run 未写任何东西；加 --apply 才真正迁移）")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="一次性把剩余 kv 账本/状态并入表（默认干跑，跑完即弃）。")
    parser.add_argument("--apply", action="store_true", help="真正迁移")
    parser.add_argument("--dry-run", action="store_true", help="只打印将迁内容（默认）")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--plugin-src", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-check-live", action="store_true")
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
            "dead": plan["dead"],
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

    skip_live = {k for k in plan["live"] if not args.force}
    to_migrate = [r["key"] for r in plan["rows"]
                  if r["present"] and r["has_data"] and r["key"] not in skip_live]
    # 组 D 死键（只删，不迁表；仍被代码读写的默认跳过）
    to_delete = [d["key"] for d in plan["dead"]
                 if d["present"] and (args.force or not d["live_refs"])]
    result: Dict[str, Any] = {"migrated": [], "deleted": [], "skipped_live": sorted(skip_live),
                              "backup_file": None}

    if not to_migrate and not to_delete:
        _say("⚠️ 没有可迁移的数据（键不存在/为空/被存活检查跳过）。")
        return result

    _say(f"→ 迁移 {len(to_migrate)} 个键：{', '.join(to_migrate)}")
    if to_delete:
        _say(f"→ 删除 {len(to_delete)} 个死键：{', '.join(to_delete)}")

    # 2) 写表（先写后删；幂等：表里已有且逐字段无损 → 跳过）
    p, store = _load_plugin_and_store()
    # ★ 注入站点名提示表（脚本进程拿不到 plugin.get_data；iyuu_cache 里的 id→名称/域名）
    try:
        _hints: Dict[str, Any] = {}
        _cache = all_kv.get("iyuu_cache") or {}
        for _nick, _item in ((_cache.get("sites") or {}) if isinstance(_cache, dict) else {}).items():
            if isinstance(_item, dict) and _item.get("id") is not None:
                _base = str(_item.get("base_url") or "")
                _host = _base.split("//")[-1].split("/")[0].strip() if _base else ""
                _hints[str(int(_item["id"]))] = {
                    "name": str(_item.get("nickname") or _nick or ""), "domain": _host,
                }
        store.bind_site_hints(_hints)
        _say(f"  站点名提示表：{len(_hints)} 条（来自 iyuu_cache）")
    except Exception as err:  # noqa: BLE001
        _say(f"  ⚠️ 站点名提示表构建失败（不影响迁移）：{err}")
    for key in to_migrate:
        value = all_kv[key]
        try:
            already = store.get(key)
        except Exception:  # noqa: BLE001
            already = None
        if key in SCALAR_KEYS:
            lossless = _verify_lossless(value, already)[0]
        else:
            pks = [str(k).strip().lower() for k in (value or {}).keys()
                   if isinstance(value.get(k), dict)]
            value_l = {str(k).strip().lower(): v for k, v in (value or {}).items()
                       if isinstance(v, dict)}
            # ★ 12.2.0 修：下面不能对 migrated 侧写 `or {}`（会把「无该条目」洗成「空 dict」→ 空真判无损）
            lossless = bool(pks) and all(
                _verify_lossless(value_l.get(pk) or {}, (already or {}).get(pk))[0]
                for pk in pks
            ) if pks else False
        if lossless:
            _say(f"  {key}：表里已有且逐字段无损 → 已迁移，跳过")
            continue
        _say(f"  写表 {key}（{_value_summary(value)}）…")
        try:
            store.save(key, value)
        except Exception as err:  # noqa: BLE001
            _fail(f"❌ 写表 {key} 失败，已中止：{err}")
            return {"error": f"写表失败: {err}", "migrated": [], "deleted": [],
                    "backup_file": None, "skipped_live": result["skipped_live"]}

    # 3) 回读校验
    verify_fail: List[str] = []
    for key in to_migrate:
        try:
            migrated = store.get(key)
        except Exception as err:  # noqa: BLE001
            _fail(f"❌ 回读 {key} 失败，已中止：{err}")
            return {"error": f"回读失败: {err}", "migrated": to_migrate, "deleted": [],
                    "backup_file": None, "skipped_live": result["skipped_live"]}
        value = all_kv[key]
        if key in SCALAR_KEYS:
            ok, problems = _verify_lossless(value, migrated)
            if not ok:
                verify_fail.append(f"{key}：" + "; ".join(problems))
            _say(f"  回读校验 {key}：标量一致")
            continue
        for pk, rec in (value or {}).items():
            if not isinstance(rec, dict):
                continue
            pk_norm = str(pk).strip().lower()
            back = (migrated or {}).get(pk_norm)
            if back is None:
                verify_fail.append(f"{key}[{pk}]：回读缺失")
                continue
            ok, problems = _verify_lossless(rec, back)
            if not ok:
                verify_fail.append(f"{key}[{pk}]：" + "; ".join(problems))
        _say(f"  回读校验 {key}：{len(value)} 条 → 表里 {len(migrated or {})} 条")
    if verify_fail:
        _fail("❌ 回读校验失败，已中止，未删任何键：")
        for line in verify_fail[:20]:
            _fail(f"   {line}")
        return {"error": "回读校验失败", "migrated": to_migrate, "deleted": [],
                "backup_file": None, "verify_fail": verify_fail,
                "skipped_live": result["skipped_live"]}

    # 4) 备份（写失败即中止，不删任何键）
    items = [
        {"key": k, "value": all_kv[k], "size": _size_of(all_kv[k]), "sha1": _sha1_of(all_kv[k])}
        for k in to_migrate
    ] + [{"key": k, "value": all_kv.get(k), "size": _size_of(all_kv.get(k)),
          "sha1": _sha1_of(all_kv.get(k)), "delete_only": True} for k in to_delete]
    try:
        backup = _write_backup(data_dir, items)
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 备份写入失败，已中止（未删任何键）：{err}")
        return {"error": f"备份失败: {err}", "migrated": to_migrate, "deleted": [],
                "backup_file": None, "skipped_live": result["skipped_live"]}
    result["backup_file"] = backup.name
    _say(f"✅ 已备份 {len(items)} 个键 → {backup.name}（0600）")

    # 5) 删前快照
    try:
        before = _table_snapshot()
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删前快照失败，已中止：{err}")
        return {"error": f"删前快照失败: {err}", "migrated": to_migrate,
                "deleted": [], "backup_file": result["backup_file"],
                "skipped_live": result["skipped_live"]}

    # 6) 删 kv
    try:
        _delete_keys(to_migrate + to_delete)
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删除 kv 键失败，已中止：{err}")
        return {"error": f"删除失败: {err}", "migrated": to_migrate, "deleted": [],
                "backup_file": result["backup_file"], "skipped_live": result["skipped_live"]}

    # 7) 删后快照 + 比对
    try:
        after = _table_snapshot()
    except Exception as err:  # noqa: BLE001
        _fail(f"❌ 删后快照失败（键已删但无法校验，见备份回滚）：{err}")
        return {"error": f"删后快照失败: {err}", "migrated": to_migrate,
                "deleted": to_delete, "backup_file": result["backup_file"],
                "skipped_live": result["skipped_live"]}
    if before != after:
        _fail("❌ 数据安全校验失败：删 kv 前后 10 表行数/规则字段计数不一致，请立即用备份回滚！")
        _fail(f"   before={json.dumps(before, ensure_ascii=False, sort_keys=True, default=str)}")
        _fail(f"   after ={json.dumps(after, ensure_ascii=False, sort_keys=True, default=str)}")
        result["error"] = "快照不一致"
        result["before"] = before
        result["after"] = after
        result["migrated"] = to_migrate
        result["deleted"] = to_delete
        return result

    result["migrated"] = to_migrate
    result["deleted"] = to_delete
    _say(f"✅ 已迁移 {len(to_migrate)} 个键 + 删 {len(to_delete)} 个死键；10 表行数/规则字段计数一致。")
    return result


if __name__ == "__main__":
    sys.exit(main())
