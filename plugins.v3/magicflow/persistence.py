"""
MagicFlow 持久化模块

负责操作日志和任务状态的持久化存储。
"""

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ============================================================
# 数据模型
# ============================================================

@dataclass
class OperationItem:
    """操作项（单个种子的操作）。"""
    hash: str
    title: str
    reason: str = ""
    bonus_per_hour: float = 0.0
    size_gb: float = 0.0
    seeders: int = 0
    source: str = ""   # 来源/动作：add/reuse/adopt/tag/watchdog…（供流水明细筛选）
    tags: str = ""     # 标签变更（before→after），仅标签类事件使用


@dataclass
class OperationRecord:
    """操作记录。"""
    operation_id: str
    request_id: str
    task_id: str
    kind: str  # "selection" | "deletion" | "protection" | "unprotection" | "reuse"
    state: str  # "submitting" | "accepted" | "completed" | "failed"
    items: List[OperationItem] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    error_message: Optional[str] = None
    duration: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "kind": self.kind,
            "state": self.state,
            "items": [asdict(item) for item in self.items],
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "error_message": self.error_message,
            "duration": self.duration,
        }

    @staticmethod
    def from_dict(d: dict) -> "OperationRecord":
        items = [OperationItem(**item) for item in d.get("items", [])]
        return OperationRecord(
            operation_id=d["operation_id"],
            request_id=d["request_id"],
            task_id=d["task_id"],
            kind=d["kind"],
            state=d["state"],
            items=items,
            created_at=d.get("created_at", time.time()),
            resolved_at=d.get("resolved_at"),
            error_message=d.get("error_message"),
            duration=d.get("duration"),
        )


@dataclass
class TaskState:
    """任务运行状态。"""
    task_id: str
    last_run_at: float = 0.0
    last_success_at: float = 0.0
    last_error: Optional[str] = None
    cumulative_added: int = 0
    cumulative_deleted: int = 0
    cumulative_kept: int = 0
    cumulative_reused: int = 0
    last_added: int = 0
    last_deleted: int = 0
    last_kept: int = 0
    last_reused: int = 0
    last_run_status: str = ""
    last_run_reason: str = ""
    last_run_duration: float = 0.0
    last_filter_reasons: Dict[str, int] = field(default_factory=dict)
    last_candidate_total: int = 0
    last_candidate_passed: int = 0
    protected_torrents: Set[str] = field(default_factory=set)
    # 每种子发布时间（unix 秒，key=infohash 小写）。用于把 Ti 统一为「发布时长」口径
    # （与候选排序一致），而非 qB 的「做种时长」。取不到时回落做种时长。
    pub_dates: Dict[str, float] = field(default_factory=dict)
    # 发布时间表所用「站点时区偏移（小时）」。与当前口径不一致时旧 pub_dates 作废（需重采）。
    # ⚠️ 必须持久化：否则每次重载后 pub_tz 丢失 → get_pub_dates 误判不匹配 → 返回空 →
    # Ti 回落「做种时长」（远小于发布时长）→ 合计 A / 站点时魔严重偏低。
    pub_tz: float = 0.0
    # 「同站纳管」纳入的种子 hash（本机早已存在的同站种子，非本插件下载）。
    # 这些视为用户自有资源（可能是自己下载的影视资源，而非刷流用），默认保护、不参与删种。
    adopted_hashes: Set[str] = field(default_factory=set)
    # 用户手动「暂停做种」的种子 hash（小写）。这些种子不再被自动恢复（auto_resume_paused）
    # 重新拉起，直到用户在界面上点「恢复做种」或在下载器里手动启动。
    manual_paused: Set[str] = field(default_factory=set)
    enabled: bool = True
    revision: int = 0  # 配置版本号，用于 optimistic locking
    # 运行阶段（供前端「运行诊断」流程链转圈用）
    last_phase: str = ""            # entry|fetch|wash|classify|process|done|error
    last_phase_label: str = ""      # 阶段中文名
    last_phase_detail: str = ""     # 阶段内的细粒度进度（如「取种 14/45」），供前端显示避免「像卡住」
    last_phase_at: float = 0.0
    page_cursor: int = 0            # 站点列表页游标（游标深翻）
    # 种子详情页映射（hash→details 页 URL）。供「检查」时回站点核对促销/免费状态。
    torrent_pages: Dict[str, str] = field(default_factory=dict)
    # 刷流模式：每种子「上传快照」（hash→{up:上次上传字节, idle:连续无上传次数, ts:检查时间}）。
    # 每次检查比对 uploaded 增量；连续 N 次近乎零上传 → 判定「无上传」→ 清理。
    brush_upload: Dict[str, dict] = field(default_factory=dict)
    # 「托管数看门狗」：上一轮观测到的托管（带标签）数。用于检测「种子还在、标签却被抹掉」
    # 这类**不产生删种记录**的异常（托管骤降但本轮删除为 0）。
    last_tagged_count: int = 0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "last_run_at": self.last_run_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "cumulative_added": self.cumulative_added,
            "cumulative_deleted": self.cumulative_deleted,
            "cumulative_kept": self.cumulative_kept,
            "cumulative_reused": self.cumulative_reused,
            "last_added": self.last_added,
            "last_deleted": self.last_deleted,
            "last_kept": self.last_kept,
            "last_reused": self.last_reused,
            "last_run_status": self.last_run_status,
            "last_run_reason": self.last_run_reason,
            "last_run_duration": self.last_run_duration,
            "last_filter_reasons": dict(self.last_filter_reasons),
            "last_candidate_total": self.last_candidate_total,
            "last_candidate_passed": self.last_candidate_passed,
            "protected_torrents": list(self.protected_torrents),
            "pub_dates": dict(self.pub_dates),
            "pub_tz": self.pub_tz,
            "adopted_hashes": list(self.adopted_hashes),
            "manual_paused": list(self.manual_paused),
            "enabled": self.enabled,
            "revision": self.revision,
            "last_phase": self.last_phase,
            "last_phase_label": self.last_phase_label,
            "last_phase_detail": self.last_phase_detail,
            "last_phase_at": self.last_phase_at,
            "page_cursor": self.page_cursor,
            "torrent_pages": dict(self.torrent_pages),
            "brush_upload": {str(k).lower(): dict(v) for k, v in self.brush_upload.items()},
            "last_tagged_count": self.last_tagged_count,
        }

    @staticmethod
    def from_dict(d: dict) -> "TaskState":
        return TaskState(
            task_id=d["task_id"],
            last_run_at=d.get("last_run_at", 0.0),
            last_success_at=d.get("last_success_at", 0.0),
            last_error=d.get("last_error"),
            cumulative_added=d.get("cumulative_added", 0),
            cumulative_deleted=d.get("cumulative_deleted", 0),
            cumulative_kept=d.get("cumulative_kept", 0),
            cumulative_reused=d.get("cumulative_reused", 0),
            last_added=d.get("last_added", 0),
            last_deleted=d.get("last_deleted", 0),
            last_kept=d.get("last_kept", 0),
            last_reused=d.get("last_reused", 0),
            last_run_status=d.get("last_run_status", ""),
            last_run_reason=d.get("last_run_reason", ""),
            last_run_duration=d.get("last_run_duration", 0.0),
            last_filter_reasons=dict(d.get("last_filter_reasons", {}) or {}),
            last_candidate_total=d.get("last_candidate_total", 0),
            last_candidate_passed=d.get("last_candidate_passed", 0),
            protected_torrents=set(d.get("protected_torrents", [])),
            pub_dates={str(k).lower(): float(v) for k, v in (d.get("pub_dates") or {}).items() if v},
            pub_tz=float(d.get("pub_tz", 0.0) or 0.0),
            adopted_hashes=set(d.get("adopted_hashes", []) or []),
            manual_paused=set(d.get("manual_paused", []) or []),
            enabled=d.get("enabled", True),
            revision=d.get("revision", 0),
            last_phase=d.get("last_phase", ""),
            last_phase_label=d.get("last_phase_label", ""),
            last_phase_detail=d.get("last_phase_detail", ""),
            last_phase_at=d.get("last_phase_at", 0.0),
            page_cursor=d.get("page_cursor", 0),
            torrent_pages={str(k).lower(): str(v) for k, v in (d.get("torrent_pages") or {}).items() if k and v},
            brush_upload={str(k).lower(): dict(v) for k, v in (d.get("brush_upload") or {}).items() if k and isinstance(v, dict)},
            last_tagged_count=int(d.get("last_tagged_count", 0) or 0),
        )


