<script setup>
// MagicFlow 前端 · 点播弹窗（搜索 / 清单 / 搜索结果）
// ★ 19.12.86 移动端改稿 + 去掉「一键挑源」路径：
//   ① 界面只有一个主按钮（搜索）；下载唯一入口＝勾选候选 → 底部「一并点播」。
//      原「选源并下载」（后端 apply=true 自动挑源）与候选行内「下这条」一并移除 ——
//      主人 11-19 15:00 定：不要一键的路，看清楚再下。
//   ② 站名/保存目录在窄屏收进一行摘要（默认折叠），90% 的点播不改这两项。
//   ③ 清单按「还要多久」排信息：剩 X 小时加粗前置，规格降为一行小字，infohash 移出正文。
//   ④ 已完成默认只露 3 条，可展开全部。
//   auto_pick 仍在、仍打「推荐」标记 —— 现在用于**默认勾选**那一颗，于是「搜索 → 一并点播」
//   两步即可，但每一步都看得见。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
import { computed, ref, watch } from 'vue'
import { tsText } from '../../format'
import {
  odTraffic, odPct, odSpeed, odEtaText, odStageColor, odIsPaused, fmtSizeGb,
  odMainTitle, odAltTitle, odSubTitle, odRawTitle, odRelease,
} from '../../composables/useOndemand'

// 开关走 defineModel（Boolean）；查询 / 站点多选 / 保存目录 / 清单筛选 / 操作提示 均两向绑定。
const ondemandOpen = defineModel({ type: Boolean, default: false })
const ondemandQuery = defineModel('query', { type: String, default: '' })
const ondemandSiteIds = defineModel('siteIds', { type: Array, default: () => [] })
const ondemandTaskId = defineModel('taskId', { type: String, default: '' })
const ondemandTab = defineModel('tab', { type: String, default: 'inflight' })
const odMsg = defineModel('msg', { type: String, default: '' })

// props：点播域展示态（useOndemand）+ 站点多选 / 保存目录（父页其它域）+ 函数 prop（isOndemandAuto）。
// ★ 保持无内联注释：护栏⑦（check_template_bindings）按 `[,{] ident :` 逐键解析 defineProps。
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
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['run', 'refresh-items', 'act', 'pick', 'pick-all', 'batch-run'])

// ★ 19.16.4：整批候选同属一部片 —— 站点没给中文名时用它当行内片名（rel=0 的行除外）。
const odCtxTitle = computed(() => String(props.ondemandResult?.resource?.title || ''))

// 候选与清单互斥显示，只占一块滚动区：默认停在清单（进来先看自己点播的东西），
// 拿到新候选自动切到候选。
const odView = ref('inventory')
const odSearchHint = ref(false)
const odAdvOpen = ref(false)     // 窄屏「站点 / 保存目录」折叠态
const odDoneAll = ref(false)     // 已完成是否展开全部

function runOndemand(apply, pick = '') { emit('run', apply, pick) }
function loadOndemandItems() { emit('refresh-items') }
function actOndemand(row, action) { emit('act', row, action) }
function pickRow(row) { emit('pick', row) }
function pickAllCandidates(on) { emit('pick-all', !!on) }
function runBatch() { emit('batch-run') }

// ★ 17.x：拿到候选后把「推荐源」默认勾上 —— 去掉一键路之后，这两步就是最短路径。
//   只在用户还没勾任何东西时补一次，取消勾选后不会被它再抢回来。
function autoPickFirst() {
  const auto = props.ondemandResult?.auto_pick
  if (!auto || (props.odPicked || []).length) return
  const row = (props.ondemandCandidates || []).find((r) => r.enclosure === auto)
  if (row) emit('pick', row)
}
watch(() => [props.ondemandResult, props.ondemandCandidates], (v) => {
  if (v[0]) { odView.value = 'candidates'; autoPickFirst() }
})

