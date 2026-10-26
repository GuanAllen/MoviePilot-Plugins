#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 全站辅种「取种链」离线回归测试（真跑，无需 MoviePilot，零网络/零写）。

覆盖 19.7.92 的取链改造（与隔壁 IYUU 插件同口径；原标 19.7.93，随本版并入 19.7.92 发版）：
  (a) 普通站：云端模板 + passkey 拼链，**不发 HTTP**（不发详情页请求）；
  (b) 特殊站（模板含 `hash=`/`authkey=`）：**没有 cookie 时不发请求**，返回 None 并给出原因；
  (c) 特殊站 + cookie：抓 `details.php?id=<tid>&hit=1`，用 4 条 xpath 抠链，相对链补成绝对链；
  (d) 特殊站详情页 HTTP 403（没过 CF 盾）→ None + 原因写明 HTTP 403；
  (e) 特殊站详情页 200 但页面没有下载链 → None + 原因写明 xpath 全未命中；
  (f) API 站（馒头）：走 `api_dl_token`；取不到时给原因；
  (g) 站点用 JSON 回错（馒头「種子未找到」）→ `_site_error_hint` 能认出来（旧代码当流控）；
  (h) `_reseed_one` 收到 `TorrentFetchGone` → 返回 "gone"（不再冒充 "flow"）；
  (i) 账本兼容：旧版「缺链」miss 按新口径 fail（1 天）重算 TTL，特征码不一致不受影响。

用法：``python3 tools/test_reseed_chain.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
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


def _load():
    _stub_app()
    _stub_sqlalchemy()
    pkg = types.ModuleType("mf_reseed_chain_test")
    pkg.__path__ = [str(ROOT)]
    sys.modules.setdefault("mf_reseed_chain_test", pkg)
    feat = types.ModuleType("mf_reseed_chain_test.features")
    feat.__path__ = [str(ROOT / "features")]
    sys.modules.setdefault("mf_reseed_chain_test.features", feat)
    spec = importlib.util.spec_from_file_location("mf_reseed_chain_test.features.reseed",
                                                  ROOT / "features" / "reseed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mf_reseed_chain_test.features.reseed"] = mod
    spec.loader.exec_module(mod)
    return mod


reseed = _load()
ReSeedMixin = reseed.ReSeedMixin
downloader_ops = sys.modules["mf_reseed_chain_test.downloader_ops"]

# 取链用到的三个云端函数：离线桩（避免依赖 IYUU 站表文件/网络）
def _fake_resolve(dom, user_fill, extra, **kw):
    out = dict(user_fill or {})
    out.update(extra or {})
    return out


def _fake_build(template, base_url, is_https, tid, variables):
    if not variables.get("passkey"):
        return ""
    tpl = template.replace("{}", str(tid))
    for k, v in (variables or {}).items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return f"https://{base_url}/{tpl.lstrip('/')}"


reseed.resolve_link_vars = _fake_resolve
reseed.build_download_url = _fake_build


# ------------------------------------------------------------------ 请求桩
class _Resp:
    def __init__(self, status_code=200, text="", content=b""):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode("utf-8")
        self.ok = 200 <= status_code < 400


CALLS: list = []


class _FakeRequestUtils:
    RESP: _Resp = _Resp(200, "")

    def __init__(self, **kw):
        self.kw = kw

    def get_res(self, url=None, **kw):
        CALLS.append(str(url))
        return _FakeRequestUtils.RESP


netmod = types.ModuleType("app.sdk.network")
netmod.RequestUtils = _FakeRequestUtils
sys.modules["app.sdk.network"] = netmod


# ------------------------------------------------------------------ lxml 桩
# 宿主（本工作区）没装 lxml，容器里才有；这里用 html.parser 做一个**只认本测试
# 四条 xpath**的最小替身（真实 lxml 由部署后的容器验证）。
class _Doc:
    def __init__(self, forms, anchors):
        self._forms = forms          # [(action,)]
        self._anchors = anchors      # [(href, cls)]

    def xpath(self, xp):
        if "form" in xp and "download.php?id=" in xp:
            return [a for a, in self._forms if "download.php?id=" in a]
        if "download.php?hash=" in xp:
            return [h for h, _c in self._anchors if "download.php?hash=" in h]
        if "download.php?id=" in xp:
            return [h for h, _c in self._anchors if "download.php?id=" in h]
        if "@class='index'" in xp and "/dl/" in xp:
            return [h for h, c in self._anchors if c == "index" and "/dl/" in h]
        return []


