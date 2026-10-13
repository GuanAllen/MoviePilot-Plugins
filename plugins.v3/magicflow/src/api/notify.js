/**
 * 事件通知接口（`plugin/MagicFlow/notify*`）。
 * ★ 15.13.0：H&R 临期 / 容量红线 / 产出骤降 / 任务失败 → MP 通知渠道；这里只读状态 + 手动触发。
 * 全部返回**原始响应**，调用点自行 unwrap。
 */
export function makeNotify(c) {
  return {
    /** 通知状态：配置 + 最近事件 + 计数 */
    getNotify: (limit = 50) => c.get(`notify?limit=${limit}`),
    /** 通知动作：test（发测试）/ scan（立即扫描）/ clear（清历史） */
    actNotify: (action, text = '') => c.post('notify/act', { action, text }),
  }
}
