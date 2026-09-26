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
  FALLBACK_SOURCE_OPTIONS,
  normalizeDefaults,
  normalizeDownloaderPaths,
  normalizeDownloaderPrefs,
  normalizeIyuuSites,
  normalizeSettings,
  normalizeTask,
  cloudStatusMeta,
  recommendStatusMeta,
  RUN_MODES,
  runModeMeta,
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
const bonusLoadedFor = ref('')
// 按任务缓存托管种子（切任务时秒显，再后台静默刷新）
const bonusCache = {}
const candidateData = ref({ candidates: [], total: 0, reason_counts: {} })
const candidateLoadedAt = ref(0)
const operationData = ref({ operations: [], total: 0 })
const recommendData = ref({ items: [], total: 0, recommended: 0, enabled: true })
const recommendOpen = ref(false)
const recommendActing = ref('')
let recommendTimer = null
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
const torrentDeleteDialog = ref(false)
const pendingTorrentDelete = ref(null)
// 批量操作：选中行（VDataTable show-select 与手机卡片共用）
const selectedRows = ref([])
const batchBusy = ref(false)
const batchDeleteDialog = ref(false)
const selectedHashes = computed(() =>
  (selectedRows.value || []).map(row => row?.hash).filter(Boolean),
)
const settingsDialog = ref(false)
const settingsTab = ref('general')
const settingsDraft = ref({
  enabled: false,
  show_sidebar_nav: true,
  debug_log: false,
  compact_mode: false,
  journal_keep: 200,
  request_interval: 0,
  bonus_upload_limit_kbps: 200,
  brush_upload_limit_kbps: 10240,
  iyuu_token: '',
  iyuu_sites: {},
  fallback_enabled: true,
  fallback_sources: ['themoviedb', 'bangumi', 'douban'],
  fallback_paths: [],
  fallback_interval_minutes: 30,
  fallback_scan_max: 30,
  fallback_sp_to_s00: false,
  fallback_after_import: true,
  fallback_dry_run: false,
  cloud_enabled: false,
  cloud_openlist_url: '',
  cloud_openlist_token: '',
  cloud_source_mount: '/quark',
  cloud_strm_mount: '/movie',
  cloud_paths: [],
  cloud_target_template: '/quark/movie/{rel}',
  cloud_interval_minutes: 360,
  cloud_scan_max: 50,
  cloud_min_size_gb: 0,
  cloud_max_size_gb: 0,
  cloud_min_age_days: 0,
  cloud_exclude_paths: [],
  cloud_exclude_tags: [],
  cloud_upload_limit_mbps: 0,
  cloud_verify: 'size',
  cloud_dry_run: true,
  cloud_delete_local: false,
  cloud_remove_torrent: false,
  cloud_notify: true,
  live_enabled: true,
  live_interval_minutes: 4,
  live_download_alert_mb: 50,
  live_ratio_target: 0.5,
  live_auto_stop: false,
  live_kill_unfree: true,
  live_kill_delete_files: true,
  live_notify: true,
})
// ---- 站点实时数据 + 流量监控（直连站点，非 MP 6h 快照）----
const liveState = ref(null)
const liveLoading = ref(false)
let liveTimer = null
const fallbackState = ref(null)
const fallbackLoading = ref(false)
const fallbackRunning = ref(false)
const fallbackSourceDraft = ref('')
const fallbackProblemShows = computed(() => (((fallbackState.value || {}).report || {}).scanned || []).filter(s => (s.problems || []).length))
const fallbackProblemCount = computed(() => fallbackProblemShows.value.reduce((acc, s) => acc + (s.problems || []).length, 0))
// ---- 云盘归档 ----
const cloudOpen = ref(false)
const cloudState = ref(null)
const cloudLoading = ref(false)
const cloudPlanning = ref(false)
const cloudRunning = ref(false)
const cloudTesting = ref(false)
const cloudTestMsg = ref('')
const cloudTestOk = ref(false)
const cloudLimit = ref(50)
const cloudUploadingPath = ref('')
const cloudPlanItems = ref([])
const cloudPlanStats = ref(null)
const cloudCfg = computed(() => (cloudState.value || {}).cfg || {})
const downloaderPrefsDraft = ref(normalizeDownloaderPrefs({}))
const downloaderPrefsRecommended = ref(null)
const downloaderPrefsLoading = ref(false)
const downloaderPrefsRaw = ref(null)
const downloaderPathsDraft = ref(normalizeDownloaderPaths({}))
const defaultsDraft = ref(normalizeDefaults({}))
const defaultsLoading = ref(false)
// IYUU 云端辅种（可选）：站点表按 MoviePilot 已配置站点生成
const iyuuSites = ref([])
const iyuuLoading = ref(false)
const iyuuTesting = ref(false)
const iyuuStatus = ref(null)
const iyuuShowMore = ref({})
let refreshTimer
let phaseTimer
let warmingTimer
let warmingRetryCount = 0

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
const defaultSavePath = computed(() => (status.value.defaults || {}).save_path || '')
const selectedTask = computed(() => tasks.value.find(item => item.id === selectedTaskId.value) || null)
const summary = computed(() => status.value.summary || {})
const selectedState = computed(() => {
  const t = selectedTask.value
  if (!t) return taskStateMeta('idle', false)
  const mode = t.run_mode || 'running'
  if (mode === 'seeding') return { text: '做种中', color: 'primary', icon: 'mdi-seed-outline' }
  if (mode === 'stopped') return { text: '已停止', color: 'secondary', icon: 'mdi-stop-circle-outline' }
  return taskStateMeta(t.state, true)
})
// 当前任务的运行状态（三态）；与运行时的状态徽章互不冲突
const selectedRunMode = computed(() => runModeMeta(selectedTask.value?.run_mode || 'running'))

// 任务徽章：非「运行中」时直接显示运行状态；运行中则显示实时状态。
function taskBadge(task) {
  const mode = task?.run_mode || 'running'
  if (mode === 'seeding') return runModeMeta('seeding')
  if (mode === 'stopped') return runModeMeta('stopped')
  return taskStateMeta(task?.state, task?.enabled ?? true)
}
// 当前任务是否刷流模式（驱动整块工作台按类型显示）
const taskIsBrush = computed(() => selectedTask.value?.task_type === 'brush')
// 站点账号真实数据（上传/下载/分享率/做种数，来自站点用户页）
const siteUser = computed(() => detailStats.value?.site_user || selectedTask.value?.site_user || {})
const taskConfig = computed(() => selectedTask.value || {})
// 刷流保种天数（缺省=2，兼容未写入该字段的旧任务）
const brushSeedDays = computed(() => {
  const v = taskConfig.value?.brush_seed_days
  return v === undefined || v === null || v === '' ? 2 : Number(v)
})
// 当前任务的「任务目标」完成情况文案
const goalFactText = computed(() => {
  const t = taskConfig.value || {}
  if (!t.goal_has) return '未设置'
  const unit = t.goal_unit || (t.task_type === 'brush' ? 'GB' : '魔力值')
  const cur = Number(t.goal_current || 0)
  const tgt = Number(t.goal_target || 0)
  const curText = unit === 'GB' ? cur.toFixed(1) : cur.toFixed(2)
  return `${curText} / ${tgt} ${unit}${t.goal_reached ? '（已达标）' : ''}`
})
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

// 运行诊断流程链（v5 阶段）—— 骨架五阶段两模式共用，但每阶段实做不同，文案按类型分显
const FLOW_STEPS_BONUS = [
  { key: 'entry', label: '入口检查' },
  { key: 'fetch', label: '抓取候选' },
  { key: 'wash', label: '洗池过滤' },
  { key: 'classify', label: '魔力排序' },
  { key: 'process', label: '保种入库' },
]
const FLOW_STEPS_BRUSH = [
  { key: 'entry', label: '入口检查' },
  { key: 'fetch', label: '抓取候选' },
  { key: 'wash', label: '免费筛选' },
  { key: 'classify', label: '下载人数排序' },
  { key: 'process', label: '复用·入库' },
]
const flowSteps = computed(() => (taskIsBrush.value ? FLOW_STEPS_BRUSH : FLOW_STEPS_BONUS))

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
  const steps = flowSteps.value
  const idx = steps.findIndex(step => step.key === phase)
  return steps.map((step, i) => {
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
  const step = flowSteps.value.find(item => item.key === (detail.value?.last_phase || ''))
  return step ? step.label : runStatusText(detail.value?.last_run_status)
})

const torrentHeaders = [
  { title: '', key: 'select', sortable: false, width: 44 },
  { title: '种子', key: 'title', sortable: false },
  { title: '状态', key: 'status', sortable: false, width: 120 },
  { title: '大小', key: 'size_gb', sortable: false, width: 96 },
  { title: '上传量', key: 'uploaded', sortable: false, width: 96 },
  { title: '分享率', key: 'ratio', sortable: false, width: 84 },
  { title: '操作', key: 'actions', sortable: false, width: 120 },
]

// 全选（当前筛选结果）
const allFilteredSelected = computed(
  () => sortedTorrents.value.length > 0 && selectedHashes.value.length === sortedTorrents.value.length,
)

function notify(message, color = 'success') {
  const method = ['error', 'info', 'warning', 'success'].includes(color) ? color : 'success'
  if (typeof hostToast?.[method] === 'function') {
    hostToast[method](message)
  } else if (method === 'error') {
    error.value = message
  }
}

const KIND_TEXT = { run: '执行', selection: '选种加入', deletion: '删种清理', protection: '手动保留', unprotection: '取消保留', reuse: '存量复用', pause: '暂停种子', resume: '恢复运行', recheck: '强制校验', goal: '达标停止', state: '运行状态', tag: '标签变更', fallback: '元数据兜底', cloud: '云盘归档' }
const STATE_TEXT = { submitting: '提交中', accepted: '已受理', completed: '已完成', failed: '失败' }
const KIND_ICON = {
  run: 'mdi-play-circle-outline',
  selection: 'mdi-download-outline',
  deletion: 'mdi-delete-outline',
  reuse: 'mdi-content-duplicate',
  protection: 'mdi-shield-check-outline',
  unprotection: 'mdi-shield-off-outline',
  pause: 'mdi-pause-circle-outline',
  resume: 'mdi-play-circle-outline',
  recheck: 'mdi-sync',
  goal: 'mdi-flag-checkered',
  state: 'mdi-power',
  tag: 'mdi-tag-outline',
  fallback: 'mdi-file-xml-box',
  cloud: 'mdi-cloud-upload-outline',
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
  if (record.kind === 'tag') return 'purple'
  if (record.kind === 'run') return 'secondary'
  return 'primary'
}

/** 操作记录明细：展开状态表（key=operation_id）。 */
const expandedOps = ref({})

/** 可展开的明细条目：仅 run 记录展开（tags/watchdog 等单条事件摘要已够）。
 *  run 记录第 0 项是汇总行，与上方摘要重复，过滤掉。 */
function opDetailItems(record) {
  if (!record || record.kind !== 'run') return []
  return (record.items || []).filter((it) => it.source && it.source !== 'run')
}

function hasOpDetail(record) {
  return opDetailItems(record).length > 0
}

function isOpDetailOpen(opId) {
  return !!expandedOps.value[opId]
}

function toggleOpDetail(opId) {
  expandedOps.value = { ...expandedOps.value, [opId]: !expandedOps.value[opId] }
}

/** 明细行的短标签（来源/动作）。 */
const ITEM_SOURCE_TEXT = { add: '新增', 'add-fail': '失败', reuse: '复用', 'reuse-fail': '辅种失败', adopt: '纳管', watchdog: '看门狗', run: '汇总' }

function itemSourceText(src) {
  return ITEM_SOURCE_TEXT[src] || ''
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

// 托管种子状态文本：做种 / 下载 X% / 暂停 / 整理中（参考 BrushFlow）
// 注意：progress=100 不等于「做种中」——已暂停/停止、整理中、校验中的种子要显示真实状态，
// 否则会出现「状态列写作种中、筛选却归到已暂停」的口径不一致。
const TORRENT_TRANSIENT_STATES = {
  moving: '整理中',
  allocating: '分配空间',
  checkingup: '校验中',
  checkingdl: '校验中',
  checkingresumedata: '校验中',
  forcedmetadl: '获取元数据',
}
const TORRENT_PAUSED_STATES = ['pausedup', 'pauseddl', 'stoppedup', 'stoppeddl']

function torrentStateText(item) {
  const key = String(item?.state || '').toLowerCase()
  if (TORRENT_TRANSIENT_STATES[key]) return TORRENT_TRANSIENT_STATES[key]
  if (TORRENT_PAUSED_STATES.includes(key)) return stateLabel(item?.state) || '已暂停'
  const pct = torrentProgressPct(item)
  if (pct >= 100) return '做种中'
  if (pct <= 0) return stateLabel(item?.state) || '等待中'
  return `下载 ${pct}%`
}

// 暂停 / 恢复按钮的口径：下载中的种子是「暂停下载 / 继续下载」，
// 已完成的才是「暂停做种 / 恢复做种」（避免下载中的种子出现「恢复做种」这种别扭文案）。
function torrentIsPaused(item) {
  return TORRENT_PAUSED_STATES.includes(String(item?.state || '').toLowerCase())
}

function torrentPauseLabel(item) {
  return torrentProgressPct(item) >= 100 ? '暂停做种' : '暂停下载'
}

function torrentResumeLabel(item) {
  return torrentProgressPct(item) >= 100 ? '恢复做种' : '继续下载'
}

// 下载进度百分比（0~100），供进度条使用
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}

// 托管种子状态分组（用于状态筛选）
// 覆盖 qBittorrent 全部常见状态，含 moving/allocating/checking*，避免出现
// 「分组里没这一档 → 只选中某个状态就再也看不到这些种子、各档数量之和 ≠ 总数」。
function torrentStatusGroup(item) {
  const key = String(item?.state || '').toLowerCase()
  if (['uploading', 'forcedup', 'stalledup', 'queuedup', 'checkingup'].includes(key)) return 'seeding'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'forcedmetadl', 'checkingdl', 'allocating'].includes(key)) return 'downloading'
  if (key === 'stalleddl') return 'stalled'
  if (TORRENT_PAUSED_STATES.includes(key)) return 'paused'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'other'
}

// 状态筛选选项（带数量）
const torrentStatusOptions = computed(() => {
  const items = bonusData.value.torrents || []
  const count = group => items.filter(item => torrentStatusGroup(item) === group).length
  const opts = [
    { title: `全部状态（${items.length}）`, value: 'all' },
    { title: `做种中（${count('seeding')}）`, value: 'seeding' },
    { title: `下载中（${count('downloading')}）`, value: 'downloading' },
    { title: `下载停滞（${count('stalled')}）`, value: 'stalled' },
    { title: `已暂停 / 停止（${count('paused')}）`, value: 'paused' },
    { title: `出错（${count('error')}）`, value: 'error' },
  ]
  const other = count('other')
  if (other > 0) opts.push({ title: `其它（${other}）`, value: 'other' })
  return opts
})

