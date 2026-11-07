// MagicFlow 前端 · useHrBills 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// P4：展示用纯函数（hrBillStateColor / hrBillsAtRisk / fmtHoursLeft）提为**具名导出**，
//     供 components/dialogs/HrBillsDialog.vue 直接 import 复用（单一真值源，不复制）。
// 依赖注入：api, error（★ 真值源仍在后端；本域只放 UI 状态与动作）。
// ★ 19.12.48（任务 96）：
//   · 默认实时刷新（live=1），修复「点了刷新仍是启动快照」；
//   · 新增当前登录身份读取（人工结清审计操作人的唯一来源）；
//   · 新增人工结清提交动作（复用后端 hrbills_settle_manual，不新增业务接口）。
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

// ★ 任务 96：操作人**只能**来自 MoviePilot 当前登录会话。
//   旧版 API 曾用占位串 'manual' 兜底，任务 89 已删；前端也不许拿它当人名。
const INVALID_OPERATORS = ['manual', 'unknown', 'anonymous']
export function normalizeOperator(v) {
  const name = String(v == null ? '' : v).trim()
  if (!name || INVALID_OPERATORS.includes(name.toLowerCase())) return ''
  return name.slice(0, 64)
}
// 后端允许条件（19.12.44 起）：void 拒绝；settled+manual 幂等；settled+auto 允许
// 人工接管；其余状态（active / breached / pending）均可人工结清。
// 前端取**保守子集**：终态（settled/void）一律不显示按钮（任务 96 阶段 C 第 9 条），
// 不为此放宽任何后端状态限制。
export function canManualSettle(it) {
  if (!it || !String(it.hash || '').trim()) return false
  const st = String(it.state || '')
  return ['active', 'breached', 'pending'].includes(st) && it.settlement_method !== 'manual'
}

export function useHrBills({ api, error, notify } = {}) {
  const hrBillsOpen = ref(false)
  // ★ 任务 96：默认实时。原来 false + 刷新按钮显式传 false → 用户点刷新拿到的是
  //   reportview 的启动快照（任务 95 实证 `at` 恒为 16:46:59，新账单永远看不见）。
  const hrBillsLive = ref(true)
  const hrBillsLoading = ref(false)
  const hrBills = ref({ totals: {}, sites: [], source_of_truth: [], write: {} })
  const hrOperator = ref('')
  const hrOperatorError = ref('')

  function openHrBills() {
    hrBillsOpen.value = true
    loadHrBills()
    loadHrOperator()
  }

  async function loadHrBills(liveOverride) {
    hrBillsLoading.value = true
    try {
      const q = new URLSearchParams()
      if (liveOverride === true || (liveOverride === undefined && hrBillsLive.value)) q.set('live', '1')
      const data = unwrapResponse(await api.poolstats.hrBills(q.toString())) || {}
      hrBills.value = data
    } catch (e) {
      if (error && typeof error === 'object' && 'value' in error) {
        error.value = `H&R 账单加载失败：${e}`
      }
    } finally {
      hrBillsLoading.value = false
    }
  }

  /** 当前登录用户名（宿主 user/current）；取不到 → 空，人工结清提交会被拒绝。 */
  async function loadHrOperator() {
    if (hrOperator.value) return hrOperator.value
    try {
      const raw = await api.poolstats.currentUser()
      const d = unwrapResponse(raw) || {}
      const name = normalizeOperator(d && (d.name || d.username || d.user_name))
      hrOperator.value = name
      hrOperatorError.value = name ? '' : '当前会话未返回有效登录用户名，不能人工结清'
    } catch (e) {
      hrOperator.value = ''
      hrOperatorError.value = `无法获取当前登录身份：${e?.message || e}`
    }
    return hrOperator.value
  }

  /**
   * 人工结清（复用已有 /tags?action=hrbills_settle_manual，confirm=1 固定）。
   * 返回归一化的 { ok, kind, message, data }，弹窗按 kind 区分
   * success / already / conflict / 其它失败；**不**改写任何账单状态。
   */
  async function settleHrBill({ hash, reason, by } = {}) {
    const h = String(hash || '').trim().toLowerCase()
    const r = String(reason || '').trim()
    const op = normalizeOperator(by)
    if (!h) return { ok: false, kind: 'invalid', message: '缺少账单 hash' }
    if (!r) return { ok: false, kind: 'missing_reason', message: '人工结清必须填写原因' }
    if (!op) {
      return { ok: false, kind: 'missing_operator', message: '缺少当前登录身份，禁止使用占位操作人' }
    }
    try {
      const resp = await api.poolstats.hrSettleManual({ hash: h, reason: r, by: op })
      const data = (resp && resp.data !== undefined) ? resp.data : resp
      if (resp && resp.success === false) {
        return {
          ok: false,
          kind: String((data && data.error) || 'failed'),
          message: String(resp.message || (data && data.message) || '人工结清失败'),
          data,
        }
      }
      const kind = data && data.already ? 'already' : 'success'
      return {
        ok: true,
        kind,
        message: String(resp?.message || (kind === 'already' ? '该账单此前已人工结清（幂等跳过）' : '人工结清成功')),
        data,
      }
    } catch (e) {
      return { ok: false, kind: 'failed', message: `人工结清失败：${e?.message || e}` }
    }
  }

  function hrSettleNotice(text, tone = 'success') {
    if (typeof notify === 'function') notify(text, tone)
  }

  return {
    hrBills,
    hrBillsLoading,
    hrBillsOpen,
    loadHrBills,
    openHrBills,
    hrOperator,
    hrOperatorError,
    loadHrOperator,
    settleHrBill,
    hrSettleNotice,
  }
}
