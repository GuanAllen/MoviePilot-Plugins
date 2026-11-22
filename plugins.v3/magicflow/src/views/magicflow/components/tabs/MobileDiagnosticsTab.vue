<script setup>
// MagicFlow 前端 · 手机端运行诊断 Tab（★ 19.16.0 重写：诊断严格跟随任务运行状态三态分叉）
// 手机端（≤959px）专用：卡 1 由 runMode（本任务运行状态，任务头三态条切换后传入）直接驱动 ——
//   running       → 五阶段紫色流转条 + 过滤原因 + 「按间隔自动跑·立即执行」+ 操作流水；
//   seeding       → 做种实况卡 SEED VIEW（四格 + H&R + 下一轮维护检查）+ 操作流水；
//   stopped       → 做种实况卡（灰调「不在调度」、不算下一轮）+ 操作流水。
// ★ 19.15.0 老版病根：showFlow 用 flowNodes.recorded / run_active 这类「后端证据」判据，
//   与用户切换的 selectedTask.run_mode 完全脱钩 —— 切「运行中」诊断纹丝不动，还会出现
//   「SEED VIEW + 等待下一轮 + 执行中」这种自相矛盾的组合。本版彻底改为 runMode 单源驱动。
// 数据与事件契约（props.data / emit）不变，仅新增 runMode prop。
import { computed, reactive } from 'vue'
import { formatDateTime } from '../../../../utils'
import {
  hasOpDetail,
  itemSourceText,
  opDetailItems,
  operationColor,
  operationDuration,
  operationIcon,
  operationKindText,
  operationStateText,
  operationSummary,
} from '../../opsDisplay'

const props = defineProps({
  data: { type: Object, required: true },
  scope: { type: [String, Number], default: '' },
  task: { type: Object, default: null },
  saving: { type: Boolean, default: false },
  // ★ 本任务运行状态（running/seeding/stopped），由 index.vue 传 selectedTask.run_mode。
  //   诊断卡 1 的分叉唯一判据 —— 与任务头三态条完全同步。
  runMode: { type: String, default: 'seeding' },
})
const emit = defineEmits(['update:scope', 'refresh', 'toggle-detail', 'open-pushes', 'run'])

const data = reactive(props.data)

const taskIsBrush = computed(() => props.task?.task_type === 'brush')

function onScopeChange(value) { emit('update:scope', value) }

function isOpDetailOpen(opId) {
  return !!(data.expandedOps || {})[opId]
}

// ── 卡 1 分叉（★ 19.16.0）：唯一判据 = 任务运行状态 runMode ──
// running=五阶段流程；seeding/stopped=做种实况。切换三态立刻重渲染，不再看后端证据。
const showFlow = computed(() => props.runMode === 'running')

// 阶段标签：手机端窄屏放两字（设计稿 fhlabel=两字）。真值源=后端 run_stages 的 label，映射不到就原样。
const FLOW_LABEL_SHORT = {
  入口检查: '入口',
  抓取候选: '抓取',
  免费筛选: '筛选',
  洗池过滤: '洗池',
  魔力排序: '魔力',
  下载人数排序: '排序',
  复用·入库: '入库',
  保种入库: '入库',
}
function shortLabel(label) {
  return FLOW_LABEL_SHORT[label] || label
}

// 阶段耗时：离开该阶段结算的 ms；0 = 没结算，不显示。
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

