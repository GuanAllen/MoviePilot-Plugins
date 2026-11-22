/**
 * 魔流前端 · 可见性感知轮询（19.12.63 / 任务 B）。
 *
 * 本页散落着 15 个主动轮询器（jobs 4s、notify/ondemand/music 10s、status 30s、
 * health 60s、live 120s、trend 300s …）。切到后台标签、最小化、手机锁屏之后
 * 它们照常发请求：既白耗流量，又正好撞上「切网 / 长连接被回收」的窗口，
 * 是「总是有网络连接失败」的放大器之一。
 *
 * 这里只做两件事：
 *  1. 标签隐藏期间，定时器空转但**不执行回调**（零请求）；
 *  2. 恢复可见时立刻错峰补一次，用户切回来不用等满一个周期才看到新数据。
 *
 * 为什么不改请求层挂起/去重：挂起的 Promise 会一直占着 `loading` 状态，
 * 恢复时还可能把几十个排队请求一起放出去；定时器层直接不触发，没有这两种副作用。
 * 后端的任务节拍（刷流 / H&R / 对账）不受影响 —— 那些在服务端跑，与页面可见性无关。
 */
const jobs = new Map()      // id -> 回调
const timers = new Map()    // id -> 原生 interval id
let seq = 0
let bound = false
let hidden = false

function pageHidden() {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden'
}

function safeCall(fn) {
  try {
    const r = fn()
    // 轮询回调大多是 async；静默吞掉 rejection，别变成未处理的 Promise 异常
    if (r && typeof r.catch === 'function') r.catch(() => {})
  } catch (_) { /* 单个轮询器出错不影响其它 */ }
}

function onVisibilityChange() {
  const nowHidden = pageHidden()
  if (nowHidden === hidden) return
  hidden = nowHidden
  if (hidden) return
  // 恢复可见：按注册顺序错峰 25ms，避免 15 个请求同一瞬间打出去
  let i = 0
  for (const fn of jobs.values()) {
    const delay = i * 25
    i += 1
    window.setTimeout(() => safeCall(fn), delay)
  }
}

function ensureBound() {
  if (bound || typeof document === 'undefined') return
  bound = true
  hidden = pageHidden()
  document.addEventListener('visibilitychange', onVisibilityChange)
  // 某些 WebView / PWA 在锁屏恢复时只发 pageshow，不发 visibilitychange
  window.addEventListener('pageshow', onVisibilityChange)
  // 从后台切回来时 focus 通常比 visibilitychange 更早；幂等，重复不会多补
  window.addEventListener('focus', onVisibilityChange)
}

/** 替代 `window.setInterval(fn, ms)`；返回句柄，交给 `stopPolling` 清理。 */
export function startPolling(fn, ms) {
  if (typeof window === 'undefined' || typeof fn !== 'function') return null
  ensureBound()
  const id = ++seq
  jobs.set(id, fn)
  timers.set(id, window.setInterval(() => {
    if (hidden || pageHidden()) return
    safeCall(fn)
  }, ms))
  return id
}

/** 替代 `window.clearInterval(id)`。 */
export function stopPolling(id) {
  if (id === null || id === undefined) return
  const timer = timers.get(id)
  if (timer !== null && timer !== undefined) window.clearInterval(timer)
  timers.delete(id)
  jobs.delete(id)
}
