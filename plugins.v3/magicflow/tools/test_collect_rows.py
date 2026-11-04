#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 站点列表页/API 行 → 候选种子 解析离线回归（19.10.35 L0 collect_rows）。

为什么能离线跑：``collect_rows.py`` 只 import 标准库（re / time / dataclasses /
datetime / typing / urllib.parse），不碰 ``common``（它顶层 ``from app.schemas.types``）
也不构造 ``SiteFetcher``（那会 ``_ensure_sdk()`` 去导 MoviePilot SDK）。所以拿一段真实
列表页 HTML 就能验「页面 → 候选」这一层，不用起容器、不用真站点。

覆盖：
  A. NexusPHP 官方皮肤：标题/大小/人数/发布时间/下载链接
  B. 促销 class → 系数（free / twoupfree / pro_50pctdown）
  C. ★ 文字促销兜底：class 给 pro_free 但行内写「50%」→ 不得判成免费
  D. 限时免费到期：两种皮肤写法（促销标记后 / 「剩余时间：」单独一行）
  E. ★ 逐行 H&R：图例区带标签不外溢到行
  F. Tailwind 系（div 切行）也能解析
  G. 去重：嵌套小表命中两次时保留字段最全的那份
  H. 叶PT API 行：促销三档 + 权威 hrPunishEnable
  I. 馒头 API 行：discount 词表 + status 嵌套字段
  J. SiteCandidateTorrent 编解码往返（缓存层靠它落 FileCache）
  K. free_time_ok：未知放行 / 够 / 不够
  L. 时间换算与非法输入不炸

用法：``python3 tools/test_collect_rows.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = 0


def ok(cond: bool, label: str) -> None:
    """记一条断言。"""
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(f"❌ {label}")
    print(f"  ✅ {label}")


