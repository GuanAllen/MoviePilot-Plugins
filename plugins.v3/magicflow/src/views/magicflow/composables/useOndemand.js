// MagicFlow 前端 · 点播域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：点播弹窗状态 + 搜索（干跑 / 落地）+ 在途清单轮询 + 行内操作 + 展示格式化。
// 依赖注入：api（createApi 客户端）。★ 真值源仍在后端（/ondemand、/ondemand/items），
// 本层只持有 UI 状态，不缓存真值。
import { startPolling, stopPolling } from '../../../polling'
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

// ── 发布名解析（★ 19.16.4）──────────────────────────────────────────────
// 站点把中文名写在副标题里时，后端 `tags.display_title` 已切好 cn_title / spec；
// 但「高清杜比」这类站只给英文发布名 —— `Fights Break Sphere 2025 S08 Complete
// 1080p WEB-DL HEVC DDP 3Audios-GROUP` 整串被两行 clamp 截在同一位置，两条候选
// 看上去一模一样（主人 2026-11-21：「搜出这样的内容我甚至不知道我下的是什么」）。
// 这里把发布名**按规则切词**成 季/集 + 分辨率/片源/编码/音轨：只拆不译、不猜片名。
const _OD_RES_RE = /\b(2160p|1080[pi]|720p|480p|4k|8k)\b/i
const _OD_SRC_RE = /\b(web[-._ ]?dl|webrip|blu[-._ ]?ray|bdrip|remux|hdtv|dvdrip)\b/i
const _OD_VID_RE = /\b(hevc|h\.?26[45]|x26[45]|avc|av1)\b/i
// 音轨要吃掉三种写法：`DDP 3Audios`（音轨数）/ `DDP5.1`（声道紧贴）/ `DTS-HD.MA.5.1`（MA 夹在中间）
const _OD_AUD_RE = /\b(dd\+|ddp|dd|eac3|ac3|dts(?:[-._ ]?hd)?(?:[-._ ]?ma)?|truehd|atmos|flac|aac|opus)(?![a-z])(?:[-._ ]?(\d{1,2}(?:\.\d)?))?[-._ ]?(audios?)?/i
const _OD_SE_RE = /\bS(\d{1,2})(?:[ ]?E(\d{1,3})(?:[ ]?-[ ]?E?(\d{1,3}))?)?\b/i
// 「像规格」的判据：清单行 subtitle 里的站点噪音（[热门]xx / 剩余时间：xx）据此挡掉
const _OD_SPECISH_RE = /(\d{3,4}[pi]\b|全\s*\d+\s*集|第\s*\d+\s*[-–~]?\s*\d*\s*集|国语|粤语|双语|多音轨|简中|繁中|中字|字幕|hdr|hevc|web-?dl|blu-?ray|remux|季)/i
const _OD_EP_RE = /\bEP?(\d{1,3})(?:[ ]?-[ ]?E?P?(\d{1,3}))?\b/i
// 中文名里已经写了「第九季 / 第 8 集」时，别在后面再补一遍
const _OD_ZH_SEASON_RE = /第\s*[0-9零一二三四五六七八九十百]+\s*[季集期]/

const _OD_SRC_LABEL = {
  webdl: 'WEB-DL', webrip: 'WEBRip', bluray: 'BluRay', bdrip: 'BDRip',
  remux: 'REMUX', hdtv: 'HDTV', dvdrip: 'DVDRip',
}
const _OD_VID_LABEL = {
  hevc: 'HEVC', h265: 'H.265', x265: 'x265', avc: 'AVC', h264: 'H.264', x264: 'x264', av1: 'AV1',
}
const _OD_AUD_LABEL = {
  'dd+': 'DD+', ddp: 'DDP', dd: 'DD', eac3: 'E-AC3', ac3: 'AC3', dts: 'DTS',
  dtshd: 'DTS-HD', dtshdma: 'DTS-HD MA', truehd: 'TrueHD', atmos: 'Atmos',
  flac: 'FLAC', aac: 'AAC', opus: 'OPUS',
}

