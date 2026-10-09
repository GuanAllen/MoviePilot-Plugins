<script setup>
// MagicFlow 前端 · 站点报表弹窗（11.10.0）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（siteReportBucketColor / siteReportItemSub / siteReportTransportCount）自
// composables/useSiteReport.js 具名导入复用 —— 单一真值源，不在两处各写一份。
import {
  siteReportBucketColor,
  siteReportItemSub,
  siteReportTransportCount,
} from '../../composables/useSiteReport'
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

defineProps({
  loading: { type: Boolean, default: false },
  live: { type: Boolean, default: false },
  report: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  items: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh', 'live', 'change'])
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
        <VBtn
          size="small"
          variant="tonal"
          :prepend-icon="live ? 'mdi-radar' : 'mdi-cloud-download-outline'"
          :loading="loading"
          @click="emit('live')"
        >H&R 现抓</VBtn>
      </div>
      <div class="magicflow-ops-dialog__body">
        <div class="magicflow-sitereport__stats">
          <div class="magicflow-sitereport__stat" title="该站点在本机下载器里的全部种子（含做种/下载中/暂停/静默）"><b>{{ summary.total || 0 }}</b><span>本站种子</span></div>
          <div class="magicflow-sitereport__stat"><b>{{ (summary.size_gb || 0).toFixed(1) }}</b><span>GB</span></div>
          <div class="magicflow-sitereport__stat is-danger"><b>{{ summary.hr_owed || 0 }}</b><span>欠 H&amp;R</span></div>
          <div class="magicflow-sitereport__stat is-danger"><b>{{ summary.hr_missing || 0 }}</b><span>本机缺失</span></div>
        </div>
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
        <div class="magicflow-sitereport__chips magicflow-sitereport__chips--l2">
          <span class="magicflow-sitereport__chip-label">传输</span>
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
        <div class="magicflow-ops-dialog__sub">
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
              <div class="magicflow-sitereport__row-t" :title="it.title">{{ it.title || it.hash }}</div>
              <div class="magicflow-sitereport__row-s">{{ siteReportItemSub(it) }}</div>
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
.magicflow-sitereport__stat { background: rgba(var(--v-theme-on-surface), 0.04); border-radius: 10px; padding: 8px 10px; text-align: center; }
.magicflow-sitereport__stat b { display: block; font-size: 20px; font-weight: 700; line-height: 1.15; }
.magicflow-sitereport__stat span { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__stat.is-danger b { color: rgb(var(--v-theme-error)); }
.magicflow-sitereport__chips { display: flex; flex-wrap: wrap; gap: 6px; margin-block-end: 10px; }
.magicflow-sitereport__chips--l2 { margin-block-end: 8px; }
.magicflow-sitereport__chip-label { align-self: center; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-inline-end: 2px; }
.magicflow-sitereport__note { font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-block-end: 8px; }
.magicflow-sitereport__err { font-size: 12px; color: rgb(var(--v-theme-error)); margin-block-end: 8px; }
.magicflow-sitereport__list { display: flex; flex-direction: column; gap: 2px; }
.magicflow-sitereport__row { display: flex; align-items: center; gap: 9px; padding: 7px 4px; border-radius: 8px; }
.magicflow-sitereport__row:hover { background: rgba(var(--v-theme-on-surface), 0.04); }
.magicflow-sitereport__row-b { flex: 0 0 auto; }
.magicflow-sitereport__row-main { flex: 1 1 auto; min-width: 0; }
.magicflow-sitereport__row-t { font-size: 13px; font-weight: 550; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-sitereport__row-s { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-sitereport__row-size { flex: 0 0 auto; font-size: 12px; font-weight: 600; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }

@media (max-width: 959px) {
  .magicflow-sitereport__stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .magicflow-sitereport__bar { flex-wrap: wrap; }
  .magicflow-sitereport__site { max-width: none; }
}
@media (max-width: 959px) {
  .magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}
</style>
