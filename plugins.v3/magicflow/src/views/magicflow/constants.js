// MagicFlow 工作台 —— 纯常量（页面清单 / 磁贴 / 设置分栏 / 报表桶 / 详情入口 / 选项 / 文案映射）
// P1 拆分产物：从 views/magicflow/index.vue 外提，纯数据，无逻辑依赖。

export const ratingSourceItems = [
  { title: '只用 TMDB（默认）', value: 'tmdb' },
  { title: '豆瓣优先（拿不到回退 TMDB · 易被豆瓣限流）', value: 'douban' },
]

// ── ★ 页面注册表（数据驱动，新增功能页只改这个数组，不必动布局）──────────────
// key 与 open* 处理函数一一对应；后续接入手机端导航 / 底栏 / 更多菜单时统一从这里取。
// scope='global' = 插件级单例（不按任务配）；'view' = 只读视图。
// ★ 权责口径见 docs/MODULES.md：全局单例的功能页必须显式标注，避免被当成「任务级」。
// ── ★ 页面注册表（数据驱动，新增功能页只改这个数组，不必动布局）──────────────
// key 与 open* 处理函数一一对应；后续接入手机端导航 / 底栏 / 更多菜单时统一从这里取。
// scope='global' = 插件级单例（不按任务配）；'view' = 只读视图。
// ★ 权责口径见 docs/MODULES.md：全局单例的功能页必须显式标注，避免被当成「任务级」。
export const MF_PAGES = [
  { key: 'recommend', label: '推荐', icon: 'mdi-movie-star-outline', scope: 'global' },
  { key: 'exam', label: '新手考核', icon: 'mdi-school-outline', scope: 'global' },
  { key: 'signin', label: '签到', icon: 'mdi-calendar-check-outline', scope: 'global' },
  { key: 'cloud', label: '云盘归档', icon: 'mdi-cloud-upload-outline', scope: 'global' },
  { key: 'douban', label: '豆瓣评分', icon: 'mdi-database-search-outline', scope: 'global' },
  { key: 'crossseed', label: '跨站取种', icon: 'mdi-swap-horizontal-bold', scope: 'global' },
  { key: 'claim', label: '认领', icon: 'mdi-seal-variant', scope: 'global' },
  { key: 'silent', label: '静默池', icon: 'mdi-pool', scope: 'global' },
  { key: 'sitereport', label: '站点报表', icon: 'mdi-table-large', scope: 'view' },
  { key: 'hrbills', label: 'H&R账单', icon: 'mdi-file-alert-outline', scope: 'view' },
  { key: 'ceiling', label: '站点容量', icon: 'mdi-gauge', scope: 'view' },
  { key: 'ops', label: '操作记录', icon: 'mdi-history', scope: 'view' },
  { key: 'settings', label: '插件设置', icon: 'mdi-tune-variant', scope: 'global' },
]

// ★ 顶栏功能磁贴显隐（7.10.1）：纯界面层开关，存「隐藏」白名单（空 = 全部显示）。
//   功能本体各有各的开关，这里只管「顶栏/手机功能格要不要显示入口」。
// ★ 顶栏功能磁贴显隐（7.10.1）：纯界面层开关，存「隐藏」白名单（空 = 全部显示）。
//   功能本体各有各的开关，这里只管「顶栏/手机功能格要不要显示入口」。
export const TILE_OPTIONS = [
  { key: 'recommend', label: '推荐', icon: 'mdi-movie-star-outline' },
  { key: 'exam', label: '新手考核', icon: 'mdi-school-outline' },
  { key: 'signin', label: '签到', icon: 'mdi-calendar-check-outline' },
  { key: 'cloud', label: '云盘归档', icon: 'mdi-cloud-upload-outline' },
  { key: 'douban', label: '豆瓣评分', icon: 'mdi-database-search-outline' },
  { key: 'crossseed', label: '跨站取种', icon: 'mdi-swap-horizontal-bold' },
  { key: 'claim', label: '认领', icon: 'mdi-seal-variant' },
  { key: 'silent', label: '静默池', icon: 'mdi-pool' },
  { key: 'sitereport', label: '站点报表', icon: 'mdi-table-large' },
  { key: 'hrbills', label: 'H&R账单', icon: 'mdi-file-alert-outline' },
  { key: 'ondemand', label: '点播', icon: 'mdi-cloud-download-outline' },
  { key: 'ceiling', label: '站点容量', icon: 'mdi-gauge' },
  { key: 'ops', label: '操作记录', icon: 'mdi-history' },
]

