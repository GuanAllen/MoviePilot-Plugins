"""
MagicFlow 持久化模块

负责操作日志和任务状态的持久化存储。

★ 存储分层（Master 2026-09-27 09:11 定的方案）：
  · **Redis = 在线热存储**（增量写，快）；
  · **JSON 文件 = 冷备份**，只用于「Redis 数据丢了以后重载恢复」，后台每 60s 落一次；
  · **Redis 不可用 → 完全退回文件模式**（默认装机不装 Redis 也照跑）。
实现方式：各 Store 的 `_save()` 变成「先写 Redis（增量），失败/不可用才写文件」，
文件写入由 `MagicFlowStore` 的后台 flusher（或 stop 时）统一触发。
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

# JSON 冷备份落盘间隔（秒）：Redis 热层负责在线读写，文件只作重载恢复
# 冷备份落盘间隔（秒）。热层才是在线权威；JSON 只用于「Redis 丢了/没装」时恢复。
# 60s 太密（活跃时 5~6 张表每分钟都脏 → 每分钟 5~6 次全量表 dump，反而比增量写便宜不了多少，
# 实测 63MB/h）。改成 5 分钟：丢掉最多 5 分钟的 seen/dead 记忆，无副作用。
KV_FILE_FLUSH_SEC = 300.0
# 热层「载入后未改动」哨兵值：跳过逐条 JSON 指纹重算（加载提速的关键）
_IN_SYNC = "\x00in-sync"

# ★ 跨热重载共享的进程级容器（放独立模块，MP 不会清它）
_SHARED_KEY = "__magicflow_shared__"


def _shared():
    """取/建跨热重载共享容器：单例注册表 + 计数器。"""
    import sys as _sys
    import types as _types

    mod = _sys.modules.get(_SHARED_KEY)
    if mod is None:
        mod = _types.ModuleType(_SHARED_KEY)
        _sys.modules[_SHARED_KEY] = mod
    # ★ 幂等补齐（任何入口先建模块都不能缺属性）
    for _attr, _factory in (("instances", dict), ("counters", dict), ("singletons", dict), ("lock", threading.Lock)):
        if not hasattr(mod, _attr):
            setattr(mod, _attr, _factory())
    return mod


class KvBridge:
    """JSON 文件 + 热层（走 MP 缓存适配器）的桥接。

    子类只需：① 在 `__init__` 里 `self.kv_bind(kv)`；② 把原来的 `_save()` 改名
    `_write_file()`，并按模板新增 kv 感知的 `_save()` / `_kv_apply()` / `_kv_load()`。
    """

    kv: Any = None
    kv_region: str = ""

    def kv_bind(self, kv: Any) -> None:
        """绑定热层（None / 非 Redis 后端 = 纯文件模式）。"""
        self.kv = kv
        self.dirty = True  # 冷备份待写（保证首次 flusher 会落一次盘）

    def kv_ready(self) -> bool:
        """热层是否真的可用（未启用 Redis / 连不上 → False → 走文件）。"""
        kv = getattr(self, "kv", None)
        if kv is None:
            return False
        try:
            return bool(kv.available())
        except Exception:  # noqa: BLE001
            return False

    def kv_key(self, suffix: str = "") -> str:
        """逻辑键名（`区域:后缀`；region 由热层内部处理）。"""
        return f"{self.kv_region}:{suffix}" if suffix else self.kv_region

    def kv_items(self, prefix: str = "") -> Dict[str, Any]:
        """列出本 Store 的所有键值对（键已去掉 region 前缀）。"""
        if not self.kv_ready():
            return {}
        want = f"{self.kv_region}:{prefix}" if prefix else f"{self.kv_region}:"
        try:
            rows = self.kv.items(want)
        except Exception:  # noqa: BLE001
            return {}
        out: Dict[str, Any] = {}
        for key, value in (rows or {}).items():
            if key.startswith(want):
                out[key[len(f"{self.kv_region}:"):]] = value
        return out

    def flush_if_dirty(self) -> bool:
        """把内存快照写进 JSON 冷备份（仅在标脏时）。"""
        if not getattr(self, "dirty", False):
            return False
        try:
            self._write_file()
            self.dirty = False
            return True
        except Exception:  # noqa: BLE001
            return False


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
    kind: str  # "selection" | "deletion" | "protection" | "unprotection" | "reseed"(辅种;原 reuse/crossseed 已归一)
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
    # 「换种」被下线（暂停做种、**不删种**）的种子 hash（小写）。换种只是不再拉它做种，
    # 种子与文件全部保留；站点腾出空间后会按需恢复（换回）。
    enabled: bool = True
    revision: int = 0  # 配置版本号，用于 optimistic locking
    # 「考核下载」模式：进入该模式时记录「站点下载量基线」（byte），用于计算本站下载增量。
    # 任务目标达成（增量 ≥ download_target_gb）或任务重开时会重置。
    exam_download_base: Optional[float] = None
    exam_download_note: str = ""
    # 运行阶段（供前端「运行诊断」流程链转圈用）
    last_phase: str = ""            # entry|fetch|wash|classify|process|done|error
    last_phase_label: str = ""      # 阶段中文名
    last_phase_detail: str = ""     # 阶段内的细粒度进度（如「取种 14/45」），供前端显示避免「像卡住」
    last_phase_at: float = 0.0
    page_cursor: int = 0            # 站点列表页游标（游标深翻）
    # ★ 7.15.0 可观测：上一轮「决策轨迹」（换种闸门 at_cap、门槛、删除原因分布、候选过滤原因…）。
    last_decision: Dict[str, Any] = field(default_factory=dict)
    # 种子详情页映射（hash→details 页 URL）。供「检查」时回站点核对促销/免费状态。
    torrent_pages: Dict[str, str] = field(default_factory=dict)
    # ★ 限时免费到期时刻（hash→unix 秒）。入种时从列表页记下，到点直接清「未下完」的，
    # 不必每轮回详情页核对（详情页可能抓不到 → 只能保守跳过）。
    torrent_free_until: Dict[str, float] = field(default_factory=dict)
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
            "last_decision": dict(self.last_decision or {}),
            "torrent_pages": dict(self.torrent_pages),
            "torrent_free_until": {str(k).lower(): float(v) for k, v in self.torrent_free_until.items()},
            "brush_upload": {str(k).lower(): dict(v) for k, v in self.brush_upload.items()},
            "last_tagged_count": self.last_tagged_count,
            "exam_download_base": self.exam_download_base,
            "exam_download_note": self.exam_download_note,
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
            exam_download_base=(
                None if d.get("exam_download_base") in (None, "") else float(d.get("exam_download_base"))
            ),
            exam_download_note=str(d.get("exam_download_note") or ""),
            last_phase=d.get("last_phase", ""),
            last_phase_label=d.get("last_phase_label", ""),
            last_phase_detail=d.get("last_phase_detail", ""),
            last_phase_at=d.get("last_phase_at", 0.0),
            page_cursor=d.get("page_cursor", 0),
            last_decision=dict(d.get("last_decision") or {}),
            torrent_pages={str(k).lower(): str(v) for k, v in (d.get("torrent_pages") or {}).items() if k and v},
            torrent_free_until={str(k).lower(): float(v) for k, v in (d.get("torrent_free_until") or {}).items() if k and v},
            brush_upload={str(k).lower(): dict(v) for k, v in (d.get("brush_upload") or {}).items() if k and isinstance(v, dict)},
            last_tagged_count=int(d.get("last_tagged_count", 0) or 0),
        )


# ============================================================
# 工作报告（分账）
# ============================================================

@dataclass
class WorkReport:
    """一个 worker（刷流/检查/慢扫）一轮工作的「工作报告」。

    设计：worker **只回报告**，由核心 ``_settle`` 统一分账到 TaskState —— 不同 source
    走不同命名空间，避免并发 worker 互相覆盖。
    计数器默认 ``None`` = 「本报告不涉及该计数」（不覆盖旧值），避免把字段清零。
    """
    task_id: str
    source: str = "brush"          # brush|check
    status: str = ""               # done|noop|skipped|failed
    reason: str = ""
    duration: Optional[float] = None
    added: Optional[int] = None
    deleted: Optional[int] = None
    kept: Optional[int] = None
    reused: Optional[int] = None
    scanned: Optional[int] = None
    # ★ 7.15.0 可观测：「本轮决策轨迹」——回答「为什么没动作」（闸门/门槛/原因分布/候选过滤）。
    decision: Optional[Dict[str, Any]] = None


# ============================================================
# 操作日志
# ============================================================

class OperationJournal(KvBridge):
    """
    操作日志持久化。

    记录每次刷流操作（选种、删种、保护），支持进程重启后恢复。

    ★ 热层 = Redis 每任务一个 hash（`mf:ops:{task_id}`，field = operation_id）；
      JSON 文件 `operations.json` 降为冷备份。
    """

    kv_region = "ops"

    def __init__(self, data_dir: Path, kv: Any = None):
        """
        初始化操作日志。

        Args:
            data_dir: 插件数据目录
            kv: Redis 热层（None = 纯文件模式）
        """
        self.data_dir = data_dir
        self.operations_file = data_dir / "operations.json"
        self._operations: Dict[str, OperationRecord] = {}
        # 每任务保留的最大操作记录数（0 = 不限）。由插件全局设置注入。
        self.keep: int = 0
        # 多个服务（刷流/检查/慢扫）会并发调用 journal；加锁避免
        # 「dictionary changed size during iteration」（add→_prune_task 边遍历边被别的线程改）。
        self._lock = threading.RLock()
        # 热层已写入内容的指纹（operation_id -> JSON），用于增量写
        self._kv_written: Dict[str, str] = {}
        self.kv_bind(kv)
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
        """加载操作日志：Redis 热层优先；热层无数据 → 读文件并回灌。"""
        if self._kv_load():
            try:
                self._heal_stale_submitting()
            except Exception:  # noqa: BLE001
                pass
            return
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

        # 文件里有历史（Redis 空/丢过）→ 回灌热层
        if self._operations:
            try:
                self._kv_apply()
            except Exception:  # noqa: BLE001
                pass

        # 载入时自愈：进程中断/重载遗留的「卡在 submitting」孤儿记录 → 标记为中断
        try:
            self._heal_stale_submitting()
        except Exception:
            pass

    # ---------------------------------------------------------- 热层（MP 缓存/Redis）
    def _kv_load(self) -> bool:
        """从热层载入（有数据返回 True）。"""
        rows = self.kv_items()
        if not rows:
            return False
        loaded = 0
        for _op_id, body in rows.items():
            try:
                data = body if isinstance(body, dict) else json.loads(body)
                op_id = str(data.get("operation_id") or _op_id)
                self._operations[op_id] = OperationRecord.from_dict(data)
                # ★ 载入即视为「与热层一致」：不算指纹（1465 条 × json.dumps ≈ 300ms，就是加载慢的元凶）
                self._kv_written[op_id] = _IN_SYNC
                loaded += 1
            except Exception:  # noqa: BLE001
                continue
        return loaded > 0

    def _kv_apply(self, delta: Optional[Set[str]] = None) -> bool:
        """把内存快照增量写进热层（一个 op 一个键：`ops:{operation_id}`）。

        ★ 批量写：变化的记录攒成一次 pipeline（原先每条一次 SET）。
        """
        if not self.kv_ready():
            return False
        with self._lock:
            ops = list(self._operations.values())
        written = dict(self._kv_written)
        alive: Set[str] = set()
        batch: Dict[str, Any] = {}
        for op in ops:
            op_id = str(getattr(op, "operation_id", "") or "")
            if not op_id:
                continue
            alive.add(op_id)
            if written.get(op_id) == _IN_SYNC:  # 载入后没动过 → 热层里就是它，跳过
                continue
            body = op.to_dict()
            fingerprint = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
            if written.get(op_id) == fingerprint:
                continue
            batch[self.kv_key(op_id)] = body
            written[op_id] = fingerprint
        # 被裁掉/删除的记录 → 删对应键
        stale = [self.kv_key(x) for x in self._kv_written if x not in alive]
        ok = True
        if batch:
            if not self.kv.set_many(batch):
                ok = False
            else:
                self._kv_written = written
        if stale:
            if not self.kv.delete_many(stale):
                ok = False
            else:
                for _sid in stale:
                    self._kv_written.pop(_sid[len(self.kv_region) + 1:], None)
        return ok

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
                    self._kv_written.pop(op.operation_id, None)  # 改过 → 下次写回热层
                    healed += 1
            if healed:
                self._save()
        return healed

    def _save(self, delta: Optional[Set[str]] = None) -> None:
        """保存（热层增量写 Redis；不可用/失败 → 直接写文件）。"""
        if self.kv_ready() and self._kv_apply(delta):
            self.dirty = True
            return
        self._write_file()

    def _write_file(self) -> None:
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
            self._kv_written.pop(operation_id, None)  # 改过 → 下次写回热层
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

            self._kv_written.pop(operation_id, None)  # 改过 → 下次写回热层
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

    def list_recent(self, limit: int = 100, kind: Optional[str] = None) -> List[OperationRecord]:
        """获取最近的操作记录（``kind`` 非空 → 只取该类型；支持逗号分隔多类型）。"""
        wanted = [k.strip() for k in str(kind or "").split(",") if k.strip()]
        records = list(self._operations.values())
        if wanted:
            records = [r for r in records if r.kind in wanted]
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

class TaskStateStore(KvBridge):
    """
    任务状态持久化。

    保存每个任务的运行状态、受保护种子列表等。

    ★ 热层 = Redis 每任务一个 JSON 值（`mf:state:{task_id}`）；`task_states.json` 降为冷备份。
    """

    kv_region = "state"

    def __init__(self, data_dir: Path, kv: Any = None):
        """
        初始化任务状态存储。

        Args:
            data_dir: 插件数据目录
            kv: Redis 热层（None = 纯文件模式）
        """
        self.data_dir = data_dir
        self.state_file = data_dir / "task_states.json"
        self._states: Dict[str, TaskState] = {}
        # 并发 worker（刷流/检查/慢扫）会并发 settle → 加锁串行化内存变更与落盘
        self._lock = threading.RLock()
        self.kv_bind(kv)
        self._load()

    def _load(self) -> None:
        """加载任务状态：Redis 热层优先；热层无数据 → 读文件并回灌。"""
        if self._kv_load():
            return
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for task_id, state_dict in data.items():
                    self._states[task_id] = TaskState.from_dict(state_dict)
        except Exception:
            self._states = {}
        if self._states:  # 文件有历史（Redis 空/丢过）→ 回灌热层
            try:
                self._kv_apply()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------- 热层（MP 缓存/Redis）
    def _kv_load(self) -> bool:
        rows = self.kv_items()
        if not rows:
            return False
        loaded = 0
        for name, body in rows.items():
            try:
                data = body if isinstance(body, dict) else json.loads(body)
                state = TaskState.from_dict(data)
                if state and state.task_id:
                    self._states[state.task_id] = state
                    loaded += 1
            except Exception:  # noqa: BLE001
                continue
        return loaded > 0

    def _kv_apply(self, task_id: Optional[str] = None) -> bool:
        """把任务状态写进热层（task_id 为空 = 全部）。"""
        if not self.kv_ready():
            return False
        with self._lock:
            states = dict(self._states)
        ok = True
        targets = [task_id] if task_id else list(states)
        for tid in targets:
            state = states.get(tid)
            if state is None:
                ok = self.kv.delete(self.kv_key(tid)) and ok
            else:
                ok = self.kv.set(self.kv_key(tid), state.to_dict()) and ok
        return ok

    def _save(self, task_id: Optional[str] = None) -> None:
        """保存（热层增量写 Redis；不可用/失败 → 直接写文件）。"""
        if self.kv_ready() and self._kv_apply(task_id):
            self.dirty = True
            return
        self._write_file()

    def _write_file(self) -> None:
        """保存任务状态到磁盘。"""
        with self._lock:
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
        with self._lock:
            self._states[state.task_id] = state
        self._save(state.task_id)

    def delete(self, task_id: str) -> bool:
        """删除任务状态。"""
        if task_id in self._states:
            del self._states[task_id]
            self._save(task_id)
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

class SeenStore(KvBridge):
    """
    已处理候选记录。

    站点列表页每次返回的都是同一批最新种子，为避免反复下载/重复添加，
    把处理过的候选（按页面链接 / infohash）记录到磁盘，在窗口期内直接跳过。

    ★ 热层 = 每任务一个键（`seen:{task_id}` = {key: ts}）；`seen.json` 降为冷备份。

    """

    kv_region = "seen"

    def __init__(self, data_dir: Path, kv: Any = None):
        """
        初始化。

        Args:
            data_dir: 插件数据目录
            kv: 热层（None / 非 Redis 后端 = 纯文件模式）
        """
        self.data_dir = data_dir
        self.file = data_dir / "seen.json"
        self._data: Dict[str, Dict[str, float]] = {}
        self.kv_bind(kv)
        self._load()

    def _load(self) -> None:
        """载入：热层优先；热层无数据 → 读文件并回灌。"""
        if self._kv_load():
            return
        if not self.file.exists():
            return
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data = loaded
        except Exception:
            self._data = {}
        if self._data:  # 文件有历史（热层空/丢过）→ 回灌
            try:
                self._kv_apply()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------- 热层（MP 缓存/Redis）
    def _kv_load(self) -> bool:
        rows = self.kv_items()
        if not rows:
            return False
        loaded = 0
        for task_id, bucket in rows.items():
            if isinstance(bucket, dict) and bucket:
                self._data[str(task_id)] = {str(k): float(v) for k, v in bucket.items()}
                loaded += 1
        return loaded > 0

    def _kv_apply(self, task_id: Optional[str] = None) -> bool:
        """把某任务的 bucket（或全部）写进热层。"""
        if not self.kv_ready():
            return False
        ok = True
        targets = [task_id] if task_id else list(self._data)
        for tid in targets:
            bucket = self._data.get(tid)
            if bucket:
                ok = self.kv.set(self.kv_key(tid), bucket) and ok
            else:
                ok = self.kv.delete(self.kv_key(tid)) and ok
        return ok

    def _save(self, task_id: Optional[str] = None) -> None:
        """保存（热层增量写；不可用/失败 → 直接写文件）。"""
        if self.kv_ready() and self._kv_apply(task_id):
            self.dirty = True
            return
        self._write_file()

    def _write_file(self) -> None:
        """写 JSON 冷备份。"""
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
            self._save(task_id)

    def prune(self, max_age_seconds: float) -> None:
        """清掉超过 max_age_seconds 的记录。"""
        if max_age_seconds <= 0:
            return
        cutoff = time.time() - max_age_seconds
        changed = False
        touched: List[str] = []
        for task_id in list(self._data.keys()):
            bucket = self._data.get(task_id) or {}
            for key in [k for k, v in bucket.items() if v < cutoff]:
                del bucket[key]
                changed = True
            if not bucket:
                del self._data[task_id]
                changed = True
            touched.append(task_id)
        if changed:
            for task_id in touched:
                self._save(task_id)

    def count(self, task_id: str) -> int:
        return len(self._data.get(task_id) or {})

    def delete(self, task_id: str) -> bool:
        """删除某任务的全部去重记录（任务被删除时调用，避免残留孤儿数据）。"""
        if not task_id:
            return False
        if self._data.pop(task_id, None) is not None:
            self._save(task_id)
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

    kv_region = "dead"

    def __init__(self, data_dir: Path, kv: Any = None):
        self.data_dir = data_dir
        self.file = data_dir / "dead.json"
        self._data: Dict[str, Dict[str, float]] = {}
        self.kv_bind(kv)
        self._load()

    def is_dead(self, task_id: str, key: str, cooldown_seconds: float = 0.0) -> bool:
        """该 key 是否在冷却期内被标记为死种。"""
        return self.is_seen(task_id, key, cooldown_seconds)


class AddGateStore(KvBridge):
    """★ 全局（**跨任务**）资源「下载占用」闸门。

    目的：**同一个资源（同一 infohash 或同一完整特征码）在插件内只允许被下载一次**，
    无论由哪个任务发起 —— 避免「A 任务下过 → B 任务又下一遍」的重复下载（白烧流量）。
    按 MODEL.md「一个资源只从一个站下载」的模型落地这条规则。

    键 = 资源身份：``h:<infohash>`` / ``fp:<完整特征码>``；值 = ``{task, ts, state}``，
    ``state`` ∈ ``inflight``（某任务正在下 → 防**并发**各下一份）/ ``done``（某任务已下完 →
    在 TTL 内防**后续**重复，含「清理掉之后又下」的抖动）。

    - 与 ``SeenStore`` / ``DeadStore`` 分属**不同文件**（``add_gate.json``），命名空间不串扰；
    - 热层 = 每键一个值（``addgate:<reskey>``）；``add_gate.json`` 降为冷备份；
    - 别名/同一任务不视为冲突（幂等续占）。
    """

    kv_region = "addgate"

    def __init__(self, data_dir: Path, kv: Any = None):
        """
        初始化。

        Args:
            data_dir: 插件数据目录
            kv: 热层（None / 非 Redis 后端 = 纯文件模式）
        """
        self.data_dir = data_dir
        self.file = data_dir / "add_gate.json"
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.kv_bind(kv)
        self._load()

    # ---------------------------------------------------------- 载入 / 持久化
    def _load(self) -> None:
        """载入：热层优先；热层无数据 → 读文件并回灌。"""
        if self._kv_load():
            return
        if not self.file.exists():
            return
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data = {
                    str(k): {
                        "task": str((v or {}).get("task") or ""),
                        "ts": float((v or {}).get("ts") or 0),
                        "state": str((v or {}).get("state") or "done"),
                    }
                    for k, v in loaded.items()
                    if isinstance(v, dict)
                }
        except Exception:
            self._data = {}
        if self._data:  # 文件有历史（热层空/丢过）→ 回灌
            try:
                self._kv_apply()
            except Exception:  # noqa: BLE001
                pass

    def _kv_load(self) -> bool:
        rows = self.kv_items()
        if not rows:
            return False
        loaded = 0
        for k, v in rows.items():
            if isinstance(v, dict):
                self._data[str(k)] = {
                    "task": str(v.get("task") or ""),
                    "ts": float(v.get("ts") or 0),
                    "state": str(v.get("state") or "done"),
                }
                loaded += 1
        return loaded > 0

    def _kv_apply(self, keys: Optional[List[str]] = None) -> bool:
        """把指定键（或全部）写进热层。"""
        if not self.kv_ready():
            return False
        ok = True
        targets = self._norm_keys(keys) if keys else list(self._data)
        for k in targets:
            entry = self._data.get(k)
            if isinstance(entry, dict):
                ok = self.kv.set(self.kv_key(k), entry) and ok
            else:
                ok = self.kv.delete(self.kv_key(k)) and ok
        return ok

    def _save(self, keys: Optional[List[str]] = None) -> None:
        """保存：热层即时增量写 + JSON 冷备份**一并落**。

        本表**不**挂在 ``MagicFlowStore.stores()`` 上（见 ``get_gate_store`` 的说明），
        因此不能依赖后台 flusher 落盘；写入又很稀疏（只在下载决策时），整表也小，
        故直接双写，确保热重载 / 进程重启后数据都在。
        """
        if self.kv_ready():
            try:
                self._kv_apply(keys)
            except Exception:  # noqa: BLE001
                pass
            self.dirty = False
        self._write_file()

    def _write_file(self) -> None:
        """写 JSON 冷备份。"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(self.file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.file)
        except Exception:
            pass

    # ---------------------------------------------------------- 对外
    @staticmethod
    def _norm_keys(keys: Any) -> List[str]:
        out: List[str] = []
        for k in (keys or []):
            s = str(k or "").strip()
            if s and s not in out:
                out.append(s)
        return out

    def _conflicts(self, keys: List[str], task_id: str, inflight_ttl: float,
                   done_ttl: float, now: float) -> List[str]:
        """返回被**其它任务**在 TTL 内占用/下过的键。"""
        out: List[str] = []
        me = str(task_id or "")
        for k in keys:
            entry = self._data.get(k)
            if not isinstance(entry, dict):
                continue
            owner = str(entry.get("task") or "")
            if not owner or owner == me:
                continue
            ttl = inflight_ttl if str(entry.get("state") or "") == "inflight" else done_ttl
            if ttl and (now - float(entry.get("ts") or 0)) > ttl:
                continue
            out.append(k)
        return out

    def claim(self, keys: Any, task_id: str, inflight_ttl: float, done_ttl: float,
              now: Optional[float] = None) -> List[str]:
        """尝试占用一批资源键（**全有或全无**）。

        返回：被别的任务占用的冲突键列表（非空 = 未占用任何键，调用方应放弃）；
        空列表 = 已成功占用（state=inflight）。同一任务重复占用幂等（续期）。
        """
        ks = self._norm_keys(keys)
        if not ks:
            return []
        now = time.time() if now is None else now
        with self._lock:
            cf = self._conflicts(ks, task_id, inflight_ttl, done_ttl, now)
            if cf:
                return cf
            changed: List[str] = []
            for k in ks:
                entry = self._data.get(k)
                if (isinstance(entry, dict) and str(entry.get("task") or "") == str(task_id)
                        and str(entry.get("state") or "") == "inflight"):
                    entry["ts"] = now  # 幂等续占
                else:
                    self._data[k] = {"task": str(task_id), "ts": now, "state": "inflight"}
                changed.append(k)
            self._save(changed)
        return []

    def peek(self, keys: Any, task_id: str, inflight_ttl: float, done_ttl: float,
             now: Optional[float] = None) -> List[str]:
        """只看冲突，不占用（用于提前跳过，避免占槽）。"""
        ks = self._norm_keys(keys)
        if not ks:
            return []
        now = time.time() if now is None else now
        with self._lock:
            return self._conflicts(ks, task_id, inflight_ttl, done_ttl, now)

    def conflict_states(self, keys: Any, task_id: str, inflight_ttl: float,
                        done_ttl: float, now: Optional[float] = None) -> Dict[str, str]:
        """返回冲突键 → 状态（``inflight``/``done``），仅含**其它任务**在 TTL 内的记录。

        用途：区分「对方**正在下**（→ 让位本轮，下轮本机有副本可辅种）」与
        「对方**已下过**（本机已无副本 → 真没得辅，终局跳过）」。
        """
        ks = self._norm_keys(keys)
        if not ks:
            return {}
        now = time.time() if now is None else now
        out: Dict[str, str] = {}
        with self._lock:
            me = str(task_id or "")
            for k in ks:
                entry = self._data.get(k)
                if not isinstance(entry, dict):
                    continue
                owner = str(entry.get("task") or "")
                if not owner or owner == me:
                    continue
                st = str(entry.get("state") or "done")
                ttl = inflight_ttl if st == "inflight" else done_ttl
                if ttl and (now - float(entry.get("ts") or 0)) > ttl:
                    continue
                out[k] = st
        return out

    def finish(self, keys: Any, task_id: str, now: Optional[float] = None) -> None:
        """标记下载完成（state=done）；登记后续 TTL 内不再重复下载。"""
        ks = self._norm_keys(keys)
        if not ks:
            return
        now = time.time() if now is None else now
        with self._lock:
            changed: List[str] = []
            for k in ks:
                entry = self._data.get(k)
                if isinstance(entry, dict) and str(entry.get("task") or "") == str(task_id):
                    entry["state"] = "done"
                    entry["ts"] = now
                    changed.append(k)
                elif k not in self._data:
                    self._data[k] = {"task": str(task_id), "ts": now, "state": "done"}
                    changed.append(k)
            if changed:
                self._save(changed)

    def release(self, keys: Any, task_id: str) -> None:
        """释放**本任务**尚未完成的占用（下载失败时调用，允许重试）。"""
        ks = self._norm_keys(keys)
        if not ks:
            return
        with self._lock:
            removed: List[str] = []
            for k in ks:
                entry = self._data.get(k)
                if (isinstance(entry, dict) and str(entry.get("task") or "") == str(task_id)
                        and str(entry.get("state") or "") == "inflight"):
                    del self._data[k]
                    removed.append(k)
            if removed:
                self._save(removed)

    def prune(self, inflight_ttl: float, done_ttl: float, now: Optional[float] = None) -> int:
        """清掉超过 TTL 的记录（按各自状态取 TTL）。"""
        now = time.time() if now is None else now
        with self._lock:
            doomed: List[str] = []
            for k, entry in list(self._data.items()):
                if not isinstance(entry, dict):
                    doomed.append(k)
                    continue
                ttl = inflight_ttl if str(entry.get("state") or "") == "inflight" else done_ttl
                if ttl and (now - float(entry.get("ts") or 0)) > ttl:
                    doomed.append(k)
            for k in doomed:
                self._data.pop(k, None)
            if doomed:
                self._save(doomed)
            return len(doomed)

    def count(self) -> int:
        """当前记录条数（诊断用）。"""
        return len(self._data)


