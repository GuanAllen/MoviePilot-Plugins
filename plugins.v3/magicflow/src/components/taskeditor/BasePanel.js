// BasePanel —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './BasePanel.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$L,
  createBlock: _createBlock$P,
  createCommentVNode: _createCommentVNode$N,
  createElementBlock: _createElementBlock$N,
  createElementVNode: _createElementVNode$T,
  createTextVNode: _createTextVNode$Q,
  createVNode: _createVNode$S,
  mergeModels: _mergeModels$z,
  normalizeClass: _normalizeClass$q,
  openBlock: _openBlock$T,
  renderList: _renderList$E,
  resolveComponent: _resolveComponent$T,
  toDisplayString: _toDisplayString$Q,
  unref: _unref$n,
  useModel: _useModel$B,
  withCtx: _withCtx$Q,
} = __vue

import TaskEditorDialog from '../TaskEditorDialog.js'
import { formatBytes } from '../../utils.js'

const _hoisted_1$P = { class: "editor-section" };
const _hoisted_2$N = { class: "editor-presets" };
const _hoisted_3$K = ["onClick"];
const _hoisted_4$K = { class: "editor-preset__title" };
const _hoisted_5$J = { class: "editor-preset__desc" };
const _hoisted_6$F = {
  key: 0,
  class: "editor-simple-note"
};
const _hoisted_7$B = { class: "editor-section" };
const _hoisted_8$x = { class: "editor-section__head" };
const _hoisted_9$v = {
  key: 0,
  class: "editor-pool__hint"
};
const _hoisted_10$u = { key: 1 };
const _hoisted_11$s = {
  key: 0,
  class: "editor-quota"
};
const _hoisted_12$r = { class: "editor-quota__head" };
const _hoisted_13$p = { class: "editor-quota__foot" };
const _hoisted_14$o = {
  key: 0,
  class: "editor-pool__hint"
};
const _hoisted_15$o = { class: "editor-switches" };
const _hoisted_16$o = {
  key: 0,
  class: "editor-section"
};
const _hoisted_17$o = { class: "editor-section__head" };
const _hoisted_18$o = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_19$n = { class: "editor-section" };
const _hoisted_20$k = { class: "editor-section__head" };
const _hoisted_21$j = { class: "text-body-2 text-medium-emphasis" };


