// ClaimConfirm —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './ClaimConfirm.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$w,
  createBlock: _createBlock$z,
  createCommentVNode: _createCommentVNode$x,
  createElementBlock: _createElementBlock$w,
  createElementVNode: _createElementVNode$C,
  createTextVNode: _createTextVNode$B,
  createVNode: _createVNode$B,
  mergeModels: _mergeModels$l,
  normalizeClass: _normalizeClass$j,
  openBlock: _openBlock$C,
  renderList: _renderList$u,
  resolveComponent: _resolveComponent$C,
  toDisplayString: _toDisplayString$C,
  useModel: _useModel$l,
  withCtx: _withCtx$z,
} = __vue


const _hoisted_1$y = {
  key: 2,
  class: "claim-confirm-abandon"
};
const _hoisted_2$w = { class: "claim-confirm-abandon__head" };
const _hoisted_3$u = {
  key: 0,
  class: "claim-confirm-abandon__why"
};
const _hoisted_4$u = { class: "claim-confirm-abandon__list" };
const _hoisted_5$u = {
  key: 3,
  class: "claim-confirm-penalty"
};
const _hoisted_6$s = { class: "claim-confirm-penalty__head" };
const _hoisted_7$q = { class: "claim-confirm-penalty__label" };
const _hoisted_8$o = {
  key: 0,
  class: "claim-confirm-penalty__meta"
};
const _hoisted_9$m = {
  key: 1,
  class: "claim-confirm-penalty__warn"
};
const _hoisted_10$m = {
  key: 5,
  class: "claim-confirm-abandon__note"
};

const {computed: computed$J} = __vue;



