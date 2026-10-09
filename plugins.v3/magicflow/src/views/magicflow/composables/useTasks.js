// MagicFlow 前端 · useTasks 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：selectedTaskId, api, emit, hostToast, settingsDraft, selectTask, warmingTimer（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, ref } from 'vue'
import { cloneTask } from '../../../utils'
import { formatBonus } from '../../../utils'
import { formatBytes } from '../../../utils'
import { normalizeSettings } from '../../../utils'
import { normalizeSortRules } from '../../../utils'
import { normalizeTask } from '../../../utils'
import { runModeMeta } from '../../../utils'
import { taskStateMeta } from '../../../utils'
import { unwrapResponse } from '../../../utils'

export function useTasks({ selectedTaskId, api, emit, hostToast, settingsDraft, selectTask, warmingTimer }) {
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
  const editorOpen = ref(false)
  const editorTask = ref({})
  const deleteDialog = ref(false)
  let warmingRetryCount = 0
  const tasks = computed(() => status.value.tasks || [])
  const defaultSavePath = computed(() => (status.value.defaults || {}).save_path || '')
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
  const selectedRunMode = computed(() => runModeMeta(selectedTask.value?.run_mode || 'running'))
  function taskBadge(task) {
    const mode = task?.run_mode || 'running'
    if (mode === 'seeding') return runModeMeta('seeding')
    if (mode === 'stopped') return runModeMeta('stopped')
    return taskStateMeta(task?.state, task?.enabled ?? true)
  }
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
  function notify(message, color = 'success') {
    const method = ['error', 'info', 'warning', 'success'].includes(color) ? color : 'success'
    if (typeof hostToast?.[method] === 'function') {
      hostToast[method](message)
    } else if (method === 'error') {
      error.value = message
    }
  }
  async function loadStatus() {
    loading.value = true
    try {
      status.value = unwrapResponse(await api.tasks.status()) || status.value
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
        hr_complete_ratio: status.value.hr_complete_ratio ?? 0.999,
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
  function openCreateTask() {
    editorTask.value = cloneTask(status.value.defaults || {})
    editorOpen.value = true
  }
  function openEditTask() {
    if (!selectedTask.value) return
    editorTask.value = cloneTask(selectedTask.value)
    editorOpen.value = true
  }
  async function saveTask(payload) {
    saving.value = true
    try {
      const normalized = normalizeTask(payload)
      if (normalized.id) {
        unwrapResponse(await api.tasks.update(normalized.id, normalized))
      } else {
        delete normalized.id
        unwrapResponse(await api.tasks.create(normalized))
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
      handover.value = unwrapResponse(await api.tasks.handoverInfo(selectedTask.value.id)) || null
      // ★ 默认退回静默池（正常就该这样）；要指定交棒得自己选 —— 同标签任务本来就会自动接管，无需交棒
      handoverTarget.value = 'idle'
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      handoverLoading.value = false
    }
  }
  async function confirmDeleteTask() {
    if (!selectedTask.value) return
    saving.value = true
    try {
      const q = handoverTarget.value === 'idle'
        ? '?settle=idle'
        : `?handover_to=${encodeURIComponent(handoverTarget.value)}`
      const res = await api.tasks.remove(selectedTask.value.id, q)
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

  return {
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
  }
}
