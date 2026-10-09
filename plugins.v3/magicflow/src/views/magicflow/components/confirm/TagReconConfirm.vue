<script setup>
// MagicFlow 前端 · 标签对账 二次确认弹窗（★ 15.2.0：只补 qB 标签，不改账本、不删不暂停）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
const open = defineModel({ type: Boolean, default: false })

// props 下（只读）：pending = 父 useInvariant().tagReconPending（预计补标签数）；
// loading = useInvariant().tagReconLoading（对账进行中）。
defineProps({
  pending: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
})

// 事件向上：确认补标签 → 父页 runTagReconcile(true)（干跑 false 只负责打开本弹窗）。
const emit = defineEmits(['run'])
</script>

<template>
  <VDialog v-model="open" max-width="32rem" persistent>
    <VCard class="magicflow-dialog">
      <VCardTitle class="text-subtitle-1 pt-4">确认标签对账</VCardTitle>
      <VCardText class="text-body-2">
        账本说在岗（魔力/刷流/保种）、但 qB 标签缺身份轴（<code>魔流-&lt;站&gt;-静默-*</code>）或缺职务的种，将按<b>账本</b>补标签（预计 <strong>{{ pending }}</strong> 个）。
        <VAlert type="info" variant="tonal" density="compact" class="mt-3">
          只写 qB 标签：<strong>不改种子账本、不删种、不暂停、不 resume</strong>；附带把「有 <code>魔流-辅种</code> 标记、两本账都没登记」的无主辅种副本补登进辅种账。
        </VAlert>
      </VCardText>
      <VDivider />
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="loading" @click="open = false">取消</VBtn>
        <VBtn variant="flat" color="warning" :loading="loading" @click="emit('run')">确认补标签</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根：随「标签对账二次确认」弹窗自 index.vue 迁入。
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
