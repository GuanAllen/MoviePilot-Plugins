// MagicFlow 前端 · 后台任务队列（★ 15.10.0）
// Master：「转圈圈这里，如果我关掉页面是不是就断了，建议加个队列后台跑…推荐那里入库也是这个情况」
// → 后端把慢动作入队；这里只负责**看**（列表/计数/清理/重试），并给菜单显示「进行中 N」。
// ★ 19.12.98：多两样东西 —— `batches`（一次批量一行汇总）和 `retryJobs`（重试失败）。
import { startPolling, stopPolling } from '../../../polling'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useJobs({ api, notify }) {
  const jobsOpen = ref(false)
  const jobs = ref([])
  const jobsSummary = ref({})
  const jobsBatches = ref([])
  let slow = null
  let fast = null

  const jobsRunning = computed(
    () => Number(jobsSummary.value.running ?? 0) + Number(jobsSummary.value.queued ?? 0),
  )

  async function loadJobs() {
    try {
      const data = unwrapResponse(await api.jobs.getJobs(60)) || {}
      jobs.value = Array.isArray(data.items) ? data.items : []
      jobsSummary.value = data.summary || {}
      jobsBatches.value = Array.isArray(data.batches) ? data.batches : []
    } catch (err) {
      // 队列读不到不影响主流程：静默（打开弹窗时手动刷新会再报）
    }
  }

  async function clearJobs() {
    try {
      const data = unwrapResponse(await api.jobs.clearJobs()) || {}
      notify(data.message || '已清理历史任务')
      await loadJobs()
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '清理失败', 'error')
    }
  }

  /**
   * ★ 19.12.98：重试失败任务（单条 / 一批 / 按种类）。
   * 失败时把后端原文报出来 —— 「跳过 N 条」的原因必须能看见，否则用户只会觉得点了没反应。
   */
  async function retryJobs(payload = {}) {
    try {
      const data = unwrapResponse(await api.jobs.retryJobs(payload)) || {}
      notify(data.message || '已提交重试')
      await loadJobs()
      return data
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '重试失败', 'error')
      return null
    }
  }

  function openJobs() {
    jobsOpen.value = true
    loadJobs()
  }

  onMounted(() => {
    loadJobs()
    slow = startPolling(loadJobs, 20000)   // 常驻慢轮询（只为菜单角标）
  })
  onUnmounted(() => {
    if (slow) stopPolling(slow)
    if (fast) stopPolling(fast)
  })
  // 弹窗打开 → 4s 快刷，实时看进度
  watch(jobsOpen, value => {
    if (fast) { stopPolling(fast); fast = null }
    if (value) {
      loadJobs()
      fast = startPolling(loadJobs, 4000)
    }
  })

  return {
    jobsOpen, jobs, jobsSummary, jobsBatches, jobsRunning,
    loadJobs, clearJobs, retryJobs, openJobs,
  }
}
