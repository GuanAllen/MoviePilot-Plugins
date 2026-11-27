# -*- coding: utf-8 -*-
"""魔力兑换写动作（★ 19.16.28）。

放在 ``sites/`` 而不是 ``features/``：check_collect_boundary R2「网络不许长在 features/」；
本站适配器的抓+写刻意耦合在这里（同 ``signin_sites/`` / ``claim_sites/``）。

NexusPHP 的 mybonus.php 兑换是**统一形态**（实测 13 站）：::

    <form action="?action=exchange" method="post">
      <input type="hidden" name="option" value="N">
      <input type="submit" name="submit" value="交换">
    </form>

所以一段 POST 打天下，**不需要分站 preset**：
``POST {base}/mybonus.php?action=exchange``，form data ``option=N & submit=交换``。

★ 写动作只接受**解析层给的合法 option**（必须在当次看板的上传量项里），
  features 层负责把 option 与站点当前页面核对；这里只管发一次请求、回读结果。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple


def site_base(site: Any) -> str:
    base = str((getattr(site, "url", "") or getattr(site, "domain", "") or "")).strip()
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


def exchange_upload(base: str, option: int, cookie: str, ua: str = "",
                    timeout: int = 20, proxies: Any = None,
                    submit: str = "交换") -> Tuple[bool, str, str, str]:
    """对某站发一次兑换写请求（上传量 / 邀请名额 / 临时邀请通用）。

    NexusPHP 三类兑换共用同一 form（``option=N & submit=按钮文案``），所以本函数不分类型，
    只管发一次请求、回读结果；option 是否合法由 features 层核对当次页面。

    Returns: ``(ok, status, message, evidence)``
      - ``ok``：**只在站点回显明确成功时为 True**（不做「没报错就算成功」）；
      - ``status``：``ok`` / ``fail`` / ``auth``（401/403）；
      - ``message``：给用户看的结论；
      - ``evidence``：页面回显关键句（脱敏后，最多 400 字），便于审计。
    """
    try:
        from app.utils.http import RequestUtils  # noqa: WPS433（惰性导入，离线可测）
    except Exception as err:  # pragma: no cover
        return False, "fail", f"SDK 不可用：{err}", ""
    url = f"{base}/mybonus.php?action=exchange"
    data = {"option": int(option), "submit": (submit or "交换")}
    try:
        req = RequestUtils(cookies=(cookie or "").strip(), ua=(ua or "Mozilla/5.0").strip(),
                           proxies=proxies, timeout=timeout, referer=base + "/mybonus.php")
        res = req.post_res(url=url, data=data)
    except Exception as err:  # noqa: BLE001
        return False, "fail", f"写请求异常：{err}", ""
    if res is None:
        return False, "fail", "站点无响应（连通性 / 登录态？）", ""
    code = int(getattr(res, "status_code", 0) or 0)
    if code in (401, 403):
        return False, "auth", f"HTTP {code}：Cookie 失效或无权限", ""
    text = str(getattr(res, "text", "") or "")
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    flat = flat[:400]
    # 站点回显：成功常见「兑换成功 / 交换成功 / 已成功兑换 / 上传量已增加」；
    # 失败常见「魔力不足 / 分享率 / 等级不足 / 购买间隔」。宁可判「待核实」也不把失败说成成功。
    ok_words = ("兑换成功", "交换成功", "已成功兑换", "成功换取", "exchange success", "uploaded")
    bad_words = ("不足", "失败", "错误", "不能", "不可", "间隔", "等级", "请稍后", "invalid", "error")
    if any(w in text for w in ok_words) and not any(w in text for w in bad_words):
        return True, "ok", "兑换成功（站点回显确认）", flat
    if any(w in text for w in bad_words):
        hit = next((w for w in bad_words if w in text), "")
        return False, "fail", f"站点未确认成功（回显含「{hit}」），请以站点页面为准", flat
    return False, "fail", "站点未回显成功字样，请到站点核实是否到账", flat
