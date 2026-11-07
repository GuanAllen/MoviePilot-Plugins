// ClaimDialog —— 由线上 dist 还原（dist 关闭了 minify，保留了完整编译产物）。
// 形态是 Vue SFC 编译后的组件对象（不是 .vue 模板），行为与 19.11.23 线上一致。
import './ClaimDialog.css'


import * as __vue from 'vue'

const {
  Fragment: _Fragment$v,
  createBlock: _createBlock$w,
  createCommentVNode: _createCommentVNode$w,
  createElementBlock: _createElementBlock$v,
  createElementVNode: _createElementVNode$z,
  createTextVNode: _createTextVNode$y,
  createVNode: _createVNode$y,
  mergeModels: _mergeModels$i,
  normalizeClass: _normalizeClass$i,
  openBlock: _openBlock$z,
  renderList: _renderList$t,
  resolveComponent: _resolveComponent$z,
  toDisplayString: _toDisplayString$z,
  useModel: _useModel$i,
  withCtx: _withCtx$w,
  withKeys: _withKeys$2,
  withModifiers: _withModifiers$3,
} = __vue


const _hoisted_1$x = { class: "magicflow-settings-dialog__head" };
const _hoisted_2$v = { class: "magicflow-claim-title" };
const _hoisted_3$t = { class: "magicflow-recommend-dialog__head-actions" };
const _hoisted_4$t = { class: "magicflow-claim-bar" };
const _hoisted_5$t = {
  key: 0,
  class: "magicflow-claim-bar__hint"
};
const _hoisted_6$r = { class: "magicflow-claim-summary" };
const _hoisted_7$p = { class: "magicflow-claim-summary__item" };
const _hoisted_8$n = { class: "magicflow-claim-summary__item" };
const _hoisted_9$l = { class: "magicflow-claim-summary__item is-accent" };
const _hoisted_10$l = { class: "magicflow-claim-tabs" };
const _hoisted_11$k = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_12$k = {
  key: 1,
  class: "magicflow-claim-list"
};
const _hoisted_13$i = { class: "magicflow-claim-item__main" };
const _hoisted_14$h = { class: "magicflow-claim-item__head" };
const _hoisted_15$h = ["title"];
const _hoisted_16$h = ["href"];
const _hoisted_17$h = {
  key: 0,
  class: "magicflow-claim-item__spec"
};
const _hoisted_18$h = { class: "magicflow-claim-item__meta" };
const _hoisted_19$g = {
  key: 1,
  class: "magicflow-claim-item__why"
};
const _hoisted_20$e = {
  key: 2,
  class: "magicflow-claim-more"
};
const _hoisted_21$d = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_22$c = {
  key: 0,
  class: "magicflow-claim-empty__why"
};
const _hoisted_23$b = {
  key: 1,
  class: "magicflow-claim-list"
};
const _hoisted_24$b = { class: "magicflow-claim-item__main" };
const _hoisted_25$b = { class: "magicflow-claim-item__head" };
const _hoisted_26$9 = ["title"];
const _hoisted_27$9 = ["href"];
const _hoisted_28$8 = {
  key: 0,
  class: "magicflow-claim-item__spec"
};
const _hoisted_29$8 = { class: "magicflow-claim-item__meta" };
const _hoisted_30$8 = {
  key: 1,
  class: "magicflow-claim-item__reward"
};
const _hoisted_31$8 = {
  key: 2,
  class: "magicflow-claim-more"
};
const _hoisted_32$8 = {
  key: 3,
  class: "magicflow-claim-soon"
};
const _hoisted_33$7 = { class: "magicflow-claim-soon__hint" };
const _hoisted_34$7 = {
  key: 0,
  class: "magicflow-claim-list magicflow-claim-list--soon"
};
const _hoisted_35$6 = { class: "magicflow-claim-item__main" };
const _hoisted_36$5 = { class: "magicflow-claim-item__head" };
const _hoisted_37$4 = ["title"];
const _hoisted_38$4 = ["href"];
const _hoisted_39$4 = {
  key: 0,
  class: "magicflow-claim-item__spec"
};
const _hoisted_40$4 = { class: "magicflow-claim-item__meta" };
const _hoisted_41$4 = {
  key: 1,
  class: "magicflow-claim-more"
};
const _hoisted_42$3 = {
  key: 0,
  class: "magicflow-claim-sites"
};
const _hoisted_43$2 = ["onClick", "onKeydown"];
const _hoisted_44$2 = { class: "magicflow-claim-site__head" };
const _hoisted_45$2 = { class: "magicflow-claim-site__name" };
const _hoisted_46$2 = { class: "magicflow-claim-site__date" };
const _hoisted_47$2 = { class: "magicflow-claim-site__stats" };
const _hoisted_48$2 = { class: "magicflow-claim-site__stat" };
const _hoisted_49$2 = { class: "magicflow-claim-site__stat" };
const _hoisted_50$2 = { class: "magicflow-claim-site__stat is-accent" };
const _hoisted_51$2 = {
  key: 0,
  class: "magicflow-claim-site__sub"
};
const _hoisted_52$2 = {
  key: 0,
  class: "magicflow-table-empty"
};
const _hoisted_53$2 = {
  key: 1,
  class: "magicflow-claim-more"
};
const _hoisted_54$2 = { class: "magicflow-claim-note" };
const _hoisted_55$2 = {
  key: 5,
  class: "magicflow-claim-note"
};

const {computed: computed$I,ref: ref$z} = __vue;

