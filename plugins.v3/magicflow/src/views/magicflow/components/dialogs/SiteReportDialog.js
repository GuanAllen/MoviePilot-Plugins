// SiteReportDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './SiteReportDialog.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$s,
  createBlock: _createBlock$t,
  createCommentVNode: _createCommentVNode$t,
  createElementBlock: _createElementBlock$s,
  createElementVNode: _createElementVNode$w,
  createTextVNode: _createTextVNode$v,
  createVNode: _createVNode$v,
  mergeModels: _mergeModels$f,
  openBlock: _openBlock$w,
  renderList: _renderList$q,
  resolveComponent: _resolveComponent$w,
  toDisplayString: _toDisplayString$w,
  unref: _unref$g,
  useModel: _useModel$f,
  withCtx: _withCtx$t,
} = __vue

import index from '../../index.vue'
import { SITE_REPORT_BUCKETS, SITE_REPORT_ORIGINS, SITE_REPORT_SILENT_SUBS, SITE_REPORT_TRANSPORT } from '../../constants.js'
import { currencyOf } from '../../composables/useCurrency.js'
import { levelNextText } from '../../format.js'
import { siteReportBucketColor, siteReportItemSub, siteReportTransportCount, useSiteReport } from '../../composables/useSiteReport.js'

const _hoisted_1$u = { class: "magicflow-settings-dialog__head" };
const _hoisted_2$s = { class: "magicflow-ops-dialog__sub magicflow-sitereport__bar" };
const _hoisted_3$r = { class: "magicflow-ops-dialog__body" };
const _hoisted_4$r = { class: "magicflow-sitereport__live" };
const _hoisted_5$r = { class: "magicflow-sitereport__live-head" };
const _hoisted_6$q = {
  key: 0,
  class: "magicflow-sitereport__live-uid"
};
const _hoisted_7$o = {
  key: 0,
  class: "magicflow-sitereport__live-grid"
};
const _hoisted_8$m = { class: "magicflow-sitereport__live-cell" };
const _hoisted_9$k = { class: "magicflow-sitereport__live-cell" };
const _hoisted_10$k = { class: "magicflow-sitereport__live-cell" };
const _hoisted_11$j = { class: "magicflow-sitereport__live-cell" };
const _hoisted_12$j = { class: "magicflow-sitereport__live-cell" };
const _hoisted_13$h = ["title"];
const _hoisted_14$g = ["title"];
const _hoisted_15$g = ["title"];
const _hoisted_16$g = {
  key: 1,
  class: "magicflow-sitereport__live-gap"
};
const _hoisted_17$g = {
  key: 2,
  class: "magicflow-sitereport__live-empty"
};
const _hoisted_18$g = {
  key: 3,
  class: "magicflow-sitereport__live-empty"
};
const _hoisted_19$f = { class: "magicflow-sitereport__stats" };
const _hoisted_20$d = {
  class: "magicflow-sitereport__stat",
  title: "该站点在本机下载器里的全部种（做种/下载/暂停/静默）"
};
const _hoisted_21$c = { class: "magicflow-sitereport__stat" };
const _hoisted_22$b = { class: "magicflow-sitereport__stat is-danger" };
const _hoisted_23$a = { class: "magicflow-sitereport__stat is-danger" };
const _hoisted_24$a = { class: "magicflow-sitereport__chips" };
const _hoisted_25$a = { class: "magicflow-sitereport__chips magicflow-sitereport__chips--l2" };
const _hoisted_26$8 = {
  key: 0,
  class: "magicflow-sitereport__chips magicflow-sitereport__chips--l2"
};
const _hoisted_27$8 = {
  key: 1,
  class: "magicflow-sitereport__chips magicflow-sitereport__chips--l2"
};
const _hoisted_28$7 = { class: "magicflow-ops-dialog__sub" };
const _hoisted_29$7 = {
  key: 2,
  class: "magicflow-sitereport__err"
};
const _hoisted_30$7 = {
  key: 3,
  class: "magicflow-sitereport__note"
};
const _hoisted_31$7 = { class: "magicflow-sitereport__list" };
const _hoisted_32$7 = { class: "magicflow-sitereport__row-main" };
const _hoisted_33$6 = ["title"];
const _hoisted_34$6 = { class: "magicflow-sitereport__row-s" };
const _hoisted_35$5 = { class: "magicflow-sitereport__row-size" };
const _hoisted_36$4 = {
  key: 0,
  class: "magicflow-ceiling-empty"
};
const {computed: computed$F} = __vue;


