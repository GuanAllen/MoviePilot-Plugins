// MagicFlow 前端 · useMusic 域 composable
// ★ 2026-10-10（批2）：音乐线改为「清单」视图 —— 与点播同构（单列表 + 行内操作）。
//   Master 口径：「清单做，跟点播一样，不要歌单了（塞不下）」。
//   真值源仍在后端（GET /agent/music/items、POST /agent/music/act）；本层只放 UI 状态与动作。
// ★ 19.12.87（移动端改版）：
//   1. 批量下载：候选勾选 → 一次 `cids=a,b,c`（后端本来就吃逗号分隔，不用改端点）；
//   2. 清单分页：后端回 total（截断前真实条数）+ offset，本层做「加载更多」；
//   3. 已完成按「要不要我动手」分组（入库失败 / 待入库 / 已入库 / 种子已不在）。
import { startPolling, stopPolling } from '../../../polling'
import { computed, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

//: 一页条数（后端 cap 最大 200）
const MUSIC_PAGE = 50
//: 搜索后默认勾几首（最相关且未过滤的），用户可自行改
const MUSIC_AUTO_PICK = 1

export function useMusic({ api }) {
  const musicOpen = ref(false)
  const musicItems = ref({ items: [], totals: {}, total: 0 })
  const musicItemsBusy = ref(false)
  const musicTab = ref('inflight')   // 兼容旧绑定；19.12.87 起清单改为纵向分段，chip 不再渲染
  const musicActing = ref('')        // `${hash}:${action}`
  const musicImporting = ref('')     // 正在提交入库的 hash
  const musicMsg = ref('')
  let musicTimer = null

  // ── 单搜 + 批量下 ────────────────────────────────────────────
  // ★ Master 2026-10-10 14:55：「不是所有人都有 AI 助手」——UI 也得能搜 + 下。
  //   走的就是 AI 入口那组端点（/agent/music/search → /agent/music/download），单一真值源。
  const musicQuery = ref('')
  const musicSiteIds = ref([])
  const musicSearching = ref(false)
  const musicResult = ref(null)      // {keyword, sites, sources[], candidates[], total_items}
  const musicDownloading = ref('')   // 正在下载的 cid（单条兼容口）
  const musicBatchBusy = ref(false)
  const musicPicked = ref([])        // 已勾选的 cid 列表
  const musicCandidates = computed(() =>
    (Array.isArray(musicResult.value?.candidates) ? musicResult.value.candidates : []))

  async function runMusicSearch() {
    const q = String(musicQuery.value || '').trim()
    if (!q) {
      musicMsg.value = '请输入歌名 / 艺人'
      return
    }
    musicSearching.value = true
    musicMsg.value = ''
    try {
      const params = [`query=${encodeURIComponent(q)}`, 'page=0']
      const _sites = (Array.isArray(musicSiteIds.value) ? musicSiteIds.value : []).map(String).filter(Boolean)
      if (_sites.length) params.push(`site_ids=${encodeURIComponent(_sites.join(','))}`)
      const res = unwrapResponse(await api.features.musicSearch(params.join('&')))
      if (res) {
        musicResult.value = res
        // ★ 19.12.87：默认勾「最相关且未过滤」的前 N 首 —— 少一次点击，但勾选状态可见可改。
        const ok = (res.candidates || []).filter((c) => c && !c.excluded && c.cid)
        musicPicked.value = ok.slice(0, MUSIC_AUTO_PICK).map((c) => String(c.cid))
      }
    } catch (err) {
      musicMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      musicSearching.value = false
    }
  }

  function toggleMusicPick(cid) {
    const id = String(cid || '')
    if (!id) return
    const cur = musicPicked.value
    musicPicked.value = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]
  }

  function pickAllMusic() {
    const ok = musicCandidates.value.filter((c) => c && !c.excluded && c.cid).map((c) => String(c.cid))
    const all = ok.length > 0 && ok.every((id) => musicPicked.value.includes(id))
    musicPicked.value = all ? [] : ok
  }

  /** 批量加种（唯一的「下」入口：cids 逗号分隔，后端一次落种） */
  async function downloadMusicPicked() {
    const ids = musicPicked.value.slice()
    if (!ids.length) {
      musicMsg.value = '先勾几首再下'
      return
    }
    musicMsg.value = ''
    musicBatchBusy.value = true
    try {
      const res = unwrapResponse(await api.features.musicDownload(ids.join(',')))
      const d = res?.summary || {}
      musicMsg.value = `已提交下载 ${ids.length} 条：新增 ${d.added || 0} / 跳过 ${d.skipped || 0} / 失败 ${d.failed || 0}`
      musicPicked.value = []
      loadMusicItems()
    } catch (err) {
      musicMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      musicBatchBusy.value = false
    }
  }

  /** 单条（兼容旧调用点 / 行内重试） */
  async function downloadMusic(cid) {
    if (!cid) return
    musicMsg.value = ''
    musicDownloading.value = String(cid)
    try {
      const res = unwrapResponse(await api.features.musicDownload(String(cid)))
      const d = res?.summary || {}
      musicMsg.value = `已提交下载：新增 ${d.added || 0} / 跳过 ${d.skipped || 0} / 失败 ${d.failed || 0}`
      loadMusicItems()
    } catch (err) {
      musicMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      musicDownloading.value = ''
    }
  }

  // ── 清单与分组 ──────────────────────────────────────────────
  const musicAll = computed(() => (Array.isArray(musicItems.value?.items) ? musicItems.value.items : []))
  const musicTotal = computed(() => {
    const n = Number(musicItems.value?.total)
    return Number.isFinite(n) && n > 0 ? n : musicAll.value.length
  })
  const musicHasMore = computed(() => musicAll.value.length < musicTotal.value)

  const musicInflight = computed(() => musicAll.value.filter(
    (r) => r && (r.stage === 'downloading' || r.stage === 'settling')))

  /** 下完没入库（最需要人动手的一档之一） */
  const musicPending = computed(() => musicAll.value.filter(
    (r) => r && r.stage === 'resource' && !r.in_library))

  /** 入库失败/部分失败 —— 以前只活在日志里 */
  const musicBroken = computed(() => musicAll.value.filter(
    (r) => r && !r.in_library && (r.import_state === 'failed' || r.import_state === 'partial'
      || Number(r.import_failed || 0) > 0)))

  const musicInLibrary = computed(() => musicAll.value.filter((r) => r && r.in_library))

  const musicGone = computed(() => musicAll.value.filter(
    (r) => r && r.stage === 'gone' && !r.in_library))

  /** 已完成（去重，按「要动手 → 不用管」排序） */
  const musicHistory = computed(() => {
    const seen = new Set()
    const out = []
    for (const arr of [musicBroken.value, musicPending.value, musicInLibrary.value, musicGone.value]) {
      for (const r of arr) {
        const h = String(r?.hash || '')
        if (!h || seen.has(h)) continue
        seen.add(h)
        out.push(r)
      }
    }
    return out
  })

  function openMusic() {
    musicOpen.value = true
    musicMsg.value = ''
    loadMusicItems()
  }

  async function _loadMusicPage(append) {
    musicItemsBusy.value = true
    try {
      // ★ 19.12.87：刷新时**保持已加载的页数**，否则 10s 轮询会把「加载更多」收回第一页。
      const loaded = musicAll.value.length
      const lim = append ? MUSIC_PAGE : Math.min(200, Math.max(MUSIC_PAGE, loaded))
      const off = append ? loaded : 0
      const res = unwrapResponse(await api.features.musicItems(lim, off))
      if (res) {
        if (append && Array.isArray(res.items)) {
          musicItems.value = { ...res, items: [...musicAll.value, ...res.items] }
        } else {
          musicItems.value = res
        }
      }
    } catch (err) {
      // 清单是增强信息，失败不打断主流程
    } finally {
      musicItemsBusy.value = false
    }
  }
  // ★ 传参保护：模板上 @click="loadMusicItems" 会把 event 当 append 传进来
  function loadMusicItems(append) { return _loadMusicPage(append === true) }
  function loadMoreMusic() {
    if (musicItemsBusy.value || !musicHasMore.value) return
    _loadMusicPage(true)
  }

  function startMusicPolling() {
    stopMusicPolling()
    musicTimer = startPolling(() => loadMusicItems(false), 10000)
  }
  function stopMusicPolling() {
    if (musicTimer) {
      stopPolling(musicTimer)
      musicTimer = null
    }
  }
  watch(musicOpen, (v) => {
    if (v) {
      loadMusicItems(false)
      startMusicPolling()
    } else {
      stopMusicPolling()
    }
  })

  async function actMusic(row, action) {
    const h = String(row?.hash || '')
    if (!h) return
    if (action === 'remove') {
      const _t = row?.title || h.slice(0, 12)
      if (!confirm(`确认移除「${_t}」？\n\n· 从下载器删除该种 + 文件\n· 欠 H&R / 受保护的种会被拦下`)) return
    }
    musicMsg.value = ''
    musicActing.value = `${h}:${action}`
    try {
      const res = unwrapResponse(await api.features.musicAct(h, action))
      musicMsg.value = res?.message || '已执行'
    } catch (err) {
      musicMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      musicActing.value = ''
      loadMusicItems(false)
    }
  }

  // ★ 19.12.0：单颗入库（下完自动那条的**手动补跑**口）
  //   Master 2026-11-03：「这次是我们手动整理的，这个功能需要做进去」——
  //   自动入队覆盖不了「下完很久了 / 上次失败 / 老种」这些情况，得留一个人能点的地方。
  //   后端提交即返回（后台线程跑），所以这里不做 loading 转圈，只回一句「已入队」。
  async function importMusic(row) {
    const h = String(row?.hash || '')
    if (!h) return
    musicMsg.value = ''
    musicImporting.value = h
    try {
      const res = unwrapResponse(await api.features.musicSettle(h, true))
      const d = res?.summary || res || {}
      const route = d.route ? `走 ${d.route === 'mp' ? 'MP 整理' : '硬链接入库'}` : ''
      const n = Number(d.total || 0)
      musicMsg.value = d.queued
        ? `已入队后台入库：${n || '?'} 首${route ? '，' + route : ''}（job ${d.job_id || '—'}，进度看「后台任务」）`
        : (d.note || '入队未生效，详见插件日志')
      loadMusicItems(false)
    } catch (err) {
      musicMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      musicImporting.value = ''
    }
  }

  return {
    actMusic,
    downloadMusic,
    downloadMusicPicked,
    importMusic,
    loadMoreMusic,
    loadMusicItems,
    musicActing,
    musicBatchBusy,
    musicBroken,
    musicCandidates,
    musicDownloading,
    musicGone,
    musicHasMore,
    musicHistory,
    musicImporting,
    musicInflight,
    musicInLibrary,
    musicItems,
    musicItemsBusy,
    musicMsg,
    musicOpen,
    musicPending,
    musicPicked,
    musicQuery,
    musicResult,
    musicSearching,
    musicSiteIds,
    musicTab,
    musicTotal,
    openMusic,
    pickAllMusic,
    runMusicSearch,
    toggleMusicPick,
  }
}
