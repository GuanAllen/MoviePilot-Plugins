<script setup>
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { cloneTask, formatBytes, normalizeTask, unwrapResponse } from '../utils'
import BasePanel from './taskeditor/BasePanel.vue'
import BrushPanel from './taskeditor/BrushPanel.vue'
import MagicPanel from './taskeditor/MagicPanel.vue'
import FormulaPanel from './taskeditor/FormulaPanel.vue'
import SelectionPanel from './taskeditor/SelectionPanel.vue'
import AdvancedPanel from './taskeditor/AdvancedPanel.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  defaultSavePath: { type: String, default: '' },
  savePaths: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
  api: { type: Object, default: null },
  pluginBase: { type: String, default: 'plugin/MagicFlow' },
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
  const full = localTask.value.id ? `编辑${kind}` : `新建${kind}`
  // 手机端标题栏窄（还要放「保存任务」按钮）→ 用短标题，避免被截成「新建魔...」
  if (display.smAndDown.value) return localTask.value.id ? '编辑任务' : '新建任务'
  return full
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
// 保存目录候选：**填过一次就记住**（localStorage）+ 已有任务用过的目录 + 设置里的默认目录 + 任务当前值。
// 用户手输过的目录会立刻落进 localStorage，下次新建/编辑就能从下拉里选到。
const SAVE_PATH_KEY = 'magicflow_save_paths'
const savePathHistory = ref([])
// 清理候选：去重 + **丢掉「别人的前缀」**（如 /vol3/1000/med 是 /vol3/1000/media 的前缀）
// —— 用户逐字打路径时 v-model 每敲一个字就变一次，不做这步会存一堆半截路径。
function cleanSavePaths(list) {
  const uniq = []
  for (const raw of list || []) {
    const v = String(raw || '').trim()
    // 至少两层目录才算「一个目录」，顺手把历史里的垃圾（半截路径）清掉
    if (v && v.split('/').filter(Boolean).length >= 2 && !uniq.includes(v)) uniq.push(v)
  }
  // 丢掉「被更长的条目吃掉」的半截路径：
  //   /vol3/1000/m、/vol3/1000/med（没打完）→ 丢；/vol3/1000/（结尾斜杠）→ 丢
  //   但 /vol6/1000/movie 与 /vol6/1000/movie/刷流 属于「父子目录」→ 都留
  return uniq
    .filter(v => !uniq.some(o => o !== v && o.length > v.length && o.startsWith(v)
      && (v.endsWith('/') || o[v.length] !== '/')))
    .slice(0, 12)
}
function readSavePathHistory() {
  try {
    const raw = window.localStorage.getItem(SAVE_PATH_KEY)
    const list = raw ? JSON.parse(raw) : []
    savePathHistory.value = cleanSavePaths(Array.isArray(list) ? list : [])
  } catch (error) {
    savePathHistory.value = []
  }
}
// ★ 只在**输入完成**时才记（失焦 / 保存任务），绝不逐字记
function rememberSavePath(value) {
  const path = String(value || '').trim()
  if (!path || path.split('/').filter(Boolean).length < 2) return
  const list = cleanSavePaths([path, ...savePathHistory.value])
  savePathHistory.value = list
  try {
    window.localStorage.setItem(SAVE_PATH_KEY, JSON.stringify(list))
  } catch (error) {
    /* 隐私模式等场景忽略 */
  }
}
const savePathOptions = computed(() => {
  const set = new Set()
  for (const item of savePathHistory.value) set.add(item)
  for (const item of props.savePaths || []) if (item) set.add(String(item))
  if (props.defaultSavePath) set.add(props.defaultSavePath)
  if (localTask.value.save_path) set.add(localTask.value.save_path)
  return [...set]
})

