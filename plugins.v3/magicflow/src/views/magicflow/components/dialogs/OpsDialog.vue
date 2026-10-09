<script setup>
// MagicFlow 前端 · 操作记录弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 展示纯函数（operationKindText / operationIcon / operationColor / operationStateText /
// operationSummary / operationDuration / hasOpDetail / opDetailItems / isOpDetailOpen /
// itemSourceText / eventLevelIcon / taskLabel）本地实现，与 composables/useOperations.js 同口径
// —— 避免把函数当 prop 传（同 components/tabs/JournalTab.vue 做法）。
import { EVENT_LEVELS, KIND_ICON, KIND_TEXT, STATE_TEXT, ITEM_SOURCE_TEXT } from '../../constants'
import { formatDateTime, formatDuration, formatDurationSeconds } from '../../../../utils'

// 开关走 defineModel（Boolean）；视图 / 类型筛选 / 事件级别 是列表展示态，同样两向绑定，子不直接改父 state。
const open = defineModel({ type: Boolean, default: false })
const view = defineModel('view', { type: String, default: 'flow' })
const kind = defineModel('kind', { type: String, default: '' })
const eventLevel = defineModel('eventLevel', { type: String, default: '' })

const props = defineProps({
  scope: { type: String, default: 'all' },
  loadingAll: { type: Boolean, default: false },
  selectedTask: { type: Object, default: null },
  eventRows: { type: Array, default: () => [] },
  eventsLoading: { type: Boolean, default: false },
  opsKindItems: { type: Array, default: () => [] },
  reseedRows: { type: Array, default: () => [] },
  opsFiltered: { type: Array, default: () => [] },
  expandedOps: { type: Object, default: () => ({}) },
  tasks: { type: Array, default: () => [] },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh-all', 'refresh-task', 'toggle-detail'])

// 刷新：全局视图拉「跨任务」、任务视图拉「当前任务」（父页拿自己的 selectedTaskId）。
function onRefresh() {
  if (props.scope === 'all') emit('refresh-all')
  else emit('refresh-task')
}

// —— 操作记录展示纯函数（本地实现，与 useOperations 同口径；避免把函数当 prop 传）——
function operationKindText(k) {
  return KIND_TEXT[k] || k
}
function operationStateText(state) {
  return STATE_TEXT[state] || state
}
function operationIcon(k) {
  return KIND_ICON[k] || 'mdi-circle-small'
}
function operationColor(record) {
  if (record.state === 'failed') return 'error'
  if (record.kind === 'deletion') return 'warning'
  if (record.kind === 'tag') return 'purple'
  if (record.kind === 'run') return 'secondary'
  return 'primary'
}
function opDetailItems(record) {
  if (!record) return []
  return (record.items || []).filter((it) => String((it && it.source) || '') !== 'run')
}
function hasOpDetail(record) {
  return opDetailItems(record).length > 0
}
function isOpDetailOpen(opId) {
  return !!props.expandedOps[opId]
}
function itemSourceText(src) {
  return ITEM_SOURCE_TEXT[src] || ''
}
function operationDuration(record) {
  if (record.duration != null && Number(record.duration) > 0) return formatDurationSeconds(record.duration)
  return formatDuration(record.created_at, record.resolved_at)
}
function operationSummary(record) {
  const first = (record.items || [])[0]
  if (first && first.title) return first.title
  const count = (record.items || []).length
  return count ? `${count} 个条目` : ''
}
function eventLevelIcon(level) {
  if (level === 'error') return 'mdi-alert-octagon-outline'
  if (level === 'warning') return 'mdi-alert-outline'
  return 'mdi-information-outline'
}
function taskLabel(taskId) {
  if (!taskId) return '—'
  if (taskId === '__silent_host__') return '静默池'
  if (taskId.startsWith('silent:')) return '静默·' + taskId.slice('silent:'.length)
  const t = (props.tasks || []).find((x) => x.id === taskId)
  return t ? t.name || taskId : taskId
}
</script>

<template>
  <VDialog v-model="open" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-ops-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">操作记录</span>
        <span class="magicflow-ops-dialog__spacer" />
        <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="loadingAll" @click="onRefresh" />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>
      <div class="magicflow-ops-dialog__sub">
        <template v-if="scope === 'all'">全部任务 · 跨站点汇总 · 每次执行 / 选种 / 删种 / 保护 / 标签 的流水（最近 100 条）</template>
        <template v-else>{{ selectedTask ? (selectedTask.name || '当前任务') : '未选择任务' }} · 每次执行 / 选种 / 删种 / 保护 / 标签 的流水</template>
      </div>
      <div class="magicflow-ops-dialog__tabs">
        <VBtn size="small" :variant="view === 'flow' ? 'tonal' : 'text'" prepend-icon="mdi-format-list-bulleted" @click="view = 'flow'">全部流水</VBtn>
        <VBtn size="small" :variant="view === 'reseed' ? 'tonal' : 'text'" prepend-icon="mdi-content-duplicate" @click="view = 'reseed'">辅种流水</VBtn>
        <VBtn size="small" :variant="view === 'timeline' ? 'tonal' : 'text'" prepend-icon="mdi-timeline-clock-outline" @click="view = 'timeline'">事件流</VBtn>
      </div>
      <div class="magicflow-ops-dialog__body">
        <div v-if="view === 'timeline'" class="mf-timeline__bar">
          <span class="mf-timeline__label">级别</span>
          <VSelect
            v-model="eventLevel"
            :items="EVENT_LEVELS"
            item-title="label"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            class="mf-timeline__select"
          />
          <VSpacer />
          <span class="mf-timeline__count">{{ eventRows.length }} 条 · 最新在前</span>
        </div>
        <div v-if="view === 'timeline'" class="mf-timeline">
          <article
            v-for="row in eventRows"
            :key="row.id"
            class="mf-timeline__row"
            :class="`is-${row.level}`"
          >
            <VIcon :icon="eventLevelIcon(row.level)" size="16" class="mf-timeline__icon" />
            <div class="mf-timeline__main">
              <div class="mf-timeline__head">
                <strong>{{ row.action || row.kind }}</strong>
                <span class="mf-timeline__ts">{{ formatDateTime(row.ts) }}</span>
              </div>
              <div class="mf-timeline__meta">
                <VChip v-if="row.task_name" size="x-small" variant="tonal">{{ row.task_name }}</VChip>
                <VChip v-if="row.site_name" size="x-small" variant="text">{{ row.site_name }}</VChip>
                <VChip v-if="row.count" size="x-small" variant="text">{{ row.count }} 种</VChip>
                <span v-if="row.reason" class="mf-timeline__reason">{{ row.reason }}</span>
              </div>
              <div v-if="row.error" class="mf-timeline__error">{{ row.error }}</div>
            </div>
          </article>
          <div v-if="eventsLoading" class="magicflow-table-empty">加载中…</div>
          <div v-else-if="!eventRows.length" class="magicflow-table-empty">暂无事件</div>
        </div>
        <div v-if="view !== 'timeline'" class="magicflow-ops-filter">
          <span class="magicflow-ops-filter__label">类型</span>
          <VSelect
            v-model="kind"
            :items="opsKindItems"
            item-title="label"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            class="magicflow-ops-filter__select"
          ></VSelect>
        </div>
        <div v-if="view === 'reseed'" class="magicflow-reseed">
          <div class="magicflow-reseed__head">
            <span>时间</span><span>任务</span><span>动作</span><span>资源</span><span class="is-num">大小</span><span>阶段</span>
          </div>
          <div v-for="row in reseedRows" :key="row.key" class="magicflow-reseed__row">
            <span class="is-time">{{ formatDateTime(row.ts) }}</span>
            <span class="is-task" :title="row.task">{{ row.task }}</span>
            <span><VChip size="x-small" variant="tonal" color="primary">{{ row.action }}</VChip></span>
            <span class="is-title" :title="row.reason || row.title">{{ row.title || row.hash || '—' }}</span>
            <span class="is-num">{{ row.size_gb ? Number(row.size_gb).toFixed(2) + 'G' : '—' }}</span>
            <span class="is-stage" :class="row.state === 'failed' ? 'text-error' : ''">{{ row.stage }}</span>
          </div>
          <div v-if="!reseedRows.length" class="magicflow-table-empty">暂无辅种流水</div>
        </div>
        <div v-else-if="view === 'flow'" class="magicflow-events">
          <article v-for="record in opsFiltered" :key="record.operation_id">
            <VIcon :icon="operationIcon(record.kind)" :color="operationColor(record)" />
            <div>
              <strong>
                {{ operationKindText(record.kind) }}
                <VChip v-if="scope === 'all'" size="x-small" variant="text" class="ml-1 magicflow-ops-dialog__task">{{ taskLabel(record.task_id) }}</VChip>
                <VChip size="x-small" variant="tonal" :color="operationColor(record)" class="ml-2">{{ operationStateText(record.state) }}</VChip>
              </strong>
              <span>{{ operationSummary(record) }}</span>
              <span>
                {{ formatDateTime(record.created_at) }} ·
                耗时 {{ operationDuration(record) }}
                <template v-if="hasOpDetail(record)"> · {{ opDetailItems(record).length }} 条明细</template>
              </span>
              <span v-if="record.error_message" class="text-error">{{ record.error_message }}</span>
              <button
                v-if="hasOpDetail(record)"
                type="button"
                class="magicflow-events__toggle"
                @click="emit('toggle-detail', record.operation_id)"
              >
                {{ isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细' }}
                <VIcon :icon="isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="14" />
              </button>
              <ul v-if="isOpDetailOpen(record.operation_id)" class="magicflow-events__detail">
                <li v-for="(it, idx) in opDetailItems(record)" :key="idx">
                  <span class="magicflow-events__detail-line">
                    <em v-if="itemSourceText(it.source)" class="magicflow-events__detail-src">{{ itemSourceText(it.source) }}</em>
                    <span class="magicflow-events__detail-title" :title="it.title || it.hash">{{ it.title || it.hash || '—' }}</span>
                    <code v-if="it.hash" class="magicflow-events__detail-hash">{{ String(it.hash).slice(0, 12) }}</code>
                  </span>
                  <span class="magicflow-events__detail-sub">
                    <template v-if="it.reason">{{ it.reason }}</template>
                    <template v-if="it.size_gb"> · {{ Number(it.size_gb).toFixed(2) }}G</template>
                    <template v-if="it.seeders"> · 做种 {{ it.seeders }}</template>
                    <template v-if="it.tags"> · {{ it.tags }}</template>
                    <template v-if="it.bonus_per_hour"> · {{ Number(it.bonus_per_hour).toFixed(2) }}/h</template>
                  </span>
                </li>
              </ul>
            </div>
          </article>
          <div v-if="!opsFiltered.length" class="magicflow-table-empty">暂无操作记录</div>
        </div>
      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 操作记录弹窗：随「操作记录」弹窗自 index.vue 迁入。
     共享选择器（magicflow-dialog / settings-dialog__head·__title·__head i / table-empty /
     events* / ops-filter* / ops-dialog__spacer·__sub·__body）父页其它弹窗也在用 → 两处各留一份
     （纯复制，零改动）。VDialog 会 teleport，父 scoped 够不到子内部，故须自带。
     专属选择器（mf-timeline* / magicflow-ops-dialog / __tabs / reseed* / ops-dialog .events）
     已从 index.vue 摘除。── */

/* ===== 弹窗壳（共享）===== */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}

.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.magicflow-settings-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
}

.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
}

.magicflow-ops-dialog__spacer { flex: 1 1 auto; }

.magicflow-ops-dialog__sub { padding: 6px 18px 4px; font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }

.magicflow-ops-dialog__body { padding: 6px 18px 20px; overflow: auto; flex: 1 1 auto; min-height: 0; }

/* ===== 事件流（专属：mf-timeline）===== */
/* ★ 可观测④：事件流 */
.mf-timeline__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-block: 4px 8px;
}

