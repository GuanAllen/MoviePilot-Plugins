<template>
  <VDialog
    :model-value="modelValue"
    max-width="780"
    scrollable
    @update:model-value="v => emit('update:modelValue', v)"
  >
    <VCard class="mf-trend">
      <VCardTitle class="mf-trend__title">
        <VIcon icon="mdi-chart-timeline-variant" size="20" class="me-2" />
        <span class="text-subtitle-1 font-weight-medium">魔力趋势与归因</span>
        <VSpacer />
        <VBtn icon="mdi-refresh" variant="text" size="small" :loading="loading" title="刷新" @click="emit('refresh')" />
        <VBtn icon="mdi-close" variant="text" size="small" title="关闭" @click="emit('update:modelValue', false)" />
      </VCardTitle>
      <VDivider />

      <VCardText class="mf-trend__body">
        <div class="mf-trend__pick">
          <VBtnToggle
            :model-value="scope"
            density="compact"
            variant="outlined"
            mandatory
            divided
            @update:model-value="v => emit('update:scope', v)"
          >
            <VBtn value="site" size="small">站点</VBtn>
            <VBtn value="task" size="small">任务</VBtn>
          </VBtnToggle>
          <VSelect
            :model-value="ident"
            :items="scopeItems"
            item-title="title"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="选择对象"
            class="mf-trend__sel"
            @update:model-value="v => emit('update:ident', String(v || ''))"
          />
          <VBtnToggle
            :model-value="hours"
            density="compact"
            variant="outlined"
            mandatory
            divided
            @update:model-value="v => emit('update:hours', Number(v))"
          >
            <VBtn v-for="w in WINDOWS" :key="w.value" :value="w.value" size="small">{{ w.title }}</VBtn>
          </VBtnToggle>
        </div>

        <VAlert v-if="!ident" density="compact" variant="tonal" type="info" class="mt-3">
          先选一个{{ scope === 'site' ? '站点' : '任务' }}，再看它的时魔走向与归因。
        </VAlert>

        <template v-else>
          <VSheet tag="section" class="mf-trend__card" :class="`is-${level}`">
            <div class="mf-trend__verdict">{{ why?.verdict || '暂无结论（采样点不够）' }}</div>
            <div v-if="deltaLine" class="mf-trend__sub">{{ deltaLine }}</div>
          </VSheet>

          <div v-if="metrics.length" class="mf-trend__metrics">
            <div v-for="m in metrics" :key="m.key" class="mf-trend__metric">
              <span class="mf-trend__metric-k">{{ m.label }}</span>
              <strong>{{ m.value }}</strong>
              <em :class="m.good ? 'is-up' : 'is-down'">{{ m.delta }}</em>
            </div>
          </div>

          <div v-if="factors.length" class="mf-trend__sec">
            <div class="mf-trend__sec-t">因子拆解（时魔变化 ≈ 各因子之和）</div>
            <div v-for="f in factors" :key="f.key" class="mf-trend__factor">
              <div class="mf-trend__factor-h">
                <span>{{ f.label }}</span>
                <strong :class="Number(f.delta) >= 0 ? 'is-up' : 'is-down'">
                  {{ Number(f.delta) >= 0 ? '+' : '' }}{{ Number(f.delta).toFixed(2) }} /h · {{ f.share }}%
                </strong>
              </div>
              <div class="mf-trend__bar">
                <i :style="{ width: Math.max(2, Number(f.share) || 0) + '%' }" :class="Number(f.delta) >= 0 ? 'is-up' : 'is-down'" />
              </div>
              <div class="mf-trend__factor-d">{{ f.detail }}</div>
            </div>
          </div>

          <div v-if="cards.length" class="mf-trend__sec">
            <div class="mf-trend__sec-t">小时趋势（最近 {{ hours }} 小时）</div>
            <div class="mf-spark-grid">
              <div v-for="c in cards" :key="c.key" class="mf-spark">
                <div class="mf-spark__head">
                  <span>{{ c.label }}</span>
                  <strong>{{ c.last }}{{ c.unit }}<em :class="c.good ? 'is-up' : 'is-down'">{{ c.delta }}</em></strong>
                </div>
                <svg class="mf-spark__svg" viewBox="0 0 100 26" preserveAspectRatio="none">
                  <path :d="c.path" fill="none" class="mf-spark__line" vector-effect="non-scaling-stroke" />
                </svg>
                <div class="mf-spark__foot">
                  <span>{{ c.count }} 点</span>
                  <span>低 {{ c.min }} · 高 {{ c.max }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="dailyBars.length" class="mf-trend__sec">
            <div class="mf-trend__sec-t">每日时魔（最近 {{ dailyBars.length }} 天，日报落盘 180 天）</div>
            <div class="mf-trend__days">
              <div v-for="d in dailyBars" :key="d.t" class="mf-trend__day" :title="d.tip">
                <i :style="{ height: d.h + '%' }" />
                <span>{{ d.label }}</span>
              </div>
            </div>
          </div>

          <div v-if="advice.length" class="mf-trend__sec">
            <div class="mf-trend__sec-t">怎么办</div>
            <ul class="mf-trend__advice">
              <li v-for="(a, i) in advice" :key="i">{{ a }}</li>
            </ul>
          </div>

          <div v-if="why?.evidence" class="mf-trend__evi">{{ why.evidence }}</div>
        </template>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  scope: { type: String, default: 'site' },
  ident: { type: String, default: '' },
  hours: { type: Number, default: 72 },
  why: { type: Object, default: null },
  daily: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  scopeItems: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'update:scope', 'update:ident', 'update:hours', 'refresh'])

