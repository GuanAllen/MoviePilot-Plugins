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
  'open-music',
  'open-assets',
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
          <h1>魔流</h1>
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
              <span class="magicflow-task-switch__body">
                <span class="magicflow-task-switch__k">当前任务</span>
                <span class="magicflow-task-switch__v">{{ selectedTask?.name || '—' }} · {{ selectedTask?.site_name || '' }}</span>
              </span>
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
          :title="`共 ${summary.total_tasks} 个任务：运行中 = 跑流程+做种；做种中 = 停调度只保做种；已停止 = 种子全暂停`"
        >
          运行 {{ summary.running_tasks || 0 }} · 做种 {{ summary.seeding_tasks || 0 }} · 停 {{ summary.stopped_tasks || 0 }}
        </VChip>
        <VBtn class="magicflow-header-create" color="primary" variant="flat" prepend-icon="mdi-plus" @click="emit('open-create-task')">
          新建任务
        </VBtn>
        <VBadge
          v-if="tileVisible('recommend') && recommendData.enabled !== false && (recommendData.recommended || 0) > 0"
          class="magicflow-recommend-wrap"
          :content="recommendData.recommended"
          color="error"
          location="top end"
          offset-x="6"
          offset-y="4"
        >
          <VBtn
            class="magicflow-recommend-btn"
            icon="mdi-movie-star-outline"
            variant="text"
            aria-label="推荐"
            @click="emit('open-recommend')"
          />
        </VBadge>
        <VBtn
          v-else-if="tileVisible('recommend')"
          class="magicflow-recommend-btn"
          icon="mdi-movie-star-outline"
          variant="text"
          aria-label="推荐"
          @click="emit('open-recommend')"
        />
        <VBtn
          v-if="tileVisible('cloud')"
          class="magicflow-cloud-btn"
          icon="mdi-cloud-upload-outline"
          variant="text"
          aria-label="云盘归档"
          @click="emit('open-cloud')"
        />
        <VBadge
          v-if="tileVisible('crossseed') && Number(crossseedData.count || 0) > 0"
          class="magicflow-crossseed-wrap"
          :content="crossseedData.count"
          color="info"
          location="top end"
          offset-x="6"
          offset-y="4"
        >
          <VBtn
            class="magicflow-crossseed-btn"
            icon="mdi-swap-horizontal-bold"
            variant="text"
            aria-label="跨站免费取种"
            @click="emit('open-crossseed')"
          />
        </VBadge>
        <VBtn
          v-else-if="tileVisible('crossseed')"
          class="magicflow-crossseed-btn"
          icon="mdi-swap-horizontal-bold"
          variant="text"
          aria-label="跨站免费取种"
          @click="emit('open-crossseed')"
        />
        <VBtn
          v-if="tileVisible('douban')"
          class="magicflow-douban-btn"
          icon="mdi-database-search-outline"
          variant="text"
          :color="doubanServiceData.ok ? undefined : 'warning'"
          :aria-label="`豆瓣评分服务：库 ${doubanServiceData.records || 0} 条`"
          :title="`豆瓣评分服务：库 ${doubanServiceData.records || 0} 条${doubanServiceData.ok ? '' : '（不可用）'}`"
          @click="emit('open-douban')"
        />
        <VBadge
          v-if="healthBadgeCount > 0"
          class="magicflow-health-wrap"
          :content="healthBadgeCount"
          :color="healthData.level === 'error' ? 'error' : 'warning'"
          location="top end"
          offset-x="6"
          offset-y="4"
        >
          <VBtn
            class="magicflow-health-btn"
            icon="mdi-heart-pulse"
            variant="text"
            :color="healthColor"
            :aria-label="healthLabel"
            :title="healthLabel"
            @click="emit('open-health')"
          />
        </VBadge>
        <VBtn
          v-else
          class="magicflow-health-btn"
          icon="mdi-heart-pulse"
          variant="text"
          :aria-label="healthLabel"
          :title="healthLabel"
          @click="emit('open-health')"
        />
        <VBtn
          v-if="tileVisible('ondemand')"
          class="magicflow-ondemand-btn"
          icon="mdi-cloud-download-outline"
          variant="text"
          aria-label="点播"
          title="点播：片名 / 豆瓣·TMDB·IMDB 链接 → 搜索选源（免费优先）→ 直接转「资源」"
          @click="emit('open-ondemand')"
        />
        <VBadge
          v-if="tileVisible('exam') && examData.enabled !== false && examBadge > 0"
          class="magicflow-exam-wrap"
          :content="examBadge"
          :color="examUrgent ? 'error' : 'warning'"
          location="top end"
          offset-x="6"
          offset-y="4"
        >
          <VBtn
            class="magicflow-exam-btn"
            icon="mdi-school-outline"
            variant="text"
            aria-label="新手考核"
            @click="emit('open-exam')"
          />
        </VBadge>
        <VBtn
          v-else-if="tileVisible('exam') && examData.enabled !== false"
          class="magicflow-exam-btn"
          icon="mdi-school-outline"
          variant="text"
          aria-label="新手考核"
          @click="emit('open-exam')"
        />
        <VBtn
          class="magicflow-rescue-btn"
          icon="mdi-lifebuoy"
          variant="text"
          aria-label="死种补源"
          title="死种补源：停滞欠 H&R 的种 → 他站无 H&R 站补下同 Release"
          @click="emit('open-rescue')"
        />
        <VBtn
          v-if="tileVisible('sitereport')"
          class="magicflow-sitereport-btn"
          icon="mdi-table-large"
          variant="text"
          aria-label="站点报表"
          title="站点报表：逐条种子状态（分类/保护/账单/qB）"
          @click="emit('open-sitereport')"
        />
        <!-- ★ 音乐甄别入口已「收起来」：只在窄屏/桌面「更多」菜单里，顶栏不再放独立图标 -->
        <!-- ★ 桌面：详情磁贴（推荐/云盘/跨站/豆瓣/点播/考核/补源）与「设置」分两档 → 中间加一条竖分隔 -->
        <span class="magicflow-hdr-sep" aria-hidden="true" />
        <VBtn
          class="magicflow-settings-btn"
          icon="mdi-tune-variant"
          variant="text"
          aria-label="插件设置"
          @click="emit('open-settings')"
        />
        <VBtn v-if="showClose" class="magicflow-close-btn" icon="mdi-close" variant="text" aria-label="关闭" @click="emit('close')" />
        <!-- 窄屏：把上面那几个图标按钮收进「更多」菜单（宽屏不显示本按钮） -->
        <VMenu location="bottom end" :close-on-content-click="true">
          <template #activator="{ props: moreProps }">
            <VBtn
              v-bind="moreProps"
              class="magicflow-more-btn"
              icon="mdi-dots-vertical"
              variant="text"
              aria-label="更多"
            />
          </template>
          <VList density="comfortable" class="magicflow-more-menu" min-width="228">
            <VListItem
              v-if="tileVisible('recommend') && recommendData.enabled !== false"
              prepend-icon="mdi-movie-star-outline"
              title="推荐"
              :subtitle="(recommendData.recommended || 0) > 0 ? `${recommendData.recommended} 个待确认` : '影视推荐甄别'"
              @click="emit('open-recommend')"
            />
            <VListItem v-if="tileVisible('cloud')" prepend-icon="mdi-cloud-upload-outline" title="云盘归档" @click="emit('open-cloud')" />
            <VListItem
              v-if="tileVisible('crossseed')"
              prepend-icon="mdi-swap-horizontal-bold"
              title="跨站取种"
              :subtitle="Number(crossseedData.count || 0) > 0 ? `${crossseedData.count} 个可免费取种` : '跨站免费取种'"
              @click="emit('open-crossseed')"
            />
            <VListItem
              v-if="tileVisible('douban')"
              prepend-icon="mdi-database-search-outline"
              title="豆瓣评分"
              :subtitle="`库 ${doubanServiceData.records || 0} 条${doubanServiceData.ok ? '' : '（服务不可用）'}`"
              @click="emit('open-douban')"
            />
            <VListItem
              prepend-icon="mdi-heart-pulse"
              title="健康自检"
              :subtitle="healthBadgeCount > 0 ? `${healthBadgeCount} 项待处理` : '各子系统正常'"
              @click="emit('open-health')"
            />
            <VListItem
              v-if="tileVisible('ondemand')"
              prepend-icon="mdi-cloud-download-outline"
              title="点播"
              subtitle="片名 / 链接 → 搜索选源（免费优先）"
              @click="emit('open-ondemand')"
            />
            <VListItem
              v-if="tileVisible('exam') && examData.enabled !== false"
              prepend-icon="mdi-school-outline"
              title="新手考核"
              :subtitle="examBadge > 0 ? `${examBadge} 个未通过` : '考核进度与一键起任务'"
              @click="emit('open-exam')"
            />
            <VListItem prepend-icon="mdi-lifebuoy" title="死种补源" subtitle="停滞欠 H&R 的种 → 无 H&R 站补源" @click="emit('open-rescue')" />
            <VListItem
              v-if="tileVisible('sitereport')"
              prepend-icon="mdi-table-large"
              title="站点报表"
              subtitle="站点逐条种子状态（分类/保护/账单）"
              @click="emit('open-sitereport')"
            />
            <!-- ★ 15.8.2：音乐薄弹窗（窄屏也走「更多」菜单） -->
            <VListItem prepend-icon="mdi-music-circle-outline" title="音乐甄别" subtitle="贴歌单 → 选种计划 → 一键加种" @click="emit('open-music')" />
            <!-- ★ 15.8.15（Master「希望增加魔流库内资产手动删除的入口」）：
                 全局入口（不挂在任务上 —— 库内资产跨任务）；默认干跑、真删需二次确认 -->
            <VListItem
              prepend-icon="mdi-delete-sweep-outline"
              title="库内资产"
              subtitle="手动删已入库资产（只破「库内资产」一道闸）"
              @click="emit('open-assets')"
            />
            <!-- ★ 上面是「详情」，下面是「设置」：分隔开，别混成一串 -->
            <VDivider class="my-1" />
            <VListItem prepend-icon="mdi-tune-variant" title="插件设置" @click="emit('open-settings')" />
            <VListItem v-if="showClose" prepend-icon="mdi-close" title="关闭" @click="emit('close')" />
          </VList>
        </VMenu>
      </div>
    </header>
