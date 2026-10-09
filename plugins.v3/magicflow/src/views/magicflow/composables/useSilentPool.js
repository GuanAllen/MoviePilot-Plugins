// MagicFlow 前端 · 静默池域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：静默池弹窗（无主种池跨站/跨任务全局视图）状态 + 过滤派生 + 拉取 + 展示文案。
// 依赖注入：api、notify（拉取失败提示）。
// ★ 真值源仍在后端（标签账本 tag_state + 下载器快照 → /silent_pool）。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'
import { SILENT_SUB_LABEL } from '../constants'
import { formatRemain } from '../format'

export function useSilentPool({ api, notify }) {
  // ── 静默池（silent，7.16.0）：无主种池（跨站 / 跨任务）的全局视图 ────────────────
  //   真值源 = 标签账本 tag_state（state=静默）+ 下载器快照；H&R 倒计时来自跨站来源份账本。
  //   ★ 关系：跨站「下完」的来源份 → 移交静默池（跨站页只留未下完的列车）。
  const silentData = ref({ summary: {}, items: [], records: [], host: {}, settings: {} })
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
      silentData.value = unwrapResponse(await api.poolstats.silentPool()) || silentData.value
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

  return {
    silentData, silentOpen, silentLoading, silentView, silentSub, silentSite, silentOnlyHr, silentQ,
    silentSummary, silentSites, silentSubs, silentRecords, silentItems,
    loadSilent, openSilent,
  }
}

// ── 纯展示函数（P4：静默池弹窗组件按具名导入复用；单一真值源，不在两处各写一份）──
export function silentProgressText(it) {
  const p = Number(it?.progress)
  if (!Number.isFinite(p) || p < 0) return '—'
  if (p >= 0.999) return '已完成'
  return `${(p * 100).toFixed(1)}%`
}
export function silentHrText(it) {
  const rem = it?.remain_min
  if (rem === null || rem === undefined) return it?.hr ? 'H&R 中' : ''
  return `剩 ${formatRemain(rem)}`
}
export function silentSubLabel(sub) { return SILENT_SUB_LABEL[String(sub || '')] || `静默-${sub || '?'}` }
