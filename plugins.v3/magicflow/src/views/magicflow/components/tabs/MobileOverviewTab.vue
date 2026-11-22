<script setup>
// MagicFlow 前端 · 手机端任务概览 Tab（★ 19.15.0 视觉层重写，对齐 task-detail-design.html viewOverview）
// 手机端（≤959px）专用：6 格关键指标（本任务 · 站点分层）+ 本轮决策 + 趋势 + 站点数据 + 最近一次运行。
// 数据向下（props）、事件向上（emit）；与桌面 OverviewTab 同 props 契约（index.vue 按 isNarrow 二选一渲染）。
// ★ 本轮只重写视图层：数据来源、props 契约、emit 一律不动。唯一新增 = sparkBars()，
//   把已有趋势 path（"M0,20 L8,18 …"）解析成柱高，忠实还原设计稿的柱状 spark（原为折线）。
import { computed } from 'vue'
import { formatBonus, formatBytes, formatDateTime, formatDurationSeconds, runStatusText } from '../../../../utils'

// ★ 19.16.3 趋势可读性重做。
// 原来直接拿 path 的 y 画柱，有两个硬伤：
//   ① path 的 y 已在后端归一化到 3~23（min→23、max→3），**任何波动都被拉成满幅** ——
//      实测站点时魔 72h 波动仅 0.07%~0.18%，画出来却是满屏跳动，看着像噪点不像趋势；
//   ② 72 个采样点塞进 366px，每根柱约 1px 宽，高度差根本看不见。
// 现在：按真实量级（s.min / s.max）判定「是否真的在动」，并降采样到 ≤24 根柱。
// 平稳就老实说平稳（并给真实波动百分比），不靠放大抖动假装有趋势。
const TREND_MAX_BARS = 24
const props = defineProps({
  selectedTask: { type: Object, default: () => ({}) },
  taskIsBrush: { type: Boolean, default: false },
  taskConfig: { type: Object, default: () => ({}) },
  brushSeedDays: { type: [Number, String], default: 0 },
  goalFactText: { type: String, default: '' },
  selectedState: { type: Object, default: () => ({}) },
  detailStats: { type: Object, default: () => ({}) },
  siteAccount: { type: Object, default: () => ({}) },
  siteUser: { type: Object, default: () => ({}) },
  siteLiveLevel: { type: String, default: '' },
  siteLiveRates: { type: Object, default: () => ({}) },
  siteLiveCfg: { type: Object, default: () => ({}) },
  siteLiveAlerts: { type: Array, default: () => [] },
  decision: { type: Object, default: () => ({}) },
  decisionCapText: { type: [String, Number], default: '' },
  decisionReasons: { type: Array, default: () => [] },
  trendCards: { type: Array, default: () => [] },
  // trendMain 桌面大图折线在手机端不渲染，保留 prop 与父绑定契约一致
  trendMain: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['open-entry'])

// 小数位：做种数是整数，其余保留两位
function trendDigits(key) {
  return key === 'seeds' ? 0 : 2
}

// 趋势卡的主图数据。
// ★ 19.16.3 关键取舍：「趋势」这张卡要回答「什么在变」，所以不再固定画第一项 ——
//   逐项算真实波动率（用 s.min/s.max，path 的 y 已被归一化不可信），挑波动最明显的一项做主图。
//   全都不足 2% 时退回第一项（时魔）并明说「基本平稳」，不靠放大抖动假装有趋势。
const TREND_FLAT_PCT = 1 // 波动 <1% 视为平稳
const TREND_PICK_PCT = 2 // 有任一项波动 ≥2% 就优先画它
const trendSpark = computed(() => {
  const cards = props.trendCards || []

  let best = null
  let first = null
  for (const c of cards) {
    const s = c && c.s
    if (!s || !s.path) continue
    const lo = Number(s.min)
    const hi = Number(s.max)
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) continue
    const base = Math.max(Math.abs(lo), Math.abs(hi), 1e-9)
    const rel = (hi - lo) / base
    const cand = { c, s, lo, hi, rel }
    if (!first) first = cand
    if (!best || rel > best.rel) best = cand
  }
  const pick = best && best.rel >= TREND_PICK_PCT / 100 ? best : first
  if (!pick) return null

  const { c, s, lo, hi, rel } = pick

  // 1) path → y 序列（视口 100×26，y 越小越高）
  const pts = String(s.path).match(/-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?/g) || []
  const ys = pts.map((p) => Number(p.split(',')[1])).filter((n) => Number.isFinite(n))
  if (ys.length < 2) return null

  // 2) 降采样：等分成 ≤24 组，每组取末值（末值保留台阶走势，取均值会把台阶抹平）
  let picked = ys
  if (ys.length > TREND_MAX_BARS) {
    picked = []
    for (let i = 0; i < TREND_MAX_BARS; i++) {
      const end = Math.round(((i + 1) * ys.length) / TREND_MAX_BARS)
      picked.push(ys[Math.max(end - 1, 0)])
    }
  }

  // 3) 平稳态不画柱（一排矮方块像坏图），改画一条持平基线
  const flat = rel < TREND_FLAT_PCT / 100
  const digits = trendDigits(c.key)
  const max = Math.max(...picked)
  const min = Math.min(...picked)
  const span = max - min
  const bars = flat
    ? []
    : picked.map((y) => Math.round(30 + ((max - y) / span) * 70)) // 30~100%，设计稿口径

  return {
    key: c.key,
    label: c.label,
    unit: c.unit || '',
    lo,
    hi,
    feet: `低 ${Number(lo).toFixed(digits)}${c.unit || ''} · 高 ${Number(hi).toFixed(digits)}${c.unit || ''}`,
    relPct: (rel * 100).toFixed(rel < 0.01 ? 2 : 1),
    flat,
    bars,
    points: ys.length,
  }
})
</script>

