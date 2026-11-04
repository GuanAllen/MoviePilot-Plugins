// TaskEditorDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './TaskEditorDialog.css'


import * as __vuetify from 'vuetify'

import * as __vue from 'vue'

const {
  Fragment: _Fragment$G,
  createBlock: _createBlock$K,
  createCommentVNode: _createCommentVNode$I,
  createElementBlock: _createElementBlock$H,
  createElementVNode: _createElementVNode$N,
  createTextVNode: _createTextVNode$M,
  createVNode: _createVNode$M,
  openBlock: _openBlock$N,
  renderList: _renderList$D,
  resolveComponent: _resolveComponent$N,
  toDisplayString: _toDisplayString$N,
  unref: _unref$m,
  withCtx: _withCtx$K,
  withModifiers: _withModifiers$4,
} = __vue

import AdvancedPanel from './taskeditor/AdvancedPanel.vue'
import BasePanel from './taskeditor/BasePanel.js'
import BrushPanel from './taskeditor/BrushPanel.vue'
import FormulaPanel from './taskeditor/FormulaPanel.vue'
import MagicPanel from './taskeditor/MagicPanel.vue'
import SelectionPanel from './taskeditor/SelectionPanel.vue'
import { cloneTask, formatBytes, normalizeTask, unwrapResponse } from '../utils.js'
import { createApi } from '../api/request.js'

const _hoisted_1$J = { class: "d-flex align-center mb-2" };
const _hoisted_2$H = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_3$F = { class: "d-flex align-center mb-2" };
const _hoisted_4$F = { class: "text-body-2 text-medium-emphasis" };

const {computed: computed$R,ref: ref$E,watch: watch$e} = __vue;

const {useDisplay} = __vuetify;

const SAVE_PATH_KEY = 'magicflow_save_paths';
const POOL_THRESHOLD = 0.8;

