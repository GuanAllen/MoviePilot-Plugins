<script setup>
// MagicFlow 前端 · 跨站取种弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 复用 composable 纯函数（crossseedStateText / crossseedCardState）→ module 级具名导出 import（单一真值源）。
import { computed } from 'vue'
import { crossseedStateText, crossseedCardState } from '../../composables/useCrossseed'

const props = defineProps({
  // 跨站取种展示态打包；state.data = index.vue 里 useCrossseed 的 crossseedData 全局状态。
  state: { type: Object, default: () => ({}) },
  gbText: { type: Function, default: (v) => v },
  narrow: { type: Boolean, default: false },
})

const crossseedOpen = defineModel({ type: Boolean, default: false })

const emit = defineEmits(['refresh', 'guard', 'unban', 'clear', 'drop', 'operations', 'silent'])

const crossseedData = computed(() => props.state.data || {})
const crossseedStats = computed(() => props.state.stats || { pending: 0, tasks: 0 })
const crossseedSilentCount = computed(() => props.state.silentCount || 0)
const crossseedGuard = computed(() => props.state.guard || { enabled: true, banned: [] })
const crossseedBanned = computed(() => props.state.banned || [])
const crossseedPending = computed(() => props.state.pending || [])
const crossseedSources = computed(() => props.state.sources || [])
const crossseedLegacyCount = computed(() => props.state.legacyCount || 0)
const crossseedPendingHandoff = computed(() => props.state.pendingHandoff || 0)
const crossseedActing = computed(() => props.state.acting || '')
const isNarrow = computed(() => props.narrow)

function loadCrossseed() { emit('refresh') }
function runCrossseedGuard() { emit('guard') }
function unbanCrossseed(domain) { emit('unban', domain) }
function clearCrossseed() { emit('clear') }
function dropCrossseed(hash) { emit('drop', hash) }
function openOperations() { emit('operations') }
function openSilent() { emit('silent') }
</script>

