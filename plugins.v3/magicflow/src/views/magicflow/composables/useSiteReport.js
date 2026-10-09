// MagicFlow 前端 · useSiteReport 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// P4：展示用纯函数（siteReportBucketColor / siteReportItemSub / siteReportTransportCount）
//     提为**具名导出**，供 components/dialogs/SiteReportDialog.vue 直接 import 复用
//     （单一真值源，不复制）。
// 依赖注入：api, error（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'
import { SITE_REPORT_BUCKETS } from '../constants'

export function siteReportBucketColor(b) {
  const hit = SITE_REPORT_BUCKETS.find(x => x.key === b)
  return hit ? hit.color : 'grey'
}

// 明细副标题 = 列字段：传输 / 身份子桶 / qB 状态 / 债务 / 账单（不再当桶）
export function siteReportItemSub(it) {
  const parts = []
  if (it.sub) parts.push(it.sub)
  if (it.origin) parts.push(it.origin)
  if (it.transport) parts.push(it.transport)
  if (it.state) parts.push(it.state)
  if (it.hr && it.hr.need_left) parts.push(`欠H&R 还需 ${it.hr.need_left}h`)
  if (it.bill && it.bill.state) parts.push(`账单 ${it.bill.state}${it.bill.rule ? '/' + it.bill.rule : ''}`)
  return parts.join(' · ')
}

// 传输三态计数：选中某桶时看该桶内三态（bucket_transport），否则看全局（by_transport）。
// P4：改为纯函数（summary / filter 作为入参），供弹窗组件复用。
export function siteReportTransportCount(trKey, summary, filter) {
  const s = summary || {}
  if (filter && (s.bucket_transport || {})[filter]) {
    return (s.bucket_transport[filter][trKey] || 0)
  }
  return (s.by_transport || {})[trKey] || 0
}

export function useSiteReport({ api, error }) {
  const siteReportOpen = ref(false)
  const siteReportSite = ref('')
  const siteReportLive = ref(false)
  const siteReportLoading = ref(false)
  const siteReport = ref({ site: {}, items: [], summary: {}, hr: {}, available_sites: [] })
  const siteReportSites = computed(() => (siteReport.value.available_sites || []))
  const siteReportFilter = ref('')
  const siteReportTransport = ref('')
  const siteReportSub = ref('')
  const siteReportOrigin = ref('')
  const siteReportItems = computed(() => {
    const all = siteReport.value.items || []
    return all.filter(it =>
      (!siteReportFilter.value || it.bucket === siteReportFilter.value) &&
      (!siteReportTransport.value || it.transport === siteReportTransport.value) &&
      (!siteReportSub.value || it.sub === siteReportSub.value) &&
      (!siteReportOrigin.value || it.origin === siteReportOrigin.value)
    )
  })
  const siteReportSummary = computed(() => siteReport.value.summary || {})
  function openSiteReport() { siteReportOpen.value = true; loadSiteReport() }
  async function loadSiteReport(liveOverride) {
    siteReportLoading.value = true
    try {
      const q = new URLSearchParams()
      if (siteReportSite.value) q.set('site', siteReportSite.value)
      if (liveOverride === true || (liveOverride === undefined && siteReportLive.value)) q.set('live', '1')
      const data = unwrapResponse(await api.poolstats.siteSeeds(q.toString())) || {}
      siteReport.value = data
      siteReportFilter.value = ''
      siteReportTransport.value = ''
      siteReportSub.value = ''
      siteReportOrigin.value = ''
      if (!siteReportSite.value && siteReportSites.value.length) {
        siteReportSite.value = siteReportSites.value[0].domain || siteReportSites.value[0].name || ''
        await loadSiteReport()
      }
    } catch (e) {
      error.value = `站点报表加载失败：${e}`
    } finally {
      siteReportLoading.value = false
    }
  }

  return {
    loadSiteReport,
    openSiteReport,
    siteReport,
    siteReportFilter,
    siteReportItems,
    siteReportLive,
    siteReportLoading,
    siteReportOpen,
    siteReportOrigin,
    siteReportSite,
    siteReportSites,
    siteReportSub,
    siteReportSummary,
    siteReportTransport,
  }
}
