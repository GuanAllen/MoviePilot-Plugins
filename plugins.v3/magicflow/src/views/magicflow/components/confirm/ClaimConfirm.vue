<script setup>
// MagicFlow 前端 · 认领二次确认弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态 / 调父方法。
// 动作真值仍由父页（claimConfirmRun）持有：「确认」→ emit('run')；「取消」→ conf = null。
const conf = defineModel({ type: [Object, null], default: null })

defineProps({
  cfg: { type: Object, default: () => ({}) },
  acting: { type: Boolean, default: false },
})

const emit = defineEmits(['run'])
</script>

<template>
  <VDialog
    :model-value="!!conf"
    max-width="32rem"
    persistent
    @update:model-value="v => { if (!v) conf = null }"
  >
    <VCard class="magicflow-dialog">
      <VCardTitle class="text-subtitle-1 pt-4">{{ conf && conf.kind === 'abandon' ? '确认放弃认领' : '确认认领' }}</VCardTitle>
      <VCardText class="text-body-2">
        <template v-if="conf && conf.kind === 'batch'">
          将对「本轮可认领」的最多 {{ cfg.batch }} 个种子执行认领（每站每日上限 {{ cfg.daily }}）。
        </template>
        <template v-else-if="conf">
          将对 <strong>{{ conf.row.title || conf.row.hash }}</strong>（{{ conf.row.site_name }}）{{ conf.kind === 'abandon' ? '放弃认领' : '执行认领' }}。
        </template>
        <VAlert type="warning" variant="tonal" density="compact" class="mt-3">
          {{ conf && conf.kind === 'abandon'
            ? '放弃认领会丢失权益，且站点可能扣魔力。'
            : '认领后该种进入硬保护、永不自动删除；站点侧不达标可能扣魔力。' }}
        </VAlert>
      </VCardText>
      <VDivider />
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="acting" @click="conf = null">取消</VBtn>
        <VBtn :color="conf && conf.kind === 'abandon' ? 'error' : 'primary'" variant="flat" :loading="acting" @click="emit('run')">确认</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根：随「认领二次确认」弹窗自 index.vue 迁入。
     `.magicflow-dialog` 为**共享**选择器（父页其它弹窗也在用）→ 组件内复制一份，index.vue 原样保留。
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
