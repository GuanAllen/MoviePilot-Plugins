<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import TaskEditorDialog from '../../components/TaskEditorDialog.vue'
import MusicDialog from './components/dialogs/MusicDialog.vue'
import CeilingDialog from './components/dialogs/CeilingDialog.vue'
import HealthDialog from './components/dialogs/HealthDialog.vue'
import DoubanDialog from './components/dialogs/DoubanDialog.vue'
import ExamDialog from './components/dialogs/ExamDialog.vue'
import HrBillsDialog from './components/dialogs/HrBillsDialog.vue'
import CloudDialog from './components/dialogs/CloudDialog.vue'
import SilentPoolDialog from './components/dialogs/SilentPoolDialog.vue'
import InvariantDialog from './components/dialogs/InvariantDialog.vue'
import ClaimConfirm from './components/confirm/ClaimConfirm.vue'
import EnforceConfirm from './components/confirm/EnforceConfirm.vue'
import TagReconConfirm from './components/confirm/TagReconConfirm.vue'
import ClaimDialog from './components/dialogs/ClaimDialog.vue'
import ExamConfirm from './components/confirm/ExamConfirm.vue'
import SiteReportDialog from './components/dialogs/SiteReportDialog.vue'
import RecommendDialog from './components/dialogs/RecommendDialog.vue'
import TorrentDialog from './components/dialogs/TorrentDialog.vue'
import SigninDialog from './components/dialogs/SigninDialog.vue'
import OndemandDialog from './components/dialogs/OndemandDialog.vue'
import OpsDialog from './components/dialogs/OpsDialog.vue'
import WorkbenchHeader from './components/WorkbenchHeader.vue'
import MobileTaskDetail from './components/MobileTaskDetail.vue'
import TaskPane from './components/TaskPane.vue'
import TorrentDeleteConfirm from './components/confirm/TorrentDeleteConfirm.vue'
import OverviewTab from './components/tabs/OverviewTab.vue'
import CrossseedDialog from './components/dialogs/CrossseedDialog.vue'
import RescueDialog from './components/dialogs/RescueDialog.vue'
import SettingsDialog from './components/dialogs/SettingsDialog.vue'
import BatchDeleteConfirm from './components/confirm/BatchDeleteConfirm.vue'
import DeleteTaskConfirm from './components/confirm/DeleteTaskConfirm.vue'
import TaskConfigTab from './components/tabs/TaskConfigTab.vue'
import JournalTab from './components/tabs/JournalTab.vue'
import CandidatesTab from './components/tabs/CandidatesTab.vue'
import SeedingTab from './components/tabs/SeedingTab.vue'
import MobileHome from './components/MobileHome.vue'
import TransferConfirm from './components/confirm/TransferConfirm.vue'
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
  normalizeSortRules,
  normalizeTask,
  cloudStatusMeta,
  recommendStatusMeta,
  RUN_MODES,
  runModeMeta,
  runStatusText,
  taskStateMeta,
  unwrapResponse,
} from '../../utils'
import {
  ratingSourceItems,
  MF_PAGES,
  TILE_OPTIONS,
  MF_SETTINGS_TABS,
  SITE_REPORT_BUCKETS,
  SITE_REPORT_TRANSPORT,
  SITE_REPORT_SILENT_SUBS,
  SITE_REPORT_ORIGINS,
  FLOW_STEPS_BONUS,
  FLOW_STEPS_BRUSH,
  MF_TABS,
  KIND_TEXT,
  STATE_TEXT,
  KIND_ICON,
  EVENT_LEVELS,
  OPS_KIND_FILTERS,
  ITEM_SOURCE_TEXT,
  RESEED_KINDS,
  TORRENT_STATE_TEXT,
  TORRENT_TRANSIENT_STATES,
  TORRENT_PAUSED_STATES,
  SIGNIN_STATUS_TEXT,
  SIGNIN_FAIL_STATUS,
  SIGNIN_ORDER,
  EXAM_KIND_TEXT,
  EXAM_KIND_ICON,
  EXAM_ACTIONABLE,
  SILENT_SUB_LABEL,
  TORRENT_ACTION_LABEL,
  BATCH_LABEL,
} from './constants'
import { createApi } from '../../api/request'
import { formatRemain, tsText, fmtTs } from './format'
import { useOndemand } from './composables/useOndemand'
import { useRescue } from './composables/useRescue'
import { useReseed } from './composables/useReseed'
import { useRecImport } from './composables/useRecImport'
import { useTagModel } from './composables/useTagModel'
import { useRecommend } from './composables/useRecommend'
import { useHealth } from './composables/useHealth'
import { useSilentPool } from './composables/useSilentPool'
import { useInvariant } from './composables/useInvariant'
import { useExam } from './composables/useExam'
import { useSignin } from './composables/useSignin'
import { useDouban } from './composables/useDouban'
import { useCloud } from './composables/useCloud'
import { useCrossseed } from './composables/useCrossseed'
import { useFallback } from './composables/useFallback'
import { useHeaderTiles } from './composables/useHeaderTiles'
import { useWorkbench } from './composables/useWorkbench'
import { useTasks } from './composables/useTasks'
import { useTaskDetail } from './composables/useTaskDetail'
import { useCandidates } from './composables/useCandidates'
import { useSiteReport } from './composables/useSiteReport'
import { useMusic } from './composables/useMusic'
import { useHrBills } from './composables/useHrBills'
import { useOperations } from './composables/useOperations'
import { useSettings } from './composables/useSettings'
import { useSeeding } from './composables/useSeeding'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MagicFlow' },
  initialTab: { type: String, default: 'overview' },
  showClose: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'action'])
const hostToast = inject('moviepilot:toast', null)

// 按任务缓存托管种子（切任务时秒显，再后台静默刷新）
let doubanServiceTimer = null
let healthTimer = null
// ── useWorkbench（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useWorkbench.js（纯搬家）。
const {
  activeTab,
  ceilingOpen,
  isNarrow,
  mhOpen,
  mhSiteOpen,
  mobileView,
  selectedTaskId,
} = useWorkbench({ props })
// 批量操作：选中行（VDataTable show-select 与手机卡片共用）
// 批量转移（托管页）


const settingsDraft = ref({
  enabled: false,
  show_sidebar_nav: true,
  debug_log: false,
  compact_mode: false,
  hidden_tiles: [],
  journal_keep: 200,
  request_interval: 0,
  bonus_upload_limit_kbps: 200,
  brush_upload_limit_kbps: 10240,
  seed_up_limit_kbps: 200,
  brush_seed_up_limit_kbps: 5120,
  tag_model_enabled: true,
  show_qb_tags: true,
  tag_silent_new_timeout_hours: 24,
  sort_rules: [],
  iyuu_token: '',
  iyuu_clear: false,
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
  promo_guard: true,
  live_notify: true,
  crossseed_guard: true,
  crossseed_guard_pct: 5,
  crossseed_guard_min_mb: 50,
  crossseed_guard_interval_min: 15,
  crossseed_guard_keep_seed: true,
  crossseed_seed_hours_default: 24,
  crossseed_site_hours: ['pt.btschool.club=10'],
  crossseed_reclaim: false,
  hr_seed_margin_hours: 2,
  hr_deadline_warn_hours: 48,
  hr_complete_ratio: 0.999,
  reseed_enabled: false,
  reseed_dry: true,
  reseed_sites: [],
  reseed_daily_per_site: 30,
  reseed_batch: 10,
  reseed_min_size_gb: 1,
  claim_enabled: false,
  claim_dry: true,
  claim_sites: [],
  claim_daily_per_site: 20,
  claim_batch: 5,
  claim_interval_sec: 8,
  claim_min_age_days: 0,
  claim_require_seeders: 0,
  claim_min_size_gb: 0,
  claim_exclude_zero_bonus: true,
  rules_auto_refresh: true,
})
// ---- 站点实时数据 + 流量监控（直连站点，非 MP 6h 快照）----
const liveState = ref(null)
const liveLoading = ref(false)
let liveTimer = null
// ---- 云盘归档 ----
// IYUU 云端辅种（可选）：站点表按 MoviePilot 已配置站点生成
let refreshTimer
let phaseTimer
let warmingTimer

// 任务图标使用站点自身图标（走 MoviePilot /site/icon/{id}，服务端带 cookie 抓取，私有站也能取到）
const siteIcons = ref({})
const siteIconPending = new Set()

async function loadSiteIcon(siteId) {
  const id = Number(siteId)
  if (!id || siteIcons.value[id] !== undefined || siteIconPending.has(id)) return
  siteIconPending.add(id)
  try {
    const data = unwrapResponse(await api.features.siteIcon(id))
    siteIcons.value = { ...siteIcons.value, [id]: (data && data.icon) || '' }
  } catch (err) {
    siteIcons.value = { ...siteIcons.value, [id]: '' }
  } finally {
    siteIconPending.delete(id)
  }
}

const pluginBase = computed(() => `plugin/${props.pluginId || 'MagicFlow'}`)
// P2：接口层（按域分组；函数返回原始响应，调用点自行 unwrapResponse）
const api = createApi(props.api, props.pluginId)
// ── useMusic（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useMusic.js（纯搬家）。
const {
  loadMusicPlan,
  musicActing,
  musicError,
  musicGrabReport,
  musicOpen,
  musicResetResult,
  musicResult,
  musicSavePath,
  musicSites,
  musicText,
  openMusic,
  runMusicGrab,
} = useMusic({ api })
// ── useTasks（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useTasks.js（纯搬家）。
const {
  confirmDeleteTask,
  defaultSavePath,
  deleteDialog,
  editorOpen,
  editorTask,
  error,
  handover,
  handoverChoices,
  handoverLoading,
  handoverTarget,
  loadStatus,
  loading,
  notify,
  onDeleteDialog,
  openCreateTask,
  openEditTask,
  recentSavePaths,
  saveTask,
  saving,
  scheduleWarmingRetry,
  selectedRunMode,
  selectedState,
  selectedTask,
  silentHostSites,
  status,
  statusLoaded,
  summary,
  taskBadge,
  taskLoading,
  taskSwitchSubtitle,
  tasks,
  warmingRetryCount,
} = useTasks({ selectedTaskId, api, emit, hostToast, settingsDraft, selectTask, warmingTimer })
// ── useOperations（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useOperations.js（纯搬家）。
const {
  backfillPages,
  backfilling,
  eventLevel,
  eventLevelColor,
  eventLevelIcon,
  eventRows,
  eventsLoading,
  expandedOps,
  hasOpDetail,
  isOpDetailOpen,
  isReseedRecord,
  itemSourceText,
  kindCount,
  loadEventRows,
  loadOperations,
  loadOperationsAll,
  opDetailItems,
  openOperations,
  operationColor,
  operationData,
  operationDuration,
  operationIcon,
  operationKindText,
  operationStateText,
  operationSummary,
  opsFiltered,
  opsKind,
  opsKindItems,
  opsLoadingAll,
  opsOpen,
  opsQuery,
  opsScope,
  opsView,
  reloadOperations,
  reseedActionText,
  reseedRows,
  taskLabel,
  toggleOpDetail,
} = useOperations({ api, error, notify, selectedTaskId, tasks })
// ── useTaskDetail（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useTaskDetail.js（纯搬家）。
const {
  bonusCache,
  bonusData,
  bonusLoadedFor,
  brushSeedDays,
  candidateData,
  candidateLoadedAt,
  candidateLoadedFor,
  decision,
  decisionCapText,
  decisionReasons,
  detail,
  detailAttention,
  detailStats,
  flowNodes,
  flowPhaseText,
  flowSteps,
  goalFactText,
  loadBonus,
  loadCandidates,
  loadDetail,
  loadTrend,
  siteUser,
  sparkline,
  taskConfig,
  taskIsBrush,
  taskSiteIcon,
  trendCards,
  trendSeries,
  trendSite,
  trendTask,
} = useTaskDetail({ api, siteIcons, error, selectedTask, selectedTaskId, taskLoading })
// ── useSeeding（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useSeeding.js（纯搬家）。
const {
  activeTorrent,
  allFilteredSelected,
  batchAction,
  batchBusy,
  batchDeleteDialog,
  clearSelection,
  confirmTorrentDelete,
  confirmTransfer,
  copyTorrentHash,
  detailTorrentAction,
  onTorrentRowClick,
  openTorrentDetail,
  openTransfer,
  pendingTorrentDelete,
  requestTorrentDelete,
  selectAllFiltered,
  selectedHashes,
  selectedRows,
  sortedTorrents,
  stateColor,
  stateLabel,
  toggleTorrentSelection,
  torrentAction,
  torrentActionMessage,
  torrentDeleteDialog,
  torrentDialog,
  torrentFilter,
  torrentHeaders,
  torrentIsPaused,
  torrentPauseLabel,
  torrentProgressPct,
  torrentResumeLabel,
  torrentStateText,
  torrentStatusFilter,
  torrentStatusGroup,
  torrentStatusOptions,
  transferChoices,
  transferDialog,
  transferTarget,
} = useSeeding({ api, emit, bonusData, error, loadBonus, loadDetail, notify, saving, selectedTask, status })
// ── useCandidates（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useCandidates.js（纯搬家）。
const {
  candidateRawTotal,
  maxReasonCount,
  poolView,
  reasonEntries,
} = useCandidates({ candidateData })
// ── useFallback（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useFallback.js（纯搬家）。
const {
  addFallbackSource,
  fallbackLoading,
  fallbackProblemCount,
  fallbackProblemShows,
  fallbackRunning,
  fallbackSourceDraft,
  fallbackSourceLabel,
  fallbackSourceOptions,
  fallbackState,
  loadFallback,
  moveFallbackSource,
  removeFallbackSource,
  runFallback,
  unusedFallbackSources,
  usedFallbackSources,
} = useFallback({ api, error, notify, settingsDraft })
// ── useCrossseed（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useCrossseed.js（纯搬家）。
const {
  clearCrossseed,
  crossseedActing,
  crossseedBanned,
  crossseedData,
  crossseedGuard,
  crossseedLegacyCount,
  crossseedOpen,
  crossseedPending,
  crossseedPendingHandoff,
  crossseedSilentCount,
  crossseedSources,
  crossseedSourcesAll,
  crossseedStats,
  crossseedTimer,
  dropCrossseed,
  loadCrossseed,
  runCrossseedGuard,
  showCrossseed,
  unbanCrossseed,
} = useCrossseed({ api, notify })
// ── useCloud（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useCloud.js（纯搬家）。
const {
  cloudCfg,
  cloudLimit,
  cloudLoading,
  cloudOpen,
  cloudPlanItems,
  cloudPlanStats,
  cloudPlanning,
  cloudPollTimer,
  cloudRecordFor,
  cloudRunning,
  cloudState,
  cloudTestMsg,
  cloudTestOk,
  cloudTesting,
  cloudUploadingPath,
  loadCloud,
  openCloud,
  planCloud,
  runCloud,
  scheduleCloudPoll,
  testCloud,
  uploadCloudOne,
} = useCloud({ api, error, notify })
/** 保存目录候选：所有任务用过的目录（+ 设置里的默认）——“填一次就能选到”。 */
/** 静默托管：静默池按站点分类（分类卡片用）。 */
// 当前任务的运行状态（三态）；与运行时的状态徽章互不冲突

