#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 推送审计（★ 19.11.15）离线回归 —— 真跑 downloader_ops.py。

背景（Master 2026-11-02 选做 ⑤）：以前「加种」失败只在日志里留一行，事后没人能回答
「这条到底推没推、推给谁、报了什么」。审计就补这一件事：**每次加种一条记录，成功也记、
失败更记**，落插件数据槽的环形表，供 `/pushes` 查。

为什么不逐处埋点：本仓「加种」只有一个入口 `DownloaderAdapter.add_torrent` ——
点播 / 辅种 / 刷流 / 套牌复用全部落到它。逐处埋必漏，包一层必不漏。

铁律：**审计绝不拖累加种**。钩子没注册、钩子抛异常，加种都必须照常返回。

断言：
  [1] 无钩子：`add_torrent` 行为不变（返回原 result，不报错）；
  [2] 成功：钩子收到 ok=True + hash/tag/站点/目录/内容类型；
  [3] 失败（返回 (None, 报错)）：ok=False 且带**原始报错**；
  [4] 抛异常：先记一条 ok=False，再把异常继续抛给调用方（不吞业务异常）；
  [5] 钩子自己抛异常：加种仍返回正确结果（审计写不进去不能影响加种）；
  [6] 内容类型：bytes→torrent（带字节数）/ magnet / url；
  [7] 源码锚点：core 注册钩子、`_push_audit` 落 `push_audit` 且按 `_PUSH_AUDIT_KEEP` 截断、
      失败写 warning；`/pushes` 路由与 handler 都在。

用法：``python3 tools/test_push_audit.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_push_audit_test"

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


def _stub():
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    for name, attrs in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
    ):
        m = sys.modules.get(name) or types.ModuleType(name)
        sys.modules[name] = m
        for k, v in attrs.items():
            setattr(m, k, v)
    for modname, attrs in (
        ("bonus", ("TorrentBonusInfo",)),
        ("fingerprint", ("Entry", "entries_fingerprint", "info_hash", "load_torrent_entries",
                         "total_size", "inner_fingerprint", "fingerprint")),
        ("fetcher", ("SiteCandidateTorrent",)),
        ("qbsync", ("QB_SYNC_INCREMENTAL", "get_qb_sync_store")),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        m.get_qb_sync_store = lambda: None  # noqa: E731
        sys.modules[PKG + "." + modname] = m
    _load(PKG + ".common", "common.py")
    _load(PKG + ".tags", "tags.py")
    return _load(PKG + ".downloader_ops", "downloader_ops.py")


def _adapter(dops, impl):
    """绕过构造器造一个适配器：只替换 `_add_torrent_impl`，测的就是外面那层审计。"""
    a = object.__new__(dops.DownloaderAdapter)
    a._add_torrent_impl = impl
    return a


def main() -> int:
    dops = _stub()
    seen = []

    def hook(payload):
        seen.append(payload)

    print("[1] 无钩子：加种行为一字不变")
    dops.set_add_audit_hook(None)
    a = _adapter(dops, lambda *x, **k: ("b" * 40, None))
    got = a.add_torrent(b"x", download_dir="/dl", tag="魔流-甲-魔力")
    ok(got == ("b" * 40, None), "没有钩子也照常返回 result")
    ok(seen == [], "没有钩子就不记（不自己造审计）")

    print("[2] 成功：ok=True + 归因线索齐全")
    dops.set_add_audit_hook(hook)
    seen.clear()
    a.add_torrent(b"x" * 1234, download_dir="/vol6/刷流", tag="魔流-Depth Studio-魔力",
                  site_domain="dstudio.me", hit_and_run=True)
    ok(len(seen) == 1 and seen[0]["ok"] is True, "成功记一条 ok=True")
    p = seen[0]
    ok(p["hash"] == "b" * 40, "hash 原样回传")
    ok(p["tag"] == "魔流-Depth Studio-魔力" and p["site_domain"] == "dstudio.me", "标签/站点带上")
    ok(p["save_path"] == "/vol6/刷流", "保存目录带上")
    ok(p["hit_and_run"] is True, "H&R 标记带上")
    ok(p["content"] == "torrent" and p["bytes"] == 1234, "内容类型 torrent + 字节数")

    print("[2b] 内容类型：magnet / url")
    seen.clear()
    a.add_torrent("magnet:?xt=urn:btih:" + "c" * 40, download_dir="/dl", tag="t")
    a.add_torrent("https://x/a.torrent", download_dir="/dl", tag="t")
    ok([x["content"] for x in seen] == ["magnet", "url"], "magnet / url 分别识别")
    ok(all(x["bytes"] == 0 for x in seen), "非 torrent 内容字节数 0")

    print("[3] 失败：ok=False 且留原始报错")
    seen.clear()
    a = _adapter(dops, lambda *x, **k: (None, "qBittorrent 添加种子失败"))
    a.add_torrent(b"x", download_dir="/dl", tag="魔流-乙-刷流")
    ok(len(seen) == 1 and seen[0]["ok"] is False, "失败也记一条")
    ok(seen[0]["error"] == "qBittorrent 添加种子失败", "原始报错原文保留（不改写）")
    ok(seen[0]["hash"] == "", "失败没有 hash → 空串（不编一个）")

    print("[4] 抛异常：先记一条，再把异常抛回调用方")
    seen.clear()

    def _boom(*x, **k):
        raise RuntimeError("网络断了")

    a = _adapter(dops, _boom)
    raised = ""
    try:
        a.add_torrent(b"x", download_dir="/dl", tag="t")
    except RuntimeError as e:
        raised = str(e)
    ok(raised == "网络断了", "业务异常没有被吞（调用方照旧收到）")
    ok(len(seen) == 1 and seen[0]["ok"] is False and seen[0]["error"] == "网络断了", "异常也留痕")

    print("[5] 钩子自己炸了：加种必须照常成功")
    def _bad_hook(_p):
        raise ValueError("审计写不进去")

    dops.set_add_audit_hook(_bad_hook)
    a = _adapter(dops, lambda *x, **k: ("d" * 40, None))
    got = a.add_torrent(b"x", download_dir="/dl", tag="t")
    ok(got == ("d" * 40, None), "审计抛异常 → 加种结果不受影响（绝不拖累）")

    print("[6] 源码锚点：钩子注册 + 落盘 + 截断 + 路由")
    dops.set_add_audit_hook(None)
    src_core = (ROOT / "features" / "core.py").read_text(encoding="utf-8")
    src_api = (ROOT / "features" / "api.py").read_text(encoding="utf-8")
    ok("set_add_audit_hook(_push_audit_hook)" in src_core, "启动时注册审计钩子")
    ok('_PUSH_AUDIT_KEY = "push_audit"' in src_core, "落盘键 push_audit")
    ok("rows[:_PUSH_AUDIT_KEEP]" in src_core, "环形截断（不会无限长）")
    ok('"推送失败：' in src_core, "失败额外写一条 warning 日志（日志里就能看到）")
    ok('def _push_task_of_tag' in src_core and "brush_tag" in src_core,
       "标签 → 任务靠 brush_tag 反查（解不出就留空，不瞎猜）")
    ok('("/pushes", "pushes", "GET"' in src_api, "/pushes 只读路由已登记")
    ok("    def pushes(self, limit: int = 50" in src_core, "handler 在 core，签名与路由对得上")
    _i_gd = src_core.find("def _get_downloader(")
    ok("self._ensure_add_audit_hook()" in src_core[_i_gd:_i_gd + 900],
       "取下载器时幂等刷钩子（热重载丢了能自己补回来，不靠 init_plugin 重跑）")

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
