<template>
  <VDialog
    :model-value="modelValue"
    max-width="820"
    scrollable
    @update:model-value="v => emit('update:modelValue', v)"
  >
    <VCard class="mf-opt">
      <VCardTitle class="mf-opt__title">
        <VIcon icon="mdi-chart-timeline-variant-shimmer" size="20" class="me-2" />
        <span class="text-subtitle-1 font-weight-medium">组合优化器</span>
        <span class="mf-opt__tag">体积预算内，保留种子的时魔总和最大</span>
        <VSpacer />
        <VBtn icon="mdi-refresh" variant="text" size="small" :loading="loading" title="刷新" @click="emit('refresh')" />
        <VBtn icon="mdi-close" variant="text" size="small" title="关闭" @click="emit('update:modelValue', false)" />
      </VCardTitle>
      <VDivider />

      <VCardText class="mf-opt__body">
        <div class="mf-opt__pick">
          <VSelect
            :model-value="taskId"
            :items="items"
            item-title="title"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="选择任务"
            class="mf-opt__sel"
            @update:model-value="v => emit('update:taskId', String(v || ''))"
          />
          <VTextField
            :model-value="budget"
            density="compact"
            variant="outlined"
            hide-details
            type="number"
            min="0"
            suffix="GB"
            placeholder="留空 = 自动"
            class="mf-opt__bud"
            @update:model-value="v => emit('update:budget', String(v ?? ''))"
          />
        </div>
        <div class="mf-opt__hint">留空＝自动取「保留 ≥95% 时魔」的最小预算；填数字＝硬上限</div>

        <VAlert v-if="!taskId" density="compact" variant="tonal" type="info" class="mt-2">
          先选一个任务，再看「预算内保谁删谁」。
        </VAlert>

        <template v-else>
          <VAlert v-if="infeasible" density="compact" variant="tonal" type="warning" class="mt-2">
            预算 {{ fmt(poolBudget, 1) }}GB < 强制保留体积 {{ fmt(mand.size_gb, 1) }}GB —— 受保护种已超预算，
            想腾空间得先动「保护」这一层（手动保留 / 认领 / H&R / 库内资产）。
          </VAlert>

          <div v-if="hasData" class="mf-opt__metrics">
            <div class="mf-opt__metric">
              <span>种池</span>
              <strong>{{ pool.count }} 个 · {{ fmt(pool.size_gb, 1) }}GB</strong>
              <em>{{ fmt(pool.bonus_per_hour, 2) }}/h</em>
            </div>
            <div class="mf-opt__metric">
              <span>强制保留</span>
              <strong>{{ mand.count }} 个 · {{ fmt(mand.size_gb, 1) }}GB</strong>
              <em>{{ fmt(mand.bonus_per_hour, 2) }}/h</em>
            </div>
            <div class="mf-opt__metric">
              <span>预算</span>
              <strong>{{ fmt(poolBudget, 1) }}GB</strong>
              <em>{{ budgetSource }}</em>
            </div>
            <div class="mf-opt__metric">
              <span>保留时魔</span>
              <strong>{{ fmt(plan.kept_bonus_per_hour, 2) }}/h</strong>
              <em :class="keptPctGood ? 'is-up' : 'is-down'">{{ fmt(plan.kept_bonus_pct, 1) }}%</em>
            </div>
          </div>

          <VAlert v-if="hasData && plan.delete_count === 0" density="compact" variant="tonal" type="success" class="mt-2">
            无待优化项：本池在预算内可整池保留{{ methodLabel ? `（${methodLabel}）` : '' }}。
          </VAlert>

          <template v-if="hasData && plan.delete_count > 0">
            <VSheet tag="section" class="mf-opt__verdict">
              <div class="mf-opt__verdict-t">
                保留 {{ plan.keep_count }} 个（{{ fmt(plan.kept_size_gb, 1) }}GB）· 删 {{ plan.delete_count }} 个
                （释放 {{ fmt(plan.freed_gb, 1) }}GB）
              </div>
              <div class="mf-opt__verdict-s">
                损失时魔 {{ fmt(plan.lost_bonus_per_hour, 3) }}/h（保留 {{ fmt(plan.kept_bonus_pct, 1) }}%）。
              </div>
            </VSheet>

            <div v-if="compareLine" class="mf-opt__cmp" :class="saved >= 0 ? 'is-good' : 'is-bad'">
              <VIcon :icon="saved >= 0 ? 'mdi-arrow-down-bold-circle-outline' : 'mdi-arrow-up-bold-circle-outline'" size="18" />
              <span>{{ compareLine }}</span>
            </div>

            <div class="mf-opt__sec">
              <div class="mf-opt__sec-t">待删清单（按体积降序，前 {{ deleteRows.length }} 条）</div>
              <div v-for="r in deleteRows" :key="r.hash" class="mf-opt__row">
                <div class="mf-opt__row-main">
                  <span class="mf-opt__row-t" :title="r.title">{{ r.title || r.hash }}</span>
                  <span class="mf-opt__row-m">{{ fmt(r.size_gb, 1) }}GB · {{ r.seeders }}人 · {{ fmt(r.age_weeks, 1) }}周</span>
                </div>
                <strong class="mf-opt__row-b">{{ fmt(r.bonus_per_hour, 3) }}/h</strong>
              </div>
              <div v-if="plan.delete_count > deleteRows.length" class="mf-opt__more">
                …还有 {{ plan.delete_count - deleteRows.length }} 条
              </div>
            </div>
          </template>

          <div v-if="frontier.length > 1" class="mf-opt__sec">
            <div class="mf-opt__sec-t">效率前沿（横轴预算，纵轴保住的时魔占比）</div>
            <div class="mf-opt__fr">
              <div v-for="(f, i) in frontier" :key="i" class="mf-opt__fr-item" :title="`预算 ${fmt(f.budget_gb, 1)}GB · 删 ${f.delete_count} 个`">
                <i :style="{ height: barH(f.kept_bonus_pct) }" :class="f.delete_count === 0 ? 'is-full' : ''" />
                <em>{{ fmt(f.kept_bonus_pct, 0) }}%</em>
                <span>{{ fmt(f.budget_gb, 0) }}G</span>
              </div>
            </div>
          </div>

          <div v-if="keepRows.length" class="mf-opt__sec">
            <div class="mf-opt__sec-t">保留清单（前 {{ keepRows.length }} 条 · 含受保护种）</div>
            <div v-for="r in keepRows" :key="r.hash" class="mf-opt__row">
              <div class="mf-opt__row-main">
                <span class="mf-opt__row-t" :title="r.title">
                  <VIcon v-if="r.protected" icon="mdi-shield-check" size="13" class="me-1" color="primary" />
                  {{ r.title || r.hash }}
                </span>
                <span class="mf-opt__row-m">{{ fmt(r.size_gb, 1) }}GB · {{ r.seeders }}人 · {{ fmt(r.age_weeks, 1) }}周</span>
              </div>
              <strong class="mf-opt__row-b">{{ fmt(r.bonus_per_hour, 3) }}/h</strong>
            </div>
          </div>

          <div v-if="note" class="mf-opt__note">{{ note }}</div>
        </template>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  taskId: { type: String, default: '' },
  budget: { type: String, default: '' },
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  items: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'update:taskId', 'update:budget', 'refresh'])

