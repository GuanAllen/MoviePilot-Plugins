#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 野马PT 逐种 H&R 权威接口（11.9.0）离线回归测试（真跑，不需要 MoviePilot 环境）。

覆盖 ``features/yema.py``：
  - ``yema_row_obligation`` / ``yema_row_view``：站点行 → 义务判定（逐种开关 + 状态，保守方向）
  - ``_yema_rows``：分页（pageSize=20）/ 吃全 / ``truncated`` / ``success:false`` → 报错（不猜）
  - ``_yema_reconcile``：站点（权威）× 本机 × 账本 → ``missing_local`` / ``present_no_bill`` /
    ``unknown_bills`` / ``done_rows``；无缓存时 ``live=0`` 如实说「无缓存」
  - ``_yema_apply``：默认干跑；``confirm=1`` 才补开账单（**只增保护**，且幂等）
  - ``_yema_absolve``：默认干跑（**零网络写**）；``confirm=1`` 才真写；缺 tid → 拒绝
  - ``_yema_round``：6h 周期门（不碰共享 meta）
  - 出口无密：报告里不出现 cookie / apikey / token

用法：``python3 tools/test_yema.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PKG = "mf_yema_test"


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
yema = _load(PKG + ".features.yema", "features/yema.py")

HrBillsMixin = hrbills.HrBillsMixin
YemaHrMixin = yema.YemaHrMixin


def _hex(n: int) -> str:
    return (f"{n:040x}")[-40:]


def _torrent_bytes(tag: str) -> bytes:
    info = {b"name": tag.encode("utf-8"), b"length": 1000, b"piece length": 16384,
            b"pieces": b"0" * 20}
    return fingerprint.bencode({b"info": info, b"announce": b"https://tracker.yemapt.org/announce"})


def _hash_of(tag: str) -> str:
    return fingerprint.info_hash(_torrent_bytes(tag))


class _SiteStub:
    """``collect.site(sid)`` 的桩：只实现 post_json（按 path 分派）。"""

    def __init__(self, rows, count=0, fail=False, success_false=False, absolve_ok=True):
        self.rows = rows
        self.count = count
        self.fail = fail
        self.success_false = success_false
        self.absolve_ok = absolve_ok
        self.calls: list = []

    def post_json(self, path, payload=None, kind="", ttl=None, force=False, cache=True):
        self.calls.append({"path": path, "payload": payload, "cache": cache, "force": force})
        if self.fail:
            return {"ok": False, "error": "HTTP 503"}
        if path.endswith("fetchUserTorrentCount"):
            return {"ok": True, "data": self.count}
        if path.endswith("fetchUserTorrentList"):
            if self.success_false:
                return {"ok": True, "data": {"success": False, "showType": 0}}
            page = int(((payload or {}).get("pageParam") or {}).get("current") or 1)
            size = int(((payload or {}).get("pageParam") or {}).get("pageSize") or 20)
            chunk = self.rows[(page - 1) * size: page * size]
            return {"ok": True, "data": {"success": True, "data": chunk}}
        if path.endswith("absolve"):
            if not self.absolve_ok:
                return {"ok": True, "data": {"success": False, "errorMessage": "积分不足"}}
            return {"ok": True, "data": {"success": True, "data": None}}
        return {"ok": True, "data": {}}


class _Collect:
    def __init__(self, site_stub):
        self._s = site_stub

    def site(self, sid):
        return self._s


class _Downloader:
    def __init__(self):
        self.fetched: list = []

    def fetch_torrent_bytes(self, url, cookie=None, user_agent=None, referer=None):
        self.fetched.append(url)
        try:
            tid = url.split("id=")[-1].split("&")[0]
        except Exception:  # noqa: BLE001
            tid = "x"
        return _torrent_bytes(f"tid{tid}")


class _SimpleRules:
    def __init__(self, rows):
        self._rows = rows

    def items(self):
        return dict(self._rows)

    def get(self, dom):
        return dict(self._rows.get(dom) or {})


