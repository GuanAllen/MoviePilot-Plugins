// OndemandDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './OndemandDialog.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$j,
  createBlock: _createBlock$j,
  createCommentVNode: _createCommentVNode$j,
  createElementBlock: _createElementBlock$j,
  createElementVNode: _createElementVNode$m,
  createTextVNode: _createTextVNode$l,
  createVNode: _createVNode$l,
  mergeModels: _mergeModels$b,
  normalizeClass: _normalizeClass$a,
  openBlock: _openBlock$m,
  renderList: _renderList$h,
  resolveComponent: _resolveComponent$m,
  toDisplayString: _toDisplayString$m,
  unref: _unref$a,
  useModel: _useModel$b,
  withCtx: _withCtx$j,
  withKeys: _withKeys
} = __vue

import SilentPoolDialog from './SilentPoolDialog.vue'
import { fmtSizeGb, odAltTitle, odEtaText, odIsPaused, odMainTitle, odPct, odSpeed, odStageColor, odSubTitle, odTraffic, useOndemand } from '../../composables/useOndemand.js'
import { tsText } from '../../format.js'
import { useSignin } from '../../composables/useSignin.js'
import { useTasks } from '../../composables/useTasks.js'

const _hoisted_1$k = { class: "magicflow-settings-dialog__head" };
const _hoisted_2$i = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_3$h = { class: "magicflow-od-search" };
const _hoisted_4$h = { class: "magicflow-od-search__grid" };
const _hoisted_5$h = { class: "magicflow-od-search__acts" };
const _hoisted_6$g = {
  key: 0,
  class: "magicflow-od-search__hint"
};
const _hoisted_7$f = { class: "magicflow-od-switch" };
const _hoisted_8$e = {
  key: 0,
  class: "magicflow-od-inventory"
};
const _hoisted_9$c = { class: "magicflow-od-inventory__head" };
const _hoisted_10$c = {
  key: 0,
  class: "magicflow-od-inventory__empty"
};
const _hoisted_11$b = ["title"];
const _hoisted_12$b = { class: "magicflow-od-row__meta" };
const _hoisted_13$a = { key: 2 };
const _hoisted_14$a = { key: 3 };
const _hoisted_15$a = { key: 4 };
const _hoisted_16$a = { class: "magicflow-od-row__stage" };
const _hoisted_17$a = {
  key: 0,
  class: "magicflow-od-row__pct"
};
const _hoisted_18$a = { class: "magicflow-od-row__hash" };
const _hoisted_19$9 = {
  key: 0,
  class: "magicflow-od-inventory__empty"
};
const _hoisted_20$9 = ["title"];
const _hoisted_21$8 = ["title"];
const _hoisted_22$7 = { class: "magicflow-od-row__meta" };
const _hoisted_23$6 = { key: 0 };
const _hoisted_24$6 = { class: "magicflow-od-row__ts" };
const _hoisted_25$6 = { class: "magicflow-od-row__stage" };
const _hoisted_26$6 = { class: "magicflow-od-row__hash" };
const _hoisted_27$6 = {
  key: 0,
  class: "magicflow-od-inventory__empty"
};
const _hoisted_28$5 = { class: "magicflow-recommend-dialog__summary mt-2" };
const _hoisted_29$5 = {
  key: 0,
  class: "magicflow-recommend-dialog__note"
};
const _hoisted_30$5 = {
  key: 1,
  class: "magicflow-od-batchbar mt-2"
};
const _hoisted_31$5 = { class: "magicflow-od-batchbar__text" };
const _hoisted_32$5 = {
  key: 2,
  class: "magicflow-ondemand-list mt-2"
};
const _hoisted_33$4 = { class: "magicflow-ondemand-item__body" };
const _hoisted_34$4 = ["title"];
const _hoisted_35$4 = {
  key: 0,
  class: "magicflow-ondemand-item__alt"
};
const _hoisted_36$3 = {
  key: 0,
  class: "magicflow-ondemand-item__sub"
};
const _hoisted_37$3 = { class: "magicflow-ondemand-item__meta" };
const _hoisted_38$3 = { key: 0 };
const _hoisted_39$3 = ["title"];
const _hoisted_40$3 = { class: "magicflow-ondemand-item__act" };
const _hoisted_41$3 = {
  key: 3,
  class: "magicflow-od-inventory__empty"
};

const {ref: ref$u,watch: watch$b} = __vue;

// 开关走 defineModel（Boolean）；查询 / 站点多选 / 保存目录 / 清单筛选 / 操作提示 均两向绑定，
// 子不直接改父 state。

