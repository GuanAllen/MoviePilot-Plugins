#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 直连搜索辅种：搜索词提取 + 结果行解析 离线回归（19.10.63）。

背景：辅种的候选来源原本只有 IYUU 反查一条腿，IYUU 站点表里没有的站（实测 104 站
不含 ``pttime.org``）在 ``_reseed_pairs`` 第一步就被 ``if sid not in site_map: continue``
排除，永远当不了目标站。直连搜索给这类站开第二条腿：自己按片名搜、下种、比特征码。

实测（2026-10-31，PT时间）踩到三个坑，全部在本测试里锁死：
  ① **非贪婪 ``<tr>…</tr>`` 切行会截断** —— 行内嵌 ``<table class="torrentname"><tr>``，
     会在内层 ``</tr>`` 处提前结束，于是体积/做种数/促销全读空；
  ② 体积写成 ``24.35<br>GB``（数字与单位之间夹 ``<br>``），``\\d+\\s*[KMGT]i?B`` 匹配不到；
  ③ 下载直链自带 ``passkey&uid``，是**最有价值的凭据**，绝不能在解析时被丢掉。

断言：
  A. 真实皮肤行 → tid / 标题 / 体积 / 促销 / 中文别名 / 做种数 / 下载直链 全部解出；
  B. 负向对照：旧写法（非贪婪 tr、通用体积正则）在同一份 HTML 上确实拿不到东西
     —— 证明本解析器不是「碰巧对」；
  C. ``search_kw_en``：英文种名切到发布标记为止；多个前缀标签全剥；中文名只取中文段；
  D. ``as_bool_arg`` 三态；
  E. ``sites/search_presets.py`` 每站字段齐全、``resolve`` 抗 ``www.``/大小写/未知域；
  F. 直连站合成 sid 基址远高于 IYUU sid（不撞号）；
  G. 源码护栏：干跑命中**不写** ok 台账（ok TTL 90 天，写了真跑 90 天不碰）；
  H. 配置面 models / status / 前端三处都有直连搜索键（防保存时静默回填）；
  I. 把 ``reseed_scan`` 的汇总行格式化段**真执行**一遍（占位符错位只在运行时炸）；
  J. 第二种行皮肤（Depth Studio）：置顶行带 class、**普通行裸 ``<tr>``** 都要解出，
     且裸 ``download.php?id=`` 直链要保留 —— 锁的是「按行标签切行不通用」这件事；
  K. 覆盖项不得劫持长期键（``search_sites``/``search_kw`` 只认正式配置）；
  L. 多站时**每站一行**失败构成（``last.by_site`` 是内存属性，重载即失，必须落日志）。

用法：``python3 tools/test_reseed_search.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_reseed_search_test"
CHECKS = 0
FAILS: list = []


def _pkg(name: str, path: Path) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def check(ok: bool, label: str) -> bool:
    global CHECKS
    CHECKS += 1
    print(("  ✓ " if ok else "  ✗ ") + label)
    if not ok:
        FAILS.append(label)
    return ok


_pkg(PKG, ROOT)
_load(PKG + ".norm", "norm.py")
CP = _load(PKG + ".collect_parse", "collect_parse.py")
PRESETS = _load(PKG + ".search_presets", "sites/search_presets.py")


