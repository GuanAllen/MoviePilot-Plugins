<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import TaskEditorDialog from './TaskEditorDialog.vue'
import {
  cloneTask,
  formatBonus,
  formatBytes,
  formatDateTime,
  formatDuration,
  formatDurationSeconds,
  normalizeSettings,
  normalizeTask,
  runStatusText,
  taskStateMeta,
  unwrapResponse,
} from '../utils'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MagicFlow' },
  initialTab: { type: String, default: 'overview' },
  showClose: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'action'])
const hostToast = inject('moviepilot:toast', null)

const loading = ref(false)
const taskLoading = ref(false)
const saving = ref(false)
const error = ref('')
const statusLoaded = ref(false)
const status = ref({
  enabled: false,
  show_sidebar_nav: true,
  summary: {},
  tasks: [],
  options: { sites: [], downloaders: [] },
})
const detail = ref(null)
const bonusData = ref({ torrents: [], total_bonus: 0, torrent_count: 0, protected_count: 0 })
const candidateData = ref({ candidates: [], total: 0, reason_counts: {} })
const candidateLoadedAt = ref(0)
const operationData = ref({ operations: [], total: 0 })
const selectedTaskId = ref('')
const activeTab = ref(props.initialTab || 'overview')
const torrentFilter = ref('all')
const torrentStatusFilter = ref('all')
const poolView = ref('candidates')
const torrentDialog = ref(false)
const activeTorrent = ref(null)
const candidateLoadedFor = ref('')
const editorOpen = ref(false)
const editorTask = ref({})
const deleteDialog = ref(false)
const settingsMenu = ref(false)
const settingsDraft = ref({ enabled: false, show_sidebar_nav: true })
let refreshTimer
let phaseTimer

// 任务图标使用站点自身图标（走 MoviePilot /site/icon/{id}，服务端带 cookie 抓取，私有站也能取到）
const siteIcons = ref({})
const siteIconPending = new Set()

async function loadSiteIcon(siteId) {
  const id = Number(siteId)
  if (!id || siteIcons.value[id] !== undefined || siteIconPending.has(id)) return
  siteIconPending.add(id)
  try {
    const data = unwrapResponse(await props.api.get(`site/icon/${id}`))
    siteIcons.value = { ...siteIcons.value, [id]: (data && data.icon) || '' }
  } catch (err) {
    siteIcons.value = { ...siteIcons.value, [id]: '' }
  } finally {
    siteIconPending.delete(id)
  }
}

const pluginBase = computed(() => `plugin/${props.pluginId || 'MagicFlow'}`)
const tasks = computed(() => status.value.tasks || [])
const selectedTask = computed(() => tasks.value.find(item => item.id === selectedTaskId.value) || null)
const summary = computed(() => status.value.summary || {})
const selectedState = computed(() =>
  taskStateMeta(selectedTask.value?.state, selectedTask.value?.enabled ?? status.value.enabled),
)
const taskConfig = computed(() => selectedTask.value || {})
const taskSiteIcon = computed(() => {
  const id = Number(selectedTask.value?.site_id)
  return id ? siteIcons.value[id] || '' : ''
})
const detailStats = computed(() => detail.value || taskConfig.value)
const sortedTorrents = computed(() => {
  let items = bonusData.value.torrents || []
  if (torrentFilter.value === 'protected') items = items.filter(item => item.is_protected)
  if (torrentStatusFilter.value !== 'all') items = items.filter(item => torrentStatusGroup(item) === torrentStatusFilter.value)
  return items
})

const reasonEntries = computed(() => {
  const counts = candidateData.value.reason_counts || {}
  return Object.entries(counts)
    .map(([label, count]) => ({ label, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
})
const maxReasonCount = computed(() => Math.max(1, ...reasonEntries.value.map(item => item.count)))
// 本轮抓取到的候选总数 = 通过数 + 各拦截原因数量
const candidateRawTotal = computed(() => {
  const rejected = Object.values(candidateData.value.reason_counts || {}).reduce((sum, value) => sum + (Number(value) || 0), 0)
  return (candidateData.value.candidates || []).length + rejected
})

// 运行诊断流程链（v5 阶段）
const FLOW_STEPS = [
  { key: 'entry', label: '入口检查' },
  { key: 'fetch', label: '抓取候选' },
  { key: 'wash', label: '洗池过滤' },
  { key: 'classify', label: '分类排序' },
  { key: 'process', label: '处理入库' },
]

// 工作台标签（预览图：分段式标签卡）
const MF_TABS = [
  { value: 'overview', label: '任务概览' },
  { value: 'diagnostics', label: '运行诊断' },
  { value: 'pool', label: '种子池' },
  { value: 'config', label: '任务配置' },
]
const flowNodes = computed(() => {
  const phase = detail.value?.last_phase || ''
  const active = !!detail.value?.run_active
  const idx = FLOW_STEPS.findIndex(step => step.key === phase)
  return FLOW_STEPS.map((step, i) => {
    let state = 'idle'
    if (active) {
      if (idx >= 0 && i < idx) state = 'done'
      else if (i === idx) state = 'running'
    } else if (phase === 'done') {
      state = 'done'
    } else if (phase === 'error' && idx >= 0) {
      state = i < idx ? 'done' : i === idx ? 'error' : 'idle'
    }
    return { ...step, state }
  })
})

// 运行流程右上角阶段标签（预览图：阶段名 pill + 呼吸圆点，运行中闪烁）
const flowPhaseText = computed(() => {
  if (detail.value?.run_active) {
    const running = flowNodes.value.find(item => item.state === 'running')
    if (running) return running.label
  }
  const step = FLOW_STEPS.find(item => item.key === (detail.value?.last_phase || ''))
  return step ? step.label : runStatusText(detail.value?.last_run_status)
})

const torrentHeaders = [
  { title: '种子', key: 'title', sortable: false },
  { title: '状态', key: 'status', sortable: false, width: 120 },
  { title: '大小', key: 'size_gb', sortable: false, width: 96 },
  { title: '上传量', key: 'uploaded', sortable: false, width: 96 },
  { title: '分享率', key: 'ratio', sortable: false, width: 84 },
  { title: '操作', key: 'actions', sortable: false, width: 120 },
]

function notify(message, color = 'success') {
  const method = ['error', 'info', 'warning', 'success'].includes(color) ? color : 'success'
  if (typeof hostToast?.[method] === 'function') {
    hostToast[method](message)
  } else if (method === 'error') {
    error.value = message
  }
}

const KIND_TEXT = { run: '执行', selection: '选种加入', deletion: '删种清理', protection: '手动保留', unprotection: '取消保留', reuse: '存量复用' }
const STATE_TEXT = { submitting: '提交中', accepted: '已受理', completed: '已完成', failed: '失败' }
const KIND_ICON = {
  run: 'mdi-play-circle-outline',
  selection: 'mdi-download-outline',
  deletion: 'mdi-delete-outline',
  reuse: 'mdi-content-duplicate',
  protection: 'mdi-shield-check-outline',
  unprotection: 'mdi-shield-off-outline',
}

function operationKindText(kind) {
  return KIND_TEXT[kind] || kind
}

function operationStateText(state) {
  return STATE_TEXT[state] || state
}

function operationIcon(kind) {
  return KIND_ICON[kind] || 'mdi-circle-small'
}

function operationColor(record) {
  if (record.state === 'failed') return 'error'
  if (record.kind === 'deletion') return 'warning'
  if (record.kind === 'run') return 'secondary'
  return 'primary'
}

/** 操作记录的耗时文本（优先用后端记录，回退到创建/完成时间差）。 */
function operationDuration(record) {
  if (record.duration != null && Number(record.duration) > 0) return formatDurationSeconds(record.duration)
  return formatDuration(record.created_at, record.resolved_at)
}

/** 操作记录的一行摘要（run 记录取结果文本）。 */
function operationSummary(record) {
  const first = (record.items || [])[0]
  if (first && first.title) return first.title
  const count = (record.items || []).length
  return count ? `${count} 个条目` : ''
}

const TORRENT_STATE_TEXT = {
  uploading: '做种中', stalledup: '做种中·无流量', forcedup: '做种中', queuedup: '排队做种',
  downloading: '下载中', forceddl: '下载中', queueddl: '排队下载', metadl: '获取元数据', checkingdl: '校验中',
  stalleddl: '下载停滞', pausedup: '已暂停', pauseddl: '已暂停', stoppedup: '已停止', stoppeddl: '已停止',
  error: '出错', missingfiles: '文件缺失', unknown: '未知',
}

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

// 托管种子状态文本：做种 / 下载 X% / 停滞（参考 BrushFlow）
function torrentStateText(item) {
  const pct = torrentProgressPct(item)
  if (pct >= 100) return '做种中'
  if (pct <= 0) return stateLabel(item?.state) || '等待中'
  return `下载 ${pct}%`
}

// 下载进度百分比（0~100），供进度条使用
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}

// 托管种子状态分组（用于状态筛选）
function torrentStatusGroup(item) {
  const key = String(item?.state || '').toLowerCase()
  if (['uploading', 'forcedup', 'stalledup', 'queuedup'].includes(key)) return 'seeding'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'checkingdl'].includes(key)) return 'downloading'
  if (key === 'stalleddl') return 'stalled'
  if (['pausedup', 'pauseddl', 'stoppedup', 'stoppeddl'].includes(key)) return 'paused'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'other'
}

