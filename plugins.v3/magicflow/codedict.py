# -*- coding: utf-8 -*-
"""魔流 · code-dict —— 代码字典（符号级索引）真值源。

把「某常量 / 函数 / 端点 / 口径在哪个文件哪一行」变成**一次调用就能答**，
让 agent 排查 / 运维 / B 端自动化**不必翻源码**。

设计（Master 2026-10-06）：
  - **字典放在插件接口里** → ``GET /agent/code-dict``（``features/agentapi.py::agent_code_dict``）；
  - **使用/维护说明放在 skill**（``skills/magicflow``）；
  - 本模块是**唯一逻辑真值源**，两处复用：
      ① 插件接口（运行时解析**插件自身源码**现算，永远与线上代码一致）；
      ② 仓库侧 ``tools/gen_code_dict.py``（渲染 ``docs/CODE-DICT.md``）。
  - ``GLOSSARY``（口径速查）**手维护在本文件**——文档 §5 与接口返回都从这里出，避免两处漂移。

铁律：**只读**（只 ``ast`` 解析自身源码 + 读本文件常量），不写任何 json / 账本 / 热层。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

SKIP_DIRS = {"_backup", "tools", "__pycache__", "dist", "node_modules", ".git",
             "data", "preview", "screenshots", "conf", "icons", "scripts"}
UPPER_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,}$")

# ------------------------------------------------------------------ 口径速查（手维护）
# 每项：{title, head(表头或 None=要点列表), rows[[...],...]}
# ★ 文档 §5 与 /agent/code-dict 的 glossary 都从这里出；改这里即可，别在别处再写一份。
GLOSSARY: List[Dict[str, Any]] = [
    {"title": "标签", "head": ["概念", "常量 = 值", "位置"], "rows": [
        ["复用/辅种副本（**非真实下载**，不判 H&R）", "`MARK_REUSE` = `魔流-辅种`", "`tags.py`"],
        ["跨站来源份（H&R 走**资源账**，不走账单）", "`CROSSSEED_TAG` = `魔流-跨站`", "`crossseed.py`"],
        ["救援补源副本（**非真实下载**）", "`RESCUE_TAG` = `魔流-补源`", "`tags.py` / `rescue.py`"],
        ["插件外/MP 手动加的种（**只标不动**）", "`EXTERNAL_TAG` = `魔流-外部`", "`tags.py`"],
        ["「非下载」标签集", "`NON_DOWNLOAD_TAGS` = `(MARK_REUSE, RESCUE_TAG)`", "`tags.py`"],
        ["MP `已整理/辅种`（**真实下载** → 仍欠 H&R）", "`ASSET_TAGS` = `('已整理','辅种')`", "`tags.py`"],
        ["retag 不冲掉的特殊标签", "`SPECIAL_TAGS`", "`tags.py`"],
        ["站点职务标签格式", "`魔流-<站>-<职务>-<身份>`", "`tags.py`"],
    ]},
    {"title": "职务 / 身份（`tags.py`）", "head": None, "rows": [
        ["职务 `STATE_*`：`刷流`(STATE_BRUSH) / `魔力`(STATE_BONUS) / `静默`(STATE_SILENT) / "
         "`推荐`(STATE_RECOMMEND) / `保种`(**STATE_HR，不可手设**，只由 `_hr_obligation` 派生）。"],
        ["身份 `SUB_*`：`新`(SUB_NEW) / `资源`(SUB_RESOURCE) / `普通`(SUB_PLAIN)。"],
        ["状态账本真值源：`TagStateStore`（`tags.py`，键 `STATE_KEY='tag_state'`）。"],
    ]},
    {"title": "H&R 账单（`features/hrbills.py`；真值源 `hr_bills.json`）", "head": None, "rows": [
        ["状态 `BILL_STATE_*`：`active` / `pending` / `settled` / `void` / `breached`。"],
        ["「不该开账」判定：`_skip_hr_bill`（`features/hrbills.py`）= 跨站 / 复用 / 补源副本。"],
        ["站点要求时长：`_hr_need_hours()` → 站规则 `seed_need_hours` → 默认 `HR_NEED_HOURS_DEFAULT=24.0`。"],
        ["存量作废（辅种）：`GET /tags?action=hrbills_void_reuse`（默认干跑，`confirm=1` 才写）。"],
        ["违约：种子消失 + active 账单 → `breached`（**只读报警**，`/agent/hr/breaches`）。"],
        ["站点对账（myhr.php，只判「还欠」不产 settled）：`_hr_reconcile_site`。"],
    ]},
    {"title": "站点报表分类桶（`features/sitereport.py`）", "head": None, "rows": [
        ["`BUCKET_HR` 欠H&R / `BUCKET_RESCUE` 补源 / `BUCKET_SILENT` 静默 / "
         "`BUCKET_PROTECTED` 保护 / `BUCKET_NORMAL` 普通（顺序见 `_BUCKET_ORDER`）。"],
    ]},
    {"title": "静默池 / H&R 保种宿主（11.11.0）", "head": None, "rows": [
        ["静默宿主任务 `SILENT_HOST_TASK_ID='__silent_host__'`；H&R 保种宿主任务 "
         "`HR_HOST_TASK_ID='__hr_host__'`（职务「保种」）——见 `common.py`。"],
        ["总开关 `SILENT_HR_SPLIT_ENABLED`（`common.py`）——**关掉 = 整体回滚到 11.10 行为**。"],
        ["静默硬不变量 `_silent_pause_gate`（`features/silent.py`）：静默池一律 pause、无 H&R 例外。"],
        ["遣散分诊 `_split_release`（`features/core.py`）：欠 H&R → 保种；否则 → 静默 + pause。"],
        ["保种迁移 `_hr_host_assign` / `_hr_host_release`（`features/hr.py`）。"],
    ]},
    {"title": "真值源清单（改前先认这个，**不造第二份**）", "head": ["真值源", "位置"], "rows": [
        ["账本 5 表（site/resource/identity/task/seed…）", "`ledger.py`"],
        ["资源账（一份内容 = 一条资源）", "`FileGroupStore`（`tags.py`）"],
        ["标签状态账本", "`TagStateStore`（`tags.py`）"],
        ["H&R 账单", "`features/hrbills.py` → `hr_bills.json`"],
        ["删除**唯一**出口（闸门）", "`DownloaderAdapter.delete_torrents` + `features/deletegate.py`"],
        ["外部取数**唯一**出口", "`collect.py`"],
    ]},
    {"title": "常见问题 → 一次调用（AI 门面，清单 `GET /agent`）", "head": ["问", "端点"], "rows": [
        ["某 hash 为什么删/留", "`GET /agent/decide?hashes=`"],
        ["某站各种种子状态", "`GET /agent/site/seeds?site=`"],
        ["某站 H&R 账单", "`GET /agent/hr/bills?site=`"],
        ["逐种 H&R", "`GET /agent/hr/per-torrent`"],
        ["违约", "`GET /agent/hr/breaches`"],
        ["静默池审计", "`GET /agent/silent/audit`"],
        ["全站概览", "`GET /agent/state` / `/agent/overview`"],
        ["端点/参数清单", "`GET /agent`"],
    ]},
]


# ------------------------------------------------------------------ 工具函数
def plugin_root() -> Path:
    """插件包根目录（本文件在 ``features/`` 下的上一层即为包根）。"""
    return Path(__file__).resolve().parent


def scan_modules(root: Path) -> List[str]:
    out: List[str] = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return out


def _first_line(text: Optional[str]) -> str:
    if not text:
        return ""
    for ln in text.strip().splitlines():
        if ln.strip():
            return ln.strip()[:110]
    return ""


def _canon(v: object) -> str:
    """确定性序列化（集合/字典按字典序，避免 PYTHONHASHSEED 抖动）。"""
    if isinstance(v, (set, frozenset)):
        return "{" + ", ".join(_canon(x) for x in sorted(v, key=repr)) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join(
            f"{_canon(k)}: {_canon(v[k])}" for k in sorted(v, key=repr)) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_canon(x) for x in v) + "]"
    if isinstance(v, tuple):
        inner = ", ".join(_canon(x) for x in v)
        return f"({inner}{',' if len(v) == 1 else ''})"
    return repr(v)


def _lit(node: ast.AST) -> Optional[str]:
    try:
        v = ast.literal_eval(node)
    except Exception:  # noqa: BLE001
        try:
            return ast.unparse(node)[:100]  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return None
    return _canon(v)[:120]


def _sig(node: ast.AST) -> str:
    try:
        return ast.unparse(node.args)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return "..."


def _parse_file(root: Path, rel: str) -> Dict[str, Any]:
    src = (root / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    classes: List[Dict[str, Any]] = []
    funcs: List[Dict[str, Any]] = []
    consts: List[Dict[str, Any]] = []

    def _const(name: str, node: ast.AST, lineno: int) -> None:
        consts.append({"name": name, "value": _lit(node) or "", "line": lineno})

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [
                {"name": s.name, "line": s.lineno, "sig": _sig(s),
                 "doc": _first_line(ast.get_docstring(s))}
                for s in node.body
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes.append({"name": node.name, "line": node.lineno,
                            "doc": _first_line(ast.get_docstring(node)),
                            "methods": methods})
            for s in node.body:
                if isinstance(s, ast.Assign):
                    for t in s.targets:
                        if isinstance(t, ast.Name) and UPPER_RE.match(t.id):
                            _const(t.id, s.value, s.lineno)
                elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name) \
                        and UPPER_RE.match(s.target.id) and s.value is not None:
                    _const(s.target.id, s.value, s.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append({"name": node.name, "line": node.lineno, "sig": _sig(node),
                          "doc": _first_line(ast.get_docstring(node))})
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and UPPER_RE.match(t.id):
                    _const(t.id, node.value, node.lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and UPPER_RE.match(node.target.id) and node.value is not None:
            _const(node.target.id, node.value, node.lineno)

    return {"file": rel, "lines": len(src.splitlines()),
            "doc": _first_line(ast.get_docstring(tree)),
            "classes": classes, "funcs": funcs, "consts": consts}


def _flat_symbols(mods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in mods:
        for c in m["classes"]:
            out.append({"name": c["name"], "kind": "class", "file": m["file"],
                        "line": c["line"], "doc": c["doc"]})
            for me in c["methods"]:
                out.append({"name": me["name"], "qual": f"{c['name']}.{me['name']}",
                            "kind": "method", "file": m["file"], "line": me["line"],
                            "sig": me["sig"], "doc": me["doc"]})
        for f in m["funcs"]:
            out.append({"name": f["name"], "qual": f["name"], "kind": "func",
                        "file": m["file"], "line": f["line"], "sig": f["sig"],
                        "doc": f["doc"]})
    return out


def _flat_consts(mods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in mods:
        for c in m["consts"]:
            out.append({"name": c["name"], "value": c["value"],
                        "file": m["file"], "line": c["line"]})
    return out


def _match(needle: str, *hay: object) -> bool:
    n = needle.lower()
    return any(n in str(h or "").lower() for h in hay)


def build_dict(root: Path, *, endpoints: Optional[List[Dict[str, Any]]] = None,
               q: str = "", section: str = "", full: bool = False,
               cap: int = 400) -> Dict[str, Any]:
    """构建代码字典。

    - 无 ``q`` / ``section`` / ``full`` → 只回**概览**（计数 + 用法 + 各节名）；
    - ``q=<子串>`` → 各节模糊匹配（名字/值/位置/说明）；
    - ``section=endpoints|constants|symbols|modules|glossary`` → 回该整节；
    - ``full=1`` → 回全部（大，慎用）。
    """
    rels = scan_modules(root)
    mods = [_parse_file(root, rel) for rel in rels]
    symbols = _flat_symbols(mods)
    consts = _flat_consts(mods)
    total_lines = sum(m["lines"] for m in mods)
    eps = list(endpoints or [])

    overview = {
        "counts": {"modules": len(mods), "lines": total_lines,
                   "symbols": len(symbols), "constants": len(consts),
                   "endpoints": len(eps)},
        "sections": ["endpoints", "constants", "symbols", "modules", "glossary"],
        "usage": {
            "q": "子串模糊查（符号/常量/端点/模块职责）",
            "section": "endpoints|constants|symbols|modules|glossary 取整节",
            "full": "1=回全部（大）",
        },
    }
    if not (q or section or full):
        overview["hint"] = "加 q=<关键词> 精确查，或 section=<节名> 取整节。"
        return {"overview": overview}

    want = set()
    if section:
        want = {section.strip().lower()}
    elif full:
        want = {"endpoints", "constants", "symbols", "modules", "glossary"}
    else:  # q
        want = {"endpoints", "constants", "symbols", "modules", "glossary"}

    out: Dict[str, Any] = {"overview": overview, "query": {"q": q, "section": section,
                                                          "full": bool(full)}}

    if "endpoints" in want:
        rows = eps
        if q:
            rows = [e for e in eps if _match(q, e.get("path"), e.get("summary"), e.get("returns"))]
        out["endpoints"] = rows[:cap] if not (full or section) else rows

    if "constants" in want:
        rows = consts
        if q:
            rows = [c for c in consts if _match(q, c["name"], c["value"], c["file"])]
        rows = sorted(rows, key=lambda x: (x["name"], x["file"], x["line"]))
        out["constants"] = rows[:cap] if (q and not full) else rows

    if "symbols" in want:
        rows = symbols
        if q:
            rows = [s for s in symbols if _match(q, s.get("qual"), s.get("name"),
                                                 s.get("file"), s.get("doc"))]
        rows = sorted(rows, key=lambda x: (x.get("name", "").lower(), x["file"], x["line"]))
        out["symbols"] = rows[:cap] if (q and not full) else rows

    if "modules" in want:
        rows = mods
        if q:
            rows = [m for m in mods if _match(q, m["file"], m["doc"])]
        out["modules"] = rows[:cap] if (q and not full) else rows

    if "glossary" in want:
        rows = GLOSSARY
        if q:
            rows = [g for g in GLOSSARY if _match(q, g["title"])
                    or any(_match(q, *[str(c) for c in r]) for r in g["rows"])]
        out["glossary"] = rows

    return out
