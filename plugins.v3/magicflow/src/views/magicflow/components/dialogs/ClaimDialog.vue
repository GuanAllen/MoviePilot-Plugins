<script setup>
// MagicFlow 前端 · 认领弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调用父方法。
import { ref } from 'vue'

// 开关：父 v-model="claimOpen"（子不改父状态）。
const claimOpen = defineModel({ type: Boolean, default: false })

// 数据向下（只读）：claimData 为原始后端状态，其余为父页派生数组（单一真值源在父页）。
const props = defineProps({
  isNarrow: { type: Boolean, default: false },
  claimData: { type: Object, default: () => ({}) },
  claimCfg: { type: Object, default: () => ({}) },
  claimSites: { type: Array, default: () => [] },
  claimSupportedSites: { type: Array, default: () => [] },
  claimClaimable: { type: Array, default: () => [] },
  claimClaimed: { type: Array, default: () => [] },
  claimSoon: { type: Array, default: () => [] },
  claimLoading: { type: Boolean, default: false },
  claimActing: { type: String, default: '' },
})

const emit = defineEmits(['refresh', 'scan', 'ask'])

// 侧栏子标签页：纯组件内部 UI 状态（父页无引用）→ 随弹窗自 index.vue 迁入。
const claimTab = ref('claimable')

// ── 展示用纯函数（随弹窗自 index.vue 迁入；数据经 props 下行，函数在组件内自持，
//    不向上传函数，避免 Function prop）──
function claimTotal() { return Number(props.claimData.claimed_total || 0) }
function claimRequestable() { return Number(props.claimData.claimable_total || 0) }
function claimAgeText(v) { return (v === null || v === undefined) ? '—' : `${Number(v).toFixed(1)} 天` }
function claimSeedersText(n) { return (n === undefined || n === null || Number(n) < 0) ? '—' : String(n) }
// ★ 站点认领画像（后端 sites[].profile：supported / min_age_days / max_claimers /
//   per_user_cap / benefit(_desc) / penalty / reason）。
function claimProfile(s) { return (s && s.profile) || {} }
function claimPenaltyText(prof) {
  const p = (prof || {}).penalty || {}
  const parts = []
  if (p.unsatisfied) parts.push(`不达标 −${p.unsatisfied}`)
  if (p.abandon) parts.push(`放弃 −${p.abandon}`)
  if (p.exempt_days) parts.push(`首 ${p.exempt_days} 天豁免`)
  return parts.join(' · ') || '—'
}
</script>

