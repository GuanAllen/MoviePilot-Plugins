// MagicFlow 前端 · useHrBills 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// P4：展示用纯函数（hrBillStateColor / hrBillsAtRisk / fmtHoursLeft）提为**具名导出**，
//     供 components/dialogs/HrBillsDialog.vue 直接 import 复用（单一真值源，不复制）。
// 依赖注入：api, error（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function hrBillStateColor(st) {
  return ({ active: 'error', breached: 'deep-orange', pending: 'amber', settled: 'success', void: 'grey' })[st] || 'grey'
}
// ★ 11.13.0 H&R 临近到期：只列该站 at_risk 的账单（最多 5 条，详情看 AI 端点）
export function hrBillsAtRisk(s) { return ((s && s.items) || []).filter(x => x.at_risk).slice(0, 5) }
// ★ 14.0.0-2：窗口归零 ≠ 违约。hours_left 只是「站点 H&R 窗口倒计时」；
// 违约与否看 state（breached 才是真违约）。窗口小于达标线（如窗口 24h / 需 26h）
// 时 hours_left 先归零，此时账单通常仍是 active —— 文案必须区分，别一律喊「已逾期」。
export function fmtHoursLeft(h, state) {
  if (h === null || h === undefined) return '—'
  const v = Number(h)
  if (!isFinite(v)) return '—'
  if (v <= 0) return String(state || '') === 'breached' ? '已违约' : '窗口已过'
  if (v < 48) return Math.round(v) + 'h'
  return (v / 24).toFixed(1) + 'd'
}

export function useHrBills({ api, error }) {
  const hrBillsOpen = ref(false)
  const hrBillsLive = ref(false)
  const hrBillsLoading = ref(false)
  const hrBills = ref({ totals: {}, sites: [], source_of_truth: [], write: {} })
  function openHrBills() { hrBillsOpen.value = true; loadHrBills() }
  async function loadHrBills(liveOverride) {
    hrBillsLoading.value = true
    try {
      const q = new URLSearchParams()
      if (liveOverride === true || (liveOverride === undefined && hrBillsLive.value)) q.set('live', '1')
      const data = unwrapResponse(await api.poolstats.hrBills(q.toString())) || {}
      hrBills.value = data
    } catch (e) {
      error.value = `H&R 账单加载失败：${e}`
    } finally {
      hrBillsLoading.value = false
    }
  }

  return {
    hrBills,
    hrBillsLoading,
    hrBillsOpen,
    loadHrBills,
    openHrBills,
  }
}
