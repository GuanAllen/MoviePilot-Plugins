<script setup>
// MagicFlow 前端 · 单种删除确认弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
const open = defineModel({ type: Boolean, default: false })

// props（向下）：pendingTorrentDelete = useSeeding.pendingTorrentDelete；
// selectedTask = useTaskDetail.selectedTask（仅用 delete_files）；saving = useSeeding.saving。
defineProps({
  pendingTorrentDelete: { type: Object, default: null },
  selectedTask: { type: Object, default: () => ({}) },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm'])
</script>

<template>
  <VDialog v-model="open" max-width="28rem">
    <VCard class="magicflow-dialog">
      <VCardTitle class="text-wrap">删除托管种子</VCardTitle>
      <VCardText class="text-body-2">
        确认删除「{{ pendingTorrentDelete?.title || '该种子' }}」？
        <br />
        <span class="text-medium-emphasis">
          将按任务设置{{ selectedTask.delete_files ? '连同文件' : '保留文件' }}从下载器删除，不可撤销。
        </span>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="open = false">取消</VBtn>
        <VBtn color="error" variant="flat" :loading="saving" @click="emit('confirm')">删除</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 共享选择器（父页其它弹窗也在用）→ 组件内复制一份、index.vue 原样保留。
     VDialog 会 teleport，父 scoped 够不到子内部，故须自带。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}
</style>
