// MagicFlow 前端 · useSeeding 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api, emit, bonusData, error, loadBonus, loadDetail, notify, saving, selectedTask, status（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'
import { BATCH_LABEL } from '../constants'
import { TORRENT_ACTION_LABEL } from '../constants'
import { TORRENT_PAUSED_STATES } from '../constants'
import { TORRENT_STATE_TEXT } from '../constants'
import { TORRENT_TRANSIENT_STATES } from '../constants'

export function useSeeding({ api, emit, bonusData, error, loadBonus, loadDetail, notify, saving, selectedTask, status }) {
  const torrentFilter = ref('all')
  const torrentStatusFilter = ref('all')
  const torrentDialog = ref(false)
  const activeTorrent = ref(null)
  const torrentDeleteDialog = ref(false)
  const pendingTorrentDelete = ref(null)
  const selectedRows = ref([])
  const batchBusy = ref(false)
  const batchDeleteDialog = ref(false)
  const transferDialog = ref(false)
  const transferTarget = ref('idle')
  const transferChoices = computed(() => {
    const out = [{ value: 'idle', text: '静默池（退回，保文件）' }]
    const me = selectedTask.value
    const mySite = String(me?.site_name || '')
    const rest = (status.value?.tasks || []).filter(t => String(t.id) !== String(me?.id))
    rest.sort((a, b) => Number(String(b.site_name) === mySite) - Number(String(a.site_name) === mySite))
    for (const t of rest) {
      const sameSite = String(t.site_name) === mySite
      out.push({
        value: String(t.id),
        text: `${t.name}${t.enabled ? '' : '（已停用）'} — ${t.site_name}·${t.task_type === 'brush' ? '刷流' : '魔力'}${sameSite ? ' · 同站' : ' · 跨站(会改站点标签)'}`,
      })
    }
    return out
  })
  function openTransfer() {
    if (!selectedHashes.value.length) return
    transferTarget.value = 'idle'
    transferDialog.value = true
  }
  async function confirmTransfer() {
    const hashes = selectedHashes.value
    if (!hashes.length || !selectedTask.value) return
    batchBusy.value = true
    try {
      const body = transferTarget.value === 'idle'
        ? { mode: 'idle', hashes }
        : { mode: 'handover', target_task_id: transferTarget.value, hashes }
      const res = await api.tasks.handover(selectedTask.value.id, body)
      if (res?.success === false) throw new Error(res?.message || '转移失败')
      notify(res?.message || '已转移')
      transferDialog.value = false
      selectedRows.value = []
      await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)])
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      batchBusy.value = false
    }
  }
  const selectedHashes = computed(() =>
    (selectedRows.value || []).map(row => row?.hash).filter(Boolean),
  )
  const sortedTorrents = computed(() => {
    let items = bonusData.value.torrents || []
    if (torrentFilter.value === 'protected') items = items.filter(item => item.is_protected)
    if (torrentStatusFilter.value !== 'all') items = items.filter(item => torrentStatusGroup(item) === torrentStatusFilter.value)
    return items
  })
  const torrentHeaders = [
    { title: '', key: 'select', sortable: false, width: 44 },
    { title: '种子', key: 'title', sortable: false },
    { title: '状态', key: 'status', sortable: false, width: 120 },
    { title: '大小', key: 'size_gb', sortable: false, width: 96 },
    { title: '上传量', key: 'uploaded', sortable: false, width: 96 },
    { title: '分享率', key: 'ratio', sortable: false, width: 84 },
    { title: '操作', key: 'actions', sortable: false, width: 120 },
  ]
  const allFilteredSelected = computed(
    () => sortedTorrents.value.length > 0 && selectedHashes.value.length === sortedTorrents.value.length,
  )
  function stateLabel(state) {
    const key = String(state || '').toLowerCase()
    return TORRENT_STATE_TEXT[key] || (key ? state : '托管中')
  }
  function stateColor(state) {
    const key = String(state || '').toLowerCase()
    if (['uploading', 'forcedup', 'stalledup', 'queuedup'].includes(key)) return 'success'
    if (['downloading', 'forceddl', 'queueddl', 'metadl', 'checkingdl'].includes(key)) return 'info'
    if (key === 'stalleddl') return 'warning'
    if (['error', 'missingfiles'].includes(key)) return 'error'
    return 'grey'
  }
  function torrentStateText(item) {
    const key = String(item?.state || '').toLowerCase()
    if (TORRENT_TRANSIENT_STATES[key]) return TORRENT_TRANSIENT_STATES[key]
    if (TORRENT_PAUSED_STATES.includes(key)) return stateLabel(item?.state) || '已暂停'
    const pct = torrentProgressPct(item)
    if (pct >= 100) return '做种中'
    if (pct <= 0) return stateLabel(item?.state) || '等待中'
    return `下载 ${pct}%`
  }
  function torrentIsPaused(item) {
    return TORRENT_PAUSED_STATES.includes(String(item?.state || '').toLowerCase())
  }
  function torrentPauseLabel(item) {
    return torrentProgressPct(item) >= 100 ? '暂停做种' : '暂停下载'
  }
  function torrentResumeLabel(item) {
    return torrentProgressPct(item) >= 100 ? '恢复做种' : '继续下载'
  }
  function torrentProgressPct(item) {
    const pct = Number(item?.progress || 0) * 100
    if (!Number.isFinite(pct)) return 0
    return Math.max(0, Math.min(100, Math.round(pct)))
  }
  function torrentStatusGroup(item) {
    const key = String(item?.state || '').toLowerCase()
    if (['uploading', 'forcedup', 'stalledup', 'queuedup', 'checkingup'].includes(key)) return 'seeding'
    if (['downloading', 'forceddl', 'queueddl', 'metadl', 'forcedmetadl', 'checkingdl', 'allocating'].includes(key)) return 'downloading'
    if (key === 'stalleddl') return 'stalled'
    if (TORRENT_PAUSED_STATES.includes(key)) return 'paused'
    if (['error', 'missingfiles'].includes(key)) return 'error'
    return 'other'
  }
  const torrentStatusOptions = computed(() => {
    const items = bonusData.value.torrents || []
    const count = group => items.filter(item => torrentStatusGroup(item) === group).length
    const opts = [
      { title: `全部状态（${items.length}）`, value: 'all' },
      { title: `做种中（${count('seeding')}）`, value: 'seeding' },
      { title: `下载中（${count('downloading')}）`, value: 'downloading' },
      { title: `下载停滞（${count('stalled')}）`, value: 'stalled' },
      { title: `已暂停 / 停止（${count('paused')}）`, value: 'paused' },
      { title: `出错（${count('error')}）`, value: 'error' },
    ]
    const other = count('other')
    if (other > 0) opts.push({ title: `其它（${other}）`, value: 'other' })
    return opts
  })
  function torrentActionMessage(torrent, action) {
    if (action === 'pause' || action === 'resume') {
      const seeding = torrentProgressPct(torrent) >= 100
      if (action === 'pause') return seeding ? '已暂停做种（不会被自动恢复）' : '已暂停下载（不会被自动恢复）'
      return seeding ? '已恢复做种' : '已继续下载'
    }
    return TORRENT_ACTION_LABEL[action] || '操作已完成'
  }
  async function torrentAction(torrent, action) {
    saving.value = true
    try {
      unwrapResponse(
        await api.tasks.torrentAction(selectedTask.value.id, torrent.hash, action),
      )
      notify(torrentActionMessage(torrent, action))
      await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)])
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      saving.value = false
    }
  }
  function requestTorrentDelete(torrent) {
    if (!torrent) return
    pendingTorrentDelete.value = torrent
    torrentDeleteDialog.value = true
  }
  async function confirmTorrentDelete() {
    const target = pendingTorrentDelete.value
    if (!target) return
    await torrentAction(target, 'delete')
    torrentDeleteDialog.value = false
    // 若刚删的是详情弹窗里那颗，一并关掉
    if ((activeTorrent.value?.hash || '') && (activeTorrent.value?.hash || '').toLowerCase() === (target.hash || '').toLowerCase()) {
      torrentDialog.value = false
    }
    pendingTorrentDelete.value = null
  }
  async function batchAction(action) {
    const hashes = selectedHashes.value
    if (!hashes.length || !selectedTask.value) return
    batchBusy.value = true
    try {
      const res = unwrapResponse(
        await api.tasks.torrentsBatch(selectedTask.value.id, { action, hashes }),
      )
      const done = Number(res?.success_count ?? hashes.length)
      notify(`${BATCH_LABEL[action] || '批量操作'}完成：${done} 个`)
      selectedRows.value = []
      batchDeleteDialog.value = false
      await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)])
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      batchBusy.value = false
    }
  }
  function selectAllFiltered() {
    selectedRows.value = [...sortedTorrents.value]
  }
  function clearSelection() {
    selectedRows.value = []
  }
  async function copyTorrentHash(hash) {
    const text = String(hash || '')
    if (!text) return
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const el = document.createElement('textarea')
        el.value = text
        document.body.appendChild(el)
        el.select()
        document.execCommand('copy')
        document.body.removeChild(el)
      }
      notify('infohash 已复制')
    } catch (err) {
      error.value = `复制失败：${err?.message || err}`
    }
  }
  function toggleTorrentSelection(item) {
    if (!item) return
    const key = (item.hash || '').toLowerCase()
    const exists = (selectedRows.value || []).some(row => (row?.hash || '').toLowerCase() === key)
    selectedRows.value = exists
      ? selectedRows.value.filter(row => (row?.hash || '').toLowerCase() !== key)
      : [...selectedRows.value, item]
  }
  function openTorrentDetail(item) {
    if (!item) return
    activeTorrent.value = item
    torrentDialog.value = true
  }
  function onTorrentRowClick(event, { item }) {
    const target = event?.target
    if (target && typeof target.closest === 'function' && target.closest('.v-btn, button, a, input, label, .v-selection-control')) return
    openTorrentDetail(item)
  }
  async function detailTorrentAction(action) {
    const current = activeTorrent.value
    if (!current) return
    await torrentAction(current, action)
    if (action === 'delete') {
      torrentDialog.value = false
      return
    }
    const key = (current.hash || '').toLowerCase()
    const found = (bonusData.value.torrents || []).find(t => (t.hash || '').toLowerCase() === key)
    if (found) activeTorrent.value = found
  }

  return {
    activeTorrent,
    allFilteredSelected,
    batchAction,
    batchBusy,
    batchDeleteDialog,
    clearSelection,
    confirmTorrentDelete,
    confirmTransfer,
    copyTorrentHash,
    detailTorrentAction,
    onTorrentRowClick,
    openTorrentDetail,
    openTransfer,
    pendingTorrentDelete,
    requestTorrentDelete,
    selectAllFiltered,
    selectedHashes,
    selectedRows,
    sortedTorrents,
    stateColor,
    stateLabel,
    toggleTorrentSelection,
    torrentAction,
    torrentActionMessage,
    torrentDeleteDialog,
    torrentDialog,
    torrentFilter,
    torrentHeaders,
    torrentIsPaused,
    torrentPauseLabel,
    torrentProgressPct,
    torrentResumeLabel,
    torrentStateText,
    torrentStatusFilter,
    torrentStatusGroup,
    torrentStatusOptions,
    transferChoices,
    transferDialog,
    transferTarget,
  }
}
