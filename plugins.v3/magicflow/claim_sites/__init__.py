# -*- coding: utf-8 -*-
"""魔流 · 认领写动作适配器注册表。

认领是**写动作**（站点侧会改状态、可能扣魔力），所以**不进** `collect` 的浏览缓存
（`collect.Http` 只有 GET）。这里照 ``signin_sites/`` 的模式：每站一个处理器模块，
类里声明 ``site_url`` + ``match(url)`` + ``claim(site_info, torrent_id, profile)``；
``find(url)`` 按域名匹配，未命中则该站视为「暂不支持认领」。

返回口径统一为 ``(ok: bool, status: str, message: str)``，``status`` 取值：

    ok          认领成功
    already     站点侧显示「已认领」（幂等：当成功处理，只补账本）
    full        名额已满（本种不再可认领）
    unmet       不满足认领条件（未到期 / 不达标 …）
    unsupported 该站/该模板不支持此动作（放弃认领等）
    fail        其它失败（网络 / 登录失效 …）

★ 写操作风控：调用方（``features/claim.py``）负责**限速 + 每日配额 + 失败冷却**；
这里只管「发一次请求 + 如实解析」，不重试。
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from abc import ABCMeta, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from app.log import logger
from app.utils.http import RequestUtils
from app.utils.string import StringUtils


class ClaimSiteHandler(metaclass=ABCMeta):
    """站点认领处理器基类。"""

    # 匹配的站点 Url（各实现类自行设置）
    site_url = ""

    @abstractmethod
    def match(self, url: str) -> bool:
        """根据站点 Url 判断是否匹配当前处理器。"""
        return bool(StringUtils.url_equal(url, self.site_url))

    @abstractmethod
    def claim(self, site_info: Dict[str, Any], torrent_id: Any, profile: Dict[str, Any]) -> Tuple[bool, str, str]:
        """执行认领 → (成功?, 状态码, 文案)。"""
        raise NotImplementedError

    def abandon(self, site_info: Dict[str, Any], torrent_id: Any, profile: Dict[str, Any]) -> Tuple[bool, str, str]:
        """放弃认领（默认：无接口模板 → unsupported，绝不猜）。"""
        return False, "unsupported", "该站未提供「放弃认领」接口模板，未执行"

    # ---------------------------------------------------------------- 工具
    @staticmethod
    def subst(tpl: Any, torrent_id: Any = None, uid: Any = None) -> Any:
        """把 endpoint/body 模板里的 ``{id}`` / ``{uid}`` 递归替换掉。"""
        if isinstance(tpl, dict):
            return {k: ClaimSiteHandler.subst(v, torrent_id, uid) for k, v in tpl.items()}
        if isinstance(tpl, list):
            return [ClaimSiteHandler.subst(v, torrent_id, uid) for v in tpl]
        if isinstance(tpl, str):
            out = tpl
            if "{id}" in out:
                out = out.replace("{id}", str(torrent_id if torrent_id is not None else ""))
            if "{uid}" in out:
                out = out.replace("{uid}", str(uid if uid is not None else ""))
            return out
        return tpl

    @staticmethod
    def site_base(site_info: Dict[str, Any]) -> str:
        base = str(site_info.get("url") or site_info.get("domain") or "").strip()
        if base and not base.startswith("http"):
            base = "https://" + base
        return base.rstrip("/")

    def post_endpoint(
        self,
        site_info: Dict[str, Any],
        profile: Dict[str, Any],
        torrent_id: Any,
        endpoint: Optional[Dict[str, Any]] = None,
        uid: Any = None,
    ) -> Tuple[bool, str, str]:
        """按 profile 的 ``endpoint`` 模板发一次写请求 → (成功?, 状态码, 原文)。

        只用 ``RequestUtils``（带站点 cookie / UA / 代理），与签到一致；不重试。
        """
        ep = endpoint or (profile or {}).get("endpoint") or {}
        path = str(ep.get("path") or "").strip()
        if not path:
            return False, "unsupported", "缺少接口模板（endpoint.path）"
        base = self.site_base(site_info)
        url = base + (path if path.startswith("/") else "/" + path)
        method = str(ep.get("method") or "POST").upper()
        body = self.subst(ep.get("body"), torrent_id=torrent_id, uid=uid)
        cookie = str(site_info.get("cookie") or "")
        ua = str(site_info.get("ua") or "")
        proxy = bool(site_info.get("proxy"))
        timeout = int(site_info.get("timeout") or 20)
        proxies = None
        if proxy:
            try:
                from app.core.config import settings as _settings  # noqa: WPS433

                proxies = _settings.PROXY
            except Exception:  # noqa: BLE001
                proxies = None
        try:
            req = RequestUtils(
                cookies=cookie,
                ua=ua,
                proxies=proxies,
                timeout=timeout,
                referer=base + "/",
            )
            if method == "POST":
                if isinstance(body, dict):
                    res = req.post_res(url, json=body)
                else:
                    res = req.post_res(url, params=body or None)
            else:
                res = req.get_res(url=url)
            if res is None:
                return False, "fail", "请求无响应（连通性 / 登录态？）"
            text = (res.text or "")[:2000]
            code = int(getattr(res, "status_code", 0) or 0)
            if code in (401, 403):
                return False, "fail", f"HTTP {code}：Cookie 失效或无权限"
            return self.parse_result(text, code)
        except Exception as err:  # noqa: BLE001
            return False, "fail", f"请求异常：{err}"

    # ---------------------------------------------------------------- 解析
    @staticmethod
    def parse_result(text: str, code: int = 200) -> Tuple[bool, str, str]:
        """解析站点返回（JSON 优先，退回关键词），→ (成功?, 状态码, 文案)。"""
        raw = (text or "").strip()
        low = raw.lower()
        msg = raw[:300]
        # 1) JSON
        if raw.startswith("{") or raw.startswith("["):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    msg = str(data.get("message") or data.get("msg") or data.get("data") or raw)[:300]
                    ok_flag = data.get("success")
                    if ok_flag is None:
                        ok_flag = data.get("ret")
                    if ok_flag is None:
                        ok_flag = data.get("status")
                    if ok_flag is None:
                        ok_flag = data.get("code")
                    if ok_flag is True or str(ok_flag).lower() in ("1", "true", "success", "ok", "200", "0"):
                        return True, "ok", msg
                    st, why = ClaimSiteHandler.classify_text(str(data))
                    return False, st, str(data.get("message") or data.get("msg") or why)[:300]
            except Exception:  # noqa: BLE001
                pass
        # 2) 关键词
        st, why = ClaimSiteHandler.classify_text(low)
        if st == "already":
            return True, "already", why
        if st != "ok":
            return False, st, why
        if code == 200 and not low:
            return False, "fail", "空响应"
        return True, "ok", msg

    @staticmethod
    def classify_text(text: str) -> Tuple[str, str]:
        """按关键词判断站点返回语义（中英兼顾）。"""
        t = str(text or "")
        low = t.lower()
        if "已认领" in t or "已经认领" in t or "already claim" in low:
            return "already", "站点侧已认领（幂等）"
        if ("名额" in t and ("满" in t or "没有" in t or "无" in t or "不足" in t)) or "full" in low:
            return "full", "认领名额已满"
        if "登录" in t or "login" in low or "cookie" in low:
            return "fail", "登录态失效"
        if "不满足" in t or "不满" in t or "未达标" in t or "条件" in t or "未到期" in t or "时间" in t:
            return "unmet", "不满足认领条件（未到期 / 未达标）"
        if "成功" in t or "success" in low or "ok" in low:
            return "ok", "成功"
        return "fail", (t[:200] or "未知响应")


# ---------------------------------------------------------------- 注册表
_HANDLERS: Optional[List[type]] = None


def handlers() -> List[type]:
    """扫描本包下所有处理器类。"""
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
            logger.error(f"认领处理器加载失败 {name}：{err}")
            continue
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and obj is not ClaimSiteHandler
                and hasattr(obj, "match")
                and hasattr(obj, "claim")
            ):
                out.append(obj)
    _HANDLERS = out
    logger.info(f"[认领] 已加载站点写动作处理器 {len(out)} 个")
    return out


def find(url: str) -> Optional[type]:
    """按站点 Url 匹配处理器，未命中返回 None。"""
    for cls in handlers():
        try:
            if cls.match(str(url or "")):
                return cls
        except Exception:  # noqa: BLE001
            continue
    return None


def domains() -> List[str]:
    """已支持写动作的站点域名列表。"""
    return sorted({str(getattr(c, "site_url", "") or "") for c in handlers() if getattr(c, "site_url", "")})
