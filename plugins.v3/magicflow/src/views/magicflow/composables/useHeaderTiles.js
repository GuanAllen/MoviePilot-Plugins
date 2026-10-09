// MagicFlow 前端 · useHeaderTiles 域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
// 依赖注入：settingsDraft, status（★ 真值源仍在后端；本域只放 UI 状态与动作）。
import { computed } from 'vue'

export function useHeaderTiles({ settingsDraft, status }) {
  const hiddenTiles = computed(() => (Array.isArray(status.value.hidden_tiles) ? status.value.hidden_tiles : []))
  function tileVisible(key) { return !hiddenTiles.value.includes(key) }
  function tileShown(key) {
    const list = settingsDraft.value.hidden_tiles
    return !(Array.isArray(list) && list.includes(key))
  }
  function setTileShown(key, shown) {
    let list = Array.isArray(settingsDraft.value.hidden_tiles) ? [...settingsDraft.value.hidden_tiles] : []
    if (shown) list = list.filter(k => k !== key)
    else if (!list.includes(key)) list.push(key)
    settingsDraft.value.hidden_tiles = list
  }

  return {
    hiddenTiles,
    setTileShown,
    tileShown,
    tileVisible,
  }
}
