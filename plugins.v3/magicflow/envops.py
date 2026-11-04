# -*- coding: utf-8 -*-
"""魔流 · envops —— 外部环境能力的唯一出口（插件日志 / MP 站点清单 / MP 下载器清单）。

为什么单独一层
--------------
这五项原本都长在 ``features/core.py`` 里：core 是「生命周期 + 调度」的服务层 mixin，
却同时寄居着「怎么访问 MoviePilot 外部世界」的实现。全库对它们的跨文件 ``self._``
调用 673 次（``_log`` 532 / ``_dbg`` 58 / ``_get_site`` 52 / ``_list_sites`` 29 /
``_list_downloaders`` 2），而 core.py 自己几乎不调 —— 基础设施寄居服务层的典型，
同 19.10.19 把 ``_get_downloader`` 下沉到 ``downloader_ops.acquire``。

本模块只回答「环境长什么样」：写日志、查站点、查下载器。**不含业务判断**
（站点该不该刷、任务该不该跑，由调用方的领域层判）。

边界
----
· ``host`` = 插件实例（49 个 mixin 共享的那个 ``self``），只用来读 ``_debug_log`` /
  ``_site_fallback_note`` 两个状态位、写回降级标记；本模块不持有插件状态。
· 只 import 标准库，不 import ``features.*``（本层在下、服务层在上），无循环导入。
· ``app.*`` 一律**函数内延迟导入**：本模块要能在没有 app 桩的离线测试里加载
  （写成顶部 import 会让十几个离线测试在 import 阶段集体崩，同 ``tags.py`` 的做法）。
· ``features/core.py`` 只留一行委托，**673 处调用点零改动**（仍是 ``self._log()``）。
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger("magicflow")

# 插件日志统一前缀：前端日志页与 grep 都按它筛
LOG_PREFIX = "魔流:"

# MoviePilot 插件级 logger 的进程级缓存（见 _mp_logger）
_MP_LOGGER = None


def _mp_logger():
    """取 MoviePilot 的插件级 logger（写进插件日志页）；离线环境回落本模块 logger。

    必须延迟取：``app.sdk.logging`` 只在 MP 运行时存在，顶部 import 会让离线测试
    在 import 阶段就崩，而这五个函数都不值得为它付这个代价。
    """
    global _MP_LOGGER
    if _MP_LOGGER is None:
        try:
            from app.sdk.logging import logger as mp_logger
        except Exception:  # noqa: BLE001
            mp_logger = logger
        _MP_LOGGER = mp_logger
    return _MP_LOGGER


def log(message: str, level: str = "info") -> None:
    """写一条带「魔流:」前缀的插件日志。

    ``level`` 收任意字符串：logging 上没有同名方法就回落 info —— 历史上传过拼错的
    等级，直接 ``getattr`` 会抛 AttributeError 把业务主流程打断。
    """
    lg = _mp_logger()
    text = f"{LOG_PREFIX}{message}"
    getattr(lg, level if hasattr(lg, level) else "info")(text)


def debug(host: Any, message: str) -> None:
    """调试日志：仅在全局「调试日志」开关（``host._debug_log``）打开时输出。"""
    if getattr(host, "_debug_log", False):
        log(f"[调试] {message}")


def get_site(host: Any, site_id: int):
    """按站点 ID 取 MoviePilot 的站点对象；取不到记一条 error 并返回 None。

    返回的是 MP 的 Site 模型（含 cookie / passkey），调用方不得回显或落盘明文。
    """
    try:
        from app.db.oper.site import SiteOper
        return SiteOper().get(site_id)
    except Exception as err:  # noqa: BLE001
        log(f"获取站点失败: {err}", "error")
        return None


def list_sites(host: Any) -> List[Dict[str, Any]]:
    """列出可选站点（SitesHelper 优先，空表/异常回落 MP 站点登记表 SiteOper）。

    ``SitesHelper().get_indexers()`` 依赖 MP「用户认证」（``auth_level >= 2``）：
    认证失效时它返回空表，站点清单、任务编辑器下拉、站点报表选择器会一起空掉。
    MP 的站点登记表（``app.db.oper.site.SiteOper``）不过这道闸门，故作为回落
    ——与 ``features/reseed.py:158 _reseed_mp_sites`` 同口径。

    回落告警按「状态变化」去重（``host._site_fallback_note``）：本函数被多条 worker
    线每轮调用，不去重会把日志刷爆（同 15.8.9 的告警去重思路）。
    """
    out: List[Dict[str, Any]] = []
    try:
        from app.sdk.network import SitesHelper
        for item in SitesHelper().get_indexers() or []:
            if not isinstance(item, dict):
                continue
            dom = str(item.get("domain") or "").strip().lower()
            sid = item.get("id")
            if sid is None and not dom:
                continue
            out.append({
                "id": sid,
                "name": item.get("name") or dom or "",
                "domain": dom,
            })
    except Exception as err:  # noqa: BLE001
        log(f"列出站点失败: {err}", "error")
    if out:
        host._site_fallback_note = False  # 认证恢复 → 下次回落重新告警
        return out
    noted = bool(getattr(host, "_site_fallback_note", False))
    try:
        from app.db.oper.site import SiteOper
        for site in SiteOper().list() or []:
            dom = str(getattr(site, "domain", "") or "").strip().lower()
            sid = getattr(site, "id", None)
            if sid is None and not dom:
                continue
            out.append({
                "id": sid,
                "name": getattr(site, "name", "") or dom,
                "domain": dom,
            })
        if not noted:
            log(f"站点清单回落站点登记表: {len(out)} 个", "warning")
    except Exception as err:  # noqa: BLE001
        if not noted:
            log(f"列出站点失败（站点登记表回落也失败）: {err}", "error")
    host._site_fallback_note = True
    return out


# ============================================================
# 站点官方 API 入口（★ 19.11.5）
# ============================================================
# 背景：2026-11-02 HDDolby 换域名（hddolby.com → uhddolby.com），官方 API 也从
# ``api.<域名>`` 搬到主站 —— ``api.uhddolby.com`` 已无解析，实测
# ``https://www.uhddolby.com/api/v1/user/data`` 带 apikey 返 200。
# 这一层只登记「域名 → API 根」，换域名时改一张表即可；调用点不再各自拼 ``api.``。
_HD_API_BASE = {
    "uhddolby.com": "https://www.uhddolby.com",
    "hddolby.com": "https://www.uhddolby.com",   # 旧域名别名（历史台账/缓存里仍有）
}


def hd_api_base(site: Any = None, domain: str = "") -> str:
    """HDDolby 类站点官方 API 根（不含 ``/api/v1``）。

    优先级：**登记表** > 站点自身 URL（MP 站点配置里就是真实入口）>
    ``https://api.<域名>``（老站口径）。
    登记表排在 URL 前面，是因为换域名后 MP 里可能还留着旧 URL，按域名判最稳。
    """
    dom = str(domain or getattr(site, "domain", "") or "").strip().lower()
    for key, base in _HD_API_BASE.items():
        if dom == key or dom.endswith("." + key):
            return base
    url = str(getattr(site, "url", "") or "").strip().rstrip("/")
    if url:
        return url
    return f"https://api.{dom}" if dom else ""


def list_downloaders(host: Any) -> List[Dict[str, Any]]:
    """列出可选下载器（MP 已配置的下载器名；一个都取不到就给出两个常见项兜底）。"""
    out: List[Dict[str, Any]] = []
    try:
        from app.sdk.services import DownloaderHelper
        configs = DownloaderHelper().get_configs() or {}
        for name in configs.keys():
            out.append({"title": str(name), "value": str(name)})
    except Exception as err:  # noqa: BLE001
        log(f"列出下载器失败: {err}", "error")
    if not out:
        out = [
            {"title": "qBittorrent", "value": "qbittorrent"},
            {"title": "Transmission", "value": "transmission"},
        ]
    return out
