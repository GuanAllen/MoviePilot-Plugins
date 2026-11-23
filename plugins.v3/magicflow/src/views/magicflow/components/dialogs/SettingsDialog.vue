<script setup>
// MagicFlow · 设置弹窗（多标签）——P4 自 views/magicflow/index.vue **纯搬家**。
// props 下 / emit 上：子组件不直接改父状态；开关与设置项走 defineModel / emit。
// 复用 composable 纯函数 → module 级具名导出 import（单一真值源）。
import { MF_SETTINGS_TABS, MF_SETTINGS_GROUPS, TILE_OPTIONS, ratingSourceItems, episodePolicyItems, agentToolScopeItems } from '../../constants'
import { fmtTs } from '../../format'
import { settingsTabLabel, ruleSourceText } from '../../composables/useSettings'
import { sortRuleText, sortRuleNeedsMin, sortRuleTypeOptions } from '../../composables/useTagModel'
import { fallbackSourceLabel } from '../../composables/useFallback'

// 弹窗开关 / 当前标签 / 可写草稿（双向）
const settingsDialog = defineModel({ type: Boolean, default: false })
const settingsTab = defineModel('settingsTab', { type: String, default: 'general' })
const fallbackSourceDraft = defineModel('fallbackSourceDraft', { type: String, default: '' })
const newRuleType = defineModel('newRuleType', { type: String, default: 'subscribe' })

const emit = defineEmits([
  'open-tab', 'back-to-dir', 'save', 'apply-recommended', 'test-iyuu', 'clear-iyuu',
  'probe-rules', 'refresh-rules', 'set-rule-hr', 'set-rule-hours', 'set-rule-ratio',
  'open-claim', 'open-signin', 'run-fallback', 'run-reseed', 'load-reseed', 'load-fallback',
  'add-fallback-source', 'move-fallback-source', 'remove-fallback-source', 'set-tile-shown',
  'add-sort-rule', 'remove-sort-rule', 'test-cloud',
])

// 供父组件在子渲染后取回设置导航栏 DOM（父 composable 的自动滚动依赖它）
defineProps({
  setNavEl: { type: Function, default: null },
  isNarrow: { type: Boolean, default: false },
  settingsPane: { type: String, default: 'form' },
  status: { type: Object, default: null },
  selectedTask: { type: Object, default: null },
  saving: { type: Boolean, default: false },
  settingsDraft: { type: Object, required: true },
  downloaderPrefsDraft: { type: Object, default: null },
  downloaderPathsDraft: { type: Object, default: null },
  defaultsDraft: { type: Object, default: null },
  downloaderPrefsRecommended: { type: Boolean, default: false },
  iyuuSites: { type: Array, default: () => [] },
  iyuuLoading: { type: Boolean, default: false },
  iyuuStatus: { type: Object, default: null },
  iyuuTesting: { type: Boolean, default: false },
  iyuuShowMore: { type: Object, default: () => ({}) },
  siteRules: { type: Array, default: () => [] },
  rulesProbeState: { type: Object, default: () => ({}) },
  rulesLoading: { type: Boolean, default: false },
  rulesProbing: { type: Boolean, default: false },
  reseedState: { type: Object, default: null },
  reseedRunning: { type: Boolean, default: false },
  reseedSiteOptions: { type: Array, default: () => [] },
  claimSiteOptions: { type: Array, default: () => [] },
  siteSelectItems: { type: Array, default: () => [] },
  siteLiveAlerts: { type: Array, default: () => [] },
  tagInfo: { type: Object, default: null },
  fallbackState: { type: Object, default: null },
  fallbackLoading: { type: Boolean, default: false },
  fallbackRunning: { type: Boolean, default: false },
  fallbackProblemShows: { type: Array, default: () => [] },
  fallbackProblemCount: { type: Number, default: 0 },
  usedFallbackSources: { type: Array, default: () => [] },
  unusedFallbackSources: { type: Array, default: () => [] },
  cloudCfg: { type: Object, default: null },
  cloudTestMsg: { type: String, default: '' },
  cloudTestOk: { type: Boolean, default: false },
  cloudTesting: { type: Boolean, default: false },
  tileShown: { type: Function, default: () => false },
})
</script>

