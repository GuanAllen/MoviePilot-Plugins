<script setup>
// MagicFlow 前端 · 主页「整体概览」
// 对应设计稿 Ardot 740112280764561 帧 1（1440×900 · 2:1）。
// 口径：**全站聚合**，不是单任务。点任务矩阵任意行 → 下钻单任务详情（emit open-task）。
//
// 设计原则（沿用项目既有约定，见 docs/DESIGN-CURRENT.md §8）：
//   - 不硬编码颜色：一律 var(--v-theme-*) / rgba(var(--v-theme-on-surface), α)，浅色/深色主题自动适配。
//   - 数据向下、事件向上；本组件不直接调 api、不改父状态。
//   - 所有数值缺数据时降级为「—」或 0，不抛错、不空白。
import { computed } from 'vue'
import { formatBonus } from '../../../utils'

const props = defineProps({
  summary: { type: Object, default: () => ({}) },
  tasks: { type: Array, default: () => [] },
  // 全站趋势原始 data：{ hours, keep, series:{ 'task:xxx':[{t,bonus,seeds,gb,reuse_gb,bonus_now}] }, names }
  trend: { type: Object, default: () => ({}) },
  health: { type: Object, default: () => ({}) },
  healthLabel: { type: String, default: '' },
  healthColor: { type: String, default: '' },
  healthBadge: { type: Number, default: 0 },
  bills: { type: Array, default: () => [] }, // H&R 账单（hrBills）
  ops: { type: Array, default: () => [] }, // 操作记录（最近 N 条）
  notifyCount: { type: Number, default: 0 },
  pages: { type: Array, default: () => [] }, // 功能中心快捷入口 [{key,label,icon,hint}]
  now: { type: Number, default: () => Date.now() },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits([
  'open-task',
  'open-ceiling',
  'open-hr',
  'open-health',
  'open-ops',
  'open-page',
  'create-task',
  'refresh',
])

// ── 全局汇总 ────────────────────────────────────────────────
const s = computed(() => props.summary || {})
const seedingCount = computed(() => Number(s.value.seeding_count || 0))
const bonusPerHour = computed(() => Number(s.value.bonus_per_hour || 0))
const currentBonus = computed(() => Number(s.value.current_bonus || 0))
const ceilingPct = computed(() => Number(s.value.ceiling_pct || 0))
const taskTotal = computed(() => Number(s.value.total_tasks || props.tasks.length || 0))
const runningCount = computed(() => Number(s.value.running_tasks || 0))
const seedingTaskCount = computed(() => Number(s.value.seeding_tasks || 0))
const stoppedCount = computed(() => Number(s.value.stopped_tasks || 0))
const activeSeeding = computed(() => Number(s.value.active_tasks || 0))

// ── 趋势：把各 task 系列按时间戳聚合成「全站」曲线 ──────────────
// 接口不返回 all: 聚合序列（只有 task:/site:），所以前端求和。
const seriesMap = computed(() => props.trend?.series || {})

const hourly = computed(() => {
  const buckets = new Map()
  for (const [key, arr] of Object.entries(seriesMap.value)) {
    if (!Array.isArray(arr) || !key.startsWith('task:')) continue
    for (const p of arr) {
      const t = Number(p?.t || 0)
      if (!t) continue
      const cur = buckets.get(t) || { t, bonus: 0, seeds: 0, bonus_now: 0 }
      cur.bonus += Number(p.bonus || 0)
      cur.seeds += Number(p.seeds || 0)
      cur.bonus_now += Number(p.bonus_now || 0)
      buckets.set(t, cur)
    }
  }
  return [...buckets.values()].sort((a, b) => a.t - b.t)
})

// 本周 = 最近 72 点；上周 = 再往前 72 点（接口 keep=168，够画对比虚线）
const thisWeek = computed(() => hourly.value.slice(-72))
const prevWeek = computed(() => (hourly.value.length > 72 ? hourly.value.slice(-144, -72) : []))

// ── sparkline（KPI 卡右侧的迷你曲线）────────────────────────
function sparkPath(points, pick, w = 170, h = 36) {
  if (!points.length) return { line: '', area: '' }
  const vals = points.map(pick).filter(v => Number.isFinite(v))
  if (!vals.length) return { line: '', area: '' }
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = max - min || 1
  const step = vals.length > 1 ? w / (vals.length - 1) : w
  const coords = vals.map((v, i) => [i * step, h - ((v - min) / span) * (h - 4) - 2])
  const line = coords.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
  const area = `${line} L${w},${h} L0,${h} Z`
  return { line, area }
}

const sparkSeeds = computed(() => sparkPath(thisWeek.value, p => Number(p.seeds || 0)))
const sparkBonus = computed(() => sparkPath(thisWeek.value, p => Number(p.bonus || 0)))
const sparkBonusNow = computed(() => sparkPath(thisWeek.value, p => Number(p.bonus_now || 0)))

// ── 全站时魔趋势图（本周实线 + 上周虚线）─────────────────────
const CHART_H = 168
const CHART_W = 900
const chart = computed(() => {
  const cur = thisWeek.value
  const prev = prevWeek.value
  const all = [...cur, ...prev].map(p => Number(p.bonus || 0)).filter(v => Number.isFinite(v))
  if (!all.length) return null
  const max = Math.max(...all, 1)
  const top = Math.ceil(max / 4) * 4 || 4
  const toPath = (pts, w) => {
    if (!pts.length) return ''
    const step = pts.length > 1 ? w / (pts.length - 1) : w
    return pts.map((p, i) => {
      const v = Number(p.bonus || 0)
      const x = i * step
      const y = CHART_H - (v / top) * CHART_H
      return `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`
    }).join(' ')
  }
  const lineCur = toPath(cur, CHART_W)
  const linePrev = toPath(prev, CHART_W)
  const areaCur = lineCur ? `${lineCur} L${CHART_W},${CHART_H} L0,${CHART_H} Z` : ''
  const ticks = [1, 0.75, 0.5, 0.25, 0].map(r => ({
    y: CHART_H * (1 - r),
    label: formatTick(top * r),
  }))
  return { lineCur, linePrev, areaCur, ticks, top, hasPrev: !!linePrev }
})

function formatTick(v) {
  const n = Number(v || 0)
  if (n >= 10000) return `${(n / 1000).toFixed(0)}k`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(Math.round(n))
}

// ── 任务矩阵 ────────────────────────────────────────────────
const stateMeta = {
  running: { color: 'success', text: '运行中' },
  seeding: { color: 'primary', text: '做种中' },
  stopped: { color: 'secondary', text: '已停止' },
  disabled: { color: 'secondary', text: '已停用' },
}

function modeKey(t) {
  if (t?.enabled === false) return 'disabled'
  return t?.run_mode || 'running'
}

function rowMeta(t) {
  const k = modeKey(t)
  return stateMeta[k] || stateMeta.running
}

const normalTasks = computed(() => (props.tasks || []).filter(t => t && t.task_type !== 'host'))
const hostTasks = computed(() => (props.tasks || []).filter(t => t && t.task_type === 'host'))

// 矩阵口径：优先经营任务（刷流/刷魔力）；没有经营任务时（如灰度环境未配站点）
// 回退显示常驻任务，避免整块空白 —— 行上会标「常驻」以示区分。
const fallbackHost = computed(() => normalTasks.value.length === 0 && hostTasks.value.length > 0)

const rows = computed(() => {
  const list = normalTasks.value.length ? normalTasks.value : hostTasks.value
  // 设计稿按产出从高到低排列（时魔相同再按种子数）
  return [...list].sort((a, b) => {
    const da = Number(a.site_bonus_per_hour || 0)
    const db = Number(b.site_bonus_per_hour || 0)
    if (db !== da) return db - da
    return Number(b.seeding_count || 0) - Number(a.seeding_count || 0)
  })
})

const hiddenHostCount = computed(() => (fallbackHost.value ? 0 : hostTasks.value.length))

function rowBonus(t) {
  if (t?.site_bonus_ok === false) return '—'
  const v = t?.site_bonus_per_hour
  if (v === null || v === undefined) return '—'
  return formatBonus(v)
}

function rowSubtitle(t) {
  // 回退到常驻任务时（灰度没配站点），标「常驻」区分口径
  if (t?.task_type === 'host') return '常驻任务 · 全站托管'
  const site = t?.site_name || t?.site_domain || '未知站点'
  const kind = t?.task_type === 'brush' ? '刷流' : '刷魔力'
  return `${site} · ${kind}`
}

// ── 上次运行 ────────────────────────────────────────────────
const lastRun = computed(() => {
  const runs = (props.ops || []).filter(o => o && o.kind === 'run')
  if (!runs.length) return null
  const o = [...runs].sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0))[0]
  const at = Number(o.created_at || 0) * 1000
  return {
    ago: at ? relativeTime(at) : '—',
    duration: o.duration ? formatDuration(o.duration) : '—',
    items: Array.isArray(o.items) ? o.items.length : 0,
    state: o.state || '',
    task: o.task_id || '',
  }
})

