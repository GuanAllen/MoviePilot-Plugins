// SettingsDialog —— 19.16.27 手机设置详情页「×」改为返回目录（目录页/桌面端仍关闭弹窗）。
// 由 SettingsDialog.vue 经 compiler-sfc 编译生成（真实线上入口），scopeId 保持 data-v-e2f63a1f。
// 重编译前已校验 .vue/.js 语义等价：emit 24/24、VTab 14/14、settingsTab 分支 16/16、props 39/39。
import './SettingsDialog.css'

import { useModel as _useModel, mergeModels as _mergeModels } from 'vue'
import { resolveComponent as _resolveComponent, openBlock as _openBlock, createBlock as _createBlock, createCommentVNode as _createCommentVNode, unref as _unref, toDisplayString as _toDisplayString, createElementVNode as _createElementVNode, createVNode as _createVNode, renderList as _renderList, Fragment as _Fragment, createElementBlock as _createElementBlock, normalizeClass as _normalizeClass, createTextVNode as _createTextVNode, withCtx as _withCtx } from "vue"

const _hoisted_1 = { class: "magicflow-settings-dialog__head" }
const _hoisted_2 = { class: "magicflow-settings-dialog__title" }
const _hoisted_3 = { class: "magicflow-settings-nav__group" }
const _hoisted_4 = { class: "magicflow-settings-nav__grid" }
const _hoisted_5 = ["onClick"]
const _hoisted_6 = {
  key: 0,
  class: "magicflow-settings-nav__new"
}
const _hoisted_7 = {
  key: 2,
  class: "magicflow-settings-dialog__body"
}
const _hoisted_8 = {
  key: 0,
  class: "magicflow-settings-form"
}
const _hoisted_9 = { class: "magicflow-settings-lede" }
const _hoisted_10 = { class: "magicflow-settings-block" }
const _hoisted_11 = { class: "magicflow-settings-block__head" }
const _hoisted_12 = { class: "magicflow-settings-switches" }
const _hoisted_13 = { class: "magicflow-settings-block" }
const _hoisted_14 = { class: "magicflow-settings-block__head" }
const _hoisted_15 = { class: "magicflow-settings-grid" }
const _hoisted_16 = { class: "magicflow-settings-block" }
const _hoisted_17 = { class: "magicflow-settings-block__head" }
const _hoisted_18 = { class: "magicflow-settings-switches" }
const _hoisted_19 = { class: "magicflow-settings-grid" }
const _hoisted_20 = {
  key: 1,
  class: "magicflow-settings-form"
}
const _hoisted_21 = { class: "magicflow-settings-block" }
const _hoisted_22 = { class: "magicflow-settings-block__head" }
const _hoisted_23 = {
  key: 1,
  class: "magicflow-settings-danger"
}
const _hoisted_24 = { class: "magicflow-settings-danger__h" }
const _hoisted_25 = { class: "magicflow-settings-block" }
const _hoisted_26 = { class: "magicflow-settings-block__head" }
const _hoisted_27 = { class: "magicflow-settings-grid" }
const _hoisted_28 = { class: "magicflow-settings-switches" }
const _hoisted_29 = { class: "magicflow-settings-block" }
const _hoisted_30 = { class: "magicflow-settings-block__head" }
const _hoisted_31 = { class: "magicflow-tile-switches" }
const _hoisted_32 = { class: "magicflow-field__sub" }
const _hoisted_33 = { class: "magicflow-settings-block" }
const _hoisted_34 = { class: "magicflow-settings-block__head" }
const _hoisted_35 = { class: "magicflow-settings-grid" }
const _hoisted_36 = {
  key: 2,
  class: "magicflow-settings-form"
}
const _hoisted_37 = { class: "magicflow-settings-lede" }
const _hoisted_38 = { class: "magicflow-settings-block" }
const _hoisted_39 = { class: "magicflow-settings-block__head" }
const _hoisted_40 = { class: "magicflow-settings-grid" }
const _hoisted_41 = { class: "magicflow-settings-switches" }
const _hoisted_42 = { class: "magicflow-settings-block" }
const _hoisted_43 = { class: "magicflow-settings-block__head" }
const _hoisted_44 = { class: "magicflow-field-stack" }
const _hoisted_45 = { class: "magicflow-settings-block" }
const _hoisted_46 = { class: "magicflow-settings-block__head" }
const _hoisted_47 = {
  key: 3,
  class: "magicflow-settings-form"
}
const _hoisted_48 = { class: "magicflow-settings-lede" }
const _hoisted_49 = { class: "magicflow-settings-block" }
const _hoisted_50 = { class: "magicflow-settings-block__head" }
const _hoisted_51 = { class: "magicflow-iyuu-token" }
const _hoisted_52 = { class: "magicflow-settings-block" }
const _hoisted_53 = { class: "magicflow-settings-block__head" }
const _hoisted_54 = { class: "magicflow-iyuu-sites" }
const _hoisted_55 = {
  key: 0,
  class: "magicflow-settings-hint"
}
const _hoisted_56 = {
  key: 1,
  class: "magicflow-settings-hint"
}
const _hoisted_57 = { class: "magicflow-iyuu-row__head" }
const _hoisted_58 = { class: "magicflow-iyuu-row__name" }
const _hoisted_59 = {
  key: 0,
  class: "magicflow-iyuu-row__fields"
}
const _hoisted_60 = {
  key: 4,
  class: "magicflow-settings-form"
}
const _hoisted_61 = { class: "magicflow-settings-lede" }
const _hoisted_62 = { class: "magicflow-settings-lede__tag" }
const _hoisted_63 = { class: "magicflow-settings-block" }
const _hoisted_64 = { class: "magicflow-settings-block__head" }
const _hoisted_65 = { class: "magicflow-settings-switches" }
const _hoisted_66 = { class: "magicflow-settings-block" }
const _hoisted_67 = { class: "magicflow-settings-block__head" }
const _hoisted_68 = { class: "magicflow-field__sub" }
const _hoisted_69 = { class: "magicflow-settings-block" }
const _hoisted_70 = { class: "magicflow-settings-block__head" }
const _hoisted_71 = { class: "magicflow-settings-grid" }
const _hoisted_72 = { class: "magicflow-settings-block" }
const _hoisted_73 = { class: "magicflow-settings-block__head" }
const _hoisted_74 = { class: "magicflow-field__sub" }
const _hoisted_75 = {
  class: "magicflow-settings-grid",
  style: {"margin-top":"12px"}
}
const _hoisted_76 = { class: "magicflow-field__sub" }
const _hoisted_77 = { class: "magicflow-settings-block" }
const _hoisted_78 = { class: "magicflow-settings-block__head" }
const _hoisted_79 = {
  key: 0,
  class: "magicflow-reseedpanel"
}
const _hoisted_80 = { class: "magicflow-reseedpanel__row" }
const _hoisted_81 = { class: "magicflow-field__sub" }
const _hoisted_82 = { class: "magicflow-reseedpanel__row" }
const _hoisted_83 = { class: "magicflow-field__sub" }
const _hoisted_84 = {
  key: 0,
  class: "magicflow-reseedpanel__row"
}
const _hoisted_85 = { class: "magicflow-field__sub" }
const _hoisted_86 = { class: "magicflow-reseedpanel__sites" }
const _hoisted_87 = { key: 0 }
const _hoisted_88 = {
  key: 0,
  class: "magicflow-table-empty"
}
const _hoisted_89 = { class: "magicflow-reseedpanel__row" }
const _hoisted_90 = { class: "magicflow-field__sub" }
const _hoisted_91 = {
  key: 1,
  class: "magicflow-field__sub"
}
const _hoisted_92 = {
  key: 5,
  class: "magicflow-settings-form"
}
const _hoisted_93 = { class: "magicflow-settings-danger" }
const _hoisted_94 = { class: "magicflow-settings-danger__h" }
const _hoisted_95 = { class: "magicflow-settings-block" }
const _hoisted_96 = { class: "magicflow-settings-block__head" }
const _hoisted_97 = { class: "magicflow-settings-switches" }
const _hoisted_98 = { class: "magicflow-settings-block" }
const _hoisted_99 = { class: "magicflow-settings-block__head" }
const _hoisted_100 = { class: "magicflow-field__sub" }
const _hoisted_101 = { class: "magicflow-settings-block" }
const _hoisted_102 = { class: "magicflow-settings-block__head" }
const _hoisted_103 = { class: "magicflow-settings-grid" }
const _hoisted_104 = { class: "magicflow-settings-block" }
const _hoisted_105 = { class: "magicflow-settings-block__head" }
const _hoisted_106 = { class: "magicflow-settings-grid" }
const _hoisted_107 = { class: "magicflow-settings-block" }
const _hoisted_108 = { class: "magicflow-settings-block__head" }
const _hoisted_109 = {
  key: 6,
  class: "magicflow-settings-form"
}
const _hoisted_110 = { class: "magicflow-settings-lede" }
const _hoisted_111 = { class: "magicflow-settings-block" }
const _hoisted_112 = { class: "magicflow-settings-block__head" }
const _hoisted_113 = { class: "magicflow-settings-grid" }
const _hoisted_114 = { class: "magicflow-settings-block" }
const _hoisted_115 = { class: "magicflow-settings-block__head" }
const _hoisted_116 = { class: "magicflow-settings-grid" }
const _hoisted_117 = { class: "magicflow-settings-block" }
const _hoisted_118 = { class: "magicflow-settings-block__head" }
const _hoisted_119 = { class: "magicflow-settings-switches" }
const _hoisted_120 = {
  key: 7,
  class: "magicflow-settings-form"
}
const _hoisted_121 = { class: "magicflow-settings-lede" }
const _hoisted_122 = { class: "magicflow-settings-block" }
const _hoisted_123 = { class: "magicflow-settings-block__head" }
const _hoisted_124 = { class: "magicflow-settings-switches" }
const _hoisted_125 = { class: "magicflow-settings-block" }
const _hoisted_126 = { class: "magicflow-settings-block__head" }
const _hoisted_127 = { class: "magicflow-settings-field" }
const _hoisted_128 = {
  key: 0,
  class: "magicflow-settings-hint magicflow-settings-hint--warn"
}
const _hoisted_129 = {
  key: 8,
  class: "magicflow-settings-form"
}
const _hoisted_130 = { class: "magicflow-signin-hero" }
const _hoisted_131 = { class: "magicflow-signin-hero__icon" }
const _hoisted_132 = { class: "magicflow-signin-hero__body" }
const _hoisted_133 = { class: "magicflow-signin-hero__title" }
const _hoisted_134 = { class: "magicflow-settings-block" }
const _hoisted_135 = { class: "magicflow-settings-block__head" }
const _hoisted_136 = { class: "magicflow-switch-list" }
const _hoisted_137 = { class: "magicflow-settings-block" }
const _hoisted_138 = { class: "magicflow-settings-block__head" }
const _hoisted_139 = { class: "magicflow-field-stack" }
const _hoisted_140 = { class: "magicflow-field" }
const _hoisted_141 = { class: "magicflow-field__sub" }
const _hoisted_142 = { class: "magicflow-field" }
const _hoisted_143 = { class: "magicflow-field__sub" }
const _hoisted_144 = { class: "magicflow-signin-actions" }
const _hoisted_145 = {
  key: 9,
  class: "magicflow-settings-form"
}
const _hoisted_146 = { class: "magicflow-settings-lede" }
const _hoisted_147 = { class: "magicflow-settings-block" }
const _hoisted_148 = { class: "magicflow-settings-block__head" }
const _hoisted_149 = { class: "magicflow-settings-switches" }
const _hoisted_150 = { class: "magicflow-settings-grid" }
const _hoisted_151 = { class: "magicflow-settings-block" }
const _hoisted_152 = { class: "magicflow-settings-block__head" }
const _hoisted_153 = { class: "magicflow-settings-switches" }
const _hoisted_154 = { class: "magicflow-settings-grid" }
const _hoisted_155 = {
  key: 0,
  class: "magicflow-live-alerts"
}
const _hoisted_156 = { class: "magicflow-live-alerts__head" }
const _hoisted_157 = {
  key: 10,
  class: "magicflow-settings-form"
}
const _hoisted_158 = { class: "magicflow-settings-lede" }
const _hoisted_159 = { class: "magicflow-settings-block" }
const _hoisted_160 = { class: "magicflow-settings-block__head" }
const _hoisted_161 = { class: "magicflow-settings-switches" }
const _hoisted_162 = { class: "magicflow-settings-block" }
const _hoisted_163 = { class: "magicflow-settings-block__head" }
const _hoisted_164 = { class: "magicflow-settings-grid" }
const _hoisted_165 = { class: "magicflow-settings-block" }
const _hoisted_166 = { class: "magicflow-settings-block__head" }
const _hoisted_167 = { class: "magicflow-settings-grid" }
const _hoisted_168 = {
  key: 11,
  class: "magicflow-settings-form"
}
const _hoisted_169 = { class: "magicflow-settings-lede" }
const _hoisted_170 = { class: "magicflow-settings-block" }
const _hoisted_171 = { class: "magicflow-settings-block__head" }
const _hoisted_172 = { class: "magicflow-settings-switches" }
const _hoisted_173 = { class: "magicflow-settings-block" }
const _hoisted_174 = { class: "magicflow-settings-block__head" }
const _hoisted_175 = { class: "magicflow-settings-grid" }
const _hoisted_176 = { class: "magicflow-settings-block" }
const _hoisted_177 = { class: "magicflow-settings-block__head" }
const _hoisted_178 = { class: "magicflow-settings-switches" }
const _hoisted_179 = { class: "magicflow-settings-block" }
const _hoisted_180 = { class: "magicflow-settings-block__head" }
const _hoisted_181 = { class: "magicflow-settings-block__note" }
const _hoisted_182 = { class: "magicflow-rules-actions" }
const _hoisted_183 = { class: "magicflow-settings-hint" }
const _hoisted_184 = {
  key: 0,
  class: "magicflow-settings-hint"
}
const _hoisted_185 = { class: "magicflow-rules-table" }
const _hoisted_186 = ["title"]
const _hoisted_187 = { key: 0 }
const _hoisted_188 = ["title"]
const _hoisted_189 = ["title"]
const _hoisted_190 = { class: "magicflow-rules-row__hr" }
const _hoisted_191 = { class: "magicflow-rules-row__hours" }
const _hoisted_192 = { class: "magicflow-rules-row__ratio" }
const _hoisted_193 = { class: "magicflow-rules-row__ops" }
const _hoisted_194 = {
  key: 12,
  class: "magicflow-settings-form"
}
const _hoisted_195 = { class: "magicflow-settings-lede" }
const _hoisted_196 = { class: "magicflow-settings-block" }
const _hoisted_197 = { class: "magicflow-settings-block__head" }
const _hoisted_198 = { class: "magicflow-settings-switches" }
const _hoisted_199 = { class: "magicflow-settings-grid" }
const _hoisted_200 = { class: "magicflow-settings-block" }
const _hoisted_201 = { class: "magicflow-settings-block__head" }
const _hoisted_202 = { class: "magicflow-sort-rules" }
const _hoisted_203 = { key: 1 }
const _hoisted_204 = { class: "magicflow-sort-rules__add" }
const _hoisted_205 = { class: "magicflow-settings-block" }
const _hoisted_206 = { class: "magicflow-settings-block__head" }
const _hoisted_207 = { class: "magicflow-field__sub" }
const _hoisted_208 = {
  key: 13,
  class: "magicflow-settings-form"
}
const _hoisted_209 = { class: "magicflow-settings-lede" }
const _hoisted_210 = { class: "magicflow-settings-block" }
const _hoisted_211 = { class: "magicflow-settings-block__head" }
const _hoisted_212 = { class: "magicflow-settings-goto" }
const _hoisted_213 = {
  key: 14,
  class: "magicflow-settings-form"
}
const _hoisted_214 = { class: "magicflow-settings-lede" }
const _hoisted_215 = { class: "magicflow-settings-block" }
const _hoisted_216 = { class: "magicflow-settings-block__head" }
const _hoisted_217 = { class: "magicflow-settings-switches" }
const _hoisted_218 = { class: "magicflow-settings-block" }
const _hoisted_219 = { class: "magicflow-settings-block__head" }
const _hoisted_220 = { class: "magicflow-settings-field" }
const _hoisted_221 = { class: "magicflow-fb-sources" }
const _hoisted_222 = { class: "magicflow-fb-source__idx" }
const _hoisted_223 = { class: "magicflow-fb-source__name" }
const _hoisted_224 = { class: "magicflow-fb-source-add" }
const _hoisted_225 = { class: "magicflow-settings-block" }
const _hoisted_226 = { class: "magicflow-settings-block__head" }
const _hoisted_227 = { class: "magicflow-settings-grid" }
const _hoisted_228 = { class: "magicflow-settings-switches" }
const _hoisted_229 = { class: "magicflow-settings-block" }
const _hoisted_230 = { class: "magicflow-settings-block__head" }
const _hoisted_231 = { class: "magicflow-fb-actions" }
const _hoisted_232 = {
  key: 0,
  class: "magicflow-fb-running"
}
const _hoisted_233 = {
  key: 0,
  class: "magicflow-fb-report"
}
const _hoisted_234 = { class: "magicflow-fb-report__line" }
const _hoisted_235 = {
  key: 0,
  class: "magicflow-fb-report__details"
}
const _hoisted_236 = { class: "magicflow-fb-report__list" }
const _hoisted_237 = { class: "magicflow-fb-report__meta" }
const _hoisted_238 = {
  key: 1,
  class: "magicflow-fb-report__details"
}
const _hoisted_239 = { class: "magicflow-fb-report__list" }
const _hoisted_240 = { class: "magicflow-fb-report__meta" }
const _hoisted_241 = {
  key: 15,
  class: "magicflow-settings-form"
}
const _hoisted_242 = { class: "magicflow-settings-lede" }
const _hoisted_243 = { class: "magicflow-settings-block" }
const _hoisted_244 = { class: "magicflow-settings-block__head" }
const _hoisted_245 = { class: "magicflow-settings-switches" }
const _hoisted_246 = { class: "magicflow-settings-block" }
const _hoisted_247 = { class: "magicflow-settings-block__head" }
const _hoisted_248 = { class: "magicflow-iyuu-token" }
const _hoisted_249 = { class: "magicflow-iyuu-token mt-2" }
const _hoisted_250 = { class: "magicflow-settings-block" }
const _hoisted_251 = { class: "magicflow-settings-block__head" }
const _hoisted_252 = { class: "magicflow-settings-grid" }
const _hoisted_253 = { class: "magicflow-settings-block" }
const _hoisted_254 = { class: "magicflow-settings-block__head" }
const _hoisted_255 = { class: "magicflow-settings-grid" }
const _hoisted_256 = { class: "magicflow-settings-block" }
const _hoisted_257 = { class: "magicflow-settings-block__head" }
const _hoisted_258 = { class: "magicflow-settings-switches" }
const _hoisted_259 = { class: "magicflow-settings-dialog__footer" }

import { MF_SETTINGS_TABS, MF_SETTINGS_GROUPS, TILE_OPTIONS, ratingSourceItems, episodePolicyItems, agentToolScopeItems } from '../../constants'
import { fmtTs } from '../../format'
import { settingsTabLabel, ruleSourceText } from '../../composables/useSettings'
import { sortRuleText, sortRuleNeedsMin, sortRuleTypeOptions } from '../../composables/useTagModel'
import { fallbackSourceLabel } from '../../composables/useFallback'

// 弹窗开关 / 当前标签 / 可写草稿（双向）

