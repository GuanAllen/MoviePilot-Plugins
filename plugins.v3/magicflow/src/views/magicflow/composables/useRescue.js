// MagicFlow 前端 · 死种补源域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：死种补源弹窗状态 + 扫描 / 干跑 / 落地 + 目标与跳过站点派生。
// 依赖注入：api（createApi 客户端）、notify（提示）、error（全局错误 ref，仅失败时写）。
// ★ 真值源仍在后端（/rescue），本层只持有 UI 状态。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useRescue({ api, notify, error }) {
  // ── 死种补源（rescue）：停滞欠 H&R 的种 → 他站「无 H&R」站补下同 Release ────────
  const rescueOpen = ref(false)
  const rescueData = ref(null)
  const rescueScanning = ref(false)
  const rescueBusy = ref(false)
  const rescueBusyType = ref('')
  const rescueTargets = computed(() => (Array.isArray(rescueData.value?.targets) ? rescueData.value.targets : []))
  const rescueSkippedSites = computed(() => (Array.isArray(rescueData.value?.skipped_sites) ? rescueData.value.skipped_sites : []))

  async function loadRescue() {
    try {
      rescueData.value = unwrapResponse(await api.features.rescueScan()) || null
    } catch (err) {
      // 补源是增强信息，失败不打断界面
    }
  }

  function openRescue() {
    rescueOpen.value = true
    rescueData.value = null
    loadRescue()
  }

  async function runRescueScan() {
    rescueScanning.value = true
    try {
      await loadRescue()
      if (!rescueData.value) notify('死种补源：扫描失败（见后端日志）', 'warning')
    } finally {
      rescueScanning.value = false
    }
  }

  async function runRescueApply(confirm) {
    rescueBusy.value = true
    rescueBusyType.value = confirm ? 'apply' : 'preview'
    try {
      const hashes = rescueTargets.value.map(t => t.hash).filter(Boolean)
      const params = [`action=apply`, `hashes=${encodeURIComponent(hashes.join(','))}`]
      if (confirm) params.push('confirm=1')
      else params.push('dry_run=1')
      const res = unwrapResponse(await api.features.rescueRun(params.join('&'))) || {}
      if (confirm) {
        notify(`死种补源：已补 ${res.added ?? 0} 个副本`)
      } else {
        notify(`死种补源（干跑）：将补 ${res.would_add ?? 0} 个副本（未落盘）`)
      }
      await loadRescue()
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      rescueBusy.value = false
      rescueBusyType.value = ''
    }
  }

  return {
    rescueOpen, rescueData, rescueScanning, rescueBusy, rescueBusyType,
    rescueTargets, rescueSkippedSites,
    loadRescue, openRescue, runRescueScan, runRescueApply,
  }
}
