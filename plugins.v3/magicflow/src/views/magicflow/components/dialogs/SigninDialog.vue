<script setup>
// MagicFlow 前端 · 签到报表弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态 / 调父方法。
// 展示用纯函数：禁止把函数当 prop 下传；useSignin() 里 signinDateLabel / signinStatusText 是工厂内闭包
// （未 module 级导出，且本轮红线不动 composable）→ 就地定义等价纯函数。状态文案复用共享常量
// SIGNIN_STATUS_TEXT（单一真值源，不另造一份映射）。
import { SIGNIN_STATUS_TEXT } from '../../constants'

const signinStatusText = s => SIGNIN_STATUS_TEXT[s] || s
// 日期标签：09/30 → 9/30（窄屏也能完整显示）
const signinDateLabel = d => {
  const s = String(d || '')
  if (s.length < 10) return s
  return `${Number(s.slice(5, 7))}/${Number(s.slice(8, 10))}`
}

// 开关走 defineModel（父 v-model="signinOpen"）；筛选 / 搜索是列表展示态，同样两向绑定，子不直接改父 state。
const open = defineModel({ type: Boolean, default: false })
const signinFilter = defineModel('signinFilter', { type: String, default: 'all' })
const signinSearch = defineModel('signinSearch', { type: String, default: '' })

