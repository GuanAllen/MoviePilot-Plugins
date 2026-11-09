#!/bin/sh
# 魔流 · 提交前自检（硬护栏总闸）。全部通过才算「可以部署」。
#
# 2026-10-10 Master 拍板「砍」：原第 11 步「代码字典同步」(`tools/gen_code_dict.py --check`)
# 与第 16 步「坐标认领」(`tools/check_dict_claims.py`) 已整块移除（16 步 → 14 步）；
# 2026-10-14 新增第 15 步「MCP 工具描述/类型/截断护栏」(`tools/check_mcptools_desc.py`)；
# 2026-10-15 新增第 16 步「设置键集输出面」(`tools/check_settings_keys.py`) —— 断言
# `src/utils.js::normalizeSettings()` 保留 `SettingsDialog.vue` 绑定的每个设置键
# （背景：该函数曾是闭集，`claim_*`/`hr_*` 改了存不进还提示「已保存」）。
# 2026-10-27 新增第 18 步「UI 术语护栏」(`tools/check_ui_terms.py`) —— 断言
# label/hint/placeholder 字面量里不再出现「保种天数/最短做种/保种时长/保种期」等
# 时长语义混用词（四个定名：达标期限/义务工时/本地保护期/轮转周期，见 GLOSSARY）。
# 2026-10-17 新增第 17 步「凭据外泄」(`tools/check_secret_echo.py`) —— 背景：Master 指令
# 「不管理/不自存/不回显站点 cookie·API 凭据」；该步断言凭据类键在出口（Response/data、
# 插件原生设置表单、诊断回显）一律过 `common.redact_secrets`/`mask_*`，且脱敏实现只有一份。
# 2026-10-29 新增第 24 步「换行符统一」(`tools/check_eol.py`) ——
#   `write_text(encoding="utf-8")` 在 Windows 上默认 newline=None，会把 \n 翻译成 \r\n。
#   实测累积 27 个文件全 CRLF（tags.py / ledger.py / features/silent.py / common.py 等），
#   后果：git diff 显示整文件重写、备份比对失真。修法：字节级 replace(b"\r\n", b"\n")。
# 2026-10-29 新增第 23 步「函数注释棘轮」(`tools/check_func_doc.py`) ——
#   Master 定的约束：构造函数时必须在固定位置（def 下一行第一句 docstring）写注释。
#   方案 A 棘轮：1876 个存量函数指纹冻结进 `tools/.func_doc_baseline.json`（不查历史），
#   新函数与**函数体改动过**的函数必须过 4 条（空话 / 太薄 / 复读 / 换名）。
# 2026-10-28 新增第 22 步「import 名字可达性」(`tools/check_import_names.py`) ——
#   事故起因：``_norm`` 收进 norm.py 后，多行括号 import 未同步，语法全绿但生产
#   ``ImportError: cannot import name '_norm'``，插件连续 8 次加载失败、下线约 13 分钟。
#   该步断言每条 ``from X import ...`` 的名字都能在 X 模块级作用域取到（含 try/if 内定义）。
# 2026-10-28 新增第 21 步「固定偏移切片」(tools/check_slice_guard.py) ——
#   禁止用 s[:-1]/s[:-2] 删换行；固定切片必须加注释说明业务截断意图。
# 2026-10-28 新增第 20 步「数据清洗重复实现」(tools/check_norm_dup.py) ——
#   norm.py 之外不得再定义同名的 norm_key/first_num/float_ok/now_iso，
#   也不得换名字重写一遍（AST 同实现照抓）。
# 2026-10-28 新增第 19 步「模块职责」(`tools/check_module_doc.py`) —— 大模块（≥300 行）的
# docstring 首行必须说清「装什么 + 还兼了什么」。背景：`GET /agent/code-dict` 的 modules 节
# 「职责」字段就是摘 docstring 首行现算；2026-10-10 砍掉字典同步检查后再没人强制它跟上代码，
# 于是 tags.py 1042 行里 440 行媒体编排完全不体现在职责上，判分层时会据此判错。
# 理由：本地 agent 有文件系统，grep/glob/read 即工作区真值；字典镜像只是「已部署构建的
# 滞后近似」且成本必付。`codedict.py` + `GET /agent/code-dict` 保留（运行时现算，本地 0 成本）。
# 2026-11-07 新增第 26–31 步「任务 105/106/107 关键测试进门禁」（25 步 → 31 步）：
#   26 H&R 临期通知筛选（HR-04 幽灵告警）  27 H&R 通知端到端集成
#   28 设置保存字段守卫（R-01 空 payload / R-02 hr_*+journal_keep）
#   29 前端设置映射（短键→长键 + 总开关不被兜底开关污染）
#   30 推送审计 import 完整性（FE-01：裸 unwrapResponse 不再出现）
#   31 设置契约跨端一致（模型 / 后端消费键 / 映射产出键 / normalizeSettings 闭集）
#   背景：这些缺陷能穿过 25 步门禁，是因为门禁里一条测试都没跑（`grep -c test_` = 0）。
#   本段起测试失败 = preflight 非零退出；node 缺失时给出明确提示，不静默跳过。
set -e
cd "$(dirname "$0")/.."

echo "── 1/38 语法编译 ─────────────────────────────"
python3 -m py_compile $(find . -name '*.py' -not -path './node_modules/*' -not -path './_backup/*')
echo "✅ py_compile"

echo "── 2/38 依赖方向（护栏①）─────────────────────"
python3 tools/check_deps.py

echo "── 3/38 未定义名（护栏④）────────────────────"
python3 tools/check_names.py

