/**
 * 池域接口（操作记录 / 事件流 / 全站辅种 / 健康检查）。
 * 全部返回**原始响应**。
 */
export function makePool(c) {
  return {
    /** 全局操作记录（qs 含 `?kind=…&limit=…`） */
    operations: (qs = '') => c.get(`operations${qs}`),
    /** 可观测事件流（qs 为 query 串，不含 `?`） */
    events: (qs) => c.get(`events?${qs}`),
    /** 全站辅种（reseed）状态 */
    reseed: () => c.get('reseed'),
    /** 全站辅种：跑一轮（dry 干跑） */
    reseedRun: (dry) => c.post(`reseed/run?dry=${dry}`, {}),
    /** 健康检查 */
    health: () => c.get('health'),
  }
}
