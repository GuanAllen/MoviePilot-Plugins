// MagicFlow 前端 · useTaskDetail 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api, siteIcons, error, selectedTask, selectedTaskId, taskLoading（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, ref } from 'vue'
import { runStatusText } from '../../../utils'
import { unwrapResponse } from '../../../utils'
import { FLOW_STEPS_BONUS, FLOW_STEPS_BRUSH } from '../constants'

export function useTaskDetail({ api, siteIcons, error, selectedTask, selectedTaskId, taskLoading }) {
  const detail = ref(null)
  const bonusData = ref({ torrents: [], total_bonus: 0, torrent_count: 0, protected_count: 0 })
  const bonusLoadedFor = ref('')
  const bonusCache = {}
  const candidateData = ref({ candidates: [], total: 0, reason_counts: {} })
  const candidateLoadedAt = ref(0)
  const candidateLoadedFor = ref('')
  const detailAttention = computed(() => selectedTask.value?.attention || detailStats.value?.attention || null)
  const taskIsBrush = computed(() => selectedTask.value?.task_type === 'brush')
  const siteUser = computed(() => detailStats.value?.site_user || selectedTask.value?.site_user || {})
  const taskConfig = computed(() => selectedTask.value || {})
  const brushSeedDays = computed(() => {
    const v = taskConfig.value?.brush_seed_days
    return v === undefined || v === null || v === '' ? 2 : Number(v)
  })
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
  const decision = computed(() => detailStats.value?.last_decision || {})
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
      const data = unwrapResponse(await api.tasks.trend()) || {}
      trendSeries.value = data.series || {}
    } catch (err) {
      trendSeries.value = {}
    }
  }
  const trendTask = computed(() => trendSeries.value[`task:${selectedTaskId.value}`] || [])
  const trendSite = computed(() => trendSeries.value[`site:${selectedTask.value?.site_id}`] || [])
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
  const flowSteps = computed(() => (taskIsBrush.value ? FLOW_STEPS_BRUSH : FLOW_STEPS_BONUS))
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
  const flowPhaseText = computed(() => {
    if (detail.value?.run_active) {
      const running = flowNodes.value.find(item => item.state === 'running')
      if (running) return running.label
    }
    const step = flowSteps.value.find(item => item.key === (detail.value?.last_phase || ''))
    return step ? step.label : runStatusText(detail.value?.last_run_status)
  })
  async function loadDetail(taskId) {
    try {
      detail.value = unwrapResponse(await api.tasks.detail(taskId))
    } catch (err) {
      error.value = err?.message || String(err)
    }
    loadTrend(taskId)
  }
  async function loadBonus(taskId, { silent = false } = {}) {
    if (!silent) taskLoading.value = true
    try {
      const data = unwrapResponse(await api.tasks.bonus(taskId)) || bonusData.value
      bonusData.value = data
      bonusCache[taskId] = data
      bonusLoadedFor.value = taskId
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      if (!silent) taskLoading.value = false
    }
  }
  async function loadCandidates(taskId) {
    taskLoading.value = true
    try {
      candidateData.value = unwrapResponse(await api.tasks.candidates(taskId)) || {
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

  return {
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
  }
}
