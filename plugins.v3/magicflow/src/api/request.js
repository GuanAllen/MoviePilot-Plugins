/**
 * 魔流前端 · 接口层入口（P2）。
 *
 * 约定：
 *  1. **域函数一律返回「原始响应」**，由调用点决定是否 `unwrapResponse()` —— 与拆分前逐一等价，零语义变更。
 *  2. 路径**相对插件基址**（内部拼 `plugin/<id>`）；宿主域接口（`rules` / `site/icon`）显式走 `hostGet`。
 *  3. 动态拼出来的路径（如带筛选条件的 query）直接用 `get/post`，命名函数只覆盖**固定端点**。
 *  4. 只有工作台在用 → 就放 `src/api/`，不提前抽全局。
 */
import { unwrapResponse } from '../utils'
import { makeTasks } from './tasks'
import { makePool } from './pool'
import { makeSettings } from './settings'
import { makeFeatures } from './features'
import { makePoolstats } from './poolstats'

/** 插件 API 基址。 */
export function pluginBaseOf(pluginId) {
  return `plugin/${pluginId || 'MagicFlow'}`
}

/**
 * 建一个「按域分组」的接口客户端。
 * @param {object} http 宿主注入的 api（`props.api`，有 get/post）
 * @param {string} pluginId 插件 id（默认 MagicFlow）
 */
export function createApi(http, pluginId = 'MagicFlow') {
  const base = pluginBaseOf(pluginId)
  const c = {
    base,
    /** 宿主 api 原对象（逃生舱，尽量别用） */
    raw: http,
    /** 插件域 GET/POST（path 相对基址） */
    get: (path) => http.get(`${base}/${path}`),
    post: (path, body) => http.post(`${base}/${path}`, body),
    put: (path, body) => http.put(`${base}/${path}`, body),
    delete: (path) => http.delete(`${base}/${path}`),
    /** 宿主域 GET/POST（path 相对宿主 API 根） */
    hostGet: (path) => http.get(path),
    hostPost: (path, body) => http.post(path, body),
    /** 顺手拆包版（等价于 unwrapResponse(await get/post)） */
    getU: async (path) => unwrapResponse(await http.get(`${base}/${path}`)),
    postU: async (path, body) => unwrapResponse(await http.post(`${base}/${path}`, body)),
  }
  c.tasks = makeTasks(c)
  c.pool = makePool(c)
  c.settings = makeSettings(c)
  c.features = makeFeatures(c)
  c.poolstats = makePoolstats(c)
  return c
}
