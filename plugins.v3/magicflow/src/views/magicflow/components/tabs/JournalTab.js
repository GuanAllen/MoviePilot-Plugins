// JournalTab —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './JournalTab.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$7,
  createBlock: _createBlock$6,
  createCommentVNode: _createCommentVNode$7,
  createElementBlock: _createElementBlock$7,
  createElementVNode: _createElementVNode$8,
  createTextVNode: _createTextVNode$7,
  createVNode: _createVNode$7,
  normalizeClass: _normalizeClass$3,
  normalizeStyle: _normalizeStyle$1,
  openBlock: _openBlock$8,
  renderList: _renderList$7,
  resolveComponent: _resolveComponent$8,
  toDisplayString: _toDisplayString$8,
  unref: _unref$3,
  withCtx: _withCtx$6,
} = __vue

import index from '../../index.vue'
import { formatDateTime } from '../../../../utils.js'
import { hasOpDetail, itemSourceText, opDetailItems, operationColor, operationDuration, operationIcon, operationKindText, operationStateText, operationSummary } from '../../opsDisplay.js'
import { useCandidates } from '../../composables/useCandidates.js'
import { useOperations } from '../../composables/useOperations.js'
import { useTaskDetail } from '../../composables/useTaskDetail.js'

const _hoisted_1$7 = { class: "magicflow-panel__head" };
const _hoisted_2$7 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_3$6 = { class: "magicflow-flow__chain" };
const _hoisted_4$6 = { class: "magicflow-flow__dot" };
const _hoisted_5$6 = { class: "magicflow-flow__label" };
const _hoisted_6$5 = { class: "magicflow-panel__head" };
const _hoisted_7$5 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_8$5 = {
  key: 0,
  class: "magicflow-reasons"
};
const _hoisted_9$5 = { class: "magicflow-reason__track" };
const _hoisted_10$5 = {
  key: 1,
  class: "magicflow-table-empty"
};
const _hoisted_11$5 = { class: "magicflow-panel__head" };
const _hoisted_12$5 = { class: "magicflow-ops-filter" };
const _hoisted_13$4 = { class: "magicflow-events" };
const _hoisted_14$4 = {
  key: 0,
  class: "text-error"
};
const _hoisted_15$4 = ["onClick"];
const _hoisted_16$4 = {
  key: 2,
  class: "magicflow-events__detail"
};
const _hoisted_17$4 = { class: "magicflow-events__detail-line" };
const _hoisted_18$4 = {
  key: 0,
  class: "magicflow-events__detail-src"
};
const _hoisted_19$4 = ["title"];
const _hoisted_20$4 = {
  key: 1,
  class: "magicflow-events__detail-hash"
};
const _hoisted_21$3 = { class: "magicflow-events__detail-sub" };
const _hoisted_22$2 = {
  key: 0,
  class: "magicflow-table-empty"
};

const {computed: computed$q,reactive} = __vue;

// props：data = useTaskDetail / useCandidates / useOperations 的「状态 + 派生」整体下传（含 expandedOps），只读；
//        scope = 操作记录的类型筛选（原 opsKind），双向：emit update:scope；
//        task = 当前任务（原 selectedTask），用于判定刷流 / 养护。