const showAdv = computed(() => !props.narrow || odAdvOpen.value)
const siteText = computed(() => {
  const ids = (props.ondemandSiteIds || []).map(String).filter(Boolean)
  const all = (props.siteSelectItems || []).length
  if (!ids.length || (all && ids.length >= all)) return '全部站点'
  const names = ids.map((id) => (props.siteSelectItems.find((s) => String(s.value) === id) || {}).title || id)
  return names.length <= 2 ? names.join('、') : `${names.slice(0, 2).join('、')} 等 ${names.length} 站`
})
const taskText = computed(() => {
  const tid = String(props.ondemandTaskId || '')
  const t = (props.tasks || []).find((x) => String(x.id) === tid)
  return t ? `${t.name}${t.site_name ? '·' + t.site_name : ''}` : '默认目录'
})
const doneRows = computed(() => (odDoneAll.value ? props.odHistory : (props.odHistory || []).slice(0, 3)))
const pickedGb = computed(() => {
  const set = new Set(props.odPicked || [])
  return (props.ondemandCandidates || [])
    .filter((r) => set.has(r.enclosure))
    .reduce((s, r) => s + Number(r.size || 0), 0)
})
const allPicked = computed(() =>
  props.ondemandCandidates.length > 0 && props.odPicked.length >= props.ondemandCandidates.length)
</script>

