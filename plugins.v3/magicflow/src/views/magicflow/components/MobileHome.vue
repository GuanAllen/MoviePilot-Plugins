<script setup>
import { computed } from 'vue'
// MagicFlow 前端 · 手机端首页（分组任务列表，P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（内层 template + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不直接调父方法。
// 说明：外层容器 `<div class="magicflow-mobile-home">`（含其显隐 scoped 样式）留在父页，本组件只含**内层内容**。
// 不使用 Function prop：点色 / 状态行 / 主数 / 是否多任务等派生展示字段由父在 mobileHomeGroups 里烘焙好下发
// （单一真值源仍在前端域，taskBadge/mobileRowLine/mobileRowNum 不在两处各写一份）。
// props.groups 形状：[{ key, label, count, sites:[{ key, site, attention, dotClass, statusText, multi, taskCount, num, tasks:[{ id, name, dotClass, num }] }] }]
// props.open = 分组展开态（父 mhOpen）；props.openSites = 站点折叠态（父 mhSiteOpen）。
const props = defineProps({
  groups: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
  open: { type: Object, default: () => ({}) },
  openSites: { type: Object, default: () => ({}) },
  liveCount: { type: Number, default: 0 },
  todayGain: { type: Number, default: 0 },
  pages: { type: Array, default: () => [] },
})

const emit = defineEmits([
  'toggle-group',
  'toggle-site',
  'open-task',
  'open-ceiling',
  'open-page',
  'create-task',
  'open-settings',
])

const bonus = computed(() => (Number(props.summary.bonus_per_hour) || 0).toFixed(1))
const ceilingPct = computed(() => Number(props.summary.ceiling_pct || 0))

// 站点行点击：多任务 → 折叠/展开；单任务 → 直接进详情（口径同父 openSiteRow）
function onSiteRow(s) {
  if (s.multi) emit('toggle-site', s.key)
  else emit('open-task', s.tasks[0].id)
}
</script>

<template>
  <div class="mh-hero" role="button" tabindex="0" @click="emit('open-ceiling')">
    <div class="mh-hero__main">
      <div class="mh-hero__v">{{ bonus }}<small>/h</small></div>
      <div class="mh-hero__s">{{ liveCount }} 个魔力站在跑<template v-if="ceilingPct > 0"> · 上限占用 {{ ceilingPct }}%</template><template v-if="todayGain > 0"> · 今日 +{{ todayGain.toFixed(1) }}</template></div>
    </div>
    <VIcon icon="mdi-chevron-right" size="22" class="mh-hero__chev" />
  </div>
  <div v-for="g in groups" :key="g.key" class="mh-group">
    <button type="button" class="mh-group__head" @click="emit('toggle-group', g.key)">
      <span>{{ g.label }}</span>
      <span class="mh-count">{{ g.count }}</span>
      <VIcon :icon="open[g.key] ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="18" />
    </button>
    <div v-show="open[g.key]" class="mh-list">
      <template v-for="s in g.sites" :key="s.key">
        <button
          type="button"
          class="mh-row"
          @click="onSiteRow(s)"
        >
          <span class="mh-dot" :class="s.dotClass" />
          <span class="mh-row__main">
            <span class="mh-row__nm">
              {{ s.site }}
              <span v-if="s.multi" class="mh-row__tag">{{ s.taskCount }} 任务</span>
            </span>
            <span class="mh-row__st" :class="{ 'is-att': s.attention }">{{ s.statusText }}</span>
          </span>
          <span v-if="s.num" class="mh-row__num">{{ s.num }}</span>
          <VIcon
            :icon="s.multi ? (openSites[s.key] ? 'mdi-chevron-up' : 'mdi-chevron-down') : 'mdi-chevron-right'"
            size="18"
            class="mh-row__chev"
          />
        </button>
        <div v-if="s.multi" v-show="openSites[s.key]" class="mh-sublist">
          <button
            v-for="t in s.tasks"
            :key="t.id"
            type="button"
            class="mh-subrow"
            @click="emit('open-task', t.id)"
          >
            <span class="mh-dot" :class="t.dotClass" />
            <span class="mh-row__main"><span class="mh-row__nm">{{ t.name }}</span></span>
            <span v-if="t.num" class="mh-row__num">{{ t.num }}</span>
          </button>
        </div>
      </template>
    </div>
  </div>
  <div class="mh-sect">功能</div>
  <div class="mh-tools">
    <button
      v-for="p in pages"
      :key="p.key"
      type="button"
      class="mh-tool"
      @click="emit('open-page', p)"
    >
      <VIcon :icon="p.icon" size="20" />
      <span>{{ p.label }}<em v-if="p.scope === 'global'" class="mh-tool__scope">全局</em></span>
    </button>
  </div>
  <div class="mh-foot">
    <button type="button" class="mh-btn" @click="emit('create-task')">
      <VIcon icon="mdi-plus" size="18" />新建任务
    </button>
    <button type="button" class="mh-btn mh-btn--ghost" @click="emit('open-settings')">
      <VIcon icon="mdi-tune-variant" size="18" />设置
    </button>
  </div>
</template>

