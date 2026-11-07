# -*- coding: utf-8 -*-
"""魔流 · hrbills —— 下载即开账（11.0.0 第二阶段：账单生效 + 存量回填）。

把「我们**自己下载**的种子」在 H&R 站上自动开一张 H&R 账单（原来只有辅种路径
``features/assets.py:352`` 开账，自下载路径是缺口）。

阶段演进：
  - **第一阶段（影子记账）**：只记账 + 出统计，``HR_BILLS_ENFORCE = False``，不改任何保护。
  - **第二阶段（本版）**：``HR_BILLS_ENFORCE = True`` —— 账单接入 ``features/hr.py::_hr_obligation``
    作为**第三来源**（与资源级/种子级取**并集**，只增保护、绝不减）；并在 ``_hrbills_tick`` 里
    做**存量回填**（给账本托管种补开账单，幂等，每轮限量）。

★ 一键回退：把 ``HR_BILLS_ENFORCE`` 改回 ``False`` 即恢复「不接保护」（其余逻辑照跑）。
  - ``HrBillsStore``：纯数据（零业务逻辑），JSON 持久化到 ``hr_bills.json``；
  - ``get_hr_bills_store``：模块级工厂（照 ``persistence.get_gate_store``），**绝不挂
    ``MagicFlowStore``**（进程级单例热重载不重建 → 新字段/新方法拿不到）；
  - ``HrBillsMixin``：开账 / 巡检（作废·结清·回填，只改账单状态）/ 干跑 / 统计。

★ 19.10.34：站点 ``myhr.php`` 对账（``HrReconcileMixin`` + ``HrReconcileCache``）已拆到
  ``features/hrreconcile.py`` —— 本文件只留**账单状态机**。「站点说你还欠什么」是只读的
  第三方视角，「账本记你欠什么」才由本文件维护，两者改动理由不同，见该模块 docstring。
"""

import json
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..tags import MARK_REUSE, RESCUE_TAG, is_reuse_copy
from ..fingerprint import fingerprint
from ..downloader_ops import seed_hours_for_hr
from ..persistence import _shared
from ..common import (
    HR_COMPLETE_RATIO_DEFAULT,
    HR_DEADLINE_WARN_HOURS_DEFAULT,
    HR_SEED_MARGIN_HOURS_DEFAULT,
)

def _rv_state() -> Any:
    """取报表快照失效信号（离线/未加载 → None，绝不因此影响写入）。"""
    m = sys.modules.get("magicflow_rv_state_v1")
    if m is None:
        try:
            from . import rvstate as m  # noqa: WPS433
        except Exception:  # noqa: BLE001
            return None
    return m


def _rv_invalidate() -> None:
    """★ 19.12.48（任务 96）：账单写成功后通知报表快照失效。

    收口位置 = **两个账单存储的全部写方法**，不是某个开账调用点 —— 开账、tick、
    人工结清、作废、批量清账、yema 升格都经过这里，任何一条都不会漏。
    异常一律吞掉：报表刷新是增强，绝不能反过来让账单写入失败。
    """
    try:
        st = _rv_state()
        if st is not None:
            st.bump()
    except Exception:  # noqa: BLE001
        pass


# ★ 11.0.0 第二阶段：账单接入保护。
#   一键回退：把本常量改回 ``False`` 即恢复「不接保护」（账单照记、回填照跑，只是
#   ``_hr_obligation`` 不再读账单 → 自下载种回到「仅资源级/种子级」判定）。
HR_BILLS_ENFORCE = True

# 连续多少天进度无增长 → 作废（死账）
# ★ 19.12.40：**不再作废/删账**。种还在 qB 却没进度 = 暂停/无 peer，正是 H&R 该挂住的
#   状态，删账等于「眼不见为净」。现在只记 ``stalled_at`` 计数，账单保留。
HR_BILLS_STALL_DAYS = 7.0

# ★ 19.12.40：qB 里找不到种子时，账单**默认保留**多少天才允许在「站端明确 clear」
#   的前提下销账。为什么不再「当轮直接删」：qB 抖动、recheck、刚被外部工具删了又加、
#   站点同步滞后都会让种子短暂缺席；当轮删账 = 义务凭空消失（保护没了、站端还欠）。
#   ``0`` = 永不自动销（孤儿只能人工 ``action=hrbills_purge_missing&confirm=1``）。
HR_BILLS_MISSING_TTL_DAYS = 30.0

# ★ 19.0.0：settled 行保留天数（挂够结清后仍暂存作幂等锚，防回填反复开/结；
# 到期即销）。种消失**不再**当轮直接销（19.12.40 起走 HR_BILLS_MISSING_TTL_DAYS）。
HR_BILLS_SETTLED_TTL_DAYS = 30.0

# ★ 11.7.0 逐种 H&R 标记（YemaPT ``hrPunishEnable`` 这类「无站点级规则、逐种开关」）。
#   一键回退：改 ``False`` → 忽略候选的逐种标记，退回「只认站点规则」的旧行为
#   （不影响 ``HR_BILLS_ENFORCE`` 这层总开关）。
HR_PER_TORRENT = True

# ★★ 11.8.0 站点 ``myhr`` 定期对账（**第三视角**）。
#   已有两条 H&R 巡检都不是站点视角：``_hrbills_tick`` 只对账本、``_hr_blindspot_scan``
#   只对本机。缺的一环是「**站点说欠、本机却没有种**」——账本永远看不见。
#   一键回退：改 ``False`` → 读+写全停，其余功能不变。
HR_RECONCILE_ENABLED = True
HR_RECONCILE_HOURS = 6.0
HR_RECONCILE_MAX_FETCH = 60
HR_RECONCILE_TTL = 1800.0
# ★ 19.12.41：默认**只抓首页**。旧值 6 配的是「上一页不满 10 条 → 已到末页」这条**猜**的
#   末页判据（实测四站分页控件无可用 href、无「共 N 条」）。完整性改由页头 H&R 聚合计数
#   交叉验证（``_hr_bar_cert``）；翻页既无证据也无必要。想临时深翻可调大，但**不能**
#   靠它判清。
HR_RECONCILE_MAX_PAGES = 1
HR_RECONCILE_BACKOFF_HOURS = (6.0, 12.0, 24.0)
HR_RECONCILE_TIME_BUDGET = 240.0
HR_RECONCILE_TAG_SUFFIX = "补种"

# ★★ 19.12.4 站端确认闸门（Master 2026-11-03 23:40「本地说够了站端还欠的逻辑再搞下」）。
#   账单「挂够」= 本地 qB 活跃做种 ≥ ``need_h + margin``。但**债主是站端**：
#   CARPT 7 颗账本记 113~151h 而 myhr 仍欠 2~3h（差 92h 全是被站端忽略的墙钟）。
#   于是三层：
#     ① 结清前先看站端最近一轮 ``myhr.php`` 对账（``hr_reconcile.json``）：
#        站端还欠 → **不结清**（账单留在 active，继续挂）；
#     ② 已 settled 的账单，站端又说欠 → **重开**（settled → active，保挂不中断）；
#     ③ 站端说欠的 hash 一律进保护集合（**即使本地工时已够**）—— 否则保挂一撤、
#        种被暂停、站端计时立刻停表，就永远还不清（这个闭环依赖这一条）。
#   证据**只读缓存、不在 tick 里联网**（联网是 ``_hr_reconcile_round`` 每 6h 的活）；
#   剩余时间按「证据时刻」做时间衰减外推（保守方向：真被暂停时站端其实不衰减 →
#   我们多挂，而不是少挂）。
#   一键回退：改 ``False`` → 回到「只信本地工时」的旧行为。
HR_SETTLE_SITE_GATE = True
#   站端证据可信上限（小时）：超过就不再用它推剩余（外推到 0 也不当「清了」），
#   降级成 unknown（按本地工时判），避免拿一份很旧的报告去结清。
HR_SITE_EVIDENCE_MAX_HOURS = 48.0
#   欠账索引的进程内复用窗口（秒）：``_hr_bill_owed_hashes`` / ``_hr_obligation``
#   每轮会被调几十次，重建索引要遍历全部报告 → 60s 内复用同一份。
HR_SITE_DEBT_TTL = 60.0

# 账单状态全集
BILL_STATE_ACTIVE = "active"
BILL_STATE_PENDING = "pending"
BILL_STATE_SETTLED = "settled"
BILL_STATE_VOID = "void"          # ★ 19.12.43：**墓碑保留**（不再「作废即删」）——见 _hrbills_void
BILL_STATE_BREACHED = "breached"  # ★ 11.11.0：欠 H&R 的种消失（违约/待处理）——不是 void，保护不解除

# 账单规则来源
RULE_HIT_AND_RUN = "hit_and_run"
RULE_SITE_HR = "site_hr"
RULE_UNKNOWN = "unknown"

# ★ 19.12.46（任务 89 · 人工结清保护闭环）：
#   `settlement_method` 的「人工结清」取值。**唯一判据**——不得由 settled 状态、
#   操作人、原因或 `taken_by` 反推（历史 auto 账单也有 settled_at，settled_by 也可能是
#   人名）。所有自动路径（重开 / TTL / 降级 / 删除 / 作废 / 跨模块 patch）都必须用
#   `_is_manual_settled()` 判，不要各处自己写字符串比较。
HR_MANUAL_SETTLE = "manual"

# ★ 任务 98 · 受控纠错重开 + append-only 审计事件 --------------------------------
#   任务 89 拍板「人工结清不可被自动任务推翻」；任务 97 审计发现这条保护是**结构性
#   跳过**（manual 账单根本不读站端），于是「站端可靠证据证明仍欠」也无法纠错。
#   任务 98 放开一条**唯一、受控**的例外：只有 myhr 证据八项全达标才允许重开。
HR_REOPEN_SETTLE = "reopened"   # 重开后的 settlement_method：离开 manual → 8 个保护点自动让位
HR_RECONCILE_REOPEN = True      # 总开关：False = 完全退回任务 89 的「manual 不重开」
HR_REOPEN_EVIDENCE_MAX_HOURS = 48.0   # 纠错证据可信上限（与站端闸门同源，单独常量便于收紧）

# 事件类型（append-only 表 mf_bill_events 的 event_type 取值）
EVT_MANUAL_SETTLED = "manual_settled"
EVT_AUTO_SETTLED = "auto_settled"
EVT_REOPENED = "reopened"
EVT_MANUAL_VOID = "manual_void"
EVT_AUTO_VOID = "auto_void"
EVT_LEGACY_MANUAL = "legacy_manual_settled"  # 历史账单无事件 → 纠错时补录，不假造操作时刻
EVT_SYSTEM_ACTOR = "system/hrbills_tick"

# 事件行字段（与 db.BillEventRow 逐列同名；JSON / PG 双后端共用一份投影）
BILL_EVENT_FIELDS = (
    "hash", "event_type", "at", "actor", "reason",
    "prev_state", "new_state", "bill_snapshot",
    "evidence_source", "evidence_at", "evidence_digest", "dedup_key",
)

# 人工作废「人工结清账单」的显式授权作用域。传布尔就能绕过 = 保护形同虚设，
# 所以要求调用方显式给出这个串 + 操作人 + 纠错原因三件套（见 `_manual_void_override_ok`）。
MANUAL_VOID_SCOPE = "manual-void"

# ★ 11.11.1：站点「实际做种达标小时」的保守兜底（站点规则 seed_need_hours 取不到时）。
#   与 common.CROSSSEED_SEED_HOURS_DEFAULT 同值；不引 common（其拉进 MP 依赖，会破坏离线测试）。
HR_NEED_HOURS_DEFAULT = 24.0

# ★ 11.11.1：辅种（复用/补源）不是「本账单口径的真实下载」→ 开账/回填一律跳过。
#   - MARK_REUSE(魔流-辅种)：复用副本（add_torrent_reuse，paused+recheck）→ 无真实下载。
#   - RESCUE_TAG(魔流-补源)：死种补源副本，来源站被 rescue_source_blocked 保证 hr=False。
#  MP 写的「已整理/辅种」(ASSET_TAGS) 是**真实下载被整理**，仍欠 H&R → 不跳过。
# ★ 19.10.11：CROSSSEED_TAG **从跳过名单移除**。跨站来源份是**真实下载**（只是下在他站
#   的免费种上），欠的是**来源站**的 H&R —— 与刷流/音乐/点播完全同性质。旧注释说
#   「H&R 由 assets.py 资源账记」，实际是 `CrossSeedSources` 自己另算一套工时（seeded_sec
#   vs hours），与账单 seeded_h 同源却各存一份快照 → 规则一改两份就漂。现改为：
#   下完那一刻直接开账单（`_crossseed_protect_source` → `_hrbills_open`），工时只认账单。
_SKIP_BILL_TAGS = (MARK_REUSE, RESCUE_TAG)


def _skip_hr_bill(tags: Any) -> bool:
    """该种是否**不该**在本账单口径开账（跨站/复用/补源副本）。"""
    return any(str(x).strip() in _SKIP_BILL_TAGS for x in (tags or []))


def _is_manual_settled(bill: Any) -> bool:
    """★ 19.12.46（任务 89）：这张账单是不是「人工结清」。

    **唯一判据** ``settlement_method == "manual"``。不传 dict / 无该字段 / 值为 None
    → False（历史数据与自动结清一律 False，保持既有兼容行为）。
    """
    return isinstance(bill, dict) and \
        str(bill.get("settlement_method") or "") == HR_MANUAL_SETTLE


def _manual_void_override_ok(manual_override: Any) -> Dict[str, Any]:
    """校验「作废一张人工结清账单」的授权凭证；无效返回 ``{}``（= 拒绝）。

    三件套缺一不可：``authorization`` 必须是 ``MANUAL_VOID_SCOPE``（显式作用域串，
    布尔/``1`` 一律不认，避免一个参数就把保护绕过去）、``authorized_by``（操作人）、
    ``reason``（纠错原因）。返回归一化后的 dict 供审计事件落账。
    """
    if not isinstance(manual_override, dict):
        return {}
    if str(manual_override.get("authorization") or "").strip() != MANUAL_VOID_SCOPE:
        return {}
    by = str(manual_override.get("authorized_by") or "").strip()
    reason = str(manual_override.get("reason") or "").strip()
    if not by or not reason:
        return {}
    return {"authorization": MANUAL_VOID_SCOPE,
            "authorized_by": by[:64], "reason": reason[:200]}


def _void_ok(res: Any) -> bool:
    """``_hrbills_void`` 的返回值是否代表「真的作废了」。

    ★ 19.12.46：作废被保护拦下时返回 ``{"error": "manual_protected", ...}``（truthy），
    调用方若只写 ``if self._hrbills_void(...)`` 就会把被拒的算成成功 —— 统一走这里判。
    """
    return isinstance(res, dict) and not res.get("error")


class HrBillsStore:
    """纯数据存储：``hash -> 账单 dict``。零业务逻辑。

    持久化：``hr_bills.json``（原子写 tmp→rename）；``save()`` 节流（热层即时、
    文件至少间隔 ``FILE_MIN_INTERVAL`` 秒）；``load()`` 容错（坏文件 → 空）。
    """

    kv_region = "hrbills"
    FILE_MIN_INTERVAL = 5.0

    EVENTS_FILE = "hr_bill_events.json"

    def __init__(self, data_dir: Path, kv: Any = None):
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "hr_bills.json"
        self.bills: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._last_file_write = 0.0
        self._pending = False
        self._dirty: Set[str] = set()   # ★ 脏键集合：save/flush 只写变化的键（避免 O(N) 全量热层写）
        self.kv = kv
        # ★ 任务 98：append-only 审计事件（JSON 降级后端）。与 bills **共用同一把锁**，
        #   事件追加 + 账单状态变更必须是同一个临界区，才不会「状态改了历史没记」。
        self.events_file = self.data_dir / self.EVENTS_FILE
        self.events: List[Dict[str, Any]] = []
        self._event_keys: Set[str] = set()
        self.load()
        self._load_events()

    # ------------------------------------------------------ 热层桥接（可选）
    def kv_bind(self, kv: Any) -> None:
        """重绑热层（工厂每次调用都会做，保证热重载后拿到新热层）。"""
        self.kv = kv

    def _kv_ready(self) -> bool:
        kv = getattr(self, "kv", None)
        if kv is None:
            return False
        try:
            return bool(kv.available())
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------ 载入 / 持久化
    def load(self) -> None:
        """载入：热层优先；热层无数据 → 读文件并回灌；坏文件容错为空。"""
        try:
            if self._kv_ready():
                rows = self.kv.items(self.kv_region + ":")
                if rows:
                    out: Dict[str, Dict[str, Any]] = {}
                    for key, value in (rows or {}).items():
                        if isinstance(value, dict):
                            out[str(key).split(":", 1)[-1].lower()] = dict(value)
                    if out:
                        self.bills = out
                        return
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.file.exists():
                with open(self.file, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if isinstance(data, dict):
                    self.bills = {
                        str(k).strip().lower(): dict(v)
                        for k, v in data.items()
                        if isinstance(v, dict)
                    }
        except Exception:  # noqa: BLE001
            self.bills = {}

    def _write_file(self, strict: bool = False) -> None:
        """写账单冷备。``strict=True`` 时**不吞异常**（任务 98 原子事件写用）。"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(self.file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.bills, f, ensure_ascii=False, indent=2)
            tmp.replace(self.file)
        except Exception:  # noqa: BLE001
            if strict:
                raise
            pass

    # ------------------------------------------------------ ★ 任务 98：审计事件（JSON 后端）
    def _load_events(self) -> None:
        """载入 append-only 事件档案；坏文件容错为空（**不删文件**，交给人工修）。"""
        try:
            if self.events_file.exists():
                with open(self.events_file, "r", encoding="utf-8") as f:
                    data = json.load(f) or []
                if isinstance(data, list):
                    self.events = [dict(x) for x in data if isinstance(x, dict)]
        except Exception:  # noqa: BLE001
            self.events = []
        self._event_keys = {
            str(e.get("dedup_key") or "").strip()
            for e in self.events if str(e.get("dedup_key") or "").strip()
        }

    def _write_events_file(self) -> None:
        """写事件档案（**故意不吞异常**）：写失败必须让整次状态变更一起失败。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.events_file.with_name(self.events_file.name + ".tmp")
        # ★ 项目铁律：写文件用 write_bytes（write_text 在 Windows 会静默 LF→CRLF）。
        tmp.write_bytes(json.dumps(self.events, ensure_ascii=False, indent=2).encode("utf-8"))
        tmp.replace(self.events_file)

    def _append_events_locked(self, events: Any) -> Tuple[int, str]:
        """在 ``self._lock`` 内追加事件。返回 ``(新增条数, 错误码)``。

        ``dedup_key`` 已存在 → 跳过（幂等）。写文件失败 → **内存回滚**并返回错误码，
        调用方据此放弃整次账单状态变更（fail-closed，绝不留下「有状态没历史」）。
        """
        new: List[Dict[str, Any]] = []
        for e in (events or []):
            if not isinstance(e, dict):
                continue
            key = str(e.get("dedup_key") or "").strip()[:160]
            if key and key in self._event_keys:
                continue
            row = {c: e.get(c) for c in BILL_EVENT_FIELDS}
            row["hash"] = str(row.get("hash") or "").strip().lower()[:64]
            try:
                row["at"] = float(row.get("at") or 0.0) or time.time()
            except (TypeError, ValueError):
                row["at"] = time.time()
            row["dedup_key"] = key
            new.append(row)
        if not new:
            return 0, ""
        mark = len(self.events)
        self.events.extend(new)
        try:
            self._write_events_file()
        except Exception as err:  # noqa: BLE001
            del self.events[mark:]
            return 0, "event_write_failed:%s" % err
        for r in new:
            if r.get("dedup_key"):
                self._event_keys.add(str(r["dedup_key"]))
        return len(new), ""

    def events_for(self, hash_string: str = "", limit: int = 0) -> List[Dict[str, Any]]:
        """按 hash 读事件历史（默认全量、按时间升序）；``hash_string=""`` = 全部。"""
        h = str(hash_string or "").strip().lower()
        with self._lock:
            rows = [dict(e) for e in self.events
                    if not h or str(e.get("hash") or "").strip().lower() == h]
        rows.sort(key=lambda x: (float(x.get("at") or 0.0), str(x.get("event_type") or "")))
        if limit and limit > 0:
            rows = rows[-int(limit):]
        return rows

    def _write_hot(self, keys: Optional[Any] = None) -> None:
        """写热层。``keys=None`` = 全量（强制），否则只写指定键（增量）。"""
        if not self._kv_ready():
            return
        try:
            if keys is None:
                keys = list(self.bills.keys())
            batch = {f"{self.kv_region}:{k}": self.bills[k] for k in keys if k in self.bills}
            if batch:
                self.kv.set_many(batch)
        except Exception:  # noqa: BLE001
            pass

    def save(self, force: bool = False, strict: bool = False) -> None:
        """保存：热层（**只写脏键**）+ 文件节流（``force`` 立即落盘）。

        ``strict=True``（★ 任务 98）：文件写失败**抛异常**而不是静默吞掉，供
        ``patch_if(events=...)`` 做「事件 + 状态」同生共死的回滚。普通写路径行为不变。
        """
        with self._lock:
            _dirty = set(self._dirty)
            self._dirty.clear()
            if _dirty or force:
                try:
                    self._write_hot(sorted(_dirty) if _dirty else None)
                except Exception:  # noqa: BLE001
                    pass
            now = time.time()
            if force or (now - self._last_file_write) >= self.FILE_MIN_INTERVAL:
                self._write_file(strict=strict)
                self._last_file_write = time.time()
                self._pending = False
            else:
                self._pending = True

    def flush(self) -> None:
        """把待写热层 + 冷备落盘（巡检收尾 / 停机前调用，防节流丢末笔）。"""
        with self._lock:
            _dirty = set(self._dirty)
            self._dirty.clear()
            if _dirty:
                try:
                    self._write_hot(sorted(_dirty))
                except Exception:  # noqa: BLE001
                    pass
            if _dirty or self._pending or (time.time() - self._last_file_write) >= self.FILE_MIN_INTERVAL:
                self._write_file()
                self._last_file_write = time.time()
                self._pending = False

    # ------------------------------------------------------ 对外（纯数据）
    def get(self, hash_string: str) -> Optional[Dict[str, Any]]:
        h = str(hash_string or "").strip().lower()
        return self.bills.get(h)

    def put(self, hash_string: str, bill: Dict[str, Any],
            save: bool = True) -> Optional[Dict[str, Any]]:
        """写入账单；同 hash 已存在 → 返回已有账单（不重复开）。

        ``save=False``：只标脏，由调用方结尾统一 ``flush()`` —— 批量开账（回填 200 张）
        走这条，避免「每张一次全量热层写」把一轮拖到分钟级。
        """
        h = str(hash_string or "").strip().lower()
        with self._lock:
            if h in self.bills:
                return self.bills[h]
            self.bills[h] = dict(bill)
            self._dirty.add(h)
            _rv_invalidate()
            if save:
                self.save()
            return self.bills[h]

    def patch(self, hash_string: str, save: bool = True,
              **fields: Any) -> Optional[Dict[str, Any]]:
        """改字段（``save=False`` 同 ``put``：只标脏，等结尾一次性 flush）。"""
        h = str(hash_string or "").strip().lower()
        with self._lock:
            b = self.bills.get(h)
            if not isinstance(b, dict):
                return None
            b.update(fields)
            self._dirty.add(h)
            _rv_invalidate()
            if save:
                self.save()
            return b

    def patch_if(self, hash_string: str, expect: Any = None,
                 save: bool = True, events: Any = None, **fields: Any) -> Dict[str, Any]:
        """**条件写（CAS）**：仅当账单当前值仍等于 ``expect`` 时才改字段。

        ★ 任务 98：``events`` 是可选的 append-only 审计事件列表。给定时，事件的
        落盘与账单状态变更在**同一把锁**内完成，且强制 ``force + strict`` 落盘：
        事件写失败 / 账单写失败 → 两边一起回滚，返回 ``{"ok": False,
        "reason": "event_write_failed:*" | "bill_write_failed:*"}``。
        不允许「账单重开了但历史没记」，也不允许「历史记了但状态没变」。

        ★ 19.12.47（任务 91）为什么必须有它：``patch`` 是**整块覆盖**，而调用方的判定
        基于**更早**读到的快照（``_hrbills_tick`` 的 ``store.all()``）。两者之间若有人工
        结清落地，``patch`` 会把人工结论盖掉 —— 实测 ``settlement_method`` 从 ``manual``
        被写成 ``auto``、``settled_by`` 还留着（行自相矛盾），8 个 manual 保护点同时失效
        且**无日志**。CAS 把「读到的值」变成写前提，冲突即放弃本轮。

        ``expect``：``{字段: 期望值}``；值为 ``None`` 表示期望「空/无此结论」。
        返回三态（**调用方必须判 ``ok``**，不得只看有没有异常）：
          · ``{"ok": True,  "reason": "",        "row": {...}}``  写入成功
          · ``{"ok": False, "reason": "missing", "row": None}``   行不存在
          · ``{"ok": False, "reason": "conflict","row": {...}}``  期望值不符（**未写入**）
        """
        h = str(hash_string or "").strip().lower()
        with self._lock:
            b = self.bills.get(h)
            if not isinstance(b, dict):
                return {"ok": False, "reason": "missing", "row": None}
            for k, v in (expect or {}).items():
                if b.get(k) != v:
                    return {"ok": False, "reason": "conflict", "row": dict(b)}
            evs = list(events) if isinstance(events, (list, tuple)) else []
            mark = len(self.events)
            keys_before = set(self._event_keys)
            if evs:
                _n, _err = self._append_events_locked(evs)
                if _err:
                    # 事件落盘失败 → 账单一步都不动（fail-closed）
                    return {"ok": False, "reason": _err, "row": dict(b)}
            before = dict(b)
            b.update(fields)
            self._dirty.add(h)
            if evs:
                try:
                    self.save(force=True, strict=True)
                except Exception as err:  # noqa: BLE001
                    self.bills[h] = before
                    del self.events[mark:]
                    self._event_keys = keys_before
                    try:
                        self._write_events_file()
                    except Exception:  # noqa: BLE001
                        pass
                    return {"ok": False, "reason": "bill_write_failed:%s" % err,
                            "row": before}
            elif save:
                self.save()
            _rv_invalidate()
            return {"ok": True, "reason": "", "row": dict(b),
                    "events": len(evs) if evs else 0}

    def drop(self, hash_string: str) -> bool:
        """删除一张账单（**误开账单清理 / 人工兜底**用，正常作废走 ``_hrbills_void``）。"""
        h = str(hash_string or "").strip().lower()
        with self._lock:
            if h not in self.bills:
                return False
            del self.bills[h]
            self._dirty.discard(h)
            try:
                self.kv.delete(f"{self.kv_region}:{h}")
            except Exception:  # noqa: BLE001
                pass
            self._write_file()
            _rv_invalidate()
            return True

    def drop_void(self) -> int:
        """批量删除所有 ``state=void`` 墓碑。**只作人工清理入口，tick 已不再调用**。

        ★ 19.12.43：墓碑是「这颗种已被判为不欠」的唯一凭证，删了就等于**允许回填
        重新开账**（``_hrbills_backfill`` 幂等判据就是 ``store.get(h)`` 是否存在）。
        所以 ``_hrbills_tick`` 每轮调用 ``drop_void()`` 的老逻辑已移除 —— 本方法只留给
        「确认墓碑过期、要人工重开」的场合。返回删除条数。
        """
        with self._lock:
            voids = [h for h, b in self.bills.items()
                     if isinstance(b, dict) and str(b.get("state") or "") == BILL_STATE_VOID]
            if not voids:
                return 0
            for h in voids:
                del self.bills[h]
                self._dirty.discard(h)
            try:
                self.kv.delete_many([f"{self.kv_region}:{h}" for h in voids])
            except Exception:  # noqa: BLE001
                pass
            self._write_file()
            _rv_invalidate()
            return len(voids)

    def drop_many(self, hashes: Any) -> int:
        """批量删除指定 hash 的账单（误开账单清理）。返回删除条数。"""
        with self._lock:
            hs = [str(h or "").strip().lower() for h in (hashes or [])]
            hs = [h for h in hs if h in self.bills]
            if not hs:
                return 0
            for h in hs:
                del self.bills[h]
                self._dirty.discard(h)
            try:
                self.kv.delete_many([f"{self.kv_region}:{h}" for h in hs])
            except Exception:  # noqa: BLE001
                pass
            self._write_file()
            _rv_invalidate()
            return len(hs)

    def drop_many_if(self, items: Any) -> Dict[str, Any]:
        """**条件批量删**：每项 ``(hash, expect)``，当前值仍等于 ``expect`` 才删。

        ★ 19.12.47（任务 91）：tick 的销账/复用份清理都是「按快照判定 → 事后批量删」，
        期间若有人工结清落地，删行会让 ``_hrbills_backfill`` 的幂等判据（行存在）失效 →
        同 hash 被重开成 active，人工结论反转成「还欠」。条件删除把判定固化成删除前提。

        返回 ``{"dropped": [...], "skipped": [...]}``（skipped = 行不存在或期望值已变）。
        """
        out: Dict[str, Any] = {"dropped": [], "skipped": []}
        with self._lock:
            for item in (items or []):
                try:
                    hs = item[0]
                    expect = item[1] if len(item) > 1 else None
                except Exception:  # noqa: BLE001
                    continue
                h = str(hs or "").strip().lower()
                b = self.bills.get(h)
                if not isinstance(b, dict):
                    out["skipped"].append(h)
                    continue
                if any(b.get(k) != v for k, v in (expect or {}).items()):
                    out["skipped"].append(h)
                    continue
                del self.bills[h]
                self._dirty.discard(h)
                out["dropped"].append(h)
            if out["dropped"]:
                try:
                    self.kv.delete_many([f"{self.kv_region}:{h}" for h in out["dropped"]])
                except Exception:  # noqa: BLE001
                    pass
                self._write_file()
                _rv_invalidate()
        return out

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self.bills)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return _bills_stats(dict(self.bills))



