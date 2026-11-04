// 「手动保种」弹窗 —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 源码形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.12.x 线上一致。
import './keep.css'
import * as __vue from 'vue'

const {
  Fragment: _Fragment$x,
  createBlock: _createBlock$B,
  createCommentVNode: _createCommentVNode$z,
  createElementBlock: _createElementBlock$y,
  createElementVNode: _createElementVNode$E,
  createTextVNode: _createTextVNode$D,
  createVNode: _createVNode$D,
  mergeModels: _mergeModels$n,
  normalizeClass: _normalizeClass$k,
  openBlock: _openBlock$E,
  renderList: _renderList$v,
  resolveComponent: _resolveComponent$E,
  toDisplayString: _toDisplayString$E,
  useModel: _useModel$n,
  withCtx: _withCtx$B,
} = __vue

const _hoisted_1$A = { class: "magicflow-settings-dialog__head" };
const _hoisted_2$y = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_3$w = { class: "magicflow-cs-stats" };
const _hoisted_4$w = { class: "magicflow-cs-stat" };
const _hoisted_5$w = { class: "magicflow-cs-stat" };
const _hoisted_6$u = { class: "magicflow-keep-tools" };
const _hoisted_7$r = { class: "magicflow-keep-list" };
const _hoisted_8$p = { class: "magicflow-keep-list__head" };
const _hoisted_9$n = { class: "magicflow-keep-row__main" };
const _hoisted_10$n = ["title"];
const _hoisted_11$l = { class: "magicflow-keep-row__meta" };
const _hoisted_12$l = { class: "magicflow-cs-status__dim" };
const _hoisted_13$j = { class: "magicflow-cs-status__dim" };
const _hoisted_14$i = {
  key: 0,
  class: "magicflow-cs-status__dim"
};
const _hoisted_15$i = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_16$i = { class: "magicflow-cs-stats" };
const _hoisted_17$i = { class: "magicflow-cs-stat" };
const _hoisted_18$i = { class: "magicflow-cs-stat" };
const _hoisted_19$h = { class: "magicflow-cs-stat is-pick" };
const _hoisted_20$f = { class: "magicflow-keep-tools" };
const _hoisted_21$e = { class: "magicflow-keep-list" };
const _hoisted_22$d = { class: "magicflow-keep-list__head" };
const _hoisted_23$c = {
  key: 0,
  class: "magicflow-keep-bulkwarn"
};
const _hoisted_24$c = { class: "magicflow-keep-row__main" };
const _hoisted_25$c = ["title"];
const _hoisted_26$a = { class: "magicflow-keep-row__meta" };
const _hoisted_27$a = { class: "magicflow-cs-status__dim" };
const _hoisted_28$9 = { class: "magicflow-cs-status__dim" };
const _hoisted_29$9 = {
  key: 1,
  class: "magicflow-cs-status__dim"
};
const _hoisted_30$9 = {
  key: 1,
  class: "magicflow-table-empty"
};
const _hoisted_31$9 = {
  key: 2,
  class: "magicflow-table-empty"
};
const _hoisted_32$9 = {
  key: 3,
  class: "magicflow-keep-pager"
};

const {computed: computed$K} = __vue