# --------------------------------------------------------------------- 样本
# 结构取自 2026-10-31 实测 PT时间 搜索页（只裁掉与本解析无关的图片/脚本）：
# 行内嵌 table、体积 br 分隔、促销 font、直链带 passkey&uid —— 四个坑一个不少。
ROW_HTML = """<tr data=63400>
<td class="rowfollow" valign="middle"><a class='dib' href="?cat=402">
<span class="category dib c_tvseries" title="TV Series"></span></a></td>
<td class="rowfollow" align="left"><table class="torrentname" width="100%"><tr>
<td class='torrentimg image-cell on_show'><img class="lazy-image" data-src="/public/douban/10465145.webp"></td>
<td class="embedded"><a title="A Gentlemans Dignity S01 2012 720p NF WEB-DL DDP 2.0 x264-ARiN"
 class="torrentname_title" href="details.php?id=63400&amp;hit=1">
<b title="A Gentlemans Dignity S01 2012 720p NF WEB-DL DDP 2.0 x264-ARiN">A Gentlemans Dignity S01 2012 720p</b></a>
<font class='promotion halfdown' >50%免费</font><br>
<font title="绅士的品格 / 绅士的风度 / The Dignity Of The Gentleman">绅士的品格 / 绅士的风度</font></td>
<td class="embedded"><a href="download.php?id=63400&amp;passkey=PK123&amp;uid=116940"
 title='点击下载该种子'>DL</a></td>
</tr></table></td>
<td class="rowfollow dn" style='display:none'>0</td>
<td class="rowfollow"><a href="viewsnatches.php?id=63400"><b>3</b></a></td>
<td class="rowfollow"><span class="red">7</span></td>
<td class="rowfollow">24.35<br>GB</td>
</tr>"""

# 结构取自 2026-10-31 实测 Depth Studio 搜索页（只裁掉图片/脚本/lazy-load）：
# ① 置顶行显式带 `torrent-sticky-row` + `data-sticky-level`，但**普通行是裸 `<tr>`**；
# ② 标题不在 `torrentname_title` 里，是 `<a title="…" href="details.php?id=…"><b>…</b></a>`；
# ③ 直链是**裸** `download.php?id=`（无 passkey）——取种必须靠站点 cookie；
# ④ 体积写成 `<br />`（带空格），与 PT时间 的 `<br>` 不同形态。
DS_HTML = """<tr class="torrent-sticky-row torrent-sticky-row--second" style="background-color: #aadbf3" data-sticky-level="second">
<td class="rowfollow nowrap torrent-cell-type"><a href="?cat=402"><img class="c_tvseries" /></a></td>
<td class="rowfollow torrent-cell-title" width="100%"><table class="torrentname" width="100%"><tr class="torrent-sticky-row torrent-sticky-row--second">
<td class="embedded"><a title="The Great Long March 2026 S01E39 2160p iQ WEB-DL DDP5.1 H.265-DepWeb" href="details.php?id=5177&amp;hit=1"><b>The Great Long March 2026 S01E39 2160p iQ WEB-DL DDP5.1 H.265-DepWeb</b></a>
<img class="pro_free" src="pic/trans.gif" alt="Free" /></td>
</tr></table></td>
<td class="rowfollow"><a href="download.php?id=5177"><img class="download" /></a></td>
<td class="rowfollow">1.48<br />GB</td>
</tr>
<tr>
<td class="rowfollow nowrap torrent-cell-type"><a href="?cat=402"><img class="c_tvseries" /></a></td>
<td class="rowfollow torrent-cell-title" width="100%"><table class="torrentname" width="100%"><tr>
<td class="embedded"><a title="The Great Long March 2026 S01E38 2160p iQ WEB-DL DDP5.1 H.265-DepWeb" href="details.php?id=5176&amp;hit=1"><b>The Great Long March 2026 S01E38 2160p iQ WEB-DL DDP5.1 H.265-DepWeb</b></a></td>
</tr></table></td>
<td class="rowfollow"><a href="download.php?id=5176"><img class="download" /></a></td>
<td class="rowfollow">1.45<br />GB</td>
</tr>"""


