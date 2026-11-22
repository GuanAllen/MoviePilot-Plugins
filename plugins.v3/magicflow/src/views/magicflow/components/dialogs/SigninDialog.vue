<script setup>
// MagicFlow 前端 · 签到报表弹窗
// ★ 19.12.89 移动端重做（稿：_design_mobile/signin-mobile.html）：
//   ① 数字必须对得上账：16 = 15 成功 + 1「插件管不了」。原来「跳过」这一档在四个 chip
//      和四张统计卡里都没有位置，16 个站只显示 15，剩下那个（馒头）从界面上消失 ——
//      而它恰好是唯一有删号规则、必须主人亲自登入的站。
//   ② 近 7 天成功率口径修正（改在 useSignin.js）：原来只认「都失败」，签到✗或登录✗
//      单独失败时既不计成功也不计失败 → 数字虚高（实测 99% 显示成 100%）。
//   ③ 四张统计卡 → 一行「15 / 16 + 进度条」：0 失败、0 待执行是正常态，不值得各占一格。
//   ④ 「立即签到 / 立即登录」两颗并列按钮撤掉：有失败时主机位给「重试这 N 站」，
//      无事时底部一个「重新签到」；「刷新登录态」降级进 ⋯ 菜单 —— 原名「立即登录」与
//      保活卡的「去登入」是两件事，用同一个词会让人以为点一下就保活了。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
import { computed, ref } from 'vue'
import { SIGNIN_STATUS_TEXT, SIGNIN_FAIL_STATUS } from '../../constants'

const statusText = s => SIGNIN_STATUS_TEXT[s] || s

// 日期标签：09/30 → 9/30（窄屏也能完整显示）
const dateLabel = d => {
  const s = String(d || '')
  if (s.length < 10) return s
  return `${Number(s.slice(5, 7))}/${Number(s.slice(8, 10))}`
}
// 保活时间戳：2026-10-08 05:53:38 → 10-08 05:53（跨年才带年份）
const shortTs = v => {
  const s = String(v || '').trim()
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2})/)
  if (!m) return s
  return m[1] === String(new Date().getFullYear()) ? `${m[2]}-${m[3]} ${m[4]}` : `${m[1]}-${m[2]}-${m[3]}`
}

// 开关走 defineModel（父 v-model="signinOpen"）；筛选 / 搜索是列表展示态，同样两向绑定。
const open = defineModel({ type: Boolean, default: false })
const signinFilter = defineModel('signinFilter', { type: String, default: 'all' })
const signinSearch = defineModel('signinSearch', { type: String, default: '' })