// ── 做种实况四格 + 下一轮倒计时（逻辑与桌面 JournalTab.js seedView 同构）──
const seedView = computed(() => {
  const d = data.detailStats || {}
  const s = data.diagSeed || {}
  // ★ 19.16.0：mode 用任务状态 runMode（三态条驱动），不再读后端 detailStats.run_mode
  const mode = String(props.runMode || 'seeding')
  const active = !!d.run_active

  const title = mode === 'seeding' ? '做种中' : mode === 'stopped' ? '已停止' : mode === 'running' ? '等待下一轮' : '未运行'
  const sub = mode === 'seeding'
    ? (active
      ? '正在跑维护检查：核对种子状态与收益 —— 不抓新种、不筛种'
      : '只维持做种与收益：不抓新种、不筛种，种子池保持不变')
    : mode === 'stopped'
      ? '任务已停止：做种与调度都不在跑'
      : '本轮还没开始，到点会自动跑一遍五阶段流程'

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

  const sizeGb = Number(s.sizeGb || 0)
  const sizeText = sizeGb >= 1000 ? `${(sizeGb / 1000).toFixed(2)} TB` : `${sizeGb.toFixed(1)} GB`

  const hrKnown = Number(s.hrKnown || 0)
  const hrPending = Number(s.hrPending || 0)
  const hrOwed = Number(s.hrOwed || 0)
  const hrWaiting = Number(s.hrWaiting || 0)
  const hrAtRisk = Number(s.hrAtRisk || 0)
  const hrValue = hrKnown === 0 ? '—' : hrOwed > 0 ? String(hrOwed) : hrPending > 0 ? String(hrPending) : '0'
  const tightest = (s.hrTightest || [])[0] || null
  let hrNote = ''
  if (hrKnown === 0) {
    hrNote = '未取到全站 H&R 账本'
  } else if (hrOwed > 0 && tightest) {
    const left = tightest.left
    const leftText = left === null ? '站端未给截止' : left <= 0 ? '已超过站端截止' : `还剩 ${Math.round(left)}h`
    hrNote = `${tightest.site} · 已做种 ${Number(tightest.seeded || 0).toFixed(1)}h / 需 ${Number(tightest.need || 0)}h · ${leftText}`
  } else if (hrWaiting > 0) {
    const where = (s.hrWaitSites || []).filter(Boolean).join(' / ')
    hrNote = `${hrWaiting} 颗工时已够，等站端确认${where ? `（${where}）` : ''}`
  } else {
    hrNote = `全站 ${hrKnown} 颗账单已结清`
  }
  if (hrAtRisk > 0) hrNote = `风险 ${hrAtRisk} 颗 · ${hrNote}`

  const tone = stopped ? 'is-idle' : active ? 'is-live' : 'is-steady'
  const badge = stopped ? '不在调度' : active ? '执行中' : '稳定做种'

  return {
    title, sub, tone, badge,
    cells: [
      { key: 'count', label: '在管做种', value: String(Number(s.count || 0)), unit: '颗' },
      { key: 'size', label: '在管体积', value: sizeText.replace(/ [GT]B$/, ''), unit: sizeText.slice(-2) },
      { key: 'cum', label: '累计做种', value: String(Number(s.cumKept || 0)), unit: '颗' },
      { key: 'hr', label: hrOwed > 0 ? '欠 H&R' : '待确认 H&R', value: hrValue, unit: hrUnit(hrKnown, hrPending), tag: '全站' },
    ],
    hrNote,
    hrAtRisk,
    nextLabel,
    nextText,
    progress,
    hasNext: leftSec !== null,
    stopped,
  }
})

function hrUnit(hrKnown, hrPending) {
  return hrKnown === 0 || hrPending === 0 ? '' : '颗'
}

// 流程卡副标：最近一次执行的状态落地
const flowSub = computed(() => {
  const d = data.detailStats || {}
  if (d.run_active) return taskIsBrush.value ? '正在执行本轮刷流…' : '正在执行本轮养护…'
  return d.last_run_at ? `最近执行 ${formatDateTime(d.last_run_at)}` : '尚未运行'
})
</script>

