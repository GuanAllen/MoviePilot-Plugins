#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 挂种健康度自检离线回归（★ 12.5.0，真跑 features/health.py，不需 MoviePilot）。

背景：两段式（顶层 listing 粗筛 → 逐文件 os.path.exists 精确）找出「qB 报完成但盘上
找不到数据」的空转种（ghost）/ 缺文件种（partial），并标出其中还欠 H&R 的风险种。
本测试直接加载真 ``features/health.py``（合成父包解相对导入），断言：
  1) 正常种（顶层名在 listing）→ 不误报（bucket=normal，不核盘）；
  2) ghost（0 文件）→ bucket=ghost、files_exist=0、files_total=N；
  3) partial（部分缺）→ bucket=partial、0<exist<total；
  4) 数据在临时目录（temp）→ 不算 ghost（粗筛命中 temp listing → normal）；
  5) site 过滤：只回该站；
  6) only 过滤：only=ghost 只回 ghost；
  7) 汇总数 / 体积 / by_site 正确；
  8) hr_at_risk（ghost 且账单 active/breached）+ not_in_qb（账单在册但 qB 无种）；
  9) **零写调用**：下载器/账本/账本 store 全部无写动作；
  10) 候选上限截断（max_probe 生效，标 probe_truncated）。

用法：``python3 tools/test_health_scan.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_health_scan_test"


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


