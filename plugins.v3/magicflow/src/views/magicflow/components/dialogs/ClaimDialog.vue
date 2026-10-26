<script setup>
// MagicFlow 前端 · 认领弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调用父方法。
import { computed, ref } from 'vue'

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

// 站点筛选（下拉选站）：单站看该站认领详情，全部站点看各站详情汇总。
// 纯组件内部 UI 状态（父页无引用）→ 随弹窗自 index.vue 迁入。
const claimSiteFilter = ref('')
const claimFilterItems = computed(() => [
  { title: '全部站点', value: '' },
  ...(props.claimSites || []).map((s) => ({
    title: `${s.site_name || s.domain}${s.supported ? '' : '（未收录）'}`,
    value: String(s.site_id),
  })),
])
function claimFilterSite() {
  if (!claimSiteFilter.value) return null
  return (props.claimSites || []).find((s) => String(s.site_id) === claimSiteFilter.value) || null
}
// 站点列表：只列支持认领的站。全部站点时逐站汇总，不跨站求和。
const claimSupportedList = computed(() => (props.claimSites || []).filter((s) => s.supported))
const claimScopeSite = computed(() => claimFilterSite())
// 站点自己的结算口径（不再跨站取「最近日期」或最高倍率）。
function claimSiteSettle(s) { return (s && s.settlement) || {} }
// 结算日期文案：「11 月 1 日 · 剩 14.5 天 · 每月结算（自然月）」。
function claimSiteDateText(s) {
  const st = claimSiteSettle(s)
  if (!st.next_settle_at) return '结算日待定'
  const d = new Date(st.next_settle_at * 1000)
  const dateText = `${d.getMonth() + 1} 月 ${d.getDate()} 日`
  const left = (st.days_left === null || st.days_left === undefined) ? '' : `剩 ${Number(st.days_left).toFixed(1)} 天`
  return [dateText, left].filter(Boolean).join(' · ')
}
function claimSiteCycleText(s) { return claimSiteSettle(s).cycle_text || '结算周期待定' }
function claimSiteById(id) { return (props.claimSites || []).find(s => String(s.site_id) === String(id)) || null }
function claimSiteReward(s) {
  if (!s) return '—'
  const rows = (props.claimClaimed || []).filter(r => String(r.site_id) === String(s.site_id) && r.site_reward_num != null)
  if (rows.length) {
    const total = rows.reduce((a, r) => a + (Number(r.site_reward_num) || 0), 0)
    if (total > 0) return claimNum(total)
  }
  const p = claimProfile(s)
  return p.benefit === 'bonus_x2' ? '×2' : (p.benefit || '—')
}
function claimRowSettleText(row) {
  const s = claimSiteById(row.site_id)
  return s ? claimSiteDateText(s) : (row.site_next_settle || '—')
}
function claimRowReward(row) {
  if (row.site_reward) return row.site_reward
  const s = claimSiteById(row.site_id)
  const p = s ? claimProfile(s) : {}
  return p.benefit === 'bonus_x2' ? '×2' : (p.benefit || '—')
}
// 配比规则（单站口径）。
function claimRuleText(s) {
  const st = claimSiteSettle(s)
  if (!st.cycle_text) return ''
  const parts = [st.cycle_text]
  if (Number(st.payout_multiplier) > 1) parts.push(`达标魔力 ×${st.payout_multiplier}`)
  if (Number(st.target_seed_hours) > 0) parts.push(`月做种 ≥${st.target_seed_hours}h`)
  if (Number(st.target_upload_ratio) > 0) parts.push(`或上传 ≥${st.target_upload_ratio}×体积`)
  return parts.join(' · ')
}
// 列表按选中站点过滤；未选站 = 全部。
function claimRowsFor(rows, siteId) {
  const list = rows || []
  if (!siteId) return list
  return list.filter((r) => String(r.site_id) === String(siteId))
}
const claimFilteredClaimable = computed(() => claimRowsFor(props.claimClaimable, claimSiteFilter.value))
const claimFilteredClaimed = computed(() => claimRowsFor(props.claimClaimed, claimSiteFilter.value))
const claimFilteredSoon = computed(() => claimRowsFor(props.claimSoon, claimSiteFilter.value))
// 多站大量种子时列表只渲染前 50 条（总量与收益在报表里，列表只是操作入口）。
const CLAIM_LIST_SHOWN = 50
const claimClaimedLimit = ref(20)
const claimClaimableLimit = ref(20)
const claimShownClaimed = computed(() => claimFilteredClaimed.value.slice(0, claimClaimedLimit.value))
const claimShownClaimable = computed(() => claimFilteredClaimable.value.slice(0, claimClaimableLimit.value))
function claimMoreClaimed() { claimClaimedLimit.value += 20 }
function claimMoreClaimable() { claimClaimableLimit.value += 20 }
const claimListTab = ref('claimed')
const claimSummaryClaimed = computed(() => claimFilteredClaimed.value.length)
const claimSummaryReward = computed(() => {
  let n = 0
  for (const r of claimFilteredClaimed.value) {
    const v = Number(r.site_reward_num)
    if (Number.isFinite(v)) n += v
  }
  return n
})
const claimSummaryRewardText = computed(() => claimSummaryReward.value > 0 ? claimNum(claimSummaryReward.value) : '—')
const claimSummarySettle = computed(() => {
  if (claimScopeSite.value) return claimSiteDateText(claimScopeSite.value)
  const rows = (props.claimSites || []).filter(s => s.supported && s.settlement && s.settlement.next_settle_at)
  if (!rows.length) return '—'
  const min = Math.min(...rows.map(s => Number(s.settlement.next_settle_at)))
  const s = rows.find(x => Number(x.settlement.next_settle_at) === min)
  return s ? claimSiteDateText(s) : '—'
})
function claimNum(v) { return Number(v || 0).toLocaleString('zh-CN') }
// ── 展示用纯函数（随弹窗自 index.vue 迁入；数据经 props 下行，函数在组件内自持，
//    不向上传函数，避免 Function prop）──
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
// ★ 认领「入口」文案（2026-10-18 Master 指出：一部分站入口在个人详情页，学校在种子详情页）。
function claimEntryText(s) {
  const p = claimProfile(s) || {}
  const entry = String(p.claim_entry || '').trim()
  if (entry.includes('viewclaims')) return '种子详情页「认领」→ viewclaims.php（已认领列表）'
  if (entry.includes('userdetails')) return '个人详情页「认领: [n/N]」配额；实际认领在种子详情页'
  if (entry) return entry
  return '种子详情页「认领」按钮'
}
// ★ 单站结算口径文案（结算日 / 周期 / 倍率）。
function claimSettlementText(s) {
  const st = claimSiteSettle(s)
  if (!st.cycle_text) return ''
  const parts = [st.cycle_text]
  if (st.days_left !== undefined && st.days_left !== null) parts.push(`本周期剩 ${Number(st.days_left).toFixed(1)} 天`)
  if (st.payout_multiplier && Number(st.payout_multiplier) > 1) parts.push(`达标魔力 ×${st.payout_multiplier}`)
  if (st.target_seed_hours) parts.push(`月做种 ≥${st.target_seed_hours}h`)
  return parts.join(' · ')
}
function claimSeedHoursText(row) {
  const h = Number((row || {}).seed_hours || 0)
  if (!(h > 0)) return ''
  return `已保 ${h.toFixed(1)}h`
}
// ★ 19.7.0：认领保挂实况（账本 × qB）
const claimHost = computed(() => props.claimData.host || {})
function claimQbKind(row) {
  if (row && row.site_only) return 'site'
  if (!row || !row.in_qb) return 'missing'
  const s = String(row.qb_state || '').toLowerCase()
  if (s.includes('paus') || s.includes('stop')) return 'paused'
  return 'seeding'
}
function claimQbText(row) {
  const k = claimQbKind(row)
  if (k === 'site') return '站点侧'
  return k === 'seeding' ? '做种中' : (k === 'paused' ? '已暂停' : '不在 qB')
}
function claimQbColor(row) {
  const k = claimQbKind(row)
  if (k === 'site') return 'info'
  return k === 'seeding' ? 'success' : (k === 'paused' ? 'warning' : 'error')
}
// ── ★ 19.5.0：干跑 / 真跑两个动作彻底分开（用户可见文案，短句）──
//   顶栏常驻模式徽标；「扫描（只读）」永不写；「认领本轮」常驻但禁用时给出原因。
const claimModeText = computed(() => (props.claimCfg.dry ? '干跑' : '真跑'))
const claimSkipped = computed(() => props.claimData.sites_skipped || [])
const claimSitesTotal = computed(() => Number(props.claimData.sites_total || 0))
const claimSitesSupported = computed(() => Number(props.claimData.sites_supported_total || 0))
// ★ 19.6.0「其他站点纳入」：规则未核对的站（preset 用同族插件默认值）——UI 必须如实标注。
const claimUnverified = computed(() => {
  const n = Number(props.claimData.sites_unverified_total || 0)
  if (n > 0) return n
  return (props.claimSites || []).filter((s) => s.supported && claimProfile(s).rules_unverified).length
})
const claimUnverifiedNames = computed(() => props.claimData.sites_unverified || [])
function claimRulesUnverified(s) { return !!(s && s.supported && claimProfile(s).rules_unverified) }
function claimBatchDisabled() {
  if (!props.claimCfg.enabled) return true
  if (props.claimCfg.dry) return true
  return !claimRequestable()
}
function claimBatchHint() {
  if (!props.claimCfg.enabled) return '认领未开启'
  if (props.claimCfg.dry) return '干跑中：执行认领已禁用'
  if (!claimRequestable()) return '暂无可认领'
  return ''
}
</script>

