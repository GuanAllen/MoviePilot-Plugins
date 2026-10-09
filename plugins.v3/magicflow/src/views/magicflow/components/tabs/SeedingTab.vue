<script setup>
// MagicFlow 前端 · 托管做种明细（种子池 · poolView === 'torrents'）
// P4：自 views/magicflow/index.vue 纯搬家（模板 + 配套 scoped 样式），无行为/样式变更。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
import { formatBytes } from '../../../../utils'
import { TORRENT_STATE_TEXT } from '../../constants'
import { TORRENT_TRANSIENT_STATES } from '../../constants'
import { TORRENT_PAUSED_STATES } from '../../constants'

// rows=已按筛选/状态过滤+排序后的行；真值源仍在 useSeeding。
defineProps({
  rows: { type: Array, default: () => [] },
  headers: { type: Array, default: () => [] },
  statusOptions: { type: Array, default: () => [] },
  selectedHashes: { type: Array, default: () => [] },
  allSelected: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
})

// 子组件不直接改父状态 → 用 model 回传（父 v-model:filter / v-model:status-filter）。
const filter = defineModel('filter', { type: String, default: 'all' })
const statusFilter = defineModel('statusFilter', { type: String, default: 'all' })

const emit = defineEmits([
  'batch',
  'transfer',
  'batch-delete',
  'select-all',
  'clear-selection',
  'toggle-row',
  'row-click',
  'torrent-action',
  'delete',
  'open-detail',
])

// 展示态纯函数（真值源仍在 useSeeding；此处为 P4 拆分随模板搬入的同口径实现）。
function stateLabel(state) {
  const key = String(state || '').toLowerCase()
  return TORRENT_STATE_TEXT[key] || (key ? state : '托管中')
}
function stateColor(state) {
  const key = String(state || '').toLowerCase()
  if (['uploading', 'forcedup', 'stalledup', 'queuedup'].includes(key)) return 'success'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'checkingdl'].includes(key)) return 'info'
  if (key === 'stalleddl') return 'warning'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'grey'
}
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}
function torrentStateText(item) {
  const key = String(item?.state || '').toLowerCase()
  if (TORRENT_TRANSIENT_STATES[key]) return TORRENT_TRANSIENT_STATES[key]
  if (TORRENT_PAUSED_STATES.includes(key)) return stateLabel(item?.state) || '已暂停'
  const pct = torrentProgressPct(item)
  if (pct >= 100) return '做种中'
  if (pct <= 0) return stateLabel(item?.state) || '等待中'
  return `下载 ${pct}%`
}
function torrentIsPaused(item) {
  return TORRENT_PAUSED_STATES.includes(String(item?.state || '').toLowerCase())
}
function torrentPauseLabel(item) {
  return torrentProgressPct(item) >= 100 ? '暂停做种' : '暂停下载'
}
function torrentResumeLabel(item) {
  return torrentProgressPct(item) >= 100 ? '恢复做种' : '继续下载'
}
</script>

