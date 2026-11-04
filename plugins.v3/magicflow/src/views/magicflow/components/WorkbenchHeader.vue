<script setup>
// MagicFlow 前端 · 工作台顶栏 / 头部（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不直接调父方法。
// 磁贴显隐：hiddenTiles 由父下发，口径同 useHeaderTiles.tileVisible（!hiddenTiles.includes(key)）。
// taskBadge / taskSwitchSubtitle 是 useTasks 返回的展示纯函数，由父作 prop 下发（单一真值源，不在两处各写一份）。
const props = defineProps({
  tasks: { type: Array, default: () => [] },
  selectedTask: { type: Object, default: null },
  selectedTaskId: { type: [String, Number], default: null },
  selectedState: { type: Object, default: () => ({}) },
  taskSiteIcon: { type: String, default: '' },
  summary: { type: Object, default: () => ({}) },
  hiddenTiles: { type: Array, default: () => [] },
  recommendData: { type: Object, default: () => ({}) },
  crossseedData: { type: Object, default: () => ({}) },
  doubanServiceData: { type: Object, default: () => ({}) },
  healthData: { type: Object, default: () => ({}) },
  healthColor: { type: String, default: '' },
  healthLabel: { type: String, default: '' },
  healthBadgeCount: { type: Number, default: 0 },
  examData: { type: Object, default: () => ({}) },
  examBadge: { type: Number, default: 0 },
  examUrgent: { type: Boolean, default: false },
  showClose: { type: Boolean, default: false },
  jobsBadge: { type: Number, default: 0 },
  notifyBadge: { type: Number, default: 0 },
  taskBadge: { type: Function, required: true },
  taskSwitchSubtitle: { type: Function, required: true },
})

const emit = defineEmits([
  'select-task',
  'open-create-task',
  'open-recommend',
  'open-cloud',
  'open-crossseed',
  'open-douban',
  'open-health',
  'open-ondemand',
  'open-exam',
  'open-rescue',
  'open-sitereport',
  'open-claim',
  'open-rss',
  'open-silent',
  'open-hrbills',
  'open-ceiling',
  'open-ops',
  'open-music',
  'open-assets',
  'open-jobs',
  'open-trend',
  'open-optimize',
  'open-plan',
  'open-notify',
  'open-hub',
  'open-settings',
  'close',
])

function tileVisible(key) { return !props.hiddenTiles.includes(key) }
</script>

