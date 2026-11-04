// PushAuditDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './PushAuditDialog.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$p,
  createBlock: _createBlock$q,
  createCommentVNode: _createCommentVNode$q,
  createElementBlock: _createElementBlock$p,
  createElementVNode: _createElementVNode$t,
  createTextVNode: _createTextVNode$s,
  createVNode: _createVNode$s,
  normalizeClass: _normalizeClass$g,
  openBlock: _openBlock$t,
  renderList: _renderList$n,
  resolveComponent: _resolveComponent$t,
  toDisplayString: _toDisplayString$t,
  unref: _unref$d,
  withCtx: _withCtx$q,
} = __vue

import { formatBytes, formatDateTime } from '../../../../utils.js'

const _hoisted_1$r = { class: "magicflow-push-dialog__stats" };
const _hoisted_2$p = { class: "magicflow-push-dialog__stat" };
const _hoisted_3$o = { class: "magicflow-push-dialog__num" };
const _hoisted_4$o = { class: "magicflow-push-dialog__num" };
const _hoisted_5$o = { class: "magicflow-push-dialog__stat" };
const _hoisted_6$n = { class: "magicflow-push-dialog__num" };
const _hoisted_7$m = {
  key: 2,
  class: "magicflow-push-dialog__empty"
};
const _hoisted_8$k = {
  key: 3,
  class: "magicflow-push-dialog__list"
};
const _hoisted_9$i = { class: "magicflow-push-dialog__time" };
const _hoisted_10$i = { class: "magicflow-push-dialog__site" };
const _hoisted_11$h = ["title"];
const _hoisted_12$h = { class: "magicflow-push-dialog__meta" };
const _hoisted_13$f = {
  key: 0,
  class: "magicflow-push-dialog__err"
};

const {computed: computed$C} = __vue;


const _sfc_main$t = {
  __name: 'PushAuditDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  items: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
  filter: { type: String, default: '' }, // '' 全部 / 'false' 仅失败 / 'true' 仅成功
  taskName: { type: String, default: '' }, // 非空 = 当前按任务过滤
  loading: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
},
  emits: ['update:modelValue', 'refresh', 'update:filter', 'clear-task'],
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 推送记录弹窗（★ 19.11.22，⑤ 推送审计的「看」那一半）
// 数据向下（props）/ 事件向上（emit）；本组件不直接调 api。
// 只读定位：每次「加种」一条（成功也记、失败更记），用途是**排障**，不是决策依据。
const props = __props;
const emit = __emit;

const open = computed$C({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
});

const FILTERS = [
  { value: '', title: '全部' },
  { value: 'false', title: '仅失败' },
  { value: 'true', title: '仅成功' },
];

const CONTENT = { torrent: '种子文件', magnet: '磁力', url: '链接' };

const hookReady = computed$C(() => props.summary?.hook_ready !== false);
const failed = computed$C(() => Number(props.summary?.failed_count || 0));
const okCount = computed$C(() => Number(props.summary?.ok_count || 0));
const kept = computed$C(() => Number(props.summary?.kept || 0));
const keepLimit = computed$C(() => Number(props.summary?.keep_limit || 0));

