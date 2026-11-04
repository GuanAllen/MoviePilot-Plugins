# -*- coding: utf-8 -*-
"""envops.hd_api_base 的边界（19.11.5）。

背景：HDDolby 2026-11-02 换域名到 uhddolby.com，官方 API 从 ``api.<域名>``
搬到主站（``api.uhddolby.com`` 已无解析，``https://www.uhddolby.com/api/v1`` 实测 200）。
本测试钉死取值优先级，防止以后有人把 ``api.`` 前缀再加回来。

基线：6 条断言（新增功能，无历史回归）。
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from envops import hd_api_base  # noqa: E402

_fail = 0
_n = 0


def ok(cond: bool, name: str, extra: str = "") -> None:
    global _fail, _n
    _n += 1
    if cond:
        print(f"  [ok] {name}")
    else:
        _fail += 1
        print(f"  [FAIL] {name} {extra}")


def main() -> int:
    print("== 登记表优先 ==")
    ok(hd_api_base(None, "uhddolby.com") == "https://www.uhddolby.com", "新域名走主站")
    ok(hd_api_base(None, "hddolby.com") == "https://www.uhddolby.com", "旧域名别名同指向")
    ok(hd_api_base(SimpleNamespace(domain="uhddolby.com", url="https://api.uhddolby.com")) ==
       "https://www.uhddolby.com", "登记表压过站点里的旧 URL")

    print("== 未登记站点 ==")
    ok(hd_api_base(SimpleNamespace(domain="example.org", url="https://www.example.org/")) ==
       "https://www.example.org", "有 URL 用 URL（去尾斜杠）")
    ok(hd_api_base(SimpleNamespace(domain="example.org", url="")) ==
       "https://api.example.org", "无 URL 回落 api 子域")

    print("== 空输入 ==")
    ok(hd_api_base(None, "") == "", "无域名返回空串（调用方自行短路）")

    print(f"\n{_n - _fail}/{_n} 通过")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
