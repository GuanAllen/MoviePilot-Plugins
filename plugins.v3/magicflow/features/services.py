# -*- coding: utf-8 -*-
"""魔流 · services —— 外部服务接入（豆瓣评分服务代理等）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

from datetime import datetime


from app.schemas import Response


class ServicesMixin:
    """services 功能集（原 MagicFlow 方法原样搬入）。"""

    def douban_service_status(self, action: str = "") -> Response:
        """豆瓣评分服务（magicflow-douban）状态：库容量 + 爬虫进度。"""
        try:
            from ..douban import get_client  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"豆瓣模块不可用:{err}")
        cli = get_client(self)
        try:
            st = cli.snapshot_stats()
            crawl = cli.crawl_status()
            if str(action or "").strip().lower() in ("start", "stop", "reset"):
                crawl = cli.crawl_control(action)
            data = {
                "ok": bool(st.get("ok")),
                "service": st.get("service"),
                "records": int(st.get("total") or 0),
                "cache": st.get("cache") or {},
                "errors": st.get("errors") or 0,
                "last_error": st.get("last_error") or "",
                "crawl": crawl,
            }
            return Response(success=True, data=data,
                            message=("豆瓣服务不可用" if not data["ok"] else f"库 {data['records']} 条"))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))
