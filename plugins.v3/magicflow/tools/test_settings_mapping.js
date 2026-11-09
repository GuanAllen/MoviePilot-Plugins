// 魔流 · 任务 105 / API-01 前端设置映射离线测试（node，无浏览器/无后端）
//
// 复现的旧缺陷（19.12.43）：
//   useTasks.loadStatus 里 `...(status.value.fallback || {})` 把后端 fallback 段的
//   短键 enabled 铺到 settingsDraft 上 → 覆盖插件总开关 enabled；
//   同时短键（interval/sources/...）与长键（fallback_interval_minutes/...）不匹配，
//   fallback_* 一个都没填 → normalizeSettings 用默认值把用户配置静默覆盖。
//
// 本测试只 import 两个纯模块（settingsMap.js / utils.js），不依赖 Vue/DOM。
//
// 用法：node tools/test_settings_mapping.js（退出码 0=PASS / 1=FAIL）

import { fallbackSettingsFrom } from '../src/views/magicflow/composables/settingsMap.js'
import { normalizeSettings } from '../src/utils.js'

let cases = 0
const fails = []
function ok(cond, name, detail = '') {
  cases += 1
  if (cond) console.log(`  ✅ ${name}`)
  else {
    console.log(`  ❌ ${name}${detail ? ` —— ${detail}` : ''}`)
    fails.push(name)
  }
}

// 与 useTasks.loadStatus 相同的组装方式（只保留开关与 fallback 段，其余键不影响本测试）
function draftFromStatus(status) {
  return normalizeSettings({
    enabled: status.enabled,
    ...fallbackSettingsFrom(status.fallback),
  })
}

console.log('── 0. 修改前问题复现（旧代码 spread 行为） ──')
{
  const status = { enabled: false, fallback: { enabled: true, interval: 120 } }
  // 旧实现原样：
  const legacyDraft = normalizeSettings({ enabled: status.enabled, ...(status.fallback || {}) })
  ok(legacyDraft.enabled === true, '旧写法确实把总开关翻成 true（复现 API-01 前一半）')
  ok(legacyDraft.fallback_interval_minutes === 30,
    '旧写法把 interval=120 丢成默认 30（复现 API-01 后一半）')
  // 新实现：
  const fixedDraft = draftFromStatus(status)
  ok(fixedDraft.enabled === false && fixedDraft.fallback_interval_minutes === 120,
    '新写法同时修好两半（总开关 false / 兜底 120）')
}

console.log('── A. 总开关与兜底开关互不污染（4 种组合） ──')
const combos = [
  [true, false, '总开 / 兜底关'],
  [false, true, '总关 / 兜底开'],
  [true, true, '双开'],
  [false, false, '双关'],
]
for (const [enabled, fbEnabled, label] of combos) {
  const d = draftFromStatus({ enabled, fallback: { enabled: fbEnabled } })
  ok(d.enabled === enabled, `${label}：插件总开关保持 ${enabled}（旧代码会被 fallback.enabled 覆盖）`)
  ok(d.fallback_enabled === fbEnabled, `${label}：兜底开关 = ${fbEnabled}`)
}

console.log('── B. fallback 短键 → 长键映射完整 ──')
const status = {
  enabled: true,
  fallback: {
    enabled: false,
    sources: ['tvdb', 'imdb'],
    paths: ['/downloads/a', '/downloads/b'],
    interval: 120,
    scan_max: 66,
    sp_to_s00: true,
    after_import: false,
    dry_run: true,
  },
}
const d = draftFromStatus(status)
ok(d.enabled === true, '总开关 true 不被 fallback.enabled=false 污染')
ok(d.fallback_enabled === false, 'fallback_enabled 正确取 false')
ok(JSON.stringify(d.fallback_sources) === JSON.stringify(['tvdb', 'imdb']), 'sources 映射')
ok(JSON.stringify(d.fallback_paths) === JSON.stringify(['/downloads/a', '/downloads/b']), 'paths 映射')
ok(d.fallback_interval_minutes === 120, 'interval → fallback_interval_minutes')
ok(d.fallback_scan_max === 66, 'scan_max → fallback_scan_max')
ok(d.fallback_sp_to_s00 === true, 'sp_to_s00 映射')
ok(d.fallback_after_import === false, 'after_import 映射（缺省 true）')
ok(d.fallback_dry_run === true, 'dry_run 映射')

console.log('── C. 缺省与边界 ──')
const none = draftFromStatus({ enabled: true })
ok(none.fallback_enabled === true, '无 fallback 段：兜底默认开（与后端 fallback_enabled 缺省一致）')
ok(none.fallback_interval_minutes === 30 && none.fallback_scan_max === 30, '默认 30/30')
ok(none.enabled === true, '无 fallback 段不影响总开关')
const zero = fallbackSettingsFrom({ interval: 0, scan_max: 0 })
ok(zero.fallback_interval_minutes === 30 && zero.fallback_scan_max === 30, '非法 0 回落到默认（不让 normalize 把 0 钳成 5 掩盖配置缺失）')

console.log('── D. 只改一个 fallback 配置，其余保持一致 ──')
const before = draftFromStatus(status)
const edited = normalizeSettings({ ...before, fallback_scan_max: 99 })
ok(edited.fallback_scan_max === 99, '被改项生效')
ok(edited.enabled === before.enabled, '总开关未变')
ok(edited.fallback_enabled === before.fallback_enabled, '兜底开关未变')
ok(edited.fallback_interval_minutes === before.fallback_interval_minutes, '未改项 interval 未变')
ok(JSON.stringify(edited.fallback_sources) === JSON.stringify(before.fallback_sources), '未改项 sources 未变')

console.log('── E. 保存其他设置但不碰两个开关 ──')
const other = normalizeSettings({ ...before, journal_keep: 9 })
ok(other.journal_keep === 9, '其他设置生效')
ok(other.enabled === before.enabled && other.fallback_enabled === before.fallback_enabled, '两个开关保持')
ok(other.fallback_interval_minutes === before.fallback_interval_minutes && other.fallback_scan_max === before.fallback_scan_max,
  'fallback 其余键保持')
const again = normalizeSettings(other)
ok(JSON.stringify(again) === JSON.stringify(other), '保存后再归一化幂等（不会二次漂移）')

console.log('── F. 源码回归守卫 ──')
const fs = await import('node:fs')
const src = fs.readFileSync(new URL('../src/views/magicflow/composables/useTasks.js', import.meta.url), 'utf8')
ok(src.includes('fallbackSettingsFrom('), 'useTasks 使用显式映射函数')
ok(!/\(status\.value\.fallback \|\| \{\}\)/.test(src), '旧的 `...(status.value.fallback || {})` 已移除且未复活')
const map = fs.readFileSync(new URL('../src/views/magicflow/composables/settingsMap.js', import.meta.url), 'utf8')
ok(!/^\s*enabled\s*:/m.test(map), '映射模块不产出 enabled（总开关只从 status.enabled 来）')

console.log(`\n${fails.length ? '❌ FAIL' : '✅ PASS'} —— ${cases - fails.length}/${cases} 通过`)
if (fails.length) console.log('失败项：' + fails.join('；'))
process.exit(fails.length ? 1 : 0)
