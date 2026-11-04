#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""站点账本对账：本地实挂 vs 站点认账 vs 台账（19.11.8）。

现场（2026-11-02）：10 颗辅种的 announce 只剩 ``?passkey=<账号口令>``、没有主机名，
在 qB 里挂了 13 天、357GB 上传 0。**本地信号全都判不出来**——``tracker`` 字段为空的
种全库 196 颗（多数是有 DHT 的正常种）、「暂停+零上传+超 7 天」1248 颗（静默池常态）。
唯一判据是跟站点对账。

断言（纯函数 + 桩，离线可跑）：
  [1] 体积归一：字节数字 / ``40.64 GB`` 文本 / 空值 / 乱码
  [2] 标题归一只用于仲裁（大小写、标点、全角）
  [3] 匹配：体积精确命中；容差区间内用标题仲裁；一颗 qB 不被两行复用
  [4] 双向差额：站点认账本地没有 → site_only；本地挂着站点不认 → local_only（坏链那一类）
  [5] 站点侧取不到 → ``verdict=unknown`` 且 ``site=None``，**不当成 0**（铁律 8）
  [6] 有差额 → ``verdict=diff``，且 local_only 每行带 ``in_ledger``/``age_days``
  [7] **paused 不参与对账**：站点只统计「正在做种」，静默池 paused 的种不算，
      否则差额数正好等于 paused 数（学校 213 对 4 → 假报 209）
  [8] 新挂上的种有 announce 宽限期
  [9] 全对上 → ``verdict=ok``；汇总数字是全量、明细才截断
  [10] 站点侧不够全（peer 视图 / 分页没抓全）→ 只给 ``partial``，不判差额
  [11] 在跑但没有可用 tracker：**在跑**且 ``trackers_count>0`` 但 ``tracker`` 为空
       → 本地就能判，**站点侧取不到也不能吞掉**；paused 的空 tracker 不算（否则 153 颗假的）
  [12] 源码锚点：路由已登记 / 不塞进 health（health 的「零外部请求」铁律）

用法：``python3 tools/test_recon.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_recon_test"


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

_app = types.ModuleType("app")
_app_schemas = types.ModuleType("app.schemas")


class _Resp:
    def __init__(self, success=False, message="", data=None):
        self.success = success
        self.message = message
        self.data = data


_app_schemas.Response = _Resp
sys.modules.setdefault("app", _app)
sys.modules["app.schemas"] = _app_schemas

recon = _load(PKG + ".features.recon", "features/recon.py")

FAILS = []
N = 0

GB = 1024 ** 3


def ok(cond, label):
    global N
    N += 1
    if not cond:
        FAILS.append(label)
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


def qb(h, size_gb, title="", site="高清杜比", state="stalledUP", uploaded=0.0,
       added_on=0.0, tracker="https://example.com/announce", trackers_count=1):
    """一颗 qB 种（模拟 TorrentInfo 的必要字段）。

    默认 ``stalledUP``＝**在跑**（站点会把它算进「做种」）。要模拟静默池里停着的种，
    显式传 ``state="pausedUP"`` —— 那一类**不参与**对账，站点本来也不统计它。
    构造坏链种时传 ``tracker="", trackers_count=1``。
    """
    return types.SimpleNamespace(
        hash=h, title=title or h, size=size_gb * GB, state=state,
        uploaded=uploaded, added_on=added_on,
        tracker=tracker, trackers_count=trackers_count,
        tags=[f"魔流-{site}-静默-资源"],
    )


