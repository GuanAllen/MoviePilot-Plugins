// MagicFlow 前端 · 后台任务队列（★ 15.10.0）
// Master：「转圈圈这里，如果我关掉页面是不是就断了，建议加个队列后台跑…推荐那里入库也是这个情况」
// → 后端把慢动作入队；这里只负责**看**（列表/计数/清理），并给菜单显示「进行中 N」。
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useJobs({ api, notify }) {
  const jobsOpen = ref(false)
  const jobs = ref([])
  const jobsSummary = ref({})
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

  function openJobs() {
    jobsOpen.value = true
    loadJobs()
  }

  onMounted(() => {
    loadJobs()
    slow = window.setInterval(loadJobs, 20000)   // 常驻慢轮询（只为菜单角标）
  })
  onUnmounted(() => {
    if (slow) window.clearInterval(slow)
    if (fast) window.clearInterval(fast)
  })
  // 弹窗打开 → 4s 快刷，实时看进度
  watch(jobsOpen, value => {
    if (fast) { window.clearInterval(fast); fast = null }
    if (value) {
      loadJobs()
      fast = window.setInterval(loadJobs, 4000)
    }
  })

  return { jobsOpen, jobs, jobsSummary, jobsRunning, loadJobs, clearJobs, openJobs }
}
