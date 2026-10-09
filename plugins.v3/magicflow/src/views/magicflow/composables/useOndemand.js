// MagicFlow 前端 · 点播域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：点播弹窗状态 + 搜索（干跑 / 落地）+ 在途清单轮询 + 行内操作 + 展示格式化。
// 依赖注入：api（createApi 客户端）。★ 真值源仍在后端（/ondemand、/ondemand/items），
// 本层只持有 UI 状态，不缓存真值。
import { computed, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

// ── 展示用纯函数（无状态）→ module 级具名导出：OndemandDialog.vue 直接复用，单一真值源。
//    仍保留在下方 useOndemand 的 return 里（index.vue 解构不变 → 护栏⑥ 解构↔return 逐字一致）。

/** 大小文案（GB）。 */
export function fmtSizeGb(bytes) {
  const v = Number(bytes || 0) / (1024 * 1024 * 1024)
  return v ? `${v.toFixed(2)} GB` : '—'
}

/** 点播候选的流量标识：dv=下载因子（0=免费，0<dv<1=折扣，1=全额计入）。 */
export function odTraffic(dv) {
  const v = Number(dv ?? 1)
  if (!Number.isFinite(v) || v >= 1) return { text: '计流量', color: '' }
  if (v <= 0) return { text: '免费', color: 'success' }
  return { text: `流量 ×${Math.round(v * 100)}%`, color: 'warning' }
}

/** 进度百分比（0–100）。 */
export function odPct(row) {
  return Math.max(0, Math.min(100, Number(row?.progress || 0) * 100))
}

/** 速度文案（B/s → KB/s / MB/s）。 */
export function odSpeed(bps) {
  const v = Number(bps || 0)
  if (!v) return ''
  if (v >= 1024 * 1024) return `${(v / 1024 / 1024).toFixed(1)} MB/s`
  if (v >= 1024) return `${(v / 1024).toFixed(0)} KB/s`
  return `${v.toFixed(0)} B/s`
}

/** 剩余时间文案。 */
export function odEtaText(sec) {
  const s = Number(sec || 0)
  if (!s || s <= 0) return ''
  if (s < 60) return `剩 ${Math.round(s)} 秒`
  if (s < 3600) return `剩 ${Math.round(s / 60)} 分`
  return `剩 ${(s / 3600).toFixed(1)} 小时`
}

/** 阶段配色（点播清单用）。 */
export function odStageColor(stage) {
  if (stage === 'downloading') return 'primary'
  if (stage === 'resource') return 'success'
  if (stage === 'pending_settle') return 'info'
  return 'warning'   // gone
}

/** 是否暂停态（暂停 / 停止）。 */
export function odIsPaused(row) {
  const s = String(row?.state || '')
  return s === 'pausedUP' || s === 'pausedDL' || s === 'stoppedUP' || s === 'stoppedDL' || s === 'paused'
}

export function useOndemand(api) {
  // ── 点播（§1 权威来源 1 · 7.1.0）────────────────────────────────────
  const ondemandOpen = ref(false)
  const ondemandQuery = ref('')
  const ondemandTaskId = ref('')
  // ★ 站点多选（勾选框）：不勾 = 全部站点；勾了就只搜勾中的（点播不再依赖任务）
  const ondemandSiteIds = ref([])
  const ondemandBusy = ref('')
  const ondemandResult = ref(null)
  const ondemandError = ref('')
  const ondemandCandidates = computed(() => {
    const rows = ondemandResult.value?.candidates
    return Array.isArray(rows) ? rows : []
  })

  function openOndemand() {
    ondemandOpen.value = true
    ondemandResult.value = null
    ondemandError.value = ''
    loadOndemandItems()
  }

  // fmtSizeGb / odTraffic / odPct / odSpeed / odEtaText / odStageColor / odIsPaused
  //   → 已上提为 module 级具名导出（见文件顶部）；本域只留依赖状态的 isOndemandAuto。
  function isOndemandAuto(row) {
    return !!row?.enclosure && row.enclosure === ondemandResult.value?.auto_pick
  }

  async function runOndemand(apply, pick = '') {
    const q = String(ondemandQuery.value || '').trim()
    if (!q) {
      ondemandError.value = '请输入片名或豆瓣/TMDB/IMDB 链接'
      return
    }
    ondemandBusy.value = apply ? 'apply' : 'preview'
    ondemandError.value = ''
    try {
      const params = [`query=${encodeURIComponent(q)}`, `apply=${apply ? 'true' : 'false'}`]
      if (ondemandTaskId.value) params.push(`task_id=${encodeURIComponent(ondemandTaskId.value)}`)
      const _sites = (Array.isArray(ondemandSiteIds.value) ? ondemandSiteIds.value : []).map(String).filter(Boolean)
      if (_sites.length) params.push(`site_ids=${encodeURIComponent(_sites.join(','))}`)
      if (pick) params.push(`pick=${encodeURIComponent(pick)}`)
      const res = unwrapResponse(await api.features.ondemandSearch(params.join('&')))
      if (res) ondemandResult.value = res
      if (apply) loadOndemandItems()   // ★ 15.4.0：下完马上刷新清单（进度/历史可见）
    } catch (err) {
      ondemandError.value = err?.message || String(err)
    } finally {
      ondemandBusy.value = ''
    }
  }

  // ★ 15.4.0：点播清单（进行中带进度 + 历史）。真值源：后端 ondemand_pending × qB 快照 + journal。
  const ondemandItems = ref({ inflight: [], history: [], totals: {} })
  const ondemandItemsBusy = ref(false)
  let ondemandItemsTimer = null
  const odInflight = computed(() => (Array.isArray(ondemandItems.value?.inflight) ? ondemandItems.value.inflight : []))
  const odHistory = computed(() => (Array.isArray(ondemandItems.value?.history) ? ondemandItems.value.history : []))

  async function loadOndemandItems() {
    ondemandItemsBusy.value = true
    try {
      const res = unwrapResponse(await api.features.ondemandItems())
      if (res) ondemandItems.value = res
    } catch (err) {
      // 清单是增强信息，失败不打断搜索/下载主流程
    } finally {
      ondemandItemsBusy.value = false
    }
  }
  function startOndemandItemsPolling() {
    stopOndemandItemsPolling()
    ondemandItemsTimer = window.setInterval(loadOndemandItems, 10000)
  }
  function stopOndemandItemsPolling() {
    if (ondemandItemsTimer) {
      window.clearInterval(ondemandItemsTimer)
      ondemandItemsTimer = null
    }
  }
  watch(ondemandOpen, (v) => {
    if (v) {
      loadOndemandItems()
      startOndemandItemsPolling()
    } else {
      stopOndemandItemsPolling()
    }
  })

  // ★ 15.5.0：筛选（进行中 / 已完成）+ 行内操作（暂停 / 继续 / 移除）
  const ondemandTab = ref('inflight')   // 'inflight' | 'done'
  const odActing = ref('')
  const odMsg = ref('')
  async function actOndemand(row, action) {
    const h = String(row?.hash || '')
    if (!h) return
    if (action === 'remove') {
      const _t = row?.title || h.slice(0, 12)
      if (!confirm(`确认移除「${_t}」？\n\n· 从下载器删除该种 + 文件\n· 欠 H&R / 受保护的种会被闸门拦下`)) return
    }
    odMsg.value = ''
    odActing.value = `${h}:${action}`
    try {
      const res = unwrapResponse(await api.features.ondemandAct(h, action))
      odMsg.value = res?.message || '已执行'
    } catch (err) {
      odMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      odActing.value = ''
      loadOndemandItems()
    }
  }

  return {
    ondemandOpen, ondemandQuery, ondemandTaskId, ondemandSiteIds, ondemandBusy,
    ondemandResult, ondemandError, ondemandCandidates,
    ondemandItems, ondemandItemsBusy, ondemandTab, odInflight, odHistory, odActing, odMsg,
    openOndemand, runOndemand, loadOndemandItems, actOndemand,
    odTraffic, odPct, odSpeed, odEtaText, odStageColor, odIsPaused, isOndemandAuto, fmtSizeGb,
  }
}