function relativeTime(ms) {
  const diff = Math.max(0, Number(props.now || Date.now()) - ms)
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  return `${Math.floor(hr / 24)} 天前`
}

function formatDuration(sec) {
  const v = Number(sec || 0)
  if (v < 60) return `${v.toFixed(1)}s`
  const m = Math.floor(v / 60)
  const r = Math.round(v % 60)
  return `${m}m${r}s`
}

function opTime(o) {
  const at = Number(o?.created_at || 0) * 1000
  return at ? relativeTime(at) : '—'
}

function stateDotClass(st) {
  if (st === 'completed') return 'is-ok'
  if (st === 'failed' || st === 'error') return 'is-bad'
  if (st === 'running') return 'is-run'
  return 'is-idle'
}

function opText(o) {
  const it = Array.isArray(o?.items) && o.items.length ? o.items[0] : null
  const head = it?.title || it?.reason || '—'
  const task = taskName(o?.task_id)
  return task ? `${task} · ${head}` : head
}

const taskNameMap = computed(() => {
  const m = {}
  for (const t of props.tasks || []) m[t.id] = t.name
  return m
})

function taskName(id) {
  return taskNameMap.value[id] || ''
}

const recentOps = computed(() =>
  [...(props.ops || [])]
    .sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0))
    .slice(0, 5),
)