<template>
    <header class="magicflow-page__header">
      <div class="magicflow-page__identity">
        <span class="magicflow-logo"><VIcon icon="mdi-magnet" size="20" /></span>
        <div>
          <h1>魔流<span class="magicflow-page__brand-en">MagicFlow</span></h1>
          <p>PT 做种 · 魔力养护 / 刷流保种</p>
        </div>
      </div>
      <div class="magicflow-page__actions">
        <VMenu v-if="tasks.length" :close-on-content-click="true" location="bottom end">
          <template #activator="{ props: menuProps }">
            <button
              v-bind="menuProps"
              type="button"
              class="magicflow-task-switch"
              :aria-label="`当前任务：${selectedTask?.name || ''}`"
            >
              <span class="magicflow-task-switch__icon">
                <img v-if="taskSiteIcon" :src="taskSiteIcon" alt="" />
                <VIcon v-else icon="mdi-web" size="15" />
              </span>
              <span class="magicflow-task-switch__v">{{ selectedTask?.name || '—' }} · {{ selectedTask?.site_name || '' }}</span>
              <span class="magicflow-status-dot" :class="`magicflow-status-dot--${selectedState.color}`" />
              <VIcon icon="mdi-chevron-down" size="18" class="magicflow-task-switch__chev" />
            </button>
          </template>
          <VList density="comfortable" class="magicflow-task-switch__menu">
            <VListItem
              v-for="task in tasks"
              :key="task.id"
              :title="task.name"
              :subtitle="taskSwitchSubtitle(task)"
              :active="task.id === selectedTaskId"
              lines="two"
              @click="emit('select-task', task.id)"
            >
              <template #prepend>
                <VIcon :icon="taskBadge(task).icon" :color="taskBadge(task).color" size="18" />
              </template>
            </VListItem>
          </VList>
        </VMenu>
        <VChip
          v-if="summary.total_tasks"
          class="magicflow-enabled-chip"
          size="small"
          variant="tonal"
          :title="`共 ${summary.total_tasks} 个任务 · 运行中跑流程+做种 · 做种中只保种 · 已停止全暂停`"
        >
          <span class="magicflow-enabled-chip__dot" aria-hidden="true" />
          运行 {{ summary.running_tasks || 0 }} · 做种 {{ summary.seeding_tasks || 0 }} · 停 {{ summary.stopped_tasks || 0 }}
        </VChip>
        <!-- ★ 新建任务：设计稿页头没有它，但它是主操作 —— 放在「运行/做种/停」之后、
             与右侧「铃铛 / 齿轮 / 功能中心」用竖分隔隔开，避免和实心紫的功能中心撞色成一对 -->
        <VBtn
          class="magicflow-header-create"
          color="primary"
          variant="flat"
          prepend-icon="mdi-plus"
          aria-label="新建任务"
          title="新建任务：选站点、定模式、开跑"
          @click="emit('open-create-task')"
        >
          新建任务
        </VBtn>
        <span class="magicflow-hdr-sep" aria-hidden="true" />
        <!-- ★★ 页头右端按设计稿只留三样：通知铃铛 / 设置齿轮 / 功能中心。
             其余 20+ 个入口（推荐·云盘·跨站·豆瓣·健康·点播·考核·补源·站点报表·
             音乐·库内资源·后台任务·趋势·优化·计划·通知·认领·RSS·静默池·H&R·容量·
             操作记录·新建任务·关闭）**全部收进「功能中心」**，页头不再逐个摆图标。 -->
        <VBadge
          v-if="notifyBadge > 0"
          :content="notifyBadge"
          color="error"
          location="top end"
          offset-x="6"
          offset-y="4"
        >
          <VBtn
            class="magicflow-icon-btn magicflow-notify-btn"
            icon="mdi-bell-outline"
            variant="text"
            :aria-label="`事件通知：${notifyBadge} 条`"
            :title="`事件通知：${notifyBadge} 条`"
            @click="emit('open-notify')"
          />
        </VBadge>
        <VBtn
          v-else
          class="magicflow-icon-btn magicflow-notify-btn"
          icon="mdi-bell-outline"
          variant="text"
          aria-label="事件通知"
          title="事件通知"
          @click="emit('open-notify')"
        />
        <VBtn
          class="magicflow-icon-btn magicflow-settings-btn"
          icon="mdi-cog-outline"
          variant="text"
          aria-label="插件设置"
          title="插件设置"
          @click="emit('open-settings')"
        />
        <VBtn
          class="magicflow-hub-btn"
          color="primary"
          variant="flat"
          prepend-icon="mdi-view-grid-outline"
          aria-label="功能中心"
          title="功能中心：全部功能页与工具"
          @click="emit('open-hub')"
        >
          功能中心
        </VBtn>
      </div>
    </header>
</template>

<style scoped>
/* P4：WorkbenchHeader 专属样式（自 index.vue 纯搬家）。
   ★ 共享选择器（magicflow-status-dot / magicflow-task-switch*）在 index.vue 各留一份。 */

/* ── 顶栏：品牌 / 动作区布局 ──────────────────────────────────────────── */
.magicflow-page__header,
.magicflow-page__identity,
.magicflow-page__actions {
  display: flex;
  align-items: center;
}

.magicflow-page__header {
  justify-content: space-between;
}

.magicflow-page__header {
  min-block-size: 48px;
  gap: 16px;
}

