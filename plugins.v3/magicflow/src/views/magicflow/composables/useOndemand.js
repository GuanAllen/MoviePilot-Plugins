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

/** ★ 19.11.0 候选主标题：**中文名优先**，取不到才退回站点原名（拼音/英文）。
 *  中文名来自站点副标题（`torrent_info.description`），后端 `tags.display_title` 切好。 */
export function odMainTitle(row) {
  return String(row?.cn_title || row?.title || '')
}

/** 候选别名（「粉红猪小妹」这类台的译名）—— 有就淡色跟在主标题后面。 */
export function odAltTitle(row) {
  return String(row?.cn_alt || '')
}

/** 候选副标题：规格串优先；没有规格串才给站点副标题原文。
 *  但站点副标题常与片名同串（「小猪佩奇 第七季」）或与原标题同串 —— 那两种都不显示，
 *  否则主标题下面再抄一遍同样的字，纯噪音。 */
export function odSubTitle(row) {
  const spec = String(row?.spec || '')
  if (spec) return spec
  const sub = String(row?.subtitle || '')
  const main = String(row?.cn_title || '')
  const raw = String(row?.title || '')
  if (!sub || sub === raw) return ''
  if (main && sub.startsWith(main)) return ''
  return sub
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

/** 阶段配色（点播清单用；★ 15.9.0：stage 枚举 downloading/settling/resource/gone）。 */
export function odStageColor(stage) {
  if (stage === 'downloading') return 'primary'
  if (stage === 'resource') return 'success'
  if (stage === 'settling') return 'info'
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

  // 勾选只存 enclosure（纯 UI 状态）：候选本身在后端池里，本层不缓存真值。
  // ★ 19.11.0 多选一并下载的 UI 态，声明在 runOndemand 之前（它换搜索结果时要清空）。
  const odPicked = ref([])
  const odBatchBusy = ref(false)

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
    odPicked.value = []          // ★ 19.11.0：换了一次搜索结果 → 旧勾选的 enclosure 已不在列表里
    try {
      const params = [`query=${encodeURIComponent(q)}`, `apply=${apply ? 'true' : 'false'}`]
      if (ondemandTaskId.value) params.push(`task_id=${encodeURIComponent(ondemandTaskId.value)}`)
      const _sites = (Array.isArray(ondemandSiteIds.value) ? ondemandSiteIds.value : []).map(String).filter(Boolean)
      if (_sites.length) params.push(`site_ids=${encodeURIComponent(_sites.join(','))}`)
      if (pick) params.push(`pick=${encodeURIComponent(pick)}`)
      // ★ 19.11.7：**这里不走 unwrapResponse**。「没认出片名 / 站点里没有匹配资源」后端
      //   返回 success=false，但 data.candidates 里带着站点粗筛结果 —— unwrapResponse 在
      //   success===false 时直接抛错，把 data 一起丢掉 → 用户只剩一句报错、一条候选也看不见
      //   （实测搜「欢迎来到龙餐馆」：20 条候选全被吞成空白）。所以自己分流：
      //     · data 里真有 candidates → 照常渲染（噪音行后端已标 rel=0，列表灰显/打标）
      //     · 失败原因保留后端原文 → 用户知道「为什么没自动选源、该自己挑哪条」
      //   cand_expired / 下载失败这两类 data 没有候选，只显示原因，不动已有列表。
      const raw = await api.features.ondemandSearch(params.join('&'))
      const data = raw?.data && typeof raw.data === 'object' ? raw.data : null
      if (data && Array.isArray(data.candidates)) ondemandResult.value = data
      else if (data && raw?.success !== false) ondemandResult.value = data
      if (raw?.success === false) ondemandError.value = String(raw?.message || '操作失败')
      if (apply) loadOndemandItems()   // ★ 15.4.0：下完马上刷新清单（进度/历史可见）
    } catch (err) {
      ondemandError.value = err?.message || String(err)
    } finally {
      ondemandBusy.value = ''
    }
  }

  // ── 多选一并下载（★ 19.11.0）──────────────────────────────────────
  function isOdPicked(row) {
    const u = String(row?.enclosure || '')
    return !!u && odPicked.value.includes(u)
  }
  function toggleOdPick(row) {
    const u = String(row?.enclosure || '')
    if (!u) return
    const i = odPicked.value.indexOf(u)
    if (i >= 0) odPicked.value.splice(i, 1)
    else odPicked.value.push(u)
  }
  function pickAllOndemand(on) {
    const all = (ondemandCandidates.value || []).map((r) => String(r?.enclosure || '')).filter(Boolean)
    odPicked.value = on ? Array.from(new Set(all)) : []
  }
  async function runOndemandBatch() {
    const picks = odPicked.value.slice()
    if (!picks.length) {
      ondemandError.value = '请先勾选要下载的候选'
      return
    }
    odBatchBusy.value = true
    ondemandError.value = ''
    odMsg.value = ''
    try {
      const params = [`picks=${encodeURIComponent(picks.join('\n'))}`]
      if (ondemandTaskId.value) params.push(`task_id=${encodeURIComponent(ondemandTaskId.value)}`)
      // 不走 unwrapResponse：全失败时 success=false 会抛错并丢掉 data.fail 明细，
      // 而「哪几条没下成、为什么」正是批量最该说清楚的部分。
      const raw = await api.features.ondemandBatch(params.join('&'))
      const data = raw?.data || {}
      const fails = Array.isArray(data.fail) ? data.fail : []
      const head = raw?.success === false ? '❌ ' : ''
      let text = head + String(raw?.message || '已提交')
      if (fails.length) {
        text += `\n· ${fails.slice(0, 3).map((f) => `${f.title || '（无标题）'}：${f.message || '失败'}`).join('\n· ')}`
      }
      odMsg.value = text
      if (data.ok_count) {
        odPicked.value = []
        loadOndemandItems()
      }
    } catch (err) {
      odMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      odBatchBusy.value = false
    }
  }

  // ★ 15.4.0：点播清单。★ 15.9.0 后端换皮为「单列表 items[]（进行中+历史同构）」；
  //   真值源：后端 ondemand_pending × qB 快照 + journal；此处按 stage 派生两个 Tab。
  const ondemandItems = ref({ items: [], totals: {} })
  const ondemandItemsBusy = ref(false)
  let ondemandItemsTimer = null
  const _odItems = computed(() => (Array.isArray(ondemandItems.value?.items) ? ondemandItems.value.items : []))
  const odInflight = computed(() => _odItems.value.filter(
    (r) => r && (r.stage === 'downloading' || r.stage === 'settling')))
  const odHistory = computed(() => _odItems.value.filter(
    (r) => r && (r.stage === 'resource' || r.stage === 'gone')))

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
      if (!confirm(`确认移除「${_t}」？\n\n· 从下载器删除该种 + 文件\n· 欠 H&R / 受保护的种会被拦下`)) return
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
    odMainTitle, odAltTitle, odSubTitle,
    odPicked, odBatchBusy, isOdPicked, toggleOdPick, pickAllOndemand, runOndemandBatch,
  }
}
