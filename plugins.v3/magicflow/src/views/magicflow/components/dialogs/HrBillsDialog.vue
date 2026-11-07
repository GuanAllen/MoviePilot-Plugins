<script setup>
// MagicFlow 前端 · H&R 账单弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（hrBillStateColor / hrBillsAtRisk / fmtHoursLeft）自 composables/useHrBills.js
// 具名导入复用 —— 单一真值源，不在两处各写一份。
// ★ 19.12.48（任务 96）：
//   · pending 独立明细区（站点/名称/hash/规则/状态/需做种/已做种/进度），默认展开；
//   · 实时刷新（live=1），新账单不再被启动快照挡住；
//   · 任务 86/89 的人工结清审计展示块逐字保留，未改一个字。
// ★ 任务 98：本弹窗**只负责查看账单与审计**，不承担人工结清操作。
//   操作入口归位到魔流插件自己的「任务详情 → 种子明细」每颗种子的操作区
//   （SeedingTab.js），按 hash 精确关联；这里不提供任何改状态的按钮。
//   新增 append-only 事件历史时间线（结清 / 纠错重开 / 作废），展示
//   「谁、何时、凭哪份证据推翻了哪一次结清」，含原结清信息快照。
import { computed } from 'vue'
import {
  hrBillStateColor, hrBillsAtRisk, fmtHoursLeft, fmtBillSeeded, fmtBillLeft,
  hrBillLeftH,
} from '../../composables/useHrBills'

const open = defineModel({ type: Boolean, default: false })

const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh'])

const totals = computed(() => (props.data && props.data.totals) || {})

// ★ 19.12.34：「已结清」是**机器的记忆**，不是**人的待办**。
//   账本里必须留着 —— ① 幂等锚：防回填反复开账/结清；② 站端翻案（myhr 又说欠）时
//   settled → active 重开，保挂不中断。但它对使用者没有任何可执行信息，所以：
//   欠账视图只列「还欠着」的，settled/void 一律折进单独一行，到期由 TTL 自动销。
const OWED_STATES = ['active', 'breached']   // 真欠：在挂 && 已出事
const PENDING_STATES = ['pending']           // 未下完（完成才起算），★ 任务 96 起有独立明细区
const CLOSED_STATES = ['settled', 'void']
function openItems(s) { return (s.items || []).filter(it => OWED_STATES.includes(String(it.state || ''))) }
function closedItems(s) { return (s.items || []).filter(it => CLOSED_STATES.includes(String(it.state || ''))) }
// ★ 任务 96：pending 明细只认后端 pending_items（与后端逐颗同源），不把它归进 active/settled。
function pendingItems(s) {
  return (s.pending_items || []).filter(it => PENDING_STATES.includes(String(it.state || '')))
}
function pendingCountMismatch(s) {
  return Number((s.bills || {}).pending || 0) !== pendingItems(s).length
}
// ★ 任务 96：顶部列表数量必须与 API 统计一致，不一致要看得见，不许静默少显示。
const listTotal = computed(() => sites.value.reduce(
  (a, s) => a + Number((s.bills || {}).total || 0), 0))