def get_gate_store(data_dir: Path, kv: Any = None) -> AddGateStore:
    """取/建**进程级**资源下载闸门（按 data_dir 单例，跨热重载存活）。

    ★ 为什么不挂在 ``MagicFlowStore`` 上：``MagicFlowStore`` 是**进程级单例**，MP 热重载
    只会让插件实例重绑它、**不会重建**——热重载后旧实例上的 ``stores()`` / 属性仍是**旧类**
    （persistence 里 ``get_operations`` 注释亦已注明）。往 ``MagicFlowStore`` 加新子表
    在热重载后拿不到。因此用与 store 同一套 ``_shared()`` 注册表单独持有闸门实例，
    热重载后仍指向同一个对象，不需重启 MP 即可生效。

    Args:
        data_dir: 插件数据目录（作为单例键）
        kv: 热层（每次调用都重绑，保证热重载后拿到新热层）
    """
    key = f"gate:{Path(data_dir)}"
    sh = _shared()
    with sh.lock:
        gate = sh.singletons.get(key)
        if gate is None:
            gate = AddGateStore(data_dir, kv=kv)
            sh.singletons[key] = gate
        elif kv is not None:
            try:
                gate.kv_bind(kv)
            except Exception:  # noqa: BLE001
                pass
    return gate


