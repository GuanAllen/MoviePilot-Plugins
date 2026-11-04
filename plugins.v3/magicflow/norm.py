# -*- coding: utf-8 -*-
"""数据清洗纯函数（L0 唯一出口）：文本归一 / 数值提取 / 时间格式。

为什么存在：
    19.10.16 实证——生产代码 490 个模块级短函数里，完全重复的实现集中在
    「文本归一 / 取第一个数字 / 数值有效性 / 当前时间」这四类，且分散在
    recommend / fallback / douban / live_stats / collect / sitestore / rescue /
    reportview 八个文件。它们各自重写的原因是「不知道别处已经有」，
    不是语义不同。本模块把这四类收敛成单一定义。

纳入标准（★ 入职必读）：
    只收**无状态、无 I/O、无 self、接口只有一个正确签名**的纯函数。
    这类函数**可以先验提供**——因为它的签名不可能猜错，也不存在未来分化。

不纳入（有意为之）：
    - `set_collect(ref)` 之类**依赖注入口**（改模块全局量），不是数据清洗；
    - `_norm_dom` / `_norm_sub` 之类**语义域已经分化**的归一（域名归一会剥
      scheme/端口/www，身份轴归一会解 tuple/JSON，两者未来必然分家）；
    - 任何带 self / 需要 try-except 包 plugin 的 adapter（如 `_site`）。

护栏：preflight 第 20 步（tools/check_norm_dup.py）——features/ 下再出现
    `norm_key` / `first_num` / `float_ok` / `now_iso` 的本地定义会直接报错。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

# ---------------------------------------------------------------- 文本归一

# 保留：数字 / 小写字母 / CJK 统一表意文字；其余（标点、空格、符号）全部剥掉
_NORM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def norm_key(s: Any) -> str:
    """标题归一：去标点/空格、转小写，用于跨源匹配（榜单↔订阅↔豆瓣）。

    ★ 三处实现（recommend / fallback / douban）一字不差，19.10.16 收于此处。
    豆瓣侧注释过「与服务端 & 旧快照实现保持一致」——改动此正则会破坏
    豆瓣快照的向后兼容，任何调整都必须先核对服务端实现。
    """
    return _NORM_RE.sub("", str(s or "").lower())


# ---------------------------------------------------------------- 数值

def first_num(pattern: str, text: str) -> Optional[float]:
    """按正则取第一个捕获组的数字（去千分位逗号），失败返回 None。

    ★ live_stats / collect 两处实现一字不差，19.10.16 收于此处。
    """
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return float(str(m.group(1)).replace(",", ""))
    except Exception:  # noqa: BLE001
        return None


def float_ok(v: Any) -> bool:
    """能否安全转成 float（None / 空串 / 脏串 → False），不做转换只判定。

    ★ sitestore / features.rescue 两处实现一字不差，19.10.16 收于此处。
    """
    try:
        float(v)
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- 时间

def now_iso() -> str:
    """当前本地时间 ISO 串（带时区、秒精度）。统一时间格式化的唯一出口。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")