const countsMismatch = computed(() => {
  const n = Number(totals.value.bills || 0)
  return n > 0 && n !== listTotal.value
})
function fmtH(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(1) + 'h' : '—'
}
function fmtProgress(it) {
  const p = Number(it && it.progress)
  if (!Number.isFinite(p) || p < 0) return '—'
  return Math.round(Math.min(1, Math.max(0, p)) * 100) + '%'
}
function hashShort(h) { return String(h || '').slice(0, 12) || '—' }
// ★ 19.12.45（任务 86 · P2 结清审计）：人工结清判定严格用 settlement_method === 'manual'
//   （不得由 settled 状态 / 操作人 / 原因推断）；auto / None / 历史无字段一律不算。
function isManualSettled(it) { return !!it && it.settlement_method === 'manual' }
function auditBlank(v) { return v == null || (typeof v === 'string' && !v.trim()) }
// ★ 19.12.46（任务 89）：操作人**不可信**判定 —— 缺失/空白，或是旧版 API 的占位串
//   'manual'（当年操作人没传就用它兜底落库）。占位串不是人名，绝不能当真实操作人展示，
//   也不能因为「非空」就让审计看起来完整。历史数据原样保留，前端只做展示层提示。
function auditByBad(v) {
  if (auditBlank(v)) return true
  return typeof v === 'string' && v.trim().toLowerCase() === 'manual'
}
// 结清时间：settled_at（epoch 秒）→ 本地可读「YYYY-MM-DD HH:mm」；无效/缺失 → '—'
function fmtSettleTime(v) {
  const n = Number(v)
  if (typeof v === 'boolean' || !Number.isFinite(n) || n <= 0) return '—'
  const d = new Date(n * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
// ★ 任务 102（审计可见性）：非 manual 的已结清 / 已作废行也要能看见结清轨迹。
//   口径是「只显示账单原值」：settlement_method 为空 = **未记录**，不是"自动"——
//   19.12.40 前 backfill / 迁移直接置 settled 的行本来就没有结清方式与操作人，
//   这里不得推断、不得补造。
function settleTagText(it) {
  const st = String((it && it.state) || '')
  const sm = String((it && it.settlement_method) || '')
  if (st === 'void') return '已作废'
  if (sm === 'manual') return '人工结清'
  if (sm === 'auto') return '自动结清'
  if (sm === 'reopened') return '纠错重开'
  // 无 settlement_method 不等于「没结清」，只等于「当时没记方式」——
  // 用中性标签，把事实（未记录）放到紧随其后的 kv 上，避免 51 行像告警刷屏。
  return '历史结清'
}
function settleMethodKnown(it) {
  return !!String((it && it.settlement_method) || '').trim()
}
// 有没有留下任何可用轨迹：后端 settlement_tracked=false 是权威否定；否则按字段推断
// （兼容未升级后端：老接口不返回该键，此时靠 settled_at 判断）。
function settleTracked(it) {
  if (!it) return false
  if (it.settlement_tracked === false) return false
  if (String(it.state || '') === 'void') {
    return Number(it.voided_at || 0) > 0 || !auditBlank(it.void_reason)
  }
  return Number(it.settled_at || 0) > 0
    || !auditBlank(it.settled_by) || !auditBlank(it.settlement_reason)
}
function settleTimeLabel(it) {
  if (String((it && it.state) || '') === 'void') {
    return '作废时间：' + fmtSettleTime(it && it.voided_at)
  }
  return '结清时间：' + fmtSettleTime(it && it.settled_at)
}
function openChips(b) {
  const out = {}
  for (const k of OWED_STATES.concat(PENDING_STATES)) {
    const n = Number((b || {})[k] || 0)
    if (n > 0) out[k] = n
  }
  return out
}
// 是否「真清干净」：欠的、待起表的都没有（settled/void 不算）
function openCount(s) {
  const b = (s && s.bills) || {}
  return OWED_STATES.concat(PENDING_STATES).reduce((a, k) => a + Number(b[k] || 0), 0)
}
// 未结清合计（顶部第一格）：账本总条数含历史结清，对使用者是噪音
const openTotal = computed(() => {
  const t = totals.value || {}
  return OWED_STATES.concat(PENDING_STATES).reduce((a, k) => a + Number(t[k] || 0), 0)
})
// 有欠的站排前面；全部结清的沉底（不是删，只是别占头部）
const sites = computed(() => {
  const arr = ((props.data && props.data.sites) || []).slice()
  const w = (s) => {
    const b = (s && s.bills) || {}
    return Number(b.breached || 0) * 10000 + Number(b.active || 0) * 100 + Number(b.pending || 0)
  }
  arr.sort((a, b) => w(b) - w(a))
  return arr
})

// ───────────────────────────── ★ 任务 98 · 结清/纠错历史时间线 ─────────────────────────────
// 后端 `view_hr` 只在**确有事件**时才往 item 注入 `history`（append-only
// `mf_bill_events`）。历史账单零事件 → 这里也零渲染，展示面与任务 96 逐字一致。
const EVENT_LABELS = {
  manual_settled: '人工结清',
  auto_settled: '自动结清',
  reopened: '站端证据纠错重开',
  manual_void: '人工作废',
  auto_void: '自动作废',
  legacy_manual_settled: '人工结清（历史账单补录）',
}
function eventLabel(e) {
  return EVENT_LABELS[String((e && e.event_type) || '')] || String((e && e.event_type) || '历史事件')
}
function historyOf(it) {
  return Array.isArray(it && it.history) ? it.history.filter(x => x && typeof x === 'object') : []
}
function eventTime(e) { return fmtSettleTime(e && e.at) }
function evidenceText(e) {
  const src = String((e && e.evidence_source) || '')
  const at = Number((e && e.evidence_at) || 0)
  if (!src && !(at > 0)) return ''
  return `证据：${src || '—'}${at > 0 ? ' @ ' + fmtSettleTime(at) : ''}`
}
// 重开事件里 `bill_snapshot` = 被推翻的那次结清的不可变副本。
function reopenedSnapshotText(e) {
  const s = (e && e.bill_snapshot) || {}
  const by = auditByBad(s.settled_by) ? '—' : s.settled_by
  return `原结清：${by} · ${fmtSettleTime(s.settled_at)} · ${auditBlank(s.settlement_reason) ? '—' : s.settlement_reason}`
}
</script>

<template>
  <VDialog v-model="open" max-width="48rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-hrbills-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">H&amp;R 账单 · 审计</span>
        <VChip v-if="loading" size="x-small" color="grey" variant="tonal">加载中</VChip>
        <VChip v-else-if="totals.breached" size="x-small" color="deep-orange" variant="tonal">{{ totals.breached }} 违约</VChip>
        <VChip v-if="totals.at_risk" size="x-small" color="warning" variant="tonal">{{ totals.at_risk }} 临近到期</VChip>
        <span class="magicflow-ops-dialog__spacer" />
        <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="loading" @click="emit('refresh')" />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>
      <div class="magicflow-ops-dialog__body">
        <!-- ★ 任务 104：这里原先有一对「无指令的 template 标签」包裹整块内容。
             Vue 编译器会把它的子节点整块丢弃 → 弹窗正文永远空白（标题栏正常，
             所以看着像"审计没内容"，实际连统计块和站点卡片都没渲染）。
             已删除包裹层，内容直接挂在 .magicflow-ops-dialog__body 下。
             勿再引入同类包裹：SSR 仍会把子节点输出成字符串，测不出这个洞。 -->
        <div class="magicflow-sitereport__stats">
          <div class="magicflow-sitereport__stat"><b>{{ openTotal }}</b><span>未结清</span></div>
          <div class="magicflow-sitereport__stat is-danger"><b>{{ totals.active || 0 }}</b><span>欠债</span></div>
          <div class="magicflow-sitereport__stat is-danger"><b>{{ totals.breached || 0 }}</b><span>违约</span></div>
          <div class="magicflow-sitereport__stat is-danger"><b>{{ totals.missing || 0 }}</b><span>本机缺失</span></div>
          <div class="magicflow-sitereport__stat" :class="totals.at_risk ? 'is-danger' : ''"><b>{{ totals.at_risk || 0 }}</b><span>临近到期</span></div>
          </div>
          <div v-if="countsMismatch" class="magicflow-hrbills__mismatch">
          接口统计 {{ totals.bills || 0 }} 张，站点列表合计 {{ listTotal }} 张，数量不一致 —— 请点刷新复核
          </div>
          <div v-if="!openTotal && sites.length" class="magicflow-hrbills__allclear">
          当前没有 H&amp;R 欠账 —— 下面 {{ sites.length }} 个站共 {{ totals.settled || 0 }} 颗已结清，到期自动清除
          </div>
          <div class="magicflow-hrbills__list">
          <div v-for="s in sites" :key="s.domain" class="magicflow-hrbills__card">
            <div class="magicflow-hrbills__head">
              <span class="magicflow-hrbills__name">{{ s.name || s.domain }}</span>
              <VChip v-if="s.per_torrent_hr" size="x-small" color="purple" variant="tonal">逐种</VChip>
              <VChip v-if="s.rule_source" size="x-small" color="grey" variant="tonal">{{ s.rule_source }}</VChip>
              <VChip v-if="!openCount(s)" size="x-small" color="success" variant="tonal">已结清</VChip>
              <span class="magicflow-ops-dialog__spacer" />
              <span class="magicflow-hrbills__nums">欠 {{ s.owed }} · 在qb {{ s.in_qb }} · 缺 {{ s.missing }}<template v-if="s.at_risk"> · ⚠临期 {{ s.at_risk }}</template></span>
              <VChip v-if="(s.bills || {}).pending" size="x-small" color="amber" variant="tonal">待起表 {{ s.bills.pending }}</VChip>
            </div>
            <div class="magicflow-hrbills__chips">
              <VChip
                v-for="(n, st) in openChips(s.bills)"
                :key="st"
                size="x-small"
                :color="hrBillStateColor(st)"
                variant="tonal"
              >{{ st }} {{ n }}</VChip>
              <VChip v-if="s.window_h" size="x-small" color="blue-grey" variant="tonal">窗口 {{ (s.window_h / 24).toFixed(1) }}d</VChip>
              <VChip v-if="s.bills && s.bills.settled" size="x-small" color="grey" variant="text">已结清 {{ s.bills.settled }}</VChip>
            </div>
            <details v-if="openItems(s).length" class="magicflow-hrbills__detail">
              <summary>还欠 {{ openItems(s).length }} 颗（逐颗）</summary>
              <div class="magicflow-hrbills__rows">
                <div v-for="it in openItems(s)" :key="it.hash" class="magicflow-hrbills__row">
                  <span class="magicflow-hrbills__row-title" :title="it.title || it.hash">{{ it.title || it.hash.slice(0, 8) }}</span>
                  <span class="magicflow-hrbills__row-seed">{{ fmtBillSeeded(it) }}</span>
                  <span class="magicflow-hrbills__row-left" :class="{ 'is-ok': hrBillLeftH(it) <= 0.05 }">{{ fmtBillLeft(it) }}</span>
                  <!-- ★ 任务 98：结清 / 纠错历史（只查看，不提供任何改状态入口） -->
                  <details v-if="historyOf(it).length" class="magicflow-hrbills__history">
                    <summary>结清 / 纠错历史 {{ historyOf(it).length }} 条</summary>
                    <div v-for="(e, i) in historyOf(it)" :key="i" class="magicflow-hrbills__history-row">
                      <span class="magicflow-hrbills__history-tag">{{ eventLabel(e) }}</span>
                      <span>{{ eventTime(e) }}</span>
                      <span>操作人：{{ e.actor || '—' }}</span>
                      <span v-if="e.reason">原因：{{ e.reason }}</span>
                      <span v-if="evidenceText(e)">{{ evidenceText(e) }}</span>
                      <span v-if="e.event_type === 'reopened'">{{ reopenedSnapshotText(e) }}</span>
                    </div>
                  </details>
                </div>
              </div>
            </details>
            <!-- ★ 19.12.48（任务 96）：pending 独立明细区（默认展开）。
                 既不归 active 也不归 settled；数量以 s.bills.pending 为准，不一致时显式提示。 -->
            <details v-if="pendingItems(s).length" open class="magicflow-hrbills__detail magicflow-hrbills__detail--pending">
              <summary>待起表 {{ pendingItems(s).length }} 颗（未下完，完成即计 H&amp;R）</summary>
              <div v-if="pendingCountMismatch(s)" class="magicflow-hrbills__mismatch">
                接口统计 {{ (s.bills || {}).pending || 0 }} 颗，明细 {{ pendingItems(s).length }} 颗，数量不一致 —— 请点刷新复核
              </div>
              <div class="magicflow-hrbills__prows">
                <div v-for="it in pendingItems(s)" :key="it.hash" class="magicflow-hrbills__prow">
                  <div class="magicflow-hrbills__prow-title" :title="it.title || it.hash">{{ it.title || hashShort(it.hash) }}</div>
                  <div class="magicflow-hrbills__pmeta">
                    <span>站点：{{ s.name || s.domain }}</span>
                    <span>规则：{{ it.rule || '—' }}</span>
                    <span>状态：<b>{{ it.state || '—' }}</b></span>
                    <span>需做种：{{ fmtH(it.need_h) }}</span>
                    <span>已做种：{{ fmtH(it.seeded_h) }}</span>
                    <span>进度：{{ fmtProgress(it) }}</span>
                    <span class="magicflow-hrbills__phash" :title="it.hash">hash：{{ it.hash }}</span>
                  </div>
                  <!-- ★ 任务 98：结清 / 纠错历史（只查看，不提供任何改状态入口） -->
                  <details v-if="historyOf(it).length" class="magicflow-hrbills__history">
                    <summary>结清 / 纠错历史 {{ historyOf(it).length }} 条</summary>
                    <div v-for="(e, i) in historyOf(it)" :key="i" class="magicflow-hrbills__history-row">
                      <span class="magicflow-hrbills__history-tag">{{ eventLabel(e) }}</span>
                      <span>{{ eventTime(e) }}</span>
                      <span>操作人：{{ e.actor || '—' }}</span>
                      <span v-if="e.reason">原因：{{ e.reason }}</span>
                      <span v-if="evidenceText(e)">{{ evidenceText(e) }}</span>
                      <span v-if="e.event_type === 'reopened'">{{ reopenedSnapshotText(e) }}</span>
                    </div>
                  </details>
                </div>
              </div>
            </details>
            <details v-if="closedItems(s).length" class="magicflow-hrbills__detail magicflow-hrbills__detail--done">
              <summary>已结清 {{ closedItems(s).length }} 颗（到期自动清除，无需操作）</summary>
              <div class="magicflow-hrbills__rows">
                <div v-for="it in closedItems(s)" :key="it.hash" class="magicflow-hrbills__row">
                  <span class="magicflow-hrbills__row-title" :title="it.title || it.hash">{{ it.title || it.hash.slice(0, 8) }}</span>
                  <span class="magicflow-hrbills__row-seed">{{ fmtBillSeeded(it) }}</span>
                  <span class="magicflow-hrbills__row-left is-ok">{{ fmtBillLeft(it) }}</span>
                  <!-- ★ 19.12.45（任务 86）：人工结清审计块 —— 仅 manual 显示；
                       manual 是唯一承诺「四列齐全」的路径，故独占「需人工复核」。 -->
                  <div v-if="isManualSettled(it)" class="magicflow-hrbills__audit">
                    <span class="magicflow-hrbills__audit-tag">人工结清</span>
                    <span class="magicflow-hrbills__audit-kv">操作人：{{ auditByBad(it.settled_by) ? '—' : it.settled_by }}</span>
                    <span class="magicflow-hrbills__audit-kv">原因：{{ auditBlank(it.settlement_reason) ? '—' : it.settlement_reason }}</span>
                    <span class="magicflow-hrbills__audit-kv">结清时间：{{ fmtSettleTime(it.settled_at) }}</span>
                    <span class="magicflow-hrbills__audit-review">需人工复核</span>
                    <span v-if="it.settlement_audit_incomplete" class="magicflow-hrbills__audit-warn">审计信息不完整，请人工核查</span>
                  </div>
                  <!-- ★ 任务 102（审计可见性）：非 manual 的已结清 / 已作废行也给轨迹。
                       这一批历史账单（19.12.40 前 backfill/迁移直接置 settled）本来就没有
                       操作人与原因 —— 这里**只显示原值 + 说明**，不补造任何信息。 -->
                  <div v-else class="magicflow-hrbills__audit">
                    <span class="magicflow-hrbills__audit-tag">{{ settleTagText(it) }}</span>
                    <span v-if="!settleMethodKnown(it)" class="magicflow-hrbills__audit-kv">方式未记录</span>
                    <span class="magicflow-hrbills__audit-kv">{{ settleTimeLabel(it) }}</span>
                    <span v-if="!auditByBad(it.settled_by)" class="magicflow-hrbills__audit-kv">操作人：{{ it.settled_by }}</span>
                    <span v-if="!auditBlank(it.settlement_reason)" class="magicflow-hrbills__audit-kv">原因：{{ it.settlement_reason }}</span>
                    <span v-if="!auditBlank(it.void_reason)" class="magicflow-hrbills__audit-kv">作废原因：{{ it.void_reason }}</span>
                    <span v-if="!settleTracked(it)" class="magicflow-hrbills__audit-warn">该账单未留下结清记录（19.12.40 前结清，事件表尚未启用）</span>
                  </div>
                  <details v-if="historyOf(it).length" class="magicflow-hrbills__history">
                    <summary>结清 / 纠错历史 {{ historyOf(it).length }} 条</summary>
                    <div v-for="(e, i) in historyOf(it)" :key="i" class="magicflow-hrbills__history-row">
                      <span class="magicflow-hrbills__history-tag">{{ eventLabel(e) }}</span>
                      <span>{{ eventTime(e) }}</span>
                      <span>操作人：{{ e.actor || '—' }}</span>
                      <span v-if="e.reason">原因：{{ e.reason }}</span>
                      <span v-if="evidenceText(e)">{{ evidenceText(e) }}</span>
                      <span v-if="e.event_type === 'reopened'">{{ reopenedSnapshotText(e) }}</span>
                    </div>
                  </details>
                </div>
              </div>
            </details>
            <div v-if="s.at_risk" class="magicflow-ops-dialog__sub">
              临近到期：
              <span v-for="(it, i) in hrBillsAtRisk(s)" :key="it.hash">{{ i ? '、' : '' }}{{ it.title || it.hash.slice(0, 8) }}（站点窗口剩 {{ fmtHoursLeft(it.hours_left, it.state) }} · 需 {{ it.due_h }}h）</span>
            </div>
          </div>
          <div v-if="!loading && !sites.length" class="magicflow-ceiling-empty">暂无 H&amp;R 账单（无欠债站）</div>
        </div>
      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 正文：随「H&R 账单弹窗」自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head·__title / ops-dialog__spacer·__body·__sub /
     sitereport__stats·__stat / ceiling-empty）父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。── */
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
.magicflow-ceiling-empty { font-size: 12.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); text-align: center; padding: 20px 0; }
.magicflow-sitereport__stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-block-end: 10px; }
.magicflow-sitereport__stat { background: rgba(var(--v-theme-on-surface), 0.04); border-radius: 10px; padding: 8px 10px; text-align: center; }
.magicflow-sitereport__stat b { display: block; font-size: 20px; font-weight: 700; line-height: 1.15; }
.magicflow-sitereport__stat span { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__stat.is-danger b { color: rgb(var(--v-theme-error)); }

/* ── 按站卡片：这几条样式在 P4 拆分时**丢了**（template 有类名、全库无 CSS），
   结果所有站的内容糊成一片、卡片之间没有边界。19.10.11 补齐。── */
.magicflow-hrbills__list { display: flex; flex-direction: column; gap: 10px; }
/* ★ 19.12.34：全清时先给一句结论，别让人逐卡去数 */
.magicflow-hrbills__allclear {
  margin-block-end: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 12px;
  color: rgb(var(--v-theme-success));
  background: rgba(var(--v-theme-success), 0.08);
  border: 1px solid rgba(var(--v-theme-success), 0.22);
}
.magicflow-hrbills__mismatch {
  margin-block-end: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 11.5px;
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.08);
  border: 1px solid rgba(var(--v-theme-error), 0.25);
}
.magicflow-hrbills__card {
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 12px;
  padding: 10px 12px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}
