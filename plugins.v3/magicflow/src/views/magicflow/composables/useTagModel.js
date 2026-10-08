// MagicFlow 前端 · 标签模型域 composable（★ 3.13.0）
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：① 标签总览（/tags）② 魔力排序规则编辑器（草稿在 settingsDraft.sort_rules）
//      ③ 老标签 →「魔流-站点-状态」新命名的迁移（预演 / 应用）。
// 依赖注入：api、notify、error、settingsDraft（排序规则草稿）、emit（迁完通知父组件 action）。
// ★ 真值源：后端 /tags 与 /tags/migrate/*；本域只放标签相关 UI 状态。
import { ref } from 'vue'
import { SORT_RULE_TYPES } from '../../../utils'

export function useTagModel({ api, notify, error, settingsDraft, emit }) {
  const tagInfo = ref(null)
  const tagMigratePlan = ref(null)
  const tagMigrating = ref(false)
  const newRuleType = ref('subscribe')
  const sortRuleTypeOptions = SORT_RULE_TYPES
  // ── 标签模型 ─────────────────────────────────────────────
  async function loadTags() {
    try {
      const res = await api.settings.tags()
      tagInfo.value = res?.data || null
    } catch (err) {
      error.value = err?.message || String(err)
    }
  }

  function sortRuleText(r) {
    return (SORT_RULE_TYPES.find(t => t.value === r?.type)?.text) || r?.type || '-'
  }

  function sortRuleNeedsMin(type) {
    return !!SORT_RULE_TYPES.find(t => t.value === type)?.min
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

  async function previewTagMigrate() {
    tagMigrating.value = true
    try {
      const res = await api.settings.tagMigratePlan()
      tagMigratePlan.value = res?.data || null
      await loadTags()
    } catch (err) {
      alert(`迁移预演失败: ${err?.message || err}`)
    } finally {
      tagMigrating.value = false
    }
  }

  async function applyTagMigrate() {
    const total = tagMigratePlan.value?.total || 0
    if (!total) return
    if (!confirm(`确认把 ${total} 个托管种子的老标签迁移到「魔流-站点-状态」新命名？\n（保留 已整理/辅种 等外来标签）`)) return
    tagMigrating.value = true
    try {
      const res = await api.settings.tagMigrateApply()
      notify(res?.message || '迁移完成')
      tagMigratePlan.value = null
      await loadTags()
      emit('action')
    } catch (err) {
      alert(`迁移失败: ${err?.message || err}`)
    } finally {
      tagMigrating.value = false
    }
  }

  return {
    tagInfo, tagMigratePlan, tagMigrating, newRuleType, sortRuleTypeOptions, loadTags, sortRuleText, sortRuleNeedsMin, addSortRule, removeSortRule, previewTagMigrate, applyTagMigrate,
  }
}
