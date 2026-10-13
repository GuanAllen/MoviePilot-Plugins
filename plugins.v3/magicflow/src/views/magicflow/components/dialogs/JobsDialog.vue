<script setup>
// MagicFlow 前端 · 后台任务队列弹窗（★ 15.10.0）
// 数据向下、事件向上：本组件只渲染 + emit('refresh' / 'clear' / 'update:modelValue')。
import { computed } from 'vue'
import { formatDateTime } from '../../../../utils'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobs: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
  narrow: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'refresh', 'clear'])

const open = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const STATUS = {
  queued: { text: '排队中', color: 'amber' },
  running: { text: '执行中', color: 'primary' },
  done: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
}
function statusMeta(status) {
  return STATUS[String(status ?? '')] || { text: String(status ?? '未知'), color: 'grey' }
}
function duration(job) {
  const s = Number(job?.started ?? 0)
  const f = Number(job?.finished ?? 0)
  if (!s) return ''
  const end = f || (Date.now() / 1000)
  const d = Math.max(0, end - s)
  return d < 60 ? `${d.toFixed(0)} 秒` : `${(d / 60).toFixed(1)} 分`
}
const running = computed(
  () => Number(props.summary?.running ?? 0) + Number(props.summary?.queued ?? 0),
)
</script>

<template>
  <VDialog v-model="open" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-jobs-dialog">
      <VCardTitle class="d-flex align-center">
        <VIcon icon="mdi-progress-clock" class="me-2" />
        后台任务
        <VChip v-if="running" size="x-small" color="primary" variant="tonal" class="ms-2">{{ running }} 进行中</VChip>
        <VSpacer />
        <VBtn icon="mdi-refresh" variant="text" size="small" aria-label="刷新" @click="emit('refresh')" />
        <VBtn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="open = false" />
      </VCardTitle>
      <VDivider />
      <VCardText>
        <div class="text-body-2 text-medium-emphasis mb-2">
          慢动作（整理入库 / 订阅 / 刮削 / 批量删除）都在后台跑，<strong>关掉页面也会继续</strong>；这里看进度和结果。
        </div>
        <div v-if="!jobs.length" class="magicflow-jobs-empty">还没有后台任务</div>
        <ul v-else class="magicflow-jobs">
          <li v-for="job in jobs" :key="job.id">
            <VChip class="magicflow-jobs__chip" size="small" variant="tonal"
                   :color="statusMeta(job.status).color">
              {{ statusMeta(job.status).text }}
            </VChip>
            <span class="magicflow-jobs__kind">{{ job.kind_text || job.kind }}</span>
            <span class="magicflow-jobs__time">
              {{ formatDateTime(job.started || job.created) }}
              <template v-if="duration(job)"> · {{ duration(job) }}</template>
            </span>
            <span class="magicflow-jobs__title" :title="job.title">{{ job.title }}</span>
            <span v-if="job.message && job.message !== job.title" class="magicflow-jobs__msg"
                  :title="job.message">{{ job.message }}</span>
          </li>
        </ul>
      </VCardText>
      <VDivider />
      <VCardActions>
        <VBtn size="small" variant="text" prepend-icon="mdi-broom" @click="emit('clear')">清理已完成</VBtn>
        <VSpacer />
        <VBtn size="small" variant="tonal" prepend-icon="mdi-refresh" @click="emit('refresh')">刷新</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.magicflow-jobs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.magicflow-jobs li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 3px 8px;
  padding: 7px 9px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  font-size: 0.82rem;
}
.magicflow-jobs__chip { flex: 0 0 auto; }
.magicflow-jobs__kind {
  min-inline-size: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
}
.magicflow-jobs__title,
.magicflow-jobs__msg {
  grid-column: 1 / -1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.magicflow-jobs__title { color: rgba(var(--v-theme-on-surface), 0.87); }
.magicflow-jobs__time {
  white-space: nowrap;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-jobs-empty {
  padding: 24px 8px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
@media (max-width: 600px) {
  .magicflow-jobs__time { grid-column: 1 / -1; }
}
</style>