<template>
    <VDialog
      v-model="ondemandOpen"
      :fullscreen="narrow"
      :max-width="narrow ? undefined : '54rem'"
      scrollable
    >
      <VCard class="magicflow-dialog magicflow-ondemand-dialog" :class="{ 'magicflow-ondemand-dialog--narrow': narrow }">
        <header class="magicflow-settings-dialog__head">
          <span class="magicflow-settings-dialog__title">点播</span>
          <div class="magicflow-recommend-dialog__head-actions">
            <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="ondemandOpen = false" />
          </div>
        </header>
        <VDivider />

        <!-- 固定区①：搜索（不随内容滚动，永远够得着） -->
        <div class="magicflow-od-search">
          <div class="magicflow-od-search__grid" :class="{ 'magicflow-od-search__grid--stack': narrow }">
            <VTextField
              v-model="ondemandQuery"
              class="magicflow-od-q"
              density="compact"
              variant="outlined"
              hide-details
              :label="narrow ? undefined : '片名 / 链接'"
              placeholder="片名 / 豆瓣链接 / 磁力"
              prepend-inner-icon="mdi-magnify"
              clearable
              @keyup.enter="runOndemand(false)"
            />
            <!-- ★ 窄屏摘要行：一行交代「用哪些站 / 存哪」，点开才需要动 -->
            <button
              v-if="narrow"
              type="button"
              class="magicflow-od-summary"
              :aria-expanded="odAdvOpen ? 'true' : 'false'"
              @click="odAdvOpen = !odAdvOpen"
            >
              <span class="magicflow-od-summary__val">{{ siteText }}</span>
              <span class="magicflow-od-summary__sep">·</span>
              <span class="magicflow-od-summary__val">{{ taskText }}</span>
              <VIcon :icon="odAdvOpen ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="18" class="magicflow-od-summary__chev" />
            </button>
            <template v-if="showAdv">
              <VSelect
                v-model="ondemandSiteIds"
                class="magicflow-od-sites"
                density="compact"
                variant="outlined"
                hide-details
                :items="siteSelectItems"
                :label="narrow ? undefined : '站点（可多选 · 空＝全部）'"
                :placeholder="narrow ? '全部站点' : undefined"
                multiple
                chips
                closable-chips
              />
              <VSelect
                v-model="ondemandTaskId"
                class="magicflow-od-task"
                density="compact"
                variant="outlined"
                hide-details
                :items="[{ title: '（默认目录）', value: '' }, ...tasks.map((t) => ({ title: `${t.name}·${t.site_name || t.site_id}`, value: t.id }))]"
                :label="narrow ? undefined : '保存目录'"
                :placeholder="narrow ? '默认目录' : undefined"
              />
            </template>
          </div>

          <div class="magicflow-od-search__acts">
            <VBtn
              class="magicflow-od-go"
              :block="narrow"
              color="primary"
              :height="narrow ? 46 : undefined"
              size="small"
              :loading="ondemandBusy === 'preview'"
              @click="runOndemand(false)"
            >搜索</VBtn>
            <VBtn
              class="magicflow-od-help"
              size="x-small"
              variant="text"
              :append-icon="odSearchHint ? 'mdi-chevron-up' : 'mdi-help-circle-outline'"
              @click="odSearchHint = !odSearchHint"
            >说明</VBtn>
          </div>
          <div v-if="odSearchHint" class="magicflow-od-search__hint">
            搜出候选后<strong>勾选</strong> → 点底部<strong>「一并点播」</strong>；<strong>不勾就什么都不会下</strong>，
            魔流不会替你挑。默认勾好的那条是推荐源，不满意直接改勾。
            片名认不出、或站点里没有同名资源时它<strong>不会乱选</strong>，只把站点结果列出来让你自己看
            （标「名称未匹配」的是按关键词捞到的噪音）。下完<strong>自动整理进影视库</strong>。
            候选第一行是<strong>中文名</strong>，灰色小字为站点原名。
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
          <!-- ═══ 点播清单：进行中 / 已完成 两段顺排（已完成默认折叠 3 条）═══ -->
          <div v-if="odView === 'inventory'" class="magicflow-od-inventory">
            <VAlert
              v-if="odMsg"
              :type="odMsg.startsWith('❌') ? 'warning' : 'info'"
              variant="tonal"
              density="compact"
              closable
              class="mb-2 magicflow-od-msg"
              @click:close="odMsg = ''"
            >{{ odMsg }}</VAlert>

            <div class="magicflow-od-sec">
              <span class="magicflow-od-sec__t">点播中</span>
              <span class="magicflow-od-sec__n">{{ odInflight.length }}</span>
            </div>
            <div v-if="!odInflight.length" class="magicflow-od-inventory__empty">
              没有进行中的点播。搜一部片开始吧。
            </div>
            <article v-for="row in odInflight" :key="'od-i-' + row.hash" class="magicflow-od-card">
              <div class="magicflow-od-card__title" :title="odRawTitle(row) || row.hash">{{ odMainTitle(row) || row.hash.slice(0, 12) }}<template v-if="row.year"> ({{ row.year }})</template></div>
              <div v-if="odSubTitle(row)" class="magicflow-od-card__spec">{{ odSubTitle(row) }}</div>
              <div class="magicflow-od-card__sub">
                <span>{{ row.site || '—' }}</span>
                <span v-if="row.size_gb" class="magicflow-od-dot"></span>
                <span v-if="row.size_gb">{{ row.size_gb.toFixed(2) }} GB</span>
                <VChip v-if="row.free" size="x-small" variant="tonal" color="success">免费</VChip>
                <VChip v-if="row.hit_and_run" size="x-small" variant="tonal" color="warning">H&R</VChip>
              </div>
              <div class="magicflow-od-card__prog">
                <VProgressLinear
                  :model-value="odPct(row)"
                  height="6"
                  rounded
                  :color="odIsPaused(row) ? 'warning' : (row.stage === 'downloading' ? 'primary' : 'success')"
                  class="magicflow-od-card__bar"
                />
                <span class="magicflow-od-card__pct">{{ odPct(row).toFixed(1) }}%</span>
              </div>
              <div class="magicflow-od-card__foot">
                <span v-if="row.stage === 'downloading' && !odIsPaused(row) && row.eta_s" class="magicflow-od-card__eta">{{ odEtaText(row.eta_s) }}</span>
                <span v-if="row.stage === 'downloading' && !odIsPaused(row) && row.speed" class="magicflow-od-card__spd">{{ odSpeed(row.speed) }}</span>
                <VChip
                  v-if="odIsPaused(row) || row.stage !== 'downloading'"
                  size="x-small"
                  variant="tonal"
                  :color="odIsPaused(row) ? 'warning' : odStageColor(row.stage)"
                >{{ odIsPaused(row) ? '已暂停' : row.stage_text }}</VChip>
                <div class="magicflow-od-card__acts">
                  <VBtn
                    v-if="!odIsPaused(row)"
                    size="x-small"
                    variant="tonal"
                    class="magicflow-od-act"
                    :loading="odActing === row.hash + ':pause'"
                    @click="actOndemand(row, 'pause')"
                  >暂停</VBtn>
                  <VBtn
                    v-else
                    size="x-small"
                    variant="tonal"
                    color="primary"
                    class="magicflow-od-act"
                    :loading="odActing === row.hash + ':resume'"
                    @click="actOndemand(row, 'resume')"
                  >继续</VBtn>
                  <VBtn
                    size="x-small"
                    variant="text"
                    color="error"
                    class="magicflow-od-act"
                    :loading="odActing === row.hash + ':remove'"
                    @click="actOndemand(row, 'remove')"
                  >移除</VBtn>
                </div>
              </div>
            </article>

            <div class="magicflow-od-sec">
              <span class="magicflow-od-sec__t">已完成</span>
              <span class="magicflow-od-sec__n">{{ odHistory.length }}</span>
              <VSpacer />
              <VBtn
                v-if="odHistory.length > 3"
                size="x-small"
                variant="text"
                color="primary"
                class="magicflow-od-more"
                @click="odDoneAll = !odDoneAll"
              >{{ odDoneAll ? '收起' : `查看全部 ${odHistory.length}` }}</VBtn>
            </div>
            <div v-if="!odHistory.length" class="magicflow-od-inventory__empty">还没有已完成的点播。</div>
            <article
              v-for="row in doneRows"
              :key="'od-h-' + row.hash"
              class="magicflow-od-done"
              :title="odRawTitle(row) || row.subtitle || ''"
            >
              <div class="magicflow-od-done__col">
                <div class="magicflow-od-done__t">{{ odMainTitle(row) || row.hash.slice(0, 12) }}</div>
                <div v-if="odSubTitle(row)" class="magicflow-od-done__spec">{{ odSubTitle(row) }}</div>
              </div>
              <div class="magicflow-od-done__m">
                <span v-if="row.size_gb">{{ row.size_gb.toFixed(2) }} GB</span>
                <span class="magicflow-od-done__ts">{{ tsText(row.added_at) }}</span>
              </div>
            </article>
          </div>

          <!-- ═══ 候选 ═══ -->
          <template v-if="odView === 'candidates'">
            <div v-if="!ondemandResult" class="magicflow-od-inventory__empty">
              输入片名点「搜索」：结果在这里，可勾选多条后一并点播。
            </div>
            <template v-else>
            <div class="magicflow-recommend-dialog__summary mt-1">
              <VChip size="small" :color="ondemandResult.resource?.recognized ? 'success' : 'warning'" variant="tonal">
                {{ ondemandResult.resource?.recognized ? '已识别' : '未识别（按原串搜）' }}
              </VChip>
              <span>{{ ondemandResult.resource?.title }} {{ ondemandResult.resource?.year }}</span>
              <span class="magicflow-od-dot"></span>
              <span>候选 {{ ondemandCandidates.length }}</span>
              <span class="magicflow-od-dot"></span>
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
                :class="{ 'magicflow-ondemand-item--auto': isOndemandAuto(row), 'magicflow-ondemand-item--picked': odPicked.includes(row.enclosure) }"
                @click="pickRow(row)"
              >
                <VCheckbox
                  class="magicflow-ondemand-item__check"
                  :model-value="odPicked.includes(row.enclosure)"
                  density="compact"
                  hide-details
                  :aria-label="'选择 ' + odMainTitle(row, odCtxTitle)"
                  @update:model-value="pickRow(row)"
                  @click.stop
                />
                <div class="magicflow-ondemand-item__body">
                  <div class="magicflow-ondemand-item__title" :title="row.subtitle || row.title">
                    {{ odMainTitle(row, odCtxTitle) }}<span v-if="odAltTitle(row)" class="magicflow-ondemand-item__alt">（{{ odAltTitle(row) }}）</span>
                  </div>
                  <div v-if="odSubTitle(row)" class="magicflow-ondemand-item__sub">{{ odSubTitle(row) }}</div>
                  <div class="magicflow-ondemand-item__meta">
                    <VChip size="x-small" variant="tonal" color="primary">{{ row.site_name || row.site }}</VChip>
                    <span>{{ fmtSizeGb(row.size) }}</span>
                    <span>做种 {{ row.seeders }}</span>
                    <span v-if="Number(row.counted_gb) > 0">实扣 {{ Number(row.counted_gb).toFixed(2) }} GB</span>
                    <span v-if="Number(row.uploadvolumefactor) !== 1">{{ Number(row.uploadvolumefactor) === 2 ? '2X' : Number(row.uploadvolumefactor) + 'X' }} 上传</span>
                    <VChip
                      size="x-small"
                      variant="tonal"
                      :color="odTraffic(row.downloadvolumefactor).color || undefined"
                    >{{ odTraffic(row.downloadvolumefactor).text }}</VChip>
                    <VChip v-if="row.hit_and_run" size="x-small" variant="tonal" color="warning">H&R</VChip>
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
                  <div v-if="odRawTitle(row, odCtxTitle)" class="magicflow-ondemand-item__raw" :title="row.title">{{ row.title }}</div>
                </div>
              </article>
            </div>
            <div v-else class="magicflow-od-inventory__empty">
              没搜到候选。换个片名，或把站点选择清空（＝全部站点）再试一次。
            </div>
            </template>
          </template>
        </VCardText>

        <!-- ★ 吸底条：勾选 → 一并点播（唯一的下种入口） -->
        <div v-if="odView === 'candidates' && ondemandCandidates.length" class="magicflow-od-dock">
          <VCheckbox
            :model-value="allPicked"
            :indeterminate="odPicked.length > 0 && !allPicked"
            density="compact"
            hide-details
            aria-label="全选候选"
            @update:model-value="pickAllCandidates"
          />
          <div class="magicflow-od-dock__cnt">
            <b>已选 {{ odPicked.length }} 条</b>
            <span>{{ pickedGb ? fmtSizeGb(pickedGb) : '还没选' }}</span>
          </div>
          <VBtn
            class="magicflow-od-dock__go"
            color="primary"
            size="small"
            :height="narrow ? 46 : undefined"
            prepend-icon="mdi-download-multiple"
            :loading="odBatchBusy"
            :disabled="!odPicked.length || !!ondemandBusy"
            @click="runBatch"
          >一并点播</VBtn>
        </div>
      </VCard>
    </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 摘要行：随「点播弹窗」自 index.vue 迁入。
     下列**共享选择器**（magicflow-dialog / settings-dialog__head（含 i）/ settings-dialog__title /
     recommend-dialog__head-actions / recommend-dialog__summary / recommend-dialog__note）
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
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-recommend-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  opacity: 0.85;
}