// ── 右栏：H&R 临期 ──────────────────────────────────────────
const hrSummary = computed(() => {
  const list = props.bills || []
  if (!list.length) return { count: 0, soonest: null }
  const pending = list.filter(b => !b.completed)
  const pool = pending.length ? pending : list
  const sorted = [...pool].sort((a, b) => Number(a.remain_hours ?? 1e9) - Number(b.remain_hours ?? 1e9))
  return { count: pool.length, soonest: sorted[0] || null }
})

// ── 状态 chip ───────────────────────────────────────────────
const notifyTotal = computed(() => Number(props.notifyCount || 0))

const healthChip = computed(() => ({
  label: props.healthLabel || (props.health?.ok === false ? '异常' : '正常'),
  color: props.healthColor || (props.health?.ok === false ? 'error' : 'success'),
}))

const ceilingColor = computed(() => (ceilingPct.value >= 85 ? 'error' : ceilingPct.value >= 70 ? 'warning' : 'success'))

const quickPages = computed(() => (props.pages || []).slice(0, 3))
</script>

<template>
  <div class="mfh">
    <!-- ═══ 主列 ═══ -->
    <div class="mfh__main">
      <header class="mfh__head">
        <div class="mfh__head-text">
          <h2>整体概览</h2>
          <p>
            {{ taskTotal }} 个任务 · 全站口径 · 每 5 分钟刷新
            <span v-if="hiddenHostCount" class="mfh__dim">（另有 {{ hiddenHostCount }} 个常驻任务，见功能中心）</span>
          </p>
        </div>
        <div class="mfh__chips">
          <button type="button" class="mfh-chip" @click="emit('open-health')">
            <span class="mfh-chip__dot" :class="`is-${healthChip.color}`" />
            健康自检 · {{ healthChip.label }}
            <span v-if="healthBadge" class="mfh-chip__num">{{ healthBadge }}</span>
          </button>
          <button type="button" class="mfh-chip" @click="emit('open-ceiling')">
            <span class="mfh-chip__dot" :class="`is-${ceilingColor}`" />
            站点容量 · {{ ceilingPct.toFixed(0) }}%
          </button>
          <button type="button" class="mfh-chip" @click="emit('open-hr')">
            <span class="mfh-chip__dot" :class="hrSummary.count ? 'is-warning' : 'is-success'" />
            H&amp;R · {{ hrSummary.count }} 期
          </button>
          <button type="button" class="mfh-chip" @click="emit('open-page', 'notify')">
            <span class="mfh-chip__dot is-info" />
            通知 · {{ notifyTotal }} 条
          </button>
        </div>
      </header>

      <!-- ── 全局 4 指标 ── -->
      <section class="mfh__kpis">
        <article class="mfh-kpi">
          <div class="mfh-kpi__label">托管种子<span class="mfh-kpi__scope">· 全站</span></div>
          <div class="mfh-kpi__row">
            <div class="mfh-kpi__value">{{ seedingCount }}<span class="mfh-kpi__unit">条</span></div>
            <svg class="mfh-kpi__spark" viewBox="0 0 170 36" preserveAspectRatio="none" aria-hidden="true">
              <path v-if="sparkSeeds.area" :d="sparkSeeds.area" class="mfh-spark__area is-primary" />
              <path v-if="sparkSeeds.line" :d="sparkSeeds.line" class="mfh-spark__line is-primary" />
            </svg>
          </div>
          <div class="mfh-kpi__foot">做种 {{ activeSeeding }} · 暂停 {{ stoppedCount }} · 任务 {{ runningCount }} 跑中</div>
        </article>

        <article class="mfh-kpi">
          <div class="mfh-kpi__label">站点上报时魔<span class="mfh-kpi__scope">/ h</span></div>
          <div class="mfh-kpi__row">
            <div class="mfh-kpi__value">{{ formatBonus(bonusPerHour) }}</div>
            <svg class="mfh-kpi__spark" viewBox="0 0 170 36" preserveAspectRatio="none" aria-hidden="true">
              <path v-if="sparkBonus.area" :d="sparkBonus.area" class="mfh-spark__area is-success" />
              <path v-if="sparkBonus.line" :d="sparkBonus.line" class="mfh-spark__line is-success" />
            </svg>
          </div>
          <div class="mfh-kpi__foot">全站 {{ taskTotal }} 个任务汇总</div>
        </article>

        <article class="mfh-kpi">
          <div class="mfh-kpi__label">站点当前魔力<span class="mfh-kpi__scope">点</span></div>
          <div class="mfh-kpi__row">
            <div class="mfh-kpi__value">{{ Math.round(currentBonus).toLocaleString() }}</div>
            <svg class="mfh-kpi__spark" viewBox="0 0 170 36" preserveAspectRatio="none" aria-hidden="true">
              <path v-if="sparkBonusNow.area" :d="sparkBonusNow.area" class="mfh-spark__area is-info" />
              <path v-if="sparkBonusNow.line" :d="sparkBonusNow.line" class="mfh-spark__line is-info" />
            </svg>
          </div>
          <div class="mfh-kpi__foot">各站实时存量之和</div>
        </article>

        <article class="mfh-kpi">
          <div class="mfh-kpi__label">上次运行</div>
          <div class="mfh-kpi__row">
            <div class="mfh-kpi__value">
              {{ lastRun ? lastRun.ago : '—' }}
            </div>
          </div>
          <div class="mfh-kpi__foot">
            <template v-if="lastRun">处理 {{ lastRun.items }} 项 · 耗时 {{ lastRun.duration }}</template>
            <template v-else>暂无运行记录</template>
          </div>
        </article>
      </section>

      <!-- ── 任务矩阵 ── -->
      <section class="mfh-panel">
        <header class="mfh-panel__head">
          <div>
            <div class="mfh-panel__title">任务矩阵</div>
            <div class="mfh-panel__sub">{{ rows.length }} 个任务 · 点击任意任务进入单任务详情</div>
          </div>
          <button type="button" class="mfh-link" @click="emit('create-task')">新建任务</button>
        </header>

        <div class="mfh-matrix">
          <div class="mfh-matrix__head">
            <span>任务</span>
            <span class="mfh-matrix__num">时魔 / h</span>
            <span class="mfh-matrix__num">种子</span>
            <span />
          </div>
          <button
            v-for="t in rows"
            :key="t.id"
            type="button"
            class="mfh-matrix__row"
            @click="emit('open-task', t.id)"
          >
            <span class="mfh-matrix__name">
              <span class="mfh-dot" :class="`is-${rowMeta(t).color}`" />
              <span class="mfh-matrix__label">
                <strong>{{ t.name }}</strong>
                <em>{{ rowSubtitle(t) }}</em>
              </span>
            </span>
            <span class="mfh-matrix__num">{{ rowBonus(t) }}</span>
            <span class="mfh-matrix__num">{{ t.seeding_count || 0 }}</span>
            <VIcon icon="mdi-chevron-right" size="16" class="mfh-matrix__chev" />
          </button>
          <div v-if="!rows.length" class="mfh-matrix__empty">
            还没有任务。点右上角「新建任务」开始。
          </div>
        </div>
      </section>

      <!-- ── 全站时魔趋势 ── -->
      <section class="mfh-panel mfh-panel--chart">
        <header class="mfh-panel__head">
          <div>
            <div class="mfh-panel__title">全站时魔趋势</div>
            <div class="mfh-panel__sub">每小时采样 · 最近 72 小时</div>
          </div>
          <div class="mfh-legend">
            <span class="mfh-legend__item"><i class="mfh-legend__line is-primary" />本周</span>
            <span v-if="chart && chart.hasPrev" class="mfh-legend__item"><i class="mfh-legend__line is-dashed" />上周</span>
          </div>
        </header>

        <div v-if="chart" class="mfh-chart">
          <div class="mfh-chart__yaxis">
            <span v-for="tick in chart.ticks" :key="tick.y" :style="{ bottom: `${(tick.y / CHART_H) * 100}%` }">
              {{ tick.label }}
            </span>
          </div>
          <div class="mfh-chart__plot">
            <svg viewBox="0 0 900 168" preserveAspectRatio="none" class="mfh-chart__svg" aria-hidden="true">
              <line
                v-for="tick in chart.ticks"
                :key="`g${tick.y}`"
                x1="0"
                :y1="tick.y"
                x2="900"
                :y2="tick.y"
                class="mfh-chart__grid"
              />
              <path v-if="chart.areaCur" :d="chart.areaCur" class="mfh-chart__area" />
              <path v-if="chart.linePrev" :d="chart.linePrev" class="mfh-chart__prev" />
              <path v-if="chart.lineCur" :d="chart.lineCur" class="mfh-chart__cur" />
            </svg>
            <div class="mfh-chart__xaxis">
              <span>72h 前</span>
              <span>36h 前</span>
              <span>现在</span>
            </div>
          </div>
        </div>
        <div v-else class="mfh-chart__empty">暂无小时采样数据（任务跑起来后才会有曲线）</div>
      </section>
    </div>

    <!-- ═══ 右栏 ═══ -->
    <aside class="mfh__side">
      <!-- 全局动态 -->
      <section class="mfh-panel mfh-panel--side">
        <header class="mfh-panel__head">
          <div class="mfh-panel__title">全局动态</div>
          <button type="button" class="mfh-link" @click="emit('open-ops')">全部</button>
        </header>
        <div class="mfh-ops">
          <div v-if="!recentOps.length" class="mfh-ops__empty">暂无操作记录</div>
          <button
            v-for="o in recentOps"
            :key="o.operation_id"
            type="button"
            class="mfh-ops__row"
            @click="emit('open-ops')"
          >
            <span class="mfh-dot" :class="stateDotClass(o.state)" />
            <span class="mfh-ops__body">
              <span class="mfh-ops__title">{{ opText(o) }}</span>
              <span class="mfh-ops__time">{{ opTime(o) }}</span>
            </span>
          </button>
        </div>
      </section>

      <!-- 站点监控 -->
      <section class="mfh-panel mfh-panel--side">
        <header class="mfh-panel__head">
          <div class="mfh-panel__title">站点监控</div>
          <button type="button" class="mfh-link" @click="emit('open-page', 'hub')">功能中心</button>
        </header>
        <div class="mfh-mon">
          <button type="button" class="mfh-mon__row" @click="emit('open-health')">
            <span class="mfh-mon__label"><span class="mfh-dot" :class="`is-${healthChip.color}`" />健康自检</span>
            <span class="mfh-mon__value" :class="`is-${healthChip.color}`">{{ healthChip.label }}</span>
          </button>
          <button type="button" class="mfh-mon__row" @click="emit('open-ceiling')">
            <span class="mfh-mon__label"><span class="mfh-dot" :class="`is-${ceilingColor}`" />站点容量</span>
            <span class="mfh-mon__value">{{ ceilingPct.toFixed(0) }}%</span>
          </button>
          <div class="mfh-mon__bar">
            <span :class="`is-${ceilingColor}`" :style="{ width: `${Math.min(100, ceilingPct)}%` }" />
          </div>
          <button type="button" class="mfh-mon__row" @click="emit('open-hr')">
            <span class="mfh-mon__label"><span class="mfh-dot" :class="hrSummary.count ? 'is-warning' : 'is-success'" />H&amp;R 账单</span>
            <span class="mfh-mon__value">
              {{ hrSummary.count ? `${hrSummary.count} 个待完成` : '无' }}
            </span>
          </button>
        </div>
      </section>

      <!-- 快速功能 -->
      <section class="mfh-panel mfh-panel--side">
        <header class="mfh-panel__head">
          <div class="mfh-panel__title">快速功能</div>
          <button type="button" class="mfh-link" @click="emit('open-page', 'hub')">全部功能</button>
        </header>
        <div class="mfh-quick">
          <button
            v-for="p in quickPages"
            :key="p.key"
            type="button"
            class="mfh-quick__item"
            @click="emit('open-page', p.key)"
          >
            <VIcon :icon="p.icon" size="18" />
            <span>
              <strong>{{ p.label }}</strong>
              <em v-if="p.hint">{{ p.hint }}</em>
            </span>
          </button>
        </div>
      </section>
    </aside>
  </div>
