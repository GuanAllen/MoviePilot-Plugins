/**
 * 设置域接口（设置草稿 / 下载器 / 目录 / 默认模板 / IYUU / 标签 / 站点规则）。
 * 全部返回**原始响应**。
 *
 * 注：`rules*` 之前被误当成**宿主域**接口走 `hostGet`，实测打到 `/api/v1/rules` 是 **404**
 *      —— MP 没有这个路由，规则库一直是插件自己注册的 `GET /rules`
 *      （`features/api.py` → `get_site_rules`，真实地址 `/api/v1/plugin/MagicFlow/rules`）。
 *      现一律走插件域 `get`。
 */
export function makeSettings(c) {
  return {
    // ── 标签模型 ───────────────────────────────────────────
    /** 标签模型概览 */
    tags: () => c.get('tags'),
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

    // ── 站点规则（插件域 /rules）────────────────────────────
    rules: () => c.get('rules'),
    refreshRules: () => c.get('rules?action=refresh'),
    rulesProbe: (q = '') => c.get(`rules?action=probe${q}`),
    setRuleHr: (domain, hr) => c.get(
      `rules?action=hr&site=${encodeURIComponent(domain)}&hr=${encodeURIComponent(hr)}`,
    ),
    setRuleHours: (dom, hours) => c.get(
      `rules?action=set&site=${encodeURIComponent(dom)}&hours=${encodeURIComponent(hours)}`,
    ),
    setRuleRatio: (dom, ratio) => c.get(
      `rules?action=set_ratio&site=${encodeURIComponent(dom)}&ratio=${encodeURIComponent(ratio)}`,
    ),

    // ── 手动保种（`__keep__` 伪任务，★ 19.10.41/42）────────────
    // 三个入口都在 `tags` 域按 `action` 分发（`features/tags.py` 的 TAG_ACTIONS）：
    //   hold_list         名单（账本 taken_by=__keep__ + 下载器实况）
    //   hold_candidates   静默池候选（挑种用）
    //   hold / unhold     挂 / 解除（confirm=1 才真写；unhold 恒真写）
    /** 已挂的手动保种名单 */
    keepList: () => c.get('tags?action=hold_list'),
    /** 静默池候选（从这里挑要保的种） */
    holdCandidates: () => c.get('tags?action=hold_candidates'),
    /**
     * 挂 / 解除手动保种。
     * @param {string|string[]} hashes 一个或多个 hash（后端按逗号批量）
     * @param {boolean} hold true=挂保种（并拉起做种）· false=解除（退回静默池）
     */
    holdSeeds: (hashes, hold = true) => {
      const hs = (Array.isArray(hashes) ? hashes : [hashes])
        .map((h) => String(h || '').trim().toLowerCase())
        .filter(Boolean);
      const act = hold ? 'hold' : 'unhold';
      return c.get(
        `tags?action=${act}&hash=${encodeURIComponent(hs.join(','))}`
        + `&confirm=1&reason=${encodeURIComponent('界面手动保种')}`,
      );
    },
  }
}
