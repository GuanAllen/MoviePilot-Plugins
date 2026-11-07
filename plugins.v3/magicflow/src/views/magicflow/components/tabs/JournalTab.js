// JournalTab —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板）。
// 19.12.15：按设计稿「运行诊断」(2:1399) 重排为五卡布局 —— 五阶段运行流程 / 阶段明细 /
//   过滤原因 / 操作记录 / 诊断说明。过滤原因与操作记录是线上独有的真实数据，稿里没有但要留。
import './JournalTab.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$7,
  createBlock: _createBlock$6,
  createCommentVNode: _createCommentVNode$7,
  createElementBlock: _createElementBlock$7,
  createElementVNode: _createElementVNode$8,
  createTextVNode: _createTextVNode$7,
  createVNode: _createVNode$7,
  normalizeClass: _normalizeClass$3,
  normalizeStyle: _normalizeStyle$1,
  openBlock: _openBlock$8,
  renderList: _renderList$7,
  resolveComponent: _resolveComponent$8,
  toDisplayString: _toDisplayString$8,
  unref: _unref$3,
  withCtx: _withCtx$6,
} = __vue

// 19.12.15：删掉 4 个死导入（index.vue / useCandidates / useOperations / useTaskDetail）——
// 它们是 P4 拆组件时留下的，本组件只吃 props.data，一个都没用到；留着会把整个 app 拖进包里。
// 下面两个是真正用到的：日期/时长格式化 + 操作记录的展示函数。
import { formatDateTime, formatDurationSeconds } from '../../../../utils.js'
import { hasOpDetail, itemSourceText, opDetailItems, operationColor, operationDuration, operationIcon, operationKindText, operationStateText, operationSummary } from '../../opsDisplay.js'

// ── hoisted 静态节点（新增的用 mf-diag__* 前缀，与旧 .magicflow-* 并存）──
const _hoisted_1$7 = { class: "magicflow-panel__head" };
const _hoisted_2$7 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_3$6 = { class: "magicflow-flow__chain" };
const _hoisted_4$6 = { class: "magicflow-flow__dot" };
const _hoisted_5$6 = { class: "magicflow-flow__label" };
const _hoisted_6$5 = { class: "magicflow-panel__head" };
const _hoisted_7$5 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_8$5 = {
  key: 0,
  class: "magicflow-reasons"
};
const _hoisted_9$5 = { class: "magicflow-reason__track" };
const _hoisted_10$5 = {
  key: 1,
  class: "magicflow-table-empty"
};
const _hoisted_11$5 = { class: "magicflow-panel__head" };
const _hoisted_12$5 = { class: "magicflow-ops-filter" };
const _hoisted_13$4 = { class: "magicflow-events" };
const _hoisted_14$4 = {
  key: 0,
  class: "text-error"
};
const _hoisted_15$4 = ["onClick"];
const _hoisted_16$4 = {
  key: 2,
  class: "magicflow-events__detail"
};
const _hoisted_17$4 = { class: "magicflow-events__detail-line" };
const _hoisted_18$4 = {
  key: 0,
  class: "magicflow-events__detail-src"
};
const _hoisted_19$4 = ["title"];
const _hoisted_20$4 = {
  key: 1,
  class: "magicflow-events__detail-hash"
};
const _hoisted_21$3 = { class: "magicflow-events__detail-sub" };
const _hoisted_22$2 = {
  key: 0,
  class: "magicflow-table-empty"
};

// 新卡片的静态节点
const _hoisted_24$1 = { class: "mf-diag__head" };
const _hoisted_25$1 = { class: "mf-diag__titles" };
const _hoisted_26$1 = { class: "mf-diag__title" };
const _hoisted_27$1 = { class: "mf-diag__sub" };
const _hoisted_28$1 = { class: "mf-diag__metric" };
const _hoisted_29$1 = { class: "mf-diag__seq" };
const _hoisted_30$1 = { class: "mf-diag__thead" };
const _hoisted_31$1 = { class: "mf-diag__th mf-diag__th--name" };
const _hoisted_32$1 = { class: "mf-diag__th mf-diag__th--num" };
const _hoisted_33$1 = { class: "mf-diag__th mf-diag__th--io" };
const _hoisted_34$1 = { class: "mf-diag__th mf-diag__th--res" };
const _hoisted_35$1 = { class: "mf-diag__rows" };
const _hoisted_36$1 = { class: "mf-diag__dot" };
const _hoisted_37$1 = { class: "mf-diag__name" };
const _hoisted_38$1 = { class: "mf-diag__num" };
const _hoisted_39$1 = { class: "mf-diag__io" };
const _hoisted_40$1 = { class: "mf-diag__res" };
const _hoisted_41$0 = { class: "mf-diag__empty" };
const _hoisted_42$0 = { class: "mf-diag__notes" };
const _hoisted_43$0 = { class: "mf-diag__note-col" };
const _hoisted_44$0 = { class: "mf-diag__note-title" };
const _hoisted_45$0 = { class: "mf-diag__note" };
const _hoisted_48$0 = { class: "mf-diag__rule-text" };

const {computed: computed$q,reactive} = __vue;

// props：data = useTaskDetail / useCandidates / useOperations 的「状态 + 派生」整体下传（含 expandedOps），只读；
//        scope = 操作记录的类型筛选（原 opsKind），双向：emit update:scope；
//        task = 当前任务（原 selectedTask），用于判定刷流 / 养护。
//
// 19.12.15 重排后的口径约束（别照稿硬写，稿里有一列我们拿不到）：
//   ① 稿的「阶段明细」有「耗时」列，但接口只有整轮 `last_run_duration`，**没有分阶段耗时**
//      → 这一列换成同宽的「本轮」计数（真实字段），整轮耗时放到卡片右上角。
//   ② 稿的「诊断说明卡」写「自动重试 2 次 / 从失败阶段续起」—— 代码里没有这两条行为，
//      照抄等于给用户假承诺 → 右栏只写可验证的：站点冷却 180s、流控让路、限流不记死下轮重试、
//      凭据失效该站本轮让路（`common.SITE_FETCH_BACKOFF` / `brush._fetch` / `reseed`）。
//   ③ 五个阶段的指标全部取自 detail 接口真实字段（last_candidate_total / _passed / _kept /
//      _added / _deleted / _reused），没有的显示「—」，不编数。

