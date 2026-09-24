"""
MagicFlow 持久化模块

负责操作日志和任务状态的持久化存储。
"""

import json
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
    enabled: bool = True
    revision: int = 0  # 配置版本号，用于 optimistic locking
    # 运行阶段（供前端「运行诊断」流程链转圈用）
    last_phase: str = ""            # entry|fetch|wash|classify|process|done|error
    last_phase_label: str = ""      # 阶段中文名
    last_phase_at: float = 0.0
    page_cursor: int = 0            # 站点列表页游标（游标深翻）

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
            "enabled": self.enabled,
            "revision": self.revision,
            "last_phase": self.last_phase,
            "last_phase_label": self.last_phase_label,
            "last_phase_at": self.last_phase_at,
            "page_cursor": self.page_cursor,
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
            enabled=d.get("enabled", True),
            revision=d.get("revision", 0),
            last_phase=d.get("last_phase", ""),
            last_phase_label=d.get("last_phase_label", ""),
            last_phase_at=d.get("last_phase_at", 0.0),
            page_cursor=d.get("page_cursor", 0),
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
        self._load()

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

    def _save(self) -> None:
        """保存操作日志到磁盘。"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            data = {op_id: op.to_dict() for op_id, op in self._operations.items()}
            with open(self.operations_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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

        self._operations[operation_id] = record
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
            op for op in self._operations.values()
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
        old_ids = [
            op_id for op_id, op in self._operations.items()
            if op.created_at < cutoff
        ]
        for op_id in old_ids:
            del self._operations[op_id]

        if old_ids:
            self._save()

        return len(old_ids)


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

    def record_phase(self, task_id: str, phase: str, label: str = "") -> None:
        """记录当前运行阶段（供前端「运行诊断」流程链转圈）。"""
        if not task_id:
            return
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        state.last_phase = phase or ""
        state.last_phase_label = label or ""
        state.last_phase_at = time.time()
        self.task_states.save(state)

    def get_phase(self, task_id: str) -> Dict[str, Any]:
        """读取当前运行阶段。"""
        state = self.task_states.get(task_id)
        if not state:
            return {"last_phase": "", "last_phase_label": "", "last_phase_at": 0.0}
        return {
            "last_phase": state.last_phase,
            "last_phase_label": state.last_phase_label,
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