const props = defineProps({
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
  signinPendingRows: { type: Array, default: () => [] },
  signinDoneRows: { type: Array, default: () => [] },
  signinSkipCount: { type: Number, default: 0 },
  signinRate: { type: Object, default: () => ({ ok: 0, fail: 0, skip: 0, none: 0, total: 0, pct: null }) },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh', 'run', 'settings'])

// ── 展示态 ────────────────────────────────────────────────
const showAll = ref(false)     // 「今日已完成」展开成完整列表（含筛选 / 搜索）
const heatOpen = ref(false)    // 近 7 天点阵：它是「成功率凭什么」的证据，不是首屏信息
const noteOpen = ref(false)    // 保活规则原文

const counts = computed(() => {
  const raw = props.signinTodayCounts || {}
  const all = Number(raw.all || 0) || (props.signinReportTodayRows || []).length
  return {
    all,
    ok: Number(raw.ok || 0),
    fail: Number(raw.fail || 0),
    pending: Number(raw.pending || 0),
    skip: Number(raw.skip || 0),
  }
})

// 进度条三段：成功 / 失败 / 插件管不了
const barSeg = computed(() => {
  const t = Math.max(1, counts.value.all)
  return {
    ok: `${(counts.value.ok * 100) / t}%`,
    fail: `${(counts.value.fail * 100) / t}%`,
    skip: `${(counts.value.skip * 100) / t}%`,
  }
})

const donePreview = computed(() => (props.signinDoneRows || []).slice(0, 6))
const doneRest = computed(() => Math.max(0, (props.signinDoneRows || []).length - 6))

const rate = computed(() => props.signinRate || {})
const rateText = computed(() => (rate.value.pct == null ? '—' : `${rate.value.pct}%`))
const rateDenom = computed(() => Number(rate.value.ok || 0) + Number(rate.value.fail || 0))
const rateNote = computed(() => {
  const r = rate.value
  if (r.pct == null) return '近 7 天还没有记录'
  const bits = []
  if (r.fail) bits.push(`${r.fail} 次失败`)
  if (r.skip) bits.push(`${r.skip} 格插件管不了`)
  return bits.length ? `（${bits.join(' · ')}）` : '（无失败）'
})

const pendingCount = computed(() => (props.signinPendingRows || []).length)
const failCount = computed(() => (props.signinPendingRows || []).filter(r => SIGNIN_FAIL_STATUS.includes(r.status)).length)

const headline = computed(() => {
  const c = counts.value
  if (!c.all) return '还没有站点结果'
  if (!pendingCount.value) return `${c.all} 个站点 · 今天都签完了`
  return `${c.all} 个站点 · ${c.ok} 个已完成`
})

// 保活：按 site_id 找同一条（今日区和保活区共用一个站时，登入口只出现一次）
const keepOf = sid => (props.signinKeepalive || []).find(k => String(k.site_id) === String(sid)) || null

const statusTag = s => ({
  ok: '已完成',
  fail: '签到和登录都失败',
  signfail: '签到失败',
  loginfail: '登录失败',
  pending: '待执行',
  skip: '插件管不了',
  none: '无记录',
}[s] || statusText(s))

function rowWhy(row) {
  const rs = row.reasons || []
  if (rs.length) return rs.map(x => `${x.kind}：${x.message || '失败'}`).join('；')
  if (row.all_na) return 'API 鉴权站，没有签到接口 —— 这个站得你自己去'
  if (row.status === 'pending') return '还没轮到，稍后会自动补'
  return row.msg || ''
}

const canRetry = row => SIGNIN_FAIL_STATUS.includes(row.status)
function retryOne(row) {
  emit('run', 'sign', { siteIds: [row.site_id], force: true })
}
function retryFailed() {
  const ids = (props.signinPendingRows || [])
    .filter(r => SIGNIN_FAIL_STATUS.includes(r.status))
    .map(r => r.site_id)
  if (ids.length) emit('run', 'sign', { siteIds: ids, force: true })
}
function rerunAll() {
  emit('run', 'sign', {})
}
function relogin() {
  emit('run', 'login', {})
}
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
        <VMenu location="bottom end" :close-on-content-click="true">
          <template #activator="{ props: menuProps }">
            <VBtn v-bind="menuProps" icon="mdi-dots-vertical" size="small" variant="text" aria-label="更多" />
          </template>
          <VList density="compact">
            <VListItem prepend-icon="mdi-login-variant" title="刷新登录态" subtitle="模拟登录，换一次站点 cookie" @click="relogin" />
            <VListItem prepend-icon="mdi-tune-variant" title="签到设置" subtitle="选站点、签到间隔" @click="open = false; emit('settings')" />
          </VList>
        </VMenu>
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>

      <div class="magicflow-ops-dialog__sub">{{ headline }}</div>

      <div class="magicflow-ops-dialog__body">

        <!-- ① 一行摘要：15 / 16 + 进度条（替掉四张各占一格的统计卡） -->
        <div class="mf-sg-kpi">
          <div class="mf-sg-kpi__row">
            <div class="mf-sg-kpi__big">{{ counts.ok }}<i> / {{ counts.all }}</i></div>
            <div class="mf-sg-kpi__note">
              近 7 天<b>{{ rateText }}</b>{{ rateNote }}
            </div>
          </div>
          <div class="mf-sg-kpi__bar">
            <i class="is-ok" :style="{ width: barSeg.ok }" />
            <i class="is-fail" :style="{ width: barSeg.fail }" />
            <i class="is-na" :style="{ width: barSeg.skip }" />
          </div>
        </div>

        <!-- ② 要人动手的：失败 / 待执行 / 插件管不了 -->
        <div
          v-for="row in signinPendingRows"
          :key="'todo-' + row.site_id"
          class="mf-sg-todo"
          :class="'is-' + row.status"
        >
          <div class="mf-sg-todo__top">
            <span class="mf-sg-dot" :class="'is-' + row.status" />
            <span class="mf-sg-todo__nm">{{ row.site_name }}</span>
            <span class="mf-sg-todo__tag">{{ statusTag(row.status) }}</span>
          </div>
          <div class="mf-sg-todo__why">{{ rowWhy(row) }}</div>
          <div class="mf-sg-todo__acts">
            <VBtn
              v-if="canRetry(row)"
              size="small"
              color="primary"
              variant="flat"
              :loading="signinRunning"
              @click="retryOne(row)"
            >重试这一站</VBtn>
            <VBtn
              v-if="keepOf(row.site_id) && keepOf(row.site_id).url"
              size="small"
              color="primary"
              variant="tonal"
              :href="keepOf(row.site_id).url"
              target="_blank"
              rel="noopener"
              append-icon="mdi-open-in-new"
            >去网站登入</VBtn>
            <span
              v-if="keepOf(row.site_id) && keepOf(row.site_id).days_left != null"
              class="mf-sg-todo__hint"
            >还有 <b>{{ keepOf(row.site_id).days_left }}</b> 天到 {{ keepOf(row.site_id).keep_days }} 天删号线</span>
          </div>
        </div>

        <!-- 失败不止一个时，给一个「一次都重试」 -->
        <div v-if="failCount > 1" class="mf-sg-bulk">
          <VBtn size="small" color="primary" variant="flat" :loading="signinRunning" @click="retryFailed">
            重试这 {{ failCount }} 站
          </VBtn>
          <span class="mf-sg-bulk__hint">只重试失败的，已经签过的站不必再打扰</span>
        </div>

        <!-- ③ 今日已完成（默认 6 条，可展开成完整列表） -->
        <div class="mf-sg-sec">
          <h3>今日已完成</h3>
          <span class="n">{{ signinDoneRows.length }} 站</span>
          <button v-if="!showAll && signinDoneRows.length" class="act" type="button" @click="showAll = true">
            全部
            <VIcon icon="mdi-chevron-right" size="14" />
          </button>
          <button v-else-if="showAll" class="act" type="button" @click="showAll = false">
            收起
            <VIcon icon="mdi-chevron-left" size="14" />
          </button>
        </div>

        <template v-if="!showAll">
          <div v-for="row in donePreview" :key="'done-' + row.site_id" class="mf-sg-srow">
            <span class="mf-sg-dot is-ok" />
            <span class="mf-sg-srow__nm">{{ row.site_name }}</span>
            <span class="mf-sg-srow__st">{{ row.msg || '已完成' }}</span>
          </div>
          <button v-if="doneRest" class="mf-sg-fold" type="button" @click="showAll = true">
            还有 {{ doneRest }} 站
            <VIcon icon="mdi-chevron-down" size="16" />
          </button>
          <p v-if="!signinDoneRows.length" class="mf-sg-empty">
            今天还没有签完的站点。{{ pendingCount ? '上面列着还没处理完的。' : '先到 ⋯ 签到设置里勾选要签的站点。' }}
          </p>
        </template>

        <template v-else>
          <div class="mf-sg-chips">
            <VChip
              v-for="f in signinFilterItems"
              :key="f.value"
              size="small"
              :color="signinFilter === f.value ? (f.color || 'grey-darken-1') : undefined"
              :variant="signinFilter === f.value ? 'flat' : 'tonal'"
              @click="signinFilter = f.value"
            >{{ f.label }}</VChip>
            <VTextField
              v-model="signinSearch"
              class="mf-sg-search"
              density="compact"
              variant="solo-filled"
              flat
              hide-details
              clearable
              placeholder="搜站点"
              prepend-inner-icon="mdi-magnify"
            />
          </div>
          <div v-if="signinTodayList.length" class="mf-sg-list">
            <div v-for="row in signinTodayList" :key="row.site_id" class="mf-sg-srow" :class="'is-' + row.status">
              <span class="mf-sg-dot" :class="'is-' + row.status" />
              <span class="mf-sg-srow__nm">{{ row.site_name }}</span>
              <span class="mf-sg-srow__st">{{ row.msg || statusTag(row.status) }}</span>
            </div>
          </div>
          <p v-else class="mf-sg-empty">这个筛选下没有站点</p>
        </template>

        <!-- ④ 账号登入（这功能存在的唯一理由：插件不算登入，必须本人去登） -->
        <div v-if="signinKeepalive.length" class="mf-sg-keep">
          <div class="mf-sg-keep__hd">
            <VIcon icon="mdi-account-clock-outline" size="16" />
            账号登入
            <span class="only">仅列出有明确删号规则的站点</span>
          </div>

          <div
            v-for="k in signinKeepalive"
            :key="'keep-' + k.site_id"
            class="mf-sg-keep__row"
            :class="'is-' + (k.level || 'unknown')"
          >
            <div class="mf-sg-keep__top">
              <span class="mf-sg-keep__nm">{{ k.site_name }}</span>
              <span class="mf-sg-keep__left" :class="'is-' + (k.level || 'unknown')">
                <template v-if="k.days_left !== null && k.days_left !== undefined">
                  <b>{{ k.days_left }}</b> 天后到 {{ k.keep_days }} 天删号线
                </template>
                <template v-else>暂无登入记录</template>
              </span>
            </div>
            <div class="mf-sg-keep__tl">
              <div v-if="k.last_login" class="is-hi">你上次亲自登入 <b>{{ shortTs(k.last_login) }}</b></div>
              <div v-if="k.last_browse && k.last_browse !== k.last_login">
                插件 {{ shortTs(k.last_browse) }} 访问过 —— <b>不算</b>
              </div>
              <div v-if="k.last_seen_kind === '浏览'">按更早的「{{ shortTs(k.last_seen) }}」保守起算</div>
            </div>
            <a
              v-if="k.url"
              class="mf-sg-keep__go"
              :href="k.url"
              target="_blank"
              rel="noopener"
              :title="'打开 ' + k.site_name + ' 亲自登入：' + k.url"
            >
              打开 {{ k.site_name }} 去登入
              <VIcon icon="mdi-open-in-new" size="14" />
            </a>
            <div v-if="k.exempt" class="mf-sg-keep__exempt">豁免：{{ k.exempt }}</div>
          </div>

          <button class="mf-sg-note" type="button" @click="noteOpen = !noteOpen">
            <span>官方口径：只有用浏览器打开网站才算登入</span>
            <span class="more">{{ noteOpen ? '收起' : '详情' }}</span>
          </button>
          <p v-if="noteOpen" class="mf-sg-note__body">
            {{ signinKeepaliveNote || '官方口径：登入指用浏览器存取网站网页进行登入或存取；单纯做种不算登入，使用第三方工具间接存取也不算登入' }}
            做种不算，第三方工具（包括本插件）间接访问也不算。
          </p>
          <p class="mf-sg-keep__foot">
            只有这些站有可查的删号规则。其余站点没查到明确规则，所以不在这里 —— 不是「不用管」。
          </p>
        </div>

        <!-- ⑤ 近 7 天点阵（默认收起） -->
        <div v-if="signinMatrix.rows.length" class="mf-sg-sec">
          <h3>近 7 天</h3>
          <span class="n">{{ signinMatrix.rows.length }} 站 · {{ signinMatrix.dates.length }} 天</span>
          <button class="act" type="button" @click="heatOpen = !heatOpen">
            {{ heatOpen ? '收起' : '展开' }}
            <VIcon :icon="heatOpen ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="16" />
          </button>
        </div>

        <div v-if="heatOpen && signinMatrix.rows.length" class="mf-sg-heat">
          <div class="mf-sg-heat__row is-head">
            <span class="nm">站点</span>
            <span v-for="d in signinMatrix.dates" :key="'h-' + d" class="dt">{{ dateLabel(d) }}</span>
          </div>
          <div v-for="row in signinMatrix.rows" :key="'hm-' + row.sid" class="mf-sg-heat__row">
            <span class="nm" :title="row.name">{{ row.name }}</span>
            <span
              v-for="c in row.cells"
              :key="'c-' + row.sid + '-' + c.date"
              class="mf-sg-cell"
              :class="'is-' + c.status"
              :title="c.date + ' ' + statusText(c.status)"
            />
          </div>
          <div class="mf-sg-legend">
            <span><i class="mf-sg-cell is-ok" />成功</span>
            <span><i class="mf-sg-cell is-signfail" />签到失败</span>
            <span><i class="mf-sg-cell is-loginfail" />登录失败</span>
            <span><i class="mf-sg-cell is-fail" />都失败</span>
            <span><i class="mf-sg-cell is-pending" />待执行</span>
            <span><i class="mf-sg-cell is-skip" />插件管不了</span>
          </div>
          <p class="mf-sg-heat__foot">
            成功率只算「有结果的格」：<b>{{ rate.ok }} / {{ rateDenom }}</b><template v-if="rate.pct != null"> = {{ rate.pct }}%</template>。
            <template v-if="rate.skip">跳过的 {{ rate.skip }} 格不进分子也不进分母，但它们在上面单独列了出来。</template>
          </p>
        </div>

        <!-- ⑥ 底部：无事时只有一个次级动作 -->
        <div class="mf-sg-foot">
          <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-refresh" :loading="signinRunning" @click="rerunAll">
            重新签到
          </VBtn>
          <span class="mf-sg-foot__hint">已签过的站通常返回「今日已签到」，不会重复签</span>
        </div>

      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 共享选择器（.magicflow-dialog / settings-dialog__head·__title / ops-dialog__spacer·__sub·__body）：
   VDialog teleport 到 body，父 scoped 够不到子内部，必须两边各留一份（纯复制，零改动）。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}
.magicflow-settings-dialog__head i { color: rgba(var(--v-theme-on-surface), 0.9); }
.magicflow-settings-dialog__head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 10px 8px 18px;
}
.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
  margin-inline-end: 4px;
}
.magicflow-ops-dialog__spacer { flex: 1 1 auto; }
.magicflow-ops-dialog__sub {
  padding: 0 18px 6px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-ops-dialog__body { padding: 4px 18px 20px; overflow: auto; flex: 1 1 auto; min-height: 0; }

/* MoviePilot 会给表单控件套一层 .app-responsive-input（默认 ~72px 高），在自研分块里把它收紧 */
.magicflow-signin-dialog .app-responsive-input {
  min-block-size: 0 !important;
  block-size: auto !important;
  padding-block: 0 !important;
  margin-block: 0 !important;
}

/* ── ① 摘要 ───────────────────────────────────────── */
.mf-sg-kpi { padding: 6px 0 2px; }
.mf-sg-kpi__row { display: flex; align-items: baseline; gap: 10px; }
.mf-sg-kpi__big {
  font-size: 1.85rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.mf-sg-kpi__big i {
  font-style: normal;
  font-size: 1rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.42);
}
.mf-sg-kpi__note {
  margin-inline-start: auto;
  text-align: end;
  font-size: 0.76rem;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-sg-kpi__note b {
  display: block;
  font-size: 0.9rem;
  color: rgb(var(--v-theme-on-surface));
  font-variant-numeric: tabular-nums;
}
.mf-sg-kpi__bar {
  display: flex;
  height: 6px;
  margin-block-start: 12px;
  border-radius: 3px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.mf-sg-kpi__bar i { display: block; height: 100%; }
.mf-sg-kpi__bar .is-ok { background: rgb(var(--v-theme-success)); }
.mf-sg-kpi__bar .is-fail { background: rgb(var(--v-theme-error)); }
.mf-sg-kpi__bar .is-na { background: rgba(var(--v-theme-on-surface), 0.24); }

/* ── ② 待处理卡 ───────────────────────────────────── */
.mf-sg-todo {
  margin-block-start: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-inline-start: 3px solid rgba(var(--v-theme-on-surface), 0.3);
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.mf-sg-todo.is-fail,
.mf-sg-todo.is-signfail {
  border-color: rgba(var(--v-theme-error), 0.32);
  border-inline-start-color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.06);
}
.mf-sg-todo.is-loginfail {
  border-color: rgba(245, 158, 11, 0.34);
  border-inline-start-color: #f59e0b;
  background: rgba(245, 158, 11, 0.07);
}
.mf-sg-todo.is-pending { border-inline-start-color: rgb(var(--v-theme-warning)); }
.mf-sg-todo.is-skip { border-inline-start-color: rgba(var(--v-theme-on-surface), 0.28); }
.mf-sg-todo__top { display: flex; align-items: center; gap: 8px; }
.mf-sg-todo__nm { font-size: 0.95rem; font-weight: 600; }
.mf-sg-todo__tag {
  margin-inline-start: auto;
  font-size: 0.72rem;
  padding: 3px 7px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.mf-sg-todo.is-fail .mf-sg-todo__tag,
.mf-sg-todo.is-signfail .mf-sg-todo__tag { background: rgba(var(--v-theme-error), 0.14); color: rgb(var(--v-theme-error)); }
.mf-sg-todo.is-loginfail .mf-sg-todo__tag { background: rgba(245, 158, 11, 0.16); color: #b45309; }
.mf-sg-todo__why {
  margin-block-start: 5px;
  font-size: 0.82rem;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.72);
  overflow-wrap: anywhere;
}
.mf-sg-todo__acts { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-block-start: 10px; }
.mf-sg-todo__hint { font-size: 0.76rem; color: rgba(var(--v-theme-on-surface), 0.62); }
.mf-sg-todo__hint b { color: rgb(var(--v-theme-on-surface)); font-variant-numeric: tabular-nums; }

.mf-sg-bulk { display: flex; align-items: center; gap: 10px; margin-block-start: 10px; flex-wrap: wrap; }
.mf-sg-bulk__hint { font-size: 0.74rem; color: rgba(var(--v-theme-on-surface), 0.55); }

/* ── ③ 分区标题 ───────────────────────────────────── */
.mf-sg-sec { display: flex; align-items: center; gap: 7px; margin-block: 22px 4px; }
.mf-sg-sec h3 {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-sg-sec .n { font-size: 0.74rem; color: rgba(var(--v-theme-on-surface), 0.42); font-variant-numeric: tabular-nums; }
.mf-sg-sec .act {
  margin-inline-start: auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-block-size: 40px;
  padding-inline: 4px 2px;
  border: 0;
  background: none;
  color: rgb(var(--v-theme-primary));
  font: 500 0.82rem/1 inherit;
  cursor: pointer;
}

/* ── 站点行 ───────────────────────────────────────── */
.mf-sg-srow {
  display: flex;
  align-items: center;
  gap: 10px;
  min-block-size: 48px;
  padding-block: 4px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  min-inline-size: 0;
}
.mf-sg-srow__nm {
  flex: 0 1 auto;
  min-inline-size: 4.5em;
  max-inline-size: 48%;
  font-size: 0.88rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mf-sg-srow__st {
  flex: 1 1 auto;
  min-inline-size: 0;
  text-align: end;
  font-size: 0.76rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mf-sg-srow.is-signfail .mf-sg-srow__st { color: rgb(var(--v-theme-error)); }
.mf-sg-srow.is-loginfail .mf-sg-srow__st { color: #b45309; }
.mf-sg-srow.is-fail .mf-sg-srow__st { color: rgb(var(--v-theme-error)); font-weight: 600; }

.mf-sg-dot {
  flex: 0 0 auto;
  inline-size: 8px;
  block-size: 8px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.22);
}
.mf-sg-dot.is-ok { background: rgb(var(--v-theme-success)); }
.mf-sg-dot.is-signfail,
.mf-sg-dot.is-fail { background: rgb(var(--v-theme-error)); }
.mf-sg-dot.is-loginfail { background: #f59e0b; }
.mf-sg-dot.is-pending { background: rgb(var(--v-theme-warning)); }
.mf-sg-dot.is-skip { background: rgba(var(--v-theme-on-surface), 0.28); }

.mf-sg-fold {
  display: flex;
  align-items: center;
  gap: 6px;
  inline-size: 100%;
  min-block-size: 46px;
  margin-block-start: 4px;
  padding: 0;
  border: 0;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  background: none;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font: 400 0.8rem/1 inherit;
  cursor: pointer;
}
.mf-sg-empty {
  margin: 10px 0 0;
  padding: 16px 12px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 12px;
  text-align: center;
  font-size: 0.8rem;
  line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

/* 完整列表：筛选 + 搜索 + 可滚 */
.mf-sg-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block: 8px 6px;
}
.mf-sg-search { flex: 1 1 130px; min-inline-size: 110px; }
.mf-sg-list { max-block-size: 42vh; overflow: auto; }

/* ── ④ 账号登入 ───────────────────────────────────── */
.mf-sg-keep {
  margin-block-start: 22px;
  padding: 12px 14px 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.11);
  border-radius: 12px;
}
.mf-sg-keep__hd {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-sg-keep__hd .only {
  margin-inline-start: auto;
  font-size: 0.7rem;
  font-weight: 400;
  color: rgba(var(--v-theme-on-surface), 0.42);
}
.mf-sg-keep__row {
  margin-block-start: 12px;
  padding-block-start: 12px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}
.mf-sg-keep__row:first-of-type { margin-block-start: 10px; padding-block-start: 0; border-block-start: 0; }
.mf-sg-keep__top { display: flex; align-items: baseline; gap: 8px; }
.mf-sg-keep__nm { font-size: 0.92rem; font-weight: 600; }
.mf-sg-keep__left {
  margin-inline-start: auto;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-variant-numeric: tabular-nums;
}
.mf-sg-keep__left b { font-size: 1.15rem; font-weight: 700; color: rgb(var(--v-theme-success)); }
.mf-sg-keep__left.is-warn b { color: #b45309; }
.mf-sg-keep__left.is-unknown b { color: rgba(var(--v-theme-on-surface), 0.5); }
.mf-sg-keep__tl {
  margin-block-start: 8px;
  padding-inline-start: 13px;
  border-inline-start: 2px solid rgba(var(--v-theme-on-surface), 0.12);
}
.mf-sg-keep__tl div {
  position: relative;
  font-size: 0.78rem;
  line-height: 1.65;
  color: rgba(var(--v-theme-on-surface), 0.66);
}
.mf-sg-keep__tl div::before {
  content: "";
  position: absolute;
  inset-inline-start: -18px;
  inset-block-start: 7px;
  inline-size: 6px;
  block-size: 6px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.25);
}
.mf-sg-keep__tl div.is-hi::before { background: rgb(var(--v-theme-primary)); }
.mf-sg-keep__tl b { color: rgb(var(--v-theme-on-surface)); font-weight: 600; }
.mf-sg-keep__go {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-block-size: 40px;
  margin-block-start: 8px;
  padding: 0 12px;
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
  font-size: 0.8rem;
  font-weight: 600;
  text-decoration: none;
}
.mf-sg-keep__exempt {
  margin-block-start: 6px;
  font-size: 0.72rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.mf-sg-note {
  display: flex;
  align-items: baseline;
  gap: 6px;
  inline-size: 100%;
  min-block-size: 40px;
  margin-block-start: 10px;
  padding: 8px 0 0;
  border: 0;
  border-block-start: 1px dashed rgba(var(--v-theme-on-surface), 0.14);
  background: none;
  text-align: start;
  font: 400 0.74rem/1.5 inherit;
  color: rgba(var(--v-theme-on-surface), 0.62);
  cursor: pointer;
}
.mf-sg-note .more { margin-inline-start: auto; color: rgb(var(--v-theme-primary)); }
.mf-sg-note__body {
  margin: 6px 0 0;
  font-size: 0.74rem;
  line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.mf-sg-keep__foot {
  margin: 8px 0 0;
  font-size: 0.72rem;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.45);
}

/* ── ⑤ 近 7 天点阵 ─────────────────────────────────── */
.mf-sg-heat {
  margin-block-start: 6px;
  padding: 10px 10px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.11);
  border-radius: 12px;
  overflow: auto;
}
.mf-sg-heat__row {
  display: grid;
  grid-template-columns: minmax(74px, 1fr) repeat(7, 26px);
  align-items: center;
  gap: 3px;
  padding-block: 3px;
  min-inline-size: 0;
}
.mf-sg-heat__row.is-head { margin-block-end: 4px; }
.mf-sg-heat__row .nm {
  font-size: 0.76rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.68);
}
.mf-sg-heat__row .dt {
  font-size: 0.62rem;
  text-align: center;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.42);
}
.mf-sg-cell {
  display: inline-block;
  inline-size: 12px;
  block-size: 12px;
  margin-inline: auto;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.mf-sg-cell.is-ok { background: rgb(var(--v-theme-success)); }
.mf-sg-cell.is-signfail { background: rgb(var(--v-theme-error)); }
.mf-sg-cell.is-loginfail { background: #f59e0b; }
.mf-sg-cell.is-fail { background: #b91c1c; }
.mf-sg-cell.is-pending { background: rgb(var(--v-theme-warning)); }
.mf-sg-cell.is-skip { background: rgba(var(--v-theme-on-surface), 0.2); }
.mf-sg-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-block-start: 10px;
  font-size: 0.68rem;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.mf-sg-legend span { display: inline-flex; align-items: center; gap: 4px; }
.mf-sg-legend .mf-sg-cell { margin-inline: 0; }
.mf-sg-heat__foot {
  margin: 8px 0 0;
  font-size: 0.72rem;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

/* ── ⑥ 底部 ───────────────────────────────────────── */
.mf-sg-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-block-start: 22px;
  padding-block-start: 14px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}
.mf-sg-foot__hint { font-size: 0.72rem; color: rgba(var(--v-theme-on-surface), 0.42); }

@media (max-width: 959px) {
  .magicflow-ops-dialog__body { padding: 4px 16px 18px; }
  .mf-sg-kpi__big { font-size: 2rem; }
  .mf-sg-heat__row { grid-template-columns: minmax(66px, 1fr) repeat(7, minmax(20px, 1fr)); }
  .mf-sg-cell { inline-size: 13px; block-size: 13px; }
}
</style>
