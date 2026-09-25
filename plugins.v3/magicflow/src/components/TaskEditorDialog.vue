<script setup>
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { cloneTask, normalizeTask } from '../utils'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  defaultSavePath: { type: String, default: '' },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'save'])
const display = useDisplay()
const formRef = ref(null)
const activeTab = ref('base')
const localTask = ref(cloneTask())

// 刷流模式：做种满设定天数即清理换新（保种天数），不套用魔力门槛。
const isBrush = computed(() => localTask.value.task_type === 'brush')
const dialogTitle = computed(() => {
  const kind = isBrush.value ? '刷流任务' : '魔力任务'
  return localTask.value.id ? `编辑${kind}` : `新建${kind}`
})
// 编辑器标签页随类型切换：刷流隐藏「魔力托管/魔力公式」，改显「刷流运维」。
const editorTabs = computed(() =>
  isBrush.value
    ? [
        { value: 'base', icon: 'mdi-calendar-clock', label: '基础与调度' },
        { value: 'brush', icon: 'mdi-upload-network-outline', label: '刷流运维' },
        { value: 'selection', icon: 'mdi-filter-cog-outline', label: '选种规则' },
        { value: 'advanced', icon: 'mdi-tune-variant', label: '高级' },
      ]
    : [
        { value: 'base', icon: 'mdi-calendar-clock', label: '基础与调度' },
        { value: 'magic', icon: 'mdi-star-four-points-outline', label: '魔力托管' },
        { value: 'formula', icon: 'mdi-function-variant', label: '魔力公式' },
        { value: 'selection', icon: 'mdi-filter-cog-outline', label: '选种规则' },
        { value: 'advanced', icon: 'mdi-tune-variant', label: '高级' },
      ],
)
const siteName = computed(() => {
  const site = props.sites.find(item => Number(item.value ?? item.id) === Number(localTask.value.site_id))
  return site?.title || site?.name || '未选择'
})
const scheduleText = computed(() => localTask.value.cron_expression || `每 ${localTask.value.brush_interval || 5} 分钟`)
// 刷流「上传速率门槛」可选档（KB/s）：低于该平均速率即判「无上传」。
const uploadRateOptions = [
  { title: '温和 · 100 KB/s（≈ 60 MB / 10 分钟）', value: 100 },
  { title: '适中 · 200 KB/s（≈ 120 MB / 10 分钟，推荐）', value: 200 },
  { title: '激进 · 500 KB/s（≈ 300 MB / 10 分钟）', value: 500 },
  { title: '极限 · 1000 KB/s（1 MB/s，只留最热）', value: 1000 },
]
// 保存目录候选：插件设置的默认目录 + 任务当前值（供统一下拉选择，也可手输）。
const savePathOptions = computed(() => {
  const set = new Set()
  if (props.defaultSavePath) set.add(props.defaultSavePath)
  if (localTask.value.save_path) set.add(localTask.value.save_path)
  return [...set]
})

// 每次打开弹窗都从服务端任务快照重新创建本地草稿。
watch(
  () => props.modelValue,
  visible => {
    if (!visible) return
    localTask.value = cloneTask(props.task)
    activeTab.value = 'base'
  },
)

// 切换任务类型时，若当前标签在新类型下不存在，回到「基础与调度」。
watch(
  () => localTask.value.task_type,
  () => {
    if (!editorTabs.value.some(tab => tab.value === activeTab.value)) activeTab.value = 'base'
  },
)

// 关闭编辑器并丢弃尚未保存的草稿。
function closeDialog() {
  emit('update:modelValue', false)
}

// 未填「任务目标」时的提醒弹窗
const goalWarning = ref(false)

// 是否已填写有效的任务目标（>0）
function hasGoal() {
  const v = localTask.value.goal_value
  return !(v === '' || v === null || v === undefined) && Number(v) > 0
}

// 校验必填项后提交标准化任务数据；未填任务目标先弹窗提醒。
async function saveTask() {
  const result = await formRef.value?.validate()
  if (result && !result.valid) return
  if (!hasGoal()) {
    goalWarning.value = true
    return
  }
  emit('save', normalizeTask(localTask.value))
}

