# -*- coding: utf-8 -*-
"""魔流 · services —— 外部服务接入（豆瓣评分服务代理等）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

from datetime import datetime


from app.schemas import Response


class ServicesMixin:
    """services 功能集（原 MagicFlow 方法原样搬入）。"""

    def get_douban_service(self, action: str = "") -> Response:
        """豆瓣评分服务状态：库容量 + 后台慢爬/详情回填进度。**只读**。

        ★ 19.10.3（整改 S9）：GET 不再承担写语义。
          旧版 ``GET /douban_service?action=start|stop|reset|enrich_*`` 会真启停爬虫、
          真重置评分库 —— 浏览器预抓、代理预取即可触发。写操作现在只接
          ``POST /douban_service``（前端本来就是 POST，零改动）。
          GET 带 action 时**显式拒绝**而非静默降级：静默会让调用方以为写成功了。
        """
        act = str(action or "").strip().lower()
        if act:
            return Response(
                success=False,
                message=f"写操作不接受 GET：请改用 POST /douban_service（action={act}）",
            )
        return self.douban_service_status()

    def post_douban_service(self, action: str = "") -> Response:
        """豆瓣评分服务的**写**操作（只接受 POST）。

        ``action=start|stop|reset`` 控制慢爬；``action=enrich_<子动作>`` 控制详情回填。
        """
        return self.douban_service_status(action=action)

    def douban_service_status(self, action: str = "") -> Response:
        """豆瓣评分服务（magicflow-douban）状态：库容量 + 爬虫进度。

        ★ 保留原名与原签名：``features/agentledger.py`` 把它当**只读**代调用
          （不带 action），改路由不应牵动 agent 侧。
        """
        try:
            from ..douban import get_client  # noqa: WPS433
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"豆瓣模块不可用:{err}")
        cli = get_client(self)
        try:
            st = cli.snapshot_stats()
            crawl = cli.crawl_status()
            enrich = cli.enrich_status()
            act = str(action or "").strip().lower()
            if act in ("start", "stop", "reset"):
                crawl = cli.crawl_control(act)
            elif act.startswith("enrich_"):
                enrich = cli.enrich_control(act[len("enrich_"):])
            data = {
                "ok": bool(st.get("ok")),
                "service": st.get("service"),
                "records": int(st.get("total") or 0),
                "cache": st.get("cache") or {},
                "errors": st.get("errors") or 0,
                "last_error": st.get("last_error") or "",
                "crawl": crawl,
                "enrich": enrich,
            }
            return Response(success=True, data=data,
                            message=("豆瓣服务不可用" if not data["ok"] else f"库 {data['records']} 条"))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))