<template>
    <VDialog v-model="settingsDialog" max-width="62rem" :fullscreen="isNarrow">
      <VCard class="magicflow-dialog magicflow-settings-dialog">
        <header class="magicflow-settings-dialog__head">
          <VBtn
            v-if="isNarrow && settingsPane === 'form'"
            icon="mdi-arrow-left"
            size="small"
            variant="text"
            aria-label="返回设置目录"
            @click="emit('back-to-dir')"
          />
          <span class="magicflow-settings-dialog__title">{{ isNarrow && settingsPane === 'form' ? settingsTabLabel(settingsTab) : '插件设置' }}</span>
          <span class="magicflow-scope-tag">全局</span>
          <VBtn
            icon="mdi-close"
            size="small"
            variant="text"
            :aria-label="isNarrow && settingsPane === 'form' ? '返回设置目录' : '关闭'"
            @click="isNarrow && settingsPane === 'form' ? emit('back-to-dir') : (settingsDialog = false)"
          />
        </header>

        <div v-if="!isNarrow || settingsPane === 'dir'" class="magicflow-settings-nav" :ref="setNavEl">
          <template v-for="g in MF_SETTINGS_GROUPS" :key="g.title">
            <div class="magicflow-settings-nav__group">{{ g.title }}</div>
            <div class="magicflow-settings-nav__grid">
              <button
                v-for="t in g.items"
                :key="t.key"
                type="button"
                class="magicflow-settings-nav__item"
                :class="{ 'is-active': settingsTab === t.key, 'is-new': !!t.isNew }"
                @click="emit('open-tab', t.key)"
              >
                <span v-if="t.isNew" class="magicflow-settings-nav__new">新</span>
                <VIcon :icon="t.icon" size="18" />
                <span>{{ t.label }}</span>
              </button>
            </div>
          </template>
        </div>

        <VTabs v-model="settingsTab" class="magicflow-settings-dialog__tabs" density="comfortable" show-arrows>
          <VTab value="general" class="magicflow-settings-tab">常规</VTab>
          <VTab value="downloader" class="magicflow-settings-tab">下载与目录</VTab>
          <VTab value="template" class="magicflow-settings-tab">默认任务模板</VTab>
          <VTab value="iyuu" class="magicflow-settings-tab">IYUU 辅种</VTab>
          <VTab value="fallback" class="magicflow-settings-tab">元数据兜底</VTab>
          <VTab value="cloud" class="magicflow-settings-tab">云盘归档</VTab>
          <VTab value="exam" class="magicflow-settings-tab">考核</VTab>
          <VTab value="signin" class="magicflow-settings-tab">签到</VTab>
          <VTab value="live" class="magicflow-settings-tab">站点监控</VTab>
          <VTab value="recommend" class="magicflow-settings-tab">推荐</VTab>
          <VTab value="crossseed" class="magicflow-settings-tab">跨站</VTab>
          <VTab value="rules" class="magicflow-settings-tab">站点规则</VTab>
          <VTab value="tags" class="magicflow-settings-tab">标签管理</VTab>
          <VTab value="notify" class="magicflow-settings-tab">通知</VTab>
        </VTabs>
        <VDivider v-if="!isNarrow || settingsPane === 'form'" />

        <div v-if="!isNarrow || settingsPane === 'form'" class="magicflow-settings-dialog__body">
          <!-- ★ 15.13.0：事件通知（H&R 临期 / 容量红线 / 产出骤降 / 任务失败 / 日报） -->
          <div v-if="settingsTab === 'notify'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-bell-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">出事了主动告警，不用自己盯</div>
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 通知开关</div>
              <div class="magicflow-settings-switches">
                <VSwitch
                  v-model="settingsDraft.notify_enabled"
                  label="开启事件通知"
                  color="primary"
                  hide-details
                  inset
                />
                <VSwitch
                  v-model="settingsDraft.notify_task_fail"
                  label="任务失败时通知"
                  color="primary"
                  hide-details
                  inset
                  :disabled="!settingsDraft.notify_enabled"
                />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-timer-alert-outline" /> 告警阈值
              </div>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-model.number="settingsDraft.notify_hr_hours"
                  type="number"
                  min="0"
                  step="1"
                  label="H&amp;R 到期提醒提前量（小时）"
                  hint="距达标期限不足该小时数就发信（默认 24）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.notify_enabled"
                />
                <VTextField
                  v-model.number="settingsDraft.notify_capacity_pct"
                  type="number"
                  min="50"
                  max="99"
                  step="1"
                  label="池盘告警阈值（%）"
                  hint="池盘占用达到该百分比就提醒（默认 80）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.notify_enabled"
                />
                <VTextField
                  v-model.number="settingsDraft.notify_drop_pct"
                  type="number"
                  min="1"
                  step="1"
                  label="产出骤降阈值（%）"
                  hint="比前 3 日均值低超过该比例就提醒（默认 20%）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.notify_enabled"
                />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-newspaper-variant-outline" /> 每日日报与免打扰
              </div>
              <div class="magicflow-settings-switches">
                <VSwitch
                  v-model="settingsDraft.notify_daily"
                  label="发送每日日报"
                  color="primary"
                  hide-details
                  inset
                  :disabled="!settingsDraft.notify_enabled"
                />
              </div>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-if="settingsDraft.notify_daily && settingsDraft.notify_enabled"
                  v-model.number="settingsDraft.notify_daily_hour"
                  type="number"
                  min="0"
                  max="23"
                  step="1"
                  label="日报发送时间（小时，0-23）"
                  hint="当天首次扫描时发送"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model="settingsDraft.notify_quiet"
                  label="免打扰时段（可空）"
                  placeholder="23:00-08:00"
                  hint="该时段内不发送（仍记入历史）；留空 = 不静音"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.notify_enabled"
                />
              </div>
            </div>
          </div>

          <div v-if="settingsTab === 'general'" class="magicflow-settings-form">
            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 总开关与入口</div>
            <VSwitch v-model="settingsDraft.enabled" label="启用插件（总开关）" color="primary" hide-details inset />
            <VSwitch
              v-model="settingsDraft.show_sidebar_nav"
              label="显示侧栏入口"
              color="primary"
              hide-details
              inset
            />
            <VSwitch
              v-model="settingsDraft.agent_mcp"
              label="把魔流能力注册进 MoviePilot Agent / MCP"
              color="primary"
              hide-details
              inset
            />
            <VSelect
              v-if="settingsDraft.agent_mcp"
              v-model="settingsDraft.agent_mcp_scope"
              :items="agentToolScopeItems"
              item-title="title"
              item-value="value"
              label="注册范围"
              hide-details
              variant="outlined"
              density="comfortable"
            />
            <div v-if="settingsDraft.agent_mcp" class="magicflow-settings-danger">
              <div class="magicflow-settings-danger__h"><VIcon icon="mdi-alert-outline" size="18" /> 写操作也一并注册</div>
              
            </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-timer-sand" /> 请求与记录</div>
            <VTextField
              v-model.number="settingsDraft.request_interval"
              type="number"
              min="0"
              step="0.5"
              label="站点请求间隔（秒）"
              hint="站点翻页之间的最小间隔，0＝不限；强流控站可加大"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />
            <VTextField
              v-model.number="settingsDraft.journal_keep"
              type="number"
              min="0"
              label="操作记录保留上限"
              hint="每个任务最多保留的操作记录条数，0 = 不限"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.bonus_upload_limit_kbps"
                type="number"
                min="0"
                step="10"
                label="魔力任务上传限速（KB/s）"
                hint="仅有魔力任务在跑时生效，0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.brush_upload_limit_kbps"
                type="number"
                min="0"
                step="10"
                label="刷流任务上传限速（KB/s）"
                hint="有刷流任务在跑时生效（优先），0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.seed_up_limit_kbps"
                type="number"
                min="0"
                step="50"
                label="挂种单种上传限速（KB/s）"
                hint="管控中的种单种限速，默认 200；0＝不限；不管控的不限速"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.brush_seed_up_limit_kbps"
                type="number"
                min="0"
                step="256"
                label="刷流单种上传限速（KB/s）"
                hint="我们管控的刷流种：要冲量，默认 5120（=5 MB/s）；0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.debug_log" label="调试日志" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.compact_mode" label="紧凑模式" color="primary" hide-details inset />
            </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-view-grid-outline" size="16" /> 顶栏功能磁贴</div>
              <div class="magicflow-tile-switches">
                <VSwitch
                  v-for="t in TILE_OPTIONS"
                  :key="t.key"
                  :model-value="tileShown(t.key)"
                  :label="t.label"
                  :prepend-icon="t.icon"
                  color="primary"
                  hide-details
                  inset
                  density="comfortable"
                  @update:model-value="v => emit('set-tile-shown', t.key, v)"
                />
              </div>
              <p class="magicflow-field__sub">
                已显示 {{ TILE_OPTIONS.filter(t => tileShown(t.key)).length }} / {{ TILE_OPTIONS.length }}
              </p>
            </div>
            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-lifebuoy" size="16" /> 死种补源（rescue）</div>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-model.number="settingsDraft.rescue_stall_hours"
                  type="number"
                  min="0"
                  max="720"
                  step="1"
                  label="停滞阈值（小时）"
                  hint="0 速持续超过该时长才纳入补源（默认 6，越小越灵敏）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.rescue_max_candidates"
                  type="number"
                  min="1"
                  max="10"
                  step="1"
                  label="每目标候选数"
                  hint="只列无 H&R 站的同 Release 候选（默认 3）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
              </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'downloader'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-download-network-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">调 qBittorrent 的全局参数</div>
              </div>
              <span class="magicflow-settings-lede__tag is-warn">写 qB 全局</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-speedometer" /> 限速与连接
              </div>
              <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="downloaderPrefsDraft.download_limit_kbps"
                type="number"
                min="0"
                label="最大下载速度"
                suffix="KB/s"
                hint="0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.upload_limit_kbps"
                type="number"
                min="0"
                label="最大上传速度"
                suffix="KB/s"
                hint="0 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_connec"
                type="number"
                min="0"
                label="最大连接数"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_connec_per_torrent"
                type="number"
                min="0"
                label="每种子连接数"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_uploads"
                type="number"
                min="-1"
                label="最大上传连接数"
                hint="-1 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_uploads_per_torrent"
                type="number"
                min="-1"
                label="每种子上传连接数"
                hint="-1 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_active_downloads"
                type="number"
                min="-1"
                label="最大活动下载数"
                hint="排队不计入；-1 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="downloaderPrefsDraft.max_active_torrents"
                type="number"
                min="-1"
                label="最大活动种子数"
                hint="-1 = 不限"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
              <div class="magicflow-settings-switches">
                <VSwitch
                  v-model="downloaderPrefsDraft.queueing_enabled"
                  label="启用队列限制（活动数上限生效的前提）"
                  color="primary"
                  hide-details
                  inset
                />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-folder-network-outline" /> qBittorrent 目录
              </div>
              <div class="magicflow-field-stack">
                <VTextField
                  v-model="downloaderPathsDraft.save_path"
                  label="默认保存路径"
                  placeholder="如 /vol3/1000/media"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
                <VTextField
                  v-model="downloaderPathsDraft.temp_path"
                  label="临时下载路径"
                  placeholder="下载中暂存目录"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
                <VSwitch
                  v-model="downloaderPathsDraft.temp_path_enabled"
                  label="启用临时下载路径（下载中放临时目录，完成后移入保存路径）"
                  color="primary"
                  hide-details
                  inset
                />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-folder-marker-outline" /> 任务保存目录
              </div>
              <VTextField
                v-model="defaultsDraft.save_path"
                label="任务保存目录"
                placeholder="如 /vol3/1000/media/magicflow"
                hint="新建任务时预填此目录（不改已有任务）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
          </div>

          <div v-else-if="settingsTab === 'iyuu'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-cloud-sync-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">IYUU 云端辅种（可选增强）</div>
              </div>
              <span class="magicflow-settings-lede__tag" :class="{ 'is-warn': !(settingsDraft.iyuu_token || iyuuStatus?.token_set) }">{{ (settingsDraft.iyuu_token || iyuuStatus?.token_set) ? '已启用' : '未启用' }}</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-key-outline" /> 云端 Token
              </div>
            <div class="magicflow-iyuu-token">
              <VTextField
                v-model="settingsDraft.iyuu_token"
                label="IYUU 云端 Token"
                :placeholder="iyuuStatus?.token_set ? '已保存（留空则不修改）' : '留空 = 不启用 IYUU 辅种'"
                variant="outlined"
                density="comfortable"
                hide-details
                autocomplete="off"
              />
              <VBtn
                variant="tonal"
                color="primary"
                size="small"
                prepend-icon="mdi-connection"
                :loading="iyuuTesting"
                :disabled="!settingsDraft.iyuu_token && !iyuuStatus?.token_set"
                @click="emit('test-iyuu')"
              >测试</VBtn>
              <VBtn
                v-if="settingsDraft.iyuu_token || iyuuStatus?.token_set"
                variant="text"
                color="error"
                size="small"
                prepend-icon="mdi-close-circle-outline"
                @click="emit('clear-iyuu')"
              >清空</VBtn>
            </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-key-variant" /> 站点密钥
                <VChip
                  v-if="iyuuStatus"
                  class="magicflow-settings-block__note"
                  size="x-small"
                  variant="tonal"
                  :color="iyuuStatus.enabled ? 'success' : 'grey'"
                >{{ iyuuStatus.enabled ? '已启用' : '未启用' }}</VChip>
              </div>
            <div class="magicflow-iyuu-sites">
              <p v-if="iyuuLoading" class="magicflow-settings-hint">加载中…</p>
              <p v-else-if="!iyuuSites.length" class="magicflow-settings-hint">
                未检测到已配置站点（请先在 MoviePilot 中添加站点）。
              </p>
              <div v-for="row in iyuuSites" :key="row.domain || row.name" class="magicflow-iyuu-row">
                <div class="magicflow-iyuu-row__head">
                  <span class="magicflow-iyuu-row__name">{{ row.name }}</span>
                  <VChip v-if="row.iyuu_sid" size="x-small" variant="tonal">IYUU #{{ row.iyuu_sid }}</VChip>
                  <VChip v-if="row.has_apikey" size="x-small" variant="tonal" color="success">API</VChip>
                  <VChip v-if="row.has_cookie" size="x-small" variant="tonal" color="info">Cookie</VChip>
                  <VSpacer />
                  <VBtn
                    size="x-small"
                    variant="text"
                    :append-icon="iyuuShowMore[row.domain || row.name] ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                    @click="iyuuShowMore[row.domain || row.name] = !iyuuShowMore[row.domain || row.name]"
                  >{{ iyuuShowMore[row.domain || row.name] ? '收起' : '更多' }}</VBtn>
                </div>
                <div v-if="iyuuShowMore[row.domain || row.name]" class="magicflow-iyuu-row__fields">
                  <div class="text-caption text-medium-emphasis" style="grid-column: 1 / -1">
                    passkey 统一在「RSS / 凭据」里填写（这里不再重复）
                  </div>
                  <VTextField
                    v-model="row.uid"
                    label="uid（可选）"
                    :placeholder="row.uid_set ? '已保存（留空则不修改）' : '留空 = 自动获取'"
                    variant="outlined"
                    density="compact"
                    hide-details
                    autocomplete="off"
                  />
                </div>
                <VTextField
                  v-if="iyuuShowMore[row.domain || row.name]"
                  v-model="row.downhash"
                  label="downhash（可选）"
                  :placeholder="row.downhash_set ? '已保存（留空则不修改）' : '留空 = 自动获取'"
                  variant="outlined"
                  density="compact"
                  hide-details
                  autocomplete="off"
                />
              </div>
            </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'reseed'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-seed-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">本机已有的文件，去各站找同一种子挂上去</div>
              </div>
              <span class="magicflow-settings-lede__tag">零下载 · 本地 {{ reseedState?.debug?.direct_sites ?? 0 }} 站</span>
            </div>


            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 开关</div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.reseed_enabled" label="启用全站辅种" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.reseed_dry" label="干跑（只算不挂）" color="primary" hide-details inset :disabled="!settingsDraft.reseed_enabled" />
            </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-web" size="16" /> 目标站点（留空 = 全部有 IYUU 编号的站）</div>
              <VSelect
                v-model="settingsDraft.reseed_sites"
                :items="reseedSiteOptions"
                label="铺设站点"
                multiple
                chips
                closable-chips
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <span class="magicflow-field__sub">已选 {{ (settingsDraft.reseed_sites || []).length }} 个 · 不在 IYUU 站点表里的站当不了目标</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-tune" size="16" /> 限量</div>
              <div class="magicflow-settings-grid">
                <VTextField v-model.number="settingsDraft.reseed_daily_per_site" type="number" label="每站每天挂种上限" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.reseed_batch" type="number" label="每轮最多处理（对）" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.reseed_min_size_gb" type="number" label="最小体积 GB" variant="outlined" density="comfortable" hide-details />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-magnify" size="16" /> 本地直连搜索</div>
              <VSelect
                v-model="settingsDraft.reseed_search_sites"
                :items="(reseedState?.config?.search_options || []).map((o) => ({ title: `${o.name} · ${o.domain}`, value: o.domain }))"
                label="启用直连搜索的站"
                multiple
                chips
                closable-chips
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <span class="magicflow-field__sub">候选来自后端预设（{{ (reseedState?.config?.search_options || []).length }} 站）· 只放实测过的站，新站要先写进预设表</span>
              <div class="magicflow-settings-grid" style="margin-top: 12px">
                <VTextField v-model.number="settingsDraft.reseed_search_kw" type="number" label="每轮词数上限（0 = 用预设）" variant="outlined" density="comfortable" hide-details />
              </div>
              <span class="magicflow-field__sub">已启用 {{ (settingsDraft.reseed_search_sites || []).length }} 站 · 每轮 {{ settingsDraft.reseed_search_kw || (reseedState?.config?.search_options?.[0]?.kw_per_round || 20) }} 词 · worker 15 分钟一轮</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-content-duplicate" size="16" /> 运行 / 状态
                <VSpacer />
                <VBtn size="small" variant="text" prepend-icon="mdi-refresh" class="me-2" @click="emit('load-reseed')">刷新</VBtn>
                <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-play" :loading="reseedRunning" @click="emit('run-reseed')">
                  {{ settingsDraft.reseed_dry ? '立即干跑一轮' : '立即跑一轮' }}
                </VBtn>
              </div>
              <div v-if="reseedState" class="magicflow-reseedpanel">
                <div class="magicflow-reseedpanel__row">
                  <VChip size="small" variant="tonal" :color="reseedState.enabled ? 'success' : 'grey'">{{ reseedState.enabled ? '已启用' : '未启用' }}</VChip>
                  <VChip size="small" variant="tonal" :color="reseedState.dry ? 'warning' : 'grey'">{{ reseedState.dry ? '干跑' : '实挂' }}</VChip>
                  <VChip v-if="reseedState.running" size="small" variant="tonal" color="info">运行中…</VChip>
                  <span class="magicflow-field__sub">IYUU 云端 {{ reseedState.debug?.token ? '✓' : '✗' }} · 云端站点表 {{ reseedState.debug?.iyuu_sites ?? 0 }} · 可辅站 {{ reseedState.debug?.mapped ?? 0 }}</span>
                </div>
                <div class="magicflow-reseedpanel__row">
                  <span class="magicflow-field__sub">本机上报 {{ reseedState.cloud?.hashes ?? 0 }} 颗 · IYUU 云端命中候选 {{ reseedState.cloud?.candidates ?? 0 }} 对</span>
                </div>
                <div v-if="reseedState.last && reseedState.last.at" class="magicflow-reseedpanel__row">
                  <span class="magicflow-field__sub">
                    上轮 {{ fmtTs(reseedState.last.at) }}：计划 {{ reseedState.last.plan ?? 0 }} · 挂上 {{ reseedState.last.ok ?? 0 }} · 已有 {{ reseedState.last.have ?? 0 }} · 不一致 {{ reseedState.last.mismatch ?? 0 }} · 缺链 {{ reseedState.last.nourl ?? 0 }} · 缺 PV {{ reseedState.last.pv ?? 0 }} · 失败 {{ reseedState.last.fail ?? 0 }} · 干跑可挂 {{ reseedState.last.would ?? 0 }}（{{ reseedState.last.duration ?? 0 }}s）
                  </span>
                </div>
                <div class="magicflow-reseedpanel__sites">
                  <div class="magicflow-reseedpanel__head">
                    <span>站点</span><span>IYUU</span><span>passkey</span><span>今日 / 上限</span>
                  </div>
                  <div v-for="s in (reseedState.sites || [])" :key="s.sid" class="magicflow-reseedpanel__line">
                    <span>{{ s.name }}<em v-if="s.domain"> · {{ s.domain }}</em></span>
                    <span>#{{ s.sid }}</span>
                    <span>{{ s.passkey_ok ? '✓' : '—' }}</span>
                    <span>{{ s.done_today }} / {{ s.cap }}</span>
                  </div>
                  <div v-if="!(reseedState.sites || []).length" class="magicflow-table-empty">没有可辅种的站点（与 IYUU 站点表对不上）</div>
                </div>
                <div class="magicflow-reseedpanel__row">
                  <span class="magicflow-field__sub">账本：{{ Object.entries(reseedState.ledger || {}).map((pair) => `${pair[0]} ${pair[1]}`).join(' · ') || '空（还没跑过）' }}</span>
                </div>
              </div>
              <p v-else class="magicflow-field__sub">加载中…</p>
            </div>
          </div>

          <div v-else-if="settingsTab === 'claim'" class="magicflow-settings-form">
            <div class="magicflow-settings-danger">
              <div class="magicflow-settings-danger__h"><VIcon icon="mdi-alert-outline" size="18" /> 不可逆的对外写操作</div>
              
            </div>
            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 开关</div>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="settingsDraft.claim_enabled" label="启用认领" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.claim_dry" label="干跑（只读，不认领）" color="primary" hide-details inset :disabled="!settingsDraft.claim_enabled" />
                <VSwitch v-model="settingsDraft.claim_exclude_zero_bonus" label="零魔种不认领" color="primary" hide-details inset />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-web" size="16" /> 站点白名单（留空 = 全站）</div>
              <VCombobox
                v-model="settingsDraft.claim_sites"
                :items="claimSiteOptions"
                label="认领站点（可多选 / 手输域名）"
                multiple
                chips
                closable-chips
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <span class="magicflow-field__sub">已选 {{ (settingsDraft.claim_sites || []).length }} 个 · 支持认领的站：{{ claimSiteOptions.join(' / ') || '（尚未探测，打开认领页后可见）' }}</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-tune" size="16" /> 限量 / 限速</div>
              <div class="magicflow-settings-grid">
                <VTextField v-model.number="settingsDraft.claim_daily_per_site" type="number" label="每站每天认领上限" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.claim_batch" type="number" label="单轮最多认领" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.claim_interval_sec" type="number" label="两次认领间隔（秒）" variant="outlined" density="comfortable" hide-details />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-shield-alert-outline" size="16" /> 安全阀（拿不准就留着）</div>
              <div class="magicflow-settings-grid">
                <VTextField v-model.number="settingsDraft.claim_min_age_days" type="number" label="最短发布天数（0=按站点规则）" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.claim_require_seeders" type="number" label="做种人数下限（0=不限）" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="settingsDraft.claim_min_size_gb" type="number" label="体积下限 GB（0=不限）" variant="outlined" density="comfortable" hide-details />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-seal-variant" size="16" /> 运行 / 状态
                <VSpacer />
                <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-open-in-new" @click="emit('open-claim')">打开认领页</VBtn>
              </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'template'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-file-cog-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">新建任务时预先填好的值</div>
              </div>
              <span class="magicflow-settings-lede__tag">仅预填</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-download-outline" /> 下载器与周期
              </div>
              <div class="magicflow-settings-grid">
                <VSelect
                  v-model="defaultsDraft.downloader"
                  :items="status.options.downloaders"
                  label="默认下载器"
                  placeholder="不指定（新建任务时再选）"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
                <VTextField v-model.number="defaultsDraft.brush_interval" type="number" min="1" label="选种周期（分钟）" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="defaultsDraft.check_interval" type="number" min="1" label="检查周期（分钟）" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="defaultsDraft.brush_seed_days" type="number" min="0" max="365" label="默认轮转周期(天)（0=按无上传）" variant="outlined" density="comfortable" hide-details />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-filter-variant" /> 候选与限量
              </div>
              <div class="magicflow-settings-grid">
                <VTextField v-model.number="defaultsDraft.max_add_per_run" type="number" min="1" label="单轮最多新增" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="defaultsDraft.max_download_concurrent" type="number" min="1" label="同时下载数上限" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="defaultsDraft.top_n" type="number" min="1" label="候选 TopN" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="defaultsDraft.browse_pages" type="number" min="1" label="每轮翻页数" variant="outlined" density="comfortable" hide-details />
                <VTextField v-model.number="defaultsDraft.seen_cooldown_hours" type="number" min="0" label="候选去重冷却（小时）" variant="outlined" density="comfortable" hide-details />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-broom" /> 清理策略
              </div>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="defaultsDraft.refill_when_empty" label="清理后自动补种" color="primary" hide-details inset />
                <VSwitch v-model="defaultsDraft.cleanup_no_progress" label="清理无进度种子" color="primary" hide-details inset />
                <VSwitch v-model="defaultsDraft.cleanup_slow_progress" label="清理过慢种子" color="primary" hide-details inset />
                <VSwitch v-model="defaultsDraft.purge_unfree_incomplete" label="清理「已非免费」未下完种子" color="primary" hide-details inset />
                <VSwitch v-model="defaultsDraft.auto_resume_paused" label="自动恢复被暂停种子" color="primary" hide-details inset />
                <VSwitch v-model="defaultsDraft.delete_files" label="删种同时删除文件" color="primary" hide-details inset />
              </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'exam'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-school-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">盯住各站新手考核，缺什么一键补</div>
              </div>
            </div>


            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 开关</div>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="settingsDraft.exam_enabled" label="启用「新手考核」（关闭则不抓取、不显示）" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.exam_include_pass" label="显示「已通过」的考核（默认只显示未通过）" color="primary" hide-details inset :disabled="!settingsDraft.exam_enabled" />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-web" /> 考核站点
              </div>
              <div class="magicflow-settings-field">
                <VSelect
                  v-model="settingsDraft.exam_sites"
                  :items="siteSelectItems"
                  label="考核站点"
                  multiple
                  chips
                  closable-chips
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  :disabled="!settingsDraft.exam_enabled"
                />
                <p class="magicflow-settings-hint">只盯你关心的站；不选＝全都盯</p>
              </div>
              <p v-if="!settingsDraft.exam_enabled" class="magicflow-settings-hint magicflow-settings-hint--warn">
                当前处于<strong>关闭</strong>状态：不会去抓考核，也不会做任何额外请求。
              </p>
            </div>
          </div>

          <div v-else-if="settingsTab === 'signin'" class="magicflow-settings-form">
            <div class="magicflow-signin-hero">
              <span class="magicflow-signin-hero__icon"><VIcon icon="mdi-calendar-check-outline" size="20" /></span>
              <div class="magicflow-signin-hero__body">
                <div class="magicflow-signin-hero__title">
                  <span>站点签到 / 模拟登录</span>
                  <VChip size="small" variant="tonal" :color="settingsDraft.signin_enabled ? 'success' : 'grey'">
                    {{ settingsDraft.signin_enabled ? '已启用' : '已关闭' }}
                  </VChip>
                </div>
                <div class="magicflow-signin-hero__desc">
                  勾选站点即可，其余全自动完成。
                </div>
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" size="16" /> 开关</div>
              <div class="magicflow-switch-list">
                <VSwitch v-model="settingsDraft.signin_enabled" label="启用站点签到 / 模拟登录" color="primary" hide-details inset density="comfortable" />
                <VSwitch v-model="settingsDraft.signin_notify" label="结果推送通知" color="primary" hide-details inset density="comfortable" :disabled="!settingsDraft.signin_enabled" />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-web" size="16" /> 站点选择（勾选即生效）</div>
              <div class="magicflow-field-stack">
                <div class="magicflow-field">
                  <VSelect
                    v-model="settingsDraft.signin_sites"
                    :items="siteSelectItems"
                    label="签到站点"
                    multiple
                    chips
                    closable-chips
                    variant="outlined"
                    density="comfortable"
                    hide-details
                  />
                  <span class="magicflow-field__sub">已选 {{ (settingsDraft.signin_sites || []).length }} 个站点</span>
                </div>
                <div class="magicflow-field">
                  <VSelect
                    v-model="settingsDraft.signin_login_sites"
                    :items="siteSelectItems"
                    label="模拟登录站点"
                    multiple
                    chips
                    closable-chips
                    variant="outlined"
                    density="comfortable"
                    hide-details
                  />
                  <span class="magicflow-field__sub">已选 {{ (settingsDraft.signin_login_sites || []).length }} 个站点 · 保活 Cookie + 刷新站点数据</span>
                </div>
              </div>
            </div>

            <div class="magicflow-signin-actions">
              <VBtn size="small" color="primary" variant="tonal" prepend-icon="mdi-chart-box-outline" @click="emit('open-signin')">查看签到报表</VBtn>
            </div>
          </div>

          <div v-else-if="settingsTab === 'live'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-access-point" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">把站点数据从「6 小时前」变成「刚刚」</div>
              </div>
              <span class="magicflow-settings-lede__tag is-warn">会耗 PV</span>
            </div>


            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 实时采样</div>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="settingsDraft.live_enabled" label="启用站点实时数据 + 流量监控" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.live_notify" label="命中告警时推送通知" color="primary" hide-details inset :disabled="!settingsDraft.live_enabled" />
                <VSwitch v-model="settingsDraft.live_auto_stop" label="同时把该站「运行中」任务切「做种中」（只停调度）" color="primary" hide-details inset :disabled="!settingsDraft.live_enabled" />
              </div>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-model.number="settingsDraft.live_interval_minutes"
                  type="number"
                  min="1"
                  label="采样周期（分钟）"
                  hint="默认 4 分钟；太频繁站点吃不消"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.live_download_alert_mb"
                  type="number"
                  min="1"
                  label="下载增长告警阈值（MB/分钟）"
                  hint="超过则告警；默认 50"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.live_ratio_target"
                  type="number"
                  min="0"
                  step="0.05"
                  label="分享率目标线"
                  hint="低于则告警并算缺口；0 = 不检查"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-shield-alert-outline" /> 流量兜底
              </div>
              <p class="magicflow-settings-hint">
                三处都会核对：<em>任务内</em>回种子详情页核对（开关在任务「高级」里，受本总开关约束）、
                <em>全局</em>用站点「正在下载」列表核对、<em>取种期间</em>核对来源站。
              </p>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="settingsDraft.promo_guard" label="启用流量兜底（关掉＝下面三项只告警、不动手）" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.live_kill_unfree" :disabled="!settingsDraft.promo_guard" label="全局：下载量异常增长时，干掉站点里非免费的下载" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.live_kill_delete_files" :disabled="!settingsDraft.promo_guard || !settingsDraft.live_kill_unfree" label="干掉时连文件一起删（只动名称+体积对得上的下载中种）" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.crossseed_guard" :disabled="!settingsDraft.promo_guard" label="取种期间核对来源站免费状态；判错就删种并拉黑（建议开启）" color="primary" hide-details inset />
              </div>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-model.number="settingsDraft.crossseed_guard_pct"
                  type="number"
                  min="0"
                  max="100"
                  step="0.5"
                  :disabled="!settingsDraft.promo_guard || !settingsDraft.crossseed_guard"
                  label="下载增量阈值（体积的 %）"
                  hint="下载增量超过目标体积该比例即判「不免费」（默认 5%）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.crossseed_guard_min_mb"
                  type="number"
                  min="0"
                  step="10"
                  :disabled="!settingsDraft.promo_guard || !settingsDraft.crossseed_guard"
                  label="最小判定增量（MB）"
                  hint="避免统计抖动误判，默认 50MB"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.crossseed_guard_interval_min"
                  type="number"
                  min="1"
                  max="1440"
                  step="1"
                  :disabled="!settingsDraft.promo_guard || !settingsDraft.crossseed_guard"
                  label="兜底核对间隔（分钟）"
                  hint="同一来源站两次核对的间隔（默认 15 分钟，各花 1 次请求）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
              </div>
            </div>

            <div v-if="siteLiveAlerts.length" class="magicflow-live-alerts">
              <div class="magicflow-live-alerts__head">当前「{{ selectedTask?.name }}」站点告警</div>
              <div v-for="(alert, idx) in siteLiveAlerts" :key="`live-cfg-${idx}`" class="magicflow-live-alert" :class="`magicflow-live-alert--${alert.level || 'info'}`">
                {{ alert.text }}
              </div>
            </div>
          </div>
          <div v-else-if="settingsTab === 'recommend'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-star-shooting-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">刷流时顺带挑出值得收藏的片</div>
              </div>
              <span class="magicflow-settings-lede__tag">受闸门保护</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 开关</div>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="settingsDraft.recommend_enabled" label="启用推荐甄别" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.recommend_require_chart" label="榜单 / 热映 / 订阅命中也算达标（与评分为「或」）" color="primary" hide-details inset :disabled="!settingsDraft.recommend_enabled" />
                <VSwitch v-model="settingsDraft.recommend_auto_import" label="确认后自动整理入库" color="primary" hide-details inset :disabled="!settingsDraft.recommend_enabled" />
                <VSwitch v-model="settingsDraft.recommend_notify" label="发现推荐时通知" color="primary" hide-details inset :disabled="!settingsDraft.recommend_enabled" />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-gauge" /> 门槛与回收
              </div>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-model.number="settingsDraft.recommend_min_rating"
                  type="number"
                  min="0"
                  max="10"
                  step="0.1"
                  label="评分门槛（高于）"
                  hint="评分高于该值才推荐（默认 7.5）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.recommend_enabled"
                />
                <VTextField
                  v-model.number="settingsDraft.recommend_expire_days"
                  type="number"
                  min="0"
                  step="1"
                  label="推荐过期天数"
                  hint="超过该天数仍未确认即视为过期（0＝不过期）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.recommend_enabled"
                />
                <VTextField
                  v-model.number="settingsDraft.recommend_temp_ttl_days"
                  type="number"
                  min="0"
                  step="1"
                  label="临时种 TTL（天）"
                  hint="未入选推荐的刷流临时种，超过该天数回收"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.recommend_enabled"
                />
                <VTextField
                  v-model.number="settingsDraft.recommend_disk_min_free_gb"
                  type="number"
                  min="0"
                  step="1"
                  label="磁盘余量下限（GB）"
                  hint="剩余空间低于该值时推荐立即过期"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.recommend_enabled"
                />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-source-branch" /> 评分来源与标签
              </div>
              <div class="magicflow-settings-grid">
                <VSelect
                  v-model="settingsDraft.recommend_rating_source"
                  :items="ratingSourceItems"
                  item-title="title"
                  item-value="value"
                  label="评分来源"
                  hint="豆瓣优先走本地服务 magicflow-douban"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.recommend_enabled"
                />
                <VSelect
                  v-model="settingsDraft.recommend_episode_policy"
                  :items="episodePolicyItems"
                  item-title="title"
                  item-value="value"
                  label="单集策略"
                  hint="默认不自动推荐，要整季请点推荐列表的「订阅整季」"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.recommend_enabled"
                />
                <VTextField
                  v-model="settingsDraft.recommend_douban_service_url"
                  label="豆瓣服务地址"
                  placeholder="http://magicflow-douban:18789"
                  hint="留空用默认；本地查询不限流"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model="settingsDraft.recommend_tag"
                  label="推荐标签"
                  hint="推荐资源单独打的标签，默认「魔流-推荐」"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                  :disabled="!settingsDraft.recommend_enabled"
                />
              </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'rules'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-shield-check-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">全站 H&amp;R 的唯一入口</div>
              </div>
              <span class="magicflow-settings-lede__tag is-warn">影响开账</span>
            </div>


            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-radar" /> 自动探测</div>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="settingsDraft.rules_auto_refresh" label="每周自动逐站探测规则并入库" color="primary" hide-details inset />
              </div>
              <p class="magicflow-settings-hint">
                到点才跑：每 10 分钟醒来看一眼，满 7 天才真探一次；<strong>重启/更新不会把周期清零</strong>，
                探测失败按 30 分钟 → 6 小时退避重试（不再一次失败干等一周）。
              </p>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-tune" /> 全局默认
              </div>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-model.number="settingsDraft.crossseed_seed_hours_default"
                  type="number"
                  min="0"
                  max="720"
                  step="1"
                  label="来源站义务工时（小时）"
                  hint="来源站未单独指定时的 H&amp;R 义务工时，默认 24h"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.hr_seed_margin_hours"
                  type="number"
                  step="0.5"
                  min="0"
                  label="H&amp;R 结清安全垫（小时）"
                  hint="做种需 ≥ 站点要求 + 该值才判结清（默认 2，0＝不留垫）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.hr_deadline_warn_hours"
                  type="number"
                  step="1"
                  min="0"
                  label="H&amp;R 账单临期阈值（小时）"
                  hint="未达标且距期限 ≤ 该值 → 账单标 at_risk（默认 48）"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
                <VTextField
                  v-model.number="settingsDraft.hr_complete_ratio"
                  type="number"
                  step="0.001"
                  min="0"
                  max="1"
                  label="H&amp;R 完成度阈值（全局默认）"
                  hint="达到该进度才计 H&amp;R（默认 99.9%）；分站可在下表覆盖"
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-seed-outline" /> 来源份保护与回收</div>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="settingsDraft.crossseed_guard_keep_seed" label="来源份 H&amp;R 保护（义务工时内不得删/改标签）" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.crossseed_reclaim" label="H&amp;R 期满后回收来源份（只删种子不删文件）" color="warning" hide-details inset />
              </div>
            </div>
            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-table-cog" /> 逐站规则
                <span class="magicflow-settings-block__note">共 {{ siteRules.length }} 条</span>
              </div>
            <div class="magicflow-rules-actions">
              <VBtn size="small" color="primary" variant="tonal" :loading="rulesProbing" @click="emit('probe-rules')">
                <VIcon start size="small">mdi-download-network-outline</VIcon>逐站拉取（探测页面）
              </VBtn>
              <VBtn size="small" variant="text" :disabled="rulesLoading" @click="emit('refresh-rules')">按 MP 配置补全</VBtn>
              <span class="magicflow-settings-hint">上次自动探测：{{ rulesProbeState?.at ? fmtTs(rulesProbeState.at) : '从未探测' }}<template v-if="rulesProbeState?.fail">（连续失败 {{ rulesProbeState.fail }} 次，自动退避重试中）</template></span>
            </div>
            <p v-if="rulesProbing" class="magicflow-settings-hint">正在逐站抓取规则页（每站 1~2 个请求，随机歇 1.5~3.5 秒）…</p>
            <div class="magicflow-rules-table">
              <div class="magicflow-rules-row magicflow-rules-row--head">
                <span>站点 · 来源</span><span>H&amp;R</span><span>达标小时</span><span>完成度</span><span></span>
              </div>
              <div v-for="row in siteRules" :key="row.domain" class="magicflow-rules-row">
                <span class="magicflow-rules-row__name" :title="row.domain">
                  <b>{{ row.site_name || row.domain }}</b>
                  <em v-if="!row.in_library">未入库</em>
                  <em v-if="row.exam_avg_hours" :title="row.exam_evidence || '站点考核的平均做种要求（不是 H&R）'">考核{{ row.exam_avg_hours }}h</em>
                  <!-- ★ 任务 129：标了「无 H&R」的站不再显示期限（旧数据显示 hr=false 还挂着 360h，自相矛盾） -->
                  <i :title="row.evidence || ''">{{ ruleSourceText(row) }}<template v-if="row.seed_cap"> · 上限{{ row.seed_cap }}</template><template v-if="row.seed_window_hours && row.hr !== false"> · 期限{{ row.seed_window_hours }}h</template><template v-if="row.seed_window_hours_seen != null && row.hr !== false"> · 见{{ row.seed_window_hours_seen }}h</template></i>
                </span>
                <span class="magicflow-rules-row__hr">
                  <VChip v-if="row.hr === true" size="x-small" color="error" variant="tonal">有</VChip>
                  <VChip v-else-if="row.hr === false" size="x-small" color="success" variant="tonal">无</VChip>
                  <VChip v-else size="x-small" variant="tonal">未知</VChip>
                  <!-- ★ 只对「手填覆盖」给恢复入口：来源已是内置/探测/收件箱时，恢复是语义 no-op
                       （回落后结论相同），旧条件只判 hr===false → 按钮永远在、点了看不出变化。 -->
                  <VBtn v-if="row.hr === false && row.hr_source === 'manual'" size="x-small" variant="text" :disabled="rulesProbing" title="恢复为探测/内置判定（清除手动标记）" @click="emit('set-rule-hr', row, 'unknown')">恢复</VBtn>
                  <template v-else>
                    <VBtn size="x-small" variant="text" :disabled="rulesProbing" title="该站有 H&R：手动确认「有」并按当前时长保护" @click="emit('set-rule-hr', row, '1')">标有</VBtn>
                    <VBtn size="x-small" variant="text" :disabled="rulesProbing" title="该站没有 H&R：直接标无，不做保种保护" @click="emit('set-rule-hr', row, '0')">标无</VBtn>
                  </template>
                </span>
                <span class="magicflow-rules-row__hours">
                  <VTextField
                    :model-value="row.hr === false ? '' : (row.seed_need_hours ?? '')"
                    type="number"
                    min="0"
                    max="720"
                    step="1"
                    density="compact"
                    variant="outlined"
                    hide-details
                    label="达标小时"
                    :disabled="row.hr === false"
                    :placeholder="row.hr === false ? '无 H&R' : '未探明'"
                    :title="row.hr === false
                      ? '该站已标「无 H&R」，不设达标小时'
                      : 'H&R 要求做满的做种小时（判结清用的就是它）。留空＝未探明，按 24h 保守兜底'"
                    @change="emit('set-rule-hours', row, $event.target.value)"
                  />
                </span>
                <span class="magicflow-rules-row__ratio">
                  <VTextField
                    :model-value="row.complete_ratio"
                    type="number"
                    min="0"
                    max="1"
                    step="0.001"
                    density="compact"
                    variant="outlined"
                    hide-details
                    label="完成度"
                    placeholder="跟全局"
                    :title="row.complete_ratio == null ? '未覆盖，用全局「H&amp;R 完成度阈值」' : '站点级覆盖（进度达到该值才计 H&amp;R）'"
                    @change="emit('set-rule-ratio', row, $event.target.value)"
                  />
                </span>
                <span class="magicflow-rules-row__ops">
                  <VBtn
                    v-if="row.rule_url"
                    size="x-small"
                    variant="text"
                    icon
                    :href="String(row.rule_url).split(/\s+/)[0]"
                    target="_blank"
                    rel="noopener"
                    :title="'规则地址（来自收件箱欢迎短讯）：' + row.rule_url"
                  ><VIcon size="x-small">mdi-link-variant</VIcon></VBtn>
                  <VBtn size="x-small" variant="text" :disabled="rulesProbing" title="只探测这一站" @click="emit('probe-rules', row.domain)">探测</VBtn>
                </span>
              </div>
            </div>
            <details class="magicflow-rules-help">
              <summary>怎么改 / 取值说明</summary>
              <p class="magicflow-settings-hint">
                <strong>达标小时</strong>：H&amp;R 要求做满多少小时（例：学校「10 天内做种 20 小时」→ 20）。
                判结清读的就是它；留空＝未探明，按 24h 保守兜底。直接改 = 手填覆盖
                （优先级：手填 &gt; 探测 &gt; 内置 &gt; 全局默认）。该站标了「无 H&amp;R」→ 此列禁用并清空。
              </p>
              <p class="magicflow-settings-hint">
                <strong>完成度</strong>：进度达到多少才算「下载完成」并开始计 H&amp;R。<strong>留空 = 跟全局</strong>
                （默认 0.999，下满才算）；某站若规定「下载中即计 H&amp;R」→ 在该站填 <code>0.2</code> 之类。
              </p>
              <p class="magicflow-settings-hint">
                每个站只有两个时长数字：<strong>达标小时</strong>（做满多少才算清，上面可改）与
                <strong>期限</strong>（多久之内要做满，例：10 天，探测从规则原文写入，不在这里改）。
                标「无 H&amp;R」时两者一并清空。
              </p>
            </details>
            </div>
          </div>

          <div v-else-if="settingsTab === 'tags'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-tag-multiple-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">用标签把每个种子的状态写清楚</div>
              </div>
              <span class="magicflow-settings-lede__tag">可自愈</span>
            </div>


            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 标签模型</div>
              <div class="magicflow-settings-switches">
                <VSwitch v-model="settingsDraft.tag_model_enabled" label="启用标签模型（状态账本 + 魔流-站点-状态 标签）" color="primary" hide-details inset />
                <VSwitch v-model="settingsDraft.show_qb_tags" label="往 qB 写标签（关=纯账本模式）" color="primary" hide-details inset />
              </div>
              <div class="magicflow-settings-grid">
                <VTextField v-model.number="settingsDraft.tag_silent_new_timeout_hours" type="number" min="0" step="1"
                  label="「静默-新」超时(小时)" hint="超过该时长未分拣自动归「静默-普通」（0＝不超时）"
                  persistent-hint variant="outlined" density="comfortable" />
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-filter-cog-outline" /> 静默分拣规则
              </div>
              <div class="magicflow-sort-rules">
                <div class="magicflow-sort-rules__row magicflow-sort-rules__row--head">
                  <span>规则</span><span>阈值</span><span>权重</span><span>启用</span><span></span>
                </div>
                <div v-for="(r, i) in settingsDraft.sort_rules" :key="i" class="magicflow-sort-rules__row">
                  <span>{{ sortRuleText(r) }}</span>
                  <span>
                    <VTextField v-if="sortRuleNeedsMin(r.type)" v-model.number="r.min" type="number" step="0.5" density="compact" variant="outlined" hide-details style="max-width: 110px" />
                    <em v-else>-</em>
                  </span>
                  <span>
                    <VTextField v-model.number="r.weight" type="number" step="5" density="compact" variant="outlined" hide-details style="max-width: 90px" />
                  </span>
                  <span>
                    <VSwitch v-model="r.enabled" color="primary" density="compact" hide-details inset />
                  </span>
                  <span>
                    <VBtn size="x-small" variant="text" color="error" icon="mdi-close" aria-label="删除这条规则" title="删除这条规则" @click="emit('remove-sort-rule', i)" />
                  </span>
                </div>
              </div>
              <div class="magicflow-sort-rules__add">
                <VSelect v-model="newRuleType" :items="sortRuleTypeOptions" item-title="text" item-value="value"
                  density="compact" variant="outlined" hide-details style="max-width: 200px" label="新增规则" />
                <VBtn size="small" variant="tonal" color="primary" @click="emit('add-sort-rule')">加上</VBtn>
              </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-database-outline" /> 账本</div>
              <span class="magicflow-field__sub">账本 {{ tagInfo?.ledger_count ?? 0 }} 条 · 文件组 {{ tagInfo?.groups?.groups ?? 0 }}（多站 {{ tagInfo?.groups?.multi_site_groups ?? 0 }}）</span>
            </div>
          </div>

          <div v-else-if="settingsTab === 'crossseed'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-swap-horizontal" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">本站非免费，就去兄弟站免费下</div>
              </div>
              <span class="magicflow-settings-lede__tag">本页无独立参数</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-map-marker-path" /> 这套东西分别在哪配</div>
              <div class="magicflow-field-stack">
                <div class="magicflow-field">
                    </div>
                <div class="magicflow-field">
                    </div>
                <div class="magicflow-field">
                    </div>
              </div>
              <div class="magicflow-settings-goto">
                <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-access-point" @click="emit('open-tab', 'live')">站点监控 · 流量兜底</VBtn>
                <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-seed-outline" @click="emit('open-tab', 'reseed')">全站辅种</VBtn>
                <VBtn size="small" variant="text" prepend-icon="mdi-tag-multiple-outline" @click="emit('open-tab', 'tags')">标签管理</VBtn>
              </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'fallback'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-file-document-refresh-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">TMDB 查不到的片子，用多源兜底补 NFO</div>
              </div>
              <span class="magicflow-settings-lede__tag">只写 NFO</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 开关</div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.fallback_enabled" label="启用元数据兜底" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.fallback_after_import" label="每次整理入库后自动兜底" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.fallback_dry_run" label="演练模式（只报告不写 NFO）" color="primary" hide-details inset />
            </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-sort-numeric-ascending" /> 识别来源顺序</div>
            <div class="magicflow-settings-field">
              <ol class="magicflow-fb-sources">
                <li v-for="(src, idx) in usedFallbackSources" :key="src" class="magicflow-fb-source">
                  <span class="magicflow-fb-source__idx">{{ idx + 1 }}</span>
                  <span class="magicflow-fb-source__name">{{ fallbackSourceLabel(src) }}</span>
                  <VBtn icon="mdi-arrow-up" size="x-small" variant="text" :disabled="idx === 0" aria-label="上移" @click="emit('move-fallback-source', idx, -1)" />
                  <VBtn icon="mdi-arrow-down" size="x-small" variant="text" :disabled="idx === usedFallbackSources.length - 1" aria-label="下移" @click="emit('move-fallback-source', idx, 1)" />
                  <VBtn icon="mdi-close" size="x-small" variant="text" aria-label="移除" @click="emit('remove-fallback-source', src)" />
                </li>
              </ol>
              <div class="magicflow-fb-source-add">
                <VSelect
                  v-model="fallbackSourceDraft"
                  :items="unusedFallbackSources"
                  item-title="title"
                  item-value="value"
                  label="添加来源"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  clearable
                />
                <VBtn variant="tonal" color="primary" :disabled="!fallbackSourceDraft" @click="emit('add-fallback-source')">添加</VBtn>
              </div>
            </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-folder-search-outline" /> 扫描范围与频率
              </div>
            <VCombobox
              v-model="settingsDraft.fallback_paths"
              :items="fallbackState?.effective_paths || []"
              label="兜底扫描的库目录"
              hint="留空 = 自动取 MoviePilot 目录配置里的 library 路径（如 /movie）"
              persistent-hint
              variant="outlined"
              density="comfortable"
              multiple
              chips
              clearable
            />

            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.fallback_interval_minutes"
                type="number"
                label="扫描周期（分钟）"
                hint="定时扫库兜底，默认 30"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.fallback_scan_max"
                type="number"
                label="每轮最多处理剧集数"
                hint="其余下轮继续，避免一次卡爆，默认 30"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>

            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.fallback_sp_to_s00" label="特别篇归位：源中不存在的集改归 Season 0（S00EXX）" color="primary" hide-details inset />
            </div>
            </div>
            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-play-circle-outline" /> 运行与报告</div>

            <div class="magicflow-fb-actions">
              <VBtn variant="tonal" color="primary" size="small" :loading="fallbackRunning" :disabled="fallbackRunning" @click="emit('run-fallback', true)">演练扫描</VBtn>
              <VBtn variant="flat" color="primary" size="small" :loading="fallbackRunning" :disabled="fallbackRunning" @click="emit('run-fallback', false)">立即执行</VBtn>
              <VBtn variant="text" size="small" :loading="fallbackLoading" @click="emit('load-fallback')">刷新结果</VBtn>
              <span v-if="fallbackState?.running" class="magicflow-fb-running">● 扫描中…</span>
            </div>

            <div v-if="fallbackState?.report" class="magicflow-fb-report">
              <div class="magicflow-fb-report__line">
                上次{{ fallbackState.report.applied === false ? '演练' : '执行' }}：
                扫描 {{ fallbackState.report.stats?.shows || 0 }} 剧<template v-if="fallbackState.report.stats?.total_shows">/共 {{ fallbackState.report.stats.total_shows }} 部</template> ·
                识别 {{ fallbackState.report.stats?.resolved || 0 }} ·
                补集 NFO {{ fallbackState.report.stats?.ep_nfo || 0 }} ·
                补剧 NFO {{ fallbackState.report.stats?.show_nfo || 0 }} ·
                源中缺失 {{ fallbackState.report.stats?.missing || 0 }} ·
                多源补齐 {{ fallbackState.report.stats?.via_extra || 0 }} 集 ·
                归位 {{ fallbackState.report.stats?.renumbered || 0 }} ·
                {{ fallbackState.report.duration }}s
              </div>
              <details v-if="fallbackProblemShows.length" class="magicflow-fb-report__details">
                <summary>源里查不到的集（{{ fallbackProblemCount }} 集，已按本地文件兜底）</summary>
                <ul class="magicflow-fb-report__list">
                  <li v-for="item in fallbackProblemShows" :key="item.show">
                    <strong>{{ item.show }}</strong>
                    <span class="magicflow-fb-report__meta">{{ (item.problems || []).map(p => `S${String(p.season).padStart(2, '0')}E${String(p.episode).padStart(2, '0')}`).join(' ') }}</span>
                  </li>
                </ul>
              </details>
              <details v-if="(fallbackState.report.shows || []).length" class="magicflow-fb-report__details">
                <summary>展开本剧集明细（{{ fallbackState.report.shows.length }} 部有变动）</summary>
                <ul class="magicflow-fb-report__list">
                  <li v-for="item in fallbackState.report.shows" :key="item.show">
                    <strong>{{ item.show }}</strong>
                    <span class="magicflow-fb-report__meta">识别自 {{ item.resolved || '未命中' }}｜补集 {{ (item.episodes || []).filter(e => e.nfo).length }}｜归位 {{ (item.renumbered || []).length }}</span>
                  </li>
                </ul>
              </details>
            </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'cloud'" class="magicflow-settings-form">
            <div class="magicflow-settings-lede">
              <VIcon icon="mdi-cloud-upload-outline" />
              <div class="magicflow-settings-lede__bd">
                <div class="magicflow-settings-lede__t">本地当热区，夸克当冷库</div>
              </div>
              <span class="magicflow-settings-lede__tag is-warn">默认不删本地</span>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-toggle-switch-outline" /> 开关</div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.cloud_enabled" label="启用云盘归档" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.cloud_dry_run" label="演练模式（只列计划，不真传）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.cloud_notify" label="完成后通知" color="primary" hide-details inset />
            </div>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-lan-connect" /> 连接</div>
              <div class="magicflow-iyuu-token">
                <VTextField
                  v-model="settingsDraft.cloud_openlist_url"
                  label="OpenList 地址"
                  placeholder="http://192.168.0.61:12022"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  autocomplete="off"
                />
              </div>
              <div class="magicflow-iyuu-token mt-2">
                <VTextField
                  v-model="settingsDraft.cloud_openlist_token"
                  label="OpenList Token"
                  :placeholder="cloudCfg.has_token ? '已保存（留空则不修改）' : 'openlist-…'"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  autocomplete="off"
                  persistent-hint
                  hint="留空＝保留已存 Token；Token 不回显"
                />
                <VBtn
                  variant="tonal"
                  color="primary"
                  size="small"
                  prepend-icon="mdi-connection"
                  :loading="cloudTesting"
                  @click="emit('test-cloud')"
                >测试</VBtn>
              </div>
              <p v-if="cloudTestMsg" class="magicflow-settings-feedback" :class="cloudTestOk ? 'is-ok' : 'is-no'">{{ cloudTestMsg }}</p>
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-folder-arrow-up-down-outline" /> 路径模板</div>
            <div class="magicflow-settings-grid">
              <VTextField
                v-model="settingsDraft.cloud_source_mount"
                label="可写存储路径"
                hint="OpenList 里可写的存储挂载点，默认 /quark"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model="settingsDraft.cloud_strm_mount"
                label="Strm 视图路径"
                hint="只读校验用（Strm 驱动），默认 /movie"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>

            <VTextField
              v-model="settingsDraft.cloud_target_template"
              label="远端目标模板"
              hint="{rel}＝相对库根的路径；默认 /quark/movie/{rel}（与本地库同构）"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />

            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-filter-variant" /> 归档范围与限速
              </div>
            <VCombobox
              v-model="settingsDraft.cloud_paths"
              label="扫描目录（容器内路径，留空 = /movie）"
              hint="可多个；只扫这些库根下的媒体文件"
              persistent-hint
              variant="outlined"
              density="comfortable"
              chips
              multiple
              clearable
              :items="['/movie']"
            />

            <VCombobox
              v-model="settingsDraft.cloud_exclude_paths"
              label="排除路径（子串匹配）"
              hint="默认已排除下载区/刷流区/蓝光原盘；这里可再加"
              persistent-hint
              variant="outlined"
              density="comfortable"
              chips
              multiple
              clearable
              :items="['/movie/刷流', '/movie/下载']"
            />

            <VCombobox
              v-model="settingsDraft.cloud_exclude_tags"
              label="排除标签（做种中的种不打上传策略标，可留空）"
              variant="outlined"
              density="comfortable"
              chips
              multiple
              clearable
              :items="['魔流-推荐', '辅种', '已整理']"
            />

            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.cloud_min_size_gb"
                type="number"
                label="最小体积（GB，0 = 不限）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="settingsDraft.cloud_max_size_gb"
                type="number"
                label="最大体积（GB，0 = 不限）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="settingsDraft.cloud_min_age_days"
                type="number"
                label="最小入库天数（0 = 不限）"
                hint="只归档入库较久、已经稳定的资源"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.cloud_upload_limit_mbps"
                type="number"
                label="上传限速（Mbps，0 = 不限）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="settingsDraft.cloud_interval_minutes"
                type="number"
                label="后台归档周期（分钟）"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VTextField
                v-model.number="settingsDraft.cloud_scan_max"
                type="number"
                label="每轮最多处理文件数"
                variant="outlined"
                density="comfortable"
                hide-details
              />
            </div>

            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head">
                <VIcon icon="mdi-alert-outline" /> 危险区
              </div>

            <div class="magicflow-settings-switches">
              <VSwitch
                v-model="settingsDraft.cloud_delete_local"
                label="归档后删除本地文件（危险：会停种；插件只记录、不自动执行）"
                color="error"
                hide-details
                inset
              />
              <VSwitch
                v-model="settingsDraft.cloud_remove_torrent"
                label="同时移除下载器任务（危险，需人工确认）"
                color="error"
                hide-details
                inset
              />
            </div>
              <p class="magicflow-settings-hint magicflow-settings-hint--warn">
                安全默认：<strong>不删本地、不停种</strong>。删本地需要逐条上传校验通过后手动确认，绝不会自动执行。
              </p>
            </div>
          </div>
        </div>

        <footer class="magicflow-settings-dialog__footer">
          <VBtn
            v-if="settingsTab === 'downloader'"
            variant="tonal"
            color="primary"
            :disabled="!downloaderPrefsRecommended"
            @click="emit('apply-recommended')"
          >
            恢复推荐值
          </VBtn>
          <VSpacer />
          <VBtn variant="text" @click="settingsDialog = false">取消</VBtn>
          <VBtn color="primary" variant="flat" :loading="saving" @click="emit('save')">保存</VBtn>
        </footer>
      </VCard>
    </VDialog>
