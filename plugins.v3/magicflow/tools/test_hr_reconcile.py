#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 站点 myhr 定期对账（11.8.0）离线回归测试（真跑，不需要 MoviePilot 环境）。

覆盖 ``features/hrbills.py`` 第三视角对账：
  - ``_hr_myhr_parse``：NexusPHP ``myhr.php`` 行解析（hr_id / tid / title / size / need_left）
    + 「可识别但空」→ ``[]`` + 「不可识别」→ ``None``
  - ``_hr_reconcile_site``：三方对账（missing_local / present_no_bill / safe_rotate_candidate）
    + 抓取失败 → ``ok=False`` 且**零结论**（绝不从半份数据推「站点说干净」）
  - ``_hr_reconcile_apply``：默认干跑（不写）；``confirm=1`` 才重下
  - ``_hr_reconcile_add_one``：同站重下 + 「已在下载器则跳过」
  - ``HrReconcileCache``：tid 索引 / 退避 / 上次报告 落盘
  - 常量：``HR_RECONCILE_ENABLED`` 一键回退开关

用法：``python3 tools/test_hr_reconcile.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PKG = "mf_hr_reconcile_test"


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
HrReconcileCache = hrbills.HrReconcileCache


def _hex(n: int) -> str:
    return (f"{n:040x}")[-40:]


def _torrent_bytes(name: str) -> bytes:
    info = {b"name": name.encode("utf-8"), b"length": 1000, b"piece length": 16384,
            b"pieces": b"0" * 20}
    meta = {b"info": info, b"announce": b"http://carpt.net/announce"}
    return fingerprint.bencode(meta)


MYHR_PAGE1 = """<html><body><table id="myhr">
<tr><td>8800001</td><td><a href="details.php?id=209930">牧神记 S01E102</a></td>
<td>2.116 GB</td><td>19:47:35</td></tr>
<tr><td>8800002</td><td><a href="details.php?id=209931">Abang Adik 2026</a></td>
<td>4.5 GB</td><td>12:00:00</td></tr>
</table></body></html>"""

MYHR_EMPTY_OK = "<html><body><div>myhr 暂无 H&R 记录</div></body></html>"

# ★ 11.8.1 实测坑样本：头部（用户名 / 新人考核公告）里的 details.php?id=<uid> 噪声行
#   + 行内嵌套 <table> 导致同一行被重复匹配 + CARPT 真实列序
#   （上传量 | 下载量 | 分享率 | 还需做种时间 | 下载完成时间 | 剩余考察时间 | 操作）
MYHR_NOISY = """<html><body><table class="main">
<tr><td colspan=2>欢迎回来, alanguan <a href="details.php?id=59688">alanguan</a> 上传量： 30.26 GB</td></tr>
<tr><td colspan=6>离新人考核结束还有 <a href="details.php?id=59688">考核</a> 上传量： 已通过</td></tr>
<tr><td>8300140</td><td><a href="details.php?id=209955">A Good Day to Ascend S01E12 2026</a></td>
<td>0.003 GB</td><td>10.00 GB</td><td>0.000</td><td>17:38:47</td><td>2026-10-05 21:03</td><td>9天20:04:16</td><td>购买免罪</td></tr>
<tr><td>8294339</td><td><a href="details.php?id=209821">The Old Story of Yu Hong 2026 S01 E14-E17 2160p WEB-DL H265 DV DDP5.1-PTerWEB</a></td>
<td>224.50 MB</td><td>21.83 GB</td><td>0.010</td><td>19:28:20</td><td>2026-10-05 13:05</td><td>5天20:02:04</td><td>购买免罪</td></tr>
</table></body></html>"""

# 标题被套在子 <table> 里 → 行会被 ``</tr>`` 切断 → 保守返回 None（退避），**绝不当作无欠**
MYHR_NESTED = """<html><body><table id="hr-table"><tr><td class='colhead'>还需做种时间</td></tr>
<tr><td>8294339</td><td><table><tr><td><a href="details.php?id=209821">Nested Title</a></td></tr></table></td>
<td>19:28:20</td></tr></table></body></html>"""
MYHR_GARBAGE = "<html><body>please login</body></html>"


