#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 下载即开账（HrBills）离线回归测试（真跑，不需要 MoviePilot 环境）。

覆盖 ``features/hrbills.py`` 的第一阶段（影子记账）行为：
  - 开账去重（同 hash 不重复开）
  - 未知站 → pending（不保护不罚）
  - ★ 15.5.1：开账恒 pending（H&R 自「下载完成」起算）；完成 → active；未完成的历史 active 自动降回 pending
  - crossseed tag → 跳过（crossseed 自己记账）
  - 7 天无进度 → void
  - 消失且未完成 → 立即 void
  - progress ≥ 0.999 → active
  - seeded_h ≥ need_h → settled

用法：``python3 tools/test_hrbills.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 以「合成包」加载 hrbills.py —— 它的相对导入（..crossseed / ..fingerprint / ..persistence）
# 需要父包。persistence / crossseed / fingerprint 都是纯 stdlib（模块级无 MP 依赖），可直接加载。
# ---------------------------------------------------------------------------
PKG = "mf_hrbills_test"


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
downloader_ops = _load(PKG + ".downloader_ops", "downloader_ops.py")
hrbills = _load(PKG + ".features.hrbills", "features/hrbills.py")

HrBillsMixin = hrbills.HrBillsMixin
HrBillsStore = hrbills.HrBillsStore
get_hr_bills_store = hrbills.get_hr_bills_store
CROSSSEED_TAG = crossseed.CROSSSEED_TAG


def _torrent(progress=0.0, seed_time=0.0, hit_and_run=False, title="test", tracker="hdfans.org",
             completion_on=0.0):
    return types.SimpleNamespace(
        hash="", title=title, progress=progress, seed_time=seed_time,
        hit_and_run=hit_and_run, tags=[], tracker=tracker,
        completion_on=completion_on,
    )


class Harness(HrBillsMixin):
    """带桩的最小插件实例，只实现 hrbills 用到的依赖。"""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._hot = None
        self.site_hr: dict = {}       # dom -> True/False/None
        self.pt_hr: dict = {}         # dom -> 逐种 H&R 站（11.7.0）
        self.need_hours: dict = {}    # dom -> float
        self.torrents: dict = {}      # hash -> SimpleNamespace
        self.ledger: dict = {}        # hash -> rec dict
        self.name2dom: dict = {}      # 站名 -> 域名
        # ★ 11.13.0：默认把安全垫置 0（保留「need_h 即达标」的旧断言），
        #   安全垫 / 到期预警单独在 [7b] 里开 2.0 验证。
        self._hr_seed_margin_hours = 0.0
        self._hr_deadline_warn_hours = 48.0

    def _crossseed_seed_window_hours(self, dom):
        return 0.0

    def get_data_path(self):
        return self._data_dir

    def _site_hr_flag(self, dom):
        return self.site_hr.get(dom)   # 未登记 → None（未知）

    def _site_per_torrent_hr(self, dom):
        return bool(self.pt_hr.get(dom, False))

    def _crossseed_seed_need_hours(self, dom):
        return self.need_hours.get(dom, 0.0)

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _tag_state(self):
        class _S:
            def __init__(self, d):
                self._d = d

            def items(self):
                return dict(self._d)
        return _S(self.ledger)

    def _site_domain_by_name(self, name):
        if not name:
            return ""
        if "." in name and " " not in name:
            return name.lower()
        return self.name2dom.get(name, "")


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def _torrent_bytes(name="test") -> bytes:
    """构造一个最小合法 .torrent 字节（可算特征码）。"""
    info = {b"name": name.encode("utf-8"), b"length": 1000, b"piece length": 16384,
            b"pieces": b"0" * 20}
    meta = {b"info": info, b"announce": b"http://hdfans.org/announce"}
    return fingerprint.bencode(meta)


