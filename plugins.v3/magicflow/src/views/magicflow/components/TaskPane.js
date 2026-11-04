// TaskPane —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './TaskPane.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$e,
  createBlock: _createBlock$f,
  createCommentVNode: _createCommentVNode$e,
  createElementBlock: _createElementBlock$e,
  createElementVNode: _createElementVNode$h,
  createTextVNode: _createTextVNode$g,
  createVNode: _createVNode$g,
  normalizeClass: _normalizeClass$6,
  openBlock: _openBlock$h,
  renderList: _renderList$c,
  resolveComponent: _resolveComponent$h,
  toDisplayString: _toDisplayString$h,
  withCtx: _withCtx$f,
} = __vue

import index from '../index.vue'
import { runModeMeta, taskStateMeta } from '../../../utils.js'
import { taskKindText, taskMetrics } from '../format.js'
import { useTasks } from '../composables/useTasks.js'

const _hoisted_1$f = { class: "magicflow-task-rail__head" };
const _hoisted_2$d = { class: "magicflow-task-list" };
const _hoisted_3$c = ["aria-pressed", "onClick"];
const _hoisted_4$c = { class: "magicflow-task-item__title" };
const _hoisted_5$c = { class: "magicflow-task-item__meta" };
const _hoisted_6$b = ["title"];
const _hoisted_7$a = {
  key: 0,
  class: "magicflow-task-item__idle",
  "aria-hidden": "true"
};
const _hoisted_8$a = { class: "magicflow-task-item__sub" };

const {computed: computed$v} = __vue;