// 任务徽章：非「运行中」时直接显示运行状态；运行中则显示实时状态。
// 任务切换器菜单的副标题：站点 + 关键数字一行表达
// 统一分发：新增功能页只改 MF_PAGES + 这里加一行
function mfOpenPage(page) {
  switch (page.key) {
    case 'recommend': return openRecommend()
    case 'exam': return openExam()
    case 'signin': return openSignin()
    case 'cloud': return openCloud()
    case 'douban': return openDoubanService()
    case 'crossseed': return showCrossseed()
    case 'claim': return openClaim()
    case 'silent': return openSilent()
    case 'sitereport': return openSiteReport()
    case 'hrbills': return openHrBills()
    case 'ceiling': return openCeiling()
    case 'ops': return openOperations('all')
    case 'settings': return openSettings()
  }
}
// 已保存的隐藏集合（来自 /status）→ 顶栏/菜单/功能格据此显隐。保存后 loadStatus 刷新。
// ── useHeaderTiles（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useHeaderTiles.js（纯搬家）。
const {
  hiddenTiles,
  setTileShown,
  tileShown,
  tileVisible,
} = useHeaderTiles({ settingsDraft, status })
// 设置面板里的开关（draft 控件，保存后落盘）
// 操作记录作用域：'all' = 主页入口（跨任务 / 跨站点汇总）；'task' = 任务详情入口（当前任务）。
// ★ 主页是全局视角，绝不能把「单个任务」的流水摆在主页（既别扭又不合语义）。

// ── 手机端首页（任务列表）导航状态 ────────────────────────────────────────
// 桌面端无需该状态：相关显隐全部由 @media (max-width: 959px) 的 CSS 控制。
// 窄屏（手机/平板竖屏）：弹窗改为整页。数据驱动，只改这一处。
if (typeof window !== 'undefined') {
  const mq = window.matchMedia('(max-width: 959px)')
  const onChange = (e) => { isNarrow.value = e.matches }
  if (mq.addEventListener) mq.addEventListener('change', onChange)
  else if (mq.addListener) mq.addListener(onChange)
}
function toggleGroup(key) { mhOpen.value = { ...mhOpen.value, [key]: !mhOpen.value[key] } }
function openTaskMobile(id) { selectTask(id); mobileView.value = 'detail' }
function backToMobileList() { mobileView.value = 'list' }

// 首页分组：**按站点聚合**（同站多任务折叠为一行，时魔只算一次）→ 再按优先级分组
// 需要你管（有问题/待决策）> 在跑 > 不用管（已停用 / 静默托管）
function mhTaskRank(t) {
  if (t.attention) return 0
  if (t.builtin) return 3
  const c = taskBadge(t).color
  if (c === 'error' || c === 'warning') return 0
  const m = t.run_mode || 'running'
  return (m === 'seeding' || m === 'running') ? 1 : 2
}
const mobileHomeGroups = computed(() => {
  const sites = new Map()
  for (const t of tasks.value) {
    const key = t.builtin ? `#${t.id}` : (t.site_name || t.id)
    if (!sites.has(key)) sites.set(key, { key, site: t.site_name || t.name, builtin: !!t.builtin, tasks: [] })
    sites.get(key).tasks.push(t)
  }
  const list = [...sites.values()].map((s) => {
    s.tasks.sort((a, b) => mhTaskRank(a) - mhTaskRank(b))
    s.rank = Math.min(...s.tasks.map(mhTaskRank))
    const head = s.tasks[0]
    s.bonus = head.site_bonus_ok ? Number(head.site_bonus_per_hour || 0) : 0
    s.num = mobileRowNum(head)
    s.attention = s.tasks.map(x => x.attention).find(Boolean) || null
    // P4：手机首页视图字段（随 MobileHome 走 props 下发；子组件不使用 Function prop）
    s.multi = s.tasks.length > 1
    s.taskCount = s.tasks.length
    s.dotClass = `is-${s.attention ? s.attention.level : taskBadge(head).color}`
    s.statusText = s.attention ? s.attention.text : mobileRowLine(head)
    s.tasks = s.tasks.map((t) => ({ id: t.id, name: t.name, dotClass: `is-${taskBadge(t).color}`, num: mobileRowNum(t) }))
    return s
  })
  const byBonus = (a, b) => b.bonus - a.bonus
  const mk = (key, label, hint, pred) => ({ key, label, hint, sites: list.filter(pred).sort(byBonus) })
  const groups = [
    mk('need', '需要你管', '有问题或待决策', s => s.rank === 0),
    mk('live', '在跑', '正常养护中', s => s.rank === 1),
    mk('rest', '不用管', '已停用 / 静默托管', s => s.rank >= 2),
  ].filter(g => g.sites.length)
  groups.forEach(g => { g.count = g.sites.reduce((n, s) => n + s.tasks.length, 0) })
  return groups
})
// 手机首页「功能」格：MF_PAGES 去设置且按隐藏磁贴过滤（口径同旧模板内联表达式）
const mobileHomePages = computed(() => MF_PAGES.filter(item => item.key !== 'settings' && tileVisible(item.key)))
const mobileLiveCount = computed(() => {
  const set = new Set()
  for (const t of tasks.value) {
    if (t.builtin) continue
    // 只数「魔力站」（刷流任务的数字口径是上传量，不算进时魔总览）
    if (t.task_type === 'brush') continue
    const m = t.run_mode || 'running'
    if (m === 'seeding' || m === 'running') set.add(t.site_name || t.id)
  }
  return set.size
})
// 今日魔力增量（按站点去重后求和；各站增量可累加）
const mobileTodayGain = computed(() => {
  const by = new Map()
  for (const t of tasks.value) {
    if (t.bonus_day_delta == null) continue
    const k = t.site_name || t.id
    if (!by.has(k)) by.set(k, Number(t.bonus_day_delta) || 0)
  }
  let sum = 0
  for (const v of by.values()) sum += v
  return sum
})
// 站点容量：每站时魔 / 上限 / 占用（按站点去重，占用高的排前）
const siteCeilingRows = computed(() => {
  const by = new Map()
  for (const t of tasks.value) {
    if (t.builtin) continue
    const k = t.site_name || t.id
    const pct = Number(t.ceiling_pct || 0)
    const prev = by.get(k)
    if (!prev || pct > prev.pct) {
      by.set(k, {
        site: k,
        bonus: Number(t.site_bonus_per_hour || 0),
        ceiling: Number(t.site_ceiling || 0),
        pct,
        seeds: Number(t.seeding_count || 0),
      })
    }
  }
  return [...by.values()].sort((a, b) => b.pct - a.pct)
})
function openCeiling() { ceilingOpen.value = true }
// ── 站点报表（11.10.0）：站点级逐条种子状态（★ 两轴分级）─────────────────────
// ── useSiteReport（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useSiteReport.js（纯搬家）。
const {
  loadSiteReport,
  openSiteReport,
  siteReport,
  siteReportFilter,
  siteReportItems,
  siteReportLive,
  siteReportLoading,
  siteReportOpen,
  siteReportOrigin,
  siteReportSite,
  siteReportSites,
  siteReportSub,
  siteReportSummary,
  siteReportTransport,
} = useSiteReport({ api, error })
// ★ 两轴筛选：第一级=职务/身份桶、第二级=传输三态、静默桶再按身份子桶细分
// 传输三态计数：选中某桶时看该桶内三态（bucket_transport），否则看全局（by_transport）
// 明细副标题 = 列字段：传输 / 身份子桶 / qB 状态 / 债务 / 账单（不再当桶）
// ★ 11.11.0 H&R 账单按站
// ── useHrBills（P3 已抽）────────────────────────────────
// P4：H&R 账单弹窗已拆到 ./components/dialogs/HrBillsDialog.vue（props 下 / emit 上）。
const {
  hrBills,
  hrBillsLoading,
  hrBillsOpen,
  loadHrBills,
  openHrBills,
} = useHrBills({ api, error })
// 站点折叠：多任务行可展开
function toggleSite(key) { mhSiteOpen.value = { ...mhSiteOpen.value, [key]: !mhSiteOpen.value[key] } }
const mobileSilentCount = computed(() => tasks.value.find(t => t.builtin)?.seeding_count || 0)
// 列表行副标题：状态词 + 关键数
function mobileRowLine(t) {
  const parts = []
  const b = taskBadge(t)
  parts.push(b.text)
  if (t.seeding_count) parts.push(`${t.seeding_count} 种`)
  return parts.join(' · ')
}
// 列表行右侧主数：刷魔力任务给时魔（/h），刷流任务给上传量
function mobileRowNum(t) {
  if (t.task_type === 'brush') return t.task_uploaded ? `↑ ${formatBytes(t.task_uploaded)}` : ''
  if (t.site_bonus_ok && t.site_bonus_per_hour != null) return formatBonus(t.site_bonus_per_hour)
  return ''
}
function mobileDetailEntry(entry) {
  const e = typeof entry === 'string' ? { key: entry } : entry
  if (e.action === 'ops') return openOperations('task')
  activeTab.value = activeTab.value === e.key ? 'overview' : e.key
}
// mobileDetailCards / mobileStrategyText / mobileDetailHint 已随紧凑块搬入 components/MobileTaskDetail.vue（P4 拆分）。
// 「需要你管」：后端给的信号（出错 / 站点读不到 / 从未成功）
// 当前任务是否刷流模式（驱动整块工作台按类型显示）
// 站点账号真实数据（上传/下载/分享率/做种数，来自站点用户页）
// 刷流保种天数（缺省=2，兼容未写入该字段的旧任务）
// 当前任务的「任务目标」完成情况文案

// ★ 可观测：本轮决策轨迹（Why-not） + 每小时趋势序列（sparkline）

// 用最近窗口的最大值序列画 sparkline（单序列纯 SVG，无图表库依赖）