// 加载插件总览与任务列表。
async function loadStatus() {
  loading.value = true
  try {
    status.value = unwrapResponse(await props.api.get(`${pluginBase.value}/status`)) || status.value
    settingsDraft.value = normalizeSettings({
      enabled: status.value.enabled,
      show_sidebar_nav: status.value.show_sidebar_nav,
      debug_log: status.value.debug_log,
      compact_mode: status.value.compact_mode,
      journal_keep: status.value.journal_keep,
      request_interval: status.value.request_interval,
      bonus_upload_limit_kbps: status.value.bonus_upload_limit_kbps,
      brush_upload_limit_kbps: status.value.brush_upload_limit_kbps,
      iyuu_token: status.value.iyuu_token,
      iyuu_sites: status.value.iyuu_sites,
      ...(status.value.fallback || {}),
      ...(status.value.live ? {
        live_enabled: status.value.live.enabled,
        live_interval_minutes: status.value.live.interval,
        live_download_alert_mb: status.value.live.download_alert_mb,
        live_ratio_target: status.value.live.ratio_target,
        live_auto_stop: status.value.live.auto_stop,
        live_kill_unfree: status.value.live.kill_unfree,
        live_kill_delete_files: status.value.live.kill_delete_files,
        live_notify: status.value.live.notify,
      } : {}),
      ...(status.value.cloud ? {
        cloud_enabled: status.value.cloud.enabled,
        cloud_openlist_url: status.value.cloud.url,
        cloud_openlist_token: '',
        cloud_source_mount: status.value.cloud.source_mount,
        cloud_strm_mount: status.value.cloud.strm_mount,
        cloud_paths: status.value.cloud.paths || [],
        cloud_target_template: status.value.cloud.target_template,
        cloud_interval_minutes: status.value.cloud.interval,
        cloud_scan_max: status.value.cloud.scan_max,
        cloud_min_size_gb: status.value.cloud.min_size_gb,
        cloud_max_size_gb: status.value.cloud.max_size_gb,
        cloud_min_age_days: status.value.cloud.min_age_days,
        cloud_exclude_paths: status.value.cloud.exclude_paths || [],
        cloud_exclude_tags: status.value.cloud.exclude_tags || [],
        cloud_upload_limit_mbps: status.value.cloud.upload_limit_mbps,
        cloud_verify: status.value.cloud.verify,
        cloud_dry_run: status.value.cloud.dry_run,
        cloud_delete_local: status.value.cloud.delete_local,
        cloud_remove_torrent: status.value.cloud.remove_torrent,
        cloud_notify: status.value.cloud.notify,
      } : {}),
    })
    statusLoaded.value = true
    if (!selectedTaskId.value && tasks.value.length) {
      selectTask(tasks.value[0].id)
    } else if (selectedTaskId.value && !tasks.value.some(item => item.id === selectedTaskId.value)) {
      selectedTaskId.value = ''
    }
    scheduleWarmingRetry()
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    loading.value = false
  }
}

// 冷启动时后端先返回轻量壳（warming=true）并后台构建重数据；这里快速重拉几次直到就绪。
function scheduleWarmingRetry() {
  if (status.value && status.value.warming) {
    if (warmingRetryCount < 12) {
      warmingRetryCount += 1
      if (warmingTimer) window.clearTimeout(warmingTimer)
      warmingTimer = window.setTimeout(() => loadStatus(), 1200)
    }
  } else {
    warmingRetryCount = 0
    if (warmingTimer) {
      window.clearTimeout(warmingTimer)
      warmingTimer = null
    }
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
// silent=true：已有数据时后台刷新，不置加载态（切换「托管」时秒显，避免 1~2 秒空白）。
async function loadBonus(taskId, { silent = false } = {}) {
  if (!silent) taskLoading.value = true
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}/bonus`)) || bonusData.value
    bonusData.value = data
    bonusCache[taskId] = data
    bonusLoadedFor.value = taskId
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    if (!silent) taskLoading.value = false
  }
}

const backfilling = ref(false)
async function backfillPages() {
  const taskId = selectedTaskId.value
  if (!taskId || backfilling.value) return
  backfilling.value = true
  try {
    const data = unwrapResponse(await props.api.post(`${pluginBase.value}/tasks/${taskId}/backfill-pages`)) || {}
    notify(`已回填 ${data.resolved || 0} 个详情页链接${data.unresolved ? `（${data.unresolved} 个未匹配）` : ''}`)
  } catch (err) {
    notify(err?.response?.data?.message || err?.message || '回填失败', 'error')
  } finally {
    backfilling.value = false
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

// ---- 推荐甄别（价值生命周期） ----
const showAllRecs = ref(false)
// 列表默认只显示「真·命中推荐」的生命周期项；未达门槛/未识别的临时种默认隐藏（「显示全部」才展开）。
function recWorthShowing(rec) {
  if (!rec) return false
  const st = String(rec.status || '').toLowerCase()
  return st === 'recommended' || st === 'confirmed' || st === 'dismissed' || st === 'deleted'
}
// 展示名：优先「媒体标题 (年份)」；不显示原始下载文件名（文件名只进 tooltip 属性）。
function recName(rec) {
  if (!rec) return ''
  const m = rec.media || {}
  const t = m.title || ''
  if (t) return m.year ? `${t} (${m.year})` : t
  return rec.title || rec.hash || ''
}
const recommendItems = computed(() => {
  const order = { recommended: 0, pending: 1, confirmed: 2, dismissed: 3, deleted: 4 }
  let items = [...(recommendData.value.items || [])]
  if (!showAllRecs.value) items = items.filter(recWorthShowing)
  items.sort((a, b) => {
    const oa = order[a.status] ?? 9
    const ob = order[b.status] ?? 9
    if (oa !== ob) return oa - ob
    return (b.updated_at || 0) - (a.updated_at || 0)
  })
  // 同一部作品（media_key）只保留最靠前的一条（去重：同片多发布/多版本）
  const seen = new Set()
  const out = []
  for (const it of items) {
    const k = it.media_key || it.hash
    if (k && seen.has(k)) continue
    if (k) seen.add(k)
    out.push(it)
  }
  return out
})
const hiddenRecCount = computed(() => (recommendData.value.items || []).filter(i => !recWorthShowing(i)).length)
const confirmedCount = computed(() => (recommendData.value.items || []).filter(i => i.status === 'confirmed').length)
// 可手动确认的行：命中推荐（待确认），或「待核实」里非「已在库 / 重复」的临时种。
function recommendActionable(rec) {
  if (!rec) return false
  const st = String(rec.status || '').toLowerCase()
  if (st === 'recommended') return true
  if (st === 'pending') {
    const r = String(rec.reason || '')
    return !r.includes('已在影视库') && !r.includes('重复推荐')
  }
  return false
}
const pendingCount = computed(() => (recommendData.value.items || []).filter(i => i.status === 'pending').length)

async function loadRecommend() {
  try {
    recommendData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/recommend`)) || { items: [], total: 0 }
  } catch (err) {
    error.value = err?.message || String(err)
  }
}

async function loadLive() {
  if (liveLoading.value) return
  const sid = Number(selectedTask.value?.site_id || 0)
  liveLoading.value = true
  try {
    liveState.value = unwrapResponse(await props.api.get(`${pluginBase.value}/live${sid ? `?site_id=${sid}` : ''}`)) || liveState.value
  } catch (err) {
    // 站点实时数据是增强信息，失败不打断界面
  } finally {
    liveLoading.value = false
  }
}

const siteLive = computed(() => {
  const sid = Number(selectedTask.value?.site_id || 0)
  const rows = (liveState.value || {}).sites || []
  return rows.find(row => Number(row.site_id) === sid) || null
})
const siteLiveCfg = computed(() => (liveState.value || {}).cfg || {})
const siteLiveAlerts = computed(() => ((siteLive.value || {}).alerts || []))
const siteLiveLevel = computed(() => (siteLive.value || {}).level || 'ok')
const siteLiveInfo = computed(() => (siteLive.value || {}).live || {})
const siteLiveRates = computed(() => (siteLive.value || {}).rates || {})
// 站点账号数据：**实时优先**（魔流直连站点），拿不到才回退 MP 的 6h 快照 → 只展示一份，避免重复。
const siteAccount = computed(() => {
  const live = siteLiveInfo.value || {}
  if (live.ok) {
    return {
      ok: true,
      source: 'live',
      upload: live.upload || 0,
      download: live.download || 0,
      ratio: live.ratio,
      seeding: live.seeding,
      leeching: live.leeching,
      bonus: live.bonus,
      bonus_per_hour: live.bonus_per_hour,
      seeding_size: Number((siteUser.value || {}).seeding_size || 0),
      sampledAt: live.ts ? new Date(Number(live.ts) * 1000).toLocaleTimeString() : '',
    }
  }
  const mp = siteUser.value || {}
  return { ...mp, source: mp.ok ? 'mp' : '', sampledAt: '' }
})

async function actRecommend(hash, action, label) {
  if (!hash || recommendActing.value) return
  recommendActing.value = hash + action
  try {
    const data = unwrapResponse(await props.api.post(`${pluginBase.value}/recommend/${hash}/${action}`, {})) || {}
    notify(data.message || `${label}完成`)
    await loadRecommend()
  } catch (err) {
    notify(err?.response?.data?.message || err?.message || `${label}失败`, 'error')
  } finally {
    recommendActing.value = ''
  }
}
function confirmRecommend(hash) {
  return actRecommend(hash, 'confirm', '确认')
}
function dismissRecommend(hash) {
  return actRecommend(hash, 'dismiss', '忽略')
}
function openRecommend() {
  recommendOpen.value = true
  loadRecommend()
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
  if (activeTab.value === 'pool' && poolView.value === 'candidates') loadCandidates(taskId)
}

// 重新拉取当前任务的全部明细数据。
function reloadSelected(taskId = selectedTaskId.value) {
  if (!taskId) return
  selectedTaskId.value = taskId
  detail.value = null
  const cachedBonus = bonusCache[taskId]
  if (cachedBonus) {
    // 命中缓存：先秒显，再后台静默刷新
    bonusData.value = cachedBonus
    bonusLoadedFor.value = taskId
  } else {
    bonusData.value = { torrents: [], total_bonus: 0, torrent_count: 0, protected_count: 0 }
    bonusLoadedFor.value = ''
  }
  candidateData.value = { candidates: [], total: 0, reason_counts: {} }
  candidateLoadedFor.value = ''
  candidateLoadedAt.value = 0
  operationData.value = { operations: [], total: 0 }
  loadDetail(taskId)
  loadBonus(taskId, { silent: !!cachedBonus })
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

// 切换当前任务的运行状态（running / seeding / stopped）。
async function setRunMode(mode) {
  if (!selectedTask.value) return
  const target = mode || 'running'
  if (target === (selectedTask.value.run_mode || 'running')) return
  saving.value = true
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/state`, { mode: target }),
    )
    notify(`运行状态已切换为「${runModeMeta(target).text}」`)
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
  editorTask.value = cloneTask(status.value.defaults || {})
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

// 对托管种子执行 保留 / 取消保留 / 暂停 / 恢复 / 强制校验 / 删除。
const TORRENT_ACTION_LABEL = {
  protect: '已保留种子',
  unprotect: '已取消保留',
  pause: '已暂停种子（不会被自动恢复）',
  resume: '已恢复做种',
  recheck: '已开始重新校验',
  delete: '已删除种子',
}

// 提示文案随种子状态变化：下载中的是「暂停 / 继续下载」，已完成的才是「暂停 / 恢复做种」，
// 避免下载中的种子弹出「已恢复做种」这种说不通的提示。
function torrentActionMessage(torrent, action) {
  if (action === 'pause' || action === 'resume') {
    const seeding = torrentProgressPct(torrent) >= 100
    if (action === 'pause') return seeding ? '已暂停做种（不会被自动恢复）' : '已暂停下载（不会被自动恢复）'
    return seeding ? '已恢复做种' : '已继续下载'
  }
  return TORRENT_ACTION_LABEL[action] || '操作已完成'
}

async function torrentAction(torrent, action) {
  saving.value = true
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/torrents/${torrent.hash}/${action}`, {}),
    )
    notify(torrentActionMessage(torrent, action))
    await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)])
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 删除种子需二次确认（避免手滑，删种不可逆）
function requestTorrentDelete(torrent) {
  if (!torrent) return
  pendingTorrentDelete.value = torrent
  torrentDeleteDialog.value = true
}

async function confirmTorrentDelete() {
  const target = pendingTorrentDelete.value
  if (!target) return
  await torrentAction(target, 'delete')
  torrentDeleteDialog.value = false
  // 若刚删的是详情弹窗里那颗，一并关掉
  if ((activeTorrent.value?.hash || '') && (activeTorrent.value?.hash || '').toLowerCase() === (target.hash || '').toLowerCase()) {
    torrentDialog.value = false
  }
  pendingTorrentDelete.value = null
}

// ---------------- 批量操作 ----------------
const BATCH_LABEL = {
  protect: '批量保留',
  unprotect: '批量取消保留',
  pause: '批量暂停',
  resume: '批量恢复',
  recheck: '批量校验',
  delete: '批量删除',
}

async function batchAction(action) {
  const hashes = selectedHashes.value
  if (!hashes.length || !selectedTask.value) return
  batchBusy.value = true
  try {
    const res = unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/torrents/batch`, { action, hashes }),
    )
    const done = Number(res?.success_count ?? hashes.length)
    notify(`${BATCH_LABEL[action] || '批量操作'}完成：${done} 个`)
    selectedRows.value = []
    batchDeleteDialog.value = false
    await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)])
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    batchBusy.value = false
  }
}

function selectAllFiltered() {
  selectedRows.value = [...sortedTorrents.value]
}

function clearSelection() {
  selectedRows.value = []
}

// 复制 infohash
async function copyTorrentHash(hash) {
  const text = String(hash || '')
  if (!text) return
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    notify('infohash 已复制')
  } catch (err) {
    error.value = `复制失败：${err?.message || err}`
  }
}

// 手机卡片上的勾选（对象引用与表格行一致）
function toggleTorrentSelection(item) {
  if (!item) return
  const key = (item.hash || '').toLowerCase()
  const exists = (selectedRows.value || []).some(row => (row?.hash || '').toLowerCase() === key)
  selectedRows.value = exists
    ? selectedRows.value.filter(row => (row?.hash || '').toLowerCase() !== key)
    : [...selectedRows.value, item]
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
  if (target && typeof target.closest === 'function' && target.closest('.v-btn, button, a, input, label, .v-selection-control')) return
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

// 打开插件设置弹窗。
async function openSettings(tab = 'general') {
  settingsTab.value = tab
  settingsDialog.value = true
  await Promise.all([loadDownloaderPrefs(), loadDefaults(), loadIyuuSites()])
  if (tab === 'fallback') loadFallback()
  if (tab === 'cloud') loadCloud()
}

// ── 云盘归档 ─────────────────────────────────────────────
async function loadCloud() {
  cloudLoading.value = true
  try {
    cloudState.value = unwrapResponse(await props.api.get(`${pluginBase.value}/cloud`))
    if (!cloudPlanStats.value) cloudPlanStats.value = (cloudState.value?.plan_stats || null)
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    cloudLoading.value = false
  }
}

async function testCloud() {
  cloudTesting.value = true
  cloudTestMsg.value = ''
  try {
    const res = unwrapResponse(await props.api.get(`${pluginBase.value}/cloud/test`))
    cloudTestOk.value = Boolean(res?.ok)
    cloudTestMsg.value = res?.ok
      ? `连通正常 · 源挂载 ${res.source_items ?? '?'} 项 · strm 视图 ${res.strm_items ?? '?'} 项`
      : (res?.message || '连接失败')
  } catch (err) {
    cloudTestOk.value = false
    cloudTestMsg.value = err?.message || String(err)
  } finally {
    cloudTesting.value = false
  }
}

async function planCloud() {
  cloudPlanning.value = true
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/cloud/plan?limit=${cloudLimit.value || 50}`))
    cloudPlanItems.value = res?.items || []
    cloudPlanStats.value = res?.stats || null
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    cloudPlanning.value = false
  }
}

