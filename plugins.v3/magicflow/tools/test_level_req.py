#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 等级表 / 升级要求（★ 19.11.18，④ 的第二半）离线回归 —— 真跑 level_req.py。

数据抄自 PT-depiler（pt-plugins/PT-depiler master）的站点 levelRequirements；
口径与它的差异见 level_req.py 文件头（认不出等级不倒推、缺输入列 unknown 不猜 0）。

断言分组：
  [1] 域名 → 表（含 www 剥离 / 没表不套默认 / cyanbug 显式默认表）
  [2] 等级名 → id（精确 / 包含 / (连长) 前缀 / 用户名不误判 / 满级）
  [3] API 数字等级 → 名字（馒头 levelId=10 → VIP；叶PT 1 → 小卒）
  [4] 距下一级差值（体积 / 做种积分 / 分享率 / 入站时长 / 缺输入进 unknown）
  [5] 边界（没表 → None；认不出等级 → None；已满级 → None）

用法：``python3 tools/test_level_req.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []
N = 0
GB = 1024 ** 3


def ok(cond, label):
    global N
    N += 1
    if not cond:
        FAILS.append(label)
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


def _load():
    spec = importlib.util.spec_from_file_location("mf_level_req_test", ROOT / "level_req.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mf_level_req_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    lr = _load()

    print("[1] 域名 → 等级表")
    carpt = lr.reqs_for_domain("carpt.net")
    ok(isinstance(carpt, list) and len(carpt) == 9, f"carpt 9 级（实际 {len(carpt) if carpt else None}）")
    ok(lr.reqs_for_domain("www.uhddolby.com") is not None, "www. 前缀剥掉也能命中")
    ok(lr.reqs_for_domain("unknown-pt.example.com") is None, "没表的站 → None（不套默认表）")
    ok(lr.reqs_for_domain("") is None and lr.reqs_for_domain(None) is None, "空域名 → None")
    ok(lr.reqs_for_domain("cyanbug.net") is lr.XIAOMLOVE_DEFAULT, "cyanbug 显式引用 xiaomlove 默认表")
    ok(len(lr.XIAOMLOVE_DEFAULT) == 17, f"默认表 17 级（实际 {len(lr.XIAOMLOVE_DEFAULT)}）")

    print("[2] 等级名 → id")
    ok(lr.guess_level_id("Power User", carpt) == 1, "Power User → carpt id 1")
    ok(lr.guess_level_id("power_user", carpt) == 1, "清洗后等价（power_user）")
    hd = lr.reqs_for_domain("uhddolby.com")
    ok(lr.guess_level_id("(连长)Elite User", hd) == 3, f"hddolby (连长)Elite User → 3（实际 {lr.guess_level_id('(连长)Elite User', hd)}）")
    ok(lr.guess_level_id("alanguan", carpt) is None, "用户名 → None（不误判）")
    ok(lr.guess_level_id("alanguan", carpt) != 1, "尤其不许当成 User")
    # VIP/管理组：PTD 口径给「组兜底 id」（100/200）而不是 None；关键是下游不给升级建议
    ok(lr.guess_level_id("贵宾(VIP)", carpt) == 100, f"VIP 组 → 组兜底 id 100（实际 {lr.guess_level_id('贵宾(VIP)', carpt)}）")
    ok(lr.next_level_unmet({"download": 10 * GB}, carpt, "贵宾(VIP)") is None, "VIP → 没有「下一级」（不给升级建议）")
    ok(lr.guess_level_id("", carpt) is None and lr.guess_level_id(None, carpt) is None, "空等级名 → None")

    print("[3] API 数字等级 → 名字")
    mt = lr.reqs_for_domain("m-team.cc")
    ok(lr.api_level_name(10, mt) == "VIP", f"馒头 levelId=10 → VIP（实际 {lr.api_level_name(10, mt)!r}）")
    ok(lr.api_level_name("10", mt) == "VIP", "字符串 10 同样认")
    ye = lr.reqs_for_domain("yemapt.org")
    ok(lr.api_level_name(1, ye) == "小卒", f"叶PT 1 → 小卒（实际 {lr.api_level_name(1, ye)!r}）")
    ok(lr.api_level_name(999, mt) is None, "表里没有的数字 → None（不当名字展示）")
    ok(lr.api_level_name(None, mt) is None and lr.api_level_name("", mt) is None, "空 → None")

    print("[4] 距下一级差值")
    # carpt User(id 0) → Power User(id 1)：200GB 下载 / 分享率 2.0 / 做种积分 40000 / P4W
    facts = {
        "download": 10 * GB, "upload": 30 * GB, "ratio": 2.5,
        "bonus": 5000.0, "seeding_bonus": 10000.0,
        "join_time": 1700000000.0,  # 2023-11 → P4W 早满足
    }
    r = lr.next_level_unmet(facts, carpt, "User")
    ok(r is not None and r["name"] == "Power User", f"User → Power User（实际 {r and r['name']!r}）")
    ok(abs(r["unmet"]["downloaded"] - 190 * GB) < 1, f"下载差 190GB（实际 {r['unmet'].get('downloaded')}）")
    ok(r["unmet"].get("seedingBonus") == 30000, f"做种积分差 30000（实际 {r['unmet'].get('seedingBonus')}）")
    ok("ratio" not in r["unmet"], "分享率 2.5 ≥ 2.0 → 不欠")
    ok("interval" not in r["unmet"] and "interval" not in r["unknown"], "入站 2023 → P4W 已满足")
    # 入站没满：把 join_time 调成现在
    import time
    r2 = lr.next_level_unmet({**facts, "join_time": time.time() - 86400.0}, carpt, "User")
    ok("interval" in r2["unmet"] and r2["unmet"]["interval"] > 20 * 86400,
       f"刚入站 → P4W 差 ~27 天（实际 {r2['unmet'].get('interval')}）")
    # 缺输入进 unknown，不猜 0
    r3 = lr.next_level_unmet({"download": 10 * GB, "ratio": 2.5}, carpt, "User")
    ok("seeding_bonus" not in r3 and "seedingBonus" in r3["unknown"],
       f"做种积分缺失 → unknown（实际 {r3['unknown']}）")
    ok("downloaded" not in r3["unmet"] or abs(r3["unmet"]["downloaded"] - 190 * GB) < 1,
       "有输入的项照算")
    # 分享率 ∞（下载 0）→ 任何分享率门槛都过
    r4 = lr.next_level_unmet({"download": 0, "upload": 5 * GB, "ratio_inf": True}, carpt, "User")
    ok("ratio" not in r4["unmet"] and "ratio" not in r4["unknown"], "ratio_inf → 分享率门槛直接过")
    # 分享率不够 → 记门槛值
    r5 = lr.next_level_unmet({**facts, "ratio": 0.5}, carpt, "User")
    ok(r5["unmet"].get("ratio") == 2.0, f"分享率 0.5 < 2.0 → 记门槛（实际 {r5['unmet'].get('ratio')}）")

    print("[5] 边界")
    ok(lr.next_level_unmet(facts, None, "User") is None, "没表 → None")
    ok(lr.next_level_unmet(facts, carpt, None) is None, "认不出当前等级 → None（不倒推）")
    ok(lr.next_level_unmet(facts, carpt, "Nexus Master") is None, "已满级 → None")
    ok(lr.next_level_unmet(facts, carpt, "alanguan") is None, "用户名当等级输入 → None")

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
