# -*- coding: utf-8 -*-
"""魔流 · mcptools —— 把「AI 入口」注册进 MoviePilot Agent / MCP（★ 15.11.0）。

Master 2026-10-11：「我说的就是我们 agent 里面的东西可以注册到这个 mcp 里面，点播什么的」

MP v3 的插件可以实现 ``get_agent_tools()`` 返回 ``MoviePilotTool`` 子类，这些工具会进
**MoviePilot 内置 Agent** 和 **MCP server**（``POST /api/v1/mcp``，认证 ``X-API-Key: API_TOKEN``）。

本模块把 ``_agent_endpoints()``（**唯一真值源**）里的端点机械地包成工具，不手抄一遍参数：

- ``scope="core"``（默认）：常用业务工具（任务/站点/账单/H&R/补源/点播/库内资源/推荐/音乐/队列/设置…）
- ``scope="all"``：76 个端点全注册（= ``_agent_endpoints()`` 当前条数）
- 另附万能 ``magicflow_agent_api``：按 path 调**任意已登记** ``/agent/*`` 端点（含未进 core 的）

约定
----
- 工具名 ``magicflow_<名字>``（core 用显式表；all 由路径派生）——稳定，改 = 破坏外部集成
- 描述 = 读写标记（**前置**，永不被截断）+ 一句话「什么时候用」+ 返回类型；
  参数说明**只进 ``args_schema``**（描述里不再重复 → 省掉约 1/3 文本，也不会两处漂移）
- 写工具打 ``write`` 标签（MP 策略层可据此门禁），读工具打 ``read``
- 同步 handler 走 ``asyncio.to_thread``（不阻塞事件循环）；异步 handler 直接 ``await``
- 插件实例经 ``PluginManager().running_plugins["MagicFlow"]`` 取（与 AgentResourceOfficer 同款）
- 结果统一 ``JSON`` 文本（``Response`` → ``model_dump()``）；超 ``RESULT_MAX_CHARS`` 时
  **结构化降级**（裁剪最长列表/长文本 + 顶层 ``_truncated`` 说明，仍是合法 JSON），不再切字符串
"""

import asyncio
import inspect
import json
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field, create_model

from .agentapi import _agent_endpoints

PLUGIN_ID = "MagicFlow"
RESULT_MAX_CHARS = 30000