async function uploadCloudOne(item) {
  if (!item?.path) return
  cloudUploadingPath.value = item.path
  try {
    const res = unwrapResponse(await props.api.post(
      `${pluginBase.value}/cloud/upload?dry_run=false&path=${encodeURIComponent(item.path)}`,
    ))
    item.status = res?.status || 'uploading'
    item.message = res?.message || ''
    notify(item.message || '已开始上传')
    scheduleCloudPoll()
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    cloudUploadingPath.value = ''
  }
}

// 上传/归档是后台跑的：轮询到没有 uploading / running 就自动停。
let cloudPollTimer = null
function scheduleCloudPoll() {
  if (cloudPollTimer) return
  cloudPollTimer = window.setInterval(async () => {
    await loadCloud()
    const records = (cloudState.value || {}).records || []
    const uploading = records.some(r => r?.status === 'uploading')
    if (!uploading && !(cloudState.value || {}).running) {
      window.clearInterval(cloudPollTimer)
      cloudPollTimer = null
    }
  }, 6000)
}

function cloudRecordFor(item) {
  const key = String((item || {}).path || '')
  const records = (cloudState.value || {}).records || []
  return records.find(r => String(r?.path || '') === key) || null
}

async function runCloud(dryRun = true) {
  cloudRunning.value = true
  try {
    const res = unwrapResponse(await props.api.post(
      `${pluginBase.value}/cloud/run?dry_run=${dryRun ? 'true' : 'false'}&limit=${cloudLimit.value || 50}`,
    ))
    notify(res?.message || (dryRun ? '归档演练已开始' : '归档任务已开始'))
    setTimeout(() => { loadCloud() }, 3000)
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    cloudRunning.value = false
  }
}

function openCloud() {
  cloudOpen.value = true
  loadCloud()
}

// ── 元数据兜底 ─────────────────────────────────────────────
// 可选来源（与后端 MediaSource 对齐）；顺序可调，识别时按顺序回退。
const fallbackSourceOptions = FALLBACK_SOURCE_OPTIONS
const usedFallbackSources = computed(() => settingsDraft.value.fallback_sources || [])
const unusedFallbackSources = computed(() =>
  FALLBACK_SOURCE_OPTIONS.filter(opt => !usedFallbackSources.value.includes(opt.value)),
)

function fallbackSourceLabel(value) {
  const found = FALLBACK_SOURCE_OPTIONS.find(opt => opt.value === value)
  return found ? found.title : String(value || '')
}

function moveFallbackSource(index, delta) {
  const list = [...(settingsDraft.value.fallback_sources || [])]
  const target = index + delta
  if (target < 0 || target >= list.length) return
  const tmp = list[index]
  list[index] = list[target]
  list[target] = tmp
  settingsDraft.value.fallback_sources = list
}

function removeFallbackSource(value) {
  settingsDraft.value.fallback_sources = (settingsDraft.value.fallback_sources || []).filter(v => v !== value)
}

function addFallbackSource() {
  const value = String(fallbackSourceDraft.value || '').trim().toLowerCase()
  if (!value) return
  const list = [...(settingsDraft.value.fallback_sources || [])]
  if (!list.includes(value)) list.push(value)
  settingsDraft.value.fallback_sources = list
  fallbackSourceDraft.value = ''
}

async function loadFallback() {
  fallbackLoading.value = true
  try {
    fallbackState.value = unwrapResponse(await props.api.get(`${pluginBase.value}/fallback?resolve_paths=true`))
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    fallbackLoading.value = false
    if (fallbackState.value?.running) setTimeout(() => { loadFallback() }, 6000)
  }
}

async function runFallback(dryRun = false) {
  fallbackRunning.value = true
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/fallback/run?dry_run=${dryRun ? 'true' : 'false'}`),
    )
    notify(dryRun ? '演练扫描已开始（不会写 NFO）' : '元数据兜底已开始')
    setTimeout(() => { loadFallback() }, 3000)
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    fallbackRunning.value = false
  }
}

// 加载 IYUU 站点表（按 MoviePilot 已配置站点生成）。
async function loadIyuuSites() {
  iyuuLoading.value = true
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/iyuu/sites`))
    iyuuStatus.value = data || null
    const draftFill = normalizeIyuuSites(settingsDraft.value.iyuu_sites)
    iyuuSites.value = (data?.sites || []).map(row => {
      const domain = String(row.domain || '').toLowerCase()
      const serverFill = normalizeIyuuSites({ d: row.fill || {} }).d || {}
      const fill = draftFill[domain] || serverFill
      return {
        id: row.id,
        name: row.name || row.domain || '',
        domain: row.domain || '',
        iyuu_sid: row.iyuu_sid,
        is_active: row.is_active,
        has_apikey: row.has_apikey,
        has_cookie: row.has_cookie,
        passkey: fill.passkey || '',
        uid: fill.uid || '',
        downhash: fill.downhash || '',
      }
    })
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    iyuuLoading.value = false
  }
}

// 把站点密钥表写回 settingsDraft（保存前调用）。
function syncIyuuToDraft() {
  const map = {}
  iyuuSites.value.forEach(row => {
    const domain = String(row.domain || '').toLowerCase()
    if (!domain) return
    const clean = normalizeIyuuSites({ d: { passkey: row.passkey, uid: row.uid, downhash: row.downhash } }).d
    if (clean) map[domain] = clean
  })
  settingsDraft.value.iyuu_sites = map
}

// 测试 IYUU Token。
async function testIyuu() {
  iyuuTesting.value = true
  try {
    syncIyuuToDraft()
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/iyuu/test`))
    notify(`IYUU Token 有效（账号 ${data?.username || data?.id || '-'}，站点表 ${data?.sites ?? 0} 条）`)
  } catch (err) {
    notify(err?.message || String(err))
  } finally {
    iyuuTesting.value = false
  }
}

// 保存 IYUU 设置（Token + 站点密钥表）。
async function saveIyuu() {
  saving.value = true
  try {
    syncIyuuToDraft()
    unwrapResponse(await props.api.post(`${pluginBase.value}/settings`, normalizeSettings(settingsDraft.value)))
    notify('IYUU 设置已保存')
    await loadStatus()
    await loadIyuuSites()
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 加载下载器全局参数。
async function loadDownloaderPrefs() {
  downloaderPrefsLoading.value = true
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/downloader/prefs`))
    if (data && data.available) {
      downloaderPrefsDraft.value = normalizeDownloaderPrefs(data)
      downloaderPathsDraft.value = normalizeDownloaderPaths(data)
      downloaderPrefsRecommended.value = data.recommended || null
      downloaderPrefsRaw.value = data.raw || null
    }
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    downloaderPrefsLoading.value = false
  }
}

// 把下载器参数恢复为推荐值（仅填表，点保存才写入）。
function applyRecommendedPrefs() {
  if (downloaderPrefsRecommended.value) {
    downloaderPrefsDraft.value = normalizeDownloaderPrefs(downloaderPrefsRecommended.value)
    notify('已填入推荐值，点「保存」后生效')
  }
}

// 保存下载器全局参数。
async function saveDownloaderPrefs() {
  saving.value = true
  try {
    const data = unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/prefs`, normalizeDownloaderPrefs(downloaderPrefsDraft.value)),
    )
    if (data && data.available) {
      downloaderPrefsDraft.value = normalizeDownloaderPrefs(data)
      downloaderPrefsRaw.value = data.raw || null
    }
    notify('下载器参数已保存')
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 保存下载目录。
async function saveDownloaderPaths() {
  saving.value = true
  try {
    const data = unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/paths`, normalizeDownloaderPaths(downloaderPathsDraft.value)),
    )
    if (data && data.available) {
      downloaderPathsDraft.value = normalizeDownloaderPaths(data)
      downloaderPrefsRaw.value = data.raw || null
    }
    notify('下载目录已保存')
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 加载默认任务模板。
async function loadDefaults() {
  defaultsLoading.value = true
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/defaults`))
    defaultsDraft.value = normalizeDefaults(data || {})
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    defaultsLoading.value = false
  }
}

// 保存默认任务模板。
async function saveDefaults() {
  saving.value = true
  try {
    unwrapResponse(await props.api.post(`${pluginBase.value}/defaults`, normalizeDefaults(defaultsDraft.value)))
    notify('默认任务模板已保存')
    await loadStatus()
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 保存当前设置标签页。
function saveActiveSettings() {
  const tab = settingsTab.value
  if (tab === 'downloader') return saveDownloaderPrefs()
  if (tab === 'paths') return savePathsTab()
  if (tab === 'template') return saveDefaults()
  if (tab === 'iyuu') return saveIyuu()
  if (tab === 'fallback') return saveSettings()
  if (tab === 'cloud') return saveCloud()
  return saveSettings()
}

// 保存「云盘归档」设置：保存后立刻回读配置 + 自检一次，避免「存了但没生效」。
async function saveCloud() {
  await saveSettings()
  await loadCloud()
  await testCloud()
}

// 保存「下载目录」标签：qBittorrent 全局路径 + 任务保存目录（默认模板）。
async function savePathsTab() {
  saving.value = true
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/paths`, normalizeDownloaderPaths(downloaderPathsDraft.value)),
    )
    unwrapResponse(await props.api.post(`${pluginBase.value}/defaults`, normalizeDefaults(defaultsDraft.value)))
    notify('下载目录已保存')
    await loadStatus()
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
}

// 保存全局设置。
async function saveSettings() {
  saving.value = true
  try {
    unwrapResponse(await props.api.post(`${pluginBase.value}/settings`, normalizeSettings(settingsDraft.value)))
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
    else if (bonusLoadedFor.value === selectedTaskId.value) loadBonus(selectedTaskId.value, { silent: true })
    else loadBonus(selectedTaskId.value)
  }
  if (tab === 'diagnostics' && selectedTaskId.value) {
    loadOperations(selectedTaskId.value)
    loadDetail(selectedTaskId.value)
  }
})

watch(poolView, view => {
  if (!selectedTaskId.value) return
  if (view === 'candidates') {
    loadCandidates(selectedTaskId.value)
  } else if (bonusLoadedFor.value === selectedTaskId.value) {
    // 已有托管数据：立即展示，后台静默刷新
    loadBonus(selectedTaskId.value, { silent: true })
  } else {
    loadBonus(selectedTaskId.value)
  }
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
    loadLive()
  },
  { immediate: true },
)

onMounted(() => {
  loadStatus()
  loadRecommend()
  refreshTimer = window.setInterval(loadStatus, 30000)
  // 推荐列表是全局的，低频刷新一下角标计数
  recommendTimer = window.setInterval(loadRecommend, 60000)
  // 站点实时数据：采样周期 240s，这里 120s 轮询（服务端有缓存，不会重复打站点）
  loadLive()
  liveTimer = window.setInterval(loadLive, 120000)
  // 运行诊断页每秒多刷新一次任务阶段，驱动流程链转圈
  phaseTimer = window.setInterval(() => {
    if (activeTab.value === 'diagnostics' && selectedTaskId.value) loadDetail(selectedTaskId.value)
  }, 1500)
})

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (phaseTimer) window.clearInterval(phaseTimer)
  if (recommendTimer) window.clearInterval(recommendTimer)
  if (liveTimer) window.clearInterval(liveTimer)
  if (warmingTimer) window.clearTimeout(warmingTimer)
  if (cloudPollTimer) window.clearInterval(cloudPollTimer)
})
</script>