const _sfc_main$N = {
  __name: 'TaskEditorDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  task: { type: Object, default: () => ({}) },
  sites: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  defaultSavePath: { type: String, default: '' },
  savePaths: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
  api: { type: Object, default: null },
  // 保留兼容：已不再使用（★ 15.17.1：路径相对**插件域客户端** props.api，勿再拼 plugin/<id>）
  pluginBase: { type: String, default: 'plugin/MagicFlow' },
},
  emits: ['update:modelValue', 'save'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;
const display = useDisplay();
const formRef = ref$E(null);
const activeTab = ref$E('base');
const localTask = ref$E(cloneTask());

// 刷流模式：做种满设定天数即清理换新（轮转周期），不套用魔力门槛。
const isBrush = computed$R(() => localTask.value.task_type === 'brush');
const dialogTitle = computed$R(() => {
  const kind = isBrush.value ? '刷流任务' : '魔力任务';
  const full = localTask.value.id ? `编辑${kind}` : `新建${kind}`;
  // 手机端标题栏窄（还要放「保存任务」按钮）→ 用短标题，避免被截成「新建魔...」
  if (display.smAndDown.value) return localTask.value.id ? '编辑任务' : '新建任务'
  return full
});
// 编辑器标签页随类型切换：刷流隐藏「魔力托管/魔力公式」，改显「刷流运维」。
const editorTabs = computed$R(() =>
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
const siteName = computed$R(() => {
  const site = props.sites.find(item => Number(item.value ?? item.id) === Number(localTask.value.site_id));
  return site?.title || site?.name || '未选择'
});
const scheduleText = computed$R(() => localTask.value.cron_expression || `每 ${localTask.value.brush_interval || 5} 分钟`);
// 刷流「上传速率门槛」可选档（KB/s）：低于该平均速率即判「无上传」。
const uploadRateOptions = [
  { title: '温和 · 100 KB/s（≈ 60 MB / 10 分钟）', value: 100 },
  { title: '适中 · 200 KB/s（≈ 120 MB / 10 分钟，推荐）', value: 200 },
  { title: '激进 · 500 KB/s（≈ 300 MB / 10 分钟）', value: 500 },
  { title: '极限 · 1000 KB/s（1 MB/s，只留最热）', value: 1000 },
];
// 保存目录候选：**填过一次就记住**（localStorage）+ 已有任务用过的目录 + 设置里的默认目录 + 任务当前值。
// 用户手输过的目录会立刻落进 localStorage，下次新建/编辑就能从下拉里选到。
const savePathHistory = ref$E([]);
// 清理候选：去重 + **丢掉「别人的前缀」**（如 /vol3/1000/med 是 /vol3/1000/media 的前缀）
// —— 用户逐字打路径时 v-model 每敲一个字就变一次，不做这步会存一堆半截路径。
function cleanSavePaths(list) {
  const uniq = [];
  for (const raw of list || []) {
    const v = String(raw || '').trim();
    // 至少两层目录才算「一个目录」，顺手把历史里的垃圾（半截路径）清掉
    if (v && v.split('/').filter(Boolean).length >= 2 && !uniq.includes(v)) uniq.push(v);
  }
  // 丢掉「被更长的条目吃掉」的半截路径：
  //   /vol3/1000/m、/vol3/1000/med（没打完）→ 丢；/vol3/1000/（结尾斜杠）→ 丢
  //   但 /vol6/1000/movie 与 /vol6/1000/movie/刷流 属于「父子目录」→ 都留
  return uniq
    .filter(v => !uniq.some(o => o !== v && o.length > v.length && o.startsWith(v)
      && (v.endsWith('/') || o[v.length] !== '/')))
    .slice(0, 12)
}
function readSavePathHistory() {
  try {
    const raw = window.localStorage.getItem(SAVE_PATH_KEY);
    const list = raw ? JSON.parse(raw) : [];
    savePathHistory.value = cleanSavePaths(Array.isArray(list) ? list : []);
  } catch (error) {
    savePathHistory.value = [];
  }
}
// ★ 只在**输入完成**时才记（失焦 / 保存任务），绝不逐字记
function rememberSavePath(value) {
  const path = String(value || '').trim();
  if (!path || path.split('/').filter(Boolean).length < 2) return
  const list = cleanSavePaths([path, ...savePathHistory.value]);
  savePathHistory.value = list;
  try {
    window.localStorage.setItem(SAVE_PATH_KEY, JSON.stringify(list));
  } catch (error) {
    /* 隐私模式等场景忽略 */
  }
}
const savePathOptions = computed$R(() => {
  const set = new Set();
  for (const item of savePathHistory.value) set.add(item);
  for (const item of props.savePaths || []) if (item) set.add(String(item));
  if (props.defaultSavePath) set.add(props.defaultSavePath);
  if (localTask.value.save_path) set.add(localTask.value.save_path);
  return [...set]
});

// ★ 19.10.36：刷流/魔力任务保存目录必填（host 类任务不下载，留空合法）。
// 后端 create/update 已强制拒绝，这里提前在前端表单拦截，省一次来回。
const savePathRequired = computed$R(() =>
  ['brush', 'bonus'].includes(String(localTask.value.task_type || 'bonus').toLowerCase()),
);

// ★ 5.9.0 预设模板：用户「选类型就行」—— 模板只覆盖**程序可决定**的参数
//   （选种/清理/限速/调度/复用…）；站点 / 保存目录 / 目标 / 任务名 仍由用户决定。
// ★ 5.10.0/5.10.3 模板还会按**当前磁盘空间**自动设「最多占多少体积」：以 80% 为阈值（见 POOL_THRESHOLD），
//   并给一个**可拉的百分比**（拉条实时显示折合多少 GB）。
const TASK_PRESETS = [
  {
    key: 'brush',
    icon: 'mdi-upload-network-outline',
    title: '刷流',
    desc: '按上传潜力选种，做种满几天轮换；达标自动停',
    share: 1,
    patch: {
      task_type: 'brush',
      brush_seed_days: 2,
      brush_min_leechers: 1,
      upload_min_kbps: 200,
      except_subscribe: true,
      refill_when_empty: true,
      cleanup_no_progress: true,
      cleanup_slow_progress: true,
      purge_unfree_incomplete: true,
      auto_resume_paused: true,
      delete_files: true,
      ti_source: 'publish',
    },
  },
  {
    key: 'bonus',
    icon: 'mdi-star-four-points-outline',
    title: '刷魔力',
    desc: '挂种产出魔力最大化',
    share: 1,
    patch: {
      task_type: 'bonus',
      except_subscribe: true,
      refill_when_empty: true,
      cleanup_no_progress: true,
      cleanup_slow_progress: true,
      purge_unfree_incomplete: true,
      auto_resume_paused: true,
      delete_files: true,
      ti_source: 'publish',
    },
  },
  {
    key: 'exam',
    icon: 'mdi-school-outline',
    title: '考核冲刺',
    desc: '新站考核期：抢热门免费种攒上传，快转速换',
    share: 1,
    patch: {
      task_type: 'brush',
      brush_seed_days: 1,
      brush_min_leechers: 2,
      upload_min_kbps: 300,
      upload_idle_minutes: 30,
      brush_grace_minutes: 15,
      rotate_upload_gb: null,
      except_subscribe: true,
      refill_when_empty: true,
      max_add_per_run: 8,
      cleanup_no_progress: true,
      cleanup_slow_progress: false,
      purge_unfree_incomplete: true,
      auto_resume_paused: true,
      delete_files: true,
      ti_source: 'publish',
    },
  },
  {
    key: 'keep',
    icon: 'mdi-shield-outline',
    title: '轻量保种',
    desc: '少占盘：只复用本机资源，尽量不新增下载',
    share: 0.25,
    patch: {
      task_type: 'bonus',
      max_add_per_run: 3,
      top_n: 20,
      browse_pages: 1,
      except_subscribe: true,
      refill_when_empty: false,
      cleanup_no_progress: true,
      cleanup_slow_progress: true,
      purge_unfree_incomplete: true,
      auto_resume_paused: true,
      delete_files: true,
      ti_source: 'publish',
    },
  },
  {
    key: 'custom',
    icon: 'mdi-tune-variant',
    title: '自定义',
    desc: '所有参数自己来（展开全部标签页）',
    share: 0,
    patch: {},
  },
];
const presetKey = ref$E('bonus');
const simpleMode = computed$R(() => presetKey.value !== 'custom');
const presetInfo = computed$R(() => TASK_PRESETS.find(p => p.key === presetKey.value) || TASK_PRESETS[1]);

// ★ F2：反推该任务当前命中哪个模板 —— 逐个比对 patch 的每个键，全等才算命中；
//   一个键对不上就说明用户手改过（或历史遗留值），判定为 custom，避免「谎报身份」。
//   注意：patch 里不含 disk_size_gb（它由磁盘空间单独回填），所以无需排除任何键。
function detectPresetKey(task) {
  for (const p of TASK_PRESETS) {
    if (p.key === 'custom') continue
    if (p.patch.task_type !== task.task_type) continue
    if (Object.keys(p.patch).every(k => p.patch[k] === task[k])) return p.key
  }
  return 'custom'
}
// 磁盘状态（**按目录分盘**，只看任务自己那块盘；80% 阈值 → 本任务可占体积）
// ★ 不能用 MP 仪表板的「本地存储」：那是把多个目录加起来的总数（例如 /movie + /media），
//   任务写不到别的池里，拿总和算阈值会严重高估。
const pool = ref$E(null);
const poolError = ref$E('');
const poolLoading = ref$E(false);
async function loadPool() {
  if (!props.api) {
    poolError.value = '未接入宿主 API，无法读取磁盘空间';
    return
  }
  poolLoading.value = true;
  poolError.value = '';
  try {
    const savePath = String(localTask.value.save_path || props.defaultSavePath || '').trim();
    const query = `?path=${encodeURIComponent(savePath)}`;
    // ★ 15.17.1 修复：`props.api` 是**插件域客户端**（createApi，路径相对插件基址，内部已拼 `plugin/<id>/`）。
    //   原来这里又拼了一次 `pluginBase` → `plugin/MagicFlow/plugin/MagicFlow/pool` → 404 Not Found
    //   （新建任务弹窗每次都报「Not Found」）。
    const raw = await props.api.get(`pool${query}`);
    const data = unwrapResponse(raw) || {};
    if (!data.total) throw new Error('empty')
    pool.value = {
      name: data.name || '',
      path: data.path || '',
      total_gb: Number(data.total) / 1024 ** 3,
      used_gb: Number(data.used) / 1024 ** 3,
      pct: Number(data.pct) || 0,
      budget_gb: Number(data.budget_gb) || 0,
      pools: Array.isArray(data.pools) ? data.pools : [],
    };
    // 磁盘读得快时，把体积上限回填给当前模板（自定义模式不碰用户手填值）
    if (simpleMode.value && poolBudgetGb.value > 0) localTask.value.disk_size_gb = poolBudgetGb.value;
  } catch (error) {
    pool.value = null;
    poolError.value = '磁盘空间读取失败';
  } finally {
    poolLoading.value = false;
  }
}
const poolOver = computed$R(() => !!pool.value && pool.value.pct >= POOL_THRESHOLD * 100);
// 可拉的百分比：占「磁盘剩余可用空间（到 80% 阈值）」的比例（0~100），拉条实时显示折合 GB
const poolPct = ref$E(100);
const poolBudgetGb = computed$R(() => {
  if (!pool.value) return 0
  return Math.round(pool.value.budget_gb * (Number(poolPct.value) || 0) / 100 * 10) / 10
});
const poolBudgetText = computed$R(() => (poolBudgetGb.value > 0 ? `${poolBudgetGb.value} GB` : '不限'));
const poolFreeText = computed$R(() => (pool.value ? formatBytes(pool.value.budget_gb * 1024 ** 3) : '—'));
const presetPatchCount = computed$R(() => Object.keys(presetInfo.value.patch || {}).length + (poolBudgetGb.value > 0 ? 1 : 0));
// ★ F3（19.10.6）：套用前先 diff —— 只把「会被覆盖、且当前值既不等于新模板值、也不等于旧模板值」
//   的字段算作用户手调过。点同一张卡且没手改时差异为空 → 直接套用、不打扰。
//   旧实现 `Object.assign` 不比对、不问，用户把「每轮最多添加」调成 5 后点一下别的模板就静默抹掉。
const presetConfirm = ref$E({ open: false, key: '', count: 0 });
// 选模板 → 只覆盖「程序可决定」的参数（用户已填的站点/目录/目标/名称不动）
function applyPreset(key) {
  const p = TASK_PRESETS.find(x => x.key === key);
  if (!p) return
  const prev = TASK_PRESETS.find(x => x.key === presetKey.value);
  const dirty = Object.keys(p.patch || {}).filter(
    k => localTask.value[k] !== p.patch[k] && (!prev || localTask.value[k] !== prev.patch[k]),
  );
  if (dirty.length) {
    presetConfirm.value = { open: true, key, count: dirty.length };
    return
  }
  doApplyPreset(key);
}

function doApplyPreset(key) {
  presetConfirm.value = { open: false, key: '', count: 0 };
  presetKey.value = key;
  const p = TASK_PRESETS.find(x => x.key === key);
  if (p && Object.keys(p.patch || {}).length) Object.assign(localTask.value, p.patch);
  // 体积上限：按磁盘 80% 阈值 × 拉条比例（轻量保种默认 25%），已超阈则不设
  if (p && Number(p.share)) poolPct.value = Math.round(Number(p.share) * 100);
  else if (p && p.key === 'custom') poolPct.value = poolPct.value || 100;
  const budget = poolBudgetGb.value;
  if (budget > 0) localTask.value.disk_size_gb = budget;
  autoFillName(false);
  autoFillTag();
  // ★ F4（19.10.2）：简单模式下只剩「基础与调度」一个 VWindowItem，
  //   切模板后 activeTab 必须回到 base，否则 Vuetify 的 forceMandatoryValue()
  //   在 unregister() 里「先判定、后 splice」，救不了「选中项被 v-if 移除」这一路
  //   → 所有 VWindowItem 全隐藏，内容区整片空白。
  //   非 custom 时只剩 base（必须回），custom 时全部标签都在（回 base 无害），合并即无条件。
  activeTab.value = 'base';
}
// 任务名自动填「站点·模板名」；换站点/换模板都会跟着变（用户手改过才不动）
const autoNameSet = computed$R(() => {
  const set = new Set();
  for (const site of props.sites) {
    const sname = site?.title || site?.name || '';
    if (!sname) continue
    for (const p of TASK_PRESETS) set.add(`${sname}·${p.title}`);
  }
  return set
});
function autoFillName(force = true) {
  const site = props.sites.find(item => Number(item.value ?? item.id) === Number(localTask.value.site_id));
  const sname = site?.title || site?.name || '';
  if (!sname) return
  const cur = String(localTask.value.name || '').trim();
  const wasAuto = !cur || autoNameSet.value.has(cur);
  if (force || wasAuto) localTask.value.name = `${sname}·${presetInfo.value.title}`;
}
// ★ 下载器标签：和任务名同规矩 —— **推荐默认值 + 强制统一**。
//   永远按「站点 + 任务类型」派生（刷流任务 → 刷流，其余 → 魔力）；
//   字段里展示的就是推荐值，手填了不统一的内容也会在换站点/换类型/保存时被纠正。
const tagState = computed$R(() => (String(localTask.value.task_type || 'bonus').toLowerCase() === 'brush' ? '刷流' : '魔力'));
// siteName 已在上面定义（未选择站点时为「未选择」）
const autoTag = computed$R(() => {
  const n = String(siteName.value || '').trim();
  return n && n !== '未选择' ? `魔流-${n}-${tagState.value}` : ''
});
function autoFillTag() {
  if (autoTag.value) localTask.value.brush_tag = autoTag.value;
}
function onPctChange() {
  if (simpleMode.value && poolBudgetGb.value > 0) localTask.value.disk_size_gb = poolBudgetGb.value;
}
function onSiteChange() {
  autoFillName(false);
  autoFillTag();
}
function onSavePathChange() {
  loadPool();
}

// 每次打开弹窗都从服务端任务快照重新创建本地草稿。
watch$e(
  () => props.modelValue,
  visible => {
    if (!visible) return
    localTask.value = cloneTask(props.task);
    activeTab.value = 'base';
    presetKey.value = detectPresetKey(localTask.value);
    readSavePathHistory();
    rememberSavePath(localTask.value.save_path);
    autoFillTag();
    // ★ 新建任务时 downloader 为空则自动选第一台（避免必填项空值导致 validate 静默失败）
    if (!localTask.value.downloader && props.downloaders?.length) {
      localTask.value.downloader = props.downloaders[0].value || props.downloaders[0].title || '';
    }
    pool.value = null;
    loadPool();
  },
);

// 切换任务类型时，若当前标签在新类型下不存在，回到「基础与调度」。
// ★ 不再回写 presetKey：task_type 只可能由模板 patch 写入（界面没有任何手动改类型的控件），
//   回写会把 exam/keep 这类「模板名 ≠ 类型名」的选择顶掉（F1），也会顶掉开档时判定的 custom（F2）。
watch$e(
  () => localTask.value.task_type,
  () => {
    autoFillTag();
    if (!editorTabs.value.some(tab => tab.value === activeTab.value)) activeTab.value = 'base';
  },
);

// 关闭编辑器并丢弃尚未保存的草稿。
function closeDialog() {
  emit('update:modelValue', false);
}

// 表单校验失败的提示（避免 validate() 静默 return 导致「点了没反应」）
const formError = ref$E('');

// 未填「任务目标」时的提醒弹窗
const goalWarning = ref$E(false);

// 是否已填写有效的任务目标（>0）—— 刷流看 download_target_gb（上传量 GB），刷魔力看 goal_value（魔力值）
function hasGoal() {
  const t = String(localTask.value.task_type || 'bonus').toLowerCase();
  const v = t === 'brush' ? localTask.value.download_target_gb : localTask.value.goal_value;
  return !(v === '' || v === null || v === undefined) && Number(v) > 0
}

// 校验必填项后提交标准化任务数据；未填任务目标先弹窗提醒。
async function saveTask() {
  formError.value = '';
  const result = await formRef.value?.validate();
  if (result && !result.valid) {
    formError.value = '请检查标红的必填项（站点 / 任务名 / 下载器 / 保存目录）后再保存';
    return
  }
  if (!hasGoal()) {
    goalWarning.value = true;
    return
  }
  rememberSavePath(localTask.value.save_path);
  emit('save', normalizeTask(localTask.value));
}

// 确认「仍然保存」（不带目标）
function confirmSaveWithoutGoal() {
  goalWarning.value = false;
  rememberSavePath(localTask.value.save_path);
  emit('save', normalizeTask(localTask.value));
}

return (_ctx, _cache) => {
  const _component_VToolbarTitle = _resolveComponent$N("VToolbarTitle");
  const _component_VChip = _resolveComponent$N("VChip");
  const _component_VSpacer = _resolveComponent$N("VSpacer");
  const _component_VBtn = _resolveComponent$N("VBtn");
  const _component_VToolbar = _resolveComponent$N("VToolbar");
  const _component_VDivider = _resolveComponent$N("VDivider");
  const _component_VAlert = _resolveComponent$N("VAlert");
  const _component_VTab = _resolveComponent$N("VTab");
  const _component_VTabs = _resolveComponent$N("VTabs");
  const _component_VWindowItem = _resolveComponent$N("VWindowItem");
  const _component_VWindow = _resolveComponent$N("VWindow");
  const _component_VForm = _resolveComponent$N("VForm");
  const _component_VCardText = _resolveComponent$N("VCardText");
  const _component_VCard = _resolveComponent$N("VCard");
  const _component_VIcon = _resolveComponent$N("VIcon");
  const _component_VCardActions = _resolveComponent$N("VCardActions");
  const _component_VDialog = _resolveComponent$N("VDialog");

  return (_openBlock$N(), _createBlock$K(_component_VDialog, {
    "model-value": __props.modelValue,
    scrollable: "",
    fullscreen: _unref$m(display).smAndDown.value,
    "max-width": "74rem",
    "onUpdate:modelValue": _cache[89] || (_cache[89] = value => emit('update:modelValue', value))
  }, {
    default: _withCtx$K(() => [
      _createVNode$M(_component_VCard, { class: "magicflow-editor" }, {
        default: _withCtx$K(() => [
          _createVNode$M(_component_VToolbar, {
            color: "transparent",
            density: "comfortable",
            class: "magicflow-editor__toolbar"
          }, {
            default: _withCtx$K(() => [
              _createVNode$M(_component_VToolbarTitle, null, {
                default: _withCtx$K(() => [
                  _createTextVNode$M(_toDisplayString$N(dialogTitle.value), 1)
                ]),
                _: 1
              }),
              (localTask.value.id)
                ? (_openBlock$N(), _createBlock$K(_component_VChip, {
                    key: 0,
                    size: "small",
                    variant: "tonal",
                    class: "mr-2"
                  }, {
                    default: _withCtx$K(() => [
                      _createTextVNode$M(_toDisplayString$N(siteName.value), 1)
                    ]),
                    _: 1
                  }))
                : _createCommentVNode$I("", true),
              _createVNode$M(_component_VSpacer),
              _createVNode$M(_component_VBtn, {
                color: "primary",
                variant: "flat",
                "prepend-icon": "mdi-content-save",
                loading: __props.saving,
                onClick: saveTask
              }, {
                default: _withCtx$K(() => [...(_cache[90] || (_cache[90] = [
                  _createTextVNode$M(" 保存任务 ", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              _createVNode$M(_component_VBtn, {
                icon: "mdi-close",
                variant: "text",
                "aria-label": "关闭",
                onClick: closeDialog
              })
            ]),
            _: 1
          }),
          _createVNode$M(_component_VDivider),
          _createVNode$M(_component_VCardText, { class: "magicflow-editor__body" }, {
            default: _withCtx$K(() => [
              (formError.value)
                ? (_openBlock$N(), _createBlock$K(_component_VAlert, {
                    key: 0,
                    type: "error",
                    variant: "tonal",
                    closable: "",
                    class: "mb-3",
                    "onClick:close": _cache[0] || (_cache[0] = $event => (formError.value = ''))
                  }, {
                    default: _withCtx$K(() => [
                      _createTextVNode$M(_toDisplayString$N(formError.value), 1)
                    ]),
                    _: 1
                  }))
                : _createCommentVNode$I("", true),
              _createVNode$M(_component_VForm, {
                ref_key: "formRef",
                ref: formRef,
                class: "magicflow-editor__form",
                onSubmit: _withModifiers$4(saveTask, ["prevent"])
              }, {
                default: _withCtx$K(() => [
                  (!simpleMode.value)
                    ? (_openBlock$N(), _createBlock$K(_component_VTabs, {
                        key: 0,
                        modelValue: activeTab.value,
                        "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((activeTab).value = $event)),
                        direction: _unref$m(display).mdAndUp.value ? 'vertical' : 'horizontal',
                        color: "primary",
                        class: "magicflow-editor__tabs"
                      }, {
                        default: _withCtx$K(() => [
                          (_openBlock$N(true), _createElementBlock$H(_Fragment$G, null, _renderList$D(editorTabs.value, (tab) => {
                            return (_openBlock$N(), _createBlock$K(_component_VTab, {
                              key: tab.value,
                              value: tab.value,
                              "prepend-icon": tab.icon
                            }, {
                              default: _withCtx$K(() => [
                                _createTextVNode$M(_toDisplayString$N(tab.label), 1)
                              ]),
                              _: 2
                            }, 1032, ["value", "prepend-icon"]))
                          }), 128))
                        ]),
                        _: 1
                      }, 8, ["modelValue", "direction"]))
                    : _createCommentVNode$I("", true),
                  (!simpleMode.value)
                    ? (_openBlock$N(), _createBlock$K(_component_VDivider, {
                        key: 1,
                        vertical: _unref$m(display).mdAndUp.value
                      }, null, 8, ["vertical"]))
                    : _createCommentVNode$I("", true),
                  _createVNode$M(_component_VWindow, {
                    modelValue: activeTab.value,
                    "onUpdate:modelValue": _cache[83] || (_cache[83] = $event => ((activeTab).value = $event)),
                    touch: false,
                    class: "magicflow-editor__window"
                  }, {
                    default: _withCtx$K(() => [
                      _createVNode$M(_component_VWindowItem, { value: "base" }, {
                        default: _withCtx$K(() => [
                          _createVNode$M(BasePanel, {
                            "site-id": localTask.value.site_id,
                            "onUpdate:siteId": _cache[2] || (_cache[2] = $event => ((localTask.value.site_id) = $event)),
                            name: localTask.value.name,
                            "onUpdate:name": _cache[3] || (_cache[3] = $event => ((localTask.value.name) = $event)),
                            downloader: localTask.value.downloader,
                            "onUpdate:downloader": _cache[4] || (_cache[4] = $event => ((localTask.value.downloader) = $event)),
                            "brush-tag": localTask.value.brush_tag,
                            "onUpdate:brushTag": _cache[5] || (_cache[5] = $event => ((localTask.value.brush_tag) = $event)),
                            "save-path": localTask.value.save_path,
                            "onUpdate:savePath": _cache[6] || (_cache[6] = $event => ((localTask.value.save_path) = $event)),
                            enabled: localTask.value.enabled,
                            "onUpdate:enabled": _cache[7] || (_cache[7] = $event => ((localTask.value.enabled) = $event)),
                            "rss-support": localTask.value.rss_support,
                            "onUpdate:rssSupport": _cache[8] || (_cache[8] = $event => ((localTask.value.rss_support) = $event)),
                            "brush-interval": localTask.value.brush_interval,
                            "onUpdate:brushInterval": _cache[9] || (_cache[9] = $event => ((localTask.value.brush_interval) = $event)),
                            "check-interval": localTask.value.check_interval,
                            "onUpdate:checkInterval": _cache[10] || (_cache[10] = $event => ((localTask.value.check_interval) = $event)),
                            "cron-expression": localTask.value.cron_expression,
                            "onUpdate:cronExpression": _cache[11] || (_cache[11] = $event => ((localTask.value.cron_expression) = $event)),
                            "active-time-range": localTask.value.active_time_range,
                            "onUpdate:activeTimeRange": _cache[12] || (_cache[12] = $event => ((localTask.value.active_time_range) = $event)),
                            "goal-value": localTask.value.goal_value,
                            "onUpdate:goalValue": _cache[13] || (_cache[13] = $event => ((localTask.value.goal_value) = $event)),
                            "pool-pct": poolPct.value,
                            "onUpdate:poolPct": _cache[14] || (_cache[14] = $event => ((poolPct).value = $event)),
                            presets: TASK_PRESETS,
                            "preset-key": presetKey.value,
                            "simple-mode": simpleMode.value,
                            "preset-patch-count": presetPatchCount.value,
                            sites: __props.sites,
                            downloaders: __props.downloaders,
                            "auto-tag": autoTag.value,
                            "save-path-options": savePathOptions.value,
                            pool: pool.value,
                            "pool-over": poolOver.value,
                            "pool-error": poolError.value,
                            "pool-loading": poolLoading.value,
                            "pool-free-text": poolFreeText.value,
                            "pool-budget-text": poolBudgetText.value,
                            "schedule-text": scheduleText.value,
                            "is-brush": isBrush.value,
                            "save-path-required": savePathRequired.value,
                            onApplyPreset: applyPreset,
                            onSiteChange: onSiteChange,
                            onSavePathChange: onSavePathChange,
                            onRememberSavePath: rememberSavePath,
                            onLoadPool: loadPool,
                            onPctChange: onPctChange
                          }, null, 8, ["site-id", "name", "downloader", "brush-tag", "save-path", "enabled", "rss-support", "brush-interval", "check-interval", "cron-expression", "active-time-range", "goal-value", "pool-pct", "preset-key", "simple-mode", "preset-patch-count", "sites", "downloaders", "auto-tag", "save-path-options", "pool", "pool-over", "pool-error", "pool-loading", "pool-free-text", "pool-budget-text", "schedule-text", "is-brush", "save-path-required"])
                        ]),
                        _: 1
                      }),
                      (!simpleMode.value)
                        ? (_openBlock$N(), _createBlock$K(_component_VWindowItem, {
                            key: 0,
                            value: "brush"
                          }, {
                            default: _withCtx$K(() => [
                              _createVNode$M(BrushPanel, {
                                brushSeedDays: localTask.value.brush_seed_days,
                                "onUpdate:brushSeedDays": _cache[15] || (_cache[15] = $event => ((localTask.value.brush_seed_days) = $event)),
                                brushMinLeechers: localTask.value.brush_min_leechers,
                                "onUpdate:brushMinLeechers": _cache[16] || (_cache[16] = $event => ((localTask.value.brush_min_leechers) = $event)),
                                rotateUploadGb: localTask.value.rotate_upload_gb,
                                "onUpdate:rotateUploadGb": _cache[17] || (_cache[17] = $event => ((localTask.value.rotate_upload_gb) = $event)),
                                rotateRatio: localTask.value.rotate_ratio,
                                "onUpdate:rotateRatio": _cache[18] || (_cache[18] = $event => ((localTask.value.rotate_ratio) = $event)),
                                exceptSubscribe: localTask.value.except_subscribe,
                                "onUpdate:exceptSubscribe": _cache[19] || (_cache[19] = $event => ((localTask.value.except_subscribe) = $event)),
                                uploadMinKbps: localTask.value.upload_min_kbps,
                                "onUpdate:uploadMinKbps": _cache[20] || (_cache[20] = $event => ((localTask.value.upload_min_kbps) = $event)),
                                uploadIdleMinutes: localTask.value.upload_idle_minutes,
                                "onUpdate:uploadIdleMinutes": _cache[21] || (_cache[21] = $event => ((localTask.value.upload_idle_minutes) = $event)),
                                brushGraceMinutes: localTask.value.brush_grace_minutes,
                                "onUpdate:brushGraceMinutes": _cache[22] || (_cache[22] = $event => ((localTask.value.brush_grace_minutes) = $event)),
                                maxAddPerRun: localTask.value.max_add_per_run,
                                "onUpdate:maxAddPerRun": _cache[23] || (_cache[23] = $event => ((localTask.value.max_add_per_run) = $event)),
                                maxDownloadConcurrent: localTask.value.max_download_concurrent,
                                "onUpdate:maxDownloadConcurrent": _cache[24] || (_cache[24] = $event => ((localTask.value.max_download_concurrent) = $event)),
                                topN: localTask.value.top_n,
                                "onUpdate:topN": _cache[25] || (_cache[25] = $event => ((localTask.value.top_n) = $event)),
                                browsePages: localTask.value.browse_pages,
                                "onUpdate:browsePages": _cache[26] || (_cache[26] = $event => ((localTask.value.browse_pages) = $event)),
                                refillWhenEmpty: localTask.value.refill_when_empty,
                                "onUpdate:refillWhenEmpty": _cache[27] || (_cache[27] = $event => ((localTask.value.refill_when_empty) = $event)),
                                cleanupNoProgress: localTask.value.cleanup_no_progress,
                                "onUpdate:cleanupNoProgress": _cache[28] || (_cache[28] = $event => ((localTask.value.cleanup_no_progress) = $event)),
                                cleanupSlowProgress: localTask.value.cleanup_slow_progress,
                                "onUpdate:cleanupSlowProgress": _cache[29] || (_cache[29] = $event => ((localTask.value.cleanup_slow_progress) = $event)),
                                purgeUnfreeIncomplete: localTask.value.purge_unfree_incomplete,
                                "onUpdate:purgeUnfreeIncomplete": _cache[30] || (_cache[30] = $event => ((localTask.value.purge_unfree_incomplete) = $event)),
                                autoResumePaused: localTask.value.auto_resume_paused,
                                "onUpdate:autoResumePaused": _cache[31] || (_cache[31] = $event => ((localTask.value.auto_resume_paused) = $event)),
                                deleteFiles: localTask.value.delete_files,
                                "onUpdate:deleteFiles": _cache[32] || (_cache[32] = $event => ((localTask.value.delete_files) = $event)),
                                deleteExceptTags: localTask.value.delete_except_tags,
                                "onUpdate:deleteExceptTags": _cache[33] || (_cache[33] = $event => ((localTask.value.delete_except_tags) = $event)),
                                noProgressMinutes: localTask.value.no_progress_minutes,
                                "onUpdate:noProgressMinutes": _cache[34] || (_cache[34] = $event => ((localTask.value.no_progress_minutes) = $event)),
                                seenCooldownHours: localTask.value.seen_cooldown_hours,
                                "onUpdate:seenCooldownHours": _cache[35] || (_cache[35] = $event => ((localTask.value.seen_cooldown_hours) = $event)),
                                slowProgressGraceMinutes: localTask.value.slow_progress_grace_minutes,
                                "onUpdate:slowProgressGraceMinutes": _cache[36] || (_cache[36] = $event => ((localTask.value.slow_progress_grace_minutes) = $event)),
                                slowProgressMaxHours: localTask.value.slow_progress_max_hours,
                                "onUpdate:slowProgressMaxHours": _cache[37] || (_cache[37] = $event => ((localTask.value.slow_progress_max_hours) = $event)),
                                "upload-rate-options": uploadRateOptions
                              }, null, 8, ["brushSeedDays", "brushMinLeechers", "rotateUploadGb", "rotateRatio", "exceptSubscribe", "uploadMinKbps", "uploadIdleMinutes", "brushGraceMinutes", "maxAddPerRun", "maxDownloadConcurrent", "topN", "browsePages", "refillWhenEmpty", "cleanupNoProgress", "cleanupSlowProgress", "purgeUnfreeIncomplete", "autoResumePaused", "deleteFiles", "deleteExceptTags", "noProgressMinutes", "seenCooldownHours", "slowProgressGraceMinutes", "slowProgressMaxHours"])
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode$I("", true),
                      (!simpleMode.value && !isBrush.value)
                        ? (_openBlock$N(), _createBlock$K(_component_VWindowItem, {
                            key: 1,
                            value: "magic"
                          }, {
                            default: _withCtx$K(() => [
                              _createVNode$M(MagicPanel, {
                                minBonusPerHour: localTask.value.min_bonus_per_hour,
                                "onUpdate:minBonusPerHour": _cache[38] || (_cache[38] = $event => ((localTask.value.min_bonus_per_hour) = $event)),
                                diskSizeGb: localTask.value.disk_size_gb,
                                "onUpdate:diskSizeGb": _cache[39] || (_cache[39] = $event => ((localTask.value.disk_size_gb) = $event)),
                                maxKeepTorrents: localTask.value.max_keep_torrents,
                                "onUpdate:maxKeepTorrents": _cache[40] || (_cache[40] = $event => ((localTask.value.max_keep_torrents) = $event)),
                                maxAddPerRun: localTask.value.max_add_per_run,
                                "onUpdate:maxAddPerRun": _cache[41] || (_cache[41] = $event => ((localTask.value.max_add_per_run) = $event)),
                                maxDownloadConcurrent: localTask.value.max_download_concurrent,
                                "onUpdate:maxDownloadConcurrent": _cache[42] || (_cache[42] = $event => ((localTask.value.max_download_concurrent) = $event)),
                                topN: localTask.value.top_n,
                                "onUpdate:topN": _cache[43] || (_cache[43] = $event => ((localTask.value.top_n) = $event)),
                                browsePages: localTask.value.browse_pages,
                                "onUpdate:browsePages": _cache[44] || (_cache[44] = $event => ((localTask.value.browse_pages) = $event)),
                                bonusProtectThreshold: localTask.value.bonus_protect_threshold,
                                "onUpdate:bonusProtectThreshold": _cache[45] || (_cache[45] = $event => ((localTask.value.bonus_protect_threshold) = $event)),
                                minBonusToKeep: localTask.value.min_bonus_to_keep,
                                "onUpdate:minBonusToKeep": _cache[46] || (_cache[46] = $event => ((localTask.value.min_bonus_to_keep) = $event)),
                                refillWhenEmpty: localTask.value.refill_when_empty,
                                "onUpdate:refillWhenEmpty": _cache[47] || (_cache[47] = $event => ((localTask.value.refill_when_empty) = $event)),
                                cleanupNoProgress: localTask.value.cleanup_no_progress,
                                "onUpdate:cleanupNoProgress": _cache[48] || (_cache[48] = $event => ((localTask.value.cleanup_no_progress) = $event)),
                                cleanupSlowProgress: localTask.value.cleanup_slow_progress,
                                "onUpdate:cleanupSlowProgress": _cache[49] || (_cache[49] = $event => ((localTask.value.cleanup_slow_progress) = $event)),
                                purgeUnfreeIncomplete: localTask.value.purge_unfree_incomplete,
                                "onUpdate:purgeUnfreeIncomplete": _cache[50] || (_cache[50] = $event => ((localTask.value.purge_unfree_incomplete) = $event)),
                                autoResumePaused: localTask.value.auto_resume_paused,
                                "onUpdate:autoResumePaused": _cache[51] || (_cache[51] = $event => ((localTask.value.auto_resume_paused) = $event)),
                                tiSource: localTask.value.ti_source,
                                "onUpdate:tiSource": _cache[52] || (_cache[52] = $event => ((localTask.value.ti_source) = $event)),
                                noProgressMinutes: localTask.value.no_progress_minutes,
                                "onUpdate:noProgressMinutes": _cache[53] || (_cache[53] = $event => ((localTask.value.no_progress_minutes) = $event)),
                                seenCooldownHours: localTask.value.seen_cooldown_hours,
                                "onUpdate:seenCooldownHours": _cache[54] || (_cache[54] = $event => ((localTask.value.seen_cooldown_hours) = $event)),
                                slowProgressGraceMinutes: localTask.value.slow_progress_grace_minutes,
                                "onUpdate:slowProgressGraceMinutes": _cache[55] || (_cache[55] = $event => ((localTask.value.slow_progress_grace_minutes) = $event)),
                                slowProgressMaxHours: localTask.value.slow_progress_max_hours,
                                "onUpdate:slowProgressMaxHours": _cache[56] || (_cache[56] = $event => ((localTask.value.slow_progress_max_hours) = $event)),
                                minSeedTime: localTask.value.min_seed_time,
                                "onUpdate:minSeedTime": _cache[57] || (_cache[57] = $event => ((localTask.value.min_seed_time) = $event)),
                                minRatio: localTask.value.min_ratio,
                                "onUpdate:minRatio": _cache[58] || (_cache[58] = $event => ((localTask.value.min_ratio) = $event)),
                                deleteFiles: localTask.value.delete_files,
                                "onUpdate:deleteFiles": _cache[59] || (_cache[59] = $event => ((localTask.value.delete_files) = $event)),
                                deleteExceptTags: localTask.value.delete_except_tags,
                                "onUpdate:deleteExceptTags": _cache[60] || (_cache[60] = $event => ((localTask.value.delete_except_tags) = $event)),
                                protectPerfect: localTask.value.protect_perfect,
                                "onUpdate:protectPerfect": _cache[61] || (_cache[61] = $event => ((localTask.value.protect_perfect) = $event)),
                                perfectMaxSeeders: localTask.value.perfect_max_seeders,
                                "onUpdate:perfectMaxSeeders": _cache[62] || (_cache[62] = $event => ((localTask.value.perfect_max_seeders) = $event)),
                                perfectMinWeeks: localTask.value.perfect_min_weeks,
                                "onUpdate:perfectMinWeeks": _cache[63] || (_cache[63] = $event => ((localTask.value.perfect_min_weeks) = $event))
                              }, null, 8, ["minBonusPerHour", "diskSizeGb", "maxKeepTorrents", "maxAddPerRun", "maxDownloadConcurrent", "topN", "browsePages", "bonusProtectThreshold", "minBonusToKeep", "refillWhenEmpty", "cleanupNoProgress", "cleanupSlowProgress", "purgeUnfreeIncomplete", "autoResumePaused", "tiSource", "noProgressMinutes", "seenCooldownHours", "slowProgressGraceMinutes", "slowProgressMaxHours", "minSeedTime", "minRatio", "deleteFiles", "deleteExceptTags", "protectPerfect", "perfectMaxSeeders", "perfectMinWeeks"])
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode$I("", true),
                      (!simpleMode.value && !isBrush.value)
                        ? (_openBlock$N(), _createBlock$K(_component_VWindowItem, {
                            key: 2,
                            value: "formula"
                          }, {
                            default: _withCtx$K(() => [
                              _createVNode$M(FormulaPanel, {
                                bonusT0: localTask.value.bonus_t0,
                                "onUpdate:bonusT0": _cache[64] || (_cache[64] = $event => ((localTask.value.bonus_t0) = $event)),
                                bonusN0: localTask.value.bonus_n0,
                                "onUpdate:bonusN0": _cache[65] || (_cache[65] = $event => ((localTask.value.bonus_n0) = $event)),
                                bonusB0: localTask.value.bonus_b0,
                                "onUpdate:bonusB0": _cache[66] || (_cache[66] = $event => ((localTask.value.bonus_b0) = $event)),
                                bonusL: localTask.value.bonus_l,
                                "onUpdate:bonusL": _cache[67] || (_cache[67] = $event => ((localTask.value.bonus_l) = $event)),
                                bonusZeroWeight: localTask.value.bonus_zero_weight,
                                "onUpdate:bonusZeroWeight": _cache[68] || (_cache[68] = $event => ((localTask.value.bonus_zero_weight) = $event))
                              }, null, 8, ["bonusT0", "bonusN0", "bonusB0", "bonusL", "bonusZeroWeight"])
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode$I("", true),
                      (!simpleMode.value)
                        ? (_openBlock$N(), _createBlock$K(_component_VWindowItem, {
                            key: 3,
                            value: "selection"
                          }, {
                            default: _withCtx$K(() => [
                              _createVNode$M(SelectionPanel, {
                                freeleech: localTask.value.freeleech,
                                "onUpdate:freeleech": _cache[69] || (_cache[69] = $event => ((localTask.value.freeleech) = $event)),
                                hr: localTask.value.hr,
                                "onUpdate:hr": _cache[70] || (_cache[70] = $event => ((localTask.value.hr) = $event)),
                                size: localTask.value.size,
                                "onUpdate:size": _cache[71] || (_cache[71] = $event => ((localTask.value.size) = $event)),
                                seeder: localTask.value.seeder,
                                "onUpdate:seeder": _cache[72] || (_cache[72] = $event => ((localTask.value.seeder) = $event)),
                                pubtime: localTask.value.pubtime,
                                "onUpdate:pubtime": _cache[73] || (_cache[73] = $event => ((localTask.value.pubtime) = $event)),
                                include: localTask.value.include,
                                "onUpdate:include": _cache[74] || (_cache[74] = $event => ((localTask.value.include) = $event)),
                                exclude: localTask.value.exclude,
                                "onUpdate:exclude": _cache[75] || (_cache[75] = $event => ((localTask.value.exclude) = $event)),
                                excludeZeroBonus: localTask.value.exclude_zero_bonus,
                                "onUpdate:excludeZeroBonus": _cache[76] || (_cache[76] = $event => ((localTask.value.exclude_zero_bonus) = $event)),
                                "is-brush": isBrush.value
                              }, null, 8, ["freeleech", "hr", "size", "seeder", "pubtime", "include", "exclude", "excludeZeroBonus", "is-brush"])
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode$I("", true),
                      (!simpleMode.value)
                        ? (_openBlock$N(), _createBlock$K(_component_VWindowItem, {
                            key: 4,
                            value: "advanced"
                          }, {
                            default: _withCtx$K(() => [
                              _createVNode$M(AdvancedPanel, {
                                crossseedEnabled: localTask.value.crossseed_enabled,
                                "onUpdate:crossseedEnabled": _cache[77] || (_cache[77] = $event => ((localTask.value.crossseed_enabled) = $event)),
                                crossseedMaxPerRound: localTask.value.crossseed_max_per_round,
                                "onUpdate:crossseedMaxPerRound": _cache[78] || (_cache[78] = $event => ((localTask.value.crossseed_max_per_round) = $event)),
                                crossseedMaxSizeGb: localTask.value.crossseed_max_size_gb,
                                "onUpdate:crossseedMaxSizeGb": _cache[79] || (_cache[79] = $event => ((localTask.value.crossseed_max_size_gb) = $event)),
                                crossseedMaxSites: localTask.value.crossseed_max_sites,
                                "onUpdate:crossseedMaxSites": _cache[80] || (_cache[80] = $event => ((localTask.value.crossseed_max_sites) = $event)),
                                upSpeed: localTask.value.up_speed,
                                "onUpdate:upSpeed": _cache[81] || (_cache[81] = $event => ((localTask.value.up_speed) = $event)),
                                dlSpeed: localTask.value.dl_speed,
                                "onUpdate:dlSpeed": _cache[82] || (_cache[82] = $event => ((localTask.value.dl_speed) = $event)),
                                "site-name": siteName.value,
                                "schedule-text": scheduleText.value,
                                "is-brush": isBrush.value,
                                downloader: localTask.value.downloader,
                                "active-time-range": localTask.value.active_time_range,
                                "goal-value": localTask.value.goal_value,
                                "has-goal": hasGoal()
                              }, null, 8, ["crossseedEnabled", "crossseedMaxPerRound", "crossseedMaxSizeGb", "crossseedMaxSites", "upSpeed", "dlSpeed", "site-name", "schedule-text", "is-brush", "downloader", "active-time-range", "goal-value", "has-goal"])
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode$I("", true)
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
      _createVNode$M(_component_VDialog, {
        modelValue: goalWarning.value,
        "onUpdate:modelValue": _cache[85] || (_cache[85] = $event => ((goalWarning).value = $event)),
        "max-width": "30rem"
      }, {
        default: _withCtx$K(() => [
          _createVNode$M(_component_VCard, { class: "pa-2" }, {
            default: _withCtx$K(() => [
              _createVNode$M(_component_VCardText, null, {
                default: _withCtx$K(() => [
                  _createElementVNode$N("div", _hoisted_1$J, [
                    _createVNode$M(_component_VIcon, {
                      icon: "mdi-flag-alert",
                      color: "warning",
                      class: "mr-2"
                    }),
                    _cache[91] || (_cache[91] = _createElementVNode$N("span", { class: "text-subtitle-1 font-weight-medium" }, "尚未设置任务目标", -1))
                  ]),
                  _createElementVNode$N("div", _hoisted_2$H, [
                    _cache[92] || (_cache[92] = _createTextVNode$M(" 建议为每个任务设置目标，达到后会自动停止： ", -1)),
                    _createElementVNode$N("strong", null, _toDisplayString$N(isBrush.value ? '站点上传量（GB）' : '站点魔力值'), 1),
                    _cache[93] || (_cache[93] = _createTextVNode$M("。 ", -1))
                  ])
                ]),
                _: 1
              }),
              _createVNode$M(_component_VCardActions, null, {
                default: _withCtx$K(() => [
                  _createVNode$M(_component_VSpacer),
                  _createVNode$M(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[84] || (_cache[84] = $event => (goalWarning.value = false))
                  }, {
                    default: _withCtx$K(() => [...(_cache[94] || (_cache[94] = [
                      _createTextVNode$M("返回填写", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode$M(_component_VBtn, {
                    color: "warning",
                    variant: "flat",
                    onClick: confirmSaveWithoutGoal
                  }, {
                    default: _withCtx$K(() => [...(_cache[95] || (_cache[95] = [
                      _createTextVNode$M("仍然保存", -1)
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
      }, 8, ["modelValue"]),
      _createVNode$M(_component_VDialog, {
        modelValue: presetConfirm.value.open,
        "onUpdate:modelValue": _cache[88] || (_cache[88] = $event => ((presetConfirm.value.open) = $event)),
        "max-width": "30rem"
      }, {
        default: _withCtx$K(() => [
          _createVNode$M(_component_VCard, { class: "pa-2" }, {
            default: _withCtx$K(() => [
              _createVNode$M(_component_VCardText, null, {
                default: _withCtx$K(() => [
                  _createElementVNode$N("div", _hoisted_3$F, [
                    _createVNode$M(_component_VIcon, {
                      icon: "mdi-alert-outline",
                      color: "warning",
                      class: "mr-2"
                    }),
                    _cache[96] || (_cache[96] = _createElementVNode$N("span", { class: "text-subtitle-1 font-weight-medium" }, "切换模板会覆盖已调整的参数", -1))
                  ]),
                  _createElementVNode$N("div", _hoisted_4$F, " 有 " + _toDisplayString$N(presetConfirm.value.count) + " 项参数与模板取值不同（看起来是你手动调过的），继续将用模板值覆盖。 ", 1)
                ]),
                _: 1
              }),
              _createVNode$M(_component_VCardActions, null, {
                default: _withCtx$K(() => [
                  _createVNode$M(_component_VSpacer),
                  _createVNode$M(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[86] || (_cache[86] = $event => (presetConfirm.value.open = false))
                  }, {
                    default: _withCtx$K(() => [...(_cache[97] || (_cache[97] = [
                      _createTextVNode$M("取消", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode$M(_component_VBtn, {
                    color: "warning",
                    variant: "flat",
                    onClick: _cache[87] || (_cache[87] = $event => (doApplyPreset(presetConfirm.value.key)))
                  }, {
                    default: _withCtx$K(() => [...(_cache[98] || (_cache[98] = [
                      _createTextVNode$M("覆盖并继续", -1)
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
// Vue 的 _export_sfc(sfc, [['__scopeId', ...]]) 等价于挂 __scopeId 属性；
// 这里手写，避免依赖 rollup 私有辅助函数。
const TaskEditorDialog = Object.assign(_sfc_main$N, { __scopeId: 'data-v-6791ce5d' })

export default TaskEditorDialog