// 本轮抓取到的候选总数 = 通过数 + 各拦截原因数量



// 运行流程右上角阶段标签（预览图：阶段名 pill + 呼吸圆点，运行中闪烁）


// 全选（当前筛选结果）






/** 操作记录明细：展开状态表（key=operation_id）。 */

/** 可展开的明细条目：**所有类型都可展开**（Master 2026-10-01 18:10「操作记录要加详情」）。
 *  只有 run 记录第 0 项是汇总行（source=run），与上方摘要重复 → 过滤掉。 */
// ── 可观测④：结构化事件流（/events）──────────────────────────────


/** ★ 操作记录按类型筛选（Master 2026-10-01 18:10）。'' = 全部。 */





/** 明细行的短标签（来源/动作）。 */


/** ★ §4.1 辅种流水：把「辅种」类记录（kind=reseed，含历史 reuse/crossseed）摊平成一张表。 */
watch(opsView, (v) => {
  if (v === 'timeline') loadEventRows()
})

/** 操作记录的耗时文本（优先用后端记录，回退到创建/完成时间差）。 */

/** 操作记录的一行摘要（run 记录取结果文本）。 */




// 暂停 / 恢复按钮的口径：下载中的种子是「暂停下载 / 继续下载」，
// 已完成的才是「暂停做种 / 恢复做种」（避免下载中的种子出现「恢复做种」这种别扭文案）。



// 下载进度百分比（0~100），供进度条使用

// 托管种子状态分组（用于状态筛选）
// 覆盖 qBittorrent 全部常见状态，含 moving/allocating/checking*，避免出现
// 「分组里没这一档 → 只选中某个状态就再也看不到这些种子、各档数量之和 ≠ 总数」。

// 状态筛选选项（带数量）

// 加载插件总览与任务列表。

// 冷启动时后端先返回轻量壳（warming=true）并后台构建重数据；这里快速重拉几次直到就绪。

// 加载任务详情统计。

// 加载托管种子与魔力汇总。
// silent=true：已有数据时后台刷新，不置加载态（切换「托管」时秒显，避免 1~2 秒空白）。


// 加载候选种子（触发站点抓取，切换标签时按需加载）。

// ★ 类型筛选下推到服务端：选了类型就多拉（后端「先取大窗口再筛再截断」），
//   避免只在已加载的 100 条窗口里本地过滤导致深一点的历史被漏掉。

// 加载操作记录（单任务）。

// 加载操作记录（全局：最近 100 条，跨任务 / 跨站点；按类型筛选时拉 200 条）。


// 切换筛选类型 → 重新拉取（服务端已按类型深挖窗口）。
watch(opsKind, () => reloadOperations())

// 操作记录全局视图：task_id → 任务名（静默池是常驻伪任务，任务列表里没有它的条目）。

// ---- 推荐甄别（价值生命周期） ----
// ── 推荐（批量入库候选）──────────────────────────────────
// P3：状态 / 取数 / 排序去重 / 动作 已抽到 ./composables/useRecommend.js（纯搬家）；60s 定时器随域自管。
const {
  recommendData, recommendOpen, recommendActing, showAllRecs,
  recommendItems, hiddenRecCount, confirmedCount, pendingCount,
  recWorthShowing, recName, recommendActionable,
  loadRecommend, actRecommend, confirmRecommend, dismissRecommend, openRecommend,
} = useRecommend({ api, notify, error })







// ── 死种补源（rescue）：停滞欠 H&R 的种 → 他站「无 H&R」站补下同 Release ────────
// P3：状态 / 请求 / 动作已抽到 ./composables/useRescue.js（纯搬家，真值源仍在后端）
const {
  rescueOpen, rescueData, rescueScanning, rescueBusy, rescueBusyType,
  rescueTargets, rescueSkippedSites,
  loadRescue, openRescue, runRescueScan, runRescueApply,
} = useRescue({ api, notify, error })

// ── ★ 全站辅种（7.10.0）：本机已有资源 → 去各站挂种落户（零下载）──────────────
// P3：状态 / 请求 / 动作已抽到 ./composables/useReseed.js（纯搬家）；fmtTs → ./format.js
const {
  reseedState, reseedRunning, reseedSiteOptions,
  loadReseed, runReseed,
} = useReseed({ api, notify, settingsDraft, loadStatus, error })

// ── 豆瓣评分服务（magicflow-douban · 3.23.1）─────────────────────────
// P3：状态 / 请求 / 动作已抽到 ./composables/useDouban.js（纯搬家）
const {
  doubanServiceOpen, doubanServiceActing, doubanServiceData, doubanCrawl, doubanCrawlProgress,
  loadDoubanService, openDoubanService, doubanCrawlAction,
} = useDouban({ api })

// ── 健康自检（可观测③）：零外部请求，只看本地任务状态 + 趋势 ─────────
// P3：状态 / 请求 / 派生已抽到 ./composables/useHealth.js（纯搬家）
const {
  healthOpen, healthData, healthColor, healthBadgeCount, healthLabel,
  loadHealth, openHealth, healthGoto,
} = useHealth({ api, selectTask })

function fmtCount(n) {
  const v = Number(n || 0)
  if (v >= 10000) return `${(v / 10000).toFixed(1)} 万`
  return String(v)
}

// ── 点播（§1 权威来源 1 · 7.1.0）────────────────────────────────────
// P3：状态 / 请求 / 轮询生命周期已抽到 ./composables/useOndemand.js（纯搬家，真值源仍在后端）
const {
  ondemandOpen, ondemandQuery, ondemandTaskId, ondemandSiteIds, ondemandBusy,
  ondemandResult, ondemandError, ondemandCandidates,
  ondemandItems, ondemandItemsBusy, ondemandTab, odInflight, odHistory, odActing, odMsg,
  openOndemand, runOndemand, loadOndemandItems, actOndemand,
  odTraffic, odPct, odSpeed, odEtaText, odStageColor, odIsPaused, isOndemandAuto, fmtSizeGb,
} = useOndemand(api)

// ── 跨站辅种：队列 / 流量兜底（3.11.0）────────────────────────────────
// ★ 7.19.3：旧「回填」记录没有 来源站/目标站 信息 → 不在本页展示（历史信息见操作记录）
// ★ 已移交静默池的来源份（下完即移交，H&R 由静默池负责）
/** ★ 跨站取种（7.4.0 改版）：顶部三个核心数字 + 极简来源份卡片。 */

/** 大小文案（GB / TB）。 */
function gbText(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return '—'
  return n >= 1024 ? `${(n / 1024).toFixed(2)} TB` : `${n.toFixed(2)} GB`
}

/** 来源份保种状态徽章：绿=正常（义务已完成）· 黄=保种中 · 灰=保种期满可回收。 */