</template>

<style scoped>
/* P4：WorkbenchHeader 专属样式（自 index.vue 纯搬家）。
   ★ 共享选择器（magicflow-status-dot / magicflow-task-switch*）在 index.vue 各留一份。 */

/* ── 顶栏：品牌 / 动作区布局 ───────────────────────────── */
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
  margin-inline: 6px;
  align-self: center;
  background: rgba(var(--v-border-color), 0.45);
  flex: 0 0 auto;
}

.magicflow-settings-btn {
  margin-inline-start: 2px;
}

/* 「更多」⋮ 只在窄屏出现（宽屏直接展开各图标按钮） */
.magicflow-more-btn {
  display: none;
}

.magicflow-more-menu .v-list-item {
  min-block-size: 44px;
}

/* ── 状态点（与任务栏共用选择器 → 两处各留一份）────────── */
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

/* ── 窄屏（≤959px）：品牌头吸顶 / 折叠 ─────────────────── */
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

/* ── 窄屏（≤699px）────────────────────────────────────── */
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

/* ── 超窄（≤419px）────────────────────────────────────── */
@media (max-width: 419px) {
  .magicflow-page:not(.magicflow-page--compact) .magicflow-page__header,
  .magicflow-page:not(.magicflow-page--compact) .magicflow-page__identity {
    gap: 8px;
  }
}