const MAX_ROWS = 20

function fmt(v, digits = 0) {
  const n = Number(v || 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

const hasData = computed(() => !!(props.data && props.data.plan))
const method = computed(() => (props.data && props.data.method) || '')
const methodLabel = computed(() => {
  const m = method.value || ''
  if (!m || m === 'empty') return m === 'empty' ? '池内无做种' : ''
  if (m.indexOf('仅受保护种') >= 0) return '全部为受保护种'
  return m
})
const note = computed(() => (props.data && props.data.compare && props.data.compare.note) || '')
const infeasible = computed(() => !!(props.data && props.data.infeasible))
const poolBudget = computed(() => Number((props.data && props.data.budget_gb) || 0))
const budgetSource = computed(() => {
  const s = String((props.data && props.data.budget_source) || '')
  if (s.indexOf('auto') === 0) return '自动（≥95% 时魔）'
  if (s === 'param') return '手动设定'
  return s
})

const pool = computed(() => (props.data && props.data.pool) || {})
const mand = computed(() => (props.data && props.data.mandatory) || {})
const plan = computed(() => (props.data && props.data.plan) || {})
const frontier = computed(() => (props.data && Array.isArray(props.data.frontier) ? props.data.frontier : []))
const compare = computed(() => (props.data && props.data.compare) || {})

const keptPctGood = computed(() => Number(plan.value.kept_bonus_pct || 0) >= 95)

const deleteRows = computed(() => {
  const rows = Array.isArray(plan.value.delete) ? plan.value.delete.slice() : []
  rows.sort((a, b) => Number(b.size_gb || 0) - Number(a.size_gb || 0))
  return rows.slice(0, MAX_ROWS)
})

const keepRows = computed(() => {
  const rows = Array.isArray(plan.value.keep) ? plan.value.keep.slice() : []
  rows.sort((a, b) => Number(b.bonus_per_hour || 0) - Number(a.bonus_per_hour || 0))
  return rows.slice(0, MAX_ROWS)
})

const saved = computed(() => Number((compare.value && compare.value.saved_bonus_per_hour) || 0))

const compareLine = computed(() => {
  const c = compare.value
  if (!c || !c.threshold) return ''
  const t = c.threshold
  const o = c.optimized_at_same_freed || {}
  const diff = Number(c.saved_bonus_per_hour || 0)
  if (Math.abs(diff) < 0.0005) {
    return `同等释放 ${fmt(t.freed_gb, 1)}GB：阈值法删 ${t.delete_count} 个、优化器删 ${o.delete_count} 个，时魔损失持平。`
  }
  return diff > 0
    ? `同等释放 ${fmt(t.freed_gb, 1)}GB：优化器比「逐条阈值」少损失 ${fmt(diff, 3)}/h 时魔（更省）。`
    : `同等释放 ${fmt(t.freed_gb, 1)}GB：优化器比「逐条阈值」多损失 ${fmt(-diff, 3)}/h 时魔。`
})

function barH(pct) {
  const p = Math.max(2, Math.min(100, Number(pct) || 0))
  return `${p}%`
}
</script>

<style scoped>
.mf-opt__title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-block: 12px;
}

.mf-opt__tag {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-weight: 400;
}

.mf-opt__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mf-opt__pick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mf-opt__sel { flex: 1 1 220px; min-width: 160px; }
.mf-opt__bud { flex: 0 0 150px; max-width: 180px; }

.mf-opt__hint {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  line-height: 1.5;
}

.mf-opt__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
}

