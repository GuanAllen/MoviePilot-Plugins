<script setup>
// MagicFlow 前端 · 魔力兑换看板（★ 19.16.29：上传量 + 邀请名额 + 临时邀请）
// 只读看板：各站当前魔力 + 三类兑换项；兑换走 emit('act') 交父页二次确认。
// 数据向下（props）、事件向上（emit）；子组件不直接发写请求。
import { computed, ref } from 'vue'

const open = defineModel({ type: Boolean, default: false })
const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  acting: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
})
const emit = defineEmits(['refresh', 'act'])

const rows = computed(() => (props.data && props.data.sites) || [])
const totals = computed(() => (props.data && props.data.totals) || {})
// ★ 站点筛选：可搜索下拉（不是纯文本输入）——点开即见全部站，选中即单站；
//   仍保留输入能力（站名 / 域名都能匹配），站点变多也不怕。null = 全部。
const pick = ref(null)
const filtered = computed(() => {
  if (pick.value === null || pick.value === undefined || pick.value === '') return rows.value
  return rows.value.filter(r => r.site_id === pick.value)
})
const siteItems = computed(() => rows.value.map(r => {
  const c = canOf(r)
  const tail = !r.ok ? '抓取失败' : (c ? `可换 ${c}` : '全禁')
  return { title: `${r.site_name || r.site_id} · ${tail}`, value: r.site_id }
}))
const onlyOk = ref(false)
const shown = computed(() => onlyOk.value
  ? filtered.value.filter(r => r.ok && (r.items || []).some(i => !i.disabled))
  : filtered.value)
// 空态说实话：区分「没数据 / 选了失败站 / 该站全禁 / 没有站有可换项」
const emptyText = computed(() => {
  if (!rows.value.length) return '暂无数据'
  if (pick.value) {
    const r = rows.value.find(x => x.site_id === pick.value)
    if (r && !r.ok) return '该站抓取失败，原因见站点卡'
    return onlyOk.value ? '该站当前没有可换项' : '该站没有兑换项'
  }
  return onlyOk.value ? '没有站点有可换项' : '暂无数据'
})

const KIND_ORDER = ['upload', 'invite', 'temp_invite']
const KIND_LABEL = { upload: '上传量', invite: '邀请名额', temp_invite: '临时邀请' }

function groupsOf(r) {
  const map = {}
  for (const it of (r.items || [])) {
    const k = it.kind || 'upload'
    if (!map[k]) map[k] = []
    map[k].push(it)
  }
  return KIND_ORDER
    .filter(k => (map[k] || []).length)
    .map(k => ({
      kind: k,
      label: KIND_LABEL[k],
      items: map[k],
      can: map[k].filter(x => !x.disabled).length,
      total: map[k].length,
    }))
}

function fmtNum(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}
function fmtSize(gb) {
  if (gb === null || gb === undefined) return '—'
  if (gb >= 1024) return (gb / 1024).toFixed(gb / 1024 >= 10 ? 0 : 1) + ' TB'
  return (gb >= 10 ? gb.toFixed(0) : gb.toFixed(1)) + ' GB'
}
function amtOf(it, kind) {
  if (kind === 'upload') return fmtSize(it.size_gb)
  return String(it.count || 1)
}
// 域名精简：去 scheme / www. / 路径 / 尾斜杠
function shortDomain(d) {
  let t = String(d || '').trim().toLowerCase()
  if (t.includes('://')) t = t.split('://')[1] || ''
  t = t.split('/')[0].split('?')[0]
  while (t.startsWith('www.')) t = t.slice(4)
  return t
}
// 长禁用原因压成短标签（完整文案放 title）：邀请类常见的是等级门槛
function shortWhy(it) {
  const w = String(it.disabled_reason || '')
  if (!w) return '不可换'
  if (w.includes('等级')) return '等级不足'
  if (w.includes('分享率')) return '分享率已高'
  if (w.includes('魔力') || w.includes('币') || w.includes('不足')) return '余额不足'
  return w.length > 8 ? w.slice(0, 8) + '…' : w
}
// 站点可换总数（角标）：三类可换之和，与顶部统计可对账
function canOf(r) {
  return (r.items || []).filter(i => !i.disabled).length
}
function canKind(k) {
  return (totals.value.exchangeable_by_kind || {})[k] || 0
}
</script>