<template>
  <VDialog v-model="claimOpen" max-width="52rem" scrollable :fullscreen="isNarrow">
    <VCard class="magicflow-dialog magicflow-claim-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">认领</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" :loading="claimLoading" @click="emit('refresh')">刷新</VBtn>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="claimOpen = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-claim-body">
        <div class="magicflow-claim-hero">
          <div class="magicflow-claim-hero__item"><span class="num">{{ claimTotal() }}</span><span class="cap">已认领</span></div>
          <div class="magicflow-claim-hero__item"><span class="num">{{ claimRequestable() }}</span><span class="cap">当前可认领</span></div>
          <div class="magicflow-claim-hero__item"><span class="num">{{ claimSupportedSites.length }}</span><span class="cap">支持站点</span></div>
          <VSpacer />
          <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-radar" :loading="claimActing === 'run'" @click="emit('scan')">扫描（干跑）</VBtn>
          <VBtn
            v-if="claimCfg.enabled && !claimCfg.dry && claimRequestable()"
            size="small"
            variant="flat"
            color="primary"
            prepend-icon="mdi-seal"
            @click="emit('ask', 'batch', null)"
          >认领本轮 {{ claimRequestable() }} 个</VBtn>
        </div>
        <VAlert v-if="!claimCfg.enabled" type="info" variant="tonal" density="compact" class="mb-2">
          认领默认关闭。开启路径：插件设置 → 认领（开启后仍是干跑，确认链路后再关干跑）。
        </VAlert>
        <VAlert v-else-if="claimCfg.dry" type="warning" variant="tonal" density="compact" class="mb-2">
          当前为「干跑」：只列出可认领的种，**不发任何写请求**（含手动单条）。要实写请到「插件设置 → 认领」关闭「干跑」。
        </VAlert>
        <VAlert type="info" variant="tonal" density="compact" class="mb-2">
          认领 = 保种承诺：认领后的种进硬保护、永不自动删除；站点侧不达标可能扣魔力，主动放弃更亏。
          <template v-if="claimData.benefit_desc">权益：{{ claimData.benefit_desc }}。</template>
        </VAlert>

        <VTabs v-model="claimTab" density="compact" class="mb-1">
          <VTab value="claimable">可认领（{{ claimRequestable() }}）</VTab>
          <VTab value="claimed">已认领（{{ claimTotal() }}）</VTab>
          <VTab value="soon">快到期（{{ claimSoon.length }}）</VTab>
          <VTab value="sites">站点能力（{{ claimSites.length }}）</VTab>
        </VTabs>
        <VWindow v-model="claimTab">
          <VWindowItem value="claimable">
            <div v-if="!claimClaimable.length" class="magicflow-table-empty">当前没有可认领的种（未满发布天数 / 无详情页 / 被安全阀挡住）。</div>
            <ul v-else class="magicflow-claim-list">
              <li v-for="row in claimClaimable" :key="row.hash" class="magicflow-claim-item">
                <div class="magicflow-claim-item__main">
                  <span class="magicflow-claim-item__title">{{ row.title || row.hash }}</span>
                  <span class="magicflow-claim-item__meta">{{ row.site_name }} · {{ row.size_gb }}G · 做种 {{ claimSeedersText(row.seeders) }} · 发布 {{ claimAgeText(row.age_days) }}</span>
                </div>
                <VBtn size="x-small" variant="flat" color="primary" prepend-icon="mdi-seal" :disabled="claimCfg.dry" :loading="claimActing === ('do:' + row.hash)" @click="emit('ask', 'do', row)">认领</VBtn>
              </li>
            </ul>
          </VWindowItem>
          <VWindowItem value="claimed">
            <div v-if="!claimClaimed.length" class="magicflow-table-empty">还没有认领记录。</div>
            <ul v-else class="magicflow-claim-list">
              <li v-for="row in claimClaimed" :key="row.hash" class="magicflow-claim-item is-claimed">
                <div class="magicflow-claim-item__main">
                  <span class="magicflow-claim-item__title">{{ row.title || row.hash }}</span>
                  <span class="magicflow-claim-item__meta">{{ row.site_name }} · {{ row.benefit || '权益' }} · {{ row.state }} <template v-if="row.note">· {{ row.note }}</template></span>
                </div>
                <VChip size="x-small" color="success" variant="tonal" prepend-icon="mdi-shield-lock-outline">硬保护</VChip>
              </li>
            </ul>
          </VWindowItem>
          <VWindowItem value="soon">
            <div v-if="!claimSoon.length" class="magicflow-table-empty">没有临近可认领的种。</div>
            <ul v-else class="magicflow-claim-list">
              <li v-for="row in claimSoon" :key="row.hash" class="magicflow-claim-item is-dim">
                <div class="magicflow-claim-item__main">
                  <span class="magicflow-claim-item__title">{{ row.title || row.hash }}</span>
                  <span class="magicflow-claim-item__meta">{{ row.site_name }} · 发布 {{ claimAgeText(row.age_days) }} · {{ (row.block || []).join(' / ') }}</span>
                </div>
              </li>
            </ul>
          </VWindowItem>
          <VWindowItem value="sites">
            <div v-if="!claimSites.length" class="magicflow-table-empty">没有启用中的任务站点。</div>
            <ul v-else class="magicflow-claim-list">
              <li v-for="s in claimSites" :key="s.site_id" class="magicflow-claim-item">
                <div class="magicflow-claim-item__main">
                  <span class="magicflow-claim-item__title">{{ s.site_name }} <small class="is-dim">{{ s.domain }}</small></span>
                  <span v-if="s.supported" class="magicflow-claim-item__meta">
                    满 {{ claimProfile(s).min_age_days }} 天可认领 · 每颗 {{ claimProfile(s).max_claimers }} 名额 · 每人上限 {{ claimProfile(s).per_user_cap }}
                    · {{ claimProfile(s).benefit_desc || claimProfile(s).benefit }} · {{ claimPenaltyText(claimProfile(s)) }}
                  </span>
                  <span v-else class="magicflow-claim-item__meta">{{ claimProfile(s).reason || '暂不支持认领' }}</span>
                </div>
                <div class="magicflow-claim-item__stat">
                  <VChip size="x-small" variant="tonal">{{ s.claimed || 0 }} 已认领</VChip>
                  <VChip size="x-small" variant="tonal" color="primary">{{ s.claimable || 0 }} 可认领</VChip>
                </div>
              </li>
            </ul>
          </VWindowItem>
        </VWindow>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 正文：随「认领」弹窗自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head(` i`) / settings-dialog__title /
     recommend-dialog__head-actions / table-empty）父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。
     VDialog 会 teleport 到 body，父 scoped 够不到子内部，故须自带。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}
.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.magicflow-settings-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
}
.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
}
.magicflow-recommend-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

/* ── 认领弹窗（专属选择器，随弹窗自 index.vue 迁入并从 index.vue 删除）── */
.magicflow-claim-hero { display: flex; align-items: center; gap: 18px; padding: 4px 2px 12px; flex-wrap: wrap; }
.magicflow-claim-hero__item { display: flex; flex-direction: column; line-height: 1.1; }
.magicflow-claim-hero__item .num { font-size: 1.35rem; font-weight: 700; }
.magicflow-claim-hero__item .cap { font-size: .72rem; opacity: .62; }
.magicflow-claim-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.magicflow-claim-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
}
.magicflow-claim-item.is-claimed { border-color: rgba(var(--v-theme-success), .35); }
.magicflow-claim-item.is-dim { opacity: .7; }
.magicflow-claim-item__main { display: flex; flex-direction: column; min-width: 0; flex: 1 1 auto; gap: 2px; }
.magicflow-claim-item__title { font-size: .82rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-claim-item__meta { font-size: .7rem; opacity: .62; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-claim-item__stat { display: flex; gap: 4px; flex: 0 0 auto; }
</style>