</template>

<style scoped>
.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.magicflow-rules-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem 0.5rem;
  margin: 0.75rem 0 0.25rem;
}

.magicflow-rules-table {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.5rem;
  max-height: 46vh;
  overflow-y: auto;
}

.magicflow-sort-rules {
  max-height: 34vh;
  overflow-y: auto;
  margin-bottom: 0.5rem;
}

.magicflow-sort-rules__row {
  display: grid;
  grid-template-columns: minmax(9rem, 1.6fr) 7rem 6rem 4rem 4rem;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.magicflow-sort-rules__row:nth-child(even) {
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.magicflow-sort-rules__row--head {
  font-weight: 600;
  opacity: var(--mf-op-mid);
}

.magicflow-sort-rules__add {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.magicflow-rules-row {
  display: grid;
  grid-template-columns: minmax(7rem, 1fr) auto 4.5rem 4.5rem auto;
  grid-template-areas: "name hr hours ratio ops";
  align-items: center;
  gap: 0.5rem;
  padding: 0.3rem 0.5rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.magicflow-rules-row:nth-child(even) {
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.magicflow-rules-row--head {
  font-weight: 600;
  font-size: 0.75rem;
  opacity: var(--mf-op-mid);
}

.magicflow-rules-row--head > span:nth-child(1) { grid-area: name; }
.magicflow-rules-row--head > span:nth-child(2) { grid-area: hr; }
.magicflow-rules-row--head > span:nth-child(3) { grid-area: hours; }
.magicflow-rules-row--head > span:nth-child(4) { grid-area: ratio; }
.magicflow-rules-row--head > span:nth-child(5) { grid-area: ops; }

.magicflow-rules-row__name {
  grid-area: name;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.1rem 0.35rem;
  min-width: 0;
}

.magicflow-rules-row__name b {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.magicflow-rules-row__name em {
  flex-shrink: 0;
  font-style: normal;
  font-size: 0.7rem;
  opacity: var(--mf-op-dim);
}

/* 来源/上限/义务工时长 —— 站点名下面那行小字，独占一行 */
.magicflow-rules-row__name i {
  flex-basis: 100%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-style: normal;
  font-size: 0.7rem;
  line-height: 1.15;
  opacity: var(--mf-op-soft);
}

.magicflow-rules-row__hr {
  grid-area: hr;
  display: inline-flex;
  align-items: center;
  gap: 0.05rem;
  flex-shrink: 0;
}

.magicflow-rules-row__hours { grid-area: hours; min-width: 0; }
.magicflow-rules-row__ratio { grid-area: ratio; min-width: 0; }

.magicflow-rules-row__ops {
  grid-area: ops;
  display: inline-flex;
  align-items: center;
  gap: 0.05rem;
  flex-shrink: 0;
}

.magicflow-rules-help {
  margin-top: 0.45rem;
  font-size: 0.8rem;
}

.magicflow-rules-help summary {
  cursor: pointer;
  font-size: 0.75rem;
  opacity: var(--mf-op-mid);
}

.magicflow-rules-help summary:hover {
  opacity: 1;
}

.magicflow-rules-help p {
  margin: 0.35rem 0 0;
}

.magicflow-settings-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
}

.magicflow-scope-tag {
  margin-inline-start: 6px;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 10px;
  line-height: 1.6;
  opacity: var(--mf-op-dim);
  border: 1px solid currentColor;
}

.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
}

.magicflow-settings-dialog__tabs {
  padding-inline: 8px;
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

.magicflow-settings-hint--warn {
  background: rgba(var(--v-theme-warning), 0.12);
  border-inline-start-color: rgba(var(--v-theme-warning), 0.7);
}

.magicflow-settings-dialog {
  display: flex;
  flex-direction: column;
  block-size: min(84vh, 40rem);
  max-block-size: 92vh;
  overflow: hidden;
}

.magicflow-settings-dialog__head,
.magicflow-settings-dialog__tabs,
.magicflow-settings-dialog > .v-divider {
  flex: 0 0 auto;
}

.magicflow-settings-dialog__body {
  flex: 1 1 0;
  min-block-size: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scroll-padding-block: 8px;
}

.magicflow-settings-form {
  display: grid;
  gap: 14px;
  align-content: start;
  padding: 16px 18px 14px;
}

.magicflow-settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}

.magicflow-settings-switches {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 16px;
}

.magicflow-tile-switches {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px 14px;
  margin-top: 6px;
}

@media (max-width: 599px) {
.magicflow-tile-switches {
 grid-template-columns: repeat(2, minmax(0, 1fr)); 
}
}

.magicflow-reseedpanel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.7));
  border-radius: 10px;
  background: rgba(var(--v-theme-surface), 0.35);
}

.magicflow-reseedpanel__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  line-height: 1.5;
}

