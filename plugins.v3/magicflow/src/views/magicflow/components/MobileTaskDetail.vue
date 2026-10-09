<script setup>
// MagicFlow 前端 · 手机端任务详情紧凑块（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（模板内层 + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不直接调父方法。
// ★ 外层容器 <div class="magicflow-mobile-detail">（及其显隐 scoped 样式）留在父页，本组件只搬「内层内容」。
// 结论 + 三个数 + 策略一行 + 次级入口。
import { computed } from 'vue'
import { formatBytes, formatDateTime } from '../../../utils'
import { MF_DETAIL_ENTRIES } from '../constants'

const props = defineProps({
  task: { type: Object, default: null },
  state: { type: Object, default: () => ({}) },
  attention: { type: Object, default: null },
  stats: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  siteAccount: { type: Object, default: () => ({}) },
  activeTab: { type: String, default: '' },
})

const emit = defineEmits(['entry', 'navigate'])

const mobileDetailCards = computed(() => {
  const t = props.task
  if (!t) return []
  const cards = [{ v: String(t.seeding_count || 0), k: '托管种' }]
  if (t.task_type === 'brush') {
    cards.push({ v: formatBytes(t.task_uploaded || 0), k: '本任务上传' })
    cards.push({ v: props.siteAccount?.ok ? formatBytes(props.siteAccount.upload || 0) : '—', k: '站点上传' })
  } else {
    cards.push({ v: t.site_bonus_ok && t.site_bonus_per_hour != null ? Number(t.site_bonus_per_hour).toFixed(2) : '—', k: '时魔 /h' })
    cards.push({ v: t.site_current_bonus != null ? Number(t.site_current_bonus).toFixed(0) : '—', k: '站点魔力' })
  }
  return cards
})

const mobileStrategyText = computed(() => {
  const t = props.task
  if (!t) return ''
  const c = props.config || {}
  const parts = [t.task_type === 'brush' ? '刷流' : '刷魔力']
  if (t.task_type === 'brush') {
    parts.push(`选种每 ${c.brush_interval ?? '—'} 分钟`)
    if (c.brush_seed_days) parts.push(`满 ${c.brush_seed_days} 天清理`)
  } else {
    parts.push(c.min_bonus_per_hour == null ? '最低魔力自动' : `最低魔力 ${Number(c.min_bonus_per_hour).toFixed(1)}/h`)
    parts.push(c.protect_perfect === false ? '完美种保护关' : '完美种保护开')
    if (t.protected_count) parts.push(`接管保护 ${t.protected_count}`)
  }
  const hr = Number(props.stats?.hr_owed ?? t.hr_owed ?? 0)
  if (hr > 0) parts.push(`H&R 欠 ${hr}`)
  return parts.join(' · ')
})

const mobileDetailHint = computed(() => {
  const d = props.stats || {}
  if (d.last_error) return `⚠ ${String(d.last_error).slice(0, 60)}`
  if (d.last_run_at) return `上次运行 ${formatDateTime(d.last_run_at)}`
  return '尚未运行'
})
</script>

<template>
  <div class="md-verdict" :class="{ 'is-warn': !!attention }">
    <span class="md-dot" :class="`is-${attention ? attention.level : state.color}`" />
    <div class="md-verdict__body">
      <div class="md-v">{{ attention ? attention.text : state.text }}<template v-if="!attention"> · 无需操作</template></div>
      <div class="md-s">{{ attention ? attention.detail : mobileDetailHint }}</div>
    </div>
    <button v-if="attention" type="button" class="md-act" @click="emit('navigate', 'diagnostics')">{{ attention.action }}</button>
  </div>
  <div class="md-cards">
    <div v-for="c in mobileDetailCards" :key="c.k" class="md-card">
      <b>{{ c.v }}</b><span>{{ c.k }}</span>
    </div>
  </div>
  <div class="md-strategy">{{ mobileStrategyText }}</div>
  <div class="md-entries">
    <button
      v-for="e in MF_DETAIL_ENTRIES"
      :key="e.key"
      type="button"
      class="md-entry"
      :class="{ 'is-active': activeTab === e.key }"
      @click="emit('entry', e)"
    >
      <VIcon :icon="e.icon" size="20" />
      <span>{{ e.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.magicflow-page .md-verdict {
  display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-radius: 16px;
  background: linear-gradient(140deg, rgba(var(--v-theme-success), 0.15), rgba(var(--v-theme-success), 0.04));
  border: 1px solid rgba(var(--v-theme-success), 0.32);
}

.magicflow-page .md-verdict.is-warn {
  background: linear-gradient(140deg, rgba(var(--v-theme-error), 0.15), rgba(var(--v-theme-error), 0.04));
  border-color: rgba(var(--v-theme-error), 0.34);
}

.magicflow-page .md-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; background: rgb(var(--v-theme-primary)); box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.8); }

.magicflow-page .md-dot.is-error { background: rgb(var(--v-theme-error)); box-shadow: 0 0 8px rgba(var(--v-theme-error), 0.7); }

.magicflow-page .md-dot.is-warning { background: rgb(var(--v-theme-warning)); box-shadow: 0 0 8px rgba(var(--v-theme-warning), 0.7); }

.magicflow-page .md-dot.is-secondary { background: rgba(var(--v-theme-on-surface), 0.45); box-shadow: none; }

.magicflow-page .md-verdict__body { min-inline-size: 0; }

.magicflow-page .md-v { font-size: 15px; font-weight: 750; color: rgb(var(--v-theme-success)); }

.magicflow-page .md-verdict.is-warn .md-v { color: rgb(var(--v-theme-error)); }

.magicflow-page .md-s { font-size: 11.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-block-start: 2px; }

.magicflow-page .md-act {
  margin-inline-start: auto; flex: 0 0 auto; font: inherit; font-size: 12px; font-weight: 650;
  padding: 7px 13px; border-radius: 10px; cursor: pointer; color: rgb(var(--v-theme-on-primary));
  background: rgba(var(--v-theme-error), 0.92); border: 1px solid rgba(var(--v-theme-error), 0.92);
}

.magicflow-page .md-cards { display: flex; gap: 9px; margin-block-start: 12px; }

.magicflow-page .md-card { flex: 1 1 0; min-inline-size: 0; background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd); border-radius: 15px; padding: 14px 12px; }

.magicflow-page .md-card b { font-size: 19px; font-weight: 800; display: block; letter-spacing: 0.2px; }

.magicflow-page .md-card span { font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); margin-block-start: 6px; display: block; }

.magicflow-page .md-strategy { margin-block-start: 10px; font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); padding: 0 4px; line-height: 1.5; }

.magicflow-page .md-entries { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin-block-start: 14px; }

.magicflow-page .md-entry {
  flex: 1 1 0; display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 6px;
  border-radius: 15px; background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); font: inherit; font-size: 12px; cursor: pointer;
}

.magicflow-page .md-entry.is-active { color: rgb(var(--v-theme-primary)); border-color: rgba(var(--v-theme-primary), 0.5); background: rgba(var(--v-theme-primary), 0.16); }
</style>