const WINDOWS = [
  { title: '24h', value: 24 },
  { title: '72h', value: 72 },
  { title: '7d', value: 168 },
]

const level = computed(() => props.why?.level || 'unknown')
const factors = computed(() => (Array.isArray(props.why?.factors) ? props.why.factors : []))
const advice = computed(() => (Array.isArray(props.why?.advice) ? props.why.advice : []))

const metrics = computed(() => {
  const r = props.why?.recent || {}
  const p = props.why?.prior || {}
  if (!r || !p || !Object.keys(r).length) return []
  const mk = (label, key, unit, digits) => {
    const rv = Number(r[key] ?? 0)
    const pv = Number(p[key] ?? 0)
    const pct = pv ? ((rv - pv) / Math.abs(pv)) * 100 : 0
    return {
      key,
      label,
      value: `${rv.toFixed(digits)}${unit}`,
      delta: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`,
      good: pct >= 0,
    }
  }
  return [
    mk('时魔 /h', 'bonus', '', 2),
    mk('做种数', 'seeds', ' 个', 0),
    mk('单种魔力', 'per_seed', '', 3),
    mk('体积', 'gb', ' GB', 1),
  ]
})

const deltaLine = computed(() => {
  const d = props.why?.delta
  if (!d) return ''
  return `时魔 ${Number(d.bonus) >= 0 ? '+' : ''}${Number(d.bonus).toFixed(2)}/h（${Number(d.bonus_pct).toFixed(1)}%）· 做种数 ${Number(d.seeds) >= 0 ? '+' : ''}${Number(d.seeds).toFixed(0)} 个 · 对比窗口前后等长两段`
})

function spark(series, field) {
  const pts = (series || []).filter(p => p && p[field] !== null && p[field] !== undefined)
  if (pts.length < 2) return null
  const vs = pts.map(p => Number(p[field]) || 0)
  const min = Math.min(...vs)
  const max = Math.max(...vs)
  const span = (max - min) || 1
  const W = 100
  const H = 26
  const step = W / (vs.length - 1)
  const path = vs
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(2)},${(H - 3 - ((v - min) / span) * (H - 6)).toFixed(2)}`)
    .join(' ')
  const first = vs[0]
  const last = vs[vs.length - 1]
  const delta = first ? ((last - first) / Math.abs(first)) * 100 : 0
  return {
    path,
    min: min.toFixed(1),
    max: max.toFixed(1),
    last: last.toFixed(field === 'seeds' ? 0 : 2),
    delta: `${delta >= 0 ? '▲' : '▼'}${Math.abs(delta).toFixed(1)}%`,
    good: delta >= 0,
    count: vs.length,
  }
}

const cards = computed(() => {
  const src = props.why?.series || []
  return [
    { key: 'bonus', label: '时魔 /h', unit: '', s: spark(src, 'bonus') },
    { key: 'seeds', label: '做种数', unit: ' 个', s: spark(src, 'seeds') },
    { key: 'gb', label: '自身体积', unit: ' GB', s: spark(src, 'gb') },
    { key: 'reuse', label: '辅种体积', unit: ' GB', s: spark(src, 'reuse_gb') },
  ].filter(c => c.s).map(c => ({ ...c, ...c.s }))
})

const dailyBars = computed(() => {
  const rows = (props.daily || []).slice(-21)
  if (!rows.length) return []
  const vals = rows.map(r => Number(r.bonus) || 0)
  const max = Math.max(...vals) || 1
  return rows.map(r => {
    const d = new Date((Number(r.t) || 0) * 1000)
    const label = `${d.getMonth() + 1}/${d.getDate()}`
    return {
      t: r.t,
      h: Math.max(2, Math.round(((Number(r.bonus) || 0) / max) * 100)),
      label,
      tip: `${label}：${(Number(r.bonus) || 0).toFixed(2)}/h · 做种 ${(Number(r.seeds) || 0).toFixed(0)}`,
    }
  })
})
</script>

<style scoped>
.mf-trend__title {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-block: 12px;
}

.mf-trend__body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mf-trend__pick {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.mf-trend__sel {
  flex: 1 1 180px;
  min-width: 140px;
  max-width: 320px;
}

.mf-trend__card {
  border-radius: 10px;
  padding: 10px 12px;
  border-inline-start: 3px solid rgba(var(--v-theme-on-surface), 0.25);
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mf-trend__card.is-up { border-inline-start-color: rgb(var(--v-theme-success)); }
.mf-trend__card.is-down { border-inline-start-color: rgb(var(--v-theme-error)); }
.mf-trend__card.is-flat { border-inline-start-color: rgb(var(--v-theme-info)); }

.mf-trend__verdict {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.55;
  word-break: break-word;
}

.mf-trend__sub {
  margin-block-start: 4px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  line-height: 1.5;
}

.mf-trend__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(104px, 1fr));
  gap: 8px;
}

.mf-trend__metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mf-trend__metric-k { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); }
.mf-trend__metric strong { font-size: 15px; font-weight: 600; }
.mf-trend__metric em { font-style: normal; font-size: 11px; }
.mf-trend__metric em.is-up, .mf-trend__factor-h strong.is-up { color: rgb(var(--v-theme-success)); }
.mf-trend__metric em.is-down, .mf-trend__factor-h strong.is-down { color: rgb(var(--v-theme-error)); }

.mf-trend__sec { display: flex; flex-direction: column; gap: 8px; }
.mf-trend__sec-t { font-size: 12px; font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.75); }

