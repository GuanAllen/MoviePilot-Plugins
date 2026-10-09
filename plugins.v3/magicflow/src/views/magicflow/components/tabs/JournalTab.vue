<script setup>
// MagicFlow 前端 · 运行诊断面板（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 契约见 docs/REFACTOR-FRONTEND.md §5：props `data` `scope` `task`；emits `update:scope` `refresh`。
// —— 运行诊断含：运行流程 / 过滤原因 / 操作记录（类型筛选可展开明细）。
import { computed, reactive } from 'vue'
import { KIND_ICON, KIND_TEXT, STATE_TEXT, ITEM_SOURCE_TEXT } from '../../constants'
import { formatDateTime, formatDuration, formatDurationSeconds } from '../../../../utils'

// props：data = useTaskDetail / useCandidates / useOperations 的「状态 + 派生」整体下传（含 expandedOps），只读；
//        scope = 操作记录的类型筛选（原 opsKind），双向：emit update:scope；
//        task = 当前任务（原 selectedTask），用于判定刷流 / 养护。
const props = defineProps({
  data: { type: Object, required: true },
  scope: { type: [String, Number], default: '' },
  task: { type: Object, default: null },
})
const emit = defineEmits(['update:scope', 'refresh', 'toggle-detail'])

// reactive() 解包 data 里的 ref / computed，模板沿用原 index.vue 的写法 `data.xxx`。
const data = reactive(props.data)

const taskIsBrush = computed(() => props.task?.task_type === 'brush')

function onScopeChange(value) { emit('update:scope', value) }

// —— 操作记录展示纯函数（本地实现，与 useOperations 同口径；避免把函数当 prop 传）——
function operationKindText(kind) {
  return KIND_TEXT[kind] || kind
}
function operationStateText(state) {
  return STATE_TEXT[state] || state
}
function operationIcon(kind) {
  return KIND_ICON[kind] || 'mdi-circle-small'
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
  return !!(data.expandedOps || {})[opId]
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
</script>

<template>
  <VSheet tag="section" class="magicflow-panel magicflow-flow app-surface-static">
    <header class="magicflow-panel__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">运行流程</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ data.detailStats.run_active ? (taskIsBrush ? '正在执行本轮刷流…' : '正在执行本轮养护…') : (data.detailStats.last_run_at ? `最近执行 ${formatDateTime(data.detailStats.last_run_at)}` : '尚未运行') }}
          · 翻页游标 {{ data.detailStats.page_cursor ?? 0 }}<template v-if="data.detailStats.last_phase_detail"> · {{ data.detailStats.last_phase_detail }}</template>
        </div>
      </div>
      <span class="magicflow-flow__tag" :class="{ 'is-live': data.detailStats.run_active, 'is-error': data.detailStats.last_run_status === 'failed' }">
        <i />
        {{ data.flowPhaseText }}
      </span>
    </header>
    <ol class="magicflow-flow__chain">
      <li
        v-for="(node, i) in data.flowNodes"
        :key="node.key"
        class="magicflow-flow__node"
        :class="`is-${node.state}`"
      >
        <span class="magicflow-flow__dot">
          <VIcon v-if="node.state === 'done' || node.state === 'running'" icon="mdi-check" size="16" />
          <VIcon v-else-if="node.state === 'error'" icon="mdi-alert" size="16" />
        </span>
        <span class="magicflow-flow__label">{{ node.label }}</span>
        <span v-if="i < data.flowNodes.length - 1" class="magicflow-flow__line" :class="{ 'is-done': node.state === 'done' }" />
      </li>
    </ol>
    <VAlert v-if="data.detailStats.last_error" type="error" variant="tonal" density="compact" class="mt-3">
      {{ data.detailStats.last_error }}
    </VAlert>
  </VSheet>

  <VSheet tag="section" class="magicflow-panel app-surface-static mt-4">
    <header class="magicflow-panel__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">过滤原因</div>
        <div class="text-body-2 text-medium-emphasis">
          被规则拦截的候选分布 · 共抓取 {{ data.candidateRawTotal }} 个，通过 {{ (data.candidateData.candidates || []).length }}
          <template v-if="data.candidateLoadedAt"> · 统计于 {{ formatDateTime(data.candidateLoadedAt) }}</template>
        </div>
      </div>
    </header>
    <div v-if="data.reasonEntries.length" class="magicflow-reasons">
      <div v-for="item in data.reasonEntries" :key="item.label" class="magicflow-reason">
        <div><span>{{ item.label }}</span><strong>{{ item.count }}</strong></div>
        <span class="magicflow-reason__track"><i :style="{ width: `${(item.count / data.maxReasonCount) * 100}%` }" /></span>
      </div>
    </div>
    <div v-else class="magicflow-table-empty">本轮没有记录过滤原因（候选全部通过或列表为空）</div>
    <VAlert v-if="data.detailStats.last_run_status === 'noop' && data.detailStats.last_run_reason" type="info" variant="tonal" density="compact" class="mt-3">
      最近一次执行未进入候选过滤：{{ data.detailStats.last_run_reason }}
    </VAlert>
  </VSheet>

  <VSheet tag="section" class="magicflow-panel app-surface-static mt-4">
    <header class="magicflow-panel__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">操作记录</div>
        <div class="text-body-2 text-medium-emphasis">每次执行 / 选种 / 删种 / 保护 / 标签 的流水（可展开明细）</div>
      </div>
      <VBtn variant="text" color="primary" prepend-icon="mdi-refresh" @click="emit('refresh')">刷新</VBtn>
    </header>
    <div class="magicflow-ops-filter">
      <span class="magicflow-ops-filter__label">类型</span>
      <VSelect
        :model-value="scope"
        :items="data.opsKindItems"
        item-title="label"
        item-value="value"
        density="compact"
        variant="outlined"
        hide-details
        class="magicflow-ops-filter__select"
        @update:model-value="onScopeChange"
      ></VSelect>
    </div>
    <div class="magicflow-events">
      <article v-for="record in data.opsFiltered" :key="record.operation_id">
        <VIcon :icon="operationIcon(record.kind)" :color="operationColor(record)" />
        <div>
          <strong>
            {{ operationKindText(record.kind) }}
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
      <div v-if="!data.opsFiltered.length" class="magicflow-table-empty">暂无操作记录</div>
    </div>
  </VSheet>
