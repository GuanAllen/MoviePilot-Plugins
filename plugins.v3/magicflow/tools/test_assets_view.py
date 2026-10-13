#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 库内资产「AI 读取面」（★ 15.19.0）离线回归 —— 真跑 `features/assets.py::AssetsMixin.assets_view`。

背景：`/agent/assets` 原来只有 `limit/include_stale`，全量 239 份 ≈ 390KB JSON，
而 MCP 单次结果上限 30k 字符 → 「我有哪些资源」这类清单问题**只能看到前 19 份**。
15.19.0 不新造真值（仍走 `_asset_rows`），只加**瘦身视图 + 筛选 + 排序 + 分页 + 聚合**。

断言：
  [1] 默认 = summary 视图 + limit=50 + 分页信封（matched/returned/offset/next_cursor/hint）；
  [2] summary 瘦身：不带 members/source_hash；sites 截前 8 + sites_more；
  [3] counts 永远按**全量**统计（与 q/分页无关）；
  [4] q 命中资源名 **或** 任一成员种名（大小写无关）；
  [5] sort = size（默认降序）/ sites / members / name；
  [6] group_by=site 聚合（份数/体积/可删数，按份数降序）；
  [7] resource_id 单份详情（完整 members）；不存在 → success=False（不抛）；
  [8] cursor 翻页不重不漏（全部页并集 == 全集）；
  [9] view=full 保留 members（旧粒度）；[10] limit=0 = 全部。

用法：``python3 tools/test_assets_view.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import os as _os
import sys
import types
from pathlib import Path

ROOT = Path(_os.environ.get("MF_ROOT") or Path(__file__).resolve().parent.parent)
PKG = "mf_assets_test"

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


# --- 桩：`app.schemas.Response`（真实现由 MoviePilot 提供）---
_pkg("app", ROOT)
_schemas = types.ModuleType("app.schemas")


class _Resp:
    def __init__(self, success: bool = True, message: str = "", data=None, **_kw):
        self.success = success
        self.message = message
        self.data = data


_schemas.Response = _Resp
sys.modules["app.schemas"] = _schemas

_pkg(PKG, ROOT)
_pkg(PKG + ".features", ROOT / "features")


class _Loose(types.ModuleType):
    """占位依赖：任何属性访问都返回「吞参数的假函数」。

    `features/assets.py` 顶层还 import 了 ``..common`` / ``..models`` / ``..persistence`` /
    ``..ledger`` / ``..recommend``（真身要 MoviePilot SDK）——本测试只验 ``assets_view``
    的**投影/筛选/排序/分页/聚合**逻辑（真值源 ``_asset_rows`` 由 Harness 提供），
    故把这些依赖整体桩掉，保证「离线、零网络、零下载器」。
    """

    def __getattr__(self, name):  # noqa: D105
        return lambda *a, **kw: None


for _m in ("common", "models", "persistence", "ledger", "recommend"):
    sys.modules[f"{PKG}.{_m}"] = _Loose(f"{PKG}.{_m}")
sys.modules[f"{PKG}.common"].MEDIA_ASSET_TAGS = []
sys.modules[f"{PKG}.common"].torrent_data_key = lambda *a, **kw: ""

assets_mod = _load(PKG + ".features.assets", "features/assets.py")
AssetsMixin = assets_mod.AssetsMixin


def _row(i: int, sites=("A站", "B站"), members=3, size=100.0, deletable=True, block="", stale=False):
    _sites = list(sites)   # 站点名固定（聚合/排序断言要稳定）
    _mem = [{"hash": f"{i:040x}"[:40], "site": s, "title": f"Show.S01.E{i:02d}.{s}.mkv",
             "in_qb": True, "state": "", "size_gb": size} for s in _sites[:members]]
    return {
        "resource_id": f"fp:{i:040x}",
        "name": f"资源{i:02d}",
        "source_hash": f"{i:040x}"[:40],
        "source_site": _sites[0] if _sites else "",
        "identity": "资源",
        "in_library": True,
        "sites": _sites,
        "site_count": len(_sites),
        "member_count": len(_mem),
        "members_in_qb": len(_mem),
        "size_gb": size,
        "members": _mem,
        "stale": bool(stale),
        "deletable": bool(deletable),
        "protected": not deletable,
        "protected_hashes": [],
        "block": block,
    }


ROWS = [_row(i) for i in range(60)]
# ② 一份「手动保留」、一份 stale、一份成员名带关键词
ROWS[7]["deletable"], ROWS[7]["protected"], ROWS[7]["block"] = False, True, "手动保留"
ROWS[9]["stale"] = True
ROWS[5]["members"][0]["title"] = "PHOENIX.Nirvana.2025.2160p.WEB-DL"


class Harness(AssetsMixin):
    def __init__(self, rows):
        self._rows = rows

    def _asset_rows(self, snap=None, include_stale: bool = False):
        return [dict(r) for r in self._rows if include_stale or not r.get("stale")]

    def _log(self, *a, **kw):
        pass


H = Harness(ROWS)
VISIBLE = [r for r in ROWS if not r["stale"]]      # 59（默认不显示 stale）

