<script setup>
// MagicFlow 前端 · 手机端种子池 Tab（★ 19.15.0 视觉层重写，对齐 task-detail-design.html viewPool）
// 手机端（≤959px）专用：托管/候选 seg + 状态筛选（带数量）+ 已选提示 + 批量栏横滚 + 卡片流（一行一种卡）。
// 契约与桌面 SeedingTab 对齐的子集：状态筛选/批量/行动作全部 emit 给父页守卫（与桌面同处理函数）。
// ★ 本轮只重写视图层：props / emit / 筛选语义不变。
//   · 状态筛选从 VSelect 换成原生 select：手机端点开走系统选择器，且选项文案本身就带数量（父页 torrentStatusOptions 已含）。
//   · metaText 顺手修一处真 bug：seed_time=0 时 seedTimeText 返回空串仍被 join，导致尾部留一个孤零零的「·」。
import { computed } from 'vue'
import { TORRENT_PAUSED_STATES, TORRENT_STATE_TEXT, TORRENT_TRANSIENT_STATES } from '../../constants'

const props = defineProps({
  candidateData: { type: Object, default: () => ({}) },
  taskIsBrush: { type: Boolean, default: false },
  rows: { type: Array, default: () => [] },
  statusOptions: { type: Array, default: () => [] },
  selectedHashes: { type: Array, default: () => [] },
  allSelected: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  task: { type: Object, default: null },
  backfilling: { type: Boolean, default: false },
  hrMap: { type: Object, default: () => ({}) },
  hrSettleEnabled: { type: Boolean, default: false },
  hrSettleBusy: { type: Boolean, default: false },
})
const emit = defineEmits([
  'batch',
  'transfer',
  'batch-delete',
  'select-all',
  'clear-selection',
  'toggle-row',
  'open-detail',
  'torrent-action',
  'delete',
  'hr-settle',
  'backfill',
])

const poolView = defineModel('poolView', { type: String, default: 'torrents' })
// ★ 19.14.0：手机端沿用桌面 statusFilter 语义 —— 用双向 model 直接改父状态
const statusFilter = defineModel('statusFilter', { type: String, default: 'all' })

const isBuiltin = computed(() => !!props.task?.builtin)

// 当前筛选项文案（父页 title 已带数量，如「全部状态（111）」）
const statusNow = computed(() => {
  const hit = (props.statusOptions || []).find((o) => o.value === statusFilter.value)
  return hit ? hit.title : '全部状态'
})

// ── 展示态纯函数（与 SeedingTab 同口径，真值源 useSeeding）──
function stateLabel(state) {
  const key = String(state || '').toLowerCase()
  return TORRENT_STATE_TEXT[key] || (key ? state : '托管中')
}
function stateColor(state) {
  const key = String(state || '').toLowerCase()
  if (['uploading', 'forcedup', 'stalledup', 'queuedup'].includes(key)) return 'success'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'checkingdl'].includes(key)) return 'info'
  if (key === 'stalleddl') return 'warning'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'grey'
}
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}
function torrentStateText(item) {
  const key = String(item?.state || '').toLowerCase()
  if (TORRENT_TRANSIENT_STATES[key]) return TORRENT_TRANSIENT_STATES[key]
  if (TORRENT_PAUSED_STATES.includes(key)) return stateLabel(item?.state) || '已暂停'
  const pct = torrentProgressPct(item)
  if (pct >= 100) return '做种中'
  if (pct <= 0) return stateLabel(item?.state) || '等待中'
  return `下载 ${pct}%`
}
function torrentIsPaused(item) {
  return TORRENT_PAUSED_STATES.includes(String(item?.state || '').toLowerCase())
}
function torrentPauseLabel(item) {
  return torrentProgressPct(item) >= 100 ? '暂停' : '暂停'
}
function torrentResumeLabel(item) {
  return torrentProgressPct(item) >= 100 ? '恢复' : '继续'
}
function hrOf(item) {
  const h = String(item?.hash || '').toLowerCase()
  if (!h) return null
  return (props.hrMap || {})[h] || null
}
function hrCanSettle(item) {
  if (!props.hrSettleEnabled) return false
  const b = hrOf(item)
  return !!b && !!b.can_settle
}
function seedTimeText(sec) {
  const s = Number(sec || 0)
  if (!(s > 0)) return ''
  const days = Math.floor(s / 86400)
  if (days > 0) return `做种 ${days} 天`
  const hours = Math.floor(s / 3600)
  if (hours > 0) return `做种 ${hours} 小时`
  const mins = Math.floor(s / 60)
  return mins > 0 ? `做种 ${mins} 分钟` : '刚加入'
}
function metaText(item) {
  const parts = [`${Number(item.size_gb || 0).toFixed(2)} GB`]
  // ★ 修 bug：空串不入列，否则尾部会多一个「·」
  const seedText = item.seed_time != null ? seedTimeText(item.seed_time) : ''
  if (seedText) parts.push(seedText)
  if (item.ratio != null && Number(item.ratio) > 0) parts.push(`分享率 ${Number(item.ratio).toFixed(2)}`)
  return parts.join(' · ')
}
function rowSelected(item) {
  return props.selectedHashes.includes(String(item.hash || '').toLowerCase())
}
</script>