// 状态筛选选项（带数量）
const torrentStatusOptions = computed(() => {
  const items = bonusData.value.torrents || []
  const count = group => items.filter(item => torrentStatusGroup(item) === group).length
  return [
    { title: `全部状态（${items.length}）`, value: 'all' },
    { title: `做种中（${count('seeding')}）`, value: 'seeding' },
    { title: `下载中（${count('downloading')}）`, value: 'downloading' },
    { title: `下载停滞（${count('stalled')}）`, value: 'stalled' },
    { title: `已暂停 / 停止（${count('paused')}）`, value: 'paused' },
    { title: `出错（${count('error')}）`, value: 'error' },
  ]
})

// 加载插件总览与任务列表。
async function loadStatus() {
  loading.value = true
  try {
    status.value = unwrapResponse(await props.api.get(`${pluginBase.value}/status`)) || status.value
    settingsDraft.value = normalizeSettings({
      enabled: status.value.enabled,
      show_sidebar_nav: status.value.show_sidebar_nav,
    })
    statusLoaded.value = true
    if (!selectedTaskId.value && tasks.value.length) {
      selectTask(tasks.value[0].id)
    } else if (selectedTaskId.value && !tasks.value.some(item => item.id === selectedTaskId.value)) {
      selectedTaskId.value = ''
    }
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    loading.value = false
  }
}

// 加载任务详情统计。
async function loadDetail(taskId) {
  try {
    detail.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}`))
  } catch (err) {
    error.value = err?.message || String(err)
  }
}

// 加载托管种子与魔力汇总。
async function loadBonus(taskId) {
  taskLoading.value = true
  try {
    bonusData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}/bonus`)) || bonusData.value
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    taskLoading.value = false
  }
}

// 加载候选种子（触发站点抓取，切换标签时按需加载）。
async function loadCandidates(taskId) {
  taskLoading.value = true
  try {
    candidateData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}/candidates`)) || {
      candidates: [],
      total: 0,
      reason_counts: {},
    }
    candidateLoadedFor.value = taskId
    candidateLoadedAt.value = Date.now()
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    taskLoading.value = false
  }
}

// 加载操作记录。
async function loadOperations(taskId) {
  try {
    operationData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}/operations`)) || {
      operations: [],
      total: 0,
    }
  } catch (err) {
    error.value = err?.message || String(err)
  }
}

// 选择任务并刷新其详情数据。
function selectTask(taskId) {
  if (!taskId) {
    selectedTaskId.value = ''
    return
  }
  if (taskId === selectedTaskId.value) return
  selectedTaskId.value = taskId
  reloadSelected()
  if (activeTab.value === 'pool') loadCandidates(taskId)
}

// 重新拉取当前任务的全部明细数据。
function reloadSelected(taskId = selectedTaskId.value) {
  if (!taskId) return
  selectedTaskId.value = taskId
  detail.value = null
  bonusData.value = { torrents: [], total_bonus: 0, torrent_count: 0, protected_count: 0 }
  candidateData.value = { candidates: [], total: 0, reason_counts: {} }
  candidateLoadedFor.value = ''
  candidateLoadedAt.value = 0
  operationData.value = { operations: [], total: 0 }
  loadDetail(taskId)
  loadBonus(taskId)
  loadOperations(taskId)
}

// 立即为当前任务执行一次。
async function runOperation() {
  if (!selectedTask.value) return
  const taskId = selectedTask.value.id
  saving.value = true
  try {
    unwrapResponse(await props.api.post(`${pluginBase.value}/tasks/${taskId}/run`, {}))
    notify('已提交执行请求，稍候刷新结果')
    emit('action')
    window.setTimeout(() => loadStatus(), 1500)
    window.setTimeout(() => {
      if (selectedTaskId.value !== taskId) return
      reloadSelected(taskId)
      // 执行后同步刷新候选（包含「过滤原因」），保证流水随本轮变化
      if (activeTab.value === 'pool') loadCandidates(taskId)
    }, 6000)
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 切换当前任务启停状态。
async function toggleSelectedTask() {
  if (!selectedTask.value) return
  saving.value = true
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/state`, {
        enabled: !selectedTask.value.enabled,
      }),
    )
    notify(selectedTask.value.enabled ? '任务已暂停' : '任务已启用')
    await loadStatus()
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 打开新建任务弹窗。
function openCreateTask() {
  editorTask.value = cloneTask()
  editorOpen.value = true
}

// 打开编辑任务弹窗。
function openEditTask() {
  if (!selectedTask.value) return
  editorTask.value = cloneTask(selectedTask.value)
  editorOpen.value = true
}

// 保存任务（新增或更新）。
async function saveTask(payload) {
  saving.value = true
  try {
    const normalized = normalizeTask(payload)
    if (normalized.id) {
      unwrapResponse(await props.api.put(`${pluginBase.value}/tasks/${normalized.id}`, normalized))
    } else {
      delete normalized.id
      unwrapResponse(await props.api.post(`${pluginBase.value}/tasks`, normalized))
    }
    editorOpen.value = false
    notify('任务已保存')
    await loadStatus()
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 确认删除当前任务。
async function confirmDeleteTask() {
  if (!selectedTask.value) return
  saving.value = true
  try {
    unwrapResponse(await props.api.delete(`${pluginBase.value}/tasks/${selectedTask.value.id}`))
    deleteDialog.value = false
    selectedTaskId.value = ''
    notify('任务已删除')
    await loadStatus()
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 对托管种子执行保留 / 取消保留 / 删除。
async function torrentAction(torrent, action) {
  saving.value = true
  try {
    const verb = action === 'delete' ? 'delete' : action
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/torrents/${torrent.hash}/${verb}`, {}),
    )
    notify(action === 'protect' ? '已保留种子' : action === 'unprotect' ? '已取消保留' : '已删除种子')
    await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)])
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 打开发种详情弹窗
function openTorrentDetail(item) {
  if (!item) return
  activeTorrent.value = item
  torrentDialog.value = true
}

// 行点击：点到了操作按钮则不弹详情
function onTorrentRowClick(event, { item }) {
  const target = event?.target
  if (target && typeof target.closest === 'function' && target.closest('.v-btn, button, a')) return
  openTorrentDetail(item)
}

// 在详情弹窗里操作，并在刷新后同步最新数据
async function detailTorrentAction(action) {
  const current = activeTorrent.value
  if (!current) return
  await torrentAction(current, action)
  if (action === 'delete') {
    torrentDialog.value = false
    return
  }
  const key = (current.hash || '').toLowerCase()
  const found = (bonusData.value.torrents || []).find(t => (t.hash || '').toLowerCase() === key)
  if (found) activeTorrent.value = found
}

// 保存全局设置。
async function saveSettings() {
  saving.value = true
  try {
    unwrapResponse(await props.api.post(`${pluginBase.value}/settings`, normalizeSettings(settingsDraft.value)))
    settingsMenu.value = false
    notify('设置已保存')
    await loadStatus()
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

watch(activeTab, tab => {
  // 进入「种子池」重新拉候选 / 托管，保证最新
  if (tab === 'pool' && selectedTaskId.value) {
    if (poolView.value === 'candidates') loadCandidates(selectedTaskId.value)
    else loadBonus(selectedTaskId.value)
  }
  if (tab === 'diagnostics' && selectedTaskId.value) {
    loadOperations(selectedTaskId.value)
    loadDetail(selectedTaskId.value)
  }
})

watch(poolView, view => {
  if (!selectedTaskId.value) return
  if (view === 'candidates') loadCandidates(selectedTaskId.value)
  else loadBonus(selectedTaskId.value)
})

watch(
  () => props.initialTab,
  tab => {
    if (tab) activeTab.value = tab
  },
)

// 任务切换时按 site_id 拉取站点图标（内存缓存，避免重复请求）
watch(
  () => selectedTask.value?.site_id,
  siteId => {
    if (siteId) loadSiteIcon(siteId)
  },
  { immediate: true },
)

onMounted(() => {
  loadStatus()
  refreshTimer = window.setInterval(loadStatus, 30000)
  // 运行诊断页每秒多刷新一次任务阶段，驱动流程链转圈
  phaseTimer = window.setInterval(() => {
    if (activeTab.value === 'diagnostics' && selectedTaskId.value) loadDetail(selectedTaskId.value)
  }, 1500)
})

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (phaseTimer) window.clearInterval(phaseTimer)
})
</script>

