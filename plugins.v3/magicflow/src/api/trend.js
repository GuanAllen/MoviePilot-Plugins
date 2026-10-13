/**
 * 趋势域接口（小时趋势 / 日报 / 归因）。全部返回**原始响应**。
 * ★ 15.12.0：把「时魔为什么变了」做成可查的能力 —— 小时趋势看短期拐点，
 *   日报看长期走向，归因给因子拆解 + 结论 + 建议。
 */
function qs(params = {}) {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, v)
  })
  return p.toString()
}

export function makeTrend(c) {
  return {
    /** 小时趋势（scope=site|task|all，id，hours） */
    hours: (params = {}) => c.get(`trend?${qs(params)}`),
    /** 日报（持久化 180 天；scope，id，days） */
    daily: (params = {}) => c.get(`trend/daily?${qs(params)}`),
    /** 归因（scope，id，hours） */
    why: (params = {}) => c.get(`trend/why?${qs(params)}`),
  }
}