class _Resp:
    def __init__(self, text: str, ok: bool = True, error: str = ""):
        self.text = text
        self.ok = ok
        self.error = error


class _Http:
    def __init__(self, page_text: str, fail: bool = False, empty_after: int = -1):
        self.page_text = page_text
        self.fail = fail
        self.empty_after = empty_after
        self.calls: list = []

    def text(self, site_id, url, kind="", ttl=0.0):
        self.calls.append((site_id, url, kind))
        if self.fail:
            return _Resp("", ok=False, error="HTTP 503")
        if "page=0" in url or url.endswith("/myhr.php"):
            return _Resp(self.page_text)
        return _Resp("<html><body>details.php</body></html>")   # 第 2 页起：可识别但空


class _Collect:
    def __init__(self, http):
        self.http = http


class _Downloader:
    def __init__(self, torrents: dict):
        self.torrents = torrents
        self.added: list = []
        self.next_bytes = None

    def fetch_torrent_bytes(self, url, cookie=None, user_agent=None, referer=None):
        self.last_fetch = url
        if self.next_bytes is not None:
            return self.next_bytes
        return _torrent_bytes("x")

    def add_torrent(self, content, download_dir, tag, category="", upload_limit=0,
                    download_limit=0, cookie=None, user_agent=None, proxies=None,
                    site_domain="", hit_and_run=False):
        self.added.append({"dir": download_dir, "tag": tag, "domain": site_domain})
        return _hex(0xABCDEF), ""


class _SimpleRules:
    def __init__(self, rows):
        self._rows = rows

    def items(self):
        return dict(self._rows)

    def get(self, dom):
        return dict(self._rows.get(dom) or {})


