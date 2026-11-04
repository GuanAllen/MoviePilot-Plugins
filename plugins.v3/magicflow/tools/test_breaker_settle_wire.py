#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 19.10.5 熔断补记「接线」离线回归（deletegate ⇄ downloader_ops）。

``tools/test_breach_breaker.py`` 的 B2 段只验 ``deletegate`` 内部的预占/归还数学；
本测试验的是**另一件事**：``downloader_ops.delete_torrents`` 的三个出口是否真的把
票根结算了 —— 只改一侧、另一侧没接上，B2 全绿而线上依旧虚高，这类问题只能靠接线测试抓。

覆盖（每条断言窗口里剩多少个，就是「这次真实消失的种子数」）：
  1. 全部删成功           → 窗口 = 实删数（不多不少）
  2. 下载器全部返回失败    → 窗口 = 0（失败不占额度）
  3. 账单断言整批拦下      → 窗口 = 0（没删成不占额度）
  4. 部分被拦（3 申请 1 拦）→ 窗口 = 2（只记实删）
  5. 删除过程抛异常        → 窗口 = 0
  6. 闸门整批拦下          → 窗口 = 0（且根本没有预占）
  7. 窗口已满 → 熔断       → 窗口不变（熔断路径不 pre-reserve）
  8. 票根表最终清空        → 没有泄漏（每次结算都会 pop）

用法：``python tools/test_breaker_settle_wire.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_settle_wire_test"
CHECKS = 0


def ok(cond, msg):
    global CHECKS
    CHECKS += 1
    if cond:
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        raise SystemExit(1)


def _pkg(name, path):
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")

# 桩 MoviePilot（common / downloader_ops / deletegate 顶部依赖）
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
    ("bonus", ("TorrentBonusInfo", "calc_bonus_per_hour")),
    ("fingerprint", ("Entry", "entries_fingerprint", "info_hash", "load_torrent_entries",
                     "total_size", "inner_fingerprint", "fingerprint")),
    ("fetcher", ("SiteCandidateTorrent",)),
    ("qbsync", ("QB_SYNC_INCREMENTAL",)),
):
    _m = types.ModuleType(PKG + "." + _modname)
    for _a in _attrs:
        setattr(_m, _a, object)
    _m.get_qb_sync_store = lambda: None  # noqa: E731
    sys.modules[PKG + "." + _modname] = _m

common = _load(PKG + ".common", "common.py")
_load(PKG + ".tags", "tags.py")
dops = _load(PKG + ".downloader_ops", "downloader_ops.py")
dg = _load(PKG + ".features.deletegate", "features/deletegate.py")


class FakeDownloader:
    """假下载器：``mode`` = ok（恒成功）/ fail（恒返回 False）/ boom（抛异常）。"""

    def __init__(self, mode="ok"):
        self.mode = mode
        self.calls = []

    def delete_torrents(self, ids=None, delete_file=False, **_kw):
        self.calls.append((list(ids or []), bool(delete_file)))
        if self.mode == "boom":
            raise RuntimeError("下载器会话失效（模拟）")
        return self.mode != "fail"


class Host(dg.DeleteGateMixin, dops.DownloaderAdapter):
    """最小宿主：删种链路 + 熔断混入，其余钩子全部打桩。"""

    def __init__(self, mode="ok", bills=(), gate_all=False):
        self._downloader = FakeDownloader(mode)
        self._bills = {str(b).lower() for b in bills}
        self._gate_all = bool(gate_all)
        self.rows = []
        self._tmp = Path(tempfile.mkdtemp(prefix="settle_wire_"))

    # --- 闸门 / 台账 / 报到 ---
    def gate(self, hashes):  # noqa: ANN001
        hs = [str(h or "").strip().lower() for h in (hashes or [])]
        return set(hs) if self._gate_all else set()

    def reannounce(self, hashes):  # noqa: ANN001
        return len(hashes or []), None

    def deletion_log(self, hashes, delete_file, reason, source, error,
                     blocked, blocked_by=""):
        self.rows.append({"hashes": list(hashes or []), "blocked": list(blocked or []),
                          "blocked_by": blocked_by, "error": error})

    # --- 删除前依赖 ---
    def _shared_file_hashes(self, hashes):  # noqa: ANN001
        return set()

    def _delete_bill_assert(self, hashes):  # noqa: ANN001
        return {h: "欠 H&R 账单（测试桩）" for h in hashes if str(h).lower() in self._bills}

    def get_data_path(self):
        return self._tmp


