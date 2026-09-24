import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, f as formatBonus, t as taskStateMeta, u as unwrapResponse } from './_plugin-vue_export-helper-CdYe8Uyi.js';

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,unref:_unref,resolveComponent:_resolveComponent,createVNode:_createVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,createTextVNode:_createTextVNode,createCommentVNode:_createCommentVNode,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "magicflow-dashboard" };
const _hoisted_2 = { class: "magicflow-dashboard__metrics" };
const _hoisted_3 = { class: "magicflow-dashboard__tasks" };
const _hoisted_4 = {
  key: 0,
  class: "magicflow-dashboard__empty"
};

const {computed,onMounted,onUnmounted,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Dashboard',
  props: {
  api: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
},
  setup(__props) {

const props = __props;

const loading = ref(false);
const status = ref({ summary: {}, tasks: [] });
let refreshTimer;

const enabledTasks = computed(() => (status.value.tasks || []).filter(item => item.enabled).slice(0, 3));

// 从插件接口加载仪表板聚合统计。
async function loadStatus() {
  if (!props.allowRefresh && status.value.tasks?.length) return
  loading.value = true;
  try {
    status.value = unwrapResponse(await props.api.get('plugin/MagicFlow/status')) || status.value;
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.allowRefresh,
  enabled => {
    if (enabled) loadStatus();
  },
);

onMounted(() => {
  loadStatus();
  refreshTimer = window.setInterval(loadStatus, 30000);
});

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer);
});

return (_ctx, _cache) => {
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _createElementVNode("div", null, [
        _cache[0] || (_cache[0] = _createElementVNode("span", null, "启用任务", -1)),
        _createElementVNode("strong", null, _toDisplayString(status.value.summary.enabled_tasks || 0) + " / " + _toDisplayString(status.value.summary.total_tasks || 0), 1)
      ]),
      _createElementVNode("div", null, [
        _cache[1] || (_cache[1] = _createElementVNode("span", null, "托管种子", -1)),
        _createElementVNode("strong", null, _toDisplayString(status.value.summary.seeding_count || 0), 1)
      ]),
      _createElementVNode("div", null, [
        _cache[2] || (_cache[2] = _createElementVNode("span", null, "每小时魔力", -1)),
        _createElementVNode("strong", null, _toDisplayString(_unref(formatBonus)(status.value.summary.bonus_per_hour)), 1)
      ]),
      _createElementVNode("div", null, [
        _cache[3] || (_cache[3] = _createElementVNode("span", null, "站点当前魔力", -1)),
        _createElementVNode("strong", null, _toDisplayString(Number(status.value.summary.current_bonus || 0).toFixed(2)), 1)
      ])
    ]),
    _createVNode(_component_VDivider),
    _createElementVNode("div", _hoisted_3, [
      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(enabledTasks.value, (task) => {
        return (_openBlock(), _createElementBlock("div", {
          key: task.id
        }, [
          _createVNode(_component_VIcon, {
            icon: _unref(taskStateMeta)(task.state, task.enabled).icon,
            color: _unref(taskStateMeta)(task.state, task.enabled).color,
            size: "18"
          }, null, 8, ["icon", "color"]),
          _createElementVNode("div", null, [
            _createElementVNode("strong", null, _toDisplayString(task.name), 1),
            _createElementVNode("span", null, _toDisplayString(task.site_name) + " · " + _toDisplayString(task.seeding_count || 0) + " 个种子", 1)
          ]),
          _createElementVNode("span", null, _toDisplayString(_unref(formatBonus)(task.bonus_per_hour)), 1)
        ]))
      }), 128)),
      (!enabledTasks.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_4, [
            _createVNode(_component_VIcon, { icon: "mdi-star-four-points-outline" }),
            _cache[4] || (_cache[4] = _createTextVNode(" 暂无启用的魔力任务 ", -1))
          ]))
        : _createCommentVNode("", true)
    ]),
    (loading.value)
      ? (_openBlock(), _createBlock(_component_VProgressLinear, {
          key: 0,
          indeterminate: "",
          color: "primary",
          height: "2"
        }))
      : _createCommentVNode("", true)
  ]))
}
}

};
const Dashboard = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-b4f60304"]]);

export { Dashboard as default };
