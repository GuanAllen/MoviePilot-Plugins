#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 删除闸门「第 1~3 类硬保护」fail-closed 离线回归（★ P3，真跑 deletegate，不需 MoviePilot）。

缺陷（改动前，``features/deletegate.py::_delete_gate_detail``）：
  - 第 1 类「手动保留」：内层 ``except Exception: continue`` + 外层 ``except Exception: pass``；
  - 第 2 类「跨站来源份（H&R 保种期）」：``except Exception: pass``；
  - 第 3 类「已认领（保种承诺）」：``except Exception: pass``。
  三类都是「取不到保护集合 → 当作没有保护 → 函数正常返回（不抛）」，于是
  ``downloader_ops.delete_torrents`` 的外层 fail-closed（闸门抛异常 → 全阻断）**永远拦不到**；
  而删除的触发场景恰是磁盘清理 —— 方向是「保护变少」。

改动后口径：任一类取值失败 → ``logger.error`` 记具体异常 + 本批 hash **全部**按「被拦」返回
（理由前缀 ``保护集合读取失败(<类名>): <err>``）；内层单桶失败按**整类不可信**处理。

断言：
  A. ``store.get_protected_torrents`` 抛异常 → 全部被拦（零放行），理由带前缀 + 有 error 日志；
  B. ``_crossseed_source_hashes`` 抛异常 → 同上；
  C. ``_claim_protected_hashes`` 抛异常 → 同上；
  D. 内层单桶失败（某个 task_id 抛）→ 保守判定「整类不可信」→ 全部被拦；
  E. 正常路径回归：三类正常返回 → 受保护的被拦、不受保护的放行（逐条理由与改动前一致）；
  F. 第 4 类（欠 H&R 义务）现有行为不变（owed→拦 / 不 owed→放行 / 不在快照→放行）；
  G. 第 5 类豁免开关现有行为不变（``allow_asset`` / ``allow_strip_asset`` 只跳第 5 类，
     第 1~4 类照拦；且第 1~3 类读取失败时开关也救不了 —— fail-closed 优先）；
  H. 物理入口端到端：真 ``DownloaderAdapter.delete_torrents`` + 本闸门 —— 取值失败 → 假下载器
      **零调用**、返回 0；正常路径 → 照常删除（正向对照，证明没有「一律全拦」）。

用法：``python3 tools/test_p3_gate_failclosed_items.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_p3_failclosed_test"


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


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

# 桩 MoviePilot（common.py / downloader_ops.py 顶部依赖）；本测试不碰真 qB / 真数据。
for _name, _attrs in (
    ("app", {}),
    ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
    ("app.schemas", {"Response": type("Response", (), {})}),
    ("app.schemas.types", {"EventType": type("EventType", (), {})}),
    ("app.sdk", {}),
    ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
):
    _m = sys.modules.get(_name)
    if _m is None:
        _m = types.ModuleType(_name)
        sys.modules[_name] = _m
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)

for _modname, _attrs in (
    ("bonus", ("TorrentBonusInfo",)),
    ("fingerprint", ("Entry", "entries_fingerprint", "info_hash", "load_torrent_entries",
                     "total_size", "inner_fingerprint", "fingerprint")),
    ("fetcher", ("SiteCandidateTorrent",)),
    ("qbsync", ("QB_SYNC_INCREMENTAL", "get_qb_sync_store")),
):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    _m.get_qb_sync_store = lambda: None  # noqa: E731
    sys.modules[PKG + "." + _modname] = _m

common = _load(PKG + ".common", "common.py")
_tags = _load(PKG + ".tags", "tags.py")
dg = _load(PKG + ".features.deletegate", "features/deletegate.py")
dops = _load(PKG + ".downloader_ops", "downloader_ops.py")


# ---------------------------------------------------------------------------
# 测试桩：40 位 hex（与真 hash 同形，便于走 _delete_gate 的归一化分支）
# ---------------------------------------------------------------------------
H_MAN = "a1" * 20     # 手动保留
H_CS = "b2" * 20      # 跨站来源份
H_CL = "c3" * 20      # 已认领
H_HR = "d4" * 20      # 欠 H&R
H_LIB = "e5" * 20     # 库内资产
H_FREE = "f6" * 20    # 无保护

_PREFIX_MAN = "保护集合读取失败(手动保留): "
_PREFIX_CS = "保护集合读取失败(跨站来源份): "
_PREFIX_CL = "保护集合读取失败(已认领): "