.mf-opt__metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mf-opt__metric span { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); }
.mf-opt__metric strong { font-size: 14px; font-weight: 600; }
.mf-opt__metric em { font-style: normal; font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); }
.mf-opt__metric em.is-up { color: rgb(var(--v-theme-success)); }
.mf-opt__metric em.is-down { color: rgb(var(--v-theme-error)); }

.mf-opt__verdict {
  border-radius: 10px;
  padding: 10px 12px;
  border-inline-start: 3px solid rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mf-opt__verdict-t { font-size: 13px; font-weight: 600; line-height: 1.55; }
.mf-opt__verdict-s { margin-block-start: 3px; font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); }

.mf-opt__cmp {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mf-opt__cmp.is-good { color: rgb(var(--v-theme-success)); }
.mf-opt__cmp.is-bad { color: rgb(var(--v-theme-warning)); }

.mf-opt__sec { display: flex; flex-direction: column; gap: 6px; }
.mf-opt__sec-t { font-size: 12px; font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.75); }

.mf-opt__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.mf-opt__row-main { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1 1 auto; }
.mf-opt__row-t { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mf-opt__row-m { font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.55); }
.mf-opt__row-b { font-size: 12px; font-weight: 600; flex: 0 0 auto; }
.mf-opt__more { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.5); padding-inline-start: 8px; }

.mf-opt__fr { display: flex; align-items: flex-end; gap: 6px; height: 92px; padding-block-start: 4px; overflow-x: auto; }
.mf-opt__fr-item { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: 2px; min-width: 34px; height: 100%; }
.mf-opt__fr-item i { display: block; width: 16px; border-radius: 3px 3px 0 0; background: rgb(var(--v-theme-primary)); opacity: 0.7; }
.mf-opt__fr-item i.is-full { background: rgb(var(--v-theme-success)); opacity: 0.85; }
.mf-opt__fr-item em { font-style: normal; font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.7); }
.mf-opt__fr-item span { font-size: 9px; color: rgba(var(--v-theme-on-surface), 0.5); white-space: nowrap; }

.mf-opt__note { font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.45); line-height: 1.5; }

@media (max-width: 600px) {
  .mf-opt__sel { flex: 1 1 100%; }
  .mf-opt__bud { flex: 1 1 100%; max-width: none; }
  .mf-opt__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
