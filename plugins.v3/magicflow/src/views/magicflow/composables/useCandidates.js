// MagicFlow 前端 · useCandidates 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：candidateData（真值源在 useTaskDetail，本域只放 UI 派生状态与切换）。
import { computed, ref } from 'vue'

export function useCandidates({ candidateData }) {
  const poolView = ref('candidates')
  const reasonEntries = computed(() => {
    const counts = candidateData.value.reason_counts || {}
    return Object.entries(counts)
      .map(([label, count]) => ({ label, count: Number(count) || 0 }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8)
  })
  const maxReasonCount = computed(() => Math.max(1, ...reasonEntries.value.map(item => item.count)))
  const candidateRawTotal = computed(() => {
    const rejected = Object.values(candidateData.value.reason_counts || {}).reduce((sum, value) => sum + (Number(value) || 0), 0)
    return (candidateData.value.candidates || []).length + rejected
  })

  return {
    candidateRawTotal,
    maxReasonCount,
    poolView,
    reasonEntries,
  }
}
