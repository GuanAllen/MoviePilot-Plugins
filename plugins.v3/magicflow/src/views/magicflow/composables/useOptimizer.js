// MagicFlow 前端 · 组合优化器（★ 15.15.0）
// Master：「在体积预算内，怎样取舍使保留种子的时魔总和最大」→ 0/1 背包的最优「保 / 删」组合。
// 与「逐条阈值」清种互补：阈值法答「哪颗不够格」，优化器答「预算内怎么取舍最划算」。
import { computed, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useOptimizer({ api, notify, itemsOf }) {
  const optimizerOpen = ref(false)
  const optimizerTaskId = ref('')
  const optimizerBudget = ref('')
  const optimizerLoading = ref(false)
  const optimizerData = ref(null)

  const optimizerItems = computed(() => (typeof itemsOf === 'function' ? itemsOf() : []))

  async function loadOptimize() {
    const ident = String(optimizerTaskId.value || '')
    if (!ident) {
      optimizerData.value = null
      return
    }
    optimizerLoading.value = true
    try {
      const budget = String(optimizerBudget.value ?? '').trim()
      const resp = await api.tasks.optimize(ident, budget === '' ? {} : { budget_gb: budget })
      optimizerData.value = unwrapResponse(resp) || null
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '优化读取失败', 'error')
      optimizerData.value = null
    } finally {
      optimizerLoading.value = false
    }
  }

  /** 打开弹窗（可选指定任务；缺省取任务列表第一个）。 */
  function openOptimize(opts = {}) {
    optimizerOpen.value = true
    let ident = String(opts.taskId || '')
    if (!ident) {
      const list = optimizerItems.value
      ident = list.length ? String(list[0].value) : ''
    }
    const idChanged = optimizerTaskId.value !== ident
    const budChanged = String(optimizerBudget.value ?? '') !== ''
    optimizerTaskId.value = ident
    if (opts.resetBudget !== false) optimizerBudget.value = ''
    // 变化交给 watch 触发一次；都没变（重开同一任务）才显式拉一次，避免重复请求。
    if (!idChanged && !budChanged) loadOptimize()
  }

  watch([optimizerTaskId, optimizerBudget], () => {
    if (optimizerOpen.value) loadOptimize()
  })

  return {
    optimizerOpen, optimizerTaskId, optimizerBudget, optimizerLoading, optimizerData,
    optimizerItems, loadOptimize, openOptimize,
  }
}