async function loadLive() {
  if (liveLoading.value) return
  const sid = Number(selectedTask.value?.site_id || 0)
  liveLoading.value = true
  try {
    liveState.value = unwrapResponse(await api.poolstats.live(sid)) || liveState.value
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

// ── 签到 / 模拟登录（借鉴 MoviePilot「站点自动签到」插件）──────────────────
//   另含原「签到报表页」整块（独立功能页）。P3：两块的 state/computed/动作已抽到
//   ./composables/useSignin.js（纯搬家）
const {
  siteSelectItems, signinRunning, runSigninNow, signinOpen, signinReport,
  signinReportLoading, loadSigninReport, openSignin, signinFilter, signinSearch,
  signinStatusText, signinDateLabel, signinReportTodayRows, signinTodayCounts, signinFilterItems,
  signinTodayList, signinKeepalive, signinKeepaliveNote, signinMatrix,
} = useSignin({ api, notify, status })
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



// ── 批量入库（Master 2026-09-28 07:00）────────────────────────────
// P3：勾选态 / 动作已抽到 ./composables/useRecImport.js（纯搬家）
const {
  recSelected, recBatchActing, recSelectable, recSelectedList, recAllChecked,
  toggleRec, toggleAllRecs, batchImportRecommend,
} = useRecImport({ api, notify, recommendItems, recommendActionable, loadRecommend })

// ── 新手考核（顶栏入口 + 汇总弹窗 + 一键起任务）────────────────────────
//   含原「板面重设」块（那块其实整块是考核域：站点排序 / 每项进度 / 同任务合并 / 警告前置）。
// P3：状态 / 派生 / 动作 / 定时器已抽到 ./composables/useExam.js（纯搬家）
const {
  examData, examOpen, examActing, examConfirm, examBadge,
  examUrgent, examShowPassed, examRows, examPendingSites, examNext,
  examUrgentWeek, examPendingItems, examDaysShort, examUrgencyColor, examPassedCount,
  examSitePct, examItemPct, examItemGap, examVisibleItems, examHiddenPassed,
  examTogglePassed, examActions, loadExam, openExam, examAct,
  examConfirmRun,
} = useExam({ api, notify, loadStatus })

// P4：汇总弹窗已拆到 ./components/dialogs/ExamDialog.vue —— 它需要的「状态 + 派生 + 只读回调」
// 整体作为 props.data 下传（子组件 reactive() 解包其中的 ref/computed；子不直接改父状态）。
const examDialogData = {
  examData, examUrgent, examRows, examPendingSites, examNext, examUrgentWeek, examPendingItems,
  examShowPassed, examActing, examDaysShort, examUrgencyColor, examPassedCount,
  examSitePct, examItemPct, examItemGap, examVisibleItems, examHiddenPassed,
  examTogglePassed, examActions, loadExam,
}
// P4：ExamDialog 的「一键起任务」emit → 打开二次确认弹窗（确认弹窗仍在 index.vue）
function onExamStart(payload) {
  examAct(payload.row, payload.kind)
}

// P4：运行诊断面板已拆到 ./components/tabs/JournalTab.vue —— 「状态 + 派生」整体作为 props.data 下传
// （reactive() 解包其中的 ref/computed）；类型筛选走 :scope + @update:scope，刷新/展开明细走 emit。
const journalTabData = {
  detail, detailStats, flowNodes, flowPhaseText,
  candidateData, candidateRawTotal, candidateLoadedAt, reasonEntries, maxReasonCount,
  opsFiltered, opsKindItems, expandedOps,
}

// ── 静默池（silent，7.16.0）：无主种池（跨站 / 跨任务）的全局视图 ────────────────
//   真值源 = 标签账本 tag_state（state=静默）+ 下载器快照；H&R 倒计时来自跨站来源份账本。
//   ★ 关系：跨站「下完」的来源份 → 移交静默池（跨站页只留未下完的列车）。
// P3：状态 / 过滤 / 拉取已抽到 ./composables/useSilentPool.js（纯搬家）
const {
  silentData, silentOpen, silentLoading, silentView, silentSub, silentSite, silentOnlyHr, silentQ,
  silentSummary, silentSites, silentSubs, silentRecords, silentItems,
  loadSilent, openSilent,
} = useSilentPool({ api, notify })
// P4：静默池弹窗已拆到 ./components/dialogs/SilentPoolDialog.vue —— 跨域动作（违背不变量 / 标签对账 /
//   操作记录）由子组件 emit 上来，在这层落到其它域的动作上。
function onSilentInvariant() {
  invariantOpen.value = true
  loadEnforce(0)
}

// ── 静默不变量收敛（★ 12.7.1）：账本静默但 qB 没停 → 补 pause（只 pause，不删种、不动文件）──
// P3：状态 / 动作已抽到 ./composables/useInvariant.js（纯搬家）；tsText → ./format.js
const {
  invariantOpen, enforceLoading, enforceAsk, enforceCounts,
  tagReconLoading, tagReconAsk, tagReconPending,
  runTagReconcile, loadEnforce,
} = useInvariant({ api, notify, loadSilent, silentOpen })

// ── 认领（claim，7.14.0）：把「我们在做种」的种在站点侧认领掉，换站点权益 ────────
//   ★ 写动作不可逆（不达标 −魔力 / 主动放弃 −更多）→ 默认干跑，真写要二次确认。
const claimData = ref({ sites: [], claimed: [], claimable: [], soon: [], cfg: {}, records: [] })
const claimOpen = ref(false)
const claimLoading = ref(false)
const claimActing = ref('')
const claimSiteFilter = ref(0)
const claimConfirm = ref(null)
const claimSites = computed(() => claimData.value.sites || [])
const claimCfg = computed(() => claimData.value.cfg || {})
const claimClaimable = computed(() => claimData.value.claimable || [])
const claimClaimed = computed(() => claimData.value.claimed || [])
const claimSoon = computed(() => claimData.value.soon || [])
const claimRecords = computed(() => claimData.value.records || [])
const claimSupportedSites = computed(() => claimSites.value.filter(s => s.supported))
const claimSiteOptions = computed(() => claimSupportedSites.value.map(s => s.domain).filter(Boolean))
async function loadClaim() {
  claimLoading.value = true
  try {
    const q = claimSiteFilter.value ? `?site_id=${claimSiteFilter.value}` : ''
    claimData.value = unwrapResponse(await api.features.claim(q)) || claimData.value
  } catch (err) {
    notify(`读取认领状态失败：${err?.message || err}`, 'error')
  } finally {
    claimLoading.value = false
  }
}
function openClaim() {
  claimOpen.value = true
  loadClaim()
}
async function claimScanRun() {
  if (claimActing.value) return
  claimActing.value = 'run'
  try {
    const res = unwrapResponse(await api.features.claimRun()) || {}
    notify(res.message || '已扫描')
    await loadClaim()
  } catch (err) {
    notify(`扫描失败：${err?.message || err}`, 'error')
  } finally {
    claimActing.value = ''
  }
}
function claimAsk(kind, row) {
  claimConfirm.value = { kind, row }
}
async function claimConfirmRun() {
  const ctx = claimConfirm.value
  if (!ctx || claimActing.value) return
  const row = ctx.row || {}
  claimActing.value = `${ctx.kind}:${row.hash || 'batch'}`
  try {
    let url = ''
    if (ctx.kind === 'batch') {
      const q = new URLSearchParams({ write: '1', confirm: '1' }).toString()
      url = `claim/run?${q}`
    } else if (ctx.kind === 'do') {
      const q = new URLSearchParams({ site_id: String(row.site_id), hash: String(row.hash), confirm: '1' }).toString()
      url = `claim/do?${q}`
    } else {
      const q = new URLSearchParams({ site_id: String(row.site_id), hash: String(row.hash), confirm: '1' }).toString()
      url = `claim/abandon?${q}`
    }
    const res = unwrapResponse(await api.post(url, {})) || {}
    notify(res.message || '已执行', res.success === false ? 'error' : undefined)
    claimConfirm.value = null
    await loadClaim()
  } catch (err) {
    notify(`执行失败：${err?.message || err}`, 'error')
  } finally {
    claimActing.value = ''
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
    unwrapResponse(await api.tasks.run(taskId))
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
      await api.tasks.setState(selectedTask.value.id, target),
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

// 打开编辑任务弹窗。

// 保存任务（新增或更新）。

// ── 删除任务：名下种子交棒 / 退回静默 ─────────────────────



// 确认删除当前任务。

// 提示文案随种子状态变化：下载中的是「暂停 / 继续下载」，已完成的才是「暂停 / 恢复做种」，
// 避免下载中的种子弹出「已恢复做种」这种说不通的提示。


// 删除种子需二次确认（避免手滑，删种不可逆）





// 复制 infohash

// 手机卡片上的勾选（对象引用与表格行一致）

// 打开发种详情弹窗

// 行点击：点到了操作按钮则不弹详情

// 在详情弹窗里操作，并在刷新后同步最新数据

// 打开插件设置弹窗。

// 各分类子页的「进页面即拉数据」链（openSettings 与目录下钻共用，别只改一处）。

// 设置分类「跳转」：目录页点分类 → 进入该分类表单页（手机端）。



// ── 标签模型 ─────────────────────────────────────────────
// P3：状态 / 动作已抽到 ./composables/useTagModel.js（纯搬家）
const {
  tagInfo, tagMigratePlan, tagMigrating, newRuleType, sortRuleTypeOptions,
  loadTags, sortRuleText, sortRuleNeedsMin, addSortRule, removeSortRule,
  previewTagMigrate, applyTagMigrate,
} = useTagModel({ api, notify, error, settingsDraft, emit })

// ── useSettings（P3 已抽）────────────────────────────────
// P3：状态 / 取数 / 动作 已抽到 ./composables/useSettings.js（纯搬家）。
const {
  applyRecommendedPrefs,
  backToSettingsDir,
  clearIyuuToken,
  defaultsDraft,
  defaultsLoading,
  downloaderPathsDraft,
  downloaderPrefsDraft,
  downloaderPrefsLoading,
  downloaderPrefsRaw,
  downloaderPrefsRecommended,
  iyuuLoading,
  iyuuShowMore,
  iyuuSites,
  iyuuStatus,
  iyuuTesting,
  loadDefaults,
  loadDownloaderPrefs,
  loadIyuuSites,
  loadRules,
  loadSettingsTabData,
  openSettings,
  openSettingsTab,
  probeRules,
  refreshRules,
  ruleSourceText,
  rulesLoading,
  rulesProbing,
  saveActiveSettings,
  saveCloud,
  saveDefaults,
  saveDownloaderAndPaths,
  saveDownloaderPaths,
  saveDownloaderPrefs,
  saveIyuu,
  savePathsTab,
  saveSettings,
  scrollSettingsNavToActive,
  setRuleHours,
  setRuleHr,
  setRuleRatio,
  settingsDialog,
  settingsNavEl,
  settingsPane,
  settingsTab,
  settingsTabLabel,
  siteRules,
  syncIyuuToDraft,
  testIyuu,
} = useSettings({ api, error, notify, emit, saving, loadStatus, settingsDraft, isNarrow, loadFallback, loadCloud, testCloud, loadTags, loadReseed })

// P4：把设置导航栏 DOM 交回 useSettings（其自动滚动 watcher 依赖此 ref）。
function setSettingsNavEl(el) { settingsNavEl.value = el }

// ── 云盘归档 ─────────────────────────────────────────────




// 上传/归档是后台跑的：轮询到没有 uploading / running 就自动停。




// ── 元数据兜底 ─────────────────────────────────────────────
// 可选来源（与后端 MediaSource 对齐）；顺序可调，识别时按顺序回退。







// 加载 IYUU 站点表（按 MoviePilot 已配置站点生成）。




// ★ 15.6.0：站点级完成度阈值（留空 = 跟全局默认）




// 把站点密钥表写回 settingsDraft（保存前调用）。

// 测试 IYUU Token。

// 清空已存的 IYUU Token（后端「空值=保持原值」，所以清空要显式带 iyuu_clear）。

// 保存 IYUU 设置（Token + 站点密钥表）。

// 加载下载器全局参数。

// 把下载器参数恢复为推荐值（仅填表，点保存才写入）。

// 保存下载器全局参数。

// 保存下载目录。

// 加载默认任务模板。

// 保存默认任务模板。

// 保存当前设置标签页。

// 保存「云盘归档」设置：保存后立刻回读配置 + 自检一次，避免「存了但没生效」。

// 保存「下载与目录」标签：qBittorrent 全局参数 + 全局路径 + 任务保存目录（一次存齐）。

// 保存「下载目录」标签：qBittorrent 全局路径 + 任务保存目录（默认模板）。

// 保存全局设置。

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
  // 豆瓣评分服务（库容量 + 慢爬进度，低频刷）
  loadDoubanService()
  doubanServiceTimer = window.setInterval(loadDoubanService, 60000)
  healthTimer = window.setInterval(loadHealth, 60000)
  loadHealth()
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
  if (doubanServiceTimer) window.clearInterval(doubanServiceTimer)
  if (healthTimer) window.clearInterval(healthTimer)
  if (liveTimer) window.clearInterval(liveTimer)
  if (warmingTimer) window.clearTimeout(warmingTimer)
  if (ondemandItemsTimer) window.clearInterval(ondemandItemsTimer)
})
</script>

<template>
  <div
    class="magicflow-page"
    :class="{
      'magicflow-page--compact': compact || status.compact_mode,
      'magicflow-page--m-list': mobileView === 'list',
      'magicflow-page--m-detail': mobileView === 'detail',
    }"
  >
    <WorkbenchHeader
      :tasks="tasks"
      :selected-task="selectedTask"
      :selected-task-id="selectedTaskId"
      :selected-state="selectedState"
      :task-site-icon="taskSiteIcon"
      :summary="summary"
      :hidden-tiles="hiddenTiles"
      :recommend-data="recommendData"
      :crossseed-data="crossseedData"
      :douban-service-data="doubanServiceData"
      :health-data="healthData"
      :health-color="healthColor"
      :health-label="healthLabel"
      :health-badge-count="healthBadgeCount"
      :exam-data="examData"
      :exam-badge="examBadge"
      :exam-urgent="examUrgent"
      :show-close="showClose"
      :task-badge="taskBadge"
      :task-switch-subtitle="taskSwitchSubtitle"
      @select-task="selectTask"
      @open-create-task="openCreateTask"
      @open-recommend="openRecommend"
      @open-cloud="openCloud"
      @open-crossseed="showCrossseed"
      @open-douban="openDoubanService"
      @open-health="openHealth"
      @open-ondemand="openOndemand"
      @open-exam="openExam"
      @open-rescue="openRescue"
      @open-sitereport="openSiteReport"
      @open-music="openMusic"
      @open-settings="openSettings"
      @close="emit('close')"
    />

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
        <VBtn class="magicflow-mobile-back" icon="mdi-arrow-left" variant="text" aria-label="返回列表" @click="backToMobileList" />
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
              :subtitle="taskSwitchSubtitle(task)"
              :active="task.id === selectedTaskId"
              lines="two"
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

      <!-- ★ 手机端首页：任务列表（列表优先；详情是第二层）。桌面端由 CSS 隐藏。 -->
      <div class="magicflow-mobile-home">
        <MobileHome
          :groups="mobileHomeGroups"
          :summary="summary"
          :open="mhOpen"
          :open-sites="mhSiteOpen"
          :live-count="mobileLiveCount"
          :today-gain="mobileTodayGain"
          :pages="mobileHomePages"
          @toggle-group="toggleGroup"
          @toggle-site="toggleSite"
          @open-task="openTaskMobile"
          @open-ceiling="openCeiling"
          @open-page="mfOpenPage"
          @create-task="openCreateTask"
          @open-settings="openSettings"
        />
      </div>

      <div class="magicflow-layout">
        <VSheet tag="aside" class="magicflow-task-rail app-surface-static">
          <TaskPane :tasks="tasks" :selected-id="selectedTaskId" @select="selectTask" @new="openCreateTask" />
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
                  <VChip v-if="selectedTask.builtin" size="small" variant="tonal" color="primary" prepend-icon="mdi-access-point">常驻</VChip>
                  <VChip v-else size="small" variant="tonal" :color="selectedTask.task_type === 'brush' ? 'info' : 'primary'" :prepend-icon="selectedTask.task_type === 'brush' ? 'mdi-upload-network-outline' : 'mdi-star-four-points-outline'">
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
              <VMenu v-if="!selectedTask.builtin" location="bottom end">
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
              <VTooltip v-if="!selectedTask.builtin" text="编辑任务">
                <template #activator="{ props: tipProps }">
                  <VBtn v-bind="tipProps" icon="mdi-pencil-outline" variant="text" @click="openEditTask" />
                </template>
              </VTooltip>
              <VTooltip v-if="!selectedTask.builtin" text="删除任务">
                <template #activator="{ props: tipProps }">
                  <VBtn v-bind="tipProps" icon="mdi-delete-outline" variant="text" color="error" @click="deleteDialog = true" />
                </template>
              </VTooltip>
            </div>
          </section>

          <template v-if="!selectedTask.builtin">
          <!-- ★ 手机端任务详情紧凑块（结论 + 三个数 + 策略一行 + 次级入口）；桌面端 CSS 隐藏 -->
          <div class="magicflow-mobile-detail">
            <MobileTaskDetail
              :task="selectedTask"
              :state="selectedState"
              :attention="detailAttention"
              :stats="detailStats"
              :config="taskConfig"
              :site-account="siteAccount"
              :active-tab="activeTab"
              @entry="mobileDetailEntry"
              @navigate="activeTab = $event"
            />
          </div>

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
<VWindowItem value="overview" class="magicflow-window-ov">
              <OverviewTab
                :selected-task="selectedTask"
                :task-is-brush="taskIsBrush"
                :task-config="taskConfig"
                :brush-seed-days="brushSeedDays"
                :goal-fact-text="goalFactText"
                :selected-state="selectedState"
                :detail-stats="detailStats"
                :site-account="siteAccount"
                :site-user="siteUser"
                :site-live-level="siteLiveLevel"
                :site-live-rates="siteLiveRates"
                :site-live-cfg="siteLiveCfg"
                :site-live-alerts="siteLiveAlerts"
                :decision="decision"
                :decision-cap-text="decisionCapText"
                :decision-reasons="decisionReasons"
                :trend-cards="trendCards"
                @open-entry="activeTab = $event"
              />
            </VWindowItem>

            <VWindowItem value="diagnostics">
              <JournalTab
                :data="journalTabData"
                :scope="opsKind"
                :task="selectedTask"
                @update:scope="v => (opsKind = v)"
                @refresh="loadOperations(selectedTaskId)"
                @toggle-detail="toggleOpDetail"
              />
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

              <CandidatesTab v-if="poolView === 'candidates'" :data="candidateData" :task-is-brush="taskIsBrush" />
              <SeedingTab
                v-else
                v-model:filter="torrentFilter"
                v-model:status-filter="torrentStatusFilter"
                :rows="sortedTorrents"
                :headers="torrentHeaders"
                :status-options="torrentStatusOptions"
                :selected-hashes="selectedHashes"
                :all-selected="allFilteredSelected"
                :loading="taskLoading"
                :busy="batchBusy"
                :task="selectedTask"
                @batch="batchAction"
                @transfer="openTransfer"
                @batch-delete="batchDeleteDialog = true"
                @select-all="selectAllFiltered"
                @clear-selection="clearSelection"
                @toggle-row="toggleTorrentSelection"
                @row-click="onTorrentRowClick"
                @torrent-action="torrentAction"
                @delete="requestTorrentDelete"
                @open-detail="openTorrentDetail"
              />
            </VWindowItem>

            <VWindowItem value="config">
              <TaskConfigTab
                :task="selectedTask"
                :config="taskConfig"
                :run-mode="selectedRunMode"
                :goal-text="goalFactText"
                :is-brush="taskIsBrush"
                :brush-seed-days="brushSeedDays"
                :saving="saving"
                @run="runOperation"
                @edit="openEditTask"
                @delete="deleteDialog = true"
              />
            </VWindowItem>

          </VWindow>
          </template>
          <template v-else>
            <VSheet class="magicflow-panel app-surface-static" style="margin-top:16px;">
              <header class="magicflow-panel__head">
                <div>
                  <div class="text-subtitle-1 font-weight-medium">静默托管 · 常驻 worker</div>
                  <div class="text-body-2 text-medium-emphasis">静默池的负责人：清理未下完 / 保挂（恢复做种）/ H&R 统一管理 / 辅种校验 / 分拣，低频自动运行</div>
                </div>
                <VChip color="primary" size="small" variant="tonal" prepend-icon="mdi-access-point">常驻</VChip>
              </header>
              <div class="magicflow-stat-grid">
                <VSheet class="magicflow-stat app-surface-static">
                  <strong>{{ selectedTask.seeding_count || 0 }}</strong>
                  <span>静默池种子 · 其中隔离区（欠 H&R 工时）{{ selectedTask.hr_count || 0 }} / 其他 {{ selectedTask.nonhr_count || 0 }}</span>
                </VSheet>
                <VSheet class="magicflow-stat app-surface-static">
                  <strong>{{ selectedTask.host_interval_minutes || 60 }} 分钟</strong>
                  <span>托管周期 · silent_host_interval_minutes 可调</span>
                </VSheet>
                <VSheet class="magicflow-stat app-surface-static">
                  <strong>{{ selectedTask.host_last_run || '—' }}</strong>
                  <span>上次运行</span>
                </VSheet>
              </div>
              <VSheet tag="section" class="magicflow-panel app-surface-static mt-4">
                <header class="magicflow-panel__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">分类</div>
                    <div class="text-body-2 text-medium-emphasis">静默池按子类 / 义务 / 站点拆分（职责说明见仓库 docs/静默托管.md）</div>
                  </div>
                </header>
                <div class="d-flex flex-wrap ga-2 mb-2">
                  <VChip size="small" variant="tonal" color="info">静默-新 {{ (selectedTask.classify && selectedTask.classify.by_state && selectedTask.classify.by_state['新']) || 0 }}</VChip>
                  <VChip size="small" variant="tonal" color="success">静默-资源 {{ (selectedTask.classify && selectedTask.classify.by_state && selectedTask.classify.by_state['资源']) || 0 }}</VChip>
                  <VChip size="small" variant="tonal">静默-普通 {{ (selectedTask.classify && selectedTask.classify.by_state && selectedTask.classify.by_state['普通']) || 0 }}</VChip>
                  <VChip size="small" variant="tonal" color="error">隔离区（欠 H&R 工时）{{ selectedTask.hr_count || 0 }}</VChip>
                  <VChip size="small" variant="tonal">其他 {{ selectedTask.nonhr_count || 0 }}</VChip>
                </div>
                <div v-if="silentHostSites.length" class="text-body-2 text-medium-emphasis">
                  <span v-for="(row, i) in silentHostSites" :key="row.name">{{ i ? '  ·  ' : '' }}{{ row.name }} {{ row.total }}<template v-if="row.hr">（隔离 {{ row.hr }}）</template></span>
                </div>
              </VSheet>

              <VSheet tag="section" class="magicflow-panel app-surface-static mt-4">
                <header class="magicflow-panel__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">操作记录</div>
                    <div class="text-body-2 text-medium-emphasis">每次运行一条流水（展开看九步结果）</div>
                  </div>
                  <VBtn variant="text" color="primary" prepend-icon="mdi-refresh" @click="loadOperations(selectedTaskId)">刷新</VBtn>
                </header>
                <div class="magicflow-ops-filter">
                  <span class="magicflow-ops-filter__label">类型</span>
                  <VSelect
                    v-model="opsKind"
                    :items="opsKindItems"
                    item-title="label"
                    item-value="value"
                    density="compact"
                    variant="outlined"
                    hide-details
                    class="magicflow-ops-filter__select"
                  ></VSelect>
                </div>
                <div class="magicflow-events">
                  <article v-for="record in opsFiltered" :key="record.operation_id">
                    <VIcon :icon="operationIcon(record.kind)" :color="operationColor(record)" />
                    <div>
                      <strong>
                        {{ operationKindText(record.kind) }}
                        <VChip size="x-small" variant="tonal" :color="operationColor(record)" class="ml-2">{{ operationStateText(record.state) }}</VChip>
                      </strong>
                      <span>{{ operationSummary(record) }}</span>
                      <span>{{ formatDateTime(record.created_at) }} · 耗时 {{ operationDuration(record) }}<template v-if="hasOpDetail(record)"> · {{ opDetailItems(record).length }} 条明细</template></span>
                      <span v-if="record.error_message" class="text-error">{{ record.error_message }}</span>
                      <button v-if="hasOpDetail(record)" type="button" class="magicflow-events__toggle" @click="toggleOpDetail(record.operation_id)">
                        {{ isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细' }}
                        <VIcon :icon="isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="14" />
                      </button>
                      <ul v-if="isOpDetailOpen(record.operation_id)" class="magicflow-events__detail">
                  <li v-for="(it, idx) in opDetailItems(record)" :key="idx">
                    <span class="magicflow-events__detail-line">
                      <em v-if="itemSourceText(it.source)" class="magicflow-events__detail-src">{{ itemSourceText(it.source) }}</em>
                      <span class="magicflow-events__detail-title" :title="it.title || it.hash">{{ it.title || it.hash || '—' }}</span>
                      <code v-if="it.hash" class="magicflow-events__detail-hash">{{ String(it.hash).slice(0, 12) }}</code>
                    </span>
                    <span class="magicflow-events__detail-sub">
                      <template v-if="it.reason">{{ it.reason }}</template>
                      <template v-if="it.size_gb"> · {{ Number(it.size_gb).toFixed(2) }}G</template>
                      <template v-if="it.seeders"> · 做种 {{ it.seeders }}</template>
                      <template v-if="it.tags"> · {{ it.tags }}</template>
                      <template v-if="it.bonus_per_hour"> · {{ Number(it.bonus_per_hour).toFixed(2) }}/h</template>
                    </span>
                  </li>
                </ul>
                    </div>
                  </article>
                  <div v-if="!opsFiltered.length" class="magicflow-table-empty">暂无操作记录</div>
                </div>
              </VSheet>
              <div style="margin-top:14px;display:flex;gap:8px;">
                <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-sync" :loading="saving" @click="runOperation">立即执行</VBtn>
                <VBtn size="small" variant="text" prepend-icon="mdi-refresh" @click="reloadSelected()">刷新</VBtn>
              </div>
            </VSheet>
          </template>
        </main>
      </div>
    </template>

    <!-- P4：站点容量/魔力一览弹窗已抽到 ./components/dialogs/CeilingDialog.vue（props 下 / emit 上） -->
    <CeilingDialog v-model="ceilingOpen" :rows="siteCeilingRows" :narrow="isNarrow" />

    <!-- P4：站点报表弹窗已抽到 ./components/dialogs/SiteReportDialog.vue（props 下 / emit 上） -->
    <SiteReportDialog
      v-model="siteReportOpen"
      v-model:site="siteReportSite"
      v-model:filter="siteReportFilter"
      v-model:transport="siteReportTransport"
      v-model:sub="siteReportSub"
      v-model:origin="siteReportOrigin"
      :loading="siteReportLoading"
      :live="siteReportLive"
      :report="siteReport"
      :sites="siteReportSites"
      :items="siteReportItems"
      :summary="siteReportSummary"
      :narrow="isNarrow"
      @refresh="loadSiteReport(false)"
      @live="loadSiteReport(true)"
      @change="loadSiteReport()"
    />

    <!-- ★ P4：H&R 账单（自有组件；props 下 / emit 上） -->
    <HrBillsDialog
      v-model="hrBillsOpen"
      :data="hrBills"
      :loading="hrBillsLoading"
      :narrow="isNarrow"
      @refresh="loadHrBills(false)"
    />

    <!-- P4：签到弹窗已拆到 ./components/dialogs/SigninDialog.vue（props 下 / emit 上） -->
    <SigninDialog
      v-model="signinOpen"
      v-model:signinFilter="signinFilter"
      v-model:signinSearch="signinSearch"
      :signin-report="signinReport"
      :signin-report-loading="signinReportLoading"
      :signin-report-today-rows="signinReportTodayRows"
      :signin-today-counts="signinTodayCounts"
      :signin-running="signinRunning"
      :signin-keepalive="signinKeepalive"
      :signin-keepalive-note="signinKeepaliveNote"
      :signin-filter-items="signinFilterItems"
      :signin-today-list="signinTodayList"
      :signin-matrix="signinMatrix"
      :narrow="isNarrow"
      @refresh="loadSigninReport"
      @run="runSigninNow"
      @settings="openSettings('signin')"
    />

    <!-- P4：操作记录弹窗已拆到 ./components/dialogs/OpsDialog.vue（props 下 / emit 上） -->
    <OpsDialog
      v-model="opsOpen"
      v-model:view="opsView"
      v-model:kind="opsKind"
      v-model:eventLevel="eventLevel"
      :scope="opsScope"
      :loading-all="opsLoadingAll"
      :selected-task="selectedTask"
      :event-rows="eventRows"
      :events-loading="eventsLoading"
      :ops-kind-items="opsKindItems"
      :reseed-rows="reseedRows"
      :ops-filtered="opsFiltered"
      :expanded-ops="expandedOps"
      :tasks="tasks"
      :narrow="isNarrow"
      @refresh-all="loadOperationsAll"
      @refresh-task="loadOperations(selectedTaskId)"
      @toggle-detail="toggleOpDetail"
    />

    <TaskEditorDialog
      v-model="editorOpen"
      :task="editorTask"
      :sites="status.options.sites"
      :downloaders="status.options.downloaders"
      :default-save-path="defaultSavePath"
      :save-paths="recentSavePaths"
      :saving="saving"
      :api="api"
      :plugin-base="pluginBase"
      @save="saveTask"
    />

    <!-- 设置弹窗（多标签）→ P4 已拆到 ./components/dialogs/SettingsDialog.vue（props 下 / emit 上） -->
    <SettingsDialog
      v-model="settingsDialog"
      v-model:settings-tab="settingsTab"
      v-model:fallback-source-draft="fallbackSourceDraft"
      v-model:new-rule-type="newRuleType"
      :set-nav-el="setSettingsNavEl"
      :is-narrow="isNarrow"
      :settings-pane="settingsPane"
      :status="status"
      :selected-task="selectedTask"
      :saving="saving"
      :settings-draft="settingsDraft"
      :downloader-prefs-draft="downloaderPrefsDraft"
      :downloader-paths-draft="downloaderPathsDraft"
      :defaults-draft="defaultsDraft"
      :downloader-prefs-recommended="downloaderPrefsRecommended"
      :iyuu-sites="iyuuSites"
      :iyuu-loading="iyuuLoading"
      :iyuu-status="iyuuStatus"
      :iyuu-testing="iyuuTesting"
      :iyuu-show-more="iyuuShowMore"
      :site-rules="siteRules"
      :rules-loading="rulesLoading"
      :rules-probing="rulesProbing"
      :reseed-state="reseedState"
      :reseed-running="reseedRunning"
      :reseed-site-options="reseedSiteOptions"
      :claim-site-options="claimSiteOptions"
      :site-select-items="siteSelectItems"
      :site-live-alerts="siteLiveAlerts"
      :tag-info="tagInfo"
      :tag-migrate-plan="tagMigratePlan"
      :tag-migrating="tagMigrating"
      :fallback-state="fallbackState"
      :fallback-loading="fallbackLoading"
      :fallback-running="fallbackRunning"
      :fallback-problem-shows="fallbackProblemShows"
      :fallback-problem-count="fallbackProblemCount"
      :used-fallback-sources="usedFallbackSources"
      :unused-fallback-sources="unusedFallbackSources"
      :cloud-cfg="cloudCfg"
      :cloud-test-msg="cloudTestMsg"
      :cloud-test-ok="cloudTestOk"
      :cloud-testing="cloudTesting"
      :tile-shown="tileShown"
      @open-tab="openSettingsTab"
      @back-to-dir="backToSettingsDir"
      @save="saveActiveSettings"
      @apply-recommended="applyRecommendedPrefs"
      @test-iyuu="testIyuu"
      @clear-iyuu="clearIyuuToken"
      @probe-rules="probeRules"
      @refresh-rules="refreshRules"
      @set-rule-hr="setRuleHr"
      @set-rule-hours="setRuleHours"
      @set-rule-ratio="setRuleRatio"
      @open-claim="openClaim"
      @open-signin="openSignin"
      @run-fallback="runFallback"
      @run-reseed="runReseed"
      @load-reseed="loadReseed"
      @load-fallback="loadFallback"
      @add-fallback-source="addFallbackSource"
      @move-fallback-source="moveFallbackSource"
      @remove-fallback-source="removeFallbackSource"
      @set-tile-shown="setTileShown"
      @add-sort-rule="addSortRule"
      @remove-sort-rule="removeSortRule"
      @preview-tag-migrate="previewTagMigrate"
      @apply-tag-migrate="applyTagMigrate"
      @test-cloud="testCloud"
    />

    <TorrentDialog
      v-model="torrentDialog"
      :torrent="activeTorrent"
      :task="selectedTask"
      :saving="saving"
      :narrow="isNarrow"
      @copy-hash="copyTorrentHash"
      @action="detailTorrentAction"
      @delete="requestTorrentDelete"
    />

    <!-- P4：批量转移确认弹窗已拆到 ./components/confirm/TransferConfirm.vue（props 下 / emit 上） -->
    <TransferConfirm
      v-model="transferDialog"
      v-model:target="transferTarget"
      :selected-hashes="selectedHashes"
      :choices="transferChoices"
      :busy="batchBusy"
      @confirm="confirmTransfer"
    />

    <!-- P4：批量删除确认弹窗已抽到 ./components/confirm/BatchDeleteConfirm.vue（props 下 / emit 上） -->
    <BatchDeleteConfirm
      v-model="batchDeleteDialog"
      :selected-hashes="selectedHashes"
      :selected-task="selectedTask"
      :batch-busy="batchBusy"
      @delete="batchAction('delete')"
    />

    <!-- P4：单种删除确认弹窗已抽到 ./components/confirm/TorrentDeleteConfirm.vue（props 下 / emit 上） -->
    <TorrentDeleteConfirm
      v-model="torrentDeleteDialog"
      :pending-torrent-delete="pendingTorrentDelete"
      :selected-task="selectedTask"
      :saving="saving"
      @confirm="confirmTorrentDelete"
    />

    <!-- P4：删除任务确认弹窗已拆到 ./components/confirm/DeleteTaskConfirm.vue（props 下 / emit 上） -->
    <DeleteTaskConfirm
      v-model="deleteDialog"
      v-model:target="handoverTarget"
      :selected-task="selectedTask"
      :handover-loading="handoverLoading"
      :handover="handover"
      :handover-choices="handoverChoices"
      :saving="saving"
      @update:model-value="onDeleteDialog"
      @confirm="confirmDeleteTask"
    />

    <!-- P4：云盘归档弹窗已拆到 ./components/dialogs/CloudDialog.vue（props 下 / emit 上） -->
    <CloudDialog
      v-model="cloudOpen"
      v-model:limit="cloudLimit"
      :state="{ loading: cloudLoading, planning: cloudPlanning, running: cloudRunning, testing: cloudTesting, testMsg: cloudTestMsg, testOk: cloudTestOk, uploadingPath: cloudUploadingPath, planItems: cloudPlanItems, planStats: cloudPlanStats, data: cloudState }"
      :narrow="isNarrow"
      @refresh="loadCloud"
      @plan="planCloud"
      @run="runCloud"
      @test="testCloud"
      @upload="uploadCloudOne"
    />

<!-- 跨站辅种：队列 + 流量兜底（3.11.0） -->
    <!-- P4：点播弹窗已拆到 ./components/dialogs/OndemandDialog.vue（props 下 / emit 上） -->
    <OndemandDialog
      v-model="ondemandOpen"
      v-model:query="ondemandQuery"
      v-model:site-ids="ondemandSiteIds"
      v-model:task-id="ondemandTaskId"
      v-model:tab="ondemandTab"
      v-model:msg="odMsg"
      :ondemand-result="ondemandResult"
      :ondemand-candidates="ondemandCandidates"
      :od-inflight="odInflight"
      :od-history="odHistory"
      :od-acting="odActing"
      :ondemand-busy="ondemandBusy"
      :ondemand-error="ondemandError"
      :ondemand-items-busy="ondemandItemsBusy"
      :site-select-items="siteSelectItems"
      :tasks="tasks"
      :is-ondemand-auto="isOndemandAuto"
      @run="runOndemand"
      @refresh-items="loadOndemandItems"
      @act="actOndemand"
    />

    <!-- P4：站点健康弹窗已拆到 ./components/dialogs/HealthDialog.vue（props 下 / emit 上） -->
    <HealthDialog
      v-model="healthOpen"
      :data="healthData"
      :color="healthColor"
      :label="healthLabel"
      :narrow="isNarrow"
      @goto="healthGoto"
    />

    <DoubanDialog
      v-model="doubanServiceOpen"
      :state="{ data: doubanServiceData, crawl: doubanCrawl, progress: doubanCrawlProgress, acting: doubanServiceActing }"
      :narrow="isNarrow"
      @refresh="loadDoubanService"
      @start="doubanCrawlAction"
    />

    <!-- P4：跨站取种弹窗已拆到 ./components/dialogs/CrossseedDialog.vue（props 下 / emit 上） -->
    <CrossseedDialog
      v-model="crossseedOpen"
      :state="{
        data: crossseedData,
        stats: crossseedStats,
        silentCount: crossseedSilentCount,
        guard: crossseedGuard,
        banned: crossseedBanned,
        pending: crossseedPending,
        sources: crossseedSources,
        legacyCount: crossseedLegacyCount,
        pendingHandoff: crossseedPendingHandoff,
        acting: crossseedActing,
      }"
      :gb-text="gbText"
      :narrow="isNarrow"
      @refresh="loadCrossseed"
      @guard="runCrossseedGuard"
      @unban="unbanCrossseed"
      @clear="clearCrossseed"
      @drop="dropCrossseed"
      @operations="openOperations('all')"
      @silent="openSilent()"
    />

    <!-- 死种补源 → P4 已拆到 ./components/dialogs/RescueDialog.vue（props 下 / emit 上） -->
    <RescueDialog
      v-model="rescueOpen"
      :data="rescueData"
      :scanning="rescueScanning"
      :busy="rescueBusy"
      :busy-type="rescueBusyType"
      :targets="rescueTargets"
      :skipped-sites="rescueSkippedSites"
      :narrow="isNarrow"
      @refresh="runRescueScan"
      @apply="runRescueApply"
    />

    <!-- 推荐甄别（价值生命周期）→ P4 已拆到 ./components/dialogs/RecommendDialog.vue（props 下 / emit 上） -->
    <RecommendDialog
      v-model="recommendOpen"
      v-model:showAllRecs="showAllRecs"
      :data="recommendData"
      :items="recommendItems"
      :acting="recommendActing"
      :hidden="hiddenRecCount"
      :confirmed="confirmedCount"
      :pending="pendingCount"
      :selected="recSelected"
      :selectable="recSelectable"
      :selected-list="recSelectedList"
      :all-checked="recAllChecked"
      :batch-acting="recBatchActing"
      :narrow="isNarrow"
      @refresh="loadRecommend"
      @confirm="confirmRecommend"
      @dismiss="dismissRecommend"
      @toggle-rec="toggleRec"
      @toggle-all="toggleAllRecs"
      @batch-import="batchImportRecommend"
    />

    <!-- ★ 15.8.2：音乐甄别（歌单 → 选种计划 → 一键加种） -->
    <MusicDialog
      v-model="musicOpen"
      v-model:text="musicText"
      v-model:sites="musicSites"
      v-model:savePath="musicSavePath"
      v-model:error="musicError"
      :result="musicResult"
      :acting="musicActing"
      :grab-report="musicGrabReport"
      :narrow="isNarrow"
      @plan="loadMusicPlan"
      @grab="runMusicGrab"
      @reset="musicResetResult"
    />

    <!-- 新手考核：汇总弹窗（Layout A，同「推荐」范式）→ P4 已拆到 ExamDialog.vue -->
    <ExamDialog
      v-model="examOpen"
      :data="examDialogData"
      :narrow="isNarrow"
      @start="onExamStart"
    />

    <!-- 一键起任务确认（先展示要干什么，再动手）→ P4 已拆到 ./components/confirm/ExamConfirm.vue（props 下 / emit 上） -->
    <ExamConfirm v-model="examConfirm" :acting="examActing" @run="examConfirmRun" />
    <ClaimDialog
      v-model="claimOpen"
      :is-narrow="isNarrow"
      :claim-data="claimData"
      :claim-cfg="claimCfg"
      :claim-sites="claimSites"
      :claim-supported-sites="claimSupportedSites"
      :claim-claimable="claimClaimable"
      :claim-claimed="claimClaimed"
      :claim-soon="claimSoon"
      :claim-loading="claimLoading"
      :claim-acting="claimActing"
      @refresh="loadClaim"
      @scan="claimScanRun"
      @ask="claimAsk"
    />

    <!-- ★ P4：静默池全局视图（自有组件；props 下 / emit 上） -->
    <SilentPoolDialog
      v-model="silentOpen"
      v-model:view="silentView"
      v-model:sub="silentSub"
      v-model:site="silentSite"
      v-model:onlyHr="silentOnlyHr"
      v-model:q="silentQ"
      :data="silentData"
      :summary="silentSummary"
      :subs="silentSubs"
      :sites="silentSites"
      :items="silentItems"
      :records="silentRecords"
      :loading="silentLoading"
      :narrow="isNarrow"
      :tag-recon-loading="tagReconLoading"
      :gb-text="gbText"
      @refresh="loadSilent"
      @operations="openOperations('all')"
      @invariant="onSilentInvariant"
      @tag-reconcile="runTagReconcile(false)"
    />

    <!-- 认领二次确认（写动作不可逆）★ P4：自有组件（props 下 / emit 上）——原「认领二次确认」弹窗。
         认领真值（claimConfirm）由父页持有 → v-model；「确认」→ @run（父 claimConfirmRun）。 -->
    <ClaimConfirm
      v-model="claimConfirm"
      :cfg="claimCfg"
      :acting="!!claimActing"
      @run="claimConfirmRun"
    />
    <!-- ★ P4：静默池「不变量收敛」（自有组件；props 下 / emit 上）——原「静默池 · 不变量收敛」弹窗。
         刷新 / 查违背不变量 → @load-enforce（loadEnforce(0)）；「补暂停」→ @suppress（打开二次确认弹窗）。 -->
    <InvariantDialog
      v-model="invariantOpen"
      :loading="enforceLoading"
      :counts="enforceCounts"
      :narrow="isNarrow"
      @load-enforce="loadEnforce(0)"
      @suppress="enforceAsk = true"
    />

    <!-- ★ P4：补暂停二次确认（自有组件；props 下 / emit 上）——原「补暂停二次确认」弹窗（★ 12.7.1：只 pause，不删种）。
         「取消」→ 组件内 open = false；「确认补暂停」→ @run（父页原确认处理器：关弹窗 + loadEnforce(1)）。 -->
    <EnforceConfirm
      v-model="enforceAsk"
      :loading="enforceLoading"
      :counts="enforceCounts"
      @run="enforceAsk = false; loadEnforce(1)"
    />

    <!-- ★ 15.2.0 标签对账 二次确认（只补 qB 标签，不改账本、不删不暂停）→ P4 已拆到 ./components/confirm/TagReconConfirm.vue（props 下 / emit 上） -->
    <TagReconConfirm
      v-model="tagReconAsk"
      :pending="tagReconPending"
      :loading="tagReconLoading"
      @run="runTagReconcile(true)"
    />
  </div>
</template>
<style scoped>
.magicflow-cs-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-block: 14px 8px;
}

/* 弹窗标题行 / 摘要行的「·」分隔符在深浅两色下都偏淡（3.39 / 4.39）→ 提到 0.9 */
.magicflow-recommend-dialog__summary i,
.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.magicflow-cs-status__dim {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}
.magicflow-cs-card {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(var(--v-theme-on-surface), 0.035);
  border: 1px solid rgba(var(--v-border-color), 0.16);
}

.magicflow-cs-card__name {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.magicflow-cs-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}

.magicflow-cs-card__site {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}

.magicflow-cs-card__size {
  font-variant-numeric: tabular-nums;
}
.magicflow-cs-pending {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-block-start: 16px;
}
.magicflow-cs-rules {
  margin-block-start: 18px;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-border-color), 0.16);
  background: rgba(var(--v-theme-on-surface), 0.03);
  overflow: hidden;
}

