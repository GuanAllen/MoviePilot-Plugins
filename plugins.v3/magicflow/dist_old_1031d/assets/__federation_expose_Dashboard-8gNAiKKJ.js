import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, f as formatBonus, t as taskStateMeta, u as unwrapResponse } from './_plugin-vue_export-helper-DZmhfy2R.js';

const {toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,createElementVNode:_createElementVNode,unref:_unref} = await importShared('vue');


const _hoisted_1 = { class: "mf-stat-grid" };
const _hoisted_2 = { class: "mf-stat-copy" };
const _hoisted_3 = { class: "mf-stat-label" };
const _hoisted_4 = { class: "mf-number" };
const _hoisted_5 = {
  key: 0,
  class: "mf-stat-addition"
};
const _hoisted_6 = { class: "mf-number mf-number--sm" };
const _hoisted_7 = {
  key: 1,
  class: "text-center text-medium-emphasis py-4"
};

const {computed,onMounted,onUnmounted,ref,watch} = await importShared('vue');

// ★ 15.17.6：卡片外观与「刷新方式」双双对齐 MP 原生仪表板。
//   外观：MP 前端 dashboard 渲染分支写死
//     ``render_mode === 'vue' ? 挂插件联邦组件 : 'vuetify' ? 渲染宿主 elements``，
//   我们是 vue 模式（工作台/侧栏都靠它），宿主只给一个
//   ``<div class="dashboard-plugin-vue-renderer">`` 空壳 —— 卡片长啥样全由本组件决定。
//   故照抄 MP 原生卡片骨架与度量（bundle 里扒的 CSS 原值）：
//     VCard(variant=elevated/elevation-0/rounded-lg) + VCardItem(标题/副标题) + VCardText
//     + 统计区 .dashboard-stat-grid（桌面 4 列 / ≤740px 2 列、row-gap 1rem、竖分隔线、
//       标签 .72rem、数值 1.15rem/700/tabular-nums、附加行 .72rem 成功色）
//     + 任务行用 v-list（对齐 MP「Background Tasks」卡片的列表观感）。
//   刷新：MP 原生卡片刷新是「静默」的（只有首屏骨架，后台更新不闪任何进度条），
//   且刷新信号由宿主下发（vue 模式给子组件 ``allow-refresh`` 属性）。
//   故：首屏才显加载条；之后按宿主信号 + 本地兜底定时器静默更新，不闪、不跳版式；
//   并在首屏就绪后 emit('loaded') 回执宿主（MP 的 DashboardElement 约定）。


const _sfc_main = {
  __name: 'Dashboard',
  props: {
  api: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
},
  emits: ['loaded'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = ref(false); // 仅首屏用（驱动 v-card 顶部细进度条）
const refreshing = ref(false); // 后台静默刷新中（不驱动任何视觉）
const status = ref({ summary: {}, tasks: [] });
let refreshTimer;
let loadCount = 0;
let loadedEmitted = false;

const title = computed(() => props.config?.attrs?.title || '魔流');
const subtitle = computed(() => props.config?.attrs?.subtitle || '魔力产出概览');

// 口径与工作台首页一致：run_mode ∈ {running, seeding} 才算「在跑」（`enabled` 只是「调度是否启用」）。
const ACTIVE_MODES = ['running', 'seeding'];
const activeTasks = computed(() =>
  (status.value.tasks || [])
    .filter(item => !item.builtin && ACTIVE_MODES.includes(item.run_mode || 'running'))
    .sort((a, b) => Number(b.bonus_per_hour || 0) - Number(a.bonus_per_hour || 0))
    .slice(0, 3),
);
const activeCount = computed(() => Number(status.value.summary.active_tasks ?? status.value.summary.running_tasks ?? 0));

const metrics = computed(() => {
  const s = status.value.summary || {};
  return [
    { key: 'active', icon: 'mdi-radar', label: '在跑 / 共', value: `${activeCount.value} / ${Number(s.total_tasks || 0)}` },
    { key: 'seeding', icon: 'mdi-seed-outline', label: '托管种子', value: `${Number(s.seeding_count || 0)}` },
    { key: 'bph', icon: 'mdi-star-four-points-outline', label: '每小时魔力', value: formatBonus(s.bonus_per_hour).replace(' /h', '') },
    {
      key: 'bonus',
      icon: 'mdi-chart-donut',
      label: '当前魔力',
      value: Number(s.current_bonus || 0).toLocaleString('en-US', { maximumFractionDigits: 0 }),
      addition: `上限 ${Number(s.ceiling_pct || 0).toFixed(0)}%`,
    },
  ]
});

// 从插件接口加载仪表板聚合统计。
// silent=true → 后台刷新：不触发任何 loading 视觉，失败保留旧数据。
async function loadStatus({ silent = false } = {}) {
  if (silent) {
    if (refreshing.value) return
    refreshing.value = true;
  } else {
    loading.value = true;
  }
  try {
    const data = unwrapResponse(await props.api.get('plugin/MagicFlow/status'));
    if (data) status.value = data;
  } catch {
    // 静默失败：保留上一次的数据，不闪错误态
  } finally {
    loading.value = false;
    refreshing.value = false;
    loadCount += 1;
    if (!loadedEmitted && loadCount > 0) {
      loadedEmitted = true;
      emit('loaded');
    }
  }
}

watch(
  () => props.allowRefresh,
  enabled => {
    if (enabled) loadStatus({ silent: loadCount > 0 });
  },
);

onMounted(() => {
  loadStatus();
  // 兜底：宿主未下发刷新信号时也保持数据新鲜（静默，无视觉副作用）
  refreshTimer = window.setInterval(() => loadStatus({ silent: true }), 30000);
});

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer);
});