.mf-trend__factor { display: flex; flex-direction: column; gap: 4px; }
.mf-trend__factor-h { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; font-size: 12px; }
.mf-trend__bar { height: 6px; border-radius: 3px; background: rgba(var(--v-theme-on-surface), 0.08); overflow: hidden; }
.mf-trend__bar i { display: block; height: 100%; border-radius: 3px; background: rgb(var(--v-theme-primary)); }
.mf-trend__bar i.is-up { background: rgb(var(--v-theme-success)); }
.mf-trend__bar i.is-down { background: rgb(var(--v-theme-error)); }
.mf-trend__factor-d { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); line-height: 1.5; }

.mf-spark-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.mf-spark { display: flex; flex-direction: column; gap: 2px; }
.mf-spark__head { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.65); }
.mf-spark__head strong { font-size: 12px; font-weight: 600; color: rgb(var(--v-theme-on-surface)); }
.mf-spark__head em { font-style: normal; font-size: 10px; margin-inline-start: 3px; }
.mf-spark__head em.is-up { color: rgb(var(--v-theme-success)); }
.mf-spark__head em.is-down { color: rgb(var(--v-theme-error)); }
.mf-spark__svg { width: 100%; height: 26px; }
.mf-spark__line { stroke: rgb(var(--v-theme-primary)); stroke-width: 1.5; }
.mf-spark__foot { display: flex; justify-content: space-between; font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.5); }

.mf-trend__days { display: flex; align-items: flex-end; gap: 3px; height: 76px; padding-block-start: 4px; overflow-x: auto; }
.mf-trend__day { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: 3px; min-width: 16px; height: 100%; }
.mf-trend__day i { display: block; width: 10px; border-radius: 2px 2px 0 0; background: rgb(var(--v-theme-primary)); opacity: 0.75; }
.mf-trend__day span { font-size: 9px; color: rgba(var(--v-theme-on-surface), 0.55); white-space: nowrap; }

.mf-trend__advice { margin: 0; padding-inline-start: 18px; font-size: 12px; line-height: 1.6; }
.mf-trend__advice li { margin-block-end: 4px; word-break: break-word; }
.mf-trend__evi { font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.45); line-height: 1.5; }

@media (max-width: 600px) {
  .mf-trend__sel { flex: 1 1 100%; max-width: none; }
  .mf-trend__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