<template>
  <div class="magicflow-page" :class="{ 'magicflow-page--compact': compact }">
    <header class="magicflow-page__header">
      <div class="magicflow-page__identity">
        <span class="magicflow-logo"><VIcon icon="mdi-star-four-points-outline" size="20" /></span>
        <div>
          <h1>
            魔力管家
            <span v-if="status.version" class="magicflow-page__version">v{{ status.version }}</span>
          </h1>
          <p>PT 做种 · 魔力养护后台</p>
        </div>
      </div>
      <div class="magicflow-page__actions">
        <VChip v-if="summary.total_tasks" size="small" variant="tonal">
          {{ summary.enabled_tasks || 0 }} / {{ summary.total_tasks }} 启用
        </VChip>
        <VBtn class="magicflow-header-create" color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreateTask">
          新建任务
        </VBtn>
        <VMenu v-model="settingsMenu" :close-on-content-click="false" location="bottom end">
          <template #activator="{ props: menuProps }">
            <VBtn v-bind="menuProps" icon="mdi-tune-variant" variant="text" aria-label="全局设置" />
          </template>
          <VCard class="magicflow-settings-menu" title="全局设置">
            <VCardText class="settings-menu__body">
              <VSwitch v-model="settingsDraft.enabled" label="启用插件" color="primary" hide-details inset />
              <VSwitch
                v-model="settingsDraft.show_sidebar_nav"
                label="显示侧栏入口"
                color="primary"
                hide-details
                inset
              />
            </VCardText>
            <VCardActions>
              <VSpacer />
              <VBtn color="primary" variant="flat" :loading="saving" @click="saveSettings">保存</VBtn>
            </VCardActions>
          </VCard>
        </VMenu>
        <VBtn v-if="showClose" icon="mdi-close" variant="text" aria-label="关闭" @click="emit('close')" />
      </div>
    </header>

    <VAlert v-if="error" type="error" variant="tonal" closable @click:close="error = ''">{{ error }}</VAlert>
    <VAlert v-if="statusLoaded && !status.enabled" type="warning" variant="tonal">
      插件当前未启用，任务配置与历史仍可查看，启用后才会注册选种刷新和做种检查服务。
    </VAlert>

    <div v-if="loading && !tasks.length" class="magicflow-loading">
      <VSkeletonLoader type="list-item-three-line, list-item-three-line, article" />
    </div>

    <div v-else-if="!tasks.length" class="magicflow-empty">
      <VIcon icon="mdi-star-four-points-outline" size="52" color="medium-emphasis" />
      <div class="text-h6">还没有魔力任务</div>
      <div class="text-body-2 text-medium-emphasis">创建任务后可按站点魔力公式独立养护做种</div>
      <VBtn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreateTask">创建第一个任务</VBtn>
    </div>

    <template v-else>
      <div class="magicflow-mobile-toolbar">
        <VSelect
          v-if="tasks.length > 1"
          class="magicflow-mobile-select"
          :model-value="selectedTaskId"
          :items="tasks"
          item-title="name"
          item-value="id"
          label="当前任务"
          hide-details
          @update:model-value="selectTask"
        >
          <template #item="{ props: itemProps, item }">
            <VListItem v-bind="itemProps" :subtitle="item.raw.site_name">
              <template #prepend>
                <VIcon :icon="taskStateMeta(item.raw.state, item.raw.enabled).icon" :color="taskStateMeta(item.raw.state, item.raw.enabled).color" />
              </template>
            </VListItem>
          </template>
        </VSelect>
        <div v-else class="magicflow-mobile-current">
          <span>当前任务</span>
          <strong>{{ selectedTask?.name || '—' }}</strong>
        </div>
        <VBtn class="magicflow-mobile-add" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="openCreateTask">
          新建
        </VBtn>
      </div>

      <div class="magicflow-layout">
        <VSheet tag="aside" class="magicflow-task-rail app-surface-static">
          <div class="magicflow-task-rail__head">
            <span class="text-subtitle-2">魔力任务</span>
            <VChip size="x-small" variant="tonal">{{ tasks.length }}</VChip>
          </div>
          <div class="magicflow-task-list">
            <button
              v-for="task in tasks"
              :key="task.id"
              type="button"
              class="magicflow-task-item"
              :class="{ 'magicflow-task-item--selected': task.id === selectedTaskId }"
              :aria-pressed="task.id === selectedTaskId"
              @click="selectTask(task.id)"
            >
              <span class="magicflow-task-item__title">
                <strong>{{ task.name }}</strong>
                <span class="magicflow-status-dot" :class="`magicflow-status-dot--${taskStateMeta(task.state, task.enabled).color}`" />
              </span>
              <span>{{ task.site_name }} · {{ task.downloader }}</span>
              <span class="magicflow-task-item__meta">
                <span>{{ task.seeding_count || 0 }} 个种子</span>
                <span>{{ task.site_bonus_ok ? formatBonus(task.site_bonus_per_hour) : '—' }}</span>
              </span>
            </button>
          </div>
          <VBtn class="magicflow-create-task" block variant="tonal" prepend-icon="mdi-plus" @click="openCreateTask">
            新建任务
          </VBtn>
        </VSheet>

        <main v-if="selectedTask" class="magicflow-workspace">
          <section class="magicflow-task-head">
            <div class="magicflow-task-head__identity">
              <VAvatar color="primary" variant="tonal" rounded size="42" class="magicflow-task-head__avatar">
                <img v-if="taskSiteIcon" class="magicflow-task-head__site-icon" :src="taskSiteIcon" alt="" />
                <VIcon v-else icon="mdi-web" />
              </VAvatar>
              <div class="magicflow-task-head__body">
                <div class="magicflow-task-head__title">
                  <h2>{{ selectedTask.name }}</h2>
                  <VChip :color="selectedState.color" size="small" variant="tonal" :prepend-icon="selectedState.icon">
                    {{ selectedState.text }}
                  </VChip>
                </div>
                <p>{{ selectedTask.site_name }} · 标签「{{ selectedTask.brush_tag || '未设置' }}」</p>
              </div>
            </div>
            <div class="magicflow-task-head__actions">
              <VTooltip text="立即执行">
                <template #activator="{ props: tipProps }">
                  <VBtn v-bind="tipProps" icon="mdi-sync" variant="text" :loading="saving" @click="runOperation" />
                </template>
              </VTooltip>
              <VTooltip text="刷新数据">
                <template #activator="{ props: tipProps }">
                  <VBtn v-bind="tipProps" icon="mdi-refresh" variant="text" @click="reloadSelected()" />
                </template>
              </VTooltip>
              <VTooltip :text="selectedTask.enabled ? '暂停任务' : '启用任务'">
                <template #activator="{ props: tipProps }">
                  <VBtn
                    v-bind="tipProps"
                    :icon="selectedTask.enabled ? 'mdi-pause' : 'mdi-play'"
                    variant="text"
                    @click="toggleSelectedTask"
                  />
                </template>
              </VTooltip>
              <VTooltip text="编辑任务">
                <template #activator="{ props: tipProps }">
                  <VBtn v-bind="tipProps" icon="mdi-pencil-outline" variant="text" @click="openEditTask" />
                </template>
              </VTooltip>
              <VTooltip text="删除任务">
                <template #activator="{ props: tipProps }">
                  <VBtn v-bind="tipProps" icon="mdi-delete-outline" variant="text" color="error" @click="deleteDialog = true" />
                </template>
              </VTooltip>
            </div>
          </section>

          <div class="magicflow-tabs" role="tablist">
            <button
              v-for="tab in MF_TABS"
              :key="tab.value"
              type="button"
              role="tab"
              class="magicflow-tab"
              :class="{ 'is-active': activeTab === tab.value }"
              :aria-selected="activeTab === tab.value"
              @click="activeTab = tab.value"
            >
              {{ tab.label }}
            </button>
          </div>

          <VWindow v-model="activeTab" :touch="false" class="magicflow-window">
            <VWindowItem value="overview">
              <div class="magicflow-stat-grid">
                <VSheet class="magicflow-stat magicflow-stat--accent app-surface-static">
                  <strong>{{ selectedTask.seeding_count || 0 }}</strong>
                  <span>托管种子 · {{ selectedTask.active_seeding_count || 0 }} 做种中 / {{ selectedTask.downloading_count || 0 }} 下载中 / {{ selectedTask.paused_count || 0 }} 已暂停</span>
                </VSheet>
                <VSheet class="magicflow-stat app-surface-static">
                  <strong>{{ selectedTask.site_bonus_ok ? formatBonus(selectedTask.site_bonus_per_hour) : '—' }}</strong>
                  <span>站点上报时魔 · 站点实时值</span>
                </VSheet>
                <VSheet class="magicflow-stat app-surface-static">
                  <strong>{{ Number(selectedTask.site_current_bonus || 0).toFixed(2) }}</strong>
                  <span>站点当前魔力 · 该站点实时存量</span>
                </VSheet>
                <VSheet class="magicflow-stat app-surface-static">
                  <strong>{{ detailStats.last_added || 0 }} / {{ detailStats.last_reused || 0 }} / {{ detailStats.last_deleted || 0 }}</strong>
                  <span>上次运行 新增/复用/删除 · 当前托管 {{ detailStats.last_kept || selectedTask.seeding_count || 0 }}</span>
                </VSheet>
              </div>

              <div class="magicflow-overview-grid">
                <VSheet tag="section" class="magicflow-panel app-surface-static">
                  <header class="magicflow-panel__head">
                    <div>
                      <div class="text-subtitle-1 font-weight-medium">运行状态</div>
                      <div class="text-body-2 text-medium-emphasis">当前任务调度与魔力策略</div>
                    </div>
                    <VChip :color="selectedState.color" size="small" variant="tonal">{{ selectedState.text }}</VChip>
                  </header>
                  <dl class="magicflow-facts">
                    <div><dt>选种周期</dt><dd>{{ taskConfig.cron_expression || `每 ${taskConfig.brush_interval} 分钟` }}</dd></div>
                    <div><dt>检查周期</dt><dd>每 {{ taskConfig.check_interval }} 分钟</dd></div>
                    <div><dt>开启时段</dt><dd>{{ taskConfig.active_time_range || '全天' }}</dd></div>
                    <div><dt>最低魔力</dt><dd>{{ taskConfig.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.min_bonus_per_hour).toFixed(2)} /h` }}</dd></div>
                    <div><dt>最多保留</dt><dd>{{ taskConfig.max_keep_torrents == null ? (taskConfig.disk_size_gb ? `按 ${taskConfig.disk_size_gb}GB 自动` : '不限') : `${taskConfig.max_keep_torrents} 个` }}</dd></div>
                    <div><dt>保护阈值</dt><dd>{{ taskConfig.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.bonus_protect_threshold).toFixed(0) }}</dd></div>
                    <div><dt>自动补种</dt><dd>{{ taskConfig.refill_when_empty ? '开启' : '关闭' }}</dd></div>
                    <div><dt>存量复用</dt><dd>{{ taskConfig.reuse_existing ? '开启' : '关闭' }}</dd></div>
                    <div><dt>无进度清理</dt><dd>{{ taskConfig.cleanup_no_progress ? `开启（${taskConfig.no_progress_minutes ?? 30} 分钟）` : '关闭' }}</dd></div>
                    <div><dt>慢速清理</dt><dd>{{ taskConfig.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.slow_progress_max_hours ?? 48}h 下不完即清）` }}</dd></div>
                    <div><dt>自动恢复暂停</dt><dd>{{ taskConfig.auto_resume_paused === false ? '关闭' : '开启' }}</dd></div>
                    <div><dt>选种来源</dt><dd>{{ taskConfig.rss_support ? 'RSS' : '站点列表页' }}</dd></div>
                    <div><dt>促销要求</dt><dd>{{ taskConfig.freeleech === '2xfree' ? '2X 免费' : taskConfig.freeleech === 'free' ? '免费' : '全部' }}</dd></div>
                  </dl>
                </VSheet>

                <VSheet tag="section" class="magicflow-panel app-surface-static">
                  <header class="magicflow-panel__head">
                    <div>
                      <div class="text-subtitle-1 font-weight-medium">最近一次运行</div>
                      <div class="text-body-2 text-medium-emphasis">
                        {{ detailStats.last_run_at ? formatDateTime(detailStats.last_run_at) : '暂无运行记录' }}
                      </div>
                    </div>
                    <VChip v-if="detailStats.last_error" color="error" size="small" variant="tonal">失败</VChip>
                    <VChip v-else-if="detailStats.last_run_status" :color="detailStats.last_run_status === 'done' ? 'success' : detailStats.last_run_status === 'failed' ? 'error' : 'secondary'" size="small" variant="tonal">
                      {{ runStatusText(detailStats.last_run_status) }}
                    </VChip>
                    <VChip v-else-if="detailStats.last_success_at" color="success" size="small" variant="tonal">完成</VChip>
                  </header>
                  <div class="magicflow-run-summary">
                    <div><span>上次成功</span><strong>{{ detailStats.last_success_at ? formatDateTime(detailStats.last_success_at) : '-' }}</strong></div>
                    <div><span>本次状态</span><strong>{{ runStatusText(detailStats.last_run_status) }}</strong></div>
                    <div><span>本次耗时</span><strong>{{ formatDurationSeconds(detailStats.last_run_duration) }}</strong></div>
                    <div><span>本次新增 / 复用</span><strong>{{ detailStats.last_added || 0 }} / {{ detailStats.last_reused || 0 }}</strong></div>
                    <div><span>本次删除</span><strong>{{ detailStats.last_deleted || 0 }}</strong></div>
                    <div><span>当前托管 / 受保护</span><strong>{{ detailStats.last_kept || 0 }} / {{ detailStats.protected_count || 0 }}</strong></div>
                  </div>
                  <VAlert v-if="detailStats.last_run_reason" type="info" variant="tonal" density="compact" class="mb-2">
                    本轮说明：{{ detailStats.last_run_reason }}
                  </VAlert>
                  <VAlert v-if="detailStats.last_error" type="error" variant="tonal" density="compact">
                    {{ detailStats.last_error }}
                  </VAlert>
                  <VBtn variant="text" color="primary" append-icon="mdi-arrow-right" @click="activeTab = 'diagnostics'">
                    查看运行诊断
                  </VBtn>
                </VSheet>
              </div>

            </VWindowItem>

            <VWindowItem value="diagnostics">
              <VSheet tag="section" class="magicflow-panel magicflow-flow app-surface-static">
                <header class="magicflow-panel__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">运行流程</div>
                    <div class="text-body-2 text-medium-emphasis">
                      {{ detailStats.run_active ? '正在执行本轮刷流…' : (detailStats.last_run_at ? `最近执行 ${formatDateTime(detailStats.last_run_at)}` : '尚未运行') }}
                      · 翻页游标 {{ detailStats.page_cursor ?? 0 }}
                    </div>
                  </div>
                  <span class="magicflow-flow__tag" :class="{ 'is-live': detailStats.run_active, 'is-error': detailStats.last_run_status === 'failed' }">
                    <i />
                    {{ flowPhaseText }}
                  </span>
                </header>
                <ol class="magicflow-flow__chain">
                  <li
                    v-for="(node, i) in flowNodes"
                    :key="node.key"
                    class="magicflow-flow__node"
                    :class="`is-${node.state}`"
                  >
                    <span class="magicflow-flow__dot">
                      <VIcon v-if="node.state === 'done' || node.state === 'running'" icon="mdi-check" size="16" />
                      <VIcon v-else-if="node.state === 'error'" icon="mdi-alert" size="16" />
                    </span>
                    <span class="magicflow-flow__label">{{ node.label }}</span>
                    <span v-if="i < flowNodes.length - 1" class="magicflow-flow__line" :class="{ 'is-done': node.state === 'done' }" />
                  </li>
                </ol>
                <VAlert v-if="detailStats.last_error" type="error" variant="tonal" density="compact" class="mt-3">
                  {{ detailStats.last_error }}
                </VAlert>
              </VSheet>

              <VSheet tag="section" class="magicflow-panel app-surface-static mt-4">
                <header class="magicflow-panel__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">过滤原因</div>
                    <div class="text-body-2 text-medium-emphasis">
                      被规则拦截的候选分布 · 共抓取 {{ candidateRawTotal }} 个，通过 {{ (candidateData.candidates || []).length }}
                      <template v-if="candidateLoadedAt"> · 统计于 {{ formatDateTime(candidateLoadedAt) }}</template>
                    </div>
                  </div>
                </header>
                <div v-if="reasonEntries.length" class="magicflow-reasons">
                  <div v-for="item in reasonEntries" :key="item.label" class="magicflow-reason">
                    <div><span>{{ item.label }}</span><strong>{{ item.count }}</strong></div>
                    <span class="magicflow-reason__track"><i :style="{ width: `${(item.count / maxReasonCount) * 100}%` }" /></span>
                  </div>
                </div>
                <div v-else class="magicflow-table-empty">本轮没有记录过滤原因（候选全部通过或列表为空）</div>
                <VAlert v-if="detailStats.last_run_status === 'noop' && detailStats.last_run_reason" type="info" variant="tonal" density="compact" class="mt-3">
                  最近一次执行未进入候选过滤：{{ detailStats.last_run_reason }}
                </VAlert>
              </VSheet>

              <VSheet tag="section" class="magicflow-panel app-surface-static mt-4">
                <header class="magicflow-panel__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">操作记录</div>
                    <div class="text-body-2 text-medium-emphasis">每次执行 / 选种 / 删种 / 保护的流水（含耗时）</div>
                  </div>
                  <VBtn variant="text" color="primary" prepend-icon="mdi-refresh" @click="loadOperations(selectedTaskId)">刷新</VBtn>
                </header>
                <div class="magicflow-events">
                  <article v-for="record in operationData.operations || []" :key="record.operation_id">
                    <VIcon :icon="operationIcon(record.kind)" :color="operationColor(record)" />
                    <div>
                      <strong>
                        {{ operationKindText(record.kind) }}
                        <VChip size="x-small" variant="tonal" :color="operationColor(record)" class="ml-2">{{ operationStateText(record.state) }}</VChip>
                      </strong>
                      <span>{{ operationSummary(record) }}</span>
                      <span>
                        {{ formatDateTime(record.created_at) }} ·
                        耗时 {{ operationDuration(record) }}
                        <template v-if="record.duration == null && (record.items || []).length > 1"> · {{ (record.items || []).length }} 个条目</template>
                      </span>
                      <span v-if="record.error_message" class="text-error">{{ record.error_message }}</span>
                    </div>
                  </article>
                  <div v-if="!(operationData.operations || []).length" class="magicflow-table-empty">暂无操作记录</div>
                </div>
              </VSheet>
            </VWindowItem>

            <VWindowItem value="pool">
              <div class="magicflow-diagnostic-head">
                <div>
                  <div class="text-subtitle-1 font-weight-medium">种子池</div>
                  <div class="text-body-2 text-medium-emphasis">
                    <template v-if="poolView === 'candidates'">
                      待办队列 · 共 {{ candidateData.total || 0 }} 个通过过滤
                    </template>
                    <template v-else>
                      已托管：共 {{ bonusData.torrent_count || 0 }} 个（黑盒：仅展示状态与进度）
                    </template>
                  </div>
                </div>
                <div class="magicflow-torrent-filters">
                  <VBtnToggle :model-value="poolView" mandatory color="primary" density="compact" @update:model-value="value => (poolView = value)">
                    <VBtn value="candidates" prepend-icon="mdi-filter-variant">候选</VBtn>
                    <VBtn value="torrents" prepend-icon="mdi-seed-outline">托管（{{ bonusData.torrent_count || 0 }}）</VBtn>
                  </VBtnToggle>
                </div>
              </div>

              <template v-if="poolView === 'candidates'">
                <VSheet tag="section" class="magicflow-panel app-surface-static">
                  <header class="magicflow-panel__head">
                    <div>
                      <div class="text-subtitle-1 font-weight-medium">候选排行</div>
                      <div class="text-body-2 text-medium-emphasis">待办名次由站点魔力效率内部排序 · 仅供选种参考</div>
                    </div>
                  </header>
                  <ol class="magicflow-pipeline">
                    <li v-for="candidate in (candidateData.candidates || []).slice(0, 8)" :key="candidate.hash">
                      <span class="magicflow-pipeline__index">{{ candidate.rank }}</span>
                      <div>
                        <strong>{{ candidate.title || '未知种子' }}</strong>
                        <span>{{ Number(candidate.size_gb || 0).toFixed(2) }} GB · {{ candidate.seeders }} 做种 · {{ Number(candidate.age_weeks || 0).toFixed(1) }} 周</span>
                      </div>
                    </li>
                    <li v-if="!(candidateData.candidates || []).length">
                      <div class="magicflow-table-empty">暂无候选</div>
                    </li>
                  </ol>
                </VSheet>
              </template>

              <template v-else>
              <VSheet tag="section" class="magicflow-panel magicflow-torrents app-surface-static">
                <header class="magicflow-panel__head">
                  <div>
                    <div class="magicflow-panel__title-row">
                      <span class="text-subtitle-1 font-weight-medium">托管种子</span>
                      <VChip size="x-small" variant="tonal">{{ bonusData.torrent_count || 0 }}</VChip>
                    </div>
                    <div class="text-body-2 text-medium-emphasis">
                      共 {{ bonusData.torrent_count || 0 }} 个 · 点击任意行查看详情 / 手动保留 / 删除
                    </div>
                  </div>
                  <div class="magicflow-torrent-filters">
                    <VSelect
                      v-model="torrentStatusFilter"
                      :items="torrentStatusOptions"
                      item-title="title"
                      item-value="value"
                      density="compact"
                      variant="outlined"
                      hide-details
                      class="magicflow-status-filter"
                    />
                    <VBtnToggle :model-value="torrentFilter" mandatory color="primary" density="compact" @update:model-value="value => (torrentFilter = value)">
                      <VBtn value="all">全部</VBtn>
                      <VBtn value="protected">已保护</VBtn>
                    </VBtnToggle>
                  </div>
                </header>
                <VDataTable
                  class="magicflow-torrent-table torrent-table-clickable"
                  :headers="torrentHeaders"
                  :items="sortedTorrents"
                  :loading="taskLoading"
                  :items-per-page="10"
                  density="comfortable"
                  @click:row="onTorrentRowClick"
                >
                  <template #item.title="{ item }">
                    <div class="torrent-title-cell">
                      <strong>{{ item.title || '未知种子' }}</strong>
                      <span>{{ selectedTask.site_name }}</span>
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
                      @click="torrentAction(item, item.is_protected ? 'unprotect' : 'protect')"
                    />
                    <VBtn
                      size="small"
                      variant="text"
                      color="error"
                      icon="mdi-delete-outline"
                      aria-label="删除"
                      @click="torrentAction(item, 'delete')"
                    />
                  </template>
                  <template #no-data>
                    <div class="magicflow-table-empty">当前筛选下没有托管种子</div>
                  </template>
                </VDataTable>
                <div class="magicflow-mobile-torrents">
                  <article
                    v-for="item in sortedTorrents"
                    :key="item.hash || item.title"
                    class="magicflow-mobile-torrent"
                    @click="openTorrentDetail(item)"
                  >
                    <div class="magicflow-mobile-torrent__head">
                      <div class="magicflow-mobile-torrent__title">
                        <strong>{{ item.title || '未知种子' }}</strong>
                        <span>{{ selectedTask.site_name }}</span>
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
                      <VBtn size="small" variant="tonal" :color="item.is_protected ? 'grey' : 'primary'" :prepend-icon="item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline'" @click.stop="torrentAction(item, item.is_protected ? 'unprotect' : 'protect')">
                        {{ item.is_protected ? '取消保留' : '保留' }}
                      </VBtn>
                      <VBtn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click.stop="torrentAction(item, 'delete')">删除</VBtn>
                    </div>
                  </article>
                  <div v-if="!sortedTorrents.length" class="magicflow-table-empty">当前筛选下没有托管种子</div>
                </div>
              </VSheet>
              </template>
            </VWindowItem>


            <VWindowItem value="config">
              <div class="magicflow-config-grid">
                <VSheet tag="section" class="magicflow-panel app-surface-static">
                  <header class="magicflow-panel__head">
                    <div>
                      <div class="text-subtitle-1 font-weight-medium">任务规则</div>
                      <div class="text-body-2 text-medium-emphasis">当前服务端生效配置</div>
                    </div>
                  </header>
                  <dl class="magicflow-facts magicflow-facts--two">
                    <div><dt>任务状态</dt><dd>{{ selectedTask.enabled ? '启用' : '暂停' }}</dd></div>
                    <div><dt>站点</dt><dd>{{ selectedTask.site_name }}</dd></div>
                    <div><dt>下载器</dt><dd>{{ selectedTask.downloader }}</dd></div>
                    <div><dt>下载器标签</dt><dd>{{ selectedTask.brush_tag || '未设置' }}</dd></div>
                    <div><dt>种子大小</dt><dd>{{ taskConfig.size || '不限' }}</dd></div>
                    <div><dt>做种人数</dt><dd>{{ taskConfig.seeder || '不限' }}</dd></div>
                    <div><dt>发布时间</dt><dd>{{ taskConfig.pubtime ? `${taskConfig.pubtime} 分钟` : '不限' }}</dd></div>
                    <div><dt>排除 H&R</dt><dd>{{ taskConfig.hr === 'yes' ? '是' : '否' }}</dd></div>
                    <div><dt>包含规则</dt><dd>{{ taskConfig.include || '无' }}</dd></div>
                    <div><dt>排除规则</dt><dd>{{ taskConfig.exclude || '无' }}</dd></div>
                    <div><dt>最短做种</dt><dd>{{ taskConfig.min_seed_time ? `${taskConfig.min_seed_time} 小时` : '不限' }}</dd></div>
                    <div><dt>最低分享率</dt><dd>{{ Number(taskConfig.min_ratio || 0).toFixed(2) }}</dd></div>
                    <div><dt>保种体积</dt><dd>{{ taskConfig.disk_size_gb ? `${taskConfig.disk_size_gb} GB` : '不限' }}</dd></div>
                    <div><dt>最低魔力</dt><dd>{{ taskConfig.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.min_bonus_per_hour).toFixed(2)} /h` }}</dd></div>
                    <div><dt>最多保留</dt><dd>{{ taskConfig.max_keep_torrents == null ? '自动 / 不限' : `${taskConfig.max_keep_torrents} 个` }}</dd></div>
                    <div><dt>单轮最多新增</dt><dd>{{ taskConfig.max_add_per_run ?? 10 }} 个</dd></div>
                    <div><dt>同时下载上限</dt><dd>{{ taskConfig.max_download_concurrent ?? 10 }} 个</dd></div>
                    <div><dt>每轮参评候选</dt><dd>{{ taskConfig.top_n ?? 30 }} 个</dd></div>
                    <div><dt>每轮翻页数</dt><dd>{{ taskConfig.browse_pages ?? 3 }} 页</dd></div>
                    <div><dt>保护阈值</dt><dd>{{ taskConfig.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.bonus_protect_threshold).toFixed(0) }}</dd></div>
                    <div><dt>自动补种</dt><dd>{{ taskConfig.refill_when_empty ? '开启' : '关闭' }}</dd></div>
                    <div><dt>存量复用</dt><dd>{{ taskConfig.reuse_existing ? (taskConfig.reuse_verify ? '开启（校验）' : '开启（跳过校验）') : '关闭' }}</dd></div>
                    <div><dt>无进度清理</dt><dd>{{ taskConfig.cleanup_no_progress ? `开启（${taskConfig.no_progress_minutes ?? 30} 分钟）` : '关闭' }}</dd></div>
                    <div><dt>慢速清理</dt><dd>{{ taskConfig.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.slow_progress_max_hours ?? 48}h 下不完即清）` }}</dd></div>
                    <div><dt>自动恢复暂停</dt><dd>{{ taskConfig.auto_resume_paused === false ? '关闭' : '开启' }}</dd></div>
                    <div><dt>公式 T0/N0</dt><dd>{{ taskConfig.bonus_t0 ?? '默认' }} / {{ taskConfig.bonus_n0 ?? '默认' }}</dd></div>
                    <div><dt>公式 B0/L</dt><dd>{{ taskConfig.bonus_b0 ?? '默认' }} / {{ taskConfig.bonus_l ?? '默认' }}</dd></div>
                    <div><dt>零魔权重</dt><dd>{{ taskConfig.bonus_zero_weight ?? '默认' }}</dd></div>
                    <div><dt>保底魔力</dt><dd>{{ Number(taskConfig.min_bonus_to_keep || 0).toFixed(2) }}</dd></div>
                  </dl>
                </VSheet>

                <VSheet tag="section" class="magicflow-panel app-surface-static">
                  <header class="magicflow-panel__head">
                    <div>
                      <div class="text-subtitle-1 font-weight-medium">任务操作</div>
                      <div class="text-body-2 text-medium-emphasis">以下操作只影响当前任务</div>
                    </div>
                  </header>
                  <div class="magicflow-config-actions">
                    <div>
                      <strong>执行一次</strong>
                      <span>立即按当前策略抓取候选并养护做种</span>
                      <VBtn color="primary" variant="tonal" prepend-icon="mdi-sync" :loading="saving" @click="runOperation">
                        立即执行
                      </VBtn>
                    </div>
                    <VDivider />
                    <div>
                      <strong>编辑任务</strong>
                      <span>调整调度、魔力门槛与公式参数</span>
                      <VBtn variant="tonal" prepend-icon="mdi-pencil-outline" @click="openEditTask">编辑任务</VBtn>
                    </div>
                    <VDivider />
                    <div>
                      <strong>删除任务</strong>
                      <span>存在活跃种子时后端会拒绝删除，避免留下失管任务</span>
                      <VBtn color="error" variant="tonal" prepend-icon="mdi-delete-outline" @click="deleteDialog = true">删除任务</VBtn>
                    </div>
                  </div>
                </VSheet>
              </div>
            </VWindowItem>
          </VWindow>
        </main>
      </div>
    </template>

    <TaskEditorDialog
      v-model="editorOpen"
      :task="editorTask"
      :sites="status.options.sites"
      :downloaders="status.options.downloaders"
      :saving="saving"
      @save="saveTask"
    />

    <VDialog v-model="torrentDialog" max-width="40rem">
      <VCard v-if="activeTorrent" class="magicflow-dialog">
        <VCardTitle class="text-wrap">{{ activeTorrent.title || '种子详情' }}</VCardTitle>
        <VCardText>
          <dl class="magicflow-facts magicflow-torrent-detail">
            <div><dt>状态</dt><dd><VChip size="small" :color="stateColor(activeTorrent.state)" variant="tonal">{{ stateLabel(activeTorrent.state) }}</VChip></dd></div>
            <div><dt>下载进度</dt><dd>{{ (Number(activeTorrent.progress || 0) * 100).toFixed(1) }}%</dd></div>
            <div><dt>大小</dt><dd>{{ Number(activeTorrent.size_gb || 0).toFixed(2) }} GB</dd></div>
            <div><dt>上传量</dt><dd>{{ formatBytes(activeTorrent.uploaded) }}</dd></div>
            <div><dt>分享率</dt><dd>{{ Number(activeTorrent.ratio || 0).toFixed(2) }}</dd></div>
            <div><dt>手动保留</dt><dd>{{ activeTorrent.is_protected ? '已保护' : '未保护' }}</dd></div>
          </dl>
          <div class="text-caption text-medium-emphasis magicflow-hash-line">infohash：{{ activeTorrent.hash }}</div>
        </VCardText>
        <VCardActions>
          <VBtn
            variant="tonal"
            :color="activeTorrent.is_protected ? 'grey' : 'primary'"
            :prepend-icon="activeTorrent.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline'"
            :loading="saving"
            @click="detailTorrentAction(activeTorrent.is_protected ? 'unprotect' : 'protect')"
          >{{ activeTorrent.is_protected ? '取消保留' : '保留' }}</VBtn>
          <VBtn color="error" variant="tonal" prepend-icon="mdi-delete-outline" :loading="saving" @click="detailTorrentAction('delete')">删除种子</VBtn>
          <VSpacer />
          <VBtn variant="text" @click="torrentDialog = false">关闭</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="deleteDialog" max-width="28rem">
      <VCard title="删除魔力任务" class="magicflow-dialog">
        <VCardText>确认删除「{{ selectedTask?.name }}」？存在活跃种子时不会执行删除。</VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="deleteDialog = false">取消</VBtn>
          <VBtn color="error" variant="flat" :loading="saving" @click="confirmDeleteTask">删除</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