function contentText(kind) {
  return CONTENT[String(kind || '')] || (kind ? String(kind) : '—')
}
function shortHash(row) {
  const h = String(row?.hash || '');
  return h ? h.slice(0, 12) : '—'
}
function sizeText(row) {
  const n = Number(row?.bytes || 0);
  return n > 0 ? formatBytes(n) : '—'
}
function taskText(row) {
  return row?.task_name || row?.task_id || row?.tag || '—'
}

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$t("VIcon");
  const _component_VChip = _resolveComponent$t("VChip");
  const _component_VSpacer = _resolveComponent$t("VSpacer");
  const _component_VBtn = _resolveComponent$t("VBtn");
  const _component_VCardTitle = _resolveComponent$t("VCardTitle");
  const _component_VDivider = _resolveComponent$t("VDivider");
  const _component_VAlert = _resolveComponent$t("VAlert");
  const _component_VBtnToggle = _resolveComponent$t("VBtnToggle");
  const _component_VCardText = _resolveComponent$t("VCardText");
  const _component_VCardActions = _resolveComponent$t("VCardActions");
  const _component_VCard = _resolveComponent$t("VCard");
  const _component_VDialog = _resolveComponent$t("VDialog");

  return (_openBlock$t(), _createBlock$q(_component_VDialog, {
    modelValue: open.value,
    "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((open).value = $event)),
    "max-width": "52rem",
    scrollable: "",
    fullscreen: __props.narrow
  }, {
    default: _withCtx$q(() => [
      _createVNode$s(_component_VCard, { class: "magicflow-dialog magicflow-push-dialog" }, {
        default: _withCtx$q(() => [
          _createVNode$s(_component_VCardTitle, { class: "d-flex align-center flex-wrap" }, {
            default: _withCtx$q(() => [
              _createVNode$s(_component_VIcon, {
                icon: "mdi-send-check-outline",
                class: "me-2"
              }),
              _cache[6] || (_cache[6] = _createTextVNode$s(" 推送记录 ", -1)),
              (failed.value)
                ? (_openBlock$t(), _createBlock$q(_component_VChip, {
                    key: 0,
                    size: "x-small",
                    color: "error",
                    variant: "tonal",
                    class: "ms-2"
                  }, {
                    default: _withCtx$q(() => [
                      _createTextVNode$s("失败 " + _toDisplayString$t(failed.value), 1)
                    ]),
                    _: 1
                  }))
                : _createCommentVNode$q("", true),
              _createVNode$s(_component_VSpacer),
              _createVNode$s(_component_VBtn, {
                icon: "mdi-refresh",
                variant: "text",
                size: "small",
                "aria-label": "刷新",
                loading: __props.loading,
                onClick: _cache[0] || (_cache[0] = $event => (emit('refresh')))
              }, null, 8, ["loading"]),
              _createVNode$s(_component_VBtn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                "aria-label": "关闭",
                onClick: _cache[1] || (_cache[1] = $event => (open.value = false))
              })
            ]),
            _: 1
          }),
          _createVNode$s(_component_VDivider),
          _createVNode$s(_component_VCardText, null, {
            default: _withCtx$q(() => [
              _cache[11] || (_cache[11] = _createElementVNode$t("div", { class: "text-body-2 text-medium-emphasis mb-2" }, " 每次「加种」一条，含站端 / 下载器原始报错。只读审计 —— 不参与任何判定。 ", -1)),
              (!hookReady.value)
                ? (_openBlock$t(), _createBlock$q(_component_VAlert, {
                    key: 0,
                    type: "warning",
                    variant: "tonal",
                    density: "compact",
                    class: "mb-3"
                  }, {
                    default: _withCtx$q(() => [...(_cache[7] || (_cache[7] = [
                      _createTextVNode$s(" 审计钩子当前", -1),
                      _createElementVNode$t("strong", null, "未绑定", -1),
                      _createTextVNode$s("，这段时间的加种", -1),
                      _createElementVNode$t("strong", null, "没有被记录", -1),
                      _createTextVNode$s("。 点右上刷新会重新绑定（幂等），之后的新加种才会进来。 ", -1)
                    ]))]),
                    _: 1
                  }))
                : _createCommentVNode$q("", true),
              _createElementVNode$t("div", _hoisted_1$r, [
                _createElementVNode$t("span", _hoisted_2$p, [
                  _createElementVNode$t("span", _hoisted_3$o, _toDisplayString$t(okCount.value), 1),
                  _cache[8] || (_cache[8] = _createTextVNode$s("成功 ", -1))
                ]),
                _createElementVNode$t("span", {
                  class: _normalizeClass$g(["magicflow-push-dialog__stat", { 'is-bad': failed.value > 0 }])
                }, [
                  _createElementVNode$t("span", _hoisted_4$o, _toDisplayString$t(failed.value), 1),
                  _cache[9] || (_cache[9] = _createTextVNode$s("失败 ", -1))
                ], 2),
                _createElementVNode$t("span", _hoisted_5$o, [
                  _createElementVNode$t("span", _hoisted_6$n, _toDisplayString$t(kept.value), 1),
                  _cache[10] || (_cache[10] = _createTextVNode$s("条已存", -1)),
                  (keepLimit.value)
                    ? (_openBlock$t(), _createElementBlock$p(_Fragment$p, { key: 0 }, [
                        _createTextVNode$s(" / 上限 " + _toDisplayString$t(keepLimit.value), 1)
                      ], 64))
                    : _createCommentVNode$q("", true)
                ]),
                _createVNode$s(_component_VSpacer),
                _createVNode$s(_component_VBtnToggle, {
                  "model-value": __props.filter,
                  density: "compact",
                  variant: "outlined",
                  divided: "",
                  mandatory: "",
                  "onUpdate:modelValue": _cache[2] || (_cache[2] = v => emit('update:filter', String(v ?? '')))
                }, {
                  default: _withCtx$q(() => [
                    (_openBlock$t(), _createElementBlock$p(_Fragment$p, null, _renderList$n(FILTERS, (f) => {
                      return _createVNode$s(_component_VBtn, {
                        key: f.value,
                        value: f.value,
                        size: "small"
                      }, {
                        default: _withCtx$q(() => [
                          _createTextVNode$s(_toDisplayString$t(f.title), 1)
                        ]),
                        _: 2
                      }, 1032, ["value"])
                    }), 64))
                  ]),
                  _: 1
                }, 8, ["model-value"])
              ]),
              (__props.taskName)
                ? (_openBlock$t(), _createBlock$q(_component_VChip, {
                    key: 1,
                    size: "small",
                    closable: "",
                    variant: "tonal",
                    color: "primary",
                    class: "mt-2",
                    "onClick:close": _cache[3] || (_cache[3] = $event => (emit('clear-task')))
                  }, {
                    default: _withCtx$q(() => [
                      _createTextVNode$s(" 只看任务：" + _toDisplayString$t(__props.taskName), 1)
                    ]),
                    _: 1
                  }))
                : _createCommentVNode$q("", true),
              (!__props.items.length)
                ? (_openBlock$t(), _createElementBlock$p("div", _hoisted_7$m, [
                    (!hookReady.value)
                      ? (_openBlock$t(), _createElementBlock$p(_Fragment$p, { key: 0 }, [
                          _createTextVNode$s("钩子未绑定，所以读不到记录 —— 先点刷新把钩子绑回来。")
                        ], 64))
                      : (__props.filter)
                        ? (_openBlock$t(), _createElementBlock$p(_Fragment$p, { key: 1 }, [
                            _createTextVNode$s("该筛选下没有记录。")
                          ], 64))
                        : (kept.value)
                          ? (_openBlock$t(), _createElementBlock$p(_Fragment$p, { key: 2 }, [
                              _createTextVNode$s(" 这个任务还没有加种记录。 ")
                            ], 64))
                          : (_openBlock$t(), _createElementBlock$p(_Fragment$p, { key: 3 }, [
                              _createTextVNode$s(" 还没有加种记录。只有真正「加种」时才写一条 —— 任务全在 seeding / stopped、 没有刷流或点播在下种时，这里就是空的。 ")
                            ], 64))
                  ]))
                : (_openBlock$t(), _createElementBlock$p("ul", _hoisted_8$k, [
                    (_openBlock$t(true), _createElementBlock$p(_Fragment$p, null, _renderList$n(__props.items, (row, i) => {
                      return (_openBlock$t(), _createElementBlock$p("li", {
                        key: `${row.ts}-${row.hash}-${i}`,
                        class: _normalizeClass$g({ 'is-bad': !row.ok })
                      }, [
                        _createVNode$s(_component_VChip, {
                          size: "x-small",
                          variant: "tonal",
                          color: row.ok ? 'success' : 'error'
                        }, {
                          default: _withCtx$q(() => [
                            _createTextVNode$s(_toDisplayString$t(row.ok ? '成功' : '失败'), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"]),
                        _createElementVNode$t("span", _hoisted_9$i, _toDisplayString$t(_unref$d(formatDateTime)(row.ts)), 1),
                        _createElementVNode$t("span", _hoisted_10$i, _toDisplayString$t(row.site || '—'), 1),
                        _createElementVNode$t("span", {
                          class: "magicflow-push-dialog__task",
                          title: taskText(row)
                        }, _toDisplayString$t(taskText(row)), 9, _hoisted_11$h),
                        _createElementVNode$t("span", _hoisted_12$h, [
                          _createElementVNode$t("code", null, _toDisplayString$t(shortHash(row)), 1),
                          (row.hit_and_run)
                            ? (_openBlock$t(), _createElementBlock$p(_Fragment$p, { key: 0 }, [
                                _createTextVNode$s(" · H&R")
                              ], 64))
                            : _createCommentVNode$q("", true),
                          _createTextVNode$s(" · " + _toDisplayString$t(contentText(row.content)) + " · " + _toDisplayString$t(sizeText(row)), 1)
                        ]),
                        (!row.ok && row.error)
                          ? (_openBlock$t(), _createElementBlock$p("span", _hoisted_13$f, _toDisplayString$t(row.error), 1))
                          : _createCommentVNode$q("", true)
                      ], 2))
                    }), 128))
                  ]))
            ]),
            _: 1
          }),
          _createVNode$s(_component_VDivider),
          _createVNode$s(_component_VCardActions, null, {
            default: _withCtx$q(() => [
              _cache[13] || (_cache[13] = _createElementVNode$t("span", { class: "text-caption text-medium-emphasis" }, "审计表是环形表，超出上限后最旧的自动丢弃。", -1)),
              _createVNode$s(_component_VSpacer),
              _createVNode$s(_component_VBtn, {
                size: "small",
                variant: "tonal",
                "prepend-icon": "mdi-refresh",
                onClick: _cache[4] || (_cache[4] = $event => (emit('refresh')))
              }, {
                default: _withCtx$q(() => [...(_cache[12] || (_cache[12] = [
                  _createTextVNode$s("刷新", -1)
                ]))]),
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
const PushAuditDialog = Object.assign(_sfc_main$t, { __scopeId: 'data-v-f88aa3ff' })

export default PushAuditDialog
