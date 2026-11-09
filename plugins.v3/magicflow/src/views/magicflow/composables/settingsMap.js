// MagicFlow 前端 · 设置映射（纯函数，无 Vue 依赖；useTasks 与离线测试共用）
//
// 背景（任务 105 / API-01）：后端 GET /status 的 fallback 段用的是短键
//   enabled / sources / paths / interval / scan_max / sp_to_s00 / after_import / dry_run
// 而 settingsDraft（normalizeSettings）要的是长键
//   fallback_enabled / fallback_sources / fallback_paths / fallback_interval_minutes / ...
// 旧代码直接 `...(status.value.fallback || {})`：
//   1) 兜底段里的 enabled 把「插件总开关」enabled 覆盖掉（总开关被兜底开关污染）；
//   2) 短键 name 与长键对不上，fallback_* 一个都没填，保存时被 normalizeSettings 的
//      默认值（fallback_enabled=true / interval=30 / scan_max=30）静默覆盖。
// 本模块只做「短键 → 长键」的显式映射，绝不产出 enabled（总开关只从 status.enabled 来）。

const DEFAULT_INTERVAL_MINUTES = 30
const DEFAULT_SCAN_MAX = 30

function positiveNumber(value, fallback) {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

/**
 * 把 /status 的 fallback 段映射成 settingsDraft 的 fallback_* 字段。
 * 缺失字段按「后端默认」处理（is_true 缺省 = true，路径缺省 = 空数组）。
 * @param {object|null|undefined} fallback 后端 status.fallback
 * @returns {object} 仅含 fallback_* 键（不含 enabled）
 */
export function fallbackSettingsFrom(fallback) {
  const fb = fallback && typeof fallback === 'object' ? fallback : {}
  return {
    fallback_enabled: fb.enabled !== false,
    fallback_sources: Array.isArray(fb.sources) ? fb.sources.slice() : [],
    fallback_paths: Array.isArray(fb.paths) ? fb.paths.slice() : [],
    fallback_interval_minutes: positiveNumber(fb.interval, DEFAULT_INTERVAL_MINUTES),
    fallback_scan_max: Math.max(1, Math.trunc(positiveNumber(fb.scan_max, DEFAULT_SCAN_MAX))),
    fallback_sp_to_s00: fb.sp_to_s00 === true,
    fallback_after_import: fb.after_import !== false,
    fallback_dry_run: fb.dry_run === true,
  }
}