class Stub(recon.ReconMixin):
    """把外部依赖全换掉：只测对账口径，不打网络。"""

    def __init__(self, sites, torrents, peers=None, ledger=None, seed_rows=None,
                 seed_total=None):
        self._sites = sites
        self._qb = {t.hash: t for t in torrents}
        self._peers = peers or {}
        self._ledger = ledger or {}
        self._seed_rows = seed_rows or []
        self._seed_total = seed_total
        self.logs = []

    def _tag_site_names(self):
        return [s["name"] for s in self._sites]

    def _tag_all_torrents(self):
        return self._qb

    def _list_sites(self):
        return self._sites

    def _get_site(self, site_id):
        return object()

    def _hd_api_json(self, site_id, path):
        rows = self._peers.get(site_id)
        if rows is None:
            return {}
        return {"status": 0, "data": rows}

    def _claim_site_rows(self, site, refresh=False):
        # 与真实实现同形：一行都没有时返回 {}（页面为空/抓失败不可区分）
        if not self._seed_rows:
            return {}
        return {"rows": self._seed_rows, "declared_total": self._seed_total,
                "pages": 1}

    def _recon_ledger_rows(self):
        return self._ledger

    def _as_bool_arg(self, v):
        return str(v or "").strip().lower() in ("1", "true", "yes")

    def _log(self, *a, **k):
        self.logs.append(a)

    def _site_report_torrent_site(self, t, known):
        for tag in (getattr(t, "tags", None) or []):
            if str(tag).startswith("魔流-"):
                parts = str(tag).split("-")
                if len(parts) >= 2:
                    return parts[1]
        return ""


print("[1] 体积归一（数字 / 文本 / 空 / 乱码）")
ok(recon._rc_size_of(2226967094) == 2226967094, "字节整数原样")
ok(recon._rc_size_of(1024.0) == 1024, "浮点取整")
ok(recon._rc_size_of("40.64 GB") == int(round(40.64 * GB)), "「40.64 GB」按 1024 进制换算")
ok(recon._rc_size_of("1,024 KB") == 1024 * 1024, "带千分位的 KB")
ok(recon._rc_size_of("") == 0 and recon._rc_size_of(None) == 0, "空值 → 0")
ok(recon._rc_size_of("unknown") == 0, "乱码 → 0（不抛）")
ok(recon._rc_size_of(True) == 0, "bool 不当作 1 字节")

print("\n[2] 标题归一（只用于容差区间的仲裁）")
ok(recon._rc_norm_title("The.Magic.Flute.2022") == "the magic flute 2022", "点号转空格")
ok(recon._rc_norm_title("  [小城良方]  Small Town  ") == "小城良方 small town", "方括号/多空格")
ok(recon._rc_sim("the magic flute 2022", "the magic flute 2022") == 1.0, "相同标题 = 1.0")
ok(recon._rc_sim("", "x") == 0.0, "空标题 = 0.0")

print("\n[3] 匹配：精确体积 / 容差仲裁 / 不复用同一颗")
site_rows = [
    {"tid": "1", "title": "A", "size": 100 * GB},
    {"tid": "2", "title": "B", "size": 200 * GB},
]
qb_rows = [
    {"hash": "h1", "title": "A", "size": 100 * GB},
    {"hash": "h2", "title": "B", "size": 200 * GB},
]
m, so, lo = recon._rc_match(site_rows, qb_rows)
ok(len(m) == 2 and not so and not lo, "精确体积全命中")
ok({x["hash"] for x in m} == {"h1", "h2"}, "matched 带出 hash")

# 容差：站点 100GB，本地 100.5GB（0.5% 偏差）
m2, so2, lo2 = recon._rc_match(
    [{"tid": "9", "title": "T", "size": 100 * GB}],
    [{"hash": "hx", "title": "T", "size": int(100.5 * GB)}],
)
ok(len(m2) == 1 and not lo2, "0.5% 体积偏差能靠容差配上")
ok(m2[0]["size"] == 100 * GB and m2[0]["size_qb"] == int(100.5 * GB), "两侧体积都保留")

# 区间内两颗 → 标题仲裁选对
m3, _, _ = recon._rc_match(
    [{"tid": "7", "title": "The.Magic.Flute.2022", "size": 100 * GB}],
    [{"hash": "old", "title": "The.Magic.Flute.1975", "size": int(100.2 * GB)},
     {"hash": "new", "title": "The.Magic.Flute.2022", "size": int(100.1 * GB)}],
)
ok(m3 and m3[0]["hash"] == "new", "容差区间内按标题相似度仲裁")