class _TagStore:
    """账本桩：``items()`` + ``group_of()``（第 5 类用）。"""

    def __init__(self, items=None, group_of=None):
        self._it = dict(items or {})
        self._gf = group_of

    def items(self):
        return dict(self._it)

    def group_of(self, h):
        return self._gf(h) if callable(self._gf) else None


class _ProtStore:
    """手动保留账本桩：按 task_id 返回 protected；可全局抛 / 只让某个桶抛。"""

    def __init__(self, protected=None, boom=False, boom_tids=()):
        self._pt = {str(x).strip().lower() for x in (protected or set())}
        self._boom = bool(boom)
        self._boom_tids = set(boom_tids or ())

    def get_protected_torrents(self, tid):
        if self._boom:
            raise RuntimeError("protected store boom")
        if tid in self._boom_tids:
            raise RuntimeError(f"protected bucket boom: {tid!r}")
        return set(self._pt)


class Host(dg.DeleteGateMixin):
    """最小宿主：只带闸门需要的真值源，全部可注入故障。"""

    def __init__(self, *, protected=(), manual_boom=False, manual_boom_tids=(),
                 tasks=("t1",), crossseed=(), crossseed_boom=False,
                 claim=(), claim_boom=False, snap=None, ledger=None, hr_owed=False):
        self._store = _ProtStore(protected, manual_boom, manual_boom_tids)
        self._task_configs = {t: object() for t in tasks}
        self._cs = set(crossseed)
        self._cs_boom = bool(crossseed_boom)
        self._cl = set(claim)
        self._cl_boom = bool(claim_boom)
        self._snap = dict(snap or {})
        self._led = dict(ledger or {})
        self._hr_owed = bool(hr_owed)

    def _crossseed_source_hashes(self):
        if self._cs_boom:
            raise RuntimeError("crossseed boom")
        return set(self._cs)

    def _claim_protected_hashes(self):
        if self._cl_boom:
            raise RuntimeError("claim boom")
        return set(self._cl)

    def _tag_all_torrents(self):
        return dict(self._snap)

    def _tag_state(self):
        return _TagStore(self._led)

    def _tag_groups(self):
        return _TagStore({})

    def _resource_source_index(self):
        return {}

    def _hr_obligation(self, site, t, snap=None):  # noqa: ANN001
        if self._hr_owed:
            return (True, 72.0, 12.0, "hdsky")
        return (False, 0.0, 0.0, "")


def _torrent(h, progress=1.0):
    return types.SimpleNamespace(hash=h, title=h, state="pausedUP", size=1 << 30,
                                 tags=[], progress=progress, category="",
                                 save_path="/x", content_path=f"/x/{h}")


def _why(p, hs):
    return dict(p._delete_gate_detail(hs))


# ---------------------------------------------------------------------------
# 物理入口桩（H：端到端）
# ---------------------------------------------------------------------------
class _FakeQb:
    def __init__(self):
        self.calls: list = []

    def delete_torrents(self, ids=None, delete_file=False):  # noqa: D401
        self.calls.append((list(ids or []), bool(delete_file)))
        return True