// 设置页目录（手机端：标签栏 → 目录列表；桌面端仍用标签栏）
// 设置页目录（手机端：标签栏 → 目录列表；桌面端仍用标签栏）
export const MF_SETTINGS_TABS = [
  { key: 'general', label: '常规', icon: 'mdi-cog-outline' },
  { key: 'downloader', label: '下载与目录', icon: 'mdi-download-network-outline' },
  { key: 'template', label: '默认任务模板', icon: 'mdi-file-document-outline' },
  { key: 'iyuu', label: 'IYUU 辅种', icon: 'mdi-sync' },
  { key: 'reseed', label: '全站辅种', icon: 'mdi-content-duplicate' },
  { key: 'fallback', label: '元数据兜底', icon: 'mdi-database-search-outline' },
  { key: 'cloud', label: '云盘归档', icon: 'mdi-cloud-upload-outline' },
  { key: 'exam', label: '考核', icon: 'mdi-school-outline' },
  { key: 'signin', label: '签到', icon: 'mdi-calendar-check-outline' },
  { key: 'live', label: '站点监控', icon: 'mdi-monitor-eye' },
  { key: 'recommend', label: '推荐', icon: 'mdi-movie-star-outline' },
  { key: 'crossseed', label: '跨站', icon: 'mdi-swap-horizontal-bold' },
  { key: 'claim', label: '认领', icon: 'mdi-seal-variant' },
  { key: 'rules', label: '站点规则', icon: 'mdi-shield-check-outline' },
  { key: 'tags', label: '标签管理', icon: 'mdi-tag-multiple-outline' },
]

export const SITE_REPORT_BUCKETS = [
  { key: '刷流', color: 'indigo' },
  { key: '魔力', color: 'purple' },
  { key: '保种', color: 'deep-orange' },
  { key: '静默', color: 'blue-grey' },
  { key: '补源', color: 'teal' },
  { key: '外部', color: 'grey' },
]

export const SITE_REPORT_TRANSPORT = [
  { key: '未完成', color: 'amber' },
  { key: '暂停', color: 'grey' },
  { key: '做种中', color: 'success' },
]

export const SITE_REPORT_SILENT_SUBS = [
  { key: '新', color: 'info' },
  { key: '资源', color: 'success' },
  { key: '普通', color: 'blue-grey' },
]

// ★ 15.2.0 静默桶「出身轴」：池（种子账本）/ 辅种副本（mf_reseed）/ 无主
// ★ 15.2.0 静默桶「出身轴」：池（种子账本）/ 辅种副本（mf_reseed）/ 无主
export const SITE_REPORT_ORIGINS = [
  { key: '池', color: 'blue-grey' },
  { key: '辅种副本', color: 'teal' },
  { key: '无主', color: 'warning' },
]

// ── 手机端任务详情：紧凑块（三个数 + 策略一行 + 次级入口）──────────────
// ── 手机端任务详情：紧凑块（三个数 + 策略一行 + 次级入口）──────────────
export const MF_DETAIL_ENTRIES = [
  { key: 'diagnostics', label: '运行诊断', icon: 'mdi-stethoscope' },
  { key: 'pool', label: '种子池', icon: 'mdi-seed-outline' },
  { key: 'config', label: '任务配置', icon: 'mdi-tune-variant' },
  { key: 'ops', label: '操作记录', icon: 'mdi-history', action: 'ops' },
]

// 运行诊断流程链（v5 阶段）—— 骨架五阶段两模式共用，但每阶段实做不同，文案按类型分显
// 运行诊断流程链（v5 阶段）—— 骨架五阶段两模式共用，但每阶段实做不同，文案按类型分显
export const FLOW_STEPS_BONUS = [
  { key: 'entry', label: '入口检查' },
  { key: 'fetch', label: '抓取候选' },
  { key: 'wash', label: '洗池过滤' },
  { key: 'classify', label: '魔力排序' },
  { key: 'process', label: '保种入库' },
]

export const FLOW_STEPS_BRUSH = [
  { key: 'entry', label: '入口检查' },
  { key: 'fetch', label: '抓取候选' },
  { key: 'wash', label: '免费筛选' },
  { key: 'classify', label: '下载人数排序' },
  { key: 'process', label: '复用·入库' },
]

// 工作台标签（预览图：分段式标签卡）
// 工作台标签（预览图：分段式标签卡）
export const MF_TABS = [
  { value: 'overview', label: '任务概览' },
  { value: 'diagnostics', label: '运行诊断' },
  { value: 'pool', label: '种子池' },
  { value: 'config', label: '任务配置' },
]

export const KIND_TEXT = { run: '执行', selection: '选种加入', deletion: '删种清理', protection: '手动保留', unprotection: '取消保留', reseed: '辅种', reuse: '存量复用(旧)', crossseed: '跨站取种(旧)', swap: '换种(旧)', pause: '暂停种子', resume: '恢复运行', recheck: '强制校验', goal: '达标停止', state: '运行状态', tag: '标签变更', fallback: '元数据兜底', cloud: '云盘归档' }

export const STATE_TEXT = { submitting: '提交中', accepted: '已受理', completed: '已完成', failed: '失败' }

export const KIND_ICON = {
  run: 'mdi-play-circle-outline',
  selection: 'mdi-download-outline',
  deletion: 'mdi-delete-outline',
  reseed: 'mdi-content-duplicate',
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
}

export const EVENT_LEVELS = [
  { value: '', label: '全部级别' },
  { value: 'error', label: '仅错误' },
  { value: 'warning', label: '警告以上' },
  { value: 'info', label: '仅普通' },
]

