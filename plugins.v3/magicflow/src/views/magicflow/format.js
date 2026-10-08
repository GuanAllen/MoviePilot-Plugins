// MagicFlow 前端 · 纯格式化工具（P3 拆分：自 index.vue 抽出，无行为变更）

export function formatRemain(min) {
  const m = Number(min)
  if (!Number.isFinite(m) || m <= 0) return '0 分钟'
  if (m < 60) return `${Math.round(m)} 分钟`
  const hrs = m / 60
  if (hrs < 24) return `${hrs.toFixed(hrs < 10 ? 1 : 0)} 小时`
  return `${(hrs / 24).toFixed(1)} 天`
}

// 兼容 秒 / 毫秒 / ISO 字符串
export function tsText(ts) {
  if (ts === null || ts === undefined || ts === '') return '—'
  let d
  if (typeof ts === 'number') d = new Date(ts > 1e11 ? ts : ts * 1000)
  else d = new Date(ts)
  if (!(d instanceof Date) || Number.isNaN(d.getTime())) return '—'
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function fmtTs(ts) {
  const n = Number(ts || 0)
  return n > 0 ? new Date(n * 1000).toLocaleString() : '—'
}
