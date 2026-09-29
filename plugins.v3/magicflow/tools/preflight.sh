#!/bin/sh
# 魔流 · 提交前自检（硬护栏总闸）。全部通过才算「可以部署」。
set -e
cd "$(dirname "$0")/.."

echo "── 1/6 语法编译 ─────────────────────────────"
python3 -m py_compile $(find . -name '*.py' -not -path './node_modules/*' -not -path './_backup/*')
echo "✅ py_compile"

echo "── 2/6 依赖方向（护栏①）─────────────────────"
python3 tools/check_deps.py

echo "── 3/6 未定义名（护栏④）────────────────────"
python3 tools/check_names.py

echo "── 4/6 契约（护栏③）────────────────────────"
python3 tools/check_contracts.py

echo "── 5/6 功能页对齐（契约③）──────────────────"
python3 tools/check_pages.py

echo "── 6/6 模块登记表（护栏②）──────────────────"
python3 tools/gen_modules.py --check

echo
echo "✅✅ preflight 全通过"
