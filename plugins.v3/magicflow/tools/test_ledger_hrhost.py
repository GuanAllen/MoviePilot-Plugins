#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 5 表账本「__hr_host__ 保种职务」往返测试（离线，stub sqlalchemy）。

背景（线上真 bug）：``ledger.py`` 的 ``state``/``taken_by`` 不存列，由 ``task_id`` 推导；
``task_id`` 又由 ``seed_row`` 里的 ``_task_id(rec["task"])`` 映射。``__hr_host__``/「H&R保种」
不在 ``_task_configs``/``mf_task`` 里 → 映射成 NULL → 读回 ``state=静默``、``taken_by`` 空 →
``_hr_guard_tick``（只扫 taken_by=__hr_host__）永远扫不到 → 保种机制空转。

修复：``ledger._task_id/_task_state/_task_name`` 识别 ``__hr_host__`` 伪任务。

本测试**只测推导链**（不真连 PG）：``seed_row(rec) → task_id`` 与 ``task_id → state/taken_by/task``
的往返一致性（真库写读走同一组函数，逻辑一致即端到端一致）。

用法：``python3 tools/test_ledger_hrhost.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_ledger_hrhost_test"

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub_sqlalchemy():
    sa = types.ModuleType("sqlalchemy")
    sa.delete = object
    sa.select = object
    sa.update = object
    sa.text = object
    sa.inspect = lambda *a, **k: None
    sa.func = types.SimpleNamespace(count=object)
    def _col(*a, **k):
        return None
    sa.JSON = _col
    sa.Boolean = _col
    sa.Float = _col
    sa.Integer = _col
    sa.String = _col
    sa.Text = _col
    orm = types.ModuleType("sqlalchemy.orm")
    class _DeclarativeBase:
        pass
    orm.DeclarativeBase = _DeclarativeBase
    orm.Mapped = object
    def _mapped_column(*a, **k):
        return None
    orm.mapped_column = _mapped_column
    sa.orm = orm
    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.orm"] = orm


def _load_modules():
    _stub_sqlalchemy()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    tags = _load(PKG + ".tags", "tags.py")
    fingerprint = _load(PKG + ".fingerprint", "fingerprint.py")
    crossseed = _load(PKG + ".crossseed", "crossseed.py")
    persistence = _load(PKG + ".persistence", "persistence.py")
    downloader_ops = _load(PKG + ".downloader_ops", "downloader_ops.py")
    for name, attr_map in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attr_map.items():
            setattr(m, k, v)
    for modname, attrs in (
        ("bonus", ("TorrentBonusInfo", "calc_bonus_per_hour")),
        ("fetcher", ("SiteCandidateTorrent",)),
        ("recommend", ("recognize",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    common = _load(PKG + ".common", "common.py")
    tables = _load(PKG + ".tables", "tables.py")
    db = _load(PKG + ".db", "db.py")
    ledger = _load(PKG + ".ledger", "ledger.py")
    return common, tags, tables, db, ledger


class _MockPlugin:
    def __init__(self):
        self._task_configs = {}

    def _log(self, msg, level=None):
        pass

    def get_database(self):
        return None


def main() -> int:
    print("=" * 64)
    print("魔流 · 5 表账本 __hr_host__ 保种职务往返测试")
    print("=" * 64)

    common, tags, tables, db, ledger = _load_modules()
    be = ledger.LedgerBackend(_MockPlugin())

    # ---- ① _task_id 识别 __hr_host__ / H&R保种 ----
    print("\n[1] _task_id 识别 __hr_host__ / H&R保种")
    _ok(be._task_id("__hr_host__") == common.HR_HOST_TASK_ID, "_task_id('__hr_host__') → __hr_host__")
    _ok(be._task_id("H&R保种") == common.HR_HOST_TASK_ID, "_task_id('H&R保种') → __hr_host__")
    _ok(be._task_id("不存在的任务") is None, "_task_id('不存在的任务') → None")

    # ---- ② _task_state 识别 __hr_host__ → 保种 ----
    print("\n[2] _task_state 识别 __hr_host__ → 保种")
    _ok(be._task_state("__hr_host__") == tags.STATE_HR, "_task_state('__hr_host__') → 保种")
    _ok(be._task_state("不存在的任务") == tags.STATE_SILENT, "_task_state('不存在') → 静默")

    # ---- ③ _task_name 识别 __hr_host__ → H&R保种 ----
    print("\n[3] _task_name 识别 __hr_host__ → H&R保种")
    _ok(be._task_name("__hr_host__") == "H&R保种", "_task_name('__hr_host__') → H&R保种")

    # ---- ④ seed_row 写侧往返：task 名 → task_id ----
    print("\n[4] seed_row 写侧往返：task 名 → task_id")
    row = be.seed_row("aaaa", {"task": "H&R保种", "site": "hdfans.org"}, 0.0)
    _ok(row["task_id"] == common.HR_HOST_TASK_ID, f"seed_row task='H&R保种' → task_id=__hr_host__（{row['task_id']}）")

    # ---- ⑤ 读侧往返：task_id → state/taken_by/task ----
    print("\n[5] 读侧往返：task_id → state/taken_by/task")
    task_id = row["task_id"]
    _ok(be._task_state(task_id) == tags.STATE_HR, "task_id=__hr_host__ → state=保种")
    _ok(be._task_name(task_id) == "H&R保种", "task_id=__hr_host__ → task=H&R保种")
    _ok(str(task_id) == common.HR_HOST_TASK_ID, "task_id=__hr_host__ → taken_by=__hr_host__")

    print("\n" + "=" * 64)
    print(f"✅ 全部通过：{CHECKS} 项断言")
    return 0


if __name__ == "__main__":
    sys.exit(main())
