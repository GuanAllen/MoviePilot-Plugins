<script setup>
// MagicFlow 前端 · 站点健康自检弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上；子组件不直接改父状态。
const open = defineModel({ type: Boolean, default: false })

defineProps({
  data: { type: Object, default: () => ({ issues: [] }) },
  color: { type: String, default: '' },
  label: { type: String, default: '' },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['goto'])
</script>

<template>
  <VDialog v-model="open" max-width="40rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-settings-dialog">
      <VToolbar color="transparent" density="comfortable">
        <VToolbarTitle class="text-subtitle-1">健康自检</VToolbarTitle>
        <VChip
          :color="color || 'success'"
          size="small"
          variant="tonal"
          class="me-2"
        >{{ label }}</VChip>
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </VToolbar>
      <VDivider />
      <VCardText class="magicflow-settings-body">
        <div v-if="!data.issues || !data.issues.length" class="magicflow-empty">
          <VIcon icon="mdi-check-circle-outline" size="20" class="me-2" />
          全部正常：任务运行正常、魔力无异常下滑、体积未贴上限。
        </div>
        <template v-else>
          <div class="mf-health__hint">
            按严重度排序 · 自检只看本地状态（零外部请求），共 {{ data.issues.length }} 项
          </div>
          <article
            v-for="issue in data.issues"
            :key="issue.key"
            class="mf-health__item"
            :class="`is-${issue.level}`"
          >
            <VIcon
              :icon="issue.level === 'error' ? 'mdi-alert-octagon-outline' : issue.level === 'warning' ? 'mdi-alert-outline' : 'mdi-information-outline'"
              size="18"
              class="mf-health__icon"
            />
            <div class="mf-health__body">
              <div class="mf-health__title">{{ issue.title }}</div>
              <div class="mf-health__detail">{{ issue.detail }}</div>
            </div>
            <VBtn
              v-if="issue.task_id"
              size="small"
              variant="text"
              @click="emit('goto', issue)"
            >诊断</VBtn>
          </article>
        </template>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 健康自检弹窗：随弹窗自 index.vue 迁入。
     下列共享选择器（magicflow-settings-dialog / magicflow-empty）父页其它弹窗/列表也在用
     → 两处各留一份（纯复制，零改动）。VDialog 会 teleport，父 scoped 够不到子内部，故须自带。
     .magicflow-settings-body 无样式定义（透明容器），无需复制。── */
.magicflow-settings-dialog {
  display: flex;
  flex-direction: column;
  block-size: min(84vh, 40rem);
  max-block-size: 92vh;
  overflow: hidden;
}
.magicflow-settings-dialog > .v-divider {
  flex: 0 0 auto;
}
.magicflow-empty {
  min-block-size: 20rem;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  text-align: center;
}

/* ── 健康自检弹窗（专属）────────────────────────────────────── */
.mf-health__hint {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-block-end: 8px;
}
.mf-health__item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-block-end: 6px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.mf-health__item.is-error { border-inline-start: 3px solid rgb(var(--v-theme-error)); }
.mf-health__item.is-warning { border-inline-start: 3px solid rgb(var(--v-theme-warning)); }
.mf-health__item.is-info { border-inline-start: 3px solid rgb(var(--v-theme-info)); }
.mf-health__icon { margin-block-start: 2px; }
.mf-health__item.is-error .mf-health__icon { color: rgb(var(--v-theme-error)); }
.mf-health__item.is-warning .mf-health__icon { color: rgb(var(--v-theme-warning)); }
.mf-health__item.is-info .mf-health__icon { color: rgb(var(--v-theme-info)); }
.mf-health__body { flex: 1 1 auto; min-inline-size: 0; }
.mf-health__title { font-size: 13px; font-weight: 600; }
.mf-health__detail { font-size: 12px; color: rgba(var(--v-theme-on-surface), 0.65); word-break: break-word; }

@media (max-width: 699px) {
  .magicflow-settings-dialog {
    block-size: min(90vh, 38rem);
    max-block-size: 94vh;
  }
}
</style>
