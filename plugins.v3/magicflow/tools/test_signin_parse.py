#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 签到页解析「假成功」离线回归（★ 19.2.3 加固，真跑 collect.parse_signin）。

背景（用户反馈 + Master 2026-10-17 查）：「签到系统假签到」——
  ① 旧兜底：页面**未识别**时 `parse_signin` 默认返回 `signed=True` → `signin.py` 记「签到成功」
     （登录页/报错页/改版页一律假成功）→ 19.2.3 已改成 `ambiguous=True`（不猜成功）；
  ② **残留洞（本次加固）**：成功判据是**扁平文本裸子串**，而 `SIGNED_TEXTS` 里混着
     `每日签到`（导航栏/板块标题常驻）与裸 `已签` → **未签页只因导航含「每日签到」就记已签**。
     实测复现：`<a href="logout.php">退出</a>…每日签到…<a href="attendance.php">签到</a>`
     旧表命中 → `signed=True`「今日已签到」。

本版判据顺序（强 → 弱，互不越权）：
  ① 强未签 `UNSIGNED_TEXTS`（待签到/未签到/…）→ 未签；② 强已签 `SIGNED_RE`（已得 N 魔力）；
  ③ 弱已签 `SIGNED_TEXTS`（已签回显**整短语**）；④ 弱未签 `UNSIGNED_CTRL_RE`（裸「签到」
  提交控件，只认 input/button、不认 `<a>` 导航）；⑤ 都读不到 → `ambiguous`。

断言：
  1) 登录页 → cookie_dead（不假成功）；空白页 → ambiguous（不假成功）；
  2) **回归铁证**：仅导航含「每日签到」的未签页 → **不**判已签；
  3) 裸「签到」提交控件 → 判未签（而非 ambiguous）；`<a>` 导航链接不算（不误伤已签页）；
  4) 硬判据不被翻案：已签页（已得 N 魔力 / 已签回显）+ 残留签到按钮 → 仍判已签；
  5) 已签回显各口径（已得 N 魔力 / 已签到 markup / 今日已签 / 无需再签）判已签、bonus 解出；
  6) 强未签压过一切肯定文案（dstudio：`<h1>` 固定「签到成功」+「待签到」→ 未签）；
  7) 常量护栏：`每日签到`/裸`已签` 不在 `SIGNED_TEXTS`；`UNSIGNED_CTRL_RE` 不匹配 `<a>`；
  8) 源码护栏：`signin.py` 的 ambiguous 分支记 `skipped+na`、最终兜底记 `False`（不写成功）。

用法：``python3 tools/test_signin_parse.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_signin_parse_test"

CHECKS = 0
FAILS: list[str] = []


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _pkg(name: str, path: Path) -> None:
    if name not in sys.modules:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m