<template>
  <VDialog v-model="crossseedOpen" max-width="46rem" scrollable :fullscreen="isNarrow">
    <VCard class="magicflow-dialog magicflow-crossseed-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">跨站取种</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VChip size="small" variant="tonal" color="primary">{{ crossseedData.tag || '魔流-跨站' }}</VChip>
          <VBtn
            variant="text"
            color="primary"
            size="small"
            prepend-icon="mdi-history"
            @click="openOperations('all')"
          >操作记录</VBtn>
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" @click="loadCrossseed" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="crossseedOpen = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-crossseed-dialog__body">
        <!-- 核心统计：在飞取种 / 取种任务 / 已转静默 -->
        <div class="magicflow-cs-stats">
          <div class="magicflow-cs-stat">
            <b>{{ crossseedStats.pending }}</b>
            <span>在飞取种</span>
          </div>
          <div class="magicflow-cs-stat">
            <b>{{ crossseedStats.tasks }}</b>
            <span>取种任务</span>
          </div>
          <div class="magicflow-cs-stat">
            <b>{{ crossseedSilentCount }}</b>
            <span>已转静默</span>
          </div>
        </div>

        <!-- 一行状态：流量兜底 -->
        <div class="magicflow-cs-status">
          <VChip
            size="small"
            variant="tonal"
            :color="crossseedGuard.enabled === false ? 'error' : 'success'"
            prepend-icon="mdi-shield-check-outline"
          >流量兜底 · {{ crossseedGuard.enabled === false ? '已关闭' : '已启用' }}</VChip>
          <span class="magicflow-cs-status__dim">
            阈值 下载增量 &gt; 体积×{{ crossseedGuard.pct ?? 5 }}%（≥{{ crossseedGuard.min_mb ?? 50 }}MB）· 每 {{ crossseedGuard.interval_min ?? 15 }} 分钟核对
          </span>
          <span class="magicflow-cs-status__dim">{{ crossseedBanned.length ? `· 已拉黑 ${crossseedBanned.length} 站` : '· 无拉黑站点' }}</span>
          <VSpacer />
          <VBtn
            size="small"
            variant="tonal"
            color="primary"
            prepend-icon="mdi-shield-search"
            :loading="crossseedActing === 'guard'"
            @click="runCrossseedGuard"
          >立即核对</VBtn>
        </div>

        <!-- 拉黑站点（有才出现） -->
        <div v-if="crossseedBanned.length" class="magicflow-cs-bans">
          <VChip
            v-for="b in crossseedBanned"
            :key="b.domain"
            size="small"
            variant="tonal"
            color="error"
            closable
            @click:close="unbanCrossseed(b.domain)"
          >{{ b.domain }} · {{ b.age_min }} 分钟前</VChip>
          <VBtn
            size="x-small"
            variant="text"
            color="warning"
            :loading="crossseedActing === 'unban:'"
            @click="unbanCrossseed('')"
          >全部解除</VBtn>
        </div>

        <!-- ★ 来源份 → 静默池（7.16.0）：H&R 保挂/回收不归本页，统一由静默池负责 -->
        <div class="magicflow-cs-handoff">
          <VIcon icon="mdi-pool" size="small" class="magicflow-cs-handoff__icon" />
          <div class="magicflow-cs-handoff__text">
            <b>{{ crossseedSilentCount }}</b> 份来源份已在<b>静默池</b>挂 H&R（下完即移交，保种/分拣/回收归静默池）
            <template v-if="crossseedPendingHandoff">
              <br /><span class="magicflow-cs-status__dim">另有 {{ crossseedPendingHandoff }} 份待移交（下一轮静默托管自动处理）</span>
            </template>
          </div>
          <VSpacer />
          <VBtn
            size="x-small"
            variant="text"
            color="primary"
            prepend-icon="mdi-open-in-new"
            @click="openSilent()"
          >静默池</VBtn>
        </div>

        <!-- 取种台账（在飞取种；有才出现） -->
        <section v-if="crossseedPending.length" class="magicflow-cs-pending">
          <header class="magicflow-cs-pending__head">
            <span>取种台账（在飞）</span>
            <VBtn
              size="x-small"
              variant="text"
              color="error"
              :loading="crossseedActing === 'clear'"
              @click="clearCrossseed"
            >清空</VBtn>
          </header>
          <article v-for="it in crossseedPending" :key="it.sib_hash" class="magicflow-cs-card">
            <div class="magicflow-cs-card__name" :title="it.title || it.sib_hash">{{ it.title || it.sib_hash }}</div>
            <div class="magicflow-cs-card__meta">
              <span class="magicflow-cs-card__site">从 {{ it.site_b || '?' }} 取 → 下完分诊（{{ it.site_a || '?' }}）</span>
              <span class="magicflow-cs-card__size">{{ gbText(it.size_gb) }}</span>
              <VChip size="x-small" variant="flat" color="info">{{ crossseedStateText(it) }}</VChip>
              <VSpacer />
              <VBtn
                size="x-small"
                variant="text"
                color="error"
                icon="mdi-delete-outline"
                :loading="crossseedActing === 'drop:' + it.sib_hash"
                @click="dropCrossseed(it.sib_hash)"
              />
            </div>
          </article>
        </section>

        <!-- ★ 来源份（他站那份 · 保种中）：来源站 → 目标站 明示（7.19.3） -->
        <section v-if="crossseedSources.length" class="magicflow-cs-pending">
          <header class="magicflow-cs-pending__head">
            <span>来源份（他站那份 · 源站保种中）</span>
          </header>
          <article v-for="s in crossseedSources" :key="s.sib_hash" class="magicflow-cs-card">
            <div class="magicflow-cs-card__name" :title="s.title || s.sib_hash">{{ s.title || s.sib_hash }}</div>
            <div class="magicflow-cs-card__meta">
              <span class="magicflow-cs-card__site">来自 {{ s.site_b || '?' }}（源站保种中）</span>
              <span class="magicflow-cs-card__size">{{ gbText(s.size_gb) }}</span>
              <VChip
                v-if="Number(s.progress ?? 1) < 0.999"
                size="x-small" variant="flat" color="info"
              >{{ crossseedStateText(s) }}</VChip>
              <VChip size="x-small" variant="tonal">已挂 {{ s.seeded_h || 0 }}h</VChip>
              <VChip size="x-small" variant="tonal" :color="crossseedCardState(s).color">{{ crossseedCardState(s).text }}</VChip>
              <VChip v-if="String(s.pool || '') === 'silent'" size="x-small" variant="tonal" color="primary">静默池</VChip>
            </div>
          </article>
        </section>
        <div v-if="crossseedLegacyCount" class="magicflow-cs-status__dim">
          另有 {{ crossseedLegacyCount }} 条旧回填来源份（无来源站信息）未在此列出 ——
          <a class="magicflow-cs-link" @click.prevent="openOperations('all')">见操作记录</a>
        </div>

        <!-- 完整规则：默认收起 -->
        <details class="magicflow-cs-rules">
          <summary>查看完整规则</summary>
          <div class="magicflow-cs-rules__body">
            <p><strong>取种原理</strong>：在他站<strong>免费</strong>下载同一资源。落种由全局任务「<strong>跨站取种</strong>」承接；本站判为「非免费」的候选只走跨站，<strong>绝不在本站下载</strong>。把资源挂回本站的工作由「<strong>全站辅种</strong>」负责，本线不再回辅。</p>
            <p><strong>流量兜底</strong>：判「免费」可能出错 → 取种期间核对来源站的免费状态与下载量增量；发现其实不免费，立即<strong>删种 + 拉黑该站</strong>（需人工确认后解除）。</p>
            <p><strong>来源份 H&amp;R 保种</strong>：他站那份下完即做分诊 —— 欠 H&amp;R 交保种（保种期内任何任务都不会删它、也不会改它的标签），不欠则入静默池。</p>
            <p><strong>取种台账</strong>：他站下载中=在岗；下完 → 过 H&amp;R 判定分诊并销账。超过 6 小时未下完/停滞会放弃。未下载完不会转资源、不会整理入库。</p>
            <p><strong>保种时长</strong>：默认 {{ crossseedGuard.seed_hours_default ?? 24 }} 小时；优先级 种子自带 H&amp;R 标记 &gt; 站点规则库 &gt; 默认值。站点自定义：{{ (crossseedGuard.site_hours || []).join('、') || '无' }}。</p>
            <p><strong>期满回收</strong>：{{ crossseedGuard.reclaim ? '已开启——保种期满后允许被任务删种回收空间。' : '未开启——保种期满的种也不会被自动删除。' }}</p>
          </div>
        </details>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 共享选择器（父页其它弹窗也在用）→ 两处各留一份（纯复制，零改动）。
     ⚠️ VDialog 会 teleport 到 body，父页 scoped 规则不再命中 → 组件必须自带这些。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}