export const OPS_KIND_FILTERS = [
  { value: '', label: '全部', icon: 'mdi-format-list-bulleted' },
  { value: 'deletion', label: '删种清理', icon: 'mdi-delete-outline' },
  { value: 'selection', label: '选种加入', icon: 'mdi-download-outline' },
  { value: 'reseed', label: '辅种', icon: 'mdi-content-duplicate' },
  { value: 'protection', label: '手动保留', icon: 'mdi-shield-check-outline' },
  { value: 'unprotection', label: '取消保留', icon: 'mdi-shield-off-outline' },
  { value: 'tag', label: '标签变更', icon: 'mdi-tag-outline' },
  { value: 'run', label: '执行', icon: 'mdi-play-circle-outline' },
]

export const ITEM_SOURCE_TEXT = {
  add: '新增', 'add-fail': '失败', reuse: '复用', 'reuse-fail': '辅种失败',
  adopt: '纳管', watchdog: '看门狗', run: '汇总',
  // ★ 清理类（Master 要求「清理逻辑必须有操作记录 + 详情」）
  missing: '空壳种', silent: '静默池', live: '站点监控', crossseed: '跨站',
  selection: '选种', deletion: '删种', tag: '标签', protection: '保留', unprotection: '取消保留',
}

export const RESEED_KINDS = ['reseed', 'reuse', 'crossseed']

export const TORRENT_STATE_TEXT = {
  uploading: '做种中', stalledup: '做种中·无流量', forcedup: '做种中', queuedup: '排队做种',
  downloading: '下载中', forceddl: '下载中', queueddl: '排队下载', metadl: '获取元数据', checkingdl: '校验中',
  stalleddl: '下载停滞', pausedup: '已暂停', pauseddl: '已暂停', stoppedup: '已停止', stoppeddl: '已停止',
  error: '出错', missingfiles: '文件缺失', unknown: '未知',
}

// 托管种子状态文本：做种 / 下载 X% / 暂停 / 整理中（参考 BrushFlow）
// 注意：progress=100 不等于「做种中」——已暂停/停止、整理中、校验中的种子要显示真实状态，
// 否则会出现「状态列写作种中、筛选却归到已暂停」的口径不一致。
// 托管种子状态文本：做种 / 下载 X% / 暂停 / 整理中（参考 BrushFlow）
// 注意：progress=100 不等于「做种中」——已暂停/停止、整理中、校验中的种子要显示真实状态，
// 否则会出现「状态列写作种中、筛选却归到已暂停」的口径不一致。
export const TORRENT_TRANSIENT_STATES = {
  moving: '整理中',
  allocating: '分配空间',
  checkingup: '校验中',
  checkingdl: '校验中',
  checkingresumedata: '校验中',
  forcedmetadl: '获取元数据',
}

export const TORRENT_PAUSED_STATES = ['pausedup', 'pauseddl', 'stoppedup', 'stoppeddl']

export const SIGNIN_STATUS_TEXT = { ok: '成功', fail: '都失败', signfail: '签到失败', loginfail: '登录失败', pending: '待执行', skip: '跳过', none: '无记录' }

// 失败类（三种颜色）：signfail=签到✗登录✓（红） / loginfail=签到✓登录✗（橙） / fail=都✗（深红）
// 失败类（三种颜色）：signfail=签到✗登录✓（红） / loginfail=签到✓登录✗（橙） / fail=都✗（深红）
export const SIGNIN_FAIL_STATUS = ['fail', 'signfail', 'loginfail']

export const SIGNIN_ORDER = { fail: 0, signfail: 1, loginfail: 2, pending: 3, ok: 4, skip: 5 }

export const EXAM_KIND_TEXT = { upload: '刷上传', download: '下载考核', bonus: '攒魔力', hold: '保持做种', info: '下载考核' }

export const EXAM_KIND_ICON = {
  upload: 'mdi-upload',
  download: 'mdi-download',
  bonus: 'mdi-star-four-points-outline',
  hold: 'mdi-pause-circle-outline',
  info: 'mdi-download',
}

// ★ 可一键起任务的只有「刷上传 / 攒魔力」；下载类我们不做（Master 2026-09-30），只作提示
// ★ 可一键起任务的只有「刷上传 / 攒魔力」；下载类我们不做（Master 2026-09-30），只作提示
export const EXAM_ACTIONABLE = ['upload', 'bonus']

export const SILENT_SUB_LABEL = { 新: '静默-新', 资源: '静默-资源', 普通: '静默-普通' }

// 对托管种子执行 保留 / 取消保留 / 暂停 / 恢复 / 强制校验 / 删除。
// 对托管种子执行 保留 / 取消保留 / 暂停 / 恢复 / 强制校验 / 删除。
export const TORRENT_ACTION_LABEL = {
  protect: '已保留种子',
  unprotect: '已取消保留',
  pause: '已暂停种子（不会被自动恢复）',
  resume: '已恢复做种',
  recheck: '已开始重新校验',
  delete: '已删除种子',
}

// ---------------- 批量操作 ----------------
// ---------------- 批量操作 ----------------
export const BATCH_LABEL = {
  protect: '批量保留',
  unprotect: '批量取消保留',
  pause: '批量暂停',
  resume: '批量恢复',
  recheck: '批量校验',
  delete: '批量删除',
}
