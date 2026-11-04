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

// ★ 19.10.11：每颗账单「还差多少工时」= need_h − seeded_h（≤0 即已达标的工时线）。
//   与 hours_left（站点考核窗口倒计时）是**两个不同概念**：
//     · 还需 X h → 你给自己/站点定的义务差多久做满，到了就能撤
//     · 窗口剩 X  → 站点考核的截止时间，到了可能判违约
//   界面上必须分开措辞，混着显示会让人以为「窗口过了就已经违约」。
export function hrBillLeftH(it) {
  if (!it) return 0
  const need = Number(it.need_h) || 0
  const seeded = Number(it.seeded_h) || 0
  return Math.max(0, need - seeded)
}
// 已做种 / 需做种，如 "6.1/24.0h"
export function fmtBillSeeded(it) {
  const need = Number((it && it.need_h)) || 0
  const seeded = Number((it && it.seeded_h)) || 0
  return `${seeded.toFixed(1)}/${need.toFixed(1)}h`
}
export function fmtBillLeft(it) {
  const st = String((it && it.state) || '')
  if (st === 'settled') return '已结清'
  if (st === 'void') return '已作废'
  if (st === 'pending') return '未下完'
  const left = hrBillLeftH(it)
  if (left <= 0.05) return st === 'breached' ? '已违约' : '工时已够·待结清'
  return '还需 ' + (left < 48 ? Math.round(left) + 'h' : (left / 24).toFixed(1) + 'd')
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
