#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线测试：``collect.parse_user_bar`` 用户栏解析（15.16.1 补强）。

覆盖各站真实模板差异（数据在页面上，旧正则丢掉）：
  1. 分隔符可省：「分享率 1.202 / 上传量 12.02 GB」（Depth Studio 类）
  2. 分享率「无限」（下载=0）→ ``ratio_inf=True``（有效事实，≠ 解析失败）
  3. 魔力值别名：财神「元宝」/ 蟹黄堡「蟹币值」
  4. 干扰串不误命中：「[签到得金元宝] … 邀请: 0(0)」
  5. 旧模板回归：``分享率: 1.01 / 上传量: 307.28 GB``

纯离线：不碰网络 / 不依赖插件上下文。**直接加载纯解析层** ``collect_parse.py``。
运行：``PYTHONPYCACHEPREFIX=/tmp/pyc python3 tools/test_user_bar_parse.py``
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
FAILED: list = []


def _load_collect():
    """加载纯解析层（``norm`` + ``collect_parse``），不碰传输层 ``collect.py``。

    ★ 2026-11-05：旧法是「读 ``collect.py`` 源码 + 字符串剥相对导入 + exec」，在 19.10.31
    把解析拆成 ``collect_parse.py`` 之后就废了 —— ``from .collect_parse import ...`` 在没有
    包上下文的 exec 里无法解析，本文件从此一直红着（不是断言失败，是加载就崩）。
    现在按文件加载、用一个合成包名承载相对导入，零 app 依赖、零字符串替换。
    """
    pkg = types.ModuleType("mf_parse_offline")
    pkg.__path__ = [str(ROOT)]
    sys.modules["mf_parse_offline"] = pkg
    for name in ("norm", "collect_parse"):
        spec = importlib.util.spec_from_file_location("mf_parse_offline." + name,
                                                      ROOT / (name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["mf_parse_offline." + name] = mod
        spec.loader.exec_module(mod)
    return sys.modules["mf_parse_offline.collect_parse"]


C = _load_collect()
parse_user_bar = C.parse_user_bar


def chk(name, cond, got=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ← {got}"))
    if not cond:
        FAILED.append(name)


def gb(n):
    return None if n is None else round(n / 1024 / 1024 / 1024, 2)


# 1) 无冒号模板（Depth Studio）
r = parse_user_bar("欢迎回来 分享率 1.202 上传量 12.02 GB 下载量 10.01 GB 魔力值 12,340.9")
chk("无冒号·分享率", r["ratio"] == 1.202, r["ratio"])
chk("无冒号·上传", gb(r["upload"]) == 12.02, gb(r["upload"]))
chk("无冒号·下载", gb(r["download"]) == 10.01, gb(r["download"]))
chk("无冒号·魔力", r["bonus"] == 12340.9, r["bonus"])

# 2) 分享率「无限」（下载=0）
r = parse_user_bar("分享率: 无限 上传量: 45.94 GB 下载量: 0.00 KB 魔力值 [ 使用 ]: 6,699.6")
chk("无限·ratio_inf", r["ratio_inf"] is True, r.get("ratio_inf"))
chk("无限·ratio 不误报", r["ratio"] is None, r["ratio"])
chk("无限·上传仍可读", gb(r["upload"]) == 45.94, gb(r["upload"]))

# 3) 魔力值别名：财神「元宝」（含前置干扰串「签到得金元宝」）
r = parse_user_bar(
    "[签到得金元宝] [ 邀请 ]: 0(0) [勋章] [任务] 上传量: 223.68 GB 下载量: 0.00 KB "
    "分享率: 无限 元宝 32,321.8 当前做种 0"
)
chk("别名·元宝", r["bonus"] == 32321.8, r["bonus"])
chk("别名·元宝不误命中签到串", r["bonus"] not in (0.0, None), r["bonus"])

# 4) 魔力值别名：蟹黄堡「蟹币值」
r = parse_user_bar("[签到得蟹币] 蟹币值 [ 使用 ]: 10,676.4 分享率: 无限 上传量: 21.97 GB")
chk("别名·蟹币值", r["bonus"] == 10676.4, r["bonus"])

# 5) 旧模板回归（PT时间类）
r = parse_user_bar("分享率: 1.01 上传量: 307.28 GB 下载量: 305.72 GB 元宝 0")
chk("回归·分享率", r["ratio"] == 1.01, r["ratio"])
chk("回归·上传", gb(r["upload"]) == 307.28, gb(r["upload"]))
chk("回归·下载", gb(r["download"]) == 305.72, gb(r["download"]))
chk("回归·ratio_inf 默认 False", r.get("ratio_inf") is False, r.get("ratio_inf"))

# 6) ★ 17.2.2：页头 H&R 计数事实（「考核中/未完成/上限」，上限＝达到即禁用账号）
r = parse_user_bar("<a href='myhr.php'>H&R: [0/0/15]</a> 分享率: 2.5 上传量: 10.00 GB")
chk("H&R·三数", isinstance(r.get("hr"), dict) and r["hr"]["assessing"] == 0
    and r["hr"]["unfinished"] == 0 and r["hr"]["limit"] == 15, r.get("hr"))
r = parse_user_bar("H&amp;R 2/1/10 分享率: 1.0 上传量: 1.00 GB")
chk("H&R·实体转义+无冒号", isinstance(r.get("hr"), dict) and r["hr"]["assessing"] == 2
    and r["hr"]["unfinished"] == 1 and r["hr"]["limit"] == 10, r.get("hr"))
r = parse_user_bar("H&R: 3 分享率: 1.0 上传量: 1.00 GB")
chk("H&R·单数归入未完成（保守）", isinstance(r.get("hr"), dict) and r["hr"]["assessing"] is None
    and r["hr"]["unfinished"] == 3 and r["hr"]["limit"] is None, r.get("hr"))
# 真机形态（学校 pt.btschool.club）：数字被 font/span 切开、且不给第三个数 → limit=None
r = parse_user_bar('<a href="myhr.php"><font class="medium">H&amp;R:</font>0/'
                   '<span style="color:#f00;font-weight: bold;">0</span></a> 分享率: 5.9')
chk("H&R·学校真机形态（无禁用线）", isinstance(r.get("hr"), dict) and r["hr"]["assessing"] == 0
    and r["hr"]["unfinished"] == 0 and r["hr"]["limit"] is None, r.get("hr"))
# 真机形态（财神 cspt.top）：标签写成 `[H&R]:`、数字与标签之间换行、且被 <font> 切开
r = parse_user_bar('<div class="menu-base-info-items">[H&R]:\n [<a href="myhr.php">0/'
                   '<font color="red">0</font>/10</a>]</div> 分享率: 3.3')
chk("H&R·财神真机形态（[H&R]: + 换行 + font）", isinstance(r.get("hr"), dict)
    and r["hr"]["assessing"] == 0 and r["hr"]["unfinished"] == 0 and r["hr"]["limit"] == 10, r.get("hr"))
# 真机形态（大青虫 cyanbug.net）：站点**没开这栏**，只剩模板注释 `<!-- H&R -->` → 必须 None
r = parse_user_bar("<!-- H&R --> <font>认领: </font> [<a href='claim.php'>0/1000</a>] 分享率: 1.5")
chk("H&R·注释占位=None（大青虫真机）", r.get("hr") is None, r.get("hr"))

# 7) ★ 17.2.2：**没有这一栏 → None（不等于 0）**
r = parse_user_bar("分享率: 1.01 上传量: 307.28 GB 下载量: 305.72 GB")
chk("H&R·无该栏=None", r.get("hr") is None, r.get("hr"))

# 8) ★ 17.2.2：有栏但解不出数字 → 只留 raw（不冒充 0）
#    只认真栏：命中处必须挂着 myhr.php 链接（导航文案/占位符不算）
r = parse_user_bar("<a href='myhr.php'>H&R: 详见规则页</a> 分享率: 1.0 上传量: 1.00 GB")
chk("H&R·解不出只留 raw", isinstance(r.get("hr"), dict) and r["hr"]["assessing"] is None
    and r["hr"]["raw"], r.get("hr"))
r = parse_user_bar("本站 H&R: 详见规则页 分享率: 1.0 上传量: 1.00 GB")
chk("H&R·无 myhr 链接的文案不算栏", r.get("hr") is None, r.get("hr"))



# ── API 档案归一（normalize_api_profile）────────────────────────────────
norm = getattr(C, "normalize_api_profile", None)
chk("API 归一函数存在", callable(norm))

# 野马PT：promotionUploadSize / promotionDownloadSize，无 shareRate
_yema = {"id": 4183, "name": "alanguan", "level": 2, "bonus": 978, "status": "enable",
         "promotionUploadSize": 43817850558, "promotionDownloadSize": 0}
b = norm(_yema)
chk("野马·uid", b["uid"] == "4183", b["uid"])
chk("野马·上传", gb(b["upload"]) == 40.81, gb(b["upload"]))
chk("野马·下载 0", b["download"] == 0, b["download"])
chk("野马·魔力", b["bonus"] == 978, b["bonus"])
chk("野马·分享率无限", b["ratio_inf"] is True and b["ratio"] is None, b)

# 馒头：memberCount / memberStatus
_mteam = {"memberCount": {"bonus": 20438.9, "uploaded": 605463374583, "downloaded": 192000000000, "shareRate": 3.15},
          "memberStatus": {"id": 12345, "vip": False, "warned": False}}
b = norm(_mteam)
chk("馒头·uid", b["uid"] == "12345", b["uid"])
chk("馒头·分享率", b["ratio"] == 3.15, b["ratio"])
chk("馒头·ratio_inf False", b["ratio_inf"] is False, b.get("ratio_inf"))
chk("馒头·上传", gb(b["upload"]) == 563.88, gb(b["upload"]))

# 现算：下载 > 0 且无 shareRate → 上传/下载
b = norm({"id": 1, "promotionUploadSize": 100 * 1024 ** 3, "promotionDownloadSize": 50 * 1024 ** 3, "bonus": 1})
chk("现算·分享率", b["ratio"] == 2.0, b["ratio"])
chk("现算·非无限", b["ratio_inf"] is False, b.get("ratio_inf"))

chk("空载荷 → None", norm({}) is None, norm({}))

# ★ 19.12.42 uhddolby 页头 H&R（真机原文，2026-11-05 取证）：
#   `<a href="myhr.php"> <font class="color_bonus">H&amp;R: </font> 0`
#   —— `&` 是实体转义、数字在标签外；旧正则只认字面 `H&R` → 整栏读成 None。
_UHD_HTML = ('<a href="myhr.php"> <font class="color_bonus">H&amp;R: </font> 0</a>'
             ' 分享率: 1.5 上传量: 1.00 GB 下载量: 0.50 GB')
r = parse_user_bar(_UHD_HTML)
chk("uhddolby·H&R 栏读到了", isinstance(r.get("hr"), dict), r.get("hr"))
chk("uhddolby·形态 = single", (r.get("hr") or {}).get("form") == "single", r.get("hr"))
chk("uhddolby·单数字进 unfinished=0", (r.get("hr") or {}).get("unfinished") == 0, r.get("hr"))
chk("uhddolby·assessing 不伪造", (r.get("hr") or {}).get("assessing") is None, r.get("hr"))
chk("uhddolby·limit 不伪造", (r.get("hr") or {}).get("limit") is None, r.get("hr"))

# 两数形态同样可能被实体转义 + 被 <font> 切开（真机常见）
_PAIR_HTML = ('<a href="myhr.php">[<font>H&amp;R</font>]:</a> 0/<font color=red>1</font>/15')
r = parse_user_bar(_PAIR_HTML)
chk("实体两数·form=pair", (r.get("hr") or {}).get("form") == "pair", r.get("hr"))
chk("实体两数·assessing", (r.get("hr") or {}).get("assessing") == 0, r.get("hr"))
chk("实体两数·unfinished", (r.get("hr") or {}).get("unfinished") == 1, r.get("hr"))
chk("实体两数·limit", (r.get("hr") or {}).get("limit") == 15, r.get("hr"))

# 没有这一栏 → None（**不等于 0**）
r = parse_user_bar("分享率: 1.2 上传量: 1.00 GB 下载量: 0.50 GB")
chk("无 H&R 栏 → hr=None", r.get("hr") is None, r.get("hr"))

if FAILED:
    print(f"❌ 合计 {len(FAILED)} 项失败：{FAILED}")
    sys.exit(1)
print("✅ 全部通过（用户栏 + API 档案归一）")
