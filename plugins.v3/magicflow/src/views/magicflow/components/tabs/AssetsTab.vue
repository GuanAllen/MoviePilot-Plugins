<script setup>
// MagicFlow 前端 · 库内资产（asset 页 · 手动强删入口）
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 本组件**自取数**：onMounted 调 api.assets.getAssets(0)（api 由父页 :api 下传）；
// reloadKey 变化时重拉（可选）。
import { computed, onMounted, ref, watch } from 'vue'
import { unwrapResponse } from '../../../../utils'
import AssetDeleteConfirm from '../confirm/AssetDeleteConfirm.vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  reloadKey: { type: [String, Number], default: 0 },
})

const headers = [
  { title: '', key: 'select', sortable: false, width: 44 },
  { title: '站点', key: 'site', sortable: false, width: 110 },
  { title: '标题', key: 'title', sortable: false },
  { title: '体积(GB)', key: 'size_gb', sortable: false, width: 96 },
  { title: '状态', key: 'state', sortable: false, width: 96 },
  { title: 'qB 态', key: 'qb_state', sortable: false, width: 120 },
  { title: '进度', key: 'progress', sortable: false, width: 130 },
  { title: '上传(GB)', key: 'upload_gb', sortable: false, width: 96 },
  { title: '保护状态', key: 'block', sortable: false, width: 150 },
]

const loading = ref(false)
const deleting = ref(false)
const error = ref('')
const flash = ref(null)
const items = ref([])
const counts = ref({})
const siteFilter = ref('')
const selectedHashes = ref([])
const confirmOpen = ref(false)

const siteOptions = computed(() => {
  const names = []
  for (const it of items.value) {
    const name = String(it?.site ?? '').trim()
    if (name && !names.includes(name)) names.push(name)
  }
  names.sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
  return [{ title: '全部站点', value: '' }, ...names.map(name => ({ title: name, value: name }))]
})

const visibleItems = computed(() => {
  if (!siteFilter.value) return items.value
  return items.value.filter(it => String(it?.site ?? '') === siteFilter.value)
})

const deletableVisible = computed(() => visibleItems.value.filter(it => it?.deletable === true))

const selectedItems = computed(
  () => items.value.filter(it => it?.deletable === true && selectedHashes.value.includes(it?.hash)),
)

const allSelected = computed(
  () => deletableVisible.value.length > 0
    && deletableVisible.value.every(it => selectedHashes.value.includes(it?.hash)),
)

const someSelected = computed(() => selectedHashes.value.length > 0 && !allSelected.value)

const selectedTotalGb = computed(
  () => selectedItems.value.reduce((sum, it) => sum + Number(it?.size_gb ?? 0), 0),
)

function progressPct(item) {
  const pct = Number(item?.progress ?? 0) * 100
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}
function progressText(item) {
  return `${progressPct(item)}%`
}
function progressColor(item) {
  const pct = progressPct(item)
  if (pct >= 100) return 'success'
  if (pct <= 0) return 'grey'
  return 'info'
}
function blockText(item) {
  if (item?.deletable === true) return '可删'
  return String(item?.block ?? '').trim() || '被保护'
}
function blockColor(item) {
  return item?.deletable === true ? 'success' : 'warning'
}
function stateColor(state) {
  const key = String(state ?? '').toLowerCase()
  if (['uploading', 'forcedup', 'stalledup', 'queuedup'].includes(key)) return 'success'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'checkingdl'].includes(key)) return 'info'
  if (key === 'stalleddl') return 'warning'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'grey'
}

function toggleRow(item) {
  if (!item || item.deletable !== true || !item.hash) return
  const hash = item.hash
  if (selectedHashes.value.includes(hash)) {
    selectedHashes.value = selectedHashes.value.filter(h => h !== hash)
  } else {
    selectedHashes.value = [...selectedHashes.value, hash]
  }
}
function toggleAll(value) {
  if (value) {
    selectedHashes.value = deletableVisible.value.map(it => it.hash).filter(Boolean)
  } else {
    clearSelection()
  }
}
function clearSelection() {
  selectedHashes.value = []
}
function pruneSelection() {
  const visible = new Set(visibleItems.value.map(it => it?.hash))
  selectedHashes.value = selectedHashes.value.filter(h => visible.has(h))
}