# 一行站点只消耗一颗
m4, so4, lo4 = recon._rc_match(
    [{"tid": "1", "size": 50 * GB}],
    [{"hash": "a", "size": 50 * GB}, {"hash": "b", "size": 50 * GB}],
)
ok(len(m4) == 1 and len(lo4) == 1, "同体积两颗：只认一颗，另一颗进 local_only")

print("\n[4] 双向差额")
m5, so5, lo5 = recon._rc_match(
    [{"tid": "1", "size": 10 * GB}, {"tid": "2", "size": 999 * GB}],
    [{"hash": "a", "size": 10 * GB}, {"hash": "b", "size": 77 * GB}],
)
ok(len(so5) == 1 and str(so5[0]["tid"]) == "2", "站点认账但本地没有 → site_only")
ok(len(lo5) == 1 and lo5[0]["hash"] == "b", "本地挂着站点不认 → local_only")

print("\n[5] 站点侧取不到 ≠ 0")
s = Stub([{"id": 19, "name": "高清杜比", "domain": "uhddolby.com"}], [qb("h1", 1.0)])
r = s.get_recon()
site = (r.data or {}).get("sites", [{}])[0]
ok(site.get("source") == "none", "source=none")
ok(site.get("site") is None, "site 为 None（不当成 0 颗）")
ok(site.get("verdict") == "unknown", "verdict=unknown")
ok((r.data or {}).get("summary", {}).get("unknown") == 1, "汇总里 unknown 计数为 1")

print("\n[6] 有差额 → diff，且明细带台账解释")
s2 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("h1", 10.0, site="学校"), qb("h2", 20.0, site="学校", added_on=1.0),
     qb("h3", 30.0, site="学校"), qb("h4", 40.0, site="学校"),
     qb("h5", 50.0, site="学校")],
    seed_rows=[{"tid": "1", "title": "A", "size_bytes": 10 * GB}],
    ledger={"h2": {"sub": "辅种", "state": "静默"}},
)
d2 = (s2.get_recon().data or {}).get("sites", [{}])[0]
ok(d2.get("verdict") == "diff", "verdict=diff")
ok(d2.get("matched") == 1, "matched=1")
ok((d2.get("local_only") or {}).get("count") == 4, "local_only=4")
_items2 = (d2.get("local_only") or {}).get("items") or [{}]
item = next((r for r in _items2 if r.get("hash") == "h2"), {})
ok(item.get("in_ledger") is True, "台账里有 → in_ledger=True")
ok(item.get("sub") == "辅种", "带出台账职务 sub")
ok(item.get("age_days") is not None, "带出挂了多少天")

# 容差：1~2 颗是 announce 过渡态，明细照列但不判 red
s2b = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("h1", 10.0, site="学校"), qb("h9", 90.0, site="学校")],
    seed_rows=[{"tid": "1", "title": "A", "size_bytes": 10 * GB}],
)
d2b = (s2b.get_recon().data or {}).get("sites", [{}])[0]
ok((d2b.get("local_only") or {}).get("count") == 1, "差 1 颗仍然列出来")
ok(d2b.get("verdict") == "ok", "但 1 颗在容差内 → 不判 diff（不闪红）")
ok("容差" in str(d2b.get("why") or ""), "why 说明是容差内")

print("\n[7] 静默池 paused 不参与对账（否则每颗静默种都是一条假差额）")
# 现场证据：学校 213 颗本地 vs 站点 4 行，差额 209 正好等于 paused 的数量。
s10 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("act1", 10.0, site="学校"),
     qb("idle1", 20.0, site="学校", state="pausedUP"),
     qb("idle2", 30.0, site="学校", state="pausedUP")],
    seed_rows=[{"tid": "1", "title": "A", "size_bytes": 10 * GB}],
)
d10 = (s10.get_recon().data or {}).get("sites", [{}])[0]
ok(d10.get("verdict") == "ok", "1 颗在跑 + 2 颗暂停 → ok（paused 不算差额）")
ok((d10.get("qb") or {}).get("count") == 1, "qb 侧只算活跃种：1 颗")
ok((d10.get("qb") or {}).get("idle_count") == 2, "暂停的另计 idle_count=2")
ok((d10.get("local_only") or {}).get("count") == 0, "paused 不进 local_only")

