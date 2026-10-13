<script setup>
// MagicFlow 前端 · 库内资产（asset 页 · 手动强删入口）
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 本组件**自取数**：onMounted 调 api.assets.getAssets(0)（api 由父页 :api 下传）；
// reloadKey 变化时重拉（可选）。
// ★ 2026-10-10：列表改为**资产（资源）粒度**——一条 = 一份资源（本体 + 各站全部辅种），
//   显示 resource 名（不是单个种名）；删除 = 该资源整组（删文件 + 删种 + 连带所有辅种）。
import { computed, onMounted, ref, watch } from 'vue'
import { epLabelFromName, unwrapResponse } from '../../../../utils'
import AssetDeleteConfirm from '../confirm/AssetDeleteConfirm.vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  reloadKey: { type: [String, Number], default: 0 },
})

// ★ 15.8.21：资源级「季 / 集」标签——取自**本体种**（source_hash）的种子名；
// 本体种缺失时退回首成员。仅作展示，不参与删除判定。
function assetSeedName(item) {
  const ms = Array.isArray(item?.members) ? item.members : []
  const src = ms.find(m => m && m.hash === item?.source_hash)
  return String((src || ms[0] || {}).title || '')
}
function assetEpLabel(item) {
  return epLabelFromName(assetSeedName(item))
}

// ★ 15.9.0：行内养护动作（保护 / 订阅 / 整理 / 刮削）——删除仍走选中 + 顶部按钮
const ACTIONS = [
  { key: 'protect', label: '保护', icon: 'mdi-shield-lock-outline', color: 'success' },
  { key: 'subscribe', label: '订阅整季', icon: 'mdi-playlist-plus', color: 'indigo',
    hint: '在 MoviePilot 订阅这份资源的「剧+季」补齐缺集；再点一次退订' },
  { key: 'organize', label: '整理', icon: 'mdi-folder-move-outline', color: 'primary' },
  { key: 'scrape', label: '刮削', icon: 'mdi-image-search-outline', color: 'deep-purple' },
]

const headers = [
  { title: '', key: 'select', sortable: false, width: 44 },
  { title: '资源', key: 'name', sortable: false },
  { title: '来源站', key: 'source_site', sortable: false, width: 110 },
  { title: '成员站', key: 'sites', sortable: false, width: 150 },
  { title: '成员', key: 'members_in_qb', sortable: false, width: 88 },
  { title: '体积(GB)', key: 'size_gb', sortable: false, width: 96 },
  { title: '保护状态', key: 'block', sortable: false, width: 150 },
  { title: '养护', key: 'act', sortable: false, width: 300 },
]

const loading = ref(false)
const deleting = ref(false)
const error = ref('')
const flash = ref(null)
const items = ref([])
const counts = ref({})
const siteFilter = ref('')
const includeStale = ref(false)
const selectedIds = ref([])
const confirmOpen = ref(false)
const acting = ref('')
const onlyProtected = ref(false)

const siteOptions = computed(() => {
  const names = []
  for (const it of items.value) {
    const site = String(it?.source_site ?? '').trim()
    if (site && !names.includes(site)) names.push(site)
  }
  names.sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
  return [{ title: '全部来源站', value: '' }, ...names.map(name => ({ title: name, value: name }))]
})

const visibleItems = computed(() => {
  let list = items.value
  if (siteFilter.value) list = list.filter(it => String(it?.source_site ?? '') === siteFilter.value)
  if (onlyProtected.value) list = list.filter(it => it?.protected === true)
  return list
})

const deletableVisible = computed(() => visibleItems.value.filter(it => it?.deletable === true))

const selectedItems = computed(
  () => items.value.filter(it => it?.deletable === true && selectedIds.value.includes(it?.resource_id)),
)

const allSelected = computed(
  () => deletableVisible.value.length > 0
    && deletableVisible.value.every(it => selectedIds.value.includes(it?.resource_id)),
)

const someSelected = computed(() => selectedIds.value.length > 0 && !allSelected.value)

const selectedTotalGb = computed(
  () => selectedItems.value.reduce((sum, it) => sum + Number(it?.size_gb ?? 0), 0),
)

