# -*- coding: utf-8 -*-
"""魔流 · code-dict —— 代码字典（符号级索引）真值源。

把「某常量 / 函数 / 端点 / 口径在哪个文件哪一行」变成**一次调用就能答**，
让 agent 排查 / 运维 / B 端自动化**不必翻源码**。

设计（Master 2026-10-06）：
  - **字典放在插件接口里** → ``GET /agent/code-dict``（``features/agentapi.py::agent_code_dict``）；
  - **使用/维护说明放在 skill**（``skills/magicflow``）；
  - 本模块是**唯一逻辑真值源**，只服务**够不到仓库源码的调用方**：
      ① 插件接口（运行时解析**插件自身源码**现算，永远与线上代码一致）。
    ★ 2026-10-10 Master 拍板：仓库侧镜像渲染（``tools/gen_code_dict.py`` → ``docs/CODE-DICT.md``）与坐标认领
    （``tools/check_dict_claims.py`` / ``docs/CODE-CLAIMS.md``）已**整块砍除** —— 有文件系统的 agent 用
    grep/glob/read 即真值，镜像版索引收益≈0、成本必付（实测 5–9K tok/会话）。本模块与接口保留（本地 0 成本）。
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
        ["状态账本真值源：`SeedLedgerStore`（`ledger.py`，5 表后端）。"],
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
        ["★ 两轴分级：第一级六桶 `BUCKET_BRUSH` 刷流 / `BUCKET_BONUS` 魔力 / `BUCKET_HR` 保种（欠H&R挂补） / "
         "`BUCKET_SILENT` 静默（含 新/资源/普通 三子桶）/ `BUCKET_RESCUE` 补源 / `BUCKET_EXTERNAL` 外部（顺序见 `_BUCKET_ORDER`）。"],
        ["第二级传输三态：`TRANSPORT_DOWNLOADING` 未完成 / `TRANSPORT_PAUSED` 暂停 / `TRANSPORT_SEEDING` 做种中（不单独成桶）。"],
        ["债务/账本只作列字段（`item.hr`/`item.bill`），不再当桶。"],
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
        ["资源账（一份内容 = 一条资源）", "`ResourceLedgerStore`（`ledger.py`，5 表后端）"],
        ["标签状态账本", "`SeedLedgerStore`（`ledger.py`，5 表后端）"],
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


# ------------------------------------------------------------------ 前端（.vue / .js）
# 前端不是 Python，不能用 ast；用轻量正则抽「块边界 + 顶层声明」。
# 目的同 Python 侧：让「某常量/函数/组件在哪个文件哪一行」一次调用就能答。
FE_SUFFIXES = (".vue", ".js")


def scan_frontend(root: Path) -> List[str]:
    """前端源码（``src/**/*.vue`` + ``src/**/*.js``），跳过 SKIP_DIRS。"""
    base = root / "src"
    if not base.exists():
        return []
    out: List[str] = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.suffix not in FE_SUFFIXES:
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return out


def _blocks_vue(text: str) -> Dict[str, List[List[int]]]:
    """SFC 块边界（1 基行号）：script / template / styles（可多段）。"""
    res: Dict[str, List[List[int]]] = {"script": [], "template": [], "style": []}
    for tag in ("script", "template", "style"):
        # 只认顶格（col 0）的开/闭标签——SFC 顶层块必在 col 0，嵌套块有缩进。
        open_re = re.compile(r"^<" + tag + r"\b[^>]*>", re.M)
        close_re = re.compile(r"^</" + tag + r">", re.M)
        for m in open_re.finditer(text):
            cm = close_re.search(text, m.end())
            if not cm:
                continue
            res[tag].append([text[:m.start()].count(chr(10)) + 1,
                             text[:cm.start()].count(chr(10)) + 1])
    return res


_FE_DECL_PATTERNS = (
    (r"^(?:export\s+)?const\s+([\w$]+)\s*=\s*(?:ref|shallowRef)\b", "ref"),
    (r"^(?:export\s+)?const\s+([\w$]+)\s*=\s*reactive\b", "reactive"),
    (r"^(?:export\s+)?const\s+([\w$]+)\s*=\s*computed\b", "computed"),
    (r"^(?:export\s+)?const\s+([\w$]+)\s*=\s*(?:defineProps|defineEmits|defineModel|defineExpose)\b", "api"),
    (r"^(?:export\s+)?const\s+([\w$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", "fn"),
    (r"^(?:export\s+)?(?:async\s+)?function\s+([\w$]+)", "function"),
    (r"^(?:export\s+)?const\s+([\w$]+)\s*=", "const"),
    (r"^(?:export\s+)?let\s+([\w$]+)", "let"),
    (r"^(?:watch|watchEffect)\(", "watch"),
    (r"^on(?:Mounted|Unmounted|BeforeUnmount|Activated|Deactivated)\(", "hook"),
)


def _fe_decl(line: str) -> Optional[tuple]:
    """顶层声明识别（只看顶格行——SFC/js 顶层声明都在 col 0）。"""
    if not line or line != line.lstrip():
        return None
    for pat, kind in _FE_DECL_PATTERNS:
        m = re.match(pat, line)
        if m:
            return (kind, m.group(1) if m.groups() else "")
    return None


def _parse_frontend(root: Path, rel: str) -> Dict[str, Any]:
    text = (root / rel).read_text(encoding="utf-8")
    lines = text.splitlines()
    lang = "vue" if rel.endswith(".vue") else "js"
    blocks: Dict[str, Any] = {"script": None, "template": None, "styles": []}
    if lang == "vue":
        b = _blocks_vue(text)
        if b["script"]:
            blocks["script"] = b["script"][0]
        if b["template"]:
            blocks["template"] = b["template"][0]
        blocks["styles"] = b["style"]
        s = b["script"][0] if b["script"] else None
        region = [(i + 1, lines[i]) for i in range(s[0], s[1] - 1)] if s else []
        script_text = "\n".join(lines[s[0] - 1:s[1]]) if s else ""
        base_line = s[0] if s else 1
    else:
        region = [(i + 1, ln) for i, ln in enumerate(lines)]
        script_text = text
        base_line = 1
    decls: List[Dict[str, Any]] = []
    for ln, raw in region:
        d = _fe_decl(raw)
        if d:
            decls.append({"name": d[1], "kind": d[0], "line": ln})
    return {"file": rel, "lang": lang, "lines": len(lines),
            "blocks": blocks, "decls": decls,
            "contract": _parse_contract(script_text, base_line)}


def _flat_fe(mods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in mods:
        for d in m["decls"]:
            out.append({"name": d["name"], "kind": d["kind"], "lang": m["lang"],
                        "file": m["file"], "line": d["line"]})
    return out


_STRING_RE = re.compile(r"['\"`]([^'\"`]+)['\"`]")


def _balanced(text: str, open_idx: int) -> str:
    """text[open_idx] 应为 '('，返回与其配平的括号内子串。"""
    depth = 0
    i = open_idx
    quote = None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i]
        i += 1
    return text[open_idx + 1:]


def _macro_inner(text: str, macro: str) -> Optional[str]:
    m = re.search(r"\b" + macro + r"\b\s*(?:<[^<>]*>)?\s*\(", text)
    return _balanced(text, m.end() - 1) if m else None


def _dedup_items(seq: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for x in seq:
        if x["name"] and x["name"] not in seen:
            seen.add(x["name"])
            out.append(x)
    return out


def _blank_comments(text: str) -> str:
    """把 // 与 /* */ 注释**按位用空格抹掉**（保留换行/长度），使行号不偏移。"""
    a = list(text)
    i, n = 0, len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                a[k] = " "
            i = j
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = (j + 2) if j != -1 else n
            for k in range(i, j):
                if a[k] != "\n":
                    a[k] = " "
            i = j
            continue
        i += 1
    return "".join(a)


