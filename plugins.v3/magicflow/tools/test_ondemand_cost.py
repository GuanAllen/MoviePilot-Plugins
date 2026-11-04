#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 点播「计费体积」选源（★ 19.11.14）离线回归 —— 真跑 tags.py + features/ondemand.py。

背景（Master 2026-11-02）：「促销系数化与计费体积」这条，刷流侧不适用，**点播侧适用**。
改前：候选行里其实早就有 `downloadvolumefactor` / `counted_gb`（三处采集都算过），
但选源与排序只看 `is_freeleech(dv)` 这个**布尔** —— 于是 50% / 30% 与全额完全等价：
20GB 五折（实扣 10GB）会输给 12GB 全额，「打折」在决策里等于不存在。

另修一处真 bug：`media_row_from_ti` 的 `_f()` 是 `float(v or 0.0)`，把 `None`（促销未知）
吃成 `0.0`，而 `dv=0` 的语义是**免费** → 「不知道」被当成「白送」，计费体积 0、选源排第一。
口径与 `tagspec.is_freeleech` 一致：宁可把免费当收费记账，也不把收费当免费白嫖。

断言：
  [1] `promo_factor`：None / 空串 / 非数字 → 1.0（**不是 0**）；'0'/0 → 0.0；0.5 → 0.5；
  [2] `promo_label`：免费 / 免费 2X / 2X 50% / 30% / 70% / 普通 / 1.5X；
  [3] `media_row_from_ti`：dv=None → free=False 且 counted_gb=体积（不再当免费）；dv=0 → 0；
  [4] `_od_cost`：有 counted_gb 用它；缺 → size×dv；dv 缺失 → 按全额（不按免费）；
  [5] `_ondemand_pick`：**单价低者胜** —— 20GB 五折胜 12GB 全额（系数 0.5 < 1.0）；
      免费永远胜任何折扣；同价按做种数、再按体积；**同价时小文件不许压过大文件**
      （按「实扣体积」排会有这个反效果：500MB 全额排在 60GB 全额前面）；
  [6] `_ondemand_rank`：强相关在前，同相关内按单价升序；
  [7] 源码锚点：三处排序都用 `_od_price`，不再出现 `is_freeleech(...)` 当排序键；
      `_od_cost`（实扣体积）只做展示/记账，不进排序。

用法：``python3 tools/test_ondemand_cost.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_od_cost_test"

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
    _load(PKG + ".fingerprint", "fingerprint.py")
    _load(PKG + ".persistence", "persistence.py")
    _load(PKG + ".sites.formula_fetch", "sites/formula_fetch.py")
    ondemand = _load(PKG + ".features.ondemand", "features/ondemand.py")
    return tags, ondemand


class _Fake(types.SimpleNamespace):
    """`_ondemand_pick` / `_ondemand_rank` 只读 rows + 纯函数，不需要真宿主。"""


def _row(size_gb: float, dv: float = 1.0, uvf: float = 1.0, seeders: int = 10,
         title: str = "沙丘 Dune 2021 2160p") -> dict:
    return {
        "title": title,
        "cn_title": "沙丘",
        "size": size_gb * 1e9,
        "downloadvolumefactor": dv,
        "uploadvolumefactor": uvf,
        "counted_gb": round(size_gb * dv, 2),
        "free": dv <= 0.0,
        "seeders": seeders,
        "enclosure": f"https://x/{size_gb}-{dv}-{seeders}.torrent",
        "site": 8,
        "site_name": "测试站",
    }