</template>

<style scoped>
/* ── 骨架：主列自适应 + 右栏 340px（对应设计稿 1440 下约 24%）───────── */
.mfh {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 12px;
  align-items: start;
  /* 外层 .magicflow-page 已有 18px padding，这里不再叠加 */
  padding: 0;
}
.mfh__main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.mfh__side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

/* ── 标题行 ───────────────────────────────────────────── */
.mfh__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 2px 2px 0;
}
.mfh__head-text h2 {
  margin: 0;
  font-size: 21px;
  font-weight: 600;
  letter-spacing: 0.2px;
  color: rgba(var(--v-theme-on-surface), 0.95);
}
.mfh__head-text p {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.mfh__dim {
  opacity: 0.75;
}
.mfh__chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.mfh-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.mfh-chip:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
  border-color: rgba(var(--v-theme-on-surface), 0.18);
}
.mfh-chip__num {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.22);
  color: rgb(var(--v-theme-primary));
  font-size: 10.5px;
  line-height: 16px;
  text-align: center;
}

/* ── 状态圆点 ─────────────────────────────────────────── */
.mfh-dot,
.mfh-chip__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
  background: rgba(var(--v-theme-on-surface), 0.3);
}
.is-success { background: rgb(var(--v-theme-success)) !important; }
.is-primary { background: rgb(var(--v-theme-primary)) !important; }
.is-info { background: rgb(var(--v-theme-info)) !important; }
.is-warning { background: rgb(var(--v-theme-warning)) !important; }
.is-error { background: rgb(var(--v-theme-error)) !important; }
.is-bad { background: rgb(var(--v-theme-error)) !important; }
.is-secondary { background: rgba(var(--v-theme-on-surface), 0.34) !important; }
.is-idle { background: rgba(var(--v-theme-on-surface), 0.3) !important; }
.is-run { background: rgb(var(--v-theme-info)) !important; }
.is-ok { background: rgb(var(--v-theme-success)) !important; }

