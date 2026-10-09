<script setup>
// MagicFlow 前端 · 概览 Tab（P4 拆分）
// 自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式；零行为 / 零样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不直接调父方法。
// 展示型纯函数（formatBytes / formatBonus / formatDateTime / runStatusText / formatDurationSeconds）
// 是 src/utils 的共享工具 → 直接 import（非父方法、不作为 Function prop 下发）。
import { formatBonus, formatBytes, formatDateTime, formatDurationSeconds, runStatusText } from '../../../../utils'

defineProps({
  selectedTask: { type: Object, default: () => ({}) },
  taskIsBrush: { type: Boolean, default: false },
  taskConfig: { type: Object, default: () => ({}) },
  brushSeedDays: { type: [Number, String], default: 0 },
  goalFactText: { type: String, default: '' },
  selectedState: { type: Object, default: () => ({}) },
  detailStats: { type: Object, default: () => ({}) },
  siteAccount: { type: Object, default: () => ({}) },
  siteUser: { type: Object, default: () => ({}) },
  siteLiveLevel: { type: String, default: '' },
  siteLiveRates: { type: Object, default: () => ({}) },
  siteLiveCfg: { type: Object, default: () => ({}) },
  siteLiveAlerts: { type: Array, default: () => [] },
  decision: { type: Object, default: () => ({}) },
  decisionCapText: { type: [String, Number], default: '' },
  decisionReasons: { type: Array, default: () => [] },
  trendCards: { type: Array, default: () => [] },
})

// 仅为满足模板静态检查：事件用法见 @click="emit('open-entry', 'diagnostics')"。
const emit = defineEmits(['open-entry'])
</script>