const _sfc_main$C = {
  __name: 'ClaimConfirm',
  props: /*@__PURE__*/_mergeModels$l({
  cfg: { type: Object, default: () => ({}) },
  acting: { type: Boolean, default: false },
}, {
    "modelValue": { type: [Object, null], default: null },
    "modelModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$l(['run'], ["update:modelValue"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 认领二次确认弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态 / 调父方法。
// 动作真值仍由父页（claimConfirmRun）持有：「确认」→ emit('run')；「取消」→ conf = null。
//
// ★ 19.10.52「认领前知情」：认领是**用户行为**且带罚则（咖啡 −3000 / Depth −1000 /
//   CARPT −100），确认前必须摆出**该站**的具体代价，不能只有一句「可能扣魔力」。
//   罚则取自 conf.profile.penalty（父页 claimAsk 从 sites[].profile 带入）。
const conf = _useModel$l(__props, "modelValue");



const emit = __emit;

const prof = computed$J(() => (conf.value && conf.value.profile) || {});
const isAbandon = computed$J(() => !!conf.value && conf.value.kind === 'abandon');

// 罚则三项：考核不达标 / 主动放弃 / 新人豁免。数值缺省则不显示该行（不臆造）。
const penaltyRows = computed$J(() => {
  const p = prof.value.penalty || {};
  const rows = [];
  if (p.unsatisfied) rows.push({ icon: 'mdi-alert-octagon-outline', label: '考核不达标', value: `−${p.unsatisfied}`, tone: 'error' });
  if (p.abandon) rows.push({ icon: 'mdi-close-octagon-outline', label: '主动放弃', value: `−${p.abandon}`, tone: 'warning' });
  if (p.exempt_days) rows.push({ icon: 'mdi-shield-check-outline', label: '新人豁免', value: `首 ${p.exempt_days} 天`, tone: 'success' });
  return rows
});
// 门槛与倍率：让用户知道「为什么这颗现在能领」「领了值不值」。
const gateText = computed$J(() => {
  const d = Number(prof.value.min_age_days || 0);
  return d > 0 ? `发布满 ${d} 天可认领` : ''
});
// ★ benefit 是契约码（``"bonus_x2"``），不是数字 —— 只从中取倍数，整句描述留给站点卡片。
const multText = computed$J(() => {
  const m = String(prof.value.benefit || '').match(/x(\d+)/i);
  return m ? `达标魔力 ×${m[1]}` : ''
});
// 规则未核对的站：数值是同族默认值，必须显式警示（不能让用户拿默认值当承诺）。
const unverified = computed$J(() => !!prof.value.rules_unverified);
const hasPenalty = computed$J(() => penaltyRows.value.length > 0);

// ★ 19.10.58 放弃认领：**只有安全时才允许走到这里**（按钮在后端判定 safe/grace 才可点）。
//   这一步不是「再吓一次」，而是把「为什么安全」讲清楚 —— 用户点确认前应当知道
//   放弃会失去什么（×2 奖励 / 硬保护），以及站点侧代价已被判定为 0。
const abandonRow = computed$J(() => (conf.value && conf.value.row) || {});
const abandonReason = computed$J(() => String(abandonRow.value.abandon_reason || ''));
const abandonIsGrace = computed$J(() => String(abandonRow.value.abandon_state || '') === 'grace');
const abandonFee = computed$J(() => Number(abandonRow.value.abandon_penalty || 0));
const abandonLoses = computed$J(() => {
  const p = prof.value.penalty || {};
  const out = ['站点侧认领会被取消，这颗不再计入本月 ×2 奖励'];
  // ★ 站点口径（咖啡 rules.php 原文）：「允许用户放弃认领的种子，每次每种子需支付 1000 咖啡豆」
  //   —— 放弃费与「是否达标」无关，必须单独摆出来，不能藏在「可能扣魔力」里。
  if (abandonFee.value > 0) out.push(`按站点规则支付 ${abandonFee.value} 放弃费（不退还）`);
  out.push('本地「硬保护」随之解除（可以被清种规则删掉）');
  if (abandonIsGrace.value && p.unsatisfied) {
    out.push(`未达标本应扣 ${p.unsatisfied}，当前处于首月豁免、不触发该罚`);
  }
  return out
});

return (_ctx, _cache) => {
  const _component_VCardTitle = _resolveComponent$C("VCardTitle");
  const _component_VIcon = _resolveComponent$C("VIcon");
  const _component_VAlert = _resolveComponent$C("VAlert");
  const _component_VCardText = _resolveComponent$C("VCardText");
  const _component_VDivider = _resolveComponent$C("VDivider");
  const _component_VSpacer = _resolveComponent$C("VSpacer");
  const _component_VBtn = _resolveComponent$C("VBtn");
  const _component_VCardActions = _resolveComponent$C("VCardActions");
  const _component_VCard = _resolveComponent$C("VCard");
  const _component_VDialog = _resolveComponent$C("VDialog");

  return (_openBlock$C(), _createBlock$z(_component_VDialog, {
    "model-value": !!conf.value,
    "max-width": "32rem",
    persistent: "",
    "onUpdate:modelValue": _cache[2] || (_cache[2] = v => { if (!v) conf.value = null; })
  }, {
    default: _withCtx$z(() => [
      _createVNode$B(_component_VCard, { class: "magicflow-dialog" }, {
        default: _withCtx$z(() => [
          _createVNode$B(_component_VCardTitle, { class: "text-subtitle-1 pt-4" }, {
            default: _withCtx$z(() => [
              _createTextVNode$B(_toDisplayString$C(isAbandon.value ? '确认放弃认领' : '确认认领'), 1)
            ]),
            _: 1
          }),
          _createVNode$B(_component_VCardText, { class: "text-body-2" }, {
            default: _withCtx$z(() => [
              (conf.value && conf.value.kind === 'batch')
                ? (_openBlock$C(), _createElementBlock$w(_Fragment$w, { key: 0 }, [
                    _createTextVNode$B(" 将对「本轮可认领」的最多 " + _toDisplayString$C(__props.cfg.batch) + " 个种子执行认领（每站每日上限 " + _toDisplayString$C(__props.cfg.daily) + "）。 ", 1)
                  ], 64))
                : (conf.value)
                  ? (_openBlock$C(), _createElementBlock$w(_Fragment$w, { key: 1 }, [
                      _cache[3] || (_cache[3] = _createTextVNode$B(" 将对 ", -1)),
                      _createElementVNode$C("strong", null, _toDisplayString$C(conf.value.row.title || conf.value.row.hash), 1),
                      _createTextVNode$B(" （" + _toDisplayString$C(conf.value.siteName || conf.value.row.site_name) + "）" + _toDisplayString$C(isAbandon.value ? '放弃认领' : '执行认领') + "。 ", 1)
                    ], 64))
                  : _createCommentVNode$x("", true),
              (isAbandon.value)
                ? (_openBlock$C(), _createElementBlock$w("div", _hoisted_1$y, [
                    _createElementVNode$C("div", _hoisted_2$w, [
                      _createVNode$B(_component_VIcon, {
                        icon: "mdi-lock-open-variant-outline",
                        size: "15"
                      }),
                      _createElementVNode$C("span", null, _toDisplayString$C(abandonIsGrace.value ? '首月豁免 · 不触发未达标罚' : '已达标 · 不触发未达标罚'), 1)
                    ]),
                    (abandonReason.value)
                      ? (_openBlock$C(), _createElementBlock$w("div", _hoisted_3$u, _toDisplayString$C(abandonReason.value), 1))
                      : _createCommentVNode$x("", true),
                    _createElementVNode$C("ul", _hoisted_4$u, [
                      (_openBlock$C(true), _createElementBlock$w(_Fragment$w, null, _renderList$u(abandonLoses.value, (t) => {
                        return (_openBlock$C(), _createElementBlock$w("li", { key: t }, _toDisplayString$C(t), 1))
                      }), 128))
                    ])
                  ]))
                : _createCommentVNode$x("", true),
              (!isAbandon.value && hasPenalty.value)
                ? (_openBlock$C(), _createElementBlock$w("div", _hoisted_5$u, [
                    _createElementVNode$C("div", _hoisted_6$s, [
                      _createVNode$B(_component_VIcon, {
                        icon: "mdi-gavel",
                        size: "15"
                      }),
                      _createElementVNode$C("span", null, _toDisplayString$C(conf.value.siteName || conf.value.row.site_name) + " 的认领代价", 1)
                    ]),
                    (_openBlock$C(true), _createElementBlock$w(_Fragment$w, null, _renderList$u(penaltyRows.value, (r) => {
                      return (_openBlock$C(), _createElementBlock$w("div", {
                        key: r.label,
                        class: "claim-confirm-penalty__row"
                      }, [
                        _createVNode$B(_component_VIcon, {
                          icon: r.icon,
                          size: "14",
                          class: _normalizeClass$j(`is-${r.tone}`)
                        }, null, 8, ["icon", "class"]),
                        _createElementVNode$C("span", _hoisted_7$q, _toDisplayString$C(r.label), 1),
                        _createElementVNode$C("b", {
                          class: _normalizeClass$j(`is-${r.tone}`)
                        }, _toDisplayString$C(r.value), 3)
                      ]))
                    }), 128)),
                    (gateText.value || multText.value)
                      ? (_openBlock$C(), _createElementBlock$w("div", _hoisted_8$o, [
                          (gateText.value)
                            ? (_openBlock$C(), _createElementBlock$w(_Fragment$w, { key: 0 }, [
                                _createTextVNode$B(_toDisplayString$C(gateText.value), 1)
                              ], 64))
                            : _createCommentVNode$x("", true),
                          (gateText.value && multText.value)
                            ? (_openBlock$C(), _createElementBlock$w(_Fragment$w, { key: 1 }, [
                                _createTextVNode$B(" · ")
                              ], 64))
                            : _createCommentVNode$x("", true),
                          (multText.value)
                            ? (_openBlock$C(), _createElementBlock$w(_Fragment$w, { key: 2 }, [
                                _createTextVNode$B(_toDisplayString$C(multText.value), 1)
                              ], 64))
                            : _createCommentVNode$x("", true)
                        ]))
                      : _createCommentVNode$x("", true),
                    (unverified.value)
                      ? (_openBlock$C(), _createElementBlock$w("div", _hoisted_9$m, " ⚠ 该站规则尚未核对，以上为同族默认值，请先在站点确认。 "))
                      : _createCommentVNode$x("", true)
                  ]))
                : _createCommentVNode$x("", true),
              (!isAbandon.value)
                ? (_openBlock$C(), _createBlock$z(_component_VAlert, {
                    key: 4,
                    type: "warning",
                    variant: "tonal",
                    density: "compact",
                    class: "mt-3"
                  }, {
                    default: _withCtx$z(() => [...(_cache[4] || (_cache[4] = [
                      _createTextVNode$B(" 认领后该种进入硬保护、永不自动删除；站点不达标可能扣魔力。 ", -1)
                    ]))]),
                    _: 1
                  }))
                : (_openBlock$C(), _createElementBlock$w("div", _hoisted_10$m, "放弃立即生效、不可撤销；站点仍开放时可重新认领。"))
            ]),
            _: 1
          }),
          _createVNode$B(_component_VDivider),
          _createVNode$B(_component_VCardActions, null, {
            default: _withCtx$z(() => [
              _createVNode$B(_component_VSpacer),
              _createVNode$B(_component_VBtn, {
                variant: "text",
                disabled: __props.acting,
                onClick: _cache[0] || (_cache[0] = $event => (conf.value = null))
              }, {
                default: _withCtx$z(() => [...(_cache[5] || (_cache[5] = [
                  _createTextVNode$B("取消", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$B(_component_VBtn, {
                color: isAbandon.value ? 'error' : 'primary',
                variant: "flat",
                loading: __props.acting,
                onClick: _cache[1] || (_cache[1] = $event => (emit('run')))
              }, {
                default: _withCtx$z(() => [...(_cache[6] || (_cache[6] = [
                  _createTextVNode$B("确认", -1)
                ]))]),
                _: 1
              }, 8, ["color", "loading"])
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["model-value"]))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const ClaimConfirm = Object.assign(_sfc_main$C, { __scopeId: 'data-v-31c56e5d' })

export default ClaimConfirm
