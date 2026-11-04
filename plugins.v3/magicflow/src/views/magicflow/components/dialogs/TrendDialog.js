// TrendDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './TrendDialog.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$o,
  createBlock: _createBlock$p,
  createCommentVNode: _createCommentVNode$p,
  createElementBlock: _createElementBlock$o,
  createElementVNode: _createElementVNode$s,
  createTextVNode: _createTextVNode$r,
  createVNode: _createVNode$r,
  normalizeClass: _normalizeClass$f,
  normalizeStyle: _normalizeStyle$3,
  openBlock: _openBlock$s,
  renderList: _renderList$m,
  resolveComponent: _resolveComponent$s,
  toDisplayString: _toDisplayString$s,
  unref: _unref$c,
  withCtx: _withCtx$p,
} = __vue

import { formatBytes } from '../../../../utils.js'

const _hoisted_1$q = { class: "mf-trend__pick" };
const _hoisted_2$o = { class: "mf-trend__verdict" };
const _hoisted_3$n = {
  key: 0,
  class: "mf-trend__sub"
};
const _hoisted_4$n = { class: "mf-trend__verdict" };
const _hoisted_5$n = { class: "mf-trend__sub" };
const _hoisted_6$m = {
  key: 1,
  class: "mf-trend__metrics"
};
const _hoisted_7$l = { class: "mf-trend__metric-k" };
const _hoisted_8$j = {
  key: 2,
  class: "mf-trend__sec"
};
const _hoisted_9$h = { class: "mf-trend__factor-h" };
const _hoisted_10$h = { class: "mf-trend__bar" };
const _hoisted_11$g = { class: "mf-trend__factor-d" };
const _hoisted_12$g = {
  key: 3,
  class: "mf-trend__sec"
};
const _hoisted_13$e = { class: "mf-trend__sec-t" };
const _hoisted_14$e = { class: "mf-spark-grid" };
const _hoisted_15$e = { class: "mf-spark__head" };
const _hoisted_16$e = {
  class: "mf-spark__svg",
  viewBox: "0 0 100 26",
  preserveAspectRatio: "none"
};
const _hoisted_17$e = ["d"];
const _hoisted_18$e = { class: "mf-spark__foot" };
const _hoisted_19$d = {
  key: 4,
  class: "mf-trend__sec"
};
const _hoisted_20$c = { class: "mf-trend__sec-t" };
const _hoisted_21$b = { class: "mf-trend__days" };
const _hoisted_22$a = ["title"];
const _hoisted_23$9 = {
  key: 5,
  class: "mf-trend__sec"
};
const _hoisted_24$9 = { class: "mf-trend__advice" };
const _hoisted_25$9 = {
  key: 6,
  class: "mf-trend__evi"
};

const {computed: computed$B} = __vue;


