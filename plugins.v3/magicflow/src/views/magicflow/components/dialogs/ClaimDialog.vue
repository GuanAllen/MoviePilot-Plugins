<script setup>
// MagicFlow 前端 · 认领弹窗。setup 逻辑 100% 来自线上 19.16.14 dist 还原的 ClaimDialog.js
// （零功能丢失：digest/规格/详情直链/放弃安全/soon 折叠/空原因/qb 状态全部保留），
// 本版只按设计稿重构视图层（全站汇总默认落地 + 分段控件 + 卡片瘦身），template 重写。
import { computed, ref } from 'vue'

const props = defineProps({
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
})
const emit = defineEmits(['refresh', 'scan', 'ask'])
const claimOpen = defineModel({ type: Boolean, default: false })


// 数据向下（只读）：claimData 为原始后端状态，其余为父页派生数组（单一真值源在父页）。


// ★ 19.16.15：视图切换从「下拉首项」提升为独立分段控件——
//   claimView='all' 全站汇总（默认落地，进来就看全站口径）；='site' 按站点看（单站明细）。
//   下拉只做「过滤到具体站」一件事，不再偷偷换结构；选具体站 = 进入 site 视图。
const claimView = ref('all');
function claimSetView(v) {
  claimView.value = v
  if (v === 'all') claimSiteFilter.value = ''
  else if (!claimSiteFilter.value) {
    const first = (props.claimSites || []).find((s) => s.supported)
    if (first) claimSiteFilter.value = String(first.site_id)
  }
}
const claimSiteFilter = ref('');
const claimFilterItems = computed(() => (props.claimSites || []).map((s) => ({
  title: `${s.site_name || s.domain}${s.supported ? '' : '（未收录）'}`,
  value: String(s.site_id),
})));
function claimFilterSite() {
  if (!claimSiteFilter.value) return null
  return (props.claimSites || []).find((s) => String(s.site_id) === claimSiteFilter.value) || null
}
// 站点列表：只列支持认领的站。全站视图逐站汇总，不跨站求和。
const claimSupportedList = computed(() => (props.claimSites || []).filter((s) => s.supported));
// 点逐站卡：进 site 视图并选中该站。
function claimOpenSite(sid) { claimView.value = 'site'; claimSiteFilter.value = String(sid) }
// 下拉选站：非空即进 site 视图。
function claimPickSite(v) { claimSiteFilter.value = v; claimView.value = v ? 'site' : 'all' }
// claimScopeSite 保持「只认当前选中的具体站」，全站视图下它为空（逐站卡走 claimSupportedList）。
const claimScopeSite = computed(() => (claimView.value === 'site' ? claimFilterSite() : null));
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
// 19.16.17：结算条拆三段（结算｜日期｜剩 X 天靠右），复用同一份 settlement 真值，文案数值不动。
function claimSettleDate(s) {
  const st = claimSiteSettle(s);
  if (!st.next_settle_at) return '结算日待定'
  const d = new Date(st.next_settle_at * 1000);
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
}
function claimSettleDays(s) {
  const st = claimSiteSettle(s);
  if (st.days_left === null || st.days_left === undefined) return ''
  return `剩 ${Number(st.days_left).toFixed(1)} 天`
}
const claimSettleSite = computed(() => {
  if (claimScopeSite.value) return claimScopeSite.value
  const rows = (props.claimSites || []).filter(s => s.supported && s.settlement && s.settlement.next_settle_at)
  if (!rows.length) return null
  const min = Math.min(...rows.map(s => Number(s.settlement.next_settle_at)))
  return rows.find(x => Number(x.settlement.next_settle_at) === min) || null
})
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
const claimFilteredClaimable = computed(() => claimRowsFor(props.claimClaimable, claimSiteFilter.value));
const claimFilteredClaimed = computed(() => claimRowsFor(props.claimClaimed, claimSiteFilter.value));
const claimFilteredSoon = computed(() => claimRowsFor(props.claimSoon, claimSiteFilter.value));
// ── ★ 19.10.59「可认领为零」要能自证原因 ─────────────────────────────────────
// 学校（pt.btschool.club）实测 2026-10-31：站点「当前活动」= 做种 4 颗，这 4 颗
// （326608 / 326427 / 326419 / 326403）全在 viewclaims.php 里，4 个详情页也都
// 不再有 add_torrent_id → 可认领 0 是**真值**，不是漏扫。
// 但界面只写「当前没有可认领种子」，用户没法区分「真没有」与「扫描坏了」。
// 这里只用扫描结果里**已有**的站点统计（site_rows / site_claimed / site_open /
// site_not_local / soon 条数）拼一句实话：零额外请求，也不在本地重算站点口径。
const claimEmptyReason = computed(() => {
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
const claimClaimedLimit = ref(20);
const claimClaimableLimit = ref(20);
const claimShownClaimed = computed(() => claimFilteredClaimed.value.slice(0, claimClaimedLimit.value));
const claimShownClaimable = computed(() => claimFilteredClaimable.value.slice(0, claimClaimableLimit.value));
function claimMoreClaimed() { claimClaimedLimit.value += 20; }
function claimMoreClaimable() { claimClaimableLimit.value += 20; }
const claimListTab = ref('claimed');
const claimSummaryClaimed = computed(() => claimFilteredClaimed.value.length);
const claimSummaryReward = computed(() => {
  let n = 0;
  for (const r of claimFilteredClaimed.value) {
    const v = Number(r.site_reward_num);
    if (Number.isFinite(v)) n += v;
  }
  return n
});
const claimSummaryRewardText = computed(() => claimSummaryReward.value > 0 ? claimNum(claimSummaryReward.value) : '—');
const claimSummarySettle = computed(() => {
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
const claimSoonOpen = ref(false);
const claimSoonLimit = ref(10);
const claimSoonSorted = computed(() => {
  const list = (claimFilteredSoon.value || []).slice();
  list.sort((a, b) => (Number(a.wait_days ?? 1e9)) - (Number(b.wait_days ?? 1e9)));
  return list
});
const claimSoonShown = computed(() => claimSoonSorted.value.slice(0, claimSoonLimit.value));
function claimMoreSoon() { claimSoonLimit.value += 10; }
const claimSoonTotalText = computed(() => {
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
const claimHost = computed(() => props.claimData.host || {});
function claimQbKind(row) {
  if (row && row.site_only) return 'site'
  if (!row || !row.in_qb) return 'missing'
  const s = String(row.qb_state || '').toLowerCase();
  if (s.includes('paus') || s.includes('stop')) return 'paused'
  return 'seeding'
}
function claimQbText(row) {
  const k = claimQbKind(row);
  // 19.16.18：按设计稿，状态 chip 用 2 字短语（做种/暂停/丢失/站点侧），
  // 避免 3 字「做种中」在窄屏被盾牌挤成「做种 0」的错觉。
  if (k === 'site') return '站点侧'
  return k === 'seeding' ? '做种' : (k === 'paused' ? '暂停' : '丢失')
}
function claimQbClass(row) {
  const k = claimQbKind(row);
  return 'magicflow-claim-qb is-' + k
}
function claimQbTitle(row) {
  const k = claimQbKind(row);
  if (k === 'site') return '仅站点侧认领，未纳入本机 qB'
  if (k === 'seeding') return 'qB 中正在做种'
  if (k === 'paused') return 'qB 中已暂停，需恢复做种'
  return 'qB 中未找到该种子'
}
// ── ★ 19.5.0：干跑 / 真跑两个动作彻底分开（用户可见文案，短句）──
//   顶栏常驻模式徽标；「扫描（只读）」永不写；「认领本轮」常驻但禁用时给出原因。
const claimModeText = computed(() => (props.claimCfg.dry ? '干跑' : '真跑'));
const claimSkipped = computed(() => props.claimData.sites_skipped || []);
computed(() => Number(props.claimData.sites_total || 0));
computed(() => Number(props.claimData.sites_supported_total || 0));
// ★ 19.6.0「其他站点纳入」：规则未核对的站（preset 用同族插件默认值）——UI 必须如实标注。
computed(() => {
  const n = Number(props.claimData.sites_unverified_total || 0);
  if (n > 0) return n
  return (props.claimSites || []).filter((s) => s.supported && claimProfile(s).rules_unverified).length
});
computed(() => props.claimData.sites_unverified || []);
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
</script>
<template>
  <VDialog v-model="claimOpen" max-width="52rem" scrollable :fullscreen="isNarrow">
    <VCard class="magicflow-dialog magicflow-claim-dialog">
      <header class="magicflow-settings-dialog__head">
        <div class="magicflow-claim-title">
          <span class="magicflow-settings-dialog__title">认领</span>
          <VChip size="x-small" :color="claimCfg.dry ? 'warning' : 'success'" variant="tonal">
            {{ claimModeText }}
          </VChip>
        </div>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" :loading="claimLoading" @click="emit('refresh')">刷新</VBtn>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="claimOpen = false" />
        </div>
      </header>
      <VDivider />
      <div class="magicflow-claim-bar">
        <!-- 19.16.17：bar 只放两个按钮（设计稿），分段控件移到 body 顶部（按钮行下方） -->
        <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-radar" :loading="claimActing === 'run'" @click="emit('scan')">扫描（只读）</VBtn>
        <VBtn size="small" variant="flat" color="primary" prepend-icon="mdi-seal"
          :disabled="claimBatchDisabled()" @click="emit('ask', 'batch', null)">
          认领本轮 <small class="magicflow-claim-bar__tot">{{ claimNum(claimRequestable()) }}</small> 个
        </VBtn>
      </div>
      <div v-if="claimBatchHint()" class="magicflow-claim-bar__hint">{{ claimBatchHint() }}</div>
      <VCardText class="magicflow-claim-body">
        <VAlert v-if="claimLoading" type="info" variant="tonal" density="compact" class="mb-2">正在加载认领状态…</VAlert>
        <VAlert v-else-if="!claimCfg.enabled" type="info" variant="tonal" density="compact" class="mb-2">认领未开启。开启：插件设置 → 认领。</VAlert>
        <VAlert v-else-if="claimCfg.dry" type="warning" variant="tonal" density="compact" class="mb-2">干跑中：执行认领已禁用。</VAlert>

        <!-- 视图切换分段控件：设计稿里在按钮行下方、正文顶部 -->
        <div class="magicflow-claim-seg" role="tablist" aria-label="认领视图">
          <button type="button" role="tab" :aria-selected="claimView === 'all'"
            :class="['magicflow-claim-seg__b' + (claimView === 'all' ? ' is-on' : '')]"
            @click="claimSetView('all')">全站汇总</button>
          <button type="button" role="tab" :aria-selected="claimView === 'site'"
            :class="['magicflow-claim-seg__b' + (claimView === 'site' ? ' is-on' : '')]"
            @click="claimSetView('site')">按站点看</button>
        </div>

        <!-- ============ 全站汇总（默认落地）：各站并列，不显示易误导的聚合统计卡 ============ -->
        <template v-if="claimView === 'all'">
          <div class="magicflow-claim-sites">
            <div v-for="s in claimSupportedList" :key="s.site_id"
              class="magicflow-claim-site" role="button" tabindex="0"
              @click="claimOpenSite(s.site_id)"
              @keydown.enter="claimOpenSite(s.site_id)"
              @keydown.space.prevent="claimOpenSite(s.site_id)">
              <div class="magicflow-claim-site__head">
                <div class="magicflow-claim-site__name">{{ s.site_name }}</div>
                <VChip size="x-small" color="primary" variant="tonal">{{ claimSiteCycleText(s) }}</VChip>
                <span class="magicflow-claim-site__date">{{ claimSiteDateText(s) }}</span>
                <VIcon icon="mdi-chevron-right" size="18" />
              </div>
              <div class="magicflow-claim-site__stats">
                <div class="magicflow-claim-site__stat"><b>{{ claimNum(s.claimed) }}</b><span>已认领</span></div>
                <div class="magicflow-claim-site__stat"><b>{{ claimNum(s.claimable) }}</b><span>可认领</span></div>
                <div class="magicflow-claim-site__stat is-accent"><b>{{ claimSiteReward(s) }}</b><span>奖励</span></div>
              </div>
              <div v-if="claimSiteRowText(s)" class="magicflow-claim-site__sub">{{ claimSiteRowText(s) }}</div>
            </div>
            <div v-if="!claimLoading && !claimSupportedList.length" class="magicflow-table-empty">没有支持认领的站点（认领预设表未收录；见 docs/认领.md）。</div>
            <div v-if="claimSkipped.length" class="magicflow-claim-more">
              未收录认领（跳过）：{{ claimSkipped.slice(0, 8).join('、') }}<template v-if="claimSkipped.length > 8"> 等 {{ claimSkipped.length }} 站</template>
            </div>
          </div>
          <div class="magicflow-claim-nosum">⊘ 各站并列 · 奖励口径不同 · 无跨站合计</div>
        </template>

        <!-- ============ 按站点看：单站明细 ============ -->
        <template v-else>
          <VSelect v-model="claimSiteFilter" :items="claimFilterItems" density="compact" variant="outlined"
            hide-details class="magicflow-claim-bar__site" aria-label="站点筛选"
            @update:modelValue="claimPickSite" />
          <div class="magicflow-claim-summary magicflow-claim-summary--two">
            <div class="magicflow-claim-summary__item"><b>{{ claimNum(claimSummaryClaimed) }}</b><span><i class="magicflow-claim-summary__scope">本站</i> 已认领</span></div>
            <div class="magicflow-claim-summary__item is-accent"><b>{{ claimSummaryRewardText }}</b><span><i class="magicflow-claim-summary__scope">本站</i> 合计奖励</span></div>
          </div>
          <div class="magicflow-claim-settle">
            <span class="magicflow-claim-settle__k">◷ 结算</span>
            <span>{{ claimSettleDate(claimSettleSite) }}</span>
            <span class="magicflow-claim-settle__d">{{ claimSettleDays(claimSettleSite) }}</span>
          </div>
          <div class="magicflow-claim-tabs">
            <VBtn size="small" :variant="claimListTab === 'claimed' ? 'flat' : 'text'" color="primary" @click="claimListTab = 'claimed'">
              已认领（{{ claimFilteredClaimed.length }}）
            </VBtn>
            <VBtn size="small" :variant="claimListTab === 'claimable' ? 'flat' : 'text'" color="primary" @click="claimListTab = 'claimable'">
              可认领（{{ claimFilteredClaimable.length }}）
            </VBtn>
          </div>
          <div class="magicflow-claim-notice">
            <VIcon icon="mdi-alert-outline" size="14" />
            <span>本站不支持站内放弃，如需放弃请到站点网页操作；认领后进硬保护，不达标可能扣魔力。</span>
          </div>

          <template v-if="claimListTab === 'claimed'">
            <div v-if="!claimFilteredClaimed.length" class="magicflow-table-empty">还没有已认领种子</div>
            <ul v-else class="magicflow-claim-list">
              <li v-for="row in claimShownClaimed" :key="row.hash || (row.site_id + ':' + row.torrent_id)" class="magicflow-claim-item is-claimed">
                <div class="magicflow-claim-item__main">
                  <div class="magicflow-claim-item__head">
                    <span class="magicflow-claim-item__title magicflow-claim-item__title--2" :title="row.title || row.hash">{{ claimRowName(row) }}</span>
                    <a v-if="claimRowDetailUrl(row)" :href="claimRowDetailUrl(row)" target="_blank" rel="noopener"
                      class="magicflow-claim-item__link" title="在站点打开详情页（看原名与简介）">
                      <VIcon icon="mdi-open-in-new" size="13" />
                    </a>
                  </div>
                  <span v-if="claimRowSpec(row)" class="magicflow-claim-item__spec">{{ claimRowSpec(row) }}</span>
                  <span class="magicflow-claim-item__meta">{{ row.site_only ? '站点侧' : '账本' }} · 奖励 {{ claimRowReward(row) }}<template v-if="row.site_seed_time"> · 做种 {{ row.site_seed_time }}</template></span>
                </div>
                <!-- 硬保护：由文字 chip 改为盾牌图标，info 由 tooltip 承载 -->
                <!-- 19.16.18：状态按设计稿自绘 span（绿/黄/灰底+边框+7px圆角），2字短语，flex:0 0 auto 防被盾牌挤 -->
                <span :class="claimQbClass(row)" :title="claimQbTitle(row)">{{ claimQbText(row) }}</span>
                <span class="magicflow-claim-shield" title="已进入硬保护，不会被静默清理"><VIcon icon="mdi-shield-lock-outline" size="15" /></span>
                <!-- 放弃：仅本站支持且安全时显示，不可用时隐藏（说明条已统一解释） -->
                <VBtn v-if="claimCanAbandon(row)" size="x-small" variant="text" color="error"
                  prepend-icon="mdi-close-octagon-outline" :title="row.abandon_reason || ''"
                  :loading="claimActing === claimAbandonKey(row)" @click="emit('ask', 'abandon', row)">放弃</VBtn>
              </li>
            </ul>
            <div v-if="claimFilteredClaimed.length > claimShownClaimed.length" class="magicflow-claim-more">
              <VBtn size="x-small" variant="text" @click="claimMoreClaimed">加载更多（{{ claimShownClaimed.length }} / {{ claimFilteredClaimed.length }}）</VBtn>
            </div>
          </template>

          <template v-else>
            <div v-if="!claimFilteredClaimable.length" class="magicflow-table-empty">
              当前没有可认领种子
              <div v-if="claimEmptyReason" class="magicflow-claim-empty__why">{{ claimEmptyReason }}</div>
            </div>
            <ul v-else class="magicflow-claim-list">
              <li v-for="row in claimShownClaimable" :key="row.hash" class="magicflow-claim-item">
                <div class="magicflow-claim-item__main">
                  <div class="magicflow-claim-item__head">
                    <span class="magicflow-claim-item__title magicflow-claim-item__title--2" :title="row.title || row.hash">{{ claimRowName(row) }}</span>
                    <a v-if="claimRowDetailUrl(row)" :href="claimRowDetailUrl(row)" target="_blank" rel="noopener"
                      class="magicflow-claim-item__link" title="在站点打开详情页（看原名与简介）">
                      <VIcon icon="mdi-open-in-new" size="13" />
                    </a>
                  </div>
                  <span v-if="claimRowSpec(row)" class="magicflow-claim-item__spec">{{ claimRowSpec(row) }}</span>
                  <span class="magicflow-claim-item__meta">{{ claimRowMeta(row) }}</span>
                  <span v-if="row.reward_block" class="magicflow-claim-item__reward"><VIcon icon="mdi-information-outline" size="12" />{{ row.reward_block }}</span>
                </div>
                <VBtn size="x-small" variant="flat" color="primary" prepend-icon="mdi-seal" :disabled="claimCfg.dry"
                  :loading="claimActing === ('do:' + row.hash)" @click="emit('ask', 'do', row)">认领</VBtn>
              </li>
            </ul>
            <div v-if="claimFilteredClaimable.length > claimShownClaimable.length" class="magicflow-claim-more">
              <VBtn size="x-small" variant="text" @click="claimMoreClaimable">加载更多（{{ claimShownClaimable.length }} / {{ claimFilteredClaimable.length }}）</VBtn>
            </div>
            <div v-if="claimSoonSorted.length" class="magicflow-claim-soon">
              <button type="button" class="magicflow-claim-soon__head" @click="claimSoonOpen = !claimSoonOpen">
                <VIcon :icon="claimSoonOpen ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="16" />
                <span>还有 {{ claimSoonTotalText }} 颗要等资格日</span>
                <span class="magicflow-claim-soon__hint">最近一颗 {{ claimWaitText(claimSoonSorted[0]) }}</span>
              </button>
              <ul v-if="claimSoonOpen" class="magicflow-claim-list magicflow-claim-list--soon">
                <li v-for="row in claimSoonShown" :key="(row.site_id || '') + ':' + (row.hash || row.torrent_id)" class="magicflow-claim-item is-dim">
                  <div class="magicflow-claim-item__main">
                    <div class="magicflow-claim-item__head">
                      <span class="magicflow-claim-item__title" :title="row.title">{{ claimRowName(row) }}</span>
                      <a v-if="claimRowDetailUrl(row)" :href="claimRowDetailUrl(row)" target="_blank" rel="noopener"
                        class="magicflow-claim-item__link" title="在站点打开详情页">
                        <VIcon icon="mdi-open-in-new" size="13" />
                      </a>
                    </div>
                    <span v-if="claimRowSpec(row)" class="magicflow-claim-item__spec">{{ claimRowSpec(row) }}</span>
                    <span class="magicflow-claim-item__meta">{{ claimRowMeta(row) }}</span>
                  </div>
                  <VChip size="x-small" color="warning" variant="tonal">{{ claimWaitText(row) }}</VChip>
                </li>
              </ul>
              <div v-if="claimSoonOpen && claimSoonSorted.length > claimSoonShown.length" class="magicflow-claim-more">
                <VBtn size="x-small" variant="text" @click="claimMoreSoon">加载更多（{{ claimSoonShown.length }} / {{ claimSoonSorted.length }}）</VBtn>
              </div>
            </div>
          </template>
        </template>

        <!-- 脚注：全站保挂状态（一句带过，不占统计卡） -->
        <div v-if="claimHost.total" class="magicflow-claim-foot">
          <VIcon icon="mdi-shield-check-outline" size="14" />
          <span>全站 {{ claimHost.total }} 颗保挂中 · 做种 {{ claimHost.seeding }} · 暂停 {{ claimHost.paused }} · 丢失 {{ claimHost.missing }}</span>
        </div>
      </VCardText>
    </VCard>
  </VDialog>
</template>
