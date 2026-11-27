<script setup>
// MagicFlow 前端 · 魔力兑换看板（★ 19.16.34：桌面主从布局 / 手机保持单列）
// 只读看板：各站当前魔力 + 三类兑换项；兑换走 emit('act') 交父页二次确认。
// 数据向下（props）、事件向上（emit）；子组件不直接发写请求。
//
// ★ 19.16.34 桌面布局（对齐设计稿）：
//   桌面（!narrow）：左侧站点清单网格（快照 site_list，打开零请求）+ 右侧选中站实时详情表格。
//   手机（narrow）：保持 19.16.33 的 VSelect 下拉 + 单列卡片，不动。
//   两种口径分开标注、不许抹平：左栏角标来自快照、右栏明细来自实时抓取。
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
// ★ 19.16.33：只抓当前选中的一站 —— 打开只读清单快照（零站点请求），选中哪站才请求哪站。
//   站点选择由父页持有（v-model:site），切换即触发一次 ?site_id=N。
const site = defineModel('site', { type: [Number, String], default: null })
const siteList = computed(() => (props.data && props.data.site_list) || [])
const hasPick = computed(() => !(site.value === null || site.value === undefined || site.value === ''))
const siteItems = computed(() => siteList.value.map(s => {
  const tail = !s.cached ? '未抓取' : (s.ok ? (s.exchangeable ? `可换 ${s.exchangeable}` : '全禁') : '抓取失败')
  return { title: `${s.site_name || s.site_id} · ${tail}`, value: s.site_id }
}))
const filtered = computed(() => {
  if (!hasPick.value) return rows.value
  return rows.value.filter(r => r.site_id === site.value)
})
const onlyOk = ref(false)
const shown = computed(() => onlyOk.value
  ? filtered.value.filter(r => r.ok && (r.items || []).some(i => !i.disabled))
  : filtered.value)
// 空态说实话：区分「没选站 / 选了失败站 / 该站全禁 / 没有可换项」
const emptyText = computed(() => {
  if (!hasPick.value) return '选择站点查看可兑换项'
  if (!rows.value.length) return '暂无数据'
  const r = rows.value.find(x => x.site_id === site.value)
  if (r && !r.ok) return '该站抓取失败，原因见站点卡'
  return onlyOk.value ? '该站当前没有可换项' : '该站没有兑换项'
})

// ★ 19.16.34 桌面左栏：站点清单来自快照 site_list（零请求），按可换降序。
const railSites = computed(() => [...siteList.value].sort((a, b) =>
  (b.exchangeable || 0) - (a.exchangeable || 0) ||
  String(a.site_name || '').localeCompare(String(b.site_name || ''))))
const railShown = computed(() => onlyOk.value
  ? railSites.value.filter(s => s.ok && (s.exchangeable || 0) > 0)
  : railSites.value)