async function load() {
  const client = props.api?.assets
  if (!client || typeof client.getAssets !== 'function') {
    error.value = '资产接口未接线：请父页传 `:api`，并在 request.js 注册 `c.assets = makeAssets(c)`'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data = unwrapResponse(await client.getAssets(0)) || {}
    items.value = Array.isArray(data.items) ? data.items : []
    counts.value = data.counts || {}
    pruneSelection()
  } catch (err) {
    error.value = `读取库内资产失败：${err?.message || err}`
    items.value = []
    counts.value = {}
    clearSelection()
  } finally {
    loading.value = false
  }
}

function openConfirm() {
  if (!selectedItems.value.length) return
  confirmOpen.value = true
}

async function submitDelete(payload) {
  const client = props.api?.assets
  if (!client || typeof client.deleteAssets !== 'function') {
    flash.value = { type: 'error', text: '资产接口未接线，无法删除' }
    return
  }
  const hashes = selectedItems.value.map(it => it?.hash).filter(Boolean)
  if (!hashes.length) return
  const deleteFiles = payload?.deleteFiles === true
  deleting.value = true
  try {
    const res = await client.deleteAssets({
      hashes,
      delete_files: deleteFiles ? 1 : 0,
      confirm: 1,
      reason: '手动删除库内资产',
    })
    const data = unwrapResponse(res) || {}
    const reasons = {}
    for (const row of (data.results || [])) {
      const block = String(row?.block ?? '').trim()
      if (block) reasons[block] = (reasons[block] || 0) + 1
    }
    const reasonText = Object.entries(reasons).map(([key, count]) => `${key}×${count}`).join('、')
    const failed = Number(data.failed ?? 0)
    const base = String(res?.message ?? '').trim()
      || `删除库内资产：成功 ${Number(data.deleted ?? 0)} · 被保护 ${Number(data.blocked ?? 0)} · 失败 ${failed}`
    flash.value = {
      type: failed > 0 ? 'error' : (reasonText ? 'warning' : 'success'),
      text: `${base}${deleteFiles ? '（含文件）' : '（仅删种，保留文件）'}${reasonText ? `；被拦理由：${reasonText}` : ''}`,
    }
    confirmOpen.value = false
    clearSelection()
    await load()
  } catch (err) {
    flash.value = { type: 'error', text: `删除失败：${err?.message || err}` }
  } finally {
    deleting.value = false
  }
}

onMounted(load)
watch(() => props.reloadKey, () => { load() })
watch(siteFilter, pruneSelection)
</script>

