#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 组合优化器离线回归（★ 15.15.0）。

测 ``bonus.py`` 的两个纯函数（不依赖 MoviePilot / 数据库）：
  1) ``is_undeletable`` —— 「不可删」统一判定（单一真值源，清种与优化器共用）；
  2) ``optimize_pool``  —— 容量预算下的最优「保 / 删」组合（0/1 背包）。

断言：
  A. 不可删真值表：手动保护 / H&R / 完美种 / 保护期 / 低分享率；人多非完美 → 可删；
  B. 背包最优性：与暴力枚举（2^n）逐一对齐（1GB 粒度下应完全一致）；
  C. 约束：保留体积 ≤ 预算；keep_count + delete_count == 池计数；freed = 总体积 − 保留；
  D. 强制保留：受保护种恒在保留名单；预算 < 强制保留体积 → infeasible；
  E. 缺省预算：auto → 保留 ≥95% 时魔；效率前沿单调不减、末点 = 全保留；
  F. 空输入不崩。

用法：``python3 tools/test_optimizer.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = 0


def ok(cond, msg):
    global CHECKS
    CHECKS += 1
    if cond:
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        raise SystemExit(1)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


B = _load("mf_bonus_opt_test", "bonus.py")


def _mk(h, size=10.0, seeders=1, weeks=8.0, zero=False, hr=False, ratio=1.0):
    t = B.calc_torrent_bonus(hash=h, title=h, size_gb=size, seeders=seeders,
                             age_weeks=weeks, is_zero_bonus=zero)
    t.hit_and_run = hr
    t.ratio = ratio
    return t


# ---------------------------------------------------------------- A
def t_is_undeletable():
    print("A. is_undeletable 真值表")
    pol = B.MagicPolicy(perfect_max_seeders=3, perfect_min_weeks=4.0)
    ok(B.is_undeletable(_mk("a"), pol, {"a"}) is True, "手动保护 → 不可删")
    ok(B.is_undeletable(_mk("b", hr=True), pol) is True, "H&R → 不可删")
    ok(B.is_undeletable(_mk("c", seeders=2, weeks=10), pol) is True, "完美种（非零魔/人少/够老）→ 不可删")
    ok(B.is_undeletable(_mk("d", seeders=50, weeks=10), pol) is False, "人多非完美 → 可删")
    pol2 = B.MagicPolicy(protect_perfect=False, min_seed_time_hours=168.0)
    ok(B.is_undeletable(_mk("e", weeks=0.5), pol2) is True, "保护期内 → 不可删")
    pol3 = B.MagicPolicy(protect_perfect=False, min_ratio=2.0)
    ok(B.is_undeletable(_mk("f", ratio=0.5), pol3) is True, "低分享率 → 不可删")
    ok(B.is_undeletable(_mk("g", ratio=3.0), pol3) is False, "分享率达标 → 可删")


# ---------------------------------------------------------------- B/C
def t_knapsack_optimal():
    print("B/C. 背包最优性 + 约束")
    pol = B.MagicPolicy(protect_perfect=False)
    sizes = [(10, 1), (20, 1), (5, 1), (40, 1), (10, 8), (30, 8)]
    rows = [_mk("h%d" % i, size=s, seeders=sd) for i, (s, sd) in enumerate(sizes)]
    r = B.optimize_pool(rows, 50.0, pol, set())

    best = 0.0
    n = len(rows)
    for mask in range(1 << n):
        sz = sum(rows[i].size_gb for i in range(n) if mask >> i & 1)
        if sz <= 50.0 + 1e-9:
            best = max(best, sum(B._opt_value(rows[i]) for i in range(n) if mask >> i & 1))
    ok(abs(r["plan"]["kept_bonus_per_hour"] - best) < 1e-3,
       "DP 达到暴力最优 (%.6f vs %.6f)" % (r["plan"]["kept_bonus_per_hour"], best))
    ok(r["pool"]["count"] == 6, "池计数 = 6")
    ok(r["plan"]["kept_size_gb"] <= 50.0 + 1e-6, "保留体积 ≤ 预算 (%.2f)" % r["plan"]["kept_size_gb"])
    ok(r["plan"]["keep_count"] + r["plan"]["delete_count"] == 6, "keep+delete == 池")
    ok(abs(r["plan"]["freed_gb"] - (r["pool"]["size_gb"] - r["plan"]["kept_size_gb"])) < 0.05,
       "freed_gb = 总体积 − 保留")
    ok(isinstance(r.get("compare"), dict), "compare 块存在")


# ---------------------------------------------------------------- D
def t_mandatory():
    print("D. 强制保留 + infeasible")
    pol = B.MagicPolicy(protect_perfect=False)
    rows = [_mk("x%d" % i, size=10) for i in range(3)]
    r = B.optimize_pool(rows, 100.0, pol, {"x0"})
    ok(r["mandatory"]["count"] == 1, "强制保留 1 颗")
    ok("x0" in {k["hash"] for k in r["plan"]["keep"]}, "受保护种在保留名单")
    ok(r["plan"]["delete_count"] == 0, "预算充足 → 不删")
    r2 = B.optimize_pool(rows, 5.0, pol, {"x0"})
    ok(r2["infeasible"] is True, "预算 < 强制保留体积 → infeasible")


# ---------------------------------------------------------------- E
def t_auto_frontier():
    print("E. 缺省预算(auto) + 效率前沿")
    pol = B.MagicPolicy(protect_perfect=False)
    rows = [_mk("f%d" % i, size=s) for i, s in enumerate([1, 1, 1, 1, 100])]
    r = B.optimize_pool(rows, None, pol, set())
    ok(str(r.get("budget_source", "")).startswith("auto"), "缺省预算 → auto")
    ok(r["plan"]["kept_bonus_pct"] >= 95.0 - 1e-9, "auto 保留 ≥95%% 时魔 (%.2f%%)" % r["plan"]["kept_bonus_pct"])
    fr = r["frontier"]
    ok(len(fr) >= 2, "前沿 ≥2 点")
    ok(all(fr[i]["kept_bonus_per_hour"] <= fr[i + 1]["kept_bonus_per_hour"] + 1e-3
           for i in range(len(fr) - 1)), "前沿时魔单调不减")
    ok(abs(fr[-1]["kept_bonus_per_hour"] - r["pool"]["bonus_per_hour"]) < 1e-3, "前沿末点 = 全保留")


# ---------------------------------------------------------------- F
def t_empty():
    print("F. 空输入")
    r = B.optimize_pool([], 10.0, B.MagicPolicy(), set())
    ok(r["method"] == "empty" and r["plan"]["keep_count"] == 0, "空输入不崩")


if __name__ == "__main__":
    print("=" * 60)
    print("组合优化器离线回归（15.15.0）")
    print("=" * 60)
    t_is_undeletable()
    t_knapsack_optimal()
    t_mandatory()
    t_auto_frontier()
    t_empty()
    print("-" * 60)
    print("PASS  断言数 =", CHECKS)
