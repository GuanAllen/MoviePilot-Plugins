import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, c as cloneTask, n as normalizeTask, a as normalizeDownloaderPrefs, b as normalizeDownloaderPaths, d as normalizeDefaults, t as taskStateMeta, r as runModeMeta, e as runStatusText, g as formatBytes, f as formatBonus, R as RUN_MODES, h as formatDateTime, i as formatDurationSeconds, u as unwrapResponse, j as normalizeSettings, k as formatDuration, l as normalizeIyuuSites } from './_plugin-vue_export-helper-CiM7cam3.js';

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
const _hoisted_12$1 = { class: "editor-section" };
const _hoisted_13$1 = { class: "editor-section" };
const _hoisted_14$1 = { class: "editor-section" };
const _hoisted_15$1 = { class: "editor-switches" };
const _hoisted_16$1 = { class: "editor-section" };
const _hoisted_17$1 = { class: "editor-section__head" };
const _hoisted_18$1 = { class: "editor-switches" };
const _hoisted_19$1 = { class: "editor-section" };
const _hoisted_20$1 = { class: "editor-switches" };
const _hoisted_21$1 = { class: "editor-section" };
const _hoisted_22$1 = { class: "editor-switches" };
const _hoisted_23$1 = { class: "editor-section" };
const _hoisted_24$1 = { class: "editor-section__head" };
const _hoisted_25$1 = { class: "editor-section" };
const _hoisted_26$1 = { class: "editor-section__head" };
const _hoisted_27$1 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_28$1 = { class: "editor-section" };
const _hoisted_29$1 = { class: "editor-section__head" };
const _hoisted_30$1 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_31$1 = { class: "editor-switches" };
const _hoisted_32$1 = { class: "editor-section" };
const _hoisted_33$1 = { class: "editor-section" };
const _hoisted_34$1 = { class: "magicflow-facts magicflow-facts--two" };
const _hoisted_35$1 = { class: "d-flex align-center mb-2" };
const _hoisted_36$1 = { class: "text-body-2 text-medium-emphasis" };

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
    "onUpdate:modelValue": _cache[80] || (_cache[80] = value => emit('update:modelValue', value))
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
                default: _withCtx$1(() => [...(_cache[81] || (_cache[81] = [
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
                    "onUpdate:modelValue": _cache[77] || (_cache[77] = $event => ((activeTab).value = $event)),
                    touch: false,
                    class: "magicflow-editor__window"
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_VWindowItem, { value: "base" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_1$1, [
                            _cache[82] || (_cache[82] = _createElementVNode$1("header", { class: "editor-section__head" }, [
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
                              _cache[84] || (_cache[84] = _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "任务身份"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "每个任务绑定一个站点和下载器")
                              ], -1)),
                              _createVNode$1(_component_VChip, {
                                size: "small",
                                color: "primary",
                                variant: "tonal"
                              }, {
                                default: _withCtx$1(() => [...(_cache[83] || (_cache[83] = [
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
                              _cache[85] || (_cache[85] = _createElementVNode$1("div", null, [
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
                                _cache[86] || (_cache[86] = _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "任务目标", -1)),
                                _createElementVNode$1("div", _hoisted_10$1, _toDisplayString$1(isBrush.value ? '站点上传量达到目标后，任务自动停止' : '站点魔力值达到目标后，任务自动停止'), 1)
                              ]),
                              _createVNode$1(_component_VChip, {
                                size: "small",
                                color: "primary",
                                variant: "tonal"
                              }, {
                                default: _withCtx$1(() => [...(_cache[87] || (_cache[87] = [
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
                            default: _withCtx$1(() => [...(_cache[88] || (_cache[88] = [
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
                            _cache[89] || (_cache[89] = _createElementVNode$1("header", { class: "editor-section__head" }, [
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
                            })
                          ]),
                          _createElementVNode$1("section", _hoisted_12$1, [
                            _cache[90] || (_cache[90] = _createElementVNode$1("header", { class: "editor-section__head" }, [
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
                                      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((localTask.value.upload_min_kbps) = $event)),
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
                                      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((localTask.value.upload_idle_minutes) = $event)),
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
                                      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((localTask.value.brush_grace_minutes) = $event)),
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
                          _createElementVNode$1("section", _hoisted_13$1, [
                            _cache[91] || (_cache[91] = _createElementVNode$1("header", { class: "editor-section__head" }, [
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
                                      "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((localTask.value.max_add_per_run) = $event)),
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
                                      "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((localTask.value.max_download_concurrent) = $event)),
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
                                      "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((localTask.value.top_n) = $event)),
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
                                      "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((localTask.value.browse_pages) = $event)),
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
                          _createElementVNode$1("section", _hoisted_14$1, [
                            _cache[92] || (_cache[92] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "复用与清理"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "优先复用本机已有资源；做种满天数 / 促销失效的种子清理")
                              ])
                            ], -1)),
                            _createElementVNode$1("div", _hoisted_15$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.refill_when_empty,
                                "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((localTask.value.refill_when_empty) = $event)),
                                label: "清理后主动补种",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.reuse_existing,
                                "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((localTask.value.reuse_existing) = $event)),
                                label: "复用本机已有资源（辅种）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.reuse_verify,
                                "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((localTask.value.reuse_verify) = $event)),
                                disabled: !localTask.value.reuse_existing,
                                label: "辅种前先校验（不匹配自动撤销）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue", "disabled"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.cleanup_no_progress,
                                "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((localTask.value.cleanup_no_progress) = $event)),
                                label: "清理无进度种子（停滞/出错且进度为 0）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.cleanup_slow_progress,
                                "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((localTask.value.cleanup_slow_progress) = $event)),
                                label: "清理下载过慢的种子（长期下不完腾名额）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.purge_unfree_incomplete,
                                "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((localTask.value.purge_unfree_incomplete) = $event)),
                                label: "清理「已不再免费且未下完」的种子",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.auto_resume_paused,
                                "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((localTask.value.auto_resume_paused) = $event)),
                                label: "自动恢复被暂停的已完成种子",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.delete_files,
                                "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((localTask.value.delete_files) = $event)),
                                label: "删种同时删除文件",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"])
                            ]),
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
                                          "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((localTask.value.no_progress_minutes) = $event)),
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
                                          "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((localTask.value.seen_cooldown_hours) = $event)),
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
                                          "onUpdate:modelValue": _cache[33] || (_cache[33] = $event => ((localTask.value.slow_progress_grace_minutes) = $event)),
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
                                          "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((localTask.value.slow_progress_max_hours) = $event)),
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
                              _createElementVNode$1("section", _hoisted_16$1, [
                                _createElementVNode$1("header", _hoisted_17$1, [
                                  _cache[94] || (_cache[94] = _createElementVNode$1("div", null, [
                                    _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "魔力门槛（留空 = 自动）"),
                                    _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "留空由公式与实时数据自动推算，手填即覆盖")
                                  ], -1)),
                                  _createVNode$1(_component_VChip, {
                                    size: "small",
                                    color: "primary",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx$1(() => [...(_cache[93] || (_cache[93] = [
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
                                          "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((localTask.value.min_bonus_per_hour) = $event)),
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
                                          "onUpdate:modelValue": _cache[36] || (_cache[36] = $event => ((localTask.value.disk_size_gb) = $event)),
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
                                          "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((localTask.value.max_keep_torrents) = $event)),
                                          modelModifiers: { number: true },
                                          type: "number",
                                          min: "1",
                                          label: "最多保留种子数",
                                          placeholder: "留空 = 保种体积 ÷ 平均种子大小",
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
                                          "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((localTask.value.max_add_per_run) = $event)),
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
                                          "onUpdate:modelValue": _cache[39] || (_cache[39] = $event => ((localTask.value.max_download_concurrent) = $event)),
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
                                          "onUpdate:modelValue": _cache[40] || (_cache[40] = $event => ((localTask.value.top_n) = $event)),
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
                                          "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((localTask.value.browse_pages) = $event)),
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
                                          "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((localTask.value.bonus_protect_threshold) = $event)),
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
                                          "onUpdate:modelValue": _cache[43] || (_cache[43] = $event => ((localTask.value.min_bonus_to_keep) = $event)),
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
                                _createElementVNode$1("div", _hoisted_18$1, [
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.refill_when_empty,
                                    "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((localTask.value.refill_when_empty) = $event)),
                                    label: "清理后主动补种",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.reuse_existing,
                                    "onUpdate:modelValue": _cache[45] || (_cache[45] = $event => ((localTask.value.reuse_existing) = $event)),
                                    label: "复用本机已有资源（辅种）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.reuse_verify,
                                    "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((localTask.value.reuse_verify) = $event)),
                                    disabled: !localTask.value.reuse_existing,
                                    label: "辅种前先校验（不匹配自动撤销）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue", "disabled"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.cleanup_no_progress,
                                    "onUpdate:modelValue": _cache[47] || (_cache[47] = $event => ((localTask.value.cleanup_no_progress) = $event)),
                                    label: "每次运行清理无进度种子（停滞/出错且进度为 0）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.cleanup_slow_progress,
                                    "onUpdate:modelValue": _cache[48] || (_cache[48] = $event => ((localTask.value.cleanup_slow_progress) = $event)),
                                    label: "清理下载过慢的种子（速度÷体积算 ETA，长期下不完的腾名额）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.purge_unfree_incomplete,
                                    "onUpdate:modelValue": _cache[49] || (_cache[49] = $event => ((localTask.value.purge_unfree_incomplete) = $event)),
                                    label: "检查时清理「已不再免费且未下完」的种子（回站点核对促销）",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"]),
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.auto_resume_paused,
                                    "onUpdate:modelValue": _cache[50] || (_cache[50] = $event => ((localTask.value.auto_resume_paused) = $event)),
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
                                          "onUpdate:modelValue": _cache[51] || (_cache[51] = $event => ((localTask.value.ti_source) = $event)),
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
                                              "onUpdate:modelValue": _cache[52] || (_cache[52] = $event => ((localTask.value.no_progress_minutes) = $event)),
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
                                              "onUpdate:modelValue": _cache[53] || (_cache[53] = $event => ((localTask.value.seen_cooldown_hours) = $event)),
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
                                              "onUpdate:modelValue": _cache[54] || (_cache[54] = $event => ((localTask.value.slow_progress_grace_minutes) = $event)),
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
                                              "onUpdate:modelValue": _cache[55] || (_cache[55] = $event => ((localTask.value.slow_progress_max_hours) = $event)),
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
                              _createElementVNode$1("section", _hoisted_19$1, [
                                _cache[95] || (_cache[95] = _createElementVNode$1("header", { class: "editor-section__head" }, [
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
                                          "onUpdate:modelValue": _cache[56] || (_cache[56] = $event => ((localTask.value.min_seed_time) = $event)),
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
                                          "onUpdate:modelValue": _cache[57] || (_cache[57] = $event => ((localTask.value.min_ratio) = $event)),
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
                                _createElementVNode$1("div", _hoisted_20$1, [
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.delete_files,
                                    "onUpdate:modelValue": _cache[58] || (_cache[58] = $event => ((localTask.value.delete_files) = $event)),
                                    label: "删种同时删除文件",
                                    color: "primary",
                                    "hide-details": "",
                                    inset: ""
                                  }, null, 8, ["modelValue"])
                                ])
                              ]),
                              _createElementVNode$1("section", _hoisted_21$1, [
                                _cache[96] || (_cache[96] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                                  _createElementVNode$1("div", null, [
                                    _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "完美种保护"),
                                    _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "优质老种（非零魔 · 做种人数少 · 挂得够老）永久保留，不参与任何清理——魔力靠「养」，越老越肥")
                                  ])
                                ], -1)),
                                _createElementVNode$1("div", _hoisted_22$1, [
                                  _createVNode$1(_component_VSwitch, {
                                    modelValue: localTask.value.protect_perfect,
                                    "onUpdate:modelValue": _cache[59] || (_cache[59] = $event => ((localTask.value.protect_perfect) = $event)),
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
                                              "onUpdate:modelValue": _cache[60] || (_cache[60] = $event => ((localTask.value.perfect_max_seeders) = $event)),
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
                                              "onUpdate:modelValue": _cache[61] || (_cache[61] = $event => ((localTask.value.perfect_min_weeks) = $event)),
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
                              _createElementVNode$1("section", _hoisted_23$1, [
                                _createElementVNode$1("header", _hoisted_24$1, [
                                  _cache[98] || (_cache[98] = _createElementVNode$1("div", null, [
                                    _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "魔力公式参数"),
                                    _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, " 留空使用站点预设 / NexusPHP 标准式（T0=5，N0=7，B0=100，L=300） ")
                                  ], -1)),
                                  _createVNode$1(_component_VChip, {
                                    size: "small",
                                    color: "primary",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx$1(() => [...(_cache[97] || (_cache[97] = [
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
                                          "onUpdate:modelValue": _cache[62] || (_cache[62] = $event => ((localTask.value.bonus_t0) = $event)),
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
                                          "onUpdate:modelValue": _cache[63] || (_cache[63] = $event => ((localTask.value.bonus_n0) = $event)),
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
                                          "onUpdate:modelValue": _cache[64] || (_cache[64] = $event => ((localTask.value.bonus_b0) = $event)),
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
                                          "onUpdate:modelValue": _cache[65] || (_cache[65] = $event => ((localTask.value.bonus_l) = $event)),
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
                                          "onUpdate:modelValue": _cache[66] || (_cache[66] = $event => ((localTask.value.bonus_zero_weight) = $event)),
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
                          _createElementVNode$1("section", _hoisted_25$1, [
                            _createElementVNode$1("header", _hoisted_26$1, [
                              _createElementVNode$1("div", null, [
                                _cache[99] || (_cache[99] = _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "来源与促销", -1)),
                                _createElementVNode$1("div", _hoisted_27$1, _toDisplayString$1(isBrush.value ? '刷流只看站点最新页（免费热种在最新页），不做游标深翻' : '沿用站点列表页或 RSS 获取链路'), 1)
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
                                          "onUpdate:modelValue": _cache[67] || (_cache[67] = $event => ((localTask.value.freeleech) = $event)),
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
                                      "onUpdate:modelValue": _cache[68] || (_cache[68] = $event => ((localTask.value.hr) = $event)),
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
                          _createElementVNode$1("section", _hoisted_28$1, [
                            _createElementVNode$1("header", _hoisted_29$1, [
                              _createElementVNode$1("div", null, [
                                _cache[100] || (_cache[100] = _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "候选过滤", -1)),
                                _createElementVNode$1("div", _hoisted_30$1, _toDisplayString$1(isBrush.value ? '刷流默认不限人数 / 体积 / 年龄（留空即为不限），如需收敛再填；范围支持单值或「最小值-最大值」' : '范围字段支持单值或「最小值-最大值」'), 1)
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
                                      "onUpdate:modelValue": _cache[69] || (_cache[69] = $event => ((localTask.value.size) = $event)),
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
                                      "onUpdate:modelValue": _cache[70] || (_cache[70] = $event => ((localTask.value.seeder) = $event)),
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
                                      "onUpdate:modelValue": _cache[71] || (_cache[71] = $event => ((localTask.value.pubtime) = $event)),
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
                                      "onUpdate:modelValue": _cache[72] || (_cache[72] = $event => ((localTask.value.include) = $event)),
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
                                      "onUpdate:modelValue": _cache[73] || (_cache[73] = $event => ((localTask.value.exclude) = $event)),
                                      label: "排除规则",
                                      placeholder: "支持正则表达式"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createElementVNode$1("div", _hoisted_31$1, [
                              (!isBrush.value)
                                ? (_openBlock$1(), _createBlock$1(_component_VSwitch, {
                                    key: 0,
                                    modelValue: localTask.value.exclude_zero_bonus,
                                    "onUpdate:modelValue": _cache[74] || (_cache[74] = $event => ((localTask.value.exclude_zero_bonus) = $event)),
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
                          _createElementVNode$1("section", _hoisted_32$1, [
                            _cache[101] || (_cache[101] = _createElementVNode$1("header", { class: "editor-section__head" }, [
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
                                      "onUpdate:modelValue": _cache[75] || (_cache[75] = $event => ((localTask.value.up_speed) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "上传限速（KB/s）"
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
                                      "onUpdate:modelValue": _cache[76] || (_cache[76] = $event => ((localTask.value.dl_speed) = $event)),
                                      modelModifiers: { number: true },
                                      type: "number",
                                      min: "1",
                                      label: "下载限速（KB/s）"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _createElementVNode$1("section", _hoisted_33$1, [
                            _cache[107] || (_cache[107] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "生效预览"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "保存后立即写入调度，无需重启插件")
                              ])
                            ], -1)),
                            _createElementVNode$1("dl", _hoisted_34$1, [
                              _createElementVNode$1("div", null, [
                                _cache[102] || (_cache[102] = _createElementVNode$1("dt", null, "站点", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(siteName.value), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[103] || (_cache[103] = _createElementVNode$1("dt", null, "下载器", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(localTask.value.downloader || '未选择'), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[104] || (_cache[104] = _createElementVNode$1("dt", null, "调度", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(scheduleText.value), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[105] || (_cache[105] = _createElementVNode$1("dt", null, "开启时段", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(localTask.value.active_time_range || '全天'), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[106] || (_cache[106] = _createElementVNode$1("dt", null, "任务目标", -1)),
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
        "onUpdate:modelValue": _cache[79] || (_cache[79] = $event => ((goalWarning).value = $event)),
        "max-width": "30rem"
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_VCard, { class: "pa-2" }, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_VCardText, null, {
                default: _withCtx$1(() => [
                  _createElementVNode$1("div", _hoisted_35$1, [
                    _createVNode$1(_component_VIcon, {
                      icon: "mdi-flag-alert",
                      color: "warning",
                      class: "mr-2"
                    }),
                    _cache[108] || (_cache[108] = _createElementVNode$1("span", { class: "text-subtitle-1 font-weight-medium" }, "尚未设置任务目标", -1))
                  ]),
                  _createElementVNode$1("div", _hoisted_36$1, [
                    _cache[109] || (_cache[109] = _createTextVNode$1(" 建议为每个任务设置目标，达到后会自动停止： ", -1)),
                    _createElementVNode$1("strong", null, _toDisplayString$1(isBrush.value ? '站点上传量（GB）' : '站点魔力值'), 1),
                    _cache[110] || (_cache[110] = _createTextVNode$1("。 ", -1))
                  ])
                ]),
                _: 1
              }),
              _createVNode$1(_component_VCardActions, null, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_VSpacer),
                  _createVNode$1(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[78] || (_cache[78] = $event => (goalWarning.value = false))
                  }, {
                    default: _withCtx$1(() => [...(_cache[111] || (_cache[111] = [
                      _createTextVNode$1("返回填写", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode$1(_component_VBtn, {
                    color: "warning",
                    variant: "flat",
                    onClick: confirmSaveWithoutGoal
                  }, {
                    default: _withCtx$1(() => [...(_cache[112] || (_cache[112] = [
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
const TaskEditorDialog = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-e51110bc"]]);

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createBlock:_createBlock,toDisplayString:_toDisplayString,normalizeClass:_normalizeClass,mergeProps:_mergeProps,renderList:_renderList,Fragment:_Fragment,withCtx:_withCtx,createTextVNode:_createTextVNode,unref:_unref,normalizeStyle:_normalizeStyle,withModifiers:_withModifiers} = await importShared('vue');


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
const _hoisted_19 = { class: "magicflow-layout" };
const _hoisted_20 = { class: "magicflow-task-rail__head" };
const _hoisted_21 = { class: "magicflow-task-list" };
const _hoisted_22 = ["aria-pressed", "onClick"];
const _hoisted_23 = { class: "magicflow-task-item__title" };
const _hoisted_24 = { class: "magicflow-task-item__meta" };
const _hoisted_25 = { key: 0 };
const _hoisted_26 = { key: 1 };
const _hoisted_27 = {
  key: 0,
  class: "magicflow-workspace"
};
const _hoisted_28 = { class: "magicflow-task-head" };
const _hoisted_29 = { class: "magicflow-task-head__identity" };
const _hoisted_30 = ["src"];
const _hoisted_31 = { class: "magicflow-task-head__body" };
const _hoisted_32 = { class: "magicflow-task-head__title" };
const _hoisted_33 = { class: "magicflow-task-head__actions" };
const _hoisted_34 = {
  class: "magicflow-tabs",
  role: "tablist"
};
const _hoisted_35 = ["aria-selected", "onClick"];
const _hoisted_36 = { class: "magicflow-stat-grid" };
const _hoisted_37 = { class: "magicflow-overview-grid" };
const _hoisted_38 = { class: "magicflow-panel__head" };
const _hoisted_39 = { class: "magicflow-facts" };
const _hoisted_40 = { class: "magicflow-panel__head" };
const _hoisted_41 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_42 = { class: "magicflow-facts" };
const _hoisted_43 = { class: "magicflow-panel__head" };
const _hoisted_44 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_45 = { class: "magicflow-run-summary" };
const _hoisted_46 = { class: "magicflow-panel__head" };
const _hoisted_47 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_48 = { class: "magicflow-flow__chain" };
const _hoisted_49 = { class: "magicflow-flow__dot" };
const _hoisted_50 = { class: "magicflow-flow__label" };
const _hoisted_51 = { class: "magicflow-panel__head" };
const _hoisted_52 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_53 = {
  key: 0,
  class: "magicflow-reasons"
};
const _hoisted_54 = { class: "magicflow-reason__track" };
const _hoisted_55 = {
  key: 1,
  class: "magicflow-table-empty"
};
const _hoisted_56 = { class: "magicflow-panel__head" };
const _hoisted_57 = { class: "magicflow-events" };
const _hoisted_58 = {
  key: 0,
  class: "text-error"
};
const _hoisted_59 = ["onClick"];
const _hoisted_60 = {
  key: 2,
  class: "magicflow-events__detail"
};
const _hoisted_61 = { class: "magicflow-events__detail-line" };
const _hoisted_62 = {
  key: 0,
  class: "magicflow-events__detail-src"
};
const _hoisted_63 = ["title"];
const _hoisted_64 = { class: "magicflow-events__detail-sub" };
const _hoisted_65 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_66 = { class: "magicflow-diagnostic-head" };
const _hoisted_67 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_68 = { class: "magicflow-torrent-filters" };
const _hoisted_69 = { class: "magicflow-panel__head" };
const _hoisted_70 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_71 = { class: "magicflow-pipeline" };
const _hoisted_72 = { class: "magicflow-pipeline__index" };
const _hoisted_73 = { key: 0 };
const _hoisted_74 = { class: "magicflow-panel__head" };
const _hoisted_75 = { class: "magicflow-torrent-filters" };
const _hoisted_76 = {
  key: 0,
  class: "magicflow-bulk-bar"
};
const _hoisted_77 = { class: "magicflow-bulk-bar__count" };
const _hoisted_78 = { class: "torrent-title-cell" };
const _hoisted_79 = { class: "magicflow-mobile-torrents" };
const _hoisted_80 = ["onClick"];
const _hoisted_81 = { class: "magicflow-mobile-torrent__head" };
const _hoisted_82 = { class: "magicflow-mobile-torrent__title" };
const _hoisted_83 = { class: "magicflow-mobile-torrent__grid" };
const _hoisted_84 = { class: "magicflow-mobile-torrent__actions" };
const _hoisted_85 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_86 = { class: "magicflow-config-grid" };
const _hoisted_87 = { class: "magicflow-panel__head" };
const _hoisted_88 = { class: "text-subtitle-1 font-weight-medium" };
const _hoisted_89 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_90 = { class: "magicflow-facts magicflow-facts--two" };
const _hoisted_91 = { class: "magicflow-config-actions" };
const _hoisted_92 = { class: "magicflow-settings-dialog__head" };
const _hoisted_93 = { class: "magicflow-settings-dialog__body" };
const _hoisted_94 = {
  key: 0,
  class: "magicflow-settings-form"
};
const _hoisted_95 = { class: "magicflow-settings-grid" };
const _hoisted_96 = {
  key: 1,
  class: "magicflow-settings-form"
};
const _hoisted_97 = { class: "magicflow-settings-grid" };
const _hoisted_98 = {
  key: 2,
  class: "magicflow-settings-form"
};
const _hoisted_99 = {
  key: 3,
  class: "magicflow-settings-form"
};
const _hoisted_100 = { class: "magicflow-iyuu-token" };
const _hoisted_101 = { class: "magicflow-iyuu-sites" };
const _hoisted_102 = { class: "magicflow-iyuu-sites__head" };
const _hoisted_103 = {
  key: 0,
  class: "magicflow-settings-hint"
};
const _hoisted_104 = {
  key: 1,
  class: "magicflow-settings-hint"
};
const _hoisted_105 = { class: "magicflow-iyuu-row__head" };
const _hoisted_106 = { class: "magicflow-iyuu-row__name" };
const _hoisted_107 = { class: "magicflow-iyuu-row__fields" };
const _hoisted_108 = {
  key: 4,
  class: "magicflow-settings-form"
};
const _hoisted_109 = { class: "magicflow-settings-grid" };
const _hoisted_110 = { class: "magicflow-settings-switches" };
const _hoisted_111 = { class: "magicflow-settings-dialog__footer" };
const _hoisted_112 = { class: "magicflow-torrent-dialog__head" };
const _hoisted_113 = { class: "magicflow-torrent-dialog__tags" };
const _hoisted_114 = { class: "magicflow-torrent-dialog__title" };
const _hoisted_115 = { class: "magicflow-torrent-dialog__progress" };
const _hoisted_116 = { class: "magicflow-torrent-dialog__pct" };
const _hoisted_117 = { class: "magicflow-torrent-dialog__grid" };
const _hoisted_118 = { class: "magicflow-torrent-dialog__hash" };
const _hoisted_119 = { class: "text-medium-emphasis" };
const _hoisted_120 = { class: "text-medium-emphasis" };

const {computed,inject,onMounted,onUnmounted,ref,watch} = await importShared('vue');


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
const selectedHashes = computed(() =>
  (selectedRows.value || []).map(row => row?.hash).filter(Boolean),
);
const settingsDialog = ref(false);
const settingsTab = ref('general');
const settingsDraft = ref({
  enabled: false,
  show_sidebar_nav: true,
  debug_log: false,
  compact_mode: false,
  journal_keep: 200,
  request_interval: 0,
  bonus_upload_limit_kbps: 200,
  brush_upload_limit_kbps: 10240,
  iyuu_token: '',
  iyuu_sites: {},
});
const downloaderPrefsDraft = ref(normalizeDownloaderPrefs({}));
const downloaderPrefsRecommended = ref(null);
const downloaderPrefsLoading = ref(false);
const downloaderPrefsRaw = ref(null);
const downloaderPathsDraft = ref(normalizeDownloaderPaths({}));
const defaultsDraft = ref(normalizeDefaults({}));
const defaultsLoading = ref(false);
// IYUU 云端辅种（可选）：站点表按 MoviePilot 已配置站点生成
const iyuuSites = ref([]);
const iyuuLoading = ref(false);
const iyuuTesting = ref(false);
const iyuuStatus = ref(null);
const iyuuShowMore = ref({});
let refreshTimer;
let phaseTimer;

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
  const cur = Number(t.goal_current || 0);
  const tgt = Number(t.goal_target || 0);
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

const KIND_TEXT = { run: '执行', selection: '选种加入', deletion: '删种清理', protection: '手动保留', unprotection: '取消保留', reuse: '存量复用', pause: '暂停种子', resume: '恢复运行', recheck: '强制校验', goal: '达标停止', state: '运行状态', tag: '标签变更' };
const STATE_TEXT = { submitting: '提交中', accepted: '已受理', completed: '已完成', failed: '失败' };
const KIND_ICON = {
  run: 'mdi-play-circle-outline',
  selection: 'mdi-download-outline',
  deletion: 'mdi-delete-outline',
  reuse: 'mdi-content-duplicate',
  protection: 'mdi-shield-check-outline',
  unprotection: 'mdi-shield-off-outline',
  pause: 'mdi-pause-circle-outline',
  resume: 'mdi-play-circle-outline',
  recheck: 'mdi-sync',
  goal: 'mdi-flag-checkered',
  state: 'mdi-power',
  tag: 'mdi-tag-outline',
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
      iyuu_token: status.value.iyuu_token,
      iyuu_sites: status.value.iyuu_sites,
    });
    statusLoaded.value = true;
    if (!selectedTaskId.value && tasks.value.length) {
      selectTask(tasks.value[0].id);
    } else if (selectedTaskId.value && !tasks.value.some(item => item.id === selectedTaskId.value)) {
      selectedTaskId.value = '';
    }
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    loading.value = false;
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

// 加载操作记录。
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

// 确认删除当前任务。
async function confirmDeleteTask() {
  if (!selectedTask.value) return
  saving.value = true;
  try {
    unwrapResponse(await props.api.delete(`${pluginBase.value}/tasks/${selectedTask.value.id}`));
    deleteDialog.value = false;
    selectedTaskId.value = '';
    notify('任务已删除');
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
async function openSettings(tab = 'general') {
  settingsTab.value = tab;
  settingsDialog.value = true;
  await Promise.all([loadDownloaderPrefs(), loadDefaults(), loadIyuuSites()]);
}

// 加载 IYUU 站点表（按 MoviePilot 已配置站点生成）。
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

// 保存下载器全局参数。
async function saveDownloaderPrefs() {
  saving.value = true;
  try {
    const data = unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/prefs`, normalizeDownloaderPrefs(downloaderPrefsDraft.value)),
    );
    if (data && data.available) {
      downloaderPrefsDraft.value = normalizeDownloaderPrefs(data);
      downloaderPrefsRaw.value = data.raw || null;
    }
    notify('下载器参数已保存');
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
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
  if (tab === 'downloader') return saveDownloaderPrefs()
  if (tab === 'paths') return savePathsTab()
  if (tab === 'template') return saveDefaults()
  if (tab === 'iyuu') return saveIyuu()
  return saveSettings()
}

// 保存「下载目录」标签：qBittorrent 全局路径 + 任务保存目录（默认模板）。
async function savePathsTab() {
  saving.value = true;
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/downloader/paths`, normalizeDownloaderPaths(downloaderPathsDraft.value)),
    );
    unwrapResponse(await props.api.post(`${pluginBase.value}/defaults`, normalizeDefaults(defaultsDraft.value)));
    notify('下载目录已保存');
    await loadStatus();
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
}

// 保存全局设置。
async function saveSettings() {
  saving.value = true;
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
  },
  { immediate: true },
);

onMounted(() => {
  loadStatus();
  refreshTimer = window.setInterval(loadStatus, 30000);
  // 运行诊断页每秒多刷新一次任务阶段，驱动流程链转圈
  phaseTimer = window.setInterval(() => {
    if (activeTab.value === 'diagnostics' && selectedTaskId.value) loadDetail(selectedTaskId.value);
  }, 1500);
});

onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer);
  if (phaseTimer) window.clearInterval(phaseTimer);
});

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VListItem = _resolveComponent("VListItem");
  const _component_VList = _resolveComponent("VList");
  const _component_VMenu = _resolveComponent("VMenu");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VBtn = _resolveComponent("VBtn");
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
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VDialog = _resolveComponent("VDialog");
  const _component_VCardActions = _resolveComponent("VCardActions");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VCardText = _resolveComponent("VCardText");

  return (_openBlock(), _createElementBlock("div", {
    class: _normalizeClass(["magicflow-page", { 'magicflow-page--compact': __props.compact || status.value.compact_mode }])
  }, [
    _createElementVNode("header", _hoisted_1, [
      _createElementVNode("div", _hoisted_2, [
        _createElementVNode("span", _hoisted_3, [
          _createVNode(_component_VIcon, {
            icon: "mdi-magnet",
            size: "20"
          })
        ]),
        _cache[80] || (_cache[80] = _createElementVNode("div", null, [
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
                    _cache[81] || (_cache[81] = _createElementVNode("span", { class: "magicflow-task-switch__k" }, "当前任务", -1)),
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
                        subtitle: task.site_name,
                        active: task.id === selectedTaskId.value,
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
              size: "small",
              variant: "tonal"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(summary.value.enabled_tasks || 0) + " / " + _toDisplayString(summary.value.total_tasks) + " 启用 ", 1)
              ]),
              _: 1
            }))
          : _createCommentVNode("", true),
        _createVNode(_component_VBtn, {
          class: "magicflow-header-create",
          color: "primary",
          variant: "flat",
          "prepend-icon": "mdi-plus",
          onClick: openCreateTask
        }, {
          default: _withCtx(() => [...(_cache[82] || (_cache[82] = [
            _createTextVNode(" 新建任务 ", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VBtn, {
          class: "magicflow-settings-btn",
          icon: "mdi-tune-variant",
          variant: "text",
          "aria-label": "插件设置",
          onClick: _cache[0] || (_cache[0] = $event => (openSettings()))
        }),
        (__props.showClose)
          ? (_openBlock(), _createBlock(_component_VBtn, {
              key: 2,
              icon: "mdi-close",
              variant: "text",
              "aria-label": "关闭",
              onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
            }))
          : _createCommentVNode("", true)
      ])
    ]),
    (error.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 0,
          type: "error",
          variant: "tonal",
          closable: "",
          "onClick:close": _cache[2] || (_cache[2] = $event => (error.value = ''))
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
          default: _withCtx(() => [...(_cache[83] || (_cache[83] = [
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
            _cache[85] || (_cache[85] = _createElementVNode("div", { class: "text-h6" }, "还没有任务", -1)),
            _cache[86] || (_cache[86] = _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "创建任务后可按站点魔力公式养护做种，或按上传产出刷流保种", -1)),
            _createVNode(_component_VBtn, {
              color: "primary",
              variant: "flat",
              "prepend-icon": "mdi-plus",
              onClick: openCreateTask
            }, {
              default: _withCtx(() => [...(_cache[84] || (_cache[84] = [
                _createTextVNode("创建第一个任务", -1)
              ]))]),
              _: 1
            })
          ]))
        : (_openBlock(), _createElementBlock(_Fragment, { key: 4 }, [
            _createElementVNode("div", _hoisted_12, [
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
                          _cache[87] || (_cache[87] = _createElementVNode("span", { class: "magicflow-task-switch__k" }, "当前任务", -1)),
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
                              subtitle: task.site_name,
                              active: task.id === selectedTaskId.value,
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
                    _cache[88] || (_cache[88] = _createElementVNode("span", null, "当前任务", -1)),
                    _createElementVNode("strong", null, _toDisplayString(selectedTask.value?.name || '—'), 1)
                  ])),
              _createVNode(_component_VBtn, {
                class: "magicflow-mobile-add",
                variant: "tonal",
                color: "primary",
                "prepend-icon": "mdi-plus",
                onClick: openCreateTask
              }, {
                default: _withCtx(() => [...(_cache[89] || (_cache[89] = [
                  _createTextVNode(" 新建 ", -1)
                ]))]),
                _: 1
              })
            ]),
            _createElementVNode("div", _hoisted_19, [
              _createVNode(_component_VSheet, {
                tag: "aside",
                class: "magicflow-task-rail app-surface-static"
              }, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_20, [
                    _cache[90] || (_cache[90] = _createElementVNode("span", { class: "text-subtitle-2" }, "任务", -1)),
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
                  _createElementVNode("div", _hoisted_21, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tasks.value, (task) => {
                      return (_openBlock(), _createElementBlock("button", {
                        key: task.id,
                        type: "button",
                        class: _normalizeClass(["magicflow-task-item", { 'magicflow-task-item--selected': task.id === selectedTaskId.value }]),
                        "aria-pressed": task.id === selectedTaskId.value,
                        onClick: $event => (selectTask(task.id))
                      }, [
                        _createElementVNode("span", _hoisted_23, [
                          _createElementVNode("strong", null, _toDisplayString(task.name), 1),
                          _createElementVNode("span", {
                            class: _normalizeClass(["magicflow-status-dot", `magicflow-status-dot--${taskBadge(task).color}`])
                          }, null, 2)
                        ]),
                        _createElementVNode("span", null, _toDisplayString(task.site_name) + " · " + _toDisplayString(task.downloader), 1),
                        _createElementVNode("span", _hoisted_24, [
                          _createElementVNode("span", null, _toDisplayString(task.seeding_count || 0) + " 个种子", 1),
                          (task.task_type === 'brush')
                            ? (_openBlock(), _createElementBlock("span", _hoisted_25, _toDisplayString(_unref(formatBytes)(task.task_uploaded || 0)) + " 上传", 1))
                            : (_openBlock(), _createElementBlock("span", _hoisted_26, _toDisplayString(task.site_bonus_ok ? _unref(formatBonus)(task.site_bonus_per_hour) : '—'), 1))
                        ])
                      ], 10, _hoisted_22))
                    }), 128))
                  ]),
                  _createVNode(_component_VBtn, {
                    class: "magicflow-create-task",
                    block: "",
                    variant: "tonal",
                    "prepend-icon": "mdi-plus",
                    onClick: openCreateTask
                  }, {
                    default: _withCtx(() => [...(_cache[91] || (_cache[91] = [
                      _createTextVNode(" 新建任务 ", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              (selectedTask.value)
                ? (_openBlock(), _createElementBlock("main", _hoisted_27, [
                    _createElementVNode("section", _hoisted_28, [
                      _createElementVNode("div", _hoisted_29, [
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
                                }, null, 8, _hoisted_30))
                              : (_openBlock(), _createBlock(_component_VIcon, {
                                  key: 1,
                                  icon: "mdi-web"
                                }))
                          ]),
                          _: 1
                        }),
                        _createElementVNode("div", _hoisted_31, [
                          _createElementVNode("div", _hoisted_32, [
                            _createElementVNode("h2", null, _toDisplayString(selectedTask.value.name), 1),
                            _createVNode(_component_VChip, {
                              size: "small",
                              variant: "tonal",
                              color: selectedTask.value.task_type === 'brush' ? 'info' : 'primary',
                              "prepend-icon": selectedTask.value.task_type === 'brush' ? 'mdi-upload-network-outline' : 'mdi-star-four-points-outline'
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(selectedTask.value.task_type === 'brush' ? '刷流' : '刷魔力'), 1)
                              ]),
                              _: 1
                            }, 8, ["color", "prepend-icon"]),
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
                      _createElementVNode("div", _hoisted_33, [
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
                              onClick: _cache[3] || (_cache[3] = $event => (reloadSelected()))
                            }), null, 16)
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VMenu, { location: "bottom end" }, {
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
                        }),
                        _createVNode(_component_VTooltip, { text: "编辑任务" }, {
                          activator: _withCtx(({ props: tipProps }) => [
                            _createVNode(_component_VBtn, _mergeProps(tipProps, {
                              icon: "mdi-pencil-outline",
                              variant: "text",
                              onClick: openEditTask
                            }), null, 16)
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VTooltip, { text: "删除任务" }, {
                          activator: _withCtx(({ props: tipProps }) => [
                            _createVNode(_component_VBtn, _mergeProps(tipProps, {
                              icon: "mdi-delete-outline",
                              variant: "text",
                              color: "error",
                              onClick: _cache[4] || (_cache[4] = $event => (deleteDialog.value = true))
                            }), null, 16)
                          ]),
                          _: 1
                        })
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_34, [
                      (_openBlock(), _createElementBlock(_Fragment, null, _renderList(MF_TABS, (tab) => {
                        return _createElementVNode("button", {
                          key: tab.value,
                          type: "button",
                          role: "tab",
                          class: _normalizeClass(["magicflow-tab", { 'is-active': activeTab.value === tab.value }]),
                          "aria-selected": activeTab.value === tab.value,
                          onClick: $event => (activeTab.value = tab.value)
                        }, _toDisplayString(tab.label), 11, _hoisted_35)
                      }), 64))
                    ]),
                    _createVNode(_component_VWindow, {
                      modelValue: activeTab.value,
                      "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((activeTab).value = $event)),
                      touch: false,
                      class: "magicflow-window"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VWindowItem, { value: "overview" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_36, [
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
                                        _createElementVNode("strong", null, _toDisplayString(siteUser.value.ok ? _unref(formatBytes)(siteUser.value.upload || 0) : '—'), 1),
                                        _createElementVNode("span", null, "站点上传量 · 账号真实值" + _toDisplayString(siteUser.value.ok ? ` · 下载 ${_unref(formatBytes)(siteUser.value.download || 0)}` : ''), 1)
                                      ]),
                                      _: 1
                                    })
                                  ], 64))
                                : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                    _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("strong", null, _toDisplayString(selectedTask.value.site_bonus_ok ? _unref(formatBonus)(selectedTask.value.site_bonus_per_hour) : '—'), 1),
                                        _cache[92] || (_cache[92] = _createElementVNode("span", null, "站点上报时魔 · 站点实时值", -1))
                                      ]),
                                      _: 1
                                    }),
                                    _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("strong", null, _toDisplayString(Number(selectedTask.value.site_current_bonus || 0).toFixed(2)), 1),
                                        _cache[93] || (_cache[93] = _createElementVNode("span", null, "站点当前魔力 · 该站点实时存量", -1))
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
                            _createElementVNode("div", _hoisted_37, [
                              _createVNode(_component_VSheet, {
                                tag: "section",
                                class: "magicflow-panel app-surface-static"
                              }, {
                                default: _withCtx(() => [
                                  _createElementVNode("header", _hoisted_38, [
                                    _cache[94] || (_cache[94] = _createElementVNode("div", null, [
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
                                  _createElementVNode("dl", _hoisted_39, [
                                    _createElementVNode("div", null, [
                                      _cache[95] || (_cache[95] = _createElementVNode("dt", null, "任务目标", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(goalFactText.value), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[96] || (_cache[96] = _createElementVNode("dt", null, "选种周期", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cron_expression || `每 ${taskConfig.value.brush_interval} 分钟`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[97] || (_cache[97] = _createElementVNode("dt", null, "检查周期", -1)),
                                      _createElementVNode("dd", null, "每 " + _toDisplayString(taskConfig.value.check_interval) + " 分钟", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[98] || (_cache[98] = _createElementVNode("dt", null, "开启时段", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.active_time_range || '全天'), 1)
                                    ]),
                                    (taskIsBrush.value)
                                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                          _createElementVNode("div", null, [
                                            _cache[99] || (_cache[99] = _createElementVNode("dt", null, "保种天数", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(brushSeedDays.value > 0 ? `做种满 ${brushSeedDays.value} 天清理` : '不按天数（按无上传）'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[100] || (_cache[100] = _createElementVNode("dt", null, "最小下载人数", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.brush_min_leechers ?? 1) + " 人", 1)
                                          ])
                                        ], 64))
                                      : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                          _createElementVNode("div", null, [
                                            _cache[101] || (_cache[101] = _createElementVNode("dt", null, "最低魔力", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.value.min_bonus_per_hour).toFixed(2)} /h`), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[102] || (_cache[102] = _createElementVNode("dt", null, "最多保留", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_keep_torrents == null ? (taskConfig.value.disk_size_gb ? `按 ${taskConfig.value.disk_size_gb}GB 自动` : '不限') : `${taskConfig.value.max_keep_torrents} 个`), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[103] || (_cache[103] = _createElementVNode("dt", null, "保护阈值", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.value.bonus_protect_threshold).toFixed(0)), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[104] || (_cache[104] = _createElementVNode("dt", null, "完美种保护", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.protect_perfect === false ? '关闭' : `开启（≤${taskConfig.value.perfect_max_seeders ?? 3}人 · ≥${taskConfig.value.perfect_min_weeks ?? 4}周）`), 1)
                                          ])
                                        ], 64)),
                                    _createElementVNode("div", null, [
                                      _cache[105] || (_cache[105] = _createElementVNode("dt", null, "自动补种", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.refill_when_empty ? '开启' : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[106] || (_cache[106] = _createElementVNode("dt", null, "存量复用", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.reuse_existing ? '开启' : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[107] || (_cache[107] = _createElementVNode("dt", null, "无进度清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_no_progress ? `开启（${taskConfig.value.no_progress_minutes ?? 30} 分钟）` : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[108] || (_cache[108] = _createElementVNode("dt", null, "慢速清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.value.slow_progress_max_hours ?? 48}h 下不完即清）`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[109] || (_cache[109] = _createElementVNode("dt", null, "促销失效清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[110] || (_cache[110] = _createElementVNode("dt", null, "自动恢复暂停", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.auto_resume_paused === false ? '关闭' : '开启'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[111] || (_cache[111] = _createElementVNode("dt", null, "选种来源", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.rss_support ? 'RSS' : '站点列表页'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[112] || (_cache[112] = _createElementVNode("dt", null, "促销要求", -1)),
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
                                  _createElementVNode("header", _hoisted_40, [
                                    _createElementVNode("div", null, [
                                      _cache[113] || (_cache[113] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "站点账号真实数据", -1)),
                                      _createElementVNode("div", _hoisted_41, "取自站点用户页（非下载器本地统计）" + _toDisplayString(siteUser.value.updated_at ? ` · 更新于 ${siteUser.value.updated_at}` : ''), 1)
                                    ]),
                                    (siteUser.value.ok)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 0,
                                          size: "small",
                                          variant: "tonal",
                                          color: "success"
                                        }, {
                                          default: _withCtx(() => [...(_cache[114] || (_cache[114] = [
                                            _createTextVNode("已同步", -1)
                                          ]))]),
                                          _: 1
                                        }))
                                      : (_openBlock(), _createBlock(_component_VChip, {
                                          key: 1,
                                          size: "small",
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx(() => [...(_cache[115] || (_cache[115] = [
                                            _createTextVNode("暂无数据", -1)
                                          ]))]),
                                          _: 1
                                        }))
                                  ]),
                                  _createElementVNode("dl", _hoisted_42, [
                                    _createElementVNode("div", null, [
                                      _cache[116] || (_cache[116] = _createElementVNode("dt", null, "上传量", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(siteUser.value.ok ? _unref(formatBytes)(siteUser.value.upload || 0) : '—'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[117] || (_cache[117] = _createElementVNode("dt", null, "下载量", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(siteUser.value.ok ? _unref(formatBytes)(siteUser.value.download || 0) : '—'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[118] || (_cache[118] = _createElementVNode("dt", null, "分享率", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(siteUser.value.ok ? Number(siteUser.value.ratio || 0).toFixed(3) : '—'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[119] || (_cache[119] = _createElementVNode("dt", null, "做种数 / 下载数", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(siteUser.value.ok ? `${siteUser.value.seeding || 0} / ${siteUser.value.leeching || 0}` : '—'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[120] || (_cache[120] = _createElementVNode("dt", null, "做种体积", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(siteUser.value.ok ? _unref(formatBytes)(siteUser.value.seeding_size || 0) : '—'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[121] || (_cache[121] = _createElementVNode("dt", null, "站点魔力", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(siteUser.value.ok ? Number(siteUser.value.bonus || 0).toFixed(2) : '—'), 1)
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
                                  _createElementVNode("header", _hoisted_43, [
                                    _createElementVNode("div", null, [
                                      _cache[122] || (_cache[122] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "最近一次运行", -1)),
                                      _createElementVNode("div", _hoisted_44, _toDisplayString(detailStats.value.last_run_at ? _unref(formatDateTime)(detailStats.value.last_run_at) : '暂无运行记录'), 1)
                                    ]),
                                    (detailStats.value.last_error)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 0,
                                          color: "error",
                                          size: "small",
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx(() => [...(_cache[123] || (_cache[123] = [
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
                                              default: _withCtx(() => [...(_cache[124] || (_cache[124] = [
                                                _createTextVNode("完成", -1)
                                              ]))]),
                                              _: 1
                                            }))
                                          : _createCommentVNode("", true)
                                  ]),
                                  _createElementVNode("div", _hoisted_45, [
                                    _createElementVNode("div", null, [
                                      _cache[125] || (_cache[125] = _createElementVNode("span", null, "上次成功", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_success_at ? _unref(formatDateTime)(detailStats.value.last_success_at) : '-'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[126] || (_cache[126] = _createElementVNode("span", null, "本次状态", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(_unref(runStatusText)(detailStats.value.last_run_status)), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[127] || (_cache[127] = _createElementVNode("span", null, "本次耗时", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(_unref(formatDurationSeconds)(detailStats.value.last_run_duration)), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[128] || (_cache[128] = _createElementVNode("span", null, "本次新增 / 复用", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_added || 0) + " / " + _toDisplayString(detailStats.value.last_reused || 0), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[129] || (_cache[129] = _createElementVNode("span", null, "本次删除", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_deleted || 0), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[130] || (_cache[130] = _createElementVNode("span", null, "慢扫辅种（累计 / 本次）", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(detailStats.value.cumulative_slow_reused || 0) + " / " + _toDisplayString(detailStats.value.last_slow_reused || 0), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[131] || (_cache[131] = _createElementVNode("span", null, "当前托管 / 受保护", -1)),
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
                                    onClick: _cache[5] || (_cache[5] = $event => (activeTab.value = 'diagnostics'))
                                  }, {
                                    default: _withCtx(() => [...(_cache[132] || (_cache[132] = [
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
                                _createElementVNode("header", _hoisted_46, [
                                  _createElementVNode("div", null, [
                                    _cache[133] || (_cache[133] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "运行流程", -1)),
                                    _createElementVNode("div", _hoisted_47, [
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
                                    _cache[134] || (_cache[134] = _createElementVNode("i", null, null, -1)),
                                    _createTextVNode(" " + _toDisplayString(flowPhaseText.value), 1)
                                  ], 2)
                                ]),
                                _createElementVNode("ol", _hoisted_48, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(flowNodes.value, (node, i) => {
                                    return (_openBlock(), _createElementBlock("li", {
                                      key: node.key,
                                      class: _normalizeClass(["magicflow-flow__node", `is-${node.state}`])
                                    }, [
                                      _createElementVNode("span", _hoisted_49, [
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
                                      _createElementVNode("span", _hoisted_50, _toDisplayString(node.label), 1),
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
                                _createElementVNode("header", _hoisted_51, [
                                  _createElementVNode("div", null, [
                                    _cache[135] || (_cache[135] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "过滤原因", -1)),
                                    _createElementVNode("div", _hoisted_52, [
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
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_53, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(reasonEntries.value, (item) => {
                                        return (_openBlock(), _createElementBlock("div", {
                                          key: item.label,
                                          class: "magicflow-reason"
                                        }, [
                                          _createElementVNode("div", null, [
                                            _createElementVNode("span", null, _toDisplayString(item.label), 1),
                                            _createElementVNode("strong", null, _toDisplayString(item.count), 1)
                                          ]),
                                          _createElementVNode("span", _hoisted_54, [
                                            _createElementVNode("i", {
                                              style: _normalizeStyle({ width: `${(item.count / maxReasonCount.value) * 100}%` })
                                            }, null, 4)
                                          ])
                                        ]))
                                      }), 128))
                                    ]))
                                  : (_openBlock(), _createElementBlock("div", _hoisted_55, "本轮没有记录过滤原因（候选全部通过或列表为空）")),
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
                                _createElementVNode("header", _hoisted_56, [
                                  _cache[137] || (_cache[137] = _createElementVNode("div", null, [
                                    _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "操作记录"),
                                    _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "每次执行 / 选种 / 删种 / 保护 / 标签 的流水（可展开明细）")
                                  ], -1)),
                                  _createVNode(_component_VBtn, {
                                    variant: "text",
                                    color: "primary",
                                    "prepend-icon": "mdi-refresh",
                                    onClick: _cache[6] || (_cache[6] = $event => (loadOperations(selectedTaskId.value)))
                                  }, {
                                    default: _withCtx(() => [...(_cache[136] || (_cache[136] = [
                                      _createTextVNode("刷新", -1)
                                    ]))]),
                                    _: 1
                                  })
                                ]),
                                _createElementVNode("div", _hoisted_57, [
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
                                          ? (_openBlock(), _createElementBlock("span", _hoisted_58, _toDisplayString(record.error_message), 1))
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
                                            ], 8, _hoisted_59))
                                          : _createCommentVNode("", true),
                                        (isOpDetailOpen(record.operation_id))
                                          ? (_openBlock(), _createElementBlock("ul", _hoisted_60, [
                                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(opDetailItems(record), (it, idx) => {
                                                return (_openBlock(), _createElementBlock("li", { key: idx }, [
                                                  _createElementVNode("span", _hoisted_61, [
                                                    (itemSourceText(it.source))
                                                      ? (_openBlock(), _createElementBlock("em", _hoisted_62, _toDisplayString(itemSourceText(it.source)), 1))
                                                      : _createCommentVNode("", true),
                                                    _createElementVNode("span", {
                                                      class: "magicflow-events__detail-title",
                                                      title: it.title || it.hash
                                                    }, _toDisplayString(it.title || it.hash || '—'), 9, _hoisted_63)
                                                  ]),
                                                  _createElementVNode("span", _hoisted_64, [
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
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_65, "暂无操作记录"))
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
                            _createElementVNode("div", _hoisted_66, [
                              _createElementVNode("div", null, [
                                _cache[138] || (_cache[138] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "种子池", -1)),
                                _createElementVNode("div", _hoisted_67, [
                                  (poolView.value === 'candidates')
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                        _createTextVNode(" 待办队列 · 共 " + _toDisplayString(candidateData.value.total || 0) + " 个通过过滤 ", 1)
                                      ], 64))
                                    : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                        _createTextVNode(" 已托管：共 " + _toDisplayString(bonusData.value.torrent_count || 0) + " 个 ", 1)
                                      ], 64))
                                ])
                              ]),
                              _createElementVNode("div", _hoisted_68, [
                                _createVNode(_component_VBtnToggle, {
                                  "model-value": poolView.value,
                                  mandatory: "",
                                  color: "primary",
                                  density: "compact",
                                  "onUpdate:modelValue": _cache[7] || (_cache[7] = value => (poolView.value = value))
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VBtn, {
                                      value: "candidates",
                                      "prepend-icon": "mdi-filter-variant"
                                    }, {
                                      default: _withCtx(() => [...(_cache[139] || (_cache[139] = [
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
                                      default: _withCtx(() => [...(_cache[140] || (_cache[140] = [
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
                                    _createElementVNode("header", _hoisted_69, [
                                      _createElementVNode("div", null, [
                                        _cache[141] || (_cache[141] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "候选排行", -1)),
                                        _createElementVNode("div", _hoisted_70, _toDisplayString(taskIsBrush.value ? '按上传潜力（下载人数）排序 · 仅供选种参考' : '待办名次由站点魔力效率内部排序 · 仅供选种参考'), 1)
                                      ])
                                    ]),
                                    _createElementVNode("ol", _hoisted_71, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList((candidateData.value.candidates || []).slice(0, 8), (candidate) => {
                                        return (_openBlock(), _createElementBlock("li", {
                                          key: candidate.hash
                                        }, [
                                          _createElementVNode("span", _hoisted_72, _toDisplayString(candidate.rank), 1),
                                          _createElementVNode("div", null, [
                                            _createElementVNode("strong", null, _toDisplayString(candidate.title || '未知种子'), 1),
                                            _createElementVNode("span", null, _toDisplayString(Number(candidate.size_gb || 0).toFixed(2)) + " GB · " + _toDisplayString(candidate.seeders) + " 做种 · " + _toDisplayString(candidate.leechers) + " 下载 · " + _toDisplayString(Number(candidate.age_weeks || 0).toFixed(1)) + " 周", 1)
                                          ])
                                        ]))
                                      }), 128)),
                                      (!(candidateData.value.candidates || []).length)
                                        ? (_openBlock(), _createElementBlock("li", _hoisted_73, [...(_cache[142] || (_cache[142] = [
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
                                    _createElementVNode("header", _hoisted_74, [
                                      _cache[145] || (_cache[145] = _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, " 点击任意行查看详情 / 手动保留 / 删除 ", -1)),
                                      _createElementVNode("div", _hoisted_75, [
                                        _createVNode(_component_VSelect, {
                                          modelValue: torrentStatusFilter.value,
                                          "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((torrentStatusFilter).value = $event)),
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
                                          "onUpdate:modelValue": _cache[9] || (_cache[9] = value => (torrentFilter.value = value))
                                        }, {
                                          default: _withCtx(() => [
                                            _createVNode(_component_VBtn, { value: "all" }, {
                                              default: _withCtx(() => [...(_cache[143] || (_cache[143] = [
                                                _createTextVNode("全部", -1)
                                              ]))]),
                                              _: 1
                                            }),
                                            _createVNode(_component_VBtn, { value: "protected" }, {
                                              default: _withCtx(() => [...(_cache[144] || (_cache[144] = [
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
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_76, [
                                          _createElementVNode("span", _hoisted_77, "已选 " + _toDisplayString(selectedHashes.value.length) + " 个", 1),
                                          _createVNode(_component_VBtn, {
                                            size: "small",
                                            variant: "tonal",
                                            disabled: batchBusy.value,
                                            onClick: _cache[10] || (_cache[10] = $event => (batchAction('protect')))
                                          }, {
                                            default: _withCtx(() => [...(_cache[146] || (_cache[146] = [
                                              _createTextVNode("保留", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["disabled"]),
                                          _createVNode(_component_VBtn, {
                                            size: "small",
                                            variant: "tonal",
                                            disabled: batchBusy.value,
                                            onClick: _cache[11] || (_cache[11] = $event => (batchAction('unprotect')))
                                          }, {
                                            default: _withCtx(() => [...(_cache[147] || (_cache[147] = [
                                              _createTextVNode("取消保留", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["disabled"]),
                                          _createVNode(_component_VBtn, {
                                            size: "small",
                                            variant: "tonal",
                                            disabled: batchBusy.value,
                                            onClick: _cache[12] || (_cache[12] = $event => (batchAction('pause')))
                                          }, {
                                            default: _withCtx(() => [...(_cache[148] || (_cache[148] = [
                                              _createTextVNode("暂停", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["disabled"]),
                                          _createVNode(_component_VBtn, {
                                            size: "small",
                                            variant: "tonal",
                                            disabled: batchBusy.value,
                                            onClick: _cache[13] || (_cache[13] = $event => (batchAction('resume')))
                                          }, {
                                            default: _withCtx(() => [...(_cache[149] || (_cache[149] = [
                                              _createTextVNode("恢复", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["disabled"]),
                                          _createVNode(_component_VBtn, {
                                            size: "small",
                                            variant: "tonal",
                                            disabled: batchBusy.value,
                                            onClick: _cache[14] || (_cache[14] = $event => (batchAction('recheck')))
                                          }, {
                                            default: _withCtx(() => [...(_cache[150] || (_cache[150] = [
                                              _createTextVNode("校验", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["disabled"]),
                                          _createVNode(_component_VBtn, {
                                            size: "small",
                                            variant: "tonal",
                                            color: "error",
                                            disabled: batchBusy.value,
                                            onClick: _cache[15] || (_cache[15] = $event => (batchDeleteDialog.value = true))
                                          }, {
                                            default: _withCtx(() => [...(_cache[151] || (_cache[151] = [
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
                                            default: _withCtx(() => [...(_cache[152] || (_cache[152] = [
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
                                          "onUpdate:modelValue": _cache[16] || (_cache[16] = value => (value ? selectAllFiltered() : clearSelection()))
                                        }, null, 8, ["model-value", "indeterminate"])
                                      ]),
                                      "item.select": _withCtx(({ item }) => [
                                        _createVNode(_component_VCheckbox, {
                                          "model-value": selectedHashes.value.includes(item.hash),
                                          density: "compact",
                                          "hide-details": "",
                                          "aria-label": `选择 ${item.title || ''}`,
                                          onClick: _cache[17] || (_cache[17] = _withModifiers(() => {}, ["stop"])),
                                          "onUpdate:modelValue": $event => (toggleTorrentSelection(item))
                                        }, null, 8, ["model-value", "aria-label", "onUpdate:modelValue"])
                                      ]),
                                      "item.title": _withCtx(({ item }) => [
                                        _createElementVNode("div", _hoisted_78, [
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
                                      "no-data": _withCtx(() => [...(_cache[153] || (_cache[153] = [
                                        _createElementVNode("div", { class: "magicflow-table-empty" }, "当前筛选下没有托管种子", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["items", "loading"]),
                                    _createElementVNode("div", _hoisted_79, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(sortedTorrents.value, (item) => {
                                        return (_openBlock(), _createElementBlock("article", {
                                          key: item.hash || item.title,
                                          class: "magicflow-mobile-torrent",
                                          onClick: $event => (openTorrentDetail(item))
                                        }, [
                                          _createElementVNode("div", _hoisted_81, [
                                            _createVNode(_component_VCheckbox, {
                                              "model-value": selectedHashes.value.includes(item.hash),
                                              density: "compact",
                                              "hide-details": "",
                                              class: "magicflow-mobile-torrent__check",
                                              onClick: _cache[18] || (_cache[18] = _withModifiers(() => {}, ["stop"])),
                                              "onUpdate:modelValue": $event => (toggleTorrentSelection(item))
                                            }, null, 8, ["model-value", "onUpdate:modelValue"]),
                                            _createElementVNode("div", _hoisted_82, [
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
                                          _createElementVNode("div", _hoisted_83, [
                                            _createElementVNode("span", null, [
                                              _cache[154] || (_cache[154] = _createElementVNode("em", null, "大小", -1)),
                                              _createElementVNode("b", null, _toDisplayString(Number(item.size_gb || 0).toFixed(2)) + " GB", 1)
                                            ]),
                                            _createElementVNode("span", null, [
                                              _cache[155] || (_cache[155] = _createElementVNode("em", null, "上传量", -1)),
                                              _createElementVNode("b", null, _toDisplayString(_unref(formatBytes)(item.uploaded)), 1)
                                            ]),
                                            _createElementVNode("span", null, [
                                              _cache[156] || (_cache[156] = _createElementVNode("em", null, "分享率", -1)),
                                              _createElementVNode("b", null, _toDisplayString(Number(item.ratio || 0).toFixed(2)), 1)
                                            ])
                                          ]),
                                          _createElementVNode("div", _hoisted_84, [
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
                                              default: _withCtx(() => [...(_cache[157] || (_cache[157] = [
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
                                                  default: _withCtx(() => [...(_cache[158] || (_cache[158] = [
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
                                              default: _withCtx(() => [...(_cache[159] || (_cache[159] = [
                                                _createTextVNode("校验", -1)
                                              ]))]),
                                              _: 1
                                            }, 8, ["onClick"])
                                          ])
                                        ], 8, _hoisted_80))
                                      }), 128)),
                                      (!sortedTorrents.value.length)
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_85, "当前筛选下没有托管种子"))
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
                            _createElementVNode("div", _hoisted_86, [
                              _createVNode(_component_VSheet, {
                                tag: "section",
                                class: "magicflow-panel app-surface-static"
                              }, {
                                default: _withCtx(() => [
                                  _createElementVNode("header", _hoisted_87, [
                                    _createElementVNode("div", null, [
                                      _createElementVNode("div", _hoisted_88, _toDisplayString(taskIsBrush.value ? '刷流规则' : '魔力规则'), 1),
                                      _createElementVNode("div", _hoisted_89, _toDisplayString(taskIsBrush.value ? '刷流标准：免费 + 有下载者；做种满天数清理' : '当前服务端生效的魔力养护配置'), 1)
                                    ])
                                  ]),
                                  _createElementVNode("dl", _hoisted_90, [
                                    _createElementVNode("div", null, [
                                      _cache[160] || (_cache[160] = _createElementVNode("dt", null, "任务状态", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(selectedRunMode.value.text), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[161] || (_cache[161] = _createElementVNode("dt", null, "任务目标", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(goalFactText.value), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[162] || (_cache[162] = _createElementVNode("dt", null, "站点", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(selectedTask.value.site_name), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[163] || (_cache[163] = _createElementVNode("dt", null, "下载器", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(selectedTask.value.downloader), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[164] || (_cache[164] = _createElementVNode("dt", null, "下载器标签", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(selectedTask.value.brush_tag || '未设置'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[165] || (_cache[165] = _createElementVNode("dt", null, "促销要求", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskIsBrush.value ? '免费（含 2X免费）' : (taskConfig.value.freeleech === '2xfree' ? '2X 免费' : taskConfig.value.freeleech === 'free' ? '免费' : '全部')), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[166] || (_cache[166] = _createElementVNode("dt", null, "选种来源", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.rss_support ? 'RSS' : '站点列表页'), 1)
                                    ]),
                                    (taskIsBrush.value)
                                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                          _createElementVNode("div", null, [
                                            _cache[167] || (_cache[167] = _createElementVNode("dt", null, "保种天数", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(brushSeedDays.value > 0 ? `做种满 ${brushSeedDays.value} 天清理` : '不按天数（按无上传）'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[168] || (_cache[168] = _createElementVNode("dt", null, "最小下载人数", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.brush_min_leechers ?? 1) + " 人", 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[169] || (_cache[169] = _createElementVNode("dt", null, "种子大小", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.size || '不限'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[170] || (_cache[170] = _createElementVNode("dt", null, "做种人数", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.seeder || '不限'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[171] || (_cache[171] = _createElementVNode("dt", null, "发布时间", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.pubtime ? `${taskConfig.value.pubtime} 分钟` : '不限'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[172] || (_cache[172] = _createElementVNode("dt", null, "排除 H&R", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.hr === 'yes' ? '是' : '否'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[173] || (_cache[173] = _createElementVNode("dt", null, "包含规则", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.include || '无'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[174] || (_cache[174] = _createElementVNode("dt", null, "排除规则", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.exclude || '无'), 1)
                                          ])
                                        ], 64))
                                      : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                          _createElementVNode("div", null, [
                                            _cache[175] || (_cache[175] = _createElementVNode("dt", null, "保种体积", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.disk_size_gb ? `${taskConfig.value.disk_size_gb} GB` : '不限'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[176] || (_cache[176] = _createElementVNode("dt", null, "最低魔力", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.value.min_bonus_per_hour).toFixed(2)} /h`), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[177] || (_cache[177] = _createElementVNode("dt", null, "最多保留", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_keep_torrents == null ? '自动 / 不限' : `${taskConfig.value.max_keep_torrents} 个`), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[178] || (_cache[178] = _createElementVNode("dt", null, "保护阈值", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.value.bonus_protect_threshold).toFixed(0)), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[179] || (_cache[179] = _createElementVNode("dt", null, "完美种保护", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.protect_perfect === false ? '关闭' : `开启（≤${taskConfig.value.perfect_max_seeders ?? 3}人 · ≥${taskConfig.value.perfect_min_weeks ?? 4}周）`), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[180] || (_cache[180] = _createElementVNode("dt", null, "公式 T0/N0", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_t0 ?? '默认') + " / " + _toDisplayString(taskConfig.value.bonus_n0 ?? '默认'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[181] || (_cache[181] = _createElementVNode("dt", null, "公式 B0/L", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_b0 ?? '默认') + " / " + _toDisplayString(taskConfig.value.bonus_l ?? '默认'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[182] || (_cache[182] = _createElementVNode("dt", null, "零魔权重", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_zero_weight ?? '默认'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[183] || (_cache[183] = _createElementVNode("dt", null, "保底魔力", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(Number(taskConfig.value.min_bonus_to_keep || 0).toFixed(2)), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[184] || (_cache[184] = _createElementVNode("dt", null, "种子大小", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.size || '不限'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[185] || (_cache[185] = _createElementVNode("dt", null, "做种人数", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.seeder || '不限'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[186] || (_cache[186] = _createElementVNode("dt", null, "发布时间", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.pubtime ? `${taskConfig.value.pubtime} 分钟` : '不限'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[187] || (_cache[187] = _createElementVNode("dt", null, "排除 H&R", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.hr === 'yes' ? '是' : '否'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[188] || (_cache[188] = _createElementVNode("dt", null, "包含规则", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.include || '无'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[189] || (_cache[189] = _createElementVNode("dt", null, "排除规则", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.exclude || '无'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[190] || (_cache[190] = _createElementVNode("dt", null, "最短做种", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_seed_time ? `${taskConfig.value.min_seed_time} 小时` : '不限'), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[191] || (_cache[191] = _createElementVNode("dt", null, "最低分享率", -1)),
                                            _createElementVNode("dd", null, _toDisplayString(Number(taskConfig.value.min_ratio || 0).toFixed(2)), 1)
                                          ])
                                        ], 64)),
                                    _createElementVNode("div", null, [
                                      _cache[192] || (_cache[192] = _createElementVNode("dt", null, "单轮最多新增", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_add_per_run ?? 10) + " 个", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[193] || (_cache[193] = _createElementVNode("dt", null, "同时下载上限", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_download_concurrent ?? 10) + " 个", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[194] || (_cache[194] = _createElementVNode("dt", null, "每轮参评候选", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.top_n ?? 30) + " 个", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[195] || (_cache[195] = _createElementVNode("dt", null, "每轮翻页数", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.browse_pages ?? 3) + " 页", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[196] || (_cache[196] = _createElementVNode("dt", null, "自动补种", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.refill_when_empty ? '开启' : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[197] || (_cache[197] = _createElementVNode("dt", null, "存量复用", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.reuse_existing ? (taskConfig.value.reuse_verify ? '开启（校验）' : '开启（跳过校验）') : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[198] || (_cache[198] = _createElementVNode("dt", null, "无进度清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_no_progress ? `开启（${taskConfig.value.no_progress_minutes ?? 30} 分钟）` : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[199] || (_cache[199] = _createElementVNode("dt", null, "慢速清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.value.slow_progress_max_hours ?? 48}h 下不完即清）`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[200] || (_cache[200] = _createElementVNode("dt", null, "促销失效清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[201] || (_cache[201] = _createElementVNode("dt", null, "自动恢复暂停", -1)),
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
                                  _cache[209] || (_cache[209] = _createElementVNode("header", { class: "magicflow-panel__head" }, [
                                    _createElementVNode("div", null, [
                                      _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "任务操作"),
                                      _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "以下操作只影响当前任务")
                                    ])
                                  ], -1)),
                                  _createElementVNode("div", _hoisted_91, [
                                    _createElementVNode("div", null, [
                                      _cache[203] || (_cache[203] = _createElementVNode("strong", null, "执行一次", -1)),
                                      _createElementVNode("span", null, _toDisplayString(taskIsBrush.value ? '立即按刷流标准抓取免费热种并保持上传' : '立即按当前策略抓取候选并养护做种'), 1),
                                      _createVNode(_component_VBtn, {
                                        color: "primary",
                                        variant: "tonal",
                                        "prepend-icon": "mdi-sync",
                                        loading: saving.value,
                                        onClick: runOperation
                                      }, {
                                        default: _withCtx(() => [...(_cache[202] || (_cache[202] = [
                                          _createTextVNode(" 立即执行 ", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["loading"])
                                    ]),
                                    _createVNode(_component_VDivider),
                                    _createElementVNode("div", null, [
                                      _cache[205] || (_cache[205] = _createElementVNode("strong", null, "编辑任务", -1)),
                                      _createElementVNode("span", null, _toDisplayString(taskIsBrush.value ? '调整调度、刷流门槛与清理策略' : '调整调度、魔力门槛与公式参数'), 1),
                                      _createVNode(_component_VBtn, {
                                        variant: "tonal",
                                        "prepend-icon": "mdi-pencil-outline",
                                        onClick: openEditTask
                                      }, {
                                        default: _withCtx(() => [...(_cache[204] || (_cache[204] = [
                                          _createTextVNode("编辑任务", -1)
                                        ]))]),
                                        _: 1
                                      })
                                    ]),
                                    _createVNode(_component_VDivider),
                                    _createElementVNode("div", null, [
                                      _cache[207] || (_cache[207] = _createElementVNode("strong", null, "删除任务", -1)),
                                      _cache[208] || (_cache[208] = _createElementVNode("span", null, "存在活跃种子时后端会拒绝删除，避免留下失管任务", -1)),
                                      _createVNode(_component_VBtn, {
                                        color: "error",
                                        variant: "tonal",
                                        "prepend-icon": "mdi-delete-outline",
                                        onClick: _cache[19] || (_cache[19] = $event => (deleteDialog.value = true))
                                      }, {
                                        default: _withCtx(() => [...(_cache[206] || (_cache[206] = [
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
                  ]))
                : _createCommentVNode("", true)
            ])
          ], 64)),
    _createVNode(TaskEditorDialog, {
      modelValue: editorOpen.value,
      "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((editorOpen).value = $event)),
      task: editorTask.value,
      sites: status.value.options.sites,
      downloaders: status.value.options.downloaders,
      "default-save-path": defaultSavePath.value,
      saving: saving.value,
      onSave: saveTask
    }, null, 8, ["modelValue", "task", "sites", "downloaders", "default-save-path", "saving"]),
    _createVNode(_component_VDialog, {
      modelValue: settingsDialog.value,
      "onUpdate:modelValue": _cache[64] || (_cache[64] = $event => ((settingsDialog).value = $event)),
      "max-width": "40rem"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog magicflow-settings-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("header", _hoisted_92, [
              _cache[210] || (_cache[210] = _createElementVNode("span", { class: "magicflow-settings-dialog__title" }, "插件设置", -1)),
              _createVNode(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[22] || (_cache[22] = $event => (settingsDialog.value = false))
              })
            ]),
            _createVNode(_component_VTabs, {
              modelValue: settingsTab.value,
              "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((settingsTab).value = $event)),
              class: "magicflow-settings-dialog__tabs",
              density: "comfortable",
              "show-arrows": ""
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTab, {
                  value: "general",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[211] || (_cache[211] = [
                    _createTextVNode("常规", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "downloader",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[212] || (_cache[212] = [
                    _createTextVNode("下载器参数", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "paths",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[213] || (_cache[213] = [
                    _createTextVNode("下载目录", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "template",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[214] || (_cache[214] = [
                    _createTextVNode("默认任务模板", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VTab, {
                  value: "iyuu",
                  class: "magicflow-settings-tab"
                }, {
                  default: _withCtx(() => [...(_cache[215] || (_cache[215] = [
                    _createTextVNode("IYUU 辅种", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            }, 8, ["modelValue"]),
            _createVNode(_component_VDivider),
            _createElementVNode("div", _hoisted_93, [
              (settingsTab.value === 'general')
                ? (_openBlock(), _createElementBlock("div", _hoisted_94, [
                    _createVNode(_component_VSwitch, {
                      modelValue: settingsDraft.value.enabled,
                      "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((settingsDraft.value.enabled) = $event)),
                      label: "启用插件",
                      color: "primary",
                      "hide-details": "",
                      inset: ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_VSwitch, {
                      modelValue: settingsDraft.value.show_sidebar_nav,
                      "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((settingsDraft.value.show_sidebar_nav) = $event)),
                      label: "显示侧栏入口",
                      color: "primary",
                      "hide-details": "",
                      inset: ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_VTextField, {
                      modelValue: settingsDraft.value.request_interval,
                      "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((settingsDraft.value.request_interval) = $event)),
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
                      "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((settingsDraft.value.journal_keep) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      min: "0",
                      label: "操作记录保留上限",
                      hint: "每个任务最多保留的操作记录条数，0 = 不限",
                      "persistent-hint": "",
                      variant: "outlined",
                      density: "comfortable"
                    }, null, 8, ["modelValue"]),
                    _cache[216] || (_cache[216] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                      _createTextVNode(" 任务流量：按「在跑的任务类型」自动设 qB "),
                      _createElementVNode("strong", null, "全局上传限速"),
                      _createTextVNode("（只限上传，不动下载）。有刷流任务时用刷流档，只有魔力任务时用魔力档；两者同时在跑取刷流档；一个启用的任务都没有则清除限速。 ")
                    ], -1)),
                    _createElementVNode("div", _hoisted_95, [
                      _createVNode(_component_VTextField, {
                        modelValue: settingsDraft.value.bonus_upload_limit_kbps,
                        "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((settingsDraft.value.bonus_upload_limit_kbps) = $event)),
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
                        "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((settingsDraft.value.brush_upload_limit_kbps) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "0",
                        step: "10",
                        label: "刷流任务上传限速（KB/s）",
                        hint: "有刷流任务在跑时生效（优先），0 = 不限",
                        "persistent-hint": "",
                        variant: "outlined",
                        density: "comfortable"
                      }, null, 8, ["modelValue"])
                    ]),
                    _createVNode(_component_VSwitch, {
                      modelValue: settingsDraft.value.debug_log,
                      "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((settingsDraft.value.debug_log) = $event)),
                      label: "调试日志",
                      color: "primary",
                      "hide-details": "",
                      inset: ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_VSwitch, {
                      modelValue: settingsDraft.value.compact_mode,
                      "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((settingsDraft.value.compact_mode) = $event)),
                      label: "紧凑模式",
                      color: "primary",
                      "hide-details": "",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]))
                : (settingsTab.value === 'downloader')
                  ? (_openBlock(), _createElementBlock("div", _hoisted_96, [
                      _cache[217] || (_cache[217] = _createElementVNode("p", { class: "magicflow-settings-hint magicflow-settings-hint--warn" }, " 以下为 qBittorrent 全局参数，将直接写入下载器，会影响所有使用该下载器的插件。 ", -1)),
                      _createElementVNode("div", _hoisted_97, [
                        _createVNode(_component_VTextField, {
                          modelValue: downloaderPrefsDraft.value.download_limit_kbps,
                          "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((downloaderPrefsDraft.value.download_limit_kbps) = $event)),
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
                          "onUpdate:modelValue": _cache[33] || (_cache[33] = $event => ((downloaderPrefsDraft.value.upload_limit_kbps) = $event)),
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
                          "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((downloaderPrefsDraft.value.max_connec) = $event)),
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
                          "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((downloaderPrefsDraft.value.max_connec_per_torrent) = $event)),
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
                          "onUpdate:modelValue": _cache[36] || (_cache[36] = $event => ((downloaderPrefsDraft.value.max_uploads) = $event)),
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
                          "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((downloaderPrefsDraft.value.max_uploads_per_torrent) = $event)),
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
                          "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((downloaderPrefsDraft.value.max_active_downloads) = $event)),
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
                          "onUpdate:modelValue": _cache[39] || (_cache[39] = $event => ((downloaderPrefsDraft.value.max_active_torrents) = $event)),
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
                        "onUpdate:modelValue": _cache[40] || (_cache[40] = $event => ((downloaderPrefsDraft.value.queueing_enabled) = $event)),
                        label: "启用队列限制（活动数上限生效的前提）",
                        color: "primary",
                        "hide-details": "",
                        inset: ""
                      }, null, 8, ["modelValue"])
                    ]))
                  : (settingsTab.value === 'paths')
                    ? (_openBlock(), _createElementBlock("div", _hoisted_98, [
                        _cache[218] || (_cache[218] = _createElementVNode("p", { class: "magicflow-settings-hint" }, " qBittorrent 全局目录，写入后影响所有使用该下载器的插件。 ", -1)),
                        _createVNode(_component_VTextField, {
                          modelValue: downloaderPathsDraft.value.save_path,
                          "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((downloaderPathsDraft.value.save_path) = $event)),
                          label: "默认保存路径",
                          placeholder: "如 /vol3/1000/media",
                          variant: "outlined",
                          density: "comfortable",
                          "hide-details": ""
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VTextField, {
                          modelValue: downloaderPathsDraft.value.temp_path,
                          "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((downloaderPathsDraft.value.temp_path) = $event)),
                          label: "临时下载路径",
                          placeholder: "下载中暂存目录",
                          variant: "outlined",
                          density: "comfortable",
                          "hide-details": ""
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VSwitch, {
                          modelValue: downloaderPathsDraft.value.temp_path_enabled,
                          "onUpdate:modelValue": _cache[43] || (_cache[43] = $event => ((downloaderPathsDraft.value.temp_path_enabled) = $event)),
                          label: "启用临时下载路径（下载中放临时目录，完成后移入保存路径）",
                          color: "primary",
                          "hide-details": "",
                          inset: ""
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VDivider, { class: "my-2" }),
                        _cache[219] || (_cache[219] = _createElementVNode("div", { class: "text-subtitle-2 font-weight-medium" }, "任务保存目录", -1)),
                        _cache[220] || (_cache[220] = _createElementVNode("p", { class: "magicflow-settings-hint" }, " 仅对魔流生效，不影响下载器全局设置。 ", -1)),
                        _createVNode(_component_VTextField, {
                          modelValue: defaultsDraft.value.save_path,
                          "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((defaultsDraft.value.save_path) = $event)),
                          label: "任务保存目录",
                          placeholder: "如 /vol3/1000/media/magicflow",
                          hint: "新建任务时自动预填此目录（不影响已有任务，任务内仍可单独修改）",
                          "persistent-hint": "",
                          variant: "outlined",
                          density: "comfortable"
                        }, null, 8, ["modelValue"])
                      ]))
                    : (settingsTab.value === 'iyuu')
                      ? (_openBlock(), _createElementBlock("div", _hoisted_99, [
                          _cache[225] || (_cache[225] = _createElementVNode("p", { class: "magicflow-settings-hint" }, [
                            _createTextVNode(" IYUU 云端辅种为"),
                            _createElementVNode("strong", null, "可选增强"),
                            _createTextVNode("：填写 Token 后，复用/刷流会优先用 IYUU 云端匹配"),
                            _createElementVNode("strong", null, "他站同资源"),
                            _createTextVNode("； 下方站点密钥可手填（留空则自动尝试用 MoviePilot 已存的 apikey / cookie 取链）。 "),
                            _createElementVNode("strong", null, "不填 Token 则完全不启用"),
                            _createTextVNode("，一切照旧走内置跨站特征码方案。 ")
                          ], -1)),
                          _createElementVNode("div", _hoisted_100, [
                            _createVNode(_component_VTextField, {
                              modelValue: settingsDraft.value.iyuu_token,
                              "onUpdate:modelValue": _cache[45] || (_cache[45] = $event => ((settingsDraft.value.iyuu_token) = $event)),
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
                              default: _withCtx(() => [...(_cache[221] || (_cache[221] = [
                                _createTextVNode("测试", -1)
                              ]))]),
                              _: 1
                            }, 8, ["loading", "disabled"])
                          ]),
                          _createElementVNode("div", _hoisted_101, [
                            _createElementVNode("div", _hoisted_102, [
                              _cache[222] || (_cache[222] = _createElementVNode("span", null, "站点密钥（按 MoviePilot 已配置站点生成）", -1)),
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
                              ? (_openBlock(), _createElementBlock("p", _hoisted_103, "加载中…"))
                              : (!iyuuSites.value.length)
                                ? (_openBlock(), _createElementBlock("p", _hoisted_104, " 未检测到已配置站点（请先在 MoviePilot 中添加站点）。 "))
                                : _createCommentVNode("", true),
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(iyuuSites.value, (row) => {
                              return (_openBlock(), _createElementBlock("div", {
                                key: row.domain || row.name,
                                class: "magicflow-iyuu-row"
                              }, [
                                _createElementVNode("div", _hoisted_105, [
                                  _createElementVNode("span", _hoisted_106, _toDisplayString(row.name), 1),
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
                                        default: _withCtx(() => [...(_cache[223] || (_cache[223] = [
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
                                        default: _withCtx(() => [...(_cache[224] || (_cache[224] = [
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
                                _createElementVNode("div", _hoisted_107, [
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
                      : (_openBlock(), _createElementBlock("div", _hoisted_108, [
                          _cache[226] || (_cache[226] = _createElementVNode("p", { class: "magicflow-settings-hint" }, " 仅用于新建任务时预填，不影响已有任务。 ", -1)),
                          _createElementVNode("div", _hoisted_109, [
                            _createVNode(_component_VSelect, {
                              modelValue: defaultsDraft.value.downloader,
                              "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((defaultsDraft.value.downloader) = $event)),
                              items: status.value.options.downloaders,
                              label: "默认下载器",
                              placeholder: "不指定（新建任务时再选）",
                              variant: "outlined",
                              density: "comfortable",
                              "hide-details": ""
                            }, null, 8, ["modelValue", "items"]),
                            _createVNode(_component_VTextField, {
                              modelValue: defaultsDraft.value.brush_interval,
                              "onUpdate:modelValue": _cache[47] || (_cache[47] = $event => ((defaultsDraft.value.brush_interval) = $event)),
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
                              "onUpdate:modelValue": _cache[48] || (_cache[48] = $event => ((defaultsDraft.value.check_interval) = $event)),
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
                              "onUpdate:modelValue": _cache[49] || (_cache[49] = $event => ((defaultsDraft.value.max_add_per_run) = $event)),
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
                              "onUpdate:modelValue": _cache[50] || (_cache[50] = $event => ((defaultsDraft.value.max_download_concurrent) = $event)),
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
                              "onUpdate:modelValue": _cache[51] || (_cache[51] = $event => ((defaultsDraft.value.top_n) = $event)),
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
                              "onUpdate:modelValue": _cache[52] || (_cache[52] = $event => ((defaultsDraft.value.browse_pages) = $event)),
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
                              "onUpdate:modelValue": _cache[53] || (_cache[53] = $event => ((defaultsDraft.value.seen_cooldown_hours) = $event)),
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
                              "onUpdate:modelValue": _cache[54] || (_cache[54] = $event => ((defaultsDraft.value.brush_seed_days) = $event)),
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
                          _createElementVNode("div", _hoisted_110, [
                            _createVNode(_component_VSwitch, {
                              modelValue: defaultsDraft.value.refill_when_empty,
                              "onUpdate:modelValue": _cache[55] || (_cache[55] = $event => ((defaultsDraft.value.refill_when_empty) = $event)),
                              label: "清理后自动补种",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VSwitch, {
                              modelValue: defaultsDraft.value.reuse_existing,
                              "onUpdate:modelValue": _cache[56] || (_cache[56] = $event => ((defaultsDraft.value.reuse_existing) = $event)),
                              label: "复用本机已有资源（辅种）",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VSwitch, {
                              modelValue: defaultsDraft.value.reuse_verify,
                              "onUpdate:modelValue": _cache[57] || (_cache[57] = $event => ((defaultsDraft.value.reuse_verify) = $event)),
                              label: "辅种前校验",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VSwitch, {
                              modelValue: defaultsDraft.value.cleanup_no_progress,
                              "onUpdate:modelValue": _cache[58] || (_cache[58] = $event => ((defaultsDraft.value.cleanup_no_progress) = $event)),
                              label: "清理无进度种子",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VSwitch, {
                              modelValue: defaultsDraft.value.cleanup_slow_progress,
                              "onUpdate:modelValue": _cache[59] || (_cache[59] = $event => ((defaultsDraft.value.cleanup_slow_progress) = $event)),
                              label: "清理过慢种子",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VSwitch, {
                              modelValue: defaultsDraft.value.purge_unfree_incomplete,
                              "onUpdate:modelValue": _cache[60] || (_cache[60] = $event => ((defaultsDraft.value.purge_unfree_incomplete) = $event)),
                              label: "清理「已非免费」未下完种子",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VSwitch, {
                              modelValue: defaultsDraft.value.auto_resume_paused,
                              "onUpdate:modelValue": _cache[61] || (_cache[61] = $event => ((defaultsDraft.value.auto_resume_paused) = $event)),
                              label: "自动恢复被暂停种子",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_VSwitch, {
                              modelValue: defaultsDraft.value.delete_files,
                              "onUpdate:modelValue": _cache[62] || (_cache[62] = $event => ((defaultsDraft.value.delete_files) = $event)),
                              label: "删种同时删除文件",
                              color: "primary",
                              "hide-details": "",
                              inset: ""
                            }, null, 8, ["modelValue"])
                          ])
                        ]))
            ]),
            _createElementVNode("footer", _hoisted_111, [
              (settingsTab.value === 'downloader')
                ? (_openBlock(), _createBlock(_component_VBtn, {
                    key: 0,
                    variant: "tonal",
                    color: "primary",
                    disabled: !downloaderPrefsRecommended.value,
                    onClick: applyRecommendedPrefs
                  }, {
                    default: _withCtx(() => [...(_cache[227] || (_cache[227] = [
                      _createTextVNode(" 恢复推荐值 ", -1)
                    ]))]),
                    _: 1
                  }, 8, ["disabled"]))
                : _createCommentVNode("", true),
              _createVNode(_component_VSpacer),
              _createVNode(_component_VBtn, {
                variant: "text",
                onClick: _cache[63] || (_cache[63] = $event => (settingsDialog.value = false))
              }, {
                default: _withCtx(() => [...(_cache[228] || (_cache[228] = [
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
                default: _withCtx(() => [...(_cache[229] || (_cache[229] = [
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
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: torrentDialog.value,
      "onUpdate:modelValue": _cache[72] || (_cache[72] = $event => ((torrentDialog).value = $event)),
      "max-width": "34rem"
    }, {
      default: _withCtx(() => [
        (activeTorrent.value)
          ? (_openBlock(), _createBlock(_component_VCard, {
              key: 0,
              class: "magicflow-dialog magicflow-torrent-dialog"
            }, {
              default: _withCtx(() => [
                _createElementVNode("header", _hoisted_112, [
                  _createElementVNode("div", _hoisted_113, [
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
                          default: _withCtx(() => [...(_cache[230] || (_cache[230] = [
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
                    onClick: _cache[65] || (_cache[65] = $event => (torrentDialog.value = false))
                  })
                ]),
                _createElementVNode("div", _hoisted_114, _toDisplayString(activeTorrent.value.title || '种子详情'), 1),
                _createElementVNode("div", _hoisted_115, [
                  _createVNode(_component_VProgressLinear, {
                    "model-value": torrentProgressPct(activeTorrent.value),
                    color: stateColor(activeTorrent.value.state),
                    height: "8",
                    rounded: ""
                  }, null, 8, ["model-value", "color"]),
                  _createElementVNode("span", _hoisted_116, _toDisplayString(torrentProgressPct(activeTorrent.value)) + "%", 1)
                ]),
                _createElementVNode("dl", _hoisted_117, [
                  _createElementVNode("div", null, [
                    _cache[231] || (_cache[231] = _createElementVNode("dt", null, "大小", -1)),
                    _createElementVNode("dd", null, _toDisplayString(Number(activeTorrent.value.size_gb || 0).toFixed(2)) + " GB", 1)
                  ]),
                  _createElementVNode("div", null, [
                    _cache[232] || (_cache[232] = _createElementVNode("dt", null, "上传量", -1)),
                    _createElementVNode("dd", null, _toDisplayString(_unref(formatBytes)(activeTorrent.value.uploaded)), 1)
                  ]),
                  _createElementVNode("div", null, [
                    _cache[233] || (_cache[233] = _createElementVNode("dt", null, "分享率", -1)),
                    _createElementVNode("dd", null, _toDisplayString(Number(activeTorrent.value.ratio || 0).toFixed(2)), 1)
                  ]),
                  _createElementVNode("div", null, [
                    _cache[234] || (_cache[234] = _createElementVNode("dt", null, "当前状态", -1)),
                    _createElementVNode("dd", null, _toDisplayString(stateLabel(activeTorrent.value.state)), 1)
                  ])
                ]),
                _createElementVNode("div", _hoisted_118, [
                  _cache[235] || (_cache[235] = _createElementVNode("span", { class: "magicflow-torrent-dialog__hash-label" }, "infohash", -1)),
                  _createElementVNode("code", null, _toDisplayString(activeTorrent.value.hash), 1),
                  _createVNode(_component_VBtn, {
                    size: "x-small",
                    variant: "text",
                    icon: "mdi-content-copy",
                    "aria-label": "复制 infohash",
                    onClick: _cache[66] || (_cache[66] = $event => (copyTorrentHash(activeTorrent.value.hash)))
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
                      onClick: _cache[67] || (_cache[67] = $event => (detailTorrentAction(activeTorrent.value.is_protected ? 'unprotect' : 'protect')))
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
                          onClick: _cache[68] || (_cache[68] = $event => (detailTorrentAction('resume')))
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
                          onClick: _cache[69] || (_cache[69] = $event => (detailTorrentAction('pause')))
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
                      onClick: _cache[70] || (_cache[70] = $event => (detailTorrentAction('recheck')))
                    }, {
                      default: _withCtx(() => [...(_cache[236] || (_cache[236] = [
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
                      onClick: _cache[71] || (_cache[71] = $event => (requestTorrentDelete(activeTorrent.value)))
                    }, {
                      default: _withCtx(() => [...(_cache[237] || (_cache[237] = [
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
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: batchDeleteDialog.value,
      "onUpdate:modelValue": _cache[75] || (_cache[75] = $event => ((batchDeleteDialog).value = $event)),
      "max-width": "28rem"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, null, {
              default: _withCtx(() => [...(_cache[238] || (_cache[238] = [
                _createTextVNode("批量删除托管种子", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_VCardText, { class: "text-body-2" }, {
              default: _withCtx(() => [
                _cache[239] || (_cache[239] = _createTextVNode(" 确认删除选中的 ", -1)),
                _createElementVNode("b", null, _toDisplayString(selectedHashes.value.length), 1),
                _cache[240] || (_cache[240] = _createTextVNode(" 个种子？ ", -1)),
                _cache[241] || (_cache[241] = _createElementVNode("br", null, null, -1)),
                _createElementVNode("span", _hoisted_119, " 将按任务设置" + _toDisplayString(selectedTask.value.delete_files ? '连同文件' : '保留文件') + "从下载器删除，不可撤销。 ", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_VCardActions, null, {
              default: _withCtx(() => [
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  variant: "text",
                  onClick: _cache[73] || (_cache[73] = $event => (batchDeleteDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[242] || (_cache[242] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  color: "error",
                  variant: "flat",
                  loading: batchBusy.value,
                  onClick: _cache[74] || (_cache[74] = $event => (batchAction('delete')))
                }, {
                  default: _withCtx(() => [...(_cache[243] || (_cache[243] = [
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
      "onUpdate:modelValue": _cache[77] || (_cache[77] = $event => ((torrentDeleteDialog).value = $event)),
      "max-width": "28rem"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "magicflow-dialog" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, { class: "text-wrap" }, {
              default: _withCtx(() => [...(_cache[244] || (_cache[244] = [
                _createTextVNode("删除托管种子", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_VCardText, { class: "text-body-2" }, {
              default: _withCtx(() => [
                _createTextVNode(" 确认删除「" + _toDisplayString(pendingTorrentDelete.value?.title || '该种子') + "」？ ", 1),
                _cache[245] || (_cache[245] = _createElementVNode("br", null, null, -1)),
                _createElementVNode("span", _hoisted_120, " 将按任务设置" + _toDisplayString(selectedTask.value.delete_files ? '连同文件' : '保留文件') + "从下载器删除，不可撤销。 ", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_VCardActions, null, {
              default: _withCtx(() => [
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  variant: "text",
                  onClick: _cache[76] || (_cache[76] = $event => (torrentDeleteDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[246] || (_cache[246] = [
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
                  default: _withCtx(() => [...(_cache[247] || (_cache[247] = [
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
      "onUpdate:modelValue": _cache[79] || (_cache[79] = $event => ((deleteDialog).value = $event)),
      "max-width": "28rem"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, {
          title: "删除魔力任务",
          class: "magicflow-dialog"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardText, null, {
              default: _withCtx(() => [
                _createTextVNode("确认删除「" + _toDisplayString(selectedTask.value?.name) + "」？存在活跃种子时不会执行删除。", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_VCardActions, null, {
              default: _withCtx(() => [
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  variant: "text",
                  onClick: _cache[78] || (_cache[78] = $event => (deleteDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[248] || (_cache[248] = [
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
                  default: _withCtx(() => [...(_cache[249] || (_cache[249] = [
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
    }, 8, ["modelValue"])
  ], 2))
}
}

};
const MagicFlowWorkbench = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-f91190c2"]]);

export { MagicFlowWorkbench as M };
