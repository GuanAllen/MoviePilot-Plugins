export const taskDefaults = {
  id: '',
  name: '',
  enabled: true,
  site_id: null,
  site_domain: null,
  site_name: null,
  downloader: '',
  brush_tag: null,
  save_path: null,
  task_type: 'bonus',
  brush_grace_minutes: 15,
  upload_idle_minutes: 10,
  upload_min_kbps: 200,
  brush_min_leechers: 1,
  brush_interval: 5,
  check_interval: 1,
  cron_expression: null,
  active_time_range: null,
  min_bonus_per_hour: null,
  max_keep_torrents: null,
  bonus_protect_threshold: null,
  min_bonus_to_keep: null,
  disk_size_gb: null,
  refill_when_empty: true,
  max_add_per_run: 10,
  max_download_concurrent: 10,
  top_n: 30,
  browse_pages: 3,
  reuse_existing: true,
  reuse_verify: true,
  cleanup_no_progress: true,
  no_progress_minutes: 30,
  cleanup_slow_progress: true,
  slow_progress_grace_minutes: 60,
  slow_progress_max_hours: 48,
  purge_unfree_incomplete: true,
  auto_resume_paused: true,
  ti_source: 'publish',
  seen_cooldown_hours: 24,
  bonus_t0: null,
  bonus_n0: null,
  bonus_b0: null,
  bonus_l: null,
  bonus_zero_weight: null,
  size: null,
  seeder: null,
  pubtime: null,
  include: null,
  exclude: null,
  freeleech: '',
  hr: null,
  min_seed_time: 0,
  min_ratio: 0,
  delete_files: true,
  exclude_zero_bonus: true,
  rss_support: false,
  up_speed: null,
  dl_speed: null,
}

/** 统一提取宿主 API 客户端与标准响应模型中的业务数据。 */
export function unwrapResponse(response) {
  if (response && Object.prototype.hasOwnProperty.call(response, 'success')) {
    if (response.success === false) throw new Error(response.message || '操作失败')
    return response.data
  }
  return response?.data ?? response
}

/** 基于完整默认值创建可安全编辑的任务深拷贝。 */
export function cloneTask(task = {}) {
  return JSON.parse(JSON.stringify({ ...taskDefaults, ...(task || {}) }))
}

/** 把表单空值和数字字段标准化为后端请求模型需要的类型。 */
export function normalizeTask(task) {
  const result = cloneTask(task)
  const nullableNumbers = [
    'brush_interval',
    'check_interval',
    'min_bonus_per_hour',
    'max_keep_torrents',
    'bonus_protect_threshold',
    'min_bonus_to_keep',
    'disk_size_gb',
    'bonus_t0',
    'bonus_n0',
    'bonus_b0',
    'bonus_l',
    'bonus_zero_weight',
    'min_seed_time',
    'min_ratio',
    'up_speed',
    'dl_speed',
    'site_id',
  ]
  const optionalText = [
    'brush_tag',
    'save_path',
    'cron_expression',
    'active_time_range',
    'size',
    'seeder',
    'pubtime',
    'include',
    'exclude',
    'hr',
  ]
  nullableNumbers.forEach(key => {
    const raw = result[key]
    if (raw === '' || raw === null || raw === undefined) {
      result[key] = null
      return
    }
    const value = Number(raw)
    result[key] = Number.isFinite(value) ? value : null
  })
  optionalText.forEach(key => {
    result[key] = String(result[key] ?? '').trim() || null
  })
  result.name = String(result.name || '').trim()
  result.downloader = String(result.downloader || '').trim()
  result.site_id = Number(result.site_id)
  result.brush_interval = Number(result.brush_interval || 5)
  result.check_interval = Number(result.check_interval || 1)
  result.refill_when_empty = Boolean(result.refill_when_empty)
  result.max_add_per_run = Number(result.max_add_per_run || 10)
  result.max_download_concurrent = Number(result.max_download_concurrent || 10)
  result.top_n = Number(result.top_n || 30)
  result.browse_pages = Number(result.browse_pages || 3)
  result.reuse_existing = Boolean(result.reuse_existing ?? true)
  result.reuse_verify = Boolean(result.reuse_verify ?? true)
  result.cleanup_no_progress = Boolean(result.cleanup_no_progress ?? true)
  result.no_progress_minutes = Number(result.no_progress_minutes || 30)
  result.cleanup_slow_progress = Boolean(result.cleanup_slow_progress ?? true)
  result.slow_progress_grace_minutes = Number(result.slow_progress_grace_minutes || 60)
  result.slow_progress_max_hours = Number(result.slow_progress_max_hours || 48)
  result.purge_unfree_incomplete = Boolean(result.purge_unfree_incomplete ?? true)
  result.auto_resume_paused = Boolean(result.auto_resume_paused ?? true)
  result.ti_source = ['publish', 'seed_time'].includes(result.ti_source) ? result.ti_source : 'publish'
  result.seen_cooldown_hours = Number(result.seen_cooldown_hours ?? 24)
  result.freeleech = result.freeleech || ''
  result.task_type = ['bonus', 'brush'].includes(result.task_type) ? result.task_type : 'bonus'
  result.brush_grace_minutes = Number(result.brush_grace_minutes ?? 15)
  result.upload_idle_minutes = Number(result.upload_idle_minutes ?? 10)
  result.upload_min_kbps = Number(result.upload_min_kbps ?? 200)
  result.brush_min_leechers = Number(result.brush_min_leechers ?? 1)
  result.delete_files = Boolean(result.delete_files)
  result.exclude_zero_bonus = Boolean(result.exclude_zero_bonus)
  result.rss_support = Boolean(result.rss_support)
  result.enabled = Boolean(result.enabled)
  return result
}