def _stub_app() -> None:
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
        ("bonus", ("TorrentBonusInfo",)),
        ("fingerprint", ("fingerprint", "inner_fingerprint", "info_hash",
                         "Entry", "entries_fingerprint", "load_torrent_entries", "total_size")),
        ("fetcher", ("SiteCandidateTorrent",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m


_stub_app()
_common = _load(PKG + ".common", "common.py")

# 桩 hrbills：health.py 只从它 import 4 个常量
_hrbills = types.ModuleType(PKG + ".features.hrbills")
_hrbills.BILL_STATE_ACTIVE = "active"
_hrbills.BILL_STATE_BREACHED = "breached"
_hrbills.RULE_SITE_HR = "site_hr"
_hrbills.RULE_HIT_AND_RUN = "hit_and_run"
sys.modules[PKG + ".features.hrbills"] = _hrbills

health = _load(PKG + ".features.health", "features/health.py")


class FakeTorrent:
    def __init__(self, hash, title, state="stalledUP", save_path="", content_path="",
                 progress=1.0, size_gb=1.0, tags=None, tracker=""):
        self.hash = hash
        self.title = title
        self.state = state
        self.save_path = save_path
        self.content_path = content_path
        self.progress = progress
        self.size_gb = size_gb
        self.size = size_gb * (1024 ** 3)
        self.tags = list(tags or [])
        self.tracker = tracker


class _WriteGuard:
    """任何未定义的（= 写）方法调用都会被记进 write_log。"""

    def __init__(self):
        self.write_log = []

    def __getattr__(self, name):
        def _rec(*a, **k):
            self.write_log.append(name)
            return None
        return _rec


class FakeDl(_WriteGuard):
    def __init__(self, files=None, prefs=None):
        super().__init__()
        self._files = dict(files or {})
        self._prefs = dict(prefs or {})

    def get_file_entries(self, h):
        return list(self._files.get(h, []))

    def get_app_preferences(self):
        return dict(self._prefs), None


class FakeBills(_WriteGuard):
    def __init__(self, bills=None):
        super().__init__()
        self._bills = dict(bills or {})

    def get(self, h):
        return self._bills.get(h)

    def all(self):
        return dict(self._bills)


class FakeStore(_WriteGuard):
    def __init__(self, protected=None):
        super().__init__()
        self._protected = dict(protected or {})

    def get_protected_torrents(self, tid):
        return set(self._protected.get(tid, set()))


class Plug(health.HealthMixin):
    def __init__(self, snap=None, dl=None, bills=None, protected=None, site_map=None):
        self._snap = dict(snap or {})
        self._dl = dl
        self._bills = FakeBills(bills) if bills is not None else FakeBills()
        self._store = FakeStore(protected) if protected is not None else FakeStore()
        self._task_configs = {}
        self._site_map = dict(site_map or {})

    def _tag_all_torrents(self):
        return self._snap

    def _get_downloader(self):
        return self._dl

    def _hrbills_store(self):
        return self._bills

    def _torrent_site_name(self, tags):
        for t in (tags or []):
            if str(t) in self._site_map:
                return str(t)
        return ""

    def _site_domain_by_name(self, name):
        return self._site_map.get(str(name or "").strip(), "")

    def _log(self, msg, level="info"):
        pass


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _scan(p, **kw):
    return p._health_scan(**kw)


def main() -> int:
    print("== 挂种健康度自检（12.5.0）==")

    with tempfile.TemporaryDirectory() as tmp:
        # 目录布局
        #   /save/Normal.mkv        单文件正常
        #   /save/ep01.mkv          供 partial 用（另一个 ep02 缺）
        #   （Gone / PartialFlat 目录**故意不建** → 顶层名不在 listing）
        #   /temp/TempOnly.mkv      数据只在临时目录
        save = os.path.join(tmp, "save")
        tempdir = os.path.join(tmp, "temp")
        os.makedirs(save, exist_ok=True)
        os.makedirs(tempdir, exist_ok=True)
        with open(os.path.join(save, "Normal.mkv"), "wb") as f:
            f.write(b"x" * 100)
        with open(os.path.join(save, "ep01.mkv"), "wb") as f:
            f.write(b"z" * 100)
        with open(os.path.join(tempdir, "TempOnly.mkv"), "wb") as f:
            f.write(b"w" * 100)

        carpt = "carpt"
        hdfans = "hdfans"
        site_map = {carpt: "carpt.net", hdfans: "hdfans.org"}

        snap = {
            "h-normal": FakeTorrent("h-normal", "Normal", save_path=save,
                                    content_path=os.path.join(save, "Normal.mkv"),
                                    size_gb=1.0, tags=[carpt]),
            "h-ghost": FakeTorrent("h-ghost", "Gone", save_path=save,
                                   content_path=os.path.join(save, "Gone"),
                                   size_gb=6.0, tags=[carpt]),
            "h-partial": FakeTorrent("h-partial", "PartialFlat", save_path=save,
                                     content_path=os.path.join(save, "PartialFlat"),
                                     size_gb=3.0, tags=[hdfans]),
            "h-temp": FakeTorrent("h-temp", "TempOnly", save_path=save,
                                  content_path=os.path.join(save, "TempOnly.mkv"),
                                  size_gb=2.0, tags=[carpt]),
        }

        files = {
            "h-normal": [("Normal.mkv", 100)],
            "h-ghost": [("gone_a.mkv", 100), ("gone_b.mkv", 200), ("gone_c.mkv", 300)],
            "h-partial": [("ep01.mkv", 100), ("ep02.mkv", 200)],  # ep01 在、ep02 不在
            "h-temp": [("TempOnly.mkv", 100)],
        }
        dl = FakeDl(files=files, prefs={"temp_path": tempdir, "temp_path_enabled": True})
        bills = {
            "h-ghost": {"state": "active", "rule": "site_hr", "site": "carpt.net",
                        "need_h": 24.0, "seeded_h": 0.0},
            "h-gone-from-qb": {"state": "active", "rule": "site_hr", "site": "carpt.net",
                               "need_h": 24.0, "seeded_h": 0.0},
        }
        protected = {"": {"h-ghost"}}
        p = Plug(snap=snap, dl=dl, bills=bills, protected=protected, site_map=site_map)

        data = _scan(p)
        items = {it["hash"]: it for it in data["items"]}

        _ok(data["write"] is False, "响应声明 write=false")
        _ok(data["scanned"] == 4, f"scanned=4（实际 {data['scanned']}）")

        # 1) 正常种
        n = items["h-normal"]
        _ok(n["bucket"] == "normal" and n["files_exist"] is None,
            "正常种不误报（normal，未核盘）")

        # 2) ghost
        g = items["h-ghost"]
        _ok(g["bucket"] == "ghost" and g["files_total"] == 3 and g["files_exist"] == 0,
            f"ghost：0/3 文件（{g['bucket']} {g['files_exist']}/{g['files_total']}）")

        # 3) partial
        pt = items["h-partial"]
        _ok(pt["bucket"] == "partial" and pt["files_total"] == 2 and pt["files_exist"] == 1,
            f"partial：1/2 文件（{pt['bucket']} {pt['files_exist']}/{pt['files_total']}）")

        # 4) 数据在临时目录 → 不算 ghost
        tp = items["h-temp"]
        _ok(tp["bucket"] == "normal", f"临时目录数据不算 ghost（{tp['bucket']}）")

        # 5) 汇总 / 体积 / by_site
        c = data["counts"]
        _ok(c["ghost"] == 1 and c["partial"] == 1 and c["normal"] == 2,
            f"counts：ghost=1 partial=1 normal=2（实际 {c}）")
        _ok(data["bytes"]["ghost_gb"] == 6.0 and data["bytes"]["partial_gb"] == 3.0,
            f"体积：ghost 6G / partial 3G（实际 {data['bytes']}）")
        _ok(data["by_site"]["carpt.net"]["ghost"] == 1
            and data["by_site"]["hdfans.org"]["partial"] == 1,
            f"by_site 正确（{data['by_site']}）")

        # 6) hr_at_risk + not_in_qb
        _ok(len(data["hr_at_risk"]) == 1 and data["hr_at_risk"][0]["hash"] == "h-ghost",
            "hr_at_risk：ghost 且欠 H&R 的种单列")
        _ok(c["not_in_qb"] == 1, f"not_in_qb：账单在册但 qB 无种 = 1（实际 {c['not_in_qb']}）")

        # 7) site 过滤
        d2 = _scan(p, site="carpt.net")
        _ok(all(it["site"] == "carpt.net" for it in d2["items"]),
            "site=carpt.net 只回 carpt")
        _ok(d2["counts"]["ghost"] == 1 and d2["counts"]["partial"] == 0,
            "site 过滤后 counts 也收敛")

        # 8) only 过滤
        d3 = _scan(p, only="ghost")
        _ok(all(it["bucket"] == "ghost" for it in d3["items"]) and len(d3["items"]) == 1,
            "only=ghost 只回 ghost")

        # 9) 零写调用
        _ok(dl.write_log == [] and p._bills.write_log == [] and p._store.write_log == [],
            f"零写调用（dl={dl.write_log} bills={p._bills.write_log} store={p._store.write_log}）")

        # 10) 候选上限截断
        #    构造 3 个 ghost，max_probe=2 → probed=2、probe_truncated=1
        snap2 = {}
        for i in range(3):
            h = f"g{i}"
            snap2[h] = FakeTorrent(h, f"G{i}", save_path=save,
                                   content_path=os.path.join(save, f"Miss{i}"),
                                   size_gb=1.0, tags=[carpt])
        files2 = {h: [("a.mkv", 1), ("b.mkv", 1)] for h in snap2}
        p2 = Plug(snap=snap2, dl=FakeDl(files=files2), site_map=site_map)
        d4 = _scan(p2, max_probe=2)
        _ok(d4["probed"] == 2 and d4["probe_truncated"] == 1,
            f"候选上限截断（probed={d4['probed']} truncated={d4['probe_truncated']}）")

    print("=" * 60)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