/* ── KPI 卡 ───────────────────────────────────────────── */
.mfh__kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.mfh-kpi {
  padding: 12px 14px 13px;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-on-surface), 0.03);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 104px;
}
.mfh-kpi__label {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.mfh-kpi__scope {
  margin-left: 3px;
  opacity: 0.62;
}
.mfh-kpi__row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 10px;
  min-height: 38px;
}
.mfh-kpi__value {
  font-size: 26px;
  font-weight: 600;
  line-height: 1.1;
  color: rgba(var(--v-theme-on-surface), 0.95);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.mfh-kpi__unit {
  margin-left: 3px;
  font-size: 12px;
  font-weight: 400;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.mfh-kpi__spark {
  width: 170px;
  height: 36px;
  flex: none;
  opacity: 0.9;
}
.mfh-kpi__foot {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  line-height: 1.4;
}

/* sparkline 用主题色，area 半透明 */
.mfh-spark__line {
  fill: none;
  stroke-width: 1.6;
  stroke-linejoin: round;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}
.mfh-spark__line.is-primary { stroke: rgb(var(--v-theme-primary)); }
.mfh-spark__line.is-success { stroke: rgb(var(--v-theme-success)); }
.mfh-spark__line.is-info { stroke: rgb(var(--v-theme-info)); }
.mfh-spark__area { stroke: none; opacity: 0.18; }
.mfh-spark__area.is-primary { fill: rgb(var(--v-theme-primary)); }
.mfh-spark__area.is-success { fill: rgb(var(--v-theme-success)); }
.mfh-spark__area.is-info { fill: rgb(var(--v-theme-info)); }

/* ── 面板通用 ─────────────────────────────────────────── */
.mfh-panel {
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-on-surface), 0.03);
  padding: 12px 14px 10px;
  min-width: 0;
}
.mfh-panel--side {
  padding: 11px 12px 8px;
}
.mfh-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.mfh-panel__title {
  font-size: 13.5px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.92);
}
.mfh-panel__sub {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  margin-top: 1px;
}
.mfh-link {
  border: 0;
  background: none;
  padding: 0 2px;
  font-size: 12px;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  white-space: nowrap;
}
.mfh-link:hover { text-decoration: underline; }