.magicflow-settings-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
}
.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
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

/* ── ★ 跨站取种：极简版（7.4.0 改版：低信息噪音 / 圆角卡片 / 大段文字折叠）
     —— 专属选择器，随「跨站取种弹窗」自 index.vue 迁入。── */
.magicflow-cs-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.magicflow-cs-stat {
  flex: 1 1 6.5rem;
  min-inline-size: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 12px 10px;
  border-radius: 14px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-border-color), 0.16);
}
.magicflow-cs-stat b {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
}
.magicflow-cs-stat span {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}
.magicflow-cs-card__chip.v-chip.is-success {
  background: rgba(var(--v-theme-success), 0.16) !important;
  color: rgb(var(--v-theme-success)) !important;
}
.magicflow-cs-card__chip.v-chip.is-warning {
  background: rgba(var(--v-theme-warning), 0.16) !important;
  color: rgb(var(--v-theme-warning)) !important;
}
.magicflow-cs-card__chip.v-chip.is-grey {
  background: rgba(var(--v-theme-on-surface), 0.12) !important;
  color: rgba(var(--v-theme-on-surface), 0.86) !important;
}
.magicflow-cs-bans {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block-end: 10px;
}
/* ★ 来源份 → 静默池（7.16.0）*/
.magicflow-cs-handoff {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-block: 10px 8px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(var(--v-theme-primary), 0.07);
  border: 1px solid rgba(var(--v-theme-primary), 0.22);
  font-size: 13px;
}
.magicflow-cs-handoff__icon { color: rgb(var(--v-theme-primary)); }
.magicflow-cs-handoff__text { min-inline-size: 0; line-height: 1.45; }
.magicflow-cs-link {
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  text-decoration: underline;
}
.magicflow-cs-pending__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}

