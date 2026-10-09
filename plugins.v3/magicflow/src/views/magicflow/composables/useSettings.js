// MagicFlow 前端 · useSettings 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api, error, notify, emit, saving, loadStatus, settingsDraft, isNarrow, loadFallback, loadCloud, testCloud, loadTags, loadReseed（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { nextTick, ref, watch } from 'vue'
import { normalizeDefaults } from '../../../utils'
import { normalizeDownloaderPaths } from '../../../utils'
import { normalizeDownloaderPrefs } from '../../../utils'
import { normalizeIyuuSites } from '../../../utils'
import { normalizeSettings } from '../../../utils'
import { unwrapResponse } from '../../../utils'
import { MF_SETTINGS_TABS } from '../constants'

// ★ P4：纯函数提到 module 级具名导出，供 dialogs/SettingsDialog.vue 复用（单一真值源）。
export function settingsTabLabel(key) {
  return (MF_SETTINGS_TABS.find(t => t.key === key) || {}).label || '插件设置'
}
export function ruleSourceText(row) {
  const src = row?.hours_src
  const base = ({ manual: '手填', welcome: '收件箱规则', probe: '页面探测', builtin: '内置', default: '全局默认' })[src] || src || '-'
  if (src === 'probe' && row?.confidence && row.confidence !== 'high') return `${base}(低可信)`
  if (row?.hr_src === 'retired') return `${base}`
  return base
}

