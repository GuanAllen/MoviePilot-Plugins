<script setup>
// MagicFlow 前端 · 静默池全局视图弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（silentSubLabel / silentHrText / silentProgressText）自 composables/useSilentPool.js
// 具名导入复用 —— 单一真值源，不在两处各写一份。tsText 来自 ../format。
import { silentSubLabel, silentHrText, silentProgressText } from '../../composables/useSilentPool'
import { tsText } from '../../format'

const open = defineModel({ type: Boolean, default: false })
// 过滤 / 视图状态：由父页 composables/useSilentPool.js 持有，双向绑定回传（props 下 / emit 上）。
const view = defineModel('view', { type: String, default: 'pool' })
const sub = defineModel('sub', { type: String, default: '' })
const site = defineModel('site', { type: String, default: '' })
const onlyHr = defineModel('onlyHr', { type: Boolean, default: false })
const q = defineModel('q', { type: String, default: '' })

// props 下（只读）：数据 / 派生直接来自 useSilentPool()；跨域状态 + 纯函数由父页提供。
defineProps({
  data: { type: Object, default: () => ({}) },
  summary: { type: Object, default: () => ({}) },
  subs: { type: Array, default: () => [] },
  sites: { type: Array, default: () => [] },
  items: { type: Array, default: () => [] },
  records: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
  tagReconLoading: { type: Boolean, default: false },
  gbText: { type: Function, default: (v) => v },
})

const emit = defineEmits(['refresh', 'operations', 'invariant', 'tag-reconcile'])
</script>

<template>
  <VDialog v-model="open" max-width="52rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-silent-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">静默池</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VChip size="small" variant="tonal" color="primary">全局 · 跨站/跨任务的「无主」种</VChip>
          <VBtn variant="text" color="info" size="small" prepend-icon="mdi-pause-octagon" @click="emit('invariant')">违背不变量</VBtn>
          <VBtn variant="text" color="warning" size="small" prepend-icon="mdi-tag-check" :loading="tagReconLoading" @click="emit('tag-reconcile')">标签对账</VBtn>
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-history" @click="emit('operations')">操作记录</VBtn>
          <VBtn icon="mdi-refresh" size="small" variant="text" aria-label="刷新" :loading="loading" @click="emit('refresh')" />
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-silent-body">
        <!-- 概览 -->
        <div class="magicflow-cs-stats">
          <div class="magicflow-cs-stat">
            <b>{{ summary.total || 0 }}</b>
            <span>池内总数</span>
          </div>
          <div class="magicflow-cs-stat">
            <b>{{ summary.hr || 0 }}</b>
            <span>欠 H&R</span>
          </div>
          <div class="magicflow-cs-stat">
            <b>{{ summary.incomplete || 0 }}</b>
            <span>未下完</span>
          </div>
          <div class="magicflow-cs-stat">
            <b>{{ subs.length }}</b>
            <span>子类</span>
          </div>
        </div>

        <!-- 子类 + 站点构成 -->
        <div class="magicflow-silent-chips">
          <VChip
            size="small"
            :variant="sub ? 'tonal' : 'flat'"
            :color="sub ? 'default' : 'primary'"
            @click="sub = ''"
          >全部（{{ summary.total || 0 }}）</VChip>
          <VChip
            v-for="s in subs"
            :key="s.key"
            size="small"
            :variant="sub === s.key ? 'flat' : 'tonal'"
            :color="sub === s.key ? 'primary' : 'default'"
            @click="sub = sub === s.key ? '' : s.key"
          >{{ s.label }}（{{ s.count }}）</VChip>
          <VChip
            size="small"
            :variant="onlyHr ? 'flat' : 'tonal'"
            :color="onlyHr ? 'warning' : 'default'"
            @click="onlyHr = !onlyHr"
          >只看欠 H&R（{{ summary.hr || 0 }}）</VChip>
          <VSpacer />
          <span class="magicflow-cs-status__dim">
            共 {{ gbText(summary.size_gb) }} · 静默托管每 {{ data.host?.interval_minutes ?? '—' }} 分钟一轮 · 上次 {{ data.host?.last_run || '—' }}
          </span>
        </div>

        <div v-if="sites.length" class="magicflow-silent-sites">
          <div
            v-for="s in sites"
            :key="s.site"
            class="magicflow-silent-site"
            :class="{ 'is-active': site === s.site }"
            @click="site = site === s.site ? '' : s.site"
          >
            <span class="magicflow-silent-site__name">{{ s.site }}</span>
            <span class="magicflow-silent-site__num">{{ s.total }}</span>
            <span v-if="s.hr" class="magicflow-silent-site__hr">H&R {{ s.hr }}</span>
          </div>
        </div>

        <VTabs v-model="view" density="compact" class="mb-1">
          <VTab value="pool">池内种子（{{ items.length }}）</VTab>
          <VTab value="records">静默托管记录（{{ records.length }}）</VTab>
        </VTabs>

        <VWindow v-model="view">
          <VWindowItem value="pool">
            <VTextField
              v-model="q"
              density="compact"
              variant="outlined"
              hide-details
              prepend-inner-icon="mdi-magnify"
              placeholder="按标题过滤"
              class="mb-2"
              clearable
            />
            <div class="magicflow-cs-list">
              <article v-for="it in items" :key="it.hash" class="magicflow-cs-card">
                <div class="magicflow-cs-card__name" :title="it.title || it.hash">{{ it.title || it.hash }}</div>
                <div class="magicflow-cs-card__meta">
                  <VChip size="x-small" variant="tonal" color="primary">{{ it.site }}</VChip>
                  <VChip size="x-small" variant="tonal">{{ silentSubLabel(it.sub) }}</VChip>
                  <span class="magicflow-cs-card__size">{{ gbText(it.size_gb) }}</span>
                  <VChip v-if="it.hr" size="x-small" variant="flat" color="warning">H&R {{ silentHrText(it) }}</VChip>
                  <VChip v-else size="x-small" variant="tonal">无 H&R</VChip>
                  <VChip
                    v-if="Number(it.progress) < 0.999"
                    size="x-small"
                    variant="flat"
                    color="info"
                  >下载中 {{ silentProgressText(it) }}</VChip>
                  <VChip v-if="it.crossseed" size="x-small" variant="tonal" color="secondary">跨站来源</VChip>
                  <span v-if="it.taken_by" class="magicflow-cs-status__dim">占用：{{ it.taken_by }}</span>
                </div>
              </article>
              <div v-if="!items.length" class="magicflow-table-empty">静默池为空。</div>
            </div>
            <div v-if="Number(data.items_truncated || 0) > 0" class="magicflow-cs-status__dim mt-1">
              还有 {{ data.items_truncated }} 条未展示（用过滤器缩小范围）
            </div>
          </VWindowItem>
          <VWindowItem value="records">
            <ul class="magicflow-silent-records">
              <li v-for="(r, i) in records" :key="i" class="magicflow-silent-record">
                <span class="magicflow-silent-record__time">{{ tsText(r.ts) }}</span>
                <span class="magicflow-silent-record__kind">{{ r.kind || 'run' }}</span>
                <span class="magicflow-silent-record__text">{{ r.reason || `${r.count || 0} 项` }}</span>
                <span v-if="r.duration_ms" class="magicflow-cs-status__dim">{{ (Number(r.duration_ms) / 1000).toFixed(1) }}s</span>
              </li>
              <li v-if="!records.length" class="magicflow-table-empty">暂无记录。</li>
            </ul>
          </VWindowItem>
        </VWindow>

        <div class="magicflow-settings-hint mt-2">
          静默池 = 「无主」种的池子：跨站取种下完的来源份、任务退下来的种、待分拣的新种都在这。
          H&R 保挂 / 未下完清理 / 超时降级（新→普通）/ 分拣（推荐&rarr;资源）由常驻「静默托管」自动跑。
          当前：静默-新超时 {{ data.settings?.new_timeout_hours ?? '—' }} 小时。
        </div>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 正文：随「静默池」弹窗自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head(` i`) / settings-dialog__title /
     settings-hint / table-empty / recommend-dialog__head-actions / cs-stats·stat / cs-status__dim /
     cs-card[__name·__meta·__size]）父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。
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
.magicflow-settings-hint {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 0.8rem;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  background: rgba(var(--v-theme-primary), 0.07);
  border-inline-start: 3px solid rgba(var(--v-theme-primary), 0.45);
}
.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}
.magicflow-recommend-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
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
.magicflow-cs-card__size {
  font-variant-numeric: tabular-nums;
}