<style scoped>
.magicflow-page {
  /* ===== 深色磨砂主题（仅限本插件工作台作用域）===== */
  --v-theme-background: 7, 11, 24;
  --v-theme-on-background: 231, 234, 246;
  --v-theme-surface: 17, 23, 43;
  --v-theme-on-surface: 231, 234, 246;
  --v-theme-surface-variant: 38, 46, 78;
  --v-theme-on-surface-variant: 200, 206, 232;
  --v-theme-surface-light: 26, 32, 56;
  --v-theme-surface-bright: 34, 42, 72;
  --v-theme-outline: 92, 102, 152;
  --v-theme-primary: 139, 123, 240;
  --v-theme-on-primary: 255, 255, 255;
  --v-theme-secondary: 122, 132, 212;
  --v-theme-on-secondary: 12, 16, 32;
  --v-theme-error: 235, 100, 122;
  --v-theme-on-error: 255, 255, 255;
  --v-theme-info: 120, 162, 242;
  --v-theme-on-info: 8, 12, 26;
  --v-theme-success: 96, 202, 162;
  --v-theme-on-success: 6, 20, 14;
  --v-theme-warning: 236, 182, 92;
  --v-theme-on-warning: 26, 18, 4;
  --magicflow-panel-bg: rgba(24, 30, 54, 0.72);
  --magicflow-panel-brd: rgba(140, 150, 220, 0.14);

  display: flex;
  flex-direction: column;
  gap: 16px;
  min-inline-size: 0;
  padding: 18px;
  color: rgb(var(--v-theme-on-background));
  border-radius: 20px;
  background:
    radial-gradient(1100px 560px at 12% -12%, rgba(42, 50, 116, 0.55) 0%, transparent 60%),
    radial-gradient(820px 480px at 104% -4%, rgba(74, 46, 128, 0.42) 0%, transparent 56%),
    linear-gradient(180deg, #0b1226 0%, #070b18 100%);
}

.magicflow-page--compact {
  padding: 20px;
}

.magicflow-page__header,
.magicflow-page__identity,
.magicflow-page__actions,
.magicflow-task-head,
.magicflow-task-head__identity,
.magicflow-task-head__title,
.magicflow-task-head__actions,
.magicflow-panel__head,
.magicflow-panel__title-row,
.magicflow-task-item__title,
.magicflow-task-item__meta,
.magicflow-mobile-torrent__head,
.magicflow-mobile-torrent__meta,
.magicflow-diagnostic-head {
  display: flex;
  align-items: center;
}

.magicflow-page__header,
.magicflow-task-head,
.magicflow-panel__head,
.magicflow-mobile-torrent__head,
.magicflow-diagnostic-head {
  justify-content: space-between;
}

.magicflow-page__header {
  min-block-size: 48px;
  gap: 16px;
}

.magicflow-page__identity,
.magicflow-task-head__identity {
  min-inline-size: 0;
  gap: 12px;
}

.magicflow-page__identity h1,
.magicflow-task-head h2 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: 0;
}

