#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 直连加种 `POST /agent/ondemand/add_direct`（★ 17.2.0）离线回归 —— 真跑 features/ondemand.py。

背景（Master 2026-10-14）：「点播那是不是缺一个直接加种的入口」—— 点播原来只有
「search 拿候选 → pick 命中候选」一条路（`/agent/ondemand/add`），**拿到一个种子链接却搜不到时无路可走**。
本端点补这条：只认链接本身（`details.php?id=N` / `download.php?id=N` / `.torrent` 直链），
用**指定站点**的 cookie 取种，落种复用点播通道（标签 / 伪任务 / 账本 / 静默闸全不动）。

账号口径（诚实记账，绝不假装免费）：
  · 促销 `dv` 来自详情页抗取（`fetch_torrent_promotion`）；**拿不到 → dv=1.0 按全额计**；
  · `H&R` **不自造逐种标记**：详情页解析不出 ≠ 欠 H&R，判定交回 H&R 模块（站点规则账本 `_site_hr_flag`）。

断言：
  [1] `_od_promo_dv`：free/2xfree→0.0；none/twoup/unknown→1.0；partial 从 `N%` 反解、解不出按 1.0；
  [2] `_direct_download_url`：详情页→`download.php?id=N`；已是下载链/.torrent → 原样；
  [3] `_direct_torrent_meta`：真 bencode 造的种子 → 标题/体积（单文件 + 多文件）；
  [4] 缺 url → 如实报错；
  [5] `site_ids` 不唯一 → 报「唯一」（直连不猜站点）；
  [6] 站点不存在 → 报错；
  [7] 干跑：出 plan（counted_gb = size/1e9×dv）、**不落种**；促销拿不到 → dv=1.0 / free=False；
  [8] 真加：free 促销 → dv=0.0 / counted_gb=0.0；**.torrent 只取一次**（content 透传给落种）；
  [9] 取种失败 → 如实报「取 .torrent 失败」，不落种；
  [10] 登记：清单含 `/agent/ondemand/add_direct`（POST/写/handler/returns）+ CORE_TOOLS 有
       `magicflow_ondemand_add_direct` + 领域标签 download + 描述带写标记与返回段。

用法：``python3 tools/test_agent_ondemand_add_direct.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import logging
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_od_direct_test"

FAILS = []
N = 0


def ok(cond, label):
    global N
    N += 1
    if not cond:
        FAILS.append(label)
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


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