<template>
  <div class="magicflow-page" :class="{ 'magicflow-page--compact': compact || status.compact_mode }">
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
              :subtitle="task.site_name"
              :active="task.id === selectedTaskId"
              @click="selectTask(task.id)"
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
        <VBtn class="magicflow-header-create" color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreateTask">
          新建任务
        </VBtn>
        <VBadge
          v-if="recommendData.enabled !== false && (recommendData.recommended || 0) > 0"
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
            @click="openRecommend"
          />
        </VBadge>
        <VBtn
          v-else
          class="magicflow-recommend-btn"
          icon="mdi-movie-star-outline"
          variant="text"
          aria-label="推荐"
          @click="openRecommend"
        />
        <VBtn
          class="magicflow-cloud-btn"
          icon="mdi-cloud-upload-outline"
          variant="text"
          aria-label="云盘归档"
          @click="openCloud"
        />
        <VBtn
          class="magicflow-settings-btn"
          icon="mdi-tune-variant"
          variant="text"
          aria-label="插件设置"
          @click="openSettings()"
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
          <VList density="comfortable" class="magicflow-more-menu" min-width="210">
            <VListItem
              v-if="recommendData.enabled !== false"
              prepend-icon="mdi-movie-star-outline"
              title="推荐"
              :subtitle="(recommendData.recommended || 0) > 0 ? `${recommendData.recommended} 个待确认` : '影视推荐甄别'"
              @click="openRecommend"
            />
            <VListItem prepend-icon="mdi-cloud-upload-outline" title="云盘归档" @click="openCloud" />
            <VListItem prepend-icon="mdi-tune-variant" title="插件设置" @click="openSettings()" />
            <VListItem v-if="showClose" prepend-icon="mdi-close" title="关闭" @click="emit('close')" />
          </VList>
        </VMenu>
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
      <div class="text-h6">还没有任务</div>
      <div class="text-body-2 text-medium-emphasis">创建任务后可按站点魔力公式养护做种，或按上传产出刷流保种</div>
      <VBtn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreateTask">创建第一个任务</VBtn>
    </div>

    <template v-else>
      <div class="magicflow-mobile-toolbar">
        <VMenu v-if="tasks.length > 1" :close-on-content-click="true" location="bottom start">
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
              :subtitle="task.site_name"
              :active="task.id === selectedTaskId"
              @click="selectTask(task.id)"
            >
              <template #prepend>
                <VIcon :icon="taskBadge(task).icon" :color="taskBadge(task).color" size="18" />
              </template>
            </VListItem>
          </VList>
        </VMenu>
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
            <span class="text-subtitle-2">任务</span>
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
                <span class="magicflow-status-dot" :class="`magicflow-status-dot--${taskBadge(task).color}`" />
              </span>
              <span>{{ task.site_name }} · {{ task.downloader }}</span>
              <span class="magicflow-task-item__meta">
                <span>{{ task.seeding_count || 0 }} 个种子</span>
                <span v-if="task.task_type === 'brush'">{{ formatBytes(task.task_uploaded || 0) }} 上传</span>
                <span v-else>{{ task.site_bonus_ok ? formatBonus(task.site_bonus_per_hour) : '—' }}</span>
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
                  <VChip size="small" variant="tonal" :color="selectedTask.task_type === 'brush' ? 'info' : 'primary'" :prepend-icon="selectedTask.task_type === 'brush' ? 'mdi-upload-network-outline' : 'mdi-star-four-points-outline'">
                    {{ selectedTask.task_type === 'brush' ? '刷流' : '刷魔力' }}
                  </VChip>
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
              <VMenu location="bottom end">
                <template #activator="{ props: menuProps }">
                  <VBtn
                    v-bind="menuProps"
                    :icon="selectedRunMode.icon"
                    :color="selectedRunMode.color"
                    variant="text"
                  />
                </template>
                <VList density="compact" min-width="248">
                  <VListItem
                    v-for="mode in RUN_MODES"
                    :key="mode.value"
                    :prepend-icon="mode.icon"
                    :title="mode.text"
                    :subtitle="mode.hint"
                    :active="(selectedTask.run_mode || 'running') === mode.value"
                    @click="setRunMode(mode.value)"
                  />
                </VList>
              </VMenu>
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
                <template v-if="taskIsBrush">
                  <VSheet class="magicflow-stat app-surface-static">
                    <strong>{{ formatBytes(selectedTask.task_uploaded || 0) }}</strong>
                    <span>本任务上传量 · 下载器累计（{{ selectedTask.task_upload_active || 0 }} 个有上传）</span>
                  </VSheet>
                  <VSheet class="magicflow-stat app-surface-static">
                    <strong>{{ siteAccount.ok ? formatBytes(siteAccount.upload || 0) : '—' }}</strong>
                    <span>站点上传量 · {{ siteAccount.source === 'live' ? '实时（直连站点）' : 'MP 快照' }}{{ siteAccount.ok ? ` · 下载 ${formatBytes(siteAccount.download || 0)}` : '' }}</span>
                  </VSheet>
                </template>
                <template v-else>
                  <VSheet class="magicflow-stat app-surface-static">
                    <strong>{{ selectedTask.site_bonus_ok ? formatBonus(selectedTask.site_bonus_per_hour) : '—' }}</strong>
                    <span>站点上报时魔 · 站点实时值</span>
                  </VSheet>
                  <VSheet class="magicflow-stat app-surface-static">
                    <strong>{{ Number(selectedTask.site_current_bonus || 0).toFixed(2) }}</strong>
                    <span>站点当前魔力 · 该站点实时存量</span>
                  </VSheet>
                </template>
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
                    <div><dt>任务目标</dt><dd>{{ goalFactText }}</dd></div>
                    <div><dt>选种周期</dt><dd>{{ taskConfig.cron_expression || `每 ${taskConfig.brush_interval} 分钟` }}</dd></div>
                    <div><dt>检查周期</dt><dd>每 {{ taskConfig.check_interval }} 分钟</dd></div>
                    <div><dt>开启时段</dt><dd>{{ taskConfig.active_time_range || '全天' }}</dd></div>
                    <template v-if="taskIsBrush">
                      <div><dt>保种天数</dt><dd>{{ brushSeedDays > 0 ? `做种满 ${brushSeedDays} 天清理` : '不按天数（按无上传）' }}</dd></div>
                      <div><dt>最小下载人数</dt><dd>{{ taskConfig.brush_min_leechers ?? 1 }} 人</dd></div>
                    </template>
                    <template v-else>
                      <div><dt>最低魔力</dt><dd>{{ taskConfig.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.min_bonus_per_hour).toFixed(2)} /h` }}</dd></div>
                      <div><dt>最多保留</dt><dd>{{ taskConfig.max_keep_torrents == null ? (taskConfig.disk_size_gb ? `按 ${taskConfig.disk_size_gb}GB 自动` : '不限') : `${taskConfig.max_keep_torrents} 个` }}</dd></div>
                      <div><dt>保护阈值</dt><dd>{{ taskConfig.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.bonus_protect_threshold).toFixed(0) }}</dd></div>
                      <div><dt>完美种保护</dt><dd>{{ taskConfig.protect_perfect === false ? '关闭' : `开启（≤${taskConfig.perfect_max_seeders ?? 3}人 · ≥${taskConfig.perfect_min_weeks ?? 4}周）` }}</dd></div>
                    </template>
                    <div><dt>自动补种</dt><dd>{{ taskConfig.refill_when_empty ? '开启' : '关闭' }}</dd></div>
                    <div><dt>存量复用</dt><dd>{{ taskConfig.reuse_existing ? '开启' : '关闭' }}</dd></div>
                    <div><dt>无进度清理</dt><dd>{{ taskConfig.cleanup_no_progress ? `开启（${taskConfig.no_progress_minutes ?? 30} 分钟）` : '关闭' }}</dd></div>
                    <div><dt>慢速清理</dt><dd>{{ taskConfig.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.slow_progress_max_hours ?? 48}h 下不完即清）` }}</dd></div>
                    <div><dt>促销失效清理</dt><dd>{{ taskConfig.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）' }}</dd></div>
                    <div><dt>自动恢复暂停</dt><dd>{{ taskConfig.auto_resume_paused === false ? '关闭' : '开启' }}</dd></div>
                    <div><dt>选种来源</dt><dd>{{ taskConfig.rss_support ? 'RSS' : '站点列表页' }}</dd></div>
                    <div><dt>促销要求</dt><dd>{{ taskIsBrush ? '免费（含 2X免费）' : (taskConfig.freeleech === '2xfree' ? '2X 免费' : taskConfig.freeleech === 'free' ? '免费' : '全部') }}</dd></div>
                  </dl>
                </VSheet>

                <VSheet tag="section" class="magicflow-panel app-surface-static">
                  <header class="magicflow-panel__head">
                    <div>
                      <div class="text-subtitle-1 font-weight-medium">站点数据</div>
                      <div class="text-body-2 text-medium-emphasis">
                        <template v-if="siteAccount.source === 'live'">魔流直连站点用户栏（实时）{{ siteAccount.sampledAt ? ` · 采样于 ${siteAccount.sampledAt}` : '' }}</template>
                        <template v-else-if="siteAccount.source === 'mp'">MoviePilot 站点数据快照（默认 6 小时一轮）{{ siteUser.updated_at ? ` · 更新于 ${siteUser.updated_at}` : '' }}</template>
                        <template v-else>暂无站点数据</template>
                      </div>
                    </div>
                    <VChip v-if="siteAccount.source === 'live'" size="small" variant="tonal" :color="siteLiveLevel === 'warn' ? 'warning' : 'success'">
                      {{ siteLiveLevel === 'warn' ? '实时 · 有告警' : '实时' }}
                    </VChip>
                    <VChip v-else-if="siteAccount.source === 'mp'" size="small" variant="tonal">MP 快照</VChip>
                    <VChip v-else size="small" variant="tonal">暂无数据</VChip>
                  </header>
                  <dl class="magicflow-facts">
                    <div><dt>上传量</dt><dd>{{ siteAccount.ok ? formatBytes(siteAccount.upload || 0) : '—' }}</dd></div>
                    <div><dt>下载量</dt><dd>{{ siteAccount.ok ? formatBytes(siteAccount.download || 0) : '—' }}</dd></div>
                    <div><dt>分享率</dt><dd>{{ siteAccount.ok && siteAccount.ratio != null ? Number(siteAccount.ratio).toFixed(3) : '—' }}</dd></div>
                    <div><dt>做种数 / 下载数</dt><dd>{{ siteAccount.ok ? `${siteAccount.seeding ?? '—'} / ${siteAccount.leeching ?? '—'}` : '—' }}</dd></div>
                    <div v-if="siteAccount.seeding_size"><dt>做种体积</dt><dd>{{ formatBytes(siteAccount.seeding_size) }}</dd></div>
                    <div><dt>站点魔力</dt><dd>{{ siteAccount.ok && siteAccount.bonus != null ? Number(siteAccount.bonus).toFixed(2) : '—' }}{{ siteAccount.bonus_per_hour != null ? ` · ${Number(siteAccount.bonus_per_hour).toFixed(2)}/h` : '' }}</dd></div>
                    <template v-if="siteAccount.source === 'live'">
                      <div><dt>上传速率</dt><dd>{{ siteLiveRates.ok ? `${Number(siteLiveRates.up_mb_min || 0).toFixed(1)} MB/分` : '采样中' }}</dd></div>
                      <div><dt>下载速率</dt><dd :class="{ 'text-error': (siteLiveRates.down_mb_min || 0) >= (siteLiveCfg.download_alert_mb || 50) }">{{ siteLiveRates.ok ? `${Number(siteLiveRates.down_mb_min || 0).toFixed(1)} MB/分` : '采样中' }}</dd></div>
                      <div><dt>近 1h 净增</dt><dd>{{ siteLiveRates.ok ? `⬆ ${formatBytes(Math.max(0, siteLiveRates.d_up || 0))} / ⬇ ${formatBytes(Math.max(0, siteLiveRates.d_down || 0))}` : '—' }}</dd></div>
                    </template>
                  </dl>
                  <div v-if="siteLiveAlerts.length" class="magicflow-live-alerts">
                    <div v-for="(alert, idx) in siteLiveAlerts" :key="`${alert.kind}-${idx}`" class="magicflow-live-alert" :class="`magicflow-live-alert--${alert.level || 'info'}`">
                      {{ alert.text }}
                    </div>
                  </div>
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
                    <div><span>慢扫辅种（累计 / 本次）</span><strong>{{ detailStats.cumulative_slow_reused || 0 }} / {{ detailStats.last_slow_reused || 0 }}</strong></div>
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
                      {{ detailStats.run_active ? (taskIsBrush ? '正在执行本轮刷流…' : '正在执行本轮养护…') : (detailStats.last_run_at ? `最近执行 ${formatDateTime(detailStats.last_run_at)}` : '尚未运行') }}
                      · 翻页游标 {{ detailStats.page_cursor ?? 0 }}<template v-if="detailStats.last_phase_detail"> · {{ detailStats.last_phase_detail }}</template>
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
                    <div class="text-body-2 text-medium-emphasis">每次执行 / 选种 / 删种 / 保护 / 标签 的流水（可展开明细）</div>
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
                        <template v-if="hasOpDetail(record)"> · {{ opDetailItems(record).length }} 条明细</template>
                      </span>
                      <span v-if="record.error_message" class="text-error">{{ record.error_message }}</span>
                      <button
                        v-if="hasOpDetail(record)"
                        type="button"
                        class="magicflow-events__toggle"
                        @click="toggleOpDetail(record.operation_id)"
                      >
                        {{ isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细' }}
                        <VIcon :icon="isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="14" />
                      </button>
                      <ul v-if="isOpDetailOpen(record.operation_id)" class="magicflow-events__detail">
                        <li v-for="(it, idx) in opDetailItems(record)" :key="idx">
                          <span class="magicflow-events__detail-line">
                            <em v-if="itemSourceText(it.source)" class="magicflow-events__detail-src">{{ itemSourceText(it.source) }}</em>
                            <span class="magicflow-events__detail-title" :title="it.title || it.hash">{{ it.title || it.hash || '—' }}</span>
                          </span>
                          <span class="magicflow-events__detail-sub">
                            <template v-if="it.reason">{{ it.reason }}</template>
                            <template v-if="it.size_gb"> · {{ Number(it.size_gb).toFixed(2) }}G</template>
                            <template v-if="it.seeders"> · 做种 {{ it.seeders }}</template>
                          </span>
                        </li>
                      </ul>
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
                      已托管：共 {{ bonusData.torrent_count || 0 }} 个
                    </template>
                  </div>
                </div>
                <div class="magicflow-torrent-filters">
                  <VBtnToggle :model-value="poolView" mandatory color="primary" density="compact" @update:model-value="value => (poolView = value)">
                    <VBtn value="candidates" prepend-icon="mdi-filter-variant">候选</VBtn>
                    <VBtn value="torrents" prepend-icon="mdi-seed-outline">托管（{{ bonusData.torrent_count || 0 }}）</VBtn>
                  </VBtnToggle>
                  <VBtn
                    v-if="poolView === 'torrents'"
                    size="small"
                    variant="tonal"
                    color="primary"
                    prepend-icon="mdi-link-variant-plus"
                    :loading="backfilling"
                    @click="backfillPages"
                  >回填链接</VBtn>
                </div>
              </div>

              <template v-if="poolView === 'candidates'">
                <VSheet tag="section" class="magicflow-panel app-surface-static">
                  <header class="magicflow-panel__head">
                    <div>
                      <div class="text-subtitle-1 font-weight-medium">候选排行</div>
                      <div class="text-body-2 text-medium-emphasis">{{ taskIsBrush ? '按上传潜力（下载人数）排序 · 仅供选种参考' : '待办名次由站点魔力效率内部排序 · 仅供选种参考' }}</div>
                    </div>
                  </header>
                  <ol class="magicflow-pipeline">
                    <li v-for="candidate in (candidateData.candidates || []).slice(0, 8)" :key="candidate.hash">
                      <span class="magicflow-pipeline__index">{{ candidate.rank }}</span>
                      <div>
                        <strong>{{ candidate.title || '未知种子' }}</strong>
                        <span>{{ Number(candidate.size_gb || 0).toFixed(2) }} GB · {{ candidate.seeders }} 做种 · {{ candidate.leechers }} 下载 · {{ Number(candidate.age_weeks || 0).toFixed(1) }} 周</span>
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
                  <div class="text-body-2 text-medium-emphasis">
                    点击任意行查看详情 / 手动保留 / 删除
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

                <div v-if="selectedHashes.length" class="magicflow-bulk-bar">
                  <span class="magicflow-bulk-bar__count">已选 {{ selectedHashes.length }} 个</span>
                  <VBtn size="small" variant="tonal" :disabled="batchBusy" @click="batchAction('protect')">保留</VBtn>
                  <VBtn size="small" variant="tonal" :disabled="batchBusy" @click="batchAction('unprotect')">取消保留</VBtn>
                  <VBtn size="small" variant="tonal" :disabled="batchBusy" @click="batchAction('pause')">暂停</VBtn>
                  <VBtn size="small" variant="tonal" :disabled="batchBusy" @click="batchAction('resume')">恢复</VBtn>
                  <VBtn size="small" variant="tonal" :disabled="batchBusy" @click="batchAction('recheck')">校验</VBtn>
                  <VBtn size="small" variant="tonal" color="error" :disabled="batchBusy" @click="batchDeleteDialog = true">删除</VBtn>
                  <VSpacer />
                  <VBtn size="small" variant="text" :disabled="batchBusy" @click="selectAllFiltered">全选筛选（{{ sortedTorrents.length }}）</VBtn>
                  <VBtn size="small" variant="text" :disabled="batchBusy" @click="clearSelection">取消选择</VBtn>
                </div>

                <VDataTable
                  class="magicflow-torrent-table torrent-table-clickable"
                  :headers="torrentHeaders"
                  :items="sortedTorrents"
                  :loading="taskLoading"
                  :items-per-page="10"
                  density="comfortable"
                  @click:row="onTorrentRowClick"
                >
                  <template #header.select>
                    <VCheckbox
                      :model-value="allFilteredSelected"
                      :indeterminate="selectedHashes.length > 0 && !allFilteredSelected"
                      density="compact"
                      hide-details
                      aria-label="全选"
                      @update:model-value="value => (value ? selectAllFiltered() : clearSelection())"
                    />
                  </template>
                  <template #item.select="{ item }">
                    <VCheckbox
                      :model-value="selectedHashes.includes(item.hash)"
                      density="compact"
                      hide-details
                      :aria-label="`选择 ${item.title || ''}`"
                      @click.stop
                      @update:model-value="toggleTorrentSelection(item)"
                    />
                  </template>
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
                      @click="requestTorrentDelete(item)"
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
                          @click="torrentAction(item, 'resume')"
                        />
                        <VListItem
                          v-else
                          prepend-icon="mdi-pause-circle-outline"
                          :title="torrentPauseLabel(item)"
                          subtitle="不会被自动恢复"
                          @click="torrentAction(item, 'pause')"
                        />
                        <VListItem prepend-icon="mdi-sync" title="强制校验" @click="torrentAction(item, 'recheck')" />
                        <VDivider class="my-1" />
                        <VListItem prepend-icon="mdi-delete-outline" title="删除种子" base-color="error" @click="requestTorrentDelete(item)" />
                      </VList>
                    </VMenu>
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
                      <VCheckbox
                        :model-value="selectedHashes.includes(item.hash)"
                        density="compact"
                        hide-details
                        class="magicflow-mobile-torrent__check"
                        @click.stop
                        @update:model-value="toggleTorrentSelection(item)"
                      />
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
                      <VBtn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click.stop="requestTorrentDelete(item)">删除</VBtn>
                      <VBtn
                        v-if="torrentIsPaused(item)"
                        size="small"
                        variant="tonal"
                        prepend-icon="mdi-play-circle-outline"
                        @click.stop="torrentAction(item, 'resume')"
                      >{{ torrentProgressPct(item) >= 100 ? '恢复' : '继续' }}</VBtn>
                      <VBtn v-else size="small" variant="tonal" prepend-icon="mdi-pause-circle-outline" @click.stop="torrentAction(item, 'pause')">暂停</VBtn>
                      <VBtn size="small" variant="tonal" prepend-icon="mdi-sync" @click.stop="torrentAction(item, 'recheck')">校验</VBtn>
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
                      <div class="text-subtitle-1 font-weight-medium">{{ taskIsBrush ? '刷流规则' : '魔力规则' }}</div>
                      <div class="text-body-2 text-medium-emphasis">{{ taskIsBrush ? '刷流标准：免费 + 有下载者；做种满天数清理' : '当前服务端生效的魔力养护配置' }}</div>
                    </div>
                  </header>
                  <dl class="magicflow-facts magicflow-facts--two">
                    <div><dt>任务状态</dt><dd>{{ selectedRunMode.text }}</dd></div>
                    <div><dt>任务目标</dt><dd>{{ goalFactText }}</dd></div>
                    <div><dt>站点</dt><dd>{{ selectedTask.site_name }}</dd></div>
                    <div><dt>下载器</dt><dd>{{ selectedTask.downloader }}</dd></div>
                    <div><dt>下载器标签</dt><dd>{{ selectedTask.brush_tag || '未设置' }}</dd></div>
                    <div><dt>促销要求</dt><dd>{{ taskIsBrush ? '免费（含 2X免费）' : (taskConfig.freeleech === '2xfree' ? '2X 免费' : taskConfig.freeleech === 'free' ? '免费' : '全部') }}</dd></div>
                    <div><dt>选种来源</dt><dd>{{ taskConfig.rss_support ? 'RSS' : '站点列表页' }}</dd></div>
                    <template v-if="taskIsBrush">
                      <div><dt>保种天数</dt><dd>{{ brushSeedDays > 0 ? `做种满 ${brushSeedDays} 天清理` : '不按天数（按无上传）' }}</dd></div>
                      <div><dt>最小下载人数</dt><dd>{{ taskConfig.brush_min_leechers ?? 1 }} 人</dd></div>
                      <div><dt>种子大小</dt><dd>{{ taskConfig.size || '不限' }}</dd></div>
                      <div><dt>做种人数</dt><dd>{{ taskConfig.seeder || '不限' }}</dd></div>
                      <div><dt>发布时间</dt><dd>{{ taskConfig.pubtime ? `${taskConfig.pubtime} 分钟` : '不限' }}</dd></div>
                      <div><dt>排除 H&R</dt><dd>{{ taskConfig.hr === 'yes' ? '是' : '否' }}</dd></div>
                      <div><dt>包含规则</dt><dd>{{ taskConfig.include || '无' }}</dd></div>
                      <div><dt>排除规则</dt><dd>{{ taskConfig.exclude || '无' }}</dd></div>
                    </template>
                    <template v-else>
                      <div><dt>保种体积</dt><dd>{{ taskConfig.disk_size_gb ? `${taskConfig.disk_size_gb} GB` : '不限' }}</dd></div>
                      <div><dt>最低魔力</dt><dd>{{ taskConfig.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.min_bonus_per_hour).toFixed(2)} /h` }}</dd></div>
                      <div><dt>最多保留</dt><dd>{{ taskConfig.max_keep_torrents == null ? '自动 / 不限' : `${taskConfig.max_keep_torrents} 个` }}</dd></div>
                      <div><dt>保护阈值</dt><dd>{{ taskConfig.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.bonus_protect_threshold).toFixed(0) }}</dd></div>
                      <div><dt>完美种保护</dt><dd>{{ taskConfig.protect_perfect === false ? '关闭' : `开启（≤${taskConfig.perfect_max_seeders ?? 3}人 · ≥${taskConfig.perfect_min_weeks ?? 4}周）` }}</dd></div>
                      <div><dt>公式 T0/N0</dt><dd>{{ taskConfig.bonus_t0 ?? '默认' }} / {{ taskConfig.bonus_n0 ?? '默认' }}</dd></div>
                      <div><dt>公式 B0/L</dt><dd>{{ taskConfig.bonus_b0 ?? '默认' }} / {{ taskConfig.bonus_l ?? '默认' }}</dd></div>
                      <div><dt>零魔权重</dt><dd>{{ taskConfig.bonus_zero_weight ?? '默认' }}</dd></div>
                      <div><dt>保底魔力</dt><dd>{{ Number(taskConfig.min_bonus_to_keep || 0).toFixed(2) }}</dd></div>
                      <div><dt>种子大小</dt><dd>{{ taskConfig.size || '不限' }}</dd></div>
                      <div><dt>做种人数</dt><dd>{{ taskConfig.seeder || '不限' }}</dd></div>
                      <div><dt>发布时间</dt><dd>{{ taskConfig.pubtime ? `${taskConfig.pubtime} 分钟` : '不限' }}</dd></div>
                      <div><dt>排除 H&R</dt><dd>{{ taskConfig.hr === 'yes' ? '是' : '否' }}</dd></div>
                      <div><dt>包含规则</dt><dd>{{ taskConfig.include || '无' }}</dd></div>
                      <div><dt>排除规则</dt><dd>{{ taskConfig.exclude || '无' }}</dd></div>
                      <div><dt>最短做种</dt><dd>{{ taskConfig.min_seed_time ? `${taskConfig.min_seed_time} 小时` : '不限' }}</dd></div>
                      <div><dt>最低分享率</dt><dd>{{ Number(taskConfig.min_ratio || 0).toFixed(2) }}</dd></div>
                    </template>
                    <div><dt>单轮最多新增</dt><dd>{{ taskConfig.max_add_per_run ?? 10 }} 个</dd></div>
                    <div><dt>同时下载上限</dt><dd>{{ taskConfig.max_download_concurrent ?? 10 }} 个</dd></div>
                    <div><dt>每轮参评候选</dt><dd>{{ taskConfig.top_n ?? 30 }} 个</dd></div>
                    <div><dt>每轮翻页数</dt><dd>{{ taskConfig.browse_pages ?? 3 }} 页</dd></div>
                    <div><dt>自动补种</dt><dd>{{ taskConfig.refill_when_empty ? '开启' : '关闭' }}</dd></div>
                    <div><dt>存量复用</dt><dd>{{ taskConfig.reuse_existing ? (taskConfig.reuse_verify ? '开启（校验）' : '开启（跳过校验）') : '关闭' }}</dd></div>
                    <div><dt>无进度清理</dt><dd>{{ taskConfig.cleanup_no_progress ? `开启（${taskConfig.no_progress_minutes ?? 30} 分钟）` : '关闭' }}</dd></div>
                    <div><dt>慢速清理</dt><dd>{{ taskConfig.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.slow_progress_max_hours ?? 48}h 下不完即清）` }}</dd></div>
                    <div><dt>促销失效清理</dt><dd>{{ taskConfig.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）' }}</dd></div>
                    <div><dt>自动恢复暂停</dt><dd>{{ taskConfig.auto_resume_paused === false ? '关闭' : '开启' }}</dd></div>
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
                      <span>{{ taskIsBrush ? '立即按刷流标准抓取免费热种并保持上传' : '立即按当前策略抓取候选并养护做种' }}</span>
                      <VBtn color="primary" variant="tonal" prepend-icon="mdi-sync" :loading="saving" @click="runOperation">
                        立即执行
                      </VBtn>
                    </div>
                    <VDivider />
                    <div>
                      <strong>编辑任务</strong>
                      <span>{{ taskIsBrush ? '调整调度、刷流门槛与清理策略' : '调整调度、魔力门槛与公式参数' }}</span>
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
      :default-save-path="defaultSavePath"
      :saving="saving"
      @save="saveTask"
    />

    <VDialog v-model="settingsDialog" max-width="40rem">
      <VCard class="magicflow-dialog magicflow-settings-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">插件设置</span>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="settingsDialog = false" />
        </header>

        <VTabs v-model="settingsTab" class="magicflow-settings-dialog__tabs" density="comfortable" show-arrows>
          <VTab value="general" class="magicflow-settings-tab">常规</VTab>
          <VTab value="downloader" class="magicflow-settings-tab">下载器参数</VTab>
          <VTab value="paths" class="magicflow-settings-tab">下载目录</VTab>
          <VTab value="template" class="magicflow-settings-tab">默认任务模板</VTab>
          <VTab value="iyuu" class="magicflow-settings-tab">IYUU 辅种</VTab>
          <VTab value="fallback" class="magicflow-settings-tab">元数据兜底</VTab>
          <VTab value="cloud" class="magicflow-settings-tab">云盘归档</VTab>
          <VTab value="live" class="magicflow-settings-tab">站点监控</VTab>
          <VTab value="recommend" class="magicflow-settings-tab">推荐</VTab>
        </VTabs>
        <VDivider />

        <div class="magicflow-settings-dialog__body">
          <div v-if="settingsTab === 'general'" class="magicflow-settings-form">
            <VSwitch v-model="settingsDraft.enabled" label="启用插件" color="primary" hide-details inset />
            <VSwitch
              v-model="settingsDraft.show_sidebar_nav"
              label="显示侧栏入口"
              color="primary"
              hide-details
              inset
            />
            <VTextField
              v-model.number="settingsDraft.request_interval"
              type="number"
              min="0"
              step="0.5"
              label="站点请求间隔（秒）"
              hint="站点翻页请求之间的最小间隔，0 = 不限速；对强流控站点可适当加大"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />
            <VTextField
              v-model.number="settingsDraft.journal_keep"
              type="number"
              min="0"
              label="操作记录保留上限"
              hint="每个任务最多保留的操作记录条数，0 = 不限"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />
            <p class="magicflow-settings-hint">
              任务流量：按「在跑的任务类型」自动设 qB <strong>全局上传限速</strong>（只限上传，不动下载）。有刷流任务时用刷流档，只有魔力任务时用魔力档；两者同时在跑取刷流档；一个启用的任务都没有则清除限速。
            </p>
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.bonus_upload_limit_kbps"
                type="number"
                min="0"
                step="10"
                label="魔力任务上传限速（KB/s）"
                hint="仅有魔力任务在跑时生效，0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.brush_upload_limit_kbps"
                type="number"
                min="0"
                step="10"
                label="刷流任务上传限速（KB/s）"
                hint="有刷流任务在跑时生效（优先），0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <VSwitch v-model="settingsDraft.debug_log" label="调试日志" color="primary" hide-details inset />
            <VSwitch v-model="settingsDraft.compact_mode" label="紧凑模式" color="primary" hide-details inset />
          </div>

          <div v-else-if="settingsTab === 'downloader'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint magicflow-settings-hint--warn">
              以下为 qBittorrent 全局参数，将直接写入下载器，会影响所有使用该下载器的插件。
            </p>
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="downloaderPrefsDraft.download_limit_kbps"
                type="number"
                min="0"
                label="最大下载速度"
                suffix="KB/s"
                hint="0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.upload_limit_kbps"
                type="number"
                min="0"
                label="最大上传速度"
                suffix="KB/s"
                hint="0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_connec"
                type="number"
                min="0"
                label="最大连接数"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_connec_per_torrent"
                type="number"
                min="0"
                label="每种子连接数"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_uploads"
                type="number"
                min="-1"
                label="最大上传连接数"
                hint="-1 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_uploads_per_torrent"
                type="number"
                min="-1"
                label="每种子上传连接数"
                hint="-1 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_active_downloads"
                type="number"
                min="-1"
                label="最大活动下载数"
                hint="排队不计入；-1 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_active_torrents"
                type="number"
                min="-1"
                label="最大活动种子数"
                hint="-1 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <VSwitch
              v-model="downloaderPrefsDraft.queueing_enabled"
              label="启用队列限制（活动数上限生效的前提）"
              color="primary"
              hide-details
              inset
            />
          </div>

          <div v-else-if="settingsTab === 'paths'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              qBittorrent 全局目录，写入后影响所有使用该下载器的插件。
            </p>
            <VTextField
              v-model="downloaderPathsDraft.save_path"
              label="默认保存路径"
              placeholder="如 /vol3/1000/media"
              variant="outlined"
              density="comfortable"
              hide-details
            />
            <VTextField
              v-model="downloaderPathsDraft.temp_path"
              label="临时下载路径"
              placeholder="下载中暂存目录"
              variant="outlined"
              density="comfortable"
              hide-details
            />
            <VSwitch
              v-model="downloaderPathsDraft.temp_path_enabled"
              label="启用临时下载路径（下载中放临时目录，完成后移入保存路径）"
              color="primary"
              hide-details
              inset
            />

            <VDivider class="my-2" />
            <div class="text-subtitle-2 font-weight-medium">任务保存目录</div>
            <p class="magicflow-settings-hint">
              仅对魔流生效，不影响下载器全局设置。
            </p>
            <VTextField
              v-model="defaultsDraft.save_path"
              label="任务保存目录"
              placeholder="如 /vol3/1000/media/magicflow"
              hint="新建任务时自动预填此目录（不影响已有任务，任务内仍可单独修改）"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />
          </div>

          <div v-else-if="settingsTab === 'iyuu'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              IYUU 云端辅种为<strong>可选增强</strong>：填写 Token 后，复用/刷流会优先用 IYUU 云端匹配<strong>他站同资源</strong>；
              下方站点密钥可手填（留空则自动尝试用 MoviePilot 已存的 apikey / cookie 取链）。
              <strong>不填 Token 则完全不启用</strong>，一切照旧走内置跨站特征码方案。
            </p>
            <div class="magicflow-iyuu-token">
              <VTextField
                v-model="settingsDraft.iyuu_token"
                label="IYUU 云端 Token"
                placeholder="留空 = 不启用 IYUU 辅种"
                variant="outlined"
                density="comfortable"
                hide-details
                autocomplete="off"
              />
              <VBtn
                variant="tonal"
                color="primary"
                size="small"
                prepend-icon="mdi-connection"
                :loading="iyuuTesting"
                :disabled="!settingsDraft.iyuu_token"
                @click="testIyuu"
              >测试</VBtn>
            </div>
            <div class="magicflow-iyuu-sites">
              <div class="magicflow-iyuu-sites__head">
                <span>站点密钥（按 MoviePilot 已配置站点生成）</span>
                <VChip
                  v-if="iyuuStatus"
                  size="x-small"
                  variant="tonal"
                  :color="iyuuStatus.enabled ? 'success' : 'grey'"
                >{{ iyuuStatus.enabled ? '已启用' : '未启用' }}</VChip>
              </div>
              <p v-if="iyuuLoading" class="magicflow-settings-hint">加载中…</p>
              <p v-else-if="!iyuuSites.length" class="magicflow-settings-hint">
                未检测到已配置站点（请先在 MoviePilot 中添加站点）。
              </p>
              <div v-for="row in iyuuSites" :key="row.domain || row.name" class="magicflow-iyuu-row">
                <div class="magicflow-iyuu-row__head">
                  <span class="magicflow-iyuu-row__name">{{ row.name }}</span>
                  <VChip v-if="row.iyuu_sid" size="x-small" variant="tonal">IYUU #{{ row.iyuu_sid }}</VChip>
                  <VChip v-if="row.has_apikey" size="x-small" variant="tonal" color="success">API</VChip>
                  <VChip v-if="row.has_cookie" size="x-small" variant="tonal" color="info">Cookie</VChip>
                  <VSpacer />
                  <VBtn
                    size="x-small"
                    variant="text"
                    :append-icon="iyuuShowMore[row.domain || row.name] ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                    @click="iyuuShowMore[row.domain || row.name] = !iyuuShowMore[row.domain || row.name]"
                  >{{ iyuuShowMore[row.domain || row.name] ? '收起' : '更多' }}</VBtn>
                </div>
                <div class="magicflow-iyuu-row__fields">
                  <VTextField
                    v-model="row.passkey"
                    label="passkey"
                    placeholder="留空 = 自动获取"
                    variant="outlined"
                    density="compact"
                    hide-details
                    autocomplete="off"
                  />
                  <VTextField
                    v-model="row.uid"
                    label="uid（可选）"
                    variant="outlined"
                    density="compact"
                    hide-details
                    autocomplete="off"
                  />
                </div>
                <VTextField
                  v-if="iyuuShowMore[row.domain || row.name]"
                  v-model="row.downhash"
                  label="downhash（可选）"
                  variant="outlined"
                  density="compact"
                  hide-details
                  autocomplete="off"
                />
              </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'template'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              仅用于新建任务时预填，不影响已有任务。
            </p>
            <div class="magicflow-settings-grid">
              <VSelect
                v-model="defaultsDraft.downloader"
                :items="status.options.downloaders"
                label="默认下载器"
                placeholder="不指定（新建任务时再选）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField v-model.number="defaultsDraft.brush_interval" type="number" min="1" label="选种周期（分钟）" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.check_interval" type="number" min="1" label="检查周期（分钟）" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.max_add_per_run" type="number" min="1" label="单轮最多新增" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.max_download_concurrent" type="number" min="1" label="同时下载数上限" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.top_n" type="number" min="1" label="候选 TopN" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.browse_pages" type="number" min="1" label="每轮翻页数" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.seen_cooldown_hours" type="number" min="0" label="候选去重冷却（小时）" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.brush_seed_days" type="number" min="0" max="365" label="刷流保种天数（0=按无上传）" variant="outlined" density="comfortable" hide-details />
            </div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="defaultsDraft.refill_when_empty" label="清理后自动补种" color="primary" hide-details inset />
              <VSwitch v-model="defaultsDraft.reuse_existing" label="复用本机已有资源（辅种）" color="primary" hide-details inset />
              <VSwitch v-model="defaultsDraft.reuse_verify" label="辅种前校验" color="primary" hide-details inset />
              <VSwitch v-model="defaultsDraft.cleanup_no_progress" label="清理无进度种子" color="primary" hide-details inset />
              <VSwitch v-model="defaultsDraft.cleanup_slow_progress" label="清理过慢种子" color="primary" hide-details inset />
              <VSwitch v-model="defaultsDraft.purge_unfree_incomplete" label="清理「已非免费」未下完种子" color="primary" hide-details inset />
              <VSwitch v-model="defaultsDraft.auto_resume_paused" label="自动恢复被暂停种子" color="primary" hide-details inset />
              <VSwitch v-model="defaultsDraft.delete_files" label="删种同时删除文件" color="primary" hide-details inset />
            </div>
          </div>

          <div v-else-if="settingsTab === 'live'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              MoviePilot 的站点账号数据靠它自己的「站点数据刷新」任务写库（默认 <strong>6 小时</strong>一轮），
              对展示够用，但魔流是拿它<strong>做决策</strong>的（任务目标达标 / 救号分享率 / 兑换提醒）—— 滞后 6 小时就是真偏差。
              启用后魔流<strong>直连站点用户栏页</strong>拿实时值（上传 / 下载 / 分享率 / 魔力 / 做种数），
              并监控<strong>「下载量在涨」</strong>——免费种不吃下载，下载量增长说明吃到促销尾巴了。
              站点级缓存 + 单飞，抓不到自动回退 MP 数据。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.live_enabled" label="启用站点实时数据 + 流量监控" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_notify" label="命中告警时推送通知" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_kill_unfree" label="★ 下载量异常增长 → 去站点「正在下载」列表，把非免费的种从下载器干掉" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_kill_delete_files" label="干掉时连文件一起删（只动「下载中」且名称+体积对得上的种）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_auto_stop" label="同时把该站「运行中」任务切「做种中」（停调度、不删种）" color="primary" hide-details inset />
            </div>
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.live_interval_minutes"
                type="number"
                min="1"
                label="采样周期（分钟）"
                hint="默认 4 分钟；太频繁站点吃不消"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.live_download_alert_mb"
                type="number"
                min="1"
                label="下载增长告警阈值（MB/分钟）"
                hint="超过则告警；默认 50"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.live_ratio_target"
                type="number"
                min="0"
                step="0.05"
                label="分享率目标线"
                hint="低于则告警并算缺口；0 = 不检查"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <div v-if="siteLiveAlerts.length" class="magicflow-live-alerts">
              <div class="magicflow-live-alerts__head">当前「{{ selectedTask?.name }}」站点告警</div>
              <div v-for="(alert, idx) in siteLiveAlerts" :key="`live-cfg-${idx}`" class="magicflow-live-alert" :class="`magicflow-live-alert--${alert.level || 'info'}`">
                {{ alert.text }}
              </div>
            </div>
          </div>
          <div v-else-if="settingsTab === 'recommend'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              刷流时顺带甄别「值得收藏 / 观看」的资源：命中的种子会打上推荐标签（受「媒体资产价值闸门」保护、不会被当临时种删掉）并通知你确认；错过确认窗口（过期 / 磁盘不足）则按临时种回收。
            </p>
            <VSwitch v-model="settingsDraft.recommend_enabled" label="启用推荐甄别" color="primary" hide-details inset />
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.recommend_min_rating"
                type="number"
                min="0"
                max="10"
                step="0.1"
                label="评分门槛（高于）"
                hint="豆瓣 / TMDB 评分高于该值才推荐，默认 7.5"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.recommend_expire_days"
                type="number"
                min="0"
                step="1"
                label="推荐过期天数"
                hint="超过该天数仍未确认则视为过期（0 = 不过期）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.recommend_temp_ttl_days"
                type="number"
                min="0"
                step="1"
                label="临时种 TTL（天）"
                hint="未入选推荐的普通刷流临时种，超过该天数回收"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.recommend_disk_min_free_gb"
                type="number"
                min="0"
                step="1"
                label="磁盘余量下限（GB）"
                hint="剩余空间低于该值时，推荐立即视为过期"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model="settingsDraft.recommend_tag"
                label="推荐标签"
                hint="推荐资源单独打的标签，默认「魔流-推荐」"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.recommend_require_chart" label="榜单 / 热映 / 订阅命中也算达标（与评分为「或」关系）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.recommend_auto_import" label="确认后自动整理入库" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.recommend_notify" label="发现推荐时通知" color="primary" hide-details inset />
            </div>
          </div>

          <div v-else-if="settingsTab === 'fallback'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              TMDB 对<strong>番剧特别篇/前传、国漫、B站特供</strong>常常「根本没有」，离了 TMDB 就没元数据可用。
              这里做<strong>多源识别回退</strong>（按顺序试各来源）→ 给库里缺 NFO 的集补一份<strong>最小 NFO</strong>，
              让播放器 / 飞牛影视能显示名称与集号。<strong>只写 NFO，不动媒体文件，已存在的好 NFO 不覆盖。</strong>
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.fallback_enabled" label="启用元数据兜底" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.fallback_after_import" label="每次整理入库后自动兜底" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.fallback_dry_run" label="演练模式（只报告不写 NFO）" color="primary" hide-details inset />
            </div>

            <div class="magicflow-settings-field">
              <div class="magicflow-settings-label">识别来源顺序（自上而下依次尝试）</div>
              <ol class="magicflow-fb-sources">
                <li v-for="(src, idx) in usedFallbackSources" :key="src" class="magicflow-fb-source">
                  <span class="magicflow-fb-source__idx">{{ idx + 1 }}</span>
                  <span class="magicflow-fb-source__name">{{ fallbackSourceLabel(src) }}</span>
                  <VBtn icon="mdi-arrow-up" size="x-small" variant="text" :disabled="idx === 0" aria-label="上移" @click="moveFallbackSource(idx, -1)" />
                  <VBtn icon="mdi-arrow-down" size="x-small" variant="text" :disabled="idx === usedFallbackSources.length - 1" aria-label="下移" @click="moveFallbackSource(idx, 1)" />
                  <VBtn icon="mdi-close" size="x-small" variant="text" aria-label="移除" @click="removeFallbackSource(src)" />
                </li>
              </ol>
              <div class="magicflow-fb-source-add">
                <VSelect
                  v-model="fallbackSourceDraft"
                  :items="unusedFallbackSources"
                  item-title="title"
                  item-value="value"
                  label="添加来源"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  clearable
                />
                <VBtn variant="tonal" color="primary" :disabled="!fallbackSourceDraft" @click="addFallbackSource">添加</VBtn>
              </div>
            </div>

            <VCombobox
              v-model="settingsDraft.fallback_paths"
              :items="fallbackState?.effective_paths || []"
              label="兜底扫描的库目录"
              hint="留空 = 自动取 MoviePilot 目录配置里的 library 路径（如 /movie）"
              persistent-hint
              variant="outlined"
              density="comfortable"
              multiple
              chips
              clearable
            />

            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.fallback_interval_minutes"
                type="number"
                label="扫描周期（分钟）"
                hint="定时扫库兜底，默认 30"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.fallback_scan_max"
                type="number"
                label="每轮最多处理剧集数"
                hint="其余下轮继续，避免一次卡爆，默认 30"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>

            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.fallback_sp_to_s00" label="特别篇归位：源中不存在的集改归 Season 0（S00EXX）" color="primary" hide-details inset />
            </div>

            <VDivider class="magicflow-fb-divider" />

            <div class="magicflow-fb-actions">
              <VBtn variant="tonal" color="primary" size="small" :loading="fallbackRunning" :disabled="fallbackRunning" @click="runFallback(true)">演练扫描</VBtn>
              <VBtn variant="flat" color="primary" size="small" :loading="fallbackRunning" :disabled="fallbackRunning" @click="runFallback(false)">立即执行</VBtn>
              <VBtn variant="text" size="small" :loading="fallbackLoading" @click="loadFallback">刷新结果</VBtn>
              <span v-if="fallbackState?.running" class="magicflow-fb-running">● 扫描中…</span>
            </div>

            <div v-if="fallbackState?.report" class="magicflow-fb-report">
              <div class="magicflow-fb-report__line">
                上次{{ fallbackState.report.applied === false ? '演练' : '执行' }}：
                扫描 {{ fallbackState.report.stats?.shows || 0 }} 剧<template v-if="fallbackState.report.stats?.total_shows">/共 {{ fallbackState.report.stats.total_shows }} 部</template> ·
                识别 {{ fallbackState.report.stats?.resolved || 0 }} ·
                补集 NFO {{ fallbackState.report.stats?.ep_nfo || 0 }} ·
                补剧 NFO {{ fallbackState.report.stats?.show_nfo || 0 }} ·
                源中缺失 {{ fallbackState.report.stats?.missing || 0 }} ·
                多源补齐 {{ fallbackState.report.stats?.via_extra || 0 }} 集 ·
                归位 {{ fallbackState.report.stats?.renumbered || 0 }} ·
                {{ fallbackState.report.duration }}s
              </div>
              <details v-if="fallbackProblemShows.length" class="magicflow-fb-report__details">
                <summary>源里查不到的集（{{ fallbackProblemCount }} 集，已按本地文件兜底）</summary>
                <ul class="magicflow-fb-report__list">
                  <li v-for="item in fallbackProblemShows" :key="item.show">
                    <strong>{{ item.show }}</strong>
                    <span class="magicflow-fb-report__meta">{{ (item.problems || []).map(p => `S${String(p.season).padStart(2, '0')}E${String(p.episode).padStart(2, '0')}`).join(' ') }}</span>
                  </li>
                </ul>
              </details>
              <details v-if="(fallbackState.report.shows || []).length" class="magicflow-fb-report__details">
                <summary>展开本剧集明细（{{ fallbackState.report.shows.length }} 部有变动）</summary>
                <ul class="magicflow-fb-report__list">
                  <li v-for="item in fallbackState.report.shows" :key="item.show">
                    <strong>{{ item.show }}</strong>
                    <span class="magicflow-fb-report__meta">识别自 {{ item.resolved || '未命中' }}｜补集 {{ (item.episodes || []).filter(e => e.nfo).length }}｜归位 {{ (item.renumbered || []).length }}</span>
                  </li>
                </ul>
              </details>
            </div>
          </div>

          <div v-else-if="settingsTab === 'cloud'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              <strong>本地当热区，夸克当冷库。</strong>
              把库里的成品大文件上传到 OpenList 的可写存储（夸克 cookie 驱动），
              同一夸克目录会被 OpenList 的 Strm 视图自动生成 <code>.strm</code> 播放指针，
              飞牛影视直接能看 —— <strong>无需改 OpenList 配置、也无需自己写 strm</strong>。
              默认<strong>只上传、不删本地</strong>；删本地与停种必须单独确认。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.cloud_enabled" label="启用云盘归档" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.cloud_dry_run" label="演练模式（只列计划，不真传）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.cloud_notify" label="完成后通知" color="primary" hide-details inset />
            </div>

            <div class="magicflow-settings-field">
              <div class="magicflow-settings-label">OpenList 连接</div>
              <div class="magicflow-iyuu-token">
                <VTextField
                  v-model="settingsDraft.cloud_openlist_url"
                  label="OpenList 地址"
                  placeholder="http://192.168.0.61:12022"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  autocomplete="off"
                />
              </div>
              <div class="magicflow-iyuu-token mt-2">
                <VTextField
                  v-model="settingsDraft.cloud_openlist_token"
                  label="OpenList Token"
                  :placeholder="cloudCfg.has_token ? '已保存（留空则不修改）' : 'openlist-…'"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  autocomplete="off"
                  persistent-hint
                  hint="留空 = 保留已保存的 Token；Token 不会回显到浏览器"
                />
                <VBtn
                  variant="tonal"
                  color="primary"
                  size="small"
                  prepend-icon="mdi-connection"
                  :loading="cloudTesting"
                  @click="testCloud"
                >测试</VBtn>
              </div>
              <p v-if="cloudTestMsg" class="magicflow-settings-hint" :class="cloudTestOk ? 'text-success' : 'text-error'">{{ cloudTestMsg }}</p>
            </div>

            <div class="magicflow-settings-grid">
              <VTextField
                v-model="settingsDraft.cloud_source_mount"
                label="可写存储路径"
                hint="OpenList 里可写的存储挂载点，默认 /quark"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model="settingsDraft.cloud_strm_mount"
                label="Strm 视图路径"
                hint="只读校验用（Strm 驱动），默认 /movie"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>

            <VTextField
              v-model="settingsDraft.cloud_target_template"
              label="远端目标模板"
              hint="{rel} = 相对库根的路径。默认 /quark/movie/{rel}（与本地库同构，影视侧自动对应）"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />

            <VCombobox
              v-model="settingsDraft.cloud_paths"
              label="扫描目录（容器内路径，留空 = /movie）"
              hint="可多个；只扫这些库根下的媒体文件"
              persistent-hint
              variant="outlined"
              density="comfortable"
              chips
              multiple
              clearable
              :items="['/movie']"
            />

            <VCombobox
              v-model="settingsDraft.cloud_exclude_paths"
              label="排除路径（子串匹配）"
              hint="默认已排除下载区/刷流区/蓝光原盘结构；这里可再加"
              persistent-hint
              variant="outlined"
              density="comfortable"
              chips
              multiple
              clearable
              :items="['/movie/刷流', '/movie/下载']"
            />

            <VCombobox
              v-model="settingsDraft.cloud_exclude_tags"
              label="排除标签（做种中的种子不打标上传策略，可留空）"
              variant="outlined"
              density="comfortable"
              chips
              multiple
              clearable
              :items="['魔流-推荐', '辅种', '已整理']"
            />

            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.cloud_min_size_gb"
                type="number"
                label="最小体积（GB，0 = 不限）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="settingsDraft.cloud_max_size_gb"
                type="number"
                label="最大体积（GB，0 = 不限）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="settingsDraft.cloud_min_age_days"
                type="number"
                label="最小入库天数（0 = 不限）"
                hint="只归档入库较久、已经稳定的资源"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.cloud_upload_limit_mbps"
                type="number"
                label="上传限速（Mbps，0 = 不限）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="settingsDraft.cloud_interval_minutes"
                type="number"
                label="后台归档周期（分钟）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="settingsDraft.cloud_scan_max"
                type="number"
                label="每轮最多处理文件数"
                variant="outlined"
                density="comfortable"
                hide-details
              />
            </div>

            <VDivider class="magicflow-fb-divider" />

            <div class="magicflow-settings-switches">
              <VSwitch
                v-model="settingsDraft.cloud_delete_local"
                label="归档后删除本地文件（危险：会停种；插件会拒绝自动执行，只做记录）"
                color="error"
                hide-details
                inset
              />
              <VSwitch
                v-model="settingsDraft.cloud_remove_torrent"
                label="同时移除下载器任务（危险，需人工确认）"
                color="error"
                hide-details
                inset
              />
            </div>
            <VAlert type="warning" variant="tonal" density="compact">
              安全默认：<strong>不删本地、不停种</strong>。删本地需要逐条上传校验通过后手动确认，绝不会自动执行。
            </VAlert>
          </div>
        </div>

        <footer class="magicflow-settings-dialog__footer">
          <VBtn
            v-if="settingsTab === 'downloader'"
            variant="tonal"
            color="primary"
            :disabled="!downloaderPrefsRecommended"
            @click="applyRecommendedPrefs"
          >
            恢复推荐值
          </VBtn>
          <VSpacer />
          <VBtn variant="text" @click="settingsDialog = false">取消</VBtn>
          <VBtn color="primary" variant="flat" :loading="saving" @click="saveActiveSettings">保存</VBtn>
        </footer>
      </VCard>
    </VDialog>

    <VDialog v-model="torrentDialog" max-width="34rem">
      <VCard v-if="activeTorrent" class="magicflow-dialog magicflow-torrent-dialog">
        <header class="magicflow-torrent-dialog__head">
          <div class="magicflow-torrent-dialog__tags">
            <VChip size="small" :color="stateColor(activeTorrent.state)" variant="tonal">{{ stateLabel(activeTorrent.state) }}</VChip>
            <VChip v-if="activeTorrent.is_protected" size="small" color="primary" variant="tonal" prepend-icon="mdi-shield-check-outline">已保留</VChip>
            <VChip size="small" variant="tonal">{{ selectedTask.site_name }}</VChip>
          </div>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="torrentDialog = false" />
        </header>

        <div class="magicflow-torrent-dialog__title">{{ activeTorrent.title || '种子详情' }}</div>

        <div class="magicflow-torrent-dialog__progress">
          <VProgressLinear
            :model-value="torrentProgressPct(activeTorrent)"
            :color="stateColor(activeTorrent.state)"
            height="8"
            rounded
          />
          <span class="magicflow-torrent-dialog__pct">{{ torrentProgressPct(activeTorrent) }}%</span>
        </div>

        <dl class="magicflow-torrent-dialog__grid">
          <div><dt>大小</dt><dd>{{ Number(activeTorrent.size_gb || 0).toFixed(2) }} GB</dd></div>
          <div><dt>上传量</dt><dd>{{ formatBytes(activeTorrent.uploaded) }}</dd></div>
          <div><dt>分享率</dt><dd>{{ Number(activeTorrent.ratio || 0).toFixed(2) }}</dd></div>
          <div><dt>当前状态</dt><dd>{{ stateLabel(activeTorrent.state) }}</dd></div>
        </dl>

        <div class="magicflow-torrent-dialog__hash">
          <span class="magicflow-torrent-dialog__hash-label">infohash</span>
          <code>{{ activeTorrent.hash }}</code>
          <VBtn size="x-small" variant="text" icon="mdi-content-copy" aria-label="复制 infohash" @click="copyTorrentHash(activeTorrent.hash)" />
        </div>

        <VCardActions class="magicflow-torrent-dialog__actions">
          <VBtn
            size="small"
            variant="tonal"
            :color="activeTorrent.is_protected ? 'grey' : 'primary'"
            :prepend-icon="activeTorrent.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline'"
            :loading="saving"
            @click="detailTorrentAction(activeTorrent.is_protected ? 'unprotect' : 'protect')"
          >{{ activeTorrent.is_protected ? '取消保留' : '保留' }}</VBtn>
          <VBtn
            v-if="torrentIsPaused(activeTorrent)"
            size="small"
            variant="tonal"
            prepend-icon="mdi-play-circle-outline"
            :loading="saving"
            @click="detailTorrentAction('resume')"
          >{{ torrentResumeLabel(activeTorrent) }}</VBtn>
          <VBtn v-else size="small" variant="tonal" prepend-icon="mdi-pause-circle-outline" :loading="saving" @click="detailTorrentAction('pause')">{{ torrentPauseLabel(activeTorrent) }}</VBtn>
          <VBtn size="small" variant="tonal" prepend-icon="mdi-sync" :loading="saving" @click="detailTorrentAction('recheck')">校验</VBtn>
          <VSpacer />
          <VBtn size="small" color="error" variant="tonal" prepend-icon="mdi-delete-outline" :loading="saving" @click="requestTorrentDelete(activeTorrent)">删除</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="batchDeleteDialog" max-width="28rem">
      <VCard class="magicflow-dialog">
        <VCardTitle>批量删除托管种子</VCardTitle>
        <VCardText class="text-body-2">
          确认删除选中的 <b>{{ selectedHashes.length }}</b> 个种子？
          <br />
          <span class="text-medium-emphasis">
            将按任务设置{{ selectedTask.delete_files ? '连同文件' : '保留文件' }}从下载器删除，不可撤销。
          </span>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="batchDeleteDialog = false">取消</VBtn>
          <VBtn color="error" variant="flat" :loading="batchBusy" @click="batchAction('delete')">删除</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="torrentDeleteDialog" max-width="28rem">
      <VCard class="magicflow-dialog">
        <VCardTitle class="text-wrap">删除托管种子</VCardTitle>
        <VCardText class="text-body-2">
          确认删除「{{ pendingTorrentDelete?.title || '该种子' }}」？
          <br />
          <span class="text-medium-emphasis">
            将按任务设置{{ selectedTask.delete_files ? '连同文件' : '保留文件' }}从下载器删除，不可撤销。
          </span>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="torrentDeleteDialog = false">取消</VBtn>
          <VBtn color="error" variant="flat" :loading="saving" @click="confirmTorrentDelete">删除</VBtn>
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

    <VDialog v-model="cloudOpen" max-width="52rem" scrollable>
      <VCard class="magicflow-dialog magicflow-cloud-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">云盘归档</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" :loading="cloudLoading" @click="loadCloud">刷新</VBtn>
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="cloudOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-cloud-dialog__body">
          <VAlert v-if="!cloudCfg.enabled" type="info" variant="tonal" density="compact" class="mb-2">
            云盘归档未启用（「插件设置 → 云盘归档」里开启并填 OpenList 地址 / Token）。
          </VAlert>
          <div class="magicflow-cloud-dialog__summary">
            <span><strong>{{ cloudPlanStats?.pending ?? 0 }}</strong> 待上传</span>
            <i>·</i>
            <span><strong>{{ cloudPlanStats?.remote_exists ?? 0 }}</strong> 远端已有</span>
            <i>·</i>
            <span><strong>{{ cloudPlanStats?.done ?? 0 }}</strong> 已归档</span>
            <i>·</i>
            <span>{{ cloudPlanStats?.pending_gb ?? 0 }} GB</span>
            <i>·</i>
            <span><strong>{{ cloudState?.record_count ?? 0 }}</strong> 条记录</span>
          </div>
          <div class="magicflow-cloud-dialog__note">
            上传到 OpenList 可写存储 → 同一夸克目录 → Strm 视图自动生成播放指针 → 影视直接能看。
            默认<strong>只上传不删除</strong>；本地删除需单独确认。
          </div>
          <div class="magicflow-cloud-dialog__actions">
            <VBtn variant="tonal" color="primary" size="small" prepend-icon="mdi-connection" :loading="cloudTesting" @click="testCloud">测试连接</VBtn>
            <VBtn variant="tonal" size="small" prepend-icon="mdi-clipboard-list-outline" :loading="cloudPlanning" @click="planCloud">扫描候选</VBtn>
            <VBtn variant="tonal" size="small" prepend-icon="mdi-play-circle-outline" :loading="cloudRunning" @click="runCloud(true)">演练归档</VBtn>
            <VBtn color="primary" variant="flat" size="small" prepend-icon="mdi-cloud-upload-outline" :loading="cloudRunning" @click="runCloud(false)">开始归档</VBtn>
            <VTextField
              v-model.number="cloudLimit"
              label="本轮条数"
              type="number"
              variant="outlined"
              density="compact"
              hide-details
              class="magicflow-cloud-dialog__limit"
            />
          </div>
          <VAlert v-if="cloudTestMsg" :type="cloudTestOk ? 'success' : 'error'" variant="tonal" density="compact" class="my-2">
            {{ cloudTestMsg }}
          </VAlert>
          <VAlert v-if="cloudState?.running" type="info" variant="tonal" density="compact" class="my-2">
            归档任务正在后台执行（可关闭本窗口，进度看下方列表与「操作记录」）。
          </VAlert>
          <VSheet tag="section" class="magicflow-panel app-surface-static mt-2">
            <header class="magicflow-panel__head">
              <div>
                <div class="text-subtitle-2 font-weight-medium">归档候选</div>
                <div class="text-body-2 text-medium-emphasis">点「扫描候选」列出可上传文件；逐条点「上传」立即传该文件（后台执行）</div>
              </div>
            </header>
            <p v-if="cloudLoading && !cloudPlanItems.length" class="magicflow-settings-hint">加载中…</p>
            <p v-else-if="!cloudPlanItems.length" class="magicflow-settings-hint">
              还没有候选。点上方「扫描候选」；若为 0，检查设置里的「扫描目录 / 体积范围 / 最小入库天数」。
            </p>
            <div v-for="it in cloudPlanItems" :key="it.path" class="magicflow-cloud-row">
              <div class="magicflow-cloud-row__main">
                <div class="magicflow-cloud-row__title">{{ it.name }}</div>
                <div class="magicflow-cloud-row__sub">{{ it.rel }} · {{ it.size_gb }} GB</div>
                <div v-if="it.message || (cloudRecordFor(it) || {}).error" class="magicflow-cloud-row__msg">
                  {{ it.message || (cloudRecordFor(it) || {}).error }}
                </div>
              </div>
              <div class="magicflow-cloud-row__side">
                <VChip size="x-small" variant="tonal" :color="cloudStatusMeta(cloudRecordFor(it)?.status || it.status).color">
                  {{ cloudStatusMeta(cloudRecordFor(it)?.status || it.status).text }}
                </VChip>
                <VBtn
                  size="x-small"
                  variant="tonal"
                  color="primary"
                  :loading="cloudUploadingPath === it.path"
                  @click="uploadCloudOne(it)"
                >上传</VBtn>
              </div>
            </div>
          </VSheet>
        </VCardText>
      </VCard>
    </VDialog>

    <VDialog v-model="recommendOpen" max-width="46rem" scrollable>
      <VCard class="magicflow-dialog magicflow-recommend-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">推荐甄别</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" @click="loadRecommend">刷新</VBtn>
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="recommendOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-recommend-dialog__body">
          <div class="magicflow-recommend-dialog__summary">
            <span><strong>{{ recommendData.recommended || 0 }}</strong> 待确认</span>
            <i>·</i>
            <span><strong>{{ confirmedCount }}</strong> 已入库</span>
            <i>·</i>
            <span><strong>{{ pendingCount }}</strong> 未达门槛</span>
            <i>·</i>
            <span>共 {{ recommendData.total || 0 }} 条</span>
            <i>·</i>
            <span>标签 {{ recommendData.tag || '魔流-推荐' }}</span>
          </div>
          <div class="magicflow-recommend-dialog__note">
            评分 &gt; {{ recommendData.min_rating ?? 7.5 }}<template v-if="recommendData.require_chart !== false"> 或在榜 / 热映 / 订阅</template>
            · 过期 {{ recommendData.expire_days ?? 7 }} 天 · 磁盘余量下限 {{ recommendData.disk_min_free_gb ?? 50 }}G
          </div>
          <VAlert v-if="recommendData.enabled === false" type="info" variant="tonal" density="compact" class="my-2">
            推荐甄别已关闭（可在「插件设置 → 推荐」开启）
          </VAlert>
          <VSheet tag="section" class="magicflow-panel app-surface-static mt-2">
            <header class="magicflow-panel__head">
              <div>
                <div class="text-subtitle-2 font-weight-medium">甄别结果</div>
                <div class="text-body-2 text-medium-emphasis">全部任务汇总 · 确认 = 自动整理入库；忽略 = 删除该临时种（«待核实»也可手动确认）</div>
              </div>
              <VBtn
                size="small"
                variant="text"
                color="primary"
                :prepend-icon="showAllRecs ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
                @click="showAllRecs = !showAllRecs"
              >{{ showAllRecs ? '仅看推荐' : (hiddenRecCount ? `显示全部候选 (+${hiddenRecCount})` : '显示全部候选') }}</VBtn>
            </header>
            <div class="magicflow-recs">
              <article v-for="rec in recommendItems" :key="rec.hash" class="magicflow-rec">
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
                    :loading="recommendActing === rec.hash + 'confirm'"
                    @click="confirmRecommend(rec.hash)"
                  >
                    确认入库
                  </VBtn>
                  <VBtn
                    size="small"
                    color="error"
                    variant="text"
                    prepend-icon="mdi-delete-outline"
                    :loading="recommendActing === rec.hash + 'dismiss'"
                    @click="dismissRecommend(rec.hash)"
                  >
                    忽略删除
                  </VBtn>
                </div>
              </article>
              <div v-if="!recommendItems.length" class="magicflow-table-empty">
                暂无推荐{{ showAllRecs ? '' : '（当前没有同时满足「评分 > ' + (recommendData.min_rating ?? 7.5) + ' 且在榜 / 热映 / 订阅」的资源）' }}。
                <template v-if="!showAllRecs && hiddenRecCount">可点右上「显示全部候选 (+{{ hiddenRecCount }})」看全部评估（含未达门槛的临时种）。</template>
              </div>
            </div>
          </VSheet>
        </VCardText>
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

.magicflow-settings-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
}

.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
}

.magicflow-settings-dialog__tabs {
  padding-inline: 8px;
}

.magicflow-settings-hint {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 0.8rem;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  background: rgba(var(--v-theme-primary), 0.07);
  border-inline-start: 3px solid rgba(var(--v-theme-primary), 0.45);
}

.magicflow-settings-hint--warn {
  background: rgba(var(--v-theme-warning), 0.12);
  border-inline-start-color: rgba(var(--v-theme-warning), 0.7);
}

.magicflow-settings-dialog {
  display: flex;
  flex-direction: column;
  block-size: min(84vh, 40rem);
  max-block-size: 92vh;
  overflow: hidden;
}

.magicflow-settings-dialog__head,
.magicflow-settings-dialog__tabs,
.magicflow-settings-dialog > .v-divider {
  flex: 0 0 auto;
}

.magicflow-settings-dialog__body {
  flex: 1 1 0;
  min-block-size: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scroll-padding-block: 8px;
}

.magicflow-settings-form {
  display: grid;
  gap: 14px;
  align-content: start;
  padding: 16px 18px 14px;
}

.magicflow-settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}

.magicflow-settings-switches {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 16px;
}

.magicflow-settings-actions {
  display: grid;
  gap: 10px;
  justify-items: start;
}

/* 元数据兜底设置 */
.magicflow-settings-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  margin-block-end: 6px;
}