.magicflow-reseedpanel__sites {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 2px;
}

.magicflow-reseedpanel__head,
.magicflow-reseedpanel__line {
  display: grid;
  grid-template-columns: minmax(0, 2.2fr) 0.7fr 0.7fr 1fr;
  gap: 8px;
  align-items: center;
  font-size: 12.5px;
}

.magicflow-reseedpanel__head {
  opacity: 0.6;
  font-weight: 600;
  border-bottom: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.6));
  padding-bottom: 4px;
}

.magicflow-reseedpanel__line {
  padding: 3px 0;
}

.magicflow-reseedpanel__line em {
  font-style: normal;
  opacity: 0.55;
}

.magicflow-signin-hero {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(var(--v-theme-primary), 0.13), rgba(var(--v-theme-primary), 0.04));
  border: 1px solid rgba(var(--v-theme-primary), 0.18);
}

.magicflow-signin-hero__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  inline-size: 34px;
  block-size: 34px;
  flex: 0 0 auto;
  border-radius: 9px;
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
}

.magicflow-signin-hero__body {
  flex: 1 1 auto;
  min-inline-size: 0;
  display: grid;
  gap: 3px;
}

.magicflow-signin-hero__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.95rem;
  font-weight: 700;
  line-height: 1.3;
}

.magicflow-signin-hero__title > .v-chip {
  margin-inline-start: auto;
}

