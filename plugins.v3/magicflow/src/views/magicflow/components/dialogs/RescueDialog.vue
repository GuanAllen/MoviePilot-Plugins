<script setup>
// MagicFlow 前端 · 死种补源弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
const open = defineModel({ type: Boolean, default: false })

// props 下（只读）：展示态直接来自 composables/useRescue.js（父页透传）。
defineProps({
  data: { type: Object, default: null },
  scanning: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  busyType: { type: String, default: '' },
  targets: { type: Array, default: () => [] },
  skippedSites: { type: Array, default: () => [] },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh', 'apply'])

function runRescueScan() { emit('refresh') }
function runRescueApply(confirm) { emit('apply', confirm) }
</script>

<template>
  <VDialog v-model="open" max-width="50rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-rescue-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">死种补源</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="scanning" @click="runRescueScan" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-rescue-dialog__body">
        <VAlert density="compact" type="info" variant="tonal">
          停滞欠 H&R 的种 → 从他站「无 H&R」站补下同 Release；<b>未下完的种不辅种，只能补源</b>。
        </VAlert>

        <div class="magicflow-cs-status">
          <VChip size="small" variant="tonal" color="primary" prepend-icon="mdi-seed-outline">
            待补源 {{ targets.length }}
          </VChip>
          <span v-if="skippedSites.length" class="magicflow-cs-status__dim">
            排除站点（有 H&R）{{ skippedSites.length }} 个
          </span>
          <VSpacer />
          <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-eye-outline"
                 :loading="busy && busyType === 'preview'" @click="runRescueApply(false)">预览（干跑）</VBtn>
          <VBtn size="small" variant="flat" color="primary" prepend-icon="mdi-lifebuoy" class="ml-2"
                 :disabled="!targets.length"
                 :loading="busy && busyType === 'apply'" @click="runRescueApply(true)">执行补源</VBtn>
        </div>

        <div v-if="!targets.length" class="magicflow-cs-status__dim" style="padding:1rem 0">
          当前没有「停滞欠 H&R / 手动保留」的未下完种。
        </div>

        <section v-for="t in targets" :key="t.hash" class="magicflow-cs-pending">
          <article class="magicflow-cs-card">
            <div class="magicflow-cs-card__name" :title="t.title || t.hash">{{ t.title || t.hash }}</div>
            <div class="magicflow-cs-card__meta">
              <span class="magicflow-cs-card__site">{{ t.site || '?' }}</span>
              <span class="magicflow-cs-card__size">进度 {{ Math.round((t.progress ?? 0) * 100) }}% · 停滞 {{ t.stalled_hours ?? 0 }}h</span>
              <VChip v-if="t.hr_owed" size="x-small" variant="tonal" color="error">欠 H&R {{ t.hr_need_h }}h</VChip>
              <VChip v-else-if="t.manual" size="x-small" variant="tonal" color="primary">手动保留</VChip>
            </div>
            <div class="magicflow-cs-card__meta">
              <span class="magicflow-cs-status__dim">{{ t.reason_not_reuse }}</span>
            </div>
            <div v-if="t.candidates && t.candidates.length" class="magicflow-cs-card__meta">
              <span class="magicflow-cs-card__site">最佳候选：{{ t.best?.site_name || '?' }} · {{ t.best?.seeders ?? 0 }} 源</span>
            </div>
            <div v-else class="magicflow-cs-card__meta">
              <span class="magicflow-cs-status__dim" style="color:var(--v-error-base)">
                无可用候选<template v-if="t.skipped && t.skipped.length">（{{ t.skipped.map(s => s.site).join('、') }}）</template>
              </span>
            </div>
          </article>
        </section>

        <details class="magicflow-cs-rules">
          <summary>查看补源规则</summary>
          <div class="magicflow-cs-rules__body">
            <p><strong>目标</strong>：进度 &lt; 100% 且 0 速停滞 ≥ {{ data?.settings?.stall_hours ?? 6 }} 小时，且欠 H&amp;R 或手动保留。</p>
            <p><strong>候选</strong>：标题规范化后完全一致（不把 10bit 当非 10bit）+ 来源站无 H&R + 有源。</p>
            <p><strong>未下完不辅种</strong>：progress&lt;1 的种不进全站辅种，只能走补源（避免 ADD-REUSE 空转）。</p>
          </div>
        </details>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 共享选择器（父页其它弹窗 / 跨站取种弹窗也在用）→ 两处各留一份（纯复制，零改动）。
     ⚠️ VDialog 会 teleport 到 body，父页 scoped 规则不再命中 → 组件必须自带这些。── */
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
.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
}
.magicflow-recommend-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ── 共享选择器（cs-status / cs-card / cs-pending / cs-rules 组：跨站取种弹窗也用）
     → 两处各留一份（纯复制，零改动）。── */
.magicflow-cs-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-block: 14px 8px;
}
.magicflow-cs-status__dim {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}
.magicflow-cs-card {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(var(--v-theme-on-surface), 0.035);
  border: 1px solid rgba(var(--v-border-color), 0.16);
}
.magicflow-cs-card__name {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.magicflow-cs-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}
.magicflow-cs-card__site {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-cs-card__size {
  font-variant-numeric: tabular-nums;
}
.magicflow-cs-pending {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-block-start: 16px;
}
.magicflow-cs-rules {
  margin-block-start: 18px;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-border-color), 0.16);
  background: rgba(var(--v-theme-on-surface), 0.03);
  overflow: hidden;
}
.magicflow-cs-rules > summary {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  cursor: pointer;
  list-style: none;
}
.magicflow-cs-rules > summary::before {
  content: '▸';
  font-size: 11px;
  transition: transform 0.15s ease;
}
.magicflow-cs-rules[open] > summary::before {
  transform: rotate(90deg);
}
.magicflow-cs-rules > summary::-webkit-details-marker {
  display: none;
}
.magicflow-cs-rules__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 14px 13px;
  font-size: 12.5px;
  line-height: 1.75;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-cs-rules__body p {
  margin: 0;
}
.magicflow-cs-rules__body strong {
  font-weight: 650;
  color: rgb(var(--v-theme-primary));
}
</style>