/* ── 任务矩阵 ─────────────────────────────────────────── */
.mfh-matrix {
  display: flex;
  flex-direction: column;
}
.mfh-matrix__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px 68px 20px;
  gap: 8px;
  padding: 0 6px 5px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.42);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}
.mfh-matrix__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px 68px 20px;
  gap: 8px;
  align-items: center;
  padding: 7px 6px;
  border: 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.05);
  background: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.13s ease;
}
.mfh-matrix__row:last-child { border-bottom: 0; }
.mfh-matrix__row:hover { background: rgba(var(--v-theme-primary), 0.08); }
.mfh-matrix__name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.mfh-matrix__label {
  display: flex;
  align-items: baseline;
  gap: 7px;
  min-width: 0;
}
.mfh-matrix__label strong {
  font-size: 12.8px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.9);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mfh-matrix__label em {
  font-style: normal;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  white-space: nowrap;
}
.mfh-matrix__num {
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), 0.82);
  text-align: right;
}
.mfh-matrix__chev {
  color: rgba(var(--v-theme-on-surface), 0.28);
  justify-self: end;
}
.mfh-matrix__row:hover .mfh-matrix__chev { color: rgb(var(--v-theme-primary)); }
.mfh-matrix__empty {
  padding: 18px 6px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  text-align: center;
}