function _odAudioLabel(codec, num, unit) {
  const key = String(codec || '').toLowerCase().replace(/[-._ ]/g, '')
  const head = _OD_AUD_LABEL[key] || String(codec || '').toUpperCase()
  const n = String(num || '').trim()
  if (!n) return head
  // 「DDP 3Audios」的 3 是**音轨数**；「DDP5.1」的 5.1 是声道 —— 两者显示不一样
  return unit ? `${head} ${n} 音轨` : `${head} ${n}`
}

/** 发布名 → 结构化片段（纯规则切词；切不出来就留空，调用方各自回退）。 */
export function odRelease(title) {
  const raw = String(title || '').trim()
  const out = { name: raw, season: '', pack: '', res: '', src: '', vid: '', aud: '' }
  if (!raw) return out
  const mRes = raw.match(_OD_RES_RE)
  if (mRes) out.res = /^(4k|8k)$/i.test(mRes[1]) ? mRes[1].toUpperCase() : mRes[1].toLowerCase()
  const mSrc = raw.match(_OD_SRC_RE)
  if (mSrc) out.src = _OD_SRC_LABEL[String(mSrc[1]).toLowerCase().replace(/[-._ ]/g, '')] || mSrc[1].toUpperCase()
  const mVid = raw.match(_OD_VID_RE)
  if (mVid) out.vid = _OD_VID_LABEL[String(mVid[1]).toLowerCase().replace(/\./g, '')] || mVid[1].toUpperCase()
  const mAud = raw.match(_OD_AUD_RE)
  if (mAud) out.aud = _odAudioLabel(mAud[1], mAud[2], mAud[3])
  const mSe = raw.match(_OD_SE_RE)
  if (mSe) {
    out.season = `第 ${Number(mSe[1])} 季`
    if (mSe[3]) out.pack = `${Number(mSe[2])}-${Number(mSe[3])} 集`
    else if (mSe[2]) out.pack = `第 ${Number(mSe[2])} 集`
  } else {
    const mEp = raw.match(_OD_EP_RE)
    if (mEp) out.pack = mEp[2] ? `${Number(mEp[1])}-${Number(mEp[2])} 集` : `第 ${Number(mEp[1])} 集`
  }
  if (/\bcomplete\b|全集|合集|全\s?\d+\s?集|已完结/i.test(raw)) out.pack = '全集'
  // 片名段 = 第一个版本词之前那截（去掉尾部分隔符与开头的【站名/画质】标记）
  let cut = raw.length
  for (const re of [_OD_RES_RE, _OD_SRC_RE, _OD_VID_RE, _OD_AUD_RE, _OD_SE_RE, _OD_EP_RE]) {
    const m = raw.match(re)
    if (m && m.index < cut) cut = m.index
  }
  out.name = raw.slice(0, cut)
    .replace(/^[【\[][^】\]]{1,10}[】\]]\s*/, '')
    .replace(/[\s._\-–—|]+$/, '')
    .trim()
  return out
}

/** ★ 候选主标题：**能读的片名 + 季集**。
 *
 *  优先级：站点中文名（`cn_title`）→ 本次搜索识别到的片名（`ctxTitle`，整批候选同属一部片）
 *  → 发布名里的片名段。`rel === 0` 是后端标定的「名称未匹配」，那种行绝不套用识别名。
 *  季/集跟在后面：同一次搜索里 1080p / 2160p 两行主标题相同，靠规格行区分，
 *  但「第 8 季」和「第 7 季」必须在这一行就看出来。 */
/** 候选/清单主标题：**中文名优先**，取不到才退回发布名里的片名段。
 *  ★ 19.16.5：清单行后端新增 `cn_title`（识别/站点给的中文名）与 `en_title`（发布名）——
 *  展示用中文名，**季集从发布名抽**（中文名不带「第 8 季」，同剧十季会看起来一模一样）。 */
export function odMainTitle(row, ctxTitle = '') {
  const raw = String(row?.en_title || row?.title || '')
  const cn = String(row?.cn_title || '')
  const p = odRelease(raw)
  let base = cn
  if (!base && ctxTitle && Number(row?.rel || 0) !== 0) base = String(ctxTitle)
  if (!base) base = p.name || raw
  const tail = []
  if (p.season && !_OD_ZH_SEASON_RE.test(base)) tail.push(p.season)
  if (p.pack && !base.includes(p.pack)) tail.push(p.pack)
  return tail.length ? `${base} · ${tail.join(' · ')}` : base
}