.magicflow-settings-block .app-responsive-input {
  min-block-size: 0 !important;
  block-size: auto !important;
  padding-block: 0 !important;
  margin-block: 0 !important;
}

.magicflow-signin-hero__desc {
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

.magicflow-signin-hero__desc code {
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-settings-block {
  display: grid;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
}

.magicflow-settings-block__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-switch-list {
  display: grid;
  gap: 2px;
}

.magicflow-field-stack {
  display: grid;
  gap: 14px;
}

.magicflow-field {
  display: grid;
  gap: 4px;
  min-inline-size: 0;
}

.magicflow-field__sub {
  font-size: 0.72rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  overflow-wrap: anywhere;
}

.magicflow-settings-field {
  display: block;
  margin-block: 8px 4px;
}

.magicflow-signin-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-block-start: 8px;
}

.magicflow-settings-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  margin-block-end: 6px;
}

.magicflow-fb-sources {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.magicflow-fb-source {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 4px 10px;
  border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.06);
  border: 1px solid rgba(var(--v-border-color), 0.28);
}

.magicflow-fb-source__idx {
  inline-size: 20px;
  block-size: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 0.72rem;
  font-weight: 600;
  color: rgb(var(--v-theme-on-primary));
  background: rgba(var(--v-theme-primary), 0.85);
  flex: 0 0 auto;
}