// ★ 5.9.0 预设模板：用户「选类型就行」—— 模板只覆盖**程序可决定**的参数
//   （选种/清理/限速/调度/复用…）；站点 / 保存目录 / 目标 / 任务名 仍由用户决定。
// ★ 5.10.0/5.10.3 模板还会按**当前磁盘空间**自动设「最多占多少体积」：以 80% 为阈值（见 POOL_THRESHOLD），
//   并给一个**可拉的百分比**（拉条实时显示折合多少 GB）。
const POOL_THRESHOLD = 0.8
const TASK_PRESETS = [
  {
    key: 'brush',
    icon: 'mdi-upload-network-outline',
    title: '刷流',
    desc: '按上传潜力选种，做种满几天轮换；达标自动停',
    share: 1,
    patch: {
      task_type: 'brush',
      brush_seed_days: 2,
      brush_min_leechers: 1,
      upload_min_kbps: 200,
      except_subscribe: true,
      refill_when_empty: true,
      cleanup_no_progress: true,
      cleanup_slow_progress: true,
      purge_unfree_incomplete: true,
      auto_resume_paused: true,
      delete_files: true,
      ti_source: 'publish',
    },
  },
  {
    key: 'bonus',
    icon: 'mdi-star-four-points-outline',
    title: '刷魔力',
    desc: '挂种产出魔力最大化',
    share: 1,
    patch: {
      task_type: 'bonus',
      except_subscribe: true,
      refill_when_empty: true,
      cleanup_no_progress: true,
      cleanup_slow_progress: true,
      purge_unfree_incomplete: true,
      auto_resume_paused: true,
      delete_files: true,
      ti_source: 'publish',
    },
  },
  {
    key: 'exam',
    icon: 'mdi-school-outline',
    title: '考核冲刺',
    desc: '新站考核期：抢热门免费种攒上传，快转速换',
    share: 1,
    patch: {
      task_type: 'brush',
      brush_seed_days: 1,
      brush_min_leechers: 2,
      upload_min_kbps: 300,
      upload_idle_minutes: 30,
      brush_grace_minutes: 15,
      rotate_upload_gb: null,
      except_subscribe: true,
      refill_when_empty: true,
      max_add_per_run: 8,
      cleanup_no_progress: true,
      cleanup_slow_progress: false,
      purge_unfree_incomplete: true,
      auto_resume_paused: true,
      delete_files: true,
      ti_source: 'publish',
    },
  },
  {
    key: 'keep',
    icon: 'mdi-shield-outline',
    title: '轻量保种',
    desc: '少占盘：只复用本机资源，尽量不新增下载',
    share: 0.25,
    patch: {
      task_type: 'bonus',
      max_add_per_run: 3,
      top_n: 20,
      browse_pages: 1,
      except_subscribe: true,
      refill_when_empty: false,
      cleanup_no_progress: true,
      cleanup_slow_progress: true,
      purge_unfree_incomplete: true,
      auto_resume_paused: true,
      delete_files: true,
      ti_source: 'publish',
    },
  },
  {
    key: 'custom',
    icon: 'mdi-tune-variant',
    title: '自定义',
    desc: '所有参数自己来（展开全部标签页）',
    share: 0,
    patch: {},
  },
]
const presetKey = ref('bonus')
const simpleMode = computed(() => presetKey.value !== 'custom')
const presetInfo = computed(() => TASK_PRESETS.find(p => p.key === presetKey.value) || TASK_PRESETS[1])
// 磁盘状态（**按目录分盘**，只看任务自己那块盘；80% 阈值 → 本任务可占体积）
// ★ 不能用 MP 仪表板的「本地存储」：那是把多个目录加起来的总数（例如 /movie + /media），
//   任务写不到别的池里，拿总和算阈值会严重高估。
const pool = ref(null)
const poolError = ref('')
const poolLoading = ref(false)
async function loadPool() {
  if (!props.api) {
    poolError.value = '未接入宿主 API，无法读取磁盘空间'
    return
  }
  poolLoading.value = true
  poolError.value = ''
  try {
    const savePath = String(localTask.value.save_path || props.defaultSavePath || '').trim()
    const query = `?path=${encodeURIComponent(savePath)}`
    const raw = await props.api.get(`${props.pluginBase}/pool${query}`)
    const data = unwrapResponse(raw) || {}
    if (!data.total) throw new Error('empty')
    pool.value = {
      name: data.name || '',
      path: data.path || '',
      total_gb: Number(data.total) / 1024 ** 3,
      used_gb: Number(data.used) / 1024 ** 3,
      pct: Number(data.pct) || 0,
      budget_gb: Number(data.budget_gb) || 0,
      pools: Array.isArray(data.pools) ? data.pools : [],
    }
    // 磁盘读得快时，把体积上限回填给当前模板（自定义模式不碰用户手填值）
    if (simpleMode.value && poolBudgetGb.value > 0) localTask.value.disk_size_gb = poolBudgetGb.value
  } catch (error) {
    pool.value = null
    poolError.value = '磁盘空间读取失败'
  } finally {
    poolLoading.value = false
  }
}
const poolOver = computed(() => !!pool.value && pool.value.pct >= POOL_THRESHOLD * 100)
// 可拉的百分比：占「磁盘剩余可用空间（到 80% 阈值）」的比例（0~100），拉条实时显示折合 GB
const poolPct = ref(100)
const poolBudgetGb = computed(() => {
  if (!pool.value) return 0
  return Math.round(pool.value.budget_gb * (Number(poolPct.value) || 0) / 100 * 10) / 10
})
const poolBudgetText = computed(() => (poolBudgetGb.value > 0 ? `${poolBudgetGb.value} GB` : '不限'))
const poolFreeText = computed(() => (pool.value ? formatBytes(pool.value.budget_gb * 1024 ** 3) : '—'))
const presetPatchCount = computed(() => Object.keys(presetInfo.value.patch || {}).length + (poolBudgetGb.value > 0 ? 1 : 0))
// 选模板 → 只覆盖「程序可决定」的参数（用户已填的站点/目录/目标/名称不动）
function applyPreset(key) {
  presetKey.value = key
  const p = TASK_PRESETS.find(x => x.key === key)
  if (p && Object.keys(p.patch || {}).length) Object.assign(localTask.value, p.patch)
  // 体积上限：按磁盘 80% 阈值 × 拉条比例（轻量保种默认 25%），已超阈则不设
  if (p && Number(p.share)) poolPct.value = Math.round(Number(p.share) * 100)
  else if (p && p.key === 'custom') poolPct.value = poolPct.value || 100
  const budget = poolBudgetGb.value
  if (budget > 0) localTask.value.disk_size_gb = budget
  autoFillName(false)
  autoFillTag()
  if (key === 'custom') activeTab.value = 'base'
}
// 任务名自动填「站点·模板名」；换站点/换模板都会跟着变（用户手改过才不动）
const autoNameSet = computed(() => {
  const set = new Set()
  for (const site of props.sites) {
    const sname = site?.title || site?.name || ''
    if (!sname) continue
    for (const p of TASK_PRESETS) set.add(`${sname}·${p.title}`)
  }
  return set
})
function autoFillName(force = true) {
  const site = props.sites.find(item => Number(item.value ?? item.id) === Number(localTask.value.site_id))
  const sname = site?.title || site?.name || ''
  if (!sname) return
  const cur = String(localTask.value.name || '').trim()
  const wasAuto = !cur || autoNameSet.value.has(cur)
  if (force || wasAuto) localTask.value.name = `${sname}·${presetInfo.value.title}`
}
// ★ 下载器标签：和任务名同规矩 —— **推荐默认值 + 强制统一**。
//   永远按「站点 + 任务类型」派生（刷流任务 → 刷流，其余 → 魔力）；
//   字段里展示的就是推荐值，手填了不统一的内容也会在换站点/换类型/保存时被纠正。
const tagState = computed(() => (String(localTask.value.task_type || 'bonus').toLowerCase() === 'brush' ? '刷流' : '魔力'))
// siteName 已在上面定义（未选择站点时为「未选择」）
const autoTag = computed(() => {
  const n = String(siteName.value || '').trim()
  return n && n !== '未选择' ? `魔流-${n}-${tagState.value}` : ''
})
function autoFillTag() {
  if (autoTag.value) localTask.value.brush_tag = autoTag.value
}
function onPctChange() {
  if (simpleMode.value && poolBudgetGb.value > 0) localTask.value.disk_size_gb = poolBudgetGb.value
}
function onSiteChange() {
  autoFillName(false)
  autoFillTag()
}
function onSavePathChange() {
  loadPool()
}