</template>

<style scoped>
/* P4：运行诊断面板样式。
   专属规则（.magicflow-flow* / .magicflow-reason*）已从 index.vue 摘除；
   共享规则（.magicflow-panel(__head) / .magicflow-table-empty / .magicflow-events* / .magicflow-ops-filter*）
   在 index.vue 原样保留，此处复制一份供本组件使用（父页 scoped 不穿透子组件）。 */

/* ===== 面板卡基础（共享）===== */
.magicflow-panel {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
  min-inline-size: 0;
  padding: 16px;
}

.magicflow-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

/* ===== 运行流程（专属）===== */
.magicflow-flow__chain {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}

.magicflow-flow__node {
  position: relative;
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 9px;
  min-width: 0;
  text-align: center;
}

/* 待执行：细空心灰圈，无填充、无光晕 */
.magicflow-flow__dot {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 2px solid rgba(var(--v-border-color), 0.5);
  background: transparent;
  color: transparent;
  z-index: 1;
}

.magicflow-flow__label {
  font-size: 10.5px;
  line-height: 1.2;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim));
  white-space: nowrap;
}

.magicflow-flow__node.is-done .magicflow-flow__label {
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim));
}

/* 连接线：未执行=浅灰虚线；已走过=紫色实线 */
.magicflow-flow__line {
  position: absolute;
  top: 14px;
  right: -50%;
  width: 100%;
  height: 0;
  border-top: 2px dashed rgba(var(--v-border-color), 0.5);
  z-index: 0;
}

.magicflow-flow__line.is-done {
  border-top-style: solid;
  border-top-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.35);
}

/* 已完成：紫色实心圆 + 白色对勾，无光晕 */
.magicflow-flow__node.is-done .magicflow-flow__dot {
  border-color: rgb(var(--v-theme-primary));
  background: linear-gradient(150deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
  box-shadow: 0 4px 14px rgba(var(--v-theme-primary), 0.35), inset 0 1px 0 rgba(var(--v-theme-on-primary), 0.25);
  color: rgb(var(--v-theme-on-primary));
}

/* 运行中：紫色实心圆 + 白色对勾 + 细小缓慢脉冲环 + 微弱光晕（仅当前节点） */
.magicflow-flow__node.is-running .magicflow-flow__dot {
  border-color: rgb(var(--v-theme-primary));
  background: linear-gradient(150deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
  color: rgb(var(--v-theme-on-primary));
  box-shadow: 0 0 10px rgba(var(--v-theme-primary), 0.5);
}

.magicflow-flow__node.is-running .magicflow-flow__dot::before,
.magicflow-flow__node.is-running .magicflow-flow__dot::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 50%;
  border: 1.5px solid rgba(var(--v-theme-primary), 0.85);
  animation: magicflow-halo 2.6s cubic-bezier(0.22, 0.61, 0.36, 1) infinite;
}

.magicflow-flow__node.is-running .magicflow-flow__dot::before {
  animation-delay: 1.3s;
}

.magicflow-flow__node.is-running .magicflow-flow__label {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}

/* 出错：红色实心圆 + 白色感叹号 */
.magicflow-flow__node.is-error .magicflow-flow__dot {
  border-color: rgb(var(--v-theme-error));
  background: rgb(var(--v-theme-error));
  color: rgb(var(--v-theme-on-primary));
}

/* 运行流程右上角阶段标签（预览图：阶段名 pill + 呼吸圆点） */
.magicflow-flow__tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(var(--v-theme-primary), 0.3);
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
}

.magicflow-flow__tag i {
  inline-size: 6px;
  block-size: 6px;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
  box-shadow: 0 0 8px rgb(var(--v-theme-primary));
}

.magicflow-flow__tag.is-live i {
  animation: magicflow-blink 1.6s ease-in-out infinite;
}

