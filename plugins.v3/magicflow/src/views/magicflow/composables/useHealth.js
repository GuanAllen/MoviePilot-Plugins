// MagicFlow 前端 · 健康自检域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：健康自检弹窗状态 + 拉取 + 徽标/文案派生 + 点问题跳任务。
// 依赖注入：api（createApi 客户端）、selectTask（点问题 → 切到该任务）。
// ★ 真值源仍在后端（/health，零外部请求）。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useHealth({ api, selectTask }) {
  // ── 健康自检（可观测③）：零外部请求，只看本地任务状态 + 趋势 ─────────
  const healthOpen = ref(false)
  const healthData = ref({ level: 'ok', ok: true, counts: {}, issues: [] })
  const healthColor = computed(() => {
    const lv = healthData.value?.level || 'ok'
    if (lv === 'error') return 'error'
    if (lv === 'warning') return 'warning'
    if (lv === 'info') return 'info'
    return undefined
  })
  const healthBadgeCount = computed(() => {
    const c = healthData.value?.counts || {}
    return Number(c.error || 0) + Number(c.warning || 0)
  })
  const healthLabel = computed(() => {
    const d = healthData.value || {}
    const c = d.counts || {}
    if (d.level === 'error') return `健康：${c.error || 0} 项错误`
    if (d.level === 'warning') return `健康：${c.warning || 0} 项告警`
    if (d.level === 'info') return `健康：${c.info || 0} 条提示`
    return '健康：全部正常'
  })
  async function loadHealth() {
    try {
      healthData.value = unwrapResponse(await api.pool.health())
        || { level: 'ok', ok: true, counts: {}, issues: [] }
    } catch (err) {
      // 自检是增强信息，失败不打断界面
    }
  }
  function openHealth() {
    healthOpen.value = true
    loadHealth()
  }
  function healthGoto(issue) {
    if (issue?.task_id) selectTask(issue.task_id)
    healthOpen.value = false
  }

  return {
    healthOpen, healthData, healthColor, healthBadgeCount, healthLabel,
    loadHealth, openHealth, healthGoto,
  }
}
