# AGENTS.md

本工作区是 **MagicFlow**（PT 自动化 / MoviePilot 插件）项目。

## 环境排查入口

涉及 **DSH（DeepSeek Harness）** 的问题——尤其是插件路由 404、插件面板/挂件能显示但数据或设置加载失败、
「设置读取失败」这类症状——先读 [docs/DSH-网关与插件路由.md](docs/DSH-网关与插件路由.md)。

要点：本机 DSH Web 只监听回环，浏览器是经**飞牛网关 + `/app/fn-deepseek-harness/` 前缀**访问的，
网关注入的 bridge 只给白名单内的路径补前缀，白名单文件 `/vol1/@appdata/fn-deepseek-harness/gateway/path-allowlist.json`
的缺失就是这类问题的根因；该笔记里有一步定位法和写入规则。

## 定位代码：用 grep / glob / read（原红线④「查字典 + 坐标认领」已废）

2026-10-10 Master 拍板**整块砍除**「改代码前查字典 + 改完把坐标认领进 `docs/CODE-CLAIMS.md`」
（连带 `docs/CODE-DICT.md`、`tools/gen_code_dict.py`、`tools/check_dict_claims.py`、`tools/test_dict_claims.py`、
preflight 第 11/16 步、DSH hook 注入）。理由：本地 agent 有文件系统，`grep`/`glob`/`read` **直接给工作区真值**；
字典镜像只是「已部署构建的滞后近似」（实测注入坐标偏差 ±2～15 行，且偏差正是被监视的那次编辑造成的），
**收益≈0 而成本必付**（每次提问一行提醒 + 每次编辑注入命中，实测 5–9K tok/会话）。
需要按关键词找符号/端点/口径时用在线门面 `GET /agent/code-dict?q=关键词`（真值源 `codedict.py`，运行时现算）；
`codedict.py` 与 `GET /agent/code-dict` 保留不动（对本地 0 成本）。preflight 现为 **17 步**
（第 15 步 = MCP 工具描述护栏 `tools/check_mcptools_desc.py`，2026-10-14 加；第 16 步 = 设置键集护栏 `tools/check_settings_keys.py`，2026-10-15 加；
第 17 步 = 凭据外泄护栏 `tools/check_secret_echo.py`，2026-10-17 加）。

## 汇报纪律（Master 要求）

**每一次改动/部署，都要在同一轮里明确告诉 Master「更新了什么」**——不许只回「已修复」「已部署」这种结论。
最小内容：

- **改了什么**：文件 + 函数/符号 + 行为前后差异（要能落到具体代码行为，不写「优化了逻辑」）。
- **为什么改**：触发它的现场证据 / 根因。
- **验证**：跑了哪些护栏/测试/真机端点 + 数字结果（preflight N/N、断言数、端点返回值前后对比）。
- **部署到哪**：容器副本 / 监控源 / 本地市场索引 / 公共市场仓，逐个说清「已更新 / 未更新」。
- **影响面**：行为变化波及的现有功能，以及需要 Master 亲自处理的事项。

逐版留痕按同一口径写在 `docs/DESIGN-CURRENT.md` §8（按时间倒序，一版一段）。
