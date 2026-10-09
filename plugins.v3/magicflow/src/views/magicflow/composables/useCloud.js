// MagicFlow 前端 · useCloud 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api, error, notify（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed, onUnmounted, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

// 纯函数：按 path 在记录数组里查找对应项（弹窗组件具名导入复用；单一真值源）。
export function pickCloudRecord(records, item) {
  const key = String((item || {}).path || '')
  return (records || []).find(r => String(r?.path || '') === key) || null
}

export function useCloud({ api, error, notify }) {
  const cloudOpen = ref(false)
  const cloudState = ref(null)
  const cloudLoading = ref(false)
  const cloudPlanning = ref(false)
  const cloudRunning = ref(false)
  const cloudTesting = ref(false)
  const cloudTestMsg = ref('')
  const cloudTestOk = ref(false)
  const cloudLimit = ref(50)
  const cloudUploadingPath = ref('')
  const cloudPlanItems = ref([])
  const cloudPlanStats = ref(null)
  const cloudCfg = computed(() => (cloudState.value || {}).cfg || {})
  async function loadCloud() {
    cloudLoading.value = true
    try {
      cloudState.value = unwrapResponse(await api.features.cloud())
      if (!cloudPlanStats.value) cloudPlanStats.value = (cloudState.value?.plan_stats || null)
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      cloudLoading.value = false
    }
  }
  async function testCloud() {
    cloudTesting.value = true
    cloudTestMsg.value = ''
    try {
      const res = unwrapResponse(await api.features.cloudTest())
      cloudTestOk.value = Boolean(res?.ok)
      cloudTestMsg.value = res?.ok
        ? `连通正常 · 源挂载 ${res.source_items ?? '?'} 项 · strm 视图 ${res.strm_items ?? '?'} 项`
        : (res?.message || '连接失败')
    } catch (err) {
      cloudTestOk.value = false
      cloudTestMsg.value = err?.message || String(err)
    } finally {
      cloudTesting.value = false
    }
  }
  async function planCloud() {
    cloudPlanning.value = true
    try {
      const res = unwrapResponse(await api.features.cloudPlan(cloudLimit.value || 50))
      cloudPlanItems.value = res?.items || []
      cloudPlanStats.value = res?.stats || null
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      cloudPlanning.value = false
    }
  }
  async function uploadCloudOne(item) {
    if (!item?.path) return
    cloudUploadingPath.value = item.path
    try {
      const res = unwrapResponse(await api.features.cloudUpload(item.path))
      item.status = res?.status || 'uploading'
      item.message = res?.message || ''
      notify(item.message || '已开始上传')
      scheduleCloudPoll()
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      cloudUploadingPath.value = ''
    }
  }
  let cloudPollTimer = null
  function scheduleCloudPoll() {
    if (cloudPollTimer) return
    cloudPollTimer = window.setInterval(async () => {
      await loadCloud()
      const records = (cloudState.value || {}).records || []
      const uploading = records.some(r => r?.status === 'uploading')
      if (!uploading && !(cloudState.value || {}).running) {
        window.clearInterval(cloudPollTimer)
        cloudPollTimer = null
      }
    }, 6000)
  }
  function cloudRecordFor(item) {
    return pickCloudRecord((cloudState.value || {}).records || [], item)
  }
  async function runCloud(dryRun = true) {
    cloudRunning.value = true
    try {
      const res = unwrapResponse(await api.features.cloudRun(dryRun, cloudLimit.value || 50))
      notify(res?.message || (dryRun ? '归档演练已开始' : '归档任务已开始'))
      setTimeout(() => { loadCloud() }, 3000)
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      cloudRunning.value = false
    }
  }
  function openCloud() {
    cloudOpen.value = true
    loadCloud()
  }
  onUnmounted(() => {
    if (cloudPollTimer) window.clearInterval(cloudPollTimer)
  })


  return {
    cloudCfg,
    cloudLimit,
    cloudLoading,
    cloudOpen,
    cloudPlanItems,
    cloudPlanStats,
    cloudPlanning,
    cloudPollTimer,
    cloudRecordFor,
    cloudRunning,
    cloudState,
    cloudTestMsg,
    cloudTestOk,
    cloudTesting,
    cloudUploadingPath,
    loadCloud,
    openCloud,
    planCloud,
    runCloud,
    scheduleCloudPoll,
    testCloud,
    uploadCloudOne,
  }
}
