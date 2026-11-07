/**
 * 推送审计域接口（每次加种一条：成功 + 失败，含站端/下载器原始报错）。
 * 全部返回**原始响应**。
 *
 * 注：这块在「接口层按域拆分」时被整个漏掉 —— `usePushAudit.js` 调的是
 *      `api.push.pushes(...)`，而 `request.js` 里根本没有 `push` 这个域，
 *      运行期直接 `api.push is undefined`。与 `settings.keepList` 是同一类洞：
 *      **调用点写了、域工厂没跟上**。补上时顺手加了 `_task105_api_surface.mjs`
 *      全量校验，`api.<域>.<方法>()` 只要有调用就必须有定义。
 */
export function makePush(c) {
  return {
    /**
     * 推送审计列表。
     * @param {string} qs 已拼好的 query（`limit` / `ok` / `task_id`）
     */
    pushes: (qs = 'limit=50') => c.get(`pushes?${qs}`),
  }
}
