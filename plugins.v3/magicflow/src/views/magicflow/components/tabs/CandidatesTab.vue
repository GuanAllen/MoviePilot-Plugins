<script setup>
// MagicFlow 前端 · 候选排行（种子池 · poolView === 'candidates'）
// P4：自 views/magicflow/index.vue 纯搬家（模板 + 配套 scoped 样式），无行为/样式变更。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// data：候选数据（真值源仍在父页 useTaskDetail 的 candidateData）。
// taskIsBrush：是否刷流任务 → 决定副标题文案。
defineProps({
  data: { type: Object, default: () => ({}) },
  taskIsBrush: { type: Boolean, default: false },
})
</script>

<template>
  <VSheet tag="section" class="magicflow-panel app-surface-static">
    <header class="magicflow-panel__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">候选排行</div>
        <div class="text-body-2 text-medium-emphasis">{{ taskIsBrush ? '按上传潜力（下载人数）排序 · 仅供选种参考' : '待办名次由站点魔力效率内部排序 · 仅供选种参考' }}</div>
      </div>
    </header>
    <ol class="magicflow-pipeline">
      <li v-for="candidate in (data.candidates || []).slice(0, 8)" :key="candidate.hash">
        <span class="magicflow-pipeline__index">{{ candidate.rank }}</span>
        <div>
          <strong>{{ candidate.title || '未知种子' }}</strong>
          <span>{{ Number(candidate.size_gb || 0).toFixed(2) }} GB · {{ candidate.seeders }} 做种 · {{ candidate.leechers }} 下载 · {{ Number(candidate.age_weeks || 0).toFixed(1) }} 周</span>
        </div>
      </li>
      <li v-if="!(data.candidates || []).length">
        <div class="magicflow-table-empty">暂无候选</div>
      </li>
    </ol>
  </VSheet>
</template>

<style scoped>
/* ── 共享选择器（index.vue 同有，此处复制一份；父页原样保留）────────── */
.magicflow-panel {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
  min-inline-size: 0;
  padding: 16px;
}

.magicflow-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

/* ── 本视图专属（自 index.vue 搬入）────────────────────────────────── */
.magicflow-pipeline {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}

.magicflow-pipeline li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding-block: 7px;
}

.magicflow-pipeline li > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-inline-size: 0;
}

.magicflow-pipeline li span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.82rem;
  overflow-wrap: anywhere;
}

.magicflow-pipeline__index {
  display: grid;
  place-items: center;
  inline-size: 28px;
  block-size: 28px;
  border-radius: 50%;
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
  font-size: 0.78rem;
}

/* ── .magicflow-page 级覆盖（同父页；目标元素已在本组件内）────────── */
.magicflow-page .magicflow-panel {
  padding: 18px 16px;
}

.magicflow-page .magicflow-panel__head .text-subtitle-1 {
  font-size: 14px;
  font-weight: 600;
}

.magicflow-page .magicflow-panel__head .text-body-2 {
  font-size: 11px;
}

.magicflow-page .magicflow-pipeline li strong {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 699px) {
  .magicflow-panel {
    padding: 14px;
  }

  .magicflow-panel__head {
    flex-direction: column;
    align-items: flex-start;
    flex-wrap: wrap;
  }
}
</style>
