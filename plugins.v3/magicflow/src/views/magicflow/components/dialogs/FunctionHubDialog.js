// FunctionHubDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './FunctionHubDialog.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$i,
  createBlock: _createBlock$i,
  createCommentVNode: _createCommentVNode$i,
  createElementBlock: _createElementBlock$i,
  createElementVNode: _createElementVNode$l,
  createTextVNode: _createTextVNode$k,
  createVNode: _createVNode$k,
  mergeModels: _mergeModels$a,
  openBlock: _openBlock$l,
  renderList: _renderList$g,
  resolveComponent: _resolveComponent$l,
  toDisplayString: _toDisplayString$l,
  useModel: _useModel$a,
  withCtx: _withCtx$i,
  withDirectives: _withDirectives$1,
  vModelText: _vModelText
} = __vue

import { MF_PAGES } from '../../constants.js'

const _hoisted_1$j = { class: "mfhub__head" };
const _hoisted_2$h = { class: "mfhub__search" };
const _hoisted_3$g = { class: "mfhub__body" };
const _hoisted_4$g = { class: "mfhub__primary-icon" };
const _hoisted_5$g = { class: "mfhub__group-head" };
const _hoisted_6$f = { key: 0 };
const _hoisted_7$e = { class: "mfhub__grid" };
const _hoisted_8$d = ["onClick"];
const _hoisted_9$b = { class: "mfhub__text" };
const _hoisted_10$b = {
  key: 1,
  class: "mfhub__empty"
};

const {computed: computed$x,ref: ref$t} = __vue;



