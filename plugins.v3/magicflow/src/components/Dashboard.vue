<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { formatBonus, taskStateMeta, unwrapResponse } from '../utils'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
})

const loading = ref(false)
const status = ref({ summary: {}, tasks: [] })
let refreshTimer

const enabledTasks = computed(() => (status.value.tasks || []).filter(item => item.enabled).slice(0, 3))

// 从插件接口加载仪表板聚合统计。
async function loadStatus() {
  if (!props.allowRefresh && status.value.tasks?.length) return
  loading.value = true
  try {
    status.value = unwrapResponse(await props.api.get('plugin/MagicFlow/status')) || status.value
  } finally {
    loading.value = false
  }
}

watch(
  () => props.allowRefresh,
  enabled => {
    if (enabled) loadStatus()
  },
)

onMounted(() => {
  loadStatus()
  refreshTimer = window.setInterval(loadStatus, 30000)
})

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="magicflow-dashboard">
    <div class="magicflow-dashboard__metrics">
      <div><span>启用任务</span><strong>{{ status.summary.enabled_tasks || 0 }} / {{ status.summary.total_tasks || 0 }}</strong></div>
      <div><span>托管种子</span><strong>{{ status.summary.seeding_count || 0 }}</strong></div>
      <div><span>每小时魔力</span><strong>{{ formatBonus(status.summary.bonus_per_hour) }}</strong></div>
      <div><span>站点当前魔力</span><strong>{{ Number(status.summary.current_bonus || 0).toFixed(2) }}</strong></div>
    </div>
    <VDivider />
    <div class="magicflow-dashboard__tasks">
      <div v-for="task in enabledTasks" :key="task.id">
        <VIcon :icon="taskStateMeta(task.state, task.enabled).icon" :color="taskStateMeta(task.state, task.enabled).color" size="18" />
        <div><strong>{{ task.name }}</strong><span>{{ task.site_name }} · {{ task.seeding_count || 0 }} 个种子</span></div>
        <span>{{ formatBonus(task.bonus_per_hour) }}</span>
      </div>
      <div v-if="!enabledTasks.length" class="magicflow-dashboard__empty">
        <VIcon icon="mdi-star-four-points-outline" />
        暂无启用的魔力任务
      </div>
    </div>
    <VProgressLinear v-if="loading" indeterminate color="primary" height="2" />
  </div>
</template>

<style scoped>
.magicflow-dashboard {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-inline-size: 0;
}

.magicflow-dashboard__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.magicflow-dashboard__metrics > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-inline-size: 0;
}

.magicflow-dashboard__metrics span,
.magicflow-dashboard__tasks span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.78rem;
}

.magicflow-dashboard__metrics strong {
  font-size: 1.05rem;
  overflow-wrap: anywhere;
}

.magicflow-dashboard__tasks {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.magicflow-dashboard__tasks > div {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
}

.magicflow-dashboard__tasks > div > div {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}

.magicflow-dashboard__tasks strong {
  overflow-wrap: anywhere;
}

.magicflow-dashboard__empty {
  justify-content: center;
  padding-block: 18px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

@media (max-width: 599px) {
  .magicflow-dashboard__metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
