<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
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
  normalizeSortRules,
  SORT_RULE_TYPES,
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
const crossseedData = ref({ count: 0, pending: [], enabled_tasks: [] })
const recommendOpen = ref(false)
const recommendActing = ref('')
let recommendTimer = null
let crossseedTimer = null
let doubanServiceTimer = null
let healthTimer = null
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
// 批量转移（托管页）
const transferDialog = ref(false)
const transferTarget = ref('idle')
const transferChoices = computed(() => {
  const out = [{ value: 'idle', text: '静默池（退回，保文件）' }]
  const me = selectedTask.value
  const mySite = String(me?.site_name || '')
  const rest = (status.value?.tasks || []).filter(t => String(t.id) !== String(me?.id))
  rest.sort((a, b) => Number(String(b.site_name) === mySite) - Number(String(a.site_name) === mySite))
  for (const t of rest) {
    const sameSite = String(t.site_name) === mySite
    out.push({
      value: String(t.id),
      text: `${t.name}${t.enabled ? '' : '（已停用）'} — ${t.site_name}·${t.task_type === 'brush' ? '刷流' : '魔力'}${sameSite ? ' · 同站' : ' · 跨站(会改站点标签)'}`,
    })
  }
  return out
})

function openTransfer() {
  if (!selectedHashes.value.length) return
  transferTarget.value = 'idle'
  transferDialog.value = true
}

async function confirmTransfer() {
  const hashes = selectedHashes.value
  if (!hashes.length || !selectedTask.value) return
  batchBusy.value = true
  try {
    const body = transferTarget.value === 'idle'
      ? { mode: 'idle', hashes }
      : { mode: 'handover', target_task_id: transferTarget.value, hashes }
    const res = await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/handover`, body)
    if (res?.success === false) throw new Error(res?.message || '转移失败')
    notify(res?.message || '已转移')
    transferDialog.value = false
    selectedRows.value = []
    await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)])
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    batchBusy.value = false
  }
}
const selectedHashes = computed(() =>
  (selectedRows.value || []).map(row => row?.hash).filter(Boolean),
)
const ratingSourceItems = [
  { title: '只用 TMDB（默认）', value: 'tmdb' },
  { title: '豆瓣优先（拿不到回退 TMDB · 易被豆瓣限流）', value: 'douban' },
]
const settingsDialog = ref(false)
const settingsTab = ref('general')
const settingsPane = ref('form') // 手机端设置：'dir' = 分类目录页 / 'form' = 分类表单页
const settingsNavEl = ref(null)
// ★ 手机端设置分类是单行横向胶囊条：让当前分类自动滚到可见位置（否则打开时总停在最左边）
function scrollSettingsNavToActive() {
  const el = settingsNavEl.value?.querySelector('.magicflow-settings-nav__item.is-active')
  if (el?.scrollIntoView) el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
}
watch(settingsDialog, v => { if (v) nextTick(() => scrollSettingsNavToActive()) })
watch(settingsTab, () => nextTick(() => scrollSettingsNavToActive()))
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
const siteRules = ref([])
const rulesLoading = ref(false)
// 标签模型（3.13.0）
const tagInfo = ref(null)
const tagMigratePlan = ref(null)
const tagMigrating = ref(false)
const newRuleType = ref('subscribe')
const sortRuleTypeOptions = SORT_RULE_TYPES
const rulesProbing = ref(false)
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
/** 保存目录候选：所有任务用过的目录（+ 设置里的默认）——“填一次就能选到”。 */
const recentSavePaths = computed(() => {
  const set = new Set()
  if (defaultSavePath.value) set.add(defaultSavePath.value)
  for (const t of tasks.value) {
    const p = String(t.save_path || '').trim()
    if (p) set.add(p)
  }
  return [...set]
})
const selectedTask = computed(() => tasks.value.find(item => item.id === selectedTaskId.value) || null)
/** 静默托管：静默池按站点分类（分类卡片用）。 */
const silentHostSites = computed(() => {
  const src = (selectedTask.value && selectedTask.value.classify && selectedTask.value.classify.by_site) || null
  if (!src) return []
  return Object.entries(src)
    .map(([name, v]) => ({ name, total: (v && v.total) || 0, hr: (v && v.hr) || 0 }))
    .sort((a, b) => b.total - a.total)
})
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
// 任务切换器菜单的副标题：站点 + 关键数字一行表达
function taskSwitchSubtitle(task) {
  if (!task) return ''
  const site = task.site_name || task.site_domain || ''
  const t = task.task_type || 'bonus'
  const sc = Number(task.seeding_count || 0)
  const isBrush = t === 'brush'
  // stopped 且未运行
  const mode = task.run_mode || 'running'
  if (mode === 'stopped') {
    return site ? `${site} · 已停` : '已停'
  }
  if (isBrush) {
    // 刷流任务：托管数 + 上传量
    const up = Number(task.task_uploaded || 0)
    const upText = up ? formatBytes(up) : '—'
    return site ? `${site} · ${sc} 种 · 上传 ${upText}` : `${sc} 种 · 上传 ${upText}`
  }
  // bonus 任务：托管数 + 时魔
  if (task.site_bonus_ok && task.site_bonus_per_hour != null) {
    const bh = formatBonus(task.site_bonus_per_hour)
    return site ? `${site} · ${sc} 种 · ${bh}` : `${sc} 种 · ${bh}`
  }
  return site ? `${site} · ${sc} 种` : `${sc} 种`
}
// ── ★ 页面注册表（数据驱动，新增功能页只改这个数组，不必动布局）──────────────
// key 与 open* 处理函数一一对应；后续接入手机端导航 / 底栏 / 更多菜单时统一从这里取。
// scope='global' = 插件级单例（不按任务配）；'view' = 只读视图。
// ★ 权责口径见 docs/MODULES.md：全局单例的功能页必须显式标注，避免被当成「任务级」。
const MF_PAGES = [
  { key: 'recommend', label: '推荐', icon: 'mdi-movie-star-outline', scope: 'global' },
  { key: 'exam', label: '新手考核', icon: 'mdi-school-outline', scope: 'global' },
  { key: 'signin', label: '签到', icon: 'mdi-calendar-check-outline', scope: 'global' },
  { key: 'cloud', label: '云盘归档', icon: 'mdi-cloud-upload-outline', scope: 'global' },
  { key: 'douban', label: '豆瓣评分', icon: 'mdi-database-search-outline', scope: 'global' },
  { key: 'crossseed', label: '跨站取种', icon: 'mdi-swap-horizontal-bold', scope: 'global' },
  { key: 'claim', label: '认领', icon: 'mdi-seal-variant', scope: 'global' },
  { key: 'silent', label: '静默池', icon: 'mdi-pool', scope: 'global' },
  { key: 'sitereport', label: '站点报表', icon: 'mdi-table-large', scope: 'view' },
  { key: 'hrbills', label: 'H&R账单', icon: 'mdi-file-alert-outline', scope: 'view' },
  { key: 'seedhealth', label: '挂种健康', icon: 'mdi-file-find-outline', scope: 'view' },
  { key: 'ceiling', label: '站点容量', icon: 'mdi-gauge', scope: 'view' },
  { key: 'ops', label: '操作记录', icon: 'mdi-history', scope: 'view' },
  { key: 'settings', label: '插件设置', icon: 'mdi-tune-variant', scope: 'global' },
]
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
    case 'seedhealth': return openSeedHealth()
    case 'ceiling': return openCeiling()
    case 'ops': return openOperations('all')
    case 'settings': return openSettings()
  }
}
const opsOpen = ref(false)
// ★ 顶栏功能磁贴显隐（7.10.1）：纯界面层开关，存「隐藏」白名单（空 = 全部显示）。
//   功能本体各有各的开关，这里只管「顶栏/手机功能格要不要显示入口」。
const TILE_OPTIONS = [
  { key: 'recommend', label: '推荐', icon: 'mdi-movie-star-outline' },
  { key: 'exam', label: '新手考核', icon: 'mdi-school-outline' },
  { key: 'signin', label: '签到', icon: 'mdi-calendar-check-outline' },
  { key: 'cloud', label: '云盘归档', icon: 'mdi-cloud-upload-outline' },
  { key: 'douban', label: '豆瓣评分', icon: 'mdi-database-search-outline' },
  { key: 'crossseed', label: '跨站取种', icon: 'mdi-swap-horizontal-bold' },
  { key: 'claim', label: '认领', icon: 'mdi-seal-variant' },
  { key: 'silent', label: '静默池', icon: 'mdi-pool' },
  { key: 'sitereport', label: '站点报表', icon: 'mdi-table-large' },
  { key: 'hrbills', label: 'H&R账单', icon: 'mdi-file-alert-outline' },
  { key: 'seedhealth', label: '挂种健康', icon: 'mdi-file-find-outline' },
  { key: 'ondemand', label: '点播', icon: 'mdi-cloud-download-outline' },
  { key: 'ceiling', label: '站点容量', icon: 'mdi-gauge' },
  { key: 'ops', label: '操作记录', icon: 'mdi-history' },
]
// 已保存的隐藏集合（来自 /status）→ 顶栏/菜单/功能格据此显隐。保存后 loadStatus 刷新。
const hiddenTiles = computed(() => (Array.isArray(status.value.hidden_tiles) ? status.value.hidden_tiles : []))
function tileVisible(key) { return !hiddenTiles.value.includes(key) }
// 设置面板里的开关（draft 控件，保存后落盘）
function tileShown(key) {
  const list = settingsDraft.value.hidden_tiles
  return !(Array.isArray(list) && list.includes(key))
}
function setTileShown(key, shown) {
  let list = Array.isArray(settingsDraft.value.hidden_tiles) ? [...settingsDraft.value.hidden_tiles] : []
  if (shown) list = list.filter(k => k !== key)
  else if (!list.includes(key)) list.push(key)
  settingsDraft.value.hidden_tiles = list
}
// 操作记录作用域：'all' = 主页入口（跨任务 / 跨站点汇总）；'task' = 任务详情入口（当前任务）。
// ★ 主页是全局视角，绝不能把「单个任务」的流水摆在主页（既别扭又不合语义）。
const opsScope = ref('all')
function openOperations(scope = 'all') {
  opsScope.value = scope
  opsOpen.value = true
  if (scope === 'all') loadOperationsAll()
  else if (selectedTaskId.value) loadOperations(selectedTaskId.value)
  else operationData.value = { operations: [], total: 0 }
}
// 设置页目录（手机端：标签栏 → 目录列表；桌面端仍用标签栏）
const MF_SETTINGS_TABS = [
  { key: 'general', label: '常规', icon: 'mdi-cog-outline' },
  { key: 'downloader', label: '下载与目录', icon: 'mdi-download-network-outline' },
  { key: 'template', label: '默认任务模板', icon: 'mdi-file-document-outline' },
  { key: 'iyuu', label: 'IYUU 辅种', icon: 'mdi-sync' },
  { key: 'reseed', label: '全站辅种', icon: 'mdi-content-duplicate' },
  { key: 'fallback', label: '元数据兜底', icon: 'mdi-database-search-outline' },
  { key: 'cloud', label: '云盘归档', icon: 'mdi-cloud-upload-outline' },
  { key: 'exam', label: '考核', icon: 'mdi-school-outline' },
  { key: 'signin', label: '签到', icon: 'mdi-calendar-check-outline' },
  { key: 'live', label: '站点监控', icon: 'mdi-monitor-eye' },
  { key: 'recommend', label: '推荐', icon: 'mdi-movie-star-outline' },
  { key: 'crossseed', label: '跨站', icon: 'mdi-swap-horizontal-bold' },
  { key: 'claim', label: '认领', icon: 'mdi-seal-variant' },
  { key: 'rules', label: '站点规则', icon: 'mdi-shield-check-outline' },
  { key: 'tags', label: '标签管理', icon: 'mdi-tag-multiple-outline' },
]

// ── 手机端首页（任务列表）导航状态 ────────────────────────────────────────
// 桌面端无需该状态：相关显隐全部由 @media (max-width: 959px) 的 CSS 控制。
const mobileView = ref('list') // 'list' | 'detail'
// 窄屏（手机/平板竖屏）：弹窗改为整页。数据驱动，只改这一处。
const isNarrow = ref(typeof window !== 'undefined' ? window.matchMedia('(max-width: 959px)').matches : false)
if (typeof window !== 'undefined') {
  const mq = window.matchMedia('(max-width: 959px)')
  const onChange = (e) => { isNarrow.value = e.matches }
  if (mq.addEventListener) mq.addEventListener('change', onChange)
  else if (mq.addListener) mq.addListener(onChange)
}
const mhOpen = ref({ need: true, live: true, rest: false })
function isGroupOpen(key) { return !!mhOpen.value[key] }
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
const ceilingOpen = ref(false)
function openCeiling() { ceilingOpen.value = true }
// ── 站点报表（11.10.0）：站点级逐条种子状态 ─────────────────────
const siteReportOpen = ref(false)
const siteReportSite = ref('')
const siteReportLive = ref(false)
const siteReportLoading = ref(false)
const siteReport = ref({ site: {}, items: [], summary: {}, hr: {}, available_sites: [] })
const siteReportSites = computed(() => (siteReport.value.available_sites || []))
const siteReportItems = computed(() => {
  const all = siteReport.value.items || []
  return siteReportFilter.value ? all.filter(it => it.bucket === siteReportFilter.value) : all
})
// ★ 12.x：明细按桶筛选（默认全部）。旧版列表按桶排序 → 首屏全是「暂停」，「静默」要滚很远，
//   被误读成「明细只有暂停的」。现在点上方分类标签即可只看该桶。
const siteReportFilter = ref('')
const siteReportSummary = computed(() => siteReport.value.summary || {})
const SITE_REPORT_BUCKETS = [
  { key: '欠H&R', color: 'error' },
  { key: '补源', color: 'purple' },
  { key: '未完成', color: 'amber' },
  { key: '暂停', color: 'grey' },
  { key: '静默', color: 'blue-grey' },
  { key: '保护', color: 'teal' },
  { key: '普通', color: 'primary' },
]
function siteReportBucketColor(b) {
  const hit = SITE_REPORT_BUCKETS.find(x => x.key === b)
  return hit ? hit.color : 'grey'
}
function siteReportItemSub(it) {
  const parts = []
  if (it.state) parts.push(it.state)
  if (it.progress != null && it.progress < 0.999) parts.push(`${Math.round(it.progress * 100)}%`)
  if (it.hr && it.hr.need_left) parts.push(`还需 ${it.hr.need_left}`)
  if (it.bill && it.bill.state) parts.push(`账单 ${it.bill.state}${it.bill.rule ? '/' + it.bill.rule : ''}`)
  return parts.join(' · ')
}
function openSiteReport() { siteReportOpen.value = true; loadSiteReport() }
async function loadSiteReport(liveOverride) {
  siteReportLoading.value = true
  try {
    const q = new URLSearchParams()
    if (siteReportSite.value) q.set('site', siteReportSite.value)
    if (liveOverride === true || (liveOverride === undefined && siteReportLive.value)) q.set('live', '1')
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/site/seeds?${q.toString()}`)) || {}
    siteReport.value = data
    siteReportFilter.value = ''
    if (!siteReportSite.value && siteReportSites.value.length) {
      siteReportSite.value = siteReportSites.value[0].domain || siteReportSites.value[0].name || ''
      await loadSiteReport()
    }
  } catch (e) {
    error.value = `站点报表加载失败：${e}`
  } finally {
    siteReportLoading.value = false
  }
}
// ★ 11.11.0 H&R 账单按站
const hrBillsOpen = ref(false)
const hrBillsLive = ref(false)
const hrBillsLoading = ref(false)
const hrBills = ref({ totals: {}, sites: [], source_of_truth: [], write: {} })
const hrBillsSites = computed(() => hrBills.value.sites || [])
const hrBillsTotals = computed(() => hrBills.value.totals || {})
function hrBillStateColor(st) {
  return ({ active: 'error', breached: 'deep-orange', pending: 'amber', settled: 'success', void: 'grey' })[st] || 'grey'
}
// ★ 11.13.0 H&R 临近到期：只列该站 at_risk 的账单（最多 5 条，详情看 AI 端点）
function hrBillsAtRisk(s) { return ((s && s.items) || []).filter(x => x.at_risk).slice(0, 5) }
function fmtHoursLeft(h) {
  if (h === null || h === undefined) return '—'
  const v = Number(h)
  if (!isFinite(v)) return '—'
  if (v <= 0) return '已逾期'
  if (v < 48) return Math.round(v) + 'h'
  return (v / 24).toFixed(1) + 'd'
}
function openHrBills() { hrBillsOpen.value = true; loadHrBills() }
async function loadHrBills(liveOverride) {
  hrBillsLoading.value = true
  try {
    const q = new URLSearchParams()
    if (liveOverride === true || (liveOverride === undefined && hrBillsLive.value)) q.set('live', '1')
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/hr/bills?${q.toString()}`)) || {}
    hrBills.value = data
  } catch (e) {
    error.value = `H&R 账单加载失败：${e}`
  } finally {
    hrBillsLoading.value = false
  }
}
// ★ 12.5.0 挂种健康度自检（只读）：逐文件核盘找空转/缺文件 + 欠 H&R 风险
const seedHealthOpen = ref(false)
const seedHealthLoading = ref(false)
const seedHealthOnly = ref('all')   // 'all' | 'ghost' | 'partial'
const seedHealth = ref({ counts: {}, bytes: {}, by_site: [], hr_at_risk: [], items: [], scanned: 0, candidates: 0, site_filter: '' })
const seedHealthCounts = computed(() => seedHealth.value.counts || {})
const seedHealthBytes = computed(() => seedHealth.value.bytes || {})
const seedHealthSites = computed(() => seedHealth.value.by_site || {})
const seedHealthAtRisk = computed(() => seedHealth.value.hr_at_risk || [])
const seedHealthItems = computed(() => {
  const only = seedHealthOnly.value
  const all = seedHealth.value.items || []
  return only === 'all' ? all : all.filter(it => it.bucket === only)
})
const SEED_HEALTH_BUCKETS = [
  { key: 'ghost', label: '空转', color: 'error' },
  { key: 'partial', label: '缺文件', color: 'warning' },
  { key: 'normal', label: '正常', color: 'grey' },
]
function seedHealthBucketColor(b) {
  const hit = SEED_HEALTH_BUCKETS.find(x => x.key === b)
  return hit ? hit.color : 'grey'
}
function seedHealthBucketLabel(b) {
  const hit = SEED_HEALTH_BUCKETS.find(x => x.key === b)
  return hit ? hit.label : (b || '?')
}
function openSeedHealth() { seedHealthOpen.value = true; loadSeedHealth() }
async function loadSeedHealth() {
  seedHealthLoading.value = true
  try {
    const q = new URLSearchParams()
    if (seedHealthOnly.value && seedHealthOnly.value !== 'all') q.set('only', seedHealthOnly.value)
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/health/scan?${q.toString()}`)) || {}
    seedHealth.value = data
  } catch (e) {
    error.value = `挂种健康度自检加载失败：${e}`
  } finally {
    seedHealthLoading.value = false
  }
}
// 站点折叠：多任务行可展开
const mhSiteOpen = ref({})
function siteMulti(s) { return s.tasks.length > 1 }
function siteOpen(key) { return !!mhSiteOpen.value[key] }
function toggleSite(key) { mhSiteOpen.value = { ...mhSiteOpen.value, [key]: !mhSiteOpen.value[key] } }
function openSiteRow(s) { if (siteMulti(s)) toggleSite(s.key); else openTaskMobile(s.tasks[0].id) }
const mobileBonus = computed(() => (Number(summary.value.bonus_per_hour) || 0).toFixed(1))
const mobileSilentCount = computed(() => tasks.value.find(t => t.builtin)?.seeding_count || 0)
const mobileCeilingPct = computed(() => Number(summary.value.ceiling_pct || 0))
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
// ── 手机端任务详情：紧凑块（三个数 + 策略一行 + 次级入口）──────────────
const MF_DETAIL_ENTRIES = [
  { key: 'diagnostics', label: '运行诊断', icon: 'mdi-stethoscope' },
  { key: 'pool', label: '种子池', icon: 'mdi-seed-outline' },
  { key: 'config', label: '任务配置', icon: 'mdi-tune-variant' },
  { key: 'ops', label: '操作记录', icon: 'mdi-history', action: 'ops' },
]
function mobileDetailEntry(entry) {
  const e = typeof entry === 'string' ? { key: entry } : entry
  if (e.action === 'ops') return openOperations('task')
  activeTab.value = activeTab.value === e.key ? 'overview' : e.key
}
const mobileDetailCards = computed(() => {
  const t = selectedTask.value
  if (!t) return []
  const cards = [{ v: String(t.seeding_count || 0), k: '托管种' }]
  if (t.task_type === 'brush') {
    cards.push({ v: formatBytes(t.task_uploaded || 0), k: '本任务上传' })
    cards.push({ v: siteAccount.value?.ok ? formatBytes(siteAccount.value.upload || 0) : '—', k: '站点上传' })
  } else {
    cards.push({ v: t.site_bonus_ok && t.site_bonus_per_hour != null ? Number(t.site_bonus_per_hour).toFixed(2) : '—', k: '时魔 /h' })
    cards.push({ v: t.site_current_bonus != null ? Number(t.site_current_bonus).toFixed(0) : '—', k: '站点魔力' })
  }
  return cards
})
const mobileStrategyText = computed(() => {
  const t = selectedTask.value
  if (!t) return ''
  const c = taskConfig.value || {}
  const parts = [t.task_type === 'brush' ? '刷流' : '刷魔力']
  if (t.task_type === 'brush') {
    parts.push(`选种每 ${c.brush_interval ?? '—'} 分钟`)
    if (c.brush_seed_days) parts.push(`满 ${c.brush_seed_days} 天清理`)
  } else {
    parts.push(c.min_bonus_per_hour == null ? '最低魔力自动' : `最低魔力 ${Number(c.min_bonus_per_hour).toFixed(1)}/h`)
    parts.push(c.protect_perfect === false ? '完美种保护关' : '完美种保护开')
    if (t.protected_count) parts.push(`接管保护 ${t.protected_count}`)
  }
  const hr = Number(detailStats.value?.hr_owed ?? t.hr_owed ?? 0)
  if (hr > 0) parts.push(`H&R 欠 ${hr}`)
  return parts.join(' · ')
})
const mobileDetailHint = computed(() => {
  const d = detailStats.value || {}
  if (d.last_error) return `⚠ ${String(d.last_error).slice(0, 60)}`
  if (d.last_run_at) return `上次运行 ${formatDateTime(d.last_run_at)}`
  return '尚未运行'
})
// 「需要你管」：后端给的信号（出错 / 站点读不到 / 从未成功）
const detailAttention = computed(() => selectedTask.value?.attention || detailStats.value?.attention || null)
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
  const tgt = Number(t.goal_target || 0)
  if (t.goal_source === 'pending') {
    return `— / ${tgt} ${unit} · 加载中`
  }
  const cur = Number(t.goal_current || 0)
  const curText = unit === 'GB' ? cur.toFixed(1) : cur.toFixed(2)
  return `${curText} / ${tgt} ${unit}${t.goal_reached ? '（已达标）' : ''}`
})
const taskSiteIcon = computed(() => {
  const id = Number(selectedTask.value?.site_id)
  return id ? siteIcons.value[id] || '' : ''
})
const detailStats = computed(() => detail.value || taskConfig.value)

// ★ 可观测：本轮决策轨迹（Why-not） + 每小时趋势序列（sparkline）
const decision = computed(() => detailStats.value?.last_decision || {})
const decisionSwap = computed(() => decision.value.swap || {})
const decisionReasons = computed(() =>
  Object.entries(decision.value.deleted_by_reason || {})
    .map(([label, count]) => ({ label, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count),
)
const decisionCapText = computed(() => {
  const d = decision.value
  if (!d || d.at_cap === undefined) return ''
  const cap = Number(d.cap_n || 0)
  const n = Number(d.cur_n || 0)
  const gb = Number(d.cur_gb || 0)
  const disk = Number(d.disk_gb || 0)
  const reuse = Number(d.reuse_gb || 0)
  const left = `做种 ${n}${cap ? ` / ${cap}` : ' / ∞'} · 体积 ${gb.toFixed(0)}${disk ? ` / ${disk.toFixed(0)}` : ''}GB`
  return reuse > 0 ? `${left}（辅种 ${reuse.toFixed(0)}GB 不计）` : left
})

const trendSeries = ref({})
async function loadTrend(taskId) {
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/trend?scope=all&hours=72`)) || {}
    trendSeries.value = data.series || {}
  } catch (err) {
    trendSeries.value = {}
  }
}
const trendTask = computed(() => trendSeries.value[`task:${selectedTaskId.value}`] || [])
const trendSite = computed(() => trendSeries.value[`site:${selectedTask.value?.site_id}`] || [])
// 用最近窗口的最大值序列画 sparkline（单序列纯 SVG，无图表库依赖）
function sparkline(series, field, { invert = false } = {}) {
  const pts = (series || []).filter(p => p && p[field] !== null && p[field] !== undefined)
  if (pts.length < 2) return null
  const vs = pts.map(p => Number(p[field]) || 0)
  const min = Math.min(...vs)
  const max = Math.max(...vs)
  const span = (max - min) || 1
  const W = 100, H = 26
  const step = W / (vs.length - 1)
  const path = vs
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(2)},${(H - 3 - ((v - min) / span) * (H - 6)).toFixed(2)}`)
    .join(' ')
  const first = vs[0]
  const last = vs[vs.length - 1]
  const delta = first ? ((last - first) / Math.abs(first)) * 100 : 0
  const good = invert ? delta <= 0 : delta >= 0
  return { path, min, max, last, delta, count: vs.length, good }
}
const trendCards = computed(() => {
  const src = trendTask.value.length ? trendTask.value : trendSite.value
  const scope = trendTask.value.length ? '任务' : '站点'
  return [
    { key: 'bonus', label: `${scope}口径时魔 /h`, unit: '', s: sparkline(src, 'bonus'), color: 'primary' },
    { key: 'seeds', label: '做种数', unit: ' 个', s: sparkline(src, 'seeds'), color: 'info' },
    { key: 'gb', label: '自身体积', unit: ' GB', s: sparkline(src, 'gb'), color: 'secondary' },
    { key: 'reuse_gb', label: '辅种体积（不计占用）', unit: ' GB', s: sparkline(src, 'reuse_gb'), color: 'success' },
  ].filter(c => c.s)
})
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

const KIND_TEXT = { run: '执行', selection: '选种加入', deletion: '删种清理', protection: '手动保留', unprotection: '取消保留', reseed: '辅种', reuse: '存量复用(旧)', crossseed: '跨站取种(旧)', swap: '换种', pause: '暂停种子', resume: '恢复运行', recheck: '强制校验', goal: '达标停止', state: '运行状态', tag: '标签变更', fallback: '元数据兜底', cloud: '云盘归档' }
const STATE_TEXT = { submitting: '提交中', accepted: '已受理', completed: '已完成', failed: '失败' }
const KIND_ICON = {
  run: 'mdi-play-circle-outline',
  selection: 'mdi-download-outline',
  deletion: 'mdi-delete-outline',
  reseed: 'mdi-content-duplicate',
  reuse: 'mdi-content-duplicate',
  swap: 'mdi-swap-horizontal-circle-outline',
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

/** 可展开的明细条目：**所有类型都可展开**（Master 2026-10-01 18:10「操作记录要加详情」）。
 *  只有 run 记录第 0 项是汇总行（source=run），与上方摘要重复 → 过滤掉。 */
// ── 可观测④：结构化事件流（/events）──────────────────────────────
const eventRows = ref([])
const eventsLoading = ref(false)
const eventLevel = ref('')
const EVENT_LEVELS = [
  { value: '', label: '全部级别' },
  { value: 'error', label: '仅错误' },
  { value: 'warning', label: '警告以上' },
  { value: 'info', label: '仅普通' },
]
async function loadEventRows() {
  eventsLoading.value = true
  try {
    const q = ['limit=200', 'min_level='].join('&')
    let url = `${pluginBase.value}/events?${q}`
    if (eventLevel.value === 'error') url += '&level=error'
    if (eventLevel.value === 'warning') url += '&min_level=warning'
    if (eventLevel.value === 'info') url += '&level=info'
    if (opsScope.value === 'task' && selectedTaskId.value) url += `&task_id=${encodeURIComponent(selectedTaskId.value)}`
    const data = unwrapResponse(await props.api.get(url)) || {}
    eventRows.value = (data.events || []).slice().reverse()
  } catch (err) {
    eventRows.value = []
  } finally {
    eventsLoading.value = false
  }
}
function eventLevelColor(level) {
  if (level === 'error') return 'error'
  if (level === 'warning') return 'warning'
  return 'info'
}
function eventLevelIcon(level) {
  if (level === 'error') return 'mdi-alert-octagon-outline'
  if (level === 'warning') return 'mdi-alert-outline'
  return 'mdi-information-outline'
}

function opDetailItems(record) {
  if (!record) return []
  return (record.items || []).filter((it) => String((it && it.source) || '') !== 'run')
}

/** ★ 操作记录按类型筛选（Master 2026-10-01 18:10）。'' = 全部。 */
const opsKind = ref('')
const OPS_KIND_FILTERS = [
  { value: '', label: '全部', icon: 'mdi-format-list-bulleted' },
  { value: 'deletion', label: '删种清理', icon: 'mdi-delete-outline' },
  { value: 'selection', label: '选种加入', icon: 'mdi-download-outline' },
  { value: 'reseed', label: '辅种', icon: 'mdi-content-duplicate' },
  { value: 'protection', label: '手动保留', icon: 'mdi-shield-check-outline' },
  { value: 'unprotection', label: '取消保留', icon: 'mdi-shield-off-outline' },
  { value: 'tag', label: '标签变更', icon: 'mdi-tag-outline' },
  { value: 'run', label: '执行', icon: 'mdi-play-circle-outline' },
]
const opsKindItems = computed(() => {
  // ★ 下拉里只放短标签（不带条数）：手机端窄，带条数会被省略号截断
  return OPS_KIND_FILTERS.map((k) => ({ value: k.value, label: k.label }))
})

function kindCount(kind) {
  const rows = operationData.value.operations || []
  if (!kind) return rows.length
  return rows.filter((r) => String(r.kind || '') === kind).length
}
const opsFiltered = computed(() => {
  const rows = operationData.value.operations || []
  if (!opsKind.value) return rows
  return rows.filter((r) => String(r.kind || '') === opsKind.value)
})

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
const ITEM_SOURCE_TEXT = {
  add: '新增', 'add-fail': '失败', reuse: '复用', 'reuse-fail': '辅种失败',
  adopt: '纳管', watchdog: '看门狗', run: '汇总',
  // ★ 清理类（Master 要求「清理逻辑必须有操作记录 + 详情」）
  missing: '空壳种', silent: '静默池', live: '站点监控', crossseed: '跨站',
  selection: '选种', deletion: '删种', tag: '标签', protection: '保留', unprotection: '取消保留',
}

function itemSourceText(src) {
  return ITEM_SOURCE_TEXT[src] || ''
}

/** ★ §4.1 辅种流水：把「辅种」类记录（kind=reseed，含历史 reuse/crossseed）摊平成一张表。 */
const opsView = ref('flow') // 'flow'=全部流水 · 'reseed'=辅种流水 · 'timeline'=事件流
watch(opsView, (v) => {
  if (v === 'timeline') loadEventRows()
})
const RESEED_KINDS = ['reseed', 'reuse', 'crossseed']
function isReseedRecord(record) {
  return !!record && RESEED_KINDS.includes(record.kind)
}
function reseedActionText(record) {
  if (!record) return ''
  if (record.kind === 'crossseed') return '跨站取种'
  if (record.kind === 'reuse') return '存量复用'
  return '辅种'
}
const reseedRows = computed(() => {
  const out = []
  for (const r of operationData.value.operations || []) {
    if (!isReseedRecord(r)) continue
    const items = (r.items || []).length ? r.items : [{}]
    for (let i = 0; i < items.length; i += 1) {
      const it = items[i] || {}
      out.push({
        key: `${r.operation_id}:${i}`,
        ts: r.created_at,
        task: taskLabel(r.task_id),
        action: reseedActionText(r),
        stage: operationStateText(r.state),
        state: r.state,
        hash: it.hash || '',
        title: it.title || '',
        reason: it.reason || '',
        size_gb: Number(it.size_gb || 0),
      })
    }
  }
  return out.sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || '')))
})

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
      hidden_tiles: status.value.hidden_tiles,
      journal_keep: status.value.journal_keep,
      request_interval: status.value.request_interval,
      bonus_upload_limit_kbps: status.value.bonus_upload_limit_kbps,
      brush_upload_limit_kbps: status.value.brush_upload_limit_kbps,
      seed_up_limit_kbps: status.value.seed_up_limit_kbps,
      brush_seed_up_limit_kbps: status.value.brush_seed_up_limit_kbps,
      tag_model_enabled: status.value.tag_model_enabled !== false,
      show_qb_tags: status.value.show_qb_tags !== false,
      tag_silent_new_timeout_hours: status.value.tag_silent_new_timeout_hours ?? 24,
      sort_rules: normalizeSortRules(status.value.sort_rules),
      iyuu_token: status.value.iyuu_token,
      iyuu_sites: status.value.iyuu_sites,
      hr_seed_margin_hours: status.value.hr_seed_margin_hours ?? 2,
      hr_deadline_warn_hours: status.value.hr_deadline_warn_hours ?? 48,
      ...(status.value.crossseed ? {
        crossseed_guard: status.value.crossseed.guard,
        crossseed_guard_pct: status.value.crossseed.guard_pct,
        crossseed_guard_min_mb: status.value.crossseed.guard_min_mb,
        crossseed_guard_interval_min: status.value.crossseed.guard_interval_min,
        crossseed_guard_keep_seed: status.value.crossseed.keep_seed,
        crossseed_seed_hours_default: status.value.crossseed.seed_hours_default,
        crossseed_site_hours: status.value.crossseed.site_hours || [],
        crossseed_reclaim: status.value.crossseed.reclaim,
        rules_auto_refresh: status.value.crossseed.rules_auto_refresh,
      } : {}),
      ...(status.value.reseed ? {
        reseed_enabled: status.value.reseed.enabled,
        reseed_dry: status.value.reseed.dry,
        reseed_sites: status.value.reseed.sites || [],
        reseed_daily_per_site: status.value.reseed.daily,
        reseed_batch: status.value.reseed.batch,
        reseed_min_size_gb: status.value.reseed.min_size_gb,
      } : {}),
      ...(status.value.claim ? {
        claim_enabled: status.value.claim.enabled,
        claim_dry: status.value.claim.dry,
        claim_sites: status.value.claim.sites || [],
        claim_daily_per_site: status.value.claim.daily,
        claim_batch: status.value.claim.batch,
        claim_interval_sec: status.value.claim.interval_sec,
        claim_min_age_days: status.value.claim.min_age_days,
        claim_require_seeders: status.value.claim.require_seeders,
        claim_min_size_gb: status.value.claim.min_size_gb,
        claim_exclude_zero_bonus: status.value.claim.exclude_zero_bonus,
      } : {}),
      ...(status.value.fallback || {}),
      ...(status.value.live ? {
        live_enabled: status.value.live.enabled,
        live_interval_minutes: status.value.live.interval,
        live_download_alert_mb: status.value.live.download_alert_mb,
        live_ratio_target: status.value.live.ratio_target,
        live_auto_stop: status.value.live.auto_stop,
        live_kill_unfree: status.value.live.kill_unfree,
        live_kill_delete_files: status.value.live.kill_delete_files,
        promo_guard: status.value.live.promo_guard !== false,
        live_notify: status.value.live.notify,
        exam_enabled: status.value.live.exam_enabled,
        exam_include_pass: status.value.live.exam_include_pass,
        exam_sites: status.value.live.exam_sites || [],
      } : {}),
      ...(status.value.signin ? {
        signin_enabled: status.value.signin.enabled,
        signin_sites: status.value.signin.sites || [],
        signin_login_sites: status.value.signin.login_sites || [],
        signin_retry_keyword: status.value.signin.retry_keyword,
        signin_queue: status.value.signin.queue,
        signin_notify: status.value.signin.notify,
        signin_interval_minutes: status.value.signin.interval,
        signin_window_start: status.value.signin.window_start,
        signin_window_end: status.value.signin.window_end,
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
  loadTrend(taskId)
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

// ★ 类型筛选下推到服务端：选了类型就多拉（后端「先取大窗口再筛再截断」），
//   避免只在已加载的 100 条窗口里本地过滤导致深一点的历史被漏掉。
function opsQuery() {
  if (!opsKind.value) return ''
  return `?kind=${encodeURIComponent(opsKind.value)}&limit=200`
}

// 加载操作记录（单任务）。
async function loadOperations(taskId) {
  try {
    operationData.value = unwrapResponse(
      await props.api.get(`${pluginBase.value}/tasks/${taskId}/operations${opsQuery()}`),
    ) || {
      operations: [],
      total: 0,
    }
  } catch (err) {
    error.value = err?.message || String(err)
  }
}

// 加载操作记录（全局：最近 100 条，跨任务 / 跨站点；按类型筛选时拉 200 条）。
async function loadOperationsAll() {
  opsLoadingAll.value = true
  try {
    operationData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/operations${opsQuery()}`)) || {
      operations: [],
      total: 0,
    }
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    opsLoadingAll.value = false
  }
}

function reloadOperations() {
  if (opsScope.value === 'all') loadOperationsAll()
  else if (selectedTaskId.value) loadOperations(selectedTaskId.value)
}

// 切换筛选类型 → 重新拉取（服务端已按类型深挖窗口）。
watch(opsKind, () => reloadOperations())

const opsLoadingAll = ref(false)
// 操作记录全局视图：task_id → 任务名（静默池是常驻伪任务，任务列表里没有它的条目）。
function taskLabel(taskId) {
  if (!taskId) return '—'
  if (taskId === '__silent_host__') return '静默池'
  if (taskId.startsWith('silent:')) return '静默·' + taskId.slice('silent:'.length)
  const t = tasks.value.find((x) => x.id === taskId)
  return t ? t.name || taskId : taskId
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

async function loadCrossseed() {
  try {
    crossseedData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/crossseed`))
      || { count: 0, pending: [], enabled_tasks: [] }
  } catch (err) {
    // 跨站取种是增强信息，失败不打断界面
  }
}

