// MagicFlow 前端 · 批量入库域 composable（勾选推荐 → 批量入库）
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：推荐列表里「可手动确认」的行 → 勾选 / 全选 / 批量入库。
// 依赖注入：api、notify、recommendItems（推荐行来源）、recommendActionable（判定可入库）、
//          loadRecommend（入库完刷新推荐列表）。
// ★ 真值源仍在后端（/recommend/batch-import）；本域只放勾选态。
// ★ 说明：recommend* 三件套属于「推荐」域（尚未拆），本域先按参数注入，
//   等推荐域抽成 composable 后再换成「composable 之间调用」。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useRecImport({ api, notify, recommendItems, recommendActionable, loadRecommend }) {
  const recSelected = ref({})        // hash -> true
  const recBatchActing = ref(false)
  // 可勾选/入库的行 = 可手动确认的那些
  const recSelectable = computed(() => recommendItems.value.filter(r => recommendActionable(r)))
  const recSelectedList = computed(() => recSelectable.value.filter(r => recSelected.value[r.hash]).map(r => r.hash))
  const recAllChecked = computed(() => recSelectable.value.length > 0 && recSelectedList.value.length === recSelectable.value.length)
  function toggleRec(hash) {
    recSelected.value = { ...recSelected.value, [hash]: !recSelected.value[hash] }
  }
  function toggleAllRecs() {
    const flag = !recAllChecked.value
    const m = { ...recSelected.value }
    recSelectable.value.forEach(r => { m[r.hash] = flag })
    recSelected.value = m
  }
  async function batchImportRecommend(useAll) {
    if (recBatchActing.value) return
    const list = useAll ? [] : recSelectedList.value
    if (!useAll && !list.length) return
    recBatchActing.value = true
    try {
      const qs = useAll ? 'all=1' : `hashes=${encodeURIComponent(list.join(','))}`
      const data = unwrapResponse(await api.features.recommendBatchImport(qs)) || {}
      notify(data.message || '批量入库完成')
      recSelected.value = {}
      await loadRecommend()
    } catch (err) {
      notify(err?.response?.data?.message || err?.message || '批量入库失败', 'error')
    } finally {
      recBatchActing.value = false
    }
  }

  return {
    recSelected, recBatchActing, recSelectable, recSelectedList, recAllChecked, toggleRec, toggleAllRecs, batchImportRecommend,
  }
}