/** 标准化全局设置。 */
export function normalizeSettings(settings = {}) {
  const journalKeep = Number(settings.journal_keep)
  const requestInterval = Number(settings.request_interval)
  return {
    enabled: Boolean(settings.enabled),
    show_sidebar_nav: Boolean(settings.show_sidebar_nav),
    debug_log: Boolean(settings.debug_log),
    compact_mode: Boolean(settings.compact_mode),
    journal_keep: Number.isFinite(journalKeep) ? Math.max(0, Math.round(journalKeep)) : 200,
    request_interval: Number.isFinite(requestInterval) ? Math.max(0, requestInterval) : 0,
  }
}

/** 标准化「下载器全局参数」（速度单位 KB/s）。 */
export function normalizeDownloaderPrefs(prefs = {}) {
  const num = (value, fallback) => {
    const n = Number(value)
    return Number.isFinite(n) ? n : fallback
  }
  return {
    download_limit_kbps: Math.max(0, num(prefs.download_limit_kbps, 0)),
    upload_limit_kbps: Math.max(0, num(prefs.upload_limit_kbps, 0)),
    max_connec: Math.max(0, Math.round(num(prefs.max_connec, 500))),
    max_connec_per_torrent: Math.max(0, Math.round(num(prefs.max_connec_per_torrent, 100))),
    max_uploads: Math.round(num(prefs.max_uploads, 50)),
    max_uploads_per_torrent: Math.round(num(prefs.max_uploads_per_torrent, 10)),
    max_active_downloads: Math.round(num(prefs.max_active_downloads, 3)),
    max_active_torrents: Math.round(num(prefs.max_active_torrents, 5)),
    queueing_enabled: Boolean(prefs.queueing_enabled),
  }
}

/** 标准化「下载目录」（qBittorrent 全局路径）。 */
export function normalizeDownloaderPaths(paths = {}) {
  return {
    save_path: String(paths.save_path || ''),
    temp_path: String(paths.temp_path || ''),
    temp_path_enabled: Boolean(paths.temp_path_enabled),
  }
}