.magicflow-fb-source__name {
  flex: 1 1 auto;
  min-inline-size: 0;
  font-size: 0.85rem;
  overflow-wrap: anywhere;
}

.magicflow-fb-source-add {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  margin-block-start: 8px;
}

.magicflow-fb-divider {
  margin-block: 4px;
}

.magicflow-fb-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.magicflow-fb-running {
  font-size: 0.78rem;
  color: rgb(var(--v-theme-primary));
}

.magicflow-fb-report {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.05);
  font-size: 0.8rem;
  line-height: 1.6;
}

.magicflow-fb-report__line {
  overflow-wrap: anywhere;
}

.magicflow-fb-report__details summary {
  cursor: pointer;
  color: rgba(var(--v-theme-primary), 1);
}

.magicflow-fb-report__list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: grid;
  gap: 6px;
  max-block-size: 16rem;
  overflow-y: auto;
}

.magicflow-fb-report__list li {
  display: grid;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  overflow-wrap: anywhere;
}

.magicflow-fb-report__meta {
  font-size: 0.74rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-iyuu-token {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.magicflow-iyuu-sites {
  display: grid;
  gap: 10px;
}

.magicflow-iyuu-sites__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
}

.magicflow-iyuu-row {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.magicflow-iyuu-row__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-inline-size: 0;
}

.magicflow-iyuu-row__name {
  font-weight: 600;
  font-size: 0.85rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.magicflow-iyuu-row__fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.7fr);
  gap: 8px;
}

