// OverviewTab —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './OverviewTab.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$d,
  createBlock: _createBlock$d,
  createCommentVNode: _createCommentVNode$d,
  createElementBlock: _createElementBlock$d,
  createElementVNode: _createElementVNode$f,
  createTextVNode: _createTextVNode$e,
  createVNode: _createVNode$e,
  normalizeClass: _normalizeClass$5,
  openBlock: _openBlock$f,
  renderList: _renderList$b,
  resolveComponent: _resolveComponent$f,
  toDisplayString: _toDisplayString$f,
  unref: _unref$7,
  withCtx: _withCtx$d,
} = __vue

import index from '../../index.vue'
import { levelNextText as levelNextText$1, levelNextText, taskMetrics } from '../../format.js'
import { currencyOf } from '../../composables/useCurrency.js'
import { formatBonus, formatBytes, formatDateTime, formatDurationSeconds, runStatusText } from '../../../../utils.js'

const _hoisted_1$d = { class: "magicflow-stat-grid magicflow-stat-grid--auto" };
const _hoisted_2$c = { class: "magicflow-stat__foot" };
const _hoisted_3$b = { class: "magicflow-stat__foot" };
const _hoisted_4$b = { class: "magicflow-stat__label" };
const _hoisted_5$b = { class: "magicflow-stat__foot" };
const _hoisted_6$a = {
  key: 0,
  class: "magicflow-stat-grid magicflow-stat-grid--single"
};
const _hoisted_7$9 = { class: "magicflow-stat__label" };
const _hoisted_8$9 = { class: "mf-goal__target" };
const _hoisted_9$9 = { class: "mf-goal__pct" };
const _hoisted_10$9 = { class: "magicflow-stat__foot" };
const _hoisted_11$9 = {
  key: 1,
  class: "magicflow-stat-grid magicflow-stat-grid--single"
};
const _hoisted_12$9 = { class: "magicflow-panel__head" };
const _hoisted_13$8 = { class: "mf-obs__rows" };
const _hoisted_14$8 = { class: "mf-obs__row" };
const _hoisted_15$8 = { class: "mf-obs__row" };
const _hoisted_16$8 = { class: "mf-obs__row" };
const _hoisted_17$8 = {
  key: 0,
  class: "mf-obs__row"
};
const _hoisted_18$8 = { class: "mf-obs__chips" };
const _hoisted_19$7 = { class: "mf-spark-grid" };
const _hoisted_20$7 = { class: "mf-spark__head" };
const _hoisted_21$6 = {
  class: "mf-spark__svg",
  viewBox: "0 0 100 26",
  preserveAspectRatio: "none"
};
const _hoisted_22$5 = ["d"];
const _hoisted_23$4 = { class: "mf-spark__foot" };
const _hoisted_24$4 = { class: "magicflow-overview-grid" };
const _hoisted_25$4 = { class: "magicflow-panel__head" };
const _hoisted_26$4 = { class: "magicflow-facts" };
const _hoisted_27$4 = { class: "magicflow-panel__head" };
const _hoisted_28$3 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_29$3 = { class: "magicflow-facts" };
const _hoisted_30$3 = { key: 0 };
const _hoisted_31$3 = { key: 1 };
const _hoisted_32$3 = {
  key: 0,
  class: "magicflow-live-alerts"
};
const _hoisted_33$3 = { class: "magicflow-panel__head" };
const _hoisted_34$3 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_35$3 = { class: "magicflow-run-summary" };
const {computed: computed$u} = __vue;


