#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · MCP 工具描述 / 参数类型 / 截断护栏（preflight 第 15 步）。

离线可跑（无需 MoviePilot，也不需要真 pydantic：pydantic 用最小替身，只记录字段类型）。
真机侧验证见 ``docs/AGENT-API.md`` §C.9（``tools/list`` 数数 + ``tools/call`` 看截断说明）；
本步把「改描述 / 改类型表 / 改截断逻辑会不会悄悄改坏」钉在护栏里：

  * **数量**：端点 79 / ``CORE_TOOLS`` 55 / ``build_agent_tools("core")`` = 56（55 具名 + 万能），名字唯一；
  * **描述**：≤ ``_DESC_MAX``、以读写标记开头、不含「参数：」（参数只进 args_schema）、
    返回值段与 spec.returns 一致、写工具的标记与是否带 confirm/dry_run 对得上；
  * **类型**：``_PARAM_TYPES`` 只允许 bool/int/float 三种，且每个参数在对应 inputSchema 里落型正确；
  * **截断**：``_to_text`` 超长 → 合法 JSON + 顶层 ``_truncated`` + ≤ ``RESULT_MAX_CHARS``；
    短响应原样返回；根是裸标量也能降级。

用法：``python3 tools/check_mcptools_desc.py``（0=通过 / 1=有问题）。
"""
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_mcptools_desc_check"

_ERRORS: list = []


def _fail(msg: str) -> None:
    _ERRORS.append(msg)


def _pkg(name: str, path: Path) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m
    return m


def _load(name: str, rel: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _StubSchema:
    """pydantic ``create_model`` 的替身：只留下 ``字段名 -> (类型, 描述)``。"""

    def __init__(self, name: str, fields: dict):
        self.name = name
        self.fields = fields


def _stub_deps() -> None:
    """stub ``app.*`` / ``pydantic`` / ``langchain_core``（mcptools 顶层的宿主依赖）。"""
    for name, attrs in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
        ("app.agent", {}),
        ("app.agent.tools", {}),
        ("app.agent.tools.base", {"MoviePilotTool": type("MoviePilotTool", (), {})}),
        ("langchain_core", {}),
        ("langchain_core.tools", {"BaseTool": type("BaseTool", (), {})}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attrs.items():
            setattr(m, k, v)

    pyd = types.ModuleType("pydantic")
    pyd.Field = lambda *a, **k: None  # noqa: E731
    pyd.create_model = lambda name, **fields: _StubSchema(name, fields)  # noqa: E731
    sys.modules["pydantic"] = pyd


def _load_mcptools():
    _stub_deps()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    for modname, attrs in (
        ("bonus", ("TorrentBonusInfo",)),
        ("fingerprint", ("fingerprint", "inner_fingerprint", "load_torrent_entries", "total_size")),
        ("fetcher", ("SiteCandidateTorrent",)),
        ("recommend", ("recognize",)),
    ):
        m = types.ModuleType(PKG + "." + modname)
        for a in attrs:
            setattr(m, a, object)
        sys.modules[PKG + "." + modname] = m
    _load(PKG + ".common", "common.py")
    _load(PKG + ".features.pool", "features/pool.py")
    _load(PKG + ".features.api", "features/api.py")
    _load(PKG + ".features.agentapi", "features/agentapi.py")
    return _load(PKG + ".features.mcptools", "features/mcptools.py")


def _check_counts(mc) -> None:
    if not (0 < mc._DESC_MAX <= 1000):
        _fail(f"_DESC_MAX = {mc._DESC_MAX}，越界（工具描述上限是 1000 字符；调大要同步改文档与真机基线）")
    if not (1000 < mc.RESULT_MAX_CHARS <= 60000):
        _fail(f"RESULT_MAX_CHARS = {mc.RESULT_MAX_CHARS}，越界（1k~60k 之外不合理）")
    index = mc._spec_index()
    if len(index) != 79:
        _fail(f"端点真值源 = {len(index)}，期望 79（_agent_endpoints() 变了就同步改本护栏与文档）")
    if len(mc.CORE_TOOLS) != 55:
        _fail(f"CORE_TOOLS = {len(mc.CORE_TOOLS)}，期望 55")
    names = [n for _p, n in mc.CORE_TOOLS]
    if len(set(names)) != len(names):
        _fail("CORE_TOOLS 有重名工具名")
    tools = mc.build_agent_tools("core")
    got = [t.name for t in tools]
    if len(got) != 56:
        _fail(f'build_agent_tools("core") = {len(got)} 个，期望 56（55 具名 + magicflow_agent_api）')
    if len(set(got)) != len(got):
        _fail(f"工具名重复：{sorted({n for n in got if got.count(n) > 1})}")
    want = set(names) | {"magicflow_agent_api"}
    if set(got) != want:
        _fail(f'具名工具集合与 CORE_TOOLS 不一致：多 {sorted(set(got) - want)} / 少 {sorted(want - set(got))}')
    missing = [p for p, _n in mc.CORE_TOOLS if p not in index]
    if missing:
        _fail(f"CORE_TOOLS 里的路径不在能力清单里（tool_names 会静默漏掉）：{missing}")
    print(f"  ▸ 端点 {len(index)} / CORE_TOOLS {len(names)} / core 工具 {len(got)}（含万能）")


def _check_descriptions(mc) -> None:
    index = mc._spec_index()
    n = 0
    for tool in mc.build_agent_tools("core"):
        spec = index.get(_path_of(mc, tool.name), {})
        d = str(getattr(tool, "description", "") or "")
        n += 1
        if tool.name == "magicflow_agent_api":
            # 万能兜底**不带读写标记**（它既能读也能写，且没有单一 spec）：靠「万能兜底」自述 +
            # write/admin 标签（门禁 fail-safe）。这里只钉住这两点，别让它被当成普通工具。
            if "万能兜底" not in d:
                _fail("magicflow_agent_api: 描述必须自述「万能兜底」（模型要知道它是兜底入口）")
            if "write" not in list(getattr(tool, "tags", []) or []):
                _fail("magicflow_agent_api: tags 必须含 write（它能调写端点，门禁要 fail-safe）")
            continue
        if len(d) > mc._DESC_MAX:
            _fail(f"{tool.name}: 描述 {len(d)} 字符 > _DESC_MAX({mc._DESC_MAX})（会被上游截断）")
        if not (d.startswith("[读]") or d.startswith("[写·")):
            _fail(f"{tool.name}: 描述没有前置读写标记：{d[:40]!r}")
        if "参数：" in d:
            _fail(f"{tool.name}: 描述里又出现「参数：」（参数只进 args_schema）")
        ret = str(spec.get("returns") or "").strip()
        if ret and f"｜返回 {ret}" not in d:
            _fail(f"{tool.name}: 描述缺少「｜返回 {ret}」段（超长被砍掉？）")
        exp = mc._write_mark(spec)
        if not d.startswith(exp):
            _fail(f"{tool.name}: 读写标记 {d.split(' ')[0]!r} ≠ 期望 {exp!r}")
    print(f"  ▸ 逐条描述断言通过（{n} 条：标记前置 / ≤{mc._DESC_MAX} / 无「参数：」/ 返回段与标记一致）")


def _path_of(mc, tool_name: str) -> str:
    for path, name in mc.CORE_TOOLS:
        if name == tool_name:
            return path
    return ""


def _scalar(typ) -> str:
    """``Optional[bool]`` → ``boolean``（pydantic 落进 JSON Schema 的名字）。"""
    origin = getattr(typ, "__args__", ())
    inner = origin[0] if origin else typ
    return {bool: "boolean", int: "integer", float: "number", str: "string"}.get(inner, str(inner))


def _check_types(mc) -> None:
    allowed = {Optional[bool], Optional[int], Optional[float], Optional[str]}
    #: 类型表的**钉子**：这些开关/数值参数必须显式落型（删键 = 静默退回字符串 → 模型传 "1" 靠 handler 归一化兜）。
    required = {"confirm", "dry_run", "live", "verify", "force", "force_asset", "reuse_only",
                "adopt_reseed", "include_pass", "include_stale", "resolve_paths", "full",
                "delete_files", "budget_gb", "season"}
    if set(mc._PARAM_TYPES) != required:
        _fail(f"_PARAM_TYPES 键集变了：多 {sorted(set(mc._PARAM_TYPES) - required)} / "
              f"少 {sorted(required - set(mc._PARAM_TYPES))}（改表要同步改本护栏与 docs/AGENT-API.md §C.9）")
    for name, typ in mc._PARAM_TYPES.items():
        if typ not in allowed:
            _fail(f"_PARAM_TYPES[{name!r}] 类型 {typ} 不在白名单（bool/int/float）")
        if typ is Optional[str]:
            _fail(f"_PARAM_TYPES 不该收字符串参数（默认就是 str）：{name!r}")
    seen: dict = {}
    for tool in mc.build_agent_tools("all"):
        schema = getattr(tool, "args_schema", None)
        for pname, (typ, _doc) in (getattr(schema, "fields", {}) or {}).items():
            if pname in mc._PARAM_TYPES:
                seen.setdefault(pname, []).append(_scalar(typ))
    for name, typ in mc._PARAM_TYPES.items():
        if name not in seen:
            _fail(f"_PARAM_TYPES[{name!r}] 在 79 个端点的参数里没出现（表里有僵尸键？）")
            continue
        want = _scalar(typ)
        bad = sorted({g for g in seen[name] if g != want})
        if bad:
            _fail(f"参数 {name!r} 落成 {bad}，期望 {want}（_field_type 没吃到 _PARAM_TYPES？）")
    print(f"  ▸ 类型表断言通过（{len(mc._PARAM_TYPES)} 个参数在 scope=all 的 schema 里落型正确）")


def _check_truncation(mc) -> None:
    cap = mc.RESULT_MAX_CHARS
    small = {"ok": True, "data": {"n": 1, "items": [1, 2, 3]}}
    if mc._to_text(small) != json.dumps(small, ensure_ascii=False, default=str):
        _fail("_to_text 把短响应也改写了（应当原样返回）")
    cases = {
        "长列表（silent 形态）": {"ok": True, "data": {"items": [{"hash": "a" * 40} for _ in range(3000)]}},
        "长列表 + 长文本（recommend 形态）": {"ok": True, "data": {"items": [{"t": "x" * 400} for _ in range(900)],
                                                          "records": [{"m": "y" * 300} for _ in range(400)]}},
        "超大单字符串": {"ok": True, "data": {"hint": "z" * 200000}},
        "根是裸标量": "w" * 40000,
    }
    for label, payload in cases.items():
        text = mc._to_text(payload)
        if len(text) > cap and not text.startswith('{"_truncated"'):
            _fail(f"{label}: 降级后 {len(text)} 字符 > {cap} 且不是包裹形态")
        try:
            obj = json.loads(text)
        except Exception as err:  # noqa: BLE001
            _fail(f"{label}: 降级结果不是合法 JSON（{type(err).__name__}: {err}）")
            continue
        if not isinstance(obj, dict) or mc.TRUNC_KEY not in obj:
            _fail(f"{label}: 降级结果缺顶层 {mc.TRUNC_KEY} 说明")
            continue
        note = obj[mc.TRUNC_KEY]
        if not isinstance(note, dict) or "original_chars" not in note:
            _fail(f"{label}: {mc.TRUNC_KEY} 说明缺 original_chars")
        if isinstance(payload, dict):
            keep = set(payload) - {mc.TRUNC_KEY}
            if not keep.issubset(set(obj)):
                _fail(f"{label}: 降级把业务顶层字段弄丢了：{sorted(keep - set(obj))}")
    print(f"  ▸ 截断断言通过（4 种形态 → 合法 JSON + {mc.TRUNC_KEY} + ≤{cap}）")


def main() -> int:
    try:
        mc = _load_mcptools()
    except Exception as err:  # noqa: BLE001
        print(f"❌ 加载 features/mcptools.py 失败：{type(err).__name__}: {err}")
        return 1
    _check_counts(mc)
    _check_descriptions(mc)
    _check_types(mc)
    _check_truncation(mc)
    if _ERRORS:
        print(f"❌ MCP 工具描述护栏失败（{len(_ERRORS)} 条）：")
        for e in _ERRORS:
            print(f"   • {e}")
        return 1
    print("✅ MCP 工具描述/类型/截断护栏通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