<template>
  <div class="mob-diag">
    <!-- ═══ 卡 1-A：五阶段流转条（有阶段记录 / 正在跑）═══ -->
    <div v-if="showFlow" class="flowcard">
      <div class="flowhd">
        <div>
          <h3>运行流程</h3>
          <div class="sub">
            {{ flowSub }}<template v-if="data.detailStats.page_cursor != null"> · 翻页游标 {{ data.detailStats.page_cursor }}</template><br>
            逐阶段留痕（后端 run_stages）
          </div>
        </div>
        <span class="phasepill" :class="{ 'is-error': data.detailStats.last_run_status === 'failed' }">{{ data.flowPhaseText }}</span>
      </div>

      <div class="flowh">
        <div
          v-for="(node, i) in data.flowNodes"
          :key="node.key"
          class="fhseg"
          :class="`is-${node.state}`"
          :style="{ '--i': i }"
          :title="`${node.label}${node.ms ? ` · ${fmtStageMs(node.ms)}` : ''}`"
        >
          <span class="fhdot">
            <VIcon v-if="node.state === 'done'" icon="mdi-check" size="11" />
            <VIcon v-else-if="node.state === 'error'" icon="mdi-alert" size="11" />
            <VIcon v-else-if="node.state === 'running'" icon="mdi-dots-horizontal" size="11" />
          </span>
          <div class="fhlabel">{{ shortLabel(node.label) }}</div>
          <div class="fhms">{{ fmtStageMs(node.ms) }}</div>
        </div>
      </div>

      <!-- ★ 设计稿 ③：立即执行与「下一轮」并排，是插队的次要入口 -->
      <div class="flownext">
        <span>
          <template v-if="data.detailStats.run_active">◷ 本轮执行中 · 跑完自动进入下一轮</template>
          <template v-else>◷ 按间隔自动跑 · {{ data.detailStats.last_run_at ? '下一轮按调度' : '尚未定下轮' }}</template>
        </span>
        <span class="now" role="button" tabindex="0" @click="emit('run')" @keydown.enter="emit('run')">立即执行 ↗</span>
      </div>

      <div v-if="data.detailStats.last_error" class="hint hint--bad">{{ data.detailStats.last_error }}</div>
    </div>

    <!-- ═══ 卡 1-B：做种实况卡 SEED VIEW（没跑过刷流 / 做种中 / 已停止）═══ -->
    <div v-else class="seedview" :class="seedView.tone">
      <div class="svhd">
        <div>
          <div class="sveyebrow">SEED VIEW</div>
          <h3>{{ seedView.title }}</h3>
          <div class="sub">{{ seedView.sub }}</div>
        </div>
        <span class="svbadge" :class="{ live: !seedView.stopped }">{{ seedView.badge }}</span>
      </div>

      <div class="svcells">
        <div v-for="cell in seedView.cells" :key="cell.key" class="svcell" :class="{ hr: cell.key === 'hr' && cell.unit === '颗' }">
          <span class="k">{{ cell.label }}<em v-if="cell.tag">{{ cell.tag }}</em></span>
          <span class="v">{{ cell.value }}<small v-if="cell.unit">{{ cell.unit }}</small></span>
        </div>
      </div>

      <div v-if="seedView.hrNote" class="svhr" :class="{ risk: seedView.hrAtRisk > 0 }">{{ seedView.hrNote }}</div>

      <!-- 下一轮维护：已停止不显示（不参与调度，不给它算「下一轮」） -->
      <div v-if="seedView.hasNext" class="svnext">
        <div class="nt"><span>{{ seedView.nextLabel }}</span><b>{{ seedView.nextText }}</b></div>
        <div class="track"><i :style="{ width: `${(seedView.progress * 100).toFixed(1)}%` }"></i></div>
      </div>
      <div class="svhint">
        {{ seedView.stopped
          ? '任务已停，不参与调度 —— 不给你算「下一轮」。'
          : '做种模式不跑刷流五阶段，这里看的是做种本身：在管多少、占多少盘、欠不欠 H&R、下一轮维护何时来。' }}
      </div>
    </div>

    <!-- ═══ 卡 2：过滤原因（只在运行中的流程态出现）═══ -->
    <div v-if="showFlow" class="reasoncard">
      <div class="ph2">
        <b>过滤原因</b>
        <span>抓取 {{ data.candidateRawTotal }} · 通过 {{ (data.candidateData.candidates || []).length }}<template v-if="data.candidateLoadedAt"> · 统计于 {{ formatDateTime(data.candidateLoadedAt) }}</template></span>
      </div>
      <div v-if="data.reasonEntries.length">
        <div v-for="item in data.reasonEntries" :key="item.label" class="rsn">
          <span class="rl">{{ item.label }}</span>
          <span class="bar"><i :style="{ width: `${(item.count / (data.maxReasonCount || 1)) * 100}%` }"></i></span>
          <span class="rn">{{ item.count }}</span>
        </div>
      </div>
      <div v-else class="empty">本轮无过滤原因记录（候选全通过或列表为空）</div>
      <div v-if="data.detailStats.last_run_status === 'noop' && data.detailStats.last_run_reason" class="hint">
        最近一次执行未进入候选过滤：{{ data.detailStats.last_run_reason }}
      </div>
    </div>

    <!-- ═══ 卡 3：操作流水 ═══ -->
    <div class="secttl">
      <h3>操作流水</h3>
      <small>执行 / 选种 / 删种 / 保护 / 标签</small>
    </div>

    <div class="filterbar">
      <label class="sel">
        <span>类型：</span>
        <select :value="scope" @change="onScopeChange($event.target.value)">
          <option v-for="item in data.opsKindItems" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <VIcon icon="mdi-chevron-down" size="14" />
      </label>
      <button type="button" class="rf" :disabled="saving" @click="emit('refresh')">
        <VIcon icon="mdi-refresh" size="14" />刷新
      </button>
    </div>

    <article v-for="record in data.opsFiltered" :key="record.operation_id" class="opcard">
      <div class="r1">
        <span class="ic" :class="`is-${operationColor(record)}`">
          <VIcon :icon="operationIcon(record.kind)" size="15" />
        </span>
        <div class="tt">
          <b>{{ operationKindText(record.kind) }}</b>
          <small>
            {{ operationSummary(record) || '—' }}
            <template v-if="hasOpDetail(record)"> · {{ opDetailItems(record).length }} 条明细</template>
          </small>
        </div>
        <span class="tm">
          {{ formatDateTime(record.created_at) }}
          <em>耗时 {{ operationDuration(record) }}</em>
        </span>
      </div>
      <div v-if="record.error_message" class="err">{{ record.error_message }}</div>
      <div class="r2">
        <button v-if="hasOpDetail(record)" type="button" class="more" @click="emit('toggle-detail', record.operation_id)">
          {{ isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细' }}
          <VIcon :icon="isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="13" />
        </button>
        <span v-else class="more more--muted">无明细</span>
        <span :class="record.state === 'failed' ? 'no' : 'ok'">● {{ operationStateText(record.state) }}</span>
      </div>
      <ul v-if="isOpDetailOpen(record.operation_id)" class="detail">
        <li v-for="(it, idx) in opDetailItems(record)" :key="idx">
          <span class="dl">
            <em v-if="itemSourceText(it.source)">{{ itemSourceText(it.source) }}</em>
            <span class="dt">{{ it.title || it.hash || '—' }}</span>
          </span>
          <span class="ds">
            <template v-if="it.reason">{{ it.reason }}</template>
            <template v-if="it.size_gb"> · {{ Number(it.size_gb).toFixed(2) }}G</template>
            <template v-if="it.seeders"> · 做种 {{ it.seeders }}</template>
            <template v-if="it.tags"> · {{ it.tags }}</template>
            <template v-if="it.bonus_per_hour"> · {{ Number(it.bonus_per_hour).toFixed(2) }}/h</template>
          </span>
        </li>
      </ul>
    </article>
    <div v-if="!data.opsFiltered.length" class="empty">暂无操作记录</div>

    <div class="linkrow" role="button" tabindex="0" @click="emit('open-pushes')" @keydown.enter="emit('open-pushes')">
      <span><VIcon icon="mdi-history" size="15" />查看推送审计</span>
      <VIcon icon="mdi-chevron-right" size="15" />
    </div>
  </div>
</template>

<style scoped>
/* ══════════════════════════════════════════════════════════════════════════════
   手机端运行诊断（★ 19.15.0 视觉层按设计稿 viewDiagnostics 重写）
   · 五阶段：实心圆 + 白勾、连线贯穿、流光点沿链走（设计稿 flowh/fhseg）
   · 做种实况：左侧紫条 + 2×2 四格 + 下一轮进度（seedview）
   · 操作流水：左图标 右时间 的状态卡（opcard）
   ══════════════════════════════════════════════════════════════════════════════ */
.mob-diag {
  --line: rgba(255, 255, 255, 0.07);
  --dim: #6f7488;
  --sub: #8b90a3;
  --purple: #8b7cf6;
  --purple2: #6d5ce7;
  --green: #3ddc97;
  --red: #ff6b7a;
  --amber: #f0b64c;
  display: flex;
  flex-direction: column;
}
.mob-diag > * + * { margin-top: 10px; }

.secttl { display: flex; align-items: baseline; justify-content: space-between; margin: 4px 0 -2px; }
.secttl h3 { font-size: 13px; font-weight: 700; }
.secttl small { font-size: 10px; color: var(--dim); }

/* ── 运行流程 ── */
.flowcard {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.035);
}
.flowhd { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.flowhd h3 { font-size: 12.5px; font-weight: 650; }
.flowhd .sub { margin-top: 3px; font-size: 9.5px; line-height: 1.4; color: var(--dim); }
.phasepill {
  display: inline-flex; align-items: center; gap: 5px; flex: none;
  font-size: 10px; padding: 4px 9px; border-radius: 20px;
  background: rgba(139, 124, 246, 0.14); color: #c4b8ff;
  border: 1px solid rgba(139, 124, 246, 0.35);
  white-space: nowrap;
  animation: pillBreath 2.4s ease-in-out infinite;
}
.phasepill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.phasepill.is-error { background: rgba(255, 107, 122, 0.14); color: #ff9aa5; border-color: rgba(255, 107, 122, 0.35); animation: none; }

.flowh { display: flex; align-items: flex-start; padding: 9px 0 1px; }
.fhseg {
  flex: 1; min-width: 0; position: relative; text-align: center;
  animation: fstepIn 0.45s ease both;
  animation-delay: calc(var(--i) * 0.13s);
}
.fhseg::before {
  content: ""; position: absolute; left: 50%; top: 8px; width: 100%; height: 2px;
  background: rgba(139, 124, 246, 0.32);
}
.fhseg:last-child::before { display: none; }
.fhseg:not(:last-child)::after {
  content: ""; position: absolute; top: 6px; left: 50%; width: 6px; height: 6px; border-radius: 50%;
  background: #cbbcff; box-shadow: 0 0 9px 2px rgba(139, 124, 246, 0.8);
  animation: flowX 1.9s ease-in-out infinite;
  animation-delay: calc(var(--i) * 0.16s);
  z-index: 2; pointer-events: none;
}
.fhdot {
  position: relative; z-index: 1;
  width: 18px; height: 18px; margin: 0 auto; border-radius: 50%;
  display: grid; place-items: center;
  background: rgba(139, 124, 246, 0.2); color: #c9b6ff;
  border: 1px solid rgba(139, 124, 246, 0.62);
}
.fhseg.is-done .fhdot {
  background: linear-gradient(135deg, var(--purple), var(--purple2));
  border-color: rgba(183, 172, 255, 0.9); color: #fff;
}
.fhseg.is-running .fhdot { background: rgba(139, 124, 246, 0.42); border-color: #b7acff; color: #f1ecff; }
.fhseg.is-running .fhdot::after {
  content: ""; position: absolute; inset: -2px; border-radius: 50%;
  border: 1.5px solid rgba(139, 124, 246, 0.7);
  animation: ringPulse 2.3s ease-out infinite;
  animation-delay: calc(var(--i) * 0.28s);
}
.fhseg.is-idle .fhdot { background: rgba(255, 255, 255, 0.05); border-color: rgba(255, 255, 255, 0.14); color: #6f7488; }
.fhseg.is-error .fhdot { background: rgba(255, 107, 122, 0.24); border-color: rgba(255, 107, 122, 0.62); color: #ff9aa5; }
.fhlabel {
  margin-top: 7px; height: 14px; overflow: hidden; white-space: nowrap;
  font-size: 10px; line-height: 1.25; color: #b9b3d6;
}
.fhseg.is-idle .fhlabel { color: #7d8296; }
.fhms { margin-top: 1px; font-size: 8.5px; color: var(--dim); }

.flownext {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin-top: 11px; padding-top: 10px; border-top: 1px solid var(--line);
  font-size: 9.5px; color: var(--sub);
}
.flownext .now {
  color: #b7acff; font-weight: 600; cursor: pointer; white-space: nowrap;
  border-bottom: 1px dashed rgba(183, 172, 255, 0.5); padding-bottom: 1px;
}

/* ── 做种实况 ── */
.seedview {
  position: relative; overflow: hidden;
  padding: 12px; border-radius: 12px;
  border: 1px solid var(--line); background: rgba(255, 255, 255, 0.035);
}
.seedview::before {
  content: ""; position: absolute; inset: 0 auto 0 0; width: 3px;
  background: linear-gradient(180deg, var(--purple), rgba(139, 124, 246, 0.1));
}
.seedview.is-idle::before { background: linear-gradient(180deg, #6b7085, rgba(107, 112, 133, 0.1)); }
.svhd { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.sveyebrow { font-size: 8.5px; letter-spacing: 1.3px; font-weight: 700; color: #a99bf7; }
.svhd h3 { margin-top: 2px; font-size: 14.5px; font-weight: 700; }
.svhd .sub { margin-top: 4px; font-size: 10px; line-height: 1.5; color: var(--dim); }
.svbadge {
  display: inline-flex; align-items: center; gap: 5px; flex: none;
  font-size: 10px; padding: 4px 9px; border-radius: 20px;
  background: rgba(139, 124, 246, 0.14); color: #c4b8ff;
  border: 1px solid rgba(139, 124, 246, 0.35); white-space: nowrap;
}
.svbadge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.svbadge.live::before { animation: ringPulse 2s ease-out infinite; }
.seedview.is-idle .svbadge { background: rgba(255, 255, 255, 0.05); color: #9a9fb3; border-color: var(--line); }

.svcells { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; margin-top: 12px; }
.svcell { padding: 9px 10px; border-radius: 9px; border: 1px solid var(--line); background: rgba(255, 255, 255, 0.035); }
.svcell .k { display: flex; align-items: center; gap: 4px; font-size: 9.5px; color: var(--sub); }
.svcell .k em {
  font-style: normal; font-size: 8px; color: #a99bf7;
  background: rgba(139, 124, 246, 0.14); padding: 1px 5px; border-radius: 5px;
}
.svcell .v { display: block; margin-top: 3px; font-size: 17px; font-weight: 700; line-height: 1.1; color: #e4defb; }
.svcell .v small { margin-left: 3px; font-size: 9.5px; font-weight: 500; color: var(--dim); }
.svcell.hr .v { color: var(--amber); }
.svhr { margin-top: 9px; padding-left: 2px; font-size: 9.5px; line-height: 1.5; color: var(--sub); }
.svhr.risk { color: var(--red); }

.svnext { margin-top: 11px; padding-top: 10px; border-top: 1px solid var(--line); }
.svnext .nt { display: flex; align-items: center; justify-content: space-between; font-size: 10px; color: var(--sub); }
.svnext .nt b { font-size: 10.5px; color: #c4b8ff; }
.svnext .track { height: 5px; margin-top: 7px; border-radius: 4px; overflow: hidden; background: rgba(255, 255, 255, 0.06); }
.svnext .track i { display: block; height: 100%; border-radius: 4px; background: linear-gradient(90deg, var(--purple), var(--purple2)); }

.svhint {
  margin-top: 10px; padding: 7px 9px; font-size: 9px; line-height: 1.55; color: var(--dim);
  background: rgba(139, 124, 246, 0.06); border-radius: 8px;
  border-left: 2px solid rgba(139, 124, 246, 0.45);
}

/* ── 过滤原因 ── */
.reasoncard { padding: 12px; border-radius: 12px; border: 1px solid var(--line); background: rgba(255, 255, 255, 0.035); }
.ph2 { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; margin-bottom: 10px; }
.ph2 b { font-size: 12.5px; font-weight: 650; }
.ph2 span { font-size: 9.5px; color: var(--dim); white-space: nowrap; }
.rsn { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
.rsn:last-child { margin-bottom: 0; }
.rsn .rl { width: 70px; flex: none; font-size: 10px; color: var(--sub); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rsn .bar { flex: 1; height: 7px; border-radius: 5px; overflow: hidden; background: rgba(255, 255, 255, 0.05); }
.rsn .bar i { display: block; height: 100%; border-radius: 5px; background: linear-gradient(90deg, var(--purple), var(--purple2)); }
.rsn .rn { width: 18px; flex: none; text-align: right; font-size: 10px; font-weight: 600; color: #e8e9f0; }

/* ── 操作流水 ── */
.filterbar { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.filterbar .sel {
  flex: 1; min-width: 0; position: relative;
  display: flex; align-items: center; gap: 4px;
  padding: 9px 11px; border-radius: 9px;
  border: 1px solid var(--line); background: rgba(255, 255, 255, 0.04);
  font-size: 11px; color: #c3c7d8;
}
.filterbar .sel > span { flex: none; color: var(--sub); }
.filterbar .sel select {
  flex: 1; min-width: 0; appearance: none; border: 0; outline: 0; background: transparent;
  color: #c3c7d8; font-size: 11px; font-family: inherit;
}
.filterbar .rf {
  display: inline-flex; align-items: center; gap: 5px; flex: none;
  padding: 9px 10px; border-radius: 9px;
  border: 1px solid rgba(139, 124, 246, 0.35); background: transparent;
  color: #b7acff; font-size: 11px; font-weight: 600; white-space: nowrap;
}
.filterbar .rf:disabled { opacity: 0.55; }

.opcard { padding: 11px 12px; border-radius: 12px; border: 1px solid var(--line); background: rgba(255, 255, 255, 0.03); }
.opcard .r1 { display: flex; align-items: flex-start; gap: 8px; }
.opcard .r1 .ic {
  width: 26px; height: 26px; flex: none; border-radius: 8px;
  display: grid; place-items: center;
  background: rgba(139, 124, 246, 0.16); color: #b7acff;
}
.opcard .r1 .ic.is-error { background: rgba(255, 107, 122, 0.16); color: #ff9aa5; }
.opcard .r1 .ic.is-warning { background: rgba(240, 182, 76, 0.16); color: var(--amber); }
.opcard .r1 .ic.is-purple { background: rgba(139, 124, 246, 0.2); color: #cfc6ff; }
.opcard .r1 .ic.is-secondary { background: rgba(255, 255, 255, 0.06); color: #b9bdcf; }
.opcard .r1 .tt { flex: 1; min-width: 0; }
.opcard .r1 .tt b { display: block; font-size: 11.5px; font-weight: 650; }
.opcard .r1 .tt small { display: block; margin-top: 2px; font-size: 9.5px; line-height: 1.45; color: var(--dim); }
.opcard .r1 .tm { flex: none; text-align: right; font-size: 9px; line-height: 1.35; color: var(--dim); }
.opcard .r1 .tm em { display: block; margin-top: 1px; font-style: normal; font-size: 8.5px; color: #7d8296; }
.opcard .err {
  margin: 8px 0 0; padding: 6px 8px; border-radius: 7px; font-size: 9.5px; line-height: 1.5;
  color: #ff9aa5; background: rgba(255, 107, 122, 0.08);
}
.opcard .r2 {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin-top: 9px; padding-top: 8px; border-top: 1px solid var(--line);
}
.opcard .more {
  display: inline-flex; align-items: center; gap: 4px; padding: 0; border: 0; background: transparent;
  font-size: 10px; color: #b7acff; white-space: nowrap;
}
.opcard .more--muted { color: var(--dim); }
.opcard .ok { font-size: 10px; font-weight: 650; color: var(--green); }
.opcard .no { font-size: 10px; font-weight: 650; color: #ff9aa5; }

.opcard .detail { margin-top: 8px; padding-top: 8px; border-top: 1px dashed rgba(255, 255, 255, 0.08); list-style: none; }
.opcard .detail li { padding: 5px 0; font-size: 10px; }
.opcard .dl { display: flex; align-items: baseline; gap: 5px; }
.opcard .dl em {
  flex: none; font-style: normal; font-size: 8.5px; color: #a99bf7;
  background: rgba(139, 124, 246, 0.14); padding: 1px 5px; border-radius: 5px;
}
.opcard .dt { min-width: 0; color: #dfe1ea; word-break: break-all; }
.opcard .ds { display: block; margin-top: 2px; font-size: 9px; line-height: 1.45; color: var(--dim); }

.empty { padding: 10px 0; font-size: 10px; color: var(--dim); }

.linkrow {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 2px; padding: 10px 0 2px; border-top: 1px solid var(--line);
  color: #b7acff; font-size: 11.5px; font-weight: 600; cursor: pointer;
}
.linkrow span { display: inline-flex; align-items: center; gap: 6px; }

.hint {
  margin-top: 9px; padding: 7px 9px; border-radius: 8px; font-size: 9.5px; line-height: 1.55;
  color: #b9bdcf; background: rgba(139, 124, 246, 0.06);
  border-left: 2px solid rgba(139, 124, 246, 0.45);
}
.hint--bad { background: rgba(255, 107, 122, 0.08); border-left-color: rgba(255, 107, 122, 0.6); color: #ff9aa5; }

@keyframes fstepIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@keyframes ringPulse { 0% { transform: scale(1); opacity: 0.7; } 70% { transform: scale(2.2); opacity: 0; } 100% { transform: scale(2.2); opacity: 0; } }
@keyframes flowX { 0% { left: 50%; opacity: 0; } 18% { opacity: 1; } 82% { opacity: 1; } 100% { left: 150%; opacity: 0; } }
@keyframes pillBreath { 0%, 100% { box-shadow: 0 0 0 0 rgba(139, 124, 246, 0.35); } 50% { box-shadow: 0 0 0 5px rgba(139, 124, 246, 0); } }

@media (prefers-reduced-motion: reduce) {
  .fhseg, .fhdot::after, .fhseg:not(:last-child)::after, .phasepill, .svbadge::before { animation: none !important; }
}
</style>
