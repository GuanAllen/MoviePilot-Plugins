<script setup>
// MagicFlow · 设置弹窗（多标签）——P4 自 views/magicflow/index.vue **纯搬家**。
// props 下 / emit 上：子组件不直接改父状态；开关与设置项走 defineModel / emit。
// 复用 composable 纯函数 → module 级具名导出 import（单一真值源）。
import { MF_SETTINGS_TABS, TILE_OPTIONS, ratingSourceItems } from '../../constants'
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
  'add-sort-rule', 'remove-sort-rule', 'preview-tag-migrate', 'apply-tag-migrate', 'test-cloud',
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
  rulesLoading: { type: Boolean, default: false },
  rulesProbing: { type: Boolean, default: false },
  reseedState: { type: Object, default: null },
  reseedRunning: { type: Boolean, default: false },
  reseedSiteOptions: { type: Array, default: () => [] },
  claimSiteOptions: { type: Array, default: () => [] },
  siteSelectItems: { type: Array, default: () => [] },
  siteLiveAlerts: { type: Array, default: () => [] },
  tagInfo: { type: Object, default: null },
  tagMigratePlan: { type: Object, default: null },
  tagMigrating: { type: Boolean, default: false },
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
    <VDialog v-model="settingsDialog" max-width="40rem" :fullscreen="isNarrow">
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
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="settingsDialog = false" />
        </header>

        <div v-if="!isNarrow || settingsPane === 'dir'" class="magicflow-settings-nav" :ref="setNavEl">
          <button
            v-for="t in MF_SETTINGS_TABS"
            :key="t.key"
            type="button"
            class="magicflow-settings-nav__item"
            :class="{ 'is-active': settingsTab === t.key }"
            @click="emit('open-tab', t.key)"
          >
            <VIcon :icon="t.icon" size="18" />
            <span>{{ t.label }}</span>
          </button>
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
        </VTabs>
        <VDivider v-if="!isNarrow || settingsPane === 'form'" />

        <div v-if="!isNarrow || settingsPane === 'form'" class="magicflow-settings-dialog__body">
          <div v-if="settingsTab === 'general'" class="magicflow-settings-form">
            <VSwitch v-model="settingsDraft.enabled" label="启用插件（总开关）" color="primary" hide-details inset />
            <VSwitch
              v-model="settingsDraft.show_sidebar_nav"
              label="显示侧栏入口"
              color="primary"
              hide-details
              inset
            />
            <VTextField
              v-model.number="settingsDraft.request_interval"
              type="number"
              min="0"
              step="0.5"
              label="站点请求间隔（秒）"
              hint="站点翻页请求之间的最小间隔，0 = 不限速；对强流控站点可适当加大"
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
            <p class="magicflow-settings-hint">
              任务流量：按「在跑的任务类型」自动设 qB <strong>全局上传限速</strong>（只限上传，不动下载）。有刷流任务时用刷流档，只有魔力任务时用魔力档；两者同时在跑取刷流档；一个启用的任务都没有则清除限速。
            </p>
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
                hint="我们管控的魔力 / 推荐 / 跨站种：单种限速，默认 200；不在管控下的种不限速；0 = 全不限"
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
            <VSwitch v-model="settingsDraft.debug_log" label="调试日志" color="primary" hide-details inset />
            <VSwitch v-model="settingsDraft.compact_mode" label="紧凑模式" color="primary" hide-details inset />
            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-view-grid-outline" size="16" /> 顶栏功能磁贴</div>
              <p class="magicflow-field__sub">
                关掉的磁贴不再在顶栏 / 手机「功能」里显示入口。<strong>只影响入口显示</strong>：
                功能本身在各自的设置页里单独开关，这里不动任何功能逻辑。
              </p>
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
              <p class="magicflow-field__sub">
                未下完 + 长时间 0 速，且<strong>欠 H&amp;R 或手动保留</strong>的种 → 去<strong>无 H&amp;R 的他站</strong>下同一 Release 补齐（补完 recheck 认文件）。
                独立页面在顶栏「补源」按钮，这里只调参数。
              </p>
              <div class="magicflow-settings-grid">
                <VTextField
                  v-model.number="settingsDraft.rescue_stall_hours"
                  type="number"
                  min="0"
                  max="720"
                  step="1"
                  label="停滞阈值（小时）"
                  hint="0 速持续超过该时长才纳入补源（默认 6；越小越灵敏）"
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
            <p class="magicflow-settings-hint magicflow-settings-hint--warn">
              以下为 qBittorrent 全局参数，将直接写入下载器，会影响所有使用该下载器的插件。
            </p>
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
            <VSwitch
              v-model="downloaderPrefsDraft.queueing_enabled"
              label="启用队列限制（活动数上限生效的前提）"
              color="primary"
              hide-details
              inset
            />

            <VDivider class="my-3" />
            <p class="magicflow-settings-hint">
              qBittorrent 全局目录，写入后影响所有使用该下载器的插件。
            </p>
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

            <VDivider class="my-2" />
            <p class="magicflow-settings-hint">
              任务保存目录：仅对魔流生效，不影响下载器全局设置。
            </p>
            <VTextField
              v-model="defaultsDraft.save_path"
              label="任务保存目录"
              placeholder="如 /vol3/1000/media/magicflow"
              hint="新建任务时自动预填此目录（不影响已有任务，任务内仍可单独修改）"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />
          </div>

          <div v-else-if="settingsTab === 'iyuu'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              IYUU 云端辅种为<strong>可选增强</strong>：填写 Token 后，复用/刷流会优先用 IYUU 云端匹配<strong>他站同资源</strong>；
              下方站点密钥可手填（留空则自动尝试用 MoviePilot 已存的 apikey / cookie 取链）。
              <strong>不填 Token 则完全不启用</strong>，一切照旧走内置跨站特征码方案。
            </p>
            <div class="magicflow-iyuu-token">
              <VTextField
                v-model="settingsDraft.iyuu_token"
                label="IYUU 云端 Token"
                placeholder="留空 = 不启用 IYUU 辅种"
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
                :disabled="!settingsDraft.iyuu_token"
                @click="emit('test-iyuu')"
              >测试</VBtn>
              <VBtn
                v-if="settingsDraft.iyuu_token"
                variant="text"
                color="error"
                size="small"
                prepend-icon="mdi-close-circle-outline"
                @click="emit('clear-iyuu')"
              >清空</VBtn>
            </div>
            <div class="magicflow-iyuu-sites">
              <div class="magicflow-iyuu-sites__head">
                <span>站点密钥（按 MoviePilot 已配置站点生成）</span>
                <VChip
                  v-if="iyuuStatus"
                  size="x-small"
                  variant="tonal"
                  :color="iyuuStatus.enabled ? 'success' : 'grey'"
                >{{ iyuuStatus.enabled ? '已启用' : '未启用' }}</VChip>
              </div>
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
                <div class="magicflow-iyuu-row__fields">
                  <VTextField
                    v-model="row.passkey"
                    label="passkey"
                    placeholder="留空 = 自动获取"
                    variant="outlined"
                    density="compact"
                    hide-details
                    autocomplete="off"
                  />
                  <VTextField
                    v-model="row.uid"
                    label="uid（可选）"
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
                  variant="outlined"
                  density="compact"
                  hide-details
                  autocomplete="off"
                />
              </div>
            </div>
          </div>

          <div v-else-if="settingsTab === 'reseed'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              <strong>全站辅种</strong>（本机驱动）：本机<strong>已有文件</strong>的资源 → 去各站找<strong>同一 Release</strong> 的种子挂上去落户。
              <strong>零下载</strong>：暂停加入 → recheck 校验 → <strong>通过才做种</strong>，不通过自动撤销。
              方向与「跨站取种」相反（那是本机没有、去他站免费下回来）。
            </p>
            <p class="magicflow-settings-hint magicflow-settings-hint--warn">
              ⚠️ 挂种要拼目标站下载链（IYUU 站点表模板 + passkey / API 直链）。passkey 能自动抓；抓不到的站会记「缺料」跳过。
              每站有每日上限，建议先<strong>干跑</strong>看清能挂多少再关干跑。
            </p>

            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.reseed_enabled" label="启用全站辅种" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.reseed_dry" label="干跑（只算不挂）" color="primary" hide-details inset :disabled="!settingsDraft.reseed_enabled" />
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
            <p class="magicflow-settings-hint">
              <strong>认领</strong>：把「我们正在做种」的种子在<strong>站点侧认领</strong>掉，换取站点给的权益
              （CARPT：达标种子魔力奖励 = 正常值 <strong>×2</strong>）。它是「保种增值」动作，与刷流拿种解耦。
            </p>
            <p class="magicflow-settings-hint magicflow-settings-hint--warn">
              ⚠️ 认领是<strong>不可逆的对外写操作</strong>：站点侧不达标会<strong>扣魔力</strong>，主动放弃扣得更多。
              因此默认<strong>关闭</strong>且默认<strong>干跑</strong>；认领后的种子会进<strong>硬保护、永不自动删除</strong>。
            </p>

            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.claim_enabled" label="启用认领" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.claim_dry" label="干跑（只列不写）" color="primary" hide-details inset :disabled="!settingsDraft.claim_enabled" />
              <VSwitch v-model="settingsDraft.claim_exclude_zero_bonus" label="零魔种不认领" color="primary" hide-details inset />
            </div>

            <div class="magicflow-settings-block">
              <div class="magicflow-settings-block__head"><VIcon icon="mdi-web" size="16" /> 站点白名单（留空 = 全部支持的站）</div>
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
              <span class="magicflow-field__sub">已选 {{ (settingsDraft.claim_sites || []).length }} 个 · 目前支持的站：{{ claimSiteOptions.join(' / ') || '（尚未探测，打开认领页后可见）' }}</span>
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
              <p class="magicflow-field__sub">先「扫描（干跑）」看能认领哪些，再逐条二次确认；对不熟悉的站建议长期保持干跑。</p>
            </div>
          </div>

          <div v-else-if="settingsTab === 'template'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              仅用于新建任务时预填，不影响已有任务。
            </p>
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
              <VTextField v-model.number="defaultsDraft.max_add_per_run" type="number" min="1" label="单轮最多新增" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.max_download_concurrent" type="number" min="1" label="同时下载数上限" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.top_n" type="number" min="1" label="候选 TopN" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.browse_pages" type="number" min="1" label="每轮翻页数" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.seen_cooldown_hours" type="number" min="0" label="候选去重冷却（小时）" variant="outlined" density="comfortable" hide-details />
              <VTextField v-model.number="defaultsDraft.brush_seed_days" type="number" min="0" max="365" label="刷流保种天数（0=按无上传）" variant="outlined" density="comfortable" hide-details />
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

          <div v-else-if="settingsTab === 'exam'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              把各站<strong>新手考核</strong>进度抓出来（上传/下载增量、平均做种时间、魔力/做种积分增量），
              并支持<strong>一键起任务</strong>去补未通过项。
              数据来源就是各站首页 <code>index.php</code> 的考核块 —— 魔流本来就抓这个页面拿实时数据，
              所以<strong>不额外消耗站点访问次数（PV）</strong>。
            </p>
            <p class="magicflow-settings-hint">
              <strong>已通过的考核默认不显示</strong>（过掉的就不占地方了）；想看全部就打开下面的「显示已通过」。
              考不过的站会算好缺口：上传差多少 → 刷流任务；魔力/积分差多少 → 魔力任务；平均做种时间不够 → 保持做种 + 多辅种（不用建任务）。
              下载类考核项（下载增量）<strong>只做提示、不建任务</strong>。
            </p>
            <p class="magicflow-settings-hint">
              魔流不做下载业务：<strong>不会创建任何下载任务</strong>，也不会为凑下载量去下非免费种。
              缺的下载量需要你自己安排；已通过/未通过都不会影响现有做种。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.exam_enabled" label="启用「新手考核」（关闭则不抓取、不解析、不显示）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.exam_include_pass" label="显示「已通过」的考核（默认只显示未通过的）" color="primary" hide-details inset />
            </div>
            <div class="magicflow-settings-field">
              <VSelect
                v-model="settingsDraft.exam_sites"
                :items="siteSelectItems"
                label="考核站点（不选 = 全部已配置 Cookie 的站点）"
                multiple
                chips
                closable-chips
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <p class="magicflow-settings-hint">选多少有多少：只盯你关心的站，不选就是全都盯。</p>
            </div>
            <p v-if="!settingsDraft.exam_enabled" class="magicflow-settings-hint magicflow-settings-hint--warn">
              当前处于<strong>关闭</strong>状态：不会去抓考核，也不会做任何额外请求。
            </p>
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
              <p v-if="!settingsDraft.signin_enabled" class="magicflow-field__sub">
                当前为关闭状态：不会签到、不会模拟登录，也不发任何请求。
              </p>
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
              <span class="magicflow-field__sub">签到结果与近 7 天记录都在报表页</span>
            </div>
          </div>

          <div v-else-if="settingsTab === 'live'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              MoviePilot 的站点账号数据靠它自己的「站点数据刷新」任务写库（默认 <strong>6 小时</strong>一轮），
              对展示够用，但魔流是拿它<strong>做决策</strong>的（任务目标达标 / 救号分享率 / 兑换提醒）—— 滞后 6 小时就是真偏差。
              启用后魔流<strong>直连站点用户栏页</strong>拿实时值（上传 / 下载 / 分享率 / 魔力 / 做种数），
              并监控<strong>「下载量在涨」</strong>——免费种不吃下载，下载量增长说明吃到促销尾巴了。
              站点级缓存 + 单飞，抓不到自动回退 MP 数据。
            </p>
            <p class="magicflow-settings-hint magicflow-settings-hint--warn">
              ⚠️ 多数站点有<strong>每日访问次数上限</strong>（实测 PTT：用户等级 300 PV/天，含刷流浏览）。
              采样太频会把配额打光 → 站点当天拒绝访问（连刷流也取不到种）。命中后魔流会自动<strong>停抓到次日凌晨</strong>并告警，
              但配额是共享的：<strong>建议按站点把采样周期放长</strong>（比如 15–30 分钟），给选种浏览留余量。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.live_enabled" label="启用站点实时数据 + 流量监控" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_notify" label="命中告警时推送通知" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_auto_stop" label="同时把该站「运行中」任务切「做种中」（停调度、不删种）" color="primary" hide-details inset />
            </div>

            <VDivider class="my-3" />
            <p class="magicflow-settings-hint">
              <strong>流量兜底</strong>：下载中被判「非免费」就干掉，避免白烧下载量。
              三处都会核对：<em>任务内</em>回种子详情页核对（开关在任务「高级」里，受本总开关约束）、
              <em>全局</em>用站点「正在下载」列表核对、<em>取种期间</em>核对来源站。共用下面这个总开关。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.promo_guard" label="启用流量兜底（关掉 = 下面三项都只告警、不动手）" color="primary" hide-details inset />
            </div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.live_kill_unfree" :disabled="!settingsDraft.promo_guard" label="全局：下载量异常增长 → 站点「正在下载」列表里非免费的种，从下载器干掉" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.live_kill_delete_files" :disabled="!settingsDraft.promo_guard || !settingsDraft.live_kill_unfree" label="干掉时连文件一起删（只动「下载中」且名称+体积对得上的种）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.crossseed_guard" :disabled="!settingsDraft.promo_guard" label="取种期间：核对来源站免费状态与下载量增量，判错就删种并拉黑该站（强烈建议）" color="primary" hide-details inset />
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
                hint="来源站下载增量 > 目标体积 × 该值 即判定「不免费」，默认 5%"
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
                hint="同一来源站两次核对的间隔，默认 15 分钟（各花 1 次站点请求）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
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
            <div v-if="siteLiveAlerts.length" class="magicflow-live-alerts">
              <div class="magicflow-live-alerts__head">当前「{{ selectedTask?.name }}」站点告警</div>
              <div v-for="(alert, idx) in siteLiveAlerts" :key="`live-cfg-${idx}`" class="magicflow-live-alert" :class="`magicflow-live-alert--${alert.level || 'info'}`">
                {{ alert.text }}
              </div>
            </div>
          </div>
          <div v-else-if="settingsTab === 'recommend'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              刷流时顺带甄别「值得收藏 / 观看」的资源：命中的种子会打上推荐标签（受「媒体资产价值闸门」保护、不会被当临时种删掉）并通知你确认；错过确认窗口（过期 / 磁盘不足）则按临时种回收。
            </p>
            <VSwitch v-model="settingsDraft.recommend_enabled" label="启用推荐甄别" color="primary" hide-details inset />
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.recommend_min_rating"
                type="number"
                min="0"
                max="10"
                step="0.1"
                label="评分门槛（高于）"
                hint="评分高于该值才推荐，默认 7.5（评分源见左侧「评分来源」）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.recommend_expire_days"
                type="number"
                min="0"
                step="1"
                label="推荐过期天数"
                hint="超过该天数仍未确认则视为过期（0 = 不过期）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.recommend_temp_ttl_days"
                type="number"
                min="0"
                step="1"
                label="临时种 TTL（天）"
                hint="未入选推荐的普通刷流临时种，超过该天数回收"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.recommend_disk_min_free_gb"
                type="number"
                min="0"
                step="1"
                label="磁盘余量下限（GB）"
                hint="剩余空间低于该值时，推荐立即视为过期"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model="settingsDraft.recommend_douban_service_url"
                label="豆瓣服务地址"
                placeholder="http://magicflow-douban:18789"
                hint="独立服务 magicflow-douban 的地址，留空用默认；本地查询 <1ms，不受豆瓣限流影响"
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
              />
            </div>
            <div class="magicflow-settings-grid">
              <VSelect
                v-model="settingsDraft.recommend_rating_source"
                :items="ratingSourceItems"
                item-title="title"
                item-value="value"
                label="评分来源"
                hint="默认只用 TMDB；豆瓣优先走本地服务 magicflow-douban（不再直连豆瓣）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.recommend_require_chart" label="榜单 / 热映 / 订阅命中也算达标（与评分为「或」关系）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.recommend_auto_import" label="确认后自动整理入库" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.recommend_notify" label="发现推荐时通知" color="primary" hide-details inset />
            </div>
          </div>

          <div v-else-if="settingsTab === 'rules'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              <strong>全站 H&amp;R 的唯一入口</strong>：H&amp;R 有无 / 最短保种时长 / 做种上限都在这一页
              （跨站取种的「来源份」在兄弟站同样背 H&amp;R 义务，例：学校 BTSchool 要挂种 10 小时）。
              优先级：<strong>手填 &gt; 页面探测 &gt; 内置 &gt; 全局默认</strong>；
              探测遵循「宁保守勿乐观」—— 抓不到就保持原值，绝不假设「没有 H&amp;R」。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.rules_auto_refresh" label="每周自动逐站探测规则并入库" color="primary" hide-details inset />
            </div>

            <VDivider class="my-3" />
            <p class="magicflow-settings-hint">
              <strong>H&amp;R 来源</strong>：只认<strong>收件箱「欢迎短讯」里给出的规则地址</strong>（🔗 已存下，可点开）；
              页面里顺带抓到的 H&amp;R 不算数。默认时长给<strong>表里未收录</strong>的站点兜底；
              每站的时长直接改上表的「<strong>保种(h)</strong>」列（手填覆盖，优先级最高）。
            </p>
            <div class="magicflow-settings-grid">
              <VTextField
                v-model.number="settingsDraft.crossseed_seed_hours_default"
                type="number"
                min="0"
                max="720"
                step="1"
                label="默认最短保种时长（小时）"
                hint="未收录站点的 H&R 保种时长，默认 24h"
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
                hint="实际做种需 ≥ 站点要求 + 该值才判结清（默认 2，0 = 不留垫）"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
              <VTextField
                v-model.number="settingsDraft.hr_deadline_warn_hours"
                type="number"
                step="1"
                min="0"
                label="H&amp;R 临近到期预警（小时）"
                hint="距站点考核窗口到期低于该值且未达标 → 预警（默认 48）"
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
                hint="下载进度 ≥ 该值才算「完成」、才计 H&amp;R 义务（默认 0.999 = 下满）。某站不同 → 改下表该站的「完成度」列"
                persistent-hint
                variant="outlined"
                density="comfortable"
              />
            </div>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.crossseed_guard_keep_seed" label="来源份 H&R 保护（保种期内任何任务不得删/改标签）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.crossseed_reclaim" label="H&R 期满后回收来源份（只删种子不删文件）" color="warning" hide-details inset />
            </div>
            <div class="magicflow-rules-actions">
              <VBtn size="small" color="primary" variant="tonal" :loading="rulesProbing" @click="emit('probe-rules')">
                <VIcon start size="small">mdi-download-network-outline</VIcon>逐站拉取（探测页面）
              </VBtn>
              <VBtn size="small" variant="text" :disabled="rulesLoading" @click="emit('refresh-rules')">按 MP 配置补全</VBtn>
              <VSpacer />
              <span class="magicflow-settings-hint">共 {{ siteRules.length }} 条</span>
            </div>
            <p v-if="rulesProbing" class="magicflow-settings-hint">正在逐站抓取规则页（每站 1~2 个请求，站间随机歇 1.5~3.5 秒）…</p>
            <div class="magicflow-rules-table">
              <div class="magicflow-rules-row magicflow-rules-row--head">
                <span>站点</span><span>H&amp;R</span><span>保种(h)</span><span>完成度</span><span>做种上限</span><span>来源</span><span>操作</span>
              </div>
              <div v-for="row in siteRules" :key="row.domain" class="magicflow-rules-row">
                <span class="magicflow-rules-row__name" :title="row.domain">
                  {{ row.site_name || row.domain }}
                  <em v-if="!row.in_library">未入库</em>
                  <em v-if="row.exam_avg_hours" :title="row.exam_evidence || '站点考核的平均做种要求（不是 H&R）'">考核均值{{ row.exam_avg_hours }}h</em>
                  <em v-if="row.free_over_gb" title="站点促销规则：达到该体积自动免费（列表页可能不标促销，插件按规则补判）">&gt;{{ row.free_over_gb }}G免</em>
                  <em v-if="row.free_original" title="站点促销规则：原盘自动免费">原盘免</em>
                  <em v-if="row.free_ep1" title="站点促销规则：每季第一集自动免费">首集免</em>
                </span>
                <span class="magicflow-rules-row__hr">
                  <VChip v-if="row.hr === true" size="x-small" color="error" variant="tonal">有</VChip>
                  <VChip v-else-if="row.hr === false" size="x-small" color="success" variant="tonal">无</VChip>
                  <VChip v-else size="x-small" variant="tonal">未知</VChip>
                  <VBtn v-if="row.hr === false" size="x-small" variant="text" :disabled="rulesProbing" title="恢复为探测/内置判定" @click="emit('set-rule-hr', row, 'unknown')">恢复</VBtn>
                  <template v-else>
                    <VBtn size="x-small" variant="text" :disabled="rulesProbing" title="该站有 H&R：手动确认为「有」并按当前时长保护" @click="emit('set-rule-hr', row, '1')">标有</VBtn>
                    <VBtn size="x-small" variant="text" :disabled="rulesProbing" title="该站没有 H&R：直接标无，不做保种保护" @click="emit('set-rule-hr', row, '0')">标无</VBtn>
                  </template>
                </span>
                <span>
                  <VTextField
                    :model-value="row.effective_hours"
                    type="number"
                    min="0"
                    max="720"
                    step="1"
                    density="compact"
                    variant="outlined"
                    hide-details
                    style="max-width: 6.5rem"
                    @change="emit('set-rule-hours', row, $event.target.value)"
                  />
                </span>
                <span>
                  <VTextField
                    :model-value="row.complete_ratio"
                    type="number"
                    min="0"
                    max="1"
                    step="0.001"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="跟全局"
                    style="max-width: 6rem"
                    :title="row.complete_ratio == null ? '未覆盖 → 跟设置里的全局「H&amp;R 完成度阈值」' : '站点级覆盖（下载进度 ≥ 该值才计 H&amp;R）'"
                    @change="emit('set-rule-ratio', row, $event.target.value)"
                  />
                </span>
                <span>{{ row.seed_cap || '-' }}</span>
                <span class="magicflow-rules-row__src" :title="row.evidence || ''">
                  {{ ruleSourceText(row) }}
                  <em v-if="row.seed_need_hours" :title="'规则窗口 ' + (row.seed_window_hours || row.seed_hours || 0) + 'h，达到线 ' + row.seed_need_hours + 'h；保护期取窗口(保守)'">需{{ row.seed_need_hours }}h</em>
                  <em v-if="row.seed_hours_seen != null">(看到{{ row.seed_hours_seen }}h)</em>
                </span>
                <span>
                  <VBtn
                    v-if="row.rule_url"
                    size="x-small"
                    variant="text"
                    icon
                    :href="String(row.rule_url).split(/\s+/)[0]"
                    target="_blank"
                    rel="noopener"
                    :title="'规则地址（来自收件箱欢迎短讯，已存下）：' + row.rule_url"
                  ><VIcon size="x-small">mdi-link-variant</VIcon></VBtn>
                  <VBtn size="x-small" variant="text" :disabled="rulesProbing" @click="emit('probe-rules', row.domain)">探测</VBtn>
                </span>
              </div>
            </div>
            <p class="magicflow-settings-hint">
              「保种(h)」直接改 = 写入手填覆盖（最高优先级：手填 &gt; 探测 &gt; 内置 &gt; 全局默认）。
              「<strong>完成度</strong>」= 该站的 H&amp;R 完成度阈值：<strong>留空 = 跟全局默认</strong>；
              正常站用全局 0.999（下满才算），某站若说「下载中即计 H&amp;R」→ 在该站填 0.2 之类。
            </p>
          </div>

          <div v-else-if="settingsTab === 'tags'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              标签模型：种子状态 = 标签 <code>魔流-&lt;站点&gt;-&lt;状态&gt;[-&lt;子类&gt;]</code>，
              状态有 <strong>刷流 / 魔力 / 静默(新·资源·普通) / 推荐</strong>；
              另有<strong>状态账本</strong>做真值源（标签被改坏也能自愈），以及
              <strong>文件组账本</strong>按多站引用计数——<em>摘成员只删种，最后一个成员才连文件清</em>。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.tag_model_enabled" label="启用标签模型（状态账本 + 魔流-站点-状态 标签）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.show_qb_tags" label="往 qB 写标签（关=纯账本模式）" color="primary" hide-details inset />
            </div>
            <div class="magicflow-settings-grid">
              <VTextField v-model.number="settingsDraft.tag_silent_new_timeout_hours" type="number" min="0" step="1"
                label="「静默-新」超时(小时)" hint="超过该时长未分拣自动归「静默-普通」，0 = 不超时"
                persistent-hint variant="outlined" density="comfortable" />
            </div>

            <VDivider class="my-3" />
            <p class="magicflow-settings-hint">
              <strong>静默分拣规则</strong>：<code>静默-新</code> 命中任一启用规则 → 进 <code>静默-资源</code>，
              否则进 <code>静默-普通</code>（受站点魔力产出考核）。
            </p>
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
                  <VBtn size="x-small" variant="text" color="error" @click="emit('remove-sort-rule', i)">删除</VBtn>
                </span>
              </div>
            </div>
            <div class="magicflow-sort-rules__add">
              <VSelect v-model="newRuleType" :items="sortRuleTypeOptions" item-title="text" item-value="value"
                density="compact" variant="outlined" hide-details style="max-width: 200px" label="新增规则" />
              <VBtn size="small" variant="tonal" color="primary" @click="emit('add-sort-rule')">加上</VBtn>
            </div>

            <VDivider class="my-3" />
            <div class="magicflow-rules-actions">
              <VBtn size="small" variant="tonal" color="primary" :loading="tagMigrating" @click="emit('preview-tag-migrate')">
                <VIcon start size="small">mdi-tag-multiple</VIcon>迁移预演（老标签 → 新命名）
              </VBtn>
              <VBtn v-if="tagMigratePlan" size="small" color="error" variant="tonal" :loading="tagMigrating" @click="emit('apply-tag-migrate')">
                执行迁移（{{ tagMigratePlan.total }} 个）
              </VBtn>
              <VSpacer />
              <span class="magicflow-settings-hint">账本 {{ tagInfo?.ledger_count ?? 0 }} 条 · 文件组 {{ tagInfo?.groups?.groups ?? 0 }}（多站 {{ tagInfo?.groups?.multi_site_groups ?? 0 }}）</span>
            </div>
            <div v-if="tagMigratePlan" class="magicflow-tag-migrate">
              <p class="magicflow-settings-hint">
                待迁移 <strong>{{ tagMigratePlan.total }}</strong> 个：
                <em v-for="(n, k) in tagMigratePlan.by_state" :key="k">{{ k }} {{ n }} </em>
              </p>
              <div class="magicflow-tag-migrate__samples">
                <div v-for="(row, i) in (tagMigratePlan.samples || [])" :key="i" class="magicflow-tag-migrate__row">
                  <span class="magicflow-tag-migrate__title" :title="row.title">{{ row.title }}</span>
                  <span class="magicflow-tag-migrate__tags">
                    <em>{{ (row.remove || []).join(' ') }}</em> → <strong>{{ row.add }}</strong>
                  </span>
                </div>
              </div>
            </div>
            <p class="magicflow-settings-hint">
              迁移会把任务里手填的 <code>brush_tag</code>（如 <code>魔流-财神</code>）换成状态标签，
              保留 <code>已整理 / 辅种</code> 等外来标签；预演不变更任何东西。
            </p>
          </div>

          <div v-else-if="settingsTab === 'crossseed'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              跨站免费取种：本站<strong>非免费</strong>的候选 → 去<strong>兄弟站免费下</strong>，
              落种由全局任务「<strong>跨站取种</strong>」承接（下载中=在岗）；下载完过 H&amp;R 判定：
              欠 → 交保种，不欠 → 入静默池（摘任务标、留身份）。<strong>回辅由「全站辅种」负责</strong>。
              <br />
              本页只管「<strong>怎么取种</strong>」：
              <strong>流量兜底</strong>（含取种期间核对来源站）已在「<strong>站点监控 → 流量兜底</strong>」统一配置；
              <strong>下完的来源份</strong>会移交「<strong>静默池</strong>」挂 H&amp;R（保种 / 分拣 / 回收由静默池负责）。
            </p>
          </div>

          <div v-else-if="settingsTab === 'fallback'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              TMDB 对<strong>番剧特别篇/前传、国漫、B站特供</strong>常常「根本没有」，离了 TMDB 就没元数据可用。
              这里做<strong>多源识别回退</strong>（按顺序试各来源）→ 给库里缺 NFO 的集补一份<strong>最小 NFO</strong>，
              让播放器 / 飞牛影视能显示名称与集号。<strong>只写 NFO，不动媒体文件，已存在的好 NFO 不覆盖。</strong>
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.fallback_enabled" label="启用元数据兜底" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.fallback_after_import" label="每次整理入库后自动兜底" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.fallback_dry_run" label="演练模式（只报告不写 NFO）" color="primary" hide-details inset />
            </div>

            <div class="magicflow-settings-field">
              <div class="magicflow-settings-label">识别来源顺序（自上而下依次尝试）</div>
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

            <VDivider class="magicflow-fb-divider" />

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

          <div v-else-if="settingsTab === 'cloud'" class="magicflow-settings-form">
            <p class="magicflow-settings-hint">
              <strong>本地当热区，夸克当冷库。</strong>
              把库里的成品大文件上传到 OpenList 的可写存储（夸克 cookie 驱动），
              同一夸克目录会被 OpenList 的 Strm 视图自动生成 <code>.strm</code> 播放指针，
              飞牛影视直接能看 —— <strong>无需改 OpenList 配置、也无需自己写 strm</strong>。
              默认<strong>只上传、不删本地</strong>；删本地与停种必须单独确认。
            </p>
            <div class="magicflow-settings-switches">
              <VSwitch v-model="settingsDraft.cloud_enabled" label="启用云盘归档" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.cloud_dry_run" label="演练模式（只列计划，不真传）" color="primary" hide-details inset />
              <VSwitch v-model="settingsDraft.cloud_notify" label="完成后通知" color="primary" hide-details inset />
            </div>

            <div class="magicflow-settings-field">
              <div class="magicflow-settings-label">OpenList 连接</div>
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
                  hint="留空 = 保留已保存的 Token；Token 不会回显到浏览器"
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
              <p v-if="cloudTestMsg" class="magicflow-settings-hint" :class="cloudTestOk ? 'text-success' : 'text-error'">{{ cloudTestMsg }}</p>
            </div>

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
              hint="{rel} = 相对库根的路径。默认 /quark/movie/{rel}（与本地库同构，影视侧自动对应）"
              persistent-hint
              variant="outlined"
              density="comfortable"
            />

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
              hint="默认已排除下载区/刷流区/蓝光原盘结构；这里可再加"
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
              label="排除标签（做种中的种子不打标上传策略，可留空）"
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

            <VDivider class="magicflow-fb-divider" />

            <div class="magicflow-settings-switches">
              <VSwitch
                v-model="settingsDraft.cloud_delete_local"
                label="归档后删除本地文件（危险：会停种；插件会拒绝自动执行，只做记录）"
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
            <VAlert type="warning" variant="tonal" density="compact">
              安全默认：<strong>不删本地、不停种</strong>。删本地需要逐条上传校验通过后手动确认，绝不会自动执行。
            </VAlert>
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
  gap: 0.5rem;
  margin: 0.75rem 0 0.25rem;
}

.magicflow-rules-table {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
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

.magicflow-tag-migrate {
  margin-top: 0.5rem;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
}

.magicflow-tag-migrate__samples {
  max-height: 26vh;
  overflow-y: auto;
}

.magicflow-tag-migrate__row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 0.5rem;
  font-size: 0.8125rem;
  padding: 0.125rem 0;
}

.magicflow-tag-migrate__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.magicflow-tag-migrate__tags em {
  opacity: var(--mf-op-dim);
  text-decoration: line-through;
}

.magicflow-tag-migrate__tags strong {
  color: rgb(var(--v-theme-primary));
}

.magicflow-rules-row {
  display: grid;
  grid-template-columns: minmax(8rem, 1.6fr) 5rem 7rem 6rem 6rem 6rem 4.5rem;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.magicflow-rules-row:nth-child(even) {
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.magicflow-rules-row--head {
  font-weight: 600;
  opacity: var(--mf-op-mid);
}

.magicflow-rules-row__name {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.magicflow-rules-row__name em {
  font-style: normal;
  font-size: 0.7rem;
  opacity: var(--mf-op-dim);
}

.magicflow-rules-row__src {
  opacity: var(--mf-op-soft);
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
</style>
