#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 资源账本「批量落盘」离线回归（19.10.62）。

背景：``ResourceLedgerStore.add_member`` 原先**每调一次就 save_groups 一次**，而
``save_groups`` 每次都「全量比较 changed + deepcopy 全组 + 单独 commit」→ 全站重建
（2039 颗种）实测 5 分钟（deepcopy 约 81s，2039 次 commit 占大头，O(n²)）。

改法：``add_member`` / ``set_library`` / ``set_identity`` 加 ``flush`` 参数；
``flush=False`` 时只换内存快照（``stage_groups``）不落盘，循环末尾 ``store.flush()`` 落一次。

本测试锁死四条不变量（都是**语义**，不是实现细节）：
  A. 批量结果 == 逐条结果（最终快照逐字节一致）；
  B. 批内 ``items()`` 立即可见（第二步读得到第一步的成员）；
  C. 批内**零落盘**，``flush()`` 只落一次；
  D. ``flush()`` 幂等；未 flush 的快照不会污染下一次 ``save_groups`` 的差异计算
     （``stage_groups`` 不许动 ``_group_prev``）。

用法：``python3 tools/test_ledger_batch.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import copy
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_ledger_batch_test"
CHECKS = 0


def _install_sqlalchemy_stub() -> None:
    """本机（无 app.*/无 sqlalchemy）也能跑。

    ``ledger.py`` 顶层只把 sqlalchemy 当**声明/表达式工具箱**用，本次测的
    ``add_member`` / ``flush`` 走的是内存 dict 路径，一条 SQL 都不发 —— 所以给一个
    占位 stub 足够，且**不会**让测试变成「测 stub」。
    """
    try:
        import sqlalchemy  # noqa: F401
        return
    except Exception:  # noqa: BLE001
        pass

    sa = types.ModuleType("sqlalchemy")

    class _Expr:
        def __init__(self, *a, **k):
            pass

        def __call__(self, *a, **k):
            return _Expr()

        def __getattr__(self, _n):
            return _Expr()

        def __eq__(self, _o):
            return _Expr()

        def __hash__(self):
            return id(self)

    class Mapped:
        def __class_getitem__(cls, item):
            return object

    def mapped_column(*_a, **_k):
        return _Expr()

    def _tool(*_a, **_k):
        return _Expr()

    for _n in ("JSON", "Boolean", "Float", "Integer", "String", "Text"):
        setattr(sa, _n, _Expr)
    sa.Mapped = Mapped
    sa.mapped_column = mapped_column
    for _n in ("select", "delete", "update", "text", "func", "inspect", "and_", "or_"):
        setattr(sa, _n, _tool)
    sys.modules["sqlalchemy"] = sa

    orm = types.ModuleType("sqlalchemy.orm")

    class DeclarativeBase:
        pass

    orm.DeclarativeBase = DeclarativeBase
    orm.Mapped = Mapped
    orm.mapped_column = mapped_column
    orm.relationship = _tool
    orm.sessionmaker = _tool
    sys.modules["sqlalchemy.orm"] = orm


def ok(cond, msg):
    global CHECKS
    CHECKS += 1
    if cond:
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        raise SystemExit(1)


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


_install_sqlalchemy_stub()
_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")


def _clean(v):
    return str(v or "").strip()


# 真模块优先；本机缺 app.* 时退化成带默认值的空壳。
# 这些常量/函数只在**运行期**参与拼装，本次测的 defer/flush 语义不依赖它们的具体取值，
# 但名字必须存在（``ledger.py`` 顶层 from-import）。
_STUB_ATTRS = {
    "common": {"task_is_participating": lambda _t: False},
    "dutyreg": {"DEFAULT_TASK_STATE": "静默", "TASK_DUTY": {}, "duty_id_of": lambda *a, **k: "",
                "duty_name": lambda *a, **k: "", "duty_state": lambda *a, **k: "静默"},
    "tags": {"LEASE_TTL": 600.0, "SILENT_NEW_TIMEOUT": 86400.0,
             "STATE_BONUS": "魔力", "STATE_BRUSH": "刷流", "STATE_SILENT": "静默",
             "STATES_WITH_SUB": ("静默",),
             "SUB_NEW": "新", "SUB_PLAIN": "普通", "SUB_RESOURCE": "资源",
             "_clean": _clean, "is_library_asset": lambda _r: False, "tag_for": lambda *a, **k: ""},
    "db": {},
}
for _sub, _rel in (("db", "db.py"), ("common", "common.py"),
                   ("dutyreg", "dutyreg.py"), ("tags", "features/tags.py")):
    try:
        _load(f"{PKG}.{_sub}", _rel)
    except Exception:  # noqa: BLE001  # 有 app.* 依赖的子模块，退化成带默认值的空壳
        _m = types.ModuleType(f"{PKG}.{_sub}")
        for _k, _v in (_STUB_ATTRS.get(_sub) or {}).items():
            setattr(_m, _k, _v)
        sys.modules[f"{PKG}.{_sub}"] = _m
        setattr(_pkg(PKG, ROOT), _sub, _m)