.magicflow-page__identity p,
.magicflow-task-head p {
  margin: 2px 0 0;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.875rem;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

/* 任务头卡：站点图标（方形圆角，居中于头像位） */
.magicflow-task-head__avatar {
  overflow: hidden;
}

.magicflow-task-head__site-icon {
  display: block;
  inline-size: 64%;
  block-size: 64%;
  object-fit: contain;
  border-radius: 6px;
}

.magicflow-page__actions,
.magicflow-task-head__actions,
.magicflow-task-head__title,
.magicflow-panel__title-row,
.magicflow-mobile-torrent__meta {
  flex-wrap: wrap;
  gap: 8px;
}

.settings-menu__body {
  display: grid;
  gap: 8px;
  max-block-size: min(70vh, 34rem);
  overflow-y: auto;
}

.magicflow-settings-menu {
  inline-size: min(25rem, calc(100vw - 24px));
}

.magicflow-loading,
.magicflow-empty {
  min-block-size: 20rem;
}

.magicflow-empty {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  text-align: center;
}

.magicflow-mobile-select {
  display: none;
}

.magicflow-mobile-toolbar {
  display: none;
}

.magicflow-layout {
  display: grid;
  grid-template-columns: minmax(13.5rem, 0.3fr) minmax(0, 1.7fr);
  align-items: start;
  gap: 18px;
  min-inline-size: 0;
}

.magicflow-task-rail {
  position: sticky;
  top: 76px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-block-size: calc(100dvh - 104px);
  padding: 12px;
  overflow-y: auto;
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
}

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

.magicflow-workspace {
  min-inline-size: 0;
}

.magicflow-task-head {
  min-block-size: 52px;
  gap: 12px;
  margin-block-end: 12px;
}

.magicflow-tabs {
  max-inline-size: 100%;
}

.magicflow-window {
  padding-block-start: 16px;
}

.magicflow-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.magicflow-stat,
.magicflow-panel {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
}

.magicflow-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-block-size: 116px;
  padding: 16px;
}

