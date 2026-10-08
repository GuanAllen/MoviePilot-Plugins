#!/bin/sh
# 魔流 · 提交前自检（硬护栏总闸）。全部通过才算「可以部署」。
set -e
cd "$(dirname "$0")/.."

echo "── 1/14 语法编译 ─────────────────────────────"
python3 -m py_compile $(find . -name '*.py' -not -path './node_modules/*' -not -path './_backup/*')
echo "✅ py_compile"

echo "── 2/14 依赖方向（护栏①）─────────────────────"
python3 tools/check_deps.py

echo "── 3/14 未定义名（护栏④）────────────────────"
python3 tools/check_names.py

echo "── 4/14 契约（护栏③）────────────────────────"
python3 tools/check_contracts.py

echo "── 5/14 功能页对齐（契约③）──────────────────"
python3 tools/check_pages.py

echo "── 6/14 模块登记表（护栏②）──────────────────"
python3 tools/gen_modules.py --check

echo "── 7/14 棘轮（禁止新增跨界 self._ 调用）──"
python3 tools/check_self_calls.py

echo "── 8/14 能力清单漂移（登记制：路由表 ↔ GET /agent 清单求差）──"
python3 tools/check_agent_manifest.py

echo "── 9/14 AI 对齐校验（前端覆盖=下限 + 真值源覆盖=目标）──"
python3 tools/check_agent_parity.py

echo "── 10/14 补源来源站护栏（hr != False 一律禁用）──"
python3 tools/check_rescue_guard.py

echo "── 11/14 代码字典同步（符号级索引，跟代码走）──"
python3 tools/gen_code_dict.py --check

echo "── 12/14 Vue 模板 ref 误用（护栏⑤）──"
python3 tools/check_vue_template_refs.py

echo
echo "── 13/14 前端 composables 依赖闭环 + 解构对齐（护栏⑥）──"
python3 tools/check_composables.py

echo
echo "── 14/14 Vue 模板绑定漏声明（护栏⑦）──"
python3 tools/check_template_bindings.py

echo "✅✅ preflight 全通过"