// 数据（useSignin()：状态 + 派生）——props 下，只读。
defineProps({
  signinReport: { type: Object, default: () => ({}) },
  signinReportLoading: { type: Boolean, default: false },
  signinReportTodayRows: { type: Array, default: () => [] },
  signinTodayCounts: { type: Object, default: () => ({}) },
  signinRunning: { type: Boolean, default: false },
  signinKeepalive: { type: Array, default: () => [] },
  signinKeepaliveNote: { type: String, default: '' },
  signinFilterItems: { type: Array, default: () => [] },
  signinTodayList: { type: Array, default: () => [] },
  signinMatrix: { type: Object, default: () => ({ dates: [], rows: [], stats: {} }) },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh', 'run', 'settings'])
</script>

<template>
  <VDialog v-model="open" max-width="40rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-signin-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">签到</span>
        <VChip v-if="signinReport.enabled" size="x-small" color="success" variant="tonal">已启用</VChip>
        <VChip v-else-if="signinReportLoading" size="x-small" color="grey" variant="tonal">加载中</VChip>
        <VChip v-else size="x-small" color="grey" variant="tonal">已关闭</VChip>
        <span class="magicflow-ops-dialog__spacer" />
        <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="signinReportLoading" @click="emit('refresh')" />
        <VBtn icon="mdi-tune-variant" size="small" variant="text" aria-label="设置" @click="open = false; emit('settings')" />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>
      <div class="magicflow-ops-dialog__sub">共 {{ signinReportTodayRows.length }} 个站点 · 近 7 天记录（右上设置进入配置）</div>
      <div class="magicflow-ops-dialog__body">
        <div class="magicflow-signin-stats">
          <div class="magicflow-signin-stat is-ok">
            <div class="magicflow-signin-stat__v">{{ signinTodayCounts.ok }}</div>
            <div class="magicflow-signin-stat__l">今日成功</div>
          </div>
          <div class="magicflow-signin-stat" :class="signinTodayCounts.fail ? 'is-fail' : ''">
            <div class="magicflow-signin-stat__v">{{ signinTodayCounts.fail }}</div>
            <div class="magicflow-signin-stat__l">今日失败</div>
          </div>
          <div class="magicflow-signin-stat" :class="signinTodayCounts.pending ? 'is-pending' : ''">
            <div class="magicflow-signin-stat__v">{{ signinTodayCounts.pending }}</div>
            <div class="magicflow-signin-stat__l">待执行</div>
          </div>
          <div class="magicflow-signin-stat">
            <div class="magicflow-signin-stat__v">{{ (signinMatrix.stats.ok + signinMatrix.stats.fail) ? Math.round(signinMatrix.stats.ok * 100 / (signinMatrix.stats.ok + signinMatrix.stats.fail)) + '%' : '—' }}</div>
            <div class="magicflow-signin-stat__l">近 7 天成功率</div>
          </div>
        </div>

        <div class="magicflow-signin-actions">
          <VBtn size="small" color="primary" variant="flat" prepend-icon="mdi-calendar-check" :loading="signinRunning" @click="emit('run', 'sign')">立即签到</VBtn>
          <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-login-variant" :loading="signinRunning" @click="emit('run', 'login')">立即登录</VBtn>
        </div>

        <div v-if="signinKeepalive.length" class="magicflow-settings-block">
          <div class="magicflow-settings-block__head"><VIcon icon="mdi-account-clock-outline" size="16" /> 账号保活（站点登入口径）</div>
          <div class="magicflow-keepalive">
            <div
              v-for="k in signinKeepalive"
              :key="k.site_id"
              class="magicflow-keepalive-row"
              :class="'is-' + (k.level || 'unknown')"
            >
              <span class="magicflow-keepalive-row__name" :title="k.domain + (k.exempt ? ' · 豁免：' + k.exempt : '')">{{ k.site_name }}</span>
              <span class="magicflow-keepalive-row__time">
                最后登入 <b>{{ k.last_login || '—' }}</b>
                <template v-if="k.last_browse && k.last_browse !== k.last_login"> · 最后访问 {{ k.last_browse }}</template>
                <template v-if="k.last_seen_kind === '浏览'">（按更早的「{{ k.last_seen }}」保守起算）</template>
              </span>
              <span class="magicflow-keepalive-row__left" :class="'is-' + (k.level || 'unknown')">
                <template v-if="k.days_left !== null && k.days_left !== undefined">
                  距 {{ k.keep_days }} 天红线还有 {{ k.days_left }} 天
                </template>
                <template v-else>暂无登入记录</template>
              </span>
            </div>
            <p class="magicflow-field__sub">
              {{ signinKeepaliveNote }} → 插件是第三方工具（不算登入），到点请用浏览器 / 官方 App 亲自登一次。
            </p>
          </div>
        </div>

        <div class="magicflow-settings-block">
          <div class="magicflow-settings-block__head"><VIcon icon="mdi-clipboard-check-outline" size="16" /> 今日（{{ signinReport.today || '—' }}）</div>
          <div class="magicflow-signin-filters">
            <VChip
              v-for="f in signinFilterItems"
              :key="f.value"
              size="x-small"
              :color="signinFilter === f.value ? f.color : undefined"
              :variant="signinFilter === f.value ? 'flat' : 'tonal'"
              @click="signinFilter = f.value"
            >{{ f.label }}</VChip>
            <VTextField
              v-model="signinSearch"
              class="magicflow-signin-search"
              density="compact"
              variant="solo-filled"
              flat
              hide-details
              clearable
              placeholder="搜索站点"
              prepend-inner-icon="mdi-magnify"
            />
          </div>
          <div v-if="signinTodayList.length" class="magicflow-signin-today">
            <div v-for="row in signinTodayList" :key="row.site_id" class="magicflow-signin-row" :class="'is-' + row.status">
              <span class="magicflow-signin-row__dot" :class="'is-' + row.status" />
              <span class="magicflow-signin-row__name">{{ row.site_name }}</span>
              <span class="magicflow-signin-row__msg" :title="row.msg">{{ row.msg || '待执行' }}</span>
            </div>
          </div>
          <p v-else class="magicflow-field__sub">还没有站点结果。先到右上齿轮里勾选要签到的站点。</p>
        </div>

        <div v-if="signinMatrix.rows.length" class="magicflow-settings-block">
          <div class="magicflow-settings-block__head"><VIcon icon="mdi-calendar-clock" size="16" /> 近 7 天（{{ signinMatrix.rows.length }} 站）</div>
          <div class="magicflow-signin-matrix">
            <div class="magicflow-signin-matrix__row is-head">
              <span class="magicflow-signin-matrix__name">站点</span>
              <span v-for="d in signinMatrix.dates" :key="d" class="magicflow-signin-matrix__date">{{ signinDateLabel(d) }}</span>
            </div>
            <div v-for="row in signinMatrix.rows" :key="row.sid" class="magicflow-signin-matrix__row">
              <span class="magicflow-signin-matrix__name" :title="row.name">{{ row.name }}</span>
              <span v-for="c in row.cells" :key="c.date" class="magicflow-signin-cell" :class="'is-' + c.status" :title="c.date + ' ' + signinStatusText(c.status)" />
            </div>
          </div>
          <div class="magicflow-signin-legend">
            <span><i class="magicflow-signin-cell is-ok" />成功</span>
            <span><i class="magicflow-signin-cell is-signfail" />签到失败</span>
            <span><i class="magicflow-signin-cell is-loginfail" />登录失败</span>
            <span><i class="magicflow-signin-cell is-fail" />都失败</span>
            <span><i class="magicflow-signin-cell is-pending" />待执行</span>
            <span><i class="magicflow-signin-cell is-none" />无记录</span>
          </div>
        </div>
      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 共享选择器（.magicflow-dialog / settings-dialog__head·__title / ops-dialog__spacer·__sub·__body /
     settings-block·__head / field__sub）：随「签到弹窗」自 index.vue 复制一份，index.vue 原样保留
     （VDialog teleport 到 body，父 scoped 够不到子内部，必须两边各留一份；纯复制，零改动）。── */
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
/* MoviePilot 会给表单控件套一层 .app-responsive-input（默认 ~72px 高），在自研分块里把它收紧 */
.magicflow-settings-block .app-responsive-input {
  min-block-size: 0 !important;
  block-size: auto !important;
  padding-block: 0 !important;
  margin-block: 0 !important;
}
.magicflow-settings-block {
  display: grid;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
}
.magicflow-settings-block__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-field__sub {
  font-size: 0.72rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

/* ── 签到弹窗（专属，随组件自 index.vue 迁入）────────────────────────── */
.magicflow-signin-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-block-start: 8px;
}

/* 签到报表页（按「几十个站点」的规模设计：汇总 → 今日（可筛可搜）→ 近 7 天点阵） */
.magicflow-signin-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}

.magicflow-signin-stat {
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.magicflow-signin-stat__v {
  font-size: 1.35rem;
  font-weight: 700;
  line-height: 1.15;
}

.magicflow-signin-stat__l {
  margin-block-start: 2px;
  font-size: 0.68rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-signin-stat.is-ok .magicflow-signin-stat__v { color: rgb(var(--v-theme-success)); }

.magicflow-signin-stat.is-fail .magicflow-signin-stat__v { color: rgb(var(--v-theme-error)); }

.magicflow-signin-stat.is-pending .magicflow-signin-stat__v { color: rgb(var(--v-theme-warning)); }

.magicflow-signin-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block: 8px;
}

.magicflow-signin-search {
  flex: 1 1 140px;
  min-inline-size: 120px;
}

.magicflow-signin-today {
  display: grid;
  gap: 2px;
  max-block-size: 44vh;
  overflow: auto;
}

/* ★ 7.17.0 账号保活段（最后登入 / 距删号红线） */
.magicflow-keepalive {
  display: grid;
  gap: 4px;
}

.magicflow-keepalive-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 7px 8px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-inline-start: 3px solid rgba(var(--v-theme-on-surface), 0.2);
  min-inline-size: 0;
}

.magicflow-keepalive-row.is-warn {
  background: rgba(245, 158, 11, 0.12);
  border-inline-start-color: #f59e0b;
}

.magicflow-keepalive-row.is-ok { border-inline-start-color: rgb(var(--v-theme-success)); }

.magicflow-keepalive-row__name {
  flex: 0 0 auto;
  font-size: 0.82rem;
  font-weight: 600;
}

.magicflow-keepalive-row__time {
  flex: 0 1 auto;
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.76rem;
  opacity: 0.8;
}

.magicflow-keepalive-row__left {
  margin-inline-start: auto;
  flex: 0 0 auto;
  font-size: 0.76rem;
  font-weight: 600;
  white-space: nowrap;
  opacity: 0.85;
}

.magicflow-keepalive-row__left.is-warn { color: #b45309; }

.magicflow-keepalive-row__left.is-ok { color: rgb(var(--v-theme-success)); }

.magicflow-signin-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-block: 7px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  min-inline-size: 0;
}

.magicflow-signin-row__dot {
  flex: 0 0 auto;
  inline-size: 8px;
  block-size: 8px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.25);
}

