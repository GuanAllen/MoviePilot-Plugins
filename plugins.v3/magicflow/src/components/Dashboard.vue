<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { formatBonus, taskStateMeta, unwrapResponse } from '../utils'

// ★ 15.17.6：卡片外观与「刷新方式」双双对齐 MP 原生仪表板。
//   外观：MP 前端 dashboard 渲染分支写死
//     ``render_mode === 'vue' ? 挂插件联邦组件 : 'vuetify' ? 渲染宿主 elements``，
//   我们是 vue 模式（工作台/侧栏都靠它），宿主只给一个
//   ``<div class="dashboard-plugin-vue-renderer">`` 空壳 —— 卡片长啥样全由本组件决定。
//   故照抄 MP 原生卡片骨架与度量（bundle 里扒的 CSS 原值）：
//     VCard(variant=elevated/elevation-0/rounded-lg) + VCardItem(标题/副标题) + VCardText
//     + 统计区 .dashboard-stat-grid（桌面 4 列 / ≤740px 2 列、row-gap 1rem、竖分隔线、
//       标签 .72rem、数值 1.15rem/700/tabular-nums、附加行 .72rem 成功色）
//     + 任务行用 v-list（对齐 MP「Background Tasks」卡片的列表观感）。
//   刷新：MP 原生卡片刷新是「静默」的（只有首屏骨架，后台更新不闪任何进度条），
//   且刷新信号由宿主下发（vue 模式给子组件 ``allow-refresh`` 属性）。
//   故：首屏才显加载条；之后按宿主信号 + 本地兜底定时器静默更新，不闪、不跳版式；
//   并在首屏就绪后 emit('loaded') 回执宿主（MP 的 DashboardElement 约定）。

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
})

const emit = defineEmits(['loaded'])

const loading = ref(false) // 仅首屏用（驱动 v-card 顶部细进度条）
const refreshing = ref(false) // 后台静默刷新中（不驱动任何视觉）
const status = ref({ summary: {}, tasks: [] })
let refreshTimer
let loadCount = 0
let loadedEmitted = false

const title = computed(() => props.config?.attrs?.title || '魔流')
const subtitle = computed(() => props.config?.attrs?.subtitle || '魔力产出概览')

// 口径与工作台首页一致：run_mode ∈ {running, seeding} 才算「在跑」（`enabled` 只是「调度是否启用」）。
const ACTIVE_MODES = ['running', 'seeding']
const activeTasks = computed(() =>
  (status.value.tasks || [])
    .filter(item => !item.builtin && ACTIVE_MODES.includes(item.run_mode || 'running'))
    .sort((a, b) => Number(b.bonus_per_hour || 0) - Number(a.bonus_per_hour || 0))
    .slice(0, 3),
)
const activeCount = computed(() => Number(status.value.summary.active_tasks ?? status.value.summary.running_tasks ?? 0))

const metrics = computed(() => {
  const s = status.value.summary || {}
  return [
    { key: 'active', icon: 'mdi-radar', label: '在跑 / 共', value: `${activeCount.value} / ${Number(s.total_tasks || 0)}` },
    { key: 'seeding', icon: 'mdi-seed-outline', label: '托管种子', value: `${Number(s.seeding_count || 0)}` },
    { key: 'bph', icon: 'mdi-star-four-points-outline', label: '每小时魔力', value: formatBonus(s.bonus_per_hour).replace(' /h', '') },
    {
      key: 'bonus',
      icon: 'mdi-chart-donut',
      label: '当前魔力',
      value: Number(s.current_bonus || 0).toLocaleString('en-US', { maximumFractionDigits: 0 }),
      addition: `上限 ${Number(s.ceiling_pct || 0).toFixed(0)}%`,
    },
  ]
})

// 从插件接口加载仪表板聚合统计。
// silent=true → 后台刷新：不触发任何 loading 视觉，失败保留旧数据。
async function loadStatus({ silent = false } = {}) {
  if (silent) {
    if (refreshing.value) return
    refreshing.value = true
  } else {
    loading.value = true
  }
  try {
    const data = unwrapResponse(await props.api.get('plugin/MagicFlow/status'))
    if (data) status.value = data
  } catch {
    // 静默失败：保留上一次的数据，不闪错误态
  } finally {
    loading.value = false
    refreshing.value = false
    loadCount += 1
    if (!loadedEmitted && loadCount > 0) {
      loadedEmitted = true
      emit('loaded')
    }
  }
}

