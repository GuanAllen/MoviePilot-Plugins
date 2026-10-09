<script setup>
// MagicFlow 前端 · 新手考核汇总弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props.data）、事件向上（emit start）；子组件不直接改父状态。
import { reactive } from 'vue'

const open = defineModel({ type: Boolean, default: false })
const props = defineProps({
  // useExam() 上下文：状态 + 派生 + 动作（props 下，只读）。
  data: { type: Object, required: true },
  narrow: { type: Boolean, default: false },
})
const emit = defineEmits(['start'])

// useExam() 返回的是「ref / computed / 函数的普通对象」；reactive() 会解包其中的 ref / computed，
// 于是模板里沿用原 index.vue 的写法 `data.examRows` / `data.examDaysShort(row)` / `data.examData.enabled`。
const data = reactive(props.data)
</script>

<template>
  <VDialog v-model="open" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-exam-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">新手考核</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" @click="data.loadExam">刷新</VBtn>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-exam-body">
        <!-- ① 概览：未过站数 + 最近截止 + 待过项 -->
        <div class="magicflow-exam-hero" :class="data.examUrgent ? 'is-urgent' : ''">
          <div class="magicflow-exam-hero__left">
            <span class="magicflow-exam-hero__num">{{ data.examPendingSites }}</span>
            <span class="magicflow-exam-hero__cap">站考核未过</span>
          </div>
          <div class="magicflow-exam-hero__right">
            <div v-if="data.examNext" class="magicflow-exam-hero__line">
              <VIcon icon="mdi-alarm" size="14" />
              最近截止：{{ data.examNext.site_name || ('站点 ' + data.examNext.site_id) }}
              <VChip size="x-small" variant="tonal" :color="data.examUrgencyColor(data.examNext)">剩 {{ data.examDaysShort(data.examNext) }}</VChip>
            </div>
            <div class="magicflow-exam-hero__line is-dim">待过 {{ data.examPendingItems }} 项 · {{ data.examUrgentWeek }} 站 7 天内截止</div>
          </div>
        </div>
        <VAlert v-if="data.examData.enabled === false" type="info" variant="tonal" density="compact" class="my-2">
          新手考核模块已关闭（可在「插件设置 → 考核」开启；开启后零额外 PV）
        </VAlert>
        <div v-else-if="!data.examRows.length" class="magicflow-table-empty">
          没有未通过的考核（或站点数据暂时取不到）。
        </div>
        <!-- ② 按「剩余天数」升序：最紧急的排在最上面 -->
        <VSheet v-for="row in data.examRows" :key="row.site_id" tag="section" class="magicflow-exam-card">
          <header class="magicflow-exam-card__head">
            <div class="magicflow-exam-card__title">
              <span class="magicflow-exam-card__name">{{ row.site_name || ('站点 ' + row.site_id) }}</span>
              <VChip v-if="!(row.exam || {}).all_pass" size="x-small" variant="tonal" :color="data.examUrgencyColor(row)">剩 {{ data.examDaysShort(row) }}</VChip>
              <VChip v-else size="x-small" variant="tonal" color="success">已完成</VChip>
              <span class="magicflow-exam-card__passed">{{ data.examPassedCount(row) }}/{{ (row.exam.items || []).length }} 已过</span>
            </div>
            <VProgressLinear
              :model-value="data.examSitePct(row)"
              height="4"
              rounded
              :color="data.examUrgencyColor(row)"
              bg-color="rgba(var(--v-theme-on-surface), 0.12)"
            />
          </header>
          <!-- 考核项：未过的在前，带进度条一眼看出还差多少 -->
          <ul class="magicflow-exam-items">
            <li
              v-for="it in data.examVisibleItems(row)"
              :key="it.idx"
              class="magicflow-exam-item"
              :class="it.pass ? 'is-pass' : 'is-fail'"
            >
              <span class="magicflow-exam-item__label">{{ it.label }}</span>
              <span v-if="data.examItemGap(it)" class="magicflow-exam-item__gap">还差 {{ data.examItemGap(it) }}</span>
              <span v-if="it.cur || it.req" class="magicflow-exam-item__val"><strong>{{ it.cur }}</strong><i> / {{ it.req }}</i></span>
              <VIcon :icon="it.pass ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'" size="14" :color="it.pass ? 'success' : 'error'" />
              <VProgressLinear
                v-if="Number(it.req_num) > 0"
                class="magicflow-exam-item__bar"
                :model-value="data.examItemPct(it)"
                height="4"
                rounded
                :color="it.pass ? 'success' : 'error'"
                bg-color="rgba(var(--v-theme-on-surface), 0.12)"
              />
            </li>
          </ul>
          <button
            v-if="data.examHiddenPassed(row) > 0"
            type="button"
            class="magicflow-exam-more"
            @click="data.examTogglePassed(row.site_id)"
          >显示已通过 {{ data.examHiddenPassed(row) }} 项</button>
          <button
            v-else-if="data.examShowPassed[row.site_id] && (row.exam.items || []).length > 1"
            type="button"
            class="magicflow-exam-more"
            @click="data.examTogglePassed(row.site_id)"
          >只看未通过</button>
          <!-- 可执行动作：同任务合并（魔力/做种积分都指向同一个任务只出一个） -->
          <div class="magicflow-exam-acts">
            <article v-for="a in data.examActions(row)" :key="a.key" class="magicflow-exam-act">
              <div class="magicflow-exam-act__head">
                <VIcon :icon="a.icon" size="15" />
                <strong>{{ a.label }}</strong>
                <VChip v-if="a.task_name" size="x-small" variant="text">{{ a.task_name }}</VChip>
                <VChip v-else-if="!a.can_run" size="x-small" variant="tonal" color="grey">{{ a.kind === 'info' ? '不建任务' : '保持做种' }}</VChip>
              </div>
              <VAlert
                v-if="a.warn"
                type="warning"
                variant="tonal"
                density="compact"
                class="magicflow-exam-act__warn"
              >{{ a.warn }}</VAlert>
              <ul v-if="a.notes.length" class="magicflow-exam-act__notes">
                <li v-for="(n, ni) in a.notes" :key="ni">{{ n }}</li>
              </ul>
              <VBtn
                v-if="a.can_run"
                size="small"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-play-circle-outline"
                :loading="data.examActing === `${a.kind}:${row.site_id}`"
                @click="emit('start', { row, kind: a.kind })"
              >一键起任务</VBtn>
            </article>
            <div v-if="!(row.plan || []).length" class="magicflow-table-empty">
              本站没有需要新任务的项目（保持做种即可）。
            </div>
          </div>
        </VSheet>
        <div class="magicflow-exam-foot">只统计「有 Cookie」的站点；已通过的默认不显示（可在「插件设置 → 考核」里改）</div>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行：随「新手考核」自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head / settings-dialog__title /
     recommend-dialog__head-actions / table-empty）父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}