const _sfc_main$l = {
  __name: 'FunctionHubDialog',
  props: /*@__PURE__*/_mergeModels$a({
  pages: { type: Array, default: () => [] }, // MF_PAGES（14 项，须与后端 FEATURES 对齐）
  narrow: { type: Boolean, default: false },
  badges: { type: Object, default: () => ({}) }, // 角标：recommend / exam / notify / jobs
}, {
    "modelValue": { type: Boolean, default: false },
    "modelModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$a(['open'], ["update:modelValue"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 功能中心（弹层）
// 定位：**全部功能入口的唯一落地页**。页头按设计稿只留「通知 / 设置 / 功能中心」三样，
// 原先散在页头的一排图标（推荐·云盘·跨站·豆瓣·健康·点播·考核·补源·站点报表）与
// 「更多 ⋮」菜单里的次级项（音乐·库内资源·后台任务·趋势·优化·计划·通知·认领·RSS·
// 静默池·H&R·容量·操作记录·新建任务·关闭）全部收进这里。
// 权责：数据向下（pages / badges）、事件向上（emit('open', page|key)），自身不直接调 api。
// ★ 样式全部自带：父级 index.vue 的 <style scoped> 不会命中子组件，别依赖它。
const open = _useModel$a(__props, "modelValue");

const props = __props;

const emit = __emit;

// 一句话说清「点进去能干什么」（卡片副标题）
const DESC = {
  ondemand: '片名 / 链接 → 选源下载',
  recommend: '按评分自动选种',
  exam: '新手考核进度与救急',
  signin: '各站点一键签到',
  cloud: '本地 → 云盘归档',
  douban: '库容量与评分源',
  crossseed: '已有资源去他站落户',
  claim: '发布站认领种子',
  rss: '订阅自动下载',
  silent: '静默池按站点托管',
  keep: '人工点名的种：一直做种、不被自动释放',
  sitereport: '站点维度汇总报表',
  hrbills: 'H&R 欠种与临期',
  ceiling: '站点魔力容量水位',
  ops: '全站操作流水',
  settings: '插件参数与开关',
  assets: '删除 / 保护 / 订阅 / 整理 / 刮削',
  music: '清单：进行中 / 已完成',
  rescue: '停滞欠 H&R → 他站补种',
  jobs: '整理入库 / 订阅 / 刮削 进度',
  pushes: '每次加种一条：成败与原始报错',
  trend: '时魔走向与拐点归因',
  optimize: '体积预算内保谁删谁',
  plan: '计划 → 干跑 → 批准执行',
  notify: 'H&R 临期 / 容量红线 / 产出骤降',
  health: '各子系统自检与一键修复',
  create: '选站点、定模式、开跑',
  close: '退出 MagicFlow 插件页',
};

// ★ 次级入口：不在后端 FEATURES 里（塞进 MF_PAGES 会让 preflight 5/17 前后端对齐挂掉），
//   但它们本就是这个「功能中心」该有的格子 —— 原先只藏在顶栏图标与「更多」菜单里。
const EXTRA_PAGES = [
  { key: 'ondemand', label: '点播', icon: 'mdi-cloud-download-outline', scope: 'global' },
  { key: 'keep', label: '手动保种', icon: 'mdi-pin', scope: 'global' },
  { key: 'health', label: '健康自检', icon: 'mdi-heart-pulse', scope: 'global' },
  { key: 'assets', label: '库内资源管理', icon: 'mdi-folder-cog-outline', scope: 'global' },
  { key: 'music', label: '音乐', icon: 'mdi-music-circle-outline', scope: 'global' },
  { key: 'rescue', label: '死种补源', icon: 'mdi-lifebuoy', scope: 'global' },
  { key: 'jobs', label: '后台任务', icon: 'mdi-progress-clock', scope: 'view' },
  { key: 'pushes', label: '推送记录', icon: 'mdi-send-check-outline', scope: 'view' },
  { key: 'trend', label: '魔力趋势', icon: 'mdi-chart-timeline-variant', scope: 'view' },
  { key: 'optimize', label: '组合优化', icon: 'mdi-chart-timeline-variant-shimmer', scope: 'view' },
  { key: 'plan', label: 'AI 计划审批', icon: 'mdi-clipboard-check-outline', scope: 'view' },
  { key: 'notify', label: '事件通知', icon: 'mdi-bell-ring-outline', scope: 'view' },
];

// 页头级主操作：新建任务（原来在页头那颗实心按钮，收进这里当第一格）
const CREATE_PAGE = { key: 'create', label: '新建任务', icon: 'mdi-plus', scope: 'action' };
// 页头原先的 ✕：设计稿没有它，但功能不能丢 —— 放进「配置」组
const CLOSE_PAGE = { key: 'close', label: '关闭插件页', icon: 'mdi-close', scope: 'settings' };

const q = ref$t('');

const allPages = computed$x(() => {
  const seen = new Set();
  const out = [];
  for (const p of [...(props.pages || []), ...EXTRA_PAGES]) {
    if (!p || !p.key || seen.has(p.key)) continue
    seen.add(p.key);
    out.push(p);
  }
  return out
});

const groups = computed$x(() => {
  const list = allPages.value;
  const out = [
    { key: 'global', title: '常用功能', hint: '插件级单例', items: list.filter(p => p.scope === 'global' && p.key !== 'settings') },
    { key: 'view', title: '报表与工具', hint: '只读汇总 / 诊断 / 审批', items: list.filter(p => p.scope === 'view') },
    { key: 'settings', title: '配置', hint: '', items: [...list.filter(p => p.key === 'settings'), CLOSE_PAGE] },
  ];
  return out.filter(g => g.items.length)
});

// 搜索：命中名称或说明即保留（组标题保留，空组丢弃）
const kw = computed$x(() => String(q.value || '').trim().toLowerCase());
const filteredGroups = computed$x(() => {
  const k = kw.value;
  if (!k) return groups.value
  return groups.value
    .map(g => ({
      ...g,
      items: g.items.filter(p => (`${p.label || ''} ${DESC[p.key] || ''} ${p.key}`).toLowerCase().includes(k)),
    }))
    .filter(g => g.items.length)
});

const total = computed$x(() => allPages.value.length + 1);

// ★ 模板只能用「本文件显式声明过的标识符」（preflight 13/17 守卫）：props 字段要包一层再到模板用
const isFullscreen = computed$x(() => !!props.narrow);
const badgeMap = computed$x(() => props.badges || {});
function badgeFor(key) {
  const v = Number((badgeMap.value || {})[key] || 0);
  return Number.isFinite(v) && v > 0 ? v : 0
}

function pick(page) {
  open.value = false;
  emit('open', page);
}

return (_ctx, _cache) => {
  const _component_VChip = _resolveComponent$l("VChip");
  const _component_VIcon = _resolveComponent$l("VIcon");
  const _component_VBtn = _resolveComponent$l("VBtn");
  const _component_VCard = _resolveComponent$l("VCard");
  const _component_VDialog = _resolveComponent$l("VDialog");

  return (_openBlock$l(), _createBlock$i(_component_VDialog, {
    modelValue: open.value,
    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((open).value = $event)),
    "max-width": "60rem",
    scrollable: "",
    fullscreen: isFullscreen.value
  }, {
    default: _withCtx$i(() => [
      _createVNode$k(_component_VCard, { class: "mfhub" }, {
        default: _withCtx$i(() => [
          _createElementVNode$l("header", _hoisted_1$j, [
            _cache[5] || (_cache[5] = _createElementVNode$l("span", { class: "mfhub__title" }, "功能中心", -1)),
            _createVNode$k(_component_VChip, {
              size: "x-small",
              color: "grey",
              variant: "tonal"
            }, {
              default: _withCtx$i(() => [
                _createTextVNode$k(_toDisplayString$l(total.value) + " 个入口", 1)
              ]),
              _: 1
            }),
            _cache[6] || (_cache[6] = _createElementVNode$l("span", { class: "mfhub__spacer" }, null, -1)),
            _createElementVNode$l("label", _hoisted_2$h, [
              _createVNode$k(_component_VIcon, {
                icon: "mdi-magnify",
                size: "16"
              }),
              _withDirectives$1(_createElementVNode$l("input", {
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((q).value = $event)),
                type: "text",
                placeholder: "搜索功能…",
                "aria-label": "搜索功能"
              }, null, 512), [
                [_vModelText, q.value]
              ]),
              (q.value)
                ? (_openBlock$l(), _createElementBlock$i("button", {
                    key: 0,
                    type: "button",
                    class: "mfhub__search-clear",
                    "aria-label": "清空",
                    onClick: _cache[1] || (_cache[1] = $event => (q.value = ''))
                  }, [
                    _createVNode$k(_component_VIcon, {
                      icon: "mdi-close-circle",
                      size: "14"
                    })
                  ]))
                : _createCommentVNode$i("", true)
            ]),
            _createVNode$k(_component_VBtn, {
              icon: "mdi-close",
              size: "small",
              variant: "text",
              "aria-label": "关闭",
              onClick: _cache[2] || (_cache[2] = $event => (open.value = false))
            })
          ]),
          _createElementVNode$l("div", _hoisted_3$g, [
            (!kw.value)
              ? (_openBlock$l(), _createElementBlock$i("button", {
                  key: 0,
                  type: "button",
                  class: "mfhub__primary",
                  onClick: _cache[3] || (_cache[3] = $event => (pick(CREATE_PAGE)))
                }, [
                  _createElementVNode$l("span", _hoisted_4$g, [
                    _createVNode$k(_component_VIcon, {
                      icon: "mdi-plus",
                      size: "20"
                    })
                  ]),
                  _cache[7] || (_cache[7] = _createElementVNode$l("span", { class: "mfhub__text" }, [
                    _createElementVNode$l("strong", null, "新建任务"),
                    _createElementVNode$l("em", null, "选站点、定模式（做种 / 刷流）、开跑")
                  ], -1)),
                  _createVNode$k(_component_VIcon, {
                    icon: "mdi-chevron-right",
                    size: "18",
                    class: "mfhub__primary-chev"
                  })
                ]))
              : _createCommentVNode$i("", true),
            (_openBlock$l(true), _createElementBlock$i(_Fragment$i, null, _renderList$g(filteredGroups.value, (g) => {
              return (_openBlock$l(), _createElementBlock$i("section", {
                key: g.key,
                class: "mfhub__group"
              }, [
                _createElementVNode$l("div", _hoisted_5$g, [
                  _createElementVNode$l("h3", null, _toDisplayString$l(g.title), 1),
                  (g.hint)
                    ? (_openBlock$l(), _createElementBlock$i("span", _hoisted_6$f, _toDisplayString$l(g.hint), 1))
                    : _createCommentVNode$i("", true)
                ]),
                _createElementVNode$l("div", _hoisted_7$e, [
                  (_openBlock$l(true), _createElementBlock$i(_Fragment$i, null, _renderList$g(g.items, (p) => {
                    return (_openBlock$l(), _createElementBlock$i("button", {
                      key: p.key,
                      type: "button",
                      class: "mfhub__card",
                      onClick: $event => (pick(p))
                    }, [
                      _createVNode$k(_component_VIcon, {
                        icon: p.icon,
                        size: "20",
                        class: "mfhub__icon"
                      }, null, 8, ["icon"]),
                      _createElementVNode$l("span", _hoisted_9$b, [
                        _createElementVNode$l("strong", null, _toDisplayString$l(p.label), 1),
                        _createElementVNode$l("em", null, _toDisplayString$l(DESC[p.key] || ''), 1)
                      ]),
                      (badgeFor(p.key))
                        ? (_openBlock$l(), _createBlock$i(_component_VChip, {
                            key: 0,
                            size: "x-small",
                            color: "primary",
                            variant: "tonal",
                            class: "mfhub__badge"
                          }, {
                            default: _withCtx$i(() => [
                              _createTextVNode$k(_toDisplayString$l(badgeFor(p.key)), 1)
                            ]),
                            _: 2
                          }, 1024))
                        : _createCommentVNode$i("", true),
                      _createVNode$k(_component_VIcon, {
                        icon: "mdi-chevron-right",
                        size: "18",
                        class: "mfhub__chev"
                      })
                    ], 8, _hoisted_8$d))
                  }), 128))
                ])
              ]))
            }), 128)),
            (!filteredGroups.value.length)
              ? (_openBlock$l(), _createElementBlock$i("p", _hoisted_10$b, "没有匹配的功能"))
              : _createCommentVNode$i("", true)
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
const FunctionHubDialog = Object.assign(_sfc_main$l, { __scopeId: 'data-v-69d9b8c3' })

export default FunctionHubDialog
