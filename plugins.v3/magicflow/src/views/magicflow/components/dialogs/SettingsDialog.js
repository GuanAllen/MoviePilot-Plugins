// SettingsDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './SettingsDialog.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$a,
  createBlock: _createBlock$a,
  createCommentVNode: _createCommentVNode$a,
  createElementBlock: _createElementBlock$a,
  createElementVNode: _createElementVNode$c,
  createTextVNode: _createTextVNode$b,
  createVNode: _createVNode$b,
  mergeModels: _mergeModels$5,
  normalizeClass: _normalizeClass$4,
  openBlock: _openBlock$c,
  renderList: _renderList$8,
  resolveComponent: _resolveComponent$c,
  toDisplayString: _toDisplayString$c,
  unref: _unref$5,
  useModel: _useModel$5,
  withCtx: _withCtx$a,
} = __vue

import index from '../../index.vue'
import { MF_SETTINGS_TABS, TILE_OPTIONS, agentToolScopeItems, episodePolicyItems, ratingSourceItems } from '../../constants.js'
import { fallbackSourceLabel } from '../../composables/useFallback.js'
import { fmtTs } from '../../format.js'
import { ruleSourceText, settingsTabLabel } from '../../composables/useSettings.js'
import { sortRuleNeedsMin, sortRuleText, sortRuleTypeOptions } from '../../composables/useTagModel.js'

const _hoisted_1$a = { class: "magicflow-settings-dialog__head" };
const _hoisted_2$9 = { class: "magicflow-settings-dialog__title" };
const _hoisted_3$8 = ["onClick"];
const _hoisted_4$8 = {
  key: 2,
  class: "magicflow-settings-dialog__body"
};
const _hoisted_5$8 = {
  key: 0,
  class: "magicflow-settings-form"
};
const _hoisted_6$7 = {
  key: 1,
  class: "magicflow-settings-form"
};
const _hoisted_7$6 = {
  key: 1,
  class: "magicflow-settings-hint"
};
const _hoisted_8$6 = { class: "magicflow-settings-grid" };
const _hoisted_9$6 = { class: "magicflow-settings-block" };
const _hoisted_10$6 = { class: "magicflow-settings-block__head" };
const _hoisted_11$6 = { class: "magicflow-tile-switches" };
const _hoisted_12$6 = { class: "magicflow-field__sub" };
const _hoisted_13$5 = { class: "magicflow-settings-block" };
const _hoisted_14$5 = { class: "magicflow-settings-block__head" };
const _hoisted_15$5 = { class: "magicflow-settings-grid" };
const _hoisted_16$5 = {
  key: 2,
  class: "magicflow-settings-form"
};
const _hoisted_17$5 = { class: "magicflow-settings-grid" };
const _hoisted_18$5 = {
  key: 3,
  class: "magicflow-settings-form"
};
const _hoisted_19$5 = { class: "magicflow-iyuu-token" };
const _hoisted_20$5 = { class: "magicflow-iyuu-sites" };
const _hoisted_21$4 = { class: "magicflow-iyuu-sites__head" };
const _hoisted_22$3 = {
  key: 0,
  class: "magicflow-settings-hint"
};
const _hoisted_23$2 = {
  key: 1,
  class: "magicflow-settings-hint"
};
const _hoisted_24$2 = { class: "magicflow-iyuu-row__head" };
const _hoisted_25$2 = { class: "magicflow-iyuu-row__name" };
const _hoisted_26$2 = { class: "magicflow-iyuu-row__fields" };
const _hoisted_27$2 = {
  key: 4,
  class: "magicflow-settings-form"
};
const _hoisted_28$2 = { class: "magicflow-settings-switches" };
const _hoisted_29$2 = { class: "magicflow-settings-block" };
const _hoisted_30$2 = { class: "magicflow-settings-block__head" };
const _hoisted_31$2 = { class: "magicflow-field__sub" };
const _hoisted_32$2 = { class: "magicflow-settings-block" };
const _hoisted_33$2 = { class: "magicflow-settings-block__head" };
const _hoisted_34$2 = {
  key: 0,
  class: "magicflow-field__sub"
};
const _hoisted_35$2 = { class: "magicflow-settings-block" };
const _hoisted_36$2 = { class: "magicflow-settings-block__head" };
const _hoisted_37$2 = { class: "magicflow-settings-grid" };
const _hoisted_38$2 = { class: "magicflow-settings-block" };
const _hoisted_39$2 = { class: "magicflow-settings-block__head" };
const _hoisted_40$2 = {
  key: 0,
  class: "magicflow-reseedpanel"
};
const _hoisted_41$2 = { class: "magicflow-reseedpanel__row" };
const _hoisted_42$2 = { class: "magicflow-field__sub" };
const _hoisted_43$1 = { class: "magicflow-reseedpanel__row" };
const _hoisted_44$1 = { class: "magicflow-field__sub" };
const _hoisted_45$1 = {
  key: 0,
  class: "magicflow-reseedpanel__row"
};
const _hoisted_46$1 = { class: "magicflow-field__sub" };
const _hoisted_47$1 = {
  key: 1,
  class: "magicflow-reseedpanel__row"
};
const _hoisted_48$1 = { class: "magicflow-field__sub" };
const _hoisted_49$1 = { class: "magicflow-reseedpanel__sites" };
const _hoisted_50$1 = { key: 0 };
const _hoisted_51$1 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_52$1 = { class: "magicflow-reseedpanel__row" };
const _hoisted_53$1 = { class: "magicflow-field__sub" };
const _hoisted_54$1 = {
  key: 1,
  class: "magicflow-field__sub"
};
const _hoisted_55$1 = {
  key: 5,
  class: "magicflow-settings-form"
};
const _hoisted_56$1 = { class: "magicflow-settings-switches" };
const _hoisted_57$1 = { class: "magicflow-settings-block" };
const _hoisted_58$1 = { class: "magicflow-settings-block__head" };
const _hoisted_59$1 = { class: "magicflow-field__sub" };
const _hoisted_60$1 = { class: "magicflow-settings-block" };
const _hoisted_61$1 = { class: "magicflow-settings-block__head" };
const _hoisted_62$1 = { class: "magicflow-settings-grid" };
const _hoisted_63$1 = { class: "magicflow-settings-block" };
const _hoisted_64$1 = { class: "magicflow-settings-block__head" };
const _hoisted_65$1 = { class: "magicflow-settings-grid" };
const _hoisted_66$1 = { class: "magicflow-settings-block" };
const _hoisted_67$1 = { class: "magicflow-settings-block__head" };
const _hoisted_68$1 = {
  key: 6,
  class: "magicflow-settings-form"
};
const _hoisted_69$1 = { class: "magicflow-settings-grid" };
const _hoisted_70$1 = { class: "magicflow-settings-switches" };
const _hoisted_71$1 = {
  key: 7,
  class: "magicflow-settings-form"
};
const _hoisted_72$1 = { class: "magicflow-settings-switches" };
const _hoisted_73$1 = { class: "magicflow-settings-field" };
const _hoisted_74$1 = {
  key: 0,
  class: "magicflow-settings-hint magicflow-settings-hint--warn"
};
const _hoisted_75$1 = {
  key: 8,
  class: "magicflow-settings-form"
};
const _hoisted_76$1 = { class: "magicflow-signin-hero" };
const _hoisted_77$1 = { class: "magicflow-signin-hero__icon" };
const _hoisted_78$1 = { class: "magicflow-signin-hero__body" };
const _hoisted_79 = { class: "magicflow-signin-hero__title" };
const _hoisted_80 = { class: "magicflow-settings-block" };
const _hoisted_81 = { class: "magicflow-settings-block__head" };
const _hoisted_82 = { class: "magicflow-switch-list" };
const _hoisted_83 = {
  key: 0,
  class: "magicflow-field__sub"
};
const _hoisted_84 = { class: "magicflow-settings-block" };
const _hoisted_85 = { class: "magicflow-settings-block__head" };
const _hoisted_86 = { class: "magicflow-field-stack" };
const _hoisted_87 = { class: "magicflow-field" };
const _hoisted_88 = { class: "magicflow-field__sub" };
const _hoisted_89 = { class: "magicflow-field" };
const _hoisted_90 = { class: "magicflow-field__sub" };
const _hoisted_91 = { class: "magicflow-signin-actions" };
const _hoisted_92 = {
  key: 9,
  class: "magicflow-settings-form"
};
const _hoisted_93 = { class: "magicflow-settings-switches" };
const _hoisted_94 = { class: "magicflow-settings-switches" };
const _hoisted_95 = { class: "magicflow-settings-switches" };
const _hoisted_96 = { class: "magicflow-settings-grid" };
const _hoisted_97 = { class: "magicflow-settings-grid" };
const _hoisted_98 = {
  key: 0,
  class: "magicflow-live-alerts"
};
const _hoisted_99 = { class: "magicflow-live-alerts__head" };
const _hoisted_100 = {
  key: 10,
  class: "magicflow-settings-form"
};
const _hoisted_101 = { class: "magicflow-settings-grid" };
const _hoisted_102 = { class: "magicflow-settings-grid" };
const _hoisted_103 = { class: "magicflow-settings-switches" };
const _hoisted_104 = {
  key: 11,
  class: "magicflow-settings-form"
};
const _hoisted_105 = { class: "magicflow-settings-switches" };
const _hoisted_106 = { class: "magicflow-settings-grid" };
const _hoisted_107 = { class: "magicflow-settings-switches" };
const _hoisted_108 = { class: "magicflow-rules-actions" };
const _hoisted_109 = { class: "magicflow-settings-hint" };
const _hoisted_110 = { class: "magicflow-settings-hint" };
const _hoisted_111 = {
  key: 0,
  class: "magicflow-settings-hint"
};
const _hoisted_112 = { class: "magicflow-rules-table" };
const _hoisted_113 = ["title"];
const _hoisted_114 = { key: 0 };
const _hoisted_115 = ["title"];
const _hoisted_116 = ["title"];
const _hoisted_117 = { class: "magicflow-rules-row__hr" };
const _hoisted_118 = { class: "magicflow-rules-row__hours" };
const _hoisted_119 = { class: "magicflow-rules-row__ratio" };
const _hoisted_120 = { class: "magicflow-rules-row__ops" };
const _hoisted_121 = {
  key: 12,
  class: "magicflow-settings-form"
};
const _hoisted_122 = { class: "magicflow-settings-switches" };
const _hoisted_123 = { class: "magicflow-settings-grid" };
const _hoisted_124 = { class: "magicflow-sort-rules" };
const _hoisted_125 = { key: 1 };
const _hoisted_126 = { class: "magicflow-sort-rules__add" };
const _hoisted_127 = { class: "magicflow-rules-actions" };
const _hoisted_128 = { class: "magicflow-settings-hint" };
const _hoisted_129 = {
  key: 13,
  class: "magicflow-settings-form"
};
const _hoisted_130 = {
  key: 14,
  class: "magicflow-settings-form"
};
const _hoisted_131 = { class: "magicflow-settings-switches" };
const _hoisted_132 = { class: "magicflow-settings-field" };
const _hoisted_133 = { class: "magicflow-fb-sources" };
const _hoisted_134 = { class: "magicflow-fb-source__idx" };
const _hoisted_135 = { class: "magicflow-fb-source__name" };
const _hoisted_136 = { class: "magicflow-fb-source-add" };
const _hoisted_137 = { class: "magicflow-settings-grid" };
const _hoisted_138 = { class: "magicflow-settings-switches" };
const _hoisted_139 = { class: "magicflow-fb-actions" };
const _hoisted_140 = {
  key: 0,
  class: "magicflow-fb-running"
};
const _hoisted_141 = {
  key: 0,
  class: "magicflow-fb-report"
};
const _hoisted_142 = { class: "magicflow-fb-report__line" };
const _hoisted_143 = {
  key: 0,
  class: "magicflow-fb-report__details"
};
const _hoisted_144 = { class: "magicflow-fb-report__list" };
const _hoisted_145 = { class: "magicflow-fb-report__meta" };
const _hoisted_146 = {
  key: 1,
  class: "magicflow-fb-report__details"
};
const _hoisted_147 = { class: "magicflow-fb-report__list" };
const _hoisted_148 = { class: "magicflow-fb-report__meta" };
const _hoisted_149 = {
  key: 15,
  class: "magicflow-settings-form"
};
const _hoisted_150 = { class: "magicflow-settings-switches" };
const _hoisted_151 = { class: "magicflow-settings-field" };
const _hoisted_152 = { class: "magicflow-iyuu-token" };
const _hoisted_153 = { class: "magicflow-iyuu-token mt-2" };
const _hoisted_154 = { class: "magicflow-settings-grid" };
const _hoisted_155 = { class: "magicflow-settings-grid" };
const _hoisted_156 = { class: "magicflow-settings-switches" };
const _hoisted_157 = { class: "magicflow-settings-dialog__footer" };

// 弹窗开关 / 当前标签 / 可写草稿（双向）

