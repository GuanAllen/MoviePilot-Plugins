<script setup>
// MagicFlow 前端 · 批量转移种子确认弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 L2002–L2018 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 状态真值源仍在 composables/useSeeding.js（transferDialog / transferTarget / transferChoices /
// selectedHashes / batchBusy / confirmTransfer），此处只做展示与回传。
const open = defineModel({ type: Boolean, default: false })
// 转移目标：v-model:target（对应 useSeeding.transferTarget，默认 'idle' = 退回静默池）。
const target = defineModel('target', { type: String, default: 'idle' })

// props（向下，只读）：
//   selectedHashes = useSeeding.selectedHashes（仅取 .length 展示数量）
//   choices        = useSeeding.transferChoices（VSelect 选项）
//   busy           = useSeeding.batchBusy（动作进行中）
defineProps({
  selectedHashes: { type: Array, default: () => [] },
  choices: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm'])
</script>

<template>
  <VDialog v-model="open" max-width="34rem">
    <VCard title="批量转移种子" class="magicflow-dialog">
      <VCardText class="magicflow-settings-hint">
        把选中的 <strong>{{ selectedHashes.length }}</strong> 个种子交给别的任务，或退回静默池（保文件）。
        跨站转移会改掉站点标签 —— 一般只转给<strong>同站</strong>任务。
      </VCardText>
      <VCardText>
        <VSelect v-model="target" :items="choices" item-title="text" item-value="value"
          density="compact" variant="outlined" hide-details label="转移到" />
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="busy" @click="open = false">取消</VBtn>
        <VBtn color="primary" variant="flat" :loading="busy" @click="emit('confirm')">转移</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 共享选择器（`.magicflow-dialog` / `.magicflow-settings-hint`）随本弹窗自 index.vue **复制一份**；
     父页其它弹窗仍在用，故 index.vue 原样保留（纯复制，零改动）。
     VDialog 会 teleport 到 body，父 scoped 够不到子内部，故须自带。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}
.magicflow-settings-hint {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 0.8rem;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  background: rgba(var(--v-theme-primary), 0.07);
  border-inline-start: 3px solid rgba(var(--v-theme-primary), 0.45);
}
</style>
