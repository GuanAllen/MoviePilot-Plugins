#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 站点用户等级解析（★ 19.11.16，④ 的第一半）离线回归 —— 真跑 collect_parse.py。

为什么先只做「等级」：它从**已经抓到的那个用户栏页面**里就能认出来，零额外请求；
而「升级要求」要逐站另抓详情页、再按各站规则解析，站点一改版就废，也确实算不出来时
必须显式留白 —— 先不做，等确认要不要付这个维护成本。

底线：**解不出就是 None**。等级是站点域的事实，客户端算不出来（铁律 6），
报一个像真的错值比空着坏得多。特别防一种误判：用户栏里**用户名**那条链接长得跟等级
一样（`<a href="userdetails.php?id=1"><b>名字</b></a>`），不许把它当等级。

断言：
  [1] 老模板 `[<a href=userdetails...><font class='Color_UserBar'>Power User</font></a>]`；
  [2] 双引号 class / 无外链的 `<font class="Color_UserBar">`；
  [3] 中文站「等级：骨灰」；
  [4] **不误抓用户名**（只有用户名链接 → None）；
  [5] 只有退出/邀请这类链接 → None（噪音词过滤）；
  [6] 空白 / None / 无等级字段 → None；
  [7] `parse_user_bar` 里带上 `level`（有就填，没有就 None，不编）。

用法：``python3 tools/test_user_level.py``（退出码 0=PASS / 1=FAIL）。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_user_level_test"

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


def _load_parse():
    _pkg(PKG, ROOT)
    for name, attrs in (
        ("app", {}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.logging", {"logger": __import__("logging").getLogger("mf-test")}),
    ):
        m = sys.modules.get(name) or types.ModuleType(name)
        sys.modules[name] = m
        for k, v in attrs.items():
            setattr(m, k, v)
    for modname, attrs in (("common", ()), ("tagspec", ()), ("norm", ())):
        try:
            _load(PKG + "." + modname, modname + ".py")
        except Exception:  # noqa: BLE001
            m = types.ModuleType(PKG + "." + modname)
            sys.modules[PKG + "." + modname] = m
    return _load(PKG + ".collect_parse", "collect_parse.py")


def main() -> int:
    cp = _load_parse()
    lv = cp.parse_user_level

    print("[1] 老模板：Color_UserBar 在方括号里")
    html = ("欢迎回来, <a href=\"userdetails.php?id=123\" class='User_Name'><b>someone</b></a> "
            "[<a href=\"userdetails.php?id=123\"><font class='Color_UserBar'>Power User</font></a>] "
            "| <a href=\"logout.php\">退出</a>")
    ok(lv(html) == "Power User", f"取到 Power User（实际 {lv(html)!r}）")

    print("[2] 双引号 class / 中文站写法")
    html2 = '<font class="Color_UserBar">Elite User</font>'
    ok(lv(html2) == "Elite User", "双引号 class 也认")
    html3 = '<span>等级：<font color="#ff0000">骨灰</font></span>'
    ok(lv(html3) == "骨灰", f"「等级：骨灰」→ 骨灰（实际 {lv(html3)!r}）")

    print("[3] 不许把用户名当等级")
    only_name = ("欢迎回来, <a href=\"userdetails.php?id=9\" class='User_Name'><b>someone</b></a> "
                 "| <a href=\"logout.php\">退出</a>")
    ok(lv(only_name) is None, f"只有用户名链接 → None（实际 {lv(only_name)!r}）")
    ok(lv(only_name) != "someone", "尤其不许返回用户名本身")

    print("[4] 噪音词过滤 / 空输入")
    ok(lv('<a href="logout.php">退出</a> <a href="invite.php">邀请</a>') is None,
       "退出 / 邀请这类文本不当等级")
    ok(lv("") is None and lv(None) is None, "空输入 → None")
    ok(lv("<html><body>nothing here</body></html>") is None, "没有等级 → None")

    print("[5] parse_user_bar 里带上 level")
    bar = cp.parse_user_bar(html)
    ok("level" in bar, "字段 level 存在")
    ok(bar["level"] == "Power User", "有就填真值")
    bar2 = cp.parse_user_bar(only_name)
    ok(bar2["level"] is None, "没有就 None（不编一个）")
    ok(bar2["uid"] == 9 or bar2["uid"] == "9", f"uid 仍照常解出（{bar2['uid']!r}）")

    # ── ★ 19.11.18：userdetails 页「等级」行（PTD 口径：td.rowhead + td > img[title]）──
    print("[6] parse_user_details：userdetails 的等级行 / img title")
    det = cp.parse_user_details
    # 真机 carpt 2026-11 格式：class 多值（"rowhead nowrap"）+ img title 在 src 前 + 行头格 width="99%" 陷阱
    d1 = ('<tr><td width="1%" class="rowhead nowrap" valign="top" align="right">等级</td>'
          '<td width="99%" class="rowfollow" valign="top" align="left">'
          '<img alt="User" title="User" src="pic/user.gif" /> </td></tr>')
    ok(det(d1)["level"] == "User", f"真机 carpt 格式（多 class 行头）→ User（实际 {det(d1)['level']!r}）")
    d2 = ('<td class="rowhead">等級</td><td><img title="Elite User" src="pic/class_3.gif"></td>')
    ok(det(d2)["level"] == "Elite User", "繁体等級 / title 在 src 前也认")
    d3 = ('<td class="rowhead">Class</td><td><img src="x.png" title="Nexus Master"></td>')
    ok(det(d3)["level"] == "Nexus Master", "英文 Class 行也认")
    d4 = ('<td class="rowhead">等级</td><td>骨灰</td>')
    ok(det(d4)["level"] == "骨灰", f"纯文本等级兜底（实际 {det(d4)['level']!r}）")
    ok(det("<html>no rows</html>")["level"] is None, "没有等级行 → None（不猜）")
    ok(det("")["level"] is None and det(None)["level"] is None, "空输入 → None")

    print("[7] parse_user_details：做种积分 / 加入日期（数值取格内文本，不吃行头 width 的数字）")
    d5 = ('<tr><td width="1%" class="rowhead nowrap" valign="top" align="right">做种积分</td>'
          '<td width="99%" class="rowfollow" valign="top" align="left">83,454.4&nbsp;&nbsp;'
          "<span class='text-muted'>(更新时间: 2026-11-02 21:32:17)</span></td></tr>"
          '<tr><td width="1%" class="rowhead nowrap" valign="top" align="right">加入日期</td>'
          '<td width="99%" class="rowfollow" valign="top" align="left">2026-09-27 13:24:33 '
          '(<span title="2026-09-27 13:24:33">1月6天前</span>, 5周)</td></tr>')
    r5 = det(d5)
    ok(abs((r5["seeding_bonus"] or 0) - 83454.4) < 0.01,
       f"做种积分 83454.4（实际 {r5['seeding_bonus']!r}；回归：不许吃 width=99% 的 99）")
    ok(str(r5["join_time"]).startswith("2026-09-27"), f"加入日期丢掉相对时间（实际 {r5['join_time']!r}）")
    r6 = det("<html>nothing</html>")
    ok(r6["seeding_bonus"] is None and r6["join_time"] is None, "缺行 → None（不编）")

    print("[8] 用户栏导航词不误判（真机 PT时间 曾把「个人中心」当等级）")
    nav = ('<a href="usercp.php"><font class=\'Color_UserBar\'>个人中心</font></a>'
           ' <a href="logout.php">退出</a>')
    ok(lv(nav) is None, f"个人中心 → None（实际 {lv(nav)!r}）")

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
