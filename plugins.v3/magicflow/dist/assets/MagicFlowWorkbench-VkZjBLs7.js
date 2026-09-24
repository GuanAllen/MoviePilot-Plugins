import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc, c as cloneTask, n as normalizeTask, t as taskStateMeta, r as runStatusText, f as formatBonus, a as formatDateTime, b as formatDurationSeconds, d as formatBytes, u as unwrapResponse, e as normalizeSettings, g as formatDuration } from './_plugin-vue_export-helper-CqdxjWse.js';

const {unref:_unref$1,toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,openBlock:_openBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$1,createElementVNode:_createElementVNode$1,withModifiers:_withModifiers$1} = await importShared('vue');


const _hoisted_1$1 = { class: "editor-section" };
const _hoisted_2$1 = { class: "editor-section__head" };
const _hoisted_3$1 = { class: "editor-switches" };
const _hoisted_4$1 = { class: "editor-section" };
const _hoisted_5$1 = { class: "editor-section__head" };
const _hoisted_6$1 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_7$1 = { class: "editor-section" };
const _hoisted_8$1 = { class: "editor-section__head" };
const _hoisted_9$1 = { class: "editor-switches" };
const _hoisted_10$1 = { class: "editor-section" };
const _hoisted_11$1 = { class: "editor-switches" };
const _hoisted_12$1 = { class: "editor-section" };
const _hoisted_13$1 = { class: "editor-section__head" };
const _hoisted_14$1 = { class: "editor-section" };
const _hoisted_15$1 = { class: "editor-section" };
const _hoisted_16$1 = { class: "editor-switches" };
const _hoisted_17$1 = { class: "editor-section" };
const _hoisted_18$1 = { class: "editor-section" };
const _hoisted_19$1 = { class: "magicflow-facts magicflow-facts--two" };

const {computed: computed$1,ref: ref$1,watch: watch$1} = await importShared('vue');

const {useDisplay} = await importShared('vuetify');


