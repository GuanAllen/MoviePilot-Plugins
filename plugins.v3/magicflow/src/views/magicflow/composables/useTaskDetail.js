// MagicFlow 前端 · useTaskDetail 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api, siteIcons, error, selectedTask, selectedTaskId, taskLoading（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'
import { FLOW_STEPS_BONUS, FLOW_STEPS_BRUSH } from '../constants'
import { currencyOf } from './useCurrency'

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
    // ★ 19.12.10：单位优先用后端下发的 `goal_unit`（已按站点自称算好，19.12.10 起不再恒为
    //   「魔力值」）；后端没给时才本地兜底 —— 兜底也要跟着站点币名，不能写死「魔力值」。
    const unit = t.goal_unit || (t.task_type === 'brush' ? 'GB' : currencyOf(t))
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
  // ★ 19.12.13：任务详情左栏「本任务时魔趋势」大图（设计稿 2:1242）。
  // 与小 sparkline 同源（task: 优先，退回 site:），但输出真实序列点的折线与坐标刻度 ——
  // sparkline 的 path 只有 26 高、且被 normalize 到 100 宽，放大到 132 高会糊掉细节。
  // 算不出（<2 点）返回 null，由模板整卡不渲染（铁律 6：宁可没有，不给假曲线）。
  const trendMain = computed(() => {
    const src = trendTask.value.length ? trendTask.value : trendSite.value
    const vs = (src || [])
      .filter(p => p && p.bonus !== null && p.bonus !== undefined)
      .map(p => Number(p.bonus) || 0)
    if (vs.length < 2) return null
    const min = Math.min(...vs)
    const max = Math.max(...vs)
    const span = max - min || 1
    const W = 1000
    const H = 100
    const step = W / (vs.length - 1)
    const y = v => (H - ((v - min) / span) * H).toFixed(2)
    const line = vs.map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(2)},${y(v)}`).join(' ')
    const hours = Math.max(vs.length - 1, 1)
    return {
      scope: trendTask.value.length ? '任务' : '站点',
      path: line,
      // 面积填充：折线 → 右下角 → 左下角闭合（渐变 fill 用）
      area: `${line} L${W},${H} L0,${H} Z`,
      count: vs.length,
      min,
      max,
      last: vs[vs.length - 1],
      // 4 条水平刻度：从上到下 max → min
      ticks: [0, 1, 2, 3].map(i => ({ value: max - (span * i) / 3, y: (H * i) / 3 })),
      // 3 个横轴标签：跨度按点数估（每小时一个采样）
      xLabels: [`${hours}h 前`, `${Math.round(hours / 2)}h 前`, '现在'],
    }
  })
  const flowSteps = computed(() => (taskIsBrush.value ? FLOW_STEPS_BRUSH : FLOW_STEPS_BONUS))
  // 五阶段各自的状态。**唯一真值源是后端的逐阶段记录 `run_stages`**（19.12.20 起 record_phase 逐阶段留痕）。
  // 为什么不再用 `last_phase` 兜底：它只是一个「当前位置」——
  //   · 一轮结束被写成 done → 拿它推出来五步全绿，可它只证明「这一轮结束了」，不证明每步都跑过；
  //   · 任务不跑（做种/停止模式）时它是空 → 五步全灰，而右上角又按 last_run_status 说「完成」；
  //   · 这轮只跑完入口（并发满提前收工）时它也是 done → 五步全绿，实际后四步根本没跑。
  // 没有逐阶段记录 = 没有证据 = 显示「未执行」，别再给假绿（用户报的就是这个）。
  const flowNodes = computed(() => {
    const d = detail.value || {}
    const steps = flowSteps.value
    const active = !!d.run_active
    const stages = d.run_stages || {}
    return steps.map((step) => {
      const rec = stages[step.key] || null
      let state = rec?.state ? String(rec.state) : 'idle'
      let ms = Number(rec?.ms || 0)
      const at = Number(rec?.at || 0)
      // running 只在「本轮真的还在跑」时成立。进程崩溃/重启后残留的 running 是中断，不是正在跑
      if (state === 'running' && !active) {
        state = 'error'
        ms = 0
      }
      return { ...step, state, ms, at, recorded: !!rec }
    })
  })
  const flowPhaseText = computed(() => {
    const d = detail.value || {}
    const nodes = flowNodes.value
    const recorded = nodes.some(item => item.recorded)
    if (d.run_active) {
      const running = nodes.find(item => item.state === 'running')
      if (running) return running.label
      // 在跑但一个阶段都没打点 → 此刻跑的不是刷流流程（「做种中」模式跑的是检查/优化周期）。
      return recorded ? '执行中' : '维护中'
    }
    // 一轮跑完 / 中断：说这一轮自己的结论
    const bad = nodes.find(item => item.state === 'error')
    if (bad) return `中断于${bad.label}`
    if (recorded) return '完成'
    // 一条阶段记录都没有 = 这一轮没跑（做种/停止模式）。别用 last_run_status 冒充「完成」
    return '未执行'
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
    trendMain,
    trendSeries,
    trendSite,
    trendTask,
  }
}