class Harness(YemaHrMixin, HrBillsMixin):
    """带桩的最小插件实例（组合两个 mixin，跟真插件一样）。"""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._hot = None
        self._kv = None
        self.sites = []
        self.site_hr = {}
        self.rules = {}
        self.torrents = {}
        self.bills = {}
        self.http = None
        self.site_stub = None
        self.dl = _Downloader()
        self.logs = []

    # ---- 依赖桩 ----
    def get_data_path(self):
        return self._dir

    def _log(self, msg, level="info"):
        self.logs.append((level, msg))

    def _dbg(self, msg):
        self.logs.append(("debug", msg))

    def _list_sites(self):
        return list(self.sites)

    def _reseed_mp_sites(self):
        return list(self.sites)

    def _site_domain_by_name(self, name):
        return str(name or "").strip().lower()

    def _site_hr_flag(self, dom):
        return self.site_hr.get(dom)

    def _site_rules(self):
        return _SimpleRules(self.rules)

    def _collect_ref(self):
        return _Collect(self.site_stub) if self.site_stub is not None else None

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _reseed_site_conn(self, sid):
        return {"cookie": "SECRET-COOKIE", "ua": "ua", "url": "https://www.yemapt.org"}

    def _downloader_ops(self):  # noqa: F811
        return self.dl

    def _get_downloader(self, kind="qbittorrent"):
        return self.dl

    def _get_site(self, sid):
        return None

    def _preload_bills(self):
        store = self._hrbills_store()
        for h, b in self.bills.items():
            store.put(h, b)
        return store


CHECKS = 0


def _ok(cond: bool, msg: str) -> None:
    global CHECKS
    assert cond, f"❌ {msg}"
    CHECKS += 1
    print(f"  ✅ {msg}")