@media (max-width: 480px) {
.magicflow-iyuu-row__fields {
    grid-template-columns: minmax(0, 1fr);
  
}
}

.magicflow-settings-dialog__footer {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px 14px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.magicflow-settings-hint--warn {
  background: rgba(var(--v-theme-warning), 0.10);
  border-inline-start: 3px solid rgb(var(--v-theme-warning));
  padding: 8px 10px;
  border-radius: 8px;
}

.magicflow-live-alerts {
  display: grid;
  gap: 6px;
  margin-block-start: 12px;
}

.magicflow-live-alerts__head {
  font-size: 0.78rem;
  font-weight: 600;
  opacity: 0.8;
}

.magicflow-live-alert {
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.78rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
  border-inline-start: 3px solid transparent;
}

.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

@media (max-width: 699px) {
/* 设置面板：单列字段、收紧留白 */
  .magicflow-settings-grid,
  .magicflow-settings-switches {
    grid-template-columns: 1fr;
  
}

/* 设置面板：窄屏收缩 tab，尽量一排放下 */
  .magicflow-settings-tab {
    padding-inline: 6px;
    min-width: auto !important;
    font-size: 12px;
    text-transform: none;
  
}

.magicflow-settings-dialog {
    block-size: min(90vh, 38rem);
    max-block-size: 94vh;
  
}

.magicflow-settings-form {
    padding: 12px 14px 10px;
  
}

.magicflow-settings-dialog__footer {
    padding: 10px 14px 12px;
  
}
}

.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}