// 每次打开弹窗都从服务端任务快照重新创建本地草稿。
watch(
  () => props.modelValue,
  visible => {
    if (!visible) return
    localTask.value = cloneTask(props.task)
    activeTab.value = 'base'
    presetKey.value = localTask.value.task_type === 'brush' ? 'brush' : 'bonus'
    readSavePathHistory()
    rememberSavePath(localTask.value.save_path)
    autoFillTag()
    pool.value = null
    loadPool()
  },
)

// 切换任务类型时，若当前标签在新类型下不存在，回到「基础与调度」。
watch(
  () => localTask.value.task_type,
  () => {
    presetKey.value = localTask.value.task_type === 'brush' ? 'brush' : 'bonus'
    autoFillTag()
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
  rememberSavePath(localTask.value.save_path)
  emit('save', normalizeTask(localTask.value))
}

// 确认「仍然保存」（不带目标）
function confirmSaveWithoutGoal() {
  goalWarning.value = false
  rememberSavePath(localTask.value.save_path)
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
            v-if="!simpleMode"
            v-model="activeTab"
            :direction="display.mdAndUp.value ? 'vertical' : 'horizontal'"
            color="primary"
            class="magicflow-editor__tabs"
          >
            <VTab v-for="tab in editorTabs" :key="tab.value" :value="tab.value" :prepend-icon="tab.icon">
              {{ tab.label }}
            </VTab>
          </VTabs>

          <VDivider v-if="!simpleMode" :vertical="display.mdAndUp.value" />

          <VWindow v-model="activeTab" :touch="false" class="magicflow-editor__window">
            <VWindowItem value="base">
              <BasePanel
                v-model:site-id="localTask.site_id"
                v-model:name="localTask.name"
                v-model:downloader="localTask.downloader"
                v-model:brush-tag="localTask.brush_tag"
                v-model:save-path="localTask.save_path"
                v-model:enabled="localTask.enabled"
                v-model:rss-support="localTask.rss_support"
                v-model:brush-interval="localTask.brush_interval"
                v-model:check-interval="localTask.check_interval"
                v-model:cron-expression="localTask.cron_expression"
                v-model:active-time-range="localTask.active_time_range"
                v-model:goal-value="localTask.goal_value"
                v-model:pool-pct="poolPct"
                :presets="TASK_PRESETS"
                :preset-key="presetKey"
                :simple-mode="simpleMode"
                :preset-patch-count="presetPatchCount"
                :sites="sites"
                :downloaders="downloaders"
                :auto-tag="autoTag"
                :save-path-options="savePathOptions"
                :pool="pool"
                :pool-over="poolOver"
                :pool-error="poolError"
                :pool-loading="poolLoading"
                :pool-free-text="poolFreeText"
                :pool-budget-text="poolBudgetText"
                :schedule-text="scheduleText"
                :is-brush="isBrush"
                @apply-preset="applyPreset"
                @site-change="onSiteChange"
                @save-path-change="onSavePathChange"
                @remember-save-path="rememberSavePath"
                @load-pool="loadPool"
                @pct-change="onPctChange"
              />
            </VWindowItem>

            <VWindowItem v-if="!simpleMode" value="brush">
              <BrushPanel
                v-model:brushSeedDays="localTask.brush_seed_days"
                v-model:brushMinLeechers="localTask.brush_min_leechers"
                v-model:rotateUploadGb="localTask.rotate_upload_gb"
                v-model:rotateRatio="localTask.rotate_ratio"
                v-model:exceptSubscribe="localTask.except_subscribe"
                v-model:uploadMinKbps="localTask.upload_min_kbps"
                v-model:uploadIdleMinutes="localTask.upload_idle_minutes"
                v-model:brushGraceMinutes="localTask.brush_grace_minutes"
                v-model:maxAddPerRun="localTask.max_add_per_run"
                v-model:maxDownloadConcurrent="localTask.max_download_concurrent"
                v-model:topN="localTask.top_n"
                v-model:browsePages="localTask.browse_pages"
                v-model:refillWhenEmpty="localTask.refill_when_empty"
                v-model:cleanupNoProgress="localTask.cleanup_no_progress"
                v-model:cleanupSlowProgress="localTask.cleanup_slow_progress"
                v-model:purgeUnfreeIncomplete="localTask.purge_unfree_incomplete"
                v-model:autoResumePaused="localTask.auto_resume_paused"
                v-model:deleteFiles="localTask.delete_files"
                v-model:deleteExceptTags="localTask.delete_except_tags"
                v-model:noProgressMinutes="localTask.no_progress_minutes"
                v-model:seenCooldownHours="localTask.seen_cooldown_hours"
                v-model:slowProgressGraceMinutes="localTask.slow_progress_grace_minutes"
                v-model:slowProgressMaxHours="localTask.slow_progress_max_hours"
                :upload-rate-options="uploadRateOptions"
              />
            </VWindowItem>

            <VWindowItem v-if="!simpleMode && !isBrush" value="magic">
              <MagicPanel
                v-model:minBonusPerHour="localTask.min_bonus_per_hour"
                v-model:diskSizeGb="localTask.disk_size_gb"
                v-model:maxKeepTorrents="localTask.max_keep_torrents"
                v-model:maxAddPerRun="localTask.max_add_per_run"
                v-model:maxDownloadConcurrent="localTask.max_download_concurrent"
                v-model:topN="localTask.top_n"
                v-model:browsePages="localTask.browse_pages"
                v-model:bonusProtectThreshold="localTask.bonus_protect_threshold"
                v-model:minBonusToKeep="localTask.min_bonus_to_keep"
                v-model:refillWhenEmpty="localTask.refill_when_empty"
                v-model:cleanupNoProgress="localTask.cleanup_no_progress"
                v-model:cleanupSlowProgress="localTask.cleanup_slow_progress"
                v-model:purgeUnfreeIncomplete="localTask.purge_unfree_incomplete"
                v-model:autoResumePaused="localTask.auto_resume_paused"
                v-model:tiSource="localTask.ti_source"
                v-model:noProgressMinutes="localTask.no_progress_minutes"
                v-model:seenCooldownHours="localTask.seen_cooldown_hours"
                v-model:slowProgressGraceMinutes="localTask.slow_progress_grace_minutes"
                v-model:slowProgressMaxHours="localTask.slow_progress_max_hours"
                v-model:minSeedTime="localTask.min_seed_time"
                v-model:minRatio="localTask.min_ratio"
                v-model:deleteFiles="localTask.delete_files"
                v-model:deleteExceptTags="localTask.delete_except_tags"
                v-model:protectPerfect="localTask.protect_perfect"
                v-model:perfectMaxSeeders="localTask.perfect_max_seeders"
                v-model:perfectMinWeeks="localTask.perfect_min_weeks"
              />
            </VWindowItem>

            <VWindowItem v-if="!simpleMode && !isBrush" value="formula">
              <FormulaPanel
                v-model:bonusT0="localTask.bonus_t0"
                v-model:bonusN0="localTask.bonus_n0"
                v-model:bonusB0="localTask.bonus_b0"
                v-model:bonusL="localTask.bonus_l"
                v-model:bonusZeroWeight="localTask.bonus_zero_weight"
              />
            </VWindowItem>

            <VWindowItem v-if="!simpleMode" value="selection">
              <SelectionPanel
                v-model:freeleech="localTask.freeleech"
                v-model:hr="localTask.hr"
                v-model:size="localTask.size"
                v-model:seeder="localTask.seeder"
                v-model:pubtime="localTask.pubtime"
                v-model:include="localTask.include"
                v-model:exclude="localTask.exclude"
                v-model:excludeZeroBonus="localTask.exclude_zero_bonus"
                :is-brush="isBrush"
              />
            </VWindowItem>

            <VWindowItem v-if="!simpleMode" value="advanced">
              <AdvancedPanel
                v-model:crossseedEnabled="localTask.crossseed_enabled"
                v-model:crossseedMaxPerRound="localTask.crossseed_max_per_round"
                v-model:crossseedMaxSizeGb="localTask.crossseed_max_size_gb"
                v-model:crossseedMaxSites="localTask.crossseed_max_sites"
                v-model:upSpeed="localTask.up_speed"
                v-model:dlSpeed="localTask.dl_speed"
                :site-name="siteName"
                :schedule-text="scheduleText"
                :is-brush="isBrush"
                :downloader="localTask.downloader"
                :active-time-range="localTask.active_time_range"
                :goal-value="localTask.goal_value"
                :has-goal="hasGoal()"
              />
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
  max-block-size: min(90dvh, 58rem);
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid rgba(var(--v-border-color), 0.14);
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