const _sfc_main$f = {
  __name: 'OverviewTab',
  props: {
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
},
  emits: ['open-entry'],
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 概览 Tab（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式；零行为 / 零样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不直接调父方法。
// 展示型纯函数（formatBytes / formatBonus / formatDateTime / runStatusText / formatDurationSeconds）
// 是 src/utils 的共享工具 → 直接 import（非父方法、不作为 Function prop 下发）。
const props = __props;

// 仅为满足模板静态检查：事件用法见 @click="emit('open-entry', 'diagnostics')"。
const emit = __emit;

// 该任务所属站点对「魔力」的自称（认不出兜底「魔力值」）
const currencyName = computed$u(() => currencyOf(props.selectedTask));

// ★ 19.10.39「站点魔力 · xx/h」：优先用任务侧时魔（与上方「站点上报时魔」同源），
//   否则同一页会出现两个不同的时魔（live 折算值 vs 站点自报值）。
const hourlyText = computed$u(() => {
  const t = props.selectedTask || {};
  if (t.site_bonus_ok && t.site_bonus_per_hour != null) return ` · ${formatBonus(t.site_bonus_per_hour)}`
  const a = props.siteAccount || {};
  if (a.bonus_per_hour != null) return ` · ${Number(a.bonus_per_hour).toFixed(2)}/h`
  return ''
});

// ★ 19.11.18：「距下一级还差什么」——后端 level_req 抄 PTD 站点等级表算好的差值；
// 算不出的输入后端放 unknown（写「未知」，不拿 0 顶，铁律 6）。
// ★ 19.11.20：文案出口提为 format.js::levelNextText（站点报表同款复用，单一真值源）。
const levelNextText$1 = computed$u(() => levelNextText((props.siteAccount || {}).level_next, currencyName.value));

// ★ 19.11.0：磁贴统一走 taskMetrics，主指标 = 该任务的考核目标；
// 但「本任务上传」对两种任务都展示（原先只给刷流），否则魔力任务看不到配额下的实际产出。
const metrics = computed$u(() => taskMetrics(props.selectedTask || {}));

// ★ 19.11.0：目标进度。goal_* 由 features/formula.py::_task_goal_status 算出，
// 注意口径是 **站点级**（brush → 站点上传量 GB，bonus → 站点魔力值存量），不是本任务产出。
const goalPct = computed$u(() => {
  const t = props.selectedTask || {};
  const tgt = Number(t.goal_target || 0);
  if (!t.goal_has || tgt <= 0) return 0
  const cur = Number(t.goal_current || 0);
  return Math.max(0, Math.min(100, Math.round((cur / tgt) * 100)))
});

// goal_unit 为 GB 时 goal_current / goal_target 是 GB 数，转字节后再格式化，避免「4820 GB」这种读数
const goalValueText = (value) => {
  const t = props.selectedTask || {};
  const n = Number(value || 0);
  return t.goal_unit === 'GB' ? formatBytes(n * 1024 ** 3) : n.toFixed(2)
};
const goalCurrentText = computed$u(() => goalValueText(props.selectedTask?.goal_current));
const goalTargetText = computed$u(() => goalValueText(props.selectedTask?.goal_target));
const goalSpeedText = computed$u(() => {
  const t = props.selectedTask || {};
  if (!t.goal_has || t.goal_reached) return ''
  const tgt = Number(t.goal_target || 0);
  const cur = Number(t.goal_current || 0);
  const gap = tgt - cur;
  if (tgt <= 0 || gap <= 0) return ''
  return t.goal_unit === 'GB'
    ? `距目标还差 ${formatBytes(gap * 1024 ** 3)}`
    : `距目标还差 ${gap.toFixed(2)}`
});

return (_ctx, _cache) => {
  const _component_VSheet = _resolveComponent$f("VSheet");
  const _component_VProgressLinear = _resolveComponent$f("VProgressLinear");
  const _component_VChip = _resolveComponent$f("VChip");
  const _component_VAlert = _resolveComponent$f("VAlert");
  const _component_VBtn = _resolveComponent$f("VBtn");

  return (_openBlock$f(), _createElementBlock$d(_Fragment$d, null, [
    _createElementVNode$f("div", _hoisted_1$d, [
      _createVNode$e(_component_VSheet, { class: "magicflow-stat magicflow-stat--accent app-surface-static" }, {
        default: _withCtx$d(() => [
          _cache[1] || (_cache[1] = _createElementVNode$f("span", { class: "magicflow-stat__label" }, "托管种子", -1)),
          _createElementVNode$f("strong", null, _toDisplayString$f(__props.selectedTask.seeding_count || 0), 1),
          _createElementVNode$f("span", _hoisted_2$c, "做种中 " + _toDisplayString$f(__props.selectedTask.active_seeding_count || 0) + " · 下载中 " + _toDisplayString$f(__props.selectedTask.downloading_count || 0) + " · 已暂停 " + _toDisplayString$f(__props.selectedTask.paused_count || 0), 1)
        ]),
        _: 1
      }),
      _createVNode$e(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
        default: _withCtx$d(() => [
          _cache[2] || (_cache[2] = _createElementVNode$f("span", { class: "magicflow-stat__label" }, "本任务上传", -1)),
          _createElementVNode$f("strong", null, _toDisplayString$f(metrics.value.upload.text), 1),
          _createElementVNode$f("span", {
            class: _normalizeClass$5(["magicflow-stat__foot", { 'mf-warn': metrics.value.upload.noUpload }])
          }, [
            _createTextVNode$e(" 任务级累计 · " + _toDisplayString$f(metrics.value.upload.active) + " 个有上传", 1),
            (metrics.value.upload.noUpload)
              ? (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 0 }, [
                  _createTextVNode$e("（当前无上传）")
                ], 64))
              : _createCommentVNode$d("", true)
          ], 2)
        ]),
        _: 1
      }),
      (__props.taskIsBrush)
        ? (_openBlock$f(), _createBlock$d(_component_VSheet, {
            key: 0,
            class: "magicflow-stat app-surface-static"
          }, {
            default: _withCtx$d(() => [
              _cache[3] || (_cache[3] = _createElementVNode$f("span", { class: "magicflow-stat__label" }, "站点上传量", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(__props.siteAccount.ok ? _unref$7(formatBytes)(__props.siteAccount.upload || 0) : '—'), 1),
              _createElementVNode$f("span", _hoisted_3$b, _toDisplayString$f(__props.siteAccount.source === 'live' ? '实时（直连站点）' : 'MP 快照') + _toDisplayString$f(__props.siteAccount.ok ? ` · 下载 ${_unref$7(formatBytes)(__props.siteAccount.download || 0)}` : ''), 1)
            ]),
            _: 1
          }))
        : (_openBlock$f(), _createBlock$d(_component_VSheet, {
            key: 1,
            class: "magicflow-stat app-surface-static"
          }, {
            default: _withCtx$d(() => [
              _cache[4] || (_cache[4] = _createElementVNode$f("span", { class: "magicflow-stat__label" }, "站点上报时魔", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(__props.selectedTask.site_bonus_ok ? _unref$7(formatBonus)(__props.selectedTask.site_bonus_per_hour) : '取数中…'), 1),
              _cache[5] || (_cache[5] = _createElementVNode$f("span", { class: "magicflow-stat__foot" }, "站点实时值", -1))
            ]),
            _: 1
          })),
      (!__props.taskIsBrush)
        ? (_openBlock$f(), _createBlock$d(_component_VSheet, {
            key: 2,
            class: "magicflow-stat app-surface-static"
          }, {
            default: _withCtx$d(() => [
              _createElementVNode$f("span", _hoisted_4$b, "站点当前" + _toDisplayString$f(currencyName.value), 1),
              _createElementVNode$f("strong", null, _toDisplayString$f(Number(__props.selectedTask.site_current_bonus || 0).toFixed(2)), 1),
              _cache[6] || (_cache[6] = _createElementVNode$f("span", { class: "magicflow-stat__foot" }, "该站点实时存量", -1))
            ]),
            _: 1
          }))
        : _createCommentVNode$d("", true),
      _createVNode$e(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
        default: _withCtx$d(() => [
          _cache[7] || (_cache[7] = _createElementVNode$f("span", { class: "magicflow-stat__label" }, "上次运行", -1)),
          _createElementVNode$f("strong", null, _toDisplayString$f(__props.detailStats.last_added || 0) + " / " + _toDisplayString$f(__props.detailStats.last_reused || 0) + " / " + _toDisplayString$f(__props.detailStats.last_deleted || 0), 1),
          _createElementVNode$f("span", _hoisted_5$b, "新增 / 复用 / 删除 · 当前托管 " + _toDisplayString$f(__props.detailStats.last_kept || __props.selectedTask.seeding_count || 0), 1)
        ]),
        _: 1
      })
    ]),
    (__props.selectedTask.goal_has)
      ? (_openBlock$f(), _createElementBlock$d("div", _hoisted_6$a, [
          _createVNode$e(_component_VSheet, { class: "magicflow-stat magicflow-stat--accent magicflow-stat--goal app-surface-static" }, {
            default: _withCtx$d(() => [
              _createElementVNode$f("span", _hoisted_7$9, _toDisplayString$f(__props.taskIsBrush ? '目标上传（站点累计）' : '目标魔力（站点存量）'), 1),
              _createElementVNode$f("strong", null, [
                _createTextVNode$e(_toDisplayString$f(goalCurrentText.value) + " ", 1),
                _createElementVNode$f("small", _hoisted_8$9, "/ " + _toDisplayString$f(goalTargetText.value), 1),
                _createElementVNode$f("small", _hoisted_9$9, _toDisplayString$f(goalPct.value) + "%", 1)
              ]),
              _createVNode$e(_component_VProgressLinear, {
                "model-value": goalPct.value,
                color: __props.selectedTask.goal_reached ? 'success' : 'primary',
                height: "6",
                rounded: "",
                class: "mf-goal__bar"
              }, null, 8, ["model-value", "color"]),
              _createElementVNode$f("span", _hoisted_10$9, [
                (__props.selectedTask.goal_reached)
                  ? (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 0 }, [
                      _createTextVNode$e("已达标 · 任务会自动停止")
                    ], 64))
                  : (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 1 }, [
                      _createTextVNode$e(_toDisplayString$f(goalSpeedText.value), 1),
                      (__props.selectedTask.goal_source === 'pending')
                        ? (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 0 }, [
                            _createTextVNode$e(" · 取数中")
                          ], 64))
                        : _createCommentVNode$d("", true)
                    ], 64))
              ])
            ]),
            _: 1
          })
        ]))
      : _createCommentVNode$d("", true),
    ((__props.selectedTask.run_mode || 'running') === 'seeding')
      ? (_openBlock$f(), _createElementBlock$d("div", _hoisted_11$9, [
          _createVNode$e(_component_VSheet, { class: "magicflow-stat magicflow-stat--accent magicflow-stat--strip app-surface-static" }, {
            default: _withCtx$d(() => [
              _cache[8] || (_cache[8] = _createElementVNode$f("span", { class: "magicflow-stat__label" }, "接管保护", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(__props.selectedTask.protected_count || 0), 1),
              _cache[9] || (_cache[9] = _createElementVNode$f("span", { class: "magicflow-stat__foot" }, "手动加或 IYUU 回来的种已纳管并永久保护", -1))
            ]),
            _: 1
          })
        ]))
      : _createCommentVNode$d("", true),
    (__props.decision.at_cap !== undefined)
      ? (_openBlock$f(), _createBlock$d(_component_VSheet, {
          key: 2,
          tag: "section",
          class: "magicflow-panel app-surface-static mf-obs"
        }, {
          default: _withCtx$d(() => [
            _createElementVNode$f("header", _hoisted_12$9, [
              _cache[10] || (_cache[10] = _createElementVNode$f("div", null, [
                _createElementVNode$f("div", { class: "text-subtitle-1 font-weight-medium" }, "本轮决策"),
                _createElementVNode$f("div", { class: "text-body-2 text-medium-emphasis" }, "为什么这么做 · 最近一轮闸门判定与淘汰口径")
              ], -1)),
              _createVNode$e(_component_VChip, {
                color: __props.decision.at_cap ? 'warning' : 'success',
                size: "small",
                variant: "tonal"
              }, {
                default: _withCtx$d(() => [
                  _createTextVNode$e(_toDisplayString$f(__props.decision.at_cap ? '已达上限 · 可换种' : '未达上限 · 不做低效换种'), 1)
                ]),
                _: 1
              }, 8, ["color"])
            ]),
            _createElementVNode$f("div", _hoisted_13$8, [
              _createElementVNode$f("div", _hoisted_14$8, [
                _cache[11] || (_cache[11] = _createElementVNode$f("span", null, "闸门", -1)),
                _createElementVNode$f("strong", null, _toDisplayString$f(__props.decisionCapText), 1)
              ]),
              _createElementVNode$f("div", _hoisted_15$8, [
                _cache[12] || (_cache[12] = _createElementVNode$f("span", null, "淘汰口径", -1)),
                _createElementVNode$f("strong", null, " 候选 " + _toDisplayString$f(__props.decision.candidates ?? '—') + " → 受保护 " + _toDisplayString$f(__props.decision.protected ?? '—') + " → 保留 " + _toDisplayString$f(__props.decision.keep ?? '—') + " → 待删 " + _toDisplayString$f(__props.decision.to_delete ?? '—') + " → 实删 " + _toDisplayString$f(__props.decision.deleted ?? '—'), 1)
              ]),
              _createElementVNode$f("div", _hoisted_16$8, [
                _cache[13] || (_cache[13] = _createElementVNode$f("span", null, "门槛 / 保护", -1)),
                _createElementVNode$f("strong", null, " 低效门槛 " + _toDisplayString$f(__props.decision.threshold ?? '—') + "/h · 保护阈值 " + _toDisplayString$f(__props.decision.protect_threshold ?? '∞') + " · 保留上限 " + _toDisplayString$f(__props.decision.max_keep ?? '—') + " 个 · 零魔淘汰 " + _toDisplayString$f(__props.decision.zero_bonus_delete ? '开' : '关'), 1)
              ]),
              (__props.decisionReasons.length)
                ? (_openBlock$f(), _createElementBlock$d("div", _hoisted_17$8, [
                    _cache[14] || (_cache[14] = _createElementVNode$f("span", null, "删除原因", -1)),
                    _createElementVNode$f("div", _hoisted_18$8, [
                      (_openBlock$f(true), _createElementBlock$d(_Fragment$d, null, _renderList$b(__props.decisionReasons, (r) => {
                        return (_openBlock$f(), _createBlock$d(_component_VChip, {
                          key: r.label,
                          size: "x-small",
                          variant: "tonal",
                          color: "error"
                        }, {
                          default: _withCtx$d(() => [
                            _createTextVNode$e(_toDisplayString$f(r.label) + " ×" + _toDisplayString$f(r.count), 1)
                          ]),
                          _: 2
                        }, 1024))
                      }), 128))
                    ])
                  ]))
                : _createCommentVNode$d("", true)
            ])
          ]),
          _: 1
        }))
      : _createCommentVNode$d("", true),
    (__props.trendCards.length)
      ? (_openBlock$f(), _createBlock$d(_component_VSheet, {
          key: 3,
          tag: "section",
          class: "magicflow-panel app-surface-static mf-obs"
        }, {
          default: _withCtx$d(() => [
            _cache[15] || (_cache[15] = _createElementVNode$f("header", { class: "magicflow-panel__head" }, [
              _createElementVNode$f("div", null, [
                _createElementVNode$f("div", { class: "text-subtitle-1 font-weight-medium" }, "趋势"),
                _createElementVNode$f("div", { class: "text-body-2 text-medium-emphasis" }, "每小时采样 · 最近 72 小时（本地序列）")
              ])
            ], -1)),
            _createElementVNode$f("div", _hoisted_19$7, [
              (_openBlock$f(true), _createElementBlock$d(_Fragment$d, null, _renderList$b(__props.trendCards, (c) => {
                return (_openBlock$f(), _createElementBlock$d("div", {
                  key: c.key,
                  class: "mf-spark"
                }, [
                  _createElementVNode$f("div", _hoisted_20$7, [
                    _createElementVNode$f("span", null, _toDisplayString$f(c.label), 1),
                    _createElementVNode$f("strong", null, [
                      _createTextVNode$e(_toDisplayString$f(Number(c.s.last).toFixed(c.key === 'seeds' ? 0 : 2)) + _toDisplayString$f(c.unit) + " ", 1),
                      _createElementVNode$f("em", {
                        class: _normalizeClass$5(c.s.good ? 'is-up' : 'is-down')
                      }, _toDisplayString$f(c.s.delta >= 0 ? '▲' : '▼') + _toDisplayString$f(Math.abs(c.s.delta).toFixed(1)) + "% ", 3)
                    ])
                  ]),
                  (_openBlock$f(), _createElementBlock$d("svg", _hoisted_21$6, [
                    _createElementVNode$f("path", {
                      d: c.s.path,
                      fill: "none",
                      class: _normalizeClass$5(`mf-spark__line mf-spark__line--${c.color}`),
                      "vector-effect": "non-scaling-stroke"
                    }, null, 10, _hoisted_22$5)
                  ])),
                  _createElementVNode$f("div", _hoisted_23$4, [
                    _createElementVNode$f("span", null, _toDisplayString$f(c.s.count) + " 点", 1),
                    _createElementVNode$f("span", null, "低 " + _toDisplayString$f(Number(c.s.min).toFixed(1)) + " · 高 " + _toDisplayString$f(Number(c.s.max).toFixed(1)), 1)
                  ])
                ]))
              }), 128))
            ])
          ]),
          _: 1
        }))
      : _createCommentVNode$d("", true),
    _createElementVNode$f("div", _hoisted_24$4, [
      _createVNode$e(_component_VSheet, {
        tag: "section",
        class: "magicflow-panel magicflow-panel--tall app-surface-static"
      }, {
        default: _withCtx$d(() => [
          _createElementVNode$f("header", _hoisted_25$4, [
            _cache[16] || (_cache[16] = _createElementVNode$f("div", null, [
              _createElementVNode$f("div", { class: "text-subtitle-1 font-weight-medium" }, "运行状态"),
              _createElementVNode$f("div", { class: "text-body-2 text-medium-emphasis" }, "当前任务调度与魔力策略")
            ], -1)),
            _createVNode$e(_component_VChip, {
              color: __props.selectedState.color,
              size: "small",
              variant: "tonal"
            }, {
              default: _withCtx$d(() => [
                _createTextVNode$e(_toDisplayString$f(__props.selectedState.text), 1)
              ]),
              _: 1
            }, 8, ["color"])
          ]),
          _createElementVNode$f("dl", _hoisted_26$4, [
            _cache[34] || (_cache[34] = _createElementVNode$f("div", { class: "magicflow-facts__group" }, "调度", -1)),
            _createElementVNode$f("div", null, [
              _cache[17] || (_cache[17] = _createElementVNode$f("dt", null, "任务目标", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.goalFactText), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[18] || (_cache[18] = _createElementVNode$f("dt", null, "选种周期", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.cron_expression || `每 ${__props.taskConfig.brush_interval} 分钟`), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[19] || (_cache[19] = _createElementVNode$f("dt", null, "检查周期", -1)),
              _createElementVNode$f("dd", null, "每 " + _toDisplayString$f(__props.taskConfig.check_interval) + " 分钟", 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[20] || (_cache[20] = _createElementVNode$f("dt", null, "开启时段", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.active_time_range || '全天'), 1)
            ]),
            _cache[35] || (_cache[35] = _createElementVNode$f("div", { class: "magicflow-facts__group" }, "选种与保留", -1)),
            (__props.taskIsBrush)
              ? (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 0 }, [
                  _createElementVNode$f("div", null, [
                    _cache[21] || (_cache[21] = _createElementVNode$f("dt", null, "轮转周期", -1)),
                    _createElementVNode$f("dd", null, _toDisplayString$f(__props.brushSeedDays > 0 ? `做种满 ${__props.brushSeedDays} 天清理` : '不按天数（按无上传）'), 1)
                  ]),
                  _createElementVNode$f("div", null, [
                    _cache[22] || (_cache[22] = _createElementVNode$f("dt", null, "最小下载人数", -1)),
                    _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.brush_min_leechers ?? 1) + " 人", 1)
                  ])
                ], 64))
              : (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 1 }, [
                  _createElementVNode$f("div", null, [
                    _cache[23] || (_cache[23] = _createElementVNode$f("dt", null, "最低魔力", -1)),
                    _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.min_bonus_per_hour == null ? '自动' : `${Number(__props.taskConfig.min_bonus_per_hour).toFixed(2)} /h`), 1)
                  ]),
                  _createElementVNode$f("div", null, [
                    _cache[24] || (_cache[24] = _createElementVNode$f("dt", null, "最多保留", -1)),
                    _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.max_keep_torrents == null ? (__props.taskConfig.disk_size_gb ? `按 ${__props.taskConfig.disk_size_gb}GB 自动` : '不限') : `${__props.taskConfig.max_keep_torrents} 个`), 1)
                  ]),
                  _createElementVNode$f("div", null, [
                    _cache[25] || (_cache[25] = _createElementVNode$f("dt", null, "保护阈值", -1)),
                    _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.bonus_protect_threshold == null ? `站点当前${currencyName.value}` : Number(__props.taskConfig.bonus_protect_threshold).toFixed(0)), 1)
                  ]),
                  _createElementVNode$f("div", null, [
                    _cache[26] || (_cache[26] = _createElementVNode$f("dt", null, "完美种保护", -1)),
                    _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.protect_perfect === false ? '关闭' : `开启（≤${__props.taskConfig.perfect_max_seeders ?? 3}人 · ≥${__props.taskConfig.perfect_min_weeks ?? 4}周）`), 1)
                  ])
                ], 64)),
            _createElementVNode$f("div", null, [
              _cache[27] || (_cache[27] = _createElementVNode$f("dt", null, "选种来源", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.rss_support ? 'RSS' : '站点列表页'), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[28] || (_cache[28] = _createElementVNode$f("dt", null, "促销要求", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskIsBrush ? '免费（含 2X免费）' : (__props.taskConfig.freeleech === '2xfree' ? '2X 免费' : __props.taskConfig.freeleech === 'free' ? '免费' : '全部')), 1)
            ]),
            _cache[36] || (_cache[36] = _createElementVNode$f("div", { class: "magicflow-facts__group" }, "清理与恢复", -1)),
            _createElementVNode$f("div", null, [
              _cache[29] || (_cache[29] = _createElementVNode$f("dt", null, "自动补种", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.refill_when_empty ? '开启' : '关闭'), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[30] || (_cache[30] = _createElementVNode$f("dt", null, "无进度清理", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.cleanup_no_progress ? `开启（${__props.taskConfig.no_progress_minutes ?? 30} 分钟）` : '关闭'), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[31] || (_cache[31] = _createElementVNode$f("dt", null, "慢速清理", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.cleanup_slow_progress === false ? '关闭' : `开启（> ${__props.taskConfig.slow_progress_max_hours ?? 48}h 下不完即清）`), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[32] || (_cache[32] = _createElementVNode$f("dt", null, "促销失效清理", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）'), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[33] || (_cache[33] = _createElementVNode$f("dt", null, "自动恢复暂停", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.taskConfig.auto_resume_paused === false ? '关闭' : '开启'), 1)
            ])
          ])
        ]),
        _: 1
      }),
      _createVNode$e(_component_VSheet, {
        tag: "section",
        class: "magicflow-panel app-surface-static"
      }, {
        default: _withCtx$d(() => [
          _createElementVNode$f("header", _hoisted_27$4, [
            _createElementVNode$f("div", null, [
              _cache[37] || (_cache[37] = _createElementVNode$f("div", { class: "text-subtitle-1 font-weight-medium" }, "站点数据", -1)),
              _createElementVNode$f("div", _hoisted_28$3, [
                (__props.siteAccount.source === 'live')
                  ? (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 0 }, [
                      _createTextVNode$e("魔流直连站点用户栏" + _toDisplayString$f(__props.siteAccount.sampledAt ? ` · 采样于 ${__props.siteAccount.sampledAt}` : ''), 1)
                    ], 64))
                  : (__props.siteAccount.source === 'mp')
                    ? (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 1 }, [
                        _createTextVNode$e("默认 6 小时一轮" + _toDisplayString$f(__props.siteUser.updated_at ? ` · 更新于 ${__props.siteUser.updated_at}` : ''), 1)
                      ], 64))
                    : (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 2 }, [
                        _createTextVNode$e("等待站点回填数据")
                      ], 64))
              ])
            ]),
            (__props.siteAccount.source === 'live')
              ? (_openBlock$f(), _createBlock$d(_component_VChip, {
                  key: 0,
                  size: "small",
                  variant: "tonal",
                  color: __props.siteLiveLevel === 'warn' ? 'warning' : 'success'
                }, {
                  default: _withCtx$d(() => [
                    _createTextVNode$e(_toDisplayString$f(__props.siteLiveLevel === 'warn' ? '实时 · 有告警' : '实时'), 1)
                  ]),
                  _: 1
                }, 8, ["color"]))
              : (__props.siteAccount.source === 'mp')
                ? (_openBlock$f(), _createBlock$d(_component_VChip, {
                    key: 1,
                    size: "small",
                    variant: "tonal"
                  }, {
                    default: _withCtx$d(() => [...(_cache[38] || (_cache[38] = [
                      _createTextVNode$e("MP 快照", -1)
                    ]))]),
                    _: 1
                  }))
                : (_openBlock$f(), _createBlock$d(_component_VChip, {
                    key: 2,
                    size: "small",
                    variant: "tonal"
                  }, {
                    default: _withCtx$d(() => [...(_cache[39] || (_cache[39] = [
                      _createTextVNode$e("暂无数据", -1)
                    ]))]),
                    _: 1
                  }))
          ]),
          _createElementVNode$f("dl", _hoisted_29$3, [
            _createElementVNode$f("div", null, [
              _cache[40] || (_cache[40] = _createElementVNode$f("dt", null, "上传量", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteAccount.ok ? _unref$7(formatBytes)(__props.siteAccount.upload || 0) : '—'), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[41] || (_cache[41] = _createElementVNode$f("dt", null, "下载量", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteAccount.ok ? _unref$7(formatBytes)(__props.siteAccount.download || 0) : '—'), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[42] || (_cache[42] = _createElementVNode$f("dt", null, "分享率", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteAccount.ok && __props.siteAccount.ratio != null ? Number(__props.siteAccount.ratio).toFixed(3) : '—'), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[43] || (_cache[43] = _createElementVNode$f("dt", null, "等级", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteAccount.ok && __props.siteAccount.level ? __props.siteAccount.level : '未知'), 1)
            ]),
            (__props.siteAccount.level_next)
              ? (_openBlock$f(), _createElementBlock$d("div", _hoisted_30$3, [
                  _cache[44] || (_cache[44] = _createElementVNode$f("dt", null, "下一级", -1)),
                  _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteAccount.level_next.name) + _toDisplayString$f(levelNextText$1.value ? `：${levelNextText$1.value}` : ''), 1)
                ]))
              : _createCommentVNode$d("", true),
            _createElementVNode$f("div", null, [
              _cache[45] || (_cache[45] = _createElementVNode$f("dt", null, "做种数 / 下载数", -1)),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteAccount.ok ? `${__props.siteAccount.seeding ?? '—'} / ${__props.siteAccount.leeching ?? '—'}` : '—'), 1)
            ]),
            (__props.siteAccount.seeding_size)
              ? (_openBlock$f(), _createElementBlock$d("div", _hoisted_31$3, [
                  _cache[46] || (_cache[46] = _createElementVNode$f("dt", null, "做种体积", -1)),
                  _createElementVNode$f("dd", null, _toDisplayString$f(_unref$7(formatBytes)(__props.siteAccount.seeding_size)), 1)
                ]))
              : _createCommentVNode$d("", true),
            _createElementVNode$f("div", null, [
              _createElementVNode$f("dt", null, "站点" + _toDisplayString$f(currencyName.value), 1),
              _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteAccount.ok && __props.siteAccount.bonus != null ? Number(__props.siteAccount.bonus).toFixed(2) : '—') + _toDisplayString$f(hourlyText.value), 1)
            ]),
            (__props.siteAccount.source === 'live')
              ? (_openBlock$f(), _createElementBlock$d(_Fragment$d, { key: 2 }, [
                  _createElementVNode$f("div", null, [
                    _cache[47] || (_cache[47] = _createElementVNode$f("dt", null, "上传速率", -1)),
                    _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteLiveRates.ok ? `${Number(__props.siteLiveRates.up_mb_min || 0).toFixed(1)} MB/分` : '采样中'), 1)
                  ]),
                  _createElementVNode$f("div", null, [
                    _cache[48] || (_cache[48] = _createElementVNode$f("dt", null, "下载速率", -1)),
                    _createElementVNode$f("dd", {
                      class: _normalizeClass$5({ 'text-error': (__props.siteLiveRates.down_mb_min || 0) >= (__props.siteLiveCfg.download_alert_mb || 50) })
                    }, _toDisplayString$f(__props.siteLiveRates.ok ? `${Number(__props.siteLiveRates.down_mb_min || 0).toFixed(1)} MB/分` : '采样中'), 3)
                  ]),
                  _createElementVNode$f("div", null, [
                    _cache[49] || (_cache[49] = _createElementVNode$f("dt", null, "近 1h 净增", -1)),
                    _createElementVNode$f("dd", null, _toDisplayString$f(__props.siteLiveRates.ok ? `⬆ ${_unref$7(formatBytes)(Math.max(0, __props.siteLiveRates.d_up || 0))} / ⬇ ${_unref$7(formatBytes)(Math.max(0, __props.siteLiveRates.d_down || 0))}` : '—'), 1)
                  ])
                ], 64))
              : _createCommentVNode$d("", true)
          ]),
          (__props.siteLiveAlerts.length)
            ? (_openBlock$f(), _createElementBlock$d("div", _hoisted_32$3, [
                (_openBlock$f(true), _createElementBlock$d(_Fragment$d, null, _renderList$b(__props.siteLiveAlerts, (alert, idx) => {
                  return (_openBlock$f(), _createElementBlock$d("div", {
                    key: `${alert.kind}-${idx}`,
                    class: _normalizeClass$5(["magicflow-live-alert", `magicflow-live-alert--${alert.level || 'info'}`])
                  }, _toDisplayString$f(alert.text), 3))
                }), 128))
              ]))
            : _createCommentVNode$d("", true)
        ]),
        _: 1
      }),
      _createVNode$e(_component_VSheet, {
        tag: "section",
        class: "magicflow-panel app-surface-static"
      }, {
        default: _withCtx$d(() => [
          _createElementVNode$f("header", _hoisted_33$3, [
            _createElementVNode$f("div", null, [
              _cache[50] || (_cache[50] = _createElementVNode$f("div", { class: "text-subtitle-1 font-weight-medium" }, "最近一次运行", -1)),
              _createElementVNode$f("div", _hoisted_34$3, _toDisplayString$f(__props.detailStats.last_run_at ? _unref$7(formatDateTime)(__props.detailStats.last_run_at) : '暂无运行记录'), 1)
            ]),
            (__props.detailStats.last_error)
              ? (_openBlock$f(), _createBlock$d(_component_VChip, {
                  key: 0,
                  color: "error",
                  size: "small",
                  variant: "tonal"
                }, {
                  default: _withCtx$d(() => [...(_cache[51] || (_cache[51] = [
                    _createTextVNode$e("失败", -1)
                  ]))]),
                  _: 1
                }))
              : (__props.detailStats.last_run_status)
                ? (_openBlock$f(), _createBlock$d(_component_VChip, {
                    key: 1,
                    color: __props.detailStats.last_run_status === 'done' ? 'success' : __props.detailStats.last_run_status === 'failed' ? 'error' : 'secondary',
                    size: "small",
                    variant: "tonal"
                  }, {
                    default: _withCtx$d(() => [
                      _createTextVNode$e(_toDisplayString$f(_unref$7(runStatusText)(__props.detailStats.last_run_status)), 1)
                    ]),
                    _: 1
                  }, 8, ["color"]))
                : (__props.detailStats.last_success_at)
                  ? (_openBlock$f(), _createBlock$d(_component_VChip, {
                      key: 2,
                      color: "success",
                      size: "small",
                      variant: "tonal"
                    }, {
                      default: _withCtx$d(() => [...(_cache[52] || (_cache[52] = [
                        _createTextVNode$e("完成", -1)
                      ]))]),
                      _: 1
                    }))
                  : _createCommentVNode$d("", true)
          ]),
          _createElementVNode$f("div", _hoisted_35$3, [
            _createElementVNode$f("div", null, [
              _cache[53] || (_cache[53] = _createElementVNode$f("span", null, "上次成功", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(__props.detailStats.last_success_at ? _unref$7(formatDateTime)(__props.detailStats.last_success_at) : '-'), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[54] || (_cache[54] = _createElementVNode$f("span", null, "本次状态", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(_unref$7(runStatusText)(__props.detailStats.last_run_status)), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[55] || (_cache[55] = _createElementVNode$f("span", null, "本次耗时", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(_unref$7(formatDurationSeconds)(__props.detailStats.last_run_duration)), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[56] || (_cache[56] = _createElementVNode$f("span", null, "本次新增 / 复用", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(__props.detailStats.last_added || 0) + " / " + _toDisplayString$f(__props.detailStats.last_reused || 0), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[57] || (_cache[57] = _createElementVNode$f("span", null, "本次删除", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(__props.detailStats.last_deleted || 0), 1)
            ]),
            _createElementVNode$f("div", null, [
              _cache[58] || (_cache[58] = _createElementVNode$f("span", null, "当前托管 / 受保护", -1)),
              _createElementVNode$f("strong", null, _toDisplayString$f(__props.detailStats.last_kept || 0) + " / " + _toDisplayString$f(__props.detailStats.protected_count || 0), 1)
            ])
          ]),
          (__props.detailStats.last_run_reason)
            ? (_openBlock$f(), _createBlock$d(_component_VAlert, {
                key: 0,
                type: "info",
                variant: "tonal",
                density: "compact",
                class: "mb-2"
              }, {
                default: _withCtx$d(() => [
                  _createTextVNode$e(" 本轮说明：" + _toDisplayString$f(__props.detailStats.last_run_reason), 1)
                ]),
                _: 1
              }))
            : _createCommentVNode$d("", true),
          (__props.detailStats.last_error)
            ? (_openBlock$f(), _createBlock$d(_component_VAlert, {
                key: 1,
                type: "error",
                variant: "tonal",
                density: "compact"
              }, {
                default: _withCtx$d(() => [
                  _createTextVNode$e(_toDisplayString$f(__props.detailStats.last_error), 1)
                ]),
                _: 1
              }))
            : _createCommentVNode$d("", true),
          _createVNode$e(_component_VBtn, {
            variant: "text",
            color: "primary",
            "append-icon": "mdi-arrow-right",
            onClick: _cache[0] || (_cache[0] = $event => (emit('open-entry', 'diagnostics')))
          }, {
            default: _withCtx$d(() => [...(_cache[59] || (_cache[59] = [
              _createTextVNode$e(" 查看运行诊断 ", -1)
            ]))]),
            _: 1
          })
        ]),
        _: 1
      })
    ])
  ], 64))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const OverviewTab = Object.assign(_sfc_main$f, { __scopeId: 'data-v-be190652' })

export default OverviewTab