const _sfc_main$T = {
  __name: 'BasePanel',
  props: /*@__PURE__*/_mergeModels$z({
  presets: { type: Array, default: () => [] },
  presetKey: { type: String, default: '' },
  simpleMode: { type: Boolean, default: false },
  presetPatchCount: { type: Number, default: 0 },
  sites: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  autoTag: { type: String, default: '' },
  savePathOptions: { type: Array, default: () => [] },
  pool: { type: Object, default: null },
  poolOver: { type: Boolean, default: false },
  poolError: { type: String, default: '' },
  poolLoading: { type: Boolean, default: false },
  poolFreeText: { type: String, default: '—' },
  poolBudgetText: { type: String, default: '' },
  scheduleText: { type: String, default: '' },
  isBrush: { type: Boolean, default: false },
  savePathRequired: { type: Boolean, default: true }, // ★ 19.10.36：刷流/魔力保存目录必填（host 不下载，留空合法）
}, {
    "siteId": {},
    "siteIdModifiers": {},
    "name": {},
    "nameModifiers": {},
    "downloader": {},
    "downloaderModifiers": {},
    "brushTag": {},
    "brushTagModifiers": {},
    "savePath": {},
    "savePathModifiers": {},
    "enabled": {},
    "enabledModifiers": {},
    "rssSupport": {},
    "rssSupportModifiers": {},
    "brushInterval": {},
    "brushIntervalModifiers": {},
    "checkInterval": {},
    "checkIntervalModifiers": {},
    "cronExpression": {},
    "cronExpressionModifiers": {},
    "activeTimeRange": {},
    "activeTimeRangeModifiers": {},
    "goalValue": {},
    "goalValueModifiers": {},
    "poolPct": {},
    "poolPctModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$z([
  'apply-preset', 'site-change', 'save-path-change', 'remember-save-path', 'load-pool', 'pct-change',
], ["update:siteId", "update:name", "update:downloader", "update:brushTag", "update:savePath", "update:enabled", "update:rssSupport", "update:brushInterval", "update:checkInterval", "update:cronExpression", "update:activeTimeRange", "update:goalValue", "update:poolPct"]),
  setup(__props, { emit: __emit }) {

// MagicFlow · 任务编辑器「基础与调度」面板 —— P6 自 components/TaskEditorDialog.vue **纯搬家**。
// props 下 / emit 上：面板不直接读写父状态；双向字段走 defineModel，动作走 emit，只读值走 props。
const emit = __emit;

// 双向绑定字段：父 localTask.<snake_case> ↔ defineModel(<camelCase>)
const siteId = _useModel$B(__props, 'siteId');
const name = _useModel$B(__props, 'name');
const downloader = _useModel$B(__props, 'downloader');
const brushTag = _useModel$B(__props, 'brushTag');
const savePath = _useModel$B(__props, 'savePath');
const enabled = _useModel$B(__props, 'enabled');
const rssSupport = _useModel$B(__props, 'rssSupport');
const brushInterval = _useModel$B(__props, 'brushInterval');
const checkInterval = _useModel$B(__props, 'checkInterval');
const cronExpression = _useModel$B(__props, 'cronExpression');
const activeTimeRange = _useModel$B(__props, 'activeTimeRange');
const goalValue = _useModel$B(__props, 'goalValue');
// 磁盘体积占比（父 ref，非 localTask 字段，但同为双向绑定）
const poolPct = _useModel$B(__props, 'poolPct');

// 只读数据 / 计算值（父照常传）


// 保存目录必填提示：空值不会报错，只会让任务每轮静默跳过（见后端 _save_path_blocker）。
const savePathRule = v => !!String(v ?? '').trim() || '必填：留空会导致任务一直不下载';

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$T("VIcon");
  const _component_VChip = _resolveComponent$T("VChip");
  const _component_VSelect = _resolveComponent$T("VSelect");
  const _component_VCol = _resolveComponent$T("VCol");
  const _component_VTextField = _resolveComponent$T("VTextField");
  const _component_VCombobox = _resolveComponent$T("VCombobox");
  const _component_VSlider = _resolveComponent$T("VSlider");
  const _component_VRow = _resolveComponent$T("VRow");
  const _component_VSwitch = _resolveComponent$T("VSwitch");

  return (_openBlock$T(), _createElementBlock$N(_Fragment$L, null, [
    _createElementVNode$T("section", _hoisted_1$P, [
      _cache[19] || (_cache[19] = _createElementVNode$T("header", { class: "editor-section__head" }, [
        _createElementVNode$T("div", null, [
          _createElementVNode$T("div", { class: "text-subtitle-1 font-weight-medium" }, "任务模板"),
          _createElementVNode$T("div", { class: "text-body-2 text-medium-emphasis" }, " 选一个就行 —— 选种/清理/限速/复用等参数按模板自动配好，站点·目录·目标自己定 ")
        ])
      ], -1)),
      _createElementVNode$T("div", _hoisted_2$N, [
        (_openBlock$T(true), _createElementBlock$N(_Fragment$L, null, _renderList$E(__props.presets, (p) => {
          return (_openBlock$T(), _createElementBlock$N("button", {
            key: p.key,
            type: "button",
            class: _normalizeClass$q(["editor-preset", { 'is-active': __props.presetKey === p.key }]),
            onClick: $event => (emit('apply-preset', p.key))
          }, [
            _createVNode$S(_component_VIcon, {
              icon: p.icon,
              size: "18"
            }, null, 8, ["icon"]),
            _createElementVNode$T("span", _hoisted_4$K, _toDisplayString$Q(p.title), 1),
            _createElementVNode$T("span", _hoisted_5$J, _toDisplayString$Q(p.desc), 1)
          ], 10, _hoisted_3$K))
        }), 128))
      ]),
      (__props.simpleMode)
        ? (_openBlock$T(), _createElementBlock$N("div", _hoisted_6$F, [
            _createVNode$S(_component_VIcon, {
              icon: "mdi-auto-fix",
              size: "14"
            }),
            _createElementVNode$T("span", null, "已自动配置 " + _toDisplayString$Q(__props.presetPatchCount) + " 项专业参数（调度 5 分钟 · 复用辅种 · 清理低效 · 限速两档 · 体积上限）", 1),
            _createElementVNode$T("button", {
              type: "button",
              class: "editor-simple-note__link",
              onClick: _cache[0] || (_cache[0] = $event => (emit('apply-preset', 'custom')))
            }, "展开全部参数")
          ]))
        : _createCommentVNode$N("", true)
    ]),
    _createElementVNode$T("section", _hoisted_7$B, [
      _createElementVNode$T("header", _hoisted_8$x, [
        _cache[21] || (_cache[21] = _createElementVNode$T("div", null, [
          _createElementVNode$T("div", { class: "text-subtitle-1 font-weight-medium" }, "任务身份"),
          _createElementVNode$T("div", { class: "text-body-2 text-medium-emphasis" }, "每个任务绑定一个站点和下载器")
        ], -1)),
        _createVNode$S(_component_VChip, {
          size: "small",
          color: "primary",
          variant: "tonal"
        }, {
          default: _withCtx$Q(() => [...(_cache[20] || (_cache[20] = [
            _createTextVNode$Q("必填", -1)
          ]))]),
          _: 1
        })
      ]),
      _createVNode$S(_component_VRow, null, {
        default: _withCtx$Q(() => [
          _createVNode$S(_component_VCol, {
            cols: "12",
            md: "6"
          }, {
            default: _withCtx$Q(() => [
              _createVNode$S(_component_VSelect, {
                modelValue: siteId.value,
                "onUpdate:modelValue": [
                  _cache[1] || (_cache[1] = $event => ((siteId).value = $event)),
                  _cache[2] || (_cache[2] = $event => (emit('site-change')))
                ],
                items: __props.sites,
                "item-title": "name",
                "item-value": "id",
                label: "站点",
                rules: [value => !!value || '请选择站点']
              }, null, 8, ["modelValue", "items", "rules"])
            ]),
            _: 1
          }),
          _createVNode$S(_component_VCol, {
            cols: "12",
            md: "6"
          }, {
            default: _withCtx$Q(() => [
              _createVNode$S(_component_VTextField, {
                modelValue: name.value,
                "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((name).value = $event)),
                label: "任务名称",
                hint: "选站点后自动填「站点·模板名」，可手改",
                rules: [value => !!String(value || '').trim() || '请输入任务名称']
              }, null, 8, ["modelValue", "rules"])
            ]),
            _: 1
          }),
          (__props.downloaders.length > 1)
            ? (_openBlock$T(), _createBlock$P(_component_VCol, {
                key: 0,
                cols: "12",
                md: "6"
              }, {
                default: _withCtx$Q(() => [
                  _createVNode$S(_component_VSelect, {
                    modelValue: downloader.value,
                    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((downloader).value = $event)),
                    items: __props.downloaders,
                    label: "下载器",
                    rules: [value => !!value || '请选择下载器']
                  }, null, 8, ["modelValue", "items", "rules"])
                ]),
                _: 1
              }))
            : (__props.downloaders.length === 1)
              ? (_openBlock$T(), _createBlock$P(_component_VCol, {
                  key: 1,
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx$Q(() => [
                    _createVNode$S(_component_VTextField, {
                      "model-value": downloader.value || __props.downloaders[0].title || __props.downloaders[0].value,
                      label: "下载器",
                      readonly: "",
                      "prepend-inner-icon": "mdi-lock-outline",
                      hint: "只接了一台下载器，自动使用（接多台后可切换）",
                      "persistent-hint": ""
                    }, null, 8, ["model-value"])
                  ]),
                  _: 1
                }))
              : _createCommentVNode$N("", true),
          (!__props.simpleMode)
            ? (_openBlock$T(), _createBlock$P(_component_VCol, {
                key: 2,
                cols: "12",
                md: "6"
              }, {
                default: _withCtx$Q(() => [
                  _createVNode$S(_component_VTextField, {
                    modelValue: brushTag.value,
                    "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((brushTag).value = $event)),
                    label: "下载器标签",
                    readonly: "",
                    "prepend-inner-icon": "mdi-lock-outline",
                    hint: `自动：${__props.autoTag || '魔流-站点-职务'}（按站点+类型派生，只读）`,
                    "persistent-hint": ""
                  }, null, 8, ["modelValue", "hint"])
                ]),
                _: 1
              }))
            : _createCommentVNode$N("", true),
          _createVNode$S(_component_VCol, { cols: "12" }, {
            default: _withCtx$Q(() => [
              _createVNode$S(_component_VCombobox, {
                modelValue: savePath.value,
                "onUpdate:modelValue": [
                  _cache[6] || (_cache[6] = $event => ((savePath).value = $event)),
                  _cache[7] || (_cache[7] = $event => (emit('save-path-change')))
                ],
                items: __props.savePathOptions,
                label: "保存目录",
                rules: __props.savePathRequired ? [savePathRule] : [],
                "onUpdate:focused": _cache[8] || (_cache[8] = focused => { if (!focused) emit('remember-save-path', savePath.value); }),
                placeholder: __props.savePathRequired ? '必填：如 /vol6/1000/movie/刷流' : '留空使用下载器默认目录',
                hint: __props.savePathRequired
            ? '刷流/魔力任务会往这里下载种子；留空会让任务每轮静默跳过（不下载）'
            : '默认目录可在插件设置「下载目录」里配置',
                "persistent-hint": "",
                clearable: "",
                variant: "outlined"
              }, null, 8, ["modelValue", "items", "rules", "placeholder", "hint"])
            ]),
            _: 1
          }),
          _createVNode$S(_component_VCol, { cols: "12" }, {
            default: _withCtx$Q(() => [
              _createElementVNode$T("div", {
                class: _normalizeClass$q(["editor-pool", { 'is-warn': __props.poolOver, 'is-error': !!__props.poolError }])
              }, [
                _createVNode$S(_component_VIcon, {
                  icon: __props.poolOver ? 'mdi-alert-outline' : 'mdi-harddisk',
                  size: "14"
                }, null, 8, ["icon"]),
                (__props.pool)
                  ? (_openBlock$T(), _createElementBlock$N(_Fragment$L, { key: 0 }, [
                      _createElementVNode$T("span", null, " 磁盘 " + _toDisplayString$Q(__props.pool.path) + " · 已用 " + _toDisplayString$Q(__props.pool.pct.toFixed(0)) + "%（" + _toDisplayString$Q(_unref$n(formatBytes)(__props.pool.used_gb * 1024 ** 3)) + " / " + _toDisplayString$Q(_unref$n(formatBytes)(__props.pool.total_gb * 1024 ** 3)) + "）· 按 80% 阈值还能再放 " + _toDisplayString$Q(__props.poolFreeText), 1),
                      (__props.poolOver)
                        ? (_openBlock$T(), _createElementBlock$N("span", _hoisted_9$v, "已超 80%，建议先清理再加种"))
                        : _createCommentVNode$N("", true)
                    ], 64))
                  : (_openBlock$T(), _createElementBlock$N("span", _hoisted_10$u, _toDisplayString$Q(__props.poolLoading ? '正在读取磁盘空间…' : (__props.poolError || '磁盘空间未知')), 1)),
                _createElementVNode$T("button", {
                  type: "button",
                  class: "editor-pool__link",
                  onClick: _cache[9] || (_cache[9] = $event => (emit('load-pool')))
                }, "刷新")
              ], 2),
              (__props.simpleMode && __props.pool)
                ? (_openBlock$T(), _createElementBlock$N("div", _hoisted_11$s, [
                    _createElementVNode$T("div", _hoisted_12$r, [
                      _cache[22] || (_cache[22] = _createElementVNode$T("span", null, "本任务最多占多少", -1)),
                      _createElementVNode$T("strong", null, _toDisplayString$Q(__props.poolBudgetText), 1)
                    ]),
                    _createVNode$S(_component_VSlider, {
                      modelValue: poolPct.value,
                      "onUpdate:modelValue": [
                        _cache[10] || (_cache[10] = $event => ((poolPct).value = $event)),
                        _cache[11] || (_cache[11] = $event => (emit('pct-change')))
                      ],
                      min: 0,
                      max: 100,
                      step: 5,
                      color: "primary",
                      "hide-details": "",
                      density: "compact",
                      disabled: __props.poolOver
                    }, null, 8, ["modelValue", "disabled"]),
                    _createElementVNode$T("div", _hoisted_13$p, [
                      _createElementVNode$T("span", null, _toDisplayString$Q(poolPct.value) + "% · 占磁盘剩余可用（" + _toDisplayString$Q(__props.poolFreeText) + "）", 1),
                      (__props.poolOver)
                        ? (_openBlock$T(), _createElementBlock$N("span", _hoisted_14$o, "磁盘已超 80%，先清理再加种"))
                        : _createCommentVNode$N("", true)
                    ])
                  ]))
                : _createCommentVNode$N("", true)
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createElementVNode$T("div", _hoisted_15$o, [
        _createVNode$S(_component_VSwitch, {
          modelValue: enabled.value,
          "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((enabled).value = $event)),
          label: "启用任务",
          color: "primary",
          "hide-details": "",
          inset: ""
        }, null, 8, ["modelValue"]),
        (!__props.simpleMode)
          ? (_openBlock$T(), _createBlock$P(_component_VSwitch, {
              key: 0,
              modelValue: rssSupport.value,
              "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((rssSupport).value = $event)),
              label: "使用 RSS",
              color: "primary",
              "hide-details": "",
              inset: ""
            }, null, 8, ["modelValue"]))
          : _createCommentVNode$N("", true)
      ])
    ]),
    (!__props.simpleMode)
      ? (_openBlock$T(), _createElementBlock$N("section", _hoisted_16$o, [
          _createElementVNode$T("header", _hoisted_17$o, [
            _cache[23] || (_cache[23] = _createElementVNode$T("div", null, [
              _createElementVNode$T("div", { class: "text-subtitle-1 font-weight-medium" }, "刷新计划"),
              _createElementVNode$T("div", { class: "text-body-2 text-medium-emphasis" }, "选种刷新和做种检查分别调度")
            ], -1)),
            _createElementVNode$T("span", _hoisted_18$o, _toDisplayString$Q(__props.scheduleText), 1)
          ]),
          _createVNode$S(_component_VRow, null, {
            default: _withCtx$Q(() => [
              _createVNode$S(_component_VCol, {
                cols: "12",
                md: "6"
              }, {
                default: _withCtx$Q(() => [
                  _createVNode$S(_component_VTextField, {
                    modelValue: brushInterval.value,
                    "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((brushInterval).value = $event)),
                    modelModifiers: { number: true },
                    type: "number",
                    min: "1",
                    max: "1440",
                    label: "选种刷新周期（分钟）"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              _createVNode$S(_component_VCol, {
                cols: "12",
                md: "6"
              }, {
                default: _withCtx$Q(() => [
                  _createVNode$S(_component_VTextField, {
                    modelValue: checkInterval.value,
                    "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((checkInterval).value = $event)),
                    modelModifiers: { number: true },
                    type: "number",
                    min: "1",
                    max: "1440",
                    label: "做种检查周期（分钟）"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              _createVNode$S(_component_VCol, {
                cols: "12",
                md: "6"
              }, {
                default: _withCtx$Q(() => [
                  _createVNode$S(_component_VTextField, {
                    modelValue: cronExpression.value,
                    "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((cronExpression).value = $event)),
                    label: "CRON 表达式",
                    placeholder: "留空使用固定刷新周期"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              _createVNode$S(_component_VCol, {
                cols: "12",
                md: "6"
              }, {
                default: _withCtx$Q(() => [
                  _createVNode$S(_component_VTextField, {
                    modelValue: activeTimeRange.value,
                    "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((activeTimeRange).value = $event)),
                    label: "开启时间段",
                    placeholder: "如 00:00-08:00"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]))
      : _createCommentVNode$N("", true),
    _createElementVNode$T("section", _hoisted_19$n, [
      _createElementVNode$T("header", _hoisted_20$k, [
        _createElementVNode$T("div", null, [
          _cache[24] || (_cache[24] = _createElementVNode$T("div", { class: "text-subtitle-1 font-weight-medium" }, "任务目标", -1)),
          _createElementVNode$T("div", _hoisted_21$j, _toDisplayString$Q(__props.isBrush ? '站点上传量达到目标后，任务自动停止' : '站点魔力值达到目标后，任务自动停止'), 1)
        ]),
        _createVNode$S(_component_VChip, {
          size: "small",
          color: "primary",
          variant: "tonal"
        }, {
          default: _withCtx$Q(() => [...(_cache[25] || (_cache[25] = [
            _createTextVNode$Q("建议填写", -1)
          ]))]),
          _: 1
        })
      ]),
      _createVNode$S(_component_VRow, null, {
        default: _withCtx$Q(() => [
          _createVNode$S(_component_VCol, { cols: "12" }, {
            default: _withCtx$Q(() => [
              _createVNode$S(_component_VTextField, {
                modelValue: goalValue.value,
                "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((goalValue).value = $event)),
                modelModifiers: { number: true },
                type: "number",
                min: "0",
                step: "any",
                label: __props.isBrush ? '目标上传量（GB）' : '目标魔力值',
                clearable: ""
              }, null, 8, ["modelValue", "label"])
            ]),
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
const BasePanel = Object.assign(_sfc_main$T, { __scopeId: 'data-v-e993f6a4' })

export default BasePanel
