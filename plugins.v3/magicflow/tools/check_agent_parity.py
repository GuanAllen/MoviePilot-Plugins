#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 对齐校验（AI ⊇ 前端，P1.5e）—— 前端覆盖（下限）+ 真值源覆盖（目标）。

两条检查（与 ``check_agent_manifest.py`` 输出风格一致：✅/❌ + 计数）：

1. **前端覆盖（下限）**：扫 ``src/**`` 里所有插件 API 调用（``api.get/post/put/delete``），
   与 ``GET /agent`` 能力清单**求差**：
   - GET 读路径必须被某个 ``/agent/*`` 端点覆盖，否则必须进**豁免白名单**（写清理由）；
   - 非 GET（写）路径统一豁免为「L4 控制面（P1.6 收编）」，不在此期只读门面范围内。
   未覆盖且未豁免 → exit 1。

2. **真值源覆盖（目标）**：核对账本六表 + 运行台账五表是否都被 ``/agent/ledger/{table}``
   覆盖，漏的 → exit 1。

纯标准库 + 本地 stub，离线可跑，无需 MoviePilot。
用法：``python3 tools/check_agent_parity.py``（退出码 0=通过 / 1=失败）。
"""
import importlib.util
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mf_agent_parity_check"

# ---------------------------------------------------------------------------
# 前端 GET 读路径 → 覆盖它的 /agent 端点（意图寻址）
# ---------------------------------------------------------------------------
COVERED = {
    "/status": "/agent/overview",
    "/pool": "/agent/pool",
    "/trend": "/agent/trend",
    "/rules": "/agent/rules",
    "/health": "/agent/health",
    "/operations": "/agent/operations",
    "/tasks/{x}/operations": "/agent/operations",
    "/tasks/{x}": "/agent/tasks/{x}",
    "/rescue": "/agent/rescue",
    "/downloader/prefs": "/agent/settings",
    "/defaults": "/agent/settings",
    # ---- P1.5c 功能域只读（19 个只读豁免域收编）----
    "/tasks/{x}/bonus": "/agent/tasks/{x}/bonus",
    "/tasks/{x}/candidates": "/agent/tasks/{x}/candidates",
    "/tasks/{x}/handover": "/agent/tasks/{x}/handover",
    "/recommend": "/agent/recommend",
    "/crossseed": "/agent/crossseed",
    "/reseed": "/agent/reseed",
    "/douban_service": "/agent/douban",
    "/live": "/agent/live",
    "/signin": "/agent/signin",
    "/exam": "/agent/exam",
    "/silent/pool": "/agent/silent",
    "/claim": "/agent/claim",
    "/tags": "/agent/tags",
    "/cloud": "/agent/cloud",
    "/cloud/test": "/agent/cloud",
    "/fallback": "/agent/fallback",
    "/iyuu/sites": "/agent/iyuu",
    "/iyuu/test": "/agent/iyuu",
    "/events": "/agent/events",
    "/site/seeds": "/agent/site/seeds",
    "/ondemand/items": "/agent/ondemand",
    "/hr/bills": "/agent/hr/bills",
    "/health/scan": "/agent/seeds/health",
    "/agent/music/plan": "/agent/music/plan",
    "/agent/music/grab": "/agent/music/grab",
}

# 前端 GET 只读域 → 豁免理由（非插件端点 / MP 全局端点）
READ_WHITELIST = {
    "/site/icon/{x}": "非插件端点（MP 全局站点图标）",
}

WRITE_REASON = "写端点 → L4 /agent/act 控制面（P1.5 只读阶段不收编，P1.6 收编）"

# 真值源覆盖（目标）：账本六表 + 运行台账五表
REQUIRED_TABLES = (
    "site", "resource", "identity", "task", "seed", "deck", "crossseed",
    "bills", "deletions", "journal", "protected", "rescue_actions",
    "reseed", "run", "claim",
)


# ---------------------------------------------------------------------------
# 前端调用抽取（src/**）
# ---------------------------------------------------------------------------
def extract_calls(text: str):
    """抽取 ``api.<method>(<arg>)``，返回 ``[(method, raw_arg), ...]``。

    模板字面量里的 ``${...}`` 折叠为 ``{x}``（含嵌套反引号的 ``${sid ? `...` : ''}``
    也能正确跳过）。
    """
    out = []
    i = 0
    while True:
        m = re.search(r"(?:props\.)?api\.(get|post|put|delete)\s*\(", text[i:])
        if not m:
            break
        method = m.group(1)
        pos = i + m.end()
        while pos < len(text) and text[pos] in " \t":
            pos += 1
        if pos >= len(text) or text[pos] not in ("'", '"', "`"):
            i = pos
            continue
        q = text[pos]
        j = pos + 1
        buf = []
        while j < len(text):
            c = text[j]
            if q == "`" and text[j:j + 2] == "${":
                k = j + 2
                depth = 1
                while k < len(text) and depth > 0:
                    if text[k] == "{":
                        depth += 1
                    elif text[k] == "}":
                        depth -= 1
                    k += 1
                buf.append("{x}")
                j = k
                continue
            if c == q:
                break
            buf.append(c)
            j += 1
        out.append((method, "".join(buf)))
        i = j + 1
    return out


def normalize_path(raw: str):
    """原始参数串 → 归一化插件路径（``/xxx``；``${...}`` 折叠为 ``{x}``，剥查询与尾部查询变量）。"""
    p = str(raw).strip()
    p = re.sub(r"^plugin/MagicFlow/?", "", p)
    p = re.sub(r"^plugin/\{[^}]*\}/?", "", p)
    p = re.sub(r"^\{x\}/", "", p)          # 头部 ${pluginBase.value} / ${props.pluginBase}
    p = p.split("?")[0]
    p = p.strip("/")
    if not p:
        return None
    p = "/" + p
    # 剥尾部「非 / 引导的 {x}」= 查询模板变量（${query}/${q}/${opsQuery()}…），
    # 保留 / 引导的 {x} = 路径参数（/tasks/{x}、/recommend/{x}/{x}）。
    while p.endswith("{x}") and len(p) > 3 and p[-4] != "/":
        p = p[:-3]
    return p


def collect_frontend_calls():
    """扫 src/** 返回 ``set[(method, path)]``。"""
    calls = set()
    for f in sorted(ROOT.glob("src/**/*")):
        if not f.is_file() or f.suffix not in (".vue", ".js"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        for method, raw in extract_calls(text):
            path = normalize_path(raw)
            if path:
                calls.add((method.lower(), path))
    return calls


def classify(method, path):
    """分类：``("covered"|"whitelisted"|"write"|"uncovered", 详情)``。"""
    m = str(method).lower()
    p = str(path or "")
    if m == "get":
        if p in COVERED:
            return "covered", COVERED[p]
        if p in READ_WHITELIST:
            return "whitelisted", READ_WHITELIST[p]
        return "uncovered", None
    return "write", WRITE_REASON


# ---------------------------------------------------------------------------
# 离线加载 agentapi（能力清单）+ agentledger（真值表清单）
# ---------------------------------------------------------------------------
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


def _stub_app() -> None:
    for name, attr_map in (
        ("app", {}),
        ("app.plugins", {"_PluginBase": type("_PluginBase", (), {})}),
        ("app.schemas", {"Response": type("Response", (), {})}),
        ("app.schemas.types", {"EventType": type("EventType", (), {})}),
        ("app.sdk", {}),
        ("app.sdk.events", {"eventmanager": types.SimpleNamespace()}),
    ):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        for k, v in attr_map.items():
            setattr(m, k, v)


def load_manifest_paths():
    """加载能力清单 → 归一化 agent 路径集合。"""
    _stub_app()
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
    agentapi = _load(PKG + ".features.agentapi", "features/agentapi.py")
    paths = set()
    for ep in (agentapi._agent_endpoints() or []):
        p = str(ep.get("path") or "")
        p = re.sub(r"\{[^}]*\}", "{x}", p)
        paths.add(p)
    return paths


def load_ledger_tables():
    _stub_app()
    _pkg(PKG, ROOT)
    _pkg(PKG + ".features", ROOT / "features")
    agentledger = _load(PKG + ".features.agentledger", "features/agentledger.py")
    return tuple(getattr(agentledger, "LEDGER_TABLES", ()))


# ---------------------------------------------------------------------------
def _norm_agent(p: str) -> str:
    return re.sub(r"\{[^}]*\}", "{x}", str(p or ""))


def main() -> int:
    errors: list = []
    covered_n = whitelisted_n = write_n = 0
    uncovered: list = []

    # ---- 1) 前端覆盖（下限） ----
    calls = collect_frontend_calls()
    manifest_paths = load_manifest_paths()

    for method, path in sorted(calls):
        status, detail = classify(method, path)
        if status == "covered":
            # 校验覆盖它的 /agent 端点确实在清单里
            target = _norm_agent(detail)
            if target not in manifest_paths:
                errors.append(f"前端 {method.upper()} {path} 覆盖端点 {detail} 不在 /agent 清单")
                continue
            covered_n += 1
        elif status == "whitelisted":
            whitelisted_n += 1
        elif status == "write":
            write_n += 1
        else:
            uncovered.append((method, path))

    if uncovered:
        for method, path in uncovered:
            errors.append(f"前端 {method.upper()} {path} 既未被 /agent 覆盖也未进白名单")

    # ---- 2) 真值源覆盖（目标） ----
    tables = load_ledger_tables()
    missing_tables = [t for t in REQUIRED_TABLES if t not in tables]
    if "/agent/ledger/{x}" not in manifest_paths:
        errors.append("清单缺 /agent/ledger/{table} 端点（真值源直出没接上）")
    if missing_tables:
        errors.append(f"真值源未覆盖（缺表）：{', '.join(missing_tables)}")

    # ---- 汇总 ----
    if errors:
        print(f"❌ 对齐校验失败：{len(errors)} 处")
        for msg in errors:
            print(f"  - {msg}")
        return 1
    print("✅ 对齐校验通过：")
    print(f"  前端覆盖（下限）：GET 覆盖 {covered_n} / 只读豁免 {whitelisted_n} / 写豁免 {write_n} / 未覆盖 0")
    print(f"  真值源覆盖（目标）：{len(tables)} 张真值表全部由 /agent/ledger/{{table}} 直出"
          f"（账本 + 运行台账 + 12.2.0 新表）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