.magicflow-cs-rules > summary {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  cursor: pointer;
  list-style: none;
}

.magicflow-cs-rules > summary::before {
  content: '▸';
  font-size: 11px;
  transition: transform 0.15s ease;
}

.magicflow-cs-rules[open] > summary::before {
  transform: rotate(90deg);
}

.magicflow-cs-rules > summary::-webkit-details-marker {
  display: none;
}

.magicflow-cs-rules__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 14px 13px;
  font-size: 12.5px;
  line-height: 1.75;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}

.magicflow-cs-rules__body p {
  margin: 0;
}

.magicflow-cs-rules__body strong {
  font-weight: 650;
  color: rgb(var(--v-theme-primary));
}

.magicflow-page {
  /* ===== 深色磨砂主题（仅限本插件工作台作用域）===== */
  --magicflow-panel-bg: rgb(var(--v-theme-surface));
  --magicflow-panel-brd: rgba(var(--v-border-color), 0.14);

  display: flex;
  flex-direction: column;
  gap: 16px;
  min-inline-size: 0;
  padding: 18px;
  color: rgb(var(--v-theme-on-background));
  border-radius: 20px;
  background: rgb(var(--v-theme-background));
}

.magicflow-page--compact {
  padding: 20px;
}

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

.magicflow-task-head,
.magicflow-panel__head,
.magicflow-mobile-torrent__head,
.magicflow-diagnostic-head {
  justify-content: space-between;
}

