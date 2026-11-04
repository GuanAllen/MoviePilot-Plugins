// OverviewHome —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './OverviewHome.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$1,
  createCommentVNode: _createCommentVNode$1,
  createElementBlock: _createElementBlock$1,
  createElementVNode: _createElementVNode$2,
  createTextVNode: _createTextVNode$2,
  createVNode: _createVNode$2,
  normalizeClass: _normalizeClass$1,
  openBlock: _openBlock$2,
  renderList: _renderList$1,
  resolveComponent: _resolveComponent$2,
  toDisplayString: _toDisplayString$2,
  unref: _unref$1,
  normalizeStyle: _normalizeStyle
} = __vue

import { currencyOfMany } from '../composables/useCurrency.js'
import { formatBonus } from '../../../utils.js'

const _hoisted_1$1 = { class: "mfh" };
const _hoisted_2$1 = { class: "mfh__main" };
const _hoisted_3$1 = { class: "mfh__head" };
const _hoisted_4$1 = { class: "mfh__head-text" };
const _hoisted_5$1 = {
  key: 0,
  class: "mfh__dim"
};
const _hoisted_6$1 = { class: "mfh__chips" };
const _hoisted_7$1 = {
  key: 0,
  class: "mfh-chip__num"
};
const _hoisted_8$1 = { class: "mfh__kpis" };
const _hoisted_9$1 = { class: "mfh-kpi" };
const _hoisted_10$1 = { class: "mfh-kpi__row" };
const _hoisted_11$1 = { class: "mfh-kpi__value" };
const _hoisted_12$1 = {
  class: "mfh-kpi__spark",
  viewBox: "0 0 170 36",
  preserveAspectRatio: "none",
  "aria-hidden": "true"
};
const _hoisted_13$1 = ["d"];
const _hoisted_14$1 = ["d"];
const _hoisted_15$1 = { class: "mfh-kpi__foot" };
const _hoisted_16$1 = { class: "mfh-kpi" };
const _hoisted_17$1 = { class: "mfh-kpi__row" };
const _hoisted_18$1 = { class: "mfh-kpi__value" };
const _hoisted_19$1 = {
  class: "mfh-kpi__spark",
  viewBox: "0 0 170 36",
  preserveAspectRatio: "none",
  "aria-hidden": "true"
};
const _hoisted_20$1 = ["d"];
const _hoisted_21$1 = ["d"];
const _hoisted_22$1 = { class: "mfh-kpi__foot" };
const _hoisted_23$1 = { class: "mfh-kpi" };
const _hoisted_24$1 = { class: "mfh-kpi__label" };
const _hoisted_25$1 = { class: "mfh-kpi__row" };
const _hoisted_26$1 = { class: "mfh-kpi__value" };
const _hoisted_27$1 = {
  class: "mfh-kpi__spark",
  viewBox: "0 0 170 36",
  preserveAspectRatio: "none",
  "aria-hidden": "true"
};
const _hoisted_28$1 = ["d"];
const _hoisted_29$1 = ["d"];
const _hoisted_30$1 = { class: "mfh-kpi" };
const _hoisted_31$1 = { class: "mfh-kpi__row" };
const _hoisted_32$1 = { class: "mfh-kpi__value" };
const _hoisted_33$1 = { class: "mfh-kpi__foot" };
const _hoisted_34$1 = { class: "mfh-panel" };
const _hoisted_35$1 = { class: "mfh-panel__head" };
const _hoisted_36$1 = { class: "mfh-panel__sub" };
const _hoisted_37$1 = { class: "mfh-matrix" };
const _hoisted_38$1 = ["onClick"];
const _hoisted_39$1 = { class: "mfh-matrix__name" };
const _hoisted_40$1 = { class: "mfh-matrix__label" };
const _hoisted_41$1 = { class: "mfh-matrix__num" };
const _hoisted_42$1 = { class: "mfh-matrix__num" };
const _hoisted_43 = {
  key: 0,
  class: "mfh-matrix__empty"
};
const _hoisted_44 = { class: "mfh-panel mfh-panel--chart" };
const _hoisted_45 = { class: "mfh-panel__head" };
const _hoisted_46 = { class: "mfh-legend" };
const _hoisted_47 = {
  key: 0,
  class: "mfh-legend__item"
};
const _hoisted_48 = {
  key: 0,
  class: "mfh-chart"
};
const _hoisted_49 = { class: "mfh-chart__yaxis" };
const _hoisted_50 = { class: "mfh-chart__plot" };
const _hoisted_51 = {
  viewBox: "0 0 900 168",
  preserveAspectRatio: "none",
  class: "mfh-chart__svg",
  "aria-hidden": "true"
};
const _hoisted_52 = ["y1", "y2"];
const _hoisted_53 = ["d"];
const _hoisted_54 = ["d"];
const _hoisted_55 = ["d"];
const _hoisted_56 = {
  key: 1,
  class: "mfh-chart__empty"
};
const _hoisted_57 = { class: "mfh__side" };
const _hoisted_58 = { class: "mfh-panel mfh-panel--side" };
const _hoisted_59 = { class: "mfh-panel__head" };
const _hoisted_60 = { class: "mfh-ops" };
const _hoisted_61 = {
  key: 0,
  class: "mfh-ops__empty"
};
const _hoisted_62 = { class: "mfh-ops__body" };
const _hoisted_63 = { class: "mfh-ops__title" };
const _hoisted_64 = { class: "mfh-ops__time" };
const _hoisted_65 = { class: "mfh-panel mfh-panel--side" };
const _hoisted_66 = { class: "mfh-panel__head" };
const _hoisted_67 = { class: "mfh-mon" };
const _hoisted_68 = { class: "mfh-mon__label" };
const _hoisted_69 = { class: "mfh-mon__label" };
const _hoisted_70 = { class: "mfh-mon__value" };
const _hoisted_71 = { class: "mfh-mon__bar" };
const _hoisted_72 = { class: "mfh-mon__label" };
const _hoisted_73 = { class: "mfh-mon__value" };
const _hoisted_74 = { class: "mfh-panel mfh-panel--side" };
const _hoisted_75 = { class: "mfh-panel__head" };
const _hoisted_76 = { class: "mfh-quick" };
const _hoisted_77 = ["onClick"];
const _hoisted_78 = { key: 0 };

