<script setup>
// MagicFlow 前端 · 概览 Tab 的「可观测」面板（本轮决策 + 每小时趋势图）
//
// 为什么单独成组件：这两块在 19.12.x 的 OverviewTab.vue 里写好了，
// 但运行态 index.vue 引用的是从线上 dist 还原的 OverviewTab.js（旧版），
// 于是「可观测① 本轮决策」「可观测② 趋势 sparkline」从来没上过线。
// 这里把两块原样搬出来独立挂载：不改旧组件、不动它的 scoped 样式，
// 风险最小，且图表（趋势折线）直接回到页面上。
//
// 数据向下（props）、不发事件：点「进种子池」等入口留在 OverviewTab 里。
defineProps({
  decision: { type: Object, default: () => ({}) },
  decisionCapText: { type: [String, Number], default: '' },
  decisionReasons: { type: Array, default: () => [] },
  trendCards: { type: Array, default: () => [] },
})
</script>

<template>
  <!-- ★ 可观测①：本轮决策轨迹（回答「为什么这轮没删 / 没换 / 删了什么」） -->
  <VSheet v-if="decision.at_cap !== undefined" tag="section" class="magicflow-panel app-surface-static mf-obs">
    <header class="mf-obs__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">本轮决策</div>
        <div class="text-body-2 text-medium-emphasis">为什么这么做 · 最近一轮闸门判定与淘汰口径</div>
      </div>
      <VChip :color="decision.at_cap ? 'warning' : 'success'" size="small" variant="tonal">
        {{ decision.at_cap ? '已达上限 · 可换种' : '未达上限 · 不做低效换种' }}
      </VChip>
    </header>
    <div class="mf-obs__rows">
      <div class="mf-obs__row">
        <span>闸门</span>
        <strong>{{ decisionCapText }}</strong>
      </div>
      <div class="mf-obs__row">
        <span>淘汰口径</span>
        <strong>
          候选 {{ decision.candidates ?? '—' }} → 受保护 {{ decision.protected ?? '—' }} →
          保留 {{ decision.keep ?? '—' }} → 待删 {{ decision.to_delete ?? '—' }} → 实删 {{ decision.deleted ?? '—' }}
        </strong>
      </div>
      <div class="mf-obs__row">
        <span>门槛 / 保护</span>
        <strong>
          低效门槛 {{ decision.threshold ?? '—' }}/h · 保护阈值
          {{ decision.protect_threshold ?? '∞' }} · 保留上限 {{ decision.max_keep ?? '—' }} 个 ·
          零魔淘汰 {{ decision.zero_bonus_delete ? '开' : '关' }}
        </strong>
      </div>
      <div v-if="decisionReasons.length" class="mf-obs__row">
        <span>删除原因</span>
        <div class="mf-obs__chips">
          <VChip v-for="r in decisionReasons" :key="r.label" size="x-small" variant="tonal" color="error">
            {{ r.label }} ×{{ r.count }}
          </VChip>
        </div>
      </div>
    </div>
  </VSheet>

  <!-- ★ 可观测②：每小时趋势 sparkline（时魔 / 做种数 / 自身体积 / 辅种体积） -->
  <VSheet v-if="trendCards.length" tag="section" class="magicflow-panel app-surface-static mf-obs">
    <header class="mf-obs__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">趋势</div>
        <div class="text-body-2 text-medium-emphasis">每小时采样 · 最近 72 小时（本地序列）</div>
      </div>
    </header>
    <div class="mf-spark-grid">
      <div v-for="c in trendCards" :key="c.key" class="mf-spark">
        <div class="mf-spark__head">
          <span>{{ c.label }}</span>
          <strong>
            {{ Number(c.s.last).toFixed(c.key === 'seeds' ? 0 : 2) }}{{ c.unit }}
            <em :class="c.s.good ? 'is-up' : 'is-down'">
              {{ c.s.delta >= 0 ? '▲' : '▼' }}{{ Math.abs(c.s.delta).toFixed(1) }}%
            </em>
          </strong>
        </div>
        <svg class="mf-spark__svg" viewBox="0 0 100 26" preserveAspectRatio="none">
          <path :d="c.s.path" fill="none" :class="`mf-spark__line mf-spark__line--${c.color}`" vector-effect="non-scaling-stroke" />
        </svg>
        <div class="mf-spark__foot">
          <span>{{ c.s.count }} 点</span>
          <span>低 {{ Number(c.s.min).toFixed(1) }} · 高 {{ Number(c.s.max).toFixed(1) }}</span>
        </div>
      </div>
    </div>
  </VSheet>
</template>

<style scoped>
/* ── 共享选择器（index.vue / 兄弟 tab 同有；父页是 scoped，样式不穿透子组件，
      组件内必须自带一份，否则面板没有内边距 / 圆角 / 边框）────────────── */
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

/* 深色磨砂主题覆盖（与概览其它面板一致；变量定义在祖先 .magicflow-page 上） */
.magicflow-page .magicflow-panel {
  padding: 18px 16px;
  background: var(--magicflow-panel-bg) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 16px;
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(var(--v-theme-on-surface), 0.04);
}

/* 面板标题排版：14px/600 + 11px 说明（同概览其它面板） */
.magicflow-panel .text-subtitle-1 {
  font-size: 14px;
  font-weight: 600;
}

.magicflow-panel .text-body-2 {
  font-size: 11px;
}

/* 面板之间 12px，末块留 12px 与下方「磁贴 / 运行状态」分隔；
   首块不留上边距（.magicflow-window 已有 padding-block-start:16px，否则会出现双倍留白） */
.mf-obs {
  margin-block: 0 12px;
}

.mf-obs__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-block-end: 10px;
}

.mf-obs__rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mf-obs__row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
}

.mf-obs__row > span {
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.mf-obs__row > strong {
  font-weight: 500;
  word-break: break-word;
}

.mf-obs__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.mf-spark-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.mf-spark__head {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.65);
}

.mf-spark__head strong {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}

.mf-spark__head em {
  font-style: normal;
  font-size: 11px;
  margin-inline-start: 4px;
}

.mf-spark__head em.is-up { color: rgb(var(--v-theme-success)); }
.mf-spark__head em.is-down { color: rgb(var(--v-theme-error)); }

.mf-spark__svg {
  display: block;
  inline-size: 100%;
  block-size: 26px;
  margin-block: 4px;
}

.mf-spark__line { stroke-width: 1.5; }
.mf-spark__line--primary { stroke: rgb(var(--v-theme-primary)); }
.mf-spark__line--info { stroke: rgb(var(--v-theme-info)); }
.mf-spark__line--secondary { stroke: rgb(var(--v-theme-secondary)); }
.mf-spark__line--success { stroke: rgb(var(--v-theme-success)); }

.mf-spark__foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

/* 与概览其它面板同步的窄屏收缩 */
@media (max-width: 699px) {
  .magicflow-page .magicflow-panel,
  .magicflow-panel {
    padding: 14px;
  }

  .mf-obs__head {
    flex-direction: column;
    align-items: flex-start;
  }

  /* 窄屏改「标签在上、值在下」，避免 88px 标签列把值挤成竖排 */
  .mf-obs__row {
    grid-template-columns: 1fr;
    gap: 2px;
  }
}

@media (max-width: 419px) {
  .mf-spark-grid {
    grid-template-columns: 1fr;
  }
}
</style>