<template>
  <VSheet tag="section" class="magicflow-panel magicflow-assets app-surface-static">
    <header class="magicflow-panel__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">魔流库内资产</div>
        <div class="text-body-2 text-medium-emphasis">
          总数 {{ Number(counts.total ?? 0) }} · 可删 {{ Number(counts.deletable ?? 0) }} · 被保护 {{ Number(counts.blocked ?? 0) }}
        </div>
      </div>
      <div class="magicflow-asset-filters">
        <VSelect
          v-model="siteFilter"
          :items="siteOptions"
          item-title="title"
          item-value="value"
          density="compact"
          variant="outlined"
          hide-details
          class="magicflow-asset-site-filter"
        />
        <VBtn
          size="small"
          variant="tonal"
          prepend-icon="mdi-refresh"
          :disabled="loading || deleting"
          @click="load"
        >
          刷新
        </VBtn>
        <VBtn
          size="small"
          variant="flat"
          color="error"
          prepend-icon="mdi-delete-outline"
          :disabled="!selectedHashes.length || deleting"
          @click="openConfirm"
        >
          删除选中 ({{ selectedHashes.length }})
        </VBtn>
      </div>
    </header>

    <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mt-3">{{ error }}</VAlert>
    <VAlert
      v-if="flash"
      :type="flash.type"
      variant="tonal"
      density="compact"
      closable
      class="mt-3"
      @click:close="flash = null"
    >
      {{ flash.text }}
    </VAlert>

    <div v-if="selectedHashes.length" class="magicflow-bulk-bar">
      <span class="magicflow-bulk-bar__count">
        已选 {{ selectedHashes.length }} 个 · {{ selectedTotalGb.toFixed(2) }} GB
      </span>
      <VSpacer />
      <VBtn size="small" variant="text" :disabled="deleting" @click="clearSelection">取消选择</VBtn>
    </div>

    <VDataTable
      class="magicflow-asset-table"
      :headers="headers"
      :items="visibleItems"
      :loading="loading"
      :items-per-page="10"
      density="comfortable"
    >
      <template #header.select>
        <VCheckbox
          :model-value="allSelected"
          :indeterminate="someSelected"
          :disabled="!deletableVisible.length"
          density="compact"
          hide-details
          aria-label="全选可删资产"
          @update:model-value="value => toggleAll(value)"
        />
      </template>
      <template #item.select="{ item }">
        <span :title="item.deletable === true ? '可删' : blockText(item)">
          <VCheckbox
            :model-value="item.deletable === true && selectedHashes.includes(item.hash)"
            :disabled="item.deletable !== true"
            density="compact"
            hide-details
            color="error"
            :aria-label="item.deletable === true ? `选择 ${item.title || ''}` : `不可选：${blockText(item)}`"
            @click.stop
            @update:model-value="toggleRow(item)"
          />
        </span>
      </template>
      <template #item.title="{ item }">
        <div class="magicflow-asset-title">
          <strong>{{ item.title || '未知种子' }}</strong>
          <span>{{ item.save_path || '' }}</span>
        </div>
      </template>
      <template #item.size_gb="{ item }">{{ Number(item.size_gb ?? 0).toFixed(2) }}</template>
      <template #item.state="{ item }">
        <VChip size="small" :color="stateColor(item.state)" variant="tonal">{{ item.state ?? '—' }}</VChip>
      </template>
      <template #item.qb_state="{ item }">
        <code>{{ item.qb_state ?? '—' }}</code>
      </template>
      <template #item.progress="{ item }">
        <div class="magicflow-asset-progress">
          <VProgressLinear
            :model-value="progressPct(item)"
            :color="progressColor(item)"
            height="6"
            rounded
          />
          <span>{{ progressText(item) }}</span>
        </div>
      </template>
      <template #item.upload_gb="{ item }">{{ Number(item.upload_gb ?? 0).toFixed(2) }}</template>
      <template #item.block="{ item }">
        <VChip size="small" :color="blockColor(item)" variant="tonal">{{ blockText(item) }}</VChip>
      </template>
      <template #no-data>
        <div class="magicflow-table-empty">
          {{ loading ? '正在读取库内资产…' : '当前筛选下没有库内资产' }}
        </div>
      </template>
    </VDataTable>

    <div class="magicflow-mobile-assets">
      <article
        v-for="item in visibleItems"
        :key="item.hash || item.title"
        class="magicflow-mobile-asset"
      >
        <div class="magicflow-mobile-asset__head">
          <span :title="item.deletable === true ? '可删' : blockText(item)">
            <VCheckbox
              :model-value="item.deletable === true && selectedHashes.includes(item.hash)"
              :disabled="item.deletable !== true"
              density="compact"
              hide-details
              color="error"
              class="magicflow-mobile-asset__check"
              @update:model-value="toggleRow(item)"
            />
          </span>
          <div class="magicflow-mobile-asset__title">
            <strong>{{ item.title || '未知种子' }}</strong>
            <span>{{ item.site ?? '' }}</span>
          </div>
          <VChip size="small" :color="blockColor(item)" variant="tonal" class="magicflow-mobile-asset__state">
            {{ blockText(item) }}
          </VChip>
        </div>
        <VProgressLinear
          :model-value="progressPct(item)"
          :color="progressColor(item)"
          height="6"
          rounded
          class="magicflow-mobile-asset__bar"
        />
        <div class="magicflow-mobile-asset__grid">
          <span><em>体积</em><b>{{ Number(item.size_gb ?? 0).toFixed(2) }} GB</b></span>
          <span><em>进度</em><b>{{ progressText(item) }}</b></span>
          <span><em>qB 态</em><b>{{ item.qb_state ?? '—' }}</b></span>
          <span><em>上传</em><b>{{ Number(item.upload_gb ?? 0).toFixed(2) }} GB</b></span>
        </div>
      </article>
      <div v-if="!visibleItems.length" class="magicflow-table-empty">
        {{ loading ? '正在读取库内资产…' : '当前筛选下没有库内资产' }}
      </div>
    </div>

    <AssetDeleteConfirm
      v-model="confirmOpen"
      :items="selectedItems"
      :loading="deleting"
      @confirm="submitDelete"
    />
  </VSheet>