.magicflow-page__identity {
  min-inline-size: 0;
  gap: 12px;
}

.magicflow-page__identity h1 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: 0;
}

.magicflow-page__identity h1 .magicflow-page__brand-en {
  margin-inline-start: 6px;
  font-size: 0.92em;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: rgba(var(--v-theme-on-surface), 0.86);
}

/* 计数胶囊（运行 / 做种 / 停）：设计稿左边带一颗绿点 */
.magicflow-page .magicflow-enabled-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.magicflow-page .magicflow-enabled-chip__dot {
  inline-size: 7px;
  block-size: 7px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: rgb(var(--v-theme-success));
}

.magicflow-page__identity p {
  margin: 2px 0 0;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.875rem;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.magicflow-page__actions {
  flex-wrap: wrap;
  gap: 8px;
}

/* ★ 桌面头部：「详情磁贴组」与「设置齿轮」之间的竖分隔（窄屏整组隐藏） */
.magicflow-page .magicflow-hdr-sep {
  display: inline-block;
  inline-size: 1px;
  block-size: 22px;
  margin-inline: 10px;
  align-self: center;
  background: rgba(var(--v-border-color), 0.45);
  flex: 0 0 auto;
}

/* ★ 页头图标钮（通知铃铛 / 设置齿轮）：设计稿是浅底圆角方形，不是裸图标 */
.magicflow-page .magicflow-icon-btn {
  inline-size: 34px;
  block-size: 34px;
  min-inline-size: 34px;
  border-radius: 11px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.magicflow-page .magicflow-icon-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.13);
  color: rgb(var(--v-theme-on-surface));
}

.magicflow-settings-btn {
  margin-inline-start: 2px;
}

/* ── 状态点（与任务栏共用选择器 → 两处各留一份）────────────────────────── */
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

/* ── 窄屏（≤959px）：品牌头吸顶 / 折叠 ─────────────────────────────── */
@media (max-width: 959px) {
  .magicflow-page--compact .magicflow-page__header {
    position: sticky;
    top: 0;
    z-index: 4;
    margin-inline: -12px;
    padding: 12px;
    border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    backdrop-filter: blur(var(--transparent-blur, 0px));
    background-color: rgba(var(--v-theme-surface), var(--transparent-opacity-heavy, 1));
  }

  .magicflow-page__header {
    align-items: flex-start;
  }
}