// 快照口径（左栏角标相加）vs 实时口径（右栏 totals）——分别显示，不强行抹平。
const snapCan = computed(() => siteList.value.reduce((a, s) => a + (s.exchangeable || 0), 0))
const snapOk = computed(() => siteList.value.filter(s => s.ok).length)
// 桌面右栏只显示当前选中站（单站抓取，rows 最多一站）。
const detail = computed(() => shown.value[0] || null)

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
function amtParts(it, kind) {
  if (kind === 'upload') {
    const s = fmtSize(it.size_gb)
    const i = s.indexOf(' ')
    return i < 0 ? { v: s, u: '' } : { v: s.slice(0, i), u: s.slice(i + 1) }
  }
  return { v: String(it.count || 1), u: '个' }
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
function snapTail(s) {
  if (!s.cached) return '未抓取'
  if (!s.ok) return '抓取失败'
  return s.exchangeable ? '可换 ' + s.exchangeable : '全禁'
}
function doAct(r, it) {
  emit('act', { siteId: r.site_id, option: it.option, item: it })
}
</script>

<template>
  <VDialog v-model="open" :max-width="narrow ? undefined : '68rem'" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-be-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">魔力兑换</span>
        <VSpacer />
        <VBtn icon="mdi-refresh" size="small" variant="text" :loading="loading"
              aria-label="刷新看板" @click="emit('refresh')" />
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>

      <!-- 桌面统计条：快照口径（清单）与实时口径（选中站）分开标注，不抹平 -->
      <div v-if="!narrow" class="magicflow-be__sum">
        <span class="magicflow-be__sum-big"><em>{{ snapOk }}</em> 站已取到</span>
        <span class="magicflow-be__sum-sep"></span>
        <span class="magicflow-be__sum-sub">清单可换 <em>{{ snapCan }}</em>（快照）</span>
        <span class="magicflow-be__sum-detail">
          <template v-if="hasPick">当前站可换 {{ totals.exchangeable ?? 0 }} = 上传 {{ canKind('upload') }} · 邀请 {{ canKind('invite') }} · 临时 {{ canKind('temp_invite') }}（实时）</template>
          <template v-else>选中哪站才抓哪站（10 分钟内复用缓存）</template>
        </span>
        <span class="magicflow-be__sum-i"
              title="清单角标来自上次抓取快照（打开弹窗零请求）；右侧详情为选中站实时抓取。两者因站点页面变化会短暂不同，刷新当前站后趋同。灰色=站点判定不可换（分享率已很高 / 余额不足 / 等级不足）。点兑换需二次确认，提交前会重抓页面核对。规则详见 wiki。">i</span>
      </div>
      <!-- 手机统计条：保持 19.16.33 原样 -->
      <div v-else-if="!hasPick" class="magicflow-be__sum">
        <span class="magicflow-be__sum-big"><em>{{ siteList.length }}</em> 站可选</span>
        <span class="magicflow-be__sum-sep"></span>
        <span class="magicflow-be__sum-sub">选中哪站才抓哪站（10 分钟内复用缓存）</span>
        <span class="magicflow-be__sum-i"
              title="不再打开就逐站拉取。清单里的站点状态来自上次抓取；点刷新只重抓当前选中站。">i</span>
      </div>
      <div v-else class="magicflow-be__sum">
        <span class="magicflow-be__sum-big"><em>{{ totals.ok ?? '—' }}</em> 站已取到</span>
        <span class="magicflow-be__sum-sep"></span>
        <span class="magicflow-be__sum-sub"><em>{{ totals.exchangeable ?? 0 }}</em> 项可换</span>
        <span class="magicflow-be__sum-detail">
          上传 {{ canKind('upload') }} · 邀请 {{ canKind('invite') }} · 临时 {{ canKind('temp_invite') }}
        </span>
        <span class="magicflow-be__sum-i"
              title="可换上传量 / 邀请名额 / 临时邀请。灰色=站点判定不可换（分享率已很高 / 余额不足 / 等级不足）。点兑换需二次确认，提交前会重抓页面核对。规则详见 wiki。">i</span>
      </div>

      <!-- ══════════ 桌面：主从布局（左站点清单 + 右实时详情） ══════════ -->
      <div v-if="!narrow" class="magicflow-be__desk">
        <aside class="magicflow-be__rail">
          <div class="magicflow-be__rail-top">
            <span>站点 <b>{{ siteList.length }}</b> · 快照清单（零请求）</span>
            <label class="magicflow-be__sw">
              <input type="checkbox" v-model="onlyOk" />
              <span class="magicflow-be__sw-track"></span>只看可换
            </label>
          </div>
          <div class="magicflow-be__rail-list">
            <div v-for="s in railShown" :key="s.site_id"
                 class="magicflow-be-rk"
                 :class="{ 'is-on': site === s.site_id, 'is-fail': !s.ok }"
                 @click="site = s.site_id">
              <div class="magicflow-be-rk__t">
                <span class="magicflow-be-rk__nm">{{ s.site_name || s.site_id }}</span>
                <span class="magicflow-be-rk__badge" :class="{ 'is-none': !s.exchangeable }">
                  {{ s.exchangeable ? '可换 ' + s.exchangeable : '无可换' }}
                </span>
              </div>
              <div class="magicflow-be-rk__m">
                <span class="magicflow-be-rk__dm">{{ shortDomain(s.domain) }}</span>
                <span class="magicflow-be-rk__bal">{{ fmtNum(s.balance) }} <i>{{ s.currency || '魔力' }}</i></span>
              </div>
              <div class="magicflow-be-rk__s">· {{ snapTail(s) }}</div>
            </div>
            <div v-if="!railShown.length" class="magicflow-be__rail-empty">没有符合的站点</div>
          </div>
        </aside>

        <div class="magicflow-be__detail">
          <template v-if="detail">
            <div class="magicflow-be__dt-head">
              <div class="magicflow-be__dt-id">
                <h3>{{ detail.site_name }}</h3>
                <span class="magicflow-be-badge" :class="{ 'is-none': canOf(detail) === 0 }">
                  {{ canOf(detail) ? '可换 ' + canOf(detail) : '无可换' }}
                </span>
                <span class="magicflow-be-card__dm">{{ shortDomain(detail.domain) }}</span>
                <span class="magicflow-be__live">实时</span>
              </div>
              <div class="magicflow-be-card__bal">
                <strong>{{ fmtNum(detail.balance) }}</strong>
                <span class="magicflow-be-card__cur">{{ detail.currency || '魔力' }}</span>
              </div>
            </div>
            <div class="magicflow-be__dt-meta">
              <span>本页 {{ (detail.items || []).length }} 项 · {{ canOf(detail) }} 可换</span>
              <span>选中站才抓 · 10 分钟缓存</span>
            </div>
            <div v-if="!detail.ok" class="magicflow-be-card__err" :title="detail.why">
              该站抓取失败：{{ detail.why || '未知原因' }}
            </div>
            <template v-else>
              <div v-for="g in groupsOf(detail)" :key="g.kind" class="magicflow-be-group">
                <div class="magicflow-be-group__h">
                  <span class="magicflow-be-group__t">{{ g.label }}</span>
                  <span class="magicflow-be-group__c">{{ g.total }} 项<template v-if="g.can"> · {{ g.can }} 可换</template></span>
                </div>
                <div class="magicflow-be-tbl">
                  <div class="magicflow-be-tbl-th"><span>项目</span><span>价格</span><span>操作</span></div>
                  <div v-for="it in g.items" :key="it.option" class="magicflow-be-tr"
                       :class="{ 'is-disabled': it.disabled }">
                    <span class="magicflow-be-tr__amt">
                      {{ amtParts(it, g.kind).v }}<i>{{ amtParts(it, g.kind).u }}</i>
                    </span>
                    <span class="magicflow-be-tr__price">{{ fmtNum(it.price) }} <i>{{ detail.currency || '魔力' }}</i></span>
                    <span class="magicflow-be-tr__act">
                      <button v-if="!it.disabled" type="button" class="magicflow-be__go"
                              :disabled="acting" @click="doAct(detail, it)">
                        {{ acting ? '处理中' : '兑换' }}
                      </button>
                      <span v-else class="magicflow-be-item__why" :title="it.disabled_reason">{{ shortWhy(it) }}</span>
                    </span>
                  </div>
                </div>
              </div>
              <div v-if="!(detail.items || []).length" class="magicflow-be__dt-empty">该站没有可兑换项</div>
            </template>
          </template>
          <div v-else class="magicflow-be__dt-empty">{{ loading ? '正在抓取该站页面…' : emptyText }}</div>
        </div>
      </div>

      <!-- ══════════ 手机：保持 19.16.33 的单列下拉 + 卡片 ══════════ -->
      <template v-else>
        <div class="magicflow-be__bar">
          <VSelect v-model="site" :items="siteItems" item-title="title" item-value="value"
                   density="compact" variant="outlined" hide-details clearable
                   prepend-inner-icon="mdi-format-list-bulleted" placeholder="选择站点"
                   class="magicflow-be__search" />
          <VSwitch v-if="hasPick" v-model="onlyOk" density="compact" hide-details inset color="primary"
                   label="只看可换" class="magicflow-be__switch" />
        </div>

        <div class="magicflow-be__body">
          <div v-if="loading && !rows.length" class="magicflow-be__empty">正在抓取该站页面…</div>
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
      </template>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 共享选择器（父页其它弹窗也在用）→ 两处各留一份（纯复制，零改动）。
     ⚠️ VDialog 会 teleport 到 body，父页 scoped 规则不再命中 → 组件必须自带这些。── */
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
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
}
.magicflow-settings-dialog__title {
  font-size: 1.05rem;
  font-weight: 600;
}

