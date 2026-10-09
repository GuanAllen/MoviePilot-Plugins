<script setup>
// MagicFlow 前端 · 批量删除托管种子「确认」弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态 / 调父方法。
// 动作真值仍由父页 composables/useSeeding.js 持有：点「删除」→ @delete（父页 batchAction('delete')）。
const open = defineModel({ type: Boolean, default: false })

// props 下（只读）：selectedHashes = 父 useSeeding().selectedHashes；selectedTask = 父 useTasks().selectedTask；
// batchBusy = 父 useSeeding().batchBusy。
defineProps({
  selectedHashes: { type: Array, default: () => [] },
  selectedTask: { type: Object, default: () => ({}) },
  batchBusy: { type: Boolean, default: false },
})

const emit = defineEmits(['delete'])
</script>

<template>
  <VDialog v-model="open" max-width="28rem">
    <VCard class="magicflow-dialog">
      <VCardTitle>批量删除托管种子</VCardTitle>
      <VCardText class="text-body-2">
        确认删除选中的 <b>{{ selectedHashes.length }}</b> 个种子？
        <br />
        <span class="text-medium-emphasis">
          将按任务设置{{ selectedTask.delete_files ? '连同文件' : '保留文件' }}从下载器删除，不可撤销。
        </span>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="open = false">取消</VBtn>
        <VBtn color="error" variant="flat" :loading="batchBusy" @click="emit('delete')">删除</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根：随「批量删除确认」弹窗自 index.vue 迁入。
     下列为**共享**选择器（父页其它弹窗也在用）→ 组件内复制一份，index.vue 原样保留。
     VDialog 会 teleport 到 body，且内容改由本组件渲染（带本组件 scope id）→ 父 scoped 够不到，故须自带。── */
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
