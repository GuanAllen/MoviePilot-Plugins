<template>
  <VDialog
    :model-value="modelValue"
    max-width="860"
    scrollable
    @update:model-value="v => emit('update:modelValue', v)"
  >
    <VCard class="mf-plan">
      <VCardTitle class="mf-plan__title">
        <VIcon icon="mdi-clipboard-check-outline" size="20" class="me-2" />
        <span class="text-subtitle-1 font-weight-medium">AI 计划审批</span>
        <span class="mf-plan__tag">AI 出计划 → 人复核 → 执行（凭据 = 计划内容哈希）</span>
        <VSpacer />
        <VBtn icon="mdi-refresh" variant="text" size="small" :loading="loading" title="重新生成计划" @click="emit('refresh')" />
        <VBtn icon="mdi-close" variant="text" size="small" title="关闭" @click="emit('update:modelValue', false)" />
      </VCardTitle>
      <VDivider />

      <VCardText class="mf-plan__body">
        <div class="mf-plan__pick">
          <VSelect
            :model-value="action"
            :items="actions"
            item-title="title"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            class="mf-plan__act"
            :menu-props="{ maxWidth: 320 }"
            @update:model-value="v => emit('update:action', String(v || 'cleanup'))"
          />
          <VSelect
            :model-value="taskId"
            :items="items"
            item-title="title"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="选择任务"
            class="mf-plan__sel"
            @update:model-value="v => emit('update:taskId', String(v || ''))"
          />
          <VTextField
            v-if="action === 'optimize'"
            :model-value="budget"
            density="compact"
            variant="outlined"
            hide-details
            type="number"
            min="0"
            suffix="GB"
            placeholder="留空 = 自动"
            class="mf-plan__bud"
            @update:model-value="v => emit('update:budget', String(v ?? ''))"
          />
        </div>
        <div class="mf-plan__hint">
          <strong>只算不删</strong>：本页只生成计划（含逐条依据链），不动下载器。
          执行默认<strong>干跑</strong>；真删要「先干跑再批准」，且必须与生成时<strong>同一条计划</strong>
          （池内一变，哈希就变，旧批准作废）。
        </div>

        <VAlert v-if="!taskId" density="compact" variant="tonal" type="info" class="mt-2">
          先选一个任务，再看 AI 出的计划。
        </VAlert>

        <template v-else>
          <VAlert v-if="loading && !hasData" density="compact" variant="tonal" type="info" class="mt-2">
            正在生成计划…
          </VAlert>

          <template v-if="hasData">
            <div class="mf-plan__metrics">
              <div class="mf-plan__metric">
                <span>计划</span>
                <strong>{{ actionLabel }}</strong>
                <em>{{ taskName || taskId }}</em>
              </div>
              <div class="mf-plan__metric">
                <span>待删</span>
                <strong>{{ count }} 条</strong>
                <em>释放 {{ fmt(freed, 1) }}GB</em>
              </div>
              <div class="mf-plan__metric">
                <span>凭据（内容哈希）</span>
                <strong class="mf-plan__pid">{{ planId || '—' }}</strong>
                <em>{{ createdAt }}</em>
              </div>
            </div>

            <VAlert
              v-for="(w, i) in warnings"
              :key="i"
              density="compact"
              variant="tonal"
              type="warning"
              class="mt-1"
            >{{ w }}</VAlert>

            <VAlert v-if="count === 0" density="compact" variant="tonal" type="success" class="mt-2">
              无待删项：本池已达标准（{{ actionLabel }}）。无需审批。
            </VAlert>

            <div v-else class="mf-plan__sec">
              <div class="mf-plan__sec-t">待删清单 + 依据链（每条：身份 → 保护 → 闸门 → 评分 → 历史 → 结论）</div>
              <VExpansionPanels variant="accordion" density="compact" class="mf-plan__exp">
                <VExpansionPanel v-for="(it, i) in rows" :key="it.hash || i">
                  <VExpansionPanelTitle>
                    <div class="mf-plan__row-t">
                      <span class="mf-plan__row-n" :title="it.title">{{ it.title || it.hash }}</span>
                      <span class="mf-plan__row-m">{{ fmt(it.size_gb, 1) }}GB · {{ fmt(it.bonus_per_hour, 3) }}/h</span>
                    </div>
                  </VExpansionPanelTitle>
                  <VExpansionPanelText>
                    <div v-if="it.reason" class="mf-plan__why">{{ it.reason }}</div>
                    <div v-for="(st, j) in (it.chain || [])" :key="j" class="mf-plan__step">
                      <span class="mf-plan__step-v" :class="stepClass(st.verdict)">{{ stepLabel(st.verdict) }}</span>
                      <div class="mf-plan__step-main">
                        <div class="mf-plan__step-r">{{ st.rule }}</div>
                        <div class="mf-plan__step-a">{{ stepArgs(st) }}</div>
                        <div class="mf-plan__step-s">真值源：{{ st.source_of_truth }}</div>
                      </div>
                    </div>
                    <div v-if="!it.chain || !it.chain.length" class="mf-plan__step-s">（无依据链）</div>
                  </VExpansionPanelText>
                </VExpansionPanel>
              </VExpansionPanels>
              <div v-if="count > rows.length" class="mf-plan__more">…还有 {{ count - rows.length }} 条（依据链已省略）</div>
            </div>

            <VDivider class="my-2" />
            <VCheckbox
              :model-value="deleteFiles"
              density="compact"
              hide-details
              color="error"
              label="同时删除文件（默认只摘种、保留文件）"
              class="mf-plan__df"
              @update:model-value="v => emit('update:deleteFiles', !!v)"
            />

            <VAlert v-if="applied && !applied.dry_run" density="compact" variant="tonal" type="success" class="mt-2">
              已执行：删 {{ applied.deleted || 0 }} 条<template v-if="applied.blocked && applied.blocked.length">，
              {{ applied.blocked.length }} 条被保护拦下</template>。
            </VAlert>
            <VAlert v-else-if="applied && applied.dry_run" density="compact" variant="tonal" type="info" class="mt-2">
              干跑结果：将删 {{ applied.would_delete || 0 }} 条（{{ applied.delete_files ? '含文件' : '只摘种' }}）· 零写入。
              核对无误后点「批准执行」。
            </VAlert>

            <div v-if="count > 0" class="mf-plan__act-bar">
              <VBtn
                variant="tonal"
                size="small"
                :loading="applying"
                @click="emit('apply', { confirm: false, deleteFiles })"
              >干跑</VBtn>
              <VBtn
                color="error"
                size="small"
                variant="flat"
                :disabled="!approvable"
                :loading="applying"
                :title="approvable ? '' : '先按当前设置干跑一次，再批准'"
                @click="emit('apply', { confirm: true, deleteFiles })"
              >批准执行</VBtn>
              <span class="mf-plan__act-hint">{{ approvable ? '已干跑核对，可批准' : '先干跑核对，再批准' }}</span>
            </div>
          </template>
        </template>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  action: { type: String, default: 'cleanup' },
  taskId: { type: String, default: '' },
  budget: { type: String, default: '' },
  deleteFiles: { type: Boolean, default: false },
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  applying: { type: Boolean, default: false },
  applied: { type: Object, default: null },
  items: { type: Array, default: () => [] },
  actions: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'update:action', 'update:taskId', 'update:budget', 'update:deleteFiles', 'refresh', 'apply'])