const _sfc_main$E = {
  __name: 'KeepDialog',
  props: /*@__PURE__*/_mergeModels$n({
  data: { type: Object, default: () => ({}) },
  items: { type: Array, default: () => [] },
  sel: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
  candLoading: { type: Boolean, default: false },
  candData: { type: Object, default: () => ({}) },
  candRows: { type: Array, default: () => [] },
  candList: { type: Array, default: () => [] },
  candSel: { type: Array, default: () => [] },
  candSubs: { type: Array, default: () => [] },
  candPages: { type: Number, default: 1 },
  candPage: { type: Number, default: 1 },
  candSelGb: { type: Number, default: 0 },
  candSelOnPage: { type: Number, default: 0 },
}, {
    "modelValue": { type: Boolean, default: false },
    "modelModifiers": {},
    "tab": { type: String, default: 'list' },
    "tabModifiers": {},
    "q": { type: String, default: '' },
    "qModifiers": {},
    "onlyBad": { type: Boolean, default: false },
    "onlyBadModifiers": {},
    "candQ": { type: String, default: '' },
    "candQModifiers": {},
    "candSite": { type: String, default: '' },
    "candSiteModifiers": {},
    "candSub": { type: String, default: '' },
    "candSubModifiers": {},
    "candOnlyHr": { type: Boolean, default: false },
    "candOnlyHrModifiers": {},
    "candSort": { type: String, default: 'site' },
    "candSortModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$n([
  'refresh', 'toggle-row', 'toggle-all', 'release', 'resume', 'switch-tab',
  'cand-toggle-row', 'cand-toggle-page', 'cand-toggle-all', 'cand-clear', 'cand-goto', 'cand-hold',
], ["update:modelValue", "update:tab", "update:q", "update:onlyBad", "update:candQ", "update:candSite", "update:candSub", "update:candOnlyHr", "update:candSort"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 「手动保种」弹窗（★ 19.10.41 / 19.10.42）
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
//
// ★ 为什么单独一个弹窗：手动保种挂的是 `__keep__` 伪任务 —— 它**不是真任务**，
//   所以这批种既不在任何任务的种子池里、也不进 `status.tasks`。挂上之后界面上
//   哪儿都看不见，只能自己记 hash 才能解除（2026-10-30 实测存量 18 个）。
//
// ★ 19.10.42 两个标签页（Master：「才是 18 个，我要所有静默池里的都能选」）：
//   ·「已保种」= 挂在 `__keep__` 名下的种 —— 看状态 / 拉起 / 解除；
//   ·「从静默池挑选」= 静默池全部候选（1000+）—— 过滤 / 分页 / 全选后挂上。
//   只有前者时「挂保种」只能去种子池里一页页翻，静默池根本没有勾选入口。
const open = _useModel$n(__props, "modelValue");
const tab = _useModel$n(__props, 'tab');
const q = _useModel$n(__props, 'q');
const onlyBad = _useModel$n(__props, 'onlyBad');
// 候选池的筛选条件（同样由父页持有，切标签/关弹窗后不丢）
const candQ = _useModel$n(__props, 'candQ');
const candSite = _useModel$n(__props, 'candSite');
const candSub = _useModel$n(__props, 'candSub');
const candOnlyHr = _useModel$n(__props, 'candOnlyHr');
const candSort = _useModel$n(__props, 'candSort');

const props = __props;

const emit = __emit;

const total = computed$K(() => Number(props.data.total || (props.data.items || []).length || 0));
const notSeeding = computed$K(() => Number(props.data.not_seeding || 0));
const sizeGb = computed$K(() => (props.data.items || []).reduce((s, it) => s + Number(it.size_gb || 0), 0));
const allSel = computed$K(() => props.items.length > 0 && props.sel.length >= props.items.length);

const candTotal = computed$K(() => Number(props.candData.total || 0));
const candPoolGb = computed$K(() => Number(props.candData.size_gb || 0));
const candHrN = computed$K(() => Number(props.candData.owed_hr || 0));
const candSites = computed$K(() => props.candData.sites || []);
// 已选超过一屏时提醒：挂保种会一并 force start，一次太多会占满上传带宽
const bulkWarn = computed$K(() => props.candSel.length > 20);

function sizeText(v) {
  const n = Number(v || 0);
  if (!n) return '—'
  return n >= 1024 ? `${(n / 1024).toFixed(2)} TB` : `${n.toFixed(2)} GB`
}

/** 行状态：不在下载器 / 在做种 / 下载中 / 其它（暂停等，直接显示下载器状态）。 */
function rowState(it) {
  if (!it.in_qb) return { text: '不在下载器', color: 'error' }
  if (it.seeding) return { text: '在做种', color: 'success' }
  const p = Number(it.progress || 0);
  if (p < 0.999) return { text: `下载中 ${(p * 100).toFixed(1)}%`, color: 'info' }
  const s = String(it.state || '').toLowerCase();
  if (s.startsWith('paused')) return { text: '已暂停', color: 'warning' }
  if (s.startsWith('stopped')) return { text: '已停止', color: 'warning' }
  if (s.startsWith('error') || s.startsWith('missing')) return { text: '异常', color: 'error' }
  return { text: it.state || '—', color: 'warning' }
}

function candState(it) {
  const s = String(it.state || '').toLowerCase();
  const p = Number(it.progress || 0);
  if (p < 0.999) return { text: `未下完 ${(p * 100).toFixed(0)}%`, color: 'info' }
  if (s.startsWith('paused')) return { text: '已暂停', color: 'warning' }
  if (s.startsWith('stopped')) return { text: '已停止', color: 'warning' }
  return { text: '静默中', color: 'default' }
}

function onTab(v) {
  tab.value = v;
  emit('switch-tab', v);
}

return (_ctx, _cache) => {
  const _component_VChip = _resolveComponent$E("VChip");
  const _component_VBtn = _resolveComponent$E("VBtn");
  const _component_VTab = _resolveComponent$E("VTab");
  const _component_VTabs = _resolveComponent$E("VTabs");
  const _component_VDivider = _resolveComponent$E("VDivider");
  const _component_VTextField = _resolveComponent$E("VTextField");
  const _component_VCheckbox = _resolveComponent$E("VCheckbox");
  const _component_VSpacer = _resolveComponent$E("VSpacer");
  const _component_VSelect = _resolveComponent$E("VSelect");
  const _component_VCardText = _resolveComponent$E("VCardText");
  const _component_VCard = _resolveComponent$E("VCard");
  const _component_VDialog = _resolveComponent$E("VDialog");

  return (_openBlock$E(), _createBlock$B(_component_VDialog, {
    modelValue: open.value,
    "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((open).value = $event)),
    "max-width": "58rem",
    fullscreen: __props.narrow
  }, {
    default: _withCtx$B(() => [
      _createVNode$D(_component_VCard, { class: "magicflow-dialog magicflow-keep-dialog" }, {
        default: _withCtx$B(() => [
          _createElementVNode$E("header", _hoisted_1$A, [
            _cache[19] || (_cache[19] = _createElementVNode$E("span", { class: "magicflow-settings-dialog__title" }, "手动保种", -1)),
            _createElementVNode$E("div", _hoisted_2$y, [
              _createVNode$D(_component_VChip, {
                size: "small",
                variant: "tonal",
                color: "primary"
              }, {
                default: _withCtx$B(() => [...(_cache[18] || (_cache[18] = [
                  _createTextVNode$D("人工点名 · 不会被自动释放", -1)
                ]))]),
                _: 1
              }),
              _createVNode$D(_component_VBtn, {
                icon: "mdi-refresh",
                size: "small",
                variant: "text",
                "aria-label": "刷新",
                loading: __props.loading || __props.candLoading,
                onClick: _cache[0] || (_cache[0] = $event => (emit('refresh')))
              }, null, 8, ["loading"]),
              _createVNode$D(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[1] || (_cache[1] = $event => (open.value = false))
              })
            ])
          ]),
          _createVNode$D(_component_VTabs, {
            "model-value": tab.value,
            density: "compact",
            color: "primary",
            "show-arrows": "",
            class: "magicflow-keep-tabs",
            "onUpdate:modelValue": onTab
          }, {
            default: _withCtx$B(() => [
              _createVNode$D(_component_VTab, {
                value: "list",
                "prepend-icon": "mdi-pin"
              }, {
                default: _withCtx$B(() => [
                  _createTextVNode$D("已保种（" + _toDisplayString$E(total.value) + "）", 1)
                ]),
                _: 1
              }),
              _createVNode$D(_component_VTab, {
                value: "pick",
                "prepend-icon": "mdi-playlist-plus"
              }, {
                default: _withCtx$B(() => [
                  _createTextVNode$D(" 从静默池挑选（" + _toDisplayString$E(candTotal.value || '…') + "） ", 1)
                ]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["model-value"]),
          _createVNode$D(_component_VDivider),
          _createVNode$D(_component_VCardText, { class: "magicflow-keep-body" }, {
            default: _withCtx$B(() => [
              (tab.value === 'list')
                ? (_openBlock$E(), _createElementBlock$y(_Fragment$x, { key: 0 }, [
                    _createElementVNode$E("div", _hoisted_3$w, [
                      _createElementVNode$E("div", _hoisted_4$w, [
                        _createElementVNode$E("b", null, _toDisplayString$E(total.value), 1),
                        _cache[20] || (_cache[20] = _createElementVNode$E("span", null, "保种总数", -1))
                      ]),
                      _createElementVNode$E("div", {
                        class: _normalizeClass$k(["magicflow-cs-stat", { 'is-warn': notSeeding.value > 0 }])
                      }, [
                        _createElementVNode$E("b", null, _toDisplayString$E(notSeeding.value), 1),
                        _cache[21] || (_cache[21] = _createElementVNode$E("span", null, "没在做种", -1))
                      ], 2),
                      _createElementVNode$E("div", _hoisted_5$w, [
                        _createElementVNode$E("b", null, _toDisplayString$E(sizeText(sizeGb.value)), 1),
                        _cache[22] || (_cache[22] = _createElementVNode$E("span", null, "占用空间", -1))
                      ])
                    ]),
                    _createElementVNode$E("div", _hoisted_6$u, [
                      _createVNode$D(_component_VTextField, {
                        modelValue: q.value,
                        "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((q).value = $event)),
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        "prepend-inner-icon": "mdi-magnify",
                        placeholder: "按标题 / 站点 / hash 过滤",
                        class: "magicflow-keep-search",
                        clearable: ""
                      }, null, 8, ["modelValue"]),
                      _createVNode$D(_component_VChip, {
                        size: "small",
                        variant: onlyBad.value ? 'flat' : 'tonal',
                        color: onlyBad.value ? 'warning' : 'default',
                        onClick: _cache[3] || (_cache[3] = $event => (onlyBad.value = !onlyBad.value))
                      }, {
                        default: _withCtx$B(() => [
                          _createTextVNode$D("只看没在做种（" + _toDisplayString$E(notSeeding.value) + "）", 1)
                        ]),
                        _: 1
                      }, 8, ["variant", "color"])
                    ]),
                    _createElementVNode$E("div", _hoisted_7$r, [
                      _createElementVNode$E("div", _hoisted_8$p, [
                        _createVNode$D(_component_VCheckbox, {
                          "model-value": allSel.value,
                          indeterminate: __props.sel.length > 0 && !allSel.value,
                          density: "compact",
                          "hide-details": "",
                          "aria-label": "全选",
                          "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => (emit('toggle-all')))
                        }, null, 8, ["model-value", "indeterminate"]),
                        _createElementVNode$E("span", null, _toDisplayString$E(__props.sel.length ? `已选 ${__props.sel.length} 个` : `共 ${__props.items.length} 条`), 1),
                        _createVNode$D(_component_VSpacer),
                        _createVNode$D(_component_VBtn, {
                          size: "small",
                          variant: "tonal",
                          color: "success",
                          disabled: __props.busy || !__props.sel.length,
                          "prepend-icon": "mdi-play-circle-outline",
                          onClick: _cache[5] || (_cache[5] = $event => (emit('resume', [])))
                        }, {
                          default: _withCtx$B(() => [
                            _createTextVNode$D("拉起做种（" + _toDisplayString$E(__props.sel.length) + "）", 1)
                          ]),
                          _: 1
                        }, 8, ["disabled"]),
                        _createVNode$D(_component_VBtn, {
                          size: "small",
                          variant: "tonal",
                          color: "warning",
                          disabled: __props.busy || !__props.sel.length,
                          "prepend-icon": "mdi-pin-off",
                          onClick: _cache[6] || (_cache[6] = $event => (emit('release', [])))
                        }, {
                          default: _withCtx$B(() => [
                            _createTextVNode$D("解除所选（" + _toDisplayString$E(__props.sel.length) + "）", 1)
                          ]),
                          _: 1
                        }, 8, ["disabled"])
                      ]),
                      (_openBlock$E(true), _createElementBlock$y(_Fragment$x, null, _renderList$v(__props.items, (it) => {
                        return (_openBlock$E(), _createElementBlock$y("article", {
                          key: it.hash,
                          class: _normalizeClass$k(["magicflow-keep-row", { 'is-sel': __props.sel.includes(it.hash) }])
                        }, [
                          _createVNode$D(_component_VCheckbox, {
                            "model-value": __props.sel.includes(it.hash),
                            density: "compact",
                            "hide-details": "",
                            "aria-label": `选择 ${it.title || it.hash}`,
                            "onUpdate:modelValue": $event => (emit('toggle-row', it.hash))
                          }, null, 8, ["model-value", "aria-label", "onUpdate:modelValue"]),
                          _createElementVNode$E("div", _hoisted_9$n, [
                            _createElementVNode$E("div", {
                              class: "magicflow-keep-row__name",
                              title: it.title || it.hash
                            }, _toDisplayString$E(it.title || it.hash), 9, _hoisted_10$n),
                            _createElementVNode$E("div", _hoisted_11$l, [
                              _createVNode$D(_component_VChip, {
                                size: "x-small",
                                variant: "tonal",
                                color: "primary"
                              }, {
                                default: _withCtx$B(() => [
                                  _createTextVNode$D(_toDisplayString$E(it.site || '—'), 1)
                                ]),
                                _: 2
                              }, 1024),
                              _createVNode$D(_component_VChip, {
                                size: "x-small",
                                variant: "flat",
                                color: rowState(it).color
                              }, {
                                default: _withCtx$B(() => [
                                  _createTextVNode$D(_toDisplayString$E(rowState(it).text), 1)
                                ]),
                                _: 2
                              }, 1032, ["color"]),
                              _createElementVNode$E("span", _hoisted_12$l, _toDisplayString$E(sizeText(it.size_gb)), 1),
                              _createElementVNode$E("span", _hoisted_13$j, _toDisplayString$E((it.hash || '').slice(0, 12)), 1),
                              (it.sub)
                                ? (_openBlock$E(), _createElementBlock$y("span", _hoisted_14$i, _toDisplayString$E(it.sub), 1))
                                : _createCommentVNode$z("", true)
                            ])
                          ]),
                          (!it.seeding)
                            ? (_openBlock$E(), _createBlock$B(_component_VBtn, {
                                key: 0,
                                size: "small",
                                variant: "text",
                                color: "success",
                                disabled: __props.busy,
                                "aria-label": "重新拉起这一条做种",
                                icon: "mdi-play-circle-outline",
                                onClick: $event => (emit('resume', [it.hash]))
                              }, null, 8, ["disabled", "onClick"]))
                            : _createCommentVNode$z("", true),
                          _createVNode$D(_component_VBtn, {
                            size: "small",
                            variant: "text",
                            color: "warning",
                            disabled: __props.busy,
                            "aria-label": "解除这一条的人工占用",
                            icon: "mdi-pin-off",
                            onClick: $event => (emit('release', [it.hash]))
                          }, null, 8, ["disabled", "onClick"])
                        ], 2))
                      }), 128)),
                      (!__props.items.length)
                        ? (_openBlock$E(), _createElementBlock$y("div", _hoisted_15$i, _toDisplayString$E(total.value ? '当前过滤下没有匹配的种' : '还没有手动保种的种 —— 切到「从静默池挑选」勾选后挂上'), 1))
                        : _createCommentVNode$z("", true)
                    ]),
                    _cache[23] || (_cache[23] = _createElementVNode$E("div", { class: "magicflow-settings-hint mt-2" }, [
                      _createTextVNode$D(" 手动保种 = 把种挂到 "),
                      _createElementVNode$E("code", null, "__keep__"),
                      _createTextVNode$D(" 伪任务（职务标签「魔流-<站>-保种」）。 挂着期间静默闸 / 清理闸 / H&R 保种都不会来收它，下完也继续做种。 但「挂着」不等于「在做种」—— 被下载器暂停过的种要在这里点"),
                      _createElementVNode$E("b", null, "拉起做种"),
                      _createTextVNode$D("（force start）。 解除后种退回静默池 —— 没下完的会被当半成品清理，因此只在确实要停时才解。 ")
                    ], -1))
                  ], 64))
                : (_openBlock$E(), _createElementBlock$y(_Fragment$x, { key: 1 }, [
                    _createElementVNode$E("div", _hoisted_16$i, [
                      _createElementVNode$E("div", _hoisted_17$i, [
                        _createElementVNode$E("b", null, _toDisplayString$E(candTotal.value), 1),
                        _cache[24] || (_cache[24] = _createElementVNode$E("span", null, "静默池可挂", -1))
                      ]),
                      _createElementVNode$E("div", _hoisted_18$i, [
                        _createElementVNode$E("b", null, _toDisplayString$E(sizeText(candPoolGb.value)), 1),
                        _cache[25] || (_cache[25] = _createElementVNode$E("span", null, "候选总容量", -1))
                      ]),
                      _createElementVNode$E("div", {
                        class: _normalizeClass$k(["magicflow-cs-stat", { 'is-warn': candHrN.value > 0 }])
                      }, [
                        _createElementVNode$E("b", null, _toDisplayString$E(candHrN.value), 1),
                        _cache[26] || (_cache[26] = _createElementVNode$E("span", null, "欠 H&R", -1))
                      ], 2),
                      _createElementVNode$E("div", _hoisted_19$h, [
                        _createElementVNode$E("b", null, _toDisplayString$E(__props.candSel.length), 1),
                        _createElementVNode$E("span", null, "已选 " + _toDisplayString$E(sizeText(__props.candSelGb)), 1)
                      ])
                    ]),
                    _createElementVNode$E("div", _hoisted_20$f, [
                      _createVNode$D(_component_VTextField, {
                        modelValue: candQ.value,
                        "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((candQ).value = $event)),
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        "prepend-inner-icon": "mdi-magnify",
                        placeholder: "按标题 / hash 过滤",
                        class: "magicflow-keep-search",
                        clearable: ""
                      }, null, 8, ["modelValue"]),
                      _createVNode$D(_component_VSelect, {
                        modelValue: candSite.value,
                        "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((candSite).value = $event)),
                        items: [{ title: '全部站点', value: '' }, ...candSites.value.map(s => ({ title: s, value: s }))],
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        class: "magicflow-keep-site"
                      }, null, 8, ["modelValue", "items"]),
                      _createVNode$D(_component_VSelect, {
                        modelValue: candSort.value,
                        "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((candSort).value = $event)),
                        items: [
                { title: '按站点', value: 'site' },
                { title: '按体积', value: 'size' },
                { title: '欠 H&R 优先', value: 'hr' },
              ],
                        density: "compact",
                        variant: "outlined",
                        "hide-details": "",
                        class: "magicflow-keep-sort"
                      }, null, 8, ["modelValue"]),
                      (candHrN.value)
                        ? (_openBlock$E(), _createBlock$B(_component_VChip, {
                            key: 0,
                            size: "small",
                            variant: candOnlyHr.value ? 'flat' : 'tonal',
                            color: candOnlyHr.value ? 'error' : 'default',
                            onClick: _cache[10] || (_cache[10] = $event => (candOnlyHr.value = !candOnlyHr.value))
                          }, {
                            default: _withCtx$B(() => [...(_cache[27] || (_cache[27] = [
                              _createTextVNode$D("只看欠 H&R", -1)
                            ]))]),
                            _: 1
                          }, 8, ["variant", "color"]))
                        : _createCommentVNode$z("", true),
                      (_openBlock$E(true), _createElementBlock$y(_Fragment$x, null, _renderList$v(__props.candSubs, (s) => {
                        return (_openBlock$E(), _createBlock$B(_component_VChip, {
                          key: s.key,
                          size: "small",
                          variant: candSub.value === s.key ? 'flat' : 'tonal',
                          color: candSub.value === s.key ? 'primary' : 'default',
                          onClick: $event => (candSub.value = candSub.value === s.key ? '' : s.key)
                        }, {
                          default: _withCtx$B(() => [
                            _createTextVNode$D(_toDisplayString$E(s.key) + "（" + _toDisplayString$E(s.count) + "）", 1)
                          ]),
                          _: 2
                        }, 1032, ["variant", "color", "onClick"]))
                      }), 128))
                    ]),
                    _createElementVNode$E("div", _hoisted_21$e, [
                      _createElementVNode$E("div", _hoisted_22$d, [
                        _createVNode$D(_component_VCheckbox, {
                          "model-value": __props.candRows.length > 0 && __props.candSelOnPage >= __props.candRows.length,
                          indeterminate: __props.candSelOnPage > 0 && __props.candSelOnPage < __props.candRows.length,
                          density: "compact",
                          "hide-details": "",
                          "aria-label": "全选本页",
                          "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => (emit('cand-toggle-page')))
                        }, null, 8, ["model-value", "indeterminate"]),
                        _createElementVNode$E("span", null, "本页 " + _toDisplayString$E(__props.candRows.length) + " 条 · 筛选出 " + _toDisplayString$E(__props.candList.length) + " 条", 1),
                        _createVNode$D(_component_VSpacer),
                        _createVNode$D(_component_VBtn, {
                          size: "small",
                          variant: "text",
                          disabled: __props.candLoading || !__props.candList.length,
                          onClick: _cache[12] || (_cache[12] = $event => (emit('cand-toggle-all')))
                        }, {
                          default: _withCtx$B(() => [
                            _createTextVNode$D("全选筛选结果（" + _toDisplayString$E(__props.candList.length) + "）", 1)
                          ]),
                          _: 1
                        }, 8, ["disabled"]),
                        (__props.candSel.length)
                          ? (_openBlock$E(), _createBlock$B(_component_VBtn, {
                              key: 0,
                              size: "small",
                              variant: "text",
                              onClick: _cache[13] || (_cache[13] = $event => (emit('cand-clear')))
                            }, {
                              default: _withCtx$B(() => [...(_cache[28] || (_cache[28] = [
                                _createTextVNode$D("清空", -1)
                              ]))]),
                              _: 1
                            }))
                          : _createCommentVNode$z("", true),
                        _createVNode$D(_component_VBtn, {
                          size: "small",
                          variant: bulkWarn.value ? 'flat' : 'tonal',
                          color: bulkWarn.value ? 'warning' : 'primary',
                          disabled: __props.busy || !__props.candSel.length,
                          "prepend-icon": "mdi-pin",
                          onClick: _cache[14] || (_cache[14] = $event => (emit('cand-hold')))
                        }, {
                          default: _withCtx$B(() => [
                            _createTextVNode$D("挂保种（" + _toDisplayString$E(__props.candSel.length) + "）", 1)
                          ]),
                          _: 1
                        }, 8, ["variant", "color", "disabled"])
                      ]),
                      (bulkWarn.value)
                        ? (_openBlock$E(), _createElementBlock$y("div", _hoisted_23$c, " 一次挂 " + _toDisplayString$E(__props.candSel.length) + " 个（" + _toDisplayString$E(sizeText(__props.candSelGb)) + "）会同时 force start 做种， 上传带宽会被占满。建议按站分批挂，挂完再挑下一批。 ", 1))
                        : _createCommentVNode$z("", true),
                      (_openBlock$E(true), _createElementBlock$y(_Fragment$x, null, _renderList$v(__props.candRows, (it) => {
                        return (_openBlock$E(), _createElementBlock$y("article", {
                          key: it.hash,
                          class: _normalizeClass$k(["magicflow-keep-row", { 'is-sel': __props.candSel.includes(it.hash) }])
                        }, [
                          _createVNode$D(_component_VCheckbox, {
                            "model-value": __props.candSel.includes(it.hash),
                            density: "compact",
                            "hide-details": "",
                            "aria-label": `选择 ${it.title || it.hash}`,
                            "onUpdate:modelValue": $event => (emit('cand-toggle-row', it.hash))
                          }, null, 8, ["model-value", "aria-label", "onUpdate:modelValue"]),
                          _createElementVNode$E("div", _hoisted_24$c, [
                            _createElementVNode$E("div", {
                              class: "magicflow-keep-row__name",
                              title: it.title || it.hash
                            }, _toDisplayString$E(it.title || it.hash), 9, _hoisted_25$c),
                            _createElementVNode$E("div", _hoisted_26$a, [
                              _createVNode$D(_component_VChip, {
                                size: "x-small",
                                variant: "tonal",
                                color: "primary"
                              }, {
                                default: _withCtx$B(() => [
                                  _createTextVNode$D(_toDisplayString$E(it.site_name || it.site || '—'), 1)
                                ]),
                                _: 2
                              }, 1024),
                              _createVNode$D(_component_VChip, {
                                size: "x-small",
                                variant: "flat",
                                color: candState(it).color
                              }, {
                                default: _withCtx$B(() => [
                                  _createTextVNode$D(_toDisplayString$E(candState(it).text), 1)
                                ]),
                                _: 2
                              }, 1032, ["color"]),
                              (it.owed_hr)
                                ? (_openBlock$E(), _createBlock$B(_component_VChip, {
                                    key: 0,
                                    size: "x-small",
                                    variant: "flat",
                                    color: "error"
                                  }, {
                                    default: _withCtx$B(() => [...(_cache[29] || (_cache[29] = [
                                      _createTextVNode$D("欠 H&R", -1)
                                    ]))]),
                                    _: 1
                                  }))
                                : _createCommentVNode$z("", true),
                              _createElementVNode$E("span", _hoisted_27$a, _toDisplayString$E(sizeText(it.size_gb)), 1),
                              _createElementVNode$E("span", _hoisted_28$9, _toDisplayString$E((it.hash || '').slice(0, 12)), 1),
                              (it.sub)
                                ? (_openBlock$E(), _createElementBlock$y("span", _hoisted_29$9, _toDisplayString$E(it.sub), 1))
                                : _createCommentVNode$z("", true)
                            ])
                          ]),
                          _createVNode$D(_component_VBtn, {
                            size: "small",
                            variant: "text",
                            color: "primary",
                            disabled: __props.busy,
                            "aria-label": `只挂这一条 ${it.title || it.hash}`,
                            icon: "mdi-pin",
                            onClick: $event => (emit('cand-hold', [it.hash]))
                          }, null, 8, ["disabled", "aria-label", "onClick"])
                        ], 2))
                      }), 128)),
                      (__props.candLoading)
                        ? (_openBlock$E(), _createElementBlock$y("div", _hoisted_30$9, "正在读取静默池…"))
                        : (!__props.candRows.length)
                          ? (_openBlock$E(), _createElementBlock$y("div", _hoisted_31$9, _toDisplayString$E(candTotal.value ? '当前过滤下没有匹配的种' : '静默池是空的（池子里的种都已挂上或不在下载器）'), 1))
                          : _createCommentVNode$z("", true),
                      (__props.candPages > 1)
                        ? (_openBlock$E(), _createElementBlock$y("div", _hoisted_32$9, [
                            _createVNode$D(_component_VBtn, {
                              size: "small",
                              variant: "text",
                              disabled: __props.candPage <= 1,
                              "prepend-icon": "mdi-chevron-left",
                              onClick: _cache[15] || (_cache[15] = $event => (emit('cand-goto', __props.candPage - 1)))
                            }, {
                              default: _withCtx$B(() => [...(_cache[30] || (_cache[30] = [
                                _createTextVNode$D("上一页", -1)
                              ]))]),
                              _: 1
                            }, 8, ["disabled"]),
                            _createElementVNode$E("span", null, "第 " + _toDisplayString$E(__props.candPage) + " / " + _toDisplayString$E(__props.candPages) + " 页", 1),
                            _createVNode$D(_component_VBtn, {
                              size: "small",
                              variant: "text",
                              disabled: __props.candPage >= __props.candPages,
                              "append-icon": "mdi-chevron-right",
                              onClick: _cache[16] || (_cache[16] = $event => (emit('cand-goto', __props.candPage + 1)))
                            }, {
                              default: _withCtx$B(() => [...(_cache[31] || (_cache[31] = [
                                _createTextVNode$D("下一页", -1)
                              ]))]),
                              _: 1
                            }, 8, ["disabled"])
                          ]))
                        : _createCommentVNode$z("", true)
                    ]),
                    _cache[32] || (_cache[32] = _createElementVNode$E("div", { class: "magicflow-settings-hint mt-2" }, [
                      _createTextVNode$D(" 这里列出"),
                      _createElementVNode$E("b", null, "静默池里所有能挂的种"),
                      _createTextVNode$D("（不在下载器的幽灵行不出现 —— 挂上也做不了种）。 「挂保种」= 挪进 "),
                      _createElementVNode$E("code", null, "__keep__"),
                      _createTextVNode$D(" 并 force start 开始做种，静默闸 / 清理闸 / H&R 保种都不会再来收它。已挂在名下的种不在此列（去「已保种」页看）。 ")
                    ], -1))
                  ], 64))
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
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于给组件挂 __scopeId 属性；
// 这里手写，避免引入 rollup 的私有辅助函数。渲染时 Vue 会给元素加 data-v-39c7e08d，
// 与下面 keep.css 里的选择器对齐（样式与线上完全一致）。
const KeepDialog = Object.assign(_sfc_main$E, { __scopeId: 'data-v-39c7e08d' })

export default KeepDialog
