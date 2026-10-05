#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 下载即开账 第二阶段（账单生效 + 存量回填）离线回归测试。

覆盖 ``features/hr.py`` 的第三来源（``hr_bills.json`` 接入 ``_hr_obligation``，只增保护）
与 ``features/hrbills.py`` 的存量回填（幂等 + 三级站点解析 + 回填后立即结清判定）。

断言面：
  - active 未挂够 → 欠（来源 "hrbill"）
  - active 挂够 / settled / void / pending → 不欠
  - rule=unknown 即使 active → 不欠（Master 红线：未知站不保护）
  - 账单读取抛异常 → 不欠（回退原逻辑，绝不让保护变少/闸门抛错）
  - 回填幂等（跑两次账单数不变）
  - 站点解析三级回退各一例

用法：``python3 tools/test_hrenforce.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PKG = "mf_hrenforce_test"


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

fingerprint = _load(PKG + ".fingerprint", "fingerprint.py")
crossseed = _load(PKG + ".crossseed", "crossseed.py")
persistence = _load(PKG + ".persistence", "persistence.py")
tags = _load(PKG + ".tags", "tags.py")
hrbills = _load(PKG + ".features.hrbills", "features/hrbills.py")
hr = _load(PKG + ".features.hr", "features/hr.py")

HrMixin = hr.HrMixin
HrBillsMixin = hrbills.HrBillsMixin
HrBillsStore = hrbills.HrBillsStore


def _torrent(hash_string="", progress=0.0, seed_time=0.0, hit_and_run=False,
             title="test", tracker=""):
    return types.SimpleNamespace(
        hash=str(hash_string).lower(), title=title, progress=progress,
        seed_time=seed_time, hit_and_run=hit_and_run, tags=[], tracker=tracker,
    )


class _Ledger:
    """极简状态账本 stub：只暴露 ``.items()``。"""
    def __init__(self, d):
        self._d = d

    def items(self):
        return dict(self._d)


class _Groups:
    """极简文件组账本 stub：``.items()`` + ``.group_of(hash)``。"""
    def __init__(self, data, group_of_map):
        self._data = data
        self._group_of_map = group_of_map

    def items(self):
        return dict(self._data)

    def group_of(self, hash_string):
        return self._group_of_map.get(str(hash_string).lower(), "")


class Harness(HrMixin, HrBillsMixin):
    """带桩的最小插件实例：只实现 hrbills/hr 用到的依赖。"""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._hot = None
        self.site_hr: dict = {}       # dom -> True/False/None
        self.need_hours: dict = {}    # dom -> float
        self.torrents: dict = {}      # hash -> SimpleNamespace
        self.ledger: dict = {}        # hash -> rec
        self.name2dom: dict = {}      # 站名 -> 域名
        self.groups_data: dict = {}   # group_id -> grec
        self.group_of_map: dict = {}  # hash -> group_id

    # ---- hrbills / hr 依赖桩 ----
    def get_data_path(self):
        return self._data_dir

    def _site_hr_flag(self, dom):
        return self.site_hr.get(dom)   # 未登记 → None（未知）

    def _crossseed_seed_need_hours(self, dom):
        return self.need_hours.get(dom, 0.0)

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _tag_state(self):
        return _Ledger(self.ledger)

    def _tag_groups(self):
        return _Groups(self.groups_data, self.group_of_map)

    def _site_domain_by_name(self, name):
        if not name:
            return ""
        if "." in name and " " not in name:
            return name.lower()
        return self.name2dom.get(name, "")

    # ---- 让 _hr_obligation 的「资源级/种子级」来源全部哑火 → 第三来源成为唯一判定 ----
    def _resource_source_index(self):
        return {}

    def _hr_obligation_by_seed(self, site, torrent):
        return (False, 0.0, 0.0, "")


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _open_bill(h, hs, *, state="active", rule="site_hr", need_h=20.0, seeded_h=0.0):
    """直接往 store 里放一张账单。"""
    return h._hrbills_store().put(hs, {
        "site": "hdfans.org", "rule": rule, "state": state, "need_h": need_h,
        "seeded_h": seeded_h, "fp": "", "title": "x", "opened_at": time.time(),
        "last_progress": 1.0, "last_progress_at": time.time(), "progress": 1.0,
        "opened_by": "open",
    })


