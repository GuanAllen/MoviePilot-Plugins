// MagicFlow 前端 · useWorkbench 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：props（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { ref } from 'vue'

export function useWorkbench({ props }) {
  const selectedTaskId = ref('')
  const activeTab = ref(props.initialTab || 'overview')
  const mobileView = ref('list') // 'list' | 'detail'
  const isNarrow = ref(typeof window !== 'undefined' ? window.matchMedia('(max-width: 959px)').matches : false)
  const mhOpen = ref({ need: true, live: true, rest: false })
  const ceilingOpen = ref(false)
  const mhSiteOpen = ref({})

  return {
    activeTab,
    ceilingOpen,
    isNarrow,
    mhOpen,
    mhSiteOpen,
    mobileView,
    selectedTaskId,
  }
}
