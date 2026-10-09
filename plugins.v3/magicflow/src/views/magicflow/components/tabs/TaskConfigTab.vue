<script setup>
// MagicFlow 前端 · 任务配置（只读参数）面板（P4）
// P4 拆分：自 views/magicflow/index.vue 的 <VWindowItem value="config"> 面板**纯搬家**
// （template 块 + 配套 scoped 样式，零行为/样式变更）。
// 数据向下（props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 只读派生值（isBrush / config / runMode / goalText / brushSeedDays）由父页 composable 计算后传入，
// 子组件不重复计算（单一真值源）。
// props 下（只读）：task=selectedTask / config=taskConfig / runMode=selectedRunMode /
// goalText=goalFactText / isBrush=taskIsBrush / brushSeedDays / saving。
// 只读派生值由父页 composable 计算后传入，子组件不重复计算（单一真值源）。
defineProps({
  task: { type: Object, default: () => ({}) },
  config: { type: Object, default: () => ({}) },
  runMode: { type: Object, default: () => ({ text: '' }) },
  goalText: { type: String, default: '' },
  isBrush: { type: Boolean, default: false },
  brushSeedDays: { type: Number, default: 0 },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['run', 'edit', 'delete'])
</script>

<template>
  <div class="magicflow-config-grid">
    <VSheet tag="section" class="magicflow-panel app-surface-static">
      <header class="magicflow-panel__head">
        <div>
          <div class="text-subtitle-1 font-weight-medium">{{ isBrush ? '刷流规则' : '魔力规则' }}</div>
          <div class="text-body-2 text-medium-emphasis">{{ isBrush ? '刷流标准：免费 + 有下载者；做种满天数清理' : '当前服务端生效的魔力养护配置' }}</div>
        </div>
      </header>
      <dl class="magicflow-facts magicflow-facts--two">
        <div><dt>任务状态</dt><dd>{{ runMode.text }}</dd></div>
        <div><dt>任务目标</dt><dd>{{ goalText }}</dd></div>
        <div>
          <dt>站点</dt>
          <dd>
            {{ task.site_name || task.site_domain || '未设置' }}
            <VChip
              v-if="task.site_missing"
              size="x-small"
              variant="tonal"
              color="error"
              title="该站点已从 MoviePilot 删除：站点相关处理已跳过，请删除任务或改绑其他站点"
            >站点已删除</VChip>
          </dd>
        </div>
        <div><dt>下载器</dt><dd>{{ task.downloader }}</dd></div>
        <div><dt>下载器标签</dt><dd>{{ task.brush_tag || '未设置' }}</dd></div>
        <div><dt>促销要求</dt><dd>{{ isBrush ? '免费（含 2X免费）' : (config.freeleech === '2xfree' ? '2X 免费' : config.freeleech === 'free' ? '免费' : '全部') }}</dd></div>
        <div><dt>选种来源</dt><dd>{{ config.rss_support ? 'RSS' : '站点列表页' }}</dd></div>
        <template v-if="isBrush">
          <div><dt>保种天数</dt><dd>{{ brushSeedDays > 0 ? `做种满 ${brushSeedDays} 天清理` : '不按天数（按无上传）' }}</dd></div>
          <div><dt>最小下载人数</dt><dd>{{ config.brush_min_leechers ?? 1 }} 人</dd></div>
          <div><dt>种子大小</dt><dd>{{ config.size || '不限' }}</dd></div>
          <div><dt>做种人数</dt><dd>{{ config.seeder || '不限' }}</dd></div>
          <div><dt>发布时间</dt><dd>{{ config.pubtime ? `${config.pubtime} 分钟` : '不限' }}</dd></div>
          <div><dt>排除 H&R</dt><dd>{{ config.hr === 'yes' ? '是' : '否' }}</dd></div>
          <div><dt>包含规则</dt><dd>{{ config.include || '无' }}</dd></div>
          <div><dt>排除规则</dt><dd>{{ config.exclude || '无' }}</dd></div>
        </template>
        <template v-else>
          <div><dt>保种体积</dt><dd>{{ config.disk_size_gb ? `${config.disk_size_gb} GB` : '不限' }}</dd></div>
          <div><dt>最低魔力</dt><dd>{{ config.min_bonus_per_hour == null ? '自动' : `${Number(config.min_bonus_per_hour).toFixed(2)} /h` }}</dd></div>
          <div><dt>最多保留</dt><dd>{{ config.max_keep_torrents == null ? '自动 / 不限' : `${config.max_keep_torrents} 个` }}</dd></div>
          <div><dt>保护阈值</dt><dd>{{ config.bonus_protect_threshold == null ? '站点当前魔力' : Number(config.bonus_protect_threshold).toFixed(0) }}</dd></div>
          <div><dt>完美种保护</dt><dd>{{ config.protect_perfect === false ? '关闭' : `开启（≤${config.perfect_max_seeders ?? 3}人 · ≥${config.perfect_min_weeks ?? 4}周）` }}</dd></div>
          <div><dt>公式 T0/N0</dt><dd>{{ config.bonus_t0 ?? '默认' }} / {{ config.bonus_n0 ?? '默认' }}</dd></div>
          <div><dt>公式 B0/L</dt><dd>{{ config.bonus_b0 ?? '默认' }} / {{ config.bonus_l ?? '默认' }}</dd></div>
          <div><dt>零魔权重</dt><dd>{{ config.bonus_zero_weight ?? '默认' }}</dd></div>
          <div><dt>保底魔力</dt><dd>{{ Number(config.min_bonus_to_keep || 0).toFixed(2) }}</dd></div>
          <div><dt>种子大小</dt><dd>{{ config.size || '不限' }}</dd></div>
          <div><dt>做种人数</dt><dd>{{ config.seeder || '不限' }}</dd></div>
          <div><dt>发布时间</dt><dd>{{ config.pubtime ? `${config.pubtime} 分钟` : '不限' }}</dd></div>
          <div><dt>排除 H&R</dt><dd>{{ config.hr === 'yes' ? '是' : '否' }}</dd></div>
          <div><dt>包含规则</dt><dd>{{ config.include || '无' }}</dd></div>
          <div><dt>排除规则</dt><dd>{{ config.exclude || '无' }}</dd></div>
          <div><dt>最短做种</dt><dd>{{ config.min_seed_time ? `${config.min_seed_time} 小时` : '不限' }}</dd></div>
          <div><dt>最低分享率</dt><dd>{{ Number(config.min_ratio || 0).toFixed(2) }}</dd></div>
        </template>
        <div><dt>单轮最多新增</dt><dd>{{ config.max_add_per_run ?? 10 }} 个</dd></div>
        <div><dt>同时下载上限</dt><dd>{{ config.max_download_concurrent ?? 10 }} 个</dd></div>
        <div><dt>每轮参评候选</dt><dd>{{ config.top_n ?? 30 }} 个</dd></div>
        <div><dt>每轮翻页数</dt><dd>{{ config.browse_pages ?? 3 }} 页</dd></div>
        <div><dt>自动补种</dt><dd>{{ config.refill_when_empty ? '开启' : '关闭' }}</dd></div>
        <div><dt>无进度清理</dt><dd>{{ config.cleanup_no_progress ? `开启（${config.no_progress_minutes ?? 30} 分钟）` : '关闭' }}</dd></div>
        <div><dt>慢速清理</dt><dd>{{ config.cleanup_slow_progress === false ? '关闭' : `开启（> ${config.slow_progress_max_hours ?? 48}h 下不完即清）` }}</dd></div>
        <div><dt>促销失效清理</dt><dd>{{ config.purge_unfree_incomplete === false ? '关闭' : '开启（已非免费且未下完→清）' }}</dd></div>
        <div><dt>自动恢复暂停</dt><dd>{{ config.auto_resume_paused === false ? '关闭' : '开启' }}</dd></div>
      </dl>
    </VSheet>

    <VSheet tag="section" class="magicflow-panel app-surface-static">
      <header class="magicflow-panel__head">
        <div>
          <div class="text-subtitle-1 font-weight-medium">任务操作</div>
          <div class="text-body-2 text-medium-emphasis">以下操作只影响当前任务</div>
        </div>
      </header>
      <div class="magicflow-config-actions">
        <div>
          <strong>执行一次</strong>
          <span>{{ isBrush ? '立即按刷流标准抓取免费热种并保持上传' : '立即按当前策略抓取候选并养护做种' }}</span>
          <VBtn color="primary" variant="tonal" prepend-icon="mdi-sync" :loading="saving" @click="emit('run')">
            立即执行
          </VBtn>
        </div>
        <VDivider />
        <div>
          <strong>编辑任务</strong>
          <span>{{ isBrush ? '调整调度、刷流门槛与清理策略' : '调整调度、魔力门槛与公式参数' }}</span>
          <VBtn variant="tonal" prepend-icon="mdi-pencil-outline" @click="emit('edit')">编辑任务</VBtn>
        </div>
        <VDivider />
        <div>
          <strong>删除任务</strong>
          <span>存在活跃种子时后端会拒绝删除，避免留下失管任务</span>
          <VBtn color="error" variant="tonal" prepend-icon="mdi-delete-outline" @click="emit('delete')">删除任务</VBtn>
        </div>
      </div>
    </VSheet>
  </div>
</template>

<style scoped>
/* ── 本面板专属选择器（随面板自 index.vue 迁入并从 index.vue 删除）：magicflow-config-grid / magicflow-config-actions * ──
   ── 共享选择器（父页多处共用：magicflow-panel / __head / facts *）→ index.vue 原样保留，此处**纯复制**一份，
      因 Vue scoped 样式不作用于子组件内部 DOM。── */
.magicflow-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-block-start: 12px;
}

/* ↓ 共享：magicflow-panel（复制自 index.vue，父页保留）*/
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

/* ↓ 共享：magicflow-facts（复制自 index.vue，父页保留）*/
.magicflow-facts {
  display: grid;
  gap: 11px;
  margin: 18px 0 0;
}
.magicflow-facts--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
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

/* ↓ 本面板专属：magicflow-config-actions *（自 index.vue 迁入并删除）*/
.magicflow-config-actions {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-block-start: 16px;
}
.magicflow-config-actions :deep(.v-btn) {
  align-self: flex-start;
  margin-block-start: 8px;
}
.magicflow-config-actions > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-inline-size: 0;
}
.magicflow-config-actions span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.82rem;
  overflow-wrap: anywhere;
}

/* 窄屏（复制自 index.vue 对应 media 块，父页保留）*/
@media (max-width: 959px) {
  .magicflow-config-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 699px) {
  .magicflow-panel__head {
    flex-direction: column;
    align-items: flex-start;
  }
  .magicflow-panel {
    padding: 14px;
  }
  .magicflow-panel__head {
    flex-wrap: wrap;
  }
  .magicflow-facts--two {
    grid-template-columns: 1fr;
  }
}
</style>