const _sfc_main$h = {
  __name: 'TaskPane',
  props: {
  tasks: { type: Array, default: () => [] },
  selectedId: { type: [String, Number], default: null },
},
  emits: ['select', 'new'],
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 桌面任务栏「内层」（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（内层模板 + 配套 scoped 样式，零行为/样式变更）。
// 外层容器 <VSheet tag="aside" class="magicflow-task-rail app-surface-static"> 留在父页；
// 此处仅含任务栏内层：头部（任务 + 计数）+ 任务列表 + 新建按钮。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不直接调父方法；无 Function prop。
// 契约（docs/REFACTOR-FRONTEND.md §5）以现有数据流为准收敛为：
//   props → tasks / selectedId；emits → select(id) / new。
// taskBadge 是展示型纯函数（真值源仍在 useTasks），此处按同口径本地实现，避免把函数当 prop 传。
const props = __props;

const emit = __emit;

function taskBadge(task) {
  const mode = task?.run_mode || 'running';
  if (mode === 'seeding') return runModeMeta('seeding')
  if (mode === 'stopped') return runModeMeta('stopped')
  return taskStateMeta(task?.state, task?.enabled ?? true)
}

// ★ 19.11.0：指标按任务类型并列展示（主指标 = 考核目标），不再用 v-if/v-else 互斥，
// 使魔力任务也能看到配额下的实际上传产出，且两类任务的数字口径一致、可横向对比。
const rows = computed$v(() => props.tasks.map(task => ({
  task,
  metrics: taskMetrics(task),
  kindText: taskKindText(task),
})));

return (_ctx, _cache) => {
  const _component_VChip = _resolveComponent$h("VChip");
  const _component_VBtn = _resolveComponent$h("VBtn");

  return (_openBlock$h(), _createElementBlock$e(_Fragment$e, null, [
    _createElementVNode$h("div", _hoisted_1$f, [
      _cache[1] || (_cache[1] = _createElementVNode$h("span", { class: "text-subtitle-2" }, "任务", -1)),
      _createVNode$g(_component_VChip, {
        size: "x-small",
        variant: "tonal"
      }, {
        default: _withCtx$f(() => [
          _createTextVNode$g(_toDisplayString$h(__props.tasks.length), 1)
        ]),
        _: 1
      })
    ]),
    _createElementVNode$h("div", _hoisted_2$d, [
      (_openBlock$h(true), _createElementBlock$e(_Fragment$e, null, _renderList$c(rows.value, (row) => {
        return (_openBlock$h(), _createElementBlock$e("button", {
          key: row.task.id,
          type: "button",
          class: _normalizeClass$6(["magicflow-task-item", { 'magicflow-task-item--selected': row.task.id === __props.selectedId }]),
          "aria-pressed": row.task.id === __props.selectedId,
          onClick: $event => (emit('select', row.task.id))
        }, [
          _createElementVNode$h("span", _hoisted_4$c, [
            _createElementVNode$h("strong", null, _toDisplayString$h(row.task.name), 1),
            _createVNode$g(_component_VChip, {
              size: "x-small",
              variant: "tonal",
              color: row.metrics.isBrush ? 'info' : 'primary',
              title: "任务类型：刷流考核上传量，魔力考核魔力值"
            }, {
              default: _withCtx$f(() => [
                _createTextVNode$g(_toDisplayString$h(row.kindText), 1)
              ]),
              _: 2
            }, 1032, ["color"]),
            (row.task.builtin)
              ? (_openBlock$h(), _createBlock$f(_component_VChip, {
                  key: 0,
                  size: "x-small",
                  variant: "tonal",
                  color: "primary"
                }, {
                  default: _withCtx$f(() => [...(_cache[2] || (_cache[2] = [
                    _createTextVNode$g("常驻", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode$e("", true),
            (row.task.site_missing)
              ? (_openBlock$h(), _createBlock$f(_component_VChip, {
                  key: 1,
                  size: "x-small",
                  variant: "tonal",
                  color: "error",
                  title: "站点已删除：相关处理已跳过，请删除任务或改绑站点"
                }, {
                  default: _withCtx$f(() => [...(_cache[3] || (_cache[3] = [
                    _createTextVNode$g("站点已删除", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode$e("", true),
            _createElementVNode$h("span", {
              class: _normalizeClass$6(["magicflow-status-dot", `magicflow-status-dot--${taskBadge(row.task).color}`])
            }, null, 2)
          ]),
          _createElementVNode$h("span", null, _toDisplayString$h(row.task.site_name || row.task.site_domain || ('站点 ' + row.task.site_id)) + " · " + _toDisplayString$h(row.task.downloader), 1),
          _createElementVNode$h("span", _hoisted_5$c, [
            _createElementVNode$h("span", null, _toDisplayString$h(row.metrics.seeds) + " 个种子", 1),
            _createElementVNode$h("span", {
              class: _normalizeClass$6(["magicflow-task-item__main", { 'is-idle': row.metrics.upload.noUpload }]),
              title: row.metrics.upload.noUpload
            ? `有 ${row.metrics.seeds} 个托管种子，但当前 0 个在上传`
            : (row.metrics.isBrush ? '本任务上传（任务级累计）' : '站点时魔（站点级自报）')
            }, [
              _createTextVNode$g(_toDisplayString$h(row.metrics.primary.text), 1),
              (row.metrics.upload.noUpload)
                ? (_openBlock$h(), _createElementBlock$e("span", _hoisted_7$a))
                : _createCommentVNode$e("", true)
            ], 10, _hoisted_6$b),
            _createElementVNode$h("span", _hoisted_8$a, _toDisplayString$h(row.metrics.secondaryText), 1)
          ])
        ], 10, _hoisted_3$c))
      }), 128))
    ]),
    _createVNode$g(_component_VBtn, {
      class: "magicflow-create-task",
      block: "",
      variant: "tonal",
      "prepend-icon": "mdi-plus",
      onClick: _cache[0] || (_cache[0] = $event => (emit('new')))
    }, {
      default: _withCtx$f(() => [...(_cache[4] || (_cache[4] = [
        _createTextVNode$g(" 新建任务 ", -1)
      ]))]),
      _: 1
    })
  ], 64))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const TaskPane = Object.assign(_sfc_main$h, { __scopeId: 'data-v-15655e51' })

export default TaskPane