function showCrossseed() {
  crossseedOpen.value = true
  loadCrossseed()
}

// ── 死种补源（rescue）：停滞欠 H&R 的种 → 他站「无 H&R」站补下同 Release ────────
const rescueOpen = ref(false)
const rescueData = ref(null)
const rescueScanning = ref(false)
const rescueBusy = ref(false)
const rescueBusyType = ref('')
const rescueTargets = computed(() => (Array.isArray(rescueData.value?.targets) ? rescueData.value.targets : []))
const rescueSkippedSites = computed(() => (Array.isArray(rescueData.value?.skipped_sites) ? rescueData.value.skipped_sites : []))

async function loadRescue() {
  try {
    rescueData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/rescue?action=scan`)) || null
  } catch (err) {
    // 补源是增强信息，失败不打断界面
  }
}

function openRescue() {
  rescueOpen.value = true
  rescueData.value = null
  loadRescue()
}

async function runRescueScan() {
  rescueScanning.value = true
  try {
    await loadRescue()
    if (!rescueData.value) notify('死种补源：扫描失败（见后端日志）', 'warning')
  } finally {
    rescueScanning.value = false
  }
}

async function runRescueApply(confirm) {
  rescueBusy.value = true
  rescueBusyType.value = confirm ? 'apply' : 'preview'
  try {
    const hashes = rescueTargets.value.map(t => t.hash).filter(Boolean)
    const params = [`action=apply`, `hashes=${encodeURIComponent(hashes.join(','))}`]
    if (confirm) params.push('confirm=1')
    else params.push('dry_run=1')
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/rescue?${params.join('&')}`, {})) || {}
    if (confirm) {
      notify(`死种补源：已补 ${res.added ?? 0} 个副本`)
    } else {
      notify(`死种补源（干跑）：将补 ${res.would_add ?? 0} 个副本（未落盘）`)
    }
    await loadRescue()
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    rescueBusy.value = false
    rescueBusyType.value = ''
  }
}

// ── ★ 全站辅种（7.10.0）：本机已有资源 → 去各站挂种落户（零下载）──────────────
const reseedState = ref(null)
const reseedRunning = ref(false)
// 目标站候选：来自 /reseed 的站点映射（只有 IYUU 站点表里有的站才能当目标），值用域名（后端白名单按域名/名称匹配）
const reseedSiteOptions = computed(() =>
  ((reseedState.value && reseedState.value.sites) || []).map(s => ({
    title: `${s.name || s.domain}${s.passkey_ok ? ' · passkey ✓' : ''}`,
    value: String(s.domain || s.name || s.sid),
  })),
)
async function loadReseed() {
  try {
    reseedState.value = unwrapResponse(await props.api.get(`${pluginBase.value}/reseed`)) || null
  } catch (err) {
    // 全站辅种是增强信息，失败不打断界面
  }
}
function fmtTs(ts) {
  const n = Number(ts || 0)
  return n > 0 ? new Date(n * 1000).toLocaleString() : '—'
}
async function runReseed(forceReal = false) {
  reseedRunning.value = true
  try {
    const dry = forceReal ? 0 : (settingsDraft.value.reseed_dry ? 1 : 0)
    const rep = unwrapResponse(await props.api.post(`${pluginBase.value}/reseed/run?dry=${dry}`, {})) || {}
    const parts = []
    if (rep.plan != null) parts.push(`计划 ${rep.plan}`)
    if (rep.would) parts.push(`可挂 ${rep.would}`)
    if (rep.ok) parts.push(`挂上 ${rep.ok}`)
    if (rep.have) parts.push(`已有 ${rep.have}`)
    if (rep.mismatch) parts.push(`不一致 ${rep.mismatch}`)
    if (rep.nourl) parts.push(`缺链 ${rep.nourl}`)
    if (rep.pv) parts.push(`缺 PV ${rep.pv}`)
    if (rep.fail) parts.push(`失败 ${rep.fail}`)
    notify(`全站辅种${dry ? '（干跑）' : ''}完成：` + (parts.join(' / ') || '无候选') +
      ((rep.errors && rep.errors.length) ? `｜${rep.errors[0]}` : ''))
    await Promise.all([loadReseed(), loadStatus()])
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    reseedRunning.value = false
  }
}

// ── 豆瓣评分服务（magicflow-douban · 3.23.1）─────────────────────────
const doubanServiceOpen = ref(false)
const doubanServiceActing = ref('')
const doubanServiceData = ref({ ok: false, records: 0, cache: {}, crawl: {} })
const doubanCrawl = computed(() => (doubanServiceData.value || {}).crawl || {})
const doubanCrawlProgress = computed(() => {
  const c = doubanCrawl.value
  const total = Number(c.spec_total || 0)
  const idx = Number(c.spec_index || 0)
  if (!total) return 0
  return Math.min(100, Math.round((idx / total) * 100))
})

async function loadDoubanService() {
  try {
    doubanServiceData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/douban_service`))
      || { ok: false, records: 0, cache: {}, crawl: {} }
  } catch (err) {
    // 豆瓣服务是增强信息，失败不打断界面
  }
}

function openDoubanService() {
  doubanServiceOpen.value = true
  loadDoubanService()
}

async function doubanCrawlAction(action) {
  doubanServiceActing.value = action
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/douban_service?action=${action}`, {}))
    if (res) doubanServiceData.value = res
  } catch (err) {
    // 静默
  } finally {
    doubanServiceActing.value = ''
  }
}

// ── 健康自检（可观测③）：零外部请求，只看本地任务状态 + 趋势 ─────────
const healthOpen = ref(false)
const healthData = ref({ level: 'ok', ok: true, counts: {}, issues: [] })
const healthColor = computed(() => {
  const lv = healthData.value?.level || 'ok'
  if (lv === 'error') return 'error'
  if (lv === 'warning') return 'warning'
  if (lv === 'info') return 'info'
  return undefined
})
const healthBadgeCount = computed(() => {
  const c = healthData.value?.counts || {}
  return Number(c.error || 0) + Number(c.warning || 0)
})
const healthLabel = computed(() => {
  const d = healthData.value || {}
  const c = d.counts || {}
  if (d.level === 'error') return `健康：${c.error || 0} 项错误`
  if (d.level === 'warning') return `健康：${c.warning || 0} 项告警`
  if (d.level === 'info') return `健康：${c.info || 0} 条提示`
  return '健康：全部正常'
})
async function loadHealth() {
  try {
    healthData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/health`))
      || { level: 'ok', ok: true, counts: {}, issues: [] }
  } catch (err) {
    // 自检是增强信息，失败不打断界面
  }
}
function openHealth() {
  healthOpen.value = true
  loadHealth()
}
function healthGoto(issue) {
  if (issue?.task_id) selectTask(issue.task_id)
  healthOpen.value = false
}

function fmtCount(n) {
  const v = Number(n || 0)
  if (v >= 10000) return `${(v / 10000).toFixed(1)} 万`
  return String(v)
}

// ── 点播（§1 权威来源 1 · 7.1.0）────────────────────────────────────
const ondemandOpen = ref(false)
const ondemandQuery = ref('')
const ondemandTaskId = ref('')
// ★ 站点多选（勾选框）：不勾 = 全部站点；勾了就只搜勾中的（点播不再依赖任务）
const ondemandSiteIds = ref([])
const ondemandBusy = ref('')
const ondemandResult = ref(null)
const ondemandError = ref('')
const ondemandCandidates = computed(() => {
  const rows = ondemandResult.value?.candidates
  return Array.isArray(rows) ? rows : []
})

function openOndemand() {
  ondemandOpen.value = true
  ondemandResult.value = null
  ondemandError.value = ''
}

function fmtSizeGb(bytes) {
  const v = Number(bytes || 0) / (1024 * 1024 * 1024)
  return v ? `${v.toFixed(2)} GB` : '—'
}

// 点播候选的流量标识：dv=下载因子（0=免费，0<dv<1=折扣，1=全额计入）
function odTraffic(dv) {
  const v = Number(dv ?? 1)
  if (!Number.isFinite(v) || v >= 1) return { text: '计流量', color: '' }
  if (v <= 0) return { text: '免费', color: 'success' }
  return { text: `流量 ×${Math.round(v * 100)}%`, color: 'warning' }
}

function isOndemandAuto(row) {
  return !!row?.enclosure && row.enclosure === ondemandResult.value?.auto_pick
}

async function runOndemand(apply, pick = '') {
  const q = String(ondemandQuery.value || '').trim()
  if (!q) {
    ondemandError.value = '请输入片名或豆瓣/TMDB/IMDB 链接'
    return
  }
  ondemandBusy.value = apply ? 'apply' : 'preview'
  ondemandError.value = ''
  try {
    const params = [`query=${encodeURIComponent(q)}`, `apply=${apply ? 'true' : 'false'}`]
    if (ondemandTaskId.value) params.push(`task_id=${encodeURIComponent(ondemandTaskId.value)}`)
    const _sites = (Array.isArray(ondemandSiteIds.value) ? ondemandSiteIds.value : []).map(String).filter(Boolean)
    if (_sites.length) params.push(`site_ids=${encodeURIComponent(_sites.join(','))}`)
    if (pick) params.push(`pick=${encodeURIComponent(pick)}`)
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/ondemand?${params.join('&')}`, {}))
    if (res) ondemandResult.value = res
  } catch (err) {
    ondemandError.value = err?.message || String(err)
  } finally {
    ondemandBusy.value = ''
  }
}

// ── 跨站辅种：队列 / 流量兜底（3.11.0）────────────────────────────────
const crossseedOpen = ref(false)
const crossseedActing = ref('')
const crossseedPending = computed(() =>
  (Array.isArray(crossseedData.value?.pending) ? crossseedData.value.pending : [])
)
const crossseedGuard = computed(() => (crossseedData.value || {}).guard || { enabled: true, banned: [] })
const crossseedBanned = computed(() =>
  (Array.isArray(crossseedGuard.value?.banned) ? crossseedGuard.value.banned : [])
)
const crossseedSourcesAll = computed(() =>
  (Array.isArray(crossseedData.value?.sources) ? crossseedData.value.sources : [])
)
// ★ 7.19.3：旧「回填」记录没有 来源站/目标站 信息 → 不在本页展示（历史信息见操作记录）
const crossseedSources = computed(() => crossseedSourcesAll.value.filter(s => !s.legacy))
const crossseedLegacyCount = computed(() => crossseedSourcesAll.value.filter(s => !!s.legacy).length)
// ★ 已移交静默池的来源份（下完即移交，H&R 由静默池负责）
const crossseedSilentCount = computed(
  () => crossseedSources.value.filter(s => String(s.pool || '') === 'silent').length
)
const crossseedPendingHandoff = computed(() =>
  Math.max(0, crossseedSources.value.length - crossseedSilentCount.value)
)

function formatRemain(min) {
  const m = Number(min)
  if (!Number.isFinite(m) || m <= 0) return '0 分钟'
  if (m < 60) return `${Math.round(m)} 分钟`
  const hrs = m / 60
  if (hrs < 24) return `${hrs.toFixed(hrs < 10 ? 1 : 0)} 小时`
  return `${(hrs / 24).toFixed(1)} 天`
}

/** ★ 跨站取种（7.4.0 改版）：顶部三个核心数字 + 极简来源份卡片。 */
const crossseedStats = computed(() => ({
  pending: Number(crossseedData.value?.count || 0),
  tasks: Array.isArray(crossseedData.value?.enabled_tasks) ? crossseedData.value.enabled_tasks.length : 0,
  sources: crossseedSources.value.length,
}))

/** 大小文案（GB / TB）。 */
function gbText(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return '—'
  return n >= 1024 ? `${(n / 1024).toFixed(2)} TB` : `${n.toFixed(2)} GB`
}

/** 来源份保种状态徽章：绿=正常（义务已完成）· 黄=保种中 · 灰=保种期满可回收。 */
function crossseedCardState(it) {
  if (it?.done) return { color: 'grey', text: '保种期满可回收' }
  if (it?.fulfilled) return { color: 'success', text: '正常' }
  const rest = Number(it?.remain_min)
  return { color: 'warning', text: rest > 0 ? `保种中 · 剩 ${formatRemain(rest)}` : '保种中' }
}

function crossseedStateText(it) {
  const st = String(it?.state || '')
  const p = it?.progress
  if (st && /paused|stopped|暂停/i.test(st)) return '已暂停'
  if (Number.isFinite(Number(p)) && Number(p) >= 0.999) return '已下载完（回辅中）'
  if (Number.isFinite(Number(p)) && Number(p) > 0) return `下载中 ${(Number(p) * 100).toFixed(1)}%`
  if (p === null || p === undefined) return '下载器中无此种'
  return '等待下载'
}

async function dropCrossseed(h) {
  if (!h) return
  crossseedActing.value = `drop:${h}`
  try {
    const res = unwrapResponse(await props.api.post(
      `${pluginBase.value}/crossseed?action=drop&hash=${encodeURIComponent(h)}`, {}
    )) || {}
    notify(res.message || '已删除跨站种', 'success')
    await loadCrossseed()
  } catch (err) {
    notify(err?.message || '删除失败', 'error')
  } finally {
    crossseedActing.value = ''
  }
}

async function unbanCrossseed(domain = '') {
  crossseedActing.value = `unban:${domain}`
  try {
    const q = domain ? `?action=unban&site=${encodeURIComponent(domain)}` : '?action=unban'
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/crossseed${q}`, {})) || {}
    notify(res.message || '已解除来源站黑名单', 'success')
    await loadCrossseed()
  } catch (err) {
    notify(err?.message || '解除失败', 'error')
  } finally {
    crossseedActing.value = ''
  }
}

async function runCrossseedGuard() {
  crossseedActing.value = 'guard'
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/crossseed?action=guard`, {})) || {}
    if (res) crossseedData.value = res
    notify(res.message || '流量兜底核对完成', 'success')
  } catch (err) {
    notify(err?.message || '核对失败', 'error')
  } finally {
    crossseedActing.value = ''
  }
}

async function clearCrossseed() {
  crossseedActing.value = 'clear'
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/crossseed?action=clear`, {})) || {}
    notify(res.message || '已清空待回辅队列', 'success')
    await loadCrossseed()
  } catch (err) {
    notify(err?.message || '清空失败', 'error')
  } finally {
    crossseedActing.value = ''
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

// ── 签到 / 模拟登录（借鉴 MoviePilot「站点自动签到」插件）──────────────────
// 站点多选：想签几个签几个（siteSelectItems 直接来自 /status.options.sites）
const siteSelectItems = computed(() =>
  (status.value.options?.sites || []).map(s => ({
    title: s.name || s.domain || String(s.id),
    value: String(s.id),
  }))
)
const signinCfg = computed(() => status.value.signin || {})
const signinToday = computed(() => signinCfg.value.today || {})
const signinTodayRows = computed(() => {
  const cfg = signinCfg.value || {}
  const signIds = (cfg.sites || []).map(String)
  const loginIds = (cfg.login_sites || []).map(String)
  const rows = []
  const seen = new Set()
  ;[...signIds, ...loginIds].forEach(key => {
    if (seen.has(key)) return
    seen.add(key)
    const info = siteSelectItems.value.find(s => s.value === key) || {}
    const rec = signinToday.value[key] || {}
    rows.push({
      site_id: key,
      site_name: rec.site_name || info.title || key,
      sign: signIds.includes(key),
      login: loginIds.includes(key),
      signin: rec.sign || null,
      loginResult: rec.login || null,
    })
  })
  return rows
})
const signinRunning = ref(false)
async function runSigninNow(kind = 'sign') {
  if (signinRunning.value) return
  signinRunning.value = true
  try {
    // ★ 插件 API 的 POST 参数只从 query 绑定（body 不生效）→ 参数拼在 URL 上
    const query = new URLSearchParams({ kind: String(kind) }).toString()
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/signin/run?${query}`, {})) || {}
    const s = res.summary || {}
    notify(`${kind === 'sign' ? '签到' : '登录'}完成：成功 ${s.ok || 0} / 失败 ${s.fail || 0}`)
    // 只刷新 status（不重载 settingsDraft，避免把正在编辑的设置冲掉）
    status.value = unwrapResponse(await props.api.get(`${pluginBase.value}/status`)) || status.value
    if (signinOpen.value) loadSigninReport()
  } catch (err) {
    notify(`执行失败：${err?.message || err}`, 'error')
  } finally {
    signinRunning.value = false
  }
}
// ── 签到报表页（独立的「签到」功能页；设置仍在设置页）─────────────────
const signinOpen = ref(false)
const signinReport = ref({ enabled: false, sites: [], records: [], today: '' })
const signinReportLoading = ref(false)
async function loadSigninReport() {
  signinReportLoading.value = true
  try {
    signinReport.value = unwrapResponse(await props.api.get(`${pluginBase.value}/signin?days=7`)) || signinReport.value
  } catch (err) {
    notify(`签到报表读取失败：${err?.message || err}`, 'error')
  } finally {
    signinReportLoading.value = false
  }
}
function openSignin() {
  signinOpen.value = true
  loadSigninReport()
}
// ---------------- 报表（按「几十个站」的规模设计） ----------------
const signinFilter = ref('all')
const signinSearch = ref('')
const SIGNIN_STATUS_TEXT = { ok: '成功', fail: '都失败', signfail: '签到失败', loginfail: '登录失败', pending: '待执行', skip: '跳过', none: '无记录' }
// 失败类（三种颜色）：signfail=签到✗登录✓（红） / loginfail=签到✓登录✗（橙） / fail=都✗（深红）
const SIGNIN_FAIL_STATUS = ['fail', 'signfail', 'loginfail']
function signinStatusText(s) {
  return SIGNIN_STATUS_TEXT[s] || s
}
// 日期标签：09/30 → 9/30（窄屏也能完整显示）
function signinDateLabel(d) {
  const s = String(d || '')
  if (s.length < 10) return s
  return `${Number(s.slice(5, 7))}/${Number(s.slice(8, 10))}`
}
// 单站当天要看的动作：只算「设置里勾了」的那几项（登录站不会显示签到结果）
function _signinWant(r) {
  const want = []
  if (r.sign !== false) want.push(['签到', r.signin])
  if (r.login !== false) want.push(['登录', r.loginResult])
  return want
}
// 单站某天的状态：有失败→fail；缺结果→pending（今天）/none（历史）；全跳过→skip
function _signinStatus(signin, loginResult, pendingWhenEmpty, cfgSign, cfgLogin) {
  const want = _signinWant({ sign: cfgSign, login: cfgLogin, signin, loginResult })
  if (!want.length) return pendingWhenEmpty ? 'pending' : 'none'
  const vals = want.map(([, x]) => x).filter(Boolean)
  if (vals.length < want.length) return pendingWhenEmpty ? 'pending' : 'none'
  if (vals.every(x => x.skipped)) return 'skip'
  // ★ 失败按「谁失败」分色：签到✗=红、登录✗=橙、都✗=深红
  const bad = k => want.some(([kk, x]) => kk === k && x && !x.ok && !x.skipped)
  const signBad = bad('签到')
  const loginBad = bad('登录')
  if (signBad && loginBad) return 'fail'
  if (signBad) return 'signfail'
  if (loginBad) return 'loginfail'
  return 'ok'
}
const signinReportTodayRows = computed(() => {
  const sites = signinReport.value.sites || []
  if (!sites.length) return signinTodayRows.value
  return sites.map(s => ({
    site_id: s.site_id,
    site_name: s.site_name || s.domain || String(s.site_id),
    sign: !!s.sign,
    login: !!s.login,
    signin: s.signin || null,
    loginResult: s.login_result || null,
  }))
})
// 今日各状态计数 + 过滤后的列表（失败优先，几十个站也一眼看出问题）
const signinTodayCounts = computed(() => {
  const c = { all: 0, ok: 0, fail: 0, pending: 0, skip: 0 }
  ;(signinReportTodayRows.value || []).forEach(r => {
    const s = _signinStatus(r.signin, r.loginResult, true, r.sign, r.login)
    c.all++
    if (SIGNIN_FAIL_STATUS.includes(s)) c.fail++
    else c[s] = (c[s] || 0) + 1
  })
  return c
})
const signinFilterItems = computed(() => {
  const c = signinTodayCounts.value
  return [
    { value: 'all', label: `全部 ${c.all}`, color: 'primary' },
    { value: 'fail', label: `失败 ${c.fail}`, color: 'error' },
    { value: 'pending', label: `待执行 ${c.pending}`, color: 'warning' },
    { value: 'ok', label: `成功 ${c.ok}`, color: 'success' },
  ]
})
const SIGNIN_ORDER = { fail: 0, signfail: 1, loginfail: 2, pending: 3, ok: 4, skip: 5 }
const signinTodayList = computed(() => {
  const ord = SIGNIN_ORDER
  const q = String(signinSearch.value || '').trim().toLowerCase()
  return (signinReportTodayRows.value || [])
    .map(r => {
      const status = _signinStatus(r.signin, r.loginResult, true, r.sign, r.login)
      const pairs = _signinWant(r)
      const rt = (signinReport.value.retry || {})[String(r.site_id)]
      const fails = pairs.filter(([, x]) => x && !x.ok && !x.skipped)
      let msg
      if (fails.length) {
        msg = fails.map(([k, x]) => `${k} ✗ ${x.message || ''}`.trim()).join(' · ')
      } else {
        // 全成功 / 待执行：只给简短标记，几十个站也不刷屏（失败才展开原因）
        msg = pairs.map(([k, x]) => (x ? `${k} ${x.ok ? '✓' : (x.na ? '不支持' : (x.skipped ? '跳过' : '✗'))}` : `${k} ⏳`)).join(' · ')
      }
      return { ...r, status, msg: SIGNIN_FAIL_STATUS.includes(status) && rt ? `${msg} · ${rt.next_at} 重试` : msg }
    })
    .filter(r => !q || String(r.site_name || '').toLowerCase().includes(q))
    .filter(r => signinFilter.value === 'all' || (signinFilter.value === 'fail' ? SIGNIN_FAIL_STATUS.includes(r.status) : r.status === signinFilter.value))
    .sort((a, b) => (ord[a.status] - ord[b.status]) || String(a.site_name || '').localeCompare(String(b.site_name || '')))
})
// 近 7 天矩阵：行=站点、列=日期（点阵）；异常在前，支持几十个站滚动查看
const signinKeepalive = computed(() => ((signinReport.value.keepalive || {}).sites || []))
const signinKeepaliveNote = computed(() => {
  const rows = signinKeepalive.value || []
  return rows.length ? String(rows[0].rule_note || '') : ''
})

const signinMatrix = computed(() => {
  const records = signinReport.value.records || []
  const today = signinReport.value.today || ''
  // 近 7 天窗口：以今天为锚，缺记录的日期补空点（列固定 7 个，方便竖着对比）
  const anchor = today || records.map(r => r.date).sort().slice(-1)[0] || ''
  const dates = []
  if (anchor) {
    const base = new Date(`${anchor}T00:00:00`)
    for (let i = 0; i < 7; i += 1) {
      const d = new Date(base)
      d.setDate(base.getDate() - i)
      dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
    }
  }
  const map = new Map()
  const ensure = (sid, name) => {
    const k = String(sid)
    if (!map.has(k)) map.set(k, { sid: k, name: name || k, cells: {} })
    else if (name) map.get(k).name = name
    return map.get(k)
  }
  // 先按设置里的勾选取好「该看哪几项」（登录站不算签到）
  const flags = new Map()
  ;(signinReport.value.sites || []).forEach(s => {
    ensure(s.site_id, s.site_name || s.domain || String(s.site_id))
    flags.set(String(s.site_id), { sign: !!s.sign, login: !!s.login })
  })
  records.forEach(r => {
    Object.keys(r.sites || {}).forEach(sid => {
      const rec = r.sites[sid] || {}
      const row = ensure(sid, rec.site_name)
      const f = flags.get(String(sid)) || {}
      row.cells[r.date] = _signinStatus(rec.sign, rec.login, false, f.sign, f.login)
      if (rec.sign) row.sign = true
      if (rec.login) row.login = true
    })
  })
  ;(signinReport.value.sites || []).forEach(s => {
    const row = ensure(s.site_id, s.site_name)
    row.cells[today] = _signinStatus(s.signin, s.login_result, true, s.sign, s.login)
    row.sign = !!s.sign
    row.login = !!s.login
  })
  const rows = [...map.values()].map(row => {
    const cells = dates.map(d => ({ date: d, status: row.cells[d] || 'none' }))
    const failIdx = cells.findIndex(c => c.status === 'fail')
    return { ...row, cells, failIdx, todayStatus: cells.length ? cells[0].status : 'none' }
  })
  const rank = r => (r.todayStatus === 'fail' ? 0 : r.todayStatus === 'pending' ? 1 : r.failIdx >= 0 ? 2 : 3)
  rows.sort((a, b) => (rank(a) - rank(b)) || (a.failIdx - b.failIdx) || String(a.name).localeCompare(String(b.name)))
  const stats = { ok: 0, fail: 0 }
  rows.forEach(r => r.cells.forEach(c => { if (c.status === 'ok') stats.ok++; else if (c.status === 'fail') stats.fail++ }))
  return { dates, rows, stats }
})
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

// ── 批量入库（Master 2026-09-28 07:00）────────────────────────────
const recSelected = ref({})        // hash -> true
const recBatchActing = ref(false)
// 可勾选/入库的行 = 可手动确认的那些
const recSelectable = computed(() => recommendItems.value.filter(r => recommendActionable(r)))
const recSelectedList = computed(() => recSelectable.value.filter(r => recSelected.value[r.hash]).map(r => r.hash))
const recAllChecked = computed(() => recSelectable.value.length > 0 && recSelectedList.value.length === recSelectable.value.length)
function toggleRec(hash) {
  recSelected.value = { ...recSelected.value, [hash]: !recSelected.value[hash] }
}
function toggleAllRecs() {
  const flag = !recAllChecked.value
  const m = { ...recSelected.value }
  recSelectable.value.forEach(r => { m[r.hash] = flag })
  recSelected.value = m
}
async function batchImportRecommend(useAll) {
  if (recBatchActing.value) return
  const list = useAll ? [] : recSelectedList.value
  if (!useAll && !list.length) return
  recBatchActing.value = true
  try {
    const qs = useAll ? 'all=1' : `hashes=${encodeURIComponent(list.join(','))}`
    const data = unwrapResponse(await props.api.post(`${pluginBase.value}/recommend/batch_import?${qs}`, {})) || {}
    notify(data.message || '批量入库完成')
    recSelected.value = {}
    await loadRecommend()
  } catch (err) {
    notify(err?.response?.data?.message || err?.message || '批量入库失败', 'error')
  } finally {
    recBatchActing.value = false
  }
}

