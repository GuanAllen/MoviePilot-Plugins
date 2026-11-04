import * as __vue from 'vue'
import { unwrapResponse } from '../../../utils'

// MagicFlow 前端 · 手动保种域 composable（★ 19.10.41）
//
// 职责：手动保种名单（`__keep__` 伪任务）弹窗的状态 + 拉取 + 解除动作，
//       外加「从静默池挑选」候选池（★ 19.10.42）。
// 依赖注入：api、notify、onChanged（解除后通知父页刷新任务/概览）。
//
// ★ 为什么需要它：手动保种落的是 `taken_by=__keep__` 伪任务 —— 它**不是真任务**，
//   所以这批种既不在任何任务的种子池里、也不进 `status.tasks`。挂上之后界面上哪儿都
//   看不见，只能自己记 hash 才能解除（2026-10-30 实测存量 18 个）。后端 `action=hold_list`
//   把名单与下载器实况一次给出，这里只做 UI 侧状态。
// ★ 19.10.42：只有「已挂的 18 个」不够用 —— 静默池里 1000+ 个种没处可挑。候选池
//   （`hold_candidates`）一次给全，过滤 / 分页 / 全选都在这里做；写入仍走 `action=hold`。
// ★ 真值源仍在后端（标签账本 + qB 快照），本文件不缓存业务判断。
const {computed: computed$c, ref: ref$c, watch: watch$2} = __vue

// 一次 hold 请求最多带多少个 hash（★ 19.10.42）。
// 单条 hold 的代价是「改一次 qB 标签 + 落一次账本 + force_start 并读回校验」，
// 1000 个塞进一个请求要跑几分钟，而 API_WORKERS=1 —— 会把整个插件界面卡死。
// 拆成小块逐个发：每块约 2~4 秒，其间前端还能刷新进度。
const HOLD_CHUNK = 20;

// 候选池的新鲜期（毫秒，★ 19.10.43）。
// 静默池每轮静默闸都在收放，切回来必须能看到最新的；但一次拉 1000+ 条要 0.6 秒 / 339KB，
// 挑种时反复切标签页会很难受 —— 60 秒内直接用现有数据。
const CAND_TTL = 60000;