const _sfc_main$c = {
  __name: 'SettingsDialog',
  props: /*@__PURE__*/_mergeModels$5({
  setNavEl: { type: Function, default: null },
  isNarrow: { type: Boolean, default: false },
  settingsPane: { type: String, default: 'form' },
  status: { type: Object, default: null },
  selectedTask: { type: Object, default: null },
  saving: { type: Boolean, default: false },
  settingsDraft: { type: Object, required: true },
  downloaderPrefsDraft: { type: Object, default: null },
  downloaderPathsDraft: { type: Object, default: null },
  defaultsDraft: { type: Object, default: null },
  downloaderPrefsRecommended: { type: Boolean, default: false },
  iyuuSites: { type: Array, default: () => [] },
  iyuuLoading: { type: Boolean, default: false },
  iyuuStatus: { type: Object, default: null },
  iyuuTesting: { type: Boolean, default: false },
  iyuuShowMore: { type: Object, default: () => ({}) },
  siteRules: { type: Array, default: () => [] },
  rulesProbeState: { type: Object, default: () => ({}) },
  rulesLoading: { type: Boolean, default: false },
  rulesProbing: { type: Boolean, default: false },
  reseedState: { type: Object, default: null },
  reseedRunning: { type: Boolean, default: false },
  reseedSiteOptions: { type: Array, default: () => [] },
  claimSiteOptions: { type: Array, default: () => [] },
  siteSelectItems: { type: Array, default: () => [] },
  siteLiveAlerts: { type: Array, default: () => [] },
  tagInfo: { type: Object, default: null },
  fallbackState: { type: Object, default: null },
  fallbackLoading: { type: Boolean, default: false },
  fallbackRunning: { type: Boolean, default: false },
  fallbackProblemShows: { type: Array, default: () => [] },
  fallbackProblemCount: { type: Number, default: 0 },
  usedFallbackSources: { type: Array, default: () => [] },
  unusedFallbackSources: { type: Array, default: () => [] },
  cloudCfg: { type: Object, default: null },
  cloudTestMsg: { type: String, default: '' },
  cloudTestOk: { type: Boolean, default: false },
  cloudTesting: { type: Boolean, default: false },
  tileShown: { type: Function, default: () => false },
}, {
    "modelValue": { type: Boolean, default: false },
    "modelModifiers": {},
    "settingsTab": { type: String, default: 'general' },
    "settingsTabModifiers": {},
    "fallbackSourceDraft": { type: String, default: '' },
    "fallbackSourceDraftModifiers": {},
    "newRuleType": { type: String, default: 'subscribe' },
    "newRuleTypeModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$5([
  'open-tab', 'back-to-dir', 'save', 'apply-recommended', 'test-iyuu', 'clear-iyuu',
  'probe-rules', 'refresh-rules', 'set-rule-hr', 'set-rule-hours', 'set-rule-ratio',
  'open-claim', 'open-signin', 'run-fallback', 'run-reseed', 'load-reseed', 'load-fallback',
  'add-fallback-source', 'move-fallback-source', 'remove-fallback-source', 'set-tile-shown',
  'add-sort-rule', 'remove-sort-rule', 'test-cloud',
], ["update:modelValue", "update:settingsTab", "update:fallbackSourceDraft", "update:newRuleType"]),
  setup(__props, { emit: __emit }) {

// MagicFlow · 设置弹窗（多标签）——P4 自 views/magicflow/index.vue **纯搬家**。
// props 下 / emit 上：子组件不直接改父状态；开关与设置项走 defineModel / emit。
// 复用 composable 纯函数 → module 级具名导出 import（单一真值源）。
const settingsDialog = _useModel$5(__props, "modelValue");
const settingsTab = _useModel$5(__props, 'settingsTab');
const fallbackSourceDraft = _useModel$5(__props, 'fallbackSourceDraft');
const newRuleType = _useModel$5(__props, 'newRuleType');

const emit = __emit;

// 供父组件在子渲染后取回设置导航栏 DOM（父 composable 的自动滚动依赖它）


return (_ctx, _cache) => {
  const _component_VBtn = _resolveComponent$c("VBtn");
  const _component_VIcon = _resolveComponent$c("VIcon");
  const _component_VTab = _resolveComponent$c("VTab");
  const _component_VTabs = _resolveComponent$c("VTabs");
  const _component_VDivider = _resolveComponent$c("VDivider");
  const _component_VSwitch = _resolveComponent$c("VSwitch");
  const _component_VTextField = _resolveComponent$c("VTextField");
  const _component_VSelect = _resolveComponent$c("VSelect");
  const _component_VChip = _resolveComponent$c("VChip");
  const _component_VSpacer = _resolveComponent$c("VSpacer");
  const _component_VCombobox = _resolveComponent$c("VCombobox");
  const _component_VAlert = _resolveComponent$c("VAlert");
  const _component_VCard = _resolveComponent$c("VCard");
  const _component_VDialog = _resolveComponent$c("VDialog");

  return (_openBlock$c(), _createBlock$a(_component_VDialog, {
    modelValue: settingsDialog.value,
    "onUpdate:modelValue": _cache[159] || (_cache[159] = $event => ((settingsDialog).value = $event)),
    "max-width": "40rem",
    fullscreen: __props.isNarrow
  }, {
    default: _withCtx$a(() => [
      _createVNode$b(_component_VCard, { class: "magicflow-dialog magicflow-settings-dialog" }, {
        default: _withCtx$a(() => [
          _createElementVNode$c("header", _hoisted_1$a, [
            (__props.isNarrow && __props.settingsPane === 'form')
              ? (_openBlock$c(), _createBlock$a(_component_VBtn, {
                  key: 0,
                  icon: "mdi-arrow-left",
                  size: "small",
                  variant: "text",
                  "aria-label": "返回设置目录",
                  onClick: _cache[0] || (_cache[0] = $event => (emit('back-to-dir')))
                }))
              : _createCommentVNode$a("", true),
            _createElementVNode$c("span", _hoisted_2$9, _toDisplayString$c(__props.isNarrow && __props.settingsPane === 'form' ? _unref$5(settingsTabLabel)(settingsTab.value) : '插件设置'), 1),
            _cache[160] || (_cache[160] = _createElementVNode$c("span", { class: "magicflow-scope-tag" }, "全局", -1)),
            _createVNode$b(_component_VBtn, {
              icon: "mdi-close",
              size: "small",
              variant: "text",
              "aria-label": "关闭",
              onClick: _cache[1] || (_cache[1] = $event => (settingsDialog.value = false))
            })
          ]),
          (!__props.isNarrow || __props.settingsPane === 'dir')
            ? (_openBlock$c(), _createElementBlock$a("div", {
                key: 0,
                class: "magicflow-settings-nav",
                ref: __props.setNavEl
              }, [
                (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(_unref$5(MF_SETTINGS_TABS), (t) => {
                  return (_openBlock$c(), _createElementBlock$a("button", {
                    key: t.key,
                    type: "button",
                    class: _normalizeClass$4(["magicflow-settings-nav__item", { 'is-active': settingsTab.value === t.key }]),
                    onClick: $event => (emit('open-tab', t.key))
                  }, [
                    _createVNode$b(_component_VIcon, {
                      icon: t.icon,
                      size: "18"
                    }, null, 8, ["icon"]),
                    _createElementVNode$c("span", null, _toDisplayString$c(t.label), 1)
                  ], 10, _hoisted_3$8))
                }), 128))
              ], 512))
            : _createCommentVNode$a("", true),
          _createVNode$b(_component_VTabs, {
            modelValue: settingsTab.value,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((settingsTab).value = $event)),
            class: "magicflow-settings-dialog__tabs",
            density: "comfortable",
            "show-arrows": ""
          }, {
            default: _withCtx$a(() => [
              _createVNode$b(_component_VTab, {
                value: "general",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[161] || (_cache[161] = [
                  _createTextVNode$b("常规", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "downloader",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[162] || (_cache[162] = [
                  _createTextVNode$b("下载与目录", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "template",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[163] || (_cache[163] = [
                  _createTextVNode$b("默认任务模板", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "iyuu",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[164] || (_cache[164] = [
                  _createTextVNode$b("IYUU 辅种", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "fallback",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[165] || (_cache[165] = [
                  _createTextVNode$b("元数据兜底", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "cloud",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[166] || (_cache[166] = [
                  _createTextVNode$b("云盘归档", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "exam",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[167] || (_cache[167] = [
                  _createTextVNode$b("考核", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "signin",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[168] || (_cache[168] = [
                  _createTextVNode$b("签到", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "live",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[169] || (_cache[169] = [
                  _createTextVNode$b("站点监控", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "recommend",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[170] || (_cache[170] = [
                  _createTextVNode$b("推荐", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "crossseed",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[171] || (_cache[171] = [
                  _createTextVNode$b("跨站", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "rules",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[172] || (_cache[172] = [
                  _createTextVNode$b("站点规则", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "tags",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[173] || (_cache[173] = [
                  _createTextVNode$b("标签管理", -1)
                ]))]),
                _: 1
              }),
              _createVNode$b(_component_VTab, {
                value: "notify",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx$a(() => [...(_cache[174] || (_cache[174] = [
                  _createTextVNode$b("通知", -1)
                ]))]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["modelValue"]),
          (!__props.isNarrow || __props.settingsPane === 'form')
            ? (_openBlock$c(), _createBlock$a(_component_VDivider, { key: 1 }))
            : _createCommentVNode$a("", true),
          (!__props.isNarrow || __props.settingsPane === 'form')
            ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_4$8, [
                (settingsTab.value === 'notify')
                  ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_5$8, [
                      _createVNode$b(_component_VSwitch, {
                        modelValue: __props.settingsDraft.notify_enabled,
                        "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((__props.settingsDraft.notify_enabled) = $event)),
                        label: "开启事件通知",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"]),
                      _cache[175] || (_cache[175] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                        _createTextVNode$b(" 走 MoviePilot 已配置的通知渠道（微信 / Telegram / Bark…），推四类事件： "),
                        _createElementVNode$c("strong", null, "H&R 临期"),
                        _createTextVNode$b("、"),
                        _createElementVNode$c("strong", null, "池盘触红线"),
                        _createTextVNode$b("、"),
                        _createElementVNode$c("strong", null, "时魔产出骤降"),
                        _createTextVNode$b("、"),
                        _createElementVNode$c("strong", null, "任务失败"),
                        _createTextVNode$b("。 通知只发消息，绝不自动删种或订阅。 ")
                      ], -1)),
                      _createVNode$b(_component_VTextField, {
                        modelValue: __props.settingsDraft.notify_hr_hours,
                        "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((__props.settingsDraft.notify_hr_hours) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "0",
                        step: "1",
                        label: "H&R 到期提醒提前量（小时）",
                        hint: "距达标期限到期不足该小时数就发信（默认 24）；这是通知侧的发信门槛",
                        "persistent-hint": "",
                        variant: "outlined",
                        density: "comfortable"
                      }, null, 8, ["modelValue"]),
                      _createVNode$b(_component_VTextField, {
                        modelValue: __props.settingsDraft.notify_capacity_pct,
                        "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((__props.settingsDraft.notify_capacity_pct) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "50",
                        max: "99",
                        step: "1",
                        label: "池盘告警阈值（%）",
                        hint: "池盘占用达到该百分比就提醒（默认 80）",
                        "persistent-hint": "",
                        variant: "outlined",
                        density: "comfortable"
                      }, null, 8, ["modelValue"]),
                      _createVNode$b(_component_VTextField, {
                        modelValue: __props.settingsDraft.notify_drop_pct,
                        "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((__props.settingsDraft.notify_drop_pct) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "1",
                        step: "1",
                        label: "产出骤降阈值（%）",
                        hint: "比前 3 日均值低超过该比例就提醒（默认 20%）",
                        "persistent-hint": "",
                        variant: "outlined",
                        density: "comfortable"
                      }, null, 8, ["modelValue"]),
                      _createVNode$b(_component_VSwitch, {
                        modelValue: __props.settingsDraft.notify_task_fail,
                        "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((__props.settingsDraft.notify_task_fail) = $event)),
                        label: "任务失败时通知",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"]),
                      _createVNode$b(_component_VSwitch, {
                        modelValue: __props.settingsDraft.notify_daily,
                        "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((__props.settingsDraft.notify_daily) = $event)),
                        label: "发送每日日报",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"]),
                      (__props.settingsDraft.notify_daily)
                        ? (_openBlock$c(), _createBlock$a(_component_VTextField, {
                            key: 0,
                            modelValue: __props.settingsDraft.notify_daily_hour,
                            "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((__props.settingsDraft.notify_daily_hour) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            max: "23",
                            step: "1",
                            label: "日报发送时间（小时，0-23）",
                            hint: "按本地时间，当天首次扫描时发送",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]))
                        : _createCommentVNode$a("", true),
                      _createVNode$b(_component_VTextField, {
                        modelValue: __props.settingsDraft.notify_quiet,
                        "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((__props.settingsDraft.notify_quiet) = $event)),
                        label: "免打扰时段（可空）",
                        placeholder: "23:00-08:00",
                        hint: "该时段内不发送（仍记入历史）；留空 = 不静音",
                        "persistent-hint": "",
                        variant: "outlined",
                        density: "comfortable"
                      }, null, 8, ["modelValue"])
                    ]))
                  : _createCommentVNode$a("", true),
                (settingsTab.value === 'general')
                  ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_6$7, [
                      _createVNode$b(_component_VSwitch, {
                        modelValue: __props.settingsDraft.enabled,
                        "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((__props.settingsDraft.enabled) = $event)),
                        label: "启用插件（总开关）",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"]),
                      _createVNode$b(_component_VSwitch, {
                        modelValue: __props.settingsDraft.show_sidebar_nav,
                        "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((__props.settingsDraft.show_sidebar_nav) = $event)),
                        label: "显示侧栏入口",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"]),
                      _createVNode$b(_component_VSwitch, {
                        modelValue: __props.settingsDraft.agent_mcp,
                        "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((__props.settingsDraft.agent_mcp) = $event)),
                        label: "把魔流能力注册进 MoviePilot Agent / MCP",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"]),
                      (__props.settingsDraft.agent_mcp)
                        ? (_openBlock$c(), _createBlock$a(_component_VSelect, {
                            key: 0,
                            modelValue: __props.settingsDraft.agent_mcp_scope,
                            "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((__props.settingsDraft.agent_mcp_scope) = $event)),
                            items: _unref$5(agentToolScopeItems),
                            "item-title": "title",
                            "item-value": "value",
                            label: "注册范围",
                            "hide-details": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue", "items"]))
                        : _createCommentVNode$a("", true),
                      (__props.settingsDraft.agent_mcp)
                        ? (_openBlock$c(), _createElementBlock$a("p", _hoisted_7$6, [...(_cache[176] || (_cache[176] = [
                            _createTextVNode$b(" 注册后，MoviePilot 的 AI 助手 / MCP 客户端（Claude、Cherry Studio 等）可直接调用魔流：", -1),
                            _createElementVNode$c("strong", null, "常用工具", -1),
                            _createTextVNode$b(" 52 个高频接口（任务 / 站点做种 / H&R / 补源 / 点播 / 库内资源 / 推荐 / 队列…），", -1),
                            _createElementVNode$c("strong", null, "全部端点", -1),
                            _createTextVNode$b(" 76 个（含冷门排障接口）。写操作也一并注册，请只接可信的 AI 客户端。 ", -1)
                          ]))]))
                        : _createCommentVNode$a("", true),
                      _createVNode$b(_component_VTextField, {
                        modelValue: __props.settingsDraft.request_interval,
                        "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((__props.settingsDraft.request_interval) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "0",
                        step: "0.5",
                        label: "站点请求间隔（秒）",
                        hint: "站点翻页之间的最小间隔，0＝不限；强流控站可加大",
                        "persistent-hint": "",
                        variant: "outlined",
                        density: "comfortable"
                      }, null, 8, ["modelValue"]),
                      _createVNode$b(_component_VTextField, {
                        modelValue: __props.settingsDraft.journal_keep,
                        "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((__props.settingsDraft.journal_keep) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "0",
                        label: "操作记录保留上限",
                        hint: "每个任务最多保留的操作记录条数，0 = 不限",
                        "persistent-hint": "",
                        variant: "outlined",
                        density: "comfortable"
                      }, null, 8, ["modelValue"]),
                      _cache[181] || (_cache[181] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                        _createTextVNode$b(" 任务流量：按「在跑的任务类型」自动设 qB "),
                        _createElementVNode$c("strong", null, "全局上传限速"),
                        _createTextVNode$b("（只限上传，不动下载）。有刷流任务时用刷流档，只有魔力任务时用魔力档；两者同时在跑取刷流档；一个启用的任务都没有则清除限速。 ")
                      ], -1)),
                      _createElementVNode$c("div", _hoisted_8$6, [
                        _createVNode$b(_component_VTextField, {
                          modelValue: __props.settingsDraft.bonus_upload_limit_kbps,
                          "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((__props.settingsDraft.bonus_upload_limit_kbps) = $event)),
                          modelModifiers: { number: true },
                          type: "number",
                          min: "0",
                          step: "10",
                          label: "魔力任务上传限速（KB/s）",
                          hint: "仅有魔力任务在跑时生效，0 = 不限",
                          "persistent-hint": "",
                          variant: "outlined",
                          density: "comfortable"
                        }, null, 8, ["modelValue"]),
                        _createVNode$b(_component_VTextField, {
                          modelValue: __props.settingsDraft.brush_upload_limit_kbps,
                          "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((__props.settingsDraft.brush_upload_limit_kbps) = $event)),
                          modelModifiers: { number: true },
                          type: "number",
                          min: "0",
                          step: "10",
                          label: "刷流任务上传限速（KB/s）",
                          hint: "有刷流任务在跑时生效（优先），0 = 不限",
                          "persistent-hint": "",
                          variant: "outlined",
                          density: "comfortable"
                        }, null, 8, ["modelValue"]),
                        _createVNode$b(_component_VTextField, {
                          modelValue: __props.settingsDraft.seed_up_limit_kbps,
                          "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((__props.settingsDraft.seed_up_limit_kbps) = $event)),
                          modelModifiers: { number: true },
                          type: "number",
                          min: "0",
                          step: "50",
                          label: "挂种单种上传限速（KB/s）",
                          hint: "管控中的种单种限速，默认 200；0＝不限；不管控的不限速",
                          "persistent-hint": "",
                          variant: "outlined",
                          density: "comfortable"
                        }, null, 8, ["modelValue"]),
                        _createVNode$b(_component_VTextField, {
                          modelValue: __props.settingsDraft.brush_seed_up_limit_kbps,
                          "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((__props.settingsDraft.brush_seed_up_limit_kbps) = $event)),
                          modelModifiers: { number: true },
                          type: "number",
                          min: "0",
                          step: "256",
                          label: "刷流单种上传限速（KB/s）",
                          hint: "我们管控的刷流种：要冲量，默认 5120（=5 MB/s）；0 = 不限",
                          "persistent-hint": "",
                          variant: "outlined",
                          density: "comfortable"
                        }, null, 8, ["modelValue"])
                      ]),
                      _createVNode$b(_component_VSwitch, {
                        modelValue: __props.settingsDraft.debug_log,
                        "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((__props.settingsDraft.debug_log) = $event)),
                        label: "调试日志",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"]),
                      _createVNode$b(_component_VSwitch, {
                        modelValue: __props.settingsDraft.compact_mode,
                        "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((__props.settingsDraft.compact_mode) = $event)),
                        label: "紧凑模式",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"]),
                      _createElementVNode$c("div", _hoisted_9$6, [
                        _createElementVNode$c("div", _hoisted_10$6, [
                          _createVNode$b(_component_VIcon, {
                            icon: "mdi-view-grid-outline",
                            size: "16"
                          }),
                          _cache[177] || (_cache[177] = _createTextVNode$b(" 顶栏功能磁贴", -1))
                        ]),
                        _cache[178] || (_cache[178] = _createElementVNode$c("p", { class: "magicflow-field__sub" }, [
                          _createTextVNode$b(" 关掉的磁贴不再在顶栏 / 手机「功能」里显示入口。"),
                          _createElementVNode$c("strong", null, "只影响入口显示"),
                          _createTextVNode$b("： 功能本身在各自的设置页里单独开关，这里不动任何功能逻辑。 ")
                        ], -1)),
                        _createElementVNode$c("div", _hoisted_11$6, [
                          (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(_unref$5(TILE_OPTIONS), (t) => {
                            return (_openBlock$c(), _createBlock$a(_component_VSwitch, {
                              key: t.key,
                              "model-value": __props.tileShown(t.key),
                              label: t.label,
                              "prepend-icon": t.icon,
                              color: "primary",
                              "hide-details": "",
                              inset: "",
                              density: "comfortable",
                              "onUpdate:modelValue": v => emit('set-tile-shown', t.key, v)
                            }, null, 8, ["model-value", "label", "prepend-icon", "onUpdate:modelValue"]))
                          }), 128))
                        ]),
                        _createElementVNode$c("p", _hoisted_12$6, " 已显示 " + _toDisplayString$c(_unref$5(TILE_OPTIONS).filter(t => __props.tileShown(t.key)).length) + " / " + _toDisplayString$c(_unref$5(TILE_OPTIONS).length), 1)
                      ]),
                      _createElementVNode$c("div", _hoisted_13$5, [
                        _createElementVNode$c("div", _hoisted_14$5, [
                          _createVNode$b(_component_VIcon, {
                            icon: "mdi-lifebuoy",
                            size: "16"
                          }),
                          _cache[179] || (_cache[179] = _createTextVNode$b(" 死种补源（rescue）", -1))
                        ]),
                        _cache[180] || (_cache[180] = _createElementVNode$c("p", { class: "magicflow-field__sub" }, [
                          _createTextVNode$b(" 未下完 + 长时间 0 速，且"),
                          _createElementVNode$c("strong", null, "欠 H&R 或手动保留"),
                          _createTextVNode$b("的种 → 去"),
                          _createElementVNode$c("strong", null, "无 H&R 的他站"),
                          _createTextVNode$b("下同一 Release 补齐（补完 recheck 认文件）。 独立页面在顶栏「补源」按钮，这里只调参数。 ")
                        ], -1)),
                        _createElementVNode$c("div", _hoisted_15$5, [
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.settingsDraft.rescue_stall_hours,
                            "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((__props.settingsDraft.rescue_stall_hours) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            max: "720",
                            step: "1",
                            label: "停滞阈值（小时）",
                            hint: "0 速持续超过该时长才纳入补源（默认 6，越小越灵敏）",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.settingsDraft.rescue_max_candidates,
                            "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((__props.settingsDraft.rescue_max_candidates) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "1",
                            max: "10",
                            step: "1",
                            label: "每目标候选数",
                            hint: "只列无 H&R 站的同 Release 候选（默认 3）",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"])
                        ])
                      ])
                    ]))
                  : (settingsTab.value === 'downloader')
                    ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_16$5, [
                        _cache[182] || (_cache[182] = _createElementVNode$c("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, " 以下为 qBittorrent 全局参数，将直接写入下载器，会影响所有使用该下载器的插件。 ", -1)),
                        _createElementVNode$c("div", _hoisted_17$5, [
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.downloaderPrefsDraft.download_limit_kbps,
                            "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((__props.downloaderPrefsDraft.download_limit_kbps) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            label: "最大下载速度",
                            suffix: "KB/s",
                            hint: "0 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.downloaderPrefsDraft.upload_limit_kbps,
                            "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((__props.downloaderPrefsDraft.upload_limit_kbps) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            label: "最大上传速度",
                            suffix: "KB/s",
                            hint: "0 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.downloaderPrefsDraft.max_connec,
                            "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((__props.downloaderPrefsDraft.max_connec) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            label: "最大连接数",
                            variant: "outlined",
                            density: "comfortable",
                            "hide-details": ""
                          }, null, 8, ["modelValue"]),
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.downloaderPrefsDraft.max_connec_per_torrent,
                            "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((__props.downloaderPrefsDraft.max_connec_per_torrent) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            label: "每种子连接数",
                            variant: "outlined",
                            density: "comfortable",
                            "hide-details": ""
                          }, null, 8, ["modelValue"]),
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.downloaderPrefsDraft.max_uploads,
                            "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((__props.downloaderPrefsDraft.max_uploads) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "-1",
                            label: "最大上传连接数",
                            hint: "-1 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.downloaderPrefsDraft.max_uploads_per_torrent,
                            "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((__props.downloaderPrefsDraft.max_uploads_per_torrent) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "-1",
                            label: "每种子上传连接数",
                            hint: "-1 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.downloaderPrefsDraft.max_active_downloads,
                            "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((__props.downloaderPrefsDraft.max_active_downloads) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "-1",
                            label: "最大活动下载数",
                            hint: "排队不计入；-1 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode$b(_component_VTextField, {
                            modelValue: __props.downloaderPrefsDraft.max_active_torrents,
                            "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((__props.downloaderPrefsDraft.max_active_torrents) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "-1",
                            label: "最大活动种子数",
                            hint: "-1 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"])
                        ]),
                        _createVNode$b(_component_VSwitch, {
                          modelValue: __props.downloaderPrefsDraft.queueing_enabled,
                          "onUpdate:modelValue": _cache[33] || (_cache[33] = $event => ((__props.downloaderPrefsDraft.queueing_enabled) = $event)),
                          label: "启用队列限制（活动数上限生效的前提）",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8, ["modelValue"]),
                        _createVNode$b(_component_VDivider, { class: "my-3" }),
                        _cache[183] || (_cache[183] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, " qBittorrent 全局目录，写入后影响所有使用该下载器的插件。 ", -1)),
                        _createVNode$b(_component_VTextField, {
                          modelValue: __props.downloaderPathsDraft.save_path,
                          "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((__props.downloaderPathsDraft.save_path) = $event)),
                          label: "默认保存路径",
                          placeholder: "如 /vol3/1000/media",
                          variant: "outlined",
                          density: "comfortable",
                          "hide-details": ""
                        }, null, 8, ["modelValue"]),
                        _createVNode$b(_component_VTextField, {
                          modelValue: __props.downloaderPathsDraft.temp_path,
                          "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((__props.downloaderPathsDraft.temp_path) = $event)),
                          label: "临时下载路径",
                          placeholder: "下载中暂存目录",
                          variant: "outlined",
                          density: "comfortable",
                          "hide-details": ""
                        }, null, 8, ["modelValue"]),
                        _createVNode$b(_component_VSwitch, {
                          modelValue: __props.downloaderPathsDraft.temp_path_enabled,
                          "onUpdate:modelValue": _cache[36] || (_cache[36] = $event => ((__props.downloaderPathsDraft.temp_path_enabled) = $event)),
                          label: "启用临时下载路径（下载中放临时目录，完成后移入保存路径）",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8, ["modelValue"]),
                        _createVNode$b(_component_VDivider, { class: "my-2" }),
                        _cache[184] || (_cache[184] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, " 任务保存目录：仅对魔流生效，不影响下载器全局设置。 ", -1)),
                        _createVNode$b(_component_VTextField, {
                          modelValue: __props.defaultsDraft.save_path,
                          "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((__props.defaultsDraft.save_path) = $event)),
                          label: "任务保存目录",
                          placeholder: "如 /vol3/1000/media/magicflow",
                          hint: "新建任务时预填此目录（不改已有任务）",
                          "persistent-hint": "",
                          variant: "outlined",
                          density: "comfortable"
                        }, null, 8, ["modelValue"])
                      ]))
                    : (settingsTab.value === 'iyuu')
                      ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_18$5, [
                          _cache[191] || (_cache[191] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                            _createTextVNode$b(" IYUU 云端辅种为"),
                            _createElementVNode$c("strong", null, "可选增强"),
                            _createTextVNode$b("：填 Token 后，复用/刷流优先用 IYUU 云端匹配"),
                            _createElementVNode$c("strong", null, "他站同资源"),
                            _createTextVNode$b("； 下方站点密钥可手填（留空则自动用 MoviePilot 已存的 apikey / cookie 取链）。 "),
                            _createElementVNode$c("strong", null, "不填 Token 则完全不启用"),
                            _createTextVNode$b("，照旧走内置跨站特征码方案。 ")
                          ], -1)),
                          _createElementVNode$c("div", _hoisted_19$5, [
                            _createVNode$b(_component_VTextField, {
                              modelValue: __props.settingsDraft.iyuu_token,
                              "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((__props.settingsDraft.iyuu_token) = $event)),
                              label: "IYUU 云端 Token",
                              placeholder: __props.iyuuStatus?.token_set ? '已保存（留空则不修改）' : '留空 = 不启用 IYUU 辅种',
                              variant: "outlined",
                              density: "comfortable",
                              "hide-details": "",
                              autocomplete: "off"
                            }, null, 8, ["modelValue", "placeholder"]),
                            _createVNode$b(_component_VBtn, {
                              variant: "tonal",
                              color: "primary",
                              size: "small",
                              "prepend-icon": "mdi-connection",
                              loading: __props.iyuuTesting,
                              disabled: !__props.settingsDraft.iyuu_token && !__props.iyuuStatus?.token_set,
                              onClick: _cache[39] || (_cache[39] = $event => (emit('test-iyuu')))
                            }, {
                              default: _withCtx$a(() => [...(_cache[185] || (_cache[185] = [
                                _createTextVNode$b("测试", -1)
                              ]))]),
                              _: 1
                            }, 8, ["loading", "disabled"]),
                            (__props.settingsDraft.iyuu_token || __props.iyuuStatus?.token_set)
                              ? (_openBlock$c(), _createBlock$a(_component_VBtn, {
                                  key: 0,
                                  variant: "text",
                                  color: "error",
                                  size: "small",
                                  "prepend-icon": "mdi-close-circle-outline",
                                  onClick: _cache[40] || (_cache[40] = $event => (emit('clear-iyuu')))
                                }, {
                                  default: _withCtx$a(() => [...(_cache[186] || (_cache[186] = [
                                    _createTextVNode$b("清空", -1)
                                  ]))]),
                                  _: 1
                                }))
                              : _createCommentVNode$a("", true)
                          ]),
                          _createElementVNode$c("div", _hoisted_20$5, [
                            _createElementVNode$c("div", _hoisted_21$4, [
                              _cache[187] || (_cache[187] = _createElementVNode$c("span", null, "站点密钥（按 MoviePilot 已配置站点生成）", -1)),
                              (__props.iyuuStatus)
                                ? (_openBlock$c(), _createBlock$a(_component_VChip, {
                                    key: 0,
                                    size: "x-small",
                                    variant: "tonal",
                                    color: __props.iyuuStatus.enabled ? 'success' : 'grey'
                                  }, {
                                    default: _withCtx$a(() => [
                                      _createTextVNode$b(_toDisplayString$c(__props.iyuuStatus.enabled ? '已启用' : '未启用'), 1)
                                    ]),
                                    _: 1
                                  }, 8, ["color"]))
                                : _createCommentVNode$a("", true)
                            ]),
                            (__props.iyuuLoading)
                              ? (_openBlock$c(), _createElementBlock$a("p", _hoisted_22$3, "加载中…"))
                              : (!__props.iyuuSites.length)
                                ? (_openBlock$c(), _createElementBlock$a("p", _hoisted_23$2, " 未检测到已配置站点（请先在 MoviePilot 中添加站点）。 "))
                                : _createCommentVNode$a("", true),
                            (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(__props.iyuuSites, (row) => {
                              return (_openBlock$c(), _createElementBlock$a("div", {
                                key: row.domain || row.name,
                                class: "magicflow-iyuu-row"
                              }, [
                                _createElementVNode$c("div", _hoisted_24$2, [
                                  _createElementVNode$c("span", _hoisted_25$2, _toDisplayString$c(row.name), 1),
                                  (row.iyuu_sid)
                                    ? (_openBlock$c(), _createBlock$a(_component_VChip, {
                                        key: 0,
                                        size: "x-small",
                                        variant: "tonal"
                                      }, {
                                        default: _withCtx$a(() => [
                                          _createTextVNode$b("IYUU #" + _toDisplayString$c(row.iyuu_sid), 1)
                                        ]),
                                        _: 2
                                      }, 1024))
                                    : _createCommentVNode$a("", true),
                                  (row.has_apikey)
                                    ? (_openBlock$c(), _createBlock$a(_component_VChip, {
                                        key: 1,
                                        size: "x-small",
                                        variant: "tonal",
                                        color: "success"
                                      }, {
                                        default: _withCtx$a(() => [...(_cache[188] || (_cache[188] = [
                                          _createTextVNode$b("API", -1)
                                        ]))]),
                                        _: 1
                                      }))
                                    : _createCommentVNode$a("", true),
                                  (row.has_cookie)
                                    ? (_openBlock$c(), _createBlock$a(_component_VChip, {
                                        key: 2,
                                        size: "x-small",
                                        variant: "tonal",
                                        color: "info"
                                      }, {
                                        default: _withCtx$a(() => [...(_cache[189] || (_cache[189] = [
                                          _createTextVNode$b("Cookie", -1)
                                        ]))]),
                                        _: 1
                                      }))
                                    : _createCommentVNode$a("", true),
                                  _createVNode$b(_component_VSpacer),
                                  _createVNode$b(_component_VBtn, {
                                    size: "x-small",
                                    variant: "text",
                                    "append-icon": __props.iyuuShowMore[row.domain || row.name] ? 'mdi-chevron-up' : 'mdi-chevron-down',
                                    onClick: $event => (__props.iyuuShowMore[row.domain || row.name] = !__props.iyuuShowMore[row.domain || row.name])
                                  }, {
                                    default: _withCtx$a(() => [
                                      _createTextVNode$b(_toDisplayString$c(__props.iyuuShowMore[row.domain || row.name] ? '收起' : '更多'), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["append-icon", "onClick"])
                                ]),
                                _createElementVNode$c("div", _hoisted_26$2, [
                                  _cache[190] || (_cache[190] = _createElementVNode$c("div", {
                                    class: "text-caption text-medium-emphasis",
                                    style: {"grid-column":"1 / -1"}
                                  }, " passkey 统一在「RSS / 凭据」里填写（这里不再重复） ", -1)),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: row.uid,
                                    "onUpdate:modelValue": $event => ((row.uid) = $event),
                                    label: "uid（可选）",
                                    placeholder: row.uid_set ? '已保存（留空则不修改）' : '留空 = 自动获取',
                                    variant: "outlined",
                                    density: "compact",
                                    "hide-details": "",
                                    autocomplete: "off"
                                  }, null, 8, ["modelValue", "onUpdate:modelValue", "placeholder"])
                                ]),
                                (__props.iyuuShowMore[row.domain || row.name])
                                  ? (_openBlock$c(), _createBlock$a(_component_VTextField, {
                                      key: 0,
                                      modelValue: row.downhash,
                                      "onUpdate:modelValue": $event => ((row.downhash) = $event),
                                      label: "downhash（可选）",
                                      placeholder: row.downhash_set ? '已保存（留空则不修改）' : '留空 = 自动获取',
                                      variant: "outlined",
                                      density: "compact",
                                      "hide-details": "",
                                      autocomplete: "off"
                                    }, null, 8, ["modelValue", "onUpdate:modelValue", "placeholder"]))
                                  : _createCommentVNode$a("", true)
                              ]))
                            }), 128))
                          ])
                        ]))
                      : (settingsTab.value === 'reseed')
                        ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_27$2, [
                            _cache[201] || (_cache[201] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                              _createElementVNode$c("strong", null, "全站辅种"),
                              _createTextVNode$b("（本机驱动）：本机"),
                              _createElementVNode$c("strong", null, "已有文件"),
                              _createTextVNode$b("的资源 → 去各站找"),
                              _createElementVNode$c("strong", null, "同一 Release"),
                              _createTextVNode$b(" 的种子挂上去落户。 "),
                              _createElementVNode$c("strong", null, "零下载"),
                              _createTextVNode$b("：暂停加入 → recheck 校验 → "),
                              _createElementVNode$c("strong", null, "通过才做种"),
                              _createTextVNode$b("，不通过自动撤销。 方向与「跨站取种」相反（那是本机没有、去他站免费下回来）。 "),
                              _createElementVNode$c("br"),
                              _createTextVNode$b(" 候选有两条来源：① "),
                              _createElementVNode$c("strong", null, "IYUU 云端反查"),
                              _createTextVNode$b("（覆盖 IYUU 收录的站，免费、无请求开销）； ② "),
                              _createElementVNode$c("strong", null, "直连搜索"),
                              _createTextVNode$b("（覆盖没有 IYUU 编号的站：自己按片名搜 → 体积粗筛 → 特征码比对）。 ")
                            ], -1)),
                            _cache[202] || (_cache[202] = _createElementVNode$c("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, [
                              _createTextVNode$b(" ⚠️ 挂种要拼目标站下载链（IYUU 站点表模板 + passkey / API 直链）。passkey 能自动抓；抓不到的站会记「缺料」跳过。 每站有每日上限，建议先"),
                              _createElementVNode$c("strong", null, "干跑"),
                              _createTextVNode$b("看清能挂多少再关干跑。 ")
                            ], -1)),
                            _createElementVNode$c("div", _hoisted_28$2, [
                              _createVNode$b(_component_VSwitch, {
                                modelValue: __props.settingsDraft.reseed_enabled,
                                "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((__props.settingsDraft.reseed_enabled) = $event)),
                                label: "启用全站辅种",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$b(_component_VSwitch, {
                                modelValue: __props.settingsDraft.reseed_dry,
                                "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((__props.settingsDraft.reseed_dry) = $event)),
                                label: "干跑（只算不挂）",
                                color: "primary",
                                "hide-details": "",
                                inset: "",
                                disabled: !__props.settingsDraft.reseed_enabled
                              }, null, 8, ["modelValue", "disabled"])
                            ]),
                            _createElementVNode$c("div", _hoisted_29$2, [
                              _createElementVNode$c("div", _hoisted_30$2, [
                                _createVNode$b(_component_VIcon, {
                                  icon: "mdi-web",
                                  size: "16"
                                }),
                                _cache[192] || (_cache[192] = _createTextVNode$b(" 目标站点（留空 = 全部有 IYUU 编号的站）", -1))
                              ]),
                              _createVNode$b(_component_VSelect, {
                                modelValue: __props.settingsDraft.reseed_sites,
                                "onUpdate:modelValue": _cache[43] || (_cache[43] = $event => ((__props.settingsDraft.reseed_sites) = $event)),
                                items: __props.reseedSiteOptions,
                                label: "铺设站点",
                                multiple: "",
                                chips: "",
                                "closable-chips": "",
                                variant: "outlined",
                                density: "comfortable",
                                "hide-details": ""
                              }, null, 8, ["modelValue", "items"]),
                              _createElementVNode$c("span", _hoisted_31$2, "已选 " + _toDisplayString$c((__props.settingsDraft.reseed_sites || []).length) + " 个 · 只列有 IYUU 编号的站；没有编号的站用下面「直连搜索站」", 1)
                            ]),
                            _createElementVNode$c("div", _hoisted_32$2, [
                              _createElementVNode$c("div", _hoisted_33$2, [
                                _createVNode$b(_component_VIcon, {
                                  icon: "mdi-magnify-scan",
                                  size: "16"
                                }),
                                _cache[193] || (_cache[193] = _createTextVNode$b(" 直连搜索站（IYUU 不收录的站）", -1))
                              ]),
                              _createVNode$b(_component_VSelect, {
                                modelValue: __props.settingsDraft.reseed_search_sites,
                                "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((__props.settingsDraft.reseed_search_sites) = $event)),
                                items: (__props.reseedState?.config?.search_options || []).map((o) => ({ title: `${o.name}（${o.domain}）`, value: o.domain })),
                                label: "自己搜的站",
                                multiple: "",
                                chips: "",
                                "closable-chips": "",
                                variant: "outlined",
                                density: "comfortable",
                                "hide-details": ""
                              }, null, 8, ["modelValue", "items"]),
                              _cache[194] || (_cache[194] = _createElementVNode$c("span", { class: "magicflow-field__sub" }, [
                                _createTextVNode$b(" 这些站没有 IYUU 编号，走"),
                                _createElementVNode$c("strong", null, "组名 → 站点搜索 → 特征码比对"),
                                _createTextVNode$b("自己找同一颗种子（找到才挂，对不上不挂）。 未选 = 不启用（每轮要花真实站点请求，不会装上就偷偷跑）。 ")
                              ], -1)),
                              (!(__props.reseedState?.config?.search_options || []).length)
                                ? (_openBlock$c(), _createElementBlock$a("span", _hoisted_34$2, " 当前没有可直连搜索的站（需要先在 MoviePilot 里配好站点，且该站有解析预设）。 "))
                                : _createCommentVNode$a("", true)
                            ]),
                            _createElementVNode$c("div", _hoisted_35$2, [
                              _createElementVNode$c("div", _hoisted_36$2, [
                                _createVNode$b(_component_VIcon, {
                                  icon: "mdi-tune",
                                  size: "16"
                                }),
                                _cache[195] || (_cache[195] = _createTextVNode$b(" 限量", -1))
                              ]),
                              _createElementVNode$c("div", _hoisted_37$2, [
                                _createVNode$b(_component_VTextField, {
                                  modelValue: __props.settingsDraft.reseed_daily_per_site,
                                  "onUpdate:modelValue": _cache[45] || (_cache[45] = $event => ((__props.settingsDraft.reseed_daily_per_site) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  label: "每站每天挂种上限",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode$b(_component_VTextField, {
                                  modelValue: __props.settingsDraft.reseed_batch,
                                  "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((__props.settingsDraft.reseed_batch) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  label: "每轮最多处理（对）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode$b(_component_VTextField, {
                                  modelValue: __props.settingsDraft.reseed_min_size_gb,
                                  "onUpdate:modelValue": _cache[47] || (_cache[47] = $event => ((__props.settingsDraft.reseed_min_size_gb) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  label: "最小体积 GB",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode$b(_component_VTextField, {
                                  modelValue: __props.settingsDraft.reseed_search_kw,
                                  "onUpdate:modelValue": _cache[48] || (_cache[48] = $event => ((__props.settingsDraft.reseed_search_kw) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  label: "每轮搜索词数（0=站点预设）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"])
                              ]),
                              _cache[196] || (_cache[196] = _createElementVNode$c("span", { class: "magicflow-field__sub" }, [
                                _createTextVNode$b(" 搜索词是"),
                                _createElementVNode$c("strong", null, "长期增量"),
                                _createTextVNode$b("口径：搜过的资源组进台账（没货锁 30 天 / 出错锁 1 天），下一轮只搜新进来的，不会每轮把同样几部片重搜一遍。 ")
                              ], -1))
                            ]),
                            _createElementVNode$c("div", _hoisted_38$2, [
                              _createElementVNode$c("div", _hoisted_39$2, [
                                _createVNode$b(_component_VIcon, {
                                  icon: "mdi-content-duplicate",
                                  size: "16"
                                }),
                                _cache[198] || (_cache[198] = _createTextVNode$b(" 运行 / 状态 ", -1)),
                                _createVNode$b(_component_VSpacer),
                                _createVNode$b(_component_VBtn, {
                                  size: "small",
                                  variant: "text",
                                  "prepend-icon": "mdi-refresh",
                                  class: "me-2",
                                  onClick: _cache[49] || (_cache[49] = $event => (emit('load-reseed')))
                                }, {
                                  default: _withCtx$a(() => [...(_cache[197] || (_cache[197] = [
                                    _createTextVNode$b("刷新", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _createVNode$b(_component_VBtn, {
                                  size: "small",
                                  color: "primary",
                                  variant: "tonal",
                                  "prepend-icon": "mdi-play",
                                  loading: __props.reseedRunning,
                                  onClick: _cache[50] || (_cache[50] = $event => (emit('run-reseed')))
                                }, {
                                  default: _withCtx$a(() => [
                                    _createTextVNode$b(_toDisplayString$c(__props.settingsDraft.reseed_dry ? '立即干跑一轮' : '立即跑一轮'), 1)
                                  ]),
                                  _: 1
                                }, 8, ["loading"])
                              ]),
                              (__props.reseedState)
                                ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_40$2, [
                                    _createElementVNode$c("div", _hoisted_41$2, [
                                      _createVNode$b(_component_VChip, {
                                        size: "small",
                                        variant: "tonal",
                                        color: __props.reseedState.enabled ? 'success' : 'grey'
                                      }, {
                                        default: _withCtx$a(() => [
                                          _createTextVNode$b(_toDisplayString$c(__props.reseedState.enabled ? '已启用' : '未启用'), 1)
                                        ]),
                                        _: 1
                                      }, 8, ["color"]),
                                      _createVNode$b(_component_VChip, {
                                        size: "small",
                                        variant: "tonal",
                                        color: __props.reseedState.dry ? 'warning' : 'grey'
                                      }, {
                                        default: _withCtx$a(() => [
                                          _createTextVNode$b(_toDisplayString$c(__props.reseedState.dry ? '干跑' : '实挂'), 1)
                                        ]),
                                        _: 1
                                      }, 8, ["color"]),
                                      (__props.reseedState.running)
                                        ? (_openBlock$c(), _createBlock$a(_component_VChip, {
                                            key: 0,
                                            size: "small",
                                            variant: "tonal",
                                            color: "info"
                                          }, {
                                            default: _withCtx$a(() => [...(_cache[199] || (_cache[199] = [
                                              _createTextVNode$b("运行中…", -1)
                                            ]))]),
                                            _: 1
                                          }))
                                        : _createCommentVNode$a("", true),
                                      _createElementVNode$c("span", _hoisted_42$2, "IYUU 云端 " + _toDisplayString$c(__props.reseedState.debug?.token ? '✓' : '✗') + " · 云端站点表 " + _toDisplayString$c(__props.reseedState.debug?.iyuu_sites ?? 0) + " · 可辅站 " + _toDisplayString$c(__props.reseedState.debug?.mapped ?? 0) + " · 直连搜索站 " + _toDisplayString$c(__props.reseedState.debug?.direct_sites ?? 0), 1)
                                    ]),
                                    _createElementVNode$c("div", _hoisted_43$1, [
                                      _createElementVNode$c("span", _hoisted_44$1, "本机上报 " + _toDisplayString$c(__props.reseedState.cloud?.hashes ?? 0) + " 颗 · IYUU 云端命中候选 " + _toDisplayString$c(__props.reseedState.cloud?.candidates ?? 0) + " 对", 1)
                                    ]),
                                    (__props.reseedState.last && __props.reseedState.last.at)
                                      ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_45$1, [
                                          _createElementVNode$c("span", _hoisted_46$1, " 上轮 " + _toDisplayString$c(_unref$5(fmtTs)(__props.reseedState.last.at)) + "：计划 " + _toDisplayString$c(__props.reseedState.last.plan ?? 0) + " · 挂上 " + _toDisplayString$c(__props.reseedState.last.ok ?? 0) + " · 已有 " + _toDisplayString$c(__props.reseedState.last.have ?? 0) + " · 不一致 " + _toDisplayString$c(__props.reseedState.last.mismatch ?? 0) + " · 缺链 " + _toDisplayString$c(__props.reseedState.last.nourl ?? 0) + " · 缺 PV " + _toDisplayString$c(__props.reseedState.last.pv ?? 0) + " · 失败 " + _toDisplayString$c(__props.reseedState.last.fail ?? 0) + " · 干跑可挂 " + _toDisplayString$c(__props.reseedState.last.would ?? 0) + "（" + _toDisplayString$c(__props.reseedState.last.duration ?? 0) + "s） ", 1)
                                        ]))
                                      : _createCommentVNode$a("", true),
                                    (__props.reseedState.last && __props.reseedState.last.search_kw)
                                      ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_47$1, [
                                          _createElementVNode$c("span", _hoisted_48$1, [
                                            _createTextVNode$b(" 上轮直连搜索 " + _toDisplayString$c(__props.reseedState.last.search_kw) + " 词 → 命中 " + _toDisplayString$c(__props.reseedState.last.search_hit ?? 0) + " · 无此片 " + _toDisplayString$c(__props.reseedState.last.search_nomatch ?? 0) + " · 体积不符 " + _toDisplayString$c(__props.reseedState.last.search_size_miss ?? 0) + " · 特征码不符 " + _toDisplayString$c(__props.reseedState.last.search_fp_miss ?? 0), 1),
                                            (__props.reseedState.last.search_dead)
                                              ? (_openBlock$c(), _createElementBlock$a(_Fragment$a, { key: 0 }, [
                                                  _createTextVNode$b(" · 会话失效 " + _toDisplayString$c(__props.reseedState.last.search_dead), 1)
                                                ], 64))
                                              : _createCommentVNode$a("", true),
                                            (__props.reseedState.last.search_flow)
                                              ? (_openBlock$c(), _createElementBlock$a(_Fragment$a, { key: 1 }, [
                                                  _createTextVNode$b(" · 流控 " + _toDisplayString$c(__props.reseedState.last.search_flow), 1)
                                                ], 64))
                                              : _createCommentVNode$a("", true)
                                          ])
                                        ]))
                                      : _createCommentVNode$a("", true),
                                    _createElementVNode$c("div", _hoisted_49$1, [
                                      _cache[200] || (_cache[200] = _createElementVNode$c("div", { class: "magicflow-reseedpanel__head" }, [
                                        _createElementVNode$c("span", null, "站点"),
                                        _createElementVNode$c("span", null, "IYUU"),
                                        _createElementVNode$c("span", null, "passkey"),
                                        _createElementVNode$c("span", null, "今日 / 上限")
                                      ], -1)),
                                      (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8((__props.reseedState.sites || []), (s) => {
                                        return (_openBlock$c(), _createElementBlock$a("div", {
                                          key: s.sid,
                                          class: "magicflow-reseedpanel__line"
                                        }, [
                                          _createElementVNode$c("span", null, [
                                            _createTextVNode$b(_toDisplayString$c(s.name), 1),
                                            (s.domain)
                                              ? (_openBlock$c(), _createElementBlock$a("em", _hoisted_50$1, " · " + _toDisplayString$c(s.domain), 1))
                                              : _createCommentVNode$a("", true)
                                          ]),
                                          _createElementVNode$c("span", null, "#" + _toDisplayString$c(s.sid), 1),
                                          _createElementVNode$c("span", null, _toDisplayString$c(s.passkey_ok ? '✓' : '—'), 1),
                                          _createElementVNode$c("span", null, _toDisplayString$c(s.done_today) + " / " + _toDisplayString$c(s.cap), 1)
                                        ]))
                                      }), 128)),
                                      (!(__props.reseedState.sites || []).length)
                                        ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_51$1, "没有可辅种的站点（与 IYUU 站点表对不上）"))
                                        : _createCommentVNode$a("", true)
                                    ]),
                                    _createElementVNode$c("div", _hoisted_52$1, [
                                      _createElementVNode$c("span", _hoisted_53$1, "账本：" + _toDisplayString$c(Object.entries(__props.reseedState.ledger || {}).map((pair) => `${pair[0]} ${pair[1]}`).join(' · ') || '空（还没跑过）'), 1)
                                    ])
                                  ]))
                                : (_openBlock$c(), _createElementBlock$a("p", _hoisted_54$1, "加载中…"))
                            ])
                          ]))
                        : (settingsTab.value === 'claim')
                          ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_55$1, [
                              _cache[209] || (_cache[209] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                _createElementVNode$c("strong", null, "认领"),
                                _createTextVNode$b("：把「我们正在做种」的种子在"),
                                _createElementVNode$c("strong", null, "站点侧认领"),
                                _createTextVNode$b("掉，换取站点给的权益 （CARPT：达标种子魔力奖励 = 正常值 "),
                                _createElementVNode$c("strong", null, "×2"),
                                _createTextVNode$b("）。它是「保种增值」动作，与刷流拿种解耦。 ")
                              ], -1)),
                              _cache[210] || (_cache[210] = _createElementVNode$c("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, [
                                _createTextVNode$b(" ⚠️ 认领是"),
                                _createElementVNode$c("strong", null, "不可逆的对外写操作"),
                                _createTextVNode$b("：站点侧不达标会"),
                                _createElementVNode$c("strong", null, "扣魔力"),
                                _createTextVNode$b("，主动放弃扣得更多。 因此默认"),
                                _createElementVNode$c("strong", null, "关闭"),
                                _createTextVNode$b("且默认"),
                                _createElementVNode$c("strong", null, "干跑"),
                                _createTextVNode$b("；认领后的种子会进"),
                                _createElementVNode$c("strong", null, "硬保护、永不自动删除"),
                                _createTextVNode$b("。 ")
                              ], -1)),
                              _createElementVNode$c("div", _hoisted_56$1, [
                                _createVNode$b(_component_VSwitch, {
                                  modelValue: __props.settingsDraft.claim_enabled,
                                  "onUpdate:modelValue": _cache[51] || (_cache[51] = $event => ((__props.settingsDraft.claim_enabled) = $event)),
                                  label: "启用认领",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"]),
                                _createVNode$b(_component_VSwitch, {
                                  modelValue: __props.settingsDraft.claim_dry,
                                  "onUpdate:modelValue": _cache[52] || (_cache[52] = $event => ((__props.settingsDraft.claim_dry) = $event)),
                                  label: "干跑（只读，不认领）",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: "",
                                  disabled: !__props.settingsDraft.claim_enabled
                                }, null, 8, ["modelValue", "disabled"]),
                                _createVNode$b(_component_VSwitch, {
                                  modelValue: __props.settingsDraft.claim_exclude_zero_bonus,
                                  "onUpdate:modelValue": _cache[53] || (_cache[53] = $event => ((__props.settingsDraft.claim_exclude_zero_bonus) = $event)),
                                  label: "零魔种不认领",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"])
                              ]),
                              _createElementVNode$c("div", _hoisted_57$1, [
                                _createElementVNode$c("div", _hoisted_58$1, [
                                  _createVNode$b(_component_VIcon, {
                                    icon: "mdi-web",
                                    size: "16"
                                  }),
                                  _cache[203] || (_cache[203] = _createTextVNode$b(" 站点白名单（留空 = 全站）", -1))
                                ]),
                                _createVNode$b(_component_VCombobox, {
                                  modelValue: __props.settingsDraft.claim_sites,
                                  "onUpdate:modelValue": _cache[54] || (_cache[54] = $event => ((__props.settingsDraft.claim_sites) = $event)),
                                  items: __props.claimSiteOptions,
                                  label: "认领站点（可多选 / 手输域名）",
                                  multiple: "",
                                  chips: "",
                                  "closable-chips": "",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "items"]),
                                _createElementVNode$c("span", _hoisted_59$1, "已选 " + _toDisplayString$c((__props.settingsDraft.claim_sites || []).length) + " 个 · 支持认领的站：" + _toDisplayString$c(__props.claimSiteOptions.join(' / ') || '（尚未探测，打开认领页后可见）'), 1)
                              ]),
                              _createElementVNode$c("div", _hoisted_60$1, [
                                _createElementVNode$c("div", _hoisted_61$1, [
                                  _createVNode$b(_component_VIcon, {
                                    icon: "mdi-tune",
                                    size: "16"
                                  }),
                                  _cache[204] || (_cache[204] = _createTextVNode$b(" 限量 / 限速", -1))
                                ]),
                                _createElementVNode$c("div", _hoisted_62$1, [
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_daily_per_site,
                                    "onUpdate:modelValue": _cache[55] || (_cache[55] = $event => ((__props.settingsDraft.claim_daily_per_site) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "每站每天认领上限",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_batch,
                                    "onUpdate:modelValue": _cache[56] || (_cache[56] = $event => ((__props.settingsDraft.claim_batch) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "单轮最多认领",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_interval_sec,
                                    "onUpdate:modelValue": _cache[57] || (_cache[57] = $event => ((__props.settingsDraft.claim_interval_sec) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "两次认领间隔（秒）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"])
                                ])
                              ]),
                              _createElementVNode$c("div", _hoisted_63$1, [
                                _createElementVNode$c("div", _hoisted_64$1, [
                                  _createVNode$b(_component_VIcon, {
                                    icon: "mdi-shield-alert-outline",
                                    size: "16"
                                  }),
                                  _cache[205] || (_cache[205] = _createTextVNode$b(" 安全阀（拿不准就留着）", -1))
                                ]),
                                _createElementVNode$c("div", _hoisted_65$1, [
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_min_age_days,
                                    "onUpdate:modelValue": _cache[58] || (_cache[58] = $event => ((__props.settingsDraft.claim_min_age_days) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "最短发布天数（0=按站点规则）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_require_seeders,
                                    "onUpdate:modelValue": _cache[59] || (_cache[59] = $event => ((__props.settingsDraft.claim_require_seeders) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "做种人数下限（0=不限）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_min_size_gb,
                                    "onUpdate:modelValue": _cache[60] || (_cache[60] = $event => ((__props.settingsDraft.claim_min_size_gb) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "体积下限 GB（0=不限）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"])
                                ])
                              ]),
                              _createElementVNode$c("div", _hoisted_66$1, [
                                _createElementVNode$c("div", _hoisted_67$1, [
                                  _createVNode$b(_component_VIcon, {
                                    icon: "mdi-seal-variant",
                                    size: "16"
                                  }),
                                  _cache[207] || (_cache[207] = _createTextVNode$b(" 运行 / 状态 ", -1)),
                                  _createVNode$b(_component_VSpacer),
                                  _createVNode$b(_component_VBtn, {
                                    size: "small",
                                    color: "primary",
                                    variant: "tonal",
                                    "prepend-icon": "mdi-open-in-new",
                                    onClick: _cache[61] || (_cache[61] = $event => (emit('open-claim')))
                                  }, {
                                    default: _withCtx$a(() => [...(_cache[206] || (_cache[206] = [
                                      _createTextVNode$b("打开认领页", -1)
                                    ]))]),
                                    _: 1
                                  })
                                ]),
                                _cache[208] || (_cache[208] = _createElementVNode$c("p", { class: "magicflow-field__sub" }, "先「扫描（只读）」看清单；关掉干跑后再执行认领", -1))
                              ])
                            ]))
                          : (settingsTab.value === 'template')
                            ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_68$1, [
                                _cache[211] || (_cache[211] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, " 仅用于新建任务时预填，不影响已有任务。 ", -1)),
                                _createElementVNode$c("div", _hoisted_69$1, [
                                  _createVNode$b(_component_VSelect, {
                                    modelValue: __props.defaultsDraft.downloader,
                                    "onUpdate:modelValue": _cache[62] || (_cache[62] = $event => ((__props.defaultsDraft.downloader) = $event)),
                                    items: __props.status.options.downloaders,
                                    label: "默认下载器",
                                    placeholder: "不指定（新建任务时再选）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue", "items"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.defaultsDraft.brush_interval,
                                    "onUpdate:modelValue": _cache[63] || (_cache[63] = $event => ((__props.defaultsDraft.brush_interval) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    min: "1",
                                    label: "选种周期（分钟）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.defaultsDraft.check_interval,
                                    "onUpdate:modelValue": _cache[64] || (_cache[64] = $event => ((__props.defaultsDraft.check_interval) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    min: "1",
                                    label: "检查周期（分钟）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.defaultsDraft.max_add_per_run,
                                    "onUpdate:modelValue": _cache[65] || (_cache[65] = $event => ((__props.defaultsDraft.max_add_per_run) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    min: "1",
                                    label: "单轮最多新增",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.defaultsDraft.max_download_concurrent,
                                    "onUpdate:modelValue": _cache[66] || (_cache[66] = $event => ((__props.defaultsDraft.max_download_concurrent) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    min: "1",
                                    label: "同时下载数上限",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.defaultsDraft.top_n,
                                    "onUpdate:modelValue": _cache[67] || (_cache[67] = $event => ((__props.defaultsDraft.top_n) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    min: "1",
                                    label: "候选 TopN",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.defaultsDraft.browse_pages,
                                    "onUpdate:modelValue": _cache[68] || (_cache[68] = $event => ((__props.defaultsDraft.browse_pages) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    min: "1",
                                    label: "每轮翻页数",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.defaultsDraft.seen_cooldown_hours,
                                    "onUpdate:modelValue": _cache[69] || (_cache[69] = $event => ((__props.defaultsDraft.seen_cooldown_hours) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    min: "0",
                                    label: "候选去重冷却（小时）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VTextField, {
                                    modelValue: __props.defaultsDraft.brush_seed_days,
                                    "onUpdate:modelValue": _cache[70] || (_cache[70] = $event => ((__props.defaultsDraft.brush_seed_days) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    min: "0",
                                    max: "365",
                                    label: "默认轮转周期(天)（0=按无上传）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue"])
                                ]),
                                _createElementVNode$c("div", _hoisted_70$1, [
                                  _createVNode$b(_component_VSwitch, {
                                    modelValue: __props.defaultsDraft.refill_when_empty,
                                    "onUpdate:modelValue": _cache[71] || (_cache[71] = $event => ((__props.defaultsDraft.refill_when_empty) = $event)),
                                    label: "清理后自动补种",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VSwitch, {
                                    modelValue: __props.defaultsDraft.cleanup_no_progress,
                                    "onUpdate:modelValue": _cache[72] || (_cache[72] = $event => ((__props.defaultsDraft.cleanup_no_progress) = $event)),
                                    label: "清理无进度种子",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VSwitch, {
                                    modelValue: __props.defaultsDraft.cleanup_slow_progress,
                                    "onUpdate:modelValue": _cache[73] || (_cache[73] = $event => ((__props.defaultsDraft.cleanup_slow_progress) = $event)),
                                    label: "清理过慢种子",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VSwitch, {
                                    modelValue: __props.defaultsDraft.purge_unfree_incomplete,
                                    "onUpdate:modelValue": _cache[74] || (_cache[74] = $event => ((__props.defaultsDraft.purge_unfree_incomplete) = $event)),
                                    label: "清理「已非免费」未下完种子",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VSwitch, {
                                    modelValue: __props.defaultsDraft.auto_resume_paused,
                                    "onUpdate:modelValue": _cache[75] || (_cache[75] = $event => ((__props.defaultsDraft.auto_resume_paused) = $event)),
                                    label: "自动恢复被暂停种子",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$b(_component_VSwitch, {
                                    modelValue: __props.defaultsDraft.delete_files,
                                    "onUpdate:modelValue": _cache[76] || (_cache[76] = $event => ((__props.defaultsDraft.delete_files) = $event)),
                                    label: "删种同时删除文件",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"])
                                ])
                              ]))
                            : (settingsTab.value === 'exam')
                              ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_71$1, [
                                  _cache[214] || (_cache[214] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                    _createTextVNode$b(" 把各站"),
                                    _createElementVNode$c("strong", null, "新手考核"),
                                    _createTextVNode$b("进度抓出来（上传/下载增量、平均做种时间、魔力/做种积分增量）， 并支持"),
                                    _createElementVNode$c("strong", null, "一键起任务"),
                                    _createTextVNode$b("去补未通过项。 数据来源就是各站首页 "),
                                    _createElementVNode$c("code", null, "index.php"),
                                    _createTextVNode$b(" 的考核块 —— 魔流本来就抓这个页面拿实时数据， 所以"),
                                    _createElementVNode$c("strong", null, "不额外消耗站点访问次数（PV）"),
                                    _createTextVNode$b("。 ")
                                  ], -1)),
                                  _cache[215] || (_cache[215] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                    _createElementVNode$c("strong", null, "已通过的考核默认不显示"),
                                    _createTextVNode$b("（过掉的就不占地方了）；想看全部就打开下面的「显示已通过」。 考不过的站会算好缺口：上传差多少 → 刷流任务；魔力/积分差多少 → 魔力任务；平均做种时间不够 → 保持做种 + 多辅种（不用建任务）。 下载类考核项（下载增量）"),
                                    _createElementVNode$c("strong", null, "只做提示、不建任务"),
                                    _createTextVNode$b("。 ")
                                  ], -1)),
                                  _cache[216] || (_cache[216] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                    _createTextVNode$b(" 魔流不做下载业务："),
                                    _createElementVNode$c("strong", null, "不会创建任何下载任务"),
                                    _createTextVNode$b("，也不会为凑下载量去下非免费种。 缺的下载量需要你自己安排；已通过/未通过都不会影响现有做种。 ")
                                  ], -1)),
                                  _createElementVNode$c("div", _hoisted_72$1, [
                                    _createVNode$b(_component_VSwitch, {
                                      modelValue: __props.settingsDraft.exam_enabled,
                                      "onUpdate:modelValue": _cache[77] || (_cache[77] = $event => ((__props.settingsDraft.exam_enabled) = $event)),
                                      label: "启用「新手考核」（关闭则不抓取、不显示）",
                                      color: "primary",
                                      "hide-details": "",
                                      inset: ""
                                    }, null, 8, ["modelValue"]),
                                    _createVNode$b(_component_VSwitch, {
                                      modelValue: __props.settingsDraft.exam_include_pass,
                                      "onUpdate:modelValue": _cache[78] || (_cache[78] = $event => ((__props.settingsDraft.exam_include_pass) = $event)),
                                      label: "显示「已通过」的考核（默认只显示未通过）",
                                      color: "primary",
                                      "hide-details": "",
                                      inset: ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _createElementVNode$c("div", _hoisted_73$1, [
                                    _createVNode$b(_component_VSelect, {
                                      modelValue: __props.settingsDraft.exam_sites,
                                      "onUpdate:modelValue": _cache[79] || (_cache[79] = $event => ((__props.settingsDraft.exam_sites) = $event)),
                                      items: __props.siteSelectItems,
                                      label: "考核站点（不选 = 全部已配置 Cookie 的站点）",
                                      multiple: "",
                                      chips: "",
                                      "closable-chips": "",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8, ["modelValue", "items"]),
                                    _cache[212] || (_cache[212] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, "只盯你关心的站；不选＝全都盯", -1))
                                  ]),
                                  (!__props.settingsDraft.exam_enabled)
                                    ? (_openBlock$c(), _createElementBlock$a("p", _hoisted_74$1, [...(_cache[213] || (_cache[213] = [
                                        _createTextVNode$b(" 当前处于", -1),
                                        _createElementVNode$c("strong", null, "关闭", -1),
                                        _createTextVNode$b("状态：不会去抓考核，也不会做任何额外请求。 ", -1)
                                      ]))]))
                                    : _createCommentVNode$a("", true)
                                ]))
                              : (settingsTab.value === 'signin')
                                ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_75$1, [
                                    _createElementVNode$c("div", _hoisted_76$1, [
                                      _createElementVNode$c("span", _hoisted_77$1, [
                                        _createVNode$b(_component_VIcon, {
                                          icon: "mdi-calendar-check-outline",
                                          size: "20"
                                        })
                                      ]),
                                      _createElementVNode$c("div", _hoisted_78$1, [
                                        _createElementVNode$c("div", _hoisted_79, [
                                          _cache[217] || (_cache[217] = _createElementVNode$c("span", null, "站点签到 / 模拟登录", -1)),
                                          _createVNode$b(_component_VChip, {
                                            size: "small",
                                            variant: "tonal",
                                            color: __props.settingsDraft.signin_enabled ? 'success' : 'grey'
                                          }, {
                                            default: _withCtx$a(() => [
                                              _createTextVNode$b(_toDisplayString$c(__props.settingsDraft.signin_enabled ? '已启用' : '已关闭'), 1)
                                            ]),
                                            _: 1
                                          }, 8, ["color"])
                                        ]),
                                        _cache[218] || (_cache[218] = _createElementVNode$c("div", { class: "magicflow-signin-hero__desc" }, " 勾选站点即可，其余全自动完成。 ", -1))
                                      ])
                                    ]),
                                    _createElementVNode$c("div", _hoisted_80, [
                                      _createElementVNode$c("div", _hoisted_81, [
                                        _createVNode$b(_component_VIcon, {
                                          icon: "mdi-toggle-switch-outline",
                                          size: "16"
                                        }),
                                        _cache[219] || (_cache[219] = _createTextVNode$b(" 开关", -1))
                                      ]),
                                      _createElementVNode$c("div", _hoisted_82, [
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.signin_enabled,
                                          "onUpdate:modelValue": _cache[80] || (_cache[80] = $event => ((__props.settingsDraft.signin_enabled) = $event)),
                                          label: "启用站点签到 / 模拟登录",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: "",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"]),
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.signin_notify,
                                          "onUpdate:modelValue": _cache[81] || (_cache[81] = $event => ((__props.settingsDraft.signin_notify) = $event)),
                                          label: "结果推送通知",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: "",
                                          density: "comfortable",
                                          disabled: !__props.settingsDraft.signin_enabled
                                        }, null, 8, ["modelValue", "disabled"])
                                      ]),
                                      (!__props.settingsDraft.signin_enabled)
                                        ? (_openBlock$c(), _createElementBlock$a("p", _hoisted_83, " 当前为关闭状态：不会签到、不会模拟登录，也不发任何请求。 "))
                                        : _createCommentVNode$a("", true)
                                    ]),
                                    _createElementVNode$c("div", _hoisted_84, [
                                      _createElementVNode$c("div", _hoisted_85, [
                                        _createVNode$b(_component_VIcon, {
                                          icon: "mdi-web",
                                          size: "16"
                                        }),
                                        _cache[220] || (_cache[220] = _createTextVNode$b(" 站点选择（勾选即生效）", -1))
                                      ]),
                                      _createElementVNode$c("div", _hoisted_86, [
                                        _createElementVNode$c("div", _hoisted_87, [
                                          _createVNode$b(_component_VSelect, {
                                            modelValue: __props.settingsDraft.signin_sites,
                                            "onUpdate:modelValue": _cache[82] || (_cache[82] = $event => ((__props.settingsDraft.signin_sites) = $event)),
                                            items: __props.siteSelectItems,
                                            label: "签到站点",
                                            multiple: "",
                                            chips: "",
                                            "closable-chips": "",
                                            variant: "outlined",
                                            density: "comfortable",
                                            "hide-details": ""
                                          }, null, 8, ["modelValue", "items"]),
                                          _createElementVNode$c("span", _hoisted_88, "已选 " + _toDisplayString$c((__props.settingsDraft.signin_sites || []).length) + " 个站点", 1)
                                        ]),
                                        _createElementVNode$c("div", _hoisted_89, [
                                          _createVNode$b(_component_VSelect, {
                                            modelValue: __props.settingsDraft.signin_login_sites,
                                            "onUpdate:modelValue": _cache[83] || (_cache[83] = $event => ((__props.settingsDraft.signin_login_sites) = $event)),
                                            items: __props.siteSelectItems,
                                            label: "模拟登录站点",
                                            multiple: "",
                                            chips: "",
                                            "closable-chips": "",
                                            variant: "outlined",
                                            density: "comfortable",
                                            "hide-details": ""
                                          }, null, 8, ["modelValue", "items"]),
                                          _createElementVNode$c("span", _hoisted_90, "已选 " + _toDisplayString$c((__props.settingsDraft.signin_login_sites || []).length) + " 个站点 · 保活 Cookie + 刷新站点数据", 1)
                                        ])
                                      ])
                                    ]),
                                    _createElementVNode$c("div", _hoisted_91, [
                                      _createVNode$b(_component_VBtn, {
                                        size: "small",
                                        color: "primary",
                                        variant: "tonal",
                                        "prepend-icon": "mdi-chart-box-outline",
                                        onClick: _cache[84] || (_cache[84] = $event => (emit('open-signin')))
                                      }, {
                                        default: _withCtx$a(() => [...(_cache[221] || (_cache[221] = [
                                          _createTextVNode$b("查看签到报表", -1)
                                        ]))]),
                                        _: 1
                                      }),
                                      _cache[222] || (_cache[222] = _createElementVNode$c("span", { class: "magicflow-field__sub" }, "签到结果与近 7 天记录都在报表页", -1))
                                    ])
                                  ]))
                                : (settingsTab.value === 'live')
                                  ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_92, [
                                      _cache[223] || (_cache[223] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                        _createTextVNode$b(" MoviePilot 的站点账号数据靠它自己的「站点数据刷新」任务写库（默认 "),
                                        _createElementVNode$c("strong", null, "6 小时"),
                                        _createTextVNode$b("一轮）， 对展示够用，但魔流是拿它"),
                                        _createElementVNode$c("strong", null, "做决策"),
                                        _createTextVNode$b("的（任务目标达标 / 救号分享率 / 兑换提醒）—— 滞后 6 小时就是真偏差。 启用后魔流"),
                                        _createElementVNode$c("strong", null, "直连站点用户栏页"),
                                        _createTextVNode$b("拿实时值（上传 / 下载 / 分享率 / 魔力 / 做种数）， 并监控"),
                                        _createElementVNode$c("strong", null, "「下载量在涨」"),
                                        _createTextVNode$b("——免费种不吃下载，下载量增长说明吃到促销尾巴了。 站点级缓存 + 单飞，抓不到自动回退 MP 数据。 ")
                                      ], -1)),
                                      _cache[224] || (_cache[224] = _createElementVNode$c("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, [
                                        _createTextVNode$b(" ⚠️ 多数站点有"),
                                        _createElementVNode$c("strong", null, "每日访问次数上限"),
                                        _createTextVNode$b("（实测 PTT：用户等级 300 PV/天，含刷流浏览）。 采样太频会把配额打光 → 站点当天拒绝访问（连刷流也取不到种）。命中后魔流会自动"),
                                        _createElementVNode$c("strong", null, "停抓到次日凌晨"),
                                        _createTextVNode$b("并告警， 但配额是共享的："),
                                        _createElementVNode$c("strong", null, "建议按站点把采样周期放长"),
                                        _createTextVNode$b("（比如 15–30 分钟），给选种浏览留余量。 ")
                                      ], -1)),
                                      _createElementVNode$c("div", _hoisted_93, [
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.live_enabled,
                                          "onUpdate:modelValue": _cache[85] || (_cache[85] = $event => ((__props.settingsDraft.live_enabled) = $event)),
                                          label: "启用站点实时数据 + 流量监控",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue"]),
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.live_notify,
                                          "onUpdate:modelValue": _cache[86] || (_cache[86] = $event => ((__props.settingsDraft.live_notify) = $event)),
                                          label: "命中告警时推送通知",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue"]),
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.live_auto_stop,
                                          "onUpdate:modelValue": _cache[87] || (_cache[87] = $event => ((__props.settingsDraft.live_auto_stop) = $event)),
                                          label: "同时把该站「运行中」任务切「做种中」（只停调度）",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _createVNode$b(_component_VDivider, { class: "my-3" }),
                                      _cache[225] || (_cache[225] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                        _createElementVNode$c("strong", null, "流量兜底"),
                                        _createTextVNode$b("：下载中被判「非免费」就干掉，避免白烧下载量。 三处都会核对："),
                                        _createElementVNode$c("em", null, "任务内"),
                                        _createTextVNode$b("回种子详情页核对（开关在任务「高级」里，受本总开关约束）、 "),
                                        _createElementVNode$c("em", null, "全局"),
                                        _createTextVNode$b("用站点「正在下载」列表核对、"),
                                        _createElementVNode$c("em", null, "取种期间"),
                                        _createTextVNode$b("核对来源站。共用下面这个总开关。 ")
                                      ], -1)),
                                      _createElementVNode$c("div", _hoisted_94, [
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.promo_guard,
                                          "onUpdate:modelValue": _cache[88] || (_cache[88] = $event => ((__props.settingsDraft.promo_guard) = $event)),
                                          label: "启用流量兜底（关掉＝下面三项只告警、不动手）",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _createElementVNode$c("div", _hoisted_95, [
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.live_kill_unfree,
                                          "onUpdate:modelValue": _cache[89] || (_cache[89] = $event => ((__props.settingsDraft.live_kill_unfree) = $event)),
                                          disabled: !__props.settingsDraft.promo_guard,
                                          label: "全局：下载量异常增长时，干掉站点里非免费的下载",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue", "disabled"]),
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.live_kill_delete_files,
                                          "onUpdate:modelValue": _cache[90] || (_cache[90] = $event => ((__props.settingsDraft.live_kill_delete_files) = $event)),
                                          disabled: !__props.settingsDraft.promo_guard || !__props.settingsDraft.live_kill_unfree,
                                          label: "干掉时连文件一起删（只动名称+体积对得上的下载中种）",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue", "disabled"]),
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.crossseed_guard,
                                          "onUpdate:modelValue": _cache[91] || (_cache[91] = $event => ((__props.settingsDraft.crossseed_guard) = $event)),
                                          disabled: !__props.settingsDraft.promo_guard,
                                          label: "取种期间核对来源站免费状态；判错就删种并拉黑（建议开启）",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue", "disabled"])
                                      ]),
                                      _createElementVNode$c("div", _hoisted_96, [
                                        _createVNode$b(_component_VTextField, {
                                          modelValue: __props.settingsDraft.crossseed_guard_pct,
                                          "onUpdate:modelValue": _cache[92] || (_cache[92] = $event => ((__props.settingsDraft.crossseed_guard_pct) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          max: "100",
                                          step: "0.5",
                                          disabled: !__props.settingsDraft.promo_guard || !__props.settingsDraft.crossseed_guard,
                                          label: "下载增量阈值（体积的 %）",
                                          hint: "下载增量超过目标体积该比例即判「不免费」（默认 5%）",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue", "disabled"]),
                                        _createVNode$b(_component_VTextField, {
                                          modelValue: __props.settingsDraft.crossseed_guard_min_mb,
                                          "onUpdate:modelValue": _cache[93] || (_cache[93] = $event => ((__props.settingsDraft.crossseed_guard_min_mb) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "10",
                                          disabled: !__props.settingsDraft.promo_guard || !__props.settingsDraft.crossseed_guard,
                                          label: "最小判定增量（MB）",
                                          hint: "避免统计抖动误判，默认 50MB",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue", "disabled"]),
                                        _createVNode$b(_component_VTextField, {
                                          modelValue: __props.settingsDraft.crossseed_guard_interval_min,
                                          "onUpdate:modelValue": _cache[94] || (_cache[94] = $event => ((__props.settingsDraft.crossseed_guard_interval_min) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          max: "1440",
                                          step: "1",
                                          disabled: !__props.settingsDraft.promo_guard || !__props.settingsDraft.crossseed_guard,
                                          label: "兜底核对间隔（分钟）",
                                          hint: "同一来源站两次核对的间隔（默认 15 分钟，各花 1 次请求）",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue", "disabled"])
                                      ]),
                                      _createElementVNode$c("div", _hoisted_97, [
                                        _createVNode$b(_component_VTextField, {
                                          modelValue: __props.settingsDraft.live_interval_minutes,
                                          "onUpdate:modelValue": _cache[95] || (_cache[95] = $event => ((__props.settingsDraft.live_interval_minutes) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "采样周期（分钟）",
                                          hint: "默认 4 分钟；太频繁站点吃不消",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"]),
                                        _createVNode$b(_component_VTextField, {
                                          modelValue: __props.settingsDraft.live_download_alert_mb,
                                          "onUpdate:modelValue": _cache[96] || (_cache[96] = $event => ((__props.settingsDraft.live_download_alert_mb) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "下载增长告警阈值（MB/分钟）",
                                          hint: "超过则告警；默认 50",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"]),
                                        _createVNode$b(_component_VTextField, {
                                          modelValue: __props.settingsDraft.live_ratio_target,
                                          "onUpdate:modelValue": _cache[97] || (_cache[97] = $event => ((__props.settingsDraft.live_ratio_target) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "0.05",
                                          label: "分享率目标线",
                                          hint: "低于则告警并算缺口；0 = 不检查",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      (__props.siteLiveAlerts.length)
                                        ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_98, [
                                            _createElementVNode$c("div", _hoisted_99, "当前「" + _toDisplayString$c(__props.selectedTask?.name) + "」站点告警", 1),
                                            (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(__props.siteLiveAlerts, (alert, idx) => {
                                              return (_openBlock$c(), _createElementBlock$a("div", {
                                                key: `live-cfg-${idx}`,
                                                class: _normalizeClass$4(["magicflow-live-alert", `magicflow-live-alert--${alert.level || 'info'}`])
                                              }, _toDisplayString$c(alert.text), 3))
                                            }), 128))
                                          ]))
                                        : _createCommentVNode$a("", true)
                                    ]))
                                  : (settingsTab.value === 'recommend')
                                    ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_100, [
                                        _cache[226] || (_cache[226] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, " 刷流时顺带甄别「值得收藏 / 观看」的资源：命中的种子会打上推荐标签（受「媒体资产价值闸门」保护、不会被当临时种删掉）并通知你确认；错过确认窗口（过期 / 磁盘不足）则按临时种回收。 ", -1)),
                                        _createVNode$b(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.recommend_enabled,
                                          "onUpdate:modelValue": _cache[98] || (_cache[98] = $event => ((__props.settingsDraft.recommend_enabled) = $event)),
                                          label: "启用推荐甄别",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue"]),
                                        _createElementVNode$c("div", _hoisted_101, [
                                          _createVNode$b(_component_VTextField, {
                                            modelValue: __props.settingsDraft.recommend_min_rating,
                                            "onUpdate:modelValue": _cache[99] || (_cache[99] = $event => ((__props.settingsDraft.recommend_min_rating) = $event)),
                                            modelModifiers: { number: true },
                                            type: "number",
                                            min: "0",
                                            max: "10",
                                            step: "0.1",
                                            label: "评分门槛（高于）",
                                            hint: "评分高于该值才推荐（默认 7.5，来源见左侧）",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue"]),
                                          _createVNode$b(_component_VTextField, {
                                            modelValue: __props.settingsDraft.recommend_expire_days,
                                            "onUpdate:modelValue": _cache[100] || (_cache[100] = $event => ((__props.settingsDraft.recommend_expire_days) = $event)),
                                            modelModifiers: { number: true },
                                            type: "number",
                                            min: "0",
                                            step: "1",
                                            label: "推荐过期天数",
                                            hint: "超过该天数仍未确认即视为过期（0＝不过期）",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue"]),
                                          _createVNode$b(_component_VTextField, {
                                            modelValue: __props.settingsDraft.recommend_temp_ttl_days,
                                            "onUpdate:modelValue": _cache[101] || (_cache[101] = $event => ((__props.settingsDraft.recommend_temp_ttl_days) = $event)),
                                            modelModifiers: { number: true },
                                            type: "number",
                                            min: "0",
                                            step: "1",
                                            label: "临时种 TTL（天）",
                                            hint: "未入选推荐的刷流临时种，超过该天数回收",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue"]),
                                          _createVNode$b(_component_VTextField, {
                                            modelValue: __props.settingsDraft.recommend_disk_min_free_gb,
                                            "onUpdate:modelValue": _cache[102] || (_cache[102] = $event => ((__props.settingsDraft.recommend_disk_min_free_gb) = $event)),
                                            modelModifiers: { number: true },
                                            type: "number",
                                            min: "0",
                                            step: "1",
                                            label: "磁盘余量下限（GB）",
                                            hint: "剩余空间低于该值时推荐立即过期",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue"]),
                                          _createVNode$b(_component_VTextField, {
                                            modelValue: __props.settingsDraft.recommend_douban_service_url,
                                            "onUpdate:modelValue": _cache[103] || (_cache[103] = $event => ((__props.settingsDraft.recommend_douban_service_url) = $event)),
                                            label: "豆瓣服务地址",
                                            placeholder: "http://magicflow-douban:18789",
                                            hint: "magicflow-douban 服务地址，留空用默认；本地查询不限流",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue"]),
                                          _createVNode$b(_component_VTextField, {
                                            modelValue: __props.settingsDraft.recommend_tag,
                                            "onUpdate:modelValue": _cache[104] || (_cache[104] = $event => ((__props.settingsDraft.recommend_tag) = $event)),
                                            label: "推荐标签",
                                            hint: "推荐资源单独打的标签，默认「魔流-推荐」",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue"])
                                        ]),
                                        _createElementVNode$c("div", _hoisted_102, [
                                          _createVNode$b(_component_VSelect, {
                                            modelValue: __props.settingsDraft.recommend_episode_policy,
                                            "onUpdate:modelValue": _cache[105] || (_cache[105] = $event => ((__props.settingsDraft.recommend_episode_policy) = $event)),
                                            items: _unref$5(episodePolicyItems),
                                            "item-title": "title",
                                            "item-value": "value",
                                            label: "单集策略",
                                            hint: "单集＝只有一个文件；默认不自动推荐，要整季请点推荐列表的「订阅整季」",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue", "items"]),
                                          _createVNode$b(_component_VSelect, {
                                            modelValue: __props.settingsDraft.recommend_rating_source,
                                            "onUpdate:modelValue": _cache[106] || (_cache[106] = $event => ((__props.settingsDraft.recommend_rating_source) = $event)),
                                            items: _unref$5(ratingSourceItems),
                                            "item-title": "title",
                                            "item-value": "value",
                                            label: "评分来源",
                                            hint: "默认只用 TMDB；豆瓣优先走本地服务 magicflow-douban",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue", "items"])
                                        ]),
                                        _createElementVNode$c("div", _hoisted_103, [
                                          _createVNode$b(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.recommend_require_chart,
                                            "onUpdate:modelValue": _cache[107] || (_cache[107] = $event => ((__props.settingsDraft.recommend_require_chart) = $event)),
                                            label: "榜单 / 热映 / 订阅命中也算达标（与评分为「或」）",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8, ["modelValue"]),
                                          _createVNode$b(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.recommend_auto_import,
                                            "onUpdate:modelValue": _cache[108] || (_cache[108] = $event => ((__props.settingsDraft.recommend_auto_import) = $event)),
                                            label: "确认后自动整理入库",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8, ["modelValue"]),
                                          _createVNode$b(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.recommend_notify,
                                            "onUpdate:modelValue": _cache[109] || (_cache[109] = $event => ((__props.settingsDraft.recommend_notify) = $event)),
                                            label: "发现推荐时通知",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8, ["modelValue"])
                                        ])
                                      ]))
                                    : (settingsTab.value === 'rules')
                                      ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_104, [
                                          _cache[240] || (_cache[240] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                            _createElementVNode$c("strong", null, "全站 H&R 的唯一入口"),
                                            _createTextVNode$b("：H&R 有无 / 最短保种时长 / 做种上限都在这一页 （跨站取种的「来源份」在兄弟站同样背 H&R 义务，例：学校 BTSchool 要挂种 10 小时）。 优先级："),
                                            _createElementVNode$c("strong", null, "手填 > 页面探测 > 内置 > 全局默认"),
                                            _createTextVNode$b("； 探测遵循「宁保守勿乐观」—— 抓不到就保持原值，绝不假设「没有 H&R」。 ")
                                          ], -1)),
                                          _createElementVNode$c("div", _hoisted_105, [
                                            _createVNode$b(_component_VSwitch, {
                                              modelValue: __props.settingsDraft.rules_auto_refresh,
                                              "onUpdate:modelValue": _cache[110] || (_cache[110] = $event => ((__props.settingsDraft.rules_auto_refresh) = $event)),
                                              label: "每周自动逐站探测规则并入库",
                                              color: "primary",
                                              "hide-details": "",
                                              inset: ""
                                            }, null, 8, ["modelValue"]),
                                            _cache[227] || (_cache[227] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                              _createTextVNode$b(" 到点才跑：每 10 分钟醒来看一眼，满 7 天才真探一次；"),
                                              _createElementVNode$c("strong", null, "重启/更新不会把周期清零"),
                                              _createTextVNode$b("，探测失败按 30 分钟 → 6 小时退避重试（不再一次失败干等一周）。 ")
                                            ], -1))
                                          ]),
                                          _createVNode$b(_component_VDivider, { class: "my-3" }),
                                          _cache[241] || (_cache[241] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                            _createElementVNode$c("strong", null, "H&R 来源"),
                                            _createTextVNode$b("：只认"),
                                            _createElementVNode$c("strong", null, "收件箱「欢迎短讯」里给出的规则地址"),
                                            _createTextVNode$b("（🔗 已存下，可点开）； 页面里顺带抓到的 H&R 不算数。默认时长给"),
                                            _createElementVNode$c("strong", null, "表里未收录"),
                                            _createTextVNode$b("的站点兜底； 每站的时长直接改上表的「"),
                                            _createElementVNode$c("strong", null, "达标期限(h)"),
                                            _createTextVNode$b("」列（手填覆盖，优先级最高）。 ")
                                          ], -1)),
                                          _createElementVNode$c("div", _hoisted_106, [
                                            _createVNode$b(_component_VTextField, {
                                              modelValue: __props.settingsDraft.crossseed_seed_hours_default,
                                              "onUpdate:modelValue": _cache[111] || (_cache[111] = $event => ((__props.settingsDraft.crossseed_seed_hours_default) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              max: "720",
                                              step: "1",
                                              label: "来源站义务工时（小时）",
                                              hint: "来源站未单独指定时的 H&R 义务工时，默认 24h",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable"
                                            }, null, 8, ["modelValue"]),
                                            _createVNode$b(_component_VTextField, {
                                              modelValue: __props.settingsDraft.hr_seed_margin_hours,
                                              "onUpdate:modelValue": _cache[112] || (_cache[112] = $event => ((__props.settingsDraft.hr_seed_margin_hours) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              step: "0.5",
                                              min: "0",
                                              label: "H&R 结清安全垫（小时）",
                                              hint: "做种需 ≥ 站点要求 + 该值才判结清（默认 2，0＝不留垫）",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable"
                                            }, null, 8, ["modelValue"]),
                                            _createVNode$b(_component_VTextField, {
                                              modelValue: __props.settingsDraft.hr_deadline_warn_hours,
                                              "onUpdate:modelValue": _cache[113] || (_cache[113] = $event => ((__props.settingsDraft.hr_deadline_warn_hours) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              step: "1",
                                              min: "0",
                                              label: "H&R 账单临期阈值（小时）",
                                              hint: "种还在 qB、未达标、距达标期限到期 ≤ 该值 → 账单标 at_risk（默认 48）",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable"
                                            }, null, 8, ["modelValue"]),
                                            _createVNode$b(_component_VTextField, {
                                              modelValue: __props.settingsDraft.hr_complete_ratio,
                                              "onUpdate:modelValue": _cache[114] || (_cache[114] = $event => ((__props.settingsDraft.hr_complete_ratio) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              step: "0.001",
                                              min: "0",
                                              max: "1",
                                              label: "H&R 完成度阈值（全局默认）",
                                              hint: "达到该进度才算完成、才计 H&R（默认 99.9%）；分站可在下表覆盖",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable"
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _createElementVNode$c("div", _hoisted_107, [
                                            _createVNode$b(_component_VSwitch, {
                                              modelValue: __props.settingsDraft.crossseed_guard_keep_seed,
                                              "onUpdate:modelValue": _cache[115] || (_cache[115] = $event => ((__props.settingsDraft.crossseed_guard_keep_seed) = $event)),
                                              label: "来源份 H&R 保护（义务工时内不得删/改标签）",
                                              color: "primary",
                                              "hide-details": "",
                                              inset: ""
                                            }, null, 8, ["modelValue"]),
                                            _createVNode$b(_component_VSwitch, {
                                              modelValue: __props.settingsDraft.crossseed_reclaim,
                                              "onUpdate:modelValue": _cache[116] || (_cache[116] = $event => ((__props.settingsDraft.crossseed_reclaim) = $event)),
                                              label: "H&R 期满后回收来源份（只删种子不删文件）",
                                              color: "warning",
                                              "hide-details": "",
                                              inset: ""
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _createElementVNode$c("div", _hoisted_108, [
                                            _createVNode$b(_component_VBtn, {
                                              size: "small",
                                              color: "primary",
                                              variant: "tonal",
                                              loading: __props.rulesProbing,
                                              onClick: _cache[117] || (_cache[117] = $event => (emit('probe-rules')))
                                            }, {
                                              default: _withCtx$a(() => [
                                                _createVNode$b(_component_VIcon, {
                                                  start: "",
                                                  size: "small"
                                                }, {
                                                  default: _withCtx$a(() => [...(_cache[228] || (_cache[228] = [
                                                    _createTextVNode$b("mdi-download-network-outline", -1)
                                                  ]))]),
                                                  _: 1
                                                }),
                                                _cache[229] || (_cache[229] = _createTextVNode$b("逐站拉取（探测页面） ", -1))
                                              ]),
                                              _: 1
                                            }, 8, ["loading"]),
                                            _createVNode$b(_component_VBtn, {
                                              size: "small",
                                              variant: "text",
                                              disabled: __props.rulesLoading,
                                              onClick: _cache[118] || (_cache[118] = $event => (emit('refresh-rules')))
                                            }, {
                                              default: _withCtx$a(() => [...(_cache[230] || (_cache[230] = [
                                                _createTextVNode$b("按 MP 配置补全", -1)
                                              ]))]),
                                              _: 1
                                            }, 8, ["disabled"]),
                                            _createElementVNode$c("span", _hoisted_109, [
                                              _createTextVNode$b("上次自动探测：" + _toDisplayString$c(__props.rulesProbeState?.at ? _unref$5(fmtTs)(__props.rulesProbeState.at) : '从未探测'), 1),
                                              (__props.rulesProbeState?.fail)
                                                ? (_openBlock$c(), _createElementBlock$a(_Fragment$a, { key: 0 }, [
                                                    _createTextVNode$b("（连续失败 " + _toDisplayString$c(__props.rulesProbeState.fail) + " 次，自动退避重试中）", 1)
                                                  ], 64))
                                                : _createCommentVNode$a("", true)
                                            ]),
                                            _createVNode$b(_component_VSpacer),
                                            _createElementVNode$c("span", _hoisted_110, "共 " + _toDisplayString$c(__props.siteRules.length) + " 条", 1)
                                          ]),
                                          (__props.rulesProbing)
                                            ? (_openBlock$c(), _createElementBlock$a("p", _hoisted_111, "正在逐站抓取规则页（每站 1~2 个请求，随机歇 1.5~3.5 秒）…"))
                                            : _createCommentVNode$a("", true),
                                          _createElementVNode$c("div", _hoisted_112, [
                                            _cache[239] || (_cache[239] = _createElementVNode$c("div", { class: "magicflow-rules-row magicflow-rules-row--head" }, [
                                              _createElementVNode$c("span", null, "站点 · 来源"),
                                              _createElementVNode$c("span", null, "H&R"),
                                              _createElementVNode$c("span", null, "期限(h)"),
                                              _createElementVNode$c("span", null, "完成度"),
                                              _createElementVNode$c("span")
                                            ], -1)),
                                            (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(__props.siteRules, (row) => {
                                              return (_openBlock$c(), _createElementBlock$a("div", {
                                                key: row.domain,
                                                class: "magicflow-rules-row"
                                              }, [
                                                _createElementVNode$c("span", {
                                                  class: "magicflow-rules-row__name",
                                                  title: row.domain
                                                }, [
                                                  _createElementVNode$c("b", null, _toDisplayString$c(row.site_name || row.domain), 1),
                                                  (!row.in_library)
                                                    ? (_openBlock$c(), _createElementBlock$a("em", _hoisted_114, "未入库"))
                                                    : _createCommentVNode$a("", true),
                                                  (row.exam_avg_hours)
                                                    ? (_openBlock$c(), _createElementBlock$a("em", {
                                                        key: 1,
                                                        title: row.exam_evidence || '站点考核的平均做种要求（不是 H&R）'
                                                      }, "考核" + _toDisplayString$c(row.exam_avg_hours) + "h", 9, _hoisted_115))
                                                    : _createCommentVNode$a("", true),
                                                  _createElementVNode$c("i", {
                                                    title: row.evidence || ''
                                                  }, [
                                                    _createTextVNode$b(_toDisplayString$c(_unref$5(ruleSourceText)(row)), 1),
                                                    (row.seed_cap)
                                                      ? (_openBlock$c(), _createElementBlock$a(_Fragment$a, { key: 0 }, [
                                                          _createTextVNode$b(" · 上限" + _toDisplayString$c(row.seed_cap), 1)
                                                        ], 64))
                                                      : _createCommentVNode$a("", true),
                                                    (row.seed_need_hours)
                                                      ? (_openBlock$c(), _createElementBlock$a(_Fragment$a, { key: 1 }, [
                                                          _createTextVNode$b(" · 义务" + _toDisplayString$c(row.seed_need_hours) + "h", 1)
                                                        ], 64))
                                                      : _createCommentVNode$a("", true),
                                                    (row.seed_hours_seen != null)
                                                      ? (_openBlock$c(), _createElementBlock$a(_Fragment$a, { key: 2 }, [
                                                          _createTextVNode$b(" · 见" + _toDisplayString$c(row.seed_hours_seen) + "h", 1)
                                                        ], 64))
                                                      : _createCommentVNode$a("", true)
                                                  ], 8, _hoisted_116)
                                                ], 8, _hoisted_113),
                                                _createElementVNode$c("span", _hoisted_117, [
                                                  (row.hr === true)
                                                    ? (_openBlock$c(), _createBlock$a(_component_VChip, {
                                                        key: 0,
                                                        size: "x-small",
                                                        color: "error",
                                                        variant: "tonal"
                                                      }, {
                                                        default: _withCtx$a(() => [...(_cache[231] || (_cache[231] = [
                                                          _createTextVNode$b("有", -1)
                                                        ]))]),
                                                        _: 1
                                                      }))
                                                    : (row.hr === false)
                                                      ? (_openBlock$c(), _createBlock$a(_component_VChip, {
                                                          key: 1,
                                                          size: "x-small",
                                                          color: "success",
                                                          variant: "tonal"
                                                        }, {
                                                          default: _withCtx$a(() => [...(_cache[232] || (_cache[232] = [
                                                            _createTextVNode$b("无", -1)
                                                          ]))]),
                                                          _: 1
                                                        }))
                                                      : (_openBlock$c(), _createBlock$a(_component_VChip, {
                                                          key: 2,
                                                          size: "x-small",
                                                          variant: "tonal"
                                                        }, {
                                                          default: _withCtx$a(() => [...(_cache[233] || (_cache[233] = [
                                                            _createTextVNode$b("未知", -1)
                                                          ]))]),
                                                          _: 1
                                                        })),
                                                  (row.hr === false)
                                                    ? (_openBlock$c(), _createBlock$a(_component_VBtn, {
                                                        key: 3,
                                                        size: "x-small",
                                                        variant: "text",
                                                        disabled: __props.rulesProbing,
                                                        title: "恢复为探测/内置判定",
                                                        onClick: $event => (emit('set-rule-hr', row, 'unknown'))
                                                      }, {
                                                        default: _withCtx$a(() => [...(_cache[234] || (_cache[234] = [
                                                          _createTextVNode$b("恢复", -1)
                                                        ]))]),
                                                        _: 1
                                                      }, 8, ["disabled", "onClick"]))
                                                    : (_openBlock$c(), _createElementBlock$a(_Fragment$a, { key: 4 }, [
                                                        _createVNode$b(_component_VBtn, {
                                                          size: "x-small",
                                                          variant: "text",
                                                          disabled: __props.rulesProbing,
                                                          title: "该站有 H&R：手动确认「有」并按当前时长保护",
                                                          onClick: $event => (emit('set-rule-hr', row, '1'))
                                                        }, {
                                                          default: _withCtx$a(() => [...(_cache[235] || (_cache[235] = [
                                                            _createTextVNode$b("标有", -1)
                                                          ]))]),
                                                          _: 1
                                                        }, 8, ["disabled", "onClick"]),
                                                        _createVNode$b(_component_VBtn, {
                                                          size: "x-small",
                                                          variant: "text",
                                                          disabled: __props.rulesProbing,
                                                          title: "该站没有 H&R：直接标无，不做保种保护",
                                                          onClick: $event => (emit('set-rule-hr', row, '0'))
                                                        }, {
                                                          default: _withCtx$a(() => [...(_cache[236] || (_cache[236] = [
                                                            _createTextVNode$b("标无", -1)
                                                          ]))]),
                                                          _: 1
                                                        }, 8, ["disabled", "onClick"])
                                                      ], 64))
                                                ]),
                                                _createElementVNode$c("span", _hoisted_118, [
                                                  _createVNode$b(_component_VTextField, {
                                                    "model-value": row.effective_hours,
                                                    type: "number",
                                                    min: "0",
                                                    max: "720",
                                                    step: "1",
                                                    density: "compact",
                                                    variant: "outlined",
                                                    "hide-details": "",
                                                    title: '达标期限(h)，来自' + _unref$5(ruleSourceText)(row) + (row.hours_src === 'manual' ? '（手填覆盖）' : ''),
                                                    onChange: $event => (emit('set-rule-hours', row, $event.target.value))
                                                  }, null, 8, ["model-value", "title", "onChange"])
                                                ]),
                                                _createElementVNode$c("span", _hoisted_119, [
                                                  _createVNode$b(_component_VTextField, {
                                                    "model-value": row.complete_ratio,
                                                    type: "number",
                                                    min: "0",
                                                    max: "1",
                                                    step: "0.001",
                                                    density: "compact",
                                                    variant: "outlined",
                                                    "hide-details": "",
                                                    placeholder: "跟全局",
                                                    title: row.complete_ratio == null ? '未覆盖，用全局「H&R 完成度阈值」' : '站点级覆盖（进度达到该值才计 H&R）',
                                                    onChange: $event => (emit('set-rule-ratio', row, $event.target.value))
                                                  }, null, 8, ["model-value", "title", "onChange"])
                                                ]),
                                                _createElementVNode$c("span", _hoisted_120, [
                                                  (row.rule_url)
                                                    ? (_openBlock$c(), _createBlock$a(_component_VBtn, {
                                                        key: 0,
                                                        size: "x-small",
                                                        variant: "text",
                                                        icon: "",
                                                        href: String(row.rule_url).split(/\s+/)[0],
                                                        target: "_blank",
                                                        rel: "noopener",
                                                        title: '规则地址（来自收件箱欢迎短讯）：' + row.rule_url
                                                      }, {
                                                        default: _withCtx$a(() => [
                                                          _createVNode$b(_component_VIcon, { size: "x-small" }, {
                                                            default: _withCtx$a(() => [...(_cache[237] || (_cache[237] = [
                                                              _createTextVNode$b("mdi-link-variant", -1)
                                                            ]))]),
                                                            _: 1
                                                          })
                                                        ]),
                                                        _: 1
                                                      }, 8, ["href", "title"]))
                                                    : _createCommentVNode$a("", true),
                                                  _createVNode$b(_component_VBtn, {
                                                    size: "x-small",
                                                    variant: "text",
                                                    disabled: __props.rulesProbing,
                                                    title: "只探测这一站",
                                                    onClick: $event => (emit('probe-rules', row.domain))
                                                  }, {
                                                    default: _withCtx$a(() => [...(_cache[238] || (_cache[238] = [
                                                      _createTextVNode$b("探测", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["disabled", "onClick"])
                                                ])
                                              ]))
                                            }), 128))
                                          ]),
                                          _cache[242] || (_cache[242] = _createElementVNode$c("details", { class: "magicflow-rules-help" }, [
                                            _createElementVNode$c("summary", null, "怎么改 / 取值说明"),
                                            _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                              _createTextVNode$b(" 「期限(h)」直接改 = 写入手填覆盖（优先级：手填 > 探测 > 内置 > 全局默认）。 「"),
                                              _createElementVNode$c("strong", null, "完成度"),
                                              _createTextVNode$b("」是该站的 H&R 完成度阈值："),
                                              _createElementVNode$c("strong", null, "留空 = 跟全局"),
                                              _createTextVNode$b("（默认 0.999，下满才算）； 某站若规定「下载中即计 H&R」→ 在该站填 "),
                                              _createElementVNode$c("code", null, "0.2"),
                                              _createTextVNode$b(" 之类。 ")
                                            ])
                                          ], -1))
                                        ]))
                                      : (settingsTab.value === 'tags')
                                        ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_121, [
                                            _cache[246] || (_cache[246] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                              _createTextVNode$b(" 标签模型：种子状态 = 标签 "),
                                              _createElementVNode$c("code", null, "魔流-<站点>-<状态>[-<子类>]"),
                                              _createTextVNode$b("， 状态有 "),
                                              _createElementVNode$c("strong", null, "刷流 / 魔力 / 静默(新·资源·普通) / 推荐"),
                                              _createTextVNode$b("； 另有"),
                                              _createElementVNode$c("strong", null, "状态账本"),
                                              _createTextVNode$b("做真值源（标签被改坏也能自愈），以及 "),
                                              _createElementVNode$c("strong", null, "文件组账本"),
                                              _createTextVNode$b("按多站引用计数——"),
                                              _createElementVNode$c("em", null, "摘成员只删种，最后一个成员才连文件清"),
                                              _createTextVNode$b("。 ")
                                            ], -1)),
                                            _createElementVNode$c("div", _hoisted_122, [
                                              _createVNode$b(_component_VSwitch, {
                                                modelValue: __props.settingsDraft.tag_model_enabled,
                                                "onUpdate:modelValue": _cache[119] || (_cache[119] = $event => ((__props.settingsDraft.tag_model_enabled) = $event)),
                                                label: "启用标签模型（状态账本 + 魔流-站点-状态 标签）",
                                                color: "primary",
                                                "hide-details": "",
                                                inset: ""
                                              }, null, 8, ["modelValue"]),
                                              _createVNode$b(_component_VSwitch, {
                                                modelValue: __props.settingsDraft.show_qb_tags,
                                                "onUpdate:modelValue": _cache[120] || (_cache[120] = $event => ((__props.settingsDraft.show_qb_tags) = $event)),
                                                label: "往 qB 写标签（关=纯账本模式）",
                                                color: "primary",
                                                "hide-details": "",
                                                inset: ""
                                              }, null, 8, ["modelValue"])
                                            ]),
                                            _createElementVNode$c("div", _hoisted_123, [
                                              _createVNode$b(_component_VTextField, {
                                                modelValue: __props.settingsDraft.tag_silent_new_timeout_hours,
                                                "onUpdate:modelValue": _cache[121] || (_cache[121] = $event => ((__props.settingsDraft.tag_silent_new_timeout_hours) = $event)),
                                                modelModifiers: { number: true },
                                                type: "number",
                                                min: "0",
                                                step: "1",
                                                label: "「静默-新」超时(小时)",
                                                hint: "超过该时长未分拣自动归「静默-普通」（0＝不超时）",
                                                "persistent-hint": "",
                                                variant: "outlined",
                                                density: "comfortable"
                                              }, null, 8, ["modelValue"])
                                            ]),
                                            _createVNode$b(_component_VDivider, { class: "my-3" }),
                                            _cache[247] || (_cache[247] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                              _createElementVNode$c("strong", null, "静默分拣规则"),
                                              _createTextVNode$b("："),
                                              _createElementVNode$c("code", null, "静默-新"),
                                              _createTextVNode$b(" 命中任一启用规则 → 进 "),
                                              _createElementVNode$c("code", null, "静默-资源"),
                                              _createTextVNode$b("， 否则进 "),
                                              _createElementVNode$c("code", null, "静默-普通"),
                                              _createTextVNode$b("（受站点魔力产出考核）。 ")
                                            ], -1)),
                                            _createElementVNode$c("div", _hoisted_124, [
                                              _cache[244] || (_cache[244] = _createElementVNode$c("div", { class: "magicflow-sort-rules__row magicflow-sort-rules__row--head" }, [
                                                _createElementVNode$c("span", null, "规则"),
                                                _createElementVNode$c("span", null, "阈值"),
                                                _createElementVNode$c("span", null, "权重"),
                                                _createElementVNode$c("span", null, "启用"),
                                                _createElementVNode$c("span")
                                              ], -1)),
                                              (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(__props.settingsDraft.sort_rules, (r, i) => {
                                                return (_openBlock$c(), _createElementBlock$a("div", {
                                                  key: i,
                                                  class: "magicflow-sort-rules__row"
                                                }, [
                                                  _createElementVNode$c("span", null, _toDisplayString$c(_unref$5(sortRuleText)(r)), 1),
                                                  _createElementVNode$c("span", null, [
                                                    (_unref$5(sortRuleNeedsMin)(r.type))
                                                      ? (_openBlock$c(), _createBlock$a(_component_VTextField, {
                                                          key: 0,
                                                          modelValue: r.min,
                                                          "onUpdate:modelValue": $event => ((r.min) = $event),
                                                          modelModifiers: { number: true },
                                                          type: "number",
                                                          step: "0.5",
                                                          density: "compact",
                                                          variant: "outlined",
                                                          "hide-details": "",
                                                          style: {"max-width":"110px"}
                                                        }, null, 8, ["modelValue", "onUpdate:modelValue"]))
                                                      : (_openBlock$c(), _createElementBlock$a("em", _hoisted_125, "-"))
                                                  ]),
                                                  _createElementVNode$c("span", null, [
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: r.weight,
                                                      "onUpdate:modelValue": $event => ((r.weight) = $event),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      step: "5",
                                                      density: "compact",
                                                      variant: "outlined",
                                                      "hide-details": "",
                                                      style: {"max-width":"90px"}
                                                    }, null, 8, ["modelValue", "onUpdate:modelValue"])
                                                  ]),
                                                  _createElementVNode$c("span", null, [
                                                    _createVNode$b(_component_VSwitch, {
                                                      modelValue: r.enabled,
                                                      "onUpdate:modelValue": $event => ((r.enabled) = $event),
                                                      color: "primary",
                                                      density: "compact",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8, ["modelValue", "onUpdate:modelValue"])
                                                  ]),
                                                  _createElementVNode$c("span", null, [
                                                    _createVNode$b(_component_VBtn, {
                                                      size: "x-small",
                                                      variant: "text",
                                                      color: "error",
                                                      onClick: $event => (emit('remove-sort-rule', i))
                                                    }, {
                                                      default: _withCtx$a(() => [...(_cache[243] || (_cache[243] = [
                                                        _createTextVNode$b("删除", -1)
                                                      ]))]),
                                                      _: 1
                                                    }, 8, ["onClick"])
                                                  ])
                                                ]))
                                              }), 128))
                                            ]),
                                            _createElementVNode$c("div", _hoisted_126, [
                                              _createVNode$b(_component_VSelect, {
                                                modelValue: newRuleType.value,
                                                "onUpdate:modelValue": _cache[122] || (_cache[122] = $event => ((newRuleType).value = $event)),
                                                items: _unref$5(sortRuleTypeOptions),
                                                "item-title": "text",
                                                "item-value": "value",
                                                density: "compact",
                                                variant: "outlined",
                                                "hide-details": "",
                                                style: {"max-width":"200px"},
                                                label: "新增规则"
                                              }, null, 8, ["modelValue", "items"]),
                                              _createVNode$b(_component_VBtn, {
                                                size: "small",
                                                variant: "tonal",
                                                color: "primary",
                                                onClick: _cache[123] || (_cache[123] = $event => (emit('add-sort-rule')))
                                              }, {
                                                default: _withCtx$a(() => [...(_cache[245] || (_cache[245] = [
                                                  _createTextVNode$b("加上", -1)
                                                ]))]),
                                                _: 1
                                              })
                                            ]),
                                            _createVNode$b(_component_VDivider, { class: "my-3" }),
                                            _createElementVNode$c("div", _hoisted_127, [
                                              _createVNode$b(_component_VSpacer),
                                              _createElementVNode$c("span", _hoisted_128, "账本 " + _toDisplayString$c(__props.tagInfo?.ledger_count ?? 0) + " 条 · 文件组 " + _toDisplayString$c(__props.tagInfo?.groups?.groups ?? 0) + "（多站 " + _toDisplayString$c(__props.tagInfo?.groups?.multi_site_groups ?? 0) + "）", 1)
                                            ])
                                          ]))
                                        : (settingsTab.value === 'crossseed')
                                          ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_129, [...(_cache[248] || (_cache[248] = [
                                              _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                                _createTextVNode$b(" 跨站免费取种：本站"),
                                                _createElementVNode$c("strong", null, "非免费"),
                                                _createTextVNode$b("的候选 → 去"),
                                                _createElementVNode$c("strong", null, "兄弟站免费下"),
                                                _createTextVNode$b("， 落种由全局任务「"),
                                                _createElementVNode$c("strong", null, "跨站取种"),
                                                _createTextVNode$b("」承接（下载中=在岗）；下载完过 H&R 判定： 欠 → 交保种，不欠 → 入静默池（摘任务标、留身份）。"),
                                                _createElementVNode$c("strong", null, "回辅由「全站辅种」负责"),
                                                _createTextVNode$b("。 "),
                                                _createElementVNode$c("br"),
                                                _createTextVNode$b(" 本页只管「"),
                                                _createElementVNode$c("strong", null, "怎么取种"),
                                                _createTextVNode$b("」： "),
                                                _createElementVNode$c("strong", null, "流量兜底"),
                                                _createTextVNode$b("（含取种期间核对来源站）已在「"),
                                                _createElementVNode$c("strong", null, "站点监控 → 流量兜底"),
                                                _createTextVNode$b("」统一配置； "),
                                                _createElementVNode$c("strong", null, "下完的来源份"),
                                                _createTextVNode$b("会移交「"),
                                                _createElementVNode$c("strong", null, "静默池"),
                                                _createTextVNode$b("」挂 H&R（保种 / 分拣 / 回收由静默池负责）。 ")
                                              ], -1)
                                            ]))]))
                                          : (settingsTab.value === 'fallback')
                                            ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_130, [
                                                _cache[254] || (_cache[254] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                                  _createTextVNode$b(" TMDB 对"),
                                                  _createElementVNode$c("strong", null, "番剧特别篇/前传、国漫、B站特供"),
                                                  _createTextVNode$b("常常「根本没有」，离了它就没元数据可用。 这里做"),
                                                  _createElementVNode$c("strong", null, "多源识别回退"),
                                                  _createTextVNode$b("（按顺序试各来源），给库里缺 NFO 的集补一份"),
                                                  _createElementVNode$c("strong", null, "最小 NFO"),
                                                  _createTextVNode$b("， 让播放器 / 飞牛影视能显示名称与集号。"),
                                                  _createElementVNode$c("strong", null, "只写 NFO，不动媒体文件，已存在的好 NFO 不覆盖。")
                                                ], -1)),
                                                _createElementVNode$c("div", _hoisted_131, [
                                                  _createVNode$b(_component_VSwitch, {
                                                    modelValue: __props.settingsDraft.fallback_enabled,
                                                    "onUpdate:modelValue": _cache[124] || (_cache[124] = $event => ((__props.settingsDraft.fallback_enabled) = $event)),
                                                    label: "启用元数据兜底",
                                                    color: "primary",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode$b(_component_VSwitch, {
                                                    modelValue: __props.settingsDraft.fallback_after_import,
                                                    "onUpdate:modelValue": _cache[125] || (_cache[125] = $event => ((__props.settingsDraft.fallback_after_import) = $event)),
                                                    label: "每次整理入库后自动兜底",
                                                    color: "primary",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode$b(_component_VSwitch, {
                                                    modelValue: __props.settingsDraft.fallback_dry_run,
                                                    "onUpdate:modelValue": _cache[126] || (_cache[126] = $event => ((__props.settingsDraft.fallback_dry_run) = $event)),
                                                    label: "演练模式（只报告不写 NFO）",
                                                    color: "primary",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"])
                                                ]),
                                                _createElementVNode$c("div", _hoisted_132, [
                                                  _cache[250] || (_cache[250] = _createElementVNode$c("div", { class: "magicflow-settings-label" }, "识别来源顺序（自上而下依次尝试）", -1)),
                                                  _createElementVNode$c("ol", _hoisted_133, [
                                                    (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(__props.usedFallbackSources, (src, idx) => {
                                                      return (_openBlock$c(), _createElementBlock$a("li", {
                                                        key: src,
                                                        class: "magicflow-fb-source"
                                                      }, [
                                                        _createElementVNode$c("span", _hoisted_134, _toDisplayString$c(idx + 1), 1),
                                                        _createElementVNode$c("span", _hoisted_135, _toDisplayString$c(_unref$5(fallbackSourceLabel)(src)), 1),
                                                        _createVNode$b(_component_VBtn, {
                                                          icon: "mdi-arrow-up",
                                                          size: "x-small",
                                                          variant: "text",
                                                          disabled: idx === 0,
                                                          "aria-label": "上移",
                                                          onClick: $event => (emit('move-fallback-source', idx, -1))
                                                        }, null, 8, ["disabled", "onClick"]),
                                                        _createVNode$b(_component_VBtn, {
                                                          icon: "mdi-arrow-down",
                                                          size: "x-small",
                                                          variant: "text",
                                                          disabled: idx === __props.usedFallbackSources.length - 1,
                                                          "aria-label": "下移",
                                                          onClick: $event => (emit('move-fallback-source', idx, 1))
                                                        }, null, 8, ["disabled", "onClick"]),
                                                        _createVNode$b(_component_VBtn, {
                                                          icon: "mdi-close",
                                                          size: "x-small",
                                                          variant: "text",
                                                          "aria-label": "移除",
                                                          onClick: $event => (emit('remove-fallback-source', src))
                                                        }, null, 8, ["onClick"])
                                                      ]))
                                                    }), 128))
                                                  ]),
                                                  _createElementVNode$c("div", _hoisted_136, [
                                                    _createVNode$b(_component_VSelect, {
                                                      modelValue: fallbackSourceDraft.value,
                                                      "onUpdate:modelValue": _cache[127] || (_cache[127] = $event => ((fallbackSourceDraft).value = $event)),
                                                      items: __props.unusedFallbackSources,
                                                      "item-title": "title",
                                                      "item-value": "value",
                                                      label: "添加来源",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      "hide-details": "",
                                                      clearable: ""
                                                    }, null, 8, ["modelValue", "items"]),
                                                    _createVNode$b(_component_VBtn, {
                                                      variant: "tonal",
                                                      color: "primary",
                                                      disabled: !fallbackSourceDraft.value,
                                                      onClick: _cache[128] || (_cache[128] = $event => (emit('add-fallback-source')))
                                                    }, {
                                                      default: _withCtx$a(() => [...(_cache[249] || (_cache[249] = [
                                                        _createTextVNode$b("添加", -1)
                                                      ]))]),
                                                      _: 1
                                                    }, 8, ["disabled"])
                                                  ])
                                                ]),
                                                _createVNode$b(_component_VCombobox, {
                                                  modelValue: __props.settingsDraft.fallback_paths,
                                                  "onUpdate:modelValue": _cache[129] || (_cache[129] = $event => ((__props.settingsDraft.fallback_paths) = $event)),
                                                  items: __props.fallbackState?.effective_paths || [],
                                                  label: "兜底扫描的库目录",
                                                  hint: "留空 = 自动取 MoviePilot 目录配置里的 library 路径（如 /movie）",
                                                  "persistent-hint": "",
                                                  variant: "outlined",
                                                  density: "comfortable",
                                                  multiple: "",
                                                  chips: "",
                                                  clearable: ""
                                                }, null, 8, ["modelValue", "items"]),
                                                _createElementVNode$c("div", _hoisted_137, [
                                                  _createVNode$b(_component_VTextField, {
                                                    modelValue: __props.settingsDraft.fallback_interval_minutes,
                                                    "onUpdate:modelValue": _cache[130] || (_cache[130] = $event => ((__props.settingsDraft.fallback_interval_minutes) = $event)),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    label: "扫描周期（分钟）",
                                                    hint: "定时扫库兜底，默认 30",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable"
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode$b(_component_VTextField, {
                                                    modelValue: __props.settingsDraft.fallback_scan_max,
                                                    "onUpdate:modelValue": _cache[131] || (_cache[131] = $event => ((__props.settingsDraft.fallback_scan_max) = $event)),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    label: "每轮最多处理剧集数",
                                                    hint: "其余下轮继续，避免一次卡爆，默认 30",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable"
                                                  }, null, 8, ["modelValue"])
                                                ]),
                                                _createElementVNode$c("div", _hoisted_138, [
                                                  _createVNode$b(_component_VSwitch, {
                                                    modelValue: __props.settingsDraft.fallback_sp_to_s00,
                                                    "onUpdate:modelValue": _cache[132] || (_cache[132] = $event => ((__props.settingsDraft.fallback_sp_to_s00) = $event)),
                                                    label: "特别篇归位：源中不存在的集改归 Season 0（S00EXX）",
                                                    color: "primary",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"])
                                                ]),
                                                _createVNode$b(_component_VDivider, { class: "magicflow-fb-divider" }),
                                                _createElementVNode$c("div", _hoisted_139, [
                                                  _createVNode$b(_component_VBtn, {
                                                    variant: "tonal",
                                                    color: "primary",
                                                    size: "small",
                                                    loading: __props.fallbackRunning,
                                                    disabled: __props.fallbackRunning,
                                                    onClick: _cache[133] || (_cache[133] = $event => (emit('run-fallback', true)))
                                                  }, {
                                                    default: _withCtx$a(() => [...(_cache[251] || (_cache[251] = [
                                                      _createTextVNode$b("演练扫描", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["loading", "disabled"]),
                                                  _createVNode$b(_component_VBtn, {
                                                    variant: "flat",
                                                    color: "primary",
                                                    size: "small",
                                                    loading: __props.fallbackRunning,
                                                    disabled: __props.fallbackRunning,
                                                    onClick: _cache[134] || (_cache[134] = $event => (emit('run-fallback', false)))
                                                  }, {
                                                    default: _withCtx$a(() => [...(_cache[252] || (_cache[252] = [
                                                      _createTextVNode$b("立即执行", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["loading", "disabled"]),
                                                  _createVNode$b(_component_VBtn, {
                                                    variant: "text",
                                                    size: "small",
                                                    loading: __props.fallbackLoading,
                                                    onClick: _cache[135] || (_cache[135] = $event => (emit('load-fallback')))
                                                  }, {
                                                    default: _withCtx$a(() => [...(_cache[253] || (_cache[253] = [
                                                      _createTextVNode$b("刷新结果", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["loading"]),
                                                  (__props.fallbackState?.running)
                                                    ? (_openBlock$c(), _createElementBlock$a("span", _hoisted_140, "● 扫描中…"))
                                                    : _createCommentVNode$a("", true)
                                                ]),
                                                (__props.fallbackState?.report)
                                                  ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_141, [
                                                      _createElementVNode$c("div", _hoisted_142, [
                                                        _createTextVNode$b(" 上次" + _toDisplayString$c(__props.fallbackState.report.applied === false ? '演练' : '执行') + "： 扫描 " + _toDisplayString$c(__props.fallbackState.report.stats?.shows || 0) + " 剧", 1),
                                                        (__props.fallbackState.report.stats?.total_shows)
                                                          ? (_openBlock$c(), _createElementBlock$a(_Fragment$a, { key: 0 }, [
                                                              _createTextVNode$b("/共 " + _toDisplayString$c(__props.fallbackState.report.stats.total_shows) + " 部", 1)
                                                            ], 64))
                                                          : _createCommentVNode$a("", true),
                                                        _createTextVNode$b(" · 识别 " + _toDisplayString$c(__props.fallbackState.report.stats?.resolved || 0) + " · 补集 NFO " + _toDisplayString$c(__props.fallbackState.report.stats?.ep_nfo || 0) + " · 补剧 NFO " + _toDisplayString$c(__props.fallbackState.report.stats?.show_nfo || 0) + " · 源中缺失 " + _toDisplayString$c(__props.fallbackState.report.stats?.missing || 0) + " · 多源补齐 " + _toDisplayString$c(__props.fallbackState.report.stats?.via_extra || 0) + " 集 · 归位 " + _toDisplayString$c(__props.fallbackState.report.stats?.renumbered || 0) + " · " + _toDisplayString$c(__props.fallbackState.report.duration) + "s ", 1)
                                                      ]),
                                                      (__props.fallbackProblemShows.length)
                                                        ? (_openBlock$c(), _createElementBlock$a("details", _hoisted_143, [
                                                            _createElementVNode$c("summary", null, "源里查不到的集（" + _toDisplayString$c(__props.fallbackProblemCount) + " 集，已按本地文件兜底）", 1),
                                                            _createElementVNode$c("ul", _hoisted_144, [
                                                              (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(__props.fallbackProblemShows, (item) => {
                                                                return (_openBlock$c(), _createElementBlock$a("li", {
                                                                  key: item.show
                                                                }, [
                                                                  _createElementVNode$c("strong", null, _toDisplayString$c(item.show), 1),
                                                                  _createElementVNode$c("span", _hoisted_145, _toDisplayString$c((item.problems || []).map(p => `S${String(p.season).padStart(2, '0')}E${String(p.episode).padStart(2, '0')}`).join(' ')), 1)
                                                                ]))
                                                              }), 128))
                                                            ])
                                                          ]))
                                                        : _createCommentVNode$a("", true),
                                                      ((__props.fallbackState.report.shows || []).length)
                                                        ? (_openBlock$c(), _createElementBlock$a("details", _hoisted_146, [
                                                            _createElementVNode$c("summary", null, "展开本剧集明细（" + _toDisplayString$c(__props.fallbackState.report.shows.length) + " 部有变动）", 1),
                                                            _createElementVNode$c("ul", _hoisted_147, [
                                                              (_openBlock$c(true), _createElementBlock$a(_Fragment$a, null, _renderList$8(__props.fallbackState.report.shows, (item) => {
                                                                return (_openBlock$c(), _createElementBlock$a("li", {
                                                                  key: item.show
                                                                }, [
                                                                  _createElementVNode$c("strong", null, _toDisplayString$c(item.show), 1),
                                                                  _createElementVNode$c("span", _hoisted_148, "识别自 " + _toDisplayString$c(item.resolved || '未命中') + "｜补集 " + _toDisplayString$c((item.episodes || []).filter(e => e.nfo).length) + "｜归位 " + _toDisplayString$c((item.renumbered || []).length), 1)
                                                                ]))
                                                              }), 128))
                                                            ])
                                                          ]))
                                                        : _createCommentVNode$a("", true)
                                                    ]))
                                                  : _createCommentVNode$a("", true)
                                              ]))
                                            : (settingsTab.value === 'cloud')
                                              ? (_openBlock$c(), _createElementBlock$a("div", _hoisted_149, [
                                                  _cache[258] || (_cache[258] = _createElementVNode$c("p", { class: "magicflow-settings-hint" }, [
                                                    _createElementVNode$c("strong", null, "本地当热区，夸克当冷库。"),
                                                    _createTextVNode$b(" 把库里的成品大文件上传到 OpenList 的可写存储（夸克 cookie 驱动）， 同一夸克目录会被 OpenList 的 Strm 视图自动生成 "),
                                                    _createElementVNode$c("code", null, ".strm"),
                                                    _createTextVNode$b(" 播放指针， 飞牛影视直接能看 —— "),
                                                    _createElementVNode$c("strong", null, "无需改 OpenList 配置、也无需自己写 strm"),
                                                    _createTextVNode$b("。 默认"),
                                                    _createElementVNode$c("strong", null, "只上传、不删本地"),
                                                    _createTextVNode$b("；删本地与停种必须单独确认。 ")
                                                  ], -1)),
                                                  _createElementVNode$c("div", _hoisted_150, [
                                                    _createVNode$b(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.cloud_enabled,
                                                      "onUpdate:modelValue": _cache[136] || (_cache[136] = $event => ((__props.settingsDraft.cloud_enabled) = $event)),
                                                      label: "启用云盘归档",
                                                      color: "primary",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.cloud_dry_run,
                                                      "onUpdate:modelValue": _cache[137] || (_cache[137] = $event => ((__props.settingsDraft.cloud_dry_run) = $event)),
                                                      label: "演练模式（只列计划，不真传）",
                                                      color: "primary",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.cloud_notify,
                                                      "onUpdate:modelValue": _cache[138] || (_cache[138] = $event => ((__props.settingsDraft.cloud_notify) = $event)),
                                                      label: "完成后通知",
                                                      color: "primary",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8, ["modelValue"])
                                                  ]),
                                                  _createElementVNode$c("div", _hoisted_151, [
                                                    _cache[256] || (_cache[256] = _createElementVNode$c("div", { class: "magicflow-settings-label" }, "OpenList 连接", -1)),
                                                    _createElementVNode$c("div", _hoisted_152, [
                                                      _createVNode$b(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_openlist_url,
                                                        "onUpdate:modelValue": _cache[139] || (_cache[139] = $event => ((__props.settingsDraft.cloud_openlist_url) = $event)),
                                                        label: "OpenList 地址",
                                                        placeholder: "http://192.168.0.61:12022",
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": "",
                                                        autocomplete: "off"
                                                      }, null, 8, ["modelValue"])
                                                    ]),
                                                    _createElementVNode$c("div", _hoisted_153, [
                                                      _createVNode$b(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_openlist_token,
                                                        "onUpdate:modelValue": _cache[140] || (_cache[140] = $event => ((__props.settingsDraft.cloud_openlist_token) = $event)),
                                                        label: "OpenList Token",
                                                        placeholder: __props.cloudCfg.has_token ? '已保存（留空则不修改）' : 'openlist-…',
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": "",
                                                        autocomplete: "off",
                                                        "persistent-hint": "",
                                                        hint: "留空＝保留已存 Token；Token 不回显"
                                                      }, null, 8, ["modelValue", "placeholder"]),
                                                      _createVNode$b(_component_VBtn, {
                                                        variant: "tonal",
                                                        color: "primary",
                                                        size: "small",
                                                        "prepend-icon": "mdi-connection",
                                                        loading: __props.cloudTesting,
                                                        onClick: _cache[141] || (_cache[141] = $event => (emit('test-cloud')))
                                                      }, {
                                                        default: _withCtx$a(() => [...(_cache[255] || (_cache[255] = [
                                                          _createTextVNode$b("测试", -1)
                                                        ]))]),
                                                        _: 1
                                                      }, 8, ["loading"])
                                                    ]),
                                                    (__props.cloudTestMsg)
                                                      ? (_openBlock$c(), _createElementBlock$a("p", {
                                                          key: 0,
                                                          class: _normalizeClass$4(["magicflow-settings-hint", __props.cloudTestOk ? 'text-success' : 'text-error'])
                                                        }, _toDisplayString$c(__props.cloudTestMsg), 3))
                                                      : _createCommentVNode$a("", true)
                                                  ]),
                                                  _createElementVNode$c("div", _hoisted_154, [
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_source_mount,
                                                      "onUpdate:modelValue": _cache[142] || (_cache[142] = $event => ((__props.settingsDraft.cloud_source_mount) = $event)),
                                                      label: "可写存储路径",
                                                      hint: "OpenList 里可写的存储挂载点，默认 /quark",
                                                      "persistent-hint": "",
                                                      variant: "outlined",
                                                      density: "comfortable"
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_strm_mount,
                                                      "onUpdate:modelValue": _cache[143] || (_cache[143] = $event => ((__props.settingsDraft.cloud_strm_mount) = $event)),
                                                      label: "Strm 视图路径",
                                                      hint: "只读校验用（Strm 驱动），默认 /movie",
                                                      "persistent-hint": "",
                                                      variant: "outlined",
                                                      density: "comfortable"
                                                    }, null, 8, ["modelValue"])
                                                  ]),
                                                  _createVNode$b(_component_VTextField, {
                                                    modelValue: __props.settingsDraft.cloud_target_template,
                                                    "onUpdate:modelValue": _cache[144] || (_cache[144] = $event => ((__props.settingsDraft.cloud_target_template) = $event)),
                                                    label: "远端目标模板",
                                                    hint: "{rel}＝相对库根的路径；默认 /quark/movie/{rel}（与本地库同构）",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable"
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode$b(_component_VCombobox, {
                                                    modelValue: __props.settingsDraft.cloud_paths,
                                                    "onUpdate:modelValue": _cache[145] || (_cache[145] = $event => ((__props.settingsDraft.cloud_paths) = $event)),
                                                    label: "扫描目录（容器内路径，留空 = /movie）",
                                                    hint: "可多个；只扫这些库根下的媒体文件",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    chips: "",
                                                    multiple: "",
                                                    clearable: "",
                                                    items: ['/movie']
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode$b(_component_VCombobox, {
                                                    modelValue: __props.settingsDraft.cloud_exclude_paths,
                                                    "onUpdate:modelValue": _cache[146] || (_cache[146] = $event => ((__props.settingsDraft.cloud_exclude_paths) = $event)),
                                                    label: "排除路径（子串匹配）",
                                                    hint: "默认已排除下载区/刷流区/蓝光原盘；这里可再加",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    chips: "",
                                                    multiple: "",
                                                    clearable: "",
                                                    items: ['/movie/刷流', '/movie/下载']
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode$b(_component_VCombobox, {
                                                    modelValue: __props.settingsDraft.cloud_exclude_tags,
                                                    "onUpdate:modelValue": _cache[147] || (_cache[147] = $event => ((__props.settingsDraft.cloud_exclude_tags) = $event)),
                                                    label: "排除标签（做种中的种不打上传策略标，可留空）",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    chips: "",
                                                    multiple: "",
                                                    clearable: "",
                                                    items: ['魔流-推荐', '辅种', '已整理']
                                                  }, null, 8, ["modelValue"]),
                                                  _createElementVNode$c("div", _hoisted_155, [
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_min_size_gb,
                                                      "onUpdate:modelValue": _cache[148] || (_cache[148] = $event => ((__props.settingsDraft.cloud_min_size_gb) = $event)),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      label: "最小体积（GB，0 = 不限）",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      "hide-details": ""
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_max_size_gb,
                                                      "onUpdate:modelValue": _cache[149] || (_cache[149] = $event => ((__props.settingsDraft.cloud_max_size_gb) = $event)),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      label: "最大体积（GB，0 = 不限）",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      "hide-details": ""
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_min_age_days,
                                                      "onUpdate:modelValue": _cache[150] || (_cache[150] = $event => ((__props.settingsDraft.cloud_min_age_days) = $event)),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      label: "最小入库天数（0 = 不限）",
                                                      hint: "只归档入库较久、已经稳定的资源",
                                                      "persistent-hint": "",
                                                      variant: "outlined",
                                                      density: "comfortable"
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_upload_limit_mbps,
                                                      "onUpdate:modelValue": _cache[151] || (_cache[151] = $event => ((__props.settingsDraft.cloud_upload_limit_mbps) = $event)),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      label: "上传限速（Mbps，0 = 不限）",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      "hide-details": ""
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_interval_minutes,
                                                      "onUpdate:modelValue": _cache[152] || (_cache[152] = $event => ((__props.settingsDraft.cloud_interval_minutes) = $event)),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      label: "后台归档周期（分钟）",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      "hide-details": ""
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_scan_max,
                                                      "onUpdate:modelValue": _cache[153] || (_cache[153] = $event => ((__props.settingsDraft.cloud_scan_max) = $event)),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      label: "每轮最多处理文件数",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      "hide-details": ""
                                                    }, null, 8, ["modelValue"])
                                                  ]),
                                                  _createVNode$b(_component_VDivider, { class: "magicflow-fb-divider" }),
                                                  _createElementVNode$c("div", _hoisted_156, [
                                                    _createVNode$b(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.cloud_delete_local,
                                                      "onUpdate:modelValue": _cache[154] || (_cache[154] = $event => ((__props.settingsDraft.cloud_delete_local) = $event)),
                                                      label: "归档后删除本地文件（危险：会停种；插件只记录、不自动执行）",
                                                      color: "error",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8, ["modelValue"]),
                                                    _createVNode$b(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.cloud_remove_torrent,
                                                      "onUpdate:modelValue": _cache[155] || (_cache[155] = $event => ((__props.settingsDraft.cloud_remove_torrent) = $event)),
                                                      label: "同时移除下载器任务（危险，需人工确认）",
                                                      color: "error",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8, ["modelValue"])
                                                  ]),
                                                  _createVNode$b(_component_VAlert, {
                                                    type: "warning",
                                                    variant: "tonal",
                                                    density: "compact"
                                                  }, {
                                                    default: _withCtx$a(() => [...(_cache[257] || (_cache[257] = [
                                                      _createTextVNode$b(" 安全默认：", -1),
                                                      _createElementVNode$c("strong", null, "不删本地、不停种", -1),
                                                      _createTextVNode$b("。删本地需要逐条上传校验通过后手动确认，绝不会自动执行。 ", -1)
                                                    ]))]),
                                                    _: 1
                                                  })
                                                ]))
                                              : _createCommentVNode$a("", true)
              ]))
            : _createCommentVNode$a("", true),
          _createElementVNode$c("footer", _hoisted_157, [
            (settingsTab.value === 'downloader')
              ? (_openBlock$c(), _createBlock$a(_component_VBtn, {
                  key: 0,
                  variant: "tonal",
                  color: "primary",
                  disabled: !__props.downloaderPrefsRecommended,
                  onClick: _cache[156] || (_cache[156] = $event => (emit('apply-recommended')))
                }, {
                  default: _withCtx$a(() => [...(_cache[259] || (_cache[259] = [
                    _createTextVNode$b(" 恢复推荐值 ", -1)
                  ]))]),
                  _: 1
                }, 8, ["disabled"]))
              : _createCommentVNode$a("", true),
            _createVNode$b(_component_VSpacer),
            _createVNode$b(_component_VBtn, {
              variant: "text",
              onClick: _cache[157] || (_cache[157] = $event => (settingsDialog.value = false))
            }, {
              default: _withCtx$a(() => [...(_cache[260] || (_cache[260] = [
                _createTextVNode$b("取消", -1)
              ]))]),
              _: 1
            }),
            _createVNode$b(_component_VBtn, {
              color: "primary",
              variant: "flat",
              loading: __props.saving,
              onClick: _cache[158] || (_cache[158] = $event => (emit('save')))
            }, {
              default: _withCtx$a(() => [...(_cache[261] || (_cache[261] = [
                _createTextVNode$b("保存", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ])
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
const SettingsDialog = Object.assign(_sfc_main$c, { __scopeId: 'data-v-e2f63a1f' })

export default SettingsDialog