const _sfc_main$8 = {
  __name: 'JournalTab',
  props: {
  data: { type: Object, required: true },
  scope: { type: [String, Number], default: '' },
  task: { type: Object, default: null },
},
  emits: ['update:scope', 'refresh', 'toggle-detail', 'open-pushes'],
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 运行诊断面板（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 契约见 docs/REFACTOR-FRONTEND.md §5：props `data` `scope` `task`；emits `update:scope` `refresh`。
// —— 运行诊断含：运行流程 / 阶段明细 / 过滤原因 / 操作记录（类型筛选可展开明细）/ 诊断说明。
const props = __props;
const emit = __emit;

// reactive() 解包 data 里的 ref / computed，模板沿用原 index.vue 的写法 `data.xxx`。
const data = reactive(props.data);

const taskIsBrush = computed$q(() => props.task?.task_type === 'brush');

function onScopeChange(value) { emit('update:scope', value); }

// —— 只属于本文件的展示函数 ——
// 展开态：本面板的展开表来自 props.data.expandedOps（弹窗读的是 props.expandedOps，不是同一份）
function isOpDetailOpen(opId) {
  return !!(data.expandedOps || {})[opId]
}

// ── 本轮运行的真实计数（全取自 detail 接口，不做推算）──
const runCounts = computed$q(() => {
  const d = data.detailStats || {}
  const total = Number(d.last_candidate_total || 0)
  const passed = Number(d.last_candidate_passed || 0)
  const kept = Number(d.last_kept || 0)
  const added = Number(d.last_added || 0)
  const deleted = Number(d.last_deleted || 0)
  const reused = Number(d.last_reused || 0)
  // 拦截数：优先「抓取 - 通过」，缺失时退回过滤原因累加（reasonEntries 是候选页的真实分布）
  const reasons = (data.reasonEntries || []).reduce((sum, item) => sum + Number(item.count || 0), 0)
  const blocked = Math.max(total - passed, 0) || reasons
  // 是否真的跑过一轮：只有 kept 有值不算（kept 是常驻做种数，只做种模式下也非零）
  const ran = total > 0 || passed > 0 || added > 0 || deleted > 0 || reused > 0
  return { total, passed, kept, added, deleted, reused, blocked, reasons, ran }
})

// 19.12.17：展示层护栏 —— 任何值进来都不允许渲染成 `[object Object]`。
// 线上踩过：这张卡有几处插值直接吃上游 computed，上游一旦没解包 / 接口字段变成嵌套结构，
// 页面上就是一排 `[object Object]`。展示层不该把对象原样丢给用户：
// 对象取 label/name/text/title，取不到就整体省略；数组按 · 连接。真值仍由上游保证。
function asText(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) return v.map(asText).filter(Boolean).join(' · ')
  if (typeof v === 'object') return asText(v.label ?? v.name ?? v.text ?? v.title ?? '')
  return String(v)
}

// 五阶段链的副标：入口检查 → 抓取候选 → …（跟任务类型走，刷流与养护阶段名不同）
const stageChain = computed$q(() => (data.flowNodes || []).map(node => asText(node.label)).filter(Boolean).join(' → '))

// 本轮有没有留下逐阶段记录（后端 run_stages）。有记录 = 这一轮真的跑过（哪怕只跑完入口）。
const hasStageRecords = computed$q(() => (data.flowNodes || []).some(node => node.recorded))

// 卡片右上角的「当前阶段」：与五步用**同一份口径**（node.state / node.recorded）。
// 之前是「五步靠 last_phase 推、标签靠 flowPhaseText 回落 last_run_status」，于是出现
// 「五步全灰只挂个待运行 + 右上角已完成」这种自相矛盾。
const phaseText = computed$q(() => {
  const nodes = data.flowNodes || []
  const d = data.detailStats || {}
  if (d.run_active) {
    const running = nodes.find(node => node.state === 'running')
    if (running) return asText(running.label)
    // 在跑却没有任何阶段打点 → 此刻跑的是检查/优化周期，不是刷流五步
    return hasStageRecords.value ? '执行中' : '维护中'
  }
  const bad = nodes.find(node => node.state === 'error')
  if (bad) return `中断于${asText(bad.label)}`
  if (hasStageRecords.value) return '完成'
  // 一条阶段记录都没有 = 这一轮没跑（做种/停止模式不跑刷流流程）。
  // 不再回退 last_phase / last_run_status：那俩是上一轮的残留，会说出「五步全灰但已完成」的矛盾。
  return asText(data.flowPhaseText) || '未执行'
})

// 五阶段卡底部的一行说明：回答「为什么五个点不动 / 这是哪一轮的记录」。
// 做种 / 停止模式本来就不跑刷流流程，不说明白就会被当成 bug（「永远第一个待执行」）。
const flowHint = computed$q(() => {
  const d = data.detailStats || {}
  const nodes = data.flowNodes || []
  if (d.run_active) {
    // 正在跑：有阶段记录 = 跑的就是刷流流程；一条都没有 = 跑的是检查/优化周期，
    // 它本来就不经过这五个阶段（「做种中」模式下每个周期都在跑它）。
    if (hasStageRecords.value) return '本轮执行中'
    return '正在执行维护流程（检查/优化）—— 它不经过刷流这五个阶段，所以五个点本轮不会动'
  }
  if (hasStageRecords.value) {
    // 有逐阶段记录：给出「这一轮是什么时候跑的」，避免和上一轮混淆
    const lastAt = Math.max(0, ...nodes.map(node => Number(node.at || 0)))
    if (!(lastAt > 0)) return ''
    const dt = new Date(lastAt * 1000)
    const pad = (n) => String(n).padStart(2, '0')
    return `本轮执行于 ${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`
  }
  const mode = String(d.run_mode || '')
  const modeName = { running: '运行中', seeding: '做种中', stopped: '已停止' }[mode] || ''
  const why = mode === 'seeding' ? '只维持做种、不跑刷流流程'
    : mode === 'stopped' ? '本轮不执行'
      : '本轮还没开始跑，等待调度'
  // 没有逐阶段记录时五步一律是灰的（不给假绿），这里补一句「上次什么时候跑过」
  const lastAt = Number(d.last_run_at || 0)
  let when = ''
  if (lastAt > 0) {
    const dt = new Date(lastAt * 1000)
    const pad = (n) => String(n).padStart(2, '0')
    when = `；上次执行 ${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`
  }
  return `本轮未执行 —— ${modeName ? `当前「${modeName}」，` : ''}${why}${when}`
})