.magicflow-stat > span,
.magicflow-stat > small {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-stat > strong {
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.magicflow-stat :deep(.v-progress-linear) {
  margin-block-start: auto;
}

.magicflow-overview-grid,
.magicflow-diagnostic-grid,
.magicflow-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-block-start: 12px;
}

.magicflow-panel {
  min-inline-size: 0;
  padding: 16px;
}

.magicflow-panel__head,
.magicflow-diagnostic-head {
  align-items: flex-start;
  gap: 12px;
}

.magicflow-facts {
  display: grid;
  gap: 11px;
  margin: 18px 0 0;
}

.magicflow-facts--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.magicflow-facts > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-inline-size: 0;
}

.magicflow-facts dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-facts dd {
  margin: 0;
  text-align: end;
  overflow-wrap: anywhere;
}

.magicflow-run-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-block: 20px;
}

.magicflow-run-summary > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.magicflow-run-summary span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.8rem;
}

.magicflow-run-summary strong {
  font-size: 1.2rem;
}

.magicflow-torrents {
  margin-block-start: 12px;
}

.magicflow-torrent-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.magicflow-status-filter {
  inline-size: 13rem;
  max-inline-size: 100%;
}

.magicflow-torrent-table {
  margin-block-start: 8px;
  background: transparent;
}

