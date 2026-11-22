// MagicFlow 前端 · useOperations 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api, error, notify, selectedTaskId, tasks（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'
import { KIND_TEXT, OPS_KIND_FILTERS, RESEED_KINDS } from '../constants'
// S14 / F6：9 个展示纯函数原先在本文件、components/dialogs/OpsDialog.vue、
// components/tabs/JournalTab.js 三处逐字重复，现统一从 ../opsDisplay 引入。
// 返回对象仍原样带上这 9 个键 —— index.vue 依赖该结构，保持零破坏。
import {
  hasOpDetail,
  itemSourceText,
  opDetailItems,
  operationColor,
  operationDuration,
  operationIcon,
  operationKindText,
  operationStateText,
  operationSummary,
} from '../opsDisplay'

export function useOperations({ api, error, notify, selectedTaskId, tasks }) {
  const operationData = ref({ operations: [], total: 0 })
  const opsOpen = ref(false)
  const opsScope = ref('all')
  function openOperations(scope = 'all') {
    opsScope.value = scope
    opsOpen.value = true
    if (scope === 'all') loadOperationsAll()
    else if (selectedTaskId.value) loadOperations(selectedTaskId.value)
    else operationData.value = { operations: [], total: 0 }
  }
  const expandedOps = ref({})
  const eventRows = ref([])
  const eventsLoading = ref(false)
  const eventLevel = ref('')
  async function loadEventRows() {
    eventsLoading.value = true
    try {
      const q = ['limit=200', 'min_level='].join('&')
      let qs = `${q}`
      if (eventLevel.value === 'error') qs += '&level=error'
      if (eventLevel.value === 'warning') qs += '&min_level=warning'
      if (eventLevel.value === 'info') qs += '&level=info'
      if (opsScope.value === 'task' && selectedTaskId.value) qs += `&task_id=${encodeURIComponent(selectedTaskId.value)}`
      const data = unwrapResponse(await api.pool.events(qs)) || {}
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
  const opsKind = ref('')
  const opsKindItems = computed(() => {
    // ★ 下拉里只放短标签（不带条数）：手机端窄，带条数会被省略号截断
    // ★ 19.12.71：基础表 + 「数据里出现过但表里没有」的兜底。后端新增 kind 时，
    //   下拉会自己长出来，不用再回来改前端（原来写死 8 项，live 两天 474 条却筛不到）。
    const out = OPS_KIND_FILTERS.map((k) => ({ value: k.value, label: k.label }))
    const seen = new Set(out.map((o) => o.value))
    for (const r of operationData.value.operations || []) {
      const k = String(r.kind || '')
      if (!k || seen.has(k)) continue
      seen.add(k)
      out.push({ value: k, label: KIND_TEXT[k] || k })
    }
    return out
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
  function isOpDetailOpen(opId) {
    return !!expandedOps.value[opId]
  }
  function toggleOpDetail(opId) {
    expandedOps.value = { ...expandedOps.value, [opId]: !expandedOps.value[opId] }
  }
  const opsView = ref('flow') // 'flow'=全部流水 · 'reseed'=辅种流水 · 'timeline'=事件流
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
  const backfilling = ref(false)
  async function backfillPages() {
    const taskId = selectedTaskId.value
    if (!taskId || backfilling.value) return
    backfilling.value = true
    try {
      const data = unwrapResponse(await api.tasks.backfillPages(taskId)) || {}
      notify(`已回填 ${data.resolved || 0} 个详情页链接${data.unresolved ? `（${data.unresolved} 个未匹配）` : ''}`)
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '回填失败', 'error')
    } finally {
      backfilling.value = false
    }
  }
  function opsQuery() {
    // ★ 19.12.71 ①：无条件带 limit。原来不选类型时不带 limit，后端默认只给 100 条，
    //   而 live + tag 两天就 900 多条 → 其它类型永远挤不进第一屏（看起来像「类型全缺了」）。
    // ★ 19.12.71 ②：辅种流水按 reseed 类向服务端要 —— 服务端带 kind 时窗口放宽到 2000，
    //   否则稀少的辅种记录会被 tag/live 冲到 500 条以外，前端再怎么筛都筛不出来。
    let kinds = opsKind.value
    if (!kinds && opsView.value === 'reseed') kinds = RESEED_KINDS.join(',')
    const parts = ['limit=500']
    if (kinds) parts.unshift(`kind=${encodeURIComponent(kinds)}`)
    return `?${parts.join('&')}`
  }
  async function loadOperations(taskId) {
    try {
      operationData.value = unwrapResponse(
        await api.tasks.taskOperations(taskId, opsQuery()),
      ) || {
        operations: [],
        total: 0,
      }
    } catch (err) {
      error.value = err?.message || String(err)
    }
  }
  async function loadOperationsAll() {
    opsLoadingAll.value = true
    try {
      operationData.value = unwrapResponse(await api.pool.operations(opsQuery())) || {
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
  const opsLoadingAll = ref(false)
  function taskLabel(taskId) {
    if (!taskId) return '—'
    if (taskId === '__silent_host__') return '静默池'
    if (taskId === '__reseed__') return '全站辅种'
    if (taskId.startsWith('silent:')) return '静默·' + taskId.slice('silent:'.length)
    const t = tasks.value.find((x) => x.id === taskId)
    return t ? t.name || taskId : taskId
  }

  return {
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
  }
}