/* ── 跨站辅种：队列 / 流量兜底（3.11.0）—— 专属选择器，随组件迁入。── */
.magicflow-crossseed-dialog__body {
  padding-block: 12px;
}
.magicflow-crossseed-guard {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding-block: 6px;
}
.magicflow-crossseed-bans {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 6px;
}
.magicflow-crossseed-ban {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid rgba(var(--v-border-color), 0.18);
  border-radius: 8px;
  background: rgba(var(--v-theme-error), 0.06);
}
.magicflow-crossseed-ban__main {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}
.magicflow-crossseed-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 6px;
}
.magicflow-crossseed-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-border-color), 0.18);
  border-radius: 8px;
}
.magicflow-crossseed-item__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-inline-size: 0;
  flex: 1 1 auto;
}
.magicflow-crossseed-item__main strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.magicflow-crossseed-item__meta {
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}

/* ── 共享选择器（cs-status / cs-card / cs-pending / cs-rules 组：死种补源弹窗也用）→ 两处各留一份（纯复制）。── */
.magicflow-cs-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-block: 14px 8px;
}
.magicflow-cs-status__dim {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}
.magicflow-cs-card {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(var(--v-theme-on-surface), 0.035);
  border: 1px solid rgba(var(--v-border-color), 0.16);
}
.magicflow-cs-card__name {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.magicflow-cs-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}
.magicflow-cs-card__site {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-cs-card__size {
  font-variant-numeric: tabular-nums;
}
.magicflow-cs-pending {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-block-start: 16px;
}
.magicflow-cs-rules {
  margin-block-start: 18px;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-border-color), 0.16);
  background: rgba(var(--v-theme-on-surface), 0.03);
  overflow: hidden;
}
.magicflow-cs-rules > summary {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  cursor: pointer;
  list-style: none;
}
.magicflow-cs-rules > summary::before {
  content: '▸';
  font-size: 11px;
  transition: transform 0.15s ease;
}
.magicflow-cs-rules[open] > summary::before {
  transform: rotate(90deg);
}
.magicflow-cs-rules > summary::-webkit-details-marker {
  display: none;
}
.magicflow-cs-rules__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 14px 13px;
  font-size: 12.5px;
  line-height: 1.75;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-cs-rules__body p {
  margin: 0;
}
.magicflow-cs-rules__body strong {
  font-weight: 650;
  color: rgb(var(--v-theme-primary));
}

/* ── ★ 功能弹窗统一：卡片纵向 flex + 正文吃掉剩余高度（消除手机端全屏弹窗底部大片留白）
     —— 原 index.vue 共享组（.magicflow-ondemand-dialog, .magicflow-crossseed-dialog, .magicflow-torrent-dialog）
     中属本弹窗的那一行，随组件迁入；其余两行父页保留。── */
.magicflow-crossseed-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}
</style>
