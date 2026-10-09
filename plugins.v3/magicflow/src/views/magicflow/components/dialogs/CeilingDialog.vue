<script setup>
// MagicFlow 前端 · 站点容量/魔力一览弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上；子组件不直接改父状态。
const open = defineModel({ type: Boolean, default: false })

defineProps({
  rows: { type: Array, default: () => [] },
  narrow: { type: Boolean, default: false },
})
</script>

<template>
  <VDialog v-model="open" max-width="34rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-ceiling-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">站点容量</span>
        <span class="magicflow-ops-dialog__spacer" />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>
      <div class="magicflow-ops-dialog__sub">
        时魔 ÷ 站点上限。占用高 = 快满，占用低 = 还有空间加种
      </div>
      <div class="magicflow-ops-dialog__body">
        <div class="magicflow-ceiling-list">
          <div v-for="r in rows" :key="r.site" class="magicflow-ceiling-row">
            <div class="magicflow-ceiling-row__head">
              <span class="magicflow-ceiling-row__nm">{{ r.site }}</span>
              <span class="magicflow-ceiling-row__val">
                {{ r.bonus ? r.bonus.toFixed(1) : '—' }}<small>/h</small>
                <template v-if="r.ceiling"> · 上限 {{ r.ceiling.toFixed(0) }}</template>
              </span>
            </div>
            <div class="magicflow-ceiling-bar">
              <i :style="{ width: Math.min(r.pct, 100) + '%' }" :class="{ 'is-full': r.pct >= 85 }" />
            </div>
            <div class="magicflow-ceiling-row__foot">
              <span>占用 {{ r.pct }}%</span>
              <span>{{ r.seeds }} 种</span>
            </div>
          </div>
          <div v-if="!rows.length" class="magicflow-ceiling-empty">暂无数据（任务尚未产出统计）</div>
        </div>
      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 站点容量弹窗：随「站点上限/魔力一览」弹窗自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head / settings-dialog__title /
     ops-dialog__spacer / ops-dialog__sub / ops-dialog__body / ceiling-empty）父页其它弹窗
     也在用 → 两处各留一份（纯复制，零改动）。VDialog 会 teleport，父 scoped 够不到子内部，故须自带。── */
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

/* ── 站点容量弹窗（专属）────────────────────────────────────── */
.magicflow-ceiling-dialog { display: flex; flex-direction: column; }
.magicflow-ceiling-list { display: flex; flex-direction: column; gap: 15px; }
.magicflow-ceiling-row__head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.magicflow-ceiling-row__nm { font-size: 14px; font-weight: 650; }
.magicflow-ceiling-row__val { font-size: 13px; font-weight: 700; color: rgb(var(--v-theme-primary)); flex: 0 0 auto; }
.magicflow-ceiling-row__val small { font-size: 10px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-inline-start: 1px; }
.magicflow-ceiling-bar { margin-block-start: 7px; height: 7px; border-radius: 4px; background: rgba(var(--v-border-color), 0.16); overflow: hidden; }
.magicflow-ceiling-bar i { display: block; height: 100%; border-radius: 4px; background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary))); }
.magicflow-ceiling-bar i.is-full { background: linear-gradient(90deg, rgb(var(--v-theme-warning)), rgb(var(--v-theme-error))); }
.magicflow-ceiling-row__foot { display: flex; justify-content: space-between; margin-block-start: 5px; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }

@media (max-width: 959px) {
  .magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}
</style>