class _FakeEtree:
    @staticmethod
    def HTML(text):
        import html.parser as _hp

        forms: list = []
        anchors: list = []

        class _P(_hp.HTMLParser):
            def handle_starttag(self, tag, attrs):
                d = dict(attrs)
                if tag == "form" and d.get("action"):
                    forms.append((d["action"],))
                if tag == "a" and d.get("href"):
                    anchors.append((d["href"], d.get("class") or ""))

        p = _P()
        p.feed(text or "")
        if not str(text or "").strip():
            return None
        return _Doc(forms, anchors)


_lxml = types.ModuleType("lxml")
_lxml.__path__ = []
_lxml_etree = types.ModuleType("lxml.etree")
_lxml_etree.HTML = _FakeEtree.HTML
_lxml.etree = _lxml_etree
sys.modules.setdefault("lxml", _lxml)
sys.modules.setdefault("lxml.etree", _lxml_etree)


class _ApiSite:
    def __init__(self, url="", error=None):
        self._url = url
        self._error = error

    def api_dl_token(self, tid):
        return {"url": self._url, "error": self._error}


class _Collect:
    def __init__(self, api=False, site=None):
        self._api = api
        self._site = site or _ApiSite()

    def is_api_site(self, site_id):
        return self._api

    def site(self, site_id):
        return self._site


NORMAL_ENTRY = {
    "download_page": "download.php?id={}&passkey={passkey}",
    "base_url": "pt.example.com",
    "is_https": 1,
    "details_page": "details.php?id={}",
}
SPECIAL_ENTRY = {
    "download_page": "download.php?id={}&uid={uid}&hash={hash}",
    "base_url": "www.hddolby.com",
    "is_https": 1,
    "details_page": "details.php?id={}",
}


def _conn(**kw):
    base = {"site_id": 17, "domain": "www.hddolby.com", "cookie": "cf_clearance=x",
            "ua": "UA", "url": "https://www.hddolby.com", "apikey": "", "token": ""}
    base.update(kw)
    return base


class _UrlHost(ReSeedMixin):
    """只注入取链所需的几个点，其余真方法不碰。"""

    def __init__(self, conn=None, entry=None, creds=None, api=False, api_url="", api_err=None):
        self._conn = dict(conn or _conn())
        self._entry = dict(entry or SPECIAL_ENTRY)
        self._creds = dict(creds or {})
        self._iyuu_sites: dict = {}
        self._api = _Collect(api, _ApiSite(api_url, api_err))
        self.dbgs: list = []
        # 目录缓存桩（`_reseed_cache_link` / `_reseed_pairs` 用）
        self.rows: dict = {}
        self.cached_tids: set = set()
        self.sizes: dict = {}

    def _rss_lookup(self, site_id, tid):
        return dict((self.rows or {}).get(str(tid), {}))

    def _rss_tids(self, site_id):
        self.rss_tids_calls = getattr(self, "rss_tids_calls", []) + [int(site_id)]
        return set(self.cached_tids or ())

    def _rss_sizes(self, site_id, tids):
        self.rss_sizes_calls = getattr(self, "rss_sizes_calls", []) + [int(site_id)]
        return dict(self.sizes or {})

    def _reseed_day(self):
        return {"day": "2026-10-20", "sites": {}}

    def get_data(self, *a, **k):
        return None

    def _reseed_site_conn(self, sid):
        return dict(self._conn)

    def _reseed_iyuu_entry(self, sid):
        return dict(self._entry)

    def _cred_get(self, site_id, key):
        return self._creds.get(key)

    def _collect_ref(self):
        return self._api

    def _reseed_passkey(self, *a, **k):
        return self._creds.get("passkey", "")

    def _dbg(self, msg, *a, **k):
        self.dbgs.append(str(msg))

    # ---- `_reseed_one` 需要的注入点
    def _reseed_site_map(self):
        return {17: {"name": "HDDolby"}}

    def _pv_block_reason(self, sid):
        return ""

    def _pv_allow(self, sid, kind, want=1):
        return True

    def _pv_spend(self, sid, kind, n=1):
        return None

    def _reseed_ledger_put(self, key, st, note=""):
        self.ledger_put = (key, st, note)

    def _log(self, msg, level="info"):
        self.logs = getattr(self, "logs", []) + [msg]


