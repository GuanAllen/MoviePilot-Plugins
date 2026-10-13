/**
 * 后台任务队列接口（`plugin/MagicFlow/jobs*`）。
 * ★ 15.10.0：慢动作（整理入库 / 订阅 / 刮削 / 批量删除）都在后台跑，
 *   页面关掉也不断；这里只读队列 + 清理历史记录（全部返回原始响应，调用点自行 unwrap）。
 */
export function makeJobs(c) {
  return {
    /** 后台任务列表（含 summary：queued/running/done/failed 计数）。 */
    getJobs: (limit = 50) => c.get(`jobs?limit=${limit}`),
    /** 清理「已完成 / 失败」的记录（在跑的不动）。 */
    clearJobs: () => c.post('jobs/clear', {}),
  }
}