def _stub_app():
    for name, attrs in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {}),
                               "MediaType": type("MediaType", (), {"MUSIC": "music"})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
        # claim.py 硬依赖它（`_ondemand_add_direct` 惰性 import claim 抠种子 id）
        ("app.sdk.logging", {"logger": logging.getLogger("mf-test")}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attrs.items():
            setattr(m, k, v)


def _load_ondemand():
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    _pkg(PKG + ".sites", ROOT / "sites")
    tags = _load(PKG + ".tags", "tags.py")
    for modname, attrs in (
        ("recommend", {"recognize": lambda *a, **k: None}),
        ("sitestore", {"slot_callbacks": lambda *a, **k: (lambda *x, **y: {}, lambda *x, **y: None)}),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[PKG + "." + modname] = m
    fp = _load(PKG + ".fingerprint", "fingerprint.py")
    _load(PKG + ".persistence", "persistence.py")
    _load(PKG + ".sites.formula_fetch", "sites/formula_fetch.py")
    ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")
    return tags, fp, ondemand


def _torrent_bytes(name: str = "Some.Movie.2024.2160p.WEB-DL", files=None) -> bytes:
    """造一颗真 .torrent（用仓内真 bencode 编码）。"""
    import importlib
    fp = importlib.import_module(PKG + ".fingerprint")
    files = files if files is not None else [(b"a.mkv", 1_000_000_000), (b"b.srt", 24_000)]
    info = {b"name": name.encode(), b"piece length": 262144, b"pieces": b"\x00" * 20}
    if len(files) == 1:
        info[b"length"] = files[0][1]
    else:
        info[b"files"] = [{b"length": n, b"path": [p]} for p, n in files]
    return fp.bencode({b"info": info, b"announce": b"https://cspt.top/announce"})


def _site(sid: int = 8):
    return types.SimpleNamespace(id=sid, name="财神", domain="cspt.top", url="https://cspt.top",
                                 cookie="c=1", ua="UA", proxy=False)


def _fake(ondemand, *, sites=(8,), site=None, content=b"x", promo=("none", "")):
    class Fake(ondemand.OnDemandMixin):
        def __init__(self):
            self._sites = list(sites)
            self._site = _site() if site is None else site
            self.content = content
            self.fetched = 0
            self.download_calls = []

        def _log(self, *a, **k):
            pass

        def _get_task_config(self, tid):
            return types.SimpleNamespace(save_path="/srv/dl")

        def _ondemand_sites(self, task=None, site_ids=""):
            ids = [int(x) for x in str(site_ids or "").replace("，", ",").split(",") if str(x).strip()]
            return ids or list(self._sites)

        def _get_site(self, sid):
            return self._site if (self._site is not None and int(sid) == int(self._site.id)) else None

        def _crossseed_torrent_bytes(self, row):
            self.fetched += 1
            return self.content

        def _ondemand_default_save_path(self):
            return "/default/dl"

        def _ondemand_download(self, row, task=None, title="", year="", content=None):
            self.download_calls.append({"row": dict(row), "title": title,
                                        "content": content, "task": task})
            return {"ok": True, "hash": "a" * 40, "save_path": row.get("_save") or "/srv/dl"}

    f = Fake()
    f._promo = promo
    ondemand.fetch_torrent_promotion = lambda site, page_url: {"promotion": promo[0], "raw": promo[1]}
    return f


def main() -> int:
    tags, fp, ondemand = _load_ondemand()

    print("[1] _od_promo_dv：促销 → 下载计费系数（拿不到按全额）")
    dv = ondemand._od_promo_dv
    ok(dv("free") == 0.0, "free → 0.0")
    ok(dv("2xfree") == 0.0, "2xfree → 0.0")
    ok(dv("none") == 1.0, "none → 1.0")
    ok(dv("twoup") == 1.0, "twoup（仅 2X 上传）→ 1.0")
    ok(dv("unknown") == 1.0, "unknown → 1.0（宁保守不白嫖）")
    ok(dv("partial", "50%免费") == 0.5, "partial + 50% → 0.5")
    ok(dv("partial", "") == 1.0, "partial 解不出 → 1.0")

    print("[2] _direct_download_url：链接归一（只换端点，不猜站点）")
    du = ondemand.OnDemandMixin._direct_download_url
    ok(du("https://cspt.top/details.php?id=215642&hit=1", "https://cspt.top", "215642")
       == "https://cspt.top/download.php?id=215642", "详情页 → download.php?id=N")
    ok(du("https://cspt.top/download.php?id=215642", "https://cspt.top", "215642")
       == "https://cspt.top/download.php?id=215642", "已是下载链 → 原样")
    ok(du("https://cspt.top/xx.torrent", "https://cspt.top", "") == "https://cspt.top/xx.torrent",
       ".torrent 直链 → 原样")
    ok(du("cspt.top/download.php?id=7", "https://cspt.top", "7") == "https://cspt.top/download.php?id=7",
       "缺协议 → 补 https")

    print("[3] _direct_torrent_meta：从 .torrent 读标题/体积（真值源 = fingerprint）")
    meta = ondemand.OnDemandMixin._direct_torrent_meta(
        _torrent_bytes("Movie.2024", [(b"a.mkv", 1000), (b"b.srt", 24)]))
    ok(meta["title"] == "Movie.2024", "多文件 → 根目录名当标题")
    ok(meta["size"] == 1024, "多文件 → 总字节 = 1024")
    meta1 = ondemand.OnDemandMixin._direct_torrent_meta(_torrent_bytes("One.2024", [(b"a.mkv", 500)]))
    ok(meta1["title"] == "One.2024" and meta1["size"] == 500, "单文件 → 标题/体积")

    print("[4] 缺 url → 如实报错")
    f = _fake(ondemand)
    r = f._ondemand_add_direct(url="", site_ids="8")
    ok(r.get("ok") is False and "url" in str(r.get("message")), "缺 url → ok False + 提到 url")

    print("[5] site_ids 不唯一 → 报「唯一」（直连取种要用该站 cookie，不猜站点）")
    r = f._ondemand_add_direct(url="https://cspt.top/details.php?id=1", site_ids="8,9")
    ok(r.get("ok") is False and "唯一" in str(r.get("message")), "多站点 → ok False + 「唯一」")

    print("[6] 站点不存在 → 报错")
    f2 = _fake(ondemand, site=_site(7))
    r = f2._ondemand_add_direct(url="https://cspt.top/details.php?id=1", site_ids="8")
    ok(r.get("ok") is False and "不存在" in str(r.get("message")), "站点不在 MP 登记表 → ok False")

    print("[7] 干跑：出 plan + 不落种；促销拿不到 → dv=1.0 / free=False")
    f3 = _fake(ondemand, content=_torrent_bytes("Big.2024", [(b"a.mkv", 100_000_000_000), (b"b.srt", 0)]),
               promo=("unknown", ""))
    r = f3._ondemand_add_direct(url="https://cspt.top/details.php?id=215642", site_ids="8",
                                task_id="t1", apply=False)
    ok(r.get("ok") is True and r.get("applied") is False and r.get("dry_run") is True, "干跑 → applied=False")
    plan = r.get("plan") or {}
    ok(plan.get("counted_gb") == 100.0, f"counted_gb = 100.0（实际 {plan.get('counted_gb')}）")
    ok(plan.get("downloadvolumefactor") == 1.0 and plan.get("free") is False, "拿不到促销 → 按全额计")
    ok(plan.get("torrent_id") == "215642" and plan.get("url") == "https://cspt.top/download.php?id=215642",
       "plan 带 torrent_id + 归一后的下载链")
    ok(plan.get("save_path") == "/srv/dl", "task_id 决定保存目录")
    ok(f3.download_calls == [], "干跑 → 一次都没落种")
    ok(f3.fetched == 1, "干跑也取一次 .torrent 读元数据")

    print("[8] 真加：free 促销 → dv=0；.torrent 只取一次（content 透传）")
    f4 = _fake(ondemand, content=_torrent_bytes("Free.2024", [(b"a.mkv", 50_000)]), promo=("free", "免费"))
    r = f4._ondemand_add_direct(url="https://cspt.top/download.php?id=99", site_ids="8",
                                task_id="t1", apply=True)
    ok(r.get("ok") is True and r.get("applied") is True and r.get("hash") == "a" * 40, "真加 → 回 hash")
    ok((r.get("plan") or {}).get("counted_gb") == 0.0 and (r.get("plan") or {}).get("free") is True,
       "free 促销 → counted_gb=0 / free=True")
    ok(len(f4.download_calls) == 1, "落种被调用 1 次")
    ok(f4.fetched == 1, ".torrent 只取一次（落种复用 content）")
    if f4.download_calls:
        _c = f4.download_calls[0]
        ok(_c["content"] is not None and _c["title"] == "Free.2024", "content/title 透传给落种")
        ok("hit_and_run" not in _c["row"], "H&R 解析不出 → 不自造逐种标记（row 不带 hit_and_run）")

    print("[9] 取种失败 → 如实报错，不落种")
    f5 = _fake(ondemand, content=b"")
    r = f5._ondemand_add_direct(url="https://cspt.top/details.php?id=5", site_ids="8")
    ok(r.get("ok") is False and "取 .torrent 失败" in str(r.get("message")), "取种失败 → ok False")
    ok(f5.download_calls == [], "取种失败 → 不落种")

    print("[10] 登记：清单 + CORE_TOOLS + 领域标签 + 描述标记/返回段")
    sys.path.insert(0, str(ROOT / "tools"))
    import check_mcptools_desc as guard  # noqa: E402
    mc = guard._load_mcptools()
    index = mc._spec_index()
    ent = index.get("/agent/ondemand/add_direct")
    ok(ent is not None, "清单含 /agent/ondemand/add_direct")
    if ent:
        ok(ent.get("method") == "POST" and ent.get("write") is True, "POST + 写")
        ok(ent.get("handler") == "agent_ondemand_add_direct", "handler = agent_ondemand_add_direct")
        ok(ent.get("returns") == "OnDemandAddDirect", "returns = OnDemandAddDirect")
    ok(("/agent/ondemand/add_direct", "magicflow_ondemand_add_direct") in mc.CORE_TOOLS,
       "CORE_TOOLS 有 magicflow_ondemand_add_direct")
    tool = next((t for t in mc.build_agent_tools("core") if t.name == "magicflow_ondemand_add_direct"), None)
    ok(tool is not None, "core 工具集里有它")
    if tool is not None:
        d = str(getattr(tool, "description", "") or "")
        ok(d.startswith("[写"), "描述带写标记")
        ok("｜返回 OnDemandAddDirect" in d, "描述含「｜返回 OnDemandAddDirect」")
        ok("download" in list(getattr(tool, "tags", []) or []), "领域标签 = download（写动作按域门禁）")
        schema = getattr(tool, "args_schema", None)
        ok(schema is not None and "url" in (getattr(schema, "fields", {}) or {}), "args_schema 有 url")
    agentapi = sys.modules.get(guard.PKG + ".features.agentapi")
    ok(agentapi is not None and hasattr(agentapi.AgentApiMixin, "agent_ondemand_add_direct"),
       "handler 方法存在")
    if agentapi is not None:
        h = getattr(agentapi.AgentApiMixin, "agent_ondemand_add_direct", None)
        ok(h is not None and not inspect.iscoroutinefunction(h), "直连加种是同步 handler（同 /add）")

    print()
    if FAILS:
        print(f"❌ FAIL：{len(FAILS)}/{N} 断言失败")
        for x in FAILS:
            print("   -", x)
        return 1
    print(f"✅ PASS：{N}/{N} 断言全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
