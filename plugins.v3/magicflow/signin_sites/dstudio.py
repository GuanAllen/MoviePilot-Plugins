# 魔流 · Depth Studio (dstudio.me) 专用签到处理器。
#
# 背景：dstudio 的签到**不是** GET attendance.php（通用兜底路径打不中，
# 且其签到页 <h1> 固定写「签到成功」→ 通用文本匹配会**误报成功**）。
#
# ★ 8.0.1 修正（2026-10-05 实测）：日常签到的真正入口是**签到页上的表单**
#     `<form method="post" action="attendance.php">` + `<input type="submit" value="立即签到">`
#     → **POST attendance.php**（无隐藏字段、无验证码）。
#   而 `ajax.php action=attendanceRetroactive` 是**「补签」**动作：对今天调用会被站点判
#     「补签卡不足」（原实现只对**已签到**的当天返回「已经签到」，导致 10-04 那次验证是**假阳性**）。
#   现在：① 先探「是否已签」；② POST attendance.php 日常签到；③ 复核页面是否仍「待签到」；
#   ④ 仍失败再兜底补签 action；⑤ 最终以**签到页状态**为准，杜绝误报。
#
# 判定「已签」：签到页出现 `is-pending` / 「待签到」= 未签；否则视为已签。
from datetime import datetime
from typing import Tuple

from app.core.config import settings
from app.log import logger
from app.utils.http import RequestUtils
from app.utils.string import StringUtils
from ruamel.yaml import CommentedMap

from . import SiteSigninHandler as _ISiteSigninHandler


class DepthStudio(_ISiteSigninHandler):
    """Depth Studio（dstudio.me）签到。"""

    # 匹配的站点 Url（域名）
    site_url = "dstudio.me"

    _ENDPOINT = "ajax.php"
    _REFERER = "attendance.php"

    @classmethod
    def match(cls, url: str) -> bool:
        """根据站点 Url 判断是否匹配当前处理器。"""
        return True if StringUtils.url_equal(url, cls.site_url) else False

    @staticmethod
    def _base(site_info: CommentedMap) -> str:
        u = str(site_info.get("url") or "").strip().rstrip("/")
        return u or "https://dstudio.me"

    # ---------------------------------------------------------------- 工具
    @classmethod
    def _req(cls, base: str, site_info: CommentedMap, timeout=None) -> RequestUtils:
        proxies = settings.PROXY if site_info.get("proxy") else None
        return RequestUtils(
            cookies=site_info.get("cookie"),
            ua=site_info.get("ua"),
            proxies=proxies,
            timeout=timeout,
            referer=f"{base}/{cls._REFERER}",
        )

    @classmethod
    def _check_signed(cls, base: str, site_info: CommentedMap, timeout=None) -> Tuple[bool, bool]:
        """抓签到页判断状态。返回 ``(是否已签, 是否可达)``。

        已签 = 页面**不再**出现 `is-pending` / 「待签到」。
        """
        res = cls._req(base, site_info, timeout).get_res(url=f"{base}/attendance.php")
        if not res or res.status_code != 200:
            return False, False
        text = res.text or ""
        if "login.php" in text or 'name="password"' in text:
            return False, False
        if "is-pending" in text or "待签到" in text:
            return False, True
        return True, True

    def signin(self, site_info: CommentedMap) -> Tuple[bool, str]:
        """执行签到：POST attendance.php（日常）；复核页面状态；兜底补签 action。"""
        name = site_info.get("name") or self.site_url
        timeout = site_info.get("timeout")
        base = self._base(site_info)

        # ① 先探是否已签（避免误报 + 省一次写）
        signed, reachable = self._check_signed(base, site_info, timeout)
        if signed:
            logger.info(f"{name} 今日已签到")
            return True, "今日已签到"
        if not reachable:
            logger.error(f"{name} 签到失败，请检查站点连通性")
            return False, "签到失败，请检查站点连通性"

        # ② 日常签到：POST attendance.php（「立即签到」表单）
        try:
            self._req(base, site_info, timeout).post_res(
                url=f"{base}/attendance.php", data={"submit": "立即签到"}
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"{name} attendance POST 异常: {e}")

        # ③ 复核
        signed, _ = self._check_signed(base, site_info, timeout)
        if signed:
            logger.info(f"{name} 签到成功")
            return True, "签到成功"

        # ④ 兜底：补签 action（对今天）
        today = datetime.now().strftime("%Y-%m-%d")
        _msg = ""
        try:
            res = self._req(base, site_info, timeout).post_res(
                url=f"{base}/{self._ENDPOINT}",
                data={"action": "attendanceRetroactive", "params[date]": today},
            )
            if res and res.status_code == 200:
                try:
                    payload = res.json()
                except Exception:  # noqa: BLE001
                    payload = None
                if isinstance(payload, dict):
                    ret = payload.get("ret")
                    _msg = str(payload.get("msg") or "").strip()
                    if ret == 0 or "已经签" in _msg or "已签" in _msg or "重复" in _msg:
                        signed, _ = self._check_signed(base, site_info, timeout)
                        if signed:
                            logger.info(f"{name} 签到成功")
                            return True, (_msg or "签到成功")
        except Exception as e:  # noqa: BLE001
            logger.error(f"{name} 补签兜底异常: {e}")

        # ⑤ 最终以签到页状态为准
        signed, _ = self._check_signed(base, site_info, timeout)
        if signed:
            logger.info(f"{name} 签到成功")
            return True, "签到成功"
        logger.error(f"{name} 签到失败（签到页仍是「待签到」）: {_msg}")
        return False, (_msg or "签到失败（仍待签到）")

    def login(self, site_info: CommentedMap) -> Tuple[bool, str]:
        """模拟登录：只读访问首页确认会话有效（**不做写动作**）。"""
        name = site_info.get("name") or self.site_url
        base = self._base(site_info)
        proxies = settings.PROXY if site_info.get("proxy") else None
        res = RequestUtils(
            cookies=site_info.get("cookie"),
            ua=site_info.get("ua"),
            proxies=proxies,
            timeout=site_info.get("timeout"),
        ).get_res(url=f"{base}/index.php")
        if not res or res.status_code != 200:
            return False, "登录失败，请检查站点连通性"
        text = res.text or ""
        if 'name="password"' in text or "login.php" in text:
            return False, "登录失败，Cookie已失效"
        return True, "模拟登录成功"