<template>
  <VDialog v-model="open" max-width="52rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-be-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">魔力兑换</span>
        <VSpacer />
        <VBtn icon="mdi-refresh" size="small" variant="text" :loading="loading"
              aria-label="刷新看板" @click="emit('refresh')" />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>

      <!-- 一行统计（替代原解释文案，规则细节见 title / wiki） -->
      <div class="magicflow-be__sum">
        <span class="magicflow-be__sum-big"><em>{{ totals.ok ?? '—' }}</em> 站已取到</span>
        <span class="magicflow-be__sum-sep"></span>
        <span class="magicflow-be__sum-sub"><em>{{ totals.exchangeable ?? 0 }}</em> 项可换</span>
        <span class="magicflow-be__sum-detail">
          上传 {{ canKind('upload') }} · 邀请 {{ canKind('invite') }} · 临时 {{ canKind('temp_invite') }}
        </span>
        <span class="magicflow-be__sum-i"
              title="可换上传量 / 邀请名额 / 临时邀请。灰色=站点判定不可换（分享率已很高 / 余额不足 / 等级不足）。点兑换需二次确认，提交前会重抓页面核对。规则详见 wiki。">i</span>
      </div>

      <div class="magicflow-be__bar">
        <VSelect v-model="pick" :items="siteItems" item-title="title" item-value="value"
                 density="compact" variant="outlined" hide-details clearable
                 prepend-inner-icon="mdi-format-list-bulleted" placeholder="全部站点"
                 class="magicflow-be__search" />
        <VSwitch v-model="onlyOk" density="compact" hide-details inset color="primary"
                 label="只看可换" class="magicflow-be__switch" />
      </div>

      <div class="magicflow-be__body">
        <div v-if="loading && !rows.length" class="magicflow-be__empty">正在拉取各站魔力余额…</div>
        <div v-else-if="!shown.length" class="magicflow-be__empty">{{ emptyText }}</div>

        <div v-for="r in shown" :key="r.site_id" class="magicflow-be-card">
          <div class="magicflow-be-card__head">
            <div class="magicflow-be-card__id">
              <span class="magicflow-be-card__nm">{{ r.site_name }}</span>
              <span v-if="r.ok" class="magicflow-be-badge"
                    :class="{ 'is-none': canOf(r) === 0 }">
                {{ canOf(r) ? '可换 ' + canOf(r) : '无可换' }}
              </span>
              <span class="magicflow-be-card__dm">{{ shortDomain(r.domain) }}</span>
            </div>
            <div class="magicflow-be-card__bal">
              <template v-if="r.ok">
                <strong>{{ fmtNum(r.balance) }}</strong>
                <span class="magicflow-be-card__cur">{{ r.currency || '魔力' }}</span>
              </template>
              <span v-else class="magicflow-be-card__err" :title="r.why">未取到 · {{ r.why || '失败' }}</span>
            </div>
          </div>

          <div v-if="r.ok && r.items.length" class="magicflow-be-card__items">
            <div v-for="g in groupsOf(r)" :key="g.kind" class="magicflow-be-group">
              <div class="magicflow-be-group__h">
                <span class="magicflow-be-group__t">{{ g.label }}</span>
                <span class="magicflow-be-group__c">{{ g.total }} 项<template v-if="g.can"> · {{ g.can }} 可换</template></span>
              </div>
              <div v-for="it in g.items" :key="it.option" class="magicflow-be-item"
                   :class="{ 'is-disabled': it.disabled }">
                <div class="magicflow-be-item__nm">
                  <span class="magicflow-be-item__amt">{{ amtOf(it, g.kind) }}</span>
                  <span v-if="g.kind !== 'upload'" class="magicflow-be-item__unit">个</span>
                </div>
                <div class="magicflow-be-item__price">
                  {{ fmtNum(it.price) }} <small>{{ r.currency || '魔力' }}</small>
                </div>
                <VBtn v-if="!it.disabled" size="x-small" variant="tonal" color="primary"
                      :loading="acting"
                      @click="emit('act', { siteId: r.site_id, option: it.option, item: it })">
                  兑换
                </VBtn>
                <span v-else class="magicflow-be-item__why" :title="it.disabled_reason">
                  {{ shortWhy(it) }}
                </span>
              </div>
            </div>
          </div>
          <div v-else-if="r.ok" class="magicflow-be-card__empty">该站没有可兑换项</div>
        </div>
      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