/* 本弹窗沿用 19.16.29 的深色渐变底：放在共享块之后 + !important 覆盖共享背景 */
.magicflow-be-dialog { background: linear-gradient(165deg, #191a24, #0e0f15) !important; }

/* 统计条（替代解释文案） */
.magicflow-be__sum { display: flex; align-items: center; gap: 9px; padding: 8px 18px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), .07); background: rgba(139,124,246,.045); }
.magicflow-be__sum-big { font-size: 12.5px; font-weight: 650; white-space: nowrap; }
.magicflow-be__sum-big em { font-style: normal; color: #b6a9ff; }
.magicflow-be__sum-sep { width: 1px; height: 13px; background: rgba(var(--v-theme-on-surface), .13); }
.magicflow-be__sum-sub { font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); white-space: nowrap; }
.magicflow-be__sum-sub em { font-style: normal; color: #b6a9ff; font-weight: 650; }
.magicflow-be__sum-detail { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.magicflow-be__sum-i { margin-left: auto; flex: 0 0 auto; width: 18px; height: 18px; border-radius: 50%;
  border: 1px solid rgba(var(--v-theme-on-surface), .16); color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); font-size: 11px;
  display: grid; place-items: center; cursor: help; font-style: italic; }

.magicflow-be__bar { display: flex; align-items: center; gap: 10px; padding: 8px 18px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), .07); }
.magicflow-be__search { max-width: 260px; }
.magicflow-be__switch { flex: 0 0 auto; }
.magicflow-be__body { padding: 6px 18px 20px; max-height: 62vh; overflow-y: auto; }
.magicflow-be__empty { padding: 32px 0; text-align: center; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); font-size: 13px; }

