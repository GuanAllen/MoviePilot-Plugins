<script setup>
// MagicFlow 前端 · 库内资源（asset 页 · 手动强删入口）
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 本组件**自取数**：onMounted 调 api.assets.getAssets(0)（api 由父页 :api 下发）；
// reloadKey 变化时重拉（可选）。
// ★ 2026-10-10：列表改为**资产（资源）粒度**——一条 = 一份资源（本体 + 各站全部辅种），
//   显示 resource 名（不是单个种名）；删除 = 该资源整组（删文件 + 删种 + 连带所有辅种）。
// ★ 19.12.92：窄屏改三屏（概览 / 清单 / 详情）。
//   ① 数字按**两根轴**分开且各自闭环：媒体库 已入库+仅保种+落点丢失 = 总数；
//      能不能删 可删+被拦 = 总数。原来只念了 5 个数，漏了 dest_missing
//      → 「144+144 却写共 295」，少的 7 条恰好是唯一需要处理的那批。
//   ② 两段说明压成一行副行，细节进 ⓘ（说明从 7 行降到 1 行）。
//   ③ 「删除选中 (0)」整行红块 → 选中后才出现的吸底条，并写清 份数/体积/种数。
//   ④ 被拦的行不显示灰勾（点了没反应像卡死），换锁。
//   ⑤ 落点丢失从筛选器暗格升成告警卡，给「看这 N 份」+「全部重新整理」。
//   ⑥ 列表分页 20 条起（原来窄屏一次渲染全部 295 张卡）。
import { computed, onMounted, ref, watch } from 'vue'
import { epLabelFromName, unwrapResponse } from '../../../../utils'
import AssetDeleteConfirm from '../confirm/AssetDeleteConfirm.vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  reloadKey: { type: [String, Number], default: 0 },
  // ★ 19.12.92：≤959px（与父页 isNarrow 同一断点）走三屏布局
  narrow: { type: Boolean, default: false },
})

// ★ 15.8.21：资源级「季 / 集」标签——取自**本体种**（source_hash）的种名；
// 本体种缺失时退回首成员。仅作展示，不参与删除判定。
function assetSeedName(item) {
  const ms = Array.isArray(item?.members) ? item.members : []
  const src = ms.find(m => m && m.hash === item?.source_hash)
  return String((src || ms[0] || {}).title || '')
}
function assetEpLabel(item) {
  return epLabelFromName(assetSeedName(item))
}

// ★ 15.9.0：行内养护动作（保护 / 订阅 / 整理 / 刮削）——删除仍走选中 + 顶部按钮
// ★ 设计统一：养护一列里「保护」是唯一带状态切换的主操作，走实心 success；
//   其余三个是低频次操作，统一收成中性描边（原来四种颜色并排，看不出主次）。
const ACTIONS = [
  { key: 'subscribe', label: '订阅整季', icon: 'mdi-playlist-plus',
    hint: '在 MoviePilot 订阅这份资源的「剧+季」补齐缺集；再点一次退订' },
  { key: 'organize', label: '整理', icon: 'mdi-folder-move-outline',
    hint: '★ 只取代表种以 link 方式入库；同组其余成员不整理、不强制校验，只做只读核验' },
  { key: 'scrape', label: '刮削', icon: 'mdi-image-search-outline',
    hint: '纠错元数据' },
]

const headers = [
  { title: '', key: 'select', sortable: false, width: 44 },
  { title: '资源', key: 'name', sortable: false },
  { title: '来源站', key: 'source_site', sortable: false, width: 110 },
  { title: '成员站', key: 'sites', sortable: false, width: 150 },
  { title: '成员', key: 'members_in_qb', sortable: false, width: 88 },
  { title: '体积(GB)', key: 'size_gb', sortable: false, width: 96 },
  { title: '媒体库状态', key: 'media_library', sortable: false, width: 132 },
  { title: '保护状态', key: 'block', sortable: false, width: 150 },
  { title: '养护', key: 'act', sortable: false, width: 300 },
]

const loading = ref(false)
const deleting = ref(false)
const error = ref('')
const flash = ref(null)
const items = ref([])
const counts = ref({})
const siteFilter = ref('')
const mediaFilter = ref('')
const includeStale = ref(false)
const selectedIds = ref([])
const confirmOpen = ref(false)
const acting = ref('')
const onlyProtected = ref(false)
const preview = ref(null)
const previewing = ref(false)
const previewOpen = ref(false)

// ── 19.12.92 窄屏三屏状态 ──────────────────────────────────────────────
const screen = ref('overview')       // overview | list | detail
const detailId = ref('')
const detailFrom = ref('overview')
const search = ref('')
const chip = ref('all')
const sortKey = ref('size_desc')
const mLimit = ref(20)
const infoOpen = ref(false)
const sitesOpen = ref(false)
const allBusy = ref(false)
const chipRow = ref(null)

// ★ 19.12.64：这里的「库」= 魔流资源账本；「媒体库状态」才是飞牛影视/MP 能不能看到。
const MEDIA_STATES = [
  { title: '全部媒体库状态', value: '' },
  { title: '仅保种（未入库）', value: 'seeding_only' },
  { title: '已入库', value: 'in_media' },
  { title: '落点丢失', value: 'dest_missing' },
  { title: '账本残留', value: 'stale' },
]
const MEDIA_TEXT = {
  in_media: '已入库', dest_missing: '落点丢失',
  seeding_only: '仅保种', stale: '账本残留',
}
const VERDICT_TEXT = {
  ready: '可整理', manual_path: '需人工',
  skip_in_media: '已入库跳过', skip_no_qb: '无下载器种',
}
const SORTS = [
  { title: '体积 大→小', value: 'size_desc' },
  { title: '体积 小→大', value: 'size_asc' },
  { title: '种数 少→多', value: 'seeds_asc' },
  { title: '名称', value: 'name' },
]

function mediaText(item) {
  return MEDIA_TEXT[String(item?.media_library || '')] || '未知'
}
// 中性色不写主题色名（glass 主题 secondary 与 info 同色，会渲染成蓝标签）
function mediaColor(item) {
  const m = String(item?.media_library || '')
  return m === 'in_media' ? 'success' : (m === 'dest_missing' ? 'error' : undefined)
}
function mediaTitle(item) {
  const bits = []
  const d = String(item?.media_dest || '').trim()
  if (d) bits.push(`整理落点：${d}`)
  const v = item?.organize_verify
  if (v) bits.push(`上次整理核验：${v.dest_ok ? '落点已确认' : '落点待回读'} · 其余 ${v.others ?? 0} 颗未 recheck`)
  return bits.join('\n') || mediaText(item)
}

const siteOptions = computed(() => {
  const names = []
  for (const it of items.value) {
    const site = String(it?.source_site ?? '').trim()
    if (site && !names.includes(site)) names.push(site)
  }
  names.sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
  return [{ title: '全部来源站', value: '' }, ...names.map(name => ({ title: name, value: name }))]
})

const visibleItems = computed(() => {
  let list = items.value
  if (siteFilter.value) list = list.filter(it => String(it?.source_site ?? '') === siteFilter.value)
  if (mediaFilter.value) list = list.filter(it => String(it?.media_library ?? '') === mediaFilter.value)
  if (onlyProtected.value) list = list.filter(it => it?.protected === true)
  return list
})

const deletableVisible = computed(() => visibleItems.value.filter(it => it?.deletable === true))

const selectedItems = computed(
  () => items.value.filter(it => it?.deletable === true && selectedIds.value.includes(it?.resource_id)),
)

const allSelected = computed(
  () => deletableVisible.value.length > 0
    && deletableVisible.value.every(it => selectedIds.value.includes(it?.resource_id)),
)

const someSelected = computed(() => selectedIds.value.length > 0 && !allSelected.value)

const selectedTotalGb = computed(
  () => selectedItems.value.reduce((sum, it) => sum + Number(it?.size_gb ?? 0), 0),
)

const selectedSeedCount = computed(
  () => selectedItems.value.reduce((sum, it) => sum + Number(it?.members_in_qb ?? 0), 0),
)
// 选中里「只有 1 个种」的份数：删了没有第二份可补，按之前必须先说
const selectedSingleCount = computed(
  () => selectedItems.value.filter(it => Number(it?.members_in_qb ?? 0) === 1).length,
)

// ── 19.12.92 对账：两根轴各自闭环 ──────────────────────────────────────
const totalCount = computed(() => Number(counts.value.total ?? items.value.length ?? 0))
const mediaTiles = computed(() => ([
  { key: 'in_media', label: '已入库', n: Number(counts.value.in_media ?? 0), err: false },
  { key: 'seeding_only', label: '仅保种', n: Number(counts.value.seeding_only ?? 0), err: false },
  { key: 'dest_missing', label: '落点丢失', n: Number(counts.value.dest_missing ?? 0), err: true },
]))
const mediaSum = computed(() => mediaTiles.value.reduce((sum, t) => sum + t.n, 0))
const totalGb = computed(() => items.value.reduce((sum, it) => sum + Number(it?.size_gb ?? 0), 0))
const singleSeedCount = computed(
  () => items.value.filter(it => Number(it?.members_in_qb ?? 0) === 1).length,
)
const lostItems = computed(() => items.value.filter(it => String(it?.media_library ?? '') === 'dest_missing'))