// ── 卡 1 分叉（★ 19.12.24）：这张卡回答的是「任务此刻在干什么」──────────────
//   跑过刷流（后端有逐阶段记录）→ 五阶段流程；否则 → 做种实况。
//   ★ 为什么分叉：做种模式不抓种、不筛种，五个阶段本来就不会动。把一条永远不动的流程链
//     摆在这页最上面，用户读到的就是「坏了 / 永远第一个待执行」。做种期间该看的是做种本身
//     在不在、欠不欠 H&R、下一轮维护什么时候来 —— 那才是会变的东西。
//   ★ 判据只看**证据**，不看模式名：有阶段记录就说明真跑过刷流；run_active 且卡在 running
//     阶段则说明此刻正跑刷流。两者都没有就是没在跑，一律走做种卡。
const showFlow = computed$q(() => {
  const nodes = data.flowNodes || []
  if (nodes.some(node => node.recorded)) return true
  const d = data.detailStats || {}
  return !!d.run_active && nodes.some(node => node.state === 'running')
})

// 做种实况的四格 + 下一轮倒计时。全部取自真实字段，取不到就留空，不硬凑 0。
const seedView = computed$q(() => {
  const d = data.detailStats || {}
  const s = data.diagSeed || {}
  const mode = String(d.run_mode || '')
  const active = !!d.run_active

  // 标题 / 副标：说清此刻在做什么，以及「为什么不筛种」
  const title = mode === 'seeding' ? '做种中' : mode === 'stopped' ? '已停止' : mode === 'running' ? '等待下一轮' : '未运行'
  const sub = mode === 'seeding'
    ? (active
      ? '正在跑维护检查：核对种子状态与收益 —— 不抓新种、不筛种'
      : '只维持做种与收益：不抓新种、不筛种，种子池保持不变')
    : mode === 'stopped'
      ? '任务已停止：做种与调度都不在跑'
      : '本轮还没开始，到点会自动跑一遍五阶段流程'

  // 下一轮：running 模式等 brush_interval，其余等 check_interval（做种模式跑的是维护检查）
  // 已停止的任务不参与调度 —— 不能给它算「下一轮」，否则页面自己在说「停着但马上要跑」。
  const stopped = mode === 'stopped'
  const intervalMin = stopped ? 0 : (mode === 'running' ? Number(d.brush_interval || 0) : Number(d.check_interval || 0))
  const lastAt = Number(d.last_run_at || 0)
  const nowSec = Date.now() / 1000
  let leftSec = null
  if (lastAt > 0 && intervalMin > 0) leftSec = Math.max(0, Math.round(lastAt + intervalMin * 60 - nowSec))
  const totalSec = intervalMin > 0 ? intervalMin * 60 : 0
  const progress = (totalSec > 0 && leftSec !== null)
    ? Math.min(1, Math.max(0, 1 - leftSec / totalSec))
    : 0
  const nextText = leftSec === null ? ''
    : leftSec <= 1 ? '即将开始'
      : leftSec < 60 ? `${leftSec} 秒后`
        : `${Math.round(leftSec / 60)} 分钟后`
  const nextLabel = mode === 'running' ? '下一轮刷流' : '下一轮维护检查'

  // 体积：GB 到四位数就换 TB，别让「12480 GB」这种数出现在卡上
  const sizeGb = Number(s.sizeGb || 0)
  const sizeText = sizeGb >= 1000 ? `${(sizeGb / 1000).toFixed(2)} TB` : `${sizeGb.toFixed(1)} GB`

  // H&R：全站账本口径，所以「全站」两个字必须出现在格子上。
  // ★ 待结清 ≠ 欠账：账本里 pending 可能「工时早就够了、只是站端还没确认」。
  //   两者混着报会让人以为欠了一堆账（线上 22 颗 pending 全是这种），必须分开说。
  const hrKnown = Number(s.hrKnown || 0)
  const hrPending = Number(s.hrPending || 0)
  const hrOwed = Number(s.hrOwed || 0)
  const hrWaiting = Number(s.hrWaiting || 0)
  const hrAtRisk = Number(s.hrAtRisk || 0)
  const hrValue = hrKnown === 0 ? '—' : hrOwed > 0 ? String(hrOwed) : hrPending > 0 ? String(hrPending) : '0'
  const hrUnit = hrKnown === 0 || hrPending === 0 ? '' : '颗'
  const tightest = (s.hrTightest || [])[0] || null
  let hrNote = ''
  if (hrKnown === 0) {
    hrNote = '未取到全站 H&R 账本'
  } else if (hrOwed > 0 && tightest) {
    // 真欠：说清还差多少工时 / 站端给没给截止
    const left = tightest.left
    const leftText = left === null ? '站端未给截止' : left <= 0 ? '已超过站端截止' : `还剩 ${Math.round(left)}h`
    hrNote = `${asText(tightest.site)} · 已做种 ${Number(tightest.seeded || 0).toFixed(1)}h / 需 ${Number(tightest.need || 0)}h · ${leftText}`
  } else if (hrWaiting > 0) {
    const where = (s.hrWaitSites || []).map(asText).filter(Boolean).join(' / ')
    hrNote = `${hrWaiting} 颗工时已够，等站端确认${where ? `（${where}）` : ''}`
  } else {
    hrNote = `全站 ${hrKnown} 颗账单已结清`
  }

  // 站端把某颗标成 at_risk 时，无论欠不欠都要在最前面说一句 —— 这是唯一带「风险」语义的字段
  if (hrAtRisk > 0) hrNote = `风险 ${hrAtRisk} 颗 · ${hrNote}`

  const tone = stopped ? 'is-idle' : active ? 'is-live' : 'is-steady'
  // 徽标与标题不重复用词：标题说是「已停止」，徽标就别再写一遍
  const badge = stopped ? '不在调度' : active ? '执行中' : '稳定做种'

  return {
    title, sub, tone, badge,
    cells: [
      { key: 'count', label: '在管做种', value: String(Number(s.count || 0)), unit: '颗' },
      { key: 'size', label: '在管体积', value: sizeText.replace(/ [GT]B$/, ''), unit: sizeText.slice(-2) },
      { key: 'cum', label: '累计做种', value: String(Number(s.cumKept || 0)), unit: '颗' },
      { key: 'hr', label: hrOwed > 0 ? '欠 H&R' : '待确认 H&R', value: hrValue, unit: hrUnit, tag: '全站' },
    ],
    hrNote,
    hrAtRisk,
    nextLabel,
    nextText,
    progress,
    hasNext: leftSec !== null,
  }
})

