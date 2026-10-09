// MagicFlow 前端 · useCrossseed 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api, notify（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { unwrapResponse } from '../../../utils'
import { formatRemain } from '../format'

// ★ P4（2026-10-09）：模板用的两个纯函数改 **module 级具名导出**，供 CrossseedDialog.vue 直接 import 复用
//   （单一真值源；原在工厂内定义，拆弹窗后工厂不再需要返回它们）。
export function crossseedCardState(it) {
  if (it?.done) return { color: 'grey', text: '保种期满可回收' }
  if (it?.fulfilled) return { color: 'success', text: '正常' }
  const rest = Number(it?.remain_min)
  return { color: 'warning', text: rest > 0 ? `保种中 · 剩 ${formatRemain(rest)}` : '保种中' }
}

export function crossseedStateText(it) {
  const st = String(it?.state || '')
  const p = it?.progress
  if (st && /paused|stopped|暂停/i.test(st)) return '已暂停'
  if (Number.isFinite(Number(p)) && Number(p) >= 0.999) return '已下载完（待分诊）'
  if (Number.isFinite(Number(p)) && Number(p) > 0) return `下载中 ${(Number(p) * 100).toFixed(1)}%`
  if (p === null || p === undefined) return '下载器中无此种'
  return '等待下载'
}

export function useCrossseed({ api, notify }) {
  const crossseedData = ref({ count: 0, pending: [], enabled_tasks: [] })
  let crossseedTimer = null
  async function loadCrossseed() {
    try {
      crossseedData.value = unwrapResponse(await api.features.crossseed())
        || { count: 0, pending: [], enabled_tasks: [] }
    } catch (err) {
      // 跨站取种是增强信息，失败不打断界面
    }
  }
  function showCrossseed() {
    crossseedOpen.value = true
    loadCrossseed()
  }
  const crossseedOpen = ref(false)
  const crossseedActing = ref('')
  const crossseedPending = computed(() =>
    (Array.isArray(crossseedData.value?.pending) ? crossseedData.value.pending : [])
  )
  const crossseedGuard = computed(() => (crossseedData.value || {}).guard || { enabled: true, banned: [] })
  const crossseedBanned = computed(() =>
    (Array.isArray(crossseedGuard.value?.banned) ? crossseedGuard.value.banned : [])
  )
  const crossseedSourcesAll = computed(() =>
    (Array.isArray(crossseedData.value?.sources) ? crossseedData.value.sources : [])
  )
  const crossseedSources = computed(() => crossseedSourcesAll.value.filter(s => !s.legacy))
  const crossseedLegacyCount = computed(() => crossseedSourcesAll.value.filter(s => !!s.legacy).length)
  const crossseedSilentCount = computed(
    () => crossseedSources.value.filter(s => String(s.pool || '') === 'silent').length
  )
  const crossseedPendingHandoff = computed(() =>
    Math.max(0, crossseedSources.value.length - crossseedSilentCount.value)
  )
  const crossseedStats = computed(() => ({
    pending: Number(crossseedData.value?.count || 0),
    tasks: Array.isArray(crossseedData.value?.enabled_tasks) ? crossseedData.value.enabled_tasks.length : 0,
    sources: crossseedSources.value.length,
  }))
  async function dropCrossseed(h) {
    if (!h) return
    crossseedActing.value = `drop:${h}`
    try {
      const res = unwrapResponse(await api.features.crossseedDrop(h)) || {}
      notify(res.message || '已删除跨站种', 'success')
      await loadCrossseed()
    } catch (err) {
      notify(err?.message || '删除失败', 'error')
    } finally {
      crossseedActing.value = ''
    }
  }
  async function unbanCrossseed(domain = '') {
    crossseedActing.value = `unban:${domain}`
    try {
      const res = unwrapResponse(await api.features.crossseedUnban(domain)) || {}
      notify(res.message || '已解除来源站黑名单', 'success')
      await loadCrossseed()
    } catch (err) {
      notify(err?.message || '解除失败', 'error')
    } finally {
      crossseedActing.value = ''
    }
  }
  async function runCrossseedGuard() {
    crossseedActing.value = 'guard'
    try {
      const res = unwrapResponse(await api.features.crossseedGuard()) || {}
      if (res) crossseedData.value = res
      notify(res.message || '流量兜底核对完成', 'success')
    } catch (err) {
      notify(err?.message || '核对失败', 'error')
    } finally {
      crossseedActing.value = ''
    }
  }
  async function clearCrossseed() {
    crossseedActing.value = 'clear'
    try {
      const res = unwrapResponse(await api.features.crossseedClear()) || {}
      notify(res.message || '已清空取种台账', 'success')
      await loadCrossseed()
    } catch (err) {
      notify(err?.message || '清空失败', 'error')
    } finally {
      crossseedActing.value = ''
    }
  }
  onMounted(() => {
    // 跨站免费取种台账（在飞取种 · 低频刷角标）
    loadCrossseed()
    crossseedTimer = window.setInterval(loadCrossseed, 120000)
  })

  onUnmounted(() => {
    if (crossseedTimer) window.clearInterval(crossseedTimer)
  })


  return {
    clearCrossseed,
    crossseedActing,
    crossseedBanned,
    crossseedData,
    crossseedGuard,
    crossseedLegacyCount,
    crossseedOpen,
    crossseedPending,
    crossseedPendingHandoff,
    crossseedSilentCount,
    crossseedSources,
    crossseedSourcesAll,
    crossseedStats,
    crossseedTimer,
    dropCrossseed,
    loadCrossseed,
    runCrossseedGuard,
    showCrossseed,
    unbanCrossseed,
  }
}