/* ── 按预览图对齐：品牌头排版 ─────────────────────────── */
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
  background: linear-gradient(145deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
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
  background: linear-gradient(145deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
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

/* ── 窄屏（≤959px）：只留品牌 + 「更多」菜单 ──────────── */
@media (max-width: 959px) {
  /* 桌面品牌头里的切换胶囊隐藏；移动端由工具栏承担 */
  .magicflow-page__actions .magicflow-task-switch {
    display: none;
  }

  /* ★ 窄屏：顶栏只留「魔流」品牌 + 右上角「⋮ 更多」——把**所有**功能入口（推荐/云盘/跨站/豆瓣/
     健康/点播/考核/补源/设置/关闭）都收进这一个菜单，别一边留图标、一边又放菜单（≡ 两边都有）。 */
  .magicflow-page__actions .magicflow-header-create,
  .magicflow-page__actions .magicflow-recommend-wrap,
  .magicflow-page__actions .magicflow-recommend-btn,
  .magicflow-page__actions .magicflow-exam-wrap,
  .magicflow-page__actions .magicflow-exam-btn,
  .magicflow-page__actions .magicflow-cloud-btn,
  .magicflow-page__actions .magicflow-crossseed-wrap,
  .magicflow-page__actions .magicflow-crossseed-btn,
  .magicflow-page__actions .magicflow-douban-btn,
  .magicflow-page__actions .magicflow-health-wrap,
  .magicflow-page__actions .magicflow-health-btn,
  .magicflow-page__actions .magicflow-ondemand-btn,
  .magicflow-page__actions .magicflow-rescue-btn,
  .magicflow-page__actions .magicflow-sitereport-btn,
  .magicflow-page__actions .magicflow-settings-btn,
  .magicflow-page__actions .magicflow-hdr-sep,
  .magicflow-page__actions .magicflow-close-btn {
    display: none;
  }

  .magicflow-page__actions .magicflow-more-btn {
    display: inline-flex;
  }

  /* 手机端隐藏自相矛盾的运行计数胶囊（信息已由首页大数承担） */
  .magicflow-page .magicflow-enabled-chip { display: none; }
}
</style>