<template>
  <div class="magicflow-stat-grid">
    <VSheet class="magicflow-stat magicflow-stat--accent app-surface-static">
      <strong>{{ selectedTask.seeding_count || 0 }}</strong>
      <span>托管种子 · {{ selectedTask.active_seeding_count || 0 }} 做种中 / {{ selectedTask.downloading_count || 0 }} 下载中 / {{ selectedTask.paused_count || 0 }} 已暂停</span>
    </VSheet>
    <template v-if="taskIsBrush">
      <VSheet class="magicflow-stat app-surface-static">
        <strong>{{ formatBytes(selectedTask.task_uploaded || 0) }}</strong>
        <span>本任务上传量 · 下载器累计（{{ selectedTask.task_upload_active || 0 }} 个有上传）</span>
      </VSheet>
      <VSheet class="magicflow-stat app-surface-static">
        <strong>{{ siteAccount.ok ? formatBytes(siteAccount.upload || 0) : '—' }}</strong>
        <span>站点上传量 · {{ siteAccount.source === 'live' ? '实时（直连站点）' : 'MP 快照' }}{{ siteAccount.ok ? ` · 下载 ${formatBytes(siteAccount.download || 0)}` : '' }}</span>
      </VSheet>
    </template>
    <template v-else>
      <VSheet class="magicflow-stat app-surface-static">
        <strong>{{ selectedTask.site_bonus_ok ? formatBonus(selectedTask.site_bonus_per_hour) : '—' }}</strong>
        <span>站点上报时魔 · 站点实时值</span>
      </VSheet>
      <VSheet class="magicflow-stat app-surface-static">
        <strong>{{ Number(selectedTask.site_current_bonus || 0).toFixed(2) }}</strong>
        <span>站点当前魔力 · 该站点实时存量</span>
      </VSheet>
    </template>
    <VSheet class="magicflow-stat app-surface-static">
      <strong>{{ detailStats.last_added || 0 }} / {{ detailStats.last_reused || 0 }} / {{ detailStats.last_deleted || 0 }}</strong>
      <span>上次运行 新增/复用/删除 · 当前托管 {{ detailStats.last_kept || selectedTask.seeding_count || 0 }}</span>
    </VSheet>
  </div>
  <div v-if="(selectedTask.run_mode || 'running') === 'seeding'" class="magicflow-stat-grid magicflow-stat-grid--single">
    <VSheet class="magicflow-stat magicflow-stat--accent app-surface-static">
      <strong>{{ selectedTask.protected_count || 0 }}</strong>
      <span>接管保护 · 手动加或 IYUU 回来的种子已纳管并永久保护（不再补种/刷魔力）</span>
    </VSheet>
  </div>

  <!-- ★ 可观测①：本轮决策轨迹（回答「为什么这轮没删 / 没换 / 删了什么」） -->
  <VSheet v-if="decision.at_cap !== undefined" tag="section" class="magicflow-panel app-surface-static mf-obs">
    <header class="magicflow-panel__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">本轮决策</div>
        <div class="text-body-2 text-medium-emphasis">为什么这么做 · 最近一轮的闸门判定与淘汰口径</div>
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

  <!-- ★ 可观测②：每小时趋势 sparkline -->
  <VSheet v-if="trendCards.length" tag="section" class="magicflow-panel app-surface-static mf-obs">
    <header class="magicflow-panel__head">
      <div>
        <div class="text-subtitle-1 font-weight-medium">趋势</div>
        <div class="text-body-2 text-medium-emphasis">每小时采样 · 最近 72 小时（本地序列，无外部依赖）</div>
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

  <div class="magicflow-overview-grid">
    <VSheet tag="section" class="magicflow-panel app-surface-static">
      <header class="magicflow-panel__head">
        <div>
          <div class="text-subtitle-1 font-weight-medium">运行状态</div>
          <div class="text-body-2 text-medium-emphasis">当前任务调度与魔力策略</div>
        </div>
        <VChip :color="selectedState.color" size="small" variant="tonal">{{ selectedState.text }}</VChip>
      </header>
      <dl class="magicflow-facts">
        <div><dt>任务目标</dt><dd>{{ goalFactText }}</dd></div>
        <div><dt>选种周期</dt><dd>{{ taskConfig.cron_expression || `每 ${taskConfig.brush_interval} 分钟` }}</dd></div>
        <div><dt>检查周期</dt><dd>每 {{ taskConfig.check_interval }} 分钟</dd></div>
        <div><dt>开启时段</dt><dd>{{ taskConfig.active_time_range || '全天' }}</dd></div>
        <template v-if="taskIsBrush">
          <div><dt>保种天数</dt><dd>{{ brushSeedDays > 0 ? `做种满 ${brushSeedDays} 天清理` : '不按天数（按无上传）' }}</dd></div>
          <div><dt>最小下载人数</dt><dd>{{ taskConfig.brush_min_leechers ?? 1 }} 人</dd></div>
        </template>
        <template v-else>
          <div><dt>最低魔力</dt><dd>{{ taskConfig.min_bonus_per_hour == null ? '自动' : `${Number(taskConfig.min_bonus_per_hour).toFixed(2)} /h` }}</dd></div>
          <div><dt>最多保留</dt><dd>{{ taskConfig.max_keep_torrents == null ? (taskConfig.disk_size_gb ? `按 ${taskConfig.disk_size_gb}GB 自动` : '不限') : `${taskConfig.max_keep_torrents} 个` }}</dd></div>
          <div><dt>保护阈值</dt><dd>{{ taskConfig.bonus_protect_threshold == null ? '站点当前魔力' : Number(taskConfig.bonus_protect_threshold).toFixed(0) }}</dd></div>
          <div><dt>完美种保护</dt><dd>{{ taskConfig.protect_perfect === false ? '关闭' : `开启（≤${taskConfig.perfect_max_seeders ?? 3}人 · ≥${taskConfig.perfect_min_weeks ?? 4}周）` }}</dd></div>
        </template>
        <div><dt>自动补种</dt><dd>{{ taskConfig.refill_when_empty ? '开启' : '关闭' }}</dd></div>
        <div><dt>无进度清理</dt><dd>{{ taskConfig.cleanup_no_progress ? `开启（${taskConfig.no_progress_minutes ?? 30} 分钟）` : '关闭' }}</dd></div>
        <div><dt>慢速清理</dt><dd>{{ taskConfig.cleanup_slow_progress === false ? '关闭' : `开启（> ${taskConfig.slow_progress_max_hours ?? 48}h 下不完即清）` }}</dd></div>
        <div><dt>促销失效清理</dt><dd>{{ taskConfig.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）' }}</dd></div>
        <div><dt>自动恢复暂停</dt><dd>{{ taskConfig.auto_resume_paused === false ? '关闭' : '开启' }}</dd></div>
        <div><dt>选种来源</dt><dd>{{ taskConfig.rss_support ? 'RSS' : '站点列表页' }}</dd></div>
        <div><dt>促销要求</dt><dd>{{ taskIsBrush ? '免费（含 2X免费）' : (taskConfig.freeleech === '2xfree' ? '2X 免费' : taskConfig.freeleech === 'free' ? '免费' : '全部') }}</dd></div>
      </dl>
    </VSheet>

    <VSheet tag="section" class="magicflow-panel app-surface-static">
      <header class="magicflow-panel__head">
        <div>
          <div class="text-subtitle-1 font-weight-medium">站点数据</div>
          <div class="text-body-2 text-medium-emphasis">
            <template v-if="siteAccount.source === 'live'">魔流直连站点用户栏（实时）{{ siteAccount.sampledAt ? ` · 采样于 ${siteAccount.sampledAt}` : '' }}</template>
            <template v-else-if="siteAccount.source === 'mp'">MoviePilot 站点数据快照（默认 6 小时一轮）{{ siteUser.updated_at ? ` · 更新于 ${siteUser.updated_at}` : '' }}</template>
            <template v-else>暂无站点数据</template>
          </div>
        </div>
        <VChip v-if="siteAccount.source === 'live'" size="small" variant="tonal" :color="siteLiveLevel === 'warn' ? 'warning' : 'success'">
          {{ siteLiveLevel === 'warn' ? '实时 · 有告警' : '实时' }}
        </VChip>
        <VChip v-else-if="siteAccount.source === 'mp'" size="small" variant="tonal">MP 快照</VChip>
        <VChip v-else size="small" variant="tonal">暂无数据</VChip>
      </header>
      <dl class="magicflow-facts">
        <div><dt>上传量</dt><dd>{{ siteAccount.ok ? formatBytes(siteAccount.upload || 0) : '—' }}</dd></div>
        <div><dt>下载量</dt><dd>{{ siteAccount.ok ? formatBytes(siteAccount.download || 0) : '—' }}</dd></div>
        <div><dt>分享率</dt><dd>{{ siteAccount.ok && siteAccount.ratio != null ? Number(siteAccount.ratio).toFixed(3) : '—' }}</dd></div>
        <div><dt>做种数 / 下载数</dt><dd>{{ siteAccount.ok ? `${siteAccount.seeding ?? '—'} / ${siteAccount.leeching ?? '—'}` : '—' }}</dd></div>
        <div v-if="siteAccount.seeding_size"><dt>做种体积</dt><dd>{{ formatBytes(siteAccount.seeding_size) }}</dd></div>
        <div><dt>站点魔力</dt><dd>{{ siteAccount.ok && siteAccount.bonus != null ? Number(siteAccount.bonus).toFixed(2) : '—' }}{{ siteAccount.bonus_per_hour != null ? ` · ${Number(siteAccount.bonus_per_hour).toFixed(2)}/h` : '' }}</dd></div>
        <template v-if="siteAccount.source === 'live'">
          <div><dt>上传速率</dt><dd>{{ siteLiveRates.ok ? `${Number(siteLiveRates.up_mb_min || 0).toFixed(1)} MB/分` : '采样中' }}</dd></div>
          <div><dt>下载速率</dt><dd :class="{ 'text-error': (siteLiveRates.down_mb_min || 0) >= (siteLiveCfg.download_alert_mb || 50) }">{{ siteLiveRates.ok ? `${Number(siteLiveRates.down_mb_min || 0).toFixed(1)} MB/分` : '采样中' }}</dd></div>
          <div><dt>近 1h 净增</dt><dd>{{ siteLiveRates.ok ? `⬆ ${formatBytes(Math.max(0, siteLiveRates.d_up || 0))} / ⬇ ${formatBytes(Math.max(0, siteLiveRates.d_down || 0))}` : '—' }}</dd></div>
        </template>
      </dl>
      <div v-if="siteLiveAlerts.length" class="magicflow-live-alerts">
        <div v-for="(alert, idx) in siteLiveAlerts" :key="`${alert.kind}-${idx}`" class="magicflow-live-alert" :class="`magicflow-live-alert--${alert.level || 'info'}`">
          {{ alert.text }}
        </div>
      </div>
    </VSheet>

    <VSheet tag="section" class="magicflow-panel app-surface-static">
      <header class="magicflow-panel__head">
        <div>
          <div class="text-subtitle-1 font-weight-medium">最近一次运行</div>
          <div class="text-body-2 text-medium-emphasis">
            {{ detailStats.last_run_at ? formatDateTime(detailStats.last_run_at) : '暂无运行记录' }}
          </div>
        </div>
        <VChip v-if="detailStats.last_error" color="error" size="small" variant="tonal">失败</VChip>
        <VChip v-else-if="detailStats.last_run_status" :color="detailStats.last_run_status === 'done' ? 'success' : detailStats.last_run_status === 'failed' ? 'error' : 'secondary'" size="small" variant="tonal">
          {{ runStatusText(detailStats.last_run_status) }}
        </VChip>
        <VChip v-else-if="detailStats.last_success_at" color="success" size="small" variant="tonal">完成</VChip>
      </header>
      <div class="magicflow-run-summary">
        <div><span>上次成功</span><strong>{{ detailStats.last_success_at ? formatDateTime(detailStats.last_success_at) : '-' }}</strong></div>
        <div><span>本次状态</span><strong>{{ runStatusText(detailStats.last_run_status) }}</strong></div>
        <div><span>本次耗时</span><strong>{{ formatDurationSeconds(detailStats.last_run_duration) }}</strong></div>
        <div><span>本次新增 / 复用</span><strong>{{ detailStats.last_added || 0 }} / {{ detailStats.last_reused || 0 }}</strong></div>
        <div><span>本次删除</span><strong>{{ detailStats.last_deleted || 0 }}</strong></div>
        <div><span>当前托管 / 受保护</span><strong>{{ detailStats.last_kept || 0 }} / {{ detailStats.protected_count || 0 }}</strong></div>
      </div>
      <VAlert v-if="detailStats.last_run_reason" type="info" variant="tonal" density="compact" class="mb-2">
        本轮说明：{{ detailStats.last_run_reason }}
      </VAlert>
      <VAlert v-if="detailStats.last_error" type="error" variant="tonal" density="compact">
        {{ detailStats.last_error }}
      </VAlert>
      <VBtn variant="text" color="primary" append-icon="mdi-arrow-right" @click="emit('open-entry', 'diagnostics')">
        查看运行诊断
      </VBtn>
    </VSheet>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   概览 Tab 样式（P4 拆分）。
   · **专属选择器**（仅本面板使用）：.magicflow-overview-grid / .magicflow-stat-grid--single /
     .magicflow-stat--accent / .magicflow-live-alert(s) / .magicflow-run-summary / .mf-obs* / .mf-spark*
     → 自 index.vue **迁入**（父页对应规则已删除）。
   · **共享选择器**（父页多处使用）：.magicflow-stat(-grid) / .magicflow-panel(__head) / .magicflow-facts
     → 组件内**复制一份**，index.vue 原样保留（纯复制、零改动）。
   顺序与 index.vue 中一致，保证层叠（!important / 主题覆盖）行为完全相同。
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── 共享：面板头部（index.vue L3673 / L3688 / L4493）── */
.magicflow-panel__head {
  display: flex;
  align-items: center;
}
.magicflow-panel__head {
  justify-content: space-between;
}
.magicflow-panel__head {
  align-items: flex-start;
  gap: 12px;
}

/* ── 共享：磁贴网格 / 磁贴 / 面板 / 事实表（index.vue L4250 / L4449-4477 / L4488-4503 / L4534-4549）── */
.magicflow-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.magicflow-stat,
.magicflow-panel {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
}

.magicflow-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-block-size: 116px;
  padding: 16px;
}

.magicflow-stat > span,
.magicflow-stat > small {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-stat > strong {
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.magicflow-stat :deep(.v-progress-linear) {
  margin-block-start: auto;
}

.magicflow-panel {
  min-inline-size: 0;
  padding: 16px;
}

.magicflow-facts {
  display: grid;
  gap: 11px;
  margin: 18px 0 0;
}

.magicflow-facts > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-inline-size: 0;
}

.magicflow-facts dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.magicflow-facts dd {
  margin: 0;
  text-align: end;
  overflow-wrap: anywhere;
}

/* ── 专属（迁入）：概览网格 / 单列磁贴网格 ── */
.magicflow-overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-block-start: 12px;
}

.magicflow-stat-grid--single {
  grid-template-columns: minmax(0, 1fr);
  margin-block-start: 12px;
}

.magicflow-stat-grid--single .magicflow-stat {
  min-block-size: auto;
  padding-block: 12px;
}

/* ── 专属（迁入）：站点实时告警 ── */
.magicflow-live-alerts {
  display: grid;
  gap: 6px;
  margin-block-start: 12px;
}

.magicflow-live-alert {
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.78rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
  border-inline-start: 3px solid transparent;
}

.magicflow-live-alert--warn {
  background: rgba(var(--v-theme-warning), 0.12);
  border-inline-start-color: rgb(var(--v-theme-warning));
}

.magicflow-live-alert--info {
  background: rgba(var(--v-theme-info), 0.12);
  border-inline-start-color: rgb(var(--v-theme-info));
}

/* ── 专属（迁入）：最近一次运行摘要 ── */
.magicflow-run-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-block: 20px;
}

