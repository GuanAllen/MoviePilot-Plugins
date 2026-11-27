#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 列表页逐种 H&R 标签解析离线回归测试（17.2.2）。

背景（2026-10-14 实测）：
  - ``carpt.net`` 列表页 **每行** 都带 ``<img class="hitandrun" src="pic/trans.gif" alt="H&R" title="H&R" />``
    （该站是站点级 H&R，102/102 行）；
  - ``dstudio.me`` 同皮肤，但只在「有 H&R 的种子」上带这个黑色标签
    （rules.php 原文：「本站很少有种子存在 H&R，有 H&R 的种子，会显示黑色标签」）；
  - 在此之前 ``SiteFetcher._parse_np_rows`` 把行内 H&R 写死 False，于是自解析路径
    （免费定向视图 / 直连免费索引 / exclude_hnr 初筛）拿不到逐种事实。

覆盖：
  A. 行内带 ``hitandrun`` → ``hit_and_run=True``（且促销/大小/人数解析不受影响）；
  B. 行内不带 → ``hit_and_run=False``；
  C. 页面别处（图例区）带 ``hitandrun``、但本行不带 → 仍为 False（**逐行判定，不整页外溢**）。

用法：``python3 tools/test_fetcher_hr_label.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = 0


def _ok(cond: bool, label: str) -> None:
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(f"❌ {label}")
    print(f"  ✅ {label}")


def _load_fetcher():
    """加载 ``fetcher.py``。

    ★ 宿主 Python 3.11 兼容：插件运行在 MP 容器的 **Python 3.14**（PEP 649，注解惰性求值），
    而 fetcher.py 里 `def f(...) -> List[SiteCandidateTorrent]` 的位置**在类定义之前**——
    3.11 会在导入期立刻求值注解 → NameError。这里给源码补一行
    ``from __future__ import annotations``（必须排在文件最前）再编译，语义等价。
    """
    name = "mf_fetcher_hr_label"
    src = (ROOT / "fetcher.py").read_text(encoding="utf-8")
    code = compile("from __future__ import annotations\n" + src, str(ROOT / "fetcher.py"), "exec")
    mod = types.ModuleType(name)
    mod.__file__ = str(ROOT / "fetcher.py")
    sys.modules[name] = mod
    exec(code, mod.__dict__)
    return mod


def _row(tid: int, title: str, *, hr_label: bool, promo: str = "pro_50pctdown") -> str:
    label = (
        '<img class="hitandrun" src="pic/trans.gif" alt="H&amp;R" title="H&amp;R" />'
        if hr_label
        else ""
    )
    return (
        f'<tr class="torrent-row">'
        f'<td class="rowfollow torrent-cell-title"><a title="{title}" '
        f'href="details.php?id={tid}&amp;hit=1"><b>{title}</b></a>'
        f'<img class="{promo}" src="pic/trans.gif" alt="50%" title="50%" />{label}</td>'
        f'<td class="rowfollow nowrap torrent-cell-size">643.8<br />MB</td>'
        f'<td class="rowfollow torrent-cell-seeders"><b><a '
        f'href="details.php?id={tid}#seeders">53</a></b></td>'
        f'<td class="rowfollow torrent-cell-time">'
        f'<span title="2026-10-01 12:00:00">1天</span></td>'
        f'<td class="rowfollow"><a href="download.php?id={tid}">下载</a></td>'
        f'</tr>'
    )


def main() -> int:
    mod = _load_fetcher()
    fetcher = mod.SiteFetcher()

    print("[A/B/C] 逐种 H&R 标签按行解析")
    html = (
        '<html><body>'
        # 图例区：整页可见，但**不属于任何行**
        '<div class="legend"><img class="hitandrun" src="pic/trans.gif" '
        'alt="H&amp;R" title="H&amp;R" />H&amp;R 种子</div>'
        '<table class="torrents"><tbody>'
        + _row(101, "Alpha 2026 2160p WEB-DL-DepWeb", hr_label=True)
        + _row(202, "Beta 2026 2160p WEB-DL-DepWeb", hr_label=False)
        + '</tbody></table></body></html>'
    )
    rows = fetcher._parse_np_rows(html, "dstudio.me", "https://dstudio.me", None, None)
    by_id = {re.search(r"details\.php\?id=(\d+)", r.page_url).group(1): r for r in rows}
    _ok(len(rows) == 2, f"两行都解析出来（实际 {len(rows)}）")
    a, b = by_id.get("101"), by_id.get("202")
    _ok(a is not None and b is not None, "两行的 page_url 都能对上 id")

    _ok(a.hit_and_run is True, "★ 行 A（带 hitandrun 标签）→ hit_and_run=True")
    _ok(b.hit_and_run is False, "★ 行 B（不带标签、但页面图例带）→ hit_and_run=False（不整页外溢）")

    for r, name in ((a, "A"), (b, "B")):
        _ok(r.size == 643800000 or abs(r.size_gb - 643.8 / 1024) < 0.01,
            f"行 {name} 大小仍解析（size_gb={r.size_gb:.3f}）")
        _ok(r.seeders == 53, f"行 {name} 做种数仍解析（seeders={r.seeders}）")
        _ok(r.downloadvolumefactor == 0.5 and r.is_free is False,
            f"行 {name} 促销仍解析（dv={r.downloadvolumefactor} / is_free={r.is_free}）")
        _ok(bool(re.search(r"download\.php\?id=\d+", r.enclosure)), f"行 {name} 下载链接仍解析")

    print("[D] 无标签页面（dstudio 现状）不产生 True")
    html2 = ('<table><tbody>'
             + _row(303, "Gamma 2026 2160p WEB-DL-DepWeb", hr_label=False)
             + '</tbody></table>')
    rows2 = fetcher._parse_np_rows(html2, "dstudio.me", "https://dstudio.me", None, None)
    _ok(len(rows2) == 1, "单行页面解析出 1 行")
    _ok(rows2[0].hit_and_run is False, "无标签 → False（不推断、不补默认）")

    print(f"\n✅✅ 全部通过（{CHECKS} 项断言）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(str(e))
        sys.exit(1)