.magicflow-fb-sources {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.magicflow-fb-source {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 4px 10px;
  border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.06);
  border: 1px solid rgba(var(--v-border-color), 0.28);
}

.magicflow-fb-source__idx {
  inline-size: 20px;
  block-size: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 0.72rem;
  font-weight: 600;
  color: rgb(var(--v-theme-on-primary));
  background: rgba(var(--v-theme-primary), 0.85);
  flex: 0 0 auto;
}

.magicflow-fb-source__name {
  flex: 1 1 auto;
  min-inline-size: 0;
  font-size: 0.85rem;
  overflow-wrap: anywhere;
}

.magicflow-fb-source-add {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  margin-block-start: 8px;
}

.magicflow-fb-divider {
  margin-block: 4px;
}

.magicflow-fb-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.magicflow-fb-running {
  font-size: 0.78rem;
  color: rgb(var(--v-theme-primary));
}

.magicflow-fb-report {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.05);
  font-size: 0.8rem;
  line-height: 1.6;
}

.magicflow-fb-report__line {
  overflow-wrap: anywhere;
}

.magicflow-fb-report__details summary {
  cursor: pointer;
  color: rgba(var(--v-theme-primary), 1);
}

.magicflow-fb-report__list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: grid;
  gap: 6px;
  max-block-size: 16rem;
  overflow-y: auto;
}