def main() -> int:
    tags, ondemand = _load_ondemand()

    print("[1] promo_factor：未知一律按全额，绝不按免费")
    pf = tags.promo_factor
    ok(pf(None) == 1.0, "None → 1.0（促销未知 ≠ 免费）")
    ok(pf("") == 1.0, "空串 → 1.0")
    ok(pf("abc") == 1.0, "非数字 → 1.0")
    ok(pf(0) == 0.0 and pf("0") == 0.0, "0 / '0' → 0.0（真免费）")
    ok(pf(0.5) == 0.5 and pf("0.3") == 0.3, "折扣系数原样")
    ok(pf(None, 2.0) == 2.0, "可指定默认值")

    print("[2] promo_label：人话促销（候选可见面）")
    pl = tags.promo_label
    ok(pl(0.0, 1.0) == "免费", "(0,1) → 免费")
    ok(pl(0.0, 2.0) == "免费 2X", "(0,2) → 免费 2X")
    ok(pl(0.5, 2.0) == "2X 50%", "(0.5,2) → 2X 50%")
    ok(pl(0.3, 1.0) == "30%", "(0.3,1) → 30%")
    ok(pl(0.7, 1.0) == "70%", "(0.7,1) → 70%")
    ok(pl(1.0, 1.0) == "普通", "(1,1) → 普通")
    ok(pl(1.0, 1.5) == "1.5X", "(1,1.5) → 1.5X（仅上传加成）")

    print("[3] media_row_from_ti：dv 未知不再被算成免费")
    r = tags.media_row_from_ti({"enclosure": "https://x/a.torrent", "size": 10 * 1e9,
                                "title": "Dune 2021", "seeders": 5})
    ok(r["downloadvolumefactor"] == 1.0, "缺 dv → 1.0（改前会被 `or 0.0` 变成 0.0）")
    ok(r["free"] is False, "缺 dv → 不标免费")
    ok(abs(r["counted_gb"] - 10.0) < 1e-6, "缺 dv → 计费体积 = 体积（10GB）")
    ok(r["promo"] == "普通", "缺 dv → promo 普通")
    r2 = tags.media_row_from_ti({"enclosure": "https://x/b.torrent", "size": 10 * 1e9,
                                 "downloadvolumefactor": 0, "uploadvolumefactor": 2})
    ok(r2["free"] is True and r2["counted_gb"] == 0.0, "dv=0 → 免费 / 计费 0")
    ok(r2["promo"] == "免费 2X", "dv=0 + uvf=2 → 免费 2X")
    r3 = tags.media_row_from_ti({"enclosure": "https://x/c.torrent", "size": 20 * 1e9,
                                 "downloadvolumefactor": 0.5})
    ok(abs(r3["counted_gb"] - 10.0) < 1e-6, "五折 20GB → 计费 10GB")
    ok(r3["promo"] == "50%", "五折 → promo 50%")

    print("[4] _od_price / _od_cost：单价系数排序、实扣体积展示")
    cost = ondemand._od_cost
    ok(cost(_row(20, 0.5)) == 10.0, "20GB 五折 → 10")
    ok(cost(_row(12, 1.0)) == 12.0, "12GB 全额 → 12")
    ok(cost(_row(20, 0.0)) == 0.0, "免费 → 0")
    ok(cost({"size": 8 * 1e9}) == 8.0, "缺 counted_gb / dv → 按全额（不按免费）")
    ok(cost({"size": 8 * 1e9, "downloadvolumefactor": None}) == 8.0, "dv=None → 按全额")
    ok(cost({"counted_gb": None, "size": 8 * 1e9, "downloadvolumefactor": 0.25}) == 2.0,
       "counted_gb=None 但 dv=0.25 → 8×0.25=2")
    ok(cost({"size": 100}) > 0.0,
       "小体积按现算取精度：100B 全额 > 0（`counted_gb` 只留 2 位 GB 会被舍成 0 撞免费档）")

    price = ondemand._od_price
    ok(price(_row(20, 0.5)) == 0.5 and price(_row(2, 0.0)) == 0.0, "单价 = 下载系数本身")
    ok(price({"downloadvolumefactor": None}) == 1.0, "系数未知 → 按全额 1.0（不按免费 0）")
    ok(price(_row(9, 0.3)) < price(_row(9, 0.5)) < price(_row(9, 1.0)), "三折 < 五折 < 全额")

    print("[5] _ondemand_pick：单价低者胜（折扣不再被抹平）")
    f = _Fake()
    pick = ondemand.OnDemandMixin._ondemand_pick
    rows = [_row(12, 1.0, seeders=99), _row(20, 0.5, seeders=1)]
    got = pick(f, rows)
    ok(got is not None and abs(got["size"] / 1e9 - 20) < 1e-6,
       "20GB 五折（系数 0.5）胜 12GB 全额（1.0）—— 改前按布尔两者同级，会选做种多的 12GB")
    rows = [_row(20, 0.5), _row(30, 0.3)]
    got = pick(f, rows)
    ok(got is not None and abs(got["size"] / 1e9 - 30) < 1e-6, "30GB 三折（0.3）胜 20GB 五折（0.5）")
    rows = [_row(50, 0.5), _row(2, 0.0)]
    got = pick(f, rows)
    ok(got is not None and abs(got["size"] / 1e9 - 2) < 1e-6, "免费(0) 永远胜任何折扣")
    rows = [_row(0.5, 1.0, seeders=5), _row(60, 1.0, seeders=5)]
    got = pick(f, rows)
    ok(got is not None and abs(got["size"] / 1e9 - 60) < 1e-6,
       "同价时大文件胜（500MB 全额不许因「实扣更少」压过 60GB 全额 —— 那会毁画质）")
    rows = [_row(5, 0.0, seeders=3), _row(9, 0.0, seeders=40)]
    got = pick(f, rows)
    ok(got is not None and abs(got["size"] / 1e9 - 9) < 1e-6, "同成本 → 做种多的胜")
    rows = [_row(5, 0.0, seeders=3), _row(9, 0.0, seeders=3)]
    got = pick(f, rows)
    ok(got is not None and abs(got["size"] / 1e9 - 9) < 1e-6, "同成本同做种 → 体积大的胜")
    ok(pick(f, []) is None, "空候选 → None")
    got = pick(f, [_row(12, 1.0)], names=[])
    ok(got is None, "names=[]（认不出片名）→ 绝不自动选源（既有铁律不变）")
    got = pick(f, [_row(12, 1.0, title="完全无关的片子 XYZ", seeders=1),
                   _row(20, 1.0, title="沙丘 Dune 2021 2160p", seeders=1)], names=["沙丘"])
    ok(got is not None and abs(got["size"] / 1e9 - 20) < 1e-6,
       "相关性优先：只在与片名强相关的行里比成本")

    print("[6] _ondemand_rank：强相关在前，同相关内按单价")
    rank = ondemand.OnDemandMixin._ondemand_rank
    rows = [_row(3, 1.0, title="完全无关的片子 XYZ"), _row(12, 1.0), _row(20, 0.5)]
    out = rank(f, rows, ["沙丘"])
    ok(abs(out[0]["size"] / 1e9 - 20) < 1e-6,
       "同为强相关 → 20GB 五折（0.5）在 12GB 全额（1.0）前")
    ok(out[-1]["rel"] == 0, "不沾边的行沉底并标 rel=0（既有行为不变）")

    print("[7] 源码锚点：排序键统一走 _od_price，实扣体积只做展示")
    src = (ROOT / "features" / "ondemand.py").read_text(encoding="utf-8")
    ok(src.count("_od_price(r)") >= 3, "三处排序键都换成 _od_price（单价系数）")
    ok("_od_cost(r)," not in src and "-_od_cost(r)" not in src,
       "实扣体积没被当排序键（会让小文件压过大文件）")
    ok('0 if is_freeleech(r.get("downloadvolumefactor")) else 1,' not in src,
       "旧的「免费=0/收费=1」排序键已清空")
    ok("promo_factor" in src and "promo_label" in src, "计费口径从 tags 引入，不在两处各写一份")

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
