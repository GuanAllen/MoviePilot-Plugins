/**
 * 后台任务队列接口（`plugin/MagicFlow/jobs*`）。
 * ★ 15.10.0：慢动作（整理入库 / 订阅 / 刮削 / 批量删除）都在后台跑，
 *   页面关掉也不断；这里只读队列 + 清理历史记录（全部返回原始响应，调用点自行 unwrap）。
 */
export function makeJobs(c) {
  return {
    /** 后台任务列表（含 summary：queued/running/done/failed 计数；batches：按批次汇总）。 */
    getJobs: (limit = 50) => c.get(`jobs?limit=${limit}`),
    /** 清理「已完成 / 失败」的记录（在跑的不动）。 */
    clearJobs: () => c.post('jobs/clear', {}),
    /**
     * ★ 19.12.98：重试失败任务。三选一（优先级 job_id > batch_id > kind）：
     * - `job_id`：重试一条；
     * - `batch_id`：重试**这一批**里失败的（批次行上的「重试本批」，口径最准）；
     * - `kind`：按种类批量。
     * 参数走 query string（MP 插件 API 的 POST 不吃 JSON body）。删除类不可重试。
     */
    retryJobs: ({ job_id = '', batch_id = '', kind = '' } = {}) => {
      const q = []
      if (job_id) q.push(`job_id=${encodeURIComponent(job_id)}`)
      if (batch_id) q.push(`batch_id=${encodeURIComponent(batch_id)}`)
      if (kind) q.push(`kind=${encodeURIComponent(kind)}`)
      return c.post(`jobs/retry?${q.join('&')}`, {})
    },
  }
}
