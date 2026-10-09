<script setup>
// MagicFlow · 任务编辑器「魔力公式」面板
// P6 拆分：自 components/TaskEditorDialog.vue **纯搬家**（VWindowItem 内层 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel）/ 事件向上（emit）：面板不直接改父状态 / 调父方法。
// 本面板只读写父 localTask 的 bonus_* 字段（无 props、无 emit）。
const bonusT0 = defineModel('bonusT0')
const bonusN0 = defineModel('bonusN0')
const bonusB0 = defineModel('bonusB0')
const bonusL = defineModel('bonusL')
const bonusZeroWeight = defineModel('bonusZeroWeight')
</script>

<template>
  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">魔力公式参数</div>
        <div class="text-body-2 text-medium-emphasis">
          留空使用站点预设 / NexusPHP 标准式（T0=5，N0=7，B0=100，L=300）
        </div>
      </div>
      <VChip size="small" color="primary" variant="tonal">高级</VChip>
    </header>
    <VRow>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="bonusT0"
          type="number"
          min="0.1"
          step="0.1"
          label="生存时间参数 T0"
          placeholder="默认 5"
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="bonusN0"
          type="number"
          min="2"
          label="做种人数参数 N0"
          placeholder="默认 7"
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="bonusB0"
          type="number"
          min="0.1"
          step="0.1"
          label="每小时魔力上限 B0"
          placeholder="默认 100"
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="bonusL"
          type="number"
          min="0.1"
          step="0.1"
          label="曲线参数 L"
          placeholder="默认 300"
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="bonusZeroWeight"
          type="number"
          min="0"
          step="0.05"
          label="零魔种子权重"
          placeholder="默认 0.2"
        />
      </VCol>
    </VRow>
  </section>
</template>

<style scoped>
/* 共享类（父组件同时在使用）：子内复制一份，父保留。 */
.editor-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-section + .editor-section {
  margin-block-start: 28px;
  padding-block-start: 24px;
  border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.editor-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
</style>