# ============================================================
# 插件数据存储（高层封装）
# ============================================================

class RecommendStore(KvBridge):
    """推荐甄别结果存储（JSON 冷备份 + 热层）。

    记录每个候选刷流种的价值甄别结果与生命周期状态：
    ``hash -> {first_seen, title, size_gb, media{source,id,type,year}, rating,
               source, status, notified_at, confirmed_at, note, updated_at}``
    status ∈ pending（临时种等待） / recommended（已打推荐 tag 待确认）
             / confirmed（已确认，待入库/已入库） / dismissed / deleted。

    单例由 ``MagicFlowStore`` 持有；_write_file 采用**读-合并-写**（按 updated_at），
    避免热重载多实例互相覆盖（同 OperationJournal 的教训）。
    热层 = 每项一个键（`rec:{hash}`）；JSON 降为冷备份。
    """

    kv_region = "rec"

    def __init__(self, data_dir: Path, kv: Any = None):
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "recommend.json"
        self._lock = threading.RLock()
        self._items: Dict[str, Dict[str, Any]] = {}
        self._kv_written: Dict[str, str] = {}
        self.kv_bind(kv)
        self._load()

    def _load(self) -> None:
        """载入：热层优先；热层无数据 → 读文件并回灌。"""
        rows = self.kv_items()
        if rows:
            for key, item in rows.items():
                if isinstance(item, dict):
                    self._items[str(key).lower()] = dict(item)
            if self._items:
                return
        try:
            if self.file.exists():
                with open(self.file, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if isinstance(data, dict):
                    self._items = {
                        str(k).lower(): dict(v)
                        for k, v in data.items()
                        if isinstance(v, dict)
                    }
        except Exception:
            self._items = {}
        if self._items:  # 文件有历史（热层空/丢过）→ 回灌
            try:
                self._kv_apply()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------- 热层（MP 缓存/Redis）
    def _kv_apply(self, key: Optional[str] = None) -> bool:
        """增量写热层（key 为空 = 全量对比）。★ 批量 pipeline 写。"""
        if not self.kv_ready():
            return False
        with self._lock:
            items = dict(self._items)
        targets = [str(key).lower()] if key else list(items)
        ok = True
        batch: Dict[str, Any] = {}
        for k in targets:
            item = items.get(k)
            if item is None:
                batch[self.kv_key(k)] = None
                continue
            fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if self._kv_written.get(k) == fingerprint:
                continue
            batch[self.kv_key(k)] = item
        # 内存里已没有的项 → 删键（全量模式才做）
        if not key:
            for k in [x for x in self._kv_written if x not in items]:
                batch[self.kv_key(k)] = None
                self._kv_written.pop(k, None)
        if not batch:
            return True
        writes = {k: v for k, v in batch.items() if v is not None}
        drops = [k for k, v in batch.items() if v is None]
        if writes and not self.kv.set_many(writes):
            ok = False
        if drops and not self.kv.delete_many(drops):
            ok = False
        if ok:
            for k, item in items.items():
                if self.kv_key(k) in writes:
                    self._kv_written[k] = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        return ok

    def _save(self, key: Optional[str] = None) -> None:
        """保存（热层增量写；不可用/失败 → 直接写文件）。"""
        if self.kv_ready() and self._kv_apply(key):
            self.dirty = True
            return
        self._write_file()

    def _write_file(self) -> None:
        with self._lock:
            try:
                self.data_dir.mkdir(parents=True, exist_ok=True)
                disk: Dict[str, Dict[str, Any]] = {}
                if self.file.exists():
                    try:
                        with open(self.file, "r", encoding="utf-8") as f:
                            d = json.load(f) or {}
                        if isinstance(d, dict):
                            disk = {
                                str(k).lower(): v
                                for k, v in d.items()
                                if isinstance(v, dict)
                            }
                    except Exception:
                        disk = {}
                merged = dict(disk)
                for h, item in self._items.items():
                    cur = merged.get(h)
                    if cur is None or float(item.get("updated_at", 0) or 0) >= float(cur.get("updated_at", 0) or 0):
                        merged[h] = item
                self._items = merged
                tmp = self.file.with_name(self.file.name + ".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.file)
            except Exception:
                pass

    def get(self, h: str) -> Optional[Dict[str, Any]]:
        h = str(h or "").lower()
        if not h:
            return None
        with self._lock:
            item = self._items.get(h)
            return dict(item) if item else None

    def get_many(self, hs: Any) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            out: Dict[str, Dict[str, Any]] = {}
            for h in hs or []:
                k = str(h or "").lower()
                if k and k in self._items:
                    out[k] = dict(self._items[k])
            return out

    def upsert(self, h: str, **fields: Any) -> Dict[str, Any]:
        h = str(h or "").lower()
        if not h:
            return {}
        with self._lock:
            cur = dict(self._items.get(h) or {})
            cur.update({k: v for k, v in fields.items() if v is not None})
            cur["updated_at"] = time.time()
            self._items[h] = cur
            self._save()
            return dict(cur)

    def set_status(self, h: str, status: str, **fields: Any) -> Dict[str, Any]:
        return self.upsert(h, status=status, **fields)

    def delete(self, h: str) -> bool:
        h = str(h or "").lower()
        with self._lock:
            if h in self._items:
                self._items.pop(h, None)
                self._save()
                return True
        return False

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = [dict(v, hash=k) for k, v in self._items.items()]
        if status:
            items = [i for i in items if i.get("status") == status]
        items.sort(key=lambda x: float(x.get("updated_at", 0) or 0), reverse=True)
        return items

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._items.items()}

    def clear(self) -> int:
        """清空全部记录（诊断/重置用；直接覆盖写，不走合并）。"""
        with self._lock:
            n = len(self._items)
            self._items = {}
            try:
                tmp = self.file.with_name(self.file.name + ".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False)
                os.replace(tmp, self.file)
            except Exception:
                pass
            return n


class ArchiveStore(KvBridge):
    """云盘归档记录存储（JSON 冷备份 + 热层）。

    ``本地路径 -> {rel, remote, size, status, uploaded_at, verified, error,
                    deleted_at, updated_at}``
    status ∈ uploading / uploaded / failed / archived。

    与 RecommendStore 同样的教训：**热重载多实例下必须读-合并-写**，
    否则内存快照整表覆盖会丢记录。
    热层 = 每项一个键（`cloud:{路径}`）；JSON 降为冷备份。
    """

    kv_region = "cloud"

    def __init__(self, data_dir: Path, kv: Any = None):
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "cloud.json"
        self._lock = threading.RLock()
        self._items: Dict[str, Dict[str, Any]] = {}
        self._kv_written: Dict[str, str] = {}
        self.kv_bind(kv)
        self._load()

    def _load(self) -> None:
        """载入：热层优先；热层无数据 → 读文件并回灌。"""
        rows = self.kv_items()
        if rows:
            self._items = {str(k): dict(v) for k, v in rows.items() if isinstance(v, dict)}
            if self._items:
                return
        try:
            if self.file.exists():
                with open(self.file, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if isinstance(data, dict):
                    self._items = {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
        except Exception:
            self._items = {}
        if self._items:  # 文件有历史（热层空/丢过）→ 回灌
            try:
                self._kv_apply()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------- 热层（MP 缓存/Redis）
    def _kv_apply(self, key: Optional[str] = None) -> bool:
        """★ 批量 pipeline 写热层。"""
        if not self.kv_ready():
            return False
        with self._lock:
            items = dict(self._items)
        targets = [str(key)] if key else list(items)
        ok = True
        batch: Dict[str, Any] = {}
        for k in targets:
            item = items.get(k)
            if item is None:
                batch[self.kv_key(k)] = None
                continue
            fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if self._kv_written.get(k) == fingerprint:
                continue
            batch[self.kv_key(k)] = item
        if not key:
            for k in [x for x in self._kv_written if x not in items]:
                batch[self.kv_key(k)] = None
                self._kv_written.pop(k, None)
        if not batch:
            return True
        writes = {k: v for k, v in batch.items() if v is not None}
        drops = [k for k, v in batch.items() if v is None]
        if writes and not self.kv.set_many(writes):
            ok = False
        if drops and not self.kv.delete_many(drops):
            ok = False
        if ok:
            for k, item in items.items():
                if self.kv_key(k) in writes:
                    self._kv_written[k] = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        return ok

    def _save(self, key: Optional[str] = None) -> None:
        """保存（热层增量写；不可用/失败 → 直接写文件）。"""
        if self.kv_ready() and self._kv_apply(key):
            self.dirty = True
            return
        self._write_file()

    def _write_file(self) -> None:
        with self._lock:
            try:
                self.data_dir.mkdir(parents=True, exist_ok=True)
                disk: Dict[str, Dict[str, Any]] = {}
                if self.file.exists():
                    try:
                        with open(self.file, "r", encoding="utf-8") as f:
                            d = json.load(f) or {}
                        if isinstance(d, dict):
                            disk = {str(k): v for k, v in d.items() if isinstance(v, dict)}
                    except Exception:
                        disk = {}
                merged = dict(disk)
                for k, item in self._items.items():
                    cur = merged.get(k)
                    if cur is None or float(item.get("updated_at", 0) or 0) >= float(cur.get("updated_at", 0) or 0):
                        merged[k] = item
                self._items = merged
                tmp = self.file.with_name(self.file.name + ".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.file)
            except Exception:
                pass

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._items.get(str(path or ""))
            return dict(item) if item else None

    def upsert(self, path: str, **fields: Any) -> Dict[str, Any]:
        path = str(path or "")
        if not path:
            return {}
        with self._lock:
            cur = dict(self._items.get(path) or {})
            cur.update({k: v for k, v in fields.items() if v is not None})
            cur["path"] = path
            cur["updated_at"] = time.time()
            self._items[path] = cur
            self._save()
            return dict(cur)

    def delete(self, path: str) -> bool:
        with self._lock:
            if str(path) in self._items:
                self._items.pop(str(path), None)
                self._save()
                return True
        return False

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = [dict(v, path=k) for k, v in self._items.items()]
        items.sort(key=lambda x: float(x.get("updated_at", 0) or 0), reverse=True)
        return items

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._items.items()}

    def clear(self) -> int:
        with self._lock:
            n = len(self._items)
            self._items = {}
            try:
                tmp = self.file.with_name(self.file.name + ".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False)
                os.replace(tmp, self.file)
            except Exception:
                pass
            return n


class MagicFlowStore:
    """
    MagicFlow 统一数据存储。

    整合操作日志和任务状态管理。

    ★ 进程内**按 data_dir 单例**：MoviePilot 热重载会 new 出新的插件实例，但上一实例
    可能仍有在飞线程（如跨重载的 brush）。若各自持有独立的内存快照，落盘会「整表互相覆盖」
    → 统计/状态被旧快照回滚（曾实际发生）。共用同一实例即可根治。

    ★★ 单例注册表放在**独立模块**（`sys.modules[_SHARED_KEY]`）里，不能放类属性：
    MP 热重载会清掉 `app.plugins.magicflow.*` 模块缓存，类属性会跟着重置
    → 每次重载都新建 store + **再起一个后台落盘线程（线程泄漏）**，
    旧线程还继续用旧常量、旧内存快照落盘。实测现象：文件被 20~36s 间隔乱写。
    """

    _instances: Dict[str, "MagicFlowStore"] = {}
    _instances_lock = threading.Lock()

    def __new__(cls, data_dir: Path, kv: Any = None):
        del kv  # 单例只看 data_dir；热层在 __init__ / bind_hot 里绑定
        key = str(Path(data_dir))
        sh = _shared()
        with sh.lock:
            inst = sh.instances.get(key)
            if inst is None:
                inst = super().__new__(cls)
                inst._initialized = False
                sh.instances[key] = inst
            elif type(inst) is not cls:
                # ★ 15.8.12：MP 热重载会清 ``app.plugins.magicflow.*`` 模块缓存 → 本类
                #   对象换代，但单例注册表（独立模块，跨重载）里还是**旧类**的实例。
                #   旧类没有本次新增的方法 ⇒ ``purge_adopted_protected`` 抛
                #   AttributeError 被 ``init_plugin`` 的 try 吞掉、旧 ``note_adopted``
                #   也继续写 ``protected_torrents``（实测：漏洞在重载后依旧生效）。
                #   只换 ``__class__``（同一对象、同一内存快照、同一落盘线程、同一热层
                #   绑定）：重新 ``__init__`` 会丢未落盘的改动并再起一个落盘线程。
                #   子 Store（journal/task_states/...）方法未变，暂不换代。
                try:
                    inst.__class__ = cls
                except TypeError:  # pragma: no cover - 布局不兼容时退回旧类
                    pass
            return inst

    def __init__(self, data_dir: Path, kv: Any = None):
        """
        初始化数据存储（同一 data_dir 只真正初始化一次）。

        Args:
            data_dir: 插件数据目录
            kv: 在线热层（走 MP 缓存；未启用 Redis 时自动退化为纯文件）
        """
        if getattr(self, "_initialized", False):
            if kv is not None:
                self.bind_hot(kv)
            return
        self._initialized = True
        self.data_dir = data_dir
        _t0 = time.perf_counter()
        _marks: Dict[str, float] = {}
        self.journal = OperationJournal(data_dir, kv=kv)
        _marks["日志"] = time.perf_counter()
        self.task_states = TaskStateStore(data_dir, kv=kv)
        self.seen = SeenStore(data_dir, kv=kv)
        self.dead = DeadStore(data_dir, kv=kv)
        _marks["状态"] = time.perf_counter()
        self.recommend = RecommendStore(data_dir, kv=kv)
        self.cloud = ArchiveStore(data_dir, kv=kv)
        _marks["推荐"] = time.perf_counter()
        # 数据层载入耗时（常驻诊断：>300ms 才告警，带分项）——「加载慢」可量化
        _total_ms = (time.perf_counter() - _t0) * 1000
        try:
            _log = getattr(kv, "_log", None) if kv is not None else None
            _keys = int(kv.count()) if kv is not None and kv.available() else 0
            _msg = (
                f"数据层载入 {_total_ms:.0f}ms（日志 {(_marks['日志'] - _t0) * 1000:.0f} / "
                f"状态 {(_marks['状态'] - _marks['日志']) * 1000:.0f} / "
                f"推荐 {(_marks['推荐'] - _marks['状态']) * 1000:.0f}）热层键 {_keys}"
            )
            if callable(_log):
                _log(_msg, "warning" if _total_ms > 300 else "info")
        except Exception:  # noqa: BLE001
            pass
        self.flush_sec = float(KV_FILE_FLUSH_SEC)
        self._flusher_stop = False
        self._flusher_thread = None
        self._start_flusher()

    # -------------------- 热层 / 冷备份 --------------------
    def stores(self) -> List[Any]:
        """全部 Store（顺序 = journal / task_states / seen / dead / recommend / cloud）。"""
        return [self.journal, self.task_states, self.seen, self.dead, self.recommend, self.cloud]

    def bind_hot(self, kv: Any) -> None:
        """把热层绑到已存在的单例上（热重载后 config 变化时重新绑定）。"""
        for store in self.stores():
            try:
                store.kv_bind(kv)
            except Exception:  # noqa: BLE001
                continue

    def flush_all(self) -> List[str]:
        """把标脏的 Store 快照写进 JSON 冷备份（供 stop / 定时器调用）。"""
        written: List[str] = []
        for store in self.stores():
            try:
                if store.flush_if_dirty():
                    written.append(type(store).__name__)
            except Exception:  # noqa: BLE001
                continue
        return written

    def _start_flusher(self) -> None:
        """后台按 ``flush_sec`` 把脏快照落一次 JSON（Redis 丢了以后的恢复源）。

        单例 + 跨重载不泄漏：线程只起一个（`_flusher_thread` 存活判断），
        间隔每次循环重读 ``self.flush_sec``（重载时由插件实例调 `set_flush_sec` 更新）。
        """
        th = getattr(self, "_flusher_thread", None)
        if th is not None and th.is_alive() and not getattr(self, "_flusher_stop", False):
            return
        self._flusher_stop = False

        def _loop() -> None:
            while not getattr(self, "_flusher_stop", False):
                try:
                    sec = float(getattr(self, "flush_sec", KV_FILE_FLUSH_SEC) or KV_FILE_FLUSH_SEC)
                except Exception:  # noqa: BLE001
                    sec = KV_FILE_FLUSH_SEC
                for _ in range(int(max(sec, 5.0))):
                    if getattr(self, "_flusher_stop", False):
                        return
                    time.sleep(1.0)
                try:
                    self.flush_all()
                except Exception:  # noqa: BLE001
                    continue

        self._flusher_thread = threading.Thread(target=_loop, daemon=True, name="MagicFlow-KvFlush")
        self._flusher_thread.start()

    def set_flush_sec(self, sec: Any) -> None:
        """更新冷备份落盘间隔（热重载后新代码里的常量可以生效）。"""
        try:
            self.flush_sec = float(sec)
        except Exception:  # noqa: BLE001
            return
        self._start_flusher()

    def stop_flusher(self) -> None:
        """停后台落盘线程（插件停止时调；避免旧模块线程一直活着）。"""
        self._flusher_stop = True

    def hot_stats(self) -> Dict[str, Any]:
        """热层健康度（给 /debug/store 用）。"""
        out: Dict[str, Any] = {}
        for store in self.stores():
            name = getattr(store, "kv_region", type(store).__name__)
            out[name] = {
                "hot": bool(getattr(store, "kv", None) is not None and store.kv_ready()),
                "dirty": bool(getattr(store, "dirty", False)),
            }
        return out

    def flush_to_disk_and_hot(self) -> Dict[str, int]:
        """把内存快照写入热层 + 冷备份（供手动对齐用）。"""
        counts: Dict[str, int] = {}
        for store in self.stores():
            name = getattr(store, "kv_region", type(store).__name__)
            try:
                applied = store._kv_apply() if store.kv_ready() else False  # noqa: SLF001
                store._write_file()  # noqa: SLF001
                store.dirty = False
                counts[name] = 1 if applied else 0
            except Exception:  # noqa: BLE001
                counts[name] = 0
        return counts

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

    # -------------------- 考核下载模式（基线） --------------------

    def get_exam_download(self, task_id: str) -> Dict[str, Any]:
        """读取「考核下载」基线：{base, note}。"""
        state = self.task_states.get(task_id)
        base = getattr(state, "exam_download_base", None) if state else None
        return {
            "base": (None if base in (None, "") else float(base)),
            "note": str(getattr(state, "exam_download_note", "") or "") if state else "",
        }

    def set_exam_download(self, task_id: str, base: Optional[float], note: str = "") -> None:
        """写入「考核下载」基线（base=None 表示清空）。"""
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        state.exam_download_base = None if base is None else float(base)
        state.exam_download_note = str(note or "")
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

    # -------------------- 限时免费到期时刻（hash→unix） --------------------

    def get_torrent_free_until(self, task_id: str) -> Dict[str, float]:
        """读取本任务记录的「种子免费到期时刻」（hash→unix 秒）。"""
        state = self.task_states.get(task_id)
        if not state:
            return {}
        return dict(getattr(state, "torrent_free_until", {}) or {})

    def note_torrent_free_until(self, task_id: str, mapping: Dict[str, float]) -> None:
        """记录一批「hash→免费到期时刻(unix 秒)」（仅在有值时写入）。"""
        if not task_id or not mapping:
            return
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        table = getattr(state, "torrent_free_until", None)
        if table is None:
            table = state.torrent_free_until = {}
        changed = False
        for h, ts in mapping.items():
            hs = str(h or "").lower()
            try:
                t = float(ts)
            except (TypeError, ValueError):
                continue
            if hs and t > 0 and table.get(hs) != t:
                table[hs] = t
                changed = True
        if changed:
            state.torrent_free_until = table
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
        fu = getattr(state, "torrent_free_until", None)
        if fu:
            fu2 = {
                k: v for k, v in fu.items()
                if (k or "").strip().lower() not in keys
            }
            if len(fu2) != len(fu):
                state.torrent_free_until = fu2
                before += 1  # 触发保存（免费到期表也有变动）
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
        """记录新纳入的「同站纳管」种子 hash（持久化）。返回本次新增数量。

        ★ 15.8.12：纳管只记 ``adopted_hashes``（软保护），顺手把同一 hash 从
        ``protected_torrents``（=「手动保留」，硬保护）摘掉 —— 纳管 ≠ 手动保留。
        历史上两条路径都写，导致删除闸门 / 站点报表 / 静默盘点把纳管种当手动保留。
        """
        state = self.task_states.get(task_id)
        if not state:
            state = self.task_states.create(task_id)
        before = len(state.adopted_hashes)
        _unprotected = 0
        for h in hashes:
            hs = (h or "").lower()
            if not hs:
                continue
            state.adopted_hashes.add(hs)
            _hit = {h for h in state.protected_torrents if str(h or "").strip().lower() == hs}
            if _hit:
                state.protected_torrents -= _hit
                _unprotected += len(_hit)
        if len(state.adopted_hashes) != before or _unprotected:
            self.task_states.save(state)
        return len(state.adopted_hashes) - before

    def purge_adopted_protected(self) -> int:
        """★ 15.8.12 一次性清理：把所有任务里「既纳管、又被写成手动保留」的 hash
        从 ``protected_torrents`` 摘除（纳管语义照旧保留在 ``adopted_hashes`` → 软保护）。

        背景：``BrushMixin._adopt_same_site`` 曾在纳管时同时调 ``protect_torrent``，
        使纳管种被删除闸门（``deletegate`` 第 1 条「手动保留」）/ 站点报表 / 静默盘点
        当成用户手动保留（线上实测 525 条，其中 520 条来自纳管）；而 ``_protection_sets``
        本就把纳管从 hard 剥到 soft（``features/protection.py``）⇒ 那些写入是纯污染。

        幂等：可反复调用；返回本次摘除条数（逐任务相加）。
        """
        total = 0
        try:
            states = list(self.task_states.list_all() or [])
        except Exception:  # noqa: BLE001
            return 0
        for state in states:
            adopted = {
                str(h or "").strip().lower()
                for h in (getattr(state, "adopted_hashes", set()) or set())
                if str(h or "").strip()
            }
            if not adopted:
                continue
            hit = {h for h in state.protected_torrents if str(h or "").strip().lower() in adopted}
            if not hit:
                continue
            state.protected_torrents -= hit
            self.task_states.save(state)
            total += len(hit)
        return total

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

    def settle(self, report: "WorkReport") -> None:
        """核心分账：把一个 worker 的 WorkReport 归入对应命名空间的 TaskState。

        - ``source in {brush, check}``：更新本轮字段（二者通过 ``_try_begin_run`` 互斥，不并发）。
        计数器为 ``None`` 时跳过（不清零），所以「失败/无计数」的报告只更新状态/原因。
        """
        if report is None or not report.task_id:
            return
        state = self.task_states.get(report.task_id)
        if not state:
            state = self.task_states.create(report.task_id)
        has_counts = any(
            v is not None for v in (report.added, report.deleted, report.kept, report.reused)
        )
        if report.added is not None:
            state.cumulative_added += int(report.added)
            state.last_added = int(report.added)
        if report.deleted is not None:
            state.cumulative_deleted += int(report.deleted)
            state.last_deleted = int(report.deleted)
        if report.reused is not None:
            state.cumulative_reused += int(report.reused)
            state.last_reused = int(report.reused)
        if report.kept is not None:
            # 语义是「当前托管快照」，不累加
            state.cumulative_kept = int(report.kept)
            state.last_kept = int(report.kept)
        if has_counts:
            state.last_success_at = time.time()
            state.last_error = None
        if report.status:
            state.last_run_status = report.status
        if report.reason is not None:
            state.last_run_reason = report.reason or ""
        if report.duration is not None:
            state.last_run_duration = round(float(report.duration or 0.0), 2)
        if report.decision is not None:
            state.last_decision = dict(report.decision or {})
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
                "last_decision": {},
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
            "last_decision": dict(getattr(state, "last_decision", {}) or {}),
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