.magicflow-settings-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
}
.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
}
.magicflow-recommend-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}
/* 功能弹窗统一：卡片纵向 flex + 正文吃满（原 index.vue 的共享组里含 .magicflow-exam-dialog，随组件迁入） */
.magicflow-exam-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}

/* 新手任务板面（5.5.0 重设）：概览 → 按紧急度排序的站点卡（考核项进度条）→ 合并后的动作 */
.magicflow-exam-body {
  display: grid;
  gap: 10px;
  align-content: start;
}

.magicflow-exam-hero {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.08);
  border: 1px solid rgba(var(--v-theme-primary), 0.18);
}

.magicflow-exam-hero.is-urgent {
  background: rgba(var(--v-theme-error), 0.1);
  border-color: rgba(var(--v-theme-error), 0.28);
}

.magicflow-exam-hero__left {
  display: grid;
  gap: 2px;
  min-inline-size: 3.6em;
}

.magicflow-exam-hero__num {
  font-size: 1.55rem;
  font-weight: 800;
  line-height: 1;
}

.magicflow-exam-hero__cap {
  font-size: 0.68rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  white-space: nowrap;
}

.magicflow-exam-hero__right {
  margin-inline-start: auto;
  display: grid;
  gap: 3px;
  text-align: end;
}

.magicflow-exam-hero__line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 3px 6px;
  font-size: 0.76rem;
}

.magicflow-exam-hero__line.is-dim {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.7rem;
}

.magicflow-exam-card {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}

.magicflow-exam-card__head {
  display: grid;
  gap: 6px;
  min-inline-size: 0;
}

.magicflow-exam-card__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
}

.magicflow-exam-card__name {
  font-size: 0.9rem;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-inline-size: 45%;
}

.magicflow-exam-card__passed {
  margin-inline-start: auto;
  font-size: 0.7rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  white-space: nowrap;
}

.magicflow-exam-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 7px;
}

.magicflow-exam-item {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  align-items: center;
  gap: 0 6px;
  font-size: 0.76rem;
  min-inline-size: 0;
}

.magicflow-exam-item__gap {
  font-size: 0.68rem;
  font-weight: 700;
  white-space: nowrap;
  padding: 0 5px;
  border-radius: 999px;
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.12);
}

.magicflow-exam-item.is-pass {
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}

.magicflow-exam-item__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.magicflow-exam-item__val {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.magicflow-exam-item__val i {
  font-style: normal;
  opacity: var(--mf-op-dim);
}

.magicflow-exam-item__bar {
  grid-column: 1 / -1;
  margin-block-start: 3px;
}

.magicflow-exam-more {
  justify-self: start;
  padding: 0;
  border: 0;
  background: none;
  font-size: 0.72rem;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
}

.magicflow-exam-acts {
  display: grid;
  gap: 8px;
  border-block-start: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
  padding-block-start: 8px;
}

.magicflow-exam-act {
  display: grid;
  gap: 6px;
  justify-items: start;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  min-inline-size: 0;
}

.magicflow-exam-act__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  font-size: 0.82rem;
}

.magicflow-exam-act__notes {
  margin: 0;
  padding-inline-start: 1.1em;
  font-size: 0.74rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

.magicflow-exam-act__warn {
  inline-size: 100%;
  font-size: 0.74rem !important;
}

.magicflow-exam-foot {
  font-size: 0.68rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}
</style>