.magicflow-run-summary > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.magicflow-run-summary span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.8rem;
}

.magicflow-run-summary strong {
  font-size: 1.2rem;
}

/* ── 专属（迁入）：本轮决策 / 趋势 sparkline ── */
.mf-obs {
  margin-block-start: 12px;
}

.mf-obs__rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-block-start: 4px;
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
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
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

/* ── 响应式（index.vue 对应 @media 内规则；共享部分复制、专属部分迁入）── */
@media (max-width: 1199px) {
  .magicflow-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .magicflow-page .magicflow-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 959px) {
  .magicflow-overview-grid {
    grid-template-columns: 1fr;
  }
  /* 概览窗口里的旧大块内容在手机端隐藏（信息已收进紧凑块 / 任务配置页） */
  .magicflow-page .magicflow-window .magicflow-window-ov .magicflow-stat-grid,
  .magicflow-page .magicflow-window .magicflow-window-ov .magicflow-overview-grid { display: none; }
}

@media (max-width: 699px) {
  .magicflow-panel__head {
    flex-direction: column;
    align-items: flex-start;
  }
  .magicflow-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .magicflow-stat {
    min-block-size: 104px;
    padding: 13px;
  }
  .magicflow-stat > strong {
    font-size: 1.05rem;
  }
  .magicflow-panel {
    padding: 14px;
  }
  .magicflow-panel__head {
    flex-wrap: wrap;
  }
  .magicflow-run-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 419px) {
  .magicflow-stat-grid {
    grid-template-columns: 1fr;
  }
}

