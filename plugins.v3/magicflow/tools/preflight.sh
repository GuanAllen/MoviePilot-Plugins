#!/bin/sh
# 魔流 · 提交前自检（硬护栏总闸）。全部通过才算「可以部署」。
set -e
cd "$(dirname "$0")/.."

echo "── 1/11 语法编译 ─────────────────────────────"
python3 -m py_compile $(find . -name '*.py' -not -path './node_modules/*' -not -path './_backup/*')
echo "✅ py_compile"

echo "── 2/11 依赖方向（护栏①）─────────────────────"
python3 tools/check_deps.py

echo "── 3/11 未定义名（护栏④）────────────────────"
python3 tools/check_names.py

echo "── 4/11 契约（护栏③）────────────────────────"
python3 tools/check_contracts.py

echo "── 5/11 功能页对齐（契约③）──────────────────"
python3 tools/check_pages.py

echo "── 6/11 模块登记表（护栏②）──────────────────"
python3 tools/gen_modules.py --check

echo "── 7/11 棘轮（禁止新增跨界 self._ 调用）──"
python3 tools/check_self_calls.py

echo "── 8/11 能力清单漂移（登记制：路由表 ↔ GET /agent 清单求差）──"
python3 tools/check_agent_manifest.py

echo "── 9/11 AI 对齐校验（前端覆盖=下限 + 真值源覆盖=目标）──"
python3 tools/check_agent_parity.py

echo "── 10/11 补源来源站护栏（hr != False 一律禁用）──"
python3 tools/check_rescue_guard.py

echo "── 11/11 代码字典同步（符号级索引，跟代码走）──"
python3 tools/gen_code_dict.py --check

echo
echo "✅✅ preflight 全通过"