// 「被拦」的组成：已认领 8 + 手动保留 4 + 其他 —— 只在这几项真能加回总数时才写细分
const blockedItems = computed(() => items.value.filter(it => it?.deletable !== true && it?.stale !== true))
const blockedParts = computed(() => {
  const claim = blockedItems.value.filter(it => String(it?.block || '').includes('认领'))
  const manual = blockedItems.value.filter(it => it?.protected === true)
  const claimOnly = claim.filter(it => it?.protected !== true).length
  const manualOnly = manual.filter(it => !String(it?.block || '').includes('认领')).length
  const both = claim.filter(it => it?.protected === true).length
  const other = blockedItems.value.length - claimOnly - manualOnly - both
  const bits = []
  if (claimOnly) bits.push(`已认领 ${claimOnly}`)
  if (manualOnly) bits.push(`手动保留 ${manualOnly}`)
  if (both) bits.push(`两者都有 ${both}`)
  if (other) bits.push(`其他 ${other}`)
  return bits.join(' + ')
})
const blockedText = computed(() => {
  const n = blockedItems.value.length
  return blockedParts.value ? `${n} 份被拦（${blockedParts.value}）` : `${n} 份被拦`
})

// ── 19.12.92 窄屏筛选 / 排序 / 分页 ────────────────────────────────────
const chips = computed(() => {
  const c = counts.value
  return [
    { key: 'all', label: '全部', n: Number(c.total ?? 0), cls: '' },
    { key: 'in_media', label: '已入库', n: Number(c.in_media ?? 0), cls: '' },
    { key: 'seeding_only', label: '仅保种', n: Number(c.seeding_only ?? 0), cls: '' },
    { key: 'dest_missing', label: '落点丢失', n: Number(c.dest_missing ?? 0), cls: 'is-err' },
    { key: 'blocked', label: '被拦', n: Number(c.blocked ?? 0), cls: 'is-warn' },
    { key: 'deletable', label: '可删', n: Number(c.deletable ?? 0), cls: '' },
  ]
})

function haystack(item) {
  const parts = [
    item?.name, item?.source_site, assetSeedName(item), item?.media_dest,
    ...(Array.isArray(item?.sites) ? item.sites : []),
  ]
  return parts.filter(Boolean).join(' ').toLowerCase()
}

const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase()
  let list = items.value
  if (chip.value === 'blocked') list = list.filter(it => it?.deletable !== true)
  else if (chip.value === 'deletable') list = list.filter(it => it?.deletable === true)
  else if (chip.value !== 'all') list = list.filter(it => String(it?.media_library ?? '') === chip.value)
  if (q) list = list.filter(it => haystack(it).includes(q))
  const arr = [...list]
  if (sortKey.value === 'size_desc') arr.sort((a, b) => Number(b?.size_gb ?? 0) - Number(a?.size_gb ?? 0))
  else if (sortKey.value === 'size_asc') arr.sort((a, b) => Number(a?.size_gb ?? 0) - Number(b?.size_gb ?? 0))
  else if (sortKey.value === 'seeds_asc') arr.sort((a, b) => Number(a?.members_in_qb ?? 0) - Number(b?.members_in_qb ?? 0))
  else arr.sort((a, b) => String(a?.name ?? '').localeCompare(String(b?.name ?? ''), 'zh-Hans-CN'))
  return arr
})
const shownItems = computed(() => filteredItems.value.slice(0, mLimit.value))
const moreCount = computed(() => Math.max(0, filteredItems.value.length - mLimit.value))
const filteredDeletable = computed(() => filteredItems.value.filter(it => it?.deletable === true))
const filteredAllSelected = computed(
  () => filteredDeletable.value.length > 0
    && filteredDeletable.value.every(it => selectedIds.value.includes(it?.resource_id)),
)
const detailItem = computed(() => items.value.find(it => String(it?.resource_id) === detailId.value) || null)