export function useSettings({ api, error, notify, emit, saving, loadStatus, settingsDraft, isNarrow, loadFallback, loadCloud, testCloud, loadTags, loadReseed }) {
  const settingsDialog = ref(false)
  const settingsTab = ref('general')
  const settingsPane = ref('form') // 手机端设置：'dir' = 分类目录页 / 'form' = 分类表单页
  const settingsNavEl = ref(null)
  function scrollSettingsNavToActive() {
    const el = settingsNavEl.value?.querySelector('.magicflow-settings-nav__item.is-active')
    if (el?.scrollIntoView) el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }
  // ★ 手机端设置分类是单行横向胶囊条：让当前分类自动滚到可见位置（否则打开时总停在最左边）
  watch(settingsDialog, v => { if (v) nextTick(() => scrollSettingsNavToActive()) })
  watch(settingsTab, () => nextTick(() => scrollSettingsNavToActive()))
  const downloaderPrefsDraft = ref(normalizeDownloaderPrefs({}))
  const downloaderPrefsRecommended = ref(null)
  const downloaderPrefsLoading = ref(false)
  const downloaderPrefsRaw = ref(null)
  const downloaderPathsDraft = ref(normalizeDownloaderPaths({}))
  const defaultsDraft = ref(normalizeDefaults({}))
  const defaultsLoading = ref(false)
  const iyuuSites = ref([])
  const siteRules = ref([])
  const rulesLoading = ref(false)
  const rulesProbing = ref(false)
  const iyuuLoading = ref(false)
  const iyuuTesting = ref(false)
  const iyuuStatus = ref(null)
  const iyuuShowMore = ref({})
  async function openSettings(tab = '') {
    settingsTab.value = tab || 'general'
    // 手机端：从「设置」按钮进 → 先给分类目录页；从功能格指定分类进 → 直达该分类表单页。
    settingsPane.value = isNarrow.value && !tab ? 'dir' : 'form'
    settingsDialog.value = true
    await Promise.all([loadDownloaderPrefs(), loadDefaults(), loadIyuuSites()])
    loadSettingsTabData()
  }
  function loadSettingsTabData() {
    if (settingsTab.value === 'fallback') loadFallback()
    if (settingsTab.value === 'cloud') loadCloud()
    if (settingsTab.value === 'rules') loadRules()
    if (settingsTab.value === 'tags') loadTags()
    if (settingsTab.value === 'reseed') loadReseed()
  }
  async function openSettingsTab(key) {
    settingsTab.value = key
    settingsPane.value = 'form'
    await Promise.all([loadDownloaderPrefs(), loadDefaults(), loadIyuuSites()])
    loadSettingsTabData()
  }
  function backToSettingsDir() {
    settingsPane.value = 'dir'
  }
  async function loadRules() {
    rulesLoading.value = true
    try {
      const res = await api.settings.rules()
      siteRules.value = res?.data?.rules || []
    } catch (e) {
      siteRules.value = []
    } finally {
      rulesLoading.value = false
    }
  }
  async function probeRules(site) {
    rulesProbing.value = true
    try {
      const q = site ? `&site=${encodeURIComponent(site)}` : ''
      const res = await api.settings.rulesProbe(q)
      if (res?.success === false) throw new Error(res?.message || '探测失败')
      siteRules.value = res?.data?.rules || siteRules.value
      return res
    } finally {
      rulesProbing.value = false
    }
  }
  async function setRuleHr(row, hr) {
    if (!row?.domain) return
    try {
      const res = await api.settings.setRuleHr(row.domain, hr)
      if (res?.success === false) throw new Error(res?.message || '失败')
      siteRules.value = res?.data?.rules || siteRules.value
      await loadRules()
    } catch (e) {
      alert(`标记失败: ${e?.message || e}`)
    }
  }
  async function setRuleHours(row, hours) {
    const dom = row?.domain
    if (!dom) return
    await api.settings.setRuleHours(dom, hours)
    await loadRules()
  }
  async function setRuleRatio(row, ratio) {
    const dom = row?.domain
    if (!dom) return
    const v = String(ratio ?? '').trim()
    await api.settings.setRuleRatio(dom, v)
    await loadRules()
  }
  async function refreshRules() {
    const res = await api.settings.refreshRules()
    siteRules.value = res?.data?.rules || []
  }
  async function loadIyuuSites() {
    iyuuLoading.value = true
    try {
      const data = unwrapResponse(await api.settings.iyuuSites())
      iyuuStatus.value = data || null
      const draftFill = normalizeIyuuSites(settingsDraft.value.iyuu_sites)
      iyuuSites.value = (data?.sites || []).map(row => {
        const domain = String(row.domain || '').toLowerCase()
        const serverFill = normalizeIyuuSites({ d: row.fill || {} }).d || {}
        const fill = draftFill[domain] || serverFill
        return {
          id: row.id,
          name: row.name || row.domain || '',
          domain: row.domain || '',
          iyuu_sid: row.iyuu_sid,
          is_active: row.is_active,
          has_apikey: row.has_apikey,
          has_cookie: row.has_cookie,
          passkey: fill.passkey || '',
          uid: fill.uid || '',
          downhash: fill.downhash || '',
        }
      })
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      iyuuLoading.value = false
    }
  }
  function syncIyuuToDraft() {
    const map = {}
    iyuuSites.value.forEach(row => {
      const domain = String(row.domain || '').toLowerCase()
      if (!domain) return
      const clean = normalizeIyuuSites({ d: { passkey: row.passkey, uid: row.uid, downhash: row.downhash } }).d
      if (clean) map[domain] = clean
    })
    settingsDraft.value.iyuu_sites = map
  }
  async function testIyuu() {
    iyuuTesting.value = true
    try {
      syncIyuuToDraft()
      const data = unwrapResponse(await api.settings.iyuuTest())
      notify(`IYUU Token 有效（账号 ${data?.username || data?.id || '-'}，站点表 ${data?.sites ?? 0} 条）`)
    } catch (err) {
      notify(err?.message || String(err))
    } finally {
      iyuuTesting.value = false
    }
  }
  async function clearIyuuToken() {
    settingsDraft.value.iyuu_token = ''
    settingsDraft.value.iyuu_clear = true
    try {
      await saveIyuu()
    } finally {
      settingsDraft.value.iyuu_clear = false
    }
  }
  async function saveIyuu() {
    saving.value = true
    try {
      syncIyuuToDraft()
      unwrapResponse(await api.settings.saveSettings(normalizeSettings(settingsDraft.value)))
      notify('IYUU 设置已保存')
      await loadStatus()
      await loadIyuuSites()
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      saving.value = false
    }
  }
  async function loadDownloaderPrefs() {
    downloaderPrefsLoading.value = true
    try {
      const data = unwrapResponse(await api.settings.downloaderPrefs())
      if (data && data.available) {
        downloaderPrefsDraft.value = normalizeDownloaderPrefs(data)
        downloaderPathsDraft.value = normalizeDownloaderPaths(data)
        downloaderPrefsRecommended.value = data.recommended || null
        downloaderPrefsRaw.value = data.raw || null
      }
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      downloaderPrefsLoading.value = false
    }
  }
  function applyRecommendedPrefs() {
    if (downloaderPrefsRecommended.value) {
      downloaderPrefsDraft.value = normalizeDownloaderPrefs(downloaderPrefsRecommended.value)
      notify('已填入推荐值，点「保存」后生效')
    }
  }
  async function saveDownloaderPrefs() {
    saving.value = true
    try {
      const data = unwrapResponse(
        await api.settings.saveDownloaderPrefs(normalizeDownloaderPrefs(downloaderPrefsDraft.value)),
      )
      if (data && data.available) {
        downloaderPrefsDraft.value = normalizeDownloaderPrefs(data)
        downloaderPrefsRaw.value = data.raw || null
      }
      notify('下载器参数已保存')
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      saving.value = false
    }
  }
  async function saveDownloaderPaths() {
    saving.value = true
    try {
      const data = unwrapResponse(
        await api.settings.saveDownloaderPaths(normalizeDownloaderPaths(downloaderPathsDraft.value)),
      )
      if (data && data.available) {
        downloaderPathsDraft.value = normalizeDownloaderPaths(data)
        downloaderPrefsRaw.value = data.raw || null
      }
      notify('下载目录已保存')
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      saving.value = false
    }
  }
  async function loadDefaults() {
    defaultsLoading.value = true
    try {
      const data = unwrapResponse(await api.settings.defaults())
      defaultsDraft.value = normalizeDefaults(data || {})
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      defaultsLoading.value = false
    }
  }
  async function saveDefaults() {
    saving.value = true
    try {
      unwrapResponse(await api.settings.saveDefaults(normalizeDefaults(defaultsDraft.value)))
      notify('默认任务模板已保存')
      await loadStatus()
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      saving.value = false
    }
  }
  function saveActiveSettings() {
    const tab = settingsTab.value
    if (tab === 'downloader') return saveDownloaderAndPaths()
    if (tab === 'template') return saveDefaults()
    if (tab === 'iyuu') return saveIyuu()
    if (tab === 'fallback') return saveSettings()
    if (tab === 'cloud') return saveCloud()
    return saveSettings()
  }
  async function saveCloud() {
    await saveSettings()
    await loadCloud()
    await testCloud()
  }
  async function saveDownloaderAndPaths() {
    saving.value = true
    try {
      const data = unwrapResponse(
        await api.settings.saveDownloaderPrefs(normalizeDownloaderPrefs(downloaderPrefsDraft.value)),
      )
      if (data && data.available) {
        downloaderPrefsDraft.value = normalizeDownloaderPrefs(data)
        downloaderPrefsRaw.value = data.raw || null
      }
      unwrapResponse(
        await api.settings.saveDownloaderPaths(normalizeDownloaderPaths(downloaderPathsDraft.value)),
      )
      unwrapResponse(await api.settings.saveDefaults(normalizeDefaults(defaultsDraft.value)))
      notify('下载与目录已保存')
      await loadStatus()
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      saving.value = false
    }
  }
  async function savePathsTab() {
    saving.value = true
    try {
      unwrapResponse(
        await api.settings.saveDownloaderPaths(normalizeDownloaderPaths(downloaderPathsDraft.value)),
      )
      unwrapResponse(await api.settings.saveDefaults(normalizeDefaults(defaultsDraft.value)))
      notify('下载目录已保存')
      await loadStatus()
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      saving.value = false
    }
  }
  async function saveSettings() {  saving.value = true
    try {
      unwrapResponse(await api.settings.saveSettings(normalizeSettings(settingsDraft.value)))
      notify('设置已保存')
      await loadStatus()
      emit('action')
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      saving.value = false
    }
  }

  return {
    applyRecommendedPrefs,
    backToSettingsDir,
    clearIyuuToken,
    defaultsDraft,
    defaultsLoading,
    downloaderPathsDraft,
    downloaderPrefsDraft,
    downloaderPrefsLoading,
    downloaderPrefsRaw,
    downloaderPrefsRecommended,
    iyuuLoading,
    iyuuShowMore,
    iyuuSites,
    iyuuStatus,
    iyuuTesting,
    loadDefaults,
    loadDownloaderPrefs,
    loadIyuuSites,
    loadRules,
    loadSettingsTabData,
    openSettings,
    openSettingsTab,
    probeRules,
    refreshRules,
    ruleSourceText,
    rulesLoading,
    rulesProbing,
    saveActiveSettings,
    saveCloud,
    saveDefaults,
    saveDownloaderAndPaths,
    saveDownloaderPaths,
    saveDownloaderPrefs,
    saveIyuu,
    savePathsTab,
    saveSettings,
    scrollSettingsNavToActive,
    setRuleHours,
    setRuleHr,
    setRuleRatio,
    settingsDialog,
    settingsNavEl,
    settingsPane,
    settingsTab,
    settingsTabLabel,
    siteRules,
    syncIyuuToDraft,
    testIyuu,
  }
}
