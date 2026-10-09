<script setup>
// MagicFlow 前端 · H&R 账单弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（hrBillStateColor / hrBillsAtRisk / fmtHoursLeft）自 composables/useHrBills.js
// 具名导入复用 —— 单一真值源，不在两处各写一份。
import { computed } from 'vue'
import { hrBillStateColor, hrBillsAtRisk, fmtHoursLeft } from '../../composables/useHrBills'

const open = defineModel({ type: Boolean, default: false })

const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh'])

const totals = computed(() => (props.data && props.data.totals) || {})
const sites = computed(() => (props.data && props.data.sites) || [])
</script>

<template>
  <VDialog v-model="open" max-width="48rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-hrbills-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">H&amp;R 账单</span>
        <VChip v-if="loading" size="x-small" color="grey" variant="tonal">加载中</VChip>
        <VChip v-else-if="totals.breached" size="x-small" color="deep-orange" variant="tonal">{{ totals.breached }} 违约</VChip>
        <VChip v-if="totals.at_risk" size="x-small" color="warning" variant="tonal">{{ totals.at_risk }} 临近到期</VChip>
        <span class="magicflow-ops-dialog__spacer" />
        <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="loading" @click="emit('refresh')" />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>
      <div class="magicflow-ops-dialog__body">
        <div class="magicflow-sitereport__stats">
          <div class="magicflow-sitereport__stat"><b>{{ totals.bills || 0 }}</b><span>账单</span></div>
          <div class="magicflow-sitereport__stat is-danger"><b>{{ totals.active || 0 }}</b><span>欠债</span></div>
          <div class="magicflow-sitereport__stat is-danger"><b>{{ totals.breached || 0 }}</b><span>违约</span></div>
          <div class="magicflow-sitereport__stat is-danger"><b>{{ totals.missing || 0 }}</b><span>本机缺失</span></div>
          <div class="magicflow-sitereport__stat" :class="totals.at_risk ? 'is-danger' : ''"><b>{{ totals.at_risk || 0 }}</b><span>临近到期</span></div>
        </div>
        <div class="magicflow-hrbills__list">
          <div v-for="s in sites" :key="s.domain" class="magicflow-hrbills__card">
            <div class="magicflow-hrbills__head">
              <span class="magicflow-hrbills__name">{{ s.name || s.domain }}</span>
              <VChip v-if="s.per_torrent_hr" size="x-small" color="purple" variant="tonal">逐种</VChip>
              <VChip v-if="s.rule_source" size="x-small" color="grey" variant="tonal">{{ s.rule_source }}</VChip>
              <span class="magicflow-ops-dialog__spacer" />
              <span class="magicflow-hrbills__nums">欠 {{ s.owed }} · 在qb {{ s.in_qb }} · 缺 {{ s.missing }}<template v-if="s.at_risk"> · ⚠临期 {{ s.at_risk }}</template></span>
            </div>
            <div class="magicflow-hrbills__chips">
              <VChip
                v-for="(n, st) in s.bills"
                :key="st"
                size="x-small"
                :color="hrBillStateColor(st)"
                variant="tonal"
              >{{ st }} {{ n }}</VChip>
              <VChip v-if="s.window_h" size="x-small" color="blue-grey" variant="tonal">窗口 {{ (s.window_h / 24).toFixed(1) }}d</VChip>
            </div>
            <div v-if="s.at_risk" class="magicflow-ops-dialog__sub">
              临近到期：
              <span v-for="(it, i) in hrBillsAtRisk(s)" :key="it.hash">{{ i ? '、' : '' }}{{ it.title || it.hash.slice(0, 8) }}（剩 {{ fmtHoursLeft(it.hours_left, it.state) }} / 需 {{ it.due_h }}h）</span>
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

@media (max-width: 959px) {
  .magicflow-sitereport__stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 959px) {
  .magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}
</style>
