<script setup>
// MagicFlow 前端 · 云盘归档弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 记录查找纯函数（pickCloudRecord）自 composables/useCloud.js 具名导入复用 —— 单一真值源。
import { computed } from 'vue'
import { cloudStatusMeta } from '../../../../utils'
import { pickCloudRecord } from '../../composables/useCloud'

const cloudOpen = defineModel({ type: Boolean, default: false })
const cloudLimit = defineModel('limit', { type: Number, default: 50 })

const props = defineProps({
  // 云盘归档状态（useCloud 的展示态打包；state.data = cloudState 全局状态）
  state: { type: Object, default: () => ({}) },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh', 'plan', 'run', 'test', 'upload'])

const cloudState = computed(() => props.state.data || null)
const cloudCfg = computed(() => (cloudState.value || {}).cfg || {})
const cloudPlanItems = computed(() => props.state.planItems || [])
const cloudPlanStats = computed(() => props.state.planStats || null)
const cloudLoading = computed(() => Boolean(props.state.loading))
const cloudPlanning = computed(() => Boolean(props.state.planning))
const cloudRunning = computed(() => Boolean(props.state.running))
const cloudTesting = computed(() => Boolean(props.state.testing))
const cloudTestMsg = computed(() => props.state.testMsg || '')
const cloudTestOk = computed(() => Boolean(props.state.testOk))
const cloudUploadingPath = computed(() => props.state.uploadingPath || '')

function loadCloud() { emit('refresh') }
function testCloud() { emit('test') }
function planCloud() { emit('plan') }
function runCloud(dryRun) { emit('run', dryRun) }
function uploadCloudOne(item) { emit('upload', item) }
function cloudRecordFor(item) { return pickCloudRecord((cloudState.value || {}).records, item) }
</script>

<template>
  <VDialog v-model="cloudOpen" max-width="52rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-cloud-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">云盘归档</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" :loading="cloudLoading" @click="loadCloud">刷新</VBtn>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="cloudOpen = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-cloud-dialog__body">
        <VAlert v-if="!cloudCfg.enabled" type="info" variant="tonal" density="compact" class="mb-2">
          云盘归档未启用（「插件设置 → 云盘归档」里开启并填 OpenList 地址 / Token）。
        </VAlert>
        <div class="magicflow-cloud-dialog__summary">
          <span><strong>{{ cloudPlanStats?.pending ?? 0 }}</strong> 待上传</span>
          <i>·</i>
          <span><strong>{{ cloudPlanStats?.remote_exists ?? 0 }}</strong> 远端已有</span>
          <i>·</i>
          <span><strong>{{ cloudPlanStats?.done ?? 0 }}</strong> 已归档</span>
          <i>·</i>
          <span>{{ cloudPlanStats?.pending_gb ?? 0 }} GB</span>
          <i>·</i>
          <span><strong>{{ cloudState?.record_count ?? 0 }}</strong> 条记录</span>
        </div>
        <div class="magicflow-cloud-dialog__note">
          上传到 OpenList 可写存储 → 同一夸克目录 → Strm 视图自动生成播放指针 → 影视直接能看。
          默认<strong>只上传不删除</strong>；本地删除需单独确认。
        </div>
        <div class="magicflow-cloud-dialog__actions">
          <VBtn variant="tonal" color="primary" size="small" prepend-icon="mdi-connection" :loading="cloudTesting" @click="testCloud">测试连接</VBtn>
          <VBtn variant="tonal" size="small" prepend-icon="mdi-clipboard-list-outline" :loading="cloudPlanning" @click="planCloud">扫描候选</VBtn>
          <VBtn variant="tonal" size="small" prepend-icon="mdi-play-circle-outline" :loading="cloudRunning" @click="runCloud(true)">演练归档</VBtn>
          <VBtn color="primary" variant="flat" size="small" prepend-icon="mdi-cloud-upload-outline" :loading="cloudRunning" @click="runCloud(false)">开始归档</VBtn>
          <VTextField
            v-model.number="cloudLimit"
            label="本轮条数"
            type="number"
            variant="outlined"
            density="compact"
            hide-details
            class="magicflow-cloud-dialog__limit"
          />
        </div>
        <VAlert v-if="cloudTestMsg" :type="cloudTestOk ? 'success' : 'error'" variant="tonal" density="compact" class="my-2">
          {{ cloudTestMsg }}
        </VAlert>
        <VAlert v-if="cloudState?.running" type="info" variant="tonal" density="compact" class="my-2">
          归档任务正在后台执行（可关闭本窗口，进度看下方列表与「操作记录」）。
        </VAlert>
        <VSheet tag="section" class="magicflow-panel app-surface-static mt-2">
          <header class="magicflow-panel__head">
            <div>
              <div class="text-subtitle-2 font-weight-medium">归档候选</div>
              <div class="text-body-2 text-medium-emphasis">点「扫描候选」列出可上传文件；逐条点「上传」立即传该文件（后台执行）</div>
            </div>
          </header>
          <p v-if="cloudLoading && !cloudPlanItems.length" class="magicflow-settings-hint">加载中…</p>
          <p v-else-if="!cloudPlanItems.length" class="magicflow-settings-hint">
            还没有候选。点上方「扫描候选」；若为 0，检查设置里的「扫描目录 / 体积范围 / 最小入库天数」。
          </p>
          <div v-for="it in cloudPlanItems" :key="it.path" class="magicflow-cloud-row">
            <div class="magicflow-cloud-row__main">
              <div class="magicflow-cloud-row__title">{{ it.name }}</div>
              <div class="magicflow-cloud-row__sub">{{ it.rel }} · {{ it.size_gb }} GB</div>
              <div v-if="it.message || (cloudRecordFor(it) || {}).error" class="magicflow-cloud-row__msg">
                {{ it.message || (cloudRecordFor(it) || {}).error }}
              </div>
            </div>
            <div class="magicflow-cloud-row__side">
              <VChip size="x-small" variant="tonal" :color="cloudStatusMeta(cloudRecordFor(it)?.status || it.status).color">
                {{ cloudStatusMeta(cloudRecordFor(it)?.status || it.status).text }}
              </VChip>
              <VBtn
                size="x-small"
                variant="tonal"
                color="primary"
                :loading="cloudUploadingPath === it.path"
                @click="uploadCloudOne(it)"
              >上传</VBtn>
            </div>
          </div>
        </VSheet>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 摘要行 / 面板：随「云盘归档弹窗」自 index.vue 迁入。
     下列**共享选择器**（magicflow-dialog / settings-dialog__head·__title / recommend-dialog__head-actions /
     panel / panel__head）父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。
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
.magicflow-panel {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
  min-inline-size: 0;
  padding: 16px;
}
.magicflow-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

/* ── 云盘归档弹窗（专属选择器，随组件迁入）────────────────────── */
.magicflow-cloud-dialog__body {
  max-block-size: min(70dvh, 44rem);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.magicflow-cloud-dialog__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  font-size: 0.85rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}

.magicflow-cloud-dialog__summary strong {
  font-size: 1.05rem;
  color: rgb(var(--v-theme-primary));
}

.magicflow-cloud-dialog__summary i {
  font-style: normal;
  opacity: var(--mf-op-dim);
}

.magicflow-cloud-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  opacity: 0.85;
}

.magicflow-cloud-dialog__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.magicflow-cloud-dialog__limit {
  inline-size: 7.5rem;
}

.magicflow-cloud-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-block: 8px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-cloud-row:last-child {
  border-block-end: 0;
}

.magicflow-cloud-row__main {
  flex: 1 1 auto;
  min-inline-size: 0;
}

.magicflow-cloud-row__title {
  font-size: 0.88rem;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.magicflow-cloud-row__sub {
  font-size: 0.76rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  overflow-wrap: anywhere;
}

.magicflow-cloud-row__msg {
  margin-block-start: 2px;
  font-size: 0.74rem;
  color: rgb(var(--v-theme-warning));
  overflow-wrap: anywhere;
}

.magicflow-cloud-row__side {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

@media (max-width: 699px) {
  .magicflow-cloud-dialog__actions {
    gap: 6px;
  }

  .magicflow-cloud-dialog__limit {
    inline-size: 100%;
  }

  .magicflow-cloud-row {
    flex-direction: column;
    align-items: stretch;
  }

  .magicflow-cloud-row__side {
    justify-content: space-between;
  }
}

/* ── ★ 功能弹窗统一：卡片纵向 flex + 正文吃满（原 index.vue 的共享组里含 .magicflow-cloud-dialog，
      随组件迁入；放在上方专属块之后，保证 max-block-size 覆盖生效）── */
.magicflow-cloud-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}
.magicflow-cloud-dialog__body {
  flex: 1 1 auto;
  min-block-size: 0;
  max-block-size: none;
  overflow-y: auto;
  overscroll-behavior: contain;
}

@media (max-width: 699px) {
  .magicflow-panel {
    padding: 14px;
  }

  .magicflow-panel__head {
    flex-wrap: wrap;
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
