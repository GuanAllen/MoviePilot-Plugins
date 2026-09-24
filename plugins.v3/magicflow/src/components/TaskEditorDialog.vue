<script setup>
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { cloneTask, normalizeTask } from '../utils'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'save'])
const display = useDisplay()
const formRef = ref(null)
const activeTab = ref('base')
const localTask = ref(cloneTask())

const dialogTitle = computed(() => (localTask.value.id ? '编辑魔力任务' : '新建魔力任务'))
const siteName = computed(() => {
  const site = props.sites.find(item => Number(item.value ?? item.id) === Number(localTask.value.site_id))
  return site?.title || site?.name || '未选择'
})
const scheduleText = computed(() => localTask.value.cron_expression || `每 ${localTask.value.brush_interval || 5} 分钟`)

// 每次打开弹窗都从服务端任务快照重新创建本地草稿。
watch(
  () => props.modelValue,
  visible => {
    if (!visible) return
    localTask.value = cloneTask(props.task)
    activeTab.value = 'base'
  },
)

// 关闭编辑器并丢弃尚未保存的草稿。
function closeDialog() {
  emit('update:modelValue', false)
}

// 校验必填项后提交标准化任务数据。
async function saveTask() {
  const result = await formRef.value?.validate()
  if (result && !result.valid) return
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
            <VTab value="base" prepend-icon="mdi-calendar-clock">基础与调度</VTab>
            <VTab value="magic" prepend-icon="mdi-star-four-points-outline">魔力托管</VTab>
            <VTab value="formula" prepend-icon="mdi-function-variant">魔力公式</VTab>
            <VTab value="selection" prepend-icon="mdi-filter-cog-outline">选种规则</VTab>
            <VTab value="advanced" prepend-icon="mdi-tune-variant">高级</VTab>
          </VTabs>

          <VDivider :vertical="display.mdAndUp.value" />

          <VWindow v-model="activeTab" :touch="false" class="magicflow-editor__window">
            <VWindowItem value="base">
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
                      placeholder="留空自动使用「魔力管家-任务名」"
                    />
                  </VCol>
                  <VCol cols="12">
                    <VTextField v-model="localTask.save_path" label="保存目录" placeholder="留空使用下载器默认目录" />
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
            </VWindowItem>

            <VWindowItem value="magic">
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
            </VWindowItem>

            <VWindowItem value="formula">
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
                    <div class="text-body-2 text-medium-emphasis">沿用站点列表页或 RSS 获取链路</div>
                  </div>
                </header>
                <VRow>
                  <VCol cols="12" md="6">
                    <VSelect
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
                    <div class="text-body-2 text-medium-emphasis">范围字段支持单值或「最小值-最大值」</div>
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
                </dl>
              </section>
            </VWindowItem>
          </VWindow>
        </VForm>
      </VCardText>
    </VCard>
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
