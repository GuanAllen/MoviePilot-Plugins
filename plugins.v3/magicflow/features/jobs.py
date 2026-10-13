# -*- coding: utf-8 -*-
"""魔流 · jobs —— 后台任务队列（★ 15.10.0）。

Master 2026-10-11：「转圈圈这里，如果我关掉页面是不是就断了，建议加个队列后台跑，
这样让用户等体验不好；推荐那里入库也是这个情况」→ 慢动作（整理入库 / 订阅 / 刮削 /
批量删除…）一律**入队后台跑**：前端立刻拿到 job id，页面关掉/刷新都不影响
（任务跑在插件进程里），结果到「后台任务」面板看。

设计
----
- 每个插件实例一个 ``JobQueue``；任务记录持久化到插件数据目录 ``jobs.json``（重启后仍可查）；
- 提交即返回；执行用 ``threading.Thread(daemon=True)``（与插件既有后台 worker 同款）；
- 全局并发上限 ``CONCURRENCY=2``——MP 的整理/订阅/刮削都是重活，别把站点和磁盘打爆；
- 幂等：同 ``dedup_key`` 的 queued/running 任务不重复入队（直接返回既有那条）。
"""

import json
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from app.sdk.logging import logger

from app.schemas import Response

#: 任务种类 → 中文名（前端/通知里显示用）
KIND_TEXT: Dict[str, str] = {
    "asset_protect": "保护",
    "asset_unprotect": "取消保护",
    "asset_subscribe": "订阅整季",
    "asset_unsubscribe": "退订",
    "asset_organize": "整理入库",
    "asset_scrape": "重新刮削",
    "asset_delete": "删除库内资源",
    "recommend_import": "整理入库",
    "recommend_batch_import": "批量整理入库",
    "recommend_dismiss": "忽略并删除",
}

KEEP_MAX = 100                      # 队列里最多留多少条记录
KEEP_DONE_SECONDS = 2 * 86400       # 已完成的记录保留 2 天


