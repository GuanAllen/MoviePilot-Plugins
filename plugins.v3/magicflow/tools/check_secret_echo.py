#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔流 · 凭据外泄护栏（P2：cookie / API key / 第三方密钥**只在出口脱敏**）

背景（真值源：`common.SECRET_KEYS` + `common.redact_secrets`）
------------------------------------------------------------
Master 2026-10-17 要求：**不管理、不自存、不回显**站点 cookie/API 凭据。
摸底结论（已实测）：站点 cookie/apikey 侧本来合规 —— 一律现取 MoviePilot 的 Site 对象
（`collect.sanitize_site_headers` → `RequestUtils(cookies=…)`、`reseed._reseed_site_conn` 等），
**插件自己不落盘**；真正的问题在「出口回显」：`/status`、`/settings`、`get_iyuu_sites`、
插件原生设置表单 `get_form` 会把已存的第三方密钥（IYUU token / OpenList token /
站点密钥表 passkey 等）明文送回浏览器，前端再原样存回。

本护栏把「出口必须脱敏」变成可执行的断言（纯 stdlib · 离线 · 退出码 0/1）：

  R1 `SECRET_KEYS` **单一真值源**：全仓库只许 `common.py` 定义一次（不许各处再抄一份名单）。
  R2 不许第二份脱敏实现：`redact_secrets` / `_agent_scrub` / `mask_secret_fields`
     只许在 `common.py` 里`def`（其它模块只能 import）。
  R3 凭据写入白名单：`save_data(key=…)` 里**键名含凭据字样**的只许
     `iyuu_token` / `cloud_token`（站点 cookie/apikey 必须现取 MP，不许另存）。
  R4 出口脱敏：函数若「返回 `Response(..., data=…)`」且函数体碰到凭据属性
     （`self._iyuu_token` / `_iyuu_sites` / `_cloud_token`）或调 `self._current_config()`，
     则该函数体内必须出现任一 masker；`return ... self._current_config()` 同理
     （`get_form` 案）。例外可用 `# noqa: secret-echo` 显式豁免（会打印出来）。
  R5 `EXPLICIT_OUTLETS` 登记表：诊断类出口（URL 里内嵌口令）逐个登记、同样要求 masker。
  R6 `features/reseed.py` 不许回显口令**片段**（`parsed_pk` / `pk` / `label` 这类
     「前 N 位」键名 = 变相外泄；只许回长度）。
  R7 `iyuu_sites` 不许整份替换（`self._iyuu_sites = {`）：出口只回 `***`，
     整份替换会把真值写成掩码 —— 必须逐字段合并 + `is_secret_blank` 跳过空/掩码。

★ 为什么不做「键名匹配式」扫描（凡出现 token 字样就要求脱敏）：`token`/`cookie`
  这类词在站点表、任务配置、日志文案里到处都是，键名匹配必然大面积假红；
  本护栏只认**代码结构**（返回面 + 凭据属性/`_current_config`），宁可少报也不假红。

离线 · 纯 stdlib · 退出码 0（通过）/ 1（失败）。不联网、不写文件。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "common.py"
FEATURES = ROOT / "features"

#: 允许出现在出口的脱敏函数（任一在场即算已脱敏）。
MASKERS = {
    "redact_secrets",
    "mask_secret_fields",
    "mask_url_secrets",
    "mask_long_tokens",
    "_agent_scrub",
}
#: 「凭据属性」：函数体碰到它们又直接返回 data ⇒ 必须脱敏。
SECRET_ATTRS = {"_iyuu_token", "_cloud_token", "_iyuu_sites"}
#: `save_data(key=…)` 白名单（键名含凭据字样时）。
SAVE_DATA_WHITELIST = {"iyuu_token", "cloud_token"}
#: 凭据字样（判 save_data 键名 + reseed 片段键名）。
SECRETISH = ("token", "cookie", "passkey", "apikey", "secret", "downhash",
             "authkey", "rsskey", "credential")
#: 显式登记的诊断出口：(相对路径, 函数名) -> 为什么必须脱敏。
EXPLICIT_OUTLETS = {
    ("features/reseed.py", "reseed_probe"): "诊断回显的下载链/浏览页 URL 里内嵌 passkey",
}
#: reseed.py 禁止回显的「口令片段」键名（只许回长度：`*_len`）。
FORBIDDEN_FRAGMENT_KEYS = {"parsed_pk", "label", "pk"}
#: 显式豁免标记（会打印，便于审计）。
NOQA = "noqa: secret-echo"

FAILS: list[str] = []
NOTES: list[str] = []


def _py_files() -> list[Path]:
    files = sorted(FEATURES.glob("*.py")) + sorted(ROOT.glob("*.py")) + sorted((ROOT / "sites").glob("*.py"))
    return sorted({p for p in files if p.name != "__init__.py" or p.parent != ROOT})


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _parse_or_fail(path: Path) -> ast.Module | None:
    """解析失败 → 记一条失败并返回 None（护栏自身不许因被扫文件语法错而崩）。"""
    try:
        return _tree(path)
    except SyntaxError as err:
        FAILS.append(
            "R0 语法解析失败（先过 preflight 第 1 步 py_compile）："
            f"{path.relative_to(ROOT).as_posix()}: {err}"
        )
        return None


def _seg(src: str, node: ast.AST) -> str:
    return ast.get_source_segment(src, node) or ""


def _call_name(node: ast.AST) -> str:
    func = getattr(node, "func", None)
    return str(getattr(func, "id", None) or getattr(func, "attr", None) or "")