.magicflow-be-card { background: rgba(var(--v-theme-on-surface), .035); border: 1px solid rgba(var(--v-theme-on-surface), .09);
  border-radius: 12px; margin-bottom: 12px; overflow: hidden; }
.magicflow-be-card__head { display: flex; align-items: center; justify-content: space-between;
  gap: 10px; padding: 10px 12px; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .06); }
.magicflow-be-card__id { display: flex; align-items: baseline; gap: 8px; min-width: 0; flex-wrap: wrap; }
.magicflow-be-card__nm { font-size: 14px; font-weight: 650; }
.magicflow-be-badge { font-size: 9.5px; font-weight: 650; color: #3ddc97; background: rgba(61,220,151,.12);
  border: 1px solid rgba(61,220,151,.3); border-radius: 20px; padding: 1px 7px; white-space: nowrap; }
.magicflow-be-badge.is-none { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); background: rgba(var(--v-theme-on-surface), .05);
  border-color: rgba(var(--v-theme-on-surface), .13); }
.magicflow-be-card__dm { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim));
  font-family: ui-monospace, monospace; }
.magicflow-be-card__bal { display: flex; align-items: baseline; gap: 6px; white-space: nowrap; }
.magicflow-be-card__bal strong { font-size: 16px; color: #b6a9ff; font-variant-numeric: tabular-nums; }
.magicflow-be-card__cur { font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-be-card__err { font-size: 11px; color: #ff8a96; }
.magicflow-be-card__empty { padding: 16px; text-align: center; font-size: 12px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-be-card__items { padding: 2px 12px 8px; }

/* 类别分组 */
.magicflow-be-group { padding-top: 4px; }
.magicflow-be-group + .magicflow-be-group { border-top: 1px solid rgba(var(--v-theme-on-surface), .06); margin-top: 4px; }
.magicflow-be-group__h { display: flex; align-items: baseline; gap: 8px; padding: 6px 0 4px; }
.magicflow-be-group__t { font-size: 11px; font-weight: 650; color: #b6a9ff; letter-spacing: .3px; }
.magicflow-be-group__c { font-size: 10px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }

.magicflow-be-item { display: grid; grid-template-columns: 1fr auto auto; align-items: center;
  gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .05); }
.magicflow-be-item:last-child { border-bottom: 0; }
.magicflow-be-item__nm { display: flex; align-items: baseline; gap: 5px; min-width: 0; }
.magicflow-be-item__amt { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums;
  white-space: nowrap; }
.magicflow-be-item__unit { font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-be-item__price { font-size: 12.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
  font-variant-numeric: tabular-nums; white-space: nowrap; }
.magicflow-be-item__price small { font-size: 10px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-be-item__why { font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); white-space: nowrap;
  background: rgba(var(--v-theme-on-surface), .05); border: 1px solid rgba(var(--v-theme-on-surface), .1);
  border-radius: 7px; padding: 3px 8px; max-width: 96px; overflow: hidden; text-overflow: ellipsis; }
.magicflow-be-item.is-disabled { opacity: .72; }

/* ══════════ 19.16.34 桌面主从布局 ══════════ */
.magicflow-be__desk { display: grid; grid-template-columns: 246px minmax(0, 1fr);
  height: 560px; border-top: 1px solid rgba(var(--v-theme-on-surface), .07); }
.magicflow-be__rail { border-right: 1px solid rgba(var(--v-theme-on-surface), .07); background: rgba(0,0,0,.15);
  display: flex; flex-direction: column; min-height: 0; }
.magicflow-be__rail-top { display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 13px; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .07);
  font-size: 11.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-be__rail-top b { color: #b6a9ff; }
.magicflow-be__sw { display: inline-flex; align-items: center; gap: 6px; font-size: 11px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); cursor: pointer; white-space: nowrap; user-select: none; }
.magicflow-be__sw input { position: absolute; opacity: 0; width: 0; height: 0; }
.magicflow-be__sw-track { width: 24px; height: 14px; border-radius: 20px;
  background: rgba(var(--v-theme-on-surface), .12); position: relative; transition: background .18s; flex: 0 0 auto; }
.magicflow-be__sw-track::after { content: ""; position: absolute; left: 2px; top: 2px;
  width: 10px; height: 10px; border-radius: 50%; background: #c8c9d4;
  transition: transform .18s, background .18s; }
.magicflow-be__sw input:checked + .magicflow-be__sw-track { background: #8b7cf6; }
.magicflow-be__sw input:checked + .magicflow-be__sw-track::after { transform: translateX(10px); background: #fff; }
.magicflow-be__rail-list { overflow-y: auto; flex: 1; }
.magicflow-be__rail-empty { padding: 24px 12px; text-align: center; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-be-rk { position: relative; padding: 8px 12px 8px 14px; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .06);
  cursor: pointer; transition: background .15s; }
.magicflow-be-rk:hover { background: rgba(var(--v-theme-on-surface), .04); }
.magicflow-be-rk.is-on { background: rgba(139,124,246,.14); }
.magicflow-be-rk.is-on::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0;
  width: 3px; background: #8b7cf6; }
.magicflow-be-rk.is-fail { opacity: .6; }
.magicflow-be-rk__t { display: flex; align-items: center; justify-content: space-between; gap: 5px; }
.magicflow-be-rk__nm { font-size: 12.5px; font-weight: 600; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.magicflow-be-rk__badge { font-size: 9.5px; font-weight: 650; color: #3ddc97;
  background: rgba(61,220,151,.12); border: 1px solid rgba(61,220,151,.3);
  border-radius: 20px; padding: 1px 6px; white-space: nowrap; }
.magicflow-be-rk__badge.is-none { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); background: rgba(var(--v-theme-on-surface), .05);
  border-color: rgba(var(--v-theme-on-surface), .13); }
.magicflow-be-rk__m { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; margin-top: 3px; }
.magicflow-be-rk__dm { font-size: 10px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); font-family: ui-monospace, monospace;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-be-rk__bal { font-size: 10.5px; color: #b6a9ff; font-variant-numeric: tabular-nums; white-space: nowrap; }
.magicflow-be-rk__bal i { font-style: normal; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); font-size: 9.5px; }
.magicflow-be-rk__s { font-size: 9px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); margin-top: 2px; }

.magicflow-be__detail { overflow-y: auto; padding: 14px 18px 22px; min-width: 0; }
.magicflow-be__dt-empty { padding: 56px 0; text-align: center; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); font-size: 12.5px; }
.magicflow-be__dt-head { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding-bottom: 10px; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .13); }
.magicflow-be__dt-id { display: flex; align-items: center; gap: 9px; min-width: 0; flex-wrap: wrap; }
.magicflow-be__dt-id h3 { font-size: 16px; font-weight: 700; white-space: nowrap; margin: 0; }
.magicflow-be__live { font-size: 9px; color: #3ddc97; background: rgba(61,220,151,.12);
  border: 1px solid rgba(61,220,151,.3); border-radius: 6px; padding: 1px 6px; }
.magicflow-be__dt-meta { display: flex; align-items: center; justify-content: space-between;
  font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); padding: 7px 0 2px; }
.magicflow-be__dt-meta span:last-child { font-size: 9.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }

.magicflow-be-tbl { border: 1px solid rgba(var(--v-theme-on-surface), .07); border-radius: 9px; overflow: hidden; }
.magicflow-be-tbl-th, .magicflow-be-tr { display: grid; grid-template-columns: minmax(0,1fr) 150px 108px;
  align-items: center; gap: 10px; padding: 8px 13px; }
.magicflow-be-tbl-th { background: rgba(var(--v-theme-on-surface), .03); font-size: 10px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-be-tbl-th span:last-child { text-align: right; }
.magicflow-be-tr { border-top: 1px solid rgba(var(--v-theme-on-surface), .05); font-size: 12.5px; }
.magicflow-be-tr.is-disabled { opacity: .6; }
.magicflow-be-tr__amt { font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.magicflow-be-tr__amt i { font-style: normal; font-size: 10.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); font-weight: 400; }
.magicflow-be-tr__price { color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); font-variant-numeric: tabular-nums; white-space: nowrap; }
.magicflow-be-tr__price i { font-style: normal; font-size: 10px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-be-tr__act { display: flex; justify-content: flex-end; }
.magicflow-be__go { font-size: 11.5px; color: rgb(var(--v-theme-on-surface));
  background: rgba(139,124,246,.14); border: 1px solid rgba(139,124,246,.32);
  border-radius: 7px; padding: 4px 13px; cursor: pointer; }
.magicflow-be__go:disabled { opacity: .6; cursor: default; }

@media (max-width: 600px) {
  .magicflow-be__sum { flex-wrap: wrap; gap: 7px; padding: 8px 14px; }
  .magicflow-be__sum-detail { flex: 1 1 100%; order: 3; }
  .magicflow-be__bar { flex-wrap: nowrap; gap: 8px; padding: 8px 14px; }
  .magicflow-be__search { max-width: none; flex: 1 1 auto; min-width: 0; }
  .magicflow-be__body { padding: 4px 14px 18px; }
  .magicflow-be-card__id { gap: 6px; }
  .magicflow-be-card__dm { flex: 1 1 100%; }
  .magicflow-be-item { gap: 8px; }
  .magicflow-be-item__why { max-width: 80px; }
}
</style>