def _macro_inner_span(text: str, macro: str):
    """macro 调用括号内子串 及 其在 text 中的起始偏移（无则 (None,0)）。"""
    m = re.search(r"\b" + macro + r"\b\s*(?:<[^<>]*>)?\s*\(", text)
    if not m:
        return None, 0
    return _balanced(text, m.end() - 1), m.end()


def _obj_items(inner: Optional[str], abs_start: int, ln) -> List[Dict[str, Any]]:
    """对象字面量顶层键（深度 1）；数组字面量取字符串项。每项带行号。"""
    if not inner:
        return []
    out: List[Dict[str, Any]] = []
    if inner.lstrip().startswith("["):
        for s in _STRING_RE.finditer(inner):
            out.append({"name": s.group(1), "line": ln(abs_start + s.start())})
        return _dedup_items(out)
    i, depth, n = 0, 0, len(inner)
    while i < n:
        ch = inner[i]
        if ch in "([{":
            depth += 1
            i += 1
            continue
        if ch in ")]}":
            depth -= 1
            i += 1
            continue
        if ch in "'\"`":
            j = i + 1
            while j < n and inner[j] != ch:
                j += 2 if inner[j] == "\\" else 1
            if depth == 1:
                k = j + 1
                while k < n and inner[k] in " \t\r\n":
                    k += 1
                if k < n and inner[k] == ":":
                    out.append({"name": inner[i + 1:j], "line": ln(abs_start + i)})
            i = j + 1
            continue
        if depth == 1 and (ch.isalnum() or ch in "_$"):
            j = i
            while j < n and (inner[j].isalnum() or inner[j] in "_$"):
                j += 1
            k = j
            while k < n and inner[k] in " \t\r\n":
                k += 1
            if k < n and inner[k] == ":":
                out.append({"name": inner[i:j], "line": ln(abs_start + i)})
            i = j
            continue
        i += 1
    return _dedup_items(out)