.magicflow-task-head__identity {
  min-inline-size: 0;
  gap: 12px;
}

.magicflow-task-head h2 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: 0;
}

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

.magicflow-task-head__actions,
.magicflow-task-head__title,
.magicflow-panel__title-row,
.magicflow-mobile-torrent__meta {
  flex-wrap: wrap;
  gap: 8px;
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

.magicflow-settings-dialog {
  display: flex;
  flex-direction: column;
  block-size: min(84vh, 40rem);
  max-block-size: 92vh;
  overflow: hidden;
}

.magicflow-settings-dialog__head,
.magicflow-settings-dialog > .v-divider {
  flex: 0 0 auto;
}

/* MoviePilot 会给表单控件套一层 .app-responsive-input（默认 ~72px 高），
   在自研分块里把它收紧，让间距由我们自己的 grid/gap 决定 */
.magicflow-settings-block .app-responsive-input {
  min-block-size: 0 !important;
  block-size: auto !important;
  padding-block: 0 !important;
  margin-block: 0 !important;
}

.magicflow-settings-block {
  display: grid;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
}

.magicflow-settings-block__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-field__sub {
  font-size: 0.72rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

.magicflow-field-grid {
  display: grid;
  /* MoviePilot 在窄屏会把每个控件渲染成「左标签 / 右值」一行，
     列宽太窄会把「并发数」等标签拆成多行 → 窄屏自动收成单列，宽屏才分两列 */
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px 12px;
}

.magicflow-settings-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 8px 12px;
  margin-block-start: 8px;
}

/* 旧版新手考核样式（保留，部分页面仍在用） */
.magicflow-exam-plan {
  display: grid;
  gap: 8px;
}

.magicflow-exam-plan__item {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 8px 10px;
  display: grid;
  gap: 6px;
  justify-items: start;
  min-inline-size: 0;
}

.magicflow-exam-plan__main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  overflow-wrap: anywhere;
}