class JobQueue:
    """线程安全的后台任务队列（记录落 JSON）。"""

    def __init__(self, path: Optional[Any] = None, concurrency: int = 2) -> None:
        self._path = path
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._sem = threading.Semaphore(max(1, int(concurrency or 1)))
        self._loaded = False

    # ---------------------------------------------------------------- 持久化
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path:
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                rows = json.load(fh) or []
            now = time.time()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                jid = str(row.get("id") or "")
                if not jid:
                    continue
                # 重启后不可能还在跑：把 running/queued 标成「中断」
                if str(row.get("status")) in ("running", "queued"):
                    row["status"] = "failed"
                    row["message"] = "插件重启，任务中断（可重试）"
                    row["finished"] = float(row.get("finished") or now)
                if str(row.get("status")) in ("done", "failed") and \
                        now - float(row.get("finished") or now) > KEEP_DONE_SECONDS:
                    continue
                self._jobs[jid] = row
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流 后台任务记录读取失败（忽略）：{err}")

    def _save(self) -> None:
        if not self._path:
            return
        try:
            with self._lock:
                rows = sorted(self._jobs.values(), key=lambda x: float(x.get("created") or 0))
                rows = rows[-KEEP_MAX:]
            tmp = str(self._path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(rows, fh, ensure_ascii=False)
            import os as _os
            _os.replace(tmp, str(self._path))
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流 后台任务记录写入失败（忽略）：{err}")

    # ---------------------------------------------------------------- 提交/执行
    def submit(self, kind: str, title: str, fn: Callable[[], Any],
               dedup_key: str = "", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """入队并立刻返回任务记录（``dedup_key`` 命中在跑的同类任务 → 返回既有那条）。"""
        self._load()
        with self._lock:
            if dedup_key:
                for row in self._jobs.values():
                    if (str(row.get("dedup_key") or "") == dedup_key
                            and str(row.get("status")) in ("queued", "running")):
                        return dict(row, dedup=True)
            jid = uuid.uuid4().hex[:12]
            job: Dict[str, Any] = {
                "id": jid,
                "kind": str(kind or "job"),
                "kind_text": KIND_TEXT.get(str(kind or ""), str(kind or "任务")),
                "title": str(title or ""),
                "params": dict(params or {}),
                "dedup_key": str(dedup_key or ""),
                "status": "queued",
                "message": "排队中",
                "created": time.time(),
                "started": 0.0,
                "finished": 0.0,
                "result": None,
            }
            self._jobs[jid] = job
            self._trim()
        self._save()
        threading.Thread(target=self._run, args=(jid, fn), name=f"magicflow-job-{jid}",
                         daemon=True).start()
        return dict(job)

    def _run(self, jid: str, fn: Callable[[], Any]) -> None:
        with self._sem:
            with self._lock:
                job = self._jobs.get(jid)
                if job is None:
                    return
                job["status"] = "running"
                job["started"] = time.time()
                job["message"] = "执行中…"
            self._save()
            ok, msg, result = True, "完成", None
            try:
                out = fn()
                if isinstance(out, tuple) and len(out) >= 2:
                    ok, msg = bool(out[0]), str(out[1] or "")
                    result = out[2] if len(out) > 2 else None
                elif isinstance(out, str):
                    msg = out
                elif out is not None:
                    result = out
                if not msg:
                    msg = "完成" if ok else "未生效"
            except Exception as err:  # noqa: BLE001
                ok, msg = False, f"执行异常：{err}"
                logger.warning(f"魔流 后台任务 {jid} 失败：{err}")
            with self._lock:
                job = self._jobs.get(jid) or {}
                job["status"] = "done" if ok else "failed"
                job["message"] = str(msg)[:300]
                job["result"] = result
                job["finished"] = time.time()
            self._save()

    # ---------------------------------------------------------------- 查询
    def _trim(self) -> None:
        if len(self._jobs) <= KEEP_MAX:
            return
        rows = sorted(self._jobs.values(), key=lambda x: float(x.get("created") or 0))
        for row in rows[: len(self._jobs) - KEEP_MAX]:
            if str(row.get("status")) in ("done", "failed"):
                self._jobs.pop(str(row.get("id") or ""), None)

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        self._load()
        with self._lock:
            rows = sorted(self._jobs.values(),
                          key=lambda x: float(x.get("created") or 0), reverse=True)
            return [dict(r) for r in rows[: max(1, int(limit or 50))]]

    def summary(self) -> Dict[str, int]:
        self._load()
        with self._lock:
            rows = list(self._jobs.values())
        return {
            "total": len(rows),
            "queued": sum(1 for r in rows if str(r.get("status")) == "queued"),
            "running": sum(1 for r in rows if str(r.get("status")) == "running"),
            "done": sum(1 for r in rows if str(r.get("status")) == "done"),
            "failed": sum(1 for r in rows if str(r.get("status")) == "failed"),
        }

    def clear_done(self) -> int:
        with self._lock:
            gone = [k for k, v in self._jobs.items()
                    if str(v.get("status")) in ("done", "failed")]
            for k in gone:
                self._jobs.pop(k, None)
        self._save()
        return len(gone)


class JobsMixin:
    """后台任务队列的 mixin 入口（所有动作共用）。"""

    def _job_queue(self) -> JobQueue:
        q = getattr(self, "_jobs_queue", None)
        if q is None:
            try:
                path = self.get_data_path() / "jobs.json"
            except Exception:  # noqa: BLE001
                path = None
            q = JobQueue(path)
            self._jobs_queue = q
        return q

    def _job_submit(self, kind: str, title: str, fn: Callable[[], Any],
                    dedup_key: str = "", params: Optional[Dict[str, Any]] = None
                    ) -> Dict[str, Any]:
        return self._job_queue().submit(kind=kind, title=title, fn=fn,
                                        dedup_key=dedup_key, params=params)

    # ---------------------------------------------------------------- API
    def jobs_list(self, limit: int = 50) -> Response:
        """★ 15.10.0：后台任务列表（页面关掉也在跑，回来这里看进度/结果）。"""
        try:
            q = self._job_queue()
            rows = q.list(limit=int(limit or 50))
            return Response(
                success=True,
                message=f"后台任务 {len(rows)} 条（进行中 {q.summary()['running'] + q.summary()['queued']}）",
                data={"items": rows, "summary": q.summary()},
            )
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))

    def jobs_clear(self) -> Response:
        """清掉「已完成 / 失败」的后台任务记录（在跑的不动）。"""
        try:
            n = self._job_queue().clear_done()
            return Response(success=True, message=f"已清理 {n} 条历史任务")
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))