/* ── 静默池弹窗（专属选择器，随弹窗自 index.vue 迁入并从 index.vue 删除）── */
/* ★ 静默池弹窗头：手机上标题曾被右侧 chip+按钮挤成一字一行 → 标题不换行，动作单独一行 */
.magicflow-silent-dialog .magicflow-settings-dialog__head {
  flex-wrap: wrap;
  row-gap: 6px;
}
.magicflow-silent-dialog .magicflow-settings-dialog__title {
  flex: 0 0 auto;
  white-space: nowrap;
}
.magicflow-silent-dialog .magicflow-recommend-dialog__head-actions {
  flex: 1 1 100%;
  justify-content: flex-end;
  /* ★ 2026-10-08：窄屏（390px）下 3 个文本按钮 + chip 实测撑到 602px → 横向溢出。允许换行。 */
  flex-wrap: wrap;
  row-gap: 4px;
}

.magicflow-silent-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block: 14px 8px;
}
.magicflow-silent-sites {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-block-end: 10px;
}
.magicflow-silent-site {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  cursor: pointer;
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-border-color), 0.16);
  font-size: 12px;
}
.magicflow-silent-site.is-active {
  background: rgba(var(--v-theme-primary), 0.14);
  border-color: rgba(var(--v-theme-primary), 0.4);
}
.magicflow-silent-site__num { font-weight: 700; font-variant-numeric: tabular-nums; }
.magicflow-silent-site__hr { color: rgb(var(--v-theme-warning)); }
.magicflow-silent-records {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.magicflow-silent-record {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.035);
  border: 1px solid rgba(var(--v-border-color), 0.14);
  font-size: 13px;
}
.magicflow-silent-record__time { font-variant-numeric: tabular-nums; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-silent-record__kind {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.09);
}
.magicflow-silent-record__text { flex: 1 1 12rem; min-inline-size: 0; }
.magicflow-cs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
