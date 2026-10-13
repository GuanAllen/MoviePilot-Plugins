// MagicFlow 前端 · 标签模型域 composable（★ 3.13.0）
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：① 标签总览（/tags）② 魔力排序规则编辑器（草稿在 settingsDraft.sort_rules）。
// 依赖注入：api、notify、error、settingsDraft（排序规则草稿）。
// ★ 真值源：后端 /tags；本域只放标签相关 UI 状态。
//   （旧「标签迁移」已删：后端 features/migrate.py 于 12.0.0 退役，路由 tags/migrate 早已 404。）
import { ref } from 'vue'
import { SORT_RULE_TYPES } from '../../../utils'

// ★ P4：纯函数 / 常量提到 module 级具名导出，供 dialogs/SettingsDialog.vue 复用（单一真值源）。
export const sortRuleTypeOptions = SORT_RULE_TYPES
export function sortRuleText(r) {
  return (SORT_RULE_TYPES.find(t => t.value === r?.type)?.text) || r?.type || '-'
}
export function sortRuleNeedsMin(type) {
  return !!SORT_RULE_TYPES.find(t => t.value === type)?.min
}

export function useTagModel({ api, notify, error, settingsDraft }) {
  const tagInfo = ref(null)
  const newRuleType = ref('subscribe')
  // ── 标签模型 ─────────────────────────────────────────────
  async function loadTags() {
    try {
      const res = await api.settings.tags()
      tagInfo.value = res?.data || null
    } catch (err) {
      error.value = err?.message || String(err)
    }
  }

  function addSortRule() {
    const t = newRuleType.value
    if (!t) return
    if (!Array.isArray(settingsDraft.value.sort_rules)) settingsDraft.value.sort_rules = []
    if (settingsDraft.value.sort_rules.some(r => r.type === t)) {
      notify('该规则已存在')
      return
    }
    const meta = SORT_RULE_TYPES.find(x => x.value === t) || {}
    const row = { type: t, weight: 50, enabled: true }
    if (meta.min) row.min = meta.defaultMin ?? 0
    settingsDraft.value.sort_rules.push(row)
  }

  function removeSortRule(i) {
    if (Array.isArray(settingsDraft.value.sort_rules)) settingsDraft.value.sort_rules.splice(i, 1)
  }

  return {
    tagInfo, newRuleType, sortRuleTypeOptions, loadTags, sortRuleText, sortRuleNeedsMin, addSortRule, removeSortRule,
  }
}