const {computed: computed$m} = __vue;

const CHART_H = 168;
const CHART_W = 900;

const _sfc_main$2 = {
  __name: 'OverviewHome',
  props: {
  summary: { type: Object, default: () => ({}) },
  tasks: { type: Array, default: () => [] },
  // 全站趋势原始 data：{ hours, keep, series:{ 'task:xxx':[{t,bonus,seeds,gb,reuse_gb,bonus_now}] }, names }
  trend: { type: Object, default: () => ({}) },
  health: { type: Object, default: () => ({}) },
  healthLabel: { type: String, default: '' },
  healthColor: { type: String, default: '' },
  healthBadge: { type: Number, default: 0 },
  bills: { type: Array, default: () => [] }, // H&R 账单（hrBills）
  ops: { type: Array, default: () => [] }, // 操作记录（最近 N 条）
  notifyCount: { type: Number, default: 0 },
  pages: { type: Array, default: () => [] }, // 功能中心快捷入口 [{key,label,icon,hint}]
  now: { type: Number, default: () => Date.now() },
  loading: { type: Boolean, default: false },
},
  emits: [
  'open-task',
  'open-ceiling',
  'open-hr',
  'open-health',
  'open-ops',
  'open-page',
  'create-task',
  'refresh',
],
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 主页「整体概览」
// 对应设计稿 Ardot 740112280764561 帧 1（1440×900 · 2:1）。
// 口径：**全站聚合**，不是单任务。点任务矩阵任意行 → 下钻单任务详情（emit open-task）。
//
// 设计原则（沿用项目既有约定，见 docs/DESIGN-CURRENT.md §8）：
//   - 不硬编码颜色：一律 var(--v-theme-*) / rgba(var(--v-theme-on-surface), α)，浅色/深色主题自动适配。
//   - 数据向下、事件向上；本组件不直接调 api、不改父状态。
//   - 所有数值缺数据时降级为「—」或 0，不抛错、不空白。
const props = __props;

const emit = __emit;

// ── 全局汇总 ────────────────────────────────────────────────
const s = computed$m(() => props.summary || {});
const seedingCount = computed$m(() => Number(s.value.seeding_count || 0));
const bonusPerHour = computed$m(() => Number(s.value.bonus_per_hour || 0));
const currentBonus = computed$m(() => Number(s.value.current_bonus || 0));
// 各站货币名一致才用站点的叫法，否则「魔力值」（各站货币互不通兑，不能假装同名）
const currencyLabel = computed$m(() => currencyOfMany(props.tasks));
const ceilingPct = computed$m(() => Number(s.value.ceiling_pct || 0));
const taskTotal = computed$m(() => Number(s.value.total_tasks || props.tasks.length || 0));
const runningCount = computed$m(() => Number(s.value.running_tasks || 0));
computed$m(() => Number(s.value.seeding_tasks || 0));
const stoppedCount = computed$m(() => Number(s.value.stopped_tasks || 0));
const activeSeeding = computed$m(() => Number(s.value.active_tasks || 0));

// ── 趋势：把各 task 系列按时间戳聚合成「全站」曲线 ──────────────
// 接口不返回 all: 聚合序列（只有 task:/site:），所以前端求和。
const seriesMap = computed$m(() => props.trend?.series || {});

const hourly = computed$m(() => {
  const buckets = new Map();
  for (const [key, arr] of Object.entries(seriesMap.value)) {
    if (!Array.isArray(arr) || !key.startsWith('task:')) continue
    for (const p of arr) {
      const t = Number(p?.t || 0);
      if (!t) continue
      const cur = buckets.get(t) || { t, bonus: 0, seeds: 0, bonus_now: 0 };
      cur.bonus += Number(p.bonus || 0);
      cur.seeds += Number(p.seeds || 0);
      cur.bonus_now += Number(p.bonus_now || 0);
      buckets.set(t, cur);
    }
  }
  return [...buckets.values()].sort((a, b) => a.t - b.t)
});

// 本周 = 最近 72 点；上周 = 再往前 72 点（接口 keep=168，够画对比虚线）
const thisWeek = computed$m(() => hourly.value.slice(-72));
const prevWeek = computed$m(() => (hourly.value.length > 72 ? hourly.value.slice(-144, -72) : []));

// ── sparkline（KPI 卡右侧的迷你曲线）────────────────────────
function sparkPath(points, pick, w = 170, h = 36) {
  if (!points.length) return { line: '', area: '' }
  const vals = points.map(pick).filter(v => Number.isFinite(v));
  if (!vals.length) return { line: '', area: '' }
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const step = vals.length > 1 ? w / (vals.length - 1) : w;
  const coords = vals.map((v, i) => [i * step, h - ((v - min) / span) * (h - 4) - 2]);
  const line = coords.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const area = `${line} L${w},${h} L0,${h} Z`;
  return { line, area }
}

const sparkSeeds = computed$m(() => sparkPath(thisWeek.value, p => Number(p.seeds || 0)));
const sparkBonus = computed$m(() => sparkPath(thisWeek.value, p => Number(p.bonus || 0)));
const sparkBonusNow = computed$m(() => sparkPath(thisWeek.value, p => Number(p.bonus_now || 0)));

// ── 全站时魔趋势图（本周实线 + 上周虚线）─────────────────────
const chart = computed$m(() => {
  const cur = thisWeek.value;
  const prev = prevWeek.value;
  const all = [...cur, ...prev].map(p => Number(p.bonus || 0)).filter(v => Number.isFinite(v));
  if (!all.length) return null
  const max = Math.max(...all, 1);
  const top = Math.ceil(max / 4) * 4 || 4;
  const toPath = (pts, w) => {
    if (!pts.length) return ''
    const step = pts.length > 1 ? w / (pts.length - 1) : w;
    return pts.map((p, i) => {
      const v = Number(p.bonus || 0);
      const x = i * step;
      const y = CHART_H - (v / top) * CHART_H;
      return `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`
    }).join(' ')
  };
  const lineCur = toPath(cur, CHART_W);
  const linePrev = toPath(prev, CHART_W);
  const areaCur = lineCur ? `${lineCur} L${CHART_W},${CHART_H} L0,${CHART_H} Z` : '';
  const ticks = [1, 0.75, 0.5, 0.25, 0].map(r => ({
    y: CHART_H * (1 - r),
    label: formatTick(top * r),
  }));
  return { lineCur, linePrev, areaCur, ticks, top, hasPrev: !!linePrev }
});

function formatTick(v) {
  const n = Number(v || 0);
  if (n >= 10000) return `${(n / 1000).toFixed(0)}k`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(Math.round(n))
}

// ── 任务矩阵 ────────────────────────────────────────────────
const stateMeta = {
  running: { color: 'success', text: '运行中' },
  seeding: { color: 'primary', text: '做种中' },
  stopped: { color: 'secondary', text: '已停止' },
  disabled: { color: 'secondary', text: '已停用' },
};

function modeKey(t) {
  if (t?.enabled === false) return 'disabled'
  return t?.run_mode || 'running'
}

function rowMeta(t) {
  const k = modeKey(t);
  return stateMeta[k] || stateMeta.running
}

const normalTasks = computed$m(() => (props.tasks || []).filter(t => t && t.task_type !== 'host'));
const hostTasks = computed$m(() => (props.tasks || []).filter(t => t && t.task_type === 'host'));

// 矩阵口径：优先经营任务（刷流/刷魔力）；没有经营任务时（如灰度环境未配站点）
// 回退显示常驻任务，避免整块空白 —— 行上会标「常驻」以示区分。
const fallbackHost = computed$m(() => normalTasks.value.length === 0 && hostTasks.value.length > 0);

const rows = computed$m(() => {
  const list = normalTasks.value.length ? normalTasks.value : hostTasks.value;
  // 设计稿按产出从高到低排列（时魔相同再按种子数）
  return [...list].sort((a, b) => {
    const da = Number(a.site_bonus_per_hour || 0);
    const db = Number(b.site_bonus_per_hour || 0);
    if (db !== da) return db - da
    return Number(b.seeding_count || 0) - Number(a.seeding_count || 0)
  })
});

const hiddenHostCount = computed$m(() => (fallbackHost.value ? 0 : hostTasks.value.length));

function rowBonus(t) {
  if (t?.site_bonus_ok === false) return '—'
  const v = t?.site_bonus_per_hour;
  if (v === null || v === undefined) return '—'
  return formatBonus(v)
}

function rowSubtitle(t) {
  // 回退到常驻任务时（灰度没配站点），标「常驻」区分口径
  if (t?.task_type === 'host') return '常驻任务 · 全站托管'
  const site = t?.site_name || t?.site_domain || '未知站点';
  const kind = t?.task_type === 'brush' ? '刷流' : '刷魔力';
  return `${site} · ${kind}`
}

// ── 上次运行 ────────────────────────────────────────────────
const lastRun = computed$m(() => {
  const runs = (props.ops || []).filter(o => o && o.kind === 'run');
  if (!runs.length) return null
  const o = [...runs].sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0))[0];
  const at = Number(o.created_at || 0) * 1000;
  return {
    ago: at ? relativeTime(at) : '—',
    duration: o.duration ? formatDuration(o.duration) : '—',
    items: Array.isArray(o.items) ? o.items.length : 0,
    state: o.state || '',
    task: o.task_id || '',
  }
});

