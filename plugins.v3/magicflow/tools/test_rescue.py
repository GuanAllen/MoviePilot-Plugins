#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 死种补源（rescue）离线回归测试（真跑，无需 MoviePilot，零网络/零写）。

覆盖：
  (a) 标题归一化：大小写/全半角/点空格归一 + 「10bit vs 非 10bit」绝不等同
  (b) 目标扫描 `_rescue_targets`：停滞欠 H&R / 手动保留 → 目标；未停滞/已完成/
      已跨站/无关种 → 排除；每条带 `reason_not_reuse` + `reason_chain`
  (c) 候选检索 `_rescue_candidates`：来源站 hr!=False → 排除（保留证据）；无源 → 排除；
      hr==False 且有源 → 候选；标题不一致(10bit) → 绝不进候选
  (d) 写操作 `_rescue_apply`：默认干跑不写；confirm 缺位拒绝；confirm=1 才真 add_torrent
  (e) AI 入口 `agent_rescue`：统一信封 + targets/skipped_sites/settings

用法：``python3 tools/test_rescue.py``（退出码 0=PASS / 1=FAIL）。
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
    for name, attr_map in (
        ("app", {}),
        ("app.schemas", {"Response": type("Response", (), {})}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attr_map.items():
            setattr(m, k, v)


def _load_rescue():
    _stub_app()
    pkg = types.ModuleType("mf_rescue_test")
    pkg.__path__ = [str(ROOT)]
    sys.modules.setdefault("mf_rescue_test", pkg)
    feat = types.ModuleType("mf_rescue_test.features")
    feat.__path__ = [str(ROOT / "features")]
    sys.modules.setdefault("mf_rescue_test.features", feat)
    # rescue 内部有延迟相对导入 `from ..fingerprint import ...` → 先把 fingerprint 挂上
    fspec = importlib.util.spec_from_file_location("mf_rescue_test.fingerprint",
                                                   ROOT / "fingerprint.py")
    fmod = importlib.util.module_from_spec(fspec)
    sys.modules["mf_rescue_test.fingerprint"] = fmod
    fspec.loader.exec_module(fmod)
    spec = importlib.util.spec_from_file_location("mf_rescue_test.features.rescue",
                                                  ROOT / "features" / "rescue.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mf_rescue_test.features.rescue"] = mod
    spec.loader.exec_module(mod)
    return mod


rescue = _load_rescue()
RescueMixin = rescue.RescueMixin
norm_title = rescue._rescue_norm_title
RESCUE_TAG = rescue.RESCUE_TAG


# ------------------------------------------------------------------ 假对象
def _torrent(h, title="T", progress=1.0, dlspeed=0.0, added_on=0.0, downloaded=0.0,
             tags=None, save_path="/dl", size=1073741824):
    return types.SimpleNamespace(
        hash=str(h).lower(), title=title, progress=progress,
        download_speed=dlspeed, added_on=added_on, downloaded=downloaded,
        tags=list(tags or []), save_path=save_path, size=size,
        state="stalledDL",
    )


def _hit(title, site, site_name, seeders, size=1073741824):
    return types.SimpleNamespace(
        title=title, site=site, site_name=site_name, seeders=seeders, size=size,
        enclosure=f"http://{site_name}/dl/{site}", page_url=f"http://{site_name}/t/{site}",
    )


def _tb(name: str, size: int, piece: bytes = b"\x11" * 20) -> bytes:
    """构造最小合法 .torrent（单文件）字节（供指纹/写前校验用）。"""
    nb = name.encode("utf-8")
    return (b"d4:infod6:lengthi" + str(int(size)).encode() + b"e4:name"
            + str(len(nb)).encode() + b":" + nb
            + b"12:piece lengthi65536e6:pieces20:" + piece + b"ee")


def _fp(raw: bytes):
    return sys.modules["mf_rescue_test.fingerprint"].fingerprint(raw)


class _FakeIYUU:
    """假 IYUU 云端：`query` 返回「他站同资源」行。"""

    def __init__(self, rows=None, sid_by_domain=None):
        self.rows = list(rows or [])
        self.map = dict(sid_by_domain or {})
        self.calls = []

    def query(self, hashes, sids=None):
        self.calls.append(list(hashes))
        return {str(h).lower(): list(self.rows) for h in hashes}

    def sid_by_domain(self, domain):
        return self.map.get(str(domain or "").strip().lower())


class _FakeDownloader:
    def __init__(self):
        self.is_available = True
        self.added = []
        self.fp_by_hash = {}
        self.fetch_bytes = {}
        self.fetch_calls = []

    def add_torrent(self, content=None, download_dir="", tag=None, **kw):
        self.added.append({"content": content, "download_dir": download_dir, "tag": tag, **kw})
        return "newhash000000000000000000000000000000000000", None

    def get_torrent_fingerprint(self, hash_string):
        return self.fp_by_hash.get(str(hash_string).lower())

    def fetch_torrent_bytes(self, url, cookie=None, user_agent=None, proxies=None, referer=None):
        self.fetch_calls.append(url)
        return self.fetch_bytes.get(url)


class Harness(RescueMixin):
    def __init__(self):
        self.snap = {}
        self.manual = set()
        self.hr_result = (False, 0.0, 0.0, "")
        self._rescue_cfg = {"stall_hours": 6.0, "max_candidates": 3}
        self._rescue_stall_obj = {}
        self.name2domain = {}
        self.rules_hr = {}          # domain -> True/False/None
        self.site_list = []
        self.domain_to_id = {}
        self.mp_hits = []
        self._torrent_bytes = _tb("Some.Movie.2024.1080p.BluRay.x264-FLUX.mkv", 1234567)
        self._downloader = _FakeDownloader()
        self.logs = []
        self.saved = []
        # IYUU 指纹索引假件（11.6.0）
        self._iyuu_client = None
        self.reseed_site_map = {}
        self.reseed_urls = {}
        self.reseed_conn = {}
        self.pv_spent = []
        self.pv_deny = set()

    # ---- 注入点（真值源 / 复用点全部可替换）----
    def _tag_all_torrents(self):
        return dict(self.snap)

    def _agent_manual_hashes(self):
        return set(self.manual)

    def _hr_obligation(self, site, torrent, snap=None):
        return self.hr_result

    def _torrent_site_name(self, tags, fallback=""):
        for t in tags:
            if t in self.name2domain:
                return t
        return fallback or ""

    def _site_domain_by_name(self, name):
        return self.name2domain.get(str(name or "").strip(), "")

    def _site_hr_flag(self, domain):
        return self.rules_hr.get(str(domain or "").strip().lower())

    def _list_sites(self):
        return self.site_list

    def _site_id_by_domain(self, domain):
        return self.domain_to_id.get(str(domain or "").strip().lower(), 0)

    def _mp_search_title(self, keyword, sites):
        return list(self.mp_hits)

    def _crossseed_torrent_bytes(self, row):
        return self._torrent_bytes

    # ---- IYUU / PV 注入点（11.6.0）----
    def _reseed_site_map(self):
        return dict(self.reseed_site_map)

    def _reseed_download_url(self, sid, tid):
        return self.reseed_urls.get((int(sid), tid))

    def _reseed_site_conn(self, sid):
        return self.reseed_conn.get(int(sid), {})

    def _pv_allow(self, site_id, kind="browse", want=1):
        return int(site_id) not in self.pv_deny

    def _pv_spend(self, site_id, kind, n=1):
        self.pv_spent.append((int(site_id), kind, int(n)))
        return 1

    def _get_downloader(self, name="qbittorrent"):
        return self._downloader

    def _log(self, message, level="info"):
        self.logs.append(message)

    def save_data(self, key=None, value=None):
        self.saved.append((key, value))

    def get_data(self, key):
        return None

    def _agent_ok(self, data, t0):
        return {"ok": True, "code": "ok", "message": "", "data": data, "meta": {}}

    def _agent_err(self, code, message, t0, **kw):
        return {"ok": False, "code": code, "message": message, "data": None, "meta": {}}


def _hex(i: int) -> str:
    return format(i, "x").rjust(40, "0")


def main() -> int:
    print("=" * 66)
    print("魔流 · 死种补源（rescue）离线回归测试")
    print("=" * 66)

    # =====================================================================
    # (a) 标题归一化
    # =====================================================================
    print("\n[a] 标题归一化（完全一致 + 10bit 绝不等同）")
    a = "Some.Movie.2024.1080p.BluRay.x264-FLUX"
    b = "Some Movie 2024 1080p BluRay x264 FLUX"
    _ok(norm_title(a) == norm_title(b), "点/空格/大小写归一后一致（同 Release）")
    _ok(norm_title("Some.Movie.2024.1080p.BluRay.x264.10bit-FLUX") != norm_title(a),
        "10bit 与非 10bit 判不一致（词元多一个）")
    _ok(norm_title("Some.Movie.2024.1080p.BluRay.x265-FLUX") != norm_title(a),
        "x264 与 x265 判不一致")
    # 全角 → 半角
    _ok(norm_title("ＡＢＣ") == norm_title("abc"), "全角 AＢＣ → 半角 abc（全半角归一）")
    _ok(norm_title("") == (), "空标题 → 空词元组")

    # =====================================================================
    # (b) 目标扫描
    # =====================================================================
    print("\n[b] 目标扫描 _rescue_targets")
    now = time.time()
    h = Harness()
    h_owed = _hex(1)     # 停滞 + 欠 H&R → 目标
    h_manual = _hex(2)   # 停滞 + 手动保留（不欠）→ 目标
    h_active = _hex(3)   # 未停滞（dlspeed>0）→ 排除
    h_done = _hex(4)     # 已完成（progress=1）→ 排除
    h_idle = _hex(5)     # 停滞但既不欠 H&R 也不手动 → 排除
    h_cross = _hex(6)    # 停滞欠 H&R 但已跨站 → 排除
    h_recent = _hex(7)   # 停滞但时长不足 → 排除
    h.snap = {
        h_owed: _torrent(h_owed, "征途 2160p", progress=0.364, dlspeed=0.0,
                         added_on=now - 10 * 3600, downloaded=0.0),
        h_manual: _torrent(h_manual, "手动种 1080p", progress=0.5, dlspeed=0.0,
                           added_on=now - 20 * 3600, downloaded=0.0),
        h_active: _torrent(h_active, "在动种", progress=0.4, dlspeed=100.0,
                           added_on=now - 10 * 3600, downloaded=1024),
        h_done: _torrent(h_done, "完成种", progress=1.0, dlspeed=0.0),
        h_idle: _torrent(h_idle, "无关停滞种", progress=0.4, dlspeed=0.0,
                         added_on=now - 10 * 3600, downloaded=0.0),
        h_cross: _torrent(h_cross, "已跨站种", progress=0.4, dlspeed=0.0,
                          added_on=now - 10 * 3600, downloaded=0.0,
                          tags=["魔流-跨站"]),
        h_recent: _torrent(h_recent, "刚停种", progress=0.4, dlspeed=0.0,
                           added_on=now, downloaded=0.0),
    }
    h.manual = {h_manual}
    h.name2domain = {"学校": "pt.btschool.club"}

    def _hr_for(site, torrent, snap=None):
        return (True, 24.0, 0.0, "hrbill") if torrent.hash == h_owed else (False, 0.0, 0.0, "")
    h.hr_result = None  # 用函数替换
    h._hr_obligation = _hr_for

    targets = h._rescue_targets()
    got = {t["hash"] for t in targets}
    _ok(got == {h_owed, h_manual}, f"目标 = {{停滞欠H&R, 停滞手动}}，实际 {len(got)} 个")
    by = {t["hash"]: t for t in targets}
    _ok(by[h_owed]["hr_owed"] is True and by[h_owed]["hr_need_h"] == 24.0,
        "欠 H&R 目标带 hr_need_h=24.0")
    _ok(by[h_manual]["manual"] is True and by[h_manual]["hr_owed"] is False,
        "手动目标 manual=True 且不欠 H&R")
    for t in targets:
        _ok("reason_not_reuse" in t and "不可辅种" in t["reason_not_reuse"],
            f"target {t['hash'][:8]}… 带 reason_not_reuse（未下完不可辅种）")
        _ok(isinstance(t.get("reason_chain"), list) and t["reason_chain"],
            f"target {t['hash'][:8]}… 带非空 reason_chain")
        for rc in t["reason_chain"]:
            for k in ("rule", "verdict", "inputs", "source_of_truth", "at"):
                _ok(k in rc, f"reason_chain 单条含 {k!r}（rule={rc.get('rule')}）")
    # 排除项
    _ok(h_active not in got and h_done not in got and h_idle not in got
        and h_cross not in got and h_recent not in got,
        "在动/已完成/无关/已跨站/时长不足 全部排除")

    # =====================================================================
    # (c) 候选检索
    # =====================================================================
    print("\n[c] 候选检索 _rescue_candidates")
    hc = Harness()
    target = {"title": "Some.Movie.2024.1080p.BluRay.x264-FLUX", "site": "目标站",
              "size_gb": 1.0}
    hc.name2domain = {"学校": "pt.btschool.club", "目标站": "target.org",
                      "咖啡": "coffee.org", "红豆饭": "hd.ai"}
    hc.rules_hr = {"pt.btschool.club": True,   # 有 H&R → 排除（学校）
                   "coffee.org": False,         # 无 H&R 但有源 0 → 排除
                   "hd.ai": False,              # 无 H&R 且有源 → 候选
                   "target.org": False}
    hc.site_list = [{"id": 1, "name": "目标站", "domain": "target.org"},
                    {"id": 2, "name": "学校", "domain": "pt.btschool.club"},
                    {"id": 3, "name": "咖啡", "domain": "coffee.org"},
                    {"id": 4, "name": "红豆饭", "domain": "hd.ai"}]
    hc.domain_to_id = {"target.org": 1}
    hc._downloader.fp_by_hash = {"": _fp(hc._torrent_bytes)}
    hc.mp_hits = [
        _hit("Some.Movie.2024.1080p.BluRay.x264-FLUX", 2, "学校", 10),      # H&R → 排除
        _hit("Some.Movie.2024.1080p.BluRay.x264-FLUX", 3, "咖啡", 0),       # 无源 → 排除
        _hit("Some Movie 2024 1080p BluRay x264 FLUX", 4, "红豆饭", 25),    # 候选
        _hit("Some.Movie.2024.1080p.BluRay.x264.10bit-FLUX", 4, "红豆饭", 30),  # 10bit → 绝不进候选
    ]
    res = hc._rescue_candidates(target)
    cands = res["candidates"]
    _ok(len(cands) == 1, f"候选恰 1 条（{len(cands)}）")
    _ok(cands[0]["domain"] == "hd.ai" and cands[0]["seeders"] == 25, "候选来自无 H&R 且有源的红豆饭")
    _ok(all(c["title"].lower().find("10bit") < 0 for c in cands), "10bit 标题绝不进候选")
    skip_sites = {s["site"] for s in res["skipped"]}
    _ok("pt.btschool.club" in skip_sites, "学校（有 H&R）进排除证据")
    _ok(any(s["site"] == "coffee.org" and "无源" in s["reason"] for s in res["skipped"]),
        "咖啡（无源）进排除证据")
    # 无其它站点可搜
    hc.site_list = []
    res2 = hc._rescue_candidates(target)
    _ok(res2["candidates"] == [] and res2["skipped"], "无其它站点 → 空候选 + 排除说明")

    # =====================================================================
    # (d) 写操作
    # =====================================================================
    print("\n[d] 写操作 _rescue_apply（干跑 / confirm 闸门 / 真写）")
    hw = Harness()
    hw_t = _hex(8)
    hw.snap = {hw_t: _torrent(hw_t, "Some.Movie.2024.1080p.BluRay.x264-FLUX",
                              progress=0.364, dlspeed=0.0,
                              added_on=now - 10 * 3600, downloaded=0.0,
                              save_path="/dl")}
    hw.manual = set()

    def _hr_w(site, torrent, snap=None):
        return (True, 24.0, 0.0, "hrbill")
    hw._hr_obligation = _hr_w
    hw.name2domain = {"红豆饭": "hd.ai"}
    hw.rules_hr = {"hd.ai": False}
    hw.site_list = [{"id": 4, "name": "红豆饭", "domain": "hd.ai"}]
    hw.domain_to_id = {}
    hw._downloader.fp_by_hash = {hw_t: _fp(hw._torrent_bytes)}
    hw.mp_hits = [_hit("Some Movie 2024 1080p BluRay x264 FLUX", 4, "红豆饭", 25)]

    # 默认（dry=None, confirm=None）→ 干跑
    r1 = hw._rescue_apply([hw_t], dry=None, confirm=None)
    _ok(r1.get("dry_run") is True and r1.get("would_add") == 1, "默认干跑：would_add=1、未写")
    _ok(len(hw._downloader.added) == 0, "干跑不落任何 add_torrent")
    _ok(any(p.get("action") == "add" and p.get("dry") for p in r1["plan"]), "计划含 add(dry) 项")

    # confirm 缺位 → 拒绝
    r2 = hw._rescue_apply([hw_t], dry=False, confirm=False)
    _ok(r2.get("dry_run") is False and r2.get("added") == 0, "confirm 缺位 → added=0")
    _ok(any(p.get("reason") == "需 confirm=1" for p in r2["plan"]), "confirm 缺位 → 计划标注需 confirm=1")
    _ok(len(hw._downloader.added) == 0, "confirm 缺位不写")

    # confirm=1 → 真写
    r3 = hw._rescue_apply([hw_t], dry=False, confirm=True)
    _ok(r3.get("added") == 1, f"confirm=1 → added=1（{r3.get('added')}）")
    _ok(len(hw._downloader.added) == 1, "真写调用 1 次 add_torrent")
    _ok(hw._downloader.added[0]["tag"] == RESCUE_TAG, "副本打补源标签 RESCUE_TAG")
    _ok(hw._downloader.added[0]["download_dir"] == "/dl", "副本落到目标保存目录")
    _ok(hw._downloader.added[0].get("site_domain") == "hd.ai", "写时带 site_domain（下载即开账）")
    _ok(any(r.get("ok") and r.get("new_hash") for r in r3["results"]), "结果含 ok + new_hash")

    # 无候选 → 计划 skip（不写）
    hw.mp_hits = []
    r4 = hw._rescue_apply([hw_t], dry=False, confirm=True)
    _ok(r4.get("added") == 0 and any(p.get("action") == "skip" for p in r4["plan"]),
        "无候选 → skip、不写")

    # =====================================================================
    # (e) AI 入口
    # =====================================================================
    print("\n[e] AI 入口 agent_rescue（只读信封）")
    he = Harness()
    he_t = _hex(9)
    he.snap = {he_t: _torrent(he_t, "征途 2160p", progress=0.364, dlspeed=0.0,
                              added_on=now - 10 * 3600, downloaded=0.0)}
    he._hr_obligation = _hr_w
    he.name2domain = {"学校": "pt.btschool.club"}
    he.rules_hr = {"pt.btschool.club": True}
    he.site_list = [{"id": 2, "name": "学校", "domain": "pt.btschool.club"}]
    resp = he.agent_rescue()
    _ok(resp["ok"] is True and resp["code"] == "ok", "agent_rescue 成功信封")
    d = resp["data"]
    _ok(len(d["targets"]) == 1 and d["targets"][0]["hash"] == he_t, "agent_rescue targets 含该种")
    _ok(any(s["domain"] == "pt.btschool.club" for s in d["skipped_sites"]),
        "agent_rescue skipped_sites 含学校（有 H&R 不能当源）")
    _ok("stall_hours" in d["settings"] and "reason_not_reuse" in d["settings"],
        "agent_rescue settings 含 stall_hours + reason_not_reuse")

    # =====================================================================
    # (f) 来源站护栏唯一判定（11.5.0）：hr != False 一律禁当补源
    print("\n[f] rescue_source_blocked —— 补源来源站唯一判定")
    _ok(rescue.rescue_source_blocked(False) is False, "hr=False（无 H&R）→ 允许当补源")
    _ok(rescue.rescue_source_blocked(True) is True, "hr=True（有 H&R）→ 禁用")
    _ok(rescue.rescue_source_blocked(None) is True, "hr=None（未知）→ 保守禁用")
    _ok(rescue.rescue_source_blocked("") is True, "空值 → 保守禁用")
    # 11.7.0：逐种 H&R 站（站点级 hr=False 但逐种标记开）→ 保守禁用（防空手引入逐种债）
    _ok(rescue.rescue_source_blocked(False, True) is True,
        "逐种 H&R 站（hr=False + per_torrent_hr）→ 保守禁用")
    _ok(rescue.rescue_source_blocked(False, False) is False,
        "hr=False 且非逐种站 → 允许当补源")
    _src = (ROOT / "features" / "rescue.py").read_text(encoding="utf-8")
    _ok(_src.count("rescue_source_blocked(flag, pthr)") >= 3,
        "候选过滤 + 站点排除清单都改用同一判定（单一真值源，含逐种站参）")

    # =====================================================================
    # (g) IYUU 指纹索引候选 + 落地校验（11.6.0）
    print("\n[g] IYUU 指纹索引候选 + 落地校验（拉 .torrent 比特征码）")
    hg = Harness()
    hg_t = _hex(11)
    TB = _tb("Some.Movie.2024.1080p.BluRay.x264-FLUX.mkv", 1234567)
    BAD = _tb("Other.Movie.2024.1080p.BluRay.x264-FLUX.mkv", 999999)
    hg.snap = {hg_t: _torrent(hg_t, "Some.Movie.2024.1080p.BluRay.x264-FLUX",
                              progress=0.30, dlspeed=0.0, added_on=now - 10 * 3600,
                              save_path="/dl")}
    hg._hr_obligation = _hr_w
    hg.name2domain = {"CARPT": "carpt.net", "红豆饭": "hd.ai", "咖啡": "coffee.org",
                      "Depth": "dstudio.me"}
    hg.rules_hr = {"carpt.net": True, "hd.ai": False, "coffee.org": False,
                   "dstudio.me": True}
    hg.site_list = [{"id": 13, "name": "CARPT", "domain": "carpt.net"},
                    {"id": 2, "name": "红豆饭", "domain": "hd.ai"},
                    {"id": 3, "name": "咖啡", "domain": "coffee.org"},
                    {"id": 15, "name": "Depth", "domain": "dstudio.me"}]
    hg._downloader.fp_by_hash = {hg_t: _fp(TB)}
    hg.reseed_site_map = {
        57: {"sid": 57, "name": "红豆饭", "domain": "hd.ai", "site_id": 2},
        107: {"sid": 107, "name": "咖啡", "domain": "coffee.org", "site_id": 3},
        13: {"sid": 13, "name": "CARPT", "domain": "carpt.net", "site_id": 13},
        15: {"sid": 15, "name": "Depth", "domain": "dstudio.me", "site_id": 15},
    }
    hg.reseed_urls = {(57, 1): "http://hd.ai/dl/1",
                      (107, 2): "http://coffee.org/dl/2",
                      (13, 3): "http://carpt.net/dl/3",
                      (15, 4): "http://dstudio.me/dl/4"}
    hg._downloader.fetch_bytes = {"http://hd.ai/dl/1": TB,
                                   "http://coffee.org/dl/2": BAD,
                                   "http://carpt.net/dl/3": TB,
                                   "http://dstudio.me/dl/4": TB}
    hg._iyuu_client = _FakeIYUU(
        rows=[{"info_hash": "aa" * 20, "sid": 57, "torrent_id": 1},
              {"info_hash": "bb" * 20, "sid": 107, "torrent_id": 2},
              {"info_hash": "cc" * 20, "sid": 13, "torrent_id": 3},
              {"info_hash": "dd" * 20, "sid": 15, "torrent_id": 4}],
        sid_by_domain={"hd.ai": 57, "coffee.org": 107, "carpt.net": 13, "dstudio.me": 15},
    )
    gtarget = {"hash": hg_t, "title": "Some.Movie.2024.1080p.BluRay.x264-FLUX",
               "site": "CARPT", "size_gb": 0.001}
    gres = hg._rescue_candidates(gtarget)
    _ok(gres["source"] == "iyuu", f"命中 IYUU 路径（source={gres['source']}）")
    _ok(len(gres["candidates"]) == 1, f"校验通过候选恰 1 条（{len(gres['candidates'])}）")
    gc0 = gres["candidates"][0]
    _ok(gc0["source"] == "iyuu" and gc0["verified"] is True, "候选来自 IYUU 且 verified=True")
    _ok(gc0["domain"] == "hd.ai" and gc0["iyuu_sid"] == 57, "候选 = 红豆饭（无 H&R）")
    _ok(gc0["fingerprint"] == _fp(TB), "候选特征码 = 目标种特征码（同内容）")
    rules = [r["rule"] for r in gc0["reason_chain"]]
    _ok(rules == ["rescue/candidate_source", "rescue/source_guard", "rescue/fingerprint_check"],
        f"候选带完整依据链（{rules}）")
    gskip = " | ".join(f"{s['site']}:{s['reason']}" for s in gres["skipped"])
    _ok("dstudio.me" in gskip and "H&R" in gskip, f"hr 站（Depth Studio）进排除证据（{gskip[:70]}）")
    _ok("carpt.net" in gskip and "自身" in gskip, "目标站自身不当补源")
    _ok("coffee.org" in gskip and "特征码" in gskip, "近邻非同封装（咖啡）被指纹校验拦下")
    _ok((57, "rescue", 1) in hg.pv_spent and (107, "rescue", 1) in hg.pv_spent,
        "校验抓取计了 PV（红豆饭 + 咖啡）")
    _ok((15, "rescue", 1) not in hg.pv_spent and (13, "rescue", 1) not in hg.pv_spent,
        "hr 站一个 PV 都不花（候选级就排除）")

    # 写：复用校验缓存（不重复抓）+ 带 site_domain
    before_fetches = len(hg._downloader.fetch_calls)
    gr = hg._rescue_apply([hg_t], dry=False, confirm=True)
    _ok(gr.get("added") == 1, f"IYUU 候选可真写（added={gr.get('added')}）")
    _ok(len(hg._downloader.fetch_calls) == before_fetches, "写时复用校验缓存，不重复抓取")
    _ok(hg._downloader.added[-1]["tag"] == RESCUE_TAG, "IYUU 副本同打 RESCUE_TAG")
    _ok(hg._downloader.added[-1].get("site_domain") == "hd.ai", "IYUU 副本带 site_domain")
    _ok(gr["results"][0].get("candidate_fingerprint") == _fp(TB), "结果附候选特征码（可追溯）")

    # verify=0 → 不联网、不回 IYUU
    hv = Harness()
    hv_t = _hex(12)
    hv.snap = {hv_t: _torrent(hv_t, "Some.Movie.2024.1080p.BluRay.x264-FLUX",
                              progress=0.3, dlspeed=0.0, added_on=now - 10 * 3600)}
    hv._hr_obligation = _hr_w
    hv.name2domain = {"CARPT": "carpt.net"}
    hv.rules_hr = {"carpt.net": True}
    hv.site_list = [{"id": 13, "name": "CARPT", "domain": "carpt.net"}]
    hv._iyuu_client = _FakeIYUU(rows=[{"info_hash": "aa" * 20, "sid": 57, "torrent_id": 1}])
    hv._downloader.fetch_bytes = {"http://hd.ai/dl/1": TB}
    hv2 = hv._rescue_candidates({"hash": hv_t, "title": "x", "site": "CARPT"}, verify=False)
    _ok(len(hv._downloader.fetch_calls) == 0, "verify=False 不抓任何 .torrent（便宜调用）")
    _ok(not any(c.get("source") == "iyuu" for c in hv2["candidates"]),
        "verify=False 不出 IYUU 候选")

    # =====================================================================
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