.mf-timeline__label { font-size: 12px; color: rgba(var(--v-theme-on-surface), 0.6); }

.mf-timeline__select { max-inline-size: 12rem; }

.mf-timeline__count { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.5); }

.mf-timeline__row {
  display: flex;
  gap: 8px;
  padding: 7px 8px;
  border-inline-start: 3px solid transparent;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.mf-timeline__row.is-error { border-inline-start-color: rgb(var(--v-theme-error)); }

.mf-timeline__row.is-warning { border-inline-start-color: rgb(var(--v-theme-warning)); }

.mf-timeline__row.is-info { border-inline-start-color: rgb(var(--v-theme-info)); }

.mf-timeline__icon { margin-block-start: 2px; }

.mf-timeline__row.is-error .mf-timeline__icon { color: rgb(var(--v-theme-error)); }

.mf-timeline__row.is-warning .mf-timeline__icon { color: rgb(var(--v-theme-warning)); }

.mf-timeline__row.is-info .mf-timeline__icon { color: rgb(var(--v-theme-info)); }

.mf-timeline__main { flex: 1 1 auto; min-inline-size: 0; }

.mf-timeline__head { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }

.mf-timeline__ts { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.5); white-space: nowrap; }

.mf-timeline__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.mf-timeline__reason { word-break: break-word; }