#: 默认注册的「能干活」端点 → 工具名（显式表 = 稳定契约；未列入的可走 magicflow_agent_api）
CORE_TOOLS: Tuple[Tuple[str, str], ...] = (
    # ---- 观察 / 排障 ----
    ("/agent/overview", "magicflow_overview"),
    ("/agent/state", "magicflow_state"),
    ("/agent/health", "magicflow_health"),
    ("/agent/tasks", "magicflow_tasks"),
    ("/agent/tasks/{id}", "magicflow_task_detail"),
    ("/agent/pool", "magicflow_pool"),
    ("/agent/decide", "magicflow_decide"),
    ("/agent/cleanup/preview", "magicflow_cleanup_preview"),
    ("/agent/optimize", "magicflow_optimize"),
    ("/agent/plan", "magicflow_plan"),
    ("/agent/plan/apply", "magicflow_plan_apply"),
    ("/agent/bills", "magicflow_bills"),
    ("/agent/ledger/{table}", "magicflow_ledger"),
    # ---- 站点 / H&R ----
    ("/agent/live", "magicflow_live"),
    ("/agent/site/seeds", "magicflow_site_seeds"),
    ("/agent/hr/bills", "magicflow_hr_bills"),
    ("/agent/notify", "magicflow_notify"),
    ("/agent/notify/act", "magicflow_notify_act"),
    ("/agent/trend/why", "magicflow_trend_why"),
    ("/agent/trend/daily", "magicflow_trend_daily"),
    ("/agent/blindspot", "magicflow_hr_blindspot"),
    ("/agent/sites/deleted", "magicflow_deleted_sites"),
    # ---- 补源 ----
    ("/agent/rescue", "magicflow_rescue"),
    ("/agent/rescue/candidates", "magicflow_rescue_candidates"),
    # ---- 点播 ----
    ("/agent/ondemand", "magicflow_ondemand"),
    ("/agent/ondemand/search", "magicflow_ondemand_search"),
    ("/agent/ondemand/add", "magicflow_ondemand_add"),
    # ---- 库内资源 / 推荐 ----
    ("/agent/assets", "magicflow_assets"),
    ("/agent/recommend", "magicflow_recommend"),
    # ---- 音乐 ----
    ("/agent/music/search", "magicflow_music_search"),
    ("/agent/music/items", "magicflow_music_items"),
    # ---- 运维 ----
    ("/agent/jobs", "magicflow_jobs"),
    ("/agent/settings", "magicflow_settings"),
    # ---- 写（会动下载器/账本/订阅）----
    ("/agent/ondemand/act", "magicflow_ondemand_act"),
    ("/agent/assets/act", "magicflow_assets_act"),
    ("/agent/assets/delete", "magicflow_assets_delete"),
    ("/agent/recommend/act", "magicflow_recommend_act"),
    ("/agent/music/download", "magicflow_music_download"),
    ("/agent/music/act", "magicflow_music_act"),
    ("/agent/silent/enforce", "magicflow_silent_enforce"),
    ("/agent/tags/reconcile", "magicflow_tags_reconcile"),
    ("/agent/yema/absolve", "magicflow_yema_absolve"),
    ("/agent/sites/deleted/act", "magicflow_deleted_sites_act"),
    # ---- 功能页（新手考核 / 签到 / 云盘归档 / 豆瓣 / 跨站取种 / 操作记录 / 野马PT / 静默池）----
    ("/agent/exam", "magicflow_exam"),
    ("/agent/exam/act", "magicflow_exam_act"),
    ("/agent/signin", "magicflow_signin"),
    ("/agent/cloud", "magicflow_cloud"),
    ("/agent/douban", "magicflow_douban"),
    ("/agent/crossseed", "magicflow_crossseed"),
    ("/agent/operations", "magicflow_operations"),
    ("/agent/yema", "magicflow_yema"),
    ("/agent/silent", "magicflow_silent"),
)

#: 领域标签（方便 MP 策略按域门禁）
_DOMAIN_TAGS = (
    ("/agent/ondemand", "download"),
    ("/agent/ondemand/search", "site"),
    ("/agent/exam", "site"),
    ("/agent/signin", "site"),
    ("/agent/crossseed", "site"),
    ("/agent/douban", "recommendation"),
    ("/agent/cloud", "library"),
    ("/agent/site/", "site"),
    ("/agent/sites", "site"),
    ("/agent/hr", "site"),
    ("/agent/yema", "site"),
    ("/agent/blindspot", "site"),
    ("/agent/bills", "site"),
    ("/agent/rescue", "site"),
    ("/agent/assets", "library"),
    ("/agent/recommend", "recommendation"),
    ("/agent/music", "media"),
    ("/agent/silent", "download"),
    ("/agent/tags", "settings"),
    ("/agent/settings", "settings"),
    ("/agent/jobs", "system"),
)


