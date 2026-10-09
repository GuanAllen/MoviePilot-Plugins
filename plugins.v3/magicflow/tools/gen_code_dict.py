#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 代码字典生成器 —— 把 ``codedict.build_dict()`` 渲染成 ``docs/CODE-DICT.md``。

**逻辑真值源** = ``codedict.py``（与插件接口 ``GET /agent/code-dict`` 同一份）；
口径速查 = ``codedict.GLOSSARY``（手维护，在代码里）。本工具只负责 markdown 渲染。

用法：
  python3 tools/gen_code_dict.py            # 生成/更新 docs/CODE-DICT.md
  python3 tools/gen_code_dict.py --check    # 校验已同步（CI/提交前跑）
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

OUT = ROOT / "docs" / "CODE-DICT.md"


def _load_codedict():
    spec = importlib.util.spec_from_file_location("mf_codedict", ROOT / "codedict.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def agent_endpoints() -> list[dict]:
    try:
        from check_agent_manifest import _load_agentapi  # noqa: E402
        mod = _load_agentapi()
        raw = getattr(mod, "_agent_endpoints", None)
        if callable(raw):
            return [dict(e) for e in raw()]  # 含 summary
        data = mod.AgentApiMixin()._agent_manifest_data()
        return list(data.get("endpoints") or [])
    except Exception:  # noqa: BLE001
        return []


def ui_endpoints() -> list[dict]:
    """AST 解析 features/api.py 的 get_api() 返回列表。"""
    p = ROOT / "features" / "api.py"
    if not p.exists():
        return []
    tree = ast.parse(p.read_text(encoding="utf-8"))
    out: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_api":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Dict):
                    d = {}
                    for k, v in zip(sub.keys, sub.values):
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            d[k.value] = v
                    if "path" in d and "endpoint" in d:
                        try:
                            out.append({
                                "path": ast.literal_eval(d["path"]),
                                "endpoint": ast.unparse(d["endpoint"]),
                                "summary": ast.literal_eval(d["summary"]) if "summary" in d else "",
                            })
                        except Exception:  # noqa: BLE001
                            continue
    return out


def build() -> str:
    cd = _load_codedict()
    data = cd.build_dict(ROOT, endpoints=agent_endpoints(), full=True)
    ov = data["overview"]
    c = ov["counts"]

    L: list[str] = []
    L.append("# 魔流 · 代码字典（自动生成，勿手改）\n")
    L.append("> 由 `python3 tools/gen_code_dict.py` 生成；提交前 `--check` 校验。")
    L.append("> **逻辑真值源**：`codedict.py`（与插件接口 `GET /agent/code-dict` 同一份）；"
             "口径速查在 `codedict.GLOSSARY`。")
    L.append(f"> 模块 **{c['modules']}** / 行数 **{c['lines']}** / 符号 **{c['symbols']}** / "
             f"常量 **{c['constants']}** / 端点 **{c['endpoints']}** / "
             f"前端文件 **{c.get('fe_files', 0)}**（声明 **{c.get('fe_decls', 0)}**）。\n")
    L.append("**怎么用**：`grep -ni \"关键词\" docs/CODE-DICT.md` 一次拿到 file:line；"
             "线上可直接 `GET /agent/code-dict?q=关键词`。\n")

    # 1. 端点
    L.append("## 1. 端点总表\n")
    ae = agent_endpoints()
    ue = ui_endpoints()
    L.append("### 1.1 AI 门面 `_agent_endpoints()`（唯一真值源，登记制）\n")
    L.append("| 端点 | 方法 | 写 | 参数 | 返回 | 版本 | 说明 |")
    L.append("|---|---|---|---|---|---|---|")
    for e in ae:
        params = ", ".join(f"`{k}`:{v}" for k, v in (e.get("params") or {}).items()) or "—"
        L.append(f"| `{e['path']}` | {e.get('method', 'GET')} | "
                 f"{'✓' if e.get('write') else ''} | {params} | `{e.get('returns', '')}` | "
                 f"{e.get('version', '')} | {e.get('summary', '')} |")
    L.append(f"\n（{len(ae)} 个）\n")
    L.append("### 1.2 UI 路由 `get_api()`（`features/api.py`）\n")
    L.append("| 路径 | 处理函数 | 说明 |")
    L.append("|---|---|---|")
    for e in ue:
        L.append(f"| `{e['path']}` | `{e['endpoint']}` | {e['summary']} |")
    L.append(f"\n（{len(ue)} 个）\n")

    # 2. 常量
    L.append("## 2. 常量总表（模块级 UPPER_CASE）\n")
    L.append("| 常量 | 值 | 位置 |")
    L.append("|---|---|---|")
    for s in data["constants"]:
        L.append(f"| `{s['name']}` | `{s['value']}` | `{s['file']}:{s['line']}` |")
    L.append("")

    # 3. 符号
    L.append("## 3. 符号总索引（字母序）\n")
    L.append("| 符号 | 类型 | 位置 | 说明 |")
    L.append("|---|---|---|---|")
    for s in data["symbols"]:
        L.append(f"| `{s.get('qual', s['name'])}` | {s['kind']} | `{s['file']}:{s['line']}` | "
                 f"{s.get('doc', '')} |")
    L.append("")

    # 4. 模块明细
    L.append("## 4. 模块明细\n")
    for m in data["modules"]:
        L.append(f"### `{m['file']}` （{m['lines']} 行）")
        if m["doc"]:
            L.append(f"\n> {m['doc']}\n")
        for cl in m["classes"]:
            L.append(f"- **class `{cl['name']}`** L{cl['line']}"
                     + (f" — {cl['doc']}" if cl["doc"] else ""))
            for me in cl["methods"]:
                L.append(f"  - `{me['name']}({me['sig']})` L{me['line']}"
                         + (f" — {me['doc']}" if me["doc"] else ""))
        if m["funcs"]:
            L.append("- **顶层函数**")
            for f in m["funcs"]:
                L.append(f"  - `{f['name']}({f['sig']})` L{f['line']}"
                         + (f" — {f['doc']}" if f["doc"] else ""))
        if m["consts"]:
            L.append("- **常量**")
            for co in sorted(m["consts"], key=lambda x: x["line"]):
                L.append(f"  - `{co['name']} = {co['value']}` L{co['line']}")
        L.append("")

    # 5. 口径速查（来自 codedict.GLOSSARY，手维护在代码里）
    L.append("## 5. 口径速查（真值源：`codedict.GLOSSARY`，手维护在代码里）\n")
    for g in data["glossary"]:
        L.append(f"#### 5.x {g['title']}\n")
        head = g.get("head")
        if head:
            L.append("| " + " | ".join(head) + " |")
            L.append("|" + "---|" * len(head))
            for row in g["rows"]:
                L.append("| " + " | ".join(str(x) for x in row) + " |")
        else:
            for row in g["rows"]:
                L.append(f"- {row[0]}")
        L.append("")

    # 6. 前端索引（给 agent：名字 → kind → 文件:行；按名排序，grep 一步定位）
    fe = data.get("frontend", [])
    L.append("## 6. 前端索引（`src/` 下 .vue/.js · 按名字排序）\n")
    L.append("> **给 agent**：`grep -ni \"<名字>\" docs/CODE-DICT.md` → 得 `文件:行`；"
             "线上 `GET /agent/code-dict?q=<名字>`。kind：`model`=defineModel 双向字段、"
             "`prop`=defineProps、`emit`=defineEmits；其余为脚本顶层声明（ref/computed/fn/const…）。\n")
    entries = []
    for m in fe:
        for d in m["decls"]:
            if d["kind"] == "api":  # defineModel/Props/Emits 赋值，已由 contract 覆盖
                continue
            entries.append((d["name"] or "—", d["kind"], m["file"], d["line"]))
        ct = m.get("contract") or {}
        for kind, key in (("model", "models"), ("prop", "props"), ("emit", "emits")):
            for it in ct.get(key, []):
                entries.append((it["name"], kind, m["file"], it["line"]))
    entries.sort(key=lambda e: (e[0].lower(), e[2], e[3]))
    L.append("| 名字 | kind | 位置 |")
    L.append("|---|---|---|")
    for name, kind, file, line in entries:
        L.append(f"| `{name}` | {kind} | `{file}:{line}` |")
    L.append(f"\n（{len(entries)} 条）\n")
    return "\n".join(L) + "\n"


def main() -> int:
    content = build()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != content:
            print("❌ docs/CODE-DICT.md 未同步，请跑 python3 tools/gen_code_dict.py")
            return 1
        print("✅ docs/CODE-DICT.md 已同步")
        return 0
    OUT.write_text(content, encoding="utf-8")
    print(f"✅ 已生成 {OUT.relative_to(ROOT)}（{content.count(chr(10))} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