// ── 新手考核（顶栏入口 + 汇总弹窗 + 一键起任务）────────────────────────
const examData = ref({ sites: [], count: 0, enabled: true })
const examOpen = ref(false)
const examActing = ref('')
const examConfirm = ref(null)
let examTimer = null
const examSites = computed(() => examData.value.sites || [])
const examBadge = computed(() => (examData.value.enabled === false ? 0 : Number(examData.value.count || 0)))
const examUrgent = computed(() => examSites.value.filter(s => Number((s.exam || {}).days_left ?? 999) <= 3).length)
// ── 板面重设（5.5.0）：按剩余天数排序 + 每项进度条 + 同任务合并 + 警告前置
const examShowPassed = ref({})
// ★ 排序：**已完成的沉到最下面**；未完成的按剩余天数升序（最紧急的在最上面）
const examRows = computed(() =>
  [...(examData.value.sites || [])].sort((a, b) => {
    const pa = (a.exam || {}).all_pass ? 1 : 0
    const pb = (b.exam || {}).all_pass ? 1 : 0
    if (pa !== pb) return pa - pb
    return Number(((a.exam || {}).days_left ?? 999)) - Number(((b.exam || {}).days_left ?? 999))
  })
)
// 未完成（还有未通过项）的站点数 —— 顶部大数用这个口径，不含已完成的
const examPendingSites = computed(() => examRows.value.filter(r => !(r.exam || {}).all_pass).length)
const examNext = computed(() => examRows.value.find(r => !(r.exam || {}).all_pass) || examRows.value[0] || null)
const examUrgentWeek = computed(() => examRows.value.filter(r => Number(((r.exam || {}).days_left ?? 999)) <= 7).length)
const examPendingItems = computed(() =>
  examRows.value.reduce((n, r) => n + (((r.exam || {}).items || []).filter(i => !i.pass).length), 0)
)
const EXAM_KIND_TEXT = { upload: '刷上传', download: '下载考核', bonus: '攒魔力', hold: '保持做种', info: '下载考核' }
const EXAM_KIND_ICON = {
  upload: 'mdi-upload',
  download: 'mdi-download',
  bonus: 'mdi-star-four-points-outline',
  hold: 'mdi-pause-circle-outline',
  info: 'mdi-download',
}
// ★ 可一键起任务的只有「刷上传 / 攒魔力」；下载类我们不做（Master 2026-09-30），只作提示
const EXAM_ACTIONABLE = ['upload', 'bonus']
function examDaysShort(row) {
  const d = Number(((row || {}).exam || {}).days_left)
  if (!isFinite(d)) return '—'
  return `${Math.max(0, Math.ceil(d))} 天`
}
function examUrgencyColor(row) {
  const d = Number(((row || {}).exam || {}).days_left)
  if (!isFinite(d)) return 'grey'
  if (d <= 3) return 'error'
  if (d <= 7) return 'warning'
  return 'success'
}
// 未过的排前面（已过项可折叠）
function examItems(row) {
  const its = ((row || {}).exam || {}).items || []
  return [...its].sort((a, b) => (a.pass ? 1 : 0) - (b.pass ? 1 : 0))
}
function examPassedCount(row) {
  return (((row || {}).exam || {}).items || []).filter(i => i.pass).length
}
function examSitePct(row) {
  const total = (((row || {}).exam || {}).items || []).length || 1
  return Math.round((examPassedCount(row) * 100) / total)
}
function examItemPct(it) {
  const req = Number((it || {}).req_num) || 0
  const cur = Number((it || {}).cur_num) || 0
  if (req <= 0) return it && it.pass ? 100 : 0
  return Math.max(0, Math.min(100, Math.round((cur * 100) / req)))
}
// 还差多少（失败项最关键的信息；后端给了 short_gb/short_num 就用它）
function examItemGap(it) {
  const o = it || {}
  if (o.pass) return ''
  const fmt = v => (Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 100) / 100))
  if (Number(o.short_gb) > 0) return `${fmt(Number(o.short_gb))} GB`
  if (Number(o.short_num) > 0) return `${fmt(Number(o.short_num))}${o.unit ? ` ${o.unit}` : ''}`
  const d = (Number(o.req_num) || 0) - (Number(o.cur_num) || 0)
  if (d > 0) return `${fmt(d)}${o.unit ? ` ${o.unit}` : ''}`
  return ''
}
function examVisibleItems(row) {
  const all = examItems(row)
  if (examShowPassed.value[row.site_id]) return all
  const fails = all.filter(i => !i.pass)
  return fails.length ? fails : all
}
function examHiddenPassed(row) {
  return examItems(row).length - examVisibleItems(row).length
}
function examTogglePassed(siteId) {
  examShowPassed.value = { ...examShowPassed.value, [siteId]: !examShowPassed.value[siteId] }
}
// 同一任务只出一个动作（如「魔力增量 / 做种积分增量」都指向 XX-考核魔力）
function examActions(row) {
  const out = new Map()
  ;((row || {}).plan || []).forEach(p => {
    const key = `${p.kind}|${p.task_name || ''}`
    if (!out.has(key)) {
      out.set(key, {
        key,
        kind: p.kind,
        label: EXAM_KIND_TEXT[p.kind] || p.label || '任务',
        icon: EXAM_KIND_ICON[p.kind] || 'mdi-play-circle-outline',
        task_name: p.task_name || '',
        can_run: EXAM_ACTIONABLE.includes(p.kind),
        notes: [],
        warn: '',
      })
    }
    const a = out.get(key)
    ;(p.notes || []).forEach(n => {
      let s = String(n || '').trim()
      if (!s) return
      // 窄屏压缩后端长句：尾巴的泛泛建议没信息量，去掉
      s = s.replace(/[;；]?\s*(魔力靠多挂种.*|靠多挂种.*)$/, '').replace('达到后自动停', '→ 自动停')
      // ⚠️ 类提醒（花钱白干/比例掉）前置成警戒条，不能埋在按钮下面
      if (/^⚠️|不建议|建议等|会低于 1|先补上传/.test(s)) {
        a.warn = a.warn ? `${a.warn} · ${s}` : s
        return
      }
      if (!a.notes.includes(s)) a.notes.push(s)
    })
  })
  return [...out.values()]
}
async function loadExam() {
  try {
    examData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/exam`)) || examData.value
  } catch (err) {
    // 考核是增强信息，失败不打断界面
  }
}
function openExam() {
  examOpen.value = true
  loadExam()
}
function examFailedText(row) {
  return ((row.exam || {}).failed || []).join(' / ') || '—'
}
function examDaysText(row) {
  const d = (row.exam || {}).days_left
  if (d === null || d === undefined) return '截止未知'
  const v = Number(d)
  return v <= 3 ? `⚠️ 剩 ${v.toFixed(1)} 天` : `剩 ${v.toFixed(1)} 天`
}
function examGb(v) {
  const n = Number(v || 0) / (1024 ** 3)
  if (!n) return '0'
  return n >= 1024 ? `${(n / 1024).toFixed(2)}T` : `${n.toFixed(2)}G`
}
function examPlan(row, kind) {
  return (row.plan || []).find(p => p.kind === kind) || null
}
function examAct(row, kind) {
  const item = examPlan(row, kind)
  if (!item) return
  if (item.noop || kind === 'hold' || item.kind === 'hold') {
    notify('该考核项目前无需建任务：保持做种 + 多辅种即可')
    return
  }
  examConfirm.value = { row, item, kind }
}
async function examConfirmRun() {
  const ctx = examConfirm.value
  if (!ctx || examActing.value) return
  examActing.value = `${ctx.kind}:${ctx.row.site_id}`
  try {
    // ★ 插件 API 的 POST 参数只在 query 绑定
    const q = new URLSearchParams({ site_id: String(ctx.row.site_id), kind: String(ctx.kind), confirm: 'true' }).toString()
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/exam/act?${q}`, {})) || {}
    notify(res.message || '已执行')
    examConfirm.value = null
    await loadExam()
    status.value = unwrapResponse(await props.api.get(`${pluginBase.value}/status`)) || status.value
  } catch (err) {
    notify(`执行失败：${err?.message || err}`, 'error')
  } finally {
    examActing.value = ''
  }
}

// ── 静默池（silent，7.16.0）：无主种池（跨站 / 跨任务）的全局视图 ────────────────
//   真值源 = 标签账本 tag_state（state=静默）+ 下载器快照；H&R 倒计时来自跨站来源份账本。
//   ★ 关系：跨站「下完」的来源份 → 移交静默池（跨站页只留未下完的列车）。
const silentData = ref({ summary: {}, items: [], records: [], host: {}, settings: {} })
const stage1ZeroDelete = computed(() => silentData.value.pool_cleanup === false)
const silentOpen = ref(false)
const silentLoading = ref(false)
const silentView = ref('pool')   // 'pool' | 'records'
const silentSub = ref('')        // 子类过滤：'' | 新 | 资源 | 普通
const silentSite = ref('')       // 站点过滤
const silentOnlyHr = ref(false)
const silentQ = ref('')
const silentSummary = computed(() => silentData.value.summary || {})
const silentSites = computed(() => silentSummary.value.sites || [])
const silentSubs = computed(() => silentSummary.value.subs || [])
const silentRecords = computed(() => silentData.value.records || [])
const silentItems = computed(() => {
  const kw = String(silentQ.value || '').trim().toLowerCase()
  return (silentData.value.items || []).filter(it => {
    if (silentSub.value && String(it.sub || '') !== silentSub.value) return false
    if (silentSite.value && String(it.site || '') !== silentSite.value) return false
    if (silentOnlyHr.value && !it.hr) return false
    if (kw && !String(it.title || '').toLowerCase().includes(kw)) return false
    return true
  })
})
async function loadSilent() {
  silentLoading.value = true
  try {
    silentData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/silent/pool`)) || silentData.value
  } catch (err) {
    notify(`读取静默池失败：${err?.message || err}`, 'error')
  } finally {
    silentLoading.value = false
  }
}
function openSilent() {
  silentOpen.value = true
  loadSilent()
}
function silentProgressText(it) {
  const p = Number(it?.progress)
  if (!Number.isFinite(p) || p < 0) return '—'
  if (p >= 0.999) return '已完成'
  return `${(p * 100).toFixed(1)}%`
}
function silentHrText(it) {
  const rem = it?.remain_min
  if (rem === null || rem === undefined) return it?.hr ? 'H&R 中' : ''
  return `剩 ${formatRemain(rem)}`
}
const SILENT_SUB_LABEL = { 新: '静默-新', 资源: '静默-资源', 普通: '静默-普通' }
function silentSubLabel(sub) { return SILENT_SUB_LABEL[String(sub || '')] || `静默-${sub || '?'}` }

// ── 静默池「清理（删除）」（★ 13.0.0）：默认干跑，真写二次确认 ──────────────
const purgeOpen = ref(false)
const purgeAsk = ref(false)
const purgeLoading = ref(false)
const purgeActing = ref('')          // '' | 'dry' | 'apply'
const purgeBatch = ref(50)
const purgeSub = ref('普通')          // '' | 普通 | 新 | 资源（保守默认只删「普通」）
const purgeScopeOptions = [
  { label: '仅静默-普通（保守）', value: '普通' },
  { label: '仅静默-新', value: '新' },
  { label: '全部（含静默-新）', value: '' },
]
const purgeData = ref({ counts: {}, by_site: {}, blocked_items: [] })
const purgeCounts = computed(() => purgeData.value.counts || {})
const purgeBlocked = computed(() => purgeData.value.blocked_items || [])
const purgeBySite = computed(() => Object.entries(purgeData.value.by_site || {})
  .map(([site, v]) => ({ site, ...(v || {}) }))
  .sort((a, b) => Number(b.delete || 0) - Number(a.delete || 0)))
async function loadPurge(confirm = 0) {
  purgeActing.value = confirm ? 'apply' : 'dry'
  purgeLoading.value = true
  try {
    const url = `${pluginBase.value}/silent/purge?confirm=${confirm ? 1 : 0}&batch=${Number(purgeBatch.value) || 50}&sub=${encodeURIComponent(purgeSub.value)}`
    const res = unwrapResponse(await props.api.get(url)) || {}
    purgeData.value = res
    notify(res.message || (confirm ? '已删除' : '干跑完成'))
    if (confirm) loadSilent()
  } catch (err) {
    notify(`静默池清理失败：${err?.message || err}`, 'error')
  } finally {
    purgeActing.value = ''
    purgeLoading.value = false
  }
}
function openPurge() {
  purgeOpen.value = true
  loadPurge(0)
}
async function runPurge() {
  purgeAsk.value = false
  await loadPurge(1)
}
// ── 静默不变量收敛（★ 12.7.1）：账本静默但 qB 没停 → 补 pause（只 pause，不删种、不动文件）──
const enforceLoading = ref(false)
const enforceAsk = ref(false)
const enforceData = ref({ scanned: 0, violations: 0, paused: 0, failed: 0, items: [] })
const enforceCounts = computed(() => enforceData.value || {})
async function loadEnforce(confirm = 0) {
  enforceLoading.value = true
  try {
    const url = `${pluginBase.value}/silent/enforce?confirm=${confirm ? 1 : 0}`
    const res = unwrapResponse(await props.api.get(url)) || {}
    enforceData.value = res
    notify(res.message || (confirm ? '已补 pause' : '干跑完成'))
    if (confirm) loadPurge(0)
  } catch (err) {
    notify(`静默不变量收敛失败：${err?.message || err}`, 'error')
  } finally {
    enforceLoading.value = false
  }
}
// 兼容 秒 / 毫秒 / ISO 字符串
function tsText(ts) {
  if (ts === null || ts === undefined || ts === '') return '—'
  let d
  if (typeof ts === 'number') d = new Date(ts > 1e11 ? ts : ts * 1000)
  else d = new Date(ts)
  if (!(d instanceof Date) || Number.isNaN(d.getTime())) return '—'
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// ── 认领（claim，7.14.0）：把「我们在做种」的种在站点侧认领掉，换站点权益 ────────
//   ★ 写动作不可逆（不达标 −魔力 / 主动放弃 −更多）→ 默认干跑，真写要二次确认。
const claimData = ref({ sites: [], claimed: [], claimable: [], soon: [], cfg: {}, records: [] })
const claimOpen = ref(false)
const claimLoading = ref(false)
const claimActing = ref('')
const claimTab = ref('claimable')
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
    claimData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/claim${q}`)) || claimData.value
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
function claimTotal() { return Number(claimData.value.claimed_total || 0) }
function claimRequestable() { return Number(claimData.value.claimable_total || 0) }
function claimAgeText(v) { return (v === null || v === undefined) ? '—' : `${Number(v).toFixed(1)} 天` }
function claimSeedersText(n) { return (n === undefined || n === null || Number(n) < 0) ? '—' : String(n) }
function claimPenaltyText(prof) {
  const p = (prof || {}).penalty || {}
  const parts = []
  if (p.unsatisfied) parts.push(`不达标 −${p.unsatisfied}`)
  if (p.abandon) parts.push(`放弃 −${p.abandon}`)
  if (p.exempt_days) parts.push(`首 ${p.exempt_days} 天豁免`)
  return parts.join(' · ') || '—'
}
async function claimScanRun() {
  if (claimActing.value) return
  claimActing.value = 'run'
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/claim/run?dry=1`, {})) || {}
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
      url = `${pluginBase.value}/claim/run?${q}`
    } else if (ctx.kind === 'do') {
      const q = new URLSearchParams({ site_id: String(row.site_id), hash: String(row.hash), confirm: '1' }).toString()
      url = `${pluginBase.value}/claim/do?${q}`
    } else {
      const q = new URLSearchParams({ site_id: String(row.site_id), hash: String(row.hash), confirm: '1' }).toString()
      url = `${pluginBase.value}/claim/abandon?${q}`
    }
    const res = unwrapResponse(await props.api.post(url, {})) || {}
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

// ── 删除任务：名下种子交棒 / 退回静默 ─────────────────────
const handover = ref(null)
const handoverLoading = ref(false)
const handoverTarget = ref('idle')

const handoverChoices = computed(() => {
  const h = handover.value
  const out = [{ value: 'idle', text: '退回静默池（保文件，交给全局规则管）' }]
  for (const c of h?.candidates || []) {
    const mark = c.same_tag ? '同标签·自动接管' : (c.same_site ? '同站·需重贴标签' : '跨站·会改站点标签')
    const off = c.enabled ? '' : '（已停用）'
    out.push({ value: c.id, text: `${c.name}${off} — ${c.site}·${c.state}（${mark}）` })
  }
  return out
})

async function onDeleteDialog(open) {
  if (!open) return
  handover.value = null
  handoverTarget.value = 'idle'
  if (!selectedTask.value) return
  handoverLoading.value = true
  try {
    handover.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${selectedTask.value.id}/handover`)) || null
    // ★ 默认退回静默池（正常就该这样）；要指定交棒得自己选 —— 同标签任务本来就会自动接管，无需交棒
    handoverTarget.value = 'idle'
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    handoverLoading.value = false
  }
}

