/**
 * 池统计域接口（站点种子 / H&R 账单 / 静默池 / 站点通报 live）。
 * 全部返回**原始响应**。
 */
export function makePoolstats(c) {
  return {
    /** 站点种子状态（qs 为 query 串，不含 `?`） */
    siteSeeds: (qs) => c.get(`site/seeds?${qs}`),
    /** H&R 账单（qs 为 query 串，不含 `?`）；live=1 = 绕过报表缓存重采 */
    hrBills: (qs) => c.get(`hr/bills?${qs}`),
    /** 当前登录用户（宿主域，人工结清审计操作人的唯一来源） */
    currentUser: () => c.hostGet('user/current'),
    /**
     * 人工结清 H&R 账单（★ 任务 96：复用 19.12.44 已有动作，不新增业务接口）。
     * confirm=1 是后端写动作硬要求；reason / by 后端都会校验，前端也做一遍。
     */
    hrSettleManual: ({ hash, reason, by }) => {
      const q = new URLSearchParams({
        action: 'hrbills_settle_manual',
        confirm: '1',
        hash: String(hash || ''),
        reason: String(reason || ''),
        by: String(by || ''),
      })
      return c.get(`tags?${q.toString()}`)
    },
    /** 静默池全局视图 */
    silentPool: () => c.get('silent/pool'),
    /** 静默不变量收敛（confirm=1 才写） */
    silentEnforce: (confirm = 0) => c.get(`silent/enforce?confirm=${confirm ? 1 : 0}`),
    /** 站点实时通报 */
    live: (sid) => c.get(`live${sid ? `?site_id=${sid}` : ''}`),
  }
}
