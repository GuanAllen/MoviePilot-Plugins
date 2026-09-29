"""魔流 · 站点签到专用处理器注册表。

架构借鉴 MoviePilot「站点自动签到」插件（thsrite / autosignin, GPL-3.0）：
每个站点一个处理器模块，类里声明 ``site_url`` + ``match(url)`` + ``signin(site_info)``；
``find(url)`` 按域名匹配，命中则走专用逻辑，否则由 ``signin.py`` 的通用兜底处理。

处理器来自 autosignin ``sites/`` 目录（同协议移植，导入路径已适配本插件）。
"""

from __future__ import annotations

import importlib
import pkgutil
from abc import ABCMeta, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.helper.browser import PlaywrightHelper
from app.log import logger
from app.utils.http import RequestUtils
from app.utils.string import StringUtils


class SiteSigninHandler(metaclass=ABCMeta):
    """站点签到处理器基类（与 autosignin ``_ISiteSigninHandler`` 同协议）。"""

    # 匹配的站点 Url（各实现类自行设置）
    site_url = ""

    @abstractmethod
    def match(self, url: str) -> bool:
        """根据站点 Url 判断是否匹配当前处理器。"""
        return bool(StringUtils.url_equal(url, self.site_url))

    @abstractmethod
    def signin(self, site_info: Dict[str, Any]) -> Tuple[bool, str]:
        """执行签到，返回 (是否成功, 结果文案)。"""
        raise NotImplementedError

    def login(self, site_info: Dict[str, Any]) -> Tuple[bool, str]:
        """模拟登录（默认与签到同义，站点需要区分时自行覆盖）。"""
        return self.signin(site_info)

    # ---------------------------------------------------------------- 工具
    @staticmethod
    def get_page_source(
        url: str,
        cookie: str,
        ua: str,
        proxy: bool,
        render: bool,
        token: str = None,
        timeout: int = None,
    ) -> str:
        """抓页面源码（render=True 走浏览器渲染，可过 Cloudflare）。"""
        if render:
            return PlaywrightHelper().get_page_source(
                url=url,
                cookies=cookie,
                ua=ua,
                proxies=settings.PROXY_SERVER if proxy else None,
                timeout=timeout or 60,
            )
        if token:
            headers = {"Authorization": token, "User-Agent": ua}
        else:
            headers = {"User-Agent": ua, "Cookie": cookie}
        res = RequestUtils(
            headers=headers,
            proxies=settings.PROXY if proxy else None,
            timeout=timeout or 20,
        ).get_res(url=url)
        if res is not None:
            raw_data = res.content
            if raw_data:
                try:
                    import chardet

                    encoding = chardet.detect(raw_data)["encoding"]
                    return raw_data.decode(encoding)
                except Exception as err:  # noqa: BLE001
                    logger.error(f"chardet 解码失败：{err}")
                    return res.text
            return res.text
        return ""

    @staticmethod
    def sign_in_result(html_res: str, regexs: list) -> bool:
        """按正则列表判断是否签到成功。"""
        import re

        html_text = re.sub(r"#\d+", "", re.sub(r"\d+px", "", html_res or ""))
        for regex in regexs:
            if re.search(str(regex), html_text):
                return True
        return False


# ---------------------------------------------------------------- 注册表
_HANDLERS: Optional[List[type]] = None


def handlers() -> List[type]:
    """扫描本包下所有处理器类（有 match/signin 即注册）。"""
    global _HANDLERS
    if _HANDLERS is not None:
        return _HANDLERS
    out: List[type] = []
    for mod in pkgutil.iter_modules(__path__):
        name = mod.name
        if name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f".{name}", __package__)
        except Exception as err:  # noqa: BLE001
            logger.error(f"签到处理器加载失败 {name}：{err}")
            continue
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and obj is not SiteSigninHandler
                and hasattr(obj, "match")
                and hasattr(obj, "signin")
            ):
                out.append(obj)
    _HANDLERS = out
    logger.info(f"[签到] 已加载站点专用处理器 {len(out)} 个")
    return out


def find(url: str) -> Optional[type]:
    """按站点 Url 匹配专用处理器，未命中返回 None。"""
    for cls in handlers():
        try:
            if cls.match(str(url or "")):
                return cls
        except Exception:  # noqa: BLE001
            continue
    return None


def domains() -> List[str]:
    """已支持站点域名列表（报表/诊断用）。"""
    return sorted({str(getattr(c, "site_url", "") or "") for c in handlers() if getattr(c, "site_url", "")})