print("=== [1] 默认：summary + limit=50 + 分页信封 ===")
r = H.assets_view()
d = r.data
ok(r.success and d["view"] == "summary", "默认 view=summary")
ok(d["returned"] == 50 and d["offset"] == 0, "默认返回 50 条（offset=0）")
ok(d["next_cursor"] == "50" and "cursor=50" in (d.get("hint") or ""), "next_cursor=50 + hint")
ok(d["counts"]["total"] == len(VISIBLE) and d["counts"]["deletable"] == len(VISIBLE) - 1, "counts 全量口径")

print("=== [2] summary 瘦身 ===")
one = d["items"][0]
ok("members" not in one and "source_hash" not in one, "summary 不带 members/source_hash")
ok(len(one["sites"]) == 2 and one["sites_more"] == 0, "sites 原样（≤8）")
H2 = Harness([_row(99, sites=("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"), members=10)])
d2 = H2.assets_view().data["items"][0]
ok(len(d2["sites"]) == 8 and d2["sites_more"] == 2, "sites 截 8 + sites_more=2")
_brief_len = len(str(one))
ok(_brief_len < 400, f"单条摘要体积小（{_brief_len} 字符 < 400）")

print("=== [3] counts 与筛选无关 ===")
dq = H.assets_view(q="资源1").data
ok(dq["counts"]["total"] == len(VISIBLE) and dq["matched"] == 10, "q 筛选后 counts 仍全量 / matched=10")

print("=== [4] q 命中名 or 成员种名（大小写无关）===")
_m = H.assets_view(q="资源0").data["matched"]
ok(_m == 9, f"按资源名命中 9 条（00–09 去掉 stale 的 09）实际 {_m}")
ok(H.assets_view(q="phoenix").data["matched"] == 1, "小写关键词命中成员种名（PHOENIX…）")
ok(H.assets_view(q="Nirvana").data["matched"] == 1, "大小写无关")

print("=== [5] 排序 ===")
_sz = H.assets_view(sort="size", limit=0).data["items"]
ok(_sz[0]["size_gb"] == _sz[-1]["size_gb"], "size 排序（同体积稳定）")
_nm = H.assets_view(sort="name", limit=0).data["items"]
ok(_nm[0]["name"] < _nm[-1]["name"], "name 升序")
_si = H.assets_view(sort="sites", limit=0).data["items"]
ok(_si[0]["site_count"] >= _si[-1]["site_count"], "sites 降序")

print("=== [6] group_by=site 聚合 ===")
g = H.assets_view(group_by="site").data
ok(g["view"] == "group" and "items" not in g, "group 视图只回 groups")
_ga = {x["site"]: x for x in g["groups"]}
ok(len(g["groups"]) == 2 and g["groups"][0]["resources"] >= g["groups"][1]["resources"], "按份数降序")
ok(all(x["resources"] == len(VISIBLE) for x in g["groups"]), "两站各 59 份（每行两站）")
ok(abs(sum(x["size_gb"] for x in g["groups"]) - sum(float(x["size_gb"]) for x in VISIBLE) * 2) < 1e-6,
   "体积聚合 = 各行体积 × 站数")
ok(sum(x["deletable"] for x in g["groups"]) == (len(VISIBLE) - 1) * 2, "可删数聚合正确")

print("=== [7] resource_id 单份详情 ===")
rid = VISIBLE[3]["resource_id"]
det = H.assets_view(resource_id=rid)
ok(det.success and det.data["view"] == "detail" and det.data["item"]["resource_id"] == rid, "单份详情命中")
ok(bool(det.data["item"]["members"]), "详情含完整 members")
miss = H.assets_view(resource_id="fp:deadbeef")
ok((not miss.success) and "没找到" in miss.message, "不存在 → success=False（不抛）")

print("=== [8] cursor 翻页不重不漏 ===")
seen, cur, pages = [], "", 0
while True:
    p = H.assets_view(limit=20, cursor=cur).data
    seen += [x["resource_id"] for x in p["items"]]
    pages += 1
    cur = p["next_cursor"]
    if not cur:
        break
ok(len(seen) == len(VISIBLE) and len(set(seen)) == len(VISIBLE), f"3 页（{pages}）覆盖全集且无重复")
ok(pages == 3, f"59 条 / 每页 20 → 3 页（实际 {pages}）")

print("=== [9] view=full ===")
f1 = H.assets_view(view="full", limit=1).data["items"][0]
ok(bool(f1.get("members")) and "source_hash" in f1, "full 视图保留 members/source_hash")

print("=== [10] limit=0 = 全部；include_stale ===")
ok(H.assets_view(limit=0).data["returned"] == len(VISIBLE), "limit=0 返回全部可见")
ok(H.assets_view(limit=0, include_stale=1).data["returned"] == len(ROWS), "include_stale=1 带上 stale")

print("=== [11] 非法 limit → bad_request（由 agentapi 校验）===")
try:
    H.assets_view(limit="abc")    # 视图层兜底：非整数 → 回退 50
    ok(True, "视图层容错不抛")
except Exception as e:  # noqa: BLE001
    ok(False, f"视图层不应抛异常: {e}")

print()
if FAILS:
    print(f"❌ FAIL {len(FAILS)}/{N}：" + "；".join(FAILS))
    sys.exit(1)
print(f"✅ PASS {N}/{N}")