<template>
  <VSheet tag="section" class="magicflow-panel magicflow-torrents app-surface-static">
    <header class="magicflow-panel__head">
      <div class="text-body-2 text-medium-emphasis">
        点击任意行查看详情 / 手动保留 / 删除
      </div>
      <div class="magicflow-torrent-filters">
        <VSelect
          v-model="statusFilter"
          :items="statusOptions"
          item-title="title"
          item-value="value"
          density="compact"
          variant="outlined"
          hide-details
          class="magicflow-status-filter"
        />
        <VBtnToggle v-model="filter" mandatory color="primary" density="compact">
          <VBtn value="all">全部</VBtn>
          <VBtn value="protected">已保护</VBtn>
        </VBtnToggle>
      </div>
    </header>

    <div v-if="selectedHashes.length" class="magicflow-bulk-bar">
      <span class="magicflow-bulk-bar__count">已选 {{ selectedHashes.length }} 个</span>
      <VBtn size="small" variant="tonal" :disabled="busy" @click="emit('batch', 'protect')">保留</VBtn>
      <VBtn size="small" variant="tonal" :disabled="busy" @click="emit('batch', 'unprotect')">取消保留</VBtn>
      <VBtn size="small" variant="tonal" :disabled="busy" @click="emit('batch', 'pause')">暂停</VBtn>
      <VBtn size="small" variant="tonal" :disabled="busy" @click="emit('batch', 'resume')">恢复</VBtn>
      <VBtn size="small" variant="tonal" :disabled="busy" @click="emit('batch', 'recheck')">校验</VBtn>
      <VBtn size="small" variant="tonal" color="primary" :disabled="busy" @click="emit('transfer')">批量转移</VBtn>
      <VBtn size="small" variant="tonal" color="error" :disabled="busy" @click="emit('batch-delete')">删除</VBtn>
      <VSpacer />
      <VBtn size="small" variant="text" :disabled="busy" @click="emit('select-all')">全选筛选（{{ rows.length }}）</VBtn>
      <VBtn size="small" variant="text" :disabled="busy" @click="emit('clear-selection')">取消选择</VBtn>
    </div>

    <VDataTable
      class="magicflow-torrent-table torrent-table-clickable"
      :headers="headers"
      :items="rows"
      :loading="loading"
      :items-per-page="10"
      density="comfortable"
      @click:row="(event, payload) => emit('row-click', event, payload)"
    >
      <template #header.select>
        <VCheckbox
          :model-value="allSelected"
          :indeterminate="selectedHashes.length > 0 && !allSelected"
          density="compact"
          hide-details
          aria-label="全选"
          @update:model-value="value => (value ? emit('select-all') : emit('clear-selection'))"
        />
      </template>
      <template #item.select="{ item }">
        <VCheckbox
          :model-value="selectedHashes.includes(item.hash)"
          density="compact"
          hide-details
          :aria-label="`选择 ${item.title || ''}`"
          @click.stop
          @update:model-value="emit('toggle-row', item)"
        />
      </template>
      <template #item.title="{ item }">
        <div class="torrent-title-cell">
          <strong>{{ item.title || '未知种子' }}</strong>
          <span>{{ task.site_name }}</span>
        </div>
      </template>
      <template #item.status="{ item }">
        <VChip size="small" :color="stateColor(item.state)" variant="tonal">{{ torrentStateText(item) }}</VChip>
      </template>
      <template #item.size_gb="{ item }">{{ Number(item.size_gb || 0).toFixed(2) }} GB</template>
      <template #item.uploaded="{ item }">{{ formatBytes(item.uploaded) }}</template>
      <template #item.ratio="{ item }">{{ Number(item.ratio || 0).toFixed(2) }}</template>
      <template #item.actions="{ item }">
        <VBtn
          size="small"
          variant="text"
          :icon="item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline'"
          :aria-label="item.is_protected ? '取消保留' : '保留'"
          @click="emit('torrent-action', item, item.is_protected ? 'unprotect' : 'protect')"
        />
        <VBtn
          size="small"
          variant="text"
          color="error"
          icon="mdi-delete-outline"
          aria-label="删除"
          @click="emit('delete', item)"
        />
        <VMenu location="bottom end">
          <template #activator="{ props: menuProps }">
            <VBtn v-bind="menuProps" size="small" variant="text" icon="mdi-dots-vertical" aria-label="更多操作" />
          </template>
          <VList density="compact" min-width="168">
            <VListItem
              v-if="torrentIsPaused(item)"
              prepend-icon="mdi-play-circle-outline"
              :title="torrentResumeLabel(item)"
              @click="emit('torrent-action', item, 'resume')"
            />
            <VListItem
              v-else
              prepend-icon="mdi-pause-circle-outline"
              :title="torrentPauseLabel(item)"
              subtitle="不会被自动恢复"
              @click="emit('torrent-action', item, 'pause')"
            />
            <VListItem prepend-icon="mdi-sync" title="强制校验" @click="emit('torrent-action', item, 'recheck')" />
            <VDivider class="my-1" />
            <VListItem prepend-icon="mdi-delete-outline" title="删除种子" base-color="error" @click="emit('delete', item)" />
          </VList>
        </VMenu>
      </template>
      <template #no-data>
        <div class="magicflow-table-empty">当前筛选下没有托管种子</div>
      </template>
    </VDataTable>
    <div class="magicflow-mobile-torrents">
      <article
        v-for="item in rows"
        :key="item.hash || item.title"
        class="magicflow-mobile-torrent"
        @click="emit('open-detail', item)"
      >
        <div class="magicflow-mobile-torrent__head">
          <VCheckbox
            :model-value="selectedHashes.includes(item.hash)"
            density="compact"
            hide-details
            class="magicflow-mobile-torrent__check"
            @click.stop
            @update:model-value="emit('toggle-row', item)"
          />
          <div class="magicflow-mobile-torrent__title">
            <strong>{{ item.title || '未知种子' }}</strong>
            <span>{{ task.site_name }}</span>
          </div>
          <VChip size="small" :color="stateColor(item.state)" variant="tonal" class="magicflow-mobile-torrent__state">
            {{ torrentStateText(item) }}
          </VChip>
        </div>
        <VProgressLinear
          :model-value="torrentProgressPct(item)"
          :color="stateColor(item.state)"
          height="6"
          rounded
          class="magicflow-mobile-torrent__bar"
        />
        <div class="magicflow-mobile-torrent__grid">
          <span><em>大小</em><b>{{ Number(item.size_gb || 0).toFixed(2) }} GB</b></span>
          <span><em>上传量</em><b>{{ formatBytes(item.uploaded) }}</b></span>
          <span><em>分享率</em><b>{{ Number(item.ratio || 0).toFixed(2) }}</b></span>
        </div>
        <div class="magicflow-mobile-torrent__actions">
          <VBtn size="small" variant="tonal" :color="item.is_protected ? 'grey' : 'primary'" :prepend-icon="item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline'" @click.stop="emit('torrent-action', item, item.is_protected ? 'unprotect' : 'protect')">
            {{ item.is_protected ? '取消保留' : '保留' }}
          </VBtn>
          <VBtn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click.stop="emit('delete', item)">删除</VBtn>
          <VBtn
            v-if="torrentIsPaused(item)"
            size="small"
            variant="tonal"
            prepend-icon="mdi-play-circle-outline"
            @click.stop="emit('torrent-action', item, 'resume')"
          >{{ torrentProgressPct(item) >= 100 ? '恢复' : '继续' }}</VBtn>
          <VBtn v-else size="small" variant="tonal" prepend-icon="mdi-pause-circle-outline" @click.stop="emit('torrent-action', item, 'pause')">暂停</VBtn>
          <VBtn size="small" variant="tonal" prepend-icon="mdi-sync" @click.stop="emit('torrent-action', item, 'recheck')">校验</VBtn>
        </div>
      </article>
      <div v-if="!rows.length" class="magicflow-table-empty">当前筛选下没有托管种子</div>
    </div>
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

