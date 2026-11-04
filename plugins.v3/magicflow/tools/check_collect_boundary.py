# -*- coding: utf-8 -*-
"""护栏㉖ · 采集边界（collect.py 五条铁律的机器化）

`collect.py` 的 docstring 写着两条铁律：

    1. **采集就一个人干**：抓 + **解析** + 配额 + 缓存 + 事实库，全归这里；别人只拿。
    2. **采集也是唯一的手**：全仓只有它碰网络。

19.10.30 之前，这两条**只活在 docstring 里**（preflight 25 步没有任何一条检查它），
于是长出一堆「抓在 collect、解析在业务模块」的半遵守：
    · ``hrbills._hr_myhr_parse``（myhr 列表）—— 抓走 ``c.http.text(kind="hr")``，解析自留
    · ``rss._rss_parse`` / ``reseed._rss_fetch``（RSS）—— 连抓都自己发 RequestUtils
    · ``claim._claim_parse_table``（认领页）—— 同上

本检查做三件事：

  R1 **解析不许长在业务模块**（19.10.35 起范围 = **根目录 py + features/**）：出现
     「HTML/XML 解析正则」（``re.findall(r"<tr…")`` 这类字面量含标签前缀的模式）→ 报红。
     ★ 原来只扫 ``features/``，于是根目录 30 多个模块没人管 —— ``fetcher.py`` 攒下
     250 行列表页解析就是这么漏的。规则看不见的地方就会长出规矩之外的东西。
     不扫 ``signin_sites/``：那是「一站一文件」的站点适配扩展点，抓+解析刻意耦合。
  R2 **网络不许长在 features/**：出现 ``RequestUtils(...)`` / ``requests.*`` /
     ``urlopen`` → 报红。（仍只管 ``features/``：``collect.py`` 是唯一该有网络的，
     ``signin_sites`` 有自己的站点开关。）
  R3 **解析不许回长进 collect.py**（19.10.31 新增）：解析那 800 行已下沉到 L0
     ``collect_parse.py``；``collect.py`` 只留传输 / 配额 / 事实库 / 观测。
     再在里面写页面解析正则 → 报红（否则一年后又长回 2460 行）。

两处**有理由的豁免**登记在 ``ALLOW``（改这里的门槛是「写清楚为什么」）：

  · ``features/debug.py``  —— ``KIND_TTL["debug"] = 0.0``：调试端点天生要裸拿原始响应，
    走 collect 的缓存/配额反而看不到真问题。
  · 外部服务（豆瓣 / IYUU / 云盘）—— ``SCOPE_SERVICE``，collect 的 ``svc()`` docstring
    明说「只登记与计时，实现仍在其模块」，且它们不在 ``features/`` 下（本检查扫不到）。

用法：``python3 tools/check_collect_boundary.py``（0=PASS / 1=有违规）。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / "features"

# ── 解析动作：这些函数第一个参数是「正则字面量」时才算解析 ────────────────────
_RE_FUNCS = {"findall", "finditer", "search", "match", "fullmatch", "sub", "compile", "split"}

# ── 网络动作：模块名 / 函数名 ────────────────────────────────────────────────
_NET_NAMES = {"RequestUtils", "urlopen", "Session"}
_NET_ATTRS = {"requests", "httpx", "aiohttp", "urllib"}

# ── 永久豁免：(相对路径, 规则) → 理由 ────────────────────────────────────────
ALLOW: Dict[Tuple[str, str], str] = {
    ("features/debug.py", "parse"): "调试端点：KIND_TTL['debug']=0，天生要裸拿原始响应",
    ("features/debug.py", "net"): "同上",
}

# ── 已知待搬（棘轮）：登记的是**存量债务**，不算通过 ──────────────────────────
#   每搬一处就删一条；**新增**任何一条都算违规（护栏的意义就在这）。
#   19.10.30 第一批已搬：myhr 列表 / 认领页 / RSS×2；
#   19.10.31 已搬：reseed 详情页 XPath（→ collect_parse.parse_detail_download_link）
#                  → 解析侧债务清零，全表只剩 net。
PENDING: Dict[Tuple[str, str], str] = {
    ("features/brush.py", "net"): "download.php 取 .torrent 算 hash → 应走 c.http.client()",
    ("features/claim.py", "net"): "userdetails.php / claim.php 抓取 → 应走 c.site(sid).page()",
    ("features/crossseed.py", "net"): "HDDolby api.<domain> 搜索 POST → 与 reseed 逐字重复，应收进 SiteView.api_search",
    ("features/live.py", "net"): "HDDolby api.<domain> 实时值 → 应走 c.http.api()",
    ("features/reseed.py", "net"): "详情页 / RSS / API 三处抓取 → 应走 c.http.text() / c.http.api()",
    # ★ 19.10.35：R1 扩到根目录后才看得见的最后一处页面解析。
    ("live_stats.py", "parse"): "考核/免费区块 HTML 去标签与逐项提取 → 应搬进 collect_parse.py（账号态事实，与 myhr/认领同类）",
}

# ── 不在 R1 管辖范围的「解析层的家」──────────────────────────────────────────
#   这两个文件**就是**解析层，里面出现 HTML 正则不是越界，是本分。
#   与 ALLOW 的区别：ALLOW 是「违规但有理由」，这里是「不在管辖范围」。
PARSE_HOME = {"collect_parse.py", "collect_rows.py"}


# ── HTML/XML 解析特征：正则字面量里出现这些**标签前缀**才算解析 ──────────────
#   为什么不直接判「含 ``<``」：``(?<=…)`` / ``(?<name>…)`` 也含 ``<``，
#   而它们在 features/ 里大量出现（分词、去重、锚点）→ 会满屏误报。
_HTML_TAG_MARKERS = (
    "<tr", "<td", "<th", "<table", "<a ", "<a[", "<item", "<entry", "<title",
    "<link", "<enclosure", "<size", "<pubdate", "<description", "<script",
    # ★ 19.10.35：原为 ``"<[^"``，过宽 —— Vue 泛型 ``(?:<[^<>]*>)?``（codedict）也含它。
    #   真正的「去标签」写法是 ``<[^>]+>``，收紧到这个形状即可（live_stats 命中、
    #   Vue 泛型不再命中）。``(?P<title>`` 这类命名组由下面的前缀排除处理。
    "<[^>]",
)


def _is_html_pattern(node: ast.AST) -> bool:
    """正则字面量里带 HTML/XML 标签前缀 → 认作「页面解析」。

    ★ 19.10.35：排除正则**命名组**写法。``(?P<title>.+?)`` 里的 ``<title`` 与 XML 标签
    同形，但它是在给捕获组起名（fallback.py 的标题切分就这么写），不是解析页面。
    判据：标记前紧邻 ``(?P`` → 不是标签。
    """
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    low = node.value.lower()
    for marker in _HTML_TAG_MARKERS:
        start = 0
        while True:
            idx = low.find(marker, start)
            if idx < 0:
                break
            if not low[:idx].endswith("(?p"):
                return True
            start = idx + 1
    return False


def _call_name(node: ast.Call) -> Tuple[str, str]:
    """(接收者, 方法名)：``re.findall`` → ("re", "findall")；``x.search`` → ("x", "search")。"""
    f = node.func
    if isinstance(f, ast.Attribute):
        recv = ""
        if isinstance(f.value, ast.Name):
            recv = f.value.id
        elif isinstance(f.value, ast.Attribute):
            recv = f.value.attr
        return recv, f.attr
    if isinstance(f, ast.Name):
        return "", f.id
    return "", ""


def scan(path: Path) -> List[Dict[str, Any]]:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    hits: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        recv, name = _call_name(node)
        # R1 解析
        if name in _RE_FUNCS and recv in ("re", "_re") and node.args:
            if _is_html_pattern(node.args[0]):
                hits.append({"file": rel, "line": node.lineno, "rule": "parse",
                             "what": f"{recv}.{name}({ast.unparse(node.args[0])[:60]})"})
        # R2 网络
        elif name in _NET_NAMES or (recv in _NET_ATTRS and name in {"get", "post", "request", "Session"}):
            hits.append({"file": rel, "line": node.lineno, "rule": "net",
                         "what": f"{recv + '.' if recv else ''}{name}(…)"})
        elif recv in _NET_ATTRS and name == "request":
            hits.append({"file": rel, "line": node.lineno, "rule": "net",
                         "what": f"{recv}.request(…)"})
        # ``lxml.etree`` / ``BeautifulSoup`` 这类外部解析器（import 层面）
    # import 层面的解析库
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "lxml" in node.module or node.module.split(".")[0] == "bs4":
                hits.append({"file": rel, "line": node.lineno, "rule": "parse",
                             "what": f"from {node.module} import …"})
        elif isinstance(node, ast.Import):
            for a in node.names:
                if "lxml" in a.name or a.name.split(".")[0] == "bs4":
                    hits.append({"file": rel, "line": node.lineno, "rule": "parse",
                                 "what": f"import {a.name}"})
    return hits


def _scan_files() -> List[Path]:
    """R1 的扫描范围：**根目录 py + features/**。

    ★ 19.10.35 为什么要扩到根目录：R1 原来只扫 ``features/``，于是根目录那 30 多个模块
    里的页面解析完全没人管 —— ``fetcher.py`` 攒下 250 行列表页解析就是这么漏的
    （改一次皮肤要绕开 ``SiteFetcher`` 与 ``_ensure_sdk()``）。规则看不见的地方，
    就会长出规矩之外的东西。

    ★ 为什么仍**不扫 signin_sites/**：那是「一站一文件」的站点适配扩展点，抓取 + 解析
    刻意耦合在同一个 ``SiteSignIn`` 子类里（MP 生态惯例，16 个站的格式各不相同），
    且不在配额 / 熔断 / RSS 主路径上 —— 搬走只会让「加一个签到站」从改一个文件变成改两个。
    这是设计取舍，不是漏网。
    """
    out = list(ROOT.glob("*.py")) + list(FEATURES.rglob("*.py"))
    return sorted(p for p in out if "__pycache__" not in p.parts)


def main() -> int:
    bad: List[Dict[str, Any]] = []
    allowed = 0
    pending: List[Dict[str, Any]] = []
    files = _scan_files()
    for p in files:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        in_features = rel.startswith("features/")
        for h in scan(p):
            # R2（网络）仍只管 features/：根目录里 collect.py 是唯一该有网络的地方，
            # signin_sites 的裸 RequestUtils 是站点适配层自己的开关（见上）。
            if h["rule"] == "net" and not in_features:
                continue
            # 解析层的家：出现 HTML 正则是本分，不是越界
            if h["rule"] == "parse" and rel in PARSE_HOME:
                continue
            # collect.py 的解析由下面 R3 单独判（判得更准，会指出该搬去哪）
            if h["rule"] == "parse" and rel == "collect.py":
                continue
            key = (h["file"], h["rule"])
            if key in ALLOW:
                allowed += 1
            elif key in PENDING:
                pending.append(h)
            else:
                bad.append(h)

    # R3：collect.py 自己不许再长解析（19.10.31 拆出 collect_parse.py 之后）
    back: List[Dict[str, Any]] = []
    collect_py = ROOT / "collect.py"
    if collect_py.is_file():
        back = [h for h in scan(collect_py) if h["rule"] == "parse"]
    if back:
        print(f"❌ collect.py 里又长出 {len(back)} 处页面解析（铁律 1 的解析层已拆到 collect_parse.py）\n")
        for h in back:
            print(f"    L{h['line']:<5} [parse] {h['what']}")
        print("\n修法：把这段解析搬到 ``collect_parse.py``（L0 纯函数，只 import 标准库 + norm），")
        print("      ``collect.py`` 顶部的 ``from .collect_parse import (...)`` 全量 re-export")
        print("      会把它带回来；业务模块的 import 面不用改。")
        return 1

    if not bad:
        note = f"，{allowed} 处登记豁免" if allowed else ""
        debt = f"；{len(pending)} 处已知待搬（见 PENDING）" if pending else ""
        print(f"采集边界：{len(files)} 个模块（根目录 + features/），0 处新增越界{note}{debt}")
        return 0

    print(f"❌ {len(bad)} 处越过 collect 边界（铁律 1「解析归采集」/ 铁律 2「唯一的手」）\n")
    cur = None
    for h in bad:
        if h["file"] != cur:
            cur = h["file"]
            print(f"  {cur}")
        print(f"    L{h['line']:<5} [{h['rule']}] {h['what']}")
    print("\n修法二选一：")
    print("  · 解析（parse）→ 搬到 collect_parse.py 做成 ``parse_xxx_rows/page/items`` 纯函数，"
          "业务模块只留 ``from ..collect import parse_xxx``")
    print("  · 抓取（net）→ 走 ``c.http.text()`` / ``c.http.client()`` / ``c.site(sid).page()``，"
          "让配额闸门、PV 熔断、页缓存、观测都能看见")
    print("  · 有正当理由要留在原地 → 在 ALLOW 里登记 (文件, 规则) 并写明理由")
    print("  · 暂时搬不动的存量 → 登记进 PENDING 并写清「该搬去哪」，别静默放过")
    return 1


if __name__ == "__main__":
    sys.exit(main())
