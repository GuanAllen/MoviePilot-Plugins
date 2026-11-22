// MagicFlow 前端 · 签到/模拟登录域 composable
// P3 拆分：自 views/magicflow/index.vue **纯搬家**（无行为变更）。
//
// 职责：① 设置页的签到配置（站点多选 siteSelectItems / 今日概览）② 独立「签到」报表功能页
//       （今日矩阵 / 近 7 天热力矩阵 / 筛选 / 一键补签·模拟登录）。
// 依赖注入：api、notify（提示）、status（插件总览；本域只读 options.sites / signin）。
// ★ 真值源仍在后端（/signin/*）；站点列表来自 /status.options.sites。
// ★ 注意：runSigninNow 起完后**只刷 status**，不用 loadStatus()——后者会重载 settingsDraft，
//   把用户正在编辑的设置冲掉（原注释即此意）。
import { computed, ref } from 'vue'
import { unwrapResponse } from '../../../utils'
import { SIGNIN_STATUS_TEXT, SIGNIN_FAIL_STATUS, SIGNIN_ORDER } from '../constants'

export function useSignin({ api, notify, status }) {
  // ── 签到 / 模拟登录（借鉴 MoviePilot「站点自动签到」插件）──────────────────
  // 站点多选：想签几个签几个（siteSelectItems 直接来自 /status.options.sites）
  const siteSelectItems = computed(() =>
    (status.value.options?.sites || []).map(s => ({
      title: s.name || s.domain || String(s.id),
      value: String(s.id),
    }))
  )
  const signinCfg = computed(() => status.value.signin || {})
  const signinToday = computed(() => signinCfg.value.today || {})
  const signinTodayRows = computed(() => {
    const cfg = signinCfg.value || {}
    const signIds = (cfg.sites || []).map(String)
    const loginIds = (cfg.login_sites || []).map(String)
    const rows = []
    const seen = new Set()
    ;[...signIds, ...loginIds].forEach(key => {
      if (seen.has(key)) return
      seen.add(key)
      const info = siteSelectItems.value.find(s => s.value === key) || {}
      const rec = signinToday.value[key] || {}
      rows.push({
        site_id: key,
        site_name: rec.site_name || info.title || key,
        sign: signIds.includes(key),
        login: loginIds.includes(key),
        signin: rec.sign || null,
        loginResult: rec.login || null,
      })
    })
    return rows
  })
  const signinRunning = ref(false)
  // ★ 19.12.89：支持只跑指定的几个站（后端 run_signin 一直有 site_ids，前端以前没用）
  async function runSigninNow(kind = 'sign', opts = {}) {
    if (signinRunning.value) return
    signinRunning.value = true
    try {
      // ★ 插件 API 的 POST 参数只从 query 绑定（body 不生效）→ 参数拼在 URL 上
      const params = { kind: String(kind) }
      const ids = (opts.siteIds || []).map(String).filter(Boolean)
      if (ids.length) params.site_ids = ids.join(',')
      if (opts.force) params.force = 'true'
      const query = new URLSearchParams(params).toString()
      const res = unwrapResponse(await api.features.signinRun(query)) || {}
      const s = res.summary || {}
      const who = ids.length ? `这 ${ids.length} 个站` : ''
      notify(`${who}${kind === 'sign' ? '签到' : '登录'}完成：成功 ${s.ok || 0} / 失败 ${s.fail || 0}`)
      // 只刷新 status（不重载 settingsDraft，避免把正在编辑的设置冲掉）
      status.value = unwrapResponse(await api.tasks.status()) || status.value
      if (signinOpen.value) loadSigninReport()
    } catch (err) {
      notify(`执行失败：${err?.message || err}`, 'error')
    } finally {
      signinRunning.value = false
    }
  }
  // ── 签到报表页（独立的「签到」功能页；设置仍在设置页）─────────────────
  const signinOpen = ref(false)
  const signinReport = ref({ enabled: false, sites: [], records: [], today: '' })
  const signinReportLoading = ref(false)
  async function loadSigninReport() {
    signinReportLoading.value = true
    try {
      signinReport.value = unwrapResponse(await api.features.signinReport()) || signinReport.value
    } catch (err) {
      notify(`签到报表读取失败：${err?.message || err}`, 'error')
    } finally {
      signinReportLoading.value = false
    }
  }
  function openSignin() {
    signinOpen.value = true
    loadSigninReport()
  }
  // ---------------- 报表（按「几十个站」的规模设计） ----------------
  const signinFilter = ref('all')
  const signinSearch = ref('')
  function signinStatusText(s) {
    return SIGNIN_STATUS_TEXT[s] || s
  }
  // 日期标签：09/30 → 9/30（窄屏也能完整显示）
  function signinDateLabel(d) {
    const s = String(d || '')
    if (s.length < 10) return s
    return `${Number(s.slice(5, 7))}/${Number(s.slice(8, 10))}`
  }
  // 单站当天要看的动作：只算「设置里勾了」的那几项（登录站不会显示签到结果）
  function _signinWant(r) {
    const want = []
    if (r.sign !== false) want.push(['签到', r.signin])
    if (r.login !== false) want.push(['登录', r.loginResult])
    return want
  }
  // 单站某天的状态：有失败→fail；缺结果→pending（今天）/none（历史）；全跳过→skip
  function _signinStatus(signin, loginResult, pendingWhenEmpty, cfgSign, cfgLogin) {
    const want = _signinWant({ sign: cfgSign, login: cfgLogin, signin, loginResult })
    if (!want.length) return pendingWhenEmpty ? 'pending' : 'none'
    const vals = want.map(([, x]) => x).filter(Boolean)
    if (vals.length < want.length) return pendingWhenEmpty ? 'pending' : 'none'
    if (vals.every(x => x.skipped)) return 'skip'
    // ★ 失败按「谁失败」分色：签到✗=红、登录✗=橙、都✗=深红
    const bad = k => want.some(([kk, x]) => kk === k && x && !x.ok && !x.skipped)
    const signBad = bad('签到')
    const loginBad = bad('登录')
    if (signBad && loginBad) return 'fail'
    if (signBad) return 'signfail'
    if (loginBad) return 'loginfail'
    return 'ok'
  }
  const signinReportTodayRows = computed(() => {
    const sites = signinReport.value.sites || []
    if (!sites.length) return signinTodayRows.value
    return sites.map(s => ({
      site_id: s.site_id,
      site_name: s.site_name || s.domain || String(s.site_id),
      sign: !!s.sign,
      login: !!s.login,
      signin: s.signin || null,
      loginResult: s.login_result || null,
    }))
  })
  // 今日各状态计数 + 过滤后的列表（失败优先，几十个站也一眼看出问题）
  const signinTodayCounts = computed(() => {
    const c = { all: 0, ok: 0, fail: 0, pending: 0, skip: 0 }
    ;(signinReportTodayRows.value || []).forEach(r => {
      const s = _signinStatus(r.signin, r.loginResult, true, r.sign, r.login)
      c.all++
      if (SIGNIN_FAIL_STATUS.includes(s)) c.fail++
      else c[s] = (c[s] || 0) + 1
    })
    return c
  })
  const signinFilterItems = computed(() => {
    const c = signinTodayCounts.value
    // ★ 19.12.89：失败 / 待执行 / 跳过都只在「有」的时候出现 —— 常驻两个 0 的筛选项，
    //   点了是空列表，白占一行。全部 / 成功常驻（保证至少有得点）。
    const out = [{ value: 'all', label: `全部 ${c.all || 0}`, color: 'primary' }]
    if (c.fail) out.push({ value: 'fail', label: `失败 ${c.fail}`, color: 'error' })
    if (c.pending) out.push({ value: 'pending', label: `待执行 ${c.pending}`, color: 'warning' })
    // ★ 跳过以前没有出口：16 站里 1 个跳过，chip 只剩 15，用户找不到那一个
    if (c.skip) out.push({ value: 'skip', label: `插件管不了 ${c.skip}`, color: undefined })
    out.push({ value: 'ok', label: `成功 ${c.ok || 0}`, color: 'success' })
    return out
  })
  // 全部行（带状态 / 文案，未过滤未排序）—— 弹窗「待处理」区要用它，避免受 tab 过滤影响
  const signinRowsAll = computed(() =>
    (signinReportTodayRows.value || []).map(r => {
      const status = _signinStatus(r.signin, r.loginResult, true, r.sign, r.login)
      const pairs = _signinWant(r)
      const rt = (signinReport.value.retry || {})[String(r.site_id)]
      const fails = pairs.filter(([, x]) => x && !x.ok && !x.skipped)
      let msg
      if (fails.length) {
        msg = fails.map(([k, x]) => `${k} ✗ ${x.message || ''}`.trim()).join(' · ')
      } else {
        // 全成功 / 待执行：只给简短标记，几十个站也不刷屏（失败才展开原因）
        msg = pairs.map(([k, x]) => (x ? `${k} ${x.ok ? '✓' : (x.na ? '不支持' : (x.skipped ? '跳过' : '✗'))}` : `${k} ⏳`)).join(' · ')
      }
      return {
        ...r,
        status,
        msg: SIGNIN_FAIL_STATUS.includes(status) && rt ? `${msg} · ${rt.next_at} 重试` : msg,
        // ★ 19.12.89：失败原因单独抛出，供弹窗展开显示（原来只能挤在一行 msg 里被省略号切掉）
        reasons: fails.map(([k, x]) => ({ kind: k, message: String(x.message || ''), na: !!x.na })),
        retry_at: rt ? String(rt.next_at || '') : '',
        // 整站都「不支持」→ 属于「插件管不了」，不是失败
        all_na: pairs.length > 0 && pairs.every(([, x]) => x && x.na),
      }
    })
  )
  const signinTodayList = computed(() => {
    const ord = SIGNIN_ORDER
    const rank = s => (ord[s] == null ? 9 : ord[s])
    const q = String(signinSearch.value || '').trim().toLowerCase()
    return signinRowsAll.value
      .filter(r => !q || String(r.site_name || '').toLowerCase().includes(q))
      .filter(r => signinFilter.value === 'all' || (signinFilter.value === 'fail' ? SIGNIN_FAIL_STATUS.includes(r.status) : r.status === signinFilter.value))
      .sort((a, b) => (rank(a.status) - rank(b.status)) || String(a.site_name || '').localeCompare(String(b.site_name || '')))
  })
  // 今天要人动手的：失败 / 待执行 / 插件管不了 —— 「今日已完成」以外的全部
  const signinPendingRows = computed(() => {
    const ord = SIGNIN_ORDER
    const rank = s => (ord[s] == null ? 9 : ord[s])
    return signinRowsAll.value
      .filter(r => r.status !== 'ok')
      .sort((a, b) => (rank(a.status) - rank(b.status)) || String(a.site_name || '').localeCompare(String(b.site_name || '')))
  })
  // 今天已完成的（不受 tab 过滤影响，弹窗默认只列这个）
  const signinDoneRows = computed(() => signinRowsAll.value.filter(r => r.status === 'ok'))
  // ★ 19.12.89 弹窗头摘要用：跳过的站数（现在四个 chip 里没有它的位置 → 16 显示成 15）
  const signinSkipCount = computed(() => {
    const c = signinTodayCounts.value || {}
    return Number(c.skip || 0)
  })
  // 近 7 天矩阵：行=站点、列=日期（点阵）；异常在前，支持几十个站滚动查看
  const signinKeepalive = computed(() => ((signinReport.value.keepalive || {}).sites || []))
  const signinKeepaliveNote = computed(() => {
    const rows = signinKeepalive.value || []
    return rows.length ? String(rows[0].rule_note || '') : ''
  })

  const signinMatrix = computed(() => {
    const records = signinReport.value.records || []
    const today = signinReport.value.today || ''
    // 近 7 天窗口：以今天为锚，缺记录的日期补空点（列固定 7 个，方便竖着对比）
    const anchor = today || records.map(r => r.date).sort().slice(-1)[0] || ''
    const dates = []
    if (anchor) {
      const base = new Date(`${anchor}T00:00:00`)
      for (let i = 0; i < 7; i += 1) {
        const d = new Date(base)
        d.setDate(base.getDate() - i)
        dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
      }
    }
    const map = new Map()
    const ensure = (sid, name) => {
      const k = String(sid)
      if (!map.has(k)) map.set(k, { sid: k, name: name || k, cells: {} })
      else if (name) map.get(k).name = name
      return map.get(k)
    }
    // 先按设置里的勾选取好「该看哪几项」（登录站不算签到）
    const flags = new Map()
    ;(signinReport.value.sites || []).forEach(s => {
      ensure(s.site_id, s.site_name || s.domain || String(s.site_id))
      flags.set(String(s.site_id), { sign: !!s.sign, login: !!s.login })
    })
    records.forEach(r => {
      Object.keys(r.sites || {}).forEach(sid => {
        const rec = r.sites[sid] || {}
        const row = ensure(sid, rec.site_name)
        const f = flags.get(String(sid)) || {}
        row.cells[r.date] = _signinStatus(rec.sign, rec.login, false, f.sign, f.login)
        if (rec.sign) row.sign = true
        if (rec.login) row.login = true
      })
    })
    ;(signinReport.value.sites || []).forEach(s => {
      const row = ensure(s.site_id, s.site_name)
      row.cells[today] = _signinStatus(s.signin, s.login_result, true, s.sign, s.login)
      row.sign = !!s.sign
      row.login = !!s.login
    })
    const rows = [...map.values()].map(row => {
      const cells = dates.map(d => ({ date: d, status: row.cells[d] || 'none' }))
      const failIdx = cells.findIndex(c => c.status === 'fail')
      return { ...row, cells, failIdx, todayStatus: cells.length ? cells[0].status : 'none' }
    })
    const rank = r => (r.todayStatus === 'fail' ? 0 : r.todayStatus === 'pending' ? 1 : r.failIdx >= 0 ? 2 : 3)
    rows.sort((a, b) => (rank(a) - rank(b)) || (a.failIdx - b.failIdx) || String(a.name).localeCompare(String(b.name)))
    // ★ 19.12.89 口径修正：原来只认 'fail'（签到+登录都失败），signfail / loginfail
    //   既不计成功也不计失败 → 从分子分母里凭空消失，成功率虚高。
    //   实测 11-13 March 登录失败（HTTP 521）被吞，页面显示 100%，真实 104/105 = 99%。
    const stats = { ok: 0, fail: 0, skip: 0, none: 0, total: 0 }
    rows.forEach(r => r.cells.forEach(c => {
      stats.total++
      if (c.status === 'ok') stats.ok++
      else if (SIGNIN_FAIL_STATUS.includes(c.status)) stats.fail++
      else if (c.status === 'skip') stats.skip++
      else stats.none++
    }))
    return { dates, rows, stats }
  })
  // 近 7 天成功率：分母只含「有结果的格」（成功 + 三种失败），跳过/无记录单独报
  const signinRate = computed(() => {
    const s = (signinMatrix.value.stats || {})
    const ok = Number(s.ok || 0)
    const fail = Number(s.fail || 0)
    const denom = ok + fail
    return {
      ok,
      fail,
      skip: Number(s.skip || 0),
      none: Number(s.none || 0),
      total: Number(s.total || 0),
      pct: denom ? Math.round((ok * 100) / denom) : null,
    }
  })

  return { siteSelectItems, signinRunning, runSigninNow, signinOpen, signinReport, signinReportLoading, loadSigninReport, openSignin, signinFilter, signinSearch, signinStatusText, signinDateLabel, signinReportTodayRows, signinTodayCounts, signinFilterItems, signinTodayList, signinRowsAll, signinPendingRows, signinDoneRows, signinSkipCount, signinRate, signinKeepalive, signinKeepaliveNote, signinMatrix }
}
