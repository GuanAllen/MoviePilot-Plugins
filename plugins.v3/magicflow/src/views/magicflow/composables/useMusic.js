// MagicFlow 前端 · useMusic 域 composable
// ★ 2026-10-10（批2）：音乐线改为「清单」视图 —— 与点播同构（单列表 + 进行中/已完成两 Tab + 行内操作）。
//   Master 口径：「清单做，跟点播一样，不要歌单了（塞不下）」。
//   真值源仍在后端（GET /agent/music/items、POST /agent/music/act）；本层只放 UI 状态与动作。
import { computed, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useMusic({ api }) {
  const musicOpen = ref(false)
  const musicItems = ref({ items: [], totals: {} })
  const musicItemsBusy = ref(false)
  const musicTab = ref('inflight')   // 'inflight' | 'done'
  const musicActing = ref('')        // `${hash}:${action}`
  const musicImporting = ref('')     // ★ 19.12.0：正在提交入库的 hash
  const musicMsg = ref('')
  let musicTimer = null

  // ── 单搜单下（人机同源）───────────────────────────────────────
  // ★ Master 2026-10-10 14:55：「不是所有人都有 AI 助手」——UI 也得能单首搜 + 下。
  //   走的就是 AI 入口那组端点（/agent/music/search → /agent/music/download），单一真值源。
  const musicQuery = ref('')
  const musicSiteIds = ref([])
  const musicSearching = ref(false)
  const musicResult = ref(null)      // {keyword, sites, sources[], candidates[], total_items}
  const musicDownloading = ref('')   // 正在下载的 cid
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
      if (res) musicResult.value = res
    } catch (err) {
      musicMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      musicSearching.value = false
    }
  }

  async function downloadMusic(cid) {
    if (!cid) return
    musicMsg.value = ''
    musicDownloading.value = String(cid)
    try {
      const res = unwrapResponse(await api.features.musicDownload(cid))
      const d = res?.summary || {}
      musicMsg.value = `已提交下载：新增 ${d.added || 0} / 跳过 ${d.skipped || 0} / 失败 ${d.failed || 0}`
      loadMusicItems()
    } catch (err) {
      musicMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      musicDownloading.value = ''
    }
  }

  // ★ 后端为单列表 items[]（在库+历史同构）；此处按 stage 派生两个 Tab（与点播一致）。
  const _mItems = computed(() => (Array.isArray(musicItems.value?.items) ? musicItems.value.items : []))
  const musicInflight = computed(() => _mItems.value.filter(
    (r) => r && (r.stage === 'downloading' || r.stage === 'settling')))
  const musicHistory = computed(() => _mItems.value.filter(
    (r) => r && (r.stage === 'resource' || r.stage === 'gone')))

  function openMusic() {
    musicOpen.value = true
    musicMsg.value = ''
    loadMusicItems()
  }

  async function loadMusicItems() {
    musicItemsBusy.value = true
    try {
      const res = unwrapResponse(await api.features.musicItems())
      if (res) musicItems.value = res
    } catch (err) {
      // 清单是增强信息，失败不打断主流程
    } finally {
      musicItemsBusy.value = false
    }
  }
  function startMusicPolling() {
    stopMusicPolling()
    musicTimer = window.setInterval(loadMusicItems, 10000)
  }
  function stopMusicPolling() {
    if (musicTimer) {
      window.clearInterval(musicTimer)
      musicTimer = null
    }
  }
  watch(musicOpen, (v) => {
    if (v) {
      loadMusicItems()
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
      loadMusicItems()
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
      loadMusicItems()
    } catch (err) {
      musicMsg.value = `❌ ${err?.message || String(err)}`
    } finally {
      musicImporting.value = ''
    }
  }

  return {
    actMusic,
    downloadMusic,
    importMusic,
    loadMusicItems,
    musicActing,
    musicCandidates,
    musicDownloading,
    musicHistory,
    musicImporting,
    musicInflight,
    musicItems,
    musicItemsBusy,
    musicMsg,
    musicOpen,
    musicQuery,
    musicResult,
    musicSearching,
    musicSiteIds,
    musicTab,
    openMusic,
    runMusicSearch,
  }
}
