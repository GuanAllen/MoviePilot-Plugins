<script setup>
// MagicFlow 前端 · 桌面任务栏「内层」（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（内层模板 + 配套 scoped 样式，零行为/样式变更）。
// 外层容器 <VSheet tag="aside" class="magicflow-task-rail app-surface-static"> 留在父页；
// 此处仅含任务栏内层：头部（任务 + 计数）+ 任务列表 + 新建按钮。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不直接调父方法；无 Function prop。
// 契约（docs/REFACTOR-FRONTEND.md §5）以现有数据流为准收敛为：
//   props → tasks / selectedId；emits → select(id) / new。
// taskBadge 是展示型纯函数（真值源仍在 useTasks），此处按同口径本地实现，避免把函数当 prop 传。
import { formatBonus, formatBytes, runModeMeta, taskStateMeta } from '../../../utils'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  selectedId: { type: [String, Number], default: null },
})

const emit = defineEmits(['select', 'new'])

function taskBadge(task) {
  const mode = task?.run_mode || 'running'
  if (mode === 'seeding') return runModeMeta('seeding')
  if (mode === 'stopped') return runModeMeta('stopped')
  return taskStateMeta(task?.state, task?.enabled ?? true)
}
</script>

<template>
  <div class="magicflow-task-rail__head">
    <span class="text-subtitle-2">任务</span>
    <VChip size="x-small" variant="tonal">{{ tasks.length }}</VChip>
  </div>
  <div class="magicflow-task-list">
    <button
      v-for="task in tasks"
      :key="task.id"
      type="button"
      class="magicflow-task-item"
      :class="{ 'magicflow-task-item--selected': task.id === selectedId }"
      :aria-pressed="task.id === selectedId"
      @click="emit('select', task.id)"
    >
      <span class="magicflow-task-item__title">
        <strong>{{ task.name }}</strong>
        <VChip v-if="task.builtin" size="x-small" variant="tonal" color="primary">常驻</VChip>
        <VChip
          v-if="task.site_missing"
          size="x-small"
          variant="tonal"
          color="error"
          title="该任务绑定的站点已从 MoviePilot 删除：站点相关处理已跳过，请删除任务或改绑其他站点"
        >站点已删除</VChip>
        <span class="magicflow-status-dot" :class="`magicflow-status-dot--${taskBadge(task).color}`" />
      </span>
      <span>{{ task.site_name || task.site_domain || ('站点 ' + task.site_id) }} · {{ task.downloader }}</span>
      <span class="magicflow-task-item__meta">
        <span>{{ task.seeding_count || 0 }} 个种子</span>
        <span v-if="task.task_type === 'brush'">{{ formatBytes(task.task_uploaded || 0) }} 上传</span>
        <span v-else>{{ task.site_bonus_ok ? formatBonus(task.site_bonus_per_hour) : '—' }}</span>
      </span>
    </button>
  </div>
  <VBtn class="magicflow-create-task" block variant="tonal" prepend-icon="mdi-plus" @click="emit('new')">
    新建任务
  </VBtn>
</template>

<style scoped>
/* ── 内层专属选择器（自 index.vue 搬入并从父页删除）────────────── */
.magicflow-task-rail__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-inline: 4px;
}

.magicflow-task-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.magicflow-create-task {
  flex: 0 0 auto;
}

.magicflow-task-item {
  appearance: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  inline-size: 100%;
  padding: 11px 12px;
  border: 1px solid transparent;
  border-radius: var(--app-control-radius);
  color: rgb(var(--v-theme-on-surface));
  background: transparent;
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.magicflow-task-item:hover {
  background: rgba(var(--v-theme-primary), 0.05);
}

.magicflow-task-item:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.magicflow-task-item--selected {
  border-color: rgba(var(--v-theme-primary), 0.28);
  background: rgba(var(--v-theme-primary), 0.1);
}

.magicflow-task-item__title,
.magicflow-task-item__meta {
  justify-content: space-between;
  gap: 8px;
}

.magicflow-task-item__title strong {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.magicflow-task-item > span:not(.magicflow-task-item__title) {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.78rem;
}

/* ── 共享选择器（index.vue 同有，此处复制一份；父页原样保留）────── */
.magicflow-task-item__title,
.magicflow-task-item__meta {
  display: flex;
  align-items: center;
}

.magicflow-status-dot {
  inline-size: 8px;
  block-size: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: rgb(var(--v-theme-secondary));
}

.magicflow-status-dot--success { background: rgb(var(--v-theme-success)); }

.magicflow-status-dot--primary { background: rgb(var(--v-theme-primary)); }

.magicflow-status-dot--info { background: rgb(var(--v-theme-info)); }

.magicflow-status-dot--warning { background: rgb(var(--v-theme-warning)); }

.magicflow-status-dot--error { background: rgb(var(--v-theme-error)); }

/* ── .magicflow-page 级深色主题覆盖（目标元素已在本组件内；自 index.vue 搬入） */
.magicflow-page .magicflow-task-item {
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid transparent;
  border-radius: 12px;
}

.magicflow-page .magicflow-task-item--selected {
  background: rgba(var(--v-theme-primary), 0.16);
  border-color: rgba(var(--v-theme-primary), 0.42);
}

.magicflow-page .magicflow-task-item:hover {
  background: rgba(var(--v-theme-primary), 0.1);
}

/* ── 紧凑布局（.magicflow-page--compact）下任务列表滚动（自 index.vue 搬入） */
@media (min-width: 960px) {
  .magicflow-page--compact .magicflow-task-list {
    flex: 1 1 auto;
    min-block-size: 0;
    padding-inline-end: 2px;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
  }
}
</style>