def main() -> int:
    print("=" * 64)
    print("魔流 · 下载即开账（HrBills）影子记账回归测试")
    print("=" * 64)

    tmp = tempfile.mkdtemp(prefix="hrbills_test_")
    h = Harness(Path(tmp))

    # ---- 0) 模块常量 ----
    print("\n[0] 模块常量")
    _ok(hrbills.HR_BILLS_ENFORCE is True, "HR_BILLS_ENFORCE = True（第二阶段账单生效）")
    _ok(crossseed.CROSSSEED_TAG == "魔流-跨站", f"CROSSSEED_TAG = {crossseed.CROSSSEED_TAG!r}")

    # ---- 1) 开账去重 ----
    print("\n[1] 开账去重")
    h.site_hr["hdfans.org"] = True
    h.need_hours["hdfans.org"] = 20.0
    raw = _torrent_bytes()
    t = _torrent(progress=0.0, title="样本A", tracker="hdfans.org")
    t.hash = "aaaa"
    h.torrents["aaaa"] = t
    b1 = h._hrbills_open("AAAA", "hdfans.org", "魔流-hdfans-刷流", raw)
    _ok(b1 is not None, "首次开账成功")
    b2 = h._hrbills_open("aaaa", "hdfans.org", "魔流-hdfans-刷流", raw)
    _ok(b2 is b1, "同 hash 二次开账返回已有账单（不重复开）")
    store = h._hrbills_store()
    _ok(len(store.all()) == 1, f"store 里只有 1 张账单（实际 {len(store.all())}）")
    _ok(b1["site"] == "hdfans.org", f"账单 site=domain（{b1['site']}）")
    _ok(b1["rule"] == "site_hr", f"规则 = site_hr（{b1['rule']}）")
    _ok(b1["state"] == "pending",
        f"★ 15.5.1：开账恒 pending（H&R 自完成起算）（{b1['state']}）")
    _ok(abs(b1["need_h"] - 20.0) < 1e-9, f"need_h = 20.0（{b1['need_h']}）")
    _ok(bool(b1["fp"]) and len(b1["fp"]) == 40, f"fp 已算出（{b1['fp'][:12]}…）")
    _ok(b1["title"] == "样本A", f"title = 样本A（{b1['title']}）")

    # ---- 2) 未知站 → pending ----
    print("\n[2] 未知站 → pending")
    t2 = _torrent(progress=0.0, title="未知站种", tracker="unknown.site")
    t2.hash = "bbbb"
    h.torrents["bbbb"] = t2
    b3 = h._hrbills_open("bbbb", "unknown.site", "魔流-x-刷流", _torrent_bytes("b"))
    _ok(b3 is not None, "未知站也开账（影子记录）")
    _ok(b3["rule"] == "unknown", f"规则 = unknown（{b3['rule']}）")
    _ok(b3["state"] == "pending", f"状态 = pending（{b3['state']}）")
    _ok(abs(b3["need_h"] - 24.0) < 1e-9, f"need_h 兜底 24.0（{b3['need_h']}）")

    # ---- 3) crossseed tag → 跳过 ----
    print("\n[3] crossseed tag → 跳过")
    n_before = len(store.all())
    t3 = _torrent(progress=0.0, title="跨站种")
    t3.hash = "cccc"
    h.torrents["cccc"] = t3
    b4 = h._hrbills_open("cccc", "hdfans.org", CROSSSEED_TAG, _torrent_bytes("c"))
    _ok(b4 is None, "crossseed tag 开账被跳过（返回 None）")
    _ok(len(store.all()) == n_before, "账单数不变（crossseed 自己记账）")

    # ---- 4) 7 天无进度 → void ----
    print("\n[4] 7 天无进度 → void")
    t4 = _torrent(progress=0.0, title="卡住种")
    t4.hash = "dddd"
    h.torrents["dddd"] = t4
    h._hrbills_open("dddd", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("d"))
    t4.progress = 0.3
    h._hrbills_tick()  # 第一次：记下 last_progress=0.3
    _ok(abs(store.get("dddd")["last_progress"] - 0.3) < 1e-9, "tick 记录 progress 增长 0.3")
    # 模拟 8 天前就停在 0.3
    store.patch("dddd", last_progress_at=time.time() - 8 * 86400.0)
    h._hrbills_tick()
    _ok(store.get("dddd")["state"] == "void", f"连续无进度 → void（{store.get('dddd')['state']}）")

    # ---- 5) 消失且未完成 → 立即 void ----
    print("\n[5] 消失且未完成 → 立即 void")
    t5 = _torrent(progress=0.5, title="半截种")
    t5.hash = "eeee"
    h.torrents["eeee"] = t5
    h._hrbills_open("eeee", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("e"))
    h.torrents.pop("eeee")  # 从下载器消失
    h._hrbills_tick()
    _ok(store.get("eeee")["state"] == "void", f"消失且未完成 → 立即 void（{store.get('eeee')['state']}）")
    _ok(store.get("eeee").get("void_reason") == "disappeared_uncompleted", "void_reason = disappeared_uncompleted")

    # ---- 6) progress ≥ 0.999 → active ----
    print("\n[6] progress ≥ 0.999 → active")
    t6 = _torrent(progress=0.0, title="未知站完成种", tracker="other.site")
    t6.hash = "ffff"
    h.torrents["ffff"] = t6
    h._hrbills_open("ffff", "other.site", "魔流-x-刷流", _torrent_bytes("f"))
    _ok(store.get("ffff")["state"] == "pending", "初始 pending（未知站）")
    t6.progress = 1.0
    h._hrbills_tick()
    _ok(store.get("ffff")["state"] == "active", f"下载完成 → active（{store.get('ffff')['state']}）")

    # ---- 7) seeded_h ≥ need_h → settled ----
    print("\n[7] seeded_h ≥ need_h → settled")
    t7 = _torrent(progress=1.0, title="挂够种", tracker="hdfans.org")
    t7.hash = "abab"
    h.torrents["abab"] = t7
    h._hrbills_open("abab", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("g"))
    _ok(store.get("abab")["state"] == "pending", "开账 pending（已知站，未完成）")
    h._hrbills_tick()
    _ok(store.get("abab")["state"] == "active", "已完成 → 转 active")
    t7.seed_time = 21.0 * 3600.0  # 挂够 21h > 20h
    h._hrbills_tick()
    _ok(store.get("abab")["state"] == "settled", f"挂够 need_h → settled（{store.get('abab')['state']}）")

    # ---- 7b) ★ 11.13.0 安全垫：need_h + margin 才算结清 ----
    print("\n[7b] 安全垫：seeded_h ≥ need_h + margin 才结清")
    t7b = _torrent(progress=1.0, title="安全垫种", tracker="hdfans.org")
    t7b.hash = "abab2"
    h.torrents["abab2"] = t7b
    h._hrbills_open("abab2", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("h"))
    h._hr_seed_margin_hours = 2.0          # 需 20 + 2 = 22h
    t7b.seed_time = 21.0 * 3600.0          # 21 < 22 → 不结清
    h._hrbills_tick()
    _ok(store.get("abab2")["state"] == "active",
        f"21h < need 20 + margin 2 → 仍未结清（{store.get('abab2')['state']}）")
    t7b.seed_time = 22.5 * 3600.0          # 22.5 ≥ 22 → 结清
    h._hrbills_tick()
    _ok(store.get("abab2")["state"] == "settled",
        f"22.5h ≥ 20 + 2 → 结清（{store.get('abab2')['state']}）")
    h._hr_seed_margin_hours = 0.0

    # ---- 8) 磁力链（无特征码）→ fp="" ----
    print("\n[8] 磁力链（无特征码）→ fp=''")
    t8 = _torrent(progress=0.0, title="磁力种")
    t8.hash = "cdcd"
    h.torrents["cdcd"] = t8
    b8 = h._hrbills_open("cdcd", "hdfans.org", "魔流-hdfans-刷流",
                         "magnet:?xt=urn:btih:cdcd&dn=x")
    _ok(b8 is not None, "磁力链也开账")
    _ok(b8["fp"] == "", f"磁力链无特征码 → fp=''（{b8['fp']!r}）")

    # ---- 8b) ★ 15.5.1 未完成 = 无 H&R：历史 active 降回 pending，完成再升 active ----
    print("\n[8b] 未完成 = 无 H&R（active → pending；完成 → active）")
    t11 = _torrent(progress=0.4, title="未完成虚欠", tracker="hdfans.org")
    t11.hash = "e5e5"
    h.torrents["e5e5"] = t11
    h._hrbills_open("e5e5", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("i"))
    store.patch("e5e5", state="active")  # 模拟 15.5.1 之前「下载即 active」开出的账单
    r11 = h._hrbills_tick()
    _ok(store.get("e5e5")["state"] == "pending",
        f"未完成的 active → 降回 pending（{store.get('e5e5')['state']}）")
    _ok(int(r11.get("demoted") or 0) >= 1, f"tick 报 demoted={r11.get('demoted')}")
    t11.progress = 1.0
    h._hrbills_tick()
    _ok(store.get("e5e5")["state"] == "active",
        f"下载完成 → 重新 active（{store.get('e5e5')['state']}）")

    # ---- 8c) ★ 15.5.1 完成度阈值可设置（默认 0.999）----
    print("\n[8c] 完成度阈值可设置（默认 0.999）")
    _tc = _torrent(progress=0.6, title="半程种", tracker="hdfans.org")
    _tc.hash = "c0c0"
    h.torrents["c0c0"] = _tc
    h._hrbills_open("c0c0", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("co"))
    h._hrbills_tick()
    _ok(store.get("c0c0")["state"] == "pending",
        "默认 0.999：60% 未完成 → pending（不计 H&R）")
    h._hr_complete_ratio_v = 0.5
    h._hrbills_tick()
    _ok(store.get("c0c0")["state"] == "active",
        f"阈值 0.5：60% 算完成 → active（{store.get('c0c0')['state']}）")
    h._hr_complete_ratio_v = 0.999
    h._hrbills_tick()
    _ok(store.get("c0c0")["state"] == "pending",
        f"回调 0.999：60% 未完成 → 降回 pending（{store.get('c0c0')['state']}）")

    # ---- 9) 干跑 + 统计 ----
    print("\n[9] 干跑 + 统计")
    dry = h._hrbills_dryrun()
    _ok(isinstance(dry, dict) and "no_fp" in dry and "would_open" in dry, "干跑返回分桶")
    stats = h._hrbills_stats()
    _ok(stats["total"] == len(store.all()), f"stats.total == 账单数（{stats['total']}）")
    _ok("settled" in stats["by_state"], "统计含 settled 分桶")

    # ---- 10) H&R 盲区扫描（旁路加种）----
    print("\n[10] H&R 盲区扫描（旁路加种）")
    h.site_hr["pt.btschool.club"] = True
    h.site_hr["ptcafe.club"] = False
    t_by = _torrent(progress=0.02, title="旁路加种", tracker="pt.btschool.club")
    t_by.hash = "b111"
    t_by.tags = []
    h.torrents["b111"] = t_by
    t_mg = _torrent(progress=1.0, title="已纳管", tracker="pt.btschool.club")
    t_mg.hash = "b222"
    t_mg.tags = ["魔流-补源"]
    h.torrents["b222"] = t_mg
    t_nohr = _torrent(progress=1.0, title="无H&R站", tracker="ptcafe.club")
    t_nohr.hash = "b333"
    t_nohr.tags = []
    h.torrents["b333"] = t_nohr
    t_unk = _torrent(progress=1.0, title="未知站", tracker="unknown.example")
    t_unk.hash = "b444"
    t_unk.tags = []
    h.torrents["b444"] = t_unk
    scan = h._hr_blindspot_scan()
    hits = {i["hash"] for i in scan["items"]}
    _ok("b111" in hits, "旁路加种（hr 站 + 无账单 + 无标签）被报为盲区")
    _ok(not ({"b222", "b333", "b444"} & hits),
        "已打魔流标签 / hr=False 站 / 未知站 都不报")
    _ok(scan["scanned_hr"] >= 1, f"scanned_hr 统计明确有 H&R 的站（{scan['scanned_hr']}）")
    _item = next(i for i in scan["items"] if i["hash"] == "b111")
    _ok(_item["site"] == "pt.btschool.club" and _item["hr"] is True, "盲区项带站点域名 + hr=True")
    _ok(scan["reason_chain"][0]["rule"] == "hrbills/blindspot", "带判定依据链（hrbills/blindspot）")
    # 开账纳管 → 盲区立即消失
    h._hrbills_open("b111", "pt.btschool.club", "魔流-btschool-刷流", _torrent_bytes("by"))
    _ok("b111" not in {i["hash"] for i in h._hr_blindspot_scan()["items"]},
        "纳管（开账）后不再报 b111")

    # ---- 11) 做种时长保守口径 seed_hours_for_hr（11.6.1）----
    print("\n[11] 做种时长保守口径（11.6.1）")
    f = downloader_ops.seed_hours_for_hr
    _now = time.time()
    # 未下完 → 0（不管 qB 报多少）
    _t = _torrent(progress=0.42, seed_time=16 * 3600, completion_on=0.0)
    _ok(f(_t, now=_now) == 0.0, "未下完（42%）→ 做种小时 = 0")
    # 刚完成：qB 报 16h，但完成才 0.1h → 取小 = 0.1h
    _t2 = _torrent(progress=1.0, seed_time=16 * 3600, completion_on=_now - 360.0)
    _ok(abs(f(_t2, now=_now) - 0.1) < 1e-6,
        f"刚完成 → 取 min(qB 16h, 距完成 0.1h)=0.1h（实得 {f(_t2, now=_now):.2f}h）")
    # 长期做种：qB 小于距完成 → 用 qB
    _t3 = _torrent(progress=1.0, seed_time=5 * 3600, completion_on=_now - 100 * 3600)
    _ok(abs(f(_t3, now=_now) - 5.0) < 1e-6, "长期做种 → 用 qB 值（5h）")
    # 无 completion_on（老数据/未完成）→ 退回 qB 值（但不小于 0）
    _t4 = _torrent(progress=1.0, seed_time=3 * 3600, completion_on=0.0)
    _ok(abs(f(_t4, now=_now) - 3.0) < 1e-6, "无完成时间 → 退回 qB 值（3h）")
    # 账单巡检用同口径：刚完成 0.1h 的种不会因 qB 报 16h 被误结清
    _t5 = _torrent(progress=1.0, seed_time=16 * 3600, completion_on=_now - 360.0, tracker="hdfans.org")
    _t5.hash = "e555"
    h.torrents["e555"] = _t5
    h._hrbills_open("e555", "hdfans.org", "魔流-hdfans-刷流", _torrent_bytes("e5"))
    h._hrbills_tick()
    _b5 = store.get("e555")
    _ok(_b5 and abs(float(_b5.get("seeded_h") or 0) - 0.1) < 0.02,
        f"巡检写入的 seeded_h 走保守口径（实得 {(_b5 or {}).get('seeded_h')}）")
    _ok(_b5 and _b5.get("state") == "active", "刚完成的账单保持 active（不提前结清）")

    print("\n[12] 逐种 H&R 标记落账 + 审计 + 人工作废（11.7.0）")
    # 12.1 下载瞬间带 hit_and_run=True 的候选 → 账单 rule=hit_and_run（欠 H&R，保护）
    h.pt_hr["www.yemapt.org"] = True
    _t12 = _torrent(progress=1.0, seed_time=2 * 3600, tracker="www.yemapt.org")
    _t12.hash = "e1200"
    h.torrents["e1200"] = _t12
    h._hrbills_open("e1200", "www.yemapt.org", "魔流-野马-刷流", _torrent_bytes("e12"),
                    hit_and_run=True)
    _b12 = store.get("e1200")
    _ok(_b12 and _b12.get("rule") == "hit_and_run",
        f"带标记的候选 → 账单 rule=hit_and_run（实得 {(_b12 or {}).get('rule')}）")
    _ok(_b12 and _b12.get("state") == "pending",
        f"★ 15.5.1：开账 pending（H&R 自完成起算）（实得 {(_b12 or {}).get('state')}）")
    h._hrbills_tick()
    _b12 = store.get("e1200")
    _ok(_b12 and _b12.get("state") == "active", "完成（tick 后）→ active（受保护）")
    # 12.2 无标记（默认）→ 逐种站无站点级 H&R → unknown（不保护不罚）
    _t12b = _torrent(progress=1.0, seed_time=2 * 3600, tracker="www.yemapt.org")
    _t12b.hash = "e1201"
    h.torrents["e1201"] = _t12b
    h._hrbills_open("e1201", "www.yemapt.org", "魔流-野马-刷流", _torrent_bytes("e120b"))
    _b12b = store.get("e1201")
    _ok(_b12b and _b12b.get("rule") == "unknown" and _b12b.get("state") == "pending",
        "无标记 → unknown/pending（不保护不罚）")
    # 12.3 回退开关：HR_PER_TORRENT=False → 标记不影响（退回 11.6.1 行为）
    _prev = hrbills.HR_PER_TORRENT
    hrbills.HR_PER_TORRENT = False
    _t12c = _torrent(progress=1.0, seed_time=2 * 3600, tracker="www.yemapt.org")
    _t12c.hash = "e1202"
    h.torrents["e1202"] = _t12c
    h._hrbills_open("e1202", "www.yemapt.org", "魔流-野马-刷流", _torrent_bytes("e12c"),
                    hit_and_run=True)
    _b12c = store.get("e1202")
    _ok(_b12c and _b12c.get("rule") == "unknown",
        "HR_PER_TORRENT=False → 标记不落账（一键回退生效）")
    hrbills.HR_PER_TORRENT = _prev
    # 12.4 审计：逐种站按 rule 摊开，unknown 单列
    _aud = h._hr_per_torrent_audit()
    _yt = next((s for s in _aud["sites"] if s["domain"] == "www.yemapt.org"), None)
    _ok(_yt is not None and _yt["by_rule"].get("hit_and_run") == 1
        and _yt["by_rule"].get("unknown") == 2,
        f"审计：逐种站 hit_and_run=1 / unknown=2（实得 {(_yt or {}).get('by_rule')}）")
    _ok(len((_yt or {}).get("unknown_bills") or []) == 2, "审计：unknown 账单可逐条列出（待人工核对）")
    _ok(_aud["totals"]["sites"] == 1 and _aud["totals"]["hit_and_run"] == 1,
        f"审计汇总正确（sites={_aud['totals']['sites']} hit_and_run={_aud['totals']['hit_and_run']}）")
    # 非逐种站不进审计
    _ok(all(s["domain"] != "hdfans.org" for s in _aud["sites"]), "非逐种站不进逐种审计")
    # 12.5 人工作废：置 void + void_reason，幂等；回填不会重开
    _v = h._hrbills_void("e1201", "resolved_no_hr")
    _ok(_v and _v.get("state") == "void" and _v.get("void_reason") == "resolved_no_hr",
        "人工作废 → state=void + void_reason")
    _ok(h._hrbills_void("e1201", "again").get("void_reason") == "resolved_no_hr",
        "作废幂等（不覆盖已有 void_reason）")
    _ok(h._hrbills_void("nope", "x") is None, "作废不存在的账单 → None")

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
