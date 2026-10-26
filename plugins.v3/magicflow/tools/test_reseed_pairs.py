#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 全站辅种「配对」离线回归测试（真跑，无需 MoviePilot，零网络/零写）。

覆盖 19.7.92 的三处改动 + 原有配对口径：
  (a) 同轮同站同一目标 info_hash **只取一对**（原先同轮重挂 2~5 次、qB 空操作却吃 daily）
  (b) 目标体积预筛：mf_rss.size（GB）在体积线以下的目标提前跳过；**没有体积数据的站不筛**
  (c) 体积线可被 `min_gb` 覆盖（`reseed_round` 自动降档复算的钩子）
  (d) 原有口径不回归：未下完的源不做源 / 台账命中跳过 / daily 上限跳过 / 跨站同资源照排

用法：``python3 tools/test_reseed_pairs.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


# ------------------------------------------------------------------ 离线加载
def _stub_app() -> None:
    import logging as _logging

    app = types.ModuleType("app")
    app.__path__ = []
    sys.modules.setdefault("app", app)
    sdk = types.ModuleType("app.sdk")
    sdk.__path__ = []
    sys.modules.setdefault("app.sdk", sdk)
    logmod = types.ModuleType("app.sdk.logging")
    logmod.logger = _logging.getLogger("magicflow-test")
    sys.modules.setdefault("app.sdk.logging", logmod)
    schemas = types.ModuleType("app.schemas")
    schemas.__path__ = []
    schemas.Response = type("Response", (), {})
    sys.modules.setdefault("app.schemas", schemas)
    stypes = types.ModuleType("app.schemas.types")

    class _EventType:
        def __getattr__(self, _n):
            return _n

    stypes.EventType = _EventType()
    sys.modules.setdefault("app.schemas.types", stypes)
    events = types.ModuleType("app.sdk.events")

    class _EventManager:
        def __getattr__(self, _n):
            return lambda *a, **k: None

    events.eventmanager = _EventManager()
    sys.modules.setdefault("app.sdk.events", events)


def _stub_sqlalchemy() -> None:
    """宿主没装 sqlalchemy（只活在 MoviePilot 容器里）→ 顶层 import 用最小桩。"""
    if "sqlalchemy" in sys.modules:
        return
    sa = types.ModuleType("sqlalchemy")
    sa.select = lambda *a, **k: None
    sa.delete = lambda *a, **k: None
    sa.update = lambda *a, **k: None
    sa.insert = lambda *a, **k: None
    sa.text = lambda *a, **k: None
    sa.and_ = lambda *a, **k: None
    sa.or_ = lambda *a, **k: None
    sa.desc = lambda *a, **k: None
    sa.inspect = lambda *a, **k: None
    sa.func = types.SimpleNamespace(max=lambda *a, **k: None, count=lambda *a, **k: None)
    for _t in ("JSON", "Boolean", "Float", "Integer", "String", "Text", "BigInteger", "DateTime"):
        setattr(sa, _t, lambda *a, **k: None)
    orm = types.ModuleType("sqlalchemy.orm")
    orm.DeclarativeBase = type("DeclarativeBase", (), {})
    orm.Mapped = object
    orm.mapped_column = lambda *a, **k: None
    orm.relationship = lambda *a, **k: None
    orm.sessionmaker = lambda *a, **k: None
    sa.orm = orm
    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.orm"] = orm


def _load_reseed():
    _stub_app()
    _stub_sqlalchemy()
    pkg = types.ModuleType("mf_reseed_pairs_test")
    pkg.__path__ = [str(ROOT)]
    sys.modules.setdefault("mf_reseed_pairs_test", pkg)
    feat = types.ModuleType("mf_reseed_pairs_test.features")
    feat.__path__ = [str(ROOT / "features")]
    sys.modules.setdefault("mf_reseed_pairs_test.features", feat)
    spec = importlib.util.spec_from_file_location("mf_reseed_pairs_test.features.reseed",
                                                  ROOT / "features" / "reseed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mf_reseed_pairs_test.features.reseed"] = mod
    spec.loader.exec_module(mod)
    return mod


reseed = _load_reseed()
ReSeedMixin = reseed.ReSeedMixin

GB = 1024 ** 3


