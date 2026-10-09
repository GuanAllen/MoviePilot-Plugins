<script setup>
// MagicFlow 前端 · 补暂停二次确认弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态 / 调父方法。
// 开关走 defineModel（父 v-model="enforceAsk"）；「取消」→ open = false；
// 「确认补暂停」→ @run（接父页原确认处理器 = 关弹窗 + loadEnforce(1)；★ 只 pause，不删种）。
const open = defineModel({ type: Boolean, default: false })

// props 下（只读）：loading = 父 useInvariant().enforceLoading；counts = enforceCounts 派生。
defineProps({
  loading: { type: Boolean, default: false },
  counts: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['run'])
</script>

<template>
  <VDialog v-model="open" max-width="32rem" persistent>
    <VCard class="magicflow-dialog">
      <VCardTitle class="text-subtitle-1 pt-4">确认补暂停</VCardTitle>
      <VCardText class="text-body-2">
        将对「账本或标签已是静默、但下载器里还在跑」的种补 pause（预计 <strong>{{ counts.violations || 0 }}</strong> 个）。
        <VAlert type="info" variant="tonal" density="compact" class="mt-3">
          只暂停：<strong>不删种、不动文件、不 resume</strong>；幂等可重跑。
        </VAlert>
      </VCardText>
      <VDivider />
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="loading" @click="open = false">取消</VBtn>
        <VBtn variant="flat" color="warning" :loading="loading" @click="emit('run')">确认补暂停</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根：随「补暂停二次确认」弹窗自 index.vue 迁入。
     .magicflow-dialog 为**共享**选择器（父页其它弹窗也在用）→ 组件内复制一份，index.vue 原样保留。
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
