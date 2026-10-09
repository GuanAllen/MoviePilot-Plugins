<script setup>
// MagicFlow 前端 · 推荐甄别弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（recName / recommendActionable）自 composables/useRecommend.js 具名导入复用
// —— 单一真值源，不在两处各写一份（同 useHrBills 的 hrBillStateColor 做法）。
import { recommendStatusMeta, formatDateTime } from '../../../../utils'
import { recName, recommendActionable } from '../../composables/useRecommend'

// 开关走 defineModel（Boolean）；「显示全部候选」是列表展示态，同样两向绑定，子不直接改父 state。
const open = defineModel({ type: Boolean, default: false })
const showAllRecs = defineModel('showAllRecs', { type: Boolean, default: false })

// 推荐域（useRecommend）：data / items / acting / hidden / confirmed / pending
// 批量入库域（useRecImport）：selected / selectable / selectedList / allChecked / batchActing
// 壳：narrow（窄屏全屏）
defineProps({
  data: { type: Object, default: () => ({}) },
  items: { type: Array, default: () => [] },
  acting: { type: String, default: '' },
  hidden: { type: Number, default: 0 },
  confirmed: { type: Number, default: 0 },
  pending: { type: Number, default: 0 },
  selected: { type: Object, default: () => ({}) },
  selectable: { type: Array, default: () => [] },
  selectedList: { type: Array, default: () => [] },
  allChecked: { type: Boolean, default: false },
  batchActing: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits([
  'refresh',
  'confirm',
  'dismiss',
  'toggle-rec',
  'toggle-all',
  'batch-import',
])
</script>

<template>
  <VDialog v-model="open" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-recommend-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">推荐甄别</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" @click="emit('refresh')">刷新</VBtn>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-recommend-dialog__body">
        <div class="magicflow-recommend-dialog__summary">
          <span><strong>{{ data.recommended || 0 }}</strong> 待确认</span>
          <i>·</i>
          <span><strong>{{ confirmed }}</strong> 已入库</span>
          <i>·</i>
          <span><strong>{{ pending }}</strong> 未达门槛</span>
          <i>·</i>
          <span>共 {{ data.total || 0 }} 条</span>
          <i>·</i>
          <span>标签 {{ data.tag || '魔流-推荐' }}</span>
        </div>
        <div class="magicflow-recommend-dialog__note">
          评分 &gt; {{ data.min_rating ?? 7.5 }}<template v-if="data.require_chart !== false"> 或在榜 / 热映 / 订阅</template>
          · 过期 {{ data.expire_days ?? 7 }} 天 · 磁盘余量下限 {{ data.disk_min_free_gb ?? 50 }}G
        </div>
        <VAlert v-if="data.enabled === false" type="info" variant="tonal" density="compact" class="my-2">
          推荐甄别已关闭（可在「插件设置 → 推荐」开启）
        </VAlert>
        <VSheet tag="section" class="magicflow-panel app-surface-static mt-2">
          <header class="magicflow-panel__head">
            <div>
              <div class="text-subtitle-2 font-weight-medium">甄别结果</div>
              <div class="text-body-2 text-medium-emphasis">全部任务汇总 · 确认 = 自动整理入库；忽略 = 删除该临时种（«待核实»也可手动确认）</div>
            </div>
            <div class="d-flex align-center flex-wrap ga-2 justify-end">
              <VBtn
                v-if="selectable.length"
                size="small"
                variant="text"
                :prepend-icon="allChecked ? 'mdi-checkbox-multiple-marked-outline' : 'mdi-checkbox-multiple-blank-outline'"
                @click="emit('toggle-all')"
              >{{ allChecked ? '取消全选' : `全选 (${selectable.length})` }}</VBtn>
              <VBtn
                size="small"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-tray-arrow-down"
                :disabled="!selectedList.length"
                :loading="batchActing"
                @click="emit('batch-import', false)"
              >批量入库 ({{ selectedList.length }})</VBtn>
              <VBtn
                v-if="selectable.length"
                size="small"
                variant="text"
                :loading="batchActing"
                @click="emit('batch-import', true)"
              >全部入库</VBtn>
              <VBtn
                size="small"
                variant="text"
                color="primary"
                :prepend-icon="showAllRecs ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
                @click="showAllRecs = !showAllRecs"
              >{{ showAllRecs ? '仅看推荐' : (hidden ? `显示全部候选 (+${hidden})` : '显示全部候选') }}</VBtn>
            </div>
          </header>
          <div class="magicflow-recs">
            <article v-for="rec in items" :key="rec.hash" class="magicflow-rec" :class="{ 'magicflow-rec--sel': recommendActionable(rec) }">
              <VCheckbox
                v-if="recommendActionable(rec)"
                :model-value="!!selected[rec.hash]"
                density="compact"
                hide-details
                class="magicflow-rec__check"
                :aria-label="`选择 ${recName(rec)}`"
                @update:model-value="emit('toggle-rec', rec.hash)"
              />
              <div class="magicflow-rec__poster">
                <img v-if="rec.poster" :src="rec.poster" :alt="recName(rec)" loading="lazy" referrerpolicy="no-referrer" />
                <VIcon v-else icon="mdi-movie-open-outline" size="22" />
              </div>
              <div class="magicflow-rec__main">
                <strong :title="rec.title || rec.hash">{{ recName(rec) }}</strong>
                <span class="magicflow-rec__meta">
                  <VChip size="x-small" variant="tonal" :color="recommendStatusMeta(rec.status).color">{{ recommendStatusMeta(rec.status).text }}</VChip>
                  <template v-if="rec.media && rec.media.type"> · {{ rec.media.type }}</template>
                  <template v-if="rec.rating"> · 评分 {{ Number(rec.rating).toFixed(1) }}</template>
                  <template v-if="rec.size_gb"> · {{ Number(rec.size_gb).toFixed(2) }}G</template>
                  <template v-if="rec.in_chart"> · 在榜</template>
                  <template v-if="rec.in_subscribe"> · 已订阅</template>
                </span>
                <span class="magicflow-rec__sub">
                  首次发现 {{ formatDateTime(rec.first_seen) }}
                  <template v-if="rec.import_result"> · {{ rec.import_result }}</template>
                  <template v-if="rec.note"> · {{ rec.note }}</template>
                </span>
              </div>
              <div v-if="recommendActionable(rec)" class="magicflow-rec__actions">
                <VBtn
                  size="small"
                  color="primary"
                  variant="tonal"
                  prepend-icon="mdi-check"
                  :loading="acting === rec.hash + 'confirm'"
                  @click="emit('confirm', rec.hash)"
                >
                  确认入库
                </VBtn>
                <VBtn
                  size="small"
                  color="error"
                  variant="text"
                  prepend-icon="mdi-delete-outline"
                  :loading="acting === rec.hash + 'dismiss'"
                  @click="emit('dismiss', rec.hash)"
                >
                  忽略删除
                </VBtn>
              </div>
            </article>
            <div v-if="!items.length" class="magicflow-table-empty">
              暂无推荐{{ showAllRecs ? '' : '（当前没有同时满足「评分 > ' + (data.min_rating ?? 7.5) + ' 且在榜 / 热映 / 订阅」的资源）' }}。
              <template v-if="!showAllRecs && hidden">可点右上「显示全部候选 (+{{ hidden }})」看全部评估（含未达门槛的临时种）。</template>
            </div>
          </div>
        </VSheet>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 正文：随「推荐甄别弹窗」自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head（含 i）/ settings-dialog__title /
     recommend-dialog__head-actions / panel / panel__head / table-empty）父页其它弹窗也在用
     → 两处各留一份（纯复制，零改动）。⚠️ VDialog 会 teleport 到 body，父 scoped 规则够不到子内部，
     组件内必须自带这些共享规则。── */
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
.magicflow-panel {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
  min-inline-size: 0;
  padding: 16px;
}
.magicflow-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

/* ── 推荐甄别弹窗（专属）──────────────────────────────────────────── */
.magicflow-recommend-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}
.magicflow-recommend-dialog__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  font-size: 0.85rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-recommend-dialog__summary strong {
  font-size: 1.05rem;
  color: rgb(var(--v-theme-primary));
}
.magicflow-recommend-dialog__summary i {
  font-style: normal;
  opacity: var(--mf-op-dim);
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.magicflow-recommend-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  opacity: 0.85;
}
.magicflow-recommend-dialog__body {
  max-block-size: min(68dvh, 42rem);
  overflow-y: auto;
  overscroll-behavior: contain;
}
.magicflow-recommend-dialog__body {
  flex: 1 1 auto;
  min-block-size: 0;
  max-block-size: none;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.magicflow-rec {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding-block: 8px;
}
/* 可勾选的行多一列「复选框」（无勾选的行保持三列，避免整体错位） */
.magicflow-rec--sel {
  grid-template-columns: auto auto minmax(0, 1fr) auto;
}
.magicflow-rec__check {
  flex: 0 0 auto;
  margin-inline: -6px -2px;
}
.magicflow-rec__poster {
  inline-size: 40px;
  block-size: 60px;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-rec__poster img {
  inline-size: 100%;
  block-size: 100%;
  object-fit: cover;
  display: block;
}
.magicflow-rec__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-inline-size: 0;
}
.magicflow-rec__main > strong {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.magicflow-rec__meta,
.magicflow-rec__sub {
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  font-size: 0.8rem;
  overflow-wrap: anywhere;
}
.magicflow-rec__actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

@media (max-width: 699px) {
  .magicflow-rec {
    grid-template-columns: auto minmax(0, 1fr);
  }
  .magicflow-rec--sel {
    grid-template-columns: auto auto minmax(0, 1fr);
  }
  .magicflow-rec__actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}
@media (max-width: 699px) {
  .magicflow-panel { padding: 14px; }
  .magicflow-panel__head { flex-wrap: wrap; flex-direction: column; align-items: flex-start; }
}
</style>