def _spec_index() -> Dict[str, Dict[str, Any]]:
    """``path -> spec``（含 handler/write/params/summary）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for spec in _agent_endpoints():
        try:
            out[str(spec.get("path") or "")] = dict(spec)
        except Exception:  # noqa: BLE001
            continue
    return out


def _slug_from_path(path: str) -> str:
    """``/agent/tasks/{id}`` → ``tasks_by_id``（scope=all 时的兜底命名）。"""
    raw = str(path or "").strip("/")
    if raw.startswith("agent/"):
        raw = raw[len("agent/"):]
    slug = raw.replace("{", "by_").replace("}", "")
    slug = slug.replace("/", "_").replace("-", "_")
    return "magicflow_" + "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in slug)


#: 参数名 → 显式类型真值：说明首词判不出型的开关/数值参数（文档写的是「1=真做；0/缺省=干跑」）。
#: 已逐个核对 handler 侧归一化（``int(x or 0)`` / ``str(x).lower() in ("1","true",…)`` / ``_truthy``），
#: 传 bool/int 与传 "1"/"0" 等价；不在此表的一律按字符串（不改既有语义）。
_PARAM_TYPES: Dict[str, Any] = {
    "confirm": Optional[bool],
    "dry_run": Optional[bool],
    "live": Optional[bool],
    "verify": Optional[bool],
    "force": Optional[bool],
    "force_asset": Optional[bool],
    "reuse_only": Optional[bool],
    "adopt_reseed": Optional[bool],
    "include_pass": Optional[bool],
    "include_stale": Optional[bool],
    "resolve_paths": Optional[bool],
    "full": Optional[bool],
    "delete_files": Optional[int],
    "budget_gb": Optional[float],
    "season": Optional[int],
}


def _field_type(doc: str, name: str = "") -> Any:
    """参数类型：先查 ``_PARAM_TYPES`` 显式真值，再退回「说明首词」启发式。"""
    forced = _PARAM_TYPES.get(str(name or "").strip())
    if forced is not None:
        return forced
    head = str(doc or "").strip().lower()
    if head.startswith("int"):
        return Optional[int]
    if head.startswith("float"):
        return Optional[float]
    if head.startswith("bool"):
        return Optional[bool]
    return Optional[str]


def _args_schema(spec: Dict[str, Any], tool_name: str):
    """按 spec.params 造 pydantic 输入模型（全可选；None 不下传，保持 handler 默认值）。"""
    fields: Dict[str, Any] = {}
    for pname, doc in (spec.get("params") or {}).items():
        name = str(pname or "").strip()
        if not name.isidentifier() or name in ("self", "kwargs"):
            continue
        fields[name] = (_field_type(str(doc or ""), name), Field(default=None, description=str(doc or "")))
    if not fields:
        return None
    model_name = "".join(part.capitalize() for part in str(tool_name).split("_")) + "Input"
    try:
        return create_model(model_name, **fields)
    except Exception:  # noqa: BLE001
        return None


def _tags_for(spec: Dict[str, Any], path: str) -> List[str]:
    tags = ["write"] if spec.get("write") else ["read"]
    for prefix, tag in _DOMAIN_TAGS:
        if str(path).startswith(prefix):
            tags.append(tag)
            break
    return tags


_DESC_MAX = 1000


def _write_mark(spec: Dict[str, Any]) -> str:
    """读写标记（前置：模型第一眼就看到「这工具会不会动真格」）。"""
    if not spec.get("write"):
        return "[读]"
    params = spec.get("params") or {}
    if "confirm" in params:
        return "[写·需 confirm=1]"
    if "dry_run" in params:
        return "[写·默认干跑]"
    return "[写·即时生效]"


def _describe(spec: Dict[str, Any], path: str) -> str:
    """工具描述：``标记 + 魔流 · 什么时候用（summary）|> 返回类型``。

    参数说明**不进描述**（只由 ``_args_schema`` 落到 ``inputSchema.properties[*].description``）
    —— 两处都写会重复约 1/3 文本，且必然漂移。超长时**只砍尾部**：读写标记与首句永远保留。
    """
    head = f"{_write_mark(spec)} 魔流 · {str(spec.get('summary') or path).strip()}"
    ret = str(spec.get("returns") or "").strip()
    tail = f"｜返回 {ret}" if ret else ""
    if len(head) + len(tail) <= _DESC_MAX:
        return head + tail
    return head[: max(0, _DESC_MAX - len(tail))] + tail


def _label(spec: Dict[str, Any]) -> str:
    """UI 进度行短标签：summary 的「场景」段（首个 ``：`` 或 ``（`` 之前），≤40 字。"""
    text = str(spec.get("summary") or "").strip()
    cuts = [i for i in (text.find("："), text.find("（")) if i > 0]
    return text[: min(cuts) if cuts else len(text)][:40] or "魔流"


#: 结构化降级说明的键名（模型据此知道「少看了什么」，而不是拿到半个 JSON）
TRUNC_KEY = "_truncated"


def _collect_nodes(obj: Any, path: str, parent: Any, key: Any,
                   out: List[Tuple[str, int, str, Any, Any]]) -> None:
    """收集可裁剪节点 ``(kind, size, json_path, parent, key)``（parent 为容器，None=根、不可剪）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _collect_nodes(v, f"{path}.{k}", obj, k, out)
    elif isinstance(obj, list):
        if parent is not None:
            out.append(("list", len(obj), path, parent, key))
        for i, v in enumerate(obj):
            _collect_nodes(v, f"{path}[{i}]", obj, i, out)
    elif isinstance(obj, str) and parent is not None:
        out.append(("str", len(obj), path, parent, key))