const _sfc_main$8 = {
  __name: 'JournalTab',
  props: {
  data: { type: Object, required: true },
  scope: { type: [String, Number], default: '' },
  task: { type: Object, default: null },
},
  emits: ['update:scope', 'refresh', 'toggle-detail', 'open-pushes'],
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 运行诊断面板（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 契约见 docs/REFACTOR-FRONTEND.md §5：props `data` `scope` `task`；emits `update:scope` `refresh`。
// —— 运行诊断含：运行流程 / 过滤原因 / 操作记录（类型筛选可展开明细）。
const props = __props;
const emit = __emit;

// reactive() 解包 data 里的 ref / computed，模板沿用原 index.vue 的写法 `data.xxx`。
const data = reactive(props.data);

const taskIsBrush = computed$q(() => props.task?.task_type === 'brush');

function onScopeChange(value) { emit('update:scope', value); }

// —— 只属于本文件的展示函数 ——
// 展开态：本面板的展开表来自 props.data.expandedOps（弹窗读的是 props.expandedOps，不是同一份）
function isOpDetailOpen(opId) {
  return !!(data.expandedOps || {})[opId]
}

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$8("VIcon");
  const _component_VAlert = _resolveComponent$8("VAlert");
  const _component_VSheet = _resolveComponent$8("VSheet");
  const _component_VBtn = _resolveComponent$8("VBtn");
  const _component_VSelect = _resolveComponent$8("VSelect");
  const _component_VChip = _resolveComponent$8("VChip");

  return (_openBlock$8(), _createElementBlock$7(_Fragment$7, null, [
    _createVNode$7(_component_VSheet, {
      tag: "section",
      class: "magicflow-panel magicflow-flow app-surface-static"
    }, {
      default: _withCtx$6(() => [
        _createElementVNode$8("header", _hoisted_1$7, [
          _createElementVNode$8("div", null, [
            _cache[2] || (_cache[2] = _createElementVNode$8("div", { class: "text-subtitle-1 font-weight-medium" }, "运行流程", -1)),
            _createElementVNode$8("div", _hoisted_2$7, [
              _createTextVNode$7(_toDisplayString$8(data.detailStats.run_active ? (taskIsBrush.value ? '正在执行本轮刷流…' : '正在执行本轮养护…') : (data.detailStats.last_run_at ? `最近执行 ${_unref$3(formatDateTime)(data.detailStats.last_run_at)}` : '尚未运行')) + " · 翻页游标 " + _toDisplayString$8(data.detailStats.page_cursor ?? 0), 1),
              (data.detailStats.last_phase_detail)
                ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
                    _createTextVNode$7(" · " + _toDisplayString$8(data.detailStats.last_phase_detail), 1)
                  ], 64))
                : _createCommentVNode$7("", true)
            ])
          ]),
          _createElementVNode$8("span", {
            class: _normalizeClass$3(["magicflow-flow__tag", { 'is-live': data.detailStats.run_active, 'is-error': data.detailStats.last_run_status === 'failed' }])
          }, [
            _cache[3] || (_cache[3] = _createElementVNode$8("i", null, null, -1)),
            _createTextVNode$7(" " + _toDisplayString$8(data.flowPhaseText), 1)
          ], 2)
        ]),
        _createElementVNode$8("ol", _hoisted_3$6, [
          (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(data.flowNodes, (node, i) => {
            return (_openBlock$8(), _createElementBlock$7("li", {
              key: node.key,
              class: _normalizeClass$3(["magicflow-flow__node", `is-${node.state}`])
            }, [
              _createElementVNode$8("span", _hoisted_4$6, [
                (node.state === 'done' || node.state === 'running')
                  ? (_openBlock$8(), _createBlock$6(_component_VIcon, {
                      key: 0,
                      icon: "mdi-check",
                      size: "16"
                    }))
                  : (node.state === 'error')
                    ? (_openBlock$8(), _createBlock$6(_component_VIcon, {
                        key: 1,
                        icon: "mdi-alert",
                        size: "16"
                      }))
                    : _createCommentVNode$7("", true)
              ]),
              _createElementVNode$8("span", _hoisted_5$6, _toDisplayString$8(node.label), 1),
              (i < data.flowNodes.length - 1)
                ? (_openBlock$8(), _createElementBlock$7("span", {
                    key: 0,
                    class: _normalizeClass$3(["magicflow-flow__line", { 'is-done': node.state === 'done' }])
                  }, null, 2))
                : _createCommentVNode$7("", true)
            ], 2))
          }), 128))
        ]),
        (data.detailStats.last_error)
          ? (_openBlock$8(), _createBlock$6(_component_VAlert, {
              key: 0,
              type: "error",
              variant: "tonal",
              density: "compact",
              class: "mt-3"
            }, {
              default: _withCtx$6(() => [
                _createTextVNode$7(_toDisplayString$8(data.detailStats.last_error), 1)
              ]),
              _: 1
            }))
          : _createCommentVNode$7("", true)
      ]),
      _: 1
    }),
    _createVNode$7(_component_VSheet, {
      tag: "section",
      class: "magicflow-panel app-surface-static mt-4"
    }, {
      default: _withCtx$6(() => [
        _createElementVNode$8("header", _hoisted_6$5, [
          _createElementVNode$8("div", null, [
            _cache[4] || (_cache[4] = _createElementVNode$8("div", { class: "text-subtitle-1 font-weight-medium" }, "过滤原因", -1)),
            _createElementVNode$8("div", _hoisted_7$5, [
              _createTextVNode$7(" 被规则拦截的候选分布 · 共抓取 " + _toDisplayString$8(data.candidateRawTotal) + " 个，通过 " + _toDisplayString$8((data.candidateData.candidates || []).length) + " ", 1),
              (data.candidateLoadedAt)
                ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
                    _createTextVNode$7(" · 统计于 " + _toDisplayString$8(_unref$3(formatDateTime)(data.candidateLoadedAt)), 1)
                  ], 64))
                : _createCommentVNode$7("", true)
            ])
          ])
        ]),
        (data.reasonEntries.length)
          ? (_openBlock$8(), _createElementBlock$7("div", _hoisted_8$5, [
              (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(data.reasonEntries, (item) => {
                return (_openBlock$8(), _createElementBlock$7("div", {
                  key: item.label,
                  class: "magicflow-reason"
                }, [
                  _createElementVNode$8("div", null, [
                    _createElementVNode$8("span", null, _toDisplayString$8(item.label), 1),
                    _createElementVNode$8("strong", null, _toDisplayString$8(item.count), 1)
                  ]),
                  _createElementVNode$8("span", _hoisted_9$5, [
                    _createElementVNode$8("i", {
                      style: _normalizeStyle$1({ width: `${(item.count / data.maxReasonCount) * 100}%` })
                    }, null, 4)
                  ])
                ]))
              }), 128))
            ]))
          : (_openBlock$8(), _createElementBlock$7("div", _hoisted_10$5, "本轮无过滤原因记录（候选全通过或列表为空）")),
        (data.detailStats.last_run_status === 'noop' && data.detailStats.last_run_reason)
          ? (_openBlock$8(), _createBlock$6(_component_VAlert, {
              key: 2,
              type: "info",
              variant: "tonal",
              density: "compact",
              class: "mt-3"
            }, {
              default: _withCtx$6(() => [
                _createTextVNode$7(" 最近一次执行未进入候选过滤：" + _toDisplayString$8(data.detailStats.last_run_reason), 1)
              ]),
              _: 1
            }))
          : _createCommentVNode$7("", true)
      ]),
      _: 1
    }),
    _createVNode$7(_component_VSheet, {
      tag: "section",
      class: "magicflow-panel app-surface-static mt-4"
    }, {
      default: _withCtx$6(() => [
        _createElementVNode$8("header", _hoisted_11$5, [
          _cache[7] || (_cache[7] = _createElementVNode$8("div", null, [
            _createElementVNode$8("div", { class: "text-subtitle-1 font-weight-medium" }, "操作记录"),
            _createElementVNode$8("div", { class: "text-body-2 text-medium-emphasis" }, "执行 / 选种 / 删种 / 保护 / 标签 的流水（可展开明细）")
          ], -1)),
          _createVNode$7(_component_VBtn, {
            variant: "text",
            color: "primary",
            "prepend-icon": "mdi-send-check-outline",
            onClick: _cache[0] || (_cache[0] = $event => (emit('open-pushes')))
          }, {
            default: _withCtx$6(() => [...(_cache[5] || (_cache[5] = [
              _createTextVNode$7("加种推送", -1)
            ]))]),
            _: 1
          }),
          _createVNode$7(_component_VBtn, {
            variant: "text",
            color: "primary",
            "prepend-icon": "mdi-refresh",
            onClick: _cache[1] || (_cache[1] = $event => (emit('refresh')))
          }, {
            default: _withCtx$6(() => [...(_cache[6] || (_cache[6] = [
              _createTextVNode$7("刷新", -1)
            ]))]),
            _: 1
          })
        ]),
        _createElementVNode$8("div", _hoisted_12$5, [
          _cache[8] || (_cache[8] = _createElementVNode$8("span", { class: "magicflow-ops-filter__label" }, "类型", -1)),
          _createVNode$7(_component_VSelect, {
            "model-value": __props.scope,
            items: data.opsKindItems,
            "item-title": "label",
            "item-value": "value",
            density: "compact",
            variant: "outlined",
            "hide-details": "",
            class: "magicflow-ops-filter__select",
            "onUpdate:modelValue": onScopeChange
          }, null, 8, ["model-value", "items"])
        ]),
        _createElementVNode$8("div", _hoisted_13$4, [
          (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(data.opsFiltered, (record) => {
            return (_openBlock$8(), _createElementBlock$7("article", {
              key: record.operation_id
            }, [
              _createVNode$7(_component_VIcon, {
                icon: _unref$3(operationIcon)(record.kind),
                color: _unref$3(operationColor)(record)
              }, null, 8, ["icon", "color"]),
              _createElementVNode$8("div", null, [
                _createElementVNode$8("strong", null, [
                  _createTextVNode$7(_toDisplayString$8(_unref$3(operationKindText)(record.kind)) + " ", 1),
                  _createVNode$7(_component_VChip, {
                    size: "x-small",
                    variant: "tonal",
                    color: _unref$3(operationColor)(record),
                    class: "ml-2"
                  }, {
                    default: _withCtx$6(() => [
                      _createTextVNode$7(_toDisplayString$8(_unref$3(operationStateText)(record.state)), 1)
                    ]),
                    _: 2
                  }, 1032, ["color"])
                ]),
                _createElementVNode$8("span", null, _toDisplayString$8(_unref$3(operationSummary)(record)), 1),
                _createElementVNode$8("span", null, [
                  _createTextVNode$7(_toDisplayString$8(_unref$3(formatDateTime)(record.created_at)) + " · 耗时 " + _toDisplayString$8(_unref$3(operationDuration)(record)) + " ", 1),
                  (_unref$3(hasOpDetail)(record))
                    ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
                        _createTextVNode$7(" · " + _toDisplayString$8(_unref$3(opDetailItems)(record).length) + " 条明细", 1)
                      ], 64))
                    : _createCommentVNode$7("", true)
                ]),
                (record.error_message)
                  ? (_openBlock$8(), _createElementBlock$7("span", _hoisted_14$4, _toDisplayString$8(record.error_message), 1))
                  : _createCommentVNode$7("", true),
                (_unref$3(hasOpDetail)(record))
                  ? (_openBlock$8(), _createElementBlock$7("button", {
                      key: 1,
                      type: "button",
                      class: "magicflow-events__toggle",
                      onClick: $event => (emit('toggle-detail', record.operation_id))
                    }, [
                      _createTextVNode$7(_toDisplayString$8(isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细') + " ", 1),
                      _createVNode$7(_component_VIcon, {
                        icon: isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down',
                        size: "14"
                      }, null, 8, ["icon"])
                    ], 8, _hoisted_15$4))
                  : _createCommentVNode$7("", true),
                (isOpDetailOpen(record.operation_id))
                  ? (_openBlock$8(), _createElementBlock$7("ul", _hoisted_16$4, [
                      (_openBlock$8(true), _createElementBlock$7(_Fragment$7, null, _renderList$7(_unref$3(opDetailItems)(record), (it, idx) => {
                        return (_openBlock$8(), _createElementBlock$7("li", { key: idx }, [
                          _createElementVNode$8("span", _hoisted_17$4, [
                            (_unref$3(itemSourceText)(it.source))
                              ? (_openBlock$8(), _createElementBlock$7("em", _hoisted_18$4, _toDisplayString$8(_unref$3(itemSourceText)(it.source)), 1))
                              : _createCommentVNode$7("", true),
                            _createElementVNode$8("span", {
                              class: "magicflow-events__detail-title",
                              title: it.title || it.hash
                            }, _toDisplayString$8(it.title || it.hash || '—'), 9, _hoisted_19$4),
                            (it.hash)
                              ? (_openBlock$8(), _createElementBlock$7("code", _hoisted_20$4, _toDisplayString$8(String(it.hash).slice(0, 12)), 1))
                              : _createCommentVNode$7("", true)
                          ]),
                          _createElementVNode$8("span", _hoisted_21$3, [
                            (it.reason)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 0 }, [
                                  _createTextVNode$7(_toDisplayString$8(it.reason), 1)
                                ], 64))
                              : _createCommentVNode$7("", true),
                            (it.size_gb)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 1 }, [
                                  _createTextVNode$7(" · " + _toDisplayString$8(Number(it.size_gb).toFixed(2)) + "G", 1)
                                ], 64))
                              : _createCommentVNode$7("", true),
                            (it.seeders)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 2 }, [
                                  _createTextVNode$7(" · 做种 " + _toDisplayString$8(it.seeders), 1)
                                ], 64))
                              : _createCommentVNode$7("", true),
                            (it.tags)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 3 }, [
                                  _createTextVNode$7(" · " + _toDisplayString$8(it.tags), 1)
                                ], 64))
                              : _createCommentVNode$7("", true),
                            (it.bonus_per_hour)
                              ? (_openBlock$8(), _createElementBlock$7(_Fragment$7, { key: 4 }, [
                                  _createTextVNode$7(" · " + _toDisplayString$8(Number(it.bonus_per_hour).toFixed(2)) + "/h", 1)
                                ], 64))
                              : _createCommentVNode$7("", true)
                          ])
                        ]))
                      }), 128))
                    ]))
                  : _createCommentVNode$7("", true)
              ])
            ]))
          }), 128)),
          (!data.opsFiltered.length)
            ? (_openBlock$8(), _createElementBlock$7("div", _hoisted_22$2, "暂无操作记录"))
            : _createCommentVNode$7("", true)
        ])
      ]),
      _: 1
    })
  ], 64))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const JournalTab = Object.assign(_sfc_main$8, { __scopeId: 'data-v-d0146d4d' })

export default JournalTab