// 确认「仍然保存」（不带目标）
function confirmSaveWithoutGoal() {
  goalWarning.value = false
  emit('save', normalizeTask(localTask.value))
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    scrollable
    :fullscreen="display.smAndDown.value"
    max-width="74rem"
    @update:model-value="value => emit('update:modelValue', value)"
  >
    <VCard class="magicflow-editor">
      <VToolbar color="transparent" density="comfortable" class="magicflow-editor__toolbar">
        <VToolbarTitle>{{ dialogTitle }}</VToolbarTitle>
        <VChip v-if="localTask.id" size="small" variant="tonal" class="mr-2">{{ siteName }}</VChip>
        <VSpacer />
        <VBtn color="primary" variant="flat" prepend-icon="mdi-content-save" :loading="saving" @click="saveTask">
          保存任务
        </VBtn>
        <VBtn icon="mdi-close" variant="text" aria-label="关闭" @click="closeDialog" />
      </VToolbar>
      <VDivider />

      <VCardText class="magicflow-editor__body">
        <VForm ref="formRef" class="magicflow-editor__form" @submit.prevent="saveTask">
          <VTabs
            v-model="activeTab"
            :direction="display.mdAndUp.value ? 'vertical' : 'horizontal'"
            color="primary"
            class="magicflow-editor__tabs"
          >
            <VTab v-for="tab in editorTabs" :key="tab.value" :value="tab.value" :prepend-icon="tab.icon">
              {{ tab.label }}
            </VTab>
          </VTabs>

          <VDivider :vertical="display.mdAndUp.value" />

          <VWindow v-model="activeTab" :touch="false" class="magicflow-editor__window">
            <VWindowItem value="base">
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">任务类型</div>
                    <div class="text-body-2 text-medium-emphasis">决定选种排序与清理策略，建议新建时就选定</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VSelect
                      v-model="localTask.task_type"
                      label="类型"
                      :items="[
                        { title: '刷魔力（魔力/小时最大化）', value: 'bonus' },
                        { title: '刷流（按上传潜力选种，做种满天数轮换）', value: 'brush' },
                      ]"
                      hint="刷流模式在「刷流运维」标签配置，魔力门槛/公式自动隐藏"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
              </section>

              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">任务身份</div>
                    <div class="text-body-2 text-medium-emphasis">每个任务绑定一个站点和下载器</div>
                  </div>
                  <VChip size="small" color="primary" variant="tonal">必填</VChip>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model="localTask.name"
                      label="任务名称"
                      :rules="[value => !!String(value || '').trim() || '请输入任务名称']"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VSelect
                      v-model="localTask.site_id"
                      :items="sites"
                      item-title="name"
                      item-value="id"
                      label="站点"
                      :rules="[value => !!value || '请选择站点']"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VSelect
                      v-model="localTask.downloader"
                      :items="downloaders"
                      label="下载器"
                      :rules="[value => !!value || '请选择下载器']"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model="localTask.brush_tag"
                      label="下载器标签"
                      placeholder="留空自动使用「魔流-任务名」"
                    />
                  </VCol>
                  <VCol cols="12">
                    <VCombobox
                      v-model="localTask.save_path"
                      :items="savePathOptions"
                      label="保存目录"
                      placeholder="留空使用下载器默认目录"
                      hint="默认目录可在插件设置「下载目录」中配置"
                      persistent-hint
                      clearable
                      variant="outlined"
                    />
                  </VCol>
                </VRow>
                <div class="editor-switches">
                  <VSwitch v-model="localTask.enabled" label="启用任务" color="primary" hide-details inset />
                  <VSwitch v-model="localTask.rss_support" label="使用 RSS" color="primary" hide-details inset />
                </div>
              </section>

              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">刷新计划</div>
                    <div class="text-body-2 text-medium-emphasis">选种刷新和做种检查分别调度</div>
                  </div>
                  <span class="text-body-2 text-medium-emphasis">{{ scheduleText }}</span>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.brush_interval"
                      type="number"
                      min="1"
                      max="1440"
                      label="选种刷新周期（分钟）"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.check_interval"
                      type="number"
                      min="1"
                      max="1440"
                      label="做种检查周期（分钟）"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField v-model="localTask.cron_expression" label="CRON 表达式" placeholder="留空使用固定刷新周期" />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField v-model="localTask.active_time_range" label="开启时间段" placeholder="如 00:00-08:00" />
                  </VCol>
                </VRow>
              </section>

              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">任务目标</div>
                    <div class="text-body-2 text-medium-emphasis">
                      {{ isBrush ? '站点上传量达到目标后，任务自动停止' : '站点魔力值达到目标后，任务自动停止' }}
                    </div>
                  </div>
                  <VChip size="small" color="primary" variant="tonal">建议填写</VChip>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.goal_value"
                      type="number"
                      min="0"
                      :step="isBrush ? 100 : 1000"
                      :label="isBrush ? '目标上传量（GB）' : '目标魔力值'"
                      :suffix="isBrush ? 'GB' : '魔力值'"
                      hint="达到目标后任务自动停止（仅停调度，不撤种、不删种）；未填会弹窗提醒"
                      persistent-hint
                      clearable
                    />
                  </VCol>
                </VRow>
              </section>
            </VWindowItem>

            <VWindowItem value="brush">
              <VAlert type="info" variant="tonal" density="compact" class="mb-2" icon="mdi-upload-network-outline">
                刷流模式：<strong>按「上传潜力」运行，有自己的选种标准</strong> —— 只挑<strong>免费（含 2X免费）且有下载者</strong>的种，
                不设做种人数上限、体积/年龄不限（热门大种才是上传主力）；定期检查每个种子，
                <strong>做种满设定天数即清理换新的</strong>（默认 2 天）；没下完也算（只要在上传）。
              </VAlert>
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">刷流轮换</div>
                    <div class="text-body-2 text-medium-emphasis">做种满设定天数即清理换新（默认 2 天）</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.brush_seed_days"
                      type="number"
                      min="0"
                      max="365"
                      label="保种天数"
                      hint="做种满该天数后清理换新；0 = 不按天数，改回「无上传」判定"
                      suffix="天"
                      persistent-hint
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.brush_min_leechers"
                      type="number"
                      min="0"
                      label="最小下载人数"
                      hint="只挑下载人数≥该值的种（有下载需求才值得下）"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
              </section>

              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">抓取与并发</div>
                    <div class="text-body-2 text-medium-emphasis">刷流只看最新页（免费热种在最新页），不深翻</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="6"><VTextField v-model.number="localTask.max_add_per_run" type="number" min="1" label="单轮最多新增" placeholder="默认 10" suffix="个/轮" clearable /></VCol>
                  <VCol cols="12" md="6"><VTextField v-model.number="localTask.max_download_concurrent" type="number" min="1" label="同时下载上限" placeholder="默认 10" suffix="个" clearable /></VCol>
                  <VCol cols="12" md="6"><VTextField v-model.number="localTask.top_n" type="number" min="1" label="每轮参评候选数" placeholder="默认 30" suffix="个" clearable /></VCol>
                  <VCol cols="12" md="6"><VTextField v-model.number="localTask.browse_pages" type="number" min="1" max="60" label="每轮翻页数" placeholder="默认 3" suffix="页" clearable /></VCol>
                </VRow>
              </section>

              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">复用与清理</div>
                    <div class="text-body-2 text-medium-emphasis">优先复用本机已有资源；做种满天数 / 促销失效的种子清理</div>
                  </div>
                </header>
                <div class="editor-switches">
                  <VSwitch v-model="localTask.refill_when_empty" label="清理后主动补种" color="primary" hide-details inset />
                  <VSwitch v-model="localTask.reuse_existing" label="复用本机已有资源（辅种）" color="primary" hide-details inset />
                  <VSwitch v-model="localTask.reuse_verify" :disabled="!localTask.reuse_existing" label="辅种前先校验（不匹配自动撤销）" color="primary" hide-details inset />
                  <VSwitch v-model="localTask.cleanup_no_progress" label="清理无进度种子（停滞/出错且进度为 0）" color="primary" hide-details inset />
                  <VSwitch v-model="localTask.cleanup_slow_progress" label="清理下载过慢的种子（长期下不完腾名额）" color="primary" hide-details inset />
                  <VSwitch v-model="localTask.purge_unfree_incomplete" label="清理「已不再免费且未下完」的种子" color="primary" hide-details inset />
                  <VSwitch v-model="localTask.auto_resume_paused" label="自动恢复被暂停的已完成种子" color="primary" hide-details inset />
                  <VSwitch v-model="localTask.delete_files" label="删种同时删除文件" color="primary" hide-details inset />
                </div>
                <VRow v-if="localTask.cleanup_no_progress">
                  <VCol cols="12" md="6"><VTextField v-model.number="localTask.no_progress_minutes" type="number" min="1" label="无进度判定时长（分钟）" persistent-hint /></VCol>
                  <VCol cols="12" md="6"><VTextField v-model.number="localTask.seen_cooldown_hours" type="number" min="0" label="已处理去重窗口（小时）" hint="同一候选在该时长内不重复拉取，0 = 不跳过" persistent-hint /></VCol>
                </VRow>
                <VRow v-if="localTask.cleanup_slow_progress">
                  <VCol cols="12" md="6"><VTextField v-model.number="localTask.slow_progress_grace_minutes" type="number" min="1" label="慢种宽限（分钟）" persistent-hint /></VCol>
                  <VCol cols="12" md="6"><VTextField v-model.number="localTask.slow_progress_max_hours" type="number" min="1" label="预计下完上限（小时）" persistent-hint /></VCol>
                </VRow>
              </section>
            </VWindowItem>

            <VWindowItem v-if="!isBrush" value="magic">
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">魔力门槛（留空 = 自动）</div>
                    <div class="text-body-2 text-medium-emphasis">留空由公式与实时数据自动推算，手填即覆盖</div>
                  </div>
                  <VChip size="small" color="primary" variant="tonal">可自动</VChip>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.min_bonus_per_hour"
                      type="number"
                      min="0"
                      step="0.01"
                      label="每小时最低魔力"
                      placeholder="留空 = 种子魔力中位数 × 0.5"
                      suffix="/h"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.disk_size_gb"
                      type="number"
                      min="0"
                      step="10"
                      label="保种体积上限"
                      placeholder="留空 = 不限"
                      suffix="GB"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.max_keep_torrents"
                      type="number"
                      min="1"
                      label="最多保留种子数"
                      placeholder="留空 = 保种体积 ÷ 平均种子大小"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.max_add_per_run"
                      type="number"
                      min="1"
                      label="单轮最多新增"
                      placeholder="默认 10"
                      suffix="个/轮"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.max_download_concurrent"
                      type="number"
                      min="1"
                      label="同时下载上限"
                      placeholder="默认 10"
                      suffix="个"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.top_n"
                      type="number"
                      min="1"
                      label="每轮参评候选数"
                      placeholder="默认 30"
                      suffix="个"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.browse_pages"
                      type="number"
                      min="1"
                      max="60"
                      label="每轮翻页数"
                      placeholder="默认 3"
                      suffix="页"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.bonus_protect_threshold"
                      type="number"
                      min="0"
                      label="魔力保护阈值"
                      placeholder="留空 = 站点当前魔力"
                      clearable
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.min_bonus_to_keep"
                      type="number"
                      min="0"
                      label="最低魔力保底值"
                      placeholder="留空 = 0（不设保底）"
                      clearable
                      :rules="[
                        value =>
                          Number(value || 0) < Number(localTask.bonus_protect_threshold || 999999999) ||
                          '最低魔力保底值应小于魔力保护阈值',
                      ]"
                    />
                  </VCol>
                </VRow>
                <div class="editor-switches">
                  <VSwitch v-model="localTask.refill_when_empty" label="清理后主动补种" color="primary" hide-details inset />
                  <VSwitch
                    v-model="localTask.reuse_existing"
                    label="复用本机已有资源（辅种）"
                    color="primary"
                    hide-details
                    inset
                  />
                  <VSwitch
                    v-model="localTask.reuse_verify"
                    :disabled="!localTask.reuse_existing"
                    label="辅种前先校验（不匹配自动撤销）"
                    color="primary"
                    hide-details
                    inset
                  />
                  <VSwitch
                    v-model="localTask.cleanup_no_progress"
                    label="每次运行清理无进度种子（停滞/出错且进度为 0）"
                    color="primary"
                    hide-details
                    inset
                  />
                  <VSwitch
                    v-model="localTask.cleanup_slow_progress"
                    label="清理下载过慢的种子（速度÷体积算 ETA，长期下不完的腾名额）"
                    color="primary"
                    hide-details
                    inset
                  />
                  <VSwitch
                    v-model="localTask.purge_unfree_incomplete"
                    label="检查时清理「已不再免费且未下完」的种子（回站点核对促销）"
                    color="primary"
                    hide-details
                    inset
                  />
                  <VSwitch
                    v-model="localTask.auto_resume_paused"
                    label="自动恢复被暂停的已完成种子（重新做种）"
                    color="primary"
                    hide-details
                    inset
                  />
                </div>
                <VRow>
                  <VCol cols="12" md="6">
                    <VSelect
                      v-model="localTask.ti_source"
                      :items="[
                        { title: '发布时长（站点公式口径，推荐）', value: 'publish' },
                        { title: '做种时长（qB 统计）', value: 'seed_time' },
                      ]"
                      label="Ti 口径（做种时间因子）"
                      hint="候选排序与做种汇总使用同一口径；取不到发布时间时自动回落做种时长"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
                <VRow v-if="localTask.cleanup_no_progress">
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.no_progress_minutes"
                      type="number"
                      min="1"
                      label="无进度判定时长（分钟）"
                      hint="加入下载器超过该时长仍无进度才清理"
                      persistent-hint
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.seen_cooldown_hours"
                      type="number"
                      min="0"
                      label="已处理去重窗口（小时）"
                      hint="同一候选在该时长内不重复拉取，0 = 不跳过"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
                <VRow v-if="localTask.cleanup_slow_progress">
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.slow_progress_grace_minutes"
                      type="number"
                      min="1"
                      label="慢种宽限（分钟）"
                      hint="种子加入后该时长内不判「慢」，给新种起步时间"
                      persistent-hint
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.slow_progress_max_hours"
                      type="number"
                      min="1"
                      label="预计下完上限（小时）"
                      hint="按当前速度（速度÷体积）预计还要超过该小时数才下完 → 清理"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
              </section>

              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">删种保护</div>
                    <div class="text-body-2 text-medium-emphasis">保护期内、受保护与 H&R 种子永不删除</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.min_seed_time"
                      type="number"
                      min="0"
                      label="最短做种时间（小时）"
                      placeholder="0 = 不设保护期"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.min_ratio"
                      type="number"
                      min="0"
                      step="0.01"
                      label="最低分享率"
                      placeholder="0 = 不限"
                    />
                  </VCol>
                </VRow>
                <div class="editor-switches">
                  <VSwitch v-model="localTask.delete_files" label="删种同时删除文件" color="primary" hide-details inset />
                </div>
              </section>
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">完美种保护</div>
                    <div class="text-body-2 text-medium-emphasis">优质老种（非零魔 · 做种人数少 · 挂得够老）永久保留，不参与任何清理——魔力靠「养」，越老越肥</div>
                  </div>
                </header>
                <div class="editor-switches">
                  <VSwitch v-model="localTask.protect_perfect" label="启用完美种保护（满足条件的种子永不清理）" color="primary" hide-details inset />
                </div>
                <VRow v-if="localTask.protect_perfect">
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.perfect_max_seeders"
                      type="number"
                      min="0"
                      label="完美种：做种人数上限"
                      hint="站内做种人数 ≤ 该值才算完美（0 = 不限制）"
                      suffix="人"
                      persistent-hint
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.perfect_min_weeks"
                      type="number"
                      min="0"
                      step="0.5"
                      label="完美种：做种周数下限"
                      hint="做种周数 ≥ 该值才算完美（0 = 不限制）"
                      suffix="周"
                      persistent-hint
                    />
                  </VCol>
                </VRow>
              </section>
            </VWindowItem>

            <VWindowItem v-if="!isBrush" value="formula">
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">魔力公式参数</div>
                    <div class="text-body-2 text-medium-emphasis">
                      留空使用站点预设 / NexusPHP 标准式（T0=5，N0=7，B0=100，L=300）
                    </div>
                  </div>
                  <VChip size="small" color="primary" variant="tonal">高级</VChip>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.bonus_t0"
                      type="number"
                      min="0.1"
                      step="0.1"
                      label="生存时间参数 T0"
                      placeholder="默认 5"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.bonus_n0"
                      type="number"
                      min="2"
                      label="做种人数参数 N0"
                      placeholder="默认 7"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.bonus_b0"
                      type="number"
                      min="0.1"
                      step="0.1"
                      label="每小时魔力上限 B0"
                      placeholder="默认 100"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.bonus_l"
                      type="number"
                      min="0.1"
                      step="0.1"
                      label="曲线参数 L"
                      placeholder="默认 300"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField
                      v-model.number="localTask.bonus_zero_weight"
                      type="number"
                      min="0"
                      step="0.05"
                      label="零魔种子权重"
                      placeholder="默认 0.2"
                    />
                  </VCol>
                </VRow>
              </section>
            </VWindowItem>

            <VWindowItem value="selection">
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">来源与促销</div>
                    <div class="text-body-2 text-medium-emphasis">{{ isBrush ? '刷流只看站点最新页（免费热种在最新页），不做游标深翻' : '沿用站点列表页或 RSS 获取链路' }}</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VSelect
                      v-if="isBrush"
                      :model-value="'free'"
                      label="促销"
                      :items="[{ title: '免费（含 2X 免费）', value: 'free' }]"
                      disabled
                      hint="刷流固定只抓免费种（下载不计量），保障分享率"
                      persistent-hint
                    />
                    <VSelect
                      v-else
                      v-model="localTask.freeleech"
                      label="促销"
                      :items="[
                        { title: '全部（包括普通）', value: '' },
                        { title: '免费', value: 'free' },
                        { title: '2X 免费', value: '2xfree' },
                      ]"
                    />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VSelect
                      v-model="localTask.hr"
                      label="排除 H&R"
                      :items="[
                        { title: '是', value: 'yes' },
                        { title: '否', value: 'no' },
                      ]"
                    />
                  </VCol>
                </VRow>
              </section>

              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">候选过滤</div>
                    <div class="text-body-2 text-medium-emphasis">{{ isBrush ? '刷流默认不限人数 / 体积 / 年龄（留空即为不限），如需收敛再填；范围支持单值或「最小值-最大值」' : '范围字段支持单值或「最小值-最大值」' }}</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="4">
                    <VTextField v-model="localTask.size" label="种子大小（GB）" placeholder="10-80" />
                  </VCol>
                  <VCol cols="12" md="4">
                    <VTextField v-model="localTask.seeder" label="做种人数" placeholder="1-10" />
                  </VCol>
                  <VCol cols="12" md="4">
                    <VTextField v-model="localTask.pubtime" label="发布时间（分钟）" placeholder="5-120" />
                  </VCol>
                  <VCol cols="12">
                    <VTextField v-model="localTask.include" label="包含规则" placeholder="支持正则表达式" />
                  </VCol>
                  <VCol cols="12">
                    <VTextField v-model="localTask.exclude" label="排除规则" placeholder="支持正则表达式" />
                  </VCol>
                </VRow>
                <div class="editor-switches">
                  <VSwitch
                    v-if="!isBrush"
                    v-model="localTask.exclude_zero_bonus"
                    label="不选零魔种子（Wi=0.2）"
                    color="primary"
                    hide-details
                    inset
                  />
                </div>
              </section>
            </VWindowItem>

            <VWindowItem value="advanced">
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">单种限速</div>
                    <div class="text-body-2 text-medium-emphasis">只作用于当前任务新添加的种子</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VTextField v-model.number="localTask.up_speed" type="number" min="1" label="上传限速（KB/s）" />
                  </VCol>
                  <VCol cols="12" md="6">
                    <VTextField v-model.number="localTask.dl_speed" type="number" min="1" label="下载限速（KB/s）" />
                  </VCol>
                </VRow>
              </section>
              <section class="editor-section">
                <header class="editor-section__head">
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">生效预览</div>
                    <div class="text-body-2 text-medium-emphasis">保存后立即写入调度，无需重启插件</div>
                  </div>
                </header>
                <dl class="magicflow-facts magicflow-facts--two">
                  <div><dt>站点</dt><dd>{{ siteName }}</dd></div>
                  <div><dt>下载器</dt><dd>{{ localTask.downloader || '未选择' }}</dd></div>
                  <div><dt>调度</dt><dd>{{ scheduleText }}</dd></div>
                  <div><dt>开启时段</dt><dd>{{ localTask.active_time_range || '全天' }}</dd></div>
                  <div>
                    <dt>任务目标</dt>
                    <dd>{{ hasGoal() ? (isBrush ? `${localTask.goal_value} GB 上传量` : `${localTask.goal_value} 魔力值`) : '未设置' }}</dd>
                  </div>
                </dl>
              </section>
            </VWindowItem>
          </VWindow>
        </VForm>
      </VCardText>
    </VCard>

    <VDialog v-model="goalWarning" max-width="30rem">
      <VCard class="pa-2">
        <VCardText>
          <div class="d-flex align-center mb-2">
            <VIcon icon="mdi-flag-alert" color="warning" class="mr-2" />
            <span class="text-subtitle-1 font-weight-medium">尚未设置任务目标</span>
          </div>
          <div class="text-body-2 text-medium-emphasis">
            建议为每个任务设置目标，达到后会自动停止：
            <strong>{{ isBrush ? '站点上传量（GB）' : '站点魔力值' }}</strong>。
            未设置目标的任务将一直运行下去。
          </div>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="goalWarning = false">返回填写</VBtn>
          <VBtn color="warning" variant="flat" @click="confirmSaveWithoutGoal">仍然保存</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </VDialog>
