// MagicFlow 前端 · useMusic 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：api（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { ref } from 'vue'
import { unwrapResponse } from '../../../utils'

export function useMusic({ api }) {
  // 15.8.2：音乐薄弹窗（歌单 → 选种计划 / 加种）
  const musicOpen = ref(false)
  const musicText = ref('')
  const musicSites = ref('')        // 逗号分隔站 id；空 = 全部
  const musicResult = ref(null)     // {query, sites, limit, items[], policy, totals{planned, skipped, ...}}
  const musicActing = ref('')       // '' | 'plan' | 'grab'
  const musicError = ref('')
  const musicSavePath = ref('')
  const musicGrabReport = ref(null) // grab 完的落盘报告（带 added/skipped/failed）
  function openMusic() {
    musicOpen.value = true
    musicError.value = ''
  }
  async function loadMusicPlan() {
    if (musicActing.value || !musicText.value.trim()) return
    musicActing.value = 'plan'
    musicError.value = ''
    try {
      const params = new URLSearchParams()
      params.set('text', musicText.value)
      if (musicSites.value && musicSites.value.trim()) params.set('sites', musicSites.value)
      const data = unwrapResponse(await api.features.musicPlan(params.toString()))
        || { items: [] }
      musicResult.value = data
    } catch (err) {
      musicError.value = err?.message || '选种计划失败'
    } finally {
      musicActing.value = ''
    }
  }
  async function runMusicGrab() {
    if (musicActing.value || !musicText.value.trim()) return
    if (!confirm('确认按当前歌单加种？\n\n已加种会自动进账本 / 静默池 / H&R / 删除闸门 / 站点报表。')) return
    musicActing.value = 'grab'
    musicError.value = ''
    try {
      const params = new URLSearchParams()
      params.set('text', musicText.value)
      if (musicSites.value && musicSites.value.trim()) params.set('sites', musicSites.value)
      params.set('confirm', '1')
      if (musicSavePath.value && musicSavePath.value.trim()) params.set('save_path', musicSavePath.value)
      const data = unwrapResponse(await api.features.musicGrab(params.toString()))
        || {}
      musicResult.value = data.plan || musicResult.value
      musicGrabReport.value = data
    } catch (err) {
      musicError.value = err?.message || '加种失败'
    } finally {
      musicActing.value = ''
    }
  }
  function musicResetResult() {
    musicResult.value = null
    musicGrabReport.value = null
  }

  return {
    loadMusicPlan,
    musicActing,
    musicError,
    musicGrabReport,
    musicOpen,
    musicResetResult,
    musicResult,
    musicSavePath,
    musicSites,
    musicText,
    openMusic,
    runMusicGrab,
  }
}
