<script setup>
// MagicFlow 前端 · 起考核任务二次确认弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit run）；子组件不直接改父状态。
// 父变量 examConfirm 是「对象或 null」→ defineModel 承接；内部把 !!conf 当开关、conf 当载荷。
const conf = defineModel({ type: [Object, null], default: null })
// acting：父页 useExam().examActing（正在执行的动作标记，字符串），非空即禁用/转圈。
defineProps({
  acting: { type: String, default: '' },
})
const emit = defineEmits(['run'])
</script>

<template>
  <VDialog :model-value="!!conf" max-width="32rem" @update:model-value="v => { if (!v) conf = null }">
    <VCard v-if="conf" class="magicflow-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">确认执行</span>
      </header>
      <VDivider />
      <VCardText class="d-flex flex-column ga-2">
        <div>
          将在 <strong>{{ conf.row.site_name }}</strong> 上
          <strong>{{ conf.item.kind === 'upload' ? '创建 / 启用「考核刷流」任务' : '创建 / 启用「考核魔力」任务' }}</strong>：
        </div>
        <div class="text-body-2">任务名：<code>{{ conf.item.task_name }}</code></div>
        <ul v-if="(conf.item.notes || []).length" class="magicflow-exam-plan__notes">
          <li v-for="(n, ni) in conf.item.notes" :key="ni">{{ n }}</li>
        </ul>
        <VAlert type="info" variant="tonal" density="compact">
          任务达标后自动停；全程只做种、不删种（魔流不做下载任务）。
        </VAlert>
      </VCardText>
      <VDivider />
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="!!acting" @click="conf = null">取消</VBtn>
        <VBtn color="primary" variant="flat" :loading="!!acting" @click="emit('run', conf)">确认创建 / 启用</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行：随「起考核任务确认」自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head / settings-dialog__title）
     父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）；VDialog teleport 到 body，需自带样式。── */
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
/* 专属选择器：仅本弹窗用 → 自 index.vue 迁入并从父页删除（原 index.vue L2692）。 */
.magicflow-exam-plan__notes {
  margin: 0;
  padding-inline-start: 1.1em;
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}
</style>
