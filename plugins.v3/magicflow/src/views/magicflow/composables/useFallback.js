// MagicFlow 前端 · useFallback 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api, error, notify, settingsDraft（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, ref } from 'vue'
import { FALLBACK_SOURCE_OPTIONS } from '../../../utils'
import { unwrapResponse } from '../../../utils'

// ★ P4：纯函数提到 module 级具名导出，供 dialogs/SettingsDialog.vue 复用（单一真值源）。
export function fallbackSourceLabel(value) {
  const found = FALLBACK_SOURCE_OPTIONS.find(opt => opt.value === value)
  return found ? found.title : String(value || '')
}

export function useFallback({ api, error, notify, settingsDraft }) {
  const fallbackState = ref(null)
  const fallbackLoading = ref(false)
  const fallbackRunning = ref(false)
  const fallbackSourceDraft = ref('')
  const fallbackProblemShows = computed(() => (((fallbackState.value || {}).report || {}).scanned || []).filter(s => (s.problems || []).length))
  const fallbackProblemCount = computed(() => fallbackProblemShows.value.reduce((acc, s) => acc + (s.problems || []).length, 0))
  const fallbackSourceOptions = FALLBACK_SOURCE_OPTIONS
  const usedFallbackSources = computed(() => settingsDraft.value.fallback_sources || [])
  const unusedFallbackSources = computed(() =>
    FALLBACK_SOURCE_OPTIONS.filter(opt => !usedFallbackSources.value.includes(opt.value)),
  )
  function moveFallbackSource(index, delta) {
    const list = [...(settingsDraft.value.fallback_sources || [])]
    const target = index + delta
    if (target < 0 || target >= list.length) return
    const tmp = list[index]
    list[index] = list[target]
    list[target] = tmp
    settingsDraft.value.fallback_sources = list
  }
  function removeFallbackSource(value) {
    settingsDraft.value.fallback_sources = (settingsDraft.value.fallback_sources || []).filter(v => v !== value)
  }
  function addFallbackSource() {
    const value = String(fallbackSourceDraft.value || '').trim().toLowerCase()
    if (!value) return
    const list = [...(settingsDraft.value.fallback_sources || [])]
    if (!list.includes(value)) list.push(value)
    settingsDraft.value.fallback_sources = list
    fallbackSourceDraft.value = ''
  }
  async function loadFallback() {
    fallbackLoading.value = true
    try {
      fallbackState.value = unwrapResponse(await api.features.fallback())
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      fallbackLoading.value = false
      if (fallbackState.value?.running) setTimeout(() => { loadFallback() }, 6000)
    }
  }
  async function runFallback(dryRun = false) {
    fallbackRunning.value = true
    try {
      unwrapResponse(
        await api.features.fallbackRun(dryRun),
      )
      notify(dryRun ? '演练扫描已开始（不会写 NFO）' : '元数据兜底已开始')
      setTimeout(() => { loadFallback() }, 3000)
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      fallbackRunning.value = false
    }
  }

  return {
    addFallbackSource,
    fallbackLoading,
    fallbackProblemCount,
    fallbackProblemShows,
    fallbackRunning,
    fallbackSourceDraft,
    fallbackSourceLabel,
    fallbackSourceOptions,
    fallbackState,
    loadFallback,
    moveFallbackSource,
    removeFallbackSource,
    runFallback,
    unusedFallbackSources,
    usedFallbackSources,
  }
}