def _returns_current_config(fn: ast.AST) -> bool:
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Return):
            continue
        for call in ast.walk(sub):
            if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "_current_config":
                return True
    return False


def _returns_response_data(fn: ast.AST) -> bool:
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call) and _call_name(sub) == "Response":
            if any(k.arg == "data" for k in sub.keywords):
                return True
    return False


def r1_single_source() -> None:
    hits = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        if re.search(r"^SECRET_KEYS\s*=\s*frozenset\(", text, re.M):
            hits.append(path.relative_to(ROOT).as_posix())
    if hits != ["common.py"]:
        FAILS.append(f"R1 SECRET_KEYS 单一真值源被破坏：定义处 = {hits or '（无）'}，应恰为 ['common.py']")
    else:
        print("  ✓ R1 SECRET_KEYS 仅 common.py 定义一次")


def r2_single_masker() -> None:
    pat = re.compile(r"^def\s+(redact_secrets|_agent_scrub|mask_secret_fields)\s*\(", re.M)
    hits = []
    for path in _py_files():
        if path == COMMON:
            continue
        if pat.search(path.read_text(encoding="utf-8")):
            hits.append(path.relative_to(ROOT).as_posix())
    if hits:
        FAILS.append(f"R2 出现第二份脱敏实现（应只 import common 的）：{hits}")
    else:
        print("  ✓ R2 脱敏实现只此一份（common.py）")


def r3_save_data_whitelist() -> None:
    bad = []
    for path in _py_files():
        src = path.read_text(encoding="utf-8")
        tree = _parse_or_fail(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _call_name(node) == "save_data"):
                continue
            kws = {k.arg: k.value for k in node.keywords}
            key_node = kws.get("key")
            key = str(key_node.value) if isinstance(key_node, ast.Constant) else "<动态>"
            val = _seg(src, kws["value"]) if "value" in kws else ""
            blob = f"{key} {val}".lower()
            if any(s in blob for s in SECRETISH) and key not in SAVE_DATA_WHITELIST:
                bad.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno} save_data(key={key!r})")
    if bad:
        FAILS.append("R3 凭据写入了白名单外的键（站点 cookie/apikey 必须现取 MP，不许另存）：\n      " + "\n      ".join(bad))
    else:
        print(f"  ✓ R3 凭据 save_data 白名单内（{sorted(SAVE_DATA_WHITELIST)}）")


def r4_outlets_masked() -> None:
    bad = []
    checked = 0
    for path in _py_files():
        src = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        tree = _parse_or_fail(path)
        if tree is None:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
            touches = bool(attrs & SECRET_ATTRS) or _returns_current_config(fn)
            outlet = _returns_response_data(fn) or _returns_current_config(fn)
            if not (outlet and touches) and (rel, fn.name) not in EXPLICIT_OUTLETS:
                continue
            checked += 1
            seg = _seg(src, fn)
            if NOQA in seg:
                NOTES.append(f"{rel}::{fn.name} 已用 `{NOQA}` 显式豁免（{EXPLICIT_OUTLETS.get((rel, fn.name), '本地豁免')}）")
                continue
            if not any(m in seg for m in MASKERS):
                reason = EXPLICIT_OUTLETS.get((rel, fn.name), "函数体碰到凭据属性/`_current_config()`")
                bad.append(f"{rel}::{fn.name}（{reason}）")
    if bad:
        FAILS.append("R4 出口未脱敏（data 里可能带明文凭据）：\n      " + "\n      ".join(bad))
    else:
        print(f"  ✓ R4 凭据出口均已过 masker（受检 {checked} 个函数）")


def r6_no_fragment_echo() -> None:
    path = ROOT / "features" / "reseed.py"
    bad = []
    tree = _parse_or_fail(path)
    if tree is None:
        FAILS.append("R6 reseed.py 解析失败")
    for node in ast.walk(tree) if tree else []:
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and str(key.value) in FORBIDDEN_FRAGMENT_KEYS:
                    bad.append(f"features/reseed.py:{node.lineno} 回显口令片段键 {key.value!r}")
    if bad:
        FAILS.append("R6 诊断回显不许带口令片段（只许回长度 `*_len`）：\n      " + "\n      ".join(bad))
    else:
        print("  ✓ R6 reseed 诊断片段不回显口令（只回长度）")


def r7_iyuu_merge() -> None:
    path = ROOT / "features" / "settings.py"
    src = path.read_text(encoding="utf-8")
    problems = []
    if re.search(r"self\._iyuu_sites\s*=\s*\{", src):
        problems.append("`self._iyuu_sites = {`（整份替换：会把出口回显的 `***` 写成真值）")
    if "is_secret_blank" not in src:
        problems.append("缺少 `is_secret_blank`（空/掩码必须跳过，不能覆盖真值）")
    if problems:
        FAILS.append("R7 iyuu_sites 保存路径不是「逐字段合并」：\n      " + "\n      ".join(problems))
    else:
        print("  ✓ R7 iyuu_sites 保存 = 逐字段合并且跳过空/掩码")


def main() -> int:
    print("── 凭据外泄护栏（tools/check_secret_echo.py）──")
    r1_single_source()
    r2_single_masker()
    r3_save_data_whitelist()
    r4_outlets_masked()
    r6_no_fragment_echo()
    r7_iyuu_merge()
    for note in NOTES:
        print(f"  · 豁免：{note}")
    if FAILS:
        print("\n❌ 凭据外泄护栏未通过：")
        for f in FAILS:
            print(f"  ✗ {f}")
        return 1
    print("\n✅ 凭据外泄护栏通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