class Harness(HrBillsMixin):
    """带桩的最小插件实例，只实现站点对账用到的依赖。"""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._hot = None
        self.site_hr = {}
        self.rules = {}
        self.sites = []
        self.torrents = {}          # hash -> SimpleNamespace
        self.bills = {}             # hash -> bill dict
        self.task_cfgs = {}
        self._task_configs = {}
        self.http = None
        self.dl = _Downloader({})
        self.logs = []

    # ---- 依赖桩 ----
    def get_data_path(self):
        return self._data_dir

    def _log(self, msg, level="info"):
        self.logs.append((level, msg))

    def _dbg(self, msg):
        self.logs.append(("debug", msg))

    def _list_sites(self):
        return list(self.sites)

    def _site_hr_flag(self, dom):
        return self.site_hr.get(dom)

    def _site_rules(self):
        return _SimpleRules(self.rules)

    def _collect_ref(self):
        return _Collect(self.http)

    def _pv_allow(self, site_id, kind="browse", want=1):
        return True

    def _pv_spend(self, site_id, kind="browse", n=1):
        return n

    def _tag_all_torrents(self):
        return dict(self.torrents)

    def _reseed_site_conn(self, sid):
        return {"cookie": "c", "ua": "ua", "url": "https://carpt.net"}

    def _get_downloader(self, kind="qbittorrent"):
        return self.dl

    def _get_site(self, sid):
        return None

    def _hr_domain(self, site, torrent):
        tr = str(getattr(torrent, "tracker", "") or "")
        return tr.split("://")[-1].split("/")[0].split(":")[0].strip().lower()

    # 账单库：直接用真 store（HrBillsMixin._hrbills_store 走 get_data_path/_hot）
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
    print("魔流 · 站点 myhr 定期对账（第三视角）回归测试")
    print("=" * 64)

    tmp = tempfile.mkdtemp(prefix="hr_reconcile_test_")
    h = Harness(Path(tmp))
    h.sites = [{"id": 13, "name": "CARPT", "domain": "carpt.net"},
               {"id": 2, "name": "红豆饭", "domain": "hdfans.org"}]
    h.site_hr = {"carpt.net": True, "hdfans.org": False}
    h.rules = {"carpt.net": {"hr": True, "seed_hours": 24.0}}

    # ---- 0) 常量 / 回退开关 ----
    print("\n[0] 常量")
    _ok(hrbills.HR_RECONCILE_ENABLED is True, "HR_RECONCILE_ENABLED = True（一键回退开关）")
    _ok(abs(hrbills.HR_RECONCILE_HOURS - 6.0) < 1e-9, "对账周期 = 6h")
    _ok(hrbills.HR_RECONCILE_BACKOFF_HOURS[-1] == 24.0, "退避阶梯封顶 24h")

    # ---- 1) myhr 页解析 ----
    print("\n[1] _hr_myhr_parse")
    rows = hrbills._hr_myhr_parse(MYHR_PAGE1)
    _ok(isinstance(rows, list) and len(rows) == 2, f"解析出 2 行（{len(rows or [])}）")
    r0 = rows[0]
    _ok(r0["tid"] == "209930", f"tid = 209930（{r0['tid']}）")
    _ok(r0["hr_id"] == "8800001", f"hr_id = 8800001（{r0['hr_id']}）")
    _ok("牧神记" in r0["title"], f"title 含片名（{r0['title']}）")
    _ok(abs(r0["size_gb"] - 2.116) < 0.01, f"size_gb ≈ 2.116（{r0['size_gb']}）")
    _ok(r0["need_left"] == "19:47:35", f"need_left = 19:47:35（{r0['need_left']}）")
    _ok(hrbills._hr_myhr_parse(MYHR_EMPTY_OK) == [], "可识别但空 → []（= 无欠，不是解析失败）")
    _ok(hrbills._hr_myhr_parse(MYHR_GARBAGE) is None, "不可识别 → None（整页跳过，不当作无欠）")
    _ok(hrbills._hr_myhr_parse("") == [], "空串 → []")

    # ---- 2) 三方对账 ----
    print("\n[2] _hr_reconcile_site（三方对账）")
    h.http = _Http(MYHR_PAGE1)
    # 本机：tA 与记录 1 粗配（present, 无账单）；tB 与任何记录都不配（有 settled 账单）
    hA = _hex(0xA1)
    tA = types.SimpleNamespace(hash=hA, title="牧神记 S01E102", size=int(2.116 * 1024 ** 3),
                               tracker="https://carpt.net/announce", tags=[])
    hB = _hex(0xB2)
    tB = types.SimpleNamespace(hash=hB, title="Totally Unrelated", size=int(10 * 1024 ** 3),
                               tracker="https://carpt.net/announce", tags=[])
    h.torrents = {hA: tA, hB: tB}
    # 记录 2 需拉 .torrent → 造一个「本机没有」的 hash
    h.dl.next_bytes = _torrent_bytes("record2")
    hB_record2 = fingerprint.info_hash(h.dl.next_bytes)
    h.bills = {hB: {"site": "carpt.net", "rule": "site_hr", "state": "settled",
                    "need_h": 24.0, "seeded_h": 25.0}}
    h._preload_bills()
    rep = h._hr_reconcile_site("carpt.net")
    _ok(rep["ok"] is True, "对账成功")
    _ok(rep["records_total"] == 2, f"记录 2 条（{rep['records_total']}）")
    _ok(len(rep["missing_local"]) == 1, f"missing_local = 1（{len(rep['missing_local'])}）")
    _ok(rep["missing_local"][0]["tid"] == "209931",
        f"缺的是 tid 209931（{rep['missing_local'][0]['tid']}）")
    _ok(rep["missing_local"][0]["infohash"] == hB_record2,
        "missing_local 的 infohash 来自站点 .torrent（精确）")
    _ok(len(rep["present_no_bill"]) == 1 and rep["present_no_bill"][0]["infohash"] == hA,
        "present_no_bill = tA（站点欠、本机有、账本无账单）")
    _ok(rep["hash_coverage_complete"] is True, "infohash 覆盖完整（可输出 rotate 候选）")
    _ok(len(rep["safe_rotate_candidate"]) == 1
        and rep["safe_rotate_candidate"][0]["infohash"] == hB,
        "safe_rotate_candidate = tB（本机有、站点未列欠、账本已结清）")
    _ok(rep["torrents_fetched"] == 1, f"只拉了 1 个 .torrent（粗配省流量，{rep['torrents_fetched']}）")

    # ---- 3) 抓取失败 → 零结论 ----
    print("\n[3] 抓取失败 → ok=False 且零结论")
    h.http = _Http(MYHR_PAGE1, fail=True)
    rep_bad = h._hr_reconcile_site("carpt.net")
    _ok(rep_bad["ok"] is False, "抓取失败 → ok=False")
    _ok(rep_bad["partial"] is True, "标记 partial=True")
    _ok(not rep_bad["missing_local"] and not rep_bad["present_no_bill"]
        and not rep_bad["safe_rotate_candidate"], "零结论（绝不从半份数据推「站点说干净」）")

    # ---- 4) 干跑 vs confirm ----
    print("\n[4] _hr_reconcile_apply 干跑 / confirm")
    h.http = _Http(MYHR_PAGE1)
    h.dl.added = []
    plan = h._hr_reconcile_apply("carpt.net", confirm=None)
    _ok(plan["dry_run"] is True and plan["would_add"] == 1, "默认干跑：would_add=1")
    _ok(not h.dl.added, "干跑**不**调用 add_torrent")
    # 先验证「没有保存目录就拒绝」（不落到下载器默认目录）
    blocked = h._hr_reconcile_add_one("carpt.net", "209931", hB_record2)
    _ok(blocked["ok"] is False and "保存目录" in blocked["err"],
        "未配置保存目录 → 拒绝（不落下载器默认目录）")
    # 挂一个任务（提供 save_path / tag）
    h._task_configs = {"t1": types.SimpleNamespace(
        id="t1", site_domain="carpt.net", save_path="/movie/刷流", brush_tag="魔流-CARPT-刷魔力")}
    done = h._hr_reconcile_apply("carpt.net", confirm="1")
    _ok(done["dry_run"] is False and done["added"] == 1, f"confirm=1：added=1（{done.get('added')}）")
    _ok(len(h.dl.added) == 1 and h.dl.added[0]["domain"] == "carpt.net",
        "add_torrent 被调用且带 site_domain")
    _ok(h.dl.added[0]["dir"] == "/movie/刷流", f"用任务的 save_path（{h.dl.added[0]['dir']}）")
    _ok(done["results"][0]["new_hash"], f"新 hash = {str(done['results'][0].get('new_hash'))[:12]}…")

    # ---- 5) 已在下载器 → 跳过（不重复下载） ----
    print("\n[5] 同站重下 · 已在下载器则跳过")
    already = fingerprint.info_hash(_torrent_bytes("record2"))
    h.torrents[already] = types.SimpleNamespace(hash=already, title="record2", size=0,
                                                tracker="https://carpt.net/announce", tags=[])
    res = h._hr_reconcile_add_one("carpt.net", "209931", already)
    _ok(res.get("skipped") == "已在下载器",
        "infohash 已在 qB → 跳过（零下载）")
    h.torrents.pop(already, None)

    # ---- 6) 缓存 / 退避 / 落盘 ----
    print("\n[6] HrReconcileCache")
    cache = h._hr_reconcile_cache()
    import time as _t
    cache.tid_put("carpt.net", "209930", hA, "牧神记", 2.116, now=_t.time())
    hit = cache.tid_get("carpt.net", "209930")
    _ok(hit and hit["h"] == hA, "tid→infohash 索引可读写")
    _ok(cache.tid_get("carpt.net", "nope") is None, "未命中 → None")
    cache.note_result("carpt.net", False, now=1000.0, fail_count=1)
    _ok(cache.site_due("carpt.net", 1000.0 + 3600) is False, "失败后 1h 内不到期（6h 退避）")
    _ok(cache.site_due("carpt.net", 1000.0 + 7 * 3600) is True, "6h 后退避到期")
    cache.note_result("carpt.net", True, now=2000.0)
    _ok(cache.site_due("carpt.net", 2000.0) is True, "成功后清退避")
    cache.set_last_run(1234.0)
    cache.flush()
    file = Path(tmp) / "hr_reconcile.json"
    _ok(file.exists(), "hr_reconcile.json 落盘")
    again = HrReconcileCache(Path(tmp))
    _ok(again.last_run_ts() == 1234.0, "重新载入 last_run_ts 保持")
    _ok((again.tid_get("carpt.net", "209930") or {}).get("h") == hA, "重新载入 tid 索引保持")

    # ---- 7) 一轮对账（force，不联网之外的站点） ----
    print("\n[7] _hr_reconcile_round（force）")
    h.http = _Http(MYHR_PAGE1)
    h.dl.next_bytes = _torrent_bytes("record2")
    rnd = h._hr_reconcile_round(force=True)
    _ok(rnd.get("enabled") is True, "enabled=True")
    _ok(rnd.get("sites") == 1, f"只对 hr=True 站对账（sites={rnd.get('sites')}）")
    _ok(rnd.get("missing_total") == 1, f"missing_total=1（{rnd.get('missing_total')}）")

    # ---- 8) 解析健壮性（11.8.1）：噪声行 / 嵌套 tr 重复 / 列序 ----------------
    print("\n[8] 解析健壮性（噪声行 / 嵌套 tr / 列字段）")
    rows8 = hrbills._hr_myhr_parse(MYHR_NOISY)
    _ok(isinstance(rows8, list) and len(rows8) == 2,
        f"噪声行剔除、恰 2 条真记录（{len(rows8 or [])}）")
    r = [x for x in (rows8 or []) if x["tid"] == "209821"][0]
    _ok(r["tid"] == "209821", f"tid 取自**最长锚文本**（标题）链接（{r['tid']}）")
    _ok(hrbills._hr_myhr_parse(MYHR_NESTED) is None,
        "标题套在子表里（布局不兼容）→ None（退避，不当作无欠）")
    _ok(abs(r["up_gb"] - 0.219) < 0.005, f"up_gb ≈ 0.219（{r['up_gb']}）")
    _ok(abs(r["down_gb"] - 21.83) < 0.05, f"down_gb ≈ 21.83（{r['down_gb']}）")
    _ok(r["need_left"] == "19:28:20", f"need_left = 19:28:20（{r['need_left']}）")
    _ok(r["done_at"] == "2026-10-05 13:05", f"done_at（{r['done_at']}）")
    _ok("5天20:02:04" == r["keep_left"], f"keep_left（{r['keep_left']}）")

    # ---- 9) 粗配 v2：中英混排 token / 双胞胎歧义 / 已占位 ----------------
    print("\n[9] _hr_reconcile_rough_match（token 版本）")
    hCN = _hex(0xC1)
    hCN2 = _hex(0xC2)
    hOther = _hex(0xD3)
    lh = {
        hCN: types.SimpleNamespace(hash=hCN,
                                   title="余红旧事.The.Old.Story.of.Yu.Hong.2026.S01.2160p.WEB-DL.H265.DV.DDP5.1-PTerWEB"),
        hCN2: types.SimpleNamespace(hash=hCN2,
                                    title="余红旧事.The.Old.Story.of.Yu.Hong.2026.S01.2160p.WEB-DL.H265.DV.DDP5.1-PTerWEB.2"),
        hOther: types.SimpleNamespace(hash=hOther, title="Lucky Jo 1964 (BD25)"),
    }
    rec_cn = {"tid": "209821", "title": "The Old Story of Yu Hong 2026 S01 E14-E17 2160p WEB-DL H265 DV DDP5.1-PTerWEB"}
    m = hrbills.HrBillsMixin._hr_reconcile_rough_match(rec_cn, lh)
    _ok(m == "", "两个孪生候选同分 → 不认（去拉种，宁多拉不误判）")
    m1 = hrbills.HrBillsMixin._hr_reconcile_rough_match(rec_cn, {hCN: lh[hCN]})
    _ok(m1 == hCN, f"中英混排 token 命中（{m1[:12]}）")
    _ok(hrbills.HrBillsMixin._hr_reconcile_rough_match(rec_cn, {hCN: lh[hCN]}, {hCN}) == "",
        "已被别的记录占位 → 不认（一对一）")
    rec_jo = {"tid": "209946", "title": "Lucky Jo 1964 1080p GER Blu-ray AVC DTS-HD MA 2.0"}
    _ok(hrbills.HrBillsMixin._hr_reconcile_rough_match(rec_jo, lh) == "",
        "同片不同版（BD25 ≠ 1080p Blu-ray）→ 不认")

    print("\n" + "=" * 64)
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:  # noqa: BLE001
        print(f"\n{e}")
        sys.exit(1)