HTML_OK = ('<html><body><form id="form1" action="download.php?id=42&uid=46684&hash=abcdef">'
           '</form></body></html>')
HTML_NOLINK = '<html><body><p>Nothing here</p></body></html>'


def main() -> int:
    print("魔流 · 全站辅种取种链离线回归\n")

    print("(a) 普通站：模板 + passkey 拼链（不发 HTTP）")
    CALLS.clear()
    h = _UrlHost(conn=_conn(domain="pt.example.com", site_id=3,
                            url="https://pt.example.com", cookie="c=1"),
                 entry=NORMAL_ENTRY, creds={"passkey": "PK123"})
    url = h._reseed_download_url(3, 42)
    _ok(url == "https://pt.example.com/download.php?id=42&passkey=PK123",
        f"拼出模板链：{url}")
    _ok(not CALLS, "普通站不抓详情页（零额外请求）")

    print("\n(b) 特殊站：模板含 hash=，无 cookie → 不发请求 + 原因可读")
    CALLS.clear()
    h = _UrlHost(conn=_conn(cookie=""), entry=SPECIAL_ENTRY)
    note: dict = {}
    url = h._reseed_download_url(17, 42, note=note)
    _ok(url is None, "无 cookie → 取不到链（不再白花一次 403 请求）")
    _ok(not CALLS, "无 cookie 时一次 HTTP 都不发")
    _ok("cookie" in note.get("why", ""), f"原因写明缺 cookie：{note.get('why')}")
    _ok(bool(h.dbgs), "留了 _dbg 现场（排查用）")

    print("\n(c) 特殊站 + cookie：抓详情页 → xpath 抠链 → 补绝对地址")
    CALLS.clear()
    _FakeRequestUtils.RESP = _Resp(200, HTML_OK)
    h = _UrlHost(entry=SPECIAL_ENTRY)
    url = h._reseed_download_url(17, 42)
    _ok(url == "https://www.hddolby.com/download.php?id=42&uid=46684&hash=abcdef",
        f"抠出一次性链：{url}")
    _ok(CALLS and CALLS[0] == "https://www.hddolby.com/details.php?id=42&hit=1",
        f"抓的是详情页（带 hit=1）：{CALLS[0] if CALLS else ''}")

    print("\n(d) 详情页 HTTP 403（没过 CF 盾）→ 原因写明")
    _FakeRequestUtils.RESP = _Resp(403, "")
    h = _UrlHost(entry=SPECIAL_ENTRY)
    note = {}
    url = h._reseed_download_url(17, 42, note=note)
    _ok(url is None and "403" in note.get("why", ""), f"403 原因：{note.get('why')}")

    print("\n(e) 详情页 200 但没有下载链 → 原因写明 xpath 未命中")
    _FakeRequestUtils.RESP = _Resp(200, HTML_NOLINK)
    h = _UrlHost(entry=SPECIAL_ENTRY)
    note = {}
    url = h._reseed_download_url(17, 42, note=note)
    _ok(url is None and "xpath" in note.get("why", ""), f"未命中原因：{note.get('why')}")

    print("\n(f) API 站（馒头）：走 api_dl_token")
    h = _UrlHost(conn=_conn(site_id=9, domain="api.m-team.cc", url="https://api.m-team.cc"),
                 entry=NORMAL_ENTRY, api=True, api_url="https://api.m-team.cc/api/rss/dlv2?sign=x")
    url = h._reseed_download_url(9, 1)
    _ok(url == "https://api.m-team.cc/api/rss/dlv2?sign=x", f"API 签名链：{url}")
    h = _UrlHost(conn=_conn(site_id=9, domain="api.m-team.cc", url="https://api.m-team.cc"),
                 entry=NORMAL_ENTRY, api=True, api_url="", api_err="種子未找到")
    note = {}
    _ok(h._reseed_download_url(9, 1, note=note) is None and "種子未找到" in note.get("why", ""),
        f"API 失败原因透出：{note.get('why')}")

    print("\n(g) 站点 JSON 错误体识别（旧代码当流控）")
    hint = downloader_ops._site_error_hint(
        b'{"code":"1","message":"\xe7\xa8\xae\xe5\xad\x90\xe6\x9c\xaa\xe6\x89\xbe\xe5\x88\xb0","data":null}')
    _ok("種子未找到" in hint and "code=1" in hint, f"认出馒头 JSON 错误：{hint}")
    _ok(downloader_ops._site_error_hint(b'{"code":"0","message":"ok","data":{"x":1}}') == "",
        "正常返回体（带 data）不算错误")
    _ok(downloader_ops._site_error_hint(b"d8:announce3:url4:infod4:name1:aee") == "",
        "bencode 种子内容不算错误体")
    _ok(downloader_ops._site_error_hint(b"<html>Just a moment...</html>") == "",
        "HTML 挑战页不算 JSON 错误体")

    print("\n(h) `_reseed_one` 收到 TorrentFetchGone → 返回 gone（不冒充 flow）")
    class _DL:
        def fetch_torrent_bytes(self, url, **kw):
            raise reseed.TorrentFetchGone("種子未找到（code=1）")

    h = _UrlHost(conn=_conn(site_id=9, domain="api.m-team.cc", url="https://api.m-team.cc",
                            cookie="x=1"),
                 entry=NORMAL_ENTRY, creds={"passkey": "PK"}, api=True,
                 api_url="https://api.m-team.cc/api/rss/dlv2?sign=x")
    st = h._reseed_one(_DL(), {}, {"sid": 9, "tid": 1, "key": "9:abc", "ih": "abcdef1234",
                                  "src": "s", "src_size": 1.0})
    _ok(st == "gone", f"状态 = {st}")
    _ok(getattr(h, "ledger_put", ("", "", ""))[1] == "fail"
        and "目标种子不存在" in getattr(h, "ledger_put", ("", "", ""))[2],
        f"台账按确定性失效记账：{getattr(h, 'ledger_put', None)}")

    print("\n(i) 账本兼容：旧的「缺链」miss 按 fail（1 天）重算 TTL")
    import time as _t

    _raw_led = {
        "105:aaa": {"st": "miss", "note": "无下载链模板/缺口令", "ts": _t.time() - 2 * 86400},
        "105:bbb": {"st": "miss", "note": "无下载链模板/缺口令", "ts": _t.time() - 3600},
        "105:ccc": {"st": "miss", "note": "特征码不一致", "ts": _t.time() - 2 * 86400},
    }
    reseed.slot_callbacks = lambda app, key: (lambda: _raw_led, lambda **kw: None)
    _led = _UrlHost()._reseed_ledger()
    _ok("105:aaa" not in _led, "缺链旧 miss 超 1 天 → 放行重试（不再冻 30 天）")
    _ok("105:bbb" in _led and _led["105:bbb"]["st"] == "fail", "缺链旧 miss 未超 1 天 → 保留为 fail")
    _ok("105:ccc" in _led, "「特征码不一致」不动（仍按 30 天冻结）")

    print("\n(j) 方案3：特殊站无 cookie + 目录缓存有 downhash → 免登录拼链（零请求）")
    CALLS.clear()
    DH = "8164a497x1792465938x46684x258702xac2364e8641979e0426c063dde80d1cf"
    h = _UrlHost(conn=_conn(cookie=""), entry=SPECIAL_ENTRY)
    h.rows = {"258702": {"downhash": DH}}
    note = {}
    url = h._reseed_download_url(17, 258702, note=note)
    _ok(url == f"https://www.hddolby.com/download.php?id=258702&downhash={DH}",
        f"拼出 MP spider 同款链：{url}")
    _ok(not CALLS, "缓存链一次 HTTP 都不发（免登录）")
    _ok(note.get("chain") == "cache", f"note 记了走缓存腿：{note}")

    print("\n(k) 方案3：特殊站无 cookie 且缓存没有这颗 → 不给链、不发请求")
    CALLS.clear()
    h = _UrlHost(conn=_conn(cookie=""), entry=SPECIAL_ENTRY)
    note = {}
    url = h._reseed_download_url(17, 42, note=note)
    _ok(url is None and "downhash" in note.get("why", ""), f"原因：{note.get('why')}")
    _ok(not CALLS, "无 cookie 且无缓存时一次 HTTP 都不发")

    print("\n(l) 选对阶段：缓存 downhash 让无 cookie 的特殊站照排；体积预筛用 MP 站点 id")
    reseed._reuse_local_complete = lambda _src: True

    class _Src:
        size = 2 * 1024 ** 3
        save_path = "/vol1/x"
        title = "t"

    local_index = {"src1": _Src()}
    cloud = {"by_hash": {"src1": [{"sid": 105, "torrent_id": "258702", "info_hash": "IH1"}]}}
    site_map = {105: {"sid": 105, "name": "HDDolby", "site_id": 17,
                      "domain": "hddolby.com"}}
    h = _UrlHost(conn=_conn(site_id=17, cookie=""), entry=SPECIAL_ENTRY)
    h.cached_tids = {"258702"}
    st: dict = {}
    picked = h._reseed_pairs(cloud, local_index, site_map, stats=st)
    _ok(len(picked) == 1 and picked[0]["sid"] == 105,
        f"缓存命中 → 无 cookie 也照排：{picked}")
    _ok(getattr(h, "rss_sizes_calls", []) == [17],
        f"体积预筛收到的是 MP 站点 id（不是 IYUU sid）：{getattr(h, 'rss_sizes_calls', [])}")
    _ok(int(st.get("nocookie") or 0) == 0, f"没被误记成「取链不可用」：{st}")

    h = _UrlHost(conn=_conn(site_id=17, cookie=""), entry=SPECIAL_ENTRY)
    h.cached_tids = set()
    st = {}
    picked = h._reseed_pairs(cloud, local_index, site_map, stats=st)
    _ok(not picked and int(st.get("nocookie") or 0) == 1,
        f"缓存没有这颗 → 不排并计数：picked={picked} st={st}")

    print("\n(m) 云端反查 0 命中（IYUU 429/配额耗尽）→ 保留旧候选、不推进 ts、进冷静期")
    import time as _t

    store: dict = {}

    def _c_get(app, ns, key, ttl=0):
        return store.get(key)

    def _c_set(app, ns, key, val, ttl=0):
        store[key] = val

    class _Cli:
        def __init__(self):
            self.calls = 0

        def query(self, hashes, sids=None):
            self.calls += 1
            return {}          # 现场 429：IYUU 回空

    _OLD = {"src1": [{"sid": 17, "torrent_id": "1"}]}
    old_ts = _t.time() - 3600
    store[reseed.RESEED_CLOUD_KEY] = {"ts": old_ts, "hashes": ["src1"],
                                      "by_hash": _OLD, "sids": [17]}
    reseed.cache_get = _c_get
    reseed.cache_set = _c_set
    h = _UrlHost()
    h._iyuu_client = _Cli()
    out = h._reseed_cloud_map(["src1", "src2"])
    _ok(out.get("by_hash") == _OLD, f"旧候选一条不丢：{out.get('by_hash')}")
    _ok(float(out.get("ts") or 0) == old_ts, "不推进 ts（TTL 不被一次失败续命）")
    _ok(float(out.get("blocked_until") or 0) > _t.time(), "记下冷静期 blocked_until")
    _ok(store[reseed.RESEED_CLOUD_KEY].get("by_hash") == _OLD, "落盘的也仍是旧候选")
    _ok(h._iyuu_client.calls == 1, f"两批 hash 只发 1 次请求即停：{h._iyuu_client.calls}")

    print("\n(n) 冷静期内：不再打 IYUU（即使本机 hash 集合变了）")
    out2 = h._reseed_cloud_map(["src1", "src3"])
    _ok(h._iyuu_client.calls == 1, f"零新增查询：{h._iyuu_client.calls}")
    _ok(out2.get("by_hash") == _OLD, "冷静期直接吃旧候选")

    print("\n(o) 首次就 0 命中：仍然落空结果 + 冷静期，短时间不反复烧配额")
    store.clear()
    h2 = _UrlHost()
    h2._iyuu_client = _Cli()
    out3 = h2._reseed_cloud_map(["src1"])
    _ok(not out3.get("by_hash") and float(out3.get("blocked_until") or 0) > _t.time(),
        f"空结果也记冷静期：{out3}")
    h2._reseed_cloud_map(["src1"])
    _ok(h2._iyuu_client.calls == 1, f"冷静期内只查过一次：{h2._iyuu_client.calls}")

    print("\n" + "=" * 66)
    print(f"PASS：{CHECKS} 项断言全部通过 ✅")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as err:  # noqa: BLE001
        print(f"\n{err}\nFAIL", file=sys.stderr)
        sys.exit(1)