return (_ctx, _cache) => {
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VCardSubtitle = _resolveComponent("VCardSubtitle");
  const _component_VCardItem = _resolveComponent("VCardItem");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VAvatar = _resolveComponent("VAvatar");
  const _component_VListItemTitle = _resolveComponent("VListItemTitle");
  const _component_VListItemSubtitle = _resolveComponent("VListItemSubtitle");
  const _component_VListItem = _resolveComponent("VListItem");
  const _component_VList = _resolveComponent("VList");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");

  return (_openBlock(), _createBlock(_component_VCard, {
    class: "magicflow-dashboard rounded-lg elevation-0",
    variant: "elevated",
    loading: loading.value
  }, {
    default: _withCtx(() => [
      _createVNode(_component_VCardItem, null, {
        default: _withCtx(() => [
          _createVNode(_component_VCardTitle, { class: "text-body-1" }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(title.value), 1)
            ]),
            _: 1
          }),
          (subtitle.value)
            ? (_openBlock(), _createBlock(_component_VCardSubtitle, { key: 0 }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(subtitle.value), 1)
                ]),
                _: 1
              }))
            : _createCommentVNode("", true)
        ]),
        _: 1
      }),
      _createVNode(_component_VCardText, { class: "pt-0" }, {
        default: _withCtx(() => [
          _createElementVNode("div", _hoisted_1, [
            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(metrics.value, (item) => {
              return (_openBlock(), _createElementBlock("div", {
                key: item.key,
                class: "mf-stat-item"
              }, [
                _createVNode(_component_VAvatar, {
                  size: "38",
                  class: "bg-primary"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VIcon, {
                      icon: item.icon,
                      size: "20"
                    }, null, 8, ["icon"])
                  ]),
                  _: 2
                }, 1024),
                _createElementVNode("div", _hoisted_2, [
                  _createElementVNode("span", _hoisted_3, _toDisplayString(item.label), 1),
                  _createElementVNode("span", _hoisted_4, _toDisplayString(item.value), 1),
                  (item.addition)
                    ? (_openBlock(), _createElementBlock("span", _hoisted_5, _toDisplayString(item.addition), 1))
                    : _createCommentVNode("", true)
                ])
              ]))
            }), 128))
          ]),
          (activeTasks.value.length)
            ? (_openBlock(), _createBlock(_component_VList, {
                key: 0,
                class: "mf-task-list",
                density: "compact"
              }, {
                default: _withCtx(() => [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(activeTasks.value, (task) => {
                    return (_openBlock(), _createBlock(_component_VListItem, {
                      key: task.id,
                      class: "px-0"
                    }, {
                      prepend: _withCtx(() => [
                        _createVNode(_component_VAvatar, {
                          size: "32",
                          color: _unref(taskStateMeta)(task.state).color,
                          class: "me-3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VIcon, {
                              icon: _unref(taskStateMeta)(task.state).icon,
                              size: "18"
                            }, null, 8, ["icon"])
                          ]),
                          _: 2
                        }, 1032, ["color"])
                      ]),
                      append: _withCtx(() => [
                        _createElementVNode("span", _hoisted_6, _toDisplayString(_unref(formatBonus)(task.bonus_per_hour)), 1)
                      ]),
                      default: _withCtx(() => [
                        _createVNode(_component_VListItemTitle, { class: "text-body-2" }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(task.name), 1)
                          ]),
                          _: 2
                        }, 1024),
                        _createVNode(_component_VListItemSubtitle, { class: "text-caption" }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(task.site_name || task.site_domain) + " · " + _toDisplayString(task.seeding_count || 0) + " 种 ", 1)
                          ]),
                          _: 2
                        }, 1024)
                      ]),
                      _: 2
                    }, 1024))
                  }), 128))
                ]),
                _: 1
              }))
            : (!loading.value)
              ? (_openBlock(), _createElementBlock("div", _hoisted_7, "暂无在跑的魔力任务"))
              : _createCommentVNode("", true)
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["loading"]))
}
}

};
const Dashboard = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-fe8fae67"]]);

export { Dashboard as default };