def _adapter(gate, log_sink=None):
    """裸造真 ``DownloaderAdapter``（不过 __init__，避开 MP 环境）。"""
    dl = object.__new__(dops.DownloaderAdapter)
    dl._downloader = _FakeQb()
    dl.gate = gate
    # ★ 走生产缝：真实 ``_emit_delete_log`` 读 ``deletion_log`` 回调。旧写法直接替换
    #   ``_emit_delete_log`` 反而绕过了它，且 ``blocked`` 是**第 6 个位置参数**（非关键字）。
    dl.deletion_log = (lambda *a, **k: log_sink.append((a, k))) if log_sink is not None else None
    dl._shared_file_hashes = lambda hs: set()
    dl.reannounce = lambda hs: (0, None)
    return dl


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.messages: list = []

    def emit(self, record):
        try:
            self.messages.append(record.getMessage())
        except Exception:  # noqa: BLE001
            pass


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def main() -> int:
    print("=" * 68)
    print("魔流 · 删除闸门前三类硬保护 fail-closed（P3）")
    print("=" * 68)

    # ---- A. 手动保留：store.get_protected_torrents 抛异常 → 全批被拦 ----
    print("\n[A] 手动保留：账本读取抛异常 → 本批全部被拦（零放行）+ error 日志")
    cap = _Capture()
    dg.logger.addHandler(cap)
    try:
        p = Host(protected={H_MAN}, manual_boom=True)
        w = _why(p, [H_FREE, H_MAN])
    finally:
        dg.logger.removeHandler(cap)
    _ok(set(w.keys()) == {H_FREE, H_MAN}, f"本批 2 个 hash 全部出现在返回字典（实际 {sorted(w)}）")
    _ok(all(str(v).startswith(_PREFIX_MAN) for v in w.values()),
        f"理由都带前缀「{_PREFIX_MAN.strip()}」（实际 {w}）")
    _ok(all("RuntimeError" in str(v) and "boom" in str(v) for v in w.values()),
        "理由带具体异常类型 + 消息（RuntimeError / boom）")
    _ok(p._delete_gate([H_FREE]) == {H_FREE}, "_delete_gate 同口径：返回集合 = 全批（零放行）")
    _ok(p._delete_gate_manual([H_FREE]) == {H_FREE}, "_delete_gate_manual 同样全拦（豁免开关救不了）")
    _ok(p._delete_gate_strip([H_FREE]) == {H_FREE}, "_delete_gate_strip 同样全拦")
    _ok(any("保护集合读取失败" in m and "手动保留" in m and "RuntimeError" in m
            for m in cap.messages), f"logger.error 记录了具体异常（{cap.messages}）")

    # ---- B. 跨站来源份：抛异常 → 全批被拦 ----
    print("\n[B] 跨站来源份：_crossseed_source_hashes 抛异常 → 本批全部被拦")
    p = Host(protected=set(), crossseed_boom=True)
    w = _why(p, [H_FREE, H_CS])
    _ok(set(w.keys()) == {H_FREE, H_CS}, f"本批 2 个 hash 全部被拦（实际 {sorted(w)}）")
    _ok(all(str(v).startswith(_PREFIX_CS) for v in w.values()), f"理由带跨站前缀（实际 {w}）")

    # ---- C. 已认领：抛异常 → 全批被拦 ----
    print("\n[C] 已认领：_claim_protected_hashes 抛异常 → 本批全部被拦")
    p = Host(protected=set(), claim_boom=True)
    w = _why(p, [H_FREE, H_CL])
    _ok(set(w.keys()) == {H_FREE, H_CL}, f"本批 2 个 hash 全部被拦（实际 {sorted(w)}）")
    _ok(all(str(v).startswith(_PREFIX_CL) for v in w.values()), f"理由带已认领前缀（实际 {w}）")

    # ---- D. 内层单桶失败：保守 = 整类不可信 ----
    print("\n[D] 手动保留：单个 task 桶读失败 → 整类不可信 → 全批被拦（保守选择）")
    p = Host(protected=set(), tasks=("t1", "t2"), manual_boom_tids=("t2",))
    w = _why(p, [H_FREE, H_MAN])
    _ok(set(w.keys()) == {H_FREE, H_MAN},
        "任一桶失败 = 并集不完整（无法知道失败桶里有没有本批 hash）→ 全批被拦")
    _ok(all(str(v).startswith(_PREFIX_MAN) for v in w.values()), "理由同样是读取失败前缀")

    # ---- E. 正常路径回归（与改动前逐条一致） ----
    print("\n[E] 正常路径回归：三类正常返回 → 受保护被拦 / 不受保护放行")
    p = Host(protected={H_MAN}, crossseed={H_CS}, claim={H_CL})
    w = _why(p, [H_MAN, H_CS, H_CL, H_FREE])
    _ok(w.get(H_MAN) == "手动保留", f"手动保留 → 拦（{w.get(H_MAN)!r}）")
    _ok(w.get(H_CS) == "跨站来源份（H&R 保种期）", f"跨站来源份 → 拦（{w.get(H_CS)!r}）")
    _ok(w.get(H_CL) == "已认领（保种承诺）", f"已认领 → 拦（{w.get(H_CL)!r}）")
    _ok(H_FREE not in w, "无保护种 → 放行（不出现）")
    _ok(len(w) == 3, f"恰好 3 个被拦（实际 {len(w)}）")

    # ---- F. 第 4 类（欠 H&R 义务）行为不变 ----
    print("\n[F] 第 4 类（欠 H&R 义务）现有行为不变")
    p = Host(snap={H_HR: _torrent(H_HR)}, hr_owed=True)
    w = _why(p, [H_HR, H_FREE])
    _ok(H_HR in w and "欠 H&R 义务" in w[H_HR], f"欠义务 → 拦（{w.get(H_HR)!r}）")
    _ok(w.get(H_HR) == "欠 H&R 义务（hdsky·未挂满 12.0/72.0h）", "理由串逐字不变")
    _ok(H_FREE not in w, "不在快照的种不因第 4 类被拦（未变）")
    p2 = Host(snap={H_HR: _torrent(H_HR)}, hr_owed=False)
    _ok(H_HR not in _why(p2, [H_HR]), "不欠义务 → 放行（未变）")

    # ---- G. 第 5 类豁免开关行为不变（只跳第 5 类） ----
    print("\n[G] 第 5 类（库内资产）豁免开关：只跳第 5 类，第 1~4 类照拦")
    ledger = {H_LIB: {"site": "s", "sub": "资源", "state": "静默"}}
    p = Host(protected={H_MAN}, crossseed={H_CS}, claim={H_CL}, ledger=ledger,
             snap={H_HR: _torrent(H_HR)}, hr_owed=True)
    hs = [H_MAN, H_CS, H_CL, H_HR, H_LIB, H_FREE]
    strict = _why(p, hs)
    _ok(strict.get(H_LIB) == "库内资产（已入库，永不删）", f"严格闸门：库内资产被拦（{strict.get(H_LIB)!r}）")
    _ok(all(strict.get(h) for h in (H_MAN, H_CS, H_CL, H_HR)), "严格闸门：第 1~4 类照拦")
    _ok(H_FREE not in strict, "严格闸门：无保护种放行")
    _manual = dict(p._delete_gate_detail(hs, allow_asset=True))
    _strip = dict(p._delete_gate_detail(hs, allow_strip_asset=True))
    _ok(H_LIB not in _manual, "allow_asset=True → 只放行库内资产")
    _ok(H_LIB not in _strip, "allow_strip_asset=True → 只放行库内资产")
    _ok(all(_manual.get(h) for h in (H_MAN, H_CS, H_CL, H_HR)),
        "allow_asset=True → 第 1~4 类照拦（未变）")
    _ok(all(_strip.get(h) for h in (H_MAN, H_CS, H_CL, H_HR)),
        "allow_strip_asset=True → 第 1~4 类照拦（未变）")
    _ok(p._delete_gate_manual(hs) == set(_manual.keys()),
        "_delete_gate_manual == detail(allow_asset=True).keys()")
    _ok(p._delete_gate_strip(hs) == set(_strip.keys()),
        "_delete_gate_strip == detail(allow_strip_asset=True).keys()")
    # fail-closed 优先于豁免开关
    p_bad = Host(protected={H_MAN}, manual_boom=True, ledger=ledger)
    _ok(set(p_bad._delete_gate_detail(hs, allow_asset=True).keys()) == set(hs),
        "读取失败时 allow_asset 也救不了：本批仍全部被拦")
    _ok(set(p_bad._delete_gate_detail(hs, allow_strip_asset=True).keys()) == set(hs),
        "读取失败时 allow_strip_asset 也救不了：本批仍全部被拦")

    # ---- H. 物理入口端到端（真 DownloaderAdapter + 真闸门） ----
    print("\n[H] 物理入口端到端：闸门取值失败 → 假下载器零调用、返回 0；正常路径照删")
    log_sink: list = []
    p_bad = Host(protected={H_MAN}, manual_boom=True)
    ad = _adapter(p_bad._delete_gate, log_sink)
    n, err = ad.delete_torrents(hashes=[H_MAN, H_FREE], delete_file=False,
                                reason="p3-test", source="p3-test")
    _ok(n == 0, f"返回 0（实际 {n}）")
    _ok(ad._downloader.calls == [], f"假下载器零调用（实际 {ad._downloader.calls}）")
    _ok(bool(log_sink), "统一台账回调被调用（记录了 blocked）")
    if log_sink:
        _a = log_sink[-1][0]
        _blocked = list(_a[5] or []) if len(_a) > 5 else []
        _ok(len(_blocked) == 2, f"台账 blocked 记了全批 2 个（实际 {_blocked}）")
        _ok(list(_a[0]) == [], f"台账 hashes 为空（不谎报删除，实际 {_a[0]!r}）")

    p_ok = Host(protected={H_MAN})
    ad2 = _adapter(p_ok._delete_gate)
    n2, err2 = ad2.delete_torrents(hashes=[H_MAN, H_FREE], delete_file=False,
                                   reason="p3-test", source="p3-test")
    _ok(n2 == 1, f"正常路径：只删无保护的 1 个（实际 {n2}）")
    _ok(len(ad2._downloader.calls) == 1 and ad2._downloader.calls[0][0] == [H_FREE],
        f"正常路径：仅 H_FREE 被物理删除（实际 {ad2._downloader.calls}）")

    print("\n" + "=" * 68)
    print(f"PASS：{CHECKS} 项断言全部通过 ✅")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"\n{e}")
        raise SystemExit(1)
