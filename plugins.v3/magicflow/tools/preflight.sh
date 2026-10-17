#!/bin/sh
# 魔流 · 提交前自检（硬护栏总闸）。全部通过才算「可以部署」。
#
# 2026-10-10 Master 拍板「砍」：原第 11 步「代码字典同步」(`tools/gen_code_dict.py --check`)
# 与第 16 步「坐标认领」(`tools/check_dict_claims.py`) 已整块移除（16 步 → 14 步）；
# 2026-10-14 新增第 15 步「MCP 工具描述/类型/截断护栏」(`tools/check_mcptools_desc.py`)；
# 2026-10-15 新增第 16 步「设置键集输出面」(`tools/check_settings_keys.py`) —— 断言
# `src/utils.js::normalizeSettings()` 保留 `SettingsDialog.vue` 绑定的每个设置键
# （背景：该函数曾是闭集，`claim_*`/`hr_*` 改了存不进还提示「已保存」）。
# 2026-10-17 新增第 17 步「凭据外泄」(`tools/check_secret_echo.py`) —— 背景：Master 指令
# 「不管理/不自存/不回显站点 cookie·API 凭据」；该步断言凭据类键在出口（Response/data、
# 插件原生设置表单、诊断回显）一律过 `common.redact_secrets`/`mask_*`，且脱敏实现只有一份。
# 理由：本地 agent 有文件系统，grep/glob/read 即工作区真值；字典镜像只是「已部署构建的
# 滞后近似」且成本必付。`codedict.py` + `GET /agent/code-dict` 保留（运行时现算，本地 0 成本）。
set -e
cd "$(dirname "$0")/.."

echo "── 1/17 语法编译 ─────────────────────────────"
python3 -m py_compile $(find . -name '*.py' -not -path './node_modules/*' -not -path './_backup/*')
echo "✅ py_compile"

echo "── 2/17 依赖方向（护栏①）─────────────────────"
python3 tools/check_deps.py

echo "── 3/17 未定义名（护栏④）────────────────────"
python3 tools/check_names.py

echo "── 4/17 契约（护栏③）────────────────────────"
python3 tools/check_contracts.py

echo "── 5/17 功能页对齐（契约③）──────────────────"
python3 tools/check_pages.py

echo "── 6/17 模块登记表（护栏②）──────────────────"
python3 tools/gen_modules.py --check

echo "── 7/17 棘轮（禁止新增跨界 self._ 调用）──"
python3 tools/check_self_calls.py

echo "── 8/17 能力清单漂移（登记制：路由表 ↔ GET /agent 清单求差）──"
python3 tools/check_agent_manifest.py

echo "── 9/17 AI 对齐校验（前端覆盖=下限 + 真值源覆盖=目标）──"
python3 tools/check_agent_parity.py

echo "── 10/17 补源来源站护栏（hr != False 一律禁用）──"
python3 tools/check_rescue_guard.py

echo "── 11/17 Vue 模板 ref 误用（护栏⑤）──"
python3 tools/check_vue_template_refs.py

echo
echo "── 12/17 前端 composables 依赖闭环 + 解构对齐（护栏⑥）──"
python3 tools/check_composables.py

echo
echo "── 13/17 Vue 模板绑定漏声明（护栏⑦）──"
python3 tools/check_template_bindings.py



echo
echo "── 14/17 Vue API 未导入（护栏⑧，防白屏：无 auto-import 须显式 import）──"
python3 tools/check_vue_imports.py

echo
echo "── 15/17 MCP 工具描述/参数类型/截断（护栏⑨）──"
python3 tools/check_mcptools_desc.py

echo
echo "── 16/17 设置键集输出面（前端 normalizeSettings ⊇ UI 绑定）──"
python3 tools/check_settings_keys.py

echo
echo "── 17/17 凭据外泄（出口遮罩 / 日志回显 / 单一真值源）──"
python3 tools/check_secret_echo.py

echo "✅✅ preflight 全通过"