.magicflow-settings-nav { display: none; }

.magicflow-settings-nav__item {
  display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px 6px;
  border-radius: 14px; background: rgba(var(--v-theme-surface), 0.9); border: 1px solid rgba(var(--v-border-color), 0.16);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); font: inherit; font-size: 12px; cursor: pointer;
}

.magicflow-settings-nav__item.is-active { color: rgb(var(--v-theme-primary)); border-color: rgba(var(--v-theme-primary), 0.5); background: rgba(var(--v-theme-primary), 0.16); }

@media (max-width: 959px) {
.magicflow-settings-dialog__tabs {
 display: none; 
}

/* ★ 手机端设置：分类「目录页」（2 列网格，恢复 3.33.0 版式）。
     点分类 = 跳转到该分类的「表单页」——目录不再和表单挤在同一屏，正文拿回整屏高度。 */
  .magicflow-settings-nav {
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px; padding: 12px 16px 18px; overflow: visible;
  
}

.magicflow-settings-nav__item {
    padding: 18px 10px; font-size: 12.5px;
  
}

.magicflow-settings-nav__item.is-active {
 background: rgba(var(--v-theme-primary), 0.22); 
}
}

@media (max-width: 959px) {
.magicflow-settings-dialog .magicflow-settings-grid {
 grid-template-columns: minmax(0, 1fr); 
}

.magicflow-settings-dialog .magicflow-settings-switches {
 grid-template-columns: minmax(0, 1fr); 
}
}
@media (max-width: 520px) {
/* ★ 站点规则：5 列在 360~400px 上仍会挤，切成三行卡片式
     —— 第一行「站点 + 探测」，第二行「H&R 状态 + 标有/标无」，
     第三行「达标小时 + 完成度」各占一半（旧版两个框各只有 72px，label 放不下）。 */
  .magicflow-rules-row--head {
    display: none;
  }

.magicflow-rules-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
    grid-template-areas:
      "name  name  ops"
      "hr    hr    hr"
      "hours ratio ratio";
    gap: 0.35rem 0.5rem;
    padding: 0.45rem 0.5rem;
    border: 1px solid rgba(var(--v-border-color), 0.14);
    border-radius: 8px;
  }

.magicflow-rules-row:nth-child(even) {
    background: transparent;
  }

.magicflow-rules-row__hr {
    align-self: center;
  }
}


/* ★ 19.16.25 桌面设置页目录：宽屏改左侧 4 组分组导航 + 右侧表单（沿用手机端 MF_SETTINGS_GROUPS）。
   手机（<=959px）完全不动：仍走目录页/表单页两段式 + 三列紧凑格。
   桌面把 VDialog 加宽到 62rem，nav 竖排左栏、body 右栏、footer 跨两列；VTabs 在宽屏隐藏。 */
@media (min-width: 960px) {
  .magicflow-settings-dialog {
    display: grid;
    grid-template-columns: 13.25rem minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr) auto;
    grid-template-areas:
      "hd hd"
      "nv bd"
      "ft ft";
  }
  .magicflow-settings-dialog__head { grid-area: hd; }
  .magicflow-settings-dialog__footer { grid-area: ft; }
  .magicflow-settings-dialog__tabs { display: none; }
  .magicflow-settings-dialog > .v-divider { display: none; }

  .magicflow-settings-nav {
    grid-area: nv;
    display: flex;
    flex-direction: column;
    gap: 0;
    padding: 12px 8px 16px;
    overflow-y: auto;
    overscroll-behavior: contain;
    border-inline-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    background: rgba(var(--v-theme-surface), 0.55);
  }
  .magicflow-settings-nav__group {
    display: block;
    margin: 14px 8px 6px;
    color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .magicflow-settings-nav__group:first-child { margin-top: 2px; }
  .magicflow-settings-nav__group::after { display: none; }
  .magicflow-settings-nav__grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 2px;
  }
  .magicflow-settings-nav__item {
    position: relative;
    flex-direction: row;
    justify-content: flex-start;
    gap: 9px;
    padding: 8px 9px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: transparent;
    font-size: 0.8rem;
    line-height: 1.3;
    text-align: start;
  }
  .magicflow-settings-nav__item .v-icon { font-size: 17px; }
  .magicflow-settings-nav__item:hover { background: rgba(var(--v-theme-primary), 0.07); }
  .magicflow-settings-nav__item.is-active {
    color: rgb(var(--v-theme-primary));
    border-color: transparent;
    background: rgba(var(--v-theme-primary), 0.14);
    box-shadow: inset 2px 0 0 rgb(var(--v-theme-primary));
  }
  .magicflow-settings-nav__item.is-new {
    border-color: transparent;
    background: transparent;
  }
  .magicflow-settings-nav__new {
    top: 50%;
    right: 7px;
    transform: translateY(-50%);
  }
  .magicflow-settings-dialog__body {
    grid-area: bd;
  }
}

</style>