// 确认删除当前任务。
async function confirmDeleteTask() {
  if (!selectedTask.value) return
  saving.value = true
  try {
    const q = handoverTarget.value === 'idle'
      ? '?settle=idle'
      : `?handover_to=${encodeURIComponent(handoverTarget.value)}`
    const res = await props.api.delete(`${pluginBase.value}/tasks/${selectedTask.value.id}${q}`)
    if (res?.success === false) throw new Error(res?.message || '删除失败')
    notify(res?.message || '任务已删除')
    deleteDialog.value = false
    selectedTaskId.value = ''
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
async function openSettings(tab = '') {
  settingsTab.value = tab || 'general'
  // 手机端：从「设置」按钮进 → 先给分类目录页；从功能格指定分类进 → 直达该分类表单页。
  settingsPane.value = isNarrow.value && !tab ? 'dir' : 'form'
  settingsDialog.value = true
  await Promise.all([loadDownloaderPrefs(), loadDefaults(), loadIyuuSites()])
  loadSettingsTabData()
}

// 各分类子页的「进页面即拉数据」链（openSettings 与目录下钻共用，别只改一处）。
function loadSettingsTabData() {
  if (settingsTab.value === 'fallback') loadFallback()
  if (settingsTab.value === 'cloud') loadCloud()
  if (settingsTab.value === 'rules') loadRules()
  if (settingsTab.value === 'tags') loadTags()
  if (settingsTab.value === 'reseed') loadReseed()
}

// 设置分类「跳转」：目录页点分类 → 进入该分类表单页（手机端）。
async function openSettingsTab(key) {
  settingsTab.value = key
  settingsPane.value = 'form'
  await Promise.all([loadDownloaderPrefs(), loadDefaults(), loadIyuuSites()])
  loadSettingsTabData()
}

function settingsTabLabel(key) {
  return (MF_SETTINGS_TABS.find(t => t.key === key) || {}).label || '插件设置'
}

function backToSettingsDir() {
  settingsPane.value = 'dir'
}

// ── 标签模型 ─────────────────────────────────────────────
async function loadTags() {
  try {
    const res = await props.api.get(`${pluginBase.value}/tags`)
    tagInfo.value = res?.data || null
  } catch (err) {
    error.value = err?.message || String(err)
  }
}

function sortRuleText(r) {
  return (SORT_RULE_TYPES.find(t => t.value === r?.type)?.text) || r?.type || '-'
}

function sortRuleNeedsMin(type) {
  return !!SORT_RULE_TYPES.find(t => t.value === type)?.min
}

function addSortRule() {
  const t = newRuleType.value
  if (!t) return
  if (!Array.isArray(settingsDraft.value.sort_rules)) settingsDraft.value.sort_rules = []
  if (settingsDraft.value.sort_rules.some(r => r.type === t)) {
    notify('该规则已存在')
    return
  }
  const meta = SORT_RULE_TYPES.find(x => x.value === t) || {}
  const row = { type: t, weight: 50, enabled: true }
  if (meta.min) row.min = meta.defaultMin ?? 0
  settingsDraft.value.sort_rules.push(row)
}

function removeSortRule(i) {
  if (Array.isArray(settingsDraft.value.sort_rules)) settingsDraft.value.sort_rules.splice(i, 1)
}

async function previewTagMigrate() {
  tagMigrating.value = true
  try {
    const res = await props.api.get(`${pluginBase.value}/tags?action=migrate`)
    tagMigratePlan.value = res?.data || null
    await loadTags()
  } catch (err) {
    alert(`迁移预演失败: ${err?.message || err}`)
  } finally {
    tagMigrating.value = false
  }
}

async function applyTagMigrate() {
  const total = tagMigratePlan.value?.total || 0
  if (!total) return
  if (!confirm(`确认把 ${total} 个托管种子的老标签迁移到「魔流-站点-状态」新命名？\n（保留 已整理/辅种 等外来标签）`)) return
  tagMigrating.value = true
  try {
    const res = await props.api.post(`${pluginBase.value}/tags/migrate`, { apply: true })
    notify(res?.message || '迁移完成')
    tagMigratePlan.value = null
    await loadTags()
    emit('action')
  } catch (err) {
    alert(`迁移失败: ${err?.message || err}`)
  } finally {
    tagMigrating.value = false
  }
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
async function loadRules() {
  rulesLoading.value = true
  try {
    const res = await props.api.get('rules')
    siteRules.value = res?.data?.rules || []
  } catch (e) {
    siteRules.value = []
  } finally {
    rulesLoading.value = false
  }
}

async function probeRules(site) {
  rulesProbing.value = true
  try {
    const q = site ? `&site=${encodeURIComponent(site)}` : ''
    const res = await props.api.get(`rules?action=probe${q}`)
    if (res?.success === false) throw new Error(res?.message || '探测失败')
    siteRules.value = res?.data?.rules || siteRules.value
    return res
  } finally {
    rulesProbing.value = false
  }
}

async function setRuleHr(row, hr) {
  if (!row?.domain) return
  try {
    const res = await props.api.get(
      `rules?action=hr&site=${encodeURIComponent(row.domain)}&hr=${encodeURIComponent(hr)}`,
    )
    if (res?.success === false) throw new Error(res?.message || '失败')
    siteRules.value = res?.data?.rules || siteRules.value
    await loadRules()
  } catch (e) {
    alert(`标记失败: ${e?.message || e}`)
  }
}

async function setRuleHours(row, hours) {
  const dom = row?.domain
  if (!dom) return
  await props.api.get(`rules?action=set&site=${encodeURIComponent(dom)}&hours=${encodeURIComponent(hours)}`)
  await loadRules()
}

async function refreshRules() {
  const res = await props.api.get('rules?action=refresh')
  siteRules.value = res?.data?.rules || []
}

function ruleSourceText(row) {
  const src = row?.hours_src
  const base = ({ manual: '手填', welcome: '收件箱规则', probe: '页面探测', builtin: '内置', default: '全局默认' })[src] || src || '-'
  if (src === 'probe' && row?.confidence && row.confidence !== 'high') return `${base}(低可信)`
  if (row?.hr_src === 'retired') return `${base}`
  return base
}

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

// 清空已存的 IYUU Token（后端「空值=保持原值」，所以清空要显式带 iyuu_clear）。
async function clearIyuuToken() {
  settingsDraft.value.iyuu_token = ''
  settingsDraft.value.iyuu_clear = true
  try {
    await saveIyuu()
  } finally {
    settingsDraft.value.iyuu_clear = false
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
  if (tab === 'downloader') return saveDownloaderAndPaths()
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

// 保存「下载与目录」标签：qBittorrent 全局参数 + 全局路径 + 任务保存目录（一次存齐）。
async function saveDownloaderAndPaths() {
  saving.value = true
  try {
    const data = unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/prefs`, normalizeDownloaderPrefs(downloaderPrefsDraft.value)),
    )
    if (data && data.available) {
      downloaderPrefsDraft.value = normalizeDownloaderPrefs(data)
      downloaderPrefsRaw.value = data.raw || null
    }
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/paths`, normalizeDownloaderPaths(downloaderPathsDraft.value)),
    )
    unwrapResponse(await props.api.post(`${pluginBase.value}/defaults`, normalizeDefaults(defaultsDraft.value)))
    notify('下载与目录已保存')
    await loadStatus()
    emit('action')
  } catch (err) {
    error.value = err?.message || String(err)
  } finally {
    saving.value = false
  }
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
async function saveSettings() {  saving.value = true
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
  // 跨站免费取种待回辅队列（低频刷角标）
  loadCrossseed()
  crossseedTimer = window.setInterval(loadCrossseed, 120000)
  // 豆瓣评分服务（库容量 + 慢爬进度，低频刷）
  loadDoubanService()
  doubanServiceTimer = window.setInterval(loadDoubanService, 60000)
  healthTimer = window.setInterval(loadHealth, 60000)
  loadHealth()
  // 新手考核也是全局的（低频刷新角标；关闭时服务端立即返回，零开销）
  loadExam()
  examTimer = window.setInterval(loadExam, 300000)
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
  if (crossseedTimer) window.clearInterval(crossseedTimer)
  if (doubanServiceTimer) window.clearInterval(doubanServiceTimer)
  if (healthTimer) window.clearInterval(healthTimer)
  if (examTimer) window.clearInterval(examTimer)
  if (liveTimer) window.clearInterval(liveTimer)
  if (warmingTimer) window.clearTimeout(warmingTimer)
  if (cloudPollTimer) window.clearInterval(cloudPollTimer)
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
            @click="openRecommend"
          />
        </VBadge>
        <VBtn
          v-else-if="tileVisible('recommend')"
          class="magicflow-recommend-btn"
          icon="mdi-movie-star-outline"
          variant="text"
          aria-label="推荐"
          @click="openRecommend"
        />
        <VBtn
          v-if="tileVisible('cloud')"
          class="magicflow-cloud-btn"
          icon="mdi-cloud-upload-outline"
          variant="text"
          aria-label="云盘归档"
          @click="openCloud"
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
            @click="showCrossseed"
          />
        </VBadge>
        <VBtn
          v-else-if="tileVisible('crossseed')"
          class="magicflow-crossseed-btn"
          icon="mdi-swap-horizontal-bold"
          variant="text"
          aria-label="跨站免费取种"
          @click="showCrossseed"
        />
        <VBtn
          v-if="tileVisible('douban')"
          class="magicflow-douban-btn"
          icon="mdi-database-search-outline"
          variant="text"
          :color="doubanServiceData.ok ? undefined : 'warning'"
          :aria-label="`豆瓣评分服务：库 ${doubanServiceData.records || 0} 条`"
          :title="`豆瓣评分服务：库 ${doubanServiceData.records || 0} 条${doubanServiceData.ok ? '' : '（不可用）'}`"
          @click="openDoubanService"
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
            @click="openHealth"
          />
        </VBadge>
        <VBtn
          v-else
          class="magicflow-health-btn"
          icon="mdi-heart-pulse"
          variant="text"
          :aria-label="healthLabel"
          :title="healthLabel"
          @click="openHealth"
        />
        <VBtn
          v-if="tileVisible('ondemand')"
          class="magicflow-ondemand-btn"
          icon="mdi-cloud-download-outline"
          variant="text"
          aria-label="点播"
          title="点播：片名 / 豆瓣·TMDB·IMDB 链接 → 搜索选源（免费优先）→ 直接转「资源」"
          @click="openOndemand"
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
            @click="openExam"
          />
        </VBadge>
        <VBtn
          v-else-if="tileVisible('exam') && examData.enabled !== false"
          class="magicflow-exam-btn"
          icon="mdi-school-outline"
          variant="text"
          aria-label="新手考核"
          @click="openExam"
        />
        <VBtn
          class="magicflow-rescue-btn"
          icon="mdi-lifebuoy"
          variant="text"
          aria-label="死种补源"
          title="死种补源：停滞欠 H&R 的种 → 他站无 H&R 站补下同 Release"
          @click="openRescue"
        />
        <VBtn
          v-if="tileVisible('sitereport')"
          class="magicflow-sitereport-btn"
          icon="mdi-table-large"
          variant="text"
          aria-label="站点报表"
          title="站点报表：逐条种子状态（分类/保护/账单/qB）"
          @click="openSiteReport"
        />
        <VBtn
          v-if="tileVisible('seedhealth')"
          class="magicflow-seedhealth-btn"
          icon="mdi-file-find-outline"
          variant="text"
          aria-label="挂种健康"
          title="挂种健康：逐文件核盘找空转/缺文件的种 + 欠 H&R 风险"
          @click="openSeedHealth"
        />
        <!-- ★ 桌面：详情磁贴（推荐/云盘/跨站/豆瓣/点播/考核/补源）与「设置」分两档 → 中间加一条竖分隔 -->
        <span class="magicflow-hdr-sep" aria-hidden="true" />
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
          <VList density="comfortable" class="magicflow-more-menu" min-width="228">
            <VListItem
              v-if="tileVisible('recommend') && recommendData.enabled !== false"
              prepend-icon="mdi-movie-star-outline"
              title="推荐"
              :subtitle="(recommendData.recommended || 0) > 0 ? `${recommendData.recommended} 个待确认` : '影视推荐甄别'"
              @click="openRecommend"
            />
            <VListItem v-if="tileVisible('cloud')" prepend-icon="mdi-cloud-upload-outline" title="云盘归档" @click="openCloud" />
            <VListItem
              v-if="tileVisible('crossseed')"
              prepend-icon="mdi-swap-horizontal-bold"
              title="跨站取种"
              :subtitle="Number(crossseedData.count || 0) > 0 ? `${crossseedData.count} 个可免费取种` : '跨站免费取种'"
              @click="showCrossseed"
            />
            <VListItem
              v-if="tileVisible('douban')"
              prepend-icon="mdi-database-search-outline"
              title="豆瓣评分"
              :subtitle="`库 ${doubanServiceData.records || 0} 条${doubanServiceData.ok ? '' : '（服务不可用）'}`"
              @click="openDoubanService"
            />
            <VListItem
              prepend-icon="mdi-heart-pulse"
              title="健康自检"
              :subtitle="healthBadgeCount > 0 ? `${healthBadgeCount} 项待处理` : '各子系统正常'"
              @click="openHealth"
            />
            <VListItem
              v-if="tileVisible('ondemand')"
              prepend-icon="mdi-cloud-download-outline"
              title="点播"
              subtitle="片名 / 链接 → 搜索选源（免费优先）"
              @click="openOndemand"
            />
            <VListItem
              v-if="tileVisible('exam') && examData.enabled !== false"
              prepend-icon="mdi-school-outline"
              title="新手考核"
              :subtitle="examBadge > 0 ? `${examBadge} 个未通过` : '考核进度与一键起任务'"
              @click="openExam"
            />
            <VListItem prepend-icon="mdi-lifebuoy" title="死种补源" subtitle="停滞欠 H&R 的种 → 无 H&R 站补源" @click="openRescue" />
            <VListItem
              v-if="tileVisible('sitereport')"
              prepend-icon="mdi-table-large"
              title="站点报表"
              subtitle="站点逐条种子状态（分类/保护/账单）"
              @click="openSiteReport"
            />
            <VListItem
              v-if="tileVisible('seedhealth')"
              prepend-icon="mdi-file-find-outline"
              title="挂种健康"
              :subtitle="Number(seedHealthCounts.ghost || 0) + Number(seedHealthCounts.partial || 0) > 0 ? `${Number(seedHealthCounts.ghost || 0) + Number(seedHealthCounts.partial || 0)} 个异常` : '逐文件核盘自检'"
              @click="openSeedHealth"
            />
            <!-- ★ 上面是「详情」，下面是「设置」：分隔开，别混成一串 -->
            <VDivider class="my-1" />
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
        <div class="mh-hero" role="button" tabindex="0" @click="openCeiling()">
          <div class="mh-hero__main">
            <div class="mh-hero__v">{{ mobileBonus }}<small>/h</small></div>
            <div class="mh-hero__s">{{ mobileLiveCount }} 个魔力站在跑<template v-if="mobileCeilingPct > 0"> · 上限占用 {{ mobileCeilingPct }}%</template><template v-if="mobileTodayGain > 0"> · 今日 +{{ mobileTodayGain.toFixed(1) }}</template></div>
          </div>
          <VIcon icon="mdi-chevron-right" size="22" class="mh-hero__chev" />
        </div>
        <div v-for="g in mobileHomeGroups" :key="g.key" class="mh-group">
          <button type="button" class="mh-group__head" @click="toggleGroup(g.key)">
            <span>{{ g.label }}</span>
            <span class="mh-count">{{ g.count }}</span>
            <VIcon :icon="isGroupOpen(g.key) ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="18" />
          </button>
          <div v-show="isGroupOpen(g.key)" class="mh-list">
            <template v-for="s in g.sites" :key="s.key">
              <button
                type="button"
                class="mh-row"
                @click="openSiteRow(s)"
              >
                <span class="mh-dot" :class="`is-${s.attention ? s.attention.level : taskBadge(s.tasks[0]).color}`" />
                <span class="mh-row__main">
                  <span class="mh-row__nm">
                    {{ s.site }}
                    <span v-if="siteMulti(s)" class="mh-row__tag">{{ s.tasks.length }} 任务</span>
                  </span>
                  <span class="mh-row__st" :class="{ 'is-att': s.attention }">{{ s.attention ? s.attention.text : mobileRowLine(s.tasks[0]) }}</span>
                </span>
                <span v-if="s.num" class="mh-row__num">{{ s.num }}</span>
                <VIcon
                  :icon="siteMulti(s) ? (siteOpen(s.key) ? 'mdi-chevron-up' : 'mdi-chevron-down') : 'mdi-chevron-right'"
                  size="18"
                  class="mh-row__chev"
                />
              </button>
              <div v-if="siteMulti(s)" v-show="siteOpen(s.key)" class="mh-sublist">
                <button
                  v-for="t in s.tasks"
                  :key="t.id"
                  type="button"
                  class="mh-subrow"
                  @click="openTaskMobile(t.id)"
                >
                  <span class="mh-dot" :class="`is-${taskBadge(t).color}`" />
                  <span class="mh-row__main"><span class="mh-row__nm">{{ t.name }}</span></span>
                  <span v-if="mobileRowNum(t)" class="mh-row__num">{{ mobileRowNum(t) }}</span>
                </button>
              </div>
            </template>
          </div>
        </div>
        <div class="mh-sect">功能</div>
        <div class="mh-tools">
          <button
            v-for="p in MF_PAGES.filter(item => item.key !== 'settings' && tileVisible(item.key))"
            :key="p.key"
            type="button"
            class="mh-tool"
            @click="mfOpenPage(p)"
          >
            <VIcon :icon="p.icon" size="20" />
            <span>{{ p.label }}<em v-if="p.scope === 'global'" class="mh-tool__scope">全局</em></span>
          </button>
        </div>
        <div class="mh-foot">
          <button type="button" class="mh-btn" @click="openCreateTask">
            <VIcon icon="mdi-plus" size="18" />新建任务
          </button>
          <button type="button" class="mh-btn mh-btn--ghost" @click="openSettings()">
            <VIcon icon="mdi-tune-variant" size="18" />设置
          </button>
        </div>
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
                <VChip v-if="task.builtin" size="x-small" variant="tonal" color="primary">常驻</VChip>
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
            <div class="md-verdict" :class="{ 'is-warn': !!detailAttention }">
              <span class="md-dot" :class="`is-${detailAttention ? detailAttention.level : selectedState.color}`" />
              <div class="md-verdict__body">
                <div class="md-v">{{ detailAttention ? detailAttention.text : selectedState.text }}<template v-if="!detailAttention"> · 无需操作</template></div>
                <div class="md-s">{{ detailAttention ? detailAttention.detail : mobileDetailHint }}</div>
              </div>
              <button v-if="detailAttention" type="button" class="md-act" @click="activeTab = 'diagnostics'">{{ detailAttention.action }}</button>
            </div>
            <div class="md-cards">
              <div v-for="c in mobileDetailCards" :key="c.k" class="md-card">
                <b>{{ c.v }}</b><span>{{ c.k }}</span>
              </div>
            </div>
            <div class="md-strategy">{{ mobileStrategyText }}</div>
            <div class="md-entries">
              <button
                v-for="e in MF_DETAIL_ENTRIES"
                :key="e.key"
                type="button"
                class="md-entry"
                :class="{ 'is-active': activeTab === e.key }"
                @click="mobileDetailEntry(e)"
              >
                <VIcon :icon="e.icon" size="20" />
                <span>{{ e.label }}</span>
              </button>
            </div>
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
              <div v-if="(selectedTask.run_mode || 'running') === 'seeding'" class="magicflow-stat-grid magicflow-stat-grid--single">
                <VSheet class="magicflow-stat magicflow-stat--accent app-surface-static">
                  <strong>{{ selectedTask.protected_count || 0 }}</strong>
                  <span>接管保护 · 手动加或 IYUU 回来的种子已纳管并永久保护（不再补种/刷魔力）</span>
                </VSheet>
              </div>

              <!-- ★ 可观测①：本轮决策轨迹（回答「为什么这轮没删 / 没换 / 删了什么」） -->
              <VSheet v-if="decision.at_cap !== undefined" tag="section" class="magicflow-panel app-surface-static mf-obs">
                <header class="magicflow-panel__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">本轮决策</div>
                    <div class="text-body-2 text-medium-emphasis">为什么这么做 · 最近一轮的闸门判定与淘汰口径</div>
                  </div>
                  <VChip :color="decision.at_cap ? 'warning' : 'success'" size="small" variant="tonal">
                    {{ decision.at_cap ? '已达上限 · 可换种' : '未达上限 · 不做低效换种' }}
                  </VChip>
                </header>
                <div class="mf-obs__rows">
                  <div class="mf-obs__row">
                    <span>闸门</span>
                    <strong>{{ decisionCapText }}</strong>
                  </div>
                  <div class="mf-obs__row">
                    <span>淘汰口径</span>
                    <strong>
                      候选 {{ decision.candidates ?? '—' }} → 受保护 {{ decision.protected ?? '—' }} →
                      保留 {{ decision.keep ?? '—' }} → 待删 {{ decision.to_delete ?? '—' }} → 实删 {{ decision.deleted ?? '—' }}
                    </strong>
                  </div>
                  <div class="mf-obs__row">
                    <span>门槛 / 保护</span>
                    <strong>
                      低效门槛 {{ decision.threshold ?? '—' }}/h · 保护阈值
                      {{ decision.protect_threshold ?? '∞' }} · 保留上限 {{ decision.max_keep ?? '—' }} 个 ·
                      零魔淘汰 {{ decision.zero_bonus_delete ? '开' : '关' }}
                    </strong>
                  </div>
                  <div class="mf-obs__row">
                    <span>自动换种</span>
                    <strong>
                      {{ decisionSwap.triggered ? '触发' : '未触发' }}
                      <template v-if="decisionSwap.trigger">（{{ decisionSwap.trigger }}）</template>
                      <template v-if="decisionSwap.reason"> · {{ decisionSwap.reason }}</template>
                      · 实际换 {{ decisionSwap.applied || 0 }} 个 · 净收益 {{ decisionSwap.net || 0 }}/h
                    </strong>
                  </div>
                  <div v-if="decisionReasons.length" class="mf-obs__row">
                    <span>删除原因</span>
                    <div class="mf-obs__chips">
                      <VChip v-for="r in decisionReasons" :key="r.label" size="x-small" variant="tonal" color="error">
                        {{ r.label }} ×{{ r.count }}
                      </VChip>
                    </div>
                  </div>
                </div>
              </VSheet>

              <!-- ★ 可观测②：每小时趋势 sparkline -->
              <VSheet v-if="trendCards.length" tag="section" class="magicflow-panel app-surface-static mf-obs">
                <header class="magicflow-panel__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">趋势</div>
                    <div class="text-body-2 text-medium-emphasis">每小时采样 · 最近 72 小时（本地序列，无外部依赖）</div>
                  </div>
                </header>
                <div class="mf-spark-grid">
                  <div v-for="c in trendCards" :key="c.key" class="mf-spark">
                    <div class="mf-spark__head">
                      <span>{{ c.label }}</span>
                      <strong>
                        {{ Number(c.s.last).toFixed(c.key === 'seeds' ? 0 : 2) }}{{ c.unit }}
                        <em :class="c.s.good ? 'is-up' : 'is-down'">
                          {{ c.s.delta >= 0 ? '▲' : '▼' }}{{ Math.abs(c.s.delta).toFixed(1) }}%
                        </em>
                      </strong>
                    </div>
                    <svg class="mf-spark__svg" viewBox="0 0 100 26" preserveAspectRatio="none">
                      <path :d="c.s.path" fill="none" :class="`mf-spark__line mf-spark__line--${c.color}`" vector-effect="non-scaling-stroke" />
                    </svg>
                    <div class="mf-spark__foot">
                      <span>{{ c.s.count }} 点</span>
                      <span>低 {{ Number(c.s.min).toFixed(1) }} · 高 {{ Number(c.s.max).toFixed(1) }}</span>
                    </div>
                  </div>
                </div>
              </VSheet>

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
                  <VBtn size="small" variant="tonal" color="primary" :disabled="batchBusy" @click="openTransfer">批量转移</VBtn>
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

    <VDialog v-model="ceilingOpen" max-width="34rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-ceiling-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">站点容量</span>
          <span class="magicflow-ops-dialog__spacer" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="ceilingOpen = false" />
        </header>
        <div class="magicflow-ops-dialog__sub">
          时魔 ÷ 站点上限。占用高 = 快满，占用低 = 还有空间加种
        </div>
        <div class="magicflow-ops-dialog__body">
          <div class="magicflow-ceiling-list">
            <div v-for="r in siteCeilingRows" :key="r.site" class="magicflow-ceiling-row">
              <div class="magicflow-ceiling-row__head">
                <span class="magicflow-ceiling-row__nm">{{ r.site }}</span>
                <span class="magicflow-ceiling-row__val">
                  {{ r.bonus ? r.bonus.toFixed(1) : '—' }}<small>/h</small>
                  <template v-if="r.ceiling"> · 上限 {{ r.ceiling.toFixed(0) }}</template>
                </span>
              </div>
              <div class="magicflow-ceiling-bar">
                <i :style="{ width: Math.min(r.pct, 100) + '%' }" :class="{ 'is-full': r.pct >= 85 }" />
              </div>
              <div class="magicflow-ceiling-row__foot">
                <span>占用 {{ r.pct }}%</span>
                <span>{{ r.seeds }} 种</span>
              </div>
            </div>
            <div v-if="!siteCeilingRows.length" class="magicflow-ceiling-empty">暂无数据（任务尚未产出统计）</div>
          </div>
        </div>
      </VCard>
    </VDialog>

    <VDialog v-model="siteReportOpen" max-width="48rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-sitereport-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">站点报表</span>
          <VChip v-if="siteReportLoading" size="x-small" color="grey" variant="tonal">加载中</VChip>
          <span class="magicflow-ops-dialog__spacer" />
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="siteReportLoading" @click="loadSiteReport(false)" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="siteReportOpen = false" />
        </header>
        <div class="magicflow-ops-dialog__sub magicflow-sitereport__bar">
          <VSelect
            v-model="siteReportSite"
            :items="siteReportSites.map(s => ({ title: `${s.name || s.domain}${s.domain ? ' · ' + s.domain : ''}`, value: s.domain || s.name }))"
            density="compact"
            variant="outlined"
            hide-details
            class="magicflow-sitereport__site"
            @update:model-value="loadSiteReport()"
          />
          <VBtn
            size="small"
            variant="tonal"
            :prepend-icon="siteReportLive ? 'mdi-radar' : 'mdi-cloud-download-outline'"
            :loading="siteReportLoading"
            @click="loadSiteReport(true)"
          >H&R 现抓</VBtn>
        </div>
        <div class="magicflow-ops-dialog__body">
          <div class="magicflow-sitereport__stats">
            <div class="magicflow-sitereport__stat" title="该站点在本机下载器里的全部种子（含做种/下载中/暂停/静默）"><b>{{ siteReportSummary.total || 0 }}</b><span>本站种子</span></div>
            <div class="magicflow-sitereport__stat"><b>{{ (siteReportSummary.size_gb || 0).toFixed(1) }}</b><span>GB</span></div>
            <div class="magicflow-sitereport__stat is-danger"><b>{{ siteReportSummary.hr_owed || 0 }}</b><span>欠 H&amp;R</span></div>
            <div class="magicflow-sitereport__stat is-danger"><b>{{ siteReportSummary.hr_missing || 0 }}</b><span>本机缺失</span></div>
          </div>
          <div class="magicflow-sitereport__chips">
            <VChip
              size="small"
              :color="siteReportFilter ? 'grey' : 'primary'"
              :variant="siteReportFilter ? 'tonal' : 'flat'"
              style="cursor: pointer"
              @click="siteReportFilter = ''"
            >全部 {{ siteReportSummary.total || 0 }}</VChip>
            <VChip
              v-for="b in SITE_REPORT_BUCKETS"
              :key="b.key"
              size="small"
              :color="b.color"
              :variant="siteReportFilter === b.key ? 'flat' : 'tonal'"
              style="cursor: pointer"
              @click="siteReportFilter = siteReportFilter === b.key ? '' : b.key"
            >{{ b.key }} {{ (siteReportSummary.by_bucket || {})[b.key] || 0 }}</VChip>
          </div>
          <div class="magicflow-ops-dialog__sub">
            明细 {{ siteReportItems.length }} / {{ siteReportSummary.total || 0 }}{{ siteReportFilter ? ' · 只看「' + siteReportFilter + '」' : ' · 点分类可筛选' }}
          </div>
          <div v-if="siteReport.hr && siteReport.hr.error" class="magicflow-sitereport__err">
            H&amp;R 对账（{{ siteReport.hr.source }}）：{{ siteReport.hr.error }}
          </div>
          <div v-else-if="siteReport.hr && siteReport.hr.records_total != null" class="magicflow-sitereport__note">
            H&amp;R 对账（{{ siteReport.hr.source }}）：站点欠 {{ siteReport.hr.records_total }} 条，本机缺失 {{ siteReport.hr.missing }} 条{{ siteReport.hr.hash_coverage_complete ? '' : '（部分未覆盖）' }}
          </div>
          <div class="magicflow-sitereport__list">
            <div v-for="it in siteReportItems" :key="it.hash" class="magicflow-sitereport__row">
              <VChip size="x-small" :color="siteReportBucketColor(it.bucket)" variant="tonal" class="magicflow-sitereport__row-b">{{ it.bucket }}</VChip>
              <div class="magicflow-sitereport__row-main">
                <div class="magicflow-sitereport__row-t" :title="it.title">{{ it.title || it.hash }}</div>
                <div class="magicflow-sitereport__row-s">{{ siteReportItemSub(it) }}</div>
              </div>
              <span class="magicflow-sitereport__row-size">{{ (it.size_gb || 0).toFixed(2) }}G</span>
            </div>
            <div v-if="!siteReportLoading && !siteReportItems.length" class="magicflow-ceiling-empty">该站点暂无种子（或未选择站点）</div>
          </div>
        </div>
      </VCard>
    </VDialog>

    <VDialog v-model="hrBillsOpen" max-width="48rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-hrbills-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">H&amp;R 账单</span>
          <VChip v-if="hrBillsLoading" size="x-small" color="grey" variant="tonal">加载中</VChip>
          <VChip v-else-if="hrBillsTotals.breached" size="x-small" color="deep-orange" variant="tonal">{{ hrBillsTotals.breached }} 违约</VChip>
          <VChip v-if="hrBillsTotals.at_risk" size="x-small" color="warning" variant="tonal">{{ hrBillsTotals.at_risk }} 临近到期</VChip>
          <span class="magicflow-ops-dialog__spacer" />
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="hrBillsLoading" @click="loadHrBills(false)" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="hrBillsOpen = false" />
        </header>
        <div class="magicflow-ops-dialog__body">
          <div class="magicflow-sitereport__stats">
            <div class="magicflow-sitereport__stat"><b>{{ hrBillsTotals.bills || 0 }}</b><span>账单</span></div>
            <div class="magicflow-sitereport__stat is-danger"><b>{{ hrBillsTotals.active || 0 }}</b><span>欠债</span></div>
            <div class="magicflow-sitereport__stat is-danger"><b>{{ hrBillsTotals.breached || 0 }}</b><span>违约</span></div>
            <div class="magicflow-sitereport__stat is-danger"><b>{{ hrBillsTotals.missing || 0 }}</b><span>本机缺失</span></div>
            <div class="magicflow-sitereport__stat" :class="hrBillsTotals.at_risk ? 'is-danger' : ''"><b>{{ hrBillsTotals.at_risk || 0 }}</b><span>临近到期</span></div>
          </div>
          <div class="magicflow-hrbills__list">
            <div v-for="s in hrBillsSites" :key="s.domain" class="magicflow-hrbills__card">
              <div class="magicflow-hrbills__head">
                <span class="magicflow-hrbills__name">{{ s.name || s.domain }}</span>
                <VChip v-if="s.per_torrent_hr" size="x-small" color="purple" variant="tonal">逐种</VChip>
                <VChip v-if="s.rule_source" size="x-small" color="grey" variant="tonal">{{ s.rule_source }}</VChip>
                <span class="magicflow-ops-dialog__spacer" />
                <span class="magicflow-hrbills__nums">欠 {{ s.owed }} · 在qb {{ s.in_qb }} · 缺 {{ s.missing }}<template v-if="s.at_risk"> · ⚠临期 {{ s.at_risk }}</template></span>
              </div>
              <div class="magicflow-hrbills__chips">
                <VChip
                  v-for="(n, st) in s.bills"
                  :key="st"
                  size="x-small"
                  :color="hrBillStateColor(st)"
                  variant="tonal"
                >{{ st }} {{ n }}</VChip>
                <VChip v-if="s.window_h" size="x-small" color="blue-grey" variant="tonal">窗口 {{ (s.window_h / 24).toFixed(1) }}d</VChip>
              </div>
              <div v-if="s.at_risk" class="magicflow-ops-dialog__sub">
                临近到期：
                <span v-for="(it, i) in hrBillsAtRisk(s)" :key="it.hash">{{ i ? '、' : '' }}{{ it.title || it.hash.slice(0, 8) }}（剩 {{ fmtHoursLeft(it.hours_left) }} / 需 {{ it.due_h }}h）</span>
              </div>
            </div>
            <div v-if="!hrBillsLoading && !hrBillsSites.length" class="magicflow-ceiling-empty">暂无 H&amp;R 账单（无欠债站）</div>
          </div>
        </div>
      </VCard>
    </VDialog>

    <VDialog v-model="seedHealthOpen" max-width="48rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-seedhealth-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">挂种健康度自检</span>
          <VChip v-if="seedHealthLoading" size="x-small" color="grey" variant="tonal">加载中</VChip>
          <VChip v-else-if="seedHealthAtRisk.length" size="x-small" color="error" variant="tonal">{{ seedHealthAtRisk.length }} 风险</VChip>
          <span class="magicflow-ops-dialog__spacer" />
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="seedHealthLoading" @click="loadSeedHealth()" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="seedHealthOpen = false" />
        </header>
        <div class="magicflow-ops-dialog__body">
          <div class="magicflow-sitereport__stats">
            <div class="magicflow-sitereport__stat"><b>{{ seedHealth.scanned || 0 }}</b><span>qB 种子</span></div>
            <div class="magicflow-sitereport__stat is-danger"><b>{{ seedHealthCounts.ghost || 0 }}</b><span>空转</span></div>
            <div class="magicflow-sitereport__stat is-danger"><b>{{ seedHealthCounts.partial || 0 }}</b><span>缺文件</span></div>
            <div class="magicflow-sitereport__stat"><b>{{ (seedHealthBytes.ghost_gb || 0).toFixed(1) }}</b><span>空转 GB</span></div>
            <div class="magicflow-sitereport__stat" :class="seedHealthCounts.not_in_qb ? 'is-danger' : ''"><b>{{ seedHealthCounts.not_in_qb || 0 }}</b><span>已消失</span></div>
          </div>
          <div class="magicflow-sitereport__chips">
            <VChip
              size="small"
              :color="seedHealthOnly === 'all' ? 'primary' : 'grey'"
              :variant="seedHealthOnly === 'all' ? 'flat' : 'tonal'"
              style="cursor: pointer"
              @click="seedHealthOnly = 'all'"
            >全部 {{ (seedHealthCounts.ghost || 0) + (seedHealthCounts.partial || 0) + (seedHealthCounts.normal || 0) }}</VChip>
            <VChip
              size="small"
              color="error"
              :variant="seedHealthOnly === 'ghost' ? 'flat' : 'tonal'"
              style="cursor: pointer"
              @click="seedHealthOnly = seedHealthOnly === 'ghost' ? 'all' : 'ghost'"
            >空转 {{ seedHealthCounts.ghost || 0 }}</VChip>
            <VChip
              size="small"
              color="warning"
              :variant="seedHealthOnly === 'partial' ? 'flat' : 'tonal'"
              style="cursor: pointer"
              @click="seedHealthOnly = seedHealthOnly === 'partial' ? 'all' : 'partial'"
            >缺文件 {{ seedHealthCounts.partial || 0 }}</VChip>
          </div>
          <div v-if="seedHealth.probe_truncated" class="magicflow-ops-dialog__sub">
            候选过多，已截断逐文件核盘（未核 {{ seedHealth.probe_truncated }} 个）；先看已命中的异常。
          </div>
          <div v-if="seedHealthAtRisk.length" class="magicflow-hrbills__list">
            <div class="magicflow-ops-dialog__sub">⚠ 空转且仍欠 H&amp;R（有删除/清理风险）：</div>
            <div v-for="it in seedHealthAtRisk" :key="it.hash" class="magicflow-sitereport__row">
              <VChip size="x-small" color="error" variant="tonal" class="magicflow-sitereport__row-b">欠H&amp;R</VChip>
              <div class="magicflow-sitereport__row-main">
                <div class="magicflow-sitereport__row-t" :title="it.title">{{ it.title || it.hash }}</div>
                <div class="magicflow-sitereport__row-s">{{ it.site }} · 还需 {{ it.need_left }}h（账单 {{ it.state }}/{{ it.rule }}）</div>
              </div>
              <span class="magicflow-sitereport__row-size">{{ (it.size_gb || 0).toFixed(2) }}G</span>
            </div>
          </div>
          <div class="magicflow-ops-dialog__sub">
            明细 {{ seedHealthItems.length }} / {{ (seedHealth.value.items || []).length }}<template v-if="seedHealth.site_filter"> · 只看 {{ seedHealth.site_filter }}</template>
          </div>
          <div class="magicflow-sitereport__list">
            <div v-for="it in seedHealthItems" :key="it.hash" class="magicflow-sitereport__row">
              <VChip size="x-small" :color="seedHealthBucketColor(it.bucket)" variant="tonal" class="magicflow-sitereport__row-b">{{ seedHealthBucketLabel(it.bucket) }}</VChip>
              <div class="magicflow-sitereport__row-main">
                <div class="magicflow-sitereport__row-t" :title="it.title">{{ it.title || it.hash }}</div>
                <div class="magicflow-sitereport__row-s">
                  {{ it.site }} · {{ it.qb_state }}
                  <template v-if="it.files_exist != null"> · 文件 {{ it.files_exist }}/{{ it.files_total }}</template>
                  <template v-if="it.hr"> · 欠H&amp;R 还需 {{ it.hr.need_left }}h</template>
                  <template v-if="(it.protected || []).length"> · 保护 {{ it.protected.join('/') }}</template>
                </div>
              </div>
              <span class="magicflow-sitereport__row-size">{{ (it.size_gb || 0).toFixed(2) }}G</span>
            </div>
            <div v-if="!seedHealthLoading && !seedHealthItems.length" class="magicflow-ceiling-empty">没有命中条件的种子</div>
          </div>
        </div>
      </VCard>
    </VDialog>

    <VDialog v-model="signinOpen" max-width="40rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-signin-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">签到</span>
          <VChip v-if="signinReport.enabled" size="x-small" color="success" variant="tonal">已启用</VChip>
          <VChip v-else-if="signinReportLoading" size="x-small" color="grey" variant="tonal">加载中</VChip>
          <VChip v-else size="x-small" color="grey" variant="tonal">已关闭</VChip>
          <span class="magicflow-ops-dialog__spacer" />
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="signinReportLoading" @click="loadSigninReport" />
          <VBtn icon="mdi-tune-variant" size="small" variant="text" aria-label="设置" @click="signinOpen = false; openSettings('signin')" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="signinOpen = false" />
        </header>
        <div class="magicflow-ops-dialog__sub">共 {{ signinReportTodayRows.length }} 个站点 · 近 7 天记录（右上设置进入配置）</div>
        <div class="magicflow-ops-dialog__body">
          <div class="magicflow-signin-stats">
            <div class="magicflow-signin-stat is-ok">
              <div class="magicflow-signin-stat__v">{{ signinTodayCounts.ok }}</div>
              <div class="magicflow-signin-stat__l">今日成功</div>
            </div>
            <div class="magicflow-signin-stat" :class="signinTodayCounts.fail ? 'is-fail' : ''">
              <div class="magicflow-signin-stat__v">{{ signinTodayCounts.fail }}</div>
              <div class="magicflow-signin-stat__l">今日失败</div>
            </div>
            <div class="magicflow-signin-stat" :class="signinTodayCounts.pending ? 'is-pending' : ''">
              <div class="magicflow-signin-stat__v">{{ signinTodayCounts.pending }}</div>
              <div class="magicflow-signin-stat__l">待执行</div>
            </div>
            <div class="magicflow-signin-stat">
              <div class="magicflow-signin-stat__v">{{ (signinMatrix.stats.ok + signinMatrix.stats.fail) ? Math.round(signinMatrix.stats.ok * 100 / (signinMatrix.stats.ok + signinMatrix.stats.fail)) + '%' : '—' }}</div>
              <div class="magicflow-signin-stat__l">近 7 天成功率</div>
            </div>
          </div>

          <div class="magicflow-signin-actions">
            <VBtn size="small" color="primary" variant="flat" prepend-icon="mdi-calendar-check" :loading="signinRunning" @click="runSigninNow('sign')">立即签到</VBtn>
            <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-login-variant" :loading="signinRunning" @click="runSigninNow('login')">立即登录</VBtn>
          </div>

          <div v-if="signinKeepalive.length" class="magicflow-settings-block">
            <div class="magicflow-settings-block__head"><VIcon icon="mdi-account-clock-outline" size="16" /> 账号保活（站点登入口径）</div>
            <div class="magicflow-keepalive">
              <div
                v-for="k in signinKeepalive"
                :key="k.site_id"
                class="magicflow-keepalive-row"
                :class="'is-' + (k.level || 'unknown')"
              >
                <span class="magicflow-keepalive-row__name" :title="k.domain + (k.exempt ? ' · 豁免：' + k.exempt : '')">{{ k.site_name }}</span>
                <span class="magicflow-keepalive-row__time">
                  最后登入 <b>{{ k.last_login || '—' }}</b>
                  <template v-if="k.last_browse && k.last_browse !== k.last_login"> · 最后访问 {{ k.last_browse }}</template>
                  <template v-if="k.last_seen_kind === '浏览'">（按更早的「{{ k.last_seen }}」保守起算）</template>
                </span>
                <span class="magicflow-keepalive-row__left" :class="'is-' + (k.level || 'unknown')">
                  <template v-if="k.days_left !== null && k.days_left !== undefined">
                    距 {{ k.keep_days }} 天红线还有 {{ k.days_left }} 天
                  </template>
                  <template v-else>暂无登入记录</template>
                </span>
              </div>
              <p class="magicflow-field__sub">
                {{ signinKeepaliveNote }} → 插件是第三方工具（不算登入），到点请用浏览器 / 官方 App 亲自登一次。
              </p>
            </div>
          </div>

          <div class="magicflow-settings-block">
            <div class="magicflow-settings-block__head"><VIcon icon="mdi-clipboard-check-outline" size="16" /> 今日（{{ signinReport.today || '—' }}）</div>
            <div class="magicflow-signin-filters">
              <VChip
                v-for="f in signinFilterItems"
                :key="f.value"
                size="x-small"
                :color="signinFilter === f.value ? f.color : undefined"
                :variant="signinFilter === f.value ? 'flat' : 'tonal'"
                @click="signinFilter = f.value"
              >{{ f.label }}</VChip>
              <VTextField
                v-model="signinSearch"
                class="magicflow-signin-search"
                density="compact"
                variant="solo-filled"
                flat
                hide-details
                clearable
                placeholder="搜索站点"
                prepend-inner-icon="mdi-magnify"
              />
            </div>
            <div v-if="signinTodayList.length" class="magicflow-signin-today">
              <div v-for="row in signinTodayList" :key="row.site_id" class="magicflow-signin-row" :class="'is-' + row.status">
                <span class="magicflow-signin-row__dot" :class="'is-' + row.status" />
                <span class="magicflow-signin-row__name">{{ row.site_name }}</span>
                <span class="magicflow-signin-row__msg" :title="row.msg">{{ row.msg || '待执行' }}</span>
              </div>
            </div>
            <p v-else class="magicflow-field__sub">还没有站点结果。先到右上齿轮里勾选要签到的站点。</p>
          </div>

          <div v-if="signinMatrix.rows.length" class="magicflow-settings-block">
            <div class="magicflow-settings-block__head"><VIcon icon="mdi-calendar-clock" size="16" /> 近 7 天（{{ signinMatrix.rows.length }} 站）</div>
            <div class="magicflow-signin-matrix">
              <div class="magicflow-signin-matrix__row is-head">
                <span class="magicflow-signin-matrix__name">站点</span>
                <span v-for="d in signinMatrix.dates" :key="d" class="magicflow-signin-matrix__date">{{ signinDateLabel(d) }}</span>
              </div>
              <div v-for="row in signinMatrix.rows" :key="row.sid" class="magicflow-signin-matrix__row">
                <span class="magicflow-signin-matrix__name" :title="row.name">{{ row.name }}</span>
                <span v-for="c in row.cells" :key="c.date" class="magicflow-signin-cell" :class="'is-' + c.status" :title="c.date + ' ' + signinStatusText(c.status)" />
              </div>
            </div>
            <div class="magicflow-signin-legend">
              <span><i class="magicflow-signin-cell is-ok" />成功</span>
              <span><i class="magicflow-signin-cell is-signfail" />签到失败</span>
              <span><i class="magicflow-signin-cell is-loginfail" />登录失败</span>
              <span><i class="magicflow-signin-cell is-fail" />都失败</span>
              <span><i class="magicflow-signin-cell is-pending" />待执行</span>
              <span><i class="magicflow-signin-cell is-none" />无记录</span>
            </div>
          </div>
        </div>
      </VCard>
    </VDialog>

    <VDialog v-model="opsOpen" max-width="46rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-ops-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">操作记录</span>
          <span class="magicflow-ops-dialog__spacer" />
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="opsLoadingAll" @click="opsScope === 'all' ? loadOperationsAll() : loadOperations(selectedTaskId)" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="opsOpen = false" />
        </header>
        <div class="magicflow-ops-dialog__sub">
          <template v-if="opsScope === 'all'">全部任务 · 跨站点汇总 · 每次执行 / 选种 / 删种 / 保护 / 标签 的流水（最近 100 条）</template>
          <template v-else>{{ selectedTask ? (selectedTask.name || '当前任务') : '未选择任务' }} · 每次执行 / 选种 / 删种 / 保护 / 标签 的流水</template>
        </div>
        <div class="magicflow-ops-dialog__tabs">
          <VBtn size="small" :variant="opsView === 'flow' ? 'tonal' : 'text'" prepend-icon="mdi-format-list-bulleted" @click="opsView = 'flow'">全部流水</VBtn>
          <VBtn size="small" :variant="opsView === 'reseed' ? 'tonal' : 'text'" prepend-icon="mdi-content-duplicate" @click="opsView = 'reseed'">辅种流水</VBtn>
          <VBtn size="small" :variant="opsView === 'timeline' ? 'tonal' : 'text'" prepend-icon="mdi-timeline-clock-outline" @click="opsView = 'timeline'">事件流</VBtn>
        </div>
        <div class="magicflow-ops-dialog__body">
          <div v-if="opsView === 'timeline'" class="mf-timeline__bar">
            <span class="mf-timeline__label">级别</span>
            <VSelect
              v-model="eventLevel"
              :items="EVENT_LEVELS"
              item-title="label"
              item-value="value"
              density="compact"
              variant="outlined"
              hide-details
              class="mf-timeline__select"
            />
            <VSpacer />
            <span class="mf-timeline__count">{{ eventRows.length }} 条 · 最新在前</span>
          </div>
          <div v-if="opsView === 'timeline'" class="mf-timeline">
            <article
              v-for="row in eventRows"
              :key="row.id"
              class="mf-timeline__row"
              :class="`is-${row.level}`"
            >
              <VIcon :icon="eventLevelIcon(row.level)" size="16" class="mf-timeline__icon" />
              <div class="mf-timeline__main">
                <div class="mf-timeline__head">
                  <strong>{{ row.action || row.kind }}</strong>
                  <span class="mf-timeline__ts">{{ formatDateTime(row.ts) }}</span>
                </div>
                <div class="mf-timeline__meta">
                  <VChip v-if="row.task_name" size="x-small" variant="tonal">{{ row.task_name }}</VChip>
                  <VChip v-if="row.site_name" size="x-small" variant="text">{{ row.site_name }}</VChip>
                  <VChip v-if="row.count" size="x-small" variant="text">{{ row.count }} 种</VChip>
                  <span v-if="row.reason" class="mf-timeline__reason">{{ row.reason }}</span>
                </div>
                <div v-if="row.error" class="mf-timeline__error">{{ row.error }}</div>
              </div>
            </article>
            <div v-if="eventsLoading" class="magicflow-table-empty">加载中…</div>
            <div v-else-if="!eventRows.length" class="magicflow-table-empty">暂无事件</div>
          </div>
          <div v-if="opsView !== 'timeline'" class="magicflow-ops-filter">
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
          <div v-if="opsView === 'reseed'" class="magicflow-reseed">
            <div class="magicflow-reseed__head">
              <span>时间</span><span>任务</span><span>动作</span><span>资源</span><span class="is-num">大小</span><span>阶段</span>
            </div>
            <div v-for="row in reseedRows" :key="row.key" class="magicflow-reseed__row">
              <span class="is-time">{{ formatDateTime(row.ts) }}</span>
              <span class="is-task" :title="row.task">{{ row.task }}</span>
              <span><VChip size="x-small" variant="tonal" color="primary">{{ row.action }}</VChip></span>
              <span class="is-title" :title="row.reason || row.title">{{ row.title || row.hash || '—' }}</span>
              <span class="is-num">{{ row.size_gb ? Number(row.size_gb).toFixed(2) + 'G' : '—' }}</span>
              <span class="is-stage" :class="row.state === 'failed' ? 'text-error' : ''">{{ row.stage }}</span>
            </div>
            <div v-if="!reseedRows.length" class="magicflow-table-empty">暂无辅种流水</div>
          </div>
          <div v-else-if="opsView === 'flow'" class="magicflow-events">
            <article v-for="record in opsFiltered" :key="record.operation_id">
              <VIcon :icon="operationIcon(record.kind)" :color="operationColor(record)" />
              <div>
                <strong>
                  {{ operationKindText(record.kind) }}
                  <VChip v-if="opsScope === 'all'" size="x-small" variant="text" class="ml-1 magicflow-ops-dialog__task">{{ taskLabel(record.task_id) }}</VChip>
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
        </div>
      </VCard>
    </VDialog>

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

    <VDialog v-model="settingsDialog" max-width="40rem" :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-settings-dialog">
        <header class="magicflow-settings-dialog__head">
          <VBtn
            v-if="isNarrow && settingsPane === 'form'"
            icon="mdi-arrow-left"
            size="small"
            variant="text"
            aria-label="返回设置目录"
            @click="backToSettingsDir"
          />
          <span class="magicflow-settings-dialog__title">{{ isNarrow && settingsPane === 'form' ? settingsTabLabel(settingsTab) : '插件设置' }}</span>
          <span class="magicflow-scope-tag">全局</span>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="settingsDialog = false" />
        </header>

        <div v-if="!isNarrow || settingsPane === 'dir'" class="magicflow-settings-nav" ref="settingsNavEl">
          <button
            v-for="t in MF_SETTINGS_TABS"
            :key="t.key"
            type="button"
            class="magicflow-settings-nav__item"
            :class="{ 'is-active': settingsTab === t.key }"
            @click="openSettingsTab(t.key)"
          >
            <VIcon :icon="t.icon" size="18" />
            <span>{{ t.label }}</span>
          </button>
        </div>

        <VTabs v-model="settingsTab" class="magicflow-settings-dialog__tabs" density="comfortable" show-arrows>
          <VTab value="general" class="magicflow-settings-tab">常规</VTab>
          <VTab value="downloader" class="magicflow-settings-tab">下载与目录</VTab>
          <VTab value="template" class="magicflow-settings-tab">默认任务模板</VTab>
          <VTab value="iyuu" class="magicflow-settings-tab">IYUU 辅种</VTab>
          <VTab value="fallback" class="magicflow-settings-tab">元数据兜底</VTab>
          <VTab value="cloud" class="magicflow-settings-tab">云盘归档</VTab>
          <VTab value="exam" class="magicflow-settings-tab">考核</VTab>
          <VTab value="signin" class="magicflow-settings-tab">签到</VTab>
          <VTab value="live" class="magicflow-settings-tab">站点监控</VTab>
          <VTab value="recommend" class="magicflow-settings-tab">推荐</VTab>
          <VTab value="crossseed" class="magicflow-settings-tab">跨站</VTab>
          <VTab value="rules" class="magicflow-settings-tab">站点规则</VTab>
          <VTab value="tags" class="magicflow-settings-tab">标签管理</VTab>
        </VTabs>
        <VDivider v-if="!isNarrow || settingsPane === 'form'" />

        <div v-if="!isNarrow || settingsPane === 'form'" class="magicflow-settings-dialog__body">
          <div v-if="settingsTab === 'general'" class="magicflow-settings-form">
            <VSwitch v-model="settingsDraft.enabled" label="启用插件（总开关）" color="primary" hide-details inset />
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
              <VTextField
                v-model.number="settingsDraft.seed_up_limit_kbps"
                type="number"
                min="0"
                step="50"
                label="挂种单种上传限速（KB/s）"
                hint="我们管控的魔力 / 推荐 / 跨站种：单种限速，默认 200；不在管控下的种不限速；0 = 全不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.brush_seed_up_limit_kbps"
                type="number"
                min="0"
                step="256"
                label="刷流单种上传限速（KB/s）"
                hint="我们管控的刷流种：要冲量，默认 5120（=5 MB/s）；0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <VSwitch v-model="settingsDraft.debug_log" label="调试日志" color="primary" hide-details inset />
            <VSwitch v-model="settingsDraft.compact_mode" label="紧凑模式" color="primary" hide-details inset />
            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-view-grid-outline" size="16" /> 顶栏功能磁贴</div>
              <p class="magicflow-field__sub">
                关掉的磁贴不再在顶栏 / 手机「功能」里显示入口。<strong>只影响入口显示</strong>：
                功能本身在各自的设置页里单独开关，这里不动任何功能逻辑。
              </p>
              <div class="magicflow-tile-switches">
                <VSwitch
                  v-for="t in TILE_OPTIONS"
                  :key="t.key"
                  :model-value="tileShown(t.key)"
                  :label="t.label"
                  :prepend-icon="t.icon"
                  color="primary"
                  hide-details
                  inset
                  density="comfortable"
                  @update:model-value="v => setTileShown(t.key, v)"
                />
              </div>
              <p class="magicflow-field__sub">
                已显示 {{ TILE_OPTIONS.filter(t => tileShown(t.key)).length }} / {{ TILE_OPTIONS.length }}
              </p>
            </div>
            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-lifebuoy" size="16" /> 死种补源（rescue）</div>
              <p class="magicflow-field__sub">
                未下完 + 长时间 0 速，且<strong>欠 H&amp;R 或手动保留</strong>的种 → 去<strong>无 H&amp;R 的他站</strong>下同一 Release 补齐（补完 recheck 认文件）。
                独立页面在顶栏「补源」按钮，这里只调参数。
              </p>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-model.number="settingsDraft.rescue_stall_hours"
                  type="number"
                  min="0"
                  max="720"
                  step="1"
                  label="停滞阈值（小时）"
                  hint="0 速持续超过该时长才纳入补源（默认 6；越小越灵敏）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.rescue_max_candidates"
                  type="number"
                  min="1"
                  max="10"
                  step="1"
                  label="每目标候选数"
                  hint="只列无 H&R 站的同 Release 候选（默认 3）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
              </div>
            </div>
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

            <VDivider class="my-3" />
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
            <p class="magicflow-settings-hint">
              任务保存目录：仅对魔流生效，不影响下载器全局设置。
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
              <VBtn
                v-if="settingsDraft.iyuu_token"
                variant="text"
                color="error"
                size="small"
                prepend-icon="mdi-close-circle-outline"
                @click="clearIyuuToken"
              >清空</VBtn>
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

          <div v-else-if="settingsTab === 'reseed'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              <strong>全站辅种</strong>（本机驱动）：本机<strong>已有文件</strong>的资源 → 去各站找<strong>同一 Release</strong> 的种子挂上去落户。
              <strong>零下载</strong>：暂停加入 → recheck 校验 → <strong>通过才做种</strong>，不通过自动撤销。
              方向与「跨站取种」相反（那是本机没有、去他站免费下回来）。
            </p>
            <p class="magicflow-settings-hint magicflow-settings-hint--warn">
              ⚠️ 挂种要拼目标站下载链（IYUU 站点表模板 + passkey / API 直链）。passkey 能自动抓；抓不到的站会记「缺料」跳过。
              每站有每日上限，建议先<strong>干跑</strong>看清能挂多少再关干跑。
            </p>

            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.reseed_enabled" label="启用全站辅种" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.reseed_dry" label="干跑（只算不挂）" color="primary" hide-details inset :disabled="!settingsDraft.reseed_enabled" />
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-web" size="16" /> 目标站点（留空 = 全部有 IYUU 编号的站）</div>
              <VSelect
                v-model="settingsDraft.reseed_sites"
                :items="reseedSiteOptions"
                label="铺设站点"
                multiple
                chips
                closable-chips
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <span class="magicflow-field__sub">已选 {{ (settingsDraft.reseed_sites || []).length }} 个 · 不在 IYUU 站点表里的站当不了目标</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-tune" size="16" /> 限量</div>
              <div class="magicflow-settings-grid">
                <VTextField v-model.number="settingsDraft.reseed_daily_per_site" type="number" label="每站每天挂种上限" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.reseed_batch" type="number" label="每轮最多处理（对）" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.reseed_min_size_gb" type="number" label="最小体积 GB" variant="outlined" density="comfortable" hide-details />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-content-duplicate" size="16" /> 运行 / 状态
                <VSpacer />
                <VBtn size="small" variant="text" prepend-icon="mdi-refresh" class="me-2" @click="loadReseed()">刷新</VBtn>
                <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-play" :loading="reseedRunning" @click="runReseed()">
                  {{ settingsDraft.reseed_dry ? '立即干跑一轮' : '立即跑一轮' }}
                </VBtn>
              </div>
              <div v-if="reseedState" class="magicflow-reseedpanel">
                <div class="magicflow-reseedpanel__row">
                  <VChip size="small" variant="tonal" :color="reseedState.enabled ? 'success' : 'grey'">{{ reseedState.enabled ? '已启用' : '未启用' }}</VChip>
                  <VChip size="small" variant="tonal" :color="reseedState.dry ? 'warning' : 'grey'">{{ reseedState.dry ? '干跑' : '实挂' }}</VChip>
                  <VChip v-if="reseedState.running" size="small" variant="tonal" color="info">运行中…</VChip>
                  <span class="magicflow-field__sub">IYUU 云端 {{ reseedState.debug?.token ? '✓' : '✗' }} · 云端站点表 {{ reseedState.debug?.iyuu_sites ?? 0 }} · 可辅站 {{ reseedState.debug?.mapped ?? 0 }}</span>
                </div>
                <div class="magicflow-reseedpanel__row">
                  <span class="magicflow-field__sub">本机上报 {{ reseedState.cloud?.hashes ?? 0 }} 颗 · IYUU 云端命中候选 {{ reseedState.cloud?.candidates ?? 0 }} 对</span>
                </div>
                <div v-if="reseedState.last && reseedState.last.at" class="magicflow-reseedpanel__row">
                  <span class="magicflow-field__sub">
                    上轮 {{ fmtTs(reseedState.last.at) }}：计划 {{ reseedState.last.plan ?? 0 }} · 挂上 {{ reseedState.last.ok ?? 0 }} · 已有 {{ reseedState.last.have ?? 0 }} · 不一致 {{ reseedState.last.mismatch ?? 0 }} · 缺链 {{ reseedState.last.nourl ?? 0 }} · 缺 PV {{ reseedState.last.pv ?? 0 }} · 失败 {{ reseedState.last.fail ?? 0 }} · 干跑可挂 {{ reseedState.last.would ?? 0 }}（{{ reseedState.last.duration ?? 0 }}s）
                  </span>
                </div>
                <div class="magicflow-reseedpanel__sites">
                  <div class="magicflow-reseedpanel__head">
                    <span>站点</span><span>IYUU</span><span>passkey</span><span>今日 / 上限</span>
                  </div>
                  <div v-for="s in (reseedState.sites || [])" :key="s.sid" class="magicflow-reseedpanel__line">
                    <span>{{ s.name }}<em v-if="s.domain"> · {{ s.domain }}</em></span>
                    <span>#{{ s.sid }}</span>
                    <span>{{ s.passkey_ok ? '✓' : '—' }}</span>
                    <span>{{ s.done_today }} / {{ s.cap }}</span>
                  </div>
                  <div v-if="!(reseedState.sites || []).length" class="magicflow-table-empty">没有可辅种的站点（与 IYUU 站点表对不上）</div>
                </div>
                <div class="magicflow-reseedpanel__row">
                  <span class="magicflow-field__sub">账本：{{ Object.entries(reseedState.ledger || {}).map(([k, v]) => `${k} ${v}`).join(' · ') || '空（还没跑过）' }}</span>
                </div>
              </div>
              <p v-else class="magicflow-field__sub">加载中…</p>
            </div>
          </div>

          <div v-else-if="settingsTab === 'claim'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              <strong>认领</strong>：把「我们正在做种」的种子在<strong>站点侧认领</strong>掉，换取站点给的权益
              （CARPT：达标种子魔力奖励 = 正常值 <strong>×2</strong>）。它是「保种增值」动作，与刷流拿种解耦。
            </p>
            <p class="magicflow-settings-hint magicflow-settings-hint--warn">
              ⚠️ 认领是<strong>不可逆的对外写操作</strong>：站点侧不达标会<strong>扣魔力</strong>，主动放弃扣得更多。
              因此默认<strong>关闭</strong>且默认<strong>干跑</strong>；认领后的种子会进<strong>硬保护、永不自动删除</strong>。
            </p>

            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.claim_enabled" label="启用认领" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.claim_dry" label="干跑（只列不写）" color="primary" hide-details inset :disabled="!settingsDraft.claim_enabled" />
              <VSwitch v-model="settingsDraft.claim_exclude_zero_bonus" label="零魔种不认领" color="primary" hide-details inset />
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-web" size="16" /> 站点白名单（留空 = 全部支持的站）</div>
              <VCombobox
                v-model="settingsDraft.claim_sites"
                :items="claimSiteOptions"
                label="认领站点（可多选 / 手输域名）"
                multiple
                chips
                closable-chips
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <span class="magicflow-field__sub">已选 {{ (settingsDraft.claim_sites || []).length }} 个 · 目前支持的站：{{ claimSiteOptions.join(' / ') || '（尚未探测，打开认领页后可见）' }}</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-tune" size="16" /> 限量 / 限速</div>
              <div class="magicflow-settings-grid">
                <VTextField v-model.number="settingsDraft.claim_daily_per_site" type="number" label="每站每天认领上限" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.claim_batch" type="number" label="单轮最多认领" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.claim_interval_sec" type="number" label="两次认领间隔（秒）" variant="outlined" density="comfortable" hide-details />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-shield-alert-outline" size="16" /> 安全阀（拿不准就留着）</div>
              <div class="magicflow-settings-grid">
                <VTextField v-model.number="settingsDraft.claim_min_age_days" type="number" label="最短发布天数（0=按站点规则）" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.claim_require_seeders" type="number" label="做种人数下限（0=不限）" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.claim_min_size_gb" type="number" label="体积下限 GB（0=不限）" variant="outlined" density="comfortable" hide-details />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-seal-variant" size="16" /> 运行 / 状态
                <VSpacer />
                <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-open-in-new" @click="openClaim()">打开认领页</VBtn>
              </div>
              <p class="magicflow-field__sub">先「扫描（干跑）」看能认领哪些，再逐条二次确认；对不熟悉的站建议长期保持干跑。</p>
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

          <div v-else-if="settingsTab === 'exam'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              把各站<strong>新手考核</strong>进度抓出来（上传/下载增量、平均做种时间、魔力/做种积分增量），
              并支持<strong>一键起任务</strong>去补未通过项。
              数据来源就是各站首页 <code>index.php</code> 的考核块 —— 魔流本来就抓这个页面拿实时数据，
              所以<strong>不额外消耗站点访问次数（PV）</strong>。
            </p>
            <p class="magicflow-settings-hint">
              <strong>已通过的考核默认不显示</strong>（过掉的就不占地方了）；想看全部就打开下面的「显示已通过」。
              考不过的站会算好缺口：上传差多少 → 刷流任务；魔力/积分差多少 → 魔力任务；平均做种时间不够 → 保持做种 + 多辅种（不用建任务）。
              下载类考核项（下载增量）<strong>只做提示、不建任务</strong>。
            </p>
            <p class="magicflow-settings-hint">
              魔流不做下载业务：<strong>不会创建任何下载任务</strong>，也不会为凑下载量去下非免费种。
              缺的下载量需要你自己安排；已通过/未通过都不会影响现有做种。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.exam_enabled" label="启用「新手考核」（关闭则不抓取、不解析、不显示）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.exam_include_pass" label="显示「已通过」的考核（默认只显示未通过的）" color="primary" hide-details inset />
            </div>
            <div class="magicflow-settings-field">
              <VSelect
                v-model="settingsDraft.exam_sites"
                :items="siteSelectItems"
                label="考核站点（不选 = 全部已配置 Cookie 的站点）"
                multiple
                chips
                closable-chips
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <p class="magicflow-settings-hint">选多少有多少：只盯你关心的站，不选就是全都盯。</p>
            </div>
            <p v-if="!settingsDraft.exam_enabled" class="magicflow-settings-hint magicflow-settings-hint--warn">
              当前处于<strong>关闭</strong>状态：不会去抓考核，也不会做任何额外请求。
            </p>
          </div>

          <div v-else-if="settingsTab === 'signin'" class="magicflow-settings-form">
            <div class="magicflow-signin-hero">
              <span class="magicflow-signin-hero__icon"><VIcon icon="mdi-calendar-check-outline" size="20" /></span>
              <div class="magicflow-signin-hero__body">
                <div class="magicflow-signin-hero__title">
                  <span>站点签到 / 模拟登录</span>
                  <VChip size="small" variant="tonal" :color="settingsDraft.signin_enabled ? 'success' : 'grey'">
                    {{ settingsDraft.signin_enabled ? '已启用' : '已关闭' }}
                  </VChip>
                </div>
                <div class="magicflow-signin-hero__desc">
                  勾选站点即可，其余全自动完成。
                </div>
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" size="16" /> 开关</div>
              <div class="magicflow-switch-list">
                <VSwitch v-model="settingsDraft.signin_enabled" label="启用站点签到 / 模拟登录" color="primary" hide-details inset density="comfortable" />
                <VSwitch v-model="settingsDraft.signin_notify" label="结果推送通知" color="primary" hide-details inset density="comfortable" :disabled="!settingsDraft.signin_enabled" />
              </div>
              <p v-if="!settingsDraft.signin_enabled" class="magicflow-field__sub">
                当前为关闭状态：不会签到、不会模拟登录，也不发任何请求。
              </p>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-web" size="16" /> 站点选择（勾选即生效）</div>
              <div class="magicflow-field-stack">
                <div class="magicflow-field">
                  <VSelect
                    v-model="settingsDraft.signin_sites"
                    :items="siteSelectItems"
                    label="签到站点"
                    multiple
                    chips
                    closable-chips
                    variant="outlined"
                    density="comfortable"
                    hide-details
                  />
                  <span class="magicflow-field__sub">已选 {{ (settingsDraft.signin_sites || []).length }} 个站点</span>
                </div>
                <div class="magicflow-field">
                  <VSelect
                    v-model="settingsDraft.signin_login_sites"
                    :items="siteSelectItems"
                    label="模拟登录站点"
                    multiple
                    chips
                    closable-chips
                    variant="outlined"
                    density="comfortable"
                    hide-details
                  />
                  <span class="magicflow-field__sub">已选 {{ (settingsDraft.signin_login_sites || []).length }} 个站点 · 保活 Cookie + 刷新站点数据</span>
                </div>
              </div>
            </div>

            <div class="magicflow-signin-actions">
              <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-chart-box-outline" @click="openSignin()">查看签到报表</VBtn>
              <span class="magicflow-field__sub">签到结果与近 7 天记录都在报表页</span>
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
            <p class="magicflow-settings-hint magicflow-settings-hint--warn">
              ⚠️ 多数站点有<strong>每日访问次数上限</strong>（实测 PTT：用户等级 300 PV/天，含刷流浏览）。
              采样太频会把配额打光 → 站点当天拒绝访问（连刷流也取不到种）。命中后魔流会自动<strong>停抓到次日凌晨</strong>并告警，
              但配额是共享的：<strong>建议按站点把采样周期放长</strong>（比如 15–30 分钟），给选种浏览留余量。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.live_enabled" label="启用站点实时数据 + 流量监控" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_notify" label="命中告警时推送通知" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_auto_stop" label="同时把该站「运行中」任务切「做种中」（停调度、不删种）" color="primary" hide-details inset />
            </div>

            <VDivider class="my-3" />
            <p class="magicflow-settings-hint">
              <strong>流量兜底</strong>：下载中被判「非免费」就干掉，避免白烧下载量。
              三处都会核对：<em>任务内</em>回种子详情页核对（开关在任务「高级」里，受本总开关约束）、
              <em>全局</em>用站点「正在下载」列表核对、<em>取种期间</em>核对来源站。共用下面这个总开关。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.promo_guard" label="启用流量兜底（关掉 = 下面三项都只告警、不动手）" color="primary" hide-details inset />
            </div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.live_kill_unfree" :disabled="!settingsDraft.promo_guard" label="全局：下载量异常增长 → 站点「正在下载」列表里非免费的种，从下载器干掉" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_kill_delete_files" :disabled="!settingsDraft.promo_guard || !settingsDraft.live_kill_unfree" label="干掉时连文件一起删（只动「下载中」且名称+体积对得上的种）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.crossseed_guard" :disabled="!settingsDraft.promo_guard" label="取种期间：核对来源站免费状态与下载量增量，判错就删种并拉黑该站（强烈建议）" color="primary" hide-details inset />
            </div>
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.crossseed_guard_pct"
                type="number"
                min="0"
                max="100"
                step="0.5"
                :disabled="!settingsDraft.promo_guard || !settingsDraft.crossseed_guard"
                label="下载增量阈值（体积的 %）"
                hint="来源站下载增量 > 目标体积 × 该值 即判定「不免费」，默认 5%"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.crossseed_guard_min_mb"
                type="number"
                min="0"
                step="10"
                :disabled="!settingsDraft.promo_guard || !settingsDraft.crossseed_guard"
                label="最小判定增量（MB）"
                hint="避免统计抖动误判，默认 50MB"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.crossseed_guard_interval_min"
                type="number"
                min="1"
                max="1440"
                step="1"
                :disabled="!settingsDraft.promo_guard || !settingsDraft.crossseed_guard"
                label="兜底核对间隔（分钟）"
                hint="同一来源站两次核对的间隔，默认 15 分钟（各花 1 次站点请求）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
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
                hint="评分高于该值才推荐，默认 7.5（评分源见左侧「评分来源」）"
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
                v-model="settingsDraft.recommend_douban_service_url"
                label="豆瓣服务地址"
                placeholder="http://magicflow-douban:18789"
                hint="独立服务 magicflow-douban 的地址，留空用默认；本地查询 <1ms，不受豆瓣限流影响"
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
            <div class="magicflow-settings-grid">
              <VSelect
                v-model="settingsDraft.recommend_rating_source"
                :items="ratingSourceItems"
                item-title="title"
                item-value="value"
                label="评分来源"
                hint="默认只用 TMDB；豆瓣优先走本地服务 magicflow-douban（不再直连豆瓣）"
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

          <div v-else-if="settingsTab === 'rules'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              <strong>全站 H&amp;R 的唯一入口</strong>：H&amp;R 有无 / 最短保种时长 / 做种上限都在这一页
              （跨站取种的「来源份」在兄弟站同样背 H&amp;R 义务，例：学校 BTSchool 要挂种 10 小时）。
              优先级：<strong>手填 &gt; 页面探测 &gt; 内置 &gt; 全局默认</strong>；
              探测遵循「宁保守勿乐观」—— 抓不到就保持原值，绝不假设「没有 H&amp;R」。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.rules_auto_refresh" label="每周自动逐站探测规则并入库" color="primary" hide-details inset />
            </div>

            <VDivider class="my-3" />
            <p class="magicflow-settings-hint">
              <strong>H&amp;R 来源</strong>：只认<strong>收件箱「欢迎短讯」里给出的规则地址</strong>（🔗 已存下，可点开）；
              页面里顺带抓到的 H&amp;R 不算数。默认时长给<strong>表里未收录</strong>的站点兜底；
              每站的时长直接改上表的「<strong>保种(h)</strong>」列（手填覆盖，优先级最高）。
            </p>
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.crossseed_seed_hours_default"
                type="number"
                min="0"
                max="720"
                step="1"
                label="默认最短保种时长（小时）"
                hint="未收录站点的 H&R 保种时长，默认 24h"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.hr_seed_margin_hours"
                type="number"
                step="0.5"
                min="0"
                label="H&amp;R 结清安全垫（小时）"
                hint="实际做种需 ≥ 站点要求 + 该值才判结清（默认 2，0 = 不留垫）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.hr_deadline_warn_hours"
                type="number"
                step="1"
                min="0"
                label="H&amp;R 临近到期预警（小时）"
                hint="距站点考核窗口到期低于该值且未达标 → 预警（默认 48）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.crossseed_guard_keep_seed" label="来源份 H&R 保护（保种期内任何任务不得删/改标签）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.crossseed_reclaim" label="H&R 期满后回收来源份（只删种子不删文件）" color="warning" hide-details inset />
            </div>
            <div class="magicflow-rules-actions">
              <VBtn size="small" color="primary" variant="tonal" :loading="rulesProbing" @click="probeRules()">
                <VIcon start size="small">mdi-download-network-outline</VIcon>逐站拉取（探测页面）
              </VBtn>
              <VBtn size="small" variant="text" :disabled="rulesLoading" @click="refreshRules">按 MP 配置补全</VBtn>
              <VSpacer />
              <span class="magicflow-settings-hint">共 {{ siteRules.length }} 条</span>
            </div>
            <p v-if="rulesProbing" class="magicflow-settings-hint">正在逐站抓取规则页（每站 1~2 个请求，站间随机歇 1.5~3.5 秒）…</p>
            <div class="magicflow-rules-table">
              <div class="magicflow-rules-row magicflow-rules-row--head">
                <span>站点</span><span>H&amp;R</span><span>保种(h)</span><span>做种上限</span><span>来源</span><span>操作</span>
              </div>
              <div v-for="row in siteRules" :key="row.domain" class="magicflow-rules-row">
                <span class="magicflow-rules-row__name" :title="row.domain">
                  {{ row.site_name || row.domain }}
                  <em v-if="!row.in_library">未入库</em>
                  <em v-if="row.exam_avg_hours" :title="row.exam_evidence || '站点考核的平均做种要求（不是 H&R）'">考核均值{{ row.exam_avg_hours }}h</em>
                  <em v-if="row.free_over_gb" title="站点促销规则：达到该体积自动免费（列表页可能不标促销，插件按规则补判）">&gt;{{ row.free_over_gb }}G免</em>
                  <em v-if="row.free_original" title="站点促销规则：原盘自动免费">原盘免</em>
                  <em v-if="row.free_ep1" title="站点促销规则：每季第一集自动免费">首集免</em>
                </span>
                <span class="magicflow-rules-row__hr">
                  <VChip v-if="row.hr === true" size="x-small" color="error" variant="tonal">有</VChip>
                  <VChip v-else-if="row.hr === false" size="x-small" color="success" variant="tonal">无</VChip>
                  <VChip v-else size="x-small" variant="tonal">未知</VChip>
                  <VBtn v-if="row.hr === false" size="x-small" variant="text" :disabled="rulesProbing" title="恢复为探测/内置判定" @click="setRuleHr(row, 'unknown')">恢复</VBtn>
                  <template v-else>
                    <VBtn size="x-small" variant="text" :disabled="rulesProbing" title="该站有 H&R：手动确认为「有」并按当前时长保护" @click="setRuleHr(row, '1')">标有</VBtn>
                    <VBtn size="x-small" variant="text" :disabled="rulesProbing" title="该站没有 H&R：直接标无，不做保种保护" @click="setRuleHr(row, '0')">标无</VBtn>
                  </template>
                </span>
                <span>
                  <VTextField
                    :model-value="row.effective_hours"
                    type="number"
                    min="0"
                    max="720"
                    step="1"
                    density="compact"
                    variant="outlined"
                    hide-details
                    style="max-width: 6.5rem"
                    @change="setRuleHours(row, $event.target.value)"
                  />
                </span>
                <span>{{ row.seed_cap || '-' }}</span>
                <span class="magicflow-rules-row__src" :title="row.evidence || ''">
                  {{ ruleSourceText(row) }}
                  <em v-if="row.seed_need_hours" :title="'规则窗口 ' + (row.seed_window_hours || row.seed_hours || 0) + 'h，达到线 ' + row.seed_need_hours + 'h；保护期取窗口(保守)'">需{{ row.seed_need_hours }}h</em>
                  <em v-if="row.seed_hours_seen != null">(看到{{ row.seed_hours_seen }}h)</em>
                </span>
                <span>
                  <VBtn
                    v-if="row.rule_url"
                    size="x-small"
                    variant="text"
                    icon
                    :href="String(row.rule_url).split(/\s+/)[0]"
                    target="_blank"
                    rel="noopener"
                    :title="'规则地址（来自收件箱欢迎短讯，已存下）：' + row.rule_url"
                  ><VIcon size="x-small">mdi-link-variant</VIcon></VBtn>
                  <VBtn size="x-small" variant="text" :disabled="rulesProbing" @click="probeRules(row.domain)">探测</VBtn>
                </span>
              </div>
            </div>
            <p class="magicflow-settings-hint">
              「保种(h)」直接改 = 写入手填覆盖（最高优先级：手填 &gt; 探测 &gt; 内置 &gt; 全局默认）。
            </p>
          </div>

          <div v-else-if="settingsTab === 'tags'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              标签模型：种子状态 = 标签 <code>魔流-&lt;站点&gt;-&lt;状态&gt;[-&lt;子类&gt;]</code>，
              状态有 <strong>刷流 / 魔力 / 静默(新·资源·普通) / 推荐</strong>；
              另有<strong>状态账本</strong>做真值源（标签被改坏也能自愈），以及
              <strong>文件组账本</strong>按多站引用计数——<em>摘成员只删种，最后一个成员才连文件清</em>。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.tag_model_enabled" label="启用标签模型（状态账本 + 魔流-站点-状态 标签）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.show_qb_tags" label="往 qB 写标签（关=纯账本模式）" color="primary" hide-details inset />
            </div>
            <div class="magicflow-settings-grid">
              <VTextField v-model.number="settingsDraft.tag_silent_new_timeout_hours" type="number" min="0" step="1"
                label="「静默-新」超时(小时)" hint="超过该时长未分拣自动归「静默-普通」，0 = 不超时"
                persistent-hint variant="outlined" density="comfortable" />
            </div>

            <VDivider class="my-3" />
            <p class="magicflow-settings-hint">
              <strong>静默分拣规则</strong>：<code>静默-新</code> 命中任一启用规则 → 进 <code>静默-资源</code>，
              否则进 <code>静默-普通</code>（受站点魔力产出考核）。
            </p>
            <div class="magicflow-sort-rules">
              <div class="magicflow-sort-rules__row magicflow-sort-rules__row--head">
                <span>规则</span><span>阈值</span><span>权重</span><span>启用</span><span></span>
              </div>
              <div v-for="(r, i) in settingsDraft.sort_rules" :key="i" class="magicflow-sort-rules__row">
                <span>{{ sortRuleText(r) }}</span>
                <span>
                  <VTextField v-if="sortRuleNeedsMin(r.type)" v-model.number="r.min" type="number" step="0.5" density="compact" variant="outlined" hide-details style="max-width: 110px" />
                  <em v-else>-</em>
                </span>
                <span>
                  <VTextField v-model.number="r.weight" type="number" step="5" density="compact" variant="outlined" hide-details style="max-width: 90px" />
                </span>
                <span>
                  <VSwitch v-model="r.enabled" color="primary" density="compact" hide-details inset />
                </span>
                <span>
                  <VBtn size="x-small" variant="text" color="error" @click="removeSortRule(i)">删除</VBtn>
                </span>
              </div>
            </div>
            <div class="magicflow-sort-rules__add">
              <VSelect v-model="newRuleType" :items="sortRuleTypeOptions" item-title="text" item-value="value"
                density="compact" variant="outlined" hide-details style="max-width: 200px" label="新增规则" />
              <VBtn size="small" variant="tonal" color="primary" @click="addSortRule">加上</VBtn>
            </div>

            <VDivider class="my-3" />
            <div class="magicflow-rules-actions">
              <VBtn size="small" variant="tonal" color="primary" :loading="tagMigrating" @click="previewTagMigrate">
                <VIcon start size="small">mdi-tag-multiple</VIcon>迁移预演（老标签 → 新命名）
              </VBtn>
              <VBtn v-if="tagMigratePlan" size="small" color="error" variant="tonal" :loading="tagMigrating" @click="applyTagMigrate">
                执行迁移（{{ tagMigratePlan.total }} 个）
              </VBtn>
              <VSpacer />
              <span class="magicflow-settings-hint">账本 {{ tagInfo?.ledger_count ?? 0 }} 条 · 文件组 {{ tagInfo?.groups?.groups ?? 0 }}（多站 {{ tagInfo?.groups?.multi_site_groups ?? 0 }}）</span>
            </div>
            <div v-if="tagMigratePlan" class="magicflow-tag-migrate">
              <p class="magicflow-settings-hint">
                待迁移 <strong>{{ tagMigratePlan.total }}</strong> 个：
                <em v-for="(n, k) in tagMigratePlan.by_state" :key="k">{{ k }} {{ n }} </em>
              </p>
              <div class="magicflow-tag-migrate__samples">
                <div v-for="(row, i) in (tagMigratePlan.samples || [])" :key="i" class="magicflow-tag-migrate__row">
                  <span class="magicflow-tag-migrate__title" :title="row.title">{{ row.title }}</span>
                  <span class="magicflow-tag-migrate__tags">
                    <em>{{ (row.remove || []).join(' ') }}</em> → <strong>{{ row.add }}</strong>
                  </span>
                </div>
              </div>
            </div>
            <p class="magicflow-settings-hint">
              迁移会把任务里手填的 <code>brush_tag</code>（如 <code>魔流-财神</code>）换成状态标签，
              保留 <code>已整理 / 辅种</code> 等外来标签；预演不变更任何东西。
            </p>
          </div>

          <div v-else-if="settingsTab === 'crossseed'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              跨站免费取种：本站<strong>非免费</strong>的候选（或本地没有的免费种）→ 去<strong>兄弟站免费下</strong>，
              下完再把目标站的种子指向同一批文件回辅（校验通过才保留）。
              <br />
              本页只管「<strong>怎么取种</strong>」：
              <strong>流量兜底</strong>（含取种期间核对来源站）已在「<strong>站点监控 → 流量兜底</strong>」统一配置；
              <strong>下完的来源份</strong>会移交「<strong>静默池</strong>」挂 H&amp;R（保种 / 分拣 / 回收由静默池负责）。
            </p>
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

    <VDialog v-model="torrentDialog" max-width="34rem" :fullscreen="isNarrow">
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

    <VDialog v-model="transferDialog" max-width="34rem">
      <VCard title="批量转移种子" class="magicflow-dialog">
        <VCardText class="magicflow-settings-hint">
          把选中的 <strong>{{ selectedHashes.length }}</strong> 个种子交给别的任务，或退回静默池（保文件）。
          跨站转移会改掉站点标签 —— 一般只转给<strong>同站</strong>任务。
        </VCardText>
        <VCardText>
          <VSelect v-model="transferTarget" :items="transferChoices" item-title="text" item-value="value"
            density="compact" variant="outlined" hide-details label="转移到" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="batchBusy" @click="transferDialog = false">取消</VBtn>
          <VBtn color="primary" variant="flat" :loading="batchBusy" @click="confirmTransfer">转移</VBtn>
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

    <VDialog v-model="deleteDialog" max-width="34rem" @update:model-value="onDeleteDialog">
      <VCard title="删除魔力任务" class="magicflow-dialog">
        <VCardText>
          确认删除「{{ selectedTask?.name }}」？
        </VCardText>
        <VCardText v-if="handoverLoading" class="magicflow-settings-hint">正在统计名下种子…</VCardText>
        <VCardText v-else-if="handover" class="magicflow-settings-hint">
          名下 <strong>{{ handover.managed }}</strong> 个种子 · {{ handover.size_gb }} GB
          <template v-if="handover.auto_handover?.length">
            <br />
            <VAlert density="compact" variant="tonal" color="info" class="mt-2">
              另有同站同状态任务「<strong>{{ handover.auto_handover[0].name }}</strong>」用同一批标签
              （{{ handover.tag }}），<strong>不交棒它也会接着管</strong>。<br />
              <strong>默认退回静默池</strong>（保文件）—— 想指定交给谁再在下面选。
            </VAlert>
          </template>
          <template v-else>
            <br />
            <VAlert density="compact" variant="tonal" color="info" class="mt-2">
              <strong>默认退回静默池</strong>（保文件）—— 想指定交给谁再在下面选。
            </VAlert>
          </template>
        </VCardText>
        <VCardText v-if="handover">
          <VSelect v-model="handoverTarget" :items="handoverChoices" item-title="text" item-value="value"
            density="compact" variant="outlined" hide-details label="名下种子怎么处理" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="deleteDialog = false">取消</VBtn>
          <VBtn color="error" variant="flat" :loading="saving" @click="confirmDeleteTask">确认删除</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="cloudOpen" max-width="52rem" scrollable :fullscreen="isNarrow">
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

    <!-- 跨站辅种：队列 + 流量兜底（3.11.0） -->
    <VDialog v-model="ondemandOpen" max-width="46rem" scrollable>
      <VCard class="magicflow-dialog magicflow-ondemand-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">点播</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="ondemandOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-ondemand-dialog__body">
          <div class="magicflow-ondemand-hint">
            <div>输入片名或链接 → <strong>搜候选</strong> → 点<strong>「下这条」</strong>；不选就点<strong>「选源并下载」</strong>（自动挑推荐源）。下完<strong>自动整理进影视库</strong>。</div>
            <div class="magicflow-ondemand-hint__legend">
              站点可多选，<strong>不勾＝全部</strong>；默认优先选<strong>免费</strong>的源。
            </div>
          </div>
          <div class="magicflow-ondemand-form">
            <VTextField
              v-model="ondemandQuery"
              density="comfortable"
              hide-details="auto"
              label="片名 / 链接"
              placeholder="如 流浪地球 或 https://movie.douban.com/subject/35267208/"
              @keyup.enter="runOndemand(false)"
            />
            <VSelect
              v-model="ondemandSiteIds"
              density="comfortable"
              hide-details="auto"
              :items="siteSelectItems"
              label="站点（可多选 · 不勾 = 全部站点）"
              multiple
              chips
              closable-chips
            />
            <VSelect
              v-model="ondemandTaskId"
              density="comfortable"
              hide-details="auto"
              :items="[{ title: '（默认目录）', value: '' }, ...tasks.map((t) => ({ title: `${t.name}·${t.site_name || t.site_id}`, value: t.id }))]"
              label="保存目录"
            />
          </div>
          <div class="magicflow-ondemand-actions">
            <VBtn
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-magnify"
              :loading="ondemandBusy === 'preview'"
              @click="runOndemand(false)"
            >搜候选</VBtn>
            <VBtn
              size="small"
              color="primary"
              prepend-icon="mdi-cloud-download-outline"
              :loading="ondemandBusy === 'apply'"
              @click="runOndemand(true)"
            >选源并下载</VBtn>
          </div>
          <VAlert v-if="ondemandError" type="error" variant="tonal" density="compact" class="mt-2">
            {{ ondemandError }}
          </VAlert>
          <template v-if="ondemandResult">
            <div class="magicflow-recommend-dialog__summary mt-2">
              <VChip size="small" :color="ondemandResult.resource?.recognized ? 'success' : 'warning'" variant="tonal">
                {{ ondemandResult.resource?.recognized ? '已识别' : '未识别（按原串搜）' }}
              </VChip>
              <i>·</i>
              <span>{{ ondemandResult.resource?.title }} {{ ondemandResult.resource?.year }}</span>
              <i>·</i>
              <span>候选 {{ ondemandCandidates.length }}</span>
              <i>·</i>
              <span>站点 {{ (ondemandResult.sites || []).join(', ') || '—' }}</span>
              <i>·</i>
              <span>存到 <code>{{ ondemandResult.save_path || '（未配置）' }}</code></span>
            </div>
            <div v-if="ondemandResult.added" class="magicflow-recommend-dialog__note">
              已下载：<code>{{ ondemandResult.added }}</code>（完成后直接转「资源」）
            </div>
            <div v-if="ondemandCandidates.length" class="magicflow-ondemand-list mt-2">
              <article
                v-for="(row, idx) in ondemandCandidates"
                :key="idx"
                class="magicflow-ondemand-item"
                :class="{ 'magicflow-ondemand-item--auto': isOndemandAuto(row) }"
              >
                <div class="magicflow-ondemand-item__title" :title="row.title">{{ row.title }}</div>
                <div class="magicflow-ondemand-item__meta">
                  <VChip size="x-small" variant="tonal">{{ row.site_name || row.site }}</VChip>
                  <span>{{ fmtSizeGb(row.size) }}</span>
                  <span>做种 {{ row.seeders }}</span>
                  <VChip
                    size="x-small"
                    variant="tonal"
                    :color="odTraffic(row.downloadvolumefactor).color || undefined"
                  >{{ odTraffic(row.downloadvolumefactor).text }}</VChip>
                  <VChip v-if="isOndemandAuto(row)" size="x-small" variant="flat" color="primary">推荐</VChip>
                  <VChip
                    v-if="ondemandResult?.added && ondemandResult?.picked?.enclosure === row.enclosure"
                    size="x-small"
                    variant="flat"
                    color="success"
                  >已下</VChip>
                </div>
                <div class="magicflow-ondemand-item__act">
                  <VBtn
                    size="x-small"
                    variant="tonal"
                    color="primary"
                    prepend-icon="mdi-download"
                    :loading="ondemandBusy === 'apply'"
                    :disabled="!!ondemandBusy"
                    @click="runOndemand(true, row.enclosure)"
                  >下这条</VBtn>
                </div>
              </article>
            </div>
          </template>
        </VCardText>
      </VCard>
    </VDialog>

    <!-- ★ 可观测③：健康自检 -->
    <VDialog v-model="healthOpen" max-width="40rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-settings-dialog">
        <VToolbar color="transparent" density="comfortable">
          <VToolbarTitle class="text-subtitle-1">健康自检</VToolbarTitle>
          <VChip
            :color="healthColor || 'success'"
            size="small"
            variant="tonal"
            class="me-2"
          >{{ healthLabel }}</VChip>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="healthOpen = false" />
        </VToolbar>
        <VDivider />
        <VCardText class="magicflow-settings-body">
          <div v-if="!healthData.issues || !healthData.issues.length" class="magicflow-empty">
            <VIcon icon="mdi-check-circle-outline" size="20" class="me-2" />
            全部正常：任务运行正常、魔力无异常下滑、体积未贴上限。
          </div>
          <template v-else>
            <div class="mf-health__hint">
              按严重度排序 · 自检只看本地状态（零外部请求），共 {{ healthData.issues.length }} 项
            </div>
            <article
              v-for="issue in healthData.issues"
              :key="issue.key"
              class="mf-health__item"
              :class="`is-${issue.level}`"
            >
              <VIcon
                :icon="issue.level === 'error' ? 'mdi-alert-octagon-outline' : issue.level === 'warning' ? 'mdi-alert-outline' : 'mdi-information-outline'"
                size="18"
                class="mf-health__icon"
              />
              <div class="mf-health__body">
                <div class="mf-health__title">{{ issue.title }}</div>
                <div class="mf-health__detail">{{ issue.detail }}</div>
              </div>
              <VBtn
                v-if="issue.task_id"
                size="small"
                variant="text"
                @click="healthGoto(issue)"
              >诊断</VBtn>
            </article>
          </template>
        </VCardText>
      </VCard>
    </VDialog>

    <VDialog v-model="doubanServiceOpen" max-width="46rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-douban-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">豆瓣评分服务</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" @click="loadDoubanService">刷新</VBtn>
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="doubanServiceOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-douban-dialog__body">
          <div class="magicflow-recommend-dialog__summary">
            <VChip size="small" :color="doubanServiceData.ok ? 'success' : 'error'" variant="tonal">
              {{ doubanServiceData.ok ? '服务正常' : '服务不可用（回退 TMDB）' }}
            </VChip>
            <i>·</i>
            <span>库 <strong>{{ fmtCount(doubanServiceData.records) }}</strong> 条</span>
            <i>·</i>
            <span>缓存 {{ fmtCount(doubanServiceData.cache?.total) }} 条 · 负缓存 {{ doubanServiceData.cache?.negative || 0 }}</span>
          </div>
          <div class="magicflow-recommend-dialog__note">
            地址：{{ doubanServiceData.service || '（未配置）' }}。独立服务 magicflow-douban，本地查询 &lt;1ms，不受豆瓣限流影响。
          </div>

          <VSheet tag="section" class="magicflow-panel app-surface-static mt-2">
            <header class="magicflow-panel__head">
              <div>
                <div class="text-subtitle-2 font-weight-medium">后台数据采集（慢爬）</div>
                <div class="text-body-2 text-medium-emphasis">
                  从豆瓣「选电影」接口（一次 20 条带评分）按类型×题材×排序逐步枚举，限速 + 每日上限，进度落库可续跑
                </div>
              </div>
              <VChip
                size="small"
                variant="tonal"
                :color="doubanCrawl.running ? 'success' : (doubanCrawl.finished ? 'info' : 'warning')"
              >{{ doubanCrawl.running ? '采集中' : (doubanCrawl.finished ? '已完成' : '已暂停') }}</VChip>
            </header>
            <div class="magicflow-douban-crawl">
              <div class="magicflow-douban-crawl__row">
                <span>进度</span>
                <span class="text-medium-emphasis">
                  组合 {{ doubanCrawl.spec_index || 0 }} / {{ doubanCrawl.spec_total || 0 }}
                  <template v-if="doubanCrawl.finished">· 全部跑完</template>
                  <template v-else-if="doubanCrawl.current">· 当前 {{ doubanCrawl.current.tags || '（全部）' }} / {{ doubanCrawl.current.sort }}</template>
                </span>
              </div>
              <VProgressLinear :model-value="doubanCrawlProgress" height="6" rounded color="primary" class="my-2" />
              <div class="magicflow-douban-crawl__grid">
                <span>累计请求 <strong>{{ doubanCrawl.requests || 0 }}</strong></span>
                <span>今日 <strong>{{ doubanCrawl.day_requests || 0 }}</strong> / {{ doubanCrawl.daily_max || '—' }}</span>
                <span>已抓 <strong>{{ fmtCount(doubanCrawl.items) }}</strong> 条</span>
                <span>新增 <strong>{{ fmtCount(doubanCrawl.new) }}</strong> 条</span>
                <span>错误 <strong>{{ doubanCrawl.errors || 0 }}</strong></span>
              </div>
              <div v-if="doubanCrawl.finished" class="magicflow-douban-crawl__warn magicflow-douban-crawl__warn--ok">
                ✓ 全部 {{ doubanCrawl.spec_total || 0 }} 个组合已抓完（累计 {{ fmtCount(doubanCrawl.items) }} 条 / 新增 {{ fmtCount(doubanCrawl.new) }} 条）。
                豆瓣榜单有变动时，可点「从头重跑」再补一轮。
              </div>
              <div v-if="doubanCrawl.blocked_for > 0" class="magicflow-douban-crawl__warn">
                ⚠ 触发限流/退避，暂停 {{ doubanCrawl.blocked_for }} 秒后继续
              </div>
              <div v-else-if="doubanCrawl.last_error" class="magicflow-douban-crawl__warn">
                最近异常：{{ doubanCrawl.last_error }}<template v-if="doubanCrawl.last_error_at"> · {{ fmtTs(doubanCrawl.last_error_at) }}</template>
              </div>
              <div class="magicflow-douban-crawl__actions">
                <VBtn
                  v-if="doubanCrawl.running"
                  size="small" variant="tonal" color="warning" prepend-icon="mdi-pause"
                  :loading="doubanServiceActing === 'stop'"
                  @click="doubanCrawlAction('stop')"
                >暂停采集</VBtn>
                <VBtn
                  v-else-if="!doubanCrawl.finished"
                  size="small" variant="tonal" color="success" prepend-icon="mdi-play"
                  :loading="doubanServiceActing === 'start'"
                  @click="doubanCrawlAction('start')"
                >继续采集</VBtn>
                <VBtn
                  size="small" :variant="doubanCrawl.finished ? 'tonal' : 'text'" color="primary" prepend-icon="mdi-restart"
                  :loading="doubanServiceActing === 'reset'"
                  @click="doubanCrawlAction('reset')"
                >从头重跑</VBtn>
              </div>
            </div>
          </VSheet>
        </VCardText>
      </VCard>
    </VDialog>

    <VDialog v-model="crossseedOpen" max-width="46rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-crossseed-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">跨站取种</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VChip size="small" variant="tonal" color="primary">{{ crossseedData.tag || '魔流-跨站' }}</VChip>
            <VBtn
              variant="text"
              color="primary"
              size="small"
              prepend-icon="mdi-history"
              @click="openOperations('all')"
            >操作记录</VBtn>
            <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" @click="loadCrossseed" />
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="crossseedOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-crossseed-dialog__body">
          <!-- 核心统计：待回辅 / 运行任务 / 保种来源份 -->
          <div class="magicflow-cs-stats">
            <div class="magicflow-cs-stat">
              <b>{{ crossseedStats.pending }}</b>
              <span>待回辅</span>
            </div>
            <div class="magicflow-cs-stat">
              <b>{{ crossseedStats.tasks }}</b>
              <span>运行任务</span>
            </div>
            <div class="magicflow-cs-stat">
              <b>{{ crossseedSilentCount }}</b>
              <span>已转静默</span>
            </div>
          </div>

          <!-- 一行状态：流量兜底 -->
          <div class="magicflow-cs-status">
            <VChip
              size="small"
              variant="tonal"
              :color="crossseedGuard.enabled === false ? 'error' : 'success'"
              prepend-icon="mdi-shield-check-outline"
            >流量兜底 · {{ crossseedGuard.enabled === false ? '已关闭' : '已启用' }}</VChip>
            <span class="magicflow-cs-status__dim">
              阈值 下载增量 &gt; 体积×{{ crossseedGuard.pct ?? 5 }}%（≥{{ crossseedGuard.min_mb ?? 50 }}MB）· 每 {{ crossseedGuard.interval_min ?? 15 }} 分钟核对
            </span>
            <span class="magicflow-cs-status__dim">{{ crossseedBanned.length ? `· 已拉黑 ${crossseedBanned.length} 站` : '· 无拉黑站点' }}</span>
            <VSpacer />
            <VBtn
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-shield-search"
              :loading="crossseedActing === 'guard'"
              @click="runCrossseedGuard"
            >立即核对</VBtn>
          </div>

          <!-- 拉黑站点（有才出现） -->
          <div v-if="crossseedBanned.length" class="magicflow-cs-bans">
            <VChip
              v-for="b in crossseedBanned"
              :key="b.domain"
              size="small"
              variant="tonal"
              color="error"
              closable
              @click:close="unbanCrossseed(b.domain)"
            >{{ b.domain }} · {{ b.age_min }} 分钟前</VChip>
            <VBtn
              size="x-small"
              variant="text"
              color="warning"
              :loading="crossseedActing === 'unban:'"
              @click="unbanCrossseed('')"
            >全部解除</VBtn>
          </div>

          <!-- ★ 来源份 → 静默池（7.16.0）：H&R 保挂/回收不归本页，统一由静默池负责 -->
          <div class="magicflow-cs-handoff">
            <VIcon icon="mdi-pool" size="small" class="magicflow-cs-handoff__icon" />
            <div class="magicflow-cs-handoff__text">
              <b>{{ crossseedSilentCount }}</b> 份来源份已在<b>静默池</b>挂 H&R（下完即移交，保种/分拣/回收归静默池）
              <template v-if="crossseedPendingHandoff">
                <br /><span class="magicflow-cs-status__dim">另有 {{ crossseedPendingHandoff }} 份待移交（下一轮静默托管自动处理）</span>
              </template>
            </div>
            <VSpacer />
            <VBtn
              size="x-small"
              variant="text"
              color="primary"
              prepend-icon="mdi-open-in-new"
              @click="openSilent()"
            >静默池</VBtn>
          </div>

          <!-- 待回辅队列（有才出现） -->
          <section v-if="crossseedPending.length" class="magicflow-cs-pending">
            <header class="magicflow-cs-pending__head">
              <span>待回辅队列</span>
              <VBtn
                size="x-small"
                variant="text"
                color="error"
                :loading="crossseedActing === 'clear'"
                @click="clearCrossseed"
              >清空</VBtn>
            </header>
            <article v-for="it in crossseedPending" :key="it.sib_hash" class="magicflow-cs-card">
              <div class="magicflow-cs-card__name" :title="it.title || it.sib_hash">{{ it.title || it.sib_hash }}</div>
              <div class="magicflow-cs-card__meta">
                <span class="magicflow-cs-card__site">从 {{ it.site_b || '?' }} 取 → 辅回 {{ it.site_a || '?' }}</span>
                <span class="magicflow-cs-card__size">{{ gbText(it.size_gb) }}</span>
                <VChip size="x-small" variant="flat" color="info">{{ crossseedStateText(it) }}</VChip>
                <VSpacer />
                <VBtn
                  size="x-small"
                  variant="text"
                  color="error"
                  icon="mdi-delete-outline"
                  :loading="crossseedActing === 'drop:' + it.sib_hash"
                  @click="dropCrossseed(it.sib_hash)"
                />
              </div>
            </article>
          </section>

          <!-- ★ 来源份（他站那份 · 保种中）：来源站 → 目标站 明示（7.19.3） -->
          <section v-if="crossseedSources.length" class="magicflow-cs-pending">
            <header class="magicflow-cs-pending__head">
              <span>来源份（他站那份 · 保种中）</span>
            </header>
            <article v-for="s in crossseedSources" :key="s.sib_hash" class="magicflow-cs-card">
              <div class="magicflow-cs-card__name" :title="s.title || s.sib_hash">{{ s.title || s.sib_hash }}</div>
              <div class="magicflow-cs-card__meta">
                <span class="magicflow-cs-card__site">来自 {{ s.site_b || '?' }} → 辅回 {{ s.site_a || '?' }}</span>
                <span class="magicflow-cs-card__size">{{ gbText(s.size_gb) }}</span>
                <VChip
                  v-if="Number(s.progress ?? 1) < 0.999"
                  size="x-small" variant="flat" color="info"
                >{{ crossseedStateText(s) }}</VChip>
                <VChip size="x-small" variant="tonal">已挂 {{ s.seeded_h || 0 }}h</VChip>
                <VChip size="x-small" variant="tonal" :color="crossseedCardState(s).color">{{ crossseedCardState(s).text }}</VChip>
                <VChip v-if="String(s.pool || '') === 'silent'" size="x-small" variant="tonal" color="primary">静默池</VChip>
              </div>
            </article>
          </section>
          <div v-if="crossseedLegacyCount" class="magicflow-cs-status__dim">
            另有 {{ crossseedLegacyCount }} 条旧回填来源份（无来源/目标站信息）未在此列出 ——
            <a class="magicflow-cs-link" @click.prevent="openOperations('all')">见操作记录</a>
          </div>

          <!-- 完整规则：默认收起 -->
          <details class="magicflow-cs-rules">
            <summary>查看完整规则</summary>
            <div class="magicflow-cs-rules__body">
              <p><strong>取种原理</strong>：在他站<strong>免费</strong>下载 → 下完把目标站的种子指向同一批文件回辅（校验通过才保留）。本站判为「非免费」的候选只走跨站，<strong>绝不在本站下载</strong>。</p>
              <p><strong>流量兜底</strong>：判「免费」可能出错 → 取种期间核对来源站的免费状态与下载量增量；发现其实不免费，立即<strong>删种 + 拉黑该站</strong>（需人工确认后解除）。</p>
              <p><strong>来源份 H&amp;R 保种</strong>：他站那份下完（无论回辅成功或失败）都要留在来源站挂种，否则算 H&amp;R —— 保种期内任何任务都不会删它、也不会改它的标签。</p>
              <p><strong>待回辅队列</strong>：他站下完 → 自动回辅目标站；超过 6 小时未完成会放弃。未下载完不会转资源、不会整理入库。</p>
              <p><strong>保种时长</strong>：默认 {{ crossseedGuard.seed_hours_default ?? 24 }} 小时；优先级 种子自带 H&amp;R 标记 &gt; 站点规则库 &gt; 默认值。站点自定义：{{ (crossseedGuard.site_hours || []).join('、') || '无' }}。</p>
              <p><strong>期满回收</strong>：{{ crossseedGuard.reclaim ? '已开启——保种期满后允许被任务删种回收空间。' : '未开启——保种期满的种也不会被自动删除。' }}</p>
            </div>
          </details>
        </VCardText>
      </VCard>
    </VDialog>

    <VDialog v-model="rescueOpen" max-width="50rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-rescue-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">死种补源</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="rescueScanning" @click="runRescueScan" />
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="rescueOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-rescue-dialog__body">
          <VAlert density="compact" type="info" variant="tonal">
            停滞欠 H&R 的种 → 从他站「无 H&R」站补下同 Release；<b>未下完的种不辅种，只能补源</b>。
          </VAlert>

          <div class="magicflow-cs-status">
            <VChip size="small" variant="tonal" color="primary" prepend-icon="mdi-seed-outline">
              待补源 {{ rescueTargets.length }}
            </VChip>
            <span v-if="rescueSkippedSites.length" class="magicflow-cs-status__dim">
              排除站点（有 H&R）{{ rescueSkippedSites.length }} 个
            </span>
            <VSpacer />
            <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-eye-outline"
                   :loading="rescueBusy && rescueBusyType === 'preview'" @click="runRescueApply(false)">预览（干跑）</VBtn>
            <VBtn size="small" variant="flat" color="primary" prepend-icon="mdi-lifebuoy" class="ml-2"
                   :disabled="!rescueTargets.length"
                   :loading="rescueBusy && rescueBusyType === 'apply'" @click="runRescueApply(true)">执行补源</VBtn>
          </div>

          <div v-if="!rescueTargets.length" class="magicflow-cs-status__dim" style="padding:1rem 0">
            当前没有「停滞欠 H&R / 手动保留」的未下完种。
          </div>

          <section v-for="t in rescueTargets" :key="t.hash" class="magicflow-cs-pending">
            <article class="magicflow-cs-card">
              <div class="magicflow-cs-card__name" :title="t.title || t.hash">{{ t.title || t.hash }}</div>
              <div class="magicflow-cs-card__meta">
                <span class="magicflow-cs-card__site">{{ t.site || '?' }}</span>
                <span class="magicflow-cs-card__size">进度 {{ Math.round((t.progress ?? 0) * 100) }}% · 停滞 {{ t.stalled_hours ?? 0 }}h</span>
                <VChip v-if="t.hr_owed" size="x-small" variant="tonal" color="error">欠 H&R {{ t.hr_need_h }}h</VChip>
                <VChip v-else-if="t.manual" size="x-small" variant="tonal" color="primary">手动保留</VChip>
              </div>
              <div class="magicflow-cs-card__meta">
                <span class="magicflow-cs-status__dim">{{ t.reason_not_reuse }}</span>
              </div>
              <div v-if="t.candidates && t.candidates.length" class="magicflow-cs-card__meta">
                <span class="magicflow-cs-card__site">最佳候选：{{ t.best?.site_name || '?' }} · {{ t.best?.seeders ?? 0 }} 源</span>
              </div>
              <div v-else class="magicflow-cs-card__meta">
                <span class="magicflow-cs-status__dim" style="color:var(--v-error-base)">
                  无可用候选<template v-if="t.skipped && t.skipped.length">（{{ t.skipped.map(s => s.site).join('、') }}）</template>
                </span>
              </div>
            </article>
          </section>

          <details class="magicflow-cs-rules">
            <summary>查看补源规则</summary>
            <div class="magicflow-cs-rules__body">
              <p><strong>目标</strong>：进度 &lt; 100% 且 0 速停滞 ≥ {{ rescueData?.settings?.stall_hours ?? 6 }} 小时，且欠 H&amp;R 或手动保留。</p>
              <p><strong>候选</strong>：标题规范化后完全一致（不把 10bit 当非 10bit）+ 来源站无 H&amp;R + 有源。</p>
              <p><strong>未下完不辅种</strong>：progress&lt;1 的种不进全站辅种，只能走补源（避免 ADD-REUSE 空转）。</p>
            </div>
          </details>
        </VCardText>
      </VCard>
    </VDialog>

    <VDialog v-model="recommendOpen" max-width="46rem" scrollable :fullscreen="isNarrow">
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
              <div class="d-flex align-center flex-wrap ga-2 justify-end">
                <VBtn
                  v-if="recSelectable.length"
                  size="small"
                  variant="text"
                  :prepend-icon="recAllChecked ? 'mdi-checkbox-multiple-marked-outline' : 'mdi-checkbox-multiple-blank-outline'"
                  @click="toggleAllRecs"
                >{{ recAllChecked ? '取消全选' : `全选 (${recSelectable.length})` }}</VBtn>
                <VBtn
                  size="small"
                  color="primary"
                  variant="tonal"
                  prepend-icon="mdi-tray-arrow-down"
                  :disabled="!recSelectedList.length"
                  :loading="recBatchActing"
                  @click="batchImportRecommend(false)"
                >批量入库 ({{ recSelectedList.length }})</VBtn>
                <VBtn
                  v-if="recSelectable.length"
                  size="small"
                  variant="text"
                  :loading="recBatchActing"
                  @click="batchImportRecommend(true)"
                >全部入库</VBtn>
                <VBtn
                  size="small"
                  variant="text"
                  color="primary"
                  :prepend-icon="showAllRecs ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
                  @click="showAllRecs = !showAllRecs"
                >{{ showAllRecs ? '仅看推荐' : (hiddenRecCount ? `显示全部候选 (+${hiddenRecCount})` : '显示全部候选') }}</VBtn>
              </div>
            </header>
            <div class="magicflow-recs">
              <article v-for="rec in recommendItems" :key="rec.hash" class="magicflow-rec" :class="{ 'magicflow-rec--sel': recommendActionable(rec) }">
                <VCheckbox
                  v-if="recommendActionable(rec)"
                  :model-value="!!recSelected[rec.hash]"
                  density="compact"
                  hide-details
                  class="magicflow-rec__check"
                  :aria-label="`选择 ${recName(rec)}`"
                  @update:model-value="toggleRec(rec.hash)"
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

    <!-- 新手考核：汇总弹窗（Layout A，同「推荐」范式） -->
    <VDialog v-model="examOpen" max-width="46rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-exam-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">新手考核</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" @click="loadExam">刷新</VBtn>
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="examOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-exam-body">
          <!-- ① 概览：未过站数 + 最近截止 + 待过项 -->
          <div class="magicflow-exam-hero" :class="examUrgent ? 'is-urgent' : ''">
            <div class="magicflow-exam-hero__left">
              <span class="magicflow-exam-hero__num">{{ examPendingSites }}</span>
              <span class="magicflow-exam-hero__cap">站考核未过</span>
            </div>
            <div class="magicflow-exam-hero__right">
              <div v-if="examNext" class="magicflow-exam-hero__line">
                <VIcon icon="mdi-alarm" size="14" />
                最近截止：{{ examNext.site_name || ('站点 ' + examNext.site_id) }}
                <VChip size="x-small" variant="tonal" :color="examUrgencyColor(examNext)">剩 {{ examDaysShort(examNext) }}</VChip>
              </div>
              <div class="magicflow-exam-hero__line is-dim">待过 {{ examPendingItems }} 项 · {{ examUrgentWeek }} 站 7 天内截止</div>
            </div>
          </div>
          <VAlert v-if="examData.enabled === false" type="info" variant="tonal" density="compact" class="my-2">
            新手考核模块已关闭（可在「插件设置 → 考核」开启；开启后零额外 PV）
          </VAlert>
          <div v-else-if="!examRows.length" class="magicflow-table-empty">
            没有未通过的考核（或站点数据暂时取不到）。
          </div>
          <!-- ② 按「剩余天数」升序：最紧急的排在最上面 -->
          <VSheet v-for="row in examRows" :key="row.site_id" tag="section" class="magicflow-exam-card">
            <header class="magicflow-exam-card__head">
              <div class="magicflow-exam-card__title">
                <span class="magicflow-exam-card__name">{{ row.site_name || ('站点 ' + row.site_id) }}</span>
                <VChip v-if="!(row.exam || {}).all_pass" size="x-small" variant="tonal" :color="examUrgencyColor(row)">剩 {{ examDaysShort(row) }}</VChip>
                <VChip v-else size="x-small" variant="tonal" color="success">已完成</VChip>
                <span class="magicflow-exam-card__passed">{{ examPassedCount(row) }}/{{ (row.exam.items || []).length }} 已过</span>
              </div>
              <VProgressLinear
                :model-value="examSitePct(row)"
                height="4"
                rounded
                :color="examUrgencyColor(row)"
                bg-color="rgba(var(--v-theme-on-surface), 0.12)"
              />
            </header>
            <!-- 考核项：未过的在前，带进度条一眼看出还差多少 -->
            <ul class="magicflow-exam-items">
              <li
                v-for="it in examVisibleItems(row)"
                :key="it.idx"
                class="magicflow-exam-item"
                :class="it.pass ? 'is-pass' : 'is-fail'"
              >
                <span class="magicflow-exam-item__label">{{ it.label }}</span>
                <span v-if="examItemGap(it)" class="magicflow-exam-item__gap">还差 {{ examItemGap(it) }}</span>
                <span v-if="it.cur || it.req" class="magicflow-exam-item__val"><strong>{{ it.cur }}</strong><i> / {{ it.req }}</i></span>
                <VIcon :icon="it.pass ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'" size="14" :color="it.pass ? 'success' : 'error'" />
                <VProgressLinear
                  v-if="Number(it.req_num) > 0"
                  class="magicflow-exam-item__bar"
                  :model-value="examItemPct(it)"
                  height="4"
                  rounded
                  :color="it.pass ? 'success' : 'error'"
                  bg-color="rgba(var(--v-theme-on-surface), 0.12)"
                />
              </li>
            </ul>
            <button
              v-if="examHiddenPassed(row) > 0"
              type="button"
              class="magicflow-exam-more"
              @click="examTogglePassed(row.site_id)"
            >显示已通过 {{ examHiddenPassed(row) }} 项</button>
            <button
              v-else-if="examShowPassed[row.site_id] && (row.exam.items || []).length > 1"
              type="button"
              class="magicflow-exam-more"
              @click="examTogglePassed(row.site_id)"
            >只看未通过</button>
            <!-- 可执行动作：同任务合并（魔力/做种积分都指向同一个任务只出一个） -->
            <div class="magicflow-exam-acts">
              <article v-for="a in examActions(row)" :key="a.key" class="magicflow-exam-act">
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
                  :loading="examActing === `${a.kind}:${row.site_id}`"
                  @click="examAct(row, a.kind)"
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

    <!-- 一键起任务确认（先展示要干什么，再动手） -->
    <VDialog :model-value="!!examConfirm" max-width="32rem" @update:model-value="v => { if (!v) examConfirm = null }">
      <VCard v-if="examConfirm" class="magicflow-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">确认执行</span>
        </header>
        <VDivider />
        <VCardText class="d-flex flex-column ga-2">
          <div>
            将在 <strong>{{ examConfirm.row.site_name }}</strong> 上
            <strong>{{ examConfirm.item.kind === 'upload' ? '创建 / 启用「考核刷流」任务' : '创建 / 启用「考核魔力」任务' }}</strong>：
          </div>
          <div class="text-body-2">任务名：<code>{{ examConfirm.item.task_name }}</code></div>
          <ul v-if="(examConfirm.item.notes || []).length" class="magicflow-exam-plan__notes">
            <li v-for="(n, ni) in examConfirm.item.notes" :key="ni">{{ n }}</li>
          </ul>
          <VAlert type="info" variant="tonal" density="compact">
            任务达标后自动停；全程只做种、不删种（魔流不做下载任务）。
          </VAlert>
        </VCardText>
        <VDivider />
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="!!examActing" @click="examConfirm = null">取消</VBtn>
          <VBtn color="primary" variant="flat" :loading="!!examActing" @click="examConfirmRun">确认创建 / 启用</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
    <VDialog v-model="claimOpen" max-width="52rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-claim-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">认领</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" :loading="claimLoading" @click="loadClaim">刷新</VBtn>
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="claimOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-claim-body">
          <div class="magicflow-claim-hero">
            <div class="magicflow-claim-hero__item"><span class="num">{{ claimTotal() }}</span><span class="cap">已认领</span></div>
            <div class="magicflow-claim-hero__item"><span class="num">{{ claimRequestable() }}</span><span class="cap">当前可认领</span></div>
            <div class="magicflow-claim-hero__item"><span class="num">{{ claimSupportedSites.length }}</span><span class="cap">支持站点</span></div>
            <VSpacer />
            <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-radar" :loading="claimActing === 'run'" @click="claimScanRun">扫描（干跑）</VBtn>
            <VBtn
              v-if="claimCfg.enabled && !claimCfg.dry && claimRequestable()"
              size="small"
              variant="flat"
              color="primary"
              prepend-icon="mdi-seal"
              @click="claimAsk('batch', null)"
            >认领本轮 {{ claimRequestable() }} 个</VBtn>
          </div>
          <VAlert v-if="!claimCfg.enabled" type="info" variant="tonal" density="compact" class="mb-2">
            认领默认关闭。开启路径：插件设置 → 认领（开启后仍是干跑，确认链路后再关干跑）。
          </VAlert>
          <VAlert v-else-if="claimCfg.dry" type="warning" variant="tonal" density="compact" class="mb-2">
            当前为「干跑」：只列出可认领的种，**不发任何写请求**（含手动单条）。要实写请到「插件设置 → 认领」关闭「干跑」。
          </VAlert>
          <VAlert type="info" variant="tonal" density="compact" class="mb-2">
            认领 = 保种承诺：认领后的种进硬保护、永不自动删除；站点侧不达标可能扣魔力，主动放弃更亏。
            <template v-if="claimData.benefit_desc">权益：{{ claimData.benefit_desc }}。</template>
          </VAlert>

          <VTabs v-model="claimTab" density="compact" class="mb-1">
            <VTab value="claimable">可认领（{{ claimRequestable() }}）</VTab>
            <VTab value="claimed">已认领（{{ claimTotal() }}）</VTab>
            <VTab value="soon">快到期（{{ claimSoon.length }}）</VTab>
            <VTab value="sites">站点能力（{{ claimSites.length }}）</VTab>
          </VTabs>
          <VWindow v-model="claimTab">
            <VWindowItem value="claimable">
              <div v-if="!claimClaimable.length" class="magicflow-table-empty">当前没有可认领的种（未满发布天数 / 无详情页 / 被安全阀挡住）。</div>
              <ul v-else class="magicflow-claim-list">
                <li v-for="row in claimClaimable" :key="row.hash" class="magicflow-claim-item">
                  <div class="magicflow-claim-item__main">
                    <span class="magicflow-claim-item__title">{{ row.title || row.hash }}</span>
                    <span class="magicflow-claim-item__meta">{{ row.site_name }} · {{ row.size_gb }}G · 做种 {{ claimSeedersText(row.seeders) }} · 发布 {{ claimAgeText(row.age_days) }}</span>
                  </div>
                  <VBtn size="x-small" variant="flat" color="primary" prepend-icon="mdi-seal" :disabled="claimCfg.dry" :loading="claimActing === ('do:' + row.hash)" @click="claimAsk('do', row)">认领</VBtn>
                </li>
              </ul>
            </VWindowItem>
            <VWindowItem value="claimed">
              <div v-if="!claimClaimed.length" class="magicflow-table-empty">还没有认领记录。</div>
              <ul v-else class="magicflow-claim-list">
                <li v-for="row in claimClaimed" :key="row.hash" class="magicflow-claim-item is-claimed">
                  <div class="magicflow-claim-item__main">
                    <span class="magicflow-claim-item__title">{{ row.title || row.hash }}</span>
                    <span class="magicflow-claim-item__meta">{{ row.site_name }} · {{ row.benefit || '权益' }} · {{ row.state }} <template v-if="row.note">· {{ row.note }}</template></span>
                  </div>
                  <VChip size="x-small" color="success" variant="tonal" prepend-icon="mdi-shield-lock-outline">硬保护</VChip>
                </li>
              </ul>
            </VWindowItem>
            <VWindowItem value="soon">
              <div v-if="!claimSoon.length" class="magicflow-table-empty">没有临近可认领的种。</div>
              <ul v-else class="magicflow-claim-list">
                <li v-for="row in claimSoon" :key="row.hash" class="magicflow-claim-item is-dim">
                  <div class="magicflow-claim-item__main">
                    <span class="magicflow-claim-item__title">{{ row.title || row.hash }}</span>
                    <span class="magicflow-claim-item__meta">{{ row.site_name }} · 发布 {{ claimAgeText(row.age_days) }} · {{ (row.block || []).join(' / ') }}</span>
                  </div>
                </li>
              </ul>
            </VWindowItem>
            <VWindowItem value="sites">
              <div v-if="!claimSites.length" class="magicflow-table-empty">没有启用中的任务站点。</div>
              <ul v-else class="magicflow-claim-list">
                <li v-for="s in claimSites" :key="s.site_id" class="magicflow-claim-item">
                  <div class="magicflow-claim-item__main">
                    <span class="magicflow-claim-item__title">{{ s.site_name }} <small class="is-dim">{{ s.domain }}</small></span>
                    <span v-if="s.supported" class="magicflow-claim-item__meta">
                      满 {{ claimProfile(s).min_age_days }} 天可认领 · 每颗 {{ claimProfile(s).max_claimers }} 名额 · 每人上限 {{ claimProfile(s).per_user_cap }}
                      · {{ claimProfile(s).benefit_desc || claimProfile(s).benefit }} · {{ claimPenaltyText(claimProfile(s)) }}
                    </span>
                    <span v-else class="magicflow-claim-item__meta">{{ claimProfile(s).reason || '暂不支持认领' }}</span>
                  </div>
                  <div class="magicflow-claim-item__stat">
                    <VChip size="x-small" variant="tonal">{{ s.claimed || 0 }} 已认领</VChip>
                    <VChip size="x-small" variant="tonal" color="primary">{{ s.claimable || 0 }} 可认领</VChip>
                  </div>
                </li>
              </ul>
            </VWindowItem>
          </VWindow>
        </VCardText>
      </VCard>
    </VDialog>

    <!-- ★ 静默池（silent，7.16.0）：无主种池的全局视图（只读） -->
    <VDialog v-model="silentOpen" max-width="52rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-silent-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">静默池</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VChip size="small" variant="tonal" color="primary">全局 · 跨站/跨任务的「无主」种</VChip>
            <VBtn variant="text" color="warning" size="small" prepend-icon="mdi-delete-sweep" @click="openPurge">清理（删除）</VBtn>
            <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-history" @click="openOperations('all')">操作记录</VBtn>
            <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="silentLoading" @click="loadSilent" />
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="silentOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-silent-body">
          <!-- 概览 -->
          <div class="magicflow-cs-stats">
            <div class="magicflow-cs-stat">
              <b>{{ silentSummary.total || 0 }}</b>
              <span>池内总数</span>
            </div>
            <div class="magicflow-cs-stat">
              <b>{{ silentSummary.hr || 0 }}</b>
              <span>欠 H&R</span>
            </div>
            <div class="magicflow-cs-stat">
              <b>{{ silentSummary.incomplete || 0 }}</b>
              <span>未下完</span>
            </div>
            <div class="magicflow-cs-stat">
              <b>{{ silentSubs.length }}</b>
              <span>子类</span>
            </div>
          </div>

          <!-- 子类 + 站点构成 -->
          <div class="magicflow-silent-chips">
            <VChip
              size="small"
              :variant="silentSub ? 'tonal' : 'flat'"
              :color="silentSub ? 'default' : 'primary'"
              @click="silentSub = ''"
            >全部（{{ silentSummary.total || 0 }}）</VChip>
            <VChip
              v-for="s in silentSubs"
              :key="s.key"
              size="small"
              :variant="silentSub === s.key ? 'flat' : 'tonal'"
              :color="silentSub === s.key ? 'primary' : 'default'"
              @click="silentSub = silentSub === s.key ? '' : s.key"
            >{{ s.label }}（{{ s.count }}）</VChip>
            <VChip
              size="small"
              :variant="silentOnlyHr ? 'flat' : 'tonal'"
              :color="silentOnlyHr ? 'warning' : 'default'"
              @click="silentOnlyHr = !silentOnlyHr"
            >只看欠 H&R（{{ silentSummary.hr || 0 }}）</VChip>
            <VSpacer />
            <span class="magicflow-cs-status__dim">
              共 {{ gbText(silentSummary.size_gb) }} · 静默托管每 {{ silentData.host?.interval_minutes ?? '—' }} 分钟一轮 · 上次 {{ silentData.host?.last_run || '—' }}
            </span>
          </div>

          <div v-if="silentSites.length" class="magicflow-silent-sites">
            <div
              v-for="s in silentSites"
              :key="s.site"
              class="magicflow-silent-site"
              :class="{ 'is-active': silentSite === s.site }"
              @click="silentSite = silentSite === s.site ? '' : s.site"
            >
              <span class="magicflow-silent-site__name">{{ s.site }}</span>
              <span class="magicflow-silent-site__num">{{ s.total }}</span>
              <span v-if="s.hr" class="magicflow-silent-site__hr">H&R {{ s.hr }}</span>
            </div>
          </div>

          <VTabs v-model="silentView" density="compact" class="mb-1">
            <VTab value="pool">池内种子（{{ silentItems.length }}）</VTab>
            <VTab value="records">静默托管记录（{{ silentRecords.length }}）</VTab>
          </VTabs>

          <VWindow v-model="silentView">
            <VWindowItem value="pool">
              <VTextField
                v-model="silentQ"
                density="compact"
                variant="outlined"
                hide-details
                prepend-inner-icon="mdi-magnify"
                placeholder="按标题过滤"
                class="mb-2"
                clearable
              />
              <div class="magicflow-cs-list">
                <article v-for="it in silentItems" :key="it.hash" class="magicflow-cs-card">
                  <div class="magicflow-cs-card__name" :title="it.title || it.hash">{{ it.title || it.hash }}</div>
                  <div class="magicflow-cs-card__meta">
                    <VChip size="x-small" variant="tonal" color="primary">{{ it.site }}</VChip>
                    <VChip size="x-small" variant="tonal">{{ silentSubLabel(it.sub) }}</VChip>
                    <span class="magicflow-cs-card__size">{{ gbText(it.size_gb) }}</span>
                    <VChip v-if="it.hr" size="x-small" variant="flat" color="warning">H&R {{ silentHrText(it) }}</VChip>
                    <VChip v-else size="x-small" variant="tonal">无 H&R</VChip>
                    <VChip
                      v-if="Number(it.progress) < 0.999"
                      size="x-small"
                      variant="flat"
                      color="info"
                    >下载中 {{ silentProgressText(it) }}</VChip>
                    <VChip v-if="it.crossseed" size="x-small" variant="tonal" color="secondary">跨站来源</VChip>
                    <span v-if="it.taken_by" class="magicflow-cs-status__dim">占用：{{ it.taken_by }}</span>
                  </div>
                </article>
                <div v-if="!silentItems.length" class="magicflow-table-empty">静默池为空。</div>
              </div>
              <div v-if="Number(silentData.items_truncated || 0) > 0" class="magicflow-cs-status__dim mt-1">
                还有 {{ silentData.items_truncated }} 条未展示（用过滤器缩小范围）
              </div>
            </VWindowItem>
            <VWindowItem value="records">
              <ul class="magicflow-silent-records">
                <li v-for="(r, i) in silentRecords" :key="i" class="magicflow-silent-record">
                  <span class="magicflow-silent-record__time">{{ tsText(r.ts) }}</span>
                  <span class="magicflow-silent-record__kind">{{ r.kind || 'run' }}</span>
                  <span class="magicflow-silent-record__text">{{ r.reason || `${r.count || 0} 项` }}</span>
                  <span v-if="r.duration_ms" class="magicflow-cs-status__dim">{{ (Number(r.duration_ms) / 1000).toFixed(1) }}s</span>
                </li>
                <li v-if="!silentRecords.length" class="magicflow-table-empty">暂无记录。</li>
              </ul>
            </VWindowItem>
          </VWindow>

          <div class="magicflow-settings-hint mt-2">
            静默池 = 「无主」种的池子：跨站取种下完的来源份、任务退下来的种、待分拣的新种都在这。
            H&R 保挂 / 未下完清理 / 超时降级（新→普通）/ 分拣（推荐&rarr;资源）由常驻「静默托管」自动跑。
            当前：静默-新超时 {{ silentData.settings?.new_timeout_hours ?? '—' }} 小时{{ stage1ZeroDelete ? ' · 阶段1 零删除（清理暂停）' : '' }}。
          </div>
        </VCardText>
      </VCard>
    </VDialog>

    <!-- 认领二次确认（写动作不可逆） -->
    <VDialog
      :model-value="!!claimConfirm",
      max-width="32rem"
      persistent
      @update:model-value="v => { if (!v) claimConfirm = null }"
    >
      <VCard class="magicflow-dialog">
        <VCardTitle class="text-subtitle-1 pt-4">{{ claimConfirm && claimConfirm.kind === 'abandon' ? '确认放弃认领' : '确认认领' }}</VCardTitle>
        <VCardText class="text-body-2">
          <template v-if="claimConfirm && claimConfirm.kind === 'batch'">
            将对「本轮可认领」的最多 {{ claimCfg.batch }} 个种子执行认领（每站每日上限 {{ claimCfg.daily }}）。
          </template>
          <template v-else-if="claimConfirm">
            将对 <strong>{{ claimConfirm.row.title || claimConfirm.row.hash }}</strong>（{{ claimConfirm.row.site_name }}）{{ claimConfirm.kind === 'abandon' ? '放弃认领' : '执行认领' }}。
          </template>
          <VAlert type="warning" variant="tonal" density="compact" class="mt-3">
            {{ claimConfirm && claimConfirm.kind === 'abandon'
              ? '放弃认领会丢失权益，且站点可能扣魔力。'
              : '认领后该种进入硬保护、永不自动删除；站点侧不达标可能扣魔力。' }}
          </VAlert>
        </VCardText>
        <VDivider />
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="!!claimActing" @click="claimConfirm = null">取消</VBtn>
          <VBtn :color="claimConfirm && claimConfirm.kind === 'abandon' ? 'error' : 'primary'" variant="flat" :loading="!!claimActing" @click="claimConfirmRun">确认</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
    <!-- 静默池「清理（删除）」（★ 13.0.0）：默认干跑，真写二次确认 -->
    <VDialog v-model="purgeOpen" max-width="46rem" scrollable :fullscreen="isNarrow">
      <VCard class="magicflow-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">静默池 · 清理（删除）</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="干跑刷新" :loading="purgeLoading" @click="loadPurge()" />
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="purgeOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="text-body-2">
          <div class="d-flex flex-wrap align-center gap-2 mb-2">
            <VSelect
              v-model="purgeSub"
              :items="purgeScopeOptions"
              item-title="label"
              item-value="value"
              density="compact"
              hide-details
              variant="outlined"
              style="max-width: 14rem"
              label="清理范围（默认只删静默-普通）"
              @update:model-value="loadPurge(0)"
            />
            <VTextField
              v-model.number="purgeBatch"
              type="number"
              density="compact"
              hide-details
              variant="outlined"
              style="max-width: 9rem"
              label="每批上限"
            />
          </div>
          <div class="magicflow-cs-stats">
            <div class="magicflow-cs-stat"><b>{{ purgeCounts.delete || 0 }}</b><span>清理候选</span></div>
            <div class="magicflow-cs-stat"><b>{{ purgeCounts.keep || 0 }}</b><span>保护不删</span></div>
            <div class="magicflow-cs-stat"><b>{{ purgeCounts.pause || 0 }}</b><span>违背不变量</span></div>
            <div class="magicflow-cs-stat"><b>{{ purgeCounts.missing || 0 }}</b><span>不在下载器</span></div>
          </div>
          <VAlert type="error" variant="tonal" density="compact" class="mt-2">
            <strong>会删除 qB 条目 + 磁盘文件，不可逆。</strong>清理 = 删条目<strong>+ 删文件</strong>
            （不在岗、不欠债、非资产、非保护）；保护类只列不动；删前过删除闸门（含「库内资产」硬拦）。
            <strong>默认干跑，不写任何东西。</strong>
          </VAlert>
          <div class="magicflow-settings-hint mt-2">
            <strong>补暂停</strong>（★ 12.7.1）：设计口径「静默池本意就是暂停不上传」——账本已是静默、
            但下载器里没停的种一律补 pause（幂等，<strong>只暂停、不删种、不动文件</strong>）。
            <span v-if="enforceCounts.violations">当前违背不变量 <b>{{ enforceCounts.violations }}</b> 个。</span>
            <span v-else>当前不变量成立（全 paused）。</span>
          </div>
          <table v-if="purgeBySite.length" class="magicflow-table mt-2">
            <thead><tr><th>站点</th><th>总数</th><th>清理候选</th></tr></thead>
            <tbody>
              <tr v-for="r in purgeBySite" :key="r.site">
                <td>{{ r.site }}</td><td>{{ r.total }}</td><td>{{ r.delete }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="purgeBlocked.length" class="magicflow-settings-hint mt-2">
            闸门拦截 {{ purgeBlocked.length }} 个：
            <span v-for="b in purgeBlocked.slice(0, 20)" :key="b.hash">{{ b.hash }}（{{ b.reason }}）· </span>
          </div>
        </VCardText>
        <VDivider />
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="purgeOpen = false">关闭</VBtn>
          <VBtn variant="tonal" color="info" :loading="enforceLoading" @click="loadEnforce(0)">查违背不变量</VBtn>
          <VBtn variant="tonal" color="warning" :loading="enforceLoading" @click="enforceAsk = true">补暂停</VBtn>
          <VBtn variant="tonal" color="warning" :loading="purgeActing === 'dry'" @click="loadPurge()">干跑</VBtn>
          <VBtn variant="flat" color="error" :loading="purgeActing === 'apply'" @click="purgeAsk = true">执行清理</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- 清理（删除）二次确认（真删条目 + 文件） -->
    <VDialog :model-value="purgeAsk" max-width="32rem" persistent @update:model-value="v => { if (!v) purgeAsk = false }">
      <VCard class="magicflow-dialog">
        <VCardTitle class="text-subtitle-1 pt-4">确认执行静默池清理</VCardTitle>
        <VCardText class="text-body-2">
          将对 <strong>{{ purgeCounts.delete || 0 }}</strong> 个「清理候选」<strong>删除 qB 条目 + 磁盘文件</strong>，
          保护类（欠 H&R / 库内资产 / 跨站来源份 / 认领 / 手动保留）不动。
          <VAlert type="error" variant="tonal" density="compact" class="mt-3">
            删条目 + 删文件，<strong>不可逆</strong>（同目录另有完成种则只删条目保留文件）。会先对违背不变量的种补 pause；每批上限 {{ purgeBatch }} 个。
          </VAlert>
        </VCardText>
        <VDivider />
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="purgeActing === 'apply'" @click="purgeAsk = false">取消</VBtn>
          <VBtn variant="flat" color="error" :loading="purgeActing === 'apply'" @click="runPurge()">确认清理</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- 补暂停二次确认（★ 12.7.1：只 pause，不删种） -->
    <VDialog :model-value="enforceAsk" max-width="32rem" persistent @update:model-value="v => { if (!v) enforceAsk = false }">
      <VCard class="magicflow-dialog">
        <VCardTitle class="text-subtitle-1 pt-4">确认补暂停</VCardTitle>
        <VCardText class="text-body-2">
          将对「账本已静默、但下载器里还在跑」的种补 pause（预计 <strong>{{ enforceCounts.violations || 0 }}</strong> 个）。
          <VAlert type="info" variant="tonal" density="compact" class="mt-3">
            只暂停：<strong>不删种、不动文件、不 resume</strong>；幂等可重跑。
          </VAlert>
        </VCardText>
        <VDivider />
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" :disabled="enforceLoading" @click="enforceAsk = false">取消</VBtn>
          <VBtn variant="flat" color="warning" :loading="enforceLoading" @click="enforceAsk = false; loadEnforce(1)">确认补暂停</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
<style scoped>
/* ── 豆瓣评分服务（magicflow-douban · 3.23.1）───────────────────── */
.magicflow-douban-dialog__body {
  padding-block: 12px;
}
.magicflow-douban-crawl {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 6px;
}
.magicflow-douban-crawl__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.8125rem;
}
.magicflow-douban-crawl__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 6px 12px;
  font-size: 0.8125rem;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.magicflow-douban-crawl__grid strong {
  color: rgb(var(--v-theme-primary));
}
.magicflow-douban-crawl__warn {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.8125rem;
  background: rgba(var(--v-theme-warning), 0.12);
  color: rgb(var(--v-theme-warning));
}
.magicflow-douban-crawl__warn--ok {
  background: rgba(var(--v-theme-success), 0.12);
  color: rgb(var(--v-theme-success));
}
.magicflow-douban-crawl__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

/* ── ★ 跨站取种：极简版（7.4.0 改版：低信息噪音 / 圆角卡片 / 大段文字折叠）── */
.magicflow-cs-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.magicflow-cs-stat {
  flex: 1 1 6.5rem;
  min-inline-size: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 12px 10px;
  border-radius: 14px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-border-color), 0.16);
}
.magicflow-cs-stat b {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
}
.magicflow-cs-stat span {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}
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
.magicflow-cs-card__chip.v-chip.is-success {
  background: rgba(var(--v-theme-success), 0.16) !important;
  color: rgb(var(--v-theme-success)) !important;
}
.magicflow-cs-card__chip.v-chip.is-warning {
  background: rgba(var(--v-theme-warning), 0.16) !important;
  color: rgb(var(--v-theme-warning)) !important;
}
.magicflow-cs-card__chip.v-chip.is-grey {
  background: rgba(var(--v-theme-on-surface), 0.12) !important;
  color: rgba(var(--v-theme-on-surface), 0.86) !important;
}
.magicflow-cs-bans {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block-end: 10px;
}
/* ★ 来源份 → 静默池（7.16.0）*/
.magicflow-cs-handoff {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-block: 10px 8px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(var(--v-theme-primary), 0.07);
  border: 1px solid rgba(var(--v-theme-primary), 0.22);
  font-size: 13px;
}
.magicflow-cs-handoff__icon { color: rgb(var(--v-theme-primary)); }
.magicflow-cs-handoff__text { min-inline-size: 0; line-height: 1.45; }
/* ★ 静默池页（7.16.0）*/
/* ★ 静默池弹窗头：手机上标题曾被右侧 chip+按钮挤成一字一行 → 标题不换行，动作单独一行 */
.magicflow-silent-dialog .magicflow-settings-dialog__head {
  flex-wrap: wrap;
  row-gap: 6px;
}
.magicflow-silent-dialog .magicflow-settings-dialog__title {
  flex: 0 0 auto;
  white-space: nowrap;
}
.magicflow-silent-dialog .magicflow-recommend-dialog__head-actions {
  flex: 1 1 100%;
  justify-content: flex-end;
}

.magicflow-silent-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block: 14px 8px;
}
.magicflow-silent-sites {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-block-end: 10px;
}
.magicflow-silent-site {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  cursor: pointer;
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-border-color), 0.16);
  font-size: 12px;
}
.magicflow-silent-site.is-active {
  background: rgba(var(--v-theme-primary), 0.14);
  border-color: rgba(var(--v-theme-primary), 0.4);
}
.magicflow-silent-site__num { font-weight: 700; font-variant-numeric: tabular-nums; }
.magicflow-silent-site__hr { color: rgb(var(--v-theme-warning)); }
.magicflow-silent-records {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.magicflow-silent-record {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.035);
  border: 1px solid rgba(var(--v-border-color), 0.14);
  font-size: 13px;
}
.magicflow-silent-record__time { font-variant-numeric: tabular-nums; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-silent-record__kind {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.09);
}
.magicflow-silent-record__text { flex: 1 1 12rem; min-inline-size: 0; }
.magicflow-cs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
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
.magicflow-cs-link {
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  text-decoration: underline;
}
.magicflow-cs-pending {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-block-start: 16px;
}
.magicflow-cs-pending__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
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

