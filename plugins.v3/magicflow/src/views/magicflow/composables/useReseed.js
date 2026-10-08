// MagicFlow 前端 · 全站辅种域 composable（★ 7.10.0）
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：本机已有资源 → 去各站「挂种落户」（零下载）。
// 依赖注入：api、notify、settingsDraft（只读 reseed_dry）、loadStatus（跑完刷总览）、error（错误横幅）。
// ★ 真值源仍在后端（/reseed、/reseed/run）；站点映射（IYUU 站点表）由后端给，前端只展示。
// ★ fmtTs（秒时间戳 → 本地字符串）是通用格式化 → 已提到 ../format.js。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useReseed({ api, notify, settingsDraft, loadStatus, error }) {
  const reseedState = ref(null)
  const reseedRunning = ref(false)
  // 目标站候选：来自 /reseed 的站点映射（只有 IYUU 站点表里有的站才能当目标），值用域名（后端白名单按域名/名称匹配）
  const reseedSiteOptions = computed(() =>
    ((reseedState.value && reseedState.value.sites) || []).map(s => ({
      title: `${s.name || s.domain}${s.passkey_ok ? ' · passkey ✓' : ''}`,
      value: String(s.domain || s.name || s.sid),
    })),
  )
  async function loadReseed() {
    try {
      reseedState.value = unwrapResponse(await api.pool.reseed()) || null
    } catch (err) {
      // 全站辅种是增强信息，失败不打断界面
    }
  }
  async function runReseed(forceReal = false) {
    reseedRunning.value = true
    try {
      const dry = forceReal ? 0 : (settingsDraft.value.reseed_dry ? 1 : 0)
      const rep = unwrapResponse(await api.pool.reseedRun(dry)) || {}
      const parts = []
      if (rep.plan != null) parts.push(`计划 ${rep.plan}`)
      if (rep.would) parts.push(`可挂 ${rep.would}`)
      if (rep.ok) parts.push(`挂上 ${rep.ok}`)
      if (rep.have) parts.push(`已有 ${rep.have}`)
      if (rep.mismatch) parts.push(`不一致 ${rep.mismatch}`)
      if (rep.nourl) parts.push(`缺链 ${rep.nourl}`)
      if (rep.pv) parts.push(`缺 PV ${rep.pv}`)
      if (rep.fail) parts.push(`失败 ${rep.fail}`)
      notify(`全站辅种${dry ? '（干跑）' : ''}完成：` + (parts.join(' / ') || '无候选') +
        ((rep.errors && rep.errors.length) ? `｜${rep.errors[0]}` : ''))
      await Promise.all([loadReseed(), loadStatus()])
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      reseedRunning.value = false
    }
  }

  return {
    reseedState, reseedRunning, reseedSiteOptions, loadReseed, runReseed,
  }
}
