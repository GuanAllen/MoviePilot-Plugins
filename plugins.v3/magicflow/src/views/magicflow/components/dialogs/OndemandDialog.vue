<script setup>
// MagicFlow 前端 · 点播弹窗（搜索 / 清单 / 搜索结果）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（odTraffic / odPct / odSpeed / odEtaText / odStageColor / odIsPaused / fmtSizeGb）
// 自 composables/useOndemand.js 具名导入复用 —— 单一真值源；isOndemandAuto 依赖点播结果
// （ondemandResult.auto_pick），仍由 useOndemand 定义 → 以函数 prop 下传（同 SilentPoolDialog 的 gbText 做法）。
import { fmtTs } from '../../format'
import {
  odTraffic, odPct, odSpeed, odEtaText, odStageColor, odIsPaused, fmtSizeGb,
} from '../../composables/useOndemand'

// 开关走 defineModel（Boolean）；查询 / 站点多选 / 保存目录 / 清单筛选 / 操作提示 均两向绑定，
// 子不直接改父 state。
const ondemandOpen = defineModel({ type: Boolean, default: false })
const ondemandQuery = defineModel('query', { type: String, default: '' })
const ondemandSiteIds = defineModel('siteIds', { type: Array, default: () => [] })
const ondemandTaskId = defineModel('taskId', { type: String, default: '' })
const ondemandTab = defineModel('tab', { type: String, default: 'inflight' })
const odMsg = defineModel('msg', { type: String, default: '' })

// props：点播域展示态（useOndemand）+ 站点多选 / 保存目录（父页其它域）+ 函数 prop（isOndemandAuto）。
// ★ 保持无内联注释：护栏⑦（check_template_bindings）按 `[,{] ident :` 逐键解析 defineProps。
//   siteSelectItems ← useSignin；tasks ← useTasks；isOndemandAuto ← useOndemand（依赖结果，函数下传）。
defineProps({
  ondemandResult: { type: Object, default: null },
  ondemandCandidates: { type: Array, default: () => [] },
  odInflight: { type: Array, default: () => [] },
  odHistory: { type: Array, default: () => [] },
  odActing: { type: String, default: '' },
  ondemandBusy: { type: String, default: '' },
  ondemandError: { type: String, default: '' },
  ondemandItemsBusy: { type: Boolean, default: false },
  siteSelectItems: { type: Array, default: () => [] },
  tasks: { type: Array, default: () => [] },
  isOndemandAuto: { type: Function, default: () => false },
})

const emit = defineEmits(['run', 'refresh-items', 'act'])

// 动作向上：搜候选 / 选源并下载、刷新清单、行内操作（暂停 / 继续 / 移除）
function runOndemand(apply, pick = '') { emit('run', apply, pick) }
function loadOndemandItems() { emit('refresh-items') }
function actOndemand(row, action) { emit('act', row, action) }
</script>

