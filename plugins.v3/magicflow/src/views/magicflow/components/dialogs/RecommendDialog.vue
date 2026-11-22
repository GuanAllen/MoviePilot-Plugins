<script setup>
// MagicFlow 前端 · 推荐甄别弹窗
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（props 下 / emit 上）。
// ★ 19.12.90 移动端重做（稿：_design_mobile/recommend-mobile.html）：
//   ① 数字必须对得上账：506 = 0 待确认 + 27 未达门槛 + 108 已入库 + 5 已忽略 + 366 已转普通。
//      原来顶部只写 0+108+27，旁边却写「共 506 条」，366 条 downgraded 在界面上一个名字都没有。
//   ② 「已入库」里躺着 2 条整理失败的（import_result 报「没有找到可整理的媒体文件」），
//      chip 却写着「已入库」——骗人。单拎成「需要你看一眼」，给「重新整理」。
//   ③ 未达门槛那 27 条现在可以勾、可以一并入库（后端一直支持，界面从来没有入口），
//      并写清「差 0.2」——用户要判断的就是这点值不值得破例。
//   ④ 卡片点开进详情：为什么没达门槛 / 同季各版本 / 订阅整季 / 只收这一集 / 忽略并删除。
//      后两个动作（subscribe / unsubscribe / import）后端 15.8.25 就有，前端从没调过。
//   ⑤ ＜1G 一律写 MB：0.08G 写成 80 MB，碎片一眼看得出来。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
import { computed, ref, watch } from 'vue'
import { recommendStatusMeta } from '../../../../utils'
import {
  recName, recommendActionable, recGroupKey, recSeasonLabel, recEpisodeLabel,
  recIsSingle, recImportBroken, recImportDead, recNoteHuman, recSizeText,
} from '../../composables/useRecommend'

// 开关走 defineModel（Boolean）
const open = defineModel({ type: Boolean, default: false })

