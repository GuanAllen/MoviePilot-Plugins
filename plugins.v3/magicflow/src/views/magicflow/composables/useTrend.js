// MagicFlow 前端 · 魔力趋势 + 归因（★ 15.12.0）
// Master：「你觉得魔流还需要什么功能」→「全部」→ 批次①：时魔走向要能看、掉了要知道为什么。
import { computed, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useTrend({ api, notify, itemsOf }) {
  const trendOpen = ref(false)
  const trendScope = ref('site')
  const trendId = ref('')
  const trendHours = ref(72)
  const trendLoading = ref(false)
  const trendWhy = ref(null)
  const trendDaily = ref([])

  const trendScopeItems = computed(() => (typeof itemsOf === 'function' ? itemsOf(trendScope.value) : []))

  async function loadTrendReport() {
    const scope = trendScope.value
    const ident = String(trendId.value || '')
    if (!ident) {
      trendWhy.value = null
      trendDaily.value = []
      return
    }
    trendLoading.value = true
    try {
      const [whyResp, dayResp] = await Promise.all([
        api.trend.why({ scope, id: ident, hours: trendHours.value }),
        api.trend.daily({ scope, id: ident, days: 30 }),
      ])
      const w = unwrapResponse(whyResp) || {}
      trendWhy.value = w
      const d = unwrapResponse(dayResp) || {}
      const seriesMap = d.series || {}
      trendDaily.value = seriesMap[`${scope}:${ident}`] || []
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '趋势读取失败', 'error')
      trendWhy.value = null
      trendDaily.value = []
    } finally {
      trendLoading.value = false
    }
  }

  /**
   * 打开弹窗（可选指定对象）。
   * 兜底：指定的那条序列**没有小时采样点**时，自动落到「同口径里点最多」的一条
   * （站点监控每轮采样 → 站点口径基本都有点；任务口径要看任务跑没跑）。
   */
  async function openTrend(opts = {}) {
    trendOpen.value = true
    trendScope.value = opts.scope === 'task' ? 'task' : 'site'
    let ident = String(opts.id || '')
    if (!ident) {
      const list = trendScopeItems.value
      ident = list.length ? String(list[0].value) : ''
    }
    try {
      const resp = await api.trend.hours({ scope: 'all', hours: trendHours.value })
      const series = (unwrapResponse(resp) || {}).series || {}
      const keys = Object.keys(series)
      if (keys.length && !keys.includes(`${trendScope.value}:${ident}`)) {
        const pool = keys.filter(k => k.startsWith(`${trendScope.value}:`))
        pool.sort((a, b) => ((series[b] || []).length - (series[a] || []).length))
        if (pool.length) {
          const parts = pool[0].split(':')
          trendScope.value = parts[0]
          ident = parts.slice(1).join(':')
        }
      }
    } catch (err) {
      // 拿不到序列清单就按用户给的原样看
    }
    trendId.value = ident
    loadTrendReport()
  }

  watch([trendScope, trendId, trendHours], () => {
    if (trendOpen.value) loadTrendReport()
  })

  return {
    trendOpen, trendScope, trendId, trendHours, trendLoading, trendWhy, trendDaily,
    trendScopeItems, loadTrendReport, openTrend,
  }
}
