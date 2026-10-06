# -*- coding: utf-8 -*-
"""魔流 · agentapi —— 「AI 友好」只读门面（P1.5a）。

目标（Master 2026-10-05）：
把「插件内部怎么想、为什么这么判」变成**一次调用就能拿到的结构化答案**，
让 agent 排查 / 运维 / B 端自动化**不必翻源码**。契约见 ``docs/AGENT-API.md``。

本模块是**只读半边**（P1.5a）：
  - ``GET /agent``          能力清单（自描述：端点/方法/参数/返回类型/是否可写/版本）
  - ``GET /agent/state``    总览（任务/托管/账单/池/站点 计数）
  - ``GET /agent/decide``   ★核心：每个 hash 的 ``verdict`` + ``reason_chain``
  - ``GET /agent/bills``    分页账单（limit/cursor + site/state/rule 过滤）
  - ``GET /agent/bills/{hash}``  单条账单
  - ``GET /agent/snapshot`` 快照轮观测（复用 ``common.decision_round_stats``）

铁律（本模块只读，不碰决策/账本真值源）：
  - 只读现有真值源：``_delete_gate_detail`` / ``_protection_sets`` / ``_hr_obligation`` /
    bills store / task store / ``common.decision_round_stats``。
  - **绝不新增 / 缓存真值**（不写任何 json / 账本 / 热层）。
  - 不引入新的进程级单例字段。
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..common import (
    __version__,
    RUN_MODE_RUNNING,
    RUN_MODE_SEEDING,
    decision_round_stats,
    run_mode_of,
)
from .pool import POOL_THRESHOLD

# 契约版本（§2 信封 meta.schema_version）。字段/端点只增不改，改 = MAJOR。
AGENT_SCHEMA_VERSION = "1.0"
# 端点清单版本（每个端点单独记 version，当前全 1.0）。
AGENT_ENDPOINT_VERSION = "1.0"

# 分页默认 / 上限
DEFAULT_LIMIT = 50
MAX_LIMIT = 500

# 合法 hex 长度（40 = SHA1 info-hash，64 = 全 sha256；只做长度+字符校验，不猜语义）
_HEX = set("0123456789abcdef")

# ---------------------------------------------------------------------------
# ★ 不泄密：AI 门面出口统一剥密（唯一出口关卡，所有 handler 都过 _agent_ok）
# ---------------------------------------------------------------------------
#: 键名命中即视为密文：非空字符串值 → ``"***"``，并补 ``<key>_set=True`` 保住「是否已配置」。
_AGENT_SECRET_KEYS = frozenset({
    "token", "iyuu_token", "cloud_openlist_token", "cookie", "site_cookie",
    "passkey", "credential", "credentials", "apikey", "api_key", "apikeys",
    "password", "passwd", "secret", "private_key", "access_token", "refresh_token",
    "user_agent", "ua", "authorization",
})


def _agent_scrub(obj: Any) -> Any:
    """递归剥密（纯函数）：密文键的**非空字符串**值 → ``"***"``。

    - 布尔/数字/空值原样保留（``{"token": False}`` = 未配置 → 不遮）
    - 被遮的键补 ``<key>_set: True``，保证「是否已配置」仍可判定
    - dict/list 递归；其它类型原样返回
    """
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            key = k.strip().lower() if isinstance(k, str) else ""
            if key in _AGENT_SECRET_KEYS and isinstance(v, str) and v.strip():
                out[k] = "***"
                out[key + "_set"] = True
            else:
                out[k] = _agent_scrub(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_agent_scrub(x) for x in obj]
    return obj


def _agent_endpoints() -> List[Dict[str, Any]]:
    """能力清单**唯一真值源**（登记制：新增端点必须加在这里，preflight 校验）。

    ``handler`` 是 ``AgentApiMixin`` 上的方法名（``get_api`` 用它绑定路由）；
    公开给 ``GET /agent`` 时会把 ``handler`` 剥掉（不暴露内部方法名）。
    """
    return [
        {"path": "/agent", "method": "GET", "handler": "agent_manifest", "write": False,
         "params": {}, "returns": "Manifest", "version": AGENT_ENDPOINT_VERSION,
         "summary": "能力清单（自描述：端点/方法/参数/返回类型/是否可写/版本）"},
        {"path": "/agent/state", "method": "GET", "handler": "agent_state", "write": False,
         "params": {}, "returns": "AgentState", "version": AGENT_ENDPOINT_VERSION,
         "summary": "总览（任务/托管/账单/池/站点 计数）"},
        {"path": "/agent/decide", "method": "GET", "handler": "agent_decide", "write": False,
         "params": {"hashes": "hex[] 逗号分隔（必填，40/64 位）"}, "returns": "DecideReport",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "★核心：每个 hash 的 verdict + reason_chain + bills + protection"},
        {"path": "/agent/bills", "method": "GET", "handler": "agent_bills", "write": False,
         "params": {"site": "domain", "state": "active|settled|pending|void",
                    "rule": "site_hr|hit_and_run|unknown", "limit": "int", "cursor": "str"},
         "returns": "BillPage", "version": AGENT_ENDPOINT_VERSION,
         "summary": "分页账单（limit/cursor + site/state/rule 过滤）"},
        {"path": "/agent/bills/{hash}", "method": "GET", "handler": "agent_bill", "write": False,
         "params": {"hash": "hex 路径参数（40/64 位）"}, "returns": "Bill",
         "version": AGENT_ENDPOINT_VERSION, "summary": "单条账单（含 opened_by/opened_at/void_reason）"},
        {"path": "/agent/snapshot", "method": "GET", "handler": "agent_snapshot", "write": False,
         "params": {}, "returns": "SnapshotRound", "version": AGENT_ENDPOINT_VERSION,
         "summary": "快照轮观测（本轮决策拉了几次快照、耗时）"},
        {"path": "/agent/rescue", "method": "GET", "handler": "agent_rescue", "write": False,
         "params": {}, "returns": "RescueReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "死种补源观测：停滞欠 H&R/手动保留的未下完种 + 不能当源的站点 + 配置"},
        {"path": "/agent/rescue/candidates", "method": "GET", "handler": "agent_rescue_candidates",
         "write": False,
         "params": {"hashes": "逗号分隔 hash（可空=全部目标）", "verify": "1|0（默认 1；会联网拉候选 .torrent 做指纹校验）"},
         "returns": "RescueCandidatesReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★ 真正可用的补源候选（IYUU 指纹索引 + 拉 .torrent 校验文件清单特征码）；不写下载器"},
        # ---- P1.5b：真值源直出 + 字段字典 + 报表层首批（handler 在 AgentLedgerMixin）----
        {"path": "/agent/ledger/{table}", "method": "GET", "handler": "agent_ledger", "write": False,
         "params": {"table": "site|resource|identity|task|seed|deck|crossseed|bills|deletions|journal|protected|rescue_actions|reseed|run|claim",
                    "limit": "int（默认 50，0=全量）", "cursor": "str", "filter": "k=v 逗号分隔（如 site=/state=/rule=）",
                    "fields": "逗号分隔字段投影"}, "returns": "LedgerPage",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "真值表原样导出（列字典 + 分页 + 过滤 + 字段投影）——前端基本不给看的那一层"},
        {"path": "/agent/schema", "method": "GET", "handler": "agent_schema", "write": False,
         "params": {}, "returns": "SchemaReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "字段字典：所有返回类型 + 所有真值表的字段/类型/单位/枚举/可空"},
        {"path": "/agent/overview", "method": "GET", "handler": "agent_overview", "write": False,
         "params": {}, "returns": "Overview", "version": AGENT_ENDPOINT_VERSION,
         "summary": "聚合首页（复用 /status 内部实现 + AgentState）"},
        {"path": "/agent/tasks", "method": "GET", "handler": "agent_tasks", "write": False,
         "params": {}, "returns": "TaskList", "version": AGENT_ENDPOINT_VERSION,
         "summary": "任务列表（含 enabled/run_mode/site/统计）"},
        {"path": "/agent/tasks/{id}", "method": "GET", "handler": "agent_task_detail", "write": False,
         "params": {"id": "任务 id 路径参数"}, "returns": "TaskDetail",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "任务详情（含完整配置）+ 候选/种子/操作记录摘要"},
        {"path": "/agent/operations", "method": "GET", "handler": "agent_operations", "write": False,
         "params": {"limit": "int", "cursor": "str", "task": "任务 id", "action": "操作类型(kind)"},
         "returns": "OperationsPage", "version": AGENT_ENDPOINT_VERSION,
         "summary": "跨任务操作记录（limit/cursor/task/action 过滤）"},
        {"path": "/agent/pool", "method": "GET", "handler": "agent_pool", "write": False,
         "params": {"path": "任务保存目录（可选）"}, "returns": "PoolReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "池容积 / 磁盘水位 / 预算"},
        {"path": "/agent/trend", "method": "GET", "handler": "agent_trend", "write": False,
         "params": {"scope": "all|task|site", "id": "任务/站点 id", "hours": "int（默认 72）"},
         "returns": "TrendReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "趋势（每小时；复用 features/trend.py）"},
        {"path": "/agent/rules", "method": "GET", "handler": "agent_rules", "write": False,
         "params": {}, "returns": "RulesReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "站点规则（H&R / need_hours / 来源 builtin|override）"},
        {"path": "/agent/settings", "method": "GET", "handler": "agent_settings", "write": False,
         "params": {}, "returns": "SettingsReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "当前设置 + 默认模板 + 下载器参数（只读）"},
        {"path": "/agent/health", "method": "GET", "handler": "agent_health", "write": False,
         "params": {}, "returns": "HealthReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "健康检查（各子系统；复用现有 health）"},
        {"path": "/agent/blindspot", "method": "GET", "handler": "agent_blindspot", "write": False,
         "params": {}, "returns": "HrBlindspotReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★H&R 盲区（有 H&R 的站却没记账/没标签的种）+ 补源来源站禁用清单"},
        {"path": "/agent/hr/per-torrent", "method": "GET", "handler": "agent_hr_per_torrent",
         "write": False,
         "params": {}, "returns": "PerTorrentHrReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★逐种 H&R 站（野马PT 类）账单审计：按 rule/state 摊开，unknown=可能漏记"},
        {"path": "/agent/hr/reconcile", "method": "GET", "handler": "agent_hr_reconcile",
         "write": False,
         "params": {"site": "站点域名（可空=全部 hr=True 站）", "live": "1=现在就真抓一轮（默认只读上次结果）"},
         "returns": "HrReconcileReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★站点 myhr 三方对账（站点欠×本机有无×账本账单）：只判「还欠」，绝不判「已结清」"},
        {"path": "/agent/yema", "method": "GET", "handler": "agent_yema", "write": False,
         "params": {"live": "1=联机对账（拉站点后台接口）；默认读上一轮缓存",
                    "force": "1=忽略缓存强拉"},
         "returns": "YemaReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★野马PT 逐种 H&R 对账（站点 hrPunishEnable × 本机 × 账本）：漏挂/漏记可见；不产 settled"},
        {"path": "/agent/yema/absolve", "method": "GET", "handler": "agent_yema_absolve", "write": True,
         "params": {"tid": "站点 torrentId（必填）", "confirm": "1=真写（默认干跑，只报成本）"},
         "returns": "YemaAbsolve", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★野马PT「免罪」（扣积分、不可逆）：默认干跑；confirm=1 才写"},
        {"path": "/agent/site/seeds", "method": "GET", "handler": "agent_site_seeds",
         "write": False,
         "params": {"site": "站点域名 / 短名 / id（可空 = 只回站点清单）",
                    "live": "1 = 现抓站点 H&R 对账（同 /agent/hr/reconcile）"},
         "returns": "SiteSeedsReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★站点级种子报表：逐条种子状态（分类/保护/账单/qB） + H&R 摘要"},
        # ---- 11.11.0 H&R 账单按站 + 违约告警（只读）----
        {"path": "/agent/hr/bills", "method": "GET", "handler": "agent_hr_bills", "write": False,
         "params": {"site": "域名（可空=全站）", "live": "1=现抓对账（默认读缓存）"},
         "returns": "HrBillsBySite", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★H&R 账单按站分组（欠债/状态分布/need_left/in_qb/missing/per_torrent_hr/规则来源）；只读"},
        {"path": "/agent/hr/breaches", "method": "GET", "handler": "agent_hr_breaches", "write": False,
         "params": {}, "returns": "HrBreaches", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★H&R 违约告警清单（欠债种消失：归因 plugin/external + gate_bug 升级 + 补源提示）；只读"},
        {"path": "/agent/silent/audit", "method": "GET", "handler": "agent_silent_audit", "write": False,
         "params": {"limit": "int（默认 1000；0=全量）"}, "returns": "SilentAudit", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★静默池盘点（四类分类 + stalled_violation 违背不变量 + 清理候选）；只读"},
        {"path": "/agent/silent/enforce", "method": "GET", "handler": "agent_silent_enforce",
         "write": True,
         "params": {"confirm": "1=真补 pause（默认干跑）"},
         "returns": "SilentEnforce", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★★静默不变量收敛（12.7.1）：账本静默但 qB 没停的种补 pause（幂等、只 pause 不删）；默认干跑"},
        # ---- P1.5c：功能域只读（AI ⊇ 前端，收编 19 个只读豁免域）----
        {"path": "/agent/tasks/{id}/bonus", "method": "GET", "handler": "agent_task_bonus", "write": False,
         "params": {"id": "任务 id 路径参数"}, "returns": "TaskBonusReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "做种魔力明细（= /tasks/{id}/bonus）"},
        {"path": "/agent/tasks/{id}/candidates", "method": "GET", "handler": "agent_task_candidates", "write": False,
         "params": {"id": "任务 id 路径参数"}, "returns": "TaskCandidatesReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "候选种子及评分（= /tasks/{id}/candidates）"},
        {"path": "/agent/tasks/{id}/handover", "method": "GET", "handler": "agent_task_handover", "write": False,
         "params": {"id": "任务 id 路径参数"}, "returns": "TaskHandoverReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "交棒预览（= /tasks/{id}/handover）"},
        {"path": "/agent/recommend", "method": "GET", "handler": "agent_recommend", "write": False,
         "params": {}, "returns": "RecommendReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "推荐甄别结果（= /recommend）"},
        {"path": "/agent/crossseed", "method": "GET", "handler": "agent_crossseed", "write": False,
         "params": {}, "returns": "CrossseedReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "跨站取种待回辅队列（= /crossseed 只读）"},
        {"path": "/agent/reseed", "method": "GET", "handler": "agent_reseed", "write": False,
         "params": {}, "returns": "ReseedReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "全站辅种现状（= /reseed）"},
        {"path": "/agent/douban", "method": "GET", "handler": "agent_douban", "write": False,
         "params": {}, "returns": "DoubanReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "豆瓣评分服务现状（= /douban_service）"},
        {"path": "/agent/live", "method": "GET", "handler": "agent_live", "write": False,
         "params": {"site_id": "站点 id（可选）"}, "returns": "LiveReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "站点实时数据（= /live）"},
        {"path": "/agent/signin", "method": "GET", "handler": "agent_signin", "write": False,
         "params": {"days": "int（近 N 天，默认 7）"}, "returns": "SigninReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "签到现状（= /signin）"},
        {"path": "/agent/exam", "method": "GET", "handler": "agent_exam", "write": False,
         "params": {"site_id": "站点 id（可选）", "include_pass": "是否含已通过（默认否）"},
         "returns": "ExamReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "新手考核现状（= /exam）"},
        {"path": "/agent/silent", "method": "GET", "handler": "agent_silent", "write": False,
         "params": {"limit": "int", "records": "int"}, "returns": "SilentReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "静默池现状（= /silent/pool）"},
        {"path": "/agent/claim", "method": "GET", "handler": "agent_claim", "write": False,
         "params": {"site_id": "站点 id（可选）"}, "returns": "ClaimReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "认领现状（= /claim）"},
        {"path": "/agent/cloud", "method": "GET", "handler": "agent_cloud", "write": False,
         "params": {}, "returns": "CloudReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "云盘归档现状 + 连通性（= /cloud + /cloud/test）"},
        {"path": "/agent/fallback", "method": "GET", "handler": "agent_fallback", "write": False,
         "params": {"resolve_paths": "bool（是否解析路径）"}, "returns": "FallbackReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "元数据兜底现状（= /fallback）"},
        {"path": "/agent/iyuu", "method": "GET", "handler": "agent_iyuu", "write": False,
         "params": {}, "returns": "IYUUReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "IYUU 密钥表 + 连通性（= /iyuu/sites + /iyuu/test）"},
        {"path": "/agent/events", "method": "GET", "handler": "agent_events", "write": False,
         "params": {"since": "ts", "limit": "int", "kind": "类型", "task_id": "任务 id", "level": "级别"},
         "returns": "EventsReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "结构化事件流（= /events）"},
        {"path": "/agent/tags", "method": "GET", "handler": "agent_tags", "write": False,
         "params": {"action": "只读动作（默认 status）"}, "returns": "TagsReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "标签模型总览（= /tags status）"},
        # ---- 11.12.0 代码字典（符号级索引，只读）----
        {"path": "/agent/code-dict", "method": "GET", "handler": "agent_code_dict", "write": False,
         "params": {"q": "子串模糊查（符号/常量/端点/模块职责/口径）",
                    "section": "endpoints|constants|symbols|modules|glossary（取整节）",
                    "full": "1=回全部（大，慎用）"},
         "returns": "CodeDict", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★代码字典（符号级索引）：一次调用答「某常量/函数/端点/口径在哪个文件哪一行」"},
        # ---- 12.5.0 挂种健康度自检（只读）----
        {"path": "/agent/seeds/health", "method": "GET", "handler": "agent_seeds_health",
         "write": False,
         "params": {"site": "域名/短名/id（可空=全站）", "only": "ghost|partial|all（默认 all）",
                    "limit": "int（默认 200，0=不限）"},
         "returns": "SeedsHealthReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "★挂种健康度自检（逐文件核盘）：空转/缺文件 + 体积 + 其中欠 H&R 的风险；只读"},
        # ---- 12.7.0 调试面自描述（只读）----
        {"path": "/agent/debug/surface", "method": "GET", "handler": "agent_debug_surface",
         "write": False,
         "params": {},
         "returns": "DebugSurface",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "★调试面自描述：有哪些 /debug 端点 / 哪些会写 / 写操作需 confirm=1 / 读文件白名单与敏感文件黑名单；只读"},
    ]


class AgentApiMixin:
    """AI 友好只读门面（P1.5a）。"""

    # ------------------------------------------------------------------ 信封（§2）
    def _agent_meta(self, t0: float) -> Dict[str, Any]:
        took_ms = max(0, int(round((time.time() - t0) * 1000.0)))
        return {
            "schema_version": AGENT_SCHEMA_VERSION,
            "plugin_version": __version__,
            "took_ms": took_ms,
        }

    def _agent_ok(self, data: Any, t0: float) -> Dict[str, Any]:
        return {"ok": True, "code": "ok", "message": "", "data": _agent_scrub(data),
                "meta": self._agent_meta(t0)}

    def _agent_err(self, code: str, message: str, t0: Optional[float] = None,
                   field: Optional[str] = None, trace_id: Optional[str] = None) -> Dict[str, Any]:
        data = None
        if field is not None or trace_id is not None:
            data = {}
            if field is not None:
                data["field"] = field
            if trace_id is not None:
                data["trace_id"] = trace_id
        return {"ok": False, "code": code, "message": message, "data": data,
                "meta": self._agent_meta(t0 if t0 is not None else time.time())}

    @staticmethod
    def _agent_now() -> str:
        """判定时间戳（ISO 8601 带时区）。可被离线测试覆盖。"""
        return datetime.now().astimezone().isoformat(timespec="seconds")

    # ------------------------------------------------------------------ 路由注册
    def get_api(self) -> List[Dict[str, Any]]:
        """在现有路由表上**只追加** ``/agent*`` 路由，不动其它任何端点。"""
        routes = super().get_api()
        for ep in _agent_endpoints():
            handler = getattr(self, ep["handler"], None)
            if not callable(handler):
                continue
            routes.append({
                "path": ep["path"],
                "endpoint": handler,
                "methods": [ep["method"]],
                "auth": "bear",
                "summary": ep.get("summary", ep["handler"]),
            })
        return routes

    # ------------------------------------------------------------------ 能力清单
    def _agent_manifest_data(self) -> Dict[str, Any]:
        endpoints = []
        for ep in _agent_endpoints():
            endpoints.append({
                "path": ep["path"],
                "method": ep["method"],
                "write": bool(ep.get("write")),
                "params": dict(ep.get("params") or {}),
                "returns": ep.get("returns", ""),
                "version": ep.get("version", AGENT_ENDPOINT_VERSION),
            })
        return {
            "plugin": "MagicFlow",
            "plugin_version": __version__,
            "schema_version": AGENT_SCHEMA_VERSION,
            "endpoints": endpoints,
            "types": {
                "Reason": "判定依据链单条 {rule, verdict, inputs, source_of_truth, at}",
                "DecideReport": "{hash, name, state, progress, verdict, reason_chain[], bills[], protection[]}",
                "BillPage": "{items[], next_cursor, total}",
                "AgentState": "{tasks{}, managed{}, bills{}, pool{}, sites{}}",
            },
        }

    def agent_manifest(self) -> Dict[str, Any]:
        """``GET /agent`` —— 能力清单。"""
        t0 = time.time()
        return self._agent_ok(self._agent_manifest_data(), t0)

    # ------------------------------------------------------------------ 只读真值源小助手（无副作用，纯读）
    def _agent_manual_hashes(self) -> set:
        """手动保留 hash 并集（跨所有任务 + 历史空 task_id），与 ``_delete_gate_detail`` 同源。"""
        out: set = set()
        try:
            store = getattr(self, "_store", None)
            if store is None:
                return out
            tids = list((getattr(self, "_task_configs", None) or {}).keys())
            tids.append("")
            for tid in tids:
                try:
                    out |= set(store.get_protected_torrents(tid) or set())
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        return {str(h).strip().lower() for h in out}

    def _agent_crossseed_hashes(self) -> set:
        try:
            return {str(h).strip().lower() for h in (self._crossseed_source_hashes() or set())}
        except Exception:  # noqa: BLE001
            return set()

    def _agent_claim_hashes(self) -> set:
        try:
            return {str(h).strip().lower() for h in (self._claim_protected_hashes() or set())}
        except Exception:  # noqa: BLE001
            return set()

    @staticmethod
    def _agent_bill_view(h: str, bill: Dict[str, Any]) -> Dict[str, Any]:
        """账单视图：hash 键并入账单自身字段（含 opened_by/opened_at/void_reason）。"""
        out = {"hash": str(h).strip().lower()}
        out.update(dict(bill or {}))
        return out

    # ------------------------------------------------------------------ 状态总览
    def agent_state(self) -> Dict[str, Any]:
        """``GET /agent/state`` —— 总览（任务/托管/账单/池/站点 计数）。

        纯计数、零副作用；只读现有真值源（task_configs / tag 账本 / bills store /
        pool / site rules）。不做快照级保护合成（贵），硬保护计数只取「无需快照」的
        三类（手动 / 跨站来源份 / 已认领），H&R 欠账见 ``/agent/bills?state=active``。
        """
        t0 = time.time()
        # 任务（唯一真源 run_mode；enabled = running + seeding）
        tasks: Dict[str, Any] = {"total": 0, "enabled": 0, "running": 0,
                                 "seeding": 0, "stopped": 0}
        try:
            cfgs = getattr(self, "_task_configs", None) or {}
            for task in cfgs.values():
                tasks["total"] = int(tasks["total"]) + 1
                m = run_mode_of(task)
                if m == RUN_MODE_RUNNING:
                    tasks["running"] = int(tasks["running"]) + 1
                elif m == RUN_MODE_SEEDING:
                    tasks["seeding"] = int(tasks["seeding"]) + 1
                else:
                    tasks["stopped"] = int(tasks["stopped"]) + 1
            tasks["enabled"] = int(tasks["running"]) + int(tasks["seeding"])
        except Exception:  # noqa: BLE001
            pass
        # 托管（torrents = 状态账本规模；保护计数 = 无需快照的三类硬保护）
        managed: Dict[str, Any] = {"torrents": 0, "protected_manual": 0,
                                   "protected_crossseed": 0, "protected_claim": 0}
        try:
            managed["torrents"] = len(dict(self._tag_state().items() or {}))
        except Exception:  # noqa: BLE001
            pass
        try:
            managed["protected_manual"] = len(self._agent_manual_hashes())
        except Exception:  # noqa: BLE001
            pass
        try:
            managed["protected_crossseed"] = len(self._agent_crossseed_hashes())
        except Exception:  # noqa: BLE001
            pass
        try:
            managed["protected_claim"] = len(self._agent_claim_hashes())
        except Exception:  # noqa: BLE001
            pass
        # 账单（复用 bills store 自带 stats，只读）
        try:
            bills = self._hrbills_store().stats()
        except Exception:  # noqa: BLE001
            bills = {"total": 0, "by_state": {}, "by_rule": {}, "by_site": {}, "opened_by": {}}
        # 池（每个下载目录一个池；watermark 与 pool.POOL_THRESHOLD 同源）
        pool: Dict[str, Any] = {"volumes": [], "watermark": round(POOL_THRESHOLD * 100.0, 1)}
        try:
            for name, path in self._pool_dirs():
                u = self._usage(path)
                if not u:
                    continue
                pool["volumes"].append({
                    "path": path,
                    "name": name,
                    "used_pct": float(u.get("pct") or 0.0),
                    "free_gb": round(float(u.get("free") or 0.0) / (1024 ** 3), 1),
                })
        except Exception:  # noqa: BLE001
            pass
        # 站点（hr_enabled = 规则库明确 True 的站）
        sites: Dict[str, Any] = {"total": 0, "hr_enabled": 0}
        try:
            sl = self._list_sites() or []
            sites["total"] = len(sl)
            for s in sl:
                dom = str(s.get("domain") or "").strip().lower()
                if dom:
                    try:
                        if self._site_hr_flag(dom) is True:
                            sites["hr_enabled"] = int(sites["hr_enabled"]) + 1
                    except Exception:  # noqa: BLE001
                        continue
        except Exception:  # noqa: BLE001
            pass
        return self._agent_ok({"tasks": tasks, "managed": managed, "bills": bills,
                               "pool": pool, "sites": sites}, t0)

    # ------------------------------------------------------------------ 判定
    @staticmethod
    def _agent_parse_hashes(hashes: str) -> Optional[List[str]]:
        """把逗号分隔的 hex 解析成小写 hash 列表；空/非法返回 None。"""
        hs = [h.strip().lower() for h in str(hashes or "").split(",") if h.strip()]
        if not hs:
            return None
        for h in hs:
            if len(h) not in (40, 64) or any(c not in _HEX for c in h):
                return None
        return hs

    def _decide_one(self, h: str, snap: Dict[str, Any], ledger: Dict[str, Any],
                    manual: set, crossseed: set, claim: set) -> Dict[str, Any]:
        """合成单个 hash 的判定（只读现有真值源，不新增真值）。

        判定口径与物理删除闸门 ``_delete_gate_detail`` **同源**（手动保留 / 跨站来源份 /
        已认领 / 欠 H&R）。这里的 ``reason_chain`` 只是把闸门/账本的结论转成结构化链。

        TODO（P1.5b）：软保护（库内资产 / 同站纳管）与「未下完」属 ``_protection_sets``
        的策略级口径（需任务上下文），本端点（hash 寻址、无任务上下文）暂不含入。
        """
        t = snap.get(h)
        rec = ledger.get(h) or {}
        now = self._agent_now()
        name = str(getattr(t, "title", "") or "")
        if not name:
            name = str(rec.get("title") or "")
        state = str(getattr(t, "state", "") or "").strip() or "unknown"
        try:
            progress = float(getattr(t, "progress", 1.0) or 0.0)
        except (TypeError, ValueError):
            progress = 1.0
        entry: Dict[str, Any] = {
            "hash": h, "name": name[:200], "state": state,
            "progress": round(progress, 4),
            "verdict": "keep", "reason_chain": [], "bills": [], "protection": [],
        }
        blocked = False
        if h in manual:
            blocked = True
            entry["protection"].append({"scope": "manual"})
            entry["reason_chain"].append({
                "rule": "delete_gate/manual_protect", "verdict": "block",
                "inputs": {"manual": True},
                "source_of_truth": "task_states.json:protected_torrents", "at": now,
            })
        if h in crossseed:
            blocked = True
            entry["protection"].append({"scope": "crossseed_source"})
            entry["reason_chain"].append({
                "rule": "delete_gate/crossseed_source", "verdict": "block",
                "inputs": {"crossseed": True},
                "source_of_truth": "crossseed_source_hashes()", "at": now,
            })
        if h in claim:
            blocked = True
            entry["protection"].append({"scope": "claim"})
            entry["reason_chain"].append({
                "rule": "delete_gate/claim", "verdict": "block",
                "inputs": {"claimed": True},
                "source_of_truth": "claim_protected_hashes()", "at": now,
            })
        if t is not None:
            try:
                owed, need, seeded, src = self._hr_obligation("", t, snap=snap)
            except Exception:  # noqa: BLE001
                owed, need, seeded, src = False, 0.0, 0.0, "err"
            if owed:
                blocked = True
                entry["protection"].append({"scope": "hr_bill"})
                entry["reason_chain"].append({
                    "rule": "hr/bill", "verdict": "block",
                    "inputs": {
                        "site": str(rec.get("site") or ""),
                        "seeded_h": round(float(seeded or 0.0), 1),
                        "need_h": round(float(need or 0.0), 1),
                        "src": str(src or ""),
                    },
                    "source_of_truth": ("hr_bills.json" if str(src) == "hrbill"
                                        else "resource ledger (mf_resource hrs)"),
                    "at": now,
                })
        # 账单（bills store 单条；欠债/已结清/作废都照实回，不自己判）
        bill = None
        try:
            bill = self._hrbills_store().get(h)
        except Exception:  # noqa: BLE001
            bill = None
        if bill:
            entry["bills"].append(self._agent_bill_view(h, bill))
        if blocked:
            entry["verdict"] = "blocked"
        elif t is not None or h in ledger:
            entry["verdict"] = "delete_candidate"
        return entry

    def agent_decide(self, hashes: str = "") -> Dict[str, Any]:
        """``GET /agent/decide?hashes=a,b`` —— 每个 hash 为什么（Q1/Q4）。

        一整批只拉**一次** qB 快照（同一轮内复用），传给 ``_hr_obligation``；
        不逐种重拉。
        """
        t0 = time.time()
        hs = self._agent_parse_hashes(hashes)
        if hs is None:
            return self._agent_err(
                "bad_param", "hashes 需要 40/64 位 hex（逗号分隔，必填）", t0, field="hashes")
        snap: Dict[str, Any] = {}
        try:
            snap = self._tag_all_torrents() or {}
        except Exception:  # noqa: BLE001
            snap = {}
        ledger: Dict[str, Any] = {}
        try:
            ledger = dict(self._tag_state().items() or {})
        except Exception:  # noqa: BLE001
            ledger = {}
        manual = self._agent_manual_hashes()
        crossseed = self._agent_crossseed_hashes()
        claim = self._agent_claim_hashes()
        items = [self._decide_one(h, snap, ledger, manual, crossseed, claim) for h in hs]
        return self._agent_ok({"items": items}, t0)

    # ------------------------------------------------------------------ 账单
    @staticmethod
    def _agent_filter_bills(all_bills: Dict[str, Any], site: str, state: str,
                            rule: str) -> List[tuple]:
        """过滤 + 按 hash 字典序排序（分页游标依赖稳定顺序）。"""
        out: List[tuple] = []
        for h, b in (all_bills or {}).items():
            if not isinstance(b, dict):
                continue
            if site and str(b.get("site") or "") != site:
                continue
            if state and str(b.get("state") or "") != state:
                continue
            if rule and str(b.get("rule") or "") != rule:
                continue
            out.append((str(h).strip().lower(), b))
        out.sort(key=lambda x: x[0])
        return out

    def agent_bills(self, site: str = "", state: str = "", rule: str = "",
                    limit: int = DEFAULT_LIMIT, cursor: str = "") -> Dict[str, Any]:
        """``GET /agent/bills`` —— 分页账单。

        游标 = 上一页最后一条的 hash（字典序）。``next_cursor`` 非空时用它取下一页；
        空 → 已到末页。
        """
        t0 = time.time()
        try:
            all_bills = self._hrbills_store().all()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"读账单失败:{e}", t0, trace_id=str(e))
        items = self._agent_filter_bills(all_bills, site, state, rule)
        # 游标：只取 hash 严格大于 cursor 的（字典序）
        cursor = str(cursor or "").strip().lower()
        if cursor:
            items = [x for x in items if x[0] > cursor]
        try:
            limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        page = items[:limit]
        next_cursor = page[-1][0] if len(items) > limit else None
        data = {
            "items": [self._agent_bill_view(h, b) for h, b in page],
            "next_cursor": next_cursor,
            "total": len(items),
        }
        return self._agent_ok(data, t0)

    def agent_bill(self, hash: str = "") -> Dict[str, Any]:
        """``GET /agent/bills/{hash}`` —— 单条账单（含 opened_by/opened_at/void_reason）。"""
        t0 = time.time()
        h = str(hash or "").strip().lower()
        if not h:
            return self._agent_err("bad_param", "hash 路径参数必填", t0, field="hash")
        if len(h) not in (40, 64) or any(c not in _HEX for c in h):
            return self._agent_err("bad_param", f"hash 非法（需要 40/64 位 hex）：{h[:16]}…",
                                   t0, field="hash")
        try:
            bill = self._hrbills_store().get(h)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"读账单失败:{e}", t0, trace_id=str(e))
        if not bill:
            return self._agent_err("not_found", "账单不存在", t0)
        return self._agent_ok(self._agent_bill_view(h, bill), t0)

    # ------------------------------------------------------------------ 快照轮
    def agent_snapshot(self) -> Dict[str, Any]:
        """``GET /agent/snapshot`` —— 快照轮观测（复用 common.decision_round_stats）。"""
        t0 = time.time()
        try:
            stats = decision_round_stats()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"快照轮观测失败:{e}", t0, trace_id=str(e))
        return self._agent_ok(stats, t0)

    # ---------------------------------------------------- 11.8.0 站点 myhr 对账（只读）
    def agent_hr_reconcile(self, site: str = "", live: int = 0) -> Dict[str, Any]:
        """``GET /agent/hr/reconcile`` —— ★ **站点 myhr 三方对账**（第三视角，只读）。

        一次调用答：**「站点觉得我们欠哪些 H&R、本机到底有没有、账本记了没」**。

        - 默认**不联网**：返回上一轮（每 6h 由「标签账本维护」worker 跑）的缓存结果；
        - ``live=1`` → 现在真抓一轮（仍**只读**，不写任何账单/不删任何种）；
        - 语义（pro 评审定，硬约束）：**站点页只能判「还欠」，绝不判「已结清」** ——
          settled 只归 ``_hrbills_tick`` 的保守口径；本端点不产 settle 判定。
        - 写出口：``write.add_missing``（需 ``confirm=1``，**同站重下**，只加不删）。

        真值源：站点 ``myhr.php``（≥） + 下载器快照 + ``hr_bills.json``；``hr_reconcile.json``
        是**派生缓存**（tid→infohash / 退避 / 上次报告），**不是真值源**。
        """
        t0 = time.time()
        try:
            if int(live or 0):
                data = self._hr_reconcile_round(force=True)
            else:
                data = self._hr_reconcile_report(str(site or ""))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"站点 H&R 对账失败:{e}", t0, trace_id=str(e))
        payload = dict(data or {})
        payload["write"] = {
            "run_now": "GET /agent/hr/reconcile?live=1",
            "add_missing": ("GET /tags?action=hr_reconcile&site=<domain>&tids=<tid,tid>"
                            "&confirm=1（默认干跑；同站重下，只加不删）"),
            "note": "site 缺省=全部 hr=True 站；重下前逐条人工确认（流量 2~5GB/条）",
        }
        return self._agent_report(
            payload, t0,
            ("hrbills._hr_reconcile_site() → 站点 myhr.php + 下载器快照 + hr_bills.json；"
             "缓存 hr_reconcile.json（派生，非真值源）"))

    # ---------------------------------------------------- 11.10.0 站点级种子报表（只读）
    def agent_site_seeds(self, site: str = "", live: int = 0) -> Dict[str, Any]:
        """``GET /agent/site/seeds`` —— ★ **站点级种子报表**（只读）。

        一次调用答：**「某站点上，我们挂的各种种子现在都是什么状态」**。

        - 逐条种子：hash / 标题 / 体积 / 保存目录 / qB 状态 / 进度 / 比例 / 上传 / 分类桶 /
          是否保护 / 账单 / H&R 需做种时间；
        - 分类桶：欠H&R / 未完成 / 暂停 / 静默 / 保护 / 普通；
        - 汇总：按桶 / 按 qB 状态计数 + 体积 + H&R 欠账摘要（owed / in_qb / missing）；
        - ``site`` 可空 → 只回 ``available_sites``（供选择器）；
        - ``live=1`` → 现抓站点 H&R 对账（否则读上一轮缓存）。

        真值源：下载器快照 + ``hr_bills.json`` + 站点 ``myhr.php``（经 ``_hr_reconcile_site``）；
        本端点**只读**：不写下载器 / 不写账本 / 不新增缓存。
        """
        t0 = time.time()
        try:
            data = self._site_seed_report(str(site or ""), int(live or 0))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"站点报表失败:{e}", t0, trace_id=str(e))
        payload = dict(data or {})
        payload["write"] = {
            "run_now": "GET /agent/hr/reconcile?site=<domain>&live=1（刷新 H&R 对账）",
            "note": "本站点报表只读；补种 / 开账 / 轮换见 /agent/hr/reconcile、/agent/bills",
        }
        return self._agent_report(
            payload, t0,
            ("features/sitereport._site_seed_report() → 下载器快照 + hr_bills.json + "
             "站点 myhr.php（经 _hr_reconcile_site）"))

    # ---------------------------------------------------- 11.12.0 代码字典（只读）
    def agent_code_dict(self, q: str = "", section: str = "", full: int = 0) -> Dict[str, Any]:
        """``GET /agent/code-dict`` —— ★ **代码字典**（符号级索引，只读）。

        一次调用答：**「某常量 / 函数 / 端点 / 口径在哪个文件哪一行」**，排查/运维不必翻源码。

        - 默认 → 概览（各节计数 + 用法）；
        - ``q=<子串>`` → 模糊匹配（符号 / 常量 / 端点 / 模块职责 / 口径）；
        - ``section=endpoints|constants|symbols|modules|glossary`` → 回该整节；
        - ``full=1`` → 回全部（大，慎用）。

        真值源：**插件自身源码**（运行时 ``ast`` 现算，永远与线上代码一致）+ ``codedict.GLOSSARY``
        （手维护口径）。本端点**只读**：不写任何 json / 账本 / 热层。
        """
        t0 = time.time()
        try:
            from ..codedict import build_dict as _build, plugin_root as _proot
            data = _build(_proot(), endpoints=_agent_endpoints(),
                          q=str(q or ""), section=str(section or ""),
                          full=bool(int(full or 0)))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"代码字典失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("插件自身源码（ast 现算）+ codedict.GLOSSARY（手维护口径）"))

    # ---------------------------------------------------- 11.11.0 H&R 账单按站 + 违约告警（只读）
    def agent_hr_bills(self, site: str = "", live: int = 0) -> Dict[str, Any]:
        """``GET /agent/hr/bills`` —— ★ **H&R 账单按站分组**（只读）。

        一次调用答：**「各站欠多少债 / 账单状态分布 / 有没有种在 qB / 缺了没」**。
        只读：欠债数 / 状态分布(active/pending/settled/void/breached) / need_left / in_qb /
        missing / per_torrent_hr 站标 / 规则来源。与 ``GET /hr/bills`` 同源（人机同源）。
        """
        t0 = time.time()
        try:
            data = self._hr_bills_by_site(str(site or ""), int(live or 0))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"H&R账单失败:{e}", t0, trace_id=str(e))
        payload = dict(data or {})
        payload["write"] = {
            "void": "GET /tags?action=hrbills_void&hash=<h>&reason=..&confirm=1",
            "reconcile": "GET /agent/hr/reconcile?site=<dom>&live=1",
            "breaches": "GET /agent/hr/breaches",
        }
        return self._agent_report(
            payload, t0,
            ("features/sitereport._hr_bills_by_site() → hr_bills.json + 下载器快照 + "
             "_site_rules() + 对账缓存（只读）"))

    def agent_hr_breaches(self) -> Dict[str, Any]:
        """``GET /agent/hr/breaches`` —— ★ **H&R 违约告警清单**（只读）。

        一次调用答：**「哪些欠 H&R 的种从下载器消失了，谁删的（本插件/外部）」**。
        归因：deletions.jsonl 命中 ok=true → 本插件删（gate bug 升级 critical）；否则外部删。
        只读：不写任何账单/账本；补回走 write.reseed / write.rescue（需 confirm=1）。
        """
        t0 = time.time()
        try:
            data = self._hr_breaches()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"H&R违约清单失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("features/hrbills._hr_breaches() → hr_bills.json + deletions.jsonl + "
             "下载器快照（只读，归因不造第二真值）"))

    def agent_silent_audit(self, limit: int = 0) -> Dict[str, Any]:
        """``GET /agent/silent/audit`` —— ★ **静默池盘点**（只读）。

        一次调用答：**「静默池里各种怎么分类（欠H&R/资产/跨站/认领/手动/清理候选）+ 谁违背不变量」**。
        纯只读，判据与 ``_delete_gate`` 同源（``_hr_obligation`` + 保护集）。
        """
        t0 = time.time()
        try:
            data = self._silent_audit(int(limit or 0))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"静默池盘点失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("features/silent._silent_audit() → tag_state(账本) + 下载器快照 + "
             "_hr_obligation + 保护集（只读）"))

    def agent_silent_enforce(self, confirm: int = 0) -> Dict[str, Any]:
        """``GET /agent/silent/enforce`` —— ★★ **静默不变量收敛**（写；默认干跑）。

        一次调用答：**「静默池里有多少种违背『全 paused』不变量、这次补了几个 pause」**。
        设计口径（11.11.0）：「静默池本意就是暂停不上传」；「库内资产」只保证**永不删**（删除闸门
        第 5 类硬拦），**不保证在做种**。收敛是幂等的、只 pause（不删种、不动文件、不 resume）。
        ``confirm=0``（默认）= 只清单零写入；``confirm=1`` = 真补 pause。
        """
        t0 = time.time()
        try:
            data = self._silent_enforce_pause(apply=bool(int(confirm or 0)))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"静默不变量收敛失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("features/silent._silent_enforce_pause() → _silent_audit(stalled_violation, 只读) + "
             "_silent_pause_gate → DownloaderAdapter.pause_torrents(只 pause，不删)"))

    # ---------------------------------------------------- 11.9.0 野马PT 逐种 H&R（只读 + 免罪写）
    def agent_yema(self, live: int = 0, force: int = 0) -> Dict[str, Any]:
        """``GET /agent/yema`` —— ★ **野马PT 逐种 H&R 对账**（站点 × 本机 × 账本；只读）。

        一次调用答：**「野马说我欠哪些种（逐种开关）、本机挂着没、账本记了没」**。

        - 野马PT **没有站点级 H&R 规则**：H&R 是发布者**逐种**开关 ``hrPunishEnable``
          （Master 2026-10-05 定论）→ 唯一权威来源是站点后台接口；
        - ``live=1`` 联机拉一轮（列分页 + 必要时拉 .torrent 算 infohash）；默认读缓存；
        - 语义：站点**只能判「还欠」**；``settled`` 只归 ``seed_hours_for_hr`` → 本端点不产 settled、不自动作废；
        - 三桶：``missing_local``（站点说欠、本机没有 = **违规风险**）/
          ``present_no_bill``（本机有、站点说欠、账本没记 = 可补开账单）/
          ``unknown_bills``（账本 rule=unknown，可能漏记）。
        - 写出口：``write.open_bills``（补开账单，只增保护）、``write.absolve``（免罪，扣分不可逆）。
        """
        t0 = time.time()
        try:
            data = self._yema_reconcile(live=int(live or 0), force=int(force or 0))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"野马PT 逐种 H&R 对账失败:{e}", t0, trace_id=str(e))
        payload = dict(data or {})
        payload["write"] = {
            "open_bills": ("GET /tags?action=yema&confirm=1（默认干跑；给「本机有+站点说欠+账本没记」的种"
                           "补开账单，只增保护）"),
            "absolve": "GET /agent/yema/absolve?tid=<tid>&confirm=1（扣积分、不可逆；默认干跑）",
            "note": "missing_local 需同站重下（流量 2~5GB/条）→ 逐条人工；本端点绝不自动删种。",
        }
        return self._agent_report(
            payload, t0,
            ("features/yema.py → 站点 /api/torrent/fetchUserTorrentList（cookie）"
             " + GET /api/torrent/download?id= 算 infohash + 下载器快照 + hr_bills.json；"
             "缓存 hr_reconcile.json（派生）"))

    def agent_yema_absolve(self, tid: str = "", confirm: int = 0) -> Dict[str, Any]:
        """``GET /agent/yema/absolve`` —— ★ 野马PT「免罪」（**写**：扣积分、不可逆）。

        默认**干跑**：只报目标行 + 成本说明；``confirm=1`` 才真调站点
        ``POST /api/userTorrent/absolve``。逐条人工（不做批量、不做自动）。
        """
        t0 = time.time()
        try:
            data = self._yema_absolve(tid, confirm=int(confirm or 0))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"野马PT 免罪失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            dict(data or {}), t0,
            "features/yema.py::_yema_absolve → POST /api/userTorrent/absolve（干跑/写）")

    # ---------------------------------------------------- 12.5.0 挂种健康度自检（只读）
    def agent_seeds_health(self, site: str = "", only: str = "", limit: int = 200) -> Dict[str, Any]:
        """``GET /agent/seeds/health`` —— ★ **挂种健康度自检**（只读）。

        一次调用答：**「哪些挂种在空转 / 缺文件、占多少体积、其中哪些还欠 H&R（风险）」**。
        两段式：顶层 listing 粗筛 → 逐文件 ``os.path.exists`` 精确（含 qB 临时路径）。
        与 UI ``GET /health/scan`` **同源**（同一个 ``_health_scan``，人机同源）。
        零写入：不 recheck / 不改 qB / 不写账本 / 不动文件。
        """
        t0 = time.time()
        try:
            data = self._health_scan(str(site or ""), str(only or ""), int(limit or 200))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"挂种健康度自检失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("features/health._health_scan() → qB 快照 + torrents/files（逐文件 os.path.exists）"
             " + hr_bills.json（只读）"),
            inputs={"site": str(site or ""), "only": str(only or ""), "limit": limit})

    # ---------------------------------------- 12.7.0 调试面自描述（只读）
    def agent_debug_surface(self) -> Dict[str, Any]:
        """``GET /agent/debug/surface`` —— ★ **调试面自描述**（只读）。

        一次调用答：「有哪些 ``/debug`` 端点 / 哪些会写 / 写操作要求什么 / 读文件白名单与敏感文件黑名单」。
        真值源 = **路由表**（``get_api()`` 的 ``/debug*`` 子集）+ **写标记表**（``DEBUG_WRITE_PATHS``）；
        不另建一份清单。零写入。
        """
        t0 = time.time()
        try:
            from .debug import DEBUG_WRITE_PATHS, _DBG_READ_ROOTS  # noqa: WPS433
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"调试面不可用:{e}", t0, trace_id=str(e))
        try:
            routes = super().get_api() or []
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"路由表不可用:{e}", t0, trace_id=str(e))
        items: List[Dict[str, Any]] = []
        for r in routes:
            p = str(r.get("path") or "")
            if not p.startswith("/debug"):
                continue
            note = str(DEBUG_WRITE_PATHS.get(p) or "")
            items.append({
                "path": p,
                "endpoint": str(getattr(r.get("endpoint"), "__name__", "") or ""),
                "methods": [str(m) for m in (r.get("methods") or [])],
                "summary": str(r.get("summary") or ""),
                "write": bool(note),
                "write_note": note,
                "confirm_param": "confirm=1" if note else "",
            })
        items.sort(key=lambda x: x["path"])
        data = {
            "count": len(items),
            "write_count": sum(1 for i in items if i["write"]),
            "items": items,
            "policy": {
                "confirm": "所有写操作需显式 confirm=1，缺省直接拒绝（防误触 / 防 GET 副作用）",
                "read_roots": list(_DBG_READ_ROOTS),
                "sensitive_deny": "app.env / *.env / *token* / *cookie* / *.pem / *.key / id_rsa … 一律不可读",
            },
        }
        return self._agent_report(
            data, t0,
            "features/api.get_api()（/debug* 冒牌子集） + features/debug.DEBUG_WRITE_PATHS（写标记）",
            inputs={})
