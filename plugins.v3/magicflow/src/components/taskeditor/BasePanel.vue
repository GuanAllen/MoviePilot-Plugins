<script setup>
// MagicFlow · 任务编辑器「基础与调度」面板 —— P6 自 components/TaskEditorDialog.vue **纯搬家**。
// props 下 / emit 上：面板不直接读写父状态；双向字段走 defineModel，动作走 emit，只读值走 props。
import { formatBytes } from '../../utils'

const emit = defineEmits([
  'apply-preset', 'site-change', 'save-path-change', 'remember-save-path', 'load-pool', 'pct-change',
])

// 双向绑定字段：父 localTask.<snake_case> ↔ defineModel(<camelCase>)
const siteId = defineModel('siteId')
const name = defineModel('name')
const downloader = defineModel('downloader')
const brushTag = defineModel('brushTag')
const savePath = defineModel('savePath')
const enabled = defineModel('enabled')
const rssSupport = defineModel('rssSupport')
const brushInterval = defineModel('brushInterval')
const checkInterval = defineModel('checkInterval')
const cronExpression = defineModel('cronExpression')
const activeTimeRange = defineModel('activeTimeRange')
const goalValue = defineModel('goalValue')
// 磁盘体积占比（父 ref，非 localTask 字段，但同为双向绑定）
const poolPct = defineModel('poolPct')

// 只读数据 / 计算值（父照常传）
defineProps({
  presets: { type: Array, default: () => [] },
  presetKey: { type: String, default: '' },
  simpleMode: { type: Boolean, default: false },
  presetPatchCount: { type: Number, default: 0 },
  sites: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  autoTag: { type: String, default: '' },
  savePathOptions: { type: Array, default: () => [] },
  pool: { type: Object, default: null },
  poolOver: { type: Boolean, default: false },
  poolError: { type: String, default: '' },
  poolLoading: { type: Boolean, default: false },
  poolFreeText: { type: String, default: '—' },
  poolBudgetText: { type: String, default: '' },
  scheduleText: { type: String, default: '' },
  isBrush: { type: Boolean, default: false },
})
</script>