// 阶段状态：done / running / error / idle（idle = 这一轮没跑到）。
const stageStateOf = (key) => {
  const node = (data.flowNodes || []).find(item => item.key === key)
  if (!node) return 'idle'
  const state = String(node.state || 'idle')
  if (state === 'done' || state === 'running' || state === 'error') return state
  return node.recorded ? 'done' : 'idle'
}

// 每阶段的 10px 指标。只有真跑过才给计数；没跑到 / 正在跑 / 出错一律说状态，不硬凑 0。
const stageMetrics = computed$q(() => {
  const c = runCounts.value
  const word = (key, doneText, idleText = '未执行') => {
    const state = stageStateOf(key)
    if (state === 'running') return '进行中'
    if (state === 'error') return '失败'
    if (state === 'idle') return idleText
    return doneText
  }
  return {
    entry: word('entry', '连通正常'),
    fetch: c.total ? `${c.total} 个候选` : word('fetch', '无候选'),
    wash: (c.total || c.passed) ? `保留 ${c.passed} · 拦 ${c.blocked}` : word('wash', '无候选'),
    classify: stageStateOf('classify') === 'done' ? `实删 ${c.deleted}` : word('classify', '未执行'),
    process: (c.added || c.reused || 0) > 0 ? `做种 ${c.kept}` : word('process', '无新增'),
  }
})