def _ensure_app() -> None:
    """容器里有真 ``app``；本机（无 MoviePilot）时给最小桩，让 common.py 能加载。"""
    try:
        import app.schemas.types  # noqa: F401
        import app.sdk.events  # noqa: F401
        return
    except Exception:
        pass
    for name in ("app", "app.schemas", "app.sdk"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    t = types.ModuleType("app.schemas.types")
    t.EventType = type("EventType", (), {})
    sys.modules["app.schemas.types"] = t
    e = types.ModuleType("app.sdk.events")
    e.eventmanager = types.SimpleNamespace()
    sys.modules["app.sdk.events"] = e


def ok(cond: bool, msg: str) -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  ✓ {msg}")
    else:
        FAILS.append(msg)
        print(f"  ✗ {msg}")


def log(t: str) -> None:
    print(f"\n── {t} ──")


# ---------------------------------------------------------------------------
# 加载真 collect.py（合成父包解相对导入：fingerprint/common/kvstore → collect）
# ---------------------------------------------------------------------------
_pkg(PKG, ROOT)
_ensure_app()
_load(PKG + ".fingerprint", "fingerprint.py")
_load(PKG + ".common", "common.py")
_load(PKG + ".kvstore", "kvstore.py")
collect = _load(PKG + ".collect", "collect.py")
parse_signin = collect.parse_signin

OUT = '<a href="logout.php">退出</a>'  # 已登录标记（有它 → 绝不判 cookie 失效）


def case(title: str, raw: str, **exp) -> dict:
    """跑一例：逐字段断言 exp（键 ∈ {ok,signed,already,ambiguous,cookie_dead,pv_limited,bonus}）。

    缺省值即「没有这个键」→ 期望 ``False`` 时按「falsy」判（如 cookie_dead/ambiguous 为 False
    时键根本不存在），期望 ``True`` 时要真的 ``is True``。
    """
    got = parse_signin(raw)

    def _bad(k: str, want) -> bool:
        have = got.get(k)
        if want is False:
            return bool(have)
        if want is True:
            return have is not True
        return have != want

    bad = {k: (got.get(k), v) for k, v in exp.items() if _bad(k, v)}
    ok(not bad, f"{title} → " + (f"✅ {exp}" if not bad else f"✗ 期望 {exp}，实得 {{{', '.join(f'{k}={a}(期望{b})' for k, (a, b) in bad.items())}}} | {got}"))
    return got


def main() -> int:
    # ── 1) 旧兜底：认不出 ≠ 成功 ──────────────────────────────────────────
    log("1) 认不出就不许说成功（19.2.3 兜底：ambiguous）")
    case("登录页（密码框）", '<html><title>登录 - Powered by NexusPHP</title><input type="password" name="password"></html>',
         cookie_dead=True, signed=None)
    case("登录页（仅 title）", "<html><title>登录 :: NexusPHP</title></html>", cookie_dead=True, signed=None)
    case("空白页", "<html><body>nothing here</body></html>", ambiguous=True, signed=False, ok=False)
    case("PV 上限页", f"{OUT}访问次数已达上限", pv_limited=True)
    case("已登录但页无签到特征", f"{OUT}<div>welcome</div>", ambiguous=True, signed=False, cookie_dead=False)

    # ── 2) 回归铁证：导航「每日签到」不得算已签 ───────────────────────────
    log("2) ★ 残留洞回归：页面常驻「每日签到」不是已签事实")
    case("仅导航含「每日签到」（未签）",
         f'{OUT}<ul><li>每日签到</li></ul><a href="attendance.php">签到</a>',
         signed=False, ok=False)
    case("仅导航含「已签」（未签）", f"{OUT}<li>已签</li>", signed=False, ok=False)

    # ── 3) 弱未签：裸「签到」提交控件 ─────────────────────────────────────
    log("3) 弱未签判据：裸「签到」控件（只认 input/button）")
    case("input value=签到",
         f'{OUT}<form action="attendance.php"><input type="submit" value="签到"></form>',
         signed=False, ambiguous=False)
    case("button 包签到", f"{OUT}<form><button type='submit'>签到</button></form>",
         signed=False, ambiguous=False)
    case("待签到文案（强未签）", f"{OUT}<span>待签到</span>", signed=False, ambiguous=False)

    # ── 4) 硬/弱已签：不被弱未签控件翻案 ──────────────────────────────────
    log("4) 已签判据优先于弱未签控件（不许把真成功记成未签）")
    g = case("已得 N 魔力 + 残留签到按钮", f'{OUT}已得 2.5 个魔力<input type="submit" value="签到">',
             signed=True, already=True, bonus=2.5)
    ok(g.get("message") == "今日已签到", f"已得 N 魔力文案=今日已签到（实得 {g.get('message')!r}）")
    case("「今日已签到」+ 残留签到按钮", f'{OUT}<a href="attendance.php">今日已签到</a><input value="签到">',
         signed=True, already=True)
    case("「签到成功」回显", f"{OUT}<div>签到成功</div>", signed=True, already=False)
    case("「无需再签」回显", f"{OUT}<div>无需再签</div>", signed=True, already=True)
    case("pttime 式「今日已签」", f"{OUT}<div>今日已签</div>", signed=True, already=True)
    case("已得 1,234 个魔力（千分位）", f"{OUT}已得 1,234 个魔力", signed=True, bonus=1234.0)

    # ── 5) 强未签压过肯定文案（dstudio 类）───────────────────────────────
    log("5) 强未签压过一切肯定文案")
    case("h1 固定「签到成功」+「待签到」", f"{OUT}<h1>签到成功</h1><span>待签到</span>",
         signed=False, ambiguous=False)
    case("「已签到」+「未签到」并存（以未签为准）", f"{OUT}<div>已签到</div><div>未签到</div>", signed=False)

    # ── 6) 常量 / 源码护栏 ───────────────────────────────────────────────
    log("6) 护栏：常量表与上游分支不许退化")
    ok("每日签到" not in collect.SIGNED_TEXTS, "SIGNED_TEXTS 不含「每日签到」（导航常驻文案）")
    ok("已签" not in collect.SIGNED_TEXTS, "SIGNED_TEXTS 不含裸「已签」（半截词/历史记录）")
    for t in ("已签到", "今日已签到", "今日已签", "无需再签", "签到成功"):
        ok(t in collect.SIGNED_TEXTS, f"SIGNED_TEXTS 保留已签回显「{t}」")
    ok(not collect.UNSIGNED_CTRL_RE.search('<a href="attendance.php">签到</a>'),
       "UNSIGNED_CTRL_RE 不匹配 <a> 导航链接（不误伤已签页）")
    ok(bool(collect.UNSIGNED_CTRL_RE.search('<input type="submit" value="签到">')),
       "UNSIGNED_CTRL_RE 命中 value=\"签到\" 提交控件")

    src = (ROOT / "signin.py").read_text(encoding="utf-8")
    ok('if got.get("ambiguous")' in src, "signin.py 有 ambiguous 分支（未识别不算成功）")
    ok(re.search(r'if got\.get\("ambiguous"\):(?:.|\n){0,400}?skipped=True, na=True', src) is not None,
       "signin.py ambiguous 分支记 skipped+na（不粘「今日已成功」）")
    ok(re.search(r'return self\._store_result\(\s*"sign", site_id, name, False,\s*got\.get\("message"\)',
                 src) is not None,
       "signin.py 最终兜底记 False（不写成功）")
    ok(re.search(r'msg = "今日已签到（\+%s 魔力）"', src) is not None,
       "signin.py 记住成功路径（+N 魔力文案）")

    print("=" * 60)
    if FAILS:
        print(f"❌ FAIL —— {len(FAILS)}/{CHECKS} 项未过：")
        for f in FAILS:
            print(f"   · {f}")
        return 1
    print(f"✅ PASS —— 共 {CHECKS} 项全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