watch(
  () => props.allowRefresh,
  enabled => {
    if (enabled) loadStatus({ silent: loadCount > 0 })
  },
)

onMounted(() => {
  loadStatus()
  // 兜底：宿主未下发刷新信号时也保持数据新鲜（静默，无视觉副作用）
  refreshTimer = window.setInterval(() => loadStatus({ silent: true }), 30000)
})

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <VCard class="magicflow-dashboard rounded-lg elevation-0" variant="elevated" :loading="loading">
    <VCardItem>
      <VCardTitle class="text-body-1">{{ title }}</VCardTitle>
      <VCardSubtitle v-if="subtitle">{{ subtitle }}</VCardSubtitle>
    </VCardItem>
    <VCardText class="pt-0">
      <div class="mf-stat-grid">
        <div v-for="item in metrics" :key="item.key" class="mf-stat-item">
          <VAvatar size="38" class="bg-primary">
            <VIcon :icon="item.icon" size="20" />
          </VAvatar>
          <div class="mf-stat-copy">
            <span class="mf-stat-label">{{ item.label }}</span>
            <span class="mf-number">{{ item.value }}</span>
            <span v-if="item.addition" class="mf-stat-addition">{{ item.addition }}</span>
          </div>
        </div>
      </div>

      <VList v-if="activeTasks.length" class="mf-task-list" density="compact">
        <VListItem v-for="task in activeTasks" :key="task.id" class="px-0">
          <template #prepend>
            <VAvatar size="32" :color="taskStateMeta(task.state).color" class="me-3">
              <VIcon :icon="taskStateMeta(task.state).icon" size="18" />
            </VAvatar>
          </template>
          <VListItemTitle class="text-body-2">{{ task.name }}</VListItemTitle>
          <VListItemSubtitle class="text-caption">
            {{ task.site_name || task.site_domain }} · {{ task.seeding_count || 0 }} 种
          </VListItemSubtitle>
          <template #append>
            <span class="mf-number mf-number--sm">{{ formatBonus(task.bonus_per_hour) }}</span>
          </template>
        </VListItem>
      </VList>
      <div v-else-if="!loading" class="text-center text-medium-emphasis py-4">暂无在跑的魔力任务</div>
    </VCardText>
  </VCard>
</template>

<style scoped>
/* 度量照抄 MP 原生卡片（bundle CSS 原值，仅改类名前缀）。 */
.magicflow-dashboard {
  display: flex;
  flex-direction: column;
  block-size: 100%;
  min-block-size: 0;
}

.mf-stat-grid {
  display: grid;
  flex: 1 1 auto;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding-block: 0.6rem;
}

.mf-stat-item {
  display: flex;
  min-inline-size: 0;
  align-items: center;
  gap: 0.7rem;
  padding-inline: 1.1rem;
}

.mf-stat-item:first-child {
  padding-inline-start: 0;
}

.mf-stat-item + .mf-stat-item {
  border-inline-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.mf-stat-copy {
  display: flex;
  min-inline-size: 0;
  flex-direction: column;
}

.mf-stat-label,
.mf-stat-addition {
  font-size: 0.72rem;
  line-height: 1.25;
}

.mf-stat-label {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mf-stat-addition {
  overflow: hidden;
  color: rgb(var(--v-theme-success));
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mf-number {
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
  font-size: 1.15rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mf-number--sm {
  font-size: 0.95rem;
}

.mf-task-list {
  padding-block: 0;
  margin-block-start: 0.2rem;
  border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.mf-task-list :deep(.v-list-item) {
  min-block-size: 46px;
}

@media (max-width: 740px) {
  .mf-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    row-gap: 1rem;
    padding-block: 0.35rem 0.3rem;
  }

  .mf-stat-item {
    padding-inline: 0.5rem;
  }

  .mf-stat-item:nth-child(odd) {
    border-inline-start: 0;
    padding-inline-start: 0;
  }
}
</style>
