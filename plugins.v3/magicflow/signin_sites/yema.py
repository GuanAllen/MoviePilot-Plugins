# 来源：MoviePilot「站点自动签到」插件（thsrite / autosignin, GPL-3.0）—— 移植适配魔流。
# ★ 7.19.0 重写：原实现用 **GET** 打 `api/consumer/checkIn`（真接口是 **POST** JSON）→ 必失败，
#   且 7.17.0 的「API 鉴权站如实化」误把本站短路成「不支持签到」，处理器根本没机会跑（本次一并修正）。
#   站点实际签到 = `POST api/consumer/checkIn`，且必须携带 **Altcha 人机验证（PoW）** 结果：
#     ① GET  api/consumer/fetchCheckInPageInfo  → 只读查「今日是否已签」
#     ② POST api/captcha/generateAltchaChallenge {feature:"checkIn"} → 拿挑战
#     ③ 本地求解（signin_sites/altcha.py）
#     ④ POST api/consumer/checkIn {altchaPayload:"<base64>"} → success / 「已签过到」= 成功
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

from ruamel.yaml import CommentedMap

from app.core.config import settings
from app.utils.http import RequestUtils
from . import SiteSigninHandler as _ISiteSigninHandler
from . import altcha


def _json(res: Any) -> Dict[str, Any]:
    try:
        d = res.json()
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


class YemaPT(_ISiteSigninHandler):
    """
    YemaPT 签到（openApi 通道 + Altcha 人机验证）
    """
    # 匹配的站点Url，每一个实现类都需要设置为自己的站点Url
    site_url = "yemapt.org"

    @classmethod
    def match(cls, url: str) -> bool:
        """根据站点Url判断是否匹配当前站点签到类。"""
        return True if cls.site_url in url else False

    # ---------------------------------------------------------------- 工具
    @staticmethod
    def _headers(site_info: CommentedMap) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": site_info.get("ua"),
        }

    def _req(self, site_info: CommentedMap) -> RequestUtils:
        return RequestUtils(
            headers=self._headers(site_info),
            timeout=site_info.get("timeout"),
            cookies=site_info.get("cookie"),
            proxies=settings.PROXY if site_info.get("proxy") else None,
            referer=site_info.get("url"),
        )

    # ---------------------------------------------------------------- 签到
    def signin(self, site_info: CommentedMap) -> Tuple[bool, str]:
        """执行签到：先看今日状态 → 取 Altcha 挑战并求解 → 提交签到。"""
        base = str(site_info.get("url") or "")

        # ① 今日状态（只读，零副作用）
        try:
            st = self._req(site_info).get_res(urljoin(base, "api/consumer/fetchCheckInPageInfo"))
        except Exception as err:  # noqa: BLE001
            return False, f"签到失败：{err}"
        if st is not None:
            sj = _json(st)
            if sj.get("success") and ((sj.get("data") or {}).get("checkedInToday")):
                return True, "今日已签到"

        # ② 取 Altcha 挑战
        try:
            ch_res = self._req(site_info).post_res(
                url=urljoin(base, "api/captcha/generateAltchaChallenge"),
                json={"feature": "checkIn"},
            )
        except Exception as err:  # noqa: BLE001
            return False, f"签到失败：获取人机验证异常（{err}）"
        if ch_res is None:
            return False, "签到失败：无法获取人机验证"
        cj = _json(ch_res)
        challenge = cj.get("data") if cj.get("success") else None
        if not challenge:
            return False, f"签到失败：人机验证下发失败（{cj.get('errorMessage') or ch_res.status_code}）"

        # ③ 本地求解（PBKDF2/SHA-256 PoW）
        payload = altcha.solve_payload(challenge)
        if not payload:
            return False, "签到失败：人机验证未能求解（超时或格式不符）"

        # ④ 提交签到
        try:
            res = self._req(site_info).post_res(
                url=urljoin(base, "api/consumer/checkIn"),
                json={"altchaPayload": payload},
            )
        except Exception as err:  # noqa: BLE001
            return False, f"签到失败：{err}"
        if res is None:
            return False, "签到失败，无法打开网站"
        rj = _json(res)
        if rj.get("success"):
            return True, "签到成功"
        emsg = str(rj.get("errorMessage") or "")
        if "已签" in emsg:
            return True, "今日已签到"
        return False, f"签到失败，签到结果：{emsg or res.status_code}"

    # ---------------------------------------------------------------- 登录
    def login(self, site_info: CommentedMap) -> Tuple[bool, str]:
        """执行模拟登录（读 openApi 用户信息验活）。"""
        try:
            res = self._req(site_info).get_res(urljoin(str(site_info.get("url") or ""), "api/user/profile"))
        except Exception as err:  # noqa: BLE001
            return False, f"模拟登录失败：{err}"
        if res is not None and _json(res).get("success"):
            return True, "模拟登录成功"
        if res is not None:
            return False, f"模拟登录失败，状态码：{res.status_code}"
        return False, "模拟登录失败，无法打开网站"