def load():
    """直接加载 L0 模块（无需包上下文、无需 app 桩）。"""
    spec = importlib.util.spec_from_file_location("collect_rows", ROOT / "collect_rows.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = load()


# ---------------------------------------------------------------- 样本构造
def np_row(
    tid: int,
    title: str,
    *,
    promo_class: str = "pro_50pctdown",
    hr: bool = False,
    size: str = "643.8<br />MB",
    seeders: int = 53,
    leechers: int = 7,
    pubdate: str = "2026-10-01 12:00:00",
) -> str:
    """一条 NexusPHP（CHD/Tailwind 混排）列表行。"""
    label = '<img class="hitandrun" src="pic/trans.gif" alt="H&amp;R" />' if hr else ""
    return (
        f'<tr class="torrent-row">'
        f'<td class="rowfollow torrent-cell-title">'
        f'<a title="{title}" href="details.php?id={tid}&amp;hit=1"><b>{title}</b></a>'
        f'<img class="{promo_class}" src="pic/trans.gif" alt="" />{label}</td>'
        f'<td class="rowfollow nowrap torrent-cell-size">{size}</td>'
        f'<td class="rowfollow torrent-cell-seeders"><b><a '
        f'href="details.php?id={tid}#seeders">{seeders}</a></b></td>'
        f'<td class="rowfollow"><a href="details.php?id={tid}#leechers">{leechers}</a></td>'
        f'<td class="rowfollow torrent-cell-time">'
        f'<span title="{pubdate}">1天</span></td>'
        f'<td class="rowfollow"><a href="download.php?id={tid}">下载</a></td>'
        f'</tr>'
    )


def wrap(*rows: str) -> str:
    """包成一张完整列表页。"""
    return '<html><body><table class="torrents"><tbody>' + "".join(rows) + "</tbody></table></body></html>"


def idx(cands):
    """按 page_url 里的详情 id 建索引。"""
    import re
    out = {}
    for c in cands:
        m = re.search(r"details\.php\?id=(\d+)", c.page_url or "")
        if m:
            out[m.group(1)] = c
    return out


def main() -> int:
    print("[A] 官方/CHD 皮肤：基础字段")
    html = wrap(np_row(101, "Alpha 2026 2160p WEB-DL-DepWeb", seeders=53, leechers=7))
    rows = R.parse_np_rows(html, "demo.org", "https://demo.org", "ck=1", "UA/1.0")
    ok(len(rows) == 1, f"解析出 1 条（实际 {len(rows)}）")
    r = rows[0]
    ok(r.title == "Alpha 2026 2160p WEB-DL-DepWeb", "标题正确")
    ok(abs(r.size - 643.8 * 1024 ** 2) < 1024, f"大小换算成字节（{r.size:.0f}）")
    ok(abs(r.size_gb - 643.8 / 1024) < 1e-6, "size_gb 自动由 __post_init__ 补")
    ok(r.seeders == 53 and r.leechers == 7, "做种/下载人数")
    ok(r.pubdate == "2026-10-01 12:00:00", "发布时间取时间单元格")
    ok(r.age_weeks > 0, f"age_weeks 由发布时间算出（{r.age_weeks:.2f} 周）")
    ok(r.enclosure == "https://demo.org/download.php?id=101", "下载链接绝对化")
    ok(r.site_cookie == "ck=1" and r.site_ua == "UA/1.0", "cookie/ua 原样带出（供入选时取种）")
    ok(r.hash == r.page_url, "行内无 infohash → hash 退化为详情页 URL")

    print("[B] 促销 class → 系数")
    cases = {
        "pro_free": (0.0, 1.0, True, False),
        "pro_free2up": (0.0, 2.0, True, True),
        "pro_50pctdown": (0.5, 1.0, False, False),
        "pro_2up": (1.0, 2.0, False, False),
    }
    for cls, (dv, uv, free, dbl) in cases.items():
        c = R.parse_np_rows(wrap(np_row(1, "T", promo_class=cls)), "d.org", "https://d.org", None, None)[0]
        ok(
            (c.downloadvolumefactor, c.uploadvolumefactor, c.is_free, c.is_double_free) == (dv, uv, free, dbl),
            f"{cls:16s} → dv={dv} uv={uv} free={free} dbl={dbl}",
        )

    print("[C] ★ 文字促销兜底：class 说免费、行内写「50%」→ 不得当免费")
    trap = wrap(
        np_row(301, "含50%文案", promo_class="pro_free").replace(
            '<img class="pro_free" src="pic/trans.gif" alt="" />',
            '<img class="pro_free" src="pic/trans.gif" alt="" />50%',
        )
    )
    c = R.parse_np_rows(trap, "hd", "https://hd", None, None)[0]
    ok(c.downloadvolumefactor == 0.5, f"dv 取文字口径 0.5（实际 {c.downloadvolumefactor}）")
    ok(c.is_free is False, "不再误判为免费（否则会把计费种当免费下回来）")

    print("[D] 限时免费到期：两种皮肤写法")
    official = wrap(
        np_row(401, "限时免费", promo_class="pro_free").replace(
            '<img class="pro_free" src="pic/trans.gif" alt="" />',
            '<font class="promotion free">免费</font>'
            f'<span title="2099-01-01 00:00:00">剩余</span>',
        )
    )
    c = R.parse_np_rows(official, "p.org", "https://p.org", None, None)[0]
    ok(c.free_until == "2099-01-01 00:00:00", "读到促销标记后的 span")
    ok(c.free_remaining_sec > 0, f"剩余秒数为正（{c.free_remaining_sec:.0f}）")

    dstudio = wrap(
        np_row(402, "剩余时间写法", promo_class="pro_free").replace(
            '<img class="pro_free" src="pic/trans.gif" alt="" />',
            '<font class="promotion free">免费</font>'
            '<font>剩余时间：<span title="2099-01-01 00:00:00">2天0时</span></font>',
        )
    )
    c = R.parse_np_rows(dstudio, "ds.me", "https://ds.me", None, None)[0]
    ok(c.free_until == "2099-01-01 00:00:00", "皮肤差异：「剩余时间：」单独一行也读得到")

    print("[E] ★ 逐行 H&R：图例区标签不外溢")
    page = (
        '<html><body>'
        '<div class="legend"><img class="hitandrun" src="pic/trans.gif" alt="H&amp;R" />H&amp;R 说明</div>'
        '<table class="torrents"><tbody>'
        + np_row(501, "带标签", hr=True)
        + np_row(502, "不带标签", hr=False)
        + "</tbody></table></body></html>"
    )
    got = idx(R.parse_np_rows(page, "carpt.net", "https://carpt.net", None, None))
    ok(got["501"].hit_and_run is True, "本行带 hitandrun → True")
    ok(got["502"].hit_and_run is False, "本行不带 → False（图例区不整页外溢）")

    print("[F] Tailwind 系（div 切行）")
    tail = (
        '<html><body><div class="list">'
        '<div class="torrent-info"><a class="torrent-info-text-name" '
        'href="details.php?id=601&amp;hit=1">Gamma S01E01 2160p WEB-DL-GRP</a>'
        '<img class="pro_free" src="pic/trans.gif" alt="free" />'
        '<span class="torrent-info-text-added" title="2026-09-20 08:30:00">2周</span>'
        '<span class="torrent-info-text-size">1.5 GB</span>'
        '<span class="torrent-info-text-seeders">12</span>'
        '<span class="torrent-info-text-leechers">3</span>'
        '<a href="download.php?id=601&amp;passkey=x">下载</a></div>'
        "</div></body></html>"
    )
    rows = R.parse_np_rows(tail, "cspt.cc", "https://cspt.cc", None, None)
    ok(len(rows) == 1, f"div 型皮肤解析出 1 条（实际 {len(rows)}）")
    ok(rows[0].title == "Gamma S01E01 2160p WEB-DL-GRP", "标题取 torrent-info-text-name")
    ok(rows[0].is_free is True, "促销取 pro_free")
    ok(abs(rows[0].size - 1.5 * 1024 ** 3) < 1024, f"大小取 torrent-info-text-size（{rows[0].size:.0f}）")

    print("[G] 去重：同一 id 命中多次时保留字段最全的")
    dup = wrap(
        np_row(701, "Dup 2026", seeders=9),
        np_row(701, "Dup 2026", seeders=9),      # 完全重复
    )
    ok(len(R.parse_np_rows(dup, "d.org", "https://d.org", None, None)) == 1, "两条同 id 合并成 1 条")

    print("[H] 叶PT API 行")
    yema_rows = [
        {
            "id": 9001, "showName": "Yema 2026 1080p WEB-DL",
            "fileSize": 2 * 1024 ** 3, "seedNum": 8, "leechNum": 2,
            "listingTime": "2026-10-01 12:00:00",
            "downloadPromotion": "free", "uploadPromotion": "double_upload",
            "downloadPromotionEndTime": "2099-01-01 00:00:00",
            "hrPunishEnable": True,
        },
        {"id": 9002, "showName": "Half", "downloadPromotion": "half", "uploadPromotion": "none"},
        {"id": "", "showName": "无 id 的行"},
        "不是字典的行",
    ]
    ys = R.parse_yema_rows(yema_rows, site_name="叶PT", domain="yema.pt", site_url="https://yema.pt", site_id=7)
    ok(len(ys) == 2, f"只收有 id 的字典行（实际 {len(ys)}）")
    y = ys[0]
    ok(y.is_free and y.is_double_free, "free + double_upload → 免费且双倍")
    ok(y.hit_and_run is True, "hrPunishEnable 是该站权威 H&R 标记，直接照抄")
    ok(y.api_tid == "9001" and y.page_url == "https://yema.pt/torrent/9001", "api_tid + 详情页 URL")
    ok(y.enclosure == "", "API 站下载直链留到入选时现取")
    ok(y.site_id == 7 and y.site_domain == "yema.pt", "站点信息带出")
    ok(ys[1].downloadvolumefactor == 0.5, "half → 0.5")

    print("[I] 馒头 API 行")
    mteam_rows = [
        {
            "id": "8001", "name": "MT 2026 2160p BluRay",
            "size": str(10 * 1024 ** 3), "createdDate": "2026-10-01 12:00:00",
            "status": {"discount": "FREE", "seeders": "30", "leechers": "4",
                       "discountEndTime": "2099-01-01 00:00:00"},
        },
        {"id": "8002", "name": "50% off", "status": {"discount": "PERCENT_50"}},
        {"id": "8003", "name": "2X", "status": {"discount": "2X"}},
    ]
    ms = R.parse_mteam_rows(mteam_rows, site_name="馒头", domain="m-team.io", site_url="https://m-team.io")
    ok(len(ms) == 3, f"三条都解析（实际 {len(ms)}）")
    ok(ms[0].is_free and ms[0].seeders == 30 and ms[0].leechers == 4, "status 嵌套字段取到")
    ok(ms[0].free_until == "2099-01-01 00:00:00" and ms[0].free_remaining_sec > 0, "限时免费到期")
    ok(ms[0].hit_and_run is False, "馒头行内无 H&R 事实 → False（不推断）")
    ok(ms[1].downloadvolumefactor == 0.5 and not ms[1].is_free, "PERCENT_50 → 0.5")
    ok(ms[2].uploadvolumefactor == 2.0 and ms[2].downloadvolumefactor == 1.0, "2X → 上传翻倍、下载照常")
    ok(ms[0].age_weeks > 0, "createdDate → age_weeks")

    print("[J] SiteCandidateTorrent 编解码往返（缓存层靠它落 FileCache）")
    c = R.SiteCandidateTorrent(hash="h", title="t", size=1024 ** 3, site_cookie="c")
    d = c.to_dict()
    ok(d["size_gb"] == 1.0, "size_gb 在 __post_init__ 补齐")
    back = R.SiteCandidateTorrent.from_dict(d)
    ok(back == c, "to_dict → from_dict 往返一致")
    ok(R.SiteCandidateTorrent.from_dict("不是字典") is None, "非法输入返回 None 而不是抛")
    ok(R.SiteCandidateTorrent.from_dict({**d, "不认识的字段": 1}) is not None, "多余字段容错")

    print("[K] free_time_ok：未知放行 / 够 / 不够")
    ok(R.free_time_ok(R.SiteCandidateTorrent(hash="", title="", size=0))[0] is True,
       "剩余时间未知（-1）→ 放行（不误杀非限时站）")
    big = R.SiteCandidateTorrent(hash="", title="", size=100 * 1024 ** 3, free_remaining_sec=60.0)
    passed, need, remain = R.free_time_ok(big)
    ok(passed is False and need > remain, f"100GB 只剩 60s → 拦下（需要 {need:.0f}s）")
    ok(R.free_time_ok(R.SiteCandidateTorrent(hash="", title="", size=1024 ** 3, free_remaining_sec=86400.0))[0] is True,
       "1GB 还剩 1 天 → 放行")

    print("[L] 时间换算与非法输入")
    ok(R.promo_remaining_sec("2099-01-01 00:00:00") > 0, "未来时间 → 正秒数")
    ok(R.promo_remaining_sec("2020-01-01 00:00:00") < 0, "过去时间 → 负秒数")
    ok(R.promo_remaining_sec("乱码") == -1.0, "解析失败 → -1（未知，不是 0）")
    ok(R.pubdate_to_ts("2026-10-01 12:00:00") > 0, "本地时间按 UTC+8 换算")
    ok(R.pubdate_to_ts(None) == 0.0 and R.pubdate_to_ts("乱码") == 0.0, "无效 → 0.0")
    ok(R.ts_to_age_weeks(0) == 0.0 and R.ts_to_age_weeks(time.time() + 86400) == 0.0, "未来时间归 0")
    ok(R._np_size_to_bytes("1,024", "MB") == 1024 * 1024 ** 2, "带千分位也能算")
    ok(R._np_size_to_bytes("x", "GB") == 0.0, "非法数字 → 0（不抛）")
    ok(R.parse_np_rows("", "d", "https://d", None, None) == [], "空页面 → 空列表")
    ok(R.parse_np_rows("<html>无种子的页面</html>", "d", "https://d", None, None) == [], "无种子行 → 空列表")

    print(f"\n✅✅ 全部通过（{CHECKS} 项断言）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as err:
        print(f"\n{err}")
        sys.exit(1)