const _sfc_main$z = {
  __name: 'ClaimDialog',
  props: /*@__PURE__*/_mergeModels$i({
  isNarrow: { type: Boolean, default: false },
  claimData: { type: Object, default: () => ({}) },
  claimCfg: { type: Object, default: () => ({}) },
  claimSites: { type: Array, default: () => [] },
  claimSupportedSites: { type: Array, default: () => [] },
  claimClaimable: { type: Array, default: () => [] },
  claimClaimed: { type: Array, default: () => [] },
  claimSoon: { type: Array, default: () => [] },
  claimLoading: { type: Boolean, default: false },
  claimActing: { type: String, default: '' },
}, {
    "modelValue": { type: Boolean, default: false },
    "modelModifiers": {},
  }),
  emits: /*@__PURE__*/_mergeModels$i(['refresh', 'scan', 'ask'], ["update:modelValue"]),
  setup(__props, { emit: __emit }) {

// MagicFlow 前端 · 认领弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调用父方法。
const claimOpen = _useModel$i(__props, "modelValue");

// 数据向下（只读）：claimData 为原始后端状态，其余为父页派生数组（单一真值源在父页）。
const props = __props;

const emit = __emit;

// 站点筛选（下拉选站）：单站看该站认领详情，全部站点看各站详情汇总。
// 纯组件内部 UI 状态（父页无引用）→ 随弹窗自 index.vue 迁入。
const claimSiteFilter = ref$z('');
const claimFilterItems = computed$I(() => [
  { title: '全部站点', value: '' },
  ...(props.claimSites || []).map((s) => ({
    title: `${s.site_name || s.domain}${s.supported ? '' : '（未收录）'}`,
    value: String(s.site_id),
  })),
]);
function claimFilterSite() {
  if (!claimSiteFilter.value) return null
  return (props.claimSites || []).find((s) => String(s.site_id) === claimSiteFilter.value) || null
}
// 站点列表：只列支持认领的站。全部站点时逐站汇总，不跨站求和。
const claimSupportedList = computed$I(() => (props.claimSites || []).filter((s) => s.supported));
const claimScopeSite = computed$I(() => claimFilterSite());
// 站点自己的结算口径（不再跨站取「最近日期」或最高倍率）。
function claimSiteSettle(s) { return (s && s.settlement) || {} }
// 结算日期文案：「11 月 1 日 · 剩 14.5 天 · 每月结算（自然月）」。
function claimSiteDateText(s) {
  const st = claimSiteSettle(s);
  if (!st.next_settle_at) return '结算日待定'
  const d = new Date(st.next_settle_at * 1000);
  const dateText = `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
  const left = (st.days_left === null || st.days_left === undefined) ? '' : `剩 ${Number(st.days_left).toFixed(1)} 天`;
  return [dateText, left].filter(Boolean).join(' · ')
}
function claimSiteCycleText(s) { return claimSiteSettle(s).cycle_text || '结算周期待定' }
function claimSiteById(id) { return (props.claimSites || []).find(s => String(s.site_id) === String(id)) || null }
function claimSiteReward(s) {
  if (!s) return '—'
  const rows = (props.claimClaimed || []).filter(r => String(r.site_id) === String(s.site_id) && r.site_reward_num != null);
  if (rows.length) {
    const total = rows.reduce((a, r) => a + (Number(r.site_reward_num) || 0), 0);
    if (total > 0) return claimNum(total)
  }
  const p = claimProfile(s);
  return p.benefit === 'bonus_x2' ? '×2' : (p.benefit || '—')
}
function claimRowReward(row) {
  if (row.site_reward) return row.site_reward
  const s = claimSiteById(row.site_id);
  const p = s ? claimProfile(s) : {};
  return p.benefit === 'bonus_x2' ? '×2' : (p.benefit || '—')
}
// 列表按选中站点过滤；未选站 = 全部。
function claimRowsFor(rows, siteId) {
  const list = rows || [];
  if (!siteId) return list
  return list.filter((r) => String(r.site_id) === String(siteId))
}
const claimFilteredClaimable = computed$I(() => claimRowsFor(props.claimClaimable, claimSiteFilter.value));
const claimFilteredClaimed = computed$I(() => claimRowsFor(props.claimClaimed, claimSiteFilter.value));
const claimFilteredSoon = computed$I(() => claimRowsFor(props.claimSoon, claimSiteFilter.value));
// ── ★ 19.10.59「可认领为零」要能自证原因 ─────────────────────────────────────
// 学校（pt.btschool.club）实测 2026-10-31：站点「当前活动」= 做种 4 颗，这 4 颗
// （326608 / 326427 / 326419 / 326403）全在 viewclaims.php 里，4 个详情页也都
// 不再有 add_torrent_id → 可认领 0 是**真值**，不是漏扫。
// 但界面只写「当前没有可认领种子」，用户没法区分「真没有」与「扫描坏了」。
// 这里只用扫描结果里**已有**的站点统计（site_rows / site_claimed / site_open /
// site_not_local / soon 条数）拼一句实话：零额外请求，也不在本地重算站点口径。
const claimEmptyReason = computed$I(() => {
  const s = claimScopeSite.value;
  if (!s) return ''
  const rows = Number(s.site_rows || 0);
  const claimed = Number(s.site_claimed || 0);
  const open = Number(s.site_open || 0);
  const notLocal = Number(s.site_not_local || 0);
  const soon = claimFilteredSoon.value.length;
  const minAge = Number(claimProfile(s).min_age_days || 0);
  if (!rows) {
    return '站点没回发「我的做种」列表：可能当前没有在做种的种子，或站点登录态失效'
  }
  const parts = [`本站做种 ${rows} 颗`];
  if (claimed) parts.push(`${claimed} 颗已认领`);
  // 站点没有发布天数门槛时（minAge=0），soon 行不是「还差几天」，别硬套天数
  if (soon) parts.push(minAge > 0 ? `${soon} 颗未满 ${minAge} 天在等` : `${soon} 颗站点暂未给认领入口`);
  if (notLocal) parts.push(`${notLocal} 颗本地没有`);
  if (open) parts.push(`站点显示 ${open} 颗可领、但本地对不上`);
  return parts.join('，')
});
// 站点卡片的副行（全部站点视图）：只报站点侧真实行数，不做推算。
function claimSiteRowText(s) {
  const rows = Number((s || {}).site_rows || 0);
  if (!rows) return ''
  const claimed = Number((s || {}).site_claimed || 0);
  return `做种 ${rows} 颗${claimed ? ` · 已领 ${claimed}` : ''}`
}
// 多站大量种子时列表只渲染前 50 条（总量与收益在报表里，列表只是操作入口）。
const claimClaimedLimit = ref$z(20);
const claimClaimableLimit = ref$z(20);
const claimShownClaimed = computed$I(() => claimFilteredClaimed.value.slice(0, claimClaimedLimit.value));
const claimShownClaimable = computed$I(() => claimFilteredClaimable.value.slice(0, claimClaimableLimit.value));
function claimMoreClaimed() { claimClaimedLimit.value += 20; }
function claimMoreClaimable() { claimClaimableLimit.value += 20; }
const claimListTab = ref$z('claimed');
const claimSummaryClaimed = computed$I(() => claimFilteredClaimed.value.length);
const claimSummaryReward = computed$I(() => {
  let n = 0;
  for (const r of claimFilteredClaimed.value) {
    const v = Number(r.site_reward_num);
    if (Number.isFinite(v)) n += v;
  }
  return n
});
const claimSummaryRewardText = computed$I(() => claimSummaryReward.value > 0 ? claimNum(claimSummaryReward.value) : '—');
const claimSummarySettle = computed$I(() => {
  if (claimScopeSite.value) return claimSiteDateText(claimScopeSite.value)
  const rows = (props.claimSites || []).filter(s => s.supported && s.settlement && s.settlement.next_settle_at);
  if (!rows.length) return '—'
  const min = Math.min(...rows.map(s => Number(s.settlement.next_settle_at)));
  const s = rows.find(x => Number(x.settlement.next_settle_at) === min);
  return s ? claimSiteDateText(s) : '—'
});
function claimNum(v) { return Number(v || 0).toLocaleString('zh-CN') }
// ── 展示用纯函数（随弹窗自 index.vue 迁入；数据经 props 下行，函数在组件内自持，
//    不向上传函数，避免 Function prop）──
function claimRequestable() { return Number(props.claimData.claimable_total || 0) }
function claimAgeText(v) { return (v === null || v === undefined) ? '—' : `${Number(v).toFixed(1)} 天` }

// ── ★ 19.10.53「我认领的到底是什么」────────────────────────────────────────
// 站点给的是拼音/英文发布名（站点把「唐朝诡事录之长安」写成
// `Tang Chao Gui Shi Lu Zhi Chang An`），列表里认不出是哪部片。
// 实测**本机拿不到中文名**：MP 识别链一次 32s 还返空、媒体库转移历史 0 行，
// 所以不翻译、不猜 —— 只做两件零成本的事：
//   ① 把标题里**本来就有**的中文抽出来（digest.cn）+ 年份/季集/分辨率/来源，
//      这些是纯本地正则，恒有结果、不发一次请求；
//   ② 给一个详情页直达链接 —— 站点页上有原名、简介、截图，点一下就知道是什么。
function claimDigest(row) {
  const d = (row && row.digest) || {};
  return {
    year: d.year || null,
    res: d.res || '',
    src: d.src || '',
    season: (d.season === 0 || d.season) ? d.season : null,
    ep: d.ep || '',
    pack: !!d.pack,
    group: d.group || '',
    cn: d.cn || '',
  }
}
// 剧集写法：整季 `S02 全集` / 区间 `S01 E01-E12` / 单集 `S01E05`
function claimEpText(d) {
  if (!d.season) return ''
  const s = `S${String(d.season).padStart(2, '0')}`;
  if (!d.ep) return `${s} 全集`
  return `${s}E${String(d.ep).replace('-', '-E')}`
}
// 主行：站点原文发布名 —— **唯一事实，不做任何改写**（改写过的名字比原名更难核对）。
function claimRowName(row) {
  return String((row && row.title) || (row && row.hash) || '')
}
// 副行规格：只列**确实解析出来**的字段，缺的跳过（不拿默认值凑数）。
// 标题自带中文时放最前（「唐朝诡事录」比拼音更好认），没有就只列规格。
function claimRowSpec(row) {
  const d = claimDigest(row);
  const out = [];
  if (d.cn) out.push(`「${d.cn}」`);
  if (d.year) out.push(String(d.year));
  const ep = claimEpText(d);
  if (ep) out.push(ep);
  if (d.res) out.push(d.res.toLowerCase());
  if (d.src) out.push(d.src);
  if (d.group) out.push(`-${d.group}`);
  return out.join(' · ')
}
function claimRowMeta(row) {
  return [`${row.size_gb}G`, `发布 ${claimAgeText(row.age_days)}`].filter(Boolean).join(' · ')
}
// 详情页直达：站点把中文名转成拼音，点开站点页才是认片最快的路（零猜测）。
// 缺域名或缺 tid 就**不显示**链接（不吐裸站点首页那种假入口）。
function claimRowDetailUrl(row) {
  const d = String((row && row.site_domain) || '').trim()
    .replace(/^https?:\/\//i, '').replace(/\/+$/, '');
  const tid = String((row && row.torrent_id) || '').trim();
  if (!d || !/^\d+$/.test(tid)) return ''
  return `https://${d}/details.php?id=${tid}`
}
// 「还差几天」：soon 行有的是站点没给按钮（未满资格），有的只是等资格日。
// 有 wait_days 就说人话，没有就退回后端给的 block 理由。
function claimWaitText(row) {
  const w = Number(row && row.wait_days);
  if (Number.isFinite(w) && w > 0) return `还差 ${w.toFixed(1)} 天`
  const blk = (row && row.block) || [];
  return blk.length ? String(blk[0]) : '等待站点开放'
}
const claimSoonOpen = ref$z(false);
const claimSoonLimit = ref$z(10);
const claimSoonSorted = computed$I(() => {
  const list = (claimFilteredSoon.value || []).slice();
  list.sort((a, b) => (Number(a.wait_days ?? 1e9)) - (Number(b.wait_days ?? 1e9)));
  return list
});
const claimSoonShown = computed$I(() => claimSoonSorted.value.slice(0, claimSoonLimit.value));
function claimMoreSoon() { claimSoonLimit.value += 10; }
const claimSoonTotalText = computed$I(() => {
  const n = Number(props.claimData && props.claimData.soon_total) || claimSoonSorted.value.length;
  return claimNum(n)
});
// ★ 站点认领画像（后端 sites[].profile：supported / min_age_days / max_claimers /
//   per_user_cap / benefit(_desc) / penalty / reason）。
function claimProfile(s) { return (s && s.profile) || {} }
// ── ★ 19.10.58「放弃认领」：只在**安全**时可点 ────────────────────────────────
// 放弃是带罚则的承诺：站点判未达标又过了豁免期，放弃会扣魔力（咖啡 −1000 / CARPT −500）。
// 判定在**后端**做（站点口径：本月是否达标 + 认领记录 id + 首 N 天豁免），前端只摆结论；
// 这里绝不本地重算，否则两套口径必然打架。
//   safe / grace → 可点；blocked / unknown / unsupported → 置灰并把原因写在行里。
function claimAbandonState(row) { return String((row && row.abandon_state) || 'unknown') }
function claimAbandonPenalty(row) { return Number((row && row.abandon_penalty) || 0) }
function claimCanAbandon(row) {
  const st = claimAbandonState(row);
  return (st === 'safe' || st === 'grace') && !props.claimCfg.dry
}
// 行内短标签：「可安全放弃 / 豁免期内 / 放弃扣 1000 / 状态未知 / 需站内放弃」
function claimAbandonTag(row) {
  const st = claimAbandonState(row);
  if (st === 'safe') return '可安全放弃'
  if (st === 'grace') return '首月内可退'
  if (st === 'blocked') {
    const p = claimAbandonPenalty(row);
    return p ? `放弃扣 ${p}` : '未达标不可退'
  }
  if (st === 'unsupported') return '需站内放弃'
  return '放弃状态未知'
}
// 不可点时必须说明**为什么**（灰按钮不说话，用户只会以为坏了）。
function claimAbandonBlockedText(row) {
  const st = claimAbandonState(row);
  if (st === 'safe' || st === 'grace') return ''
  return String((row && row.abandon_reason) || '站点未回发放弃所需信息')
}
function claimAbandonKey(row) { return 'abandon:' + String((row && row.hash) || 'batch') }
// ★ 19.7.0：认领保挂实况（账本 × qB）
const claimHost = computed$I(() => props.claimData.host || {});
function claimQbKind(row) {
  if (row && row.site_only) return 'site'
  if (!row || !row.in_qb) return 'missing'
  const s = String(row.qb_state || '').toLowerCase();
  if (s.includes('paus') || s.includes('stop')) return 'paused'
  return 'seeding'
}
function claimQbText(row) {
  const k = claimQbKind(row);
  if (k === 'site') return '站点侧'
  return k === 'seeding' ? '做种中' : (k === 'paused' ? '已暂停' : '不在 qB')
}
function claimQbColor(row) {
  const k = claimQbKind(row);
  if (k === 'site') return 'info'
  return k === 'seeding' ? 'success' : (k === 'paused' ? 'warning' : 'error')
}
// ── ★ 19.5.0：干跑 / 真跑两个动作彻底分开（用户可见文案，短句）──
//   顶栏常驻模式徽标；「扫描（只读）」永不写；「认领本轮」常驻但禁用时给出原因。
const claimModeText = computed$I(() => (props.claimCfg.dry ? '干跑' : '真跑'));
const claimSkipped = computed$I(() => props.claimData.sites_skipped || []);
computed$I(() => Number(props.claimData.sites_total || 0));
computed$I(() => Number(props.claimData.sites_supported_total || 0));
// ★ 19.6.0「其他站点纳入」：规则未核对的站（preset 用同族插件默认值）——UI 必须如实标注。
computed$I(() => {
  const n = Number(props.claimData.sites_unverified_total || 0);
  if (n > 0) return n
  return (props.claimSites || []).filter((s) => s.supported && claimProfile(s).rules_unverified).length
});
computed$I(() => props.claimData.sites_unverified || []);
function claimBatchDisabled() {
  if (!props.claimCfg.enabled) return true
  if (props.claimCfg.dry) return true
  return !claimRequestable()
}
function claimBatchHint() {
  if (!props.claimCfg.enabled) return '认领未开启'
  if (props.claimCfg.dry) return '干跑中：执行认领已禁用'
  if (!claimRequestable()) return '暂无可认领'
  return ''
}

return (_ctx, _cache) => {
  const _component_VChip = _resolveComponent$z("VChip");
  const _component_VBtn = _resolveComponent$z("VBtn");
  const _component_VDivider = _resolveComponent$z("VDivider");
  const _component_VSelect = _resolveComponent$z("VSelect");
  const _component_VSpacer = _resolveComponent$z("VSpacer");
  const _component_VAlert = _resolveComponent$z("VAlert");
  const _component_VIcon = _resolveComponent$z("VIcon");
  const _component_VCardText = _resolveComponent$z("VCardText");
  const _component_VCard = _resolveComponent$z("VCard");
  const _component_VDialog = _resolveComponent$z("VDialog");

  return (_openBlock$z(), _createBlock$w(_component_VDialog, {
    modelValue: claimOpen.value,
    "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((claimOpen).value = $event)),
    "max-width": "52rem",
    scrollable: "",
    fullscreen: __props.isNarrow
  }, {
    default: _withCtx$w(() => [
      _createVNode$y(_component_VCard, { class: "magicflow-dialog magicflow-claim-dialog" }, {
        default: _withCtx$w(() => [
          _createElementVNode$z("header", _hoisted_1$x, [
            _createElementVNode$z("div", _hoisted_2$v, [
              _cache[9] || (_cache[9] = _createElementVNode$z("span", { class: "magicflow-settings-dialog__title" }, "认领", -1)),
              _createVNode$y(_component_VChip, {
                size: "x-small",
                color: __props.claimCfg.dry ? 'warning' : 'success',
                variant: "tonal"
              }, {
                default: _withCtx$w(() => [
                  _createTextVNode$y(_toDisplayString$z(claimModeText.value), 1)
                ]),
                _: 1
              }, 8, ["color"])
            ]),
            _createElementVNode$z("div", _hoisted_3$t, [
              _createVNode$y(_component_VBtn, {
                variant: "text",
                color: "primary",
                size: "small",
                "prepend-icon": "mdi-refresh",
                loading: __props.claimLoading,
                onClick: _cache[0] || (_cache[0] = $event => (emit('refresh')))
              }, {
                default: _withCtx$w(() => [...(_cache[10] || (_cache[10] = [
                  _createTextVNode$y("刷新", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              _createVNode$y(_component_VBtn, {
                icon: "mdi-close",
                size: "small",
                variant: "text",
                "aria-label": "关闭",
                onClick: _cache[1] || (_cache[1] = $event => (claimOpen.value = false))
              })
            ])
          ]),
          _createVNode$y(_component_VDivider),
          _createElementVNode$z("div", _hoisted_4$t, [
            _createVNode$y(_component_VSelect, {
              modelValue: claimSiteFilter.value,
              "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((claimSiteFilter).value = $event)),
              items: claimFilterItems.value,
              density: "compact",
              variant: "outlined",
              "hide-details": "",
              class: "magicflow-claim-bar__site",
              "aria-label": "站点筛选"
            }, null, 8, ["modelValue", "items"]),
            _createVNode$y(_component_VSpacer),
            _createVNode$y(_component_VBtn, {
              size: "small",
              variant: "tonal",
              color: "primary",
              "prepend-icon": "mdi-radar",
              loading: __props.claimActing === 'run',
              onClick: _cache[3] || (_cache[3] = $event => (emit('scan')))
            }, {
              default: _withCtx$w(() => [...(_cache[11] || (_cache[11] = [
                _createTextVNode$y("扫描（只读）", -1)
              ]))]),
              _: 1
            }, 8, ["loading"]),
            _createVNode$y(_component_VBtn, {
              size: "small",
              variant: "flat",
              color: "primary",
              "prepend-icon": "mdi-seal",
              disabled: claimBatchDisabled(),
              onClick: _cache[4] || (_cache[4] = $event => (emit('ask', 'batch', null)))
            }, {
              default: _withCtx$w(() => [
                _createTextVNode$y("认领本轮 " + _toDisplayString$z(claimRequestable()) + " 个", 1)
              ]),
              _: 1
            }, 8, ["disabled"])
          ]),
          (claimBatchHint())
            ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_5$t, _toDisplayString$z(claimBatchHint()), 1))
            : _createCommentVNode$w("", true),
          _createVNode$y(_component_VCardText, { class: "magicflow-claim-body" }, {
            default: _withCtx$w(() => [
              (__props.claimLoading)
                ? (_openBlock$z(), _createBlock$w(_component_VAlert, {
                    key: 0,
                    type: "info",
                    variant: "tonal",
                    density: "compact",
                    class: "mb-2"
                  }, {
                    default: _withCtx$w(() => [...(_cache[12] || (_cache[12] = [
                      _createTextVNode$y(" 正在加载认领状态… ", -1)
                    ]))]),
                    _: 1
                  }))
                : (!__props.claimCfg.enabled)
                  ? (_openBlock$z(), _createBlock$w(_component_VAlert, {
                      key: 1,
                      type: "info",
                      variant: "tonal",
                      density: "compact",
                      class: "mb-2"
                    }, {
                      default: _withCtx$w(() => [...(_cache[13] || (_cache[13] = [
                        _createTextVNode$y(" 认领未开启。开启：插件设置 → 认领。 ", -1)
                      ]))]),
                      _: 1
                    }))
                  : (__props.claimCfg.dry)
                    ? (_openBlock$z(), _createBlock$w(_component_VAlert, {
                        key: 2,
                        type: "warning",
                        variant: "tonal",
                        density: "compact",
                        class: "mb-2"
                      }, {
                        default: _withCtx$w(() => [...(_cache[14] || (_cache[14] = [
                          _createTextVNode$y(" 干跑中：执行认领已禁用。 ", -1)
                        ]))]),
                        _: 1
                      }))
                    : _createCommentVNode$w("", true),
              _createElementVNode$z("div", _hoisted_6$r, [
                _createElementVNode$z("div", _hoisted_7$p, [
                  _createElementVNode$z("b", null, _toDisplayString$z(claimNum(claimSummaryClaimed.value)), 1),
                  _cache[15] || (_cache[15] = _createElementVNode$z("span", null, "认领", -1))
                ]),
                _createElementVNode$z("div", _hoisted_8$n, [
                  _createElementVNode$z("b", null, _toDisplayString$z(claimSummarySettle.value), 1),
                  _cache[16] || (_cache[16] = _createElementVNode$z("span", null, "结算", -1))
                ]),
                _createElementVNode$z("div", _hoisted_9$l, [
                  _createElementVNode$z("b", null, _toDisplayString$z(claimSummaryRewardText.value), 1),
                  _cache[17] || (_cache[17] = _createElementVNode$z("span", null, "合计奖励", -1))
                ])
              ]),
              (claimScopeSite.value)
                ? (_openBlock$z(), _createElementBlock$v(_Fragment$v, { key: 3 }, [
                    _createElementVNode$z("div", _hoisted_10$l, [
                      _createVNode$y(_component_VBtn, {
                        size: "small",
                        variant: claimListTab.value === 'claimed' ? 'flat' : 'text',
                        color: "primary",
                        onClick: _cache[5] || (_cache[5] = $event => (claimListTab.value = 'claimed'))
                      }, {
                        default: _withCtx$w(() => [
                          _createTextVNode$y(" 已认领（" + _toDisplayString$z(claimFilteredClaimed.value.length) + "） ", 1)
                        ]),
                        _: 1
                      }, 8, ["variant"]),
                      _createVNode$y(_component_VBtn, {
                        size: "small",
                        variant: claimListTab.value === 'claimable' ? 'flat' : 'text',
                        color: "primary",
                        onClick: _cache[6] || (_cache[6] = $event => (claimListTab.value = 'claimable'))
                      }, {
                        default: _withCtx$w(() => [
                          _createTextVNode$y(" 可认领（" + _toDisplayString$z(claimFilteredClaimable.value.length) + "） ", 1)
                        ]),
                        _: 1
                      }, 8, ["variant"])
                    ]),
                    (claimListTab.value === 'claimed')
                      ? (_openBlock$z(), _createElementBlock$v(_Fragment$v, { key: 0 }, [
                          (!claimFilteredClaimed.value.length)
                            ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_11$k, "还没有已认领种子"))
                            : (_openBlock$z(), _createElementBlock$v("ul", _hoisted_12$k, [
                                (_openBlock$z(true), _createElementBlock$v(_Fragment$v, null, _renderList$t(claimShownClaimed.value, (row) => {
                                  return (_openBlock$z(), _createElementBlock$v("li", {
                                    key: row.hash || (row.site_id + ':' + row.torrent_id),
                                    class: "magicflow-claim-item is-claimed"
                                  }, [
                                    _createElementVNode$z("div", _hoisted_13$i, [
                                      _createElementVNode$z("div", _hoisted_14$h, [
                                        _createVNode$y(_component_VChip, {
                                          size: "x-small",
                                          variant: "tonal",
                                          class: "magicflow-claim-item__site"
                                        }, {
                                          default: _withCtx$w(() => [
                                            _createTextVNode$y(_toDisplayString$z(row.site_name), 1)
                                          ]),
                                          _: 2
                                        }, 1024),
                                        _createElementVNode$z("span", {
                                          class: "magicflow-claim-item__title",
                                          title: row.title || row.hash
                                        }, _toDisplayString$z(claimRowName(row)), 9, _hoisted_15$h),
                                        (claimRowDetailUrl(row))
                                          ? (_openBlock$z(), _createElementBlock$v("a", {
                                              key: 0,
                                              href: claimRowDetailUrl(row),
                                              target: "_blank",
                                              rel: "noopener",
                                              class: "magicflow-claim-item__link",
                                              title: "在站点打开详情页（看原名与简介）"
                                            }, [
                                              _createVNode$y(_component_VIcon, {
                                                icon: "mdi-open-in-new",
                                                size: "13"
                                              })
                                            ], 8, _hoisted_16$h))
                                          : _createCommentVNode$w("", true)
                                      ]),
                                      (claimRowSpec(row))
                                        ? (_openBlock$z(), _createElementBlock$v("span", _hoisted_17$h, _toDisplayString$z(claimRowSpec(row)), 1))
                                        : _createCommentVNode$w("", true),
                                      _createElementVNode$z("span", _hoisted_18$h, [
                                        _createTextVNode$y(_toDisplayString$z(row.site_only ? '站点侧' : '账本') + " · 奖励 " + _toDisplayString$z(claimRowReward(row)), 1),
                                        (row.site_seed_time)
                                          ? (_openBlock$z(), _createElementBlock$v(_Fragment$v, { key: 0 }, [
                                              _createTextVNode$y(" · 做种 " + _toDisplayString$z(row.site_seed_time), 1)
                                            ], 64))
                                          : _createCommentVNode$w("", true),
                                        _cache[18] || (_cache[18] = _createTextVNode$y(" · ", -1)),
                                        _createElementVNode$z("span", {
                                          class: _normalizeClass$i(claimCanAbandon(row) ? 'is-safe' : 'is-blocked')
                                        }, _toDisplayString$z(claimAbandonTag(row)), 3)
                                      ]),
                                      (claimAbandonBlockedText(row))
                                        ? (_openBlock$z(), _createElementBlock$v("span", _hoisted_19$g, _toDisplayString$z(claimAbandonBlockedText(row)), 1))
                                        : _createCommentVNode$w("", true)
                                    ]),
                                    _createVNode$y(_component_VChip, {
                                      size: "x-small",
                                      color: claimQbColor(row),
                                      variant: "tonal"
                                    }, {
                                      default: _withCtx$w(() => [
                                        _createTextVNode$y(_toDisplayString$z(claimQbText(row)), 1)
                                      ]),
                                      _: 2
                                    }, 1032, ["color"]),
                                    _createVNode$y(_component_VBtn, {
                                      size: "x-small",
                                      variant: "text",
                                      color: "error",
                                      "prepend-icon": "mdi-close-octagon-outline",
                                      disabled: !claimCanAbandon(row),
                                      title: row.abandon_reason || '',
                                      loading: __props.claimActing === claimAbandonKey(row),
                                      onClick: $event => (emit('ask', 'abandon', row))
                                    }, {
                                      default: _withCtx$w(() => [...(_cache[19] || (_cache[19] = [
                                        _createTextVNode$y("放弃", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["disabled", "title", "loading", "onClick"]),
                                    _createVNode$y(_component_VChip, {
                                      size: "x-small",
                                      color: "success",
                                      variant: "tonal",
                                      "prepend-icon": "mdi-shield-lock-outline"
                                    }, {
                                      default: _withCtx$w(() => [...(_cache[20] || (_cache[20] = [
                                        _createTextVNode$y("硬保护", -1)
                                      ]))]),
                                      _: 1
                                    })
                                  ]))
                                }), 128))
                              ])),
                          (claimFilteredClaimed.value.length > claimShownClaimed.value.length)
                            ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_20$e, [
                                _createVNode$y(_component_VBtn, {
                                  size: "x-small",
                                  variant: "text",
                                  onClick: claimMoreClaimed
                                }, {
                                  default: _withCtx$w(() => [
                                    _createTextVNode$y("加载更多（" + _toDisplayString$z(claimShownClaimed.value.length) + " / " + _toDisplayString$z(claimFilteredClaimed.value.length) + "）", 1)
                                  ]),
                                  _: 1
                                })
                              ]))
                            : _createCommentVNode$w("", true)
                        ], 64))
                      : (_openBlock$z(), _createElementBlock$v(_Fragment$v, { key: 1 }, [
                          (!claimFilteredClaimable.value.length)
                            ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_21$d, [
                                _cache[21] || (_cache[21] = _createTextVNode$y(" 当前没有可认领种子 ", -1)),
                                (claimEmptyReason.value)
                                  ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_22$c, _toDisplayString$z(claimEmptyReason.value), 1))
                                  : _createCommentVNode$w("", true)
                              ]))
                            : (_openBlock$z(), _createElementBlock$v("ul", _hoisted_23$b, [
                                (_openBlock$z(true), _createElementBlock$v(_Fragment$v, null, _renderList$t(claimShownClaimable.value, (row) => {
                                  return (_openBlock$z(), _createElementBlock$v("li", {
                                    key: row.hash,
                                    class: "magicflow-claim-item"
                                  }, [
                                    _createElementVNode$z("div", _hoisted_24$b, [
                                      _createElementVNode$z("div", _hoisted_25$b, [
                                        _createVNode$y(_component_VChip, {
                                          size: "x-small",
                                          variant: "tonal",
                                          class: "magicflow-claim-item__site"
                                        }, {
                                          default: _withCtx$w(() => [
                                            _createTextVNode$y(_toDisplayString$z(row.site_name), 1)
                                          ]),
                                          _: 2
                                        }, 1024),
                                        _createElementVNode$z("span", {
                                          class: "magicflow-claim-item__title",
                                          title: row.title || row.hash
                                        }, _toDisplayString$z(claimRowName(row)), 9, _hoisted_26$9),
                                        (claimRowDetailUrl(row))
                                          ? (_openBlock$z(), _createElementBlock$v("a", {
                                              key: 0,
                                              href: claimRowDetailUrl(row),
                                              target: "_blank",
                                              rel: "noopener",
                                              class: "magicflow-claim-item__link",
                                              title: "在站点打开详情页（看原名与简介）"
                                            }, [
                                              _createVNode$y(_component_VIcon, {
                                                icon: "mdi-open-in-new",
                                                size: "13"
                                              })
                                            ], 8, _hoisted_27$9))
                                          : _createCommentVNode$w("", true)
                                      ]),
                                      (claimRowSpec(row))
                                        ? (_openBlock$z(), _createElementBlock$v("span", _hoisted_28$8, _toDisplayString$z(claimRowSpec(row)), 1))
                                        : _createCommentVNode$w("", true),
                                      _createElementVNode$z("span", _hoisted_29$8, _toDisplayString$z(claimRowMeta(row)), 1),
                                      (row.reward_block)
                                        ? (_openBlock$z(), _createElementBlock$v("span", _hoisted_30$8, [
                                            _createVNode$y(_component_VIcon, {
                                              icon: "mdi-information-outline",
                                              size: "12"
                                            }),
                                            _createTextVNode$y(_toDisplayString$z(row.reward_block), 1)
                                          ]))
                                        : _createCommentVNode$w("", true)
                                    ]),
                                    _createVNode$y(_component_VBtn, {
                                      size: "x-small",
                                      variant: "flat",
                                      color: "primary",
                                      "prepend-icon": "mdi-seal",
                                      disabled: __props.claimCfg.dry,
                                      loading: __props.claimActing === ('do:' + row.hash),
                                      onClick: $event => (emit('ask', 'do', row))
                                    }, {
                                      default: _withCtx$w(() => [...(_cache[22] || (_cache[22] = [
                                        _createTextVNode$y("认领", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["disabled", "loading", "onClick"])
                                  ]))
                                }), 128))
                              ])),
                          (claimFilteredClaimable.value.length > claimShownClaimable.value.length)
                            ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_31$8, [
                                _createVNode$y(_component_VBtn, {
                                  size: "x-small",
                                  variant: "text",
                                  onClick: claimMoreClaimable
                                }, {
                                  default: _withCtx$w(() => [
                                    _createTextVNode$y("加载更多（" + _toDisplayString$z(claimShownClaimable.value.length) + " / " + _toDisplayString$z(claimFilteredClaimable.value.length) + "）", 1)
                                  ]),
                                  _: 1
                                })
                              ]))
                            : _createCommentVNode$w("", true),
                          (claimSoonSorted.value.length)
                            ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_32$8, [
                                _createElementVNode$z("button", {
                                  type: "button",
                                  class: "magicflow-claim-soon__head",
                                  onClick: _cache[7] || (_cache[7] = $event => (claimSoonOpen.value = !claimSoonOpen.value))
                                }, [
                                  _createVNode$y(_component_VIcon, {
                                    icon: claimSoonOpen.value ? 'mdi-chevron-down' : 'mdi-chevron-right',
                                    size: "16"
                                  }, null, 8, ["icon"]),
                                  _createElementVNode$z("span", null, "还有 " + _toDisplayString$z(claimSoonTotalText.value) + " 颗要等资格日", 1),
                                  _createElementVNode$z("span", _hoisted_33$7, "最近一颗 " + _toDisplayString$z(claimWaitText(claimSoonSorted.value[0])), 1)
                                ]),
                                (claimSoonOpen.value)
                                  ? (_openBlock$z(), _createElementBlock$v("ul", _hoisted_34$7, [
                                      (_openBlock$z(true), _createElementBlock$v(_Fragment$v, null, _renderList$t(claimSoonShown.value, (row) => {
                                        return (_openBlock$z(), _createElementBlock$v("li", {
                                          key: (row.site_id || '') + ':' + (row.hash || row.torrent_id),
                                          class: "magicflow-claim-item is-dim"
                                        }, [
                                          _createElementVNode$z("div", _hoisted_35$6, [
                                            _createElementVNode$z("div", _hoisted_36$5, [
                                              _createVNode$y(_component_VChip, {
                                                size: "x-small",
                                                variant: "tonal",
                                                class: "magicflow-claim-item__site"
                                              }, {
                                                default: _withCtx$w(() => [
                                                  _createTextVNode$y(_toDisplayString$z(row.site_name), 1)
                                                ]),
                                                _: 2
                                              }, 1024),
                                              _createElementVNode$z("span", {
                                                class: "magicflow-claim-item__title",
                                                title: row.title
                                              }, _toDisplayString$z(claimRowName(row)), 9, _hoisted_37$4),
                                              (claimRowDetailUrl(row))
                                                ? (_openBlock$z(), _createElementBlock$v("a", {
                                                    key: 0,
                                                    href: claimRowDetailUrl(row),
                                                    target: "_blank",
                                                    rel: "noopener",
                                                    class: "magicflow-claim-item__link",
                                                    title: "在站点打开详情页（看原名与简介）"
                                                  }, [
                                                    _createVNode$y(_component_VIcon, {
                                                      icon: "mdi-open-in-new",
                                                      size: "13"
                                                    })
                                                  ], 8, _hoisted_38$4))
                                                : _createCommentVNode$w("", true)
                                            ]),
                                            (claimRowSpec(row))
                                              ? (_openBlock$z(), _createElementBlock$v("span", _hoisted_39$4, _toDisplayString$z(claimRowSpec(row)), 1))
                                              : _createCommentVNode$w("", true),
                                            _createElementVNode$z("span", _hoisted_40$4, _toDisplayString$z(row.size_gb) + "G · 发布 " + _toDisplayString$z(claimAgeText(row.age_days)), 1)
                                          ]),
                                          _createVNode$y(_component_VChip, {
                                            size: "x-small",
                                            color: "warning",
                                            variant: "tonal"
                                          }, {
                                            default: _withCtx$w(() => [
                                              _createTextVNode$y(_toDisplayString$z(claimWaitText(row)), 1)
                                            ]),
                                            _: 2
                                          }, 1024)
                                        ]))
                                      }), 128))
                                    ]))
                                  : _createCommentVNode$w("", true),
                                (claimSoonOpen.value && claimSoonSorted.value.length > claimSoonShown.value.length)
                                  ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_41$4, [
                                      _createVNode$y(_component_VBtn, {
                                        size: "x-small",
                                        variant: "text",
                                        onClick: claimMoreSoon
                                      }, {
                                        default: _withCtx$w(() => [
                                          _createTextVNode$y("加载更多（" + _toDisplayString$z(claimSoonShown.value.length) + " / " + _toDisplayString$z(claimSoonSorted.value.length) + "）", 1)
                                        ]),
                                        _: 1
                                      })
                                    ]))
                                  : _createCommentVNode$w("", true)
                              ]))
                            : _createCommentVNode$w("", true)
                        ], 64))
                  ], 64))
                : (_openBlock$z(), _createElementBlock$v(_Fragment$v, { key: 4 }, [
                    (!claimScopeSite.value)
                      ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_42$3, [
                          (_openBlock$z(true), _createElementBlock$v(_Fragment$v, null, _renderList$t(claimSupportedList.value, (s) => {
                            return (_openBlock$z(), _createElementBlock$v("div", {
                              key: s.site_id,
                              class: "magicflow-claim-site",
                              role: "button",
                              tabindex: "0",
                              onClick: $event => (claimSiteFilter.value = String(s.site_id)),
                              onKeydown: [
                                _withKeys$2($event => (claimSiteFilter.value = String(s.site_id)), ["enter"]),
                                _withKeys$2(_withModifiers$3($event => (claimSiteFilter.value = String(s.site_id)), ["prevent"]), ["space"])
                              ]
                            }, [
                              _createElementVNode$z("div", _hoisted_44$2, [
                                _createElementVNode$z("div", _hoisted_45$2, _toDisplayString$z(s.site_name), 1),
                                _createVNode$y(_component_VChip, {
                                  size: "x-small",
                                  color: "primary",
                                  variant: "tonal"
                                }, {
                                  default: _withCtx$w(() => [
                                    _createTextVNode$y(_toDisplayString$z(claimSiteCycleText(s)), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createElementVNode$z("span", _hoisted_46$2, _toDisplayString$z(claimSiteDateText(s)), 1),
                                _createVNode$y(_component_VIcon, {
                                  icon: "mdi-chevron-right",
                                  size: "18"
                                })
                              ]),
                              _createElementVNode$z("div", _hoisted_47$2, [
                                _createElementVNode$z("div", _hoisted_48$2, [
                                  _createElementVNode$z("b", null, _toDisplayString$z(claimNum(s.claimed)), 1),
                                  _cache[23] || (_cache[23] = _createElementVNode$z("span", null, "已认领", -1))
                                ]),
                                _createElementVNode$z("div", _hoisted_49$2, [
                                  _createElementVNode$z("b", null, _toDisplayString$z(claimNum(s.claimable)), 1),
                                  _cache[24] || (_cache[24] = _createElementVNode$z("span", null, "可认领", -1))
                                ]),
                                _createElementVNode$z("div", _hoisted_50$2, [
                                  _createElementVNode$z("b", null, _toDisplayString$z(claimSiteReward(s)), 1),
                                  _cache[25] || (_cache[25] = _createElementVNode$z("span", null, "奖励", -1))
                                ])
                              ]),
                              (claimSiteRowText(s))
                                ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_51$2, _toDisplayString$z(claimSiteRowText(s)), 1))
                                : _createCommentVNode$w("", true)
                            ], 40, _hoisted_43$2))
                          }), 128)),
                          (!__props.claimLoading && !claimSupportedList.value.length)
                            ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_52$2, "没有支持认领的站点（认领预设表未收录；见 docs/认领.md）。"))
                            : _createCommentVNode$w("", true),
                          (claimSkipped.value.length)
                            ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_53$2, [
                                _createTextVNode$y(" 未收录认领（跳过）：" + _toDisplayString$z(claimSkipped.value.slice(0, 8).join('、')), 1),
                                (claimSkipped.value.length > 8)
                                  ? (_openBlock$z(), _createElementBlock$v(_Fragment$v, { key: 0 }, [
                                      _createTextVNode$y(" 等 " + _toDisplayString$z(claimSkipped.value.length) + " 站", 1)
                                    ], 64))
                                  : _createCommentVNode$w("", true)
                              ]))
                            : _createCommentVNode$w("", true)
                        ]))
                      : _createCommentVNode$w("", true)
                  ], 64)),
              _createElementVNode$z("div", _hoisted_54$2, [
                _createVNode$y(_component_VIcon, {
                  icon: "mdi-information-outline",
                  size: "14"
                }),
                _cache[26] || (_cache[26] = _createElementVNode$z("span", null, "认领后进硬保护；不达标可能扣魔力。", -1))
              ]),
              (claimHost.value.total)
                ? (_openBlock$z(), _createElementBlock$v("div", _hoisted_55$2, [
                    _createVNode$y(_component_VIcon, {
                      icon: "mdi-shield-check-outline",
                      size: "14"
                    }),
                    _createElementVNode$z("span", null, "保挂：" + _toDisplayString$z(claimHost.value.total) + " 个已认领 · 做种 " + _toDisplayString$z(claimHost.value.seeding) + " · 暂停 " + _toDisplayString$z(claimHost.value.paused) + " · 丢失 " + _toDisplayString$z(claimHost.value.missing), 1)
                  ]))
                : _createCommentVNode$w("", true)
            ]),
            _: 1
          })
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
const ClaimDialog = Object.assign(_sfc_main$z, { __scopeId: 'data-v-2acf1ac2' })

export default ClaimDialog
