// MagicFlow 前端 · 计划审批（★ 15.17.0）
// Master：「ai决策链」→ 一起做：「AI 出计划 → 人复核 → 执行」。
// 关键设计：**审批凭据 = 计划内容哈希（plan_id）** —— 人批准的是「他看到的那个计划」；
// 池内状态一变，重新生成的哈希就变，旧批准自动作废（后端 plan_stale 拒绝）。
// 前端只做两件事：① 生成并展示计划 + 逐条依据链；② 把 plan_id 原样带回去执行（默认干跑）。
import { computed, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

export function usePlan({ api, notify, itemsOf }) {
  const planOpen = ref(false)
  const planAction = ref('cleanup')
  const planTaskId = ref('')
  const planBudget = ref('')
  const planLoading = ref(false)
  const planData = ref(null)
  const planApplying = ref(false)
  const planApplied = ref(null)

  const planItems = computed(() => (typeof itemsOf === 'function' ? itemsOf() : []))
  const PLAN_ACTIONS = [
    { title: '清理（逐条阈值）', value: 'cleanup' },
    { title: '组合优化（体积预算）', value: 'optimize' },
  ]

  /** 生成计划（只算不删）。任何输入变化都应重新生成 → plan_id 失效。 */
  async function loadPlan() {
    const ident = String(planTaskId.value || '')
    if (!ident) {
      planData.value = null
      return
    }
    planLoading.value = true
    planApplied.value = null
    try {
      const params = { action: String(planAction.value || 'cleanup'), task_id: ident }
      const budget = String(planBudget.value ?? '').trim()
      if (params.action === 'optimize' && budget !== '') params.budget_gb = budget
      const resp = await api.plan.plan(params)
      planData.value = unwrapResponse(resp) || null
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '计划生成失败', 'error')
      planData.value = null
    } finally {
      planLoading.value = false
    }
  }

  /** 打开弹窗（可选指定任务；缺省取任务列表第一个）。 */
  function openPlan(opts = {}) {
    planOpen.value = true
    let ident = String(opts.taskId || '')
    if (!ident) {
      const list = planItems.value
      ident = list.length ? String(list[0].value) : ''
    }
    const idChanged = planTaskId.value !== ident
    const actChanged = String(planAction.value || '') !== String(opts.action || 'cleanup')
    planTaskId.value = ident
    planAction.value = String(opts.action || 'cleanup')
    if (opts.resetBudget !== false) planBudget.value = ''
    // 输入没变（重开同一任务）才显式拉一次，避免重复请求。
    if (!idChanged && !actChanged) loadPlan()
  }

  /**
   * 执行计划。``confirm=false`` = 干跑（零写入，后端也回 dry_run）。
   * ★ 必须带**当前** plan_id：后端会重新生成比对，不一致回 ``plan_stale`` → 提示重新生成。
   * ★ ``deleteFiles`` 也是审批的一部分：换档必须重新干跑（前端 ``approvable`` 会把关）。
   */
  async function applyPlan(confirm = false, deleteFiles = 0) {
    const data = planData.value
    const pid = String((data && data.plan_id) || '')
    if (!pid) {
      notify('先生成计划，再执行', 'warning')
      return
    }
    planApplying.value = true
    try {
      const resp = await api.plan.apply({
        plan_id: pid,
        action: String(planAction.value || 'cleanup'),
        task_id: String(planTaskId.value || ''),
        budget_gb: String(planBudget.value ?? '').trim(),
        delete_files: deleteFiles ? 1 : 0,
        confirm: confirm ? 1 : 0,
      })
      const out = unwrapResponse(resp) || {}
      planApplied.value = out
      if (out.dry_run) {
        notify(`干跑：将删 ${out.would_delete || 0} 条（零写入）`, 'info')
      } else {
        const n = Number(out.deleted || 0)
        const blocked = Array.isArray(out.blocked) ? out.blocked.length : 0
        notify(`已执行：删 ${n} 条${blocked ? `，${blocked} 条被保护拦下` : ''}`, n > 0 ? 'success' : 'info')
        await loadPlan() // 执行后池内已变 → 重新生成，plan_id 自然更新
      }
    } catch (err) {
      const code = err?.response?.data?.code || ''
      if (code === 'plan_stale') {
        notify('计划已过期（池内已变），已重新生成，请复核后批准', 'warning')
        planApplied.value = null
        await loadPlan()
      } else {
        notify(err?.response?.data?.message || err?.message || '执行失败', 'error')
      }
    } finally {
      planApplying.value = false
    }
  }

  watch([planAction, planTaskId, planBudget], () => {
    if (planOpen.value) loadPlan()
  })

  return {
    planOpen, planAction, planTaskId, planBudget, planLoading, planData, planApplying, planApplied,
    planItems, PLAN_ACTIONS, loadPlan, openPlan, applyPlan,
  }
}