const MAX_ROWS = 12

function fmt(v, digits = 0) {
  const n = Number(v || 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

const hasData = computed(() => !!(props.data && props.data.plan_id))
const planId = computed(() => String((props.data && props.data.plan_id) || ''))
const rows = computed(() => {
  const list = (props.data && Array.isArray(props.data.items)) ? props.data.items : []
  return list.slice(0, MAX_ROWS)
})
const count = computed(() => Number((props.data && props.data.items && props.data.items.length) || 0))
const warnings = computed(() => (props.data && Array.isArray(props.data.warnings) ? props.data.warnings : []))
const taskName = computed(() => String((props.data && props.data.task_name) || ''))
const createdAt = computed(() => String((props.data && props.data.created_at) || ''))
const freed = computed(() => Number((props.data && props.data.totals && props.data.totals.freed_gb) || 0))
const actionLabel = computed(() => (props.action === 'optimize' ? '组合优化（体积预算）' : '清理（逐条阈值）'))

/** 批准门槛：**已对同一条计划 + 同一 delete_files 档位干跑过**。 */
const approvable = computed(() => {
  const a = props.applied
  if (!a || !a.dry_run) return false
  if (String(a.plan_id || '') !== planId.value) return false
  return !!a.delete_files === !!props.deleteFiles
})

const VERDICT_LABEL = { block: '拦', soft_block: '软保', delete_candidate: '待删', keep: '保', info: '记录', blocked: '拦', soft_protected: '软保', unknown: '待定' }
function stepLabel(v) {
  return VERDICT_LABEL[String(v || '')] || String(v || '·')
}
function stepClass(v) {
  const s = String(v || '')
  if (s === 'block' || s === 'blocked') return 'is-block'
  if (s === 'soft_block' || s === 'soft_protected') return 'is-soft'
  if (s === 'delete_candidate') return 'is-del'
  if (s === 'keep') return 'is-keep'
  return 'is-info'
}
function stepArgs(st) {
  const inp = (st && st.inputs) || {}
  const parts = []
  Object.keys(inp).forEach((k) => {
    const v = inp[k]
    if (v === null || v === undefined || typeof v === 'object') return
    parts.push(`${k}=${v}`)
  })
  return parts.slice(0, 6).join(' · ')
}
</script>

<style scoped>
.mf-plan__title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-block: 12px;
}

.mf-plan__tag {
  flex: 0 1 auto;
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-weight: 400;
}

.mf-plan__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mf-plan__pick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mf-plan__act { flex: 0 0 180px; max-width: 220px; }
/* ★ MP 会给「带 label 的输入」套一层 .app-responsive-input__container（手机端宽度只有 126px）→
   label 已去掉（改由计划卡片显示动作名）；这一条兜底，防主题再套一层把宽度压死。 */
.mf-plan__act :deep(.app-responsive-input__container) { inline-size: 100% !important; }
.mf-plan__sel { flex: 1 1 200px; min-width: 150px; }
.mf-plan__bud { flex: 0 0 140px; max-width: 180px; }

.mf-plan__hint {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  line-height: 1.6;
}

.mf-plan__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin-block-start: 4px;
}