const selectedSeedCount = computed(
  () => selectedItems.value.reduce((sum, it) => sum + Number(it?.members_in_qb ?? 0), 0),
)

function blockText(item) {
  if (item?.deletable === true) return '可删'
  const full = String(item?.block ?? '').trim() || '被保护'
  // 列表里只显示短标签，长原因（如 H&R 义务）截断 + 悬停看全文，避免把卡片撑爆
  return full.length > 12 ? `${full.slice(0, 12)}…` : full
}
function blockColor(item) {
  return item?.deletable === true ? 'success' : 'warning'
}
function sitesText(item) {
  const list = (item?.sites || []).filter(Boolean)
  if (!list.length) return '—'
  return list.join('、')
}
function membersText(item) {
  const live = Number(item?.members_in_qb ?? 0)
  const total = Number(item?.member_count ?? 0)
  if (!total) return String(live)
  return total === live ? `${live}` : `${live}/${total}`
}

function toggleRow(item) {
  if (!item || item.deletable !== true || !item.resource_id) return
  const rid = item.resource_id
  if (selectedIds.value.includes(rid)) {
    selectedIds.value = selectedIds.value.filter(x => x !== rid)
  } else {
    selectedIds.value = [...selectedIds.value, rid]
  }
}
function toggleAll(value) {
  if (value) {
    selectedIds.value = deletableVisible.value.map(it => it.resource_id).filter(Boolean)
  } else {
    clearSelection()
  }
}
// ★ 15.9.0：单条资源的养护动作（protect / unprotect / subscribe / unsubscribe / organize / scrape）
async function act(item, action, label) {
  const client = props.api?.assets
  if (!client || typeof client.actAssets !== 'function') {
    flash.value = { type: 'error', text: '资产接口未接线，无法执行' }
    return
  }
  const rid = String(item?.resource_id ?? '').trim()
  if (!rid || acting.value) return
  acting.value = rid + action
  try {
    const res = await client.actAssets({ action, resource_ids: [rid] })
    const data = unwrapResponse(res) || {}
    const row = (data.results || [])[0] || {}
    const ok = row.ok === true
    flash.value = {
      type: ok ? 'success' : 'warning',
      text: `${label}「${item?.name || rid}」：${row.message || res?.message || (ok ? '完成' : '未生效')}`,
    }
    await load()
  } catch (err) {
    flash.value = { type: 'error', text: `${label}失败：${err?.response?.data?.message || err?.message || err}` }
  } finally {
    acting.value = ''
  }
}

function protectLabel(item) {
  return item?.protected === true ? '取消保护' : '保护'
}
function protectAction(item) {
  return item?.protected === true ? 'unprotect' : 'protect'
}