def _bills_stats(bills: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """账单分桶统计（JSON / PG 两种后端共用同一口径）。"""
    out: Dict[str, Any] = {"total": 0, "by_state": {}, "by_rule": {}, "by_site": {},
                           "no_site": 0, "opened_by": {}}
    for b in bills.values():
        if not isinstance(b, dict):
            continue
        out["total"] = int(out["total"]) + 1
        st = str(b.get("state") or "")
        out["by_state"][st] = int(out["by_state"].get(st) or 0) + 1
        ru = str(b.get("rule") or "")
        out["by_rule"][ru] = int(out["by_rule"].get(ru) or 0) + 1
        si = str(b.get("site") or "")
        out["by_site"][si] = int(out["by_site"].get(si) or 0) + 1
        if not si:
            out["no_site"] = int(out["no_site"]) + 1
        ob = str(b.get("opened_by") or "")
        out["opened_by"][ob] = int(out["opened_by"].get(ob) or 0) + 1
    return out


def _mfdb_module() -> Any:
    """懒取插件 db 模块（离线无 sqlalchemy → None，调用方走 JSON 降级）。"""
    try:
        from .. import db as mfdb  # noqa: WPS433
        return mfdb
    except Exception:  # noqa: BLE001
        return None


class PgHrBillsStore(HrBillsStore):
    """mf_bills 表后端（★ 19.0.0 存储收口：hr_bills.json + Redis hrbills:* → PG）。

    - 真值源 = PG 表 ``mf_bills``，直写直读（每操作一事务）；无热层、无 JSON 冷备、
      无节流 —— ``save``/``flush``/``load`` 全部兼容空实现，调用面签名不变。
    - ``put`` 时 ``fp`` 为空 → **反查 ``mf_seed[hash].resource_id`` 强制填**（修 18.x
      回填硬写空串、账单只能靠 hash 挂的根因；见 db.BillRow 文档）。
    - 离线（无 app.* / 无 sqlalchemy）：工厂不会选本类；即便误入，读返回空、写返回
      入参，不会碰文件。
    """

    # BillRow 业务列（hash/created/updated 由 store 自己管）
    # ★ 19.12.43（P0 持久化契约）：补 5 个「代码在写、此前不在列投影里 → PG 路径静默丢」
    #   的字段：src（义务来源）/ missing_since（qB 缺席起点，缺席 TTL 闸门）/
    #   stalled_at（停滞标记）/ settle_block + settle_block_at（结清被挡原因/时刻）。
    #   与 db.BillRow 逐列同名；tools/test_bills_pg_contract.py 双向钉住。
    # ★ 19.12.44（人工结清）：+3 字段 settlement_method（auto/manual，None=auto）/
    #   settled_by（操作人）/ settlement_reason（结清原因）。settled_at 已有。
    _FIELDS = ("site", "rule", "state", "fp", "need_h", "seeded_h", "progress",
               "last_progress", "last_progress_at", "title", "opened_at", "opened_by",
               "settled_at", "breached_at", "voided_at", "void_reason",
               "alive", "last_seen", "seen_by",
               "src", "missing_since", "stalled_at", "settle_block", "settle_block_at",
               "settlement_method", "settled_by", "settlement_reason")

    def __init__(self, data_dir: Path, kv: Any = None):
        # 不调父类 __init__（其会 load() JSON——PG 模式下那不是真值源）
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "hr_bills.json"
        self.bills: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._last_file_write = 0.0
        self._pending = False
        self._dirty: Set[str] = set()
        self.kv = kv
        # ★ 任务 98：PG 后端事件走 mf_bill_events 表；这几个属性只为保持双后端接口同形。
        self.events_file = self.data_dir / self.EVENTS_FILE
        self.events: List[Dict[str, Any]] = []
        self._event_keys: Set[str] = set()

    # ------------------------------------------------------ 兼容面（no-op）
    def load(self) -> None:
        return None

    def save(self, force: bool = False, strict: bool = False) -> None:
        return None

    def flush(self) -> None:
        return None

    # ------------------------------------------------------ 内部
    def _run(self, fn: Any, default: Any = None) -> Any:
        """在 PG 会话里跑 ``fn(sess, mfdb)``；离线/异常 → ``default``。"""
        mf = _mfdb_module()
        if mf is None or not mf.db_available():
            return default
        try:
            with mf.db_session() as sess:
                out = fn(sess, mf)
                sess.commit()
                return out
        except Exception:  # noqa: BLE001
            return default

    @classmethod
    def _to_dict(cls, row: Any) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for c in cls._FIELDS:
            out[c] = getattr(row, c, None)
        return out

    # ------------------------------------------------------ 对外（同 HrBillsStore API）
    def get(self, hash_string: str) -> Optional[Dict[str, Any]]:
        h = str(hash_string or "").strip().lower()
        if not h:
            return None

        def _q(sess: Any, mf: Any) -> Optional[Dict[str, Any]]:
            row = sess.get(mf.BillRow, h)
            return self._to_dict(row) if row is not None else None

        return self._run(_q)

    def put(self, hash_string: str, bill: Dict[str, Any],
            save: bool = True) -> Optional[Dict[str, Any]]:
        h = str(hash_string or "").strip().lower()
        if not h:
            return None
        bill = bill if isinstance(bill, dict) else {}
        touched = [False]

        def _op(sess: Any, mf: Any) -> Optional[Dict[str, Any]]:
            row = sess.get(mf.BillRow, h)
            if row is not None:  # 幂等：同 hash 已存在 → 返回已有账单
                return self._to_dict(row)
            now = time.time()
            kw = {c: bill.get(c) for c in self._FIELDS if c in bill}
            # ★ fp 强制填：调用方没给（回填路径）→ 反查 mf_seed
            if not str(kw.get("fp") or "").strip():
                seed = sess.get(mf.SeedRow, h)
                rid = str(getattr(seed, "resource_id", "") or "").strip() if seed else ""
                if rid:
                    kw["fp"] = rid
            row = mf.BillRow(hash=h, created=now, updated=now, **kw)
            sess.add(row)
            sess.flush()
            touched[0] = True
            return self._to_dict(row)

        res = self._run(_op)
        if res is not None and touched[0]:
            _rv_invalidate()
        return res

    def patch(self, hash_string: str, save: bool = True,
              **fields: Any) -> Optional[Dict[str, Any]]:
        h = str(hash_string or "").strip().lower()
        if not h:
            return None

        touched = [False]

        def _op(sess: Any, mf: Any) -> Optional[Dict[str, Any]]:
            row = sess.get(mf.BillRow, h)
            if row is not None:
                for k, v in fields.items():
                    if k in self._FIELDS:
                        setattr(row, k, v)
                row.updated = time.time()
                sess.flush()
                touched[0] = True
            return self._to_dict(row) if row is not None else None

        res = self._run(_op)
        if res is not None and touched[0]:
            _rv_invalidate()
        return res

    @staticmethod
    def _insert_events_tx(sess: Any, mf: Any, events: Any) -> int:
        """★ 任务 98：在**同一个 PG 事务**里插入 append-only 事件行。

        与账单 ``UPDATE … WHERE`` 共用 ``sess``：事件 INSERT 抛异常 → ``_run`` 不
        commit → 整次状态变更回滚（绝不会出现「账单重开了但历史没记」）。
        ``dedup_key`` 已存在则跳过，保证同一纠错事件幂等。表不存在（迁移未跑）→
        直接抛，让本次写入按 ``store_unavailable`` 失败，而不是静默丢审计。
        """
        Row = getattr(mf, "BillEventRow", None)
        if Row is None:
            raise RuntimeError("mf_bill_events 模型缺失（迁移未完成）")
        n = 0
        for e in (events or []):
            if not isinstance(e, dict):
                continue
            key = str(e.get("dedup_key") or "").strip()[:160]
            if key and sess.query(Row).filter(Row.dedup_key == key).first() is not None:
                continue
            kw = {c: e.get(c) for c in BILL_EVENT_FIELDS}
            kw["hash"] = str(e.get("hash") or "").strip().lower()[:64]
            try:
                kw["at"] = float(e.get("at") or 0.0) or time.time()
            except (TypeError, ValueError):
                kw["at"] = time.time()
            kw["dedup_key"] = key
            sess.add(Row(**kw))
            n += 1
        return n

    @staticmethod
    def _event_row_dict(row: Any) -> Dict[str, Any]:
        return {c: getattr(row, c, None) for c in BILL_EVENT_FIELDS}

    def events_for(self, hash_string: str = "", limit: int = 0) -> List[Dict[str, Any]]:
        """按 hash 读事件历史；离线 / 表缺失 → 空列表（展示层按「兼容历史」渲染）。"""
        h = str(hash_string or "").strip().lower()

        def _q(sess: Any, mf: Any) -> List[Dict[str, Any]]:
            Row = getattr(mf, "BillEventRow", None)
            if Row is None:
                return []
            q = sess.query(Row)
            if h:
                q = q.filter(Row.hash == h)
            rows = [self._event_row_dict(r) for r in q.all()]
            rows.sort(key=lambda x: (float(x.get("at") or 0.0),
                                     str(x.get("event_type") or "")))
            return rows[-int(limit):] if limit and limit > 0 else rows

        return self._run(_q, default=[])

    def patch_if(self, hash_string: str, expect: Any = None,
                 save: bool = True, events: Any = None, **fields: Any) -> Dict[str, Any]:
        """**条件写（CAS）· 存储层原子版**（★ 19.12.47 / 任务 91）。

        实现：**单条** ``UPDATE mf_bills SET … WHERE hash = ? AND state IS NOT DISTINCT
        FROM ? AND settlement_method IS NOT DISTINCT FROM ?``，用 ``rowcount`` 判成败。
        PG 在 READ COMMITTED 下对同一行加行锁、并对**更新后的行版本**重新求值 WHERE →
        两个并发的条件更新里**最多一个**拿到 ``rowcount=1``，另一个必然 0。因此这是
        **跨进程/跨实例**安全的保护（不依赖进程内锁，也不依赖"只有一个实例"这个假设）。

        ★ 与 ``patch`` 的区别：``patch`` 的 ``sess.get + setattr + flush`` 是 ORM 读-改-写，
        无论期间谁改过都照写不误；本方法把「判定依据」搬进 WHERE。

        ★ ``_run`` 会吞异常并返回 default —— 那是**失败**，不是「0 行受影响」，两者必须
        区分：default 映射为 ``store_unavailable``（调用方按失败处理，绝不当作成功）。

        返回 ``{"ok": bool, "reason": ""|"missing"|"conflict"|"store_unavailable", "row": dict|None}``。
        """
        h = str(hash_string or "").strip().lower()
        if not h:
            return {"ok": False, "reason": "missing", "row": None}

        def _cond(q: Any, mf: Any, exp: Any) -> Any:
            for k, v in (exp or {}).items():
                if k not in self._FIELDS:
                    continue
                col = getattr(mf.BillRow, k)
                q = q.filter(col.is_(None) if v is None else col == v)
            return q

        def _op(sess: Any, mf: Any) -> Dict[str, Any]:
            # ★ 先 UPDATE 再判（不要先 SELECT）：PG 的 ``UPDATE … WHERE`` 会在拿到行锁
            #   之后**对更新后的行版本重新求值谓词**，所以并发下最多一个拿到 rowcount=1；
            #   而「先读后写」会让本事务先取得读快照，反而在快照隔离后端上引发升级冲突。
            payload = {k: v for k, v in (fields or {}).items() if k in self._FIELDS}
            payload["updated"] = time.time()
            n = int(_cond(sess.query(mf.BillRow).filter(mf.BillRow.hash == h), mf, expect)
                    .update(payload, synchronize_session=False) or 0)
            evs = list(events) if isinstance(events, (list, tuple)) else []
            # ★ 任务 98：只有 CAS 真正拿到 rowcount=1 才写事件；与上面的 UPDATE
            #   同一 sess / 同一事务。并发下后到的那个 n=0，根本不会走到这里。
            if n > 0 and evs:
                self._insert_events_tx(sess, mf, evs)
            sess.flush()
            sess.expire_all()   # ★ 回读必须拿库里的最新值，不能吃 identity map 的旧对象
            after = sess.get(mf.BillRow, h)
            row = self._to_dict(after) if after is not None else None
            if n > 0:
                return {"ok": True, "reason": "", "row": row,
                        "events": len(evs) if evs else 0}
            if row is None:
                return {"ok": False, "reason": "missing", "row": None}
            return {"ok": False, "reason": "conflict", "row": row}

        res = self._run(_op, default=None)
        if not isinstance(res, dict):
            return {"ok": False, "reason": "store_unavailable", "row": None}
        if res.get("ok"):
            _rv_invalidate()
        return res

    def drop(self, hash_string: str) -> bool:
        h = str(hash_string or "").strip().lower()
        if not h:
            return False

        def _op(sess: Any, mf: Any) -> bool:
            row = sess.get(mf.BillRow, h)
            if row is None:
                return False
            sess.delete(row)
            return True

        changed = bool(self._run(_op, default=False))
        if changed:
            _rv_invalidate()
        return changed

    def drop_void(self) -> int:
        """删所有 void 墓碑（人工清理口，tick 不调用；见 ``HrBillsStore.drop_void``）。"""

        def _op(sess: Any, mf: Any) -> int:
            return int(sess.query(mf.BillRow)
                       .filter(mf.BillRow.state == BILL_STATE_VOID)
                       .delete(synchronize_session=False))

        n = int(self._run(_op, default=0) or 0)
        if n:
            _rv_invalidate()
        return n

    def drop_many(self, hashes: Any) -> int:
        hs = sorted({str(x or "").strip().lower() for x in (hashes or [])
                     if str(x or "").strip()})
        if not hs:
            return 0

        def _op(sess: Any, mf: Any) -> int:
            return int(sess.query(mf.BillRow)
                       .filter(mf.BillRow.hash.in_(hs))
                       .delete(synchronize_session=False))

        n = int(self._run(_op, default=0) or 0)
        if n:
            _rv_invalidate()
        return n

    def drop_many_if(self, items: Any) -> Dict[str, Any]:
        """**条件批量删 · 存储层原子版**（★ 19.12.47 / 任务 91）。

        每行一条 ``DELETE … WHERE hash = ? AND state IS NOT DISTINCT FROM ? AND
        settlement_method IS NOT DISTINCT FROM ?``，用 ``rowcount`` 判是否真删。

        ★ 后端不可用/异常 → **全部按 skipped 返回**（fail-closed：宁可不删）。
        """
        rows: List[Tuple[str, Any]] = []
        for item in (items or []):
            try:
                hs = str(item[0] or "").strip().lower()
                exp = item[1] if len(item) > 1 else None
            except Exception:  # noqa: BLE001
                continue
            if hs:
                rows.append((hs, exp))
        out: Dict[str, Any] = {"dropped": [], "skipped": []}
        if not rows:
            return out
        _fail = {"dropped": [], "skipped": [h for h, _e in rows]}

        def _op(sess: Any, mf: Any) -> Dict[str, Any]:
            got: Dict[str, Any] = {"dropped": [], "skipped": []}
            for h, exp in rows:
                q = sess.query(mf.BillRow).filter(mf.BillRow.hash == h)
                for k, v in (exp or {}).items():
                    if k not in self._FIELDS:
                        continue
                    col = getattr(mf.BillRow, k)
                    q = q.filter(col.is_(None) if v is None else col == v)
                n = int(q.delete(synchronize_session=False) or 0)
                (got["dropped"] if n else got["skipped"]).append(h)
            return got

        res = self._run(_op, default=None)
        out = res if isinstance(res, dict) else _fail
        if out.get("dropped"):
            _rv_invalidate()
        return out

    def all(self) -> Dict[str, Dict[str, Any]]:
        def _op(sess: Any, mf: Any) -> Dict[str, Dict[str, Any]]:
            rows = sess.query(mf.BillRow).all()
            return {str(r.hash): self._to_dict(r) for r in rows}

        return self._run(_op, default={}) or {}

    def stats(self) -> Dict[str, Any]:
        return _bills_stats(self.all())


def get_hr_bills_store(data_dir: Path, kv: Any = None) -> HrBillsStore:
    """取/建**进程级** H&R 账单存储（按 data_dir 单例，跨热重载存活）。

    ★ 照 ``persistence.get_gate_store`` 一模一样：用同一套 ``_shared()`` 注册表
    单例持有实例，热重载后仍指向同一对象；**不挂 ``MagicFlowStore``**（其是进程级
    单例，热重载不重建 → 新字段/新方法拿不到）。
    ★ 19.0.0：db 句柄已绑定（生产）→ ``PgHrBillsStore``（mf_bills 表）；离线
    （单测/工具，无 app.*）→ 原 JSON 版。两代类不同 → isinstance 校验自动重建。
    """
    key = f"hrbills:{Path(data_dir)}"
    sh = _shared()
    with sh.lock:
        store = sh.singletons.get(key)
        # ★ 热重载后：模块里是**新类**，而单例还可能是**旧类的实例** → 方法过时/缺失
        #   （实测踩过：`stats()` 新增字段在 reload 后仍不出现）。校验类型，不匹配就重建
        #   （PG 模式数据本来就在库里；JSON 模式从冷备恢复）。
        if store is not None and not isinstance(store, HrBillsStore):
            try:
                store.flush()
            except Exception:  # noqa: BLE001
                pass
            store = None
        if store is None:
            mf = _mfdb_module()
            if mf is not None and mf.db_available():
                store = PgHrBillsStore(data_dir, kv=kv)
            else:
                store = HrBillsStore(data_dir, kv=kv)
            sh.singletons[key] = store
        elif kv is not None:
            try:
                store.kv_bind(kv)
            except Exception:  # noqa: BLE001
                pass
    return store


class HrBillsMixin:
    """下载即开账功能集（第一阶段：影子记账，不接保护）。"""

    # ---------------------------------------------------------- 工具
    @staticmethod
    def _hrbills_norm_domain(site_domain: Any) -> str:
        dom = str(site_domain or "").strip().lower()
        dom = re.sub(r"^https?://", "", dom).split("/")[0].strip()
        return dom

    def _hr_need_hours(self, dom: str) -> float:
        """★ 11.11.1 站点「实际做种达标小时」取值链（不再写死 24）：

        ① 站点规则库 ``seed_need_hours``（如学校 20h）—— ``_crossseed_seed_need_hours``
           （rule → 内置表 BUILTIN_RULES，取到 >0 即用）；
        ② 取不到 → 保守默认 ``HR_NEED_HOURS_DEFAULT``（24h，挂久点不要紧）。

        说明：站点对账 myhr 的 ``need_left`` 是「剩余做种时间」而非「总要求」，只在
        ``_hr_reconcile_site`` / ``_hr_bills_by_site`` 里作**逐条展示/人工核对**用，
        **不**反推改写账单 ``need_h``（避免账单口径与站点口径漂移）。
        """
        try:
            need = float(self._crossseed_seed_need_hours(dom) or 0.0)
        except Exception:  # noqa: BLE001
            need = 0.0
        if need <= 0:
            need = float(HR_NEED_HOURS_DEFAULT)
        return need

    # ---------------------------------------------------------- 11.13.0 安全垫 / 到期预警
    def _hr_margin_hours(self) -> float:
        """★ 11.13.0 **结清冗余安全垫**（小时，默认 ``HR_SEED_MARGIN_HOURS_DEFAULT``）。

        判定结清时用 ``need_h + margin`` 而不是 ``need_h``——挂久一点（免费种不花流量），
        避开「站点计时/我们计时」的偏差与最后一秒开销。设置面板可改；0 = 不留垫。
        """
        try:
            v = float(getattr(self, "_hr_seed_margin_hours", HR_SEED_MARGIN_HOURS_DEFAULT) or 0.0)
        except (TypeError, ValueError):
            v = float(HR_SEED_MARGIN_HOURS_DEFAULT)
        return max(0.0, v)

    def _hr_complete_ratio(self, dom: str = "") -> float:
        """★ 15.5.1 **完成度阈值**（“下载完成”判据）：“下载完成”= ``progress ≥ 该值``。

        取值链（Master 2026-10-07 16:56）：**站点覆盖 > 全局默认**。
        - 站点覆盖：站点规则库 ``complete_ratio``（例：某站说 20% → ``0.2``）；
        - 全局默认：设置项 ``hr_complete_ratio``（默认 ``HR_COMPLETE_RATIO_DEFAULT`` = 0.999 = 下满）。
        """
        _d = str(dom or "").strip().lower()
        if _d:
            try:
                _r = self._site_rules().get(_d).get("complete_ratio")
                if _r is not None and str(_r) != "":
                    return min(1.0, max(0.0, float(_r)))
            except Exception:  # noqa: BLE001
                pass
        try:
            v = float(getattr(self, "_hr_complete_ratio_v", HR_COMPLETE_RATIO_DEFAULT))
        except (TypeError, ValueError):
            v = float(HR_COMPLETE_RATIO_DEFAULT)
        return min(1.0, max(0.0, v))

    def _hr_warn_hours(self) -> float:
        """★ 11.13.0 临近到期预警阈值（小时，默认 48）。"""
        try:
            v = float(getattr(self, "_hr_deadline_warn_hours", HR_DEADLINE_WARN_HOURS_DEFAULT) or 0.0)
        except (TypeError, ValueError):
            v = float(HR_DEADLINE_WARN_HOURS_DEFAULT)
        return max(0.0, v)

    def _hr_window_hours(self, dom: str) -> float:
        """站点 H&R **考核窗口**（小时）：多久之内要做满 ``need_h``。取不到 → 0（= 无窗口信息）。

        链：``_crossseed_seed_window_hours``（规则库 ``seed_window_hours`` → ``seed_hours`` 保护期 → 内置表）。
        """
        try:
            return float(self._crossseed_seed_window_hours(dom) or 0.0)
        except Exception:  # noqa: BLE001
            return 0.0

    def _hr_deadline(self, bill: Any, now: Optional[float] = None) -> Dict[str, Any]:
        """★ 11.13.0 账单**到期信息**（只读推导，不落库、不造第二真值）。

        真值源 = 站点窗口（``_hr_window_hours``）+ 账单 ``opened_at`` + 当前做种进度。
        ``at_risk`` = 未达标 且 距窗口到期 ≤ ``_hr_warn_hours()``（含已逾期）—— 预警≠违约。
        """
        b = bill if isinstance(bill, dict) else {}
        _now = float(now if now is not None else time.time())
        dom = str(b.get("site") or "")
        margin = self._hr_margin_hours()
        try:
            need_h = float(b.get("need_h") or 0.0)
        except (TypeError, ValueError):
            need_h = 0.0
        try:
            seeded_h = float(b.get("seeded_h") or 0.0)
        except (TypeError, ValueError):
            seeded_h = 0.0
        due_h = round(need_h + margin, 3)
        window_h = self._hr_window_hours(dom)
        out: Dict[str, Any] = {"window_h": round(window_h, 3), "due_h": due_h,
                               "deadline_at": None, "hours_left": None, "at_risk": False}
        if window_h <= 0:
            return out
        try:
            opened = float(b.get("opened_at") or 0.0)
        except (TypeError, ValueError):
            opened = 0.0
        if opened <= 0:
            return out
        deadline_at = opened + window_h * 3600.0
        hours_left = (deadline_at - _now) / 3600.0
        state = str(b.get("state") or "")
        out["deadline_at"] = deadline_at
        out["hours_left"] = round(hours_left, 2)
        out["at_risk"] = bool(
            str(b.get("rule") or "") in (RULE_SITE_HR, RULE_HIT_AND_RUN)
            and state in (BILL_STATE_ACTIVE, BILL_STATE_PENDING)
            and (seeded_h + 1e-9) < due_h
            and hours_left <= self._hr_warn_hours()
        )
        return out

    def _hrbills_store(self) -> HrBillsStore:
        # ★ 19.12.43（P0）：PG 路径先过账本后端触发 ``ensure_schema``（建表 + _ensure_columns
        #   补列）——``create_all`` 只建表不加列，新列没补上时 put/patch 会静默丢字段
        #   （BillRow 没这列）。只在 db 句柄已绑定时触发（= 工厂会选 PgHrBillsStore 的
        #   同一条件）；离线/单测走 JSON 降级，无需 schema，也不引入额外导入。
        _mf = _mfdb_module()
        if _mf is not None and _mf.db_available():
            try:
                from ..ledger import get_backend  # noqa: WPS433
                get_backend(self)
            except Exception:  # noqa: BLE001
                pass
        try:
            data_dir = self.get_data_path()
        except Exception:  # noqa: BLE001
            data_dir = Path(".")
        try:
            kv = getattr(self, "_hot", None)
        except Exception:  # noqa: BLE001
            kv = None
        return get_hr_bills_store(Path(data_dir), kv=kv)

    # ---------------------------------------------------------- 并发守卫（CAS）
    @staticmethod
    def _hrbills_guard(bill: Any) -> Dict[str, Any]:
        """CAS 守卫：把「本轮判定所依据的结论字段」原值抄下来（★ 19.12.47 / 任务 91）。

        只取 ``(state, settlement_method)`` 两项，理由：

          · ``state`` 单独不够 —— 人工结清把 ``settled/auto`` 改成 ``settled/manual`` 时
            **state 没变**，只比 state 的 CAS 会放行，于是「站端翻案重开」会把
            ``settled_at`` / ``settled_by`` / ``settlement_reason`` 整块清空；
          · ``settlement_method`` 是「结清结论归属」的唯一判据（``_is_manual_settled``）；
          · 其它字段（``settled_at`` / ``rule`` / 存活列）不承载结论，且全仓没有单独改
            ``settled_by``/``settlement_reason`` 的写点（任务 91 阶段 A 全量 grep），
            再加键只增加假冲突面。

        ★ 原值照抄，**不归一**（``None`` 就是 ``None``）：PG 侧要落成 ``IS NULL``，
        归一成 ``""`` 会让历史上 state 为 NULL 的行永远冲突。
        """
        b = bill if isinstance(bill, dict) else {}
        return {"state": b.get("state"), "settlement_method": b.get("settlement_method")}

    def _hrbills_cas(self, store: Any, hash_string: str, guard: Any,
                     save: bool = False, **fields: Any) -> Dict[str, Any]:
        """条件写一层皮：统一三态、异常兜成失败。**绝不把失败当成功**。

        返回 store 的原始结果 dict（``ok`` / ``reason`` / ``row``）；store 不支持 CAS
        （旧版实例）→ ``store_unsupported``，调用方按失败处理（fail-closed）。
        """
        fn = getattr(store, "patch_if", None)
        if not callable(fn):
            return {"ok": False, "reason": "store_unsupported", "row": None}
        try:
            res = fn(hash_string, guard, save=save, **fields)
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "reason": "error:%s" % err, "row": None}
        return res if isinstance(res, dict) else {"ok": False, "reason": "bad_result", "row": None}

    # ---------------------------------------------------------- ★ 任务 98：审计事件构造
    @staticmethod
    def _hr_bill_snapshot(bill: Any) -> Dict[str, Any]:
        """事件发生**之前**的结清四列 + 规则/工时快照（不可变副本）。

        行上四列是「当前结论」，会被后续结清/重开覆盖；真值留在这份快照里，
        所以 `bill_snapshot` 一旦写入事件表就再也不改。
        """
        b = bill if isinstance(bill, dict) else {}
        return {
            "state": b.get("state"), "rule": b.get("rule"),
            "need_h": b.get("need_h"), "seeded_h": b.get("seeded_h"),
            "settled_at": b.get("settled_at"),
            "settlement_method": b.get("settlement_method"),
            "settled_by": b.get("settled_by"),
            "settlement_reason": b.get("settlement_reason"),
        }

    def _hr_bill_event(self, hash_string: str, event_type: str, bill: Any,
                       at: Any = None, actor: str = "", reason: str = "",
                       prev_state: str = "", new_state: str = "",
                       evidence_source: str = "", evidence_at: Any = 0.0,
                       evidence_digest: Any = None,
                       dedup_key: str = "") -> Dict[str, Any]:
        """构造一条 append-only 事件行（字段与 ``db.BillEventRow`` 逐一同名）。

        ``dedup_key`` 是业务幂等键：调用方对「站端纠错重开」显式传
        ``hash|reopened|<原结清时刻>|<证据时刻>``，连续 tick 采到同一份证据只记一次；
        未显式给的普通事件用 ``hash|type|at``（同一次动作只可能有同一个 at）。
        """
        h = str(hash_string or "").strip().lower()
        try:
            _at = float(at or 0.0) or time.time()
        except (TypeError, ValueError):
            _at = time.time()
        try:
            _ev_at = float(evidence_at or 0.0) or None
        except (TypeError, ValueError):
            _ev_at = None
        _dk = str(dedup_key or "").strip() or ("%s|%s|%.6f" % (h, event_type, _at))
        return {
            "hash": h[:64], "event_type": str(event_type)[:32], "at": _at,
            "actor": str(actor or EVT_SYSTEM_ACTOR)[:64],
            "reason": str(reason or "")[:300],
            "prev_state": str(prev_state or "")[:24],
            "new_state": str(new_state or "")[:24],
            "bill_snapshot": self._hr_bill_snapshot(bill),
            "evidence_source": str(evidence_source or "")[:120],
            "evidence_at": _ev_at,
            "evidence_digest": dict(evidence_digest) if isinstance(evidence_digest, dict) else {},
            "dedup_key": _dk[:160],
        }

    def _hr_bill_events_store(self):
        """事件读写都走账单 store（同一实例 = 同一把锁 / 同一个 PG 会话入口）。"""
        return self._hrbills_store()

    def _hr_bill_history(self, hash_string: str = "", limit: int = 0) -> List[Dict[str, Any]]:
        """读事件历史；store 不支持（旧版实例/离线夹具）→ 空列表，展示层按兼容历史处理。"""
        try:
            fn = getattr(self._hr_bill_events_store(), "events_for", None)
            if callable(fn):
                return list(fn(hash_string, limit) or [])
        except Exception:  # noqa: BLE001
            pass
        return []

    def _hrbills_title(self, hash_string: str) -> str:
        try:
            t = (self._tag_all_torrents() or {}).get(str(hash_string).strip().lower())
            return str(getattr(t, "title", "") or "") if t is not None else ""
        except Exception:  # noqa: BLE001
            return ""

    # ---------------------------------------------------------- 加种 journal
    def _journal_seed_add(self, hash_string: str, site_domain: str, tag: str) -> None:
        """加种落 journal（kind=add，供事后取证；不作运行时真值）。

        DESIGN-RESOURCE-SEED §3：加种时记录 hash/site/tag；fp/reused/completed_at 等
        事实由「完成」路径写 mf_seed（不在此处）。
        """
        try:
            _store = getattr(self, "_store", None)
            _journal = getattr(_store, "journal", None) if _store is not None else None
            if _journal is None:
                return
            from ..persistence import OperationItem  # noqa: WPS433
            _journal.record(
                task_id="",
                kind="add",
                items=[OperationItem(
                    hash=str(hash_string or "").strip().lower(),
                    title="",
                    source="add",
                    tags=str(tag or ""),
                    reason=str(site_domain or ""),
                )],
            )
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------- 义务判定（两道门槛）
    def _hr_obligation_rule(self, domain: str,
                            torrent_hr: Any = None) -> Optional[str]:
        """★ 19.12.33：H&R 义务的**唯一**判定入口（开账 / 回填共用）。

        两道门槛，任一不过就**不记账**（``None``）：

        **门槛 1 · 查来源站点** —— ``_site_hr_flag(domain)``
            ``False``（该站明确没有 H&R 制度）→ 不记。
            ``None``（规则库还没探到）→ 非逐种站也不记（宁可漏记，不凭空欠债）。

        **门槛 2 · 逐种判定**
            逐种站（``_site_per_torrent_hr``）：站点级结论**对单颗种不适用**，
                只看这颗种的 H&R 标记 —— 有 → ``hit_and_run``；没有 → 不记。
            非逐种站：站点级 ``True`` → ``site_hr``（全量义务）。

        为什么删掉旧的 ``unknown`` 分支：unknown 账在 tick 里**永不开、永不结清**
        （``_known_rule`` 闸），本质是僵尸 pending。2026-11-05 线上 YemaPT
        （逐种站、站点级规则未识别）因此挂了 22 张僵尸账，卡片说「还欠 22」、
        执行层 owed=0，两处打架。规则不明就**不记**，比记一笔说不清的账诚实。

        逐种标记（``torrent_hr is True``）优先级最高：它是下载瞬间的事实，
        比站点级推断硬，且不受「逐种站 / 非逐种站」影响。
        """
        if torrent_hr is True:
            return RULE_HIT_AND_RUN
        dom = str(domain or "").strip().lower()
        try:
            site_hr = self._site_hr_flag(dom) if dom else None
        except Exception:  # noqa: BLE001
            site_hr = None
        try:
            per_torrent = bool(self._site_per_torrent_hr(dom)) if dom else False
        except Exception:  # noqa: BLE001
            per_torrent = False
        if per_torrent:
            return None          # 门槛 2：逐种站、这颗没标 H&R → 没有义务
        if site_hr is True:
            return RULE_SITE_HR  # 门槛 1/2 均通过：非逐种站 + 站点明确有 H&R
        return None              # 站点明确没有 / 规则未知 → 不记

    # ---------------------------------------------------------- 开账
    def _hrbills_open(self, hash_string: str, site_domain: str, tag: str,
                      content: Any, hit_and_run: bool = False,
                      crossseed: bool = False) -> Optional[Dict[str, Any]]:
        """下载成功后开一张 H&R 账单（影子记账）。

        跳过：复用/补源副本（``_SKIP_BILL_TAGS``）；同 hash 已存在不重复开。
        ★ 19.10.11：跨站来源份（``CROSSSEED_TAG``）**不再跳过** —— 它欠的是来源站 H&R，
        与刷流/音乐同性质，统走本账单。走 ``crossseed=True`` 的**专用口径**（见
        ``_hrbills_open_crossseed``）：义务判定与工时都取跨站/站点规则的既有真值源。
        规则判定：``_site_hr_flag(dom) is True`` → ``site_hr``；种子 ``hit_and_run`` →
        ``hit_and_run``；两者皆无 → ``unknown``（pending，不保护不罚）。

        11.7.0：``hit_and_run`` 由**下载调用点**从候选带入（qB 侧无此信息）；为兼容旧调用，
        未传时回退读 qB 快照的 ``TorrentInfo.hit_and_run``（历史上恒 False）。
        回滚开关 ``HR_PER_TORRENT=False`` → 忽略逐种标记，退回只认站点规则。
        """
        hs = str(hash_string or "").strip().lower()
        if not hs:
            return None
        # ★ 11.11.1：复用/补源副本不是本账单口径的真实下载 → 不开账。
        #   19.10.11 起跨站来源份**已从名单移除**（真实下载，欠来源站 H&R）。
        if _skip_hr_bill([str(tag or "")]):
            return None
        store = self._hrbills_store()
        _existing = store.get(hs)
        if _existing:
            return _existing  # 已存在 → 不重复开（幂等）
        dom = self._hrbills_norm_domain(site_domain)
        # ★ 19.10.11：来源份走专用口径（义务判定 + 工时都取跨站既有真值源）。
        if crossseed:
            return self._hrbills_open_crossseed(hs, dom, hit_and_run=hit_and_run)
        # 逐种标记：优先取「钩子传入」（下载瞬间最准），没传（旧路径）才回退 qB 快照。
        thr = None
        if HR_PER_TORRENT:
            thr = True if bool(hit_and_run) else None
        if thr is None:
            try:
                t = (self._tag_all_torrents() or {}).get(hs)
                thr = bool(getattr(t, "hit_and_run", False)) if t is not None else None
            except Exception:  # noqa: BLE001
                thr = None
        # ★ 19.12.33：义务判定收敛到两道门槛（站点有没有 H&R → 逐种站看种子标记），
        #   不过门就**不记账**。旧的 `unknown` 影子账已取消（僵尸 pending，见 _hr_obligation_rule）。
        rule = self._hr_obligation_rule(dom, thr)
        if not rule:
            return None
        # ★ 15.5.1（Master 2026-10-07 16:33「1 的话我删了，你账不是还欠着」）：
        #   刚加入下载 → 必然未完成。**H&R 义务自「下载完成」起算**，故开账只挂
        #   观测（pending：不算欠、不拦删、不进 owed）；完成那一刻由 ``_hrbills_tick``
        #   ① 转 active 开始计 need_h。与 ``common.hr_incomplete`` 同一口径。
        state = BILL_STATE_PENDING
        need_h = self._hr_need_hours(dom)
        fp = ""
        try:
            _fp = fingerprint(content)
            if _fp:
                fp = str(_fp)
        except Exception:  # noqa: BLE001
            fp = ""
        now = time.time()
        bill = {
            "site": dom,
            "rule": rule,
            "state": state,
            "need_h": float(need_h),
            "seeded_h": 0.0,
            "fp": fp,
            "title": self._hrbills_title(hs),
            "opened_at": now,
            "last_progress": 0.0,
            "last_progress_at": now,
            "progress": 0.0,
            "opened_by": "open",
        }
        return store.put(hs, bill)

    def _hrbills_open_crossseed(self, hs: str, dom: str,
                                hit_and_run: bool = False) -> Optional[Dict[str, Any]]:
        """★ 19.10.11：给**跨站来源份**开一张 H&R 账单（义务口径专用）。

        为什么不用通用判定：通用判定对「规则未知的站」不开账（``unknown``，Master 红线
        「未知站不凭空欠债」）。但跨站来源份的口径一直是**保守兜底**
        （``_crossseed_hr_decision``：种子标记 > 站点规则 > 未知保守）—— 跨站取种的
        来源站多半还没在规则库里填过 H&R。若套用通用口径，来源份**永远开不出账**，
        也就永远不受保护。

        为什么直接开 **active**（不是 pending）：账单口径的 pending = 「刚加入下载，必然
        未完成」。但来源份是在**下完那一刻**才移交的（``_crossseed_tick``：
        ``progress >= 0.999`` 才调 ``_crossseed_protect_source``），pending 在这里不成立。
        直接 active → 立刻受删除闸门第 4 档（账单）保护，不留「已下完却还 pending」的窗口期。

        工时取 ``_hr_need_hours_or_default``（**唯一**义务工时兜底点）：
        站点规则明确写了真实 0 → 0（不要求做种时长 → 无需挂 → 不开账）；
        规则缺失 → 24（保守）。
        """
        store = self._hrbills_store()
        _existing = store.get(hs)
        if _existing:
            return _existing  # 幂等
        thr = True if bool(hit_and_run) else False
        try:
            protect, _hours, hsrc = self._crossseed_hr_decision(dom, thr)
        except Exception as err:  # noqa: BLE001
            self._log(f"跨站账单:义务判定失败 {hs[:12]}:{err}", "warning")
            return None
        if not protect:
            return None       # 该站/该种确实没有 H&R 义务 → 不开账
        try:
            need_h = float(self._hr_need_hours_or_default(dom) or 0.0)
        except Exception:  # noqa: BLE001
            need_h = 0.0
        if need_h <= 0:
            # 站点明确「不要求做种时长」→ 没有挂种约束 → 无需保护，不开账。
            self._log(
                f"跨站账单:{dom} 规则明确不要求做种时长 → 来源份 {hs[:12]} 不开账",
                "info",
            )
            return None
        rule = RULE_HIT_AND_RUN if thr is True else RULE_SITE_HR
        now = time.time()
        bill = {
            "site": dom,
            "rule": rule,
            "state": BILL_STATE_ACTIVE,
            "need_h": float(need_h),
            "seeded_h": 0.0,
            "fp": "",
            "title": self._hrbills_title(hs),
            "opened_at": now,
            "last_progress": 1.0,
            "last_progress_at": now,
            "progress": 1.0,
            "opened_by": "crossseed",
            "src": str(hsrc or ""),
        }
        return store.put(hs, bill)

    # ======================================== 19.12.4 站端欠账证据（只读缓存，不联网）
    @staticmethod
    def _hr_need_left_sec(text: Any) -> Optional[float]:
        """站端「还需做种时间」单元格 → 秒。**解析不了返回 ``None``（不是 0）**。

        两种渲染（``collect_parse.parse_myhr_rows`` 已统一收）：
        剩余 ≥1h 是 ``H:MM:SS`` / ``HH:MM:SS``；<1h 是 ``MM:SS``。
        返回 ``None`` 与 ``0.0`` 的差别是本模块的安全边界 —— ``0`` 才敢说「站端说清了」。
        """
        s = str(text or "").strip()
        if not s:
            return None
        m = re.search(r"(\d+):([0-5]\d)(?::([0-5]\d))?", s)
        if not m:
            return None
        try:
            if m.group(3) is None:
                return float(int(m.group(1)) * 60 + int(m.group(2)))
            return float(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)))
        except (TypeError, ValueError):
            return None

    def _hr_live_sid_map(self) -> Dict[str, int]:
        """域名 → MP 站点 id（读实时快照用，5 分钟内复用）。取不到就空表。"""
        try:
            _box = getattr(self, "_hr_sid_map_box", None)
            if isinstance(_box, tuple) and (time.time() - float(_box[0] or 0)) < 300.0:
                return dict(_box[1] or {})
        except Exception:  # noqa: BLE001
            pass
        out: Dict[str, int] = {}
        try:
            for row in (self._list_sites() or []):
                try:
                    d = self._hrbills_norm_domain((row or {}).get("domain") or "")
                    if d:
                        out[d] = int((row or {}).get("id") or 0)
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            out = {}
        try:
            self._hr_sid_map_box = (time.time(), out)
        except Exception:  # noqa: BLE001
            pass
        return dict(out)

    def _hr_bar_cert(self, dom: str, site_id: Optional[int] = None, rep: Any = None,
                     now: Optional[float] = None) -> Dict[str, Any]:
        """★ 19.12.41：页头 H&R 计数**凭证**（只读，绝不联网、绝不触发抓取）。

        为什么需要它：``myhr.php`` 列表分页无法自证「抓全了」（实测四站分页控件是纯文本、
        没有「下一页」href、也没有「共 N 条」）。而站点 ``index.php`` 用户栏里的
        ``H&R: [考核中/未完成/上限]`` 是**同一份债的聚合计数**，不受列表分页/改版影响 ——
        用它反证列表完整性：计数为 0 且明细为 0，才算「站端自己说没有记录」。

        口径（★ 每条都是为了「别把未知读成 0」）：
          · **只认两数形态**（``assessing`` 与 ``unfinished`` 都是整数）。``H&R: 0`` 这种
            单数字形态**一律不认**（uhddolby 实测；采集侧把它保守归进 ``unfinished``，
            那是对的报警口径，但在结清场景恰好是危险方向）；
          · 必须来自**成功**的首页响应（``ok is not False``）且**已登录**
            （``logged_in is not False``）；
          · 必须有 ``ts`` 且年龄在 ``HR_SITE_EVIDENCE_MAX_HOURS`` 内 —— ``LiveStats.cached()``
            不判过期（TierCache 存 2h、内存层干脆不过期），所以**闸门自己算 age**；
          · 取不到实时快照时退回对账报告里的 ``bar`` 快照（同一条口径、同一个 age 判据）。

        Returns: ``{known, total, assessing, unfinished, limit, raw, form, ts, age, stale, src}``。
        """
        out: Dict[str, Any] = {
            "known": False, "total": None, "assessing": None, "unfinished": None,
            "limit": None, "raw": "", "ts": 0.0, "age": None, "stale": True, "src": "",
        }
        _now = float(now or 0) or time.time()
        bar: Dict[str, Any] = {}
        sid = int(site_id or 0)
        if not sid:
            try:
                sid = int(self._hr_live_sid_map().get(self._hrbills_norm_domain(dom)) or 0)
            except Exception:  # noqa: BLE001
                sid = 0
        live = getattr(self, "_live", None)
        if sid and live is not None:
            try:
                _hit = live.cached(sid) or {}
            except Exception:  # noqa: BLE001
                _hit = {}
            if isinstance(_hit, dict) and isinstance(_hit.get("hr"), dict):
                bar = _hit
                out["src"] = "live"
        if out["src"] != "live" and isinstance(rep, dict):
            _snap = rep.get("bar")
            if isinstance(_snap, dict) and isinstance(_snap.get("hr"), dict):
                bar = _snap
                out["src"] = "report"
        if not out["src"]:
            return out
        if bar.get("ok") is False or bar.get("logged_in") is False:
            return out
        hr = bar.get("hr") or {}
        if not isinstance(hr, dict):
            return out
        out["raw"] = str(hr.get("raw") or "")[:40]
        out["form"] = str(hr.get("form") or "")[:8]
        out["limit"] = hr.get("limit") if isinstance(hr.get("limit"), int) else None
        _a, _u = hr.get("assessing"), hr.get("unfinished")
        _is_int = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
        _form = out["form"]
        # ★ 19.12.42：采集侧已显式标了形态（pair/single/raw）。非 pair 一律不可当证据 ——
        #   即使旧字段凑巧把单个数塞进了 unfinished。老快照没 form 时退回「两数齐全」判据。
        if _form and _form != "pair":
            out["assessing"] = _a if _is_int(_a) else None
            out["unfinished"] = _u if _is_int(_u) else None
            return out
        if not (_is_int(_a) and _is_int(_u)):
            # 单数字形态 / 只有 raw / 字段缺失 → 不可用作放行证据
            out["assessing"] = _a if _is_int(_a) else None
            out["unfinished"] = _u if _is_int(_u) else None
            return out
        out["assessing"] = int(_a)
        out["unfinished"] = int(_u)
        out["known"] = True
        out["total"] = int(_a) + int(_u)
        try:
            out["ts"] = float(bar.get("ts") or 0.0)
        except (TypeError, ValueError):
            out["ts"] = 0.0
        if out["ts"] > 0:
            age = _now - float(out["ts"])
            out["age"] = age
            _max_age = max(0.0, float(HR_SITE_EVIDENCE_MAX_HOURS)) * 3600.0
            out["stale"] = bool(age > _max_age or age < -3600.0)
        return out

    # ---------------------------------------------------------- 站端索引（两处共用）
    def _hr_index_new(self, now: float) -> Dict[str, Any]:
        """站端欠账索引骨架。

        ★ 19.12.42：``_hr_site_debt_index``（结清闸门）和 ``_hrbills_breach_reconcile``
        （违约清账）**共用同一套折叠逻辑**。此前违约清账自己写了一遍「不在欠列表里 →
        站点不欠」，那条路绕开了页头计数双源闸门 —— 一次登录页/改版就能把 breached
        账单批量作废。两条路必须同一口径，所以把折叠抽出来。
        """
        return {"at": float(now), "sites": {}, "need": {}, "seen": set(),
                "done": set(), "bars": {}}

    def _hr_index_add_report(self, out: Dict[str, Any], dom: Any, rep: Any,
                             now: float, sts: Any = None) -> bool:
        """把**一份**站点对账报告折进索引（就地累积）。返回是否被采纳。

        采纳即要求 ``rep.ok``（失败报告不覆盖旧视图，见 ``_hr_site_debt_index`` 的说明）。
        """
        if not isinstance(rep, dict) or not rep.get("ok"):
            return False
        d = ""
        try:
            d = self._hrbills_norm_domain(dom)
        except Exception:  # noqa: BLE001
            d = ""
        if not d:
            return False
        _max_age = max(0.0, float(HR_SITE_EVIDENCE_MAX_HOURS)) * 3600.0
        _at = 0.0
        for _cand in (rep.get("at"), ((sts or {}).get(d) or {}).get("last_ok_ts")):
            try:
                _v = float(_cand or 0.0)
            except (TypeError, ValueError):
                _v = 0.0
            if _v > 0:
                _at = _v
                break
        # ★ 19.12.41：「可判清」= 页面有效 ∧ 列表可判完整 ∧ 每条记录都能落到 hash。
        #   旧口径只看 ``hash_coverage_complete``（它只校验「已抓到的记录能解出 hash」，
        #   对「0 条记录」恒为 True）→ 一次登录页/改版就能清空所有欠账。
        _page_ok = rep.get("page_ok")
        _list_ok = rep.get("list_complete")
        out["sites"][d] = {
            "at": _at,
            "page_ok": bool(_page_ok) if isinstance(_page_ok, bool) else False,
            "list_complete": bool(_list_ok) if isinstance(_list_ok, bool) else False,
            "coverage": bool(rep.get("hash_coverage_complete")),
            "complete": bool(_page_ok is True and _list_ok is True
                             and rep.get("hash_coverage_complete")),
        }
        # 页头计数凭证（供 clear 闸门做双源交叉；只读，取不到就是 unknown）
        try:
            out["bars"][d] = self._hr_bar_cert(d, rep=rep, now=now)
        except Exception:  # noqa: BLE001
            out["bars"][d] = {"known": False, "total": None, "stale": True, "src": ""}
        _age = (now - _at) if _at > 0 else 0.0
        _stale = bool(_at > 0 and _age > _max_age)
        for rec in (rep.get("records") or []):
            if not isinstance(rec, dict):
                continue
            hh = str(rec.get("infohash") or "").strip().lower()
            if not hh:
                continue
            sec = self._hr_need_left_sec(rec.get("need_left"))
            if sec is None or _stale:
                # 判不了「还欠多久」：既不敢说欠、也不敢说清
                out["seen"].add(hh)
                continue
            left = sec - max(0.0, _age) if _at > 0 else sec
            if left <= 0:
                # ★ 站端**自己列了这颗、且剩余为 0**（或按证据时刻外推已到期）→
                #   这是关于这颗种的**正向证据**（不是「没看见」），可以直接判清。
                #   证据过旧（_stale）时不算 —— 那时的 0 可能是我们自己外推出来的。
                out["done"].add(hh)
                continue
            _cur = out["need"].get(hh)
            if _cur is None or left > float(_cur.get("left") or 0.0):
                out["need"][hh] = {"left": float(left), "at": _at, "dom": d}
        return True

    def _hr_index_finish(self, out: Dict[str, Any]) -> Dict[str, Any]:
        """收尾：只把「没有任何一站明确说欠」的进 ``seen``。"""
        out["seen"] = {h for h in (out.get("seen") or set())
                       if h not in (out.get("need") or {})}
        return out

    def _hr_site_debt_index(self, now: Optional[float] = None) -> Dict[str, Any]:
        """站端欠账索引（**只读 ``hr_reconcile.json`` 缓存，绝不联网**）。

        返回 ``{"at", "sites", "need", "seen"}``：
          - ``sites[dom] = {"at", "complete"}``：该站上一轮报告的时刻 / hash 覆盖是否完整；
          - ``need[hash] = {"left", "at", "dom"}``：站端明确「还需做种 ``left`` 秒」
            （**已按证据时刻外推到本轮**）；
          - ``seen``：出现在站端清单里、却判不了「还欠多久」的 hash（解析失败 / 证据过旧）
            → 调用方只能判 unknown，**不得**当「站端说清了」。

        为什么以 hash 为键：一笔债只挂一颗种。跨站同内容各欠一份时取**最欠**的那份
        （``max``）—— 宁可多挂，不可提前撒手。
        为什么失败报告直接跳过：``_hr_reconcile_site`` 抓失败时提前 return、**不覆盖**旧
        报告，所以缓存里留下的总是最后一次成功的视图；``ok=False`` 的行只可能是历史残留。
        """
        _now = float(now or 0) or time.time()
        try:
            _box = getattr(self, "_hr_site_debt_box", None)
            if isinstance(_box, tuple) and (_now - float(_box[0] or 0)) < float(HR_SITE_DEBT_TTL):
                return _box[1]
        except Exception:  # noqa: BLE001
            pass
        out = self._hr_index_new(_now)
        try:
            cache = self._hr_reconcile_cache()
            reps = dict(cache.reports() or {})
            sts = dict(cache.site_status() or {})
        except Exception:  # noqa: BLE001
            reps, sts = {}, {}
        for dom, rep in (reps or {}).items():
            self._hr_index_add_report(out, dom, rep, _now, sts=sts)
        self._hr_index_finish(out)
        try:
            self._hr_site_debt_box = (_now, out)
        except Exception:  # noqa: BLE001
            pass
        return out

    def _hr_idx_site(self, idx: Any, dom: str) -> Tuple[str, Any]:
        """索引里按「互为后缀」找该站条目 → ``(key, entry)``；没有则 ``(dom, None)``。"""
        d = str(dom or "").strip().lower()
        _sites = (idx or {}).get("sites") or {}
        st = _sites.get(d)
        if isinstance(st, dict):
            return d, st
        for k, v in (_sites or {}).items():
            k = str(k or "")
            if isinstance(v, dict) and k and (
                    k == d or k.endswith("." + d) or d.endswith("." + k)):
                return k, v
        return d, None

    def _hr_gate_state(self, dom: str, idx: Any = None,
                       now: Optional[float] = None) -> Dict[str, Any]:
        """该站**闸门口径快照**（只读、绝不联网）：给审计回答「为什么判 unknown」。

        只描述证据本身，不下结论 —— 结论在 ``_hr_site_verdict`` 里，避免两套判据。
        """
        _now = float(now or 0) or time.time()
        _idx = idx if isinstance(idx, dict) else self._hr_site_debt_index(_now)
        try:
            d = self._hrbills_norm_domain(dom)
        except Exception:  # noqa: BLE001
            d = str(dom or "").strip().lower()
        key, st = self._hr_idx_site(_idx, d)
        cert = ((_idx.get("bars") or {}).get(key) or {})
        if not isinstance(cert, dict):
            cert = {}
        out: Dict[str, Any] = {
            "site_key": key,
            "has_report": isinstance(st, dict),
            "page_ok": bool((st or {}).get("page_ok")),
            "list_complete": bool((st or {}).get("list_complete")),
            "coverage": bool((st or {}).get("coverage")),
            "complete": bool((st or {}).get("complete")),
            "bar_known": bool(cert.get("known")),
            "bar_total": cert.get("total"),
            "bar_form": str(cert.get("form") or ""),
            "bar_raw": str(cert.get("raw") or "")[:40],
            "bar_stale": bool(cert.get("stale")) if cert else True,
            "bar_age_h": (round(float(cert.get("age")) / 3600.0, 2)
                          if isinstance(cert.get("age"), (int, float)) else None),
            "why": "",
        }
        if not isinstance(st, dict):
            out["why"] = "no_report"
        elif not out["page_ok"]:
            out["why"] = "page_not_evidence"
        elif not out["complete"]:
            out["why"] = "list_not_complete"
        elif not out["bar_known"]:
            out["why"] = "bar_unknown"
        elif out["bar_total"] != 0:
            out["why"] = "bar_total=%s" % out["bar_total"]
        elif out["bar_stale"]:
            out["why"] = "bar_stale"
        else:
            out["why"] = "ok"
        return out

    def _hr_site_verdict(self, hash_string: str, dom: str, now: Optional[float] = None,
                         idx: Any = None) -> Tuple[str, float]:
        """站端对该种的裁决：``("owed", 剩余秒)`` / ``("clear", 0)`` / ``("unknown", 0)``。

        - ``owed``：站端 myhr 明确说这颗还需做种 N 秒（N 已按证据时刻外推）；
        - ``clear``：站端报告 **ok ∧ 页面有效 ∧ 列表可判完整 ∧ hash 覆盖完整**，
          且**页头 H&R 聚合计数（两数形态）新鲜且为 0**，这颗又不在欠列表里 → 敢结清；
          ★ 19.12.41 起单靠列表不够（列表没分页证据 → 「没看见」不等于「不存在」）；
        - ``unknown``：没报告 / 覆盖不完整 / 页头计数缺失·单数字·过期·非 0 / 判不了
          → **调用方必须保留账单**（★ 19.12.40 起；旧口径是「退回本地工时口径」并允许结清
          —— 那是赌）。想回退旧行为：``HR_SETTLE_SITE_GATE=False``（明确关掉站端闸门）。
        """
        if not HR_SETTLE_SITE_GATE:
            return ("unknown", 0.0)
        _now = float(now or 0) or time.time()
        hh = str(hash_string or "").strip().lower()
        try:
            d = self._hrbills_norm_domain(dom)
        except Exception:  # noqa: BLE001
            d = str(dom or "").strip().lower()
        if not hh or not d:
            return ("unknown", 0.0)
        _idx = idx if isinstance(idx, dict) else self._hr_site_debt_index(_now)
        # ★ 19.12.4 域名两种写法都要认：对账报告的 key 是 MP 站点域名（实测 `pt.btschool.club`），
        #   而账单 `site` 存的是裸域（`btschool.club`）→ 精确比对会让闸门静默失效。
        #   与 ``_hr_reconcile_site`` 里「本机该站的种」同一套后缀匹配口径（见 ``_hr_idx_site``）。
        _key, _st = self._hr_idx_site(_idx, d)
        if not isinstance(_st, dict):
            return ("unknown", 0.0)
        _hit = (_idx.get("need") or {}).get(hh)
        if isinstance(_hit, dict):
            _built = float(_idx.get("at") or 0.0)
            _left = float(_hit.get("left") or 0.0)
            if _built > 0:
                _left -= max(0.0, _now - _built)   # 索引有 TTL，再衰减一次
            if _left > 0:
                return ("owed", float(_left))
            return ("clear", 0.0)
        if hh in (_idx.get("done") or set()):
            # 站端清单里**有这颗**且剩余为 0 → 正向证据，与「列表抓没抓全」无关
            return ("clear", 0.0)
        if hh in (_idx.get("seen") or set()):
            return ("unknown", 0.0)
        if not bool(_st.get("complete")):
            return ("unknown", 0.0)
        # ★ 19.12.41 双源闸门：列表「没看见这颗」只是**观察**，不是站端断言。
        #   必须再拿页头 H&R 聚合计数佐证**这份列表本身是完整的**：
        #   计数可解（两数形态）∧ 未过期 ∧ x+y == 0。任一不满足 → unknown（保留账单）。
        _cert = (_idx.get("bars") or {}).get(_key)
        if not isinstance(_cert, dict) or not _cert.get("known"):
            return ("unknown", 0.0)
        try:
            if int(_cert.get("total") if _cert.get("total") is not None else -1) != 0:
                return ("unknown", 0.0)
        except (TypeError, ValueError):
            return ("unknown", 0.0)
        # 闸门**自己**再算一次年龄：索引有 60s TTL，不能拿它建索引那一刻的结论当现值。
        try:
            _ts = float(_cert.get("ts") or 0.0)
        except (TypeError, ValueError):
            _ts = 0.0
        if _ts <= 0:
            return ("unknown", 0.0)
        _age = _now - _ts
        if _age > max(0.0, float(HR_SITE_EVIDENCE_MAX_HOURS)) * 3600.0 or _age < -3600.0:
            return ("unknown", 0.0)
        return ("clear", 0.0)

    # -------------------------------------------------- ★ 任务 98：受控纠错证据门槛
    def _hr_reopen_evidence(self, hash_string: str, bill: Any, now: float,
                            idx: Any, verdict: str, left: float) -> Dict[str, Any]:
        """「站端可靠证据证明人工结清结论错了」的**八项门槛**（只读、绝不联网）。

        重开 = 推翻一次人工核实结论，是比「阻止自动结清」更强的动作。日常
        ``_hr_site_verdict`` 的 ``owed`` 分支只看 ``need[hash]``、**不校验列表完整性**
        （一次抓到登录页/改版页却恰好解析出这颗也会判 owed），所以纠错必须另立
        一套更严的判据，任一不满足都 fail-closed：保持 settled、零写入、零事件。

          ① 功能开关 ``HR_RECONCILE_REOPEN`` 与 ``HR_SETTLE_SITE_GATE`` 均开启；
          ② 规则明确（``site_hr`` / ``hit_and_run``；``rule=unknown`` 拒绝）；
          ③ 账单站点归属非空，且该站存在成功报告且 ``page_ok``；
          ④ 列表完整 ``list_complete`` ∧ hash 覆盖完整 ``coverage``；
          ⑤ 页头计数可解且新鲜 ``bar_known`` ∧ 非 ``bar_stale``；
          ⑥ hash 精确命中 ``need`` 列表，且该条记录的站点归属 == 该站报告 key；
          ⑦ 证据时间有效（``0 <= age <= 48h``，负钟差 >1h 也拒绝）；
          ⑧ 最终裁决 == ``owed`` 且剩余 > 0。

        Returns ``{"ok", "why", "source", "at", "digest", "left", "site_key"}``。
        """
        out: Dict[str, Any] = {"ok": False, "why": "", "source": "", "at": 0.0,
                               "digest": {}, "left": float(left or 0.0), "site_key": ""}
        b = bill if isinstance(bill, dict) else {}
        h = str(hash_string or "").strip().lower()

        def _no(why: str) -> Dict[str, Any]:
            out["why"] = why
            return out

        # ① 开关
        if not HR_RECONCILE_REOPEN or not HR_SETTLE_SITE_GATE:
            return _no("reopen_disabled")
        if not isinstance(idx, dict):
            return _no("no_index")
        # ② 规则明确
        rule = str(b.get("rule") or "")
        if rule not in (RULE_SITE_HR, RULE_HIT_AND_RUN):
            return _no("rule_unknown")
        # ③ 站点归属 + 报告存在
        try:
            dom = self._hrbills_norm_domain(b.get("site"))
        except Exception:  # noqa: BLE001
            dom = str(b.get("site") or "").strip().lower()
        if not dom or not h:
            return _no("site_or_hash_missing")
        key, st = self._hr_idx_site(idx, dom)
        out["site_key"] = str(key or "")
        if not isinstance(st, dict):
            return _no("no_report")
        try:
            gate = self._hr_gate_state(dom, idx, now)
        except Exception:  # noqa: BLE001
            return _no("gate_unavailable")
        # ③/④/⑤ 页面 / 列表 / 页头
        if not gate.get("page_ok"):
            return _no("page_ok_false")
        if not gate.get("list_complete"):
            return _no("list_incomplete")
        if not gate.get("coverage"):
            return _no("coverage_incomplete")
        if not gate.get("bar_known"):
            return _no("bar_unknown")
        if gate.get("bar_stale"):
            return _no("bar_stale")
        # ⑥ hash 精确命中 + 站点归属精确匹配（互为后缀匹配找到的 key 必须就是证据来源站）
        hit = (idx.get("need") or {}).get(h)
        if not isinstance(hit, dict):
            return _no("hash_not_in_owed_list")
        try:
            need_dom = self._hrbills_norm_domain(hit.get("dom"))
        except Exception:  # noqa: BLE001
            need_dom = ""
        if not need_dom or str(key or "").strip().lower() != need_dom:
            return _no("site_mismatch")
        # ⑧ 最终裁决
        if str(verdict or "") != "owed" or float(left or 0.0) <= 0:
            return _no("verdict_not_owed")
        # ⑦ 证据时间
        try:
            at = float(hit.get("at") or 0.0)
        except (TypeError, ValueError):
            at = 0.0
        if at <= 0:
            return _no("evidence_at_missing")
        age = float(now) - at
        if age < -3600.0 or age > max(0.0, float(HR_REOPEN_EVIDENCE_MAX_HOURS)) * 3600.0:
            return _no("evidence_stale")
        out["digest"] = {
            "site_key": str(key or ""), "rule": rule,
            "page_ok": bool(gate.get("page_ok")),
            "list_complete": bool(gate.get("list_complete")),
            "coverage": bool(gate.get("coverage")),
            "bar_known": bool(gate.get("bar_known")),
            "bar_total": gate.get("bar_total"),
            "bar_form": gate.get("bar_form"),
            "bar_age_h": gate.get("bar_age_h"),
            "bar_stale": bool(gate.get("bar_stale")),
            "gate_why": str(gate.get("why") or ""),
            "left_h": round(float(left) / 3600.0, 2),
            "evidence_at": at, "evidence_age_h": round(age / 3600.0, 2),
            "index_at": idx.get("at"),
        }
        out["source"] = ("myhr.php:%s" % str(key or ""))[:120]
        out["at"] = at
        out["ok"] = True
        out["why"] = "ok"
        return out

    def _hr_bill_owed_hashes(self) -> Set[str]:
        """★ 19.10.11：**账单里仍欠工时**的 hash 集合（账单口径的保护来源）。

        判据与 ``_hr_obligation`` 的第三来源**同源**：``state == active``（已下完、开始计工时）
        且 ``rule ∈ (site_hr, hit_and_run)``（规则已知才欠），且
        ``seeded_h < need_h + margin``（margin 走 ``_hr_due_hours``，与账单状态机一致）。
        区别只在于这是**集合式**的（不需要 ``TorrentInfo``），供「保护集合」类场景使用
        （硬保护汇总 / 清理候选豁免）。

        ★ 为什么不再拿「跨站来源份集合」当保护判据：那是**第二套工时口径**
        （``CrossSeedSources`` 自己算 ``seeded_sec`` vs ``hours``），与账单 ``seeded_h``
        同源却各存一份快照 → 站点规则一改两份就漂。现在工时真值源只剩账单一处。

        ★ 19.12.4：**站端说欠的一律进集合，不看本地工时、也不看 state**。
        这条是把闭环接上的关键：若只按本地 ``seeded_h`` 判，站端还欠而本地已够的种会被
        排出保护 → 保挂撤销 → 被静默池 pause → 站端停表 → 债务永远清不掉。所以
        ``settled`` 的行只要站端还欠，也照样留在集合里（下一轮 tick 会把它重开成 active）。
        """
        out: Set[str] = set()
        try:
            store = self._hrbills_store()
            bills = store.all() or {}
        except Exception:  # noqa: BLE001
            return out
        _now = time.time()
        _idx: Any = None
        if HR_SETTLE_SITE_GATE:
            try:
                _idx = self._hr_site_debt_index(_now)
            except Exception:  # noqa: BLE001
                _idx = None
        for h, b in (bills or {}).items():
            if not isinstance(b, dict):
                continue
            if str(b.get("rule") or "") not in (RULE_SITE_HR, RULE_HIT_AND_RUN):
                continue
            _hh = str(h or "").strip().lower()
            if not _hh:
                continue
            # ① 站端口径优先：站端说还欠 → 欠（哪怕本地工时已够、哪怕已 settled）
            if _idx is not None:
                try:
                    if self._hr_site_verdict(_hh, str(b.get("site") or ""), _now, _idx)[0] == "owed":
                        out.add(_hh)
                        continue
                except Exception:  # noqa: BLE001
                    pass
            # ② 本地工时口径（原有行为）
            if str(b.get("state") or "") != BILL_STATE_ACTIVE:
                continue
            try:
                need = float(b.get("need_h") or 0.0)
                seeded = float(b.get("seeded_h") or 0.0)
            except (TypeError, ValueError):
                continue
            if need <= 0:
                continue
            try:
                due = float(self._hr_due_hours(need))
            except Exception:  # noqa: BLE001
                due = need
            if seeded + 1e-6 < due:
                out.add(_hh)
        return out

    # ---------------------------------------------------------- 站点解析（三级回退，供回填用）
    def _hrbills_resolve_domain(self, rec: Dict[str, Any], t: Any, groups: Any) -> str:
        """三级站点解析（补识别不出的存量种）：

        ① 账本 ``rec["site"]`` → ``_site_domain_by_name``；
        ② ``TorrentInfo.tracker`` 域名；
        ③ 账本 ``group_id``（即资源）的来源站 ``source_site`` → ``_site_domain_by_name``；
        全部失败 → 返回 ``""``（pending + 计 no_site）。
        """
        rec = rec or {}
        # ① 账本站点 → 域名
        site = str(rec.get("site") or "").strip()
        if site:
            try:
                dom = self._site_domain_by_name(site)
            except Exception:  # noqa: BLE001
                dom = ""
            if dom:
                return self._hrbills_norm_domain(dom)
        # ② tracker 域名
        try:
            tr = str(getattr(t, "tracker", "") or "").strip().lower()
        except Exception:  # noqa: BLE001
            tr = ""
        if tr:
            dom = tr.split("://")[-1].split("/")[0].split(":")[0].strip()
            if dom:
                return self._hrbills_norm_domain(dom)
        # ③ 资源来源站
        try:
            gid = str(rec.get("group_id") or "").strip()
            if groups is not None:
                if not gid:
                    gid = str(groups.group_of(str(getattr(t, "hash", "") or "").strip().lower()) or "")
                grec = (groups.items() or {}).get(gid) or {}
                src = str(grec.get("source_site") or "").strip()
                if src:
                    dom = self._site_domain_by_name(src)
                    if dom:
                        return self._hrbills_norm_domain(dom)
        except Exception:  # noqa: BLE001
            pass
        # ④ 标签推断（复用 hr.py::_hr_domain：站点名 → 账本 → 标签 → tracker）
        #    实测 22 个 carpt 种不在账本里 → ①③ 取不到，只能靠标签（魔流-CARPT-…）。
        try:
            dom = self._hr_domain("", t)
            if dom:
                return self._hrbills_norm_domain(dom)
        except Exception:  # noqa: BLE001
            pass
        return ""
    def _hrbills_seed_fp(self, h: str) -> str:
        """反查 ``mf_seed[hash].resource_id``（= fp）。离线 / 无行 / 异常 → ""。"""
        mf = _mfdb_module()
        if mf is None or not mf.db_available():
            return ""
        try:
            with mf.db_session() as sess:
                row = sess.get(mf.SeedRow, h)
                rid = str(getattr(row, "resource_id", "") or "").strip() if row else ""
                return rid if (len(rid) == 40 and re.fullmatch(r"[0-9a-f]{40}", rid)) else ""
        except Exception:  # noqa: BLE001
            return ""
    def _hrbills_backfill(self, store: HrBillsStore, snap: Dict[str, Any],
                          limit: int = 200) -> Dict[str, Any]:
        """给「本插件托管种」补开账单（**不是**下载器全量）。

        幂等：跳过已有账单；每轮最多开 ``limit`` 张。规则判定同第一阶段
        （``_site_hr_flag`` / ``hit_and_run``；未知 → pending）。站点解析走
        ``_hrbills_resolve_domain`` 三级回退；全失败 → ``site=""``（pending + no_site）。
        """
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        try:
            groups = self._tag_groups()
        except Exception:  # noqa: BLE001
            groups = None
        # ★ 除账本外，还要覆盖「快照里带魔流标签的托管种」——实测 22 个 carpt 种
        #   未登记进账本（手动/外部路径加进来的），只遍历账本会永远漏开账单。
        _extra: Dict[str, Any] = {}
        for _h, _t in (snap or {}).items():
            try:
                _tags = [str(x) for x in (getattr(_t, "tags", None) or [])]
            except Exception:  # noqa: BLE001
                _tags = []
            if not any("魔流" in x for x in _tags):
                continue
            if _skip_hr_bill(_tags):
                continue
            _hh = str(_h or "").strip().lower()
            if _hh and _hh not in ledger:
                _extra[_hh] = {}
        _cand: List[Any] = list((ledger or {}).items()) + list(_extra.items())
        now = time.time()
        opened = no_site = 0
        for h, rec in _cand:
            if opened >= int(limit or 0):
                break
            h = str(h or "").strip().lower()
            if not h:
                continue
            if store.get(h):
                continue  # 已有账单 → 跳过（幂等）
            t = (snap or {}).get(h)
            if t is None:
                continue  # 快照里没有 → 这轮不补（下轮可能补上）
            try:
                _tags = [str(x) for x in (getattr(t, "tags", None) or [])]
                if _skip_hr_bill(_tags):
                    continue  # 跨站/复用/补源副本：不重复开（各自口径自己记账/不判 H&R）
            except Exception:  # noqa: BLE001
                pass
            # ★ 2026-10-11：复用份（downloaded≈0）→ 不开账（复用副本不欠 H&R）
            try:
                if float(getattr(t, "downloaded", 0) or 0) <= 0:
                    continue
            except (TypeError, ValueError):
                pass
            rec = rec or {}
            dom = self._hrbills_resolve_domain(rec, t, groups)
            # ★ 19.12.33：与开账共用同一判定（两道门槛），不过门就不补记。
            try:
                thr = bool(getattr(t, "hit_and_run", False))
            except Exception:  # noqa: BLE001
                thr = False
            rule = self._hr_obligation_rule(dom, thr)
            if not rule:
                continue
            try:
                progress = float(getattr(t, "progress", 0) or 0)
            except (TypeError, ValueError):
                progress = 0.0
            # ★ 15.5.1：H&R 义务自「下载完成」起算 —— 未完成 → 只挂 pending（不算欠）。
            state = (BILL_STATE_ACTIVE if progress >= self._hr_complete_ratio(dom)
                     else BILL_STATE_PENDING)
            if not dom:
                no_site += 1
            need_h = self._hr_need_hours(dom)
            try:
                seeded_h = seed_hours_for_hr(t)
            except Exception:  # noqa: BLE001
                seeded_h = 0.0
            # ★ 19.0.0：fp 强制填——先取账本 group_id（即 resource_id/fp），
            #   没有再反查 mf_seed[hash].resource_id；再不行才允许空（PG 侧 put 还会兜一次）。
            #   （修 18.x 回填硬写 "fp": "" —— 账单只能靠 hash 挂、种一删就成孤儿的根因。）
            fp = str(rec.get("group_id") or "").strip().lower()
            if not (len(fp) == 40 and re.fullmatch(r"[0-9a-f]{40}", fp)):
                fp = self._hrbills_seed_fp(h)
            bill = {
                "site": dom,
                "rule": rule,
                "state": state,
                "need_h": float(need_h),
                "seeded_h": seeded_h,
                "fp": fp,
                "title": str(getattr(t, "title", "") or "")[:200],
                "opened_at": now,
                "last_progress": progress,
                "last_progress_at": now,
                "progress": progress,
                "opened_by": "backfill",
            }
            store.put(h, bill, save=False)
            opened += 1
        return {"opened": opened, "no_site": no_site}

    # ---------------------------------------------------------- 巡检（只改账单状态，不影响删除）
    def _hrbills_tick(self) -> Dict[str, Any]:
        """作废/结清规则（只改账单状态，**不影响删除/保护**）+ 存量回填：

        回填：给账本托管种补开账单（幂等，每轮限量 ≤200）。
        ★ 19.12.40 **默认保留，删除要证据**（Master 2026-11-05 需求书）：
        ① ``progress >= 完成度阈值`` → active（仅明确规则）；
        ② 连续 ``HR_BILLS_STALL_DAYS`` 天无进度 → **保留** + 记 ``stalled_at``
           （种还在却不动，正是该挂住的状态，删账=义务凭空消失）；
        ③ 种从 qB 消失 → active（明确规则）转 breached 违约在案，其余**保留** +
           记 ``missing_since``；只有「站端明确 clear 且缺席超过
           ``HR_BILLS_MISSING_TTL_DAYS``」才销账（qB 抖动/recheck 不能当义务消失）；
        ④ qB 工时够（``seeded_h >= need_h + margin``）**且站端明确 clear** → settled
           （记 ``settled_at``，挂 ``HR_BILLS_SETTLED_TTL_DAYS`` 天后销）。
           站端 ``owed`` → 保留；站端 ``unknown``（抓取失败/记录缺失/覆盖不完整/
           证据过旧）→ **保留** + ``settle_block=site_unknown``，绝不当已结清。
        ⑤ 快照为空 + 账单非空 → 跳过本轮（防下载器 API 抖动误销）。
        生命周期：在下载器 → ``alive=True`` + ``last_seen/seen_by``；消失 → ``alive=False``。

        ★ 与职务彻底解耦：全程只按 hash 读 qB 工时，不看 ``taken_by`` / 标签 ——
          种挂在 H&R / 保种 / 认领 / 刷流名下都能结清，结清也不改别人的归属。
        """
        store = self._hrbills_store()
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        # ★ 11.0.0 第二阶段：存量回填（放在状态判定前 → 新补账单当轮即判定结清）
        backfilled = 0
        no_site = 0
        try:
            _bf = self._hrbills_backfill(store, snap, limit=200)
            backfilled = int((_bf or {}).get("opened") or 0)
            no_site = int((_bf or {}).get("no_site") or 0)
        except Exception as err:  # noqa: BLE001
            try:
                self._log(f"魔流:H&R账单回填异常:{err}", "warning")
            except Exception:  # noqa: BLE001
                pass
        bills = store.all()
        if not bills:
            store.flush()
            return {"bills": 0, "activated": 0, "voided": 0, "settled": 0,
                    "breached": 0, "demoted": 0, "conflicted": 0,
                    "backfilled": backfilled, "no_site": no_site}
        # ★ 19.0.0 安全闸：快照为空（多半是下载器 API 抖动）+ 账单非空 → 跳过本轮，
        #   防止「一次抖动把全部账单当消失销掉」（销账已是默认删，宁可漏一轮）。
        if bills and not snap:
            store.flush()
            return {"bills": len(bills), "activated": 0, "voided": 0, "settled": 0,
                    "breached": 0, "demoted": 0, "skipped_empty_snap": 1,
                    "conflicted": 0,
                    "backfilled": backfilled, "no_site": no_site}
        now = time.time()
        activated = voided = settled = breached = demoted = titles_filled = dropped = 0
        unknown_dropped = 0           # ★ 19.12.33：未定性且已做满 → 销账笔数
        reopened = held_by_site = 0   # ★ 19.12.4：站端口径的两个计数
        reopen_blocked = 0            # ★ 任务 98：人工账单对账未达标 → 保持 settled（fail-closed 可见）
        held_unknown = 0              # ★ 19.12.40：站端判不明 → 保留账单（不结清）
        missing_kept = 0              # ★ 19.12.40：qB 里暂时找不到 → 保留（不销账）
        stalled_kept = 0              # ★ 19.12.40：长时间无进度 → 保留（不销账）
        void_kept = 0                 # ★ 19.12.43：void 墓碑 → 一律跳过（不结清/不重开/不销账）
        manual_kept = 0               # ★ 19.12.46：人工结清 → 任何自动销账/删除一律跳过
        # ★ 19.12.4：站端欠账索引（只读缓存，整轮建一次）
        _hr_idx: Any = None
        if HR_SETTLE_SITE_GATE:
            try:
                _hr_idx = self._hr_site_debt_index(now)
            except Exception:  # noqa: BLE001
                _hr_idx = None
        _drop: List[Any] = []          # ★ 19.12.47：(hash, 守卫, 通道) —— 删除也要过 CAS
        conflicted = 0                 # ★ 19.12.47：CAS 冲突 → 本轮放弃的条数（下轮重判）
        _conflict_hashes: List[str] = []

        def _cas_patch(_h: str, _guard: Dict[str, Any], events: Any = None,
                       **fields: Any) -> bool:
            """条件写：成功 True；冲突/异常 False 并计入 ``conflicted``（不抛、不静默）。

            ★ 19.12.47（任务 91）：**冲突一律放弃本轮**。不用旧快照重试、不用新快照
            重算整轮（重算要重跑站端裁决/进度判定，成本高且会把「放弃」变成「抢写」）；
            下一次巡检本来就是全新快照，天然完成「重读重判」。
            ★ 任务 98：``events`` 随同一次 CAS 写入事件表（同锁 / 同事务）；
            事件写失败 → CAS 整体失败 → 计 conflicted，绝不留下「状态改了没历史」。
            """
            nonlocal conflicted
            if self._hrbills_cas(store, _h, _guard, events=events, **fields).get("ok"):
                return True
            conflicted += 1
            if len(_conflict_hashes) < 5:
                _conflict_hashes.append(_h)
            return False

        for h, b in list(bills.items()):
            if not isinstance(b, dict):
                continue
            t = (snap or {}).get(h)
            cur_state = str(b.get("state") or "")
            # ★ 19.12.47（任务 91）：把「判定依据」在**本轮唯一一次**抄成守卫。
            #   后面每个写回点都带上它做 CAS —— 判定期间若有人工结清/作废落地，
            #   这次写入自然落空（conflict），而不是把人工结论覆盖掉。
            _guard = self._hrbills_guard(b)
            # ★ 任务 98：本行本轮要随 CAS 一起落盘的审计事件（自动结清等）。
            #   统一在循环末尾的 `_cas_patch` 里带下去，保证「状态 + 事件」同生共死。
            _events: List[Dict[str, Any]] = []
            # ★ 19.12.47：本轮计数基线 —— CAS 冲突时回滚到它（只回滚「变更类」计数，
            #   「保留类」计数如 manual_kept/missing_kept 描述的是判定，不是写入）。
            _cnt0 = (activated, demoted, settled, titles_filled)
            if cur_state == BILL_STATE_VOID:
                # ★ 19.12.43：void 是**终态墓碑** —— 不结清、不重开、不销账、不刷存活列。
                #   它同时是回填/开账的幂等挡板（``store.get(h)`` 存在即跳过），
                #   所以这里绝不能把它删掉，也不能因为本地工时够了就改回 settled。
                void_kept += 1
                continue
            _known_rule = str(b.get("rule") or "") in (RULE_SITE_HR, RULE_HIT_AND_RUN)
            if t is None:
                # ★ 19.12.40（Master 2026-11-05「qB 中暂时找不到种子的账单，不得直接删除」）：
                #   旧口径**默认删**（只有 active/breached 例外），把「qB 抖一下、recheck、
                #   刚被外部工具删了又加、站点同步滞后」全当成了「义务消失」。删账 = 保护
                #   没了 + 站端还欠着，是最贵的一种错。
                #   新口径：**默认保留**，只认「站端明确 clear」这一个销账证据；
                #   且连续缺席超过 ``HR_BILLS_MISSING_TTL_DAYS`` 仍未 clear → 保留并计数，
                #   等人工 ``hrbills_purge_missing``（不自动删孤儿）。
                _ms = float(b.get("missing_since") or 0) or now
                _gone: Dict[str, Any] = {"alive": False, "last_seen": now,
                                         "seen_by": "tick_gone"}
                if not b.get("missing_since"):
                    _gone["missing_since"] = now
                # 站端口径（只读缓存；判不出来 → unknown，绝不当 clear 用）
                _gv = "unknown"
                if _hr_idx is not None and _known_rule:
                    try:
                        _gv = self._hr_site_verdict(h, str(b.get("site") or ""), now, _hr_idx)[0]
                    except Exception:  # noqa: BLE001
                        _gv = "unknown"
                if cur_state == BILL_STATE_ACTIVE and _known_rule:
                    # 明确欠债的种消失了 → 违约在案（保护不解除），不是销账
                    if _cas_patch(h, _guard, state=BILL_STATE_BREACHED,
                                  breached_at=now, **_gone):
                        breached += 1
                    continue
                if cur_state == BILL_STATE_BREACHED and _known_rule:
                    _cas_patch(h, _guard, **_gone)
                    continue  # 违约在案：保留
                # 唯一自动销账出口：站端明确说这颗不欠了（且已过缺席宽限期）
                # ★ 19.12.46（任务 89）：**人工结清账单不自动销账**。站端 clear 只证明
                #   「站不欠了」，不证明「人工结清结论该消失」；删行还会让
                #   ``_hrbills_backfill`` 的幂等判据（store.get 存在）失效 → 同 hash 被
                #   重开成 active，人工结论反转成「还欠」。保留行，只刷新缺席快照。
                # ★ 19.12.47（任务 91）：删除也要带守卫 —— 上面的判断基于旧快照，
                #   期间若有人工结清落地，这行已变成 manual，必须删不动。
                _aged = (now - _ms) >= max(0.0, float(HR_BILLS_MISSING_TTL_DAYS)) * 86400.0
                if _gv == "clear" and _aged and not _is_manual_settled(b):
                    _drop.append((h, _guard, "clear"))
                    continue
                if _cas_patch(h, _guard, **_gone):
                    if _is_manual_settled(b):
                        manual_kept += 1
                    else:
                        missing_kept += 1
                continue
            # ★ 19.0.0 生命周期：还在下载器 → 刷新存活三列（统一对账口径）。
            #   settled 行挂够即销（TTL）→ 账单表只剩「还欠着」的。
            if cur_state == BILL_STATE_SETTLED:
                # ★ 19.12.44（人工结清保护）：settlement_method=manual → 自动任务
                #   **不得 TTL 删除**。人工结清是「人工核实后落定」的结论，到期销账
                #   不能覆盖 —— 发现结清错误走独立撤销口。
                # ★ 任务 98：原实现在这里直接 `pass`（根本不读站端），于是「站端可靠
                #   证据证明义务仍在」也无法纠错。现改为**唯一一条受控例外**：
                #   `_hr_reopen_evidence()` 八项门槛全过才允许重开；异常/缺数据/
                #   unknown/规则不明/列表不全/hash 不匹配/站点归属不明 → 一律保持
                #   settled、零写入、零事件（场景 C 的 fail-closed 显式重做）。
                if _is_manual_settled(b):
                    _v, _left = "unknown", 0.0
                    _ev: Dict[str, Any] = {}
                    if HR_RECONCILE_REOPEN and _hr_idx is not None and _known_rule:
                        try:
                            _v, _left = self._hr_site_verdict(
                                h, str(b.get("site") or ""), now, _hr_idx)
                        except Exception:  # noqa: BLE001
                            _v, _left = "unknown", 0.0
                        try:
                            _ev = self._hr_reopen_evidence(h, b, now, _hr_idx, _v, _left)
                        except Exception:  # noqa: BLE001
                            _ev = {"ok": False, "why": "evidence_exception"}
                    if not _ev.get("ok"):
                        reopen_blocked += 1
                    else:
                        _sat = float(b.get("settled_at") or 0) or now
                        evs: List[Dict[str, Any]] = []
                        # ① 兼容历史账单：老版本人工结清没有事件行 → 按行上四列补录
                        #    一条 legacy 事件（用原 settled_at 当事件时刻，不假造操作时刻）。
                        _hist = self._hr_bill_history(h)
                        if not any(str(x.get("event_type") or "") in
                                   (EVT_MANUAL_SETTLED, EVT_LEGACY_MANUAL) for x in _hist):
                            evs.append(self._hr_bill_event(
                                h, EVT_LEGACY_MANUAL, b, at=_sat,
                                actor=str(b.get("settled_by") or "legacy")[:64],
                                reason=str(b.get("settlement_reason") or "历史账单补录")[:300],
                                prev_state="", new_state=BILL_STATE_SETTLED,
                                evidence_source="legacy_bill_row",
                                dedup_key="%s|%s|%.6f" % (h, EVT_LEGACY_MANUAL, _sat)))
                        # ② 重新打开事件：bill_snapshot = 原人工结清四列的不可变副本，
                        #    evidence_* = 这份 myhr 证据的来源/时刻/摘要。
                        evs.append(self._hr_bill_event(
                            h, EVT_REOPENED, b, at=now, actor=EVT_SYSTEM_ACTOR,
                            reason="站端 myhr 可靠证据证明义务仍存在（剩余 %.2fh）"
                                   % (float(_left) / 3600.0),
                            prev_state=BILL_STATE_SETTLED, new_state=BILL_STATE_ACTIVE,
                            evidence_source=_ev.get("source"), evidence_at=_ev.get("at"),
                            evidence_digest=_ev.get("digest"),
                            dedup_key="%s|%s|%.6f|%.6f" %
                                      (h, EVT_REOPENED, _sat, float(_ev.get("at") or 0.0))))
                        # ③ CAS 重开：guard 仍是 (settled, manual)。行上四列清空，
                        #    但原记录已进事件表；settlement_method 改成 "reopened"
                        #    （不是 "auto"、也不是 "manual"）→ 8 个 `_is_manual_settled`
                        #    保护点自动让位，账单重新进入正常 H&R 跟踪。
                        if _cas_patch(h, _guard, events=evs,
                                      state=BILL_STATE_ACTIVE, settled_at=None,
                                      settlement_method=HR_REOPEN_SETTLE,
                                      settled_by=None, settlement_reason=None,
                                      alive=True, last_seen=now, seen_by="tick_reopen_site"):
                            reopened += 1
                            try:
                                self._log(
                                    "魔流:H&R 人工结清纠错重开 %s（%s）站端还需 %.1fh，"
                                    "证据 %s @%.0f，原结清人 %s 已归档"
                                    % (str(h)[:12], str(b.get("site") or "?"),
                                       float(_left) / 3600.0, str(_ev.get("source") or "?"),
                                       float(_ev.get("at") or 0.0),
                                       str(b.get("settled_by") or "?")))
                            except Exception:  # noqa: BLE001
                                pass
                        continue   # 人工账单不进 TTL；下轮 state=active 也不再进此分支
                else:
                    # ★ 19.12.4 站端翻案：本地判「挂够」结清了，站端 myhr 却还欠 →
                    #   **重开**（settled → active）。这是「本地够了、站端还欠」的收口：
                    #   不重开的话，这行会一直装作结清、静默池还按「不欠」把它 pause，
                    #   站端计时随之停表 —— 债务永远清不掉，还因为 TTL 到期被销账无痕。
                    #   ★ 任务 98：日常重开**不放宽也不收紧判据**，只补一条事件留痕。
                    if _hr_idx is not None and _known_rule:
                        try:
                            _v, _left = self._hr_site_verdict(h, str(b.get("site") or ""), now, _hr_idx)
                        except Exception:  # noqa: BLE001
                            _v, _left = "unknown", 0.0
                        if _v == "owed":
                            # ★ 19.12.47（任务 91）：这是「state 单独不够」的正面例子 ——
                            #   人工结清把 settled/auto 改成 settled/manual 时 state 仍是
                            #   settled，只比 state 的 CAS 会放行，把结清审计清空。
                            _rev = self._hr_bill_event(
                                h, EVT_REOPENED, b, at=now, actor=EVT_SYSTEM_ACTOR,
                                reason="站端翻案重开（日常口径，剩余 %.2fh）"
                                       % (float(_left) / 3600.0),
                                prev_state=BILL_STATE_SETTLED,
                                new_state=BILL_STATE_ACTIVE,
                                evidence_source="tick_daily_reopen",
                                dedup_key="%s|%s|%.6f" %
                                          (h, "daily_reopen", float(b.get("settled_at") or 0)))
                            if _cas_patch(h, _guard, events=[_rev],
                                          state=BILL_STATE_ACTIVE, settled_at=None,
                                          settlement_method=None, settled_by=None,
                                          settlement_reason=None,
                                          alive=True, last_seen=now, seen_by="tick_reopen_site"):
                                reopened += 1
                                try:
                                    self._log(
                                        "魔流:H&R 站端翻案重开 %s（%s）站端还需 %.1fh，本地已挂 %.1fh"
                                        % (str(h)[:12], str(b.get("site") or "?"),
                                           float(_left) / 3600.0, float(b.get("seeded_h") or 0.0)))
                                except Exception:  # noqa: BLE001
                                    pass
                            continue
                    _sa = float(b.get("settled_at") or 0) or now
                    if now - _sa >= HR_BILLS_SETTLED_TTL_DAYS * 86400.0:
                        _drop.append((h, _guard, "ttl"))
                        continue
            try:
                progress = float(getattr(t, "progress", 0) or 0)
            except (TypeError, ValueError):
                progress = float(b.get("progress") or 0)
            try:
                seeded_h = seed_hours_for_hr(t)
            except Exception:  # noqa: BLE001
                seeded_h = float(b.get("seeded_h") or 0)
            # ★ 2026-10-10：规则闸——只有明确 H&R 规则（site_hr / hit_and_run）才算「欠」。
            #   unknown / 空规则一律不算（对齐 ``_hr_obligation``），并自愈存量错误 active。
            fields: Dict[str, Any] = {"progress": progress, "seeded_h": seeded_h,
                                      "alive": True, "last_seen": now, "seen_by": "tick"}
            # ★ 15.8.1：补空标题（开账时快照可能还没这个种，如刚加的音乐种；只在能取到时补）。
            if not str(b.get("title") or "").strip():
                _tt = str(getattr(t, "title", "") or "").strip()
                if _tt:
                    fields["title"] = _tt[:200]
                    titles_filled += 1
            # ★ 种重新出现（breached → 恢复 active，复欠重进继续挂）
            if cur_state == BILL_STATE_BREACHED:
                if _known_rule:
                    fields["state"] = BILL_STATE_ACTIVE
                    fields["breached_at"] = None
                    activated += 1
                else:
                    # ★ 2026-10-10：unknown 规则不算欠 → 恢复也降回 pending
                    fields["state"] = BILL_STATE_PENDING
                    fields["breached_at"] = None
                    demoted += 1
            elif cur_state == BILL_STATE_ACTIVE and not _known_rule:
                # ★ 2026-10-10 自愈：存量 unknown-active（凭空欠债）降回 pending。
                fields["state"] = BILL_STATE_PENDING
                demoted += 1
            elif cur_state == BILL_STATE_SETTLED and not _known_rule \
                    and str(b.get("settlement_method") or "") != "manual":
                # ★ 2026-10-11 自愈：存量 unknown-settled（无 H&R 规则却记结清）降回 pending。
                #   ★ 19.12.44：人工结清的不降级 —— 自动任务不得覆盖人工结论。
                fields["state"] = BILL_STATE_PENDING
                demoted += 1
            # ★ 15.5.1（Master 16:33）：未完成的种不产生 H&R 义务 → active 账单降回 pending。
            #   兼容 15.5.1 之前「下载即 active」开出的历史账单（下一轮自动清掉虚欠）。
            elif progress < self._hr_complete_ratio(str(b.get("site") or "")) and cur_state == BILL_STATE_ACTIVE:
                fields["state"] = BILL_STATE_PENDING
                demoted += 1
            if progress >= self._hr_complete_ratio(str(b.get("site") or "")):
                # ★ 19.12.33：``unknown`` 规则 + **已做满最保守工时** → 销账（删行）。
                #   ★ 19.12.43：这里仍是**真删**、不走 void 墓碑 —— 它清的是「本就不该存在
                #   的僵尸账」（新口径已不再产生 unknown 账），删掉也不会被回填重开
                #   （``_hr_obligation_rule`` 对 unknown 直接返回空）。人工核销仍走墓碑。
                #   逐种站（YemaPT ``per_torrent_hr=True``）站点级规则未知时，开账走
                #   ``rule=unknown``「跟踪漏记」；这类账永不激活（下一行只认已知规则）、
                #   也永不结清（下方 settled 分支的 ``_known_rule`` 闸），只要种还在 qB
                #   就一直 pending —— 展示层按「未 settled/void」数欠账时，就把这些僵尸
                #   账谎报成「还欠」（2026-11-05 线上 22 条，工时 137h+ vs need 24h）。
                #   最保守口径都做满了 → 这行账再无跟踪价值，删掉让账本与实际一致。
                if (not _known_rule) and cur_state == BILL_STATE_PENDING \
                        and not _is_manual_settled(b) \
                        and seeded_h >= float(b.get("need_h") or 24.0) + self._hr_margin_hours():
                    _drop.append((h, _guard, "unknown"))
                    continue
                # ① 完成 → active（★ 2026-10-10：仅限**明确 H&R 规则**才激活）
                if cur_state == BILL_STATE_PENDING and _known_rule:
                    fields["state"] = BILL_STATE_ACTIVE
                    activated += 1
                # ④ 挂够 → settled（★ 11.13.0：达到线额外加冗余安全垫 ``_hr_margin_hours()``）
                #   ★ 2026-10-11：仅限明确 H&R 规则（unknown 不算欠、不结清）。
                #   ★ 19.12.4 站端闸门：本地挂够了**不代表站端认账**。结清前先看站端
                #     myhr 最近一轮对账 —— 站端说还欠就留在 active 继续挂（下一轮再看）。
                #   ★ 19.12.40（fail-closed）：旧口径「站端不可判 → 结清」是**赌**。
                #     现在只有站端**明确 clear** 才落 settled；``owed`` 与 ``unknown``
                #     一律保留账单 + 记原因，等下一轮复查（Master 2026-11-05：
                #     「查询失败、记录暂时缺失、状态不明确 —— 一律不得视为已结清」）。
                #     开关关掉（HR_SETTLE_SITE_GATE=False）= 明确退回本地工时口径（兼容旧行为）。
                need_h = float(b.get("need_h") or 24.0)
                due_h = need_h + self._hr_margin_hours()
                if _known_rule and cur_state not in (BILL_STATE_SETTLED, BILL_STATE_VOID) and seeded_h >= due_h:
                    _v, _left = "unknown", 0.0
                    if _hr_idx is not None:
                        try:
                            _v, _left = self._hr_site_verdict(h, str(b.get("site") or ""), now, _hr_idx)
                        except Exception:  # noqa: BLE001
                            _v, _left = "unknown", 0.0
                    if _v == "owed":
                        held_by_site += 1
                        fields["settle_block"] = "site_owed"
                        try:
                            self._log(
                                "魔流:H&R 站端仍欠 %s（%s）站端还需 %.1fh，本地已挂 %.1fh → 暂不结清"
                                % (str(h)[:12], str(b.get("site") or "?"),
                                   float(_left) / 3600.0, float(seeded_h or 0.0)))
                        except Exception:  # noqa: BLE001
                            pass
                    elif _v == "unknown" and HR_SETTLE_SITE_GATE:
                        # 站端给不出结论（抓取失败/覆盖不完整/记录缺失/证据过旧/数据未同步）
                        # → **不结清**。这是本闸门唯一正确的方向：账单多留一轮的代价远小于
                        # 误判结清（误判 = 债没了、保护没了、站端封号）。
                        held_unknown += 1
                        fields["settle_block"] = "site_unknown"
                        fields["settle_block_at"] = now
                        try:
                            self._log(
                                "魔流:H&R 站端状态不明确 %s（%s）本地已挂 %.1fh → 保留账单待复查"
                                % (str(h)[:12], str(b.get("site") or "?"),
                                   float(seeded_h or 0.0)))
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        fields["state"] = BILL_STATE_SETTLED
                        fields["settled_at"] = now
                        fields["settlement_method"] = "auto"  # ★ 19.12.44：自动结清标记
                        fields["settle_block"] = None
                        # ★ 任务 98：自动结清也留下事件（L4 曾是完全空白的一段历史）。
                        #   快照保留判定前的 active 状态，操作人固定 system/hrbills_tick。
                        _events.append(self._hr_bill_event(
                            h, EVT_AUTO_SETTLED, b, at=now, actor=EVT_SYSTEM_ACTOR,
                            reason="本地工时达标且站端明确 clear，自动结清",
                            prev_state=cur_state, new_state=BILL_STATE_SETTLED,
                            evidence_source="tick_site_clear"))
                        settled += 1
                fields["last_progress"] = progress
                fields["last_progress_at"] = now
            else:
                last = float(b.get("last_progress") or 0)
                last_at = float(b.get("last_progress_at") or 0) or now
                if progress > last + 1e-9:
                    fields["last_progress"] = progress
                    fields["last_progress_at"] = now
                    fields["stalled_at"] = None       # 恢复下载 → 摘掉停滞标记
                elif now - last_at >= HR_BILLS_STALL_DAYS * 86400.0:
                    # ★ 19.12.40：**不再作废/删账**。种还在 qB 却没进度，说明它暂停了、
                    #   没 peer、或 client 拒绝连接 —— 这恰恰是 H&R 最该挂住的状态。
                    #   删账 = 义务凭空消失（站端还欠、保护没了）。只标记，保留待复查。
                    if not b.get("stalled_at"):
                        fields["stalled_at"] = now
                    stalled_kept += 1
            # ★ 19.12.47（任务 91）：**条件写**。判定基于本轮快照，写入必须校验快照未变；
            #   冲突 = 放弃本轮（本轮计数一并回滚，绝不虚报「已结清」）。
            #   这一步就是「tick 用旧快照把 manual 写成 auto」的修复点。
            if not _cas_patch(h, _guard, events=(_events or None), **fields):
                activated, demoted, settled, titles_filled = _cnt0
        if _drop:
            # ★ 19.12.47（任务 91）：删除同样带守卫 —— 判定基于旧快照，期间若有人工
            #   结清落地，行已不是「可销账」状态，必须删不动（删了会被回填重开成 active）。
            try:
                _dres = store.drop_many_if([(x[0], x[1]) for x in _drop])
            except Exception:  # noqa: BLE001
                _dres = None
            _gone_set = set((_dres or {}).get("dropped") or []) if isinstance(_dres, dict) else set()
            if not isinstance(_dres, dict):
                conflicted += len(_drop)   # store 不支持/异常 → 全部视为未删（fail-closed）
            for _h2, _g2, _tag in _drop:
                if _h2 not in _gone_set:
                    if isinstance(_dres, dict):
                        conflicted += 1
                        if len(_conflict_hashes) < 5:
                            _conflict_hashes.append(_h2)
                    continue
                dropped += 1
                if _tag == "unknown":
                    unknown_dropped += 1
        store.flush()
        # ★ 2026-10-11：清理误开账单（unknown 规则 + 复用份 downloaded≈0）→ 批量删。
        _wrong: List[Any] = []
        for _h, _b in (bills or {}).items():
            if not isinstance(_b, dict):
                continue
            if str(_b.get("state") or "") == BILL_STATE_VOID:
                continue  # ★ 19.12.43：墓碑只由人工清（drop_void），自动清理不得动它
            # ★ 19.12.46（任务 89）：人工结清 → **自动清理一律跳过**。
            #   这条路径此前只走 `_wrong` 通道（不计 dropped、无日志），删掉人工结清账
            #   完全无声，比「可见的销账」更危险；删完还会被 backfill 重开成 active。
            if _is_manual_settled(_b):
                manual_kept += 1
                continue
            if str(_b.get("rule") or "") not in (RULE_SITE_HR, RULE_HIT_AND_RUN):
                continue  # unknown 账单交给自愈降级（pending），不删
            _t = (snap or {}).get(_h)
            if _t is not None:
                try:
                    _ratio = self._hr_complete_ratio(str(_b.get("site") or ""))
                    if float(getattr(_t, "progress", 0) or 0) >= _ratio \
                            and float(getattr(_t, "downloaded", 0) or 0) <= 0:
                        # ★ 19.12.47：已完成却从未下载字节 = 复用份（守卫随行，删除前校验）
                        _wrong.append((_h, self._hrbills_guard(_b)))
                except (TypeError, ValueError):
                    pass
        if _wrong:
            try:
                _wres = store.drop_many_if(_wrong)
            except Exception:  # noqa: BLE001
                _wres = None
            if isinstance(_wres, dict):
                _wskip = list(_wres.get("skipped") or [])
                conflicted += len(_wskip)
                for _h3 in _wskip[:5]:
                    if len(_conflict_hashes) < 5:
                        _conflict_hashes.append(str(_h3))
            else:
                conflicted += len(_wrong)
        # ★ 19.12.43：``drop_void()`` 已从这里移除 —— 墓碑必须活过每一轮，否则回填会把
        #   人工作废的账重新开回来（旧 2026-10-11 口径「作废就删了」的坑）。
        #   要清墓碑只能人工走 ``drop_void()``（与 ``hrbills_void`` 成对，且不可逆）。
        # ★ 19.12.47（任务 91）：CAS 冲突必须**可见**（不是静默丢弃、也不是失败）——
        #   行上有别的判定落地过（多半是人工结清/作废），本轮让位，下轮全新快照重判。
        if conflicted:
            try:
                self._log(
                    "魔流:H&R 账单巡检 %d 条判定因并发变更放弃（让位给人工/其它写入，下轮重判）：%s"
                    % (conflicted, ",".join(str(x)[:12] for x in _conflict_hashes)),
                    "info")
            except Exception:  # noqa: BLE001
                pass
        return {"bills": len(bills), "activated": activated, "voided": voided,
                "settled": settled, "breached": breached, "demoted": demoted,
                "dropped": dropped, "titles_filled": titles_filled,
                "reopened": reopened, "reopen_blocked": reopen_blocked,
                "held_by_site": held_by_site,
                "held_unknown": held_unknown,
                "missing_kept": missing_kept, "stalled_kept": stalled_kept,
                "manual_kept": manual_kept,
                "void_kept": void_kept,
                "unknown_dropped": unknown_dropped,
                "conflicted": conflicted,
                "backfilled": backfilled, "no_site": no_site}

    # ---------------------------------------------------------- 干跑（只读，不落库）
    def _hrbills_dryrun(self) -> Dict[str, Any]:
        """对当前所有本插件托管的种算「如果现在就开账会怎样」的分桶（只读）。"""
        store = self._hrbills_store()
        _bills = store.all() or {}
        existing = set(_bills.keys())
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        buckets = {k: [] for k in (
            "would_open", "would_active", "would_pending",
            "already_enough", "needs_protection_now", "no_hr_site", "no_fp",
        )}
        # ★ 11.0.0 第二阶段：把「若生效会受保护」的完整 hash 收集起来（最多 200，供人工核对）
        would_protect: List[str] = []
        # ★ 只统计「本插件托管的种」（状态账本 = 托管真值源），**不是**下载器全量
        #   （旧稿遍历全量快照 → 会把全机所有种都算进 would_open，数字虚高）。
        for h, rec in (ledger or {}).items():
            h = str(h or "").strip().lower()
            if not h:
                continue
            t = (snap or {}).get(h)
            if t is None:
                continue
            rec = rec or {}
            site = str(rec.get("site") or "").strip()
            dom = ""
            if site:
                try:
                    dom = self._site_domain_by_name(site) or site
                except Exception:  # noqa: BLE001
                    dom = site
            dom = self._hrbills_norm_domain(dom)
            if not dom:
                tr = str(getattr(t, "tracker", "") or "").strip().lower()
                dom = tr.split("://")[-1].split("/")[0].split(":")[0].strip() if tr else ""
            example = {"hash": h[:12], "title": str(getattr(t, "title", "") or "")[:60],
                       "site": dom}
            if h in existing:
                continue
            buckets["would_open"].append(example)
            try:
                site_hr = self._site_hr_flag(dom) if dom else None
            except Exception:  # noqa: BLE001
                site_hr = None
            try:
                thr = bool(getattr(t, "hit_and_run", False))
            except Exception:  # noqa: BLE001
                thr = False
            if site_hr is False and not thr:
                # 站点规则**明确无 H&R** → 不需要账单（与「未知」区分开）
                buckets["no_hr_site"].append(example)
                continue
            known = (site_hr is True) or thr
            try:
                need = self._hr_need_hours(dom)
            except Exception:  # noqa: BLE001
                need = float(HR_NEED_HOURS_DEFAULT)
            try:
                seeded_h = seed_hours_for_hr(t)
            except Exception:  # noqa: BLE001
                seeded_h = 0.0
            if known:
                buckets["would_active"].append(example)
                if seeded_h >= need:
                    buckets["already_enough"].append(example)
                else:
                    buckets["needs_protection_now"].append(example)
                    if len(would_protect) < 200:
                        would_protect.append(h)
            else:
                buckets["would_pending"].append(example)
        # no_fp：已开账单里没算出特征码的（自动路径「无 fp 不下载」的观测面）
        for _h, _b in (_bills or {}).items():
            if isinstance(_b, dict) and not str(_b.get("fp") or "").strip():
                buckets["no_fp"].append({"hash": str(_h)[:12],
                                         "title": str(_b.get("title") or "")[:60],
                                         "site": str(_b.get("site") or "")})
            # 已生效账单里「active + 已知规则 + 没挂够」的种 → 若生效会被保护
            if isinstance(_b, dict):
                try:
                    if str(_b.get("state") or "") == BILL_STATE_ACTIVE \
                            and str(_b.get("rule") or "") in (RULE_SITE_HR, RULE_HIT_AND_RUN):
                        _need = float(_b.get("need_h") or 24.0)
                        _seed = float(_b.get("seeded_h") or 0.0)
                        if _seed + 1e-6 < _need and len(would_protect) < 200:
                            would_protect.append(str(_h).strip().lower())
                except Exception:  # noqa: BLE001
                    continue
        return {"managed_total": len(ledger or {}),
                "would_protect_hashes": would_protect[:200],
                **{k: {"count": len(v), "samples": v[:10]} for k, v in buckets.items()}}

    # ---------------------------------------------------------- 统计
    def _hrbills_stats(self) -> Dict[str, Any]:
        """落库账单按 state/rule/site 计数 + 生效开关 + 回填/无站点观测。"""
        out = self._hrbills_store().stats()
        out["enforcing"] = bool(HR_BILLS_ENFORCE)
        return out

    # ------------------------------------------- 逐种 H&R 站审计（11.7.0）
    def _hr_per_torrent_audit(self) -> Dict[str, Any]:
        """★ 逐种 H&R 站（如野马PT）的账单审计（**纯只读，不联网**）。

        背景：逐种开关站的 H&R 由**发布者逐种标记**决定（站点级无规则）。11.7.0 起
        下载瞬间把候选标记落进账单 ``rule``；本审计把「已有账单」按 ``rule`` 摊开，
        让 ``unknown``（= 未读到逐种标记，不保护不罚，可能是**漏记的义务**）可见。

        判定依据：站点规则 ``per_torrent_hr``（不是猜域名）+ 账单 ``site/rule/state``。
        返回：逐站分组 + 汇总 + 原因链（含建议动作）。
        """
        store = self._hrbills_store()
        sites: Dict[str, Dict[str, Any]] = {}
        totals = {"sites": 0, "bills": 0, "hit_and_run": 0, "site_hr": 0, "unknown": 0,
                  "active": 0, "pending": 0, "settled": 0, "void": 0}
        for h, b in (store.all() or {}).items():
            if not isinstance(b, dict):
                continue
            dom = str(b.get("site") or "").strip().lower()
            if not dom:
                continue
            try:
                if not self._site_per_torrent_hr(dom):
                    continue
            except Exception:  # noqa: BLE001
                continue
            g = sites.setdefault(dom, {
                "domain": dom, "per_torrent_hr": True, "bills": 0,
                "by_rule": {"hit_and_run": 0, "site_hr": 0, "unknown": 0},
                "by_state": {}, "unknown_bills": [], "protected_bills": [],
            })
            hh = str(h or "").strip().lower()
            rule = str(b.get("rule") or RULE_UNKNOWN)
            state = str(b.get("state") or "")
            g["bills"] += 1
            totals["bills"] += 1
            if rule in g["by_rule"]:
                g["by_rule"][rule] += 1
                totals[rule] += 1
            if state in totals:
                totals[state] += 1
            g["by_state"][state] = int(g["by_state"].get(state) or 0) + 1
            _row = {"hash": hh, "title": str(b.get("title") or "")[:80],
                    "state": state, "rule": rule,
                    "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                    "need_h": round(float(b.get("need_h") or 0.0), 2),
                    "opened_by": str(b.get("opened_by") or "")}
            if rule == RULE_UNKNOWN and state != BILL_STATE_VOID:
                g["unknown_bills"].append(_row)
            elif rule == RULE_HIT_AND_RUN and state == BILL_STATE_ACTIVE:
                g["protected_bills"].append(_row)
        totals["sites"] = len(sites)
        return {
            "sites": [sites[k] for k in sorted(sites)],
            "totals": totals,
            "reason_chain": [
                {"rule": "site/per_torrent_hr",
                 "inputs": {"source_of_truth": "sites/rules.py（内置表/手填）"},
                 "verdict": "逐种 H&R 站；站点级无 H&R 规则"},
                {"rule": "bill/rule",
                 "inputs": {"source_of_truth": "hr_bills.json；11.7.0 起由下载瞬间的候选标记落定"},
                 "verdict": "hit_and_run=欠；unknown=未读到标记（不保护不罚，可能是漏记）"},
            ],
            "notes": ("unknown 账单：若是 11.7.0 之前开的历史账单，或走旁路(MP 接口/手动)加的种，"
                      "可能漏记逐种标记 → 建议用站点 API 核对后作废或升级；"
                      "href=GET /agent/blindspot 看旁路盲区；"
                      "人工作废：GET /tags?action=hrbills_void&hash=<h>&reason=resolved_no_hr&confirm=1"),
        }

    # ---------------------------------------------------------- 违约清单（11.11.0）
    def _hr_breaches(self) -> Dict[str, Any]:
        """★ H&R 违约清单（只读）：active/breached 账单 + 种已从下载器消失。

        归因：删除台账（mf_deletions）命中 `ok=true` → 本插件删（gate bug 升级 critical）；
        否则 → 外部删。只读，不写任何账本/账单。
        """
        store = self._hrbills_store()
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        deleted_ok: Set[str] = set()
        deleted_rows: Dict[str, Dict[str, Any]] = {}
        try:
            # ★ 19.0.0：走统一读口（真值源 mf_deletions 表，离线回退 JSONL），
            #   不再直读 deletions.jsonl（避免第二真值源）。
            _rows = self._agent_deletions_rows() if hasattr(self, "_agent_deletions_rows") else []
            for _row in (_rows or []):
                if _row.get("ok") and not _row.get("blocked"):
                    _dh = str(_row.get("hash") or "").strip().lower()
                    if _dh:
                        deleted_ok.add(_dh)
                        deleted_rows[_dh] = _row
        except Exception:  # noqa: BLE001
            pass
        breaches: List[Dict[str, Any]] = []
        at_risk: List[Dict[str, Any]] = []  # ★ 11.13.0：种还在、但快到期且未达标
        for h, b in (store.all() or {}).items():
            if not isinstance(b, dict):
                continue
            st = str(b.get("state") or "")
            hh = str(h or "").strip().lower()
            if st not in (BILL_STATE_ACTIVE, BILL_STATE_BREACHED):
                continue
            if hh in snap:
                # ★ 11.13.0：种还在 qB（未违约）→ 看它是否「临近到期」
                _dl = self._hr_deadline(b)
                if _dl.get("at_risk"):
                    at_risk.append({
                        "hash": hh, "site": str(b.get("site") or ""),
                        "title": str(b.get("title") or "")[:120],
                        "bill_state": st, "rule": str(b.get("rule") or ""),
                        "need_h": round(float(b.get("need_h") or 0.0), 2),
                        "due_h": _dl.get("due_h"),
                        "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                        "window_h": _dl.get("window_h"),
                        "hours_left": _dl.get("hours_left"),
                        "deadline_at": _dl.get("deadline_at"),
                        "severity": "warning",
                        "rescue_hint": "GET /agent/hr/bills?site=" + str(b.get("site") or "") + "&live=1",
                    })
                continue
            attr = "plugin_deleted" if hh in deleted_ok else "external_deleted"
            gate_bug = attr == "plugin_deleted"
            # ★ 14.0.0 归因细分：删除时账单是否已在册？在册却放行 = **闸门漏**（gate_miss）；
            #   删除早于开账 = 账单/口径后置（口径差，rule_drift）——margin 口径统一正收敛这一类。
            gate_bug_kind = ""
            _del_row: Dict[str, Any] = deleted_rows.get(hh) or {}
            _del_ts = 0.0
            if _del_row:
                try:
                    _del_ts = float(_del_row.get("ts") or 0.0)
                except (TypeError, ValueError):
                    _del_ts = 0.0
            if gate_bug:
                try:
                    _opened = float(b.get("opened_at") or 0.0)
                except (TypeError, ValueError):
                    _opened = 0.0
                gate_bug_kind = "gate_miss" if (_opened and _del_ts and _opened <= _del_ts) else "rule_drift"
            breaches.append({
                "hash": hh, "site": str(b.get("site") or ""),
                "title": str(b.get("title") or "")[:120],
                "bill_state": st, "rule": str(b.get("rule") or ""),
                "need_h": round(float(b.get("need_h") or 0.0), 2),
                "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                "opened_at": float(b.get("opened_at") or 0.0),
                "attribution": attr, "gate_bug": gate_bug,
                "gate_bug_kind": gate_bug_kind,
                "delete_source": str(_del_row.get("source") or ""),
                "deleted_at": _del_ts,
                "severity": "critical" if gate_bug else "high",
                "breached_at": b.get("breached_at") or 0,
                "rescue_hint": "GET /tags?action=hr_reconcile&site=" + str(b.get("site") or "") + "&confirm=1",
            })
        at_risk = sorted(at_risk, key=lambda x: (x.get("hours_left") if x.get("hours_left") is not None else 1e9))[:50]
        return {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "totals": {"breached": len(breaches),
                       "critical": sum(1 for x in breaches if x.get("gate_bug")),
                       "gate_miss": sum(1 for x in breaches if x.get("gate_bug_kind") == "gate_miss"),
                       "rule_drift": sum(1 for x in breaches if x.get("gate_bug_kind") == "rule_drift"),
                       "at_risk": len(at_risk)},
            "breaches": breaches,
            "at_risk": at_risk,
            "policy": {
                "deadline_warn_hours": round(float(self._hr_warn_hours() or 0.0), 2),
                "seed_margin_hours": round(float(self._hr_margin_hours() or 0.0), 2),
                "rule": "at_risk = 种还在 qB、未达标、距站点考核窗口到期 ≤ warn 小时数（预警≠违约）",
                "gate_bug_kind": "gate_miss=删除时账单已在册（闸门当班漏判）；rule_drift=删除早于开账/口径差",
            },
            "source_of_truth": ["mf_bills", "mf_deletions", "_tag_all_torrents()"],
            "write": {
                "reseed": "GET /tags?action=hr_reconcile&site=<dom>&confirm=1",
                "rescue": "POST /plugin/MagicFlow/rescue?confirm=1",
                "void": "GET /tags?action=hrbills_void&hash=<h>&reason=..&confirm=1",
                "breach_reconcile": "GET /tags?action=breach_reconcile&confirm=1（站点不欠→自动清账 / 站点欠→自动补种）",
            },
        }

    # ---------------------------------------------------------- 违约自动核对（11.12.0）
    def _hrbills_breach_reconcile(self, site: str = "", confirm: bool = False,
                                  reports: Any = None) -> Dict[str, Any]:
        """★ 11.12.0 违约自动核对：对每张 breached 账单拉站点真值 → **站点不欠→清账 / 站点欠→补种**。

        Master 2026-10-06：「消违约也是正常动作」/「站点不欠自动清账、站点欠自动补种」——把
        「逐笔人工核对」变成周期性自动动作。

        真值源：站点 ``myhr.php``（经 ``_hr_reconcile_site``，可传 ``reports`` 复用本轮报告
        避免重复联网）+ ``hr_bills.json``。判定依据链（逐张账单）：
          ① 站点报告 ``ok`` 且覆盖完整（否则 **fail-closed**：不验证、不动）；
          ② 逐张走 ``_hr_site_verdict``（**与结清闸门同一口径**）：
             - ``owed``  → 站端明确还欠 → ``_hr_reconcile_apply`` 重下补种；
             - ``clear`` → 拿到证据（单颗正向证据 / 页头计数双源为 0 且新鲜）→ 作废；
             - ``unknown`` → **保留**（站端判不明就不动）。

        ★ 19.12.42（Master 2026-11-05）：**旧口径是「hash 不在欠列表 → 站点已不欠 → 作废」**，
        等于把「没看见」当成「不存在」——一次登录页/改版/分页截断就能把 breached 批量清掉，
        而且绕开了结清闸门的页头计数校验。现在两条路共用 ``_hr_index_*`` + ``_hr_site_verdict``。
        作废时把证据摘要写进审计事件（``_hr_void_audit``）；★ 19.12.43 起账单行本身
        **保留为 void 墓碑**（``voided_at`` / ``void_reason`` 可回查，回填不会重开）。

        ``confirm=False``（默认）只出计划不落库；``confirm=True`` 真写（作废 + 重下）。
        """
        store = self._hrbills_store()
        now = time.time()
        dom_filter = self._hrbills_norm_domain(site) if site else ""
        by_site: Dict[str, List[str]] = {}
        for h, b in (store.all() or {}).items():
            if not isinstance(b, dict):
                continue
            if str(b.get("state") or "") != BILL_STATE_BREACHED:
                continue
            dom = self._hrbills_norm_domain(str(b.get("site") or ""))
            if not dom:
                continue
            if dom_filter and dom != dom_filter:
                continue
            by_site.setdefault(dom, []).append(str(h).strip().lower())
        rep_map: Dict[str, Any] = {}
        try:
            for _r in (reports or []):
                if isinstance(_r, dict) and _r.get("site"):
                    rep_map[self._hrbills_norm_domain(str(_r.get("site")))] = _r
        except Exception:  # noqa: BLE001
            rep_map = {}
        # 缺报告的站再拉一次（只读）；失败就是 unknown，**绝不**当「站点不欠」
        for dom in list(by_site.keys()):
            if isinstance(rep_map.get(dom), dict):
                continue
            try:
                rep_map[dom] = self._hr_reconcile_site(dom)
            except Exception as e:  # noqa: BLE001
                rep_map[dom] = {"site": dom, "ok": False, "error": str(e)}
        # ★ 19.12.42：与结清闸门**同一套折叠**（页头计数双源 + 证据新鲜度 + 单颗正向证据）。
        #   此前这里自己写了一遍「hash 不在欠列表 → 站点已不欠 → 作废」，绕开了闸门。
        idx = self._hr_index_new(now)
        for dom, rep in rep_map.items():
            self._hr_index_add_report(idx, dom, rep, now)
        self._hr_index_finish(idx)

        out_sites: List[Dict[str, Any]] = []
        voided: List[str] = []
        reseeded = 0
        unverified = 0
        for dom, hashes in by_site.items():
            rep = rep_map.get(dom) or {}
            gate = self._hr_gate_state(dom, idx)
            if not rep.get("ok") or not rep.get("hash_coverage_complete"):
                unverified += len(hashes)
                out_sites.append({"site": dom, "breached": len(hashes), "verified": False,
                                  "error": str(rep.get("error")
                                               or "站点对账覆盖不完整（fail-closed）"),
                                  "will_void": [], "will_reseed": [], "gate": gate,
                                  "audit": [{"hash": h, "verdict": "unknown",
                                             "why": "report_unusable"} for h in hashes]})
                continue
            owed: List[str] = []
            will_void: List[str] = []
            audit: List[Dict[str, Any]] = []
            for h in hashes:
                try:
                    verdict, left = self._hr_site_verdict(h, dom, now=now, idx=idx)
                except Exception:  # noqa: BLE001
                    verdict, left = "unknown", 0.0
                audit.append({
                    "hash": h, "verdict": verdict,
                    "left_h": round(float(left or 0.0) / 3600.0, 2) if left else 0.0,
                    "why": "" if verdict != "unknown" else str(gate.get("why") or ""),
                })
                if verdict == "clear":
                    will_void.append(h)
                elif verdict == "owed":
                    owed.append(h)
                else:
                    unverified += 1
            will_reseed = list(owed)
            if confirm and will_void:
                for h in will_void:
                    try:
                        if _void_ok(self._hrbills_void(h, "site_no_longer_owed", evidence={
                                "via": "breach_reconcile", "site": dom,
                                "gate": gate, "audit": [a for a in audit if a["hash"] == h],
                        })):
                            voided.append(h)
                    except Exception:  # noqa: BLE001
                        pass
            if confirm and will_reseed:
                try:
                    _want = set(will_reseed)
                    tids = [str(r.get("tid")) for r in (rep.get("records") or [])
                            if r.get("tid") and not r.get("in_qb")
                            and str(r.get("infohash") or "").strip().lower() in _want]
                    _out = self._hr_reconcile_apply(dom, tids=tids, confirm=True)
                    reseeded += int(_out.get("added") or 0)
                except Exception:  # noqa: BLE001
                    pass
            out_sites.append({"site": dom, "breached": len(hashes), "verified": True,
                              "will_void": will_void, "will_reseed": will_reseed,
                              "gate": gate, "audit": audit})
        return {
            "ok": True, "dry_run": not confirm,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"), "sites": out_sites,
            "totals": {
                "sites": len(out_sites),
                "breached": sum(len(v) for v in by_site.values()),
                "will_void": sum(len(s["will_void"]) for s in out_sites if s.get("verified")),
                "will_reseed": sum(len(s["will_reseed"]) for s in out_sites if s.get("verified")),
                "unverified": unverified,
                "voided": len(voided), "reseeded": reseeded,
            },
            "source_of_truth": ["hr_bills.json", "站点 myhr.php(经 _hr_reconcile_site)",
                                "index.php 页头 H&R 计数", "_tag_all_torrents()"],
            "write": {"run": "GET /tags?action=breach_reconcile&confirm=1"},
        }

    # ---------------------------------------------------------- 人工作废（11.7.0）
    def _hr_void_audit(self, hs: str, row: Dict[str, Any], reason: str,
                       evidence: Any = None) -> None:
        """作废审计：账单行删了也要留下「谁·何时·凭什么」。**只写事件日志，不落新表**。

        证据里只允许放判定元数据（站点/结论/门槛快照/页头计数），**不放** cookie、UA、
        页面正文或任何可识别用户的内容。
        """
        try:
            _ev = evidence if isinstance(evidence, dict) else {}
            _g = _ev.get("gate") if isinstance(_ev.get("gate"), dict) else {}
            _txt = ("%s · 站端：%s · 页头 %s（total=%s, age=%sh）"
                    % (str(reason or "manual")[:40], str(_ev.get("via") or "-"),
                       ("known" if _g.get("bar_known") else "unknown"),
                       _g.get("bar_total"), _g.get("bar_age_h")))
            self._emit_event(
                "hr", action="H&R 账单作废", level="info",
                reason=_txt[:300],
                metrics={
                    "count": 1, "hash": str(hs or "")[:64],
                    "site": str(row.get("site") or "")[:64],
                    "bill_state": str(row.get("state") or ""),
                    "rule": str(row.get("rule") or "")[:24],
                    "reason": str(reason or "manual")[:40],
                    "need_h": row.get("need_h"), "seeded_h": row.get("seeded_h"),
                    # ★ 19.12.46（任务 89）：作废时把**原始结清审计**一并写进事件，
                    #   保证「人工作废一张人工结清账」之后，历史结论仍可追溯。
                    "settlement_method": row.get("settlement_method"),
                    "settled_by": row.get("settled_by"),
                    "settled_at": row.get("settled_at"),
                    "evidence": _ev,
                },
            )
        except Exception:  # noqa: BLE001
            pass

    def _hrbills_void(self, hash_string: str, reason: str = "",
                      evidence: Any = None,
                      manual_override: Any = None) -> Optional[Dict[str, Any]]:
        """作废一张账单（摘保护）：站点侧**免罪/确认无 H&R**、或对账拿到「不欠」证据后的落账口子。

        ``reason`` 举例：``pardoned`` / ``resolved_no_hr`` / ``site_no_longer_owed`` / ``manual``。

        ★ 19.12.43（Master 2026-11-05 拍板）：**留 void 墓碑，不再「作废即删」**。
        旧口径（2026-10-11「作废就删了」）删行 + tick 每轮 ``drop_void()`` 兜底，代价是
        **作废不生效**：``_hrbills_backfill`` 的幂等判据就是 ``store.get(h)`` 是否存在，
        行一删，下一轮回填会把同一颗种按当前规则重新开成 active —— 人工作废被静默推翻，
        而且账本里查不到「曾经作废过」。

        现在：行保留、``state=void`` + ``voided_at`` / ``void_reason``，
        tick 遇 void 直接跳过（不结清、不重开、不销账），回填与开账都会被这一行挡住。
        副作用边界：``void`` 在展示口径里一律「不算欠」（``hr.py`` 释放闸、
        ``reportview`` 的 owed 计数、``yema`` 审计都按这个口径），所以墓碑不会让卡片多欠。
        审计事件照旧写（``_hr_void_audit``）—— 墓碑记状态，事件记「谁·何时·凭什么」。

        ★ 19.12.46（任务 89 · 人工结清保护闭环）：本函数是 **breach_reconcile /
        purge_unknown / purge_missing / void_reuse / 人工作废** 五条路径的共同汇合点。
        对 ``settlement_method == "manual"`` 的账单**默认拒绝**（返回
        ``{"error": "manual_protected"}``）—— 自动清理不承担人工撤销职责。
        合法的撤销必须走**显式人工作废旁路**：``manual_override`` 传
        ``{"authorization": MANUAL_VOID_SCOPE, "authorized_by": 操作人, "reason": 纠错原因}``
        三件套（见 ``_manual_void_override_ok``）。行上的原始结清审计
        （``settled_by`` / ``settlement_reason`` / ``settled_at``）**原样保留**
        （patch 不碰这三列），审计事件另记一条「人工作废」，不覆盖历史。

        幂等：不存在 / 已是 void → ``None``。
        """
        hs = str(hash_string or "").strip().lower()
        if not hs:
            return None
        store = self._hrbills_store()
        cur = store.get(hs)
        if not cur:
            return None
        if str(cur.get("state") or "") == BILL_STATE_VOID:
            return None  # 已作废：墓碑已在，不重复写、不重复审计
        _ov: Dict[str, Any] = {}
        if _is_manual_settled(cur):
            _ov = _manual_void_override_ok(manual_override)
            if not _ov:
                return {"error": "manual_protected",
                        "message": ("该账单是人工结清结论，自动作废已拦截；"
                                    "确需撤销请走人工作废（需授权 + 操作人 + 纠错原因）"),
                        "hash": hs, "state": cur.get("state"),
                        "settlement_method": HR_MANUAL_SETTLE}
            reason = _ov["reason"]
        now = time.time()
        row = {"site": cur.get("site"), "state": cur.get("state"), "rule": cur.get("rule"),
               "need_h": cur.get("need_h"), "seeded_h": cur.get("seeded_h"),
               # ★ 19.12.46：把结清审计一起带进作废事件，行被 void 后仍可追溯「原本谁结清的」
               "settlement_method": cur.get("settlement_method"),
               "settled_by": cur.get("settled_by"),
               "settled_at": cur.get("settled_at")}
        # ★ 任务 98：作废同样留 append-only 事件；`bill_snapshot` 保留被作废前
        #   的结清四列（任务 89 只能把它们塞进热层事件 metrics，重启/300 条后即丢）。
        _vev_type = EVT_MANUAL_VOID if _ov else EVT_AUTO_VOID
        _vev = self._hr_bill_event(
            hs, _vev_type, cur, at=now,
            actor=(str(_ov.get("authorized_by") or "") if _ov else EVT_SYSTEM_ACTOR),
            reason=str(reason or "manual")[:300],
            prev_state=str(cur.get("state") or ""), new_state=BILL_STATE_VOID,
            evidence_source=("manual_void" if _ov else "tick_void"))
        _vres = self._hrbills_cas(store, hs, self._hrbills_guard(cur), save=True,
                                  events=[_vev],
                                  state=BILL_STATE_VOID, voided_at=now,
                                  void_reason=str(reason or "manual")[:60],
                                  settle_block=None)
        if not _vres.get("ok"):
            # ★ 19.12.47（任务 91）：读→写之间被人改过（多半是刚落下的人工结清/已 void）。
            #   **不覆盖、不重试**：作废是不可逆动作，拿新状态自动重来等于替人做决定。
            #   ``_void_ok`` 对 error dict 返回 False → 5 条调用方都按「没作废」处理。
            _vrow = _vres.get("row")
            if not isinstance(_vrow, dict):
                _vrow = cur if isinstance(cur, dict) else {}
            return {"error": "concurrent_modified",
                    "message": ("账单在读与写之间被修改（%s），本次作废已放弃；复核后重试"
                                % (_vres.get("reason") or "conflict")),
                    "hash": hs, "reason_code": _vres.get("reason") or "conflict",
                    "state": _vrow.get("state"),
                    "settlement_method": _vrow.get("settlement_method")}
        if _ov:
            _ev = dict(evidence) if isinstance(evidence, dict) else {}
            _ev["manual_override"] = {"authorization": _ov["authorization"],
                                      "authorized_by": _ov["authorized_by"],
                                      "reason": _ov["reason"]}
            evidence = _ev
        self._hr_void_audit(hs, row, reason, evidence)
        out: Dict[str, Any] = {"voided": hs, "state": BILL_STATE_VOID, "voided_at": now,
                               "reason": str(reason or "manual")[:60],
                               "prev_state": row["state"]}
        if _ov:
            out["manual_override"] = _ov
        return out

    # ★ 19.12.44：人工结清（自动处理 + 人工兜底）
    def _hrbills_settle_manual(self, hash_string: str, reason: str = "",
                               settled_by: str = "") -> Optional[Dict[str, Any]]:
        """人工结清一张 H&R 账单：自动任务无法判断/自动结清的长期滞留账单，由人工核实后结清。

        判定规则（★ 19.12.44，★ 19.12.46 收紧操作人）：
          · 必须填写 ``reason``（结清原因）——空原因拒绝；
          · 必须提供 ``settled_by``（操作人）——缺失 / 空串 / 纯空白一律拒绝，
            **不再用占位串 "manual" 兜底**（那会让审计看起来完整、实际无人可追）；
          · ``state=void``（墓碑）→ 拒绝（void 是终态）；
          · 已 ``settled`` + ``settlement_method="manual"`` → **幂等返回**（不重复审计）；
          · 已 ``settled`` + auto → 允许覆盖为 manual（人工确认接管）。

        持久化：``settlement_method="manual"`` + ``settled_by`` + ``settlement_reason``
        + ``settled_at=now``。P1 闸门（tick 重开/TTL 删除/unknown 降级）对
        ``settlement_method="manual"`` 一律跳过——人工结清不被自动任务覆盖。

        幂等：重复调用同一 hash → 返回 ``already=True``，不重复写、不重复审计。
        并发（★ 19.12.47 / 任务 91）：写入走 ``patch_if``（CAS，期望值 = 本次读到的
        ``state`` + ``settlement_method``）—— 读与写之间被改过 → **重读重判**（最多
        2 次），仍冲突则返回 ``concurrent_modified``，绝不覆盖、绝不复活 void 墓碑。
        PG 后端下这是**存储层**原子条件更新，跨进程/跨实例同样成立。
        """
        hs = str(hash_string or "").strip().lower()
        if not hs:
            return None
        _reason = str(reason or "").strip()
        if not _reason:
            return {"error": "missing_reason", "message": "人工结清必须填写原因（reason）"}
        store = self._hrbills_store()
        # ★ 19.12.47（任务 91）：**带 CAS 的重读重判**。
        #   读与写之间若被别的写入插进来（tick 自动结清 / 作废落墓碑），旧实现会用
        #   ``patch`` 无条件覆盖 —— 最严重的是把 void 墓碑**复活**成 settled。现在：
        #   冲突 → **重读最新账单重新走一遍判定**（最多 2 次），仍冲突则明确失败。
        #   成功路径的行为、返回字段、错误码与 19.12.46 完全一致。
        _by = str(settled_by or "").strip()[:64]
        cur: Any = None
        cur_state = ""
        now = 0.0
        _ok_write = False
        _last_reason = ""
        for _attempt in (1, 2):
            cur = store.get(hs)
            if not cur:
                return {"error": "not_found", "message": "账单不存在"}
            cur_state = str(cur.get("state") or "")
            if cur_state == BILL_STATE_VOID:
                return {"error": "void_terminal",
                        "message": "void 墓碑是终态，不能人工结清"}
            if cur_state == BILL_STATE_SETTLED and cur.get("settlement_method") == "manual":
                return {"settled": hs, "already": True, "state": BILL_STATE_SETTLED,
                        "settled_at": cur.get("settled_at"),
                        "settled_by": cur.get("settled_by"),
                        "settlement_reason": cur.get("settlement_reason")}
            now = time.time()
            # ★ 19.12.46（任务 89）：操作人硬校验 —— 空白不落到 "manual" 占位值。
            #   放在幂等判断之后：重复结清同一张 manual 账时无需再带操作人（保持幂等语义）。
            if not _by:
                return {"error": "missing_settled_by",
                        "message": "人工结清必须提供操作人（不能为空或纯空白）"}
            # ★ 任务 98：人工结清事件与状态变更在同一次 CAS 里落盘（同锁 / 同事务）。
            #   `bill_snapshot` 保存结清前的账单（含上一次纠错重开后的状态），
            #   因此「重开 → 再次人工结清」天然成为第 2 条事件，多次历史完整。
            _mev = self._hr_bill_event(
                hs, EVT_MANUAL_SETTLED, cur, at=now, actor=_by,
                reason=_reason[:300], prev_state=cur_state,
                new_state=BILL_STATE_SETTLED, evidence_source="manual")
            _sres = self._hrbills_cas(store, hs, self._hrbills_guard(cur), save=True,
                                      events=[_mev],
                                      state=BILL_STATE_SETTLED,
                                      settled_at=now,
                                      settlement_method="manual",
                                      settled_by=_by,
                                      settlement_reason=_reason[:200],
                                      settle_block=None)
            if _sres.get("ok"):
                _ok_write = True
                break
            _last_reason = str(_sres.get("reason") or "conflict")
            if _last_reason != "conflict":
                # 存储不可用/异常 → 不能静默当作成功，也不能拿旧状态重试
                return {"error": "store_unavailable",
                        "message": "账单写入失败（%s），本次人工结清未落库" % _last_reason}
        if not _ok_write:
            return {"error": "concurrent_modified",
                    "message": "账单在读写之间被反复修改，本次人工结清已放弃；请复核后重试",
                    "reason_code": _last_reason, "hash": hs}
        row = {"site": cur.get("site"), "state": cur_state, "rule": cur.get("rule"),
               "need_h": cur.get("need_h"), "seeded_h": cur.get("seeded_h")}
        # 审计事件：谁·何时·凭什么结清
        try:
            self._emit_event(
                "hr", action="H&R 账单人工结清", level="info",
                reason="%s · 操作人：%s" % (_reason[:200], _by),
                metrics={
                    "count": 1, "hash": hs[:64],
                    "site": str(row.get("site") or "")[:64],
                    "prev_state": cur_state,
                    "rule": str(row.get("rule") or "")[:24],
                    "need_h": row.get("need_h"), "seeded_h": row.get("seeded_h"),
                    "settlement_method": "manual",
                    "settled_by": _by,
                    "settlement_reason": _reason[:200],
                },
            )
        except Exception:  # noqa: BLE001
            pass
        return {"settled": hs, "state": BILL_STATE_SETTLED, "settled_at": now,
                "settlement_method": "manual", "settled_by": _by,
                "settlement_reason": _reason[:200], "prev_state": cur_state}

    # ---------------------------------------------------------- 存量：辅种账单作废（11.11.1）
    def _hrbills_void_reuse(self, confirm: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 存量：把「active 辅种账单」作废（辅种≠真实下载 → 不该有 H&R 账单）。

        辅种 = 带 ``MARK_REUSE``（魔流-辅种）/ ``RESCUE_TAG``（魔流-补源）标签的种。
        这些种历史上被 ``_hrbills_backfill`` 误开成 active 账单（11.11.0 只跳了跨站、
        没跳辅种）→ 现在把**已在账本里的 active 辅种账单**作废（void_reason="reuse_not_hr"）。

        默认干跑（confirm=False）：只返回待作废清单（供分批核对）；
        confirm=True：逐张 void（幂等；settled/void 不动）。**只作废账单、不删种**。
        """
        store = self._hrbills_store()
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        targets: List[Dict[str, Any]] = []
        kept_manual: List[str] = []
        cap = int(limit or 0)
        _capped = False
        for h, b in (store.all() or {}).items():
            if not isinstance(b, dict):
                continue
            if str(b.get("state") or "") != BILL_STATE_ACTIVE:
                continue  # 只处理 active（欠债中的辅种）；settled/void/pending 不动
            # ★ 19.12.46（任务 89）：防御性 —— 人工结清账（含未来可能的非 settled 形态）
            #   一律不进自动作废清单。
            if _is_manual_settled(b):
                kept_manual.append(str(h or "").strip().lower())
                continue
            hh = str(h or "").strip().lower()
            t = (snap or {}).get(hh)
            if t is None:
                continue  # 种已不在下载器 → 交给 _hrbills_tick 违约/作废，这里不碰
            try:
                _tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            except Exception:  # noqa: BLE001
                _tags = []
            if not is_reuse_copy(_tags):
                continue  # 非辅种 → 不碰（真欠 H&R）
            row = {"hash": hh, "site": str(b.get("site") or ""),
                   "title": str(b.get("title") or "")[:120],
                   "rule": str(b.get("rule") or ""), "need_h": b.get("need_h"),
                   "seeded_h": b.get("seeded_h")}
            targets.append(row)
            if cap and len(targets) >= cap:
                _capped = True
                break
        voided: List[str] = []
        if confirm:
            for row in targets:
                try:
                    if _void_ok(self._hrbills_void(row["hash"], "reuse_not_hr")):
                        voided.append(row["hash"])
                except Exception:  # noqa: BLE001
                    pass
        return {"dry_run": not bool(confirm), "targets": targets,
                "count": len(targets), "limit": cap, "capped": _capped,
                "voided": len(voided),
                "kept_manual": len(kept_manual),
                "void_reason": "reuse_not_hr",
                "note": ("只作废「active 且带 魔流-辅种/魔流-补源」的账单；辅种仍受保护、绝不删种；"
                         "★ 19.12.46：人工结清账永不自动作废（kept_manual 计数）")}

    # ------------------------------------------- 存量：规则未定性账单清理（19.12.33）
    def _hrbills_purge_unknown(self, confirm: bool = False,
                               limit: int = 0) -> Dict[str, Any]:
        """清理**规则未定性**的僵尸账单（``rule`` 既非 site_hr 也非 hit_and_run）。

        背景：19.12.33 起开账/回填只走两道门槛，``rule=unknown`` 不再产生。但存量里
        还有旧口径留下的记录 —— 它们在 tick 里**永不开、永不结清**（只挂 pending），
        卡片却曾把它们算成「还欠」（2026-11-05 线上 YemaPT 22 张）。

        处置：走 ``_hrbills_void``（★ 19.12.43 起**留 void 墓碑**，不再删行）。理由：它们的
        ``rule`` 说明「站点没给规则、逐种站又没标记」= 本就不该有账。**只摘账，不删种**；
        墓碑挡住回填，同一颗种不会再被自动开成账（旧「摘完会按新口径重开」的自愈已取消 ——
        要重开必须人工先 ``drop_void()`` 清墓碑）。

        默认干跑（confirm=False）只列清单。
        """
        store = self._hrbills_store()
        targets: List[Dict[str, Any]] = []
        kept_manual: List[str] = []
        cap = int(limit or 0)
        _capped = False
        for h, b in (store.all() or {}).items():
            if not isinstance(b, dict):
                continue
            if str(b.get("state") or "") == BILL_STATE_VOID:
                continue
            # ★ 19.12.46（任务 89）：人工结清账**不进清理清单** —— 自动清理不承担
            #   人工撤销职责。要让它们消失须走人工作废旁路（授权 + 操作人 + 纠错原因）。
            if _is_manual_settled(b):
                kept_manual.append(str(h or "").strip().lower())
                continue
            if str(b.get("rule") or "") in (RULE_SITE_HR, RULE_HIT_AND_RUN):
                continue
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            targets.append({
                "hash": hh,
                "site": str(b.get("site") or ""),
                "title": str(b.get("title") or "")[:120],
                "rule": str(b.get("rule") or ""),
                "state": str(b.get("state") or ""),
                "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                "need_h": round(float(b.get("need_h") or 0.0), 2),
            })
            if cap and len(targets) >= cap:
                _capped = True
                break
        dropped: List[str] = []
        if confirm:
            for row in targets:
                try:
                    if _void_ok(self._hrbills_void(row["hash"], "legacy_rule_unknown")):
                        dropped.append(row["hash"])
                except Exception:  # noqa: BLE001
                    pass
        return {
            "dry_run": not bool(confirm),
            "targets": targets,
            "count": len(targets),
            "limit": cap,
            "capped": _capped,
            "dropped": len(dropped),
            "kept_manual": len(kept_manual),
            "note": ("只摘「规则未定性」账单（rule 非 site_hr/hit_and_run）；不删种。"
                     "19.12.43 起留 void 墓碑（不再删行），回填不会把同一 hash 重开；"
                     "要重开须先人工清墓碑。★ 19.12.46：人工结清账不进清单（"
                     "kept_manual 计数），撤销须走人工作废旁路。"),
        }

    # ------------------------------------------- 存量：qB 长期缺席的孤儿账单（19.12.40）
    def _hrbills_purge_missing(self, confirm: bool = False,
                               limit: int = 0, min_days: float = 0.0) -> Dict[str, Any]:
        """列出/摘除「qB 里长期找不到、且站端**明确说清**」的孤儿账单。**默认干跑**。

        为什么需要它：19.12.40 起种消失**不再自动删账**（qB 抖动不能当义务消失）。
        代价是真正的孤儿会一直留着 —— 这条给了人工出口，判据仍然保守：

          · 必须 ``alive=False`` 且连续缺席 ≥ ``min_days``（默认走
            ``HR_BILLS_MISSING_TTL_DAYS``）；
          · 站端**明确 owed** 一律不摘（还欠着就不是孤儿）；
          · 站端**判不明（unknown）也一律不摘**（★ 19.12.41：unknown 不是「大概清了」，
            而是「没有证据」。人工 confirm 也不再越过这条 —— 摘账是不可逆的，
            而欠账留在 active 最多多挂一颗种）；
          · 只有站端**明确 clear**（列表 + 页头计数双源一致，见 ``_hr_site_verdict``）
            才进候选，confirm 后才摘。

        只摘账，不删种、不动任何岗位归属。
        """
        store = self._hrbills_store()
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        now = time.time()
        _days = float(min_days or 0) or float(HR_BILLS_MISSING_TTL_DAYS)
        _age_limit = max(0.0, _days) * 86400.0
        idx: Any = None
        try:
            idx = self._hr_site_debt_index(now)
        except Exception:  # noqa: BLE001
            idx = None
        targets: List[Dict[str, Any]] = []
        kept_unknown: List[str] = []
        kept_manual: List[str] = []
        cap = int(limit or 0)
        capped = False
        for h, b in (store.all() or {}).items():
            if not isinstance(b, dict):
                continue
            hh = str(h or "").strip().lower()
            if not hh or hh in snap:
                continue
            if str(b.get("state") or "") == BILL_STATE_VOID:
                continue        # ★ 19.12.43：已作废（墓碑）→ 不在「待摘」清单里重复出现
            # ★ 19.12.46（任务 89）：人工结清账不进「待摘」清单（site 说 clear 也不行）。
            if _is_manual_settled(b):
                kept_manual.append(hh)
                continue
            if b.get("alive") is not False:
                continue
            _ms = float(b.get("missing_since") or 0) or 0.0
            if not _ms or now - _ms < _age_limit:
                continue
            _v = "unknown"
            if idx is not None and str(b.get("rule") or "") in (RULE_SITE_HR, RULE_HIT_AND_RUN):
                try:
                    _v = self._hr_site_verdict(hh, str(b.get("site") or ""), now, idx)[0]
                except Exception:  # noqa: BLE001
                    _v = "unknown"
            if _v == "owed":
                continue        # 站端还欠 → 不是孤儿
            if _v != "clear":
                # ★ 19.12.41：站端判不明 → **保留**（不再是「人工 confirm 就能摘」）。
                kept_unknown.append(hh)
                continue
            targets.append({
                "hash": hh, "site": str(b.get("site") or ""),
                "title": str(b.get("title") or "")[:120],
                "state": str(b.get("state") or ""),
                "missing_days": round((now - _ms) / 86400.0, 1),
                "site_verdict": _v,
                "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                "need_h": round(float(b.get("need_h") or 0.0), 2),
            })
            if cap and len(targets) >= cap:
                capped = True
                break
        dropped: List[str] = []
        if confirm:
            for row in targets:
                try:
                    if _void_ok(self._hrbills_void(row["hash"], "missing_too_long")):
                        dropped.append(row["hash"])
                except Exception:  # noqa: BLE001
                    pass
        return {
            "dry_run": not bool(confirm), "targets": targets, "count": len(targets),
            "limit": cap, "capped": capped, "min_days": _days, "dropped": len(dropped),
            "site_unknown": sum(1 for r in targets if r.get("site_verdict") == "unknown"),
            "kept_unknown": len(kept_unknown),
            "kept_manual": len(kept_manual),
            "note": ("只摘「qB 长期缺席 + 站端**明确说清**」的孤儿账；站端还欠或判不明的一律不摘；"
                     "19.12.43 起留 void 墓碑（rows 可查，回填不会重开）；"
                     "★ 19.12.46：人工结清账一律不摘（kept_manual 计数）；"
                     "不删种、不动归属。默认干跑，confirm=1 才写。"),
        }

    # ------------------------------------------------- H&R 盲区（旁路加种）
    def _hr_blindspot_scan(self, limit: int = 50) -> Dict[str, Any]:
        """★ H&R 盲区扫描（**纯只读**）：来自「明确有 H&R」的站、但**既无账单、也无魔流标签**的种。

        背景（踩过，2026-10-05）：走 **MP 下载接口等旁路**加进来的种不经过插件下载
        路径，不会自动开账（手动补源从 ``pt.btschool.club``（hr=true/20h）拉了一单 →
        造出一笔**账本里看不见**的 H&R 欠账）。本扫描只报不改，让「欠 H&R 却没记账」
        可见（UI/CLI 无入口，AI 入口 ``GET /agent/blindspot``）。

        判定（不造第二真值源）：
          ① 遍历下载器快照 ``_tag_all_torrents()``；
          ② 带任何「魔流」标签 → 已纳管（走账本路径），跳过；
          ③ 站点域名 = tracker 主机名（回退 ``_hr_domain`` 标签推断）；
          ④ ``_site_hr_flag(dom) is not True`` → 跳过（未知站不制造噪音）；
          ⑤ ``_hrbills_store().get(hash)`` 已有账单 → 已纳管，跳过。
        """
        items: List[Dict[str, Any]] = []
        scanned_hr = 0
        try:
            torrents = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            torrents = {}
        try:
            store = self._hrbills_store()
        except Exception:  # noqa: BLE001
            store = None
        for h, t in (torrents or {}).items():
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            try:
                tags = [str(x) for x in (getattr(t, "tags", None) or [])]
            except Exception:  # noqa: BLE001
                tags = []
            if any("魔流" in x for x in tags):
                continue  # 已纳管（插件自己下载/托管 → 账单路径已覆盖）
            dom = ""
            try:
                tr = str(getattr(t, "tracker", "") or "").strip().lower()
            except Exception:  # noqa: BLE001
                tr = ""
            if tr:
                dom = tr.split("://")[-1].split("/")[0].split(":")[0].strip()
            if not dom:
                try:  # 标签推断（魔流-<站点>-…）
                    dom = str(self._hr_domain("", t) or "").strip().lower()
                except Exception:  # noqa: BLE001
                    dom = ""
            if not dom:
                continue
            try:
                flag = self._site_hr_flag(dom)
            except Exception:  # noqa: BLE001
                flag = None
            if flag is not True:
                continue  # 只报「明确有 H&R」，未知站不制造噪音
            scanned_hr += 1
            try:
                if store is not None and store.get(hh):
                    continue  # 已有账单 → 已纳管
            except Exception:  # noqa: BLE001
                pass
            try:
                prog = float(getattr(t, "progress", 0.0) or 0.0)
            except Exception:  # noqa: BLE001
                prog = 0.0
            items.append({
                "hash": hh,
                "title": str(getattr(t, "title", "") or "")[:120],
                "site": dom,
                "hr": True,
                "state": str(getattr(t, "state", "") or ""),
                "progress": round(prog, 4),
                "size_gb": round(float(getattr(t, "size", 0) or 0) / (1024 ** 3), 2),
                "tags": tags,
                "reason": "站点有 H&R 但账本无账单、且无魔流标签（很可能是旁路加种）",
                "action_hint": "打魔流标签纳管（下一轮 backfill 开账）或手动核对该站 H&R 规则",
            })
        return {
            "count": len(items),
            "scanned_hr": scanned_hr,
            "total_torrents": len(torrents or {}),
            "limit": int(limit),
            "items": items[:int(limit)],
            "reason_chain": [{
                "rule": "hrbills/blindspot",
                "verdict": "report",
                "inputs": {"scanned_hr": scanned_hr, "total": len(torrents or {})},
                "source_of_truth": "_tag_all_torrents() + _site_hr_flag() + hr_bills.json",
                "at": time.time(),
            }],
        }


# ============================================================================
# 19.10.34：站点 myhr 对账（``HrReconcileMixin``）+ 对账缓存（``HrReconcileCache``）
#   已迁到 ``features/hrreconcile.py`` —— 本文件只剩**账单状态机**
#   （开账 / 作废 / 结清 / 违约判定 / 回填），改账本口径就只看这里。
#   两边的唯一连接点是 ``self._hr_reconcile_*``（运行时 self 调用，无模块级反向 import）。
# ============================================================================