/** 标准化「默认任务模板」。 */
export function normalizeDefaults(raw = {}) {
  const num = (value, fallback) => {
    const n = Number(value)
    return Number.isFinite(n) ? n : fallback
  }
  return {
    downloader: String(raw.downloader || ''),
    save_path: String(raw.save_path || ''),
    brush_interval: Math.max(1, Math.round(num(raw.brush_interval, 5))),
    check_interval: Math.max(1, Math.round(num(raw.check_interval, 1))),
    max_add_per_run: Math.max(1, Math.round(num(raw.max_add_per_run, 10))),
    max_download_concurrent: Math.max(1, Math.round(num(raw.max_download_concurrent, 10))),
    top_n: Math.max(1, Math.round(num(raw.top_n, 30))),
    browse_pages: Math.max(1, Math.round(num(raw.browse_pages, 3))),
    seen_cooldown_hours: Math.max(0, num(raw.seen_cooldown_hours, 24)),
    refill_when_empty: raw.refill_when_empty !== false,
    reuse_existing: raw.reuse_existing !== false,
    reuse_verify: raw.reuse_verify !== false,
    cleanup_no_progress: raw.cleanup_no_progress !== false,
    cleanup_slow_progress: raw.cleanup_slow_progress !== false,
    purge_unfree_incomplete: raw.purge_unfree_incomplete !== false,
    auto_resume_paused: raw.auto_resume_paused !== false,
    delete_files: raw.delete_files !== false,
  }
}

/** 将字节数格式化为适合紧凑界面展示的容量文本。 */
export function formatBytes(value) {
  const bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const number = bytes / 1024 ** index
  return `${number >= 100 ? number.toFixed(0) : number.toFixed(1)} ${units[index]}`
}

/** 将秒 / 毫秒 / ISO 时间统一格式化为月日与时分。 */
export function formatDateTime(value) {
  if (value === null || value === undefined || value === '') return '暂无'
  let input = value
  if (typeof input === 'number') {
    // 后端时间戳以秒为单位
    input = input < 1e12 ? input * 1000 : input
  }
  const date = new Date(input)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

/** 计算一次运行记录的秒级耗时。 */
export function formatDuration(startedAt, finishedAt) {
  if (!startedAt || !finishedAt) return '-'
  const toMs = value => (typeof value === 'number' ? (value < 1e12 ? value * 1000 : value) : new Date(value).getTime())
  const seconds = Math.max(Math.round((toMs(finishedAt) - toMs(startedAt)) / 1000), 0)
  return `${seconds} 秒`
}

/** 把秒数格式化成中文耗时文本。 */
export function formatDurationSeconds(seconds) {
  const value = Number(seconds || 0)
  if (!Number.isFinite(value) || value <= 0) return '-'
  if (value < 60) return `${value.toFixed(1)} 秒`
  const minutes = Math.floor(value / 60)
  const rest = Math.round(value - minutes * 60)
  return `${minutes} 分 ${rest} 秒`
}

/** 最近一次运行状态的中文文本。 */
export function runStatusText(status) {
  const map = { done: '完成', noop: '无需动作', skipped: '已跳过', failed: '失败' }
  return map[status] || '未执行'
}

/** 格式化每小时魔力产出。 */
export function formatBonus(value) {
  const number = Number(value || 0)
  return `${number.toFixed(2)} /h`
}

/** 返回任务状态对应的中文文本、主题色和图标。 */
export function taskStateMeta(state, enabled = true) {
  const states = {
    running: { text: '运行中', color: 'success', icon: 'mdi-check-circle-outline' },
    idle: { text: '空闲', color: 'success', icon: 'mdi-check-circle-outline' },
    seeding: { text: '做种中', color: 'primary', icon: 'mdi-seed-outline' },
    downloading: { text: '下载中', color: 'info', icon: 'mdi-download-outline' },
    paused: { text: '已暂停', color: 'secondary', icon: 'mdi-pause-circle-outline' },
    error: { text: '运行异常', color: 'error', icon: 'mdi-alert-circle-outline' },
    disabled: { text: '插件停用', color: 'secondary', icon: 'mdi-stop-circle-outline' },
  }
  if (state === 'disabled' || !enabled) return states.paused
  return states[state] || states.running
}

/** 计算魔力打分相对占比（用于简易进度展示）。 */
export function bonusShare(value, max) {
  const peak = Number(max || 0)
  if (!peak) return 0
  return Math.min(Math.round((Number(value || 0) * 100) / peak), 100)
}