function clearSelection() {
  selectedIds.value = []
}
function pruneSelection() {
  const visible = new Set(visibleItems.value.map(it => it?.resource_id))
  selectedIds.value = selectedIds.value.filter(id => visible.has(id))
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
    const data = unwrapResponse(await client.getAssets(0, includeStale.value)) || {}
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
  const resourceIds = selectedItems.value.map(it => it?.resource_id).filter(Boolean)
  if (!resourceIds.length) return
  const deleteFiles = payload?.deleteFiles === true
  deleting.value = true
  try {
    const res = await client.deleteAssets({
      resource_ids: resourceIds,
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
watch(includeStale, () => { load() })
</script>

<template>
  <VSheet tag="section" class="magicflow-panel magicflow-assets app-surface-static">
    <header class="magicflow-panel__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">魔流库内资源管理</div>
        <div class="text-body-2 text-medium-emphasis">
          共 {{ Number(counts.total ?? 0) }} 份资源 · 可删 {{ Number(counts.deletable ?? 0) }} · 被保护 {{ Number(counts.blocked ?? 0) }}
          · 手动保留 {{ Number(counts.manual_keep ?? 0) }}
        </div>
        <div class="magicflow-asset-hint">
          保护=手动保留（永不自动删） · 订阅整季=让 MoviePilot 补这季缺的集（不动本资源文件）
          · 整理=换个地方再入库 · 刮削=纠错元数据。慢动作都在后台跑，关页面不断。
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
        <VSwitch
          v-model="includeStale"
          density="compact"
          hide-details
          color="warning"
          label="含账本残留"
          class="magicflow-asset-stale-switch"
        />
        <VSwitch
          v-model="onlyProtected"
          density="compact"
          hide-details
          color="success"
          label="只看已保护"
          class="magicflow-asset-stale-switch"
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
          :disabled="!selectedIds.length || deleting"
          @click="openConfirm"
        >
          删除选中 ({{ selectedIds.length }})
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

    <div v-if="selectedIds.length" class="magicflow-bulk-bar">
      <span class="magicflow-bulk-bar__count">
        已选 {{ selectedIds.length }} 份资源 · {{ selectedSeedCount }} 个种 · {{ selectedTotalGb.toFixed(2) }} GB
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
            :model-value="item.deletable === true && selectedIds.includes(item.resource_id)"
            :disabled="item.deletable !== true"
            density="compact"
            hide-details
            color="error"
            :aria-label="item.deletable === true ? `选择 ${item.name || ''}` : `不可选：${blockText(item)}`"
            @click.stop
            @update:model-value="toggleRow(item)"
          />
        </span>
      </template>
      <template #item.name="{ item }">
        <div class="magicflow-asset-title">
          <strong>{{ item.name || '未命名资源' }}</strong>
          <span v-if="assetEpLabel(item)" class="magicflow-asset-ep">{{ assetEpLabel(item) }}</span>
          <span v-if="item.stale">仅账本残留（不在下载器）</span>
        </div>
      </template>
      <template #item.source_site="{ item }">{{ item.source_site || '—' }}</template>
      <template #item.sites="{ item }">{{ sitesText(item) }}</template>
      <template #item.members_in_qb="{ item }">{{ membersText(item) }}</template>
      <template #item.size_gb="{ item }">{{ Number(item.size_gb ?? 0).toFixed(2) }}</template>
      <template #item.block="{ item }">
        <div class="magicflow-asset-blocks">
          <VChip size="small" :color="blockColor(item)" variant="tonal">{{ blockText(item) }}</VChip>
          <VChip v-if="item.protected" size="small" color="success" variant="tonal">手动保留</VChip>
        </div>
      </template>
      <template #item.act="{ item }">
        <div class="magicflow-asset-act">
          <VBtn
            size="x-small" variant="tonal"
            :color="item.protected ? 'grey' : 'success'"
            :prepend-icon="item.protected ? 'mdi-shield-off-outline' : 'mdi-shield-lock-outline'"
            :loading="acting === String(item.resource_id) + protectAction(item)"
            @click="act(item, protectAction(item), protectLabel(item))"
          >{{ protectLabel(item) }}</VBtn>
          <VBtn
            v-for="a in ACTIONS.filter(x => x.key !== 'protect')"
            :key="a.key"
            size="x-small" variant="tonal" :color="a.color"
            :prepend-icon="a.icon"
            :loading="acting === String(item.resource_id) + a.key"
            :title="a.hint || a.label"
            @click="act(item, a.key, a.label)"
          >{{ a.label }}</VBtn>
        </div>
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
        :key="item.resource_id || item.name"
        class="magicflow-mobile-asset"
      >
        <div class="magicflow-mobile-asset__head">
          <span :title="item.deletable === true ? '可删' : blockText(item)">
            <VCheckbox
              :model-value="item.deletable === true && selectedIds.includes(item.resource_id)"
              :disabled="item.deletable !== true"
              density="compact"
              hide-details
              color="error"
              class="magicflow-mobile-asset__check"
              @update:model-value="toggleRow(item)"
            />
          </span>
          <div class="magicflow-mobile-asset__title">
            <strong>{{ item.name || '未命名资源' }}</strong>
            <span v-if="assetEpLabel(item)" class="magicflow-asset-ep">{{ assetEpLabel(item) }}</span>
            <span class="magicflow-mobile-asset__sites" :title="sitesText(item)">{{ sitesText(item) }}</span>
          </div>
          <VChip
            size="small"
            :color="blockColor(item)"
            variant="tonal"
            class="magicflow-mobile-asset__state"
            :title="String(item?.block ?? '').trim() || (item?.deletable === true ? '可删' : '被保护')"
          >
            {{ blockText(item) }}
          </VChip>
        </div>
        <div class="magicflow-mobile-asset__grid">
          <span><em>来源站</em><b>{{ item.source_site || '—' }}</b></span>
          <span><em>成员</em><b>{{ membersText(item) }} 个种</b></span>
          <span><em>体积</em><b>{{ Number(item.size_gb ?? 0).toFixed(2) }} GB</b></span>
        </div>
        <div class="magicflow-asset-act magicflow-asset-act--mobile">
          <VBtn
            size="x-small" variant="tonal"
            :color="item.protected ? 'grey' : 'success'"
            :prepend-icon="item.protected ? 'mdi-shield-off-outline' : 'mdi-shield-lock-outline'"
            :loading="acting === String(item.resource_id) + protectAction(item)"
            @click="act(item, protectAction(item), protectLabel(item))"
          >{{ protectLabel(item) }}</VBtn>
          <VBtn
            v-for="a in ACTIONS.filter(x => x.key !== 'protect')"
            :key="a.key"
            size="x-small" variant="tonal" :color="a.color"
            :prepend-icon="a.icon"
            :loading="acting === String(item.resource_id) + a.key"
            :title="a.hint || a.label"
            @click="act(item, a.key, a.label)"
          >{{ a.label }}</VBtn>
          <VChip v-if="item.protected" size="x-small" color="success" variant="tonal">手动保留</VChip>
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
/* ★ 15.9.0：行内养护动作按钮组（桌面表格 + 移动卡片共用） */
.magicflow-asset-act {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.magicflow-asset-act--mobile {
  margin-top: 8px;
}
.magicflow-asset-blocks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
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

.magicflow-asset-stale-switch {
  flex: 0 0 auto;
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
  flex-wrap: nowrap;   /* ★ P10：不许换行，否则「可删」chip 会掉到下一行 */
}

.magicflow-mobile-asset__check {
  flex: 0 0 auto;
  margin-inline-end: 2px;
}

.magicflow-mobile-asset__title {
  display: flex;
  flex: 1 1 auto;      /* ★ P10：吃掉中间剩余宽度 */
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

.magicflow-mobile-asset__sites {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.75rem;
  white-space: nowrap;      /* ★ P10：站名列表只占一行，超出省略 */
  overflow: hidden;
  text-overflow: ellipsis;
}

.magicflow-asset-hint {
  margin-top: 2px;
  font-size: 0.72rem;
  line-height: 1.35;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-mobile-asset__state {
  /* ★ 15.9.0：标题过长时「可删 / 被保护」被压到截断 → chip 不再收缩（取 min(内容宽, 50%)） */
  flex: 0 0 auto;
  max-inline-size: 50%;
  min-inline-size: 0;
}
.magicflow-mobile-asset__state :deep(.v-chip__content) {
  white-space: nowrap;      /* ★ P11：可删/被保护 这类短标签绝不竖着折断 */
  overflow: hidden;
  text-overflow: ellipsis;  /* 太长（如 H&R 原因）→ 单行省略，title 里看全文 */
}

.magicflow-mobile-asset__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));   /* ★ P10：3 项 3 列，不落单 */
  gap: 6px 10px;
}

.magicflow-mobile-asset__grid span {
  display: flex;
  flex-direction: column;   /* ★ P10：标签在上、数值在下，窄屏对齐更稳 */
  gap: 1px;
  min-inline-size: 0;
  font-size: 0.82rem;
}

.magicflow-mobile-asset__grid em {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.7rem;        /* ★ P10：小标签 */
  font-style: normal;
}

.magicflow-mobile-asset__grid b {
  min-inline-size: 0;
  font-weight: 600;
  text-align: start;        /* ★ P10：左对齐（竖排后不该再靠右）*/
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

  .magicflow-asset-stale-switch {
    margin-inline-end: auto;   /* ★ P10：开关留左，刷新/删除靠右 */
  }

  .magicflow-asset-filters {
    justify-content: flex-end; /* ★ P12：换行的动作按钮也靠右，别孤零零吊在左边 */
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
/* ★ 15.8.21：季 / 集 标签 */
.magicflow-asset-ep {
  flex: 0 0 auto;
  font-size: 0.72rem;
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
  white-space: nowrap;
}
</style>