<template>
    <VDialog v-model="ondemandOpen" max-width="46rem" scrollable>
      <VCard class="magicflow-dialog magicflow-ondemand-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">点播</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="ondemandOpen = false" />
          </div>
        </header>
        <VDivider />
        <VCardText class="magicflow-ondemand-dialog__body">
          <div class="magicflow-ondemand-hint">
            <div>输入片名或链接 → <strong>搜候选</strong> → 点<strong>「下这条」</strong>；不选就点<strong>「选源并下载」</strong>（自动挑推荐源）。下完<strong>自动整理进影视库</strong>。</div>
            <div class="magicflow-ondemand-hint__legend">
              站点可多选，<strong>不勾＝全部</strong>；默认优先选<strong>免费</strong>的源。
            </div>
          </div>
          <div class="magicflow-ondemand-form">
            <VTextField
              v-model="ondemandQuery"
              density="comfortable"
              hide-details="auto"
              label="片名 / 链接"
              placeholder="如 流浪地球 或 https://movie.douban.com/subject/35267208/"
              @keyup.enter="runOndemand(false)"
            />
            <VSelect
              v-model="ondemandSiteIds"
              density="comfortable"
              hide-details="auto"
              :items="siteSelectItems"
              label="站点（可多选 · 不勾 = 全部站点）"
              multiple
              chips
              closable-chips
            />
            <VSelect
              v-model="ondemandTaskId"
              density="comfortable"
              hide-details="auto"
              :items="[{ title: '（默认目录）', value: '' }, ...tasks.map((t) => ({ title: `${t.name}·${t.site_name || t.site_id}`, value: t.id }))]"
              label="保存目录"
            />
          </div>
          <div class="magicflow-ondemand-actions">
            <VBtn
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-magnify"
              :loading="ondemandBusy === 'preview'"
              @click="runOndemand(false)"
            >搜候选</VBtn>
            <VBtn
              size="small"
              color="primary"
              prepend-icon="mdi-cloud-download-outline"
              :loading="ondemandBusy === 'apply'"
              @click="runOndemand(true)"
            >选源并下载</VBtn>
          </div>
          <VAlert v-if="ondemandError" type="error" variant="tonal" density="compact" class="mt-2">
            {{ ondemandError }}
          </VAlert>

          <!-- ★ 15.4.0/15.5.0：点播清单（筛选 + 行内操作）——先看见自己点播的东西，再看搜索结果 -->
          <div class="magicflow-od-inventory mt-3">
            <div class="magicflow-od-inventory__head">
              <span class="magicflow-od-inventory__title">点播清单</span>
              <VChip
                size="x-small"
                :variant="ondemandTab === 'inflight' ? 'flat' : 'tonal'"
                :color="ondemandTab === 'inflight' ? 'primary' : ''"
                class="magicflow-od-tab"
                @click="ondemandTab = 'inflight'"
              >进行中 {{ odInflight.length }}</VChip>
              <VChip
                size="x-small"
                :variant="ondemandTab === 'done' ? 'flat' : 'tonal'"
                :color="ondemandTab === 'done' ? 'primary' : ''"
                class="magicflow-od-tab"
                @click="ondemandTab = 'done'"
              >已完成 {{ odHistory.length }}</VChip>
              <VSpacer />
              <VBtn
                icon="mdi-refresh"
                size="x-small"
                variant="text"
                aria-label="刷新点播清单"
                :loading="ondemandItemsBusy"
                @click="loadOndemandItems"
              />
            </div>
            <VAlert
              v-if="odMsg"
              :type="odMsg.startsWith('❌') ? 'warning' : 'info'"
              variant="tonal"
              density="compact"
              closable
              class="mb-2"
              @click:close="odMsg = ''"
            >{{ odMsg }}</VAlert>
            <!-- 进行中 -->
            <template v-if="ondemandTab === 'inflight'">
              <div v-if="!odInflight.length" class="magicflow-od-inventory__empty">
                没有进行中的点播。搜一部片开始吧。
              </div>
              <article v-for="row in odInflight" :key="'od-i-' + row.hash" class="magicflow-od-row">
                <div class="magicflow-od-row__title" :title="row.title">
                  {{ row.title || row.hash.slice(0, 12) }}<template v-if="row.year"> ({{ row.year }})</template>
                </div>
                <div class="magicflow-od-row__meta">
                  <VChip size="x-small" variant="tonal">{{ row.site || '—' }}</VChip>
                  <VChip v-if="row.free" size="x-small" variant="tonal" color="success">免费</VChip>
                  <VChip v-if="row.hit_and_run" size="x-small" variant="tonal" color="warning">H&R</VChip>
                  <span v-if="row.size_gb">{{ row.size_gb.toFixed(2) }} GB</span>
                  <span v-if="row.stage === 'downloading' && row.speed">{{ odSpeed(row.speed) }}</span>
                  <span v-if="row.eta_s">{{ odEtaText(row.eta_s) }}</span>
                </div>
                <VProgressLinear
                  :model-value="odPct(row)"
                  height="6"
                  rounded
                  :color="odIsPaused(row) ? 'warning' : (row.stage === 'downloading' ? 'primary' : 'success')"
                  class="mt-1"
                />
                <div class="magicflow-od-row__stage">
                  <VChip size="x-small" variant="flat" :color="odIsPaused(row) ? 'warning' : odStageColor(row.stage)">
                    {{ odIsPaused(row) ? '已暂停' : row.stage_text }}
                  </VChip>
                  <span v-if="row.stage === 'downloading' && !odIsPaused(row)" class="magicflow-od-row__pct">{{ odPct(row).toFixed(1) }}%</span>
                  <span class="magicflow-od-row__hash">{{ row.hash.slice(0, 12) }}</span>
                  <VSpacer />
                  <VBtn
                    v-if="!odIsPaused(row)"
                    size="x-small"
                    variant="tonal"
                    :loading="odActing === row.hash + ':pause'"
                    @click="actOndemand(row, 'pause')"
                  >暂停</VBtn>
                  <VBtn
                    v-else
                    size="x-small"
                    variant="tonal"
                    color="primary"
                    :loading="odActing === row.hash + ':resume'"
                    @click="actOndemand(row, 'resume')"
                  >继续</VBtn>
                  <VBtn
                    size="x-small"
                    variant="tonal"
                    color="error"
                    :loading="odActing === row.hash + ':remove'"
                    @click="actOndemand(row, 'remove')"
                  >移除</VBtn>
                </div>
              </article>
            </template>
            <!-- 已完成 -->
            <template v-else>
              <div v-if="!odHistory.length" class="magicflow-od-inventory__empty">还没有已完成的点播。</div>
              <article
                v-for="row in odHistory"
                :key="'od-h-' + row.hash"
                class="magicflow-od-row magicflow-od-row--done"
              >
                <div class="magicflow-od-row__title" :title="row.title">
                  {{ row.title || row.hash.slice(0, 12) }}
                </div>
                <div class="magicflow-od-row__meta">
                  <VChip size="x-small" variant="tonal">{{ row.site || '—' }}</VChip>
                  <span v-if="row.size_gb">{{ row.size_gb.toFixed(2) }} GB</span>
                  <span class="magicflow-od-row__ts">{{ fmtTs(row.ts) }}</span>
                </div>
                <div class="magicflow-od-row__stage">
                  <VChip size="x-small" variant="tonal" :color="row.result === 'resource' ? 'success' : (row.result === 'downloading' ? 'primary' : '')">
                    {{ row.result_text }}
                  </VChip>
                  <span class="magicflow-od-row__hash">{{ row.hash.slice(0, 12) }}</span>
                </div>
              </article>
            </template>
          </div>
          <template v-if="ondemandResult">
            <div class="magicflow-recommend-dialog__summary mt-2">
              <VChip size="small" :color="ondemandResult.resource?.recognized ? 'success' : 'warning'" variant="tonal">
                {{ ondemandResult.resource?.recognized ? '已识别' : '未识别（按原串搜）' }}
              </VChip>
              <i>·</i>
              <span>{{ ondemandResult.resource?.title }} {{ ondemandResult.resource?.year }}</span>
              <i>·</i>
              <span>候选 {{ ondemandCandidates.length }}</span>
              <i>·</i>
              <span>站点 {{ (ondemandResult.sites || []).join(', ') || '—' }}</span>
              <i>·</i>
              <span>存到 <code>{{ ondemandResult.save_path || '（未配置）' }}</code></span>
            </div>
            <div v-if="ondemandResult.added" class="magicflow-recommend-dialog__note">
              已下载：<code>{{ ondemandResult.added }}</code>（完成后直接转「资源」）
            </div>
            <div v-if="ondemandCandidates.length" class="magicflow-ondemand-list mt-2">
              <article
                v-for="(row, idx) in ondemandCandidates"
                :key="idx"
                class="magicflow-ondemand-item"
                :class="{ 'magicflow-ondemand-item--auto': isOndemandAuto(row) }"
              >
                <div class="magicflow-ondemand-item__title" :title="row.title">{{ row.title }}</div>
                <div class="magicflow-ondemand-item__meta">
                  <VChip size="x-small" variant="tonal">{{ row.site_name || row.site }}</VChip>
                  <span>{{ fmtSizeGb(row.size) }}</span>
                  <span>做种 {{ row.seeders }}</span>
                  <VChip
                    size="x-small"
                    variant="tonal"
                    :color="odTraffic(row.downloadvolumefactor).color || undefined"
                  >{{ odTraffic(row.downloadvolumefactor).text }}</VChip>
                  <VChip v-if="isOndemandAuto(row)" size="x-small" variant="flat" color="primary">推荐</VChip>
                  <VChip
                    v-if="ondemandResult?.added && ondemandResult?.picked?.enclosure === row.enclosure"
                    size="x-small"
                    variant="flat"
                    color="success"
                  >已下</VChip>
                </div>
                <div class="magicflow-ondemand-item__act">
                  <VBtn
                    size="x-small"
                    variant="tonal"
                    color="primary"
                    prepend-icon="mdi-download"
                    :loading="ondemandBusy === 'apply'"
                    :disabled="!!ondemandBusy"
                    @click="runOndemand(true, row.enclosure)"
                  >下这条</VBtn>
                </div>
              </article>
            </div>
          </template>
        </VCardText>
      </VCard>
    </VDialog>