function useKeep({ api, notify, onChanged }) {
  const keepOpen = ref$c(false);
  const keepTab = ref$c('list');      // 'list' = 已挂的 | 'pick' = 从静默池挑选
  const keepLoading = ref$c(false);
  const keepData = ref$c({ total: 0, not_seeding: 0, items: [] });
  const keepOnlyBad = ref$c(false);   // 只看「没在做种」（幽灵行 / 暂停 / 没下完）
  const keepQ = ref$c('');            // 按标题或站点过滤
  const keepSel = ref$c([]);          // 勾选中的 hash（批量解除用）
  const keepBusy = ref$c(false);

  const keepItems = computed$c(() => {
    const kw = String(keepQ.value || '').trim().toLowerCase();
    return (keepData.value.items || []).filter(it => {
      if (keepOnlyBad.value && it.seeding) return false
      if (kw && !`${it.title || ''} ${it.site || ''} ${it.hash || ''}`.toLowerCase().includes(kw)) return false
      return true
    })
  });

  async function loadKeep() {
    keepLoading.value = true;
    try {
      keepData.value = unwrapResponse(await api.settings.keepList()) || keepData.value;
    } catch (err) {
      notify(`读取手动保种名单失败：${err?.message || err}`, 'error');
    } finally {
      keepLoading.value = false;
    }
  }

  // ── 候选池：从静默池里挑要保的种（★ 19.10.42）────────────────────────────
  const candLoading = ref$c(false);
  const candLoaded = ref$c(false);
  const candAt = ref$c(0);            // 上次拉成功的时刻（判新鲜期用）
  const candData = ref$c({ total: 0, size_gb: 0, owed_hr: 0, items: [], sites: [] });
  const candQ = ref$c('');
  const candSite = ref$c('');
  const candSub = ref$c('');
  const candOnlyHr = ref$c(false);
  const candSort = ref$c('site');     // 'site'（按站归堆，后端已排）| 'size' | 'hr'
  const candSel = ref$c([]);          // 勾选中的 hash（数组，便于模板 includes）
  const candPage = ref$c(1);
  const candPer = ref$c(40);

  const candIndex = computed$c(() => {
    const m = new Map();
    for (const it of candData.value.items || []) m.set(String(it.hash || ''), it);
    return m
  });

  const candList = computed$c(() => {
    const kw = String(candQ.value || '').trim().toLowerCase();
    const rows = (candData.value.items || []).filter(it => {
      if (candSite.value && String(it.site || '') !== candSite.value) return false
      if (candSub.value && String(it.sub || '') !== candSub.value) return false
      if (candOnlyHr.value && !it.owed_hr) return false
      if (kw) {
        const hay = `${it.title || ''} ${it.hash || ''} ${it.site_name || ''} ${it.site || ''}`.toLowerCase();
        if (!hay.includes(kw)) return false
      }
      return true
    });
    if (candSort.value === 'size') return [...rows].sort((a, b) => Number(b.size_gb || 0) - Number(a.size_gb || 0))
    if (candSort.value === 'hr') return [...rows].sort((a, b) => Number(!!b.owed_hr) - Number(!!a.owed_hr))
    return rows
  });

  const candPages = computed$c(() => Math.max(1, Math.ceil(candList.value.length / candPer.value)));
  // 过滤后条数变少页码会越界 → 随时夹回最后一页（不要让用户停在空白页）
  watch$2(candPages, (n) => { if (candPage.value > n) candPage.value = Math.max(1, n); });
  const candRows = computed$c(() => {
    const from = (Math.min(candPage.value, candPages.value) - 1) * candPer.value;
    return candList.value.slice(from, from + candPer.value)
  });
  const candSelGb = computed$c(() => candSel.value.reduce(
    (s, h) => s + Number((candIndex.value.get(String(h)) || {}).size_gb || 0), 0));
  const candSelOnPage = computed$c(() => candRows.value.filter(it => candSel.value.includes(String(it.hash))).length);
  const candSubs = computed$c(() => {
    const m = new Map();
    for (const it of candData.value.items || []) {
      const k = String(it.sub || '');
      if (k) m.set(k, (m.get(k) || 0) + 1);
    }
    return [...m.entries()].map(([key, count]) => ({ key, count }))
  });

  async function loadCandidates(resetPage = true) {
    candLoading.value = true;
    try {
      candData.value = unwrapResponse(await api.settings.holdCandidates()) || candData.value;
      candLoaded.value = true;
      candAt.value = Date.now();
      if (resetPage) candPage.value = 1;
    } catch (err) {
      notify(`读取静默池候选失败：${err?.message || err}`, 'error');
    } finally {
      candLoading.value = false;
    }
  }

  /**
   * 候选池是否需要重拉（★ 19.10.43）。
   *
   * 静默池是会自己变的（静默闸每轮都在收放），所以**切回挑选页时要重拉**，
   * 否则看到的还是几分钟前的池子。但又不能每次都拉满 339KB —— 挑种时来回
   * 切标签页很常见，故加 60 秒新鲜期：期内切回来直接用现有数据。
   */
  function candStale() {
    return !candLoaded.value || (Date.now() - Number(candAt.value || 0)) > CAND_TTL
  }

  /** 切标签页：候选池过新鲜期才拉（1000+ 条，0.6 秒 + 339KB，不必要就别拉）。 */
  function switchKeepTab(t) {
    keepTab.value = t === 'pick' ? 'pick' : 'list';
    if (keepTab.value === 'pick' && candStale()) loadCandidates(!candLoaded.value);
    if (keepTab.value === 'list') loadKeep();
  }

  function toggleCandRow(hash) {
    const h = String(hash || '').toLowerCase();
    if (!h) return
    const i = candSel.value.indexOf(h);
    if (i >= 0) candSel.value.splice(i, 1);
    else candSel.value.push(h);
  }

  /** 全选/取消**当前页**（一页 40 条，翻页逐页勾最常用）。 */
  function toggleCandPage() {
    const hs = candRows.value.map(it => String(it.hash || ''));
    const allOn = hs.length > 0 && hs.every(h => candSel.value.includes(h));
    if (allOn) candSel.value = candSel.value.filter(h => !hs.includes(h));
    else candSel.value = [...new Set([...candSel.value, ...hs])];
  }

  /** 全选/取消**当前筛选结果**（含未渲染的页 —— 这才是「所有静默池里的都能选」）。 */
  function toggleCandAll() {
    const hs = candList.value.map(it => String(it.hash || '').toLowerCase());
    const allOn = hs.length > 0 && hs.every(h => candSel.value.includes(h));
    if (allOn) candSel.value = candSel.value.filter(h => !hs.includes(h));
    else candSel.value = [...new Set([...candSel.value, ...hs])];
  }

  function clearCandSel() { candSel.value = []; }

  function candGoto(p) {
    const n = Math.min(Math.max(1, Number(p) || 1), candPages.value);
    candPage.value = n;
  }

  function openKeep() {
    keepOpen.value = true;
    keepSel.value = [];
    if (keepTab.value === 'pick' && candStale()) loadCandidates(!candLoaded.value);
    loadKeep();
  }

  function toggleKeepRow(hash) {
    const h = String(hash || '').toLowerCase();
    if (!h) return
    const i = keepSel.value.indexOf(h);
    if (i >= 0) keepSel.value.splice(i, 1);
    else keepSel.value.push(h);
  }

  function toggleKeepAll() {
    const all = keepItems.value.map(it => String(it.hash || '').toLowerCase());
    keepSel.value = keepSel.value.length >= all.length ? [] : all;
  }

  /** 解除手动保种（退回静默池）。`hashes` 省略时用勾选集合。 */
  async function releaseKeep(hashes) {
    const hs = (Array.isArray(hashes) ? hashes : [hashes]).filter(Boolean);
    const target = hs.length ? hs : keepSel.value;
    if (!target.length) return
    keepBusy.value = true;
    try {
      const r = unwrapResponse(await api.settings.holdSeeds(target, false));
      const n = Number(r?.released ?? 0);
      notify(n > 0 ? `已解除手动保种 ${n} 个 · 已退回静默池` : '没有可解除的种（可能已归别的岗位）');
      keepSel.value = [];
      // ★ 19.10.43 两个方向都要刷：解除后种会**回到静默池候选**，
      //   只刷「已保种」的话，切回挑选页那个种还不在列表里，看起来像没退回去。
      await Promise.all([
        loadKeep(),
        candLoaded.value ? loadCandidates(false) : Promise.resolve(),
      ]);
      if (typeof onChanged === 'function') onChanged();
    } catch (err) {
      notify(`解除失败：${err?.message || err}`, 'error');
    } finally {
      keepBusy.value = false;
    }
  }

  /**
   * 把候选池里的种挂成手动保种（★ 19.10.42）。
   *
   * `hashes` 省略时用勾选集合（批量）；给单个 hash 就是行内「只挂这一条」。
   * ★ **必须分块发**：单条 hold 要改 qB 标签 + 落账本 + force_start 并读回校验，
   *   1000 条塞一个请求要跑几分钟；而插件是 API_WORKERS=1 —— 会把整个界面卡死。
   *   每块 `HOLD_CHUNK` 条，逐块发，其间 notify 进度。
   * ★ 结果按块累加：`held` 是**新增挂载**数，`resumed` 是拉起做种数，两者都可能 < 选择数
   *   （种已不在下载器 / 被更高优先级岗位占着）。
   */
  async function holdSelected(hashes) {
    const one = Array.isArray(hashes) ? hashes.filter(Boolean) : (hashes ? [hashes] : []);
    const target = one.length ? one.map(h => String(h).toLowerCase()) : candSel.value.slice();
    if (!target.length) return
    keepBusy.value = true;
    let held = 0;
    let resumed = 0;
    const fails = [];
    try {
      for (let i = 0; i < target.length; i += HOLD_CHUNK) {
        const part = target.slice(i, i + HOLD_CHUNK);
        const r = unwrapResponse(await api.settings.holdSeeds(part, true)) || {};
        held += Number(r.held || 0);
        resumed += Number(r.resumed || 0);
        if (Array.isArray(r.resume_failed)) fails.push(...r.resume_failed);
        if (target.length > HOLD_CHUNK) {
          notify(`挂手动保种 ${Math.min(i + HOLD_CHUNK, target.length)}/${target.length}…`);
        }
      }
      const extra = [];
      if (resumed) extra.push(`拉起做种 ${resumed} 个`);
      if (fails.length) extra.push(`拉起失败 ${fails.length} 个`);
      notify(`已挂手动保种 ${held} 个${extra.length ? ` · ${extra.join(' · ')}` : ''}`);
      // 挂上的从选择集里摘掉（批量时等于清空；单条时保留其它勾选）
      candSel.value = candSel.value.filter(h => !target.includes(h));
      // 保留页码：批量挂完不该把用户踢回第 1 页
      await Promise.all([loadCandidates(false), loadKeep()]);
      if (typeof onChanged === 'function') onChanged();
    } catch (err) {
      notify(`挂保种失败（已挂上 ${held} 个后中断）：${err?.message || err}`, 'error');
      await loadCandidates();
    } finally {
      keepBusy.value = false;
    }
  }

  /**
   * 重新拉起做种（★ 19.10.41）。
   *
   * 手动保种的种可能被 qB 侧暂停（迁移/系统 churn）→ 账本还在岗、标签也对，
   * 但「挂着保种却没在做种」= 名存实亡。重新走一遍 `action=hold` 会让后端对
   * **已在岗**的种也 force_start（`resume_when="all"`），并把拉起结果如实回传。
   * ★ 不能拿 `held`（新增挂载数）判断成功 —— 已在岗时它恒为 0，要看 `resumed`。
   */
  async function resumeKeep(hashes) {
    const hs = (Array.isArray(hashes) ? hashes : [hashes]).filter(Boolean);
    const target = hs.length ? hs : keepSel.value;
    if (!target.length) return
    keepBusy.value = true;
    try {
      const r = unwrapResponse(await api.settings.holdSeeds(target, true));
      const okN = Number(r?.resumed ?? 0);
      const bad = r?.resume_failed || [];
      if (okN > 0) notify(`已拉起做种 ${okN} 个${bad.length ? ` · 失败 ${bad.length} 个` : ''}`);
      else notify(`没有拉起成功（${bad[0]?.error || '下载器未确认'}）`, 'warning');
      await loadKeep();
      if (typeof onChanged === 'function') onChanged();
    } catch (err) {
      notify(`拉起失败：${err?.message || err}`, 'error');
    } finally {
      keepBusy.value = false;
    }
  }

  return {
    keepOpen, keepTab, keepLoading, keepData, keepOnlyBad, keepQ, keepSel, keepBusy,
    keepItems,
    loadKeep, openKeep, toggleKeepRow, toggleKeepAll, releaseKeep, resumeKeep,
    candLoading, candData, candQ, candSite, candSub, candOnlyHr, candSort,
    candSel, candPage, candList, candRows, candPages, candSubs,
    candSelGb, candSelOnPage,
    switchKeepTab, toggleCandRow, toggleCandPage, toggleCandAll,
    clearCandSel, candGoto, holdSelected,
  }
}

export { useKeep }