/* ── 跨站辅种：队列 / 流量兜底（3.11.0）────────────────────────────── */
.magicflow-crossseed-dialog__body {
  padding-block: 12px;
}
.magicflow-crossseed-guard {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding-block: 6px;
}
.magicflow-crossseed-bans {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 6px;
}
.magicflow-crossseed-ban {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid rgba(var(--v-border-color), 0.18);
  border-radius: 8px;
  background: rgba(var(--v-theme-error), 0.06);
}
.magicflow-crossseed-ban__main {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}
.magicflow-rules-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.75rem 0 0.25rem;
}

.magicflow-rules-table {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.5rem;
  max-height: 46vh;
  overflow-y: auto;
}

.magicflow-sort-rules {
  max-height: 34vh;
  overflow-y: auto;
  margin-bottom: 0.5rem;
}

.magicflow-sort-rules__row {
  display: grid;
  grid-template-columns: minmax(9rem, 1.6fr) 7rem 6rem 4rem 4rem;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.magicflow-sort-rules__row:nth-child(even) {
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.magicflow-sort-rules__row--head {
  font-weight: 600;
  opacity: var(--mf-op-mid);
}

.magicflow-sort-rules__add {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.magicflow-tag-migrate {
  margin-top: 0.5rem;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
}

.magicflow-tag-migrate__samples {
  max-height: 26vh;
  overflow-y: auto;
}

.magicflow-tag-migrate__row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 0.5rem;
  font-size: 0.8125rem;
  padding: 0.125rem 0;
}

.magicflow-tag-migrate__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.magicflow-tag-migrate__tags em {
  opacity: var(--mf-op-dim);
  text-decoration: line-through;
}

.magicflow-tag-migrate__tags strong {
  color: rgb(var(--v-theme-primary));
}

.magicflow-rules-row {
  display: grid;
  grid-template-columns: minmax(8rem, 1.6fr) 5rem 7rem 6rem 6rem 4.5rem;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.magicflow-rules-row:nth-child(even) {
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.magicflow-rules-row--head {
  font-weight: 600;
  opacity: var(--mf-op-mid);
}

.magicflow-rules-row__name {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.magicflow-rules-row__name em {
  font-style: normal;
  font-size: 0.7rem;
  opacity: var(--mf-op-dim);
}

.magicflow-rules-row__src {
  opacity: var(--mf-op-soft);
}

.magicflow-crossseed-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 6px;
}
.magicflow-crossseed-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-border-color), 0.18);
  border-radius: 8px;
}
.magicflow-crossseed-item__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-inline-size: 0;
  flex: 1 1 auto;
}
.magicflow-crossseed-item__main strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.magicflow-crossseed-item__meta {
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
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

.magicflow-scope-tag {
  margin-inline-start: 6px;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 10px;
  line-height: 1.6;
  opacity: var(--mf-op-dim);
  border: 1px solid currentColor;
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

/* ── 顶栏功能磁贴开关（7.10.1）────────────────────────────────── */
.magicflow-tile-switches {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px 14px;
  margin-top: 6px;
}
@media (max-width: 599px) {
  .magicflow-tile-switches { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* ── 全站辅种状态面板（7.10.0）────────────────────────────────── */
.magicflow-reseedpanel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.7));
  border-radius: 10px;
  background: rgba(var(--v-theme-surface), 0.35);
}
.magicflow-reseedpanel__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  line-height: 1.5;
}
.magicflow-reseedpanel__sites {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 2px;
}
.magicflow-reseedpanel__head,
.magicflow-reseedpanel__line {
  display: grid;
  grid-template-columns: minmax(0, 2.2fr) 0.7fr 0.7fr 1fr;
  gap: 8px;
  align-items: center;
  font-size: 12.5px;
}
.magicflow-reseedpanel__head {
  opacity: 0.6;
  font-weight: 600;
  border-bottom: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.6));
  padding-bottom: 4px;
}
.magicflow-reseedpanel__line {
  padding: 3px 0;
}
.magicflow-reseedpanel__line em {
  font-style: normal;
  opacity: 0.55;
}