def _parse_contract(script_text: str, base_line: int = 1) -> Dict[str, List[Dict[str, Any]]]:
    """解析 <script setup> 组件契约，每项带 file 行号：defineModel/defineProps/defineEmits。"""
    b = _blank_comments(script_text)

    def ln(pos: int) -> int:
        return base_line + b[:pos].count("\n")

    models: List[Dict[str, Any]] = []
    for m in re.finditer(r"\bdefineModel\b\s*(?:<[^<>]*>)?\s*\(", b):
        s = _STRING_RE.search(_balanced(b, m.end() - 1))
        models.append({"name": s.group(1) if s else "modelValue", "line": ln(m.start())})
    pspan = _macro_inner_span(b, "defineProps")
    espan = _macro_inner_span(b, "defineEmits")
    return {
        "models": _dedup_items(models),
        "props": _obj_items(pspan[0], pspan[1], ln),
        "emits": _obj_items(espan[0], espan[1], ln),
    }


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
    fe_rels = scan_frontend(root)
    fe_mods = [_parse_frontend(root, rel) for rel in fe_rels]
    fe_decls = _flat_fe(fe_mods)
    fe_lines = sum(m["lines"] for m in fe_mods)

    overview = {
        "counts": {"modules": len(mods), "lines": total_lines,
                   "symbols": len(symbols), "constants": len(consts),
                   "endpoints": len(eps), "fe_files": len(fe_mods),
                   "fe_lines": fe_lines, "fe_decls": len(fe_decls),
                   "fe_models": sum(len(m["contract"]["models"]) for m in fe_mods),
                   "fe_props": sum(len(m["contract"]["props"]) for m in fe_mods),
                   "fe_emits": sum(len(m["contract"]["emits"]) for m in fe_mods)},
        "sections": ["endpoints", "constants", "symbols", "modules", "frontend",
                     "glossary"],
        "usage": {
            "q": "子串模糊查（符号/常量/端点/模块职责/前端声明）",
            "section": "endpoints|constants|symbols|modules|frontend|glossary 取整节",
            "full": "1=回全部（大）",
        },
    }
    if not (q or section or full):
        overview["hint"] = "加 q=<关键词> 精确查，或 section=<节名> 取整节。"
        return {"overview": overview}

    ALL = {"endpoints", "constants", "symbols", "modules", "frontend", "glossary"}
    want = set()
    if section:
        want = {section.strip().lower()}
    elif full:
        want = set(ALL)
    else:  # q
        want = set(ALL)

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

    if "frontend" in want:
        rows = fe_mods
        if q:
            keep: List[Dict[str, Any]] = []
            for m in rows:
                hit_file = _match(q, m["file"])
                ds = [d for d in m["decls"] if _match(q, d["name"], d["kind"])]
                ct = m.get("contract") or {}
                hit_ct = any(_match(q, n["name"]) for k in ("models", "props", "emits")
                             for n in ct.get(k, []))
                if hit_file or ds or hit_ct:
                    mm = dict(m)
                    mm["decls"] = m["decls"] if hit_file else ds
                    keep.append(mm)
            rows = keep
        out["frontend"] = rows[:cap] if (q and not full) else rows
        if q and not full:
            out["frontend_decls"] = [d for d in fe_decls
                                     if _match(q, d["name"], d["kind"], d["file"])][:cap]

    if "glossary" in want:
        rows = GLOSSARY
        if q:
            rows = [g for g in GLOSSARY if _match(q, g["title"])
                    or any(_match(q, *[str(c) for c in r]) for r in g["rows"])]
        out["glossary"] = rows

    return out