/* .magicflow-signin-* / .magicflow-keepalive-*（专属选择器）随弹窗迁入 components/dialogs/SigninDialog.vue。 */

.magicflow-settings-actions {
  display: grid;
  gap: 10px;
  justify-items: start;
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

/* .mf-health__*（专属选择器）随弹窗迁入 components/dialogs/HealthDialog.vue。
   .magicflow-settings-dialog / .magicflow-empty 为共享（父页其它弹窗/列表也用）→ 父页保留。 */

/* ★ 可观测④：事件流 */
.mf-timeline__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-block: 4px 8px;
}

.mf-timeline__label { font-size: 12px; color: rgba(var(--v-theme-on-surface), 0.6); }

.mf-timeline__select { max-inline-size: 12rem; }

.mf-timeline__count { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.5); }

.mf-timeline__row {
  display: flex;
  gap: 8px;
  padding: 7px 8px;
  border-inline-start: 3px solid transparent;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.mf-timeline__row.is-error { border-inline-start-color: rgb(var(--v-theme-error)); }

.mf-timeline__row.is-warning { border-inline-start-color: rgb(var(--v-theme-warning)); }

.mf-timeline__row.is-info { border-inline-start-color: rgb(var(--v-theme-info)); }

.mf-timeline__icon { margin-block-start: 2px; }

.mf-timeline__row.is-error .mf-timeline__icon { color: rgb(var(--v-theme-error)); }

.mf-timeline__row.is-warning .mf-timeline__icon { color: rgb(var(--v-theme-warning)); }

.mf-timeline__row.is-info .mf-timeline__icon { color: rgb(var(--v-theme-info)); }

.mf-timeline__main { flex: 1 1 auto; min-inline-size: 0; }

.mf-timeline__head { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }

.mf-timeline__ts { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.5); white-space: nowrap; }

.mf-timeline__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.mf-timeline__reason { word-break: break-word; }

.mf-timeline__error { font-size: 12px; color: rgb(var(--v-theme-error)); word-break: break-word; }

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

.magicflow-diagnostic-grid {
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


.magicflow-torrent-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.magicflow-torrent-detail {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.magicflow-hash-line {
  margin-block-start: 10px;
  overflow-wrap: anywhere;
}

.torrent-status-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

.magicflow-diagnostic-head {
  margin-block-end: 12px;
}

.magicflow-pipeline li > div,
.magicflow-events article > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-inline-size: 0;
}

.magicflow-pipeline li span,
.magicflow-events article span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.82rem;
  overflow-wrap: anywhere;
}


.magicflow-recommend-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* .magicflow-recommend-dialog__summary(_strong/_i) / __note 为共享（点播弹窗等也用）→ 父页保留；
   RecommendDialog.vue 自带一份。 */
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
}

.magicflow-recommend-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  opacity: 0.85;
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

@media (min-width: 960px) {
/* 详情弹窗由宿主提供固定高度，内部只让右侧工作区承担页面滚动。 */
  .magicflow-page--compact {
    block-size: calc(100dvh - 48px);
    min-block-size: 0;
    overflow: hidden;
  }.magicflow-page--compact .magicflow-layout {
    flex: 1 1 auto;
    grid-template-rows: minmax(0, 1fr);
    align-items: stretch;
    min-block-size: 0;
    overflow: hidden;
  }.magicflow-page--compact .magicflow-task-rail {
    position: static;
    block-size: 100%;
    min-block-size: 0;
    max-block-size: none;
    overflow: hidden;
  }.magicflow-page--compact .magicflow-workspace {
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
  }.magicflow-page--compact {
    padding-block-start: 0;
  }

  .magicflow-task-head {
    align-items: flex-start;
  }.magicflow-task-rail {
    display: none;
  }.magicflow-mobile-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-block-end: 4px;
  }.magicflow-mobile-toolbar .magicflow-mobile-select {
    display: block;
    flex: 1 1 auto;
    min-inline-size: 0;
  }.magicflow-mobile-current {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    justify-content: center;
    min-inline-size: 0;
    padding-inline: 2px;
  }.magicflow-mobile-current span {
    font-size: 11px;
    color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  }.magicflow-mobile-current strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }.magicflow-mobile-add {
    flex: 0 0 auto;
  }.magicflow-layout {
    grid-template-columns: 1fr;
  }.magicflow-diagnostic-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 699px) {
  .magicflow-settings-tab {
    padding-inline: 6px;
    min-width: auto !important;
    font-size: 12px;
    text-transform: none;
  }.magicflow-settings-dialog {
    block-size: min(90vh, 38rem);
    max-block-size: 94vh;
  }  .magicflow-task-head {
    flex-direction: column;
    gap: 0;
  }.magicflow-task-head__identity {
    align-items: flex-start;
    inline-size: 100%;
  }/* 预览图：任务名左侧、状态徽章推到卡片最右 */
  .magicflow-task-head__body {
    flex: 1 1 auto;
    min-inline-size: 0;
  }.magicflow-task-head__title {
    inline-size: 100%;
    justify-content: space-between;
    align-items: center;
  }.magicflow-diagnostic-head,
  .magicflow-panel__head {
    flex-direction: column;
    align-items: flex-start;
  }

  .magicflow-task-head__actions {
    inline-size: 100%;
    justify-content: flex-end;
    gap: 0;
    margin-block-start: 10px;
    padding-block-start: 8px;
    border-block-start: 1px solid rgba(var(--v-border-color), 0.1);
  }

  .magicflow-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }.magicflow-stat {
    min-block-size: 104px;
    padding: 13px;
  }.magicflow-stat > strong {
    font-size: 1.05rem;
  }.magicflow-panel {
    padding: 14px;
  }.magicflow-panel__head {
    flex-wrap: wrap;
  }.magicflow-facts--two {
    grid-template-columns: 1fr;
  }.magicflow-torrent-filters {
    inline-size: 100%;
    flex-wrap: wrap;
  }
}

@media (max-width: 419px) {
.magicflow-stat-grid {
    grid-template-columns: 1fr;
  }

  .magicflow-task-head__title {
    align-items: center;
    flex-wrap: wrap;
  }
}

/* ===== 深色磨砂主题：卡片 / 面板 / 弹窗 ===== */
.magicflow-page .magicflow-panel,
.magicflow-page .magicflow-stat,
.magicflow-page .magicflow-task-rail,
.magicflow-page .magicflow-task-head,
.magicflow-page .magicflow-torrents {
  background: var(--magicflow-panel-bg) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 16px;
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(var(--v-theme-on-surface), 0.04);
}

/* 弹窗（会 teleport 到 body，按专属类名限定，不污染宿主） */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}

/* 品牌区版本号徽标（版本必须常驻显示） */
.magicflow-page .magicflow-page__version {
  display: inline-block;
  margin-inline-start: 8px;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid rgba(var(--v-theme-primary), 0.3);
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
  font-size: 11px;
  font-weight: 500;
  line-height: 1.5;
  vertical-align: middle;
}

/* 顶部「当前任务」切换下拉（方案 B） */
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