.mf-timeline__error { font-size: 12px; color: rgb(var(--v-theme-error)); word-break: break-word; }

.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

.magicflow-events article > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-inline-size: 0;
}

.magicflow-events article span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.82rem;
  overflow-wrap: anywhere;
}

.magicflow-events {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-block-size: min(30rem, 52dvh);
  margin-block-start: 16px;
  padding-inline-end: 4px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.magicflow-events article {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 10px;
}

/* 明细里的短 hash（等宽、弱化） */
.magicflow-dialog .magicflow-events__detail-hash {
  flex: 0 0 auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.66rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

/* ★ 操作记录类型筛选：一行下拉，右对齐 */
.magicflow-dialog .magicflow-ops-filter {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin: 0 0 6px;
}

.magicflow-dialog .magicflow-ops-filter__label {
  font-size: 0.76rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-dialog .magicflow-ops-filter__select {
  inline-size: 10rem;
  flex: 0 0 auto;
}

.magicflow-dialog .magicflow-ops-filter__select .v-field {
  font-size: 0.78rem;
}

.magicflow-dialog .magicflow-ops-filter__select .v-field__input {
  min-block-size: 32px;
  padding-block: 0;
  font-size: 0.78rem;
}

.magicflow-dialog .magicflow-ops-dialog__tabs {
  align-items: center;
  gap: 8px;
}

/* ===== 操作记录独立页（专属）===== */
.magicflow-ops-dialog { display: flex; flex-direction: column; }

.magicflow-ops-dialog__tabs { display: flex; gap: 4px; padding: 0 14px 4px; }

/* ★ §4.1 辅种流水单表 */
.magicflow-reseed { display: flex; flex-direction: column; font-size: 12px; }

.magicflow-reseed__head, .magicflow-reseed__row { display: grid; grid-template-columns: 8.5em minmax(0, 0.8fr) 5.2em minmax(0, 2fr) 4.2em 4.2em; gap: 8px; align-items: center; padding: 5px 2px; }

.magicflow-reseed__head { font-weight: 600; opacity: var(--mf-op-dim); border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12); position: sticky; top: 0; background: rgb(var(--v-theme-surface)); z-index: 1; }

.magicflow-reseed__row { border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06); }

.magicflow-reseed__row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.magicflow-reseed .is-time { font-variant-numeric: tabular-nums; opacity: var(--mf-op-soft); }

.magicflow-reseed .is-num { text-align: right; font-variant-numeric: tabular-nums; }

.magicflow-reseed .is-stage { opacity: 0.8; }

@media (max-width: 640px) {
.magicflow-reseed { font-size: 11px; }.magicflow-reseed__head, .magicflow-reseed__row { grid-template-columns: 5.6em minmax(0, 0.9fr) 4.4em minmax(0, 1.7fr) 3.4em; gap: 6px; }.magicflow-reseed__head > span:nth-child(5),
  .magicflow-reseed__row > span:nth-child(5) { display: none; }
}

/* 操作记录 / 站点容量 弹窗：让列表撑满卡片可滚区，不再被 .magicflow-events 的 52dvh 上限截断，下方留一大片空白 */
.magicflow-ops-dialog .magicflow-events { max-block-size: none; margin-block-start: 0; padding-inline-end: 0; overflow: visible; }

@media (max-width: 959px) {
.magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}
</style>