// 阶段耗时：后端逐阶段记录里的 ms（离开该阶段时结算）。0 = 还没结算，不显示。
function fmtStageMs(ms) {
  const value = Number(ms || 0)
  if (!(value > 0)) return ''
  if (value < 1000) return `${value}ms`
  const sec = value / 1000
  if (sec < 60) return `${sec.toFixed(1)}s`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}m${String(s).padStart(2, '0')}s`
}

// 阶段明细的行：阶段 / 本轮 / 输入 → 输出 / 结果
const stageRows = computed$q(() => {
  const c = runCounts.value
  const cells = {
    entry: { num: '', io: '站点凭据 · 连通校验 → 通过', res: '通过' },
    fetch: { num: c.total || '', io: `RSS + 浏览页 → 候选 ${c.total} 个`, res: '完成' },
    wash: { num: c.blocked || '', io: `${c.total} 候选 → 保留 ${c.passed} · 拦截 ${c.blocked}`, res: `保留 ${c.passed}` },
    classify: { num: c.deleted || '', io: `${c.passed} 保留 → 实删低效 ${c.deleted}`, res: '已执行' },
    process: { num: c.added || c.reused || '', io: `新增 ${c.added} · 复用 ${c.reused} → 做种 ${c.kept}`, res: `做种 ${c.kept}` },
  }
  // 只挑需要的字段，不 spread node —— 免得把上游多出来的对象字段带进插值点
  return (data.flowNodes || []).map(node => {
    const cell = cells[node.key] || { num: '', io: '—', res: '—' }
    const state = stageStateOf(node.key)
    // 结果列由「这一步到底跑没跑」定调：没记录就不能说完成，出错要能看出来，跑完附耗时
    let res = ''
    if (state === 'running') res = '进行中'
    else if (state === 'error') res = '中断'
    else if (state === 'idle') res = '未执行'
    else {
      const spent = fmtStageMs(node.ms)
      res = asText(cell.res) + (spent ? ` · ${spent}` : '')
    }
    return {
      key: node.key,
      state,
      label: asText(node.label),
      num: state === 'idle' ? '' : cell.num,
      io: asText(cell.io),
      res: asText(res),
    }
  })
})

// 卡片右上角：整轮耗时（唯一能拿到的时长口径）
const runDurationText = computed$q(() => {
  const d = data.detailStats || {}
  if (d.run_active) return '本轮执行中'
  if (!runCounts.value.ran) return hasStageRecords.value ? '本轮未产生候选' : '—'
  const text = formatDurationSeconds(d.last_run_duration)
  return text === '-' ? '本轮已结束' : `本轮耗时 ${text}`
})

// 明细卡副标：最近一次执行的状态落地
const runStatusText = computed$q(() => {
  const d = data.detailStats || {}
  if (d.run_active) return taskIsBrush.value ? '正在执行本轮刷流' : '正在执行本轮养护'
  if (!runCounts.value.ran) return hasStageRecords.value ? '本轮未产生候选' : '本轮未执行'
  if (d.last_run_status === 'failed') return `本轮中断${d.last_phase_detail ? ' · ' + d.last_phase_detail : ''}`
  if (d.last_run_status === 'noop') return `本轮空转${d.last_run_reason ? ' · ' + d.last_run_reason : ''}`
  return '五阶段全部通过'
})

// 说明卡右栏：只写代码里确实存在的处理规则（见文件头 ②）
const rules = computed$q(() => ([
  { tone: 'warn', text: '站点未取到候选 → 该站冷却 180 秒，冷却期内不再重复请求' },
  { tone: 'warn', text: '站点流控 / 取种超时 → 本轮放弃该站，不记死种，下轮再试' },
  { tone: 'error', text: '站点凭据（Cookie / passkey）失效 → 该站本轮让路，不重试' },
  { tone: 'ok', text: '本轮异常写入「最近错误」并显示在本页顶部，不静默吞掉' },
  { tone: 'info', text: '页面所有计数都来自最近一次运行的落库结果，不做本地推算' },
]))

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$8("VIcon");
  const _component_VAlert = _resolveComponent$8("VAlert");
  const _component_VSheet = _resolveComponent$8("VSheet");
  const _component_VBtn = _resolveComponent$8("VBtn");
  const _component_VSelect = _resolveComponent$8("VSelect");
  const _component_VChip = _resolveComponent$8("VChip");

  return (_openBlock$8(), _createElementBlock$7(_Fragment$7, null, [
    // ── 卡 1：任务此刻在干什么 ──────────────────────────────────────────
    //   跑刷流 → 五阶段流程（会动）；做种 / 停止 → 做种实况（不摆不动的空流程链）。
    //   两态共用同一张卡壳：换的是内容，不是位置，避免页面高度跳来跳去。
    _createVNode$7(_component_VSheet, {
      tag: "section",
      class: "magicflow-panel mf-diag__card app-surface-static"
    }, {
      default: _withCtx$6(() => [
        (showFlow.value)
          ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
              _createElementVNode$8("div", { class: "magicflow-flow" }, [
                _createElementVNode$8("header", _hoisted_24$1, [
                  _createElementVNode$8("div", _hoisted_25$1, [
                    _createElementVNode$8("div", _hoisted_26$1, "五阶段运行流程"),
                    _createElementVNode$8("div", _hoisted_27$1, _toDisplayString$8(stageChain.value), 1)
                  ]),
                  _createElementVNode$8("span", {
                    class: _normalizeClass$3(["magicflow-flow__tag", { 'is-live': data.detailStats.run_active, 'is-error': data.detailStats.last_run_status === 'failed' }])
                  }, [
                    _cache[2] || (_cache[2] = _createElementVNode$8("i", null, null, -1)),
                    _createTextVNode$7(" " + _toDisplayString$8(phaseText.value), 1)
                  ], 2)
                ]),
                _createElementVNode$8("ol", _hoisted_3$6, [
                  (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(data.flowNodes, (node, i) => {
                    return (_openBlock$8(), _createElementBlock$7("li", {
                      key: node.key,
                      class: _normalizeClass$3(["magicflow-flow__node", `is-${node.state}`])
                    }, [
                      // 圆点：子节点是对勾图标 / 序号，二者互斥 → 必须是**块**（自带 dynamicChildren），
                      // 否则父块 patch 时不进来、状态翻转后图标不更新；且绝不能带 TEXT flag（数组子节点
                      // 遇 patchFlag&1 会被 hostSetElementText 整体 String() 成 "[object Object]"）。
                      (_openBlock$8(), _createElementBlock$7("span", _hoisted_4$6, [
                        (node.state === 'done' || node.state === 'running')
                          ? (_openBlock$8(), _createBlock$6(_component_VIcon, {
                              key: 0,
                              icon: "mdi-check",
                              size: "17"
                            }))
                          : (node.state === 'error')
                            ? (_openBlock$8(), _createBlock$6(_component_VIcon, {
                                key: 1,
                                icon: "mdi-alert",
                                size: "17"
                              }))
                            : _createElementVNode$8("span", _hoisted_29$1, _toDisplayString$8(i + 1), 1)
                      ])),
                      _createElementVNode$8("span", _hoisted_5$6, _toDisplayString$8(asText(node.label)), 1),
                      _createElementVNode$8("span", _hoisted_28$1, _toDisplayString$8(asText(stageMetrics.value[node.key]) || '—'), 1),
                      (i < data.flowNodes.length - 1)
                        ? (_openBlock$8(), _createElementBlock$7("span", {
                            key: 0,
                            class: _normalizeClass$3(["magicflow-flow__line", { 'is-done': node.state === 'done' }])
                          }, null, 2))
                        : _createCommentVNode$7("", true)
                    ], 2))
                  }), 128))
                ]),
                (flowHint.value)
                  ? _createElementVNode$8("div", { class: "magicflow-flow__hint" }, _toDisplayString$8(flowHint.value), 1)
                  : _createCommentVNode$7("", true)
              ])
            ], 64))
          // ── 做种实况（19.12.24）──────────────────────────────────────
          //   做种不抓种、不筛种，五阶段本来就不会动。这里换成「做种这件事本身」：
          //   在管多少、占多少盘、欠不欠 H&R、下一轮维护何时来。
          //   注意：所有文本都走 _toDisplayString（子节点是字符串才安全），数组子节点不带 patchFlag。
          : (_openBlock$8(), _createElementBlock$7("div", {
              key: 1,
              class: _normalizeClass$3(["mf-seed", seedView.value.tone])
            }, [
              _createElementVNode$8("div", { class: "mf-seed__top" }, [
                _createElementVNode$8("span", { class: "mf-seed__eyebrow" }, "SEED VIEW"),
                _createElementVNode$8("span", { class: "mf-seed__badge" }, [
                  _createElementVNode$8("i", { class: "mf-seed__pulse" }),
                  _createTextVNode$7(" " + _toDisplayString$8(seedView.value.badge), 1)
                ])
              ]),
              _createElementVNode$8("div", { class: "mf-seed__title" }, _toDisplayString$8(seedView.value.title), 1),
              _createElementVNode$8("div", { class: "mf-seed__sub" }, _toDisplayString$8(seedView.value.sub), 1),
              _createElementVNode$8("div", { class: "mf-seed__grid" }, [
                (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(seedView.value.cells, (cell) => {
                  return (_openBlock$8(), _createElementBlock$7("div", {
                    key: cell.key,
                    class: "mf-seed__cell"
                  }, [
                    (cell.tag)
                      ? _createElementVNode$8("span", { class: "mf-seed__celltag" }, _toDisplayString$8(cell.tag), 1)
                      : _createCommentVNode$7("", true),
                    _createElementVNode$8("div", { class: "mf-seed__num" }, [
                      _createElementVNode$8("b", null, _toDisplayString$8(cell.value), 1),
                      (cell.unit)
                        ? _createElementVNode$8("span", null, _toDisplayString$8(cell.unit), 1)
                        : _createCommentVNode$7("", true)
                    ]),
                    _createElementVNode$8("div", { class: "mf-seed__label" }, _toDisplayString$8(cell.label), 1)
                  ]))
                }), 128))
              ]),
              (seedView.value.hrNote)
                ? _createElementVNode$8("div", { class: "mf-seed__note" }, [
                    _createElementVNode$8("i", { class: "mf-seed__notedot" }),
                    _createTextVNode$7(" " + _toDisplayString$8(seedView.value.hrNote), 1)
                  ])
                : _createCommentVNode$7("", true),
              (seedView.value.hasNext)
                ? _createElementVNode$8("div", { class: "mf-seed__next" }, [
                    _createElementVNode$8("div", { class: "mf-seed__bar" }, [
                      _createElementVNode$8("i", {
                        style: { width: (seedView.value.progress * 100).toFixed(1) + '%' }
                      })
                    ]),
                    _createElementVNode$8("div", { class: "mf-seed__nexttext" }, [
                      _createElementVNode$8("span", null, _toDisplayString$8(seedView.value.nextLabel), 1),
                      _createTextVNode$7(" · " + _toDisplayString$8(seedView.value.nextText), 1)
                    ])
                  ])
                : _createCommentVNode$7("", true)
            ], 2)),
        (data.detailStats.last_error)
          ? (_openBlock$8(), _createBlock$6(_component_VAlert, {
              key: 0,
              type: "error",
              variant: "tonal",
              density: "compact",
              class: "mt-3"
            }, {
              default: _withCtx$6(() => [
                _createTextVNode$7(_toDisplayString$8(asText(data.detailStats.last_error)), 1)
              ]),
              _: 1
            }))
          : _createCommentVNode$7("", true)
      ]),
      _: 1
    }),

    // ── 卡 2：阶段明细（表格）────────────────────────────────────────────
    //   只在跑过刷流时出现。做种 / 停止模式下这张表只能摆五行「未执行」——不提供任何信息，
    //   纯占屏（19.12.24：用户的原话是「做种只是做种而已，不筛种子」）。
    (showFlow.value)
      ? (_openBlock$8(), _createBlock$6(_component_VSheet, {
          key: 1,
          tag: "section",
          class: "magicflow-panel mf-diag__card app-surface-static mt-4"
        }, {
          default: _withCtx$6(() => [
            _createElementVNode$8("header", _hoisted_24$1, [
              _createElementVNode$8("div", _hoisted_25$1, [
                _createElementVNode$8("div", _hoisted_26$1, "阶段明细"),
                _createElementVNode$8("div", _hoisted_27$1, _toDisplayString$8(runStatusText.value), 1)
              ]),
              _createElementVNode$8("span", _hoisted_28$1, _toDisplayString$8(runDurationText.value), 1)
            ]),
            (runCounts.value.ran || hasStageRecords.value)
          ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
              _createElementVNode$8("div", _hoisted_30$1, [
                _createElementVNode$8("span", _hoisted_31$1, "阶段"),
                _createElementVNode$8("span", _hoisted_32$1, "本轮"),
                _createElementVNode$8("span", _hoisted_33$1, "输入 → 输出"),
                _createElementVNode$8("span", _hoisted_34$1, "结果")
              ]),
              _createElementVNode$8("div", _hoisted_35$1, [
                (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(stageRows.value, (row) => {
                  return (_openBlock$8(), _createElementBlock$7("div", {
                    key: row.key,
                    class: _normalizeClass$3(["mf-diag__row", `is-${row.state}`])
                  }, [
                    _createElementVNode$8("span", _hoisted_36$1),
                    _createElementVNode$8("span", _hoisted_37$1, _toDisplayString$8(asText(row.label)), 1),
                    _createElementVNode$8("span", _hoisted_38$1, _toDisplayString$8(row.num === '' ? '—' : asText(row.num)), 1),
                    _createElementVNode$8("span", _hoisted_39$1, _toDisplayString$8(asText(row.io)), 1),
                    _createElementVNode$8("span", _hoisted_40$1, _toDisplayString$8(asText(row.res)), 1)
                  ], 2))
                }), 128))
              ])
            ], 64))
          : (_openBlock$8(), _createElementBlock$7("div", _hoisted_41$0, [
              _createElementVNode$8("p", null, "本轮没有逐阶段记录，五阶段明细暂时没有数据。"),
              _createElementVNode$8("p", null, "刷流流程只在运行模式为「运行中」时才跑；「做种中 / 已停止」只维持做种。跑过一轮后，这里会逐阶段列出候选数、拦截数、结果与各阶段耗时。"),
              _createElementVNode$8("p", null, "当前做种 " + _toDisplayString$8(runCounts.value.kept) + " 个（该项来自常驻做种计数，与是否跑过流程无关）。")
            ])),
        (data.detailStats.last_run_status === 'noop' && data.detailStats.last_run_reason)
          ? (_openBlock$8(), _createBlock$6(_component_VAlert, {
              key: 1,
              type: "info",
              variant: "tonal",
              density: "compact",
              class: "mt-3"
            }, {
              default: _withCtx$6(() => [
                _createTextVNode$7(" 最近一次执行未进入候选过滤：" + _toDisplayString$8(asText(data.detailStats.last_run_reason)), 1)
              ]),
              _: 1
            }))
          : _createCommentVNode$7("", true)
          ]),
          _: 1
        }))
      : _createCommentVNode$7("", true),

    // ── 卡 3：过滤原因（线上独有真实数据）────────────────────────────────
    //   同样只在跑过刷流时出现：做种不筛种，「被规则拦截的候选分布」永远只有空态。
    (showFlow.value)
      ? (_openBlock$8(), _createBlock$6(_component_VSheet, {
          key: 3,
          tag: "section",
          class: "magicflow-panel mf-diag__card app-surface-static mt-4"
        }, {
          default: _withCtx$6(() => [
        _createElementVNode$8("header", _hoisted_24$1, [
          _createElementVNode$8("div", _hoisted_25$1, [
            _createElementVNode$8("div", _hoisted_26$1, "过滤原因"),
            _createElementVNode$8("div", _hoisted_27$1, [
              _createTextVNode$7(" 被规则拦截的候选分布 · 共抓取 " + _toDisplayString$8(asText(data.candidateRawTotal)) + " 个，通过 " + _toDisplayString$8((data.candidateData.candidates || []).length) + " ", 1),
              (data.candidateLoadedAt)
                ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
                    _createTextVNode$7(" · 统计于 " + _toDisplayString$8(_unref$3(formatDateTime)(data.candidateLoadedAt)), 1)
                  ], 64))
                : _createCommentVNode$7("", true)
            ])
          ])
        ]),
        (data.reasonEntries.length)
          ? (_openBlock$8(), _createElementBlock$7("div", _hoisted_8$5, [
              (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(data.reasonEntries, (item) => {
                return (_openBlock$8(), _createElementBlock$7("div", {
                  key: item.label,
                  class: "magicflow-reason"
                }, [
                  _createElementVNode$8("div", null, [
                    _createElementVNode$8("span", null, _toDisplayString$8(asText(item.label)), 1),
                    _createElementVNode$8("strong", null, _toDisplayString$8(asText(item.count)), 1)
                  ]),
                  _createElementVNode$8("span", _hoisted_9$5, [
                    _createElementVNode$8("i", {
                      style: _normalizeStyle$1({ width: `${(item.count / data.maxReasonCount) * 100}%` })
                    }, null, 4)
                  ])
                ]))
              }), 128))
            ]))
          : (_openBlock$8(), _createElementBlock$7("div", _hoisted_10$5, "本轮无过滤原因记录（候选全通过或列表为空）")),
        (data.detailStats.last_run_status === 'noop' && data.detailStats.last_run_reason)
          ? (_openBlock$8(), _createBlock$6(_component_VAlert, {
              key: 2,
              type: "info",
              variant: "tonal",
              density: "compact",
              class: "mt-3"
            }, {
              default: _withCtx$6(() => [
                _createTextVNode$7(" 最近一次执行未进入候选过滤：" + _toDisplayString$8(asText(data.detailStats.last_run_reason)), 1)
              ]),
              _: 1
            }))
          : _createCommentVNode$7("", true)
          ]),
          _: 1
        }))
      : _createCommentVNode$7("", true),

    // ── 卡 4：操作记录（线上独有真实数据）──────────────────────────────
    _createVNode$7(_component_VSheet, {
      tag: "section",
      class: "magicflow-panel mf-diag__card app-surface-static mt-4"
    }, {
      default: _withCtx$6(() => [
        _createElementVNode$8("header", _hoisted_11$5, [
          _createElementVNode$8("div", _hoisted_25$1, [
            _createElementVNode$8("div", _hoisted_26$1, "操作记录"),
            _createElementVNode$8("div", _hoisted_27$1, "执行 / 选种 / 删种 / 保护 / 标签 的流水（可展开明细）")
          ]),
          _createVNode$7(_component_VBtn, {
            variant: "text",
            color: "primary",
            "prepend-icon": "mdi-send-check-outline",
            onClick: _cache[0] || (_cache[0] = $event => (emit('open-pushes')))
          }, {
            default: _withCtx$6(() => [...(_cache[5] || (_cache[5] = [
              _createTextVNode$7("加种推送", -1)
            ]))]),
            _: 1
          }),
          _createVNode$7(_component_VBtn, {
            variant: "text",
            color: "primary",
            "prepend-icon": "mdi-refresh",
            onClick: _cache[1] || (_cache[1] = $event => (emit('refresh')))
          }, {
            default: _withCtx$6(() => [...(_cache[6] || (_cache[6] = [
              _createTextVNode$7("刷新", -1)
            ]))]),
            _: 1
          })
        ]),
        _createElementVNode$8("div", _hoisted_12$5, [
          _cache[8] || (_cache[8] = _createElementVNode$8("span", { class: "magicflow-ops-filter__label" }, "类型", -1)),
          _createVNode$7(_component_VSelect, {
            "model-value": __props.scope,
            items: data.opsKindItems,
            "item-title": "label",
            "item-value": "value",
            density: "compact",
            variant: "outlined",
            "hide-details": "",
            class: "magicflow-ops-filter__select",
            "onUpdate:modelValue": onScopeChange
          }, null, 8, ["model-value", "items"])
        ]),
        _createElementVNode$8("div", _hoisted_13$4, [
          (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(data.opsFiltered, (record) => {
            return (_openBlock$8(), _createElementBlock$7("article", {
              key: record.operation_id
            }, [
              _createVNode$7(_component_VIcon, {
                icon: _unref$3(operationIcon)(record.kind),
                color: _unref$3(operationColor)(record)
              }, null, 8, ["icon", "color"]),
              _createElementVNode$8("div", null, [
                _createElementVNode$8("strong", null, [
                  _createTextVNode$7(_toDisplayString$8(_unref$3(operationKindText)(record.kind)) + " ", 1),
                  _createVNode$7(_component_VChip, {
                    size: "x-small",
                    variant: "tonal",
                    color: _unref$3(operationColor)(record),
                    class: "ml-2"
                  }, {
                    default: _withCtx$6(() => [
                      _createTextVNode$7(_toDisplayString$8(_unref$3(operationStateText)(record.state)), 1)
                    ]),
                    _: 2
                  }, 1032, ["color"])
                ]),
                _createElementVNode$8("span", null, _toDisplayString$8(asText(_unref$3(operationSummary)(record))), 1),
                _createElementVNode$8("span", null, [
                  _createTextVNode$7(_toDisplayString$8(_unref$3(formatDateTime)(record.created_at)) + " · 耗时 " + _toDisplayString$8(_unref$3(operationDuration)(record)) + " ", 1),
                  (_unref$3(hasOpDetail)(record))
                    ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
                        _createTextVNode$7(" · " + _toDisplayString$8(_unref$3(opDetailItems)(record).length) + " 条明细", 1)
                      ], 64))
                    : _createCommentVNode$7("", true)
                ]),
                (record.error_message)
                  ? (_openBlock$8(), _createElementBlock$7("span", _hoisted_14$4, _toDisplayString$8(asText(record.error_message)), 1))
                  : _createCommentVNode$7("", true),
                (_unref$3(hasOpDetail)(record))
                  ? (_openBlock$8(), _createElementBlock$7("button", {
                      key: 1,
                      type: "button",
                      class: "magicflow-events__toggle",
                      onClick: $event => (emit('toggle-detail', record.operation_id))
                    }, [
                      _createTextVNode$7(_toDisplayString$8(isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细') + " ", 1),
                      _createVNode$7(_component_VIcon, {
                        icon: isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down',
                        size: "14"
                      }, null, 8, ["icon"])
                    ], 8, _hoisted_15$4))
                  : _createCommentVNode$7("", true),
                (isOpDetailOpen(record.operation_id))
                  ? (_openBlock$8(), _createElementBlock$7("ul", _hoisted_16$4, [
                      (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(_unref$3(opDetailItems)(record), (it, idx) => {
                        return (_openBlock$8(), _createElementBlock$7("li", { key: idx }, [
                          _createElementVNode$8("span", _hoisted_17$4, [
                            (_unref$3(itemSourceText)(it.source))
                              ? (_openBlock$8(), _createElementBlock$7("em", _hoisted_18$4, _toDisplayString$8(asText(_unref$3(itemSourceText)(it.source))), 1))
                              : _createCommentVNode$7("", true),
                            _createElementVNode$8("span", {
                              class: "magicflow-events__detail-title",
                              title: it.title || it.hash
                            }, _toDisplayString$8(asText(it.title) || asText(it.hash) || '—'), 9, _hoisted_19$4),
                            (it.hash)
                              ? (_openBlock$8(), _createElementBlock$7("code", _hoisted_20$4, _toDisplayString$8(String(it.hash).slice(0, 12)), 1))
                              : _createCommentVNode$7("", true)
                          ]),
                          _createElementVNode$8("span", _hoisted_21$3, [
                            (it.reason)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
                                  _createTextVNode$7(_toDisplayString$8(asText(it.reason)), 1)
                                ], 64))
                              : _createCommentVNode$7("", true),
                            (it.size_gb)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 1 }, [
                                  _createTextVNode$7(" · " + _toDisplayString$8(Number(it.size_gb).toFixed(2)) + "G", 1)
                                ], 64))
                              : _createCommentVNode$7("", true),
                            (it.seeders)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 2 }, [
                                  _createTextVNode$7(" · 做种 " + _toDisplayString$8(it.seeders), 1)
                                ], 64))
                              : _createCommentVNode$7("", true),
                            (it.tags)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 3 }, [
                                  _createTextVNode$7(" · " + _toDisplayString$8(asText(it.tags)), 1)
                                ], 64))
                              : _createCommentVNode$7("", true),
                            (it.bonus_per_hour)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 4 }, [
                                  _createTextVNode$7(" · " + _toDisplayString$8(Number(it.bonus_per_hour).toFixed(2)) + "/h", 1)
                                ], 64))
                              : _createCommentVNode$7("", true)
                          ])
                        ]))
                      }), 128))
                    ]))
                  : _createCommentVNode$7("", true)
              ])
            ]))
          }), 128)),
          (!data.opsFiltered.length)
            ? (_openBlock$8(), _createElementBlock$7("div", _hoisted_22$2, "暂无操作记录"))
            : _createCommentVNode$7("", true)
        ])
      ]),
      _: 1
    }),

    // ── 卡 5：诊断说明（两栏静态说明；文案只写可验证行为）─────────────────
    //   讲的是五阶段各管什么，因此同样只在有刷流流程时出现（19.12.24）——
    //   上面没有阶段可看时，一张解释阶段的卡只会让人找「阶段在哪儿」。
    (showFlow.value)
      ? (_openBlock$8(), _createBlock$6(_component_VSheet, {
          key: 5,
          tag: "section",
          class: "magicflow-panel mf-diag__card app-surface-static mt-4"
        }, {
          default: _withCtx$6(() => [
            _createElementVNode$8("div", _hoisted_42$0, [
          _createElementVNode$8("div", _hoisted_43$0, [
            _createElementVNode$8("div", _hoisted_44$0, "各阶段在管什么"),
            _createElementVNode$8("p", _hoisted_45$0, "入口检查 · 校验站点凭据与连通性，失败则本轮不再抓取"),
            _createElementVNode$8("p", _hoisted_45$0, "抓取候选 · RSS 与浏览页双通道取候选，免费 / 促销优先入池"),
            _createElementVNode$8("p", _hoisted_45$0, "洗池过滤 · 按体积预算、重复、H&R 风险剔除低效候选"),
            _createElementVNode$8("p", _hoisted_45$0, "魔力排序 · 按时魔期望排序，命中预算才决定删哪些低效种"),
            _createElementVNode$8("p", _hoisted_45$0, "保种入库 · 推送下载器、登记做种信息、写操作记录"),
            _createElementVNode$8("p", _hoisted_45$0, "口径说明 · 本页只统计本任务的种子，与主页全站口径分开")
          ]),
          _createElementVNode$8("div", _hoisted_43$0, [
            _createElementVNode$8("div", _hoisted_44$0, "中断与处理规则"),
            (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(rules.value, (rule) => {
              return (_openBlock$8(), _createElementBlock$7("div", {
                key: rule.text,
                class: "mf-diag__rule-row"
              }, [
                _createElementVNode$8("span", {
                  class: _normalizeClass$3(["mf-diag__rule-dot", `is-${rule.tone}`])
                }, null, 2),
                _createElementVNode$8("span", _hoisted_48$0, _toDisplayString$8(rule.text), 1)
              ]))
            }), 128))
          ])
        ])
          ]),
          _: 1
        }))
      : _createCommentVNode$7("", true)
  ], 64))
}
}
};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const JournalTab = Object.assign(_sfc_main$8, { __scopeId: 'data-v-d0146d4d' })

export default JournalTab