.mf-plan__metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mf-plan__metric span { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); }
.mf-plan__metric strong { font-size: 14px; font-weight: 600; }
.mf-plan__metric em { font-style: normal; font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); }
.mf-plan__pid { font-family: ui-monospace, monospace; letter-spacing: 0.04em; }

.mf-plan__sec { display: flex; flex-direction: column; gap: 6px; margin-block-start: 4px; }
.mf-plan__sec-t { font-size: 12px; font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.75); }

.mf-plan__exp { border-radius: 8px; }
.mf-plan__row-t { display: flex; align-items: center; gap: 8px; min-width: 0; width: 100%; }
.mf-plan__row-n { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1 1 auto; }
.mf-plan__row-m { font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.55); flex: 0 0 auto; }

.mf-plan__why { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.7); margin-block-end: 6px; }

.mf-plan__step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.mf-plan__step-v {
  flex: 0 0 auto;
  min-inline-size: 34px;
  text-align: center;
  font-size: 10px;
  font-weight: 600;
  border-radius: 4px;
  padding: 1px 4px;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.mf-plan__step-v.is-block { color: rgb(var(--v-theme-error)); background: rgba(var(--v-theme-error), 0.12); }
.mf-plan__step-v.is-soft { color: rgb(var(--v-theme-warning)); background: rgba(var(--v-theme-warning), 0.12); }
.mf-plan__step-v.is-del { color: rgb(var(--v-theme-error)); background: rgba(var(--v-theme-error), 0.1); }
.mf-plan__step-v.is-keep { color: rgb(var(--v-theme-success)); background: rgba(var(--v-theme-success), 0.12); }
.mf-plan__step-v.is-info { color: rgba(var(--v-theme-on-surface), 0.7); }

.mf-plan__step-main { min-width: 0; flex: 1 1 auto; }
.mf-plan__step-r { font-size: 11px; font-weight: 600; font-family: ui-monospace, monospace; }
.mf-plan__step-a { font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.7); word-break: break-all; }
.mf-plan__step-s { font-size: 9px; color: rgba(var(--v-theme-on-surface), 0.45); }
.mf-plan__more { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.5); padding-inline-start: 8px; }

.mf-plan__df { margin-block-start: -4px; }

.mf-plan__act-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-block-start: 2px;
}

.mf-plan__act-hint { font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.5); }

@media (max-width: 600px) {
  /* ★ 手机端标题行挤不下 tag（曾把刷新/关闭按钮顶出屏幕）→ 直接收起 tag */
  .mf-plan__tag { display: none; }
  .mf-plan__act, .mf-plan__sel, .mf-plan__bud { flex: 1 1 100%; max-width: none; }
  .mf-plan__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