/* ── 深色磨砂主题覆盖（.magicflow-page 作用域）：共享部分复制、专属部分迁入。──
   注意：--magicflow-panel-bg/--magicflow-panel-brd 定义在祖先 .magicflow-page 上，随 CSS 变量继承生效。 */
.magicflow-page .magicflow-panel,
.magicflow-page .magicflow-stat {
  background: var(--magicflow-panel-bg) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 16px;
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32), inset 0 1px 0 rgba(var(--v-theme-on-surface), 0.04);
}

.magicflow-page .magicflow-stat {
  gap: 6px;
  min-block-size: 84px;
  padding: 14px 16px;
}

.magicflow-page .magicflow-stat > strong {
  font-size: 20px;
  font-weight: 680;
  line-height: 1.2;
  letter-spacing: 0.2px;
}

.magicflow-page .magicflow-stat > span,
.magicflow-page .magicflow-stat > small {
  font-size: 11px;
}

.magicflow-page .magicflow-stat--accent > strong {
  color: rgb(var(--v-theme-primary));
}

/* 面板标题排版（预览图：14px/600 + 11px 说明） */
.magicflow-page .magicflow-panel {
  padding: 18px 16px;
}

.magicflow-page .magicflow-panel__head .text-subtitle-1 {
  font-size: 14px;
  font-weight: 600;
}

.magicflow-page .magicflow-panel__head .text-body-2 {
  font-size: 11px;
}
</style>