</template>
<style scoped>
.magicflow-editor {
  /* 深色磨砂主题（与工作台保持一致）*/
  --v-theme-surface: 17, 23, 43;
  --v-theme-on-surface: 231, 234, 246;
  --v-theme-surface-variant: 38, 46, 78;
  --v-theme-on-surface-variant: 200, 206, 232;
  --v-theme-surface-light: 26, 32, 56;
  --v-theme-outline: 92, 102, 152;
  --v-theme-primary: 139, 123, 240;
  --v-theme-on-primary: 255, 255, 255;
  --v-theme-error: 235, 100, 122;
  max-block-size: min(90dvh, 58rem);
  background: rgba(20, 26, 48, 0.94) !important;
  border: 1px solid rgba(140, 150, 220, 0.14);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}

.magicflow-editor__toolbar {
  flex: 0 0 auto;
  padding-inline: 8px;
  z-index: 4;
  backdrop-filter: blur(var(--transparent-blur, 0px));
  background-color: rgba(var(--v-theme-surface), var(--transparent-opacity-heavy, 1));
}

.magicflow-editor__body {
  padding: 0;
}

.magicflow-editor__form {
  display: grid;
  grid-template-columns: 12rem auto minmax(0, 1fr) minmax(12rem, 0.34fr);
  min-block-size: 34rem;
}

