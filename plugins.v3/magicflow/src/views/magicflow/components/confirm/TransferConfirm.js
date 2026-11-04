// TransferConfirm —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './TransferConfirm.css'


import * as __vue from 'vue'

const {
  createBlock: _createBlock$1,
  createElementVNode: _createElementVNode$1,
  createTextVNode: _createTextVNode$1,
  createVNode: _createVNode$1,
  openBlock: _openBlock$1,
  resolveComponent: _resolveComponent$1,
  toDisplayString: _toDisplayString$1,
  withCtx: _withCtx$1,
  mergeModels: _mergeModels,
  useModel: _useModel
} = __vue

import index from '../../index.vue'
import { useSeeding } from '../../composables/useSeeding.js'

const _sfc_main$1 = {
  __name: 'TransferConfirm',
  props: /*@__PURE__*/_mergeModels({
  selectedHashes: { type: Array, default: () => [] },
  choices: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
}, {
    "modelValue": { type: Boolean, default: false },
    "modelModifiers": {},
    "target": { type: String, default: 'idle' },
    "targetModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels(['confirm'], ["update:modelValue", "update:target"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 批量转移种子确认弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 L2002–L2018 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 状态真值源仍在 composables/useSeeding.js（transferDialog / transferTarget / transferChoices /
// selectedHashes / batchBusy / confirmTransfer），此处只做展示与回传。
const open = _useModel(__props, "modelValue");
// 转移目标：v-model:target（对应 useSeeding.transferTarget，默认 'idle' = 退回静默池）。
const target = _useModel(__props, 'target');

// props（向下，只读）：
//   selectedHashes = useSeeding.selectedHashes（仅取 .length 展示数量）
//   choices        = useSeeding.transferChoices（VSelect 选项）
//   busy           = useSeeding.batchBusy（动作进行中）


const emit = __emit;

return (_ctx, _cache) => {
  const _component_VCardText = _resolveComponent$1("VCardText");
  const _component_VSelect = _resolveComponent$1("VSelect");
  const _component_VSpacer = _resolveComponent$1("VSpacer");
  const _component_VBtn = _resolveComponent$1("VBtn");
  const _component_VCardActions = _resolveComponent$1("VCardActions");
  const _component_VCard = _resolveComponent$1("VCard");
  const _component_VDialog = _resolveComponent$1("VDialog");

  return (_openBlock$1(), _createBlock$1(_component_VDialog, {
    modelValue: open.value,
    "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((open).value = $event)),
    "max-width": "34rem"
  }, {
    default: _withCtx$1(() => [
      _createVNode$1(_component_VCard, {
        title: "批量转移种子",
        class: "magicflow-dialog"
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_VCardText, { class: "magicflow-settings-hint" }, {
            default: _withCtx$1(() => [
              _cache[4] || (_cache[4] = _createTextVNode$1(" 把选中的 ", -1)),
              _createElementVNode$1("strong", null, _toDisplayString$1(__props.selectedHashes.length), 1),
              _cache[5] || (_cache[5] = _createTextVNode$1(" 个种子交给别的任务，或退回静默池（保文件）。 跨站转移会改掉站点标签 —— 一般只转给", -1)),
              _cache[6] || (_cache[6] = _createElementVNode$1("strong", null, "同站", -1)),
              _cache[7] || (_cache[7] = _createTextVNode$1("任务。 ", -1))
            ]),
            _: 1
          }),
          _createVNode$1(_component_VCardText, null, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_VSelect, {
                modelValue: target.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((target).value = $event)),
                items: __props.choices,
                "item-title": "text",
                "item-value": "value",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                label: "转移到"
              }, null, 8, ["modelValue", "items"])
            ]),
            _: 1
          }),
          _createVNode$1(_component_VCardActions, null, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_VSpacer),
              _createVNode$1(_component_VBtn, {
                variant: "text",
                disabled: __props.busy,
                onClick: _cache[1] || (_cache[1] = $event => (open.value = false))
              }, {
                default: _withCtx$1(() => [...(_cache[8] || (_cache[8] = [
                  _createTextVNode$1("取消", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$1(_component_VBtn, {
                color: "primary",
                variant: "flat",
                loading: __props.busy,
                onClick: _cache[2] || (_cache[2] = $event => (emit('confirm')))
              }, {
                default: _withCtx$1(() => [...(_cache[9] || (_cache[9] = [
                  _createTextVNode$1("转移", -1)
                ]))]),
                _: 1
              }, 8, ["loading"])
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
const TransferConfirm = Object.assign(_sfc_main$1, { __scopeId: 'data-v-5c527562' })

export default TransferConfirm