print("\n[8] 新挂上的种不算差额（announce 宽限期）")
s5 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("new1", 5.0, site="学校", added_on=time.time())],
    seed_rows=[{"tid": "1", "title": "A", "size_bytes": 5 * GB}],
)
d5 = (s5.get_recon().data or {}).get("sites", [{}])[0]
ok(d5.get("verdict") == "ok", "只有刚挂上的（站点已认账）→ ok")
ok((d5.get("local_only") or {}).get("fresh_count") == 0, "对上了就不算 fresh 差额")

s6 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("old1", 40.0, site="学校", added_on=time.time() - 13 * 86400),
     qb("old2", 41.0, site="学校", added_on=time.time() - 13 * 86400),
     qb("old3", 42.0, site="学校", added_on=time.time() - 13 * 86400),
     qb("old4", 43.0, site="学校", added_on=time.time() - 13 * 86400),
     qb("new2", 5.0, site="学校", added_on=time.time())],
    seed_rows=[{"tid": "1", "title": "A", "size_bytes": 5 * GB}],
)
d6 = (s6.get_recon().data or {}).get("sites", [{}])[0]
ok(d6.get("verdict") == "diff", "老种对不上 → diff")
ok((d6.get("local_only") or {}).get("hard_count") == 4, "hard_count=4（只算老种）")
ok((d6.get("local_only") or {}).get("fresh_count") == 0, "新种已对上，不再进 fresh")

print("\n[9] 全对上 → ok；汇总全量、明细截断")
s3 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("h1", 10.0, site="学校")],
    seed_rows=[{"tid": "1", "title": "A", "size_bytes": 10 * GB}],
)
d3 = (s3.get_recon().data or {}).get("sites", [{}])[0]
ok(d3.get("verdict") == "ok", "verdict=ok")
ok((d3.get("qb") or {}).get("count") == 1, "qb 侧 1 颗")

s4 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb(f"h{i}", float(i + 1), site="学校") for i in range(30)],
    seed_rows=[{"tid": "1", "title": "A", "size_bytes": 1 * GB}],
)
d4 = (s4.get_recon(limit=5).data or {}).get("sites", [{}])[0]
ok((d4.get("local_only") or {}).get("count") == 29, "count 是全量 29")
ok(len((d4.get("local_only") or {}).get("items") or []) == 5, "items 按 limit 截断到 5")

print("\n[10] 站点侧不够全时只给 partial，不判差额")
# peers 是「当前有 peer 的种」视图：同一站在三轮实测给过 52 / 41 / 9 行 → 永远局部
s7 = Stub(
    [{"id": 19, "name": "高清杜比", "domain": "uhddolby.com"}],
    [qb("k1", 30.0, added_on=time.time() - 20 * 86400)],
    peers={19: [{"id": 9, "size": 1 * GB}]},
)
d7 = (s7.get_recon().data or {}).get("sites", [{}])[0]
ok(d7.get("source") == "api:peers", "走官方 peers 接口")
ok(d7.get("verdict") == "partial", "peer 视图 → partial（不报成差额）")
ok("peer" in str(d7.get("why") or ""), "why 说明是 peer 视图")

# 分页没抓全（declared_total 比抓到的多）→ 也不判差额
s11 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("k2", 30.0, site="学校", added_on=time.time() - 20 * 86400)],
    seed_rows=[{"tid": "9", "title": "别的种", "size_bytes": 1 * GB}],
    seed_total=500,
)
d11 = (s11.get_recon().data or {}).get("sites", [{}])[0]
ok(d11.get("verdict") == "partial", "声明 500 条只抓到 1 条 → partial")
ok("500" in str(d11.get("why") or ""), "why 带上站点声明的条数")