def _torrent(h, size_gb=2.0, progress=1.0):
    return types.SimpleNamespace(hash=str(h).lower(), progress=progress,
                                 size=float(size_gb) * GB, title="T", save_path="/dl")


class _PairHost(ReSeedMixin):
    """只需 `_reseed_pairs` 依赖的几个注入点（其余真方法不碰）。"""

    def __init__(self, cfg=None, ledger=None, day_sites=None, sizes=None):
        self._cfg = dict(cfg or {"min_size_gb": 1.0, "daily": 30, "batch": 10})
        self._ledger = dict(ledger or {})
        self._day = {"day": time.strftime("%Y-%m-%d"), "sites": dict(day_sites or {})}
        self._sizes = dict(sizes or {})

    def _reseed_cfg(self):
        return dict(self._cfg)

    def _reseed_ledger(self):
        return dict(self._ledger)

    def _reseed_day(self):
        return {"day": self._day["day"], "sites": dict(self._day["sites"])}

    def _rss_sizes(self, site_id, tids):
        return dict(self._sizes.get(int(site_id)) or {})


def _row(ih, sid, tid):
    return {"info_hash": ih, "sid": sid, "torrent_id": tid}


_SITE_MAP = {17: {"name": "HDDolby", "site_id": 17, "domain": "hddolby.com"},
             18: {"name": "织梦", "site_id": 18, "domain": "zmpt.cc"}}
_H1 = "a1" * 20
_H2 = "b2" * 20