.torrent-table-clickable :deep(tbody tr) {
  cursor: pointer;
}

.magicflow-torrent-detail {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.magicflow-hash-line {
  margin-block-start: 10px;
  overflow-wrap: anywhere;
}

.torrent-title-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-inline-size: 30rem;
}

.torrent-status-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.torrent-title-cell strong,
.torrent-title-cell span {
  overflow-wrap: anywhere;
}

.torrent-title-cell span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.78rem;
}

.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
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

.magicflow-diagnostic-head {
  margin-block-end: 12px;
}

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

.magicflow-pipeline li > div,
.magicflow-events article > div,
.magicflow-config-actions > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-inline-size: 0;
}

.magicflow-pipeline li span,
.magicflow-events article span,
.magicflow-config-actions span {
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

.magicflow-reasons {
  display: flex;
  flex-direction: column;
  gap: 13px;
  max-block-size: min(30rem, 52dvh);
  margin-block-start: 18px;
  padding-inline-end: 4px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.magicflow-reason > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-block-end: 5px;
}

.magicflow-reason__track {
  display: block;
  block-size: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-reason__track i {
  display: block;
  block-size: 100%;
  border-radius: inherit;
  background: rgb(var(--v-theme-warning));
}

.magicflow-events {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-block-size: min(30rem, 52dvh);
  margin-block-start: 16px;
  padding-inline-end: 4px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.magicflow-events article {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 10px;
}

.magicflow-config-actions {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-block-start: 16px;
}

.magicflow-config-actions :deep(.v-btn) {
  align-self: flex-start;
  margin-block-start: 8px;
}

@media (min-width: 960px) {
  /* 详情弹窗由宿主提供固定高度，内部只让右侧工作区承担页面滚动。 */
  .magicflow-page--compact {
    block-size: calc(100dvh - 48px);
    min-block-size: 0;
    overflow: hidden;
  }

  .magicflow-page--compact .magicflow-layout {
    flex: 1 1 auto;
    grid-template-rows: minmax(0, 1fr);
    align-items: stretch;
    min-block-size: 0;
    overflow: hidden;
  }

  .magicflow-page--compact .magicflow-task-rail {
    position: static;
    block-size: 100%;
    min-block-size: 0;
    max-block-size: none;
    overflow: hidden;
  }

  .magicflow-page--compact .magicflow-task-list {
    flex: 1 1 auto;
    min-block-size: 0;
    padding-inline-end: 2px;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
  }

  .magicflow-page--compact .magicflow-workspace {
    block-size: 100%;
    min-block-size: 0;
    padding-inline-end: 4px;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
  }
}

@media (max-width: 1199px) {
  .magicflow-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 959px) {
  .magicflow-page {
    padding: 12px;
  }

  .magicflow-page--compact {
    padding-block-start: 0;
  }

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

  .magicflow-page__header,
  .magicflow-task-head {
    align-items: flex-start;
  }

  .magicflow-task-rail {
    display: none;
  }

  .magicflow-mobile-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-block-end: 4px;
  }

  .magicflow-mobile-toolbar .magicflow-mobile-select {
    display: block;
    flex: 1 1 auto;
    min-inline-size: 0;
  }

  .magicflow-mobile-current {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    justify-content: center;
    min-inline-size: 0;
    padding-inline: 2px;
  }

  .magicflow-mobile-current span {
    font-size: 11px;
    color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  }

  .magicflow-mobile-current strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .magicflow-mobile-add {
    flex: 0 0 auto;
  }

  .magicflow-layout {
    grid-template-columns: 1fr;
  }

  .magicflow-overview-grid,
  .magicflow-diagnostic-grid,
  .magicflow-config-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 699px) {
  /* 窄屏隐藏顶部「新建任务」，交给移动工具栏的「新建」按钮 */
  .magicflow-page .magicflow-header-create {
    display: none;
  }

  .magicflow-task-head {
    flex-direction: column;
    gap: 0;
  }

  .magicflow-task-head__identity {
    align-items: flex-start;
    inline-size: 100%;
  }

  /* 预览图：任务名左侧、状态徽章推到卡片最右 */
  .magicflow-task-head__body {
    flex: 1 1 auto;
    min-inline-size: 0;
  }

  .magicflow-task-head__title {
    inline-size: 100%;
    justify-content: space-between;
    align-items: center;
  }

  .magicflow-diagnostic-head,
  .magicflow-panel__head {
    flex-direction: column;
    align-items: flex-start;
  }

  /* 预览图：运行流程卡头部保持标题左 / 阶段标签右（不堆叠） */
  .magicflow-flow .magicflow-panel__head {
    flex-direction: row;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }

  .magicflow-flow .magicflow-panel__head > div {
    min-inline-size: 0;
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

  .magicflow-task-head__actions {
    inline-size: 100%;
    justify-content: flex-end;
    gap: 0;
    margin-block-start: 10px;
    padding-block-start: 8px;
    border-block-start: 1px solid rgba(140, 150, 220, 0.1);
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

  .magicflow-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .magicflow-stat {
    min-block-size: 104px;
    padding: 13px;
  }

  .magicflow-stat > strong {
    font-size: 1.05rem;
  }

  .magicflow-panel {
    padding: 14px;
  }

  .magicflow-panel__head {
    flex-wrap: wrap;
  }

  .magicflow-facts--two {
    grid-template-columns: 1fr;
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

  .magicflow-run-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 419px) {
  .magicflow-stat-grid {
    grid-template-columns: 1fr;
  }

  .magicflow-page:not(.magicflow-page--compact) .magicflow-page__header,
  .magicflow-page:not(.magicflow-page--compact) .magicflow-page__identity {
    gap: 8px;
  }

  .magicflow-task-head__title {
    align-items: center;
    flex-wrap: wrap;
  }
}

/* 「运行诊断」流程链 */
.magicflow-flow__chain {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}

.magicflow-flow__node {
  position: relative;
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 9px;
  min-width: 0;
  text-align: center;
}

/* 待执行：细空心灰圈，无填充、无光晕 */
.magicflow-flow__dot {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 2px solid rgba(150, 158, 200, 0.3);
  background: transparent;
  color: transparent;
  z-index: 1;
}

.magicflow-flow__label {
  font-size: 10.5px;
  line-height: 1.2;
  color: #5f688c;
  white-space: nowrap;
}

.magicflow-flow__node.is-done .magicflow-flow__label {
  color: #9aa3c7;
}

/* 连接线：未执行=浅灰虚线；已走过=紫色实线 */
.magicflow-flow__line {
  position: absolute;
  top: 14px;
  right: -50%;
  width: 100%;
  height: 0;
  border-top: 2px dashed rgba(150, 158, 200, 0.3);
  z-index: 0;
}

.magicflow-flow__line.is-done {
  border-top-style: solid;
  border-top-color: #8b7bf0;
  box-shadow: 0 0 8px rgba(139, 123, 240, 0.35);
}

/* 已完成：紫色实心圆 + 白色对勾，无光晕 */
.magicflow-flow__node.is-done .magicflow-flow__dot {
  border-color: #8b7bf0;
  background: linear-gradient(150deg, #9484f5, #6a5cd8);
  box-shadow: 0 4px 14px rgba(139, 123, 240, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.25);
  color: #fff;
}

/* 运行中：紫色实心圆 + 白色对勾 + 细小缓慢脉冲环 + 微弱光晕（仅当前节点） */
.magicflow-flow__node.is-running .magicflow-flow__dot {
  border-color: #a396ff;
  background: linear-gradient(150deg, #9c8cff, #6f60dd);
  color: #fff;
  box-shadow: 0 0 10px rgba(139, 123, 240, 0.5);
}

.magicflow-flow__node.is-running .magicflow-flow__dot::before,
.magicflow-flow__node.is-running .magicflow-flow__dot::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 50%;
  border: 1.5px solid rgba(160, 148, 255, 0.85);
  animation: magicflow-halo 2.6s cubic-bezier(0.22, 0.61, 0.36, 1) infinite;
}

.magicflow-flow__node.is-running .magicflow-flow__dot::before {
  animation-delay: 1.3s;
}

.magicflow-flow__node.is-running .magicflow-flow__label {
  color: #cfc7ff;
  font-weight: 600;
}

/* 出错：红色实心圆 + 白色感叹号 */
.magicflow-flow__node.is-error .magicflow-flow__dot {
  border-color: rgb(var(--v-theme-error));
  background: rgb(var(--v-theme-error));
  color: #fff;
}

/* 运行流程右上角阶段标签（预览图：阶段名 pill + 呼吸圆点） */
.magicflow-flow__tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(139, 123, 240, 0.3);
  background: rgba(139, 123, 240, 0.16);
  color: #bdb4ff;
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
}

.magicflow-flow__tag i {
  inline-size: 6px;
  block-size: 6px;
  border-radius: 50%;
  background: #8b7bf0;
  box-shadow: 0 0 8px #8b7bf0;
}

.magicflow-flow__tag.is-live i {
  animation: magicflow-blink 1.6s ease-in-out infinite;
}

.magicflow-flow__tag.is-error {
  border-color: rgba(235, 100, 122, 0.32);
  background: rgba(235, 100, 122, 0.16);
  color: #f0a0af;
}

.magicflow-flow__tag.is-error i {
  background: rgb(var(--v-theme-error));
  box-shadow: 0 0 8px rgb(var(--v-theme-error));
}

/* 仅运行中节点有光晕；任务结束后 running 类被移除，脉冲动画随之销毁 */
@keyframes magicflow-halo {
  0% { transform: scale(1); opacity: 0.45; }
  100% { transform: scale(1.7); opacity: 0; }
}

@keyframes magicflow-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

/* ===== 深色磨砂主题：卡片 / 面板 / 弹窗 ===== */
.magicflow-page .magicflow-panel,
.magicflow-page .magicflow-stat,
.magicflow-page .magicflow-task-rail,
.magicflow-page .magicflow-task-head,
.magicflow-page .magicflow-flow,
.magicflow-page .magicflow-torrents {
  background: var(--magicflow-panel-bg) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 16px;
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.magicflow-page .magicflow-task-item {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid transparent;
  border-radius: 12px;
}

.magicflow-page .magicflow-task-item--selected {
  background: rgba(139, 123, 240, 0.16);
  border-color: rgba(139, 123, 240, 0.42);
}

.magicflow-page .magicflow-task-item:hover {
  background: rgba(139, 123, 240, 0.1);
}

/* 弹窗（会 teleport 到 body，按专属类名限定，不污染宿主） */
.magicflow-dialog {
  --v-theme-surface: 17, 23, 43;
  --v-theme-on-surface: 231, 234, 246;
  --v-theme-surface-variant: 38, 46, 78;
  --v-theme-on-surface-variant: 200, 206, 232;
  --v-theme-outline: 92, 102, 152;
  --v-theme-primary: 139, 123, 240;
  --v-theme-on-primary: 255, 255, 255;
  --v-theme-error: 235, 100, 122;
  background: rgba(24, 30, 54, 0.92) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}

/* ===== 按预览图对齐：品牌头 / 分段标签 / 数据卡排版 ===== */
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
  color: #fff;
  background: linear-gradient(145deg, #9484f5, #5b4fb8);
  box-shadow: 0 6px 20px rgba(139, 123, 240, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.magicflow-page .magicflow-page__identity h1 {
  font-size: 17px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: 0.2px;
}

/* 品牌区版本号徽标（版本必须常驻显示） */
.magicflow-page .magicflow-page__version {
  display: inline-block;
  margin-inline-start: 8px;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid rgba(139, 123, 240, 0.3);
  background: rgba(139, 123, 240, 0.16);
  color: #bdb4ff;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.5;
  vertical-align: middle;
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

/* 任务头「删除」按钮：与其余图标按钮拉开一点距离，降低误触 */
.magicflow-page .magicflow-task-head__actions .v-btn[color='error'] {
  margin-inline-start: 2px;
}

.magicflow-page .magicflow-task-head h2 {
  font-size: 15px;
  font-weight: 650;
}

.magicflow-page .magicflow-task-head p {
  font-size: 11px;
}

/* 分段式标签卡（预览图样式） */
.magicflow-page .magicflow-tabs {
  display: flex;
  gap: 4px;
  padding: 6px;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 16px;
  background: var(--magicflow-panel-bg);
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.magicflow-page .magicflow-tab {
  flex: 1 1 0;
  min-inline-size: 0;
  padding: 9px 4px;
  border: 0;
  border-radius: 11px;
  color: rgba(231, 234, 246, 0.6);
  background: transparent;
  font: inherit;
  font-size: 12px;
  text-align: center;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.magicflow-page .magicflow-tab.is-active {
  color: #cfc7ff;
  background: rgba(139, 123, 240, 0.18);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px rgba(139, 123, 240, 0.4);
}

/* 数据卡：数值在上、说明在下（预览图样式） */
@media (max-width: 1199px) {
  .magicflow-page .magicflow-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.magicflow-page .magicflow-stat {
  gap: 6px;
  min-block-size: 84px;
  padding: 14px 16px;
}

.magicflow-page .magicflow-stat > strong {
  font-size: 20px;
  font-weight: 680;
  line-height: 1.2;
  letter-spacing: 0.2px;
}

.magicflow-page .magicflow-stat > span,
.magicflow-page .magicflow-stat > small {
  font-size: 11px;
}

.magicflow-page .magicflow-stat--accent > strong {
  color: #c3b8ff;
}

/* 面板标题排版（预览图：14px/600 + 11px 说明） */
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

/* 过滤原因条形图（预览图：8px 圆角 + 紫色渐变） */
.magicflow-page .magicflow-reason > div {
  font-size: 11.5px;
}

.magicflow-page .magicflow-reason__track {
  block-size: 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
}

.magicflow-page .magicflow-reason__track i {
  border-radius: 999px;
  background: linear-gradient(90deg, #6a5cd8, #9c8cff);
  box-shadow: 0 0 12px rgba(139, 123, 240, 0.5);
}

/* 操作记录（预览图：图标瓦片 + 顶部细分隔线） */
.magicflow-page .magicflow-events article {
  align-items: start;
  gap: 11px;
  padding-block: 11px;
  border-top: 1px solid rgba(140, 150, 220, 0.1);
}

.magicflow-page .magicflow-events article:first-child {
  padding-block-start: 0;
  border-top: 0;
}

.magicflow-page .magicflow-events article > .v-icon:first-child {
  inline-size: 30px;
  block-size: 30px;
  flex: 0 0 auto;
  border-radius: 10px;
  background: rgba(139, 123, 240, 0.14);
}

.magicflow-page .magicflow-events article strong {
  font-size: 12.5px;
  font-weight: 600;
}

/* 任务头卡片内边距（对齐预览图 .thead） */
.magicflow-page .magicflow-task-head {
  padding: 14px 16px;
}

/* 种子名称过长时收成 2 行，避免撑破卡片 */
.magicflow-page .torrent-title-cell strong,
.magicflow-page .magicflow-pipeline li strong,
.magicflow-page .magicflow-mobile-torrent__title strong {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 移动端任务选择器：紧凑成圆角下拉，避免大块空白 */
.magicflow-page .magicflow-mobile-select {
  padding-block: 0;
}

.magicflow-page .magicflow-mobile-select .app-responsive-input__meta {
  margin-block-end: 4px;
}

.magicflow-page .magicflow-mobile-select .v-field {
  min-block-size: 42px;
  padding-inline: 12px;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

/* 底部宿主悬浮导航会盖住内容，预留安全间距 */
@media (max-width: 699px) {
  .magicflow-page {
    padding-block-end: 76px;
  }
}
</style>