class FakeBackend:
    """只实现 ResourceLedgerStore 用到的三个口子，并记录落盘次数。"""

    def __init__(self, initial=None):
        self.groups = copy.deepcopy(initial or {})
        self._group_prev = copy.deepcopy(self.groups)
        self.saves = 0
        self.stages = 0

    def load_groups(self):
        return self.groups

    def stage_groups(self, data):
        self.stages += 1
        self.groups = dict(data or {})

    def save_groups(self, data):
        self.saves += 1
        self._group_prev = copy.deepcopy(dict(data or {}))
        self.groups = dict(data or {})


def main() -> int:
    ledger = _load(f"{PKG}.ledger", "ledger.py")
    store_cls = ledger.ResourceLedgerStore
    fp1 = "a" * 40
    fp2 = "b" * 40
    h1, h2, h3 = "1" * 40, "2" * 40, "3" * 40
    g1, g2 = f"fp:{fp1}", f"fp:{fp2}"

    def fresh():
        return store_cls(FakeBackend(), log=None)

    # ── A. 逐条 vs 批量结果一致 ───────────────────────────────────────
    print("[A] 批量结果 == 逐条结果")
    one_at_a_time = fresh()
    one_at_a_time.add_member(g1, h1, site="咖啡", size_gb=10.0, fp=fp1)
    one_at_a_time.add_member(g1, h2, site="财神", size_gb=10.0, fp=fp1)
    one_at_a_time.add_member(g2, h3, site="学校", size_gb=5.0, fp=fp2)
    one_at_a_time.set_library(g1, True)
    one_at_a_time.set_identity(g1, "资源", by="sync")

    batched = fresh()
    batched.add_member(g1, h1, site="咖啡", size_gb=10.0, fp=fp1, flush=False)
    batched.add_member(g1, h2, site="财神", size_gb=10.0, fp=fp1, flush=False)
    batched.add_member(g2, h3, site="学校", size_gb=5.0, fp=fp2, flush=False)
    batched.set_library(g1, True, flush=False)
    batched.set_identity(g1, "资源", by="sync", flush=False)
    batched.flush()

    ok(set(one_at_a_time.items()) == set(batched.items()), "组集合一致")
    for gid in batched.items():
        a = one_at_a_time.items()[gid]
        b = batched.items()[gid]
        ok(set(a.get("members") or {}) == set(b.get("members") or {}),
           f"{gid[:12]} 成员集合一致")
        ok(bool((a.get("library") or {}).get("in_library"))
           == bool((b.get("library") or {}).get("in_library")), f"{gid[:12]} 库记一致")
        ok(str(a.get("identity") or "") == str(b.get("identity") or ""),
           f"{gid[:12]} 身份一致")

    # ── B. 批内可见 ────────────────────────────────────────────────
    print("[B] 批内 items() 立即可见")
    live = fresh()
    live.add_member(g1, h1, site="咖啡", size_gb=10.0, fp=fp1, flush=False)
    mid = live.items().get(g1) or {}
    ok(mid.get("members"), "第一步后立刻能读到该组")
    live.add_member(g1, h2, site="财神", size_gb=10.0, fp=fp1, flush=False)
    mid2 = live.items().get(g1) or {}
    ok(len(mid2.get("members") or {}) == 2, "第二步看得到上一步的成员（没被覆盖）")
    live.flush()

    # ── C. 批内零落盘，flush 只落一次 ───────────────────────────────
    print("[C] 批内不落盘，flush 只落一次")
    cnt = fresh()
    before = cnt.backend.saves
    for i in range(50):
        cnt.add_member(g1, f"{i:040x}", site="咖啡", size_gb=1.0, fp=fp1, flush=False)
    ok(cnt.backend.saves == before, f"50 次 add_member 零落盘（saves={cnt.backend.saves}）")
    cnt.flush()
    ok(cnt.backend.saves == before + 1, f"flush 只落一次（saves={cnt.backend.saves}）")
    ok(len((cnt.backend.groups.get(g1) or {}).get("members") or {}) == 50, "50 个成员都在")

    # ── D. flush 幂等 + stage 不污染差异基线 ────────────────────────
    print("[D] flush 幂等 / stage 不动 _group_prev")
    idem = fresh()
    idem.add_member(g1, h1, site="咖啡", size_gb=10.0, fp=fp1, flush=False)
    prev_before = len(idem.backend._group_prev)
    idem.flush()
    saves1 = idem.backend.saves
    idem.flush()
    ok(idem.backend.saves == saves1, "空 flush 不再落盘（幂等）")

    guarded = fresh()
    guarded.add_member(g1, h1, site="咖啡", size_gb=10.0, fp=fp1, flush=False)
    ok(len(guarded.backend._group_prev) == prev_before,
       "stage 期间 _group_prev 保持落盘真值（否则 flush 比较不出差异）")
    guarded.flush()

    # ── E. 默认行为不变（不传 flush 仍然立即落盘）────────────────────
    print("[E] 默认仍逐次落盘（向后兼容）")
    legacy = fresh()
    s0 = legacy.backend.saves
    legacy.add_member(g1, h1, site="咖啡", size_gb=10.0, fp=fp1)
    ok(legacy.backend.saves == s0 + 1, "不传 flush → 立即落盘")

    print(f"\nPASS · {CHECKS} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