.magicflow-fb-report__list li {
  display: grid;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  overflow-wrap: anywhere;
}

.magicflow-fb-report__meta {
  font-size: 0.74rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

/* IYUU 辅种设置 */
.magicflow-iyuu-token {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.magicflow-iyuu-sites {
  display: grid;
  gap: 10px;
}

.magicflow-iyuu-sites__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
}

.magicflow-iyuu-row {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-iyuu-row__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-inline-size: 0;
}

.magicflow-iyuu-row__name {
  font-weight: 600;
  font-size: 0.85rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.magicflow-iyuu-row__fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.7fr);
  gap: 8px;
}

@media (max-width: 480px) {
  .magicflow-iyuu-row__fields {
    grid-template-columns: minmax(0, 1fr);
  }
}

.magicflow-settings-dialog__footer {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px 14px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
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

.magicflow-live-alerts {
  display: grid;
  gap: 6px;
  margin-block-start: 12px;
}

.magicflow-live-alerts__head {
  font-size: 0.78rem;
  font-weight: 600;
  opacity: 0.8;
}

.magicflow-live-alert {
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.78rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
  border-inline-start: 3px solid transparent;
}

.magicflow-live-alert--warn {
  background: rgba(255, 152, 0, 0.12);
  border-inline-start-color: #ff9800;
}

.magicflow-live-alert--info {
  background: rgba(var(--v-theme-info), 0.12);
  border-inline-start-color: rgb(var(--v-theme-info));
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

.magicflow-bulk-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block: 10px 4px;
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(139, 123, 240, 0.12);
  box-shadow: inset 0 0 0 1px rgba(139, 123, 240, 0.28);
}

.magicflow-bulk-bar__count {
  font-size: 12px;
  font-weight: 600;
  color: #cfc7ff;
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

/* ---------- 种子详情弹窗 ---------- */
.magicflow-torrent-dialog {
  padding: 18px 20px 8px;
}

.magicflow-torrent-dialog__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.magicflow-torrent-dialog__tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-inline-size: 0;
}

.magicflow-torrent-dialog__title {
  margin-block: 10px 0;
  font-size: 15px;
  font-weight: 650;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.magicflow-torrent-dialog__progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-block: 12px 4px;
}

.magicflow-torrent-dialog__progress .v-progress-linear {
  flex: 1 1 auto;
}

.magicflow-torrent-dialog__pct {
  flex: 0 0 auto;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: rgba(226, 232, 240, 0.85);
  min-inline-size: 3.2em;
  text-align: end;
}

.magicflow-torrent-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
  margin-block: 14px 4px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(139, 123, 240, 0.07);
  box-shadow: inset 0 0 0 1px rgba(139, 123, 240, 0.16);
}