print("\n[11] 在跑但没有可用 tracker（本地可判，不依赖站点侧口径）")
# 分支一：站点侧完全取不到（seed_rows 空 → _claim_site_rows 返回 {}）也照样报坏链
s8 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("bad1", 40.0, site="学校", tracker="", trackers_count=1,
        added_on=time.time() - 13 * 86400),
     qb("dht1", 5.0, site="学校", tracker="", trackers_count=0,
        added_on=time.time() - 13 * 86400)],
    seed_rows=[],
)
d8 = (s8.get_recon().data or {}).get("sites", [{}])[0]
ok(d8.get("source") == "none", "站点侧取不到")
ok((d8.get("orphans") or {}).get("count") == 1, "只有「在跑但没有可用 tracker」的算")
ok(d8.get("verdict") == "diff", "站点侧取不到也不能吞掉本地能判的这一项")
ok("tracker" in str(d8.get("why") or ""), "why 说明是本地判出来的")
item8 = ((d8.get("orphans") or {}).get("items") or [{}])[0]
ok(item8.get("hash") == "bad1", "DHT-only 种（count=0）不误报")

# ★ 关键反例：暂停的空 tracker 不是坏链（否则全站刷 153 颗假坏链）
s9 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("idle3", 40.0, site="学校", state="pausedUP", tracker="", trackers_count=1,
        added_on=time.time() - 13 * 86400)],
    seed_rows=[],
)
d9 = (s9.get_recon().data or {}).get("sites", [{}])[0]
ok((d9.get("orphans") or {}).get("count") == 0, "paused 且 tracker 为空 → 不算")
ok(d9.get("verdict") != "diff", "paused 空 tracker 不该把该站弄成 diff")

# 站点说我在做种、本地一颗都没在跑 → 反过来是 site_only，要报
s13 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("idle4", 40.0, site="学校", state="pausedUP")],
    seed_rows=[{"tid": "9", "title": "别的种", "size_bytes": 1 * GB}],
)
d13 = (s13.get_recon().data or {}).get("sites", [{}])[0]
ok((d13.get("site_only") or {}).get("count") == 1,
   "站点认账但本地没在跑 → site_only（反向差额照样报）")

# 分支二：站点侧是局部清单（partial）时，坏链仍然把结论提到 diff
s12 = Stub(
    [{"id": 1, "name": "学校", "domain": "btschool.club"}],
    [qb("bad2", 40.0, site="学校", tracker="", trackers_count=2,
        added_on=time.time() - 13 * 86400)],
    seed_rows=[{"tid": "9", "title": "别的种", "size_bytes": 1 * GB}],
    seed_total=500,
)
d12 = (s12.get_recon().data or {}).get("sites", [{}])[0]
ok(d12.get("verdict") == "diff", "清单没抓全本只给 partial，但空 announce 种把它提到 diff")
ok((d12.get("orphans") or {}).get("count") == 1, "局部清单下照样被抓到")

print("\n[12] 源码锚点")
_src_api = (ROOT / "features" / "api.py").read_text(encoding="utf-8")
_src_recon = (ROOT / "features" / "recon.py").read_text(encoding="utf-8")
_src_health = (ROOT / "features" / "health.py").read_text(encoding="utf-8")
_src_init = (ROOT / "__init__.py").read_text(encoding="utf-8")
ok('("/recon", "get_recon", "GET"' in _src_api, "路由表已登记 /recon")
ok("ReconMixin" in _src_init, "主类已混入 ReconMixin")
ok("RECON_TTL" in _src_recon and "api/v1/user/peers" in _src_recon, "对账带缓存且走 peers")
ok("零外部请求" in _src_health, "health 的「零外部请求」铁律仍在（对账没塞进去）")
ok("_recon_site_rows" not in _src_health, "health 没有引用对账（职责不混）")
ok("SeedLedgerStore(get_backend(self), log=self._log).items()" in _src_recon,
   "台账走 items()（load_seeds 是 backend 的方法，写错会被 except 吞成 0）")
ok("RECON_NEW_GRACE" in _src_recon, "有 announce 宽限期")
ok("_claim_site_claims" not in _src_recon,
   "不用认领页当站点侧（它只列可认领/已认领，不是全部做种）")
ok("_claim_site_rows" in _src_recon, "走「我的种子」列表（getusertorrentlistajax）")

print()
if FAILS:
    print(f"FAIL: {len(FAILS)}/{N} 项未通过")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print(f"PASS: {N}/{N} 项全部通过")