<template>
  <VDialog v-model="claimOpen" max-width="52rem" scrollable :fullscreen="isNarrow">
    <VCard class="magicflow-dialog magicflow-claim-dialog">
      <header class="magicflow-settings-dialog__head">
        <div class="magicflow-claim-title">
          <span class="magicflow-settings-dialog__title">认领</span>
          <VChip size="x-small" :color="claimCfg.dry ? 'warning' : 'success'" variant="tonal">
            {{ claimModeText }}
          </VChip>
        </div>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" :loading="claimLoading" @click="emit('refresh')">刷新</VBtn>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="claimOpen = false" />
        </div>
      </header>
      <VDivider />
      <div class="magicflow-claim-bar">
        <VSelect
          v-model="claimSiteFilter"
          :items="claimFilterItems"
          density="compact"
          variant="outlined"
          hide-details
          class="magicflow-claim-bar__site"
          aria-label="站点筛选"
        />
        <VSpacer />
        <!-- 只读：只扫描，永不写（干跑/真跑分开后扫描不再受「干跑」开关影响） -->
        <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-radar" :loading="claimActing === 'run'" @click="emit('scan')">扫描（只读）</VBtn>
        <!-- 真写：常驻；干跑中/未开启/无可认领时禁用并给出原因 -->
        <VBtn
          size="small"
          variant="flat"
          color="primary"
          prepend-icon="mdi-seal"
          :disabled="claimBatchDisabled()"
          @click="emit('ask', 'batch', null)"
        >认领本轮 {{ claimRequestable() }} 个</VBtn>
      </div>
      <div v-if="claimBatchHint()" class="magicflow-claim-bar__hint">{{ claimBatchHint() }}</div>
      <VCardText class="magicflow-claim-body">
        <VAlert v-if="claimLoading" type="info" variant="tonal" density="compact" class="mb-2">
          正在加载认领状态…
        </VAlert>
        <VAlert v-else-if="!claimCfg.enabled" type="info" variant="tonal" density="compact" class="mb-2">
          认领未开启。开启：插件设置 → 认领。
        </VAlert>
        <VAlert v-else-if="claimCfg.dry" type="warning" variant="tonal" density="compact" class="mb-2">
          干跑中：执行认领已禁用。
        </VAlert>

        <div class="magicflow-claim-summary">
          <div class="magicflow-claim-summary__item">
            <b>{{ claimNum(claimSummaryClaimed) }}</b><span>认领</span>
          </div>
          <div class="magicflow-claim-summary__item">
            <b>{{ claimSummarySettle }}</b><span>结算</span>
          </div>
          <div class="magicflow-claim-summary__item is-accent">
            <b>{{ claimSummaryRewardText }}</b><span>合计奖励</span>
          </div>
        </div>

        <template v-if="claimScopeSite">
        <div class="magicflow-claim-tabs">
          <VBtn size="small" :variant="claimListTab === 'claimed' ? 'flat' : 'text'" color="primary" @click="claimListTab = 'claimed'">
            已认领（{{ claimFilteredClaimed.length }}）
          </VBtn>
          <VBtn size="small" :variant="claimListTab === 'claimable' ? 'flat' : 'text'" color="primary" @click="claimListTab = 'claimable'">
            可认领（{{ claimFilteredClaimable.length }}）
          </VBtn>
        </div>

        <template v-if="claimListTab === 'claimed'">
          <div v-if="!claimFilteredClaimed.length" class="magicflow-table-empty">还没有已认领种子</div>
          <ul v-else class="magicflow-claim-list">
            <li v-for="row in claimShownClaimed" :key="row.hash || (row.site_id + ':' + row.torrent_id)" class="magicflow-claim-item is-claimed">
              <div class="magicflow-claim-item__main">
                <span class="magicflow-claim-item__title">{{ row.title || row.hash }}</span>
                <span class="magicflow-claim-item__meta">{{ row.site_name }} · {{ row.site_only ? '站点侧' : '账本' }} · 奖励 {{ claimRowReward(row) }}<template v-if="row.site_seed_time"> · 做种 {{ row.site_seed_time }}</template></span>
              </div>
              <VChip size="x-small" :color="claimQbColor(row)" variant="tonal">{{ claimQbText(row) }}</VChip>
              <VChip size="x-small" color="success" variant="tonal" prepend-icon="mdi-shield-lock-outline">硬保护</VChip>
            </li>
          </ul>
          <div v-if="claimFilteredClaimed.length > claimShownClaimed.length" class="magicflow-claim-more">
            <VBtn size="x-small" variant="text" @click="claimMoreClaimed">加载更多（{{ claimShownClaimed.length }} / {{ claimFilteredClaimed.length }}）</VBtn>
          </div>
        </template>

        <template v-else>
          <div v-if="!claimFilteredClaimable.length" class="magicflow-table-empty">当前没有可认领种子</div>
          <ul v-else class="magicflow-claim-list">
            <li v-for="row in claimShownClaimable" :key="row.hash" class="magicflow-claim-item">
              <div class="magicflow-claim-item__main">
                <span class="magicflow-claim-item__title">{{ row.title || row.hash }}</span>
                <span class="magicflow-claim-item__meta">{{ row.site_name }} · {{ row.size_gb }}G · 做种 {{ claimSeedersText(row.seeders) }} · 发布 {{ claimAgeText(row.age_days) }}</span>
              </div>
              <VBtn size="x-small" variant="flat" color="primary" prepend-icon="mdi-seal" :disabled="claimCfg.dry" :loading="claimActing === ('do:' + row.hash)" @click="emit('ask', 'do', row)">认领</VBtn>
            </li>
          </ul>
          <div v-if="claimFilteredClaimable.length > claimShownClaimable.length" class="magicflow-claim-more">
            <VBtn size="x-small" variant="text" @click="claimMoreClaimable">加载更多（{{ claimShownClaimable.length }} / {{ claimFilteredClaimable.length }}）</VBtn>
          </div>
        </template>

        </template>

        <template v-else>