.magicflow-signin-row__dot.is-ok { background: rgb(var(--v-theme-success)); }

.magicflow-signin-row__dot.is-signfail { background: rgb(var(--v-theme-error)); }

.magicflow-signin-row__dot.is-loginfail { background: #f59e0b; }

.magicflow-signin-row__dot.is-fail { background: #b91c1c; }

.magicflow-signin-row__dot.is-pending { background: rgb(var(--v-theme-warning)); }

.magicflow-signin-row__dot.is-skip { background: rgba(var(--v-theme-on-surface), 0.3); }

/* 失败行整体着色：签到失败=红 / 登录失败=橙 / 都失败=深红 */
.magicflow-signin-row.is-signfail .magicflow-signin-row__msg { color: rgb(var(--v-theme-error)); }

.magicflow-signin-row.is-loginfail .magicflow-signin-row__msg { color: #b45309; }

.magicflow-signin-row.is-fail .magicflow-signin-row__msg { color: #b91c1c; font-weight: 600; }

.magicflow-signin-row__name {
  flex: 0 1 auto;
  min-inline-size: 5.5em;
  max-inline-size: 46%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.82rem;
  font-weight: 600;
}

.magicflow-signin-row__msg {
  flex: 1 1 auto;
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: end;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-signin-matrix {
  max-block-size: 52vh;
  overflow: auto;
}

.magicflow-signin-matrix__row {
  display: grid;
  grid-template-columns: minmax(70px, 1fr) repeat(7, 26px);
  align-items: center;
  gap: 2px;
  padding-block: 3px;
  min-inline-size: 0;
}

.magicflow-signin-matrix__row.is-head {
  position: sticky;
  inset-block-start: 0;
  z-index: 1;
  background: rgb(var(--v-theme-surface));
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

.magicflow-signin-matrix__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.76rem;
}

.magicflow-signin-matrix__date {
  font-size: 0.6rem;
  text-align: center;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-signin-cell {
  display: inline-block;
  inline-size: 12px;
  block-size: 12px;
  margin-inline: auto;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-signin-cell.is-ok { background: rgb(var(--v-theme-success)); }

.magicflow-signin-cell.is-signfail { background: rgb(var(--v-theme-error)); }

.magicflow-signin-cell.is-loginfail { background: #f59e0b; }

.magicflow-signin-cell.is-fail { background: #b91c1c; }

.magicflow-signin-cell.is-pending { background: rgb(var(--v-theme-warning)); }

.magicflow-signin-cell.is-skip { background: rgba(var(--v-theme-on-surface), 0.3); }

.magicflow-signin-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-block-start: 8px;
  font-size: 0.66rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-signin-legend > span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.magicflow-signin-legend .magicflow-signin-cell {
  margin-inline: 0;
}

/* 共享响应式：ops-dialog__body（repl 自 index.vue 的 @media） */
@media (max-width: 959px) {
  .magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}
</style>