.magicflow-torrent-dialog__grid > div {
  min-inline-size: 0;
}

.magicflow-torrent-dialog__grid dt {
  font-size: 11px;
  color: rgba(200, 208, 232, 0.65);
  margin-block-end: 2px;
}

.magicflow-torrent-dialog__grid dd {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.magicflow-torrent-dialog__hash {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-block: 12px 0;
  min-inline-size: 0;
}

.magicflow-torrent-dialog__hash-label {
  flex: 0 0 auto;
  font-size: 11px;
  color: rgba(200, 208, 232, 0.6);
}

.magicflow-torrent-dialog__hash code {
  flex: 1 1 auto;
  min-inline-size: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  overflow-wrap: anywhere;
  color: rgba(210, 216, 240, 0.8);
}

.magicflow-torrent-dialog__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 14px 0 8px;
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

.magicflow-recommend-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.magicflow-recommend-dialog__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  font-size: 0.85rem;
  color: rgb(var(--v-theme-on-surface-variant));
}

.magicflow-recommend-dialog__summary strong {
  font-size: 1.05rem;
  color: rgb(var(--v-theme-primary));
}

.magicflow-recommend-dialog__summary i {
  font-style: normal;
  opacity: 0.4;
}

.magicflow-recommend-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.85;
}

.magicflow-recommend-dialog__body {
  max-block-size: min(68dvh, 42rem);
  overflow-y: auto;
  overscroll-behavior: contain;
}

