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

中断与重试（★ 19.12.96）
------------------------
执行体是闭包，**不可能持久化** —— 落盘的只有 ``kind`` 与 ``params``。所以插件重载时
queued/running 只能标成 failed（「任务中断」），靠 ``jobs_retry`` 按 ``kind`` + ``params``
重建执行体重新入队。
两条配套的硬要求：
1. ``queued/running`` 的记录**永不截断**（只截已完成/失败的历史）——不然大批量整理
   一重载，被截掉的连「被打断」都看不见；
2. 重试前先核当前状态（落点已回来就别再重建），见 ``_job_retry_asset``。

批量聚合与自动复原（★ 19.12.97）
--------------------------------
**批量聚合**：一次批量 = N 条互不相干的 job，面板上只是一长串，看不出「这批一共多少、
成不成、还能不能救」。``submit(batch_id=...)`` 给同一次操作打上同一个批次号，
``jobs_batches`` 按批次聚成一行，口径必须能加回总数：
``total == queued + running + done + failed`` 且 ``failed == retryable + dead``。

**自动复原**：19.12.96 的重试口能用了，但还得人去点。插件启动后
``jobs_resume_interrupted`` 自动把**排队中被打断**的任务重新入队，不需要人盯。
``running`` 被打断的**故意不自动重放**：MP 重载不 join daemon 线程，旧线程可能还在跑，
重放会让两次整理同时动同一颗资源（后果是多出一份副本，正好踩在「已整理过」的判据盲区上）。
宁可让那几条躺着等人看一眼 —— 它们本来就已经是「失败 + 可重试」。
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
    # ★ 19.12.0：音乐散曲入库（读标签 → 硬链接进库 → 触发媒体库扫描）
    "music_import": "音乐入库",
}

KEEP_MAX = 100                      # 队列里最多留多少条记录
KEEP_DONE_SECONDS = 2 * 86400       # 已完成的记录保留 2 天

#: ★ 19.12.97 自动复原：启动后等多久再动手。
#: 等的是两件事 —— MP 运行时（store / 下载器 / 账单）就绪，以及**旧线程收尾**。
#: 太早上来就重放，会在 MP 各存储还没绑好时跑整理，失败一轮反而把「可重试」用掉。
JOBS_RESUME_DELAY = 90

#: 自动复原单次最多重放多少条。正常批量是几百条、本来就要跑几小时，
#: 这个上限只用来挡住「异常大数量」把启动瞬间打爆。
JOBS_RESUME_MAX = 500