<template>
  <div class="mob-pool">
    <div class="secttl">
      <h3>种子池</h3>
      <small>已托管 {{ rows.length }} 个</small>
    </div>

    <!-- 托管 / 候选 + 回填 -->
    <div class="poolbar">
      <div class="seg">
        <button type="button" :class="{ on: poolView === 'torrents' }" @click="poolView = 'torrents'">
          托管（{{ rows.length }}）
        </button>
        <button v-if="!isBuiltin" type="button" :class="{ on: poolView === 'candidates' }" @click="poolView = 'candidates'">
          候选
        </button>
      </div>
      <button v-if="poolView === 'torrents' && !isBuiltin" type="button" class="rf" :disabled="backfilling" @click="emit('backfill')">
        <VIcon icon="mdi-link-variant-plus" size="14" />回填
      </button>
    </div>

    <!-- 候选队列：直接嵌桌面 CandidatesTab（纯展示，无 emit） -->
    <template v-if="poolView === 'candidates'">
      <CandidatesTab :data="candidateData" :task-is-brush="taskIsBrush" />
    </template>

    <template v-else>
      <!-- 状态筛选：带数量的 pill 入口（点开走系统选择器，选项文案含数量） -->
      <label class="statusfilter">
        <span>状态：<b>{{ statusNow }}</b></span>
        <select v-model="statusFilter">
          <option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">{{ opt.title }}</option>
        </select>
        <VIcon icon="mdi-chevron-down" size="14" />
      </label>

      <!-- 已选提示 + 全选 / 取消（设计稿 selhint，常驻） -->
      <div class="selhint">
        已选 {{ selectedHashes.length }} 个 ·
        <button type="button" :disabled="busy" @click="emit('select-all')">全选筛选（{{ rows.length }}）</button>
        <template v-if="selectedHashes.length"> · <button type="button" :disabled="busy" @click="emit('clear-selection')">取消选择</button></template>
      </div>

      <!-- 批量栏：横向滚动 -->
      <div class="batchwrap">
        <button type="button" class="batch" :disabled="busy" @click="emit('batch', 'protect')">保留</button>
        <button type="button" class="batch" :disabled="busy" @click="emit('batch', 'unprotect')">取消保留</button>
        <button type="button" class="batch" :disabled="busy" @click="emit('batch', 'pause')">暂停</button>
        <button type="button" class="batch" :disabled="busy" @click="emit('batch', 'resume')">恢复</button>
        <button type="button" class="batch" :disabled="busy" @click="emit('batch', 'recheck')">校验</button>
        <button type="button" class="batch pri" :disabled="busy" @click="emit('transfer')">批量转移</button>
        <button type="button" class="batch del" :disabled="busy" @click="emit('batch-delete')">删除</button>
      </div>

      <!-- 种子卡片流 -->
      <div v-if="loading" class="empty">加载中…</div>
      <div v-else-if="!rows.length" class="empty">暂无托管种子</div>
      <div v-else class="cards">
        <article v-for="item in rows" :key="item.hash" class="tcard" :class="{ 'is-picked': rowSelected(item) }">
          <div class="l1">
            <span
              class="cb"
              :class="{ on: rowSelected(item) }"
              role="checkbox"
              :aria-checked="rowSelected(item)"
              tabindex="0"
              @click="emit('toggle-row', item)"
              @keydown.enter="emit('toggle-row', item)"
            >
              <VIcon v-if="rowSelected(item)" icon="mdi-check" size="12" />
            </span>
            <div class="nm" role="button" tabindex="0" :title="item.title" @click="emit('open-detail', item)">
              <VIcon v-if="item.is_protected" icon="mdi-shield-check" size="12" class="nm-prot" />
              {{ item.title || item.hash }}
            </div>
            <span class="st" :class="`st--${stateColor(item.state)}`">{{ torrentStateText(item) }}</span>
          </div>

          <div class="meta">{{ metaText(item) }}</div>

          <div class="acts">
            <button
              type="button"
              class="mini"
              :class="{ pri: !item.is_protected, danger: false }"
              @click.stop="emit('torrent-action', item, item.is_protected ? 'unprotect' : 'protect')"
            >
              <VIcon :icon="item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline'" size="12" />
              {{ item.is_protected ? '取消保护' : '保护' }}
            </button>
            <button type="button" class="mini" @click.stop="emit('torrent-action', item, 'recheck')">
              <VIcon icon="mdi-sync" size="12" />校验
            </button>
            <button
              v-if="torrentIsPaused(item)"
              type="button"
              class="mini"
              @click.stop="emit('torrent-action', item, 'resume')"
            >
              <VIcon icon="mdi-play" size="12" />{{ torrentResumeLabel(item) }}
            </button>
            <button v-else type="button" class="mini" @click.stop="emit('torrent-action', item, 'pause')">
              <VIcon icon="mdi-pause" size="12" />{{ torrentPauseLabel(item) }}
            </button>
            <button type="button" class="mini danger" @click.stop="emit('delete', item)">
              <VIcon icon="mdi-delete-outline" size="12" />删除
            </button>
            <VMenu location="bottom end">
              <template #activator="{ props: menuProps }">
                <button v-bind="menuProps" type="button" class="mini moreml">
                  <VIcon icon="mdi-dots-horizontal" size="14" />
                </button>
              </template>
              <VList density="compact">
                <VListItem prepend-icon="mdi-shield-plus-outline" :title="item.is_protected ? '取消保护' : '保护'" @click="emit('torrent-action', item, item.is_protected ? 'unprotect' : 'protect')" />
                <VListItem v-if="hrCanSettle(item)" prepend-icon="mdi-check-decagram-outline" title="H&R 结清" @click="emit('hr-settle', item)" />
                <VListItem prepend-icon="mdi-delete-outline" title="删除种子" base-color="error" @click="emit('delete', item)" />
              </VList>
            </VMenu>
          </div>
        </article>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ══════════════════════════════════════════════════════════════════════════════
   手机端种子池（★ 19.15.0 视觉层按设计稿 viewPool 重写）
   设计稿口径：11px 标题两行截断、9px 状态胶囊、9.5px meta、10px 迷你操作、
   状态筛选为「状态：xxx（N）」pill 入口、批量栏横向滚动。
   ══════════════════════════════════════════════════════════════════════════════ */