def main() -> int:
    print("[A] 真实皮肤行解析")
    rows = CP.parse_np_search_rows(ROW_HTML)
    check(len(rows) == 1, "解出 1 行")
    r = rows[0] if rows else {}
    check(r.get("tid") == "63400", "tid = 63400")
    check("A Gentlemans Dignity S01 2012 720p" in str(r.get("title")), "标题取 <b title>")
    check(abs(float(r.get("size_gb") or 0) - 24.35) < 1e-6, "体积 24.35 GB（br 分隔）")
    check(r.get("promo") == "halfdown" and "50%" in str(r.get("promo_text")),
          "促销 halfdown / 50%免费")
    check("绅士的品格" in str(r.get("alias")), "中文别名解出")
    check(r.get("seeds") == 7, "做种数 7")
    check(str(r.get("download_url") or "").startswith("download.php?id=63400"),
          "下载直链保留（相对形态）")
    check("passkey=PK123" in str(r.get("download_url") or ""), "直链里的 passkey 没被丢")
    check("&amp;" not in str(r.get("download_url") or ""), "实体 &amp; 已解成 &")

    print("[B] 负向对照：旧写法在同一份 HTML 上拿不到")
    old_rows = [x for x in re.findall(r"<tr[^>]*>.*?</tr>", ROW_HTML, re.S)
                if "download.php" in x]
    check(len(old_rows) == 1, "旧写法也能切出 1 块（但内容是截断的）")
    check("<br>GB</td>" not in (old_rows[0] if old_rows else ""),
          "旧写法的块**丢掉了体积列**（内层 </tr> 截断）")
    check(not re.findall(r"\d+(?:\.\d+)?\s*[KMGT]i?B", ROW_HTML),
          "通用体积正则 ``\\d+\\s*[KMGT]i?B`` 在 br 形态上零命中")

    print("[C] 搜索词提取 search_kw_en")
    cases = [
        ("Toy.Story.1995.2160p.UHD.BluRay.x265-TERMiNAL", "Toy Story"),
        ("[VCB-Studio] Toaru Majutsu no Index III [Ma10p_1080p]", "Toaru Majutsu no Index III"),
        ("[BDMV][Movie]", ""),
        ("The.Phoenician.Scheme.2025.1080p.WEB-DL", "The Phoenician Scheme"),
        ("Postman.1997.1080p.BluRay.x264", "Postman"),
        ("唐朝诡事录之长安.Tang.Chao.2025.S01", "唐朝诡事录之长安"),
        ("", ""),
    ]
    for src, want in cases:
        got = CP.search_kw_en(src)
        check(got == want, f"{src[:42]!r} → {want!r}（得 {got!r}）")

    print("[D] as_bool_arg 三态")
    for v, want in ((None, None), ("", None), ("  ", None),
                    ("0", False), ("false", False), ("off", False), ("no", False),
                    ("1", True), ("true", True), ("yes", True)):
        check(CP.as_bool_arg(v) is want, f"as_bool_arg({v!r}) is {want}")

    print("[E] 站点预设表")
    conf = PRESETS.resolve("pttime.org")
    check(conf is not None and conf.get("name") == "PT时间", "pttime.org 命中 PT时间")
    check(PRESETS.resolve("www.PTTime.org") is conf, "www./大小写不敏感")
    check(PRESETS.resolve("example.invalid") is None, "未知域名返回 None")
    for dom in PRESETS.domains():
        c = PRESETS.SEARCH_SITES[dom]
        ok = (bool(c.get("name")) and bool(c.get("path"))
              and isinstance(c.get("params"), dict)
              and "{kw}" in str((c.get("params") or {}).get("search") or "")
              and int(c.get("kw_per_round") or 0) > 0
              and float(c.get("delay") or 0) > 0)
        check(ok, f"{dom} 字段齐全（name/path/params{{kw}}/kw_per_round/delay）")

    print("[F] 源码护栏：直连站 sid 不与 IYUU sid 重叠")
    src = (ROOT / "features/reseed.py").read_text(encoding="utf-8")
    m = re.search(r"^DIRECT_SID_BASE\s*=\s*(\d+)$", src, re.M)
    check(m is not None, "DIRECT_SID_BASE 已定义")
    base = int(m.group(1)) if m else 0
    check(base >= 10000, f"基址 {base} 远高于 IYUU sid 量级（1~200），不会撞号")

    print("[G] 源码护栏：干跑命中不写 ok 台账（ok TTL 90 天，写了真跑 90 天不碰）")
    #   这条是「干跑一跑、真跑就废」的反向断言：ok 的 _reseed_ledger_put 必须被
    #   `if not dry:` 包住。只断言「存在 if not dry」，并确认它紧邻 ok 写入之前。
    idx = src.find("搜索命中 tid=")
    seg = src[max(0, idx - 400):idx] if idx >= 0 else ""
    check(idx > 0, "找到搜索命中的 ok 台账写入点")
    check("if not dry:" in seg, "ok 台账写入受 `if not dry:` 保护")
    check(src.count("dry=bool(dry))") >= 1, "reseed_round 把 dry 透传给搜索候选源")

    print("[H] 配置面：models / status / 前端三处都有直连搜索键（防保存时静默回填）")
    models_src = (ROOT / "models.py").read_text(encoding="utf-8")
    status_src = (ROOT / "features/status.py").read_text(encoding="utf-8")
    utils_src = (ROOT / "src/utils.js").read_text(encoding="utf-8")
    check("reseed_search_sites" in models_src, "models.py 有 reseed_search_sites")
    check("reseed_search_kw" in models_src, "models.py 有 reseed_search_kw")
    check("_reseed_search_sites" in status_src, "status.py 设置面输出 search_sites")
    check("reseed_search_sites" in utils_src, "src/utils.js 归一化 search_sites")
    use_tasks_src = (ROOT / "src/views/magicflow/composables/useTasks.js").read_text(encoding="utf-8")
    check("reseed_search_sites: Array.isArray(status.value.reseed.search_sites)"
          in use_tasks_src, "useTasks.js 回填 search_sites（API-02）")

    print("[I] 汇总行实执行：把 reseed_scan 里那段 % 格式化**真跑一遍**")
    #   ★ 为什么不用「grep 到关键字就算过」：占位符与参数个数错位在运行时才炸，而且被
    #     `except` 吞成「本轮异常」——日志里只会少一行，没人发现。这里直接抽源码段执行。
    start = src.index('_sfrag = ""')
    tail = src[start:start + 2600]
    end = tail.index("_sfrag)\n            )") + len("_sfrag)\n            )")
    seg = "\n".join(l[12:] if l.startswith(" " * 12) else l
                    for l in tail[:end].splitlines())

    class _Cap(object):
        def __init__(self):
            self.msg = None

        def info(self, m):
            self.msg = m

        def error(self, m):
            self.msg = "ERR:" + m

    # `_search_site_brief` 也被汇总行调用 —— 同样抽源码执行，别在测试里写替身
    _bf: dict = {}
    exec(src[src.index("def _search_site_brief"):src.index("def _rlog")], _bf)  # noqa: S102
    _brief = _bf["_search_site_brief"]

    base = {"plan": 10, "ok": 6, "have": 2, "mismatch": 0, "fail": 1, "nourl": 1, "pv": 0,
            "flow": 1, "nosave": 0, "gone": 0, "would": 0, "dup": 1758, "too_small": 87,
            "duration": 2102.0, "downshift": True, "min_size_used": 1.5,
            "search_kw": 20, "search_hit": 3, "search_nomatch": 14,
            "search_size_miss": 5, "search_fp_miss": 0, "search_dead": 1,
            "search_quota": 1, "search_nokw": 2}
    cap = _Cap()
    exec(seg, {"logger": cap, "rep": dict(base), "_search_site_brief": _brief})  # noqa: S102
    check(cap.msg is not None and not str(cap.msg).startswith("ERR:"), "汇总行能格式化（无占位符错位）")
    check("直连搜索 20词 → 命中 3 / 无此片 14 / 体积不符 5 / 特征码不符 0" in str(cap.msg),
          "汇总行含搜索产出四段")
    check("会话失效 1" in str(cap.msg) and "配额截断 1" in str(cap.msg),
          "汇总行含异常计数（会话失效/配额截断）")
    cap2 = _Cap()
    r2 = dict(base)
    r2.pop("search_kw")
    exec(seg, {"logger": cap2, "rep": r2, "_search_site_brief": _brief})          # noqa: S102
    check("直连搜索" not in str(cap2.msg), "搜索未启用时汇总行不带搜索段")

    # 按站明细：多站才拼 —— 合计「命中 1 / 无此片 30」回答不了「哪站在白跑」
    by2 = dict(base)
    by2["by_site"] = {"PT时间": {"search_kw": 20, "search_hit": 0},
                      "Depth Studio": {"search_kw": 20, "search_hit": 1}}
    cap3 = _Cap()
    exec(seg, {"logger": cap3, "rep": by2, "_search_site_brief": _brief})         # noqa: S102
    check("（PT时间 20/0 · Depth Studio 20/1）" in str(cap3.msg),
          "汇总行带按站明细「站名 词数/命中」")
    by1 = dict(base)
    by1["by_site"] = {"PT时间": {"search_kw": 20, "search_hit": 1}}
    cap4 = _Cap()
    exec(seg, {"logger": cap4, "rep": by1, "_search_site_brief": _brief})         # noqa: S102
    check("PT时间 20/1" not in str(cap4.msg), "单站时不拼按站明细（合计已够）")
    check(_brief({"A": {"search_kw": 3, "search_hit": 1}}) == "", "单站返回空串")
    check(_brief(None) == "" and _brief({}) == "", "无 by_site 时容错")

    print("[L] 多站时每站一行失败构成（必须落日志：last.by_site 是内存的，重载即失）")
    _lstart = src.index('if len(st.get("by_site") or {}) > 1:')
    _lend = src.index("        return out", _lstart)
    _lseg = "\n".join(l[8:] if l.startswith(" " * 8) else l
                      for l in src[_lstart:_lend].splitlines())
    _logs: list = []

    def _cap_log(m, level="info"):
        _logs.append(m)

    _st2 = {"by_site": {
        "PT时间": {"search_kw": 20, "search_hit": 1, "search_nomatch": 12,
                   "search_size_miss": 5, "search_fp_miss": 2, "search_quota": 1},
        "Depth Studio": {"search_kw": 20, "search_hit": 0, "search_nomatch": 16,
                         "search_size_miss": 3, "search_fp_miss": 1},
    }}
    exec(_lseg, {"st": _st2, "_rlog": _cap_log})            # noqa: S102
    check(len(_logs) == 2, f"两站各打一行，得 {len(_logs)}")
    _d = [x for x in _logs if "Depth Studio" in x]
    check(bool(_d) and "搜 20 词 → 命中 0 / 无此片 16 / 体积不符 3 / 特征码不符 1" in _d[0],
          "Depth Studio 那行含四段失败构成")
    _p = [x for x in _logs if "PT时间" in x]
    check(bool(_p) and "配额截断 1" in _p[0], "异常计数只出现在有计数的那站")
    check(bool(_d) and "配额截断" not in _d[0], "没有配额的站不拼异常段")
    _logs.clear()
    exec(_lseg, {"st": {"by_site": {"PT时间": {"search_kw": 20, "search_hit": 1}}},
                 "_rlog": _cap_log})                        # noqa: S102
    check(not _logs, "单站时不打（合计行已够）")
    _logs.clear()
    exec(_lseg, {"st": {"by_site": {"A": {"search_kw": 0}, "B": {"search_kw": 3}}},
                 "_rlog": _cap_log})                        # noqa: S102
    check(len(_logs) == 1 and "B" in _logs[0], "这轮没搜的站不占用日志行")

    print("[J] 第二种行皮肤（Depth Studio）：置顶行带 class，**普通行是裸 <tr>**")
    #   ★ 这条锁的是「按行标签切行根本不通用」：同一份 NexusPHP，PT时间 的行是
    #     `<tr data=NNN>`，Depth 的普通行**不带任何属性**，唯一稳定的锚是行内那张
    #     `<table class="torrentname">`。实测按标签切只拿到 9/39 行（漏 77%）。
    drows = CP.parse_np_search_rows(DS_HTML)
    check(len(drows) == 2, f"两行全解出（含裸 <tr> 行），得 {len(drows)}")
    d1 = drows[0] if drows else {}
    d2 = drows[1] if len(drows) > 1 else {}
    check(d1.get("tid") == "5177" and d2.get("tid") == "5176",
          "tid 从行内 details.php 取（不是行标签属性）")
    check(abs(float(d1.get("size_gb") or 0) - 1.48) < 1e-6, "体积 1.48 GB（`<br />` 带空格形态）")
    check(abs(float(d2.get("size_gb") or 0) - 1.45) < 1e-6, "裸 <tr> 行体积 1.45 GB")
    check("The Great Long March 2026 S01E39" in str(d1.get("title")),
          "标题走 details.php 锚点兜底（该皮肤没有 torrentname_title）")
    check(str(d1.get("download_url") or "") == "download.php?id=5177",
          "裸直链（无 passkey）原样保留 —— 取种靠站点 cookie")
    check("passkey" not in str(d1.get("download_url") or ""), "确认这条链本来就没有口令")
    old_style = re.findall(r"<tr\s+data=\d+>", DS_HTML, re.I)
    check(not old_style, "负向对照：这份 HTML 里没有任何 `<tr data=NNN>`（旧切法必然 0 行）")
    check(CP.parse_np_search_rows(DS_HTML.replace('<table class="torrentname"', "<table"))
          == [], "没有 torrentname 表的页面 → 不解（不猜）")
    dconf = PRESETS.resolve("www.DStudio.me")
    check(dconf is not None and dconf.get("name") == "Depth Studio",
          "dstudio.me 已登记且抗 www./大小写")

    print("[K] 覆盖项不得劫持长期键（search_sites/search_kw 只认正式配置）")
    #   ★ 这条锁 19.10.64 的真 bug：认领了却不摘覆盖项 ⇒ `_reseed_cfg()` 的
    #     「覆盖项优先」让正式配置永远失效（设置面显示 A、实际跑 B）。
    #     加第二站时暴露：PUT 正式配置加了 dstudio.me，接口仍报只有 pttime.org。
    core_src = (ROOT / "features/core.py").read_text(encoding="utf-8")
    cfg_seg = src[src.index("def _reseed_cfg"):src.index("def set_reseed_cfg")]
    check('k in ("search_sites", "search_kw")' in cfg_seg and "continue" in cfg_seg,
          "_reseed_cfg 跳过覆盖项里的两个长期键")
    set_seg = src[src.index("def set_reseed_cfg"):src.index("def _reseed_ledger")]
    check("apply_reseed_search_cfg" in set_seg, "set_reseed_cfg 把长期键转交正式配置")
    check('cur.pop("search_sites", None)' in set_seg,
          "set_reseed_cfg 不把长期键留在覆盖项里")
    check("def apply_reseed_search_cfg" in core_src, "core.py 提供 apply_reseed_search_cfg")
    adopt = core_src[core_src.index("def _adopt_legacy_reseed_search"):
                     core_src.index("def apply_reseed_search_cfg")]
    check('k not in ("search_sites", "search_kw")' in adopt,
          "认领后**摘除**覆盖项（不留着继续劫持）")
    check('"reseed_search_sites": list(getattr' in core_src,
          "_current_config() 回写 search_sites（否则落盘会丢）")

    print()
    if FAILS:
        print(f"FAIL · {len(FAILS)}/{CHECKS} 项未过")
        for f in FAILS:
            print("   -", f)
        return 1
    print(f"PASS · {CHECKS} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