const props = defineProps({
  data: { type: Object, default: () => ({}) },
  items: { type: Array, default: () => [] },
  raw: { type: Array, default: () => [] },
  counts: { type: Object, default: () => ({}) },
  failed: { type: Array, default: () => [] },
  acting: { type: String, default: '' },
  selected: { type: Object, default: () => ({}) },
  selectedList: { type: Array, default: () => [] },
  batchActing: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits([
  'refresh', 'confirm', 'dismiss', 'import-rec', 'subscribe-rec', 'unsubscribe-rec',
  'toggle-rec', 'toggle-all', 'batch-import',
])

// ── 展示态（纯 UI，不向上改父状态）────────────────────────────
const activeFilter = ref('recommended')
const expanded = ref({})      // group_key -> true（同季展开）
const detail = ref(null)      // 当前详情记录
const askDismiss = ref(false) // 详情里「忽略并删除」二次确认
const refreshing = ref(false)
const PAGE = 12
const shown = ref(PAGE)

// 首帧定锚：有真·待确认就停在「待确认」，没有就落到「已入库」（今天线上就是 0 待确认）。
// 只定一次 —— 之后用户在哪儿就留在哪儿，不被 60s 轮询拽走。
let anchored = false
watch(() => props.counts, c => {
  if (anchored || !c || !c.total) return
  anchored = true
  activeFilter.value = (c.recommended || 0) > 0 ? 'recommended' : 'confirmed'
}, { immediate: true })

watch(() => props.data, () => { refreshing.value = false })
watch(activeFilter, () => { shown.value = PAGE })

const totalCount = computed(() => Number((props.counts || {}).total || 0))
const downgradedCount = computed(() => Number((props.counts || {}).downgraded || 0))
const failedCount = computed(() => (props.failed || []).length)

// 四个（有订阅记录时五个）数字都可点 = 筛选
const tiles = computed(() => {
  const c = props.counts || {}
  const out = [{ key: 'recommended', label: '待确认', n: Number(c.recommended || 0), tone: 'zero' }]
  if (Number(c.subscribed || 0)) out.push({ key: 'subscribed', label: '已订阅', n: Number(c.subscribed || 0), tone: 'sub' })
  out.push({ key: 'pending', label: '未达门槛', n: Number(c.pending || 0), tone: 'warn' })
  out.push({ key: 'confirmed', label: '已入库', n: Number(c.confirmed || 0), tone: 'ok' })
  out.push({ key: 'dismissed', label: '已忽略', n: Number(c.dismissed || 0), tone: 'mute' })
  return out
})

// 「已转普通」不在上面那排数字格里（它是历史，只从下面那行走），所以要单独给一个标题，
// 否则 activeTile 会退回第一格 —— 列表头写着「待确认 366 条」这种自相矛盾的标题。
const activeTile = computed(() => {
  if (activeFilter.value === 'downgraded') return { key: 'downgraded', label: '已转普通', n: downgradedCount.value, tone: 'mute' }
  return tiles.value.find(t => t.key === activeFilter.value) || tiles.value[0]
})

// 这一档的**原始条数**（对账口径，和上面数字格一致）；列表里同季已合并，行数会少几条。
const activeRawCount = computed(() => Number((props.counts || {})[activeFilter.value] || 0))

const filterItems = computed(() => (props.items || []).filter(r => String(r.status || '').toLowerCase() === activeFilter.value))
const visibleItems = computed(() => filterItems.value.slice(0, shown.value))
const restCount = computed(() => Math.max(0, filterItems.value.length - shown.value))

const selectableVisible = computed(() => visibleItems.value.filter(r => recommendActionable(r)))
// 「全选」按**当前这一档的全部**算（不是当前这一页）——按钮上写多少就选多少，
// 否则「未达门槛 27 条」旁边一个「全选 12」会让人以为还有 15 条选不到。
const selectableAll = computed(() => filterItems.value.filter(r => recommendActionable(r)))
const visibleAllChecked = computed(() => selectableAll.value.length > 0
  && selectableAll.value.every(r => !!props.selected[r.hash]))

const selSize = computed(() => {
  const map = new Map((props.items || []).map(r => [r.hash, Number(r.size_gb) || 0]))
  return (props.selectedList || []).reduce((sum, h) => sum + (map.get(h) || 0), 0)
})

// ── 文案 ──────────────────────────────────────────────────
const minRating = computed(() => Number(props.data.min_rating ?? 7.5))
const expireDays = computed(() => Number(props.data.expire_days ?? 7))

const shortTs = v => {
  const n = Number(v) || 0
  if (!n) return ''
  const d = new Date(n * 1000)
  const now = new Date()
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const md = `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  if (d.toDateString() === now.toDateString()) return `今天 ${hm}`
  return `${md} ${hm}`
}

const lastScan = computed(() => {
  const ts = Math.max(0, ...(props.raw || []).map(r => Number(r.updated_at) || 0))
  return ts ? shortTs(ts) : ''
})

const subline = computed(() => {
  // 详情页不再重复「首次发现」—— 下面 kv 里就有，同一句话出现两次是噪音。
  if (detail.value) return ''
  const bits = [`最近一次扫描 ${lastScan.value || '—'}`, `评分门槛 ${minRating.value}`]
  return bits.join(' · ')
})

// 体积：＜1G 一律 MB
const sizeText = gb => recSizeText(gb)
const ratingText = r => (Number(r) > 0 ? `${Number(r).toFixed(1)} 分` : '没有评分')

// 未达门槛的「差多少」——这屏唯一真正有用的信息
const gapText = rec => {
  const r = Number(rec.rating) || 0
  if (!r) return '没有评分'
  const d = Math.round((minRating.value - r) * 10) / 10
  return d > 0 ? `评分 ${r.toFixed(1)} · 差 ${d.toFixed(1)}` : `评分 ${r.toFixed(1)}`
}

const kindLabel = rec => {
  if (!rec) return ''
  if (rec.kind === 'single' || recIsSingle(rec)) return '单集'
  if (rec.kind === 'multi') return '多集'
  const s = String(rec.media && rec.media.type || '')
  return s || ''
}

// 「碎片」：整季却只有几百 MB —— 不可能是真的一整季，标出来免得当成正常入库
const isFragment = rec => String(rec.kind || '') === 'season' && Number(rec.size_gb || 0) < 0.3

const seasonLine = rec => {
  // 「集数未知」是开发口径，卡片上不出现：种名只到「季」时，就只写季。
  const bits = [recSeasonLabel(rec), recEpisodeLabel(rec)].filter(b => b && b !== '集数未知')
  return bits.join(' ')
}
const epText = rec => {
  const s = recEpisodeLabel(rec)
  return s && s !== '集数未知' ? s : '—'
}

// 卡片第二行（类型 / 季集 / 评分 / 体积）
const metaBits = rec => {
  const out = []
  const t = String((rec.media && rec.media.type) || '')
  if (t) out.push(t)
  const se = seasonLine(rec)
  if (se) out.push(se)
  if (Number(rec.rating) > 0) out.push(ratingText(rec.rating))
  const sz = sizeText(rec.size_gb)
  if (sz) out.push(sz)
  return out
}

// 卡片第三行：状态相关的「一句话」
const statusLine = rec => {
  const st = String(rec.status || '').toLowerCase()
  if (recImportDead(rec)) return '入库失败 · 临时种已不在下载器'
  if (recImportBroken(rec)) return rec.import_result || '整理失败'
  if (st === 'recommended') {
    const why = []
    if (Number(rec.rating) > 0) why.push(`评分 ${Number(rec.rating).toFixed(1)}`)
    if (rec.in_chart) why.push('在榜')
    if (rec.in_subscribe) why.push('已订阅')
    return `命中 · ${why.join(' · ') || '规则命中'}`
  }
  if (st === 'pending') return gapText(rec)
  if (st === 'confirmed') return rec.confirmed_at ? `已入库 · ${shortTs(rec.confirmed_at)}` : '已入库'
  if (st === 'subscribed') return '已订阅整季（MP 抓齐其余集）'
  if (st === 'dismissed') return rec.updated_at ? `已忽略 · ${shortTs(rec.updated_at)}` : '已忽略'
  if (st === 'downgraded') return recNoteHuman(rec) || '已转普通种'
  if (st === 'deleted') return '已过期删除'
  return recommendStatusMeta(rec.status).text
}

const statusTone = rec => {
  if (recImportBroken(rec)) return 'fail'
  const st = String(rec.status || '').toLowerCase()
  if (st === 'confirmed') return 'ok'
  if (st === 'pending') return 'warn'
  if (st === 'recommended') return 'hot'
  if (st === 'subscribed') return 'sub'
  return 'mute'
}

// ── 同季聚合（明细靠 raw；items 已按 group 去重，只剩代表行）──────
const groupMembers = rec => {
  const key = recGroupKey(rec)
  if (!key) return []
  return (props.raw || []).filter(it => recGroupKey(it) === key)
}
const otherMembers = rec => groupMembers(rec).filter(it => it.hash !== rec.hash)
function toggleGroup(rec) {
  const key = recGroupKey(rec)
  if (!key) return
  expanded.value = { ...expanded.value, [key]: !expanded.value[key] }
}
const groupSummary = rec => {
  const m = groupMembers(rec)
  if (m.length < 2) return ''
  if (isFragment(rec)) {
    const sizes = m.map(it => Number(it.size_gb) || 0)
    const lo = Math.round(Math.min(...sizes) * 1024)
    const hi = Math.round(Math.max(...sizes) * 1024)
    return `同季 ${m.length} 个版本全是 ${lo}–${hi} MB`
  }
  return `同季共 ${m.length} 个版本`
}

// ── 详情页文案 ────────────────────────────────────────────
const detailWhyTitle = computed(() => {
  const rec = detail.value
  if (!rec) return ''
  if (recImportBroken(rec)) return '为什么没进库'
  const st = String(rec.status || '').toLowerCase()
  if (st === 'pending') return '为什么没达门槛'
  if (st === 'confirmed') return '入库结果'
  if (st === 'recommended') return '为什么收它'
  if (st === 'downgraded') return '为什么转普通种'
  return '这条记录'
})

const detailWhyText = computed(() => {
  const rec = detail.value
  if (!rec) return ''
  if (recImportBroken(rec)) {
    // ★ 19.12.91 分两种，别再让用户对着一个必失败的按钮点第二遍
    if (recImportDead(rec)) {
      return `标记为已入库，但当时没整理成功：${rec.import_result}。这颗临时种现在已经不在下载器里了，`
        + '重新整理也找不到文件。要么「订阅整季」让 MoviePilot 去补，要么把这条从清单里移掉。'
    }
    return `标记为已入库，但整理时失败了：${rec.import_result}。文件应该还在下载器里，点「重新整理」再试一次。`
  }
  const st = String(rec.status || '').toLowerCase()
  if (st === 'pending') {
    const r = Number(rec.rating) || 0
    if (!r) return `没有评分，也不在榜、不在热映、不在你的订阅里 —— 三条都不满足，所以没自动收。`
    const d = Math.round((minRating.value - r) * 10) / 10
    if (d > 0) {
      return `评分 ${r.toFixed(1)}，门槛 ${minRating.value}，差 ${d.toFixed(1)}。也不在榜、不在热映、不在你的订阅里 —— 三条都不满足，所以没自动收。`
    }
    return `评分 ${r.toFixed(1)} 已经够，但不在榜、不在热映、也不在订阅里 —— 没过规则，所以没自动收。`
  }
  if (st === 'recommended') {
    const bits = []
    if (Number(rec.rating) > 0) bits.push(`评分 ${Number(rec.rating).toFixed(1)}（门槛 ${minRating.value}）`)
    if (rec.in_chart) bits.push('在榜')
    if (rec.in_subscribe) bits.push('在你订阅的季里')
    return `${bits.join('、') || '规则命中'}，所以打上了「${props.data.tag || '魔流-推荐'}」标签等你确认。`
  }
  if (st === 'confirmed') {
    // 有 import_result 就是整理回执；没有就别编「已提交」——这批 108 条里 106 条都没回执。
    if (String(rec.import_result || '').trim()) return `整理入库：${rec.import_result}`
    return '标记为已入库，但没有整理回执 —— 可能是手动确认的，或确认时「自动整理入库」是关的。种子文件按原样留着。'
  }
  if (st === 'downgraded') return `${recNoteHuman(rec) || '已转普通种'}。它不再占推荐名额，也不会被推荐规则清理。`
  if (st === 'dismissed') return '你忽略过这条，临时种已删除。'
  if (st === 'subscribed') return '已给这一季加了 MoviePilot 订阅，MP 会去抓其余集并整理到一起。'
  return ''
})

const daysLeft = computed(() => {
  const rec = detail.value
  if (!rec) return null
  const st = String(rec.status || '').toLowerCase()
  if (st !== 'pending' && st !== 'recommended') return null
  const seen = Number(rec.first_seen) || 0
  if (!seen) return null
  const gone = (Date.now() / 1000 - seen) / 86400
  return Math.max(0, Math.ceil(expireDays.value - gone))
})

// 动作按钮的动词：别对电影说「只收这一集」
const collectLabel = rec => {
  if (!rec) return '收下'
  if (String(rec.kind || '') === 'single' || recIsSingle(rec)) return '只收这一集'
  if (String(rec.kind || '') === 'multi') return `全 ${Number(rec.ep_begin) || 1}–${Number(rec.ep_end) || '?'} 集一起收`
  if (String(rec.kind || '') === 'season') return '收下这一季'
  const t = String((rec.media && rec.media.type) || '')
  if (t === '电影') return '收下这部电影'
  return '收下这个种'
}

// 单集只拿到一集 → 订阅整季补齐；整理失败的死账也是「缺集」，同样给这个出口
// （★ 19.12.91：以前只认 kind==='single'，幼女战记这种「标成整季、实际只有一个 E12」
//   恰好拿不到这个按钮 —— 而那才是它唯一能救回来的路）。
const canSubscribe = rec => !!rec && (recIsSingle(rec) || recImportDead(rec))
const isSubscribed = rec => String((rec || {}).status || '').toLowerCase() === 'subscribed'

// 「忽略并删除」= 删种+删文件。已经整理进库的那条不能给这个按钮（文件已经不在临时目录了）；
// 已订阅整季的也不给（种子还要留着喂 MP 抓其余集）。
const canDismiss = rec => {
  const st = String((rec || {}).status || '').toLowerCase()
  if (!st || st === 'dismissed' || st === 'deleted' || st === 'subscribed') return false
  if (st === 'confirmed' && !recImportBroken(rec)) return false
  return true
}
const hasDetailAction = rec => canDismiss(rec) || isSubscribed(rec) || recImportBroken(rec)
  || recommendActionable(rec) || String((rec || {}).status || '') === 'recommended'
const idleNote = rec => {
  const st = String((rec || {}).status || '').toLowerCase()
  if (st === 'confirmed') return '这条已经在库里，没有需要处理的动作。'
  if (st === 'dismissed') return '你已经忽略过这条，临时种已删除。'
  if (st === 'deleted') return '这条已过期删除。'
  return '这条没有需要处理的动作。'
}

// ── 交互 ─────────────────────────────────────────────────
function onRefresh() {
  refreshing.value = true
  emit('refresh')
}
function openDetail(rec) {
  detail.value = rec
  askDismiss.value = false
}
function closeDetail() {
  detail.value = null
  askDismiss.value = false
}
function doDismiss(hash) {
  emit('dismiss', hash)
  askDismiss.value = false
  closeDetail()
}
function doConfirm(hash) {
  emit('confirm', hash)
  closeDetail()
}
function doImport(hash) {
  emit('import-rec', hash)
}
function doSubscribe(hash) {
  emit('subscribe-rec', hash)
}
function doUnsubscribe(hash) {
  emit('unsubscribe-rec', hash)
}
function askDelete() {
  askDismiss.value = true
}
function cancelDelete() {
  askDismiss.value = false
}
function toggleAllVisible() {
  emit('toggle-all', selectableAll.value.map(r => r.hash))
}
function loadMore() {
  shown.value += PAGE
}
</script>

<template>
  <VDialog v-model="open" max-width="44rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-recommend-dialog">
      <header class="magicflow-settings-dialog__head">
        <VBtn
          v-if="detail"
          icon="mdi-chevron-left"
          size="small"
          variant="text"
          aria-label="返回列表"
          @click="closeDetail"
        />
        <span class="magicflow-settings-dialog__title">{{ detail ? '推荐详情' : '推荐甄别' }}</span>
        <VChip v-if="data.enabled === false" size="x-small" color="grey" variant="tonal">已关闭</VChip>
        <span class="magicflow-ops-dialog__spacer" />
        <VBtn
          v-if="!detail"
          icon="mdi-refresh"
          size="small"
          variant="text"
          aria-label="刷新"
          :loading="refreshing"
          @click="onRefresh"
        />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>

      <div v-if="subline" class="magicflow-ops-dialog__sub">{{ subline }}</div>

      <div class="magicflow-ops-dialog__body">

        <!-- ══════════ 列表 ══════════ -->
        <template v-if="!detail">

          <VAlert v-if="data.enabled === false" type="info" variant="tonal" density="compact" class="mb-2">
            推荐甄别已关闭（可在「插件设置 → 推荐」开启）
          </VAlert>

          <!-- ① 对账：四个数字都可点，等于筛选 -->
          <div class="mf-rc-tiles">
            <button
              v-for="t in tiles"
              :key="t.key"
              type="button"
              class="mf-rc-tile"
              :class="['is-' + t.tone, { 'is-on': activeFilter === t.key, 'is-zero': t.n === 0 && t.key !== 'recommended' }]"
              @click="activeFilter = t.key"
            >
              <b>{{ t.n }}</b>
              <span>{{ t.label }}</span>
            </button>
          </div>
          <p class="mf-rc-recon">
            另有 <b>{{ downgradedCount }}</b> 条已过临时期、转为普通种（历史记录）
            <button type="button" class="mf-rc-recon__go" @click="activeFilter = 'downgraded'">查看</button>
            <span class="mf-rc-recon__sum">合计 <b>{{ totalCount }}</b></span>
          </p>

          <!-- ② 需要你看一眼：标着已入库，其实没进库 -->
          <div v-if="failedCount" class="mf-rc-alarm">
            <div class="mf-rc-alarm__hd">
              <VIcon icon="mdi-alert-circle-outline" size="16" />
              <span class="t">需要你看一眼</span>
              <span class="n">{{ failedCount }}</span>
            </div>
            <div v-for="rec in failed" :key="'al-' + rec.hash" class="mf-rc-alarm__row">
              <div class="mf-rc-alarm__nm">{{ recName(rec) }}</div>
              <div class="mf-rc-alarm__why">
                <template v-if="recImportDead(rec)">当时没整理成功，临时种现在已经不在下载器里 —— 重试也找不到文件</template>
                <template v-else>{{ rec.import_result || '整理时没找到可整理的媒体文件 —— 库里其实没有' }}</template>
              </div>
              <div class="mf-rc-alarm__acts">
                <VBtn
                  v-if="!recImportDead(rec)"
                  size="small"
                  variant="tonal"
                  color="primary"
                  :loading="acting === rec.hash + 'import'"
                  @click="doImport(rec.hash)"
                >重新整理</VBtn>
                <VBtn size="small" variant="text" color="error" @click="openDetail(rec)">看详情</VBtn>
              </div>
            </div>
          </div>

          <!-- ③ 列表头：当前筛到哪一档（条数＝对账口径，组数＝同季合并后的行数） -->
          <div class="mf-rc-sec">
            <h3>{{ activeTile.label }}</h3>
            <span class="n">
              {{ activeRawCount }} 条<template v-if="filterItems.length !== activeRawCount"> · {{ filterItems.length }} 组</template>
            </span>
            <button
              v-if="selectableAll.length"
              class="act"
              type="button"
              @click="toggleAllVisible"
            >{{ visibleAllChecked ? '取消全选' : `全选 ${selectableAll.length}` }}</button>
          </div>

          <!-- ④ 卡片 -->
          <div class="mf-rc-list">
            <article
              v-for="rec in visibleItems"
              :key="rec.hash"
              class="mf-rc-card"
              :class="['is-' + statusTone(rec), { 'is-sel': !!selected[rec.hash] }]"
              role="button"
              tabindex="0"
              @click="openDetail(rec)"
              @keyup.enter="openDetail(rec)"
            >
              <div v-if="recommendActionable(rec)" class="mf-rc-card__box" @click.stop>
                <VCheckbox
                  :model-value="!!selected[rec.hash]"
                  density="compact"
                  hide-details
                  :aria-label="`选择 ${recName(rec)}`"
                  @update:model-value="emit('toggle-rec', rec.hash)"
                />
              </div>
              <div class="mf-rc-card__poster">
                <img v-if="rec.poster" :src="rec.poster" :alt="recName(rec)" loading="lazy" referrerpolicy="no-referrer" />
                <VIcon v-else icon="mdi-movie-open-outline" size="20" />
              </div>
              <div class="mf-rc-card__main">
                <div class="mf-rc-card__ttl">{{ recName(rec) }}</div>
                <div class="mf-rc-card__meta">
                  <template v-for="(b, i) in metaBits(rec)" :key="'m' + i">
                    <span v-if="i" class="sep">·</span>{{ b }}
                  </template>
                </div>
                <div class="mf-rc-card__st" :class="'is-' + statusTone(rec)">
                  <span v-if="isFragment(rec)" class="mf-rc-frag">碎片</span>{{ statusLine(rec) }}
                </div>
                <button
                  v-if="groupMembers(rec).length > 1"
                  class="mf-rc-card__more"
                  type="button"
                  @click.stop="toggleGroup(rec)"
                >
                  <VIcon :icon="expanded[recGroupKey(rec)] ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="14" />
                  {{ groupSummary(rec) }}
                </button>
                <ul v-if="expanded[recGroupKey(rec)]" class="mf-rc-vers" @click.stop>
                  <li v-for="m in otherMembers(rec)" :key="'gm-' + m.hash">
                    <span class="ep">{{ epText(m) }}</span>
                    <span class="sz">{{ sizeText(m.size_gb) || '—' }}</span>
                    <span class="st">{{ recommendStatusMeta(m.status).text }}</span>
                    <span v-if="!!selected[m.hash]" class="st is-ok">已勾选</span>
                  </li>
                </ul>
              </div>
            </article>

            <button v-if="restCount" class="mf-rc-fold" type="button" @click="loadMore">
              还有 {{ restCount }} 组
              <VIcon icon="mdi-chevron-down" size="16" />
            </button>

            <div v-if="!filterItems.length" class="mf-rc-empty">
              <template v-if="activeFilter === 'recommended'">
                <div class="t">今天没有待确认</div>
                <div class="d">有新的候选时会出现在最上面，并推一条通知。</div>
              </template>
              <template v-else-if="activeFilter === 'pending'">
                <div class="t">没有未达门槛的候选</div>
                <div class="d">评分门槛 {{ minRating }}，目前在等的都过了。</div>
              </template>
              <template v-else-if="activeFilter === 'downgraded'">
                <div class="t">没有历史记录</div>
                <div class="d">临时种过期或被判定不是整季后会落到这里。</div>
              </template>
              <template v-else>
                <div class="t">这一档是空的</div>
                <div class="d">换个数字看看。</div>
              </template>
            </div>
          </div>
        </template>

        <!-- ══════════ 详情 ══════════ -->
        <template v-else>

          <div class="mf-rc-hero">
            <div class="mf-rc-hero__poster">
              <img v-if="detail.poster" :src="detail.poster" :alt="recName(detail)" referrerpolicy="no-referrer" />
              <VIcon v-else icon="mdi-movie-open-outline" size="24" />
            </div>
            <div class="mf-rc-hero__main">
              <h3>{{ recName(detail) }}</h3>
              <div class="sub">
                {{ [(detail.media && detail.media.type), (detail.media && detail.media.year), seasonLine(detail)].filter(Boolean).join(' · ') }}
              </div>
              <div class="tags">
                <span v-if="kindLabel(detail)" class="chip">{{ kindLabel(detail) }}</span>
                <span v-if="sizeText(detail.size_gb)" class="chip">{{ sizeText(detail.size_gb) }}</span>
                <span class="chip" :class="'is-' + statusTone(detail)">{{ recImportBroken(detail) ? '入库失败' : recommendStatusMeta(detail.status).text }}</span>
              </div>
            </div>
          </div>

          <div class="mf-rc-why" :class="'is-' + statusTone(detail)">
            <div class="h">{{ detailWhyTitle }}</div>
            <div class="l">{{ detailWhyText }}</div>
          </div>

          <table class="mf-rc-kv">
            <tr><th>首次发现</th><td>{{ shortTs(detail.first_seen) || '—' }}</td></tr>
            <tr v-if="daysLeft !== null">
              <th>临时种</th>
              <td>还剩 {{ daysLeft }} 天（到期自动转普通，不删文件）</td>
            </tr>
            <tr><th>评分</th><td>{{ ratingText(detail.rating) }}<template v-if="Number(detail.rating) > 0 && (String(detail.status || '') === 'pending' || String(detail.status || '') === 'recommended')"> · 门槛 {{ minRating }}</template></td></tr>
            <tr v-if="otherMembers(detail).length"><th>同季其它</th><td>{{ otherMembers(detail).length }} 个版本</td></tr>
            <tr v-if="detail.import_result && !recImportBroken(detail)"><th>整理结果</th><td>{{ detail.import_result }}</td></tr>
            <tr v-if="detail.note && !recImportBroken(detail)"><th>{{ String(detail.status || '') === 'confirmed' ? '此前记录' : '记录说明' }}</th><td>{{ recNoteHuman(detail) || detail.note }}</td></tr>
          </table>

          <ul v-if="otherMembers(detail).length" class="mf-rc-vers is-detail">
            <li v-for="m in otherMembers(detail)" :key="'dv-' + m.hash">
              <span class="ep">{{ epText(m) }}</span>
              <span class="sz">{{ sizeText(m.size_gb) || '—' }}</span>
              <span class="st">{{ recommendStatusMeta(m.status).text }}</span>
            </li>
          </ul>

          <div class="mf-rc-foot">
            <template v-if="isSubscribed(detail)">
              <VBtn size="small" variant="outlined" :loading="acting === detail.hash + 'unsubscribe'" @click="doUnsubscribe(detail.hash)">
                退订整季
              </VBtn>
            </template>
            <template v-else>
              <VBtn
                v-if="canSubscribe(detail)"
                size="small"
                color="primary"
                variant="flat"
                :loading="acting === detail.hash + 'subscribe'"
                @click="doSubscribe(detail.hash)"
              >订阅整季（MP 去抓其余集）</VBtn>
            </template>

            <VBtn
              v-if="recImportBroken(detail) && !recImportDead(detail)"
              size="small"
              color="primary"
              variant="flat"
              :loading="acting === detail.hash + 'import'"
              @click="doImport(detail.hash)"
            >重新整理</VBtn>
            <VBtn
              v-else-if="recommendActionable(detail) || String(detail.status || '') === 'recommended'"
              size="small"
              color="primary"
              :variant="canSubscribe(detail) ? 'outlined' : 'flat'"
              :loading="acting === detail.hash + 'confirm'"
              @click="doConfirm(detail.hash)"
            >{{ collectLabel(detail) }}</VBtn>

            <VBtn
              v-if="canDismiss(detail)"
              size="small"
              variant="text"
              :color="recImportDead(detail) ? undefined : 'error'"
              :loading="acting === detail.hash + 'dismiss'"
              @click="recImportDead(detail) ? doDismiss(detail.hash) : askDelete()"
            >{{ recImportDead(detail) ? '从清单里移除' : '忽略并删除临时种' }}</VBtn>
            <span v-if="!hasDetailAction(detail)" class="mf-rc-done-note">{{ idleNote(detail) }}</span>
          </div>

          <div v-if="askDismiss" class="mf-rc-ask">
            <div>「忽略」会删掉这个临时种（含已下载文件），不能撤销。</div>
            <div class="acts">
              <VBtn size="small" variant="text" @click="cancelDelete">取消</VBtn>
              <VBtn size="small" color="error" variant="flat" @click="doDismiss(detail.hash)">确认删除</VBtn>
            </div>
          </div>
          <p v-else-if="canDismiss(detail) && !recImportDead(detail)" class="mf-rc-danger-note">「忽略」会删掉这个临时种，不能撤销。</p>

        </template>
      </div>

      <!-- ⑤ 吸底条：只在有勾选时出现（没有勾选就不摆一个禁用的按钮） -->
      <div v-if="!detail && selectedList.length" class="mf-rc-bar">
        <div class="cnt">
          <b>已选 {{ selectedList.length }} 条</b>
          <span v-if="selSize">共 {{ selSize.toFixed(1) }} GB</span>
        </div>
        <VBtn
          color="primary"
          variant="flat"
          size="small"
          :loading="batchActing"
          @click="emit('batch-import', false)"
        >一并入库</VBtn>
      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 共享选择器（.magicflow-dialog / settings-dialog__head·__title / ops-dialog__spacer·__sub·__body）：
   VDialog 会 teleport 到 body，父 scoped 规则够不到子内部，必须组件内自带一份（纯复制，零改动）。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}
.magicflow-settings-dialog__head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 10px 8px 18px;
}
.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
  margin-inline-end: 4px;
}
.magicflow-ops-dialog__spacer { flex: 1 1 auto; }
.magicflow-ops-dialog__sub {
  padding: 0 18px 6px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-ops-dialog__body { padding: 4px 18px 20px; overflow: auto; flex: 1 1 auto; min-height: 0; }

/* MoviePilot 会给表单控件套一层 .app-responsive-input（默认 ~72px 高），在自研分块里收紧 */
.magicflow-recommend-dialog .app-responsive-input {
  min-block-size: 0 !important;
  block-size: auto !important;
  padding-block: 0 !important;
  margin-block: 0 !important;
}

/* ── 弹窗根 ─────────────────────────────────────────── */
.magicflow-recommend-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}

/* ── ① 对账四格 ─────────────────────────────────────── */
.mf-rc-tiles {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  gap: 6px;
  margin-block: 2px 0;
}
.mf-rc-tile {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-items: flex-start;
  min-block-size: 54px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  color: inherit;
  text-align: start;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.mf-rc-tile b {
  font-size: 1.22rem;
  font-weight: 700;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.mf-rc-tile span {
  font-size: 0.68rem;
  line-height: 1.2;
  color: rgba(var(--v-theme-on-surface), 0.55);
  white-space: nowrap;
}
.mf-rc-tile.is-warn b { color: rgb(var(--v-theme-warning)); }
.mf-rc-tile.is-ok b { color: rgb(var(--v-theme-success)); }
.mf-rc-tile.is-sub b { color: #6366f1; }
.mf-rc-tile.is-zero b { color: rgba(var(--v-theme-on-surface), 0.5); }
.mf-rc-tile.is-mute b { color: rgba(var(--v-theme-on-surface), 0.62); }
.mf-rc-tile.is-on {
  border-color: rgba(var(--v-theme-primary), 0.55);
  background: rgba(var(--v-theme-primary), 0.1);
}
.mf-rc-tile.is-on b { color: rgb(var(--v-theme-primary)); }
.mf-rc-tile.is-on span { color: rgb(var(--v-theme-primary)); }

.mf-rc-recon {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 6px;
  margin: 8px 0 0;
  font-size: 0.74rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.mf-rc-recon b { color: rgba(var(--v-theme-on-surface), 0.8); font-variant-numeric: tabular-nums; }
.mf-rc-recon__go {
  padding: 0;
  border: 0;
  background: none;
  color: rgb(var(--v-theme-primary));
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}
.mf-rc-recon__sum { margin-inline-start: auto; }

/* ── ② 需要你看一眼 ─────────────────────────────────── */
.mf-rc-alarm {
  margin-block-start: 14px;
  padding: 10px 12px 4px;
  border: 1px solid rgba(var(--v-theme-error), 0.32);
  border-radius: 12px;
  background: rgba(var(--v-theme-error), 0.07);
}
.mf-rc-alarm__hd {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 600;
  color: rgb(var(--v-theme-error));
}
.mf-rc-alarm__hd .n {
  margin-inline-start: auto;
  padding: 0 7px;
  border-radius: 99px;
  background: rgb(var(--v-theme-error));
  color: #fff;
  font-size: 0.7rem;
  font-variant-numeric: tabular-nums;
}
.mf-rc-alarm__row { padding-block: 8px; border-block-start: 1px solid rgba(var(--v-theme-error), 0.16); margin-block-start: 8px; }
.mf-rc-alarm__row:first-of-type { border-block-start: 0; }
.mf-rc-alarm__nm { font-size: 0.86rem; font-weight: 600; }
.mf-rc-alarm__why {
  margin-block-start: 2px;
  font-size: 0.74rem;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.62);
}
.mf-rc-alarm__acts { display: flex; gap: 4px; margin-block-start: 6px; }

/* ── ③ 列表头 ───────────────────────────────────────── */
.mf-rc-sec {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-block: 18px 6px;
}
.mf-rc-sec h3 { margin: 0; font-size: 0.92rem; font-weight: 600; }
.mf-rc-sec .n { font-size: 0.78rem; color: rgba(var(--v-theme-on-surface), 0.45); font-variant-numeric: tabular-nums; }
.mf-rc-sec .act {
  margin-inline-start: auto;
  padding: 6px 4px;
  border: 0;
  background: none;
  color: rgb(var(--v-theme-primary));
  font: inherit;
  font-size: 0.76rem;
  font-weight: 600;
  cursor: pointer;
}

/* ── ④ 卡片 ─────────────────────────────────────────── */
.mf-rc-list { display: flex; flex-direction: column; gap: 6px; }
.mf-rc-card {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.025);
  cursor: pointer;
}
.mf-rc-card:hover { background: rgba(var(--v-theme-on-surface), 0.055); }
.mf-rc-card.is-sel { border-color: rgba(var(--v-theme-primary), 0.45); background: rgba(var(--v-theme-primary), 0.07); }
.mf-rc-card__box { flex: 0 0 auto; display: flex; align-items: center; min-block-size: 44px; margin-inline: -4px -6px; }
.mf-rc-card__poster {
  flex: 0 0 auto;
  inline-size: 40px;
  block-size: 60px;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.mf-rc-card__poster img { inline-size: 100%; block-size: 100%; object-fit: cover; display: block; }
.mf-rc-card__main { min-inline-size: 0; flex: 1 1 auto; display: flex; flex-direction: column; gap: 2px; }
.mf-rc-card__ttl {
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.mf-rc-card__meta {
  font-size: 0.74rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-variant-numeric: tabular-nums;
}
.mf-rc-card__meta .sep { margin-inline: 4px; opacity: 0.55; }
.mf-rc-card__st {
  font-size: 0.74rem;
  line-height: 1.45;
  color: rgba(var(--v-theme-on-surface), 0.6);
  overflow-wrap: anywhere;
}
.mf-rc-card__st.is-ok { color: rgb(var(--v-theme-success)); }
.mf-rc-card__st.is-warn { color: rgb(var(--v-theme-warning)); }
.mf-rc-card__st.is-hot { color: rgb(var(--v-theme-primary)); }
.mf-rc-card__st.is-sub { color: #6366f1; }
.mf-rc-card__st.is-fail { color: rgb(var(--v-theme-error)); }
.mf-rc-card__st.is-mute { color: rgba(var(--v-theme-on-surface), 0.42); }
.mf-rc-frag {
  display: inline-block;
  margin-inline-end: 5px;
  padding: 0 5px;
  border-radius: 4px;
  background: rgba(var(--v-theme-error), 0.16);
  color: rgb(var(--v-theme-error));
  font-size: 0.7rem;
  font-weight: 600;
}
.mf-rc-card__more {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-block-start: 2px;
  align-self: flex-start;
  padding: 4px 0;
  border: 0;
  background: none;
  color: rgb(var(--v-theme-primary));
  font: inherit;
  font-size: 0.74rem;
  cursor: pointer;
}

.mf-rc-vers { list-style: none; margin: 4px 0 0; padding: 0; }
.mf-rc-vers li {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding-block: 2px;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.mf-rc-vers .ep { min-inline-size: 3.6rem; color: rgb(var(--v-theme-primary)); }
.mf-rc-vers .sz { min-inline-size: 4.2rem; font-variant-numeric: tabular-nums; }
.mf-rc-vers .st { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mf-rc-vers.is-detail {
  margin-block-start: 10px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 10px;
}

.mf-rc-fold {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  inline-size: 100%;
  min-block-size: 40px;
  margin-block-start: 4px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.16);
  border-radius: 10px;
  background: none;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font: inherit;
  font-size: 0.78rem;
  cursor: pointer;
}
.mf-rc-empty { padding: 26px 10px; text-align: center; }
.mf-rc-empty .t { font-size: 0.88rem; font-weight: 600; }
.mf-rc-empty .d { margin-block-start: 4px; font-size: 0.76rem; color: rgba(var(--v-theme-on-surface), 0.5); }

/* ── 吸底条 ─────────────────────────────────────────── */
.mf-rc-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 18px calc(10px + env(safe-area-inset-bottom));
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgb(var(--v-theme-surface));
}
.mf-rc-bar .cnt { display: flex; flex-direction: column; line-height: 1.2; min-inline-size: 0; }
.mf-rc-bar .cnt b { font-size: 0.88rem; }
.mf-rc-bar .cnt span { font-size: 0.72rem; color: rgba(var(--v-theme-on-surface), 0.5); font-variant-numeric: tabular-nums; }
.mf-rc-bar .v-btn { margin-inline-start: auto; }

/* ── ⑤ 详情 ─────────────────────────────────────────── */
.mf-rc-hero { display: flex; gap: 12px; align-items: flex-start; padding-block: 4px 10px; }
.mf-rc-hero__poster {
  flex: 0 0 auto;
  inline-size: 64px;
  block-size: 96px;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.mf-rc-hero__poster img { inline-size: 100%; block-size: 100%; object-fit: cover; display: block; }
.mf-rc-hero__main { min-inline-size: 0; }
.mf-rc-hero__main h3 {
  margin: 0;
  font-size: 1.08rem;
  font-weight: 700;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.mf-rc-hero__main .sub {
  margin-block-start: 4px;
  font-size: 0.76rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.mf-rc-hero__main .tags { display: flex; flex-wrap: wrap; gap: 5px; margin-block-start: 8px; }
.mf-rc-hero__main .chip {
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.07);
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
.mf-rc-hero__main .chip.is-ok { background: rgba(var(--v-theme-success), 0.14); color: rgb(var(--v-theme-success)); }
.mf-rc-hero__main .chip.is-warn { background: rgba(var(--v-theme-warning), 0.16); color: rgb(var(--v-theme-warning)); }
.mf-rc-hero__main .chip.is-fail { background: rgba(var(--v-theme-error), 0.14); color: rgb(var(--v-theme-error)); }
.mf-rc-hero__main .chip.is-hot { background: rgba(var(--v-theme-primary), 0.14); color: rgb(var(--v-theme-primary)); }

.mf-rc-why {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.05);
  border-inline-start: 3px solid rgba(var(--v-theme-on-surface), 0.25);
}
.mf-rc-why.is-warn { background: rgba(var(--v-theme-warning), 0.09); border-inline-start-color: rgb(var(--v-theme-warning)); }
.mf-rc-why.is-fail { background: rgba(var(--v-theme-error), 0.08); border-inline-start-color: rgb(var(--v-theme-error)); }
.mf-rc-why.is-ok { background: rgba(var(--v-theme-success), 0.08); border-inline-start-color: rgb(var(--v-theme-success)); }
.mf-rc-why.is-hot { background: rgba(var(--v-theme-primary), 0.08); border-inline-start-color: rgb(var(--v-theme-primary)); }
.mf-rc-why .h { font-size: 0.78rem; font-weight: 600; margin-block-end: 4px; }
.mf-rc-why .l { font-size: 0.8rem; line-height: 1.6; color: rgba(var(--v-theme-on-surface), 0.72); }

.mf-rc-kv { inline-size: 100%; margin-block-start: 12px; border-collapse: collapse; }
.mf-rc-kv th,
.mf-rc-kv td {
  padding: 7px 0;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  font-size: 0.78rem;
  line-height: 1.5;
  text-align: start;
  vertical-align: top;
}
.mf-rc-kv th { inline-size: 5.2rem; font-weight: 400; color: rgba(var(--v-theme-on-surface), 0.5); white-space: nowrap; }
.mf-rc-kv td { color: rgba(var(--v-theme-on-surface), 0.8); overflow-wrap: anywhere; }

.mf-rc-foot { display: flex; flex-wrap: wrap; gap: 8px; margin-block-start: 16px; }
.mf-rc-done-note { font-size: 0.78rem; color: rgba(var(--v-theme-on-surface), 0.5); }
.mf-rc-danger-note {
  margin: 8px 0 0;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.mf-rc-ask {
  margin-block-start: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(var(--v-theme-error), 0.35);
  border-radius: 10px;
  background: rgba(var(--v-theme-error), 0.07);
  font-size: 0.78rem;
  line-height: 1.5;
}
.mf-rc-ask .acts { display: flex; justify-content: flex-end; gap: 6px; margin-block-start: 8px; }

@media (max-width: 959px) {
  .magicflow-recommend-dialog {
    block-size: 100dvh;
    max-block-size: 100dvh;
    border-radius: 0;
  }
  .magicflow-ops-dialog__body { padding: 4px 16px 24px; }
  .mf-rc-tile { padding: 7px 8px; min-block-size: 52px; }
  .mf-rc-tile b { font-size: 1.16rem; }
  .mf-rc-card { padding: 10px 6px; }
  .mf-rc-bar { padding-inline: 16px; }
}
</style>
