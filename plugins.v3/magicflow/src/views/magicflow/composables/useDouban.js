// MagicFlow 前端 · 豆瓣评分服务域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：豆瓣评分服务弹窗状态 + 拉取 + 抓取动作（start/pause/...）。
// 依赖注入：api（createApi 客户端）。★ 真值源仍在后端（/douban_service）。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useDouban({ api }) {
  // ── 豆瓣评分服务（magicflow-douban · 3.23.1）─────────────────────────
  const doubanServiceOpen = ref(false)
  const doubanServiceActing = ref('')
  const doubanServiceData = ref({ ok: false, records: 0, cache: {}, crawl: {} })
  const doubanCrawl = computed(() => (doubanServiceData.value || {}).crawl || {})
  const doubanCrawlProgress = computed(() => {
    const c = doubanCrawl.value
    const total = Number(c.spec_total || 0)
    const idx = Number(c.spec_index || 0)
    if (!total) return 0
    return Math.min(100, Math.round((idx / total) * 100))
  })

  async function loadDoubanService() {
    try {
      doubanServiceData.value = unwrapResponse(await api.features.doubanService())
        || { ok: false, records: 0, cache: {}, crawl: {} }
    } catch (err) {
      // 豆瓣服务是增强信息，失败不打断界面
    }
  }

  function openDoubanService() {
    doubanServiceOpen.value = true
    loadDoubanService()
  }

  async function doubanCrawlAction(action) {
    doubanServiceActing.value = action
    try {
      const res = unwrapResponse(await api.features.doubanAction(action))
      if (res) doubanServiceData.value = res
    } catch (err) {
      // 静默
    } finally {
      doubanServiceActing.value = ''
    }
  }

  return {
    doubanServiceOpen, doubanServiceActing, doubanServiceData, doubanCrawl, doubanCrawlProgress,
    loadDoubanService, openDoubanService, doubanCrawlAction,
  }
}
