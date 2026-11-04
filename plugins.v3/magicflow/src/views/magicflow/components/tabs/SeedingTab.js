// SeedingTab —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './SeedingTab.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$5,
  createBlock: _createBlock$4,
  createCommentVNode: _createCommentVNode$5,
  createElementBlock: _createElementBlock$5,
  createElementVNode: _createElementVNode$6,
  createTextVNode: _createTextVNode$6,
  createVNode: _createVNode$6,
  mergeModels: _mergeModels$2,
  mergeProps: _mergeProps$1,
  openBlock: _openBlock$6,
  renderList: _renderList$5,
  resolveComponent: _resolveComponent$6,
  toDisplayString: _toDisplayString$6,
  unref: _unref$2,
  useModel: _useModel$2,
  withCtx: _withCtx$4,
  withModifiers: _withModifiers$1,
} = __vue

import index from '../../index.vue'
import { TORRENT_PAUSED_STATES, TORRENT_STATE_TEXT, TORRENT_TRANSIENT_STATES } from '../../constants.js'
import { formatBytes } from '../../../../utils.js'
import { useSeeding } from '../../composables/useSeeding.js'

const _hoisted_1$5 = { class: "magicflow-panel__head" };
const _hoisted_2$5 = { class: "magicflow-torrent-filters" };
const _hoisted_3$4 = {
  key: 0,
  class: "magicflow-bulk-bar"
};
const _hoisted_4$4 = { class: "magicflow-bulk-bar__count" };
const _hoisted_5$4 = { class: "torrent-title-cell" };
const _hoisted_6$4 = { class: "magicflow-mobile-torrents" };
const _hoisted_7$4 = ["onClick"];
const _hoisted_8$4 = { class: "magicflow-mobile-torrent__head" };
const _hoisted_9$4 = { class: "magicflow-mobile-torrent__title" };
const _hoisted_10$4 = { class: "magicflow-mobile-torrent__grid" };
const _hoisted_11$4 = { class: "magicflow-mobile-torrent__actions" };
const _hoisted_12$4 = {
  key: 0,
  class: "magicflow-table-empty"
};

// rows=已按筛选/状态过滤+排序后的行；真值源仍在 useSeeding。

const _sfc_main$6 = {
  __name: 'SeedingTab',
  props: /*@__PURE__*/_mergeModels$2({
  rows: { type: Array, default: () => [] },
  headers: { type: Array, default: () => [] },
  statusOptions: { type: Array, default: () => [] },
  selectedHashes: { type: Array, default: () => [] },
  allSelected: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
}, {
    "filter": { type: String, default: 'all' },
    "filterModifiers": {},
    "statusFilter": { type: String, default: 'all' },
    "statusFilterModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$2([
  'batch',
  'transfer',
  'batch-delete',
  'select-all',
  'clear-selection',
  'toggle-row',
  'row-click',
  'torrent-action',
  'delete',
  'open-detail',
], ["update:filter", "update:statusFilter"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 托管做种明细（种子池 · poolView === 'torrents'）
// P4：自 views/magicflow/index.vue 纯搬家（模板 + 配套 scoped 样式），无行为/样式变更。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。


// 子组件不直接改父状态 → 用 model 回传（父 v-model:filter / v-model:status-filter）。
const filter = _useModel$2(__props, 'filter');
const statusFilter = _useModel$2(__props, 'statusFilter');

const emit = __emit;

// 展示态纯函数（真值源仍在 useSeeding；此处为 P4 拆分随模板搬入的同口径实现）。
function stateLabel(state) {
  const key = String(state || '').toLowerCase();
  return TORRENT_STATE_TEXT[key] || (key ? state : '托管中')
}
function stateColor(state) {
  const key = String(state || '').toLowerCase();
  if (['uploading', 'forcedup', 'stalledup', 'queuedup'].includes(key)) return 'success'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'checkingdl'].includes(key)) return 'info'
  if (key === 'stalleddl') return 'warning'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'grey'
}
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100;
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}
function torrentStateText(item) {
  const key = String(item?.state || '').toLowerCase();
  if (TORRENT_TRANSIENT_STATES[key]) return TORRENT_TRANSIENT_STATES[key]
  if (TORRENT_PAUSED_STATES.includes(key)) return stateLabel(item?.state) || '已暂停'
  const pct = torrentProgressPct(item);
  if (pct >= 100) return '做种中'
  if (pct <= 0) return stateLabel(item?.state) || '等待中'
  return `下载 ${pct}%`
}
function torrentIsPaused(item) {
  return TORRENT_PAUSED_STATES.includes(String(item?.state || '').toLowerCase())
}
function torrentPauseLabel(item) {
  return torrentProgressPct(item) >= 100 ? '暂停做种' : '暂停下载'
}
function torrentResumeLabel(item) {
  return torrentProgressPct(item) >= 100 ? '恢复做种' : '继续下载'
}