<template>
  <section class="editor-section">
    <header class="editor-section__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">任务模板</div>
        <div class="text-body-2 text-medium-emphasis">
          选一个就行 —— 选种/清理/限速/复用等参数按模板自动配好，站点·目录·目标自己定
        </div>
      </div>
    </header>
    <div class="editor-presets">
      <button
        v-for="p in presets"
        :key="p.key"
        type="button"
        class="editor-preset"
        :class="{ 'is-active': presetKey === p.key }"
        @click="emit('apply-preset', p.key)"
      >
        <VIcon :icon="p.icon" size="18" />
        <span class="editor-preset__title">{{ p.title }}</span>
        <span class="editor-preset__desc">{{ p.desc }}</span>
      </button>
    </div>
    <div v-if="simpleMode" class="editor-simple-note">
      <VIcon icon="mdi-auto-fix" size="14" />
      <span>已自动配置 {{ presetPatchCount }} 项专业参数（调度 5 分钟 · 复用辅种 · 清理低效 · 限速两档 · 体积上限）</span>
      <button type="button" class="editor-simple-note__link" @click="emit('apply-preset', 'custom')">展开全部参数</button>
    </div>
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
        <VSelect
          v-model="siteId"
          :items="sites"
          item-title="name"
          item-value="id"
          label="站点"
          :rules="[value => !!value || '请选择站点']"
          @update:model-value="emit('site-change')"
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model="name"
          label="任务名称"
          hint="选站点后自动填「站点·模板名」，可手改"
          :rules="[value => !!String(value || '').trim() || '请输入任务名称']"
        />
      </VCol>
      <VCol v-if="downloaders.length > 1" cols="12" md="6">
        <VSelect
          v-model="downloader"
          :items="downloaders"
          label="下载器"
          :rules="[value => !!value || '请选择下载器']"
        />
      </VCol>
      <VCol v-if="!simpleMode" cols="12" md="6">
        <VTextField
          v-model="brushTag"
          label="下载器标签"
          readonly
          prepend-inner-icon="mdi-lock-outline"
          :hint="`自动：${autoTag || '魔流-站点-职务'}（按站点+任务类型派生，只读）`"
          persistent-hint
        />
      </VCol>
      <VCol cols="12">
        <VCombobox
          v-model="savePath"
          :items="savePathOptions"
          label="保存目录"
          @update:model-value="emit('save-path-change')"
          @update:focused="focused => { if (!focused) emit('remember-save-path', savePath) }"
          placeholder="留空使用下载器默认目录"
          hint="默认目录可在插件设置「下载目录」中配置"
          persistent-hint
          clearable
          variant="outlined"
        />
      </VCol>
      <VCol cols="12">
        <div class="editor-pool" :class="{ 'is-warn': poolOver, 'is-error': !!poolError }">
          <VIcon :icon="poolOver ? 'mdi-alert-outline' : 'mdi-harddisk'" size="14" />
          <template v-if="pool">
            <span>
            磁盘 {{ pool.path }} · 已用 {{ pool.pct.toFixed(0) }}%（{{ formatBytes(pool.used_gb * 1024 ** 3) }} / {{ formatBytes(pool.total_gb * 1024 ** 3) }}）· 按 80% 阈值还能再放 {{ poolFreeText }}
          </span>
            <span v-if="poolOver" class="editor-pool__hint">已超 80%，建议先清理再加种</span>
          </template>
          <template v-else>
            <span>{{ poolLoading ? '正在读取磁盘空间…' : (poolError || '磁盘空间未知') }}</span>
          </template>
          <button type="button" class="editor-pool__link" @click="emit('load-pool')">刷新</button>
        </div>
        <div v-if="simpleMode && pool" class="editor-quota">
          <div class="editor-quota__head">
            <span>本任务最多占多少</span>
            <strong>{{ poolBudgetText }}</strong>
          </div>
          <VSlider
            v-model="poolPct"
            :min="0"
            :max="100"
            :step="5"
            color="primary"
            hide-details
            density="compact"
            :disabled="poolOver"
            @update:model-value="emit('pct-change')"
          />
          <div class="editor-quota__foot">
            <span>{{ poolPct }}% · 占磁盘剩余可用（{{ poolFreeText }}）</span>
            <span v-if="poolOver" class="editor-pool__hint">磁盘已超 80%，先清理再加种</span>
          </div>
        </div>
      </VCol>
    </VRow>
    <div class="editor-switches">
      <VSwitch v-model="enabled" label="启用任务" color="primary" hide-details inset />
      <VSwitch v-if="!simpleMode" v-model="rssSupport" label="使用 RSS" color="primary" hide-details inset />
    </div>
  </section>

  <section v-if="!simpleMode" class="editor-section">
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
          v-model.number="brushInterval"
          type="number"
          min="1"
          max="1440"
          label="选种刷新周期（分钟）"
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField
          v-model.number="checkInterval"
          type="number"
          min="1"
          max="1440"
          label="做种检查周期（分钟）"
        />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField v-model="cronExpression" label="CRON 表达式" placeholder="留空使用固定刷新周期" />
      </VCol>
      <VCol cols="12" md="6">
        <VTextField v-model="activeTimeRange" label="开启时间段" placeholder="如 00:00-08:00" />
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
      <VCol cols="12">
        <VTextField
          v-model.number="goalValue"
          type="number"
          min="0"
          step="any"
          :label="isBrush ? '目标上传量（GB）' : '目标魔力值'"
          clearable
        />
      </VCol>
    </VRow>
  </section>
</template>

<style scoped>
/* 面板专属（原父组件搬运；父已删除） */
.editor-presets {
  display: grid;
  gap: 8px;
}
.editor-preset {
  display: grid;
  grid-template-columns: 22px 1fr;
  grid-template-areas: "icon title" "icon desc";
  gap: 2px 8px;
  align-items: center;
  padding: 10px 12px;
  text-align: start;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  background: rgba(var(--v-theme-surface-variant), 0.35);
  color: inherit;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.editor-preset > .v-icon {
  grid-area: icon;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.editor-preset__title {
  grid-area: title;
  font-weight: 600;
}
.editor-preset__desc {
  grid-area: desc;
  font-size: 0.75rem;
  line-height: 1.3;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.editor-preset.is-active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}
.editor-preset.is-active > .v-icon {
  color: rgb(var(--v-theme-primary));
}
.editor-pool {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin-top: 10px;
  font-size: 0.75rem;
  line-height: 1.35;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.editor-quota {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 2px 0 6px;
}

.editor-quota__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 12px;
  opacity: 0.85;
}

.editor-quota__head strong {
  font-size: 14px;
}

.editor-quota__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  opacity: 0.7;
}

.editor-pool.is-warn {
  color: rgb(var(--v-theme-warning));
}
.editor-pool.is-error {
  color: rgb(var(--v-theme-error));
}
.editor-pool__hint {
  font-weight: 600;
}
.editor-pool__link {
  border: 0;
  background: none;
  padding: 0;
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
  cursor: pointer;
}

.editor-simple-note {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.editor-simple-note__link {
  border: 0;
  background: none;
  padding: 0;
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
  cursor: pointer;
}

/* 共享选择器（父里别处也在用）→ 子内复制一份，父原样保留 */
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
</style>