.magicflow-flow__tag.is-error {
  border-color: rgba(var(--v-theme-error), 0.32);
  background: rgba(var(--v-theme-error), 0.16);
  color: rgb(var(--v-theme-error));
}

.magicflow-flow__tag.is-error i {
  background: rgb(var(--v-theme-error));
  box-shadow: 0 0 8px rgb(var(--v-theme-error));
}

/* 仅运行中节点有光晕；任务结束后 running 类被移除，脉冲动画随之销毁 */
@keyframes magicflow-halo {
  0% { transform: scale(1); opacity: 0.45; }
  100% { transform: scale(1.7); opacity: 0; }
}

@keyframes magicflow-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

/* ===== 过滤原因（专属）===== */
.magicflow-reasons {
  display: flex;
  flex-direction: column;
  gap: 13px;
  max-block-size: min(30rem, 52dvh);
  margin-block-start: 18px;
  padding-inline-end: 4px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.magicflow-reason > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-block-end: 5px;
}

.magicflow-reason__track {
  display: block;
  block-size: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-reason__track i {
  display: block;
  block-size: 100%;
  border-radius: inherit;
  background: rgb(var(--v-theme-warning));
}

/* ===== 操作记录（共享，复制一份）===== */
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

/* ===== 深色磨砂主题（专属：.magicflow-flow）+ 面板卡（共享）===== */
.magicflow-page .magicflow-panel,
.magicflow-page .magicflow-flow {
  background: var(--magicflow-panel-bg) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 16px;
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(var(--v-theme-on-surface), 0.04);
}

/* ===== 预览态细分（共享副本）===== */
.magicflow-page .magicflow-reason > div {
  font-size: 11.5px;
}

.magicflow-page .magicflow-reason__track {
  block-size: 8px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.magicflow-page .magicflow-reason__track i {
  border-radius: 999px;
  background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
  box-shadow: 0 0 12px rgba(var(--v-theme-primary), 0.5);
}

/* 操作记录（预览图：图标瓦片 + 顶部细分隔线） */
.magicflow-page .magicflow-events article {
  align-items: start;
  gap: 11px;
  padding-block: 11px;
  border-top: 1px solid rgba(var(--v-border-color), 0.1);
}

.magicflow-page .magicflow-events article:first-child {
  padding-block-start: 0;
  border-top: 0;
}

.magicflow-page .magicflow-events article > .v-icon:first-child {
  inline-size: 30px;
  block-size: 30px;
  flex: 0 0 auto;
  border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.14);
}

.magicflow-page .magicflow-events article strong {
  font-size: 12.5px;
  font-weight: 600;
}

/* 操作记录 · 明细展开（手机优先：单行省略，不撑破卡片） */
.magicflow-page .magicflow-events__toggle {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-block-start: 2px;
  padding: 0;
  border: 0;
  background: none;
  color: rgb(var(--v-theme-primary));
  font-size: 0.76rem;
  font-weight: 600;
  cursor: pointer;
}

.magicflow-page .magicflow-events__detail {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}

.magicflow-page .magicflow-events__detail li {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-inline-size: 0;
  padding-block: 5px;
  border-top: 1px dashed rgba(var(--v-border-color), 0.14);
}

.magicflow-page .magicflow-events__detail li:first-child {
  border-top: 0;
}

.magicflow-page .magicflow-events__detail-line {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-inline-size: 0;
}

.magicflow-page .magicflow-events__detail-src {
  flex: 0 0 auto;
  font-style: normal;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 0 5px;
  border-radius: 5px;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.16);
}

.magicflow-page .magicflow-events__detail-title {
  min-inline-size: 0;
  flex: 1 1 auto;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), 0.86);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.magicflow-page .magicflow-events__detail-sub {
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

/* 明细里的短 hash（等宽、弱化） */
.magicflow-page .magicflow-events__detail-hash {
  flex: 0 0 auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.66rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

/* ★ 操作记录类型筛选：一行下拉，右对齐 */
.magicflow-page .magicflow-ops-filter {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin: 0 0 6px;
}

.magicflow-page .magicflow-ops-filter__label {
  font-size: 0.76rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-page .magicflow-ops-filter__select {
  inline-size: 10rem;
  flex: 0 0 auto;
}

.magicflow-page .magicflow-ops-filter__select .v-field {
  font-size: 0.78rem;
}

.magicflow-page .magicflow-ops-filter__select .v-field__input {
  min-block-size: 32px;
  padding-block: 0;
  font-size: 0.78rem;
}

/* ===== 窄屏 ===== */
@media (max-width: 699px) {
  .magicflow-panel {
    padding: 14px;
  }

  .magicflow-panel__head {
    flex-direction: column;
    align-items: flex-start;
    flex-wrap: wrap;
  }

  /* 预览图：运行流程卡头部保持标题左 / 阶段标签右（不堆叠） */
  .magicflow-flow .magicflow-panel__head {
    flex-direction: row;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }

  .magicflow-flow .magicflow-panel__head > div {
    min-inline-size: 0;
  }
}
</style>