const _sfc_main$s = {
  __name: 'TrendDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  scope: { type: String, default: 'site' },
  ident: { type: String, default: '' },
  hours: { type: Number, default: 72 },
  why: { type: Object, default: null },
  daily: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  scopeItems: { type: Array, default: () => [] },
  uploadIncrement: { type: Number, default: null },
},
  emits: ['update:modelValue', 'update:scope', 'update:ident', 'update:hours', 'refresh'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const WINDOWS = [
  { title: '24h', value: 24 },
  { title: '72h', value: 72 },
  { title: '7d', value: 168 },
];

const level = computed$B(() => props.why?.level || 'unknown');
const factors = computed$B(() => (Array.isArray(props.why?.factors) ? props.why.factors : []));
const advice = computed$B(() => (Array.isArray(props.why?.advice) ? props.why.advice : []));

const metrics = computed$B(() => {
  const r = props.why?.recent || {};
  const p = props.why?.prior || {};
  if (!r || !p || !Object.keys(r).length) return []
  const mk = (label, key, unit, digits) => {
    const rv = Number(r[key] ?? 0);
    const pv = Number(p[key] ?? 0);
    const pct = pv ? ((rv - pv) / Math.abs(pv)) * 100 : 0;
    return {
      key,
      label,
      value: `${rv.toFixed(digits)}${unit}`,
      delta: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`,
      good: pct >= 0,
    }
  };
  return [
    mk('时魔 /h', 'bonus', '', 2),
    mk('做种数', 'seeds', ' 个', 0),
    mk('单种魔力', 'per_seed', '', 3),
    mk('体积', 'gb', ' GB', 1),
  ]
});

const deltaLine = computed$B(() => {
  const d = props.why?.delta;
  if (!d) return ''
  return `时魔 ${Number(d.bonus) >= 0 ? '+' : ''}${Number(d.bonus).toFixed(2)}/h（${Number(d.bonus_pct).toFixed(1)}%）· 做种数 ${Number(d.seeds) >= 0 ? '+' : ''}${Number(d.seeds).toFixed(0)} 个 · 对比窗口前后等长两段`
});

function spark(series, field) {
  const pts = (series || []).filter(p => p && p[field] !== null && p[field] !== undefined);
  if (pts.length < 2) return null
  const vs = pts.map(p => Number(p[field]) || 0);
  const min = Math.min(...vs);
  const max = Math.max(...vs);
  const span = (max - min) || 1;
  const W = 100;
  const H = 26;
  const step = W / (vs.length - 1);
  const path = vs
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(2)},${(H - 3 - ((v - min) / span) * (H - 6)).toFixed(2)}`)
    .join(' ');
  const first = vs[0];
  const last = vs[vs.length - 1];
  const delta = first ? ((last - first) / Math.abs(first)) * 100 : 0;
  return {
    path,
    min: min.toFixed(1),
    max: max.toFixed(1),
    last: last.toFixed(field === 'seeds' ? 0 : 2),
    lastRaw: last,
    delta: `${delta >= 0 ? '▲' : '▼'}${Math.abs(delta).toFixed(1)}%`,
    good: delta >= 0,
    count: vs.length,
  }
}

const cards = computed$B(() => {
  const src = props.why?.series || [];
  const base = [
    { key: 'bonus', label: '时魔 /h', unit: '', s: spark(src, 'bonus') },
    { key: 'seeds', label: '做种数', unit: ' 个', s: spark(src, 'seeds') },
    { key: 'gb', label: '自身体积', unit: ' GB', s: spark(src, 'gb') },
    { key: 'reuse', label: '辅种体积', unit: ' GB', s: spark(src, 'reuse_gb') },
    // ★ 19.11.0：上传口径时序（qB 本地累计 + 当前速率），按时间看「干了多少活」
    { key: 'uploaded', label: '上传量', unit: '', s: spark(src, 'uploaded'), bytes: true },
    { key: 'up_speed', label: '上传速率', unit: '/s', s: spark(src, 'up_speed'), bytes: true, speed: true },
  ].filter(c => c.s);
  return base.map(c => {
    const merged = { ...c, ...c.s };
    if (c.bytes) {
      const v = Number(merged.lastRaw) || 0;
      merged.last = formatBytes(v);
      merged.unit = c.speed ? '/s' : '';
    }
    return merged
  })
});

const dailyBars = computed$B(() => {
  const rows = (props.daily || []).slice(-21);
  if (!rows.length) return []
  const vals = rows.map(r => Number(r.bonus) || 0);
  const max = Math.max(...vals) || 1;
  return rows.map(r => {
    const d = new Date((Number(r.t) || 0) * 1000);
    const label = `${d.getMonth() + 1}/${d.getDate()}`;
    return {
      t: r.t,
      h: Math.max(2, Math.round(((Number(r.bonus) || 0) / max) * 100)),
      label,
      tip: `${label}：${(Number(r.bonus) || 0).toFixed(2)}/h · 做种 ${(Number(r.seeds) || 0).toFixed(0)}`,
    }
  })
});

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$s("VIcon");
  const _component_VSpacer = _resolveComponent$s("VSpacer");
  const _component_VBtn = _resolveComponent$s("VBtn");
  const _component_VCardTitle = _resolveComponent$s("VCardTitle");
  const _component_VDivider = _resolveComponent$s("VDivider");
  const _component_VBtnToggle = _resolveComponent$s("VBtnToggle");
  const _component_VSelect = _resolveComponent$s("VSelect");
  const _component_VAlert = _resolveComponent$s("VAlert");
  const _component_VSheet = _resolveComponent$s("VSheet");
  const _component_VCardText = _resolveComponent$s("VCardText");
  const _component_VCard = _resolveComponent$s("VCard");
  const _component_VDialog = _resolveComponent$s("VDialog");

  return (_openBlock$s(), _createBlock$p(_component_VDialog, {
    "model-value": __props.modelValue,
    "max-width": "780",
    scrollable: "",
    "onUpdate:modelValue": _cache[5] || (_cache[5] = v => emit('update:modelValue', v))
  }, {
    default: _withCtx$p(() => [
      _createVNode$r(_component_VCard, { class: "mf-trend" }, {
        default: _withCtx$p(() => [
          _createVNode$r(_component_VCardTitle, { class: "mf-trend__title" }, {
            default: _withCtx$p(() => [
              _createVNode$r(_component_VIcon, {
                icon: "mdi-chart-timeline-variant",
                size: "20",
                class: "me-2"
              }),
              _cache[6] || (_cache[6] = _createElementVNode$s("span", { class: "text-subtitle-1 font-weight-medium" }, "魔力趋势与归因", -1)),
              _createVNode$r(_component_VSpacer),
              _createVNode$r(_component_VBtn, {
                icon: "mdi-refresh",
                variant: "text",
                size: "small",
                loading: __props.loading,
                title: "刷新",
                onClick: _cache[0] || (_cache[0] = $event => (emit('refresh')))
              }, null, 8, ["loading"]),
              _createVNode$r(_component_VBtn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                title: "关闭",
                onClick: _cache[1] || (_cache[1] = $event => (emit('update:modelValue', false)))
              })
            ]),
            _: 1
          }),
          _createVNode$r(_component_VDivider),
          _createVNode$r(_component_VCardText, { class: "mf-trend__body" }, {
            default: _withCtx$p(() => [
              _createElementVNode$s("div", _hoisted_1$q, [
                _createVNode$r(_component_VBtnToggle, {
                  "model-value": __props.scope,
                  density: "compact",
                  variant: "outlined",
                  mandatory: "",
                  divided: "",
                  "onUpdate:modelValue": _cache[2] || (_cache[2] = v => emit('update:scope', v))
                }, {
                  default: _withCtx$p(() => [
                    _createVNode$r(_component_VBtn, {
                      value: "site",
                      size: "small"
                    }, {
                      default: _withCtx$p(() => [...(_cache[7] || (_cache[7] = [
                        _createTextVNode$r("站点", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode$r(_component_VBtn, {
                      value: "task",
                      size: "small"
                    }, {
                      default: _withCtx$p(() => [...(_cache[8] || (_cache[8] = [
                        _createTextVNode$r("任务", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                }, 8, ["model-value"]),
                _createVNode$r(_component_VSelect, {
                  "model-value": __props.ident,
                  items: __props.scopeItems,
                  "item-title": "title",
                  "item-value": "value",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "",
                  placeholder: "选择对象",
                  class: "mf-trend__sel",
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = v => emit('update:ident', String(v || '')))
                }, null, 8, ["model-value", "items"]),
                _createVNode$r(_component_VBtnToggle, {
                  "model-value": __props.hours,
                  density: "compact",
                  variant: "outlined",
                  mandatory: "",
                  divided: "",
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = v => emit('update:hours', Number(v)))
                }, {
                  default: _withCtx$p(() => [
                    (_openBlock$s(), _createElementBlock$o(_Fragment$o, null, _renderList$m(WINDOWS, (w) => {
                      return _createVNode$r(_component_VBtn, {
                        key: w.value,
                        value: w.value,
                        size: "small"
                      }, {
                        default: _withCtx$p(() => [
                          _createTextVNode$r(_toDisplayString$s(w.title), 1)
                        ]),
                        _: 2
                      }, 1032, ["value"])
                    }), 64))
                  ]),
                  _: 1
                }, 8, ["model-value"])
              ]),
              (!__props.ident)
                ? (_openBlock$s(), _createBlock$p(_component_VAlert, {
                    key: 0,
                    density: "compact",
                    variant: "tonal",
                    type: "info",
                    class: "mt-3"
                  }, {
                    default: _withCtx$p(() => [
                      _createTextVNode$r(" 先选一个" + _toDisplayString$s(__props.scope === 'site' ? '站点' : '任务') + "，再看它的时魔走向与归因。 ", 1)
                    ]),
                    _: 1
                  }))
                : (_openBlock$s(), _createElementBlock$o(_Fragment$o, { key: 1 }, [
                    _createVNode$r(_component_VSheet, {
                      tag: "section",
                      class: _normalizeClass$f(["mf-trend__card", `is-${level.value}`])
                    }, {
                      default: _withCtx$p(() => [
                        _createElementVNode$s("div", _hoisted_2$o, _toDisplayString$s(__props.why?.verdict || '暂无结论（采样点不够）'), 1),
                        (deltaLine.value)
                          ? (_openBlock$s(), _createElementBlock$o("div", _hoisted_3$n, _toDisplayString$s(deltaLine.value), 1))
                          : _createCommentVNode$p("", true)
                      ]),
                      _: 1
                    }, 8, ["class"]),
                    (__props.scope === 'task' && __props.uploadIncrement != null)
                      ? (_openBlock$s(), _createBlock$p(_component_VSheet, {
                          key: 0,
                          tag: "section",
                          class: "mf-trend__card is-up",
                          style: {"margin-top":"8px"}
                        }, {
                          default: _withCtx$p(() => [
                            _createElementVNode$s("div", _hoisted_4$n, "该窗口（" + _toDisplayString$s(__props.hours) + "h）本任务实际上传", 1),
                            _createElementVNode$s("div", _hoisted_5$n, _toDisplayString$s(_unref$c(formatBytes)(__props.uploadIncrement)) + "（qB 本地累计，按采样差分取非负累加，种子轮换不丢值）", 1)
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode$p("", true),
                    (metrics.value.length)
                      ? (_openBlock$s(), _createElementBlock$o("div", _hoisted_6$m, [
                          (_openBlock$s(true), _createElementBlock$o(_Fragment$o, null, _renderList$m(metrics.value, (m) => {
                            return (_openBlock$s(), _createElementBlock$o("div", {
                              key: m.key,
                              class: "mf-trend__metric"
                            }, [
                              _createElementVNode$s("span", _hoisted_7$l, _toDisplayString$s(m.label), 1),
                              _createElementVNode$s("strong", null, _toDisplayString$s(m.value), 1),
                              _createElementVNode$s("em", {
                                class: _normalizeClass$f(m.good ? 'is-up' : 'is-down')
                              }, _toDisplayString$s(m.delta), 3)
                            ]))
                          }), 128))
                        ]))
                      : _createCommentVNode$p("", true),
                    (factors.value.length)
                      ? (_openBlock$s(), _createElementBlock$o("div", _hoisted_8$j, [
                          _cache[9] || (_cache[9] = _createElementVNode$s("div", { class: "mf-trend__sec-t" }, "因子拆解（时魔变化 ≈ 各因子之和）", -1)),
                          (_openBlock$s(true), _createElementBlock$o(_Fragment$o, null, _renderList$m(factors.value, (f) => {
                            return (_openBlock$s(), _createElementBlock$o("div", {
                              key: f.key,
                              class: "mf-trend__factor"
                            }, [
                              _createElementVNode$s("div", _hoisted_9$h, [
                                _createElementVNode$s("span", null, _toDisplayString$s(f.label), 1),
                                _createElementVNode$s("strong", {
                                  class: _normalizeClass$f(Number(f.delta) >= 0 ? 'is-up' : 'is-down')
                                }, _toDisplayString$s(Number(f.delta) >= 0 ? '+' : '') + _toDisplayString$s(Number(f.delta).toFixed(2)) + " /h · " + _toDisplayString$s(f.share) + "% ", 3)
                              ]),
                              _createElementVNode$s("div", _hoisted_10$h, [
                                _createElementVNode$s("i", {
                                  style: _normalizeStyle$3({ width: Math.max(2, Number(f.share) || 0) + '%' }),
                                  class: _normalizeClass$f(Number(f.delta) >= 0 ? 'is-up' : 'is-down')
                                }, null, 6)
                              ]),
                              _createElementVNode$s("div", _hoisted_11$g, _toDisplayString$s(f.detail), 1)
                            ]))
                          }), 128))
                        ]))
                      : _createCommentVNode$p("", true),
                    (cards.value.length)
                      ? (_openBlock$s(), _createElementBlock$o("div", _hoisted_12$g, [
                          _createElementVNode$s("div", _hoisted_13$e, "小时趋势（最近 " + _toDisplayString$s(__props.hours) + " 小时）", 1),
                          _createElementVNode$s("div", _hoisted_14$e, [
                            (_openBlock$s(true), _createElementBlock$o(_Fragment$o, null, _renderList$m(cards.value, (c) => {
                              return (_openBlock$s(), _createElementBlock$o("div", {
                                key: c.key,
                                class: "mf-spark"
                              }, [
                                _createElementVNode$s("div", _hoisted_15$e, [
                                  _createElementVNode$s("span", null, _toDisplayString$s(c.label), 1),
                                  _createElementVNode$s("strong", null, [
                                    _createTextVNode$r(_toDisplayString$s(c.last) + _toDisplayString$s(c.unit), 1),
                                    _createElementVNode$s("em", {
                                      class: _normalizeClass$f(c.good ? 'is-up' : 'is-down')
                                    }, _toDisplayString$s(c.delta), 3)
                                  ])
                                ]),
                                (_openBlock$s(), _createElementBlock$o("svg", _hoisted_16$e, [
                                  _createElementVNode$s("path", {
                                    d: c.path,
                                    fill: "none",
                                    class: "mf-spark__line",
                                    "vector-effect": "non-scaling-stroke"
                                  }, null, 8, _hoisted_17$e)
                                ])),
                                _createElementVNode$s("div", _hoisted_18$e, [
                                  _createElementVNode$s("span", null, _toDisplayString$s(c.count) + " 点", 1),
                                  _createElementVNode$s("span", null, "低 " + _toDisplayString$s(c.min) + " · 高 " + _toDisplayString$s(c.max), 1)
                                ])
                              ]))
                            }), 128))
                          ])
                        ]))
                      : _createCommentVNode$p("", true),
                    (dailyBars.value.length)
                      ? (_openBlock$s(), _createElementBlock$o("div", _hoisted_19$d, [
                          _createElementVNode$s("div", _hoisted_20$c, "每日时魔（最近 " + _toDisplayString$s(dailyBars.value.length) + " 天，日报落盘 180 天）", 1),
                          _createElementVNode$s("div", _hoisted_21$b, [
                            (_openBlock$s(true), _createElementBlock$o(_Fragment$o, null, _renderList$m(dailyBars.value, (d) => {
                              return (_openBlock$s(), _createElementBlock$o("div", {
                                key: d.t,
                                class: "mf-trend__day",
                                title: d.tip
                              }, [
                                _createElementVNode$s("i", {
                                  style: _normalizeStyle$3({ height: d.h + '%' })
                                }, null, 4),
                                _createElementVNode$s("span", null, _toDisplayString$s(d.label), 1)
                              ], 8, _hoisted_22$a))
                            }), 128))
                          ])
                        ]))
                      : _createCommentVNode$p("", true),
                    (advice.value.length)
                      ? (_openBlock$s(), _createElementBlock$o("div", _hoisted_23$9, [
                          _cache[10] || (_cache[10] = _createElementVNode$s("div", { class: "mf-trend__sec-t" }, "怎么办", -1)),
                          _createElementVNode$s("ul", _hoisted_24$9, [
                            (_openBlock$s(true), _createElementBlock$o(_Fragment$o, null, _renderList$m(advice.value, (a, i) => {
                              return (_openBlock$s(), _createElementBlock$o("li", { key: i }, _toDisplayString$s(a), 1))
                            }), 128))
                          ])
                        ]))
                      : _createCommentVNode$p("", true),
                    (__props.why?.evidence)
                      ? (_openBlock$s(), _createElementBlock$o("div", _hoisted_25$9, _toDisplayString$s(__props.why.evidence), 1))
                      : _createCommentVNode$p("", true)
                  ], 64))
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["model-value"]))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const TrendDialog = Object.assign(_sfc_main$s, { __scopeId: 'data-v-94fe1d07' })

export default TrendDialog