<style scoped>
/* ── ★ 手机端首页（任务列表）内层样式：自 index.vue 的 scoped 块纯搬家 ── */
/* 说明：保留 `.magicflow-page` 祖先前缀（元素在组件内带本组件 data-v，祖先 .magicflow-page 仍可匹配）。 */
.magicflow-page .mh-hero {
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  padding: 18px 18px 16px;
  border-radius: 18px;
  background: linear-gradient(140deg, rgba(var(--v-theme-primary), 0.20), rgba(var(--v-theme-primary), 0.05));
  border: 1px solid rgba(var(--v-theme-primary), 0.30);
}

.magicflow-page .mh-hero__main { min-inline-size: 0; flex: 1 1 auto; }

.magicflow-page .mh-hero__chev { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); flex: 0 0 auto; }

.magicflow-page .mh-hero__v { font-size: 34px; font-weight: 800; letter-spacing: 0.5px; line-height: 1; }

.magicflow-page .mh-hero__v small { font-size: 14px; font-weight: 600; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); margin-inline-start: 4px; }

.magicflow-page .mh-hero__s { margin-block-start: 8px; font-size: 12.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }

.magicflow-page .mh-group { display: flex; flex-direction: column; gap: 8px; margin-block-start: 16px; }

.magicflow-page .mh-group__head {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 6px; background: transparent; border: 0;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); font: inherit; font-size: 12.5px; cursor: pointer;
}

.magicflow-page .mh-group__head .mh-count { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }

.magicflow-page .mh-group__head .v-icon { margin-inline-start: auto; }

.magicflow-page .mh-list { display: flex; flex-direction: column; gap: 8px; }

.magicflow-page .mh-row {
  display: flex; align-items: center; gap: 12px; width: 100%; text-align: start;
  padding: 14px; border-radius: 15px;
  background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: inherit; font: inherit; cursor: pointer;
  transition: background-color 0.15s ease;
}

.magicflow-page .mh-row:active { background: rgba(var(--v-theme-primary), 0.14); }

.magicflow-page .mh-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; background: rgba(var(--v-theme-on-surface), 0.45); }

.magicflow-page .mh-dot.is-primary,
.magicflow-page .mh-dot.is-success { background: rgb(var(--v-theme-primary)); box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.8); }

.magicflow-page .mh-dot.is-error { background: rgb(var(--v-theme-error)); box-shadow: 0 0 8px rgba(var(--v-theme-error), 0.7); }

.magicflow-page .mh-dot.is-warning { background: rgb(var(--v-theme-warning)); box-shadow: 0 0 8px rgba(var(--v-theme-warning), 0.7); }

.magicflow-page .mh-row__main { min-inline-size: 0; flex: 1 1 auto; display: flex; flex-direction: column; gap: 3px; }

.magicflow-page .mh-row__nm { font-size: 14.5px; font-weight: 650; }

.magicflow-page .mh-row__tag {
  margin-inline-start: 7px; font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 7px;
  color: rgb(var(--v-theme-primary)); background: rgba(var(--v-theme-primary), 0.18); vertical-align: 1.5px;
}

.magicflow-page .mh-sublist { margin: 2px 0 6px 14px; border-inline-start: 1px solid rgba(var(--v-border-color), 0.18); padding-inline-start: 10px; }

.magicflow-page .mh-subrow {
  display: flex; align-items: center; gap: 9px; inline-size: 100%; text-align: start; padding: 9px 6px;
  background: none; border: 0; color: inherit; font: inherit; cursor: pointer; border-radius: 10px;
}

.magicflow-page .mh-subrow:active { background: rgba(var(--v-theme-primary), 0.12); }

.magicflow-page .mh-subrow .mh-row__nm { font-size: 13px; font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.82); }

.magicflow-page .mh-subrow .mh-row__num { font-size: 14px; font-weight: 700; color: rgba(var(--v-theme-on-surface), 0.7); }

.magicflow-page .mh-row__st { font-size: 11.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }

.magicflow-page .mh-row__num { font-size: 16px; font-weight: 800; flex: 0 0 auto; }

.magicflow-page .mh-row__chev { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); flex: 0 0 auto; }

.magicflow-page .mh-sect { margin-block-start: 22px; font-size: 11px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); letter-spacing: 0.4px; padding: 0 6px 6px; }

.magicflow-page .mh-tools { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; }

.magicflow-page .mh-tool {
  display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 6px;
  border-radius: 15px; background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); font: inherit; font-size: 12px; cursor: pointer;
}

.magicflow-page .mh-tool:active { background: rgba(var(--v-theme-primary), 0.14); }

.magicflow-page .mh-tool__scope {
  margin-inline-start: 4px;
  padding: 0 4px;
  border-radius: 4px;
  font-style: normal;
  font-size: 10px;
  line-height: 1.5;
  /* 透明度不再叠加：文字色继承 .mh-tool（浅色主题已加深） */
  border: 1px solid currentColor;
}

.magicflow-page .mh-foot { display: flex; gap: 10px; margin-block-start: 22px; }

.magicflow-page .mh-btn {
  flex: 1 1 0; display: flex; align-items: center; justify-content: center; gap: 6px;
  block-size: 46px; border-radius: 14px; border: 0; cursor: pointer;
  font-size: 14px; font-weight: 650; color: rgb(var(--v-theme-on-primary));
  background: linear-gradient(145deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-primary)));
}

.magicflow-page .mh-btn--ghost {
  background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
</style>
