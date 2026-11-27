<script setup>
// MagicFlow 前端 · 站点报表弹窗（11.10.0）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（siteReportBucketColor / siteReportItemSub / siteReportTransportCount）自
// composables/useSiteReport.js 具名导入复用 —— 单一真值源，不在两处各写一份。
import {
  siteReportBucketColor,
  siteReportItemParts,
  siteReportItemSub,
  siteReportTitleParts,
  siteReportTransportCount,
} from '../../composables/useSiteReport'
import { computed, ref } from 'vue'
import { formatBytes } from '../../../../utils'
import { currencyOf } from '../../composables/useCurrency'
import { levelNextText } from '../../format'
import {
  SITE_REPORT_BUCKETS,
  SITE_REPORT_TRANSPORT,
  SITE_REPORT_SILENT_SUBS,
  SITE_REPORT_ORIGINS,
} from '../../constants'

const open = defineModel({ type: Boolean, default: false })
const site = defineModel('site', { type: String, default: '' })
const filter = defineModel('filter', { type: String, default: '' })
const transport = defineModel('transport', { type: String, default: '' })
const sub = defineModel('sub', { type: String, default: '' })
const origin = defineModel('origin', { type: String, default: '' })

const props = defineProps({
  loading: { type: Boolean, default: false },
  live: { type: Boolean, default: false },
  liveLoading: { type: Boolean, default: false },
  liveStats: { type: Object, default: () => null },
  report: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  items: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
  siteBonus: { type: Number, default: null },
  siteCurrency: { type: String, default: '' },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh', 'live', 'change'])

// ★ 15.16.0 站点流量块：展示用格式化（分享率 2 位 / 字节→G / 数字千分位）
const liveRatio = computed(() => {
  const s = props.liveStats || {}
  if (s.ratio_inf) return '∞'   // ★ 15.16.1：站点下载=0 → 页面显示「无限」，照实呈现
  const v = s.ratio
  return v === null || v === undefined ? '—' : Number(v).toFixed(2)
})
function liveGb(bytes) {
  const n = Number(bytes || 0)
  if (!n) return '0'
  return `${(n / 1024 / 1024 / 1024).toFixed(1)}G`
}
function liveNum(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  return Number.isFinite(n) ? (Math.round(n * 10) / 10).toLocaleString('en-US') : '—'
}

// ★ 19.16.8：与生效 .js 同步的计算（源码一致性保险；实际构建走 SiteReportDialog.js）
const bonusPerHour = computed(() => {
  if (props.siteBonus != null) return props.siteBonus
  const s = props.liveStats || {}
  return s.bonus_per_hour == null ? null : s.bonus_per_hour
})
const currencyName = computed(() => currencyOf(props.siteCurrency))
const bonusPerHourHint = computed(() => {
  if (props.siteBonus != null) return '站点上报时魔（与任务详情同一口径）'
  const s = props.liveStats || {}
  if (s.bonus_per_hour_source === 'observed') return '本地采样折算（该站未提供时魔接口），不是站点自报值'
  return ''
})
const levelName = computed(() => (props.liveStats || {}).level || '未知')
const levelNextName = computed(() => ((props.liveStats || {}).level_next || {}).name || '—')
const levelGapText = computed(() => levelNextText((props.liveStats || {}).level_next, currencyName.value))

// ★ 19.16.8 升级条件清单（AND 多条件逐条达标，替代单条进度条）
const LV_LABELS = {
  interval: '入站时长', downloaded: '下载量', uploaded: '上传量',
  trueDownloaded: '下载量', trueUploaded: '上传量', ratio: '分享率', trueRatio: '分享率',
  seedingSize: '做种体积', totalTraffic: '总流量', seedingBonus: '做种积分',
  bonus: '魔力', seeding: '做种数', snatches: '完成数', uploads: '发布数', posts: '发帖数',
}
const LV_ORDER = ['interval', 'downloaded', 'trueDownloaded', 'uploaded', 'trueUploaded', 'ratio', 'trueRatio', 'seedingSize', 'totalTraffic', 'seedingBonus', 'bonus', 'seeding', 'snatches', 'uploads', 'posts']
const LV_BYTES = new Set(['downloaded', 'trueDownloaded', 'uploaded', 'trueUploaded', 'seedingSize', 'totalTraffic'])
function lvTargetText(k, v) {
  if (k === 'interval') {
    const w = String(v || '').match(/P(\d+)W/); const d = String(v || '').match(/P(\d+)D/)
    if (w) return '满 ' + w[1] + ' 周'
    if (d) return '满 ' + d[1] + ' 天'
    return String(v || '')
  }
  if (k === 'ratio' || k === 'trueRatio') return '≥' + Number(v).toFixed(2)
  if (LV_BYTES.has(k)) return '≥' + String(v || '')
  const n = Number(v)
  return Number.isFinite(n) ? '≥' + n.toLocaleString('en-US') : String(v ?? '')
}
function lvGapText(k, gap, cur) {
  if (LV_BYTES.has(k)) return '还差 ' + formatBytes(gap)
  if (k === 'ratio' || k === 'trueRatio') {
    const c = Number(cur)
    return Number.isFinite(c) ? '当前 ' + c.toFixed(2) + ' · 需 ≥' + Number(gap).toFixed(2) : '需 ≥' + Number(gap).toFixed(2)
  }
  if (k === 'interval') {
    const days = Math.ceil(Number(gap) / 86400)
    return '还需 ' + (days > 0 ? days : 1) + ' 天'
  }
  const n = Number(gap)
  return '还差 ' + (Number.isFinite(n) ? Math.round(n).toLocaleString('en-US') : String(gap))
}
const levelConditions = computed(() => {
  const n = (props.liveStats || {}).level_next
  const s = props.liveStats || {}
  if (!n || !n.req || !n.unmet) return null
  const req = n.req, un = n.unmet || {}, unk = new Set(n.unknown || [])
  const rows = []
  for (const k of LV_ORDER) {
    if (!(k in req)) continue
    if (unk.has(k)) { rows.push({ key: k, label: LV_LABELS[k] || k, state: 'unknown', detail: '未知' }); continue }
    if (un[k] != null) {
      // ★ 19.16.9 修复：ratio 不是字节类，之前塞在 LV_BYTES 三元里永远拿不到 → "当前 0.00"
      const cur = (k === 'ratio' || k === 'trueRatio') ? s.ratio : LV_BYTES.has(k) ? s.download : null
      rows.push({ key: k, label: LV_LABELS[k] || k, state: 'miss', detail: lvGapText(k, un[k], cur) })
    } else {
      rows.push({ key: k, label: LV_LABELS[k] || k, state: 'ok', detail: lvTargetText(k, req[k]) })
    }
  }
  if (!rows.length) return null
  return { rows, met: rows.filter(r => r.state === 'ok').length, total: rows.length, name: n.name || '' }
})
const hrOwedDanger = computed(() => Number((props.summary || {}).hr_owed || 0) > 0)
const hrMissingDanger = computed(() => Number((props.summary || {}).hr_missing || 0) > 0)
const origOpen = ref({})
function toggleOrig(h) { origOpen.value = { ...origOpen.value, [h]: !origOpen.value[h] } }
</script>

<template>
  <VDialog v-model="open" max-width="48rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-sitereport-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">站点报表</span>
        <VChip v-if="loading" size="x-small" color="grey" variant="tonal">加载中</VChip>
        <span class="magicflow-ops-dialog__spacer" />
        <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="loading" @click="emit('refresh')" />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>
      <div class="magicflow-ops-dialog__sub magicflow-sitereport__bar">
        <VSelect
          v-model="site"
          :items="sites.map(s => ({ title: `${s.name || s.domain}${s.domain ? ' · ' + s.domain : ''}`, value: s.domain || s.name }))"
          density="compact"
          variant="outlined"
          hide-details
          class="magicflow-sitereport__site"
          @update:model-value="emit('change')"
        />
      </div>
      <div class="magicflow-ops-dialog__body">
        <div class="magicflow-sitereport__live">
          <div class="magicflow-sitereport__live-head">
            <span class="magicflow-sitereport__live-t">账号概览</span>
            <VChip v-if="liveLoading" size="x-small" color="grey" variant="tonal">加载中</VChip>
            <template v-else-if="liveStats">
              <VChip size="x-small" :color="liveStats.logged_in ? 'success' : 'warning'" variant="tonal">{{ liveStats.logged_in ? '已登录' : '未登录' }}</VChip>
              <span v-if="liveStats.uid" class="magicflow-sitereport__live-uid">UID {{ liveStats.uid }}</span>
            </template>
          </div>
          <div v-if="liveStats && liveStats.ok" class="magicflow-sitereport__live-body">
            <div class="magicflow-sitereport__live-grid">
              <div class="magicflow-sitereport__live-cell"><b>{{ liveRatio }}</b><span>分享率</span></div>
              <div class="magicflow-sitereport__live-cell"><b>{{ liveGb(liveStats.upload) }}</b><span>上传</span></div>
              <div class="magicflow-sitereport__live-cell"><b>{{ liveGb(liveStats.download) }}</b><span>下载</span></div>
              <div class="magicflow-sitereport__live-cell"><b>{{ liveNum(liveStats.bonus) }}</b><span>魔力值</span></div>
            </div>
            <div class="magicflow-sitereport__live-minor">
              <span>做种 {{ liveNum(liveStats.seeding) }}</span>
              <span :title="bonusPerHourHint">{{ currencyName }}/时 {{ liveNum(bonusPerHour) }}</span>
              <span :title="liveStats.level || '站点未报等级'">等级 {{ levelName }}</span>
            </div>
          </div>
          <!-- ★ 19.16.8 升级条件清单：AND 多条件逐条达标，替代单条进度条 -->
          <div v-if="levelConditions" class="magicflow-sitereport__reqs">
            <div class="magicflow-sitereport__reqs-top">
              <span class="magicflow-sitereport__reqs-name">升级 {{ levelConditions.name || levelNextName }}</span>
              <span class="magicflow-sitereport__reqs-count">满足 {{ levelConditions.met }} / {{ levelConditions.total }}</span>
            </div>
            <div v-for="row in levelConditions.rows" :key="row.key" class="magicflow-sitereport__reqs-row" :class="'is-' + row.state">
              <span class="magicflow-sitereport__reqs-mark">{{ row.state === 'ok' ? '✓' : (row.state === 'miss' ? '✕' : '?') }}</span>
              <span class="magicflow-sitereport__reqs-label">{{ row.label }}</span>
              <span class="magicflow-sitereport__reqs-detail">{{ row.detail }}</span>
            </div>
          </div>
          <div v-else-if="levelGapText" class="magicflow-sitereport__live-gap">距 {{ levelNextName }}：{{ levelGapText }}</div>
          <div v-else-if="!liveLoading && liveStats && liveStats.warming" class="magicflow-sitereport__live-empty">取数中…（实时数据正在后台补齐，稍候自动刷新）</div>
          <div v-else-if="!liveLoading" class="magicflow-sitereport__live-empty">暂无实时账号数据（站点未登录或取数失败）</div>
        </div>
        <div class="magicflow-sitereport__stats">
          <div class="magicflow-sitereport__stat" title="该站点在本机下载器里的全部种（做种/下载/暂停/静默）"><b>{{ summary.total || 0 }} <small>种</small></b><span>本站收录</span></div>
          <div class="magicflow-sitereport__stat"><b>{{ (summary.size_gb || 0).toFixed(1) }} <small>GB</small></b><span>种子总容量</span></div>
          <div class="magicflow-sitereport__stat" :class="hrOwedDanger ? 'is-danger' : 'is-ok'"><b>{{ summary.hr_owed || 0 }}</b><span v-if="hrOwedDanger">欠 H&amp;R</span><span v-else>✓ 欠 H&amp;R · 无欠款</span></div>
          <div class="magicflow-sitereport__stat" :class="hrMissingDanger ? 'is-danger' : 'is-ok'"><b>{{ summary.hr_missing || 0 }}</b><span v-if="hrMissingDanger">本机缺失</span><span v-else>✓ 本机缺失 · 文件齐全</span></div>
        </div>
        <div class="magicflow-sitereport__fgroup">
          <span class="magicflow-sitereport__chip-label">用途</span>
          <div class="magicflow-sitereport__chips">
          <VChip
            size="small"
            :color="filter ? 'grey' : 'primary'"
            :variant="filter ? 'tonal' : 'flat'"
            style="cursor: pointer"
            @click="filter = ''"
          >全部 {{ summary.total || 0 }}</VChip>
          <VChip
            v-for="b in SITE_REPORT_BUCKETS"
            :key="b.key"
            size="small"
            :color="b.color"
            :variant="filter === b.key ? 'flat' : 'tonal'"
            style="cursor: pointer"
            @click="filter = filter === b.key ? '' : b.key"
          >{{ b.key }} {{ (summary.by_bucket || {})[b.key] || 0 }}</VChip>
          </div>
        </div>
        <div class="magicflow-sitereport__fgroup magicflow-sitereport__chips--l2">
          <span class="magicflow-sitereport__chip-label">传输状态</span>
          <div class="magicflow-sitereport__chips">
          <VChip
            size="small"
            :color="transport ? 'grey' : 'primary'"
            :variant="transport ? 'tonal' : 'flat'"
            style="cursor: pointer"
            @click="transport = ''"
          >全部</VChip>
          <VChip
            v-for="tr in SITE_REPORT_TRANSPORT"
            :key="tr.key"
            size="small"
            :color="tr.color"
            :variant="transport === tr.key ? 'flat' : 'tonal'"
            style="cursor: pointer"
            @click="transport = transport === tr.key ? '' : tr.key"
          >{{ tr.key }} {{ siteReportTransportCount(tr.key, summary, filter) }}</VChip>
          </div>
        </div>
        <div v-if="filter === '静默'" class="magicflow-sitereport__chips magicflow-sitereport__chips--l2">
          <span class="magicflow-sitereport__chip-label">身份</span>
          <VChip
            size="small"
            :color="sub ? 'grey' : 'primary'"
            :variant="sub ? 'tonal' : 'flat'"
            style="cursor: pointer"
            @click="sub = ''"
          >全部</VChip>
          <VChip
            v-for="s in SITE_REPORT_SILENT_SUBS"
            :key="s.key"
            size="small"
            :color="s.color"
            :variant="sub === s.key ? 'flat' : 'tonal'"
            style="cursor: pointer"
            @click="sub = sub === s.key ? '' : s.key"
          >{{ s.key }} {{ (summary.silent_by_sub || {})[s.key] || 0 }}</VChip>
        </div>
        <div v-if="filter === '静默'" class="magicflow-sitereport__chips magicflow-sitereport__chips--l2">
          <span class="magicflow-sitereport__chip-label">出身</span>
          <VChip
            size="small"
            :color="origin ? 'grey' : 'primary'"
            :variant="origin ? 'tonal' : 'flat'"
            style="cursor: pointer"
            @click="origin = ''"
          >全部</VChip>
          <VChip
            v-for="s in SITE_REPORT_ORIGINS"
            :key="s.key"
            size="small"
            :color="s.color"
            :variant="origin === s.key ? 'flat' : 'tonal'"
            style="cursor: pointer"
            @click="origin = origin === s.key ? '' : s.key"
          >{{ s.key }} {{ (summary.silent_origin || {})[s.key] || 0 }}</VChip>
        </div>
        <div class="magicflow-sitereport__detail">
          明细 {{ items.length }} / {{ summary.total || 0 }}{{ (filter || transport || sub || origin) ? ' · 已筛选' : ' · 点分类可筛选' }}
        </div>
        <div v-if="report.hr && report.hr.error" class="magicflow-sitereport__err">
          H&amp;R 对账（{{ report.hr.source }}）：{{ report.hr.error }}
        </div>
        <div v-else-if="report.hr && report.hr.records_total != null" class="magicflow-sitereport__note">
          H&amp;R 对账（{{ report.hr.source }}）：站点欠 {{ report.hr.records_total }} 条，本机缺失 {{ report.hr.missing }} 条{{ report.hr.hash_coverage_complete ? '' : '（部分未覆盖）' }}
        </div>
        <div class="magicflow-sitereport__list">
          <div v-for="it in items" :key="it.hash" class="magicflow-sitereport__row">
            <VChip size="x-small" :color="siteReportBucketColor(it.bucket)" variant="tonal" class="magicflow-sitereport__row-b">{{ it.bucket }}</VChip>
            <div class="magicflow-sitereport__row-main">
              <div class="magicflow-sitereport__row-t" :title="siteReportTitleParts(it.title || it.hash).main">{{ siteReportTitleParts(it.title || it.hash).main || it.hash }}</div>
              <div class="magicflow-sitereport__row-s">
                <span v-for="(pt, pi) in siteReportItemParts(it)" :key="pi" :class="{ 'magicflow-sitereport__stall': pt.stall }">{{ (pi ? ' · ' : '') + pt.t }}</span>
              </div>
              <div
                v-if="siteReportTitleParts(it.title || it.hash).orig"
                class="magicflow-sitereport__row-orig"
                :class="origOpen[it.hash] ? 'is-open' : ''"
                @click="toggleOrig(it.hash)"
              >原名 <span>{{ siteReportTitleParts(it.title || it.hash).orig }}</span></div>
            </div>
            <span class="magicflow-sitereport__row-size">{{ (it.size_gb || 0).toFixed(2) }}G</span>
          </div>
          <div v-if="!loading && !items.length" class="magicflow-ceiling-empty">该站点暂无种子（或未选择站点）</div>
        </div>
      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 正文：随「站点报表弹窗」自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head·__title /
     ops-dialog__spacer·__sub·__body / ceiling-empty）父页其它弹窗也在用
     → 两处各留一份（纯复制，零改动）。VDialog 会 teleport，父 scoped 够不到子内部，故须自带。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
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

/* ── 站点报表（11.10.0）：站点级逐条种子状态（专属选择器，随弹窗迁入）── */
.magicflow-sitereport__bar { display: flex; align-items: center; gap: 10px; }
.magicflow-sitereport__site { flex: 1 1 auto; max-width: 22rem; }
.magicflow-sitereport__stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-block-end: 10px; }
/* ★ 15.16.0 站点流量块（弹窗顶部）：账号实时数据（比例/上传/下载/魔力/做种）── */
.magicflow-sitereport__live { background: rgba(var(--v-theme-primary), 0.06); border: 1px solid rgba(var(--v-theme-primary), 0.18); border-radius: 10px; padding: 8px 10px; margin-block-end: 10px; }
.magicflow-sitereport__live-head { display: flex; align-items: center; gap: 8px; margin-block-end: 6px; }
.magicflow-sitereport__live-t { font-size: 12.5px; font-weight: 600; }
.magicflow-sitereport__live-uid { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__live-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
.magicflow-sitereport__live-cell { text-align: center; min-width: 0; }
.magicflow-sitereport__live-cell b { display: block; font-size: 14px; font-weight: 700; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-sitereport__live-cell span { font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__live-minor { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-block-start: 9px; padding-block-start: 8px; border-top: 1px solid rgba(var(--v-theme-on-surface), .075); font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__live-minor span { white-space: nowrap; }
.magicflow-sitereport__live-empty { font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__stat { background: rgba(var(--v-theme-on-surface), 0.04); border-radius: 10px; padding: 8px 10px; text-align: center; }
.magicflow-sitereport__stat b { display: block; font-size: 20px; font-weight: 700; line-height: 1.15; }
.magicflow-sitereport__stat span { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__stat.is-danger b { color: rgb(var(--v-theme-error)); }
/* ★ 19.16.7 概览单位 + 健康值语义 */
.magicflow-sitereport__stat small { font-size: 11px; font-weight: 500; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__stat.is-ok span { color: rgb(var(--v-theme-success, 61, 220, 151)); }
/* ★ 19.16.8 升级条件清单 */
.magicflow-sitereport__reqs { margin-block-start: 9px; background: rgba(240, 182, 76, .06); border: 1px solid rgba(240, 182, 76, .2); border-radius: 10px; padding: 9px 11px; }
.magicflow-sitereport__reqs-top { display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; margin-block-end: 5px; }
.magicflow-sitereport__reqs-name { font-weight: 600; }
.magicflow-sitereport__reqs-count { color: rgb(240, 182, 76); font-weight: 600; }
.magicflow-sitereport__reqs-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; padding: 5px 0; border-top: 1px solid rgba(var(--v-theme-on-surface), .06); }
.magicflow-sitereport__reqs-mark { flex: 0 0 14px; width: 14px; text-align: center; font-weight: 700; }
.magicflow-sitereport__reqs-label { flex: 1 1 auto; color: rgba(var(--v-theme-on-surface), .8); }
.magicflow-sitereport__reqs-detail { flex: 0 0 auto; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__reqs-row.is-ok .magicflow-sitereport__reqs-mark { color: rgb(var(--v-theme-success, 61, 220, 151)); }
.magicflow-sitereport__reqs-row.is-miss .magicflow-sitereport__reqs-mark,
.magicflow-sitereport__reqs-row.is-miss .magicflow-sitereport__reqs-detail { color: rgb(var(--v-theme-error, 255, 107, 122)); font-weight: 600; }
.magicflow-sitereport__reqs-row.is-unknown .magicflow-sitereport__reqs-mark { color: rgba(var(--v-theme-on-surface), .45); }
/* ★ 19.16.8 筛选 chip 8px 小圆角 */
.magicflow-sitereport__chips .v-chip { border-radius: 8px !important; }
/* ★ 19.16.7 筛选分组 */
.magicflow-sitereport__fgroup { margin-block-end: 10px; }
.magicflow-sitereport__fgroup .magicflow-sitereport__chip-label { display: block; font-size: 10.5px; letter-spacing: .5px; margin: 0 0 6px 2px; color: rgba(var(--v-theme-on-surface), .42); }
.magicflow-sitereport__fgroup.magicflow-sitereport__chips--l2 { margin-block-end: 8px; }
/* ★ 19.16.7 明细原名折叠 */
.magicflow-sitereport__row-orig { font-size: 10px; color: rgba(var(--v-theme-on-surface), .42); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; user-select: none; margin-block-start: 2px; }
.magicflow-sitereport__row-orig:hover { color: rgba(var(--v-theme-on-surface), .62); }
.magicflow-sitereport__row-orig.is-open { white-space: normal; overflow: visible; text-overflow: clip; color: rgba(var(--v-theme-on-surface), .58); }
.magicflow-sitereport__chips { display: flex; flex-wrap: wrap; gap: 6px; margin-block-end: 10px; }
.magicflow-sitereport__chips--l2 { margin-block-end: 8px; }
.magicflow-sitereport__chip-label { align-self: center; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-inline-end: 2px; }
.magicflow-sitereport__detail { padding: 6px 0 4px; font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__note { font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-block-end: 8px; }
.magicflow-sitereport__err { font-size: 12px; color: rgb(var(--v-theme-error)); margin-block-end: 8px; }
.magicflow-sitereport__list { display: flex; flex-direction: column; gap: 2px; }
.magicflow-sitereport__row { display: flex; align-items: center; gap: 9px; padding: 7px 4px; border-radius: 8px; }
.magicflow-sitereport__row:hover { background: rgba(var(--v-theme-on-surface), 0.04); }
.magicflow-sitereport__row-b { flex: 0 0 auto; }
.magicflow-sitereport__row-main { flex: 1 1 auto; min-width: 0; }
.magicflow-sitereport__row-t { font-size: 13px; font-weight: 550; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-sitereport__stall { color: #f0b64c; }
.magicflow-sitereport__row-s { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-sitereport__row-size { flex: 0 0 auto; font-size: 12px; font-weight: 600; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }

@media (max-width: 959px) {
  .magicflow-sitereport__stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .magicflow-sitereport__live-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .magicflow-sitereport__bar { flex-wrap: wrap; }
  .magicflow-sitereport__site { max-width: none; }
}
@media (max-width: 959px) {
  .magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}
</style>
