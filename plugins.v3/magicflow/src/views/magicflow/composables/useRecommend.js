// MagicFlow 前端 · 「推荐（批量入库候选）」域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：推荐列表（/features/recommend）取数 → 排序 / 去重 / 可操作判定（recWorthShowing、recommendItems、
//      recommendActionable）、确认 / 忽略 / 打开弹窗（actRecommend、confirmRecommend、dismissRecommend、
//      openRecommend），以及 60s 低频谱刷新角标的定时器（随域自管生命周期）。
// 依赖注入：api、notify、error。★ 真值源仍然后端；本域只放推荐相关 UI 状态。
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useRecommend({ api, notify, error }) {
const recommendData = ref({ items: [], total: 0, recommended: 0, enabled: true })
const recommendOpen = ref(false)
const recommendActing = ref('')
let recommendTimer = null

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
      recommendData.value = unwrapResponse(await api.features.recommend()) || { items: [], total: 0 }
    } catch (err) {
      error.value = err?.message || String(err)
    }
  }

  async function actRecommend(hash, action, label) {
    if (!hash || recommendActing.value) return
    recommendActing.value = hash + action
    try {
      const data = unwrapResponse(await api.features.recommendAct(hash, action)) || {}
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
  onMounted(() => {
    recommendTimer = window.setInterval(loadRecommend, 60000)
  })
  onUnmounted(() => {
    if (recommendTimer) window.clearInterval(recommendTimer)
  })

  return {
    recommendData,
    recommendOpen,
    recommendActing,
    showAllRecs,
    recommendItems,
    hiddenRecCount,
    confirmedCount,
    pendingCount,
    recWorthShowing,
    recName,
    recommendActionable,
    loadRecommend,
    actRecommend,
    confirmRecommend,
    dismissRecommend,
    openRecommend,
  }
}
