# -*- coding: utf-8 -*-
"""魔流 · cloud —— 云盘归档（功能页 + 触发执行）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import threading
from concurrent.futures import wait
from datetime import datetime
from typing import List, Optional


from app.schemas import Response
from app.sdk.logging import logger

from ..fallback import FallbackEngine, DEFAULT_SOURCES as FALLBACK_SOURCES
from ..cloud_archive import ArchiveEngine
from ..persistence import OperationItem


from ..common import (
    FALLBACK_SCAN_MAX,
)


class CloudMixin:
    """cloud 功能集（原 MagicFlow 方法原样搬入）。"""

    def _get_fallback_engine(self) -> FallbackEngine:
        """元数据兜底引擎(惰性创建 + 配置同步)。"""
        engine = getattr(self, "_fallback_engine", None)
        if engine is None:
            engine = self._fallback_engine = FallbackEngine(self, dict(getattr(self, "_fallback_cfg", {}) or {}))
        else:
            engine.set_cfg(dict(getattr(self, "_fallback_cfg", {}) or {}))
        return engine

    # ------------------------------------------------------------------
    # 元数据兜底:定时 worker 与「整理入库后」钩子
    # ------------------------------------------------------------------
    def fallback_scan(self) -> None:
        """定时任务:多源识别 + 给库里缺 NFO 的集补最小 NFO。"""
        cfg = dict(getattr(self, "_fallback_cfg", {}) or {})
        if not bool(cfg.get("enabled", True)):
            return
        if not self._try_begin_run("fallback"):
            self._log("魔流 元数据兜底:上一轮仍在执行,跳过")
            return
        if not self._acquire_worker_slot("元数据兜底"):
            self._end_run("fallback")
            return
        try:
            engine = self._get_fallback_engine()
            report = engine.scan(apply=not bool(cfg.get("dry_run", False)))
            st = report.get("stats") or {}
            self._log(
                f"元数据兜底完成:扫描 {st.get('shows', 0)} 剧 / 识别 {st.get('resolved', 0)} / "
                f"补剧集 NFO {st.get('ep_nfo', 0)} / 补剧 NFO {st.get('show_nfo', 0)} / "
                f"源中缺失 {st.get('missing', 0)} / 归位 {st.get('renumbered', 0)} "
                f"({'演练' if report.get('applied') is False else '已写入'} {report.get('duration')}s)"
            )
            if self._store and (st.get("ep_nfo") or st.get("show_nfo") or st.get("renumbered")):
                items = [OperationItem(
                    hash="", title=t.get("show", ""),
                    reason=(
                        f"识别自 {t.get('resolved') or '未命中'}|补集 {sum(1 for e in t.get('episodes', []) if e.get('nfo'))}|"
                        f"归位 {len(t.get('renumbered') or [])}"
                    ),
                    source="fallback",
                ) for t in (report.get("shows") or [])[:20]]
                self._store.journal.record(
                    task_id="", kind="fallback",
                    items=[OperationItem(
                        hash="", title="元数据兜底",
                        reason=(
                            f"扫描 {st.get('shows', 0)} 剧|识别 {st.get('resolved', 0)}|"
                            f"补集 NFO {st.get('ep_nfo', 0)}|补剧 NFO {st.get('show_nfo', 0)}"
                        ),
                        source="fallback",
                    )] + items,
                    duration=report.get("duration"),
                )
        except Exception as err:  # noqa: BLE001
            import traceback
            logger.error(f"魔流 元数据兜底异常: {err}\n{traceback.format_exc()}")
            self._log(f"魔流 元数据兜底异常:{err}", "warning")
        finally:
            self._release_worker_slot()
            self._end_run("fallback")

    def _fallback_after_import(self, library_hint: str = "") -> None:
        """整理入库后,对该剧做一次定向兜底(异步、去重、限频)。"""
        cfg = dict(getattr(self, "_fallback_cfg", {}) or {})
        if not bool(cfg.get("enabled", True)) or not bool(cfg.get("after_import", True)):
            return
        if not self._try_begin_run("fallback"):
            return
        if not self._acquire_worker_slot("元数据兜底(入库后)"):
            self._end_run("fallback")
            return

        def _worker() -> None:
            try:
                engine = self._get_fallback_engine()
                report = engine.scan(apply=not bool(cfg.get("dry_run", False)))
                st = report.get("stats") or {}
                self._dbg(
                    f"整理入库后兜底(hint={library_hint}):补集 NFO {st.get('ep_nfo', 0)} / "
                    f"补剧 NFO {st.get('show_nfo', 0)}"
                )
            except Exception as err:  # noqa: BLE001
                self._log(f"整理入库后兜底失败(忽略):{err}", "warning")
            finally:
                self._release_worker_slot()
                self._end_run("fallback")

        threading.Thread(target=_worker, name="magicflow-fallback", daemon=True).start()

    # ------------------------------------------------------------------
    # 元数据兜底:API
    # ------------------------------------------------------------------
    def get_fallback_state(self, resolve_paths: bool = False) -> Response:
        """返回元数据兜底配置 + 最近一次结果(可选解析实际扫描目录)。"""
        engine = self._get_fallback_engine()
        cfg = dict(getattr(self, "_fallback_cfg", {}) or {})
        paths: List[str] = list(cfg.get("paths") or [])
        if not paths and resolve_paths:
            try:
                paths = engine.library_paths()
            except Exception as err:  # noqa: BLE001
                self._log(f"解析兜底库目录失败:{err}", "warning")
                paths = []
        running = bool(self._task_runs.get("fallback"))
        return Response(success=True, data={
            "enabled": bool(cfg.get("enabled", True)),
            "sources": list(cfg.get("sources") or FALLBACK_SOURCES),
            "paths": list(cfg.get("paths") or []),
            "effective_paths": paths,
            "interval_minutes": float(cfg.get("interval", 30.0) or 30.0),
            "scan_max": int(cfg.get("scan_max", FALLBACK_SCAN_MAX) or FALLBACK_SCAN_MAX),
            "sp_to_s00": bool(cfg.get("sp_to_s00", False)),
            "after_import": bool(cfg.get("after_import", True)),
            "dry_run": bool(cfg.get("dry_run", False)),
            "running": running,
            "report": engine.last_report(),
        })

    def run_fallback(self, dry_run: Optional[bool] = None) -> Response:
        """立即跑一轮元数据兜底(后台线程;dry_run=true 仅演练不落盘)。"""
        cfg = dict(getattr(self, "_fallback_cfg", {}) or {})
        if not bool(cfg.get("enabled", True)):
            return Response(success=False, message="元数据兜底已关闭,请先在设置里启用")
        apply = not (bool(cfg.get("dry_run", False)) if dry_run is None else bool(dry_run))
        if not self._try_begin_run("fallback"):
            return Response(success=False, message="上一轮兜底仍在执行,请稍后再试")
        if not self._acquire_worker_slot("元数据兜底(手动)"):
            self._end_run("fallback")
            return Response(success=False, message="全局并发已满,请稍后再试")

        def _worker() -> None:
            try:
                engine = self._get_fallback_engine()
                report = engine.scan(apply=apply)
                st = report.get("stats") or {}
                self._log(
                    f"元数据兜底(手动)完成:扫描 {st.get('shows', 0)} 剧 / 补集 NFO {st.get('ep_nfo', 0)} / "
                    f"补剧 NFO {st.get('show_nfo', 0)}({'已写入' if apply else '演练'})"
                )
            except Exception as err:  # noqa: BLE001
                self._log(f"元数据兜底(手动)异常:{err}", "warning")
            finally:
                self._release_worker_slot()
                self._end_run("fallback")

        threading.Thread(target=_worker, name="magicflow-fallback-manual", daemon=True).start()
        return Response(success=True, message="已开始扫描,稍后刷新查看结果", data={"dry_run": not apply})

    def _get_cloud_engine(self) -> ArchiveEngine:
        """取(并刷新配置)云盘归档引擎。"""
        cfg = dict(getattr(self, "_cloud_cfg", {}) or {})
        engine = getattr(self, "_cloud_engine", None)
        if engine is None:
            engine = ArchiveEngine(self, cfg)
            self._cloud_engine = engine
        else:
            engine.set_cfg(cfg)
        return engine

    def _cloud_cfg_view(self) -> dict:
        """给前端看的云盘配置:★ 绝不能带 token(等同密码),只告诉「有没有」。"""
        cfg = dict(getattr(self, "_cloud_cfg", {}) or {})
        cfg["has_token"] = bool(cfg.get("token"))
        cfg.pop("token", None)
        return cfg

    def get_cloud_state(self) -> Response:
        """云盘归档:配置 + 最近计划/结果 + 归档记录。"""
        engine = self._get_cloud_engine()
        cfg = dict(getattr(self, "_cloud_cfg", {}) or {})
        data = engine.state()
        # 配置里回显给前端时抹掉 token(只告诉「有没有」)
        cfg_view = self._cloud_cfg_view()
        # ★ engine.state() 里的 cfg 也带 token,必须一并抹掉(避免把它送回浏览器)
        inner_cfg = data.get("cfg")
        if isinstance(inner_cfg, dict):
            inner_cfg = dict(inner_cfg)
            inner_cfg["has_token"] = bool(inner_cfg.get("token"))
            inner_cfg.pop("token", None)
            data["cfg"] = inner_cfg
        data.update({
            "cfg": cfg_view,
            "enabled": bool(cfg.get("enabled", False)),
            "running": bool(self._task_runs.get("cloud")),
        })
        return Response(success=True, data=data)

    def test_cloud(self) -> Response:
        """云盘归档:连通性自检(看 OpenList 存储与两个挂载点)。"""
        try:
            return Response(success=True, data=self._get_cloud_engine().test())
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))

    def plan_cloud(self, limit: Optional[int] = None) -> Response:
        """云盘归档:生成计划(只读:扫本地 + 查远端,不写不删)。"""
        try:
            return Response(success=True, data=self._get_cloud_engine().plan(limit=limit))
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))

    def upload_cloud(self, path: str = "", dry_run: bool = True, wait: bool = False) -> Response:
        """云盘归档:上传单个文件(默认 dry_run)。

        大文件上传耗时很长,**默认丢后台线程执行**(不阻塞 HTTP 请求);
        前端靠 `/cloud` 里的记录(status=uploading/uploaded/failed)看进度。
        传 `wait=true` 或 `dry_run=true` 时同步返回(演练瞬间完成)。
        """
        engine = self._get_cloud_engine()
        item = engine.make_item(path)
        if not item:
            return Response(success=False, message="文件不存在或不可读(需为容器内可见路径)")
        if dry_run or wait:
            res = engine.upload(item, dry_run=bool(dry_run))
            return Response(success=bool(res.get("ok")) or bool(dry_run),
                            message=str(res.get("message") or ""), data=res)
        busy = getattr(self, "_cloud_uploads", None)
        if busy is None:
            busy = self._cloud_uploads = set()
        key = str(item["path"])
        if key in busy:
            return Response(success=False, message="该文件正在上传中")
        if len(busy) >= 2:
            return Response(success=False, message="已有 2 个文件在上传,请稍后再试")
        busy.add(key)

        def _worker() -> None:
            try:
                res = engine.upload(item, dry_run=False)
                self._log(f"单文件归档{('完成' if res.get('ok') else '失败')}:{item['rel']}"
                          f"({res.get('message') or ''})")
            except Exception as err:  # noqa: BLE001
                self._log(f"单文件归档异常:{err}", "warning")
            finally:
                busy.discard(key)

        threading.Thread(target=_worker, name="magicflow-cloud-put", daemon=True).start()
        return Response(success=True, message=f"已开始上传:{item['name']}",
                        data={**item, "status": "uploading", "ok": True, "message": "已开始上传"})

    def run_cloud(self, limit: Optional[int] = None, dry_run: Optional[bool] = None,
                  delete_local: Optional[bool] = None) -> Response:
        """云盘归档:跑一轮(后台线程;默认按配置:dry_run 开、不删本地)。"""
        cfg = dict(getattr(self, "_cloud_cfg", {}) or {})
        if not bool(cfg.get("enabled", False)):
            return Response(success=False, message="云盘归档未启用,请先在设置里打开")
        dele = bool(cfg.get("delete_local", False)) if delete_local is None else bool(delete_local)
        dry = bool(cfg.get("dry_run", True)) if dry_run is None else bool(dry_run)
        if dele and not dry:
            return Response(success=False, message="已开启「删本地」,为防止误删:请逐条用上传确认后再手动删")
        if not self._try_begin_run("cloud"):
            return Response(success=False, message="上一轮归档仍在执行,请稍后再试")
        if not self._acquire_worker_slot("云盘归档"):
            self._end_run("cloud")
            return Response(success=False, message="全局并发已满,请稍后再试")

        def _worker() -> None:
            try:
                engine = self._get_cloud_engine()
                report = engine.run(limit=limit, dry_run=dry, delete_local=dele)
                st = report.get("stats") or {}
                try:
                    self.save_data(key="cloud_report", value=report)
                except Exception:  # noqa: BLE001
                    pass
                self._log(
                    f"云盘归档完成:计划 {st.get('planned', 0)} / 上传 {st.get('uploaded', 0)} / "
                    f"失败 {st.get('failed', 0)} / 删本地 {st.get('deleted', 0)}"
                    f"({'演练' if dry else '实传'})"
                )
            except Exception as err:  # noqa: BLE001
                self._log(f"云盘归档异常:{err}", "warning")
            finally:
                self._release_worker_slot()
                self._end_run("cloud")

        threading.Thread(target=_worker, name="magicflow-cloud", daemon=True).start()
        return Response(success=True, message="已开始归档,稍后刷新查看结果", data={"dry_run": dry})

    def clear_cloud(self) -> Response:
        """云盘归档:清空归档记录(**不动任何文件**)。"""
        try:
            store = getattr(self._store, "cloud", None)
            n = store.clear() if store is not None else 0
            self.save_data(key="cloud_report", value={})
            return Response(success=True, message=f"已清空 {n} 条归档记录", data={"cleared": n})
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))
