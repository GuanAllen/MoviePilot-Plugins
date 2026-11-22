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
//
// ★ 19.13.2 设计落地（手机端首页重设计 v3）：
//   1. 删「功能九宫格」——与顶部「功能中心」弹层同出自 MF_PAGES（九宫格只是过滤子集），重复入口收口。
//      pages prop / open-page emit 保留定义（index.vue 本版不动），仅不再渲染九宫格。
//   2. 分组头显示「N 站 · M 任务」——站点数用 sites.length（口径同 hero 的 liveCount），任务数仍是 g.count。
//   3. 列表「一站一卡」改为单容器 + 细分割线；多任务子列表缩进。
//   4. 站点状态色点改字母徽标（首字），保留 is-* 状态色语义。
//   5. hero 右侧补「看详情」文字（chevron 保留）。
//   宿主的顶栏 / 磁吸底栏不属插件渲染范围，本版不动（仅给内容末尾留底部安全区）。
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

// 站点徽标首字：中文/英文/emoji 都取第一个字素，空值回退「·」
function initial(name) {
  const s = String(name || '').trim()
  return s ? Array.from(s)[0].toUpperCase() : '·'
}

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
    <span class="mh-hero__go">看详情</span>
    <VIcon icon="mdi-chevron-right" size="22" class="mh-hero__chev" />
  </div>
  <div v-for="g in groups" :key="g.key" class="mh-group">
    <button type="button" class="mh-group__head" @click="emit('toggle-group', g.key)">
      <span>{{ g.label }}</span>
      <span class="mh-group__hint">{{ g.key === 'need' ? '有问题或待决策' : (g.key === 'live' ? '正常运行中' : '已停用 / 内置托管') }}</span>
      <span v-if="g.key === 'live'" class="mh-count mh-count--site">{{ g.sites.length }} 站</span>
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
          <span class="mh-badge" :class="s.dotClass">{{ initial(s.site) }}</span>
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
  <!-- ★ 19.13.2：功能九宫格已移除——与「功能中心」弹层同出自 MF_PAGES（九宫格只是过滤子集），
       同一批入口摆两遍是冗余；功能统一收口到 WorkbenchHeader 的「功能中心」按钮。
       pages prop / open-page emit 保留（index.vue 本版不动），仅此处不再渲染。 -->
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

.magicflow-page .mh-hero__go { font-size: 12px; font-weight: 600; color: rgb(var(--v-theme-primary)); flex: 0 0 auto; }

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

.magicflow-page .mh-group__hint { font-size: 11px; font-weight: 400; color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-page .mh-group__head .mh-count { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); }
.magicflow-page .mh-group__head .mh-count--site { color: rgb(var(--v-theme-primary)); font-weight: 700; }
.magicflow-page .mh-group__head .v-icon { margin-inline-start: auto; }

/* 19.13.2：单容器 + 细分割线（原为一站一卡，gap 8px 的独立圆角卡） */
.magicflow-page .mh-list {
  display: flex; flex-direction: column;
  background: rgba(var(--v-theme-surface), 0.9);
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 15px;
  overflow: hidden;
}

.magicflow-page .mh-row {
  display: flex; align-items: center; gap: 12px; width: 100%; text-align: start;
  padding: 13px 14px; border-radius: 0;
  background: transparent; border: 0; border-bottom: 1px solid var(--magicflow-panel-brd);
  color: inherit; font: inherit; cursor: pointer;
  transition: background-color 0.15s ease;
}
.magicflow-page .mh-list > .mh-row:last-child { border-bottom: 0; }
.magicflow-page .mh-row:active { background: rgba(var(--v-theme-primary), 0.14); }

/* 19.13.2：站点字母徽标（替代原 9px 状态点），保留 is-* 状态色语义 */
.magicflow-page .mh-badge {
  width: 36px; height: 36px; flex: 0 0 36px; border-radius: 11px;
  display: grid; place-items: center;
  font-size: 14px; font-weight: 800; letter-spacing: -0.02em;
  background: rgba(var(--v-theme-on-surface), 0.12);
  color: rgb(var(--v-theme-on-surface));
}
.magicflow-page .mh-badge.is-primary,
.magicflow-page .mh-badge.is-success { background: rgb(var(--v-theme-primary)); color: rgb(var(--v-theme-on-primary)); }
.magicflow-page .mh-badge.is-error { background: rgb(var(--v-theme-error)); color: #fff; }
.magicflow-page .mh-badge.is-warning { background: rgb(var(--v-theme-warning)); color: #fff; }

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

.magicflow-page .mh-sublist { margin: 2px 0 6px 50px; border-inline-start: 1px solid rgba(var(--v-border-color), 0.18); padding-inline-start: 10px; }

.magicflow-page .mh-subrow {
  display: flex; align-items: center; gap: 9px; inline-size: 100%; text-align: start; padding: 9px 6px;
  background: none; border: 0; color: inherit; font: inherit; cursor: pointer; border-radius: 10px;
}
.magicflow-page .mh-subrow:active { background: rgba(var(--v-theme-primary), 0.12); }
.magicflow-page .mh-subrow .mh-row__nm { font-size: 13px; font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.82); }
.magicflow-page .mh-subrow .mh-row__num { font-size: 14px; font-weight: 700; color: rgba(var(--v-theme-on-surface), 0.7); }

.magicflow-page .mh-row__st { font-size: 11.5px; color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid)); }
.magicflow-page .mh-row__st.is-att { color: rgb(var(--v-theme-error)); }
.magicflow-page .mh-row__num { font-size: 16px; font-weight: 800; flex: 0 0 auto; }
.magicflow-page .mh-row__chev { color: rgba(var(--v-theme-on-surface), var(--mf-fg-dim)); flex: 0 0 auto; }

.magicflow-page .mh-foot { display: flex; gap: 10px; margin-block-start: 22px; margin-block-end: 24px; }

.magicflow-page .mh-btn {
  flex: 1 1 0; display: flex; align-items: center; justify-content: center; gap: 6px;
  block-size: 46px; border-radius: 14px; border: 0; cursor: pointer;
  font-size: 14px; font-weight: 650; color: rgb(var(--v-theme-on-primary));
  background: linear-gradient(145deg, #8D51F9 0%, #7432DF 55%, #5B00C5 100%);
}

.magicflow-page .mh-btn--ghost {
  background: rgba(var(--v-theme-surface), 0.9); border: 1px solid var(--magicflow-panel-brd);
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
}
</style>