/* ── 弹窗骨架 ───────────────────────────────────────────── */
.magicflow-ondemand-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}
.magicflow-ondemand-dialog--narrow {
  max-block-size: none;
  block-size: 100%;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.magicflow-ondemand-dialog__body {
  padding: 8px 18px 16px;
  overflow: auto;
  flex: 1 1 auto;
  min-height: 0;
  overscroll-behavior: contain;
}
.magicflow-ondemand-dialog--narrow .magicflow-ondemand-dialog__body { padding: 6px 16px 16px; }
.magicflow-ondemand-dialog--narrow .magicflow-settings-dialog__head { padding: 12px 16px 10px; }
.magicflow-ondemand-dialog--narrow .magicflow-settings-dialog__title { font-size: 1.12rem; }

/* ── 搜索区 ─────────────────────────────────────────────── */
.magicflow-od-search { padding: 10px 18px 8px; flex: 0 0 auto; }
.magicflow-ondemand-dialog--narrow .magicflow-od-search { padding: 6px 16px 6px; }
.magicflow-od-search__grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}
.magicflow-od-search__grid--stack { grid-template-columns: 1fr; gap: 0; }

/* 窄屏摘要行：只有窄屏渲染 */
.magicflow-od-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  inline-size: 100%;
  min-block-size: 44px;
  padding: 0;
  border: 0;
  background: none;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  font: inherit;
  font-size: 0.84rem;
  text-align: start;
  cursor: pointer;
}
.magicflow-od-summary__val {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgb(var(--v-theme-on-surface));
}
.magicflow-od-summary__sep { opacity: 0.4; }
.magicflow-od-summary__chev { margin-inline-start: auto; opacity: 0.55; }

