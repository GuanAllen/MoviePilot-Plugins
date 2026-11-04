// TaskConfigTab —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './TaskConfigTab.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$8,
  createBlock: _createBlock$7,
  createCommentVNode: _createCommentVNode$8,
  createElementBlock: _createElementBlock$8,
  createElementVNode: _createElementVNode$9,
  createTextVNode: _createTextVNode$8,
  createVNode: _createVNode$8,
  openBlock: _openBlock$9,
  resolveComponent: _resolveComponent$9,
  toDisplayString: _toDisplayString$9,
  unref: _unref$4,
  withCtx: _withCtx$7,
} = __vue

import index from '../../index.vue'
import { currencyOf } from '../../composables/useCurrency.js'

const _hoisted_1$8 = { class: "magicflow-config-grid" };
const _hoisted_2$8 = { class: "magicflow-panel__head" };
const _hoisted_3$7 = { class: "text-subtitle-1 font-weight-medium" };
const _hoisted_4$7 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_5$7 = { class: "magicflow-facts magicflow-facts--two" };
const _hoisted_6$6 = { class: "magicflow-config-actions" };

const _sfc_main$9 = {
  __name: 'TaskConfigTab',
  props: {
  task: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  runMode: { type: Object, default: () => ({ text: '' }) },
  goalText: { type: String, default: '' },
  isBrush: { type: Boolean, default: false },
  brushSeedDays: { type: Number, default: 0 },
  saving: { type: Boolean, default: false },
},
  emits: ['run', 'edit', 'delete'],
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 任务配置（只读参数）面板（P4）
// P4 拆分：自 views/magicflow/index.vue 的 <VWindowItem value="config"> 面板**纯搬家**
// （template 块 + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 只读派生值（isBrush / config / runMode / goalText / brushSeedDays）由父页 composable 计算后传入，
// 子组件不重复计算（单一真值源）。
// props 下（只读）：task=selectedTask / config=taskConfig / runMode=selectedRunMode /
// goalText=goalFactText / isBrush=taskIsBrush / brushSeedDays / saving。
// 只读派生值由父页 composable 计算后传入，子组件不重复计算（单一真值源）。
// ★ 19.10.48：站点货币名（各站自称不同），仅用于「站点当前 X」这类数值说明。
//   纯函数、开销可忽略，模板里直接用 currencyOf(task)。


const emit = __emit;

return (_ctx, _cache) => {
  const _component_VChip = _resolveComponent$9("VChip");
  const _component_VSheet = _resolveComponent$9("VSheet");
  const _component_VBtn = _resolveComponent$9("VBtn");
  const _component_VDivider = _resolveComponent$9("VDivider");

  return (_openBlock$9(), _createElementBlock$8("div", _hoisted_1$8, [
    _createVNode$8(_component_VSheet, {
      tag: "section",
      class: "magicflow-panel app-surface-static"
    }, {
      default: _withCtx$7(() => [
        _createElementVNode$9("header", _hoisted_2$8, [
          _createElementVNode$9("div", null, [
            _createElementVNode$9("div", _hoisted_3$7, _toDisplayString$9(__props.isBrush ? '刷流规则' : '魔力规则'), 1),
            _createElementVNode$9("div", _hoisted_4$7, _toDisplayString$9(__props.isBrush ? '刷流标准：免费 + 有下载者；做种满天数清理' : '当前服务端生效的魔力养护配置'), 1)
          ])
        ]),
        _createElementVNode$9("dl", _hoisted_5$7, [
          _createElementVNode$9("div", null, [
            _cache[3] || (_cache[3] = _createElementVNode$9("dt", null, "任务状态", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.runMode.text), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[4] || (_cache[4] = _createElementVNode$9("dt", null, "任务目标", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.goalText), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[6] || (_cache[6] = _createElementVNode$9("dt", null, "站点", -1)),
            _createElementVNode$9("dd", null, [
              _createTextVNode$8(_toDisplayString$9(__props.task.site_name || __props.task.site_domain || '未设置') + " ", 1),
              (__props.task.site_missing)
                ? (_openBlock$9(), _createBlock$7(_component_VChip, {
                    key: 0,
                    size: "x-small",
                    variant: "tonal",
                    color: "error",
                    title: "站点已删除：相关处理已跳过，请删除任务或改绑站点"
                  }, {
                    default: _withCtx$7(() => [...(_cache[5] || (_cache[5] = [
                      _createTextVNode$8("站点已删除", -1)
                    ]))]),
                    _: 1
                  }))
                : _createCommentVNode$8("", true)
            ])
          ]),
          _createElementVNode$9("div", null, [
            _cache[7] || (_cache[7] = _createElementVNode$9("dt", null, "下载器", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.task.downloader), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[8] || (_cache[8] = _createElementVNode$9("dt", null, "下载器标签", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.task.brush_tag || '未设置'), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[9] || (_cache[9] = _createElementVNode$9("dt", null, "促销要求", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.isBrush ? '免费（含 2X免费）' : (__props.config.freeleech === '2xfree' ? '2X 免费' : __props.config.freeleech === 'free' ? '免费' : '全部')), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[10] || (_cache[10] = _createElementVNode$9("dt", null, "选种来源", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.rss_support ? 'RSS' : '站点列表页'), 1)
          ]),
          (__props.isBrush)
            ? (_openBlock$9(), _createElementBlock$8(_Fragment$8, { key: 0 }, [
                _createElementVNode$9("div", null, [
                  _cache[11] || (_cache[11] = _createElementVNode$9("dt", null, "轮转周期", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.brushSeedDays > 0 ? `做种满 ${__props.brushSeedDays} 天清理` : '不按天数（按无上传）'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[12] || (_cache[12] = _createElementVNode$9("dt", null, "最小下载人数", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.brush_min_leechers ?? 1) + " 人", 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[13] || (_cache[13] = _createElementVNode$9("dt", null, "种子大小", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.size || '不限'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[14] || (_cache[14] = _createElementVNode$9("dt", null, "做种人数", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.seeder || '不限'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[15] || (_cache[15] = _createElementVNode$9("dt", null, "发布时间", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.pubtime ? `${__props.config.pubtime} 分钟` : '不限'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[16] || (_cache[16] = _createElementVNode$9("dt", null, "排除 H&R", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.hr === 'yes' ? '是' : '否'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[17] || (_cache[17] = _createElementVNode$9("dt", null, "包含规则", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.include || '无'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[18] || (_cache[18] = _createElementVNode$9("dt", null, "排除规则", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.exclude || '无'), 1)
                ])
              ], 64))
            : (_openBlock$9(), _createElementBlock$8(_Fragment$8, { key: 1 }, [
                _createElementVNode$9("div", null, [
                  _cache[19] || (_cache[19] = _createElementVNode$9("dt", null, "保种体积", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.disk_size_gb ? `${__props.config.disk_size_gb} GB` : '不限'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[20] || (_cache[20] = _createElementVNode$9("dt", null, "最低魔力", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.min_bonus_per_hour == null ? '自动' : `${Number(__props.config.min_bonus_per_hour).toFixed(2)} /h`), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[21] || (_cache[21] = _createElementVNode$9("dt", null, "最多保留", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.max_keep_torrents == null ? '自动 / 不限' : `${__props.config.max_keep_torrents} 个`), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[22] || (_cache[22] = _createElementVNode$9("dt", null, "保护阈值", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.bonus_protect_threshold == null ? `站点当前${_unref$4(currencyOf)(__props.task)}` : Number(__props.config.bonus_protect_threshold).toFixed(0)), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[23] || (_cache[23] = _createElementVNode$9("dt", null, "完美种保护", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.protect_perfect === false ? '关闭' : `开启（≤${__props.config.perfect_max_seeders ?? 3}人 · ≥${__props.config.perfect_min_weeks ?? 4}周）`), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[24] || (_cache[24] = _createElementVNode$9("dt", null, "公式 T0/N0", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.bonus_t0 ?? '默认') + " / " + _toDisplayString$9(__props.config.bonus_n0 ?? '默认'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[25] || (_cache[25] = _createElementVNode$9("dt", null, "公式 B0/L", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.bonus_b0 ?? '默认') + " / " + _toDisplayString$9(__props.config.bonus_l ?? '默认'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[26] || (_cache[26] = _createElementVNode$9("dt", null, "零魔权重", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.bonus_zero_weight ?? '默认'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[27] || (_cache[27] = _createElementVNode$9("dt", null, "保底魔力", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(Number(__props.config.min_bonus_to_keep || 0).toFixed(2)), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[28] || (_cache[28] = _createElementVNode$9("dt", null, "种子大小", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.size || '不限'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[29] || (_cache[29] = _createElementVNode$9("dt", null, "做种人数", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.seeder || '不限'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[30] || (_cache[30] = _createElementVNode$9("dt", null, "发布时间", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.pubtime ? `${__props.config.pubtime} 分钟` : '不限'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[31] || (_cache[31] = _createElementVNode$9("dt", null, "排除 H&R", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.hr === 'yes' ? '是' : '否'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[32] || (_cache[32] = _createElementVNode$9("dt", null, "包含规则", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.include || '无'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[33] || (_cache[33] = _createElementVNode$9("dt", null, "排除规则", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.exclude || '无'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[34] || (_cache[34] = _createElementVNode$9("dt", null, "本地保护期", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.min_seed_time ? `${__props.config.min_seed_time} 小时` : '不限'), 1)
                ]),
                _createElementVNode$9("div", null, [
                  _cache[35] || (_cache[35] = _createElementVNode$9("dt", null, "最低分享率", -1)),
                  _createElementVNode$9("dd", null, _toDisplayString$9(Number(__props.config.min_ratio || 0).toFixed(2)), 1)
                ])
              ], 64)),
          _createElementVNode$9("div", null, [
            _cache[36] || (_cache[36] = _createElementVNode$9("dt", null, "单轮最多新增", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.max_add_per_run ?? 10) + " 个", 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[37] || (_cache[37] = _createElementVNode$9("dt", null, "同时下载上限", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.max_download_concurrent ?? 10) + " 个", 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[38] || (_cache[38] = _createElementVNode$9("dt", null, "每轮参评候选", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.top_n ?? 30) + " 个", 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[39] || (_cache[39] = _createElementVNode$9("dt", null, "每轮翻页数", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.browse_pages ?? 3) + " 页", 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[40] || (_cache[40] = _createElementVNode$9("dt", null, "自动补种", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.refill_when_empty ? '开启' : '关闭'), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[41] || (_cache[41] = _createElementVNode$9("dt", null, "无进度清理", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.cleanup_no_progress ? `开启（${__props.config.no_progress_minutes ?? 30} 分钟）` : '关闭'), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[42] || (_cache[42] = _createElementVNode$9("dt", null, "慢速清理", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.cleanup_slow_progress === false ? '关闭' : `开启（> ${__props.config.slow_progress_max_hours ?? 48}h 下不完即清）`), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[43] || (_cache[43] = _createElementVNode$9("dt", null, "促销失效清理", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）'), 1)
          ]),
          _createElementVNode$9("div", null, [
            _cache[44] || (_cache[44] = _createElementVNode$9("dt", null, "自动恢复暂停", -1)),
            _createElementVNode$9("dd", null, _toDisplayString$9(__props.config.auto_resume_paused === false ? '关闭' : '开启'), 1)
          ])
        ])
      ]),
      _: 1
    }),
    _createVNode$8(_component_VSheet, {
      tag: "section",
      class: "magicflow-panel app-surface-static"
    }, {
      default: _withCtx$7(() => [
        _cache[52] || (_cache[52] = _createElementVNode$9("header", { class: "magicflow-panel__head" }, [
          _createElementVNode$9("div", null, [
            _createElementVNode$9("div", { class: "text-subtitle-1 font-weight-medium" }, "任务操作"),
            _createElementVNode$9("div", { class: "text-body-2 text-medium-emphasis" }, "以下操作只影响当前任务")
          ])
        ], -1)),
        _createElementVNode$9("div", _hoisted_6$6, [
          _createElementVNode$9("div", null, [
            _cache[46] || (_cache[46] = _createElementVNode$9("strong", null, "执行一次", -1)),
            _createElementVNode$9("span", null, _toDisplayString$9(__props.isBrush ? '立即按刷流标准抓取免费热种并保持上传' : '立即按当前策略抓取候选并养护做种'), 1),
            _createVNode$8(_component_VBtn, {
              color: "primary",
              variant: "tonal",
              "prepend-icon": "mdi-sync",
              loading: __props.saving,
              onClick: _cache[0] || (_cache[0] = $event => (emit('run')))
            }, {
              default: _withCtx$7(() => [...(_cache[45] || (_cache[45] = [
                _createTextVNode$8(" 立即执行 ", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ]),
          _createVNode$8(_component_VDivider),
          _createElementVNode$9("div", null, [
            _cache[48] || (_cache[48] = _createElementVNode$9("strong", null, "编辑任务", -1)),
            _createElementVNode$9("span", null, _toDisplayString$9(__props.isBrush ? '调整调度、刷流门槛与清理策略' : '调整调度、魔力门槛与公式参数'), 1),
            _createVNode$8(_component_VBtn, {
              variant: "tonal",
              "prepend-icon": "mdi-pencil-outline",
              onClick: _cache[1] || (_cache[1] = $event => (emit('edit')))
            }, {
              default: _withCtx$7(() => [...(_cache[47] || (_cache[47] = [
                _createTextVNode$8("编辑任务", -1)
              ]))]),
              _: 1
            })
          ]),
          _createVNode$8(_component_VDivider),
          _createElementVNode$9("div", null, [
            _cache[50] || (_cache[50] = _createElementVNode$9("strong", null, "删除任务", -1)),
            _cache[51] || (_cache[51] = _createElementVNode$9("span", null, "存在活跃种子时后端会拒绝删除，避免失管任务", -1)),
            _createVNode$8(_component_VBtn, {
              color: "error",
              variant: "tonal",
              "prepend-icon": "mdi-delete-outline",
              onClick: _cache[2] || (_cache[2] = $event => (emit('delete')))
            }, {
              default: _withCtx$7(() => [...(_cache[49] || (_cache[49] = [
                _createTextVNode$8("删除任务", -1)
              ]))]),
              _: 1
            })
          ])
        ])
      ]),
      _: 1
    })
  ]))
}
}

};
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const TaskConfigTab = Object.assign(_sfc_main$9, { __scopeId: 'data-v-0c39928f' })

export default TaskConfigTab