const _sfc_main$m = {
  __name: 'OndemandDialog',
  props: /*@__PURE__*/_mergeModels$b({
  ondemandResult: { type: Object, default: null },
  ondemandCandidates: { type: Array, default: () => [] },
  odInflight: { type: Array, default: () => [] },
  odHistory: { type: Array, default: () => [] },
  odActing: { type: String, default: '' },
  ondemandBusy: { type: String, default: '' },
  ondemandError: { type: String, default: '' },
  ondemandItemsBusy: { type: Boolean, default: false },
  siteSelectItems: { type: Array, default: () => [] },
  tasks: { type: Array, default: () => [] },
  isOndemandAuto: { type: Function, default: () => false },
  odPicked: { type: Array, default: () => [] },
  odBatchBusy: { type: Boolean, default: false },
}, {
    "modelValue": { type: Boolean, default: false },
    "modelModifiers": {},
    "query": { type: String, default: '' },
    "queryModifiers": {},
    "siteIds": { type: Array, default: () => [] },
    "siteIdsModifiers": {},
    "taskId": { type: String, default: '' },
    "taskIdModifiers": {},
    "tab": { type: String, default: 'inflight' },
    "tabModifiers": {},
    "msg": { type: String, default: '' },
    "msgModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$b(['run', 'refresh-items', 'act', 'pick', 'pick-all', 'batch-run'], ["update:modelValue", "update:query", "update:siteIds", "update:taskId", "update:tab", "update:msg"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 点播弹窗（搜索 / 清单 / 搜索结果）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（odTraffic / odPct / odSpeed / odEtaText / odStageColor / odIsPaused / fmtSizeGb）
// 自 composables/useOndemand.js 具名导入复用 —— 单一真值源；isOndemandAuto 依赖点播结果
// （ondemandResult.auto_pick），仍由 useOndemand 定义 → 以函数 prop 下传（同 SilentPoolDialog 的 gbText 做法）。
const ondemandOpen = _useModel$b(__props, "modelValue");
const ondemandQuery = _useModel$b(__props, 'query');
const ondemandSiteIds = _useModel$b(__props, 'siteIds');
const ondemandTaskId = _useModel$b(__props, 'taskId');
const ondemandTab = _useModel$b(__props, 'tab');
const odMsg = _useModel$b(__props, 'msg');

// props：点播域展示态（useOndemand）+ 站点多选 / 保存目录（父页其它域）+ 函数 prop（isOndemandAuto）。
// ★ 保持无内联注释：护栏⑦（check_template_bindings）按 `[,{] ident :` 逐键解析 defineProps。
//   siteSelectItems ← useSignin；tasks ← useTasks；isOndemandAuto ← useOndemand（依赖结果，函数下传）。
const props = __props;

const emit = __emit;

// ★ 19.11.1 视图分流：候选与清单**互斥显示**，只占一块滚动区。
//   起因：两块长列表原本上下串联在同一滚动槽里 —— 搜完要滚过整份点播清单（可上百条）
//   才看见候选，用户反馈「放不了那么多内容». 默认停在清单（进来先看自己点播的东西），
//   一旦拿到新候选就自动切到候选。
const odView = ref$u('inventory');
const odSearchHint = ref$u(false);
watch$b(() => props.ondemandResult, (v) => {
  if (v) odView.value = 'candidates';
});

// 动作向上：搜候选 / 选源并下载、刷新清单、行内操作（暂停 / 继续 / 移除）、多选勾选与批量点播
function runOndemand(apply, pick = '') { emit('run', apply, pick); }
function loadOndemandItems() { emit('refresh-items'); }
function actOndemand(row, action) { emit('act', row, action); }
function pickRow(row) { emit('pick', row); }
function pickAllCandidates(on) { emit('pick-all', !!on); }
function runBatch() { emit('batch-run'); }
// 全选 / 半选态在 template 里就地算（props 键可直接引用，无需再包一层 computed）

return (_ctx, _cache) => {
  const _component_VBtn = _resolveComponent$m("VBtn");
  const _component_VDivider = _resolveComponent$m("VDivider");
  const _component_VTextField = _resolveComponent$m("VTextField");
  const _component_VSelect = _resolveComponent$m("VSelect");
  const _component_VSpacer = _resolveComponent$m("VSpacer");
  const _component_VAlert = _resolveComponent$m("VAlert");
  const _component_VChip = _resolveComponent$m("VChip");
  const _component_VProgressLinear = _resolveComponent$m("VProgressLinear");
  const _component_VCheckbox = _resolveComponent$m("VCheckbox");
  const _component_VCardText = _resolveComponent$m("VCardText");
  const _component_VCard = _resolveComponent$m("VCard");
  const _component_VDialog = _resolveComponent$m("VDialog");

  return (_openBlock$m(), _createBlock$j(_component_VDialog, {
    modelValue: ondemandOpen.value,
    "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((ondemandOpen).value = $event)),
    "max-width": "54rem",
    scrollable: ""
  }, {
    default: _withCtx$j(() => [
      _createVNode$l(_component_VCard, { class: "magicflow-dialog magicflow-ondemand-dialog" }, {
        default: _withCtx$j(() => [
          _createElementVNode$m("header", _hoisted_1$k, [
            _cache[14] || (_cache[14] = _createElementVNode$m("span", { class: "magicflow-settings-dialog__title" }, "点播", -1)),
            _createElementVNode$m("div", _hoisted_2$i, [
              _createVNode$l(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[0] || (_cache[0] = $event => (ondemandOpen.value = false))
              })
            ])
          ]),
          _createVNode$l(_component_VDivider),
          _createElementVNode$m("div", _hoisted_3$h, [
            _createElementVNode$m("div", _hoisted_4$h, [
              _createVNode$l(_component_VTextField, {
                modelValue: ondemandQuery.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((ondemandQuery).value = $event)),
                density: "compact",
                "hide-details": "auto",
                label: "片名 / 链接",
                placeholder: "如 流浪地球 或 豆瓣链接",
                onKeyup: _cache[2] || (_cache[2] = _withKeys($event => (runOndemand(false)), ["enter"]))
              }, null, 8, ["modelValue"]),
              _createVNode$l(_component_VSelect, {
                modelValue: ondemandSiteIds.value,
                "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((ondemandSiteIds).value = $event)),
                density: "compact",
                "hide-details": "auto",
                items: __props.siteSelectItems,
                label: "站点（可多选 · 空＝全部）",
                multiple: "",
                chips: "",
                "closable-chips": ""
              }, null, 8, ["modelValue", "items"]),
              _createVNode$l(_component_VSelect, {
                modelValue: ondemandTaskId.value,
                "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((ondemandTaskId).value = $event)),
                density: "compact",
                "hide-details": "auto",
                items: [{ title: '（默认目录）', value: '' }, ...__props.tasks.map((t) => ({ title: `${t.name}·${t.site_name || t.site_id}`, value: t.id }))],
                label: "保存目录"
              }, null, 8, ["modelValue", "items"])
            ]),
            _createElementVNode$m("div", _hoisted_5$h, [
              _createVNode$l(_component_VBtn, {
                size: "small",
                variant: "tonal",
                color: "primary",
                "prepend-icon": "mdi-magnify",
                loading: __props.ondemandBusy === 'preview',
                onClick: _cache[5] || (_cache[5] = $event => (runOndemand(false)))
              }, {
                default: _withCtx$j(() => [...(_cache[15] || (_cache[15] = [
                  _createTextVNode$l("搜候选", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              _createVNode$l(_component_VBtn, {
                size: "small",
                color: "primary",
                "prepend-icon": "mdi-cloud-download-outline",
                loading: __props.ondemandBusy === 'apply',
                onClick: _cache[6] || (_cache[6] = $event => (runOndemand(true)))
              }, {
                default: _withCtx$j(() => [...(_cache[16] || (_cache[16] = [
                  _createTextVNode$l("选源并下载", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              _createVNode$l(_component_VSpacer),
              _createVNode$l(_component_VBtn, {
                size: "x-small",
                variant: "text",
                "append-icon": odSearchHint.value ? 'mdi-chevron-up' : 'mdi-help-circle-outline',
                onClick: _cache[7] || (_cache[7] = $event => (odSearchHint.value = !odSearchHint.value))
              }, {
                default: _withCtx$j(() => [...(_cache[17] || (_cache[17] = [
                  _createTextVNode$l("说明", -1)
                ]))]),
                _: 1
              }, 8, ["append-icon"])
            ]),
            (odSearchHint.value)
              ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_6$g, [...(_cache[18] || (_cache[18] = [
                  _createTextVNode$l(" 搜出候选后", -1),
                  _createElementVNode$m("strong", null, "勾选", -1),
                  _createTextVNode$l("多条 → 点底部", -1),
                  _createElementVNode$m("strong", null, "「一并点播」", -1),
                  _createTextVNode$l("；不勾也能点", -1),
                  _createElementVNode$m("strong", null, "「选源并下载」", -1),
                  _createTextVNode$l("自动挑推荐源。 片名认不出、或站点里没有同名资源时它", -1),
                  _createElementVNode$m("strong", null, "不会替你乱选", -1),
                  _createTextVNode$l("，只把站点结果列出来让你自己勾 （标「名称未匹配」的是按关键词捞到的噪音）。 下完", -1),
                  _createElementVNode$m("strong", null, "自动整理进影视库", -1),
                  _createTextVNode$l("。候选第一行是", -1),
                  _createElementVNode$m("strong", null, "中文名", -1),
                  _createTextVNode$l("，灰色小字为站点原名。 ", -1)
                ]))]))
              : _createCommentVNode$j("", true),
            (__props.ondemandError)
              ? (_openBlock$m(), _createBlock$j(_component_VAlert, {
                  key: 1,
                  type: __props.ondemandCandidates.length ? 'warning' : 'error',
                  variant: "tonal",
                  density: "compact",
                  class: "mt-2"
                }, {
                  default: _withCtx$j(() => [
                    _createTextVNode$l(_toDisplayString$m(__props.ondemandError), 1)
                  ]),
                  _: 1
                }, 8, ["type"]))
              : _createCommentVNode$j("", true)
          ]),
          _createElementVNode$m("div", _hoisted_7$f, [
            _createVNode$l(_component_VChip, {
              size: "small",
              class: "magicflow-od-tab",
              variant: odView.value === 'candidates' ? 'flat' : 'tonal',
              color: odView.value === 'candidates' ? 'primary' : '',
              onClick: _cache[8] || (_cache[8] = $event => (odView.value = 'candidates'))
            }, {
              default: _withCtx$j(() => [
                _createTextVNode$l("候选 " + _toDisplayString$m(__props.ondemandCandidates.length), 1)
              ]),
              _: 1
            }, 8, ["variant", "color"]),
            _createVNode$l(_component_VChip, {
              size: "small",
              class: "magicflow-od-tab",
              variant: odView.value === 'inventory' ? 'flat' : 'tonal',
              color: odView.value === 'inventory' ? 'primary' : '',
              onClick: _cache[9] || (_cache[9] = $event => (odView.value = 'inventory'))
            }, {
              default: _withCtx$j(() => [
                _createTextVNode$l("点播清单 " + _toDisplayString$m(__props.odInflight.length + __props.odHistory.length), 1)
              ]),
              _: 1
            }, 8, ["variant", "color"]),
            _createVNode$l(_component_VSpacer),
            _createVNode$l(_component_VBtn, {
              icon: "mdi-refresh",
              size: "x-small",
              variant: "text",
              "aria-label": "刷新点播清单",
              loading: __props.ondemandItemsBusy,
              onClick: loadOndemandItems
            }, null, 8, ["loading"])
          ]),
          _createVNode$l(_component_VCardText, { class: "magicflow-ondemand-dialog__body" }, {
            default: _withCtx$j(() => [
              (odView.value === 'inventory')
                ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_8$e, [
                    _createElementVNode$m("div", _hoisted_9$c, [
                      _createVNode$l(_component_VChip, {
                        size: "x-small",
                        variant: ondemandTab.value === 'inflight' ? 'flat' : 'tonal',
                        color: ondemandTab.value === 'inflight' ? 'primary' : '',
                        class: "magicflow-od-tab",
                        onClick: _cache[10] || (_cache[10] = $event => (ondemandTab.value = 'inflight'))
                      }, {
                        default: _withCtx$j(() => [
                          _createTextVNode$l("进行中 " + _toDisplayString$m(__props.odInflight.length), 1)
                        ]),
                        _: 1
                      }, 8, ["variant", "color"]),
                      _createVNode$l(_component_VChip, {
                        size: "x-small",
                        variant: ondemandTab.value === 'done' ? 'flat' : 'tonal',
                        color: ondemandTab.value === 'done' ? 'primary' : '',
                        class: "magicflow-od-tab",
                        onClick: _cache[11] || (_cache[11] = $event => (ondemandTab.value = 'done'))
                      }, {
                        default: _withCtx$j(() => [
                          _createTextVNode$l("已完成 " + _toDisplayString$m(__props.odHistory.length), 1)
                        ]),
                        _: 1
                      }, 8, ["variant", "color"])
                    ]),
                    (odMsg.value)
                      ? (_openBlock$m(), _createBlock$j(_component_VAlert, {
                          key: 0,
                          type: odMsg.value.startsWith('❌') ? 'warning' : 'info',
                          variant: "tonal",
                          density: "compact",
                          closable: "",
                          class: "mb-2 magicflow-od-msg",
                          "onClick:close": _cache[12] || (_cache[12] = $event => (odMsg.value = ''))
                        }, {
                          default: _withCtx$j(() => [
                            _createTextVNode$l(_toDisplayString$m(odMsg.value), 1)
                          ]),
                          _: 1
                        }, 8, ["type"]))
                      : _createCommentVNode$j("", true),
                    (ondemandTab.value === 'inflight')
                      ? (_openBlock$m(), _createElementBlock$j(_Fragment$j, { key: 1 }, [
                          (!__props.odInflight.length)
                            ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_10$c, " 没有进行中的点播。搜一部片开始吧。 "))
                            : _createCommentVNode$j("", true),
                          (_openBlock$m(true), _createElementBlock$j(_Fragment$j, null, _renderList$h(__props.odInflight, (row) => {
                            return (_openBlock$m(), _createElementBlock$j("article", {
                              key: 'od-i-' + row.hash,
                              class: "magicflow-od-row"
                            }, [
                              _createElementVNode$m("div", {
                                class: "magicflow-od-row__title",
                                title: row.title
                              }, [
                                _createTextVNode$l(_toDisplayString$m(row.title || row.hash.slice(0, 12)), 1),
                                (row.year)
                                  ? (_openBlock$m(), _createElementBlock$j(_Fragment$j, { key: 0 }, [
                                      _createTextVNode$l(" (" + _toDisplayString$m(row.year) + ")", 1)
                                    ], 64))
                                  : _createCommentVNode$j("", true)
                              ], 8, _hoisted_11$b),
                              _createElementVNode$m("div", _hoisted_12$b, [
                                _createVNode$l(_component_VChip, {
                                  size: "x-small",
                                  variant: "tonal"
                                }, {
                                  default: _withCtx$j(() => [
                                    _createTextVNode$l(_toDisplayString$m(row.site || '—'), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                (row.free)
                                  ? (_openBlock$m(), _createBlock$j(_component_VChip, {
                                      key: 0,
                                      size: "x-small",
                                      variant: "tonal",
                                      color: "success"
                                    }, {
                                      default: _withCtx$j(() => [...(_cache[19] || (_cache[19] = [
                                        _createTextVNode$l("免费", -1)
                                      ]))]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$j("", true),
                                (row.hit_and_run)
                                  ? (_openBlock$m(), _createBlock$j(_component_VChip, {
                                      key: 1,
                                      size: "x-small",
                                      variant: "tonal",
                                      color: "warning"
                                    }, {
                                      default: _withCtx$j(() => [...(_cache[20] || (_cache[20] = [
                                        _createTextVNode$l("H&R", -1)
                                      ]))]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$j("", true),
                                (row.size_gb)
                                  ? (_openBlock$m(), _createElementBlock$j("span", _hoisted_13$a, _toDisplayString$m(row.size_gb.toFixed(2)) + " GB", 1))
                                  : _createCommentVNode$j("", true),
                                (row.stage === 'downloading' && row.speed)
                                  ? (_openBlock$m(), _createElementBlock$j("span", _hoisted_14$a, _toDisplayString$m(_unref$a(odSpeed)(row.speed)), 1))
                                  : _createCommentVNode$j("", true),
                                (row.eta_s)
                                  ? (_openBlock$m(), _createElementBlock$j("span", _hoisted_15$a, _toDisplayString$m(_unref$a(odEtaText)(row.eta_s)), 1))
                                  : _createCommentVNode$j("", true)
                              ]),
                              _createVNode$l(_component_VProgressLinear, {
                                "model-value": _unref$a(odPct)(row),
                                height: "6",
                                rounded: "",
                                color: _unref$a(odIsPaused)(row) ? 'warning' : (row.stage === 'downloading' ? 'primary' : 'success'),
                                class: "mt-1"
                              }, null, 8, ["model-value", "color"]),
                              _createElementVNode$m("div", _hoisted_16$a, [
                                _createVNode$l(_component_VChip, {
                                  size: "x-small",
                                  variant: "flat",
                                  color: _unref$a(odIsPaused)(row) ? 'warning' : _unref$a(odStageColor)(row.stage)
                                }, {
                                  default: _withCtx$j(() => [
                                    _createTextVNode$l(_toDisplayString$m(_unref$a(odIsPaused)(row) ? '已暂停' : row.stage_text), 1)
                                  ]),
                                  _: 2
                                }, 1032, ["color"]),
                                (row.stage === 'downloading' && !_unref$a(odIsPaused)(row))
                                  ? (_openBlock$m(), _createElementBlock$j("span", _hoisted_17$a, _toDisplayString$m(_unref$a(odPct)(row).toFixed(1)) + "%", 1))
                                  : _createCommentVNode$j("", true),
                                _createElementVNode$m("span", _hoisted_18$a, _toDisplayString$m(row.hash.slice(0, 12)), 1),
                                _createVNode$l(_component_VSpacer),
                                (!_unref$a(odIsPaused)(row))
                                  ? (_openBlock$m(), _createBlock$j(_component_VBtn, {
                                      key: 1,
                                      size: "x-small",
                                      variant: "tonal",
                                      loading: __props.odActing === row.hash + ':pause',
                                      onClick: $event => (actOndemand(row, 'pause'))
                                    }, {
                                      default: _withCtx$j(() => [...(_cache[21] || (_cache[21] = [
                                        _createTextVNode$l("暂停", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["loading", "onClick"]))
                                  : (_openBlock$m(), _createBlock$j(_component_VBtn, {
                                      key: 2,
                                      size: "x-small",
                                      variant: "tonal",
                                      color: "primary",
                                      loading: __props.odActing === row.hash + ':resume',
                                      onClick: $event => (actOndemand(row, 'resume'))
                                    }, {
                                      default: _withCtx$j(() => [...(_cache[22] || (_cache[22] = [
                                        _createTextVNode$l("继续", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["loading", "onClick"])),
                                _createVNode$l(_component_VBtn, {
                                  size: "x-small",
                                  variant: "tonal",
                                  color: "error",
                                  loading: __props.odActing === row.hash + ':remove',
                                  onClick: $event => (actOndemand(row, 'remove'))
                                }, {
                                  default: _withCtx$j(() => [...(_cache[23] || (_cache[23] = [
                                    _createTextVNode$l("移除", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["loading", "onClick"])
                              ])
                            ]))
                          }), 128))
                        ], 64))
                      : (_openBlock$m(), _createElementBlock$j(_Fragment$j, { key: 2 }, [
                          (!__props.odHistory.length)
                            ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_19$9, "还没有已完成的点播。"))
                            : _createCommentVNode$j("", true),
                          (_openBlock$m(true), _createElementBlock$j(_Fragment$j, null, _renderList$h(__props.odHistory, (row) => {
                            return (_openBlock$m(), _createElementBlock$j("article", {
                              key: 'od-h-' + row.hash,
                              class: "magicflow-od-row magicflow-od-row--done"
                            }, [
                              _createElementVNode$m("div", {
                                class: "magicflow-od-row__title",
                                title: row.title
                              }, _toDisplayString$m(row.title || row.hash.slice(0, 12)), 9, _hoisted_20$9),
                              (row.subtitle)
                                ? (_openBlock$m(), _createElementBlock$j("div", {
                                    key: 0,
                                    class: "magicflow-od-row__sub",
                                    title: row.subtitle
                                  }, _toDisplayString$m(row.subtitle), 9, _hoisted_21$8))
                                : _createCommentVNode$j("", true),
                              _createElementVNode$m("div", _hoisted_22$7, [
                                _createVNode$l(_component_VChip, {
                                  size: "x-small",
                                  variant: "tonal"
                                }, {
                                  default: _withCtx$j(() => [
                                    _createTextVNode$l(_toDisplayString$m(row.site || '—'), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                (row.size_gb)
                                  ? (_openBlock$m(), _createElementBlock$j("span", _hoisted_23$6, _toDisplayString$m(row.size_gb.toFixed(2)) + " GB", 1))
                                  : _createCommentVNode$j("", true),
                                _createElementVNode$m("span", _hoisted_24$6, _toDisplayString$m(_unref$a(tsText)(row.added_at)), 1)
                              ]),
                              _createElementVNode$m("div", _hoisted_25$6, [
                                _createVNode$l(_component_VChip, {
                                  size: "x-small",
                                  variant: "tonal",
                                  color: row.stage === 'resource' ? 'success' : (row.stage === 'downloading' ? 'primary' : '')
                                }, {
                                  default: _withCtx$j(() => [
                                    _createTextVNode$l(_toDisplayString$m(row.stage_text), 1)
                                  ]),
                                  _: 2
                                }, 1032, ["color"]),
                                _createElementVNode$m("span", _hoisted_26$6, _toDisplayString$m(row.hash.slice(0, 12)), 1)
                              ])
                            ]))
                          }), 128))
                        ], 64))
                  ]))
                : _createCommentVNode$j("", true),
              (odView.value === 'candidates')
                ? (_openBlock$m(), _createElementBlock$j(_Fragment$j, { key: 1 }, [
                    (!__props.ondemandResult)
                      ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_27$6, " 输入片名点「搜候选」：结果在这里，可勾选多条后一并点播。 "))
                      : (_openBlock$m(), _createElementBlock$j(_Fragment$j, { key: 1 }, [
                          _createElementVNode$m("div", _hoisted_28$5, [
                            _createVNode$l(_component_VChip, {
                              size: "small",
                              color: __props.ondemandResult.resource?.recognized ? 'success' : 'warning',
                              variant: "tonal"
                            }, {
                              default: _withCtx$j(() => [
                                _createTextVNode$l(_toDisplayString$m(__props.ondemandResult.resource?.recognized ? '已识别' : '未识别（按原串搜）'), 1)
                              ]),
                              _: 1
                            }, 8, ["color"]),
                            _cache[25] || (_cache[25] = _createElementVNode$m("i", null, "·", -1)),
                            _createElementVNode$m("span", null, _toDisplayString$m(__props.ondemandResult.resource?.title) + " " + _toDisplayString$m(__props.ondemandResult.resource?.year), 1),
                            _cache[26] || (_cache[26] = _createElementVNode$m("i", null, "·", -1)),
                            _createElementVNode$m("span", null, "候选 " + _toDisplayString$m(__props.ondemandCandidates.length), 1),
                            _cache[27] || (_cache[27] = _createElementVNode$m("i", null, "·", -1)),
                            _createElementVNode$m("span", null, "站点 " + _toDisplayString$m((__props.ondemandResult.sites || []).join(', ') || '—'), 1),
                            _cache[28] || (_cache[28] = _createElementVNode$m("i", null, "·", -1)),
                            _createElementVNode$m("span", null, [
                              _cache[24] || (_cache[24] = _createTextVNode$l("存到 ", -1)),
                              _createElementVNode$m("code", null, _toDisplayString$m(__props.ondemandResult.save_path || '（未配置）'), 1)
                            ])
                          ]),
                          (__props.ondemandResult.added)
                            ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_29$5, [
                                _cache[29] || (_cache[29] = _createTextVNode$l(" 已下载：", -1)),
                                _createElementVNode$m("code", null, _toDisplayString$m(__props.ondemandResult.added), 1),
                                _cache[30] || (_cache[30] = _createTextVNode$l("（完成后直接转「资源」） ", -1))
                              ]))
                            : _createCommentVNode$j("", true),
                          (__props.ondemandCandidates.length)
                            ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_30$5, [
                                _createVNode$l(_component_VCheckbox, {
                                  "model-value": __props.ondemandCandidates.length > 0 && __props.odPicked.length >= __props.ondemandCandidates.length,
                                  indeterminate: __props.odPicked.length > 0 && __props.odPicked.length < __props.ondemandCandidates.length,
                                  density: "compact",
                                  "hide-details": "",
                                  "aria-label": "全选候选",
                                  "onUpdate:modelValue": pickAllCandidates
                                }, null, 8, ["model-value", "indeterminate"]),
                                _createElementVNode$m("span", _hoisted_31$5, [
                                  _cache[31] || (_cache[31] = _createTextVNode$l("全选 · 已选 ", -1)),
                                  _createElementVNode$m("strong", null, _toDisplayString$m(__props.odPicked.length), 1),
                                  _cache[32] || (_cache[32] = _createTextVNode$l(" 条", -1))
                                ]),
                                _createVNode$l(_component_VSpacer),
                                _createVNode$l(_component_VBtn, {
                                  size: "small",
                                  color: "primary",
                                  "prepend-icon": "mdi-download-multiple",
                                  loading: __props.odBatchBusy,
                                  disabled: !__props.odPicked.length || !!__props.ondemandBusy,
                                  onClick: runBatch
                                }, {
                                  default: _withCtx$j(() => [...(_cache[33] || (_cache[33] = [
                                    _createTextVNode$l("一并点播", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["loading", "disabled"])
                              ]))
                            : _createCommentVNode$j("", true),
                          (__props.ondemandCandidates.length)
                            ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_32$5, [
                                (_openBlock$m(true), _createElementBlock$j(_Fragment$j, null, _renderList$h(__props.ondemandCandidates, (row, idx) => {
                                  return (_openBlock$m(), _createElementBlock$j("article", {
                                    key: idx,
                                    class: _normalizeClass$a(["magicflow-ondemand-item", { 'magicflow-ondemand-item--auto': __props.isOndemandAuto(row), 'magicflow-ondemand-item--picked': __props.odPicked.includes(row.enclosure) }])
                                  }, [
                                    _createVNode$l(_component_VCheckbox, {
                                      class: "magicflow-ondemand-item__check",
                                      "model-value": __props.odPicked.includes(row.enclosure),
                                      density: "compact",
                                      "hide-details": "",
                                      "aria-label": '选择 ' + _unref$a(odMainTitle)(row),
                                      "onUpdate:modelValue": $event => (pickRow(row))
                                    }, null, 8, ["model-value", "aria-label", "onUpdate:modelValue"]),
                                    _createElementVNode$m("div", _hoisted_33$4, [
                                      _createElementVNode$m("div", {
                                        class: "magicflow-ondemand-item__title",
                                        title: row.subtitle || row.title
                                      }, [
                                        _createTextVNode$l(_toDisplayString$m(_unref$a(odMainTitle)(row)), 1),
                                        (_unref$a(odAltTitle)(row))
                                          ? (_openBlock$m(), _createElementBlock$j("span", _hoisted_35$4, "（" + _toDisplayString$m(_unref$a(odAltTitle)(row)) + "）", 1))
                                          : _createCommentVNode$j("", true)
                                      ], 8, _hoisted_34$4),
                                      (_unref$a(odSubTitle)(row))
                                        ? (_openBlock$m(), _createElementBlock$j("div", _hoisted_36$3, _toDisplayString$m(_unref$a(odSubTitle)(row)), 1))
                                        : _createCommentVNode$j("", true),
                                      _createElementVNode$m("div", _hoisted_37$3, [
                                        _createVNode$l(_component_VChip, {
                                          size: "x-small",
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx$j(() => [
                                            _createTextVNode$l(_toDisplayString$m(row.site_name || row.site), 1)
                                          ]),
                                          _: 2
                                        }, 1024),
                                        _createElementVNode$m("span", null, _toDisplayString$m(_unref$a(fmtSizeGb)(row.size)), 1),
                                        (Number(row.counted_gb) > 0)
                                          ? (_openBlock$m(), _createElementBlock$j("span", _hoisted_38$3, "实扣 " + _toDisplayString$m(Number(row.counted_gb).toFixed(2)) + " GB", 1))
                                          : _createCommentVNode$j("", true),
                                        _createElementVNode$m("span", null, "做种 " + _toDisplayString$m(row.seeders), 1),
                                        _createVNode$l(_component_VChip, {
                                          size: "x-small",
                                          variant: "tonal",
                                          color: _unref$a(odTraffic)(row.downloadvolumefactor).color || undefined
                                        }, {
                                          default: _withCtx$j(() => [
                                            _createTextVNode$l(_toDisplayString$m(_unref$a(odTraffic)(row.downloadvolumefactor).text), 1)
                                          ]),
                                          _: 2
                                        }, 1032, ["color"]),
                                        (Number(row.uploadvolumefactor) > 1)
                                          ? (_openBlock$m(), _createBlock$j(_component_VChip, {
                                              key: 1,
                                              size: "x-small",
                                              variant: "tonal",
                                              color: "success"
                                            }, {
                                              default: _withCtx$j(() => [
                                                _createTextVNode$l(_toDisplayString$m(Number(row.uploadvolumefactor) === 2 ? '2X' : Number(row.uploadvolumefactor) + 'X') + " 上传", 1)
                                              ]),
                                              _: 2
                                            }, 1024))
                                          : _createCommentVNode$j("", true),
                                        (row.hit_and_run)
                                          ? (_openBlock$m(), _createBlock$j(_component_VChip, {
                                              key: 2,
                                              size: "x-small",
                                              variant: "tonal",
                                              color: "warning"
                                            }, {
                                              default: _withCtx$j(() => [...(_cache[34] || (_cache[34] = [
                                                _createTextVNode$l("H&R", -1)
                                              ]))]),
                                              _: 1
                                            }))
                                          : _createCommentVNode$j("", true),
                                        (row.rel >= 2 && !__props.isOndemandAuto(row))
                                          ? (_openBlock$m(), _createBlock$j(_component_VChip, {
                                              key: 3,
                                              size: "x-small",
                                              variant: "tonal",
                                              color: "primary"
                                            }, {
                                              default: _withCtx$j(() => [...(_cache[35] || (_cache[35] = [
                                                _createTextVNode$l("片名对得上", -1)
                                              ]))]),
                                              _: 1
                                            }))
                                          : (row.rel === 0)
                                            ? (_openBlock$m(), _createBlock$j(_component_VChip, {
                                                key: 4,
                                                size: "x-small",
                                                variant: "tonal"
                                              }, {
                                                default: _withCtx$j(() => [...(_cache[36] || (_cache[36] = [
                                                  _createTextVNode$l("名称未匹配", -1)
                                                ]))]),
                                                _: 1
                                              }))
                                            : _createCommentVNode$j("", true),
                                        (__props.isOndemandAuto(row))
                                          ? (_openBlock$m(), _createBlock$j(_component_VChip, {
                                              key: 5,
                                              size: "x-small",
                                              variant: "flat",
                                              color: "primary"
                                            }, {
                                              default: _withCtx$j(() => [...(_cache[37] || (_cache[37] = [
                                                _createTextVNode$l("推荐", -1)
                                              ]))]),
                                              _: 1
                                            }))
                                          : _createCommentVNode$j("", true),
                                        (__props.ondemandResult?.added && __props.ondemandResult?.picked?.enclosure === row.enclosure)
                                          ? (_openBlock$m(), _createBlock$j(_component_VChip, {
                                              key: 6,
                                              size: "x-small",
                                              variant: "flat",
                                              color: "success"
                                            }, {
                                              default: _withCtx$j(() => [...(_cache[38] || (_cache[38] = [
                                                _createTextVNode$l("已下", -1)
                                              ]))]),
                                              _: 1
                                            }))
                                          : _createCommentVNode$j("", true)
                                      ]),
                                      _createElementVNode$m("div", {
                                        class: "magicflow-ondemand-item__raw",
                                        title: row.title
                                      }, _toDisplayString$m(row.title), 9, _hoisted_39$3)
                                    ]),
                                    _createElementVNode$m("div", _hoisted_40$3, [
                                      _createVNode$l(_component_VBtn, {
                                        size: "x-small",
                                        variant: "tonal",
                                        color: "primary",
                                        "prepend-icon": "mdi-download",
                                        loading: __props.ondemandBusy === 'apply',
                                        disabled: !!__props.ondemandBusy,
                                        onClick: $event => (runOndemand(true, row.enclosure))
                                      }, {
                                        default: _withCtx$j(() => [...(_cache[39] || (_cache[39] = [
                                          _createTextVNode$l("下这条", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["loading", "disabled", "onClick"])
                                    ])
                                  ], 2))
                                }), 128))
                              ]))
                            : (_openBlock$m(), _createElementBlock$j("div", _hoisted_41$3, " 没搜到候选。换个片名，或把站点选择清空（＝全部站点）再试一次。 "))
                        ], 64))
                  ], 64))
                : _createCommentVNode$j("", true)
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["modelValue"]))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const OndemandDialog = Object.assign(_sfc_main$m, { __scopeId: 'data-v-0cb84649' })

export default OndemandDialog
