// MagicFlow 前端 · 「推荐（批量入库候选）」域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：推荐列表（/features/recommend）取数 → 排序 / 去重 / 可操作判定（recAllItems、
//      recStatusCounts、recFailedItems、recommendActionable）、动作（确认 / 忽略 / 重新整理 /
//      订阅整季 / 退订整季）、打开弹窗，以及 60s 低频谱刷新角标的定时器（随域自管生命周期）。
// 依赖注入：api、notify、error。★ 真值源仍然后端；本域只放推荐相关 UI 状态。
import { startPolling, stopPolling } from '../../../polling'
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

// 后端 `_recommend_import` 失败时的原话（如「xxx.mkv 没有找到可整理的媒体文件」）。
// 只有失败会写进 import_result，成功时这里是文件名/路径 —— 所以不能「非空即失败」。
const REC_IMPORT_FAIL_RE = /没有找到可整理的媒体文件|无法自动整理|整理失败|未能识别|缺少保存路径|缺少资源标题|不在下载器/
export function recImportBroken(rec) {
  if (!rec) return false
  if (String(rec.status || '').toLowerCase() !== 'confirmed') return false
  const s = String(rec.import_result || '')
  return !!s && REC_IMPORT_FAIL_RE.test(s)
}

// ★ 19.12.91：整理失败还分**能不能救**。
//   「种不在下载器里」= 死账：文件早没了，点十次「重新整理」也只会弹十次「无法自动整理」。
//   判据优先用后端落的 `import_dead`（19.12.91 起失败也会落库）；
//   老数据没有这个字段，用 `files_n===0 && files_at` 兜底（探针查过、一个文件都没有）。
export function recImportDead(rec) {
  if (!rec || !recImportBroken(rec)) return false
  if (rec.import_dead === true) return true
  const s = String(rec.import_result || '')
  if (s.includes('不在下载器')) return true
  return Number(rec.files_at || 0) > 0 && Number(rec.files_n || 0) === 0
}

// 状态说明 → 人话（历史记录里全是「过期→转普通」这类开发术语，卡片上不该出现）
const REC_NOTE_HUMAN = {
  '过期→转普通': '超过待确认窗口没处理，已转普通种（文件还在）',
  '临时种到期→转普通': '临时种到期，已转普通种（文件还在）',
  '过期未确认→转普通': '过期未确认，已转普通种（文件还在）',
  '单集（非整季）→转普通': '单集，没当成整季推荐',
}
export function recNoteHuman(rec) {
  const n = String((rec && rec.note) || '').trim()
  if (!n) return ''
  return REC_NOTE_HUMAN[n] || n
}

// 体积：＜1G 一律写 MB（0.08G → 80 MB），碎片一眼能看出来
export function recSizeText(gb) {
  const v = Number(gb) || 0
  if (!v) return ''
  if (v < 1) return `${Math.round(v * 1024)} MB`
  if (v < 10) return `${v.toFixed(2)} GB`
  return `${v.toFixed(1)} GB`
}

export function useRecommend({ api, notify, error }) {
const recommendData = ref({ items: [], total: 0, recommended: 0, enabled: true })
const recommendOpen = ref(false)
const recommendActing = ref('')
let recommendTimer = null

  // ★ 19.12.90 移动端改版：列表不再有「显示全部候选」这个开关，改成按状态筛选
  //   （待确认 / 未达门槛 / 已入库 / 已忽略 / 已转普通）。所以只留一份「去重但不过滤」的全量，
  //   同季聚合规则不变（同一「作品+季」只留最靠前的一条，组内其它在行内可展开）。
  const recAllItems = computed(() => {
    const order = { recommended: 0, pending: 1, subscribed: 2, confirmed: 3, dismissed: 4, downgraded: 5, deleted: 6 }
    const items = [...(recommendData.value.items || [])]
    items.sort((a, b) => {
      const oa = order[a.status] ?? 9
      const ob = order[b.status] ?? 9
      if (oa !== ob) return oa - ob
      return (b.updated_at || 0) - (a.updated_at || 0)
    })
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

  // 对账用计数：必须按**原始条目**算（不做同季聚合），否则 506 这个总数对不上。
  // 实测口径 506 = 0 待确认 + 27 未达门槛 + 108 已入库 + 5 已忽略 + 366 已转普通。
  const recStatusCounts = computed(() => {
    const raw = recommendData.value.items || []
    const c = {
      recommended: 0, pending: 0, subscribed: 0, confirmed: 0,
      dismissed: 0, downgraded: 0, deleted: 0, total: raw.length,
    }
    for (const it of raw) {
      const st = String(it.status || '').toLowerCase()
      if (st in c) c[st] += 1
    }
    return c
  })

  // 「已入库」里其实躺着整理失败的：import_result 带错误原因（如「…没有找到可整理的媒体文件」）。
  // 这些行 chip 写着「已入库」= 骗人，单独拎出来要人看一眼。
  const recFailedItems = computed(() => (recommendData.value.items || []).filter(recImportBroken))

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
  // ★ 19.12.90：三个后端早就有、前端从没调过的动作，接出来。
  //   import     —— 重新整理（专治「已入库」却 import_result 报错的那几条）
  //   subscribe  —— 手工给「作品+季」加 MP 整季订阅（MP 去抓其余集），只手动触发，不自动
  //   unsubscribe—— 退订整季并复位为待核实（不动种子）
  function importRecommend(hash) {
    return actRecommend(hash, 'import', '重新整理')
  }
  function subscribeRecommend(hash) {
    return actRecommend(hash, 'subscribe', '订阅整季')
  }
  function unsubscribeRecommend(hash) {
    return actRecommend(hash, 'unsubscribe', '退订整季')
  }
  function openRecommend() {
    recommendOpen.value = true
    loadRecommend()
  }
  onMounted(() => {
    recommendTimer = startPolling(loadRecommend, 60000)
  })
  onUnmounted(() => {
    if (recommendTimer) stopPolling(recommendTimer)
  })

  return {
    recommendData,
    recommendOpen,
    recommendActing,
    recAllItems,
    recStatusCounts,
    recFailedItems,
    recommendActionable,
    loadRecommend,
    confirmRecommend,
    dismissRecommend,
    importRecommend,
    subscribeRecommend,
    unsubscribeRecommend,
    openRecommend,
  }
}