const _sfc_main$c = {
  __name: 'SettingsDialog',
  props: /*@__PURE__*/_mergeModels({
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
  emits: /*@__PURE__*/_mergeModels([
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
const settingsDialog = _useModel(__props, "modelValue")
const settingsTab = _useModel(__props, 'settingsTab')
const fallbackSourceDraft = _useModel(__props, 'fallbackSourceDraft')
const newRuleType = _useModel(__props, 'newRuleType')

const emit = __emit

// 供父组件在子渲染后取回设置导航栏 DOM（父 composable 的自动滚动依赖它）


return (_ctx, _cache) => {
  const _component_VBtn = _resolveComponent("VBtn")
  const _component_VIcon = _resolveComponent("VIcon")
  const _component_VTab = _resolveComponent("VTab")
  const _component_VTabs = _resolveComponent("VTabs")
  const _component_VDivider = _resolveComponent("VDivider")
  const _component_VSwitch = _resolveComponent("VSwitch")
  const _component_VTextField = _resolveComponent("VTextField")
  const _component_VSelect = _resolveComponent("VSelect")
  const _component_VChip = _resolveComponent("VChip")
  const _component_VSpacer = _resolveComponent("VSpacer")
  const _component_VCombobox = _resolveComponent("VCombobox")
  const _component_VCard = _resolveComponent("VCard")
  const _component_VDialog = _resolveComponent("VDialog")

  return (_openBlock(), _createBlock(_component_VDialog, {
    modelValue: settingsDialog.value,
    "onUpdate:modelValue": _cache[162] || (_cache[162] = $event => ((settingsDialog).value = $event)),
    "max-width": "62rem",
    fullscreen: __props.isNarrow
  }, {
    default: _withCtx(() => [
      _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-settings-dialog" }, {
        default: _withCtx(() => [
          _createElementVNode("header", _hoisted_1, [
            (__props.isNarrow && __props.settingsPane === 'form')
              ? (_openBlock(), _createBlock(_component_VBtn, {
                  key: 0,
                  icon: "mdi-arrow-left",
                  size: "small",
                  variant: "text",
                  "aria-label": "返回设置目录",
                  onClick: _cache[0] || (_cache[0] = $event => (emit('back-to-dir')))
                }))
              : _createCommentVNode("v-if", true),
            _createElementVNode("span", _hoisted_2, _toDisplayString(__props.isNarrow && __props.settingsPane === 'form' ? _unref(settingsTabLabel)(settingsTab.value) : '插件设置'), 1 /* TEXT */),
            _cache[163] || (_cache[163] = _createElementVNode("span", { class: "magicflow-scope-tag" }, "全局", -1 /* CACHED */)),
            _createVNode(_component_VBtn, {
              icon: "mdi-close",
              size: "small",
              variant: "text",
              "aria-label": __props.isNarrow && __props.settingsPane === 'form' ? '返回设置目录' : '关闭',
              onClick: _cache[1] || (_cache[1] = $event => (__props.isNarrow && __props.settingsPane === 'form' ? emit('back-to-dir') : (settingsDialog.value = false)))
            }, null, 8 /* PROPS */, ["aria-label"])
          ]),
          (!__props.isNarrow || __props.settingsPane === 'dir')
            ? (_openBlock(), _createElementBlock("div", {
                key: 0,
                class: "magicflow-settings-nav",
                ref: __props.setNavEl
              }, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(MF_SETTINGS_GROUPS), (g) => {
                  return (_openBlock(), _createElementBlock(_Fragment, {
                    key: g.title
                  }, [
                    _createElementVNode("div", _hoisted_3, _toDisplayString(g.title), 1 /* TEXT */),
                    _createElementVNode("div", _hoisted_4, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(g.items, (t) => {
                        return (_openBlock(), _createElementBlock("button", {
                          key: t.key,
                          type: "button",
                          class: _normalizeClass(["magicflow-settings-nav__item", { 'is-active': settingsTab.value === t.key, 'is-new': !!t.isNew }]),
                          onClick: $event => (emit('open-tab', t.key))
                        }, [
                          (t.isNew)
                            ? (_openBlock(), _createElementBlock("span", _hoisted_6, "新"))
                            : _createCommentVNode("v-if", true),
                          _createVNode(_component_VIcon, {
                            icon: t.icon,
                            size: "18"
                          }, null, 8 /* PROPS */, ["icon"]),
                          _createElementVNode("span", null, _toDisplayString(t.label), 1 /* TEXT */)
                        ], 10 /* CLASS, PROPS */, _hoisted_5))
                      }), 128 /* KEYED_FRAGMENT */))
                    ])
                  ], 64 /* STABLE_FRAGMENT */))
                }), 128 /* KEYED_FRAGMENT */))
              ], 512 /* NEED_PATCH */))
            : _createCommentVNode("v-if", true),
          _createVNode(_component_VTabs, {
            modelValue: settingsTab.value,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((settingsTab).value = $event)),
            class: "magicflow-settings-dialog__tabs",
            density: "comfortable",
            "show-arrows": ""
          }, {
            default: _withCtx(() => [
              _createVNode(_component_VTab, {
                value: "general",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[164] || (_cache[164] = [
                  _createTextVNode("常规", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "downloader",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[165] || (_cache[165] = [
                  _createTextVNode("下载与目录", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "template",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[166] || (_cache[166] = [
                  _createTextVNode("默认任务模板", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "iyuu",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[167] || (_cache[167] = [
                  _createTextVNode("IYUU 辅种", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "fallback",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[168] || (_cache[168] = [
                  _createTextVNode("元数据兜底", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "cloud",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[169] || (_cache[169] = [
                  _createTextVNode("云盘归档", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "exam",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[170] || (_cache[170] = [
                  _createTextVNode("考核", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "signin",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[171] || (_cache[171] = [
                  _createTextVNode("签到", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "live",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[172] || (_cache[172] = [
                  _createTextVNode("站点监控", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "recommend",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[173] || (_cache[173] = [
                  _createTextVNode("推荐", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "crossseed",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[174] || (_cache[174] = [
                  _createTextVNode("跨站", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "rules",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[175] || (_cache[175] = [
                  _createTextVNode("站点规则", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "tags",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[176] || (_cache[176] = [
                  _createTextVNode("标签管理", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              }),
              _createVNode(_component_VTab, {
                value: "notify",
                class: "magicflow-settings-tab"
              }, {
                default: _withCtx(() => [...(_cache[177] || (_cache[177] = [
                  _createTextVNode("通知", -1 /* CACHED */)
                ]))]),
                _: 1 /* STABLE */
              })
            ]),
            _: 1 /* STABLE */
          }, 8 /* PROPS */, ["modelValue"]),
          (!__props.isNarrow || __props.settingsPane === 'form')
            ? (_openBlock(), _createBlock(_component_VDivider, { key: 1 }))
            : _createCommentVNode("v-if", true),
          (!__props.isNarrow || __props.settingsPane === 'form')
            ? (_openBlock(), _createElementBlock("div", _hoisted_7, [
                _createCommentVNode(" ★ 15.13.0：事件通知（H&R 临期 / 容量红线 / 产出骤降 / 任务失败 / 日报） "),
                (settingsTab.value === 'notify')
                  ? (_openBlock(), _createElementBlock("div", _hoisted_8, [
                      _createElementVNode("div", _hoisted_9, [
                        _createVNode(_component_VIcon, { icon: "mdi-bell-outline" }),
                        _cache[178] || (_cache[178] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                          _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "出事了主动告警，不用自己盯")
                        ], -1 /* CACHED */))
                      ]),
                      _createElementVNode("div", _hoisted_10, [
                        _createElementVNode("div", _hoisted_11, [
                          _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                          _cache[179] || (_cache[179] = _createTextVNode(" 通知开关", -1 /* CACHED */))
                        ]),
                        _createElementVNode("div", _hoisted_12, [
                          _createVNode(_component_VSwitch, {
                            modelValue: __props.settingsDraft.notify_enabled,
                            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((__props.settingsDraft.notify_enabled) = $event)),
                            label: "开启事件通知",
                            color: "primary",
                            "hide-details": "",
                            inset: ""
                          }, null, 8 /* PROPS */, ["modelValue"]),
                          _createVNode(_component_VSwitch, {
                            modelValue: __props.settingsDraft.notify_task_fail,
                            "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((__props.settingsDraft.notify_task_fail) = $event)),
                            label: "任务失败时通知",
                            color: "primary",
                            "hide-details": "",
                            inset: "",
                            disabled: !__props.settingsDraft.notify_enabled
                          }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_13, [
                        _createElementVNode("div", _hoisted_14, [
                          _createVNode(_component_VIcon, { icon: "mdi-timer-alert-outline" }),
                          _cache[180] || (_cache[180] = _createTextVNode(" 告警阈值 ", -1 /* CACHED */))
                        ]),
                        _createElementVNode("div", _hoisted_15, [
                          _createVNode(_component_VTextField, {
                            modelValue: __props.settingsDraft.notify_hr_hours,
                            "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((__props.settingsDraft.notify_hr_hours) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            step: "1",
                            label: "H&R 到期提醒提前量（小时）",
                            hint: "距达标期限不足该小时数就发信（默认 24）",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable",
                            disabled: !__props.settingsDraft.notify_enabled
                          }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                          _createVNode(_component_VTextField, {
                            modelValue: __props.settingsDraft.notify_capacity_pct,
                            "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((__props.settingsDraft.notify_capacity_pct) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "50",
                            max: "99",
                            step: "1",
                            label: "池盘告警阈值（%）",
                            hint: "池盘占用达到该百分比就提醒（默认 80）",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable",
                            disabled: !__props.settingsDraft.notify_enabled
                          }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                          _createVNode(_component_VTextField, {
                            modelValue: __props.settingsDraft.notify_drop_pct,
                            "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((__props.settingsDraft.notify_drop_pct) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "1",
                            step: "1",
                            label: "产出骤降阈值（%）",
                            hint: "比前 3 日均值低超过该比例就提醒（默认 20%）",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable",
                            disabled: !__props.settingsDraft.notify_enabled
                          }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_16, [
                        _createElementVNode("div", _hoisted_17, [
                          _createVNode(_component_VIcon, { icon: "mdi-newspaper-variant-outline" }),
                          _cache[181] || (_cache[181] = _createTextVNode(" 每日日报与免打扰 ", -1 /* CACHED */))
                        ]),
                        _createElementVNode("div", _hoisted_18, [
                          _createVNode(_component_VSwitch, {
                            modelValue: __props.settingsDraft.notify_daily,
                            "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((__props.settingsDraft.notify_daily) = $event)),
                            label: "发送每日日报",
                            color: "primary",
                            "hide-details": "",
                            inset: "",
                            disabled: !__props.settingsDraft.notify_enabled
                          }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                        ]),
                        _createElementVNode("div", _hoisted_19, [
                          (__props.settingsDraft.notify_daily && __props.settingsDraft.notify_enabled)
                            ? (_openBlock(), _createBlock(_component_VTextField, {
                                key: 0,
                                modelValue: __props.settingsDraft.notify_daily_hour,
                                "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((__props.settingsDraft.notify_daily_hour) = $event)),
                                modelModifiers: { number: true },
                                type: "number",
                                min: "0",
                                max: "23",
                                step: "1",
                                label: "日报发送时间（小时，0-23）",
                                hint: "当天首次扫描时发送",
                                "persistent-hint": "",
                                variant: "outlined",
                                density: "comfortable"
                              }, null, 8 /* PROPS */, ["modelValue"]))
                            : _createCommentVNode("v-if", true),
                          _createVNode(_component_VTextField, {
                            modelValue: __props.settingsDraft.notify_quiet,
                            "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((__props.settingsDraft.notify_quiet) = $event)),
                            label: "免打扰时段（可空）",
                            placeholder: "23:00-08:00",
                            hint: "该时段内不发送（仍记入历史）；留空 = 不静音",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable",
                            disabled: !__props.settingsDraft.notify_enabled
                          }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                        ])
                      ])
                    ]))
                  : _createCommentVNode("v-if", true),
                (settingsTab.value === 'general')
                  ? (_openBlock(), _createElementBlock("div", _hoisted_20, [
                      _createElementVNode("div", _hoisted_21, [
                        _createElementVNode("div", _hoisted_22, [
                          _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                          _cache[182] || (_cache[182] = _createTextVNode(" 总开关与入口", -1 /* CACHED */))
                        ]),
                        _createVNode(_component_VSwitch, {
                          modelValue: __props.settingsDraft.enabled,
                          "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((__props.settingsDraft.enabled) = $event)),
                          label: "启用插件（总开关）",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8 /* PROPS */, ["modelValue"]),
                        _createVNode(_component_VSwitch, {
                          modelValue: __props.settingsDraft.show_sidebar_nav,
                          "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((__props.settingsDraft.show_sidebar_nav) = $event)),
                          label: "显示侧栏入口",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8 /* PROPS */, ["modelValue"]),
                        _createVNode(_component_VSwitch, {
                          modelValue: __props.settingsDraft.agent_mcp,
                          "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((__props.settingsDraft.agent_mcp) = $event)),
                          label: "把魔流能力注册进 MoviePilot Agent / MCP",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8 /* PROPS */, ["modelValue"]),
                        (__props.settingsDraft.agent_mcp)
                          ? (_openBlock(), _createBlock(_component_VSelect, {
                              key: 0,
                              modelValue: __props.settingsDraft.agent_mcp_scope,
                              "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((__props.settingsDraft.agent_mcp_scope) = $event)),
                              items: _unref(agentToolScopeItems),
                              "item-title": "title",
                              "item-value": "value",
                              label: "注册范围",
                              "hide-details": "",
                              variant: "outlined",
                              density: "comfortable"
                            }, null, 8 /* PROPS */, ["modelValue", "items"]))
                          : _createCommentVNode("v-if", true),
                        (__props.settingsDraft.agent_mcp)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_23, [
                              _createElementVNode("div", _hoisted_24, [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-alert-outline",
                                  size: "18"
                                }),
                                _cache[183] || (_cache[183] = _createTextVNode(" 写操作也一并注册", -1 /* CACHED */))
                              ])
                            ]))
                          : _createCommentVNode("v-if", true)
                      ]),
                      _createElementVNode("div", _hoisted_25, [
                        _createElementVNode("div", _hoisted_26, [
                          _createVNode(_component_VIcon, { icon: "mdi-timer-sand" }),
                          _cache[184] || (_cache[184] = _createTextVNode(" 请求与记录", -1 /* CACHED */))
                        ]),
                        _createVNode(_component_VTextField, {
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
                        }, null, 8 /* PROPS */, ["modelValue"]),
                        _createVNode(_component_VTextField, {
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
                        }, null, 8 /* PROPS */, ["modelValue"]),
                        _createElementVNode("div", _hoisted_27, [
                          _createVNode(_component_VTextField, {
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
                          }, null, 8 /* PROPS */, ["modelValue"]),
                          _createVNode(_component_VTextField, {
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
                          }, null, 8 /* PROPS */, ["modelValue"]),
                          _createVNode(_component_VTextField, {
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
                          }, null, 8 /* PROPS */, ["modelValue"]),
                          _createVNode(_component_VTextField, {
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
                          }, null, 8 /* PROPS */, ["modelValue"])
                        ]),
                        _createElementVNode("div", _hoisted_28, [
                          _createVNode(_component_VSwitch, {
                            modelValue: __props.settingsDraft.debug_log,
                            "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((__props.settingsDraft.debug_log) = $event)),
                            label: "调试日志",
                            color: "primary",
                            "hide-details": "",
                            inset: ""
                          }, null, 8 /* PROPS */, ["modelValue"]),
                          _createVNode(_component_VSwitch, {
                            modelValue: __props.settingsDraft.compact_mode,
                            "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((__props.settingsDraft.compact_mode) = $event)),
                            label: "紧凑模式",
                            color: "primary",
                            "hide-details": "",
                            inset: ""
                          }, null, 8 /* PROPS */, ["modelValue"])
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_29, [
                        _createElementVNode("div", _hoisted_30, [
                          _createVNode(_component_VIcon, {
                            icon: "mdi-view-grid-outline",
                            size: "16"
                          }),
                          _cache[185] || (_cache[185] = _createTextVNode(" 顶栏功能磁贴", -1 /* CACHED */))
                        ]),
                        _createElementVNode("div", _hoisted_31, [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(TILE_OPTIONS), (t) => {
                            return (_openBlock(), _createBlock(_component_VSwitch, {
                              key: t.key,
                              "model-value": __props.tileShown(t.key),
                              label: t.label,
                              "prepend-icon": t.icon,
                              color: "primary",
                              "hide-details": "",
                              inset: "",
                              density: "comfortable",
                              "onUpdate:modelValue": v => emit('set-tile-shown', t.key, v)
                            }, null, 8 /* PROPS */, ["model-value", "label", "prepend-icon", "onUpdate:modelValue"]))
                          }), 128 /* KEYED_FRAGMENT */))
                        ]),
                        _createElementVNode("p", _hoisted_32, " 已显示 " + _toDisplayString(_unref(TILE_OPTIONS).filter(t => __props.tileShown(t.key)).length) + " / " + _toDisplayString(_unref(TILE_OPTIONS).length), 1 /* TEXT */)
                      ]),
                      _createElementVNode("div", _hoisted_33, [
                        _createElementVNode("div", _hoisted_34, [
                          _createVNode(_component_VIcon, {
                            icon: "mdi-lifebuoy",
                            size: "16"
                          }),
                          _cache[186] || (_cache[186] = _createTextVNode(" 死种补源（rescue）", -1 /* CACHED */))
                        ]),
                        _createElementVNode("div", _hoisted_35, [
                          _createVNode(_component_VTextField, {
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
                          }, null, 8 /* PROPS */, ["modelValue"]),
                          _createVNode(_component_VTextField, {
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
                          }, null, 8 /* PROPS */, ["modelValue"])
                        ])
                      ])
                    ]))
                  : (settingsTab.value === 'downloader')
                    ? (_openBlock(), _createElementBlock("div", _hoisted_36, [
                        _createElementVNode("div", _hoisted_37, [
                          _createVNode(_component_VIcon, { icon: "mdi-download-network-outline" }),
                          _cache[187] || (_cache[187] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                            _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "调 qBittorrent 的全局参数")
                          ], -1 /* CACHED */)),
                          _cache[188] || (_cache[188] = _createElementVNode("span", { class: "magicflow-settings-lede__tag is-warn" }, "写 qB 全局", -1 /* CACHED */))
                        ]),
                        _createElementVNode("div", _hoisted_38, [
                          _createElementVNode("div", _hoisted_39, [
                            _createVNode(_component_VIcon, { icon: "mdi-speedometer" }),
                            _cache[189] || (_cache[189] = _createTextVNode(" 限速与连接 ", -1 /* CACHED */))
                          ]),
                          _createElementVNode("div", _hoisted_40, [
                            _createVNode(_component_VTextField, {
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
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VTextField, {
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
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: __props.downloaderPrefsDraft.max_connec,
                              "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((__props.downloaderPrefsDraft.max_connec) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "0",
                              label: "最大连接数",
                              variant: "outlined",
                              density: "comfortable",
                              "hide-details": ""
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: __props.downloaderPrefsDraft.max_connec_per_torrent,
                              "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((__props.downloaderPrefsDraft.max_connec_per_torrent) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "0",
                              label: "每种子连接数",
                              variant: "outlined",
                              density: "comfortable",
                              "hide-details": ""
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VTextField, {
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
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VTextField, {
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
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VTextField, {
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
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VTextField, {
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
                            }, null, 8 /* PROPS */, ["modelValue"])
                          ]),
                          _createElementVNode("div", _hoisted_41, [
                            _createVNode(_component_VSwitch, {
                              modelValue: __props.downloaderPrefsDraft.queueing_enabled,
                              "onUpdate:modelValue": _cache[33] || (_cache[33] = $event => ((__props.downloaderPrefsDraft.queueing_enabled) = $event)),
                              label: "启用队列限制（活动数上限生效的前提）",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8 /* PROPS */, ["modelValue"])
                          ])
                        ]),
                        _createElementVNode("div", _hoisted_42, [
                          _createElementVNode("div", _hoisted_43, [
                            _createVNode(_component_VIcon, { icon: "mdi-folder-network-outline" }),
                            _cache[190] || (_cache[190] = _createTextVNode(" qBittorrent 目录 ", -1 /* CACHED */))
                          ]),
                          _createElementVNode("div", _hoisted_44, [
                            _createVNode(_component_VTextField, {
                              modelValue: __props.downloaderPathsDraft.save_path,
                              "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((__props.downloaderPathsDraft.save_path) = $event)),
                              label: "默认保存路径",
                              placeholder: "如 /vol3/1000/media",
                              variant: "outlined",
                              density: "comfortable",
                              "hide-details": ""
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: __props.downloaderPathsDraft.temp_path,
                              "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((__props.downloaderPathsDraft.temp_path) = $event)),
                              label: "临时下载路径",
                              placeholder: "下载中暂存目录",
                              variant: "outlined",
                              density: "comfortable",
                              "hide-details": ""
                            }, null, 8 /* PROPS */, ["modelValue"]),
                            _createVNode(_component_VSwitch, {
                              modelValue: __props.downloaderPathsDraft.temp_path_enabled,
                              "onUpdate:modelValue": _cache[36] || (_cache[36] = $event => ((__props.downloaderPathsDraft.temp_path_enabled) = $event)),
                              label: "启用临时下载路径（下载中放临时目录，完成后移入保存路径）",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8 /* PROPS */, ["modelValue"])
                          ])
                        ]),
                        _createElementVNode("div", _hoisted_45, [
                          _createElementVNode("div", _hoisted_46, [
                            _createVNode(_component_VIcon, { icon: "mdi-folder-marker-outline" }),
                            _cache[191] || (_cache[191] = _createTextVNode(" 任务保存目录 ", -1 /* CACHED */))
                          ]),
                          _createVNode(_component_VTextField, {
                            modelValue: __props.defaultsDraft.save_path,
                            "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((__props.defaultsDraft.save_path) = $event)),
                            label: "任务保存目录",
                            placeholder: "如 /vol3/1000/media/magicflow",
                            hint: "新建任务时预填此目录（不改已有任务）",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8 /* PROPS */, ["modelValue"])
                        ])
                      ]))
                    : (settingsTab.value === 'iyuu')
                      ? (_openBlock(), _createElementBlock("div", _hoisted_47, [
                          _createElementVNode("div", _hoisted_48, [
                            _createVNode(_component_VIcon, { icon: "mdi-cloud-sync-outline" }),
                            _cache[192] || (_cache[192] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                              _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "IYUU 云端辅种（可选增强）")
                            ], -1 /* CACHED */)),
                            _createElementVNode("span", {
                              class: _normalizeClass(["magicflow-settings-lede__tag", { 'is-warn': !(__props.settingsDraft.iyuu_token || __props.iyuuStatus?.token_set) }])
                            }, _toDisplayString((__props.settingsDraft.iyuu_token || __props.iyuuStatus?.token_set) ? '已启用' : '未启用'), 3 /* TEXT, CLASS */)
                          ]),
                          _createElementVNode("div", _hoisted_49, [
                            _createElementVNode("div", _hoisted_50, [
                              _createVNode(_component_VIcon, { icon: "mdi-key-outline" }),
                              _cache[193] || (_cache[193] = _createTextVNode(" 云端 Token ", -1 /* CACHED */))
                            ]),
                            _createElementVNode("div", _hoisted_51, [
                              _createVNode(_component_VTextField, {
                                modelValue: __props.settingsDraft.iyuu_token,
                                "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((__props.settingsDraft.iyuu_token) = $event)),
                                label: "IYUU 云端 Token",
                                placeholder: __props.iyuuStatus?.token_set ? '已保存（留空则不修改）' : '留空 = 不启用 IYUU 辅种',
                                variant: "outlined",
                                density: "comfortable",
                                "hide-details": "",
                                autocomplete: "off"
                              }, null, 8 /* PROPS */, ["modelValue", "placeholder"]),
                              _createVNode(_component_VBtn, {
                                variant: "tonal",
                                color: "primary",
                                size: "small",
                                "prepend-icon": "mdi-connection",
                                loading: __props.iyuuTesting,
                                disabled: !__props.settingsDraft.iyuu_token && !__props.iyuuStatus?.token_set,
                                onClick: _cache[39] || (_cache[39] = $event => (emit('test-iyuu')))
                              }, {
                                default: _withCtx(() => [...(_cache[194] || (_cache[194] = [
                                  _createTextVNode("测试", -1 /* CACHED */)
                                ]))]),
                                _: 1 /* STABLE */
                              }, 8 /* PROPS */, ["loading", "disabled"]),
                              (__props.settingsDraft.iyuu_token || __props.iyuuStatus?.token_set)
                                ? (_openBlock(), _createBlock(_component_VBtn, {
                                    key: 0,
                                    variant: "text",
                                    color: "error",
                                    size: "small",
                                    "prepend-icon": "mdi-close-circle-outline",
                                    onClick: _cache[40] || (_cache[40] = $event => (emit('clear-iyuu')))
                                  }, {
                                    default: _withCtx(() => [...(_cache[195] || (_cache[195] = [
                                      _createTextVNode("清空", -1 /* CACHED */)
                                    ]))]),
                                    _: 1 /* STABLE */
                                  }))
                                : _createCommentVNode("v-if", true)
                            ])
                          ]),
                          _createElementVNode("div", _hoisted_52, [
                            _createElementVNode("div", _hoisted_53, [
                              _createVNode(_component_VIcon, { icon: "mdi-key-variant" }),
                              _cache[196] || (_cache[196] = _createTextVNode(" 站点密钥 ", -1 /* CACHED */)),
                              (__props.iyuuStatus)
                                ? (_openBlock(), _createBlock(_component_VChip, {
                                    key: 0,
                                    class: "magicflow-settings-block__note",
                                    size: "x-small",
                                    variant: "tonal",
                                    color: __props.iyuuStatus.enabled ? 'success' : 'grey'
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(_toDisplayString(__props.iyuuStatus.enabled ? '已启用' : '未启用'), 1 /* TEXT */)
                                    ]),
                                    _: 1 /* STABLE */
                                  }, 8 /* PROPS */, ["color"]))
                                : _createCommentVNode("v-if", true)
                            ]),
                            _createElementVNode("div", _hoisted_54, [
                              (__props.iyuuLoading)
                                ? (_openBlock(), _createElementBlock("p", _hoisted_55, "加载中…"))
                                : (!__props.iyuuSites.length)
                                  ? (_openBlock(), _createElementBlock("p", _hoisted_56, " 未检测到已配置站点（请先在 MoviePilot 中添加站点）。 "))
                                  : _createCommentVNode("v-if", true),
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.iyuuSites, (row) => {
                                return (_openBlock(), _createElementBlock("div", {
                                  key: row.domain || row.name,
                                  class: "magicflow-iyuu-row"
                                }, [
                                  _createElementVNode("div", _hoisted_57, [
                                    _createElementVNode("span", _hoisted_58, _toDisplayString(row.name), 1 /* TEXT */),
                                    (row.iyuu_sid)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 0,
                                          size: "x-small",
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx(() => [
                                            _createTextVNode("IYUU #" + _toDisplayString(row.iyuu_sid), 1 /* TEXT */)
                                          ]),
                                          _: 2 /* DYNAMIC */
                                        }, 1024 /* DYNAMIC_SLOTS */))
                                      : _createCommentVNode("v-if", true),
                                    (row.has_apikey)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 1,
                                          size: "x-small",
                                          variant: "tonal",
                                          color: "success"
                                        }, {
                                          default: _withCtx(() => [...(_cache[197] || (_cache[197] = [
                                            _createTextVNode("API", -1 /* CACHED */)
                                          ]))]),
                                          _: 1 /* STABLE */
                                        }))
                                      : _createCommentVNode("v-if", true),
                                    (row.has_cookie)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 2,
                                          size: "x-small",
                                          variant: "tonal",
                                          color: "info"
                                        }, {
                                          default: _withCtx(() => [...(_cache[198] || (_cache[198] = [
                                            _createTextVNode("Cookie", -1 /* CACHED */)
                                          ]))]),
                                          _: 1 /* STABLE */
                                        }))
                                      : _createCommentVNode("v-if", true),
                                    _createVNode(_component_VSpacer),
                                    _createVNode(_component_VBtn, {
                                      size: "x-small",
                                      variant: "text",
                                      "append-icon": __props.iyuuShowMore[row.domain || row.name] ? 'mdi-chevron-up' : 'mdi-chevron-down',
                                      onClick: $event => (__props.iyuuShowMore[row.domain || row.name] = !__props.iyuuShowMore[row.domain || row.name])
                                    }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(__props.iyuuShowMore[row.domain || row.name] ? '收起' : '更多'), 1 /* TEXT */)
                                      ]),
                                      _: 2 /* DYNAMIC */
                                    }, 1032 /* PROPS, DYNAMIC_SLOTS */, ["append-icon", "onClick"])
                                  ]),
                                  (__props.iyuuShowMore[row.domain || row.name])
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_59, [
                                        _cache[199] || (_cache[199] = _createElementVNode("div", {
                                          class: "text-caption text-medium-emphasis",
                                          style: {"grid-column":"1 / -1"}
                                        }, " passkey 统一在「RSS / 凭据」里填写（这里不再重复） ", -1 /* CACHED */)),
                                        _createVNode(_component_VTextField, {
                                          modelValue: row.uid,
                                          "onUpdate:modelValue": $event => ((row.uid) = $event),
                                          label: "uid（可选）",
                                          placeholder: row.uid_set ? '已保存（留空则不修改）' : '留空 = 自动获取',
                                          variant: "outlined",
                                          density: "compact",
                                          "hide-details": "",
                                          autocomplete: "off"
                                        }, null, 8 /* PROPS */, ["modelValue", "onUpdate:modelValue", "placeholder"])
                                      ]))
                                    : _createCommentVNode("v-if", true),
                                  (__props.iyuuShowMore[row.domain || row.name])
                                    ? (_openBlock(), _createBlock(_component_VTextField, {
                                        key: 1,
                                        modelValue: row.downhash,
                                        "onUpdate:modelValue": $event => ((row.downhash) = $event),
                                        label: "downhash（可选）",
                                        placeholder: row.downhash_set ? '已保存（留空则不修改）' : '留空 = 自动获取',
                                        variant: "outlined",
                                        density: "compact",
                                        "hide-details": "",
                                        autocomplete: "off"
                                      }, null, 8 /* PROPS */, ["modelValue", "onUpdate:modelValue", "placeholder"]))
                                    : _createCommentVNode("v-if", true)
                                ]))
                              }), 128 /* KEYED_FRAGMENT */))
                            ])
                          ])
                        ]))
                      : (settingsTab.value === 'reseed')
                        ? (_openBlock(), _createElementBlock("div", _hoisted_60, [
                            _createElementVNode("div", _hoisted_61, [
                              _createVNode(_component_VIcon, { icon: "mdi-seed-outline" }),
                              _cache[200] || (_cache[200] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "本机已有的文件，去各站找同一种子挂上去")
                              ], -1 /* CACHED */)),
                              _createElementVNode("span", _hoisted_62, "零下载 · 本地 " + _toDisplayString(__props.reseedState?.debug?.direct_sites ?? 0) + " 站", 1 /* TEXT */)
                            ]),
                            _createElementVNode("div", _hoisted_63, [
                              _createElementVNode("div", _hoisted_64, [
                                _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                                _cache[201] || (_cache[201] = _createTextVNode(" 开关", -1 /* CACHED */))
                              ]),
                              _createElementVNode("div", _hoisted_65, [
                                _createVNode(_component_VSwitch, {
                                  modelValue: __props.settingsDraft.reseed_enabled,
                                  "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((__props.settingsDraft.reseed_enabled) = $event)),
                                  label: "启用全站辅种",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8 /* PROPS */, ["modelValue"]),
                                _createVNode(_component_VSwitch, {
                                  modelValue: __props.settingsDraft.reseed_dry,
                                  "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((__props.settingsDraft.reseed_dry) = $event)),
                                  label: "干跑（只算不挂）",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: "",
                                  disabled: !__props.settingsDraft.reseed_enabled
                                }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                              ])
                            ]),
                            _createElementVNode("div", _hoisted_66, [
                              _createElementVNode("div", _hoisted_67, [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-web",
                                  size: "16"
                                }),
                                _cache[202] || (_cache[202] = _createTextVNode(" 目标站点（留空 = 全部有 IYUU 编号的站）", -1 /* CACHED */))
                              ]),
                              _createVNode(_component_VSelect, {
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
                              }, null, 8 /* PROPS */, ["modelValue", "items"]),
                              _createElementVNode("span", _hoisted_68, "已选 " + _toDisplayString((__props.settingsDraft.reseed_sites || []).length) + " 个 · 不在 IYUU 站点表里的站当不了目标", 1 /* TEXT */)
                            ]),
                            _createElementVNode("div", _hoisted_69, [
                              _createElementVNode("div", _hoisted_70, [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-tune",
                                  size: "16"
                                }),
                                _cache[203] || (_cache[203] = _createTextVNode(" 限量", -1 /* CACHED */))
                              ]),
                              _createElementVNode("div", _hoisted_71, [
                                _createVNode(_component_VTextField, {
                                  modelValue: __props.settingsDraft.reseed_daily_per_site,
                                  "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((__props.settingsDraft.reseed_daily_per_site) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  label: "每站每天挂种上限",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8 /* PROPS */, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: __props.settingsDraft.reseed_batch,
                                  "onUpdate:modelValue": _cache[45] || (_cache[45] = $event => ((__props.settingsDraft.reseed_batch) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  label: "每轮最多处理（对）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8 /* PROPS */, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: __props.settingsDraft.reseed_min_size_gb,
                                  "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((__props.settingsDraft.reseed_min_size_gb) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  label: "最小体积 GB",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8 /* PROPS */, ["modelValue"])
                              ])
                            ]),
                            _createElementVNode("div", _hoisted_72, [
                              _createElementVNode("div", _hoisted_73, [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-magnify",
                                  size: "16"
                                }),
                                _cache[204] || (_cache[204] = _createTextVNode(" 本地直连搜索", -1 /* CACHED */))
                              ]),
                              _createVNode(_component_VSelect, {
                                modelValue: __props.settingsDraft.reseed_search_sites,
                                "onUpdate:modelValue": _cache[47] || (_cache[47] = $event => ((__props.settingsDraft.reseed_search_sites) = $event)),
                                items: (__props.reseedState?.config?.search_options || []).map((o) => ({ title: `${o.name} · ${o.domain}`, value: o.domain })),
                                label: "启用直连搜索的站",
                                multiple: "",
                                chips: "",
                                "closable-chips": "",
                                variant: "outlined",
                                density: "comfortable",
                                "hide-details": ""
                              }, null, 8 /* PROPS */, ["modelValue", "items"]),
                              _createElementVNode("span", _hoisted_74, "候选来自后端预设（" + _toDisplayString((__props.reseedState?.config?.search_options || []).length) + " 站）· 只放实测过的站，新站要先写进预设表", 1 /* TEXT */),
                              _createElementVNode("div", _hoisted_75, [
                                _createVNode(_component_VTextField, {
                                  modelValue: __props.settingsDraft.reseed_search_kw,
                                  "onUpdate:modelValue": _cache[48] || (_cache[48] = $event => ((__props.settingsDraft.reseed_search_kw) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  label: "每轮词数上限（0 = 用预设）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8 /* PROPS */, ["modelValue"])
                              ]),
                              _createElementVNode("span", _hoisted_76, "已启用 " + _toDisplayString((__props.settingsDraft.reseed_search_sites || []).length) + " 站 · 每轮 " + _toDisplayString(__props.settingsDraft.reseed_search_kw || (__props.reseedState?.config?.search_options?.[0]?.kw_per_round || 20)) + " 词 · worker 15 分钟一轮", 1 /* TEXT */)
                            ]),
                            _createElementVNode("div", _hoisted_77, [
                              _createElementVNode("div", _hoisted_78, [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-content-duplicate",
                                  size: "16"
                                }),
                                _cache[206] || (_cache[206] = _createTextVNode(" 运行 / 状态 ", -1 /* CACHED */)),
                                _createVNode(_component_VSpacer),
                                _createVNode(_component_VBtn, {
                                  size: "small",
                                  variant: "text",
                                  "prepend-icon": "mdi-refresh",
                                  class: "me-2",
                                  onClick: _cache[49] || (_cache[49] = $event => (emit('load-reseed')))
                                }, {
                                  default: _withCtx(() => [...(_cache[205] || (_cache[205] = [
                                    _createTextVNode("刷新", -1 /* CACHED */)
                                  ]))]),
                                  _: 1 /* STABLE */
                                }),
                                _createVNode(_component_VBtn, {
                                  size: "small",
                                  color: "primary",
                                  variant: "tonal",
                                  "prepend-icon": "mdi-play",
                                  loading: __props.reseedRunning,
                                  onClick: _cache[50] || (_cache[50] = $event => (emit('run-reseed')))
                                }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(__props.settingsDraft.reseed_dry ? '立即干跑一轮' : '立即跑一轮'), 1 /* TEXT */)
                                  ]),
                                  _: 1 /* STABLE */
                                }, 8 /* PROPS */, ["loading"])
                              ]),
                              (__props.reseedState)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_79, [
                                    _createElementVNode("div", _hoisted_80, [
                                      _createVNode(_component_VChip, {
                                        size: "small",
                                        variant: "tonal",
                                        color: __props.reseedState.enabled ? 'success' : 'grey'
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(__props.reseedState.enabled ? '已启用' : '未启用'), 1 /* TEXT */)
                                        ]),
                                        _: 1 /* STABLE */
                                      }, 8 /* PROPS */, ["color"]),
                                      _createVNode(_component_VChip, {
                                        size: "small",
                                        variant: "tonal",
                                        color: __props.reseedState.dry ? 'warning' : 'grey'
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(__props.reseedState.dry ? '干跑' : '实挂'), 1 /* TEXT */)
                                        ]),
                                        _: 1 /* STABLE */
                                      }, 8 /* PROPS */, ["color"]),
                                      (__props.reseedState.running)
                                        ? (_openBlock(), _createBlock(_component_VChip, {
                                            key: 0,
                                            size: "small",
                                            variant: "tonal",
                                            color: "info"
                                          }, {
                                            default: _withCtx(() => [...(_cache[207] || (_cache[207] = [
                                              _createTextVNode("运行中…", -1 /* CACHED */)
                                            ]))]),
                                            _: 1 /* STABLE */
                                          }))
                                        : _createCommentVNode("v-if", true),
                                      _createElementVNode("span", _hoisted_81, "IYUU 云端 " + _toDisplayString(__props.reseedState.debug?.token ? '✓' : '✗') + " · 云端站点表 " + _toDisplayString(__props.reseedState.debug?.iyuu_sites ?? 0) + " · 可辅站 " + _toDisplayString(__props.reseedState.debug?.mapped ?? 0), 1 /* TEXT */)
                                    ]),
                                    _createElementVNode("div", _hoisted_82, [
                                      _createElementVNode("span", _hoisted_83, "本机上报 " + _toDisplayString(__props.reseedState.cloud?.hashes ?? 0) + " 颗 · IYUU 云端命中候选 " + _toDisplayString(__props.reseedState.cloud?.candidates ?? 0) + " 对", 1 /* TEXT */)
                                    ]),
                                    (__props.reseedState.last && __props.reseedState.last.at)
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_84, [
                                          _createElementVNode("span", _hoisted_85, " 上轮 " + _toDisplayString(_unref(fmtTs)(__props.reseedState.last.at)) + "：计划 " + _toDisplayString(__props.reseedState.last.plan ?? 0) + " · 挂上 " + _toDisplayString(__props.reseedState.last.ok ?? 0) + " · 已有 " + _toDisplayString(__props.reseedState.last.have ?? 0) + " · 不一致 " + _toDisplayString(__props.reseedState.last.mismatch ?? 0) + " · 缺链 " + _toDisplayString(__props.reseedState.last.nourl ?? 0) + " · 缺 PV " + _toDisplayString(__props.reseedState.last.pv ?? 0) + " · 失败 " + _toDisplayString(__props.reseedState.last.fail ?? 0) + " · 干跑可挂 " + _toDisplayString(__props.reseedState.last.would ?? 0) + "（" + _toDisplayString(__props.reseedState.last.duration ?? 0) + "s） ", 1 /* TEXT */)
                                        ]))
                                      : _createCommentVNode("v-if", true),
                                    _createElementVNode("div", _hoisted_86, [
                                      _cache[208] || (_cache[208] = _createElementVNode("div", { class: "magicflow-reseedpanel__head" }, [
                                        _createElementVNode("span", null, "站点"),
                                        _createElementVNode("span", null, "IYUU"),
                                        _createElementVNode("span", null, "passkey"),
                                        _createElementVNode("span", null, "今日 / 上限")
                                      ], -1 /* CACHED */)),
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList((__props.reseedState.sites || []), (s) => {
                                        return (_openBlock(), _createElementBlock("div", {
                                          key: s.sid,
                                          class: "magicflow-reseedpanel__line"
                                        }, [
                                          _createElementVNode("span", null, [
                                            _createTextVNode(_toDisplayString(s.name), 1 /* TEXT */),
                                            (s.domain)
                                              ? (_openBlock(), _createElementBlock("em", _hoisted_87, " · " + _toDisplayString(s.domain), 1 /* TEXT */))
                                              : _createCommentVNode("v-if", true)
                                          ]),
                                          _createElementVNode("span", null, "#" + _toDisplayString(s.sid), 1 /* TEXT */),
                                          _createElementVNode("span", null, _toDisplayString(s.passkey_ok ? '✓' : '—'), 1 /* TEXT */),
                                          _createElementVNode("span", null, _toDisplayString(s.done_today) + " / " + _toDisplayString(s.cap), 1 /* TEXT */)
                                        ]))
                                      }), 128 /* KEYED_FRAGMENT */)),
                                      (!(__props.reseedState.sites || []).length)
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_88, "没有可辅种的站点（与 IYUU 站点表对不上）"))
                                        : _createCommentVNode("v-if", true)
                                    ]),
                                    _createElementVNode("div", _hoisted_89, [
                                      _createElementVNode("span", _hoisted_90, "账本：" + _toDisplayString(Object.entries(__props.reseedState.ledger || {}).map((pair) => `${pair[0]} ${pair[1]}`).join(' · ') || '空（还没跑过）'), 1 /* TEXT */)
                                    ])
                                  ]))
                                : (_openBlock(), _createElementBlock("p", _hoisted_91, "加载中…"))
                            ])
                          ]))
                        : (settingsTab.value === 'claim')
                          ? (_openBlock(), _createElementBlock("div", _hoisted_92, [
                              _createElementVNode("div", _hoisted_93, [
                                _createElementVNode("div", _hoisted_94, [
                                  _createVNode(_component_VIcon, {
                                    icon: "mdi-alert-outline",
                                    size: "18"
                                  }),
                                  _cache[209] || (_cache[209] = _createTextVNode(" 不可逆的对外写操作", -1 /* CACHED */))
                                ])
                              ]),
                              _createElementVNode("div", _hoisted_95, [
                                _createElementVNode("div", _hoisted_96, [
                                  _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                                  _cache[210] || (_cache[210] = _createTextVNode(" 开关", -1 /* CACHED */))
                                ]),
                                _createElementVNode("div", _hoisted_97, [
                                  _createVNode(_component_VSwitch, {
                                    modelValue: __props.settingsDraft.claim_enabled,
                                    "onUpdate:modelValue": _cache[51] || (_cache[51] = $event => ((__props.settingsDraft.claim_enabled) = $event)),
                                    label: "启用认领",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8 /* PROPS */, ["modelValue"]),
                                  _createVNode(_component_VSwitch, {
                                    modelValue: __props.settingsDraft.claim_dry,
                                    "onUpdate:modelValue": _cache[52] || (_cache[52] = $event => ((__props.settingsDraft.claim_dry) = $event)),
                                    label: "干跑（只读，不认领）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: "",
                                    disabled: !__props.settingsDraft.claim_enabled
                                  }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                  _createVNode(_component_VSwitch, {
                                    modelValue: __props.settingsDraft.claim_exclude_zero_bonus,
                                    "onUpdate:modelValue": _cache[53] || (_cache[53] = $event => ((__props.settingsDraft.claim_exclude_zero_bonus) = $event)),
                                    label: "零魔种不认领",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8 /* PROPS */, ["modelValue"])
                                ])
                              ]),
                              _createElementVNode("div", _hoisted_98, [
                                _createElementVNode("div", _hoisted_99, [
                                  _createVNode(_component_VIcon, {
                                    icon: "mdi-web",
                                    size: "16"
                                  }),
                                  _cache[211] || (_cache[211] = _createTextVNode(" 站点白名单（留空 = 全站）", -1 /* CACHED */))
                                ]),
                                _createVNode(_component_VCombobox, {
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
                                }, null, 8 /* PROPS */, ["modelValue", "items"]),
                                _createElementVNode("span", _hoisted_100, "已选 " + _toDisplayString((__props.settingsDraft.claim_sites || []).length) + " 个 · 支持认领的站：" + _toDisplayString(__props.claimSiteOptions.join(' / ') || '（尚未探测，打开认领页后可见）'), 1 /* TEXT */)
                              ]),
                              _createElementVNode("div", _hoisted_101, [
                                _createElementVNode("div", _hoisted_102, [
                                  _createVNode(_component_VIcon, {
                                    icon: "mdi-tune",
                                    size: "16"
                                  }),
                                  _cache[212] || (_cache[212] = _createTextVNode(" 限量 / 限速", -1 /* CACHED */))
                                ]),
                                _createElementVNode("div", _hoisted_103, [
                                  _createVNode(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_daily_per_site,
                                    "onUpdate:modelValue": _cache[55] || (_cache[55] = $event => ((__props.settingsDraft.claim_daily_per_site) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "每站每天认领上限",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8 /* PROPS */, ["modelValue"]),
                                  _createVNode(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_batch,
                                    "onUpdate:modelValue": _cache[56] || (_cache[56] = $event => ((__props.settingsDraft.claim_batch) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "单轮最多认领",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8 /* PROPS */, ["modelValue"]),
                                  _createVNode(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_interval_sec,
                                    "onUpdate:modelValue": _cache[57] || (_cache[57] = $event => ((__props.settingsDraft.claim_interval_sec) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "两次认领间隔（秒）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8 /* PROPS */, ["modelValue"])
                                ])
                              ]),
                              _createElementVNode("div", _hoisted_104, [
                                _createElementVNode("div", _hoisted_105, [
                                  _createVNode(_component_VIcon, {
                                    icon: "mdi-shield-alert-outline",
                                    size: "16"
                                  }),
                                  _cache[213] || (_cache[213] = _createTextVNode(" 安全阀（拿不准就留着）", -1 /* CACHED */))
                                ]),
                                _createElementVNode("div", _hoisted_106, [
                                  _createVNode(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_min_age_days,
                                    "onUpdate:modelValue": _cache[58] || (_cache[58] = $event => ((__props.settingsDraft.claim_min_age_days) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "最短发布天数（0=按站点规则）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8 /* PROPS */, ["modelValue"]),
                                  _createVNode(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_require_seeders,
                                    "onUpdate:modelValue": _cache[59] || (_cache[59] = $event => ((__props.settingsDraft.claim_require_seeders) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "做种人数下限（0=不限）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8 /* PROPS */, ["modelValue"]),
                                  _createVNode(_component_VTextField, {
                                    modelValue: __props.settingsDraft.claim_min_size_gb,
                                    "onUpdate:modelValue": _cache[60] || (_cache[60] = $event => ((__props.settingsDraft.claim_min_size_gb) = $event)),
                                    modelModifiers: { number: true },
                                    type: "number",
                                    label: "体积下限 GB（0=不限）",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8 /* PROPS */, ["modelValue"])
                                ])
                              ]),
                              _createElementVNode("div", _hoisted_107, [
                                _createElementVNode("div", _hoisted_108, [
                                  _createVNode(_component_VIcon, {
                                    icon: "mdi-seal-variant",
                                    size: "16"
                                  }),
                                  _cache[215] || (_cache[215] = _createTextVNode(" 运行 / 状态 ", -1 /* CACHED */)),
                                  _createVNode(_component_VSpacer),
                                  _createVNode(_component_VBtn, {
                                    size: "small",
                                    color: "primary",
                                    variant: "tonal",
                                    "prepend-icon": "mdi-open-in-new",
                                    onClick: _cache[61] || (_cache[61] = $event => (emit('open-claim')))
                                  }, {
                                    default: _withCtx(() => [...(_cache[214] || (_cache[214] = [
                                      _createTextVNode("打开认领页", -1 /* CACHED */)
                                    ]))]),
                                    _: 1 /* STABLE */
                                  })
                                ])
                              ])
                            ]))
                          : (settingsTab.value === 'template')
                            ? (_openBlock(), _createElementBlock("div", _hoisted_109, [
                                _createElementVNode("div", _hoisted_110, [
                                  _createVNode(_component_VIcon, { icon: "mdi-file-cog-outline" }),
                                  _cache[216] || (_cache[216] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                    _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "新建任务时预先填好的值")
                                  ], -1 /* CACHED */)),
                                  _cache[217] || (_cache[217] = _createElementVNode("span", { class: "magicflow-settings-lede__tag" }, "仅预填", -1 /* CACHED */))
                                ]),
                                _createElementVNode("div", _hoisted_111, [
                                  _createElementVNode("div", _hoisted_112, [
                                    _createVNode(_component_VIcon, { icon: "mdi-download-outline" }),
                                    _cache[218] || (_cache[218] = _createTextVNode(" 下载器与周期 ", -1 /* CACHED */))
                                  ]),
                                  _createElementVNode("div", _hoisted_113, [
                                    _createVNode(_component_VSelect, {
                                      modelValue: __props.defaultsDraft.downloader,
                                      "onUpdate:modelValue": _cache[62] || (_cache[62] = $event => ((__props.defaultsDraft.downloader) = $event)),
                                      items: __props.status.options.downloaders,
                                      label: "默认下载器",
                                      placeholder: "不指定（新建任务时再选）",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue", "items"]),
                                    _createVNode(_component_VTextField, {
                                      modelValue: __props.defaultsDraft.brush_interval,
                                      "onUpdate:modelValue": _cache[63] || (_cache[63] = $event => ((__props.defaultsDraft.brush_interval) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "选种周期（分钟）",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VTextField, {
                                      modelValue: __props.defaultsDraft.check_interval,
                                      "onUpdate:modelValue": _cache[64] || (_cache[64] = $event => ((__props.defaultsDraft.check_interval) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "检查周期（分钟）",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VTextField, {
                                      modelValue: __props.defaultsDraft.brush_seed_days,
                                      "onUpdate:modelValue": _cache[65] || (_cache[65] = $event => ((__props.defaultsDraft.brush_seed_days) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      max: "365",
                                      label: "默认轮转周期(天)（0=按无上传）",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue"])
                                  ])
                                ]),
                                _createElementVNode("div", _hoisted_114, [
                                  _createElementVNode("div", _hoisted_115, [
                                    _createVNode(_component_VIcon, { icon: "mdi-filter-variant" }),
                                    _cache[219] || (_cache[219] = _createTextVNode(" 候选与限量 ", -1 /* CACHED */))
                                  ]),
                                  _createElementVNode("div", _hoisted_116, [
                                    _createVNode(_component_VTextField, {
                                      modelValue: __props.defaultsDraft.max_add_per_run,
                                      "onUpdate:modelValue": _cache[66] || (_cache[66] = $event => ((__props.defaultsDraft.max_add_per_run) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "单轮最多新增",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VTextField, {
                                      modelValue: __props.defaultsDraft.max_download_concurrent,
                                      "onUpdate:modelValue": _cache[67] || (_cache[67] = $event => ((__props.defaultsDraft.max_download_concurrent) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "同时下载数上限",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VTextField, {
                                      modelValue: __props.defaultsDraft.top_n,
                                      "onUpdate:modelValue": _cache[68] || (_cache[68] = $event => ((__props.defaultsDraft.top_n) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "候选 TopN",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VTextField, {
                                      modelValue: __props.defaultsDraft.browse_pages,
                                      "onUpdate:modelValue": _cache[69] || (_cache[69] = $event => ((__props.defaultsDraft.browse_pages) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "每轮翻页数",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VTextField, {
                                      modelValue: __props.defaultsDraft.seen_cooldown_hours,
                                      "onUpdate:modelValue": _cache[70] || (_cache[70] = $event => ((__props.defaultsDraft.seen_cooldown_hours) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      label: "候选去重冷却（小时）",
                                      variant: "outlined",
                                      density: "comfortable",
                                      "hide-details": ""
                                    }, null, 8 /* PROPS */, ["modelValue"])
                                  ])
                                ]),
                                _createElementVNode("div", _hoisted_117, [
                                  _createElementVNode("div", _hoisted_118, [
                                    _createVNode(_component_VIcon, { icon: "mdi-broom" }),
                                    _cache[220] || (_cache[220] = _createTextVNode(" 清理策略 ", -1 /* CACHED */))
                                  ]),
                                  _createElementVNode("div", _hoisted_119, [
                                    _createVNode(_component_VSwitch, {
                                      modelValue: __props.defaultsDraft.refill_when_empty,
                                      "onUpdate:modelValue": _cache[71] || (_cache[71] = $event => ((__props.defaultsDraft.refill_when_empty) = $event)),
                                      label: "清理后自动补种",
                                      color: "primary",
                                      "hide-details": "",
                                      inset: ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VSwitch, {
                                      modelValue: __props.defaultsDraft.cleanup_no_progress,
                                      "onUpdate:modelValue": _cache[72] || (_cache[72] = $event => ((__props.defaultsDraft.cleanup_no_progress) = $event)),
                                      label: "清理无进度种子",
                                      color: "primary",
                                      "hide-details": "",
                                      inset: ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VSwitch, {
                                      modelValue: __props.defaultsDraft.cleanup_slow_progress,
                                      "onUpdate:modelValue": _cache[73] || (_cache[73] = $event => ((__props.defaultsDraft.cleanup_slow_progress) = $event)),
                                      label: "清理过慢种子",
                                      color: "primary",
                                      "hide-details": "",
                                      inset: ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VSwitch, {
                                      modelValue: __props.defaultsDraft.purge_unfree_incomplete,
                                      "onUpdate:modelValue": _cache[74] || (_cache[74] = $event => ((__props.defaultsDraft.purge_unfree_incomplete) = $event)),
                                      label: "清理「已非免费」未下完种子",
                                      color: "primary",
                                      "hide-details": "",
                                      inset: ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VSwitch, {
                                      modelValue: __props.defaultsDraft.auto_resume_paused,
                                      "onUpdate:modelValue": _cache[75] || (_cache[75] = $event => ((__props.defaultsDraft.auto_resume_paused) = $event)),
                                      label: "自动恢复被暂停种子",
                                      color: "primary",
                                      "hide-details": "",
                                      inset: ""
                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                    _createVNode(_component_VSwitch, {
                                      modelValue: __props.defaultsDraft.delete_files,
                                      "onUpdate:modelValue": _cache[76] || (_cache[76] = $event => ((__props.defaultsDraft.delete_files) = $event)),
                                      label: "删种同时删除文件",
                                      color: "primary",
                                      "hide-details": "",
                                      inset: ""
                                    }, null, 8 /* PROPS */, ["modelValue"])
                                  ])
                                ])
                              ]))
                            : (settingsTab.value === 'exam')
                              ? (_openBlock(), _createElementBlock("div", _hoisted_120, [
                                  _createElementVNode("div", _hoisted_121, [
                                    _createVNode(_component_VIcon, { icon: "mdi-school-outline" }),
                                    _cache[221] || (_cache[221] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                      _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "盯住各站新手考核，缺什么一键补")
                                    ], -1 /* CACHED */))
                                  ]),
                                  _createElementVNode("div", _hoisted_122, [
                                    _createElementVNode("div", _hoisted_123, [
                                      _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                                      _cache[222] || (_cache[222] = _createTextVNode(" 开关", -1 /* CACHED */))
                                    ]),
                                    _createElementVNode("div", _hoisted_124, [
                                      _createVNode(_component_VSwitch, {
                                        modelValue: __props.settingsDraft.exam_enabled,
                                        "onUpdate:modelValue": _cache[77] || (_cache[77] = $event => ((__props.settingsDraft.exam_enabled) = $event)),
                                        label: "启用「新手考核」（关闭则不抓取、不显示）",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                      _createVNode(_component_VSwitch, {
                                        modelValue: __props.settingsDraft.exam_include_pass,
                                        "onUpdate:modelValue": _cache[78] || (_cache[78] = $event => ((__props.settingsDraft.exam_include_pass) = $event)),
                                        label: "显示「已通过」的考核（默认只显示未通过）",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: "",
                                        disabled: !__props.settingsDraft.exam_enabled
                                      }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                                    ])
                                  ]),
                                  _createElementVNode("div", _hoisted_125, [
                                    _createElementVNode("div", _hoisted_126, [
                                      _createVNode(_component_VIcon, { icon: "mdi-web" }),
                                      _cache[223] || (_cache[223] = _createTextVNode(" 考核站点 ", -1 /* CACHED */))
                                    ]),
                                    _createElementVNode("div", _hoisted_127, [
                                      _createVNode(_component_VSelect, {
                                        modelValue: __props.settingsDraft.exam_sites,
                                        "onUpdate:modelValue": _cache[79] || (_cache[79] = $event => ((__props.settingsDraft.exam_sites) = $event)),
                                        items: __props.siteSelectItems,
                                        label: "考核站点",
                                        multiple: "",
                                        chips: "",
                                        "closable-chips": "",
                                        variant: "outlined",
                                        density: "comfortable",
                                        "hide-details": "",
                                        disabled: !__props.settingsDraft.exam_enabled
                                      }, null, 8 /* PROPS */, ["modelValue", "items", "disabled"]),
                                      _cache[224] || (_cache[224] = _createElementVNode("p", { class: "magicflow-settings-hint" }, "只盯你关心的站；不选＝全都盯", -1 /* CACHED */))
                                    ]),
                                    (!__props.settingsDraft.exam_enabled)
                                      ? (_openBlock(), _createElementBlock("p", _hoisted_128, [...(_cache[225] || (_cache[225] = [
                                          _createTextVNode(" 当前处于", -1 /* CACHED */),
                                          _createElementVNode("strong", null, "关闭", -1 /* CACHED */),
                                          _createTextVNode("状态：不会去抓考核，也不会做任何额外请求。 ", -1 /* CACHED */)
                                        ]))]))
                                      : _createCommentVNode("v-if", true)
                                  ])
                                ]))
                              : (settingsTab.value === 'signin')
                                ? (_openBlock(), _createElementBlock("div", _hoisted_129, [
                                    _createElementVNode("div", _hoisted_130, [
                                      _createElementVNode("span", _hoisted_131, [
                                        _createVNode(_component_VIcon, {
                                          icon: "mdi-calendar-check-outline",
                                          size: "20"
                                        })
                                      ]),
                                      _createElementVNode("div", _hoisted_132, [
                                        _createElementVNode("div", _hoisted_133, [
                                          _cache[226] || (_cache[226] = _createElementVNode("span", null, "站点签到 / 模拟登录", -1 /* CACHED */)),
                                          _createVNode(_component_VChip, {
                                            size: "small",
                                            variant: "tonal",
                                            color: __props.settingsDraft.signin_enabled ? 'success' : 'grey'
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(__props.settingsDraft.signin_enabled ? '已启用' : '已关闭'), 1 /* TEXT */)
                                            ]),
                                            _: 1 /* STABLE */
                                          }, 8 /* PROPS */, ["color"])
                                        ]),
                                        _cache[227] || (_cache[227] = _createElementVNode("div", { class: "magicflow-signin-hero__desc" }, " 勾选站点即可，其余全自动完成。 ", -1 /* CACHED */))
                                      ])
                                    ]),
                                    _createElementVNode("div", _hoisted_134, [
                                      _createElementVNode("div", _hoisted_135, [
                                        _createVNode(_component_VIcon, {
                                          icon: "mdi-toggle-switch-outline",
                                          size: "16"
                                        }),
                                        _cache[228] || (_cache[228] = _createTextVNode(" 开关", -1 /* CACHED */))
                                      ]),
                                      _createElementVNode("div", _hoisted_136, [
                                        _createVNode(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.signin_enabled,
                                          "onUpdate:modelValue": _cache[80] || (_cache[80] = $event => ((__props.settingsDraft.signin_enabled) = $event)),
                                          label: "启用站点签到 / 模拟登录",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: "",
                                          density: "comfortable"
                                        }, null, 8 /* PROPS */, ["modelValue"]),
                                        _createVNode(_component_VSwitch, {
                                          modelValue: __props.settingsDraft.signin_notify,
                                          "onUpdate:modelValue": _cache[81] || (_cache[81] = $event => ((__props.settingsDraft.signin_notify) = $event)),
                                          label: "结果推送通知",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: "",
                                          density: "comfortable",
                                          disabled: !__props.settingsDraft.signin_enabled
                                        }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                                      ])
                                    ]),
                                    _createElementVNode("div", _hoisted_137, [
                                      _createElementVNode("div", _hoisted_138, [
                                        _createVNode(_component_VIcon, {
                                          icon: "mdi-web",
                                          size: "16"
                                        }),
                                        _cache[229] || (_cache[229] = _createTextVNode(" 站点选择（勾选即生效）", -1 /* CACHED */))
                                      ]),
                                      _createElementVNode("div", _hoisted_139, [
                                        _createElementVNode("div", _hoisted_140, [
                                          _createVNode(_component_VSelect, {
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
                                          }, null, 8 /* PROPS */, ["modelValue", "items"]),
                                          _createElementVNode("span", _hoisted_141, "已选 " + _toDisplayString((__props.settingsDraft.signin_sites || []).length) + " 个站点", 1 /* TEXT */)
                                        ]),
                                        _createElementVNode("div", _hoisted_142, [
                                          _createVNode(_component_VSelect, {
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
                                          }, null, 8 /* PROPS */, ["modelValue", "items"]),
                                          _createElementVNode("span", _hoisted_143, "已选 " + _toDisplayString((__props.settingsDraft.signin_login_sites || []).length) + " 个站点 · 保活 Cookie + 刷新站点数据", 1 /* TEXT */)
                                        ])
                                      ])
                                    ]),
                                    _createElementVNode("div", _hoisted_144, [
                                      _createVNode(_component_VBtn, {
                                        size: "small",
                                        color: "primary",
                                        variant: "tonal",
                                        "prepend-icon": "mdi-chart-box-outline",
                                        onClick: _cache[84] || (_cache[84] = $event => (emit('open-signin')))
                                      }, {
                                        default: _withCtx(() => [...(_cache[230] || (_cache[230] = [
                                          _createTextVNode("查看签到报表", -1 /* CACHED */)
                                        ]))]),
                                        _: 1 /* STABLE */
                                      })
                                    ])
                                  ]))
                                : (settingsTab.value === 'live')
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_145, [
                                      _createElementVNode("div", _hoisted_146, [
                                        _createVNode(_component_VIcon, { icon: "mdi-access-point" }),
                                        _cache[231] || (_cache[231] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                          _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "把站点数据从「6 小时前」变成「刚刚」")
                                        ], -1 /* CACHED */)),
                                        _cache[232] || (_cache[232] = _createElementVNode("span", { class: "magicflow-settings-lede__tag is-warn" }, "会耗 PV", -1 /* CACHED */))
                                      ]),
                                      _createElementVNode("div", _hoisted_147, [
                                        _createElementVNode("div", _hoisted_148, [
                                          _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                                          _cache[233] || (_cache[233] = _createTextVNode(" 实时采样", -1 /* CACHED */))
                                        ]),
                                        _createElementVNode("div", _hoisted_149, [
                                          _createVNode(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.live_enabled,
                                            "onUpdate:modelValue": _cache[85] || (_cache[85] = $event => ((__props.settingsDraft.live_enabled) = $event)),
                                            label: "启用站点实时数据 + 流量监控",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8 /* PROPS */, ["modelValue"]),
                                          _createVNode(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.live_notify,
                                            "onUpdate:modelValue": _cache[86] || (_cache[86] = $event => ((__props.settingsDraft.live_notify) = $event)),
                                            label: "命中告警时推送通知",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: "",
                                            disabled: !__props.settingsDraft.live_enabled
                                          }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                          _createVNode(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.live_auto_stop,
                                            "onUpdate:modelValue": _cache[87] || (_cache[87] = $event => ((__props.settingsDraft.live_auto_stop) = $event)),
                                            label: "同时把该站「运行中」任务切「做种中」（只停调度）",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: "",
                                            disabled: !__props.settingsDraft.live_enabled
                                          }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                                        ]),
                                        _createElementVNode("div", _hoisted_150, [
                                          _createVNode(_component_VTextField, {
                                            modelValue: __props.settingsDraft.live_interval_minutes,
                                            "onUpdate:modelValue": _cache[88] || (_cache[88] = $event => ((__props.settingsDraft.live_interval_minutes) = $event)),
                                            modelModifiers: { number: true },
                                            type: "number",
                                            min: "1",
                                            label: "采样周期（分钟）",
                                            hint: "默认 4 分钟；太频繁站点吃不消",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8 /* PROPS */, ["modelValue"]),
                                          _createVNode(_component_VTextField, {
                                            modelValue: __props.settingsDraft.live_download_alert_mb,
                                            "onUpdate:modelValue": _cache[89] || (_cache[89] = $event => ((__props.settingsDraft.live_download_alert_mb) = $event)),
                                            modelModifiers: { number: true },
                                            type: "number",
                                            min: "1",
                                            label: "下载增长告警阈值（MB/分钟）",
                                            hint: "超过则告警；默认 50",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8 /* PROPS */, ["modelValue"]),
                                          _createVNode(_component_VTextField, {
                                            modelValue: __props.settingsDraft.live_ratio_target,
                                            "onUpdate:modelValue": _cache[90] || (_cache[90] = $event => ((__props.settingsDraft.live_ratio_target) = $event)),
                                            modelModifiers: { number: true },
                                            type: "number",
                                            min: "0",
                                            step: "0.05",
                                            label: "分享率目标线",
                                            hint: "低于则告警并算缺口；0 = 不检查",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8 /* PROPS */, ["modelValue"])
                                        ])
                                      ]),
                                      _createElementVNode("div", _hoisted_151, [
                                        _createElementVNode("div", _hoisted_152, [
                                          _createVNode(_component_VIcon, { icon: "mdi-shield-alert-outline" }),
                                          _cache[234] || (_cache[234] = _createTextVNode(" 流量兜底 ", -1 /* CACHED */))
                                        ]),
                                        _cache[235] || (_cache[235] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                          _createTextVNode(" 三处都会核对："),
                                          _createElementVNode("em", null, "任务内"),
                                          _createTextVNode("回种子详情页核对（开关在任务「高级」里，受本总开关约束）、 "),
                                          _createElementVNode("em", null, "全局"),
                                          _createTextVNode("用站点「正在下载」列表核对、"),
                                          _createElementVNode("em", null, "取种期间"),
                                          _createTextVNode("核对来源站。 ")
                                        ], -1 /* CACHED */)),
                                        _createElementVNode("div", _hoisted_153, [
                                          _createVNode(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.promo_guard,
                                            "onUpdate:modelValue": _cache[91] || (_cache[91] = $event => ((__props.settingsDraft.promo_guard) = $event)),
                                            label: "启用流量兜底（关掉＝下面三项只告警、不动手）",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8 /* PROPS */, ["modelValue"]),
                                          _createVNode(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.live_kill_unfree,
                                            "onUpdate:modelValue": _cache[92] || (_cache[92] = $event => ((__props.settingsDraft.live_kill_unfree) = $event)),
                                            disabled: !__props.settingsDraft.promo_guard,
                                            label: "全局：下载量异常增长时，干掉站点里非免费的下载",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                          _createVNode(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.live_kill_delete_files,
                                            "onUpdate:modelValue": _cache[93] || (_cache[93] = $event => ((__props.settingsDraft.live_kill_delete_files) = $event)),
                                            disabled: !__props.settingsDraft.promo_guard || !__props.settingsDraft.live_kill_unfree,
                                            label: "干掉时连文件一起删（只动名称+体积对得上的下载中种）",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                          _createVNode(_component_VSwitch, {
                                            modelValue: __props.settingsDraft.crossseed_guard,
                                            "onUpdate:modelValue": _cache[94] || (_cache[94] = $event => ((__props.settingsDraft.crossseed_guard) = $event)),
                                            disabled: !__props.settingsDraft.promo_guard,
                                            label: "取种期间核对来源站免费状态；判错就删种并拉黑（建议开启）",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                                        ]),
                                        _createElementVNode("div", _hoisted_154, [
                                          _createVNode(_component_VTextField, {
                                            modelValue: __props.settingsDraft.crossseed_guard_pct,
                                            "onUpdate:modelValue": _cache[95] || (_cache[95] = $event => ((__props.settingsDraft.crossseed_guard_pct) = $event)),
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
                                          }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                          _createVNode(_component_VTextField, {
                                            modelValue: __props.settingsDraft.crossseed_guard_min_mb,
                                            "onUpdate:modelValue": _cache[96] || (_cache[96] = $event => ((__props.settingsDraft.crossseed_guard_min_mb) = $event)),
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
                                          }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                          _createVNode(_component_VTextField, {
                                            modelValue: __props.settingsDraft.crossseed_guard_interval_min,
                                            "onUpdate:modelValue": _cache[97] || (_cache[97] = $event => ((__props.settingsDraft.crossseed_guard_interval_min) = $event)),
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
                                          }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                                        ])
                                      ]),
                                      (__props.siteLiveAlerts.length)
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_155, [
                                            _createElementVNode("div", _hoisted_156, "当前「" + _toDisplayString(__props.selectedTask?.name) + "」站点告警", 1 /* TEXT */),
                                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.siteLiveAlerts, (alert, idx) => {
                                              return (_openBlock(), _createElementBlock("div", {
                                                key: `live-cfg-${idx}`,
                                                class: _normalizeClass(["magicflow-live-alert", `magicflow-live-alert--${alert.level || 'info'}`])
                                              }, _toDisplayString(alert.text), 3 /* TEXT, CLASS */))
                                            }), 128 /* KEYED_FRAGMENT */))
                                          ]))
                                        : _createCommentVNode("v-if", true)
                                    ]))
                                  : (settingsTab.value === 'recommend')
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_157, [
                                        _createElementVNode("div", _hoisted_158, [
                                          _createVNode(_component_VIcon, { icon: "mdi-star-shooting-outline" }),
                                          _cache[236] || (_cache[236] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                            _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "刷流时顺带挑出值得收藏的片")
                                          ], -1 /* CACHED */)),
                                          _cache[237] || (_cache[237] = _createElementVNode("span", { class: "magicflow-settings-lede__tag" }, "受闸门保护", -1 /* CACHED */))
                                        ]),
                                        _createElementVNode("div", _hoisted_159, [
                                          _createElementVNode("div", _hoisted_160, [
                                            _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                                            _cache[238] || (_cache[238] = _createTextVNode(" 开关", -1 /* CACHED */))
                                          ]),
                                          _createElementVNode("div", _hoisted_161, [
                                            _createVNode(_component_VSwitch, {
                                              modelValue: __props.settingsDraft.recommend_enabled,
                                              "onUpdate:modelValue": _cache[98] || (_cache[98] = $event => ((__props.settingsDraft.recommend_enabled) = $event)),
                                              label: "启用推荐甄别",
                                              color: "primary",
                                              "hide-details": "",
                                              inset: ""
                                            }, null, 8 /* PROPS */, ["modelValue"]),
                                            _createVNode(_component_VSwitch, {
                                              modelValue: __props.settingsDraft.recommend_require_chart,
                                              "onUpdate:modelValue": _cache[99] || (_cache[99] = $event => ((__props.settingsDraft.recommend_require_chart) = $event)),
                                              label: "榜单 / 热映 / 订阅命中也算达标（与评分为「或」）",
                                              color: "primary",
                                              "hide-details": "",
                                              inset: "",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                            _createVNode(_component_VSwitch, {
                                              modelValue: __props.settingsDraft.recommend_auto_import,
                                              "onUpdate:modelValue": _cache[100] || (_cache[100] = $event => ((__props.settingsDraft.recommend_auto_import) = $event)),
                                              label: "确认后自动整理入库",
                                              color: "primary",
                                              "hide-details": "",
                                              inset: "",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                            _createVNode(_component_VSwitch, {
                                              modelValue: __props.settingsDraft.recommend_notify,
                                              "onUpdate:modelValue": _cache[101] || (_cache[101] = $event => ((__props.settingsDraft.recommend_notify) = $event)),
                                              label: "发现推荐时通知",
                                              color: "primary",
                                              "hide-details": "",
                                              inset: "",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                                          ])
                                        ]),
                                        _createElementVNode("div", _hoisted_162, [
                                          _createElementVNode("div", _hoisted_163, [
                                            _createVNode(_component_VIcon, { icon: "mdi-gauge" }),
                                            _cache[239] || (_cache[239] = _createTextVNode(" 门槛与回收 ", -1 /* CACHED */))
                                          ]),
                                          _createElementVNode("div", _hoisted_164, [
                                            _createVNode(_component_VTextField, {
                                              modelValue: __props.settingsDraft.recommend_min_rating,
                                              "onUpdate:modelValue": _cache[102] || (_cache[102] = $event => ((__props.settingsDraft.recommend_min_rating) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              max: "10",
                                              step: "0.1",
                                              label: "评分门槛（高于）",
                                              hint: "评分高于该值才推荐（默认 7.5）",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                            _createVNode(_component_VTextField, {
                                              modelValue: __props.settingsDraft.recommend_expire_days,
                                              "onUpdate:modelValue": _cache[103] || (_cache[103] = $event => ((__props.settingsDraft.recommend_expire_days) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              step: "1",
                                              label: "推荐过期天数",
                                              hint: "超过该天数仍未确认即视为过期（0＝不过期）",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                            _createVNode(_component_VTextField, {
                                              modelValue: __props.settingsDraft.recommend_temp_ttl_days,
                                              "onUpdate:modelValue": _cache[104] || (_cache[104] = $event => ((__props.settingsDraft.recommend_temp_ttl_days) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              step: "1",
                                              label: "临时种 TTL（天）",
                                              hint: "未入选推荐的刷流临时种，超过该天数回收",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "disabled"]),
                                            _createVNode(_component_VTextField, {
                                              modelValue: __props.settingsDraft.recommend_disk_min_free_gb,
                                              "onUpdate:modelValue": _cache[105] || (_cache[105] = $event => ((__props.settingsDraft.recommend_disk_min_free_gb) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              step: "1",
                                              label: "磁盘余量下限（GB）",
                                              hint: "剩余空间低于该值时推荐立即过期",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                                          ])
                                        ]),
                                        _createElementVNode("div", _hoisted_165, [
                                          _createElementVNode("div", _hoisted_166, [
                                            _createVNode(_component_VIcon, { icon: "mdi-source-branch" }),
                                            _cache[240] || (_cache[240] = _createTextVNode(" 评分来源与标签 ", -1 /* CACHED */))
                                          ]),
                                          _createElementVNode("div", _hoisted_167, [
                                            _createVNode(_component_VSelect, {
                                              modelValue: __props.settingsDraft.recommend_rating_source,
                                              "onUpdate:modelValue": _cache[106] || (_cache[106] = $event => ((__props.settingsDraft.recommend_rating_source) = $event)),
                                              items: _unref(ratingSourceItems),
                                              "item-title": "title",
                                              "item-value": "value",
                                              label: "评分来源",
                                              hint: "豆瓣优先走本地服务 magicflow-douban",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "items", "disabled"]),
                                            _createVNode(_component_VSelect, {
                                              modelValue: __props.settingsDraft.recommend_episode_policy,
                                              "onUpdate:modelValue": _cache[107] || (_cache[107] = $event => ((__props.settingsDraft.recommend_episode_policy) = $event)),
                                              items: _unref(episodePolicyItems),
                                              "item-title": "title",
                                              "item-value": "value",
                                              label: "单集策略",
                                              hint: "默认不自动推荐，要整季请点推荐列表的「订阅整季」",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "items", "disabled"]),
                                            _createVNode(_component_VTextField, {
                                              modelValue: __props.settingsDraft.recommend_douban_service_url,
                                              "onUpdate:modelValue": _cache[108] || (_cache[108] = $event => ((__props.settingsDraft.recommend_douban_service_url) = $event)),
                                              label: "豆瓣服务地址",
                                              placeholder: "http://magicflow-douban:18789",
                                              hint: "留空用默认；本地查询不限流",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable"
                                            }, null, 8 /* PROPS */, ["modelValue"]),
                                            _createVNode(_component_VTextField, {
                                              modelValue: __props.settingsDraft.recommend_tag,
                                              "onUpdate:modelValue": _cache[109] || (_cache[109] = $event => ((__props.settingsDraft.recommend_tag) = $event)),
                                              label: "推荐标签",
                                              hint: "推荐资源单独打的标签，默认「魔流-推荐」",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable",
                                              disabled: !__props.settingsDraft.recommend_enabled
                                            }, null, 8 /* PROPS */, ["modelValue", "disabled"])
                                          ])
                                        ])
                                      ]))
                                    : (settingsTab.value === 'rules')
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_168, [
                                          _createElementVNode("div", _hoisted_169, [
                                            _createVNode(_component_VIcon, { icon: "mdi-shield-check-outline" }),
                                            _cache[241] || (_cache[241] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                              _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "全站 H&R 的唯一入口")
                                            ], -1 /* CACHED */)),
                                            _cache[242] || (_cache[242] = _createElementVNode("span", { class: "magicflow-settings-lede__tag is-warn" }, "影响开账", -1 /* CACHED */))
                                          ]),
                                          _createElementVNode("div", _hoisted_170, [
                                            _createElementVNode("div", _hoisted_171, [
                                              _createVNode(_component_VIcon, { icon: "mdi-radar" }),
                                              _cache[243] || (_cache[243] = _createTextVNode(" 自动探测", -1 /* CACHED */))
                                            ]),
                                            _createElementVNode("div", _hoisted_172, [
                                              _createVNode(_component_VSwitch, {
                                                modelValue: __props.settingsDraft.rules_auto_refresh,
                                                "onUpdate:modelValue": _cache[110] || (_cache[110] = $event => ((__props.settingsDraft.rules_auto_refresh) = $event)),
                                                label: "每周自动逐站探测规则并入库",
                                                color: "primary",
                                                "hide-details": "",
                                                inset: ""
                                              }, null, 8 /* PROPS */, ["modelValue"])
                                            ]),
                                            _cache[244] || (_cache[244] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                              _createTextVNode(" 到点才跑：每 10 分钟醒来看一眼，满 7 天才真探一次；"),
                                              _createElementVNode("strong", null, "重启/更新不会把周期清零"),
                                              _createTextVNode("， 探测失败按 30 分钟 → 6 小时退避重试（不再一次失败干等一周）。 ")
                                            ], -1 /* CACHED */))
                                          ]),
                                          _createElementVNode("div", _hoisted_173, [
                                            _createElementVNode("div", _hoisted_174, [
                                              _createVNode(_component_VIcon, { icon: "mdi-tune" }),
                                              _cache[245] || (_cache[245] = _createTextVNode(" 全局默认 ", -1 /* CACHED */))
                                            ]),
                                            _createElementVNode("div", _hoisted_175, [
                                              _createVNode(_component_VTextField, {
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
                                              }, null, 8 /* PROPS */, ["modelValue"]),
                                              _createVNode(_component_VTextField, {
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
                                              }, null, 8 /* PROPS */, ["modelValue"]),
                                              _createVNode(_component_VTextField, {
                                                modelValue: __props.settingsDraft.hr_deadline_warn_hours,
                                                "onUpdate:modelValue": _cache[113] || (_cache[113] = $event => ((__props.settingsDraft.hr_deadline_warn_hours) = $event)),
                                                modelModifiers: { number: true },
                                                type: "number",
                                                step: "1",
                                                min: "0",
                                                label: "H&R 账单临期阈值（小时）",
                                                hint: "未达标且距期限 ≤ 该值 → 账单标 at_risk（默认 48）",
                                                "persistent-hint": "",
                                                variant: "outlined",
                                                density: "comfortable"
                                              }, null, 8 /* PROPS */, ["modelValue"]),
                                              _createVNode(_component_VTextField, {
                                                modelValue: __props.settingsDraft.hr_complete_ratio,
                                                "onUpdate:modelValue": _cache[114] || (_cache[114] = $event => ((__props.settingsDraft.hr_complete_ratio) = $event)),
                                                modelModifiers: { number: true },
                                                type: "number",
                                                step: "0.001",
                                                min: "0",
                                                max: "1",
                                                label: "H&R 完成度阈值（全局默认）",
                                                hint: "达到该进度才计 H&R（默认 99.9%）；分站可在下表覆盖",
                                                "persistent-hint": "",
                                                variant: "outlined",
                                                density: "comfortable"
                                              }, null, 8 /* PROPS */, ["modelValue"])
                                            ])
                                          ]),
                                          _createElementVNode("div", _hoisted_176, [
                                            _createElementVNode("div", _hoisted_177, [
                                              _createVNode(_component_VIcon, { icon: "mdi-seed-outline" }),
                                              _cache[246] || (_cache[246] = _createTextVNode(" 来源份保护与回收", -1 /* CACHED */))
                                            ]),
                                            _createElementVNode("div", _hoisted_178, [
                                              _createVNode(_component_VSwitch, {
                                                modelValue: __props.settingsDraft.crossseed_guard_keep_seed,
                                                "onUpdate:modelValue": _cache[115] || (_cache[115] = $event => ((__props.settingsDraft.crossseed_guard_keep_seed) = $event)),
                                                label: "来源份 H&R 保护（义务工时内不得删/改标签）",
                                                color: "primary",
                                                "hide-details": "",
                                                inset: ""
                                              }, null, 8 /* PROPS */, ["modelValue"]),
                                              _createVNode(_component_VSwitch, {
                                                modelValue: __props.settingsDraft.crossseed_reclaim,
                                                "onUpdate:modelValue": _cache[116] || (_cache[116] = $event => ((__props.settingsDraft.crossseed_reclaim) = $event)),
                                                label: "H&R 期满后回收来源份（只删种子不删文件）",
                                                color: "warning",
                                                "hide-details": "",
                                                inset: ""
                                              }, null, 8 /* PROPS */, ["modelValue"])
                                            ])
                                          ]),
                                          _createElementVNode("div", _hoisted_179, [
                                            _createElementVNode("div", _hoisted_180, [
                                              _createVNode(_component_VIcon, { icon: "mdi-table-cog" }),
                                              _cache[247] || (_cache[247] = _createTextVNode(" 逐站规则 ", -1 /* CACHED */)),
                                              _createElementVNode("span", _hoisted_181, "共 " + _toDisplayString(__props.siteRules.length) + " 条", 1 /* TEXT */)
                                            ]),
                                            _createElementVNode("div", _hoisted_182, [
                                              _createVNode(_component_VBtn, {
                                                size: "small",
                                                color: "primary",
                                                variant: "tonal",
                                                loading: __props.rulesProbing,
                                                onClick: _cache[117] || (_cache[117] = $event => (emit('probe-rules')))
                                              }, {
                                                default: _withCtx(() => [
                                                  _createVNode(_component_VIcon, {
                                                    start: "",
                                                    size: "small"
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[248] || (_cache[248] = [
                                                      _createTextVNode("mdi-download-network-outline", -1 /* CACHED */)
                                                    ]))]),
                                                    _: 1 /* STABLE */
                                                  }),
                                                  _cache[249] || (_cache[249] = _createTextVNode("逐站拉取（探测页面） ", -1 /* CACHED */))
                                                ]),
                                                _: 1 /* STABLE */
                                              }, 8 /* PROPS */, ["loading"]),
                                              _createVNode(_component_VBtn, {
                                                size: "small",
                                                variant: "text",
                                                disabled: __props.rulesLoading,
                                                onClick: _cache[118] || (_cache[118] = $event => (emit('refresh-rules')))
                                              }, {
                                                default: _withCtx(() => [...(_cache[250] || (_cache[250] = [
                                                  _createTextVNode("按 MP 配置补全", -1 /* CACHED */)
                                                ]))]),
                                                _: 1 /* STABLE */
                                              }, 8 /* PROPS */, ["disabled"]),
                                              _createElementVNode("span", _hoisted_183, [
                                                _createTextVNode("上次自动探测：" + _toDisplayString(__props.rulesProbeState?.at ? _unref(fmtTs)(__props.rulesProbeState.at) : '从未探测'), 1 /* TEXT */),
                                                (__props.rulesProbeState?.fail)
                                                  ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                      _createTextVNode("（连续失败 " + _toDisplayString(__props.rulesProbeState.fail) + " 次，自动退避重试中）", 1 /* TEXT */)
                                                    ], 64 /* STABLE_FRAGMENT */))
                                                  : _createCommentVNode("v-if", true)
                                              ])
                                            ]),
                                            (__props.rulesProbing)
                                              ? (_openBlock(), _createElementBlock("p", _hoisted_184, "正在逐站抓取规则页（每站 1~2 个请求，随机歇 1.5~3.5 秒）…"))
                                              : _createCommentVNode("v-if", true),
                                            _createElementVNode("div", _hoisted_185, [
                                              _cache[259] || (_cache[259] = _createElementVNode("div", { class: "magicflow-rules-row magicflow-rules-row--head" }, [
                                                _createElementVNode("span", null, "站点 · 来源"),
                                                _createElementVNode("span", null, "H&R"),
                                                _createElementVNode("span", null, "达标小时"),
                                                _createElementVNode("span", null, "完成度"),
                                                _createElementVNode("span")
                                              ], -1 /* CACHED */)),
                                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.siteRules, (row) => {
                                                return (_openBlock(), _createElementBlock("div", {
                                                  key: row.domain,
                                                  class: "magicflow-rules-row"
                                                }, [
                                                  _createElementVNode("span", {
                                                    class: "magicflow-rules-row__name",
                                                    title: row.domain
                                                  }, [
                                                    _createElementVNode("b", null, _toDisplayString(row.site_name || row.domain), 1 /* TEXT */),
                                                    (!row.in_library)
                                                      ? (_openBlock(), _createElementBlock("em", _hoisted_187, "未入库"))
                                                      : _createCommentVNode("v-if", true),
                                                    (row.exam_avg_hours)
                                                      ? (_openBlock(), _createElementBlock("em", {
                                                          key: 1,
                                                          title: row.exam_evidence || '站点考核的平均做种要求（不是 H&R）'
                                                        }, "考核" + _toDisplayString(row.exam_avg_hours) + "h", 9 /* TEXT, PROPS */, _hoisted_188))
                                                      : _createCommentVNode("v-if", true),
                                                    _createCommentVNode(" ★ 任务 129：标了「无 H&R」的站不再显示期限（旧数据显示 hr=false 还挂着 360h，自相矛盾） "),
                                                    _createElementVNode("i", {
                                                      title: row.evidence || ''
                                                    }, [
                                                      _createTextVNode(_toDisplayString(_unref(ruleSourceText)(row)), 1 /* TEXT */),
                                                      (row.seed_cap)
                                                        ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                            _createTextVNode(" · 上限" + _toDisplayString(row.seed_cap), 1 /* TEXT */)
                                                          ], 64 /* STABLE_FRAGMENT */))
                                                        : _createCommentVNode("v-if", true),
                                                      (row.seed_window_hours && row.hr !== false)
                                                        ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                                            _createTextVNode(" · 期限" + _toDisplayString(row.seed_window_hours) + "h", 1 /* TEXT */)
                                                          ], 64 /* STABLE_FRAGMENT */))
                                                        : _createCommentVNode("v-if", true),
                                                      (row.seed_window_hours_seen != null && row.hr !== false)
                                                        ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                                                            _createTextVNode(" · 见" + _toDisplayString(row.seed_window_hours_seen) + "h", 1 /* TEXT */)
                                                          ], 64 /* STABLE_FRAGMENT */))
                                                        : _createCommentVNode("v-if", true)
                                                    ], 8 /* PROPS */, _hoisted_189)
                                                  ], 8 /* PROPS */, _hoisted_186),
                                                  _createElementVNode("span", _hoisted_190, [
                                                    (row.hr === true)
                                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                                          key: 0,
                                                          size: "x-small",
                                                          color: "error",
                                                          variant: "tonal"
                                                        }, {
                                                          default: _withCtx(() => [...(_cache[251] || (_cache[251] = [
                                                            _createTextVNode("有", -1 /* CACHED */)
                                                          ]))]),
                                                          _: 1 /* STABLE */
                                                        }))
                                                      : (row.hr === false)
                                                        ? (_openBlock(), _createBlock(_component_VChip, {
                                                            key: 1,
                                                            size: "x-small",
                                                            color: "success",
                                                            variant: "tonal"
                                                          }, {
                                                            default: _withCtx(() => [...(_cache[252] || (_cache[252] = [
                                                              _createTextVNode("无", -1 /* CACHED */)
                                                            ]))]),
                                                            _: 1 /* STABLE */
                                                          }))
                                                        : (_openBlock(), _createBlock(_component_VChip, {
                                                            key: 2,
                                                            size: "x-small",
                                                            variant: "tonal"
                                                          }, {
                                                            default: _withCtx(() => [...(_cache[253] || (_cache[253] = [
                                                              _createTextVNode("未知", -1 /* CACHED */)
                                                            ]))]),
                                                            _: 1 /* STABLE */
                                                          })),
                                                    _createCommentVNode(" ★ 只对「手填覆盖」给恢复入口：来源已是内置/探测/收件箱时，恢复是语义 no-op\n                       （回落后结论相同），旧条件只判 hr===false → 按钮永远在、点了看不出变化。 "),
                                                    (row.hr === false && row.hr_source === 'manual')
                                                      ? (_openBlock(), _createBlock(_component_VBtn, {
                                                          key: 3,
                                                          size: "x-small",
                                                          variant: "text",
                                                          disabled: __props.rulesProbing,
                                                          title: "恢复为探测/内置判定（清除手动标记）",
                                                          onClick: $event => (emit('set-rule-hr', row, 'unknown'))
                                                        }, {
                                                          default: _withCtx(() => [...(_cache[254] || (_cache[254] = [
                                                            _createTextVNode("恢复", -1 /* CACHED */)
                                                          ]))]),
                                                          _: 1 /* STABLE */
                                                        }, 8 /* PROPS */, ["disabled", "onClick"]))
                                                      : (_openBlock(), _createElementBlock(_Fragment, { key: 4 }, [
                                                          _createVNode(_component_VBtn, {
                                                            size: "x-small",
                                                            variant: "text",
                                                            disabled: __props.rulesProbing,
                                                            title: "该站有 H&R：手动确认「有」并按当前时长保护",
                                                            onClick: $event => (emit('set-rule-hr', row, '1'))
                                                          }, {
                                                            default: _withCtx(() => [...(_cache[255] || (_cache[255] = [
                                                              _createTextVNode("标有", -1 /* CACHED */)
                                                            ]))]),
                                                            _: 1 /* STABLE */
                                                          }, 8 /* PROPS */, ["disabled", "onClick"]),
                                                          _createVNode(_component_VBtn, {
                                                            size: "x-small",
                                                            variant: "text",
                                                            disabled: __props.rulesProbing,
                                                            title: "该站没有 H&R：直接标无，不做保种保护",
                                                            onClick: $event => (emit('set-rule-hr', row, '0'))
                                                          }, {
                                                            default: _withCtx(() => [...(_cache[256] || (_cache[256] = [
                                                              _createTextVNode("标无", -1 /* CACHED */)
                                                            ]))]),
                                                            _: 1 /* STABLE */
                                                          }, 8 /* PROPS */, ["disabled", "onClick"])
                                                        ], 64 /* STABLE_FRAGMENT */))
                                                  ]),
                                                  _createElementVNode("span", _hoisted_191, [
                                                    _createVNode(_component_VTextField, {
                                                      "model-value": row.hr === false ? '' : (row.seed_need_hours ?? ''),
                                                      type: "number",
                                                      min: "0",
                                                      max: "720",
                                                      step: "1",
                                                      density: "compact",
                                                      variant: "outlined",
                                                      "hide-details": "",
                                                      label: "达标小时",
                                                      disabled: row.hr === false,
                                                      placeholder: row.hr === false ? '无 H&R' : '未探明',
                                                      title: row.hr === false
                      ? '该站已标「无 H&R」，不设达标小时'
                      : 'H&R 要求做满的做种小时（判结清用的就是它）。留空＝未探明，按 24h 保守兜底',
                                                      onChange: $event => (emit('set-rule-hours', row, $event.target.value))
                                                    }, null, 8 /* PROPS */, ["model-value", "disabled", "placeholder", "title", "onChange"])
                                                  ]),
                                                  _createElementVNode("span", _hoisted_192, [
                                                    _createVNode(_component_VTextField, {
                                                      "model-value": row.complete_ratio,
                                                      type: "number",
                                                      min: "0",
                                                      max: "1",
                                                      step: "0.001",
                                                      density: "compact",
                                                      variant: "outlined",
                                                      "hide-details": "",
                                                      label: "完成度",
                                                      placeholder: "跟全局",
                                                      title: row.complete_ratio == null ? '未覆盖，用全局「H&R 完成度阈值」' : '站点级覆盖（进度达到该值才计 H&R）',
                                                      onChange: $event => (emit('set-rule-ratio', row, $event.target.value))
                                                    }, null, 8 /* PROPS */, ["model-value", "title", "onChange"])
                                                  ]),
                                                  _createElementVNode("span", _hoisted_193, [
                                                    (row.rule_url)
                                                      ? (_openBlock(), _createBlock(_component_VBtn, {
                                                          key: 0,
                                                          size: "x-small",
                                                          variant: "text",
                                                          icon: "",
                                                          href: String(row.rule_url).split(/\s+/)[0],
                                                          target: "_blank",
                                                          rel: "noopener",
                                                          title: '规则地址（来自收件箱欢迎短讯）：' + row.rule_url
                                                        }, {
                                                          default: _withCtx(() => [
                                                            _createVNode(_component_VIcon, { size: "x-small" }, {
                                                              default: _withCtx(() => [...(_cache[257] || (_cache[257] = [
                                                                _createTextVNode("mdi-link-variant", -1 /* CACHED */)
                                                              ]))]),
                                                              _: 1 /* STABLE */
                                                            })
                                                          ]),
                                                          _: 1 /* STABLE */
                                                        }, 8 /* PROPS */, ["href", "title"]))
                                                      : _createCommentVNode("v-if", true),
                                                    _createVNode(_component_VBtn, {
                                                      size: "x-small",
                                                      variant: "text",
                                                      disabled: __props.rulesProbing,
                                                      title: "只探测这一站",
                                                      onClick: $event => (emit('probe-rules', row.domain))
                                                    }, {
                                                      default: _withCtx(() => [...(_cache[258] || (_cache[258] = [
                                                        _createTextVNode("探测", -1 /* CACHED */)
                                                      ]))]),
                                                      _: 1 /* STABLE */
                                                    }, 8 /* PROPS */, ["disabled", "onClick"])
                                                  ])
                                                ]))
                                              }), 128 /* KEYED_FRAGMENT */))
                                            ]),
                                            _cache[260] || (_cache[260] = _createElementVNode("details", { class: "magicflow-rules-help" }, [
                                              _createElementVNode("summary", null, "怎么改 / 取值说明"),
                                              _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                                _createElementVNode("strong", null, "达标小时"),
                                                _createTextVNode("：H&R 要求做满多少小时（例：学校「10 天内做种 20 小时」→ 20）。 判结清读的就是它；留空＝未探明，按 24h 保守兜底。直接改 = 手填覆盖 （优先级：手填 > 探测 > 内置 > 全局默认）。该站标了「无 H&R」→ 此列禁用并清空。 ")
                                              ]),
                                              _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                                _createElementVNode("strong", null, "完成度"),
                                                _createTextVNode("：进度达到多少才算「下载完成」并开始计 H&R。"),
                                                _createElementVNode("strong", null, "留空 = 跟全局"),
                                                _createTextVNode(" （默认 0.999，下满才算）；某站若规定「下载中即计 H&R」→ 在该站填 "),
                                                _createElementVNode("code", null, "0.2"),
                                                _createTextVNode(" 之类。 ")
                                              ]),
                                              _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                                _createTextVNode(" 每个站只有两个时长数字："),
                                                _createElementVNode("strong", null, "达标小时"),
                                                _createTextVNode("（做满多少才算清，上面可改）与 "),
                                                _createElementVNode("strong", null, "期限"),
                                                _createTextVNode("（多久之内要做满，例：10 天，探测从规则原文写入，不在这里改）。 标「无 H&R」时两者一并清空。 ")
                                              ])
                                            ], -1 /* CACHED */))
                                          ])
                                        ]))
                                      : (settingsTab.value === 'tags')
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_194, [
                                            _createElementVNode("div", _hoisted_195, [
                                              _createVNode(_component_VIcon, { icon: "mdi-tag-multiple-outline" }),
                                              _cache[261] || (_cache[261] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                                _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "用标签把每个种子的状态写清楚")
                                              ], -1 /* CACHED */)),
                                              _cache[262] || (_cache[262] = _createElementVNode("span", { class: "magicflow-settings-lede__tag" }, "可自愈", -1 /* CACHED */))
                                            ]),
                                            _createElementVNode("div", _hoisted_196, [
                                              _createElementVNode("div", _hoisted_197, [
                                                _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                                                _cache[263] || (_cache[263] = _createTextVNode(" 标签模型", -1 /* CACHED */))
                                              ]),
                                              _createElementVNode("div", _hoisted_198, [
                                                _createVNode(_component_VSwitch, {
                                                  modelValue: __props.settingsDraft.tag_model_enabled,
                                                  "onUpdate:modelValue": _cache[119] || (_cache[119] = $event => ((__props.settingsDraft.tag_model_enabled) = $event)),
                                                  label: "启用标签模型（状态账本 + 魔流-站点-状态 标签）",
                                                  color: "primary",
                                                  "hide-details": "",
                                                  inset: ""
                                                }, null, 8 /* PROPS */, ["modelValue"]),
                                                _createVNode(_component_VSwitch, {
                                                  modelValue: __props.settingsDraft.show_qb_tags,
                                                  "onUpdate:modelValue": _cache[120] || (_cache[120] = $event => ((__props.settingsDraft.show_qb_tags) = $event)),
                                                  label: "往 qB 写标签（关=纯账本模式）",
                                                  color: "primary",
                                                  "hide-details": "",
                                                  inset: ""
                                                }, null, 8 /* PROPS */, ["modelValue"])
                                              ]),
                                              _createElementVNode("div", _hoisted_199, [
                                                _createVNode(_component_VTextField, {
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
                                                }, null, 8 /* PROPS */, ["modelValue"])
                                              ])
                                            ]),
                                            _createElementVNode("div", _hoisted_200, [
                                              _createElementVNode("div", _hoisted_201, [
                                                _createVNode(_component_VIcon, { icon: "mdi-filter-cog-outline" }),
                                                _cache[264] || (_cache[264] = _createTextVNode(" 静默分拣规则 ", -1 /* CACHED */))
                                              ]),
                                              _createElementVNode("div", _hoisted_202, [
                                                _cache[265] || (_cache[265] = _createElementVNode("div", { class: "magicflow-sort-rules__row magicflow-sort-rules__row--head" }, [
                                                  _createElementVNode("span", null, "规则"),
                                                  _createElementVNode("span", null, "阈值"),
                                                  _createElementVNode("span", null, "权重"),
                                                  _createElementVNode("span", null, "启用"),
                                                  _createElementVNode("span")
                                                ], -1 /* CACHED */)),
                                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.settingsDraft.sort_rules, (r, i) => {
                                                  return (_openBlock(), _createElementBlock("div", {
                                                    key: i,
                                                    class: "magicflow-sort-rules__row"
                                                  }, [
                                                    _createElementVNode("span", null, _toDisplayString(_unref(sortRuleText)(r)), 1 /* TEXT */),
                                                    _createElementVNode("span", null, [
                                                      (_unref(sortRuleNeedsMin)(r.type))
                                                        ? (_openBlock(), _createBlock(_component_VTextField, {
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
                                                          }, null, 8 /* PROPS */, ["modelValue", "onUpdate:modelValue"]))
                                                        : (_openBlock(), _createElementBlock("em", _hoisted_203, "-"))
                                                    ]),
                                                    _createElementVNode("span", null, [
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: r.weight,
                                                        "onUpdate:modelValue": $event => ((r.weight) = $event),
                                                        modelModifiers: { number: true },
                                                        type: "number",
                                                        step: "5",
                                                        density: "compact",
                                                        variant: "outlined",
                                                        "hide-details": "",
                                                        style: {"max-width":"90px"}
                                                      }, null, 8 /* PROPS */, ["modelValue", "onUpdate:modelValue"])
                                                    ]),
                                                    _createElementVNode("span", null, [
                                                      _createVNode(_component_VSwitch, {
                                                        modelValue: r.enabled,
                                                        "onUpdate:modelValue": $event => ((r.enabled) = $event),
                                                        color: "primary",
                                                        density: "compact",
                                                        "hide-details": "",
                                                        inset: ""
                                                      }, null, 8 /* PROPS */, ["modelValue", "onUpdate:modelValue"])
                                                    ]),
                                                    _createElementVNode("span", null, [
                                                      _createVNode(_component_VBtn, {
                                                        size: "x-small",
                                                        variant: "text",
                                                        color: "error",
                                                        icon: "mdi-close",
                                                        "aria-label": "删除这条规则",
                                                        title: "删除这条规则",
                                                        onClick: $event => (emit('remove-sort-rule', i))
                                                      }, null, 8 /* PROPS */, ["onClick"])
                                                    ])
                                                  ]))
                                                }), 128 /* KEYED_FRAGMENT */))
                                              ]),
                                              _createElementVNode("div", _hoisted_204, [
                                                _createVNode(_component_VSelect, {
                                                  modelValue: newRuleType.value,
                                                  "onUpdate:modelValue": _cache[122] || (_cache[122] = $event => ((newRuleType).value = $event)),
                                                  items: _unref(sortRuleTypeOptions),
                                                  "item-title": "text",
                                                  "item-value": "value",
                                                  density: "compact",
                                                  variant: "outlined",
                                                  "hide-details": "",
                                                  style: {"max-width":"200px"},
                                                  label: "新增规则"
                                                }, null, 8 /* PROPS */, ["modelValue", "items"]),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "tonal",
                                                  color: "primary",
                                                  onClick: _cache[123] || (_cache[123] = $event => (emit('add-sort-rule')))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[266] || (_cache[266] = [
                                                    _createTextVNode("加上", -1 /* CACHED */)
                                                  ]))]),
                                                  _: 1 /* STABLE */
                                                })
                                              ])
                                            ]),
                                            _createElementVNode("div", _hoisted_205, [
                                              _createElementVNode("div", _hoisted_206, [
                                                _createVNode(_component_VIcon, { icon: "mdi-database-outline" }),
                                                _cache[267] || (_cache[267] = _createTextVNode(" 账本", -1 /* CACHED */))
                                              ]),
                                              _createElementVNode("span", _hoisted_207, "账本 " + _toDisplayString(__props.tagInfo?.ledger_count ?? 0) + " 条 · 文件组 " + _toDisplayString(__props.tagInfo?.groups?.groups ?? 0) + "（多站 " + _toDisplayString(__props.tagInfo?.groups?.multi_site_groups ?? 0) + "）", 1 /* TEXT */)
                                            ])
                                          ]))
                                        : (settingsTab.value === 'crossseed')
                                          ? (_openBlock(), _createElementBlock("div", _hoisted_208, [
                                              _createElementVNode("div", _hoisted_209, [
                                                _createVNode(_component_VIcon, { icon: "mdi-swap-horizontal" }),
                                                _cache[268] || (_cache[268] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                                  _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "本站非免费，就去兄弟站免费下")
                                                ], -1 /* CACHED */)),
                                                _cache[269] || (_cache[269] = _createElementVNode("span", { class: "magicflow-settings-lede__tag" }, "本页无独立参数", -1 /* CACHED */))
                                              ]),
                                              _createElementVNode("div", _hoisted_210, [
                                                _createElementVNode("div", _hoisted_211, [
                                                  _createVNode(_component_VIcon, { icon: "mdi-map-marker-path" }),
                                                  _cache[270] || (_cache[270] = _createTextVNode(" 这套东西分别在哪配", -1 /* CACHED */))
                                                ]),
                                                _cache[274] || (_cache[274] = _createElementVNode("div", { class: "magicflow-field-stack" }, [
                                                  _createElementVNode("div", { class: "magicflow-field" }),
                                                  _createElementVNode("div", { class: "magicflow-field" }),
                                                  _createElementVNode("div", { class: "magicflow-field" })
                                                ], -1 /* CACHED */)),
                                                _createElementVNode("div", _hoisted_212, [
                                                  _createVNode(_component_VBtn, {
                                                    size: "small",
                                                    variant: "tonal",
                                                    color: "primary",
                                                    "prepend-icon": "mdi-access-point",
                                                    onClick: _cache[124] || (_cache[124] = $event => (emit('open-tab', 'live')))
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[271] || (_cache[271] = [
                                                      _createTextVNode("站点监控 · 流量兜底", -1 /* CACHED */)
                                                    ]))]),
                                                    _: 1 /* STABLE */
                                                  }),
                                                  _createVNode(_component_VBtn, {
                                                    size: "small",
                                                    variant: "tonal",
                                                    color: "primary",
                                                    "prepend-icon": "mdi-seed-outline",
                                                    onClick: _cache[125] || (_cache[125] = $event => (emit('open-tab', 'reseed')))
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[272] || (_cache[272] = [
                                                      _createTextVNode("全站辅种", -1 /* CACHED */)
                                                    ]))]),
                                                    _: 1 /* STABLE */
                                                  }),
                                                  _createVNode(_component_VBtn, {
                                                    size: "small",
                                                    variant: "text",
                                                    "prepend-icon": "mdi-tag-multiple-outline",
                                                    onClick: _cache[126] || (_cache[126] = $event => (emit('open-tab', 'tags')))
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[273] || (_cache[273] = [
                                                      _createTextVNode("标签管理", -1 /* CACHED */)
                                                    ]))]),
                                                    _: 1 /* STABLE */
                                                  })
                                                ])
                                              ])
                                            ]))
                                          : (settingsTab.value === 'fallback')
                                            ? (_openBlock(), _createElementBlock("div", _hoisted_213, [
                                                _createElementVNode("div", _hoisted_214, [
                                                  _createVNode(_component_VIcon, { icon: "mdi-file-document-refresh-outline" }),
                                                  _cache[275] || (_cache[275] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                                    _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "TMDB 查不到的片子，用多源兜底补 NFO")
                                                  ], -1 /* CACHED */)),
                                                  _cache[276] || (_cache[276] = _createElementVNode("span", { class: "magicflow-settings-lede__tag" }, "只写 NFO", -1 /* CACHED */))
                                                ]),
                                                _createElementVNode("div", _hoisted_215, [
                                                  _createElementVNode("div", _hoisted_216, [
                                                    _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                                                    _cache[277] || (_cache[277] = _createTextVNode(" 开关", -1 /* CACHED */))
                                                  ]),
                                                  _createElementVNode("div", _hoisted_217, [
                                                    _createVNode(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.fallback_enabled,
                                                      "onUpdate:modelValue": _cache[127] || (_cache[127] = $event => ((__props.settingsDraft.fallback_enabled) = $event)),
                                                      label: "启用元数据兜底",
                                                      color: "primary",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                                    _createVNode(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.fallback_after_import,
                                                      "onUpdate:modelValue": _cache[128] || (_cache[128] = $event => ((__props.settingsDraft.fallback_after_import) = $event)),
                                                      label: "每次整理入库后自动兜底",
                                                      color: "primary",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                                    _createVNode(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.fallback_dry_run,
                                                      "onUpdate:modelValue": _cache[129] || (_cache[129] = $event => ((__props.settingsDraft.fallback_dry_run) = $event)),
                                                      label: "演练模式（只报告不写 NFO）",
                                                      color: "primary",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8 /* PROPS */, ["modelValue"])
                                                  ])
                                                ]),
                                                _createElementVNode("div", _hoisted_218, [
                                                  _createElementVNode("div", _hoisted_219, [
                                                    _createVNode(_component_VIcon, { icon: "mdi-sort-numeric-ascending" }),
                                                    _cache[278] || (_cache[278] = _createTextVNode(" 识别来源顺序", -1 /* CACHED */))
                                                  ]),
                                                  _createElementVNode("div", _hoisted_220, [
                                                    _createElementVNode("ol", _hoisted_221, [
                                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.usedFallbackSources, (src, idx) => {
                                                        return (_openBlock(), _createElementBlock("li", {
                                                          key: src,
                                                          class: "magicflow-fb-source"
                                                        }, [
                                                          _createElementVNode("span", _hoisted_222, _toDisplayString(idx + 1), 1 /* TEXT */),
                                                          _createElementVNode("span", _hoisted_223, _toDisplayString(_unref(fallbackSourceLabel)(src)), 1 /* TEXT */),
                                                          _createVNode(_component_VBtn, {
                                                            icon: "mdi-arrow-up",
                                                            size: "x-small",
                                                            variant: "text",
                                                            disabled: idx === 0,
                                                            "aria-label": "上移",
                                                            onClick: $event => (emit('move-fallback-source', idx, -1))
                                                          }, null, 8 /* PROPS */, ["disabled", "onClick"]),
                                                          _createVNode(_component_VBtn, {
                                                            icon: "mdi-arrow-down",
                                                            size: "x-small",
                                                            variant: "text",
                                                            disabled: idx === __props.usedFallbackSources.length - 1,
                                                            "aria-label": "下移",
                                                            onClick: $event => (emit('move-fallback-source', idx, 1))
                                                          }, null, 8 /* PROPS */, ["disabled", "onClick"]),
                                                          _createVNode(_component_VBtn, {
                                                            icon: "mdi-close",
                                                            size: "x-small",
                                                            variant: "text",
                                                            "aria-label": "移除",
                                                            onClick: $event => (emit('remove-fallback-source', src))
                                                          }, null, 8 /* PROPS */, ["onClick"])
                                                        ]))
                                                      }), 128 /* KEYED_FRAGMENT */))
                                                    ]),
                                                    _createElementVNode("div", _hoisted_224, [
                                                      _createVNode(_component_VSelect, {
                                                        modelValue: fallbackSourceDraft.value,
                                                        "onUpdate:modelValue": _cache[130] || (_cache[130] = $event => ((fallbackSourceDraft).value = $event)),
                                                        items: __props.unusedFallbackSources,
                                                        "item-title": "title",
                                                        "item-value": "value",
                                                        label: "添加来源",
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": "",
                                                        clearable: ""
                                                      }, null, 8 /* PROPS */, ["modelValue", "items"]),
                                                      _createVNode(_component_VBtn, {
                                                        variant: "tonal",
                                                        color: "primary",
                                                        disabled: !fallbackSourceDraft.value,
                                                        onClick: _cache[131] || (_cache[131] = $event => (emit('add-fallback-source')))
                                                      }, {
                                                        default: _withCtx(() => [...(_cache[279] || (_cache[279] = [
                                                          _createTextVNode("添加", -1 /* CACHED */)
                                                        ]))]),
                                                        _: 1 /* STABLE */
                                                      }, 8 /* PROPS */, ["disabled"])
                                                    ])
                                                  ])
                                                ]),
                                                _createElementVNode("div", _hoisted_225, [
                                                  _createElementVNode("div", _hoisted_226, [
                                                    _createVNode(_component_VIcon, { icon: "mdi-folder-search-outline" }),
                                                    _cache[280] || (_cache[280] = _createTextVNode(" 扫描范围与频率 ", -1 /* CACHED */))
                                                  ]),
                                                  _createVNode(_component_VCombobox, {
                                                    modelValue: __props.settingsDraft.fallback_paths,
                                                    "onUpdate:modelValue": _cache[132] || (_cache[132] = $event => ((__props.settingsDraft.fallback_paths) = $event)),
                                                    items: __props.fallbackState?.effective_paths || [],
                                                    label: "兜底扫描的库目录",
                                                    hint: "留空 = 自动取 MoviePilot 目录配置里的 library 路径（如 /movie）",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    multiple: "",
                                                    chips: "",
                                                    clearable: ""
                                                  }, null, 8 /* PROPS */, ["modelValue", "items"]),
                                                  _createElementVNode("div", _hoisted_227, [
                                                    _createVNode(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.fallback_interval_minutes,
                                                      "onUpdate:modelValue": _cache[133] || (_cache[133] = $event => ((__props.settingsDraft.fallback_interval_minutes) = $event)),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      label: "扫描周期（分钟）",
                                                      hint: "定时扫库兜底，默认 30",
                                                      "persistent-hint": "",
                                                      variant: "outlined",
                                                      density: "comfortable"
                                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                                    _createVNode(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.fallback_scan_max,
                                                      "onUpdate:modelValue": _cache[134] || (_cache[134] = $event => ((__props.settingsDraft.fallback_scan_max) = $event)),
                                                      modelModifiers: { number: true },
                                                      type: "number",
                                                      label: "每轮最多处理剧集数",
                                                      hint: "其余下轮继续，避免一次卡爆，默认 30",
                                                      "persistent-hint": "",
                                                      variant: "outlined",
                                                      density: "comfortable"
                                                    }, null, 8 /* PROPS */, ["modelValue"])
                                                  ]),
                                                  _createElementVNode("div", _hoisted_228, [
                                                    _createVNode(_component_VSwitch, {
                                                      modelValue: __props.settingsDraft.fallback_sp_to_s00,
                                                      "onUpdate:modelValue": _cache[135] || (_cache[135] = $event => ((__props.settingsDraft.fallback_sp_to_s00) = $event)),
                                                      label: "特别篇归位：源中不存在的集改归 Season 0（S00EXX）",
                                                      color: "primary",
                                                      "hide-details": "",
                                                      inset: ""
                                                    }, null, 8 /* PROPS */, ["modelValue"])
                                                  ])
                                                ]),
                                                _createElementVNode("div", _hoisted_229, [
                                                  _createElementVNode("div", _hoisted_230, [
                                                    _createVNode(_component_VIcon, { icon: "mdi-play-circle-outline" }),
                                                    _cache[281] || (_cache[281] = _createTextVNode(" 运行与报告", -1 /* CACHED */))
                                                  ]),
                                                  _createElementVNode("div", _hoisted_231, [
                                                    _createVNode(_component_VBtn, {
                                                      variant: "tonal",
                                                      color: "primary",
                                                      size: "small",
                                                      loading: __props.fallbackRunning,
                                                      disabled: __props.fallbackRunning,
                                                      onClick: _cache[136] || (_cache[136] = $event => (emit('run-fallback', true)))
                                                    }, {
                                                      default: _withCtx(() => [...(_cache[282] || (_cache[282] = [
                                                        _createTextVNode("演练扫描", -1 /* CACHED */)
                                                      ]))]),
                                                      _: 1 /* STABLE */
                                                    }, 8 /* PROPS */, ["loading", "disabled"]),
                                                    _createVNode(_component_VBtn, {
                                                      variant: "flat",
                                                      color: "primary",
                                                      size: "small",
                                                      loading: __props.fallbackRunning,
                                                      disabled: __props.fallbackRunning,
                                                      onClick: _cache[137] || (_cache[137] = $event => (emit('run-fallback', false)))
                                                    }, {
                                                      default: _withCtx(() => [...(_cache[283] || (_cache[283] = [
                                                        _createTextVNode("立即执行", -1 /* CACHED */)
                                                      ]))]),
                                                      _: 1 /* STABLE */
                                                    }, 8 /* PROPS */, ["loading", "disabled"]),
                                                    _createVNode(_component_VBtn, {
                                                      variant: "text",
                                                      size: "small",
                                                      loading: __props.fallbackLoading,
                                                      onClick: _cache[138] || (_cache[138] = $event => (emit('load-fallback')))
                                                    }, {
                                                      default: _withCtx(() => [...(_cache[284] || (_cache[284] = [
                                                        _createTextVNode("刷新结果", -1 /* CACHED */)
                                                      ]))]),
                                                      _: 1 /* STABLE */
                                                    }, 8 /* PROPS */, ["loading"]),
                                                    (__props.fallbackState?.running)
                                                      ? (_openBlock(), _createElementBlock("span", _hoisted_232, "● 扫描中…"))
                                                      : _createCommentVNode("v-if", true)
                                                  ]),
                                                  (__props.fallbackState?.report)
                                                    ? (_openBlock(), _createElementBlock("div", _hoisted_233, [
                                                        _createElementVNode("div", _hoisted_234, [
                                                          _createTextVNode(" 上次" + _toDisplayString(__props.fallbackState.report.applied === false ? '演练' : '执行') + "： 扫描 " + _toDisplayString(__props.fallbackState.report.stats?.shows || 0) + " 剧", 1 /* TEXT */),
                                                          (__props.fallbackState.report.stats?.total_shows)
                                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                                _createTextVNode("/共 " + _toDisplayString(__props.fallbackState.report.stats.total_shows) + " 部", 1 /* TEXT */)
                                                              ], 64 /* STABLE_FRAGMENT */))
                                                            : _createCommentVNode("v-if", true),
                                                          _createTextVNode(" · 识别 " + _toDisplayString(__props.fallbackState.report.stats?.resolved || 0) + " · 补集 NFO " + _toDisplayString(__props.fallbackState.report.stats?.ep_nfo || 0) + " · 补剧 NFO " + _toDisplayString(__props.fallbackState.report.stats?.show_nfo || 0) + " · 源中缺失 " + _toDisplayString(__props.fallbackState.report.stats?.missing || 0) + " · 多源补齐 " + _toDisplayString(__props.fallbackState.report.stats?.via_extra || 0) + " 集 · 归位 " + _toDisplayString(__props.fallbackState.report.stats?.renumbered || 0) + " · " + _toDisplayString(__props.fallbackState.report.duration) + "s ", 1 /* TEXT */)
                                                        ]),
                                                        (__props.fallbackProblemShows.length)
                                                          ? (_openBlock(), _createElementBlock("details", _hoisted_235, [
                                                              _createElementVNode("summary", null, "源里查不到的集（" + _toDisplayString(__props.fallbackProblemCount) + " 集，已按本地文件兜底）", 1 /* TEXT */),
                                                              _createElementVNode("ul", _hoisted_236, [
                                                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.fallbackProblemShows, (item) => {
                                                                  return (_openBlock(), _createElementBlock("li", {
                                                                    key: item.show
                                                                  }, [
                                                                    _createElementVNode("strong", null, _toDisplayString(item.show), 1 /* TEXT */),
                                                                    _createElementVNode("span", _hoisted_237, _toDisplayString((item.problems || []).map(p => `S${String(p.season).padStart(2, '0')}E${String(p.episode).padStart(2, '0')}`).join(' ')), 1 /* TEXT */)
                                                                  ]))
                                                                }), 128 /* KEYED_FRAGMENT */))
                                                              ])
                                                            ]))
                                                          : _createCommentVNode("v-if", true),
                                                        ((__props.fallbackState.report.shows || []).length)
                                                          ? (_openBlock(), _createElementBlock("details", _hoisted_238, [
                                                              _createElementVNode("summary", null, "展开本剧集明细（" + _toDisplayString(__props.fallbackState.report.shows.length) + " 部有变动）", 1 /* TEXT */),
                                                              _createElementVNode("ul", _hoisted_239, [
                                                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.fallbackState.report.shows, (item) => {
                                                                  return (_openBlock(), _createElementBlock("li", {
                                                                    key: item.show
                                                                  }, [
                                                                    _createElementVNode("strong", null, _toDisplayString(item.show), 1 /* TEXT */),
                                                                    _createElementVNode("span", _hoisted_240, "识别自 " + _toDisplayString(item.resolved || '未命中') + "｜补集 " + _toDisplayString((item.episodes || []).filter(e => e.nfo).length) + "｜归位 " + _toDisplayString((item.renumbered || []).length), 1 /* TEXT */)
                                                                  ]))
                                                                }), 128 /* KEYED_FRAGMENT */))
                                                              ])
                                                            ]))
                                                          : _createCommentVNode("v-if", true)
                                                      ]))
                                                    : _createCommentVNode("v-if", true)
                                                ])
                                              ]))
                                            : (settingsTab.value === 'cloud')
                                              ? (_openBlock(), _createElementBlock("div", _hoisted_241, [
                                                  _createElementVNode("div", _hoisted_242, [
                                                    _createVNode(_component_VIcon, { icon: "mdi-cloud-upload-outline" }),
                                                    _cache[285] || (_cache[285] = _createElementVNode("div", { class: "magicflow-settings-lede__bd" }, [
                                                      _createElementVNode("div", { class: "magicflow-settings-lede__t" }, "本地当热区，夸克当冷库")
                                                    ], -1 /* CACHED */)),
                                                    _cache[286] || (_cache[286] = _createElementVNode("span", { class: "magicflow-settings-lede__tag is-warn" }, "默认不删本地", -1 /* CACHED */))
                                                  ]),
                                                  _createElementVNode("div", _hoisted_243, [
                                                    _createElementVNode("div", _hoisted_244, [
                                                      _createVNode(_component_VIcon, { icon: "mdi-toggle-switch-outline" }),
                                                      _cache[287] || (_cache[287] = _createTextVNode(" 开关", -1 /* CACHED */))
                                                    ]),
                                                    _createElementVNode("div", _hoisted_245, [
                                                      _createVNode(_component_VSwitch, {
                                                        modelValue: __props.settingsDraft.cloud_enabled,
                                                        "onUpdate:modelValue": _cache[139] || (_cache[139] = $event => ((__props.settingsDraft.cloud_enabled) = $event)),
                                                        label: "启用云盘归档",
                                                        color: "primary",
                                                        "hide-details": "",
                                                        inset: ""
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VSwitch, {
                                                        modelValue: __props.settingsDraft.cloud_dry_run,
                                                        "onUpdate:modelValue": _cache[140] || (_cache[140] = $event => ((__props.settingsDraft.cloud_dry_run) = $event)),
                                                        label: "演练模式（只列计划，不真传）",
                                                        color: "primary",
                                                        "hide-details": "",
                                                        inset: ""
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VSwitch, {
                                                        modelValue: __props.settingsDraft.cloud_notify,
                                                        "onUpdate:modelValue": _cache[141] || (_cache[141] = $event => ((__props.settingsDraft.cloud_notify) = $event)),
                                                        label: "完成后通知",
                                                        color: "primary",
                                                        "hide-details": "",
                                                        inset: ""
                                                      }, null, 8 /* PROPS */, ["modelValue"])
                                                    ])
                                                  ]),
                                                  _createElementVNode("div", _hoisted_246, [
                                                    _createElementVNode("div", _hoisted_247, [
                                                      _createVNode(_component_VIcon, { icon: "mdi-lan-connect" }),
                                                      _cache[288] || (_cache[288] = _createTextVNode(" 连接", -1 /* CACHED */))
                                                    ]),
                                                    _createElementVNode("div", _hoisted_248, [
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_openlist_url,
                                                        "onUpdate:modelValue": _cache[142] || (_cache[142] = $event => ((__props.settingsDraft.cloud_openlist_url) = $event)),
                                                        label: "OpenList 地址",
                                                        placeholder: "http://192.168.0.61:12022",
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": "",
                                                        autocomplete: "off"
                                                      }, null, 8 /* PROPS */, ["modelValue"])
                                                    ]),
                                                    _createElementVNode("div", _hoisted_249, [
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_openlist_token,
                                                        "onUpdate:modelValue": _cache[143] || (_cache[143] = $event => ((__props.settingsDraft.cloud_openlist_token) = $event)),
                                                        label: "OpenList Token",
                                                        placeholder: __props.cloudCfg.has_token ? '已保存（留空则不修改）' : 'openlist-…',
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": "",
                                                        autocomplete: "off",
                                                        "persistent-hint": "",
                                                        hint: "留空＝保留已存 Token；Token 不回显"
                                                      }, null, 8 /* PROPS */, ["modelValue", "placeholder"]),
                                                      _createVNode(_component_VBtn, {
                                                        variant: "tonal",
                                                        color: "primary",
                                                        size: "small",
                                                        "prepend-icon": "mdi-connection",
                                                        loading: __props.cloudTesting,
                                                        onClick: _cache[144] || (_cache[144] = $event => (emit('test-cloud')))
                                                      }, {
                                                        default: _withCtx(() => [...(_cache[289] || (_cache[289] = [
                                                          _createTextVNode("测试", -1 /* CACHED */)
                                                        ]))]),
                                                        _: 1 /* STABLE */
                                                      }, 8 /* PROPS */, ["loading"])
                                                    ]),
                                                    (__props.cloudTestMsg)
                                                      ? (_openBlock(), _createElementBlock("p", {
                                                          key: 0,
                                                          class: _normalizeClass(["magicflow-settings-feedback", __props.cloudTestOk ? 'is-ok' : 'is-no'])
                                                        }, _toDisplayString(__props.cloudTestMsg), 3 /* TEXT, CLASS */))
                                                      : _createCommentVNode("v-if", true)
                                                  ]),
                                                  _createElementVNode("div", _hoisted_250, [
                                                    _createElementVNode("div", _hoisted_251, [
                                                      _createVNode(_component_VIcon, { icon: "mdi-folder-arrow-up-down-outline" }),
                                                      _cache[290] || (_cache[290] = _createTextVNode(" 路径模板", -1 /* CACHED */))
                                                    ]),
                                                    _createElementVNode("div", _hoisted_252, [
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_source_mount,
                                                        "onUpdate:modelValue": _cache[145] || (_cache[145] = $event => ((__props.settingsDraft.cloud_source_mount) = $event)),
                                                        label: "可写存储路径",
                                                        hint: "OpenList 里可写的存储挂载点，默认 /quark",
                                                        "persistent-hint": "",
                                                        variant: "outlined",
                                                        density: "comfortable"
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_strm_mount,
                                                        "onUpdate:modelValue": _cache[146] || (_cache[146] = $event => ((__props.settingsDraft.cloud_strm_mount) = $event)),
                                                        label: "Strm 视图路径",
                                                        hint: "只读校验用（Strm 驱动），默认 /movie",
                                                        "persistent-hint": "",
                                                        variant: "outlined",
                                                        density: "comfortable"
                                                      }, null, 8 /* PROPS */, ["modelValue"])
                                                    ]),
                                                    _createVNode(_component_VTextField, {
                                                      modelValue: __props.settingsDraft.cloud_target_template,
                                                      "onUpdate:modelValue": _cache[147] || (_cache[147] = $event => ((__props.settingsDraft.cloud_target_template) = $event)),
                                                      label: "远端目标模板",
                                                      hint: "{rel}＝相对库根的路径；默认 /quark/movie/{rel}（与本地库同构）",
                                                      "persistent-hint": "",
                                                      variant: "outlined",
                                                      density: "comfortable"
                                                    }, null, 8 /* PROPS */, ["modelValue"])
                                                  ]),
                                                  _createElementVNode("div", _hoisted_253, [
                                                    _createElementVNode("div", _hoisted_254, [
                                                      _createVNode(_component_VIcon, { icon: "mdi-filter-variant" }),
                                                      _cache[291] || (_cache[291] = _createTextVNode(" 归档范围与限速 ", -1 /* CACHED */))
                                                    ]),
                                                    _createVNode(_component_VCombobox, {
                                                      modelValue: __props.settingsDraft.cloud_paths,
                                                      "onUpdate:modelValue": _cache[148] || (_cache[148] = $event => ((__props.settingsDraft.cloud_paths) = $event)),
                                                      label: "扫描目录（容器内路径，留空 = /movie）",
                                                      hint: "可多个；只扫这些库根下的媒体文件",
                                                      "persistent-hint": "",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      chips: "",
                                                      multiple: "",
                                                      clearable: "",
                                                      items: ['/movie']
                                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                                    _createVNode(_component_VCombobox, {
                                                      modelValue: __props.settingsDraft.cloud_exclude_paths,
                                                      "onUpdate:modelValue": _cache[149] || (_cache[149] = $event => ((__props.settingsDraft.cloud_exclude_paths) = $event)),
                                                      label: "排除路径（子串匹配）",
                                                      hint: "默认已排除下载区/刷流区/蓝光原盘；这里可再加",
                                                      "persistent-hint": "",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      chips: "",
                                                      multiple: "",
                                                      clearable: "",
                                                      items: ['/movie/刷流', '/movie/下载']
                                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                                    _createVNode(_component_VCombobox, {
                                                      modelValue: __props.settingsDraft.cloud_exclude_tags,
                                                      "onUpdate:modelValue": _cache[150] || (_cache[150] = $event => ((__props.settingsDraft.cloud_exclude_tags) = $event)),
                                                      label: "排除标签（做种中的种不打上传策略标，可留空）",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      chips: "",
                                                      multiple: "",
                                                      clearable: "",
                                                      items: ['魔流-推荐', '辅种', '已整理']
                                                    }, null, 8 /* PROPS */, ["modelValue"]),
                                                    _createElementVNode("div", _hoisted_255, [
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_min_size_gb,
                                                        "onUpdate:modelValue": _cache[151] || (_cache[151] = $event => ((__props.settingsDraft.cloud_min_size_gb) = $event)),
                                                        modelModifiers: { number: true },
                                                        type: "number",
                                                        label: "最小体积（GB，0 = 不限）",
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": ""
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_max_size_gb,
                                                        "onUpdate:modelValue": _cache[152] || (_cache[152] = $event => ((__props.settingsDraft.cloud_max_size_gb) = $event)),
                                                        modelModifiers: { number: true },
                                                        type: "number",
                                                        label: "最大体积（GB，0 = 不限）",
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": ""
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_min_age_days,
                                                        "onUpdate:modelValue": _cache[153] || (_cache[153] = $event => ((__props.settingsDraft.cloud_min_age_days) = $event)),
                                                        modelModifiers: { number: true },
                                                        type: "number",
                                                        label: "最小入库天数（0 = 不限）",
                                                        hint: "只归档入库较久、已经稳定的资源",
                                                        "persistent-hint": "",
                                                        variant: "outlined",
                                                        density: "comfortable"
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_upload_limit_mbps,
                                                        "onUpdate:modelValue": _cache[154] || (_cache[154] = $event => ((__props.settingsDraft.cloud_upload_limit_mbps) = $event)),
                                                        modelModifiers: { number: true },
                                                        type: "number",
                                                        label: "上传限速（Mbps，0 = 不限）",
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": ""
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_interval_minutes,
                                                        "onUpdate:modelValue": _cache[155] || (_cache[155] = $event => ((__props.settingsDraft.cloud_interval_minutes) = $event)),
                                                        modelModifiers: { number: true },
                                                        type: "number",
                                                        label: "后台归档周期（分钟）",
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": ""
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VTextField, {
                                                        modelValue: __props.settingsDraft.cloud_scan_max,
                                                        "onUpdate:modelValue": _cache[156] || (_cache[156] = $event => ((__props.settingsDraft.cloud_scan_max) = $event)),
                                                        modelModifiers: { number: true },
                                                        type: "number",
                                                        label: "每轮最多处理文件数",
                                                        variant: "outlined",
                                                        density: "comfortable",
                                                        "hide-details": ""
                                                      }, null, 8 /* PROPS */, ["modelValue"])
                                                    ])
                                                  ]),
                                                  _createElementVNode("div", _hoisted_256, [
                                                    _createElementVNode("div", _hoisted_257, [
                                                      _createVNode(_component_VIcon, { icon: "mdi-alert-outline" }),
                                                      _cache[292] || (_cache[292] = _createTextVNode(" 危险区 ", -1 /* CACHED */))
                                                    ]),
                                                    _createElementVNode("div", _hoisted_258, [
                                                      _createVNode(_component_VSwitch, {
                                                        modelValue: __props.settingsDraft.cloud_delete_local,
                                                        "onUpdate:modelValue": _cache[157] || (_cache[157] = $event => ((__props.settingsDraft.cloud_delete_local) = $event)),
                                                        label: "归档后删除本地文件（危险：会停种；插件只记录、不自动执行）",
                                                        color: "error",
                                                        "hide-details": "",
                                                        inset: ""
                                                      }, null, 8 /* PROPS */, ["modelValue"]),
                                                      _createVNode(_component_VSwitch, {
                                                        modelValue: __props.settingsDraft.cloud_remove_torrent,
                                                        "onUpdate:modelValue": _cache[158] || (_cache[158] = $event => ((__props.settingsDraft.cloud_remove_torrent) = $event)),
                                                        label: "同时移除下载器任务（危险，需人工确认）",
                                                        color: "error",
                                                        "hide-details": "",
                                                        inset: ""
                                                      }, null, 8 /* PROPS */, ["modelValue"])
                                                    ]),
                                                    _cache[293] || (_cache[293] = _createElementVNode("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, [
                                                      _createTextVNode(" 安全默认："),
                                                      _createElementVNode("strong", null, "不删本地、不停种"),
                                                      _createTextVNode("。删本地需要逐条上传校验通过后手动确认，绝不会自动执行。 ")
                                                    ], -1 /* CACHED */))
                                                  ])
                                                ]))
                                              : _createCommentVNode("v-if", true)
              ]))
            : _createCommentVNode("v-if", true),
          _createElementVNode("footer", _hoisted_259, [
            (settingsTab.value === 'downloader')
              ? (_openBlock(), _createBlock(_component_VBtn, {
                  key: 0,
                  variant: "tonal",
                  color: "primary",
                  disabled: !__props.downloaderPrefsRecommended,
                  onClick: _cache[159] || (_cache[159] = $event => (emit('apply-recommended')))
                }, {
                  default: _withCtx(() => [...(_cache[294] || (_cache[294] = [
                    _createTextVNode(" 恢复推荐值 ", -1 /* CACHED */)
                  ]))]),
                  _: 1 /* STABLE */
                }, 8 /* PROPS */, ["disabled"]))
              : _createCommentVNode("v-if", true),
            _createVNode(_component_VSpacer),
            _createVNode(_component_VBtn, {
              variant: "text",
              onClick: _cache[160] || (_cache[160] = $event => (settingsDialog.value = false))
            }, {
              default: _withCtx(() => [...(_cache[295] || (_cache[295] = [
                _createTextVNode("取消", -1 /* CACHED */)
              ]))]),
              _: 1 /* STABLE */
            }),
            _createVNode(_component_VBtn, {
              color: "primary",
              variant: "flat",
              loading: __props.saving,
              onClick: _cache[161] || (_cache[161] = $event => (emit('save')))
            }, {
              default: _withCtx(() => [...(_cache[296] || (_cache[296] = [
                _createTextVNode("保存", -1 /* CACHED */)
              ]))]),
              _: 1 /* STABLE */
            }, 8 /* PROPS */, ["loading"])
          ])
        ]),
        _: 1 /* STABLE */
      })
    ]),
    _: 1 /* STABLE */
  }, 8 /* PROPS */, ["modelValue", "fullscreen"]))
}
}

}
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const SettingsDialog = Object.assign(_sfc_main$c, { __scopeId: 'data-v-e2f63a1f' })

export default SettingsDialog