/* ── 签到设置：头部 / 分块 / 字段 ─────────────────────────────── */
.magicflow-signin-hero {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(var(--v-theme-primary), 0.13), rgba(var(--v-theme-primary), 0.04));
  border: 1px solid rgba(var(--v-theme-primary), 0.18);
}

.magicflow-signin-hero__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  inline-size: 34px;
  block-size: 34px;
  flex: 0 0 auto;
  border-radius: 9px;
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
}

.magicflow-signin-hero__body {
  flex: 1 1 auto;
  min-inline-size: 0;
  display: grid;
  gap: 3px;
}

.magicflow-signin-hero__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.95rem;
  font-weight: 700;
  line-height: 1.3;
}

.magicflow-signin-hero__title > .v-chip {
  margin-inline-start: auto;
}

/* MoviePilot 会给表单控件套一层 .app-responsive-input（默认 ~72px 高），
   在自研分块里把它收紧，让间距由我们自己的 grid/gap 决定 */
.magicflow-settings-block .app-responsive-input {
  min-block-size: 0 !important;
  block-size: auto !important;
  padding-block: 0 !important;
  margin-block: 0 !important;
}

.magicflow-signin-hero__desc {
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

.magicflow-signin-hero__desc code {
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.08);
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

.magicflow-switch-list {
  display: grid;
  gap: 2px;
}

.magicflow-field-stack {
  display: grid;
  gap: 14px;
}

.magicflow-field {
  display: grid;
  gap: 4px;
  min-inline-size: 0;
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

/* 考核 / 签到 设置（借鉴「站点自动签到」插件的站点多选） */
.magicflow-settings-field {
  display: block;
  margin-block: 8px 4px;
}

.magicflow-settings-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 8px 12px;
  margin-block-start: 8px;
}

.magicflow-signin-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-block-start: 8px;
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

.magicflow-exam-plan__notes {
  margin: 0;
  padding-inline-start: 1.1em;
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

/* 签到报表页（按「几十个站点」的规模设计：汇总 → 今日（可筛可搜）→ 近 7 天点阵） */
.magicflow-signin-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}

.magicflow-signin-stat {
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.magicflow-signin-stat__v {
  font-size: 1.35rem;
  font-weight: 700;
  line-height: 1.15;
}

.magicflow-signin-stat__l {
  margin-block-start: 2px;
  font-size: 0.68rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-signin-stat.is-ok .magicflow-signin-stat__v { color: rgb(var(--v-theme-success)); }
.magicflow-signin-stat.is-fail .magicflow-signin-stat__v { color: rgb(var(--v-theme-error)); }
.magicflow-signin-stat.is-pending .magicflow-signin-stat__v { color: rgb(var(--v-theme-warning)); }

.magicflow-signin-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block: 8px;
}

.magicflow-signin-search {
  flex: 1 1 140px;
  min-inline-size: 120px;
}

.magicflow-signin-today {
  display: grid;
  gap: 2px;
  max-block-size: 44vh;
  overflow: auto;
}

/* ★ 7.17.0 账号保活段（最后登入 / 距删号红线） */
.magicflow-keepalive {
  display: grid;
  gap: 4px;
}

.magicflow-keepalive-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 7px 8px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-inline-start: 3px solid rgba(var(--v-theme-on-surface), 0.2);
  min-inline-size: 0;
}

.magicflow-keepalive-row.is-warn {
  background: rgba(245, 158, 11, 0.12);
  border-inline-start-color: #f59e0b;
}

.magicflow-keepalive-row.is-ok { border-inline-start-color: rgb(var(--v-theme-success)); }

.magicflow-keepalive-row__name {
  flex: 0 0 auto;
  font-size: 0.82rem;
  font-weight: 600;
}

.magicflow-keepalive-row__time {
  flex: 0 1 auto;
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.76rem;
  opacity: 0.8;
}

.magicflow-keepalive-row__left {
  margin-inline-start: auto;
  flex: 0 0 auto;
  font-size: 0.76rem;
  font-weight: 600;
  white-space: nowrap;
  opacity: 0.85;
}

.magicflow-keepalive-row__left.is-warn { color: #b45309; }
.magicflow-keepalive-row__left.is-ok { color: rgb(var(--v-theme-success)); }

.magicflow-signin-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-block: 7px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  min-inline-size: 0;
}

.magicflow-signin-row__dot {
  flex: 0 0 auto;
  inline-size: 8px;
  block-size: 8px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.25);
}