const _sfc_main$1 = {
  __name: 'TaskEditorDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
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

const dialogTitle = computed$1(() => (localTask.value.id ? '编辑魔力任务' : '新建魔力任务'));
const siteName = computed$1(() => {
  const site = props.sites.find(item => Number(item.value ?? item.id) === Number(localTask.value.site_id));
  return site?.title || site?.name || '未选择'
});
const scheduleText = computed$1(() => localTask.value.cron_expression || `每 ${localTask.value.brush_interval || 5} 分钟`);

// 每次打开弹窗都从服务端任务快照重新创建本地草稿。
watch$1(
  () => props.modelValue,
  visible => {
    if (!visible) return
    localTask.value = cloneTask(props.task);
    activeTab.value = 'base';
  },
);

// 关闭编辑器并丢弃尚未保存的草稿。
function closeDialog() {
  emit('update:modelValue', false);
}

// 校验必填项后提交标准化任务数据。
async function saveTask() {
  const result = await formRef.value?.validate();
  if (result && !result.valid) return
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
  const _component_VTextField = _resolveComponent$1("VTextField");
  const _component_VCol = _resolveComponent$1("VCol");
  const _component_VSelect = _resolveComponent$1("VSelect");
  const _component_VRow = _resolveComponent$1("VRow");
  const _component_VSwitch = _resolveComponent$1("VSwitch");
  const _component_VWindowItem = _resolveComponent$1("VWindowItem");
  const _component_VWindow = _resolveComponent$1("VWindow");
  const _component_VForm = _resolveComponent$1("VForm");
  const _component_VCardText = _resolveComponent$1("VCardText");
  const _component_VCard = _resolveComponent$1("VCard");
  const _component_VDialog = _resolveComponent$1("VDialog");

  return (_openBlock$1(), _createBlock$1(_component_VDialog, {
    "model-value": __props.modelValue,
    scrollable: "",
    fullscreen: _unref$1(display).smAndDown.value,
    "max-width": "74rem",
    "onUpdate:modelValue": _cache[51] || (_cache[51] = value => emit('update:modelValue', value))
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
                default: _withCtx$1(() => [...(_cache[52] || (_cache[52] = [
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
                      _createVNode$1(_component_VTab, {
                        value: "base",
                        "prepend-icon": "mdi-calendar-clock"
                      }, {
                        default: _withCtx$1(() => [...(_cache[53] || (_cache[53] = [
                          _createTextVNode$1("基础与调度", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode$1(_component_VTab, {
                        value: "magic",
                        "prepend-icon": "mdi-star-four-points-outline"
                      }, {
                        default: _withCtx$1(() => [...(_cache[54] || (_cache[54] = [
                          _createTextVNode$1("魔力托管", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode$1(_component_VTab, {
                        value: "formula",
                        "prepend-icon": "mdi-function-variant"
                      }, {
                        default: _withCtx$1(() => [...(_cache[55] || (_cache[55] = [
                          _createTextVNode$1("魔力公式", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode$1(_component_VTab, {
                        value: "selection",
                        "prepend-icon": "mdi-filter-cog-outline"
                      }, {
                        default: _withCtx$1(() => [...(_cache[56] || (_cache[56] = [
                          _createTextVNode$1("选种规则", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode$1(_component_VTab, {
                        value: "advanced",
                        "prepend-icon": "mdi-tune-variant"
                      }, {
                        default: _withCtx$1(() => [...(_cache[57] || (_cache[57] = [
                          _createTextVNode$1("高级", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["modelValue", "direction"]),
                  _createVNode$1(_component_VDivider, {
                    vertical: _unref$1(display).mdAndUp.value
                  }, null, 8, ["vertical"]),
                  _createVNode$1(_component_VWindow, {
                    modelValue: activeTab.value,
                    "onUpdate:modelValue": _cache[50] || (_cache[50] = $event => ((activeTab).value = $event)),
                    touch: false,
                    class: "magicflow-editor__window"
                  }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_VWindowItem, { value: "base" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_1$1, [
                            _createElementVNode$1("header", _hoisted_2$1, [
                              _cache[59] || (_cache[59] = _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "任务身份"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "每个任务绑定一个站点和下载器")
                              ], -1)),
                              _createVNode$1(_component_VChip, {
                                size: "small",
                                color: "primary",
                                variant: "tonal"
                              }, {
                                default: _withCtx$1(() => [...(_cache[58] || (_cache[58] = [
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
                                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((localTask.value.name) = $event)),
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
                                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((localTask.value.site_id) = $event)),
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
                                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((localTask.value.downloader) = $event)),
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
                                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((localTask.value.brush_tag) = $event)),
                                      label: "下载器标签",
                                      placeholder: "留空自动使用「魔力管家-任务名」"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }),
                                _createVNode$1(_component_VCol, { cols: "12" }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.save_path,
                                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((localTask.value.save_path) = $event)),
                                      label: "保存目录",
                                      placeholder: "留空使用下载器默认目录"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createElementVNode$1("div", _hoisted_3$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.enabled,
                                "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((localTask.value.enabled) = $event)),
                                label: "启用任务",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.rss_support,
                                "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((localTask.value.rss_support) = $event)),
                                label: "使用 RSS",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"])
                            ])
                          ]),
                          _createElementVNode$1("section", _hoisted_4$1, [
                            _createElementVNode$1("header", _hoisted_5$1, [
                              _cache[60] || (_cache[60] = _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "刷新计划"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "选种刷新和做种检查分别调度")
                              ], -1)),
                              _createElementVNode$1("span", _hoisted_6$1, _toDisplayString$1(scheduleText.value), 1)
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
                                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((localTask.value.brush_interval) = $event)),
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
                                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((localTask.value.check_interval) = $event)),
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
                                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((localTask.value.cron_expression) = $event)),
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
                                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((localTask.value.active_time_range) = $event)),
                                      label: "开启时间段",
                                      placeholder: "如 00:00-08:00"
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
                      }),
                      _createVNode$1(_component_VWindowItem, { value: "magic" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_7$1, [
                            _createElementVNode$1("header", _hoisted_8$1, [
                              _cache[62] || (_cache[62] = _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "魔力门槛（留空 = 自动）"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "留空由公式与实时数据自动推算，手填即覆盖")
                              ], -1)),
                              _createVNode$1(_component_VChip, {
                                size: "small",
                                color: "primary",
                                variant: "tonal"
                              }, {
                                default: _withCtx$1(() => [...(_cache[61] || (_cache[61] = [
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
                                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((localTask.value.min_bonus_per_hour) = $event)),
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
                                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((localTask.value.disk_size_gb) = $event)),
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
                                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((localTask.value.max_keep_torrents) = $event)),
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
                                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((localTask.value.max_add_per_run) = $event)),
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
                                      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((localTask.value.max_download_concurrent) = $event)),
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
                                      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((localTask.value.top_n) = $event)),
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
                                      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((localTask.value.browse_pages) = $event)),
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
                                      "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((localTask.value.bonus_protect_threshold) = $event)),
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
                                      "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((localTask.value.min_bonus_to_keep) = $event)),
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
                            _createElementVNode$1("div", _hoisted_9$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.refill_when_empty,
                                "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((localTask.value.refill_when_empty) = $event)),
                                label: "清理后主动补种",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.reuse_existing,
                                "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((localTask.value.reuse_existing) = $event)),
                                label: "复用本机已有资源（辅种）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.reuse_verify,
                                "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((localTask.value.reuse_verify) = $event)),
                                disabled: !localTask.value.reuse_existing,
                                label: "辅种前先校验（不匹配自动撤销）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue", "disabled"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.cleanup_no_progress,
                                "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((localTask.value.cleanup_no_progress) = $event)),
                                label: "每次运行清理无进度种子（停滞/出错且进度为 0）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.cleanup_slow_progress,
                                "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((localTask.value.cleanup_slow_progress) = $event)),
                                label: "清理下载过慢的种子（速度÷体积算 ETA，长期下不完的腾名额）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"]),
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.auto_resume_paused,
                                "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((localTask.value.auto_resume_paused) = $event)),
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
                                      "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((localTask.value.ti_source) = $event)),
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
                                          "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((localTask.value.no_progress_minutes) = $event)),
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
                                          "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((localTask.value.seen_cooldown_hours) = $event)),
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
                                          "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((localTask.value.slow_progress_grace_minutes) = $event)),
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
                                          "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((localTask.value.slow_progress_max_hours) = $event)),
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
                          _createElementVNode$1("section", _hoisted_10$1, [
                            _cache[63] || (_cache[63] = _createElementVNode$1("header", { class: "editor-section__head" }, [
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
                                      "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((localTask.value.min_seed_time) = $event)),
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
                                      "onUpdate:modelValue": _cache[33] || (_cache[33] = $event => ((localTask.value.min_ratio) = $event)),
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
                            _createElementVNode$1("div", _hoisted_11$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.delete_files,
                                "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((localTask.value.delete_files) = $event)),
                                label: "删种同时删除文件",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"])
                            ])
                          ])
                        ]),
                        _: 1
                      }),
                      _createVNode$1(_component_VWindowItem, { value: "formula" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_12$1, [
                            _createElementVNode$1("header", _hoisted_13$1, [
                              _cache[65] || (_cache[65] = _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "魔力公式参数"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, " 留空使用站点预设 / NexusPHP 标准式（T0=5，N0=7，B0=100，L=300） ")
                              ], -1)),
                              _createVNode$1(_component_VChip, {
                                size: "small",
                                color: "primary",
                                variant: "tonal"
                              }, {
                                default: _withCtx$1(() => [...(_cache[64] || (_cache[64] = [
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
                                      "onUpdate:modelValue": _cache[35] || (_cache[35] = $event => ((localTask.value.bonus_t0) = $event)),
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
                                      "onUpdate:modelValue": _cache[36] || (_cache[36] = $event => ((localTask.value.bonus_n0) = $event)),
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
                                      "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((localTask.value.bonus_b0) = $event)),
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
                                      "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((localTask.value.bonus_l) = $event)),
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
                                      "onUpdate:modelValue": _cache[39] || (_cache[39] = $event => ((localTask.value.bonus_zero_weight) = $event)),
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
                      }),
                      _createVNode$1(_component_VWindowItem, { value: "selection" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_14$1, [
                            _cache[66] || (_cache[66] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "来源与促销"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "沿用站点列表页或 RSS 获取链路")
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
                                      modelValue: localTask.value.freeleech,
                                      "onUpdate:modelValue": _cache[40] || (_cache[40] = $event => ((localTask.value.freeleech) = $event)),
                                      label: "促销",
                                      items: [
                        { title: '全部（包括普通）', value: '' },
                        { title: '免费', value: 'free' },
                        { title: '2X 免费', value: '2xfree' },
                      ]
                                    }, null, 8, ["modelValue"])
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
                                      "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((localTask.value.hr) = $event)),
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
                          _createElementVNode$1("section", _hoisted_15$1, [
                            _cache[67] || (_cache[67] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "候选过滤"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "范围字段支持单值或「最小值-最大值」")
                              ])
                            ], -1)),
                            _createVNode$1(_component_VRow, null, {
                              default: _withCtx$1(() => [
                                _createVNode$1(_component_VCol, {
                                  cols: "12",
                                  md: "4"
                                }, {
                                  default: _withCtx$1(() => [
                                    _createVNode$1(_component_VTextField, {
                                      modelValue: localTask.value.size,
                                      "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((localTask.value.size) = $event)),
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
                                      "onUpdate:modelValue": _cache[43] || (_cache[43] = $event => ((localTask.value.seeder) = $event)),
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
                                      "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((localTask.value.pubtime) = $event)),
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
                                      "onUpdate:modelValue": _cache[45] || (_cache[45] = $event => ((localTask.value.include) = $event)),
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
                                      "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((localTask.value.exclude) = $event)),
                                      label: "排除规则",
                                      placeholder: "支持正则表达式"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }),
                            _createElementVNode$1("div", _hoisted_16$1, [
                              _createVNode$1(_component_VSwitch, {
                                modelValue: localTask.value.exclude_zero_bonus,
                                "onUpdate:modelValue": _cache[47] || (_cache[47] = $event => ((localTask.value.exclude_zero_bonus) = $event)),
                                label: "不选零魔种子（Wi=0.2）",
                                color: "primary",
                                "hide-details": "",
                                inset: ""
                              }, null, 8, ["modelValue"])
                            ])
                          ])
                        ]),
                        _: 1
                      }),
                      _createVNode$1(_component_VWindowItem, { value: "advanced" }, {
                        default: _withCtx$1(() => [
                          _createElementVNode$1("section", _hoisted_17$1, [
                            _cache[68] || (_cache[68] = _createElementVNode$1("header", { class: "editor-section__head" }, [
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
                                      "onUpdate:modelValue": _cache[48] || (_cache[48] = $event => ((localTask.value.up_speed) = $event)),
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
                                      "onUpdate:modelValue": _cache[49] || (_cache[49] = $event => ((localTask.value.dl_speed) = $event)),
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
                          _createElementVNode$1("section", _hoisted_18$1, [
                            _cache[73] || (_cache[73] = _createElementVNode$1("header", { class: "editor-section__head" }, [
                              _createElementVNode$1("div", null, [
                                _createElementVNode$1("div", { class: "text-subtitle-1 font-weight-medium" }, "生效预览"),
                                _createElementVNode$1("div", { class: "text-body-2 text-medium-emphasis" }, "保存后立即写入调度，无需重启插件")
                              ])
                            ], -1)),
                            _createElementVNode$1("dl", _hoisted_19$1, [
                              _createElementVNode$1("div", null, [
                                _cache[69] || (_cache[69] = _createElementVNode$1("dt", null, "站点", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(siteName.value), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[70] || (_cache[70] = _createElementVNode$1("dt", null, "下载器", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(localTask.value.downloader || '未选择'), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[71] || (_cache[71] = _createElementVNode$1("dt", null, "调度", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(scheduleText.value), 1)
                              ]),
                              _createElementVNode$1("div", null, [
                                _cache[72] || (_cache[72] = _createElementVNode$1("dt", null, "开启时段", -1)),
                                _createElementVNode$1("dd", null, _toDisplayString$1(localTask.value.active_time_range || '全天'), 1)
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
      })
    ]),
    _: 1
  }, 8, ["model-value", "fullscreen"]))
}
}

};
const TaskEditorDialog = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-2cbfa188"]]);

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createBlock:_createBlock,toDisplayString:_toDisplayString,normalizeClass:_normalizeClass,mergeProps:_mergeProps,renderList:_renderList,Fragment:_Fragment,unref:_unref,withCtx:_withCtx,createTextVNode:_createTextVNode,normalizeStyle:_normalizeStyle,withModifiers:_withModifiers} = await importShared('vue');


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
const _hoisted_25 = {
  key: 0,
  class: "magicflow-workspace"
};
const _hoisted_26 = { class: "magicflow-task-head" };
const _hoisted_27 = { class: "magicflow-task-head__identity" };
const _hoisted_28 = ["src"];
const _hoisted_29 = { class: "magicflow-task-head__body" };
const _hoisted_30 = { class: "magicflow-task-head__title" };
const _hoisted_31 = { class: "magicflow-task-head__actions" };
const _hoisted_32 = {
  class: "magicflow-tabs",
  role: "tablist"
};
const _hoisted_33 = ["aria-selected", "onClick"];
const _hoisted_34 = { class: "magicflow-stat-grid" };
const _hoisted_35 = { class: "magicflow-overview-grid" };
const _hoisted_36 = { class: "magicflow-panel__head" };
const _hoisted_37 = { class: "magicflow-facts" };
const _hoisted_38 = { class: "magicflow-panel__head" };
const _hoisted_39 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_40 = { class: "magicflow-run-summary" };
const _hoisted_41 = { class: "magicflow-panel__head" };
const _hoisted_42 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_43 = { class: "magicflow-flow__chain" };
const _hoisted_44 = { class: "magicflow-flow__dot" };
const _hoisted_45 = { class: "magicflow-flow__label" };
const _hoisted_46 = { class: "magicflow-panel__head" };
const _hoisted_47 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_48 = {
  key: 0,
  class: "magicflow-reasons"
};
const _hoisted_49 = { class: "magicflow-reason__track" };
const _hoisted_50 = {
  key: 1,
  class: "magicflow-table-empty"
};
const _hoisted_51 = { class: "magicflow-panel__head" };
const _hoisted_52 = { class: "magicflow-events" };
const _hoisted_53 = {
  key: 0,
  class: "text-error"
};
const _hoisted_54 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_55 = { class: "magicflow-diagnostic-head" };
const _hoisted_56 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_57 = { class: "magicflow-torrent-filters" };
const _hoisted_58 = { class: "magicflow-pipeline" };
const _hoisted_59 = { class: "magicflow-pipeline__index" };
const _hoisted_60 = { key: 0 };
const _hoisted_61 = { class: "magicflow-panel__head" };
const _hoisted_62 = { class: "magicflow-panel__title-row" };
const _hoisted_63 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_64 = { class: "magicflow-torrent-filters" };
const _hoisted_65 = { class: "torrent-title-cell" };
const _hoisted_66 = { class: "magicflow-mobile-torrents" };
const _hoisted_67 = ["onClick"];
const _hoisted_68 = { class: "magicflow-mobile-torrent__head" };
const _hoisted_69 = { class: "magicflow-mobile-torrent__title" };
const _hoisted_70 = { class: "magicflow-mobile-torrent__grid" };
const _hoisted_71 = { class: "magicflow-mobile-torrent__actions" };
const _hoisted_72 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_73 = { class: "magicflow-config-grid" };
const _hoisted_74 = { class: "magicflow-facts magicflow-facts--two" };
const _hoisted_75 = { class: "magicflow-config-actions" };
const _hoisted_76 = { class: "magicflow-facts magicflow-torrent-detail" };
const _hoisted_77 = { class: "text-caption text-medium-emphasis magicflow-hash-line" };

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
const settingsMenu = ref(false);
const settingsDraft = ref({ enabled: false, show_sidebar_nav: true });
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
const selectedTask = computed(() => tasks.value.find(item => item.id === selectedTaskId.value) || null);
const summary = computed(() => status.value.summary || {});
const selectedState = computed(() =>
  taskStateMeta(selectedTask.value?.state, selectedTask.value?.enabled ?? status.value.enabled),
);
const taskConfig = computed(() => selectedTask.value || {});
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

// 运行诊断流程链（v5 阶段）
const FLOW_STEPS = [
  { key: 'entry', label: '入口检查' },
  { key: 'fetch', label: '抓取候选' },
  { key: 'wash', label: '洗池过滤' },
  { key: 'classify', label: '分类排序' },
  { key: 'process', label: '处理入库' },
];

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
  const idx = FLOW_STEPS.findIndex(step => step.key === phase);
  return FLOW_STEPS.map((step, i) => {
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
  const step = FLOW_STEPS.find(item => item.key === (detail.value?.last_phase || ''));
  return step ? step.label : runStatusText(detail.value?.last_run_status)
});

const torrentHeaders = [
  { title: '种子', key: 'title', sortable: false },
  { title: '状态', key: 'status', sortable: false, width: 120 },
  { title: '大小', key: 'size_gb', sortable: false, width: 96 },
  { title: '上传量', key: 'uploaded', sortable: false, width: 96 },
  { title: '分享率', key: 'ratio', sortable: false, width: 84 },
  { title: '操作', key: 'actions', sortable: false, width: 120 },
];

function notify(message, color = 'success') {
  const method = ['error', 'info', 'warning', 'success'].includes(color) ? color : 'success';
  if (typeof hostToast?.[method] === 'function') {
    hostToast[method](message);
  } else if (method === 'error') {
    error.value = message;
  }
}

const KIND_TEXT = { run: '执行', selection: '选种加入', deletion: '删种清理', protection: '手动保留', unprotection: '取消保留', reuse: '存量复用' };
const STATE_TEXT = { submitting: '提交中', accepted: '已受理', completed: '已完成', failed: '失败' };
const KIND_ICON = {
  run: 'mdi-play-circle-outline',
  selection: 'mdi-download-outline',
  deletion: 'mdi-delete-outline',
  reuse: 'mdi-content-duplicate',
  protection: 'mdi-shield-check-outline',
  unprotection: 'mdi-shield-off-outline',
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
  if (record.kind === 'run') return 'secondary'
  return 'primary'
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

// 托管种子状态文本：做种 / 下载 X% / 停滞（参考 BrushFlow）
function torrentStateText(item) {
  const pct = torrentProgressPct(item);
  if (pct >= 100) return '做种中'
  if (pct <= 0) return stateLabel(item?.state) || '等待中'
  return `下载 ${pct}%`
}

// 下载进度百分比（0~100），供进度条使用
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100;
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}

// 托管种子状态分组（用于状态筛选）
function torrentStatusGroup(item) {
  const key = String(item?.state || '').toLowerCase();
  if (['uploading', 'forcedup', 'stalledup', 'queuedup'].includes(key)) return 'seeding'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'checkingdl'].includes(key)) return 'downloading'
  if (key === 'stalleddl') return 'stalled'
  if (['pausedup', 'pauseddl', 'stoppedup', 'stoppeddl'].includes(key)) return 'paused'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'other'
}

// 状态筛选选项（带数量）
const torrentStatusOptions = computed(() => {
  const items = bonusData.value.torrents || [];
  const count = group => items.filter(item => torrentStatusGroup(item) === group).length;
  return [
    { title: `全部状态（${items.length}）`, value: 'all' },
    { title: `做种中（${count('seeding')}）`, value: 'seeding' },
    { title: `下载中（${count('downloading')}）`, value: 'downloading' },
    { title: `下载停滞（${count('stalled')}）`, value: 'stalled' },
    { title: `已暂停 / 停止（${count('paused')}）`, value: 'paused' },
    { title: `出错（${count('error')}）`, value: 'error' },
  ]
});

// 加载插件总览与任务列表。
async function loadStatus() {
  loading.value = true;
  try {
    status.value = unwrapResponse(await props.api.get(`${pluginBase.value}/status`)) || status.value;
    settingsDraft.value = normalizeSettings({
      enabled: status.value.enabled,
      show_sidebar_nav: status.value.show_sidebar_nav,
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
async function loadBonus(taskId) {
  taskLoading.value = true;
  try {
    bonusData.value = unwrapResponse(await props.api.get(`${pluginBase.value}/tasks/${taskId}/bonus`)) || bonusData.value;
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    taskLoading.value = false;
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
  if (activeTab.value === 'pool') loadCandidates(taskId);
}

// 重新拉取当前任务的全部明细数据。
function reloadSelected(taskId = selectedTaskId.value) {
  if (!taskId) return
  selectedTaskId.value = taskId;
  detail.value = null;
  bonusData.value = { torrents: [], total_bonus: 0, torrent_count: 0, protected_count: 0 };
  candidateData.value = { candidates: [], total: 0, reason_counts: {} };
  candidateLoadedFor.value = '';
  candidateLoadedAt.value = 0;
  operationData.value = { operations: [], total: 0 };
  loadDetail(taskId);
  loadBonus(taskId);
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

// 切换当前任务启停状态。
async function toggleSelectedTask() {
  if (!selectedTask.value) return
  saving.value = true;
  try {
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/state`, {
        enabled: !selectedTask.value.enabled,
      }),
    );
    notify(selectedTask.value.enabled ? '任务已暂停' : '任务已启用');
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
  editorTask.value = cloneTask();
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

// 对托管种子执行保留 / 取消保留 / 删除。
async function torrentAction(torrent, action) {
  saving.value = true;
  try {
    const verb = action === 'delete' ? 'delete' : action;
    unwrapResponse(
      await props.api.post(`${pluginBase.value}/tasks/${selectedTask.value.id}/torrents/${torrent.hash}/${verb}`, {}),
    );
    notify(action === 'protect' ? '已保留种子' : action === 'unprotect' ? '已取消保留' : '已删除种子');
    await Promise.all([loadBonus(selectedTask.value.id), loadDetail(selectedTask.value.id)]);
    emit('action');
  } catch (err) {
    error.value = err?.message || String(err);
  } finally {
    saving.value = false;
  }
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
  if (target && typeof target.closest === 'function' && target.closest('.v-btn, button, a')) return
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

// 保存全局设置。
async function saveSettings() {
  saving.value = true;
  try {
    unwrapResponse(await props.api.post(`${pluginBase.value}/settings`, normalizeSettings(settingsDraft.value)));
    settingsMenu.value = false;
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
    else loadBonus(selectedTaskId.value);
  }
  if (tab === 'diagnostics' && selectedTaskId.value) {
    loadOperations(selectedTaskId.value);
    loadDetail(selectedTaskId.value);
  }
});

watch(poolView, view => {
  if (!selectedTaskId.value) return
  if (view === 'candidates') loadCandidates(selectedTaskId.value);
  else loadBonus(selectedTaskId.value);
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
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VCardActions = _resolveComponent("VCardActions");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSkeletonLoader = _resolveComponent("VSkeletonLoader");
  const _component_VSheet = _resolveComponent("VSheet");
  const _component_VAvatar = _resolveComponent("VAvatar");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VWindowItem = _resolveComponent("VWindowItem");
  const _component_VBtnToggle = _resolveComponent("VBtnToggle");
  const _component_VSelect = _resolveComponent("VSelect");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VWindow = _resolveComponent("VWindow");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDialog = _resolveComponent("VDialog");

  return (_openBlock(), _createElementBlock("div", {
    class: _normalizeClass(["magicflow-page", { 'magicflow-page--compact': __props.compact }])
  }, [
    _createElementVNode("header", _hoisted_1, [
      _createElementVNode("div", _hoisted_2, [
        _createElementVNode("span", _hoisted_3, [
          _createVNode(_component_VIcon, {
            icon: "mdi-magnet",
            size: "20"
          })
        ]),
        _cache[21] || (_cache[21] = _createElementVNode("div", null, [
          _createElementVNode("h1", null, "魔力管家"),
          _createElementVNode("p", null, "PT 做种 · 魔力养护后台")
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
                    _cache[22] || (_cache[22] = _createElementVNode("span", { class: "magicflow-task-switch__k" }, "当前任务", -1)),
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
                            icon: _unref(taskStateMeta)(task.state, task.enabled).icon,
                            color: _unref(taskStateMeta)(task.state, task.enabled).color,
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
          default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
            _createTextVNode(" 新建任务 ", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VMenu, {
          modelValue: settingsMenu.value,
          "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((settingsMenu).value = $event)),
          "close-on-content-click": false,
          location: "bottom end"
        }, {
          activator: _withCtx(({ props: menuProps }) => [
            _createVNode(_component_VBtn, _mergeProps(menuProps, {
              icon: "mdi-tune-variant",
              variant: "text",
              "aria-label": "全局设置"
            }), null, 16)
          ]),
          default: _withCtx(() => [
            _createVNode(_component_VCard, {
              class: "magicflow-settings-menu",
              title: "全局设置"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VCardText, { class: "settings-menu__body" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: settingsDraft.value.enabled,
                      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((settingsDraft.value.enabled) = $event)),
                      label: "启用插件",
                      color: "primary",
                      "hide-details": "",
                      inset: ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_VSwitch, {
                      modelValue: settingsDraft.value.show_sidebar_nav,
                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((settingsDraft.value.show_sidebar_nav) = $event)),
                      label: "显示侧栏入口",
                      color: "primary",
                      "hide-details": "",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardActions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VBtn, {
                      color: "primary",
                      variant: "flat",
                      loading: saving.value,
                      onClick: saveSettings
                    }, {
                      default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
                        _createTextVNode("保存", -1)
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
        (__props.showClose)
          ? (_openBlock(), _createBlock(_component_VBtn, {
              key: 2,
              icon: "mdi-close",
              variant: "text",
              "aria-label": "关闭",
              onClick: _cache[3] || (_cache[3] = $event => (emit('close')))
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
          default: _withCtx(() => [...(_cache[25] || (_cache[25] = [
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
            _cache[27] || (_cache[27] = _createElementVNode("div", { class: "text-h6" }, "还没有魔力任务", -1)),
            _cache[28] || (_cache[28] = _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "创建任务后可按站点魔力公式独立养护做种", -1)),
            _createVNode(_component_VBtn, {
              color: "primary",
              variant: "flat",
              "prepend-icon": "mdi-plus",
              onClick: openCreateTask
            }, {
              default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
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
                          _cache[29] || (_cache[29] = _createElementVNode("span", { class: "magicflow-task-switch__k" }, "当前任务", -1)),
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
                                  icon: _unref(taskStateMeta)(task.state, task.enabled).icon,
                                  color: _unref(taskStateMeta)(task.state, task.enabled).color,
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
                    _cache[30] || (_cache[30] = _createElementVNode("span", null, "当前任务", -1)),
                    _createElementVNode("strong", null, _toDisplayString(selectedTask.value?.name || '—'), 1)
                  ])),
              _createVNode(_component_VBtn, {
                class: "magicflow-mobile-add",
                variant: "tonal",
                color: "primary",
                "prepend-icon": "mdi-plus",
                onClick: openCreateTask
              }, {
                default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
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
                    _cache[32] || (_cache[32] = _createElementVNode("span", { class: "text-subtitle-2" }, "魔力任务", -1)),
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
                            class: _normalizeClass(["magicflow-status-dot", `magicflow-status-dot--${_unref(taskStateMeta)(task.state, task.enabled).color}`])
                          }, null, 2)
                        ]),
                        _createElementVNode("span", null, _toDisplayString(task.site_name) + " · " + _toDisplayString(task.downloader), 1),
                        _createElementVNode("span", _hoisted_24, [
                          _createElementVNode("span", null, _toDisplayString(task.seeding_count || 0) + " 个种子", 1),
                          _createElementVNode("span", null, _toDisplayString(task.site_bonus_ok ? _unref(formatBonus)(task.site_bonus_per_hour) : '—'), 1)
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
                    default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
                      _createTextVNode(" 新建任务 ", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              (selectedTask.value)
                ? (_openBlock(), _createElementBlock("main", _hoisted_25, [
                    _createElementVNode("section", _hoisted_26, [
                      _createElementVNode("div", _hoisted_27, [
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
                                }, null, 8, _hoisted_28))
                              : (_openBlock(), _createBlock(_component_VIcon, {
                                  key: 1,
                                  icon: "mdi-web"
                                }))
                          ]),
                          _: 1
                        }),
                        _createElementVNode("div", _hoisted_29, [
                          _createElementVNode("div", _hoisted_30, [
                            _createElementVNode("h2", null, _toDisplayString(selectedTask.value.name), 1),
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
                      _createElementVNode("div", _hoisted_31, [
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
                              onClick: _cache[5] || (_cache[5] = $event => (reloadSelected()))
                            }), null, 16)
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VTooltip, {
                          text: selectedTask.value.enabled ? '暂停任务' : '启用任务'
                        }, {
                          activator: _withCtx(({ props: tipProps }) => [
                            _createVNode(_component_VBtn, _mergeProps(tipProps, {
                              icon: selectedTask.value.enabled ? 'mdi-pause' : 'mdi-play',
                              variant: "text",
                              onClick: toggleSelectedTask
                            }), null, 16, ["icon"])
                          ]),
                          _: 1
                        }, 8, ["text"]),
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
                              onClick: _cache[6] || (_cache[6] = $event => (deleteDialog.value = true))
                            }), null, 16)
                          ]),
                          _: 1
                        })
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_32, [
                      (_openBlock(), _createElementBlock(_Fragment, null, _renderList(MF_TABS, (tab) => {
                        return _createElementVNode("button", {
                          key: tab.value,
                          type: "button",
                          role: "tab",
                          class: _normalizeClass(["magicflow-tab", { 'is-active': activeTab.value === tab.value }]),
                          "aria-selected": activeTab.value === tab.value,
                          onClick: $event => (activeTab.value = tab.value)
                        }, _toDisplayString(tab.label), 11, _hoisted_33)
                      }), 64))
                    ]),
                    _createVNode(_component_VWindow, {
                      modelValue: activeTab.value,
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((activeTab).value = $event)),
                      touch: false,
                      class: "magicflow-window"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VWindowItem, { value: "overview" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_34, [
                              _createVNode(_component_VSheet, { class: "magicflow-stat magicflow-stat--accent app-surface-static" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("strong", null, _toDisplayString(selectedTask.value.seeding_count || 0), 1),
                                  _createElementVNode("span", null, "托管种子 · " + _toDisplayString(selectedTask.value.active_seeding_count || 0) + " 做种中 / " + _toDisplayString(selectedTask.value.downloading_count || 0) + " 下载中 / " + _toDisplayString(selectedTask.value.paused_count || 0) + " 已暂停", 1)
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("strong", null, _toDisplayString(selectedTask.value.site_bonus_ok ? _unref(formatBonus)(selectedTask.value.site_bonus_per_hour) : '—'), 1),
                                  _cache[34] || (_cache[34] = _createElementVNode("span", null, "站点上报时魔 · 站点实时值", -1))
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("strong", null, _toDisplayString(Number(selectedTask.value.site_current_bonus || 0).toFixed(2)), 1),
                                  _cache[35] || (_cache[35] = _createElementVNode("span", null, "站点当前魔力 · 该站点实时存量", -1))
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VSheet, { class: "magicflow-stat app-surface-static" }, {
                                default: _withCtx(() => [
                                  _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_added || 0) + " / " + _toDisplayString(detailStats.value.last_reused || 0) + " / " + _toDisplayString(detailStats.value.last_deleted || 0), 1),
                                  _createElementVNode("span", null, "上次运行 新增/复用/删除 · 当前托管 " + _toDisplayString(detailStats.value.last_kept || selectedTask.value.seeding_count || 0), 1)
                                ]),
                                _: 1
                              })
                            ]),
                            _createElementVNode("div", _hoisted_35, [
                              _createVNode(_component_VSheet, {
                                tag: "section",
                                class: "magicflow-panel app-surface-static"
                              }, {
                                default: _withCtx(() => [
                                  _createElementVNode("header", _hoisted_36, [
                                    _cache[36] || (_cache[36] = _createElementVNode("div", null, [
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
                                  _createElementVNode("dl", _hoisted_37, [
                                    _createElementVNode("div", null, [
                                      _cache[37] || (_cache[37] = _createElementVNode("dt", null, "选种周期", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cron_expression || `每 ${taskConfig.value.brush_interval} 分钟`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[38] || (_cache[38] = _createElementVNode("dt", null, "检查周期", -1)),
                                      _createElementVNode("dd", null, "每 " + _toDisplayString(taskConfig.value.check_interval) + " 分钟", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[39] || (_cache[39] = _createElementVNode("dt", null, "开启时段", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.active_time_range || '全天'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[40] || (_cache[40] = _createElementVNode("dt", null, "最低魔力", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.value.min_bonus_per_hour).toFixed(2)} /h`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[41] || (_cache[41] = _createElementVNode("dt", null, "最多保留", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_keep_torrents == null ? (taskConfig.value.disk_size_gb ? `按 ${taskConfig.value.disk_size_gb}GB 自动` : '不限') : `${taskConfig.value.max_keep_torrents} 个`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[42] || (_cache[42] = _createElementVNode("dt", null, "保护阈值", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.value.bonus_protect_threshold).toFixed(0)), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[43] || (_cache[43] = _createElementVNode("dt", null, "自动补种", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.refill_when_empty ? '开启' : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[44] || (_cache[44] = _createElementVNode("dt", null, "存量复用", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.reuse_existing ? '开启' : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[45] || (_cache[45] = _createElementVNode("dt", null, "无进度清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_no_progress ? `开启（${taskConfig.value.no_progress_minutes ?? 30} 分钟）` : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[46] || (_cache[46] = _createElementVNode("dt", null, "慢速清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.value.slow_progress_max_hours ?? 48}h 下不完即清）`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[47] || (_cache[47] = _createElementVNode("dt", null, "自动恢复暂停", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.auto_resume_paused === false ? '关闭' : '开启'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[48] || (_cache[48] = _createElementVNode("dt", null, "选种来源", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.rss_support ? 'RSS' : '站点列表页'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[49] || (_cache[49] = _createElementVNode("dt", null, "促销要求", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.freeleech === '2xfree' ? '2X 免费' : taskConfig.value.freeleech === 'free' ? '免费' : '全部'), 1)
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
                                  _createElementVNode("header", _hoisted_38, [
                                    _createElementVNode("div", null, [
                                      _cache[50] || (_cache[50] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "最近一次运行", -1)),
                                      _createElementVNode("div", _hoisted_39, _toDisplayString(detailStats.value.last_run_at ? _unref(formatDateTime)(detailStats.value.last_run_at) : '暂无运行记录'), 1)
                                    ]),
                                    (detailStats.value.last_error)
                                      ? (_openBlock(), _createBlock(_component_VChip, {
                                          key: 0,
                                          color: "error",
                                          size: "small",
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx(() => [...(_cache[51] || (_cache[51] = [
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
                                              default: _withCtx(() => [...(_cache[52] || (_cache[52] = [
                                                _createTextVNode("完成", -1)
                                              ]))]),
                                              _: 1
                                            }))
                                          : _createCommentVNode("", true)
                                  ]),
                                  _createElementVNode("div", _hoisted_40, [
                                    _createElementVNode("div", null, [
                                      _cache[53] || (_cache[53] = _createElementVNode("span", null, "上次成功", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_success_at ? _unref(formatDateTime)(detailStats.value.last_success_at) : '-'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[54] || (_cache[54] = _createElementVNode("span", null, "本次状态", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(_unref(runStatusText)(detailStats.value.last_run_status)), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[55] || (_cache[55] = _createElementVNode("span", null, "本次耗时", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(_unref(formatDurationSeconds)(detailStats.value.last_run_duration)), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[56] || (_cache[56] = _createElementVNode("span", null, "本次新增 / 复用", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_added || 0) + " / " + _toDisplayString(detailStats.value.last_reused || 0), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[57] || (_cache[57] = _createElementVNode("span", null, "本次删除", -1)),
                                      _createElementVNode("strong", null, _toDisplayString(detailStats.value.last_deleted || 0), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[58] || (_cache[58] = _createElementVNode("span", null, "当前托管 / 受保护", -1)),
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
                                    onClick: _cache[7] || (_cache[7] = $event => (activeTab.value = 'diagnostics'))
                                  }, {
                                    default: _withCtx(() => [...(_cache[59] || (_cache[59] = [
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
                                _createElementVNode("header", _hoisted_41, [
                                  _createElementVNode("div", null, [
                                    _cache[60] || (_cache[60] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "运行流程", -1)),
                                    _createElementVNode("div", _hoisted_42, _toDisplayString(detailStats.value.run_active ? '正在执行本轮刷流…' : (detailStats.value.last_run_at ? `最近执行 ${_unref(formatDateTime)(detailStats.value.last_run_at)}` : '尚未运行')) + " · 翻页游标 " + _toDisplayString(detailStats.value.page_cursor ?? 0), 1)
                                  ]),
                                  _createElementVNode("span", {
                                    class: _normalizeClass(["magicflow-flow__tag", { 'is-live': detailStats.value.run_active, 'is-error': detailStats.value.last_run_status === 'failed' }])
                                  }, [
                                    _cache[61] || (_cache[61] = _createElementVNode("i", null, null, -1)),
                                    _createTextVNode(" " + _toDisplayString(flowPhaseText.value), 1)
                                  ], 2)
                                ]),
                                _createElementVNode("ol", _hoisted_43, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(flowNodes.value, (node, i) => {
                                    return (_openBlock(), _createElementBlock("li", {
                                      key: node.key,
                                      class: _normalizeClass(["magicflow-flow__node", `is-${node.state}`])
                                    }, [
                                      _createElementVNode("span", _hoisted_44, [
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
                                      _createElementVNode("span", _hoisted_45, _toDisplayString(node.label), 1),
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
                                _createElementVNode("header", _hoisted_46, [
                                  _createElementVNode("div", null, [
                                    _cache[62] || (_cache[62] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "过滤原因", -1)),
                                    _createElementVNode("div", _hoisted_47, [
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
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_48, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(reasonEntries.value, (item) => {
                                        return (_openBlock(), _createElementBlock("div", {
                                          key: item.label,
                                          class: "magicflow-reason"
                                        }, [
                                          _createElementVNode("div", null, [
                                            _createElementVNode("span", null, _toDisplayString(item.label), 1),
                                            _createElementVNode("strong", null, _toDisplayString(item.count), 1)
                                          ]),
                                          _createElementVNode("span", _hoisted_49, [
                                            _createElementVNode("i", {
                                              style: _normalizeStyle({ width: `${(item.count / maxReasonCount.value) * 100}%` })
                                            }, null, 4)
                                          ])
                                        ]))
                                      }), 128))
                                    ]))
                                  : (_openBlock(), _createElementBlock("div", _hoisted_50, "本轮没有记录过滤原因（候选全部通过或列表为空）")),
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
                                _createElementVNode("header", _hoisted_51, [
                                  _cache[64] || (_cache[64] = _createElementVNode("div", null, [
                                    _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "操作记录"),
                                    _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "每次执行 / 选种 / 删种 / 保护的流水（含耗时）")
                                  ], -1)),
                                  _createVNode(_component_VBtn, {
                                    variant: "text",
                                    color: "primary",
                                    "prepend-icon": "mdi-refresh",
                                    onClick: _cache[8] || (_cache[8] = $event => (loadOperations(selectedTaskId.value)))
                                  }, {
                                    default: _withCtx(() => [...(_cache[63] || (_cache[63] = [
                                      _createTextVNode("刷新", -1)
                                    ]))]),
                                    _: 1
                                  })
                                ]),
                                _createElementVNode("div", _hoisted_52, [
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
                                          (record.duration == null && (record.items || []).length > 1)
                                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                                _createTextVNode(" · " + _toDisplayString((record.items || []).length) + " 个条目", 1)
                                              ], 64))
                                            : _createCommentVNode("", true)
                                        ]),
                                        (record.error_message)
                                          ? (_openBlock(), _createElementBlock("span", _hoisted_53, _toDisplayString(record.error_message), 1))
                                          : _createCommentVNode("", true)
                                      ])
                                    ]))
                                  }), 128)),
                                  (!(operationData.value.operations || []).length)
                                    ? (_openBlock(), _createElementBlock("div", _hoisted_54, "暂无操作记录"))
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
                            _createElementVNode("div", _hoisted_55, [
                              _createElementVNode("div", null, [
                                _cache[65] || (_cache[65] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "种子池", -1)),
                                _createElementVNode("div", _hoisted_56, [
                                  (poolView.value === 'candidates')
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                        _createTextVNode(" 待办队列 · 共 " + _toDisplayString(candidateData.value.total || 0) + " 个通过过滤 ", 1)
                                      ], 64))
                                    : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                        _createTextVNode(" 已托管：共 " + _toDisplayString(bonusData.value.torrent_count || 0) + " 个（黑盒：仅展示状态与进度） ", 1)
                                      ], 64))
                                ])
                              ]),
                              _createElementVNode("div", _hoisted_57, [
                                _createVNode(_component_VBtnToggle, {
                                  "model-value": poolView.value,
                                  mandatory: "",
                                  color: "primary",
                                  density: "compact",
                                  "onUpdate:modelValue": _cache[9] || (_cache[9] = value => (poolView.value = value))
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VBtn, {
                                      value: "candidates",
                                      "prepend-icon": "mdi-filter-variant"
                                    }, {
                                      default: _withCtx(() => [...(_cache[66] || (_cache[66] = [
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
                                }, 8, ["model-value"])
                              ])
                            ]),
                            (poolView.value === 'candidates')
                              ? (_openBlock(), _createBlock(_component_VSheet, {
                                  key: 0,
                                  tag: "section",
                                  class: "magicflow-panel app-surface-static"
                                }, {
                                  default: _withCtx(() => [
                                    _cache[68] || (_cache[68] = _createElementVNode("header", { class: "magicflow-panel__head" }, [
                                      _createElementVNode("div", null, [
                                        _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "候选排行"),
                                        _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "待办名次由站点魔力效率内部排序 · 仅供选种参考")
                                      ])
                                    ], -1)),
                                    _createElementVNode("ol", _hoisted_58, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList((candidateData.value.candidates || []).slice(0, 8), (candidate) => {
                                        return (_openBlock(), _createElementBlock("li", {
                                          key: candidate.hash
                                        }, [
                                          _createElementVNode("span", _hoisted_59, _toDisplayString(candidate.rank), 1),
                                          _createElementVNode("div", null, [
                                            _createElementVNode("strong", null, _toDisplayString(candidate.title || '未知种子'), 1),
                                            _createElementVNode("span", null, _toDisplayString(Number(candidate.size_gb || 0).toFixed(2)) + " GB · " + _toDisplayString(candidate.seeders) + " 做种 · " + _toDisplayString(Number(candidate.age_weeks || 0).toFixed(1)) + " 周", 1)
                                          ])
                                        ]))
                                      }), 128)),
                                      (!(candidateData.value.candidates || []).length)
                                        ? (_openBlock(), _createElementBlock("li", _hoisted_60, [...(_cache[67] || (_cache[67] = [
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
                                    _createElementVNode("header", _hoisted_61, [
                                      _createElementVNode("div", null, [
                                        _createElementVNode("div", _hoisted_62, [
                                          _cache[69] || (_cache[69] = _createElementVNode("span", { class: "text-subtitle-1 font-weight-medium" }, "托管种子", -1)),
                                          _createVNode(_component_VChip, {
                                            size: "x-small",
                                            variant: "tonal"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(bonusData.value.torrent_count || 0), 1)
                                            ]),
                                            _: 1
                                          })
                                        ]),
                                        _createElementVNode("div", _hoisted_63, " 共 " + _toDisplayString(bonusData.value.torrent_count || 0) + " 个 · 点击任意行查看详情 / 手动保留 / 删除 ", 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_64, [
                                        _createVNode(_component_VSelect, {
                                          modelValue: torrentStatusFilter.value,
                                          "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((torrentStatusFilter).value = $event)),
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
                                          "onUpdate:modelValue": _cache[11] || (_cache[11] = value => (torrentFilter.value = value))
                                        }, {
                                          default: _withCtx(() => [
                                            _createVNode(_component_VBtn, { value: "all" }, {
                                              default: _withCtx(() => [...(_cache[70] || (_cache[70] = [
                                                _createTextVNode("全部", -1)
                                              ]))]),
                                              _: 1
                                            }),
                                            _createVNode(_component_VBtn, { value: "protected" }, {
                                              default: _withCtx(() => [...(_cache[71] || (_cache[71] = [
                                                _createTextVNode("已保护", -1)
                                              ]))]),
                                              _: 1
                                            })
                                          ]),
                                          _: 1
                                        }, 8, ["model-value"])
                                      ])
                                    ]),
                                    _createVNode(_component_VDataTable, {
                                      class: "magicflow-torrent-table torrent-table-clickable",
                                      headers: torrentHeaders,
                                      items: sortedTorrents.value,
                                      loading: taskLoading.value,
                                      "items-per-page": 10,
                                      density: "comfortable",
                                      "onClick:row": onTorrentRowClick
                                    }, {
                                      "item.title": _withCtx(({ item }) => [
                                        _createElementVNode("div", _hoisted_65, [
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
                                          onClick: $event => (torrentAction(item, 'delete'))
                                        }, null, 8, ["onClick"])
                                      ]),
                                      "no-data": _withCtx(() => [...(_cache[72] || (_cache[72] = [
                                        _createElementVNode("div", { class: "magicflow-table-empty" }, "当前筛选下没有托管种子", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["items", "loading"]),
                                    _createElementVNode("div", _hoisted_66, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(sortedTorrents.value, (item) => {
                                        return (_openBlock(), _createElementBlock("article", {
                                          key: item.hash || item.title,
                                          class: "magicflow-mobile-torrent",
                                          onClick: $event => (openTorrentDetail(item))
                                        }, [
                                          _createElementVNode("div", _hoisted_68, [
                                            _createElementVNode("div", _hoisted_69, [
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
                                          _createElementVNode("div", _hoisted_70, [
                                            _createElementVNode("span", null, [
                                              _cache[73] || (_cache[73] = _createElementVNode("em", null, "大小", -1)),
                                              _createElementVNode("b", null, _toDisplayString(Number(item.size_gb || 0).toFixed(2)) + " GB", 1)
                                            ]),
                                            _createElementVNode("span", null, [
                                              _cache[74] || (_cache[74] = _createElementVNode("em", null, "上传量", -1)),
                                              _createElementVNode("b", null, _toDisplayString(_unref(formatBytes)(item.uploaded)), 1)
                                            ]),
                                            _createElementVNode("span", null, [
                                              _cache[75] || (_cache[75] = _createElementVNode("em", null, "分享率", -1)),
                                              _createElementVNode("b", null, _toDisplayString(Number(item.ratio || 0).toFixed(2)), 1)
                                            ])
                                          ]),
                                          _createElementVNode("div", _hoisted_71, [
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
                                              onClick: _withModifiers($event => (torrentAction(item, 'delete')), ["stop"])
                                            }, {
                                              default: _withCtx(() => [...(_cache[76] || (_cache[76] = [
                                                _createTextVNode("删除", -1)
                                              ]))]),
                                              _: 1
                                            }, 8, ["onClick"])
                                          ])
                                        ], 8, _hoisted_67))
                                      }), 128)),
                                      (!sortedTorrents.value.length)
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_72, "当前筛选下没有托管种子"))
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
                            _createElementVNode("div", _hoisted_73, [
                              _createVNode(_component_VSheet, {
                                tag: "section",
                                class: "magicflow-panel app-surface-static"
                              }, {
                                default: _withCtx(() => [
                                  _cache[106] || (_cache[106] = _createElementVNode("header", { class: "magicflow-panel__head" }, [
                                    _createElementVNode("div", null, [
                                      _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "任务规则"),
                                      _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "当前服务端生效配置")
                                    ])
                                  ], -1)),
                                  _createElementVNode("dl", _hoisted_74, [
                                    _createElementVNode("div", null, [
                                      _cache[77] || (_cache[77] = _createElementVNode("dt", null, "任务状态", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(selectedTask.value.enabled ? '启用' : '暂停'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[78] || (_cache[78] = _createElementVNode("dt", null, "站点", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(selectedTask.value.site_name), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[79] || (_cache[79] = _createElementVNode("dt", null, "下载器", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(selectedTask.value.downloader), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[80] || (_cache[80] = _createElementVNode("dt", null, "下载器标签", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(selectedTask.value.brush_tag || '未设置'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[81] || (_cache[81] = _createElementVNode("dt", null, "种子大小", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.size || '不限'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[82] || (_cache[82] = _createElementVNode("dt", null, "做种人数", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.seeder || '不限'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[83] || (_cache[83] = _createElementVNode("dt", null, "发布时间", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.pubtime ? `${taskConfig.value.pubtime} 分钟` : '不限'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[84] || (_cache[84] = _createElementVNode("dt", null, "排除 H&R", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.hr === 'yes' ? '是' : '否'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[85] || (_cache[85] = _createElementVNode("dt", null, "包含规则", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.include || '无'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[86] || (_cache[86] = _createElementVNode("dt", null, "排除规则", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.exclude || '无'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[87] || (_cache[87] = _createElementVNode("dt", null, "最短做种", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_seed_time ? `${taskConfig.value.min_seed_time} 小时` : '不限'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[88] || (_cache[88] = _createElementVNode("dt", null, "最低分享率", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(Number(taskConfig.value.min_ratio || 0).toFixed(2)), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[89] || (_cache[89] = _createElementVNode("dt", null, "保种体积", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.disk_size_gb ? `${taskConfig.value.disk_size_gb} GB` : '不限'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[90] || (_cache[90] = _createElementVNode("dt", null, "最低魔力", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.value.min_bonus_per_hour).toFixed(2)} /h`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[91] || (_cache[91] = _createElementVNode("dt", null, "最多保留", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_keep_torrents == null ? '自动 / 不限' : `${taskConfig.value.max_keep_torrents} 个`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[92] || (_cache[92] = _createElementVNode("dt", null, "单轮最多新增", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_add_per_run ?? 10) + " 个", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[93] || (_cache[93] = _createElementVNode("dt", null, "同时下载上限", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.max_download_concurrent ?? 10) + " 个", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[94] || (_cache[94] = _createElementVNode("dt", null, "每轮参评候选", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.top_n ?? 30) + " 个", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[95] || (_cache[95] = _createElementVNode("dt", null, "每轮翻页数", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.browse_pages ?? 3) + " 页", 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[96] || (_cache[96] = _createElementVNode("dt", null, "保护阈值", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.value.bonus_protect_threshold).toFixed(0)), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[97] || (_cache[97] = _createElementVNode("dt", null, "自动补种", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.refill_when_empty ? '开启' : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[98] || (_cache[98] = _createElementVNode("dt", null, "存量复用", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.reuse_existing ? (taskConfig.value.reuse_verify ? '开启（校验）' : '开启（跳过校验）') : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[99] || (_cache[99] = _createElementVNode("dt", null, "无进度清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_no_progress ? `开启（${taskConfig.value.no_progress_minutes ?? 30} 分钟）` : '关闭'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[100] || (_cache[100] = _createElementVNode("dt", null, "慢速清理", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.value.slow_progress_max_hours ?? 48}h 下不完即清）`), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[101] || (_cache[101] = _createElementVNode("dt", null, "自动恢复暂停", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.auto_resume_paused === false ? '关闭' : '开启'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[102] || (_cache[102] = _createElementVNode("dt", null, "公式 T0/N0", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_t0 ?? '默认') + " / " + _toDisplayString(taskConfig.value.bonus_n0 ?? '默认'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[103] || (_cache[103] = _createElementVNode("dt", null, "公式 B0/L", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_b0 ?? '默认') + " / " + _toDisplayString(taskConfig.value.bonus_l ?? '默认'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[104] || (_cache[104] = _createElementVNode("dt", null, "零魔权重", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(taskConfig.value.bonus_zero_weight ?? '默认'), 1)
                                    ]),
                                    _createElementVNode("div", null, [
                                      _cache[105] || (_cache[105] = _createElementVNode("dt", null, "保底魔力", -1)),
                                      _createElementVNode("dd", null, _toDisplayString(Number(taskConfig.value.min_bonus_to_keep || 0).toFixed(2)), 1)
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
                                  _cache[116] || (_cache[116] = _createElementVNode("header", { class: "magicflow-panel__head" }, [
                                    _createElementVNode("div", null, [
                                      _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "任务操作"),
                                      _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "以下操作只影响当前任务")
                                    ])
                                  ], -1)),
                                  _createElementVNode("div", _hoisted_75, [
                                    _createElementVNode("div", null, [
                                      _cache[108] || (_cache[108] = _createElementVNode("strong", null, "执行一次", -1)),
                                      _cache[109] || (_cache[109] = _createElementVNode("span", null, "立即按当前策略抓取候选并养护做种", -1)),
                                      _createVNode(_component_VBtn, {
                                        color: "primary",
                                        variant: "tonal",
                                        "prepend-icon": "mdi-sync",
                                        loading: saving.value,
                                        onClick: runOperation
                                      }, {
                                        default: _withCtx(() => [...(_cache[107] || (_cache[107] = [
                                          _createTextVNode(" 立即执行 ", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["loading"])
                                    ]),
                                    _createVNode(_component_VDivider),
                                    _createElementVNode("div", null, [
                                      _cache[111] || (_cache[111] = _createElementVNode("strong", null, "编辑任务", -1)),
                                      _cache[112] || (_cache[112] = _createElementVNode("span", null, "调整调度、魔力门槛与公式参数", -1)),
                                      _createVNode(_component_VBtn, {
                                        variant: "tonal",
                                        "prepend-icon": "mdi-pencil-outline",
                                        onClick: openEditTask
                                      }, {
                                        default: _withCtx(() => [...(_cache[110] || (_cache[110] = [
                                          _createTextVNode("编辑任务", -1)
                                        ]))]),
                                        _: 1
                                      })
                                    ]),
                                    _createVNode(_component_VDivider),
                                    _createElementVNode("div", null, [
                                      _cache[114] || (_cache[114] = _createElementVNode("strong", null, "删除任务", -1)),
                                      _cache[115] || (_cache[115] = _createElementVNode("span", null, "存在活跃种子时后端会拒绝删除，避免留下失管任务", -1)),
                                      _createVNode(_component_VBtn, {
                                        color: "error",
                                        variant: "tonal",
                                        "prepend-icon": "mdi-delete-outline",
                                        onClick: _cache[12] || (_cache[12] = $event => (deleteDialog.value = true))
                                      }, {
                                        default: _withCtx(() => [...(_cache[113] || (_cache[113] = [
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
      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((editorOpen).value = $event)),
      task: editorTask.value,
      sites: status.value.options.sites,
      downloaders: status.value.options.downloaders,
      saving: saving.value,
      onSave: saveTask
    }, null, 8, ["modelValue", "task", "sites", "downloaders", "saving"]),
    _createVNode(_component_VDialog, {
      modelValue: torrentDialog.value,
      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((torrentDialog).value = $event)),
      "max-width": "40rem"
    }, {
      default: _withCtx(() => [
        (activeTorrent.value)
          ? (_openBlock(), _createBlock(_component_VCard, {
              key: 0,
              class: "magicflow-dialog"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, { class: "text-wrap" }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(activeTorrent.value.title || '种子详情'), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardText, null, {
                  default: _withCtx(() => [
                    _createElementVNode("dl", _hoisted_76, [
                      _createElementVNode("div", null, [
                        _cache[117] || (_cache[117] = _createElementVNode("dt", null, "状态", -1)),
                        _createElementVNode("dd", null, [
                          _createVNode(_component_VChip, {
                            size: "small",
                            color: stateColor(activeTorrent.value.state),
                            variant: "tonal"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(stateLabel(activeTorrent.value.state)), 1)
                            ]),
                            _: 1
                          }, 8, ["color"])
                        ])
                      ]),
                      _createElementVNode("div", null, [
                        _cache[118] || (_cache[118] = _createElementVNode("dt", null, "下载进度", -1)),
                        _createElementVNode("dd", null, _toDisplayString((Number(activeTorrent.value.progress || 0) * 100).toFixed(1)) + "%", 1)
                      ]),
                      _createElementVNode("div", null, [
                        _cache[119] || (_cache[119] = _createElementVNode("dt", null, "大小", -1)),
                        _createElementVNode("dd", null, _toDisplayString(Number(activeTorrent.value.size_gb || 0).toFixed(2)) + " GB", 1)
                      ]),
                      _createElementVNode("div", null, [
                        _cache[120] || (_cache[120] = _createElementVNode("dt", null, "上传量", -1)),
                        _createElementVNode("dd", null, _toDisplayString(_unref(formatBytes)(activeTorrent.value.uploaded)), 1)
                      ]),
                      _createElementVNode("div", null, [
                        _cache[121] || (_cache[121] = _createElementVNode("dt", null, "分享率", -1)),
                        _createElementVNode("dd", null, _toDisplayString(Number(activeTorrent.value.ratio || 0).toFixed(2)), 1)
                      ]),
                      _createElementVNode("div", null, [
                        _cache[122] || (_cache[122] = _createElementVNode("dt", null, "手动保留", -1)),
                        _createElementVNode("dd", null, _toDisplayString(activeTorrent.value.is_protected ? '已保护' : '未保护'), 1)
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_77, "infohash：" + _toDisplayString(activeTorrent.value.hash), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardActions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_VBtn, {
                      variant: "tonal",
                      color: activeTorrent.value.is_protected ? 'grey' : 'primary',
                      "prepend-icon": activeTorrent.value.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline',
                      loading: saving.value,
                      onClick: _cache[15] || (_cache[15] = $event => (detailTorrentAction(activeTorrent.value.is_protected ? 'unprotect' : 'protect')))
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(activeTorrent.value.is_protected ? '取消保留' : '保留'), 1)
                      ]),
                      _: 1
                    }, 8, ["color", "prepend-icon", "loading"]),
                    _createVNode(_component_VBtn, {
                      color: "error",
                      variant: "tonal",
                      "prepend-icon": "mdi-delete-outline",
                      loading: saving.value,
                      onClick: _cache[16] || (_cache[16] = $event => (detailTorrentAction('delete')))
                    }, {
                      default: _withCtx(() => [...(_cache[123] || (_cache[123] = [
                        _createTextVNode("删除种子", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VBtn, {
                      variant: "text",
                      onClick: _cache[17] || (_cache[17] = $event => (torrentDialog.value = false))
                    }, {
                      default: _withCtx(() => [...(_cache[124] || (_cache[124] = [
                        _createTextVNode("关闭", -1)
                      ]))]),
                      _: 1
                    })
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
      modelValue: deleteDialog.value,
      "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((deleteDialog).value = $event)),
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
                  onClick: _cache[19] || (_cache[19] = $event => (deleteDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[125] || (_cache[125] = [
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
                  default: _withCtx(() => [...(_cache[126] || (_cache[126] = [
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
const MagicFlowWorkbench = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-75b20df2"]]);

export { MagicFlowWorkbench as M };