.mob-pool {
  /* 19.16.41 浅色主题：深色原值抽成语义变量，浅色整体覆盖 */
  --ink-strong: #e8e9f0;
  --ink-body: #b9bdcf;
  --ink-sub: #7d8296;
  --ink-purple: #cfc6ff;
  --ink-red: #ff9aa5;
  --ink-amber: #f5cd84;
  --ink-green: #7ce7b6;
  --ink-info: #8dd9f5;
  --line: rgba(var(--v-theme-on-surface), 0.07);
  --dim: #6f7488;
  --sub: #8b90a3;
  --purple: #8b7cf6;
  --purple2: #6d5ce7;
  --green: #3ddc97;
  --red: #ff6b7a;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
html[data-glass-color-scheme="light"] .mob-pool {
  --dim: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  --sub: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  --ink-strong: rgb(var(--v-theme-on-surface));
  --ink-body: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  --ink-sub: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  --ink-purple: #5c46c9;
  --ink-red: #b3263b;
  --ink-amber: #8a5a00;
  --ink-green: #137a52;
  --ink-info: #116a8a;
}


.secttl { display: flex; align-items: baseline; justify-content: space-between; margin: 2px 0 0; }
.secttl h3 { font-size: 13px; font-weight: 700; }
.secttl small { font-size: 10px; color: var(--dim); }

/* ── 托管/候选 seg ── */
.poolbar { display: flex; align-items: center; gap: 7px; }
.seg {
  display: flex; flex: 1; min-width: 0;
  padding: 2px; border-radius: 9px;
  border: 1px solid var(--line); background: rgba(var(--v-theme-on-surface), 0.04);
}
.seg button {
  flex: 1; min-width: 0; padding: 6px 4px; border: 0; border-radius: 7px;
  background: transparent; color: var(--ink-sub); font-size: 10.5px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.seg button.on { background: var(--purple2); color: #fff; }
.rf {
  display: inline-flex; align-items: center; gap: 5px; flex: none;
  padding: 8px 10px; border-radius: 9px;
  border: 1px solid rgba(139, 124, 246, 0.35); background: transparent;
  color: var(--ink-purple); font-size: 10.5px; font-weight: 600; white-space: nowrap;
}
.rf:disabled { opacity: 0.55; }

/* ── 状态筛选 pill ── */
.statusfilter {
  position: relative;
  display: flex; align-items: center; gap: 6px;
  padding: 9px 11px; border-radius: 9px;
  border: 1px solid var(--line); background: rgba(var(--v-theme-on-surface), 0.04);
  font-size: 11px; color: var(--ink-body);
}
.statusfilter > span { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.statusfilter b { color: var(--ink-purple); font-weight: 600; }
.statusfilter select {
  position: absolute; inset: 0; width: 100%; height: 100%;
  opacity: 0; appearance: none; border: 0;
}

/* ── 已选提示 / 批量栏 ── */
.selhint { font-size: 10px; color: var(--ink-purple); }
.selhint button {
  padding: 0; border: 0; background: transparent;
  color: var(--ink-purple); font-size: 10px; font-weight: 600; text-decoration: underline;
  text-underline-offset: 2px;
}
.selhint button:disabled { opacity: 0.5; }

.batchwrap {
  display: flex; gap: 6px; overflow-x: auto;
  padding-bottom: 3px; margin: 0 -2px; scrollbar-width: none;
}
.batchwrap::-webkit-scrollbar { display: none; }
.batch {
  flex: none; padding: 7px 11px; border-radius: 8px;
  border: 1px solid var(--line); background: rgba(var(--v-theme-on-surface), 0.05);
  color: var(--ink-body); font-size: 10.5px; font-weight: 600; white-space: nowrap;
}
.batch.pri { background: rgba(139, 124, 246, 0.18); border-color: rgba(139, 124, 246, 0.4); color: var(--ink-purple); }
.batch.del { color: var(--ink-red); border-color: rgba(255, 107, 122, 0.3); }
.batch:disabled { opacity: 0.55; }

/* ── 卡片流 ── */
.cards { display: flex; flex-direction: column; gap: 8px; }
.tcard {
  padding: 11px 12px; border-radius: 12px;
  border: 1px solid var(--line); background: rgba(var(--v-theme-on-surface), 0.03);
}
.tcard.is-picked { border-color: rgba(139, 124, 246, 0.42); background: rgba(139, 124, 246, 0.06); }
.l1 { display: flex; align-items: flex-start; gap: 8px; }
.cb {
  width: 16px; height: 16px; flex: none; margin-top: 1px;
  display: grid; place-items: center; cursor: pointer;
  border: 1px solid #5b6072; border-radius: 4px; color: #fff;
}
.cb.on { background: var(--purple); border-color: var(--purple); }
.nm {
  flex: 1; min-width: 0; cursor: pointer;
  font-size: 11px; font-weight: 600; line-height: 1.45; color: var(--ink-strong);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.nm-prot { margin-right: 3px; color: var(--ink-purple); vertical-align: -2px; }
.st {
  flex: none; font-size: 9px; font-weight: 600;
  padding: 3px 7px; border-radius: 20px; white-space: nowrap;
}
.st--success { background: rgba(61, 220, 151, 0.13); color: var(--ink-green); border: 1px solid rgba(61, 220, 151, 0.25); }
.st--info { background: rgba(94, 200, 240, 0.13); color: var(--ink-info); border: 1px solid rgba(94, 200, 240, 0.25); }
.st--warning { background: rgba(255, 182, 76, 0.13); color: var(--ink-amber); border: 1px solid rgba(255, 182, 76, 0.25); }
.st--error { background: rgba(255, 107, 122, 0.13); color: var(--ink-red); border: 1px solid rgba(255, 107, 122, 0.25); }
.st--grey { background: rgba(var(--v-theme-on-surface), 0.06); color: var(--ink-body); border: 1px solid var(--line); }

.meta { margin: 6px 0 9px 24px; font-size: 9.5px; color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.acts { display: flex; flex-wrap: wrap; gap: 6px; margin-left: 24px; }
.mini {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 6px 9px; border-radius: 8px;
  border: 1px solid var(--line); background: rgba(var(--v-theme-on-surface), 0.05);
  color: var(--ink-body); font-size: 10px; font-weight: 600; white-space: nowrap;
}
.mini.pri { color: var(--ink-purple); border-color: rgba(139, 124, 246, 0.4); background: rgba(139, 124, 246, 0.12); }
.mini.danger { color: var(--ink-red); }
.mini.moreml { flex: none; width: 30px; justify-content: center; padding: 6px 0; }

.empty { padding: 18px 4px; text-align: center; font-size: 11px; color: var(--dim); }
</style>
