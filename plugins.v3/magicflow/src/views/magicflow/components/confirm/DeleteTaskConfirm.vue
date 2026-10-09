<script setup>
// MagicFlow 前端 · 删除魔力任务确认弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态/调父方法。
// open：是否打开（父 deleteDialog）；target：名下种子处理方式（父 handoverTarget）。
const open = defineModel({ type: Boolean, default: false })
const target = defineModel('target', { type: String, default: 'idle' })

// props：selectedTask（当前选中任务，只读取 .name）/ handoverLoading（名下种子统计中）/
// handover（名下种子交棒信息，null=未就绪）/ handoverChoices（交棒目标下拉项，父计算属性）/ saving（删除保存中）。
defineProps({
  selectedTask: { type: Object, default: null },
  handoverLoading: { type: Boolean, default: false },
  handover: { type: Object, default: null },
  handoverChoices: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm'])
</script>

<template>
  <VDialog v-model="open" max-width="34rem">
    <VCard title="删除魔力任务" class="magicflow-dialog">
      <VCardText>
        确认删除「{{ selectedTask?.name }}」？
      </VCardText>
      <VCardText v-if="handoverLoading" class="magicflow-settings-hint">正在统计名下种子…</VCardText>
      <VCardText v-else-if="handover" class="magicflow-settings-hint">
        名下 <strong>{{ handover.managed }}</strong> 个种子 · {{ handover.size_gb }} GB
        <template v-if="handover.auto_handover?.length">
          <br />
          <VAlert density="compact" variant="tonal" color="info" class="mt-2">
            另有同站同状态任务「<strong>{{ handover.auto_handover[0].name }}</strong>」用同一批标签
            （{{ handover.tag }}），<strong>不交棒它也会接着管</strong>。<br />
            <strong>默认退回静默池</strong>（保文件）—— 想指定交给谁再在下面选。
          </VAlert>
        </template>
        <template v-else>
          <br />
          <VAlert density="compact" variant="tonal" color="info" class="mt-2">
            <strong>默认退回静默池</strong>（保文件）—— 想指定交给谁再在下面选。
          </VAlert>
        </template>
      </VCardText>
      <VCardText v-if="handover">
        <VSelect v-model="target" :items="handoverChoices" item-title="text" item-value="value"
          density="compact" variant="outlined" hide-details label="名下种子怎么处理" />
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="open = false">取消</VBtn>
        <VBtn color="error" variant="flat" :loading="saving" @click="emit('confirm')">确认删除</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根：随「删除任务确认弹窗」自 index.vue 迁入。
     共享选择器（magicflow-dialog / magicflow-settings-hint）父页其它弹窗也在用
     → 两处各留一份（纯复制，零改动）；index.vue 原样保留。
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