const _sfc_main$w = {
  __name: 'SiteReportDialog',
  props: /*@__PURE__*/_mergeModels$f({
  loading: { type: Boolean, default: false },
  live: { type: Boolean, default: false },
  liveLoading: { type: Boolean, default: false },
  liveStats: { type: Object, default: () => null },
  report: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  items: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
  narrow: { type: Boolean, default: false },
  siteBonus: { type: Number, default: null },
  // ★ 19.10.48：该站对「魔力」的自称（蟹币值/金元宝/积分…），空串兜底「魔力值」
  siteCurrency: { type: String, default: '' },
}, {
    "modelValue": { type: Boolean, default: false },
    "modelModifiers": {},
    "site": { type: String, default: '' },
    "siteModifiers": {},
    "filter": { type: String, default: '' },
    "filterModifiers": {},
    "transport": { type: String, default: '' },
    "transportModifiers": {},
    "sub": { type: String, default: '' },
    "subModifiers": {},
    "origin": { type: String, default: '' },
    "originModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$f(['refresh', 'live', 'change'], ["update:modelValue", "update:site", "update:filter", "update:transport", "update:sub", "update:origin"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 站点报表弹窗（11.10.0）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
// 展示用纯函数（siteReportBucketColor / siteReportItemSub / siteReportTransportCount）自
// composables/useSiteReport.js 具名导入复用 —— 单一真值源，不在两处各写一份。
const open = _useModel$f(__props, "modelValue");
const site = _useModel$f(__props, 'site');
const filter = _useModel$f(__props, 'filter');
const transport = _useModel$f(__props, 'transport');
const sub = _useModel$f(__props, 'sub');
const origin = _useModel$f(__props, 'origin');

const props = __props;

const emit = __emit;

// ★ 15.16.0 站点流量块：展示用格式化（分享率 2 位 / 字节→G / 数字千分位）
const liveRatio = computed$F(() => {
  const s = props.liveStats || {};
  if (s.ratio_inf) return '∞'   // ★ 15.16.1：站点下载=0 → 页面显示「无限」，照实呈现
  const v = s.ratio;
  return v === null || v === undefined ? '—' : Number(v).toFixed(2)
});
// ★ 19.10.39「魔力/时」：任务侧时魔优先（与任务详情同源，站点自报 > 本地实测），
//   其次才用 /live 的实测值；都没有 → null（模板显示「—」，绝不画成 0）。
const bonusPerHour = computed$F(() => {
  if (props.siteBonus != null) return props.siteBonus
  const s = props.liveStats || {};
  return s.bonus_per_hour == null ? null : s.bonus_per_hour
});
// ★ 19.10.48：站点货币名（各站不同：蟹币值 / 金元宝 / 积分…）
const currencyName = computed$F(() => currencyOf(props.siteCurrency));
const bonusPerHourHint = computed$F(() => {
  if (props.siteBonus != null) return '站点上报时魔（与任务详情同一口径）'
  const s = props.liveStats || {};
  if (s.bonus_per_hour_source === 'observed') return '本地采样折算（该站未提供时魔接口），不是站点自报值'
  return ''
});
// ★ 19.11.20：等级 / 下一级（与任务概览同一口径：只报站点自己说的，认不出写「未知」；
//   差值文案走 format.js::levelNextText 共用出口，不在两处各写一份）。
const levelName = computed$F(() => (props.liveStats || {}).level || '未知');
const levelNextName = computed$F(() => ((props.liveStats || {}).level_next || {}).name || '—');
const levelGapText = computed$F(() => levelNextText((props.liveStats || {}).level_next, currencyName.value));
function liveGb(bytes) {
  const n = Number(bytes || 0);
  if (!n) return '0'
  return `${(n / 1024 / 1024 / 1024).toFixed(1)}G`
}
function liveNum(v) {
  // ★ 19.10.39：null（压根没取到）不能画成 0 —— 那看着像「时魔就是 0」，与「不知道」是两件事
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v);
  return Number.isFinite(n) ? (Math.round(n * 10) / 10).toLocaleString('en-US') : '—'
}

return (_ctx, _cache) => {
  const _component_VChip = _resolveComponent$w("VChip");
  const _component_VBtn = _resolveComponent$w("VBtn");
  const _component_VSelect = _resolveComponent$w("VSelect");
  const _component_VCard = _resolveComponent$w("VCard");
  const _component_VDialog = _resolveComponent$w("VDialog");

  return (_openBlock$w(), _createBlock$t(_component_VDialog, {
    modelValue: open.value,
    "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((open).value = $event)),
    "max-width": "48rem",
    scrollable: "",
    fullscreen: __props.narrow
  }, {
    default: _withCtx$t(() => [
      _createVNode$v(_component_VCard, { class: "magicflow-dialog magicflow-sitereport-dialog" }, {
        default: _withCtx$t(() => [
          _createElementVNode$w("header", _hoisted_1$u, [
            _cache[11] || (_cache[11] = _createElementVNode$w("span", { class: "magicflow-settings-dialog__title" }, "站点报表", -1)),
            (__props.loading)
              ? (_openBlock$w(), _createBlock$t(_component_VChip, {
                  key: 0,
                  size: "x-small",
                  color: "grey",
                  variant: "tonal"
                }, {
                  default: _withCtx$t(() => [...(_cache[10] || (_cache[10] = [
                    _createTextVNode$v("加载中", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode$t("", true),
            _cache[12] || (_cache[12] = _createElementVNode$w("span", { class: "magicflow-ops-dialog__spacer" }, null, -1)),
            _createVNode$v(_component_VBtn, {
              icon: "mdi-refresh",
              size: "small",
              variant: "text",
              "aria-label": "刷新",
              loading: __props.loading,
              onClick: _cache[0] || (_cache[0] = $event => (emit('refresh')))
            }, null, 8, ["loading"]),
            _createVNode$v(_component_VBtn, {
              icon: "mdi-close",
              size: "small",
              variant: "text",
              "aria-label": "关闭",
              onClick: _cache[1] || (_cache[1] = $event => (open.value = false))
            })
          ]),
          _createElementVNode$w("div", _hoisted_2$s, [
            _createVNode$v(_component_VSelect, {
              modelValue: site.value,
              "onUpdate:modelValue": [
                _cache[2] || (_cache[2] = $event => ((site).value = $event)),
                _cache[3] || (_cache[3] = $event => (emit('change')))
              ],
              items: __props.sites.map(s => ({ title: `${s.name || s.domain}${s.domain ? ' · ' + s.domain : ''}`, value: s.domain || s.name })),
              density: "compact",
              variant: "outlined",
              "hide-details": "",
              class: "magicflow-sitereport__site"
            }, null, 8, ["modelValue", "items"]),
            _createVNode$v(_component_VBtn, {
              size: "small",
              variant: "tonal",
              "prepend-icon": __props.live ? 'mdi-radar' : 'mdi-cloud-download-outline',
              loading: __props.loading,
              onClick: _cache[4] || (_cache[4] = $event => (emit('live')))
            }, {
              default: _withCtx$t(() => [...(_cache[13] || (_cache[13] = [
                _createTextVNode$v("H&R 现抓", -1)
              ]))]),
              _: 1
            }, 8, ["prepend-icon", "loading"])
          ]),
          _createElementVNode$w("div", _hoisted_3$r, [
            _createElementVNode$w("div", _hoisted_4$r, [
              _createElementVNode$w("div", _hoisted_5$r, [
                _cache[15] || (_cache[15] = _createElementVNode$w("span", { class: "magicflow-sitereport__live-t" }, "站点流量", -1)),
                (__props.liveLoading)
                  ? (_openBlock$w(), _createBlock$t(_component_VChip, {
                      key: 0,
                      size: "x-small",
                      color: "grey",
                      variant: "tonal"
                    }, {
                      default: _withCtx$t(() => [...(_cache[14] || (_cache[14] = [
                        _createTextVNode$v("加载中", -1)
                      ]))]),
                      _: 1
                    }))
                  : (__props.liveStats)
                    ? (_openBlock$w(), _createElementBlock$s(_Fragment$s, { key: 1 }, [
                        _createVNode$v(_component_VChip, {
                          size: "x-small",
                          color: __props.liveStats.logged_in ? 'success' : 'warning',
                          variant: "tonal"
                        }, {
                          default: _withCtx$t(() => [
                            _createTextVNode$v(_toDisplayString$w(__props.liveStats.logged_in ? '已登录' : '未登录'), 1)
                          ]),
                          _: 1
                        }, 8, ["color"]),
                        (__props.liveStats.uid)
                          ? (_openBlock$w(), _createElementBlock$s("span", _hoisted_6$q, "UID " + _toDisplayString$w(__props.liveStats.uid), 1))
                          : _createCommentVNode$t("", true)
                      ], 64))
                    : _createCommentVNode$t("", true)
              ]),
              (__props.liveStats && __props.liveStats.ok)
                ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_7$o, [
                    _createElementVNode$w("div", _hoisted_8$m, [
                      _createElementVNode$w("b", null, _toDisplayString$w(liveRatio.value), 1),
                      _cache[16] || (_cache[16] = _createElementVNode$w("span", null, "分享率", -1))
                    ]),
                    _createElementVNode$w("div", _hoisted_9$k, [
                      _createElementVNode$w("b", null, _toDisplayString$w(liveGb(__props.liveStats.upload)), 1),
                      _cache[17] || (_cache[17] = _createElementVNode$w("span", null, "上传", -1))
                    ]),
                    _createElementVNode$w("div", _hoisted_10$k, [
                      _createElementVNode$w("b", null, _toDisplayString$w(liveGb(__props.liveStats.download)), 1),
                      _cache[18] || (_cache[18] = _createElementVNode$w("span", null, "下载", -1))
                    ]),
                    _createElementVNode$w("div", _hoisted_11$j, [
                      _createElementVNode$w("b", null, _toDisplayString$w(liveNum(__props.liveStats.bonus)), 1),
                      _createElementVNode$w("span", null, "当前" + _toDisplayString$w(currencyName.value), 1)
                    ]),
                    _createElementVNode$w("div", _hoisted_12$j, [
                      _createElementVNode$w("b", null, _toDisplayString$w(liveNum(__props.liveStats.seeding)), 1),
                      _cache[19] || (_cache[19] = _createElementVNode$w("span", null, "做种", -1))
                    ]),
                    _createElementVNode$w("div", {
                      class: "magicflow-sitereport__live-cell",
                      title: bonusPerHourHint.value
                    }, [
                      _createElementVNode$w("b", null, _toDisplayString$w(liveNum(bonusPerHour.value)), 1),
                      _createElementVNode$w("span", null, _toDisplayString$w(currencyName.value) + "/时", 1)
                    ], 8, _hoisted_13$h),
                    _createElementVNode$w("div", {
                      class: "magicflow-sitereport__live-cell",
                      title: __props.liveStats.level || '站点未报等级'
                    }, [
                      _createElementVNode$w("b", null, _toDisplayString$w(levelName.value), 1),
                      _cache[20] || (_cache[20] = _createElementVNode$w("span", null, "等级", -1))
                    ], 8, _hoisted_14$g),
                    _createElementVNode$w("div", {
                      class: "magicflow-sitereport__live-cell",
                      title: levelGapText.value
                    }, [
                      _createElementVNode$w("b", null, _toDisplayString$w(levelNextName.value), 1),
                      _cache[21] || (_cache[21] = _createElementVNode$w("span", null, "下一级", -1))
                    ], 8, _hoisted_15$g)
                  ]))
                : _createCommentVNode$t("", true),
              (levelGapText.value)
                ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_16$g, "距 " + _toDisplayString$w(levelNextName.value) + "：" + _toDisplayString$w(levelGapText.value), 1))
                : (!__props.liveLoading && __props.liveStats && __props.liveStats.warming)
                  ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_17$g, "取数中…（实时数据正在后台补齐，稍候自动刷新）"))
                  : (!__props.liveLoading)
                    ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_18$g, "暂无实时账号数据（站点未登录或取数失败）"))
                    : _createCommentVNode$t("", true)
            ]),
            _createElementVNode$w("div", _hoisted_19$f, [
              _createElementVNode$w("div", _hoisted_20$d, [
                _createElementVNode$w("b", null, _toDisplayString$w(__props.summary.total || 0), 1),
                _cache[22] || (_cache[22] = _createElementVNode$w("span", null, "本站种子", -1))
              ]),
              _createElementVNode$w("div", _hoisted_21$c, [
                _createElementVNode$w("b", null, _toDisplayString$w((__props.summary.size_gb || 0).toFixed(1)), 1),
                _cache[23] || (_cache[23] = _createElementVNode$w("span", null, "GB", -1))
              ]),
              _createElementVNode$w("div", _hoisted_22$b, [
                _createElementVNode$w("b", null, _toDisplayString$w(__props.summary.hr_owed || 0), 1),
                _cache[24] || (_cache[24] = _createElementVNode$w("span", null, "欠 H&R", -1))
              ]),
              _createElementVNode$w("div", _hoisted_23$a, [
                _createElementVNode$w("b", null, _toDisplayString$w(__props.summary.hr_missing || 0), 1),
                _cache[25] || (_cache[25] = _createElementVNode$w("span", null, "本机缺失", -1))
              ])
            ]),
            _createElementVNode$w("div", _hoisted_24$a, [
              _createVNode$v(_component_VChip, {
                size: "small",
                color: filter.value ? 'grey' : 'primary',
                variant: filter.value ? 'tonal' : 'flat',
                style: {"cursor":"pointer"},
                onClick: _cache[5] || (_cache[5] = $event => (filter.value = ''))
              }, {
                default: _withCtx$t(() => [
                  _createTextVNode$v("全部 " + _toDisplayString$w(__props.summary.total || 0), 1)
                ]),
                _: 1
              }, 8, ["color", "variant"]),
              (_openBlock$w(true), _createElementBlock$s(_Fragment$s, null, _renderList$q(_unref$g(SITE_REPORT_BUCKETS), (b) => {
                return (_openBlock$w(), _createBlock$t(_component_VChip, {
                  key: b.key,
                  size: "small",
                  color: b.color,
                  variant: filter.value === b.key ? 'flat' : 'tonal',
                  style: {"cursor":"pointer"},
                  onClick: $event => (filter.value = filter.value === b.key ? '' : b.key)
                }, {
                  default: _withCtx$t(() => [
                    _createTextVNode$v(_toDisplayString$w(b.key) + " " + _toDisplayString$w((__props.summary.by_bucket || {})[b.key] || 0), 1)
                  ]),
                  _: 2
                }, 1032, ["color", "variant", "onClick"]))
              }), 128))
            ]),
            _createElementVNode$w("div", _hoisted_25$a, [
              _cache[27] || (_cache[27] = _createElementVNode$w("span", { class: "magicflow-sitereport__chip-label" }, "传输", -1)),
              _createVNode$v(_component_VChip, {
                size: "small",
                color: transport.value ? 'grey' : 'primary',
                variant: transport.value ? 'tonal' : 'flat',
                style: {"cursor":"pointer"},
                onClick: _cache[6] || (_cache[6] = $event => (transport.value = ''))
              }, {
                default: _withCtx$t(() => [...(_cache[26] || (_cache[26] = [
                  _createTextVNode$v("全部", -1)
                ]))]),
                _: 1
              }, 8, ["color", "variant"]),
              (_openBlock$w(true), _createElementBlock$s(_Fragment$s, null, _renderList$q(_unref$g(SITE_REPORT_TRANSPORT), (tr) => {
                return (_openBlock$w(), _createBlock$t(_component_VChip, {
                  key: tr.key,
                  size: "small",
                  color: tr.color,
                  variant: transport.value === tr.key ? 'flat' : 'tonal',
                  style: {"cursor":"pointer"},
                  onClick: $event => (transport.value = transport.value === tr.key ? '' : tr.key)
                }, {
                  default: _withCtx$t(() => [
                    _createTextVNode$v(_toDisplayString$w(tr.key) + " " + _toDisplayString$w(_unref$g(siteReportTransportCount)(tr.key, __props.summary, filter.value)), 1)
                  ]),
                  _: 2
                }, 1032, ["color", "variant", "onClick"]))
              }), 128))
            ]),
            (filter.value === '静默')
              ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_26$8, [
                  _cache[29] || (_cache[29] = _createElementVNode$w("span", { class: "magicflow-sitereport__chip-label" }, "身份", -1)),
                  _createVNode$v(_component_VChip, {
                    size: "small",
                    color: sub.value ? 'grey' : 'primary',
                    variant: sub.value ? 'tonal' : 'flat',
                    style: {"cursor":"pointer"},
                    onClick: _cache[7] || (_cache[7] = $event => (sub.value = ''))
                  }, {
                    default: _withCtx$t(() => [...(_cache[28] || (_cache[28] = [
                      _createTextVNode$v("全部", -1)
                    ]))]),
                    _: 1
                  }, 8, ["color", "variant"]),
                  (_openBlock$w(true), _createElementBlock$s(_Fragment$s, null, _renderList$q(_unref$g(SITE_REPORT_SILENT_SUBS), (s) => {
                    return (_openBlock$w(), _createBlock$t(_component_VChip, {
                      key: s.key,
                      size: "small",
                      color: s.color,
                      variant: sub.value === s.key ? 'flat' : 'tonal',
                      style: {"cursor":"pointer"},
                      onClick: $event => (sub.value = sub.value === s.key ? '' : s.key)
                    }, {
                      default: _withCtx$t(() => [
                        _createTextVNode$v(_toDisplayString$w(s.key) + " " + _toDisplayString$w((__props.summary.silent_by_sub || {})[s.key] || 0), 1)
                      ]),
                      _: 2
                    }, 1032, ["color", "variant", "onClick"]))
                  }), 128))
                ]))
              : _createCommentVNode$t("", true),
            (filter.value === '静默')
              ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_27$8, [
                  _cache[31] || (_cache[31] = _createElementVNode$w("span", { class: "magicflow-sitereport__chip-label" }, "出身", -1)),
                  _createVNode$v(_component_VChip, {
                    size: "small",
                    color: origin.value ? 'grey' : 'primary',
                    variant: origin.value ? 'tonal' : 'flat',
                    style: {"cursor":"pointer"},
                    onClick: _cache[8] || (_cache[8] = $event => (origin.value = ''))
                  }, {
                    default: _withCtx$t(() => [...(_cache[30] || (_cache[30] = [
                      _createTextVNode$v("全部", -1)
                    ]))]),
                    _: 1
                  }, 8, ["color", "variant"]),
                  (_openBlock$w(true), _createElementBlock$s(_Fragment$s, null, _renderList$q(_unref$g(SITE_REPORT_ORIGINS), (s) => {
                    return (_openBlock$w(), _createBlock$t(_component_VChip, {
                      key: s.key,
                      size: "small",
                      color: s.color,
                      variant: origin.value === s.key ? 'flat' : 'tonal',
                      style: {"cursor":"pointer"},
                      onClick: $event => (origin.value = origin.value === s.key ? '' : s.key)
                    }, {
                      default: _withCtx$t(() => [
                        _createTextVNode$v(_toDisplayString$w(s.key) + " " + _toDisplayString$w((__props.summary.silent_origin || {})[s.key] || 0), 1)
                      ]),
                      _: 2
                    }, 1032, ["color", "variant", "onClick"]))
                  }), 128))
                ]))
              : _createCommentVNode$t("", true),
            _createElementVNode$w("div", _hoisted_28$7, " 明细 " + _toDisplayString$w(__props.items.length) + " / " + _toDisplayString$w(__props.summary.total || 0) + _toDisplayString$w((filter.value || transport.value || sub.value || origin.value) ? ' · 已筛选' : ' · 点分类可筛选'), 1),
            (__props.report.hr && __props.report.hr.error)
              ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_29$7, " H&R 对账（" + _toDisplayString$w(__props.report.hr.source) + "）：" + _toDisplayString$w(__props.report.hr.error), 1))
              : (__props.report.hr && __props.report.hr.records_total != null)
                ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_30$7, " H&R 对账（" + _toDisplayString$w(__props.report.hr.source) + "）：站点欠 " + _toDisplayString$w(__props.report.hr.records_total) + " 条，本机缺失 " + _toDisplayString$w(__props.report.hr.missing) + " 条" + _toDisplayString$w(__props.report.hr.hash_coverage_complete ? '' : '（部分未覆盖）'), 1))
                : _createCommentVNode$t("", true),
            _createElementVNode$w("div", _hoisted_31$7, [
              (_openBlock$w(true), _createElementBlock$s(_Fragment$s, null, _renderList$q(__props.items, (it) => {
                return (_openBlock$w(), _createElementBlock$s("div", {
                  key: it.hash,
                  class: "magicflow-sitereport__row"
                }, [
                  _createVNode$v(_component_VChip, {
                    size: "x-small",
                    color: _unref$g(siteReportBucketColor)(it.bucket),
                    variant: "tonal",
                    class: "magicflow-sitereport__row-b"
                  }, {
                    default: _withCtx$t(() => [
                      _createTextVNode$v(_toDisplayString$w(it.bucket), 1)
                    ]),
                    _: 2
                  }, 1032, ["color"]),
                  _createElementVNode$w("div", _hoisted_32$7, [
                    _createElementVNode$w("div", {
                      class: "magicflow-sitereport__row-t",
                      title: it.title
                    }, _toDisplayString$w(it.title || it.hash), 9, _hoisted_33$6),
                    _createElementVNode$w("div", _hoisted_34$6, _toDisplayString$w(_unref$g(siteReportItemSub)(it)), 1)
                  ]),
                  _createElementVNode$w("span", _hoisted_35$5, _toDisplayString$w((it.size_gb || 0).toFixed(2)) + "G", 1)
                ]))
              }), 128)),
              (!__props.loading && !__props.items.length)
                ? (_openBlock$w(), _createElementBlock$s("div", _hoisted_36$4, "该站点暂无种子（或未选择站点）"))
                : _createCommentVNode$t("", true)
            ])
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
const SiteReportDialog = Object.assign(_sfc_main$w, { __scopeId: 'data-v-83d60f7e' })

export default SiteReportDialog
