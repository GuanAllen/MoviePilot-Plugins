<script setup>
// MagicFlow 前端 · 种子详情弹窗（P4）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
// 展示态纯函数（stateColor / stateLabel / torrentProgressPct / torrentIsPaused /
// torrentPauseLabel / torrentResumeLabel）真值源仍在 useSeeding；此处为 P4 拆分随模板
// 搬入的同口径实现（与 components/tabs/SeedingTab.js 保持一致）。
import { formatBytes } from '../../../../utils'
import { TORRENT_STATE_TEXT, TORRENT_PAUSED_STATES } from '../../constants'

const open = defineModel({ type: Boolean, default: false })

// props（向下）：torrent = useSeeding.activeTorrent；task = useTaskDetail.selectedTask（仅用 site_name）；
// saving = useSeeding.saving；narrow = isNarrow。
defineProps({
  torrent: { type: Object, default: null },
  task: { type: Object, default: () => ({}) },
  saving: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['copy-hash', 'action', 'delete'])

function stateLabel(state) {
  const key = String(state || '').toLowerCase()
  return TORRENT_STATE_TEXT[key] || (key ? state : '托管中')
}
function stateColor(state) {
  const key = String(state || '').toLowerCase()
  if (['uploading', 'forcedup', 'stalledup', 'queuedup'].includes(key)) return 'success'
  if (['downloading', 'forceddl', 'queueddl', 'metadl', 'checkingdl'].includes(key)) return 'info'
  if (key === 'stalleddl') return 'warning'
  if (['error', 'missingfiles'].includes(key)) return 'error'
  return 'grey'
}
function torrentProgressPct(item) {
  const pct = Number(item?.progress || 0) * 100
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}
function torrentIsPaused(item) {
  return TORRENT_PAUSED_STATES.includes(String(item?.state || '').toLowerCase())
}
function torrentPauseLabel(item) {
  return torrentProgressPct(item) >= 100 ? '暂停做种' : '暂停下载'
}
function torrentResumeLabel(item) {
  return torrentProgressPct(item) >= 100 ? '恢复做种' : '继续下载'
}
</script>

<template>
  <VDialog v-model="open" max-width="34rem" :fullscreen="narrow">
    <VCard v-if="torrent" class="magicflow-dialog magicflow-torrent-dialog">
      <header class="magicflow-torrent-dialog__head">
        <div class="magicflow-torrent-dialog__tags">
          <VChip size="small" :color="stateColor(torrent.state)" variant="tonal">{{ stateLabel(torrent.state) }}</VChip>
          <VChip v-if="torrent.is_protected" size="small" color="primary" variant="tonal" prepend-icon="mdi-shield-check-outline">已保留</VChip>
          <VChip size="small" variant="tonal">{{ task.site_name }}</VChip>
        </div>
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>

      <div class="magicflow-torrent-dialog__title">{{ torrent.title || '种子详情' }}</div>

      <div class="magicflow-torrent-dialog__progress">
        <VProgressLinear
          :model-value="torrentProgressPct(torrent)"
          :color="stateColor(torrent.state)"
          height="8"
          rounded
        />
        <span class="magicflow-torrent-dialog__pct">{{ torrentProgressPct(torrent) }}%</span>
      </div>

      <dl class="magicflow-torrent-dialog__grid">
        <div><dt>大小</dt><dd>{{ Number(torrent.size_gb || 0).toFixed(2) }} GB</dd></div>
        <div><dt>上传量</dt><dd>{{ formatBytes(torrent.uploaded) }}</dd></div>
        <div><dt>分享率</dt><dd>{{ Number(torrent.ratio || 0).toFixed(2) }}</dd></div>
        <div><dt>当前状态</dt><dd>{{ stateLabel(torrent.state) }}</dd></div>
      </dl>

      <div class="magicflow-torrent-dialog__hash">
        <span class="magicflow-torrent-dialog__hash-label">infohash</span>
        <code>{{ torrent.hash }}</code>
        <VBtn size="x-small" variant="text" icon="mdi-content-copy" aria-label="复制 infohash" @click="emit('copy-hash', torrent.hash)" />
      </div>

      <VCardActions class="magicflow-torrent-dialog__actions">
        <VBtn
          size="small"
          variant="tonal"
          :color="torrent.is_protected ? 'grey' : 'primary'"
          :prepend-icon="torrent.is_protected ? 'mdi-shield-off-outline' : 'mdi-shield-check-outline'"
          :loading="saving"
          @click="emit('action', torrent.is_protected ? 'unprotect' : 'protect')"
        >{{ torrent.is_protected ? '取消保留' : '保留' }}</VBtn>
        <VBtn
          v-if="torrentIsPaused(torrent)"
          size="small"
          variant="tonal"
          prepend-icon="mdi-play-circle-outline"
          :loading="saving"
          @click="emit('action', 'resume')"
        >{{ torrentResumeLabel(torrent) }}</VBtn>
        <VBtn v-else size="small" variant="tonal" prepend-icon="mdi-pause-circle-outline" :loading="saving" @click="emit('action', 'pause')">{{ torrentPauseLabel(torrent) }}</VBtn>
        <VBtn size="small" variant="tonal" prepend-icon="mdi-sync" :loading="saving" @click="emit('action', 'recheck')">校验</VBtn>
        <VSpacer />
        <VBtn size="small" color="error" variant="tonal" prepend-icon="mdi-delete-outline" :loading="saving" @click="emit('delete', torrent)">删除</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 种子详情弹窗：随弹窗自 index.vue 迁入并从 index.vue 删除。
     共享选择器（magicflow-dialog）父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。
     VDialog 会 teleport 到 body，父 scoped 够不到子内部，故须自带。── */
.magicflow-dialog {
  background: rgb(var(--v-theme-surface)) !important;
  border: 1px solid var(--magicflow-panel-brd);
  border-radius: 18px;
  backdrop-filter: blur(16px) saturate(120%);
  -webkit-backdrop-filter: blur(16px) saturate(120%);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5);
  color: rgb(var(--v-theme-on-surface));
}

