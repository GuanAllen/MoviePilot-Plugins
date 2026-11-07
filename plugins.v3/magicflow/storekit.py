"""魔流 · 存储数据层（L0）—— 数据模型 + 冷热双写桥 + JSON 冷层惯用法。

★ 19.10.33 从 ``persistence.py`` 下沉，切出来的理由是**这一段自己在处理数据**，
  与插件运行时（host / 插件实例 / MP 站点表）零耦合：
  · 数据模型：``OperationItem`` / ``OperationRecord`` / ``TaskState`` / ``WorkReport``
    以及它们的 ``to_dict`` / ``from_dict`` 编解码 —— 纯粹的「结构 ↔ dict」；
  · ``KvBridge``：JSON 冷备份 + 热层（MP 缓存适配器）的桥接骨架，只管
    「脏标记 / 原子写 / 并集补缺」，不认识任何业务表；
  · ``read_json_dict`` / ``batch_kv_apply``：原先 5 个 Store 各抄一份的
    「容错读冷层」「差分写热层」。

★ 留在 ``persistence.py`` 的是什么：``MagicFlowStore``（后台 flusher / 阶段缓存 /
  保护集）和具体业务的 Store（操作日志 / 任务状态 / seen / 死种 / 下载闸门 / 推荐 /
  云归档）—— 它们要 host 状态与业务口径，属编排层，不是「自己处理数据」。

★ 不 import ``common`` / 任何 ``app.*``（``app.log`` 仅 try 兜底、缺 app 退回标准库），
  因此 ``python3 tools/test_storekit.py`` 能离线跑，不用造 MoviePilot 桩。

★ 调用面不变：``persistence.py`` 顶部显式列名 re-export 本模块全部名字，
  40+ 处 ``from .persistence import OperationItem`` 一行都不用改。
"""

import copy
import json
import os
import threading
import time
from dataclasses import MISSING, asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

# ★ 日志：与 persistence.py 同口径 —— 运行环境走 MP logger（进 moviepilot.log），
#   离线（无 app 包）退回标准库，保证本模块可被 tools/test_*.py 直接加载。
try:
    from app.log import logger
