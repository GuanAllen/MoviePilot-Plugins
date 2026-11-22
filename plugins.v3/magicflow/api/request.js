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
import { makeAssets } from './assets'
import { makeJobs } from './jobs'
import { makeTrend } from './trend'
import { makeNotify } from './notify'
import { makePlan } from './plan'
import { makePush } from './push'

/** 插件 API 基址。 */
export function pluginBaseOf(pluginId) {
  return `plugin/${pluginId || 'MagicFlow'}`
}

/**
 * 只读请求的默认配置（19.12.61）。
 *
 * 背景：本页有 15 个轮询器（jobs 4s / ondemand 10s / notify 10s / status 30s …），
 * 手机上切网、锁屏回来、长连接被中间层回收时，个把请求会以「没拿到任何 HTTP 响应」失败。
 * 宿主的错误提示去重窗口只有 15ms（`w$=15`），等于不去重 —— 每次抖动都弹一条
 * 「网络连接失败」，看着就是「总是有这个」。
 *
 * 因此只读请求一律：不弹提示（`feedback:'silent'`）、不计入宿主连接状态
 * （`skipConnectionTracking`，宿主自己的 ping 仍在监控）、失败后静默重试一次。
 * 写操作（post/put/delete）保持失败即提示 —— 那是用户点的，必须让他知道。
 */
const QUIET = { feedback: 'silent', skipConnectionTracking: true }

/** 没拿到任何 HTTP 响应的链路层失败（切网 / 长连接被回收 / 弱网丢包）。 */
function isTransportError(e) {
  const code = e?.code
  return code === 'ERR_NETWORK' || code === 'NETWORK_ERROR' || code === 'ETIMEDOUT'
}

/** 只读请求：静默 + 一次重试（幂等，重试安全）。 */
async function getQuiet(http, url, config) {
  const cfg = { ...QUIET, ...(config && typeof config === 'object' ? config : {}) }
  try {
    return await http.get(url, cfg)
  } catch (e) {
    // 离线时不重试，避免无谓翻倍
    if (!isTransportError(e) || (typeof navigator !== 'undefined' && navigator.onLine === false)) throw e
    await new Promise((r) => setTimeout(r, 500))
    return http.get(url, cfg)
  }
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
    get: (path, config) => getQuiet(http, `${base}/${path}`, config),
    // ★ 19.12.91：post 也能传 config。写操作默认由宿主弹一条错误提示，
    //   调用点自己再 notify 一次就是**两条一模一样的红框**（推荐详情里连弹两次
    //   「缺少保存路径」）。需要自己统一提示的写操作传 `{ feedback: 'silent' }`。
    post: (path, body, config) => http.post(`${base}/${path}`, body, config),
    put: (path, body) => http.put(`${base}/${path}`, body),
    delete: (path) => http.delete(`${base}/${path}`),
    /** 宿主域 GET/POST（path 相对宿主 API 根） */
    hostGet: (path, config) => getQuiet(http, path, config),
    hostPost: (path, body) => http.post(path, body),
    /** 顺手拆包版（等价于 unwrapResponse(await get/post)） */
    getU: async (path, config) => unwrapResponse(await getQuiet(http, `${base}/${path}`, config)),
    postU: async (path, body) => unwrapResponse(await http.post(`${base}/${path}`, body)),
  }
  c.tasks = makeTasks(c)
  c.pool = makePool(c)
  c.settings = makeSettings(c)
  c.features = makeFeatures(c)
  c.poolstats = makePoolstats(c)
  c.assets = makeAssets(c)
  c.jobs = makeJobs(c)
  c.trend = makeTrend(c)
  c.notify = makeNotify(c)
  c.plan = makePlan(c)
  c.push = makePush(c)
  return c
}