function shortPath(path) {
  const s = String(path || '')
  if (!s) return ''
  const bits = s.split('/').filter(Boolean)
  if (bits.length <= 2) return s
  return `…/${bits.slice(-2).join('/')}`
}
function sizeText(item) {
  const gb = Number(item?.size_gb ?? 0)
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${Math.round(gb * 1024)} MB`
}
function membersText2(item) {
  const n = Number(item?.members_in_qb ?? 0)
  return `${n} 个种`
}
function siteCountText(item) {
  const n = Array.isArray(item?.sites) ? item.sites.filter(Boolean).length : 0
  return n ? `${n} 个站` : '来源站未知'
}
// 卡片右侧的状态标记：只标异常态，正常的不出声（283 条都写「可删」等于没写）
function shortBlock(item) {
  const b = String(item?.block || '').trim()
  if (!b) return '被保护'
  if (b.includes('认领')) return '已认领'
  if (b.includes('H&R') || b.includes('任务')) return '欠 H&R'
  if (b.includes('残留')) return '仅账本'
  return b.length > 8 ? `${b.slice(0, 8)}…` : b
}
function blockTags(item) {
  const out = []
  const m = String(item?.media_library || '')
  if (m === 'dest_missing') out.push({ text: '落点丢失', cls: 'mf-tag--err' })
  if (item?.stale === true) out.push({ text: '仅账本残留', cls: 'mf-tag--soft' })
  if (item?.deletable !== true && item?.protected === true) out.push({ text: '手动保留', cls: 'mf-tag--ok' })
  if (item?.deletable !== true && String(item?.block || '').includes('认领')) out.push({ text: '已认领', cls: 'mf-tag--warn' })
  if (item?.deletable !== true && item?.protected !== true && item?.block && !String(item.block).includes('认领') && !item?.stale) {
    out.push({ text: shortBlock(item), cls: 'mf-tag--warn' })
  }
  return out
}
function mediaSuffix(item) {
  const m = String(item?.media_library || '')
  return m === 'seeding_only' ? '仅保种' : (m === 'stale' ? '仅账本' : '')
}
function mediaSentence(item) {
  const m = String(item?.media_library || '')
  if (m === 'in_media') return '媒体库里能看到这部片 —— 整理落点还在。'
  if (m === 'dest_missing') return '整理过，但媒体库里的落点已经不在了 —— 片子上记的「已入库」是旧账，重新整理能重建链接。'
  if (m === 'stale') return '下载器里已经没有这颗种了，只剩账本记录。'
  return '媒体库里没有这部片 —— 它只是一份在做种的资源。'
}
function deletableText(item) {
  if (item?.deletable === true) return '可以 —— 没被认领，也没手动保留'
  return `不行 —— ${String(item?.block || '').trim() || '被保护'}`
}
function detailTags(item) {
  const out = []
  const m = String(item?.media_library || '')
  if (m === 'seeding_only') out.push({ text: '仅保种', cls: 'mf-tag--soft' })
  if (m === 'in_media') out.push({ text: '已入库', cls: 'mf-tag--ok' })
  if (m === 'dest_missing') out.push({ text: '落点丢失', cls: 'mf-tag--err' })
  if (m === 'stale') out.push({ text: '仅账本残留', cls: 'mf-tag--soft' })
  if (Number(item?.members_in_qb ?? 0) === 1) out.push({ text: '仅此一份', cls: 'mf-tag--warn' })
  if (item?.protected === true) out.push({ text: '已手动保留', cls: 'mf-tag--ok' })
  if (item?.deletable !== true && String(item?.block || '').includes('认领')) out.push({ text: '已认领', cls: 'mf-tag--warn' })
  if (item?.deletable !== true && item?.protected !== true && item?.block && !String(item.block).includes('认领') && !item?.stale) {
    out.push({ text: shortBlock(item), cls: 'mf-tag--warn' })
  }
  return out
}
function detailMembers(item) {
  const ms = Array.isArray(item?.members) ? item.members : []
  return ms.map(m => ({
    hash: m?.hash || '',
    site: m?.site || '—',
    title: m?.title || '（种名未知）',
    size: Number(m?.size_gb ?? 0),
    live: m?.in_qb === true,
  }))
}

function blockText(item) {
  if (item?.deletable === true) return '可删'
  const full = String(item?.block ?? '').trim() || '被保护'
  // 列表里只显示短标签，长原因（如 H&R 义务）截断 + 悬停看全文，避免把卡片撑爆
  return full.length > 12 ? `${full.slice(0, 12)}…` : full
}
// ★ 设计统一：绿色在本页只代表「手动保留」一种含义。
//   「可删」原本也是 success 绿，和「手动保留」chip 相邻时语义撞车 → 改中性色，
//   让颜色只负责一件事：绿=已上保护，中性=可以动它，琥珀=有东西拦着。
//   ★ 中性不要写成主题色名：宿主 glass 主题的 secondary=#7C9CC4，与 info 完全同色，
//     「可删」会渲染成一颗 info 蓝的状态标签。返回 undefined 让 VChip 走默认中性，
//     五个主题（light/dark/purple/transparent/glass）下都成立。
function blockColor(item) {
  return item?.deletable === true ? undefined : 'warning'
}
function sitesText(item) {
  const list = (item?.sites || []).filter(Boolean)
  if (!list.length) return '—'
  return list.join('、')
}
function membersText(item) {
  const live = Number(item?.members_in_qb ?? 0)
  const total = Number(item?.member_count ?? 0)
  if (!total) return String(live)
  return total === live ? `${live}` : `${live}/${total}`
}

function toggleRow(item) {
  if (!item || item.deletable !== true || !item.resource_id) return
  const rid = item.resource_id
  if (selectedIds.value.includes(rid)) {
    selectedIds.value = selectedIds.value.filter(x => x !== rid)
  } else {
    selectedIds.value = [...selectedIds.value, rid]
  }
}
function toggleAll(value) {
  if (value) {
    selectedIds.value = deletableVisible.value.map(it => it.resource_id).filter(Boolean)
  } else {
    clearSelection()
  }
}
// ★ 19.12.92 窄屏全选：只选**当前筛选下**可删的那些（原来按整库算，筛了「落点丢失」再全选会连着 283 条一起选上）
function toggleAllFiltered() {
  const ids = filteredDeletable.value.map(it => it?.resource_id).filter(Boolean)
  if (!ids.length) return
  if (filteredAllSelected.value) {
    selectedIds.value = selectedIds.value.filter(id => !ids.includes(id))
  } else {
    selectedIds.value = Array.from(new Set([...selectedIds.value, ...ids]))
  }
}
// ★ 15.9.0：单条资源的养护动作（protect / unprotect / subscribe / unsubscribe / organize / scrape）
async function act(item, action, label) {
  const client = props.api?.assets
  if (!client || typeof client.actAssets !== 'function') {
    flash.value = { type: 'error', text: '资产接口未接线，无法执行' }
    return
  }
  const rid = String(item?.resource_id ?? '').trim()
  if (!rid || acting.value) return
  acting.value = rid + action
  try {
    const res = await client.actAssets({ action, resource_ids: [rid] })
    const data = unwrapResponse(res) || {}
    const row = (data.results || [])[0] || {}
    const ok = row.ok === true
    flash.value = {
      type: ok ? 'success' : 'warning',
      text: `${label}「${item?.name || rid}」：${row.message || res?.message || (ok ? '完成' : '未生效')}`,
    }
    await load()
  } catch (err) {
    flash.value = { type: 'error', text: `${label}失败：${err?.response?.data?.message || err?.message || err}` }
  } finally {
    acting.value = ''
  }
}

// ★ 19.12.92「全部重新整理」：落点丢失那批一次进后台队列（只重建 link，不动种子、不删文件）
async function organizeAllLost() {
  const client = props.api?.assets
  if (!client || typeof client.actAssets !== 'function') {
    flash.value = { type: 'error', text: '资产接口未接线，无法整理' }
    return
  }
  const list = lostItems.value.filter(it => it?.resource_id)
  if (!list.length || allBusy.value) return
  allBusy.value = true
  try {
    const res = await client.actAssets({
      action: 'organize',
      resource_ids: list.map(it => it.resource_id),
    })
    const data = unwrapResponse(res) || {}
    const n = Number((data.results || []).filter(r => r?.ok).length || list.length)
    flash.value = {
      type: 'success',
      text: `已把 ${n} 份「落点丢失」加入整理队列（只按 link 重建落点，种子和文件都不动）`,
    }
    await load()
  } catch (err) {
    flash.value = { type: 'error', text: `批量整理失败：${err?.response?.data?.message || err?.message || err}` }
  } finally {
    allBusy.value = false
  }
}

function protectLabel(item) {
  return item?.protected === true ? '取消保护' : '保护'
}
function protectAction(item) {
  return item?.protected === true ? 'unprotect' : 'protect'
}

function clearSelection() {
  selectedIds.value = []
}
function pruneSelection() {
  const visible = new Set(visibleItems.value.map(it => it?.resource_id))
  selectedIds.value = selectedIds.value.filter(id => visible.has(id))
}

// ── 19.12.92 窄屏导航 ──────────────────────────────────────────────────
function openDetail(item) {
  if (!item?.resource_id) return
  detailFrom.value = screen.value === 'overview' ? 'overview' : 'list'
  detailId.value = String(item.resource_id)
  sitesOpen.value = false
  screen.value = 'detail'
}
function backFromDetail() {
  screen.value = detailFrom.value
}
function goList(key) {
  if (key) chip.value = key
  screen.value = 'list'
}
function applyChip(key) {
  chip.value = key
  mLimit.value = 20
}
// 详情页删除：把这一份放进选中集，再走同一个确认弹窗（不另开一条删除路径）
function deleteOne(item) {
  if (!item?.resource_id || item?.deletable !== true) return
  selectedIds.value = [String(item.resource_id)]
  confirmOpen.value = true
}

async function load() {
  const client = props.api?.assets
  if (!client || typeof client.getAssets !== 'function') {
    error.value = '资产接口未接线：请父页传 `:api`，并在 request.js 注册 `c.assets = makeAssets(c)`'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data = unwrapResponse(await client.getAssets(0, includeStale.value)) || {}
    items.value = Array.isArray(data.items) ? data.items : []
    counts.value = data.counts || {}
    pruneSelection()
  } catch (err) {
    error.value = `读取库内资产失败：${err?.message || err}`
    items.value = []
    counts.value = {}
    clearSelection()
  } finally {
    loading.value = false
  }
}

// ★ 19.12.64 整理预演：只读清单，先看「哪一颗会被整理 / 源在哪 / 哪些要人工」
// 再决定要不要真跑。这里绝不调用整理动作，也不触发下载器 recheck。
async function runPreview() {
  const client = props.api?.assets
  if (!client || typeof client.organizePreview !== 'function') {
    flash.value = { type: 'error', text: '整理预演接口未接线（请确认前端已升到 19.12.64）' }
    return
  }
  previewing.value = true
  try {
    const data = unwrapResponse(await client.organizePreview(1, 0)) || {}
    preview.value = data
    previewOpen.value = true
  } catch (err) {
    flash.value = { type: 'error', text: `整理预演失败：${err?.response?.data?.message || err?.message || err}` }
  } finally {
    previewing.value = false
  }
}

function openConfirm() {
  if (!selectedItems.value.length) return
  confirmOpen.value = true
}

async function submitDelete(payload) {
  const client = props.api?.assets
  if (!client || typeof client.deleteAssets !== 'function') {
    flash.value = { type: 'error', text: '资产接口未接线，无法删除' }
    return
  }
  const resourceIds = selectedItems.value.map(it => it?.resource_id).filter(Boolean)
  if (!resourceIds.length) return
  const deleteFiles = payload?.deleteFiles === true
  deleting.value = true
  try {
    const res = await client.deleteAssets({
      resource_ids: resourceIds,
      delete_files: deleteFiles ? 1 : 0,
      confirm: 1,
      reason: '手动删除库内资产',
    })
    const data = unwrapResponse(res) || {}
    const reasons = {}
    for (const row of (data.results || [])) {
      const block = String(row?.block ?? '').trim()
      if (block) reasons[block] = (reasons[block] || 0) + 1
    }
    const reasonText = Object.entries(reasons).map(([key, count]) => `${key}×${count}`).join('、')
    const failed = Number(data.failed ?? 0)
    const base = String(res?.message ?? '').trim()
      || `删除库内资产：成功 ${Number(data.deleted ?? 0)} · 被保护 ${Number(data.blocked ?? 0)} · 失败 ${failed}`
    flash.value = {
      type: failed > 0 ? 'error' : (reasonText ? 'warning' : 'success'),
      text: `${base}${deleteFiles ? '（含文件）' : '（仅删种，保留文件）'}${reasonText ? `；被拦理由：${reasonText}` : ''}`,
    }
    confirmOpen.value = false
    clearSelection()
    await load()
    if (screen.value === 'detail' && !detailItem.value) screen.value = 'list'
  } catch (err) {
    flash.value = { type: 'error', text: `删除失败：${err?.message || err}` }
  } finally {
    deleting.value = false
  }
}

onMounted(load)
watch(() => props.reloadKey, () => { load() })
watch(siteFilter, pruneSelection)
watch(mediaFilter, pruneSelection)
watch(includeStale, () => { load() })
watch([chip, search, sortKey], () => { mLimit.value = 20 })
// 从格子/告警点进来时 chip 可能落在横向滚动区外 → 把当前选中的 chip 滚进视野
watch(chip, () => {
  requestAnimationFrame(() => {
    const row = chipRow.value
    const el = row && row.querySelector ? row.querySelector('.mf-chip.is-on') : null
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ inline: 'center', block: 'nearest' })
    }
  })
})
</script>

<template>
  <VSheet tag="section" class="magicflow-panel magicflow-assets app-surface-static">
    <!-- ★ 19.12.92 窄屏三屏（概览 / 清单 / 详情） -->
    <div v-if="narrow" class="mf-m">
      <div class="mf-m__bar">
        <VBtn
          v-if="screen === 'detail'"
          icon="mdi-chevron-left"
          variant="text"
          size="small"
          aria-label="返回"
          @click="backFromDetail"
        />
        <span class="mf-m__sub">
          {{ screen === 'detail' ? '这一份资源' : `保种资源账本 · 不是影视库` }}
        </span>
        <VSpacer />
        <VBtn
          v-if="screen === 'list'"
          icon="mdi-select-all"
          variant="text"
          size="small"
          :disabled="!filteredDeletable.length"
          :color="filteredAllSelected ? 'primary' : undefined"
          aria-label="全选当前清单里可删的资源"
          @click="toggleAllFiltered"
        />
        <VBtn
          v-if="screen !== 'detail'"
          icon="mdi-information-outline"
          variant="text"
          size="small"
          aria-label="这是什么"
          @click="infoOpen = !infoOpen"
        />
        <VBtn
          v-if="screen !== 'detail'"
          icon="mdi-refresh"
          variant="text"
          size="small"
          :loading="loading"
          aria-label="刷新"
          @click="load"
        />
      </div>

      <div v-if="infoOpen && screen !== 'detail'" class="mf-m__info">
        <p><b>这里的「库」= 魔流资源账本（保种资产），不是飞牛影视媒体库。</b>一条 = 一份资源，含它在各站的辅种。</p>
        <p>保护 = 手动保留（永不自动删） · 订阅整季 = 补这季缺集 · 整理 = 只取代表种按 link 入库，同组其余成员只读核验 · 刮削 = 纠错元数据。慢动作在后台跑，关页面不断。</p>
      </div>

      <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mt-2">{{ error }}</VAlert>
      <VAlert
        v-if="flash"
        :type="flash.type"
        variant="tonal"
        density="compact"
        closable
        class="mt-2"
        @click:close="flash = null"
      >
        {{ flash.text }}
      </VAlert>

      <!-- ① 概览 -->
      <div v-if="screen === 'overview'" class="mf-m__body">
        <div class="mf-kpi">
          <div class="mf-kpi__big">{{ totalCount }}<i>份</i></div>
          <div class="mf-kpi__note">
            <span>占用 <b>{{ totalGb >= 1024 ? `${(totalGb / 1024).toFixed(1)} TB` : `${totalGb.toFixed(0)} GB` }}</b></span>
            <span v-if="singleSeedCount">{{ singleSeedCount }} 份只有 1 个种</span>
          </div>
        </div>

        <div class="mf-axis">
          <div class="mf-axis__hd">
            <h3>媒体库状态</h3>
            <span class="mf-sum">{{ mediaTiles.map(t => t.n).join(' + ') }} = {{ mediaSum }}</span>
          </div>
          <div class="mf-tiles">
            <button
              v-for="t in mediaTiles"
              :key="t.key"
              class="mf-tile"
              :class="{ 'is-err': t.err, 'is-on': chip === t.key }"
              @click="applyChip(t.key)"
            >
              <span class="mf-tile__n" :class="{ 'is-err': t.err }">{{ t.n }}</span>
              <span class="mf-tile__l">{{ t.label }}</span>
            </button>
          </div>
        </div>

        <div class="mf-axis2" @click="goList('blocked')">
          <div class="mf-axis2__t">
            <span class="mf-axis2__l1"><b>{{ Number(counts.deletable ?? 0) }}</b> 份可删 · <b>{{ Number(counts.blocked ?? 0) }}</b> 份被拦</span>
            <span v-if="blockedParts" class="mf-axis2__l2">被拦的都是：{{ blockedParts }}</span>
          </div>
          <span class="mf-axis2__go">看清单<VIcon icon="mdi-chevron-right" size="14" /></span>
        </div>

        <div v-if="lostItems.length" class="mf-alarm">
          <div class="mf-alarm__top">
            <VIcon icon="mdi-alert-outline" size="17" color="error" />
            <span class="mf-alarm__nm">落点丢失</span>
            <span class="mf-alarm__n">{{ lostItems.length }} 份</span>
          </div>
          <div class="mf-alarm__why">
            这几份<b>整理过</b>，但媒体库里的文件后来被移走或删了 —— 片子上的「已入库」是旧账。
            <b>重新整理就能把链接重建回来</b>；已被认领/手动保留的那几份只能整理、不能删。
          </div>
          <div class="mf-alarm__acts">
            <VBtn size="small" variant="flat" color="primary" @click="applyChip('dest_missing'); screen = 'list'">
              看这 {{ lostItems.length }} 份
            </VBtn>
            <VBtn size="small" variant="tonal" :loading="allBusy" @click="organizeAllLost">全部重新整理</VBtn>
          </div>
        </div>

        <div class="mf-search">
          <VIcon icon="mdi-magnify" size="18" />
          <input v-model="search" type="search" placeholder="搜片名，或搜种名" aria-label="搜索库内资源" />
        </div>

        <div ref="chipRow" class="mf-chips">
          <button
            v-for="c in chips"
            :key="c.key"
            class="mf-chip"
            :class="{ 'is-on': chip === c.key, 'is-err': c.cls === 'is-err', 'is-warn': c.cls === 'is-warn' }"
            @click="applyChip(c.key)"
          >
            {{ c.label }}<span class="mf-chip__c">{{ c.n }}</span>
          </button>
        </div>

        <div class="mf-sec">
          <h3>{{ sortKey === 'name' ? '按名称' : (sortKey === 'seeds_asc' ? '按种数' : '按体积') }}</h3>
          <span class="mf-sec__n">{{ filteredItems.length }} 份</span>
          <button class="mf-sec__act" @click="screen = 'list'">看全部<VIcon icon="mdi-chevron-right" size="14" /></button>
        </div>

        <article
          v-for="it in shownItems.slice(0, 6)"
          :key="it.resource_id || it.name"
          class="mf-card"
          @click="openDetail(it)"
        >
          <button
            v-if="it.deletable === true"
            class="mf-card__ck"
            :class="{ 'is-on': selectedIds.includes(it.resource_id) }"
            :aria-label="`选择 ${it.name || ''}`"
            @click.stop="toggleRow(it)"
          >
            <VIcon v-if="selectedIds.includes(it.resource_id)" icon="mdi-check" size="15" />
          </button>
          <span v-else class="mf-card__ck is-lock" :title="String(it.block || '').trim() || '被保护'">
            <VIcon icon="mdi-lock-outline" size="15" />
          </span>
          <div class="mf-card__main">
            <div class="mf-card__l1">
              <strong class="mf-card__nm">{{ it.name || '未命名资源' }}</strong>
              <span v-if="assetEpLabel(it)" class="mf-tag mf-tag--soft">{{ assetEpLabel(it) }}</span>
              <span v-for="t in blockTags(it)" :key="t.text" class="mf-tag" :class="t.cls">{{ t.text }}</span>
            </div>
            <div class="mf-card__meta">
              {{ siteCountText(it) }} · {{ membersText2(it) }} · <b>{{ sizeText(it) }}</b>
              <span v-if="mediaSuffix(it)"> · {{ mediaSuffix(it) }}</span>
            </div>
            <div v-if="it.media_library === 'dest_missing'" class="mf-card__flag is-err">
              媒体库里 {{ shortPath(it.media_dest) || '这个落点' }} 已经找不到
            </div>
            <div v-else-if="Number(it.members_in_qb ?? 0) === 1" class="mf-card__flag is-warn">
              只有这 1 个种，删了就没有第二份
            </div>
          </div>
        </article>

        <button class="mf-more" @click="screen = 'list'">
          {{ moreCount ? `还有 ${filteredItems.length - shownItems.slice(0, 6).length} 份，看清单` : '看完整清单' }}
          <VIcon icon="mdi-chevron-right" size="16" />
        </button>

        <VBtn
          variant="tonal"
          class="mf-preview-btn"
          prepend-icon="mdi-file-search-outline"
          :loading="previewing"
          :disabled="loading"
          @click="runPreview"
        >
          整理预演（只列清单，不动任何东西）
        </VBtn>
      </div>

      <!-- ② 清单 -->
      <div v-else-if="screen === 'list'" class="mf-m__body mf-m__body--sticky">
        <div class="mf-search">
          <VIcon icon="mdi-magnify" size="18" />
          <input v-model="search" type="search" placeholder="搜片名，或搜种名" aria-label="搜索库内资源" />
        </div>

        <div ref="chipRow" class="mf-chips">
          <button
            v-for="c in chips"
            :key="c.key"
            class="mf-chip"
            :class="{ 'is-on': chip === c.key, 'is-err': c.cls === 'is-err', 'is-warn': c.cls === 'is-warn' }"
            @click="applyChip(c.key)"
          >
            {{ c.label }}<span class="mf-chip__c">{{ c.n }}</span>
          </button>
        </div>

        <div class="mf-sec">
          <h3>排序</h3>
          <span class="mf-sec__n">{{ filteredItems.length }} 份<template v-if="selectedIds.length"> · 已选 {{ selectedIds.length }}</template></span>
          <VSelect
            v-model="sortKey"
            :items="SORTS"
            item-title="title"
            item-value="value"
            density="compact"
            variant="plain"
            hide-details
            class="mf-sort"
          />
        </div>

        <article
          v-for="it in shownItems"
          :key="it.resource_id || it.name"
          class="mf-card"
          @click="openDetail(it)"
        >
          <button
            v-if="it.deletable === true"
            class="mf-card__ck"
            :class="{ 'is-on': selectedIds.includes(it.resource_id) }"
            :aria-label="`选择 ${it.name || ''}`"
            @click.stop="toggleRow(it)"
          >
            <VIcon v-if="selectedIds.includes(it.resource_id)" icon="mdi-check" size="15" />
          </button>
          <span v-else class="mf-card__ck is-lock" :title="String(it.block || '').trim() || '被保护'">
            <VIcon icon="mdi-lock-outline" size="15" />
          </span>
          <div class="mf-card__main">
            <div class="mf-card__l1">
              <strong class="mf-card__nm">{{ it.name || '未命名资源' }}</strong>
              <span v-if="assetEpLabel(it)" class="mf-tag mf-tag--soft">{{ assetEpLabel(it) }}</span>
              <span v-for="t in blockTags(it)" :key="t.text" class="mf-tag" :class="t.cls">{{ t.text }}</span>
            </div>
            <div class="mf-card__meta">
              {{ siteCountText(it) }} · {{ membersText2(it) }} · <b>{{ sizeText(it) }}</b>
              <span v-if="mediaSuffix(it)"> · {{ mediaSuffix(it) }}</span>
            </div>
            <div v-if="it.media_library === 'dest_missing'" class="mf-card__flag is-err">
              媒体库里 {{ shortPath(it.media_dest) || '这个落点' }} 已经找不到
            </div>
            <div v-else-if="Number(it.members_in_qb ?? 0) === 1" class="mf-card__flag is-warn">
              只有这 1 个种，删了就没有第二份
            </div>
          </div>
        </article>

        <div v-if="!shownItems.length" class="magicflow-table-empty">
          {{ loading ? '正在读取库内资源…' : '当前筛选下没有库内资源' }}
        </div>
        <button v-if="moreCount" class="mf-more" @click="mLimit += 20">
          再显示 20 份（还有 {{ moreCount }}）
        </button>
        <div class="mf-hintline">
          整理预演：
          <button class="mf-link" :disabled="previewing" @click="runPreview">
            {{ previewing ? '读取中…' : '看哪几份会被整理' }}
          </button>
        </div>

        <div v-if="previewOpen && preview" class="magicflow-asset-preview">
          <div class="magicflow-asset-preview__head">
            <strong>整理预演（只读，未触发任何整理）</strong>
            <span>
              共 {{ Number(preview.counts?.total ?? 0) }} 份 · 可整理 {{ Number(preview.counts?.ready ?? 0) }}
              · 需人工 {{ Number(preview.counts?.manual_path ?? 0) }}
            </span>
            <VSpacer />
            <VBtn size="x-small" variant="text" icon="mdi-close" @click="previewOpen = false" />
          </div>
          <div class="magicflow-asset-preview__list">
            <div
              v-for="it in (preview.items || []).slice(0, 10)"
              :key="it.resource_id || it.name"
              class="magicflow-asset-preview__row"
            >
              <span>{{ it.name }} · {{ Number(it.size_gb ?? 0).toFixed(1) }}G</span>
              <span class="magicflow-asset-preview__reason">{{ VERDICT_TEXT[it.verdict] || it.verdict }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ③ 详情 -->
      <div v-else class="mf-m__body">
        <template v-if="detailItem">
          <div class="mf-hero">
            <div class="mf-hero__nm">{{ detailItem.name || '未命名资源' }}</div>
            <div class="mf-hero__tags">
              <span v-if="assetEpLabel(detailItem)" class="mf-tag mf-tag--soft">{{ assetEpLabel(detailItem) }}</span>
              <span v-for="t in detailTags(detailItem)" :key="t.text" class="mf-tag" :class="t.cls">{{ t.text }}</span>
            </div>
            <div class="mf-hero__sum">
              在 <b>{{ (detailItem.sites || []).length || '—' }}</b> 个站做种，共
              <b>{{ Number(detailItem.members_in_qb ?? 0) }}</b> 个种、<b>{{ sizeText(detailItem) }}</b>。<br>
              {{ mediaSentence(detailItem) }}
            </div>
          </div>

          <dl class="mf-kv">
            <div class="mf-kv__r"><dt>来源站</dt><dd>{{ detailItem.source_site || '—' }}</dd></div>
            <div class="mf-kv__r"><dt>成员站</dt><dd>{{ sitesText(detailItem) }}</dd></div>
            <div class="mf-kv__r"><dt>种名</dt><dd><span class="mf-mono">{{ assetSeedName(detailItem) || '（种名未知）' }}</span></dd></div>
            <div v-if="detailItem.media_dest" class="mf-kv__r">
              <dt>整理落点</dt>
              <dd><span class="mf-mono">{{ detailItem.media_dest }}</span></dd>
            </div>
            <div class="mf-kv__r"><dt>能否删除</dt><dd>{{ deletableText(detailItem) }}</dd></div>
          </dl>

          <div class="mf-acts">
            <VBtn
              variant="outlined"
              :loading="acting === String(detailItem.resource_id) + protectAction(detailItem)"
              @click="act(detailItem, protectAction(detailItem), protectLabel(detailItem))"
            >{{ protectLabel(detailItem) }}</VBtn>
            <VBtn
              variant="outlined"
              :loading="acting === String(detailItem.resource_id) + 'subscribe'"
              @click="act(detailItem, 'subscribe', '订阅整季')"
            >订阅整季</VBtn>
            <VBtn
              variant="flat"
              color="primary"
              class="mf-acts__wide"
              :loading="acting === String(detailItem.resource_id) + 'organize'"
              @click="act(detailItem, 'organize', '整理入库')"
            >整理入库</VBtn>
            <VBtn
              variant="text"
              size="small"
              class="mf-acts__wide"
              :loading="acting === String(detailItem.resource_id) + 'scrape'"
              @click="act(detailItem, 'scrape', '刮削')"
            >刮削（纠错元数据）</VBtn>
          </div>
          <p class="mf-hintline">
            整理只取代表种以 link 方式入库，同组其余成员不动。慢动作在后台跑，关掉页面也不会断。
          </p>

          <button class="mf-fold" @click="sitesOpen = !sitesOpen">
            <span>{{ sitesOpen ? '收起' : `查看这个种的 ${detailMembers(detailItem).length} 个成员` }}</span>
            <VIcon :icon="sitesOpen ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="18" />
          </button>
          <div v-if="sitesOpen" class="mf-members">
            <div v-for="m in detailMembers(detailItem)" :key="m.hash" class="mf-members__r">
              <span class="mf-members__site">{{ m.site }}</span>
              <span class="mf-members__t">{{ m.title }}</span>
              <span class="mf-members__sz">{{ m.size >= 1 ? `${m.size.toFixed(1)}G` : `${Math.round(m.size * 1024)}M` }}</span>
            </div>
          </div>

          <div class="mf-danger">
            <div class="mf-danger__t">删除这份资源</div>
            <div class="mf-danger__d">
              会删掉 <b>{{ Number(detailItem.members_in_qb ?? 0) }} 个种</b>、<b>{{ (detailItem.sites || []).length }} 个站的保种记录</b>；
              勾选「同时删除文件」还会删掉 {{ sizeText(detailItem) }} 做种文件，<b>不可恢复</b>。
              <template v-if="Number(detailItem.members_in_qb ?? 0) === 1">
                <br>这份只有这一个种，删完库里就没有了。
              </template>
            </div>
            <VBtn
              variant="outlined"
              color="error"
              class="mf-danger__btn"
              :disabled="detailItem.deletable !== true || deleting"
              @click="deleteOne(detailItem)"
            >
              {{ detailItem.deletable === true ? '删除…' : '不可删（被拦）' }}
            </VBtn>
          </div>
        </template>
        <div v-else class="magicflow-table-empty">
          这份资源已经不在了
          <div class="mt-2"><VBtn size="small" variant="tonal" @click="screen = 'list'">回到清单</VBtn></div>
        </div>
      </div>

      <!-- 吸底删除条：没勾就不出现，勾了才写清代价 -->
      <div v-if="screen !== 'detail' && selectedItems.length" class="mf-sticky">
        <div class="mf-sticky__txt">
          <b>已选 {{ selectedItems.length }} 份 · {{ selectedTotalGb.toFixed(2) }} GB</b>
          {{ selectedSeedCount }} 个种<template v-if="selectedSingleCount"> · 其中 {{ selectedSingleCount }} 份只有这 1 个种</template>
        </div>
        <VBtn color="error" variant="flat" :disabled="deleting" @click="openConfirm">删除</VBtn>
      </div>
    </div>

    <!-- 桌面端：表格（保持原样，只修对账口径与说明文字） -->
    <template v-else>
      <header class="magicflow-panel__head">
        <div>
          <div class="text-subtitle-1 font-weight-medium">库内资源</div>
          <div class="text-body-2 text-medium-emphasis">
            共 {{ totalCount }} 份 · 媒体库 已入库 {{ Number(counts.in_media ?? 0) }} / 仅保种
            {{ Number(counts.seeding_only ?? 0) }} / 落点丢失 {{ Number(counts.dest_missing ?? 0) }}（= {{ mediaSum }}）
            · {{ Number(counts.deletable ?? 0) }} 份可删 · {{ blockedText }} · 占用
            {{ totalGb >= 1024 ? `${(totalGb / 1024).toFixed(1)} TB` : `${totalGb.toFixed(0)} GB` }}
          </div>
          <div class="magicflow-asset-hintline">
            保种资源账本 · 不是影视库
            <button class="magicflow-asset-info" @click="infoOpen = !infoOpen">
              {{ infoOpen ? '收起说明' : '这是什么？' }}
            </button>
          </div>
          <div v-if="infoOpen" class="magicflow-asset-hint">
            <b>此处「库」= 魔流资源账本（保种资产），不是飞牛影视媒体库。</b>
            「媒体库状态」按 MoviePilot 整理历史判定：仅保种 = 只在下载器做种、媒体库里查无此片；这不代表漏整理，刷流原盘多属此类。
            落点丢失 = 整理过但落点已不在，重新整理可重建链接。
          </div>
          <div v-if="infoOpen" class="magicflow-asset-hint">
            保护=手动保留（永不自动删） · 订阅整季=补这季缺集 · 整理=只取代表种以 link 入库，
            同组其余成员只读核验、<b>不强制校验</b> · 刮削=纠错元数据。慢动作在后台跑，关页面不断。
          </div>
        </div>
        <div class="magicflow-asset-filters">
          <VSelect
            v-model="siteFilter"
            :items="siteOptions"
            item-title="title"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            class="magicflow-asset-site-filter"
          />
          <VSelect
            v-model="mediaFilter"
            :items="MEDIA_STATES"
            item-title="title"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            class="magicflow-asset-site-filter"
          />
          <VSwitch
            v-model="includeStale"
            density="compact"
            hide-details
            color="warning"
            label="含账本残留"
            class="magicflow-asset-stale-switch"
          />
          <VSwitch
            v-model="onlyProtected"
            density="compact"
            hide-details
            color="success"
            label="只看已保护"
            class="magicflow-asset-stale-switch"
          />
          <VBtn
            size="small"
            variant="outlined"
            prepend-icon="mdi-file-search-outline"
            :loading="previewing"
            :disabled="loading"
            title="只读：列出每份资源会被整理的代表种、源路径与需人工项，不触发任何整理"
            @click="runPreview"
          >
            整理预演
          </VBtn>
          <VBtn
            size="small"
            variant="tonal"
            prepend-icon="mdi-refresh"
            :disabled="loading || deleting"
            @click="load"
          >
            刷新
          </VBtn>
          <VBtn
            size="small"
            variant="flat"
            color="error"
            prepend-icon="mdi-delete-outline"
            :disabled="!selectedIds.length || deleting"
            @click="openConfirm"
          >
            删除选中 ({{ selectedIds.length }})
          </VBtn>
        </div>
      </header>

      <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mt-3">{{ error }}</VAlert>
      <VAlert
        v-if="flash"
        :type="flash.type"
        variant="tonal"
        density="compact"
        closable
        class="mt-3"
        @click:close="flash = null"
      >
        {{ flash.text }}
      </VAlert>

      <div v-if="previewOpen && preview" class="magicflow-asset-preview">
        <div class="magicflow-asset-preview__head">
          <strong>整理预演（只读，未触发任何整理）</strong>
          <span>
            共 {{ Number(preview.counts?.total ?? 0) }} 份 · 可整理 {{ Number(preview.counts?.ready ?? 0) }}
            · 需人工 {{ Number(preview.counts?.manual_path ?? 0) }}
            · 电影型 {{ Number(preview.counts?.movie ?? 0) }}
            · 原盘 {{ Number(preview.counts?.bdmv ?? 0) }}
          </span>
          <VSpacer />
          <VBtn size="x-small" variant="text" icon="mdi-close" @click="previewOpen = false" />
        </div>
        <div class="magicflow-asset-preview__policy">
          代表种 = {{ preview.policy?.pick }} · 方式 = {{ preview.policy?.transfer_type }}
          · {{ preview.policy?.others }} · 失败项：{{ preview.policy?.on_failure }}
        </div>
        <div class="magicflow-asset-preview__list">
          <div
            v-for="it in (preview.items || []).slice(0, 25)"
            :key="it.resource_id || it.name"
            class="magicflow-asset-preview__row"
          >
            <VChip
              size="x-small"
              :color="it.verdict === 'ready' ? 'success' : undefined"
              variant="tonal"
            >{{ VERDICT_TEXT[it.verdict] || it.verdict }}</VChip>
            <b :title="it.seed_title">{{ it.name }}</b>
            <span>{{ Number(it.size_gb ?? 0).toFixed(1) }}G · {{ it.members_in_qb }} 颗 · {{ it.is_bdmv ? 'BDMV 原盘' : (it.is_dir ? '目录' : '单文件') }}</span>
            <code :title="it.content_path">{{ it.content_path || '（源路径不可达）' }}</code>
            <span class="magicflow-asset-preview__reason">{{ it.reason }}</span>
          </div>
          <div v-if="(preview.items || []).length > 25" class="magicflow-asset-preview__more">
            … 另有 {{ (preview.items || []).length - 25 }} 份；完整清单见接口 /assets/organize/preview
          </div>
        </div>
      </div>

      <div v-if="selectedIds.length" class="magicflow-bulk-bar">
        <span class="magicflow-bulk-bar__count">
          已选 {{ selectedIds.length }} 份资源 · {{ selectedSeedCount }} 个种 · {{ selectedTotalGb.toFixed(2) }} GB
          <template v-if="selectedSingleCount"> · 其中 {{ selectedSingleCount }} 份只有 1 个种</template>
        </span>
        <VSpacer />
        <VBtn size="small" variant="text" :disabled="deleting" @click="clearSelection">取消选择</VBtn>
      </div>

      <VDataTable
        class="magicflow-asset-table"
        :headers="headers"
        :items="visibleItems"
        :loading="loading"
        :items-per-page="10"
        density="comfortable"
      >
        <template #header.select>
          <VCheckbox
            :model-value="allSelected"
            :indeterminate="someSelected"
            :disabled="!deletableVisible.length"
            density="compact"
            hide-details
            aria-label="全选可删资产"
            @update:model-value="value => toggleAll(value)"
          />
        </template>
        <template #item.select="{ item }">
          <span :title="item.deletable === true ? '可删' : blockText(item)">
            <VCheckbox
              :model-value="item.deletable === true && selectedIds.includes(item.resource_id)"
              :disabled="item.deletable !== true"
              density="compact"
              hide-details
              color="error"
              :aria-label="item.deletable === true ? `选择 ${item.name || ''}` : `不可选：${blockText(item)}`"
              @click.stop
              @update:model-value="toggleRow(item)"
            />
          </span>
        </template>
        <template #item.name="{ item }">
          <div class="magicflow-asset-title">
            <strong>{{ item.name || '未命名资源' }}</strong>
            <span v-if="assetEpLabel(item)" class="magicflow-asset-ep">{{ assetEpLabel(item) }}</span>
            <span v-if="item.stale">仅账本残留（不在下载器）</span>
          </div>
        </template>
        <template #item.source_site="{ item }">{{ item.source_site || '—' }}</template>
        <template #item.sites="{ item }">{{ sitesText(item) }}</template>
        <template #item.members_in_qb="{ item }">{{ membersText(item) }}</template>
        <template #item.size_gb="{ item }">{{ Number(item.size_gb ?? 0).toFixed(2) }}</template>
        <template #item.media_library="{ item }">
          <VChip
            size="small"
            :color="mediaColor(item)"
            variant="tonal"
            :title="mediaTitle(item)"
          >{{ mediaText(item) }}</VChip>
        </template>
        <template #item.block="{ item }">
          <div class="magicflow-asset-blocks">
            <VChip size="small" :color="blockColor(item)" variant="tonal">{{ blockText(item) }}</VChip>
            <VChip v-if="item.protected" size="small" color="success" variant="tonal">手动保留</VChip>
          </div>
        </template>
        <template #item.act="{ item }">
          <div class="magicflow-asset-act">
            <VBtn
              size="x-small" variant="tonal"
              :color="item.protected ? undefined : 'success'"
              :prepend-icon="item.protected ? 'mdi-shield-off-outline' : 'mdi-shield-lock-outline'"
              :loading="acting === String(item.resource_id) + protectAction(item)"
              @click="act(item, protectAction(item), protectLabel(item))"
            >{{ protectLabel(item) }}</VBtn>
            <VBtn
              v-for="a in ACTIONS"
              :key="a.key"
              size="x-small" variant="outlined"
              :prepend-icon="a.icon"
              :loading="acting === String(item.resource_id) + a.key"
              :title="a.hint || a.label"
              @click="act(item, a.key, a.label)"
            >{{ a.label }}</VBtn>
          </div>
        </template>
        <template #no-data>
          <div class="magicflow-table-empty">
            {{ loading ? '正在读取库内资产…' : '当前筛选下没有库内资产' }}
          </div>
        </template>
      </VDataTable>
    </template>

    <AssetDeleteConfirm
      v-model="confirmOpen"
      :items="selectedItems"
      :loading="deleting"
      :narrow="narrow"
      @confirm="submitDelete"
    />
  </VSheet>
</template>

<style scoped>
/* ★ 15.9.0：行内养护动作按钮组（桌面表格用） */
.magicflow-asset-act {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
/* 次级养护动作统一「中性低强调」：去掉主题色名后描边按钮会继承 on-surface 全强调，
   反而比主操作（保留/取消保护）更抢眼。这里压到和指标卡副文本同档的 medium-emphasis，
   视觉层级不依赖任何主题色名，glass 主题下也不会变蓝。 */
.magicflow-asset-act :deep(.v-btn--variant-outlined) {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-asset-blocks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
/* ★ 19.12.64 整理预演清单（只读结果，不写任何状态） */
.magicflow-asset-preview {
  margin-top: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 10px 12px;
  min-inline-size: 0;
}
.magicflow-asset-preview__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 0.88rem;
}
.magicflow-asset-preview__head span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-asset-preview__policy {
  margin-top: 6px;
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-asset-preview__list {
  margin-top: 8px;
  max-height: 300px;
  overflow-y: auto;
}
.magicflow-asset-preview__row {
  display: grid;
  grid-template-columns: auto minmax(90px, 1.2fr) minmax(90px, 1fr) minmax(0, 1.6fr) minmax(0, 1.2fr);
  gap: 8px;
  align-items: center;
  padding: 5px 0;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  font-size: 0.78rem;
  min-inline-size: 0;
}
.magicflow-asset-preview__row > * { min-inline-size: 0; }
.magicflow-asset-preview__row b,
.magicflow-asset-preview__row code,
.magicflow-asset-preview__reason {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.magicflow-asset-preview__row b { font-weight: 600; }
.magicflow-asset-preview__row code { font-size: 0.72rem; opacity: 0.75; }
.magicflow-asset-preview__reason { opacity: 0.72; }
.magicflow-asset-preview__more { padding: 8px 0 2px; font-size: 0.78rem; opacity: 0.7; }
@media (max-width: 959px) {
  .magicflow-asset-preview__row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 8px;
  }
  .magicflow-asset-preview__row b { flex: 1 1 60%; }
  .magicflow-asset-preview__row code { flex: 1 1 100%; }
  .magicflow-asset-preview__reason { flex: 1 1 100%; }
}
/* ── 共享选择器（index.vue / 兄弟 tab 同有，此处复制一份；父页原样保留）──── */
.magicflow-panel {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
  min-inline-size: 0;
  padding: 16px;
}

.magicflow-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

.magicflow-bulk-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-block: 10px 4px;
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.12);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.28);
}

.magicflow-bulk-bar__count {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  margin-inline-end: 4px;
}

/* ── 本视图专属 ────────────────────────────────────────────────────────── */
.magicflow-assets {
  margin-block-start: 12px;
}

.magicflow-asset-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.magicflow-asset-site-filter {
  inline-size: 13rem;
  max-inline-size: 100%;
}

.magicflow-asset-stale-switch {
  flex: 0 0 auto;
}

.magicflow-asset-table {
  margin-block-start: 8px;
  background: transparent;
}

.magicflow-asset-table th:first-child,
.magicflow-asset-table td:first-child {
  padding-inline: 6px;
}

.magicflow-asset-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-inline-size: 30rem;
}

.magicflow-asset-title strong,
.magicflow-asset-title span {
  overflow-wrap: anywhere;
}

.magicflow-asset-title span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.78rem;
}

.magicflow-asset-hint {
  margin-top: 2px;
  font-size: 0.72rem;
  line-height: 1.35;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-asset-hintline {
  margin-top: 2px;
  font-size: 0.74rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-asset-info {
  margin-inline-start: 6px;
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
}
.magicflow-asset-info:hover { text-decoration: underline; }

/* ★ 15.8.21：季 / 集 标签 */
.magicflow-asset-ep {
  flex: 0 0 auto;
  font-size: 0.72rem;
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
  white-space: nowrap;
}

/* ══════════════════════════════════════════════════════════════════════
   19.12.92 窄屏三屏（.mf-m）—— 弹窗内全屏，边距 20px，可点区 ≥44
   ══════════════════════════════════════════════════════════════════════ */
.mf-m {
  display: flex;
  flex-direction: column;
  margin: -16px;                /* 吃掉 .magicflow-panel 的 padding，做满屏 */
  min-block-size: 100%;
  position: relative;
}
.mf-m__bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px 0 20px;
  min-block-size: 44px;
}
.mf-m__sub {
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.42);
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mf-m__info {
  margin: 4px 20px 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-size: 12px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-m__info p { margin: 0 0 6px; }
.mf-m__info p:last-child { margin-bottom: 0; }
.mf-m__body {
  flex: 1 1 auto;
  padding: 4px 20px 24px;
  min-inline-size: 0;
}
.mf-m__body--sticky { padding-block-end: 96px; }

.mf-kpi {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding-block-start: 4px;
}
.mf-kpi__big {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.05;
  font-variant-numeric: tabular-nums;
}
.mf-kpi__big i {
  font-style: normal;
  font-size: 16px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.4);
  margin-inline-start: 2px;
}
.mf-kpi__note {
  margin-inline-start: auto;
  font-size: 12.5px;
  line-height: 1.5;
  text-align: end;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-kpi__note span { display: block; white-space: nowrap; }
.mf-kpi__note b { color: rgb(var(--v-theme-on-surface)); font-weight: 600; font-variant-numeric: tabular-nums; }

.mf-axis { margin-block-start: 20px; }
.mf-axis__hd { display: flex; align-items: baseline; gap: 6px; margin-block-end: 8px; }
.mf-axis__hd h3 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-sum {
  margin-inline-start: auto;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-variant-numeric: tabular-nums;
}
.mf-tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.mf-tile {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  background: transparent;
  padding: 11px 10px 10px;
  text-align: start;
  font: inherit;
  color: inherit;
  cursor: pointer;
  min-block-size: 64px;
}
.mf-tile:active { background: rgba(var(--v-theme-on-surface), 0.04); }
.mf-tile.is-on {
  border-color: rgba(var(--v-theme-primary), 0.42);
  background: rgba(var(--v-theme-primary), 0.1);
}
.mf-tile.is-err {
  border-color: rgba(var(--v-theme-error), 0.3);
  background: rgba(var(--v-theme-error), 0.05);
}
.mf-tile__n {
  display: block;
  font-size: 23px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.mf-tile__n.is-err { color: rgb(var(--v-theme-error)); }
.mf-tile__l {
  display: block;
  margin-block-start: 3px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mf-axis2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-block-start: 10px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  padding: 11px 12px;
  background: rgba(var(--v-theme-on-surface), 0.022);
  cursor: pointer;
  min-block-size: 44px;
}
.mf-axis2__t { font-size: 12.5px; line-height: 1.45; color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity)); min-inline-size: 0; }
.mf-axis2__l1 { display: block; white-space: nowrap; }
.mf-axis2__l2 { display: block; font-size: 11.5px; color: rgba(var(--v-theme-on-surface), 0.42); }
.mf-axis2__t b { color: rgb(var(--v-theme-on-surface)); font-weight: 600; font-variant-numeric: tabular-nums; }
.mf-axis2__go {
  margin-inline-start: auto;
  display: flex;
  align-items: center;
  gap: 1px;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-primary));
}

.mf-alarm {
  margin-block-start: 14px;
  border: 1px solid rgba(var(--v-theme-error), 0.28);
  border-radius: 12px;
  background: rgba(var(--v-theme-error), 0.05);
  padding: 13px 14px;
}
.mf-alarm__top { display: flex; align-items: center; gap: 7px; }
.mf-alarm__nm { font-size: 14.5px; font-weight: 600; }
.mf-alarm__n {
  margin-inline-start: auto;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--v-theme-error));
  font-variant-numeric: tabular-nums;
}
.mf-alarm__why {
  margin-block-start: 5px;
  font-size: 12.5px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-alarm__why b { color: rgb(var(--v-theme-on-surface)); font-weight: 600; }
.mf-alarm__acts { display: flex; gap: 9px; margin-block-start: 11px; flex-wrap: wrap; }

.mf-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-block-start: 16px;
  block-size: 44px;
  padding-inline: 12px;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgba(var(--v-theme-on-surface), 0.4);
}
.mf-search input {
  flex: 1 1 auto;
  min-inline-size: 0;
  border: 0;
  background: none;
  outline: none;
  font: inherit;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface));
}
.mf-search input::-webkit-search-cancel-button { -webkit-appearance: none; }

.mf-chips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 12px 0 4px;
  margin-inline: -20px;
  padding-inline: 20px;
  scrollbar-width: none;
}
.mf-chips::-webkit-scrollbar { display: none; }
.mf-chip {
  block-size: 36px;
  padding-inline: 13px;
  border-radius: 18px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgba(var(--v-theme-on-surface), 0.03);
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font: 500 13px/1 inherit;
  white-space: nowrap;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
}
.mf-chip.is-on {
  background: rgb(var(--v-theme-primary));
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.mf-chip.is-on.is-err {
  background: rgb(var(--v-theme-error));
  border-color: rgb(var(--v-theme-error));
  color: rgb(var(--v-theme-on-error));
}
.mf-chip.is-on.is-warn {
  background: rgb(var(--v-theme-warning));
  border-color: rgb(var(--v-theme-warning));
  color: rgb(var(--v-theme-on-warning));
}
.mf-chip__c { font-variant-numeric: tabular-nums; opacity: 0.72; }

.mf-sec { display: flex; align-items: baseline; gap: 8px; margin: 16px 0 2px; }
.mf-sec h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-sec__n { font-size: 12px; color: rgba(var(--v-theme-on-surface), 0.4); font-variant-numeric: tabular-nums; }
.mf-sec__act {
  margin-inline-start: auto;
  display: flex;
  align-items: center;
  gap: 2px;
  min-block-size: 44px;
  padding-inline: 8px 0;
  border: 0;
  background: none;
  font: 500 13px/1 inherit;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
}
.mf-sort {
  margin-inline-start: auto;
  inline-size: 132px;
  flex: 0 0 auto;
}
.mf-sort :deep(.v-field) { font-size: 12.5px; }

.mf-card {
  display: flex;
  gap: 10px;
  padding-block: 13px;
  border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  cursor: pointer;
}
.mf-card:first-of-type { border-block-start: 0; }
.mf-card:active { background: rgba(var(--v-theme-on-surface), 0.025); }
.mf-card__ck {
  flex: 0 0 auto;
  inline-size: 28px;
  block-size: 28px;
  margin-block-start: 1px;
  border-radius: 7px;
  border: 1.5px solid rgba(var(--v-theme-on-surface), 0.22);
  background: transparent;
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
  padding: 0;
}
.mf-card__ck.is-on {
  background: rgb(var(--v-theme-primary));
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.mf-card__ck.is-lock {
  border: 0;
  background: none;
  color: rgba(var(--v-theme-on-surface), 0.4);
  cursor: default;
}
.mf-card__main { flex: 1 1 auto; min-inline-size: 0; }
.mf-card__l1 { display: flex; align-items: flex-start; gap: 6px; flex-wrap: wrap; }
.mf-card__nm {
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.3;
  min-inline-size: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.mf-card__meta {
  margin-block-start: 4px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-variant-numeric: tabular-nums;
}
.mf-card__meta b { font-weight: 600; }
.mf-card__flag {
  margin-block-start: 6px;
  display: flex;
  gap: 5px;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.mf-card__flag.is-warn { color: rgb(var(--v-theme-warning)); }
.mf-card__flag.is-err { color: rgb(var(--v-theme-error)); }

.mf-tag {
  flex: 0 0 auto;
  font-size: 11.5px;
  font-weight: 600;
  padding: 3px 7px;
  border-radius: 6px;
  white-space: nowrap;
  line-height: 1.3;
}
.mf-tag--err { background: rgba(var(--v-theme-error), 0.11); color: rgb(var(--v-theme-error)); }
.mf-tag--warn { background: rgba(var(--v-theme-warning), 0.14); color: rgb(var(--v-theme-warning)); }
.mf-tag--soft { background: rgba(var(--v-theme-on-surface), 0.06); color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity)); }
.mf-tag--ok { background: rgba(var(--v-theme-success), 0.13); color: rgb(var(--v-theme-success)); }

.mf-more {
  inline-size: 100%;
  min-block-size: 48px;
  margin-block-start: 6px;
  border: 0;
  border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: none;
  font: 500 13.5px/1 inherit;
  color: rgb(var(--v-theme-primary));
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  cursor: pointer;
}
.mf-preview-btn { inline-size: 100%; margin-block-start: 18px; text-transform: none; }
.mf-hintline {
  margin-block: 10px 0;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.42);
}
.mf-link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
  cursor: pointer;
}

.mf-sticky {
  position: fixed;
  inset-inline: 0;
  inset-block-end: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px calc(10px + env(safe-area-inset-bottom));
  background: rgba(var(--v-theme-surface), 0.96);
  backdrop-filter: blur(8px);
  border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.mf-sticky__txt {
  flex: 1 1 auto;
  min-inline-size: 0;
  font-size: 12.5px;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-sticky__txt b {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
  font-variant-numeric: tabular-nums;
}

.mf-hero { padding-block-start: 4px; }
.mf-hero__nm {
  font-size: 21px;
  font-weight: 650;
  letter-spacing: -0.01em;
  line-height: 1.28;
  overflow-wrap: anywhere;
}
.mf-hero__tags { display: flex; flex-wrap: wrap; gap: 6px; margin-block-start: 9px; }
.mf-hero__sum {
  margin-block-start: 10px;
  font-size: 13.5px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-hero__sum b { color: rgb(var(--v-theme-on-surface)); font-weight: 600; font-variant-numeric: tabular-nums; }

.mf-kv { margin: 16px 0 0; border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.mf-kv__r {
  display: flex;
  gap: 14px;
  padding-block: 11px;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  font-size: 13.5px;
}
.mf-kv__r dt {
  flex: 0 0 72px;
  margin: 0;
  padding-block-start: 1px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.42);
}
.mf-kv__r dd { margin: 0; flex: 1 1 auto; min-inline-size: 0; line-height: 1.5; overflow-wrap: anywhere; }
.mf-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  word-break: break-all;
}

.mf-acts { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-block-start: 18px; }
.mf-acts :deep(.v-btn) { text-transform: none; block-size: 44px; }
.mf-acts__wide { grid-column: 1 / -1; }

.mf-fold {
  inline-size: 100%;
  min-block-size: 48px;
  margin-block-start: 2px;
  border: 0;
  border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  font: 400 13.5px/1 inherit;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  cursor: pointer;
}
.mf-fold :deep(.v-icon) { margin-inline-start: auto; }
.mf-members { border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.mf-members__r {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding-block: 9px;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  font-size: 12.5px;
}
.mf-members__site { flex: 0 0 84px; color: rgba(var(--v-theme-on-surface), 0.5); }
.mf-members__t {
  flex: 1 1 auto;
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mf-members__sz { flex: 0 0 auto; font-variant-numeric: tabular-nums; }

.mf-danger {
  margin-block-start: 26px;
  border: 1px solid rgba(var(--v-theme-error), 0.26);
  border-radius: 12px;
  padding: 14px;
}
.mf-danger__t { font-size: 13px; font-weight: 600; color: rgb(var(--v-theme-error)); }
.mf-danger__d {
  margin-block-start: 5px;
  font-size: 12.5px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.mf-danger__d b { color: rgb(var(--v-theme-on-surface)); font-weight: 600; }
.mf-danger__btn { inline-size: 100%; margin-block-start: 12px; text-transform: none; block-size: 44px; }

@media (max-width: 699px) {
  .magicflow-panel { padding: 14px; }
  .mf-m { margin: -14px; }
  .magicflow-panel__head {
    flex-direction: column;
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .magicflow-asset-filters { inline-size: 100%; justify-content: flex-end; }
  .magicflow-asset-site-filter { inline-size: 100%; }
  .magicflow-asset-stale-switch { margin-inline-end: auto; }
}
</style>
