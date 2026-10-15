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
    site_type_rows,
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
         "summary": "能力清单（所有 AI 端点的自描述）"},
        {"path": "/agent/state", "method": "GET", "handler": "agent_state", "write": False,
         "params": {}, "returns": "AgentState", "version": AGENT_ENDPOINT_VERSION,
         "summary": "有多少任务在跑、多少欠账：运行计数（任务/托管/账单/池/站点）"},
        {"path": "/agent/decide", "method": "GET", "handler": "agent_decide", "write": False,
         "params": {"hashes": "hex[] 逗号分隔（必填，40/64 位）",
                    "task_id": "任务 id（可选；给了就带任务级口径：软/硬保护 + 阈值评分）"},
         "returns": "DecideReport",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "这颗种为什么留着、该不该删：判决 + 完整决策链 + 账单 + 保护依据"},
        {"path": "/agent/cleanup/preview", "method": "GET", "handler": "agent_cleanup_preview",
         "write": False, "params": {"task_id": "任务 id（必填）"},
         "returns": "CleanupPreview", "version": AGENT_ENDPOINT_VERSION,
         "summary": "这个任务本轮会删哪些：删种名单预览（只算不删，同真闸门保护集）"},
        {"path": "/agent/optimize", "method": "GET", "handler": "agent_optimize",
         "write": False, "params": {"task_id": "任务 id（必填）",
                                    "budget_gb": "保留体积预算(GB,可选;缺省=保留≥95%时魔的最小预算)"},
         "returns": "OptimizePlan", "version": AGENT_ENDPOINT_VERSION,
         "summary": "容量就这么多，保哪些最划算：预算下时魔最优组合（只算不删，含阈值对比）"},
        {"path": "/agent/plan", "method": "GET", "handler": "agent_plan", "write": False,
         "params": {"action": "cleanup|optimize（必填）", "task_id": "任务 id（必填）",
                    "budget_gb": "仅 optimize：保留体积预算(GB,可选;缺省=保留≥95%时魔的最小预算)"},
         "returns": "Plan", "version": AGENT_ENDPOINT_VERSION,
         "summary": "要删/优化哪些，先出可复核计划：条目 + plan_id（只算不删）"},
        {"path": "/agent/plan/apply", "method": "POST", "handler": "agent_plan_apply", "write": True,
         "params": {"plan_id": "计划内容哈希（必填，来自 /agent/plan）", "action": "cleanup|optimize",
                    "task_id": "任务 id", "budget_gb": "仅 optimize",
                    "delete_files": "-1=按任务配置|0=保文件|1=删文件（默认 -1）",
                    "confirm": "1=真执行；0/缺省=干跑（零写入）"},
         "returns": "PlanApply", "version": AGENT_ENDPOINT_VERSION,
         "summary": "批准并执行那份计划：比对 plan_id、过唯一删种闸门"},
        {"path": "/agent/bills", "method": "GET", "handler": "agent_bills", "write": False,
         "params": {"site": "domain", "state": "active|settled|pending|void",
                    "rule": "site_hr|hit_and_run|unknown", "limit": "int（默认 50）",
                    "cursor": "下一页游标（回填上一次返回的 next_cursor）"},
         "returns": "BillPage", "version": AGENT_ENDPOINT_VERSION,
         "summary": "欠不欠债、欠在哪些站/哪种：H&R 账单分页（可按 site/state/rule 过滤）"},
        {"path": "/agent/bills/{hash}", "method": "GET", "handler": "agent_bill", "write": False,
         "params": {"hash": "hex 路径参数（40/64 位）"}, "returns": "Bill",
         "version": AGENT_ENDPOINT_VERSION, "summary": "单条账单详情"},
        {"path": "/agent/snapshot", "method": "GET", "handler": "agent_snapshot", "write": False,
         "params": {}, "returns": "SnapshotRound", "version": AGENT_ENDPOINT_VERSION,
         "summary": "每轮决策的快照拉取次数/耗时观测"},
        {"path": "/agent/rescue", "method": "GET", "handler": "agent_rescue", "write": False,
         "params": {}, "returns": "RescueReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "哪些种快没源了：补源目标（停滞/欠 H&R/手动保留的未下完种）"},
        {"path": "/agent/rescue/candidates", "method": "GET", "handler": "agent_rescue_candidates",
         "write": False,
         "params": {"hashes": "逗号分隔 hash（可空=全部目标）", "verify": "1|0（默认 1；会联网拉候选 .torrent 做指纹校验）"},
         "returns": "RescueCandidatesReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "这些种从哪能补到源：候选（IYUU 指纹索引 + 落地校验，不写下载器）"},
        # ---- P1.5b：真值源直出 + 字段字典 + 报表层首批（handler 在 AgentLedgerMixin）----
        {"path": "/agent/ledger/{table}", "method": "GET", "handler": "agent_ledger", "write": False,
         "params": {"table": "site|resource|identity|task|seed|deck|crossseed|bills|deletions|journal|protected|rescue_actions|reseed|run|claim",
                    "limit": "int（默认 50，0=全量）", "cursor": "下一页游标（回填 next_cursor）",
                    "filter": "k=v 逗号分隔（如 site=/state=/rule=）",
                    "fields": "逗号分隔字段投影"}, "returns": "LedgerPage",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "查真值台账原文：站点/资源/做种/删除/日志等表（分页/过滤/字段投影）"},
        {"path": "/agent/schema", "method": "GET", "handler": "agent_schema", "write": False,
         "params": {}, "returns": "SchemaReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "字段字典：所有返回类型 + 真值表字段/类型/单位/枚举/可空"},
        {"path": "/agent/overview", "method": "GET", "handler": "agent_overview", "write": False,
         "params": {}, "returns": "Overview", "version": AGENT_ENDPOINT_VERSION,
         "summary": "整体现在什么情况：任务/站点/账单/池 概览数字"
                    "（注意：无参数可缩，实测约 48KB —— 超过 MCP 单次 30k 上限会被截断，截断结果是残的，"
                    "别当全量；细项改用 /agent/state、/agent/health、/agent/jobs、/agent/bills）"},
        {"path": "/agent/tasks", "method": "GET", "handler": "agent_tasks", "write": False,
         "params": {"type": "all|real|host（默认 all；real=排除伪任务；host=只看伪任务；"
                    "real/all 约 36KB 会超 30k 被截断 —— 单任务细节请用 /agent/tasks/{id}）"},
         "returns": "TaskList", "version": AGENT_ENDPOINT_VERSION,
         "summary": "有哪些任务、哪些是伪任务：任务列表（run_mode/站点/统计 + is_host 标注）"},
        {"path": "/agent/tasks/{id}", "method": "GET", "handler": "agent_task_detail", "write": False,
         "params": {"id": "任务 id 路径参数"}, "returns": "TaskDetail",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "某个任务怎么配的、最近干了什么：任务详情（配置 + 候选/种子/操作摘要）"},
        {"path": "/agent/operations", "method": "GET", "handler": "agent_operations", "write": False,
         "params": {"limit": "int（默认 50）", "cursor": "下一页游标（回填 next_cursor）",
                    "task": "任务 id", "action": "操作类型(kind)"},
         "returns": "OperationsPage", "version": AGENT_ENDPOINT_VERSION,
         "summary": "谁在什么时候删/加了什么：跨任务操作流水（可按 task/action 过滤）"},
        {"path": "/agent/pool", "method": "GET", "handler": "agent_pool", "write": False,
         "params": {"path": "任务保存目录（可选）"}, "returns": "PoolReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "池和磁盘还够不够：池容积 + 磁盘水位 + 预算"},
        {"path": "/agent/trend", "method": "GET", "handler": "agent_trend", "write": False,
         "params": {"scope": "all|task|site", "id": "任务/站点 id", "hours": "int（默认 72）"},
         "returns": "TrendReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "每小时魔力趋势"},
        {"path": "/agent/notify", "method": "GET", "handler": "agent_notify", "write": False,
         "params": {"limit": "int（默认 50）"}, "returns": "NotifyReport",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "通知发没发出去、都发过什么：配置 + 最近事件 + 计数"},
        {"path": "/agent/notify/act", "method": "POST", "handler": "agent_notify_act", "write": True,
         "params": {"action": "test|scan|clear", "text": "测试通知正文（可选）"},
         "returns": "NotifyActReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "测通知/立即扫描/清历史：通知运维动作（即时生效）"},
        {"path": "/agent/trend/daily", "method": "GET", "handler": "agent_trend_daily", "write": False,
         "params": {"scope": "site|task|all（默认 site）", "id": "任务/站点 id", "days": "int（默认 30）"},
         "returns": "TrendDailyReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "长期每天怎么走的：日报趋势（持久化 180 天）"},
        {"path": "/agent/trend/why", "method": "GET", "handler": "agent_trend_why", "write": False,
         "params": {"scope": "site|task", "id": "站点 id 或任务 id（必填；缺了报 bad_param）",
                    "hours": "int 对比窗口（默认 72）"},
         "returns": "TrendExplainReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "魔力为什么涨/跌：时魔因子拆解 + 结论 + 建议"},
        {"path": "/agent/rules", "method": "GET", "handler": "agent_rules", "write": False,
         "params": {}, "returns": "RulesReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "站点规则（H&R / 做种时长 / 来源）"},
        {"path": "/agent/settings", "method": "GET", "handler": "agent_settings", "write": False,
         "params": {}, "returns": "SettingsReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "现在是什么配置：设置 + 默认模板 + 下载器参数"},
        {"path": "/agent/health", "method": "GET", "handler": "agent_health", "write": False,
         "params": {}, "returns": "HealthReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "有没有出事、哪个子系统不健康：自检结论 + 待处理项"},
        {"path": "/agent/blindspot", "method": "GET", "handler": "agent_blindspot", "write": False,
         "params": {}, "returns": "HrBlindspotReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "H&R 有没有漏记/漏标：盲区种 + 补源禁用站"},
        {"path": "/agent/hr/per-torrent", "method": "GET", "handler": "agent_hr_per_torrent",
         "write": False,
         "params": {}, "returns": "PerTorrentHrReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "逐种 H&R 账单审计（按 rule/state 摊开；unknown=可能漏记）"},
        {"path": "/agent/hr/reconcile", "method": "GET", "handler": "agent_hr_reconcile",
         "write": False,
         "params": {"site": "站点域名（可空=全部 hr=True 站）", "live": "1=现在就真抓一轮（默认只读上次结果）"},
         "returns": "HrReconcileReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "站点 myhr 三方对账（站点欠 × 本机有无 × 账本）；只判「还欠」"},
        {"path": "/agent/yema", "method": "GET", "handler": "agent_yema", "write": False,
         "params": {"live": "1=联机对账（拉站点后台接口）；默认读上一轮缓存",
                    "force": "1=忽略缓存强拉"},
         "returns": "YemaReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "野马PT 逐种 H&R 对账：漏挂/漏记可见（可现抓，不产 settled）"},
        {"path": "/agent/yema/absolve", "method": "GET", "handler": "agent_yema_absolve", "write": True,
         "params": {"tid": "站点 torrentId（必填）", "confirm": "1=真写（默认干跑，只报成本）"},
         "returns": "YemaAbsolve", "version": AGENT_ENDPOINT_VERSION,
         "summary": "野马PT 免罪（扣积分不可逆）：默认只报成本"},
        {"path": "/agent/site/seeds", "method": "GET", "handler": "agent_site_seeds",
         "write": False,
         "params": {"site": "站点域名 / 短名 / id（可空 = 只回站点清单）",
                    "live": "1 = 现抓站点 H&R 对账（同 /agent/hr/reconcile）"},
         "returns": "SiteSeedsReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "某站做种/H&R 现状如何：六桶职务/身份 + 传输三态 + H&R 摘要"},
        # ---- 17.3.0 报表统一入口（唯一口径：账本为真值 + 全量 + 互校）----
        {"path": "/agent/report", "method": "GET", "handler": "agent_report", "write": False,
         "params": {"view": "site|silent|hr|rows（默认 site）",
                    "site": "站点域名 / 短名 / id（site/hr/rows 视图用）",
                    "state": "刷流|魔力|保种|静默（账本职务轴，可选）",
                    "bucket": "刷流|魔力|保种|静默|补源|外部（可选）",
                    "sub": "新|资源|普通（静默身份轴，可选）",
                    "origin": "池|辅种副本|无主（可选）",
                    "transport": "做种中|暂停|未完成|不在下载器（可选）",
                    "hr": "1=欠 H&R / 0=不欠 / unclassified=未定性账单（可选）",
                    "protected": "1=只保护 / 0=只未保护（可选）",
                    "limit": "int（默认 200；0=全部）", "offset": "int（默认 0）",
                    "live": "1=现抓站点 H&R 对账（site/hr 视图用）"},
         "returns": "Report", "version": AGENT_ENDPOINT_VERSION,
         "summary": "统一报表：一行=一颗种（站/静默池/账单/全量四视图同口径，参数非法即报错）"},
        {"path": "/agent/report/drift", "method": "GET", "handler": "agent_report_drift",
         "write": False, "params": {},
         "returns": "ReportDrift", "version": AGENT_ENDPOINT_VERSION,
         "summary": "报表互校：账本 × 下载器 × MP 站点 × 账单（幽灵/未纳管/站点缺失）"},
        # ---- 15.9.0 站点「分类类型」映射（只读，★ 类型真值一律用 MP）----
        {"path": "/agent/sites/types", "method": "GET", "handler": "agent_sites_types",
         "write": False, "params": {},
         "returns": "SiteTypes", "version": AGENT_ENDPOINT_VERSION,
         "summary": "站点分类类型映射（逐站 movie/tv/music 分类 id；真值来自 MP）"},
        # ---- 16.0.0 站点已删除（MP 侧删站后的善后：识别 + 牵连面 + 行内处置）----
        {"path": "/agent/sites/deleted", "method": "GET", "handler": "agent_sites_deleted",
         "write": False, "params": {},
         "returns": "DeletedSites", "version": AGENT_ENDPOINT_VERSION,
         "summary": "哪些站被删了、牵连多少种：已删站 + 只剩账单/账本残留的站（真值=全部站点引用−MP 站点表）"},
        {"path": "/agent/sites/deleted/act", "method": "POST", "handler": "agent_sites_deleted_act",
         "write": True,
         "params": {"site_id": "台账 site_id / mp_site_id / **域名**（只剩账单残留、已无台账行的站只能用域名）",
                    "action": "pause|resume|remove（remove 三档：①复用副本只摘种 ②本体/库内资产只摘种（文件留媒体库）③自有非本体连文件删；摘种走具名 gate_strip 通道，不等同于删库内资产）",
                    "reuse_only": "1=只处理带 魔流-辅种 的复用副本",
                    "dry_run": "1=干跑（默认）；0=真做",
                    "force_asset": "★1=**仅对「连文件删」那一档**改走「手动删库内资产」闸门（跳过第 5 类「库内资产（已入库，永不删）」；其余四类硬保护照拦）；对「只摘种」两档无效（那两档恒走 gate_strip）。默认 0，破坏性"},
         "returns": "SiteDeletedAct", "version": AGENT_ENDPOINT_VERSION,
         "summary": "已删站点的种怎么处置：pause/resume/remove（复用副本与本体只摘种、自有非本体才连文件删）"},
        # ---- 11.11.0 H&R 账单按站 + 违约告警（只读）----
        {"path": "/agent/hr/bills", "method": "GET", "handler": "agent_hr_bills", "write": False,
         "params": {"site": "域名（留空=全站，约 85KB 会被 30k 截断 —— 建议先按站查）",
                    "live": "1=现抓对账（默认读缓存）"},
         "returns": "HrBillsBySite", "version": AGENT_ENDPOINT_VERSION,
         "summary": "各站 H&R 欠债多少、还剩多久：按站分组账单（可现抓对账）"},
        {"path": "/agent/hr/breaches", "method": "GET", "handler": "agent_hr_breaches", "write": False,
         "params": {}, "returns": "HrBreaches", "version": AGENT_ENDPOINT_VERSION,
         "summary": "H&R 违约告警（种消失归因 + gate_bug 升级 + 补源提示）"},
        {"path": "/agent/silent/audit", "method": "GET", "handler": "agent_silent_audit", "write": False,
         "params": {"limit": "int（默认 1000；0=全量）"}, "returns": "SilentAudit", "version": AGENT_ENDPOINT_VERSION,
         "summary": "静默池盘点（分类 + 违背不变量 + 标签面 + 清理候选）"},
        {"path": "/agent/silent/enforce", "method": "GET", "handler": "agent_silent_enforce",
         "write": True,
         "params": {"confirm": "1=真补 pause（默认干跑）"},
         "returns": "SilentEnforce", "version": AGENT_ENDPOINT_VERSION,
         "summary": "账本/标签说静默但 qB 还在跑的，补 pause：幂等只暂停"},
        {"path": "/agent/tags/reconcile", "method": "GET", "handler": "agent_tags_reconcile",
         "write": True,
         "params": {"confirm": "1=真写（默认干跑只报数）",
                    "adopt_reseed": "1=顺带把「无主辅种副本」补登进 mf_reseed",
                    "limit": "int（0=不限）"},
         "returns": "TagReconcileReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "账本在岗但 qB 缺标签的补齐：不删不暂停，漂移只报"},
        {"path": "/agent/qb/snapshot", "method": "GET", "handler": "agent_qb_snapshot",
         "write": False,
         "params": {}, "returns": "QbSnapshot", "version": AGENT_ENDPOINT_VERSION,
         "summary": "qB 增量同步观测（全量/增量次数 + rid + 上次增量大小）"},
        {"path": "/agent/ondemand", "method": "GET", "handler": "agent_ondemand",
         "write": False,
         "params": {"limit": "int（清单条数上限，默认 50，最大 200）"},
         "returns": "OnDemandItems", "version": AGENT_ENDPOINT_VERSION,
         "summary": "点播进行到哪了、历史下过什么：清单（stage/进度/体积 + totals）"},
        {"path": "/agent/ondemand/act", "method": "POST", "handler": "agent_ondemand_act",
         "write": True,
         "params": {"hash": "str（点播种 infohash）", "action": "pause | resume | remove"},
         "returns": "OnDemandAct", "version": AGENT_ENDPOINT_VERSION,
         "summary": "点播条目暂停/恢复/删除：remove 过唯一删种闸门、欠 H&R 硬拦（即时生效）"},
        {"path": "/agent/ondemand/search", "method": "POST", "handler": "agent_ondemand_search",
         "write": False,
         "params": {"query": "str 片名 / 豆瓣·TMDB·IMDB 链接（首页必填；缺了报 bad_param；续页留空）",
                    "site_ids": "逗号分隔站点 id（空=全部已配置站点）",
                    "page": "int 起始页（默认 0）",
                    "source": "str 续页令牌（首页留空；回传上一次 sources[].source 即续该站下一页）"},
         "returns": "OnDemandSearch", "version": AGENT_ENDPOINT_VERSION,
         "summary": "用户要找这个片：各站候选 + 每站翻页事实（can_continue）"},
        {"path": "/agent/ondemand/add", "method": "POST", "handler": "agent_ondemand_add",
         "write": True,
         "params": {"query": "str 片名 / 豆瓣·TMDB·IMDB 链接（必填）",
                    "site_ids": "逗号分隔站点 id（空=全部已配置站点）",
                    "pick": "str 必填 = 候选 enclosure / 下载链接（来自 /agent/ondemand/search 的 candidates[].enclosure）",
                    "task_id": "任务 id（可空；只影响保存目录）",
                    "confirm": "1=真加种；否则只回干跑计划"},
         "returns": "OnDemandAdd", "version": AGENT_ENDPOINT_VERSION,
         "summary": "把用户选定的那条源加进下载器：只下 pick 那条"},
        {"path": "/agent/ondemand/add_direct", "method": "POST", "handler": "agent_ondemand_add_direct",
         "write": True,
         "params": {"url": "str 必填 = 种子链接（details.php?id=N / download.php?id=N / .torrent 直链）",
                    "site_ids": "str 必填且唯一 = 站点 id（取种要用该站 cookie，不猜站点）",
                    "task_id": "任务 id（可空；只影响保存目录）",
                    "confirm": "1=真加种；否则只回干跑计划（干跑也取一次 .torrent 读元数据，不落种）"},
         "returns": "OnDemandAddDirect", "version": AGENT_ENDPOINT_VERSION,
         "summary": "有种子链接但搜不到时直接加：按链接取种落种（不 search、不选源）"},
        {"path": "/agent/music/search", "method": "POST", "handler": "agent_music_search",
         "write": False,
         "params": {"query": "str 关键词（首页必填；缺了报 bad_param；续页留空）",
                    "site_ids": "逗号分隔站点 id（空=全部已配置站点）",
                    "page": "int 起始页（默认 0）",
                    "source": "str 续页令牌（首页留空；回传上一次 sources[].source 即续该站下一页）"},
         "returns": "MusicSearch", "version": AGENT_ENDPOINT_VERSION,
         "summary": "用户要找这个音乐：各站候选（已打分/硬过滤）+ 翻页事实"},
        {"path": "/agent/music/download", "method": "POST", "handler": "agent_music_download",
         "write": True,
         "params": {"cids": "逗号分隔候选 id（来自 /agent/music/search 的 candidates[].cid）",
                    "save_path": "覆盖保存目录（默认 /vol6/1000/music）",
                    "confirm": "1=真加种；否则只回将要加种的清单（干跑）"},
         "returns": "MusicDownload", "version": AGENT_ENDPOINT_VERSION,
         "summary": "按选中的 cid 加种到音乐线（凭据不回传）"},
        {"path": "/agent/music/items", "method": "GET", "handler": "agent_music_items",
         "write": False,
         "params": {"limit": "int 清单条数上限（默认 50，最大 200）"},
         "returns": "MusicItems", "version": AGENT_ENDPOINT_VERSION,
         "summary": "音乐下过哪些、在库什么状态：清单 + totals"},
        {"path": "/agent/music/act", "method": "POST", "handler": "agent_music_act",
         "write": True,
         "params": {"hash": "str（音乐种 infohash）", "action": "pause | resume | remove"},
         "returns": "MusicAct", "version": AGENT_ENDPOINT_VERSION,
         "summary": "音乐种暂停/恢复/删除：仅音乐线，过唯一删种闸门（即时生效）"},
        # ---- 15.8.15 库内资产手动删除（Master「希望增加魔流库内资产手动删除的入口」）----
        #   AI 侧与前端**同口径**：两个 handler 都直接复用 AssetsMixin.assets_library /
        #   assets_delete（AI ⊇ 前端），不另写一套判定。
        {"path": "/agent/assets", "method": "GET", "handler": "agent_assets", "write": False,
         "params": {"view": "summary（默认，瘦身：去 members/长字段）/ full（含全部成员明细）；单份详情用 resource_id",
                    "q": "关键词：匹配资源名或任一成员种名（不区分大小写）",
                    "resource_id": "单份资源详情（= items[].resource_id；给了它忽略 q/sort/分页）",
                    "sort": "size（默认，体积降序）/ sites / members / name",
                    "limit": "int（默认 50；0 = 全部）",
                    "cursor": "分页游标：上次返回的 next_cursor（从第 N 条起）",
                    "group_by": "site = 按站点聚合（每站份数/体积/可删数）",
                    "include_stale": "1=带上「不在下载器（仅账本残留）」条目（默认不显示）"},
         "returns": "AssetList", "version": AGENT_ENDPOINT_VERSION,
         "summary": "库内有哪些资源、哪些能删：一条=一份资源（deletable/block，可筛/排/聚合）"},
        {"path": "/agent/assets/delete", "method": "POST", "handler": "agent_assets_delete",
         "write": True,
         "params": {"resource_ids": "逗号/空格分隔的资源 id（只认库内资产；其余拒收）",
                    "delete_files": "1=连文件一起删（不可恢复）；缺省 0=只删种保文件",
                    "confirm": "1=真删；缺省/非 1 = 干跑（零写入）",
                    "reason": "删除原因（进统一删除台账 mf_deletions）"},
         "returns": "AssetDeleteReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "⚠不可恢复：真删整份库内资产（全组删完才连文件删，只破「永不删」一道闸）"},
        # ---- P1.5c：功能域只读（AI ⊇ 前端，收编 19 个只读豁免域）----
        {"path": "/agent/tasks/{id}/bonus", "method": "GET", "handler": "agent_task_bonus", "write": False,
         "params": {"id": "任务 id 路径参数"}, "returns": "TaskBonusReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "任务做种魔力明细"},
        {"path": "/agent/tasks/{id}/candidates", "method": "GET", "handler": "agent_task_candidates", "write": False,
         "params": {"id": "任务 id 路径参数"}, "returns": "TaskCandidatesReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "任务候选种子及评分"},
        {"path": "/agent/tasks/{id}/handover", "method": "GET", "handler": "agent_task_handover", "write": False,
         "params": {"id": "任务 id 路径参数"}, "returns": "TaskHandoverReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "任务交棒预览"},
        {"path": "/agent/recommend", "method": "GET", "handler": "agent_recommend", "write": False,
         "params": {}, "returns": "RecommendReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "有什么值得订：推荐甄别结果"
                    "（注意：无参数可缩，实测约 255KB —— 超 30k 会被截断，只能看到开头几条）"},
        {"path": "/agent/jobs", "method": "GET", "handler": "agent_jobs", "write": False,
         "params": {"limit": "int 最多返回多少条（默认 50）"},
         "returns": "JobList", "version": AGENT_ENDPOINT_VERSION,
         "summary": "后台慢动作跑到哪了：任务队列（异步执行，关页面不断）"},
        {"path": "/agent/assets/act", "method": "POST", "handler": "agent_assets_act",
         "write": True,
         "params": {"action": "protect=手动保留(永不自动删) / unprotect=取消保留 / "
                              "subscribe=订阅该作品+季(抓齐其余集) / unsubscribe=退订 / "
                              "organize=让 MP 重新整理入库(换个地方) / "
                              "scrape=多源重刮元数据(纠正刮错)",
                    "resource_ids": "资源 id 列表（逗号分隔；= /assets 返回的 resource_id）",
                    "hashes": "兼容：直接给成员 hash（逗号分隔）",
                    "season": "int 可选：强制季号（0=从种名解析）"},
         "returns": "AssetActReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "库内资源保护/订阅/整理/刮削：不删除（即时生效）"},
        {"path": "/agent/recommend/act", "method": "POST", "handler": "agent_recommend_act",
         "write": True,
         "params": {"hash": "推荐记录 infohash（必填）",
                    "action": "subscribe=按「作品+季」给 MP 加整季订阅（手动标记才订） / "
                              "unsubscribe=退订并复位记录"},
         "returns": "RecommendAct", "version": AGENT_ENDPOINT_VERSION,
         "summary": "给推荐记录整季订阅/退订：手动触发（即时生效）"},
        {"path": "/agent/crossseed", "method": "GET", "handler": "agent_crossseed", "write": False,
         "params": {}, "returns": "CrossseedReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "跨站取种在飞什么、来源够不够：取种台账 + 流量兜底"},
        {"path": "/agent/reseed", "method": "GET", "handler": "agent_reseed", "write": False,
         "params": {}, "returns": "ReseedReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "全站辅种现状"},
        {"path": "/agent/douban", "method": "GET", "handler": "agent_douban", "write": False,
         "params": {}, "returns": "DoubanReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "豆瓣评分服务正常吗：服务现状"},
        {"path": "/agent/live", "method": "GET", "handler": "agent_live", "write": False,
         "params": {"site_id": "站点 id（可选）"}, "returns": "LiveReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "站点现在通不通、魔力多少：站点实时采样（PV/下载量）"},
        {"path": "/agent/signin", "method": "GET", "handler": "agent_signin", "write": False,
         "params": {"days": "int（近 N 天，默认 7；默认输出约 34KB 会超 30k 被截断，查近期请 days=1..3）"},
         "returns": "SigninReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "最近签没签到：近 N 天签到现状"},
        {"path": "/agent/exam", "method": "GET", "handler": "agent_exam", "write": False,
         "params": {"site_id": "站点 id（可选）", "include_pass": "是否含已通过（默认否）"},
         "returns": "ExamReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "新手考核过没过、还差多少：进度现状（可含已通过）"},
        {"path": "/agent/exam/act", "method": "POST", "handler": "agent_exam_act", "write": True,
         "params": {"site_id": "站点 id（必填）", "kind": "考核项 upload|bonus|hold（download 不支持）",
                    "confirm": "bool（默认否=干跑；true 才新建/启用任务）"},
         "returns": "ExamAct", "version": AGENT_ENDPOINT_VERSION,
         "summary": "给考核项一键起任务：upload/bonus/hold"},
        {"path": "/agent/silent", "method": "GET", "handler": "agent_silent", "write": False,
         "params": {"limit": "int（名单条数，默认 400；0=全部）",
                    "records": "int（每条明细数，默认 60；0=不带明细）—— 默认全量约 216KB 会被 30k 截断；"
                               "只要名单请 records=0，带少量明细用 records=1"},
         "returns": "SilentReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "静默池里关着哪些种、分几类：在池名单 + 分类"},
        {"path": "/agent/claim", "method": "GET", "handler": "agent_claim", "write": False,
         "params": {"site_id": "站点 id（可选）"}, "returns": "ClaimReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "认领现状"},
        {"path": "/agent/cloud", "method": "GET", "handler": "agent_cloud", "write": False,
         "params": {}, "returns": "CloudReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "云盘归档到哪了、通不通：归档现状 + 连通性"},
        {"path": "/agent/fallback", "method": "GET", "handler": "agent_fallback", "write": False,
         "params": {"resolve_paths": "bool（是否解析路径）"}, "returns": "FallbackReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "元数据兜底现状"},
        {"path": "/agent/iyuu", "method": "GET", "handler": "agent_iyuu", "write": False,
         "params": {}, "returns": "IYUUReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "IYUU 密钥表 + 连通性"},
        {"path": "/agent/events", "method": "GET", "handler": "agent_events", "write": False,
         "params": {"since": "unix 秒（只回更新的；传毫秒自动换算；缺省 0=从头）",
                    "limit": "int（1..1000，默认 200，取最新 N 条；默认约 114KB 会被 30k 截断，建议 ≤20）",
                    "kind": "事件类型，逗号分隔精确匹配", "task_id": "任务 id",
                    "level": "info|warning|error，逗号分隔"},
         "returns": "EventsReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "结构化事件流"},
        {"path": "/agent/tags", "method": "GET", "handler": "agent_tags", "write": False,
         "params": {"action": "只读动作（默认 status）"}, "returns": "TagsReport",
         "version": AGENT_ENDPOINT_VERSION, "summary": "标签模型总览（身份/职务轴）"},
        # ---- 11.12.0 代码字典（符号级索引，只读）----
        {"path": "/agent/code-dict", "method": "GET", "handler": "agent_code_dict", "write": False,
         "params": {"q": "子串模糊查（符号/常量/端点/模块职责/口径）",
                    "section": "endpoints|constants|symbols|modules|glossary（取整节）",
                    "full": "1=回全部（大，慎用）"},
         "returns": "CodeDict", "version": AGENT_ENDPOINT_VERSION,
         "summary": "代码字典（符号级索引：某名在哪个文件哪一行）"},
        # ---- 12.5.0 挂种健康度自检（只读）----
        {"path": "/agent/seeds/health", "method": "GET", "handler": "agent_seeds_health",
         "write": False,
         "params": {"site": "域名/短名/id（可空=全站）", "only": "ghost|partial|all（默认 all）",
                    "limit": "int（默认 200，0=不限）"},
         "returns": "SeedsHealthReport", "version": AGENT_ENDPOINT_VERSION,
         "summary": "挂种健康自检（逐文件核盘：空转/缺文件 + 体积 + 欠 H&R 风险）"},
        # ---- 12.7.0 调试面自描述（只读）----
        {"path": "/agent/debug/surface", "method": "GET", "handler": "agent_debug_surface",
         "write": False,
         "params": {},
         "returns": "DebugSurface",
         "version": AGENT_ENDPOINT_VERSION,
         "summary": "调试面自描述（/debug 端点、哪些会写、读文件白名单/黑名单）"},
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
                   field: Optional[str] = None, trace_id: Optional[str] = None,
                   data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if data is None and (field is not None or trace_id is not None):
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
                "DecideReport": "{hash, name, state, progress, verdict, reason_chain[], chain[{step,rule,verdict,inputs,source_of_truth,at}], bills[], protection[]}",
                "Plan": "{plan_id, format, action, task_id, task_name, task_type, site_id, budget_gb, created_at, items[{hash,op,title,size_gb,bonus_per_hour,age_weeks,reason,chain[]}], totals{}, warnings[], note}",
                "PlanApply": "{plan_id, action, task_id, deleted, error, delete_files, blocked[{hash,reason}], note}（confirm!=1 时回 dry_run=true + items）",
                "BillPage": "{items[], next_cursor, total}",
                "AgentState": "{tasks{}, managed{}, bills{}, pool{}, sites{}}",
                "CleanupPreview": "{task_id, mode?, total_torrents?, to_delete_count?/count?, deletion_candidates?[{hash,title,size_gb,seeders,age_weeks,bonus_per_hour,reason,priority}], estimated_bonus_gain?, message?}",
                "OptimizePlan": "{task_id, method, granularity_gb, budget_gb, budget_source, infeasible, pool{count,size_gb,bonus_per_hour}, mandatory{count,size_gb,bonus_per_hour}, plan{keep_count,delete_count,kept_size_gb,freed_gb,kept_bonus_per_hour,lost_bonus_per_hour,kept_bonus_pct,keep[],delete[]}, frontier[{budget_gb,kept_size_gb,kept_count,delete_count,kept_bonus_per_hour,lost_bonus_per_hour,kept_bonus_pct}], compare{threshold,optimized_at_same_freed,saved_bonus_per_hour,note}}",
                "ExamAct": "{dry_run?, site_id, kind, confirm?, hint?} 或写入结果 {task_name/task_id/enabled/noop?, notes[]?, message}（confirm!=1 恒零写入）",
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

    def agent_decide(self, hashes: str = "", task_id: str = "") -> Dict[str, Any]:
        """``GET /agent/decide?hashes=a,b[&task_id=xxx]`` —— 每个 hash **完整的决策链**。

        一整批只拉**一次** qB 快照（同一轮内复用），传给 ``_hr_obligation``；
        不逐种重拉。给了 ``task_id`` → 走 ``_chain_ctx`` 带上任务级口径
        （硬/软保护 + 策略阈值评分），每条回 ``chain``（identity→protect→delete_gate
        →score→history→verdict）。``reason_chain`` 保留（历史集成兼容）。
        """
        t0 = time.time()
        hs = self._agent_parse_hashes(hashes)
        if hs is None:
            return self._agent_err(
                "bad_param", "hashes 需要 40/64 位 hex（逗号分隔，必填）", t0, field="hashes")
        tid = str(task_id or "").strip()
        task = None
        if tid:
            task = self._get_task_config(tid)
            if not task:
                return self._agent_err("not_found", "任务不存在", t0, field="task_id")
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
        # ★ 15.17.0：任务上下文（软/硬保护 + 策略）→ 完整决策链
        ctx: Optional[Dict[str, Any]] = None
        _chain = getattr(self, "_chain_ctx", None)
        if callable(_chain):
            try:
                ctx = _chain(task, tid, snap) if tid else _chain(None, "", snap)
            except Exception:  # noqa: BLE001
                ctx = None
        items = []
        for h in hs:
            it = self._decide_one(h, snap, ledger, manual, crossseed, claim)
            if ctx is not None:
                try:
                    it["task_id"] = tid
                    it["chain"] = self._chain_steps(h, snap.get(h), ledger.get(h), ctx)
                except Exception as e:  # noqa: BLE001
                    it["chain_error"] = str(e)
            items.append(it)
        return self._agent_ok({"items": items, "task_id": tid}, t0)

    # -------------------------------------------------------- 整批清理预览（任务级）
    def agent_cleanup_preview(self, task_id: str = "") -> Dict[str, Any]:
        """``GET /agent/cleanup/preview?task_id=xxx`` —— 某任务一轮删种名单预览（**只算不删**）。

        与 UI ``POST /tasks/{task_id}/preview`` **同源**（复用 ``preview_cleanup``，不新增第二份口径）：
        保护集 = ``_protection_sets``（手动保留 / 跨站来源份 / 已认领 / 欠 H&R / 未下完 / 库内资产）。
        **只读**：只算名单，不删任何种、不写任何真值。bonus 任务回删种候选 + 魔力增益预估；
        brush 任务回「无上传将被清理」名单。
        """
        t0 = time.time()
        tid = str(task_id or "").strip()
        if not tid:
            return self._agent_err("bad_param", "task_id 必填", t0, field="task_id")
        fn = getattr(self, "preview_cleanup", None)
        if not callable(fn):
            return self._agent_err("internal", "preview_cleanup 未实现（版本不符）", t0)
        try:
            res = fn(tid)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"预览失败:{e}", t0, trace_id=str(e))
        ok = bool(getattr(res, "success", False))
        data = getattr(res, "data", None)
        msg = str(getattr(res, "message", "") or "")
        if not ok:
            code = "not_found" if "不存在" in msg else "internal"
            return self._agent_err(code, msg or "预览失败", t0)
        payload: Dict[str, Any] = {"task_id": tid}
        if isinstance(data, dict):
            payload.update(data)
        elif data is not None:
            payload["result"] = data
        if msg and "message" not in payload:
            payload["message"] = msg
        return self._agent_ok(payload, t0)

    # -------------------------------------------------------- 组合优化器（任务级）
    def agent_optimize(self, task_id: str = "", budget_gb: str = "") -> Dict[str, Any]:
        """``GET /agent/optimize?task_id=xxx[&budget_gb=N]`` —— 容量预算下最优「保/删」组合。

        与 UI ``GET /tasks/{task_id}/optimize`` **同源**（复用 ``optimize_plan``）：在
        「保留体积 ≤ budget_gb」约束下最大化保留种子的**时魔总和**（0/1 背包，受保护种
        强制保留）。**只读**：只出计划，不删任何种、不写任何真值。``budget_gb`` 缺省 →
        自动取「保留 ≥95% 时魔」的最小预算；回包含效率前沿与「逐条阈值」口径在同释放
        体积下的对比（优化器更省多少时魔/h）。
        """
        t0 = time.time()
        tid = str(task_id or "").strip()
        if not tid:
            return self._agent_err("bad_param", "task_id 必填", t0, field="task_id")
        bud = str(budget_gb or "").strip()
        if bud != "":
            try:
                if float(bud) < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return self._agent_err("bad_param", "budget_gb 需为非负数字（GB）", t0, field="budget_gb")
        fn = getattr(self, "optimize_plan", None)
        if not callable(fn):
            return self._agent_err("internal", "optimize_plan 未实现（版本不符）", t0)
        try:
            res = fn(tid, bud)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"组合优化失败:{e}", t0, trace_id=str(e))
        ok = bool(getattr(res, "success", False))
        data = getattr(res, "data", None)
        msg = str(getattr(res, "message", "") or "")
        if not ok:
            code = "not_found" if "不存在" in msg else "bad_param" if "budget_gb" in msg else "internal"
            return self._agent_err(code, msg or "组合优化失败", t0)
        payload: Dict[str, Any] = {"task_id": tid}
        if isinstance(data, dict):
            payload.update(data)
        elif data is not None:
            payload["result"] = data
        if msg and "message" not in payload:
            payload["message"] = msg
        return self._agent_ok(payload, t0)

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
    def agent_report(self, view: str = "site", site: str = "", state: str = "",
                     bucket: str = "", sub: str = "", origin: str = "", transport: str = "",
                     hr: str = "", protected: str = "", limit: int = 200, offset: int = 0,
                     live: int = 0) -> Dict[str, Any]:
        """``GET /agent/report`` —— ★ **报表统一入口**（只读，17.3.0）。

        一次调用答：**「我们手上到底有哪些种、各是什么身份、欠不欠债、能不能动」**。
        一行 = 一颗种；真值源 = **账本**（种子账本 + ``hr_bills.json`` + 资源账本），
        下载器快照只补 ``transport``（做种中 / 暂停 / 未完成 / 不在下载器）并用于互校。

        - ``view=site``   按站聚合全量（同旧 ``/agent/site/seeds``，数字已收口）
        - ``view=silent`` 静默池（同旧 ``/agent/silent``）
        - ``view=hr``     H&R 账单（同旧 ``/agent/hr/bills``，``rule=unknown`` 显式归「未定性」）
        - ``view=rows``   通用台账（可按 state/bucket/sub/origin/transport/hr/protected 过滤）

        参数非法一律报 ``bad_param``（不再静默忽略）；``limit=0`` = 全部。
        本端点**只读**：不写下载器 / 不写账本 / 不新增缓存。
        """
        t0 = time.time()
        return self._agent_call_read(
            t0,
            ("features/reportview.get_report() → 种子账本 mf_seed + hr_bills.json + mf_resource"
             " + 下载器快照（只补传输态）+ _protection_sets()"),
            self.get_report, view, site, state, bucket, sub, origin, transport, hr,
            protected, limit, offset, live)

    def agent_report_drift(self) -> Dict[str, Any]:
        """``GET /agent/report/drift`` —— **报表四向互校**（只读，17.3.0）。

        账本 × 下载器 × MP 站点清单 × 账单对齐：``ledger_only``（账本有、下载器没有的幽灵行）、
        ``qb_only``（下载器有、账本没纳管的）、``missing_from_mp``（账本在挂但站已不在 MP）。
        只报不修。
        """
        t0 = time.time()
        return self._agent_call_read(
            t0, "features/reportview.drift() → 账本 × 下载器 × MP 站点清单 × 账单",
            self.get_report_drift)

    def agent_site_seeds(self, site: str = "", live: int = 0) -> Dict[str, Any]:
        """``GET /agent/site/seeds`` —— ★ **站点级种子报表**（只读，两轴分级）。

        一次调用答：**「某站点上，我们挂的各种种子现在都是什么状态」**。

        - 逐条种子：hash / 标题 / 体积 / 保存目录 / qB 状态 / 进度 / 比例 / 上传 /
          第一级桶（职务/身份轴）+ 身份子桶（静默桶的 新/资源/普通）+ 传输三态 / 保护 /
          账单 / H&R 需做种时间（债务列字段，不再当桶）；
        - 第一级桶：刷流 / 魔力 / 保种（欠 H&R 挂补）/ 静默 / 补源 / 外部（互斥）；
        - 第二级传输轴：未完成 / 暂停 / 做种中（每桶内三态统计，不单独成桶）；
        - 汇总：by_bucket + by_transport + bucket_transport + silent_by_sub + 体积 + H&R 欠账摘要；
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

    # ---------------------------------------------------- 15.9.0 站点类型映射（只读）
    # ---------------------------------------------------- 16.0.0 站点已删除（识别 + 处置）
    def agent_sites_deleted(self) -> Dict[str, Any]:
        """``GET /agent/sites/deleted`` —— ★ **已被 MoviePilot 删除的站点**清单 + 牵连面（只读）。

        一次调用答：**「MP 里删了哪些站、每个站在魔流这边还挂着多少东西」**。
        ★ 17.5.0 判据换成**共用真值源** ``siteops.site_deleted_domains``
        （``site_references`` − MP 站点表；报表/health H8/notify 用同一份）：
        遍历**所有站点引用**（``mf_site`` 行 ∪ 账单 ∪ ``mf_seed``/``mf_reseed``/``mf_crossseed`` ∪ 任务），
        所以**只剩账单/账本残留、台账行早已被删**的站也能看见（旧口径只看 ``mf_site`` 行 → 盲区）。
        新增字段：``refs``（被哪些层引用）、``bills``（账单条数 = 无法对账的欠账规模）、
        ``has_row``（有没有台账行）、``status``/``deleted_at``（``SiteLifecycle`` worker 落的标记）。
        牵连面只数不写：qB 标签种数/体积/暂停数/复用副本数、``mf_seed``/``mf_reseed`` 行数、站内任务。
        处置入口见 ``POST /agent/sites/deleted/act``。

        ``reason`` ∈ ``mp_deleted`` / ``domain_missing`` / ``residue_no_row``。
        **MP 站点表读不到 → 返回空**（判不出不硬判）。

        ★ 17.4.0 起本清单**已接自动化**：``notify_sweep`` → ``notify_check_site_deleted`` 发告警
        （每站一条、按 ``sitedel:<site_id>`` 去重），健康自检出 ``H8:<site_id>``。
        **只报不做**——摘种/删种一律要显式下令（act 端点，默认干跑）。
        """
        t0 = time.time()
        try:
            from .siteops import deleted_sites_rows  # noqa: WPS433（延迟导入：勿在 module 级拉兄弟 feature）
            rows = deleted_sites_rows(self)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"已删除站点盘点失败:{e}", t0, trace_id="sites")
        return self._agent_report(
            {"count": len(rows), "sites": rows}, t0,
            ("魔流**所有站点引用**（siteops.site_references：mf_site ∪ hr_bills.json ∪ "
             "mf_seed/mf_reseed/mf_crossseed ∪ _task_configs）× MoviePilot 站点表 SiteOper.list()"
             "（common.SiteGuard.mp_sites，60s 记忆化）；域名兜底：mp_site_id 查不到但同域名还在 MP → "
             "不算删（MP 删站后重加同名站会拿新 id）。牵连面只数不写"
             "（qB 标签前缀 魔流-<站名>- / mf_seed / mf_reseed / _task_configs）"))

    def agent_sites_deleted_act(self, site_id: Any = "", action: str = "",
                                reuse_only: Any = 0, dry_run: Any = 1,
                                force_asset: Any = 0) -> Dict[str, Any]:
        """``POST /agent/sites/deleted/act`` —— ★ 已删除站点行内处置（pause/resume/remove）。

        **默认干跑**（``dry_run=1``）。``remove`` 口径：**别人辅种的复用副本**（``魔流-辅种``）
        → **只摘种**；**自己的非资源**（无辅种且非 ``资源``）→ **连文件一起删**；
        **资源**（``静默-资源`` = 本体/库内资产）→ **保留不动**。
        连文件删仍过**唯一删除闸门**（欠 H&R / 已认领 / 手动保留 / 库内资产硬拦）+ 内置**共享文件护栏**
        （同批之外还有别的种共用同一份文件 → 自动降级为只摘种）。``reuse_only=1`` 只跑复用副本那档。
        ``force_asset=1`` → ★ 走「手动删库内资产」专用闸门（跳过「库内资产（已入库，永不删）」这类，
        其余四类照拦）；用于站点已删除后的彻底清理，**默认关**。

        ★ 17.5.0：``site_id`` 也接受**域名**（只剩账单/账本残留、台账行已删的站没有 site_id 可用）。
        """
        t0 = time.time()
        try:
            from .siteops import deleted_site_act  # noqa: WPS433（延迟导入：勿在 module 级拉兄弟 feature）
            rep = deleted_site_act(self, site_id=site_id, action=action,
                                   reuse_only=reuse_only, dry_run=dry_run, force_asset=force_asset)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"已删除站点处置失败:{e}", t0, trace_id=str(action))
        if not rep.get("ok"):
            code = "blocked" if rep.get("blocked") else "invalid"
            return self._agent_err(code, str(rep.get("message") or "操作未生效"), t0,
                                   trace_id=str(action), data=rep)
        return self._agent_report(
            rep, t0,
            ("写操作 → DownloaderAdapter.pause_torrents/resume_torrents/delete_torrents"
             "(delete_file=False)；remove 过唯一删除闸门（deletegate），硬保护一律拦；"
             "remove 三档：复用副本 + 本体/库内资产【只摘种、不删文件】走具名通道 gate_strip"
             "（只跳第 5 类，且**永不带** allow_library_asset），自有非本体【连文件删】走严格 gate"
             "（force_asset=1 时才改走 gate_manual 跳过第 5 类）"))

    def agent_sites_types(self) -> Dict[str, Any]:
        """``GET /agent/sites/types`` —— ★ **站点「分类类型」映射**（只读）。

        一次调用答：**「每个站的 movie/tv/music 分类 id 各是什么、站点自报什么类型」**。

        类型真值**一律用 MP**（Master 2026-10-10 定）：本端点只**读** MP 站点索引器的
        ``category`` / ``media_type``（``SitesHelper().get_indexers()``，与搜索层
        ``IndexerModule`` 同源），归一成逐站清单；**不自己造分类、不替 MP 判类型、
        不私自回退**。搜索仍按 MP 的 ``mtype`` 走（本站点只是「选站 / 核对 / 展示」的对照表）。

        真值源：``SitesHelper().get_indexers()``（内存索引器 schema）。本端点**只读**：
        不写任何 json / 账本 / 热层。
        """
        t0 = time.time()
        try:
            from app.sdk.network import SitesHelper
            indexers = SitesHelper().get_indexers() or []
        except Exception as e:  # noqa: BLE001
            return self._agent_err("unavailable", f"读取 MP 站点索引失败:{e}", t0, trace_id="sites")
        rows = site_type_rows(indexers)
        if not rows:
            return self._agent_err(
                "empty", "MP 站点索引为空（可能：站点未认证 / 未配置站点）",
                t0, trace_id="sites")
        return self._agent_report(
            {"count": len(rows),
             "with_music": sum(1 for r in rows if r["supports"]["music"]),
             "sites": rows},
            t0,
            ("MoviePilot SitesHelper.get_indexers() → 站点索引器 schema 的 "
             "category{movie,tv,music} + media_type（与搜索层 IndexerModule 同源）；"
             "只读、不造第二份分类"))

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
        归因：删除台账（mf_deletions）命中 ok=true → 本插件删（gate bug 升级 critical）；否则外部删。
        只读：不写任何账单/账本；补回走 write.reseed / write.rescue（需 confirm=1）。
        """
        t0 = time.time()
        try:
            data = self._hr_breaches()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"H&R违约清单失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("features/hrbills._hr_breaches() → mf_bills + mf_deletions + "
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

    # ---------------------------------------------------- 15.2.0 标签 ↔ 账本对账
    def agent_tags_reconcile(self, confirm: int = 0, adopt_reseed: int = 0,
                             limit: int = 0) -> Dict[str, Any]:
        """``GET /agent/tags/reconcile`` —— ★ **标签 ↔ 账本对账**（写；默认干跑）。

        一次调用答：**「账本说在岗的种里，哪些 qB 标签缺身份轴 / 缺职务轴（该补）」**。
        真值源 = 种子账本（`mf_seed`）；qB 标签只是镜像。只写 qB 标签 + （可选）补登辅种账；
        **不改种子账本、不删种、不暂停、不 resume、不碰 H&R**。
        ``confirm=0``（默认）= 只报数零写入；``confirm=1`` = 真补标签。
        """
        t0 = time.time()
        try:
            data = self._tag_ledger_reconcile(
                apply=bool(int(confirm or 0)),
                adopt_reseed=bool(int(adopt_reseed or 0)),
                limit=self._agent_int(limit, 0),
            )
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"标签↔账本对账失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("features/tags._tag_ledger_reconcile() → SeedLedgerStore.items()(真值源) + "
             "_tag_all_torrents(qB 快照) + retag(qB标签) → DownloaderAdapter.set_torrent_tags(只补标签)"))

    # ---------------------------------------------------- 15.3.0 qB 增量同步观测
    def agent_qb_snapshot(self) -> Dict[str, Any]:
        """``GET /agent/qb/snapshot`` —— qB **增量同步**观测（只读）。

        一次调用答：**「qB 快照现在是增量还是全量、省了多少、rid 走到哪」**。
        真值源 = ``qbsync.QbSyncStore``（``/sync/maindata?rid=`` 增量合并，**纯内存**，
        不写 Redis / 不落盘）。计数：``full_pulls``（全量建表）/``delta_pulls``（增量合并）/
        ``unchanged_pulls``（无变化）/``errors``，加 ``last_delta_n``/``last_delta_bytes``。
        """
        t0 = time.time()
        try:
            dl = self._get_downloader("qbittorrent")
            if dl is None or not hasattr(dl, "qb_sync_stats"):
                return self._agent_err("unavailable", "下载器不可用", t0, trace_id="qb")
            data = dl.qb_sync_stats()
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"读取 qB 增量快照观测失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("DownloaderAdapter.qb_sync_stats() → qbsync.QbSyncStore.stats()"
             "（/sync/maindata?rid= 增量合并；纯内存计数，不写 Redis/不落盘）"))

    # ---------------------------------------------------- 15.4.0 点播清单（只读）
    def agent_ondemand(self, limit: int = 50) -> Dict[str, Any]:
        """``GET /agent/ondemand`` —— 点播清单（只读）。

        一次调用答：**「我点播了哪些片、下到哪了、结果如何」**。
        真值源：进行中 = ``ondemand_pending``（``mf_seed.pending``）× qB 快照；
        历史 = **点播历史落盘记录**（``ondemand_history`` 槽；点播时写、结算/撤单时更新）。
        17.1.0 起历史**不再**动态拼 journal + 现况回查（只读记录）。
        """
        t0 = time.time()
        try:
            data = self._ondemand_items(limit=limit)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"读取点播清单失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("进行中 = ondemand_pending(mf_seed.pending) × qB 快照(progress/state/dl_speed)；"
             "历史 = ondemand_history 槽（落盘记录；点播时写、结算/撤单时更新）——只读，不再动态拼 journal"))

    # ---------------------------------------------------- 15.5.0 点播行内操作（写）
    # ---------------------------------------------------- 15.10.0 后台任务队列（只读）
    def agent_jobs(self, limit: int = 50) -> Dict[str, Any]:
        """``GET /agent/jobs`` —— 后台任务队列（读）。"""
        t0 = time.time()
        return self._agent_call_read(t0, "jobs_list() → 后台任务队列(queued/running/done/failed)",
                                     lambda: self.jobs_list(limit=int(limit or 50)))

    # ---------------------------------------------------- 15.9.0 库内资源管理动作
    def agent_notify(self, limit: int = 50) -> Dict[str, Any]:
        """``GET /agent/notify`` —— 事件通知配置 + 最近事件（只读）。"""
        t0 = time.time()
        try:
            resp = self.notify_status(limit=int(limit or 50))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"通知状态读取失败:{e}", t0, trace_id=str(e))
        d = getattr(resp, "data", {}) or {}
        try:
            n = max(1, min(int(limit or 50), 200))   # = notify.NOTIFY_HISTORY_KEEP（避免跨模块常量导入）
        except Exception:  # noqa: BLE001
            n = 50
        return self._agent_ok({
            "cfg": d.get("cfg") or {},
            "counts": d.get("counts") or {},
            "kinds": d.get("kinds") or {},
            "quiet_now": bool(d.get("quiet_now")),
            "history": (d.get("history") or [])[:n],
        }, t0)

    def agent_notify_act(self, action: str = "test", text: str = "") -> Dict[str, Any]:
        """``POST /agent/notify/act`` —— 发测试 / 立即扫描 / 清历史（**只发消息，不动任何种子**）。"""
        t0 = time.time()
        try:
            from ..models import MagicFlowNotifyActPayload  # noqa: WPS433
            rep = self.notify_act(MagicFlowNotifyActPayload(action=str(action or "test"), text=str(text or "")))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"通知动作失败:{e}", t0, trace_id=str(e))
        data = {"success": bool(getattr(rep, "success", False)),
                "message": str(getattr(rep, "message", "") or ""),
                "report": getattr(rep, "data", None)}
        if not data["success"]:
            return self._agent_err("invalid", data["message"] or "动作未生效", t0,
                                   trace_id=str(action), data=data)
        # 只用本文件定义的 _agent_ok（不新增跨界私调）；来源说明随 data 一起回
        data["source_of_truth"] = ("写操作（仅通知）：post_message() 走 MP 通知渠道；"
                                   "scan=notify_sweep(force) 只读扫描；clear=清 notify_history.json")
        return self._agent_ok(data, t0)

    def agent_assets_act(self, action: str = "", resource_ids: str = "",
                         hashes: str = "", season: int = 0) -> Dict[str, Any]:
        """``POST /agent/assets/act`` —— 库内资源管理动作（保护/订阅/整理/刮削，**不删除**）。"""
        t0 = time.time()
        _r = [x.strip() for x in str(resource_ids or "").split(",") if x.strip()]
        _h = [x.strip() for x in str(hashes or "").split(",") if x.strip()]
        if not _r and not _h:
            return self._agent_err("invalid", "resource_ids 或 hashes 至少给一个", t0,
                                   field="resource_ids")
        try:
            from ..models import MagicFlowAssetActPayload  # noqa: WPS433
            rep = self.assets_act(MagicFlowAssetActPayload(
                action=str(action or ""), resource_ids=_r, hashes=_h, season=int(season or 0),
            ))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"库内资源动作失败:{e}", t0, trace_id=str(e))
        data = {"success": bool(getattr(rep, "success", False)),
                "message": str(getattr(rep, "message", "") or ""),
                "report": getattr(rep, "data", None)}
        if not data["success"]:
            return self._agent_err("invalid", data["message"] or "动作未生效", t0,
                                   trace_id=str(action), data=data)
        return self._agent_report(
            data, t0,
            "写操作 → 手动保留桶(永不自动删) / MP SubscribeChain().add(作品+季) / "
            "TransferChain().manual_transfer(重新整理) / FallbackEngine 多源重刮元数据")

    # ---------------------------------------------------- 15.8.25 推荐整季订阅（手动）
    def agent_recommend_act(self, hash: str = "", action: str = "") -> Dict[str, Any]:
        """``POST /agent/recommend/act`` —— 推荐记录整季订阅（**手动标记才订阅**）。

        ``subscribe`` = 按「作品+季」给 MP 加整季订阅（让 MP 抓齐其余集并整理到一起）；
        ``unsubscribe`` = 退订并把记录复位为待核实（**不动种子**）。
        """
        t0 = time.time()
        act = str(action or "").strip().lower()
        if act not in ("subscribe", "unsubscribe"):
            return self._agent_err("invalid", "action 需为 subscribe / unsubscribe", t0,
                                   field="action")
        if not hash:
            return self._agent_err("invalid", "hash 必填", t0, field="hash")
        try:
            rep = (self.subscribe_recommend(hash) if act == "subscribe"
                   else self.unsubscribe_recommend(hash))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"推荐订阅操作失败:{e}", t0, trace_id=str(e))
        data = {
            "hash": hash, "action": act,
            "ok": bool(getattr(rep, "success", False)),
            "message": str(getattr(rep, "message", "") or ""),
            "record": getattr(rep, "data", None),
        }
        if not data["ok"]:
            return self._agent_err("blocked", data["message"] or "操作未生效", t0,
                                   trace_id=act, data=data)
        return self._agent_report(
            data, t0,
            "写操作 → MP SubscribeChain().add(title, year, MediaType.TV, season) 整季订阅；"
            "unsubscribe → SubscribeChain()._delete_subscription(id)")

    def agent_ondemand_act(self, hash: str = "", action: str = "") -> Dict[str, Any]:
        """``POST /agent/ondemand/act`` —— 点播行内操作（pause / resume / remove）。

        ``remove`` **走唯一删除闸门**（不绕过）：欠 H&R / 跨站来源份 / 已认领 / 手动保留 一律硬拦，
        被拦时 ``ok=false`` + ``blocked=true`` + 原因，如实回传。
        """
        t0 = time.time()
        try:
            rep = self._ondemand_act(hash=hash, action=action)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"点播操作失败:{e}", t0, trace_id=str(e))
        if not rep.get("ok"):
            code = "blocked" if rep.get("blocked") else "invalid"
            return self._agent_err(code, str(rep.get("message") or "操作未生效"), t0,
                                   trace_id=str(action), data=rep)
        return self._agent_report(
            rep, t0,
            ("写操作 → DownloaderAdapter.pause_torrents/resume_torrents/delete_torrents；"
             "remove 过唯一删除闸门（deletegate）——欠 H&R / 跨站来源份 / 已认领 / 手动保留一律硬拦"))

    # ---------------------------------------------------- 15.9.0 点播搜索自描述（只读）
    async def agent_ondemand_search(self, query: str = "", site_ids: str = "",
                                    page: int = 0, source: str = "") -> Dict[str, Any]:
        """``POST /agent/ondemand/search`` —— 点播候选 + **每站事实**（只读）。

        一次调用答：**「这单搜到没、全不全」**。**透传 MP 原生单页分页**（``search_page_events``）：
        ``sources[]`` = 每站 ``{source, site_name, page, can_continue, error}``（``can_continue`` 判有无下页；
        ``source`` 为续页令牌，回传 + ``page=N+1`` 即续该站）。类型/分页/别名/过滤全听 MP，我们不做第二真值源。
        """
        t0 = time.time()
        ids: List[int] = []
        for x in str(site_ids or "").replace("，", ",").split(","):
            s = str(x).strip()
            if s.isdigit():
                ids.append(int(s))
        if not str(query or "").strip() and not str(source or "").strip():
            return self._agent_err(
                "bad_param",
                "缺少 query（片名 / 豆瓣·TMDB·IMDB 链接）：首页必填，续页请带 source"
                "（空 query 不再静默返回空名单）", t0, field="query")
        try:
            data = await self._ondemand_search_sources(
                str(query or ""), ids, page=int(page or 0), source=str(source or ""))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("upstream_error", f"搜索失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("搜索 = MP SearchChain().search_page_events(params=…)（app/chain/search/manual.py）；"
             "sources[] = MP 逐来源事实 {source,site_name,page,can_continue,error}；类型/分页/别名/过滤全听 MP"))

    def agent_ondemand_add(self, query: str = "", site_ids: str = "", pick: str = "",
                           task_id: str = "", confirm: str = "") -> Dict[str, Any]:
        """`POST /agent/ondemand/add` —— ★ 按 **AI 选定源** 落种（写，16.0.0）。

        流程：`/agent/ondemand/search` 拿候选（含 `enclosure`）→ AI 自己选 → 本端点按 `pick` 下这条。
        **绝不自动选源**（不调 `_ondemand_pick`）：`pick` 未命中候选 → 如实回报「请先 search」，不猜。
        `confirm` 缺省（或非 1）→ **只回干跑计划**；`confirm=1` 才真加种（走点播通道，不被静默闸暂停）。
        """
        t0 = time.time()
        if not str(query or "").strip():
            return self._agent_err("bad_request", "缺少 query（片名或链接）", t0)
        if not str(pick or "").strip():
            return self._agent_err(
                "bad_request", "缺少 pick（候选 enclosure / 下载链接，来自 /agent/ondemand/search）", t0)
        _ok = str(confirm).strip().lower() in ("1", "true", "yes", "y", "on")
        try:
            data = self._ondemand_add(query=query, site_ids=site_ids, pick=pick,
                                      task_id=task_id, apply=bool(_ok))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal_error", f"加种失败: {e}", t0)
        if not data.get("ok"):
            return self._agent_err("bad_request", str(data.get("message") or "加种未生效"),
                                   t0, data=data)
        if not _ok:
            return self._agent_ok(data, t0)
        return self._agent_report(
            data, t0,
            ("写操作 → 只按 pick 命中的候选 → _ondemand_download（DownloaderAdapter.add_torrent）；"
             "身份=资源 + 职务=点播；**不调 _ondemand_pick**（不自动选源）；未下完不被静默池暂停"))

    def agent_ondemand_add_direct(self, url: str = "", site_ids: str = "",
                                  task_id: str = "", confirm: str = "") -> Dict[str, Any]:
        """`POST /agent/ondemand/add_direct` —— ★ 按**种子链接**直接加种（写，17.2.0）。

        与 `POST /agent/ondemand/add` 的分工：那个要先 search 再 pick；**这个只认链接**
        （`details.php?id=N` / `download.php?id=N` / `.torrent` 直链），用指定站点的 cookie 取种。
        `site_ids` **必填且唯一**（取种要 cookie，不猜站点）。
        `confirm` 缺省（或非 1）→ **只回干跑计划**（干跑也取一次 .torrent 读元数据、不落种）；`confirm=1` 才真加种。
        """
        t0 = time.time()
        if not str(url or "").strip():
            return self._agent_err(
                "bad_request",
                "缺少 url（种子链接：details.php?id=N / download.php?id=N / .torrent 直链）", t0)
        if not str(site_ids or "").strip():
            return self._agent_err(
                "bad_request", "缺少 site_ids（直连加种必须指定**唯一**站点：取种要用该站 cookie）", t0)
        _ok = str(confirm).strip().lower() in ("1", "true", "yes", "y", "on")
        try:
            data = self._ondemand_add_direct(url=url, site_ids=site_ids,
                                             task_id=task_id, apply=bool(_ok))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal_error", f"直连加种失败: {e}", t0)
        if not data.get("ok"):
            return self._agent_err("bad_request", str(data.get("message") or "加种未生效"),
                                   t0, data=data)
        if not _ok:
            return self._agent_ok(data, t0)
        return self._agent_report(
            data, t0,
            ("写操作 → 按链接解析 id（claim._torrent_id_of）→ 该站 cookie 取 .torrent（crossseed PV 闸门）→ "
             "复用 _ondemand_download 落种；身份=资源 + 职务=点播；"
             "促销拿不到按全额计；H&R 不自造逐种标记（判定归 H&R 模块：站点规则账本 hr=True→site_hr / "
             "False→不开账 / 未知→unknown）"))

    # ---------------------------------------------------- 15.9.0 音乐搜索自描述（只读）
    async def agent_music_search(self, query: str = "", site_ids: str = "",
                                 page: int = 0, source: str = "") -> Dict[str, Any]:
        """``POST /agent/music/search`` —— 音乐候选 + **每站事实**（只读）。

        试透传 MP 原生单页分页（``search_page_events``，``mtype=MediaType.MUSIC``）：
        ``sources[]`` = 每站 ``{source, site_name, page, can_continue, error}``（``can_continue`` 判有无下页；
        ``source`` 为续页令牌）。候选已打分/硬过滤（``score``/``excluded``/``exclude_reason``）。类型听 MP。
        """
        t0 = time.time()
        ids: List[int] = []
        for x in str(site_ids or "").replace("，", ",").split(","):
            s = str(x).strip()
            if s.isdigit():
                ids.append(int(s))
        if not str(query or "").strip() and not str(source or "").strip():
            return self._agent_err(
                "bad_param",
                "缺少 query（歌名 / 艺人）：首页必填，续页请带 source"
                "（空 query 不再静默返回空名单）", t0, field="query")
        try:
            data = await self._music_search_sources(
                str(query or ""), ids, page=int(page or 0), source=str(source or ""))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("upstream_error", f"音乐搜索失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("音乐搜索 = MP SearchChain().search_page_events(params={keyword,mtype:Music,…})；"
             "sources[] = MP 逐来源事实 {source,site_name,page,can_continue,error}；候选 = MP 过滤后 Context.torrent_info 归一 + 现有打分"))

    def agent_music_download(self, cids: str = "", save_path: str = "", confirm: str = "") -> Dict[str, Any]:
        """``POST /agent/music/download`` —— 按 AI 选中的候选 cid 加种（写）。

        流程：``/agent/music/search`` 拿 candidates[].cid → AI 挑 → 本端点按 cid 落种。
        凭据真值（enclosure/cookie/ua）只存服务端候选缓存（30min，reload 清空）；``confirm`` 缺省=干跑。
        """
        t0 = time.time()
        cid_list = [x.strip() for x in str(cids or "").replace("，", ",").split(",") if x.strip()]
        if not cid_list:
            return self._agent_err("bad_request",
                                   "缺少 cids（逗号分隔，来自 /agent/music/search 的 candidates[].cid）", t0)
        known = [c for c in cid_list if self._music_cand_get(c)]
        if not known:
            return self._agent_err("not_found", "cids 全部不存在或已过期（请重新搜索）", t0,
                                   trace_id=",".join(cid_list[:3]))
        _ok = str(confirm).strip().lower() in ("1", "true", "yes", "y", "on")
        if not _ok:
            preview = [self._music_cand_public({**self._music_cand_get(c), "cid": c}) for c in known]
            return self._agent_ok({"applied": False, "dry_run": True,
                                   "note": "干跑（confirm 未置 1，未加任何种）",
                                   "save_path": self._music_save_path(save_path),
                                   "candidates": preview,
                                   "summary": {"picked": len(known)}}, t0)
        try:
            data = self._music_download_cids(known, save_path=save_path)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal_error", f"加种失败: {e}", t0)
        return self._agent_report(data, t0,
                                  ("写操作 → 服务端候选缓存按 cid 取回凭据 → _music_grab_one "
                                   "→ _crossseed_torrent_bytes + add_torrent；category=音乐，进账本/H&R/闸门"))

    def agent_music_items(self, limit: int = 50) -> Dict[str, Any]:
        """``GET /agent/music/items`` —— 音乐清单（单列表 + totals）。只读。"""
        t0 = time.time()
        try:
            data = self._music_items(limit=limit)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"读取音乐清单失败:{e}", t0, trace_id=str(e))
        return self._agent_report(
            data, t0,
            ("音乐清单 = qB 音乐线快照(is_music_line) × journal(source=music) × 种子账本；"
             "只归一字段（stage/percent/ISO 时间），不新造真值源"))

    def agent_music_act(self, hash: str = "", action: str = "") -> Dict[str, Any]:
        """``POST /agent/music/act`` —— 音乐行内操作（pause / resume / remove）。

        ``remove`` **走唯一删除闸门**（不绕）：欠 H&R 等硬拦，被拦时 ``ok=false`` + ``blocked=true`` + 原因。
        只允许操作**音乐线**的种（不属于音乐线 → 拒绝）。
        """
        t0 = time.time()
        try:
            rep = self._music_act(hash=hash, action=action)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"音乐操作失败:{e}", t0, trace_id=str(e))
        if not rep.get("ok"):
            code = "blocked" if rep.get("blocked") else "invalid"
            return self._agent_err(code, str(rep.get("message") or "操作未生效"), t0,
                                   trace_id=str(action), data=rep)
        return self._agent_report(
            rep, t0,
            ("写操作 → DownloaderAdapter.pause_torrents/resume_torrents/delete_torrents；"
             "remove 过唯一删除闸门（deletegate）；仅限 qB 音乐线种"))

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

    # ---------------------------------------------------------------- ★ 15.8.15
    # Master「希望增加魔流库内资产手动删除的入口」的 AI 侧（AI ⊇ 前端）：
    #   两个 handler **直接复用** ``AssetsMixin.assets_library`` / ``assets_delete``，
    #   与前端走同一段代码、同一套闸门口径（不重写判定，避免两边口径漂移）。
    # ----------------------------------------------------------------
    def agent_assets(self, limit: str = "", include_stale: str = "", view: str = "",
                     q: str = "", resource_id: str = "", sort: str = "",
                     cursor: str = "", group_by: str = "") -> Dict[str, Any]:
        """``GET /agent/assets`` —— 库内资产列表（只读，★ 资产/资源粒度；15.19.0 起 AI 读取面）。

        与前端 ``GET /assets`` **同源同口径**（同一份 ``AssetsMixin._asset_rows``）。
        15.19.0（Master 2026-10-12「我有哪些资源、他们的情况」）：默认 **summary 瘦身视图 +
        50 条分页** —— 全量 239 份 ≈ 390KB 会撞 MCP 单次结果 30k 上限（原来只能看到前 19 份）。
        清单问题：默认视图翻页（``cursor=next_cursor``）或 ``group_by=site`` 聚合；
        单份详情：``resource_id=<fp:…>``；旧完整粒度：``view=full``。
        """
        t0 = time.time()
        _raw = str(limit or "").strip()
        try:
            _lim = int(_raw) if _raw else 50
        except Exception:  # noqa: BLE001
            return self._agent_err("bad_request", "limit 必须是整数（0 = 全部）", t0, field="limit")
        _stale = 1 if str(include_stale or "").strip().lower() in ("1", "true", "yes", "y", "on") else 0
        try:
            resp = self.assets_view(view=(view or "summary"), q=(q or ""),
                                    resource_id=(resource_id or ""), sort=(sort or "size"),
                                    limit=_lim, cursor=(cursor or ""),
                                    include_stale=_stale, group_by=(group_by or ""))
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal_error", f"库内资产列表失败: {e}", t0)
        if not getattr(resp, "success", False):
            return self._agent_err("bad_request", str(getattr(resp, "message", "") or "列表失败"), t0)
        data = getattr(resp, "data", None) or {}
        out = dict(data or {})
        out.setdefault("message", str(getattr(resp, "message", "") or ""))
        return self._agent_ok(out, t0)

    def agent_assets_delete(self, resource_ids: str = "", hashes: str = "", delete_files: str = "",
                            confirm: str = "", reason: str = "") -> Dict[str, Any]:
        """``POST /agent/assets/delete`` —— ★删除库内资产（写，15.8.15 / 2026-10-10）。

        ★ 删的是**整个资源**：``resource_ids`` 指定的每份资源，把它**全部在下载器的种**
        （本体 + 各站所有辅种）**一次批量删**；``delete_files=1`` 连文件删。
        一次删全组 → 文件不再被别的种共用 → 内置共享护栏不会再把连文件删降级成只摘种。

        **只破「库内资产（已入库，永不删）」这一道闸**；手动保留 / 跨站来源份 / 已认领 /
        欠 H&R 四类照旧硬拦（真删前还会重新过一遍闸门复检）。``confirm`` 非 1 → 干跑（零写入）。
        """
        t0 = time.time()
        rids = [x for x in str(resource_ids or "").replace(",", " ").split() if x]
        _truthy = ("1", "true", "yes", "y", "on")
        if not rids:
            hs = [x for x in str(hashes or "").replace(",", " ").split() if x]
            if not hs:
                return self._agent_err("bad_request", "resource_ids 为空（逗号/空格分隔的资源 id）",
                                       t0, field="resource_ids")
        else:
            hs = []
        try:
            from ..models import MagicFlowAssetDeletePayload  # noqa: WPS433
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal_error", f"请求模型不可用: {e}", t0)
        payload = MagicFlowAssetDeletePayload(
            resource_ids=rids,
            hashes=hs,
            delete_files=1 if str(delete_files or "").strip().lower() in _truthy else 0,
            confirm=1 if str(confirm or "").strip().lower() in _truthy else 0,
            reason=str(reason or "")[:200],
        )
        try:
            resp = self.assets_delete(payload)
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal_error", f"删除库内资产失败: {e}", t0)
        data = getattr(resp, "data", None) or {}
        if not getattr(resp, "success", False):
            return self._agent_err("bad_request", str(getattr(resp, "message", "") or "删除失败"), t0)
        return self._agent_ok({
            "dry_run": bool(data.get("dry_run", True)),
            "deleted": int(data.get("deleted") or 0),
            "blocked": int(data.get("blocked") or 0),
            "failed": int(data.get("failed") or 0),
            "results": data.get("results") or [],
            "note": str(getattr(resp, "message", "") or ""),
        }, t0)