/* ── 云盘归档弹窗 ───────────────────────────────── */
.magicflow-cloud-dialog__body {
  max-block-size: min(70dvh, 44rem);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.magicflow-cloud-dialog__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  font-size: 0.85rem;
  color: rgb(var(--v-theme-on-surface-variant));
}

.magicflow-cloud-dialog__summary strong {
  font-size: 1.05rem;
  color: rgb(var(--v-theme-primary));
}

.magicflow-cloud-dialog__summary i {
  font-style: normal;
  opacity: 0.4;
}

.magicflow-cloud-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.85;
}

.magicflow-cloud-dialog__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.magicflow-cloud-dialog__limit {
  inline-size: 7.5rem;
}

.magicflow-cloud-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-block: 8px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-cloud-row:last-child {
  border-block-end: 0;
}

.magicflow-cloud-row__main {
  flex: 1 1 auto;
  min-inline-size: 0;
}

.magicflow-cloud-row__title {
  font-size: 0.88rem;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.magicflow-cloud-row__sub {
  font-size: 0.76rem;
  color: rgb(var(--v-theme-on-surface-variant));
  overflow-wrap: anywhere;
}

.magicflow-cloud-row__msg {
  margin-block-start: 2px;
  font-size: 0.74rem;
  color: rgb(var(--v-theme-warning));
  overflow-wrap: anywhere;
}

.magicflow-cloud-row__side {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

@media (max-width: 699px) {
  .magicflow-cloud-dialog__actions {
    gap: 6px;
  }

  .magicflow-cloud-dialog__limit {
    inline-size: 100%;
  }

  .magicflow-cloud-row {
    flex-direction: column;
    align-items: stretch;
  }

  .magicflow-cloud-row__side {
    justify-content: space-between;
  }
}

.magicflow-rec {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding-block: 8px;
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
  color: rgb(var(--v-theme-on-surface-variant));
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
  color: rgb(var(--v-theme-on-surface-variant));
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
  .magicflow-rec__actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
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

  /* 设置面板：单列字段、收紧留白 */
  .magicflow-settings-grid,
  .magicflow-settings-switches {
    grid-template-columns: 1fr;
  }

  /* 设置面板：窄屏收缩 tab，尽量一排放下 */
  .magicflow-settings-tab {
    padding-inline: 6px;
    min-width: auto !important;
    font-size: 12px;
    text-transform: none;
  }

  .magicflow-settings-dialog {
    block-size: min(90vh, 38rem);
    max-block-size: 94vh;
  }

  .magicflow-settings-form {
    padding: 12px 14px 10px;
  }

  .magicflow-settings-dialog__footer {
    padding: 10px 14px 12px;
  }

  /* 种子详情弹窗：窄屏收紧留白与网格间距 */
  .magicflow-torrent-dialog {
    padding: 16px 14px 4px;
  }

  .magicflow-torrent-dialog__grid {
    gap: 8px 10px;
    padding: 10px 12px;
  }

  .magicflow-torrent-dialog__actions {
    gap: 4px;
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

/* 顶部「当前任务」切换下拉（方案 B） */
.magicflow-page .magicflow-task-switch {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  max-inline-size: 22rem;
  padding: 6px 10px 6px 7px;
  border: 1px solid rgba(139, 123, 240, 0.26);
  border-radius: 12px;
  background: linear-gradient(145deg, rgba(139, 123, 240, 0.16), rgba(139, 123, 240, 0.05));
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(139, 123, 240, 0.16);
}

.magicflow-page .magicflow-task-switch:hover {
  border-color: rgba(139, 123, 240, 0.42);
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
  color: #fff;
  background: linear-gradient(145deg, #9484f5, #5b4fb8);
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

@media (max-width: 959px) {
  /* 桌面品牌头里的切换胶囊隐藏；移动端由工具栏承担 */
  .magicflow-page__actions .magicflow-task-switch {
    display: none;
  }

  /* ★ 窄屏：把「新建任务 / 推荐 / 云盘归档 / 插件设置 / 关闭」这几个按钮收进右上角「⋮ 更多」菜单，
     腾出横向空间给品牌（其余版式与 3.2.0 保持一致） */
  .magicflow-page__actions .magicflow-header-create,
  .magicflow-page__actions .magicflow-recommend-wrap,
  .magicflow-page__actions .magicflow-recommend-btn,
  .magicflow-page__actions .magicflow-cloud-btn,
  .magicflow-page__actions .magicflow-settings-btn,
  .magicflow-page__actions .magicflow-close-btn {
    display: none;
  }

  .magicflow-page__actions .magicflow-more-btn {
    display: inline-flex;
  }

  /* 移动工具栏沿用「方案 B」胶囊：站点图标 + 任务名·站点 + 状态点 + ⌄ */
  .magicflow-page .magicflow-mobile-toolbar .magicflow-task-switch {
    display: inline-flex;
    flex: 1 1 auto;
    min-inline-size: 0;
    max-inline-size: none;
  }

  .magicflow-page .magicflow-mobile-toolbar .magicflow-task-switch__k {
    display: none;
  }

  .magicflow-page .magicflow-mobile-toolbar .magicflow-task-switch__v {
    font-size: 14px;
  }
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

/* 操作记录 · 明细展开（手机优先：单行省略，不撑破卡片） */
.magicflow-page .magicflow-events__toggle {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-block-start: 2px;
  padding: 0;
  border: 0;
  background: none;
  color: rgb(var(--v-theme-primary));
  font-size: 0.76rem;
  font-weight: 600;
  cursor: pointer;
}

.magicflow-page .magicflow-events__detail {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}

.magicflow-page .magicflow-events__detail li {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-inline-size: 0;
  padding-block: 5px;
  border-top: 1px dashed rgba(140, 150, 220, 0.14);
}

.magicflow-page .magicflow-events__detail li:first-child {
  border-top: 0;
}

.magicflow-page .magicflow-events__detail-line {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-inline-size: 0;
}

.magicflow-page .magicflow-events__detail-src {
  flex: 0 0 auto;
  font-style: normal;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 0 5px;
  border-radius: 5px;
  color: rgb(var(--v-theme-primary));
  background: rgba(139, 123, 240, 0.16);
}

.magicflow-page .magicflow-events__detail-title {
  min-inline-size: 0;
  flex: 1 1 auto;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), 0.86);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.magicflow-page .magicflow-events__detail-sub {
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
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

<style>
/* 滚动条适配主题（避免真实浏览器里出现刺眼的默认亮色滚动条） */
.magicflow-settings-dialog__body,
.magicflow-dialog {
  scrollbar-width: thin;
  scrollbar-color: rgba(var(--v-border-color), 0.32) transparent;
}

.magicflow-settings-dialog__body::-webkit-scrollbar,
.magicflow-dialog::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.magicflow-settings-dialog__body::-webkit-scrollbar-track,
.magicflow-dialog::-webkit-scrollbar-track {
  background: transparent;
}

.magicflow-settings-dialog__body::-webkit-scrollbar-thumb,
.magicflow-dialog::-webkit-scrollbar-thumb {
  background: rgba(var(--v-border-color), 0.3);
  background-clip: content-box;
  border: 2px solid transparent;
  border-radius: 999px;
}

.magicflow-settings-dialog__body::-webkit-scrollbar-thumb:hover,
.magicflow-dialog::-webkit-scrollbar-thumb:hover {
  background: rgba(var(--v-border-color), 0.5);
  background-clip: content-box;
}
</style>