echo "── 4/38 契约（护栏③）────────────────────────"
python3 tools/check_contracts.py

echo "── 5/38 功能页对齐（契约③）──────────────────"
python3 tools/check_pages.py

echo "── 6/38 模块登记表（护栏②）──────────────────"
# 开发态口径（2026-11-07，任务 110）：只校验「源码模块都登记」，行数/职责漂移
# 不阻断；发布路径由 tools/deploy.sh 重生成后跑严格 --check，故发布仍逐字节同步。
python3 tools/gen_modules.py --check-modules

echo "── 7/38 棘轮（禁止新增跨界 self._ 调用）──"
python3 tools/check_self_calls.py

echo "── 8/38 能力清单漂移（登记制：路由表 ↔ GET /agent 清单求差）──"
python3 tools/check_agent_manifest.py

echo "── 9/38 AI 对齐校验（前端覆盖=下限 + 真值源覆盖=目标）──"
python3 tools/check_agent_parity.py

echo "── 10/38 补源来源站护栏（hr != False 一律禁用）──"
python3 tools/check_rescue_guard.py

echo "── 11/38 Vue 模板 ref 误用（护栏⑤）──"
python3 tools/check_vue_template_refs.py

echo
echo "── 12/38 前端 composables 依赖闭环 + 解构对齐（护栏⑥）──"
python3 tools/check_composables.py

echo
echo "── 13/38 Vue 模板绑定漏声明（护栏⑦）──"
python3 tools/check_template_bindings.py



echo
echo "── 14/38 Vue API 未导入（护栏⑧，防白屏：无 auto-import 须显式 import）──"
python3 tools/check_vue_imports.py

echo
echo "── 15/38 MCP 工具描述/参数类型/截断（护栏⑨）──"
python3 tools/check_mcptools_desc.py

echo
echo "── 16/38 设置键集输出面（前端 normalizeSettings ⊇ UI 绑定）──"
python3 tools/check_settings_keys.py

echo
echo "── 17/38 凭据外泄（出口遮罩 / 日志回显 / 单一真值源）──"
python3 tools/check_secret_echo.py

echo
echo "── 18/38 UI 术语护栏（四个时长概念不再统称「保种」）──"
python3 tools/check_ui_terms.py


echo
echo "── 19/38 模块职责（字典「文件→作用」的来源）──"
python3 tools/check_module_doc.py

echo
echo "── 20/38 数据清洗重复实现（norm.py 唯一出口，护栏⑩）──"
python3 tools/check_norm_dup.py

echo
echo "── 21/38 固定偏移切片（删换行只能用 removesuffix/rstrip）──"
python3 tools/check_slice_guard.py

echo
echo "── 22/38 import 名字可达性（删符号必须同步 import，护栏⑫）──"
python3 tools/check_import_names.py

echo
echo "── 23/38 函数注释棘轮（新/改动函数必须有 docstring，护栏⑬）──"
python3 tools/check_func_doc.py

echo
echo "── 24/38 换行符统一（仓库内 .py/.sh 必须纯 LF，护栏⑭）──"
python3 tools/check_eol.py

echo
echo "── 25/38 API 路由表（142 条：无重复、无遮蔽、handler 可达）──"
python3 tools/check_api_routes.py

echo
echo "── 26/38 H&R 临期通知筛选（HR-04：settled/void 不进临期）──"
python3 tools/test_hr_notify_gate.py

echo
echo "── 27/38 H&R 通知端到端集成（notify_check_hr + 真实模块）──"
python3 tools/test_hr_notify_integration.py

echo
echo "── 28/38 设置保存字段守卫（R-01 空 payload / R-02 hr_*+journal_keep）──"
python3 tools/test_settings_save_guard.py

echo
echo "── 29/38 前端设置映射（短键→长键 + 总开关独立）──"
command -v node >/dev/null 2>&1 || { echo "❌ 需要 Node.js：第 29 步（前端设置映射）依赖 node"; exit 1; }
node tools/test_settings_mapping.js

echo
echo "── 30/38 推送审计 import 完整性（FE-01）──"
command -v node >/dev/null 2>&1 || { echo "❌ 需要 Node.js：第 30 步（推送审计 import 检查）依赖 node"; exit 1; }
node tools/test_use_push_audit_import.js

echo
echo "── 31/38 设置契约跨端一致（模型 / 后端 / 映射 / 草稿闭集）──"
python3 tools/test_settings_contract.py

echo
echo "── 32/38 趋势弹窗死链路（FE-03：不再传未定义的上传增量）──"
python3 tools/test_trend_upload_removed.py

echo
echo "── 33/38 H&R 账单存储契约（PG 单一权威：三态/写失败/meta）──"
python3 tools/test_hr_store_contract.py

echo
echo "── 34/38 存储失败关闭（N-129-03 + 占位 store 边界）──"
python3 tools/test_hr_store_failclosed.py

echo
echo "── 35/38 六条危险消费面故障注入（F7–F12 保守方向）──"
python3 tools/test_hr_consumer_guards.py

echo
echo "── 36/38 视图层 UNKNOWN 展示（reportview / agentapi）──"
python3 tools/test_hr_views_unknown.py

echo
echo "── 37/38 过期清理编排（30 天 / 批量 / 失败关闭 / 幂等）──"
python3 tools/test_hr_purge.py

echo
echo "── 38/38 H&R 账单业务契约（删除归一 / 墓碑重开 / 事件事务 / 接管矩阵）──"
python3 tools/test_hr_bill_contract.py

echo
echo "✅✅ preflight 全通过"
