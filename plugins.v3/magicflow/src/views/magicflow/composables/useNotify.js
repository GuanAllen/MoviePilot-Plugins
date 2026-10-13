// MagicFlow 前端 · 事件通知（★ 15.13.0）
// Master 22:42「全部」→ 批次②：四类事件（H&R 临期 / 容量红线 / 产出骤降 / 任务失败）推到 MP 通知渠道。
import { onUnmounted, ref, watch } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useNotify({ api, notify }) {
  const notifyOpen = ref(false)
  const notifyData = ref(null)
  const notifyLoading = ref(false)
  let timer = null

  async function loadNotify() {
    if (!notifyOpen.value) return
    notifyLoading.value = true
    try {
      const data = unwrapResponse(await api.notify.getNotify(60)) || {}
      notifyData.value = data
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '通知状态读取失败', 'error')
    } finally {
      notifyLoading.value = false
    }
  }

  async function notifyAct(action, text = '') {
    try {
      const data = unwrapResponse(await api.notify.actNotify(action, text)) || {}
      notify(data.message || '已执行')
      await loadNotify()
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '通知动作失败', 'error')
    }
  }

  function openNotify() {
    notifyOpen.value = true
    loadNotify()
  }

  watch(notifyOpen, value => {
    if (timer) {
      window.clearInterval(timer)
      timer = null
    }
    if (value) {
      loadNotify()
      timer = window.setInterval(loadNotify, 10000)
    }
  })

  onUnmounted(() => {
    if (timer) window.clearInterval(timer)
  })

  return { notifyOpen, notifyData, notifyLoading, loadNotify, notifyAct, openNotify }
}