/* ---------- 种子详情弹窗（专属） ---------- */
.magicflow-torrent-dialog {
  padding: 18px 20px 8px;
}

.magicflow-torrent-dialog__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.magicflow-torrent-dialog__tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-inline-size: 0;
}

.magicflow-torrent-dialog__title {
  margin-block: 10px 0;
  font-size: 15px;
  font-weight: 650;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.magicflow-torrent-dialog__progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-block: 12px 4px;
}

.magicflow-torrent-dialog__progress .v-progress-linear {
  flex: 1 1 auto;
}

.magicflow-torrent-dialog__pct {
  flex: 0 0 auto;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), 0.85);
  min-inline-size: 3.2em;
  text-align: end;
}

.magicflow-torrent-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
  margin-block: 14px 4px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.07);
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.16);
}

.magicflow-torrent-dialog__grid > div {
  min-inline-size: 0;
}

.magicflow-torrent-dialog__grid dt {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft));
  margin-block-end: 2px;
}

.magicflow-torrent-dialog__grid dd {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.magicflow-torrent-dialog__hash {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-block: 12px 0;
  min-inline-size: 0;
}

.magicflow-torrent-dialog__hash-label {
  flex: 0 0 auto;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), var(--mf-fg-mid));
}

.magicflow-torrent-dialog__hash code {
  flex: 1 1 auto;
  min-inline-size: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  overflow-wrap: anywhere;
  color: rgba(var(--v-theme-on-surface), 0.8);
}

.magicflow-torrent-dialog__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 14px 0 8px;
}

/* ── ★ 功能弹窗统一：卡片纵向 flex + 正文吃掉剩余高度 ── */
.magicflow-torrent-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  /* ★ 19.12.59：原来是 overflow:hidden —— 标题一长或屏一矮，操作条会被直接裁掉，
     而且滚不动（用户能看到的只有「没有操作按钮」）。改成纵向可滚、横向仍裁。 */
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
}

/* 桌面/平板：内容在顶、操作按钮钉底，中间自然撑开 */
.magicflow-torrent-dialog__actions { margin-block-start: auto; }

/* ★ 19.12.59 手机全屏（isNarrow = ≤959，VDialog 走 fullscreen）重新排布。
   旧问题：父页 index.vue 给的安全区 `.magicflow-torrent-dialog{padding-bottom:92px}`
   只有单类优先级（0,1,0），被本组件 ≤699 的 `padding:16px 14px 4px`（0,2,0）整条覆盖 →
   手机上一律失效，按钮贴死在视口最底边，正好落进 MP 右下角 AI 悬浮球的地盘，
   看起来就是「操作按钮没了」；中间还被 margin:auto 撑出一大块空白（排版乱）。
   现在：按钮不再钉底，紧跟 infohash，一屏到底；卡片自身可滚、底部留安全区。 */
@media (max-width: 959px) {
  .magicflow-torrent-dialog {
    max-block-size: 100dvh;
    padding: 14px 16px calc(14px + env(safe-area-inset-bottom, 0px));
    border-radius: 0;
  }

  .magicflow-torrent-dialog__actions {
    margin-block-start: 12px;
    padding-block: 12px 0;
    border-block-start: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  }

  .magicflow-torrent-dialog__actions .v-btn {
    flex: 1 1 auto;
    min-inline-size: 0;
  }
}

@media (max-width: 699px) {
  /* 种子详情弹窗：窄屏收紧留白与网格间距（★ 不再设 padding 简写，
     否则会把上面 959 段的安全区 padding 整条覆盖掉） */
  .magicflow-torrent-dialog__grid {
    gap: 8px 10px;
    padding: 10px 12px;
  }
  .magicflow-torrent-dialog__actions {
    gap: 4px;
  }
  .magicflow-torrent-dialog__actions .v-btn {
    padding-inline: 8px;
    font-size: 12px;
  }
}
</style>
