// SeedingTab —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板）。
//
// ★ 19.12.16 按设计稿「种子池」(2:1534 / 2:1590) 重排：
//   统计行 4 卡 + 七列自绘列表 + 自建分页。原 VDataTable 换成手写表格，原因：
//   稿的行是 **33px 高 / 7px 状态点 / r10 圆角 / 每列定宽**，Vuetify 的
//   `.v-data-table__td` 有 padding + border 组合，压不到这个密度还不串行。
//   VDataTable 唯一不可替代的能力是分页，这里用 slice 补齐（PAGE_SIZE 行/页）。
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
  computed: _computed$5,
  mergeModels: _mergeModels$2,
  mergeProps: _mergeProps$1,
  openBlock: _openBlock$6,
  ref: _ref$5,
  renderList: _renderList$5,
  resolveComponent: _resolveComponent$6,
  toDisplayString: _toDisplayString$6,
  unref: _unref$2,
  useModel: _useModel$2,
  watch: _watch$5,
  withCtx: _withCtx$4,
  withModifiers: _withModifiers$1,
} = __vue

import { TORRENT_PAUSED_STATES, TORRENT_STATE_TEXT, TORRENT_TRANSIENT_STATES } from '../../constants.js'
import { formatBytes } from '../../../../utils.js'
// ★ 任务 98：人工结清的「可操作条件」与 H&R 账单弹窗同源（单一真值源）。
//   入口归位到魔流插件**任务详情 → 种子明细 → 每颗种子的操作区**，
//   按当前种子 hash 精确关联账单；H&R 账单弹窗只负责查看与审计。
import { canManualSettle } from '../../composables/useHrBills.js'

const _hoisted_1$5 = { class: "mf-pool" };
const _hoisted_2$5 = { class: "mf-pool__stats" };
const _hoisted_3$4 = { class: "magicflow-panel mf-pool__card app-surface-static" };
const _hoisted_4$4 = { class: "mf-pool__head" };
const _hoisted_5$4 = { class: "mf-pool__titles" };
const _hoisted_6$4 = { class: "mf-pool__title" };
const _hoisted_7$4 = { class: "mf-pool__hint" };
const _hoisted_8$4 = { class: "mf-pool__tools" };
const _hoisted_9$4 = { class: "mf-pool__bulk" };
const _hoisted_10$4 = { class: "mf-pool__count" };
const _hoisted_11$4 = { class: "mf-pool__thead" };
const _hoisted_12$4 = { class: "mf-pool__rows" };
const _hoisted_13$4 = { class: "mf-pool__pager" };
const _hoisted_14$4 = { class: "mf-pool__empty" };
const _hoisted_15$4 = { class: "magicflow-mobile-torrents" };
// ★ 行/卡片的 class 是动态的（H&R 高亮），必须同时进 dynamicProps，
//   否则 patchFlag 只标 onClick 时 class 不参与 diff，切筛选后高亮会留在原地。
const _hoisted_16$4 = ["class", "onClick"];
const _hoisted_17$4 = { class: "magicflow-mobile-torrent__head" };
const _hoisted_18$4 = { class: "magicflow-mobile-torrent__title" };
const _hoisted_19$4 = { class: "magicflow-mobile-torrent__grid" };
const _hoisted_20$4 = { class: "magicflow-mobile-torrent__actions" };

// 每页行数。线上单任务最多 226 颗（馒头·魔力），1380 是全部任务合计；
// 20 行/页既能一屏看完又不会让 qB 快照的 226 条挤成长卷。
const PAGE_SIZE = 20

// 「活跃做种」状态集 —— 与 brush.py 的 _SEED 同口径（含校验中/分配中）。
const _SEED_STATES = ['uploading', 'stalledup', 'forcedup', 'queuedup', 'checkingup', 'allocating']

// 真值源仍在 useSeeding（rows 已按筛选/状态过滤+排序）；本组件只吃 props。

