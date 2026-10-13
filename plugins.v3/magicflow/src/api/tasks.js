/**
 * 任务域接口（`plugin/MagicFlow/tasks*` / `status` / `trend`）。
 * 全部返回**原始响应**（调用点自行 unwrap）。
 */
export function makeTasks(c) {
  return {
    /** 全局状态（轮询用） */
    status: () => c.get('status'),
    /** 魔力趋势（72h / 全站） */
    trend: () => c.get('trend?scope=all&hours=72'),
    /** 单个任务详情 */
    detail: (taskId) => c.get(`tasks/${taskId}`),
    /** 单个任务魔力明细（做种台账） */
    bonus: (taskId) => c.get(`tasks/${taskId}/bonus`),
    /** 候选种子 */
    candidates: (taskId) => c.get(`tasks/${taskId}/candidates`),
    /** 单任务操作记录（qs 含 `?kind=…&limit=…`） */
    taskOperations: (taskId, qs = '') => c.get(`tasks/${taskId}/operations${qs}`),
    /** ★ 组合优化器（15.15.0）：容量预算下的最优「保 / 删」（0/1 背包）。
     *  ``params.budget_gb`` 留空 = 自动取「保留 ≥95% 时魔」的最小预算。 */
    optimize: (taskId, params = {}) => {
      const p = new URLSearchParams()
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') p.set(k, v)
      })
      const qs = p.toString()
      return c.get(`tasks/${taskId}/optimize${qs ? `?${qs}` : ''}`)
    },
    /** 回填站点分页（手动触发） */
    backfillPages: (taskId) => c.post(`tasks/${taskId}/backfill-pages`),
    /** 立即跑一轮 */
    run: (taskId) => c.post(`tasks/${taskId}/run`, {}),
    /** 改运行状态（mode: running/stopped/disabled…） */
    setState: (taskId, mode) => c.post(`tasks/${taskId}/state`, { mode }),
    /** 新建任务 */
    create: (payload) => c.post('tasks', payload),
    /** 改任务（带 id） */
    update: (taskId, payload) => c.put(`tasks/${taskId}`, payload),
    /** 删任务（qs 为 `?settle=idle` 或 `?handover_to=…`） */
    remove: (taskId, qs = '') => c.delete(`tasks/${taskId}${qs}`),
    /** 批量转移（idle / handover） */
    handover: (taskId, body) => c.post(`tasks/${taskId}/handover`, body),
    /** 查转移去向 */
    handoverInfo: (taskId) => c.get(`tasks/${taskId}/handover`),
    /** 单种操作（pause/resume/delete…） */
    torrentAction: (taskId, hash, action) => c.post(`tasks/${taskId}/torrents/${hash}/${action}`, {}),
    /** 批量种操作 */
    torrentsBatch: (taskId, payload) => c.post(`tasks/${taskId}/torrents/batch`, payload),
  }
}
