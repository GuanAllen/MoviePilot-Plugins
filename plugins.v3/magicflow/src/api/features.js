/**
 * 功能域接口（推荐 / 跨站取种 / 点播 / 音乐 / 补源 / 豆瓣 / 签到 / 考核 / 认领 / 云盘归档 / 跨盘兜底）。
 * 全部返回**原始响应**。
 */
export function makeFeatures(c) {
  return {
    // ── 推荐 ──────────────────────────────────────────────
    recommend: () => c.get('recommend'),
    recommendAct: (hash, action) => c.post(`recommend/${hash}/${action}`, {}),
    recommendBatchImport: (qs) => c.post(`recommend/batch_import?${qs}`, {}),

    // ── 跨站取种 ───────────────────────────────────────────
    crossseed: () => c.get('crossseed'),
    crossseedDrop: (hash) => c.post(`crossseed?action=drop&hash=${encodeURIComponent(hash)}`, {}),
    crossseedUnban: (domain = '') => c.post(
      domain ? `crossseed?action=unban&site=${encodeURIComponent(domain)}` : 'crossseed?action=unban', {}),
    crossseedGuard: () => c.post('crossseed?action=guard', {}),
    crossseedClear: () => c.post('crossseed?action=clear', {}),

    // ── 点播 ──────────────────────────────────────────────
    ondemandSearch: (params) => c.post(`ondemand?${params}`, {}),
    ondemandItems: () => c.get('ondemand/items?limit=50'),
    ondemandAct: (hash, action) => c.post(
      `ondemand/act?hash=${encodeURIComponent(hash)}&action=${encodeURIComponent(action)}`, {}),

    // ── 音乐线 ─────────────────────────────────────────────
    musicPlan: (params) => c.get(`agent/music/plan?${params}`),
    musicGrab: (params) => c.post(`agent/music/grab?${params}`, {}),

    // ── 补源 ──────────────────────────────────────────────
    rescueScan: () => c.get('rescue?action=scan'),
    rescueRun: (params) => c.post(`rescue?${params}`, {}),

    // ── 豆瓣评分 ───────────────────────────────────────────
    doubanService: () => c.get('douban_service'),
    doubanAction: (action) => c.post(`douban_service?action=${action}`, {}),

    // ── 签到 ──────────────────────────────────────────────
    signinRun: (query) => c.post(`signin/run?${query}`, {}),
    signinReport: () => c.get('signin?days=7'),

    // ── 新手考核 ───────────────────────────────────────────
    exam: () => c.get('exam'),
    examAct: (q) => c.post(`exam/act?${q}`, {}),

    // ── 认领 ──────────────────────────────────────────────
    claim: (q = '') => c.get(`claim${q}`),
    claimRun: () => c.post('claim/run?dry=1', {}),

    // ── 云盘归档 ───────────────────────────────────────────
    cloud: () => c.get('cloud'),
    cloudTest: () => c.get('cloud/test'),
    cloudPlan: (limit) => c.post(`cloud/plan?limit=${limit}`),
    cloudUpload: (path) => c.post(`cloud/upload?dry_run=false&path=${encodeURIComponent(path)}`),
    cloudRun: (dryRun, limit) => c.post(
      `cloud/run?dry_run=${dryRun ? 'true' : 'false'}&limit=${limit}`),

    // ── 跨盘兜底 ───────────────────────────────────────────
    fallback: () => c.get('fallback?resolve_paths=true'),
    fallbackRun: (dryRun) => c.post(`fallback/run?dry_run=${dryRun ? 'true' : 'false'}`),

    // ── 宿主域 ────────────────────────────────────────────
    /** 站点图标（宿主 API 根） */
    siteIcon: (id) => c.hostGet(`site/icon/${id}`),
  }
}