except ImportError:  # pragma: no cover - 仅离线环境
    import logging

    logger = logging.getLogger("magicflow.storekit")

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
        """把内存快照写进 JSON 冷备份（仅在标脏时）。

        ★ 只有**确实写出成功**才清 ``dirty``；写失败保留 ``dirty=True``（下次重试）
        并告警 —— 否则磁盘满/权限错时内存照旧、``hot_stats()`` 报 ``dirty:false``、
        ``flush_all()`` 还把该 Store 记进 ``written``（**丢了却报告已落盘**）。
        """
        if not getattr(self, "dirty", False):
            return False
        try:
            ok = self._write_file()
        except Exception as err:  # noqa: BLE001 - 子类实现本不应抛，防御性兜底
            logger.warning(f"[{type(self).__name__}] 冷备份落盘异常，保留脏标记：{err!r}")
            return False
        if not ok:
            logger.warning(f"[{type(self).__name__}] 冷备份落盘失败，保留脏标记（下次重试）")
            return False
        self.dirty = False
        return True

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        """原子写 JSON（``tmp + os.replace``）：中途失败 → 原文件保持完好。

        失败**抛异常**（由各 ``_write_file`` 记录具体异常并返回 False）；
        半截 tmp 会清掉，不留垃圾。磁盘上已有生产数据，格式必须与旧实现一致
        （``ensure_ascii=False`` + ``indent=2``）。
        """
        tmp = path.with_name(path.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)   # ★ 19.10.33：挪进 try —— 磁盘满时抛在这儿，
            #   以前半截 .tmp 会留在盘上（docstring 却说会清掉），现在一并清掉。
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    @staticmethod
    def _merge_missing(target: Dict[str, Any], incoming: Dict[str, Any]) -> int:
        """只把 ``incoming`` 中 ``target`` **没有**的键补进去（绝不覆盖已有键）。

        用于「热层 + 冷备份」载入并集：热层是权威，文件只补热层被 LRU 淘汰/丢过的键；
        方向恒为「补缺」，对更旧的文件值安全。返回补齐条数。
        """
        added = 0
        for key, value in (incoming or {}).items():
            if key not in target:
                target[key] = value
                added += 1
        return added

    def _write_json_file(self, data: Dict[str, Any]) -> bool:
        """写 JSON 冷备份：建目录 + 原子写 + **吞异常返回成败**（★ P2 口径）。

        为什么吞而不抛：调用方（各 ``_write_file``）拿返回值决定「清脏/保脏」，
        抛异常会让后台 flusher 直接把整轮落盘打断。失败必须返回 ``False``，
        否则磁盘满/权限错时会出现「丢了却报告已落盘」。
        """
        try:
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
            self._atomic_write_json(Path(self.file), data)
            return True
        except Exception as err:  # noqa: BLE001
            logger.error(f"[{type(self).__name__}] 写 {self.file} 失败（保留脏标记，待重试）：{err!r}")
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
    # ★ 19.11.23：加种当时的站点折扣真值（下载因子 ≤0）。qB 的 /torrents/info 不返回
    #   downloadvolumefactor，回读时只能靠这里留的底；老记录缺这个键 → 默认 False。
    free: bool = False


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
        """序列化成冷层/热层共用的 dict。

        为什么手写而不直接 ``asdict(self)``：子项要展平成 list of dict（否则嵌套
        dataclass 会在 ``json.dumps`` 里报错），字段顺序也要固定，方便对拍旧文件。
        """
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
        """从 dict 还原。

        必需字段直接下标取（缺了就抛）：一条没有 ``operation_id`` 的记录还原出来
        也没法用，静默补默认值只会让坏数据在账单里留个空壳。
        """
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
    # ★ 19.10.37：`last_error` 是否是「配置错」（粘性）。
    #   配置错（未配置保存目录 / 下载器不可用）不会因为「下一轮跑起来了」而消失，
    #   所以既不被 `record_run_start` 清、也不被 `settle` 的计数清；只有配置守卫
    #   重新判定为通过时才清（见 persistence.clear_run_error）。
    #   之前这两类错只写一条 error 日志，health 的 H1（看 last_error）永远不亮。
    last_error_sticky: bool = False
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
    # ★ 19.12.20：上一轮**每个阶段各自的执行结果**（key → {state, at, ms}）。
    #   为什么不能只用 last_phase：那是一个「当前位置」单值 —— 运行中能推出前几步已完成，
    #   但一轮结束被写成 done 就整片变绿，任务不跑（做种/停止模式）时又是空 → 五步全灰；
    #   两种情形都看不出「哪一步真的跑过、跑了多久、成没成」。这里逐阶段留痕，跑完也保留。
    run_stages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
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

    @staticmethod
    def upgrade(state: Any) -> Any:
        """把热重载前创建的旧实例**换代**到当前类，并补齐缺失字段的默认值。

        ★ 为什么必须有（19.10.37 实测踩过）：``MagicFlowStore`` 是进程级单例，MP 热重载
        只换它的 ``__class__``（见 persistence.__new__），但内存里既存的 ``TaskState``
        对象仍是**旧类**建的 —— 给 ``TaskState`` 加新字段后，旧实例上
        ① 读它 → ``AttributeError``（当时把 health 接口直接打 500）；
        ② 写它 → 属性能 ``setattr`` 上去，但旧 ``to_dict`` 不认识它 → 落盘时静默丢。
        换 ``__class__`` 后两个问题一起消失（同一对象、同一内存快照，只换方法表）。

        Args:
            state: 任务状态对象（None 原样返回）

        Returns:
            换代后的同一对象；布局不兼容等极端情况退化为「只补字段」不抛异常
        """
        if state is None:
            return state
        if type(state) is TaskState:
            return state
        try:
            state.__class__ = TaskState
        except TypeError:  # pragma: no cover - 布局不兼容（如 __slots__ 变更）
            pass
        for f in fields(TaskState):
            if hasattr(state, f.name):
                continue
            try:
                if f.default is not MISSING:
                    setattr(state, f.name, copy.deepcopy(f.default))
                elif f.default_factory is not MISSING:  # type: ignore[misc]
                    setattr(state, f.name, f.default_factory())  # type: ignore[misc]
            except Exception:  # noqa: BLE001 - 补不上不阻断，读侧还有 getattr 兜底
                pass
        return state

    def to_dict(self) -> dict:
        """序列化任务状态：集合转 list、字典键统一小写。

        为什么键要小写：infohash 在 qB / 站点 / 历史文件里大小写混用，
        落盘前统一口径，否则同一个种子会被当成两条（保护集/账本重复计数）。
        """
        return {
            "task_id": self.task_id,
            "last_run_at": self.last_run_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "last_error_sticky": self.last_error_sticky,
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
            "run_stages": {str(k): dict(v) for k, v in (self.run_stages or {}).items() if isinstance(v, dict)},
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
        """从 dict 还原并**容错**：缺字段用默认、空串当 None、键统一小写。

        为什么容错而不是严格：这份文件要跨版本读回（老版本没有新字段），一个字段
        缺失就整表加载失败 → 保护集/纳管标记全丢 → 会误删种。这里宁可丢一条脏字段。
        """
        return TaskState(
            task_id=d["task_id"],
            last_run_at=d.get("last_run_at", 0.0),
            last_success_at=d.get("last_success_at", 0.0),
            last_error=d.get("last_error"),
            last_error_sticky=bool(d.get("last_error_sticky", False)),
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
            run_stages={str(k): dict(v) for k, v in (d.get("run_stages") or {}).items() if isinstance(v, dict)},
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
# 冷层惯用法（原 5 个 Store 各抄一份，收在这里）
# ============================================================

def read_json_dict(
    path: Path,
    *,
    norm_key: Optional[Callable[[Any], str]] = None,
    norm_value: Optional[Callable[[Any], Any]] = None,
) -> Dict[str, Any]:
    """容错读 JSON 字典冷备份：文件不存在 / 坏 / 顶层非 dict → **返回空字典**。

    为什么吞异常而**不**往上报：冷备份是「热层丢了才用」的兜底，
    半截 JSON 多是上次写中断留下的；此时保留内存现状（调用方拿到空字典后通常
    只补缺、不清空）比让加载整体失败安全得多。坏文件本身留在盘上供事后取证。

    Args:
        path: 冷备份文件
        norm_key: 键归一（如 ``lambda k: str(k).lower()``），None = 原样
        norm_value: 值归一（如 ``dict`` / 自定义清洗）；**返回 None 表示丢弃该条目**
            —— 用来表达「只收 dict 值」这类过滤，省掉调用方再遍历一遍
    """
    try:
        if not Path(path).exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception:  # noqa: BLE001 - 见 docstring：坏文件不阻断加载
        return {}
    if not isinstance(loaded, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in loaded.items():
        try:
            normed = norm_value(value) if norm_value else value
        except Exception:  # noqa: BLE001 - 单条坏条目丢弃，不拖垮整表
            continue
        if normed is None:
            continue
        out[norm_key(key) if norm_key else key] = normed
    return out


def batch_kv_apply(
    bridge: "KvBridge",
    items: Dict[str, Any],
    key: Optional[str] = None,
    *,
    written: Optional[Dict[str, str]] = None,
    norm_key: Optional[Callable[[Any], str]] = None,
) -> bool:
    """把 ``items`` **差分**写进热层（一次 pipeline）。

    差分口径：内存值 JSON 指纹与上次写入相同 → 跳过；内存里已没有的键
    （仅全量模式）→ 删键。指纹本身存 ``written``（调用方持有，跟着 Store 走）。

    Args:
        bridge: 提供 ``kv`` / ``kv_ready()`` / ``kv_key()`` 的 Store
        items: 内存快照（调用方在锁内拷一份再传，避免边写边改）
        key: 只写这一个键；None = 全量差分（含删除已消失的键）
        written: 指纹表 ``{键: JSON}``，本函数就地把新指纹写回
        norm_key: 键归一，与 ``items`` 的键口径必须一致

    返回 ``True`` = 全部成功（或本来就无需写）；``False`` = 热层不可用/写失败，
    调用方据此退回「直写 JSON 冷备份」。
    """
    if not bridge.kv_ready():
        return False
    nk: Callable[[Any], str] = norm_key or (lambda x: str(x))
    marks: Dict[str, str] = written if written is not None else {}
    batch: Dict[str, Any] = {}
    for k in ([nk(key)] if key is not None else list(items)):
        item = items.get(k)
        if item is None:
            batch[bridge.kv_key(k)] = None
            continue
        fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if marks.get(k) == fingerprint:
            continue
        batch[bridge.kv_key(k)] = item
    if key is None:
        for gone in [x for x in marks if x not in items]:
            batch[bridge.kv_key(gone)] = None
            marks.pop(gone, None)
    if not batch:
        return True
    writes = {k: v for k, v in batch.items() if v is not None}
    drops = [k for k, v in batch.items() if v is None]
    ok = True
    if writes and not bridge.kv.set_many(writes):
        ok = False
    if drops and not bridge.kv.delete_many(drops):
        ok = False
    if ok:
        for k, item in items.items():
            if bridge.kv_key(k) in writes:
                marks[k] = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    return ok
