// CloudDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './CloudDialog.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$z,
  createBlock: _createBlock$D,
  createCommentVNode: _createCommentVNode$B,
  createElementBlock: _createElementBlock$A,
  createElementVNode: _createElementVNode$G,
  createTextVNode: _createTextVNode$F,
  createVNode: _createVNode$F,
  mergeModels: _mergeModels$p,
  openBlock: _openBlock$G,
  renderList: _renderList$x,
  resolveComponent: _resolveComponent$G,
  toDisplayString: _toDisplayString$G,
  unref: _unref$i,
  useModel: _useModel$p,
  withCtx: _withCtx$D,
} = __vue

import index from '../../index.vue'
import { cloudStatusMeta } from '../../../../utils.js'
import { pickCloudRecord, useCloud } from '../../composables/useCloud.js'

const _hoisted_1$C = { class: "magicflow-settings-dialog__head" };
const _hoisted_2$A = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_3$y = { class: "magicflow-cloud-dialog__summary" };
const _hoisted_4$y = { class: "magicflow-cloud-dialog__actions" };
const _hoisted_5$y = {
  key: 0,
  class: "magicflow-settings-hint"
};
const _hoisted_6$w = {
  key: 1,
  class: "magicflow-settings-hint"
};
const _hoisted_7$t = { class: "magicflow-cloud-row__main" };
const _hoisted_8$r = { class: "magicflow-cloud-row__title" };
const _hoisted_9$p = { class: "magicflow-cloud-row__sub" };
const _hoisted_10$p = {
  key: 0,
  class: "magicflow-cloud-row__msg"
};
const _hoisted_11$n = { class: "magicflow-cloud-row__side" };

const {computed: computed$M} = __vue;


