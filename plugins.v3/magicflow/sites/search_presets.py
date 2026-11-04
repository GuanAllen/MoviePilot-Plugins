# -*- coding: utf-8 -*-
"""魔流 · 直连搜索站预设表（search presets）。

**为什么需要这张表**：辅种的候选来源原本只有一条腿 —— IYUU 反查
（``cli.query(want, sids=[…])``）。IYUU 站点表里没有的站（实测 2026-10-31：
104 站里不含 ``pttime.org``），在 ``_reseed_pairs`` 第一步就被
``if sid not in site_map: continue`` 排除，**永远当不了辅种目标站**。

直连搜索把候选来源补成两条腿：绕开 IYUU，自己在站点按片名搜，
用「体积粗筛 + 文件列表特征码确证」配对。站点差异全在这张表里，代码零字面量。

字段
----
``name``         站点显示名（与 MP 站点名一致，用于「资源组里是否已有该站」的判定）
``path``         搜索页路径（相对站点根，不带前导 ``/``）
``params``       查询参数模板；``{kw}`` = 搜索词，其余原样透传
``kw_per_round`` 每轮最多搜几个词（礼貌上限，不是能力上限）
``delay``        两次搜索之间的间隔秒数
``note``         实测结论 / 已知坑（写给人看，代码不读）

★ 只放**已实测**的站。加新站前先确认三件事：
  ① 列表页能用站点会话（cookie 绑 UA）打开；② 行内带下载直链或站点能拼链；
  ③ 取回的 .torrent 里 ``info.files`` 能算特征码。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# ------------------------------------------------------------------ 预设表
SEARCH_SITES: Dict[str, Dict[str, Any]] = {
    "pttime.org": {
        "name": "PT时间",
        "path": "torrents.php",
        "params": {"search": "{kw}", "search_area": "0", "search_mode": "0"},
        "kw_per_round": 20,
        "delay": 2.5,
        # 2026-10-31 实测：搜索 200 / 取种 200（application/x-bittorrent）/ 指纹与本机
        # mf_resource.fp 逐字节一致（绅士的品格 tid=63399）。三个坑：
        # ① 行内嵌 table，非贪婪 <tr>…</tr> 会截断（解析器已按 <tr data=> 切）；
        # ② 体积写成 `24.35<br>GB`；
        # ③ 下载直链自带 passkey&uid → 不需要给站点配 passkey 字段。
        # 另外：RSS 对该账号无权限（「请提升用户等级」），所以目录只能走列表页，
        # 即必须有有效 cookie；会话失效会表现为「搜索回登录页」而不是「0 结果」。
        "note": "RSS 无权限；列表页须有效 cookie；行内自带 passkey 直链",
    },
    "dstudio.me": {
        "name": "Depth Studio",
        "path": "torrents.php",
        "params": {"search": "{kw}", "search_area": "0", "search_mode": "0"},
        "kw_per_round": 20,
        "delay": 2.5,
        # 2026-10-31 实测（搜 "Great Long March" → 39 行全部可解析）：
        # ① **RSS 能开（50 条）但不吃 search 参数** —— 传 `search=` 也恒返最近 50 条，
        #    所以 RSS 只能当「最新目录」，做不了按片名搜索，候选来源必须走列表页。
        # ② **行皮肤与 PT时间 不同**：置顶行 `<tr class="torrent-sticky-row …"
        #    data-sticky-level="…">`，**普通行是裸 `<tr>`**（无任何属性）。按行标签切
        #    只能拿到 9/39 行 ⇒ 解析器已改为按 `<table class="torrentname">` 内容锚点切。
        # ③ 直链是**裸** `download.php?id=N`（不带 passkey）：带 cookie 取到 31KB 真种，
        #    不带 cookie 取回 17KB 登录页 ⇒ 取种必须带站点会话（调用方已传 cookie）。
        # ④ 内容是**分集**为主（`S01E39` 这种），与「整季合集」资源组体积差一个量级，
        #    会被 ±5% 粗筛否掉 —— 这是内容形态差异，不是解析问题，别去修匹配。
        "note": "RSS 不吃 search；普通行是裸 <tr>；直链需 cookie 取种；以分集为主",
    },
}


def resolve(domain: str) -> Optional[Dict[str, Any]]:
    """按域名取站点预设（大小写/前后空白不敏感，``www.`` 前缀忽略）。"""
    d = str(domain or "").strip().lower()
    if d.startswith("www."):
        d = d[4:]
    hit = SEARCH_SITES.get(d)
    if hit is not None:
        return hit
    # 域名带端口或子域（``pt.example.com``）时按后缀再试一次
    for key, conf in SEARCH_SITES.items():
        if d == key or d.endswith("." + key):
            return conf
    return None


def domains() -> list:
    """全部已登记站点的域名（供状态展示/测试断言）。"""
    return sorted(SEARCH_SITES.keys())
