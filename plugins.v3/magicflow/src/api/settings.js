/**
 * 设置域接口（设置草稿 / 下载器 / 目录 / 默认模板 / IYUU / 标签 / 站点规则）。
 * 全部返回**原始响应**。
 *
 * 注：`rules*` 是**宿主域**接口（MP 原生站点规则），走 `hostGet`。
 */
export function makeSettings(c) {
  return {
    // ── 标签模型 ───────────────────────────────────────────
    /** 标签模型概览 */
    tags: () => c.get('tags'),
    /** 老标签 → 新命名 迁移预演 */
    tagMigratePlan: () => c.get('tags?action=migrate'),
    /** 执行迁移 */
    tagMigrateApply: () => c.post('tags/migrate', { apply: true }),
    /** 标签 ↔ 账本对账（confirm=true 才写） */
    tagReconcile: (confirm = false) => c.get(
      `tags?action=${confirm ? 'reconcile_apply' : 'reconcile'}${confirm ? '&confirm=1&adopt_reseed=1' : ''}`,
    ),

    // ── 设置草稿 ───────────────────────────────────────────
    /** 保存常规设置 */
    saveSettings: (payload) => c.post('settings', payload),
    /** 下载器参数（读） */
    downloaderPrefs: () => c.get('downloader/prefs'),
    /** 下载器参数（写） */
    saveDownloaderPrefs: (payload) => c.post('downloader/prefs', payload),
    /** 下载目录（写） */
    saveDownloaderPaths: (payload) => c.post('downloader/paths', payload),
    /** 默认任务模板（读） */
    defaults: () => c.get('defaults'),
    /** 默认任务模板（写） */
    saveDefaults: (payload) => c.post('defaults', payload),

    // ── IYUU ──────────────────────────────────────────────
    iyuuSites: () => c.get('iyuu/sites'),
    iyuuTest: () => c.get('iyuu/test'),

    // ── 站点规则（宿主域）──────────────────────────────────
    rules: () => c.hostGet('rules'),
    refreshRules: () => c.hostGet('rules?action=refresh'),
    rulesProbe: (q = '') => c.hostGet(`rules?action=probe${q}`),
    setRuleHr: (domain, hr) => c.hostGet(
      `rules?action=hr&site=${encodeURIComponent(domain)}&hr=${encodeURIComponent(hr)}`,
    ),
    setRuleHours: (dom, hours) => c.hostGet(
      `rules?action=set&site=${encodeURIComponent(dom)}&hours=${encodeURIComponent(hours)}`,
    ),
    setRuleRatio: (dom, ratio) => c.hostGet(
      `rules?action=set_ratio&site=${encodeURIComponent(dom)}&ratio=${encodeURIComponent(ratio)}`,
    ),
  }
}