.magicflow-od-search__acts { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.magicflow-od-search__grid--stack .magicflow-od-search__acts { flex-wrap: nowrap; }
.magicflow-od-search__acts .magicflow-od-go { min-inline-size: 92px; letter-spacing: 0.02em; }
.magicflow-od-search__grid--stack .magicflow-od-search__acts .magicflow-od-go { flex: 1 1 auto; }
.magicflow-od-search__acts .magicflow-od-help { margin-inline-start: auto; opacity: 0.7; }
.magicflow-od-search__grid--stack .magicflow-od-search__acts .magicflow-od-help { margin-inline-start: 0; flex: 0 0 auto; }
.magicflow-od-search__hint {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.09);
  font-size: 0.78rem;
  line-height: 1.6;
}
.magicflow-od-search__hint strong { color: rgb(var(--v-theme-primary)); }

/* 输入控件：outlined + 44/46 高度，手机上明确是「能点的框」 */
.magicflow-od-q :deep(.v-field),
.magicflow-od-sites :deep(.v-field),
.magicflow-od-task :deep(.v-field) { border-radius: 12px; }
.magicflow-ondemand-dialog--narrow .magicflow-od-q :deep(.v-field),
.magicflow-ondemand-dialog--narrow .magicflow-od-sites :deep(.v-field),
.magicflow-ondemand-dialog--narrow .magicflow-od-task :deep(.v-field) { min-block-size: 46px; }
.magicflow-ondemand-dialog--narrow .magicflow-od-q :deep(.v-field__input),
.magicflow-ondemand-dialog--narrow .magicflow-od-sites :deep(.v-field__input),
.magicflow-ondemand-dialog--narrow .magicflow-od-task :deep(.v-field__input) { font-size: 0.95rem; }
.magicflow-od-search__grid--stack .magicflow-od-sites,
.magicflow-od-search__grid--stack .magicflow-od-task { margin-top: 8px; }

