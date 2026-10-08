/**
 * 池统计域接口（站点种子 / H&R 账单 / 静默池 / 站点通报 live）。
 * 全部返回**原始响应**。
 */
export function makePoolstats(c) {
  return {
    /** 站点种子状态（qs 为 query 串，不含 `?`） */
    siteSeeds: (qs) => c.get(`site/seeds?${qs}`),
    /** H&R 账单（qs 为 query 串，不含 `?`） */
    hrBills: (qs) => c.get(`hr/bills?${qs}`),
    /** 静默池全局视图 */
    silentPool: () => c.get('silent/pool'),
    /** 静默不变量收敛（confirm=1 才写） */
    silentEnforce: (confirm = 0) => c.get(`silent/enforce?confirm=${confirm ? 1 : 0}`),
    /** 站点实时通报 */
    live: (sid) => c.get(`live${sid ? `?site_id=${sid}` : ''}`),
  }
}
