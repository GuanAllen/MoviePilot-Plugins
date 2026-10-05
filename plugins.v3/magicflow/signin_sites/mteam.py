# 来源：MoviePilot「站点自动签到」插件（thsrite / autosignin, GPL-3.0）—— 移植适配魔流。
# ★ 7.17.0：馒头走官方 API Key 通道（第三方工具），按站点口径**不算登入**；
#   这里不再发无意义的 updateLastBrowse（apikey 直接 401），如实回报「不支持」。
from typing import Tuple

from ruamel.yaml import CommentedMap

from . import SiteSigninHandler as _ISiteSigninHandler


class MTorrent(_ISiteSigninHandler):
    """
    m-team签到
    """
    # 匹配的站点Url，每一个实现类都需要设置为自己的站点Url
    site_url = "m-team"

    # ★ 7.19.0：馒头是**真·不支持**（官方口径「第三方工具间接存取不算登入」）→ 声明后
    #   signin.py 的「API 鉴权站」短路才生效（如实回报「不支持」，不刷红）。
    api_no_signin = True

    @classmethod
    def match(cls, url: str) -> bool:
        """
        根据站点Url判断是否匹配当前站点签到类，大部分情况使用默认实现即可
        :param url: 站点Url
        :return: 是否匹配，如匹配则会调用该类的signin方法
        """
        return True if cls.site_url in url.split(".") else False

    def signin(self, site_info: CommentedMap) -> Tuple[bool, str]:
        """★ 7.17.0：馒头官方口径「第三方工具间接存取不算登入」→ **不再发**
        ``/member/updateLastBrowse``（实测该端点对 apikey 直接 401
        「Full authentication is required」，旧版不看响应体 → 误报「模拟登录成功」）。
        如实回报「不支持」，保活交给主人用浏览器 / 官方 App 亲自登。
        """
        return False, "馒头不支持登录（站点口径：第三方工具存取不计入登入）"

    def login(self, site_info: CommentedMap) -> Tuple[bool, str]:
        """
        执行登录操作
        :param site_info: 站点信息，含有站点Url、站点Cookie、UA等信息
        :return: 登录结果信息
        """
        return self.signin(site_info)
