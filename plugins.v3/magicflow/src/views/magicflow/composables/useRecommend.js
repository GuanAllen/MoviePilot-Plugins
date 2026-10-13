// MagicFlow 前端 · 「推荐（批量入库候选）」域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：推荐列表（/features/recommend）取数 → 排序 / 去重 / 可操作判定（recWorthShowing、recommendItems、
//      recommendActionable）、确认 / 忽略 / 打开弹窗（actRecommend、confirmRecommend、dismissRecommend、
//      openRecommend），以及 60s 低频谱刷新角标的定时器（随域自管生命周期）。
// 依赖注入：api、notify、error。★ 真值源仍然后端；本域只放推荐相关 UI 状态。
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

// 展示名：优先「媒体标题 (年份)」；不显示原始下载文件名（文件名只进 tooltip 属性）。
// （具名导出：RecommendDialog 直接复用，单一真值源。）
export function recName(rec) {
  if (!rec) return ''
  const m = rec.media || {}
  const t = m.title || ''
  if (t) return m.year ? `${t} (${m.year})` : t
  return rec.title || rec.hash || ''
}

// ★ 15.8.21：季 / 集 展示（单一真值源，RecommendDialog 具名复用）
// 分组键：同「作品+季」归一组；老记录无 group_key 时回退 media_key / hash。
export function recGroupKey(rec) {
  if (!rec) return ''
  return rec.group_key || rec.media_key || rec.hash || ''
}

export function recSeasonLabel(rec) {
  const s = String((rec && rec.season) || '').trim()
  if (!s) return ''
  const m = s.match(/(\d{1,3})/)
  return m ? `第 ${parseInt(m[1], 10)} 季` : s
}

export function recEpisodeLabel(rec) {
  if (!rec) return ''
  const kind = String(rec.kind || '')
  const b = Number(rec.ep_begin) || 0
  const e = Number(rec.ep_end) || 0
  if (kind === 'multi') return (b && e) ? `全 ${b}-${e} 集` : '多集'
  if (kind === 'single') {
    if (b) return `第 ${b} 集`
    const m = String(rec.episode || '').match(/(\d{1,3})/)
    return m ? `第 ${parseInt(m[1], 10)} 集` : '单集'
  }
  // ★ 15.8.22：种名只到「季」。有把握才说「整季」：发布名带 Complete/全集/完结，
  //   或体积大到不可能是单集（≥15G）；否则老实写「集数未知」。
  if (kind === 'season') {
    const title = String(rec.title || '')
    const size = Number(rec.size_gb) || 0
    if (/complete|全集|完结|全\s*\d+\s*集/i.test(title)) return '整季'
    if (size >= 15) return '整季'
    return '集数未知'
  }
  return ''
}

// 是否「单集」（season_first 策略下不会自动推荐的那种）
export function recIsSingle(rec) {
  return String((rec && rec.kind) || '') === 'single'
}

// 同组（作品+季）的全部记录：用于「同季其它 N 条」聚合展开
export function recGroupMembers(all, rec) {
  const key = recGroupKey(rec)
  if (!key || !Array.isArray(all)) return []
  return all.filter((it) => recGroupKey(it) === key)
}

// 可手动确认的行：命中推荐（待确认），或「待核实」里非「已在库 / 重复」的临时种。
// （具名导出：RecommendDialog 直接复用，单一真值源。）
export function recommendActionable(rec) {
  if (!rec) return false
  const st = String(rec.status || '').toLowerCase()
  if (st === 'recommended') return true
  if (st === 'pending') {
    const r = String(rec.reason || '')
    return !r.includes('已在影视库') && !r.includes('重复推荐')
  }
  return false
}

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
    // 同一「作品+季」（group_key）只保留最靠前的一条（★ 15.8.21：聚合到季，
    // 同片不同季分开显示；组内其它条目在行内可展开）
    const seen = new Set()
    const out = []
    for (const it of items) {
      const k = recGroupKey(it)
      if (k && seen.has(k)) continue
      if (k) seen.add(k)
      out.push(it)
    }
    return out
  })
  const hiddenRecCount = computed(() => (recommendData.value.items || []).filter(i => !recWorthShowing(i)).length)
  const confirmedCount = computed(() => (recommendData.value.items || []).filter(i => i.status === 'confirmed').length)
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