def main() -> int:  # noqa: WPS213
    print("=" * 64)
    print("魔流 · 野马PT 逐种 H&R 权威接口（11.9.0）回归测试")
    print("=" * 64)

    tmp = tempfile.mkdtemp(prefix="yema_test_")
    h = Harness(Path(tmp))
    h._dir = Path(tmp)
    h.sites = [{"id": 16, "name": "YemaPT", "domain": "yemapt.org", "url": "https://www.yemapt.org/"},
               {"id": 13, "name": "CARPT", "domain": "carpt.net"}]
    h.site_hr = {"yemapt.org": False, "carpt.net": True}
    h.rules = {"yemapt.org": {"hr": False, "per_torrent_hr": True, "seed_hours": 24.0}}

    # ---- 0) 常量 / 开关 ----
    print("\n[0] 常量与开关")
    _ok(yema.YEMA_ENABLED is True, "YEMA_ENABLED = True（一键回退开关）")
    _ok(yema.YEMA_ABSOLVE_ENABLED is True, "YEMA_ABSOLVE_ENABLED = True（写路径开关）")
    _ok(yema.YEMA_PAGE_SIZE == 20, "分页 pageSize = 20（站点 pageSize>20 返回 0 行）")
    _ok(yema.YEMA_DOMAINS == ("yemapt.org", "www.yemapt.org"), "域名白名单 = yemapt.org")

    # ---- 1) 义务判定（纯函数） ----
    print("\n[1] yema_row_obligation / yema_row_view")
    _ok(yema.yema_row_obligation({"hrPunishEnable": True, "hrStatus": "Running"})["owes"] is True,
        "punish=True + Running → 欠")
    _ok(yema.yema_row_obligation({"hrPunishEnable": True, "hrStatus": "NotStart"})["owes"] is True,
        "punish=True + NotStart → 欠（未开始也算）")
    _ok(yema.yema_row_obligation({"hrPunishEnable": True, "hrStatus": "Weird"})["owes"] is True,
        "punish=True + 未知状态 → 保守算欠")
    _ok(yema.yema_row_obligation({"hrPunishEnable": True, "hrStatus": "Pass"})["owes"] is False,
        "punish=True + Pass → 不欠（已通过）")
    _ok(yema.yema_row_obligation({"hrPunishEnable": True, "hrStatus": "Absolve"})["owes"] is False,
        "punish=True + Absolve → 不欠（已免罪）")
    _ok(yema.yema_row_obligation({"hrPunishEnable": False, "hrStatus": "Running"})["owes"] is False,
        "punish=False + Running → 不欠（发布者未开考核）")
    _v = yema.yema_row_view({"torrentId": 15855, "showName": "杀人回忆", "fileSize": 6 * 1024 ** 3,
                             "hrPunishEnable": False, "hrStatus": "NotStart", "isSeeder": "y"})
    _ok(_v["size_gb"] == 6.0 and _v["tid"] == 15855 and _v["is_seeder"] is True,
        f"视图：size_gb / tid / is_seeder（{_v['size_gb']}/{_v['tid']}/{_v['is_seeder']}）")
    _ok(yema.yema_is_yema_domain("www.yemapt.org") and not yema.yema_is_yema_domain("carpt.net"),
        "yema_is_yema_domain 认子域、不认他站")

    # ---- 2) 列表分页 ----
    print("\n[2] _yema_rows（分页 / 吃全 / 失败语义）")
    rows = [{"torrentId": 1000 + i, "showName": f"T{i}", "hrPunishEnable": False,
             "hrStatus": "NotStart", "fileSize": 1024} for i in range(25)]
    h.site_stub = _SiteStub(rows, count=25)
    got = h._yema_rows()
    _ok(got["ok"] is True and len(got["rows"]) == 25, f"25 条分 2 页吃全（{len(got['rows'])}）")
    _ok(got["pages"] == 2, "页数 = 2（第 2 页 5 行 < 20 即停）")
    _ok(got["truncated"] is False, "未撞页数上限 → truncated=False")
    _ok(h._yema_count() == 25, "站点总数 = 25")
    h.site_stub = _SiteStub(rows, success_false=True)
    bad = h._yema_rows()
    _ok(bad["ok"] is False and "success=false" in bad["error"],
        f"success:false → 如实报错（{bad['error'][:24]}…）")
    h.site_stub = _SiteStub(rows, fail=True)
    _ok(h._yema_rows()["ok"] is False, "HTTP 失败 → ok=False")

    # ---- 3) 对账（live） ----
    print("\n[3] _yema_reconcile（站点 × 本机 × 账本）")
    h.site_stub = _SiteStub([
        {"torrentId": 1, "showName": "Owes And Local No Bill", "hrPunishEnable": True,
         "hrStatus": "Running", "fileSize": 5 * 1024 ** 3},
        {"torrentId": 2, "showName": "Owes And Missing", "hrPunishEnable": True,
         "hrStatus": "NotStart", "fileSize": 4 * 1024 ** 3},
        {"torrentId": 3, "showName": "Owes And Protected", "hrPunishEnable": True,
         "hrStatus": "Running", "fileSize": 3 * 1024 ** 3},
        {"torrentId": 6, "showName": "Owes And No Bill At All", "hrPunishEnable": True,
         "hrStatus": "NotStart", "fileSize": 7 * 1024 ** 3},
        {"torrentId": 4, "showName": "Done", "hrPunishEnable": True,
         "hrStatus": "Absolve", "fileSize": 2 * 1024 ** 3},
        {"torrentId": 5, "showName": "No Punish", "hrPunishEnable": False,
         "hrStatus": "Running", "fileSize": 6 * 1024 ** 3},
    ], count=5)
    h1, h2, h3 = _hash_of("tid1"), _hash_of("tid2"), _hash_of("tid3")
    h6 = _hash_of("tid6")
    # 本机：1 / 3 / 6 有；2 没有
    h.torrents = {
        h1: types.SimpleNamespace(hash=h1, name="Owes And Local No Bill", size=5 * 1024 ** 3,
                                  tracker="https://tracker.yemapt.org/announce", state="stalledUP", tags=[]),
        h3: types.SimpleNamespace(hash=h3, name="Owes And Protected", size=3 * 1024 ** 3,
                                  tracker="https://tracker.yemapt.org/announce", state="uploading", tags=[]),
        h6: types.SimpleNamespace(hash=h6, name="Owes And No Bill At All", size=7 * 1024 ** 3,
                                  tracker="https://tracker.yemapt.org/announce", state="uploading", tags=[]),
        _hex(0xDEAD): types.SimpleNamespace(hash=_hex(0xDEAD), name="x",
                                            tracker="https://carpt.net/announce", tags=[]),
    }
    # 账本：3 有受保护账单；另有一张 rule=unknown 的野马账单（漏记候选）
    h.bills = {
        h3: {"site": "yemapt.org", "rule": "hit_and_run", "state": "active",
             "need_h": 24.0, "seeded_h": 3.0, "title": "Owes And Protected"},
        h1: {"site": "yemapt.org", "rule": "unknown", "state": "pending",
             "need_h": 24.0, "seeded_h": 0.0, "title": "Owes And Local No Bill"},
    }
    h._preload_bills()
    rep = h._yema_reconcile(live=1, force=1)
    _ok(rep["ok"] is True, "对账成功")
    _ok(rep["rows_total"] == 6 and rep["obligations_total"] == 4,
        f"6 行 / 义务 4 行（{rep['rows_total']}/{rep['obligations_total']}）")
    _ok([r["tid"] for r in rep["missing_local"]] == [2],
        f"missing_local = tid2（{[r['tid'] for r in rep['missing_local']]}）")
    _ok(sorted(r["tid"] for r in rep["present_no_bill"]) == [1, 6],
        f"present_no_bill = tid1+tid6（{sorted(r['tid'] for r in rep['present_no_bill'])}）")
    _ok(rep["unverified"] == [], "无 unverified（都能算出 infohash）")
    _ok(len(rep["unknown_bills"]) == 1 and rep["unknown_bills"][0]["hash"] == h1,
        "unknown_bills = tid1 的账单（rule=unknown 可见）")
    _ok(rep["unknown_bills"][0]["tid"] == 1, "unknown 账单能反查到站点 tid（走 tid 索引）")
    _ok([r["tid"] for r in rep["done_rows"]] == [4], "done_rows 只收 Pass/Absolve（tid4）")
    _ok(rep["hash_fetched"] == 4 and rep["cache_hits"] == 0, "首次拉 4 个 .torrent 算 hash")

    # 再跑一轮：hash 全部吃缓存
    rep2 = h._yema_reconcile(live=1, force=1)
    _ok(rep2["hash_fetched"] == 0 and rep2["cache_hits"] == 4, "第二轮 hash 全走缓存（0 拉种）")

    # live=0 读缓存
    rep_c = h._yema_reconcile(live=0)
    _ok(rep_c.get("cached") is True and rep_c["ok"] is True, "live=0 读上一轮缓存报告")

    # 出口无密
    blob = json.dumps(rep, ensure_ascii=False)
    _ok("SECRET-COOKIE" not in blob and "apikey" not in blob.lower(), "报告出口无 cookie/apikey")

    # ---- 4) 补开账单（只增保护） ----
    print("\n[4] _yema_apply（默认干跑；confirm=1 才写）")
    plan = h._yema_apply(confirm=0)
    _ok(plan["dry_run"] is True and plan["would_open"] == 2, "干跑：待处理 2 条")
    _ok(sorted(x["action"] for x in plan["plan"]) == ["open", "upgrade"],
        "干跑如实标出动作（open + upgrade）")
    _ok(h._hrbills_store().get(h1).get("rule") == "unknown", "干跑不改账本（仍 unknown）")
    done = h._yema_apply(confirm=1)
    _ok(done["dry_run"] is False and done["opened"] == 1 and done["upgraded"] == 1,
        f"confirm=1：新开 1 / 升级 1（{done['opened']}/{done['upgraded']}）")
    _ok(h._hrbills_store().get(h1).get("rule") == "hit_and_run"
        and h._hrbills_store().get(h1).get("state") == "active",
        "存量 unknown 账单 → 升级为 hit_and_run / active（受保护）")
    _ok(h._hrbills_store().get(h6).get("rule") == "hit_and_run",
        "无账单的种 → 新开 hit_and_run 账单")
    again = h._yema_apply(confirm=1)
    _ok(again["opened"] == 0 and again["upgraded"] == 0, "再跑不重复（幂等：两条都已受保护）")

    # ---- 5) 免罪（写路径） ----
    print("\n[5] _yema_absolve（默认干跑 = 零写）")
    h.site_stub = _SiteStub([], count=0)
    h.site_stub.absolve_ok = True
    dry = h._yema_absolve(9, confirm=0)
    _ok(dry["dry_run"] is True and dry["written"] is False, "干跑：written=False")
    _ok(all(not c["path"].endswith("absolve") for c in h.site_stub.calls),
        "干跑**没有**发出 absolve 请求（零副作用）")
    _ok("扣积分" in dry["cost_note"], "干跑如实报成本（扣积分/不可逆）")
    _ok(h._yema_absolve("", confirm=1).get("ok") is False, "缺 tid → 拒绝")
    _ok(h._yema_absolve("abc", confirm=1).get("ok") is False, "tid 非数字 → 拒绝")
    wr = h._yema_absolve(9, confirm=1)
    _ok(wr["written"] is True and any(c["path"].endswith("absolve") for c in h.site_stub.calls),
        "confirm=1：真写 absolve")
    _ok(any(not c["cache"] for c in h.site_stub.calls if c["path"].endswith("absolve")),
        "写操作 cache=False（绝不缓存副作用）")
    h.site_stub.absolve_ok = False
    bad = h._yema_absolve(9, confirm=1)
    _ok(bad["ok"] is False and bad["written"] is False, "站点 success:false → 如实报失败")

    # ---- 6) worker 周期门 ----
    print("\n[6] _yema_round（6h 周期门）")
    h.site_stub = _SiteStub([{"torrentId": 7, "showName": "X", "hrPunishEnable": True,
                              "hrStatus": "Running", "fileSize": 1024}], count=1)
    first = h._yema_round(force=1)
    _ok(first.get("ok") is True, "force=1 真跑一轮")
    second = h._yema_round()
    _ok(second.get("skipped") == "not_due", f"6h 内再跑 → not_due（{second.get('skipped')}）")

    print("\n" + "=" * 64)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as _e:
        print(str(_e))
        sys.exit(1)
    except Exception as _e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"💥 异常：{_e}")
        sys.exit(1)