/* ── 趋势图 ───────────────────────────────────────────── */
.mfh-panel--chart { padding-bottom: 12px; }
.mfh-legend {
  display: flex;
  gap: 12px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.mfh-legend__item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.mfh-legend__line {
  display: inline-block;
  width: 16px;
  height: 0;
  border-top: 2px solid rgb(var(--v-theme-primary));
}
.mfh-legend__line.is-dashed {
  border-top-style: dashed;
  border-color: rgba(var(--v-theme-on-surface), 0.34);
}
.mfh-chart {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 4px;
  height: 196px;
}
.mfh-chart__yaxis {
  position: relative;
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.4);
}
.mfh-chart__yaxis span {
  position: absolute;
  right: 4px;
  transform: translateY(50%);
  font-variant-numeric: tabular-nums;
}
.mfh-chart__plot {
  position: relative;
  min-width: 0;
}
.mfh-chart__svg {
  width: 100%;
  height: calc(100% - 18px);
  display: block;
  overflow: visible;
}
.mfh-chart__grid {
  stroke: rgba(var(--v-theme-on-surface), 0.07);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.mfh-chart__area {
  fill: rgb(var(--v-theme-primary));
  opacity: 0.14;
  stroke: none;
}
.mfh-chart__cur {
  fill: none;
  stroke: rgb(var(--v-theme-primary));
  stroke-width: 2;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}
.mfh-chart__prev {
  fill: none;
  stroke: rgba(var(--v-theme-on-surface), 0.3);
  stroke-width: 1.5;
  stroke-dasharray: 5 4;
  vector-effect: non-scaling-stroke;
}
.mfh-chart__xaxis {
  display: flex;
  justify-content: space-between;
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  padding-top: 2px;
}
.mfh-chart__empty {
  padding: 28px 0 30px;
  text-align: center;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.42);
}