<template>
  <div class="mob-overview">
    <div class="secttl">
      <h3>关键指标</h3>
      <small>本任务 · 站点分层</small>
    </div>

    <!-- 6 格：2 列 × 3 行（设计稿 statgrid；2 列宽度够，副标题不再折行） -->
    <div class="statgrid">
      <div class="stat accent">
        <span class="k">托管种子</span>
        <span class="v">{{ selectedTask.seeding_count || 0 }}</span>
        <span class="f">做种中 {{ selectedTask.active_seeding_count || 0 }} · 下载 {{ selectedTask.downloading_count || 0 }} · 暂停 {{ selectedTask.paused_count || 0 }}</span>
      </div>
      <div class="stat">
        <span class="k">做种中</span>
        <span class="v">{{ selectedTask.active_seeding_count || 0 }}</span>
        <span class="f">本轮新增 {{ detailStats.last_added || 0 }} / 复用 {{ detailStats.last_reused || 0 }}</span>
      </div>
      <div class="stat">
        <span class="k">本任务上传</span>
        <span class="v">{{ formatBytes(selectedTask.task_uploaded || 0) }}</span>
        <span class="f">下载器累计 · {{ selectedTask.task_upload_active || 0 }} 个有上传</span>
      </div>
      <div class="stat">
        <span class="k">站点上报时魔</span>
        <span class="v">{{ selectedTask.site_bonus_ok ? formatBonus(selectedTask.site_bonus_per_hour) : '取数中…' }}</span>
        <span class="f">站点实时值 / h</span>
      </div>
      <div class="stat">
        <span class="k">站点当前魔力</span>
        <span class="v">{{ Number(selectedTask.site_current_bonus || 0).toFixed(0) }}</span>
        <span class="f">该站实时存量</span>
      </div>
      <div class="stat">
        <span class="k">上次运行</span>
        <span class="v">{{ detailStats.last_added || 0 }} / {{ detailStats.last_reused || 0 }} / {{ detailStats.last_deleted || 0 }}</span>
        <span class="f">新增 / 复用 / 删除</span>
      </div>
    </div>

    <!-- 本轮决策（最近一轮闸门判定与淘汰口径） -->
    <div v-if="decision.at_cap !== undefined" class="panelbox">
      <div class="ph">
        <b>本轮决策</b>
        <span>{{ decision.at_cap ? '已达上限 · 可换种' : '未达上限 · 不做低效换种' }}</span>
      </div>
      <div class="row"><span>额度</span><b class="ac">{{ decisionCapText || (decision.at_cap ? '已达上限' : '未达上限') }}</b></div>
      <div class="row">
        <span>筛选链</span>
        <b>候选 {{ decision.candidates ?? '—' }} → 保护 {{ decision.protected ?? '—' }} → 留 {{ decision.keep ?? '—' }} → 删 {{ decision.to_delete ?? '—' }} → 实删 {{ decision.deleted ?? '—' }}</b>
      </div>
      <div class="row"><span>门槛</span><b>低效 {{ decision.threshold ?? '—' }}/h · 零魔淘汰 {{ decision.zero_bonus_delete ? '开' : '关' }}</b></div>
      <div v-if="decisionReasons.length" class="row">
        <span>命中</span>
        <b class="rows-chips">
          <span v-for="r in decisionReasons" :key="r.label" class="pill">{{ r.label }} ×{{ r.count }}</span>
        </b>
      </div>
    </div>

    <!-- 趋势：逐项数值 + 主项柱状走势（★ 19.16.3：降采样到 ≤24 根、按真实波动判平稳） -->
    <div v-if="trendCards.length" class="panelbox">
      <div class="ph"><b>趋势</b><span>近 72 小时 · 每小时采样</span></div>
      <!-- 图对应哪一行就点亮哪一行的标签（趋势图会自动挑波动最明显的那项） -->
      <div v-for="c in trendCards" :key="c.key" class="row" :class="{ 'is-graphed': trendSpark && trendSpark.key === c.key }">
        <span>{{ c.label }}</span>
        <b class="ac">
          {{ Number(c.s.last).toFixed(trendDigits(c.key)) }}{{ c.unit }}
          <em :class="c.s.good ? 'up' : 'down'">{{ c.s.delta >= 0 ? '▲' : '▼' }}{{ Math.abs(c.s.delta).toFixed(1) }}%</em>
        </b>
      </div>
      <template v-if="trendSpark">
        <div class="sparkmeta">
          <span>{{ trendSpark.label }}走势 · {{ trendSpark.points }} 点</span>
          <em v-if="trendSpark.flat">72h 基本平稳 · 波动 {{ trendSpark.relPct }}%</em>
          <em v-else>{{ trendSpark.feet }} · 波动 {{ trendSpark.relPct }}%</em>
        </div>
        <!-- 平稳：一条持平基线（一排矮方块会被当成图坏了）；有起伏：柱状图 -->
        <div v-if="trendSpark.flat" class="sparkflat"><i></i></div>
        <div v-else class="spark">
          <i v-for="(h, i) in trendSpark.bars" :key="i" :style="{ height: h + '%' }"></i>
        </div>
      </template>
    </div>

    <!-- 站点数据（魔流直连 · 实时采样） -->
    <div class="panelbox">
      <div class="ph">
        <b>站点数据</b>
        <span>
          <template v-if="siteAccount.source === 'live'">魔流直连 · 采样于 {{ siteAccount.sampledAt || '—' }}</template>
          <template v-else-if="siteAccount.source === 'mp'">MP 快照{{ siteUser.updated_at ? ` · ${siteUser.updated_at}` : '' }}</template>
          <template v-else>等待站点回填</template>
        </span>
      </div>
      <div class="row"><span>上传量</span><b class="ac">{{ siteAccount.ok ? formatBytes(siteAccount.upload || 0) : '—' }}</b></div>
      <div class="row"><span>下载量</span><b>{{ siteAccount.ok ? formatBytes(siteAccount.download || 0) : '—' }}</b></div>
      <div class="row"><span>分享率</span><b class="ac">{{ siteAccount.ok && siteAccount.ratio != null ? Number(siteAccount.ratio).toFixed(3) : '—' }}</b></div>
      <div class="row"><span>做种数 / 下载数</span><b>{{ siteAccount.ok ? `${siteAccount.seeding ?? '—'} / ${siteAccount.leeching ?? '—'}` : '—' }}</b></div>
      <div v-if="siteAccount.seeding_size" class="row"><span>做种体积</span><b>{{ formatBytes(siteAccount.seeding_size) }}</b></div>
      <div class="row"><span>上传速率</span><b>{{ siteLiveRates.ok ? `${Number(siteLiveRates.up_mb_min || 0).toFixed(1)} MB/分` : '—' }}</b></div>
      <div class="row"><span>下载速率</span><b>{{ siteLiveRates.ok ? `${Number(siteLiveRates.down_mb_min || 0).toFixed(1)} MB/分` : '—' }}</b></div>
      <div class="row">
        <span>站点魔力</span>
        <b>{{ siteAccount.ok && siteAccount.bonus != null ? Number(siteAccount.bonus).toFixed(2) : '—' }}{{ siteAccount.bonus_per_hour != null ? ` · ${Number(siteAccount.bonus_per_hour).toFixed(2)}/h` : '' }}</b>
      </div>
      <div v-for="(alert, idx) in siteLiveAlerts" :key="`${alert.kind}-${idx}`" class="alert" :class="`alert--${alert.level || 'info'}`">{{ alert.text }}</div>
    </div>

    <!-- 最近一次运行（不重复放跳转：页签栏可直达诊断） -->
    <div class="panelbox">
      <div class="ph">
        <b>最近一次运行</b>
        <span>{{ detailStats.last_run_at ? `${formatDateTime(detailStats.last_run_at)} · ${runStatusText(detailStats.last_run_status)}` : '暂无运行记录' }}</span>
      </div>
      <div class="row">
        <span>本次状态</span>
        <b :class="detailStats.last_error ? 'bad' : 'ac'">{{ detailStats.last_error ? '失败' : runStatusText(detailStats.last_run_status) }}</b>
      </div>
      <div class="row"><span>本次耗时</span><b>{{ formatDurationSeconds(detailStats.last_run_duration) }}</b></div>
      <div class="row"><span>本次新增 / 复用</span><b>{{ detailStats.last_added || 0 }} / {{ detailStats.last_reused || 0 }}</b></div>
      <div class="row"><span>本次删除</span><b>{{ detailStats.last_deleted || 0 }}</b></div>
      <div class="row"><span>托管 / 受保护</span><b>{{ detailStats.last_kept || 0 }} / {{ detailStats.protected_count || 0 }}</b></div>
      <div v-if="detailStats.last_run_reason" class="hint">本轮说明：{{ detailStats.last_run_reason }}</div>
      <div v-if="detailStats.last_error" class="hint hint--bad">{{ detailStats.last_error }}</div>
    </div>
  </div>
