// MagicFlow 前端 · 静默不变量收敛 / 标签↔账本对账域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：①「静默不变量收敛」= 账本静默但 qB 没停 → 补 pause（★ 只 pause，不删种、不动文件）；
//      ②「标签 ↔ 账本对账」（★ 15.2.0，与 /agent/tags/reconcile 同一实现，人机同源）。
// 依赖注入：api、notify、loadSilent（确认后刷新静默池）、silentOpen（静默池是否开着）。
// ★ 真值源仍在后端（/tags/reconcile、/silent/enforce）；本域只放 UI 状态与动作。
// ★ tsText（秒/毫秒/ISO → MM-DD HH:mm）是通用格式化 → 已提到 ../format.js。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useInvariant({ api, notify, loadSilent, silentOpen }) {
  // ★ 不变量收敛弹窗开关（模板 v-model）——2026-10-08 修：此前该标识符**从未声明**，
  //   模板 `invariantOpen = true` 落到 render 代理上（非响应式）→ 按钮点了弹窗永远不开。
  const invariantOpen = ref(false)
  const enforceLoading = ref(false)
  const enforceAsk = ref(false)
  const enforceData = ref({ scanned: 0, violations: 0, paused: 0, failed: 0, items: [] })
  const enforceCounts = computed(() => enforceData.value || {})
  // ★ 15.2.0 标签 ↔ 账本对账（与 /agent/tags/reconcile 同一实现，人机同源）
  const tagReconLoading = ref(false)
  const tagReconAsk = ref(false)
  const tagReconPending = ref(0)
  async function runTagReconcile(confirm = false) {
    tagReconLoading.value = true
    try {
      const res = unwrapResponse(await api.settings.tagReconcile(confirm)) || {}
      const pend = res.items_total ?? (res.items || []).length
      tagReconPending.value = pend
      const drift = res.drift_total ?? (res.drift || []).length
      if (confirm) {
        tagReconAsk.value = false
        notify(`标签对账：已补 ${res.repaired ?? 0} 个标签` +
          (res.adopted ? `、补登辅种副本 ${res.adopted} 个` : '') +
          (drift ? `（另有身份子桶漂移 ${drift} 个，只报不写）` : ''))
        if (silentOpen.value) loadSilent()
      } else if (pend) {
        tagReconAsk.value = true
      } else {
        notify(`标签对账（干跑）：无需修复` + (drift ? `（身份子桶漂移 ${drift} 个，只报不写）` : ''))
      }
    } catch (err) {
      notify(`标签对账失败：${err?.message || err}`, 'error')
    } finally {
      tagReconLoading.value = false
    }
  }

  async function loadEnforce(confirm = 0) {
    enforceLoading.value = true
    try {
      const res = unwrapResponse(await api.poolstats.silentEnforce(confirm)) || {}
      enforceData.value = res
      notify(res.message || (confirm ? '已补 pause' : '干跑完成'))
      if (confirm) loadSilent()
    } catch (err) {
      notify(`静默不变量收敛失败：${err?.message || err}`, 'error')
    } finally {
      enforceLoading.value = false
    }
  }

  return {
    invariantOpen, enforceLoading, enforceAsk, enforceCounts, tagReconLoading, tagReconAsk, tagReconPending, runTagReconcile, loadEnforce,
  }
}