<div v-if="!claimScopeSite" class="magicflow-claim-sites">
          <div
            v-for="s in claimSupportedList"
            :key="s.site_id"
            class="magicflow-claim-site"
            role="button"
            tabindex="0"
            @click="claimSiteFilter = String(s.site_id)"
            @keydown.enter="claimSiteFilter = String(s.site_id)"
            @keydown.space.prevent="claimSiteFilter = String(s.site_id)"
          >
            <div class="magicflow-claim-site__head">
              <div class="magicflow-claim-site__name">{{ s.site_name }}</div>
              <VChip size="x-small" color="primary" variant="tonal">{{ claimSiteCycleText(s) }}</VChip>
              <span class="magicflow-claim-site__date">{{ claimSiteDateText(s) }}</span>
              <VIcon icon="mdi-chevron-right" size="18" />
            </div>
            <div class="magicflow-claim-site__stats">
              <div class="magicflow-claim-site__stat">
                <b>{{ claimNum(s.claimed) }}</b><span>已认领</span>
              </div>
              <div class="magicflow-claim-site__stat">
                <b>{{ claimNum(s.claimable) }}</b><span>可认领</span>
              </div>
              <div class="magicflow-claim-site__stat is-accent">
                <b>{{ claimSiteReward(s) }}</b><span>奖励</span>
              </div>
            </div>
          </div>
          <div v-if="!claimLoading && !claimSupportedList.length" class="magicflow-table-empty">没有支持认领的站点（认领预设表未收录；见 docs/认领.md）。</div>
          <div v-if="claimSkipped.length" class="magicflow-claim-more">
            未收录认领（跳过）：{{ claimSkipped.slice(0, 8).join('、') }}<template v-if="claimSkipped.length > 8"> 等 {{ claimSkipped.length }} 站</template>
          </div>
        </div>
        </template>

        <div class="magicflow-claim-note">
          <VIcon icon="mdi-information-outline" size="14" />
          <span>认领后进硬保护；不达标可能扣魔力。</span>
        </div>
        <div v-if="claimHost.total" class="magicflow-claim-note">
          <VIcon icon="mdi-shield-check-outline" size="14" />
          <span>保挂：{{ claimHost.total }} 个已认领 · 做种 {{ claimHost.seeding }} · 暂停 {{ claimHost.paused }} · 丢失 {{ claimHost.missing }}</span>
        </div>
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
/* 站点筛选条（下拉选站，单站/全部站点分别看详情汇总） */
.magicflow-claim-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.magicflow-claim-bar { display: flex; align-items: center; gap: 10px; padding: 8px 18px; }
.magicflow-claim-bar__site { max-width: 240px; }
.magicflow-claim-bar__hint { padding: 0 18px 6px; font-size: 11px; color: rgba(var(--v-theme-warning), .9); }
/* 全部站点：逐站汇总（与站点报表同款：浅底统计块，不做跨站求和） */
.magicflow-claim-sites { display: flex; flex-direction: column; gap: 10px; margin-bottom: 14px; }
.magicflow-claim-site { padding: 10px 12px; border-radius: 10px; background: rgba(var(--v-theme-on-surface), .04); cursor: pointer; transition: background .15s ease; text-align: left; }
.magicflow-claim-site:hover, .magicflow-claim-site:focus-visible { background: rgba(var(--v-theme-primary), .08); outline: none; }
.magicflow-claim-site__head { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; min-width: 0; }
.magicflow-claim-site__name { font-size: 13px; font-weight: 600; }
.magicflow-claim-site__date { margin-left: auto; font-size: 11.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); white-space: nowrap; }
.magicflow-claim-site__stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; margin-top: 8px; }
.magicflow-claim-site__stat { text-align: center; min-width: 0; }
.magicflow-claim-site__stat b { display: block; font-size: 17px; font-weight: 700; line-height: 1.2; overflow-wrap: anywhere; }
.magicflow-claim-site__stat span { font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-claim-site__stat.is-accent b { color: rgb(var(--v-theme-primary)); }
.magicflow-claim-site__sub { margin-top: 7px; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); text-align: center; }
.magicflow-claim-detail { margin-bottom: 14px; }
.magicflow-claim-detail__rule { padding: 8px 2px 0; font-size: .72rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
@media (max-width: 959px) {
  .magicflow-claim-site__stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.magicflow-claim-sec { margin: 10px 2px 6px; font-size: .74rem; font-weight: 600; opacity: .78; }
.magicflow-claim-sec__hint { margin-left: 8px; font-size: .66rem; font-weight: 400; opacity: .55; }
.magicflow-claim-note { display: flex; align-items: flex-start; gap: 5px; margin: 2px 2px 6px; font-size: 11px; line-height: 1.4; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-claim-note .v-icon { opacity: .65; margin-top: 1px; }
.magicflow-claim-note.is-warning { color: rgb(var(--v-theme-warning)); }
.magicflow-claim-detail__rule.is-warning { color: rgb(var(--v-theme-warning)); }
.magicflow-claim-more { margin: 6px 2px 0; font-size: .7rem; opacity: .6; }
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

.magicflow-claim-summary { display: flex; gap: 8px; margin: 10px 0 12px; }
.magicflow-claim-summary__item { flex: 1; min-width: 0; padding: 8px 10px; border-radius: 10px; background: rgba(var(--v-theme-on-surface), .04); }
.magicflow-claim-summary__item b { display: block; font-size: 17px; line-height: 1.3; }
.magicflow-claim-summary__item span { font-size: 11px; color: var(--mf-fg-mid); }
.magicflow-claim-tabs { display: flex; gap: 6px; margin-bottom: 8px; }
</style>