return (_ctx, _cache) => {
  const _component_VSelect = _resolveComponent$6("VSelect");
  const _component_VBtn = _resolveComponent$6("VBtn");
  const _component_VBtnToggle = _resolveComponent$6("VBtnToggle");
  const _component_VSpacer = _resolveComponent$6("VSpacer");
  const _component_VCheckbox = _resolveComponent$6("VCheckbox");
  const _component_VChip = _resolveComponent$6("VChip");
  const _component_VListItem = _resolveComponent$6("VListItem");
  const _component_VDivider = _resolveComponent$6("VDivider");
  const _component_VList = _resolveComponent$6("VList");
  const _component_VMenu = _resolveComponent$6("VMenu");
  const _component_VDataTable = _resolveComponent$6("VDataTable");
  const _component_VProgressLinear = _resolveComponent$6("VProgressLinear");
  const _component_VSheet = _resolveComponent$6("VSheet");

  return (_openBlock$6(), _createBlock$4(_component_VSheet, {
    tag: "section",
    class: "magicflow-panel magicflow-torrents app-surface-static"
  }, {
    default: _withCtx$4(() => [
      _createElementVNode$6("header", _hoisted_1$5, [
        _cache[19] || (_cache[19] = _createElementVNode$6("div", { class: "text-body-2 text-medium-emphasis" }, " 点击任意行查看详情 / 手动保留 / 删除 ", -1)),
        _createElementVNode$6("div", _hoisted_2$5, [
          _createVNode$6(_component_VSelect, {
            modelValue: statusFilter.value,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((statusFilter).value = $event)),
            items: __props.statusOptions,
            "item-title": "title",
            "item-value": "value",
            density: "compact",
            variant: "outlined",
            "hide-details": "",
            class: "magicflow-status-filter"
          }, null, 8, ["modelValue", "items"]),
          _createVNode$6(_component_VBtnToggle, {
            modelValue: filter.value,
            "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((filter).value = $event)),
            mandatory: "",
            color: "primary",
            density: "compact"
          }, {
            default: _withCtx$4(() => [
              _createVNode$6(_component_VBtn, { value: "all" }, {
                default: _withCtx$4(() => [...(_cache[17] || (_cache[17] = [
                  _createTextVNode$6("全部", -1)
                ]))]),
                _: 1
              }),
              _createVNode$6(_component_VBtn, { value: "protected" }, {
                default: _withCtx$4(() => [...(_cache[18] || (_cache[18] = [
                  _createTextVNode$6("已保护", -1)
                ]))]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["modelValue"])
        ])
      ]),
      (__props.selectedHashes.length)
        ? (_openBlock$6(), _createElementBlock$5("div", _hoisted_3$4, [
            _createElementVNode$6("span", _hoisted_4$4, "已选 " + _toDisplayString$6(__props.selectedHashes.length) + " 个", 1),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              disabled: __props.busy,
              onClick: _cache[2] || (_cache[2] = $event => (emit('batch', 'protect')))
            }, {
              default: _withCtx$4(() => [...(_cache[20] || (_cache[20] = [
                _createTextVNode$6("保留", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              disabled: __props.busy,
              onClick: _cache[3] || (_cache[3] = $event => (emit('batch', 'unprotect')))
            }, {
              default: _withCtx$4(() => [...(_cache[21] || (_cache[21] = [
                _createTextVNode$6("取消保留", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              disabled: __props.busy,
              onClick: _cache[4] || (_cache[4] = $event => (emit('batch', 'pause')))
            }, {
              default: _withCtx$4(() => [...(_cache[22] || (_cache[22] = [
                _createTextVNode$6("暂停", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              disabled: __props.busy,
              onClick: _cache[5] || (_cache[5] = $event => (emit('batch', 'resume')))
            }, {
              default: _withCtx$4(() => [...(_cache[23] || (_cache[23] = [
                _createTextVNode$6("恢复", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              disabled: __props.busy,
              onClick: _cache[6] || (_cache[6] = $event => (emit('batch', 'recheck')))
            }, {
              default: _withCtx$4(() => [...(_cache[24] || (_cache[24] = [
                _createTextVNode$6("校验", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              color: "primary",
              disabled: __props.busy,
              onClick: _cache[7] || (_cache[7] = $event => (emit('transfer')))
            }, {
              default: _withCtx$4(() => [...(_cache[25] || (_cache[25] = [
                _createTextVNode$6("批量转移", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              color: "info",
              disabled: __props.busy,
              "prepend-icon": "mdi-pin",
              onClick: _cache[8] || (_cache[8] = $event => (emit('batch', 'hold')))
            }, {
              default: _withCtx$4(() => [...(_cache[26] || (_cache[26] = [
                _createTextVNode$6("手动保种", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              disabled: __props.busy,
              "prepend-icon": "mdi-pin-off",
              onClick: _cache[9] || (_cache[9] = $event => (emit('batch', 'unhold')))
            }, {
              default: _withCtx$4(() => [...(_cache[27] || (_cache[27] = [
                _createTextVNode$6("解除保种", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "tonal",
              color: "error",
              disabled: __props.busy,
              onClick: _cache[10] || (_cache[10] = $event => (emit('batch-delete')))
            }, {
              default: _withCtx$4(() => [...(_cache[28] || (_cache[28] = [
                _createTextVNode$6("删除", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VSpacer),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "text",
              disabled: __props.busy,
              onClick: _cache[11] || (_cache[11] = $event => (emit('select-all')))
            }, {
              default: _withCtx$4(() => [
                _createTextVNode$6("全选筛选（" + _toDisplayString$6(__props.rows.length) + "）", 1)
              ]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small",
              variant: "text",
              disabled: __props.busy,
              onClick: _cache[12] || (_cache[12] = $event => (emit('clear-selection')))
            }, {
              default: _withCtx$4(() => [...(_cache[29] || (_cache[29] = [
                _createTextVNode$6("取消选择", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"])
          ]))
        : _createCommentVNode$5("", true),
      _createVNode$6(_component_VDataTable, {
        class: "magicflow-torrent-table torrent-table-clickable",
        headers: __props.headers,
        items: __props.rows,
        loading: __props.loading,
        "items-per-page": 10,
        density: "comfortable",
        "onClick:row": _cache[15] || (_cache[15] = (event, payload) => emit('row-click', event, payload))
      }, {
        "header.select": _withCtx$4(() => [
          _createVNode$6(_component_VCheckbox, {
            "model-value": __props.allSelected,
            indeterminate: __props.selectedHashes.length > 0 && !__props.allSelected,
            density: "compact",
            "hide-details": "",
            "aria-label": "全选",
            "onUpdate:modelValue": _cache[13] || (_cache[13] = value => (value ? emit('select-all') : emit('clear-selection')))
          }, null, 8, ["model-value", "indeterminate"])
        ]),
        "item.select": _withCtx$4(({ item }) => [
          _createVNode$6(_component_VCheckbox, {
            "model-value": __props.selectedHashes.includes(item.hash),
            density: "compact",
            "hide-details": "",
            "aria-label": `选择 ${item.title || ''}`,
            onClick: _cache[14] || (_cache[14] = _withModifiers$1(() => {}, ["stop"])),
            "onUpdate:modelValue": $event => (emit('toggle-row', item))
          }, null, 8, ["model-value", "aria-label", "onUpdate:modelValue"])
        ]),
        "item.title": _withCtx$4(({ item }) => [
          _createElementVNode$6("div", _hoisted_5$4, [
            _createElementVNode$6("strong", null, _toDisplayString$6(item.title || '未知种子'), 1),
            _createElementVNode$6("span", null, _toDisplayString$6(__props.task.site_name), 1)
          ])
        ]),
        "item.status": _withCtx$4(({ item }) => [
          _createVNode$6(_component_VChip, {
            size: "small",
            color: stateColor(item.state),
            variant: "tonal"
          }, {
            default: _withCtx$4(() => [
              _createTextVNode$6(_toDisplayString$6(torrentStateText(item)), 1)
            ]),
            _: 2
          }, 1032, ["color"])
        ]),
        "item.size_gb": _withCtx$4(({ item }) => [
          _createTextVNode$6(_toDisplayString$6(Number(item.size_gb || 0).toFixed(2)) + " GB", 1)
        ]),
        "item.uploaded": _withCtx$4(({ item }) => [
          _createTextVNode$6(_toDisplayString$6(_unref$2(formatBytes)(item.uploaded)), 1)
        ]),
        "item.ratio": _withCtx$4(({ item }) => [
          _createTextVNode$6(_toDisplayString$6(Number(item.ratio || 0).toFixed(2)), 1)
        ]),
        "item.actions": _withCtx$4(({ item }) => [
          _createVNode$6(_component_VBtn, {
            size: "small",
            variant: "text",
            icon: item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline',
            "aria-label": item.is_protected ? '取消保留' : '保留',
            onClick: $event => (emit('torrent-action', item, item.is_protected ? 'unprotect' : 'protect'))
          }, null, 8, ["icon", "aria-label", "onClick"]),
          _createVNode$6(_component_VBtn, {
            size: "small",
            variant: "text",
            color: "error",
            icon: "mdi-delete-outline",
            "aria-label": "删除",
            onClick: $event => (emit('delete', item))
          }, null, 8, ["onClick"]),
          _createVNode$6(_component_VMenu, { location: "bottom end" }, {
            activator: _withCtx$4(({ props: menuProps }) => [
              _createVNode$6(_component_VBtn, _mergeProps$1(menuProps, {
                size: "small",
                variant: "text",
                icon: "mdi-dots-vertical",
                "aria-label": "更多操作"
              }), null, 16)
            ]),
            default: _withCtx$4(() => [
              _createVNode$6(_component_VList, {
                density: "compact",
                "min-width": "168"
              }, {
                default: _withCtx$4(() => [
                  (torrentIsPaused(item))
                    ? (_openBlock$6(), _createBlock$4(_component_VListItem, {
                        key: 0,
                        "prepend-icon": "mdi-play-circle-outline",
                        title: torrentResumeLabel(item),
                        onClick: $event => (emit('torrent-action', item, 'resume'))
                      }, null, 8, ["title", "onClick"]))
                    : (_openBlock$6(), _createBlock$4(_component_VListItem, {
                        key: 1,
                        "prepend-icon": "mdi-pause-circle-outline",
                        title: torrentPauseLabel(item),
                        subtitle: "不会被自动恢复",
                        onClick: $event => (emit('torrent-action', item, 'pause'))
                      }, null, 8, ["title", "onClick"])),
                  _createVNode$6(_component_VListItem, {
                    "prepend-icon": "mdi-sync",
                    title: "强制校验",
                    onClick: $event => (emit('torrent-action', item, 'recheck'))
                  }, null, 8, ["onClick"]),
                  _createVNode$6(_component_VDivider, { class: "my-1" }),
                  _createVNode$6(_component_VListItem, {
                    "prepend-icon": "mdi-pin",
                    title: "手动保种",
                    subtitle: "下完也一直做种，不被自动释放",
                    onClick: $event => (emit('torrent-action', item, 'hold'))
                  }, null, 8, ["onClick"]),
                  _createVNode$6(_component_VListItem, {
                    "prepend-icon": "mdi-pin-off",
                    title: "解除手动保种",
                    subtitle: "退回静默池（可能被自动暂停）",
                    onClick: $event => (emit('torrent-action', item, 'unhold'))
                  }, null, 8, ["onClick"]),
                  _createVNode$6(_component_VDivider, { class: "my-1" }),
                  _createVNode$6(_component_VListItem, {
                    "prepend-icon": "mdi-delete-outline",
                    title: "删除种子",
                    "base-color": "error",
                    onClick: $event => (emit('delete', item))
                  }, null, 8, ["onClick"])
                ]),
                _: 2
              }, 1024)
            ]),
            _: 2
          }, 1024)
        ]),
        "no-data": _withCtx$4(() => [...(_cache[30] || (_cache[30] = [
          _createElementVNode$6("div", { class: "magicflow-table-empty" }, "当前筛选下没有托管种子", -1)
        ]))]),
        _: 1
      }, 8, ["headers", "items", "loading"]),
      _createElementVNode$6("div", _hoisted_6$4, [
        (_openBlock$6(true), _createElementBlock$5(_Fragment$5, null, _renderList$5(__props.rows, (item) => {
          return (_openBlock$6(), _createElementBlock$5("article", {
            key: item.hash || item.title,
            class: "magicflow-mobile-torrent",
            onClick: $event => (emit('open-detail', item))
          }, [
            _createElementVNode$6("div", _hoisted_8$4, [
              _createVNode$6(_component_VCheckbox, {
                "model-value": __props.selectedHashes.includes(item.hash),
                density: "compact",
                "hide-details": "",
                class: "magicflow-mobile-torrent__check",
                onClick: _cache[16] || (_cache[16] = _withModifiers$1(() => {}, ["stop"])),
                "onUpdate:modelValue": $event => (emit('toggle-row', item))
              }, null, 8, ["model-value", "onUpdate:modelValue"]),
              _createElementVNode$6("div", _hoisted_9$4, [
                _createElementVNode$6("strong", null, _toDisplayString$6(item.title || '未知种子'), 1),
                _createElementVNode$6("span", null, _toDisplayString$6(__props.task.site_name), 1)
              ]),
              _createVNode$6(_component_VChip, {
                size: "small",
                color: stateColor(item.state),
                variant: "tonal",
                class: "magicflow-mobile-torrent__state"
              }, {
                default: _withCtx$4(() => [
                  _createTextVNode$6(_toDisplayString$6(torrentStateText(item)), 1)
                ]),
                _: 2
              }, 1032, ["color"])
            ]),
            _createVNode$6(_component_VProgressLinear, {
              "model-value": torrentProgressPct(item),
              color: stateColor(item.state),
              height: "6",
              rounded: "",
              class: "magicflow-mobile-torrent__bar"
            }, null, 8, ["model-value", "color"]),
            _createElementVNode$6("div", _hoisted_10$4, [
              _createElementVNode$6("span", null, [
                _cache[31] || (_cache[31] = _createElementVNode$6("em", null, "大小", -1)),
                _createElementVNode$6("b", null, _toDisplayString$6(Number(item.size_gb || 0).toFixed(2)) + " GB", 1)
              ]),
              _createElementVNode$6("span", null, [
                _cache[32] || (_cache[32] = _createElementVNode$6("em", null, "上传量", -1)),
                _createElementVNode$6("b", null, _toDisplayString$6(_unref$2(formatBytes)(item.uploaded)), 1)
              ]),
              _createElementVNode$6("span", null, [
                _cache[33] || (_cache[33] = _createElementVNode$6("em", null, "分享率", -1)),
                _createElementVNode$6("b", null, _toDisplayString$6(Number(item.ratio || 0).toFixed(2)), 1)
              ])
            ]),
            _createElementVNode$6("div", _hoisted_11$4, [
              _createVNode$6(_component_VBtn, {
                size: "small",
                variant: "tonal",
                color: item.is_protected ? 'grey' : 'primary',
                "prepend-icon": item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline',
                onClick: _withModifiers$1($event => (emit('torrent-action', item, item.is_protected ? 'unprotect' : 'protect')), ["stop"])
              }, {
                default: _withCtx$4(() => [
                  _createTextVNode$6(_toDisplayString$6(item.is_protected ? '取消保留' : '保留'), 1)
                ]),
                _: 2
              }, 1032, ["color", "prepend-icon", "onClick"]),
              _createVNode$6(_component_VBtn, {
                size: "small",
                variant: "tonal",
                color: "error",
                "prepend-icon": "mdi-delete-outline",
                onClick: _withModifiers$1($event => (emit('delete', item)), ["stop"])
              }, {
                default: _withCtx$4(() => [...(_cache[34] || (_cache[34] = [
                  _createTextVNode$6("删除", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"]),
              (torrentIsPaused(item))
                ? (_openBlock$6(), _createBlock$4(_component_VBtn, {
                    key: 0,
                    size: "small",
                    variant: "tonal",
                    "prepend-icon": "mdi-play-circle-outline",
                    onClick: _withModifiers$1($event => (emit('torrent-action', item, 'resume')), ["stop"])
                  }, {
                    default: _withCtx$4(() => [
                      _createTextVNode$6(_toDisplayString$6(torrentProgressPct(item) >= 100 ? '恢复' : '继续'), 1)
                    ]),
                    _: 2
                  }, 1032, ["onClick"]))
                : (_openBlock$6(), _createBlock$4(_component_VBtn, {
                    key: 1,
                    size: "small",
                    variant: "tonal",
                    "prepend-icon": "mdi-pause-circle-outline",
                    onClick: _withModifiers$1($event => (emit('torrent-action', item, 'pause')), ["stop"])
                  }, {
                    default: _withCtx$4(() => [...(_cache[35] || (_cache[35] = [
                      _createTextVNode$6("暂停", -1)
                    ]))]),
                    _: 1
                  }, 8, ["onClick"])),
              _createVNode$6(_component_VBtn, {
                size: "small",
                variant: "tonal",
                "prepend-icon": "mdi-sync",
                onClick: _withModifiers$1($event => (emit('torrent-action', item, 'recheck')), ["stop"])
              }, {
                default: _withCtx$4(() => [...(_cache[36] || (_cache[36] = [
                  _createTextVNode$6("校验", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"])
            ])
          ], 8, _hoisted_7$4))
        }), 128)),
        (!__props.rows.length)
          ? (_openBlock$6(), _createElementBlock$5("div", _hoisted_12$4, "当前筛选下没有托管种子"))
          : _createCommentVNode$5("", true)
      ])
    ]),
    _: 1
  }))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const SeedingTab = Object.assign(_sfc_main$6, { __scopeId: 'data-v-f0e284f2' })

export default SeedingTab