#: 同一条任务被自动复原超过这个次数就不再自动重放（防「一跑就崩」的任务无限循环）。
JOBS_RESUME_MAX_TIMES = 3



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
                    # ★ 19.12.97：留住**中断前**的状态。自动复原只重放 queued 的那些 ——
                    #   running 被打断时旧线程可能还活着（MP 重载不 join daemon 线程），
                    #   此时重放会让两次整理同时动同一颗。
                    row["interrupted_from"] = str(row.get("status"))
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
                # ★ 19.12.96：只截「已完成/失败」的历史，``queued/running`` **永不丢**。
                #   原来这里是 ``sorted(...)[-KEEP_MAX:]`` —— 不看状态无差别截断。
                #   批量整理 295 条时，jobs.json 只留最后 100 条；一旦插件重载，
                #   被截掉的那 195 条连「被打断」的记录都没有，用户在面板上
                #   根本看不出自己少跑了多少。实测 150 条入队 → 落盘只剩 100 条。
                live = [r for r in self._jobs.values()
                        if str(r.get("status")) in ("queued", "running")]
                hist = [r for r in self._jobs.values()
                        if str(r.get("status")) not in ("queued", "running")]
                hist.sort(key=lambda x: float(x.get("created") or 0))
                # live 不设上限：能留在 queued/running 的就是这次真在排队的活，
                # 条数等于一次批量的规模（几百封顶），体积可忽略；丢了才是真信息损失。
                rows = live + hist[-KEEP_MAX:]
                rows.sort(key=lambda x: float(x.get("created") or 0))
            tmp = str(self._path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(rows, fh, ensure_ascii=False)
            import os as _os
            _os.replace(tmp, str(self._path))
        except Exception as err:  # noqa: BLE001
            logger.warning(f"魔流 后台任务记录写入失败（忽略）：{err}")

    # ---------------------------------------------------------------- 提交/执行
    def submit(self, kind: str, title: str, fn: Callable[[], Any],
               dedup_key: str = "", params: Optional[Dict[str, Any]] = None,
               retry_of: str = "", batch_id: str = "") -> Dict[str, Any]:
        """入队并立刻返回任务记录（``dedup_key`` 命中在跑的同类任务 → 返回既有那条）。

        ``retry_of``（★ 19.12.96）= 从哪条失败任务重试来的（空 = 全新任务）。
        ``batch_id``（★ 19.12.97）= 本次批量操作的批次号；同一批的每条任务都带同一个值，
        面板据此把它们聚成一行（``jobs_batches``）。空 = 不属于任何批次。
        """
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
                # ★ 19.12.96：重试来源（面板/接口据此把「第 N 次重试」串起来）
                "retry_of": str(retry_of or ""),
                # ★ 19.12.97：批次号（空 = 单条操作，不进批次汇总）
                "batch_id": str(batch_id or ""),
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

    def get(self, jid: str) -> Optional[Dict[str, Any]]:
        """按 id 取一条任务记录（找不到返回 ``None``）。"""
        self._load()
        with self._lock:
            row = self._jobs.get(str(jid or "").strip())
            return dict(row) if row else None

    def note_retried(self, jid: str, new_jid: str) -> None:
        """在失败记录上标「已被哪条重试」，免得同一批失败被反复重放。"""
        self._load()
        with self._lock:
            row = self._jobs.get(str(jid or "").strip())
            if row is None:
                return
            row["retried_by"] = str(new_jid or "")
        self._save()

    def mark(self, jid: str, **fields: Any) -> None:
        """★ 19.12.97：在记录上补字段（自动复原标记等）。值给 ``None`` 表示删掉该字段。"""
        self._load()
        with self._lock:
            row = self._jobs.get(str(jid or "").strip())
            if row is None:
                return
            for k, v in (fields or {}).items():
                if v is None:
                    row.pop(str(k), None)
                else:
                    row[str(k)] = v
        self._save()

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
                    dedup_key: str = "", params: Optional[Dict[str, Any]] = None,
                    batch_id: str = "") -> Dict[str, Any]:
        return self._job_queue().submit(kind=kind, title=title, fn=fn,
                                        dedup_key=dedup_key, params=params,
                                        batch_id=batch_id)

    @staticmethod
    def _job_new_batch() -> str:
        """★ 19.12.97：生成批次号 —— 同一次批量操作里的每条任务共用它。

        只给「一次点了多条」的场景用；单条操作留空，免得面板上多出一行
        只有一条的批次噪音。
        """
        return uuid.uuid4().hex[:12]

    # ---------------------------------------------------------------- 批次汇总
    def _job_retryable(self, row: Dict[str, Any]) -> bool:
        """这条失败任务**现在**能不能重建执行体（纯判定，不构造闭包）。"""
        kind = str(row.get("kind") or "")
        key = self._REPLAY_KINDS.get(kind)
        if not key:
            return False
        return bool(str(dict(row.get("params") or {}).get(key) or "").strip())

    def _job_batches(self, limit: int = 20) -> List[Dict[str, Any]]:
        """★ 19.12.97：按 ``batch_id`` 把同一次批量操作聚成一行。

        批量 295 条在面板上是一长串，用户看不出「这批一共多少、成了多少、
        剩下多少还能救」—— 逐条看永远对不上总数，这正是我们反复踩的形态。

        口径（必须能加回总数）：
        ``total == queued + running + done + failed`` 且
        ``failed == retryable + dead``（``retryable`` = 现在还能重建执行体）。
        """
        try:
            rows = self._job_queue().list(limit=1000)
        except Exception:  # noqa: BLE001
            return []
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            bid = str(row.get("batch_id") or "")
            if bid:
                groups.setdefault(bid, []).append(row)
        out: List[Dict[str, Any]] = []
        for bid, items in groups.items():
            queued = sum(1 for r in items if str(r.get("status")) == "queued")
            running = sum(1 for r in items if str(r.get("status")) == "running")
            done = sum(1 for r in items if str(r.get("status")) == "done")
            failed = sum(1 for r in items if str(r.get("status")) == "failed")
            retryable = sum(1 for r in items
                            if str(r.get("status")) == "failed" and self._job_retryable(r))
            kind = str(items[0].get("kind") or "")
            out.append({
                "batch_id": bid,
                "kind": kind,
                "kind_text": KIND_TEXT.get(kind, kind),
                "total": len(items),
                "queued": queued,
                "running": running,
                "done": done,
                "failed": failed,
                "retryable": retryable,
                "dead": failed - retryable,
                "created": min(float(r.get("created") or 0) for r in items),
                # 全部落定才有结束时间（还有在跑的就不算这批结束）
                "finished": (max(float(r.get("finished") or 0) for r in items)
                             if not queued and not running else 0.0),
            })
        out.sort(key=lambda x: float(x.get("created") or 0), reverse=True)
        return out[:max(1, int(limit or 20))]

    # ---------------------------------------------------------------- API
    def jobs_list(self, limit: int = 50) -> Response:
        """★ 15.10.0：后台任务列表（页面关掉也在跑，回来这里看进度/结果）。

        ★ 19.12.97：``data.batches`` 是按批次聚合的汇总（一次批量一行）。

        ★ 19.12.98：每条附 ``retryable``（现在还能不能重建执行体）。前端据此决定
        要不要给这颗显示「重试」按钮 —— 判据必须在后端，前端自己维护一份 kind
        白名单必然和 ``_REPLAY_KINDS`` 漂开，那就会出现「点了没反应」的按钮。
        """
        try:
            q = self._job_queue()
            rows = q.list(limit=int(limit or 50))
            for row in rows:
                # 已完成的没有重试语义；只对 failed 标「能不能救」
                row["retryable"] = (str(row.get("status")) == "failed"
                                    and self._job_retryable(row))
            s = q.summary()
            return Response(
                success=True,
                message=f"后台任务 {len(rows)} 条（进行中 {s['running'] + s['queued']}）",
                data={"items": rows, "summary": s, "batches": self._job_batches()},
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

    # ---------------------------------------------------------------- 重试
    #: 可重试的任务种类 → ``params`` 里**必须**带的定位键。
    #: **删除类（``asset_delete``）故意不在表内**：删一半再重放要重过四道闸门
    #: （手动保留 / 跨站来源份 / 已认领 / 欠 H&R），「一键重删」的风险与收益不对称，
    #: 让用户回界面重新确认一次才安全。
    _REPLAY_KINDS: Dict[str, str] = {
        "asset_protect": "resource_id",
        "asset_unprotect": "resource_id",
        "asset_subscribe": "resource_id",
        "asset_unsubscribe": "resource_id",
        "asset_organize": "resource_id",
        "asset_scrape": "resource_id",
        "music_import": "hash",
        "recommend_import": "hash",
    }

    def _job_replay_fn(self, job: Dict[str, Any]) -> Optional[Callable[[], Any]]:
        """按任务记录重建执行体；返回 ``None`` = 该任务不可重试。

        执行体（闭包）本身不可能持久化 —— 落盘的只有 ``kind`` 与 ``params``。
        能重放的前提是这两样足够重建执行体：资源动作靠 ``resource_id``，
        音乐/推荐靠 ``hash``。缺任何一样就老实说「不可重试」，别猜。
        """
        kind = str(job.get("kind") or "")
        if not self._job_retryable(job):
            return None
        key = self._REPLAY_KINDS.get(kind) or ""
        params = dict(job.get("params") or {})
        val = str(params.get(key) or "").strip()
        if kind.startswith("asset_"):
            action = kind[len("asset_"):]
            return lambda: self._job_retry_asset(action, params)
        if kind == "music_import":
            h = val.lower()
            return lambda: self._music_import_run(h)
        if kind == "recommend_import":
            h = val.lower()
            return lambda: self._recommend_import_job(h)
        return None

    def jobs_retry(self, job_id: str = "", kind: str = "",
                   batch_id: str = "", limit: int = 0) -> Response:
        """★ 19.12.96 重试失败的后台任务（``job_id`` 单条 / ``batch_id`` 一批 / ``kind`` 按种类）。

        在此之前，重启中断的任务只会在面板上留一句「插件重启，任务中断（可重试）」，
        而**后端根本没有重试口** —— 那句话是空头承诺，用户只能自己回列表
        一格格重新勾选，还未必记得是哪几条。

        口径：
        - 只受理 ``status=failed`` 的任务（在跑 / 已完成的重试没有意义）；
        - 删除类（``asset_delete``）不在 ``_REPLAY_KINDS`` 里，会进 ``skipped``
          并说明原因；
        - ``job_id`` / ``batch_id`` / ``kind`` 都不给 → 直接拒绝，不做「手一抖全量重放」；
        - 优先级 ``job_id`` > ``batch_id`` > ``kind``：三者同时给时只按最精确的那个办；
        - **``batch_id`` 是「重试本批失败的」的正确口径**（★ 19.12.98）：按 ``kind`` 会把
          别的批次、别的时间段的同类失败一起捞进来，用户在批次行上点「重试本批」
          期待的是这一批；
        - 沿用原任务的 ``dedup_key``：同一颗还在跑时再点会返回既有那条
          （``dedup=True``），不会叠出第二个整理；
        - ``submitted + skipped == total``，统计行对得上账。
        """
        try:
            q = self._job_queue()
            jid = str(job_id or "").strip()
            kd = str(kind or "").strip()
            bid = str(batch_id or "").strip()
            if not jid and not kd and not bid:
                return Response(
                    success=False,
                    message="需指定 job_id（重试一条）、batch_id（重试一批）"
                            "或 kind（按种类批量重试），不支持全量重放")
            if jid:
                row = q.get(jid)
                if row is None:
                    return Response(success=False, message=f"未找到任务 {jid}")
                targets = [row]
            elif bid:
                rows = q.list(limit=1000)
                targets = [r for r in rows
                           if str(r.get("batch_id") or "") == bid
                           and str(r.get("status")) == "failed"]
                targets.sort(key=lambda x: float(x.get("created") or 0))
                if int(limit or 0) > 0:
                    targets = targets[: int(limit)]
                if not targets:
                    return Response(success=False,
                                    message="这一批没有失败的任务（可能刚被重试过）")
            else:
                rows = q.list(limit=1000)
                targets = [r for r in rows
                           if str(r.get("kind") or "") == kd
                           and str(r.get("status")) == "failed"]
                targets.sort(key=lambda x: float(x.get("created") or 0))
                if int(limit or 0) > 0:
                    targets = targets[: int(limit)]
                if not targets:
                    if kd not in self._REPLAY_KINDS:
                        return Response(
                            success=False,
                            message=f"{kd} 不支持重试（删除类请回界面重新确认）")
                    return Response(success=False, message=f"没有失败的「{kd}」任务")
            submitted: List[Dict[str, Any]] = []
            skipped: List[Dict[str, Any]] = []
            for row in targets:
                old = str(row.get("id") or "")
                st = str(row.get("status") or "")
                kds = str(row.get("kind") or "")
                if st != "failed":
                    skipped.append({"job_id": old, "kind": kds,
                                    "why": f"状态是「{st}」，不是失败"})
                    continue
                fn = self._job_replay_fn(row)
                if fn is None:
                    why = ("该种类不支持重试（删除类请回界面重新确认）"
                           if kds not in self._REPLAY_KINDS
                           else "任务记录缺少定位键（旧的入队代码没存），无法重建")
                    skipped.append({"job_id": old, "kind": kds, "why": why})
                    continue
                try:
                    job = q.submit(
                        kind=kds,
                        title="重试：" + str(row.get("title") or ""),
                        fn=fn,
                        dedup_key=str(row.get("dedup_key") or ""),
                        params=dict(row.get("params") or {}),
                        retry_of=old,
                        # ★ 19.12.97：重试出来的任务留在原批次里，汇总才对得上
                        batch_id=str(row.get("batch_id") or ""),
                    )
                except Exception as err:  # noqa: BLE001
                    skipped.append({"job_id": old, "kind": kds,
                                    "why": f"入队失败：{err}"})
                    continue
                new = str(job.get("id") or "")
                if not job.get("dedup"):
                    q.note_retried(old, new)
                submitted.append({"job_id": old, "new_job_id": new, "kind": kds,
                                  "title": str(row.get("title") or ""),
                                  "dedup": bool(job.get("dedup"))})
            total = len(targets)
            msg = f"重试：已入队 {len(submitted)}/{total} 条"
            if skipped:
                msg += f"，跳过 {len(skipped)} 条（{skipped[0]['why']}）"
            return Response(
                success=bool(submitted),
                message=msg,
                data={"ok": len(submitted), "total": total,
                      "submitted": submitted, "skipped": skipped},
            )
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))

    # ---------------------------------------------------------------- 自动复原
    def jobs_resume_interrupted(self, max_items: int = 0) -> Dict[str, Any]:
        """★ 19.12.97：把「排队中被中断」的任务自动重新入队（不需要人点）。

        19.12.96 只是把重试口做出来了，还得有人去点 —— 发一版、批量跑到一半，
        剩下的就躺在那儿等人想起来。这里补上「自动接上」。

        只碰 ``interrupted_from == "queued"`` 的：
        - ``queued`` 一定没开始跑 → 重放安全；
        - ``running`` 被打断时**旧线程可能还在跑**（MP 重载不 join daemon 线程），
          此时重放会让两次整理同时动同一颗资源，后果是多出一份副本 —— 正好踩在
          「已整理过」那个判据盲区上。所以 running 的**故意不自动重放**，
          它们本来就是「失败 + 可重试」，用户看一眼再点更安全。

        幂等与防循环：
        - 重放后在原记录打 ``auto_resumed_at``，同一条不会被反复重放；
        - ``auto_resume_n`` 会**继承到新记录**，超过 ``JOBS_RESUME_MAX_TIMES``
          不再自动跑（防「一跑就把插件搞崩」的任务在每次启动时循环）。
        """
        out: Dict[str, Any] = {"ok": 0, "total": 0, "skipped": 0, "over": 0}
        try:
            q = self._job_queue()
            rows = q.list(limit=1000)
        except Exception as err:  # noqa: BLE001
            out["error"] = str(err)
            return out
        cap = int(max_items or JOBS_RESUME_MAX)
        targets: List[Dict[str, Any]] = []
        for row in rows:
            if str(row.get("status")) != "failed":
                continue
            if str(row.get("interrupted_from") or "") != "queued":
                continue
            if row.get("auto_resumed_at"):
                continue
            if int(row.get("auto_resume_n") or 0) >= JOBS_RESUME_MAX_TIMES:
                out["skipped"] += 1
                continue
            if not self._job_retryable(row):
                out["skipped"] += 1
                continue
            targets.append(row)
        targets.sort(key=lambda x: float(x.get("created") or 0))
        out["total"] = len(targets)
        if len(targets) > cap:
            out["over"] = len(targets) - cap
            targets = targets[:cap]
        for row in targets:
            old = str(row.get("id") or "")
            n = int(row.get("auto_resume_n") or 0) + 1
            fn = self._job_replay_fn(row)
            if fn is None:
                out["skipped"] += 1
                continue
            try:
                job = q.submit(
                    kind=str(row.get("kind") or ""),
                    title="续跑：" + str(row.get("title") or ""),
                    fn=fn,
                    dedup_key=str(row.get("dedup_key") or ""),
                    params=dict(row.get("params") or {}),
                    retry_of=old,
                    batch_id=str(row.get("batch_id") or ""),
                )
            except Exception as err:  # noqa: BLE001
                logger.warning(f"魔流 自动复原入队失败 {old}：{err}")
                out["skipped"] += 1
                continue
            new = str(job.get("id") or "")
            # 原记录：打标记，别再被扫到（dedup 命中也算「已处理」）
            q.mark(old, auto_resumed_at=time.time(), resumed_by=new)
            if new and not job.get("dedup"):
                # 新记录：继承次数，供下次中断时判「还该不该自动跑」
                q.mark(new, auto_resume_n=n)
                out["ok"] += 1
            else:
                out["skipped"] += 1
        return out

    def _job_schedule_resume(self) -> None:
        """★ 19.12.97：启动后延迟**一次**自动复原（``init_plugin`` 末尾调）。

        为什么要延迟：MP 刚起来时 store / 下载器 / 账单可能都还没绑好，
        这时候跑整理只会失败一轮，白白把「可重试」用掉。
        """
        if getattr(self, "_jobs_resume_scheduled", False):
            return
        self._jobs_resume_scheduled = True

        def _later() -> None:
            try:
                time.sleep(JOBS_RESUME_DELAY)
                r = self.jobs_resume_interrupted()
                _n = int(r.get("ok") or 0)
                _t = int(r.get("total") or 0)
                # ★ 铁律 8：**无论有没有救到东西都留一句** ——「跑了但没救到」与
                #   「压根没跑」在日志里必须长得不一样。19.11.10 就栽在这上面：
                #   只在「摘除数 > 0」时记日志，结果「跑了但一条没摘」和「没跑」
                #   完全无法区分，残留挂了好几天才被发现。
                self._log(
                    f"后台任务:自动复原 检查 {_t} 条中断任务 / 重放 {_n} 条"
                    f" / 跳过 {int(r.get('skipped') or 0)} 条", "info")
                if int(r.get("over") or 0):
                    self._log(f"后台任务:还有 {r['over']} 条超出单次上限未自动复原，"
                              f"可在「后台任务」面板重试", "warning")
            except Exception as err:  # noqa: BLE001
                logger.warning(f"魔流 后台任务自动复原失败（忽略）：{err}")

        threading.Thread(target=_later, name="magicflow-jobs-resume",
                         daemon=True).start()