const _sfc_main$G = {
  __name: 'CloudDialog',
  props: /*@__PURE__*/_mergeModels$p({
  // 云盘归档状态（useCloud 的展示态打包；state.data = cloudState 全局状态）
  state: { type: Object, default: () => ({}) },
  narrow: { type: Boolean, default: false },
}, {
    "modelValue": { type: Boolean, default: false },
    "modelModifiers": {},
    "limit": { type: Number, default: 50 },
    "limitModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$p(['refresh', 'plan', 'run', 'test', 'upload'], ["update:modelValue", "update:limit"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 云盘归档弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 记录查找纯函数（pickCloudRecord）自 composables/useCloud.js 具名导入复用 —— 单一真值源。
const cloudOpen = _useModel$p(__props, "modelValue");
const cloudLimit = _useModel$p(__props, 'limit');

const props = __props;

const emit = __emit;

const cloudState = computed$M(() => props.state.data || null);
const cloudCfg = computed$M(() => (cloudState.value || {}).cfg || {});
const cloudPlanItems = computed$M(() => props.state.planItems || []);
const cloudPlanStats = computed$M(() => props.state.planStats || null);
const cloudLoading = computed$M(() => Boolean(props.state.loading));
const cloudPlanning = computed$M(() => Boolean(props.state.planning));
const cloudRunning = computed$M(() => Boolean(props.state.running));
const cloudTesting = computed$M(() => Boolean(props.state.testing));
const cloudTestMsg = computed$M(() => props.state.testMsg || '');
const cloudTestOk = computed$M(() => Boolean(props.state.testOk));
const cloudUploadingPath = computed$M(() => props.state.uploadingPath || '');

function loadCloud() { emit('refresh'); }
function testCloud() { emit('test'); }
function planCloud() { emit('plan'); }
function runCloud(dryRun) { emit('run', dryRun); }
function uploadCloudOne(item) { emit('upload', item); }
function cloudRecordFor(item) { return pickCloudRecord((cloudState.value || {}).records, item) }

return (_ctx, _cache) => {
  const _component_VBtn = _resolveComponent$G("VBtn");
  const _component_VDivider = _resolveComponent$G("VDivider");
  const _component_VAlert = _resolveComponent$G("VAlert");
  const _component_VTextField = _resolveComponent$G("VTextField");
  const _component_VChip = _resolveComponent$G("VChip");
  const _component_VSheet = _resolveComponent$G("VSheet");
  const _component_VCardText = _resolveComponent$G("VCardText");
  const _component_VCard = _resolveComponent$G("VCard");
  const _component_VDialog = _resolveComponent$G("VDialog");

  return (_openBlock$G(), _createBlock$D(_component_VDialog, {
    modelValue: cloudOpen.value,
    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cloudOpen).value = $event)),
    "max-width": "52rem",
    scrollable: "",
    fullscreen: __props.narrow
  }, {
    default: _withCtx$D(() => [
      _createVNode$F(_component_VCard, { class: "magicflow-dialog magicflow-cloud-dialog" }, {
        default: _withCtx$D(() => [
          _createElementVNode$G("header", _hoisted_1$C, [
            _cache[6] || (_cache[6] = _createElementVNode$G("span", { class: "magicflow-settings-dialog__title" }, "云盘归档", -1)),
            _createElementVNode$G("div", _hoisted_2$A, [
              _createVNode$F(_component_VBtn, {
                variant: "text",
                color: "primary",
                size: "small",
                "prepend-icon": "mdi-refresh",
                loading: cloudLoading.value,
                onClick: loadCloud
              }, {
                default: _withCtx$D(() => [...(_cache[5] || (_cache[5] = [
                  _createTextVNode$F("刷新", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              _createVNode$F(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[0] || (_cache[0] = $event => (cloudOpen.value = false))
              })
            ])
          ]),
          _createVNode$F(_component_VDivider),
          _createVNode$F(_component_VCardText, { class: "magicflow-cloud-dialog__body" }, {
            default: _withCtx$D(() => [
              (!cloudCfg.value.enabled)
                ? (_openBlock$G(), _createBlock$D(_component_VAlert, {
                    key: 0,
                    type: "info",
                    variant: "tonal",
                    density: "compact",
                    class: "mb-2"
                  }, {
                    default: _withCtx$D(() => [...(_cache[7] || (_cache[7] = [
                      _createTextVNode$F(" 云盘归档未启用（「插件设置 → 云盘归档」里开启并填 OpenList 地址 / Token）。 ", -1)
                    ]))]),
                    _: 1
                  }))
                : _createCommentVNode$B("", true),
              _createElementVNode$G("div", _hoisted_3$y, [
                _createElementVNode$G("span", null, [
                  _createElementVNode$G("strong", null, _toDisplayString$G(cloudPlanStats.value?.pending ?? 0), 1),
                  _cache[8] || (_cache[8] = _createTextVNode$F(" 待上传", -1))
                ]),
                _cache[12] || (_cache[12] = _createElementVNode$G("i", null, "·", -1)),
                _createElementVNode$G("span", null, [
                  _createElementVNode$G("strong", null, _toDisplayString$G(cloudPlanStats.value?.remote_exists ?? 0), 1),
                  _cache[9] || (_cache[9] = _createTextVNode$F(" 远端已有", -1))
                ]),
                _cache[13] || (_cache[13] = _createElementVNode$G("i", null, "·", -1)),
                _createElementVNode$G("span", null, [
                  _createElementVNode$G("strong", null, _toDisplayString$G(cloudPlanStats.value?.done ?? 0), 1),
                  _cache[10] || (_cache[10] = _createTextVNode$F(" 已归档", -1))
                ]),
                _cache[14] || (_cache[14] = _createElementVNode$G("i", null, "·", -1)),
                _createElementVNode$G("span", null, _toDisplayString$G(cloudPlanStats.value?.pending_gb ?? 0) + " GB", 1),
                _cache[15] || (_cache[15] = _createElementVNode$G("i", null, "·", -1)),
                _createElementVNode$G("span", null, [
                  _createElementVNode$G("strong", null, _toDisplayString$G(cloudState.value?.record_count ?? 0), 1),
                  _cache[11] || (_cache[11] = _createTextVNode$F(" 条记录", -1))
                ])
              ]),
              _cache[23] || (_cache[23] = _createElementVNode$G("div", { class: "magicflow-cloud-dialog__note" }, [
                _createTextVNode$F(" 上传到 OpenList 可写存储 → 同一夸克目录 → Strm 视图自动生成播放指针 → 影视直接能看。 默认"),
                _createElementVNode$G("strong", null, "只上传不删除"),
                _createTextVNode$F("；本地删除需单独确认。 ")
              ], -1)),
              _createElementVNode$G("div", _hoisted_4$y, [
                _createVNode$F(_component_VBtn, {
                  variant: "tonal",
                  color: "primary",
                  size: "small",
                  "prepend-icon": "mdi-connection",
                  loading: cloudTesting.value,
                  onClick: testCloud
                }, {
                  default: _withCtx$D(() => [...(_cache[16] || (_cache[16] = [
                    _createTextVNode$F("测试连接", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode$F(_component_VBtn, {
                  variant: "tonal",
                  size: "small",
                  "prepend-icon": "mdi-clipboard-list-outline",
                  loading: cloudPlanning.value,
                  onClick: planCloud
                }, {
                  default: _withCtx$D(() => [...(_cache[17] || (_cache[17] = [
                    _createTextVNode$F("扫描候选", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode$F(_component_VBtn, {
                  variant: "tonal",
                  size: "small",
                  "prepend-icon": "mdi-play-circle-outline",
                  loading: cloudRunning.value,
                  onClick: _cache[1] || (_cache[1] = $event => (runCloud(true)))
                }, {
                  default: _withCtx$D(() => [...(_cache[18] || (_cache[18] = [
                    _createTextVNode$F("演练归档", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode$F(_component_VBtn, {
                  color: "primary",
                  variant: "flat",
                  size: "small",
                  "prepend-icon": "mdi-cloud-upload-outline",
                  loading: cloudRunning.value,
                  onClick: _cache[2] || (_cache[2] = $event => (runCloud(false)))
                }, {
                  default: _withCtx$D(() => [...(_cache[19] || (_cache[19] = [
                    _createTextVNode$F("开始归档", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode$F(_component_VTextField, {
                  modelValue: cloudLimit.value,
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cloudLimit).value = $event)),
                  modelModifiers: { number: true },
                  label: "本轮条数",
                  type: "number",
                  variant: "outlined",
                  density: "compact",
                  "hide-details": "",
                  class: "magicflow-cloud-dialog__limit"
                }, null, 8, ["modelValue"])
              ]),
              (cloudTestMsg.value)
                ? (_openBlock$G(), _createBlock$D(_component_VAlert, {
                    key: 1,
                    type: cloudTestOk.value ? 'success' : 'error',
                    variant: "tonal",
                    density: "compact",
                    class: "my-2"
                  }, {
                    default: _withCtx$D(() => [
                      _createTextVNode$F(_toDisplayString$G(cloudTestMsg.value), 1)
                    ]),
                    _: 1
                  }, 8, ["type"]))
                : _createCommentVNode$B("", true),
              (cloudState.value?.running)
                ? (_openBlock$G(), _createBlock$D(_component_VAlert, {
                    key: 2,
                    type: "info",
                    variant: "tonal",
                    density: "compact",
                    class: "my-2"
                  }, {
                    default: _withCtx$D(() => [...(_cache[20] || (_cache[20] = [
                      _createTextVNode$F(" 归档任务正在后台执行（可关闭本窗口，进度看下方列表与「操作记录」）。 ", -1)
                    ]))]),
                    _: 1
                  }))
                : _createCommentVNode$B("", true),
              _createVNode$F(_component_VSheet, {
                tag: "section",
                class: "magicflow-panel app-surface-static mt-2"
              }, {
                default: _withCtx$D(() => [
                  _cache[22] || (_cache[22] = _createElementVNode$G("header", { class: "magicflow-panel__head" }, [
                    _createElementVNode$G("div", null, [
                      _createElementVNode$G("div", { class: "text-subtitle-2 font-weight-medium" }, "归档候选"),
                      _createElementVNode$G("div", { class: "text-body-2 text-medium-emphasis" }, "点「扫描候选」列出可传文件；逐条点「上传」立即传（后台执行）")
                    ])
                  ], -1)),
                  (cloudLoading.value && !cloudPlanItems.value.length)
                    ? (_openBlock$G(), _createElementBlock$A("p", _hoisted_5$y, "加载中…"))
                    : (!cloudPlanItems.value.length)
                      ? (_openBlock$G(), _createElementBlock$A("p", _hoisted_6$w, " 还没有候选。点上方「扫描候选」；若为 0，检查设置里的「扫描目录 / 体积范围 / 最小入库天数」。 "))
                      : _createCommentVNode$B("", true),
                  (_openBlock$G(true), _createElementBlock$A(_Fragment$z, null, _renderList$x(cloudPlanItems.value, (it) => {
                    return (_openBlock$G(), _createElementBlock$A("div", {
                      key: it.path,
                      class: "magicflow-cloud-row"
                    }, [
                      _createElementVNode$G("div", _hoisted_7$t, [
                        _createElementVNode$G("div", _hoisted_8$r, _toDisplayString$G(it.name), 1),
                        _createElementVNode$G("div", _hoisted_9$p, _toDisplayString$G(it.rel) + " · " + _toDisplayString$G(it.size_gb) + " GB", 1),
                        (it.message || (cloudRecordFor(it) || {}).error)
                          ? (_openBlock$G(), _createElementBlock$A("div", _hoisted_10$p, _toDisplayString$G(it.message || (cloudRecordFor(it) || {}).error), 1))
                          : _createCommentVNode$B("", true)
                      ]),
                      _createElementVNode$G("div", _hoisted_11$n, [
                        _createVNode$F(_component_VChip, {
                          size: "x-small",
                          variant: "tonal",
                          color: _unref$i(cloudStatusMeta)(cloudRecordFor(it)?.status || it.status).color
                        }, {
                          default: _withCtx$D(() => [
                            _createTextVNode$F(_toDisplayString$G(_unref$i(cloudStatusMeta)(cloudRecordFor(it)?.status || it.status).text), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"]),
                        _createVNode$F(_component_VBtn, {
                          size: "x-small",
                          variant: "tonal",
                          color: "primary",
                          loading: cloudUploadingPath.value === it.path,
                          onClick: $event => (uploadCloudOne(it))
                        }, {
                          default: _withCtx$D(() => [...(_cache[21] || (_cache[21] = [
                            _createTextVNode$F("上传", -1)
                          ]))]),
                          _: 1
                        }, 8, ["loading", "onClick"])
                      ])
                    ]))
                  }), 128))
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["modelValue", "fullscreen"]))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const CloudDialog = Object.assign(_sfc_main$G, { __scopeId: 'data-v-38c304b8' })

export default CloudDialog
