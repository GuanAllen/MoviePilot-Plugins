<script setup>
// MagicFlow 前端 · 豆瓣评分服务弹窗（magicflow-douban · 3.23.1）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（modelValue / state / narrow）、事件向上（emit）；子组件不直接改父状态。
import { fmtTs } from '../../format'

const open = defineModel({ type: Boolean, default: false })

// state = 豆瓣评分服务状态（来自 useDouban）：data / crawl / progress / acting
defineProps({
  state: {
    type: Object,
    default: () => ({ data: {}, crawl: {}, progress: 0, acting: '' }),
  },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['start', 'refresh'])

// 纯格式化：与 index.vue 的 fmtCount 同口径（< 1 万直接显示，否则「x.x 万」）。
function fmtCount(n) {
  const v = Number(n || 0)
  if (v >= 10000) return `${(v / 10000).toFixed(1)} 万`
  return String(v)
}
</script>

<template>
  <VDialog v-model="open" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-douban-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">豆瓣评分服务</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" @click="emit('refresh')">刷新</VBtn>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-douban-dialog__body">
        <div class="magicflow-recommend-dialog__summary">
          <VChip size="small" :color="state.data.ok ? 'success' : 'error'" variant="tonal">
            {{ state.data.ok ? '服务正常' : '服务不可用（回退 TMDB）' }}
          </VChip>
          <i>·</i>
          <span>库 <strong>{{ fmtCount(state.data.records) }}</strong> 条</span>
          <i>·</i>
          <span>缓存 {{ fmtCount(state.data.cache?.total) }} 条 · 负缓存 {{ state.data.cache?.negative || 0 }}</span>
        </div>
        <div class="magicflow-recommend-dialog__note">
          地址：{{ state.data.service || '（未配置）' }}。独立服务 magicflow-douban，本地查询 &lt;1ms，不受豆瓣限流影响。
        </div>

        <VSheet tag="section" class="magicflow-panel app-surface-static mt-2">
          <header class="magicflow-panel__head">
            <div>
              <div class="text-subtitle-2 font-weight-medium">后台数据采集（慢爬）</div>
              <div class="text-body-2 text-medium-emphasis">
                从豆瓣「选电影」接口（一次 20 条带评分）按类型×题材×排序逐步枚举，限速 + 每日上限，进度落库可续跑
              </div>
            </div>
            <VChip
              size="small"
              variant="tonal"
              :color="state.crawl.running ? 'success' : (state.crawl.finished ? 'info' : 'warning')"
            >{{ state.crawl.running ? '采集中' : (state.crawl.finished ? '已完成' : '已暂停') }}</VChip>
          </header>
          <div class="magicflow-douban-crawl">
            <div class="magicflow-douban-crawl__row">
              <span>进度</span>
              <span class="text-medium-emphasis">
                组合 {{ state.crawl.spec_index || 0 }} / {{ state.crawl.spec_total || 0 }}
                <template v-if="state.crawl.finished">· 全部跑完</template>
                <template v-else-if="state.crawl.current">· 当前 {{ state.crawl.current.tags || '（全部）' }} / {{ state.crawl.current.sort }}</template>
              </span>
            </div>
            <VProgressLinear :model-value="state.progress" height="6" rounded color="primary" class="my-2" />
            <div class="magicflow-douban-crawl__grid">
              <span>累计请求 <strong>{{ state.crawl.requests || 0 }}</strong></span>
              <span>今日 <strong>{{ state.crawl.day_requests || 0 }}</strong> / {{ state.crawl.daily_max || '—' }}</span>
              <span>已抓 <strong>{{ fmtCount(state.crawl.items) }}</strong> 条</span>
              <span>新增 <strong>{{ fmtCount(state.crawl.new) }}</strong> 条</span>
              <span>错误 <strong>{{ state.crawl.errors || 0 }}</strong></span>
            </div>
            <div v-if="state.crawl.finished" class="magicflow-douban-crawl__warn magicflow-douban-crawl__warn--ok">
              ✓ 全部 {{ state.crawl.spec_total || 0 }} 个组合已抓完（累计 {{ fmtCount(state.crawl.items) }} 条 / 新增 {{ fmtCount(state.crawl.new) }} 条）。
              豆瓣榜单有变动时，可点「从头重跑」再补一轮。
            </div>
            <div v-if="state.crawl.blocked_for > 0" class="magicflow-douban-crawl__warn">
              ⚠ 触发限流/退避，暂停 {{ state.crawl.blocked_for }} 秒后继续
            </div>
            <div v-else-if="state.crawl.last_error" class="magicflow-douban-crawl__warn">
              最近异常：{{ state.crawl.last_error }}<template v-if="state.crawl.last_error_at"> · {{ fmtTs(state.crawl.last_error_at) }}</template>
            </div>
            <div class="magicflow-douban-crawl__actions">
              <VBtn
                v-if="state.crawl.running"
                size="small" variant="tonal" color="warning" prepend-icon="mdi-pause"
                :loading="state.acting === 'stop'"
                @click="emit('start', 'stop')"
              >暂停采集</VBtn>
              <VBtn
                v-else-if="!state.crawl.finished"
                size="small" variant="tonal" color="success" prepend-icon="mdi-play"
                :loading="state.acting === 'start'"
                @click="emit('start', 'start')"
              >继续采集</VBtn>
              <VBtn
                size="small" :variant="state.crawl.finished ? 'tonal' : 'text'" color="primary" prepend-icon="mdi-restart"
                :loading="state.acting === 'reset'"
                @click="emit('start', 'reset')"
              >从头重跑</VBtn>
            </div>
          </div>
        </VSheet>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行 / 摘要行 / 面板 / 空态：随「豆瓣评分服务弹窗」自 index.vue 迁入。
     下列**共享选择器**（magicflow-dialog / settings-dialog__head / settings-dialog__title /
     recommend-dialog__head-actions / recommend-dialog__summary|note / panel / panel__head /
     table-empty）父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。
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
.magicflow-recommend-dialog__head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.magicflow-recommend-dialog__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  font-size: 0.85rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
.magicflow-recommend-dialog__summary strong {
  font-size: 1.05rem;
  color: rgb(var(--v-theme-primary));
}
.magicflow-recommend-dialog__summary i {
  font-style: normal;
  opacity: var(--mf-op-dim);
}
.magicflow-recommend-dialog__note {
  margin-block: 2px 6px;
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  opacity: 0.85;
}
/* 弹窗标题行 / 摘要行的「·」分隔符在深浅两色下都偏淡（3.39 / 4.39）→ 提到 0.9 */
.magicflow-settings-dialog__head i,
.magicflow-recommend-dialog__summary i {
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.magicflow-panel {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
  min-inline-size: 0;
  padding: 16px;
}
.magicflow-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.magicflow-table-empty {
  padding: 28px 12px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: center;
}

/* ── 豆瓣评分服务（magicflow-douban · 3.23.1）───────────────────── */
.magicflow-douban-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}
.magicflow-douban-dialog__body {
  padding-block: 12px;
  flex: 1 1 auto;
  min-block-size: 0;
  max-block-size: none;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.magicflow-douban-crawl {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 6px;
}
.magicflow-douban-crawl__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.8125rem;
}
.magicflow-douban-crawl__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 6px 12px;
  font-size: 0.8125rem;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.magicflow-douban-crawl__grid strong {
  color: rgb(var(--v-theme-primary));
}
.magicflow-douban-crawl__warn {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.8125rem;
  background: rgba(var(--v-theme-warning), 0.12);
  color: rgb(var(--v-theme-warning));
}
.magicflow-douban-crawl__warn--ok {
  background: rgba(var(--v-theme-success), 0.12);
  color: rgb(var(--v-theme-success));
}
.magicflow-douban-crawl__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

@media (max-width: 699px) {
  .magicflow-panel { padding: 14px; }
  .magicflow-panel__head { flex-wrap: wrap; flex-direction: column; align-items: flex-start; }
}
</style>