def _win():
    return len(dg._DELETE_WINDOW)


def _tickets():
    return len(dg._DELETE_WINDOW_TICKETS)


def _reset():
    dg._DELETE_WINDOW.clear()
    dg._DELETE_WINDOW_TICKETS.clear()


def main() -> int:
    print("=" * 64)
    print("魔流 · 熔断补记接线测试（deletegate ⇄ downloader_ops）")
    print("=" * 64)
    mx = int(common.DELETE_BREAKER_MAX)

    print("\n[1] 全部删成功 → 窗口 = 实删数")
    _reset()
    h = Host()
    n, err = h.delete_torrents(["a1", "a2", "a3"], delete_file=True, reason="r", source="test")
    ok(n == 3 and err is None, f"删成功 3 个（n={n} err={err}）")
    ok(_win() == 3, f"窗口=3（实删 3，实际 {_win()}）")
    ok(_tickets() == 0, "票根已结算清空")

    print("\n[2] 下载器全部返回失败 → 窗口 = 0")
    _reset()
    h = Host(mode="fail")
    n, err = h.delete_torrents(["b1", "b2"], delete_file=True, reason="r", source="test")
    ok(n == 0, "一个都没删成（n=0）")
    ok(_win() == 0, f"失败不占额度（窗口={_win()}）")
    ok(_tickets() == 0, "票根已归还")

    print("\n[3] 账单断言整批拦下 → 窗口 = 0")
    _reset()
    h = Host(bills={"c1", "c2"})
    n, err = h.delete_torrents(["c1", "c2"], delete_file=True, reason="r", source="test")
    ok(n == 0 and "断言" in str(err), f"整批被断言拦下（err={err}）")
    ok(_win() == 0, f"没删成不占额度（窗口={_win()}）")
    ok(_tickets() == 0, "票根已归还")

    print("\n[4] 部分被拦（申请 3、拦 1）→ 窗口 = 2")
    _reset()
    h = Host(bills={"d2"})
    n, err = h.delete_torrents(["d1", "d2", "d3"], delete_file=True, reason="r", source="test")
    ok(n == 2, f"删成 2 个（n={n}）")
    ok(_win() == 2, f"只记实删 2（窗口={_win()}）")

    print("\n[5] 删除过程抛异常 → 窗口 = 0")
    _reset()
    h = Host(mode="boom")
    n, err = h.delete_torrents(["e1", "e2"], delete_file=True, reason="r", source="test")
    ok(n == 0 and err, f"异常被兜住（err={err}）")
    ok(_win() == 0, f"整批异常全还（窗口={_win()}）")
    ok(_tickets() == 0, "票根已归还")

    print("\n[6] 闸门整批拦下 → 窗口 = 0（且没有预占）")
    _reset()
    h = Host(gate_all=True)
    n, err = h.delete_torrents(["f1", "f2"], delete_file=True, reason="r", source="test")
    ok(n == 0, "闸门拦下全部")
    ok(_win() == 0 and _tickets() == 0, "连预占都没发生（窗口=0，票根=0）")

    print("\n[7] 窗口已满 → 熔断：窗口不变、不发票根")
    _reset()
    import time as _t
    dg._DELETE_WINDOW.extend([_t.time()] * mx)   # 直接塞满（当前时间戳，保证不过期）
    h = Host()
    n, err = h.delete_torrents(["g1"], delete_file=True, reason="r", source="test")
    ok(n == 0 and "熔断" in str(err), f"整批被熔断（err={err}）")
    ok(_win() == mx, f"熔断路径不预占（窗口仍 {mx}，实际 {_win()}）")
    ok(_tickets() == 0, "没有产生票根")

    print("\n[8] 连续 5 批各删 2 个 → 窗口 = 10、票根无泄漏")
    _reset()
    h = Host()
    for i in range(5):
        h.delete_torrents([f"h{i}a", f"h{i}b"], delete_file=True, reason="r", source="test")
    ok(_win() == 10, f"窗口=10（实际 {_win()}）")
    ok(_tickets() == 0, "5 次结算后票根表为空（无泄漏）")

    _reset()
    print("\n" + "=" * 64)
    print(f"PASS：{CHECKS} 项断言全部通过 ✅")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"\n{e}")
        raise SystemExit(1)
