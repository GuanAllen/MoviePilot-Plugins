# -*- coding: utf-8 -*-
"""魔流 · agentledger —— AI 只读门面 P1.5b（真值源直出 + 报表层首批 + 字段字典）。

承接 ``docs/AGENT-API.md`` §7 的「AI ⊇ 前端」分层：

  - **L1 真值源直出**：``GET /agent/ledger/{table}`` —— 把插件里**任何一张真值表**
    （账本六表 + 运行台账）原样导出，带**列字典**（字段/类型/单位/枚举）+ 分页 + 过滤。
    这是前端基本不给看的那一层（缓存/预算/账单/删除台账/操作日志/保护集/补源记录…）。
  - **L0 字段字典**：``GET /agent/schema`` —— 所有返回类型的字段字典（诚实：写不出的
    字段标 ``"unknown"``，绝不编）。
  - **L3 报表层首批**：``/agent/overview`` / ``/agent/tasks(+/<id>)`` /
    ``/agent/operations`` / ``/agent/pool`` / ``/agent/trend`` / ``/agent/rules`` /
    ``/agent/settings`` / ``/agent/health`` —— **能复用就复用** UI 走的同一内部函数，
    只做信封规整，不复制粘贴业务逻辑。

铁律（承接 agentapi.py）：
  - **纯只读**：不写任何 json / 账本 / 热层 / 下载器，不 protect/delete/add/recheck。
  - **不造第二真值源**：只读 ``_tag_state()`` / ``_tag_groups()`` / ``_hrbills_store()`` /
    ``_store.journal`` / ``_store.task_states`` / ``deletions.jsonl`` / 插件自有库六表，
    绝不自己缓存一份真值。
  - **不泄密**：站点表导出时剥掉 ``credential``（口令/apikey/cookie 密文）。
  - 不 bump 版本、不改决策路径（golden 基线必须不变）。
  - 模块顶层**零相对 import**（db/ledger/sqlalchemy 都在方法内懒 import），
    保证离线（无 sqlalchemy）也能 import 本模块做清单/字段字典校验。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

# 分页默认 / 上限（与 agentapi 同口径）
DEFAULT_LIMIT = 50
MAX_LIMIT = 500

# 合法 hex 长度（同 agentapi）
_HEX = set("0123456789abcdef")

# ---------------------------------------------------------------------------
# 真值表清单（登记制）：账本六表 + 运行台账五表
# ---------------------------------------------------------------------------
# 账本六表（其中 seed/resource 走 ledger 进程级 store；site/identity/task/deck 走插件自有库）
LEDGER_TABLES: Tuple[str, ...] = (
    "site", "resource", "identity", "task", "seed", "deck",
    # 运行台账
    "bills", "deletions", "journal", "protected", "rescue_actions",
)


def _col(name: str, type_: str, unit: str = "", enum: Any = None,
         desc: str = "", nullable: bool = True) -> Dict[str, Any]:
    """构造列字典条目（L0 字段字典的落地）。"""
    c: Dict[str, Any] = {"name": name, "type": type_}
    if unit:
        c["unit"] = unit
    if enum is not None:
        c["enum"] = list(enum)
    if desc:
        c["desc"] = desc
    c["nullable"] = bool(nullable)
    return c


def _columns() -> Dict[str, List[Dict[str, Any]]]:
    """每张真值表的列字典（字段名 + 类型 + 单位 + 枚举 + 可空）。"""
    hex40 = dict(type="hex40", unit="", desc="种子 infohash（小写）", nullable=False)
    return {
        # ---------------------------------------------------------------- 账本六表
        # ★ 12.0.0：列字典与真值源对齐 —— 旧稿列了 7.0.0 已退役的幽灵列
        #   （asset/title/taken_at/lease_until/downloader/reason/ts），它们既不是 DB 列也不在
        #   ``_read_seeds`` 输出里 → 一并删掉；库内资产看 ``in_library``（顺 mf_resource）。
        "seed": [
            _col("hash", "hex40", desc="种子 infohash（小写）", nullable=False),
            _col("site", "string", desc="站点名"),
            _col("state", "enum", enum=["刷流", "魔力", "静默", "推荐", "保种"],
                 desc="职务（由 task_id 推导）"),
            _col("sub", "enum", enum=["新", "资源", "普通"], desc="身份（顺 mf_resource.identity）"),
            _col("task", "string", desc="所属任务名（空=静默不在岗）"),
            _col("taken_by", "string", desc="占用任务 id（空=不在岗）"),
            _col("fp", "string", desc="资源特征码（mf_resource.resource_id）"),
            _col("size_gb", "float", unit="GB", desc="顺资源表"),
            _col("rating", "float", desc="豆瓣评分（顺资源表）"),
            _col("in_library", "bool", desc="库内资产（mf_resource.in_library）"),
            _col("asset_recheck", "string", desc="推荐复核结论 keep/fail（mf_resource）"),
            _col("published_at", "float", unit="s", desc="站点口径发布时间(unix)"),
            _col("identity_at", "float", unit="s", desc="身份定稿时间"),
            _col("miss", "int", desc="巡检连续未命中"),
            _col("updated", "float", unit="s"),
        ],
        "resource": [
            _col("group_id", "string", desc="fp:<资源特征码>", nullable=False),
            _col("size_gb", "float", unit="GB"),
            _col("files_shared", "bool", desc="文件是否多站共享"),
            _col("source_site", "string", desc="来源站"),
            _col("source_hash", "string", desc="来源种 hash"),
            _col("member_count", "int", desc="挂了多少个种子"),
            _col("identity", "enum", enum=["新", "资源", "普通"]),
            _col("hrs", "json", desc="按站分账 H&R 账单"),
            _col("library", "json", desc="库记（入库状态）"),
            _col("asset_recheck", "enum", enum=["keep", "fail"],
                 desc="推荐复核结论（★ 12.0.0 真列 mf_resource.asset_recheck；fail=不再算库内资产）"),
            _col("asset_recheck_at", "float", unit="s", desc="复核时间"),
            _col("rating", "float"),
            _col("created", "float", unit="s"),
            _col("updated", "float", unit="s"),
        ],
        "site": [
            _col("site_id", "int", nullable=False),
            _col("name", "string"),
            _col("domain", "string"),
            _col("hr", "bool", desc="有无 H&R"),
            _col("hr_src", "string", desc="H&R 判定来源（builtin/override/unknown）"),
            _col("seed_hours", "float", unit="h", desc="保种时长"),
            _col("seed_need_hours", "float", unit="h", desc="需保种小时"),
            _col("seed_cap", "int", desc="做种上限"),
            _col("pv_budget", "int", desc="PV 日预算"),
            _col("source", "string", desc="规则来源"),
            _col("confidence", "string"),
            _col("created", "float", unit="s"),
            _col("updated", "float", unit="s"),
        ],
        "identity": [
            _col("code", "string", nullable=False),
            _col("is_asset", "bool", desc="是否合格资源"),
            _col("need_observe", "bool", desc="是否走观察期"),
            _col("can_cleanup", "bool"),
            _col("order", "int"),
            _col("label", "string"),
        ],
        "task": [
            _col("task_id", "string", nullable=False),
            _col("name", "string"),
            _col("site_id", "int"),
            _col("task_type", "enum", enum=["bonus", "brush"]),
            _col("run_mode", "enum", enum=["running", "seeding", "stopped"]),
            _col("enabled", "bool"),
            _col("downloader", "string"),
            _col("brush_tag", "string"),
            _col("save_path", "string"),
            _col("params", "json", desc="其余任务参数"),
            _col("updated", "float", unit="s"),
        ],
        "deck": [
            _col("deck_id", "string", nullable=False),
            _col("seed_id", "string", desc="牌 = 种子 hash"),
            _col("site_id", "int"),
            _col("task_type_id", "string"),
            _col("task_id", "string"),
            _col("a_contrib", "float", desc="该牌 A 贡献"),
            _col("size_gb", "float", unit="GB"),
            _col("frozen", "bool", desc="满魔冻结"),
            _col("frozen_at", "float", unit="s"),
            _col("created", "float", unit="s"),
            _col("updated", "float", unit="s"),
        ],
        # ---------------------------------------------------------------- 运行台账
        "bills": [
            _col("hash", "hex40", desc="种子 infohash（小写）", nullable=False),
            _col("site", "string"),
            _col("rule", "enum", enum=["site_hr", "hit_and_run", "unknown"]),
            _col("state", "enum", enum=["active", "settled", "pending", "void"]),
            _col("need_h", "float", unit="h"),
            _col("seeded_h", "float", unit="h"),
            _col("fp", "string"),
            _col("title", "string"),
            _col("opened_at", "float", unit="s"),
            _col("opened_by", "enum", enum=["open", "backfill"], desc="开账方式"),
            _col("progress", "float"),
            _col("last_progress", "float"),
            _col("last_progress_at", "float", unit="s"),
        ],
        "deletions": [
            _col("ts", "string", desc="YYYY-MM-DD HH:MM:SS", nullable=False),
            _col("hash", "hex40", nullable=False),
            _col("site", "string"),
            _col("title", "string"),
            _col("source", "string", desc="删除来源（模块.函数）"),
            _col("reason", "string"),
            _col("delete_file", "bool"),
            _col("ok", "bool"),
            _col("blocked", "bool"),
            _col("err", "string"),
            _col("blocked_by", "string", desc="阻断原因分类"),
        ],
        "journal": [
            _col("operation_id", "string", nullable=False),
            _col("request_id", "string"),
            _col("task_id", "string"),
            _col("kind", "string", desc="操作类型（deletion/selection/rescue/tag/…）"),
            _col("state", "enum", enum=["submitting", "accepted", "completed", "failed"]),
            _col("items", "json", desc="操作条目"),
            _col("created_at", "float", unit="s"),
            _col("resolved_at", "float", unit="s"),
            _col("duration", "float", unit="s"),
            _col("error_message", "string"),
        ],
        "protected": [
            _col("hash", "hex40", nullable=False),
            _col("task_id", "string", desc="所属任务（空=历史兼容）"),
            _col("scope", "enum", enum=["manual"], desc="手动保留"),
        ],
        "rescue_actions": [
            _col("operation_id", "string", nullable=False),
            _col("request_id", "string"),
            _col("task_id", "string"),
            _col("kind", "string"),
            _col("state", "string"),
            _col("items", "json", desc="补源记录（hash/title/size_gb/source）"),
            _col("created_at", "float", unit="s"),
            _col("resolved_at", "float", unit="s"),
            _col("duration", "float", unit="s"),
        ],
    }


_COLUMNS: Dict[str, List[Dict[str, Any]]] = _columns()


class AgentLedgerMixin:
    """AI 只读门面 P1.5b：真值源直出（L1）+ 字段字典（L0）+ 报表层首批（L3）。"""

    # ---------------------------------------------------------------- 工具
    @staticmethod
    def _agent_parse_limit(limit: Any) -> Optional[int]:
        """``limit`` → int（``0`` = 全量）；非法 / 负数 → ``None``（bad_param）。"""
        if limit is None or limit == "":
            return DEFAULT_LIMIT
        try:
            n = int(limit)
        except (TypeError, ValueError):
            return None
        if n < 0:
            return None
        return n

    @staticmethod
    def _agent_page(rows: List[Dict[str, Any]], keyfn: Any, limit_int: int,
                    cursor: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """按 keyfn 升序排序 + 游标分页。``limit_int=0`` = 全量。"""
        rows = sorted(rows, key=keyfn)
        cur = str(cursor or "").strip()
        if cur:
            rows = [r for r in rows if keyfn(r) > cur]
        page = rows if limit_int == 0 else rows[:limit_int]
        next_cursor = keyfn(page[-1]) if (limit_int != 0 and len(rows) > limit_int) else None
        return page, next_cursor

    def _agent_columns(self, table: str) -> List[Dict[str, Any]]:
        return list(_COLUMNS.get(table, []))

    # ---------------------------------------------------------------- 真值源读取（纯读）
    def _agent_db_rows(self, model_name: str) -> List[Any]:
        """懒读插件自有库一张表（离线无 sqlalchemy → 静默回空，不阻断）。"""
        try:
            from .. import db as mfdb  # noqa: WPS433
            from sqlalchemy import select  # noqa: WPS433
        except Exception:  # noqa: BLE001
            return []
        model = getattr(mfdb, model_name, None)
        if model is None:
            return []
        try:
            with self.get_database().session() as sess:
                return list(sess.execute(select(model)).scalars().all())
        except Exception:  # noqa: BLE001
            return []

    def _agent_db_site_rows(self) -> List[Dict[str, Any]]:
        """mf_site 行（★ 剥掉 ``credential`` 密文与证据链噪声）。"""
        out: List[Dict[str, Any]] = []
        for r in self._agent_db_rows("SiteRow"):
            out.append({
                "site_id": getattr(r, "site_id", None),
                "name": getattr(r, "name", None),
                "domain": getattr(r, "domain", None),
                "hr": getattr(r, "hr", None),
                "hr_src": getattr(r, "hr_src", None),
                "seed_hours": getattr(r, "seed_hours", None),
                "seed_need_hours": getattr(r, "seed_need_hours", None),
                "seed_cap": getattr(r, "seed_cap", None),
                "pv_budget": getattr(r, "pv_budget", None),
                "source": getattr(r, "source", None),
                "confidence": getattr(r, "confidence", None),
                "created": getattr(r, "created", None),
                "updated": getattr(r, "updated", None),
            })
        return out

    def _agent_db_identity_rows(self) -> List[Dict[str, Any]]:
        """mf_identity 行；空则回退身份枚举真值源（tables.DEFAULT_IDENTITIES）。"""
        out: List[Dict[str, Any]] = []
        for r in self._agent_db_rows("IdentityRow"):
            out.append({
                "code": getattr(r, "code", None),
                "is_asset": getattr(r, "is_asset", None),
                "need_observe": getattr(r, "need_observe", None),
                "can_cleanup": getattr(r, "can_cleanup", None),
                "order": getattr(r, "order", None),
                "label": getattr(r, "label", None),
            })
        if not out:
            try:
                from .. import tables as T  # noqa: WPS433
                out = [dict(x) for x in (getattr(T, "DEFAULT_IDENTITIES", None) or ())]
            except Exception:  # noqa: BLE001
                out = []
        return out

    def _agent_db_task_rows(self) -> List[Dict[str, Any]]:
        """mf_task 行；空则回退运行态任务真值源（``_task_configs``）。"""
        out: List[Dict[str, Any]] = []
        for r in self._agent_db_rows("TaskRow"):
            out.append({
                "task_id": getattr(r, "task_id", None),
                "name": getattr(r, "name", None),
                "site_id": getattr(r, "site_id", None),
                "task_type": getattr(r, "task_type", None),
                "run_mode": getattr(r, "run_mode", None),
                "enabled": getattr(r, "enabled", None),
                "downloader": getattr(r, "downloader", None),
                "brush_tag": getattr(r, "brush_tag", None),
                "save_path": getattr(r, "save_path", None),
                "params": getattr(r, "params", None),
                "updated": getattr(r, "updated", None),
            })
        if not out:
            try:
                cfgs = getattr(self, "_task_configs", None) or {}
                for c in cfgs.values():
                    d = dict(c.to_dict()) if hasattr(c, "to_dict") else dict(getattr(c, "__dict__", {}))
                    d["task_id"] = d.get("id") or d.get("task_id") or ""
                    out.append(d)
            except Exception:  # noqa: BLE001
                out = []
        return out

    def _agent_deletions_rows(self) -> List[Dict[str, Any]]:
        """读 ``deletions.jsonl``（删除唯一入口统一台账，逐行 JSON）。"""
        out: List[Dict[str, Any]] = []
        try:
            store = getattr(self, "_store", None)
            d = getattr(store, "data_dir", None) if store is not None else None
            if d is None:
                try:
                    d = self.get_data_path()
                except Exception:  # noqa: BLE001
                    d = None
            path = (d / "deletions.jsonl") if d is not None else None
            if path is None or not path.exists():
                return out
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        if isinstance(row, dict):
                            out.append(row)
                    except Exception:  # noqa: BLE001
                        continue
        except Exception:  # noqa: BLE001
            pass
        return out

    def _agent_journal_rows(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """读操作日志（journal）；``kind`` 非空则只取该类型（如 ``rescue``）。"""
        out: List[Dict[str, Any]] = []
        try:
            store = getattr(self, "_store", None)
            journal = getattr(store, "journal", None) if store is not None else None
            if journal is None:
                return out
            raw = journal.list_recent(limit=100000)  # journal 有 keep 裁剪，天然有界
        except Exception:  # noqa: BLE001
            return out
        for r in raw:
            d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
            if kind is not None and str(d.get("kind") or "") != kind:
                continue
            out.append(d)
        return out

    def _agent_protected_rows(self) -> List[Dict[str, Any]]:
        """读手动保护集（``task_states.json:protected_torrents``，跨所有任务）。"""
        out: List[Dict[str, Any]] = []
        try:
            store = getattr(self, "_store", None)
            ts = getattr(store, "task_states", None) if store is not None else None
            states = ts.list_all() if ts is not None else []
            for st in states:
                tid = str(getattr(st, "task_id", "") or "")
                for h in (getattr(st, "protected_torrents", None) or set()):
                    out.append({"hash": str(h).strip().lower(), "task_id": tid, "scope": "manual"})
        except Exception:  # noqa: BLE001
            pass
        return out

    def _agent_ledger_rows(self, table: str) -> List[Dict[str, Any]]:
        """读某张真值表全部行（只读，不缓存）。"""
        t = str(table or "").strip().lower()
        try:
            if t == "seed":
                out = []
                for h, r in (self._tag_state().items() or {}).items():
                    if isinstance(r, dict):
                        out.append({"hash": str(h).strip().lower(), **dict(r)})
                return out
            if t == "resource":
                out = []
                for gid, r in (self._tag_groups().items() or {}).items():
                    if not isinstance(r, dict):
                        continue
                    row = {"group_id": str(gid), **dict(r)}
                    members = row.get("members")
                    row["member_count"] = len(members) if isinstance(members, dict) else 0
                    out.append(row)
                return out
            if t == "site":
                return self._agent_db_site_rows()
            if t == "identity":
                return self._agent_db_identity_rows()
            if t == "task":
                return self._agent_db_task_rows()
            if t == "deck":
                try:
                    return self._deck_rows() or []
                except Exception:  # noqa: BLE001
                    return []
            if t == "bills":
                out = []
                for h, b in (self._hrbills_store().all() or {}).items():
                    if isinstance(b, dict):
                        out.append({"hash": str(h).strip().lower(), **dict(b)})
                return out
            if t == "deletions":
                return self._agent_deletions_rows()
            if t == "journal":
                return self._agent_journal_rows()
            if t == "protected":
                return self._agent_protected_rows()
            if t == "rescue_actions":
                return self._agent_journal_rows(kind="rescue")
        except Exception:  # noqa: BLE001
            return []
        return []

    @staticmethod
    def _agent_sort_key(table: str, row: Dict[str, Any]) -> str:
        """每张表的稳定排序键（游标分页依赖字典序）。"""
        t = str(table or "").strip().lower()
        if t == "seed" or t == "bills":
            return str(row.get("hash") or "")
        if t == "resource":
            return str(row.get("group_id") or "")
        if t == "site":
            return str(row.get("domain") or "") + "|" + str(row.get("site_id") or "")
        if t == "identity":
            return str(row.get("code") or "")
        if t == "task":
            return str(row.get("task_id") or row.get("id") or "")
        if t == "deck":
            return str(row.get("deck_id") or "") + "|" + str(row.get("seed_id") or "")
        if t == "deletions":
            return str(row.get("ts") or "") + "|" + str(row.get("hash") or "")
        if t in ("journal", "rescue_actions"):
            return "%020.6f" % float(row.get("created_at") or 0.0) + "|" + str(row.get("operation_id") or "")
        if t == "protected":
            return str(row.get("task_id") or "") + "|" + str(row.get("hash") or "")
        return str(row.get("hash") or row.get("id") or row.get("name") or "")

    @staticmethod
    def _agent_filter_rows(rows: List[Dict[str, Any]], filter_: Any, site: Any,
                           state: Any, rule: Any) -> List[Dict[str, Any]]:
        """表相关过滤：``filter=k=v,k=v`` 或显式 ``site``/``state``/``rule``。"""
        conds: Dict[str, str] = {}
        f = str(filter_ or "").strip()
        if f:
            for part in f.split(","):
                part = part.strip()
                if not part or "=" not in part:
                    continue
                k, _, v = part.partition("=")
                k = k.strip().lower()
                if k:
                    conds[k] = v.strip()
        if site:
            conds["site"] = str(site)
        if state:
            conds["state"] = str(state)
        if rule:
            conds["rule"] = str(rule)
        if not conds:
            return list(rows)
        out: List[Dict[str, Any]] = []
        for r in rows:
            ok = True
            for k, v in conds.items():
                val = str(r.get(k) if r.get(k) is not None else "").strip().lower()
                if val != str(v).strip().lower():
                    ok = False
                    break
            if ok:
                out.append(r)
        return out

    # ---------------------------------------------------------------- L1 真值源直出
    def agent_ledger(self, table: str = "", limit: Any = DEFAULT_LIMIT, cursor: str = "",
                     filter: str = "", fields: str = "", site: str = "", state: str = "",
                     rule: str = "") -> Dict[str, Any]:
        """``GET /agent/ledger/{table}`` —— 真值表原样导出（列字典 + 分页 + 过滤 + 投影）。"""
        t0 = time.time()
        t = str(table or "").strip().lower()
        if t not in LEDGER_TABLES:
            return self._agent_err(
                "not_found", f"未知真值表 {table!r}（可选：{', '.join(LEDGER_TABLES)}）",
                t0, field="table")
        n = self._agent_parse_limit(limit)
        if n is None:
            return self._agent_err("bad_param", "limit 必须是非负整数（0=全量）", t0, field="limit")
        try:
            rows = self._agent_ledger_rows(t)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"读表 {t} 失败:{e}", t0, trace_id=str(e))
        rows = self._agent_filter_rows(rows, filter, site, state, rule)
        total = len(rows)
        keyfn = lambda r: self._agent_sort_key(t, r)  # noqa: E731
        page, next_cursor = self._agent_page(rows, keyfn, n, cursor)
        if fields:
            proj = [p.strip() for p in str(fields).split(",") if p.strip()]
            page = [{k: r.get(k) for k in proj if k in r} for r in page]
        return self._agent_ok({
            "table": t,
            "columns": self._agent_columns(t),
            "rows": page,
            "total": total,
            "next_cursor": next_cursor,
        }, t0)

    # ---------------------------------------------------------------- L0 字段字典
    def agent_schema(self) -> Dict[str, Any]:
        """``GET /agent/schema`` —— 所有返回类型 + 所有真值表的字段字典。"""
        t0 = time.time()
        return self._agent_ok({
            "types": _agent_type_schemas(),
            "tables": {t: self._agent_columns(t) for t in LEDGER_TABLES},
        }, t0)

    # ---------------------------------------------------------------- L3 报表层首批
    def agent_overview(self) -> Dict[str, Any]:
        """``GET /agent/overview`` —— 聚合首页（复用 ``/status`` 内部实现 + AgentState）。"""
        t0 = time.time()
        data: Dict[str, Any] = {}
        try:
            resp = self.get_status()
            data["status"] = getattr(resp, "data", resp) or {}
        except Exception as e:  # noqa: BLE001
            data["status_error"] = str(e)
        try:
            data["state"] = (self.agent_state() or {}).get("data") or {}
        except Exception as e:  # noqa: BLE001
            data["state_error"] = str(e)
        return self._agent_ok(data, t0)

    def agent_tasks(self) -> Dict[str, Any]:
        """``GET /agent/tasks`` —— 任务列表（含 enabled/run_mode/site/统计，复用 UI 同源）。"""
        t0 = time.time()
        try:
            tasks = self._build_task_list() or []
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"任务列表失败:{e}", t0, trace_id=str(e))
        return self._agent_ok({"tasks": tasks, "total": len(tasks)}, t0)

    def agent_task_detail(self, id: str = "") -> Dict[str, Any]:
        """``GET /agent/tasks/{id}`` —— 任务详情（含完整配置）+ 候选/种子/操作记录摘要。"""
        t0 = time.time()
        tid = str(id or "").strip()
        if not tid:
            return self._agent_err("bad_param", "id 路径参数必填", t0, field="id")
        try:
            detail = self._build_task_detail(tid)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"任务详情失败:{e}", t0, trace_id=str(e))
        if not detail:
            return self._agent_err("not_found", "任务不存在", t0)
        data: Dict[str, Any] = {"task": detail}
        try:
            ops = self._store.journal.list_by_task(tid, limit=20) if self._store else []
            data["operations"] = {"items": [r.to_dict() if hasattr(r, "to_dict") else dict(r)
                                          for r in ops], "total": len(ops)}
        except Exception:  # noqa: BLE001
            data["operations"] = {"items": [], "total": 0}
        try:
            stats = self._store.get_task_stats(tid) if self._store else {}
            data["summary"] = {
                "seeding_count": int(stats.get("seeding_count") or 0),
                "candidate_total": int(stats.get("last_candidate_total") or 0),
                "candidate_passed": int(stats.get("last_candidate_passed") or 0),
            }
        except Exception:  # noqa: BLE001
            data["summary"] = {}
        return self._agent_ok(data, t0)

    def agent_operations(self, limit: Any = DEFAULT_LIMIT, cursor: str = "", task: str = "",
                         action: str = "", kind: str = "") -> Dict[str, Any]:
        """``GET /agent/operations`` —— 跨任务操作记录（limit/cursor/task/action 过滤）。"""
        t0 = time.time()
        n = self._agent_parse_limit(limit)
        if n is None:
            return self._agent_err("bad_param", "limit 必须是非负整数（0=全量）", t0, field="limit")
        act = str(action or kind or "").strip()
        try:
            store = getattr(self, "_store", None)
            journal = getattr(store, "journal", None) if store is not None else None
            if journal is None:
                return self._agent_ok({"items": [], "next_cursor": None, "total": 0}, t0)
            raw = journal.list_recent(limit=100000)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"读操作记录失败:{e}", t0, trace_id=str(e))
        rows: List[Dict[str, Any]] = []
        for r in raw:
            d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
            if act and str(d.get("kind") or "") != act:
                continue
            if task and str(d.get("task_id") or "") != str(task):
                continue
            rows.append(d)

        def _key(r: Dict[str, Any]) -> str:
            return "%020.6f" % float(r.get("created_at") or 0.0) + "|" + str(r.get("operation_id") or "")

        page, next_cursor = self._agent_page(rows, _key, n, cursor)
        return self._agent_ok({"items": page, "next_cursor": next_cursor, "total": len(rows)}, t0)

    def agent_pool(self, path: str = "") -> Dict[str, Any]:
        """``GET /agent/pool`` —— 池容积 / 磁盘水位 / 预算（复用 ``/pool`` 内部实现）。"""
        t0 = time.time()
        try:
            resp = self.pool_info(path)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"池查询失败:{e}", t0, trace_id=str(e))
        data = getattr(resp, "data", None)
        if not data:
            msg = str(getattr(resp, "message", "") or "池查询失败")
            return self._agent_err("internal", msg, t0)
        return self._agent_ok(data, t0)

    def agent_trend(self, scope: str = "all", id: str = "", hours: Any = 72) -> Dict[str, Any]:
        """``GET /agent/trend`` —— 趋势（每小时；复用 ``features/trend.py``）。"""
        t0 = time.time()
        try:
            resp = self.get_trend(scope=scope, id=id, hours=hours)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"趋势读取失败:{e}", t0, trace_id=str(e))
        return self._agent_ok(getattr(resp, "data", {}) or {}, t0)

    def agent_rules(self) -> Dict[str, Any]:
        """``GET /agent/rules`` —— 站点规则（H&R / need_hours / 来源 builtin|override）。"""
        t0 = time.time()
        try:
            resp = self.get_site_rules()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"规则读取失败:{e}", t0, trace_id=str(e))
        data = getattr(resp, "data", {}) or {}
        rules = data.get("rules") or []
        return self._agent_ok({"rules": rules, "rulepack": data.get("rulepack") or {},
                               "total": len(rules)}, t0)

    def agent_settings(self) -> Dict[str, Any]:
        """``GET /agent/settings`` —— 当前设置 + 默认模板 + 下载器参数（只读，复用 UI 同源）。"""
        t0 = time.time()
        data: Dict[str, Any] = {}
        try:
            resp = self.get_defaults()
            data["defaults"] = getattr(resp, "data", resp) or {}
        except Exception as e:  # noqa: BLE001
            data["defaults_error"] = str(e)
        try:
            resp = self.get_downloader_prefs()
            data["downloader"] = getattr(resp, "data", resp) or {}
        except Exception as e:  # noqa: BLE001
            data["downloader_error"] = str(e)
        try:
            st = self.get_status()
            sd = getattr(st, "data", {}) or {}
            data["settings"] = {k: v for k, v in sd.items()
                                if k not in ("summary", "tasks", "options")}
        except Exception as e:  # noqa: BLE001
            data["settings_error"] = str(e)
        return self._agent_ok(data, t0)

    def agent_health(self) -> Dict[str, Any]:
        """``GET /agent/health`` —— 健康检查（各子系统；复用现有 health）。"""
        t0 = time.time()
        try:
            resp = self.get_health()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"健康自检失败:{e}", t0, trace_id=str(e))
        return self._agent_ok(getattr(resp, "data", {}) or {}, t0)

    def agent_blindspot(self) -> Dict[str, Any]:
        """``GET /agent/blindspot`` —— ★H&R 盲区：有 H&R 的站、却**没记账也没标签**的种。

        一次调用答：**「有没有欠了 H&R 我们却根本不知道的种」**。
        同时给出补源**来源站护栏**（``hr != False`` 一律禁用的站点清单）——
        手动补种（含走 MP 下载接口等旁路）同样适用（``rescue.py`` 里的
        ``rescue_source_blocked()`` 是唯一判定）。纯只读，不改任何状态。
        """
        t0 = time.time()
        try:
            data = self._hr_blindspot_scan()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"H&R 盲区扫描失败:{e}", t0, trace_id=str(e))
        blocked: List[Dict[str, Any]] = []
        try:
            blocked = list(self._rescue_skipped_sites() or [])
        except Exception:  # noqa: BLE001
            blocked = []
        payload = dict(data or {})
        payload["source_guard"] = {
            "rule": "rescue/source_hr_guard",
            "verdict": "blocked_sites",
            "blocked_count": len(blocked),
            "blocked": blocked,
            "note": "补源/补种来源站 hr != False（有 H&R 或未知）一律禁用；"
                    "手动补种不得走 MP 下载接口等旁路，一律走 POST /rescue（有干跑+闸门）",
        }
        return self._agent_report(
            payload, t0,
            "hrbills._hr_blindspot_scan() → 下载器快照 + H&R 账单 + 站点规则；"
            "rescue._rescue_skipped_sites() → 补源来源站禁用清单")

    def agent_hr_per_torrent(self) -> Dict[str, Any]:
        """``GET /agent/hr/per-torrent`` —— ★ 逐种 H&R 站（野马PT 类）的账单审计。

        一次调用答：**「逐种开关的站上，我们欠不欠 H&R、有没有漏记账的种」**。
        判定依据：站点规则 ``per_torrent_hr``（不是猜域名）+ 账单 ``rule``
        （11.7.0 起由**下载瞬间**的候选标记落定）。**纯只读不联网**；
        ``unknown`` 账单 = 未读到逐种标记（不保护不罚，可能是漏记）→ 提示人工核对/作废。
        """
        t0 = time.time()
        try:
            data = self._hr_per_torrent_audit()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"逐种 H&R 审计失败:{e}", t0, trace_id=str(e))
        payload = dict(data or {})
        payload["write"] = {
            "void_bill": "GET /tags?action=hrbills_void&hash=<h>&reason=resolved_no_hr&confirm=1",
            "note": "人工作废（摘保护）：站点侧免罪 / 核对确认无 H&R 后使用；可逗号分隔批量",
        }
        return self._agent_report(
            payload, t0,
            "hrbills._hr_per_torrent_audit() → 站点规则 per_torrent_hr + hr_bills.json(rule/state)")

    # ---------------------------------------------------------------- L3 报表层：功能域只读（P1.5c，AI ⊇ 前端）
    @staticmethod
    def _agent_int(v: Any, default: int) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _agent_bool(v: Any) -> bool:
        return str(v or "").strip().lower() in ("1", "true", "yes", "on", "y")

    @staticmethod
    def _agent_resp_data(resp: Any) -> Any:
        if resp is None:
            return None
        data = getattr(resp, "data", None)
        return resp if data is None else data

    def _agent_report(self, data: Any, t0: float, source: str,
                      inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        out = self._agent_ok(data, t0)
        out["meta"]["reason_chain"] = [{
            "rule": "agent/proxy",
            "verdict": "report",
            "inputs": dict(inputs or {}),
            "source_of_truth": source,
            "at": self._agent_now(),
        }]
        return out

    def _agent_call_read(self, t0: float, source: str, fn: Any,
                         *args: Any, **kwargs: Any) -> Dict[str, Any]:
        try:
            resp = fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"{source}读取失败:{e}", t0, trace_id=str(e))
        if getattr(resp, "success", True) is False:
            return self._agent_err("internal",
                                   str(getattr(resp, "message", "") or f"{source}读取失败"), t0)
        return self._agent_report(self._agent_resp_data(resp), t0, source)

    def agent_task_bonus(self, id: str = "") -> Dict[str, Any]:
        t0 = time.time()
        tid = str(id or "").strip()
        if not tid:
            return self._agent_err("bad_param", "id 路径参数必填", t0, field="id")
        return self._agent_call_read(
            t0, "get_task_bonus() → qB 快照 + task_states.json(protected_torrents)",
            self.get_task_bonus, tid)

    def agent_task_candidates(self, id: str = "") -> Dict[str, Any]:
        t0 = time.time()
        tid = str(id or "").strip()
        if not tid:
            return self._agent_err("bad_param", "id 路径参数必填", t0, field="id")
        return self._agent_call_read(
            t0, "get_task_candidates() → 站点候选抓取(fetcher)", self.get_task_candidates, tid)

    def agent_task_handover(self, id: str = "") -> Dict[str, Any]:
        t0 = time.time()
        tid = str(id or "").strip()
        if not tid:
            return self._agent_err("bad_param", "id 路径参数必填", t0, field="id")
        return self._agent_call_read(
            t0, "get_task_handover() → tag 账本(seed ledger) + 任务配置", self.get_task_handover, tid)

    def agent_recommend(self) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(t0, "get_recommend_list() → recommend store",
                                     self.get_recommend_list)

    def agent_crossseed(self) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(t0, "get_crossseed() → 跨站待回辅队列(kv)", self.get_crossseed)

    def agent_reseed(self) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(t0, "get_reseed() → 辅种配置/站点/配额/账本", self.get_reseed)

    def agent_douban(self) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(t0, "douban_service_status() → magicflow-douban 服务状态",
                                     self.douban_service_status)

    def agent_live(self, site_id: Any = 0) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(
            t0, "get_live_state() → 站点实时数据(直连站点)",
            self.get_live_state, site_id=self._agent_int(site_id, 0))

    def agent_signin(self, days: Any = 7) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(
            t0, "get_signin_state() → 签到记录/站点账本",
            self.get_signin_state, days=self._agent_int(days, 7))

    def agent_exam(self, site_id: Any = 0, include_pass: Any = False) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(
            t0, "get_exam_state() → 考核解析 + live 快照",
            self.get_exam_state, site_id=self._agent_int(site_id, 0),
            include_pass=self._agent_bool(include_pass))

    def agent_silent(self, limit: Any = 400, records: Any = 60) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(
            t0, "silent_pool() → 静默池(tag 账本 + 下载器)",
            self.silent_pool, limit=limit, records=records)

    def agent_claim(self, site_id: Any = None) -> Dict[str, Any]:
        t0 = time.time()
        sid = self._agent_int(site_id, 0) if site_id not in (None, "") else None
        return self._agent_call_read(
            t0, "get_claim_state() → 认领账本 + journal", self.get_claim_state, site_id=sid)

    def agent_cloud(self) -> Dict[str, Any]:
        t0 = time.time()
        data: Dict[str, Any] = {}
        try:
            data["state"] = self._agent_resp_data(self.get_cloud_state()) or {}
        except Exception as e:  # noqa: BLE001
            data["state_error"] = str(e)
        try:
            data["test"] = self._agent_resp_data(self.test_cloud()) or {}
        except Exception as e:  # noqa: BLE001
            data["test_error"] = str(e)
        return self._agent_report(data, t0, "get_cloud_state()/test_cloud() → 云盘配置 + 归档记录 + 连通性")

    def agent_fallback(self, resolve_paths: Any = False) -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(
            t0, "get_fallback_state() → 元数据兜底配置 + 最近结果",
            self.get_fallback_state, resolve_paths=self._agent_bool(resolve_paths))

    def agent_iyuu(self) -> Dict[str, Any]:
        t0 = time.time()
        data: Dict[str, Any] = {}
        try:
            data["sites"] = self._agent_resp_data(self.get_iyuu_sites()) or {}
        except Exception as e:  # noqa: BLE001
            data["sites_error"] = str(e)
        try:
            data["test"] = self._agent_resp_data(self.test_iyuu()) or {}
        except Exception as e:  # noqa: BLE001
            data["test_error"] = str(e)
        return self._agent_report(data, t0, "get_iyuu_sites()/test_iyuu() → IYUU 密钥表 + 连通性")

    def agent_events(self, since: Any = 0, limit: Any = 200, kind: str = "",
                     task_id: str = "", level: str = "") -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(
            t0, "get_events() → 结构化事件流(journal + eventlog)",
            self.get_events, since=since, limit=self._agent_int(limit, 200),
            kind=kind, task_id=task_id, level=level)

    def agent_tags(self, action: str = "status") -> Dict[str, Any]:
        t0 = time.time()
        return self._agent_call_read(
            t0, "get_tag_model(status) → 标签账本 + 文件组 + 分拣规则",
            self.get_tag_model, action=str(action or "status").strip().lower() or "status")


# ---------------------------------------------------------------------------
# L0 字段字典（返回类型 schema）。诚实原则：写不出的字段标 "unknown"。
# ---------------------------------------------------------------------------

def _f(type_: str, unit: str = "", nullable: bool = False, enum: Any = None,
       desc: str = "") -> Dict[str, Any]:
    d: Dict[str, Any] = {"type": type_}
    if unit:
        d["unit"] = unit
    if enum is not None:
        d["enum"] = list(enum)
    if desc:
        d["desc"] = desc
    d["nullable"] = bool(nullable)
    return d


def _agent_type_schemas() -> Dict[str, Dict[str, Any]]:
    return {
        "Manifest": {
            "plugin": _f("string", nullable=False),
            "plugin_version": _f("string"),
            "schema_version": _f("string"),
            "endpoints": _f("array", desc="能力清单（path/method/write/params/returns/version）"),
            "types": _f("object", desc="类型字段字典"),
        },
        "AgentState": {
            "tasks": _f("object", desc="{total,enabled,running,seeding,stopped}"),
            "managed": _f("object", desc="{torrents,protected_manual,protected_crossseed,protected_claim}"),
            "bills": _f("object", desc="账单统计 {total,by_state,by_rule,by_site,opened_by}"),
            "pool": _f("object", desc="{volumes[],watermark}"),
            "sites": _f("object", desc="{total,hr_enabled}"),
        },
        "DecideReport": {
            "items": _f("array", desc="每 hash 一条 {hash,name,state,progress,verdict,reason_chain[],bills[],protection[]}"),
        },
        "BillPage": {
            "items": _f("array", desc="账单列表（含 hash）"),
            "next_cursor": _f("string", nullable=True),
            "total": _f("int"),
        },
        "Bill": {
            "hash": _f("string", nullable=False),
            "site": _f("string"), "rule": _f("string"), "state": _f("string"),
            "need_h": _f("float", unit="h"), "seeded_h": _f("float", unit="h"),
            "fp": _f("string"), "title": _f("string"),
            "opened_at": _f("float", unit="s"), "opened_by": _f("string"),
            "progress": _f("float"), "last_progress": _f("float"),
            "last_progress_at": _f("float", unit="s"),
        },
        "SnapshotRound": {
            "round_id": _f("string"), "pulls": _f("int"), "elapsed_ms": _f("int"),
        },
        "RescueReport": {
            "targets": _f("array", desc="停滞欠 H&R/手动保留的未下完种"),
            "skipped_sites": _f("array", desc="不能当补源的站点"),
            "settings": _f("object", desc="补源配置 {stall_hours,tag,max_candidates,reason_not_reuse}"),
        },
        "LedgerPage": {
            "table": _f("string", nullable=False),
            "columns": _f("array", desc="列字典 [{name,type,unit,enum?,desc?,nullable}]"),
            "rows": _f("array", desc="行数据（dict）"),
            "total": _f("int"),
            "next_cursor": _f("string", nullable=True),
        },
        "SchemaReport": {
            "types": _f("object", desc="返回类型 → 字段字典"),
            "tables": _f("object", desc="真值表 → 列字典"),
        },
        "Overview": {
            "status": _f("object", desc="= /status 内部实现（summary/tasks/options/配置面）"),
            "state": _f("object", desc="= AgentState（任务/托管/账单/池/站点 计数）"),
            "status_error": _f("string", nullable=True),
            "state_error": _f("string", nullable=True),
        },
        "TaskList": {
            "tasks": _f("array", desc="任务列表（含 enabled/run_mode/site/统计）"),
            "total": _f("int"),
        },
        "TaskDetail": {
            "task": _f("object", desc="完整任务配置 + 统计"),
            "operations": _f("object", desc="{items[],total} 该任务操作记录摘要"),
            "summary": _f("object", desc="{seeding_count,candidate_total,candidate_passed}"),
        },
        "OperationsPage": {
            "items": _f("array", desc="操作记录列表"),
            "next_cursor": _f("string", nullable=True),
            "total": _f("int"),
        },
        "PoolReport": {
            "name": _f("string"), "path": _f("string"),
            "total": _f("float", unit="B"), "used": _f("float", unit="B"),
            "free": _f("float", unit="B"), "pct": _f("float", unit="%"),
            "threshold": _f("float"), "budget_gb": _f("float", unit="GB"),
            "pools": _f("array", desc="全部池 [{name,path,total,used,free,pct,matched}]"),
        },
        "TrendReport": {
            "hours": _f("int"), "keep": _f("int"),
            "series": _f("object", desc="按 scope:id 的趋势点序列"),
            "names": _f("object", desc="任务/站点 id → 名"),
        },
        "RulesReport": {
            "rules": _f("array", desc="每站点一行 {domain,hr,seed_hours,source,…}"),
            "rulepack": _f("object", desc="内置规则包元信息"),
            "total": _f("int"),
        },
        "SettingsReport": {
            "defaults": _f("object", desc="默认任务模板"),
            "downloader": _f("object", desc="下载器全局参数 + 推荐值"),
            "settings": _f("object", desc="当前设置（= /status 配置面）"),
            "defaults_error": _f("string", nullable=True),
            "downloader_error": _f("string", nullable=True),
            "settings_error": _f("string", nullable=True),
        },
        "HealthReport": {
            "level": _f("string", enum=["ok", "info", "warning", "error"]),
            "ok": _f("bool"), "counts": _f("object"),
            "issues": _f("array", desc="问题清单（按严重度排序）"),
            "checked_at": _f("float", unit="s"),
        },
        "TaskBonusReport": {
            "torrents": _f("array", desc="托管种明细（hash/title/size_gb/is_protected/state/progress/uploaded/ratio）"),
            "total_bonus": _f("float", unit="magic/h", desc="魔力/小时（= /tasks/{id}/bonus）"),
            "torrent_count": _f("int"), "protected_count": _f("int"),
            "site": _f("object", desc="站点口径信息"),
        },
        "TaskCandidatesReport": {
            "candidates": _f("array", desc="候选种子（黑盒：名次 + 基础属性，不暴露自算评分）"),
            "total": _f("int"), "reason_counts": _f("object"),
        },
        "TaskHandoverReport": {
            "_source": _f("string", desc="= /tasks/{id}/handover 交棒预览原始数据"),
        },
        "RecommendReport": {
            "items": _f("array", desc="推荐甄别结果（media/评分/来源/状态）"),
            "total": _f("int"),
        },
        "CrossseedReport": {
            "pending": _f("array", desc="待回辅队列"),
            "sources": _f("array", desc="来源站统计"),
            "tasks": _f("array", desc="启用跨站的任务"),
        },
        "ReseedReport": {
            "_source": _f("string", desc="= /reseed 全站辅种状态（站点/配额/缓存/账本/上轮结果）"),
        },
        "DoubanReport": {
            "_source": _f("string", desc="= /douban_service 豆瓣评分服务库容量 + 慢爬进度"),
        },
        "LiveReport": {
            "_source": _f("string", desc="= /live 站点实时数据 + 流量监控"),
        },
        "SigninReport": {
            "sites": _f("array", desc="签到/登录站点状态"),
            "records": _f("array", desc="近 N 天签到记录"),
        },
        "ExamReport": {
            "sites": _f("array", desc="考核站点行（exam/plan/tasks/live_ok）"),
            "count": _f("int"), "enabled": _f("bool"), "ts": _f("float", unit="s"),
        },
        "SilentReport": {
            "_source": _f("string", desc="= /silent/pool 静默池现状（托管/欠H&R/停滞/分布）"),
        },
        "ClaimReport": {
            "_source": _f("string", desc="= /claim 认领概览/可认领/已认领/账本/记录"),
        },
        "CloudReport": {
            "state": _f("object", desc="云盘归档配置 + 最近计划/结果 + 归档记录"),
            "test": _f("object", desc="连通性自检（OpenList 存储/挂载）"),
            "state_error": _f("string", nullable=True), "test_error": _f("string", nullable=True),
        },
        "FallbackReport": {
            "_source": _f("string", desc="= /fallback 元数据兜底配置 + 最近一次结果"),
        },
        "IYUUReport": {
            "sites": _f("object", desc="IYUU 站点密钥表（剥 credential 密文）"),
            "test": _f("object", desc="IYUU 连通测试结果"),
            "sites_error": _f("string", nullable=True), "test_error": _f("string", nullable=True),
        },
        "EventsReport": {
            "events": _f("array", desc="结构化事件（升序，含 ts/kind/level/task_id/state/items）"),
            "total": _f("int"),
        },
        "TagsReport": {
            "_source": _f("string", desc="= /tags 标签模型总览（enabled/超时/快照间隔/账本数/分拣规则）"),
        },
    }
