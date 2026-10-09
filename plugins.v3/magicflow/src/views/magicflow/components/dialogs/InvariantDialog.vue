<script setup>
// MagicFlow 前端 · 静默池「不变量收敛」弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态 / 调父方法。
// 动作真值仍由父页 composables/useInvariant.js 持有：刷新 / 查违背不变量 → @load-enforce；
// 「补暂停」→ @suppress（父页打开 12.7.1 的二次确认弹窗，只 pause、不删种）。
const open = defineModel({ type: Boolean, default: false })

// props 下（只读）：loading = 父 useInvariant().enforceLoading；counts = enforceCounts 派生。
defineProps({
  loading: { type: Boolean, default: false },
  counts: { type: Object, default: () => ({}) },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['load-enforce', 'suppress'])
</script>

<template>
  <VDialog v-model="open" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">静默池 · 不变量收敛</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="loading" @click="emit('load-enforce')" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="text-body-2">
        <div class="magicflow-settings-hint mt-2">
          <strong>补暂停</strong>（★ 12.7.1 / 15.1.0）：设计口径「静默池本意就是暂停不上传」——账本（或标签）已是静默、
          但下载器里没停的种一律补 pause（幂等，<strong>只暂停、不删种、不动文件</strong>）。
          <span v-if="counts.violations">当前违背不变量 <b>{{ counts.violations }}</b> 个。</span>
          <span v-else>当前不变量成立（全 paused）。</span>
          <span v-if="counts.tag_only">（其中 <b>{{ counts.tag_only }}</b> 个是「只打了静默标签、不在账本」的——多为全站辅种副本，15.1.0 起一并纳入收敛。）</span>
        </div>
      </VCardText>
      <VDivider />
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="open = false">关闭</VBtn>
        <VBtn variant="tonal" color="info" :loading="loading" @click="emit('load-enforce')">查违背不变量</VBtn>
        <VBtn variant="tonal" color="warning" :loading="loading" @click="emit('suppress')">补暂停</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 提示条：随「不变量收敛」弹窗自 index.vue 迁入。
     下列均为**共享**选择器（父页其它弹窗也在用）→ 组件内复制一份，index.vue 原样保留。
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
.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
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
.magicflow-recommend-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
