// MobileTaskDetail —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './MobileTaskDetail.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$f,
  createCommentVNode: _createCommentVNode$f,
  createElementBlock: _createElementBlock$f,
  createElementVNode: _createElementVNode$i,
  createTextVNode: _createTextVNode$h,
  createVNode: _createVNode$h,
  normalizeClass: _normalizeClass$7,
  openBlock: _openBlock$i,
  renderList: _renderList$d,
  resolveComponent: _resolveComponent$i,
  toDisplayString: _toDisplayString$i,
  unref: _unref$8,
} = __vue

import index from '../index.vue'
import { MF_DETAIL_ENTRIES } from '../constants.js'
import { formatBytes, formatDateTime } from '../../../utils.js'
import { taskMetrics } from '../format.js'

const _hoisted_1$g = { class: "md-verdict__body" };
const _hoisted_2$e = { class: "md-v" };
const _hoisted_3$d = { class: "md-s" };
const _hoisted_4$d = { class: "md-cards" };
const _hoisted_5$d = { class: "md-strategy" };
const _hoisted_6$c = { class: "md-entries" };
const _hoisted_7$b = ["onClick"];

const {computed: computed$w} = __vue;


const _sfc_main$i = {
  __name: 'MobileTaskDetail',
  props: {
  task: { type: Object, default: null },
  state: { type: Object, default: () => ({}) },
  attention: { type: Object, default: null },
  stats: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  siteAccount: { type: Object, default: () => ({}) },
  activeTab: { type: String, default: '' },
},
  emits: ['entry', 'navigate'],
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 手机端任务详情紧凑块（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（模板内层 + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不直接调父方法。
// ★ 外层容器 <div class="magicflow-mobile-detail">（及其显隐 scoped 样式）留在父页，本组件只搬「内层内容」。
// 结论 + 三个数 + 策略一行 + 次级入口。
const props = __props;

const emit = __emit;

const mobileDetailCards = computed$w(() => {
  const t = props.task;
  if (!t) return []
  // ★ 19.11.0：走统一指标出口（主指标 = 考核目标），与桌面左栏 / 概览磁贴同口径。
  // 手机端只有 3 格，第 3 格固定给站点级数值（与第 2 格的任务级数值明确分层）。
  const m = taskMetrics(t);
  const cards = [{ v: String(m.seeds), k: '托管种' }];
  if (m.isBrush) {
    cards.push({ v: m.upload.text, k: '本任务上传' });
    cards.push({ v: props.siteAccount?.ok ? formatBytes(props.siteAccount.upload || 0) : '—', k: '站点上传' });
  } else {
    cards.push({ v: m.hourly.ok ? Number(m.hourly.value).toFixed(2) : '取数中…', k: '时魔 /h' });
    cards.push({ v: t.site_current_bonus != null ? Number(t.site_current_bonus).toFixed(0) : '—', k: '站点魔力' });
  }
  return cards
});

const mobileStrategyText = computed$w(() => {
  const t = props.task;
  if (!t) return ''
  const c = props.config || {};
  const parts = [t.task_type === 'brush' ? '刷流' : '刷魔力'];
  if (t.task_type === 'brush') {
    parts.push(`选种每 ${c.brush_interval ?? '—'} 分钟`);
    if (c.brush_seed_days) parts.push(`轮转 ${c.brush_seed_days} 天`);
  } else {
    parts.push(c.min_bonus_per_hour == null ? '最低魔力自动' : `最低魔力 ${Number(c.min_bonus_per_hour).toFixed(1)}/h`);
    parts.push(c.protect_perfect === false ? '完美种保护关' : '完美种保护开');
    if (t.protected_count) parts.push(`接管保护 ${t.protected_count}`);
  }
  const hr = Number(props.stats?.hr_owed ?? t.hr_owed ?? 0);
  if (hr > 0) parts.push(`H&R 欠 ${hr}`);
  return parts.join(' · ')
});

const mobileDetailHint = computed$w(() => {
  const d = props.stats || {};
  if (d.last_error) return `⚠ ${String(d.last_error).slice(0, 60)}`
  if (d.last_run_at) return `上次运行 ${formatDateTime(d.last_run_at)}`
  return '尚未运行'
});

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$i("VIcon");

  return (_openBlock$i(), _createElementBlock$f(_Fragment$f, null, [
    _createElementVNode$i("div", {
      class: _normalizeClass$7(["md-verdict", { 'is-warn': !!__props.attention }])
    }, [
      _createElementVNode$i("span", {
        class: _normalizeClass$7(["md-dot", `is-${__props.attention ? __props.attention.level : __props.state.color}`])
      }, null, 2),
      _createElementVNode$i("div", _hoisted_1$g, [
        _createElementVNode$i("div", _hoisted_2$e, [
          _createTextVNode$h(_toDisplayString$i(__props.attention ? __props.attention.text : __props.state.text), 1),
          (!__props.attention)
            ? (_openBlock$i(), _createElementBlock$f(_Fragment$f, { key: 0 }, [
                _createTextVNode$h(" · 无需操作")
              ], 64))
            : _createCommentVNode$f("", true)
        ]),
        _createElementVNode$i("div", _hoisted_3$d, _toDisplayString$i(__props.attention ? __props.attention.detail : mobileDetailHint.value), 1)
      ]),
      (__props.attention)
        ? (_openBlock$i(), _createElementBlock$f("button", {
            key: 0,
            type: "button",
            class: "md-act",
            onClick: _cache[0] || (_cache[0] = $event => (emit('navigate', 'diagnostics')))
          }, _toDisplayString$i(__props.attention.action), 1))
        : _createCommentVNode$f("", true)
    ], 2),
    _createElementVNode$i("div", _hoisted_4$d, [
      (_openBlock$i(true), _createElementBlock$f(_Fragment$f, null, _renderList$d(mobileDetailCards.value, (c) => {
        return (_openBlock$i(), _createElementBlock$f("div", {
          key: c.k,
          class: "md-card"
        }, [
          _createElementVNode$i("b", null, _toDisplayString$i(c.v), 1),
          _createElementVNode$i("span", null, _toDisplayString$i(c.k), 1)
        ]))
      }), 128))
    ]),
    _createElementVNode$i("div", _hoisted_5$d, _toDisplayString$i(mobileStrategyText.value), 1),
    _createElementVNode$i("div", _hoisted_6$c, [
      (_openBlock$i(true), _createElementBlock$f(_Fragment$f, null, _renderList$d(_unref$8(MF_DETAIL_ENTRIES), (e) => {
        return (_openBlock$i(), _createElementBlock$f("button", {
          key: e.key,
          type: "button",
          class: _normalizeClass$7(["md-entry", { 'is-active': __props.activeTab === e.key }]),
          onClick: $event => (emit('entry', e))
        }, [
          _createVNode$h(_component_VIcon, {
            icon: e.icon,
            size: "20"
          }, null, 8, ["icon"]),
          _createElementVNode$i("span", null, _toDisplayString$i(e.label), 1)
        ], 10, _hoisted_7$b))
      }), 128))
    ])
  ], 64))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const MobileTaskDetail = Object.assign(_sfc_main$i, { __scopeId: 'data-v-cc4581d6' })

export default MobileTaskDetail