/* ── 候选 / 清单 切换 ──────────────────────────────────── */
.magicflow-od-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 18px;
  flex: 0 0 auto;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.magicflow-ondemand-dialog--narrow .magicflow-od-switch { padding: 6px 16px; }
.magicflow-od-tab { cursor: pointer; user-select: none; }
.magicflow-od-msg { white-space: pre-line; }
.magicflow-od-inventory__empty { font-size: 0.8rem; opacity: 0.7; padding: 8px 2px; }
.magicflow-od-dot {
  inline-size: 3px;
  block-size: 3px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.35;
  display: inline-block;
}

/* ── 分区标题 ───────────────────────────────────────────── */
.magicflow-od-sec {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 14px 0 6px;
}
.magicflow-od-sec:first-of-type { margin-top: 4px; }
.magicflow-od-sec__t { font-size: 0.8rem; font-weight: 600; letter-spacing: 0.02em; opacity: 0.75; }
.magicflow-od-sec__n { font-size: 0.75rem; opacity: 0.45; font-variant-numeric: tabular-nums; }
.magicflow-od-more { letter-spacing: 0; }

/* ── 进行中卡片 ────────────────────────────────────────── */
.magicflow-od-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 12px;
  padding: 11px 12px;
  margin-top: 8px;
  background: rgba(var(--v-theme-on-surface), 0.02);
}
.magicflow-od-card__title {
  font-size: 0.9rem;
  font-weight: 550;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.magicflow-od-card__spec {
  margin-top: 2px;
  font-size: 0.74rem;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.magicflow-od-card__sub {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 3px;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-od-card__prog { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.magicflow-od-card__bar { flex: 1 1 auto; }
.magicflow-od-card__pct { font-size: 0.78rem; font-variant-numeric: tabular-nums; font-weight: 550; }
.magicflow-od-card__foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-od-card__eta {
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
  font-variant-numeric: tabular-nums;
}
.magicflow-od-card__spd { font-variant-numeric: tabular-nums; }
.magicflow-od-card__acts { margin-inline-start: auto; display: flex; align-items: center; gap: 4px; }
.magicflow-ondemand-dialog--narrow .magicflow-od-act { min-block-size: 40px; min-inline-size: 56px; }

/* ── 已完成（紧凑行）───────────────────────────────────── */
.magicflow-od-done {
  display: flex;
  align-items: center;
  gap: 10px;
  min-block-size: 44px;
  padding: 6px 0;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}
.magicflow-od-done:first-of-type { border-top: 0; }
.magicflow-od-done__col {
  flex: 1 1 auto;
  min-inline-size: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.magicflow-od-done__spec {
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.magicflow-od-done__t {
  flex: 1 1 auto;
  min-inline-size: 0;
  font-size: 0.82rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.82);
}
.magicflow-od-done__m {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  white-space: nowrap;
}
.magicflow-od-done__ts { font-variant-numeric: tabular-nums; opacity: 0.75; }

/* ── 候选列表 ──────────────────────────────────────────── */
.magicflow-ondemand-list { display: flex; flex-direction: column; gap: 6px; }
.magicflow-ondemand-item {
  display: flex;
  align-items: flex-start;
  gap: 2px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 10px;
  padding: 8px 10px 8px 2px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.magicflow-ondemand-item--auto { border-color: rgba(var(--v-theme-primary), 0.55); box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.22); }
.magicflow-ondemand-item--picked { background: rgba(var(--v-theme-primary), 0.08); border-color: rgba(var(--v-theme-primary), 0.65); }
.magicflow-ondemand-item__check { flex: 0 0 auto; margin-top: -4px; }
.magicflow-ondemand-item__body { flex: 1 1 auto; min-width: 0; }
.magicflow-ondemand-item__title { font-size: 0.86rem; font-weight: 600; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; }
.magicflow-ondemand-item__alt { font-weight: 400; font-size: 0.94em; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-ondemand-item__sub { margin-top: 2px; font-size: 0.75rem; line-height: 1.45; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; }
.magicflow-ondemand-item__raw { margin-top: 3px; font-size: 0.68rem; line-height: 1.4; opacity: 0.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-ondemand-item__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 5px; font-size: 0.74rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }

/* ── 吸底条 ────────────────────────────────────────────── */
.magicflow-od-dock {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  flex: 0 0 auto;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.10);
  background: rgba(var(--v-theme-surface), 0.96);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.magicflow-ondemand-dialog--narrow .magicflow-od-dock {
  padding: 8px 16px calc(10px + env(safe-area-inset-bottom));
}
.magicflow-od-dock__cnt { display: flex; flex-direction: column; line-height: 1.3; font-size: 0.72rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-od-dock__cnt b { font-size: 0.86rem; color: rgb(var(--v-theme-on-surface)); font-variant-numeric: tabular-nums; }
.magicflow-od-dock__go { margin-inline-start: auto; min-inline-size: 120px; }
</style>
