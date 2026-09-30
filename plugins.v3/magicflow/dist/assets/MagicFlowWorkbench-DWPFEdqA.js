import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, c as cloneTask, n as normalizeTask, a as normalizeDownloaderPrefs, b as normalizeDownloaderPaths, d as normalizeDefaults, t as taskStateMeta, r as runModeMeta, e as formatBytes, f as formatBonus, g as formatDateTime, h as runStatusText, F as FALLBACK_SOURCE_OPTIONS, R as RUN_MODES, i as formatDurationSeconds, S as SORT_RULE_TYPES, j as cloudStatusMeta, k as recommendStatusMeta, u as unwrapResponse, l as normalizeSettings, m as normalizeSortRules, o as formatDuration, p as normalizeIyuuSites } from './_plugin-vue_export-helper-Cfymej6T.js';

const {unref:_unref$1,toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,openBlock:_openBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$1,renderList:_renderList$1,Fragment:_Fragment$1,createElementBlock:_createElementBlock$1,createElementVNode:_createElementVNode$1,withModifiers:_withModifiers$1} = await importShared('vue');


const _hoisted_1$1 = { class: "editor-section" };
const _hoisted_2$1 = { class: "editor-section" };
const _hoisted_3$1 = { class: "editor-section__head" };
const _hoisted_4$1 = { class: "editor-switches" };
const _hoisted_5$1 = { class: "editor-section" };
const _hoisted_6$1 = { class: "editor-section__head" };
const _hoisted_7$1 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_8$1 = { class: "editor-section" };
const _hoisted_9$1 = { class: "editor-section__head" };
const _hoisted_10$1 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_11$1 = { class: "editor-section" };
const _hoisted_12$1 = { class: "editor-switches" };
const _hoisted_13$1 = { class: "editor-section" };
const _hoisted_14$1 = { class: "editor-section" };
const _hoisted_15$1 = { class: "editor-section" };
const _hoisted_16$1 = { class: "editor-switches" };
const _hoisted_17$1 = { class: "editor-section" };
const _hoisted_18$1 = { class: "editor-section__head" };
const _hoisted_19$1 = { class: "editor-switches" };
const _hoisted_20$1 = { class: "editor-section" };
const _hoisted_21$1 = { class: "editor-switches" };
const _hoisted_22$1 = { class: "editor-section" };
const _hoisted_23$1 = { class: "editor-switches" };
const _hoisted_24$1 = { class: "editor-section" };
const _hoisted_25$1 = { class: "editor-section__head" };
const _hoisted_26$1 = { class: "editor-section" };
const _hoisted_27$1 = { class: "editor-section__head" };
const _hoisted_28$1 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_29$1 = { class: "editor-section" };
const _hoisted_30$1 = { class: "editor-section__head" };
const _hoisted_31$1 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_32$1 = { class: "editor-switches" };
const _hoisted_33$1 = { class: "editor-section" };
const _hoisted_34$1 = { class: "editor-switches" };
const _hoisted_35$1 = { class: "editor-section" };
const _hoisted_36$1 = { class: "editor-section" };
const _hoisted_37$1 = { class: "magicflow-facts magicflow-facts--two" };
const _hoisted_38$1 = { class: "d-flex align-center mb-2" };
const _hoisted_39$1 = { class: "text-body-2 text-medium-emphasis" };

const {computed: computed$1,ref: ref$1,watch: watch$1} = await importShared('vue');

const {useDisplay} = await importShared('vuetify');


const _sfc_main$1 = {
  __name: 'TaskEditorDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  defaultSavePath: { type: String, default: '' },
  saving: { type: Boolean, default: false },
},
  emits: ['update:modelValue', 'save'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;
const display = useDisplay();
const formRef = ref$1(null);
const activeTab = ref$1('base');
const localTask = ref$1(cloneTask());

// 刷流模式：做种满设定天数即清理换新（保种天数），不套用魔力门槛。
const isBrush = computed$1(() => localTask.value.task_type === 'brush');
const dialogTitle = computed$1(() => {
  const kind = isBrush.value ? '刷流任务' : '魔力任务';
  return localTask.value.id ? `编辑${kind}` : `新建${kind}`
});
// 编辑器标签页随类型切换：刷流隐藏「魔力托管/魔力公式」，改显「刷流运维」。
const editorTabs = computed$1(() =>
  isBrush.value
    ? [
        { value: 'base', icon: 'mdi-calendar-clock', label: '基础与调度' },
        { value: 'brush', icon: 'mdi-upload-network-outline', label: '刷流运维' },
        { value: 'selection', icon: 'mdi-filter-cog-outline', label: '选种规则' },
        { value: 'advanced', icon: 'mdi-tune-variant', label: '高级' },
      ]
    : [
        { value: 'base', icon: 'mdi-calendar-clock', label: '基础与调度' },
        { value: 'magic', icon: 'mdi-star-four-points-outline', label: '魔力托管' },
        { value: 'formula', icon: 'mdi-function-variant', label: '魔力公式' },
        { value: 'selection', icon: 'mdi-filter-cog-outline', label: '选种规则' },
        { value: 'advanced', icon: 'mdi-tune-variant', label: '高级' },
      ],
);
const siteName = computed$1(() => {
  const site = props.sites.find(item => Number(item.value ?? item.id) === Number(localTask.value.site_id));
  return site?.title || site?.name || '未选择'
});
const scheduleText = computed$1(() => localTask.value.cron_expression || `每 ${localTask.value.brush_interval || 5} 分钟`);
// 刷流「上传速率门槛」可选档（KB/s）：低于该平均速率即判「无上传」。
const uploadRateOptions = [
  { title: '温和 · 100 KB/s（≈ 60 MB / 10 分钟）', value: 100 },
  { title: '适中 · 200 KB/s（≈ 120 MB / 10 分钟，推荐）', value: 200 },
  { title: '激进 · 500 KB/s（≈ 300 MB / 10 分钟）', value: 500 },
  { title: '极限 · 1000 KB/s（1 MB/s，只留最热）', value: 1000 },
];
// 保存目录候选：插件设置的默认目录 + 任务当前值（供统一下拉选择，也可手输）。
const savePathOptions = computed$1(() => {
  const set = new Set();
  if (props.defaultSavePath) set.add(props.defaultSavePath);
  if (localTask.value.save_path) set.add(localTask.value.save_path);
  return [...set]
});

// 每次打开弹窗都从服务端任务快照重新创建本地草稿。
watch$1(
  () => props.modelValue,
  visible => {
    if (!visible) return
    localTask.value = cloneTask(props.task);
    activeTab.value = 'base';
  },
);

// 切换任务类型时，若当前标签在新类型下不存在，回到「基础与调度」。
watch$1(
  () => localTask.value.task_type,
  () => {
    if (!editorTabs.value.some(tab => tab.value === activeTab.value)) activeTab.value = 'base';
  },
);

// 关闭编辑器并丢弃尚未保存的草稿。
function closeDialog() {
  emit('update:modelValue', false);
}

// 未填「任务目标」时的提醒弹窗
const goalWarning = ref$1(false);

// 是否已填写有效的任务目标（>0）
function hasGoal() {
  const v = localTask.value.goal_value;
  return !(v === '' || v === null || v === undefined) && Number(v) > 0
}

// 校验必填项后提交标准化任务数据；未填任务目标先弹窗提醒。
async function saveTask() {
  const result = await formRef.value?.validate();
  if (result && !result.valid) return
  if (!hasGoal()) {
    goalWarning.value = true;
    return
  }
  emit('save', normalizeTask(localTask.value));
}

// 确认「仍然保存」（不带目标）
function confirmSaveWithoutGoal() {
  goalWarning.value = false;
  emit('save', normalizeTask(localTask.value));
}

return (_ctx, _cache) => {
  const _component_VToolbarTitle = _resolveComponent$1("VToolbarTitle");
  const _component_VChip = _resolveComponent$1("VChip");
  const _component_VSpacer = _resolveComponent$1("VSpacer");
  const _component_VBtn = _resolveComponent$1("VBtn");
  const _component_VToolbar = _resolveComponent$1("VToolbar");
  const _component_VDivider = _resolveComponent$1("VDivider");
  const _component_VTab = _resolveComponent$1("VTab");
  const _component_VTabs = _resolveComponent$1("VTabs");
  const _component_VSelect = _resolveComponent$1("VSelect");
  const _component_VCol = _resolveComponent$1("VCol");
  const _component_VRow = _resolveComponent$1("VRow");
  const _component_VTextField = _resolveComponent$1("VTextField");
  const _component_VCombobox = _resolveComponent$1("VCombobox");
  const _component_VSwitch = _resolveComponent$1("VSwitch");
  const _component_VWindowItem = _resolveComponent$1("VWindowItem");
  const _component_VAlert = _resolveComponent$1("VAlert");
  const _component_VWindow = _resolveComponent$1("VWindow");
  const _component_VForm = _resolveComponent$1("VForm");
  const _component_VCardText = _resolveComponent$1("VCardText");
  const _component_VCard = _resolveComponent$1("VCard");
  const _component_VIcon = _resolveComponent$1("VIcon");
  const _component_VCardActions = _resolveComponent$1("VCardActions");
  const _component_VDialog = _resolveComponent$1("VDialog");

  return (_openBlock$1(), _createBlock$1(_component_VDialog, {
    "model-value": __props.modelValue,
    scrollable: "",
    fullscreen: _unref$1(display).smAndDown.value,
    "max-width": "74rem",
    "onUpdate:modelValue": _cache[103] || (_cache[103] = value => emit('update:modelValue', value))
  }, {
    default: _withCtx$1(() => [
      _createVNode$1(_component_VCard, { class: "magicflow-editor" }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_VToolbar, {
            color: "transparent",
            density: "comfortable",
            class: "magicflow-editor__toolbar"
          }, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_VToolbarTitle, null, {
                default: _withCtx$1(() => [
                  _createTextVNode$1(_toDisplayString$1(dialogTitle.value), 1)
                ]),
                _: 1
              }),
              (localTask.value.id)
                ? (_openBlock$1(), _createBlock$1(_component_VChip, {
                    key: 0,
                    size: "small",
                    variant: "tonal",
                    class: "mr-2"
                  }, {
                    default: _withCtx$1(() => [
                      _createTextVNode$1(_toDisplayString$1(siteName.value), 1)
                    ]),
                    _: 1
                  }))
                : _createCommentVNode$1("", true),
              _createVNode$1(_component_VSpacer),
              _createVNode$1(_component_VBtn, {
                color: "primary",
                variant: "flat",
                "prepend-icon": "mdi-content-save",
                loading: __props.saving,
                onClick: saveTask
              }, {
                default: _withCtx$1(() => [...(_cache[104] || (_cache[104] = [
                  _createTextVNode$1(" 保存任务 ", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              _createVNode$1(_component_VBtn, {
                icon: "mdi-close",
                variant: "text",
                "aria-label": "关闭",
                onClick: closeDialog
              })
            ]),
            _: 1
          }),
          _createVNode$1(_component_VDivider),
          _createVNode$1(_component_VCardText, { class: "magicflow-editor__body" }, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_VForm, {
                ref_key: "formRef",
                ref: formRef,
                class: "magicflow-editor__form",
                onSubmit: _withModifiers$1(saveTask, ["prevent"])
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_VTabs, {
                    modelValue: activeTab.value,
                    "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((activeTab).value = $event)),
                    direction: _unref$1(display).mdAndUp.value ? 'vertical' : 'horizontal',
                    color: "primary",
                    class: "magicflow-editor__tabs"
                  }, {
                    default: _withCtx$1(() => [
                      (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(editorTabs.value, (tab) => {
                        return (_openBlock$1(), _createBlock$1(_component_VTab, {
                          key: tab.value,
                          value: tab.value,
                          "prepend-icon": tab.icon
                        }, {
                          default: _withCtx$1(() => [
                            _createTextVNode$1(_toDisplayString$1(tab.label), 1)
                          ]),
                          _: 2
                        }, 1032, ["value", "prepend-icon"]))
                      }), 128))
                    ]),
                    _: 1
                  }, 8, ["modelValue", "direction"]),
                  _createVNode$1(_component_VDivider, {
                    vertical: _unref$1(display).mdAndUp.value
                  }, null, 8, ["vertical"]),
                  _createVNode$1(_component_VWindow, {
                    modelValue: activeTab.value,
                    "onUpdate:modelValue": _cache[100] || (_cache[100] = $event => ((activeTab).value = $event)),
                    touch: false,
                    class: "magicflow-editor__window"
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_VWindowItem, { value: "base" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_1$1, [
                            _cache[105] || (_cache[105] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "任务类型"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "决定选种排序与清理策略，建议新建时就选定")
                              ])
                            ], -1)),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VSelect, {
                                      modelValue: localTask.value.task_type,
                                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((localTask.value.task_type) = $event)),
                                      label: "类型",
                                      items: [
                        { title: '刷魔力（魔力/小时最大化）', value: 'bonus' },
                        { title: '刷流（按上传潜力选种，做种满天数轮换）', value: 'brush' },
                      ],
                                      hint: "刷流模式在「刷流运维」标签配置，魔力门槛/公式自动隐藏",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _createElementVNode$1("section", _hoisted_2$1, [
                            _createElementVNode$1("header", _hoisted_3$1, [
                              _cache[107] || (_cache[107] = _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "任务身份"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "每个任务绑定一个站点和下载器")
                              ], -1)),
                              _createVNode$1(_component_VChip, {
                                size: "small",
                                color: "primary",
                                variant: "tonal"
                              }, {
                                default: _withCtx$1(() => [...(_cache[106] || (_cache[106] = [
                                  _createTextVNode$1("必填", -1)
                                ]))]),
                                _: 1
                              })
                            ]),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.name,
                                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((localTask.value.name) = $event)),
                                      label: "任务名称",
                                      rules: [value => !!String(value || '').trim() || '请输入任务名称']
                                    }, null, 8, ["modelValue", "rules"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VSelect, {
                                      modelValue: localTask.value.site_id,
                                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((localTask.value.site_id) = $event)),
                                      items: __props.sites,
                                      "item-title": "name",
                                      "item-value": "id",
                                      label: "站点",
                                      rules: [value => !!value || '请选择站点']
                                    }, null, 8, ["modelValue", "items", "rules"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VSelect, {
                                      modelValue: localTask.value.downloader,
                                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((localTask.value.downloader) = $event)),
                                      items: __props.downloaders,
                                      label: "下载器",
                                      rules: [value => !!value || '请选择下载器']
                                    }, null, 8, ["modelValue", "items", "rules"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.brush_tag,
                                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((localTask.value.brush_tag) = $event)),
                                      label: "下载器标签",
                                      placeholder: "留空自动使用「魔流-任务名」"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, { cols: "12" }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCombobox, {
                                      modelValue: localTask.value.save_path,
                                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((localTask.value.save_path) = $event)),
                                      items: savePathOptions.value,
                                      label: "保存目录",
                                      placeholder: "留空使用下载器默认目录",
                                      hint: "默认目录可在插件设置「下载目录」中配置",
                                      "persistent-hint": "",
                                      clearable: "",
                                      variant: "outlined"
                                    }, null, 8, ["modelValue", "items"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createElementVNode$1("div", _hoisted_4$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.enabled,
                                "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((localTask.value.enabled) = $event)),
                                label: "启用任务",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.rss_support,
                                "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((localTask.value.rss_support) = $event)),
                                label: "使用 RSS",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"])
                            ])
                          ]),
                          _createElementVNode$1("section", _hoisted_5$1, [
                            _createElementVNode$1("header", _hoisted_6$1, [
                              _cache[108] || (_cache[108] = _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "刷新计划"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "选种刷新和做种检查分别调度")
                              ], -1)),
                              _createElementVNode$1("span", _hoisted_7$1, _toDisplayString$1(scheduleText.value), 1)
                            ]),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.brush_interval,
                                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((localTask.value.brush_interval) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      max: "1440",
                                      label: "选种刷新周期（分钟）"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.check_interval,
                                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((localTask.value.check_interval) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      max: "1440",
                                      label: "做种检查周期（分钟）"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.cron_expression,
                                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((localTask.value.cron_expression) = $event)),
                                      label: "CRON 表达式",
                                      placeholder: "留空使用固定刷新周期"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.active_time_range,
                                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((localTask.value.active_time_range) = $event)),
                                      label: "开启时间段",
                                      placeholder: "如 00:00-08:00"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _createElementVNode$1("section", _hoisted_8$1, [
                            _createElementVNode$1("header", _hoisted_9$1, [
                              _createElementVNode$1("div", null, [
                                _cache[109] || (_cache[109] = _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "任务目标", -1)),
                                _createElementVNode$1("div", _hoisted_10$1, _toDisplayString$1(isBrush.value ? '站点上传量达到目标后，任务自动停止' : '站点魔力值达到目标后，任务自动停止'), 1)
                              ]),
                              _createVNode$1(_component_VChip, {
                                size: "small",
                                color: "primary",
                                variant: "tonal"
                              }, {
                                default: _withCtx$1(() => [...(_cache[110] || (_cache[110] = [
                                  _createTextVNode$1("建议填写", -1)
                                ]))]),
                                _: 1
                              })
                            ]),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, { cols: "12" }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.goal_value,
                                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((localTask.value.goal_value) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      step: "any",
                                      label: isBrush.value ? '目标上传量（GB）' : '目标魔力值',
                                      clearable: ""
                                    }, null, 8, ["modelValue", "label"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ])
                        ]),
                        _: 1
                      }),
                      _createVNode$1(_component_VWindowItem, { value: "brush" }, {
                        default: _withCtx$1(() => [
                          _createVNode$1(_component_VAlert, {
                            type: "info",
                            variant: "tonal",
                            density: "compact",
                            class: "mb-2",
                            icon: "mdi-upload-network-outline"
                          }, {
                            default: _withCtx$1(() => [...(_cache[111] || (_cache[111] = [
                              _createTextVNode$1(" 刷流模式：", -1),
                              _createElementVNode$1("strong", null, "按「上传潜力」运行，有自己的选种标准", -1),
                              _createTextVNode$1(" —— 只挑", -1),
                              _createElementVNode$1("strong", null, "免费（含 2X免费）且有下载者", -1),
                              _createTextVNode$1("的种， 不设做种人数上限、体积/年龄不限（热门大种才是上传主力）；定期检查每个种子， ", -1),
                              _createElementVNode$1("strong", null, "做种满设定天数即清理换新的", -1),
                              _createTextVNode$1("（默认 2 天）；没下完也算（只要在上传）。 ", -1)
                            ]))]),
                            _: 1
                          }),
                          _createElementVNode$1("section", _hoisted_11$1, [
                            _cache[112] || (_cache[112] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "刷流轮换"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "做种满设定天数即清理换新（默认 2 天）")
                              ])
                            ], -1)),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.brush_seed_days,
                                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((localTask.value.brush_seed_days) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      max: "365",
                                      label: "保种天数",
                                      hint: "做种满该天数后清理换新；0 = 不按天数，改回「无上传」判定",
                                      suffix: "天",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.brush_min_leechers,
                                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((localTask.value.brush_min_leechers) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      label: "最小下载人数",
                                      hint: "只挑下载人数≥该值的种（有下载需求才值得下）",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.rotate_upload_gb,
                                      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((localTask.value.rotate_upload_gb) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      label: "产出换新：单种上传量",
                                      hint: "单种已上传达到该 GB 即清理换新；留空 = 不看上传量",
                                      suffix: "GB",
                                      clearable: "",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.rotate_ratio,
                                      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((localTask.value.rotate_ratio) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      step: "0.1",
                                      label: "产出换新：单种分享率",
                                      hint: "单种分享率达到该值即清理换新；留空 = 不看分享率",
                                      clearable: "",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createElementVNode$1("div", _hoisted_12$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.except_subscribe,
                                "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((localTask.value.except_subscribe) = $event)),
                                label: "选种排除订阅命中（不抢主人要看的片）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"])
                            ])
                          ]),
                          _createElementVNode$1("section", _hoisted_13$1, [
                            _cache[113] || (_cache[113] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "无上传判定（保种天数 = 0 时启用）"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "保种天数填 0 时不按天数轮换，而是以「平均上传速率」为准清理换新")
                              ])
                            ], -1)),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VSelect, {
                                      modelValue: localTask.value.upload_min_kbps,
                                      "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((localTask.value.upload_min_kbps) = $event)),
                                      modelModifiers: { number: true },
                                      label: "上传速率门槛",
                                      items: uploadRateOptions,
                                      hint: "窗口内平均上传速率低于该值 → 判「无上传」（连续若干次后删除）",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.upload_idle_minutes,
                                      "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((localTask.value.upload_idle_minutes) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      max: "1440",
                                      label: "清理时间（无上传判定时长）",
                                      hint: "连续多少分钟低于速率门槛就清理（0 = 自动：约 2×检查间隔）",
                                      suffix: "分钟",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.brush_grace_minutes,
                                      "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((localTask.value.brush_grace_minutes) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      max: "1440",
                                      label: "宽容时间（起步宽限）",
                                      hint: "新种加入后多少分钟内不判「无上传」",
                                      suffix: "分钟",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _createElementVNode$1("section", _hoisted_14$1, [
                            _cache[114] || (_cache[114] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "抓取与并发"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "刷流只看最新页（免费热种在最新页），不深翻")
                              ])
                            ], -1)),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.max_add_per_run,
                                      "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((localTask.value.max_add_per_run) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "单轮最多新增",
                                      placeholder: "默认 10",
                                      suffix: "个/轮",
                                      clearable: ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.max_download_concurrent,
                                      "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((localTask.value.max_download_concurrent) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "同时下载上限",
                                      placeholder: "默认 10",
                                      suffix: "个",
                                      clearable: ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.top_n,
                                      "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((localTask.value.top_n) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "每轮参评候选数",
                                      placeholder: "默认 30",
                                      suffix: "个",
                                      clearable: ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.browse_pages,
                                      "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((localTask.value.browse_pages) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      max: "60",
                                      label: "每轮翻页数",
                                      placeholder: "默认 3",
                                      suffix: "页",
                                      clearable: ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _createElementVNode$1("section", _hoisted_15$1, [
                            _cache[115] || (_cache[115] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "复用与清理"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "优先复用本机已有资源；做种满天数 / 促销失效的种子清理")
                              ])
                            ], -1)),
                            _createElementVNode$1("div", _hoisted_16$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.refill_when_empty,
                                "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((localTask.value.refill_when_empty) = $event)),
                                label: "清理后主动补种",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.reuse_existing,
                                "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((localTask.value.reuse_existing) = $event)),
                                label: "复用本机已有资源（辅种）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.reuse_verify,
                                "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((localTask.value.reuse_verify) = $event)),
                                disabled: !localTask.value.reuse_existing,
                                label: "辅种前先校验（不匹配自动撤销）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue", "disabled"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.auto_swap,
                                "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((localTask.value.auto_swap) = $event)),
                                label: "自动换种（名额/磁盘/站点接近上限时，按边际魔力把低价值种下线、换入更优种）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.swap_allow_download,
                                "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((localTask.value.swap_allow_download) = $event)),
                                disabled: !localTask.value.auto_swap,
                                label: "换种允许「取种换入」（默认关；开启后只走免费渠道：本站免费，或去兄弟站免费取同一 Release 的副本；两条都不通就跳过，绝不付费下载）",
                                color: "warning",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue", "disabled"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.cleanup_no_progress,
                                "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((localTask.value.cleanup_no_progress) = $event)),
                                label: "清理无进度种子（停滞/出错且进度为 0）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.cleanup_slow_progress,
                                "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((localTask.value.cleanup_slow_progress) = $event)),
                                label: "清理下载过慢的种子（长期下不完腾名额）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.purge_unfree_incomplete,
                                "onUpdate:modelValue": _cache[33] || (_cache[33] = $event => ((localTask.value.purge_unfree_incomplete) = $event)),
                                label: "清理「已不再免费且未下完」的种子",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.auto_resume_paused,
                                "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((localTask.value.auto_resume_paused) = $event)),
                                label: "自动恢复被暂停的已完成种子",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.delete_files,
                                "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((localTask.value.delete_files) = $event)),
                                label: "删种同时删除文件",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"])
                            ]),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, { cols: "12" }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.delete_except_tags,
                                      "onUpdate:modelValue": _cache[36] || (_cache[36] = $event => ((localTask.value.delete_except_tags) = $event)),
                                      label: "永不删除的标签（可选，逗号分隔）",
                                      hint: "叠加在「已整理 / 辅种」之上：带这些标签的种子删种时永不删除",
                                      "persistent-hint": "",
                                      clearable: ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.swap_max_in_gb,
                                      "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((localTask.value.swap_max_in_gb) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "0",
                                      label: "换入体积上限（GB，0 = 不限）",
                                      hint: "换入候选不超过该体积；防止为几个魔力换来巨物（炸磁盘/流量）",
                                      "persistent-hint": "",
                                      clearable: ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.swap_min_gain_pct,
                                      "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((localTask.value.swap_min_gain_pct) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "5",
                                      max: "500",
                                      label: "换种净收益门槛（%）",
                                      hint: "净增魔力 ≥ 被换出种边际的该比例（库内/自有种按 2 倍）",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.swap_daily_dl_gb,
                                      "onUpdate:modelValue": _cache[39] || (_cache[39] = $event => ((localTask.value.swap_daily_dl_gb) = $event)),
                                      modelModifiers: { number: true },
                                      disabled: !localTask.value.swap_allow_download,
                                      type: "number",
                                      min: "0",
                                      label: "每日换种下载上限（GB，0 = 不限）",
                                      hint: "按「实际下载量」计（本站免费 + 跨站免费都算）；关闭「取种换入」时此项无效",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue", "disabled"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.swap_min_gain_per_gb,
                                      "onUpdate:modelValue": _cache[40] || (_cache[40] = $event => ((localTask.value.swap_min_gain_per_gb) = $event)),
                                      modelModifiers: { number: true },
                                      disabled: !localTask.value.swap_allow_download,
                                      type: "number",
                                      min: "0",
                                      step: "0.01",
                                      label: "每 GB 下载的魔力门槛（/h）",
                                      hint: "净增魔力 ≥ 下载GB × 该值；过滤「几十 GB 换零点几/h」的赔本买卖",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue", "disabled"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.swap_min_in_seeders,
                                      "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((localTask.value.swap_min_in_seeders) = $event)),
                                      modelModifiers: { number: true },
                                      disabled: !localTask.value.swap_allow_download,
                                      type: "number",
                                      min: "1",
                                      label: "换入候选最少做种人数",
                                      hint: "老种候选中位魔力高但常常没源；人数不够就不拉（零下载辅种 / 跨站取种不受此限）",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue", "disabled"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            (localTask.value.cleanup_no_progress)
                              ? (_openBlock$1(), _createBlock$1(_component_VRow, { key: 0 }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.no_progress_minutes,
                                          "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((localTask.value.no_progress_minutes) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "无进度判定时长（分钟）",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.seen_cooldown_hours,
                                          "onUpdate:modelValue": _cache[43] || (_cache[43] = $event => ((localTask.value.seen_cooldown_hours) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          label: "已处理去重窗口（小时）",
                                          hint: "同一候选在该时长内不重复拉取，0 = 不跳过",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }))
                              : _createCommentVNode$1("", true),
                            (localTask.value.cleanup_slow_progress)
                              ? (_openBlock$1(), _createBlock$1(_component_VRow, { key: 1 }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.slow_progress_grace_minutes,
                                          "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((localTask.value.slow_progress_grace_minutes) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "慢种宽限（分钟）",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.slow_progress_max_hours,
                                          "onUpdate:modelValue": _cache[45] || (_cache[45] = $event => ((localTask.value.slow_progress_max_hours) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "预计下完上限（小时）",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }))
                              : _createCommentVNode$1("", true)
                          ])
                        ]),
                        _: 1
                      }),
                      (!isBrush.value)
                        ? (_openBlock$1(), _createBlock$1(_component_VWindowItem, {
                            key: 0,
                            value: "magic"
                          }, {
                            default: _withCtx$1(() => [
                              _createElementVNode$1("section", _hoisted_17$1, [
                                _createElementVNode$1("header", _hoisted_18$1, [
                                  _cache[117] || (_cache[117] = _createElementVNode$1("div", null, [
                                    _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "魔力门槛（留空 = 自动）"),
                                    _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "留空由公式与实时数据自动推算，手填即覆盖")
                                  ], -1)),
                                  _createVNode$1(_component_VChip, {
                                    size: "small",
                                    color: "primary",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx$1(() => [...(_cache[116] || (_cache[116] = [
                                      _createTextVNode$1("可自动", -1)
                                    ]))]),
                                    _: 1
                                  })
                                ]),
                                _createVNode$1(_component_VRow, null, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.min_bonus_per_hour,
                                          "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((localTask.value.min_bonus_per_hour) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "0.01",
                                          label: "每小时最低魔力",
                                          placeholder: "留空 = 种子魔力中位数 × 0.5",
                                          suffix: "/h",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.disk_size_gb,
                                          "onUpdate:modelValue": _cache[47] || (_cache[47] = $event => ((localTask.value.disk_size_gb) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "10",
                                          label: "保种体积上限",
                                          placeholder: "留空 = 不限",
                                          suffix: "GB",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.max_keep_torrents,
                                          "onUpdate:modelValue": _cache[48] || (_cache[48] = $event => ((localTask.value.max_keep_torrents) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "最多保留种子数（覆盖站点上限）",
                                          placeholder: "留空 = 按站点上限 → 保种体积 ÷ 平均种子大小",
                                          hint: "站点上限来自「设置 · 站点规则」；此处只覆盖当前任务",
                                          "persistent-hint": "",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.max_add_per_run,
                                          "onUpdate:modelValue": _cache[49] || (_cache[49] = $event => ((localTask.value.max_add_per_run) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "单轮最多新增",
                                          placeholder: "默认 10",
                                          suffix: "个/轮",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.max_download_concurrent,
                                          "onUpdate:modelValue": _cache[50] || (_cache[50] = $event => ((localTask.value.max_download_concurrent) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "同时下载上限",
                                          placeholder: "默认 10",
                                          suffix: "个",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.top_n,
                                          "onUpdate:modelValue": _cache[51] || (_cache[51] = $event => ((localTask.value.top_n) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "每轮参评候选数",
                                          placeholder: "默认 30",
                                          suffix: "个",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.browse_pages,
                                          "onUpdate:modelValue": _cache[52] || (_cache[52] = $event => ((localTask.value.browse_pages) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          max: "60",
                                          label: "每轮翻页数",
                                          placeholder: "默认 3",
                                          suffix: "页",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.bonus_protect_threshold,
                                          "onUpdate:modelValue": _cache[53] || (_cache[53] = $event => ((localTask.value.bonus_protect_threshold) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          label: "魔力保护阈值",
                                          placeholder: "留空 = 站点当前魔力",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.min_bonus_to_keep,
                                          "onUpdate:modelValue": _cache[54] || (_cache[54] = $event => ((localTask.value.min_bonus_to_keep) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          label: "最低魔力保底值",
                                          placeholder: "留空 = 0（不设保底）",
                                          clearable: "",
                                          rules: [
                        value =>
                          Number(value || 0) < Number(localTask.value.bonus_protect_threshold || 999999999) ||
                          '最低魔力保底值应小于魔力保护阈值',
                      ]
                                        }, null, 8, ["modelValue", "rules"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }),
                                _createElementVNode$1("div", _hoisted_19$1, [
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.refill_when_empty,
                                    "onUpdate:modelValue": _cache[55] || (_cache[55] = $event => ((localTask.value.refill_when_empty) = $event)),
                                    label: "清理后主动补种",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.reuse_existing,
                                    "onUpdate:modelValue": _cache[56] || (_cache[56] = $event => ((localTask.value.reuse_existing) = $event)),
                                    label: "复用本机已有资源（辅种）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.reuse_verify,
                                    "onUpdate:modelValue": _cache[57] || (_cache[57] = $event => ((localTask.value.reuse_verify) = $event)),
                                    disabled: !localTask.value.reuse_existing,
                                    label: "辅种前先校验（不匹配自动撤销）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue", "disabled"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.auto_swap,
                                    "onUpdate:modelValue": _cache[58] || (_cache[58] = $event => ((localTask.value.auto_swap) = $event)),
                                    label: "自动换种（名额/磁盘/站点接近上限时，按边际魔力把低价值种下线、换入更优种）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.swap_allow_download,
                                    "onUpdate:modelValue": _cache[59] || (_cache[59] = $event => ((localTask.value.swap_allow_download) = $event)),
                                    disabled: !localTask.value.auto_swap,
                                    label: "换种允许「取种换入」（默认关；开启后只走免费渠道：本站免费，或去兄弟站免费取同一 Release 的副本；两条都不通就跳过，绝不付费下载）",
                                    color: "warning",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue", "disabled"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.cleanup_no_progress,
                                    "onUpdate:modelValue": _cache[60] || (_cache[60] = $event => ((localTask.value.cleanup_no_progress) = $event)),
                                    label: "每次运行清理无进度种子（停滞/出错且进度为 0）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.cleanup_slow_progress,
                                    "onUpdate:modelValue": _cache[61] || (_cache[61] = $event => ((localTask.value.cleanup_slow_progress) = $event)),
                                    label: "清理下载过慢的种子（速度÷体积算 ETA，长期下不完的腾名额）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.purge_unfree_incomplete,
                                    "onUpdate:modelValue": _cache[62] || (_cache[62] = $event => ((localTask.value.purge_unfree_incomplete) = $event)),
                                    label: "检查时清理「已不再免费且未下完」的种子（回站点核对促销）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.auto_resume_paused,
                                    "onUpdate:modelValue": _cache[63] || (_cache[63] = $event => ((localTask.value.auto_resume_paused) = $event)),
                                    label: "自动恢复被暂停的已完成种子（重新做种）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"])
                                ]),
                                _createVNode$1(_component_VRow, null, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VSelect, {
                                          modelValue: localTask.value.ti_source,
                                          "onUpdate:modelValue": _cache[64] || (_cache[64] = $event => ((localTask.value.ti_source) = $event)),
                                          items: [
                        { title: '发布时长（站点公式口径，推荐）', value: 'publish' },
                        { title: '做种时长（qB 统计）', value: 'seed_time' },
                      ],
                                          label: "Ti 口径（做种时间因子）",
                                          hint: "候选排序与做种汇总使用同一口径；取不到发布时间时自动回落做种时长",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }),
                                (localTask.value.cleanup_no_progress)
                                  ? (_openBlock$1(), _createBlock$1(_component_VRow, { key: 0 }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VCol, {
                                          cols: "12",
                                          md: "6"
                                        }, {
                                          default: _withCtx$1(() => [
                                            _createVNode$1(_component_VTextField, {
                                              modelValue: localTask.value.no_progress_minutes,
                                              "onUpdate:modelValue": _cache[65] || (_cache[65] = $event => ((localTask.value.no_progress_minutes) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "1",
                                              label: "无进度判定时长（分钟）",
                                              hint: "加入下载器超过该时长仍无进度才清理",
                                              "persistent-hint": ""
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _: 1
                                        }),
                                        _createVNode$1(_component_VCol, {
                                          cols: "12",
                                          md: "6"
                                        }, {
                                          default: _withCtx$1(() => [
                                            _createVNode$1(_component_VTextField, {
                                              modelValue: localTask.value.seen_cooldown_hours,
                                              "onUpdate:modelValue": _cache[66] || (_cache[66] = $event => ((localTask.value.seen_cooldown_hours) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              label: "已处理去重窗口（小时）",
                                              hint: "同一候选在该时长内不重复拉取，0 = 不跳过",
                                              "persistent-hint": ""
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _: 1
                                        })
                                      ]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$1("", true),
                                (localTask.value.cleanup_slow_progress)
                                  ? (_openBlock$1(), _createBlock$1(_component_VRow, { key: 1 }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VCol, {
                                          cols: "12",
                                          md: "6"
                                        }, {
                                          default: _withCtx$1(() => [
                                            _createVNode$1(_component_VTextField, {
                                              modelValue: localTask.value.slow_progress_grace_minutes,
                                              "onUpdate:modelValue": _cache[67] || (_cache[67] = $event => ((localTask.value.slow_progress_grace_minutes) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "1",
                                              label: "慢种宽限（分钟）",
                                              hint: "种子加入后该时长内不判「慢」，给新种起步时间",
                                              "persistent-hint": ""
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _: 1
                                        }),
                                        _createVNode$1(_component_VCol, {
                                          cols: "12",
                                          md: "6"
                                        }, {
                                          default: _withCtx$1(() => [
                                            _createVNode$1(_component_VTextField, {
                                              modelValue: localTask.value.slow_progress_max_hours,
                                              "onUpdate:modelValue": _cache[68] || (_cache[68] = $event => ((localTask.value.slow_progress_max_hours) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "1",
                                              label: "预计下完上限（小时）",
                                              hint: "按当前速度（速度÷体积）预计还要超过该小时数才下完 → 清理",
                                              "persistent-hint": ""
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _: 1
                                        })
                                      ]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$1("", true)
                              ]),
                              _createElementVNode$1("section", _hoisted_20$1, [
                                _cache[118] || (_cache[118] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                                  _createElementVNode$1("div", null, [
                                    _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "删种保护"),
                                    _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "保护期内、受保护与 H&R 种子永不删除")
                                  ])
                                ], -1)),
                                _createVNode$1(_component_VRow, null, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.min_seed_time,
                                          "onUpdate:modelValue": _cache[69] || (_cache[69] = $event => ((localTask.value.min_seed_time) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          label: "最短做种时间（小时）",
                                          placeholder: "0 = 不设保护期"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.min_ratio,
                                          "onUpdate:modelValue": _cache[70] || (_cache[70] = $event => ((localTask.value.min_ratio) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "0.01",
                                          label: "最低分享率",
                                          placeholder: "0 = 不限"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }),
                                _createElementVNode$1("div", _hoisted_21$1, [
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.delete_files,
                                    "onUpdate:modelValue": _cache[71] || (_cache[71] = $event => ((localTask.value.delete_files) = $event)),
                                    label: "删种同时删除文件",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"])
                                ]),
                                _createVNode$1(_component_VRow, null, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, { cols: "12" }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.delete_except_tags,
                                          "onUpdate:modelValue": _cache[72] || (_cache[72] = $event => ((localTask.value.delete_except_tags) = $event)),
                                          label: "永不删除的标签（可选，逗号分隔）",
                                          hint: "叠加在「已整理 / 辅种」之上：带这些标签的种子删种时永不删除",
                                          "persistent-hint": "",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VRow, null, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.swap_max_in_gb,
                                          "onUpdate:modelValue": _cache[73] || (_cache[73] = $event => ((localTask.value.swap_max_in_gb) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          label: "换入体积上限（GB，0 = 不限）",
                                          hint: "换入候选不超过该体积；防止为几个魔力换来巨物（炸磁盘/流量）",
                                          "persistent-hint": "",
                                          clearable: ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.swap_min_gain_pct,
                                          "onUpdate:modelValue": _cache[74] || (_cache[74] = $event => ((localTask.value.swap_min_gain_pct) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "5",
                                          max: "500",
                                          label: "换种净收益门槛（%）",
                                          hint: "净增魔力 ≥ 被换出种边际的该比例（库内/自有种按 2 倍）",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VRow, null, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.swap_daily_dl_gb,
                                          "onUpdate:modelValue": _cache[75] || (_cache[75] = $event => ((localTask.value.swap_daily_dl_gb) = $event)),
                                          modelModifiers: { number: true },
                                          disabled: !localTask.value.swap_allow_download,
                                          type: "number",
                                          min: "0",
                                          label: "每日换种下载上限（GB，0 = 不限）",
                                          hint: "按「实际下载量」计（本站免费 + 跨站免费都算）；关闭「取种换入」时此项无效",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue", "disabled"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.swap_min_gain_per_gb,
                                          "onUpdate:modelValue": _cache[76] || (_cache[76] = $event => ((localTask.value.swap_min_gain_per_gb) = $event)),
                                          modelModifiers: { number: true },
                                          disabled: !localTask.value.swap_allow_download,
                                          type: "number",
                                          min: "0",
                                          step: "0.01",
                                          label: "每 GB 下载的魔力门槛（/h）",
                                          hint: "净增魔力 ≥ 下载GB × 该值；过滤「几十 GB 换零点几/h」的赔本买卖",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue", "disabled"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VRow, null, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.swap_min_in_seeders,
                                          "onUpdate:modelValue": _cache[77] || (_cache[77] = $event => ((localTask.value.swap_min_in_seeders) = $event)),
                                          modelModifiers: { number: true },
                                          disabled: !localTask.value.swap_allow_download,
                                          type: "number",
                                          min: "1",
                                          label: "换入候选最少做种人数",
                                          hint: "老种候选中位魔力高但常常没源；人数不够就不拉（零下载辅种 / 跨站取种不受此限）",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue", "disabled"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                })
                              ]),
                              _createElementVNode$1("section", _hoisted_22$1, [
                                _cache[119] || (_cache[119] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                                  _createElementVNode$1("div", null, [
                                    _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "完美种保护"),
                                    _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "优质老种（非零魔 · 做种人数少 · 挂得够老）永久保留，不参与任何清理——魔力靠「养」，越老越肥")
                                  ])
                                ], -1)),
                                _createElementVNode$1("div", _hoisted_23$1, [
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.protect_perfect,
                                    "onUpdate:modelValue": _cache[78] || (_cache[78] = $event => ((localTask.value.protect_perfect) = $event)),
                                    label: "启用完美种保护（满足条件的种子永不清理）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"])
                                ]),
                                (localTask.value.protect_perfect)
                                  ? (_openBlock$1(), _createBlock$1(_component_VRow, { key: 0 }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VCol, {
                                          cols: "12",
                                          md: "6"
                                        }, {
                                          default: _withCtx$1(() => [
                                            _createVNode$1(_component_VTextField, {
                                              modelValue: localTask.value.perfect_max_seeders,
                                              "onUpdate:modelValue": _cache[79] || (_cache[79] = $event => ((localTask.value.perfect_max_seeders) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              label: "完美种：做种人数上限",
                                              hint: "站内做种人数 ≤ 该值才算完美（0 = 不限制）",
                                              suffix: "人",
                                              "persistent-hint": ""
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _: 1
                                        }),
                                        _createVNode$1(_component_VCol, {
                                          cols: "12",
                                          md: "6"
                                        }, {
                                          default: _withCtx$1(() => [
                                            _createVNode$1(_component_VTextField, {
                                              modelValue: localTask.value.perfect_min_weeks,
                                              "onUpdate:modelValue": _cache[80] || (_cache[80] = $event => ((localTask.value.perfect_min_weeks) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              step: "0.5",
                                              label: "完美种：做种周数下限",
                                              hint: "做种周数 ≥ 该值才算完美（0 = 不限制）",
                                              suffix: "周",
                                              "persistent-hint": ""
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _: 1
                                        })
                                      ]),
                                      _: 1
                                    }))
                                  : _createCommentVNode$1("", true)
                              ])
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode$1("", true),
                      (!isBrush.value)
                        ? (_openBlock$1(), _createBlock$1(_component_VWindowItem, {
                            key: 1,
                            value: "formula"
                          }, {
                            default: _withCtx$1(() => [
                              _createElementVNode$1("section", _hoisted_24$1, [
                                _createElementVNode$1("header", _hoisted_25$1, [
                                  _cache[121] || (_cache[121] = _createElementVNode$1("div", null, [
                                    _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "魔力公式参数"),
                                    _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, " 留空使用站点预设 / NexusPHP 标准式（T0=5，N0=7，B0=100，L=300） ")
                                  ], -1)),
                                  _createVNode$1(_component_VChip, {
                                    size: "small",
                                    color: "primary",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx$1(() => [...(_cache[120] || (_cache[120] = [
                                      _createTextVNode$1("高级", -1)
                                    ]))]),
                                    _: 1
                                  })
                                ]),
                                _createVNode$1(_component_VRow, null, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.bonus_t0,
                                          "onUpdate:modelValue": _cache[81] || (_cache[81] = $event => ((localTask.value.bonus_t0) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0.1",
                                          step: "0.1",
                                          label: "生存时间参数 T0",
                                          placeholder: "默认 5"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.bonus_n0,
                                          "onUpdate:modelValue": _cache[82] || (_cache[82] = $event => ((localTask.value.bonus_n0) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "2",
                                          label: "做种人数参数 N0",
                                          placeholder: "默认 7"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.bonus_b0,
                                          "onUpdate:modelValue": _cache[83] || (_cache[83] = $event => ((localTask.value.bonus_b0) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0.1",
                                          step: "0.1",
                                          label: "每小时魔力上限 B0",
                                          placeholder: "默认 100"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.bonus_l,
                                          "onUpdate:modelValue": _cache[84] || (_cache[84] = $event => ((localTask.value.bonus_l) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0.1",
                                          step: "0.1",
                                          label: "曲线参数 L",
                                          placeholder: "默认 300"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      md: "6"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.bonus_zero_weight,
                                          "onUpdate:modelValue": _cache[85] || (_cache[85] = $event => ((localTask.value.bonus_zero_weight) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "0.05",
                                          label: "零魔种子权重",
                                          placeholder: "默认 0.2"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                })
                              ])
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode$1("", true),
                      _createVNode$1(_component_VWindowItem, { value: "selection" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_26$1, [
                            _createElementVNode$1("header", _hoisted_27$1, [
                              _createElementVNode$1("div", null, [
                                _cache[122] || (_cache[122] = _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "来源与促销", -1)),
                                _createElementVNode$1("div", _hoisted_28$1, _toDisplayString$1(isBrush.value ? '刷流只看站点最新页（免费热种在最新页），不做游标深翻' : '沿用站点列表页或 RSS 获取链路'), 1)
                              ])
                            ]),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    (isBrush.value)
                                      ? (_openBlock$1(), _createBlock$1(_component_VSelect, {
                                          key: 0,
                                          "model-value": 'free',
                                          label: "促销",
                                          items: [{ title: '免费（含 2X 免费）', value: 'free' }],
                                          disabled: "",
                                          hint: "刷流固定只抓免费种（下载不计量），保障分享率",
                                          "persistent-hint": ""
                                        }))
                                      : (_openBlock$1(), _createBlock$1(_component_VSelect, {
                                          key: 1,
                                          modelValue: localTask.value.freeleech,
                                          "onUpdate:modelValue": _cache[86] || (_cache[86] = $event => ((localTask.value.freeleech) = $event)),
                                          label: "促销",
                                          items: [
                        { title: '全部（包括普通）', value: '' },
                        { title: '免费', value: 'free' },
                        { title: '2X 免费', value: '2xfree' },
                      ]
                                        }, null, 8, ["modelValue"]))
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VSelect, {
                                      modelValue: localTask.value.hr,
                                      "onUpdate:modelValue": _cache[87] || (_cache[87] = $event => ((localTask.value.hr) = $event)),
                                      label: "排除 H&R",
                                      items: [
                        { title: '是', value: 'yes' },
                        { title: '否', value: 'no' },
                      ]
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _createElementVNode$1("section", _hoisted_29$1, [
                            _createElementVNode$1("header", _hoisted_30$1, [
                              _createElementVNode$1("div", null, [
                                _cache[123] || (_cache[123] = _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "候选过滤", -1)),
                                _createElementVNode$1("div", _hoisted_31$1, _toDisplayString$1(isBrush.value ? '刷流默认不限人数 / 体积 / 年龄（留空即为不限），如需收敛再填；范围支持单值或「最小值-最大值」' : '范围字段支持单值或「最小值-最大值」'), 1)
                              ])
                            ]),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "4"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.size,
                                      "onUpdate:modelValue": _cache[88] || (_cache[88] = $event => ((localTask.value.size) = $event)),
                                      label: "种子大小（GB）",
                                      placeholder: "10-80"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "4"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.seeder,
                                      "onUpdate:modelValue": _cache[89] || (_cache[89] = $event => ((localTask.value.seeder) = $event)),
                                      label: "做种人数",
                                      placeholder: "1-10"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "4"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.pubtime,
                                      "onUpdate:modelValue": _cache[90] || (_cache[90] = $event => ((localTask.value.pubtime) = $event)),
                                      label: "发布时间（分钟）",
                                      placeholder: "5-120"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, { cols: "12" }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.include,
                                      "onUpdate:modelValue": _cache[91] || (_cache[91] = $event => ((localTask.value.include) = $event)),
                                      label: "包含规则",
                                      placeholder: "支持正则表达式"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, { cols: "12" }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.exclude,
                                      "onUpdate:modelValue": _cache[92] || (_cache[92] = $event => ((localTask.value.exclude) = $event)),
                                      label: "排除规则",
                                      placeholder: "支持正则表达式"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createElementVNode$1("div", _hoisted_32$1, [
                              (!isBrush.value)
                                ? (_openBlock$1(), _createBlock$1(_component_VSwitch, {
                                    key: 0,
                                    modelValue: localTask.value.exclude_zero_bonus,
                                    "onUpdate:modelValue": _cache[93] || (_cache[93] = $event => ((localTask.value.exclude_zero_bonus) = $event)),
                                    label: "不选零魔种子（Wi=0.2）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]))
                                : _createCommentVNode$1("", true)
                            ])
                          ])
                        ]),
                        _: 1
                      }),
                      _createVNode$1(_component_VWindowItem, { value: "advanced" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_33$1, [
                            _cache[124] || (_cache[124] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "跨站免费取种"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, " 本站这颗不免费（下了就烧流量、拉低分享率）→ 去任意他站找「免费且同一 Release」的副本下回来，下完自动辅回本站（零下载纯做种） ")
                              ])
                            ], -1)),
                            _createElementVNode$1("div", _hoisted_34$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.crossseed_enabled,
                                "onUpdate:modelValue": _cache[94] || (_cache[94] = $event => ((localTask.value.crossseed_enabled) = $event)),
                                label: "启用跨站免费取种",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"])
                            ]),
                            (localTask.value.crossseed_enabled)
                              ? (_openBlock$1(), _createBlock$1(_component_VRow, { key: 0 }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      sm: "4"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.crossseed_max_per_round,
                                          "onUpdate:modelValue": _cache[95] || (_cache[95] = $event => ((localTask.value.crossseed_max_per_round) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "每轮跨站名额",
                                          hint: "每一轮刷流最多发起几个跨站取种",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      sm: "4"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.crossseed_max_size_gb,
                                          "onUpdate:modelValue": _cache[96] || (_cache[96] = $event => ((localTask.value.crossseed_max_size_gb) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0.1",
                                          step: "0.1",
                                          label: "单种大小上限（GB）",
                                          hint: "超过此体积的种子不做跨站取种",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode$1(_component_VCol, {
                                      cols: "12",
                                      sm: "4"
                                    }, {
                                      default: _withCtx$1(() => [
                                        _createVNode$1(_component_VTextField, {
                                          modelValue: localTask.value.crossseed_max_sites,
                                          "onUpdate:modelValue": _cache[97] || (_cache[97] = $event => ((localTask.value.crossseed_max_sites) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "最多探测站点数",
                                          hint: "每个候选最多查几个他站（越大越慢/越耗 PV）",
                                          "persistent-hint": ""
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  _: 1
                                }))
                              : _createCommentVNode$1("", true)
                          ]),
                          _createElementVNode$1("section", _hoisted_35$1, [
                            _cache[125] || (_cache[125] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "单种限速"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "只作用于当前任务新添加的种子")
                              ])
                            ], -1)),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.up_speed,
                                      "onUpdate:modelValue": _cache[98] || (_cache[98] = $event => ((localTask.value.up_speed) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "上传限速（KB/s）",
                                      hint: "留空 = 用全局档位（设置 · 常规：魔力 / 刷流上传限速）",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "6"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.dl_speed,
                                      "onUpdate:modelValue": _cache[99] || (_cache[99] = $event => ((localTask.value.dl_speed) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "下载限速（KB/s）",
                                      hint: "留空 = 用任务类型默认（魔力 1024 / 刷流全局档位）",
                                      "persistent-hint": ""
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _createElementVNode$1("section", _hoisted_36$1, [
                            _cache[131] || (_cache[131] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "生效预览"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "保存后立即写入调度，无需重启插件")
                              ])
                            ], -1)),
                            _createElementVNode$1("dl", _hoisted_37$1, [
                              _createElementVNode$1("div", null, [
                                _cache[126] || (_cache[126] = _createElementVNode$1("dt", null, "站点", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(siteName.value), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[127] || (_cache[127] = _createElementVNode$1("dt", null, "下载器", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(localTask.value.downloader || '未选择'), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[128] || (_cache[128] = _createElementVNode$1("dt", null, "调度", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(scheduleText.value), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[129] || (_cache[129] = _createElementVNode$1("dt", null, "开启时段", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(localTask.value.active_time_range || '全天'), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[130] || (_cache[130] = _createElementVNode$1("dt", null, "任务目标", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(hasGoal() ? (isBrush.value ? `${localTask.value.goal_value} GB 上传量` : `${localTask.value.goal_value} 魔力值`) : '未设置'), 1)
                              ])
                            ])
                          ])
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["modelValue"])
                ]),
                _: 1
              }, 512)
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode$1(_component_VDialog, {
        modelValue: goalWarning.value,
        "onUpdate:modelValue": _cache[102] || (_cache[102] = $event => ((goalWarning).value = $event)),
        "max-width": "30rem"
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_VCard, { class: "pa-2" }, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_VCardText, null, {
                default: _withCtx$1(() => [
                  _createElementVNode$1("div", _hoisted_38$1, [
                    _createVNode$1(_component_VIcon, {
                      icon: "mdi-flag-alert",
                      color: "warning",
                      class: "mr-2"
                    }),
                    _cache[132] || (_cache[132] = _createElementVNode$1("span", { class: "text-subtitle-1 font-weight-medium" }, "尚未设置任务目标", -1))
                  ]),
                  _createElementVNode$1("div", _hoisted_39$1, [
                    _cache[133] || (_cache[133] = _createTextVNode$1(" 建议为每个任务设置目标，达到后会自动停止： ", -1)),
                    _createElementVNode$1("strong", null, _toDisplayString$1(isBrush.value ? '站点上传量（GB）' : '站点魔力值'), 1),
                    _cache[134] || (_cache[134] = _createTextVNode$1("。 ", -1))
                  ])
                ]),
                _: 1
              }),
              _createVNode$1(_component_VCardActions, null, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_VSpacer),
                  _createVNode$1(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[101] || (_cache[101] = $event => (goalWarning.value = false))
                  }, {
                    default: _withCtx$1(() => [...(_cache[135] || (_cache[135] = [
                      _createTextVNode$1("返回填写", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode$1(_component_VBtn, {
                    color: "warning",
                    variant: "flat",
                    onClick: confirmSaveWithoutGoal
                  }, {
                    default: _withCtx$1(() => [...(_cache[136] || (_cache[136] = [
                      _createTextVNode$1("仍然保存", -1)
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
      }, 8, ["modelValue"])
    ]),
    _: 1
  }, 8, ["model-value", "fullscreen"]))
}
}

};
const TaskEditorDialog = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-8c0e24f8"]]);

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createBlock:_createBlock,toDisplayString:_toDisplayString,normalizeClass:_normalizeClass,mergeProps:_mergeProps,renderList:_renderList,Fragment:_Fragment,withCtx:_withCtx,createTextVNode:_createTextVNode,vShow:_vShow,withDirectives:_withDirectives,unref:_unref,normalizeStyle:_normalizeStyle,withModifiers:_withModifiers} = await importShared('vue');


const _hoisted_1 = { class: "magicflow-page__header" };
const _hoisted_2 = { class: "magicflow-page__identity" };
const _hoisted_3 = { class: "magicflow-logo" };
const _hoisted_4 = { class: "magicflow-page__actions" };
const _hoisted_5 = ["aria-label"];
const _hoisted_6 = { class: "magicflow-task-switch__icon" };
const _hoisted_7 = ["src"];
const _hoisted_8 = { class: "magicflow-task-switch__body" };
const _hoisted_9 = { class: "magicflow-task-switch__v" };
const _hoisted_10 = {
  key: 2,
  class: "magicflow-loading"
};
const _hoisted_11 = {
  key: 3,
  class: "magicflow-empty"
};
const _hoisted_12 = { class: "magicflow-mobile-toolbar" };
const _hoisted_13 = ["aria-label"];
const _hoisted_14 = { class: "magicflow-task-switch__icon" };
const _hoisted_15 = ["src"];
const _hoisted_16 = { class: "magicflow-task-switch__body" };
const _hoisted_17 = { class: "magicflow-task-switch__v" };
const _hoisted_18 = {
  key: 1,
  class: "magicflow-mobile-current"
};
const _hoisted_19 = { class: "magicflow-mobile-home" };
const _hoisted_20 = { class: "mh-hero__main" };
const _hoisted_21 = { class: "mh-hero__v" };
const _hoisted_22 = { class: "mh-hero__s" };
const _hoisted_23 = ["onClick"];
const _hoisted_24 = { class: "mh-count" };
const _hoisted_25 = { class: "mh-list" };
const _hoisted_26 = ["onClick"];
const _hoisted_27 = { class: "mh-row__main" };
const _hoisted_28 = { class: "mh-row__nm" };
const _hoisted_29 = {
  key: 0,
  class: "mh-row__tag"
};
const _hoisted_30 = {
  key: 0,
  class: "mh-row__num"
};
const _hoisted_31 = {
  key: 0,
  class: "mh-sublist"
};
const _hoisted_32 = ["onClick"];
const _hoisted_33 = { class: "mh-row__main" };
const _hoisted_34 = { class: "mh-row__nm" };
const _hoisted_35 = {
  key: 0,
  class: "mh-row__num"
};
const _hoisted_36 = { class: "mh-tools" };
const _hoisted_37 = ["onClick"];
const _hoisted_38 = {
  key: 0,
  class: "mh-tool__scope"
};
const _hoisted_39 = { class: "mh-foot" };
const _hoisted_40 = { class: "magicflow-layout" };
const _hoisted_41 = { class: "magicflow-task-rail__head" };
const _hoisted_42 = { class: "magicflow-task-list" };
const _hoisted_43 = ["aria-pressed", "onClick"];
const _hoisted_44 = { class: "magicflow-task-item__title" };
const _hoisted_45 = { class: "magicflow-task-item__meta" };
const _hoisted_46 = { key: 0 };
const _hoisted_47 = { key: 1 };
const _hoisted_48 = {
  key: 0,
  class: "magicflow-workspace"
};
const _hoisted_49 = { class: "magicflow-task-head" };
const _hoisted_50 = { class: "magicflow-task-head__identity" };
const _hoisted_51 = ["src"];
const _hoisted_52 = { class: "magicflow-task-head__body" };
const _hoisted_53 = { class: "magicflow-task-head__title" };
const _hoisted_54 = { class: "magicflow-task-head__actions" };
const _hoisted_55 = { class: "magicflow-mobile-detail" };
const _hoisted_56 = { class: "md-verdict__body" };
const _hoisted_57 = { class: "md-v" };
const _hoisted_58 = { class: "md-s" };
const _hoisted_59 = { class: "md-cards" };
const _hoisted_60 = { class: "md-strategy" };
const _hoisted_61 = { class: "md-entries" };
const _hoisted_62 = ["onClick"];
const _hoisted_63 = {
  class: "magicflow-tabs",
  role: "tablist"
};
const _hoisted_64 = ["aria-selected", "onClick"];
const _hoisted_65 = { class: "magicflow-stat-grid" };
const _hoisted_66 = {
  key: 0,
  class: "magicflow-stat-grid magicflow-stat-grid--single"
};
const _hoisted_67 = { class: "magicflow-overview-grid" };
const _hoisted_68 = { class: "magicflow-panel__head" };
const _hoisted_69 = { class: "magicflow-facts" };
const _hoisted_70 = { class: "magicflow-panel__head" };
const _hoisted_71 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_72 = { class: "magicflow-facts" };
const _hoisted_73 = { key: 0 };
const _hoisted_74 = {
  key: 0,
  class: "magicflow-live-alerts"
};
const _hoisted_75 = { class: "magicflow-panel__head" };
const _hoisted_76 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_77 = { class: "magicflow-run-summary" };
const _hoisted_78 = { class: "magicflow-panel__head" };
const _hoisted_79 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_80 = { class: "magicflow-flow__chain" };
const _hoisted_81 = { class: "magicflow-flow__dot" };
const _hoisted_82 = { class: "magicflow-flow__label" };
const _hoisted_83 = { class: "magicflow-panel__head" };
const _hoisted_84 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_85 = {
  key: 0,
  class: "magicflow-reasons"
};
const _hoisted_86 = { class: "magicflow-reason__track" };
const _hoisted_87 = {
  key: 1,
  class: "magicflow-table-empty"
};
const _hoisted_88 = { class: "magicflow-panel__head" };
const _hoisted_89 = { class: "magicflow-events" };
const _hoisted_90 = {
  key: 0,
  class: "text-error"
};
const _hoisted_91 = ["onClick"];
const _hoisted_92 = {
  key: 2,
  class: "magicflow-events__detail"
};
const _hoisted_93 = { class: "magicflow-events__detail-line" };
const _hoisted_94 = {
  key: 0,
  class: "magicflow-events__detail-src"
};
const _hoisted_95 = ["title"];
const _hoisted_96 = { class: "magicflow-events__detail-sub" };
const _hoisted_97 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_98 = { class: "magicflow-diagnostic-head" };
const _hoisted_99 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_100 = { class: "magicflow-torrent-filters" };
const _hoisted_101 = { class: "magicflow-panel__head" };
const _hoisted_102 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_103 = { class: "magicflow-pipeline" };
const _hoisted_104 = { class: "magicflow-pipeline__index" };
const _hoisted_105 = { key: 0 };
const _hoisted_106 = { class: "magicflow-panel__head" };
const _hoisted_107 = { class: "magicflow-torrent-filters" };
const _hoisted_108 = {
  key: 0,
  class: "magicflow-bulk-bar"
};
const _hoisted_109 = { class: "magicflow-bulk-bar__count" };
const _hoisted_110 = { class: "torrent-title-cell" };
const _hoisted_111 = { class: "magicflow-mobile-torrents" };
const _hoisted_112 = ["onClick"];
const _hoisted_113 = { class: "magicflow-mobile-torrent__head" };
const _hoisted_114 = { class: "magicflow-mobile-torrent__title" };
const _hoisted_115 = { class: "magicflow-mobile-torrent__grid" };
const _hoisted_116 = { class: "magicflow-mobile-torrent__actions" };
const _hoisted_117 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_118 = { class: "magicflow-config-grid" };
const _hoisted_119 = { class: "magicflow-panel__head" };
const _hoisted_120 = { class: "text-subtitle-1 font-weight-medium" };
const _hoisted_121 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_122 = { class: "magicflow-facts magicflow-facts--two" };
const _hoisted_123 = { class: "magicflow-config-actions" };
const _hoisted_124 = { class: "magicflow-panel__head" };
const _hoisted_125 = { class: "magicflow-stat-grid" };
const _hoisted_126 = { class: "d-flex flex-wrap ga-2 mb-2" };
const _hoisted_127 = {
  key: 0,
  class: "text-body-2 text-medium-emphasis"
};
const _hoisted_128 = { class: "magicflow-panel__head" };
const _hoisted_129 = { class: "magicflow-events" };
const _hoisted_130 = {
  key: 0,
  class: "text-error"
};
const _hoisted_131 = ["onClick"];
const _hoisted_132 = {
  key: 2,
  class: "magicflow-events__detail"
};
const _hoisted_133 = { class: "magicflow-events__detail-line" };
const _hoisted_134 = {
  key: 0,
  class: "magicflow-events__detail-src"
};
const _hoisted_135 = ["title"];
const _hoisted_136 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_137 = { style: {"margin-top":"14px","display":"flex","gap":"8px"} };
const _hoisted_138 = { class: "magicflow-settings-dialog__head" };
const _hoisted_139 = { class: "magicflow-ops-dialog__body" };
const _hoisted_140 = { class: "magicflow-ceiling-list" };
const _hoisted_141 = { class: "magicflow-ceiling-row__head" };
const _hoisted_142 = { class: "magicflow-ceiling-row__nm" };
const _hoisted_143 = { class: "magicflow-ceiling-row__val" };
const _hoisted_144 = { class: "magicflow-ceiling-bar" };
const _hoisted_145 = { class: "magicflow-ceiling-row__foot" };
const _hoisted_146 = {
  key: 0,
  class: "magicflow-ceiling-empty"
};
const _hoisted_147 = { class: "magicflow-settings-dialog__head" };
const _hoisted_148 = { class: "magicflow-ops-dialog__sub" };
const _hoisted_149 = { class: "magicflow-ops-dialog__body" };
const _hoisted_150 = { class: "magicflow-signin-stats" };
const _hoisted_151 = { class: "magicflow-signin-stat is-ok" };
const _hoisted_152 = { class: "magicflow-signin-stat__v" };
const _hoisted_153 = { class: "magicflow-signin-stat__v" };
const _hoisted_154 = { class: "magicflow-signin-stat__v" };
const _hoisted_155 = { class: "magicflow-signin-stat" };
const _hoisted_156 = { class: "magicflow-signin-stat__v" };
const _hoisted_157 = { class: "magicflow-signin-actions" };
const _hoisted_158 = { class: "magicflow-settings-block" };
const _hoisted_159 = { class: "magicflow-settings-block__head" };
const _hoisted_160 = { class: "magicflow-signin-filters" };
const _hoisted_161 = {
  key: 0,
  class: "magicflow-signin-today"
};
const _hoisted_162 = { class: "magicflow-signin-row__name" };
const _hoisted_163 = ["title"];
const _hoisted_164 = {
  key: 1,
  class: "magicflow-field__sub"
};
const _hoisted_165 = {
  key: 0,
  class: "magicflow-settings-block"
};
const _hoisted_166 = { class: "magicflow-settings-block__head" };
const _hoisted_167 = { class: "magicflow-signin-matrix" };
const _hoisted_168 = { class: "magicflow-signin-matrix__row is-head" };
const _hoisted_169 = ["title"];
const _hoisted_170 = ["title"];
const _hoisted_171 = { class: "magicflow-settings-dialog__head" };
const _hoisted_172 = { class: "magicflow-ops-dialog__sub" };
const _hoisted_173 = { class: "magicflow-ops-dialog__body" };
const _hoisted_174 = { class: "magicflow-events" };
const _hoisted_175 = {
  key: 0,
  class: "text-error"
};
const _hoisted_176 = ["onClick"];
const _hoisted_177 = {
  key: 2,
  class: "magicflow-events__detail"
};
const _hoisted_178 = { class: "magicflow-events__detail-line" };
const _hoisted_179 = {
  key: 0,
  class: "magicflow-events__detail-src"
};
const _hoisted_180 = ["title"];
const _hoisted_181 = { class: "magicflow-events__detail-sub" };
const _hoisted_182 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_183 = { class: "magicflow-settings-dialog__head" };
const _hoisted_184 = { class: "magicflow-settings-dialog__title" };
const _hoisted_185 = ["onClick"];
const _hoisted_186 = {
  key: 2,
  class: "magicflow-settings-dialog__body"
};
const _hoisted_187 = {
  key: 0,
  class: "magicflow-settings-form"
};
const _hoisted_188 = { class: "magicflow-settings-grid" };
const _hoisted_189 = {
  key: 1,
  class: "magicflow-settings-form"
};
const _hoisted_190 = { class: "magicflow-settings-grid" };
const _hoisted_191 = {
  key: 2,
  class: "magicflow-settings-form"
};
const _hoisted_192 = { class: "magicflow-iyuu-token" };
const _hoisted_193 = { class: "magicflow-iyuu-sites" };
const _hoisted_194 = { class: "magicflow-iyuu-sites__head" };
const _hoisted_195 = {
  key: 0,
  class: "magicflow-settings-hint"
};
const _hoisted_196 = {
  key: 1,
  class: "magicflow-settings-hint"
};
const _hoisted_197 = { class: "magicflow-iyuu-row__head" };
const _hoisted_198 = { class: "magicflow-iyuu-row__name" };
const _hoisted_199 = { class: "magicflow-iyuu-row__fields" };
const _hoisted_200 = {
  key: 3,
  class: "magicflow-settings-form"
};
const _hoisted_201 = { class: "magicflow-settings-grid" };
const _hoisted_202 = { class: "magicflow-settings-switches" };
const _hoisted_203 = {
  key: 4,
  class: "magicflow-settings-form"
};
const _hoisted_204 = { class: "magicflow-settings-switches" };
const _hoisted_205 = { class: "magicflow-settings-field" };
const _hoisted_206 = {
  key: 0,
  class: "magicflow-settings-hint magicflow-settings-hint--warn"
};
const _hoisted_207 = {
  key: 5,
  class: "magicflow-settings-form"
};
const _hoisted_208 = { class: "magicflow-signin-hero" };
const _hoisted_209 = { class: "magicflow-signin-hero__icon" };
const _hoisted_210 = { class: "magicflow-signin-hero__body" };
const _hoisted_211 = { class: "magicflow-signin-hero__title" };
const _hoisted_212 = { class: "magicflow-settings-block" };
const _hoisted_213 = { class: "magicflow-settings-block__head" };
const _hoisted_214 = { class: "magicflow-switch-list" };
const _hoisted_215 = {
  key: 0,
  class: "magicflow-field__sub"
};
const _hoisted_216 = { class: "magicflow-settings-block" };
const _hoisted_217 = { class: "magicflow-settings-block__head" };
const _hoisted_218 = { class: "magicflow-field-stack" };
const _hoisted_219 = { class: "magicflow-field" };
const _hoisted_220 = { class: "magicflow-field__sub" };
const _hoisted_221 = { class: "magicflow-field" };
const _hoisted_222 = { class: "magicflow-field__sub" };
const _hoisted_223 = { class: "magicflow-signin-actions" };
const _hoisted_224 = {
  key: 6,
  class: "magicflow-settings-form"
};
const _hoisted_225 = { class: "magicflow-settings-switches" };
const _hoisted_226 = { class: "magicflow-settings-switches" };
const _hoisted_227 = { class: "magicflow-settings-switches" };
const _hoisted_228 = { class: "magicflow-settings-grid" };
const _hoisted_229 = { class: "magicflow-settings-grid" };
const _hoisted_230 = {
  key: 0,
  class: "magicflow-live-alerts"
};
const _hoisted_231 = { class: "magicflow-live-alerts__head" };
const _hoisted_232 = {
  key: 7,
  class: "magicflow-settings-form"
};
const _hoisted_233 = { class: "magicflow-settings-grid" };
const _hoisted_234 = { class: "magicflow-settings-grid" };
const _hoisted_235 = { class: "magicflow-settings-switches" };
const _hoisted_236 = {
  key: 8,
  class: "magicflow-settings-form"
};
const _hoisted_237 = { class: "magicflow-settings-switches" };
const _hoisted_238 = { class: "magicflow-settings-grid" };
const _hoisted_239 = { class: "magicflow-settings-switches" };
const _hoisted_240 = { class: "magicflow-rules-actions" };
const _hoisted_241 = { class: "magicflow-settings-hint" };
const _hoisted_242 = {
  key: 0,
  class: "magicflow-settings-hint"
};
const _hoisted_243 = { class: "magicflow-rules-table" };
const _hoisted_244 = ["title"];
const _hoisted_245 = { key: 0 };
const _hoisted_246 = ["title"];
const _hoisted_247 = {
  key: 2,
  title: "站点促销规则：达到该体积自动免费（列表页可能不标促销，插件按规则补判）"
};
const _hoisted_248 = {
  key: 3,
  title: "站点促销规则：原盘自动免费"
};
const _hoisted_249 = {
  key: 4,
  title: "站点促销规则：每季第一集自动免费"
};
const _hoisted_250 = { class: "magicflow-rules-row__hr" };
const _hoisted_251 = ["title"];
const _hoisted_252 = ["title"];
const _hoisted_253 = { key: 1 };
const _hoisted_254 = {
  key: 9,
  class: "magicflow-settings-form"
};
const _hoisted_255 = { class: "magicflow-settings-switches" };
const _hoisted_256 = { class: "magicflow-settings-grid" };
const _hoisted_257 = { class: "magicflow-sort-rules" };
const _hoisted_258 = { key: 1 };
const _hoisted_259 = { class: "magicflow-sort-rules__add" };
const _hoisted_260 = { class: "magicflow-rules-actions" };
const _hoisted_261 = { class: "magicflow-settings-hint" };
const _hoisted_262 = {
  key: 0,
  class: "magicflow-tag-migrate"
};
const _hoisted_263 = { class: "magicflow-settings-hint" };
const _hoisted_264 = { class: "magicflow-tag-migrate__samples" };
const _hoisted_265 = ["title"];
const _hoisted_266 = { class: "magicflow-tag-migrate__tags" };
const _hoisted_267 = {
  key: 10,
  class: "magicflow-settings-form"
};
const _hoisted_268 = {
  key: 11,
  class: "magicflow-settings-form"
};
const _hoisted_269 = { class: "magicflow-settings-switches" };
const _hoisted_270 = { class: "magicflow-settings-field" };
const _hoisted_271 = { class: "magicflow-fb-sources" };
const _hoisted_272 = { class: "magicflow-fb-source__idx" };
const _hoisted_273 = { class: "magicflow-fb-source__name" };
const _hoisted_274 = { class: "magicflow-fb-source-add" };
const _hoisted_275 = { class: "magicflow-settings-grid" };
const _hoisted_276 = { class: "magicflow-settings-switches" };
const _hoisted_277 = { class: "magicflow-fb-actions" };
const _hoisted_278 = {
  key: 0,
  class: "magicflow-fb-running"
};
const _hoisted_279 = {
  key: 0,
  class: "magicflow-fb-report"
};
const _hoisted_280 = { class: "magicflow-fb-report__line" };
const _hoisted_281 = {
  key: 0,
  class: "magicflow-fb-report__details"
};
const _hoisted_282 = { class: "magicflow-fb-report__list" };
const _hoisted_283 = { class: "magicflow-fb-report__meta" };
const _hoisted_284 = {
  key: 1,
  class: "magicflow-fb-report__details"
};
const _hoisted_285 = { class: "magicflow-fb-report__list" };
const _hoisted_286 = { class: "magicflow-fb-report__meta" };
const _hoisted_287 = {
  key: 12,
  class: "magicflow-settings-form"
};
const _hoisted_288 = { class: "magicflow-settings-switches" };
const _hoisted_289 = { class: "magicflow-settings-field" };
const _hoisted_290 = { class: "magicflow-iyuu-token" };
const _hoisted_291 = { class: "magicflow-iyuu-token mt-2" };
const _hoisted_292 = { class: "magicflow-settings-grid" };
const _hoisted_293 = { class: "magicflow-settings-grid" };
const _hoisted_294 = { class: "magicflow-settings-switches" };
const _hoisted_295 = { class: "magicflow-settings-dialog__footer" };
const _hoisted_296 = { class: "magicflow-torrent-dialog__head" };
const _hoisted_297 = { class: "magicflow-torrent-dialog__tags" };
const _hoisted_298 = { class: "magicflow-torrent-dialog__title" };
const _hoisted_299 = { class: "magicflow-torrent-dialog__progress" };
const _hoisted_300 = { class: "magicflow-torrent-dialog__pct" };
const _hoisted_301 = { class: "magicflow-torrent-dialog__grid" };
const _hoisted_302 = { class: "magicflow-torrent-dialog__hash" };
const _hoisted_303 = { class: "text-medium-emphasis" };
const _hoisted_304 = { class: "text-medium-emphasis" };
const _hoisted_305 = { class: "magicflow-settings-dialog__head" };
const _hoisted_306 = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_307 = { class: "magicflow-cloud-dialog__summary" };
const _hoisted_308 = { class: "magicflow-cloud-dialog__actions" };
const _hoisted_309 = {
  key: 0,
  class: "magicflow-settings-hint"
};
const _hoisted_310 = {
  key: 1,
  class: "magicflow-settings-hint"
};
const _hoisted_311 = { class: "magicflow-cloud-row__main" };
const _hoisted_312 = { class: "magicflow-cloud-row__title" };
const _hoisted_313 = { class: "magicflow-cloud-row__sub" };
const _hoisted_314 = {
  key: 0,
  class: "magicflow-cloud-row__msg"
};
const _hoisted_315 = { class: "magicflow-cloud-row__side" };
const _hoisted_316 = { class: "magicflow-settings-dialog__head" };
const _hoisted_317 = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_318 = { class: "magicflow-recommend-dialog__summary" };
const _hoisted_319 = { class: "magicflow-recommend-dialog__note" };
const _hoisted_320 = { class: "magicflow-panel__head" };
const _hoisted_321 = { class: "magicflow-douban-crawl" };
const _hoisted_322 = { class: "magicflow-douban-crawl__row" };
const _hoisted_323 = { class: "text-medium-emphasis" };
const _hoisted_324 = { class: "magicflow-douban-crawl__grid" };
const _hoisted_325 = {
  key: 0,
  class: "magicflow-douban-crawl__warn"
};
const _hoisted_326 = {
  key: 1,
  class: "magicflow-douban-crawl__warn"
};
const _hoisted_327 = { class: "magicflow-douban-crawl__actions" };
const _hoisted_328 = { class: "magicflow-settings-dialog__head" };
const _hoisted_329 = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_330 = { class: "magicflow-recommend-dialog__summary" };
const _hoisted_331 = { class: "magicflow-panel__head" };
const _hoisted_332 = { class: "magicflow-crossseed-guard" };
const _hoisted_333 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_334 = {
  key: 0,
  class: "magicflow-crossseed-bans"
};
const _hoisted_335 = { class: "magicflow-crossseed-ban__main" };
const _hoisted_336 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_337 = {
  key: 1,
  class: "magicflow-table-empty"
};
const _hoisted_338 = { class: "magicflow-crossseed-list" };
const _hoisted_339 = { class: "magicflow-crossseed-item__main" };
const _hoisted_340 = ["title"];
const _hoisted_341 = { class: "magicflow-crossseed-item__meta" };
const _hoisted_342 = {
  key: 4,
  class: "text-medium-emphasis"
};
const _hoisted_343 = { class: "magicflow-panel__head" };
const _hoisted_344 = { class: "magicflow-crossseed-list" };
const _hoisted_345 = { class: "magicflow-crossseed-item__main" };
const _hoisted_346 = ["title"];
const _hoisted_347 = { class: "magicflow-crossseed-item__meta" };
const _hoisted_348 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_349 = { class: "magicflow-settings-dialog__head" };
const _hoisted_350 = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_351 = { class: "magicflow-recommend-dialog__summary" };
const _hoisted_352 = { class: "magicflow-recommend-dialog__note" };
const _hoisted_353 = { class: "magicflow-panel__head" };
const _hoisted_354 = { class: "d-flex align-center flex-wrap ga-2 justify-end" };
const _hoisted_355 = { class: "magicflow-recs" };
const _hoisted_356 = { class: "magicflow-rec__poster" };
const _hoisted_357 = ["src", "alt"];
const _hoisted_358 = { class: "magicflow-rec__main" };
const _hoisted_359 = ["title"];
const _hoisted_360 = { class: "magicflow-rec__meta" };
const _hoisted_361 = { class: "magicflow-rec__sub" };
const _hoisted_362 = {
  key: 1,
  class: "magicflow-rec__actions"
};
const _hoisted_363 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_364 = { class: "magicflow-settings-dialog__head" };
const _hoisted_365 = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_366 = { class: "magicflow-exam-hero__left" };
const _hoisted_367 = { class: "magicflow-exam-hero__num" };
const _hoisted_368 = { class: "magicflow-exam-hero__right" };
const _hoisted_369 = {
  key: 0,
  class: "magicflow-exam-hero__line"
};
const _hoisted_370 = { class: "magicflow-exam-hero__line is-dim" };
const _hoisted_371 = {
  key: 1,
  class: "magicflow-table-empty"
};
const _hoisted_372 = { class: "magicflow-exam-card__head" };
const _hoisted_373 = { class: "magicflow-exam-card__title" };
const _hoisted_374 = { class: "magicflow-exam-card__name" };
const _hoisted_375 = { class: "magicflow-exam-card__passed" };
const _hoisted_376 = { class: "magicflow-exam-items" };
const _hoisted_377 = { class: "magicflow-exam-item__label" };
const _hoisted_378 = {
  key: 0,
  class: "magicflow-exam-item__gap"
};
const _hoisted_379 = { class: "magicflow-exam-item__val" };
const _hoisted_380 = ["onClick"];
const _hoisted_381 = ["onClick"];
const _hoisted_382 = { class: "magicflow-exam-acts" };
const _hoisted_383 = { class: "magicflow-exam-act__head" };
const _hoisted_384 = {
  key: 1,
  class: "magicflow-exam-act__notes"
};
const _hoisted_385 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_386 = { class: "text-body-2" };
const _hoisted_387 = {
  key: 0,
  class: "magicflow-exam-plan__notes"
};

const {computed,inject,nextTick,onMounted,onUnmounted,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'MagicFlowWorkbench',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'MagicFlow' },
  initialTab: { type: String, default: 'overview' },
  showClose: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
},
  emits: ['close', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;
const hostToast = inject('moviepilot:toast', null);

const loading = ref(false);
const taskLoading = ref(false);
const saving = ref(false);
const error = ref('');
const statusLoaded = ref(false);
const status = ref({
  enabled: false,
  show_sidebar_nav: true,
  summary: {},
  tasks: [],
  options: { sites: [], downloaders: [] },
});
const detail = ref(null);
const bonusData = ref({ torrents: [], total_bonus: 0, torrent_count: 0, protected_count: 0 });
const bonusLoadedFor = ref('');
// 按任务缓存托管种子（切任务时秒显，再后台静默刷新）
const bonusCache = {};
const candidateData = ref({ candidates: [], total: 0, reason_counts: {} });
const candidateLoadedAt = ref(0);
const operationData = ref({ operations: [], total: 0 });
const recommendData = ref({ items: [], total: 0, recommended: 0, enabled: true });
const crossseedData = ref({ count: 0, pending: [], enabled_tasks: [] });
const recommendOpen = ref(false);
const recommendActing = ref('');
let recommendTimer = null;
let crossseedTimer = null;
let doubanServiceTimer = null;
const selectedTaskId = ref('');
const activeTab = ref(props.initialTab || 'overview');
const torrentFilter = ref('all');
const torrentStatusFilter = ref('all');
const poolView = ref('candidates');
const torrentDialog = ref(false);
const activeTorrent = ref(null);
const candidateLoadedFor = ref('');
const editorOpen = ref(false);
const editorTask = ref({});
const deleteDialog = ref(false);
const torrentDeleteDialog = ref(false);
const pendingTorrentDelete = ref(null);
// 批量操作：选中行（VDataTable show-select 与手机卡片共用）
const selectedRows = ref([]);
const batchBusy = ref(false);
const batchDeleteDialog = ref(false);
// 批量转移（托管页）
const transferDialog = ref(false);
const transferTarget = ref('idle');
const transferChoices = computed(() => {
  const out = [{ value: 'idle', text: '静默池（退回，保文件）' }];
  const me = selectedTask.value;
  const mySite = String(me?.site_name || '');
  const rest = (status.value?.tasks || []).filter(t => String(t.id) !== String(me?.id));
  rest.sort((a, b) => Number(String(b.site_name) === mySite) - Number(String(a.site_name) === mySite));
  for (const t of rest) {
    const sameSite = String(t.site_name) === mySite;
    out.push({
      value: String(t.id),
      text: `${t.name}${t.enabled ? '' : '（已停用）'} — ${t.site_name}·${t.task_type === 'brush' ? '刷流' : '魔力'}${sameSite ? ' · 同站' : ' · 跨站(会改站点标签)'}`,
    });
  }
  return out
});

function openTransfer() {
  if (!selectedHashes.value.length) return
  transferTarget.value = 'idle';
  transferDialog.value = true;
}

async function confirmTransfer() {
  const hashes = selectedHashes.value;
  if (!hashes.length || !selectedTask.value) return
  batchBusy.value = true;
  try {
    const body = transferTarget.value === 'idle'
      ? { mode: 'idle', hashes }
      : { mode: 'handover', target_task_id: transferTarget.value, hashes };
    const res = await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/handover`, body);
    if (res?.success === false) throw new Error(res?.message || '转移失败')
    notify(res?.message || '已转移');
    transferDialog.value = false;
    selectedRows.value = [];
    await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)]);
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    batchBusy.value = false;
  }
}
const selectedHashes = computed(() =>
  (selectedRows.value || []).map(row => row?.hash).filter(Boolean),
);
const ratingSourceItems = [
  { title: '只用 TMDB（默认）', value: 'tmdb' },
  { title: '豆瓣优先（拿不到回退 TMDB · 易被豆瓣限流）', value: 'douban' },
];
const settingsDialog = ref(false);
const settingsTab = ref('general');
const settingsPane = ref('form'); // 手机端设置：'dir' = 分类目录页 / 'form' = 分类表单页
const settingsNavEl = ref(null);
// ★ 手机端设置分类是单行横向胶囊条：让当前分类自动滚到可见位置（否则打开时总停在最左边）
function scrollSettingsNavToActive() {
  const el = settingsNavEl.value?.querySelector('.magicflow-settings-nav__item.is-active');
  if (el?.scrollIntoView) el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
}
watch(settingsDialog, v => { if (v) nextTick(() => scrollSettingsNavToActive()); });
watch(settingsTab, () => nextTick(() => scrollSettingsNavToActive()));
const settingsDraft = ref({
  enabled: false,
  show_sidebar_nav: true,
  debug_log: false,
  compact_mode: false,
  journal_keep: 200,
  request_interval: 0,
  bonus_upload_limit_kbps: 200,
  brush_upload_limit_kbps: 10240,
  seed_up_limit_kbps: 200,
  brush_seed_up_limit_kbps: 5120,
  tag_model_enabled: true,
  tag_silent_new_timeout_hours: 24,
  tag_snapshot_interval_hours: 6,
  sort_rules: [],
  iyuu_token: '',
  iyuu_clear: false,
  iyuu_sites: {},
  fallback_enabled: true,
  fallback_sources: ['themoviedb', 'bangumi', 'douban'],
  fallback_paths: [],
  fallback_interval_minutes: 30,
  fallback_scan_max: 30,
  fallback_sp_to_s00: false,
  fallback_after_import: true,
  fallback_dry_run: false,
  cloud_enabled: false,
  cloud_openlist_url: '',
  cloud_openlist_token: '',
  cloud_source_mount: '/quark',
  cloud_strm_mount: '/movie',
  cloud_paths: [],
  cloud_target_template: '/quark/movie/{rel}',
  cloud_interval_minutes: 360,
  cloud_scan_max: 50,
  cloud_min_size_gb: 0,
  cloud_max_size_gb: 0,
  cloud_min_age_days: 0,
  cloud_exclude_paths: [],
  cloud_exclude_tags: [],
  cloud_upload_limit_mbps: 0,
  cloud_verify: 'size',
  cloud_dry_run: true,
  cloud_delete_local: false,
  cloud_remove_torrent: false,
  cloud_notify: true,
  live_enabled: true,
  live_interval_minutes: 4,
  live_download_alert_mb: 50,
  live_ratio_target: 0.5,
  live_auto_stop: false,
  live_kill_unfree: true,
  live_kill_delete_files: true,
  promo_guard: true,
  live_notify: true,
  crossseed_guard: true,
  crossseed_guard_pct: 5,
  crossseed_guard_min_mb: 50,
  crossseed_guard_interval_min: 15,
  crossseed_guard_keep_seed: true,
  crossseed_seed_hours_default: 24,
  crossseed_site_hours: ['pt.btschool.club=10'],
  crossseed_reclaim: false,
  rules_auto_refresh: true,
});
// ---- 站点实时数据 + 流量监控（直连站点，非 MP 6h 快照）----
const liveState = ref(null);
const liveLoading = ref(false);
let liveTimer = null;
const fallbackState = ref(null);
const fallbackLoading = ref(false);
const fallbackRunning = ref(false);
const fallbackSourceDraft = ref('');
const fallbackProblemShows = computed(() => (((fallbackState.value || {}).report || {}).scanned || []).filter(s => (s.problems || []).length));
const fallbackProblemCount = computed(() => fallbackProblemShows.value.reduce((acc, s) => acc + (s.problems || []).length, 0));
// ---- 云盘归档 ----
const cloudOpen = ref(false);
const cloudState = ref(null);
const cloudLoading = ref(false);
const cloudPlanning = ref(false);
const cloudRunning = ref(false);
const cloudTesting = ref(false);
const cloudTestMsg = ref('');
const cloudTestOk = ref(false);
const cloudLimit = ref(50);
const cloudUploadingPath = ref('');
const cloudPlanItems = ref([]);
const cloudPlanStats = ref(null);
const cloudCfg = computed(() => (cloudState.value || {}).cfg || {});
const downloaderPrefsDraft = ref(normalizeDownloaderPrefs({}));
const downloaderPrefsRecommended = ref(null);
const downloaderPrefsLoading = ref(false);
const downloaderPrefsRaw = ref(null);
const downloaderPathsDraft = ref(normalizeDownloaderPaths({}));
const defaultsDraft = ref(normalizeDefaults({}));
const defaultsLoading = ref(false);
// IYUU 云端辅种（可选）：站点表按 MoviePilot 已配置站点生成
const iyuuSites = ref([]);
const siteRules = ref([]);
const rulesLoading = ref(false);
// 标签模型（3.13.0）
const tagInfo = ref(null);
const tagMigratePlan = ref(null);
const tagMigrating = ref(false);
const newRuleType = ref('subscribe');
const sortRuleTypeOptions = SORT_RULE_TYPES;
const rulesProbing = ref(false);
const iyuuLoading = ref(false);
const iyuuTesting = ref(false);
const iyuuStatus = ref(null);
const iyuuShowMore = ref({});
let refreshTimer;
let phaseTimer;
let warmingTimer;
let warmingRetryCount = 0;

// 任务图标使用站点自身图标（走 MoviePilot /site/icon/{id}，服务端带 cookie 抓取，私有站也能取到）
const siteIcons = ref({});
const siteIconPending = new Set();

async function loadSiteIcon(siteId) {
  const id = Number(siteId);
  if (!id || siteIcons.value[id] !== undefined || siteIconPending.has(id)) return
  siteIconPending.add(id);
  try {
    const data = unwrapResponse(await props.api.get(`site/icon/${id}`));
    siteIcons.value = { ...siteIcons.value, [id]: (data && data.icon) || '' };
  } catch (err) {
    siteIcons.value = { ...siteIcons.value, [id]: '' };
  } finally {
    siteIconPending.delete(id);
  }
}

const pluginBase = computed(() => `plugin/${props.pluginId || 'MagicFlow'}`);
const tasks = computed(() => status.value.tasks || []);
const defaultSavePath = computed(() => (status.value.defaults || {}).save_path || '');
const selectedTask = computed(() => tasks.value.find(item => item.id === selectedTaskId.value) || null);
/** 静默托管：静默池按站点分类（分类卡片用）。 */
const silentHostSites = computed(() => {
  const src = (selectedTask.value && selectedTask.value.classify && selectedTask.value.classify.by_site) || null;
  if (!src) return []
  return Object.entries(src)
    .map(([name, v]) => ({ name, total: (v && v.total) || 0, hr: (v && v.hr) || 0 }))
    .sort((a, b) => b.total - a.total)
});
const summary = computed(() => status.value.summary || {});
const selectedState = computed(() => {
  const t = selectedTask.value;
  if (!t) return taskStateMeta('idle', false)
  const mode = t.run_mode || 'running';
  if (mode === 'seeding') return { text: '做种中', color: 'primary', icon: 'mdi-seed-outline' }
  if (mode === 'stopped') return { text: '已停止', color: 'secondary', icon: 'mdi-stop-circle-outline' }
  return taskStateMeta(t.state, true)
});
// 当前任务的运行状态（三态）；与运行时的状态徽章互不冲突
const selectedRunMode = computed(() => runModeMeta(selectedTask.value?.run_mode || 'running'));

// 任务徽章：非「运行中」时直接显示运行状态；运行中则显示实时状态。
function taskBadge(task) {
  const mode = task?.run_mode || 'running';
  if (mode === 'seeding') return runModeMeta('seeding')
  if (mode === 'stopped') return runModeMeta('stopped')
  return taskStateMeta(task?.state, task?.enabled ?? true)
}
// 任务切换器菜单的副标题：站点 + 关键数字一行表达
function taskSwitchSubtitle(task) {
  if (!task) return ''
  const site = task.site_name || task.site_domain || '';
  const t = task.task_type || 'bonus';
  const sc = Number(task.seeding_count || 0);
  const isBrush = t === 'brush';
  // stopped 且未运行
  const mode = task.run_mode || 'running';
  if (mode === 'stopped') {
    return site ? `${site} · 已停` : '已停'
  }
  if (isBrush) {
    // 刷流任务：托管数 + 上传量
    const up = Number(task.task_uploaded || 0);
    const upText = up ? formatBytes(up) : '—';
    return site ? `${site} · ${sc} 种 · 上传 ${upText}` : `${sc} 种 · 上传 ${upText}`
  }
  // bonus 任务：托管数 + 时魔
  if (task.site_bonus_ok && task.site_bonus_per_hour != null) {
    const bh = formatBonus(task.site_bonus_per_hour);
    return site ? `${site} · ${sc} 种 · ${bh}` : `${sc} 种 · ${bh}`
  }
  return site ? `${site} · ${sc} 种` : `${sc} 种`
}
// ── ★ 页面注册表（数据驱动，新增功能页只改这个数组，不必动布局）──────────────
// key 与 open* 处理函数一一对应；后续接入手机端导航 / 底栏 / 更多菜单时统一从这里取。
// scope='global' = 插件级单例（不按任务配）；'view' = 只读视图。
// ★ 权责口径见 docs/MODULES.md：全局单例的功能页必须显式标注，避免被当成「任务级」。
const MF_PAGES = [
  { key: 'recommend', label: '推荐', icon: 'mdi-movie-star-outline', scope: 'global' },
  { key: 'exam', label: '新手考核', icon: 'mdi-school-outline', scope: 'global' },
  { key: 'signin', label: '签到', icon: 'mdi-calendar-check-outline', scope: 'global' },
  { key: 'cloud', label: '云盘归档', icon: 'mdi-cloud-upload-outline', scope: 'global' },
  { key: 'douban', label: '豆瓣评分', icon: 'mdi-database-search-outline', scope: 'global' },
  { key: 'crossseed', label: '跨站取种', icon: 'mdi-swap-horizontal-bold', scope: 'global' },
  { key: 'ceiling', label: '站点容量', icon: 'mdi-gauge', scope: 'view' },
  { key: 'ops', label: '操作记录', icon: 'mdi-history', scope: 'view' },
  { key: 'settings', label: '插件设置', icon: 'mdi-tune-variant', scope: 'global' },
];
// 统一分发：新增功能页只改 MF_PAGES + 这里加一行
function mfOpenPage(page) {
  switch (page.key) {
    case 'recommend': return openRecommend()
    case 'exam': return openExam()
    case 'signin': return openSignin()
    case 'cloud': return openCloud()
    case 'douban': return openDoubanService()
    case 'crossseed': return showCrossseed()
    case 'ceiling': return openCeiling()
    case 'ops': return openOperations('all')
    case 'settings': return openSettings()
  }
}
const opsOpen = ref(false);
// 操作记录作用域：'all' = 主页入口（跨任务 / 跨站点汇总）；'task' = 任务详情入口（当前任务）。
// ★ 主页是全局视角，绝不能把「单个任务」的流水摆在主页（既别扭又不合语义）。
const opsScope = ref('all');
function openOperations(scope = 'all') {
  opsScope.value = scope;
  opsOpen.value = true;
  if (scope === 'all') loadOperationsAll();
  else if (selectedTaskId.value) loadOperations(selectedTaskId.value);
  else operationData.value = { operations: [], total: 0 };
}
// 设置页目录（手机端：标签栏 → 目录列表；桌面端仍用标签栏）
const MF_SETTINGS_TABS = [
  { key: 'general', label: '常规', icon: 'mdi-cog-outline' },
  { key: 'downloader', label: '下载与目录', icon: 'mdi-download-network-outline' },
  { key: 'template', label: '默认任务模板', icon: 'mdi-file-document-outline' },
  { key: 'iyuu', label: 'IYUU 辅种', icon: 'mdi-sync' },
  { key: 'fallback', label: '元数据兜底', icon: 'mdi-database-search-outline' },
  { key: 'cloud', label: '云盘归档', icon: 'mdi-cloud-upload-outline' },
  { key: 'exam', label: '考核', icon: 'mdi-school-outline' },
  { key: 'signin', label: '签到', icon: 'mdi-calendar-check-outline' },
  { key: 'live', label: '站点监控', icon: 'mdi-monitor-eye' },
  { key: 'recommend', label: '推荐', icon: 'mdi-movie-star-outline' },
  { key: 'crossseed', label: '跨站', icon: 'mdi-swap-horizontal-bold' },
  { key: 'rules', label: '站点规则', icon: 'mdi-shield-check-outline' },
  { key: 'tags', label: '标签管理', icon: 'mdi-tag-multiple-outline' },
];

// ── 手机端首页（任务列表）导航状态 ────────────────────────────────────────
// 桌面端无需该状态：相关显隐全部由 @media (max-width: 959px) 的 CSS 控制。
const mobileView = ref('list'); // 'list' | 'detail'
// 窄屏（手机/平板竖屏）：弹窗改为整页。数据驱动，只改这一处。
const isNarrow = ref(typeof window !== 'undefined' ? window.matchMedia('(max-width: 959px)').matches : false);
if (typeof window !== 'undefined') {
  const mq = window.matchMedia('(max-width: 959px)');
  const onChange = (e) => { isNarrow.value = e.matches; };
  if (mq.addEventListener) mq.addEventListener('change', onChange);
  else if (mq.addListener) mq.addListener(onChange);
}
const mhOpen = ref({ need: true, live: true, rest: false });
function isGroupOpen(key) { return !!mhOpen.value[key] }
function toggleGroup(key) { mhOpen.value = { ...mhOpen.value, [key]: !mhOpen.value[key] }; }
function openTaskMobile(id) { selectTask(id); mobileView.value = 'detail'; }
function backToMobileList() { mobileView.value = 'list'; }

// 首页分组：**按站点聚合**（同站多任务折叠为一行，时魔只算一次）→ 再按优先级分组
// 需要你管（有问题/待决策）> 在跑 > 不用管（已停用 / 静默托管）
function mhTaskRank(t) {
  if (t.attention) return 0
  if (t.builtin) return 3
  const c = taskBadge(t).color;
  if (c === 'error' || c === 'warning') return 0
  const m = t.run_mode || 'running';
  return (m === 'seeding' || m === 'running') ? 1 : 2
}
const mobileHomeGroups = computed(() => {
  const sites = new Map();
  for (const t of tasks.value) {
    const key = t.builtin ? `#${t.id}` : (t.site_name || t.id);
    if (!sites.has(key)) sites.set(key, { key, site: t.site_name || t.name, builtin: !!t.builtin, tasks: [] });
    sites.get(key).tasks.push(t);
  }
  const list = [...sites.values()].map((s) => {
    s.tasks.sort((a, b) => mhTaskRank(a) - mhTaskRank(b));
    s.rank = Math.min(...s.tasks.map(mhTaskRank));
    const head = s.tasks[0];
    s.bonus = head.site_bonus_ok ? Number(head.site_bonus_per_hour || 0) : 0;
    s.num = mobileRowNum(head);
    s.attention = s.tasks.map(x => x.attention).find(Boolean) || null;
    return s
  });
  const byBonus = (a, b) => b.bonus - a.bonus;
  const mk = (key, label, hint, pred) => ({ key, label, hint, sites: list.filter(pred).sort(byBonus) });
  const groups = [
    mk('need', '需要你管', '有问题或待决策', s => s.rank === 0),
    mk('live', '在跑', '正常养护中', s => s.rank === 1),
    mk('rest', '不用管', '已停用 / 静默托管', s => s.rank >= 2),
  ].filter(g => g.sites.length);
  groups.forEach(g => { g.count = g.sites.reduce((n, s) => n + s.tasks.length, 0); });
  return groups
});
const mobileLiveCount = computed(() => {
  const set = new Set();
  for (const t of tasks.value) {
    if (t.builtin) continue
    // 只数「魔力站」（刷流任务的数字口径是上传量，不算进时魔总览）
    if (t.task_type === 'brush') continue
    const m = t.run_mode || 'running';
    if (m === 'seeding' || m === 'running') set.add(t.site_name || t.id);
  }
  return set.size
});
// 今日魔力增量（按站点去重后求和；各站增量可累加）
const mobileTodayGain = computed(() => {
  const by = new Map();
  for (const t of tasks.value) {
    if (t.bonus_day_delta == null) continue
    const k = t.site_name || t.id;
    if (!by.has(k)) by.set(k, Number(t.bonus_day_delta) || 0);
  }
  let sum = 0;
  for (const v of by.values()) sum += v;
  return sum
});
// 站点容量：每站时魔 / 上限 / 占用（按站点去重，占用高的排前）
const siteCeilingRows = computed(() => {
  const by = new Map();
  for (const t of tasks.value) {
    if (t.builtin) continue
    const k = t.site_name || t.id;
    const pct = Number(t.ceiling_pct || 0);
    const prev = by.get(k);
    if (!prev || pct > prev.pct) {
      by.set(k, {
        site: k,
        bonus: Number(t.site_bonus_per_hour || 0),
        ceiling: Number(t.site_ceiling || 0),
        pct,
        seeds: Number(t.seeding_count || 0),
      });
    }
  }
  return [...by.values()].sort((a, b) => b.pct - a.pct)
});
const ceilingOpen = ref(false);
function openCeiling() { ceilingOpen.value = true; }
// 站点折叠：多任务行可展开
const mhSiteOpen = ref({});
function siteMulti(s) { return s.tasks.length > 1 }
function siteOpen(key) { return !!mhSiteOpen.value[key] }
function toggleSite(key) { mhSiteOpen.value = { ...mhSiteOpen.value, [key]: !mhSiteOpen.value[key] }; }
function openSiteRow(s) { if (siteMulti(s)) toggleSite(s.key); else openTaskMobile(s.tasks[0].id); }
const mobileBonus = computed(() => (Number(summary.value.bonus_per_hour) || 0).toFixed(1));
computed(() => tasks.value.find(t => t.builtin)?.seeding_count || 0);
const mobileCeilingPct = computed(() => Number(summary.value.ceiling_pct || 0));
// 列表行副标题：状态词 + 关键数
function mobileRowLine(t) {
  const parts = [];
  const b = taskBadge(t);
  parts.push(b.text);
  if (t.seeding_count) parts.push(`${t.seeding_count} 种`);
  return parts.join(' · ')
}
// 列表行右侧主数：刷魔力任务给时魔（/h），刷流任务给上传量
function mobileRowNum(t) {
  if (t.task_type === 'brush') return t.task_uploaded ? `↑ ${formatBytes(t.task_uploaded)}` : ''
  if (t.site_bonus_ok && t.site_bonus_per_hour != null) return formatBonus(t.site_bonus_per_hour)
  return ''
}
// ── 手机端任务详情：紧凑块（三个数 + 策略一行 + 次级入口）──────────────
const MF_DETAIL_ENTRIES = [
  { key: 'diagnostics', label: '运行诊断', icon: 'mdi-stethoscope' },
  { key: 'pool', label: '种子池', icon: 'mdi-seed-outline' },
  { key: 'config', label: '任务配置', icon: 'mdi-tune-variant' },
  { key: 'ops', label: '操作记录', icon: 'mdi-history', action: 'ops' },
];
function mobileDetailEntry(entry) {
  const e = typeof entry === 'string' ? { key: entry } : entry;
  if (e.action === 'ops') return openOperations('task')
  activeTab.value = activeTab.value === e.key ? 'overview' : e.key;
}
const mobileDetailCards = computed(() => {
  const t = selectedTask.value;
  if (!t) return []
  const cards = [{ v: String(t.seeding_count || 0), k: '托管种' }];
  if (t.task_type === 'brush') {
    cards.push({ v: formatBytes(t.task_uploaded || 0), k: '本任务上传' });
    cards.push({ v: siteAccount.value?.ok ? formatBytes(siteAccount.value.upload || 0) : '—', k: '站点上传' });
  } else {
    cards.push({ v: t.site_bonus_ok && t.site_bonus_per_hour != null ? Number(t.site_bonus_per_hour).toFixed(2) : '—', k: '时魔 /h' });
    cards.push({ v: t.site_current_bonus != null ? Number(t.site_current_bonus).toFixed(0) : '—', k: '站点魔力' });
  }
  return cards
});
const mobileStrategyText = computed(() => {
  const t = selectedTask.value;
  if (!t) return ''
  const c = taskConfig.value || {};
  const parts = [t.task_type === 'brush' ? '刷流' : '刷魔力'];
  if (t.task_type === 'brush') {
    parts.push(`选种每 ${c.brush_interval ?? '—'} 分钟`);
    if (c.brush_seed_days) parts.push(`满 ${c.brush_seed_days} 天清理`);
  } else {
    parts.push(c.min_bonus_per_hour == null ? '最低魔力自动' : `最低魔力 ${Number(c.min_bonus_per_hour).toFixed(1)}/h`);
    parts.push(c.protect_perfect === false ? '完美种保护关' : '完美种保护开');
    if (t.protected_count) parts.push(`接管保护 ${t.protected_count}`);
  }
  const hr = Number(detailStats.value?.hr_owed ?? t.hr_owed ?? 0);
  if (hr > 0) parts.push(`H&R 欠 ${hr}`);
  return parts.join(' · ')
});
const mobileDetailHint = computed(() => {
  const d = detailStats.value || {};
  if (d.last_error) return `⚠ ${String(d.last_error).slice(0, 60)}`
  if (d.last_run_at) return `上次运行 ${formatDateTime(d.last_run_at)}`
  return '尚未运行'
});
// 「需要你管」：后端给的信号（出错 / 站点读不到 / 从未成功）
const detailAttention = computed(() => selectedTask.value?.attention || detailStats.value?.attention || null);
// 当前任务是否刷流模式（驱动整块工作台按类型显示）
const taskIsBrush = computed(() => selectedTask.value?.task_type === 'brush');
// 站点账号真实数据（上传/下载/分享率/做种数，来自站点用户页）
const siteUser = computed(() => detailStats.value?.site_user || selectedTask.value?.site_user || {});
const taskConfig = computed(() => selectedTask.value || {});
// 刷流保种天数（缺省=2，兼容未写入该字段的旧任务）
const brushSeedDays = computed(() => {
  const v = taskConfig.value?.brush_seed_days;
  return v === undefined || v === null || v === '' ? 2 : Number(v)
});
// 当前任务的「任务目标」完成情况文案
const goalFactText = computed(() => {
  const t = taskConfig.value || {};
  if (!t.goal_has) return '未设置'
  const unit = t.goal_unit || (t.task_type === 'brush' ? 'GB' : '魔力值');
  const tgt = Number(t.goal_target || 0);
  if (t.goal_source === 'pending') {
    return `— / ${tgt} ${unit} · 加载中`
  }
  const cur = Number(t.goal_current || 0);
  const curText = unit === 'GB' ? cur.toFixed(1) : cur.toFixed(2);
  return `${curText} / ${tgt} ${unit}${t.goal_reached ? '（已达标）' : ''}`
});
const taskSiteIcon = computed(() => {
  const id = Number(selectedTask.value?.site_id);
  return id ? siteIcons.value[id] || '' : ''
});
const detailStats = computed(() => detail.value || taskConfig.value);
const sortedTorrents = computed(() => {
  let items = bonusData.value.torrents || [];
  if (torrentFilter.value === 'protected') items = items.filter(item => item.is_protected);
  if (torrentStatusFilter.value !== 'all') items = items.filter(item => torrentStatusGroup(item) === torrentStatusFilter.value);
  return items
});

const reasonEntries = computed(() => {
  const counts = candidateData.value.reason_counts || {};
  return Object.entries(counts)
    .map(([label, count]) => ({ label, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
});
const maxReasonCount = computed(() => Math.max(1, ...reasonEntries.value.map(item => item.count)));
// 本轮抓取到的候选总数 = 通过数 + 各拦截原因数量
const candidateRawTotal = computed(() => {
  const rejected = Object.values(candidateData.value.reason_counts || {}).reduce((sum, value) => sum + (Number(value) || 0), 0);
  return (candidateData.value.candidates || []).length + rejected
});

// 运行诊断流程链（v5 阶段）—— 骨架五阶段两模式共用，但每阶段实做不同，文案按类型分显
const FLOW_STEPS_BONUS = [
  { key: 'entry', label: '入口检查' },
  { key: 'fetch', label: '抓取候选' },
  { key: 'wash', label: '洗池过滤' },
  { key: 'classify', label: '魔力排序' },
  { key: 'process', label: '保种入库' },
];
const FLOW_STEPS_BRUSH = [
  { key: 'entry', label: '入口检查' },
  { key: 'fetch', label: '抓取候选' },
  { key: 'wash', label: '免费筛选' },
  { key: 'classify', label: '下载人数排序' },
  { key: 'process', label: '复用·入库' },
];
const flowSteps = computed(() => (taskIsBrush.value ? FLOW_STEPS_BRUSH : FLOW_STEPS_BONUS));

// 工作台标签（预览图：分段式标签卡）
const MF_TABS = [
  { value: 'overview', label: '任务概览' },
  { value: 'diagnostics', label: '运行诊断' },
  { value: 'pool', label: '种子池' },
  { value: 'config', label: '任务配置' },
];
const flowNodes = computed(() => {
  const phase = detail.value?.last_phase || '';
  const active = !!detail.value?.run_active;
  const steps = flowSteps.value;
  const idx = steps.findIndex(step => step.key === phase);
  return steps.map((step, i) => {
    let state = 'idle';
    if (active) {
      if (idx >= 0 && i < idx) state = 'done';
      else if (i === idx) state = 'running';
    } else if (phase === 'done') {
      state = 'done';
    } else if (phase === 'error' && idx >= 0) {
      state = i < idx ? 'done' : i === idx ? 'error' : 'idle';
    }
    return { ...step, state }
  })
});

// 运行流程右上角阶段标签（预览图：阶段名 pill + 呼吸圆点，运行中闪烁）
const flowPhaseText = computed(() => {
  if (detail.value?.run_active) {
    const running = flowNodes.value.find(item => item.state === 'running');
    if (running) return running.label
  }
  const step = flowSteps.value.find(item => item.key === (detail.value?.last_phase || ''));
  return step ? step.label : runStatusText(detail.value?.last_run_status)
});

const torrentHeaders = [
  { title: '', key: 'select', sortable: false, width: 44 },
  { title: '种子', key: 'title', sortable: false },
  { title: '状态', key: 'status', sortable: false, width: 120 },
  { title: '大小', key: 'size_gb', sortable: false, width: 96 },
  { title: '上传量', key: 'uploaded', sortable: false, width: 96 },
  { title: '分享率', key: 'ratio', sortable: false, width: 84 },
  { title: '操作', key: 'actions', sortable: false, width: 120 },
];

// 全选（当前筛选结果）
const allFilteredSelected = computed(
  () => sortedTorrents.value.length > 0 && selectedHashes.value.length === sortedTorrents.value.length,
);

function notify(message, color = 'success') {
  const method = ['error', 'info', 'warning', 'success'].includes(color) ? color : 'success';
  if (typeof hostToast?.[method] === 'function') {
    hostToast[method](message);
  } else if (method === 'error') {
    error.value = message;
  }
}

const KIND_TEXT = { run: '执行', selection: '选种加入', deletion: '删种清理', protection: '手动保留', unprotection: '取消保留', reuse: '存量复用', crossseed: '跨站取种', swap: '换种', pause: '暂停种子', resume: '恢复运行', recheck: '强制校验', goal: '达标停止', state: '运行状态', tag: '标签变更', fallback: '元数据兜底', cloud: '云盘归档' };
const STATE_TEXT = { submitting: '提交中', accepted: '已受理', completed: '已完成', failed: '失败' };
const KIND_ICON = {
  run: 'mdi-play-circle-outline',
  selection: 'mdi-download-outline',
  deletion: 'mdi-delete-outline',
  reuse: 'mdi-content-duplicate',
  swap: 'mdi-swap-horizontal-circle-outline',
  protection: 'mdi-shield-check-outline',
  unprotection: 'mdi-shield-off-outline',
  pause: 'mdi-pause-circle-outline',
  resume: 'mdi-play-circle-outline',
  recheck: 'mdi-sync',
  goal: 'mdi-flag-checkered',
  state: 'mdi-power',
  tag: 'mdi-tag-outline',
  fallback: 'mdi-file-xml-box',
  cloud: 'mdi-cloud-upload-outline',
};

function operationKindText(kind) {
  return KIND_TEXT[kind] || kind
}

function operationStateText(state) {
  return STATE_TEXT[state] || state
}

function operationIcon(kind) {
  return KIND_ICON[kind] || 'mdi-circle-small'
}

function operationColor(record) {
  if (record.state === 'failed') return 'error'
  if (record.kind === 'deletion') return 'warning'
  if (record.kind === 'tag') return 'purple'
  if (record.kind === 'run') return 'secondary'
  return 'primary'
}

/** 操作记录明细：展开状态表（key=operation_id）。 */
const expandedOps = ref({});

/** 可展开的明细条目：仅 run 记录展开（tags/watchdog 等单条事件摘要已够）。
 *  run 记录第 0 项是汇总行，与上方摘要重复，过滤掉。 */
function opDetailItems(record) {
  if (!record || record.kind !== 'run') return []
  return (record.items || []).filter((it) => it.source && it.source !== 'run')
}

function hasOpDetail(record) {
  return opDetailItems(record).length > 0
}

function isOpDetailOpen(opId) {
  return !!expandedOps.value[opId]
}

function toggleOpDetail(opId) {
  expandedOps.value = { ...expandedOps.value, [opId]: !expandedOps.value[opId] };
}

/** 明细行的短标签（来源/动作）。 */
const ITEM_SOURCE_TEXT = { add: '新增', 'add-fail': '失败', reuse: '复用', 'reuse-fail': '辅种失败', adopt: '纳管', watchdog: '看门狗', run: '汇总' };

function itemSourceText(src) {
  return ITEM_SOURCE_TEXT[src] || ''
}

/** 操作记录的耗时文本（优先用后端记录，回退到创建/完成时间差）。 */
function operationDuration(record) {
  if (record.duration != null && Number(record.duration) > 0) return formatDurationSeconds(record.duration)
  return formatDuration(record.created_at, record.resolved_at)
}

/** 操作记录的一行摘要（run 记录取结果文本）。 */
function operationSummary(record) {
  const first = (record.items || [])[0];
  if (first && first.title) return first.title
  const count = (record.items || []).length;
  return count ? `${count} 个条目` : ''
}

const TORRENT_STATE_TEXT = {
  uploading: '做种中', stalledup: '做种中·无流量', forcedup: '做种中', queuedup: '排队做种',
  downloading: '下载中', forceddl: '下载中', queueddl: '排队下载', metadl: '获取元数据', checkingdl: '校验中',
  stalleddl: '下载停滞', pausedup: '已暂停', pauseddl: '已暂停', stoppedup: '已停止', stoppeddl: '已停止',
  error: '出错', missingfiles: '文件缺失', unknown: '未知',
};

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

// 托管种子状态文本：做种 / 下载 X% / 暂停 / 整理中（参考 BrushFlow）
// 注意：progress=100 不等于「做种中」——已暂停/停止、整理中、校验中的种子要显示真实状态，
// 否则会出现「状态列写作种中、筛选却归到已暂停」的口径不一致。
const TORRENT_TRANSIENT_STATES = {
  moving: '整理中',
  allocating: '分配空间',
  checkingup: '校验中',
  checkingdl: '校验中',
  checkingresumedata: '校验中',
  forcedmetadl: '获取元数据',
};
const TORRENT_PAUSED_STATES = ['pausedup', 'pauseddl', 'stoppedup', 'stoppeddl'];

function torrentStateText(item) {
  const key = String(item?.state || '').toLowerCase();
  if (TORRENT_TRANSIENT_STATES[key]) return TORRENT_TRANSIENT_STATES[key]
  if (TORRENT_PAUSED_STATES.includes(key)) return stateLabel(item?.state) || '已暂停'
  const pct = torrentProgressPct(item);
  if (pct >= 100) return '做种中'
  if (pct <= 0) return stateLabel(item?.state) || '等待中'
  return `下载 ${pct}%`
}

// 暂停 / 恢复按钮的口径：下载中的种子是「暂停下载 / 继续下载」，
// 已完成的才是「暂停做种 / 恢复做种」（避免下载中的种子出现「恢复做种」这种别扭文案）。
function torrentIsPaused(item) {
  return TORRENT_PAUSED_STATES.includes(String(item?.state || '').toLowerCase())
}

function torrentPauseLabel(item) {
  return torrentProgressPct(item) >= 100 ? '暂停做种' : '暂停下载'
}

function torrentResumeLabel(item) {
  return torrentProgressPct(item) >= 100 ? '恢复做种' : '继续下载'
}

// 下载进度百分比（0~100），供进度条使用
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100;
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}

// 托管种子状态分组（用于状态筛选）
// 覆盖 qBittorrent 全部常见状态，含 moving/allocating/checking*，避免出现
// 「分组里没这一档 → 只选中某个状态就再也看不到这些种子、各档数量之和 ≠ 总数」。
function torrentStatusGroup(item) {
  const key = String(item?.state || '').toLowerCase();
  if (['uploading', 'forcedup', 'stalledup', 'queuedup', 'checkingup'].includes(key)) return 'seeding'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'forcedmetadl', 'checkingdl', 'allocating'].includes(key)) return 'downloading'
  if (key === 'stalleddl') return 'stalled'
  if (TORRENT_PAUSED_STATES.includes(key)) return 'paused'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'other'
}

// 状态筛选选项（带数量）
const torrentStatusOptions = computed(() => {
  const items = bonusData.value.torrents || [];
  const count = group => items.filter(item => torrentStatusGroup(item) === group).length;
  const opts = [
    { title: `全部状态（${items.length}）`, value: 'all' },
    { title: `做种中（${count('seeding')}）`, value: 'seeding' },
    { title: `下载中（${count('downloading')}）`, value: 'downloading' },
    { title: `下载停滞（${count('stalled')}）`, value: 'stalled' },
    { title: `已暂停 / 停止（${count('paused')}）`, value: 'paused' },
    { title: `出错（${count('error')}）`, value: 'error' },
  ];
  const other = count('other');
  if (other > 0) opts.push({ title: `其它（${other}）`, value: 'other' });
  return opts
});

// 加载插件总览与任务列表。
async function loadStatus() {
  loading.value = true;
  try {
    status.value = unwrapResponse(await props.api.get(`${pluginBase.value}/status`)) || status.value;
    settingsDraft.value = normalizeSettings({
      enabled: status.value.enabled,
      show_sidebar_nav: status.value.show_sidebar_nav,
      debug_log: status.value.debug_log,
      compact_mode: status.value.compact_mode,
      journal_keep: status.value.journal_keep,
      request_interval: status.value.request_interval,
      bonus_upload_limit_kbps: status.value.bonus_upload_limit_kbps,
      brush_upload_limit_kbps: status.value.brush_upload_limit_kbps,
      seed_up_limit_kbps: status.value.seed_up_limit_kbps,
      brush_seed_up_limit_kbps: status.value.brush_seed_up_limit_kbps,
      tag_model_enabled: status.value.tag_model_enabled !== false,
      tag_silent_new_timeout_hours: status.value.tag_silent_new_timeout_hours ?? 24,
      tag_snapshot_interval_hours: status.value.tag_snapshot_interval_hours ?? 6,
      sort_rules: normalizeSortRules(status.value.sort_rules),
      iyuu_token: status.value.iyuu_token,
      iyuu_sites: status.value.iyuu_sites,
      ...(status.value.crossseed ? {
        crossseed_guard: status.value.crossseed.guard,
        crossseed_guard_pct: status.value.crossseed.guard_pct,
        crossseed_guard_min_mb: status.value.crossseed.guard_min_mb,
        crossseed_guard_interval_min: status.value.crossseed.guard_interval_min,
        crossseed_guard_keep_seed: status.value.crossseed.keep_seed,
        crossseed_seed_hours_default: status.value.crossseed.seed_hours_default,
        crossseed_site_hours: status.value.crossseed.site_hours || [],
        crossseed_reclaim: status.value.crossseed.reclaim,
        rules_auto_refresh: status.value.crossseed.rules_auto_refresh,
      } : {}),
      ...(status.value.fallback || {}),
      ...(status.value.live ? {
        live_enabled: status.value.live.enabled,
        live_interval_minutes: status.value.live.interval,
        live_download_alert_mb: status.value.live.download_alert_mb,
        live_ratio_target: status.value.live.ratio_target,
        live_auto_stop: status.value.live.auto_stop,
        live_kill_unfree: status.value.live.kill_unfree,
        live_kill_delete_files: status.value.live.kill_delete_files,
        promo_guard: status.value.live.promo_guard !== false,
        live_notify: status.value.live.notify,
        exam_enabled: status.value.live.exam_enabled,
        exam_include_pass: status.value.live.exam_include_pass,
        exam_sites: status.value.live.exam_sites || [],
      } : {}),
      ...(status.value.signin ? {
        signin_enabled: status.value.signin.enabled,
        signin_sites: status.value.signin.sites || [],
        signin_login_sites: status.value.signin.login_sites || [],
        signin_retry_keyword: status.value.signin.retry_keyword,
        signin_queue: status.value.signin.queue,
        signin_notify: status.value.signin.notify,
        signin_interval_minutes: status.value.signin.interval,
        signin_window_start: status.value.signin.window_start,
        signin_window_end: status.value.signin.window_end,
      } : {}),
      ...(status.value.cloud ? {
        cloud_enabled: status.value.cloud.enabled,
        cloud_openlist_url: status.value.cloud.url,
        cloud_openlist_token: '',
        cloud_source_mount: status.value.cloud.source_mount,
        cloud_strm_mount: status.value.cloud.strm_mount,
        cloud_paths: status.value.cloud.paths || [],
        cloud_target_template: status.value.cloud.target_template,
        cloud_interval_minutes: status.value.cloud.interval,
        cloud_scan_max: status.value.cloud.scan_max,
        cloud_min_size_gb: status.value.cloud.min_size_gb,
        cloud_max_size_gb: status.value.cloud.max_size_gb,
        cloud_min_age_days: status.value.cloud.min_age_days,
        cloud_exclude_paths: status.value.cloud.exclude_paths || [],
        cloud_exclude_tags: status.value.cloud.exclude_tags || [],
        cloud_upload_limit_mbps: status.value.cloud.upload_limit_mbps,
        cloud_verify: status.value.cloud.verify,
        cloud_dry_run: status.value.cloud.dry_run,
        cloud_delete_local: status.value.cloud.delete_local,
        cloud_remove_torrent: status.value.cloud.remove_torrent,
        cloud_notify: status.value.cloud.notify,
      } : {}),
    });
    statusLoaded.value = true;
    if (!selectedTaskId.value && tasks.value.length) {
      selectTask(tasks.value[0].id);
    } else if (selectedTaskId.value && !tasks.value.some(item => item.id === selectedTaskId.value)) {
      selectedTaskId.value = '';
    }
    scheduleWarmingRetry();
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    loading.value = false;
  }
}

// 冷启动时后端先返回轻量壳（warming=true）并后台构建重数据；这里快速重拉几次直到就绪。
function scheduleWarmingRetry() {
  if (status.value && status.value.warming) {
    if (warmingRetryCount < 12) {
      warmingRetryCount += 1;
      if (warmingTimer) window.clearTimeout(warmingTimer);
      warmingTimer = window.setTimeout(() => loadStatus(), 1200);
    }
  } else {
    warmingRetryCount = 0;
    if (warmingTimer) {
      window.clearTimeout(warmingTimer);
      warmingTimer = null;
    }
  }
}

// 加载任务详情统计。
async function loadDetail(taskId) {
  try {
    detail.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}`));
  } catch (err) {
    error.value = err?.message || String(err);
  }
}

// 加载托管种子与魔力汇总。
// silent=true：已有数据时后台刷新，不置加载态（切换「托管」时秒显，避免 1~2 秒空白）。
async function loadBonus(taskId, { silent = false } = {}) {
  if (!silent) taskLoading.value = true;
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}/bonus`)) || bonusData.value;
    bonusData.value = data;
    bonusCache[taskId] = data;
    bonusLoadedFor.value = taskId;
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    if (!silent) taskLoading.value = false;
  }
}

const backfilling = ref(false);
async function backfillPages() {
  const taskId = selectedTaskId.value;
  if (!taskId || backfilling.value) return
  backfilling.value = true;
  try {
    const data = unwrapResponse(await props.api.post(`${pluginBase.value}/tasks/${taskId}/backfill-pages`)) || {};
    notify(`已回填 ${data.resolved || 0} 个详情页链接${data.unresolved ? `（${data.unresolved} 个未匹配）` : ''}`);
  } catch (err) {
    notify(err?.response?.data?.message || err?.message || '回填失败', 'error');
  } finally {
    backfilling.value = false;
  }
}

// 加载候选种子（触发站点抓取，切换标签时按需加载）。
async function loadCandidates(taskId) {
  taskLoading.value = true;
  try {
    candidateData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}/candidates`)) || {
      candidates: [],
      total: 0,
      reason_counts: {},
    };
    candidateLoadedFor.value = taskId;
    candidateLoadedAt.value = Date.now();
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    taskLoading.value = false;
  }
}

// 加载操作记录（单任务）。
async function loadOperations(taskId) {
  try {
    operationData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}/operations`)) || {
      operations: [],
      total: 0,
    };
  } catch (err) {
    error.value = err?.message || String(err);
  }
}

// 加载操作记录（全局：最近 100 条，跨任务 / 跨站点）。
async function loadOperationsAll() {
  opsLoadingAll.value = true;
  try {
    operationData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/operations`)) || {
      operations: [],
      total: 0,
    };
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    opsLoadingAll.value = false;
  }
}

const opsLoadingAll = ref(false);
// 操作记录全局视图：task_id → 任务名（静默池是常驻伪任务，任务列表里没有它的条目）。
function taskLabel(taskId) {
  if (!taskId) return '—'
  if (taskId === '__silent_host__') return '静默池'
  if (taskId.startsWith('silent:')) return '静默·' + taskId.slice('silent:'.length)
  const t = tasks.value.find((x) => x.id === taskId);
  return t ? t.name || taskId : taskId
}

// ---- 推荐甄别（价值生命周期） ----
const showAllRecs = ref(false);
// 列表默认只显示「真·命中推荐」的生命周期项；未达门槛/未识别的临时种默认隐藏（「显示全部」才展开）。
function recWorthShowing(rec) {
  if (!rec) return false
  const st = String(rec.status || '').toLowerCase();
  return st === 'recommended' || st === 'confirmed' || st === 'dismissed' || st === 'deleted'
}
// 展示名：优先「媒体标题 (年份)」；不显示原始下载文件名（文件名只进 tooltip 属性）。
function recName(rec) {
  if (!rec) return ''
  const m = rec.media || {};
  const t = m.title || '';
  if (t) return m.year ? `${t} (${m.year})` : t
  return rec.title || rec.hash || ''
}
const recommendItems = computed(() => {
  const order = { recommended: 0, pending: 1, confirmed: 2, dismissed: 3, deleted: 4 };
  let items = [...(recommendData.value.items || [])];
  if (!showAllRecs.value) items = items.filter(recWorthShowing);
  items.sort((a, b) => {
    const oa = order[a.status] ?? 9;
    const ob = order[b.status] ?? 9;
    if (oa !== ob) return oa - ob
    return (b.updated_at || 0) - (a.updated_at || 0)
  });
  // 同一部作品（media_key）只保留最靠前的一条（去重：同片多发布/多版本）
  const seen = new Set();
  const out = [];
  for (const it of items) {
    const k = it.media_key || it.hash;
    if (k && seen.has(k)) continue
    if (k) seen.add(k);
    out.push(it);
  }
  return out
});
const hiddenRecCount = computed(() => (recommendData.value.items || []).filter(i => !recWorthShowing(i)).length);
const confirmedCount = computed(() => (recommendData.value.items || []).filter(i => i.status === 'confirmed').length);
// 可手动确认的行：命中推荐（待确认），或「待核实」里非「已在库 / 重复」的临时种。
function recommendActionable(rec) {
  if (!rec) return false
  const st = String(rec.status || '').toLowerCase();
  if (st === 'recommended') return true
  if (st === 'pending') {
    const r = String(rec.reason || '');
    return !r.includes('已在影视库') && !r.includes('重复推荐')
  }
  return false
}
const pendingCount = computed(() => (recommendData.value.items || []).filter(i => i.status === 'pending').length);

async function loadRecommend() {
  try {
    recommendData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/recommend`)) || { items: [], total: 0 };
  } catch (err) {
    error.value = err?.message || String(err);
  }
}

async function loadCrossseed() {
  try {
    crossseedData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/crossseed`))
      || { count: 0, pending: [], enabled_tasks: [] };
  } catch (err) {
    // 跨站取种是增强信息，失败不打断界面
  }
}

function showCrossseed() {
  crossseedOpen.value = true;
  loadCrossseed();
}

// ── 豆瓣评分服务（magicflow-douban · 3.23.1）─────────────────────────
const doubanServiceOpen = ref(false);
const doubanServiceActing = ref('');
const doubanServiceData = ref({ ok: false, records: 0, cache: {}, crawl: {} });
const doubanCrawl = computed(() => (doubanServiceData.value || {}).crawl || {});
const doubanCrawlProgress = computed(() => {
  const c = doubanCrawl.value;
  const total = Number(c.spec_total || 0);
  const idx = Number(c.spec_index || 0);
  if (!total) return 0
  return Math.min(100, Math.round((idx / total) * 100))
});

async function loadDoubanService() {
  try {
    doubanServiceData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/douban_service`))
      || { ok: false, records: 0, cache: {}, crawl: {} };
  } catch (err) {
    // 豆瓣服务是增强信息，失败不打断界面
  }
}

function openDoubanService() {
  doubanServiceOpen.value = true;
  loadDoubanService();
}

async function doubanCrawlAction(action) {
  doubanServiceActing.value = action;
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/douban_service?action=${action}`, {}));
    if (res) doubanServiceData.value = res;
  } catch (err) {
    // 静默
  } finally {
    doubanServiceActing.value = '';
  }
}

function fmtCount(n) {
  const v = Number(n || 0);
  if (v >= 10000) return `${(v / 10000).toFixed(1)} 万`
  return String(v)
}

// ── 跨站辅种：队列 / 流量兜底（3.11.0）────────────────────────────────
const crossseedOpen = ref(false);
const crossseedActing = ref('');
const crossseedPending = computed(() =>
  (Array.isArray(crossseedData.value?.pending) ? crossseedData.value.pending : [])
);
const crossseedGuard = computed(() => (crossseedData.value || {}).guard || { enabled: true, banned: [] });
const crossseedBanned = computed(() =>
  (Array.isArray(crossseedGuard.value?.banned) ? crossseedGuard.value.banned : [])
);
const crossseedSources = computed(() =>
  (Array.isArray(crossseedData.value?.sources) ? crossseedData.value.sources : [])
);

function formatRemain(min) {
  const m = Number(min);
  if (!Number.isFinite(m) || m <= 0) return '0 分钟'
  if (m < 60) return `${Math.round(m)} 分钟`
  const hrs = m / 60;
  if (hrs < 24) return `${hrs.toFixed(hrs < 10 ? 1 : 0)} 小时`
  return `${(hrs / 24).toFixed(1)} 天`
}

function crossseedStateText(it) {
  const st = String(it?.state || '');
  const p = it?.progress;
  if (st && /paused|stopped|暂停/i.test(st)) return '已暂停'
  if (Number.isFinite(Number(p)) && Number(p) >= 0.999) return '已下载完（回辅中）'
  if (Number.isFinite(Number(p)) && Number(p) > 0) return `下载中 ${(Number(p) * 100).toFixed(1)}%`
  if (p === null || p === undefined) return '下载器中无此种'
  return '等待下载'
}

async function dropCrossseed(h) {
  if (!h) return
  crossseedActing.value = `drop:${h}`;
  try {
    const res = unwrapResponse(await props.api.post(
      `${pluginBase.value}/crossseed?action=drop&hash=${encodeURIComponent(h)}`, {}
    )) || {};
    notify(res.message || '已删除跨站种', 'success');
    await loadCrossseed();
  } catch (err) {
    notify(err?.message || '删除失败', 'error');
  } finally {
    crossseedActing.value = '';
  }
}

async function unbanCrossseed(domain = '') {
  crossseedActing.value = `unban:${domain}`;
  try {
    const q = domain ? `?action=unban&site=${encodeURIComponent(domain)}` : '?action=unban';
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/crossseed${q}`, {})) || {};
    notify(res.message || '已解除来源站黑名单', 'success');
    await loadCrossseed();
  } catch (err) {
    notify(err?.message || '解除失败', 'error');
  } finally {
    crossseedActing.value = '';
  }
}

async function runCrossseedGuard() {
  crossseedActing.value = 'guard';
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/crossseed?action=guard`, {})) || {};
    if (res) crossseedData.value = res;
    notify(res.message || '流量兜底核对完成', 'success');
  } catch (err) {
    notify(err?.message || '核对失败', 'error');
  } finally {
    crossseedActing.value = '';
  }
}

async function clearCrossseed() {
  crossseedActing.value = 'clear';
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/crossseed?action=clear`, {})) || {};
    notify(res.message || '已清空待回辅队列', 'success');
    await loadCrossseed();
  } catch (err) {
    notify(err?.message || '清空失败', 'error');
  } finally {
    crossseedActing.value = '';
  }
}

async function loadLive() {
  if (liveLoading.value) return
  const sid = Number(selectedTask.value?.site_id || 0);
  liveLoading.value = true;
  try {
    liveState.value = unwrapResponse(await props.api.get(`${pluginBase.value}/live${sid ? `?site_id=${sid}` : ''}`)) || liveState.value;
  } catch (err) {
    // 站点实时数据是增强信息，失败不打断界面
  } finally {
    liveLoading.value = false;
  }
}

const siteLive = computed(() => {
  const sid = Number(selectedTask.value?.site_id || 0);
  const rows = (liveState.value || {}).sites || [];
  return rows.find(row => Number(row.site_id) === sid) || null
});
const siteLiveCfg = computed(() => (liveState.value || {}).cfg || {});
const siteLiveAlerts = computed(() => ((siteLive.value || {}).alerts || []));

// ── 签到 / 模拟登录（借鉴 MoviePilot「站点自动签到」插件）──────────────────
// 站点多选：想签几个签几个（siteSelectItems 直接来自 /status.options.sites）
const siteSelectItems = computed(() =>
  (status.value.options?.sites || []).map(s => ({
    title: s.name || s.domain || String(s.id),
    value: String(s.id),
  }))
);
const signinCfg = computed(() => status.value.signin || {});
const signinToday = computed(() => signinCfg.value.today || {});
const signinTodayRows = computed(() => {
  const cfg = signinCfg.value || {};
  const signIds = (cfg.sites || []).map(String);
  const loginIds = (cfg.login_sites || []).map(String);
  const rows = [];
  const seen = new Set()
  ;[...signIds, ...loginIds].forEach(key => {
    if (seen.has(key)) return
    seen.add(key);
    const info = siteSelectItems.value.find(s => s.value === key) || {};
    const rec = signinToday.value[key] || {};
    rows.push({
      site_id: key,
      site_name: rec.site_name || info.title || key,
      sign: signIds.includes(key),
      login: loginIds.includes(key),
      signin: rec.sign || null,
      loginResult: rec.login || null,
    });
  });
  return rows
});
const signinRunning = ref(false);
async function runSigninNow(kind = 'sign') {
  if (signinRunning.value) return
  signinRunning.value = true;
  try {
    // ★ 插件 API 的 POST 参数只从 query 绑定（body 不生效）→ 参数拼在 URL 上
    const query = new URLSearchParams({ kind: String(kind) }).toString();
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/signin/run?${query}`, {})) || {};
    const s = res.summary || {};
    notify(`${kind === 'sign' ? '签到' : '登录'}完成：成功 ${s.ok || 0} / 失败 ${s.fail || 0}`);
    // 只刷新 status（不重载 settingsDraft，避免把正在编辑的设置冲掉）
    status.value = unwrapResponse(await props.api.get(`${pluginBase.value}/status`)) || status.value;
    if (signinOpen.value) loadSigninReport();
  } catch (err) {
    notify(`执行失败：${err?.message || err}`, 'error');
  } finally {
    signinRunning.value = false;
  }
}
// ── 签到报表页（独立的「签到」功能页；设置仍在设置页）─────────────────
const signinOpen = ref(false);
const signinReport = ref({ enabled: false, sites: [], records: [], today: '' });
const signinReportLoading = ref(false);
async function loadSigninReport() {
  signinReportLoading.value = true;
  try {
    signinReport.value = unwrapResponse(await props.api.get(`${pluginBase.value}/signin?days=7`)) || signinReport.value;
  } catch (err) {
    notify(`签到报表读取失败：${err?.message || err}`, 'error');
  } finally {
    signinReportLoading.value = false;
  }
}
function openSignin() {
  signinOpen.value = true;
  loadSigninReport();
}
// ---------------- 报表（按「几十个站」的规模设计） ----------------
const signinFilter = ref('all');
const signinSearch = ref('');
const SIGNIN_STATUS_TEXT = { ok: '成功', fail: '都失败', signfail: '签到失败', loginfail: '登录失败', pending: '待执行', skip: '跳过', none: '无记录' };
// 失败类（三种颜色）：signfail=签到✗登录✓（红） / loginfail=签到✓登录✗（橙） / fail=都✗（深红）
const SIGNIN_FAIL_STATUS = ['fail', 'signfail', 'loginfail'];
function signinStatusText(s) {
  return SIGNIN_STATUS_TEXT[s] || s
}
// 日期标签：09/30 → 9/30（窄屏也能完整显示）
function signinDateLabel(d) {
  const s = String(d || '');
  if (s.length < 10) return s
  return `${Number(s.slice(5, 7))}/${Number(s.slice(8, 10))}`
}
// 单站当天要看的动作：只算「设置里勾了」的那几项（登录站不会显示签到结果）
function _signinWant(r) {
  const want = [];
  if (r.sign !== false) want.push(['签到', r.signin]);
  if (r.login !== false) want.push(['登录', r.loginResult]);
  return want
}
// 单站某天的状态：有失败→fail；缺结果→pending（今天）/none（历史）；全跳过→skip
function _signinStatus(signin, loginResult, pendingWhenEmpty, cfgSign, cfgLogin) {
  const want = _signinWant({ sign: cfgSign, login: cfgLogin, signin, loginResult });
  if (!want.length) return pendingWhenEmpty ? 'pending' : 'none'
  const vals = want.map(([, x]) => x).filter(Boolean);
  if (vals.length < want.length) return pendingWhenEmpty ? 'pending' : 'none'
  if (vals.every(x => x.skipped)) return 'skip'
  // ★ 失败按「谁失败」分色：签到✗=红、登录✗=橙、都✗=深红
  const bad = k => want.some(([kk, x]) => kk === k && x && !x.ok && !x.skipped);
  const signBad = bad('签到');
  const loginBad = bad('登录');
  if (signBad && loginBad) return 'fail'
  if (signBad) return 'signfail'
  if (loginBad) return 'loginfail'
  return 'ok'
}
const signinReportTodayRows = computed(() => {
  const sites = signinReport.value.sites || [];
  if (!sites.length) return signinTodayRows.value
  return sites.map(s => ({
    site_id: s.site_id,
    site_name: s.site_name || s.domain || String(s.site_id),
    sign: !!s.sign,
    login: !!s.login,
    signin: s.signin || null,
    loginResult: s.login_result || null,
  }))
});
// 今日各状态计数 + 过滤后的列表（失败优先，几十个站也一眼看出问题）
const signinTodayCounts = computed(() => {
  const c = { all: 0, ok: 0, fail: 0, pending: 0, skip: 0 }
  ;(signinReportTodayRows.value || []).forEach(r => {
    const s = _signinStatus(r.signin, r.loginResult, true, r.sign, r.login);
    c.all++;
    if (SIGNIN_FAIL_STATUS.includes(s)) c.fail++;
    else c[s] = (c[s] || 0) + 1;
  });
  return c
});
const signinFilterItems = computed(() => {
  const c = signinTodayCounts.value;
  return [
    { value: 'all', label: `全部 ${c.all}`, color: 'primary' },
    { value: 'fail', label: `失败 ${c.fail}`, color: 'error' },
    { value: 'pending', label: `待执行 ${c.pending}`, color: 'warning' },
    { value: 'ok', label: `成功 ${c.ok}`, color: 'success' },
  ]
});
const SIGNIN_ORDER = { fail: 0, signfail: 1, loginfail: 2, pending: 3, ok: 4, skip: 5 };
const signinTodayList = computed(() => {
  const ord = SIGNIN_ORDER;
  const q = String(signinSearch.value || '').trim().toLowerCase();
  return (signinReportTodayRows.value || [])
    .map(r => {
      const status = _signinStatus(r.signin, r.loginResult, true, r.sign, r.login);
      const pairs = _signinWant(r);
      const rt = (signinReport.value.retry || {})[String(r.site_id)];
      const fails = pairs.filter(([, x]) => x && !x.ok && !x.skipped);
      let msg;
      if (fails.length) {
        msg = fails.map(([k, x]) => `${k} ✗ ${x.message || ''}`.trim()).join(' · ');
      } else {
        // 全成功 / 待执行：只给简短标记，几十个站也不刷屏（失败才展开原因）
        msg = pairs.map(([k, x]) => (x ? `${k} ${x.ok ? '✓' : (x.skipped ? '跳过' : '✗')}` : `${k} ⏳`)).join(' · ');
      }
      return { ...r, status, msg: SIGNIN_FAIL_STATUS.includes(status) && rt ? `${msg} · ${rt.next_at} 重试` : msg }
    })
    .filter(r => !q || String(r.site_name || '').toLowerCase().includes(q))
    .filter(r => signinFilter.value === 'all' || (signinFilter.value === 'fail' ? SIGNIN_FAIL_STATUS.includes(r.status) : r.status === signinFilter.value))
    .sort((a, b) => (ord[a.status] - ord[b.status]) || String(a.site_name || '').localeCompare(String(b.site_name || '')))
});
// 近 7 天矩阵：行=站点、列=日期（点阵）；异常在前，支持几十个站滚动查看
const signinMatrix = computed(() => {
  const records = signinReport.value.records || [];
  const today = signinReport.value.today || '';
  // 近 7 天窗口：以今天为锚，缺记录的日期补空点（列固定 7 个，方便竖着对比）
  const anchor = today || records.map(r => r.date).sort().slice(-1)[0] || '';
  const dates = [];
  if (anchor) {
    const base = new Date(`${anchor}T00:00:00`);
    for (let i = 0; i < 7; i += 1) {
      const d = new Date(base);
      d.setDate(base.getDate() - i);
      dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
    }
  }
  const map = new Map();
  const ensure = (sid, name) => {
    const k = String(sid);
    if (!map.has(k)) map.set(k, { sid: k, name: name || k, cells: {} });
    else if (name) map.get(k).name = name;
    return map.get(k)
  };
  // 先按设置里的勾选取好「该看哪几项」（登录站不算签到）
  const flags = new Map()
  ;(signinReport.value.sites || []).forEach(s => {
    ensure(s.site_id, s.site_name || s.domain || String(s.site_id));
    flags.set(String(s.site_id), { sign: !!s.sign, login: !!s.login });
  });
  records.forEach(r => {
    Object.keys(r.sites || {}).forEach(sid => {
      const rec = r.sites[sid] || {};
      const row = ensure(sid, rec.site_name);
      const f = flags.get(String(sid)) || {};
      row.cells[r.date] = _signinStatus(rec.sign, rec.login, false, f.sign, f.login);
      if (rec.sign) row.sign = true;
      if (rec.login) row.login = true;
    });
  })
  ;(signinReport.value.sites || []).forEach(s => {
    const row = ensure(s.site_id, s.site_name);
    row.cells[today] = _signinStatus(s.signin, s.login_result, true, s.sign, s.login);
    row.sign = !!s.sign;
    row.login = !!s.login;
  });
  const rows = [...map.values()].map(row => {
    const cells = dates.map(d => ({ date: d, status: row.cells[d] || 'none' }));
    const failIdx = cells.findIndex(c => c.status === 'fail');
    return { ...row, cells, failIdx, todayStatus: cells.length ? cells[0].status : 'none' }
  });
  const rank = r => (r.todayStatus === 'fail' ? 0 : r.todayStatus === 'pending' ? 1 : r.failIdx >= 0 ? 2 : 3);
  rows.sort((a, b) => (rank(a) - rank(b)) || (a.failIdx - b.failIdx) || String(a.name).localeCompare(String(b.name)));
  const stats = { ok: 0, fail: 0 };
  rows.forEach(r => r.cells.forEach(c => { if (c.status === 'ok') stats.ok++; else if (c.status === 'fail') stats.fail++; }));
  return { dates, rows, stats }
});
const siteLiveLevel = computed(() => (siteLive.value || {}).level || 'ok');
const siteLiveInfo = computed(() => (siteLive.value || {}).live || {});
const siteLiveRates = computed(() => (siteLive.value || {}).rates || {});
// 站点账号数据：**实时优先**（魔流直连站点），拿不到才回退 MP 的 6h 快照 → 只展示一份，避免重复。
const siteAccount = computed(() => {
  const live = siteLiveInfo.value || {};
  if (live.ok) {
    return {
      ok: true,
      source: 'live',
      upload: live.upload || 0,
      download: live.download || 0,
      ratio: live.ratio,
      seeding: live.seeding,
      leeching: live.leeching,
      bonus: live.bonus,
      bonus_per_hour: live.bonus_per_hour,
      seeding_size: Number((siteUser.value || {}).seeding_size || 0),
      sampledAt: live.ts ? new Date(Number(live.ts) * 1000).toLocaleTimeString() : '',
    }
  }
  const mp = siteUser.value || {};
  return { ...mp, source: mp.ok ? 'mp' : '', sampledAt: '' }
});

async function actRecommend(hash, action, label) {
  if (!hash || recommendActing.value) return
  recommendActing.value = hash + action;
  try {
    const data = unwrapResponse(await props.api.post(`${pluginBase.value}/recommend/${hash}/${action}`, {})) || {};
    notify(data.message || `${label}完成`);
    await loadRecommend();
  } catch (err) {
    notify(err?.response?.data?.message || err?.message || `${label}失败`, 'error');
  } finally {
    recommendActing.value = '';
  }
}
function confirmRecommend(hash) {
  return actRecommend(hash, 'confirm', '确认')
}
function dismissRecommend(hash) {
  return actRecommend(hash, 'dismiss', '忽略')
}
function openRecommend() {
  recommendOpen.value = true;
  loadRecommend();
}

// ── 批量入库（Master 2026-09-28 07:00）────────────────────────────
const recSelected = ref({});        // hash -> true
const recBatchActing = ref(false);
// 可勾选/入库的行 = 可手动确认的那些
const recSelectable = computed(() => recommendItems.value.filter(r => recommendActionable(r)));
const recSelectedList = computed(() => recSelectable.value.filter(r => recSelected.value[r.hash]).map(r => r.hash));
const recAllChecked = computed(() => recSelectable.value.length > 0 && recSelectedList.value.length === recSelectable.value.length);
function toggleRec(hash) {
  recSelected.value = { ...recSelected.value, [hash]: !recSelected.value[hash] };
}
function toggleAllRecs() {
  const flag = !recAllChecked.value;
  const m = { ...recSelected.value };
  recSelectable.value.forEach(r => { m[r.hash] = flag; });
  recSelected.value = m;
}
async function batchImportRecommend(useAll) {
  if (recBatchActing.value) return
  const list = useAll ? [] : recSelectedList.value;
  if (!useAll && !list.length) return
  recBatchActing.value = true;
  try {
    const qs = useAll ? 'all=1' : `hashes=${encodeURIComponent(list.join(','))}`;
    const data = unwrapResponse(await props.api.post(`${pluginBase.value}/recommend/batch_import?${qs}`, {})) || {};
    notify(data.message || '批量入库完成');
    recSelected.value = {};
    await loadRecommend();
  } catch (err) {
    notify(err?.response?.data?.message || err?.message || '批量入库失败', 'error');
  } finally {
    recBatchActing.value = false;
  }
}

// ── 新手考核（顶栏入口 + 汇总弹窗 + 一键起任务）────────────────────────
const examData = ref({ sites: [], count: 0, enabled: true });
const examOpen = ref(false);
const examActing = ref('');
const examConfirm = ref(null);
let examTimer = null;
const examSites = computed(() => examData.value.sites || []);
const examBadge = computed(() => (examData.value.enabled === false ? 0 : Number(examData.value.count || 0)));
const examUrgent = computed(() => examSites.value.filter(s => Number((s.exam || {}).days_left ?? 999) <= 3).length);
// ── 板面重设（5.5.0）：按剩余天数排序 + 每项进度条 + 同任务合并 + 警告前置
const examShowPassed = ref({});
const examRows = computed(() =>
  [...(examData.value.sites || [])].sort((a, b) => Number(((a.exam || {}).days_left ?? 999)) - Number(((b.exam || {}).days_left ?? 999)))
);
const examNext = computed(() => examRows.value[0] || null);
const examUrgentWeek = computed(() => examRows.value.filter(r => Number(((r.exam || {}).days_left ?? 999)) <= 7).length);
const examPendingItems = computed(() =>
  examRows.value.reduce((n, r) => n + (((r.exam || {}).items || []).filter(i => !i.pass).length), 0)
);
const EXAM_KIND_TEXT = { upload: '刷上传', download: '补下载', bonus: '攒魔力', hold: '保持做种' };
const EXAM_KIND_ICON = {
  upload: 'mdi-upload',
  download: 'mdi-download',
  bonus: 'mdi-star-four-points-outline',
  hold: 'mdi-pause-circle-outline',
};
function examDaysShort(row) {
  const d = Number(((row || {}).exam || {}).days_left);
  if (!isFinite(d)) return '—'
  return `${Math.max(0, Math.ceil(d))} 天`
}
function examUrgencyColor(row) {
  const d = Number(((row || {}).exam || {}).days_left);
  if (!isFinite(d)) return 'grey'
  if (d <= 3) return 'error'
  if (d <= 7) return 'warning'
  return 'success'
}
// 未过的排前面（已过项可折叠）
function examItems(row) {
  const its = ((row || {}).exam || {}).items || [];
  return [...its].sort((a, b) => (a.pass ? 1 : 0) - (b.pass ? 1 : 0))
}
function examPassedCount(row) {
  return (((row || {}).exam || {}).items || []).filter(i => i.pass).length
}
function examSitePct(row) {
  const total = (((row || {}).exam || {}).items || []).length || 1;
  return Math.round((examPassedCount(row) * 100) / total)
}
function examItemPct(it) {
  const req = Number((it || {}).req_num) || 0;
  const cur = Number((it || {}).cur_num) || 0;
  if (req <= 0) return it && it.pass ? 100 : 0
  return Math.max(0, Math.min(100, Math.round((cur * 100) / req)))
}
// 还差多少（失败项最关键的信息；后端给了 short_gb/short_num 就用它）
function examItemGap(it) {
  const o = it || {};
  if (o.pass) return ''
  const fmt = v => (Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 100) / 100));
  if (Number(o.short_gb) > 0) return `${fmt(Number(o.short_gb))} GB`
  if (Number(o.short_num) > 0) return `${fmt(Number(o.short_num))}${o.unit ? ` ${o.unit}` : ''}`
  const d = (Number(o.req_num) || 0) - (Number(o.cur_num) || 0);
  if (d > 0) return `${fmt(d)}${o.unit ? ` ${o.unit}` : ''}`
  return ''
}
function examVisibleItems(row) {
  const all = examItems(row);
  if (examShowPassed.value[row.site_id]) return all
  const fails = all.filter(i => !i.pass);
  return fails.length ? fails : all
}
function examHiddenPassed(row) {
  return examItems(row).length - examVisibleItems(row).length
}
function examTogglePassed(siteId) {
  examShowPassed.value = { ...examShowPassed.value, [siteId]: !examShowPassed.value[siteId] };
}
// 同一任务只出一个动作（如「魔力增量 / 做种积分增量」都指向 XX-考核魔力）
function examActions(row) {
  const out = new Map()
  ;((row || {}).plan || []).forEach(p => {
    const key = `${p.kind}|${p.task_name || ''}`;
    if (!out.has(key)) {
      out.set(key, {
        key,
        kind: p.kind,
        label: EXAM_KIND_TEXT[p.kind] || p.label || '任务',
        icon: EXAM_KIND_ICON[p.kind] || 'mdi-play-circle-outline',
        task_name: p.task_name || '',
        notes: [],
        warn: '',
      });
    }
    const a = out.get(key)
    ;(p.notes || []).forEach(n => {
      let s = String(n || '').trim();
      if (!s) return
      // 窄屏压缩后端长句：尾巴的泛泛建议没信息量，去掉
      s = s.replace(/[;；]?\s*(魔力靠多挂种.*|靠多挂种.*)$/, '').replace('达到后自动停', '→ 自动停');
      // ⚠️ 类提醒（花钱白干/比例掉）前置成警戒条，不能埋在按钮下面
      if (/^⚠️|不建议|建议等|会低于 1|先补上传/.test(s)) {
        a.warn = a.warn ? `${a.warn} · ${s}` : s;
        return
      }
      if (!a.notes.includes(s)) a.notes.push(s);
    });
  });
  return [...out.values()]
}
async function loadExam() {
  try {
    examData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/exam`)) || examData.value;
  } catch (err) {
    // 考核是增强信息，失败不打断界面
  }
}
function openExam() {
  examOpen.value = true;
  loadExam();
}
function examPlan(row, kind) {
  return (row.plan || []).find(p => p.kind === kind) || null
}
function examAct(row, kind) {
  const item = examPlan(row, kind);
  if (!item) return
  if (item.noop || kind === 'hold' || item.kind === 'hold') {
    notify('该考核项目前无需建任务：保持做种 + 多辅种即可');
    return
  }
  examConfirm.value = { row, item, kind };
}
async function examConfirmRun() {
  const ctx = examConfirm.value;
  if (!ctx || examActing.value) return
  examActing.value = `${ctx.kind}:${ctx.row.site_id}`;
  try {
    // ★ 插件 API 的 POST 参数只在 query 绑定
    const q = new URLSearchParams({ site_id: String(ctx.row.site_id), kind: String(ctx.kind), confirm: 'true' }).toString();
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/exam/act?${q}`, {})) || {};
    notify(res.message || '已执行');
    examConfirm.value = null;
    await loadExam();
    status.value = unwrapResponse(await props.api.get(`${pluginBase.value}/status`)) || status.value;
  } catch (err) {
    notify(`执行失败：${err?.message || err}`, 'error');
  } finally {
    examActing.value = '';
  }
}

// 选择任务并刷新其详情数据。
function selectTask(taskId) {
  if (!taskId) {
    selectedTaskId.value = '';
    return
  }
  if (taskId === selectedTaskId.value) return
  selectedTaskId.value = taskId;
  reloadSelected();
  if (activeTab.value === 'pool' && poolView.value === 'candidates') loadCandidates(taskId);
}

// 重新拉取当前任务的全部明细数据。
function reloadSelected(taskId = selectedTaskId.value) {
  if (!taskId) return
  selectedTaskId.value = taskId;
  detail.value = null;
  const cachedBonus = bonusCache[taskId];
  if (cachedBonus) {
    // 命中缓存：先秒显，再后台静默刷新
    bonusData.value = cachedBonus;
    bonusLoadedFor.value = taskId;
  } else {
    bonusData.value = { torrents: [], total_bonus: 0, torrent_count: 0, protected_count: 0 };
    bonusLoadedFor.value = '';
  }
  candidateData.value = { candidates: [], total: 0, reason_counts: {} };
  candidateLoadedFor.value = '';
  candidateLoadedAt.value = 0;
  operationData.value = { operations: [], total: 0 };
  loadDetail(taskId);
  loadBonus(taskId, { silent: !!cachedBonus });
  loadOperations(taskId);
}

// 立即为当前任务执行一次。
async function runOperation() {
  if (!selectedTask.value) return
  const taskId = selectedTask.value.id;
  saving.value = true;
  try {
    unwrapResponse(await props.api.post(`${pluginBase.value}/tasks/${taskId}/run`, {}));
    notify('已提交执行请求，稍候刷新结果');
    emit('action');
    window.setTimeout(() => loadStatus(), 1500);
    window.setTimeout(() => {
      if (selectedTaskId.value !== taskId) return
      reloadSelected(taskId);
      // 执行后同步刷新候选（包含「过滤原因」），保证流水随本轮变化
      if (activeTab.value === 'pool') loadCandidates(taskId);
    }, 6000);
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// 切换当前任务的运行状态（running / seeding / stopped）。
async function setRunMode(mode) {
  if (!selectedTask.value) return
  const target = mode || 'running';
  if (target === (selectedTask.value.run_mode || 'running')) return
  saving.value = true;
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/state`, { mode: target }),
    );
    notify(`运行状态已切换为「${runModeMeta(target).text}」`);
    await loadStatus();
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// 打开新建任务弹窗。
function openCreateTask() {
  editorTask.value = cloneTask(status.value.defaults || {});
  editorOpen.value = true;
}

// 打开编辑任务弹窗。
function openEditTask() {
  if (!selectedTask.value) return
  editorTask.value = cloneTask(selectedTask.value);
  editorOpen.value = true;
}

// 保存任务（新增或更新）。
async function saveTask(payload) {
  saving.value = true;
  try {
    const normalized = normalizeTask(payload);
    if (normalized.id) {
      unwrapResponse(await props.api.put(`${pluginBase.value}/tasks/${normalized.id}`, normalized));
    } else {
      delete normalized.id;
      unwrapResponse(await props.api.post(`${pluginBase.value}/tasks`, normalized));
    }
    editorOpen.value = false;
    notify('任务已保存');
    await loadStatus();
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// ── 删除任务：名下种子交棒 / 退回静默 ─────────────────────
const handover = ref(null);
const handoverLoading = ref(false);
const handoverTarget = ref('idle');

const handoverChoices = computed(() => {
  const h = handover.value;
  const out = [{ value: 'idle', text: '退回静默池（保文件，交给全局规则管）' }];
  for (const c of h?.candidates || []) {
    const mark = c.same_tag ? '同标签·自动接管' : (c.same_site ? '同站·需重贴标签' : '跨站·会改站点标签');
    const off = c.enabled ? '' : '（已停用）';
    out.push({ value: c.id, text: `${c.name}${off} — ${c.site}·${c.state}（${mark}）` });
  }
  return out
});

async function onDeleteDialog(open) {
  if (!open) return
  handover.value = null;
  handoverTarget.value = 'idle';
  if (!selectedTask.value) return
  handoverLoading.value = true;
  try {
    handover.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${selectedTask.value.id}/handover`)) || null;
    // ★ 默认退回静默池（正常就该这样）；要指定交棒得自己选 —— 同标签任务本来就会自动接管，无需交棒
    handoverTarget.value = 'idle';
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    handoverLoading.value = false;
  }
}

// 确认删除当前任务。
async function confirmDeleteTask() {
  if (!selectedTask.value) return
  saving.value = true;
  try {
    const q = handoverTarget.value === 'idle'
      ? '?settle=idle'
      : `?handover_to=${encodeURIComponent(handoverTarget.value)}`;
    const res = await props.api.delete(`${pluginBase.value}/tasks/${selectedTask.value.id}${q}`);
    if (res?.success === false) throw new Error(res?.message || '删除失败')
    notify(res?.message || '任务已删除');
    deleteDialog.value = false;
    selectedTaskId.value = '';
    await loadStatus();
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// 对托管种子执行 保留 / 取消保留 / 暂停 / 恢复 / 强制校验 / 删除。
const TORRENT_ACTION_LABEL = {
  protect: '已保留种子',
  unprotect: '已取消保留',
  pause: '已暂停种子（不会被自动恢复）',
  resume: '已恢复做种',
  recheck: '已开始重新校验',
  delete: '已删除种子',
};

// 提示文案随种子状态变化：下载中的是「暂停 / 继续下载」，已完成的才是「暂停 / 恢复做种」，
// 避免下载中的种子弹出「已恢复做种」这种说不通的提示。
function torrentActionMessage(torrent, action) {
  if (action === 'pause' || action === 'resume') {
    const seeding = torrentProgressPct(torrent) >= 100;
    if (action === 'pause') return seeding ? '已暂停做种（不会被自动恢复）' : '已暂停下载（不会被自动恢复）'
    return seeding ? '已恢复做种' : '已继续下载'
  }
  return TORRENT_ACTION_LABEL[action] || '操作已完成'
}

async function torrentAction(torrent, action) {
  saving.value = true;
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/torrents/${torrent.hash}/${action}`, {}),
    );
    notify(torrentActionMessage(torrent, action));
    await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)]);
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// 删除种子需二次确认（避免手滑，删种不可逆）
function requestTorrentDelete(torrent) {
  if (!torrent) return
  pendingTorrentDelete.value = torrent;
  torrentDeleteDialog.value = true;
}

async function confirmTorrentDelete() {
  const target = pendingTorrentDelete.value;
  if (!target) return
  await torrentAction(target, 'delete');
  torrentDeleteDialog.value = false;
  // 若刚删的是详情弹窗里那颗，一并关掉
  if ((activeTorrent.value?.hash || '') && (activeTorrent.value?.hash || '').toLowerCase() === (target.hash || '').toLowerCase()) {
    torrentDialog.value = false;
  }
  pendingTorrentDelete.value = null;
}

// ---------------- 批量操作 ----------------
const BATCH_LABEL = {
  protect: '批量保留',
  unprotect: '批量取消保留',
  pause: '批量暂停',
  resume: '批量恢复',
  recheck: '批量校验',
  delete: '批量删除',
};

async function batchAction(action) {
  const hashes = selectedHashes.value;
  if (!hashes.length || !selectedTask.value) return
  batchBusy.value = true;
  try {
    const res = unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/torrents/batch`, { action, hashes }),
    );
    const done = Number(res?.success_count ?? hashes.length);
    notify(`${BATCH_LABEL[action] || '批量操作'}完成：${done} 个`);
    selectedRows.value = [];
    batchDeleteDialog.value = false;
    await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)]);
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    batchBusy.value = false;
  }
}

function selectAllFiltered() {
  selectedRows.value = [...sortedTorrents.value];
}

function clearSelection() {
  selectedRows.value = [];
}

// 复制 infohash
async function copyTorrentHash(hash) {
  const text = String(hash || '');
  if (!text) return
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    notify('infohash 已复制');
  } catch (err) {
    error.value = `复制失败：${err?.message || err}`;
  }
}

// 手机卡片上的勾选（对象引用与表格行一致）
function toggleTorrentSelection(item) {
  if (!item) return
  const key = (item.hash || '').toLowerCase();
  const exists = (selectedRows.value || []).some(row => (row?.hash || '').toLowerCase() === key);
  selectedRows.value = exists
    ? selectedRows.value.filter(row => (row?.hash || '').toLowerCase() !== key)
    : [...selectedRows.value, item];
}

// 打开发种详情弹窗
function openTorrentDetail(item) {
  if (!item) return
  activeTorrent.value = item;
  torrentDialog.value = true;
}

// 行点击：点到了操作按钮则不弹详情
function onTorrentRowClick(event, { item }) {
  const target = event?.target;
  if (target && typeof target.closest === 'function' && target.closest('.v-btn, button, a, input, label, .v-selection-control')) return
  openTorrentDetail(item);
}

// 在详情弹窗里操作，并在刷新后同步最新数据
async function detailTorrentAction(action) {
  const current = activeTorrent.value;
  if (!current) return
  await torrentAction(current, action);
  if (action === 'delete') {
    torrentDialog.value = false;
    return
  }
  const key = (current.hash || '').toLowerCase();
  const found = (bonusData.value.torrents || []).find(t => (t.hash || '').toLowerCase() === key);
  if (found) activeTorrent.value = found;
}

// 打开插件设置弹窗。
async function openSettings(tab = '') {
  settingsTab.value = tab || 'general';
  // 手机端：从「设置」按钮进 → 先给分类目录页；从功能格指定分类进 → 直达该分类表单页。
  settingsPane.value = isNarrow.value && !tab ? 'dir' : 'form';
  settingsDialog.value = true;
  await Promise.all([loadDownloaderPrefs(), loadDefaults(), loadIyuuSites()]);
  if (settingsTab.value === 'fallback') loadFallback();
  if (settingsTab.value === 'cloud') loadCloud();
  if (settingsTab.value === 'rules') loadRules();
  if (settingsTab.value === 'tags') loadTags();
}

// 设置分类「跳转」：目录页点分类 → 进入该分类表单页（手机端）。
function openSettingsTab(key) {
  settingsTab.value = key;
  settingsPane.value = 'form';
}

function settingsTabLabel(key) {
  return (MF_SETTINGS_TABS.find(t => t.key === key) || {}).label || '插件设置'
}

function backToSettingsDir() {
  settingsPane.value = 'dir';
}

// ── 标签模型 ─────────────────────────────────────────────
async function loadTags() {
  try {
    const res = await props.api.get(`${pluginBase.value}/tags`);
    tagInfo.value = res?.data || null;
  } catch (err) {
    error.value = err?.message || String(err);
  }
}

function sortRuleText(r) {
  return (SORT_RULE_TYPES.find(t => t.value === r?.type)?.text) || r?.type || '-'
}

function sortRuleNeedsMin(type) {
  return !!SORT_RULE_TYPES.find(t => t.value === type)?.min
}

function addSortRule() {
  const t = newRuleType.value;
  if (!t) return
  if (!Array.isArray(settingsDraft.value.sort_rules)) settingsDraft.value.sort_rules = [];
  if (settingsDraft.value.sort_rules.some(r => r.type === t)) {
    notify('该规则已存在');
    return
  }
  const meta = SORT_RULE_TYPES.find(x => x.value === t) || {};
  const row = { type: t, weight: 50, enabled: true };
  if (meta.min) row.min = meta.defaultMin ?? 0;
  settingsDraft.value.sort_rules.push(row);
}

function removeSortRule(i) {
  if (Array.isArray(settingsDraft.value.sort_rules)) settingsDraft.value.sort_rules.splice(i, 1);
}

async function previewTagMigrate() {
  tagMigrating.value = true;
  try {
    const res = await props.api.get(`${pluginBase.value}/tags?action=migrate`);
    tagMigratePlan.value = res?.data || null;
    await loadTags();
  } catch (err) {
    alert(`迁移预演失败: ${err?.message || err}`);
  } finally {
    tagMigrating.value = false;
  }
}

async function applyTagMigrate() {
  const total = tagMigratePlan.value?.total || 0;
  if (!total) return
  if (!confirm(`确认把 ${total} 个托管种子的老标签迁移到「魔流-站点-状态」新命名？\n（保留 已整理/辅种 等外来标签）`)) return
  tagMigrating.value = true;
  try {
    const res = await props.api.post(`${pluginBase.value}/tags/migrate`, { apply: true });
    notify(res?.message || '迁移完成');
    tagMigratePlan.value = null;
    await loadTags();
    emit('action');
  } catch (err) {
    alert(`迁移失败: ${err?.message || err}`);
  } finally {
    tagMigrating.value = false;
  }
}

// ── 云盘归档 ─────────────────────────────────────────────
async function loadCloud() {
  cloudLoading.value = true;
  try {
    cloudState.value = unwrapResponse(await props.api.get(`${pluginBase.value}/cloud`));
    if (!cloudPlanStats.value) cloudPlanStats.value = (cloudState.value?.plan_stats || null);
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    cloudLoading.value = false;
  }
}

async function testCloud() {
  cloudTesting.value = true;
  cloudTestMsg.value = '';
  try {
    const res = unwrapResponse(await props.api.get(`${pluginBase.value}/cloud/test`));
    cloudTestOk.value = Boolean(res?.ok);
    cloudTestMsg.value = res?.ok
      ? `连通正常 · 源挂载 ${res.source_items ?? '?'} 项 · strm 视图 ${res.strm_items ?? '?'} 项`
      : (res?.message || '连接失败');
  } catch (err) {
    cloudTestOk.value = false;
    cloudTestMsg.value = err?.message || String(err);
  } finally {
    cloudTesting.value = false;
  }
}

async function planCloud() {
  cloudPlanning.value = true;
  try {
    const res = unwrapResponse(await props.api.post(`${pluginBase.value}/cloud/plan?limit=${cloudLimit.value || 50}`));
    cloudPlanItems.value = res?.items || [];
    cloudPlanStats.value = res?.stats || null;
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    cloudPlanning.value = false;
  }
}

async function uploadCloudOne(item) {
  if (!item?.path) return
  cloudUploadingPath.value = item.path;
  try {
    const res = unwrapResponse(await props.api.post(
      `${pluginBase.value}/cloud/upload?dry_run=false&path=${encodeURIComponent(item.path)}`,
    ));
    item.status = res?.status || 'uploading';
    item.message = res?.message || '';
    notify(item.message || '已开始上传');
    scheduleCloudPoll();
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    cloudUploadingPath.value = '';
  }
}

// 上传/归档是后台跑的：轮询到没有 uploading / running 就自动停。
let cloudPollTimer = null;
function scheduleCloudPoll() {
  if (cloudPollTimer) return
  cloudPollTimer = window.setInterval(async () => {
    await loadCloud();
    const records = (cloudState.value || {}).records || [];
    const uploading = records.some(r => r?.status === 'uploading');
    if (!uploading && !(cloudState.value || {}).running) {
      window.clearInterval(cloudPollTimer);
      cloudPollTimer = null;
    }
  }, 6000);
}

function cloudRecordFor(item) {
  const key = String((item || {}).path || '');
  const records = (cloudState.value || {}).records || [];
  return records.find(r => String(r?.path || '') === key) || null
}

async function runCloud(dryRun = true) {
  cloudRunning.value = true;
  try {
    const res = unwrapResponse(await props.api.post(
      `${pluginBase.value}/cloud/run?dry_run=${dryRun ? 'true' : 'false'}&limit=${cloudLimit.value || 50}`,
    ));
    notify(res?.message || (dryRun ? '归档演练已开始' : '归档任务已开始'));
    setTimeout(() => { loadCloud(); }, 3000);
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    cloudRunning.value = false;
  }
}

function openCloud() {
  cloudOpen.value = true;
  loadCloud();
}
const usedFallbackSources = computed(() => settingsDraft.value.fallback_sources || []);
const unusedFallbackSources = computed(() =>
  FALLBACK_SOURCE_OPTIONS.filter(opt => !usedFallbackSources.value.includes(opt.value)),
);

function fallbackSourceLabel(value) {
  const found = FALLBACK_SOURCE_OPTIONS.find(opt => opt.value === value);
  return found ? found.title : String(value || '')
}

function moveFallbackSource(index, delta) {
  const list = [...(settingsDraft.value.fallback_sources || [])];
  const target = index + delta;
  if (target < 0 || target >= list.length) return
  const tmp = list[index];
  list[index] = list[target];
  list[target] = tmp;
  settingsDraft.value.fallback_sources = list;
}

function removeFallbackSource(value) {
  settingsDraft.value.fallback_sources = (settingsDraft.value.fallback_sources || []).filter(v => v !== value);
}

function addFallbackSource() {
  const value = String(fallbackSourceDraft.value || '').trim().toLowerCase();
  if (!value) return
  const list = [...(settingsDraft.value.fallback_sources || [])];
  if (!list.includes(value)) list.push(value);
  settingsDraft.value.fallback_sources = list;
  fallbackSourceDraft.value = '';
}

async function loadFallback() {
  fallbackLoading.value = true;
  try {
    fallbackState.value = unwrapResponse(await props.api.get(`${pluginBase.value}/fallback?resolve_paths=true`));
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    fallbackLoading.value = false;
    if (fallbackState.value?.running) setTimeout(() => { loadFallback(); }, 6000);
  }
}

async function runFallback(dryRun = false) {
  fallbackRunning.value = true;
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/fallback/run?dry_run=${dryRun ? 'true' : 'false'}`),
    );
    notify(dryRun ? '演练扫描已开始（不会写 NFO）' : '元数据兜底已开始');
    setTimeout(() => { loadFallback(); }, 3000);
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    fallbackRunning.value = false;
  }
}

// 加载 IYUU 站点表（按 MoviePilot 已配置站点生成）。
async function loadRules() {
  rulesLoading.value = true;
  try {
    const res = await props.api.get('rules');
    siteRules.value = res?.data?.rules || [];
  } catch (e) {
    siteRules.value = [];
  } finally {
    rulesLoading.value = false;
  }
}

async function probeRules(site) {
  rulesProbing.value = true;
  try {
    const q = site ? `&site=${encodeURIComponent(site)}` : '';
    const res = await props.api.get(`rules?action=probe${q}`);
    if (res?.success === false) throw new Error(res?.message || '探测失败')
    siteRules.value = res?.data?.rules || siteRules.value;
    return res
  } finally {
    rulesProbing.value = false;
  }
}

async function setRuleHr(row, hr) {
  if (!row?.domain) return
  try {
    const res = await props.api.get(
      `rules?action=hr&site=${encodeURIComponent(row.domain)}&hr=${encodeURIComponent(hr)}`,
    );
    if (res?.success === false) throw new Error(res?.message || '失败')
    siteRules.value = res?.data?.rules || siteRules.value;
    await loadRules();
  } catch (e) {
    alert(`标记失败: ${e?.message || e}`);
  }
}

async function setRuleHours(row, hours) {
  const dom = row?.domain;
  if (!dom) return
  await props.api.get(`rules?action=set&site=${encodeURIComponent(dom)}&hours=${encodeURIComponent(hours)}`);
  await loadRules();
}

async function refreshRules() {
  const res = await props.api.get('rules?action=refresh');
  siteRules.value = res?.data?.rules || [];
}

function ruleSourceText(row) {
  const src = row?.hours_src;
  const base = ({ manual: '手填', welcome: '收件箱规则', probe: '页面探测', builtin: '内置', default: '全局默认' })[src] || src || '-';
  if (src === 'probe' && row?.confidence && row.confidence !== 'high') return `${base}(低可信)`
  if (row?.hr_src === 'retired') return `${base}`
  return base
}

async function loadIyuuSites() {
  iyuuLoading.value = true;
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/iyuu/sites`));
    iyuuStatus.value = data || null;
    const draftFill = normalizeIyuuSites(settingsDraft.value.iyuu_sites);
    iyuuSites.value = (data?.sites || []).map(row => {
      const domain = String(row.domain || '').toLowerCase();
      const serverFill = normalizeIyuuSites({ d: row.fill || {} }).d || {};
      const fill = draftFill[domain] || serverFill;
      return {
        id: row.id,
        name: row.name || row.domain || '',
        domain: row.domain || '',
        iyuu_sid: row.iyuu_sid,
        is_active: row.is_active,
        has_apikey: row.has_apikey,
        has_cookie: row.has_cookie,
        passkey: fill.passkey || '',
        uid: fill.uid || '',
        downhash: fill.downhash || '',
      }
    });
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    iyuuLoading.value = false;
  }
}

// 把站点密钥表写回 settingsDraft（保存前调用）。
function syncIyuuToDraft() {
  const map = {};
  iyuuSites.value.forEach(row => {
    const domain = String(row.domain || '').toLowerCase();
    if (!domain) return
    const clean = normalizeIyuuSites({ d: { passkey: row.passkey, uid: row.uid, downhash: row.downhash } }).d;
    if (clean) map[domain] = clean;
  });
  settingsDraft.value.iyuu_sites = map;
}

// 测试 IYUU Token。
async function testIyuu() {
  iyuuTesting.value = true;
  try {
    syncIyuuToDraft();
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/iyuu/test`));
    notify(`IYUU Token 有效（账号 ${data?.username || data?.id || '-'}，站点表 ${data?.sites ?? 0} 条）`);
  } catch (err) {
    notify(err?.message || String(err));
  } finally {
    iyuuTesting.value = false;
  }
}

// 清空已存的 IYUU Token（后端「空值=保持原值」，所以清空要显式带 iyuu_clear）。
async function clearIyuuToken() {
  settingsDraft.value.iyuu_token = '';
  settingsDraft.value.iyuu_clear = true;
  try {
    await saveIyuu();
  } finally {
    settingsDraft.value.iyuu_clear = false;
  }
}

// 保存 IYUU 设置（Token + 站点密钥表）。
async function saveIyuu() {
  saving.value = true;
  try {
    syncIyuuToDraft();
    unwrapResponse(await props.api.post(`${pluginBase.value}/settings`, normalizeSettings(settingsDraft.value)));
    notify('IYUU 设置已保存');
    await loadStatus();
    await loadIyuuSites();
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// 加载下载器全局参数。
async function loadDownloaderPrefs() {
  downloaderPrefsLoading.value = true;
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/downloader/prefs`));
    if (data && data.available) {
      downloaderPrefsDraft.value = normalizeDownloaderPrefs(data);
      downloaderPathsDraft.value = normalizeDownloaderPaths(data);
      downloaderPrefsRecommended.value = data.recommended || null;
      downloaderPrefsRaw.value = data.raw || null;
    }
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    downloaderPrefsLoading.value = false;
  }
}

// 把下载器参数恢复为推荐值（仅填表，点保存才写入）。
function applyRecommendedPrefs() {
  if (downloaderPrefsRecommended.value) {
    downloaderPrefsDraft.value = normalizeDownloaderPrefs(downloaderPrefsRecommended.value);
    notify('已填入推荐值，点「保存」后生效');
  }
}

// 加载默认任务模板。
async function loadDefaults() {
  defaultsLoading.value = true;
  try {
    const data = unwrapResponse(await props.api.get(`${pluginBase.value}/defaults`));
    defaultsDraft.value = normalizeDefaults(data || {});
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    defaultsLoading.value = false;
  }
}

// 保存默认任务模板。
async function saveDefaults() {
  saving.value = true;
  try {
    unwrapResponse(await props.api.post(`${pluginBase.value}/defaults`, normalizeDefaults(defaultsDraft.value)));
    notify('默认任务模板已保存');
    await loadStatus();
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// 保存当前设置标签页。
function saveActiveSettings() {
  const tab = settingsTab.value;
  if (tab === 'downloader') return saveDownloaderAndPaths()
  if (tab === 'template') return saveDefaults()
  if (tab === 'iyuu') return saveIyuu()
  if (tab === 'fallback') return saveSettings()
  if (tab === 'cloud') return saveCloud()
  return saveSettings()
}

// 保存「云盘归档」设置：保存后立刻回读配置 + 自检一次，避免「存了但没生效」。
async function saveCloud() {
  await saveSettings();
  await loadCloud();
  await testCloud();
}

// 保存「下载与目录」标签：qBittorrent 全局参数 + 全局路径 + 任务保存目录（一次存齐）。
async function saveDownloaderAndPaths() {
  saving.value = true;
  try {
    const data = unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/prefs`, normalizeDownloaderPrefs(downloaderPrefsDraft.value)),
    );
    if (data && data.available) {
      downloaderPrefsDraft.value = normalizeDownloaderPrefs(data);
      downloaderPrefsRaw.value = data.raw || null;
    }
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/paths`, normalizeDownloaderPaths(downloaderPathsDraft.value)),
    );
    unwrapResponse(await props.api.post(`${pluginBase.value}/defaults`, normalizeDefaults(defaultsDraft.value)));
    notify('下载与目录已保存');
    await loadStatus();
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// 保存全局设置。
async function saveSettings() {  saving.value = true;
  try {
    unwrapResponse(await props.api.post(`${pluginBase.value}/settings`, normalizeSettings(settingsDraft.value)));
    notify('设置已保存');
    await loadStatus();
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

watch(activeTab, tab => {
  // 进入「种子池」重新拉候选 / 托管，保证最新
  if (tab === 'pool' && selectedTaskId.value) {
    if (poolView.value === 'candidates') loadCandidates(selectedTaskId.value);
    else if (bonusLoadedFor.value === selectedTaskId.value) loadBonus(selectedTaskId.value, { silent: true });
    else loadBonus(selectedTaskId.value);
  }
  if (tab === 'diagnostics' && selectedTaskId.value) {
    loadOperations(selectedTaskId.value);
    loadDetail(selectedTaskId.value);
  }
});

watch(poolView, view => {
  if (!selectedTaskId.value) return
  if (view === 'candidates') {
    loadCandidates(selectedTaskId.value);
  } else if (bonusLoadedFor.value === selectedTaskId.value) {
    // 已有托管数据：立即展示，后台静默刷新
    loadBonus(selectedTaskId.value, { silent: true });
  } else {
    loadBonus(selectedTaskId.value);
  }
});

watch(
  () => props.initialTab,
  tab => {
    if (tab) activeTab.value = tab;
  },
);

// 任务切换时按 site_id 拉取站点图标（内存缓存，避免重复请求）
watch(
  () => selectedTask.value?.site_id,
  siteId => {
    if (siteId) loadSiteIcon(siteId);
    loadLive();
  },
  { immediate: true },
);

onMounted(() => {
  loadStatus();
  loadRecommend();
  refreshTimer = window.setInterval(loadStatus, 30000);
  // 推荐列表是全局的，低频刷新一下角标计数
  recommendTimer = window.setInterval(loadRecommend, 60000);
  // 跨站免费取种待回辅队列（低频刷角标）
  loadCrossseed();
  crossseedTimer = window.setInterval(loadCrossseed, 120000);
  // 豆瓣评分服务（库容量 + 慢爬进度，低频刷）
  loadDoubanService();
  doubanServiceTimer = window.setInterval(loadDoubanService, 60000);
  // 新手考核也是全局的（低频刷新角标；关闭时服务端立即返回，零开销）
  loadExam();
  examTimer = window.setInterval(loadExam, 300000);
  // 站点实时数据：采样周期 240s，这里 120s 轮询（服务端有缓存，不会重复打站点）
  loadLive();
  liveTimer = window.setInterval(loadLive, 120000);
  // 运行诊断页每秒多刷新一次任务阶段，驱动流程链转圈
  phaseTimer = window.setInterval(() => {
    if (activeTab.value === 'diagnostics' && selectedTaskId.value) loadDetail(selectedTaskId.value);
  }, 1500);
});

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer);
  if (phaseTimer) window.clearInterval(phaseTimer);
  if (recommendTimer) window.clearInterval(recommendTimer);
  if (crossseedTimer) window.clearInterval(crossseedTimer);
  if (doubanServiceTimer) window.clearInterval(doubanServiceTimer);
  if (examTimer) window.clearInterval(examTimer);
  if (liveTimer) window.clearInterval(liveTimer);
  if (warmingTimer) window.clearTimeout(warmingTimer);
  if (cloudPollTimer) window.clearInterval(cloudPollTimer);
});

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VListItem = _resolveComponent("VListItem");
  const _component_VList = _resolveComponent("VList");
  const _component_VMenu = _resolveComponent("VMenu");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VBadge = _resolveComponent("VBadge");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSkeletonLoader = _resolveComponent("VSkeletonLoader");
  const _component_VSheet = _resolveComponent("VSheet");
  const _component_VAvatar = _resolveComponent("VAvatar");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VWindowItem = _resolveComponent("VWindowItem");
  const _component_VBtnToggle = _resolveComponent("VBtnToggle");
  const _component_VSelect = _resolveComponent("VSelect");
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VCheckbox = _resolveComponent("VCheckbox");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VWindow = _resolveComponent("VWindow");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VDialog = _resolveComponent("VDialog");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCombobox = _resolveComponent("VCombobox");
  const _component_VCardActions = _resolveComponent("VCardActions");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCardTitle = _resolveComponent("VCardTitle");

  return (_openBlock(), _createElementBlock("div", {
    class: _normalizeClass(["magicflow-page", {
      'magicflow-page--compact': __props.compact || status.value.compact_mode,
      'magicflow-page--m-list': mobileView.value === 'list',
      'magicflow-page--m-detail': mobileView.value === 'detail',
    }])
  }, [
    _createElementVNode("header", _hoisted_1, [
      _createElementVNode("div", _hoisted_2, [
        _createElementVNode("span", _hoisted_3, [
          _createVNode(_component_VIcon, {
            icon: "mdi-magnet",
            size: "20"
          })
        ]),
        _cache[196] || (_cache[196] = _createElementVNode("div", null, [
          _createElementVNode("h1", null, "魔流"),
          _createElementVNode("p", null, "PT 做种 · 魔力养护 / 刷流保种")
        ], -1))
      ]),
      _createElementVNode("div", _hoisted_4, [
        (tasks.value.length)
          ? (_openBlock(), _createBlock(_component_VMenu, {
              key: 0,
              "close-on-content-click": true,
              location: "bottom end"
            }, {
              activator: _withCtx(({ props: menuProps }) => [
                _createElementVNode("button", _mergeProps(menuProps, {
                  type: "button",
                  class: "magicflow-task-switch",
                  "aria-label": `当前任务：${selectedTask.value?.name || ''}`
                }), [
                  _createElementVNode("span", _hoisted_6, [
                    (taskSiteIcon.value)
                      ? (_openBlock(), _createElementBlock("img", {
                          key: 0,
                          src: taskSiteIcon.value,
                          alt: ""
                        }, null, 8, _hoisted_7))
                      : (_openBlock(), _createBlock(_component_VIcon, {
                          key: 1,
                          icon: "mdi-web",
                          size: "15"
                        }))
                  ]),
                  _createElementVNode("span", _hoisted_8, [
                    _cache[197] || (_cache[197] = _createElementVNode("span", { class: "magicflow-task-switch__k" }, "当前任务", -1)),
                    _createElementVNode("span", _hoisted_9, _toDisplayString(selectedTask.value?.name || '—') + " · " + _toDisplayString(selectedTask.value?.site_name || ''), 1)
                  ]),
                  _createElementVNode("span", {
                    class: _normalizeClass(["magicflow-status-dot", `magicflow-status-dot--${selectedState.value.color}`])
                  }, null, 2),
                  _createVNode(_component_VIcon, {
                    icon: "mdi-chevron-down",
                    size: "18",
                    class: "magicflow-task-switch__chev"
                  })
                ], 16, _hoisted_5)
              ]),
              default: _withCtx(() => [
                _createVNode(_component_VList, {
                  density: "comfortable",
                  class: "magicflow-task-switch__menu"
                }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tasks.value, (task) => {
                      return (_openBlock(), _createBlock(_component_VListItem, {
                        key: task.id,
                        title: task.name,
                        subtitle: taskSwitchSubtitle(task),
                        active: task.id === selectedTaskId.value,
                        lines: "two",
                        onClick: $event => (selectTask(task.id))
                      }, {
                        prepend: _withCtx(() => [
                          _createVNode(_component_VIcon, {
                            icon: taskBadge(task).icon,
                            color: taskBadge(task).color,
                            size: "18"
                          }, null, 8, ["icon", "color"])
                        ]),
                        _: 2
                      }, 1032, ["title", "subtitle", "active", "onClick"]))
                    }), 128))
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }))
          : _createCommentVNode("", true),
        (summary.value.total_tasks)
          ? (_openBlock(), _createBlock(_component_VChip, {
              key: 1,
              class: "magicflow-enabled-chip",
              size: "small",
              variant: "tonal",
              title: `共 ${summary.value.total_tasks} 个任务：运行中 = 跑流程+做种；做种中 = 停调度只保做种；已停止 = 种子全暂停`
            }, {
              default: _withCtx(() => [
                _createTextVNode(" 运行 " + _toDisplayString(summary.value.running_tasks || 0) + " · 做种 " + _toDisplayString(summary.value.seeding_tasks || 0) + " · 停 " + _toDisplayString(summary.value.stopped_tasks || 0), 1)
              ]),
              _: 1
            }, 8, ["title"]))
          : _createCommentVNode("", true),
        _createVNode(_component_VBtn, {
          class: "magicflow-header-create",
          color: "primary",
          variant: "flat",
          "prepend-icon": "mdi-plus",
          onClick: openCreateTask
        }, {
          default: _withCtx(() => [...(_cache[198] || (_cache[198] = [
            _createTextVNode(" 新建任务 ", -1)
          ]))]),
          _: 1
        }),
        (recommendData.value.enabled !== false && (recommendData.value.recommended || 0) > 0)
          ? (_openBlock(), _createBlock(_component_VBadge, {
              key: 2,
              class: "magicflow-recommend-wrap",
              content: recommendData.value.recommended,
              color: "error",
              location: "top end",
              "offset-x": "6",
              "offset-y": "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VBtn, {
                  class: "magicflow-recommend-btn",
                  icon: "mdi-movie-star-outline",
                  variant: "text",
                  "aria-label": "推荐",
                  onClick: openRecommend
                })
              ]),
              _: 1
            }, 8, ["content"]))
          : (_openBlock(), _createBlock(_component_VBtn, {
              key: 3,
              class: "magicflow-recommend-btn",
              icon: "mdi-movie-star-outline",
              variant: "text",
              "aria-label": "推荐",
              onClick: openRecommend
            })),
        _createVNode(_component_VBtn, {
          class: "magicflow-cloud-btn",
          icon: "mdi-cloud-upload-outline",
          variant: "text",
          "aria-label": "云盘归档",
          onClick: openCloud
        }),
        (Number(crossseedData.value.count || 0) > 0)
          ? (_openBlock(), _createBlock(_component_VBadge, {
              key: 4,
              class: "magicflow-crossseed-wrap",
              content: crossseedData.value.count,
              color: "info",
              location: "top end",
              "offset-x": "6",
              "offset-y": "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VBtn, {
                  class: "magicflow-crossseed-btn",
                  icon: "mdi-swap-horizontal-bold",
                  variant: "text",
                  "aria-label": "跨站免费取种",
                  onClick: showCrossseed
                })
              ]),
              _: 1
            }, 8, ["content"]))
          : (_openBlock(), _createBlock(_component_VBtn, {
              key: 5,
              class: "magicflow-crossseed-btn",
              icon: "mdi-swap-horizontal-bold",
              variant: "text",
              "aria-label": "跨站免费取种",
              onClick: showCrossseed
            })),
        _createVNode(_component_VBtn, {
          class: "magicflow-douban-btn",
          icon: "mdi-database-search-outline",
          variant: "text",
          color: doubanServiceData.value.ok ? undefined : 'warning',
          "aria-label": `豆瓣评分服务：库 ${doubanServiceData.value.records || 0} 条`,
          title: `豆瓣评分服务：库 ${doubanServiceData.value.records || 0} 条${doubanServiceData.value.ok ? '' : '（不可用）'}`,
          onClick: openDoubanService
        }, null, 8, ["color", "aria-label", "title"]),
        (examData.value.enabled !== false && examBadge.value > 0)
          ? (_openBlock(), _createBlock(_component_VBadge, {
              key: 6,
              class: "magicflow-exam-wrap",
              content: examBadge.value,
              color: examUrgent.value ? 'error' : 'warning',
              location: "top end",
              "offset-x": "6",
              "offset-y": "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VBtn, {
                  class: "magicflow-exam-btn",
                  icon: "mdi-school-outline",
                  variant: "text",
                  "aria-label": "新手考核",
                  onClick: openExam
                })
              ]),
              _: 1
            }, 8, ["content", "color"]))
          : (examData.value.enabled !== false)
            ? (_openBlock(), _createBlock(_component_VBtn, {
                key: 7,
                class: "magicflow-exam-btn",
                icon: "mdi-school-outline",
                variant: "text",
                "aria-label": "新手考核",
                onClick: openExam
              }))
            : _createCommentVNode("", true),
        _createVNode(_component_VBtn, {
          class: "magicflow-settings-btn",
          icon: "mdi-tune-variant",
          variant: "text",
          "aria-label": "插件设置",
          onClick: _cache[0] || (_cache[0] = $event => (openSettings()))
        }),
        (__props.showClose)
          ? (_openBlock(), _createBlock(_component_VBtn, {
              key: 8,
              class: "magicflow-close-btn",
              icon: "mdi-close",
              variant: "text",
              "aria-label": "关闭",
              onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
            }))
          : _createCommentVNode("", true),
        _createVNode(_component_VMenu, {
          location: "bottom end",
          "close-on-content-click": true
        }, {
          activator: _withCtx(({ props: moreProps }) => [
            _createVNode(_component_VBtn, _mergeProps(moreProps, {
              class: "magicflow-more-btn",
              icon: "mdi-dots-vertical",
              variant: "text",
              "aria-label": "更多"
            }), null, 16)
          ]),
          default: _withCtx(() => [
            _createVNode(_component_VList, {
              density: "comfortable",
              class: "magicflow-more-menu",
              "min-width": "210"
            }, {
              default: _withCtx(() => [
                (recommendData.value.enabled !== false)
                  ? (_openBlock(), _createBlock(_component_VListItem, {
                      key: 0,
                      "prepend-icon": "mdi-movie-star-outline",
                      title: "推荐",
                      subtitle: (recommendData.value.recommended || 0) > 0 ? `${recommendData.value.recommended} 个待确认` : '影视推荐甄别',
                      onClick: openRecommend
                    }, null, 8, ["subtitle"]))
                  : _createCommentVNode("", true),
                (examData.value.enabled !== false)
                  ? (_openBlock(), _createBlock(_component_VListItem, {
                      key: 1,
                      "prepend-icon": "mdi-school-outline",
                      title: "新手考核",
                      subtitle: examBadge.value > 0 ? `${examBadge.value} 个未通过` : '考核进度与一键起任务',
                      onClick: openExam
                    }, null, 8, ["subtitle"]))
                  : _createCommentVNode("", true),
                _createVNode(_component_VListItem, {
                  "prepend-icon": "mdi-cloud-upload-outline",
                  title: "云盘归档",
                  onClick: openCloud
                }),
                _cache[199] || (_cache[199] = _createTextVNode()),
                _createVNode(_component_VListItem, {
                  "prepend-icon": "mdi-tune-variant",
                  title: "插件设置",
                  onClick: _cache[2] || (_cache[2] = $event => (openSettings()))
                }),
                (__props.showClose)
                  ? (_openBlock(), _createBlock(_component_VListItem, {
                      key: 2,
                      "prepend-icon": "mdi-close",
                      title: "关闭",
                      onClick: _cache[3] || (_cache[3] = $event => (emit('close')))
                    }))
                  : _createCommentVNode("", true)
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ])
    ]),
    (error.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 0,
          type: "error",
          variant: "tonal",
          closable: "",
          "onClick:close": _cache[4] || (_cache[4] = $event => (error.value = ''))
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(error.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (statusLoaded.value && !status.value.enabled)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 1,
          type: "warning",
          variant: "tonal"
        }, {
          default: _withCtx(() => [...(_cache[200] || (_cache[200] = [
            _createTextVNode(" 插件当前未启用，任务配置与历史仍可查看，启用后才会注册选种刷新和做种检查服务。 ", -1)
          ]))]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (loading.value && !tasks.value.length)
      ? (_openBlock(), _createElementBlock("div", _hoisted_10, [
          _createVNode(_component_VSkeletonLoader, { type: "list-item-three-line, list-item-three-line, article" })
        ]))
      : (!tasks.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_11, [
            _createVNode(_component_VIcon, {
              icon: "mdi-star-four-points-outline",
              size: "52",
              color: "medium-emphasis"
            }),
            _cache[202] || (_cache[202] = _createElementVNode("div", { class: "text-h6" }, "还没有任务", -1)),
            _cache[203] || (_cache[203] = _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "创建任务后可按站点魔力公式养护做种，或按上传产出刷流保种", -1)),
            _createVNode(_component_VBtn, {
              color: "primary",
              variant: "flat",
              "prepend-icon": "mdi-plus",
              onClick: openCreateTask
            }, {
              default: _withCtx(() => [...(_cache[201] || (_cache[201] = [
                _createTextVNode("创建第一个任务", -1)
              ]))]),
              _: 1
            })
          ]))
        : (_openBlock(), _createElementBlock(_Fragment, { key: 4 }, [
            _createElementVNode("div", _hoisted_12, [
              _createVNode(_component_VBtn, {
                class: "magicflow-mobile-back",
                icon: "mdi-arrow-left",
                variant: "text",
                "aria-label": "返回列表",
                onClick: backToMobileList
              }),
              (tasks.value.length > 1)
                ? (_openBlock(), _createBlock(_component_VMenu, {
                    key: 0,
                    "close-on-content-click": true,
                    location: "bottom start"
                  }, {
                    activator: _withCtx(({ props: menuProps }) => [
                      _createElementVNode("button", _mergeProps(menuProps, {
                        type: "button",
                        class: "magicflow-task-switch",
                        "aria-label": `当前任务：${selectedTask.value?.name || ''}`
                      }), [
                        _createElementVNode("span", _hoisted_14, [
                          (taskSiteIcon.value)
                            ? (_openBlock(), _createElementBlock("img", {
                                key: 0,
                                src: taskSiteIcon.value,
                                alt: ""
                              }, null, 8, _hoisted_15))
                            : (_openBlock(), _createBlock(_component_VIcon, {
                                key: 1,
                                icon: "mdi-web",
                                size: "15"
                              }))
                        ]),
                        _createElementVNode("span", _hoisted_16, [
                          _cache[204] || (_cache[204] = _createElementVNode("span", { class: "magicflow-task-switch__k" }, "当前任务", -1)),
                          _createElementVNode("span", _hoisted_17, _toDisplayString(selectedTask.value?.name || '—') + " · " + _toDisplayString(selectedTask.value?.site_name || ''), 1)
                        ]),
                        _createElementVNode("span", {
                          class: _normalizeClass(["magicflow-status-dot", `magicflow-status-dot--${selectedState.value.color}`])
                        }, null, 2),
                        _createVNode(_component_VIcon, {
                          icon: "mdi-chevron-down",
                          size: "18",
                          class: "magicflow-task-switch__chev"
                        })
                      ], 16, _hoisted_13)
                    ]),
                    default: _withCtx(() => [
                      _createVNode(_component_VList, {
                        density: "comfortable",
                        class: "magicflow-task-switch__menu"
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tasks.value, (task) => {
                            return (_openBlock(), _createBlock(_component_VListItem, {
                              key: task.id,
                              title: task.name,
                              subtitle: taskSwitchSubtitle(task),
                              active: task.id === selectedTaskId.value,
                              lines: "two",
                              onClick: $event => (selectTask(task.id))
                            }, {
                              prepend: _withCtx(() => [
                                _createVNode(_component_VIcon, {
                                  icon: taskBadge(task).icon,
                                  color: taskBadge(task).color,
                                  size: "18"
                                }, null, 8, ["icon", "color"])
                              ]),
                              _: 2
                            }, 1032, ["title", "subtitle", "active", "onClick"]))
                          }), 128))
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }))
                : (_openBlock(), _createElementBlock("div", _hoisted_18, [
                    _cache[205] || (_cache[205] = _createElementVNode("span", null, "当前任务", -1)),
                    _createElementVNode("strong", null, _toDisplayString(selectedTask.value?.name || '—'), 1)
                  ])),
              _createVNode(_component_VBtn, {
                class: "magicflow-mobile-add",
                variant: "tonal",
                color: "primary",
                "prepend-icon": "mdi-plus",
                onClick: openCreateTask
              }, {
                default: _withCtx(() => [...(_cache[206] || (_cache[206] = [
                  _createTextVNode(" 新建 ", -1)
                ]))]),
                _: 1
              })
            ]),
            _createElementVNode("div", _hoisted_19, [
              _createElementVNode("div", {
                class: "mh-hero",
                role: "button",
                tabindex: "0",
                onClick: _cache[5] || (_cache[5] = $event => (openCeiling()))
              }, [
                _createElementVNode("div", _hoisted_20, [
                  _createElementVNode("div", _hoisted_21, [
                    _createTextVNode(_toDisplayString(mobileBonus.value), 1),
                    _cache[207] || (_cache[207] = _createElementVNode("small", null, "/h", -1))
                  ]),
                  _createElementVNode("div", _hoisted_22, [
                    _createTextVNode(_toDisplayString(mobileLiveCount.value) + " 个魔力站在跑", 1),
                    (mobileCeilingPct.value > 0)
                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                          _createTextVNode(" · 上限占用 " + _toDisplayString(mobileCeilingPct.value) + "%", 1)
                        ], 64))
                      : _createCommentVNode("", true),
                    (mobileTodayGain.value > 0)
                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                          _createTextVNode(" · 今日 +" + _toDisplayString(mobileTodayGain.value.toFixed(1)), 1)
                        ], 64))
                      : _createCommentVNode("", true)
                  ])
                ]),
                _createVNode(_component_VIcon, {
                  icon: "mdi-chevron-right",
                  size: "22",
                  class: "mh-hero__chev"
                })
              ]),
              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(mobileHomeGroups.value, (g) => {
                return (_openBlock(), _createElementBlock("div", {
                  key: g.key,
                  class: "mh-group"
                }, [
                  _createElementVNode("button", {
                    type: "button",
                    class: "mh-group__head",
                    onClick: $event => (toggleGroup(g.key))
                  }, [
                    _createElementVNode("span", null, _toDisplayString(g.label), 1),
                    _createElementVNode("span", _hoisted_24, _toDisplayString(g.count), 1),
                    _createVNode(_component_VIcon, {
                      icon: isGroupOpen(g.key) ? 'mdi-chevron-up' : 'mdi-chevron-down',
                      size: "18"
                    }, null, 8, ["icon"])
                  ], 8, _hoisted_23),
                  _withDirectives(_createElementVNode("div", _hoisted_25, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(g.sites, (s) => {
                      return (_openBlock(), _createElementBlock(_Fragment, {
                        key: s.key
                      }, [
                        _createElementVNode("button", {
                          type: "button",
                          class: "mh-row",
                          onClick: $event => (openSiteRow(s))
                        }, [
                          _createElementVNode("span", {
                            class: _normalizeClass(["mh-dot", `is-${s.attention ? s.attention.level : taskBadge(s.tasks[0]).color}`])
                          }, null, 2),
                          _createElementVNode("span", _hoisted_27, [
                            _createElementVNode("span", _hoisted_28, [
                              _createTextVNode(_toDisplayString(s.site) + " ", 1),
                              (siteMulti(s))
                                ? (_openBlock(), _createElementBlock("span", _hoisted_29, _toDisplayString(s.tasks.length) + " 任务", 1))
                                : _createCommentVNode("", true)
                            ]),
                            _createElementVNode("span", {
                              class: _normalizeClass(["mh-row__st", { 'is-att': s.attention }])
                            }, _toDisplayString(s.attention ? s.attention.text : mobileRowLine(s.tasks[0])), 3)
                          ]),
                          (s.num)
                            ? (_openBlock(), _createElementBlock("span", _hoisted_30, _toDisplayString(s.num), 1))
                            : _createCommentVNode("", true),
                          _createVNode(_component_VIcon, {
                            icon: siteMulti(s) ? (siteOpen(s.key) ? 'mdi-chevron-up' : 'mdi-chevron-down') : 'mdi-chevron-right',
                            size: "18",
                            class: "mh-row__chev"
                          }, null, 8, ["icon"])
                        ], 8, _hoisted_26),
                        (siteMulti(s))
                          ? _withDirectives((_openBlock(), _createElementBlock("div", _hoisted_31, [
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(s.tasks, (t) => {
                                return (_openBlock(), _createElementBlock("button", {
                                  key: t.id,
                                  type: "button",
                                  class: "mh-subrow",
                                  onClick: $event => (openTaskMobile(t.id))
                                }, [
                                  _createElementVNode("span", {
                                    class: _normalizeClass(["mh-dot", `is-${taskBadge(t).color}`])
                                  }, null, 2),
                                  _createElementVNode("span", _hoisted_33, [
                                    _createElementVNode("span", _hoisted_34, _toDisplayString(t.name), 1)
                                  ]),
                                  (mobileRowNum(t))
                                    ? (_openBlock(), _createElementBlock("span", _hoisted_35, _toDisplayString(mobileRowNum(t)), 1))
                                    : _createCommentVNode("", true)
                                ], 8, _hoisted_32))
                              }), 128))
                            ], 512)), [
                              [_vShow, siteOpen(s.key)]
                            ])
                          : _createCommentVNode("", true)
                      ], 64))
                    }), 128))
                  ], 512), [
                    [_vShow, isGroupOpen(g.key)]
                  ])
                ]))
              }), 128)),
              _cache[210] || (_cache[210] = _createElementVNode("div", { class: "mh-sect" }, "功能", -1)),
              _createElementVNode("div", _hoisted_36, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(MF_PAGES.filter(item => item.key !== 'settings'), (p) => {
                  return (_openBlock(), _createElementBlock("button", {
                    key: p.key,
                    type: "button",
                    class: "mh-tool",
                    onClick: $event => (mfOpenPage(p))
                  }, [
                    _createVNode(_component_VIcon, {
                      icon: p.icon,
                      size: "20"
                    }, null, 8, ["icon"]),
                    _createElementVNode("span", null, [
                      _createTextVNode(_toDisplayString(p.label), 1),
                      (p.scope === 'global')
                        ? (_openBlock(), _createElementBlock("em", _hoisted_38, "全局"))
                        : _createCommentVNode("", true)
                    ])
                  ], 8, _hoisted_37))
                }), 128))
              ]),
              _createElementVNode("div", _hoisted_39, [
                _createElementVNode("button", {
                  type: "button",
                  class: "mh-btn",
                  onClick: openCreateTask
                }, [
                  _createVNode(_component_VIcon, {
                    icon: "mdi-plus",
                    size: "18"
                  }),
                  _cache[208] || (_cache[208] = _createTextVNode("新建任务 ", -1))
                ]),
                _createElementVNode("button", {
                  type: "button",
                  class: "mh-btn mh-btn--ghost",
                  onClick: _cache[6] || (_cache[6] = $event => (openSettings()))
                }, [
                  _createVNode(_component_VIcon, {
                    icon: "mdi-tune-variant",
                    size: "18"
                  }),
                  _cache[209] || (_cache[209] = _createTextVNode("设置 ", -1))
                ])
              ])
            ]),
            _createElementVNode("div", _hoisted_40, [
              _createVNode(_component_VSheet, {
                tag: "aside",
                class: "magicflow-task-rail app-surface-static"
              }, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_41, [
                    _cache[211] || (_cache[211] = _createElementVNode("span", { class: "text-subtitle-2" }, "任务", -1)),
                    _createVNode(_component_VChip, {
                      size: "x-small",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(tasks.value.length), 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _createElementVNode("div", _hoisted_42, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tasks.value, (task) => {
                      return (_openBlock(), _createElementBlock("button", {
                        key: task.id,
                        type: "button",
                        class: _normalizeClass(["magicflow-task-item", { 'magicflow-task-item--selected': task.id === selectedTaskId.value }]),
                        "aria-pressed": task.id === selectedTaskId.value,
                        onClick: $event => (selectTask(task.id))
                      }, [
                        _createElementVNode("span", _hoisted_44, [
                          _createElementVNode("strong", null, _toDisplayString(task.name), 1),
                          (task.builtin)
                            ? (_openBlock(), _createBlock(_component_VChip, {
                                key: 0,
                                size: "x-small",
                                variant: "tonal",
                                color: "primary"
                              }, {
                                default: _withCtx(() => [...(_cache[212] || (_cache[212] = [
                                  _createTextVNode("常驻", -1)
                                ]))]),
                                _: 1
                              }))
                            : _createCommentVNode("", true),
                          _createElementVNode("span", {
                            class: _normalizeClass(["magicflow-status-dot", `magicflow-status-dot--${taskBadge(task).color}`])
                          }, null, 2)
                        ]),
                        _createElementVNode("span", null, _toDisplayString(task.site_name) + " · " + _toDisplayString(task.downloader), 1),
                        _createElementVNode("span", _hoisted_45, [
                          _createElementVNode("span", null, _toDisplayString(task.seeding_count || 0) + " 个种子", 1),
                          (task.task_type === 'brush')
                            ? (_openBlock(), _createElementBlock("span", _hoisted_46, _toDisplayString(_unref(formatBytes)(task.task_uploaded || 0)) + " 上传", 1))
                            : (_openBlock(), _createElementBlock("span", _hoisted_47, _toDisplayString(task.site_bonus_ok ? _unref(formatBonus)(task.site_bonus_per_hour) : '—'), 1))
                        ])
                      ], 10, _hoisted_43))
                    }), 128))
                  ]),
                  _createVNode(_component_VBtn, {
                    class: "magicflow-create-task",
                    block: "",
                    variant: "tonal",
                    "prepend-icon": "mdi-plus",
                    onClick: openCreateTask
                  }, {
                    default: _withCtx(() => [...(_cache[213] || (_cache[213] = [
                      _createTextVNode(" 新建任务 ", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              (selectedTask.value)
                ? (_openBlock(), _createElementBlock("main", _hoisted_48, [
                    _createElementVNode("section", _hoisted_49, [
                      _createElementVNode("div", _hoisted_50, [
                        _createVNode(_component_VAvatar, {
                          color: "primary",
                          variant: "tonal",
                          rounded: "",
                          size: "42",
                          class: "magicflow-task-head__avatar"
                        }, {
                          default: _withCtx(() => [
                            (taskSiteIcon.value)
                              ? (_openBlock(), _createElementBlock("img", {
                                  key: 0,
                                  class: "magicflow-task-head__site-icon",
                                  src: taskSiteIcon.value,
                                  alt: ""
                                }, null, 8, _hoisted_51))
                              : (_openBlock(), _createBlock(_component_VIcon, {
                                  key: 1,
                                  icon: "mdi-web"
                                }))
                          ]),
                          _: 1
                        }),
                        _createElementVNode("div", _hoisted_52, [
                          _createElementVNode("div", _hoisted_53, [
                            _createElementVNode("h2", null, _toDisplayString(selectedTask.value.name), 1),
                            (selectedTask.value.builtin)
                              ? (_openBlock(), _createBlock(_component_VChip, {
                                  key: 0,
                                  size: "small",
                                  variant: "tonal",
                                  color: "primary",
                                  "prepend-icon": "mdi-access-point"
                                }, {
                                  default: _withCtx(() => [...(_cache[214] || (_cache[214] = [
                                    _createTextVNode("常驻", -1)
                                  ]))]),
                                  _: 1
                                }))
                              : (_openBlock(), _createBlock(_component_VChip, {
                                  key: 1,
                                  size: "small",
                                  variant: "tonal",
                                  color: selectedTask.value.task_type === 'brush' ? 'info' : 'primary',
                                  "prepend-icon": selectedTask.value.task_type === 'brush' ? 'mdi-upload-network-outline' : 'mdi-star-four-points-outline'
                                }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(selectedTask.value.task_type === 'brush' ? '刷流' : '刷魔力'), 1)
                                  ]),
                                  _: 1
                                }, 8, ["color", "prepend-icon"])),
                            _createVNode(_component_VChip, {
                              color: selectedState.value.color,
                              size: "small",
                              variant: "tonal",
                              "prepend-icon": selectedState.value.icon
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(selectedState.value.text), 1)
                              ]),
                              _: 1
                            }, 8, ["color", "prepend-icon"])
                          ]),
                          _createElementVNode("p", null, _toDisplayString(selectedTask.value.site_name) + " · 标签「" + _toDisplayString(selectedTask.value.brush_tag || '未设置') + "」", 1)
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_54, [
                        _createVNode(_component_VTooltip, { text: "立即执行" }, {
                          activator: _withCtx(({ props: tipProps }) => [
                            _createVNode(_component_VBtn, _mergeProps(tipProps, {
                              icon: "mdi-sync",
                              variant: "text",
                              loading: saving.value,
                              onClick: runOperation
                            }), null, 16, ["loading"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VTooltip, { text: "刷新数据" }, {
                          activator: _withCtx(({ props: tipProps }) => [
                            _createVNode(_component_VBtn, _mergeProps(tipProps, {
                              icon: "mdi-refresh",
                              variant: "text",
                              onClick: _cache[7] || (_cache[7] = $event => (reloadSelected()))
                            }), null, 16)
                          ]),
                          _: 1
                        }),
                        (!selectedTask.value.builtin)
                          ? (_openBlock(), _createBlock(_component_VMenu, {
                              key: 0,
                              location: "bottom end"
                            }, {
                              activator: _withCtx(({ props: menuProps }) => [
                                _createVNode(_component_VBtn, _mergeProps(menuProps, {
                                  icon: selectedRunMode.value.icon,
                                  color: selectedRunMode.value.color,
                                  variant: "text"
                                }), null, 16, ["icon", "color"])
                              ]),
                              default: _withCtx(() => [
                                _createVNode(_component_VList, {
                                  density: "compact",
                                  "min-width": "248"
                                }, {
                                  default: _withCtx(() => [
                                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(RUN_MODES), (mode) => {
                                      return (_openBlock(), _createBlock(_component_VListItem, {
                                        key: mode.value,
                                        "prepend-icon": mode.icon,
                                        title: mode.text,
                                        subtitle: mode.hint,
                                        active: (selectedTask.value.run_mode || 'running') === mode.value,
                                        onClick: $event => (setRunMode(mode.value))
                                      }, null, 8, ["prepend-icon", "title", "subtitle", "active", "onClick"]))
                                    }), 128))
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }))
                          : _createCommentVNode("", true),
                        (!selectedTask.value.builtin)
                          ? (_openBlock(), _createBlock(_component_VTooltip, {
                              key: 1,
                              text: "编辑任务"
                            }, {
                              activator: _withCtx(({ props: tipProps }) => [
                                _createVNode(_component_VBtn, _mergeProps(tipProps, {
                                  icon: "mdi-pencil-outline",
                                  variant: "text",
                                  onClick: openEditTask
                                }), null, 16)
                              ]),
                              _: 1
                            }))
                          : _createCommentVNode("", true),
                        (!selectedTask.value.builtin)
                          ? (_openBlock(), _createBlock(_component_VTooltip, {
                              key: 2,
                              text: "删除任务"
                            }, {
                              activator: _withCtx(({ props: tipProps }) => [
                                _createVNode(_component_VBtn, _mergeProps(tipProps, {
                                  icon: "mdi-delete-outline",
                                  variant: "text",
                                  color: "error",
                                  onClick: _cache[8] || (_cache[8] = $event => (deleteDialog.value = true))
                                }), null, 16)
                              ]),
                              _: 1
                            }))
                          : _createCommentVNode("", true)
                      ])
                    ]),
                    (!selectedTask.value.builtin)
                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                          _createElementVNode("div", _hoisted_55, [
                            _createElementVNode("div", {
                              class: _normalizeClass(["md-verdict", { 'is-warn': !!detailAttention.value }])
                            }, [
                              _createElementVNode("span", {
                                class: _normalizeClass(["md-dot", `is-${detailAttention.value ? detailAttention.value.level : selectedState.value.color}`])
                              }, null, 2),
                              _createElementVNode("div", _hoisted_56, [
                                _createElementVNode("div", _hoisted_57, [
                                  _createTextVNode(_toDisplayString(detailAttention.value ? detailAttention.value.text : selectedState.value.text), 1),
                                  (!detailAttention.value)
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                        _createTextVNode(" · 无需操作")
                                      ], 64))
                                    : _createCommentVNode("", true)
                                ]),
                                _createElementVNode("div", _hoisted_58, _toDisplayString(detailAttention.value ? detailAttention.value.detail : mobileDetailHint.value), 1)
                              ]),
                              (detailAttention.value)
                                ? (_openBlock(), _createElementBlock("button", {
                                    key: 0,
                                    type: "button",
                                    class: "md-act",
                                    onClick: _cache[9] || (_cache[9] = $event => (activeTab.value = 'diagnostics'))
                                  }, _toDisplayString(detailAttention.value.action), 1))
                                : _createCommentVNode("", true)
                            ], 2),
                            _createElementVNode("div", _hoisted_59, [
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(mobileDetailCards.value, (c) => {
                                return (_openBlock(), _createElementBlock("div", {
                                  key: c.k,
                                  class: "md-card"
                                }, [
                                  _createElementVNode("b", null, _toDisplayString(c.v), 1),
                                  _createElementVNode("span", null, _toDisplayString(c.k), 1)
                                ]))
                              }), 128))
                            ]),
                            _createElementVNode("div", _hoisted_60, _toDisplayString(mobileStrategyText.value), 1),
                            _createElementVNode("div", _hoisted_61, [
                              (_openBlock(), _createElementBlock(_Fragment, null, _renderList(MF_DETAIL_ENTRIES, (e) => {
                                return _createElementVNode("button", {
                                  key: e.key,
                                  type: "button",
                                  class: _normalizeClass(["md-entry", { 'is-active': activeTab.value === e.key }]),
                                  onClick: $event => (mobileDetailEntry(e))
                                }, [
                                  _createVNode(_component_VIcon, {
                                    icon: e.icon,
                                    size: "20"
                                  }, null, 8, ["icon"]),
                                  _createElementVNode("span", null, _toDisplayString(e.label), 1)
                                ], 10, _hoisted_62)
                              }), 64))
                            ])
                          ]),
                          _createElementVNode("div", _hoisted_63, [
                            (_openBlock(), _createElementBlock(_Fragment, null, _renderList(MF_TABS, (tab) => {
                              return _createElementVNode("button", {
                                key: tab.value,
                                type: "button",
                                role: "tab",
                                class: _normalizeClass(["magicflow-tab", { 'is-active': activeTab.value === tab.value }]),
                                "aria-selected": activeTab.value === tab.value,
                                onClick: $event => (activeTab.value = tab.value)
                              }, _toDisplayString(tab.label), 11, _hoisted_64)
                            }), 64))
                          ]),
                          _createVNode(_component_VWindow, {
                            modelValue: activeTab.value,
                            "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((activeTab).value = $event)),
                            touch: false,
                            class: "magicflow-window"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_VWindowItem, {
                                value: "overview",
                                class: "magicflow-window-ov"
                              }, {
                                default: _withCtx(() => [
                                  _createElementVNode("div", _hoisted_65, [
                                    _createVNode(_component_VSheet, { class: "magicflow-stat magicflow-stat--accent app-surface-static" }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("strong", null, _toDisplayString(selectedTask.value.seeding_count || 0), 1),
                                        _createElementVNode("span", null, "托管种子 · " + _toDisplayString(selectedTask.value.active_seeding_count || 0) + " 做种中 / " + _toDisplayString(selectedTask.value.downloading_count || 0) + " 下载中 / " + _toDisplayString(selectedTask.value.paused_count || 0) + " 已暂停", 1)
                                      ]),
                                      _: 1
                                    }),
                                    (taskIsBrush.value)
                                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                          _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                            default: _withCtx(() => [
                                              _createElementVNode("strong", null, _toDisplayString(_unref(formatBytes)(selectedTask.value.task_uploaded || 0)), 1),
                                              _createElementVNode("span", null, "本任务上传量 · 下载器累计（" + _toDisplayString(selectedTask.value.task_upload_active || 0) + " 个有上传）", 1)
                                            ]),
                                            _: 1
                                          }),
                                          _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                            default: _withCtx(() => [
                                              _createElementVNode("strong", null, _toDisplayString(siteAccount.value.ok ? _unref(formatBytes)(siteAccount.value.upload || 0) : '—'), 1),
                                              _createElementVNode("span", null, "站点上传量 · " + _toDisplayString(siteAccount.value.source === 'live' ? '实时（直连站点）' : 'MP 快照') + _toDisplayString(siteAccount.value.ok ? ` · 下载 ${_unref(formatBytes)(siteAccount.value.download || 0)}` : ''), 1)
                                            ]),
                                            _: 1
                                          })
                                        ], 64))
                                      : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                          _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                            default: _withCtx(() => [
                                              _createElementVNode("strong", null, _toDisplayString(selectedTask.value.site_bonus_ok ? _unref(formatBonus)(selectedTask.value.site_bonus_per_hour) : '—'), 1),
                                              _cache[215] || (_cache[215] = _createElementVNode("span", null, "站点上报时魔 · 站点实时值", -1))
                                            ]),
                                            _: 1
                                          }),
                                          _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                            default: _withCtx(() => [
                                              _createElementVNode("strong", null, _toDisplayString(Number(selectedTask.value.site_current_bonus || 0).toFixed(2)), 1),
                                              _cache[216] || (_cache[216] = _createElementVNode("span", null, "站点当前魔力 · 该站点实时存量", -1))
                                            ]),
                                            _: 1
                                          })
                                        ], 64)),
                                    _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_added || 0) + " / " + _toDisplayString(detailStats.value.last_reused || 0) + " / " + _toDisplayString(detailStats.value.last_deleted || 0), 1),
                                        _createElementVNode("span", null, "上次运行 新增/复用/删除 · 当前托管 " + _toDisplayString(detailStats.value.last_kept || selectedTask.value.seeding_count || 0), 1)
                                      ]),
                                      _: 1
                                    })
                                  ]),
                                  ((selectedTask.value.run_mode || 'running') === 'seeding')
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_66, [
                                        _createVNode(_component_VSheet, { class: "magicflow-stat magicflow-stat--accent app-surface-static" }, {
                                          default: _withCtx(() => [
                                            _createElementVNode("strong", null, _toDisplayString(selectedTask.value.protected_count || 0), 1),
                                            _cache[217] || (_cache[217] = _createElementVNode("span", null, "接管保护 · 手动加或 IYUU 回来的种子已纳管并永久保护（不再补种/刷魔力）", -1))
                                          ]),
                                          _: 1
                                        })
                                      ]))
                                    : _createCommentVNode("", true),
                                  _createElementVNode("div", _hoisted_67, [
                                    _createVNode(_component_VSheet, {
                                      tag: "section",
                                      class: "magicflow-panel app-surface-static"
                                    }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("header", _hoisted_68, [
                                          _cache[218] || (_cache[218] = _createElementVNode("div", null, [
                                            _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "运行状态"),
                                            _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "当前任务调度与魔力策略")
                                          ], -1)),
                                          _createVNode(_component_VChip, {
                                            color: selectedState.value.color,
                                            size: "small",
                                            variant: "tonal"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(selectedState.value.text), 1)
                                            ]),
                                            _: 1
                                          }, 8, ["color"])
                                        ]),
                                        _createElementVNode("dl", _hoisted_69, [
                                          _createElementVNode("div", null, [
                                            _cache[219] || (_cache[219] = _createElementVNode("dt", null, "任务目标", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(goalFactText.value), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[220] || (_cache[220] = _createElementVNode("dt", null, "选种周期", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cron_expression || `每 ${taskConfig.value.brush_interval} 分钟`), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[221] || (_cache[221] = _createElementVNode("dt", null, "检查周期", -1)),
                                            _createElementVNode("dd", null, "每 " + _toDisplayString(taskConfig.value.check_interval) + " 分钟", 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[222] || (_cache[222] = _createElementVNode("dt", null, "开启时段", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.active_time_range || '全天'), 1)
                                          ]),
                                          (taskIsBrush.value)
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                _createElementVNode("div", null, [
                                                  _cache[223] || (_cache[223] = _createElementVNode("dt", null, "保种天数", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(brushSeedDays.value > 0 ? `做种满 ${brushSeedDays.value} 天清理` : '不按天数（按无上传）'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[224] || (_cache[224] = _createElementVNode("dt", null, "最小下载人数", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.brush_min_leechers ?? 1) + " 人", 1)
                                                ])
                                              ], 64))
                                            : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                                _createElementVNode("div", null, [
                                                  _cache[225] || (_cache[225] = _createElementVNode("dt", null, "最低魔力", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.value.min_bonus_per_hour).toFixed(2)} /h`), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[226] || (_cache[226] = _createElementVNode("dt", null, "最多保留", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_keep_torrents == null ? (taskConfig.value.disk_size_gb ? `按 ${taskConfig.value.disk_size_gb}GB 自动` : '不限') : `${taskConfig.value.max_keep_torrents} 个`), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[227] || (_cache[227] = _createElementVNode("dt", null, "保护阈值", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.value.bonus_protect_threshold).toFixed(0)), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[228] || (_cache[228] = _createElementVNode("dt", null, "完美种保护", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.protect_perfect === false ? '关闭' : `开启（≤${taskConfig.value.perfect_max_seeders ?? 3}人 · ≥${taskConfig.value.perfect_min_weeks ?? 4}周）`), 1)
                                                ])
                                              ], 64)),
                                          _createElementVNode("div", null, [
                                            _cache[229] || (_cache[229] = _createElementVNode("dt", null, "自动补种", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.refill_when_empty ? '开启' : '关闭'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[230] || (_cache[230] = _createElementVNode("dt", null, "存量复用", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.reuse_existing ? '开启' : '关闭'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[231] || (_cache[231] = _createElementVNode("dt", null, "无进度清理", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_no_progress ? `开启（${taskConfig.value.no_progress_minutes ?? 30} 分钟）` : '关闭'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[232] || (_cache[232] = _createElementVNode("dt", null, "慢速清理", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.value.slow_progress_max_hours ?? 48}h 下不完即清）`), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[233] || (_cache[233] = _createElementVNode("dt", null, "促销失效清理", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[234] || (_cache[234] = _createElementVNode("dt", null, "自动恢复暂停", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.auto_resume_paused === false ? '关闭' : '开启'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[235] || (_cache[235] = _createElementVNode("dt", null, "选种来源", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.rss_support ? 'RSS' : '站点列表页'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[236] || (_cache[236] = _createElementVNode("dt", null, "促销要求", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskIsBrush.value ? '免费（含 2X免费）' : (taskConfig.value.freeleech === '2xfree' ? '2X 免费' : taskConfig.value.freeleech === 'free' ? '免费' : '全部')), 1)
                                          ])
                                        ])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode(_component_VSheet, {
                                      tag: "section",
                                      class: "magicflow-panel app-surface-static"
                                    }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("header", _hoisted_70, [
                                          _createElementVNode("div", null, [
                                            _cache[237] || (_cache[237] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "站点数据", -1)),
                                            _createElementVNode("div", _hoisted_71, [
                                              (siteAccount.value.source === 'live')
                                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                    _createTextVNode("魔流直连站点用户栏（实时）" + _toDisplayString(siteAccount.value.sampledAt ? ` · 采样于 ${siteAccount.value.sampledAt}` : ''), 1)
                                                  ], 64))
                                                : (siteAccount.value.source === 'mp')
                                                  ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                                      _createTextVNode("MoviePilot 站点数据快照（默认 6 小时一轮）" + _toDisplayString(siteUser.value.updated_at ? ` · 更新于 ${siteUser.value.updated_at}` : ''), 1)
                                                    ], 64))
                                                  : (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                                                      _createTextVNode("暂无站点数据")
                                                    ], 64))
                                            ])
                                          ]),
                                          (siteAccount.value.source === 'live')
                                            ? (_openBlock(), _createBlock(_component_VChip, {
                                                key: 0,
                                                size: "small",
                                                variant: "tonal",
                                                color: siteLiveLevel.value === 'warn' ? 'warning' : 'success'
                                              }, {
                                                default: _withCtx(() => [
                                                  _createTextVNode(_toDisplayString(siteLiveLevel.value === 'warn' ? '实时 · 有告警' : '实时'), 1)
                                                ]),
                                                _: 1
                                              }, 8, ["color"]))
                                            : (siteAccount.value.source === 'mp')
                                              ? (_openBlock(), _createBlock(_component_VChip, {
                                                  key: 1,
                                                  size: "small",
                                                  variant: "tonal"
                                                }, {
                                                  default: _withCtx(() => [...(_cache[238] || (_cache[238] = [
                                                    _createTextVNode("MP 快照", -1)
                                                  ]))]),
                                                  _: 1
                                                }))
                                              : (_openBlock(), _createBlock(_component_VChip, {
                                                  key: 2,
                                                  size: "small",
                                                  variant: "tonal"
                                                }, {
                                                  default: _withCtx(() => [...(_cache[239] || (_cache[239] = [
                                                    _createTextVNode("暂无数据", -1)
                                                  ]))]),
                                                  _: 1
                                                }))
                                        ]),
                                        _createElementVNode("dl", _hoisted_72, [
                                          _createElementVNode("div", null, [
                                            _cache[240] || (_cache[240] = _createElementVNode("dt", null, "上传量", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(siteAccount.value.ok ? _unref(formatBytes)(siteAccount.value.upload || 0) : '—'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[241] || (_cache[241] = _createElementVNode("dt", null, "下载量", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(siteAccount.value.ok ? _unref(formatBytes)(siteAccount.value.download || 0) : '—'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[242] || (_cache[242] = _createElementVNode("dt", null, "分享率", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(siteAccount.value.ok && siteAccount.value.ratio != null ? Number(siteAccount.value.ratio).toFixed(3) : '—'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[243] || (_cache[243] = _createElementVNode("dt", null, "做种数 / 下载数", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(siteAccount.value.ok ? `${siteAccount.value.seeding ?? '—'} / ${siteAccount.value.leeching ?? '—'}` : '—'), 1)
                                          ]),
                                          (siteAccount.value.seeding_size)
                                            ? (_openBlock(), _createElementBlock("div", _hoisted_73, [
                                                _cache[244] || (_cache[244] = _createElementVNode("dt", null, "做种体积", -1)),
                                                _createElementVNode("dd", null, _toDisplayString(_unref(formatBytes)(siteAccount.value.seeding_size)), 1)
                                              ]))
                                            : _createCommentVNode("", true),
                                          _createElementVNode("div", null, [
                                            _cache[245] || (_cache[245] = _createElementVNode("dt", null, "站点魔力", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(siteAccount.value.ok && siteAccount.value.bonus != null ? Number(siteAccount.value.bonus).toFixed(2) : '—') + _toDisplayString(siteAccount.value.bonus_per_hour != null ? ` · ${Number(siteAccount.value.bonus_per_hour).toFixed(2)}/h` : ''), 1)
                                          ]),
                                          (siteAccount.value.source === 'live')
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                                _createElementVNode("div", null, [
                                                  _cache[246] || (_cache[246] = _createElementVNode("dt", null, "上传速率", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(siteLiveRates.value.ok ? `${Number(siteLiveRates.value.up_mb_min || 0).toFixed(1)} MB/分` : '采样中'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[247] || (_cache[247] = _createElementVNode("dt", null, "下载速率", -1)),
                                                  _createElementVNode("dd", {
                                                    class: _normalizeClass({ 'text-error': (siteLiveRates.value.down_mb_min || 0) >= (siteLiveCfg.value.download_alert_mb || 50) })
                                                  }, _toDisplayString(siteLiveRates.value.ok ? `${Number(siteLiveRates.value.down_mb_min || 0).toFixed(1)} MB/分` : '采样中'), 3)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[248] || (_cache[248] = _createElementVNode("dt", null, "近 1h 净增", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(siteLiveRates.value.ok ? `⬆ ${_unref(formatBytes)(Math.max(0, siteLiveRates.value.d_up || 0))} / ⬇ ${_unref(formatBytes)(Math.max(0, siteLiveRates.value.d_down || 0))}` : '—'), 1)
                                                ])
                                              ], 64))
                                            : _createCommentVNode("", true)
                                        ]),
                                        (siteLiveAlerts.value.length)
                                          ? (_openBlock(), _createElementBlock("div", _hoisted_74, [
                                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(siteLiveAlerts.value, (alert, idx) => {
                                                return (_openBlock(), _createElementBlock("div", {
                                                  key: `${alert.kind}-${idx}`,
                                                  class: _normalizeClass(["magicflow-live-alert", `magicflow-live-alert--${alert.level || 'info'}`])
                                                }, _toDisplayString(alert.text), 3))
                                              }), 128))
                                            ]))
                                          : _createCommentVNode("", true)
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode(_component_VSheet, {
                                      tag: "section",
                                      class: "magicflow-panel app-surface-static"
                                    }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("header", _hoisted_75, [
                                          _createElementVNode("div", null, [
                                            _cache[249] || (_cache[249] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "最近一次运行", -1)),
                                            _createElementVNode("div", _hoisted_76, _toDisplayString(detailStats.value.last_run_at ? _unref(formatDateTime)(detailStats.value.last_run_at) : '暂无运行记录'), 1)
                                          ]),
                                          (detailStats.value.last_error)
                                            ? (_openBlock(), _createBlock(_component_VChip, {
                                                key: 0,
                                                color: "error",
                                                size: "small",
                                                variant: "tonal"
                                              }, {
                                                default: _withCtx(() => [...(_cache[250] || (_cache[250] = [
                                                  _createTextVNode("失败", -1)
                                                ]))]),
                                                _: 1
                                              }))
                                            : (detailStats.value.last_run_status)
                                              ? (_openBlock(), _createBlock(_component_VChip, {
                                                  key: 1,
                                                  color: detailStats.value.last_run_status === 'done' ? 'success' : detailStats.value.last_run_status === 'failed' ? 'error' : 'secondary',
                                                  size: "small",
                                                  variant: "tonal"
                                                }, {
                                                  default: _withCtx(() => [
                                                    _createTextVNode(_toDisplayString(_unref(runStatusText)(detailStats.value.last_run_status)), 1)
                                                  ]),
                                                  _: 1
                                                }, 8, ["color"]))
                                              : (detailStats.value.last_success_at)
                                                ? (_openBlock(), _createBlock(_component_VChip, {
                                                    key: 2,
                                                    color: "success",
                                                    size: "small",
                                                    variant: "tonal"
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[251] || (_cache[251] = [
                                                      _createTextVNode("完成", -1)
                                                    ]))]),
                                                    _: 1
                                                  }))
                                                : _createCommentVNode("", true)
                                        ]),
                                        _createElementVNode("div", _hoisted_77, [
                                          _createElementVNode("div", null, [
                                            _cache[252] || (_cache[252] = _createElementVNode("span", null, "上次成功", -1)),
                                            _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_success_at ? _unref(formatDateTime)(detailStats.value.last_success_at) : '-'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[253] || (_cache[253] = _createElementVNode("span", null, "本次状态", -1)),
                                            _createElementVNode("strong", null, _toDisplayString(_unref(runStatusText)(detailStats.value.last_run_status)), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[254] || (_cache[254] = _createElementVNode("span", null, "本次耗时", -1)),
                                            _createElementVNode("strong", null, _toDisplayString(_unref(formatDurationSeconds)(detailStats.value.last_run_duration)), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[255] || (_cache[255] = _createElementVNode("span", null, "本次新增 / 复用", -1)),
                                            _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_added || 0) + " / " + _toDisplayString(detailStats.value.last_reused || 0), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[256] || (_cache[256] = _createElementVNode("span", null, "本次删除", -1)),
                                            _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_deleted || 0), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[257] || (_cache[257] = _createElementVNode("span", null, "慢扫辅种（累计 / 本次）", -1)),
                                            _createElementVNode("strong", null, _toDisplayString(detailStats.value.cumulative_slow_reused || 0) + " / " + _toDisplayString(detailStats.value.last_slow_reused || 0), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[258] || (_cache[258] = _createElementVNode("span", null, "当前托管 / 受保护", -1)),
                                            _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_kept || 0) + " / " + _toDisplayString(detailStats.value.protected_count || 0), 1)
                                          ])
                                        ]),
                                        (detailStats.value.last_run_reason)
                                          ? (_openBlock(), _createBlock(_component_VAlert, {
                                              key: 0,
                                              type: "info",
                                              variant: "tonal",
                                              density: "compact",
                                              class: "mb-2"
                                            }, {
                                              default: _withCtx(() => [
                                                _createTextVNode(" 本轮说明：" + _toDisplayString(detailStats.value.last_run_reason), 1)
                                              ]),
                                              _: 1
                                            }))
                                          : _createCommentVNode("", true),
                                        (detailStats.value.last_error)
                                          ? (_openBlock(), _createBlock(_component_VAlert, {
                                              key: 1,
                                              type: "error",
                                              variant: "tonal",
                                              density: "compact"
                                            }, {
                                              default: _withCtx(() => [
                                                _createTextVNode(_toDisplayString(detailStats.value.last_error), 1)
                                              ]),
                                              _: 1
                                            }))
                                          : _createCommentVNode("", true),
                                        _createVNode(_component_VBtn, {
                                          variant: "text",
                                          color: "primary",
                                          "append-icon": "mdi-arrow-right",
                                          onClick: _cache[10] || (_cache[10] = $event => (activeTab.value = 'diagnostics'))
                                        }, {
                                          default: _withCtx(() => [...(_cache[259] || (_cache[259] = [
                                            _createTextVNode(" 查看运行诊断 ", -1)
                                          ]))]),
                                          _: 1
                                        })
                                      ]),
                                      _: 1
                                    })
                                  ])
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VWindowItem, { value: "diagnostics" }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_VSheet, {
                                    tag: "section",
                                    class: "magicflow-panel magicflow-flow app-surface-static"
                                  }, {
                                    default: _withCtx(() => [
                                      _createElementVNode("header", _hoisted_78, [
                                        _createElementVNode("div", null, [
                                          _cache[260] || (_cache[260] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "运行流程", -1)),
                                          _createElementVNode("div", _hoisted_79, [
                                            _createTextVNode(_toDisplayString(detailStats.value.run_active ? (taskIsBrush.value ? '正在执行本轮刷流…' : '正在执行本轮养护…') : (detailStats.value.last_run_at ? `最近执行 ${_unref(formatDateTime)(detailStats.value.last_run_at)}` : '尚未运行')) + " · 翻页游标 " + _toDisplayString(detailStats.value.page_cursor ?? 0), 1),
                                            (detailStats.value.last_phase_detail)
                                              ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                  _createTextVNode(" · " + _toDisplayString(detailStats.value.last_phase_detail), 1)
                                                ], 64))
                                              : _createCommentVNode("", true)
                                          ])
                                        ]),
                                        _createElementVNode("span", {
                                          class: _normalizeClass(["magicflow-flow__tag", { 'is-live': detailStats.value.run_active, 'is-error': detailStats.value.last_run_status === 'failed' }])
                                        }, [
                                          _cache[261] || (_cache[261] = _createElementVNode("i", null, null, -1)),
                                          _createTextVNode(" " + _toDisplayString(flowPhaseText.value), 1)
                                        ], 2)
                                      ]),
                                      _createElementVNode("ol", _hoisted_80, [
                                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(flowNodes.value, (node, i) => {
                                          return (_openBlock(), _createElementBlock("li", {
                                            key: node.key,
                                            class: _normalizeClass(["magicflow-flow__node", `is-${node.state}`])
                                          }, [
                                            _createElementVNode("span", _hoisted_81, [
                                              (node.state === 'done' || node.state === 'running')
                                                ? (_openBlock(), _createBlock(_component_VIcon, {
                                                    key: 0,
                                                    icon: "mdi-check",
                                                    size: "16"
                                                  }))
                                                : (node.state === 'error')
                                                  ? (_openBlock(), _createBlock(_component_VIcon, {
                                                      key: 1,
                                                      icon: "mdi-alert",
                                                      size: "16"
                                                    }))
                                                  : _createCommentVNode("", true)
                                            ]),
                                            _createElementVNode("span", _hoisted_82, _toDisplayString(node.label), 1),
                                            (i < flowNodes.value.length - 1)
                                              ? (_openBlock(), _createElementBlock("span", {
                                                  key: 0,
                                                  class: _normalizeClass(["magicflow-flow__line", { 'is-done': node.state === 'done' }])
                                                }, null, 2))
                                              : _createCommentVNode("", true)
                                          ], 2))
                                        }), 128))
                                      ]),
                                      (detailStats.value.last_error)
                                        ? (_openBlock(), _createBlock(_component_VAlert, {
                                            key: 0,
                                            type: "error",
                                            variant: "tonal",
                                            density: "compact",
                                            class: "mt-3"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(detailStats.value.last_error), 1)
                                            ]),
                                            _: 1
                                          }))
                                        : _createCommentVNode("", true)
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_VSheet, {
                                    tag: "section",
                                    class: "magicflow-panel app-surface-static mt-4"
                                  }, {
                                    default: _withCtx(() => [
                                      _createElementVNode("header", _hoisted_83, [
                                        _createElementVNode("div", null, [
                                          _cache[262] || (_cache[262] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "过滤原因", -1)),
                                          _createElementVNode("div", _hoisted_84, [
                                            _createTextVNode(" 被规则拦截的候选分布 · 共抓取 " + _toDisplayString(candidateRawTotal.value) + " 个，通过 " + _toDisplayString((candidateData.value.candidates || []).length) + " ", 1),
                                            (candidateLoadedAt.value)
                                              ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                  _createTextVNode(" · 统计于 " + _toDisplayString(_unref(formatDateTime)(candidateLoadedAt.value)), 1)
                                                ], 64))
                                              : _createCommentVNode("", true)
                                          ])
                                        ])
                                      ]),
                                      (reasonEntries.value.length)
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_85, [
                                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(reasonEntries.value, (item) => {
                                              return (_openBlock(), _createElementBlock("div", {
                                                key: item.label,
                                                class: "magicflow-reason"
                                              }, [
                                                _createElementVNode("div", null, [
                                                  _createElementVNode("span", null, _toDisplayString(item.label), 1),
                                                  _createElementVNode("strong", null, _toDisplayString(item.count), 1)
                                                ]),
                                                _createElementVNode("span", _hoisted_86, [
                                                  _createElementVNode("i", {
                                                    style: _normalizeStyle({ width: `${(item.count / maxReasonCount.value) * 100}%` })
                                                  }, null, 4)
                                                ])
                                              ]))
                                            }), 128))
                                          ]))
                                        : (_openBlock(), _createElementBlock("div", _hoisted_87, "本轮没有记录过滤原因（候选全部通过或列表为空）")),
                                      (detailStats.value.last_run_status === 'noop' && detailStats.value.last_run_reason)
                                        ? (_openBlock(), _createBlock(_component_VAlert, {
                                            key: 2,
                                            type: "info",
                                            variant: "tonal",
                                            density: "compact",
                                            class: "mt-3"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(" 最近一次执行未进入候选过滤：" + _toDisplayString(detailStats.value.last_run_reason), 1)
                                            ]),
                                            _: 1
                                          }))
                                        : _createCommentVNode("", true)
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_VSheet, {
                                    tag: "section",
                                    class: "magicflow-panel app-surface-static mt-4"
                                  }, {
                                    default: _withCtx(() => [
                                      _createElementVNode("header", _hoisted_88, [
                                        _cache[264] || (_cache[264] = _createElementVNode("div", null, [
                                          _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "操作记录"),
                                          _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "每次执行 / 选种 / 删种 / 保护 / 标签 的流水（可展开明细）")
                                        ], -1)),
                                        _createVNode(_component_VBtn, {
                                          variant: "text",
                                          color: "primary",
                                          "prepend-icon": "mdi-refresh",
                                          onClick: _cache[11] || (_cache[11] = $event => (loadOperations(selectedTaskId.value)))
                                        }, {
                                          default: _withCtx(() => [...(_cache[263] || (_cache[263] = [
                                            _createTextVNode("刷新", -1)
                                          ]))]),
                                          _: 1
                                        })
                                      ]),
                                      _createElementVNode("div", _hoisted_89, [
                                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(operationData.value.operations || [], (record) => {
                                          return (_openBlock(), _createElementBlock("article", {
                                            key: record.operation_id
                                          }, [
                                            _createVNode(_component_VIcon, {
                                              icon: operationIcon(record.kind),
                                              color: operationColor(record)
                                            }, null, 8, ["icon", "color"]),
                                            _createElementVNode("div", null, [
                                              _createElementVNode("strong", null, [
                                                _createTextVNode(_toDisplayString(operationKindText(record.kind)) + " ", 1),
                                                _createVNode(_component_VChip, {
                                                  size: "x-small",
                                                  variant: "tonal",
                                                  color: operationColor(record),
                                                  class: "ml-2"
                                                }, {
                                                  default: _withCtx(() => [
                                                    _createTextVNode(_toDisplayString(operationStateText(record.state)), 1)
                                                  ]),
                                                  _: 2
                                                }, 1032, ["color"])
                                              ]),
                                              _createElementVNode("span", null, _toDisplayString(operationSummary(record)), 1),
                                              _createElementVNode("span", null, [
                                                _createTextVNode(_toDisplayString(_unref(formatDateTime)(record.created_at)) + " · 耗时 " + _toDisplayString(operationDuration(record)) + " ", 1),
                                                (hasOpDetail(record))
                                                  ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                      _createTextVNode(" · " + _toDisplayString(opDetailItems(record).length) + " 条明细", 1)
                                                    ], 64))
                                                  : _createCommentVNode("", true)
                                              ]),
                                              (record.error_message)
                                                ? (_openBlock(), _createElementBlock("span", _hoisted_90, _toDisplayString(record.error_message), 1))
                                                : _createCommentVNode("", true),
                                              (hasOpDetail(record))
                                                ? (_openBlock(), _createElementBlock("button", {
                                                    key: 1,
                                                    type: "button",
                                                    class: "magicflow-events__toggle",
                                                    onClick: $event => (toggleOpDetail(record.operation_id))
                                                  }, [
                                                    _createTextVNode(_toDisplayString(isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细') + " ", 1),
                                                    _createVNode(_component_VIcon, {
                                                      icon: isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down',
                                                      size: "14"
                                                    }, null, 8, ["icon"])
                                                  ], 8, _hoisted_91))
                                                : _createCommentVNode("", true),
                                              (isOpDetailOpen(record.operation_id))
                                                ? (_openBlock(), _createElementBlock("ul", _hoisted_92, [
                                                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(opDetailItems(record), (it, idx) => {
                                                      return (_openBlock(), _createElementBlock("li", { key: idx }, [
                                                        _createElementVNode("span", _hoisted_93, [
                                                          (itemSourceText(it.source))
                                                            ? (_openBlock(), _createElementBlock("em", _hoisted_94, _toDisplayString(itemSourceText(it.source)), 1))
                                                            : _createCommentVNode("", true),
                                                          _createElementVNode("span", {
                                                            class: "magicflow-events__detail-title",
                                                            title: it.title || it.hash
                                                          }, _toDisplayString(it.title || it.hash || '—'), 9, _hoisted_95)
                                                        ]),
                                                        _createElementVNode("span", _hoisted_96, [
                                                          (it.reason)
                                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                                _createTextVNode(_toDisplayString(it.reason), 1)
                                                              ], 64))
                                                            : _createCommentVNode("", true),
                                                          (it.size_gb)
                                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                                                _createTextVNode(" · " + _toDisplayString(Number(it.size_gb).toFixed(2)) + "G", 1)
                                                              ], 64))
                                                            : _createCommentVNode("", true),
                                                          (it.seeders)
                                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                                                                _createTextVNode(" · 做种 " + _toDisplayString(it.seeders), 1)
                                                              ], 64))
                                                            : _createCommentVNode("", true)
                                                        ])
                                                      ]))
                                                    }), 128))
                                                  ]))
                                                : _createCommentVNode("", true)
                                            ])
                                          ]))
                                        }), 128)),
                                        (!(operationData.value.operations || []).length)
                                          ? (_openBlock(), _createElementBlock("div", _hoisted_97, "暂无操作记录"))
                                          : _createCommentVNode("", true)
                                      ])
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VWindowItem, { value: "pool" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("div", _hoisted_98, [
                                    _createElementVNode("div", null, [
                                      _cache[265] || (_cache[265] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "种子池", -1)),
                                      _createElementVNode("div", _hoisted_99, [
                                        (poolView.value === 'candidates')
                                          ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                              _createTextVNode(" 待办队列 · 共 " + _toDisplayString(candidateData.value.total || 0) + " 个通过过滤 ", 1)
                                            ], 64))
                                          : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                              _createTextVNode(" 已托管：共 " + _toDisplayString(bonusData.value.torrent_count || 0) + " 个 ", 1)
                                            ], 64))
                                      ])
                                    ]),
                                    _createElementVNode("div", _hoisted_100, [
                                      _createVNode(_component_VBtnToggle, {
                                        "model-value": poolView.value,
                                        mandatory: "",
                                        color: "primary",
                                        density: "compact",
                                        "onUpdate:modelValue": _cache[12] || (_cache[12] = value => (poolView.value = value))
                                      }, {
                                        default: _withCtx(() => [
                                          _createVNode(_component_VBtn, {
                                            value: "candidates",
                                            "prepend-icon": "mdi-filter-variant"
                                          }, {
                                            default: _withCtx(() => [...(_cache[266] || (_cache[266] = [
                                              _createTextVNode("候选", -1)
                                            ]))]),
                                            _: 1
                                          }),
                                          _createVNode(_component_VBtn, {
                                            value: "torrents",
                                            "prepend-icon": "mdi-seed-outline"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode("托管（" + _toDisplayString(bonusData.value.torrent_count || 0) + "）", 1)
                                            ]),
                                            _: 1
                                          })
                                        ]),
                                        _: 1
                                      }, 8, ["model-value"]),
                                      (poolView.value === 'torrents')
                                        ? (_openBlock(), _createBlock(_component_VBtn, {
                                            key: 0,
                                            size: "small",
                                            variant: "tonal",
                                            color: "primary",
                                            "prepend-icon": "mdi-link-variant-plus",
                                            loading: backfilling.value,
                                            onClick: backfillPages
                                          }, {
                                            default: _withCtx(() => [...(_cache[267] || (_cache[267] = [
                                              _createTextVNode("回填链接", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["loading"]))
                                        : _createCommentVNode("", true)
                                    ])
                                  ]),
                                  (poolView.value === 'candidates')
                                    ? (_openBlock(), _createBlock(_component_VSheet, {
                                        key: 0,
                                        tag: "section",
                                        class: "magicflow-panel app-surface-static"
                                      }, {
                                        default: _withCtx(() => [
                                          _createElementVNode("header", _hoisted_101, [
                                            _createElementVNode("div", null, [
                                              _cache[268] || (_cache[268] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "候选排行", -1)),
                                              _createElementVNode("div", _hoisted_102, _toDisplayString(taskIsBrush.value ? '按上传潜力（下载人数）排序 · 仅供选种参考' : '待办名次由站点魔力效率内部排序 · 仅供选种参考'), 1)
                                            ])
                                          ]),
                                          _createElementVNode("ol", _hoisted_103, [
                                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList((candidateData.value.candidates || []).slice(0, 8), (candidate) => {
                                              return (_openBlock(), _createElementBlock("li", {
                                                key: candidate.hash
                                              }, [
                                                _createElementVNode("span", _hoisted_104, _toDisplayString(candidate.rank), 1),
                                                _createElementVNode("div", null, [
                                                  _createElementVNode("strong", null, _toDisplayString(candidate.title || '未知种子'), 1),
                                                  _createElementVNode("span", null, _toDisplayString(Number(candidate.size_gb || 0).toFixed(2)) + " GB · " + _toDisplayString(candidate.seeders) + " 做种 · " + _toDisplayString(candidate.leechers) + " 下载 · " + _toDisplayString(Number(candidate.age_weeks || 0).toFixed(1)) + " 周", 1)
                                                ])
                                              ]))
                                            }), 128)),
                                            (!(candidateData.value.candidates || []).length)
                                              ? (_openBlock(), _createElementBlock("li", _hoisted_105, [...(_cache[269] || (_cache[269] = [
                                                  _createElementVNode("div", { class: "magicflow-table-empty" }, "暂无候选", -1)
                                                ]))]))
                                              : _createCommentVNode("", true)
                                          ])
                                        ]),
                                        _: 1
                                      }))
                                    : (_openBlock(), _createBlock(_component_VSheet, {
                                        key: 1,
                                        tag: "section",
                                        class: "magicflow-panel magicflow-torrents app-surface-static"
                                      }, {
                                        default: _withCtx(() => [
                                          _createElementVNode("header", _hoisted_106, [
                                            _cache[272] || (_cache[272] = _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, " 点击任意行查看详情 / 手动保留 / 删除 ", -1)),
                                            _createElementVNode("div", _hoisted_107, [
                                              _createVNode(_component_VSelect, {
                                                modelValue: torrentStatusFilter.value,
                                                "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((torrentStatusFilter).value = $event)),
                                                items: torrentStatusOptions.value,
                                                "item-title": "title",
                                                "item-value": "value",
                                                density: "compact",
                                                variant: "outlined",
                                                "hide-details": "",
                                                class: "magicflow-status-filter"
                                              }, null, 8, ["modelValue", "items"]),
                                              _createVNode(_component_VBtnToggle, {
                                                "model-value": torrentFilter.value,
                                                mandatory: "",
                                                color: "primary",
                                                density: "compact",
                                                "onUpdate:modelValue": _cache[14] || (_cache[14] = value => (torrentFilter.value = value))
                                              }, {
                                                default: _withCtx(() => [
                                                  _createVNode(_component_VBtn, { value: "all" }, {
                                                    default: _withCtx(() => [...(_cache[270] || (_cache[270] = [
                                                      _createTextVNode("全部", -1)
                                                    ]))]),
                                                    _: 1
                                                  }),
                                                  _createVNode(_component_VBtn, { value: "protected" }, {
                                                    default: _withCtx(() => [...(_cache[271] || (_cache[271] = [
                                                      _createTextVNode("已保护", -1)
                                                    ]))]),
                                                    _: 1
                                                  })
                                                ]),
                                                _: 1
                                              }, 8, ["model-value"])
                                            ])
                                          ]),
                                          (selectedHashes.value.length)
                                            ? (_openBlock(), _createElementBlock("div", _hoisted_108, [
                                                _createElementVNode("span", _hoisted_109, "已选 " + _toDisplayString(selectedHashes.value.length) + " 个", 1),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "tonal",
                                                  disabled: batchBusy.value,
                                                  onClick: _cache[15] || (_cache[15] = $event => (batchAction('protect')))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[273] || (_cache[273] = [
                                                    _createTextVNode("保留", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "tonal",
                                                  disabled: batchBusy.value,
                                                  onClick: _cache[16] || (_cache[16] = $event => (batchAction('unprotect')))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[274] || (_cache[274] = [
                                                    _createTextVNode("取消保留", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "tonal",
                                                  disabled: batchBusy.value,
                                                  onClick: _cache[17] || (_cache[17] = $event => (batchAction('pause')))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[275] || (_cache[275] = [
                                                    _createTextVNode("暂停", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "tonal",
                                                  disabled: batchBusy.value,
                                                  onClick: _cache[18] || (_cache[18] = $event => (batchAction('resume')))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[276] || (_cache[276] = [
                                                    _createTextVNode("恢复", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "tonal",
                                                  disabled: batchBusy.value,
                                                  onClick: _cache[19] || (_cache[19] = $event => (batchAction('recheck')))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[277] || (_cache[277] = [
                                                    _createTextVNode("校验", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "tonal",
                                                  color: "primary",
                                                  disabled: batchBusy.value,
                                                  onClick: openTransfer
                                                }, {
                                                  default: _withCtx(() => [...(_cache[278] || (_cache[278] = [
                                                    _createTextVNode("批量转移", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "tonal",
                                                  color: "error",
                                                  disabled: batchBusy.value,
                                                  onClick: _cache[20] || (_cache[20] = $event => (batchDeleteDialog.value = true))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[279] || (_cache[279] = [
                                                    _createTextVNode("删除", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled"]),
                                                _createVNode(_component_VSpacer),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "text",
                                                  disabled: batchBusy.value,
                                                  onClick: selectAllFiltered
                                                }, {
                                                  default: _withCtx(() => [
                                                    _createTextVNode("全选筛选（" + _toDisplayString(sortedTorrents.value.length) + "）", 1)
                                                  ]),
                                                  _: 1
                                                }, 8, ["disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  size: "small",
                                                  variant: "text",
                                                  disabled: batchBusy.value,
                                                  onClick: clearSelection
                                                }, {
                                                  default: _withCtx(() => [...(_cache[280] || (_cache[280] = [
                                                    _createTextVNode("取消选择", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled"])
                                              ]))
                                            : _createCommentVNode("", true),
                                          _createVNode(_component_VDataTable, {
                                            class: "magicflow-torrent-table torrent-table-clickable",
                                            headers: torrentHeaders,
                                            items: sortedTorrents.value,
                                            loading: taskLoading.value,
                                            "items-per-page": 10,
                                            density: "comfortable",
                                            "onClick:row": onTorrentRowClick
                                          }, {
                                            "header.select": _withCtx(() => [
                                              _createVNode(_component_VCheckbox, {
                                                "model-value": allFilteredSelected.value,
                                                indeterminate: selectedHashes.value.length > 0 && !allFilteredSelected.value,
                                                density: "compact",
                                                "hide-details": "",
                                                "aria-label": "全选",
                                                "onUpdate:modelValue": _cache[21] || (_cache[21] = value => (value ? selectAllFiltered() : clearSelection()))
                                              }, null, 8, ["model-value", "indeterminate"])
                                            ]),
                                            "item.select": _withCtx(({ item }) => [
                                              _createVNode(_component_VCheckbox, {
                                                "model-value": selectedHashes.value.includes(item.hash),
                                                density: "compact",
                                                "hide-details": "",
                                                "aria-label": `选择 ${item.title || ''}`,
                                                onClick: _cache[22] || (_cache[22] = _withModifiers(() => {}, ["stop"])),
                                                "onUpdate:modelValue": $event => (toggleTorrentSelection(item))
                                              }, null, 8, ["model-value", "aria-label", "onUpdate:modelValue"])
                                            ]),
                                            "item.title": _withCtx(({ item }) => [
                                              _createElementVNode("div", _hoisted_110, [
                                                _createElementVNode("strong", null, _toDisplayString(item.title || '未知种子'), 1),
                                                _createElementVNode("span", null, _toDisplayString(selectedTask.value.site_name), 1)
                                              ])
                                            ]),
                                            "item.status": _withCtx(({ item }) => [
                                              _createVNode(_component_VChip, {
                                                size: "small",
                                                color: stateColor(item.state),
                                                variant: "tonal"
                                              }, {
                                                default: _withCtx(() => [
                                                  _createTextVNode(_toDisplayString(torrentStateText(item)), 1)
                                                ]),
                                                _: 2
                                              }, 1032, ["color"])
                                            ]),
                                            "item.size_gb": _withCtx(({ item }) => [
                                              _createTextVNode(_toDisplayString(Number(item.size_gb || 0).toFixed(2)) + " GB", 1)
                                            ]),
                                            "item.uploaded": _withCtx(({ item }) => [
                                              _createTextVNode(_toDisplayString(_unref(formatBytes)(item.uploaded)), 1)
                                            ]),
                                            "item.ratio": _withCtx(({ item }) => [
                                              _createTextVNode(_toDisplayString(Number(item.ratio || 0).toFixed(2)), 1)
                                            ]),
                                            "item.actions": _withCtx(({ item }) => [
                                              _createVNode(_component_VBtn, {
                                                size: "small",
                                                variant: "text",
                                                icon: item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline',
                                                "aria-label": item.is_protected ? '取消保留' : '保留',
                                                onClick: $event => (torrentAction(item, item.is_protected ? 'unprotect' : 'protect'))
                                              }, null, 8, ["icon", "aria-label", "onClick"]),
                                              _createVNode(_component_VBtn, {
                                                size: "small",
                                                variant: "text",
                                                color: "error",
                                                icon: "mdi-delete-outline",
                                                "aria-label": "删除",
                                                onClick: $event => (requestTorrentDelete(item))
                                              }, null, 8, ["onClick"]),
                                              _createVNode(_component_VMenu, { location: "bottom end" }, {
                                                activator: _withCtx(({ props: menuProps }) => [
                                                  _createVNode(_component_VBtn, _mergeProps(menuProps, {
                                                    size: "small",
                                                    variant: "text",
                                                    icon: "mdi-dots-vertical",
                                                    "aria-label": "更多操作"
                                                  }), null, 16)
                                                ]),
                                                default: _withCtx(() => [
                                                  _createVNode(_component_VList, {
                                                    density: "compact",
                                                    "min-width": "168"
                                                  }, {
                                                    default: _withCtx(() => [
                                                      (torrentIsPaused(item))
                                                        ? (_openBlock(), _createBlock(_component_VListItem, {
                                                            key: 0,
                                                            "prepend-icon": "mdi-play-circle-outline",
                                                            title: torrentResumeLabel(item),
                                                            onClick: $event => (torrentAction(item, 'resume'))
                                                          }, null, 8, ["title", "onClick"]))
                                                        : (_openBlock(), _createBlock(_component_VListItem, {
                                                            key: 1,
                                                            "prepend-icon": "mdi-pause-circle-outline",
                                                            title: torrentPauseLabel(item),
                                                            subtitle: "不会被自动恢复",
                                                            onClick: $event => (torrentAction(item, 'pause'))
                                                          }, null, 8, ["title", "onClick"])),
                                                      _createVNode(_component_VListItem, {
                                                        "prepend-icon": "mdi-sync",
                                                        title: "强制校验",
                                                        onClick: $event => (torrentAction(item, 'recheck'))
                                                      }, null, 8, ["onClick"]),
                                                      _createVNode(_component_VDivider, { class: "my-1" }),
                                                      _createVNode(_component_VListItem, {
                                                        "prepend-icon": "mdi-delete-outline",
                                                        title: "删除种子",
                                                        "base-color": "error",
                                                        onClick: $event => (requestTorrentDelete(item))
                                                      }, null, 8, ["onClick"])
                                                    ]),
                                                    _: 2
                                                  }, 1024)
                                                ]),
                                                _: 2
                                              }, 1024)
                                            ]),
                                            "no-data": _withCtx(() => [...(_cache[281] || (_cache[281] = [
                                              _createElementVNode("div", { class: "magicflow-table-empty" }, "当前筛选下没有托管种子", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["items", "loading"]),
                                          _createElementVNode("div", _hoisted_111, [
                                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(sortedTorrents.value, (item) => {
                                              return (_openBlock(), _createElementBlock("article", {
                                                key: item.hash || item.title,
                                                class: "magicflow-mobile-torrent",
                                                onClick: $event => (openTorrentDetail(item))
                                              }, [
                                                _createElementVNode("div", _hoisted_113, [
                                                  _createVNode(_component_VCheckbox, {
                                                    "model-value": selectedHashes.value.includes(item.hash),
                                                    density: "compact",
                                                    "hide-details": "",
                                                    class: "magicflow-mobile-torrent__check",
                                                    onClick: _cache[23] || (_cache[23] = _withModifiers(() => {}, ["stop"])),
                                                    "onUpdate:modelValue": $event => (toggleTorrentSelection(item))
                                                  }, null, 8, ["model-value", "onUpdate:modelValue"]),
                                                  _createElementVNode("div", _hoisted_114, [
                                                    _createElementVNode("strong", null, _toDisplayString(item.title || '未知种子'), 1),
                                                    _createElementVNode("span", null, _toDisplayString(selectedTask.value.site_name), 1)
                                                  ]),
                                                  _createVNode(_component_VChip, {
                                                    size: "small",
                                                    color: stateColor(item.state),
                                                    variant: "tonal",
                                                    class: "magicflow-mobile-torrent__state"
                                                  }, {
                                                    default: _withCtx(() => [
                                                      _createTextVNode(_toDisplayString(torrentStateText(item)), 1)
                                                    ]),
                                                    _: 2
                                                  }, 1032, ["color"])
                                                ]),
                                                _createVNode(_component_VProgressLinear, {
                                                  "model-value": torrentProgressPct(item),
                                                  color: stateColor(item.state),
                                                  height: "6",
                                                  rounded: "",
                                                  class: "magicflow-mobile-torrent__bar"
                                                }, null, 8, ["model-value", "color"]),
                                                _createElementVNode("div", _hoisted_115, [
                                                  _createElementVNode("span", null, [
                                                    _cache[282] || (_cache[282] = _createElementVNode("em", null, "大小", -1)),
                                                    _createElementVNode("b", null, _toDisplayString(Number(item.size_gb || 0).toFixed(2)) + " GB", 1)
                                                  ]),
                                                  _createElementVNode("span", null, [
                                                    _cache[283] || (_cache[283] = _createElementVNode("em", null, "上传量", -1)),
                                                    _createElementVNode("b", null, _toDisplayString(_unref(formatBytes)(item.uploaded)), 1)
                                                  ]),
                                                  _createElementVNode("span", null, [
                                                    _cache[284] || (_cache[284] = _createElementVNode("em", null, "分享率", -1)),
                                                    _createElementVNode("b", null, _toDisplayString(Number(item.ratio || 0).toFixed(2)), 1)
                                                  ])
                                                ]),
                                                _createElementVNode("div", _hoisted_116, [
                                                  _createVNode(_component_VBtn, {
                                                    size: "small",
                                                    variant: "tonal",
                                                    color: item.is_protected ? 'grey' : 'primary',
                                                    "prepend-icon": item.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline',
                                                    onClick: _withModifiers($event => (torrentAction(item, item.is_protected ? 'unprotect' : 'protect')), ["stop"])
                                                  }, {
                                                    default: _withCtx(() => [
                                                      _createTextVNode(_toDisplayString(item.is_protected ? '取消保留' : '保留'), 1)
                                                    ]),
                                                    _: 2
                                                  }, 1032, ["color", "prepend-icon", "onClick"]),
                                                  _createVNode(_component_VBtn, {
                                                    size: "small",
                                                    variant: "tonal",
                                                    color: "error",
                                                    "prepend-icon": "mdi-delete-outline",
                                                    onClick: _withModifiers($event => (requestTorrentDelete(item)), ["stop"])
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[285] || (_cache[285] = [
                                                      _createTextVNode("删除", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["onClick"]),
                                                  (torrentIsPaused(item))
                                                    ? (_openBlock(), _createBlock(_component_VBtn, {
                                                        key: 0,
                                                        size: "small",
                                                        variant: "tonal",
                                                        "prepend-icon": "mdi-play-circle-outline",
                                                        onClick: _withModifiers($event => (torrentAction(item, 'resume')), ["stop"])
                                                      }, {
                                                        default: _withCtx(() => [
                                                          _createTextVNode(_toDisplayString(torrentProgressPct(item) >= 100 ? '恢复' : '继续'), 1)
                                                        ]),
                                                        _: 2
                                                      }, 1032, ["onClick"]))
                                                    : (_openBlock(), _createBlock(_component_VBtn, {
                                                        key: 1,
                                                        size: "small",
                                                        variant: "tonal",
                                                        "prepend-icon": "mdi-pause-circle-outline",
                                                        onClick: _withModifiers($event => (torrentAction(item, 'pause')), ["stop"])
                                                      }, {
                                                        default: _withCtx(() => [...(_cache[286] || (_cache[286] = [
                                                          _createTextVNode("暂停", -1)
                                                        ]))]),
                                                        _: 1
                                                      }, 8, ["onClick"])),
                                                  _createVNode(_component_VBtn, {
                                                    size: "small",
                                                    variant: "tonal",
                                                    "prepend-icon": "mdi-sync",
                                                    onClick: _withModifiers($event => (torrentAction(item, 'recheck')), ["stop"])
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[287] || (_cache[287] = [
                                                      _createTextVNode("校验", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["onClick"])
                                                ])
                                              ], 8, _hoisted_112))
                                            }), 128)),
                                            (!sortedTorrents.value.length)
                                              ? (_openBlock(), _createElementBlock("div", _hoisted_117, "当前筛选下没有托管种子"))
                                              : _createCommentVNode("", true)
                                          ])
                                        ]),
                                        _: 1
                                      }))
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VWindowItem, { value: "config" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("div", _hoisted_118, [
                                    _createVNode(_component_VSheet, {
                                      tag: "section",
                                      class: "magicflow-panel app-surface-static"
                                    }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("header", _hoisted_119, [
                                          _createElementVNode("div", null, [
                                            _createElementVNode("div", _hoisted_120, _toDisplayString(taskIsBrush.value ? '刷流规则' : '魔力规则'), 1),
                                            _createElementVNode("div", _hoisted_121, _toDisplayString(taskIsBrush.value ? '刷流标准：免费 + 有下载者；做种满天数清理' : '当前服务端生效的魔力养护配置'), 1)
                                          ])
                                        ]),
                                        _createElementVNode("dl", _hoisted_122, [
                                          _createElementVNode("div", null, [
                                            _cache[288] || (_cache[288] = _createElementVNode("dt", null, "任务状态", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(selectedRunMode.value.text), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[289] || (_cache[289] = _createElementVNode("dt", null, "任务目标", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(goalFactText.value), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[290] || (_cache[290] = _createElementVNode("dt", null, "站点", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(selectedTask.value.site_name), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[291] || (_cache[291] = _createElementVNode("dt", null, "下载器", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(selectedTask.value.downloader), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[292] || (_cache[292] = _createElementVNode("dt", null, "下载器标签", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(selectedTask.value.brush_tag || '未设置'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[293] || (_cache[293] = _createElementVNode("dt", null, "促销要求", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskIsBrush.value ? '免费（含 2X免费）' : (taskConfig.value.freeleech === '2xfree' ? '2X 免费' : taskConfig.value.freeleech === 'free' ? '免费' : '全部')), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[294] || (_cache[294] = _createElementVNode("dt", null, "选种来源", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.rss_support ? 'RSS' : '站点列表页'), 1)
                                          ]),
                                          (taskIsBrush.value)
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                _createElementVNode("div", null, [
                                                  _cache[295] || (_cache[295] = _createElementVNode("dt", null, "保种天数", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(brushSeedDays.value > 0 ? `做种满 ${brushSeedDays.value} 天清理` : '不按天数（按无上传）'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[296] || (_cache[296] = _createElementVNode("dt", null, "最小下载人数", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.brush_min_leechers ?? 1) + " 人", 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[297] || (_cache[297] = _createElementVNode("dt", null, "种子大小", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.size || '不限'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[298] || (_cache[298] = _createElementVNode("dt", null, "做种人数", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.seeder || '不限'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[299] || (_cache[299] = _createElementVNode("dt", null, "发布时间", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.pubtime ? `${taskConfig.value.pubtime} 分钟` : '不限'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[300] || (_cache[300] = _createElementVNode("dt", null, "排除 H&R", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.hr === 'yes' ? '是' : '否'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[301] || (_cache[301] = _createElementVNode("dt", null, "包含规则", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.include || '无'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[302] || (_cache[302] = _createElementVNode("dt", null, "排除规则", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.exclude || '无'), 1)
                                                ])
                                              ], 64))
                                            : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                                _createElementVNode("div", null, [
                                                  _cache[303] || (_cache[303] = _createElementVNode("dt", null, "保种体积", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.disk_size_gb ? `${taskConfig.value.disk_size_gb} GB` : '不限'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[304] || (_cache[304] = _createElementVNode("dt", null, "最低魔力", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.value.min_bonus_per_hour).toFixed(2)} /h`), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[305] || (_cache[305] = _createElementVNode("dt", null, "最多保留", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_keep_torrents == null ? '自动 / 不限' : `${taskConfig.value.max_keep_torrents} 个`), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[306] || (_cache[306] = _createElementVNode("dt", null, "保护阈值", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.value.bonus_protect_threshold).toFixed(0)), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[307] || (_cache[307] = _createElementVNode("dt", null, "完美种保护", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.protect_perfect === false ? '关闭' : `开启（≤${taskConfig.value.perfect_max_seeders ?? 3}人 · ≥${taskConfig.value.perfect_min_weeks ?? 4}周）`), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[308] || (_cache[308] = _createElementVNode("dt", null, "公式 T0/N0", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_t0 ?? '默认') + " / " + _toDisplayString(taskConfig.value.bonus_n0 ?? '默认'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[309] || (_cache[309] = _createElementVNode("dt", null, "公式 B0/L", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_b0 ?? '默认') + " / " + _toDisplayString(taskConfig.value.bonus_l ?? '默认'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[310] || (_cache[310] = _createElementVNode("dt", null, "零魔权重", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_zero_weight ?? '默认'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[311] || (_cache[311] = _createElementVNode("dt", null, "保底魔力", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(Number(taskConfig.value.min_bonus_to_keep || 0).toFixed(2)), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[312] || (_cache[312] = _createElementVNode("dt", null, "种子大小", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.size || '不限'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[313] || (_cache[313] = _createElementVNode("dt", null, "做种人数", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.seeder || '不限'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[314] || (_cache[314] = _createElementVNode("dt", null, "发布时间", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.pubtime ? `${taskConfig.value.pubtime} 分钟` : '不限'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[315] || (_cache[315] = _createElementVNode("dt", null, "排除 H&R", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.hr === 'yes' ? '是' : '否'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[316] || (_cache[316] = _createElementVNode("dt", null, "包含规则", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.include || '无'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[317] || (_cache[317] = _createElementVNode("dt", null, "排除规则", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.exclude || '无'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[318] || (_cache[318] = _createElementVNode("dt", null, "最短做种", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_seed_time ? `${taskConfig.value.min_seed_time} 小时` : '不限'), 1)
                                                ]),
                                                _createElementVNode("div", null, [
                                                  _cache[319] || (_cache[319] = _createElementVNode("dt", null, "最低分享率", -1)),
                                                  _createElementVNode("dd", null, _toDisplayString(Number(taskConfig.value.min_ratio || 0).toFixed(2)), 1)
                                                ])
                                              ], 64)),
                                          _createElementVNode("div", null, [
                                            _cache[320] || (_cache[320] = _createElementVNode("dt", null, "单轮最多新增", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_add_per_run ?? 10) + " 个", 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[321] || (_cache[321] = _createElementVNode("dt", null, "同时下载上限", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_download_concurrent ?? 10) + " 个", 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[322] || (_cache[322] = _createElementVNode("dt", null, "每轮参评候选", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.top_n ?? 30) + " 个", 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[323] || (_cache[323] = _createElementVNode("dt", null, "每轮翻页数", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.browse_pages ?? 3) + " 页", 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[324] || (_cache[324] = _createElementVNode("dt", null, "自动补种", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.refill_when_empty ? '开启' : '关闭'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[325] || (_cache[325] = _createElementVNode("dt", null, "存量复用", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.reuse_existing ? (taskConfig.value.reuse_verify ? '开启（校验）' : '开启（跳过校验）') : '关闭'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[326] || (_cache[326] = _createElementVNode("dt", null, "无进度清理", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_no_progress ? `开启（${taskConfig.value.no_progress_minutes ?? 30} 分钟）` : '关闭'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[327] || (_cache[327] = _createElementVNode("dt", null, "慢速清理", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.value.slow_progress_max_hours ?? 48}h 下不完即清）`), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[328] || (_cache[328] = _createElementVNode("dt", null, "促销失效清理", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[329] || (_cache[329] = _createElementVNode("dt", null, "自动恢复暂停", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.auto_resume_paused === false ? '关闭' : '开启'), 1)
                                          ])
                                        ])
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode(_component_VSheet, {
                                      tag: "section",
                                      class: "magicflow-panel app-surface-static"
                                    }, {
                                      default: _withCtx(() => [
                                        _cache[337] || (_cache[337] = _createElementVNode("header", { class: "magicflow-panel__head" }, [
                                          _createElementVNode("div", null, [
                                            _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "任务操作"),
                                            _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "以下操作只影响当前任务")
                                          ])
                                        ], -1)),
                                        _createElementVNode("div", _hoisted_123, [
                                          _createElementVNode("div", null, [
                                            _cache[331] || (_cache[331] = _createElementVNode("strong", null, "执行一次", -1)),
                                            _createElementVNode("span", null, _toDisplayString(taskIsBrush.value ? '立即按刷流标准抓取免费热种并保持上传' : '立即按当前策略抓取候选并养护做种'), 1),
                                            _createVNode(_component_VBtn, {
                                              color: "primary",
                                              variant: "tonal",
                                              "prepend-icon": "mdi-sync",
                                              loading: saving.value,
                                              onClick: runOperation
                                            }, {
                                              default: _withCtx(() => [...(_cache[330] || (_cache[330] = [
                                                _createTextVNode(" 立即执行 ", -1)
                                              ]))]),
                                              _: 1
                                            }, 8, ["loading"])
                                          ]),
                                          _createVNode(_component_VDivider),
                                          _createElementVNode("div", null, [
                                            _cache[333] || (_cache[333] = _createElementVNode("strong", null, "编辑任务", -1)),
                                            _createElementVNode("span", null, _toDisplayString(taskIsBrush.value ? '调整调度、刷流门槛与清理策略' : '调整调度、魔力门槛与公式参数'), 1),
                                            _createVNode(_component_VBtn, {
                                              variant: "tonal",
                                              "prepend-icon": "mdi-pencil-outline",
                                              onClick: openEditTask
                                            }, {
                                              default: _withCtx(() => [...(_cache[332] || (_cache[332] = [
                                                _createTextVNode("编辑任务", -1)
                                              ]))]),
                                              _: 1
                                            })
                                          ]),
                                          _createVNode(_component_VDivider),
                                          _createElementVNode("div", null, [
                                            _cache[335] || (_cache[335] = _createElementVNode("strong", null, "删除任务", -1)),
                                            _cache[336] || (_cache[336] = _createElementVNode("span", null, "存在活跃种子时后端会拒绝删除，避免留下失管任务", -1)),
                                            _createVNode(_component_VBtn, {
                                              color: "error",
                                              variant: "tonal",
                                              "prepend-icon": "mdi-delete-outline",
                                              onClick: _cache[24] || (_cache[24] = $event => (deleteDialog.value = true))
                                            }, {
                                              default: _withCtx(() => [...(_cache[334] || (_cache[334] = [
                                                _createTextVNode("删除任务", -1)
                                              ]))]),
                                              _: 1
                                            })
                                          ])
                                        ])
                                      ]),
                                      _: 1
                                    })
                                  ])
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          }, 8, ["modelValue"])
                        ], 64))
                      : (_openBlock(), _createBlock(_component_VSheet, {
                          key: 1,
                          class: "magicflow-panel app-surface-static",
                          style: {"margin-top":"16px"}
                        }, {
                          default: _withCtx(() => [
                            _createElementVNode("header", _hoisted_124, [
                              _cache[339] || (_cache[339] = _createElementVNode("div", null, [
                                _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "静默托管 · 常驻 worker"),
                                _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "静默池的负责人：清理未下完 / 保挂（恢复做种）/ H&R 统一管理 / 辅种校验 / 分拣，低频自动运行")
                              ], -1)),
                              _createVNode(_component_VChip, {
                                color: "primary",
                                size: "small",
                                variant: "tonal",
                                "prepend-icon": "mdi-access-point"
                              }, {
                                default: _withCtx(() => [...(_cache[338] || (_cache[338] = [
                                  _createTextVNode("常驻", -1)
                                ]))]),
                                _: 1
                              })
                            ]),
                            _createElementVNode("div", _hoisted_125, [
                              _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("strong", null, _toDisplayString(selectedTask.value.seeding_count || 0), 1),
                                  _createElementVNode("span", null, "静默池种子 · 其中隔离区（欠 H&R 工时）" + _toDisplayString(selectedTask.value.hr_count || 0) + " / 其他 " + _toDisplayString(selectedTask.value.nonhr_count || 0), 1)
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("strong", null, _toDisplayString(selectedTask.value.host_interval_minutes || 60) + " 分钟", 1),
                                  _cache[340] || (_cache[340] = _createElementVNode("span", null, "托管周期 · silent_host_interval_minutes 可调", -1))
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("strong", null, _toDisplayString(selectedTask.value.host_last_run || '—'), 1),
                                  _cache[341] || (_cache[341] = _createElementVNode("span", null, "上次运行", -1))
                                ]),
                                _: 1
                              })
                            ]),
                            _createVNode(_component_VSheet, {
                              tag: "section",
                              class: "magicflow-panel app-surface-static mt-4"
                            }, {
                              default: _withCtx(() => [
                                _cache[342] || (_cache[342] = _createElementVNode("header", { class: "magicflow-panel__head" }, [
                                  _createElementVNode("div", null, [
                                    _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "分类"),
                                    _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "静默池按子类 / 义务 / 站点拆分（职责说明见仓库 docs/静默托管.md）")
                                  ])
                                ], -1)),
                                _createElementVNode("div", _hoisted_126, [
                                  _createVNode(_component_VChip, {
                                    size: "small",
                                    variant: "tonal",
                                    color: "info"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode("静默-新 " + _toDisplayString((selectedTask.value.classify && selectedTask.value.classify.by_state && selectedTask.value.classify.by_state['新']) || 0), 1)
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_VChip, {
                                    size: "small",
                                    variant: "tonal",
                                    color: "success"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode("静默-资源 " + _toDisplayString((selectedTask.value.classify && selectedTask.value.classify.by_state && selectedTask.value.classify.by_state['资源']) || 0), 1)
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_VChip, {
                                    size: "small",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode("静默-普通 " + _toDisplayString((selectedTask.value.classify && selectedTask.value.classify.by_state && selectedTask.value.classify.by_state['普通']) || 0), 1)
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_VChip, {
                                    size: "small",
                                    variant: "tonal",
                                    color: "error"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode("隔离区（欠 H&R 工时）" + _toDisplayString(selectedTask.value.hr_count || 0), 1)
                                    ]),
                                    _: 1
                                  }),
                                  _createVNode(_component_VChip, {
                                    size: "small",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode("其他 " + _toDisplayString(selectedTask.value.nonhr_count || 0), 1)
                                    ]),
                                    _: 1
                                  })
                                ]),
                                (silentHostSites.value.length)
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_127, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(silentHostSites.value, (row, i) => {
                                        return (_openBlock(), _createElementBlock("span", {
                                          key: row.name
                                        }, [
                                          _createTextVNode(_toDisplayString(i ? '  ·  ' : '') + _toDisplayString(row.name) + " " + _toDisplayString(row.total), 1),
                                          (row.hr)
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                _createTextVNode("（隔离 " + _toDisplayString(row.hr) + "）", 1)
                                              ], 64))
                                            : _createCommentVNode("", true)
                                        ]))
                                      }), 128))
                                    ]))
                                  : _createCommentVNode("", true)
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_VSheet, {
                              tag: "section",
                              class: "magicflow-panel app-surface-static mt-4"
                            }, {
                              default: _withCtx(() => [
                                _createElementVNode("header", _hoisted_128, [
                                  _cache[344] || (_cache[344] = _createElementVNode("div", null, [
                                    _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "操作记录"),
                                    _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "每次运行一条流水（展开看九步结果）")
                                  ], -1)),
                                  _createVNode(_component_VBtn, {
                                    variant: "text",
                                    color: "primary",
                                    "prepend-icon": "mdi-refresh",
                                    onClick: _cache[26] || (_cache[26] = $event => (loadOperations(selectedTaskId.value)))
                                  }, {
                                    default: _withCtx(() => [...(_cache[343] || (_cache[343] = [
                                      _createTextVNode("刷新", -1)
                                    ]))]),
                                    _: 1
                                  })
                                ]),
                                _createElementVNode("div", _hoisted_129, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(operationData.value.operations || [], (record) => {
                                    return (_openBlock(), _createElementBlock("article", {
                                      key: record.operation_id
                                    }, [
                                      _createVNode(_component_VIcon, {
                                        icon: operationIcon(record.kind),
                                        color: operationColor(record)
                                      }, null, 8, ["icon", "color"]),
                                      _createElementVNode("div", null, [
                                        _createElementVNode("strong", null, [
                                          _createTextVNode(_toDisplayString(operationKindText(record.kind)) + " ", 1),
                                          _createVNode(_component_VChip, {
                                            size: "x-small",
                                            variant: "tonal",
                                            color: operationColor(record),
                                            class: "ml-2"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(operationStateText(record.state)), 1)
                                            ]),
                                            _: 2
                                          }, 1032, ["color"])
                                        ]),
                                        _createElementVNode("span", null, _toDisplayString(operationSummary(record)), 1),
                                        _createElementVNode("span", null, [
                                          _createTextVNode(_toDisplayString(_unref(formatDateTime)(record.created_at)) + " · 耗时 " + _toDisplayString(operationDuration(record)), 1),
                                          (hasOpDetail(record))
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                _createTextVNode(" · " + _toDisplayString(opDetailItems(record).length) + " 条明细", 1)
                                              ], 64))
                                            : _createCommentVNode("", true)
                                        ]),
                                        (record.error_message)
                                          ? (_openBlock(), _createElementBlock("span", _hoisted_130, _toDisplayString(record.error_message), 1))
                                          : _createCommentVNode("", true),
                                        (hasOpDetail(record))
                                          ? (_openBlock(), _createElementBlock("button", {
                                              key: 1,
                                              type: "button",
                                              class: "magicflow-events__toggle",
                                              onClick: $event => (toggleOpDetail(record.operation_id))
                                            }, [
                                              _createTextVNode(_toDisplayString(isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细') + " ", 1),
                                              _createVNode(_component_VIcon, {
                                                icon: isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down',
                                                size: "14"
                                              }, null, 8, ["icon"])
                                            ], 8, _hoisted_131))
                                          : _createCommentVNode("", true),
                                        (isOpDetailOpen(record.operation_id))
                                          ? (_openBlock(), _createElementBlock("ul", _hoisted_132, [
                                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(opDetailItems(record), (it, idx) => {
                                                return (_openBlock(), _createElementBlock("li", { key: idx }, [
                                                  _createElementVNode("span", _hoisted_133, [
                                                    (itemSourceText(it.source))
                                                      ? (_openBlock(), _createElementBlock("em", _hoisted_134, _toDisplayString(itemSourceText(it.source)), 1))
                                                      : _createCommentVNode("", true),
                                                    _createElementVNode("span", {
                                                      class: "magicflow-events__detail-title",
                                                      title: it.title || it.hash
                                                    }, _toDisplayString(it.title || it.hash || '—'), 9, _hoisted_135)
                                                  ])
                                                ]))
                                              }), 128))
                                            ]))
                                          : _createCommentVNode("", true)
                                      ])
                                    ]))
                                  }), 128)),
                                  (!(operationData.value.operations || []).length)
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_136, "暂无操作记录"))
                                    : _createCommentVNode("", true)
                                ])
                              ]),
                              _: 1
                            }),
                            _createElementVNode("div", _hoisted_137, [
                              _createVNode(_component_VBtn, {
                                size: "small",
                                color: "primary",
                                variant: "tonal",
                                "prepend-icon": "mdi-sync",
                                loading: saving.value,
                                onClick: runOperation
                              }, {
                                default: _withCtx(() => [...(_cache[345] || (_cache[345] = [
                                  _createTextVNode("立即执行", -1)
                                ]))]),
                                _: 1
                              }, 8, ["loading"]),
                              _createVNode(_component_VBtn, {
                                size: "small",
                                variant: "text",
                                "prepend-icon": "mdi-refresh",
                                onClick: _cache[27] || (_cache[27] = $event => (reloadSelected()))
                              }, {
                                default: _withCtx(() => [...(_cache[346] || (_cache[346] = [
                                  _createTextVNode("刷新", -1)
                                ]))]),
                                _: 1
                              })
                            ])
                          ]),
                          _: 1
                        }))
                  ]))
                : _createCommentVNode("", true)
            ])
          ], 64)),
    _createVNode(_component_VDialog, {
      modelValue: ceilingOpen.value,
      "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((ceilingOpen).value = $event)),
      "max-width": "34rem",
      scrollable: "",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-ceiling-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_138, [
              _cache[347] || (_cache[347] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "站点容量", -1)),
              _cache[348] || (_cache[348] = _createElementVNode("span", { class: "magicflow-ops-dialog__spacer" }, null, -1)),
              _createVNode(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[28] || (_cache[28] = $event => (ceilingOpen.value = false))
              })
            ]),
            _cache[350] || (_cache[350] = _createElementVNode("div", { class: "magicflow-ops-dialog__sub" }, " 时魔 ÷ 站点上限。占用高 = 快满，占用低 = 还有空间加种 ", -1)),
            _createElementVNode("div", _hoisted_139, [
              _createElementVNode("div", _hoisted_140, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(siteCeilingRows.value, (r) => {
                  return (_openBlock(), _createElementBlock("div", {
                    key: r.site,
                    class: "magicflow-ceiling-row"
                  }, [
                    _createElementVNode("div", _hoisted_141, [
                      _createElementVNode("span", _hoisted_142, _toDisplayString(r.site), 1),
                      _createElementVNode("span", _hoisted_143, [
                        _createTextVNode(_toDisplayString(r.bonus ? r.bonus.toFixed(1) : '—'), 1),
                        _cache[349] || (_cache[349] = _createElementVNode("small", null, "/h", -1)),
                        (r.ceiling)
                          ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                              _createTextVNode(" · 上限 " + _toDisplayString(r.ceiling.toFixed(0)), 1)
                            ], 64))
                          : _createCommentVNode("", true)
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_144, [
                      _createElementVNode("i", {
                        style: _normalizeStyle({ width: Math.min(r.pct, 100) + '%' }),
                        class: _normalizeClass({ 'is-full': r.pct >= 85 })
                      }, null, 6)
                    ]),
                    _createElementVNode("div", _hoisted_145, [
                      _createElementVNode("span", null, "占用 " + _toDisplayString(r.pct) + "%", 1),
                      _createElementVNode("span", null, _toDisplayString(r.seeds) + " 种", 1)
                    ])
                  ]))
                }), 128)),
                (!siteCeilingRows.value.length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_146, "暂无数据（任务尚未产出统计）"))
                  : _createCommentVNode("", true)
              ])
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      modelValue: signinOpen.value,
      "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((signinOpen).value = $event)),
      "max-width": "40rem",
      scrollable: "",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-signin-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_147, [
              _cache[354] || (_cache[354] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "签到", -1)),
              (signinReport.value.enabled)
                ? (_openBlock(), _createBlock(_component_VChip, {
                    key: 0,
                    size: "x-small",
                    color: "success",
                    variant: "tonal"
                  }, {
                    default: _withCtx(() => [...(_cache[351] || (_cache[351] = [
                      _createTextVNode("已启用", -1)
                    ]))]),
                    _: 1
                  }))
                : (signinReportLoading.value)
                  ? (_openBlock(), _createBlock(_component_VChip, {
                      key: 1,
                      size: "x-small",
                      color: "grey",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [...(_cache[352] || (_cache[352] = [
                        _createTextVNode("加载中", -1)
                      ]))]),
                      _: 1
                    }))
                  : (_openBlock(), _createBlock(_component_VChip, {
                      key: 2,
                      size: "x-small",
                      color: "grey",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [...(_cache[353] || (_cache[353] = [
                        _createTextVNode("已关闭", -1)
                      ]))]),
                      _: 1
                    })),
              _cache[355] || (_cache[355] = _createElementVNode("span", { class: "magicflow-ops-dialog__spacer" }, null, -1)),
              _createVNode(_component_VBtn, {
                icon: "mdi-refresh",
                size: "small",
                variant: "text",
                "aria-label": "刷新",
                loading: signinReportLoading.value,
                onClick: loadSigninReport
              }, null, 8, ["loading"]),
              _createVNode(_component_VBtn, {
                icon: "mdi-tune-variant",
                size: "small",
                variant: "text",
                "aria-label": "设置",
                onClick: _cache[30] || (_cache[30] = $event => {signinOpen.value = false; openSettings('signin');})
              }),
              _createVNode(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[31] || (_cache[31] = $event => (signinOpen.value = false))
              })
            ]),
            _createElementVNode("div", _hoisted_148, "共 " + _toDisplayString(signinReportTodayRows.value.length) + " 个站点 · 近 7 天记录（右上设置进入配置）", 1),
            _createElementVNode("div", _hoisted_149, [
              _createElementVNode("div", _hoisted_150, [
                _createElementVNode("div", _hoisted_151, [
                  _createElementVNode("div", _hoisted_152, _toDisplayString(signinTodayCounts.value.ok), 1),
                  _cache[356] || (_cache[356] = _createElementVNode("div", { class: "magicflow-signin-stat__l" }, "今日成功", -1))
                ]),
                _createElementVNode("div", {
                  class: _normalizeClass(["magicflow-signin-stat", signinTodayCounts.value.fail ? 'is-fail' : ''])
                }, [
                  _createElementVNode("div", _hoisted_153, _toDisplayString(signinTodayCounts.value.fail), 1),
                  _cache[357] || (_cache[357] = _createElementVNode("div", { class: "magicflow-signin-stat__l" }, "今日失败", -1))
                ], 2),
                _createElementVNode("div", {
                  class: _normalizeClass(["magicflow-signin-stat", signinTodayCounts.value.pending ? 'is-pending' : ''])
                }, [
                  _createElementVNode("div", _hoisted_154, _toDisplayString(signinTodayCounts.value.pending), 1),
                  _cache[358] || (_cache[358] = _createElementVNode("div", { class: "magicflow-signin-stat__l" }, "待执行", -1))
                ], 2),
                _createElementVNode("div", _hoisted_155, [
                  _createElementVNode("div", _hoisted_156, _toDisplayString((signinMatrix.value.stats.ok + signinMatrix.value.stats.fail) ? Math.round(signinMatrix.value.stats.ok * 100 / (signinMatrix.value.stats.ok + signinMatrix.value.stats.fail)) + '%' : '—'), 1),
                  _cache[359] || (_cache[359] = _createElementVNode("div", { class: "magicflow-signin-stat__l" }, "近 7 天成功率", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_157, [
                _createVNode(_component_VBtn, {
                  size: "small",
                  color: "primary",
                  variant: "flat",
                  "prepend-icon": "mdi-calendar-check",
                  loading: signinRunning.value,
                  onClick: _cache[32] || (_cache[32] = $event => (runSigninNow('sign')))
                }, {
                  default: _withCtx(() => [...(_cache[360] || (_cache[360] = [
                    _createTextVNode("立即签到", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode(_component_VBtn, {
                  size: "small",
                  color: "primary",
                  variant: "tonal",
                  "prepend-icon": "mdi-login-variant",
                  loading: signinRunning.value,
                  onClick: _cache[33] || (_cache[33] = $event => (runSigninNow('login')))
                }, {
                  default: _withCtx(() => [...(_cache[361] || (_cache[361] = [
                    _createTextVNode("立即登录", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _createElementVNode("div", _hoisted_158, [
                _createElementVNode("div", _hoisted_159, [
                  _createVNode(_component_VIcon, {
                    icon: "mdi-clipboard-check-outline",
                    size: "16"
                  }),
                  _createTextVNode(" 今日（" + _toDisplayString(signinReport.value.today || '—') + "）", 1)
                ]),
                _createElementVNode("div", _hoisted_160, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(signinFilterItems.value, (f) => {
                    return (_openBlock(), _createBlock(_component_VChip, {
                      key: f.value,
                      size: "x-small",
                      color: signinFilter.value === f.value ? f.color : undefined,
                      variant: signinFilter.value === f.value ? 'flat' : 'tonal',
                      onClick: $event => (signinFilter.value = f.value)
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(f.label), 1)
                      ]),
                      _: 2
                    }, 1032, ["color", "variant", "onClick"]))
                  }), 128)),
                  _createVNode(_component_VTextField, {
                    modelValue: signinSearch.value,
                    "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((signinSearch).value = $event)),
                    class: "magicflow-signin-search",
                    density: "compact",
                    variant: "solo-filled",
                    flat: "",
                    "hide-details": "",
                    clearable: "",
                    placeholder: "搜索站点",
                    "prepend-inner-icon": "mdi-magnify"
                  }, null, 8, ["modelValue"])
                ]),
                (signinTodayList.value.length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_161, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(signinTodayList.value, (row) => {
                        return (_openBlock(), _createElementBlock("div", {
                          key: row.site_id,
                          class: _normalizeClass(["magicflow-signin-row", 'is-' + row.status])
                        }, [
                          _createElementVNode("span", {
                            class: _normalizeClass(["magicflow-signin-row__dot", 'is-' + row.status])
                          }, null, 2),
                          _createElementVNode("span", _hoisted_162, _toDisplayString(row.site_name), 1),
                          _createElementVNode("span", {
                            class: "magicflow-signin-row__msg",
                            title: row.msg
                          }, _toDisplayString(row.msg || '待执行'), 9, _hoisted_163)
                        ], 2))
                      }), 128))
                    ]))
                  : (_openBlock(), _createElementBlock("p", _hoisted_164, "还没有站点结果。先到右上齿轮里勾选要签到的站点。"))
              ]),
              (signinMatrix.value.rows.length)
                ? (_openBlock(), _createElementBlock("div", _hoisted_165, [
                    _createElementVNode("div", _hoisted_166, [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-calendar-clock",
                        size: "16"
                      }),
                      _createTextVNode(" 近 7 天（" + _toDisplayString(signinMatrix.value.rows.length) + " 站）", 1)
                    ]),
                    _createElementVNode("div", _hoisted_167, [
                      _createElementVNode("div", _hoisted_168, [
                        _cache[362] || (_cache[362] = _createElementVNode("span", { class: "magicflow-signin-matrix__name" }, "站点", -1)),
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(signinMatrix.value.dates, (d) => {
                          return (_openBlock(), _createElementBlock("span", {
                            key: d,
                            class: "magicflow-signin-matrix__date"
                          }, _toDisplayString(signinDateLabel(d)), 1))
                        }), 128))
                      ]),
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(signinMatrix.value.rows, (row) => {
                        return (_openBlock(), _createElementBlock("div", {
                          key: row.sid,
                          class: "magicflow-signin-matrix__row"
                        }, [
                          _createElementVNode("span", {
                            class: "magicflow-signin-matrix__name",
                            title: row.name
                          }, _toDisplayString(row.name), 9, _hoisted_169),
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(row.cells, (c) => {
                            return (_openBlock(), _createElementBlock("span", {
                              key: c.date,
                              class: _normalizeClass(["magicflow-signin-cell", 'is-' + c.status]),
                              title: c.date + ' ' + signinStatusText(c.status)
                            }, null, 10, _hoisted_170))
                          }), 128))
                        ]))
                      }), 128))
                    ]),
                    _cache[363] || (_cache[363] = _createElementVNode("div", { class: "magicflow-signin-legend" }, [
                      _createElementVNode("span", null, [
                        _createElementVNode("i", { class: "magicflow-signin-cell is-ok" }),
                        _createTextVNode("成功")
                      ]),
                      _createElementVNode("span", null, [
                        _createElementVNode("i", { class: "magicflow-signin-cell is-signfail" }),
                        _createTextVNode("签到失败")
                      ]),
                      _createElementVNode("span", null, [
                        _createElementVNode("i", { class: "magicflow-signin-cell is-loginfail" }),
                        _createTextVNode("登录失败")
                      ]),
                      _createElementVNode("span", null, [
                        _createElementVNode("i", { class: "magicflow-signin-cell is-fail" }),
                        _createTextVNode("都失败")
                      ]),
                      _createElementVNode("span", null, [
                        _createElementVNode("i", { class: "magicflow-signin-cell is-pending" }),
                        _createTextVNode("待执行")
                      ]),
                      _createElementVNode("span", null, [
                        _createElementVNode("i", { class: "magicflow-signin-cell is-none" }),
                        _createTextVNode("无记录")
                      ])
                    ], -1))
                  ]))
                : _createCommentVNode("", true)
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      modelValue: opsOpen.value,
      "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((opsOpen).value = $event)),
      "max-width": "46rem",
      scrollable: "",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-ops-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_171, [
              _cache[364] || (_cache[364] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "操作记录", -1)),
              _cache[365] || (_cache[365] = _createElementVNode("span", { class: "magicflow-ops-dialog__spacer" }, null, -1)),
              _createVNode(_component_VBtn, {
                icon: "mdi-refresh",
                size: "small",
                variant: "text",
                "aria-label": "刷新",
                loading: opsLoadingAll.value,
                onClick: _cache[36] || (_cache[36] = $event => (opsScope.value === 'all' ? loadOperationsAll() : loadOperations(selectedTaskId.value)))
              }, null, 8, ["loading"]),
              _createVNode(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[37] || (_cache[37] = $event => (opsOpen.value = false))
              })
            ]),
            _createElementVNode("div", _hoisted_172, [
              (opsScope.value === 'all')
                ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                    _createTextVNode("全部任务 · 跨站点汇总 · 每次执行 / 选种 / 删种 / 保护 / 标签 的流水（最近 100 条）")
                  ], 64))
                : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                    _createTextVNode(_toDisplayString(selectedTask.value ? (selectedTask.value.name || '当前任务') : '未选择任务') + " · 每次执行 / 选种 / 删种 / 保护 / 标签 的流水", 1)
                  ], 64))
            ]),
            _createElementVNode("div", _hoisted_173, [
              _createElementVNode("div", _hoisted_174, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(operationData.value.operations || [], (record) => {
                  return (_openBlock(), _createElementBlock("article", {
                    key: record.operation_id
                  }, [
                    _createVNode(_component_VIcon, {
                      icon: operationIcon(record.kind),
                      color: operationColor(record)
                    }, null, 8, ["icon", "color"]),
                    _createElementVNode("div", null, [
                      _createElementVNode("strong", null, [
                        _createTextVNode(_toDisplayString(operationKindText(record.kind)) + " ", 1),
                        (opsScope.value === 'all')
                          ? (_openBlock(), _createBlock(_component_VChip, {
                              key: 0,
                              size: "x-small",
                              variant: "text",
                              class: "ml-1 magicflow-ops-dialog__task"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(taskLabel(record.task_id)), 1)
                              ]),
                              _: 2
                            }, 1024))
                          : _createCommentVNode("", true),
                        _createVNode(_component_VChip, {
                          size: "x-small",
                          variant: "tonal",
                          color: operationColor(record),
                          class: "ml-2"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(operationStateText(record.state)), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"])
                      ]),
                      _createElementVNode("span", null, _toDisplayString(operationSummary(record)), 1),
                      _createElementVNode("span", null, [
                        _createTextVNode(_toDisplayString(_unref(formatDateTime)(record.created_at)) + " · 耗时 " + _toDisplayString(operationDuration(record)) + " ", 1),
                        (hasOpDetail(record))
                          ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                              _createTextVNode(" · " + _toDisplayString(opDetailItems(record).length) + " 条明细", 1)
                            ], 64))
                          : _createCommentVNode("", true)
                      ]),
                      (record.error_message)
                        ? (_openBlock(), _createElementBlock("span", _hoisted_175, _toDisplayString(record.error_message), 1))
                        : _createCommentVNode("", true),
                      (hasOpDetail(record))
                        ? (_openBlock(), _createElementBlock("button", {
                            key: 1,
                            type: "button",
                            class: "magicflow-events__toggle",
                            onClick: $event => (toggleOpDetail(record.operation_id))
                          }, [
                            _createTextVNode(_toDisplayString(isOpDetailOpen(record.operation_id) ? '收起明细' : '展开明细') + " ", 1),
                            _createVNode(_component_VIcon, {
                              icon: isOpDetailOpen(record.operation_id) ? 'mdi-chevron-up' : 'mdi-chevron-down',
                              size: "14"
                            }, null, 8, ["icon"])
                          ], 8, _hoisted_176))
                        : _createCommentVNode("", true),
                      (isOpDetailOpen(record.operation_id))
                        ? (_openBlock(), _createElementBlock("ul", _hoisted_177, [
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(opDetailItems(record), (it, idx) => {
                              return (_openBlock(), _createElementBlock("li", { key: idx }, [
                                _createElementVNode("span", _hoisted_178, [
                                  (itemSourceText(it.source))
                                    ? (_openBlock(), _createElementBlock("em", _hoisted_179, _toDisplayString(itemSourceText(it.source)), 1))
                                    : _createCommentVNode("", true),
                                  _createElementVNode("span", {
                                    class: "magicflow-events__detail-title",
                                    title: it.title || it.hash
                                  }, _toDisplayString(it.title || it.hash || '—'), 9, _hoisted_180)
                                ]),
                                _createElementVNode("span", _hoisted_181, [
                                  (it.reason)
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                        _createTextVNode(_toDisplayString(it.reason), 1)
                                      ], 64))
                                    : _createCommentVNode("", true),
                                  (it.size_gb)
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                        _createTextVNode(" · " + _toDisplayString(Number(it.size_gb).toFixed(2)) + "G", 1)
                                      ], 64))
                                    : _createCommentVNode("", true),
                                  (it.seeders)
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                                        _createTextVNode(" · 做种 " + _toDisplayString(it.seeders), 1)
                                      ], 64))
                                    : _createCommentVNode("", true)
                                ])
                              ]))
                            }), 128))
                          ]))
                        : _createCommentVNode("", true)
                    ])
                  ]))
                }), 128)),
                (!(operationData.value.operations || []).length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_182, "暂无操作记录"))
                  : _createCommentVNode("", true)
              ])
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(TaskEditorDialog, {
      modelValue: editorOpen.value,
      "onUpdate:modelValue": _cache[39] || (_cache[39] = $event => ((editorOpen).value = $event)),
      task: editorTask.value,
      sites: status.value.options.sites,
      downloaders: status.value.options.downloaders,
      "default-save-path": defaultSavePath.value,
      saving: saving.value,
      onSave: saveTask
    }, null, 8, ["modelValue", "task", "sites", "downloaders", "default-save-path", "saving"]),
    _createVNode(_component_VDialog, {
      modelValue: settingsDialog.value,
      "onUpdate:modelValue": _cache[154] || (_cache[154] = $event => ((settingsDialog).value = $event)),
      "max-width": "40rem",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-settings-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_183, [
              (isNarrow.value && settingsPane.value === 'form')
                ? (_openBlock(), _createBlock(_component_VBtn, {
                    key: 0,
                    icon: "mdi-arrow-left",
                    size: "small",
                    variant: "text",
                    "aria-label": "返回设置目录",
                    onClick: backToSettingsDir
                  }))
                : _createCommentVNode("", true),
              _createElementVNode("span", _hoisted_184, _toDisplayString(isNarrow.value && settingsPane.value === 'form' ? settingsTabLabel(settingsTab.value) : '插件设置'), 1),
              _cache[366] || (_cache[366] = _createElementVNode("span", { class: "magicflow-scope-tag" }, "全局", -1)),
              _createVNode(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[40] || (_cache[40] = $event => (settingsDialog.value = false))
              })
            ]),
            (!isNarrow.value || settingsPane.value === 'dir')
              ? (_openBlock(), _createElementBlock("div", {
                  key: 0,
                  class: "magicflow-settings-nav",
                  ref_key: "settingsNavEl",
                  ref: settingsNavEl
                }, [
                  (_openBlock(), _createElementBlock(_Fragment, null, _renderList(MF_SETTINGS_TABS, (t) => {
                    return _createElementVNode("button", {
                      key: t.key,
                      type: "button",
                      class: _normalizeClass(["magicflow-settings-nav__item", { 'is-active': settingsTab.value === t.key }]),
                      onClick: $event => (openSettingsTab(t.key))
                    }, [
                      _createVNode(_component_VIcon, {
                        icon: t.icon,
                        size: "18"
                      }, null, 8, ["icon"]),
                      _createElementVNode("span", null, _toDisplayString(t.label), 1)
                    ], 10, _hoisted_185)
                  }), 64))
                ], 512))
              : _createCommentVNode("", true),
            _createVNode(_component_VTabs, {
              modelValue: settingsTab.value,
              "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((settingsTab).value = $event)),
              class: "magicflow-settings-dialog__tabs",
              density: "comfortable",
              "show-arrows": ""
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTab, {
                  value: "general",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[367] || (_cache[367] = [
                    _createTextVNode("常规", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "downloader",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[368] || (_cache[368] = [
                    _createTextVNode("下载与目录", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "template",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[369] || (_cache[369] = [
                    _createTextVNode("默认任务模板", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "iyuu",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[370] || (_cache[370] = [
                    _createTextVNode("IYUU 辅种", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "fallback",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[371] || (_cache[371] = [
                    _createTextVNode("元数据兜底", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "cloud",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[372] || (_cache[372] = [
                    _createTextVNode("云盘归档", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "exam",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[373] || (_cache[373] = [
                    _createTextVNode("考核", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "signin",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[374] || (_cache[374] = [
                    _createTextVNode("签到", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "live",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[375] || (_cache[375] = [
                    _createTextVNode("站点监控", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "recommend",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[376] || (_cache[376] = [
                    _createTextVNode("推荐", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "crossseed",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[377] || (_cache[377] = [
                    _createTextVNode("跨站", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "rules",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[378] || (_cache[378] = [
                    _createTextVNode("站点规则", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "tags",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[379] || (_cache[379] = [
                    _createTextVNode("标签管理", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            }, 8, ["modelValue"]),
            (!isNarrow.value || settingsPane.value === 'form')
              ? (_openBlock(), _createBlock(_component_VDivider, { key: 1 }))
              : _createCommentVNode("", true),
            (!isNarrow.value || settingsPane.value === 'form')
              ? (_openBlock(), _createElementBlock("div", _hoisted_186, [
                  (settingsTab.value === 'general')
                    ? (_openBlock(), _createElementBlock("div", _hoisted_187, [
                        _createVNode(_component_VSwitch, {
                          modelValue: settingsDraft.value.enabled,
                          "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((settingsDraft.value.enabled) = $event)),
                          label: "启用插件（总开关）",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VSwitch, {
                          modelValue: settingsDraft.value.show_sidebar_nav,
                          "onUpdate:modelValue": _cache[43] || (_cache[43] = $event => ((settingsDraft.value.show_sidebar_nav) = $event)),
                          label: "显示侧栏入口",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VTextField, {
                          modelValue: settingsDraft.value.request_interval,
                          "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((settingsDraft.value.request_interval) = $event)),
                          modelModifiers: { number: true },
                          type: "number",
                          min: "0",
                          step: "0.5",
                          label: "站点请求间隔（秒）",
                          hint: "站点翻页请求之间的最小间隔，0 = 不限速；对强流控站点可适当加大",
                          "persistent-hint": "",
                          variant: "outlined",
                          density: "comfortable"
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VTextField, {
                          modelValue: settingsDraft.value.journal_keep,
                          "onUpdate:modelValue": _cache[45] || (_cache[45] = $event => ((settingsDraft.value.journal_keep) = $event)),
                          modelModifiers: { number: true },
                          type: "number",
                          min: "0",
                          label: "操作记录保留上限",
                          hint: "每个任务最多保留的操作记录条数，0 = 不限",
                          "persistent-hint": "",
                          variant: "outlined",
                          density: "comfortable"
                        }, null, 8, ["modelValue"]),
                        _cache[380] || (_cache[380] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                          _createTextVNode(" 任务流量：按「在跑的任务类型」自动设 qB "),
                          _createElementVNode("strong", null, "全局上传限速"),
                          _createTextVNode("（只限上传，不动下载）。有刷流任务时用刷流档，只有魔力任务时用魔力档；两者同时在跑取刷流档；一个启用的任务都没有则清除限速。 ")
                        ], -1)),
                        _createElementVNode("div", _hoisted_188, [
                          _createVNode(_component_VTextField, {
                            modelValue: settingsDraft.value.bonus_upload_limit_kbps,
                            "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((settingsDraft.value.bonus_upload_limit_kbps) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            step: "10",
                            label: "魔力任务上传限速（KB/s）",
                            hint: "仅有魔力任务在跑时生效，0 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            modelValue: settingsDraft.value.brush_upload_limit_kbps,
                            "onUpdate:modelValue": _cache[47] || (_cache[47] = $event => ((settingsDraft.value.brush_upload_limit_kbps) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            step: "10",
                            label: "刷流任务上传限速（KB/s）",
                            hint: "有刷流任务在跑时生效（优先），0 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            modelValue: settingsDraft.value.seed_up_limit_kbps,
                            "onUpdate:modelValue": _cache[48] || (_cache[48] = $event => ((settingsDraft.value.seed_up_limit_kbps) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            step: "50",
                            label: "挂种单种上传限速（KB/s）",
                            hint: "我们管控的魔力 / 推荐 / 跨站种：单种限速，默认 200；不在管控下的种不限速；0 = 全不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            modelValue: settingsDraft.value.brush_seed_up_limit_kbps,
                            "onUpdate:modelValue": _cache[49] || (_cache[49] = $event => ((settingsDraft.value.brush_seed_up_limit_kbps) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            step: "256",
                            label: "刷流单种上传限速（KB/s）",
                            hint: "我们管控的刷流种：要冲量，默认 5120（=5 MB/s）；0 = 不限",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"])
                        ]),
                        _createVNode(_component_VSwitch, {
                          modelValue: settingsDraft.value.debug_log,
                          "onUpdate:modelValue": _cache[50] || (_cache[50] = $event => ((settingsDraft.value.debug_log) = $event)),
                          label: "调试日志",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VSwitch, {
                          modelValue: settingsDraft.value.compact_mode,
                          "onUpdate:modelValue": _cache[51] || (_cache[51] = $event => ((settingsDraft.value.compact_mode) = $event)),
                          label: "紧凑模式",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8, ["modelValue"])
                      ]))
                    : (settingsTab.value === 'downloader')
                      ? (_openBlock(), _createElementBlock("div", _hoisted_189, [
                          _cache[381] || (_cache[381] = _createElementVNode("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, " 以下为 qBittorrent 全局参数，将直接写入下载器，会影响所有使用该下载器的插件。 ", -1)),
                          _createElementVNode("div", _hoisted_190, [
                            _createVNode(_component_VTextField, {
                              modelValue: downloaderPrefsDraft.value.download_limit_kbps,
                              "onUpdate:modelValue": _cache[52] || (_cache[52] = $event => ((downloaderPrefsDraft.value.download_limit_kbps) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "0",
                              label: "最大下载速度",
                              suffix: "KB/s",
                              hint: "0 = 不限",
                              "persistent-hint": "",
                              variant: "outlined",
                              density: "comfortable"
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: downloaderPrefsDraft.value.upload_limit_kbps,
                              "onUpdate:modelValue": _cache[53] || (_cache[53] = $event => ((downloaderPrefsDraft.value.upload_limit_kbps) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "0",
                              label: "最大上传速度",
                              suffix: "KB/s",
                              hint: "0 = 不限",
                              "persistent-hint": "",
                              variant: "outlined",
                              density: "comfortable"
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: downloaderPrefsDraft.value.max_connec,
                              "onUpdate:modelValue": _cache[54] || (_cache[54] = $event => ((downloaderPrefsDraft.value.max_connec) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "0",
                              label: "最大连接数",
                              variant: "outlined",
                              density: "comfortable",
                              "hide-details": ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: downloaderPrefsDraft.value.max_connec_per_torrent,
                              "onUpdate:modelValue": _cache[55] || (_cache[55] = $event => ((downloaderPrefsDraft.value.max_connec_per_torrent) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "0",
                              label: "每种子连接数",
                              variant: "outlined",
                              density: "comfortable",
                              "hide-details": ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: downloaderPrefsDraft.value.max_uploads,
                              "onUpdate:modelValue": _cache[56] || (_cache[56] = $event => ((downloaderPrefsDraft.value.max_uploads) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "-1",
                              label: "最大上传连接数",
                              hint: "-1 = 不限",
                              "persistent-hint": "",
                              variant: "outlined",
                              density: "comfortable"
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: downloaderPrefsDraft.value.max_uploads_per_torrent,
                              "onUpdate:modelValue": _cache[57] || (_cache[57] = $event => ((downloaderPrefsDraft.value.max_uploads_per_torrent) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "-1",
                              label: "每种子上传连接数",
                              hint: "-1 = 不限",
                              "persistent-hint": "",
                              variant: "outlined",
                              density: "comfortable"
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: downloaderPrefsDraft.value.max_active_downloads,
                              "onUpdate:modelValue": _cache[58] || (_cache[58] = $event => ((downloaderPrefsDraft.value.max_active_downloads) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "-1",
                              label: "最大活动下载数",
                              hint: "排队不计入；-1 = 不限",
                              "persistent-hint": "",
                              variant: "outlined",
                              density: "comfortable"
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VTextField, {
                              modelValue: downloaderPrefsDraft.value.max_active_torrents,
                              "onUpdate:modelValue": _cache[59] || (_cache[59] = $event => ((downloaderPrefsDraft.value.max_active_torrents) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              min: "-1",
                              label: "最大活动种子数",
                              hint: "-1 = 不限",
                              "persistent-hint": "",
                              variant: "outlined",
                              density: "comfortable"
                            }, null, 8, ["modelValue"])
                          ]),
                          _createVNode(_component_VSwitch, {
                            modelValue: downloaderPrefsDraft.value.queueing_enabled,
                            "onUpdate:modelValue": _cache[60] || (_cache[60] = $event => ((downloaderPrefsDraft.value.queueing_enabled) = $event)),
                            label: "启用队列限制（活动数上限生效的前提）",
                            color: "primary",
                            "hide-details": "",
                            inset: ""
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VDivider, { class: "my-3" }),
                          _cache[382] || (_cache[382] = _createElementVNode("p", { class: "magicflow-settings-hint" }, " qBittorrent 全局目录，写入后影响所有使用该下载器的插件。 ", -1)),
                          _createVNode(_component_VTextField, {
                            modelValue: downloaderPathsDraft.value.save_path,
                            "onUpdate:modelValue": _cache[61] || (_cache[61] = $event => ((downloaderPathsDraft.value.save_path) = $event)),
                            label: "默认保存路径",
                            placeholder: "如 /vol3/1000/media",
                            variant: "outlined",
                            density: "comfortable",
                            "hide-details": ""
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            modelValue: downloaderPathsDraft.value.temp_path,
                            "onUpdate:modelValue": _cache[62] || (_cache[62] = $event => ((downloaderPathsDraft.value.temp_path) = $event)),
                            label: "临时下载路径",
                            placeholder: "下载中暂存目录",
                            variant: "outlined",
                            density: "comfortable",
                            "hide-details": ""
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VSwitch, {
                            modelValue: downloaderPathsDraft.value.temp_path_enabled,
                            "onUpdate:modelValue": _cache[63] || (_cache[63] = $event => ((downloaderPathsDraft.value.temp_path_enabled) = $event)),
                            label: "启用临时下载路径（下载中放临时目录，完成后移入保存路径）",
                            color: "primary",
                            "hide-details": "",
                            inset: ""
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VDivider, { class: "my-2" }),
                          _cache[383] || (_cache[383] = _createElementVNode("p", { class: "magicflow-settings-hint" }, " 任务保存目录：仅对魔流生效，不影响下载器全局设置。 ", -1)),
                          _createVNode(_component_VTextField, {
                            modelValue: defaultsDraft.value.save_path,
                            "onUpdate:modelValue": _cache[64] || (_cache[64] = $event => ((defaultsDraft.value.save_path) = $event)),
                            label: "任务保存目录",
                            placeholder: "如 /vol3/1000/media/magicflow",
                            hint: "新建任务时自动预填此目录（不影响已有任务，任务内仍可单独修改）",
                            "persistent-hint": "",
                            variant: "outlined",
                            density: "comfortable"
                          }, null, 8, ["modelValue"])
                        ]))
                      : (settingsTab.value === 'iyuu')
                        ? (_openBlock(), _createElementBlock("div", _hoisted_191, [
                            _cache[389] || (_cache[389] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                              _createTextVNode(" IYUU 云端辅种为"),
                              _createElementVNode("strong", null, "可选增强"),
                              _createTextVNode("：填写 Token 后，复用/刷流会优先用 IYUU 云端匹配"),
                              _createElementVNode("strong", null, "他站同资源"),
                              _createTextVNode("； 下方站点密钥可手填（留空则自动尝试用 MoviePilot 已存的 apikey / cookie 取链）。 "),
                              _createElementVNode("strong", null, "不填 Token 则完全不启用"),
                              _createTextVNode("，一切照旧走内置跨站特征码方案。 ")
                            ], -1)),
                            _createElementVNode("div", _hoisted_192, [
                              _createVNode(_component_VTextField, {
                                modelValue: settingsDraft.value.iyuu_token,
                                "onUpdate:modelValue": _cache[65] || (_cache[65] = $event => ((settingsDraft.value.iyuu_token) = $event)),
                                label: "IYUU 云端 Token",
                                placeholder: "留空 = 不启用 IYUU 辅种",
                                variant: "outlined",
                                density: "comfortable",
                                "hide-details": "",
                                autocomplete: "off"
                              }, null, 8, ["modelValue"]),
                              _createVNode(_component_VBtn, {
                                variant: "tonal",
                                color: "primary",
                                size: "small",
                                "prepend-icon": "mdi-connection",
                                loading: iyuuTesting.value,
                                disabled: !settingsDraft.value.iyuu_token,
                                onClick: testIyuu
                              }, {
                                default: _withCtx(() => [...(_cache[384] || (_cache[384] = [
                                  _createTextVNode("测试", -1)
                                ]))]),
                                _: 1
                              }, 8, ["loading", "disabled"]),
                              (settingsDraft.value.iyuu_token)
                                ? (_openBlock(), _createBlock(_component_VBtn, {
                                    key: 0,
                                    variant: "text",
                                    color: "error",
                                    size: "small",
                                    "prepend-icon": "mdi-close-circle-outline",
                                    onClick: clearIyuuToken
                                  }, {
                                    default: _withCtx(() => [...(_cache[385] || (_cache[385] = [
                                      _createTextVNode("清空", -1)
                                    ]))]),
                                    _: 1
                                  }))
                                : _createCommentVNode("", true)
                            ]),
                            _createElementVNode("div", _hoisted_193, [
                              _createElementVNode("div", _hoisted_194, [
                                _cache[386] || (_cache[386] = _createElementVNode("span", null, "站点密钥（按 MoviePilot 已配置站点生成）", -1)),
                                (iyuuStatus.value)
                                  ? (_openBlock(), _createBlock(_component_VChip, {
                                      key: 0,
                                      size: "x-small",
                                      variant: "tonal",
                                      color: iyuuStatus.value.enabled ? 'success' : 'grey'
                                    }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(iyuuStatus.value.enabled ? '已启用' : '未启用'), 1)
                                      ]),
                                      _: 1
                                    }, 8, ["color"]))
                                  : _createCommentVNode("", true)
                              ]),
                              (iyuuLoading.value)
                                ? (_openBlock(), _createElementBlock("p", _hoisted_195, "加载中…"))
                                : (!iyuuSites.value.length)
                                  ? (_openBlock(), _createElementBlock("p", _hoisted_196, " 未检测到已配置站点（请先在 MoviePilot 中添加站点）。 "))
                                  : _createCommentVNode("", true),
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(iyuuSites.value, (row) => {
                                return (_openBlock(), _createElementBlock("div", {
                                  key: row.domain || row.name,
                                  class: "magicflow-iyuu-row"
                                }, [
                                  _createElementVNode("div", _hoisted_197, [
                                    _createElementVNode("span", _hoisted_198, _toDisplayString(row.name), 1),
                                    (row.iyuu_sid)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 0,
                                          size: "x-small",
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx(() => [
                                            _createTextVNode("IYUU #" + _toDisplayString(row.iyuu_sid), 1)
                                          ]),
                                          _: 2
                                        }, 1024))
                                      : _createCommentVNode("", true),
                                    (row.has_apikey)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 1,
                                          size: "x-small",
                                          variant: "tonal",
                                          color: "success"
                                        }, {
                                          default: _withCtx(() => [...(_cache[387] || (_cache[387] = [
                                            _createTextVNode("API", -1)
                                          ]))]),
                                          _: 1
                                        }))
                                      : _createCommentVNode("", true),
                                    (row.has_cookie)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 2,
                                          size: "x-small",
                                          variant: "tonal",
                                          color: "info"
                                        }, {
                                          default: _withCtx(() => [...(_cache[388] || (_cache[388] = [
                                            _createTextVNode("Cookie", -1)
                                          ]))]),
                                          _: 1
                                        }))
                                      : _createCommentVNode("", true),
                                    _createVNode(_component_VSpacer),
                                    _createVNode(_component_VBtn, {
                                      size: "x-small",
                                      variant: "text",
                                      "append-icon": iyuuShowMore.value[row.domain || row.name] ? 'mdi-chevron-up' : 'mdi-chevron-down',
                                      onClick: $event => (iyuuShowMore.value[row.domain || row.name] = !iyuuShowMore.value[row.domain || row.name])
                                    }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(iyuuShowMore.value[row.domain || row.name] ? '收起' : '更多'), 1)
                                      ]),
                                      _: 2
                                    }, 1032, ["append-icon", "onClick"])
                                  ]),
                                  _createElementVNode("div", _hoisted_199, [
                                    _createVNode(_component_VTextField, {
                                      modelValue: row.passkey,
                                      "onUpdate:modelValue": $event => ((row.passkey) = $event),
                                      label: "passkey",
                                      placeholder: "留空 = 自动获取",
                                      variant: "outlined",
                                      density: "compact",
                                      "hide-details": "",
                                      autocomplete: "off"
                                    }, null, 8, ["modelValue", "onUpdate:modelValue"]),
                                    _createVNode(_component_VTextField, {
                                      modelValue: row.uid,
                                      "onUpdate:modelValue": $event => ((row.uid) = $event),
                                      label: "uid（可选）",
                                      variant: "outlined",
                                      density: "compact",
                                      "hide-details": "",
                                      autocomplete: "off"
                                    }, null, 8, ["modelValue", "onUpdate:modelValue"])
                                  ]),
                                  (iyuuShowMore.value[row.domain || row.name])
                                    ? (_openBlock(), _createBlock(_component_VTextField, {
                                        key: 0,
                                        modelValue: row.downhash,
                                        "onUpdate:modelValue": $event => ((row.downhash) = $event),
                                        label: "downhash（可选）",
                                        variant: "outlined",
                                        density: "compact",
                                        "hide-details": "",
                                        autocomplete: "off"
                                      }, null, 8, ["modelValue", "onUpdate:modelValue"]))
                                    : _createCommentVNode("", true)
                                ]))
                              }), 128))
                            ])
                          ]))
                        : (settingsTab.value === 'template')
                          ? (_openBlock(), _createElementBlock("div", _hoisted_200, [
                              _cache[390] || (_cache[390] = _createElementVNode("p", { class: "magicflow-settings-hint" }, " 仅用于新建任务时预填，不影响已有任务。 ", -1)),
                              _createElementVNode("div", _hoisted_201, [
                                _createVNode(_component_VSelect, {
                                  modelValue: defaultsDraft.value.downloader,
                                  "onUpdate:modelValue": _cache[66] || (_cache[66] = $event => ((defaultsDraft.value.downloader) = $event)),
                                  items: status.value.options.downloaders,
                                  label: "默认下载器",
                                  placeholder: "不指定（新建任务时再选）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "items"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: defaultsDraft.value.brush_interval,
                                  "onUpdate:modelValue": _cache[67] || (_cache[67] = $event => ((defaultsDraft.value.brush_interval) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  min: "1",
                                  label: "选种周期（分钟）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: defaultsDraft.value.check_interval,
                                  "onUpdate:modelValue": _cache[68] || (_cache[68] = $event => ((defaultsDraft.value.check_interval) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  min: "1",
                                  label: "检查周期（分钟）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: defaultsDraft.value.max_add_per_run,
                                  "onUpdate:modelValue": _cache[69] || (_cache[69] = $event => ((defaultsDraft.value.max_add_per_run) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  min: "1",
                                  label: "单轮最多新增",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: defaultsDraft.value.max_download_concurrent,
                                  "onUpdate:modelValue": _cache[70] || (_cache[70] = $event => ((defaultsDraft.value.max_download_concurrent) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  min: "1",
                                  label: "同时下载数上限",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: defaultsDraft.value.top_n,
                                  "onUpdate:modelValue": _cache[71] || (_cache[71] = $event => ((defaultsDraft.value.top_n) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  min: "1",
                                  label: "候选 TopN",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: defaultsDraft.value.browse_pages,
                                  "onUpdate:modelValue": _cache[72] || (_cache[72] = $event => ((defaultsDraft.value.browse_pages) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  min: "1",
                                  label: "每轮翻页数",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: defaultsDraft.value.seen_cooldown_hours,
                                  "onUpdate:modelValue": _cache[73] || (_cache[73] = $event => ((defaultsDraft.value.seen_cooldown_hours) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  min: "0",
                                  label: "候选去重冷却（小时）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VTextField, {
                                  modelValue: defaultsDraft.value.brush_seed_days,
                                  "onUpdate:modelValue": _cache[74] || (_cache[74] = $event => ((defaultsDraft.value.brush_seed_days) = $event)),
                                  modelModifiers: { number: true },
                                  type: "number",
                                  min: "0",
                                  max: "365",
                                  label: "刷流保种天数（0=按无上传）",
                                  variant: "outlined",
                                  density: "comfortable",
                                  "hide-details": ""
                                }, null, 8, ["modelValue"])
                              ]),
                              _createElementVNode("div", _hoisted_202, [
                                _createVNode(_component_VSwitch, {
                                  modelValue: defaultsDraft.value.refill_when_empty,
                                  "onUpdate:modelValue": _cache[75] || (_cache[75] = $event => ((defaultsDraft.value.refill_when_empty) = $event)),
                                  label: "清理后自动补种",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VSwitch, {
                                  modelValue: defaultsDraft.value.reuse_existing,
                                  "onUpdate:modelValue": _cache[76] || (_cache[76] = $event => ((defaultsDraft.value.reuse_existing) = $event)),
                                  label: "复用本机已有资源（辅种）",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VSwitch, {
                                  modelValue: defaultsDraft.value.reuse_verify,
                                  "onUpdate:modelValue": _cache[77] || (_cache[77] = $event => ((defaultsDraft.value.reuse_verify) = $event)),
                                  label: "辅种前校验",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VSwitch, {
                                  modelValue: defaultsDraft.value.cleanup_no_progress,
                                  "onUpdate:modelValue": _cache[78] || (_cache[78] = $event => ((defaultsDraft.value.cleanup_no_progress) = $event)),
                                  label: "清理无进度种子",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VSwitch, {
                                  modelValue: defaultsDraft.value.cleanup_slow_progress,
                                  "onUpdate:modelValue": _cache[79] || (_cache[79] = $event => ((defaultsDraft.value.cleanup_slow_progress) = $event)),
                                  label: "清理过慢种子",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VSwitch, {
                                  modelValue: defaultsDraft.value.purge_unfree_incomplete,
                                  "onUpdate:modelValue": _cache[80] || (_cache[80] = $event => ((defaultsDraft.value.purge_unfree_incomplete) = $event)),
                                  label: "清理「已非免费」未下完种子",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VSwitch, {
                                  modelValue: defaultsDraft.value.auto_resume_paused,
                                  "onUpdate:modelValue": _cache[81] || (_cache[81] = $event => ((defaultsDraft.value.auto_resume_paused) = $event)),
                                  label: "自动恢复被暂停种子",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"]),
                                _createVNode(_component_VSwitch, {
                                  modelValue: defaultsDraft.value.delete_files,
                                  "onUpdate:modelValue": _cache[82] || (_cache[82] = $event => ((defaultsDraft.value.delete_files) = $event)),
                                  label: "删种同时删除文件",
                                  color: "primary",
                                  "hide-details": "",
                                  inset: ""
                                }, null, 8, ["modelValue"])
                              ])
                            ]))
                          : (settingsTab.value === 'exam')
                            ? (_openBlock(), _createElementBlock("div", _hoisted_203, [
                                _cache[393] || (_cache[393] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                  _createTextVNode(" 把各站"),
                                  _createElementVNode("strong", null, "新手考核"),
                                  _createTextVNode("进度抓出来（上传/下载增量、平均做种时间、魔力/做种积分增量）， 并支持"),
                                  _createElementVNode("strong", null, "一键起任务"),
                                  _createTextVNode("去补未通过项。 数据来源就是各站首页 "),
                                  _createElementVNode("code", null, "index.php"),
                                  _createTextVNode(" 的考核块 —— 魔流本来就抓这个页面拿实时数据， 所以"),
                                  _createElementVNode("strong", null, "不额外消耗站点访问次数（PV）"),
                                  _createTextVNode("。 ")
                                ], -1)),
                                _cache[394] || (_cache[394] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                  _createElementVNode("strong", null, "已通过的考核默认不显示"),
                                  _createTextVNode("（过掉的就不占地方了）；想看全部就打开下面的「显示已通过」。 考不过的站会算好缺口并给出建议：上传差多少 → 刷流任务；下载差多少 → 专门下载任务； 魔力/积分差多少 → 魔力任务；平均做种时间不够 → 保持做种 + 多辅种（不用建任务）。 ")
                                ], -1)),
                                _cache[395] || (_cache[395] = _createElementVNode("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, [
                                  _createTextVNode(" ⚠️ 「考核下载」任务会"),
                                  _createElementVNode("strong", null, "真的下载非免费种"),
                                  _createTextVNode("（下载增量只能在有下载时增长）， 会拉低分享率。魔流会在它跑的时候"),
                                  _createElementVNode("strong", null, "豁免「清除非免费下载种」"),
                                  _createTextVNode("（否则会互相打架）， 并在"),
                                  _createElementVNode("strong", null, "全站免费期间"),
                                  _createTextVNode("提示你「免费期下载不计入下载量」。 ")
                                ], -1)),
                                _createElementVNode("div", _hoisted_204, [
                                  _createVNode(_component_VSwitch, {
                                    modelValue: settingsDraft.value.exam_enabled,
                                    "onUpdate:modelValue": _cache[83] || (_cache[83] = $event => ((settingsDraft.value.exam_enabled) = $event)),
                                    label: "启用「新手考核」（关闭则不抓取、不解析、不显示）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode(_component_VSwitch, {
                                    modelValue: settingsDraft.value.exam_include_pass,
                                    "onUpdate:modelValue": _cache[84] || (_cache[84] = $event => ((settingsDraft.value.exam_include_pass) = $event)),
                                    label: "显示「已通过」的考核（默认只显示未通过的）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"])
                                ]),
                                _createElementVNode("div", _hoisted_205, [
                                  _createVNode(_component_VSelect, {
                                    modelValue: settingsDraft.value.exam_sites,
                                    "onUpdate:modelValue": _cache[85] || (_cache[85] = $event => ((settingsDraft.value.exam_sites) = $event)),
                                    items: siteSelectItems.value,
                                    label: "考核站点（不选 = 全部已配置 Cookie 的站点）",
                                    multiple: "",
                                    chips: "",
                                    "closable-chips": "",
                                    variant: "outlined",
                                    density: "comfortable",
                                    "hide-details": ""
                                  }, null, 8, ["modelValue", "items"]),
                                  _cache[391] || (_cache[391] = _createElementVNode("p", { class: "magicflow-settings-hint" }, "选多少有多少：只盯你关心的站，不选就是全都盯。", -1))
                                ]),
                                (!settingsDraft.value.exam_enabled)
                                  ? (_openBlock(), _createElementBlock("p", _hoisted_206, [...(_cache[392] || (_cache[392] = [
                                      _createTextVNode(" 当前处于", -1),
                                      _createElementVNode("strong", null, "关闭", -1),
                                      _createTextVNode("状态：不会去抓考核，也不会做任何额外请求。 ", -1)
                                    ]))]))
                                  : _createCommentVNode("", true)
                              ]))
                            : (settingsTab.value === 'signin')
                              ? (_openBlock(), _createElementBlock("div", _hoisted_207, [
                                  _createElementVNode("div", _hoisted_208, [
                                    _createElementVNode("span", _hoisted_209, [
                                      _createVNode(_component_VIcon, {
                                        icon: "mdi-calendar-check-outline",
                                        size: "20"
                                      })
                                    ]),
                                    _createElementVNode("div", _hoisted_210, [
                                      _createElementVNode("div", _hoisted_211, [
                                        _cache[396] || (_cache[396] = _createElementVNode("span", null, "站点签到 / 模拟登录", -1)),
                                        _createVNode(_component_VChip, {
                                          size: "small",
                                          variant: "tonal",
                                          color: settingsDraft.value.signin_enabled ? 'success' : 'grey'
                                        }, {
                                          default: _withCtx(() => [
                                            _createTextVNode(_toDisplayString(settingsDraft.value.signin_enabled ? '已启用' : '已关闭'), 1)
                                          ]),
                                          _: 1
                                        }, 8, ["color"])
                                      ]),
                                      _cache[397] || (_cache[397] = _createElementVNode("div", { class: "magicflow-signin-hero__desc" }, " 勾选站点即可，其余全自动完成。 ", -1))
                                    ])
                                  ]),
                                  _createElementVNode("div", _hoisted_212, [
                                    _createElementVNode("div", _hoisted_213, [
                                      _createVNode(_component_VIcon, {
                                        icon: "mdi-toggle-switch-outline",
                                        size: "16"
                                      }),
                                      _cache[398] || (_cache[398] = _createTextVNode(" 开关", -1))
                                    ]),
                                    _createElementVNode("div", _hoisted_214, [
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.signin_enabled,
                                        "onUpdate:modelValue": _cache[86] || (_cache[86] = $event => ((settingsDraft.value.signin_enabled) = $event)),
                                        label: "启用站点签到 / 模拟登录",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: "",
                                        density: "comfortable"
                                      }, null, 8, ["modelValue"]),
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.signin_notify,
                                        "onUpdate:modelValue": _cache[87] || (_cache[87] = $event => ((settingsDraft.value.signin_notify) = $event)),
                                        label: "结果推送通知",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: "",
                                        density: "comfortable",
                                        disabled: !settingsDraft.value.signin_enabled
                                      }, null, 8, ["modelValue", "disabled"])
                                    ]),
                                    (!settingsDraft.value.signin_enabled)
                                      ? (_openBlock(), _createElementBlock("p", _hoisted_215, " 当前为关闭状态：不会签到、不会模拟登录，也不发任何请求。 "))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _createElementVNode("div", _hoisted_216, [
                                    _createElementVNode("div", _hoisted_217, [
                                      _createVNode(_component_VIcon, {
                                        icon: "mdi-web",
                                        size: "16"
                                      }),
                                      _cache[399] || (_cache[399] = _createTextVNode(" 站点选择（勾选即生效）", -1))
                                    ]),
                                    _createElementVNode("div", _hoisted_218, [
                                      _createElementVNode("div", _hoisted_219, [
                                        _createVNode(_component_VSelect, {
                                          modelValue: settingsDraft.value.signin_sites,
                                          "onUpdate:modelValue": _cache[88] || (_cache[88] = $event => ((settingsDraft.value.signin_sites) = $event)),
                                          items: siteSelectItems.value,
                                          label: "签到站点",
                                          multiple: "",
                                          chips: "",
                                          "closable-chips": "",
                                          variant: "outlined",
                                          density: "comfortable",
                                          "hide-details": ""
                                        }, null, 8, ["modelValue", "items"]),
                                        _createElementVNode("span", _hoisted_220, "已选 " + _toDisplayString((settingsDraft.value.signin_sites || []).length) + " 个站点", 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_221, [
                                        _createVNode(_component_VSelect, {
                                          modelValue: settingsDraft.value.signin_login_sites,
                                          "onUpdate:modelValue": _cache[89] || (_cache[89] = $event => ((settingsDraft.value.signin_login_sites) = $event)),
                                          items: siteSelectItems.value,
                                          label: "模拟登录站点",
                                          multiple: "",
                                          chips: "",
                                          "closable-chips": "",
                                          variant: "outlined",
                                          density: "comfortable",
                                          "hide-details": ""
                                        }, null, 8, ["modelValue", "items"]),
                                        _createElementVNode("span", _hoisted_222, "已选 " + _toDisplayString((settingsDraft.value.signin_login_sites || []).length) + " 个站点 · 保活 Cookie + 刷新站点数据", 1)
                                      ])
                                    ])
                                  ]),
                                  _createElementVNode("div", _hoisted_223, [
                                    _createVNode(_component_VBtn, {
                                      size: "small",
                                      color: "primary",
                                      variant: "tonal",
                                      "prepend-icon": "mdi-chart-box-outline",
                                      onClick: _cache[90] || (_cache[90] = $event => (openSignin()))
                                    }, {
                                      default: _withCtx(() => [...(_cache[400] || (_cache[400] = [
                                        _createTextVNode("查看签到报表", -1)
                                      ]))]),
                                      _: 1
                                    }),
                                    _cache[401] || (_cache[401] = _createElementVNode("span", { class: "magicflow-field__sub" }, "签到结果与近 7 天记录都在报表页", -1))
                                  ])
                                ]))
                              : (settingsTab.value === 'live')
                                ? (_openBlock(), _createElementBlock("div", _hoisted_224, [
                                    _cache[402] || (_cache[402] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                      _createTextVNode(" MoviePilot 的站点账号数据靠它自己的「站点数据刷新」任务写库（默认 "),
                                      _createElementVNode("strong", null, "6 小时"),
                                      _createTextVNode("一轮）， 对展示够用，但魔流是拿它"),
                                      _createElementVNode("strong", null, "做决策"),
                                      _createTextVNode("的（任务目标达标 / 救号分享率 / 兑换提醒）—— 滞后 6 小时就是真偏差。 启用后魔流"),
                                      _createElementVNode("strong", null, "直连站点用户栏页"),
                                      _createTextVNode("拿实时值（上传 / 下载 / 分享率 / 魔力 / 做种数）， 并监控"),
                                      _createElementVNode("strong", null, "「下载量在涨」"),
                                      _createTextVNode("——免费种不吃下载，下载量增长说明吃到促销尾巴了。 站点级缓存 + 单飞，抓不到自动回退 MP 数据。 ")
                                    ], -1)),
                                    _cache[403] || (_cache[403] = _createElementVNode("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, [
                                      _createTextVNode(" ⚠️ 多数站点有"),
                                      _createElementVNode("strong", null, "每日访问次数上限"),
                                      _createTextVNode("（实测 PTT：用户等级 300 PV/天，含刷流浏览）。 采样太频会把配额打光 → 站点当天拒绝访问（连刷流也取不到种）。命中后魔流会自动"),
                                      _createElementVNode("strong", null, "停抓到次日凌晨"),
                                      _createTextVNode("并告警， 但配额是共享的："),
                                      _createElementVNode("strong", null, "建议按站点把采样周期放长"),
                                      _createTextVNode("（比如 15–30 分钟），给选种浏览留余量。 ")
                                    ], -1)),
                                    _createElementVNode("div", _hoisted_225, [
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.live_enabled,
                                        "onUpdate:modelValue": _cache[91] || (_cache[91] = $event => ((settingsDraft.value.live_enabled) = $event)),
                                        label: "启用站点实时数据 + 流量监控",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8, ["modelValue"]),
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.live_notify,
                                        "onUpdate:modelValue": _cache[92] || (_cache[92] = $event => ((settingsDraft.value.live_notify) = $event)),
                                        label: "命中告警时推送通知",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8, ["modelValue"]),
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.live_auto_stop,
                                        "onUpdate:modelValue": _cache[93] || (_cache[93] = $event => ((settingsDraft.value.live_auto_stop) = $event)),
                                        label: "同时把该站「运行中」任务切「做种中」（停调度、不删种）",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8, ["modelValue"])
                                    ]),
                                    _createVNode(_component_VDivider, { class: "my-3" }),
                                    _cache[404] || (_cache[404] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                      _createElementVNode("strong", null, "流量兜底"),
                                      _createTextVNode("：下载中被判「非免费」就干掉，避免白烧下载量。 三处都会核对："),
                                      _createElementVNode("em", null, "任务内"),
                                      _createTextVNode("回种子详情页核对（开关在任务「高级」里，受本总开关约束）、 "),
                                      _createElementVNode("em", null, "全局"),
                                      _createTextVNode("用站点「正在下载」列表核对、"),
                                      _createElementVNode("em", null, "取种期间"),
                                      _createTextVNode("核对来源站。共用下面这个总开关。 ")
                                    ], -1)),
                                    _createElementVNode("div", _hoisted_226, [
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.promo_guard,
                                        "onUpdate:modelValue": _cache[94] || (_cache[94] = $event => ((settingsDraft.value.promo_guard) = $event)),
                                        label: "启用流量兜底（关掉 = 下面三项都只告警、不动手）",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8, ["modelValue"])
                                    ]),
                                    _createElementVNode("div", _hoisted_227, [
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.live_kill_unfree,
                                        "onUpdate:modelValue": _cache[95] || (_cache[95] = $event => ((settingsDraft.value.live_kill_unfree) = $event)),
                                        disabled: !settingsDraft.value.promo_guard,
                                        label: "全局：下载量异常增长 → 站点「正在下载」列表里非免费的种，从下载器干掉",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8, ["modelValue", "disabled"]),
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.live_kill_delete_files,
                                        "onUpdate:modelValue": _cache[96] || (_cache[96] = $event => ((settingsDraft.value.live_kill_delete_files) = $event)),
                                        disabled: !settingsDraft.value.promo_guard || !settingsDraft.value.live_kill_unfree,
                                        label: "干掉时连文件一起删（只动「下载中」且名称+体积对得上的种）",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8, ["modelValue", "disabled"]),
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.crossseed_guard,
                                        "onUpdate:modelValue": _cache[97] || (_cache[97] = $event => ((settingsDraft.value.crossseed_guard) = $event)),
                                        disabled: !settingsDraft.value.promo_guard,
                                        label: "取种期间：核对来源站免费状态与下载量增量，判错就删种并拉黑该站（强烈建议）",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8, ["modelValue", "disabled"])
                                    ]),
                                    _createElementVNode("div", _hoisted_228, [
                                      _createVNode(_component_VTextField, {
                                        modelValue: settingsDraft.value.crossseed_guard_pct,
                                        "onUpdate:modelValue": _cache[98] || (_cache[98] = $event => ((settingsDraft.value.crossseed_guard_pct) = $event)),
                                        modelModifiers: { number: true },
                                        type: "number",
                                        min: "0",
                                        max: "100",
                                        step: "0.5",
                                        disabled: !settingsDraft.value.promo_guard || !settingsDraft.value.crossseed_guard,
                                        label: "下载增量阈值（体积的 %）",
                                        hint: "来源站下载增量 > 目标体积 × 该值 即判定「不免费」，默认 5%",
                                        "persistent-hint": "",
                                        variant: "outlined",
                                        density: "comfortable"
                                      }, null, 8, ["modelValue", "disabled"]),
                                      _createVNode(_component_VTextField, {
                                        modelValue: settingsDraft.value.crossseed_guard_min_mb,
                                        "onUpdate:modelValue": _cache[99] || (_cache[99] = $event => ((settingsDraft.value.crossseed_guard_min_mb) = $event)),
                                        modelModifiers: { number: true },
                                        type: "number",
                                        min: "0",
                                        step: "10",
                                        disabled: !settingsDraft.value.promo_guard || !settingsDraft.value.crossseed_guard,
                                        label: "最小判定增量（MB）",
                                        hint: "避免统计抖动误判，默认 50MB",
                                        "persistent-hint": "",
                                        variant: "outlined",
                                        density: "comfortable"
                                      }, null, 8, ["modelValue", "disabled"]),
                                      _createVNode(_component_VTextField, {
                                        modelValue: settingsDraft.value.crossseed_guard_interval_min,
                                        "onUpdate:modelValue": _cache[100] || (_cache[100] = $event => ((settingsDraft.value.crossseed_guard_interval_min) = $event)),
                                        modelModifiers: { number: true },
                                        type: "number",
                                        min: "1",
                                        max: "1440",
                                        step: "1",
                                        disabled: !settingsDraft.value.promo_guard || !settingsDraft.value.crossseed_guard,
                                        label: "兜底核对间隔（分钟）",
                                        hint: "同一来源站两次核对的间隔，默认 15 分钟（各花 1 次站点请求）",
                                        "persistent-hint": "",
                                        variant: "outlined",
                                        density: "comfortable"
                                      }, null, 8, ["modelValue", "disabled"])
                                    ]),
                                    _createElementVNode("div", _hoisted_229, [
                                      _createVNode(_component_VTextField, {
                                        modelValue: settingsDraft.value.live_interval_minutes,
                                        "onUpdate:modelValue": _cache[101] || (_cache[101] = $event => ((settingsDraft.value.live_interval_minutes) = $event)),
                                        modelModifiers: { number: true },
                                        type: "number",
                                        min: "1",
                                        label: "采样周期（分钟）",
                                        hint: "默认 4 分钟；太频繁站点吃不消",
                                        "persistent-hint": "",
                                        variant: "outlined",
                                        density: "comfortable"
                                      }, null, 8, ["modelValue"]),
                                      _createVNode(_component_VTextField, {
                                        modelValue: settingsDraft.value.live_download_alert_mb,
                                        "onUpdate:modelValue": _cache[102] || (_cache[102] = $event => ((settingsDraft.value.live_download_alert_mb) = $event)),
                                        modelModifiers: { number: true },
                                        type: "number",
                                        min: "1",
                                        label: "下载增长告警阈值（MB/分钟）",
                                        hint: "超过则告警；默认 50",
                                        "persistent-hint": "",
                                        variant: "outlined",
                                        density: "comfortable"
                                      }, null, 8, ["modelValue"]),
                                      _createVNode(_component_VTextField, {
                                        modelValue: settingsDraft.value.live_ratio_target,
                                        "onUpdate:modelValue": _cache[103] || (_cache[103] = $event => ((settingsDraft.value.live_ratio_target) = $event)),
                                        modelModifiers: { number: true },
                                        type: "number",
                                        min: "0",
                                        step: "0.05",
                                        label: "分享率目标线",
                                        hint: "低于则告警并算缺口；0 = 不检查",
                                        "persistent-hint": "",
                                        variant: "outlined",
                                        density: "comfortable"
                                      }, null, 8, ["modelValue"])
                                    ]),
                                    (siteLiveAlerts.value.length)
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_230, [
                                          _createElementVNode("div", _hoisted_231, "当前「" + _toDisplayString(selectedTask.value?.name) + "」站点告警", 1),
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(siteLiveAlerts.value, (alert, idx) => {
                                            return (_openBlock(), _createElementBlock("div", {
                                              key: `live-cfg-${idx}`,
                                              class: _normalizeClass(["magicflow-live-alert", `magicflow-live-alert--${alert.level || 'info'}`])
                                            }, _toDisplayString(alert.text), 3))
                                          }), 128))
                                        ]))
                                      : _createCommentVNode("", true)
                                  ]))
                                : (settingsTab.value === 'recommend')
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_232, [
                                      _cache[405] || (_cache[405] = _createElementVNode("p", { class: "magicflow-settings-hint" }, " 刷流时顺带甄别「值得收藏 / 观看」的资源：命中的种子会打上推荐标签（受「媒体资产价值闸门」保护、不会被当临时种删掉）并通知你确认；错过确认窗口（过期 / 磁盘不足）则按临时种回收。 ", -1)),
                                      _createVNode(_component_VSwitch, {
                                        modelValue: settingsDraft.value.recommend_enabled,
                                        "onUpdate:modelValue": _cache[104] || (_cache[104] = $event => ((settingsDraft.value.recommend_enabled) = $event)),
                                        label: "启用推荐甄别",
                                        color: "primary",
                                        "hide-details": "",
                                        inset: ""
                                      }, null, 8, ["modelValue"]),
                                      _createElementVNode("div", _hoisted_233, [
                                        _createVNode(_component_VTextField, {
                                          modelValue: settingsDraft.value.recommend_min_rating,
                                          "onUpdate:modelValue": _cache[105] || (_cache[105] = $event => ((settingsDraft.value.recommend_min_rating) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          max: "10",
                                          step: "0.1",
                                          label: "评分门槛（高于）",
                                          hint: "评分高于该值才推荐，默认 7.5（评分源见左侧「评分来源」）",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"]),
                                        _createVNode(_component_VTextField, {
                                          modelValue: settingsDraft.value.recommend_expire_days,
                                          "onUpdate:modelValue": _cache[106] || (_cache[106] = $event => ((settingsDraft.value.recommend_expire_days) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "1",
                                          label: "推荐过期天数",
                                          hint: "超过该天数仍未确认则视为过期（0 = 不过期）",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"]),
                                        _createVNode(_component_VTextField, {
                                          modelValue: settingsDraft.value.recommend_temp_ttl_days,
                                          "onUpdate:modelValue": _cache[107] || (_cache[107] = $event => ((settingsDraft.value.recommend_temp_ttl_days) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "1",
                                          label: "临时种 TTL（天）",
                                          hint: "未入选推荐的普通刷流临时种，超过该天数回收",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"]),
                                        _createVNode(_component_VTextField, {
                                          modelValue: settingsDraft.value.recommend_disk_min_free_gb,
                                          "onUpdate:modelValue": _cache[108] || (_cache[108] = $event => ((settingsDraft.value.recommend_disk_min_free_gb) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "0",
                                          step: "1",
                                          label: "磁盘余量下限（GB）",
                                          hint: "剩余空间低于该值时，推荐立即视为过期",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"]),
                                        _createVNode(_component_VTextField, {
                                          modelValue: settingsDraft.value.recommend_douban_service_url,
                                          "onUpdate:modelValue": _cache[109] || (_cache[109] = $event => ((settingsDraft.value.recommend_douban_service_url) = $event)),
                                          label: "豆瓣服务地址",
                                          placeholder: "http://magicflow-douban:18789",
                                          hint: "独立服务 magicflow-douban 的地址，留空用默认；本地查询 <1ms，不受豆瓣限流影响",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"]),
                                        _createVNode(_component_VTextField, {
                                          modelValue: settingsDraft.value.recommend_tag,
                                          "onUpdate:modelValue": _cache[110] || (_cache[110] = $event => ((settingsDraft.value.recommend_tag) = $event)),
                                          label: "推荐标签",
                                          hint: "推荐资源单独打的标签，默认「魔流-推荐」",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _createElementVNode("div", _hoisted_234, [
                                        _createVNode(_component_VSelect, {
                                          modelValue: settingsDraft.value.recommend_rating_source,
                                          "onUpdate:modelValue": _cache[111] || (_cache[111] = $event => ((settingsDraft.value.recommend_rating_source) = $event)),
                                          items: ratingSourceItems,
                                          "item-title": "title",
                                          "item-value": "value",
                                          label: "评分来源",
                                          hint: "默认只用 TMDB；豆瓣优先走本地服务 magicflow-douban（不再直连豆瓣）",
                                          "persistent-hint": "",
                                          variant: "outlined",
                                          density: "comfortable"
                                        }, null, 8, ["modelValue"])
                                      ]),
                                      _createElementVNode("div", _hoisted_235, [
                                        _createVNode(_component_VSwitch, {
                                          modelValue: settingsDraft.value.recommend_require_chart,
                                          "onUpdate:modelValue": _cache[112] || (_cache[112] = $event => ((settingsDraft.value.recommend_require_chart) = $event)),
                                          label: "榜单 / 热映 / 订阅命中也算达标（与评分为「或」关系）",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue"]),
                                        _createVNode(_component_VSwitch, {
                                          modelValue: settingsDraft.value.recommend_auto_import,
                                          "onUpdate:modelValue": _cache[113] || (_cache[113] = $event => ((settingsDraft.value.recommend_auto_import) = $event)),
                                          label: "确认后自动整理入库",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue"]),
                                        _createVNode(_component_VSwitch, {
                                          modelValue: settingsDraft.value.recommend_notify,
                                          "onUpdate:modelValue": _cache[114] || (_cache[114] = $event => ((settingsDraft.value.recommend_notify) = $event)),
                                          label: "发现推荐时通知",
                                          color: "primary",
                                          "hide-details": "",
                                          inset: ""
                                        }, null, 8, ["modelValue"])
                                      ])
                                    ]))
                                  : (settingsTab.value === 'rules')
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_236, [
                                        _cache[418] || (_cache[418] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                          _createElementVNode("strong", null, "全站 H&R 的唯一入口"),
                                          _createTextVNode("：H&R 有无 / 最短保种时长 / 做种上限都在这一页 （跨站取种的「来源份」在兄弟站同样背 H&R 义务，例：学校 BTSchool 要挂种 10 小时）。 优先级："),
                                          _createElementVNode("strong", null, "手填 > 页面探测 > 内置 > 全局默认"),
                                          _createTextVNode("； 探测遵循「宁保守勿乐观」—— 抓不到就保持原值，绝不假设「没有 H&R」。 ")
                                        ], -1)),
                                        _createElementVNode("div", _hoisted_237, [
                                          _createVNode(_component_VSwitch, {
                                            modelValue: settingsDraft.value.rules_auto_refresh,
                                            "onUpdate:modelValue": _cache[115] || (_cache[115] = $event => ((settingsDraft.value.rules_auto_refresh) = $event)),
                                            label: "每周自动逐站探测规则并入库",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8, ["modelValue"])
                                        ]),
                                        _createVNode(_component_VDivider, { class: "my-3" }),
                                        _cache[419] || (_cache[419] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                          _createElementVNode("strong", null, "H&R 来源"),
                                          _createTextVNode("：只认"),
                                          _createElementVNode("strong", null, "收件箱「欢迎短讯」里给出的规则地址"),
                                          _createTextVNode("（🔗 已存下，可点开）； 页面里顺带抓到的 H&R 不算数。默认时长给"),
                                          _createElementVNode("strong", null, "表里未收录"),
                                          _createTextVNode("的站点兜底； 每站的时长直接改上表的「"),
                                          _createElementVNode("strong", null, "保种(h)"),
                                          _createTextVNode("」列（手填覆盖，优先级最高）。 ")
                                        ], -1)),
                                        _createElementVNode("div", _hoisted_238, [
                                          _createVNode(_component_VTextField, {
                                            modelValue: settingsDraft.value.crossseed_seed_hours_default,
                                            "onUpdate:modelValue": _cache[116] || (_cache[116] = $event => ((settingsDraft.value.crossseed_seed_hours_default) = $event)),
                                            modelModifiers: { number: true },
                                            type: "number",
                                            min: "0",
                                            max: "720",
                                            step: "1",
                                            label: "默认最短保种时长（小时）",
                                            hint: "未收录站点的 H&R 保种时长，默认 24h",
                                            "persistent-hint": "",
                                            variant: "outlined",
                                            density: "comfortable"
                                          }, null, 8, ["modelValue"])
                                        ]),
                                        _createElementVNode("div", _hoisted_239, [
                                          _createVNode(_component_VSwitch, {
                                            modelValue: settingsDraft.value.crossseed_guard_keep_seed,
                                            "onUpdate:modelValue": _cache[117] || (_cache[117] = $event => ((settingsDraft.value.crossseed_guard_keep_seed) = $event)),
                                            label: "来源份 H&R 保护（保种期内任何任务不得删/改标签）",
                                            color: "primary",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8, ["modelValue"]),
                                          _createVNode(_component_VSwitch, {
                                            modelValue: settingsDraft.value.crossseed_reclaim,
                                            "onUpdate:modelValue": _cache[118] || (_cache[118] = $event => ((settingsDraft.value.crossseed_reclaim) = $event)),
                                            label: "H&R 期满后回收来源份（只删种子不删文件）",
                                            color: "warning",
                                            "hide-details": "",
                                            inset: ""
                                          }, null, 8, ["modelValue"])
                                        ]),
                                        _createElementVNode("div", _hoisted_240, [
                                          _createVNode(_component_VBtn, {
                                            size: "small",
                                            color: "primary",
                                            variant: "tonal",
                                            loading: rulesProbing.value,
                                            onClick: _cache[119] || (_cache[119] = $event => (probeRules()))
                                          }, {
                                            default: _withCtx(() => [
                                              _createVNode(_component_VIcon, {
                                                start: "",
                                                size: "small"
                                              }, {
                                                default: _withCtx(() => [...(_cache[406] || (_cache[406] = [
                                                  _createTextVNode("mdi-download-network-outline", -1)
                                                ]))]),
                                                _: 1
                                              }),
                                              _cache[407] || (_cache[407] = _createTextVNode("逐站拉取（探测页面） ", -1))
                                            ]),
                                            _: 1
                                          }, 8, ["loading"]),
                                          _createVNode(_component_VBtn, {
                                            size: "small",
                                            variant: "text",
                                            disabled: rulesLoading.value,
                                            onClick: refreshRules
                                          }, {
                                            default: _withCtx(() => [...(_cache[408] || (_cache[408] = [
                                              _createTextVNode("按 MP 配置补全", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["disabled"]),
                                          _createVNode(_component_VSpacer),
                                          _createElementVNode("span", _hoisted_241, "共 " + _toDisplayString(siteRules.value.length) + " 条", 1)
                                        ]),
                                        (rulesProbing.value)
                                          ? (_openBlock(), _createElementBlock("p", _hoisted_242, "正在逐站抓取规则页（每站 1~2 个请求，站间随机歇 1.5~3.5 秒）…"))
                                          : _createCommentVNode("", true),
                                        _createElementVNode("div", _hoisted_243, [
                                          _cache[417] || (_cache[417] = _createElementVNode("div", { class: "magicflow-rules-row magicflow-rules-row--head" }, [
                                            _createElementVNode("span", null, "站点"),
                                            _createElementVNode("span", null, "H&R"),
                                            _createElementVNode("span", null, "保种(h)"),
                                            _createElementVNode("span", null, "做种上限"),
                                            _createElementVNode("span", null, "来源"),
                                            _createElementVNode("span", null, "操作")
                                          ], -1)),
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(siteRules.value, (row) => {
                                            return (_openBlock(), _createElementBlock("div", {
                                              key: row.domain,
                                              class: "magicflow-rules-row"
                                            }, [
                                              _createElementVNode("span", {
                                                class: "magicflow-rules-row__name",
                                                title: row.domain
                                              }, [
                                                _createTextVNode(_toDisplayString(row.site_name || row.domain) + " ", 1),
                                                (!row.in_library)
                                                  ? (_openBlock(), _createElementBlock("em", _hoisted_245, "未入库"))
                                                  : _createCommentVNode("", true),
                                                (row.exam_avg_hours)
                                                  ? (_openBlock(), _createElementBlock("em", {
                                                      key: 1,
                                                      title: row.exam_evidence || '站点考核的平均做种要求（不是 H&R）'
                                                    }, "考核均值" + _toDisplayString(row.exam_avg_hours) + "h", 9, _hoisted_246))
                                                  : _createCommentVNode("", true),
                                                (row.free_over_gb)
                                                  ? (_openBlock(), _createElementBlock("em", _hoisted_247, ">" + _toDisplayString(row.free_over_gb) + "G免", 1))
                                                  : _createCommentVNode("", true),
                                                (row.free_original)
                                                  ? (_openBlock(), _createElementBlock("em", _hoisted_248, "原盘免"))
                                                  : _createCommentVNode("", true),
                                                (row.free_ep1)
                                                  ? (_openBlock(), _createElementBlock("em", _hoisted_249, "首集免"))
                                                  : _createCommentVNode("", true)
                                              ], 8, _hoisted_244),
                                              _createElementVNode("span", _hoisted_250, [
                                                (row.hr === true)
                                                  ? (_openBlock(), _createBlock(_component_VChip, {
                                                      key: 0,
                                                      size: "x-small",
                                                      color: "error",
                                                      variant: "tonal"
                                                    }, {
                                                      default: _withCtx(() => [...(_cache[409] || (_cache[409] = [
                                                        _createTextVNode("有", -1)
                                                      ]))]),
                                                      _: 1
                                                    }))
                                                  : (row.hr === false)
                                                    ? (_openBlock(), _createBlock(_component_VChip, {
                                                        key: 1,
                                                        size: "x-small",
                                                        color: "success",
                                                        variant: "tonal"
                                                      }, {
                                                        default: _withCtx(() => [...(_cache[410] || (_cache[410] = [
                                                          _createTextVNode("无", -1)
                                                        ]))]),
                                                        _: 1
                                                      }))
                                                    : (_openBlock(), _createBlock(_component_VChip, {
                                                        key: 2,
                                                        size: "x-small",
                                                        variant: "tonal"
                                                      }, {
                                                        default: _withCtx(() => [...(_cache[411] || (_cache[411] = [
                                                          _createTextVNode("未知", -1)
                                                        ]))]),
                                                        _: 1
                                                      })),
                                                (row.hr === false)
                                                  ? (_openBlock(), _createBlock(_component_VBtn, {
                                                      key: 3,
                                                      size: "x-small",
                                                      variant: "text",
                                                      disabled: rulesProbing.value,
                                                      title: "恢复为探测/内置判定",
                                                      onClick: $event => (setRuleHr(row, 'unknown'))
                                                    }, {
                                                      default: _withCtx(() => [...(_cache[412] || (_cache[412] = [
                                                        _createTextVNode("恢复", -1)
                                                      ]))]),
                                                      _: 1
                                                    }, 8, ["disabled", "onClick"]))
                                                  : (_openBlock(), _createElementBlock(_Fragment, { key: 4 }, [
                                                      _createVNode(_component_VBtn, {
                                                        size: "x-small",
                                                        variant: "text",
                                                        disabled: rulesProbing.value,
                                                        title: "该站有 H&R：手动确认为「有」并按当前时长保护",
                                                        onClick: $event => (setRuleHr(row, '1'))
                                                      }, {
                                                        default: _withCtx(() => [...(_cache[413] || (_cache[413] = [
                                                          _createTextVNode("标有", -1)
                                                        ]))]),
                                                        _: 1
                                                      }, 8, ["disabled", "onClick"]),
                                                      _createVNode(_component_VBtn, {
                                                        size: "x-small",
                                                        variant: "text",
                                                        disabled: rulesProbing.value,
                                                        title: "该站没有 H&R：直接标无，不做保种保护",
                                                        onClick: $event => (setRuleHr(row, '0'))
                                                      }, {
                                                        default: _withCtx(() => [...(_cache[414] || (_cache[414] = [
                                                          _createTextVNode("标无", -1)
                                                        ]))]),
                                                        _: 1
                                                      }, 8, ["disabled", "onClick"])
                                                    ], 64))
                                              ]),
                                              _createElementVNode("span", null, [
                                                _createVNode(_component_VTextField, {
                                                  "model-value": row.effective_hours,
                                                  type: "number",
                                                  min: "0",
                                                  max: "720",
                                                  step: "1",
                                                  density: "compact",
                                                  variant: "outlined",
                                                  "hide-details": "",
                                                  style: {"max-width":"6.5rem"},
                                                  onChange: $event => (setRuleHours(row, $event.target.value))
                                                }, null, 8, ["model-value", "onChange"])
                                              ]),
                                              _createElementVNode("span", null, _toDisplayString(row.seed_cap || '-'), 1),
                                              _createElementVNode("span", {
                                                class: "magicflow-rules-row__src",
                                                title: row.evidence || ''
                                              }, [
                                                _createTextVNode(_toDisplayString(ruleSourceText(row)) + " ", 1),
                                                (row.seed_need_hours)
                                                  ? (_openBlock(), _createElementBlock("em", {
                                                      key: 0,
                                                      title: '规则窗口 ' + (row.seed_window_hours || row.seed_hours || 0) + 'h，达到线 ' + row.seed_need_hours + 'h；保护期取窗口(保守)'
                                                    }, "需" + _toDisplayString(row.seed_need_hours) + "h", 9, _hoisted_252))
                                                  : _createCommentVNode("", true),
                                                (row.seed_hours_seen != null)
                                                  ? (_openBlock(), _createElementBlock("em", _hoisted_253, "(看到" + _toDisplayString(row.seed_hours_seen) + "h)", 1))
                                                  : _createCommentVNode("", true)
                                              ], 8, _hoisted_251),
                                              _createElementVNode("span", null, [
                                                (row.rule_url)
                                                  ? (_openBlock(), _createBlock(_component_VBtn, {
                                                      key: 0,
                                                      size: "x-small",
                                                      variant: "text",
                                                      icon: "",
                                                      href: String(row.rule_url).split(/\s+/)[0],
                                                      target: "_blank",
                                                      rel: "noopener",
                                                      title: '规则地址（来自收件箱欢迎短讯，已存下）：' + row.rule_url
                                                    }, {
                                                      default: _withCtx(() => [
                                                        _createVNode(_component_VIcon, { size: "x-small" }, {
                                                          default: _withCtx(() => [...(_cache[415] || (_cache[415] = [
                                                            _createTextVNode("mdi-link-variant", -1)
                                                          ]))]),
                                                          _: 1
                                                        })
                                                      ]),
                                                      _: 1
                                                    }, 8, ["href", "title"]))
                                                  : _createCommentVNode("", true),
                                                _createVNode(_component_VBtn, {
                                                  size: "x-small",
                                                  variant: "text",
                                                  disabled: rulesProbing.value,
                                                  onClick: $event => (probeRules(row.domain))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[416] || (_cache[416] = [
                                                    _createTextVNode("探测", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["disabled", "onClick"])
                                              ])
                                            ]))
                                          }), 128))
                                        ]),
                                        _cache[420] || (_cache[420] = _createElementVNode("p", { class: "magicflow-settings-hint" }, " 「保种(h)」直接改 = 写入手填覆盖（最高优先级：手填 > 探测 > 内置 > 全局默认）。 ", -1))
                                      ]))
                                    : (settingsTab.value === 'tags')
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_254, [
                                          _cache[429] || (_cache[429] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                            _createTextVNode(" 标签模型：种子状态 = 标签 "),
                                            _createElementVNode("code", null, "魔流-<站点>-<状态>[-<子类>]"),
                                            _createTextVNode("， 状态有 "),
                                            _createElementVNode("strong", null, "刷流 / 魔力 / 静默(新·资源·普通) / 推荐"),
                                            _createTextVNode("； 另有"),
                                            _createElementVNode("strong", null, "状态账本"),
                                            _createTextVNode("做真值源（标签被改坏也能自愈），以及 "),
                                            _createElementVNode("strong", null, "文件组账本"),
                                            _createTextVNode("按多站引用计数——"),
                                            _createElementVNode("em", null, "摘成员只删种，最后一个成员才连文件清"),
                                            _createTextVNode("。 ")
                                          ], -1)),
                                          _createElementVNode("div", _hoisted_255, [
                                            _createVNode(_component_VSwitch, {
                                              modelValue: settingsDraft.value.tag_model_enabled,
                                              "onUpdate:modelValue": _cache[120] || (_cache[120] = $event => ((settingsDraft.value.tag_model_enabled) = $event)),
                                              label: "启用标签模型（状态账本 + 魔流-站点-状态 标签）",
                                              color: "primary",
                                              "hide-details": "",
                                              inset: ""
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _createElementVNode("div", _hoisted_256, [
                                            _createVNode(_component_VTextField, {
                                              modelValue: settingsDraft.value.tag_silent_new_timeout_hours,
                                              "onUpdate:modelValue": _cache[121] || (_cache[121] = $event => ((settingsDraft.value.tag_silent_new_timeout_hours) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              step: "1",
                                              label: "「静默-新」超时(小时)",
                                              hint: "超过该时长未分拣自动归「静默-普通」，0 = 不超时",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable"
                                            }, null, 8, ["modelValue"]),
                                            _createVNode(_component_VTextField, {
                                              modelValue: settingsDraft.value.tag_snapshot_interval_hours,
                                              "onUpdate:modelValue": _cache[122] || (_cache[122] = $event => ((settingsDraft.value.tag_snapshot_interval_hours) = $event)),
                                              modelModifiers: { number: true },
                                              type: "number",
                                              min: "0",
                                              step: "1",
                                              label: "账本快照间隔(小时)",
                                              hint: "滚动保留最近 3 份，用于精确回滚；0 = 不快照",
                                              "persistent-hint": "",
                                              variant: "outlined",
                                              density: "comfortable"
                                            }, null, 8, ["modelValue"])
                                          ]),
                                          _createVNode(_component_VDivider, { class: "my-3" }),
                                          _cache[430] || (_cache[430] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                            _createElementVNode("strong", null, "静默分拣规则"),
                                            _createTextVNode("："),
                                            _createElementVNode("code", null, "静默-新"),
                                            _createTextVNode(" 命中任一启用规则 → 进 "),
                                            _createElementVNode("code", null, "静默-资源"),
                                            _createTextVNode("， 否则进 "),
                                            _createElementVNode("code", null, "静默-普通"),
                                            _createTextVNode("（受站点魔力产出考核）。 ")
                                          ], -1)),
                                          _createElementVNode("div", _hoisted_257, [
                                            _cache[422] || (_cache[422] = _createElementVNode("div", { class: "magicflow-sort-rules__row magicflow-sort-rules__row--head" }, [
                                              _createElementVNode("span", null, "规则"),
                                              _createElementVNode("span", null, "阈值"),
                                              _createElementVNode("span", null, "权重"),
                                              _createElementVNode("span", null, "启用"),
                                              _createElementVNode("span")
                                            ], -1)),
                                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(settingsDraft.value.sort_rules, (r, i) => {
                                              return (_openBlock(), _createElementBlock("div", {
                                                key: i,
                                                class: "magicflow-sort-rules__row"
                                              }, [
                                                _createElementVNode("span", null, _toDisplayString(sortRuleText(r)), 1),
                                                _createElementVNode("span", null, [
                                                  (sortRuleNeedsMin(r.type))
                                                    ? (_openBlock(), _createBlock(_component_VTextField, {
                                                        key: 0,
                                                        modelValue: r.min,
                                                        "onUpdate:modelValue": $event => ((r.min) = $event),
                                                        modelModifiers: { number: true },
                                                        type: "number",
                                                        step: "0.5",
                                                        density: "compact",
                                                        variant: "outlined",
                                                        "hide-details": "",
                                                        style: {"max-width":"110px"}
                                                      }, null, 8, ["modelValue", "onUpdate:modelValue"]))
                                                    : (_openBlock(), _createElementBlock("em", _hoisted_258, "-"))
                                                ]),
                                                _createElementVNode("span", null, [
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: r.weight,
                                                    "onUpdate:modelValue": $event => ((r.weight) = $event),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    step: "5",
                                                    density: "compact",
                                                    variant: "outlined",
                                                    "hide-details": "",
                                                    style: {"max-width":"90px"}
                                                  }, null, 8, ["modelValue", "onUpdate:modelValue"])
                                                ]),
                                                _createElementVNode("span", null, [
                                                  _createVNode(_component_VSwitch, {
                                                    modelValue: r.enabled,
                                                    "onUpdate:modelValue": $event => ((r.enabled) = $event),
                                                    color: "primary",
                                                    density: "compact",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue", "onUpdate:modelValue"])
                                                ]),
                                                _createElementVNode("span", null, [
                                                  _createVNode(_component_VBtn, {
                                                    size: "x-small",
                                                    variant: "text",
                                                    color: "error",
                                                    onClick: $event => (removeSortRule(i))
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[421] || (_cache[421] = [
                                                      _createTextVNode("删除", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["onClick"])
                                                ])
                                              ]))
                                            }), 128))
                                          ]),
                                          _createElementVNode("div", _hoisted_259, [
                                            _createVNode(_component_VSelect, {
                                              modelValue: newRuleType.value,
                                              "onUpdate:modelValue": _cache[123] || (_cache[123] = $event => ((newRuleType).value = $event)),
                                              items: _unref(sortRuleTypeOptions),
                                              "item-title": "text",
                                              "item-value": "value",
                                              density: "compact",
                                              variant: "outlined",
                                              "hide-details": "",
                                              style: {"max-width":"200px"},
                                              label: "新增规则"
                                            }, null, 8, ["modelValue", "items"]),
                                            _createVNode(_component_VBtn, {
                                              size: "small",
                                              variant: "tonal",
                                              color: "primary",
                                              onClick: addSortRule
                                            }, {
                                              default: _withCtx(() => [...(_cache[423] || (_cache[423] = [
                                                _createTextVNode("加上", -1)
                                              ]))]),
                                              _: 1
                                            })
                                          ]),
                                          _createVNode(_component_VDivider, { class: "my-3" }),
                                          _createElementVNode("div", _hoisted_260, [
                                            _createVNode(_component_VBtn, {
                                              size: "small",
                                              variant: "tonal",
                                              color: "primary",
                                              loading: tagMigrating.value,
                                              onClick: previewTagMigrate
                                            }, {
                                              default: _withCtx(() => [
                                                _createVNode(_component_VIcon, {
                                                  start: "",
                                                  size: "small"
                                                }, {
                                                  default: _withCtx(() => [...(_cache[424] || (_cache[424] = [
                                                    _createTextVNode("mdi-tag-multiple", -1)
                                                  ]))]),
                                                  _: 1
                                                }),
                                                _cache[425] || (_cache[425] = _createTextVNode("迁移预演（老标签 → 新命名） ", -1))
                                              ]),
                                              _: 1
                                            }, 8, ["loading"]),
                                            (tagMigratePlan.value)
                                              ? (_openBlock(), _createBlock(_component_VBtn, {
                                                  key: 0,
                                                  size: "small",
                                                  color: "error",
                                                  variant: "tonal",
                                                  loading: tagMigrating.value,
                                                  onClick: applyTagMigrate
                                                }, {
                                                  default: _withCtx(() => [
                                                    _createTextVNode(" 执行迁移（" + _toDisplayString(tagMigratePlan.value.total) + " 个） ", 1)
                                                  ]),
                                                  _: 1
                                                }, 8, ["loading"]))
                                              : _createCommentVNode("", true),
                                            _createVNode(_component_VSpacer),
                                            _createElementVNode("span", _hoisted_261, "账本 " + _toDisplayString(tagInfo.value?.ledger_count ?? 0) + " 条 · 文件组 " + _toDisplayString(tagInfo.value?.groups?.groups ?? 0) + "（多站 " + _toDisplayString(tagInfo.value?.groups?.multi_site_groups ?? 0) + "）", 1)
                                          ]),
                                          (tagMigratePlan.value)
                                            ? (_openBlock(), _createElementBlock("div", _hoisted_262, [
                                                _createElementVNode("p", _hoisted_263, [
                                                  _cache[426] || (_cache[426] = _createTextVNode(" 待迁移 ", -1)),
                                                  _createElementVNode("strong", null, _toDisplayString(tagMigratePlan.value.total), 1),
                                                  _cache[427] || (_cache[427] = _createTextVNode(" 个： ", -1)),
                                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tagMigratePlan.value.by_state, (n, k) => {
                                                    return (_openBlock(), _createElementBlock("em", { key: k }, _toDisplayString(k) + " " + _toDisplayString(n), 1))
                                                  }), 128))
                                                ]),
                                                _createElementVNode("div", _hoisted_264, [
                                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList((tagMigratePlan.value.samples || []), (row, i) => {
                                                    return (_openBlock(), _createElementBlock("div", {
                                                      key: i,
                                                      class: "magicflow-tag-migrate__row"
                                                    }, [
                                                      _createElementVNode("span", {
                                                        class: "magicflow-tag-migrate__title",
                                                        title: row.title
                                                      }, _toDisplayString(row.title), 9, _hoisted_265),
                                                      _createElementVNode("span", _hoisted_266, [
                                                        _createElementVNode("em", null, _toDisplayString((row.remove || []).join(' ')), 1),
                                                        _cache[428] || (_cache[428] = _createTextVNode(" → ", -1)),
                                                        _createElementVNode("strong", null, _toDisplayString(row.add), 1)
                                                      ])
                                                    ]))
                                                  }), 128))
                                                ])
                                              ]))
                                            : _createCommentVNode("", true),
                                          _cache[431] || (_cache[431] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                            _createTextVNode(" 迁移会把任务里手填的 "),
                                            _createElementVNode("code", null, "brush_tag"),
                                            _createTextVNode("（如 "),
                                            _createElementVNode("code", null, "魔流-财神"),
                                            _createTextVNode("）换成状态标签， 保留 "),
                                            _createElementVNode("code", null, "已整理 / 辅种"),
                                            _createTextVNode(" 等外来标签；预演不变更任何东西。 ")
                                          ], -1))
                                        ]))
                                      : (settingsTab.value === 'crossseed')
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_267, [...(_cache[432] || (_cache[432] = [
                                            _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                              _createTextVNode(" 跨站免费取种：本站"),
                                              _createElementVNode("strong", null, "非免费"),
                                              _createTextVNode("的候选（或本地没有的免费种）→ 去"),
                                              _createElementVNode("strong", null, "兄弟站免费下"),
                                              _createTextVNode("， 下完再把目标站的种子指向同一批文件回辅（校验通过才保留）。 "),
                                              _createElementVNode("br"),
                                              _createTextVNode(" 本页只管「"),
                                              _createElementVNode("strong", null, "怎么取种"),
                                              _createTextVNode("」： "),
                                              _createElementVNode("strong", null, "流量兜底"),
                                              _createTextVNode("（含取种期间核对来源站）已在「"),
                                              _createElementVNode("strong", null, "站点监控 → 流量兜底"),
                                              _createTextVNode("」统一配置； "),
                                              _createElementVNode("strong", null, "H&R"),
                                              _createTextVNode("（保种时长 / 来源份保护 / 期满回收）在「"),
                                              _createElementVNode("strong", null, "站点规则"),
                                              _createTextVNode("」页。 ")
                                            ], -1)
                                          ]))]))
                                        : (settingsTab.value === 'fallback')
                                          ? (_openBlock(), _createElementBlock("div", _hoisted_268, [
                                              _cache[438] || (_cache[438] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                                _createTextVNode(" TMDB 对"),
                                                _createElementVNode("strong", null, "番剧特别篇/前传、国漫、B站特供"),
                                                _createTextVNode("常常「根本没有」，离了 TMDB 就没元数据可用。 这里做"),
                                                _createElementVNode("strong", null, "多源识别回退"),
                                                _createTextVNode("（按顺序试各来源）→ 给库里缺 NFO 的集补一份"),
                                                _createElementVNode("strong", null, "最小 NFO"),
                                                _createTextVNode("， 让播放器 / 飞牛影视能显示名称与集号。"),
                                                _createElementVNode("strong", null, "只写 NFO，不动媒体文件，已存在的好 NFO 不覆盖。")
                                              ], -1)),
                                              _createElementVNode("div", _hoisted_269, [
                                                _createVNode(_component_VSwitch, {
                                                  modelValue: settingsDraft.value.fallback_enabled,
                                                  "onUpdate:modelValue": _cache[124] || (_cache[124] = $event => ((settingsDraft.value.fallback_enabled) = $event)),
                                                  label: "启用元数据兜底",
                                                  color: "primary",
                                                  "hide-details": "",
                                                  inset: ""
                                                }, null, 8, ["modelValue"]),
                                                _createVNode(_component_VSwitch, {
                                                  modelValue: settingsDraft.value.fallback_after_import,
                                                  "onUpdate:modelValue": _cache[125] || (_cache[125] = $event => ((settingsDraft.value.fallback_after_import) = $event)),
                                                  label: "每次整理入库后自动兜底",
                                                  color: "primary",
                                                  "hide-details": "",
                                                  inset: ""
                                                }, null, 8, ["modelValue"]),
                                                _createVNode(_component_VSwitch, {
                                                  modelValue: settingsDraft.value.fallback_dry_run,
                                                  "onUpdate:modelValue": _cache[126] || (_cache[126] = $event => ((settingsDraft.value.fallback_dry_run) = $event)),
                                                  label: "演练模式（只报告不写 NFO）",
                                                  color: "primary",
                                                  "hide-details": "",
                                                  inset: ""
                                                }, null, 8, ["modelValue"])
                                              ]),
                                              _createElementVNode("div", _hoisted_270, [
                                                _cache[434] || (_cache[434] = _createElementVNode("div", { class: "magicflow-settings-label" }, "识别来源顺序（自上而下依次尝试）", -1)),
                                                _createElementVNode("ol", _hoisted_271, [
                                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(usedFallbackSources.value, (src, idx) => {
                                                    return (_openBlock(), _createElementBlock("li", {
                                                      key: src,
                                                      class: "magicflow-fb-source"
                                                    }, [
                                                      _createElementVNode("span", _hoisted_272, _toDisplayString(idx + 1), 1),
                                                      _createElementVNode("span", _hoisted_273, _toDisplayString(fallbackSourceLabel(src)), 1),
                                                      _createVNode(_component_VBtn, {
                                                        icon: "mdi-arrow-up",
                                                        size: "x-small",
                                                        variant: "text",
                                                        disabled: idx === 0,
                                                        "aria-label": "上移",
                                                        onClick: $event => (moveFallbackSource(idx, -1))
                                                      }, null, 8, ["disabled", "onClick"]),
                                                      _createVNode(_component_VBtn, {
                                                        icon: "mdi-arrow-down",
                                                        size: "x-small",
                                                        variant: "text",
                                                        disabled: idx === usedFallbackSources.value.length - 1,
                                                        "aria-label": "下移",
                                                        onClick: $event => (moveFallbackSource(idx, 1))
                                                      }, null, 8, ["disabled", "onClick"]),
                                                      _createVNode(_component_VBtn, {
                                                        icon: "mdi-close",
                                                        size: "x-small",
                                                        variant: "text",
                                                        "aria-label": "移除",
                                                        onClick: $event => (removeFallbackSource(src))
                                                      }, null, 8, ["onClick"])
                                                    ]))
                                                  }), 128))
                                                ]),
                                                _createElementVNode("div", _hoisted_274, [
                                                  _createVNode(_component_VSelect, {
                                                    modelValue: fallbackSourceDraft.value,
                                                    "onUpdate:modelValue": _cache[127] || (_cache[127] = $event => ((fallbackSourceDraft).value = $event)),
                                                    items: unusedFallbackSources.value,
                                                    "item-title": "title",
                                                    "item-value": "value",
                                                    label: "添加来源",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    "hide-details": "",
                                                    clearable: ""
                                                  }, null, 8, ["modelValue", "items"]),
                                                  _createVNode(_component_VBtn, {
                                                    variant: "tonal",
                                                    color: "primary",
                                                    disabled: !fallbackSourceDraft.value,
                                                    onClick: addFallbackSource
                                                  }, {
                                                    default: _withCtx(() => [...(_cache[433] || (_cache[433] = [
                                                      _createTextVNode("添加", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["disabled"])
                                                ])
                                              ]),
                                              _createVNode(_component_VCombobox, {
                                                modelValue: settingsDraft.value.fallback_paths,
                                                "onUpdate:modelValue": _cache[128] || (_cache[128] = $event => ((settingsDraft.value.fallback_paths) = $event)),
                                                items: fallbackState.value?.effective_paths || [],
                                                label: "兜底扫描的库目录",
                                                hint: "留空 = 自动取 MoviePilot 目录配置里的 library 路径（如 /movie）",
                                                "persistent-hint": "",
                                                variant: "outlined",
                                                density: "comfortable",
                                                multiple: "",
                                                chips: "",
                                                clearable: ""
                                              }, null, 8, ["modelValue", "items"]),
                                              _createElementVNode("div", _hoisted_275, [
                                                _createVNode(_component_VTextField, {
                                                  modelValue: settingsDraft.value.fallback_interval_minutes,
                                                  "onUpdate:modelValue": _cache[129] || (_cache[129] = $event => ((settingsDraft.value.fallback_interval_minutes) = $event)),
                                                  modelModifiers: { number: true },
                                                  type: "number",
                                                  label: "扫描周期（分钟）",
                                                  hint: "定时扫库兜底，默认 30",
                                                  "persistent-hint": "",
                                                  variant: "outlined",
                                                  density: "comfortable"
                                                }, null, 8, ["modelValue"]),
                                                _createVNode(_component_VTextField, {
                                                  modelValue: settingsDraft.value.fallback_scan_max,
                                                  "onUpdate:modelValue": _cache[130] || (_cache[130] = $event => ((settingsDraft.value.fallback_scan_max) = $event)),
                                                  modelModifiers: { number: true },
                                                  type: "number",
                                                  label: "每轮最多处理剧集数",
                                                  hint: "其余下轮继续，避免一次卡爆，默认 30",
                                                  "persistent-hint": "",
                                                  variant: "outlined",
                                                  density: "comfortable"
                                                }, null, 8, ["modelValue"])
                                              ]),
                                              _createElementVNode("div", _hoisted_276, [
                                                _createVNode(_component_VSwitch, {
                                                  modelValue: settingsDraft.value.fallback_sp_to_s00,
                                                  "onUpdate:modelValue": _cache[131] || (_cache[131] = $event => ((settingsDraft.value.fallback_sp_to_s00) = $event)),
                                                  label: "特别篇归位：源中不存在的集改归 Season 0（S00EXX）",
                                                  color: "primary",
                                                  "hide-details": "",
                                                  inset: ""
                                                }, null, 8, ["modelValue"])
                                              ]),
                                              _createVNode(_component_VDivider, { class: "magicflow-fb-divider" }),
                                              _createElementVNode("div", _hoisted_277, [
                                                _createVNode(_component_VBtn, {
                                                  variant: "tonal",
                                                  color: "primary",
                                                  size: "small",
                                                  loading: fallbackRunning.value,
                                                  disabled: fallbackRunning.value,
                                                  onClick: _cache[132] || (_cache[132] = $event => (runFallback(true)))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[435] || (_cache[435] = [
                                                    _createTextVNode("演练扫描", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["loading", "disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  variant: "flat",
                                                  color: "primary",
                                                  size: "small",
                                                  loading: fallbackRunning.value,
                                                  disabled: fallbackRunning.value,
                                                  onClick: _cache[133] || (_cache[133] = $event => (runFallback(false)))
                                                }, {
                                                  default: _withCtx(() => [...(_cache[436] || (_cache[436] = [
                                                    _createTextVNode("立即执行", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["loading", "disabled"]),
                                                _createVNode(_component_VBtn, {
                                                  variant: "text",
                                                  size: "small",
                                                  loading: fallbackLoading.value,
                                                  onClick: loadFallback
                                                }, {
                                                  default: _withCtx(() => [...(_cache[437] || (_cache[437] = [
                                                    _createTextVNode("刷新结果", -1)
                                                  ]))]),
                                                  _: 1
                                                }, 8, ["loading"]),
                                                (fallbackState.value?.running)
                                                  ? (_openBlock(), _createElementBlock("span", _hoisted_278, "● 扫描中…"))
                                                  : _createCommentVNode("", true)
                                              ]),
                                              (fallbackState.value?.report)
                                                ? (_openBlock(), _createElementBlock("div", _hoisted_279, [
                                                    _createElementVNode("div", _hoisted_280, [
                                                      _createTextVNode(" 上次" + _toDisplayString(fallbackState.value.report.applied === false ? '演练' : '执行') + "： 扫描 " + _toDisplayString(fallbackState.value.report.stats?.shows || 0) + " 剧", 1),
                                                      (fallbackState.value.report.stats?.total_shows)
                                                        ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                            _createTextVNode("/共 " + _toDisplayString(fallbackState.value.report.stats.total_shows) + " 部", 1)
                                                          ], 64))
                                                        : _createCommentVNode("", true),
                                                      _createTextVNode(" · 识别 " + _toDisplayString(fallbackState.value.report.stats?.resolved || 0) + " · 补集 NFO " + _toDisplayString(fallbackState.value.report.stats?.ep_nfo || 0) + " · 补剧 NFO " + _toDisplayString(fallbackState.value.report.stats?.show_nfo || 0) + " · 源中缺失 " + _toDisplayString(fallbackState.value.report.stats?.missing || 0) + " · 多源补齐 " + _toDisplayString(fallbackState.value.report.stats?.via_extra || 0) + " 集 · 归位 " + _toDisplayString(fallbackState.value.report.stats?.renumbered || 0) + " · " + _toDisplayString(fallbackState.value.report.duration) + "s ", 1)
                                                    ]),
                                                    (fallbackProblemShows.value.length)
                                                      ? (_openBlock(), _createElementBlock("details", _hoisted_281, [
                                                          _createElementVNode("summary", null, "源里查不到的集（" + _toDisplayString(fallbackProblemCount.value) + " 集，已按本地文件兜底）", 1),
                                                          _createElementVNode("ul", _hoisted_282, [
                                                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(fallbackProblemShows.value, (item) => {
                                                              return (_openBlock(), _createElementBlock("li", {
                                                                key: item.show
                                                              }, [
                                                                _createElementVNode("strong", null, _toDisplayString(item.show), 1),
                                                                _createElementVNode("span", _hoisted_283, _toDisplayString((item.problems || []).map(p => `S${String(p.season).padStart(2, '0')}E${String(p.episode).padStart(2, '0')}`).join(' ')), 1)
                                                              ]))
                                                            }), 128))
                                                          ])
                                                        ]))
                                                      : _createCommentVNode("", true),
                                                    ((fallbackState.value.report.shows || []).length)
                                                      ? (_openBlock(), _createElementBlock("details", _hoisted_284, [
                                                          _createElementVNode("summary", null, "展开本剧集明细（" + _toDisplayString(fallbackState.value.report.shows.length) + " 部有变动）", 1),
                                                          _createElementVNode("ul", _hoisted_285, [
                                                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(fallbackState.value.report.shows, (item) => {
                                                              return (_openBlock(), _createElementBlock("li", {
                                                                key: item.show
                                                              }, [
                                                                _createElementVNode("strong", null, _toDisplayString(item.show), 1),
                                                                _createElementVNode("span", _hoisted_286, "识别自 " + _toDisplayString(item.resolved || '未命中') + "｜补集 " + _toDisplayString((item.episodes || []).filter(e => e.nfo).length) + "｜归位 " + _toDisplayString((item.renumbered || []).length), 1)
                                                              ]))
                                                            }), 128))
                                                          ])
                                                        ]))
                                                      : _createCommentVNode("", true)
                                                  ]))
                                                : _createCommentVNode("", true)
                                            ]))
                                          : (settingsTab.value === 'cloud')
                                            ? (_openBlock(), _createElementBlock("div", _hoisted_287, [
                                                _cache[442] || (_cache[442] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                                                  _createElementVNode("strong", null, "本地当热区，夸克当冷库。"),
                                                  _createTextVNode(" 把库里的成品大文件上传到 OpenList 的可写存储（夸克 cookie 驱动）， 同一夸克目录会被 OpenList 的 Strm 视图自动生成 "),
                                                  _createElementVNode("code", null, ".strm"),
                                                  _createTextVNode(" 播放指针， 飞牛影视直接能看 —— "),
                                                  _createElementVNode("strong", null, "无需改 OpenList 配置、也无需自己写 strm"),
                                                  _createTextVNode("。 默认"),
                                                  _createElementVNode("strong", null, "只上传、不删本地"),
                                                  _createTextVNode("；删本地与停种必须单独确认。 ")
                                                ], -1)),
                                                _createElementVNode("div", _hoisted_288, [
                                                  _createVNode(_component_VSwitch, {
                                                    modelValue: settingsDraft.value.cloud_enabled,
                                                    "onUpdate:modelValue": _cache[134] || (_cache[134] = $event => ((settingsDraft.value.cloud_enabled) = $event)),
                                                    label: "启用云盘归档",
                                                    color: "primary",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VSwitch, {
                                                    modelValue: settingsDraft.value.cloud_dry_run,
                                                    "onUpdate:modelValue": _cache[135] || (_cache[135] = $event => ((settingsDraft.value.cloud_dry_run) = $event)),
                                                    label: "演练模式（只列计划，不真传）",
                                                    color: "primary",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VSwitch, {
                                                    modelValue: settingsDraft.value.cloud_notify,
                                                    "onUpdate:modelValue": _cache[136] || (_cache[136] = $event => ((settingsDraft.value.cloud_notify) = $event)),
                                                    label: "完成后通知",
                                                    color: "primary",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"])
                                                ]),
                                                _createElementVNode("div", _hoisted_289, [
                                                  _cache[440] || (_cache[440] = _createElementVNode("div", { class: "magicflow-settings-label" }, "OpenList 连接", -1)),
                                                  _createElementVNode("div", _hoisted_290, [
                                                    _createVNode(_component_VTextField, {
                                                      modelValue: settingsDraft.value.cloud_openlist_url,
                                                      "onUpdate:modelValue": _cache[137] || (_cache[137] = $event => ((settingsDraft.value.cloud_openlist_url) = $event)),
                                                      label: "OpenList 地址",
                                                      placeholder: "http://192.168.0.61:12022",
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      "hide-details": "",
                                                      autocomplete: "off"
                                                    }, null, 8, ["modelValue"])
                                                  ]),
                                                  _createElementVNode("div", _hoisted_291, [
                                                    _createVNode(_component_VTextField, {
                                                      modelValue: settingsDraft.value.cloud_openlist_token,
                                                      "onUpdate:modelValue": _cache[138] || (_cache[138] = $event => ((settingsDraft.value.cloud_openlist_token) = $event)),
                                                      label: "OpenList Token",
                                                      placeholder: cloudCfg.value.has_token ? '已保存（留空则不修改）' : 'openlist-…',
                                                      variant: "outlined",
                                                      density: "comfortable",
                                                      "hide-details": "",
                                                      autocomplete: "off",
                                                      "persistent-hint": "",
                                                      hint: "留空 = 保留已保存的 Token；Token 不会回显到浏览器"
                                                    }, null, 8, ["modelValue", "placeholder"]),
                                                    _createVNode(_component_VBtn, {
                                                      variant: "tonal",
                                                      color: "primary",
                                                      size: "small",
                                                      "prepend-icon": "mdi-connection",
                                                      loading: cloudTesting.value,
                                                      onClick: testCloud
                                                    }, {
                                                      default: _withCtx(() => [...(_cache[439] || (_cache[439] = [
                                                        _createTextVNode("测试", -1)
                                                      ]))]),
                                                      _: 1
                                                    }, 8, ["loading"])
                                                  ]),
                                                  (cloudTestMsg.value)
                                                    ? (_openBlock(), _createElementBlock("p", {
                                                        key: 0,
                                                        class: _normalizeClass(["magicflow-settings-hint", cloudTestOk.value ? 'text-success' : 'text-error'])
                                                      }, _toDisplayString(cloudTestMsg.value), 3))
                                                    : _createCommentVNode("", true)
                                                ]),
                                                _createElementVNode("div", _hoisted_292, [
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: settingsDraft.value.cloud_source_mount,
                                                    "onUpdate:modelValue": _cache[139] || (_cache[139] = $event => ((settingsDraft.value.cloud_source_mount) = $event)),
                                                    label: "可写存储路径",
                                                    hint: "OpenList 里可写的存储挂载点，默认 /quark",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable"
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: settingsDraft.value.cloud_strm_mount,
                                                    "onUpdate:modelValue": _cache[140] || (_cache[140] = $event => ((settingsDraft.value.cloud_strm_mount) = $event)),
                                                    label: "Strm 视图路径",
                                                    hint: "只读校验用（Strm 驱动），默认 /movie",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable"
                                                  }, null, 8, ["modelValue"])
                                                ]),
                                                _createVNode(_component_VTextField, {
                                                  modelValue: settingsDraft.value.cloud_target_template,
                                                  "onUpdate:modelValue": _cache[141] || (_cache[141] = $event => ((settingsDraft.value.cloud_target_template) = $event)),
                                                  label: "远端目标模板",
                                                  hint: "{rel} = 相对库根的路径。默认 /quark/movie/{rel}（与本地库同构，影视侧自动对应）",
                                                  "persistent-hint": "",
                                                  variant: "outlined",
                                                  density: "comfortable"
                                                }, null, 8, ["modelValue"]),
                                                _createVNode(_component_VCombobox, {
                                                  modelValue: settingsDraft.value.cloud_paths,
                                                  "onUpdate:modelValue": _cache[142] || (_cache[142] = $event => ((settingsDraft.value.cloud_paths) = $event)),
                                                  label: "扫描目录（容器内路径，留空 = /movie）",
                                                  hint: "可多个；只扫这些库根下的媒体文件",
                                                  "persistent-hint": "",
                                                  variant: "outlined",
                                                  density: "comfortable",
                                                  chips: "",
                                                  multiple: "",
                                                  clearable: "",
                                                  items: ['/movie']
                                                }, null, 8, ["modelValue"]),
                                                _createVNode(_component_VCombobox, {
                                                  modelValue: settingsDraft.value.cloud_exclude_paths,
                                                  "onUpdate:modelValue": _cache[143] || (_cache[143] = $event => ((settingsDraft.value.cloud_exclude_paths) = $event)),
                                                  label: "排除路径（子串匹配）",
                                                  hint: "默认已排除下载区/刷流区/蓝光原盘结构；这里可再加",
                                                  "persistent-hint": "",
                                                  variant: "outlined",
                                                  density: "comfortable",
                                                  chips: "",
                                                  multiple: "",
                                                  clearable: "",
                                                  items: ['/movie/刷流', '/movie/下载']
                                                }, null, 8, ["modelValue"]),
                                                _createVNode(_component_VCombobox, {
                                                  modelValue: settingsDraft.value.cloud_exclude_tags,
                                                  "onUpdate:modelValue": _cache[144] || (_cache[144] = $event => ((settingsDraft.value.cloud_exclude_tags) = $event)),
                                                  label: "排除标签（做种中的种子不打标上传策略，可留空）",
                                                  variant: "outlined",
                                                  density: "comfortable",
                                                  chips: "",
                                                  multiple: "",
                                                  clearable: "",
                                                  items: ['魔流-推荐', '辅种', '已整理']
                                                }, null, 8, ["modelValue"]),
                                                _createElementVNode("div", _hoisted_293, [
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: settingsDraft.value.cloud_min_size_gb,
                                                    "onUpdate:modelValue": _cache[145] || (_cache[145] = $event => ((settingsDraft.value.cloud_min_size_gb) = $event)),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    label: "最小体积（GB，0 = 不限）",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    "hide-details": ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: settingsDraft.value.cloud_max_size_gb,
                                                    "onUpdate:modelValue": _cache[146] || (_cache[146] = $event => ((settingsDraft.value.cloud_max_size_gb) = $event)),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    label: "最大体积（GB，0 = 不限）",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    "hide-details": ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: settingsDraft.value.cloud_min_age_days,
                                                    "onUpdate:modelValue": _cache[147] || (_cache[147] = $event => ((settingsDraft.value.cloud_min_age_days) = $event)),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    label: "最小入库天数（0 = 不限）",
                                                    hint: "只归档入库较久、已经稳定的资源",
                                                    "persistent-hint": "",
                                                    variant: "outlined",
                                                    density: "comfortable"
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: settingsDraft.value.cloud_upload_limit_mbps,
                                                    "onUpdate:modelValue": _cache[148] || (_cache[148] = $event => ((settingsDraft.value.cloud_upload_limit_mbps) = $event)),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    label: "上传限速（Mbps，0 = 不限）",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    "hide-details": ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: settingsDraft.value.cloud_interval_minutes,
                                                    "onUpdate:modelValue": _cache[149] || (_cache[149] = $event => ((settingsDraft.value.cloud_interval_minutes) = $event)),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    label: "后台归档周期（分钟）",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    "hide-details": ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VTextField, {
                                                    modelValue: settingsDraft.value.cloud_scan_max,
                                                    "onUpdate:modelValue": _cache[150] || (_cache[150] = $event => ((settingsDraft.value.cloud_scan_max) = $event)),
                                                    modelModifiers: { number: true },
                                                    type: "number",
                                                    label: "每轮最多处理文件数",
                                                    variant: "outlined",
                                                    density: "comfortable",
                                                    "hide-details": ""
                                                  }, null, 8, ["modelValue"])
                                                ]),
                                                _createVNode(_component_VDivider, { class: "magicflow-fb-divider" }),
                                                _createElementVNode("div", _hoisted_294, [
                                                  _createVNode(_component_VSwitch, {
                                                    modelValue: settingsDraft.value.cloud_delete_local,
                                                    "onUpdate:modelValue": _cache[151] || (_cache[151] = $event => ((settingsDraft.value.cloud_delete_local) = $event)),
                                                    label: "归档后删除本地文件（危险：会停种；插件会拒绝自动执行，只做记录）",
                                                    color: "error",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"]),
                                                  _createVNode(_component_VSwitch, {
                                                    modelValue: settingsDraft.value.cloud_remove_torrent,
                                                    "onUpdate:modelValue": _cache[152] || (_cache[152] = $event => ((settingsDraft.value.cloud_remove_torrent) = $event)),
                                                    label: "同时移除下载器任务（危险，需人工确认）",
                                                    color: "error",
                                                    "hide-details": "",
                                                    inset: ""
                                                  }, null, 8, ["modelValue"])
                                                ]),
                                                _createVNode(_component_VAlert, {
                                                  type: "warning",
                                                  variant: "tonal",
                                                  density: "compact"
                                                }, {
                                                  default: _withCtx(() => [...(_cache[441] || (_cache[441] = [
                                                    _createTextVNode(" 安全默认：", -1),
                                                    _createElementVNode("strong", null, "不删本地、不停种", -1),
                                                    _createTextVNode("。删本地需要逐条上传校验通过后手动确认，绝不会自动执行。 ", -1)
                                                  ]))]),
                                                  _: 1
                                                })
                                              ]))
                                            : _createCommentVNode("", true)
                ]))
              : _createCommentVNode("", true),
            _createElementVNode("footer", _hoisted_295, [
              (settingsTab.value === 'downloader')
                ? (_openBlock(), _createBlock(_component_VBtn, {
                    key: 0,
                    variant: "tonal",
                    color: "primary",
                    disabled: !downloaderPrefsRecommended.value,
                    onClick: applyRecommendedPrefs
                  }, {
                    default: _withCtx(() => [...(_cache[443] || (_cache[443] = [
                      _createTextVNode(" 恢复推荐值 ", -1)
                    ]))]),
                    _: 1
                  }, 8, ["disabled"]))
                : _createCommentVNode("", true),
              _createVNode(_component_VSpacer),
              _createVNode(_component_VBtn, {
                variant: "text",
                onClick: _cache[153] || (_cache[153] = $event => (settingsDialog.value = false))
              }, {
                default: _withCtx(() => [...(_cache[444] || (_cache[444] = [
                  _createTextVNode("取消", -1)
                ]))]),
                _: 1
              }),
              _createVNode(_component_VBtn, {
                color: "primary",
                variant: "flat",
                loading: saving.value,
                onClick: saveActiveSettings
              }, {
                default: _withCtx(() => [...(_cache[445] || (_cache[445] = [
                  _createTextVNode("保存", -1)
                ]))]),
                _: 1
              }, 8, ["loading"])
            ])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      modelValue: torrentDialog.value,
      "onUpdate:modelValue": _cache[162] || (_cache[162] = $event => ((torrentDialog).value = $event)),
      "max-width": "34rem",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        (activeTorrent.value)
          ? (_openBlock(), _createBlock(_component_VCard, {
              key: 0,
              class: "magicflow-dialog magicflow-torrent-dialog"
            }, {
              default: _withCtx(() => [
                _createElementVNode("header", _hoisted_296, [
                  _createElementVNode("div", _hoisted_297, [
                    _createVNode(_component_VChip, {
                      size: "small",
                      color: stateColor(activeTorrent.value.state),
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(stateLabel(activeTorrent.value.state)), 1)
                      ]),
                      _: 1
                    }, 8, ["color"]),
                    (activeTorrent.value.is_protected)
                      ? (_openBlock(), _createBlock(_component_VChip, {
                          key: 0,
                          size: "small",
                          color: "primary",
                          variant: "tonal",
                          "prepend-icon": "mdi-shield-check-outline"
                        }, {
                          default: _withCtx(() => [...(_cache[446] || (_cache[446] = [
                            _createTextVNode("已保留", -1)
                          ]))]),
                          _: 1
                        }))
                      : _createCommentVNode("", true),
                    _createVNode(_component_VChip, {
                      size: "small",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(selectedTask.value.site_name), 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _createVNode(_component_VBtn, {
                    icon: "mdi-close",
                    size: "small",
                    variant: "text",
                    "aria-label": "关闭",
                    onClick: _cache[155] || (_cache[155] = $event => (torrentDialog.value = false))
                  })
                ]),
                _createElementVNode("div", _hoisted_298, _toDisplayString(activeTorrent.value.title || '种子详情'), 1),
                _createElementVNode("div", _hoisted_299, [
                  _createVNode(_component_VProgressLinear, {
                    "model-value": torrentProgressPct(activeTorrent.value),
                    color: stateColor(activeTorrent.value.state),
                    height: "8",
                    rounded: ""
                  }, null, 8, ["model-value", "color"]),
                  _createElementVNode("span", _hoisted_300, _toDisplayString(torrentProgressPct(activeTorrent.value)) + "%", 1)
                ]),
                _createElementVNode("dl", _hoisted_301, [
                  _createElementVNode("div", null, [
                    _cache[447] || (_cache[447] = _createElementVNode("dt", null, "大小", -1)),
                    _createElementVNode("dd", null, _toDisplayString(Number(activeTorrent.value.size_gb || 0).toFixed(2)) + " GB", 1)
                  ]),
                  _createElementVNode("div", null, [
                    _cache[448] || (_cache[448] = _createElementVNode("dt", null, "上传量", -1)),
                    _createElementVNode("dd", null, _toDisplayString(_unref(formatBytes)(activeTorrent.value.uploaded)), 1)
                  ]),
                  _createElementVNode("div", null, [
                    _cache[449] || (_cache[449] = _createElementVNode("dt", null, "分享率", -1)),
                    _createElementVNode("dd", null, _toDisplayString(Number(activeTorrent.value.ratio || 0).toFixed(2)), 1)
                  ]),
                  _createElementVNode("div", null, [
                    _cache[450] || (_cache[450] = _createElementVNode("dt", null, "当前状态", -1)),
                    _createElementVNode("dd", null, _toDisplayString(stateLabel(activeTorrent.value.state)), 1)
                  ])
                ]),
                _createElementVNode("div", _hoisted_302, [
                  _cache[451] || (_cache[451] = _createElementVNode("span", { class: "magicflow-torrent-dialog__hash-label" }, "infohash", -1)),
                  _createElementVNode("code", null, _toDisplayString(activeTorrent.value.hash), 1),
                  _createVNode(_component_VBtn, {
                    size: "x-small",
                    variant: "text",
                    icon: "mdi-content-copy",
                    "aria-label": "复制 infohash",
                    onClick: _cache[156] || (_cache[156] = $event => (copyTorrentHash(activeTorrent.value.hash)))
                  })
                ]),
                _createVNode(_component_VCardActions, { class: "magicflow-torrent-dialog__actions" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VBtn, {
                      size: "small",
                      variant: "tonal",
                      color: activeTorrent.value.is_protected ? 'grey' : 'primary',
                      "prepend-icon": activeTorrent.value.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline',
                      loading: saving.value,
                      onClick: _cache[157] || (_cache[157] = $event => (detailTorrentAction(activeTorrent.value.is_protected ? 'unprotect' : 'protect')))
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(activeTorrent.value.is_protected ? '取消保留' : '保留'), 1)
                      ]),
                      _: 1
                    }, 8, ["color", "prepend-icon", "loading"]),
                    (torrentIsPaused(activeTorrent.value))
                      ? (_openBlock(), _createBlock(_component_VBtn, {
                          key: 0,
                          size: "small",
                          variant: "tonal",
                          "prepend-icon": "mdi-play-circle-outline",
                          loading: saving.value,
                          onClick: _cache[158] || (_cache[158] = $event => (detailTorrentAction('resume')))
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(torrentResumeLabel(activeTorrent.value)), 1)
                          ]),
                          _: 1
                        }, 8, ["loading"]))
                      : (_openBlock(), _createBlock(_component_VBtn, {
                          key: 1,
                          size: "small",
                          variant: "tonal",
                          "prepend-icon": "mdi-pause-circle-outline",
                          loading: saving.value,
                          onClick: _cache[159] || (_cache[159] = $event => (detailTorrentAction('pause')))
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(torrentPauseLabel(activeTorrent.value)), 1)
                          ]),
                          _: 1
                        }, 8, ["loading"])),
                    _createVNode(_component_VBtn, {
                      size: "small",
                      variant: "tonal",
                      "prepend-icon": "mdi-sync",
                      loading: saving.value,
                      onClick: _cache[160] || (_cache[160] = $event => (detailTorrentAction('recheck')))
                    }, {
                      default: _withCtx(() => [...(_cache[452] || (_cache[452] = [
                        _createTextVNode("校验", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VBtn, {
                      size: "small",
                      color: "error",
                      variant: "tonal",
                      "prepend-icon": "mdi-delete-outline",
                      loading: saving.value,
                      onClick: _cache[161] || (_cache[161] = $event => (requestTorrentDelete(activeTorrent.value)))
                    }, {
                      default: _withCtx(() => [...(_cache[453] || (_cache[453] = [
                        _createTextVNode("删除", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }))
          : _createCommentVNode("", true)
      ]),
      _: 1
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      modelValue: transferDialog.value,
      "onUpdate:modelValue": _cache[165] || (_cache[165] = $event => ((transferDialog).value = $event)),
      "max-width": "34rem"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, {
          title: "批量转移种子",
          class: "magicflow-dialog"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardText, { class: "magicflow-settings-hint" }, {
              default: _withCtx(() => [
                _cache[454] || (_cache[454] = _createTextVNode(" 把选中的 ", -1)),
                _createElementVNode("strong", null, _toDisplayString(selectedHashes.value.length), 1),
                _cache[455] || (_cache[455] = _createTextVNode(" 个种子交给别的任务，或退回静默池（保文件）。 跨站转移会改掉站点标签 —— 一般只转给", -1)),
                _cache[456] || (_cache[456] = _createElementVNode("strong", null, "同站", -1)),
                _cache[457] || (_cache[457] = _createTextVNode("任务。 ", -1))
              ]),
              _: 1
            }),
            _createVNode(_component_VCardText, null, {
              default: _withCtx(() => [
                _createVNode(_component_VSelect, {
                  modelValue: transferTarget.value,
                  "onUpdate:modelValue": _cache[163] || (_cache[163] = $event => ((transferTarget).value = $event)),
                  items: transferChoices.value,
                  "item-title": "text",
                  "item-value": "value",
                  density: "compact",
                  variant: "outlined",
                  "hide-details": "",
                  label: "转移到"
                }, null, 8, ["modelValue", "items"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCardActions, null, {
              default: _withCtx(() => [
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  variant: "text",
                  disabled: batchBusy.value,
                  onClick: _cache[164] || (_cache[164] = $event => (transferDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[458] || (_cache[458] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }, 8, ["disabled"]),
                _createVNode(_component_VBtn, {
                  color: "primary",
                  variant: "flat",
                  loading: batchBusy.value,
                  onClick: confirmTransfer
                }, {
                  default: _withCtx(() => [...(_cache[459] || (_cache[459] = [
                    _createTextVNode("转移", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: batchDeleteDialog.value,
      "onUpdate:modelValue": _cache[168] || (_cache[168] = $event => ((batchDeleteDialog).value = $event)),
      "max-width": "28rem"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, null, {
              default: _withCtx(() => [...(_cache[460] || (_cache[460] = [
                _createTextVNode("批量删除托管种子", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_VCardText, { class: "text-body-2" }, {
              default: _withCtx(() => [
                _cache[461] || (_cache[461] = _createTextVNode(" 确认删除选中的 ", -1)),
                _createElementVNode("b", null, _toDisplayString(selectedHashes.value.length), 1),
                _cache[462] || (_cache[462] = _createTextVNode(" 个种子？ ", -1)),
                _cache[463] || (_cache[463] = _createElementVNode("br", null, null, -1)),
                _createElementVNode("span", _hoisted_303, " 将按任务设置" + _toDisplayString(selectedTask.value.delete_files ? '连同文件' : '保留文件') + "从下载器删除，不可撤销。 ", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_VCardActions, null, {
              default: _withCtx(() => [
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  variant: "text",
                  onClick: _cache[166] || (_cache[166] = $event => (batchDeleteDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[464] || (_cache[464] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  color: "error",
                  variant: "flat",
                  loading: batchBusy.value,
                  onClick: _cache[167] || (_cache[167] = $event => (batchAction('delete')))
                }, {
                  default: _withCtx(() => [...(_cache[465] || (_cache[465] = [
                    _createTextVNode("删除", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: torrentDeleteDialog.value,
      "onUpdate:modelValue": _cache[170] || (_cache[170] = $event => ((torrentDeleteDialog).value = $event)),
      "max-width": "28rem"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, { class: "text-wrap" }, {
              default: _withCtx(() => [...(_cache[466] || (_cache[466] = [
                _createTextVNode("删除托管种子", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_VCardText, { class: "text-body-2" }, {
              default: _withCtx(() => [
                _createTextVNode(" 确认删除「" + _toDisplayString(pendingTorrentDelete.value?.title || '该种子') + "」？ ", 1),
                _cache[467] || (_cache[467] = _createElementVNode("br", null, null, -1)),
                _createElementVNode("span", _hoisted_304, " 将按任务设置" + _toDisplayString(selectedTask.value.delete_files ? '连同文件' : '保留文件') + "从下载器删除，不可撤销。 ", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_VCardActions, null, {
              default: _withCtx(() => [
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  variant: "text",
                  onClick: _cache[169] || (_cache[169] = $event => (torrentDeleteDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[468] || (_cache[468] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  color: "error",
                  variant: "flat",
                  loading: saving.value,
                  onClick: confirmTorrentDelete
                }, {
                  default: _withCtx(() => [...(_cache[469] || (_cache[469] = [
                    _createTextVNode("删除", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: deleteDialog.value,
      "onUpdate:modelValue": [
        _cache[173] || (_cache[173] = $event => ((deleteDialog).value = $event)),
        onDeleteDialog
      ],
      "max-width": "34rem"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, {
          title: "删除魔力任务",
          class: "magicflow-dialog"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardText, null, {
              default: _withCtx(() => [
                _createTextVNode(" 确认删除「" + _toDisplayString(selectedTask.value?.name) + "」？ ", 1)
              ]),
              _: 1
            }),
            (handoverLoading.value)
              ? (_openBlock(), _createBlock(_component_VCardText, {
                  key: 0,
                  class: "magicflow-settings-hint"
                }, {
                  default: _withCtx(() => [...(_cache[470] || (_cache[470] = [
                    _createTextVNode("正在统计名下种子…", -1)
                  ]))]),
                  _: 1
                }))
              : (handover.value)
                ? (_openBlock(), _createBlock(_component_VCardText, {
                    key: 1,
                    class: "magicflow-settings-hint"
                  }, {
                    default: _withCtx(() => [
                      _cache[480] || (_cache[480] = _createTextVNode(" 名下 ", -1)),
                      _createElementVNode("strong", null, _toDisplayString(handover.value.managed), 1),
                      _createTextVNode(" 个种子 · " + _toDisplayString(handover.value.size_gb) + " GB ", 1),
                      (handover.value.auto_handover?.length)
                        ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                            _cache[477] || (_cache[477] = _createElementVNode("br", null, null, -1)),
                            _createVNode(_component_VAlert, {
                              density: "compact",
                              variant: "tonal",
                              color: "info",
                              class: "mt-2"
                            }, {
                              default: _withCtx(() => [
                                _cache[471] || (_cache[471] = _createTextVNode(" 另有同站同状态任务「", -1)),
                                _createElementVNode("strong", null, _toDisplayString(handover.value.auto_handover[0].name), 1),
                                _createTextVNode("」用同一批标签 （" + _toDisplayString(handover.value.tag) + "），", 1),
                                _cache[472] || (_cache[472] = _createElementVNode("strong", null, "不交棒它也会接着管", -1)),
                                _cache[473] || (_cache[473] = _createTextVNode("。", -1)),
                                _cache[474] || (_cache[474] = _createElementVNode("br", null, null, -1)),
                                _cache[475] || (_cache[475] = _createElementVNode("strong", null, "默认退回静默池", -1)),
                                _cache[476] || (_cache[476] = _createTextVNode("（保文件）—— 想指定交给谁再在下面选。 ", -1))
                              ]),
                              _: 1
                            })
                          ], 64))
                        : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                            _cache[479] || (_cache[479] = _createElementVNode("br", null, null, -1)),
                            _createVNode(_component_VAlert, {
                              density: "compact",
                              variant: "tonal",
                              color: "info",
                              class: "mt-2"
                            }, {
                              default: _withCtx(() => [...(_cache[478] || (_cache[478] = [
                                _createElementVNode("strong", null, "默认退回静默池", -1),
                                _createTextVNode("（保文件）—— 想指定交给谁再在下面选。 ", -1)
                              ]))]),
                              _: 1
                            })
                          ], 64))
                    ]),
                    _: 1
                  }))
                : _createCommentVNode("", true),
            (handover.value)
              ? (_openBlock(), _createBlock(_component_VCardText, { key: 2 }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSelect, {
                      modelValue: handoverTarget.value,
                      "onUpdate:modelValue": _cache[171] || (_cache[171] = $event => ((handoverTarget).value = $event)),
                      items: handoverChoices.value,
                      "item-title": "text",
                      "item-value": "value",
                      density: "compact",
                      variant: "outlined",
                      "hide-details": "",
                      label: "名下种子怎么处理"
                    }, null, 8, ["modelValue", "items"])
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_VCardActions, null, {
              default: _withCtx(() => [
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  variant: "text",
                  onClick: _cache[172] || (_cache[172] = $event => (deleteDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[481] || (_cache[481] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  color: "error",
                  variant: "flat",
                  loading: saving.value,
                  onClick: confirmDeleteTask
                }, {
                  default: _withCtx(() => [...(_cache[482] || (_cache[482] = [
                    _createTextVNode("确认删除", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: cloudOpen.value,
      "onUpdate:modelValue": _cache[178] || (_cache[178] = $event => ((cloudOpen).value = $event)),
      "max-width": "52rem",
      scrollable: "",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-cloud-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_305, [
              _cache[484] || (_cache[484] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "云盘归档", -1)),
              _createElementVNode("div", _hoisted_306, [
                _createVNode(_component_VBtn, {
                  variant: "text",
                  color: "primary",
                  size: "small",
                  "prepend-icon": "mdi-refresh",
                  loading: cloudLoading.value,
                  onClick: loadCloud
                }, {
                  default: _withCtx(() => [...(_cache[483] || (_cache[483] = [
                    _createTextVNode("刷新", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  size: "small",
                  variant: "text",
                  "aria-label": "关闭",
                  onClick: _cache[174] || (_cache[174] = $event => (cloudOpen.value = false))
                })
              ])
            ]),
            _createVNode(_component_VDivider),
            _createVNode(_component_VCardText, { class: "magicflow-cloud-dialog__body" }, {
              default: _withCtx(() => [
                (!cloudCfg.value.enabled)
                  ? (_openBlock(), _createBlock(_component_VAlert, {
                      key: 0,
                      type: "info",
                      variant: "tonal",
                      density: "compact",
                      class: "mb-2"
                    }, {
                      default: _withCtx(() => [...(_cache[485] || (_cache[485] = [
                        _createTextVNode(" 云盘归档未启用（「插件设置 → 云盘归档」里开启并填 OpenList 地址 / Token）。 ", -1)
                      ]))]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                _createElementVNode("div", _hoisted_307, [
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(cloudPlanStats.value?.pending ?? 0), 1),
                    _cache[486] || (_cache[486] = _createTextVNode(" 待上传", -1))
                  ]),
                  _cache[490] || (_cache[490] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(cloudPlanStats.value?.remote_exists ?? 0), 1),
                    _cache[487] || (_cache[487] = _createTextVNode(" 远端已有", -1))
                  ]),
                  _cache[491] || (_cache[491] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(cloudPlanStats.value?.done ?? 0), 1),
                    _cache[488] || (_cache[488] = _createTextVNode(" 已归档", -1))
                  ]),
                  _cache[492] || (_cache[492] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, _toDisplayString(cloudPlanStats.value?.pending_gb ?? 0) + " GB", 1),
                  _cache[493] || (_cache[493] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(cloudState.value?.record_count ?? 0), 1),
                    _cache[489] || (_cache[489] = _createTextVNode(" 条记录", -1))
                  ])
                ]),
                _cache[501] || (_cache[501] = _createElementVNode("div", { class: "magicflow-cloud-dialog__note" }, [
                  _createTextVNode(" 上传到 OpenList 可写存储 → 同一夸克目录 → Strm 视图自动生成播放指针 → 影视直接能看。 默认"),
                  _createElementVNode("strong", null, "只上传不删除"),
                  _createTextVNode("；本地删除需单独确认。 ")
                ], -1)),
                _createElementVNode("div", _hoisted_308, [
                  _createVNode(_component_VBtn, {
                    variant: "tonal",
                    color: "primary",
                    size: "small",
                    "prepend-icon": "mdi-connection",
                    loading: cloudTesting.value,
                    onClick: testCloud
                  }, {
                    default: _withCtx(() => [...(_cache[494] || (_cache[494] = [
                      _createTextVNode("测试连接", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"]),
                  _createVNode(_component_VBtn, {
                    variant: "tonal",
                    size: "small",
                    "prepend-icon": "mdi-clipboard-list-outline",
                    loading: cloudPlanning.value,
                    onClick: planCloud
                  }, {
                    default: _withCtx(() => [...(_cache[495] || (_cache[495] = [
                      _createTextVNode("扫描候选", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"]),
                  _createVNode(_component_VBtn, {
                    variant: "tonal",
                    size: "small",
                    "prepend-icon": "mdi-play-circle-outline",
                    loading: cloudRunning.value,
                    onClick: _cache[175] || (_cache[175] = $event => (runCloud(true)))
                  }, {
                    default: _withCtx(() => [...(_cache[496] || (_cache[496] = [
                      _createTextVNode("演练归档", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"]),
                  _createVNode(_component_VBtn, {
                    color: "primary",
                    variant: "flat",
                    size: "small",
                    "prepend-icon": "mdi-cloud-upload-outline",
                    loading: cloudRunning.value,
                    onClick: _cache[176] || (_cache[176] = $event => (runCloud(false)))
                  }, {
                    default: _withCtx(() => [...(_cache[497] || (_cache[497] = [
                      _createTextVNode("开始归档", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"]),
                  _createVNode(_component_VTextField, {
                    modelValue: cloudLimit.value,
                    "onUpdate:modelValue": _cache[177] || (_cache[177] = $event => ((cloudLimit).value = $event)),
                    modelModifiers: { number: true },
                    label: "本轮条数",
                    type: "number",
                    variant: "outlined",
                    density: "compact",
                    "hide-details": "",
                    class: "magicflow-cloud-dialog__limit"
                  }, null, 8, ["modelValue"])
                ]),
                (cloudTestMsg.value)
                  ? (_openBlock(), _createBlock(_component_VAlert, {
                      key: 1,
                      type: cloudTestOk.value ? 'success' : 'error',
                      variant: "tonal",
                      density: "compact",
                      class: "my-2"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(cloudTestMsg.value), 1)
                      ]),
                      _: 1
                    }, 8, ["type"]))
                  : _createCommentVNode("", true),
                (cloudState.value?.running)
                  ? (_openBlock(), _createBlock(_component_VAlert, {
                      key: 2,
                      type: "info",
                      variant: "tonal",
                      density: "compact",
                      class: "my-2"
                    }, {
                      default: _withCtx(() => [...(_cache[498] || (_cache[498] = [
                        _createTextVNode(" 归档任务正在后台执行（可关闭本窗口，进度看下方列表与「操作记录」）。 ", -1)
                      ]))]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                _createVNode(_component_VSheet, {
                  tag: "section",
                  class: "magicflow-panel app-surface-static mt-2"
                }, {
                  default: _withCtx(() => [
                    _cache[500] || (_cache[500] = _createElementVNode("header", { class: "magicflow-panel__head" }, [
                      _createElementVNode("div", null, [
                        _createElementVNode("div", { class: "text-subtitle-2 font-weight-medium" }, "归档候选"),
                        _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "点「扫描候选」列出可上传文件；逐条点「上传」立即传该文件（后台执行）")
                      ])
                    ], -1)),
                    (cloudLoading.value && !cloudPlanItems.value.length)
                      ? (_openBlock(), _createElementBlock("p", _hoisted_309, "加载中…"))
                      : (!cloudPlanItems.value.length)
                        ? (_openBlock(), _createElementBlock("p", _hoisted_310, " 还没有候选。点上方「扫描候选」；若为 0，检查设置里的「扫描目录 / 体积范围 / 最小入库天数」。 "))
                        : _createCommentVNode("", true),
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(cloudPlanItems.value, (it) => {
                      return (_openBlock(), _createElementBlock("div", {
                        key: it.path,
                        class: "magicflow-cloud-row"
                      }, [
                        _createElementVNode("div", _hoisted_311, [
                          _createElementVNode("div", _hoisted_312, _toDisplayString(it.name), 1),
                          _createElementVNode("div", _hoisted_313, _toDisplayString(it.rel) + " · " + _toDisplayString(it.size_gb) + " GB", 1),
                          (it.message || (cloudRecordFor(it) || {}).error)
                            ? (_openBlock(), _createElementBlock("div", _hoisted_314, _toDisplayString(it.message || (cloudRecordFor(it) || {}).error), 1))
                            : _createCommentVNode("", true)
                        ]),
                        _createElementVNode("div", _hoisted_315, [
                          _createVNode(_component_VChip, {
                            size: "x-small",
                            variant: "tonal",
                            color: _unref(cloudStatusMeta)(cloudRecordFor(it)?.status || it.status).color
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(_unref(cloudStatusMeta)(cloudRecordFor(it)?.status || it.status).text), 1)
                            ]),
                            _: 2
                          }, 1032, ["color"]),
                          _createVNode(_component_VBtn, {
                            size: "x-small",
                            variant: "tonal",
                            color: "primary",
                            loading: cloudUploadingPath.value === it.path,
                            onClick: $event => (uploadCloudOne(it))
                          }, {
                            default: _withCtx(() => [...(_cache[499] || (_cache[499] = [
                              _createTextVNode("上传", -1)
                            ]))]),
                            _: 1
                          }, 8, ["loading", "onClick"])
                        ])
                      ]))
                    }), 128))
                  ]),
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
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      modelValue: doubanServiceOpen.value,
      "onUpdate:modelValue": _cache[183] || (_cache[183] = $event => ((doubanServiceOpen).value = $event)),
      "max-width": "46rem",
      scrollable: "",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-douban-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_316, [
              _cache[503] || (_cache[503] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "豆瓣评分服务", -1)),
              _createElementVNode("div", _hoisted_317, [
                _createVNode(_component_VBtn, {
                  variant: "text",
                  color: "primary",
                  size: "small",
                  "prepend-icon": "mdi-refresh",
                  onClick: loadDoubanService
                }, {
                  default: _withCtx(() => [...(_cache[502] || (_cache[502] = [
                    _createTextVNode("刷新", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  size: "small",
                  variant: "text",
                  "aria-label": "关闭",
                  onClick: _cache[179] || (_cache[179] = $event => (doubanServiceOpen.value = false))
                })
              ])
            ]),
            _createVNode(_component_VDivider),
            _createVNode(_component_VCardText, { class: "magicflow-douban-dialog__body" }, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_318, [
                  _createVNode(_component_VChip, {
                    size: "small",
                    color: doubanServiceData.value.ok ? 'success' : 'error',
                    variant: "tonal"
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(doubanServiceData.value.ok ? '服务正常' : '服务不可用（回退 TMDB）'), 1)
                    ]),
                    _: 1
                  }, 8, ["color"]),
                  _cache[506] || (_cache[506] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, [
                    _cache[504] || (_cache[504] = _createTextVNode("库 ", -1)),
                    _createElementVNode("strong", null, _toDisplayString(fmtCount(doubanServiceData.value.records)), 1),
                    _cache[505] || (_cache[505] = _createTextVNode(" 条", -1))
                  ]),
                  _cache[507] || (_cache[507] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, "缓存 " + _toDisplayString(fmtCount(doubanServiceData.value.cache?.total)) + "（负 " + _toDisplayString(doubanServiceData.value.cache?.negative || 0) + "）", 1)
                ]),
                _createElementVNode("div", _hoisted_319, " 地址：" + _toDisplayString(doubanServiceData.value.service || '（未配置）') + "。独立服务 magicflow-douban，本地查询 <1ms，不受豆瓣限流影响。 ", 1),
                _createVNode(_component_VSheet, {
                  tag: "section",
                  class: "magicflow-panel app-surface-static mt-2"
                }, {
                  default: _withCtx(() => [
                    _createElementVNode("header", _hoisted_320, [
                      _cache[508] || (_cache[508] = _createElementVNode("div", null, [
                        _createElementVNode("div", { class: "text-subtitle-2 font-weight-medium" }, "后台数据采集（慢爬）"),
                        _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, " 从豆瓣「选电影」接口（一次 20 条带评分）按类型×题材×排序逐步枚举，限速 + 每日上限，进度落库可续跑 ")
                      ], -1)),
                      _createVNode(_component_VChip, {
                        size: "small",
                        color: doubanCrawl.value.running ? 'success' : 'warning',
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(doubanCrawl.value.running ? '采集中' : '已停止'), 1)
                        ]),
                        _: 1
                      }, 8, ["color"])
                    ]),
                    _createElementVNode("div", _hoisted_321, [
                      _createElementVNode("div", _hoisted_322, [
                        _cache[509] || (_cache[509] = _createElementVNode("span", null, "进度", -1)),
                        _createElementVNode("span", _hoisted_323, [
                          _createTextVNode(" 组合 " + _toDisplayString(doubanCrawl.value.spec_index || 0) + " / " + _toDisplayString(doubanCrawl.value.spec_total || 0) + " ", 1),
                          (doubanCrawl.value.current)
                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                _createTextVNode("· 当前 " + _toDisplayString(doubanCrawl.value.current.tags || '（全部）') + " / " + _toDisplayString(doubanCrawl.value.current.sort), 1)
                              ], 64))
                            : _createCommentVNode("", true)
                        ])
                      ]),
                      _createVNode(_component_VProgressLinear, {
                        "model-value": doubanCrawlProgress.value,
                        height: "6",
                        rounded: "",
                        color: "primary",
                        class: "my-2"
                      }, null, 8, ["model-value"]),
                      _createElementVNode("div", _hoisted_324, [
                        _createElementVNode("span", null, [
                          _cache[510] || (_cache[510] = _createTextVNode("请求 ", -1)),
                          _createElementVNode("strong", null, _toDisplayString(doubanCrawl.value.requests || 0), 1)
                        ]),
                        _createElementVNode("span", null, [
                          _cache[511] || (_cache[511] = _createTextVNode("今日 ", -1)),
                          _createElementVNode("strong", null, _toDisplayString(doubanCrawl.value.day_requests || 0), 1),
                          _createTextVNode(" / " + _toDisplayString(doubanCrawl.value.daily_max || '—'), 1)
                        ]),
                        _createElementVNode("span", null, [
                          _cache[512] || (_cache[512] = _createTextVNode("已抓 ", -1)),
                          _createElementVNode("strong", null, _toDisplayString(fmtCount(doubanCrawl.value.items)), 1),
                          _cache[513] || (_cache[513] = _createTextVNode(" 条", -1))
                        ]),
                        _createElementVNode("span", null, [
                          _cache[514] || (_cache[514] = _createTextVNode("新增 ", -1)),
                          _createElementVNode("strong", null, _toDisplayString(fmtCount(doubanCrawl.value.new)), 1),
                          _cache[515] || (_cache[515] = _createTextVNode(" 条", -1))
                        ]),
                        _createElementVNode("span", null, [
                          _cache[516] || (_cache[516] = _createTextVNode("错误 ", -1)),
                          _createElementVNode("strong", null, _toDisplayString(doubanCrawl.value.errors || 0), 1)
                        ])
                      ]),
                      (doubanCrawl.value.blocked_for > 0)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_325, " ⚠ 触发限流/退避，暂停 " + _toDisplayString(doubanCrawl.value.blocked_for) + " 秒后继续 ", 1))
                        : (doubanCrawl.value.last_error)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_326, " 最近异常：" + _toDisplayString(doubanCrawl.value.last_error), 1))
                          : _createCommentVNode("", true),
                      _createElementVNode("div", _hoisted_327, [
                        (doubanCrawl.value.running)
                          ? (_openBlock(), _createBlock(_component_VBtn, {
                              key: 0,
                              size: "small",
                              variant: "tonal",
                              color: "warning",
                              "prepend-icon": "mdi-pause",
                              loading: doubanServiceActing.value === 'stop',
                              onClick: _cache[180] || (_cache[180] = $event => (doubanCrawlAction('stop')))
                            }, {
                              default: _withCtx(() => [...(_cache[517] || (_cache[517] = [
                                _createTextVNode("暂停采集", -1)
                              ]))]),
                              _: 1
                            }, 8, ["loading"]))
                          : (_openBlock(), _createBlock(_component_VBtn, {
                              key: 1,
                              size: "small",
                              variant: "tonal",
                              color: "success",
                              "prepend-icon": "mdi-play",
                              loading: doubanServiceActing.value === 'start',
                              onClick: _cache[181] || (_cache[181] = $event => (doubanCrawlAction('start')))
                            }, {
                              default: _withCtx(() => [...(_cache[518] || (_cache[518] = [
                                _createTextVNode("继续采集", -1)
                              ]))]),
                              _: 1
                            }, 8, ["loading"])),
                        _createVNode(_component_VBtn, {
                          size: "small",
                          variant: "text",
                          color: "primary",
                          "prepend-icon": "mdi-restart",
                          loading: doubanServiceActing.value === 'reset',
                          onClick: _cache[182] || (_cache[182] = $event => (doubanCrawlAction('reset')))
                        }, {
                          default: _withCtx(() => [...(_cache[519] || (_cache[519] = [
                            _createTextVNode("从头重跑", -1)
                          ]))]),
                          _: 1
                        }, 8, ["loading"])
                      ])
                    ])
                  ]),
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
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      modelValue: crossseedOpen.value,
      "onUpdate:modelValue": _cache[186] || (_cache[186] = $event => ((crossseedOpen).value = $event)),
      "max-width": "52rem",
      scrollable: "",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-crossseed-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_328, [
              _cache[521] || (_cache[521] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "跨站免费取种", -1)),
              _createElementVNode("div", _hoisted_329, [
                _createVNode(_component_VBtn, {
                  variant: "text",
                  color: "primary",
                  size: "small",
                  "prepend-icon": "mdi-refresh",
                  onClick: loadCrossseed
                }, {
                  default: _withCtx(() => [...(_cache[520] || (_cache[520] = [
                    _createTextVNode("刷新", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  size: "small",
                  variant: "text",
                  "aria-label": "关闭",
                  onClick: _cache[184] || (_cache[184] = $event => (crossseedOpen.value = false))
                })
              ])
            ]),
            _createVNode(_component_VDivider),
            _createVNode(_component_VCardText, { class: "magicflow-crossseed-dialog__body" }, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_330, [
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(crossseedData.value.count || 0), 1),
                    _cache[522] || (_cache[522] = _createTextVNode(" 待回辅", -1))
                  ]),
                  _cache[525] || (_cache[525] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString((crossseedData.value.enabled_tasks || []).length), 1),
                    _cache[523] || (_cache[523] = _createTextVNode(" 个任务开了跨站", -1))
                  ]),
                  _cache[526] || (_cache[526] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, "标签 " + _toDisplayString(crossseedData.value.tag || '魔流-跨站'), 1),
                  _cache[527] || (_cache[527] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(crossseedData.value.sources_count || 0), 1),
                    _cache[524] || (_cache[524] = _createTextVNode(" 来源份 H&R 保种中", -1))
                  ])
                ]),
                _cache[537] || (_cache[537] = _createElementVNode("div", { class: "magicflow-recommend-dialog__note" }, [
                  _createTextVNode(" 在他站"),
                  _createElementVNode("strong", null, "免费"),
                  _createTextVNode("下 → 下完把目标站种子指向同一批文件回辅（校验通过才保留）。 本站判断「非免费」的候选只走跨站，"),
                  _createElementVNode("strong", null, "绝不在本站下载"),
                  _createTextVNode("。 ")
                ], -1)),
                _createVNode(_component_VSheet, {
                  tag: "section",
                  class: "magicflow-panel app-surface-static mt-2"
                }, {
                  default: _withCtx(() => [
                    _createElementVNode("header", _hoisted_331, [
                      _cache[529] || (_cache[529] = _createElementVNode("div", null, [
                        _createElementVNode("div", { class: "text-subtitle-2 font-weight-medium" }, "兄弟站流量兜底"),
                        _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, [
                          _createTextVNode(" 判「免费」可能出错 → 取种期间核对来源站免费状态 + 下载量增量： 发现其实不免费立即"),
                          _createElementVNode("strong", null, "删种 + 拉黑该站"),
                          _createTextVNode("（需人工确认后解除） ")
                        ])
                      ], -1)),
                      _createVNode(_component_VBtn, {
                        size: "small",
                        variant: "tonal",
                        color: "primary",
                        "prepend-icon": "mdi-shield-search",
                        loading: crossseedActing.value === 'guard',
                        onClick: runCrossseedGuard
                      }, {
                        default: _withCtx(() => [...(_cache[528] || (_cache[528] = [
                          _createTextVNode("立即核对", -1)
                        ]))]),
                        _: 1
                      }, 8, ["loading"])
                    ]),
                    _createElementVNode("div", _hoisted_332, [
                      _createVNode(_component_VChip, {
                        size: "small",
                        color: crossseedGuard.value.enabled === false ? 'error' : 'success',
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(crossseedGuard.value.enabled === false ? '兜底已关闭' : '兜底已启用'), 1)
                        ]),
                        _: 1
                      }, 8, ["color"]),
                      _createElementVNode("span", _hoisted_333, " 阈值：下载增量 > 体积 × " + _toDisplayString(crossseedGuard.value.pct ?? 5) + "%（且 ≥ " + _toDisplayString(crossseedGuard.value.min_mb ?? 50) + "MB） · 核对间隔 " + _toDisplayString(crossseedGuard.value.interval_min ?? 15) + " 分钟 ", 1)
                    ]),
                    (crossseedBanned.value.length)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_334, [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(crossseedBanned.value, (b) => {
                            return (_openBlock(), _createElementBlock("article", {
                              key: b.domain,
                              class: "magicflow-crossseed-ban"
                            }, [
                              _createElementVNode("div", _hoisted_335, [
                                _createElementVNode("strong", null, _toDisplayString(b.domain), 1),
                                _createElementVNode("span", _hoisted_336, _toDisplayString(b.reason) + " · " + _toDisplayString(b.age_min) + " 分钟前", 1)
                              ]),
                              _createVNode(_component_VBtn, {
                                size: "x-small",
                                variant: "text",
                                color: "primary",
                                loading: crossseedActing.value === 'unban:' + b.domain,
                                onClick: $event => (unbanCrossseed(b.domain))
                              }, {
                                default: _withCtx(() => [...(_cache[530] || (_cache[530] = [
                                  _createTextVNode("解除拉黑", -1)
                                ]))]),
                                _: 1
                              }, 8, ["loading", "onClick"])
                            ]))
                          }), 128)),
                          _createVNode(_component_VBtn, {
                            size: "x-small",
                            variant: "text",
                            color: "warning",
                            onClick: _cache[185] || (_cache[185] = $event => (unbanCrossseed('')))
                          }, {
                            default: _withCtx(() => [...(_cache[531] || (_cache[531] = [
                              _createTextVNode("全部解除", -1)
                            ]))]),
                            _: 1
                          })
                        ]))
                      : (_openBlock(), _createElementBlock("div", _hoisted_337, "暂无被拉黑的来源站（出现「判免费实际不免费」时才会拉黑）。"))
                  ]),
                  _: 1
                }),
                ((crossseedSources.value || []).length)
                  ? (_openBlock(), _createBlock(_component_VSheet, {
                      key: 0,
                      tag: "section",
                      class: "magicflow-panel app-surface-static mt-3"
                    }, {
                      default: _withCtx(() => [
                        _cache[533] || (_cache[533] = _createElementVNode("header", { class: "magicflow-panel__head" }, [
                          _createElementVNode("div", null, [
                            _createElementVNode("div", { class: "text-subtitle-2 font-weight-medium" }, "来源份 H&R 保种中"),
                            _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, " 他站那份已下完（回辅成功/失败都要留在来源站挂种，否则算 H&R）—— 保种期内任何任务都不会删它、也不会改它的标签 ")
                          ])
                        ], -1)),
                        _createElementVNode("div", _hoisted_338, [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(crossseedSources.value, (it) => {
                            return (_openBlock(), _createElementBlock("article", {
                              key: it.sib_hash,
                              class: "magicflow-crossseed-item"
                            }, [
                              _createElementVNode("div", _hoisted_339, [
                                _createElementVNode("strong", {
                                  title: it.title
                                }, _toDisplayString(it.title || it.sib_hash), 9, _hoisted_340),
                                _createElementVNode("span", _hoisted_341, [
                                  _createVNode(_component_VChip, {
                                    size: "x-small",
                                    variant: "tonal",
                                    color: "warning"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(_toDisplayString(it.site_b), 1)
                                    ]),
                                    _: 2
                                  }, 1024),
                                  (it.size_gb)
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                        _createTextVNode(" · " + _toDisplayString(Number(it.size_gb).toFixed(2)) + "G", 1)
                                      ], 64))
                                    : _createCommentVNode("", true),
                                  (it.fulfilled)
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                        _createVNode(_component_VChip, {
                                          size: "x-small",
                                          variant: "tonal",
                                          color: "success"
                                        }, {
                                          default: _withCtx(() => [...(_cache[532] || (_cache[532] = [
                                            _createTextVNode("义务已完成", -1)
                                          ]))]),
                                          _: 1
                                        }),
                                        _createTextVNode(" · 已挂 " + _toDisplayString(it.seeded_h) + "h ", 1),
                                        (it.need_hours)
                                          ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                              _createTextVNode("（需 " + _toDisplayString(it.need_hours) + "h）", 1)
                                            ], 64))
                                          : _createCommentVNode("", true)
                                      ], 64))
                                    : (it.need_hours)
                                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                                          _createTextVNode(" · 已挂 " + _toDisplayString(it.seeded_h) + "h / 需 " + _toDisplayString(it.need_hours) + "h · 窗口还剩 " + _toDisplayString(formatRemain(it.remain_min)), 1)
                                        ], 64))
                                      : (_openBlock(), _createElementBlock(_Fragment, { key: 3 }, [
                                          _createTextVNode(" · 要求 " + _toDisplayString(it.hours) + "h · " + _toDisplayString(it.done ? '保种期已满（可回收）' : `还剩 ${formatRemain(it.remain_min)}`), 1)
                                        ], 64)),
                                  (it.hours_src)
                                    ? (_openBlock(), _createElementBlock("span", _hoisted_342, "（" + _toDisplayString(String(it.hours_src).startsWith('种子标记') ? '种子自带 H&R 标记' : '站点规则库') + "）", 1))
                                    : _createCommentVNode("", true),
                                  (it.files_shared)
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 5 }, [
                                        _createTextVNode(" · 文件与目标站共用")
                                      ], 64))
                                    : _createCommentVNode("", true)
                                ])
                              ])
                            ]))
                          }), 128))
                        ])
                      ]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                _createVNode(_component_VSheet, {
                  tag: "section",
                  class: "magicflow-panel app-surface-static mt-3"
                }, {
                  default: _withCtx(() => [
                    _createElementVNode("header", _hoisted_343, [
                      _cache[535] || (_cache[535] = _createElementVNode("div", null, [
                        _createElementVNode("div", { class: "text-subtitle-2 font-weight-medium" }, "待回辅队列"),
                        _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "他站下完 → 自动回辅目标站；超过 6 小时未完成会放弃")
                      ], -1)),
                      (crossseedPending.value.length)
                        ? (_openBlock(), _createBlock(_component_VBtn, {
                            key: 0,
                            size: "small",
                            variant: "text",
                            color: "error",
                            loading: crossseedActing.value === 'clear',
                            onClick: clearCrossseed
                          }, {
                            default: _withCtx(() => [...(_cache[534] || (_cache[534] = [
                              _createTextVNode("清空队列", -1)
                            ]))]),
                            _: 1
                          }, 8, ["loading"]))
                        : _createCommentVNode("", true)
                    ]),
                    _createElementVNode("div", _hoisted_344, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(crossseedPending.value, (it) => {
                        return (_openBlock(), _createElementBlock("article", {
                          key: it.sib_hash,
                          class: "magicflow-crossseed-item"
                        }, [
                          _createElementVNode("div", _hoisted_345, [
                            _createElementVNode("strong", {
                              title: it.title || it.sib_hash
                            }, _toDisplayString(it.title || it.sib_hash), 9, _hoisted_346),
                            _createElementVNode("span", _hoisted_347, [
                              _createVNode(_component_VChip, {
                                size: "x-small",
                                variant: "tonal",
                                color: "info"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(it.site_b) + " → " + _toDisplayString(it.site_a), 1)
                                ]),
                                _: 2
                              }, 1024),
                              (it.size_gb)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                    _createTextVNode(" · " + _toDisplayString(Number(it.size_gb).toFixed(2)) + "G", 1)
                                  ], 64))
                                : _createCommentVNode("", true),
                              _createTextVNode(" · " + _toDisplayString(crossseedStateText(it)) + " · " + _toDisplayString(it.age_min) + " 分钟前 ", 1),
                              (it.task_name)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                    _createTextVNode(" · " + _toDisplayString(it.task_name), 1)
                                  ], 64))
                                : _createCommentVNode("", true)
                            ]),
                            (Number.isFinite(Number(it.progress)))
                              ? (_openBlock(), _createBlock(_component_VProgressLinear, {
                                  key: 0,
                                  "model-value": Math.round(Number(it.progress) * 100),
                                  height: "4",
                                  rounded: "",
                                  color: "primary",
                                  class: "mt-1"
                                }, null, 8, ["model-value"]))
                              : _createCommentVNode("", true)
                          ]),
                          _createVNode(_component_VBtn, {
                            size: "x-small",
                            variant: "text",
                            color: "error",
                            "prepend-icon": "mdi-delete-outline",
                            loading: crossseedActing.value === 'drop:' + it.sib_hash,
                            onClick: $event => (dropCrossseed(it.sib_hash))
                          }, {
                            default: _withCtx(() => [...(_cache[536] || (_cache[536] = [
                              _createTextVNode("删除", -1)
                            ]))]),
                            _: 1
                          }, 8, ["loading", "onClick"])
                        ]))
                      }), 128)),
                      (!crossseedPending.value.length)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_348, " 暂无待回辅的跨站种子。任务配置里开启「跨站免费取种」后，本站非免费的候选会自动去他站找免费源。 "))
                        : _createCommentVNode("", true)
                    ])
                  ]),
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
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      modelValue: recommendOpen.value,
      "onUpdate:modelValue": _cache[191] || (_cache[191] = $event => ((recommendOpen).value = $event)),
      "max-width": "46rem",
      scrollable: "",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-recommend-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_349, [
              _cache[539] || (_cache[539] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "推荐甄别", -1)),
              _createElementVNode("div", _hoisted_350, [
                _createVNode(_component_VBtn, {
                  variant: "text",
                  color: "primary",
                  size: "small",
                  "prepend-icon": "mdi-refresh",
                  onClick: loadRecommend
                }, {
                  default: _withCtx(() => [...(_cache[538] || (_cache[538] = [
                    _createTextVNode("刷新", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  size: "small",
                  variant: "text",
                  "aria-label": "关闭",
                  onClick: _cache[187] || (_cache[187] = $event => (recommendOpen.value = false))
                })
              ])
            ]),
            _createVNode(_component_VDivider),
            _createVNode(_component_VCardText, { class: "magicflow-recommend-dialog__body" }, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_351, [
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(recommendData.value.recommended || 0), 1),
                    _cache[540] || (_cache[540] = _createTextVNode(" 待确认", -1))
                  ]),
                  _cache[543] || (_cache[543] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(confirmedCount.value), 1),
                    _cache[541] || (_cache[541] = _createTextVNode(" 已入库", -1))
                  ]),
                  _cache[544] || (_cache[544] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, [
                    _createElementVNode("strong", null, _toDisplayString(pendingCount.value), 1),
                    _cache[542] || (_cache[542] = _createTextVNode(" 未达门槛", -1))
                  ]),
                  _cache[545] || (_cache[545] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, "共 " + _toDisplayString(recommendData.value.total || 0) + " 条", 1),
                  _cache[546] || (_cache[546] = _createElementVNode("i", null, "·", -1)),
                  _createElementVNode("span", null, "标签 " + _toDisplayString(recommendData.value.tag || '魔流-推荐'), 1)
                ]),
                _createElementVNode("div", _hoisted_352, [
                  _createTextVNode(" 评分 > " + _toDisplayString(recommendData.value.min_rating ?? 7.5), 1),
                  (recommendData.value.require_chart !== false)
                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                        _createTextVNode(" 或在榜 / 热映 / 订阅")
                      ], 64))
                    : _createCommentVNode("", true),
                  _createTextVNode(" · 过期 " + _toDisplayString(recommendData.value.expire_days ?? 7) + " 天 · 磁盘余量下限 " + _toDisplayString(recommendData.value.disk_min_free_gb ?? 50) + "G ", 1)
                ]),
                (recommendData.value.enabled === false)
                  ? (_openBlock(), _createBlock(_component_VAlert, {
                      key: 0,
                      type: "info",
                      variant: "tonal",
                      density: "compact",
                      class: "my-2"
                    }, {
                      default: _withCtx(() => [...(_cache[547] || (_cache[547] = [
                        _createTextVNode(" 推荐甄别已关闭（可在「插件设置 → 推荐」开启） ", -1)
                      ]))]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                _createVNode(_component_VSheet, {
                  tag: "section",
                  class: "magicflow-panel app-surface-static mt-2"
                }, {
                  default: _withCtx(() => [
                    _createElementVNode("header", _hoisted_353, [
                      _cache[549] || (_cache[549] = _createElementVNode("div", null, [
                        _createElementVNode("div", { class: "text-subtitle-2 font-weight-medium" }, "甄别结果"),
                        _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "全部任务汇总 · 确认 = 自动整理入库；忽略 = 删除该临时种（«待核实»也可手动确认）")
                      ], -1)),
                      _createElementVNode("div", _hoisted_354, [
                        (recSelectable.value.length)
                          ? (_openBlock(), _createBlock(_component_VBtn, {
                              key: 0,
                              size: "small",
                              variant: "text",
                              "prepend-icon": recAllChecked.value ? 'mdi-checkbox-multiple-marked-outline' : 'mdi-checkbox-multiple-blank-outline',
                              onClick: toggleAllRecs
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(recAllChecked.value ? '取消全选' : `全选 (${recSelectable.value.length})`), 1)
                              ]),
                              _: 1
                            }, 8, ["prepend-icon"]))
                          : _createCommentVNode("", true),
                        _createVNode(_component_VBtn, {
                          size: "small",
                          color: "primary",
                          variant: "tonal",
                          "prepend-icon": "mdi-tray-arrow-down",
                          disabled: !recSelectedList.value.length,
                          loading: recBatchActing.value,
                          onClick: _cache[188] || (_cache[188] = $event => (batchImportRecommend(false)))
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode("批量入库 (" + _toDisplayString(recSelectedList.value.length) + ")", 1)
                          ]),
                          _: 1
                        }, 8, ["disabled", "loading"]),
                        (recSelectable.value.length)
                          ? (_openBlock(), _createBlock(_component_VBtn, {
                              key: 1,
                              size: "small",
                              variant: "text",
                              loading: recBatchActing.value,
                              onClick: _cache[189] || (_cache[189] = $event => (batchImportRecommend(true)))
                            }, {
                              default: _withCtx(() => [...(_cache[548] || (_cache[548] = [
                                _createTextVNode("全部入库", -1)
                              ]))]),
                              _: 1
                            }, 8, ["loading"]))
                          : _createCommentVNode("", true),
                        _createVNode(_component_VBtn, {
                          size: "small",
                          variant: "text",
                          color: "primary",
                          "prepend-icon": showAllRecs.value ? 'mdi-eye-off-outline' : 'mdi-eye-outline',
                          onClick: _cache[190] || (_cache[190] = $event => (showAllRecs.value = !showAllRecs.value))
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(showAllRecs.value ? '仅看推荐' : (hiddenRecCount.value ? `显示全部候选 (+${hiddenRecCount.value})` : '显示全部候选')), 1)
                          ]),
                          _: 1
                        }, 8, ["prepend-icon"])
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_355, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(recommendItems.value, (rec) => {
                        return (_openBlock(), _createElementBlock("article", {
                          key: rec.hash,
                          class: _normalizeClass(["magicflow-rec", { 'magicflow-rec--sel': recommendActionable(rec) }])
                        }, [
                          (recommendActionable(rec))
                            ? (_openBlock(), _createBlock(_component_VCheckbox, {
                                key: 0,
                                "model-value": !!recSelected.value[rec.hash],
                                density: "compact",
                                "hide-details": "",
                                class: "magicflow-rec__check",
                                "aria-label": `选择 ${recName(rec)}`,
                                "onUpdate:modelValue": $event => (toggleRec(rec.hash))
                              }, null, 8, ["model-value", "aria-label", "onUpdate:modelValue"]))
                            : _createCommentVNode("", true),
                          _createElementVNode("div", _hoisted_356, [
                            (rec.poster)
                              ? (_openBlock(), _createElementBlock("img", {
                                  key: 0,
                                  src: rec.poster,
                                  alt: recName(rec),
                                  loading: "lazy",
                                  referrerpolicy: "no-referrer"
                                }, null, 8, _hoisted_357))
                              : (_openBlock(), _createBlock(_component_VIcon, {
                                  key: 1,
                                  icon: "mdi-movie-open-outline",
                                  size: "22"
                                }))
                          ]),
                          _createElementVNode("div", _hoisted_358, [
                            _createElementVNode("strong", {
                              title: rec.title || rec.hash
                            }, _toDisplayString(recName(rec)), 9, _hoisted_359),
                            _createElementVNode("span", _hoisted_360, [
                              _createVNode(_component_VChip, {
                                size: "x-small",
                                variant: "tonal",
                                color: _unref(recommendStatusMeta)(rec.status).color
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(_unref(recommendStatusMeta)(rec.status).text), 1)
                                ]),
                                _: 2
                              }, 1032, ["color"]),
                              (rec.media && rec.media.type)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                    _createTextVNode(" · " + _toDisplayString(rec.media.type), 1)
                                  ], 64))
                                : _createCommentVNode("", true),
                              (rec.rating)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                    _createTextVNode(" · 评分 " + _toDisplayString(Number(rec.rating).toFixed(1)), 1)
                                  ], 64))
                                : _createCommentVNode("", true),
                              (rec.size_gb)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                                    _createTextVNode(" · " + _toDisplayString(Number(rec.size_gb).toFixed(2)) + "G", 1)
                                  ], 64))
                                : _createCommentVNode("", true),
                              (rec.in_chart)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 3 }, [
                                    _createTextVNode(" · 在榜")
                                  ], 64))
                                : _createCommentVNode("", true),
                              (rec.in_subscribe)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 4 }, [
                                    _createTextVNode(" · 已订阅")
                                  ], 64))
                                : _createCommentVNode("", true)
                            ]),
                            _createElementVNode("span", _hoisted_361, [
                              _createTextVNode(" 首次发现 " + _toDisplayString(_unref(formatDateTime)(rec.first_seen)) + " ", 1),
                              (rec.import_result)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                    _createTextVNode(" · " + _toDisplayString(rec.import_result), 1)
                                  ], 64))
                                : _createCommentVNode("", true),
                              (rec.note)
                                ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                    _createTextVNode(" · " + _toDisplayString(rec.note), 1)
                                  ], 64))
                                : _createCommentVNode("", true)
                            ])
                          ]),
                          (recommendActionable(rec))
                            ? (_openBlock(), _createElementBlock("div", _hoisted_362, [
                                _createVNode(_component_VBtn, {
                                  size: "small",
                                  color: "primary",
                                  variant: "tonal",
                                  "prepend-icon": "mdi-check",
                                  loading: recommendActing.value === rec.hash + 'confirm',
                                  onClick: $event => (confirmRecommend(rec.hash))
                                }, {
                                  default: _withCtx(() => [...(_cache[550] || (_cache[550] = [
                                    _createTextVNode(" 确认入库 ", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["loading", "onClick"]),
                                _createVNode(_component_VBtn, {
                                  size: "small",
                                  color: "error",
                                  variant: "text",
                                  "prepend-icon": "mdi-delete-outline",
                                  loading: recommendActing.value === rec.hash + 'dismiss',
                                  onClick: $event => (dismissRecommend(rec.hash))
                                }, {
                                  default: _withCtx(() => [...(_cache[551] || (_cache[551] = [
                                    _createTextVNode(" 忽略删除 ", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["loading", "onClick"])
                              ]))
                            : _createCommentVNode("", true)
                        ], 2))
                      }), 128)),
                      (!recommendItems.value.length)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_363, [
                            _createTextVNode(" 暂无推荐" + _toDisplayString(showAllRecs.value ? '' : '（当前没有同时满足「评分 > ' + (recommendData.value.min_rating ?? 7.5) + ' 且在榜 / 热映 / 订阅」的资源）') + "。 ", 1),
                            (!showAllRecs.value && hiddenRecCount.value)
                              ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                  _createTextVNode("可点右上「显示全部候选 (+" + _toDisplayString(hiddenRecCount.value) + ")」看全部评估（含未达门槛的临时种）。", 1)
                                ], 64))
                              : _createCommentVNode("", true)
                          ]))
                        : _createCommentVNode("", true)
                    ])
                  ]),
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
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      modelValue: examOpen.value,
      "onUpdate:modelValue": _cache[193] || (_cache[193] = $event => ((examOpen).value = $event)),
      "max-width": "46rem",
      scrollable: "",
      fullscreen: isNarrow.value
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-exam-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_364, [
              _cache[553] || (_cache[553] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "新手考核", -1)),
              _createElementVNode("div", _hoisted_365, [
                _createVNode(_component_VBtn, {
                  variant: "text",
                  color: "primary",
                  size: "small",
                  "prepend-icon": "mdi-refresh",
                  onClick: loadExam
                }, {
                  default: _withCtx(() => [...(_cache[552] || (_cache[552] = [
                    _createTextVNode("刷新", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  size: "small",
                  variant: "text",
                  "aria-label": "关闭",
                  onClick: _cache[192] || (_cache[192] = $event => (examOpen.value = false))
                })
              ])
            ]),
            _createVNode(_component_VDivider),
            _createVNode(_component_VCardText, { class: "magicflow-exam-body" }, {
              default: _withCtx(() => [
                _createElementVNode("div", {
                  class: _normalizeClass(["magicflow-exam-hero", examUrgent.value ? 'is-urgent' : ''])
                }, [
                  _createElementVNode("div", _hoisted_366, [
                    _createElementVNode("span", _hoisted_367, _toDisplayString(examRows.value.length), 1),
                    _cache[554] || (_cache[554] = _createElementVNode("span", { class: "magicflow-exam-hero__cap" }, "站考核未过", -1))
                  ]),
                  _createElementVNode("div", _hoisted_368, [
                    (examNext.value)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_369, [
                          _createVNode(_component_VIcon, {
                            icon: "mdi-alarm",
                            size: "14"
                          }),
                          _createTextVNode(" 最近截止：" + _toDisplayString(examNext.value.site_name || ('站点 ' + examNext.value.site_id)) + " ", 1),
                          _createVNode(_component_VChip, {
                            size: "x-small",
                            variant: "tonal",
                            color: examUrgencyColor(examNext.value)
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode("剩 " + _toDisplayString(examDaysShort(examNext.value)), 1)
                            ]),
                            _: 1
                          }, 8, ["color"])
                        ]))
                      : _createCommentVNode("", true),
                    _createElementVNode("div", _hoisted_370, "待过 " + _toDisplayString(examPendingItems.value) + " 项 · " + _toDisplayString(examUrgentWeek.value) + " 站 7 天内截止", 1)
                  ])
                ], 2),
                (examData.value.enabled === false)
                  ? (_openBlock(), _createBlock(_component_VAlert, {
                      key: 0,
                      type: "info",
                      variant: "tonal",
                      density: "compact",
                      class: "my-2"
                    }, {
                      default: _withCtx(() => [...(_cache[555] || (_cache[555] = [
                        _createTextVNode(" 新手考核模块已关闭（可在「插件设置 → 考核」开启；开启后零额外 PV） ", -1)
                      ]))]),
                      _: 1
                    }))
                  : (!examRows.value.length)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_371, " 没有未通过的考核（或站点数据暂时取不到）。 "))
                    : _createCommentVNode("", true),
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(examRows.value, (row) => {
                  return (_openBlock(), _createBlock(_component_VSheet, {
                    key: row.site_id,
                    tag: "section",
                    class: "magicflow-exam-card"
                  }, {
                    default: _withCtx(() => [
                      _createElementVNode("header", _hoisted_372, [
                        _createElementVNode("div", _hoisted_373, [
                          _createElementVNode("span", _hoisted_374, _toDisplayString(row.site_name || ('站点 ' + row.site_id)), 1),
                          _createVNode(_component_VChip, {
                            size: "x-small",
                            variant: "tonal",
                            color: examUrgencyColor(row)
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode("剩 " + _toDisplayString(examDaysShort(row)), 1)
                            ]),
                            _: 2
                          }, 1032, ["color"]),
                          _createElementVNode("span", _hoisted_375, _toDisplayString(examPassedCount(row)) + "/" + _toDisplayString((row.exam.items || []).length) + " 已过", 1)
                        ]),
                        _createVNode(_component_VProgressLinear, {
                          "model-value": examSitePct(row),
                          height: "4",
                          rounded: "",
                          color: examUrgencyColor(row),
                          "bg-color": "rgba(var(--v-theme-on-surface), 0.12)"
                        }, null, 8, ["model-value", "color"])
                      ]),
                      _createElementVNode("ul", _hoisted_376, [
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(examVisibleItems(row), (it) => {
                          return (_openBlock(), _createElementBlock("li", {
                            key: it.idx,
                            class: _normalizeClass(["magicflow-exam-item", it.pass ? 'is-pass' : 'is-fail'])
                          }, [
                            _createElementVNode("span", _hoisted_377, _toDisplayString(it.label), 1),
                            (examItemGap(it))
                              ? (_openBlock(), _createElementBlock("span", _hoisted_378, "还差 " + _toDisplayString(examItemGap(it)), 1))
                              : _createCommentVNode("", true),
                            _createElementVNode("span", _hoisted_379, [
                              _createElementVNode("strong", null, _toDisplayString(it.cur), 1),
                              _createElementVNode("i", null, " / " + _toDisplayString(it.req), 1)
                            ]),
                            _createVNode(_component_VIcon, {
                              icon: it.pass ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline',
                              size: "14",
                              color: it.pass ? 'success' : 'error'
                            }, null, 8, ["icon", "color"]),
                            _createVNode(_component_VProgressLinear, {
                              class: "magicflow-exam-item__bar",
                              "model-value": examItemPct(it),
                              height: "4",
                              rounded: "",
                              color: it.pass ? 'success' : 'error',
                              "bg-color": "rgba(var(--v-theme-on-surface), 0.12)"
                            }, null, 8, ["model-value", "color"])
                          ], 2))
                        }), 128))
                      ]),
                      (examHiddenPassed(row) > 0)
                        ? (_openBlock(), _createElementBlock("button", {
                            key: 0,
                            type: "button",
                            class: "magicflow-exam-more",
                            onClick: $event => (examTogglePassed(row.site_id))
                          }, "显示已通过 " + _toDisplayString(examHiddenPassed(row)) + " 项", 9, _hoisted_380))
                        : (examShowPassed.value[row.site_id] && (row.exam.items || []).length > 1)
                          ? (_openBlock(), _createElementBlock("button", {
                              key: 1,
                              type: "button",
                              class: "magicflow-exam-more",
                              onClick: $event => (examTogglePassed(row.site_id))
                            }, "只看未通过", 8, _hoisted_381))
                          : _createCommentVNode("", true),
                      _createElementVNode("div", _hoisted_382, [
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(examActions(row), (a) => {
                          return (_openBlock(), _createElementBlock("article", {
                            key: a.key,
                            class: "magicflow-exam-act"
                          }, [
                            _createElementVNode("div", _hoisted_383, [
                              _createVNode(_component_VIcon, {
                                icon: a.icon,
                                size: "15"
                              }, null, 8, ["icon"]),
                              _createElementVNode("strong", null, _toDisplayString(a.label), 1),
                              (a.task_name)
                                ? (_openBlock(), _createBlock(_component_VChip, {
                                    key: 0,
                                    size: "x-small",
                                    variant: "text"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(_toDisplayString(a.task_name), 1)
                                    ]),
                                    _: 2
                                  }, 1024))
                                : _createCommentVNode("", true)
                            ]),
                            (a.warn)
                              ? (_openBlock(), _createBlock(_component_VAlert, {
                                  key: 0,
                                  type: "warning",
                                  variant: "tonal",
                                  density: "compact",
                                  class: "magicflow-exam-act__warn"
                                }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(a.warn), 1)
                                  ]),
                                  _: 2
                                }, 1024))
                              : _createCommentVNode("", true),
                            (a.notes.length)
                              ? (_openBlock(), _createElementBlock("ul", _hoisted_384, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(a.notes, (n, ni) => {
                                    return (_openBlock(), _createElementBlock("li", { key: ni }, _toDisplayString(n), 1))
                                  }), 128))
                                ]))
                              : _createCommentVNode("", true),
                            _createVNode(_component_VBtn, {
                              size: "small",
                              color: "primary",
                              variant: "tonal",
                              "prepend-icon": "mdi-play-circle-outline",
                              loading: examActing.value === `${a.kind}:${row.site_id}`,
                              onClick: $event => (examAct(row, a.kind))
                            }, {
                              default: _withCtx(() => [...(_cache[556] || (_cache[556] = [
                                _createTextVNode("一键起任务", -1)
                              ]))]),
                              _: 1
                            }, 8, ["loading", "onClick"])
                          ]))
                        }), 128)),
                        (!(row.plan || []).length)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_385, " 未识别到可执行动作（可能考核不要求下载量 / 或解析不出；可在「做种明细」里看站点实时数据）。 "))
                          : _createCommentVNode("", true)
                      ])
                    ]),
                    _: 2
                  }, 1024))
                }), 128)),
                _cache[557] || (_cache[557] = _createElementVNode("div", { class: "magicflow-exam-foot" }, "只统计「有 Cookie」的站点；已通过的默认不显示（可在「插件设置 → 考核」里改）", -1))
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue", "fullscreen"]),
    _createVNode(_component_VDialog, {
      "model-value": !!examConfirm.value,
      "max-width": "32rem",
      "onUpdate:modelValue": _cache[195] || (_cache[195] = v => { if (!v) examConfirm.value = null; })
    }, {
      default: _withCtx(() => [
        (examConfirm.value)
          ? (_openBlock(), _createBlock(_component_VCard, {
              key: 0,
              class: "magicflow-dialog"
            }, {
              default: _withCtx(() => [
                _cache[565] || (_cache[565] = _createElementVNode("header", { class: "magicflow-settings-dialog__head" }, [
                  _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "确认执行")
                ], -1)),
                _createVNode(_component_VDivider),
                _createVNode(_component_VCardText, { class: "d-flex flex-column ga-2" }, {
                  default: _withCtx(() => [
                    _createElementVNode("div", null, [
                      _cache[558] || (_cache[558] = _createTextVNode(" 将在 ", -1)),
                      _createElementVNode("strong", null, _toDisplayString(examConfirm.value.row.site_name), 1),
                      _cache[559] || (_cache[559] = _createTextVNode(" 上 ", -1)),
                      _createElementVNode("strong", null, _toDisplayString(examConfirm.value.item.kind === 'download' ? '创建 / 启用「考核下载」任务' : examConfirm.value.item.kind === 'upload' ? '创建 / 启用「考核刷流」任务' : '创建 / 启用「考核魔力」任务'), 1),
                      _cache[560] || (_cache[560] = _createTextVNode("： ", -1))
                    ]),
                    _createElementVNode("div", _hoisted_386, [
                      _cache[561] || (_cache[561] = _createTextVNode("任务名：", -1)),
                      _createElementVNode("code", null, _toDisplayString(examConfirm.value.item.task_name), 1)
                    ]),
                    ((examConfirm.value.item.notes || []).length)
                      ? (_openBlock(), _createElementBlock("ul", _hoisted_387, [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(examConfirm.value.item.notes, (n, ni) => {
                            return (_openBlock(), _createElementBlock("li", { key: ni }, _toDisplayString(n), 1))
                          }), 128))
                        ]))
                      : _createCommentVNode("", true),
                    _createVNode(_component_VAlert, {
                      type: "warning",
                      variant: "tonal",
                      density: "compact"
                    }, {
                      default: _withCtx(() => [...(_cache[562] || (_cache[562] = [
                        _createTextVNode(" 考核下载会真下非免费种（下载量才算数），且执行期间不会被「3.4.0 下载异常自动清种」误杀。 ", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_VDivider),
                _createVNode(_component_VCardActions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VBtn, {
                      variant: "text",
                      disabled: !!examActing.value,
                      onClick: _cache[194] || (_cache[194] = $event => (examConfirm.value = null))
                    }, {
                      default: _withCtx(() => [...(_cache[563] || (_cache[563] = [
                        _createTextVNode("取消", -1)
                      ]))]),
                      _: 1
                    }, 8, ["disabled"]),
                    _createVNode(_component_VBtn, {
                      color: "primary",
                      variant: "flat",
                      loading: !!examActing.value,
                      onClick: examConfirmRun
                    }, {
                      default: _withCtx(() => [...(_cache[564] || (_cache[564] = [
                        _createTextVNode("确认创建 / 启用", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }))
          : _createCommentVNode("", true)
      ]),
      _: 1
    }, 8, ["model-value"])
  ], 2))
}
}

};
const MagicFlowWorkbench = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-f19cc2bf"]]);

export { MagicFlowWorkbench as M };