.magicflow-be-dialog { background: linear-gradient(165deg, #191a24, #0e0f15); }

/* 统计条（替代解释文案） */
.magicflow-be__sum { display: flex; align-items: center; gap: 9px; padding: 11px 20px;
  border-bottom: 1px solid rgba(255,255,255,.07); background: rgba(139,124,246,.045); }
.magicflow-be__sum-big { font-size: 12.5px; font-weight: 650; white-space: nowrap; }
.magicflow-be__sum-big em { font-style: normal; color: #b6a9ff; }
.magicflow-be__sum-sep { width: 1px; height: 13px; background: rgba(255,255,255,.13); }
.magicflow-be__sum-sub { font-size: 12px; color: rgba(255,255,255,.6); white-space: nowrap; }
.magicflow-be__sum-sub em { font-style: normal; color: #b6a9ff; font-weight: 650; }
.magicflow-be__sum-detail { font-size: 11px; color: rgba(255,255,255,.42); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.magicflow-be__sum-i { margin-left: auto; flex: 0 0 auto; width: 18px; height: 18px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,.16); color: rgba(255,255,255,.5); font-size: 11px;
  display: grid; place-items: center; cursor: help; font-style: italic; }

.magicflow-be__bar { display: flex; align-items: center; gap: 14px; padding: 12px 20px;
  border-bottom: 1px solid rgba(255,255,255,.07); }
.magicflow-be__search { max-width: 260px; }
.magicflow-be__switch { flex: 0 0 auto; }
.magicflow-be__body { padding: 14px 20px 24px; max-height: 62vh; overflow-y: auto; }
.magicflow-be__empty { padding: 32px 0; text-align: center; color: rgba(255,255,255,.45); font-size: 13px; }

.magicflow-be-card { background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.09);
  border-radius: 12px; margin-bottom: 12px; overflow: hidden; }
.magicflow-be-card__head { display: flex; align-items: center; justify-content: space-between;
  gap: 10px; padding: 11px 14px; border-bottom: 1px solid rgba(255,255,255,.06); }
.magicflow-be-card__id { display: flex; align-items: baseline; gap: 8px; min-width: 0; flex-wrap: wrap; }
.magicflow-be-card__nm { font-size: 14px; font-weight: 650; }
.magicflow-be-badge { font-size: 9.5px; font-weight: 650; color: #3ddc97; background: rgba(61,220,151,.12);
  border: 1px solid rgba(61,220,151,.3); border-radius: 20px; padding: 1px 7px; white-space: nowrap; }
.magicflow-be-badge.is-none { color: rgba(255,255,255,.4); background: rgba(255,255,255,.05);
  border-color: rgba(255,255,255,.13); }
.magicflow-be-card__dm { font-size: 11px; color: rgba(255,255,255,.4);
  font-family: ui-monospace, monospace; }
.magicflow-be-card__bal { display: flex; align-items: baseline; gap: 6px; white-space: nowrap; }
.magicflow-be-card__bal strong { font-size: 16px; color: #b6a9ff; font-variant-numeric: tabular-nums; }
.magicflow-be-card__cur { font-size: 11px; color: rgba(255,255,255,.5); }
.magicflow-be-card__err { font-size: 11px; color: #ff8a96; }
.magicflow-be-card__empty { padding: 16px; text-align: center; font-size: 12px; color: rgba(255,255,255,.4); }
.magicflow-be-card__items { padding: 2px 14px 8px; }

/* 类别分组 */
.magicflow-be-group { padding-top: 4px; }
.magicflow-be-group + .magicflow-be-group { border-top: 1px solid rgba(255,255,255,.06); margin-top: 4px; }
.magicflow-be-group__h { display: flex; align-items: baseline; gap: 8px; padding: 7px 0 4px; }
.magicflow-be-group__t { font-size: 11px; font-weight: 650; color: #b6a9ff; letter-spacing: .3px; }
.magicflow-be-group__c { font-size: 10px; color: rgba(255,255,255,.4); }

.magicflow-be-item { display: grid; grid-template-columns: 1fr auto auto; align-items: center;
  gap: 10px; padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,.05); }
.magicflow-be-item:last-child { border-bottom: 0; }
.magicflow-be-item__nm { display: flex; align-items: baseline; gap: 5px; min-width: 0; }
.magicflow-be-item__amt { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums;
  white-space: nowrap; }
.magicflow-be-item__unit { font-size: 10.5px; color: rgba(255,255,255,.45); }
.magicflow-be-item__price { font-size: 12.5px; color: rgba(255,255,255,.66);
  font-variant-numeric: tabular-nums; white-space: nowrap; }
.magicflow-be-item__price small { font-size: 10px; color: rgba(255,255,255,.4); }
.magicflow-be-item__why { font-size: 10.5px; color: rgba(255,255,255,.42); white-space: nowrap;
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);
  border-radius: 7px; padding: 3px 8px; max-width: 96px; overflow: hidden; text-overflow: ellipsis; }
.magicflow-be-item.is-disabled { opacity: .72; }

@media (max-width: 600px) {
  .magicflow-be__sum { flex-wrap: wrap; gap: 7px; padding: 10px 14px; }
  .magicflow-be__sum-detail { flex: 1 1 100%; order: 3; }
  .magicflow-be__bar { flex-wrap: nowrap; gap: 8px; padding: 10px 14px; }
  .magicflow-be__search { max-width: none; flex: 1 1 auto; min-width: 0; }
  .magicflow-be__body { padding: 12px 12px 24px; }
  .magicflow-be-card__id { gap: 6px; }
  .magicflow-be-card__dm { flex: 1 1 100%; }
  .magicflow-be-item { gap: 8px; }
  .magicflow-be-item__why { max-width: 80px; }
}
</style>