/* ── 窄屏（≤699px）──────────────────────────────────────────────────── */
@media (max-width: 699px) {
  /* 窄屏隐藏顶部「新建任务」，交给移动工具栏的「新建」按钮 */
  .magicflow-page .magicflow-header-create {
    display: none;
  }

  .magicflow-page__header {
    align-items: center;
    flex-direction: row;
  }

  .magicflow-page__identity {
    flex: 1 1 auto;
    overflow: hidden;
  }

  .magicflow-page__identity > div {
    min-inline-size: 0;
  }

  .magicflow-page__identity h1,
  .magicflow-page__identity p {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .magicflow-page--compact .magicflow-page__header {
    align-items: center;
    flex-direction: row;
  }

  .magicflow-page__actions,
  .magicflow-page--compact .magicflow-page__actions {
    flex: 0 0 auto;
    flex-wrap: nowrap;
    inline-size: auto;
    margin-inline-start: auto;
  }

  .magicflow-page--compact .magicflow-page__actions > :deep(.v-chip),
  .magicflow-page--compact .magicflow-page__identity p {
    display: none;
  }
}

/* ── 超窄（≤419px）──────────────────────────────────────────────────── */
@media (max-width: 419px) {
  .magicflow-page:not(.magicflow-page--compact) .magicflow-page__header,
  .magicflow-page:not(.magicflow-page--compact) .magicflow-page__identity {
    gap: 8px;
  }
}

/* ── 按预览图对齐：品牌头排版 ──────────────────────────────────────── */
.magicflow-page .magicflow-page__header {
  gap: 12px;
  min-block-size: 44px;
}

.magicflow-page .magicflow-logo {
  inline-size: 38px;
  block-size: 38px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: rgb(var(--v-theme-on-primary));
  /* 品牌三段紫渐变（#8D51F9 → #7432DF → #5B00C5），替换原先的纯色假渐变 */
  background: linear-gradient(145deg, #8D51F9 0%, #7432DF 55%, #5B00C5 100%);
  box-shadow: 0 6px 20px rgba(var(--v-theme-primary), 0.45), inset 0 1px 0 rgba(var(--v-theme-on-primary), 0.25);
}

.magicflow-page .magicflow-page__identity h1 {
  font-size: 17px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: 0.2px;
}

.magicflow-page .magicflow-page__identity p {
  margin-block-start: 2px;
  font-size: 11px;
}

/* 顶部「新建任务」按钮（桌面端；移动端由工具栏承担，避免重复） */
.magicflow-page .magicflow-header-create {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
}

/* 顶部「功能中心」（设计稿页头最右的实心紫按钮；窄屏收进「更多」菜单） */
.magicflow-page .magicflow-hub-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
  margin-inline-start: 4px;
}

/* ── 顶部「当前任务」切换下拉（方案 B，与移动工具栏共用 → 两处各留一份）── */
.magicflow-page .magicflow-task-switch {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  max-inline-size: 22rem;
  padding: 6px 10px 6px 7px;
  border: 1px solid rgba(var(--v-theme-primary), 0.26);
  border-radius: 12px;
  background: linear-gradient(145deg, rgba(var(--v-theme-primary), 0.16), rgba(var(--v-theme-primary), 0.05));
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(var(--v-theme-primary), 0.16);
}

.magicflow-page .magicflow-task-switch:hover {
  border-color: rgba(var(--v-theme-primary), 0.42);
}

.magicflow-page .magicflow-task-switch:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.magicflow-page .magicflow-task-switch__icon {
  inline-size: 26px;
  block-size: 26px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 8px;
  color: rgb(var(--v-theme-on-primary));
  /* 同品牌三段紫渐变，替换原先的纯色假渐变 */
  background: linear-gradient(145deg, #8D51F9 0%, #7432DF 55%, #5B00C5 100%);
}

.magicflow-page .magicflow-task-switch__icon img {
  inline-size: 62%;
  block-size: 62%;
  object-fit: contain;
  border-radius: 5px;
}

.magicflow-page .magicflow-task-switch__body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-inline-size: 0;
  line-height: 1.15;
  text-align: start;
}

.magicflow-page .magicflow-task-switch__k {
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-page .magicflow-task-switch__v {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.magicflow-page .magicflow-task-switch__chev {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-page .magicflow-task-switch__menu {
  min-inline-size: 15rem;
}
/* 任务切换菜单项：站点 + 关键数字 (两行子文字) */
.magicflow-page .magicflow-task-switch__menu .v-list-item__subtitle {
  font-size: 11px !important;
  opacity: 0.85;
  letter-spacing: 0.01em;
}

/* ── 窄屏（≤959px）：只留「铃铛 / 齿轮 / 功能中心」───────────────── */
@media (max-width: 959px) {
  /* 桌面品牌头里的切换胶囊隐藏；移动端由工具栏承担 */
  .magicflow-page__actions .magicflow-task-switch {
    display: none;
  }

  /* 窄屏同样不再摆一排图标：全部入口都在「功能中心」里 */
  .magicflow-page__actions .magicflow-hdr-sep {
    display: none;
  }

  .magicflow-page .magicflow-hub-btn {
    margin-inline-start: 0;
  }

  /* 手机端隐藏自相矛盾的计数胶囊（信息已由首页大数承担） */
  .magicflow-page .magicflow-enabled-chip { display: none; }
}
</style>
