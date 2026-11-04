// MagicFlow 前端 · 操作记录展示纯函数（S14 / F6）
// 这 9 个函数原先在**三处**逐字重复：composables/useOperations.js、
// components/dialogs/OpsDialog.vue、components/tabs/JournalTab.js。
// 三份一旦分叉，同一个操作记录在三个入口显示的图标/颜色/耗时就会不一致，
// 故抽到这里作为唯一实现；三处各自 import，本地不再留副本。
//
// 边界（别顺手扩大）：只搬纯函数。
//   · isOpDetailOpen 不搬 —— 两处数据源不同（OpsDialog 读 props.expandedOps，JournalTab 读 data.expandedOps）
//   · eventLevelIcon / taskLabel 只有 OpsDialog 用（taskLabel 在 useOperations 里另有依赖注入版本）
//   · 组件与 CSS 不动 —— `.magicflow-events*` 两份样式已按容器作用域分叉，合并等于改样式
import { ITEM_SOURCE_TEXT, KIND_ICON, KIND_TEXT, STATE_TEXT } from './constants'
import { formatDuration, formatDurationSeconds } from '../../utils'

export function operationKindText(kind) {
  return KIND_TEXT[kind] || kind
}

export function operationStateText(state) {
  return STATE_TEXT[state] || state
}

export function operationIcon(kind) {
  return KIND_ICON[kind] || 'mdi-circle-small'
}

export function operationColor(record) {
  if (record.state === 'failed') return 'error'
  if (record.kind === 'deletion') return 'warning'
  if (record.kind === 'tag') return 'purple'
  if (record.kind === 'run') return 'secondary'
  return 'primary'
}

export function opDetailItems(record) {
  if (!record) return []
  return (record.items || []).filter((it) => String((it && it.source) || '') !== 'run')
}

export function hasOpDetail(record) {
  return opDetailItems(record).length > 0
}

export function itemSourceText(src) {
  return ITEM_SOURCE_TEXT[src] || ''
}

export function operationDuration(record) {
  if (record.duration != null && Number(record.duration) > 0) return formatDurationSeconds(record.duration)
  return formatDuration(record.created_at, record.resolved_at)
}

export function operationSummary(record) {
  const first = (record.items || [])[0]
  if (first && first.title) return first.title
  const count = (record.items || []).length
  return count ? `${count} 个条目` : ''
}
