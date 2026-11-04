<script setup>
// MagicFlow 前端 · 点播弹窗（搜索 / 清单 / 搜索结果）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（odTraffic / odPct / odSpeed / odEtaText / odStageColor / odIsPaused / fmtSizeGb）
// 自 composables/useOndemand.js 具名导入复用 —— 单一真值源；isOndemandAuto 依赖点播结果
// （ondemandResult.auto_pick），仍由 useOndemand 定义 → 以函数 prop 下传（同 SilentPoolDialog 的 gbText 做法）。
import { ref, watch } from 'vue'
import { tsText } from '../../format'
import {
  odTraffic, odPct, odSpeed, odEtaText, odStageColor, odIsPaused, fmtSizeGb,
  odMainTitle, odAltTitle, odSubTitle,
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
const props = defineProps({
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
  odPicked: { type: Array, default: () => [] },
  odBatchBusy: { type: Boolean, default: false },
})

const emit = defineEmits(['run', 'refresh-items', 'act', 'pick', 'pick-all', 'batch-run'])

// ★ 19.11.1 视图分流：候选与清单**互斥显示**，只占一块滚动区。
//   起因：两块长列表原本上下串联在同一滚动槽里 —— 搜完要滚过整份点播清单（可上百条）
//   才看见候选，用户反馈「放不了那么多内容». 默认停在清单（进来先看自己点播的东西），
//   一旦拿到新候选就自动切到候选。
const odView = ref('inventory')
const odSearchHint = ref(false)
watch(() => props.ondemandResult, (v) => {
  if (v) odView.value = 'candidates'
})

// 动作向上：搜候选 / 选源并下载、刷新清单、行内操作（暂停 / 继续 / 移除）、多选勾选与批量点播
function runOndemand(apply, pick = '') { emit('run', apply, pick) }
function loadOndemandItems() { emit('refresh-items') }
function actOndemand(row, action) { emit('act', row, action) }
function pickRow(row) { emit('pick', row) }
function pickAllCandidates(on) { emit('pick-all', !!on) }
function runBatch() { emit('batch-run') }
// 全选 / 半选态在 template 里就地算（props 键可直接引用，无需再包一层 computed）
</script>

<template>
    <VDialog v-model="ondemandOpen" max-width="54rem" scrollable>
      <VCard class="magicflow-dialog magicflow-ondemand-dialog">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">点播</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="ondemandOpen = false" />
          </div>
        </header>
        <VDivider />
        <!-- 固定区①：搜索（不随内容滚动，永远够得着） -->
        <div class="magicflow-od-search">
          <div class="magicflow-od-search__grid">
            <VTextField
              v-model="ondemandQuery"
              density="compact"
              hide-details="auto"
              label="片名 / 链接"
              placeholder="如 流浪地球 或 豆瓣链接"
              @keyup.enter="runOndemand(false)"
            />
            <VSelect
              v-model="ondemandSiteIds"
              density="compact"
              hide-details="auto"
              :items="siteSelectItems"
              label="站点（可多选 · 空＝全部）"
              multiple
              chips
              closable-chips
            />
            <VSelect
              v-model="ondemandTaskId"
              density="compact"
              hide-details="auto"
              :items="[{ title: '（默认目录）', value: '' }, ...tasks.map((t) => ({ title: `${t.name}·${t.site_name || t.site_id}`, value: t.id }))]"
              label="保存目录"
            />
          </div>
          <div class="magicflow-od-search__acts">
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
            <VSpacer />
            <VBtn
              size="x-small"
              variant="text"
              :append-icon="odSearchHint ? 'mdi-chevron-up' : 'mdi-help-circle-outline'"
              @click="odSearchHint = !odSearchHint"
            >说明</VBtn>
          </div>
          <div v-if="odSearchHint" class="magicflow-od-search__hint">
            搜出候选后<strong>勾选</strong>多条 → 点底部<strong>「一并点播」</strong>；不勾也能点<strong>「选源并下载」</strong>自动挑推荐源。
            片名认不出、或站点里没有同名资源时它<strong>不会替你乱选</strong>，只把站点结果列出来让你自己勾
            （标「名称未匹配」的是按关键词捞到的噪音）。
            下完<strong>自动整理进影视库</strong>。候选第一行是<strong>中文名</strong>，灰色小字为站点原名。
          </div>
          <VAlert
            v-if="ondemandError"
            :type="ondemandCandidates.length ? 'warning' : 'error'"
            variant="tonal"
            density="compact"
            class="mt-2"
          >{{ ondemandError }}</VAlert>
        </div>
        <!-- 固定区②：候选 / 清单 二选一，只占一块滚动区 -->
        <div class="magicflow-od-switch">
          <VChip
            size="small"
            class="magicflow-od-tab"
            :variant="odView === 'candidates' ? 'flat' : 'tonal'"
            :color="odView === 'candidates' ? 'primary' : ''"
            @click="odView = 'candidates'"
          >候选 {{ ondemandCandidates.length }}</VChip>
          <VChip
            size="small"
            class="magicflow-od-tab"
            :variant="odView === 'inventory' ? 'flat' : 'tonal'"
            :color="odView === 'inventory' ? 'primary' : ''"
            @click="odView = 'inventory'"
          >点播清单 {{ odInflight.length + odHistory.length }}</VChip>
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
        <VCardText class="magicflow-ondemand-dialog__body">

          <!-- ★ 15.4.0/15.5.0：点播清单（筛选 + 行内操作）——先看见自己点播的东西，再看搜索结果 -->
          <div v-if="odView === 'inventory'" class="magicflow-od-inventory">
            <div class="magicflow-od-inventory__head">
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
            </div>
            <VAlert
              v-if="odMsg"
              :type="odMsg.startsWith('❌') ? 'warning' : 'info'"
              variant="tonal"
              density="compact"
              closable
              class="mb-2 magicflow-od-msg"
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
                <div v-if="row.subtitle" class="magicflow-od-row__sub" :title="row.subtitle">{{ row.subtitle }}</div>
                <div class="magicflow-od-row__meta">
                  <VChip size="x-small" variant="tonal">{{ row.site || '—' }}</VChip>
                  <span v-if="row.size_gb">{{ row.size_gb.toFixed(2) }} GB</span>
                  <span class="magicflow-od-row__ts">{{ tsText(row.added_at) }}</span>
                </div>
                <div class="magicflow-od-row__stage">
                  <VChip size="x-small" variant="tonal" :color="row.stage === 'resource' ? 'success' : (row.stage === 'downloading' ? 'primary' : '')">
                    {{ row.stage_text }}
                  </VChip>
                  <span class="magicflow-od-row__hash">{{ row.hash.slice(0, 12) }}</span>
                </div>
              </article>
            </template>
          </div>
          <template v-if="odView === 'candidates'">
            <div v-if="!ondemandResult" class="magicflow-od-inventory__empty">
              输入片名点「搜候选」：结果在这里，可勾选多条后一并点播。
            </div>
            <template v-else>
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
            <div v-if="ondemandCandidates.length" class="magicflow-od-batchbar mt-2">
              <VCheckbox
                :model-value="ondemandCandidates.length > 0 && odPicked.length >= ondemandCandidates.length"
                :indeterminate="odPicked.length > 0 && odPicked.length < ondemandCandidates.length"
                density="compact"
                hide-details
                aria-label="全选候选"
                @update:model-value="pickAllCandidates"
              />
              <span class="magicflow-od-batchbar__text">全选 · 已选 <strong>{{ odPicked.length }}</strong> 条</span>
              <VSpacer />
              <VBtn
                size="small"
                color="primary"
                prepend-icon="mdi-download-multiple"
                :loading="odBatchBusy"
                :disabled="!odPicked.length || !!ondemandBusy"
                @click="runBatch"
              >一并点播</VBtn>
            </div>
            <div v-if="ondemandCandidates.length" class="magicflow-ondemand-list mt-2">
              <article
                v-for="(row, idx) in ondemandCandidates"
                :key="idx"
                class="magicflow-ondemand-item"
                :class="{ 'magicflow-ondemand-item--auto': isOndemandAuto(row), 'magicflow-ondemand-item--picked': odPicked.includes(row.enclosure) }"
              >
                <VCheckbox
                  class="magicflow-ondemand-item__check"
                  :model-value="odPicked.includes(row.enclosure)"
                  density="compact"
                  hide-details
                  :aria-label="'选择 ' + odMainTitle(row)"
                  @update:model-value="pickRow(row)"
                />
                <div class="magicflow-ondemand-item__body">
                  <div class="magicflow-ondemand-item__title" :title="row.subtitle || row.title">
                    {{ odMainTitle(row) }}<span v-if="odAltTitle(row)" class="magicflow-ondemand-item__alt">（{{ odAltTitle(row) }}）</span>
                  </div>
                  <div v-if="odSubTitle(row)" class="magicflow-ondemand-item__sub">{{ odSubTitle(row) }}</div>
                  <div class="magicflow-ondemand-item__meta">
                    <VChip size="x-small" variant="tonal">{{ row.site_name || row.site }}</VChip>
                    <span>{{ fmtSizeGb(row.size) }}</span>
                    <span>做种 {{ row.seeders }}</span>
                    <VChip
                      size="x-small"
                      variant="tonal"
                      :color="odTraffic(row.downloadvolumefactor).color || undefined"
                    >{{ odTraffic(row.downloadvolumefactor).text }}</VChip>
                    <VChip v-if="row.hit_and_run" size="x-small" variant="tonal" color="warning">H&R</VChip>
                    <!-- ★ 19.11.7：片名相关性（后端 rel）——「没自动选源」时靠它人工挑：
                         2=片名对得上 / 0=关键词粗筛的噪音（站点用译名/拼音时可能误判，故只说「未匹配」不说「不是」）。 -->
                    <VChip v-if="row.rel >= 2 && !isOndemandAuto(row)" size="x-small" variant="tonal" color="primary">片名对得上</VChip>
                    <VChip v-else-if="row.rel === 0" size="x-small" variant="tonal">名称未匹配</VChip>
                    <VChip v-if="isOndemandAuto(row)" size="x-small" variant="flat" color="primary">推荐</VChip>
                    <VChip
                      v-if="ondemandResult?.added && ondemandResult?.picked?.enclosure === row.enclosure"
                      size="x-small"
                      variant="flat"
                      color="success"
                    >已下</VChip>
                  </div>
                  <div class="magicflow-ondemand-item__raw" :title="row.title">{{ row.title }}</div>
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
            <div v-else class="magicflow-od-inventory__empty">
              没搜到候选。换个片名，或把站点选择清空（＝全部站点）再试一次。
            </div>
            </template>
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
.magicflow-ondemand-dialog__body { padding: 8px 18px 16px; overflow: auto; flex: 1 1 auto; min-height: 0; overscroll-behavior: contain; }
/* ★ 19.11.1 分区：搜索 / 切换是固定区，只有中间一块滚动 —— 内容再多也不会把别的东西挤出视野 */
.magicflow-od-search { padding: 10px 18px 8px; flex: 0 0 auto; }
.magicflow-od-search__grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1.3fr) minmax(0, 1fr); gap: 8px; align-items: start; }
.magicflow-od-search__acts { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.magicflow-od-search__hint { margin-top: 8px; padding: 7px 10px; border-radius: 8px; background: rgba(var(--v-theme-primary), 0.09); font-size: 0.78rem; line-height: 1.55; }
.magicflow-od-search__hint strong { color: rgb(var(--v-theme-primary)); }
.magicflow-od-switch { display: flex; align-items: center; gap: 6px; padding: 6px 18px 6px; flex: 0 0 auto; border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08); }
@media (max-width: 760px) {
  .magicflow-od-search__grid { grid-template-columns: 1fr; }
  .magicflow-od-search__acts { margin-top: 6px; }
}
.magicflow-ondemand-list { display: flex; flex-direction: column; gap: 6px; }
/* ★ 19.11.0：候选行改为「勾选框 | 内容 | 按钮」三栏 —— 中文主标题 + 规格副标题 + 站点原名小字 */
.magicflow-ondemand-item { display: flex; align-items: flex-start; gap: 4px; border: 1px solid rgba(var(--v-theme-on-surface), 0.14); border-radius: 8px; padding: 6px 8px 6px 2px; }
.magicflow-ondemand-item--auto { border-color: rgba(var(--v-theme-primary), 0.55); box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.22); }
.magicflow-ondemand-item--picked { background: rgba(var(--v-theme-primary), 0.08); border-color: rgba(var(--v-theme-primary), 0.65); }
.magicflow-ondemand-item__check { flex: 0 0 auto; margin-top: -2px; }
.magicflow-ondemand-item__body { flex: 1 1 auto; min-width: 0; }
.magicflow-ondemand-item__act { flex: 0 0 auto; align-self: center; display: flex; justify-content: flex-end; margin-top: 0; }
.magicflow-ondemand-item__title { font-size: 0.86rem; font-weight: 600; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; }
.magicflow-ondemand-item__alt { font-weight: 400; font-size: 0.94em; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-ondemand-item__sub { margin-top: 2px; font-size: 0.75rem; line-height: 1.45; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; }
.magicflow-ondemand-item__raw { margin-top: 3px; font-size: 0.68rem; line-height: 1.4; opacity: 0.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-ondemand-item__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 4px; font-size: 0.74rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
/* ★ 19.11.0 批量工具条：全选 / 已选计数 / 一并点播
   ★ 19.11.1 吸顶：候选再多，勾选后也能立刻点到「一并点播」，不用滚回顶部 */
.magicflow-od-batchbar {
  display: flex; align-items: center; gap: 4px; padding: 4px 8px 4px 2px; border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.10);
  position: sticky; top: 0; z-index: 2;
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}
.magicflow-od-batchbar__text { font-size: 0.78rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-od-batchbar__text strong { color: rgb(var(--v-theme-primary)); font-variant-numeric: tabular-nums; }
/* ★ 15.4.0 点播清单：进行中（带进度条）+ 历史 */
.magicflow-od-inventory { border: 1px solid rgba(var(--v-theme-on-surface), 0.12); border-radius: 10px; padding: 8px 10px; background: rgba(var(--v-theme-on-surface), 0.03); }
.magicflow-od-inventory__head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.magicflow-od-inventory__empty { font-size: 0.78rem; opacity: 0.7; padding: 6px 2px; }
.magicflow-od-tab { cursor: pointer; user-select: none; }
/* ★ 19.11.0：批量点播的回报带换行（一条失败一行），别糊成一大段 */
.magicflow-od-msg { white-space: pre-line; }
.magicflow-od-row { border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07); padding: 6px 2px; }
.magicflow-od-row:first-of-type { border-top: none; }
.magicflow-od-row__title { font-size: 0.8rem; line-height: 1.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-od-row__sub { font-size: 0.7rem; line-height: 1.4; margin-top: 1px; opacity: 0.55; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-od-row__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 3px; font-size: 0.72rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-od-row__stage { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.magicflow-od-row__pct { font-size: 0.72rem; font-variant-numeric: tabular-nums; opacity: 0.85; }
.magicflow-od-row__hash { font-size: 0.7rem; opacity: 0.55; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.magicflow-od-row__ts { font-variant-numeric: tabular-nums; opacity: 0.75; }
.magicflow-od-row--done .magicflow-od-row__title { color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
</style>
