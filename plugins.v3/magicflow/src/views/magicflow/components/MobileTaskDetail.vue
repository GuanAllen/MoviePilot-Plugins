<script setup>
// MagicFlow 前端 · 手机端任务详情头（★ 19.16.0 按设计稿 task-detail-design.html 整体重写）
// 结构：身份卡（头像 + 标题 + 类型 chip + 副标题 + 编辑/删除）→ 独立三态切换条 →
//       结论卡 → 「1主2辅」三卡 → 策略 chips。
// ★ 视觉对齐设计稿：三态条从「三个分离圆角按钮」改为「一个连体胶囊分段控件」；
//   任务头操作从桌面工具栏的 5 图标收敛为设计稿的「编辑 / 删除」两个文字按钮。
//   桌面工具栏 .magicflow-task-head 在手机端由 index.vue 媒体查询隐藏，本组件全权接管。
// 指标口径走 taskMetrics/currencyOf，与桌面左栏/概览磁贴同源（19.11.0 / 19.12.10）。
import { computed } from 'vue'
import { formatBytes, formatDateTime, RUN_MODES } from '../../../utils'
import { taskMetrics } from '../format'
import { currencyOf } from '../composables/useCurrency'

const props = defineProps({
  task: { type: Object, default: null },
  state: { type: Object, default: () => ({}) },
  attention: { type: Object, default: null },
  stats: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  siteAccount: { type: Object, default: () => ({}) },
  activeTab: { type: String, default: '' },
  runMode: { type: String, default: 'running' },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['navigate', 'set-run-mode', 'edit', 'delete'])

// 身份卡：站点字母徽标（取站点名首字），副标题显示站点 + 标签。
const siteInitial = computed(() => {
  const n = String(props.task?.site_name || props.task?.site_domain || '?').trim()
  return n ? n.charAt(0).toUpperCase() : '?'
})
const subtitle = computed(() => {
  const t = props.task || {}
  return `${t.site_name || t.site_domain || '未绑定站点'} · 标签「${t.brush_tag || '未设置'}」`
})

// 「1主+2辅」三卡：主卡=考核目标（刷流=本任务上传 / 刷魔力=站点时魔）。
const mobileDetailCards = computed(() => {
  const t = props.task
  if (!t) return []
  const m = taskMetrics(t)
  const cards = [{ v: String(m.seeds), k: '托管种' }]
  const cur = currencyOf(t)
  if (m.isBrush) {
    cards.push({ v: m.upload.text, k: '本任务上传' })
    cards.push({ v: props.siteAccount?.ok ? formatBytes(props.siteAccount.upload || 0) : '—', k: '站点上传' })
  } else {
    cards.push({ v: m.hourly.ok ? Number(m.hourly.value).toFixed(2) : '取数中…', k: `${cur}/时` })
    cards.push({ v: t.site_current_bonus != null ? Number(t.site_current_bonus).toFixed(0) : '—', k: `站点${cur}` })
  }
  return cards
})

// 策略 chips：on=绿 / off=灰 / type=紫 / danger=红（H&R 欠）。
const mobileStrategyChips = computed(() => {
  const t = props.task
  if (!t) return []
  const c = props.config || {}
  const chips = [{ kind: 'type', text: t.task_type === 'brush' ? '刷流' : '刷魔力' }]
  if (t.task_type === 'brush') {
    chips.push({ kind: 'plain', text: `选种每 ${c.brush_interval ?? '—'} 分钟` })
    if (c.brush_seed_days) chips.push({ kind: 'plain', text: `轮转 ${c.brush_seed_days} 天` })
  } else {
    chips.push({
      kind: c.min_bonus_per_hour == null ? 'auto' : 'plain',
      text: c.min_bonus_per_hour == null ? '最低魔力自动' : `最低魔力 ${Number(c.min_bonus_per_hour).toFixed(1)}/h`,
    })
    chips.push({
      kind: c.protect_perfect === false ? 'off' : 'on',
      text: c.protect_perfect === false ? '完美种保护关' : '完美种保护开',
    })
    if (t.protected_count) chips.push({ kind: 'on', text: `接管保护 ${t.protected_count}` })
  }
  const hr = Number(props.stats?.hr_owed ?? t.hr_owed ?? 0)
  if (hr > 0) chips.push({ kind: 'danger', text: `H&R 欠 ${hr}` })
  return chips
})

const mobileDetailHint = computed(() => {
  const d = props.stats || {}
  if (d.last_error) return `⚠ ${String(d.last_error).slice(0, 60)}`
  if (d.last_run_at) return `上次运行 ${formatDateTime(d.last_run_at)}`
  return '尚未运行'
})

// 三态段：图标按设计稿 play / check / pause（RUN_MODES 顺序即 value 顺序）。
const MODE_ICON = { running: 'mdi-play', seeding: 'mdi-check', stopped: 'mdi-pause' }
</script>

<template>
  <div class="mdetail">
    <!-- ═══ 身份卡（设计稿 .thead）═══ -->
    <div class="md-ident">
      <div class="md-ident__top">
        <div class="md-av">{{ siteInitial }}</div>
        <div class="md-ident__body">
          <h2>{{ task?.name || '未命名任务' }}</h2>
          <p>{{ subtitle }}</p>
        </div>
        <span class="md-type">{{ task?.task_type === 'brush' ? '✦ 刷流' : '✦ 刷魔力' }}</span>
      </div>
      <div v-if="!task?.builtin" class="md-ident__ops">
        <button type="button" class="md-op" @click="emit('edit')"><VIcon icon="mdi-pencil-outline" size="15" />编辑</button>
        <button type="button" class="md-op md-op--del" @click="emit('delete')"><VIcon icon="mdi-delete-outline" size="15" />删除</button>
      </div>
    </div>

    <!-- ═══ 运行状态：连体胶囊分段（设计稿 .runmode / .runseg）═══ -->
    <div class="md-runmode">
      <div class="md-runmode__k"><span>运行状态</span><b>点按即切换</b></div>
      <div class="md-runseg">
        <button
          v-for="m in RUN_MODES"
          :key="m.value"
          type="button"
          class="md-runseg__btn"
          :class="{ 'is-on': runMode === m.value, 'is-stop': m.value === 'stopped' }"
          :disabled="saving"
          @click="emit('set-run-mode', m.value)"
        >
          <VIcon :icon="MODE_ICON[m.value]" size="12" />
          <span>{{ m.text }}</span>
        </button>
      </div>
    </div>

    <!-- ═══ 结论卡 ═══ -->
    <div class="md-verdict" :class="{ 'is-warn': !!attention, 'is-idle': !attention && state.color === 'secondary' }">
      <span class="md-dot" :class="`is-${attention ? attention.level : state.color}`" />
      <div class="md-verdict__body">
        <div class="md-v">{{ attention ? attention.text : state.text }}<template v-if="!attention"> · 无需操作</template></div>
        <div class="md-s">{{ attention ? attention.detail : mobileDetailHint }}</div>
      </div>
      <button v-if="attention" type="button" class="md-act" @click="emit('navigate', 'diagnostics')">{{ attention.action }}</button>
    </div>

    <!-- ═══ 1主2辅三卡 ═══ -->
    <div class="md-cards">
      <div v-for="(c, i) in mobileDetailCards" :key="c.k" class="md-card" :class="{ 'is-main': i === 1 }">
        <b>{{ c.v }}</b><span>{{ c.k }}</span>
      </div>
    </div>

    <!-- ═══ 策略 chips ═══ -->
    <div class="md-chips">
      <span v-for="c in mobileStrategyChips" :key="c.text" class="md-chip" :class="`is-${c.kind}`">{{ c.text }}</span>
    </div>
  </div>
</template>

<style scoped>
.magicflow-page .mdetail {
  --line: rgba(var(--v-theme-on-surface), 0.07);
  --dim: #6f7488;
  --purple: #8b7cf6;
  --purple2: #6d5ce7;
  /* 19.16.40：原来按深色底调的中间色，浅色白底上只有约 2:1。
     先抽成语义变量让深色视觉零变化，浅色再用主题变量/加深色覆盖。 */
  --ink-sub: #7d8296;
  --ink-soft: #aeb3c6;
  --ink-muted: #8b90a3;
  --ink-purple: #c4bbff;
  --ink-purple-on: #d3c9ff;
  --ink-red: #ff9aa5;
  --ink-alert: rgb(255, 107, 122);
  --ink-green: rgb(61, 220, 151);
  display: flex;
  flex-direction: column;
}
html[data-glass-color-scheme="light"] .magicflow-page .mdetail {
  --dim: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  --ink-sub: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  --ink-soft: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  --ink-muted: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  --ink-purple: #5c46c9;
  --ink-purple-on: #412b9d;
  --ink-red: #b3263b;
  --ink-alert: #b3263b;
  --ink-green: #137a52;
}
.magicflow-page .mdetail > * + * { margin-top: 11px; }

/* ── 身份卡 ── */
.magicflow-page .md-ident {
  border: 1px solid var(--line);
  background: linear-gradient(140deg, rgba(var(--v-theme-on-surface), 0.045), rgba(var(--v-theme-on-surface), 0.015));
  border-radius: 16px;
  padding: 14px;
}
.magicflow-page .md-ident__top { display: flex; align-items: center; gap: 10px; }
.magicflow-page .md-av {
  width: 38px; height: 38px; border-radius: 11px; flex: 0 0 auto;
  background: linear-gradient(135deg, #f26d75, #e8464f);
  display: grid; place-items: center; font-size: 17px; font-weight: 800; color: #fff;
}
.magicflow-page .md-ident__body { flex: 1 1 auto; min-inline-size: 0; }
.magicflow-page .md-ident__body h2 { font-size: 15.5px; font-weight: 750; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-page .md-ident__body p { font-size: 10.5px; color: var(--ink-sub); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-page .md-type {
  margin-left: auto; flex: none; font-size: 10.5px; font-weight: 600; padding: 4px 9px; border-radius: 20px;
  color: var(--ink-purple); background: rgba(139,124,246, 0.18); border: 1px solid rgba(139,124,246, 0.35);
  white-space: nowrap;
}
.magicflow-page .md-ident__ops { display: flex; gap: 6px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); }
.magicflow-page .md-op {
  flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 5px;
  padding: 9px 4px; border-radius: 10px; cursor: pointer; font: inherit;
  background: rgba(var(--v-theme-on-surface), 0.045); border: 1px solid var(--line);
  color: var(--ink-soft); font-size: 11px; font-weight: 600;
}
.magicflow-page .md-op--del { color: var(--ink-red); border-color: rgba(255,107,122, 0.3); }

/* ── 三态连体胶囊 ── */
.magicflow-page .md-runmode {
  padding: 12px 14px; border-radius: 14px;
  border: 1px solid var(--line); background: rgba(var(--v-theme-on-surface), 0.025);
}
.magicflow-page .md-runmode__k { display: flex; align-items: center; justify-content: space-between; font-size: 9.5px; color: var(--dim); margin-bottom: 7px; }
.magicflow-page .md-runmode__k b { color: var(--ink-purple); font-weight: 600; }
.magicflow-page .md-runseg {
  display: flex; gap: 4px; padding: 3px; border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.035); border: 1px solid var(--line);
}
.magicflow-page .md-runseg__btn {
  flex: 1; min-inline-size: 0; display: flex; align-items: center; justify-content: center; gap: 4px;
  border: 0; background: transparent; color: var(--ink-muted); cursor: pointer; font: inherit;
  font-size: 10.5px; font-weight: 600; padding: 7px 3px; border-radius: 7px; white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}
.magicflow-page .md-runseg__btn:disabled { opacity: 0.6; cursor: default; }
.magicflow-page .md-runseg__btn.is-on {
  background: rgba(139,124,246, 0.22); color: var(--ink-purple-on);
  box-shadow: inset 0 0 0 1px rgba(139,124,246, 0.5);
}
.magicflow-page .md-runseg__btn.is-stop.is-on {
  background: rgba(255,107,122, 0.16); color: var(--ink-red);
  box-shadow: inset 0 0 0 1px rgba(255,107,122, 0.42);
}

/* ── 结论卡 ── */
.magicflow-page .md-verdict {
  display: flex; align-items: center; gap: 10px; padding: 13px 14px; border-radius: 15px;
  background: linear-gradient(140deg, rgba(61,220,151, 0.15), rgba(61,220,151, 0.04));
  border: 1px solid rgba(61,220,151, 0.32);
}
.magicflow-page .md-verdict.is-warn {
  background: linear-gradient(140deg, rgba(255,107,122, 0.15), rgba(255,107,122, 0.04));
  border-color: rgba(255,107,122, 0.34);
}
.magicflow-page .md-verdict.is-idle {
  background: linear-gradient(140deg, rgba(var(--v-theme-on-surface), 0.07), rgba(var(--v-theme-on-surface), 0.02));
  border-color: rgba(var(--v-theme-on-surface), 0.16);
}
.magicflow-page .md-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; background: rgb(139,124,246); box-shadow: 0 0 8px rgba(139,124,246, 0.8); }
.magicflow-page .md-dot.is-error { background: rgb(255,107,122); box-shadow: 0 0 8px rgba(255,107,122, 0.7); }
.magicflow-page .md-dot.is-warning { background: rgb(240,182,76); box-shadow: 0 0 8px rgba(240,182,76, 0.7); }
.magicflow-page .md-dot.is-secondary { background: rgba(var(--v-theme-on-surface), 0.45); box-shadow: none; }
.magicflow-page .md-verdict__body { min-inline-size: 0; flex: 1; }
.magicflow-page .md-v { font-size: 14px; font-weight: 750; color: var(--ink-green); }
.magicflow-page .md-verdict.is-warn .md-v { color: var(--ink-alert); }
.magicflow-page .md-verdict.is-idle .md-v { color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-page .md-s { font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-block-start: 2px; }
.magicflow-page .md-act {
  margin-inline-start: auto; flex: 0 0 auto; font: inherit; font-size: 12px; font-weight: 650;
  padding: 7px 13px; border-radius: 10px; cursor: pointer; color: rgb(255,255,255);
  background: rgba(255,107,122, 0.92); border: 1px solid rgba(255,107,122, 0.92);
}

/* ── 1主2辅三卡 ── */
.magicflow-page .md-cards { display: flex; gap: 9px; }
.magicflow-page .md-card {
  flex: 1 1 0; min-inline-size: 0; text-align: center;
  background: rgba(var(--v-theme-on-surface), 0.03); border: 1px solid var(--line); border-radius: 15px; padding: 14px 10px;
}
.magicflow-page .md-card.is-main {
  background: linear-gradient(140deg, rgba(139,124,246, 0.2), rgba(139,124,246, 0.05));
  border-color: rgba(139,124,246, 0.45); padding-top: 12px;
}
.magicflow-page .md-card b { font-size: 17px; font-weight: 800; display: block; letter-spacing: 0.2px; white-space: nowrap; }
.magicflow-page .md-card.is-main b { font-size: clamp(17px, 5.4vw, 23px); color: var(--ink-purple-on); }
.magicflow-page .md-card span { font-size: 9.5px; color: var(--ink-sub); margin-block-start: 5px; display: block; white-space: nowrap; }

/* ── 策略 chips ── */
.magicflow-page .md-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 3px; margin-bottom: 13px; }
.magicflow-page .md-chip { font-size: 10px; font-weight: 600; padding: 4px 9px; border-radius: 7px; white-space: nowrap;
  background: rgba(var(--v-theme-on-surface), 0.045); border: 1px solid var(--line); color: var(--ink-soft); }
.magicflow-page .md-chip b { color: var(--ink-purple-on); }
.magicflow-page .md-chip.is-type { color: var(--ink-purple); background: rgba(139,124,246, 0.18); border-color: rgba(139,124,246, 0.35); }
.magicflow-page .md-chip.is-on { color: var(--ink-green); background: rgba(61,220,151, 0.12); border-color: rgba(61,220,151, 0.26); }
.magicflow-page .md-chip.is-off { color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); background: rgba(var(--v-theme-on-surface), 0.06); border-color: rgba(var(--v-theme-on-surface), 0.14); }
.magicflow-page .md-chip.is-auto { color: var(--ink-purple); background: rgba(139,124,246, 0.14); border-color: rgba(139,124,246, 0.28); }
.magicflow-page .md-chip.is-danger { color: var(--ink-alert); background: rgba(255,107,122, 0.12); border-color: rgba(255,107,122, 0.28); }
.magicflow-page .md-chip.is-plain { color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); background: rgba(var(--v-theme-on-surface), 0.06); border-color: rgba(var(--v-theme-on-surface), 0.14); }
</style>