def _with_note(obj: Any, orig: int, dropped: Dict[str, int], trimmed: Dict[str, int]) -> str:
    """把「裁了什么」写成 ``_truncated``（放在顶层，与业务字段区分）。"""
    note: Dict[str, Any] = {
        "original_chars": orig,
        "hint": ("结果超过单次上限：已裁剪最长的列表/长文本（保留前面条目），**不是全量**；"
                 "要全量请用 limit / records / cursor / days 等参数缩小范围后分页取"),
    }
    if dropped:
        note["dropped_items"] = dropped
    if trimmed:
        note["trimmed_strings"] = trimmed
    if isinstance(obj, dict):
        out = dict(obj)
        out[TRUNC_KEY] = note
        return json.dumps(out, ensure_ascii=False, default=str)
    return json.dumps({TRUNC_KEY: note, "preview": obj}, ensure_ascii=False, default=str)


def _fit_text(text: str) -> Optional[str]:
    """超长结果的**结构化降级**：裁剪最长列表/最长字符串 + 顶层注入 ``_truncated`` 说明。

    永远返回**合法 JSON**。旧实现直接 ``text[:N] + "…（已截断）"`` → 尾巴是半个 token，
    模型只能看到一坨无法解析的文本（实测 ``magicflow_silent`` / ``magicflow_recommend``
    都在 30k 处被切在对象中间）。收敛策略：反复把最长的 list 砍半（见底后转砍最长字符串）。
    返回 ``None`` = 实在降不下来，调用方退回旧的头部截断。
    """
    try:
        obj = json.loads(text)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(obj, (dict, list)):   # 根是裸标量：包一层，好让它也能被裁剪
        obj = {"preview": obj}
    orig = len(text)
    dropped: Dict[str, int] = {}
    trimmed: Dict[str, int] = {}
    frozen: set = set()
    for _ in range(80):
        nodes: List[Tuple[str, int, str, Any, Any]] = []
        _collect_nodes(obj, "$", None, None, nodes)
        cand = [n for n in nodes if n[1] > 1 and n[2] not in frozen]
        lists = [n for n in cand if n[0] == "list"]
        if lists:
            _kind, _size, path, parent, key = max(lists, key=lambda n: n[1])
            node = parent[key]
            keep = max(1, len(node) // 2)
            dropped[path] = dropped.get(path, 0) + (len(node) - keep)
            parent[key] = node[:keep]
            if keep <= 1:
                frozen.add(path)
        else:
            strs = [n for n in cand if n[0] == "str"]
            if not strs:
                break
            _kind, _size, path, parent, key = max(strs, key=lambda n: n[1])
            s = str(parent[key])
            keep = max(64, len(s) // 2)
            trimmed[path] = trimmed.get(path, 0) + (len(s) - keep)
            parent[key] = s[:keep] + "…"
            if len(parent[key]) >= len(s):
                frozen.add(path)
        fitted = _with_note(obj, orig, dropped, trimmed)
        if len(fitted) <= RESULT_MAX_CHARS:
            return fitted
    fitted = _with_note(obj, orig, dropped, trimmed)
    if len(fitted) <= RESULT_MAX_CHARS * 2:
        return fitted
    return None


def _to_text(res: Any) -> str:
    if res is None:
        return "{}"
    if hasattr(res, "model_dump"):
        try:
            res = res.model_dump()
        except Exception:  # noqa: BLE001
            pass
    elif not isinstance(res, dict) and hasattr(res, "dict"):
        try:
            res = res.dict()
        except Exception:  # noqa: BLE001
            pass
    try:
        text = json.dumps(res, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        text = str(res)
    if len(text) > RESULT_MAX_CHARS:
        fitted = _fit_text(text)
        if fitted is not None:
            return fitted
        text = text[:RESULT_MAX_CHARS] + f"...（已截断，原长 {len(text)}）"
    return text


def _plugin():
    """取运行中的魔流插件实例（未运行时 None）。"""
    from app.sdk.plugins import PluginManager  # noqa: WPS433
    running = getattr(PluginManager(), "running_plugins", None) or {}
    return running.get(PLUGIN_ID) or running.get("magicflow")


async def _call(handler: str, kwargs: Dict[str, Any]) -> str:
    """调插件 handler（同步→线程池，异步→await），统一 JSON 文本返回。"""
    plugin = _plugin()
    if plugin is None:
        return json.dumps({"success": False, "message": "魔流插件未运行（未启用/未加载）"},
                          ensure_ascii=False)
    fn = getattr(plugin, handler, None)
    if not callable(fn):
        return json.dumps({"success": False, "message": f"端点在当前版本未实现：{handler}"},
                          ensure_ascii=False)
    args = {k: v for k, v in (kwargs or {}).items() if v is not None and str(k) != "self"}
    try:
        if inspect.iscoroutinefunction(fn):
            res = await fn(**args)
        else:
            res = await asyncio.to_thread(lambda: fn(**args))
    except Exception as err:  # noqa: BLE001
        return json.dumps({"success": False, "message": f"{type(err).__name__}: {err}"},
                          ensure_ascii=False)
    return _to_text(res)


def _make_tool(tool_name: str, description: str, schema: Any, tags: List[str],
               handler: str, label: str):
    """动态造一个 MoviePilotTool 子类（带注解，pydantic v2 才认字段覆盖）。"""
    from app.agent.tools.base import MoviePilotTool  # noqa: WPS433
    from langchain_core.tools import BaseTool  # noqa: WPS433

    async def run(self, **kwargs) -> str:  # noqa: D401
        """调魔流 AI 入口。"""
        return await _call(handler, kwargs)

    def get_tool_message(self, **kwargs) -> str:  # noqa: ARG001
        return f"魔流：{label}"

    cls_name = "".join(part.capitalize() for part in str(tool_name).split("_")) + "Tool"
    ns: Dict[str, Any] = {
        "__doc__": description,
        "__module__": __name__,
        "__annotations__": {"name": str, "description": str,
                            "args_schema": Optional[type], "tags": List[str]},
        "name": tool_name,
        "description": description,
        "args_schema": schema,
        "tags": list(tags),
        "run": run,
        "get_tool_message": get_tool_message,
        "_mf_handler": handler,
    }
    if schema is None:
        ns["__annotations__"].pop("args_schema", None)
        ns.pop("args_schema", None)
    base = MoviePilotTool if issubclass(MoviePilotTool, BaseTool) else BaseTool
    return type(cls_name, (base,), ns)


def _generic_tool(paths: List[str], covered: Optional[List[str]] = None):
    """万能入口：``magicflow_agent_api(path, params)`` —— 调任意**已登记**的 /agent 端点。

    描述里**只列没有具名工具的端点**（其余端点让模型优先走具名工具：参数带类型、语义更明确）。
    """
    all_paths = sorted(paths)
    extra = [p for p in all_paths if p not in set(covered or [])]
    listing = ("仅这些端点没有具名工具（有具名工具就优先用它）：" + ", ".join(extra)) if extra \
        else "全部端点都有具名工具；本入口只作按路径兜底。"
    desc = ("魔流：按端点路径直接调用魔流 AI 入口（万能兜底）。"
            "path 必须是已登记端点（要全量清单就调 path=/agent）；params 为对象或 JSON 字符串，"
            "键名与端点参数一致；写端点同样需要各自参数（如 confirm=1）。"
            f" | {listing}")
    schema = create_model(
        "MagicFlowAgentApiInput",
        path=(str, Field(..., description="已登记的 /agent 端点路径，如 /agent/schema")),
        params=(Optional[dict], Field(default=None, description="端点参数（对象；键名同端点参数）")),
    )

    async def run(self, path: str = "", params: Any = None, **kwargs) -> str:
        target = str(path or "").strip()
        if not target.startswith("/agent"):
            target = "/agent/" + target.lstrip("/")
        spec = _spec_index().get(target)
        if spec is None:
            return json.dumps({"success": False,
                               "message": f"未登记的端点：{target}", "available": all_paths},
                              ensure_ascii=False)
        data = params
        if isinstance(data, str) and data.strip():
            try:
                data = json.loads(data)
            except Exception:  # noqa: BLE001
                return json.dumps({"success": False, "message": "params 不是合法 JSON"},
                                  ensure_ascii=False)
        if not isinstance(data, dict):
            data = {}
        return await _call(str(spec.get("handler") or ""), data)

    def get_tool_message(self, **kwargs) -> str:  # noqa: ARG001
        return f"魔流：调用 {kwargs.get('path') or ''}"

    from app.agent.tools.base import MoviePilotTool  # noqa: WPS433
    return type("MagicFlowAgentApiTool", (MoviePilotTool,), {
        "__doc__": desc,
        "__module__": __name__,
        "__annotations__": {"name": str, "description": str, "args_schema": Optional[type],
                            "tags": List[str]},
        "name": "magicflow_agent_api",
        "description": desc,
        "args_schema": schema,
        "tags": ["write", "admin"],
        "run": run,
        "get_tool_message": get_tool_message,
        "_mf_handler": "",
    })


def build_agent_tools(scope: str = "core", include_generic: bool = True) -> List[Any]:
    """造工具类列表（MP ``get_agent_tools()`` 的返回值）。"""
    index = _spec_index()
    all_paths = list(index.keys())
    pairs: List[Tuple[str, str]] = []
    if str(scope or "core").strip().lower() == "all":
        pairs = [(p, _slug_from_path(p)) for p in all_paths]
    else:
        pairs = [(p, n) for p, n in CORE_TOOLS if p in index]
    tools: List[Any] = []
    for path, tool_name in pairs:
        spec = index.get(path) or {}
        schema = _args_schema(spec, tool_name)
        try:
            tools.append(_make_tool(tool_name, _describe(spec, path), schema,
                                    _tags_for(spec, path), str(spec.get("handler") or ""),
                                    _label(spec)))
        except Exception:  # noqa: BLE001
            continue
    if include_generic and str(scope or "core").strip().lower() != "all":
        try:
            tools.append(_generic_tool(all_paths, [p for p, _ in pairs]))
        except Exception:  # noqa: BLE001
            pass
    return tools


def tool_names(scope: str = "core") -> List[str]:
    """工具名清单（自检/文档用，不依赖 MP）。"""
    index = _spec_index()
    if str(scope or "core").strip().lower() == "all":
        return [_slug_from_path(p) for p in index]
    names = [n for p, n in CORE_TOOLS if p in index]
    names.append("magicflow_agent_api")
    return names