</template>

<style scoped>
/* ── 共享选择器（index.vue / 兄弟 tab 同有，此处复制一份；父页原样保留）──── */
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

/* ── 本视图专属 ─────────────────────────────────────────────────── */
.magicflow-assets {
  margin-block-start: 12px;
}

.magicflow-asset-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.magicflow-asset-site-filter {
  inline-size: 13rem;
  max-inline-size: 100%;
}

.magicflow-asset-table {
  margin-block-start: 8px;
  background: transparent;
}

.magicflow-asset-table th:first-child,
.magicflow-asset-table td:first-child {
  padding-inline: 6px;
}

.magicflow-asset-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-inline-size: 30rem;
}

.magicflow-asset-title strong,
.magicflow-asset-title span {
  overflow-wrap: anywhere;
}

.magicflow-asset-title span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.78rem;
}

.magicflow-asset-progress {
  display: flex;
  align-items: center;
  gap: 8px;
}

.magicflow-asset-progress :deep(.v-progress-linear) {
  flex: 1 1 auto;
  min-inline-size: 56px;
}

.magicflow-asset-progress span {
  flex: 0 0 auto;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-mobile-assets {
  display: none;
}

.magicflow-mobile-asset {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-block: 13px;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.magicflow-mobile-asset__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.magicflow-mobile-asset__check {
  flex: 0 0 auto;
  margin-inline-end: 2px;
}

.magicflow-mobile-asset__title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-inline-size: 0;
}

.magicflow-mobile-asset__title strong {
  min-inline-size: 0;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.magicflow-mobile-asset__title span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.75rem;
}

.magicflow-mobile-asset__state {
  flex: 0 0 auto;
}

.magicflow-mobile-asset__bar {
  margin-block: 2px 4px;
}

.magicflow-mobile-asset__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 12px;
}

.magicflow-mobile-asset__grid span {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  min-inline-size: 0;
  font-size: 0.8rem;
}

.magicflow-mobile-asset__grid em {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-style: normal;
}

.magicflow-mobile-asset__grid b {
  min-inline-size: 0;
  font-weight: 500;
  text-align: end;
  overflow-wrap: anywhere;
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

.magicflow-page .magicflow-asset-title strong,
.magicflow-page .magicflow-mobile-asset__title strong {
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

  .magicflow-asset-filters {
    inline-size: 100%;
  }

  .magicflow-asset-site-filter {
    inline-size: 100%;
  }

  .magicflow-asset-table {
    display: none;
  }

  .magicflow-mobile-assets {
    display: flex;
    flex-direction: column;
    gap: 0;
    margin-block-start: 12px;
  }
}
</style>
