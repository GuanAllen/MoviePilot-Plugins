/**
 * 库内资产域接口（`plugin/MagicFlow/assets*`）。
 * 全部返回**原始响应**（调用点自行 unwrap）。
 *
 * ★ 与 tasks.js / features.js 同款：`c` 是 request.js `createApi()` 造出来的域客户端，
 *   本文件只做「路径 → 方法」映射，不持有 axios 实例。
 */
export function makeAssets(c) {
  return {
    /** 库内资产列表（limit=0 = 全部）。真值源 = 下载器快照 ∩ 标签账本。 */
    getAssets: (limit = 0) => c.get(`assets?limit=${limit}`),
    /** 删库内资产：confirm=0 干跑 / confirm=1 真删；delete_files=1 连文件删（不可恢复）。 */
    deleteAssets: (payload) => c.post('assets/delete', payload),
  }
}