.magicflow-signin-row__dot.is-ok { background: rgb(var(--v-theme-success)); }
.magicflow-signin-row__dot.is-signfail { background: rgb(var(--v-theme-error)); }
.magicflow-signin-row__dot.is-loginfail { background: #f59e0b; }
.magicflow-signin-row__dot.is-fail { background: #b91c1c; }
.magicflow-signin-row__dot.is-pending { background: rgb(var(--v-theme-warning)); }
.magicflow-signin-row__dot.is-skip { background: rgba(var(--v-theme-on-surface), 0.3); }

/* 失败行整体着色：签到失败=红 / 登录失败=橙 / 都失败=深红 */
.magicflow-signin-row.is-signfail .magicflow-signin-row__msg { color: rgb(var(--v-theme-error)); }
.magicflow-signin-row.is-loginfail .magicflow-signin-row__msg { color: #b45309; }
.magicflow-signin-row.is-fail .magicflow-signin-row__msg { color: #b91c1c; font-weight: 600; }

.magicflow-signin-row__name {
  flex: 0 1 auto;
  min-inline-size: 5.5em;
  max-inline-size: 46%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.82rem;
  font-weight: 600;
}

.magicflow-signin-row__msg {
  flex: 1 1 auto;
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: end;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-signin-matrix {
  max-block-size: 52vh;
  overflow: auto;
}

.magicflow-signin-matrix__row {
  display: grid;
  grid-template-columns: minmax(70px, 1fr) repeat(7, 26px);
  align-items: center;
  gap: 2px;
  padding-block: 3px;
  min-inline-size: 0;
}

.magicflow-signin-matrix__row.is-head {
  position: sticky;
  inset-block-start: 0;
  z-index: 1;
  background: rgb(var(--v-theme-surface));
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

.magicflow-signin-matrix__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.76rem;
}

.magicflow-signin-matrix__date {
  font-size: 0.6rem;
  text-align: center;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-signin-cell {
  display: inline-block;
  inline-size: 12px;
  block-size: 12px;
  margin-inline: auto;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-signin-cell.is-ok { background: rgb(var(--v-theme-success)); }
.magicflow-signin-cell.is-signfail { background: rgb(var(--v-theme-error)); }
.magicflow-signin-cell.is-loginfail { background: #f59e0b; }
.magicflow-signin-cell.is-fail { background: #b91c1c; }
.magicflow-signin-cell.is-pending { background: rgb(var(--v-theme-warning)); }
.magicflow-signin-cell.is-skip { background: rgba(var(--v-theme-on-surface), 0.3); }

.magicflow-signin-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-block-start: 8px;
  font-size: 0.66rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-signin-legend > span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.magicflow-signin-legend .magicflow-signin-cell {
  margin-inline: 0;
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

.magicflow-stat-grid--single {
  grid-template-columns: minmax(0, 1fr);
  margin-block-start: 12px;
}

/* ★ 可观测：本轮决策 + 趋势 sparkline */
.mf-obs {
  margin-block-start: 12px;
}
.mf-health__hint {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-block-end: 8px;
}
.mf-health__item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-block-end: 6px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.mf-health__item.is-error { border-inline-start: 3px solid rgb(var(--v-theme-error)); }
.mf-health__item.is-warning { border-inline-start: 3px solid rgb(var(--v-theme-warning)); }
.mf-health__item.is-info { border-inline-start: 3px solid rgb(var(--v-theme-info)); }
.mf-health__icon { margin-block-start: 2px; }
.mf-health__item.is-error .mf-health__icon { color: rgb(var(--v-theme-error)); }
.mf-health__item.is-warning .mf-health__icon { color: rgb(var(--v-theme-warning)); }
.mf-health__item.is-info .mf-health__icon { color: rgb(var(--v-theme-info)); }
.mf-health__body { flex: 1 1 auto; min-inline-size: 0; }
.mf-health__title { font-size: 13px; font-weight: 600; }
.mf-health__detail { font-size: 12px; color: rgba(var(--v-theme-on-surface), 0.65); word-break: break-word; }

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
.mf-obs__rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-block-start: 4px;
}
.mf-obs__row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
}
.mf-obs__row > span {
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.mf-obs__row > strong {
  font-weight: 500;
  word-break: break-word;
}
.mf-obs__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.mf-spark-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.mf-spark__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.65);
}
.mf-spark__head strong {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}
.mf-spark__head em {
  font-style: normal;
  font-size: 11px;
  margin-inline-start: 4px;
}
.mf-spark__head em.is-up { color: rgb(var(--v-theme-success)); }
.mf-spark__head em.is-down { color: rgb(var(--v-theme-error)); }
.mf-spark__svg {
  display: block;
  inline-size: 100%;
  block-size: 26px;
  margin-block: 4px;
}
.mf-spark__line { stroke-width: 1.5; }
.mf-spark__line--primary { stroke: rgb(var(--v-theme-primary)); }
.mf-spark__line--info { stroke: rgb(var(--v-theme-info)); }
.mf-spark__line--secondary { stroke: rgb(var(--v-theme-secondary)); }
.mf-spark__line--success { stroke: rgb(var(--v-theme-success)); }
.mf-spark__foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.magicflow-stat-grid--single .magicflow-stat {
  min-block-size: auto;
  padding-block: 12px;
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

.magicflow-settings-hint--warn {
  background: rgba(var(--v-theme-warning), 0.10);
  border-inline-start: 3px solid rgb(var(--v-theme-warning));
  padding: 8px 10px;
  border-radius: 8px;
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
  background: rgba(var(--v-theme-warning), 0.12);
  border-inline-start-color: rgb(var(--v-theme-warning));
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
  color: rgba(var(--v-theme-on-surface), 0.85);
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
  background: rgba(var(--v-theme-primary), 0.07);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.16);
}

.magicflow-torrent-dialog__grid > div {
  min-inline-size: 0;
}

.magicflow-torrent-dialog__grid dt {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
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
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}

.magicflow-torrent-dialog__hash code {
  flex: 1 1 auto;
  min-inline-size: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  overflow-wrap: anywhere;
  color: rgba(var(--v-theme-on-surface), 0.8);
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
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}

.magicflow-cloud-dialog__summary strong {
  font-size: 1.05rem;
  color: rgb(var(--v-theme-primary));
}

.magicflow-cloud-dialog__summary i {
  font-style: normal;
  opacity: var(--mf-op-dim);
}

.magicflow-cloud-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
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
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
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
    border-block-start: 1px solid rgba(var(--v-border-color), 0.1);
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
  border: 2px solid rgba(var(--v-border-color), 0.5);
  background: transparent;
  color: transparent;
  z-index: 1;
}

.magicflow-flow__label {
  font-size: 10.5px;
  line-height: 1.2;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim));
  white-space: nowrap;
}

.magicflow-flow__node.is-done .magicflow-flow__label {
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim));
}

/* 连接线：未执行=浅灰虚线；已走过=紫色实线 */
.magicflow-flow__line {
  position: absolute;
  top: 14px;
  right: -50%;
  width: 100%;
  height: 0;
  border-top: 2px dashed rgba(var(--v-border-color), 0.5);
  z-index: 0;
}

.magicflow-flow__line.is-done {
  border-top-style: solid;
  border-top-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.35);
}

/* 已完成：紫色实心圆 + 白色对勾，无光晕 */
.magicflow-flow__node.is-done .magicflow-flow__dot {
  border-color: rgb(var(--v-theme-primary));
  background: linear-gradient(150deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
  box-shadow: 0 4px 14px rgba(var(--v-theme-primary), 0.35), inset 0 1px 0 rgba(var(--v-theme-on-primary), 0.25);
  color: rgb(var(--v-theme-on-primary));
}

/* 运行中：紫色实心圆 + 白色对勾 + 细小缓慢脉冲环 + 微弱光晕（仅当前节点） */
.magicflow-flow__node.is-running .magicflow-flow__dot {
  border-color: rgb(var(--v-theme-primary));
  background: linear-gradient(150deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
  color: rgb(var(--v-theme-on-primary));
  box-shadow: 0 0 10px rgba(var(--v-theme-primary), 0.5);
}

.magicflow-flow__node.is-running .magicflow-flow__dot::before,
.magicflow-flow__node.is-running .magicflow-flow__dot::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 50%;
  border: 1.5px solid rgba(var(--v-theme-primary), 0.85);
  animation: magicflow-halo 2.6s cubic-bezier(0.22, 0.61, 0.36, 1) infinite;
}

.magicflow-flow__node.is-running .magicflow-flow__dot::before {
  animation-delay: 1.3s;
}

.magicflow-flow__node.is-running .magicflow-flow__label {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}

/* 出错：红色实心圆 + 白色感叹号 */
.magicflow-flow__node.is-error .magicflow-flow__dot {
  border-color: rgb(var(--v-theme-error));
  background: rgb(var(--v-theme-error));
  color: rgb(var(--v-theme-on-primary));
}

/* 运行流程右上角阶段标签（预览图：阶段名 pill + 呼吸圆点） */
.magicflow-flow__tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(var(--v-theme-primary), 0.3);
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
}

.magicflow-flow__tag i {
  inline-size: 6px;
  block-size: 6px;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
  box-shadow: 0 0 8px rgb(var(--v-theme-primary));
}

.magicflow-flow__tag.is-live i {
  animation: magicflow-blink 1.6s ease-in-out infinite;
}

.magicflow-flow__tag.is-error {
  border-color: rgba(var(--v-theme-error), 0.32);
  background: rgba(var(--v-theme-error), 0.16);
  color: rgb(var(--v-theme-error));
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
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(var(--v-theme-on-surface), 0.04);
}

.magicflow-page .magicflow-task-item {
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid transparent;
  border-radius: 12px;
}

.magicflow-page .magicflow-task-item--selected {
  background: rgba(var(--v-theme-primary), 0.16);
  border-color: rgba(var(--v-theme-primary), 0.42);
}

.magicflow-page .magicflow-task-item:hover {
  background: rgba(var(--v-theme-primary), 0.1);
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
  color: rgb(var(--v-theme-primary));
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
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.magicflow-page .magicflow-reason__track i {
  border-radius: 999px;
  background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
  box-shadow: 0 0 12px rgba(var(--v-theme-primary), 0.5);
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
  background: rgba(var(--v-theme-on-surface), 0.03);
}

/* 底部宿主悬浮导航会盖住内容，预留安全间距 */
@media (max-width: 699px) {
  .magicflow-page {
    padding-block-end: 76px;
  }
}

/* ── ★ 手机端首页（任务列表）────────────────────────────────────────── */
.magicflow-page .magicflow-mobile-home { display: none; }
.magicflow-page .magicflow-mobile-back { display: none; }

.magicflow-page .mh-hero {
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  padding: 18px 18px 16px;
  border-radius: 18px;
  background: linear-gradient(140deg, rgba(var(--v-theme-primary), 0.20), rgba(var(--v-theme-primary), 0.05));
  border: 1px solid rgba(var(--v-theme-primary), 0.30);
}
.magicflow-page .mh-hero__main { min-inline-size: 0; flex: 1 1 auto; }
.magicflow-page .mh-hero__chev { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); flex: 0 0 auto; }
.magicflow-page .mh-hero__v { font-size: 34px; font-weight: 800; letter-spacing: 0.5px; line-height: 1; }
.magicflow-page .mh-hero__v small { font-size: 14px; font-weight: 600; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-inline-start: 4px; }
.magicflow-page .mh-hero__s { margin-block-start: 8px; font-size: 12.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }

.magicflow-page .mh-group { display: flex; flex-direction: column; gap: 8px; margin-block-start: 16px; }
.magicflow-page .mh-group__head {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 6px; background: transparent; border: 0;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); font: inherit; font-size: 12.5px; cursor: pointer;
}
.magicflow-page .mh-group__head .mh-count { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-page .mh-group__head .v-icon { margin-inline-start: auto; }
.magicflow-page .mh-list { display: flex; flex-direction: column; gap: 8px; }

.magicflow-page .mh-row {
  display: flex; align-items: center; gap: 12px; width: 100%; text-align: start;
  padding: 14px; border-radius: 15px;
  background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: inherit; font: inherit; cursor: pointer;
  transition: background-color 0.15s ease;
}
.magicflow-page .mh-row:active { background: rgba(var(--v-theme-primary), 0.14); }
.magicflow-page .mh-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; background: rgba(var(--v-theme-on-surface), 0.45); }
.magicflow-page .mh-dot.is-primary,
.magicflow-page .mh-dot.is-success { background: rgb(var(--v-theme-primary)); box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.8); }
.magicflow-page .mh-dot.is-error { background: rgb(var(--v-theme-error)); box-shadow: 0 0 8px rgba(var(--v-theme-error), 0.7); }
.magicflow-page .mh-dot.is-warning { background: rgb(var(--v-theme-warning)); box-shadow: 0 0 8px rgba(var(--v-theme-warning), 0.7); }
.magicflow-page .mh-row__main { min-inline-size: 0; flex: 1 1 auto; display: flex; flex-direction: column; gap: 3px; }
.magicflow-page .mh-row__nm { font-size: 14.5px; font-weight: 650; }
.magicflow-page .mh-row__tag {
  margin-inline-start: 7px; font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 7px;
  color: rgb(var(--v-theme-primary)); background: rgba(var(--v-theme-primary), 0.18); vertical-align: 1.5px;
}
.magicflow-page .mh-sublist { margin: 2px 0 6px 14px; border-inline-start: 1px solid rgba(var(--v-border-color), 0.18); padding-inline-start: 10px; }
.magicflow-page .mh-subrow {
  display: flex; align-items: center; gap: 9px; inline-size: 100%; text-align: start; padding: 9px 6px;
  background: none; border: 0; color: inherit; font: inherit; cursor: pointer; border-radius: 10px;
}
.magicflow-page .mh-subrow:active { background: rgba(var(--v-theme-primary), 0.12); }
.magicflow-page .mh-subrow .mh-row__nm { font-size: 13px; font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.82); }
.magicflow-page .mh-subrow .mh-row__num { font-size: 14px; font-weight: 700; color: rgba(var(--v-theme-on-surface), 0.7); }
.magicflow-page .mh-row__st { font-size: 11.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-page .mh-row__num { font-size: 16px; font-weight: 800; flex: 0 0 auto; }
.magicflow-page .mh-row__chev { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); flex: 0 0 auto; }

