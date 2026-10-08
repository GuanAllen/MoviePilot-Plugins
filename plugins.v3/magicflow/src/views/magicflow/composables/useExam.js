// MagicFlow 前端 · 新手考核域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：顶栏考核角标 + 汇总弹窗（站点按紧急度排序 / 每项进度 / 未过项折叠 / 警告前置）
//       + 一键起考核任务；自带 300s 角标刷新定时器（随组件生命周期）。
// 依赖注入：api、notify（提示）、loadStatus（起完任务后刷新任务列表）。
// ★ 真值源仍在后端（/exam、/exam/act）；考核是增强信息，取数失败不打断界面。
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { unwrapResponse } from '../../../utils'
import { EXAM_KIND_TEXT, EXAM_KIND_ICON, EXAM_ACTIONABLE } from '../constants'

export function useExam({ api, notify, loadStatus }) {
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
      examData.value = unwrapResponse(await api.features.exam()) || examData.value
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
      const res = unwrapResponse(await api.features.examAct(q)) || {}
      notify(res.message || '已执行')
      examConfirm.value = null
      await loadExam()
      await loadStatus()
    } catch (err) {
      notify(`执行失败：${err?.message || err}`, 'error')
    } finally {
      examActing.value = ''
    }
  }

  // 考核角标是全局的（低频刷新；关闭时服务端立即返回，零开销）——随组件生命周期起停
  onMounted(() => {
    loadExam()
    examTimer = window.setInterval(loadExam, 300000)
  })
  onUnmounted(() => {
    if (examTimer) window.clearInterval(examTimer)
  })

  return { examData, examOpen, examActing, examConfirm, examBadge, examUrgent, examShowPassed, examRows, examPendingSites, examNext, examUrgentWeek, examPendingItems, examDaysShort, examUrgencyColor, examPassedCount, examSitePct, examItemPct, examItemGap, examVisibleItems, examHiddenPassed, examTogglePassed, examActions, loadExam, openExam, examAct, examConfirmRun }
}