.magicflow-hrbills__head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.magicflow-hrbills__name { font-size: 13.5px; font-weight: 600; }
.magicflow-hrbills__nums { font-size: 11.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-hrbills__chips { display: flex; flex-wrap: wrap; gap: 6px; margin-block-start: 6px; }

/* ── 逐颗明细（19.10.11）：可折叠，默认收起，避免把弹窗堆爆 ── */
.magicflow-hrbills__detail { margin-block-start: 8px; }
.magicflow-hrbills__detail > summary {
  cursor: pointer;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  user-select: none;
}
.magicflow-hrbills__rows { display: flex; flex-direction: column; gap: 2px; margin-block-start: 6px; }
/* ★ 19.12.34：已结清那一组视觉上退到次要（是历史，不是待办） */
.magicflow-hrbills__detail--done > summary { opacity: 0.72; }
.magicflow-hrbills__detail--done .magicflow-hrbills__row-title { color: rgba(var(--v-theme-on-surface), 0.6); }
/* ★ 19.12.48：待起表独立明细（默认展开，浅琥珀底与「已结清」区分） */
.magicflow-hrbills__detail--pending > summary { color: rgb(var(--v-theme-warning)); font-weight: 600; }
.magicflow-hrbills__prows { display: flex; flex-direction: column; gap: 6px; margin-block-start: 6px; }
.magicflow-hrbills__prow {
  position: relative;
  padding: 7px 9px;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-theme-warning), 0.24);
  background: rgba(var(--v-theme-warning), 0.05);
  font-size: 11.5px;
}
.magicflow-hrbills__prow-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  padding-inline-end: 88px;
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.magicflow-hrbills__pmeta { display: flex; flex-wrap: wrap; gap: 2px 12px; margin-block-start: 4px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-hrbills__phash { word-break: break-all; }
.magicflow-hrbills__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 11.5px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
.magicflow-hrbills__row-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.86);
}
.magicflow-hrbills__row-seed { font-variant-numeric: tabular-nums; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-hrbills__row-left { font-variant-numeric: tabular-nums; color: rgb(var(--v-theme-warning)); white-space: nowrap; }
.magicflow-hrbills__row-left.is-ok { color: rgb(var(--v-theme-success)); }
/* ── ★ 任务 98：结清 / 纠错历史时间线（只查看，替代原人工结清按钮位置） ──
   在 grid 行里占满整行、默认收起；零事件账单完全不渲染，原三列布局不变。 */
.magicflow-hrbills__history {
  grid-column: 1 / -1;
  margin-block: 2px 4px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}
.magicflow-hrbills__history > summary { cursor: pointer; font-weight: 600; }
.magicflow-hrbills__history-row {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 10px;
  padding: 4px 0 4px 8px;
  margin-block-start: 3px;
  border-inline-start: 2px solid rgba(var(--v-theme-primary), 0.45);
}
.magicflow-hrbills__history-tag { font-weight: 700; color: rgb(var(--v-theme-primary)); }

/* ── ★ 19.12.45（任务 86 · P2 结清审计）：人工结清审计块。
     网格里占满整行（grid-column: 1 / -1），不动原有三列布局；
     标签与「需人工复核」用胶囊底色保证醒目，审计不完整警告用加粗错误色。── */
.magicflow-hrbills__audit {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  padding: 2px 0 4px;
  font-size: 11px;
}
.magicflow-hrbills__audit-tag {
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 600;
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.1);
  border: 1px solid rgba(var(--v-theme-error), 0.35);
}
.magicflow-hrbills__audit-kv {
  color: rgba(var(--v-theme-on-surface), 0.72);
  word-break: break-all;
}
.magicflow-hrbills__audit-review {
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 600;
  color: rgb(var(--v-theme-warning));
  background: rgba(var(--v-theme-warning), 0.12);
  border: 1px solid rgba(var(--v-theme-warning), 0.4);
}
.magicflow-hrbills__audit-warn {
  font-weight: 700;
  color: rgb(var(--v-theme-error));
}

@media (max-width: 959px) {
  .magicflow-sitereport__stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 959px) {
  .magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}
/* 窄屏：种子名独占一行，工时/还需 并到第二行，避免三列挤成省略号 */
@media (max-width: 520px) {
  .magicflow-hrbills__row {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: "t t" "s l";
    row-gap: 0;
  }
  .magicflow-hrbills__row-title { grid-area: t; }
  .magicflow-hrbills__row-seed { grid-area: s; }
  .magicflow-hrbills__row-left { grid-area: l; }
  .magicflow-hrbills__history { grid-column: 1 / -1; }
  .magicflow-hrbills__prow-title { padding-inline-end: 0; }
  .magicflow-hrbills__prow > .magicflow-hrbills__history { margin-block-start: 6px; }
}
</style>