@media (max-width: 959px) {
  /* 移动工具栏沿用「方案 B」胶囊：站点图标 + 任务名·站点 + 状态点 + ⌄ */
  .magicflow-page .magicflow-mobile-toolbar .magicflow-task-switch {
    display: inline-flex;
    flex: 1 1 auto;
    min-inline-size: 0;
    max-inline-size: none;
  }.magicflow-page .magicflow-mobile-toolbar .magicflow-task-switch__k {
    display: none;
  }.magicflow-page .magicflow-mobile-toolbar .magicflow-task-switch__v {
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
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(var(--v-theme-on-surface), 0.04);
}

.magicflow-page .magicflow-tab {
  flex: 1 1 0;
  min-inline-size: 0;
  padding: 9px 4px;
  border: 0;
  border-radius: 11px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  background: transparent;
  font: inherit;
  font-size: 12px;
  text-align: center;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.magicflow-page .magicflow-tab.is-active {
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.18);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.4);
}

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

/* 操作记录（预览图：图标瓦片 + 顶部细分隔线） */
.magicflow-page .magicflow-events article {
  align-items: start;
  gap: 11px;
  padding-block: 11px;
  border-top: 1px solid rgba(var(--v-border-color), 0.1);
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
  background: rgba(var(--v-theme-primary), 0.14);
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
  border-top: 1px dashed rgba(var(--v-border-color), 0.14);
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
  background: rgba(var(--v-theme-primary), 0.16);
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

/* 明细里的短 hash（等宽、弱化） */
.magicflow-page .magicflow-events__detail-hash,
.magicflow-dialog .magicflow-events__detail-hash {
  flex: 0 0 auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.66rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

/* ★ 操作记录类型筛选（Master 2026-10-01 18:10）：一行下拉，右对齐 */
.magicflow-page .magicflow-ops-filter,
.magicflow-dialog .magicflow-ops-filter {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin: 0 0 6px;
}

.magicflow-page .magicflow-ops-filter__label,
.magicflow-dialog .magicflow-ops-filter__label {
  font-size: 0.76rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-page .magicflow-ops-filter__select,
.magicflow-dialog .magicflow-ops-filter__select {
  inline-size: 10rem;
  flex: 0 0 auto;
}

.magicflow-page .magicflow-ops-filter__select .v-field,
.magicflow-dialog .magicflow-ops-filter__select .v-field {
  font-size: 0.78rem;
}

.magicflow-page .magicflow-ops-filter__select .v-field__input,
.magicflow-dialog .magicflow-ops-filter__select .v-field__input {
  min-block-size: 32px;
  padding-block: 0;
  font-size: 0.78rem;
}

.magicflow-dialog .magicflow-ops-dialog__tabs {
  align-items: center;
  gap: 8px;
}

/* 任务头卡片内边距（对齐预览图 .thead） */
.magicflow-page .magicflow-task-head {
  padding: 14px 16px;
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
  background: rgba(var(--v-theme-on-surface), 0.03);
}

@media (max-width: 699px) {
.magicflow-page {
    padding-block-end: 76px;
  }
}

/* ── ★ 手机端首页（任务列表）────────────────────────────────────────── */
.magicflow-page .magicflow-mobile-home { display: none; }

.magicflow-page .magicflow-mobile-back { display: none; }

@media (max-width: 959px) {
/* 列表页：显示首页，隐藏工作区与旧移动工具栏 / 桌面计数胶囊 */
  .magicflow-page--m-list .magicflow-mobile-home {
    display: flex; flex-direction: column; padding: 2px 0 6px;
  }
  .magicflow-page--m-list .magicflow-layout,
  .magicflow-page--m-list .magicflow-mobile-toolbar { display: none; }
  /* 详情页：隐藏首页 */
  .magicflow-page--m-detail .magicflow-mobile-home { display: none; }
  /* 详情页显示返回列表按钮 */
  .magicflow-page .magicflow-mobile-back { display: inline-flex; }
}

/* ── ★ 手机端任务详情：紧凑块 ─────────────────────────── */
/* .magicflow-mobile-detail 为**外层容器**（显隐由父页控制），留在本页；
   内层 .md-*（md-verdict / md-dot / md-cards / md-strategy / md-entries / md-entry…）
   全部随内层内容迁入 components/MobileTaskDetail.vue（P4 拆分）。 */
.magicflow-page .magicflow-mobile-detail { display: none; }

@media (max-width: 959px) {
.magicflow-page--m-detail .magicflow-mobile-detail { display: block; }/* 手机端：取消平级四 tab，改为紧凑块 + 次级入口 */
  .magicflow-page .magicflow-tabs { display: none; }.magicflow-page .magicflow-window { padding-block-start: 12px; }
}

/* ── ★ 操作记录独立页 ─────────────────────────────── */
.magicflow-ops-dialog { display: flex; flex-direction: column; }

.magicflow-ops-dialog__spacer { flex: 1 1 auto; }

.magicflow-ops-dialog__sub { padding: 6px 18px 4px; font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }

.magicflow-ops-dialog__tabs { display: flex; gap: 4px; padding: 0 14px 4px; }
/* .magicflow-ondemand-* / .magicflow-od-*（专属选择器）随弹窗迁入 components/dialogs/OndemandDialog.vue。 */
/* ★ §4.1 辅种流水单表 */
.magicflow-reseed { display: flex; flex-direction: column; font-size: 12px; }

.magicflow-reseed__head, .magicflow-reseed__row { display: grid; grid-template-columns: 8.5em minmax(0, 0.8fr) 5.2em minmax(0, 2fr) 4.2em 4.2em; gap: 8px; align-items: center; padding: 5px 2px; }

.magicflow-reseed__head { font-weight: 600; opacity: var(--mf-op-dim); border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12); position: sticky; top: 0; background: rgb(var(--v-theme-surface)); z-index: 1; }

.magicflow-reseed__row { border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06); }

.magicflow-reseed__row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.magicflow-reseed .is-time { font-variant-numeric: tabular-nums; opacity: var(--mf-op-soft); }

.magicflow-reseed .is-num { text-align: right; font-variant-numeric: tabular-nums; }

.magicflow-reseed .is-stage { opacity: 0.8; }

@media (max-width: 640px) {
.magicflow-reseed { font-size: 11px; }.magicflow-reseed__head, .magicflow-reseed__row { grid-template-columns: 5.6em minmax(0, 0.9fr) 4.4em minmax(0, 1.7fr) 3.4em; gap: 6px; }.magicflow-reseed__head > span:nth-child(5),
  .magicflow-reseed__row > span:nth-child(5) { display: none; }
}

.magicflow-ops-dialog__body { padding: 6px 18px 20px; overflow: auto; flex: 1 1 auto; min-height: 0; }

/* 操作记录 / 站点容量 弹窗：让列表撑满卡片可滚区，不再被 .magicflow-events 的 52dvh 上限截断，下方留一大片空白 */
.magicflow-ops-dialog .magicflow-events { max-block-size: none; margin-block-start: 0; padding-inline-end: 0; overflow: visible; }

/* .magicflow-ceiling-*（专属选择器）随弹窗迁入 components/dialogs/CeilingDialog.vue；
   .magicflow-ceiling-empty 为共享（站点报表/H&R 账单也用）→ 父页保留。 */
.magicflow-ceiling-empty { font-size: 12.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); text-align: center; padding: 20px 0; }

@media (max-width: 959px) {
.magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}

@media (max-width: 959px) {
.magicflow-dialog .magicflow-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.magicflow-dialog .magicflow-stat-grid--single { grid-template-columns: minmax(0, 1fr); }.magicflow-dialog .magicflow-config-grid { grid-template-columns: minmax(0, 1fr); }.magicflow-dialog .magicflow-facts--two { grid-template-columns: minmax(0, 1fr); }.magicflow-dialog .magicflow-run-summary { grid-template-columns: minmax(0, 1fr); }.magicflow-settings-dialog .magicflow-settings-grid { grid-template-columns: minmax(0, 1fr); }.magicflow-settings-dialog .magicflow-settings-switches { grid-template-columns: minmax(0, 1fr); }
}
</style>

<style>
/* ★ 浅色主题可读性修复（2026-10-01）
   插件原有的次级文字用 rgba(--v-theme-on-surface, .32~.66) 写死，
   在深色 / 玻璃主题下勉强够看，但在浅色（白底）主题下淡到看不清
   （实测对比度 2.07~3.66，WCAG AA 对正文要求 ≥4.5）。
   这里把「文字强调层级」抽成变量：深色维持原样，浅色主题整体加深。 */
:root {
  --mf-fg-dim: 0.45;   /* 分区标题 / 单位 / 箭头 / 卡片小注 */
  --mf-fg-mid: 0.58;   /* 列表状态行 / 副标题 / 次要说明 */
  --mf-fg-soft: 0.66;  /* 导航项 / 功能磁贴 / 次级按钮 */
  --mf-op-dim: 0.62;   /* 表头 / 角标（opacity 形态） */
  --mf-op-mid: 0.72;
  --mf-op-soft: 0.80;
}

/* ★ 注意：这里不能写 .v-theme--light 当主题钩子——vite.config.js 的 postcss
   「vuetify-filter」会删掉含 .v- 的选择器；而 MP 在 <html> 上放了 data-theme
   （light / dark / glass / purple / transparent）。 */
[data-theme="light"] {
  --mf-fg-dim: 0.74;
  --mf-fg-mid: 0.78;
  --mf-fg-soft: 0.82;
  --mf-op-dim: 0.82;
  --mf-op-mid: 0.88;
  --mf-op-soft: 0.94;
}

/* ── 工作台 / 各弹窗根元素 ───────────────────────────────── */
.magicflow-page,
.magicflow-dialog {
  --v-medium-emphasis-opacity: var(--mf-fg-mid);
}

/* ── Vuetify 组件会在自己身上重新声明主题变量（.v-theme--light），
      所以在这些元素上还要再压一层，否则 chip / 输入框 / 卡片内部
      仍会用回 0.6（浅色下 3.58，依旧偏淡）。 ───────────────── */
.magicflow-page .v-theme--light,
.magicflow-dialog .v-theme--light {
  --v-medium-emphasis-opacity: var(--mf-fg-mid);
}

/* ── MoviePilot 自带的表单提示（写死 0.56）与 Vuetify 输入后缀 ── */
.magicflow-page .app-responsive-input__hint,
.magicflow-dialog .app-responsive-input__hint,
.magicflow-page .v-text-field__suffix__text,
.magicflow-dialog .v-text-field__suffix__text {
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}

/* ── 浅色主题专修 ─────────────────────────────────────────
   MP 浅色主题的 on-surface-variant = 238,238,238（深色底用的 token），
   白底上等于看不见（对比度 1.16）；主题色（紫/琥珀/绿/蓝/红）在白底
   也只有 1.8~4.5，整体加深一档到 ≥4.5。 */
/* ── 深色 / 玻璃主题：MP 主色 141,81,249 在近黑底上仅 3.78~4.02（AA 不足）
   → 提亮一档到 178,140,255（≈5.4），强调数字 / 徽章 / 按钮文字一并达标。 */
.magicflow-page,
.magicflow-dialog,
.magicflow-page [class*="v-theme--"],
.magicflow-dialog [class*="v-theme--"] {
  --v-theme-primary: 178,140,255;
}

[data-theme="light"] .magicflow-page,
[data-theme="light"] .magicflow-dialog,
[data-theme="light"] .magicflow-page .v-theme--light,
[data-theme="light"] .magicflow-dialog .v-theme--light,
[data-theme="light"] .magicflow-page [class*="v-theme--"],
[data-theme="light"] .magicflow-dialog [class*="v-theme--"] {
  --v-theme-on-surface-variant: 101,97,107;   /* ≈ on-surface @0.78 */
  --v-theme-primary: 124,64,232;              /* 4.49 → 5.59 */
  --v-theme-warning: 180,83,9;                /* 1.78 → 5.02 */
  --v-theme-success: 38,105,42;               /* 2.13 → 5.13 / 浅底提示条 4.36 → 5.2 */
  --v-theme-info: 2,119,189;                  /* 2.40 → 4.80 */
  --v-theme-error: 198,40,40;                 /* 3.28 → 5.62 */
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


<!-- ★ 手机端底部安全区：MP 的 AI 悬浮球固定在右下角，会压住最后一屏内容 -->
<style>
@media (max-width: 959px) {
  .magicflow-page--m-list,
  .magicflow-page--m-detail { padding-bottom: 92px; }
  .magicflow-ops-dialog__body,
  .magicflow-settings-dialog__body,
  .magicflow-cloud-dialog__body,
  .magicflow-douban-dialog__body,
  .magicflow-crossseed-dialog__body,
  .magicflow-claim-body,
  .magicflow-recommend-dialog__body { padding-bottom: 92px; }
  .magicflow-music-body { padding-bottom: 92px; }
  .magicflow-torrent-dialog { padding-bottom: 92px; }
}
</style>
