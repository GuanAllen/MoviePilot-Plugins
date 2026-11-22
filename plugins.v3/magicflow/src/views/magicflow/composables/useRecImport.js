// MagicFlow 前端 · 批量入库域 composable（勾选推荐 → 批量入库）
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：推荐列表里「可手动确认」的行 → 勾选 / 全选 / 批量入库。
// 依赖注入：api、notify、allItems（去重后的全量推荐行）、recommendActionable（判定可入库）、
//          loadRecommend（入库完刷新推荐列表）。
// ★ 真值源仍在后端（/recommend/batch-import）；本域只放勾选态。
// ★ 19.12.90：勾选池从「推荐域已按状态过滤的列表」改成「去重后的全量」——
//   移动端改版后「未达门槛」那 27 条也要能勾（它们本来就能入库，只是没自动推荐）；
//   全选也改成只作用于「当前筛选下可见的那批 hash」，不再等于全库可入库行。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useRecImport({ api, notify, allItems, recommendActionable, loadRecommend }) {
  const recSelected = ref({})        // hash -> true
  const recBatchActing = ref(false)
  // 可勾选/入库的行 = 可手动确认的那些（待确认 + 未达门槛里非「已在库」的）
  const recSelectable = computed(() => (allItems.value || []).filter(r => recommendActionable(r)))
  const recSelectedList = computed(() => recSelectable.value.filter(r => recSelected.value[r.hash]).map(r => r.hash))
  function toggleRec(hash) {
    recSelected.value = { ...recSelected.value, [hash]: !recSelected.value[hash] }
  }
  // 按给定 hash 批量置位（「全选」只作用于当前筛选下的可见行）
  function setRecSelection(hashes, flag) {
    const pool = (hashes || []).map(h => String(h || '')).filter(Boolean)
    if (!pool.length) return
    const m = { ...recSelected.value }
    for (const h of pool) {
      if (flag) m[h] = true
      else delete m[h]
    }
    recSelected.value = m
  }
  function toggleAllRecs(hashes) {
    const list = Array.isArray(hashes) && hashes.length ? hashes : recSelectable.value.map(r => r.hash)
    const allOn = list.every(h => !!recSelected.value[h])
    setRecSelection(list, !allOn)
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
    recSelected, recBatchActing, recSelectedList,
    toggleRec, toggleAllRecs, batchImportRecommend,
  }
}