def main() -> int:
    print("=" * 64)
    print("魔流 · 下载即开账 第二阶段（账单生效 + 回填）回归测试")
    print("=" * 64)

    tmp = tempfile.mkdtemp(prefix="hrenforce_test_")
    h = Harness(Path(tmp))

    # ---- 0) 开关 ----
    print("\n[0] 开关")
    _ok(hrbills.HR_BILLS_ENFORCE is True, "HR_BILLS_ENFORCE = True（第二阶段账单生效）")

    # ---- 1) active 未挂够 → 欠（来源 hrbill） ----
    print("\n[1] active 未挂够 → 欠")
    h.site_hr["hdfans.org"] = True
    h.need_hours["hdfans.org"] = 20.0
    t = _torrent(hash_string="aaaa", progress=1.0, seed_time=5.0 * 3600.0)
    h.torrents["aaaa"] = t
    _open_bill(h, "aaaa", state="active", rule="site_hr", need_h=20.0, seeded_h=5.0)
    owed, need, seeded, src = h._hr_obligation("hdfans.org", t)
    _ok(owed is True, f"active 未挂够 → 欠（实际 owed={owed}）")
    _ok(src == "hrbill", f"来源 = hrbill（{src}）")
    _ok(abs(need - 20.0) < 1e-9, f"need = 20.0（{need}）")
    _ok(abs(seeded - 5.0) < 1e-9, f"seeded = 5.0（{seeded}）")

    # ---- 2) active 挂够 / settled / void / pending → 不欠 ----
    print("\n[2] active 挂够 / settled / void / pending → 不欠")
    t2 = _torrent(hash_string="bbbb", progress=1.0, seed_time=25.0 * 3600.0)
    h.torrents["bbbb"] = t2
    _open_bill(h, "bbbb", state="active", rule="site_hr", need_h=20.0, seeded_h=25.0)
    _ok(h._hr_obligation("hdfans.org", t2)[0] is False, "active 挂够 → 不欠")

    t3 = _torrent(hash_string="cccc", progress=1.0, seed_time=1.0 * 3600.0)
    h.torrents["cccc"] = t3
    _open_bill(h, "cccc", state="settled", rule="site_hr", need_h=20.0, seeded_h=1.0)
    _ok(h._hr_obligation("hdfans.org", t3)[0] is False, "settled → 不欠")

    t4 = _torrent(hash_string="dddd", progress=1.0, seed_time=1.0 * 3600.0)
    h.torrents["dddd"] = t4
    _open_bill(h, "dddd", state="void", rule="site_hr", need_h=20.0, seeded_h=1.0)
    _ok(h._hr_obligation("hdfans.org", t4)[0] is False, "void → 不欠")

    t5 = _torrent(hash_string="eeee", progress=1.0, seed_time=1.0 * 3600.0)
    h.torrents["eeee"] = t5
    _open_bill(h, "eeee", state="pending", rule="unknown", need_h=24.0, seeded_h=1.0)
    _ok(h._hr_obligation("hdfans.org", t5)[0] is False, "pending（未知站）→ 不欠")

    # ---- 3) rule=unknown 即使 active → 不欠（红线） ----
    print("\n[3] rule=unknown 即使 active → 不欠")
    t6 = _torrent(hash_string="ffff", progress=1.0, seed_time=1.0 * 3600.0)
    h.torrents["ffff"] = t6
    _open_bill(h, "ffff", state="active", rule="unknown", need_h=24.0, seeded_h=1.0)
    _ok(h._hr_obligation("hdfans.org", t6)[0] is False, "active+unknown → 不欠（不猜）")

    # ---- 4) 账单读取抛异常 → 不欠（回退原逻辑） ----
    print("\n[4] 账单读取抛异常 → 不欠")
    class _Boom:
        def get(self, _h):
            raise RuntimeError("boom")
    t7 = _torrent(hash_string="abab", progress=1.0, seed_time=1.0 * 3600.0)
    h.torrents["abab"] = t7
    h._hrbills_store = lambda: _Boom()   # 覆盖实例方法 → 第三来源读账单必炸
    owed7 = h._hr_obligation("hdfans.org", t7)
    _ok(owed7[0] is False, f"账单读取异常 → 不欠（回退，实际 owed={owed7[0]}）")

    # ---- 5) 回填幂等（跑两次账单数不变） ----
    print("\n[5] 回填幂等")
    h2 = Harness(Path(tempfile.mkdtemp(prefix="hrenforce_bf_")))
    h2.site_hr["hdfans.org"] = True
    h2.need_hours["hdfans.org"] = 20.0
    h2.name2dom["红豆饭"] = "hdfans.org"
    for i, hs in enumerate(("1111", "2222", "3333")):
        tt = _torrent(hash_string=hs, progress=0.5, tracker="http://hdfans.org/announce")
        h2.torrents[hs] = tt
        h2.ledger[hs] = {"site": "红豆饭", "state": "brush", "sub": "resource"}
    store2 = h2._hrbills_store()
    snap2 = h2._tag_all_torrents()
    r1 = h2._hrbills_backfill(store2, snap2, limit=200)
    _ok(r1["opened"] == 3, f"首次回填开 3 张（{r1['opened']}）")
    n_after_first = len(store2.all())
    r2 = h2._hrbills_backfill(store2, snap2, limit=200)
    _ok(r2["opened"] == 0, f"二次回填开 0 张（幂等，{r2['opened']}）")
    _ok(len(store2.all()) == n_after_first, f"跑两次账单数不变（{len(store2.all())}）")
    _ok(all(store2.get(hs)["opened_by"] == "backfill" for hs in ("1111", "2222", "3333")),
        "回填账单标注 opened_by=backfill")

    # ---- 6) 回填后立即判定（已完成 + 挂够 → settled） ----
    print("\n[6] 回填后立即判定 settled")
    h3 = Harness(Path(tempfile.mkdtemp(prefix="hrenforce_settle_")))
    h3.site_hr["hdfans.org"] = True
    h3.need_hours["hdfans.org"] = 20.0
    h3.name2dom["红豆饭"] = "hdfans.org"
    ts = _torrent(hash_string="9999", progress=1.0, seed_time=30.0 * 3600.0,
                  tracker="http://hdfans.org/announce")
    h3.torrents["9999"] = ts
    h3.ledger["9999"] = {"site": "红豆饭", "state": "brush", "sub": "resource"}
    tick = h3._hrbills_tick()
    b = h3._hrbills_store().get("9999")
    _ok(b is not None, "回填后账单存在")
    _ok(tick["backfilled"] == 1, f"tick 回报 backfilled=1（{tick['backfilled']}）")
    _ok(b["state"] == "settled", f"已完成且挂够 → 当轮即 settled（{b['state']}）")

    # ---- 7) 站点解析三级回退 ----
    print("\n[7] 站点解析三级回退")
    h4 = Harness(Path(tempfile.mkdtemp(prefix="hrenforce_site_")))
    h4.name2dom["红豆饭"] = "hdfans.org"
    h4.name2dom["学校"] = "school.org"
    # ① 账本 site → 域名
    t_a = _torrent(hash_string="a", tracker="")
    dom1 = h4._hrbills_resolve_domain({"site": "红豆饭"}, t_a, None)
    _ok(dom1 == "hdfans.org", f"① 账本 site→域名（{dom1}）")
    # ② tracker 域名
    t_b = _torrent(hash_string="b", tracker="http://school.org/announce.php")
    dom2 = h4._hrbills_resolve_domain({"site": ""}, t_b, None)
    _ok(dom2 == "school.org", f"② tracker→域名（{dom2}）")
    # ③ 资源来源站
    h4.groups_data["g1"] = {"source_site": "学校", "source_hash": "b", "members": {}}
    h4.group_of_map["c"] = "g1"
    t_c = _torrent(hash_string="c", tracker="")
    dom3 = h4._hrbills_resolve_domain({"site": ""}, t_c, h4._tag_groups())
    _ok(dom3 == "school.org", f"③ 资源来源站→域名（{dom3}）")
    # 全失败 → ""
    t_d = _torrent(hash_string="d", tracker="")
    dom4 = h4._hrbills_resolve_domain({"site": ""}, t_d, None)
    _ok(dom4 == "", f"全失败 → site=''（{dom4!r}）")

    # ---- 8) 统计字段 ----
    print("\n[8] 统计字段")
    stats = h2._hrbills_stats()
    _ok(stats["enforcing"] is True, f"stats.enforcing = True（{stats['enforcing']}）")
    _ok("no_site" in stats and isinstance(stats["no_site"], int), "stats.no_site 存在")
    _ok("opened_by" in stats and stats["opened_by"].get("backfill", 0) == 3,
        f"stats.opened_by.backfill = 3（{stats['opened_by']}）")
    dry = h2._hrbills_dryrun()
    _ok("would_protect_hashes" in dry, "干跑返回 would_protect_hashes")

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