function relativeTime(ms) {
  const diff = Math.max(0, Number(props.now || Date.now()) - ms);
  const min = Math.floor(diff / 60000);
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`
  return `${Math.floor(hr / 24)} 天前`
}

function formatDuration(sec) {
  const v = Number(sec || 0);
  if (v < 60) return `${v.toFixed(1)}s`
  const m = Math.floor(v / 60);
  const r = Math.round(v % 60);
  return `${m}m${r}s`
}

function opTime(o) {
  const at = Number(o?.created_at || 0) * 1000;
  return at ? relativeTime(at) : '—'
}

function stateDotClass(st) {
  if (st === 'completed') return 'is-ok'
  if (st === 'failed' || st === 'error') return 'is-bad'
  if (st === 'running') return 'is-run'
  return 'is-idle'
}

function opText(o) {
  const it = Array.isArray(o?.items) && o.items.length ? o.items[0] : null;
  const head = it?.title || it?.reason || '—';
  const task = taskName(o?.task_id);
  return task ? `${task} · ${head}` : head
}

const taskNameMap = computed$m(() => {
  const m = {};
  for (const t of props.tasks || []) m[t.id] = t.name;
  return m
});

function taskName(id) {
  return taskNameMap.value[id] || ''
}

const recentOps = computed$m(() =>
  [...(props.ops || [])]
    .sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0))
    .slice(0, 5),
);

// ── 右栏：H&R 临期 ──────────────────────────────────────────
const hrSummary = computed$m(() => {
  const list = props.bills || [];
  if (!list.length) return { count: 0, soonest: null }
  const pending = list.filter(b => !b.completed);
  const pool = pending.length ? pending : list;
  const sorted = [...pool].sort((a, b) => Number(a.remain_hours ?? 1e9) - Number(b.remain_hours ?? 1e9));
  return { count: pool.length, soonest: sorted[0] || null }
});

// ── 状态 chip ───────────────────────────────────────────────
const notifyTotal = computed$m(() => Number(props.notifyCount || 0));

const healthChip = computed$m(() => ({
  label: props.healthLabel || (props.health?.ok === false ? '异常' : '正常'),
  color: props.healthColor || (props.health?.ok === false ? 'error' : 'success'),
}));

const ceilingColor = computed$m(() => (ceilingPct.value >= 85 ? 'error' : ceilingPct.value >= 70 ? 'warning' : 'success'));

const quickPages = computed$m(() => (props.pages || []).slice(0, 3));

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$2("VIcon");

  return (_openBlock$2(), _createElementBlock$1("div", _hoisted_1$1, [
    _createElementVNode$2("div", _hoisted_2$1, [
      _createElementVNode$2("header", _hoisted_3$1, [
        _createElementVNode$2("div", _hoisted_4$1, [
          _cache[12] || (_cache[12] = _createElementVNode$2("h2", null, "整体概览", -1)),
          _createElementVNode$2("p", null, [
            _createTextVNode$2(_toDisplayString$2(taskTotal.value) + " 个任务 · 全站口径 · 每 5 分钟刷新 ", 1),
            (hiddenHostCount.value)
              ? (_openBlock$2(), _createElementBlock$1("span", _hoisted_5$1, "（另有 " + _toDisplayString$2(hiddenHostCount.value) + " 个常驻任务，见功能中心）", 1))
              : _createCommentVNode$1("", true)
          ])
        ]),
        _createElementVNode$2("div", _hoisted_6$1, [
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-chip",
            onClick: _cache[0] || (_cache[0] = $event => (emit('open-health')))
          }, [
            _createElementVNode$2("span", {
              class: _normalizeClass$1(["mfh-chip__dot", `is-${healthChip.value.color}`])
            }, null, 2),
            _createTextVNode$2(" 健康自检 · " + _toDisplayString$2(healthChip.value.label) + " ", 1),
            (__props.healthBadge)
              ? (_openBlock$2(), _createElementBlock$1("span", _hoisted_7$1, _toDisplayString$2(__props.healthBadge), 1))
              : _createCommentVNode$1("", true)
          ]),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-chip",
            onClick: _cache[1] || (_cache[1] = $event => (emit('open-ceiling')))
          }, [
            _createElementVNode$2("span", {
              class: _normalizeClass$1(["mfh-chip__dot", `is-${ceilingColor.value}`])
            }, null, 2),
            _createTextVNode$2(" 站点容量 · " + _toDisplayString$2(ceilingPct.value.toFixed(0)) + "% ", 1)
          ]),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-chip",
            onClick: _cache[2] || (_cache[2] = $event => (emit('open-hr')))
          }, [
            _createElementVNode$2("span", {
              class: _normalizeClass$1(["mfh-chip__dot", hrSummary.value.count ? 'is-warning' : 'is-success'])
            }, null, 2),
            _createTextVNode$2(" H&R · " + _toDisplayString$2(hrSummary.value.count) + " 期 ", 1)
          ]),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-chip",
            onClick: _cache[3] || (_cache[3] = $event => (emit('open-page', 'notify')))
          }, [
            _cache[13] || (_cache[13] = _createElementVNode$2("span", { class: "mfh-chip__dot is-info" }, null, -1)),
            _createTextVNode$2(" 通知 · " + _toDisplayString$2(notifyTotal.value) + " 条 ", 1)
          ])
        ])
      ]),
      _createElementVNode$2("section", _hoisted_8$1, [
        _createElementVNode$2("article", _hoisted_9$1, [
          _cache[15] || (_cache[15] = _createElementVNode$2("div", { class: "mfh-kpi__label" }, [
            _createTextVNode$2("托管种子"),
            _createElementVNode$2("span", { class: "mfh-kpi__scope" }, "· 全站")
          ], -1)),
          _createElementVNode$2("div", _hoisted_10$1, [
            _createElementVNode$2("div", _hoisted_11$1, [
              _createTextVNode$2(_toDisplayString$2(seedingCount.value), 1),
              _cache[14] || (_cache[14] = _createElementVNode$2("span", { class: "mfh-kpi__unit" }, "条", -1))
            ]),
            (_openBlock$2(), _createElementBlock$1("svg", _hoisted_12$1, [
              (sparkSeeds.value.area)
                ? (_openBlock$2(), _createElementBlock$1("path", {
                    key: 0,
                    d: sparkSeeds.value.area,
                    class: "mfh-spark__area is-primary"
                  }, null, 8, _hoisted_13$1))
                : _createCommentVNode$1("", true),
              (sparkSeeds.value.line)
                ? (_openBlock$2(), _createElementBlock$1("path", {
                    key: 1,
                    d: sparkSeeds.value.line,
                    class: "mfh-spark__line is-primary"
                  }, null, 8, _hoisted_14$1))
                : _createCommentVNode$1("", true)
            ]))
          ]),
          _createElementVNode$2("div", _hoisted_15$1, "做种 " + _toDisplayString$2(activeSeeding.value) + " · 暂停 " + _toDisplayString$2(stoppedCount.value) + " · 任务 " + _toDisplayString$2(runningCount.value) + " 跑中", 1)
        ]),
        _createElementVNode$2("article", _hoisted_16$1, [
          _cache[16] || (_cache[16] = _createElementVNode$2("div", { class: "mfh-kpi__label" }, [
            _createTextVNode$2("站点上报时魔"),
            _createElementVNode$2("span", { class: "mfh-kpi__scope" }, "/ h")
          ], -1)),
          _createElementVNode$2("div", _hoisted_17$1, [
            _createElementVNode$2("div", _hoisted_18$1, _toDisplayString$2(_unref$1(formatBonus)(bonusPerHour.value)), 1),
            (_openBlock$2(), _createElementBlock$1("svg", _hoisted_19$1, [
              (sparkBonus.value.area)
                ? (_openBlock$2(), _createElementBlock$1("path", {
                    key: 0,
                    d: sparkBonus.value.area,
                    class: "mfh-spark__area is-success"
                  }, null, 8, _hoisted_20$1))
                : _createCommentVNode$1("", true),
              (sparkBonus.value.line)
                ? (_openBlock$2(), _createElementBlock$1("path", {
                    key: 1,
                    d: sparkBonus.value.line,
                    class: "mfh-spark__line is-success"
                  }, null, 8, _hoisted_21$1))
                : _createCommentVNode$1("", true)
            ]))
          ]),
          _createElementVNode$2("div", _hoisted_22$1, "全站 " + _toDisplayString$2(taskTotal.value) + " 个任务汇总", 1)
        ]),
        _createElementVNode$2("article", _hoisted_23$1, [
          _createElementVNode$2("div", _hoisted_24$1, [
            _createTextVNode$2("站点当前" + _toDisplayString$2(currencyLabel.value), 1),
            _cache[17] || (_cache[17] = _createElementVNode$2("span", { class: "mfh-kpi__scope" }, "点", -1))
          ]),
          _createElementVNode$2("div", _hoisted_25$1, [
            _createElementVNode$2("div", _hoisted_26$1, _toDisplayString$2(Math.round(currentBonus.value).toLocaleString()), 1),
            (_openBlock$2(), _createElementBlock$1("svg", _hoisted_27$1, [
              (sparkBonusNow.value.area)
                ? (_openBlock$2(), _createElementBlock$1("path", {
                    key: 0,
                    d: sparkBonusNow.value.area,
                    class: "mfh-spark__area is-info"
                  }, null, 8, _hoisted_28$1))
                : _createCommentVNode$1("", true),
              (sparkBonusNow.value.line)
                ? (_openBlock$2(), _createElementBlock$1("path", {
                    key: 1,
                    d: sparkBonusNow.value.line,
                    class: "mfh-spark__line is-info"
                  }, null, 8, _hoisted_29$1))
                : _createCommentVNode$1("", true)
            ]))
          ]),
          _cache[18] || (_cache[18] = _createElementVNode$2("div", { class: "mfh-kpi__foot" }, "各站实时存量之和", -1))
        ]),
        _createElementVNode$2("article", _hoisted_30$1, [
          _cache[19] || (_cache[19] = _createElementVNode$2("div", { class: "mfh-kpi__label" }, "上次运行", -1)),
          _createElementVNode$2("div", _hoisted_31$1, [
            _createElementVNode$2("div", _hoisted_32$1, _toDisplayString$2(lastRun.value ? lastRun.value.ago : '—'), 1)
          ]),
          _createElementVNode$2("div", _hoisted_33$1, [
            (lastRun.value)
              ? (_openBlock$2(), _createElementBlock$1(_Fragment$1, { key: 0 }, [
                  _createTextVNode$2("处理 " + _toDisplayString$2(lastRun.value.items) + " 项 · 耗时 " + _toDisplayString$2(lastRun.value.duration), 1)
                ], 64))
              : (_openBlock$2(), _createElementBlock$1(_Fragment$1, { key: 1 }, [
                  _createTextVNode$2("暂无运行记录")
                ], 64))
          ])
        ])
      ]),
      _createElementVNode$2("section", _hoisted_34$1, [
        _createElementVNode$2("header", _hoisted_35$1, [
          _createElementVNode$2("div", null, [
            _cache[20] || (_cache[20] = _createElementVNode$2("div", { class: "mfh-panel__title" }, "任务矩阵", -1)),
            _createElementVNode$2("div", _hoisted_36$1, _toDisplayString$2(rows.value.length) + " 个任务 · 点击任意任务进入单任务详情", 1)
          ]),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-link",
            onClick: _cache[4] || (_cache[4] = $event => (emit('create-task')))
          }, "新建任务")
        ]),
        _createElementVNode$2("div", _hoisted_37$1, [
          _cache[21] || (_cache[21] = _createElementVNode$2("div", { class: "mfh-matrix__head" }, [
            _createElementVNode$2("span", null, "任务"),
            _createElementVNode$2("span", { class: "mfh-matrix__num" }, "时魔 / h"),
            _createElementVNode$2("span", { class: "mfh-matrix__num" }, "种子"),
            _createElementVNode$2("span")
          ], -1)),
          (_openBlock$2(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(rows.value, (t) => {
            return (_openBlock$2(), _createElementBlock$1("button", {
              key: t.id,
              type: "button",
              class: "mfh-matrix__row",
              onClick: $event => (emit('open-task', t.id))
            }, [
              _createElementVNode$2("span", _hoisted_39$1, [
                _createElementVNode$2("span", {
                  class: _normalizeClass$1(["mfh-dot", `is-${rowMeta(t).color}`])
                }, null, 2),
                _createElementVNode$2("span", _hoisted_40$1, [
                  _createElementVNode$2("strong", null, _toDisplayString$2(t.name), 1),
                  _createElementVNode$2("em", null, _toDisplayString$2(rowSubtitle(t)), 1)
                ])
              ]),
              _createElementVNode$2("span", _hoisted_41$1, _toDisplayString$2(rowBonus(t)), 1),
              _createElementVNode$2("span", _hoisted_42$1, _toDisplayString$2(t.seeding_count || 0), 1),
              _createVNode$2(_component_VIcon, {
                icon: "mdi-chevron-right",
                size: "16",
                class: "mfh-matrix__chev"
              })
            ], 8, _hoisted_38$1))
          }), 128)),
          (!rows.value.length)
            ? (_openBlock$2(), _createElementBlock$1("div", _hoisted_43, " 还没有任务。点右上角「新建任务」开始。 "))
            : _createCommentVNode$1("", true)
        ])
      ]),
      _createElementVNode$2("section", _hoisted_44, [
        _createElementVNode$2("header", _hoisted_45, [
          _cache[24] || (_cache[24] = _createElementVNode$2("div", null, [
            _createElementVNode$2("div", { class: "mfh-panel__title" }, "全站时魔趋势"),
            _createElementVNode$2("div", { class: "mfh-panel__sub" }, "每小时采样 · 最近 72 小时")
          ], -1)),
          _createElementVNode$2("div", _hoisted_46, [
            _cache[23] || (_cache[23] = _createElementVNode$2("span", { class: "mfh-legend__item" }, [
              _createElementVNode$2("i", { class: "mfh-legend__line is-primary" }),
              _createTextVNode$2("本周")
            ], -1)),
            (chart.value && chart.value.hasPrev)
              ? (_openBlock$2(), _createElementBlock$1("span", _hoisted_47, [...(_cache[22] || (_cache[22] = [
                  _createElementVNode$2("i", { class: "mfh-legend__line is-dashed" }, null, -1),
                  _createTextVNode$2("上周", -1)
                ]))]))
              : _createCommentVNode$1("", true)
          ])
        ]),
        (chart.value)
          ? (_openBlock$2(), _createElementBlock$1("div", _hoisted_48, [
              _createElementVNode$2("div", _hoisted_49, [
                (_openBlock$2(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(chart.value.ticks, (tick) => {
                  return (_openBlock$2(), _createElementBlock$1("span", {
                    key: tick.y,
                    style: _normalizeStyle({ bottom: `${(tick.y / CHART_H) * 100}%` })
                  }, _toDisplayString$2(tick.label), 5))
                }), 128))
              ]),
              _createElementVNode$2("div", _hoisted_50, [
                (_openBlock$2(), _createElementBlock$1("svg", _hoisted_51, [
                  (_openBlock$2(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(chart.value.ticks, (tick) => {
                    return (_openBlock$2(), _createElementBlock$1("line", {
                      key: `g${tick.y}`,
                      x1: "0",
                      y1: tick.y,
                      x2: "900",
                      y2: tick.y,
                      class: "mfh-chart__grid"
                    }, null, 8, _hoisted_52))
                  }), 128)),
                  (chart.value.areaCur)
                    ? (_openBlock$2(), _createElementBlock$1("path", {
                        key: 0,
                        d: chart.value.areaCur,
                        class: "mfh-chart__area"
                      }, null, 8, _hoisted_53))
                    : _createCommentVNode$1("", true),
                  (chart.value.linePrev)
                    ? (_openBlock$2(), _createElementBlock$1("path", {
                        key: 1,
                        d: chart.value.linePrev,
                        class: "mfh-chart__prev"
                      }, null, 8, _hoisted_54))
                    : _createCommentVNode$1("", true),
                  (chart.value.lineCur)
                    ? (_openBlock$2(), _createElementBlock$1("path", {
                        key: 2,
                        d: chart.value.lineCur,
                        class: "mfh-chart__cur"
                      }, null, 8, _hoisted_55))
                    : _createCommentVNode$1("", true)
                ])),
                _cache[25] || (_cache[25] = _createElementVNode$2("div", { class: "mfh-chart__xaxis" }, [
                  _createElementVNode$2("span", null, "72h 前"),
                  _createElementVNode$2("span", null, "36h 前"),
                  _createElementVNode$2("span", null, "现在")
                ], -1))
              ])
            ]))
          : (_openBlock$2(), _createElementBlock$1("div", _hoisted_56, "暂无小时采样数据（任务跑起来后才会有曲线）"))
      ])
    ]),
    _createElementVNode$2("aside", _hoisted_57, [
      _createElementVNode$2("section", _hoisted_58, [
        _createElementVNode$2("header", _hoisted_59, [
          _cache[26] || (_cache[26] = _createElementVNode$2("div", { class: "mfh-panel__title" }, "全局动态", -1)),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-link",
            onClick: _cache[5] || (_cache[5] = $event => (emit('open-ops')))
          }, "全部")
        ]),
        _createElementVNode$2("div", _hoisted_60, [
          (!recentOps.value.length)
            ? (_openBlock$2(), _createElementBlock$1("div", _hoisted_61, "暂无操作记录"))
            : _createCommentVNode$1("", true),
          (_openBlock$2(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(recentOps.value, (o) => {
            return (_openBlock$2(), _createElementBlock$1("button", {
              key: o.operation_id,
              type: "button",
              class: "mfh-ops__row",
              onClick: _cache[6] || (_cache[6] = $event => (emit('open-ops')))
            }, [
              _createElementVNode$2("span", {
                class: _normalizeClass$1(["mfh-dot", stateDotClass(o.state)])
              }, null, 2),
              _createElementVNode$2("span", _hoisted_62, [
                _createElementVNode$2("span", _hoisted_63, _toDisplayString$2(opText(o)), 1),
                _createElementVNode$2("span", _hoisted_64, _toDisplayString$2(opTime(o)), 1)
              ])
            ]))
          }), 128))
        ])
      ]),
      _createElementVNode$2("section", _hoisted_65, [
        _createElementVNode$2("header", _hoisted_66, [
          _cache[27] || (_cache[27] = _createElementVNode$2("div", { class: "mfh-panel__title" }, "站点监控", -1)),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-link",
            onClick: _cache[7] || (_cache[7] = $event => (emit('open-page', 'hub')))
          }, "功能中心")
        ]),
        _createElementVNode$2("div", _hoisted_67, [
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-mon__row",
            onClick: _cache[8] || (_cache[8] = $event => (emit('open-health')))
          }, [
            _createElementVNode$2("span", _hoisted_68, [
              _createElementVNode$2("span", {
                class: _normalizeClass$1(["mfh-dot", `is-${healthChip.value.color}`])
              }, null, 2),
              _cache[28] || (_cache[28] = _createTextVNode$2("健康自检", -1))
            ]),
            _createElementVNode$2("span", {
              class: _normalizeClass$1(["mfh-mon__value", `is-${healthChip.value.color}`])
            }, _toDisplayString$2(healthChip.value.label), 3)
          ]),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-mon__row",
            onClick: _cache[9] || (_cache[9] = $event => (emit('open-ceiling')))
          }, [
            _createElementVNode$2("span", _hoisted_69, [
              _createElementVNode$2("span", {
                class: _normalizeClass$1(["mfh-dot", `is-${ceilingColor.value}`])
              }, null, 2),
              _cache[29] || (_cache[29] = _createTextVNode$2("站点容量", -1))
            ]),
            _createElementVNode$2("span", _hoisted_70, _toDisplayString$2(ceilingPct.value.toFixed(0)) + "%", 1)
          ]),
          _createElementVNode$2("div", _hoisted_71, [
            _createElementVNode$2("span", {
              class: _normalizeClass$1(`is-${ceilingColor.value}`),
              style: _normalizeStyle({ width: `${Math.min(100, ceilingPct.value)}%` })
            }, null, 6)
          ]),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-mon__row",
            onClick: _cache[10] || (_cache[10] = $event => (emit('open-hr')))
          }, [
            _createElementVNode$2("span", _hoisted_72, [
              _createElementVNode$2("span", {
                class: _normalizeClass$1(["mfh-dot", hrSummary.value.count ? 'is-warning' : 'is-success'])
              }, null, 2),
              _cache[30] || (_cache[30] = _createTextVNode$2("H&R 账单", -1))
            ]),
            _createElementVNode$2("span", _hoisted_73, _toDisplayString$2(hrSummary.value.count ? `${hrSummary.value.count} 个待完成` : '无'), 1)
          ])
        ])
      ]),
      _createElementVNode$2("section", _hoisted_74, [
        _createElementVNode$2("header", _hoisted_75, [
          _cache[31] || (_cache[31] = _createElementVNode$2("div", { class: "mfh-panel__title" }, "快速功能", -1)),
          _createElementVNode$2("button", {
            type: "button",
            class: "mfh-link",
            onClick: _cache[11] || (_cache[11] = $event => (emit('open-page', 'hub')))
          }, "全部功能")
        ]),
        _createElementVNode$2("div", _hoisted_76, [
          (_openBlock$2(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(quickPages.value, (p) => {
            return (_openBlock$2(), _createElementBlock$1("button", {
              key: p.key,
              type: "button",
              class: "mfh-quick__item",
              onClick: $event => (emit('open-page', p.key))
            }, [
              _createVNode$2(_component_VIcon, {
                icon: p.icon,
                size: "18"
              }, null, 8, ["icon"]),
              _createElementVNode$2("span", null, [
                _createElementVNode$2("strong", null, _toDisplayString$2(p.label), 1),
                (p.hint)
                  ? (_openBlock$2(), _createElementBlock$1("em", _hoisted_78, _toDisplayString$2(p.hint), 1))
                  : _createCommentVNode$1("", true)
              ])
            ], 8, _hoisted_77))
          }), 128))
        ])
      ])
    ])
  ]))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const OverviewHome = Object.assign(_sfc_main$2, { __scopeId: 'data-v-d02f7544' })

export default OverviewHome
