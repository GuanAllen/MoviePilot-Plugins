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
"""

import html
import json
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..crossseed import CROSSSEED_TAG
from ..tags import MARK_REUSE, RESCUE_TAG, is_reuse_copy
from ..fingerprint import fingerprint, info_hash
from ..downloader_ops import seed_hours_for_hr
from ..persistence import _shared
from ..common import (
    HR_DEADLINE_WARN_HOURS_DEFAULT,
    HR_SEED_MARGIN_HOURS_DEFAULT,
)

# ★ 11.0.0 第二阶段：账单接入保护。
#   一键回退：把本常量改回 ``False`` 即恢复「不接保护」（账单照记、回填照跑，只是
#   ``_hr_obligation`` 不再读账单 → 自下载种回到「仅资源级/种子级」判定）。
HR_BILLS_ENFORCE = True

# 连续多少天进度无增长 → 作废（死账）
HR_BILLS_STALL_DAYS = 7.0

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
HR_RECONCILE_MAX_PAGES = 6
HR_RECONCILE_BACKOFF_HOURS = (6.0, 12.0, 24.0)
HR_RECONCILE_TIME_BUDGET = 240.0
HR_RECONCILE_TAG_SUFFIX = "补种"

# 账单状态全集
BILL_STATE_ACTIVE = "active"
BILL_STATE_PENDING = "pending"
BILL_STATE_SETTLED = "settled"
BILL_STATE_VOID = "void"
BILL_STATE_BREACHED = "breached"  # ★ 11.11.0：欠 H&R 的种消失（违约/待处理）——不是 void，保护不解除

# 账单规则来源
RULE_HIT_AND_RUN = "hit_and_run"
RULE_SITE_HR = "site_hr"
RULE_UNKNOWN = "unknown"

# ★ 11.11.1：站点「实际做种达标小时」的保守兜底（站点规则 seed_need_hours 取不到时）。
#   与 common.CROSSSEED_SEED_HOURS_DEFAULT 同值；不引 common（其拉进 MP 依赖，会破坏离线测试）。
HR_NEED_HOURS_DEFAULT = 24.0

# ★ 11.11.1：辅种（复用/跨站/补源）都不是「本账单口径的真实下载」→ 开账/回填一律跳过。
#   - MARK_REUSE(魔流-辅种)：复用副本（add_torrent_reuse，paused+recheck）→ 无真实下载。
#   - CROSSSEED_TAG(魔流-跨站)：跨站来源份，H&R 由 assets.py 资源账记（不走本账单）。
#   - RESCUE_TAG(魔流-补源)：死种补源副本，来源站被 rescue_source_blocked 保证 hr=False。
#   MP 写的「已整理/辅种」(ASSET_TAGS) 是**真实下载被整理**，仍欠 H&R → 不跳过。
_SKIP_BILL_TAGS = (CROSSSEED_TAG, MARK_REUSE, RESCUE_TAG)


def _skip_hr_bill(tags: Any) -> bool:
    """该种是否**不该**在本账单口径开账（跨站/复用/补源副本）。"""
    return any(str(x).strip() in _SKIP_BILL_TAGS for x in (tags or []))


class HrBillsStore:
    """纯数据存储：``hash -> 账单 dict``。零业务逻辑。

    持久化：``hr_bills.json``（原子写 tmp→rename）；``save()`` 节流（热层即时、
    文件至少间隔 ``FILE_MIN_INTERVAL`` 秒）；``load()`` 容错（坏文件 → 空）。
    """

    kv_region = "hrbills"
    FILE_MIN_INTERVAL = 5.0

    def __init__(self, data_dir: Path, kv: Any = None):
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "hr_bills.json"
        self.bills: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._last_file_write = 0.0
        self._pending = False
        self._dirty: Set[str] = set()   # ★ 脏键集合：save/flush 只写变化的键（避免 O(N) 全量热层写）
        self.kv = kv
        self.load()

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

    def _write_file(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(self.file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.bills, f, ensure_ascii=False, indent=2)
            tmp.replace(self.file)
        except Exception:  # noqa: BLE001
            pass

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

    def save(self, force: bool = False) -> None:
        """保存：热层（**只写脏键**）+ 文件节流（``force`` 立即落盘）。"""
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
                self._write_file()
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
            if save:
                self.save()
            return b

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self.bills)

    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"total": 0, "by_state": {}, "by_rule": {}, "by_site": {},
                              "no_site": 0, "opened_by": {}}
        with self._lock:
            for b in self.bills.values():
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


def get_hr_bills_store(data_dir: Path, kv: Any = None) -> HrBillsStore:
    """取/建**进程级** H&R 账单存储（按 data_dir 单例，跨热重载存活）。

    ★ 照 ``persistence.get_gate_store`` 一模一样：用同一套 ``_shared()`` 注册表
    单独持有实例，热重载后仍指向同一对象；**不挂 ``MagicFlowStore``**（其是进程级
    单例，热重载不重建 → 新字段/新方法拿不到）。
    """
    key = f"hrbills:{Path(data_dir)}"
    sh = _shared()
    with sh.lock:
        store = sh.singletons.get(key)
        # ★ 热重载后：模块里是**新类**，而单例还可能是**旧类的实例** → 方法过时/缺失
        #   （实测踩过：`stats()` 新增字段在 reload 后仍不出现）。校验类型，不匹配就重建
        #   （数据从 JSON 冷备恢复；照 `tags.py::_tag_state` 的同款做法）。
        if store is not None and not isinstance(store, HrBillsStore):
            try:
                store.flush()
            except Exception:  # noqa: BLE001
                pass
            store = None
        if store is None:
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
            state in (BILL_STATE_ACTIVE, BILL_STATE_PENDING)
            and (seeded_h + 1e-9) < due_h
            and hours_left <= self._hr_warn_hours()
        )
        return out

    def _hrbills_store(self) -> HrBillsStore:
        try:
            data_dir = self.get_data_path()
        except Exception:  # noqa: BLE001
            data_dir = Path(".")
        try:
            kv = getattr(self, "_hot", None)
        except Exception:  # noqa: BLE001
            kv = None
        return get_hr_bills_store(Path(data_dir), kv=kv)

    def _hrbills_title(self, hash_string: str) -> str:
        try:
            t = (self._tag_all_torrents() or {}).get(str(hash_string).strip().lower())
            return str(getattr(t, "title", "") or "") if t is not None else ""
        except Exception:  # noqa: BLE001
            return ""

    # ---------------------------------------------------------- 开账
    def _hrbills_open(self, hash_string: str, site_domain: str, tag: str,
                      content: Any, hit_and_run: bool = False) -> Optional[Dict[str, Any]]:
        """下载成功后开一张 H&R 账单（影子记账）。

        跳过：crossseed 自己记账（tag 含 ``CROSSSEED_TAG``）；同 hash 已存在不重复开。
        规则判定：``_site_hr_flag(dom) is True`` → ``site_hr``；种子 ``hit_and_run`` →
        ``hit_and_run``；两者皆无 → ``unknown``（pending，不保护不罚）。

        11.7.0：``hit_and_run`` 由**下载调用点**从候选带入（qB 侧无此信息）；为兼容旧调用，
        未传时回退读 qB 快照的 ``TorrentInfo.hit_and_run``（历史上恒 False）。
        回滚开关 ``HR_PER_TORRENT=False`` → 忽略逐种标记，退回只认站点规则。
        """
        hs = str(hash_string or "").strip().lower()
        if not hs:
            return None
        # ★ 11.11.1：辅种（跨站/复用/补源副本）不是本账单口径的真实下载 → 不开账。
        if _skip_hr_bill([str(tag or "")]):
            return None
        store = self._hrbills_store()
        _existing = store.get(hs)
        if _existing:
            return _existing  # 已存在 → 不重复开（幂等）
        dom = self._hrbills_norm_domain(site_domain)
        # 规则判定：站点规则库明确 True / 种子自带 H&R 标记；否则 unknown（不猜）
        rule = RULE_UNKNOWN
        try:
            site_hr = self._site_hr_flag(dom) if dom else None
        except Exception:  # noqa: BLE001
            site_hr = None
        thr = None
        # ★ 11.7.0：逐种标记优先取「钩子传入」（下载瞬间最准），没传（旧路径）才回退 qB 快照。
        if HR_PER_TORRENT:
            thr = True if bool(hit_and_run) else None
        if thr is None:
            try:
                t = (self._tag_all_torrents() or {}).get(hs)
                thr = bool(getattr(t, "hit_and_run", False)) if t is not None else None
            except Exception:  # noqa: BLE001
                thr = None
        if site_hr is True:
            rule = RULE_SITE_HR
        elif thr is True:
            rule = RULE_HIT_AND_RUN
        state = BILL_STATE_ACTIVE if rule != RULE_UNKNOWN else BILL_STATE_PENDING
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
            rec = rec or {}
            dom = self._hrbills_resolve_domain(rec, t, groups)
            # 规则判定：站点规则明确 True / 种子自带 H&R 标记；否则 unknown（不猜）
            rule = RULE_UNKNOWN
            try:
                site_hr = self._site_hr_flag(dom) if dom else None
            except Exception:  # noqa: BLE001
                site_hr = None
            try:
                thr = bool(getattr(t, "hit_and_run", False))
            except Exception:  # noqa: BLE001
                thr = False
            if site_hr is True:
                rule = RULE_SITE_HR
            elif thr is True:
                rule = RULE_HIT_AND_RUN
            state = BILL_STATE_ACTIVE if rule != RULE_UNKNOWN else BILL_STATE_PENDING
            if not dom:
                no_site += 1
            need_h = self._hr_need_hours(dom)
            try:
                progress = float(getattr(t, "progress", 0) or 0)
            except (TypeError, ValueError):
                progress = 0.0
            try:
                seeded_h = seed_hours_for_hr(t)
            except Exception:  # noqa: BLE001
                seeded_h = 0.0
            bill = {
                "site": dom,
                "rule": rule,
                "state": state,
                "need_h": float(need_h),
                "seeded_h": seeded_h,
                "fp": "",
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
        ① ``progress >= 0.999`` → active；
        ② 连续 ``HR_BILLS_STALL_DAYS`` 天进度无增长 → void；
        ③ 种子在下载器消失且从未完成 → 立即 void；
        ④ ``seeded_h >= need_h`` → settled。
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
                    "breached": 0, "backfilled": backfilled, "no_site": no_site}
        now = time.time()
        activated = voided = settled = breached = 0
        for h, b in list(bills.items()):
            if not isinstance(b, dict):
                continue
            t = (snap or {}).get(h)
            if t is None:
                # ③ 消失：拆两路（Master 2026-10-06 08:24）
                completed = (float(b.get("progress") or 0) >= 0.999
                             or float(b.get("last_progress") or 0) >= 0.999)
                cur_state = str(b.get("state") or "")
                if not completed and cur_state not in (BILL_STATE_VOID, BILL_STATE_BREACHED):
                    # 从未完成（无 H&R 义务）→ 立即作废（无害）
                    store.patch(h, save=False, state=BILL_STATE_VOID,
                                void_reason="disappeared_uncompleted", voided_at=now)
                    voided += 1
                elif cur_state == BILL_STATE_ACTIVE:
                    # 有 active 账单（欠 H&R）→ 违约：转 breached（不 void，保护不解除）
                    store.patch(h, save=False, state=BILL_STATE_BREACHED, breached_at=now)
                    breached += 1
                continue
            try:
                progress = float(getattr(t, "progress", 0) or 0)
            except (TypeError, ValueError):
                progress = float(b.get("progress") or 0)
            try:
                seeded_h = seed_hours_for_hr(t)
            except Exception:  # noqa: BLE001
                seeded_h = float(b.get("seeded_h") or 0)
            cur_state = str(b.get("state") or "")
            fields: Dict[str, Any] = {"progress": progress, "seeded_h": seeded_h}
            # ★ 种重新出现（breached → 恢复 active，复欠重进继续挂）
            if cur_state == BILL_STATE_BREACHED:
                fields["state"] = BILL_STATE_ACTIVE
                fields["breached_at"] = None
                activated += 1
            if progress >= 0.999:
                # ① 完成 → active
                if cur_state == BILL_STATE_PENDING:
                    fields["state"] = BILL_STATE_ACTIVE
                    activated += 1
                # ④ 挂够 → settled（★ 11.13.0：达到线额外加冗余安全垫 ``_hr_margin_hours()``）
                need_h = float(b.get("need_h") or 24.0)
                due_h = need_h + self._hr_margin_hours()
                if cur_state not in (BILL_STATE_SETTLED, BILL_STATE_VOID) and seeded_h >= due_h:
                    fields["state"] = BILL_STATE_SETTLED
                    settled += 1
                fields["last_progress"] = progress
                fields["last_progress_at"] = now
            else:
                last = float(b.get("last_progress") or 0)
                last_at = float(b.get("last_progress_at") or 0) or now
                if progress > last + 1e-9:
                    fields["last_progress"] = progress
                    fields["last_progress_at"] = now
                elif now - last_at >= HR_BILLS_STALL_DAYS * 86400.0:
                    # ② 连续 N 天无进度 → 作废
                    if cur_state != BILL_STATE_VOID:
                        fields["state"] = BILL_STATE_VOID
                        fields["void_reason"] = "no_progress_7d"
                        fields["voided_at"] = now
                        voided += 1
            store.patch(h, save=False, **fields)
        store.flush()
        return {"bills": len(bills), "activated": activated, "voided": voided,
                "settled": settled, "breached": breached,
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

        归因：deletions.jsonl（唯一删除台账）命中 `ok=true` → 本插件删（gate bug 升级 critical）；
        否则 → 外部删。只读，不写任何账本/账单。
        """
        store = self._hrbills_store()
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        deleted_ok: Set[str] = set()
        try:
            _path = self._deletions_log_path()
            if _path is not None and _path.exists():
                for _line in _path.read_text(encoding="utf-8").splitlines():
                    _line = _line.strip()
                    if not _line:
                        continue
                    try:
                        _row = json.loads(_line)
                    except Exception:  # noqa: BLE001
                        continue
                    if _row.get("ok") and not _row.get("blocked"):
                        deleted_ok.add(str(_row.get("hash") or "").strip().lower())
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
            breaches.append({
                "hash": hh, "site": str(b.get("site") or ""),
                "title": str(b.get("title") or "")[:120],
                "bill_state": st, "rule": str(b.get("rule") or ""),
                "need_h": round(float(b.get("need_h") or 0.0), 2),
                "seeded_h": round(float(b.get("seeded_h") or 0.0), 2),
                "attribution": attr, "gate_bug": gate_bug,
                "severity": "critical" if gate_bug else "high",
                "breached_at": b.get("breached_at") or 0,
                "rescue_hint": "GET /tags?action=hr_reconcile&site=" + str(b.get("site") or "") + "&confirm=1",
            })
        at_risk = sorted(at_risk, key=lambda x: (x.get("hours_left") if x.get("hours_left") is not None else 1e9))[:50]
        return {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "totals": {"breached": len(breaches),
                       "critical": sum(1 for x in breaches if x.get("gate_bug")),
                       "at_risk": len(at_risk)},
            "breaches": breaches,
            "at_risk": at_risk,
            "policy": {
                "deadline_warn_hours": round(float(self._hr_warn_hours() or 0.0), 2),
                "seed_margin_hours": round(float(self._hr_margin_hours() or 0.0), 2),
                "rule": "at_risk = 种还在 qB、未达标、距站点考核窗口到期 ≤ warn 小时数（预警≠违约）",
            },
            "source_of_truth": ["hr_bills.json", "deletions.jsonl", "_tag_all_torrents()"],
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
          ① 站点对账 ``ok`` 且 ``hash_coverage_complete``（否则 **fail-closed**：不验证、不动）；
          ② 本账单 hash 是否在站点「仍欠」集合（``records[].resolved``）：
             - 在  → 站点仍欠 → 走 ``_hr_reconcile_apply`` 重下补种；
             - 不在 → 站点已不欠 → ``_hrbills_void(reason=site_no_longer_owed)``。

        ``confirm=False``（默认）只出计划不落库；``confirm=True`` 真写（作废 + 重下）。
        """
        store = self._hrbills_store()
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
        out_sites: List[Dict[str, Any]] = []
        voided: List[str] = []
        reseeded = 0
        unverified = 0
        for dom, hashes in by_site.items():
            rep = rep_map.get(dom)
            if rep is None:
                try:
                    rep = self._hr_reconcile_site(dom)
                except Exception as e:  # noqa: BLE001
                    rep = {"site": dom, "ok": False, "error": str(e)}
            if not rep.get("ok") or not rep.get("hash_coverage_complete"):
                unverified += len(hashes)
                out_sites.append({"site": dom, "breached": len(hashes), "verified": False,
                                  "error": str(rep.get("error") or "站点对账覆盖不完整（fail-closed）"),
                                  "will_void": [], "will_reseed": []})
                continue
            owed = {str(r.get("infohash") or "").strip().lower()
                    for r in (rep.get("records") or []) if r.get("resolved")}
            will_void = [h for h in hashes if h not in owed]
            will_reseed = [h for h in hashes if h in owed]
            if confirm and will_void:
                for h in will_void:
                    try:
                        if self._hrbills_void(h, "site_no_longer_owed"):
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
                              "will_void": will_void, "will_reseed": will_reseed})
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
                                "_tag_all_torrents()"],
            "write": {"run": "GET /tags?action=breach_reconcile&confirm=1"},
        }

    # ---------------------------------------------------------- 人工作废（11.7.0）
    def _hrbills_void(self, hash_string: str, reason: str = "") -> Optional[Dict[str, Any]]:
        """人工作废一张账单（摘保护）：站点侧**免罪/确认无 H&R** 后的落账口子。

        ``state=void`` + ``void_reason``（如 ``pardoned`` / ``resolved_no_hr`` / ``manual``）。
        幂等：已是 void 直接返回。回填不会重开（``_hrbills_backfill`` 遇到已有账单即跳过）。
        """
        hs = str(hash_string or "").strip().lower()
        if not hs:
            return None
        store = self._hrbills_store()
        cur = store.get(hs)
        if not cur:
            return None
        if str(cur.get("state") or "") == BILL_STATE_VOID:
            return cur
        return store.patch(hs, state=BILL_STATE_VOID,
                           void_reason=str(reason or "manual")[:60],
                           voided_at=float(time.time()), voided_by="manual")

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
        cap = int(limit or 0)
        _capped = False
        for h, b in (store.all() or {}).items():
            if not isinstance(b, dict):
                continue
            if str(b.get("state") or "") != BILL_STATE_ACTIVE:
                continue  # 只处理 active（欠债中的辅种）；settled/void/pending 不动
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
                    if self._hrbills_void(row["hash"], "reuse_not_hr"):
                        voided.append(row["hash"])
                except Exception:  # noqa: BLE001
                    pass
        return {"dry_run": not bool(confirm), "targets": targets,
                "count": len(targets), "limit": cap, "capped": _capped,
                "voided": len(voided),
                "void_reason": "reuse_not_hr",
                "note": "只作废「active 且带 魔流-辅种/魔流-补源」的账单；辅种仍受保护、绝不删种"}

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

    # ======================================== 11.8.0 站点 myhr 定期对账（第三视角）
    def _hr_reconcile_cache(self) -> "HrReconcileCache":
        """对账缓存（模块级工厂，**绝不挂 MagicFlowStore**：进程级单例热重载不重建）。"""
        try:
            data_dir = self.get_data_path()
        except Exception:  # noqa: BLE001
            data_dir = Path(".")
        try:
            kv = getattr(self, "_hot", None)
        except Exception:  # noqa: BLE001
            kv = None
        return get_hr_reconcile_cache(Path(data_dir), kv=kv)

    def _hr_reconcile_sites(self) -> List[Dict[str, Any]]:
        """对账对象：站点规则里 ``hr is True`` 的站（站点级 H&R）。按 MP 站点 id 去重（含域名别名）。"""
        cands: List[str] = []
        try:
            for row in (self._list_sites() or []):
                d = str((row or {}).get("domain") or "")
                if d:
                    cands.append(d)
        except Exception:  # noqa: BLE001
            pass
        try:
            for dom, rec in dict(self._site_rules().items() or {}).items():
                if (rec or {}).get("hr") is True:
                    cands.append(str(dom))
        except Exception:  # noqa: BLE001
            pass
        out: List[Dict[str, Any]] = []
        seen_dom: Set[str] = set()
        seen_sid: Set[int] = set()
        for dom in cands:
            d = self._hrbills_norm_domain(dom)
            if not d or d in seen_dom:
                continue
            seen_dom.add(d)
            try:
                if self._site_hr_flag(d) is not True:
                    continue
            except Exception:  # noqa: BLE001
                continue
            sid = self._hr_reconcile_site_id(d)
            if sid and sid in seen_sid:
                continue
            if sid:
                seen_sid.add(sid)
            hours = 24.0
            try:
                rec = dict(self._site_rules().get(d) or {})
                hours = float(rec.get("seed_hours") or 24.0)
            except Exception:  # noqa: BLE001
                hours = 24.0
            out.append({"domain": d, "need_h": hours, "site_id": sid})
        return out

    def _hr_reconcile_site_id(self, domain: str) -> int:
        """域名 → MP 站点 id（抓页/取 cookie 用）。找不到返回 0。"""
        d = self._hrbills_norm_domain(domain)
        if not d:
            return 0
        try:
            rows = self._list_sites() or []
        except Exception:  # noqa: BLE001
            rows = []
        for row in rows:
            try:
                rd = self._hrbills_norm_domain((row or {}).get("domain") or "")
            except Exception:  # noqa: BLE001
                rd = ""
            if rd and (rd == d or rd.endswith("." + d) or d.endswith("." + rd)):
                try:
                    return int((row or {}).get("id") or 0)
                except Exception:  # noqa: BLE001
                    return 0
        return 0

    def _hr_reconcile_fetch(self, site_id: int, domain: str,
                            max_pages: int = HR_RECONCILE_MAX_PAGES) -> Dict[str, Any]:
        """抓该站 ``myhr.php``（走采集出口：配额闸门 + PV 熔断 + 页缓存）。**只读**。

        失败语义（pro 定）：**任何一页拿不到 → ``ok=False`` + ``partial=True``**，
        调用方必须**零写入**（绝不从半份数据推「站点说干净」）。
        """
        out: Dict[str, Any] = {"ok": False, "records": [], "pages": [], "partial": False,
                               "error": ""}
        c = None
        try:
            c = self._collect_ref()
        except Exception:  # noqa: BLE001
            c = None
        if c is None:
            out["error"] = "采集模块未就绪"
            return out
        base = f"https://{self._hrbills_norm_domain(domain)}"
        for page in range(0, max(1, int(max_pages))):
            if page and len(out["records"]) < page * 10:
                break  # 上一页明显不满 → 已到末页
            url = f"{base}/myhr.php" + (f"?page={page}" if page else "")
            try:
                if not self._pv_allow(site_id, "hr", want=1):
                    out["partial"] = True
                    out["error"] = "站点 PV 预算不足或被熔断"
                    return out
            except Exception:  # noqa: BLE001
                pass
            try:
                res = c.http.text(int(site_id), url, kind="hr", ttl=HR_RECONCILE_TTL)
            except Exception as e:  # noqa: BLE001
                out["partial"] = True
                out["error"] = f"抓取异常:{e}"
                return out
            try:
                self._pv_spend(int(site_id), "hr", 1)
            except Exception:  # noqa: BLE001
                pass
            if res is None or not bool(getattr(res, "ok", False)):
                out["partial"] = True
                out["error"] = str(getattr(res, "error", "") or "抓取失败")
                return out
            rows = _hr_myhr_parse(str(getattr(res, "text", "") or ""))
            if rows is None:
                out["partial"] = True
                out["error"] = "页面解析失败（布局不兼容？整页跳过）"
                return out
            if not rows:
                break
            out["pages"].append(page)
            out["records"].extend(rows)
        out["ok"] = True
        return out

    def _hr_reconcile_site(self, domain: str, snap: Any = None) -> Dict[str, Any]:
        """单站三方对账（**只读**）：站点欠不欠 × 本机有没有种 × 账本有没有账单。

        产出三桶（**没有 settle 判定**）：
          - ``missing_local``：站点欠、本机没有 → 「需补种」（写动作走 ``confirm=1``）
          - ``present_no_bill``：站点欠、本机有、账本没账单 → 提示回填开账
          - ``safe_rotate_candidate``：本机有、站点未列欠、账本已结清 → 仅**提示**可轮换
            （**仅当本轮 infohash 覆盖完整时**才输出，避免半份数据误判）
        """
        dom = self._hrbills_norm_domain(domain)
        t0 = time.time()
        rep: Dict[str, Any] = {
            "site": dom, "ok": False, "partial": False, "error": "",
            "records_total": 0, "pages_fetched": 0,
            "missing_local": [], "present_no_bill": [], "safe_rotate_candidate": [],
            "cache_hits": 0, "torrents_fetched": 0, "hash_coverage_complete": False,
            "deferred": 0,
            "records": [],
            "took_ms": 0,
        }
        site_id = self._hr_reconcile_site_id(dom)
        if not site_id:
            rep["error"] = "MP 站点表里找不到该域名（无法取 cookie）"
            rep["took_ms"] = int((time.time() - t0) * 1000)
            return rep
        fetched = self._hr_reconcile_fetch(site_id, dom)
        rep["pages_fetched"] = len(fetched.get("pages") or [])
        rep["error"] = str(fetched.get("error") or "")
        rep["partial"] = bool(fetched.get("partial"))
        if not fetched.get("ok"):
            rep["took_ms"] = int((time.time() - t0) * 1000)
            return rep
        records: List[Dict[str, Any]] = list(fetched.get("records") or [])
        rep["records_total"] = len(records)
        if snap is None:
            try:
                snap = self._tag_all_torrents() or {}
            except Exception:  # noqa: BLE001
                snap = {}
        try:
            store = self._hrbills_store()
        except Exception:  # noqa: BLE001
            store = None
        cache = self._hr_reconcile_cache()
        now = time.time()
        # 本机该站的种（hash → TorrentInfo）：域名取 tracker 主机名，回退标签推断
        local: Dict[str, Any] = {}
        for h, t in (snap or {}).items():
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            dt = ""
            try:
                tr = str(getattr(t, "tracker", "") or "").strip().lower()
            except Exception:  # noqa: BLE001
                tr = ""
            if tr:
                dt = tr.split("://")[-1].split("/")[0].split(":")[0].strip()
            if not dt:
                try:
                    dt = self._hrbills_norm_domain(self._hr_domain("", t))
                except Exception:  # noqa: BLE001
                    dt = ""
            if dt and (dt == dom or dt.endswith("." + dom) or dom.endswith("." + dt)):
                local[hh] = t
        # 逐条记录解析 infohash（缓存优先；只对未命中且**粗配不上**的记录拉种）
        fetch_budget = int(HR_RECONCILE_MAX_FETCH)
        rec_hashes: Set[str] = set()
        claimed: Set[str] = set()      # 本机种**一对一**占用（防两个站点行粗配到同一种）
        coverage = True
        deferred = 0
        conn: Dict[str, Any] = {}
        rec_detail: List[Dict[str, Any]] = []   # 逐条明细（供 /agent/site/seeds 等站点级报表）
        for rec in records:
            tid = str(rec.get("tid") or "").strip()
            if not tid:
                coverage = False
                continue
            hit = cache.tid_get(dom, tid)
            if not hit:
                rough = self._hr_reconcile_rough_match(rec, local, claimed)
                if rough:
                    claimed.add(rough)
                    cache.tid_put(dom, tid, str(rough), str(rec.get("title") or ""),
                                  float(rec.get("size_gb") or 0.0), now)
                    hit = str(rough)
                elif fetch_budget > 0:
                    if not conn:
                        try:
                            conn = self._reseed_site_conn(site_id) or {}
                        except Exception:  # noqa: BLE001
                            conn = {}
                    hh = self._hr_reconcile_fetch_hash(site_id, dom, tid, conn)
                    fetch_budget -= 1
                    rep["torrents_fetched"] = int(rep["torrents_fetched"] or 0) + 1
                    if hh:
                        claimed.add(str(hh).strip().lower())
                        cache.tid_put(dom, tid, hh, str(rec.get("title") or ""),
                                      float(rec.get("size_gb") or 0.0), now)
                        hit = str(hh)
                else:
                    coverage = False
                    deferred += 1
            else:
                rep["cache_hits"] = int(rep["cache_hits"] or 0) + 1
                hit = str(hit.get("h") or "")
                if hit:
                    claimed.add(str(hit).strip().lower())
            if not hit:
                coverage = False
                rec_detail.append({
                    "tid": tid, "infohash": "", "title": str(rec.get("title") or "")[:160],
                    "size_gb": round(float(rec.get("size_gb") or 0.0), 3),
                    "need_left": str(rec.get("need_left") or ""),
                    "in_qb": False, "billed": False, "bill_state": "", "bill_rule": "",
                    "resolved": False,
                })
                continue
            rec_hashes.add(str(hit).strip().lower())
            hh = str(hit).strip().lower()
            present = hh in local
            bill = None
            try:
                bill = store.get(hh) if store is not None else None
            except Exception:  # noqa: BLE001
                bill = None
            rec_detail.append({
                "tid": tid, "infohash": hh, "title": str(rec.get("title") or "")[:160],
                "size_gb": round(float(rec.get("size_gb") or 0.0), 3),
                "need_left": str(rec.get("need_left") or ""),
                "in_qb": bool(present), "billed": bool(bill is not None),
                "bill_state": str((bill or {}).get("state") or ""),
                "bill_rule": str((bill or {}).get("rule") or ""),
                "resolved": True,
            })
            if not present:
                rep["missing_local"].append({
                    "tid": tid, "infohash": hh, "title": str(rec.get("title") or "")[:120],
                    "size_gb": float(rec.get("size_gb") or 0.0),
                    "need_h_left": str(rec.get("need_left") or ""),
                    "site": dom,
                    "reason_chain": [{
                        "rule": "hr_reconcile/missing_local", "verdict": "needs_reseed",
                        "inputs": {"tid": tid, "infohash": hh, "in_qb": False},
                        "source_of_truth": f"站点 myhr.php（{dom}） + 下载器快照 + hr_bills.json",
                        "at": now,
                    }],
                })
            elif bill is None:
                rep["present_no_bill"].append({
                    "tid": tid, "infohash": hh, "title": str(rec.get("title") or "")[:120],
                    "site": dom,
                    "action_hint": "打魔流标签后跑 hrbills_tick 回填开账（只增保护）",
                })
        rep["hash_coverage_complete"] = bool(coverage)
        rep["deferred"] = int(deferred)
        rep["records"] = rec_detail
        if coverage:
            for hh, t in local.items():
                if hh in rec_hashes:
                    continue
                bill = None
                try:
                    bill = store.get(hh) if store is not None else None
                except Exception:  # noqa: BLE001
                    bill = None
                st = str((bill or {}).get("state") or "")
                if bill is not None and st in (BILL_STATE_SETTLED, BILL_STATE_VOID):
                    rep["safe_rotate_candidate"].append({
                        "infohash": hh, "title": str(getattr(t, "title", "") or "")[:120],
                        "bill_state": st, "site": dom,
                        "action_hint": "站点未列欠 + 账本已结清 → 可人工考虑轮换（**不自动删**）",
                    })
        try:
            cache.put_report(dom, {k: v for k, v in rep.items() if k != "took_ms"})
            cache.save()
        except Exception:  # noqa: BLE001
            pass
        rep["ok"] = True
        rep["took_ms"] = int((time.time() - t0) * 1000)
        return rep

    @staticmethod
    def _hr_title_tokens(s: Any) -> Set[str]:
        """标题 → 归一化 token 集合（数字/拉丁/汉字；丢掉分隔符与大小写差异）。"""
        t = unicodedata.normalize("NFKC", str(s or "")).lower()
        t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", t)
        return {x for x in t.split() if x}

    @classmethod
    def _hr_reconcile_rough_match(cls, rec: Dict[str, Any], local: Dict[str, Any],
                                  claimed: Optional[Set[str]] = None) -> str:
        """标题 token 粗配（压拉种量）：高分且**唯一**才认 → 返回本机 hash，否则 ``""``（去拉种）。

        ★ 实测：站点标题是**罗马化**（``Zheng Tu 2026 S01 E11-E12 ... -PTerWEB``），
        而 qB 名字常带中文（``征途.Zheng.Tu.2026...``）→ 旧的「前缀相等」命中率 ~0；
        改 **token Jaccard ≥ 0.80（且交集 ≥ 2）且与次优差距 ≥ 0.1**（避免同剧不同集互吃）。
        例：站点 ``The Old Story of Yu Hong 2026 S01 E14-E17 2160p ... PTerWEB`` vs qB
        ``余红旧事.The.Old.Story.of.Yu.Hong.2026.S01.2160p...PTerWEB`` → Jaccard 0.84 → 命中。

        ★ 例外：站点行**不带体积**（myhr 列里的 GB 是上传/下载量，**不是种子体积**）
        → 粗配**不得拿体积当闸门**（旧版因此把 CARPT 全判不中）。
        """
        A = cls._hr_title_tokens(rec.get("title"))
        if not A:
            return ""
        claimed = claimed or set()
        scored: List[Any] = []
        for hh, t in (local or {}).items():
            key = str(hh or "").strip().lower()
            if not key or key in claimed:
                continue
            B = cls._hr_title_tokens(getattr(t, "title", ""))
            if not B:
                continue
            inter = len(A & B)
            if inter < 2:
                continue
            jac = inter / max(1, len(A | B))
            if jac >= 0.5:
                scored.append((jac, key))
        if not scored:
            return ""
        scored.sort(reverse=True)
        top = scored[0]
        if top[0] < 0.80:
            return ""
        if len(scored) > 1 and (top[0] - scored[1][0]) < 0.1:
            return ""          # 同分双胞胎（同剧不同集）→ 不敢认，去拉种
        return top[1]

    def _hr_reconcile_fetch_hash(self, site_id: int, dom: str, tid: str,
                                 conn: Dict[str, Any]) -> str:
        """取该 tid 的 ``.torrent`` 算 infohash（NexusPHP ``download.php?id=`` 唯一可靠路径）。"""
        url = f"https://{dom}/download.php?id={tid}"
        try:
            dl = self._get_downloader("qbittorrent")
        except Exception:  # noqa: BLE001
            dl = None
        if dl is None:
            return ""
        data = None
        try:
            data = dl.fetch_torrent_bytes(url, cookie=(conn or {}).get("cookie"),
                                          user_agent=(conn or {}).get("ua"),
                                          referer=((conn or {}).get("url") or None))
        except Exception:  # noqa: BLE001
            data = None
        finally:
            try:
                self._pv_spend(int(site_id), "hr", 1)
            except Exception:  # noqa: BLE001
                pass
        if not data or data[:1] != b"d":
            return ""
        try:
            return str(info_hash(data) or "").strip().lower()
        except Exception:  # noqa: BLE001
            return ""

    def _hr_reconcile_target_task(self, dom: str) -> Dict[str, Any]:
        """该站对应的任务（取保存目录 + 标签）。找不到 → 空。"""
        try:
            tasks = list((self._task_configs or {}).values())
        except Exception:  # noqa: BLE001
            tasks = []
        for task in tasks:
            cand = ""
            for attr in ("site_domain", "site"):
                try:
                    cand = self._hrbills_norm_domain(getattr(task, attr, "") or "")
                except Exception:  # noqa: BLE001
                    cand = ""
                if cand:
                    break
            if cand and (cand == dom or cand.endswith("." + dom) or dom.endswith("." + cand)):
                return {
                    "task_id": str(getattr(task, "id", "") or ""),
                    "save_path": str(getattr(task, "save_path", "") or ""),
                    "tag": str(getattr(task, "brush_tag", "") or ""),
                    "site_domain": dom,
                }
        return {}

    def _hr_reconcile_add_one(self, dom: str, tid: str, infohash: str = "",
                              save_path: str = "") -> Dict[str, Any]:
        """**同站重下**（写动作，必须由 ``confirm=1`` 显式触发后调用）。

        ★ 与 ``rescue`` 的区别（pro 评审否决了复用 rescue）：rescue 语义是「从**无 H&R
        的他站**补同 Release 来辅」，且 ``rescue_source_blocked`` 对 ``hr=True`` 的站一律
        禁用 —— 拿它补欠债站自己的种，会被自己拦掉。这里是**还自己的债**：从**同一个
        欠债站**按 ``download.php?id=<tid>`` 重下原始种。
        三重保护：① 该 infohash 已在 qB → 不下；② 缓存到 infohash 永久化；③ 只在此函数写。
        """
        dom = self._hrbills_norm_domain(dom)
        tgt = self._hr_reconcile_target_task(dom)
        dest = str(save_path or tgt.get("save_path") or "").strip()
        if not dest:
            return {"tid": tid, "ok": False, "err": "未配置保存目录（避免落到下载器默认目录）"}
        site_id = self._hr_reconcile_site_id(dom)
        if not site_id:
            return {"tid": tid, "ok": False, "err": "MP 站点表里找不到该域名"}
        if infohash:
            try:
                if str(infohash).strip().lower() in (self._tag_all_torrents() or {}):
                    return {"tid": tid, "ok": False, "skipped": "已在下载器",
                            "err": "该 infohash 已在下载器（跳过，避免重复下载）"}
            except Exception:  # noqa: BLE001
                pass
        try:
            conn = self._reseed_site_conn(site_id) or {}
        except Exception:  # noqa: BLE001
            conn = {}
        url = f"https://{dom}/download.php?id={tid}"
        try:
            dl = self._get_downloader("qbittorrent")
        except Exception:  # noqa: BLE001
            dl = None
        if dl is None:
            return {"tid": tid, "ok": False, "err": "下载器不可用"}
        data = None
        try:
            data = dl.fetch_torrent_bytes(url, cookie=conn.get("cookie"),
                                          user_agent=conn.get("ua"),
                                          referer=(conn.get("url") or None))
        except Exception as e:  # noqa: BLE001
            data = None
            return {"tid": tid, "ok": False, "err": f"取种失败:{e}"}
        finally:
            try:
                self._pv_spend(site_id, "hr", 1)
            except Exception:  # noqa: BLE001
                pass
        if not data or data[:1] != b"d":
            return {"tid": tid, "ok": False, "err": "取到的不是种子（站点拒绝 / 需登录 / PV 拦截）"}
        try:
            nh = str(info_hash(data) or "").strip().lower()
        except Exception:  # noqa: BLE001
            nh = ""
        if not nh:
            return {"tid": tid, "ok": False, "err": "算不出 infohash（种子损坏？）"}
        if nh in (self._tag_all_torrents() or {}):
            return {"tid": tid, "ok": False, "new_hash": nh, "skipped": "已在下载器"}
        tag = str(tgt.get("tag") or "") or f"魔流-{dom.split('.')[0]}-{HR_RECONCILE_TAG_SUFFIX}"
        try:
            got, err = dl.add_torrent(content=data, download_dir=dest, tag=tag,
                                      site_domain=dom)
        except Exception as e:  # noqa: BLE001
            return {"tid": tid, "ok": False, "err": str(e)}
        if not got:
            return {"tid": tid, "ok": False, "err": str(err or "添加失败")}
        try:
            cache = self._hr_reconcile_cache()
            cache.tid_put(dom, str(tid), str(got), "", 0.0, time.time())
            cache.save()
        except Exception:  # noqa: BLE001
            pass
        self._hr_reconcile_journal(dom, str(tid), str(got))
        self._log(f"站点对账:按站点 myhr 从 {dom} 重下欠 H&R 种 tid={tid}（{str(got)[:12]}…）")
        return {"tid": tid, "ok": True, "new_hash": str(got), "tag": tag, "save_path": dest}

    def _hr_reconcile_journal(self, dom: str, tid: str, new_hash: str) -> None:
        """对账重下台账（journal kind=hr_reconcile；写失败静默）。"""
        try:
            journal = getattr(getattr(self, "_store", None), "journal", None)
            fn = getattr(journal, "record", None) if journal is not None else None
            if not callable(fn):
                return
            from ..persistence import OperationItem  # noqa: WPS433
            fn(task_id="", kind="hr_reconcile", items=[OperationItem(
                hash=str(new_hash), title=f"站点对账重下 {dom} tid={tid}",
                reason=f"站点 myhr 显示欠 H&R、本机没有种 → 同站重下（{str(new_hash)[:12]}…）",
                size_gb=0.0, source="hr_reconcile")])
        except Exception:  # noqa: BLE001
            pass

    def _hr_reconcile_round(self, force: bool = False) -> Dict[str, Any]:
        """一轮站点对账（**只读 + 只回填提示**；**不**自动重下、**不**改任何账单状态）。

        写动作（重下）只在 ``?action=hr_reconcile&confirm=1`` 里逐条发生。
        """
        if not HR_RECONCILE_ENABLED and not force:
            return {"enabled": False, "reason": "HR_RECONCILE_ENABLED=False"}
        cache = self._hr_reconcile_cache()
        now = time.time()
        try:
            last = float(cache.last_run_ts() or 0.0)
        except Exception:  # noqa: BLE001
            last = 0.0
        if not force and (now - last) < float(HR_RECONCILE_HOURS) * 3600.0:
            return {"enabled": True, "skipped": "interval", "last_run_ts": last}
        reports: List[Dict[str, Any]] = []
        deadline = now + float(HR_RECONCILE_TIME_BUDGET)
        for s in self._hr_reconcile_sites():
            dom = str(s.get("domain") or "")
            if not force:
                try:
                    if not cache.site_due(dom, time.time()):
                        continue
                except Exception:  # noqa: BLE001
                    pass
            if time.time() > deadline:
                reports.append({"site": dom, "ok": False, "error": "本轮时间预算用尽，下轮继续"})
                break
            try:
                rep = self._hr_reconcile_site(dom)
            except Exception as e:  # noqa: BLE001
                rep = {"site": dom, "ok": False, "error": str(e)}
            try:
                cache.note_result(dom, bool(rep.get("ok")), time.time(),
                                  int(rep.get("fail_count") or 0) + (0 if rep.get("ok") else 1))
            except Exception:  # noqa: BLE001
                pass
            reports.append(rep)
        if reports:
            try:
                cache.set_last_run(time.time())
            except Exception:  # noqa: BLE001
                pass
        try:
            cache.flush()
        except Exception:  # noqa: BLE001
            pass
        summary = {"enabled": True, "sites": len(reports), "reports": reports,
                   "missing_total": sum(len(r.get("missing_local") or []) for r in reports),
                   "at": time.time()}
        try:
            _miss = int(summary["missing_total"] or 0)
            if _miss:
                self._log(f"站点 H&R 对账:{summary['sites']} 站 · **{_miss} 条「站点说欠、本机没有」**"
                          f"（需人工确认后重下；只报不动）", "warning")
        except Exception:  # noqa: BLE001
            pass
        return summary

    def _hr_reconcile_report(self, site: str = "") -> Dict[str, Any]:
        """读上一次对账结果（**默认不联网**，秒回）；``live`` 由 AI 端点显式要求。"""
        cache = self._hr_reconcile_cache()
        dom = self._hrbills_norm_domain(site)
        try:
            if dom:
                rep = cache.get_report(dom)
                if not rep:
                    return {"enabled": bool(HR_RECONCILE_ENABLED), "site": dom,
                            "ok": False, "error": "该站还没有对账结果（先跑一轮）",
                            "sites": [], "write": {"run_now": "GET /agent/hr/reconcile?live=1"}}
                return {"enabled": bool(HR_RECONCILE_ENABLED), "site": dom, "ok": True,
                        "report": rep, "last_run_ts": cache.last_run_ts()}
            return {"enabled": bool(HR_RECONCILE_ENABLED),
                    "sites": cache.reports(), "last_run_ts": cache.last_run_ts(),
                    "interval_hours": float(HR_RECONCILE_HOURS),
                    "site_status": cache.site_status()}
        except Exception as e:  # noqa: BLE001
            return {"enabled": bool(HR_RECONCILE_ENABLED), "ok": False, "error": str(e)}

    def _hr_reconcile_apply(self, site: str, tids: Any = None,
                            confirm: Any = None, save_path: str = "") -> Dict[str, Any]:
        """按站点 myhr 的「需补种」清单重下（**默认干跑**；真写必须 ``confirm=1``）。

        只处理**站点当前确实还欠**且**本机没有**的记录（重跑一次实时对账取准），
        逐条走 ``_hr_reconcile_add_one``（同站重下）。**只加不删**。
        """
        dom = self._hrbills_norm_domain(site)
        if not dom:
            return {"ok": False, "error": "缺少 site（域名）"}
        try:
            want = {str(t).strip() for t in (tids if isinstance(tids, (list, tuple, set))
                                             else str(tids or "").split(",")) if str(t).strip()}
        except Exception:  # noqa: BLE001
            want = set()
        rep = self._hr_reconcile_site(dom)
        if not rep.get("ok"):
            return {"ok": False, "error": rep.get("error") or "对账失败", "site": dom}
        pool = [r for r in (rep.get("missing_local") or [])
                if not want or str(r.get("tid")) in want]
        dry = not bool(confirm)
        plan: List[Dict[str, Any]] = []
        results: List[Dict[str, Any]] = []
        for r in pool:
            if dry:
                plan.append({"tid": r.get("tid"), "action": "add", "dry": True,
                             "title": r.get("title"), "size_gb": r.get("size_gb"),
                             "need_h_left": r.get("need_h_left")})
                continue
            res = self._hr_reconcile_add_one(dom, str(r.get("tid") or ""),
                                             str(r.get("infohash") or ""), save_path=save_path)
            results.append(res)
            plan.append({"tid": r.get("tid"), "action": "add", "ok": bool(res.get("ok")),
                         "new_hash": res.get("new_hash") or "", "err": res.get("err") or ""})
        out = {"ok": True, "dry_run": dry, "site": dom, "candidates": len(pool),
               "plan": plan}
        if not dry:
            out["results"] = results
            out["added"] = sum(1 for r in results if r.get("ok"))
        else:
            out["would_add"] = len(plan)
        return out


# ============================================================================
# ★ 11.8.0 模块级：站点 ``myhr.php`` 解析器 + 对账缓存（**不挂 MagicFlowStore**）
# ============================================================================

_HR_SIZE_RE = re.compile(r"([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)", re.I)
# ★ 11.9.2："还需做种时间"列有两种渲染 —— 剩余 ≥1h 为 ``H:MM:SS``/``HH:MM:SS``，
#   剩余 <1h 为 ``MM:SS``（实测 CARPT：如 ``48:00``）。旧正则只认三段
#   ``H:MM:SS`` → 把 <1h 的行判成「布局不兼容」→ 整站 ``myhr`` 对账整页跳过。
#   放宽为「可选第三段」，两种都收。
_HR_NEED_RE = re.compile(r"^(\d+):([0-5]\d)(?::([0-5]\d))?$")
_HR_TID_RE = re.compile(r"details\.php\?id=(\d+)", re.I)
_HR_ID_RE = re.compile(r"<td[^>]*>\s*(\d{5,})\s*</td>", re.I)
_HR_MARKERS = ("myhr", "h&r", "hit and run", "hit-and-run", "details.php", "hr.php")



def _hr_cell_text(cell: str) -> str:
    """单元格 → 纯文本（去标签 + 还原实体 + 压缩空白）。"""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(cell or "")))).strip()


def _hr_row_segments(raw: str) -> Any:
    """定位 H&R 表并切出行（兼容嵌套表 / 行内嵌套 ``<table>``）。

    ★ 为什么不用「按 ``<tr>`` 嵌套层级切」：NexusPHP 把内容表嵌套在版式表的 ``<tr>``
    里 → 顶层行只剩少数几个，真正数据行全被包住。
    ★ 为什么不用「以链接为锚向前后找 <tr></tr>」：行内可能有多个 ``details.php?id=``
    链接（头像/用户名/引用）→ 会产生错行（实测 btschool 多出 tid=<uid> 的假行）。
    做法：**以表头行（含「还需做种时间」）为分界**，之后的 ``<tr>`` 按 ``</tr>`` 切开；
    只有同时拿到「还需做种时间」单元格 + ``details.php?id=`` 链接 + ≥ 3 个 ``<td>``
    的行才算数据行（其余表不会同时满足）。

    Returns:
        ``(rows, candidates)``：``candidates`` = 「看着像数据行但可能没解出来」的候选数
        （≥3 个 ``<td>`` + 标题链接）；两者不等 → 布局不兼容 → 调用方按不可识别处理。
    """
    raw = str(raw or "")
    m = re.search(r"<tr[^>]*>(?:(?!</tr>).)*还需做种时间(?:(?!</tr>).)*</tr>", raw, re.S)
    start = m.end() if m else 0
    rows: List[str] = []
    candidates = 0
    for seg in raw[start:].split("</tr>"):
        if "details.php?id=" not in seg:
            continue
        if len(re.findall(r"<td", seg, re.I)) < 3:
            continue
        candidates += 1
        cells = [_hr_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", seg, re.S | re.I)]
        if not any(_HR_NEED_RE.match(c) for c in cells):
            continue
        rows.append(seg)
    return rows, candidates


def _hr_myhr_parse(text: str) -> Optional[List[Dict[str, Any]]]:
    """NexusPHP ``myhr.php`` 页 → 记录列表（**保守解析**）。

    ★ 语义（实测 CARPT / btschool）：行首 id = H&R 记录 id（CARPT）/ 种子 id（btschool）；
    真种子 id 在行内 ``details.php?id=<tid>``。列序（实测）：
    ``上传量 | 下载量 | 分享率 | 还需做种时间 | 下载完成时间 | 剩余考察时间 | 操作``。

    ★★ 两个已踩的坑（11.8.1 修）：
      1. 页面头部（用户名 / 新人考核公告）也含 ``details.php?id=<uid>`` 链接 → 必须靠
         「还需做种时间」单元格把这类噪声行剔掉，否则产生**假记录**（还会白拉 .torrent）；
      2. 行内有嵌套 ``<table>`` 时，``<tr[^>]*>(.*?)</tr>`` 非贪婪会**重复匹配**同一行
         （实测 CARPT 22 行 → 51 条）→ 改为按 ``</tr>`` 切分 + 取最近的 ``<tr`` + 按 tid 去重。

    Returns:
        ``None`` = **页面不可识别**（布局不兼容 / 登录页）→ 调用方整页跳过并退避；
        ``[]``   = 页面可识别但**无未完成记录**（= 无欠）；
        列表     = 逐条 ``{hr_id, tid, title, up_gb, down_gb, size_gb, need_left,
                   done_at, keep_left, ratio}`；``size_gb`` 是**站点口径的下载量**
                   （非种子体积，保留旧字段兼容）。
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    low = raw.lower()
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    has_header = ("还需做种时间" in raw) or ("下载完成时间" in raw) or ("hr-table" in low)
    segs, candidates = _hr_row_segments(raw)
    for seg in segs:
        if "details.php?id=" not in seg:
            continue
        mtid = _HR_TID_RE.search(seg)
        # ★ 取**最长锚文本**的链接 = 标题链接（行内可能有其他 link）
        best_id = ""
        best_txt = ""
        for ma in re.finditer(r"<a[^>]*details\.php\?id=(\d+)[^>]*>(.*?)</a>", seg, re.S | re.I):
            txt = _hr_cell_text(ma.group(2))
            if len(txt) >= len(best_txt):
                best_txt, best_id = txt, ma.group(1)
        if not best_id and mtid:
            best_id = mtid.group(1)
        if not best_id:
            continue
        tid = best_id
        if tid in seen:
            continue
        cells = [_hr_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", seg, re.S | re.I)]
        need = ""
        for c in cells:
            if _HR_NEED_RE.match(c):
                need = c
                break
        if not need:
            continue          # 头部/公告/导航行 → 丢弃（不是 H&R 记录）
        seen.add(tid)
        mid = _HR_ID_RE.search(seg)
        hr_id = mid.group(1) if mid else ""
        title = best_txt
        if not title:
            mtitle = re.search(r"details\.php\?id=\d+['\"][^>]*>(.*?)</a>", seg, re.S | re.I)
            if mtitle:
                title = _hr_cell_text(mtitle.group(1))
        if not title:
            title = re.sub(r"<[^>]+>", " ", seg).strip()[:120]
        up_gb = down_gb = 0.0
        ratio = done_at = keep_left = ""
        n_size = 0
        for c in cells:
            msz = _HR_SIZE_RE.fullmatch(c)
            if msz:
                n_size += 1
                try:
                    v = float(msz.group(1))
                    unit = msz.group(2).lower()
                    if unit.startswith("t"):
                        v *= 1024.0
                    elif unit.startswith("m"):
                        v /= 1024.0
                    elif unit.startswith("k"):
                        v /= (1024.0 * 1024.0)
                except Exception:  # noqa: BLE001
                    v = 0.0
                if n_size == 1:
                    up_gb = round(v, 3)
                elif n_size == 2:
                    down_gb = round(v, 3)
                continue
            if not ratio and n_size >= 1 and re.fullmatch(r"\d+(?:\.\d+)?", c):
                ratio = c
                continue
            if not done_at and re.match(r"\d{4}-\d{2}-\d{2}", c):
                done_at = c
                continue
            if not keep_left and re.fullmatch(r"\d+\s*天\s*\d{1,2}:\d{2}:\d{2}", c):
                keep_left = c
        rows.append({"hr_id": hr_id, "tid": tid, "title": title[:120],
                     "up_gb": up_gb, "down_gb": down_gb,
                     "size_gb": down_gb or up_gb,
                     "ratio": ratio, "need_left": need,
                     "done_at": done_at, "keep_left": keep_left})
    if candidates > len(rows):
        # ★ 守门：表区里还有「像数据行但没解出来」的候选（如标题被套在子表里）
        #   → 布局不兼容；宁可整页跳过（退避）也**绝不**当「无欠」。
        return None
    if rows:
        return rows
    if has_header:
        return []       # 表头在但无数据行（含全部已达标的情况）→ 无欠
    if any(mk in low for mk in _HR_MARKERS):
        return []   # 可识别但无记录（= 无欠）
    return None     # 不可识别 → 不当作「无欠」


class HrReconcileCache:
    """对账缓存（**派生数据，不是真值源**）：``tid→infohash`` 索引 + 每站退避 + 上次报告。

    持久化 ``hr_reconcile.json``（原子写 tmp→rename）；**绝不挂 ``MagicFlowStore``**
    （进程级单例热重载不重建）。tid→infohash 对同一种子近似不可变 → 主策略**永久缓存**
    （按 ``seen_at`` 90 天修剪防无界膨胀）。
    """

    kv_region = "hrreconcile"
    FILE_MIN_INTERVAL = 5.0
    TID_TTL_DAYS = 90.0

    def __init__(self, data_dir: Path, kv: Any = None):
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "hr_reconcile.json"
        self.data: Dict[str, Any] = {"meta": {}, "sites": {}, "tid_index": {}, "reports": {}}
        self._lock = threading.RLock()
        self._last_file_write = 0.0
        self._pending = False
        self.kv = kv
        self.load()

    def kv_bind(self, kv: Any) -> None:
        self.kv = kv

    # ------------------------------------------------------------ 载入 / 落盘
    def load(self) -> None:
        try:
            if self.file.exists():
                with open(self.file, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if isinstance(data, dict):
                    base = {"meta": {}, "sites": {}, "tid_index": {}, "reports": {}}
                    for k in base:
                        v = data.get(k)
                        if isinstance(v, dict):
                            base[k] = v
                    self.data = base
        except Exception:  # noqa: BLE001
            self.data = {"meta": {}, "sites": {}, "tid_index": {}, "reports": {}}

    def _write_file(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(self.file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.file)
        except Exception:  # noqa: BLE001
            pass

    def save(self, force: bool = False) -> None:
        with self._lock:
            now = time.time()
            if force or (now - self._last_file_write) >= self.FILE_MIN_INTERVAL:
                self._write_file()
                self._last_file_write = now
                self._pending = False
            else:
                self._pending = True

    def flush(self) -> None:
        with self._lock:
            if self._pending or (time.time() - self._last_file_write) >= self.FILE_MIN_INTERVAL:
                self._write_file()
                self._last_file_write = time.time()
                self._pending = False

    # ------------------------------------------------------------ 运行状态
    def last_run_ts(self) -> float:
        try:
            return float((self.data.get("meta") or {}).get("last_run_ts") or 0.0)
        except Exception:  # noqa: BLE001
            return 0.0

    def set_last_run(self, ts: float) -> None:
        with self._lock:
            self.data.setdefault("meta", {})["last_run_ts"] = float(ts)
            self.save()

    def site_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.data.get("sites") or {})

    def site_due(self, domain: str, now: float) -> bool:
        d = str(domain or "").strip().lower()
        with self._lock:
            st = (self.data.get("sites") or {}).get(d) or {}
        try:
            return now >= float(st.get("next_try_ts") or 0.0)
        except Exception:  # noqa: BLE001
            return True

    def note_result(self, domain: str, ok: bool, now: float, fail_count: int = 0) -> None:
        """记一次结果：成功 → 清退避；失败 → 指数退避（阶梯封顶）。"""
        d = str(domain or "").strip().lower()
        if not d:
            return
        with self._lock:
            st = dict((self.data.get("sites") or {}).get(d) or {})
            if ok:
                st.update({"last_ok_ts": float(now), "fail_count": 0, "next_try_ts": 0.0})
            else:
                fc = max(1, int(fail_count or 1))
                steps = list(HR_RECONCILE_BACKOFF_HOURS) or [6.0]
                backoff = float(steps[min(fc - 1, len(steps) - 1)]) * 3600.0
                st.update({"fail_count": fc, "next_try_ts": float(now) + backoff})
            self.data.setdefault("sites", {})[d] = st
            self.save()

    # ------------------------------------------------------------ tid 索引
    def tid_get(self, domain: str, tid: str) -> Optional[Dict[str, Any]]:
        d = str(domain or "").strip().lower()
        t = str(tid or "").strip()
        with self._lock:
            row = ((self.data.get("tid_index") or {}).get(d) or {}).get(t)
        return dict(row) if isinstance(row, dict) else None

    def tid_put(self, domain: str, tid: str, infohash: str, title: str = "",
                size_gb: float = 0.0, now: float = 0.0) -> None:
        d = str(domain or "").strip().lower()
        t = str(tid or "").strip()
        h = str(infohash or "").strip().lower()
        if not (d and t and h):
            return
        with self._lock:
            idx = self.data.setdefault("tid_index", {}).setdefault(d, {})
            idx[t] = {"h": h, "t": str(title or "")[:120], "s": round(float(size_gb or 0.0), 3),
                      "at": float(now or time.time())}
            self._prune_locked(d)

    def _prune_locked(self, domain: str) -> None:
        """按 ``seen_at`` 修剪（默认 90 天），防索引无界膨胀。"""
        try:
            idx = (self.data.get("tid_index") or {}).get(domain) or {}
            cutoff = time.time() - float(self.TID_TTL_DAYS) * 86400.0
            dead = [k for k, v in idx.items()
                    if isinstance(v, dict) and float(v.get("at") or 0.0) < cutoff]
            for k in dead:
                idx.pop(k, None)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 报告
    def put_report(self, domain: str, report: Dict[str, Any]) -> None:
        d = str(domain or "").strip().lower()
        if not d:
            return
        with self._lock:
            self.data.setdefault("reports", {})[d] = dict(report or {})

    def get_report(self, domain: str) -> Optional[Dict[str, Any]]:
        d = str(domain or "").strip().lower()
        with self._lock:
            rep = (self.data.get("reports") or {}).get(d)
        return dict(rep) if isinstance(rep, dict) else None

    def reports(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.data.get("reports") or {})


def get_hr_reconcile_cache(data_dir: Path, kv: Any = None) -> HrReconcileCache:
    """取/建**进程级**对账缓存（按 data_dir 单例，跨热重载存活）。

    ★ 照 ``get_hr_bills_store`` / ``persistence.get_gate_store`` 一模一样：用同一套
    ``_shared()`` 注册表单独持有实例，热重载后仍指向同一对象（否则新类拿不到旧实例）。
    """
    key = f"hrreconcile:{Path(data_dir)}"
    sh = _shared()
    with sh.lock:
        obj = sh.singletons.get(key)
        if obj is not None and not isinstance(obj, HrReconcileCache):
            try:
                obj.flush()
            except Exception:  # noqa: BLE001
                pass
            obj = None
        if obj is None:
            obj = HrReconcileCache(data_dir, kv=kv)
            sh.singletons[key] = obj
        elif kv is not None:
            try:
                obj.kv_bind(kv)
            except Exception:  # noqa: BLE001
                pass
    return obj