/** 候选别名（「粉红猪小妹」这类台的译名）—— 有就淡色跟在主标题后面。 */
export function odAltTitle(row) {
  return String(row?.cn_alt || '')
}

/** 候选副标题（= 一眼看清是什么版本的那行）：站点中文规格串优先，
 *  没有就把发布名里的「分辨率 · 片源 · 编码 · 音轨」拼出来。
 *  两者都没有才退回站点副标题原文（与原名同串 / 与中文名重复的一律不显示）。 */
export function odSubTitle(row) {
  const spec = String(row?.spec || '')
  if (spec) return spec
  const raw = String(row?.en_title || row?.title || '')
  const p = odRelease(raw)
  const bits = [p.res, p.src, p.vid, p.aud].filter(Boolean)
  if (bits.length) {
    // `TrueHD.7.1.Atmos` 这类并列写法：Atmos 跟在音轨后面，别漏
    if (/\batmos\b/i.test(raw) && !/atmos/i.test(p.aud)) bits.push('Atmos')
    return bits.join(' · ')
  }
  const sub = String(row?.subtitle || '')
  if (!sub || sub === raw) return ''
  const main = String(row?.cn_title || '')
  if (main && sub.startsWith(main)) return ''
  // ★ 19.16.5：清单行的 subtitle 常是站点噪音（「[热门]欢迎来龙餐馆」「剩余时间：…」），
  //   只有真的像规格（分辨率/集数/语言/字幕）才拿来当副标题
  if (!_OD_SPECISH_RE.test(sub)) return ''
  return sub
}

/** 候选/清单「原名」：主标题已经就是这串时不再抄一遍。 */
export function odRawTitle(row, ctxTitle = '') {
  const raw = String(row?.en_title || row?.title || '')
  if (!raw) return ''
  return raw === odMainTitle(row, ctxTitle) ? '' : raw
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
      // ★ 19.16.5：刷到「只有英文发布名」的行就顺带让后端补中文名（90s 节流，不会打爆识别链）
      retitleOndemandItems()
    }
  }
  // ★ 19.16.5：清单里还剩「只有英文发布名」的行 → 让后端后台补中文名（每条 1~3s）。
  //   90s 节流：弹窗每次打开都会刷清单，别把识别当轮询；每轮 6 条、最多 6 轮（≈36 条）。
  let _odRetitleAt = 0
  let _odRetitleRounds = 0
  function retitleOndemandItems(force = false) {
    const now = Date.now()
    if (!force && now - _odRetitleAt < 90000) return
    const need = (_odItems.value || []).some((r) => {
      const t = String(r?.en_title || r?.title || '')
      return !String(r?.cn_title || '') && !!t && /[a-z]/i.test(t) && !/[\u3400-\u9fff]/.test(t)
    })
    if (!need) return
    _odRetitleAt = now
    api.features.ondemandRetitle(6).then((raw) => {
      if (!(raw?.data || {}).started) return
      _odRetitleRounds += 1
      // 后台补一条落一条 → 20s 后刷新；仍缺就再来一轮
      setTimeout(() => {
        loadOndemandItems().then(() => {
          if (_odRetitleRounds < 6) retitleOndemandItems(true)
        })
      }, 20000)
    }).catch(() => { /* 补中文名是增强，失败不打扰 */ })
  }
  function startOndemandItemsPolling() {
    ondemandItemsTimer = startPolling(loadOndemandItems, 10000)
  }
  function stopOndemandItemsPolling() {
    if (ondemandItemsTimer) {
      stopPolling(ondemandItemsTimer)
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
    openOndemand, runOndemand, loadOndemandItems, actOndemand, retitleOndemandItems,
    odTraffic, odPct, odSpeed, odEtaText, odStageColor, odIsPaused, isOndemandAuto, fmtSizeGb,
    odMainTitle, odAltTitle, odSubTitle, odRawTitle, odRelease,
    odPicked, odBatchBusy, isOdPicked, toggleOdPick, pickAllOndemand, runOndemandBatch,
  }
}
