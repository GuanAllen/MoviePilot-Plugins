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
        ["复用/辅种副本（**非真实下载**，不判 H&R）", "`MARK_REUSE` = `魔流-辅种`", "`tagspec.py`"],
        ["跨站来源份（H&R 走**资源账**，不走账单）", "`CROSSSEED_TAG` = `魔流-跨站`", "`crossseed.py`"],
        ["救援补源副本（**非真实下载**）", "`RESCUE_TAG` = `魔流-补源`", "`tagspec.py` / `rescue.py`"],
        ["插件外/MP 手动加的种（**只标不动**）", "`EXTERNAL_TAG` = `魔流-外部`", "`tagspec.py`"],
        ["「非下载」标签集", "`NON_DOWNLOAD_TAGS` = `(MARK_REUSE, RESCUE_TAG)`", "`tagspec.py`"],
        ["MP `已整理/辅种`（**真实下载** → 仍欠 H&R）", "`ASSET_TAGS` = `('已整理','辅种')`", "`tagspec.py`"],
        ["retag 不冲掉的特殊标签", "`SPECIAL_TAGS`", "`tagspec.py`"],
        ["站点职务标签格式", "`魔流-<站>-<职务>-<身份>`", "`tagspec.py`"],
    ]},
    {"title": "职务 / 身份（`tagspec.py`）", "head": None, "rows": [
        ["职务 `STATE_*`：`刷流`(STATE_BRUSH) / `魔力`(STATE_BONUS) / `静默`(STATE_SILENT) / "
         "`推荐`(STATE_RECOMMEND) / `保种`(**STATE_HR，不可手设**，只由 `_hr_obligation` 派生）。"],
        ["身份 `SUB_*`：`新`(SUB_NEW) / `资源`(SUB_RESOURCE) / `普通`(SUB_PLAIN)。"],
        ["状态账本真值源：`SeedLedgerStore`（`ledger.py`，5 表后端）。"],
    ]},
    {"title": "H&R 账单（`features/hrbills.py`；真值源 `hr_bills.json`）", "head": None, "rows": [
        ["状态 `BILL_STATE_*`：`active` / `pending` / `settled` / `void` / `breached`。"],
        ["「不该开账」判定：`_skip_hr_bill`（`features/hrbills.py`）= 复用/补源副本"
         "（`MARK_REUSE`/`RESCUE_TAG`）；★ 19.10.11 起**跨站来源份不跳过**（那是真实下载，欠来源站 H&R）。"],
        ["站点要求时长：`_hr_need_hours()` → 站规则 `seed_need_hours` → 默认 `HR_NEED_HOURS_DEFAULT=24.0`。"],
        ["存量作废（辅种）：`GET /tags?action=hrbills_void_reuse`（默认干跑，`confirm=1` 才写）。"],
        ["违约：种子消失 + active 账单 → `breached`（**只读报警**，`/agent/hr/breaches`）。"],
        ["站点对账（myhr.php，只判「还欠」不产 settled）：`_hr_reconcile_site`。"],
        ["★ 19.12.4 **站端确认闸门**：结清前先看站端 myhr 最近一轮对账（`_hr_site_debt_index` / "
         "`_hr_site_verdict`）—— 站端还欠就**不结清**、已 settled 的会被**重开**；站端说欠的 hash "
         "一律进保护集合（`_hr_bill_owed_hashes`）。回退开关 `HR_SETTLE_SITE_GATE`。"],
    ]},
    {"title": "做种时长四类口径(★ 别再统称「保种」)", "head": ["口径", "字段", "真值源 / 位置"], "rows": [
        ["**义务工时**(站点要求做满多少小时)", "`seed_need_hours` → 账单 `need_h`",
         "站点规则库 `sites/rules.py`;取不到 → `HR_NEED_HOURS_DEFAULT=24.0`(`features/hrbills.py:84`)"],
        ["**达标期限**(多久之内做满;保守取窗口)", "`seed_window_hours` / `seed_hours`",
         "同上;同句同时命中「N 天」+「M 小时」时 → 窗口进 `seed_window_hours`、小时进 `seed_need_hours`"],
        ["**本地保护期**(本机删种保护,用户配置)", "`min_seed_time`",
         "`models.py`;`features/brush.py` 灌进 `MagicPolicy.min_seed_time_hours`"],
        ["**轮转周期**(刷流做种满几天腾位)", "`brush_seed_days`",
         "`models.py`(默认 2 天);`features/cleanup.py`"],
        ["**考核均值**(新手考核的平均做种要求,**不是** H&R)", "`exam_avg_hours`",
         "`sites/rules.py:_EXAM_RE`(命中即 `continue`);`features/agentledger.py`"],
    ]},
    {"title": "本地保护期 `min_seed_time`(★ 唯一本机侧时长,勿与站点侧混)", "head": None, "rows": [
        ["是**本机删种保护期**:做种时长不足的种子不参与删种(`bonus.py` `MagicPolicy.min_seed_time_hours`);"
         "**不是**站点 H&R 义务,也**不**参与 H&R 结清判定。"],
        ["真值源:任务配置 `models.py::MagicFlowTaskPayload.min_seed_time`;`features/tasks.py` 落库、`features/brush.py` 灌给策略。"],
        ["易混 ①:`crossseed_seed_hours_default`「来源站义务工时(兜底)」——那是**他站**的 H&R 要求,两者同页并列、都带「最短」,但分属站点侧/本机侧。"],
        ["易混 ②:`brush_seed_days` 轮转周期——那是「满 N 天**主动清理**」,本项是「不足 N 小时**不许清理**」,方向相反。"],
    ]},
    {"title": "轮转周期 `brush_seed_days`", "head": None, "rows": [
        ["刷流模式:**已下完**的种子做种满 N 天即清理换种、腾位(`features/cleanup.py`);"
         "**不是**保护期——它是「到点就删」而非「到点才可删」。"],
        ["`0` = 不按天数轮换,回退「无上传」判定(平均上传速率低于 `upload_min_kbps` 才清)。"],
        ["真值源:任务级 `models.py::MagicFlowTaskPayload`(默认 2) + 默认模板 `MagicFlowDefaultsPayload`(默认 2);`common.py` 同名常量。"],
        ["易混:UI 三处旧名「保种天数」/「刷流保种天数」/「满 N 天清理」指的都是它 → 统一改「轮转周期(天)」。"],
    ]},
    {"title": "考核均值 `exam_avg_hours`(新手考核 ≠ H&R)", "head": None, "rows": [
        ["站点**新手考核**里「平均做种时间」的达标线(例:指标2:平均做种时间,要求 30 Hour);"
         "**不是** H&R 义务工时,未达标不产生 H&R 账单、不进 `hr_bills.json`。"],
        ["真值源:`sites/rules.py::parse_hr_from_html` 走 `_EXAM_RE` 单独分支(命中即 `continue`,不当 H&R 使);证据存 `exam_evidence`。"],
        ["易混:`seed_need_hours` 义务工时——考核均值只对**升级/考核**生效,且口径是「平均」而非「单种」。"],
        ["改名前:`features/agentledger.py` 列 desc 写作「考核平均保种小时」,与 `min_seed_time` 共用「保种」→ 已改「考核均值(h)」。"],
    ]},
    {"title": "达标期限 vs 义务工时(`seed_hours`/`seed_window_hours` vs `seed_need_hours`)", "head": None, "rows": [
        ["一句话:「**N 天(达标期限)内做满 M 小时(义务工时)**」;`seed_need_hours`=M,`seed_window_hours`/`seed_hours`=N×24。"],
        ["★ `seed_hours` 一名三义,看位置:`db.py` = 达标期限;`sites/claim_presets.py` `target_seed_hours` = 认领目标做种时长;"
         "`features/crossseed.py` 的 `seed_hours` = 跨站来源份兜底时长。**改名只对第一处生效**,另两处是同名不同义,别一起改。"],
        ["★ 保守原则:同句同时抓到「10 天」和「20 小时」时,`seed_hours` 取**窗口**(240h)而不是达标线(20h)——"
         "多挂几小时只是占盘,少挂就是真罚款(见 `sites/rules.py` `BUILTIN_RULES[\"pt.btschool.club\"]` 注释)。"],
        ["变体:`seed_hours_retired`(非权威来源被作废的旧值)、`seed_hours_seen`(低置信度只留证据不生效)——**都不参与**有效时长计算。"],
    ]},
    {"title": "H&R 安全垫与临期阈值(`hr_seed_margin_hours` / `hr_deadline_warn_hours`)", "head": None, "rows": [
        ["`hr_seed_margin_hours`(默认 2):结清**安全垫**——实际做种需 ≥ 义务工时 + 该值才判 `settled`(`features/hrbills.py`;账单 `due_h = need_h + margin`);`0` = 不垫。"],
        ["`hr_deadline_warn_hours`(默认 48):账单**临期阈值**——种还在 qB、未达标、距达标期限到期 ≤ 该值 → `at_risk`;**预警 ≠ 违约**。"],
        ["★ 与 `notify_hr_hours`(默认 24)区分:后者是**通知模块**扫描 `hours_left ≤ 阈值` 的发信门槛(`features/notify.py`);"
         "前者是**账单模块**打 `at_risk` 标记的口径。两者都是「剩余时间阈值」,但消费者不同、默认值不同,**别合并**。"],
        ["真值源:全局设置 `models.py::MagicFlowSettingsPayload`;`features/core.py` 读入 `self._hr_seed_margin_hours` / `self._hr_deadline_warn_hours`。"],
    ]},
    {"title": "站点报表分类桶（`features/sitereport.py`）", "head": None, "rows": [
        ["★ 两轴分级：第一级七桶 `BUCKET_BRUSH` 刷流 / `BUCKET_BONUS` 魔力 / `BUCKET_CLAIM` 认领（19.10.11，站点认领承诺） / "
         "`BUCKET_HR` 保种（欠H&R挂补） / "
         "`BUCKET_SILENT` 静默（含 新/资源/普通 三子桶）/ `BUCKET_RESCUE` 补源 / `BUCKET_EXTERNAL` 外部（顺序见 `_BUCKET_ORDER`）。"],
        ["第二级传输三态：`TRANSPORT_DOWNLOADING` 未完成 / `TRANSPORT_PAUSED` 暂停 / `TRANSPORT_SEEDING` 做种中（不单独成桶）。"],
        ["债务/账本只作列字段（`item.hr`/`item.bill`），不再当桶。"],
    ]},
    {"title": "静默池 / H&R 保种宿主（11.11.0）", "head": None, "rows": [
        ["静默宿主任务 `SILENT_HOST_TASK_ID='__silent_host__'`；H&R 保种宿主任务 "
         "`HR_HOST_TASK_ID='__hr_host__'`（职务「保种」）——见 `common.py`。"],
        ["总开关 `SILENT_HR_SPLIT_ENABLED`（`common.py`）——**关掉 = 整体回滚到 11.10 行为**。"],
        ["静默硬不变量 `_silent_pause_gate`（`features/silent.py`）：静默池一律 pause、无 H&R 例外。"],
        ["★ 19.10.13 闸门**先复核账本**再 pause：账本 `state` 不是「静默」、或 `taken_by` 是占岗岗位"
         "（`dutyreg.occupancy`）→ 跳过（记 `skipped_on_duty`）；查不到记录（tag_only 辅种副本）→ 照旧暂停。"
         "原来无条件 pause 全靠调用方写对 state，点播释放整批递 hash 时会把认领/保种的种一起停掉。"],
        ["★ 19.10.13 审计侧同口径：`_silent_audit` 的 `stalled_violation` 也按 `taken_by` 占岗豁免，"
         "**不再只靠 `claim_hashes()`**——那是打站点换来的，站点抖一下返回空集，在岗的认领种就被整批判违规暂停"
         "（qB 日志实证：每小时 :1x 分集中暂停 929 个，含认领种）。账本占位是本地真值，外部接口失败不该改判据。"],
        ["遣散分诊 `_split_release`（`features/core.py`）：欠 H&R → 保种；否则 → 静默 + pause。"],
        ["保种迁移 `_hr_host_assign` / `_hr_host_release`（`features/hr.py`）。"],
    ]},
    {"title": "认领职务（19.10.11）", "head": None, "rows": [
        ["职务常量 `STATE_CLAIM='认领'`（`tagspec.py`，已进 `STATES`/`DUTY_STATES`）；标签轴 `魔流-<站>-认领`，身份轴原样保留。"],
        ["宿主 `CLAIM_TASK_ID='__claim__'`（`common.py`）：`taken_by=__claim__` + 长期租约 → 任务分派抢不走。"],
        ["**名单 = 认领账本 `st∈{ok,already}`**（`_claim_duty_targets`）——与刷流/魔力的「任务分派清单」同构：名单在=上班，名单不在=下班。"],
        ["纳管/退出 worker：`_claim_host_status(resume=True)`（`features/claim.py`，15 分钟一轮）。退出还原 `prev_state`（只认刷流/魔力），缺省回静默并当场 pause。"],
        ["手动退出：`set_tag_state` 把职务改成非「认领」→ 账本 `manual=True` → worker 不再拉回；改回「认领」即恢复。"],
        ["跨职务抢占（19.10.12）：**只认 `dutyreg.duty_take_check`** —— 认领是 `poach=True` 的特殊岗位，"
         "可从刷流/魔力/点播/音乐/H&R 名下收人；但手动保种（95）比它高，不抢。"
         "别再加「某处显式跳过 `__claim__`」那种补丁。"],
    ]},
    {"title": "岗位注册表 / 占位口径（19.10.12，`dutyreg.py`）", "head": None, "rows": [
        ["单一真值：岗位 id / 展示名 / 职务 / 优先级 / 租约 / **能不能跨岗挑人**全在 `DUTIES` 一张表；"
         "`common.py` 的 id 常量、`ledger._task_state|_task_id|_task_name`、`set_tag_state` 白名单都从表派生。"],
        ["占位唯一闸门 `duty_take_check(taker, holder, lease_until=, now=)` → `(能否, 原因)`；"
         "读账本那一侧包成 `dutyops.free_for(rec, taker, now=)`，调用方不必再手抠 `taken_by`/`lease_until`。"],
        ["**默认口径：只从「没岗位」的池子招人**（`poach=False`）—— 静默托管/辅种不算占岗（静默=没岗位）；"
         "未登记真任务（动态 task_id）看租约，过期即视为空缺。"],
        ["特殊岗位（`poach=True`）只有三个：**手动保种 95 / 认领 90 / H&R 80** —— 「不做就违约」或「人工点名」。"
         "它们也只能从**优先级更低**的岗位挑人（同级不抢，先到先得）。"],
        ["加岗位别回头补「跳过它」：在 `DUTIES` 里写 `priority` / `poach` 就够；"
         "`tools/test_dutyreg.py` 钉住 8 岗位落库值与这套矩阵。"],
    ]},
    {"title": "岗位操作 / 纳管中台（19.10.12，`dutyops.py`）", "head": None, "rows": [
        ["分工：`dutyreg` = **岗位表 + 判据**（纯数据）；`dutyops` = **交接动作**（读账本 → 判 → 贴标签 → 写账本 → 谁拉起）。"],
        ["`assign(host, hashes, taker=, state=, ...)`：占岗。四个老实现（`tags.duty_assign` 音乐点播 / "
         "`_hr_host_assign` / `_manual_hold` / 认领纳管）现在都是它的薄壳，差异只在关键字："
         "`lease_until` / `prev_from` / `require_live` / `require_site` / `resume_when` / `extra` / `default_sub`。"],
        ["`release(host, hashes, taker=, ...)`：退岗。`restore_prev` 决定「还原成原职务」还是「回静默」，"
         "`pause` 决定是否当场暂停，`allow_untaken` 用于清洗 `taken_by` 已空的历史行。"],
        ["两个不变量：**一个种同一时刻只归一个岗位**；**贴标签成功才写账本**（标签是 qB 真值，账本是镜像）。"
         "在岗判定 = 账本归本岗 **且** 职务标签在位 —— 任一路径清过 `taken_by` 都能自愈（认领拉锯的根因）。"],
        ["`claim_hashes(host, site_id=None)`：认领名单归一化（小写集合，取不到 = 空集）；"
         "删除闸门 / 静默审计 / 保护裁决 / 任务纳管四处原来各写一遍 `{str(x).lower() ...}`，现在统一走它。"],
        ["`tools/test_dutyops.py` 用桩对象钉住：让位 / 跨岗挑人 / 幂等 / 干跑零写入 / 还原 prev_state。"],
    ]},
    {"title": "下载器写操作中台（19.10.14，`dlops.py`）", "head": None, "rows": [
        ["**为什么有它**：每 60 分钟 qB 固定 930 个被暂停、911 个被恢复，精确对消；"
         "逐个排除插件内四个 `pause_torrents` 调用点后仍**定位不到** —— 写操作散在 9 个文件、"
         "成功路径全都不打日志，「谁停的」在当前结构下不可回答。"],
        ["`pause / resume / recheck(host, hashes, by=, reason=, force=, dry=)`：**唯一出口**。"
         "`by` 必填（写进日志的就是「谁干的」）；`force=True` 只给「结清 / 遣散 / 人工点名」这类必须停的路径。"],
        ["**守卫（一处判据）**：`pause` 拒 —— 账本 state 非静默（在别的生命周期）或 `taken_by` 占岗；"
         "`resume` 拒 —— 静默且无人占岗（休息区）。**只看账本不看标签**（标签会掉、会双写）。"],
        ["**防抖**：同一 hash 在 `FLAP_WINDOW=90s` 内被**反向**操作 → 拒绝并计 `flapped`。"
         "这一条直接掐死「停 930 → 起 911 → 再停」的对消，不必先定位凶手。"],
        ["**归因日志**（成功也打）：`dlops:pause by=silent_gate 请=930 成=907 拒=23(on_duty:23) 抖=0`。"],
        ["已接的三处：`silent._silent_pause_gate`（by=silent_gate）/ `core._apply_run_mode`（by=run_mode:*，force）"
         "/ `siteops.deleted_site_act`（by=siteops:*，force）。`tags.set_tag_state` 是单 hash 人工操作，"
         "留在原地（根模块不能反向 import dlops，会成环）。"],
        ["**管得住插件自己人，管不住外部进程**（另一个容器/脚本直连 qB）。若某轮日志显示"
         "「本插件一次 pause 都没发」而 qB 仍在停，即可反证是外部调用方。"],
        ["`tools/test_dlops.py` 用桩对象钉住：静默可停不可起 / 在岗不可停 / 占岗不可停 / force / 防抖 / 干跑 / 归因。"],
    ]},
    {"title": "真值源清单（改前先认这个，**不造第二份**）", "head": ["真值源", "位置"], "rows": [
        ["账本 5 表（site/resource/identity/task/seed…）", "`ledger.py`"],
        ["资源账（一份内容 = 一条资源）", "`ResourceLedgerStore`（`ledger.py`，5 表后端）"],
        ["标签状态账本", "`SeedLedgerStore`（`ledger.py`，5 表后端）"],
        ["H&R 账单", "`features/hrbills.py` → `hr_bills.json`"],
        ["删除**唯一**出口（闸门）", "`DownloaderAdapter.delete_torrents` + `features/deletegate.py`"],
        ["下载器写操作**唯一**出口（暂停/恢复/校验）", "`dlops.pause/resume/recheck`（19.10.14）"],
        ["外部取数**唯一**出口", "`collect.py`"],
        ["模块职责（**文件 → 作用**）", "各文件模块 docstring **首行**（本接口 modules 节现算，不另存）；"
         "大模块（≥300 行）由 `preflight` 第 19 步 `tools/check_module_doc.py` 守住 —— "
         "描述与实际不符时，先改描述，改不动就说明该拆文件了"],
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