.magicflow-page .mh-sect { margin-block-start: 22px; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); letter-spacing: 0.4px; padding: 0 6px 6px; }
.magicflow-page .mh-tools { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; }
.magicflow-page .mh-tool {
  display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 6px;
  border-radius: 15px; background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); font: inherit; font-size: 12px; cursor: pointer;
}
.magicflow-page .mh-tool:active { background: rgba(var(--v-theme-primary), 0.14); }
.magicflow-page .mh-tool__scope {
  margin-inline-start: 4px;
  padding: 0 4px;
  border-radius: 4px;
  font-style: normal;
  font-size: 10px;
  line-height: 1.5;
  /* 透明度不再叠加：文字色继承 .mh-tool（浅色主题已加深） */
  border: 1px solid currentColor;
}
.magicflow-page .mh-foot { display: flex; gap: 10px; margin-block-start: 22px; }

.magicflow-page .mh-btn {
  flex: 1 1 0; display: flex; align-items: center; justify-content: center; gap: 6px;
  block-size: 46px; border-radius: 14px; border: 0; cursor: pointer;
  font-size: 14px; font-weight: 650; color: rgb(var(--v-theme-on-primary));
  background: linear-gradient(145deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
}
.magicflow-page .mh-btn--ghost {
  background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}

@media (max-width: 959px) {
  /* 列表页：显示首页，隐藏工作区与旧移动工具栏 / 桌面计数胶囊 */
  .magicflow-page--m-list .magicflow-mobile-home {
    display: flex; flex-direction: column; padding: 2px 0 6px;
  }
  .magicflow-page--m-list .magicflow-layout,
  .magicflow-page--m-list .magicflow-mobile-toolbar { display: none; }
  /* 手机端隐藏自相矛盾的运行计数胶囊（信息已由首页大数承担） */
  .magicflow-page .magicflow-enabled-chip { display: none; }
  /* 详情页：隐藏首页 */
  .magicflow-page--m-detail .magicflow-mobile-home { display: none; }
  /* 详情页显示返回列表按钮 */
  .magicflow-page .magicflow-mobile-back { display: inline-flex; }
}

/* ── ★ 手机端任务详情：紧凑块 ─────────────────────────── */
.magicflow-page .magicflow-mobile-detail { display: none; }
.magicflow-page .md-verdict {
  display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-radius: 16px;
  background: linear-gradient(140deg, rgba(var(--v-theme-success), 0.15), rgba(var(--v-theme-success), 0.04));
  border: 1px solid rgba(var(--v-theme-success), 0.32);
}
.magicflow-page .md-verdict.is-warn {
  background: linear-gradient(140deg, rgba(var(--v-theme-error), 0.15), rgba(var(--v-theme-error), 0.04));
  border-color: rgba(var(--v-theme-error), 0.34);
}
.magicflow-page .md-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; background: rgb(var(--v-theme-primary)); box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.8); }
.magicflow-page .md-dot.is-error { background: rgb(var(--v-theme-error)); box-shadow: 0 0 8px rgba(var(--v-theme-error), 0.7); }
.magicflow-page .md-dot.is-warning { background: rgb(var(--v-theme-warning)); box-shadow: 0 0 8px rgba(var(--v-theme-warning), 0.7); }
.magicflow-page .md-dot.is-secondary { background: rgba(var(--v-theme-on-surface), 0.45); box-shadow: none; }
.magicflow-page .md-verdict__body { min-inline-size: 0; }
.magicflow-page .md-v { font-size: 15px; font-weight: 750; color: rgb(var(--v-theme-success)); }
.magicflow-page .md-verdict.is-warn .md-v { color: rgb(var(--v-theme-error)); }
.magicflow-page .md-s { font-size: 11.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-block-start: 2px; }
.magicflow-page .md-act {
  margin-inline-start: auto; flex: 0 0 auto; font: inherit; font-size: 12px; font-weight: 650;
  padding: 7px 13px; border-radius: 10px; cursor: pointer; color: rgb(var(--v-theme-on-primary));
  background: rgba(var(--v-theme-error), 0.92); border: 1px solid rgba(var(--v-theme-error), 0.92);
}
.magicflow-page .md-cards { display: flex; gap: 9px; margin-block-start: 12px; }
.magicflow-page .md-card { flex: 1 1 0; min-inline-size: 0; background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd); border-radius: 15px; padding: 14px 12px; }
.magicflow-page .md-card b { font-size: 19px; font-weight: 800; display: block; letter-spacing: 0.2px; }
.magicflow-page .md-card span { font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); margin-block-start: 6px; display: block; }
.magicflow-page .md-strategy { margin-block-start: 10px; font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); padding: 0 4px; line-height: 1.5; }
.magicflow-page .md-entries { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin-block-start: 14px; }
.magicflow-page .md-entry {
  flex: 1 1 0; display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 6px;
  border-radius: 15px; background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); font: inherit; font-size: 12px; cursor: pointer;
}
.magicflow-page .md-entry.is-active { color: rgb(var(--v-theme-primary)); border-color: rgba(var(--v-theme-primary), 0.5); background: rgba(var(--v-theme-primary), 0.16); }

@media (max-width: 959px) {
  .magicflow-page--m-detail .magicflow-mobile-detail { display: block; }
  /* 手机端：取消平级四 tab，改为紧凑块 + 次级入口 */
  .magicflow-page .magicflow-tabs { display: none; }
  /* 概览窗口里的旧大块内容在手机端隐藏（信息已收进紧凑块 / 任务配置页） */
  .magicflow-page .magicflow-window .magicflow-window-ov .magicflow-stat-grid,
  .magicflow-page .magicflow-window .magicflow-window-ov .magicflow-overview-grid { display: none; }
  .magicflow-page .magicflow-window { padding-block-start: 12px; }
}

/* ── ★ 设置页手机端目录（桌面端隐藏，仍用标签栏）────────────── */
.magicflow-settings-nav { display: none; }
.magicflow-settings-nav__item {
  display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px 6px;
  border-radius: 14px; background: rgba(var(--v-theme-surface), 0.9); border: 1px solid rgba(var(--v-border-color), 0.16);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); font: inherit; font-size: 12px; cursor: pointer;
}
.magicflow-settings-nav__item.is-active { color: rgb(var(--v-theme-primary)); border-color: rgba(var(--v-theme-primary), 0.5); background: rgba(var(--v-theme-primary), 0.16); }

/* ── ★ 操作记录独立页 ─────────────────────────────── */
.magicflow-ops-dialog { display: flex; flex-direction: column; }
.magicflow-ops-dialog__spacer { flex: 1 1 auto; }
.magicflow-ops-dialog__sub { padding: 6px 18px 4px; font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-ops-dialog__tabs { display: flex; gap: 4px; padding: 0 14px 4px; }
/* ★ §1 点播弹窗 */
.magicflow-ondemand-dialog { display: flex; flex-direction: column; }
.magicflow-ondemand-dialog__body { padding: 10px 18px 20px; overflow: auto; flex: 1 1 auto; min-height: 0; }
.magicflow-ondemand-form { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-start; margin-top: 8px; }
.magicflow-ondemand-form > .v-input:first-child { flex: 1 1 100%; }
.magicflow-ondemand-form > .v-input:not(:first-child) { flex: 1 1 12rem; max-width: 24rem; }
.magicflow-ondemand-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.magicflow-ondemand-hint { margin: 2px 0 10px; padding: 8px 10px; border-radius: 10px; background: rgba(var(--v-theme-primary), 0.10); font-size: 0.84rem; line-height: 1.6; }
.magicflow-ondemand-hint strong { color: rgb(var(--v-theme-primary)); }
.magicflow-ondemand-hint__legend { margin-top: 4px; font-size: 0.76rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-ondemand-hint__legend em { font-style: normal; font-weight: 600; color: rgb(var(--v-theme-on-surface)); }
.magicflow-ondemand-list { display: flex; flex-direction: column; gap: 6px; }
.magicflow-ondemand-item { border: 1px solid rgba(var(--v-theme-on-surface), 0.14); border-radius: 8px; padding: 6px 8px; }
.magicflow-ondemand-item--auto { border-color: rgba(var(--v-theme-primary), 0.55); box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.22); }
.magicflow-ondemand-item__act { display: flex; justify-content: flex-end; margin-top: 6px; }
.magicflow-ondemand-item__title { font-size: 0.8rem; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-all; }
.magicflow-ondemand-item__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 4px; font-size: 0.74rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
/* ★ §4.1 辅种流水单表 */
.magicflow-reseed { display: flex; flex-direction: column; font-size: 12px; }
.magicflow-reseed__head, .magicflow-reseed__row { display: grid; grid-template-columns: 8.5em minmax(0, 0.8fr) 5.2em minmax(0, 2fr) 4.2em 4.2em; gap: 8px; align-items: center; padding: 5px 2px; }
.magicflow-reseed__head { font-weight: 600; opacity: var(--mf-op-dim); border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12); position: sticky; top: 0; background: rgb(var(--v-theme-surface)); z-index: 1; }
.magicflow-reseed__row { border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06); }
.magicflow-reseed__row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-reseed .is-time { font-variant-numeric: tabular-nums; opacity: var(--mf-op-soft); }
.magicflow-reseed .is-num { text-align: right; font-variant-numeric: tabular-nums; }
.magicflow-reseed .is-stage { opacity: 0.8; }
/* ★ 窄屏（手机 390px）：6 列固定宽会把表撑到 463px 横向溢出 —— 缩小字号并隐去「大小」列（4+1 列） */
@media (max-width: 640px) {
  .magicflow-reseed { font-size: 11px; }
  .magicflow-reseed__head, .magicflow-reseed__row { grid-template-columns: 5.6em minmax(0, 0.9fr) 4.4em minmax(0, 1.7fr) 3.4em; gap: 6px; }
  .magicflow-reseed__head > span:nth-child(5),
  .magicflow-reseed__row > span:nth-child(5) { display: none; }
}
.magicflow-ops-dialog__body { padding: 6px 18px 20px; overflow: auto; flex: 1 1 auto; min-height: 0; }
/* 操作记录 / 站点容量 弹窗：让列表撑满卡片可滚区，不再被 .magicflow-events 的 52dvh 上限截断，下方留一大片空白 */
.magicflow-ops-dialog .magicflow-events { max-block-size: none; margin-block-start: 0; padding-inline-end: 0; overflow: visible; }
.magicflow-ceiling-dialog { display: flex; flex-direction: column; }

/* ── ★ 功能弹窗统一：卡片纵向 flex + 正文吃掉剩余高度（消除手机端全屏弹窗底部大片留白）──
   原先这些弹窗正文被限高（推荐/考核 68dvh、云盘 70dvh）且卡片不伸展 → 全屏时下半屏全空。 */
.magicflow-cloud-dialog,
.magicflow-douban-dialog,
.magicflow-ondemand-dialog,
.magicflow-crossseed-dialog,
.magicflow-recommend-dialog,
.magicflow-exam-dialog,
.magicflow-torrent-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}
.magicflow-cloud-dialog__body,
.magicflow-douban-dialog__body,
.magicflow-crossseed-dialog__body,
.magicflow-recommend-dialog__body {
  flex: 1 1 auto;
  min-block-size: 0;
  max-block-size: none;
  overflow-y: auto;
  overscroll-behavior: contain;
}
/* 种子详情：内容在顶、操作按钮钉底，中间自然撑开（手机端全屏不再留白）*/
.magicflow-torrent-dialog__actions { margin-block-start: auto; }
.magicflow-ceiling-list { display: flex; flex-direction: column; gap: 15px; }
.magicflow-ceiling-row__head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.magicflow-ceiling-row__nm { font-size: 14px; font-weight: 650; }
.magicflow-ceiling-row__val { font-size: 13px; font-weight: 700; color: rgb(var(--v-theme-primary)); flex: 0 0 auto; }
.magicflow-ceiling-row__val small { font-size: 10px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-inline-start: 1px; }
.magicflow-ceiling-bar { margin-block-start: 7px; height: 7px; border-radius: 4px; background: rgba(var(--v-border-color), 0.16); overflow: hidden; }
.magicflow-ceiling-bar i { display: block; height: 100%; border-radius: 4px; background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary))); }
.magicflow-ceiling-bar i.is-full { background: linear-gradient(90deg, rgb(var(--v-theme-warning)), rgb(var(--v-theme-error))); }
.magicflow-ceiling-row__foot { display: flex; justify-content: space-between; margin-block-start: 5px; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-ceiling-empty { font-size: 12.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); text-align: center; padding: 20px 0; }
/* ── 站点报表（11.10.0）：站点级逐条种子状态 ──────────────── */
.magicflow-sitereport__bar { display: flex; align-items: center; gap: 10px; }
.magicflow-sitereport__site { flex: 1 1 auto; max-width: 22rem; }
.magicflow-sitereport__stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-block-end: 10px; }
.magicflow-sitereport__stat { background: rgba(var(--v-theme-on-surface), 0.04); border-radius: 10px; padding: 8px 10px; text-align: center; }
.magicflow-sitereport__stat b { display: block; font-size: 20px; font-weight: 700; line-height: 1.15; }
.magicflow-sitereport__stat span { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-sitereport__stat.is-danger b { color: rgb(var(--v-theme-error)); }
.magicflow-sitereport__chips { display: flex; flex-wrap: wrap; gap: 6px; margin-block-end: 10px; }
.magicflow-sitereport__note { font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-block-end: 8px; }
.magicflow-sitereport__err { font-size: 12px; color: rgb(var(--v-theme-error)); margin-block-end: 8px; }
.magicflow-sitereport__list { display: flex; flex-direction: column; gap: 2px; }
.magicflow-sitereport__row { display: flex; align-items: center; gap: 9px; padding: 7px 4px; border-radius: 8px; }
.magicflow-sitereport__row:hover { background: rgba(var(--v-theme-on-surface), 0.04); }
.magicflow-sitereport__row-b { flex: 0 0 auto; }
.magicflow-sitereport__row-main { flex: 1 1 auto; min-width: 0; }
.magicflow-sitereport__row-t { font-size: 13px; font-weight: 550; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-sitereport__row-s { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-sitereport__row-size { flex: 0 0 auto; font-size: 12px; font-weight: 600; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
@media (max-width: 959px) {
  .magicflow-sitereport__stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .magicflow-sitereport__bar { flex-wrap: wrap; }
  .magicflow-sitereport__site { max-width: none; }
}
@media (max-width: 959px) {
  .magicflow-ops-dialog__body { padding: 4px 14px 18px; }
}
@media (max-width: 959px) {
  .magicflow-settings-dialog__tabs { display: none; }
  /* ★ 手机端设置：分类「目录页」（2 列网格，恢复 3.33.0 版式）。
     点分类 = 跳转到该分类的「表单页」——目录不再和表单挤在同一屏，正文拿回整屏高度。 */
  .magicflow-settings-nav {
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px; padding: 12px 16px 18px; overflow: visible;
  }
  .magicflow-settings-nav__item {
    padding: 18px 10px; font-size: 12.5px;
  }
  .magicflow-settings-nav__item.is-active { background: rgba(var(--v-theme-primary), 0.22); }
}

/* ── ★ 功能页（整页弹窗）内部网格手机端适配 ───────────────── */
@media (max-width: 959px) {
  .magicflow-dialog .magicflow-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .magicflow-dialog .magicflow-stat-grid--single { grid-template-columns: minmax(0, 1fr); }
  .magicflow-dialog .magicflow-config-grid { grid-template-columns: minmax(0, 1fr); }
  .magicflow-dialog .magicflow-facts--two { grid-template-columns: minmax(0, 1fr); }
  .magicflow-dialog .magicflow-run-summary { grid-template-columns: minmax(0, 1fr); }
  .magicflow-settings-dialog .magicflow-settings-grid { grid-template-columns: minmax(0, 1fr); }
  .magicflow-settings-dialog .magicflow-settings-switches { grid-template-columns: minmax(0, 1fr); }
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

<style scoped>
/* ── 认领（7.14.0）──────────────────────────────────────────────── */
.magicflow-claim-hero { display: flex; align-items: center; gap: 18px; padding: 4px 2px 12px; flex-wrap: wrap; }
.magicflow-claim-hero__item { display: flex; flex-direction: column; line-height: 1.1; }
.magicflow-claim-hero__item .num { font-size: 1.35rem; font-weight: 700; }
.magicflow-claim-hero__item .cap { font-size: .72rem; opacity: .62; }
.magicflow-claim-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.magicflow-claim-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
}
.magicflow-claim-item.is-claimed { border-color: rgba(var(--v-theme-success), .35); }
.magicflow-claim-item.is-dim { opacity: .7; }
.magicflow-claim-item__main { display: flex; flex-direction: column; min-width: 0; flex: 1 1 auto; gap: 2px; }
.magicflow-claim-item__title { font-size: .82rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-claim-item__meta { font-size: .7rem; opacity: .62; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-claim-item__stat { display: flex; gap: 4px; flex: 0 0 auto; }
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
  .magicflow-torrent-dialog { padding-bottom: 92px; }
}
</style>