</template>

<style scoped>
/* ══════════════════════════════════════════════════════════════════════════════
   手机端任务概览（★ 19.15.0 视觉层按设计稿 viewOverview 重写）
   设计稿口径：2 列指标格（18px 值 + 9.5px 脚注）、panelbox 事实表（11px 行）、
   柱状 spark（34px 高）、无底部跳转。
   ══════════════════════════════════════════════════════════════════════════════ */
.mob-overview {
  --line: rgba(255, 255, 255, 0.07);
  --dim: #6f7488;
  --purple: #8b7cf6;
  --green: #3ddc97;
  --red: #ff6b7a;
  display: flex;
  flex-direction: column;
}

.secttl { display: flex; align-items: baseline; justify-content: space-between; margin: 2px 0 10px; }
.secttl h3 { font-size: 13px; font-weight: 700; }
.secttl small { font-size: 10px; color: var(--dim); }

/* ── 指标宫格：2 列 ── */
.statgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.stat {
  min-width: 0;
  padding: 11px 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
}
.stat .k { display: block; font-size: 10px; color: #7d8296; }
.stat .v { display: block; margin: 3px 0 4px; font-size: 18px; font-weight: 800; color: #e8e9f0; letter-spacing: 0.2px; }
.stat .f { display: block; font-size: 9.5px; line-height: 1.5; color: var(--dim); }
.stat.accent {
  background: linear-gradient(140deg, rgba(139, 124, 246, 0.18), rgba(139, 124, 246, 0.04));
  border-color: rgba(139, 124, 246, 0.4);
}
.stat.accent .v { color: #cfc6ff; }

/* ── 面板 + 事实表 ── */
.panelbox {
  padding: 13px;
  margin-bottom: 12px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
}
.ph { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.ph b { font-size: 12.5px; font-weight: 700; flex: none; }
.ph span { font-size: 9.5px; color: var(--dim); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row {
  display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  font-size: 11px; padding: 7px 0; color: #b9bdcf;
  border-top: 1px solid var(--line);
}
.row:first-of-type { border-top: 0; }
.row b { color: #e8e9f0; font-weight: 650; text-align: right; }
.row b.ac { color: #cfc6ff; }
.row b.bad { color: #ff9aa5; }
.rows-chips { display: inline-flex; flex-wrap: wrap; gap: 5px; justify-content: flex-end; }
.pill {
  display: inline-block; font-size: 9.5px; padding: 3px 8px; border-radius: 20px;
  background: rgba(255, 107, 122, 0.14); color: #ff9aa5; border: 1px solid rgba(255, 107, 122, 0.28);
  font-weight: 600;
}

/* ── 趋势柱（★ 19.16.3：图上标归属与真实高低值；平稳态柱子压暗，明确"这就是平的"） ── */
.sparkmeta {
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
  margin-top: 11px; font-size: 9.5px; color: var(--dim);
}
.sparkmeta span { color: #a9aec2; font-weight: 600; flex: none; }
.sparkmeta em { font-style: normal; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.spark { display: flex; align-items: flex-end; gap: 2px; height: 34px; margin-top: 7px; }
.spark i {
  flex: 1; min-width: 0; display: block; border-radius: 2px 2px 0 0;
  background: linear-gradient(180deg, rgba(139, 124, 246, 0.8), rgba(139, 124, 246, 0.15));
}
/* 平稳态：一条居中基线，明确「72h 就是平的」，不用矮方块假装有波动 */
.sparkflat { display: flex; align-items: center; height: 34px; margin-top: 7px; }
.sparkflat i {
  display: block; width: 100%; height: 3px; border-radius: 2px;
  background: linear-gradient(90deg, rgba(139, 124, 246, 0.12), rgba(139, 124, 246, 0.5), rgba(139, 124, 246, 0.12));
}
/* 趋势图对应的那一行：标签点亮，避免「不知道图在画哪一项」 */
.row.is-graphed > span { color: #cfc6ff; }
.row em { font-style: normal; font-size: 9.5px; margin-left: 4px; }
.row em.up { color: var(--green); }
.row em.down { color: #ff9aa5; }

.alert {
  margin-top: 8px; padding: 7px 9px; border-radius: 8px; font-size: 9.5px; line-height: 1.55;
  background: rgba(139, 124, 246, 0.06); border-left: 2px solid rgba(139, 124, 246, 0.45); color: #b9bdcf;
}
.alert--warn { background: rgba(240, 182, 76, 0.08); border-left-color: rgba(240, 182, 76, 0.6); color: #f5cd84; }
.alert--error { background: rgba(255, 107, 122, 0.08); border-left-color: rgba(255, 107, 122, 0.6); color: #ff9aa5; }

.hint {
  margin-top: 9px; padding: 7px 9px; border-radius: 8px; font-size: 9.5px; line-height: 1.55;
  color: #b9bdcf; background: rgba(139, 124, 246, 0.06);
  border-left: 2px solid rgba(139, 124, 246, 0.45);
}
.hint--bad { background: rgba(255, 107, 122, 0.08); border-left-color: rgba(255, 107, 122, 0.6); color: #ff9aa5; }
</style>
