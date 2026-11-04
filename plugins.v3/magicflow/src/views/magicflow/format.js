import { formatBytes, formatBonus } from '../../utils'

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

/** 任务类型：brush（刷流，考核上传量）/ bonus（刷魔力，考核魔力）。 */
export function taskKind(task) {
  return task?.task_type === 'brush' ? 'brush' : 'bonus'
}

/** 任务类型的中文名。 */
export function taskKindText(task) {
  return taskKind(task) === 'brush' ? '刷流' : '魔力'
}

/**
 * 汇总一个任务的展示指标。
 * 所有字段只读、不改变取数逻辑：上传来自 task_uploaded（任务级），时魔来自
 * site_bonus_per_hour（站点级），两者层级不同，UI 必须标注清楚。
 */
export function taskMetrics(task) {
  const t = task || {};
  const kind = taskKind(t);
  const isBrush = kind === 'brush';
  const seeds = Number(t.seeding_count || 0);
  const upBytes = Number(t.task_uploaded || 0);
  const upActive = Number(t.task_upload_active || 0);
  const upSpeed = Number(t.task_up_speed || 0);
  const bonusOk = !!t.site_bonus_ok && t.site_bonus_per_hour != null;
  const bonus = bonusOk ? Number(t.site_bonus_per_hour) : null;

  // 上传：任务级（本任务种子池累计）。有托管种子却一个都没在上传 → 空跑信号。
  const upload = {
    key: 'upload',
    label: '上传',
    value: upBytes,
    text: formatBytes(upBytes),
    speed: upSpeed > 0 ? formatBytes(upSpeed) : '',
    active: upActive,
    noUpload: seeds > 0 && upActive === 0,
  };
  // 时魔：站点级（站点自报值），不是本任务产出，不能与 upload 直接相除。
  const hourly = {
    key: 'bonus',
    label: '时魔',
    value: bonus,
    text: bonus == null ? '—' : formatBonus(bonus),
    ok: bonusOk,
  };

  // 列表副标题用：刷流优先给实时速率（更贴近考核），无速率时回落时魔；
  // 魔力任务给上传累计，让「配额下实际产出多少」可见。
  const secondaryText = isBrush
    ? (upload.speed ? `↑${upload.speed}/s` : hourly.text)
    : `↑${upload.text}`;

  return {
    kind,
    isBrush,
    seeds,
    upload,
    hourly,
    primary: isBrush ? upload : hourly,
    secondary: isBrush ? hourly : upload,
    // 长文本场景（副标题 / 一句话摘要）用带口径的主指标，避免数字裸奔被误读
    primaryText: isBrush ? `${upload.text} 上传` : hourly.text,
    secondaryText,
  }
}

// ── 等级「距下一级还差什么」文案（★ 19.11.20 提为共用纯函数）────────────────
// 后端 level_req 抄 PTD 站点等级表算好差值；算不出的输入放 unknown（写「未知」，
// 不拿 0 顶，铁律 6）。任务概览（OverviewTab）与站点报表（SiteReportDialog）
// 同一出口 —— 单一真值源，不在两处各写一份。
/**
 * 拼「距下一级还差什么」文案；level_next 为空返回 ''。
 * @param {object|null} n 后端 level_next（{name, unmet, unknown}）
 * @param {string} currencyLabel 该站对魔力的自称（蟹币值/金元宝/积分…）
 */
export function levelNextText(n, currencyLabel) {
  if (!n) return ''
  const labels = {
    downloaded: '下载', uploaded: '上传', trueDownloaded: '下载', trueUploaded: '上传',
    seedingSize: '做种体积', totalTraffic: '总流量', seedingBonus: '做种积分',
    bonus: currencyLabel || '魔力', seeding: '做种数', snatches: '完成数', uploads: '发布数', posts: '发帖数',
  };
  const parts = [];
  const un = n.unmet || {};
  if (un.downloaded != null) parts.push(`下载差 ${formatBytes(un.downloaded)}`);
  if (un.uploaded != null) parts.push(`上传差 ${formatBytes(un.uploaded)}`);
  if (un.seedingSize != null) parts.push(`做种体积差 ${formatBytes(un.seedingSize)}`);
  if (un.totalTraffic != null) parts.push(`总流量差 ${formatBytes(un.totalTraffic)}`);
  if (un.ratio != null) parts.push(`分享率需 ≥${Number(un.ratio).toFixed(2)}`);
  if (un.interval != null) parts.push(`入站需再等 ${Math.ceil(un.interval / 86400)} 天`);
  for (const k of ['seedingBonus', 'bonus', 'seeding', 'snatches', 'uploads', 'posts']) {
    if (un[k] != null) parts.push(`${labels[k] || k}差 ${Number(un[k]).toLocaleString()}`);
  }
  for (const k of (n.unknown || [])) {
    if (k === 'interval') continue
    parts.push(`${labels[k] || k}未知`);
  }
  return parts.join(' · ')
}