# ============================================================
# 操作日志
# ============================================================

class OperationJournal:
    """
    操作日志持久化。

    记录每次刷流操作（选种、删种、保护），支持进程重启后恢复。
    """

    def __init__(self, data_dir: Path):
        """
        初始化操作日志。

        Args:
            data_dir: 插件数据目录
        """
        self.data_dir = data_dir
        self.operations_file = data_dir / "operations.json"
        self._operations: Dict[str, OperationRecord] = {}
        # 每任务保留的最大操作记录数（0 = 不限）。由插件全局设置注入。
        self.keep: int = 0
        # 多个服务（刷流/检查/慢扫）会并发调用 journal；加锁避免
        # 「dictionary changed size during iteration」（add→_prune_task 边遍历边被别的线程改）。
        self._lock = threading.RLock()
        self._load()

    def set_keep(self, keep: int) -> None:
        """设置每个任务保留的最大操作记录数（0 = 不限）。"""
        try:
            self.keep = max(0, int(keep or 0))
        except (TypeError, ValueError):
            self.keep = 0

    def _prune_task(self, task_id: str) -> None:
        """裁剪某任务的历史记录，只保留最新的 keep 条。"""
        if not self.keep:
            return
        with self._lock:
            rows = [op for op in list(self._operations.values()) if op.task_id == task_id]
            if len(rows) <= self.keep:
                return
            rows.sort(key=lambda x: x.created_at, reverse=True)
            for op in rows[self.keep:]:
                self._operations.pop(op.operation_id, None)

    # 状态“完成度”排序：数字越大越接近终态。合并同一记录时保留更新的那份。
    _STATE_RANK = {"submitting": 0, "accepted": 1, "failed": 2, "completed": 2}

    @classmethod
    def _more_final(cls, a: OperationRecord, b: OperationRecord) -> OperationRecord:
        """两条同一 operation_id 的记录，返回更“新/终”的那条。"""
        ra = cls._STATE_RANK.get(a.state, 0)
        rb = cls._STATE_RANK.get(b.state, 0)
        if ra != rb:
            return a if ra > rb else b
        ta = a.resolved_at or 0.0
        tb = b.resolved_at or 0.0
        if ta != tb:
            return a if ta > tb else b
        # 同状态同时间：保留条目更多的那份
        return a if len(a.items or []) >= len(b.items or []) else b

    def _prune_all(self) -> None:
        """按任务裁剪全部历史（merge 后调用，避免已裁剪记录被磁盘旧数据复活）。"""
        if not self.keep:
            return
        by_task: Dict[str, List[OperationRecord]] = {}
        for op in list(self._operations.values()):
            by_task.setdefault(op.task_id, []).append(op)
        for task_id, rows in by_task.items():
            if len(rows) <= self.keep:
                continue
            rows.sort(key=lambda x: x.created_at, reverse=True)
            for op in rows[self.keep:]:
                self._operations.pop(op.operation_id, None)

    def _load(self) -> None:
        """从磁盘加载操作日志。"""
        if not self.operations_file.exists():
            return

        try:
            with open(self.operations_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for op_id, op_dict in data.items():
                    self._operations[op_id] = OperationRecord.from_dict(op_dict)
        except Exception:
            # 如果加载失败，初始化为空
            self._operations = {}

        # 载入时自愈：进程中断/重载遗留的「卡在 submitting」孤儿记录 → 标记为中断
        try:
            self._heal_stale_submitting()
        except Exception:
            pass

    # 超过该秒数仍 submitting 视为孤儿（正常运行 < _task_run_timeout=600s）
    _STALE_SUBMITTING_SEC = 900.0

    def _heal_stale_submitting(self) -> int:
        """把过期仍处于 submitting 的记录标记为「中断」（进程异常/重载未正常收尾）。"""
        now = time.time()
        healed = 0
        with self._lock:
            for op in list(self._operations.values()):
                try:
                    created = float(getattr(op, "created_at", 0) or 0)
                except (TypeError, ValueError):
                    created = 0.0
                if op.state == "submitting" and (now - created) > self._STALE_SUBMITTING_SEC:
                    op.state = "failed"
                    op.resolved_at = now
                    if not getattr(op, "error_message", None):
                        op.error_message = "中断（进程重载或异常，未正常收尾）"
                    healed += 1
            if healed:
                self._save()
        return healed

    def _save(self) -> None:
        """保存操作日志到磁盘。

        采用「与磁盘并集合并」再写回：热重载会同时存在多个插件实例，
        旧实例若用内存快照整表覆盖，会把新实例刚写入的记录覆盖丢失/状态回退。
        合并时同一 operation_id 取更“终态/更新”的那份，保证记录只增不减、状态不倒退。
        """
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            merged: Dict[str, OperationRecord] = {}
            if self.operations_file.exists():
                try:
                    with open(self.operations_file, "r", encoding="utf-8") as f:
                        disk = json.load(f)
                    for op_id, op_dict in disk.items():
                        merged[op_id] = OperationRecord.from_dict(op_dict)
                except Exception:
                    merged = {}
            for op_id, op in self._operations.items():
                if op_id in merged:
                    merged[op_id] = self._more_final(op, merged[op_id])
                else:
                    merged[op_id] = op
            self._operations = merged
            self._prune_all()
            data = {op_id: op.to_dict() for op_id, op in self._operations.items()}
            tmp = self.operations_file.with_name(self.operations_file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.operations_file)
        except Exception:
            pass

    def add(
        self,
        task_id: str,
        kind: str,
        items: Optional[List[OperationItem]] = None,
        request_id: Optional[str] = None,
    ) -> OperationRecord:
        """
        添加一条操作记录。

        Args:
            task_id: 任务 ID
            kind: 操作类型 ("selection" | "deletion" | "protection" | "unprotection")
            items: 操作项列表
            request_id: 请求 ID（可选，用于追踪）

        Returns:
            创建的操作记录
        """
        operation_id = str(uuid.uuid4())[:8]
        request_id = request_id or str(uuid.uuid4())[:8]

        record = OperationRecord(
            operation_id=operation_id,
            request_id=request_id,
            task_id=task_id,
            kind=kind,
            state="submitting",
            items=items or [],
        )

        with self._lock:
            self._operations[operation_id] = record
            self._prune_task(task_id)
            self._save()
        return record

    def record(
        self,
        task_id: str,
        kind: str,
        items: Optional[List[OperationItem]] = None,
        duration: Optional[float] = None,
        state: str = "completed",
        error_message: Optional[str] = None,
    ) -> OperationRecord:
        """直接记录一条已完成的即时操作（选种/删种/保留等），避免停留在 submitting。"""
        record = self.add(task_id=task_id, kind=kind, items=items)
        self.finalize(
            record.operation_id,
            state,
            items=items,
            duration=duration,
            error_message=error_message,
        )
        return record

    def finalize(
        self,
        operation_id: str,
        state: str,
        items: Optional[List[OperationItem]] = None,
        duration: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """完成一条操作记录：写回状态、结果项、耗时。"""
        with self._lock:
            record = self._operations.get(operation_id)
            if not record:
                return False
            record.state = state
            if items is not None:
                record.items = items
            if duration is not None:
                record.duration = round(float(duration), 2)
            if error_message:
                record.error_message = error_message
            record.resolved_at = time.time()
            self._save()
            return True

    def get(self, operation_id: str) -> Optional[OperationRecord]:
        """获取指定操作记录。"""
        return self._operations.get(operation_id)

    def update_state(
        self,
        operation_id: str,
        state: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        更新操作状态。

        Args:
            operation_id: 操作 ID
            state: 新状态 ("submitting" | "accepted" | "completed" | "failed")
            error_message: 错误信息（可选）

        Returns:
            是否更新成功
        """
        record = self._operations.get(operation_id)
        if not record:
            return False

        with self._lock:
            record.state = state
            if state in ("completed", "failed"):
                record.resolved_at = time.time()
            if error_message:
                record.error_message = error_message

            self._save()
        return True

    def list_by_task(
        self,
        task_id: str,
        kind: Optional[str] = None,
        limit: int = 50,
    ) -> List[OperationRecord]:
        """
        获取指定任务的操作记录。

        Args:
            task_id: 任务 ID
            kind: 操作类型过滤（可选）
            limit: 返回数量限制

        Returns:
            操作记录列表（按时间降序）
        """
        records = [
            op for op in list(self._operations.values())
            if op.task_id == task_id and (kind is None or op.kind == kind)
        ]
        records.sort(key=lambda x: x.created_at, reverse=True)
        return records[:limit]

    def list_recent(self, limit: int = 100) -> List[OperationRecord]:
        """获取最近的操作记录。"""
        records = list(self._operations.values())
        records.sort(key=lambda x: x.created_at, reverse=True)
        return records[:limit]

    def delete_old(self, days: int = 30) -> int:
        """
        删除旧的操作记录。

        Args:
            days: 保留天数

        Returns:
            删除的记录数
        """
        cutoff = time.time() - days * 24 * 3600
        with self._lock:
            old_ids = [
                op_id for op_id, op in list(self._operations.items())
                if op.created_at < cutoff
            ]
            for op_id in old_ids:
                del self._operations[op_id]
            if old_ids:
                self._save()
        return len(old_ids)

    def delete_task(self, task_id: str) -> int:
        """删除某任务的全部操作记录（任务被删除时调用，避免残留孤儿数据）。"""
        if not task_id:
            return 0
        with self._lock:
            doomed = [op_id for op_id, op in list(self._operations.items()) if op.task_id == task_id]
            for op_id in doomed:
                self._operations.pop(op_id, None)
            if doomed:
                self._save()
        return len(doomed)


# ============================================================
# 任务状态
# ============================================================

class TaskStateStore:
    """
    任务状态持久化。

    保存每个任务的运行状态、受保护种子列表等。
    """

    def __init__(self, data_dir: Path):
        """
        初始化任务状态存储。

        Args:
            data_dir: 插件数据目录
        """
        self.data_dir = data_dir
        self.state_file = data_dir / "task_states.json"
        self._states: Dict[str, TaskState] = {}
        self._load()

    def _load(self) -> None:
        """从磁盘加载任务状态。"""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for task_id, state_dict in data.items():
                    self._states[task_id] = TaskState.from_dict(state_dict)
        except Exception:
            self._states = {}

    def _save(self) -> None:
        """保存任务状态到磁盘。"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            data = {task_id: state.to_dict() for task_id, state in self._states.items()}
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, task_id: str) -> Optional[TaskState]:
        """获取任务状态。"""
        return self._states.get(task_id)

    def save(self, state: TaskState) -> None:
        """
        保存任务状态。

        Args:
            state: 任务状态对象
        """
        state.revision += 1  # 乐观锁版本号递增
        self._states[state.task_id] = state
        self._save()

    def delete(self, task_id: str) -> bool:
        """删除任务状态。"""
        if task_id in self._states:
            del self._states[task_id]
            self._save()
            return True
        return False

    def list_all(self) -> List[TaskState]:
        """获取所有任务状态。"""
        return list(self._states.values())

    def create(self, task_id: str) -> TaskState:
        """
        创建新任务状态。

        Args:
            task_id: 任务 ID

        Returns:
            新创建的任务状态
        """
        state = TaskState(task_id=task_id)
        self._states[task_id] = state
        self._save()
        return state


# ============================================================
# 已处理候选记录（避免重复拉取同一批种子）
# ============================================================

class SeenStore:
    """
    已处理候选记录。

    站点列表页每次返回的都是同一批最新种子，为避免反复下载/重复添加，
    把处理过的候选（按页面链接 / infohash）记录到磁盘，在窗口期内直接跳过。
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.file = data_dir / "seen.json"
        self._data: Dict[str, Dict[str, float]] = {}
        self._load()

    def _load(self) -> None:
        if not self.file.exists():
            return
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data = loaded
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(self.file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.file)
        except Exception:
            pass

    def is_seen(self, task_id: str, key: str, cooldown_seconds: float = 0.0) -> bool:
        """该 key 是否在窗口期内已被处理过。"""
        if not task_id or not key:
            return False
        ts = (self._data.get(task_id) or {}).get(key)
        if not ts:
            return False
        if cooldown_seconds and (time.time() - ts) > cooldown_seconds:
            return False
        return True

    def get_bucket(self, task_id: str) -> Dict[str, float]:
        """返回某任务的 seen 原始映射（key→时间戳），供外部重建 hash↔页面配对。"""
        if not task_id:
            return {}
        bucket = self._data.get(task_id)
        return dict(bucket) if isinstance(bucket, dict) else {}

    def mark(self, task_id: str, keys: List[str], ts: Optional[float] = None) -> None:
        """记录一批已处理的 key。"""
        if not task_id or not keys:
            return
        ts = ts or time.time()
        bucket = self._data.setdefault(task_id, {})
        changed = False
        for key in keys:
            if key and bucket.get(key) != ts:
                bucket[key] = ts
                changed = True
        if changed:
            self._save()

    def prune(self, max_age_seconds: float) -> None:
        """清掉超过 max_age_seconds 的记录。"""
        if max_age_seconds <= 0:
            return
        cutoff = time.time() - max_age_seconds
        changed = False
        for task_id in list(self._data.keys()):
            bucket = self._data.get(task_id) or {}
            for key in [k for k, v in bucket.items() if v < cutoff]:
                del bucket[key]
                changed = True
            if not bucket:
                del self._data[task_id]
                changed = True
        if changed:
            self._save()

    def count(self, task_id: str) -> int:
        return len(self._data.get(task_id) or {})

    def delete(self, task_id: str) -> bool:
        """删除某任务的全部去重记录（任务被删除时调用，避免残留孤儿数据）。"""
        if not task_id:
            return False
        if self._data.pop(task_id, None) is not None:
            self._save()
            return True
        return False


class DeadStore(SeenStore):
    """
    死种 / 失败缓存。

    与 SeenStore 分属**不同文件**（dead.json / seen.json），从根上避免命名空间串扰
    —— 历史上 seen 与 dead 共用 key 曾导致「自己把自己判死」的 bug。
    典型写入来源：
      - 候选下载失败（404 / 无法获取种子）→ 按候选 key
      - 下载器「无进度」被清理的种子 → 按 infohash
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.file = data_dir / "dead.json"
        self._data: Dict[str, Dict[str, float]] = {}
        self._load()

    def is_dead(self, task_id: str, key: str, cooldown_seconds: float = 0.0) -> bool:
        """该 key 是否在冷却期内被标记为死种。"""
        return self.is_seen(task_id, key, cooldown_seconds)


# ============================================================
# 插件数据存储（高层封装）
# ============================================================

class MagicFlowStore:
    """
    MagicFlow 统一数据存储。

    整合操作日志和任务状态管理。
    """

    def __init__(self, data_dir: Path):
        """
        初始化数据存储。

        Args:
            data_dir: 插件数据目录
        """
        self.data_dir = data_dir
        self.journal = OperationJournal(data_dir)
        self.task_states = TaskStateStore(data_dir)
        self.seen = SeenStore(data_dir)
        self.dead = DeadStore(data_dir)

    # -------------------- 运行阶段 / 游标 --------------------

    def record_phase(self, task_id: str, phase: str, label: str = "", detail: str = "") -> None:
        """记录当前运行阶段（供前端「运行诊断」流程链转圈）。

        detail 为阶段内的细粒度进度（如「取种 14/45」），前端显示以避免长时间无变化「像卡住」。
        """
        if not task_id:
            return
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        state.last_phase = phase or ""
        state.last_phase_label = label or ""
        state.last_phase_detail = detail or ""
        state.last_phase_at = time.time()
        self.task_states.save(state)

    def get_phase(self, task_id: str) -> Dict[str, Any]:
        """读取当前运行阶段。"""
        state = self.task_states.get(task_id)
        if not state:
            return {"last_phase": "", "last_phase_label": "", "last_phase_detail": "", "last_phase_at": 0.0}
        return {
            "last_phase": state.last_phase,
            "last_phase_label": state.last_phase_label,
            "last_phase_detail": state.last_phase_detail,
            "last_phase_at": state.last_phase_at,
        }

    def get_page_cursor(self, task_id: str) -> int:
        state = self.task_states.get(task_id)
        return int(getattr(state, "page_cursor", 0) or 0)

    def set_page_cursor(self, task_id: str, cursor: int) -> None:
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        state.page_cursor = max(int(cursor or 0), 0)
        self.task_states.save(state)

    # -------------------- 种子详情页映射（hash→details URL） --------------------

    def get_torrent_pages(self, task_id: str) -> Dict[str, str]:
        """读取本任务记录的「种子详情页」映射（hash→URL）。"""
        state = self.task_states.get(task_id)
        if not state:
            return {}
        return dict(getattr(state, "torrent_pages", {}) or {})

    def note_torrent_pages(self, task_id: str, mapping: Dict[str, str]) -> None:
        """记录一批「hash→详情页 URL」映射（仅在有值时写入）。"""
        if not task_id or not mapping:
            return
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        pages = state.torrent_pages or {}
        changed = False
        for h, url in mapping.items():
            hs = str(h or "").lower()
            u = str(url or "").strip()
            if hs and u and pages.get(hs) != u:
                pages[hs] = u
                changed = True
        if changed:
            state.torrent_pages = pages
            self.task_states.save(state)

    # -------------------- 刷流：上传快照（无上传清理用） --------------------

    def get_brush_upload(self, task_id: str) -> Dict[str, dict]:
        """读取本任务的「上传快照」表（hash→{up, idle, ts}）。"""
        state = self.task_states.get(task_id)
        if not state:
            return {}
        return {str(k).lower(): dict(v) for k, v in (getattr(state, "brush_upload", {}) or {}).items()}

    def set_brush_upload(self, task_id: str, mapping: Dict[str, dict]) -> None:
        """整体写回「上传快照」表。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        clean = {str(k).lower(): dict(v) for k, v in (mapping or {}).items() if k and isinstance(v, dict)}
        state.brush_upload = clean
        self.task_states.save(state)

    # -------------------- 托管数看门狗 --------------------

    def get_last_tagged_count(self, task_id: str) -> int:
        """读取上一轮记录的托管（带标签）种子数。"""
        state = self.task_states.get(task_id)
        return int(getattr(state, "last_tagged_count", 0) or 0)

    def set_last_tagged_count(self, task_id: str, count: int) -> None:
        """写回本轮托管（带标签）种子数。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        try:
            state.last_tagged_count = max(int(count or 0), 0)
        except (TypeError, ValueError):
            state.last_tagged_count = 0
        self.task_states.save(state)

    # -------------------- 发布时间（Ti 口径校准） --------------------

    def get_pub_dates(self, task_id: str, tz: Optional[float] = None) -> Dict[str, float]:
        """读取本任务记录的「种子发布时间」表（hash→unix 秒）。

        tz：当前使用的站点时区偏移（小时）。与存储时不一致则视为作废（需重采），
        避免时区修正后旧数据继续污染 Ti。
        """
        state = self.task_states.get(task_id)
        if not state:
            return {}
        if tz is not None and abs(float(getattr(state, "pub_tz", 0.0) or 0.0) - float(tz)) > 1e-6:
            return {}
        return dict(getattr(state, "pub_dates", {}) or {})

    def note_pub_dates(self, task_id: str, mapping: Dict[str, float], tz: Optional[float] = None) -> None:
        """记录一批种子的发布时间（仅在有值时写入，不会覆盖为 0）。"""
        if not task_id or not mapping:
            return
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        pd = state.pub_dates or {}
        if tz is not None and abs(float(getattr(state, "pub_tz", 0.0) or 0.0) - float(tz)) > 1e-6:
            # 时区口径变了 → 丢弃旧值重采
            pd = {}
            state.pub_tz = float(tz)
        changed = False
        for h, ts in mapping.items():
            h = str(h or "").lower()
            try:
                ts = float(ts or 0)
            except (TypeError, ValueError):
                continue
            if h and ts > 0 and pd.get(h) != ts:
                pd[h] = ts
                changed = True
        if changed:
            state.pub_dates = pd
            self.task_states.save(state)

    # -------------------- 受保护种子管理 --------------------

    def protect_torrent(self, task_id: str, hash_string: str) -> bool:
        """
        保护一个种子。

        Args:
            task_id: 任务 ID
            hash_string: 种子 hash

        Returns:
            是否成功
        """
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)

        state.protected_torrents.add(hash_string)
        self.task_states.save(state)
        return True

    def unprotect_torrent(self, task_id: str, hash_string: str) -> bool:
        """
        取消保护一个种子。

        Args:
            task_id: 任务 ID
            hash_string: 种子 hash

        Returns:
            是否成功
        """
        state = self.task_states.get(task_id)
        if not state:
            return False

        state.protected_torrents.discard(hash_string)
        self.task_states.save(state)
        return True

    def forget_torrents(self, task_id: str, hashes: Any) -> int:
        """种子已从下载器删除后，清理其「保护 / 同站纳管」记录。

        否则陈旧 hash 会一直留在集合里，导致：
          * 概览「受保护」计数虚高（与实际托管数对不上）；
          * 同一资源重新挂上时不再被纳管/保护（已删记录占位）。

        Args:
            task_id: 任务 ID
            hashes: hash 集合 / 列表

        Returns:
            实际清理的条目数（保护 + 纳管去重后）。
        """
        state = self.task_states.get(task_id)
        if not state:
            return 0
        keys = {
            (h or "").strip().lower()
            for h in (hashes or [])
            if (h or "").strip()
        }
        if not keys:
            return 0
        before = len(state.protected_torrents) + len(getattr(state, "adopted_hashes", set()) or set())
        state.protected_torrents = {
            h for h in state.protected_torrents
            if (h or "").strip().lower() not in keys
        }
        adopted = getattr(state, "adopted_hashes", None)
        if adopted:
            state.adopted_hashes = {
                h for h in adopted
                if (h or "").strip().lower() not in keys
            }
        mp = getattr(state, "manual_paused", None)
        if mp:
            state.manual_paused = {
                h for h in mp
                if (h or "").strip().lower() not in keys
            }
        after = len(state.protected_torrents) + len(getattr(state, "adopted_hashes", set()) or set())
        if before != after:
            self.task_states.save(state)
        return before - after

    def reconcile_protected(self, task_id: str, live_hashes: Any) -> int:
        """把「保护 / 同站纳管」集合与下载器中真实存在的种子对齐。

        下载器里已经没有的种子（被手动删除 / 早期版本误删 / 换客户端）会留下陈旧 hash，
        后果：概览「受保护」计数虚高，且同一资源重新挂上时不会再次被纳管保护。

        Args:
            task_id: 任务 ID
            live_hashes: 下载器当前所有种子的 hash 集合

        Returns:
            清理掉的陈旧条目数。
        """
        state = self.task_states.get(task_id)
        if not state:
            return 0
        live = {
            (h or "").strip().lower()
            for h in (live_hashes or [])
            if (h or "").strip()
        }
        if not live:
            return 0
        before = len(state.protected_torrents) + len(getattr(state, "adopted_hashes", set()) or set())
        state.protected_torrents = {
            h for h in state.protected_torrents
            if (h or "").strip().lower() in live
        }
        adopted = getattr(state, "adopted_hashes", None)
        if adopted:
            state.adopted_hashes = {
                h for h in adopted
                if (h or "").strip().lower() in live
            }
        mp = getattr(state, "manual_paused", None)
        if mp:
            state.manual_paused = {
                h for h in mp
                if (h or "").strip().lower() in live
            }
        after = len(state.protected_torrents) + len(getattr(state, "adopted_hashes", set()) or set())
        if before != after:
            self.task_states.save(state)
        return before - after

    def get_protected_torrents(self, task_id: str) -> Set[str]:
        """
        获取受保护种子集合。

        Args:
            task_id: 任务 ID

        Returns:
            受保护种子 hash 集合
        """
        state = self.task_states.get(task_id)
        if not state:
            return set()
        return state.protected_torrents.copy()

    # -------------------- 手动暂停 / 恢复 --------------------

    def get_manual_paused(self, task_id: str) -> Set[str]:
        """获取用户手动暂停的种子 hash 集合（小写）。"""
        state = self.task_states.get(task_id)
        if not state:
            return set()
        return set(getattr(state, "manual_paused", set()) or set())

    def mark_manual_paused(self, task_id: str, hashes: Any) -> int:
        """记录用户手动暂停的种子（不再自动恢复）。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        keys = {(h or "").strip().lower() for h in (hashes or []) if (h or "").strip()}
        if not keys:
            return 0
        before = len(state.manual_paused)
        state.manual_paused |= keys
        if len(state.manual_paused) != before:
            self.task_states.save(state)
        return len(state.manual_paused) - before

    def clear_manual_paused(self, task_id: str, hashes: Any) -> int:
        """取消「手动暂停」标记（用户点恢复，或种子已不在下载器里）。"""
        state = self.task_states.get(task_id)
        if not state:
            return 0
        keys = {(h or "").strip().lower() for h in (hashes or []) if (h or "").strip()}
        if not keys:
            return 0
        before = len(state.manual_paused)
        state.manual_paused = {h for h in state.manual_paused if (h or "").strip().lower() not in keys}
        if len(state.manual_paused) != before:
            self.task_states.save(state)
        return before - len(state.manual_paused)

    # -------------------- 同站纳管 --------------------

    def get_adopted(self, task_id: str) -> Set[str]:
        """获取「同站纳管」纳入的种子 hash 集合（用户自有资源）。"""
        state = self.task_states.get(task_id)
        if not state:
            return set()
        return set(getattr(state, "adopted_hashes", set()) or set())

    def note_adopted(self, task_id: str, hashes: List[str]) -> int:
        """记录新纳入的「同站纳管」种子 hash（持久化）。返回本次新增数量。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        before = len(state.adopted_hashes)
        for h in hashes:
            hs = (h or "").lower()
            if hs:
                state.adopted_hashes.add(hs)
        if len(state.adopted_hashes) != before:
            self.task_states.save(state)
        return len(state.adopted_hashes) - before

    def is_self_added(self, task_id: str, hash_string: str) -> bool:
        """该 hash 是否为本插件自己下载/复用的种子（seen 记录，兼容新旧 key 前缀）。"""
        h = (hash_string or "").lower()
        if not h or not task_id:
            return False
        return bool(
            self.seen.is_seen(task_id, f"hash:{h}", 0.0)
            or self.seen.is_seen(task_id, f"h:{h}", 0.0)
        )

    # -------------------- 任务运行记录 --------------------

    def record_run_start(self, task_id: str) -> None:
        """记录任务开始运行。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)

        state.last_run_at = time.time()
        state.last_error = None
        self.task_states.save(state)

    def record_run_success(
        self,
        task_id: str,
        added: int = 0,
        deleted: int = 0,
        kept: int = 0,
        reused: int = 0,
    ) -> None:
        """记录任务成功运行。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)

        state.last_success_at = time.time()
        state.last_error = None
        state.cumulative_added += added
        state.cumulative_deleted += deleted
        state.cumulative_reused += reused
        # cumulative_kept 语义是「当前托管快照」，不再累加，避免失控膨胀
        state.cumulative_kept = kept
        state.last_added = added
        state.last_deleted = deleted
        state.last_reused = reused
        state.last_kept = kept
        self.task_states.save(state)

    def record_filter_stats(
        self,
        task_id: str,
        reasons: Optional[Dict[str, int]] = None,
        total: int = 0,
        passed: int = 0,
    ) -> None:
        """记录最近一次刷流的候选过滤情况（供「过滤原因」展示）。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        state.last_filter_reasons = dict(reasons or {})
        state.last_candidate_total = int(total)
        state.last_candidate_passed = int(passed)
        self.task_states.save(state)

    def record_run_summary(self, task_id: str, status: str, reason: str = "", duration: float = 0.0) -> None:
        """记录最近一次刷流的状态、原因与耗时。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        state.last_run_status = status or ""
        state.last_run_reason = reason or ""
        state.last_run_duration = round(float(duration or 0.0), 2)
        self.task_states.save(state)

    def record_run_error(self, task_id: str, error: str) -> None:
        """记录任务运行错误。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)

        state.last_error = error
        self.task_states.save(state)

    def get_task_stats(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务统计信息。

        Args:
            task_id: 任务 ID

        Returns:
            统计信息字典
        """
        state = self.task_states.get(task_id)
        if not state:
            return {
                "task_id": task_id,
                "last_run_at": None,
                "last_success_at": None,
                "last_error": None,
                "cumulative_added": 0,
                "cumulative_deleted": 0,
                "cumulative_kept": 0,
                "cumulative_reused": 0,
                "last_added": 0,
                "last_deleted": 0,
                "last_kept": 0,
                "last_reused": 0,
                "last_run_status": "",
                "last_run_reason": "",
                "last_run_duration": 0.0,
                "last_filter_reasons": {},
                "last_candidate_total": 0,
                "last_candidate_passed": 0,
                "protected_count": 0,
                "last_phase": "",
                "last_phase_label": "",
                "last_phase_detail": "",
                "last_phase_at": 0.0,
                "page_cursor": 0,
            }

        return {
            "task_id": task_id,
            "last_run_at": state.last_run_at,
            "last_success_at": state.last_success_at,
            "last_error": state.last_error,
            "cumulative_added": state.cumulative_added,
            "cumulative_deleted": state.cumulative_deleted,
            "cumulative_kept": state.cumulative_kept,
            "cumulative_reused": state.cumulative_reused,
            "last_added": state.last_added,
            "last_deleted": state.last_deleted,
            "last_kept": state.last_kept,
            "last_reused": state.last_reused,
            "last_run_status": state.last_run_status,
            "last_run_reason": state.last_run_reason,
            "last_run_duration": state.last_run_duration,
            "last_filter_reasons": dict(state.last_filter_reasons),
            "last_candidate_total": state.last_candidate_total,
            "last_candidate_passed": state.last_candidate_passed,
            "protected_count": len(state.protected_torrents),
            "last_phase": state.last_phase,
            "last_phase_label": state.last_phase_label,
            "last_phase_detail": state.last_phase_detail,
            "last_phase_at": state.last_phase_at,
            "page_cursor": state.page_cursor,
        }


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("MagicFlow 持久化模块测试")
    print("=" * 60)

    # 使用临时目录测试
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "magicflow"
        store = MagicFlowStore(data_dir)

        task_id = "test_task_001"

        # 测试保护种子
        print("\n1. 测试保护种子：")
        store.protect_torrent(task_id, "hash_001")
        store.protect_torrent(task_id, "hash_002")
        protected = store.get_protected_torrents(task_id)
        print(f"   受保护种子: {protected}")

        # 测试取消保护
        print("\n2. 测试取消保护：")
        store.unprotect_torrent(task_id, "hash_001")
        protected = store.get_protected_torrents(task_id)
        print(f"   取消后受保护种子: {protected}")

        # 测试操作日志
        print("\n3. 测试操作日志：")
        record = store.journal.add(
            task_id=task_id,
            kind="deletion",
            items=[
                OperationItem(hash="hash_003", title="test.torrent", reason="魔力低"),
                OperationItem(hash="hash_004", title="test2.torrent", reason="零魔"),
            ],
        )
        print(f"   创建操作记录: {record.operation_id}")

        store.journal.update_state(record.operation_id, "completed")
        print(f"   更新状态为 completed")

        records = store.journal.list_by_task(task_id, kind="deletion")
        print(f"   任务删除记录数: {len(records)}")

        # 测试任务统计
        print("\n4. 测试任务统计：")
        store.record_run_start(task_id)
        store.record_run_success(task_id, added=5, deleted=3, kept=10)
        stats = store.get_task_stats(task_id)
        print(f"   任务统计: {stats}")

        # 测试任务状态
        print("\n5. 测试任务状态持久化（模拟重启）：")
        store2 = MagicFlowStore(data_dir)  # 重新加载
        protected2 = store2.get_protected_torrents(task_id)
        print(f"   重启后受保护种子: {protected2}")
        stats2 = store2.get_task_stats(task_id)
        print(f"   重启后任务统计: {stats2}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