.magicflow-editor__tabs {
  padding: 12px 8px;
}

.magicflow-editor__window {
  min-inline-size: 0;
  padding: 20px;
}

.editor-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-section + .editor-section {
  margin-block-start: 28px;
  padding-block-start: 24px;
  border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.editor-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.editor-switches {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
}

.magicflow-editor__summary {
  padding: 20px 16px;
  border-inline-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.magicflow-editor__summary dl {
  display: grid;
  gap: 12px;
  margin: 18px 0 0;
}

.magicflow-editor__summary dl > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.magicflow-editor__summary dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-editor__summary dd {
  margin: 0;
  text-align: end;
  overflow-wrap: anywhere;
}

@media (max-width: 959px) {
  .magicflow-editor {
    max-block-size: none;
  }

  .magicflow-editor__form {
    grid-template-columns: 1fr;
    min-block-size: 0;
  }

  .magicflow-editor__tabs {
    max-inline-size: 100%;
    padding-block: 0;
    overflow-x: auto;
  }

  .magicflow-editor__window {
    padding: 16px;
  }

  .magicflow-editor__summary {
    border-inline-start: 0;
    border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  }
}

@media (max-width: 599px) {
  .magicflow-editor__toolbar :deep(.v-toolbar-title) {
    font-size: 1rem;
  }

  .magicflow-editor__toolbar :deep(.v-btn__content) {
    white-space: normal;
  }

}
</style>
<style scoped>
.magicflow-facts {
  display: grid;
  gap: 11px;
  margin: 18px 0 0;
}
.magicflow-facts--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.magicflow-facts > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-inline-size: 0;
}
.magicflow-facts dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-facts dd {
  margin: 0;
  text-align: end;
  overflow-wrap: anywhere;
}
</style>