.magicflow-torrent-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

/* ── 本视图专属（自 index.vue 搬入）────────────────────────────────── */
.magicflow-torrents {
  margin-block-start: 12px;
}

.magicflow-status-filter {
  inline-size: 13rem;
  max-inline-size: 100%;
}

.magicflow-bulk-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block: 10px 4px;
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.12);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.28);
}

.magicflow-bulk-bar__count {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  margin-inline-end: 4px;
}

.magicflow-mobile-torrent__check {
  flex: 0 0 auto;
  margin-inline-end: 2px;
}

.magicflow-torrent-table th:first-child,
.magicflow-torrent-table td:first-child {
  padding-inline: 6px;
}

.magicflow-torrent-table {
  margin-block-start: 8px;
  background: transparent;
}

.torrent-table-clickable :deep(tbody tr) {
  cursor: pointer;
}

.torrent-title-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-inline-size: 30rem;
}

.torrent-title-cell strong,
.torrent-title-cell span {
  overflow-wrap: anywhere;
}

.torrent-title-cell span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.78rem;
}

.magicflow-mobile-torrents {
  display: none;
}

.magicflow-mobile-torrent__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.magicflow-mobile-torrent__title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-inline-size: 0;
}

.magicflow-mobile-torrent__title strong {
  min-inline-size: 0;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.magicflow-mobile-torrent__title span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.75rem;
}

.magicflow-mobile-torrent__state {
  flex: 0 0 auto;
}

.magicflow-mobile-torrent__bar {
  margin-block: 2px 4px;
}

.magicflow-mobile-torrent__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 12px;
}

.magicflow-mobile-torrent__grid span {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  min-inline-size: 0;
  font-size: 0.8rem;
}

.magicflow-mobile-torrent__grid em {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-style: normal;
}

.magicflow-mobile-torrent__grid b {
  min-inline-size: 0;
  font-weight: 500;
  text-align: end;
  overflow-wrap: anywhere;
}

.magicflow-mobile-torrent__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.magicflow-page .torrent-title-cell strong,
.magicflow-page .magicflow-mobile-torrent__title strong {
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

  .magicflow-torrent-table {
    display: none;
  }

  .magicflow-torrent-filters {
    inline-size: 100%;
    flex-wrap: wrap;
  }

  .magicflow-status-filter {
    inline-size: 100%;
  }

  .magicflow-mobile-torrents {
    display: flex;
    flex-direction: column;
    gap: 0;
    margin-block-start: 12px;
  }

  .magicflow-mobile-torrent {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-block: 13px;
    border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    cursor: pointer;
  }

  .magicflow-mobile-torrent__head {
    align-items: flex-start;
    gap: 8px;
  }

  .magicflow-mobile-torrent__head strong {
    min-inline-size: 0;
    overflow-wrap: anywhere;
  }
}
</style>