def main() -> int:  # noqa: WPS231
    print("=" * 66)
    print("魔流 · 全站辅种配对离线回归（19.7.92）")
    print("=" * 66)

    # ---------------------------------------------------------------- (a) 同轮去重
    print("\n(a) 同轮同站同一目标 info_hash 只取一对")
    src = "c3" * 20
    cloud = {"by_hash": {src: [_row(_H1, 17, 1), _row(_H1, 17, 2), _row(_H1, 17, 3)]}}
    st: dict = {}
    hv = _PairHost()
    pairs = hv._reseed_pairs(cloud, {src: _torrent(src)}, _SITE_MAP, stats=st)
    _ok(len(pairs) == 1, f"3 行同目标 → 只排 1 对（实际 {len(pairs)}）")
    _ok(int(st.get("dup") or 0) == 2, f"重复行计数 dup=2（实际 {st.get('dup')}）")
    _ok(pairs[0]["tid"] == 1, "保留第一行（tid 顺序稳定）")

    print("\n(b) 跨站同 info_hash 不算重复（同资源去两站落户是正当的）")
    cloud = {"by_hash": {src: [_row(_H1, 17, 1), _row(_H1, 18, 9)]}}
    st = {}
    pairs = _PairHost()._reseed_pairs(cloud, {src: _torrent(src)}, _SITE_MAP, stats=st)
    _ok(len(pairs) == 2, f"17/18 两站各取一对（实际 {len(pairs)}）")
    _ok(not st.get("dup"), "跨站不记 dup")

    # ---------------------------------------------------------------- (b) 目标体积预筛
    print("\n(c) 目标体积预筛（mf_rss.size，GB）")
    cloud = {"by_hash": {src: [_row(_H1, 17, 1), _row(_H2, 17, 2)]}}
    st = {}
    hv = _PairHost(sizes={17: {"1": 0.4, "2": 3.0}})
    pairs = hv._reseed_pairs(cloud, {src: _torrent(src)}, _SITE_MAP, stats=st)
    _ok([p["tid"] for p in pairs] == [2], f"0.4GB 目标被筛掉、留 3.0GB（实际 {[p['tid'] for p in pairs]}）")
    _ok(int(st.get("tgt_small") or 0) == 1, "tgt_small 计数=1")
    _ok(abs(float(st.get("tgt_max_gb") or 0) - 0.4) < 1e-6, "tgt_max_gb=0.4（自动降档要用）")

    print("\n(d) 没有体积数据的站**不筛**（其余 12 站 size 为空 → 行为与本改动前一致）")
    st = {}
    pairs = _PairHost(sizes={})._reseed_pairs(cloud, {src: _torrent(src)}, _SITE_MAP, stats=st)
    _ok(len(pairs) == 2, f"无 size 数据 → 两行都留（实际 {len(pairs)}）")
    _ok(not st.get("tgt_small"), "无数据不记 tgt_small")

    print("\n(e) size=0/None 的行不当作「小体积」误杀")
    st = {}
    pairs = _PairHost(sizes={17: {"1": 0.0, "2": None}})._reseed_pairs(
        cloud, {src: _torrent(src)}, _SITE_MAP, stats=st)
    _ok(len(pairs) == 2, f"size=0/None → 都留（实际 {len(pairs)}）")

    # ---------------------------------------------------------------- (c) 体积线覆盖
    print("\n(f) 源体积线可被 min_gb 覆盖（自动降档钩子）")
    cloud = {"by_hash": {src: [_row(_H1, 17, 1)]}}
    st = {}
    pairs = _PairHost(cfg={"min_size_gb": 1.0, "daily": 30, "batch": 10})._reseed_pairs(
        cloud, {src: _torrent(src, size_gb=0.5)}, _SITE_MAP, stats=st)
    _ok(pairs == [], "0.5GB 源在 1.0GB 线下 → 排不出")
    _ok(int(st.get("src_small") or 0) == 1, "src_small 计数=1")
    _ok(abs(float(st.get("src_max_gb") or 0) - 0.5) < 1e-6, "src_max_gb=0.5（降档目标线）")
    st = {}
    pairs = _PairHost()._reseed_pairs(cloud, {src: _torrent(src, size_gb=0.5)}, _SITE_MAP,
                                      min_gb=0.5, stats=st)
    _ok(len(pairs) == 1, "min_gb=0.5 复算 → 排出 1 对（降档生效）")

    print("\n(g) 体积线 0 = 不筛（配置关掉体积线时行为不变）")
    st = {}
    pairs = _PairHost(cfg={"min_size_gb": 0, "daily": 30, "batch": 10})._reseed_pairs(
        cloud, {src: _torrent(src, size_gb=0.01)}, _SITE_MAP, stats=st)
    _ok(len(pairs) == 1, "min_size_gb=0 → 小种也排")
    _ok(not st.get("src_small"), "不记 src_small")

    # ---------------------------------------------------------------- (d) 原口径不回归
    print("\n(h) 浮点安全：降档线取「最大被拦候选 − 1MB」时，那颗候选必须真的排得出来")
    cloud = {"by_hash": {src: [_row(_H1, 17, 1)]}}
    _s = 0.954  # 现场最大被拦源（bytes→GB→bytes 往返的临界值）
    _d = round(_s - 0.001, 3)
    st = {}
    pairs = _PairHost()._reseed_pairs(cloud, {src: _torrent(src, size_gb=_s)}, _SITE_MAP,
                                      min_gb=_d, stats=st)
    _ok(len(pairs) == 1, f"{_s}GB 源在降档线 {_d}GB 下排出 1 对")
    _ok(pairs and abs(float(pairs[0]["src_size"]) - _s * GB) < 1.0, "源体积原样带进配对（未被改写）")

    print("\n(i) 原有口径不回归")
    cloud = {"by_hash": {src: [_row(_H1, 17, 1)]}}
    pairs = _PairHost()._reseed_pairs(cloud, {src: _torrent(src, progress=0.87)}, _SITE_MAP)
    _ok(pairs == [], "未下完的源（progress 0.87）不能当辅种源")

    pairs = _PairHost()._reseed_pairs(cloud, {}, _SITE_MAP)
    _ok(pairs == [], "本机没这颗源 → 跳过")

    pairs = _PairHost(ledger={f"17:{_H1}": {"st": "miss"}})._reseed_pairs(
        cloud, {src: _torrent(src)}, _SITE_MAP)
    _ok(pairs == [], "台账命中（miss）→ 跳过")

    pairs = _PairHost(day_sites={"17": 30})._reseed_pairs(cloud, {src: _torrent(src)}, _SITE_MAP)
    _ok(pairs == [], "daily=30 已用满 → 跳过")

    cloud = {"by_hash": {src: [_row(_H1, 17, 1)]}}
    local = {src: _torrent(src), _H1: _torrent(_H1)}
    pairs = _PairHost()._reseed_pairs(cloud, local, _SITE_MAP)
    _ok(pairs == [], "目标在本机已有 → 跳过")

    print("\n" + "=" * 66)
    print(f"PASS：{CHECKS} 项断言全部通过 ✅")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"\n{e}")
        raise SystemExit(1)