const _sfc_main$6 = {
  __name: 'SeedingTab',
  props: /*@__PURE__*/_mergeModels$2({
  rows: { type: Array, default: () => [] },
  headers: { type: Array, default: () => [] },          // 19.12.16 起列表自绘，不再消费；
                                                        // 仍声明是为了让父组件的 :headers 不落到根 DOM 上
  statusOptions: { type: Array, default: () => [] },
  selectedHashes: { type: Array, default: () => [] },
  allSelected: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
  // hash(小写) -> H&R 账单条目 {state, hours_left, due_h, need_h, seeded_h, at_risk, site, site_name}
  // 空对象 = 账单没取到（不是「没有欠账」）—— 统计卡据此显示「—」而不是 0。
  hrMap: { type: Object, default: () => ({}) },
  // ★ 任务 98：父级按「当前登录身份是否有效」决定是否开放人工结清入口；
  //   busy 用于提交期间禁用按钮，防重复点击。两者都只是 UI 开关，
  //   **账单能不能结清仍以后端 hrbills_settle_manual 的校验/CAS 为准**。
  hrSettleEnabled: { type: Boolean, default: false },
  hrSettleBusy: { type: Boolean, default: false },
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
  'hr-settle',
], ["update:filter", "update:statusFilter"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 托管做种明细（种子池 · poolView === 'torrents'）
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。

const filter = _useModel$2(__props, 'filter');
const statusFilter = _useModel$2(__props, 'statusFilter');

const emit = __emit;

// ── 分页 ────────────────────────────────────────────────────────────────
const page = _ref$5(1);
const pageCount = _computed$5(() => {
  const n = (__props.rows || []).length;
  return Math.max(1, Math.ceil(n / PAGE_SIZE))
});
const pagedRows = _computed$5(() => {
  const rows = __props.rows || [];
  const p = Math.min(Math.max(1, page.value), pageCount.value);
  const start = (p - 1) * PAGE_SIZE;
  return rows.slice(start, start + PAGE_SIZE)
});
// 筛选条件一变，页码必须回第一页 —— 否则「做种中 226 条 → 已保护 3 条」时
// 停在 p7 会显示一张空表，看上去像筛选坏了。
_watch$5([filter, statusFilter], () => { page.value = 1 });
function goto(delta) {
  page.value = Math.min(Math.max(1, page.value + delta), pageCount.value)
}

// ── H&R 账单（按 hash 索引）──────────────────────────────────────────────
function hrOf(item) {
  const h = String(item?.hash || '').toLowerCase();
  if (!h) return null;
  return (__props.hrMap || {})[h] || null
}
// ★ 任务 98：按**当前种子 hash 精确关联** H&R 账单，只有后端允许的账单才显示入口。
//   `canManualSettle` 与账单弹窗共用一份判据（active/breached/pending 且非 manual）；
//   settled / void / 无账单 / 登录身份无效 → 不渲染按钮。
function hrCanSettle(item) {
  if (!__props.hrSettleEnabled) return false;
  const b = hrOf(item);
  return !!b && canManualSettle(b)
}
// 「未结清」= active / pending / breached；已 settled / void 的种不再算欠账
// （口径同 useHrBills.hrBillStateColor，别在这里另立一套）。
function hrOpen(item) {
  const b = hrOf(item);
  if (!b) return null;
  const st = String(b.state || '');
  if (st === 'settled' || st === 'void') return null;
  return b
}
// 窗口倒计时（hours_left）与还需工时（need_h − seeded_h）是两个概念，
// 措辞必须分开 —— 见 useHrBills.hrBillLeftH 上方注释。
function hrText(b) {
  const st = String((b && b.state) || '');
  // ★ 19.12.32：站点**没有 H&R 规则**的条目，账单 `rule` 是 ``unknown``、
  //   ``class`` 是「未定性」。这种条目此前一律落到「H&R 待结清」，
  //   读起来像「站点说了要罚、你还没还」，其实站点压根没给规则
  //   （2026-11-05 线上 YemaPT 22 条全是这一类）。文案不能替站点下结论。
  if (String((b && b.rule) || '') === 'unknown') return 'H&R 未定性（站点无规则）'
  if (st === 'breached') return 'H&R 已违约'
  const left = Number(b && b.hours_left);
  if (Number.isFinite(left) && left > 0) {
    return left < 48 ? `H&R 剩 ${Math.round(left)} 小时` : `H&R 剩 ${(left / 24).toFixed(1)} 天`
  }
  const due = Math.max(0, (Number(b && b.need_h) || 0) - (Number(b && b.seeded_h) || 0));
  if (due > 0.05) return `H&R 还需 ${due.toFixed(1)}h`
  return 'H&R 待结清'
}
function hrTone(b) {
  const st = String((b && b.state) || '');
  if (st === 'breached') return 'error'
  return (b && b.at_risk) ? 'warn' : 'info'
}

// ── 统计行（4 格）────────────────────────────────────────────────────────
// 稿的 4 格是「做种中·免费流量 / H&R 进行中·最紧 / 静默托管 / 欠 H&R」。
// 「免费流量」不做：qB 没有站点促销概念，线上能拿到的 is_free 是**加种时打的标签**，
// 不等于「此刻免费」，摆上去就是假的（铁律 6）。换成「受保护」这个可验证的口径。
const stats = _computed$5(() => {
  const rows = __props.rows || [];
  let seeding = 0, silent = 0, prot = 0, hrOwed = 0;
  let hrMin = null, hrKnown = 0;
  const hrMapObj = __props.hrMap || {};
  const hrKnownAny = Object.keys(hrMapObj).length > 0;
  for (const it of rows) {
    const st = String(it?.state || '').toLowerCase();
    if (_SEED_STATES.includes(st)) seeding++;
    else if (TORRENT_PAUSED_STATES.includes(st)) silent++;
    if (it?.is_protected) prot++;
    const b = hrOpen(it);
    if (b) {
      hrOwed++;
      const left = Number(b.hours_left);
      if (Number.isFinite(left) && left > 0 && (hrMin === null || left < hrMin)) hrMin = left;
    }
  }
  for (const h of Object.keys(hrMapObj)) { if (h) hrKnown++; }
  return {
    seeding,
    silent,
    prot,
    hrOwed,
    // 账单没取到 或 本任务没有一颗种在账单里 → 这两个数不可信，交给渲染层显示「—」
    hrOwedKnown: hrKnownAny && (hrOwed > 0 || hrKnown > 0),
    hrMin,
  }
});
const hrSeenText = _computed$5(() => {
  const s = stats.value;
  if (!s.hrOwedKnown) return '账单未取到'
  if (!s.hrOwed) return '无未结清'
  const m = s.hrMin;
  return (m === null) ? '窗口未知' : (m < 48 ? `最紧 ${Math.round(m)} 小时` : `最紧 ${(m / 24).toFixed(1)} 天`)
});

// ── 展示态纯函数（真值源仍在 useSeeding；此处为 P4 拆分随模板搬入的同口径实现）──
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
// 7px 状态点（稿的行首元素）用 CSS 变量色，不用 VChip 的 tonal。
function dotTone(item) {
  const b = hrOpen(item);
  if (b) return hrTone(b)
  const key = String(item?.state || '').toLowerCase();
  if (TORRENT_PAUSED_STATES.includes(key)) return 'silent'
  return stateColor(item?.state)
}
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100;
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}
function torrentStateText(item) {
  const key = String(item?.state || '').toLowerCase();
  if (TORRENT_TRANSIENT_STATES[key]) return TORRENT_TRANSIENT_STATES[key]
  if (TORRENT_PAUSED_STATES.includes(key)) {
    // 「静默托管」是本插件对该状态的产品叫法（交给静默池接管），比裸「已暂停」有信息量
    return torrentProgressPct(item) >= 100 ? '静默托管' : (stateLabel(item?.state) || '已暂停')
  }
  const pct = torrentProgressPct(item);
  if (pct >= 100) return '做种中'
  if (pct <= 0) return stateLabel(item?.state) || '等待中'
  return `下载 ${pct}%`
}
// 状态列：H&R 优先（它是义务，比瞬时做种状态更该被看见）
function rowStatusText(item) {
  const b = hrOpen(item);
  return b ? hrText(b) : torrentStateText(item)
}
function rowStatusTone(item) {
  const b = hrOpen(item);
  if (b) return 'hr-' + hrTone(b)
  return 'st-' + stateColor(item?.state)
}
// 做种时长（秒 → 人话）。qB seeding_time 只在**活跃做种**时累积，
// 所以这是「真挂机时长」，与 H&R 判据同源；拿不到就摆「—」不猜。
function seedDuration(sec) {
  const v = Number(sec || 0);
  if (!Number.isFinite(v) || v <= 0) return '—'
  const d = v / 86400;
  if (d >= 1) return `${d >= 10 ? Math.round(d) : d.toFixed(1)} 天`
  const h = v / 3600;
  if (h >= 1) return `${Math.round(h)} 小时`
  return `${Math.max(1, Math.round(v / 60))} 分钟`
}
function uploadedText(item) {
  const n = Number(item?.uploaded || 0);
  if (!Number.isFinite(n) || n <= 0) return '—'
  return formatBytes(n)
}
function ratioText(item) {
  const n = Number(item?.ratio || 0);
  return Number.isFinite(n) ? n.toFixed(2) : '0.00'
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
function rowClass(item) {
  const b = hrOpen(item);
  if (!b) return null
  if (String(b.state || '') === 'breached') return 'mf-pool__row is-hr is-hr-error'
  return (b.at_risk ? 'mf-pool__row is-hr' : 'mf-pool__row is-hr-soft')
}
function isSelected(item) {
  return (__props.selectedHashes || []).includes(item.hash)
}

return (_ctx, _cache) => {
  const _component_VBtn = _resolveComponent$6("VBtn");
  const _component_VBtnToggle = _resolveComponent$6("VBtnToggle");
  const _component_VSpacer = _resolveComponent$6("VSpacer");
  const _component_VCheckbox = _resolveComponent$6("VCheckbox");
  const _component_VSelect = _resolveComponent$6("VSelect");
  const _component_VIcon = _resolveComponent$6("VIcon");
  const _component_VListItem = _resolveComponent$6("VListItem");
  const _component_VDivider = _resolveComponent$6("VDivider");
  const _component_VList = _resolveComponent$6("VList");
  const _component_VMenu = _resolveComponent$6("VMenu");
  const _component_VProgressLinear = _resolveComponent$6("VProgressLinear");

  return (_openBlock$6(), _createElementBlock$5("div", _hoisted_1$5, [
    // ── 统计行：4 格，稿 pad 9/14 r10 ───────────────────────────────────
    _createElementVNode$6("div", _hoisted_2$5, [
      _createElementVNode$6("div", { class: "mf-pool__stat" }, [
        _createElementVNode$6("i", { class: "mf-pool__stat-dot is-ok", "aria-hidden": "true" }),
        _createElementVNode$6("span", { class: "mf-pool__stat-label" }, [
          _createTextVNode$6("做种中", -1),
          _createElementVNode$6("em", null, "活跃做种"),
        ]),
        _createElementVNode$6("b", { class: "mf-pool__stat-val" }, _toDisplayString$6(stats.value.seeding) + " 个", 1),
      ]),
      _createElementVNode$6("div", { class: "mf-pool__stat" }, [
        _createElementVNode$6("i", { class: "mf-pool__stat-dot is-silent", "aria-hidden": "true" }),
        _createElementVNode$6("span", { class: "mf-pool__stat-label" }, [
          _createTextVNode$6("静默托管", -1),
          _createElementVNode$6("em", null, "本任务管辖"),
        ]),
        _createElementVNode$6("b", { class: "mf-pool__stat-val" }, _toDisplayString$6(stats.value.silent) + " 个", 1),
      ]),
      _createElementVNode$6("div", { class: "mf-pool__stat" }, [
        _createElementVNode$6("i", { class: "mf-pool__stat-dot is-prot", "aria-hidden": "true" }),
        _createElementVNode$6("span", { class: "mf-pool__stat-label" }, [
          _createTextVNode$6("受保护", -1),
          _createElementVNode$6("em", null, "手动保种"),
        ]),
        _createElementVNode$6("b", { class: "mf-pool__stat-val" }, _toDisplayString$6(stats.value.prot) + " 个", 1),
      ]),
      _createElementVNode$6("div", { class: "mf-pool__stat" }, [
        _createElementVNode$6("i", {
          class: ["mf-pool__stat-dot", stats.value.hrOwed > 0 ? "is-hr" : "is-ok"],
          "aria-hidden": "true",
        }),
        _createElementVNode$6("span", { class: "mf-pool__stat-label" }, [
          _createTextVNode$6("欠 H&R", -1),
          _createElementVNode$6("em", null, _toDisplayString$6(hrSeenText.value), 1),
        ]),
        _createElementVNode$6("b", {
          class: ["mf-pool__stat-val", stats.value.hrOwed > 0 ? "is-warn" : ""],
        }, _toDisplayString$6(stats.value.hrOwedKnown ? stats.value.hrOwed + ' 个' : '—'), 1),
      ]),
    ]),

    // ── 列表卡（稿 pad 16/20 r14）──────────────────────────────────────
    _createElementVNode$6("section", _hoisted_3$4, [
      _createElementVNode$6("header", _hoisted_4$4, [
        _createElementVNode$6("div", _hoisted_5$4, [
          _createElementVNode$6("span", _hoisted_6$4, "种子列表"),
          _createElementVNode$6("span", _hoisted_7$4, "点任意种子看详情 · H&R 临期排前"),
        ]),
        _createElementVNode$6("div", _hoisted_8$4, [
          _createVNode$6(_component_VSelect, {
            modelValue: statusFilter.value,
            "onUpdate:modelValue": $event => ((statusFilter).value = $event),
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
            "onUpdate:modelValue": $event => ((filter).value = $event),
            mandatory: "",
            color: "primary",
            density: "compact"
          }, {
            default: _withCtx$4(() => [
              _createVNode$6(_component_VBtn, { value: "all", size: "small" }, {
                default: _withCtx$4(() => [...[
                  _createTextVNode$6("全部", -1)
                ]]),
                _: 1
              }),
              _createVNode$6(_component_VBtn, { value: "protected", size: "small" }, {
                default: _withCtx$4(() => [...[
                  _createTextVNode$6("已保护", -1)
                ]]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["modelValue"])
        ]),
      ]),

      // 批量操作条：选中才出现（功能入口一个不删，只是不常驻占位）
      (__props.selectedHashes.length)
        ? (_openBlock$6(), _createElementBlock$5("div", _hoisted_9$4, [
            _createElementVNode$6("span", _hoisted_10$4, "已选 " + _toDisplayString$6(__props.selectedHashes.length) + " 个", 1),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", disabled: __props.busy,
              onClick: $event => (emit('batch', 'protect'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("保留", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", disabled: __props.busy,
              onClick: $event => (emit('batch', 'unprotect'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("取消保留", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", disabled: __props.busy,
              onClick: $event => (emit('batch', 'pause'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("暂停", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", disabled: __props.busy,
              onClick: $event => (emit('batch', 'resume'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("恢复", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", disabled: __props.busy,
              onClick: $event => (emit('batch', 'recheck'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("校验", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", color: "primary", disabled: __props.busy,
              onClick: $event => (emit('transfer'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("批量转移", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", color: "info", "prepend-icon": "mdi-pin",
              disabled: __props.busy, onClick: $event => (emit('batch', 'hold'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("手动保种", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", "prepend-icon": "mdi-pin-off",
              disabled: __props.busy, onClick: $event => (emit('batch', 'unhold'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("解除保种", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", color: "error", disabled: __props.busy,
              onClick: $event => (emit('batch-delete'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("删除", -1)]]), _: 1 }, 8, ["disabled"]),
            _createVNode$6(_component_VSpacer),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "text", disabled: __props.busy,
              onClick: $event => (emit('select-all'))
            }, {
              default: _withCtx$4(() => [
                _createTextVNode$6("全选筛选（" + _toDisplayString$6(__props.rows.length) + "）", 1)
              ]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "text", disabled: __props.busy,
              onClick: $event => (emit('clear-selection'))
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("取消选择", -1)]]), _: 1 }, 8, ["disabled"]),
          ]))
        : _createCommentVNode$5("", true),

      // 列头（稿 h16 · 10.5px · 与行共用同一套栅格）
      _createElementVNode$6("div", _hoisted_11$4, [
        _createVNode$6(_component_VCheckbox, {
          "model-value": __props.allSelected,
          indeterminate: __props.selectedHashes.length > 0 && !__props.allSelected,
          density: "compact",
          "hide-details": "",
          "aria-label": "全选",
          class: "mf-pool__check",
          "onUpdate:modelValue": value => (value ? emit('select-all') : emit('clear-selection'))
        }, null, 8, ["model-value", "indeterminate"]),
        _createElementVNode$6("i", { class: "mf-pool__th-dot", "aria-hidden": "true" }),
        _createElementVNode$6("span", { class: "mf-pool__th" }, "种子"),
        _createElementVNode$6("span", { class: "mf-pool__th is-num" }, "大小"),
        _createElementVNode$6("span", { class: "mf-pool__th is-num" }, "分享率"),
        _createElementVNode$6("span", { class: "mf-pool__th is-num" }, "做种时长"),
        _createElementVNode$6("span", { class: "mf-pool__th is-num" }, "上传量"),
        _createElementVNode$6("span", { class: "mf-pool__th" }, "状态"),
        // 第 9 列（24px）是行内「更多操作」的位置，列头留空 —— 栅格必须与行一致
        _createElementVNode$6("span", { class: "mf-pool__th-spacer", "aria-hidden": "true" }),
      ]),

      // 行
      (_openBlock$6(true), _createElementBlock$5(_Fragment$5, null, _renderList$5(pagedRows.value, (item) => {
        return (_openBlock$6(), _createElementBlock$5("div", {
          key: item.hash || item.title,
          class: rowClass(item) || "mf-pool__row",
          onClick: $event => (emit('row-click', $event, { item })),
        }, [
          _createVNode$6(_component_VCheckbox, {
            "model-value": isSelected(item),
            density: "compact",
            "hide-details": "",
            class: "mf-pool__check",
            "aria-label": `选择 ${item.title || ''}`,
            onClick: _withModifiers$1(() => {}, ["stop"]),
            "onUpdate:modelValue": $event => (emit('toggle-row', item))
          }, null, 8, ["model-value", "aria-label"]),
          _createElementVNode$6("i", {
            class: ["mf-pool__dot", "is-" + dotTone(item)],
            "aria-hidden": "true",
          }),
          _createElementVNode$6("span", {
            class: ["mf-pool__name", item.is_protected ? "is-prot" : ""],
            title: item.title || '未知种子',
          }, [
            _createElementVNode$6("strong", null, _toDisplayString$6(item.title || '未知种子'), 1),
            (item.is_protected)
              ? _createVNode$6(_component_VIcon, { size: "12", icon: "mdi-shield-check-outline", class: "mf-pool__prot" }, null, 8, ["icon"])
              : _createCommentVNode$5("", true),
          ]),
          _createElementVNode$6("span", { class: "mf-pool__num" }, _toDisplayString$6(Number(item.size_gb || 0).toFixed(2)) + " GB", 1),
          _createElementVNode$6("span", { class: "mf-pool__num" }, _toDisplayString$6(ratioText(item)), 1),
          _createElementVNode$6("span", { class: "mf-pool__num" }, _toDisplayString$6(seedDuration(item.seed_time)), 1),
          _createElementVNode$6("span", { class: "mf-pool__num" }, _toDisplayString$6(uploadedText(item)), 1),
          _createElementVNode$6("span", { class: ["mf-pool__state", rowStatusTone(item)] }, _toDisplayString$6(rowStatusText(item)), 1),
          // 行内操作：hover 显示（稿没画，但「保留/删除/更多」是真实功能，不能只靠详情弹窗）
          _createElementVNode$6("span", { class: "mf-pool__acts" }, [
            _createVNode$6(_component_VMenu, { location: "bottom end" }, {
              activator: _withCtx$4(({ props: menuProps }) => [
                _createVNode$6(_component_VBtn, _mergeProps$1(menuProps, {
                  size: "x-small", variant: "text", density: "comfortable",
                  icon: "mdi-dots-vertical", "aria-label": "更多操作",
                  onClick: _withModifiers$1(() => {}, ["stop"])
                }), null, 16)
              ]),
              default: _withCtx$4(() => [
                _createVNode$6(_component_VList, { density: "compact", "min-width": "176" }, {
                  default: _withCtx$4(() => [
                    (torrentIsPaused(item))
                      ? (_openBlock$6(), _createBlock$4(_component_VListItem, {
                          key: 0, "prepend-icon": "mdi-play-circle-outline",
                          title: torrentResumeLabel(item),
                          onClick: $event => (emit('torrent-action', item, 'resume'))
                        }, null, 8, ["title", "onClick"]))
                      : (_openBlock$6(), _createBlock$4(_component_VListItem, {
                          key: 1, "prepend-icon": "mdi-pause-circle-outline",
                          title: torrentPauseLabel(item), subtitle: "不会被自动恢复",
                          onClick: $event => (emit('torrent-action', item, 'pause'))
                        }, null, 8, ["title", "onClick"])),
                    _createVNode$6(_component_VListItem, {
                      "prepend-icon": "mdi-sync", title: "强制校验",
                      onClick: $event => (emit('torrent-action', item, 'recheck'))
                    }, null, 8, ["onClick"]),
                    // ★ 任务 98：人工结清 —— 与保留 / 删除 / 暂停 / 校验同级，
                    //   只在这颗种子 hash 精确命中「后端允许人工结清」的账单时出现。
                    (hrCanSettle(item))
                      ? (_openBlock$6(), _createBlock$4(_component_VListItem, {
                          key: 8, "prepend-icon": "mdi-check-decagram-outline",
                          title: "人工结清",
                          subtitle: "按该种子 hash 关联 H&R 账单，需填写原因并二次确认",
                          disabled: __props.hrSettleBusy,
                          onClick: $event => (emit('hr-settle', item))
                        }, null, 8, ["disabled", "onClick"]))
                      : _createCommentVNode$5("", true),
                    _createVNode$6(_component_VDivider, { class: "my-1" }),
                    _createVNode$6(_component_VListItem, {
                      "prepend-icon": item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline',
                      title: item.is_protected ? '取消保留' : '手动保种',
                      subtitle: item.is_protected ? '退回自动释放' : '下完也一直做种，不被自动释放',
                      onClick: $event => (emit('torrent-action', item, item.is_protected ? 'unprotect' : 'protect'))
                    }, null, 8, ["prepend-icon", "title", "subtitle", "onClick"]),
                    _createVNode$6(_component_VListItem, {
                      "prepend-icon": "mdi-pin", title: "手动保种（H&R 保挂）",
                      subtitle: "标记后不被静默池收回",
                      onClick: $event => (emit('torrent-action', item, 'hold'))
                    }, null, 8, ["onClick"]),
                    _createVNode$6(_component_VListItem, {
                      "prepend-icon": "mdi-pin-off", title: "解除手动保种",
                      subtitle: "退回静默池（可能被自动暂停）",
                      onClick: $event => (emit('torrent-action', item, 'unhold'))
                    }, null, 8, ["onClick"]),
                    _createVNode$6(_component_VDivider, { class: "my-1" }),
                    _createVNode$6(_component_VListItem, {
                      "prepend-icon": "mdi-delete-outline", title: "删除种子", "base-color": "error",
                      onClick: $event => (emit('delete', item))
                    }, null, 8, ["onClick"]),
                  ]),
                  _: 2
                }, 1024)
              ]),
              _: 2
            }, 1024)
          ])
        ], 10, _hoisted_16$4))
      }), 128)),

      // 空态 / 加载态
      (!pagedRows.value.length)
        ? (_openBlock$6(), _createElementBlock$5("div", _hoisted_14$4, [
            _createElementVNode$6("p", null, _toDisplayString$6(__props.loading ? '正在读取本任务的托管种子…' : '当前筛选下没有托管种子'), 1),
            (!__props.loading && (__props.rows.length === 0))
              ? _createElementVNode$6("p", { class: "mf-pool__empty-sub" }, "种子池只列本任务管辖的种；全局静默池在顶栏「功能中心 → 静默池」")
              : _createCommentVNode$5("", true),
          ]))
        : _createCommentVNode$5("", true),

      // 分页（VDataTable 换手写后必须自己提供；226 颗种一屏拉不完）
      (pageCount.value > 1)
        ? (_openBlock$6(), _createElementBlock$5("div", _hoisted_13$4, [
            _createElementVNode$6("span", { class: "mf-pool__pager-info" }, [
              _createTextVNode$6("共 " + _toDisplayString$6(__props.rows.length) + " 条 · 每页 " + _toDisplayString$6(PAGE_SIZE) + " 条", -1),
            ]),
            _createVNode$6(_component_VSpacer),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "text", icon: "mdi-chevron-left",
              disabled: page.value <= 1, "aria-label": "上一页",
              onClick: $event => (goto(-1))
            }, null, 8, ["disabled"]),
            _createElementVNode$6("span", { class: "mf-pool__pager-page" }, _toDisplayString$6(page.value) + " / " + _toDisplayString$6(pageCount.value), 1),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "text", icon: "mdi-chevron-right",
              disabled: page.value >= pageCount.value, "aria-label": "下一页",
              onClick: $event => (goto(1))
            }, null, 8, ["disabled"]),
          ]))
        : _createCommentVNode$5("", true),
    ]),

    // ── 移动端卡片（≤959 显示；桌面表格隐藏）─────────────────────────────
    _createElementVNode$6("div", _hoisted_15$4, [
      (_openBlock$6(true), _createElementBlock$5(_Fragment$5, null, _renderList$5(__props.rows, (item) => {
        return (_openBlock$6(), _createElementBlock$5("article", {
          key: item.hash || item.title,
          class: ["magicflow-mobile-torrent", hrOpen(item) ? "is-hr" : ""],
          onClick: $event => (emit('open-detail', item))
        }, [
          _createElementVNode$6("div", _hoisted_17$4, [
            _createVNode$6(_component_VCheckbox, {
              "model-value": isSelected(item),
              density: "compact",
              "hide-details": "",
              class: "magicflow-mobile-torrent__check",
              onClick: _withModifiers$1(() => {}, ["stop"]),
              "onUpdate:modelValue": $event => (emit('toggle-row', item))
            }, null, 8, ["model-value"]),
            _createElementVNode$6("div", _hoisted_18$4, [
              _createElementVNode$6("strong", null, _toDisplayString$6(item.title || '未知种子'), 1),
              _createElementVNode$6("span", null, _toDisplayString$6(__props.task.site_name), 1),
            ]),
            _createElementVNode$6("span", {
              class: ["magicflow-mobile-torrent__state", rowStatusTone(item)],
            }, _toDisplayString$6(rowStatusText(item)), 1),
          ]),
          _createVNode$6(_component_VProgressLinear, {
            "model-value": torrentProgressPct(item),
            color: stateColor(item.state),
            height: "6",
            rounded: "",
            class: "magicflow-mobile-torrent__bar"
          }, null, 8, ["model-value", "color"]),
          _createElementVNode$6("div", _hoisted_19$4, [
            _createElementVNode$6("span", null, [
              _createElementVNode$6("em", null, "大小"),
              _createElementVNode$6("b", null, _toDisplayString$6(Number(item.size_gb || 0).toFixed(2)) + " GB", 1),
            ]),
            _createElementVNode$6("span", null, [
              _createElementVNode$6("em", null, "做种"),
              _createElementVNode$6("b", null, _toDisplayString$6(seedDuration(item.seed_time)), 1),
            ]),
            _createElementVNode$6("span", null, [
              _createElementVNode$6("em", null, "分享率"),
              _createElementVNode$6("b", null, _toDisplayString$6(ratioText(item)), 1),
            ]),
            _createElementVNode$6("span", null, [
              _createElementVNode$6("em", null, "上传量"),
              _createElementVNode$6("b", null, _toDisplayString$6(uploadedText(item)), 1),
            ]),
          ]),
          _createElementVNode$6("div", _hoisted_20$4, [
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal",
              color: item.is_protected ? 'grey' : 'primary',
              "prepend-icon": item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline',
              onClick: _withModifiers$1($event => (emit('torrent-action', item, item.is_protected ? 'unprotect' : 'protect')), ["stop"])
            }, {
              default: _withCtx$4(() => [
                _createTextVNode$6(_toDisplayString$6(item.is_protected ? '取消保留' : '保留'), 1),
              ]),
              _: 2
            }, 1032, ["color", "prepend-icon", "onClick"]),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", color: "error", "prepend-icon": "mdi-delete-outline",
              onClick: _withModifiers$1($event => (emit('delete', item)), ["stop"])
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("删除", -1)]]), _: 1 }, 8, ["onClick"]),
            (torrentIsPaused(item))
              ? (_openBlock$6(), _createBlock$4(_component_VBtn, {
                  key: 0, size: "small", variant: "tonal", "prepend-icon": "mdi-play-circle-outline",
                  onClick: _withModifiers$1($event => (emit('torrent-action', item, 'resume')), ["stop"])
                }, {
                  default: _withCtx$4(() => [
                    _createTextVNode$6(_toDisplayString$6(torrentProgressPct(item) >= 100 ? '恢复' : '继续'), 1),
                  ]),
                  _: 2
                }, 1032, ["onClick"]))
              : (_openBlock$6(), _createBlock$4(_component_VBtn, {
                  key: 1, size: "small", variant: "tonal", "prepend-icon": "mdi-pause-circle-outline",
                  onClick: _withModifiers$1($event => (emit('torrent-action', item, 'pause')), ["stop"])
                }, { default: _withCtx$4(() => [...[_createTextVNode$6("暂停", -1)]]), _: 1 }, 8, ["onClick"])),
            _createVNode$6(_component_VBtn, {
              size: "small", variant: "tonal", "prepend-icon": "mdi-sync",
              onClick: _withModifiers$1($event => (emit('torrent-action', item, 'recheck')), ["stop"])
            }, { default: _withCtx$4(() => [...[_createTextVNode$6("校验", -1)]]), _: 1 }, 8, ["onClick"]),
            // ★ 任务 98：移动端卡片操作区同级新增「人工结清」（同一 hash 判据）
            (hrCanSettle(item))
              ? (_openBlock$6(), _createBlock$4(_component_VBtn, {
                  key: 2, size: "small", variant: "tonal", color: "primary",
                  "prepend-icon": "mdi-check-decagram-outline",
                  disabled: __props.hrSettleBusy,
                  onClick: _withModifiers$1($event => (emit('hr-settle', item)), ["stop"])
                }, { default: _withCtx$4(() => [...[_createTextVNode$6("人工结清", -1)]]), _: 1 }, 1032, ["disabled", "onClick"]))
              : _createCommentVNode$5("", true),
          ])
        ], 10, _hoisted_16$4))
      }), 128)),
      (!__props.rows.length)
        ? (_openBlock$6(), _createElementBlock$5("div", _hoisted_14$4, "当前筛选下没有托管种子"))
        : _createCommentVNode$5("", true),
    ]),
  ]))
}
}
};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const SeedingTab = Object.assign(_sfc_main$6, { __scopeId: 'data-v-f0e284f2' })

export default SeedingTab
