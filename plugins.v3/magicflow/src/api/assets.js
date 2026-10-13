/**
 * 库内资产域接口（`plugin/MagicFlow/assets*`）。
 * 全部返回**原始响应**（调用点自行 unwrap）。
 *
 * ★ 与 tasks.js / features.js 同款：`c` 是 request.js `createApi()` 造出来的域客户端，
 *   本文件只做「路径 → 方法」映射，不持有 axios 实例。
 */
export function makeAssets(c) {
  return {
    /**
     * 库内资产列表（limit=0 = 全部）。真值源 = 资源账本 ∩ 下载器快照。
     * ★ 资产（资源）粒度：一条 = 一份资源（本体 + 各站全部辅种）。
     * includeStale=true 时带上「不在下载器（仅账本残留）」条目（默认不显示）。
     */
    getAssets: (limit = 0, includeStale = false) => c.get(`assets?limit=${limit}&include_stale=${includeStale ? 1 : 0}`),
    /**
     * 删库内资产：confirm=0 干跑 / confirm=1 真删；delete_files=1 连文件删（不可恢复）。
     * ★ 传 `resource_ids`（资源 id）——删除按资源整组（删种 + 连带所有辅种 + 文件）。
     */
    deleteAssets: (payload) => c.post('assets/delete', payload),
    /**
     * ★ 15.9.0 库内资源管理·行内养护动作（不删除任何东西）：
     * action ∈ protect（手动保留/永不自动删）| unprotect（取消保留）|
     * subscribe（订阅作品+季，抓齐其余集）| unsubscribe（退订）|
     * organize（让 MP 重新整理入库 = 换个地方）| scrape（多源重刮，纠正刮错）。
     * 传 `resource_ids`（= getAssets 返回的 resource_id）。
     */
    actAssets: (payload) => c.post('assets/act', payload),
  }
}