</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 摘要行：随「点播弹窗」自 index.vue 迁入。
     下列**共享选择器**（magicflow-dialog / settings-dialog__head（含 i）/ settings-dialog__title /
     recommend-dialog__head-actions / recommend-dialog__summary（含 i）/ recommend-dialog__note）
     父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。
     ⚠️ VDialog 会 teleport 到 body，父页 scoped 规则够不到子内部，组件内必须自带这些共享规则。── */
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
.magicflow-recommend-dialog__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  font-size: 0.85rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-recommend-dialog__summary i {
  font-style: normal;
  opacity: var(--mf-op-dim);
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.magicflow-recommend-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  opacity: 0.85;
}

/* ── 点播弹窗（专属选择器，随组件迁入）────────────────────────────── */
.magicflow-ondemand-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}
.magicflow-ondemand-dialog__body { padding: 10px 18px 20px; overflow: auto; flex: 1 1 auto; min-height: 0; }
.magicflow-ondemand-form { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-start; margin-top: 8px; }
.magicflow-ondemand-form > .v-input:first-child { flex: 1 1 100%; }
.magicflow-ondemand-form > .v-input:not(:first-child) { flex: 1 1 12rem; max-width: 24rem; }
.magicflow-ondemand-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.magicflow-ondemand-hint { margin: 2px 0 10px; padding: 8px 10px; border-radius: 10px; background: rgba(var(--v-theme-primary), 0.10); font-size: 0.84rem; line-height: 1.6; }
.magicflow-ondemand-hint strong { color: rgb(var(--v-theme-primary)); }
.magicflow-ondemand-hint__legend { margin-top: 4px; font-size: 0.76rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-ondemand-hint__legend em { font-style: normal; font-weight: 600; color: rgb(var(--v-theme-on-surface)); }
.magicflow-ondemand-list { display: flex; flex-direction: column; gap: 6px; }
.magicflow-ondemand-item { border: 1px solid rgba(var(--v-theme-on-surface), 0.14); border-radius: 8px; padding: 6px 8px; }
.magicflow-ondemand-item--auto { border-color: rgba(var(--v-theme-primary), 0.55); box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.22); }
.magicflow-ondemand-item__act { display: flex; justify-content: flex-end; margin-top: 6px; }
.magicflow-ondemand-item__title { font-size: 0.8rem; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-all; }
.magicflow-ondemand-item__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 4px; font-size: 0.74rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
/* ★ 15.4.0 点播清单：进行中（带进度条）+ 历史 */
.magicflow-od-inventory { border: 1px solid rgba(var(--v-theme-on-surface), 0.12); border-radius: 10px; padding: 8px 10px; background: rgba(var(--v-theme-on-surface), 0.03); }
.magicflow-od-inventory__head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.magicflow-od-inventory__title { font-size: 0.84rem; font-weight: 600; margin-right: 2px; }
.magicflow-od-inventory__empty { font-size: 0.78rem; opacity: 0.7; padding: 6px 2px; }
.magicflow-od-tab { cursor: pointer; user-select: none; }
.magicflow-od-row { border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07); padding: 6px 2px; }
.magicflow-od-row:first-of-type { border-top: none; }
.magicflow-od-row__title { font-size: 0.8rem; line-height: 1.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-od-row__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 3px; font-size: 0.72rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-od-row__stage { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.magicflow-od-row__pct { font-size: 0.72rem; font-variant-numeric: tabular-nums; opacity: 0.85; }
.magicflow-od-row__hash { font-size: 0.7rem; opacity: 0.55; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.magicflow-od-row__ts { font-variant-numeric: tabular-nums; opacity: 0.75; }
.magicflow-od-row--done .magicflow-od-row__title { color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
</style>