/* ── 右栏：全局动态 ───────────────────────────────────── */
.mfh-ops {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.mfh-ops__row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 4px;
  border: 0;
  border-radius: 6px;
  background: none;
  text-align: left;
  cursor: pointer;
}
.mfh-ops__row:hover { background: rgba(var(--v-theme-on-surface), 0.05); }
.mfh-ops__row .mfh-dot { margin-top: 5px; }
.mfh-ops__body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.mfh-ops__title {
  font-size: 12px;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), 0.82);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.mfh-ops__time {
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.4);
}
.mfh-ops__empty {
  padding: 12px 4px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.42);
}

/* ── 右栏：站点监控 ───────────────────────────────────── */
.mfh-mon {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mfh-mon__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 4px;
  border: 0;
  border-radius: 6px;
  background: none;
  cursor: pointer;
  color: inherit;
}
.mfh-mon__row:hover { background: rgba(var(--v-theme-on-surface), 0.05); }
.mfh-mon__label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.68);
}
.mfh-mon__value {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), 0.85);
}
.mfh-mon__value.is-success { color: rgb(var(--v-theme-success)); background: none !important; }
.mfh-mon__value.is-error { color: rgb(var(--v-theme-error)); background: none !important; }
.mfh-mon__value.is-warning { color: rgb(var(--v-theme-warning)); background: none !important; }
.mfh-mon__bar {
  height: 4px;
  border-radius: 2px;
  background: rgba(var(--v-theme-on-surface), 0.09);
  margin: 0 4px 6px;
  overflow: hidden;
}
.mfh-mon__bar span {
  display: block;
  height: 100%;
  border-radius: 2px;
}
.mfh-mon__bar span.is-success { background: rgb(var(--v-theme-success)) !important; }
.mfh-mon__bar span.is-warning { background: rgb(var(--v-theme-warning)) !important; }
.mfh-mon__bar span.is-error { background: rgb(var(--v-theme-error)) !important; }

/* ── 右栏：快速功能 ───────────────────────────────────── */
.mfh-quick {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mfh-quick__item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 6px;
  border: 0;
  border-radius: 7px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  color: rgba(var(--v-theme-on-surface), 0.82);
  cursor: pointer;
  text-align: left;
}
.mfh-quick__item:hover {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}
.mfh-quick__item span {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.mfh-quick__item strong {
  font-size: 12.2px;
  font-weight: 500;
}
.mfh-quick__item em {
  font-style: normal;
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.42);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 响应式 ───────────────────────────────────────────── */
@media (max-width: 1279px) {
  .mfh {
    grid-template-columns: minmax(0, 1fr);
  }
  .mfh__side {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  }
}
@media (max-width: 959px) {
  .mfh { padding: 10px 10px 18px; }
  .mfh__kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .mfh-kpi { min-height: 96px; }
  .mfh-kpi__spark { display: none; }
  .mfh-matrix__head,
  .mfh-matrix__row {
    grid-template-columns: minmax(0, 1fr) 72px 52px 16px;
  }
  .mfh-matrix__label em { display: none; }
}
</style>
