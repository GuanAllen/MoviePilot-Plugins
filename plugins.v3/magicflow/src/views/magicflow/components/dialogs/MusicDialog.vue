<script setup>
// MagicFlow 前端 · 音乐弹窗（★ 2026-10-10 批2 改版：清单视图）
// Master 口径：「清单做，跟点播一样，不要歌单了（塞不下）」——移除歌单/干跑/加种，
// 改为与点播同构的**清单**（进行中/已完成两 Tab + 行内 暂停/继续/移除）。
// 数据向下（defineModel / props）、事件向上（emit）。
import { tsText } from '../../format'
import {
  odPct, odSpeed, odEtaText, odStageColor, odIsPaused,
} from '../../composables/useOndemand'

const musicOpen = defineModel({ type: Boolean, default: false })
const musicTab = defineModel('tab', { type: String, default: 'inflight' })
const musicMsg = defineModel('msg', { type: String, default: '' })
const musicQuery = defineModel('query', { type: String, default: '' })
const musicSiteIds = defineModel('siteIds', { type: Array, default: () => [] })

defineProps({
  musicInflight: { type: Array, default: () => [] },
  musicHistory: { type: Array, default: () => [] },
  musicItemsBusy: { type: Boolean, default: false },
  musicActing: { type: String, default: '' },
  musicSearching: { type: Boolean, default: false },
  musicCandidates: { type: Array, default: () => [] },
  musicResult: { type: Object, default: null },
  musicDownloading: { type: String, default: '' },
  siteSelectItems: { type: Array, default: () => [] },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh-items', 'act', 'search', 'download'])

function loadMusicItems() { emit('refresh-items') }
function actMusic(row, action) { emit('act', row, action) }
function runMusicSearch() { emit('search') }
function downloadMusic(cid) { emit('download', cid) }
</script>

<template>
  <VDialog v-model="musicOpen" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-music-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">音乐</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="musicOpen = false" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-music-dialog__body">
        <div class="magicflow-music-search">
          <div class="magicflow-music-search__row">
            <VTextField
              v-model="musicQuery"
              density="comfortable"
              hide-details="auto"
              label="歌名 / 艺人"
              placeholder="如 周杰伦 / Butter-Fly"
              @keyup.enter="runMusicSearch"
            />
            <VSelect
              v-model="musicSiteIds"
              density="comfortable"
              hide-details="auto"
              :items="siteSelectItems"
              label="站点（空＝全部）"
              multiple
              chips
              closable-chips
            />
            <VBtn
              size="small"
              color="primary"
              variant="tonal"
              prepend-icon="mdi-magnify"
              :loading="musicSearching"
              @click="runMusicSearch"
            >搜一首</VBtn>
          </div>
          <div v-if="musicCandidates.length" class="magicflow-music-cands">
            <div class="magicflow-music-cands__head">
              候选 {{ musicCandidates.length }}（相关度 → 评分）· 点「下这条」
            </div>
            <article v-for="c in musicCandidates" :key="c.cid" class="magicflow-music-cand">
              <div class="magicflow-music-cand__main">
                <div class="magicflow-music-cand__title" :title="c.title">{{ c.title || '(无标题)' }}</div>
                <div class="magicflow-music-cand__meta">
                  <VChip size="x-small" variant="tonal">{{ c.site_name || ('站 ' + c.site) }}</VChip>
                  <VChip v-if="c.free" size="x-small" variant="tonal" color="success">免费</VChip>
                  <span v-if="c.size_gb">{{ c.size_gb }} GB</span>
                  <span>做种 {{ c.seeders }}</span>
                  <span>相关度 {{ c.relevance }}</span>
                  <span>score {{ c.score }}</span>
                  <span v-if="c.excluded" class="magicflow-music-cand__ex">已过滤：{{ c.exclude_reason }}</span>
                </div>
              </div>
              <VBtn
                size="x-small"
                color="primary"
                variant="tonal"
                :disabled="c.excluded"
                :loading="musicDownloading === c.cid"
                @click="downloadMusic(c.cid)"
              >下这条</VBtn>
            </article>
          </div>
          <div v-else-if="musicResult" class="magicflow-music-cands__empty">
            没搜到候选（站点 {{ (musicResult.sites || []).join(', ') || '—' }}）。换个关键词或站点。
          </div>
        </div>
        <div class="magicflow-music-inventory">
          <div class="magicflow-music-inventory__head">
            <span class="magicflow-music-inventory__title">音乐清单</span>
            <VChip
              size="x-small"
              :variant="musicTab === 'inflight' ? 'flat' : 'tonal'"
              :color="musicTab === 'inflight' ? 'primary' : ''"
              class="magicflow-music-tab"
              @click="musicTab = 'inflight'"
            >进行中 {{ musicInflight.length }}</VChip>
            <VChip
              size="x-small"
              :variant="musicTab === 'done' ? 'flat' : 'tonal'"
              :color="musicTab === 'done' ? 'primary' : ''"
              class="magicflow-music-tab"
              @click="musicTab = 'done'"
            >已完成 {{ musicHistory.length }}</VChip>
            <VSpacer />
            <VBtn
              icon="mdi-refresh"
              size="x-small"
              variant="text"
              aria-label="刷新音乐清单"
              :loading="musicItemsBusy"
              @click="loadMusicItems"
            />
          </div>
          <VAlert
            v-if="musicMsg"
            :type="musicMsg.startsWith('❌') ? 'warning' : 'info'"
            variant="tonal"
            density="compact"
            closable
            class="mb-2"
            @click:close="musicMsg = ''"
          >{{ musicMsg }}</VAlert>
          <template v-if="musicTab === 'inflight'">
            <div v-if="!musicInflight.length" class="magicflow-music-inventory__empty">
              没有进行中的音乐。让 AI 搜 + 下几条吧。
            </div>
            <article v-for="row in musicInflight" :key="'m-i-' + row.hash" class="magicflow-music-row">
              <div class="magicflow-music-row__title" :title="row.title">
                {{ row.title || row.hash.slice(0, 12) }}
              </div>
              <div class="magicflow-music-row__meta">
                <VChip size="x-small" variant="tonal">{{ row.site || '—' }}</VChip>
                <VChip v-if="row.free" size="x-small" variant="tonal" color="success">免费</VChip>
                <VChip v-if="row.hit_and_run" size="x-small" variant="tonal" color="warning">H&R</VChip>
                <span v-if="row.size_gb">{{ row.size_gb.toFixed(2) }} GB</span>
                <span v-if="row.stage === 'downloading' && row.speed">{{ odSpeed(row.speed) }}</span>
                <span v-if="row.eta_s">{{ odEtaText(row.eta_s) }}</span>
              </div>
              <VProgressLinear
                :model-value="odPct(row)"
                height="6"
                rounded
                :color="odIsPaused(row) ? 'warning' : (row.stage === 'downloading' ? 'primary' : 'success')"
                class="mt-1"
              />
              <div class="magicflow-music-row__stage">
                <VChip size="x-small" variant="flat" :color="odIsPaused(row) ? 'warning' : odStageColor(row.stage)">
                  {{ odIsPaused(row) ? '已暂停' : row.stage_text }}
                </VChip>
                <span v-if="row.stage === 'downloading' && !odIsPaused(row)" class="magicflow-music-row__pct">{{ odPct(row).toFixed(1) }}%</span>
                <span class="magicflow-music-row__hash">{{ row.hash.slice(0, 12) }}</span>
                <VSpacer />
                <VBtn
                  v-if="!odIsPaused(row)"
                  size="x-small"
                  variant="tonal"
                  :loading="musicActing === row.hash + ':pause'"
                  @click="actMusic(row, 'pause')"
                >暂停</VBtn>
                <VBtn
                  v-else
                  size="x-small"
                  variant="tonal"
                  color="primary"
                  :loading="musicActing === row.hash + ':resume'"
                  @click="actMusic(row, 'resume')"
                >继续</VBtn>
                <VBtn
                  size="x-small"
                  variant="tonal"
                  color="error"
                  :loading="musicActing === row.hash + ':remove'"
                  @click="actMusic(row, 'remove')"
                >移除</VBtn>
              </div>
            </article>
          </template>
          <template v-else>
            <div v-if="!musicHistory.length" class="magicflow-music-inventory__empty">还没有已完成的音乐。</div>
            <article
              v-for="row in musicHistory"
              :key="'m-h-' + row.hash"
              class="magicflow-music-row magicflow-music-row--done"
            >
              <div class="magicflow-music-row__title" :title="row.title">
                {{ row.title || row.hash.slice(0, 12) }}
              </div>
              <div class="magicflow-music-row__meta">
                <VChip size="x-small" variant="tonal">{{ row.site || '—' }}</VChip>
                <span v-if="row.size_gb">{{ row.size_gb.toFixed(2) }} GB</span>
                <span class="magicflow-music-row__ts">{{ tsText(row.added_at) }}</span>
              </div>
              <div class="magicflow-music-row__stage">
                <VChip size="x-small" variant="tonal" :color="row.stage === 'resource' ? 'success' : (row.stage === 'downloading' ? 'primary' : '')">
                  {{ row.stage_text }}
                </VChip>
                <span class="magicflow-music-row__hash">{{ row.hash.slice(0, 12) }}</span>
              </div>
            </article>
          </template>
        </div>
        <p class="text-caption text-medium-emphasis mt-3 mb-0">
          音乐线：qB 分类 <code>音乐</code> 的种（与刷流/魔力分线，不会被当低效种清理）。
          搜索 + 下载走 AI 入口（<code>/agent/music/search</code> → <code>/agent/music/download</code>）——按相关度挑候选更靠谱。
        </p>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* 共享选择器（父页其它弹窗也用）→ 纯复制一份。VDialog teleport 到 body，父页 scoped 够不到。 */
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
.magicflow-settings-dialog__head i {
  color: rgba(var(--v-theme-on-surface), 0.9);
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

/* ── 音乐清单（与点播清单同构）────────────────────────────────────── */
.magicflow-music-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
}
.magicflow-music-dialog__body { padding: 10px 18px 20px; overflow: auto; flex: 1 1 auto; min-height: 0; }
/* ── 单搜单下（人机同源）──────────────────────────────────── */
.magicflow-music-search { margin-bottom: 10px; }
.magicflow-music-search__row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.magicflow-music-search__row > .v-input:first-child { flex: 1 1 16rem; }
.magicflow-music-search__row > .v-input:nth-child(2) { flex: 1 1 12rem; max-width: 22rem; }
.magicflow-music-cands { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
.magicflow-music-cands__head { font-size: 0.76rem; opacity: 0.75; }
.magicflow-music-cands__empty { margin-top: 6px; font-size: 0.78rem; opacity: 0.7; }
.magicflow-music-cand { display: flex; align-items: center; gap: 8px; border: 1px solid rgba(var(--v-theme-on-surface), 0.12); border-radius: 8px; padding: 6px 8px; }
.magicflow-music-cand__main { flex: 1 1 auto; min-inline-size: 0; }
.magicflow-music-cand__title { font-size: 0.8rem; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.magicflow-music-cand__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 3px; font-size: 0.72rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-music-cand__ex { color: rgb(var(--v-theme-warning)); }
.magicflow-music-inventory { border: 1px solid rgba(var(--v-theme-on-surface), 0.12); border-radius: 10px; padding: 8px 10px; background: rgba(var(--v-theme-on-surface), 0.03); }
.magicflow-music-inventory__head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.magicflow-music-inventory__title { font-size: 0.84rem; font-weight: 600; margin-right: 2px; }
.magicflow-music-inventory__empty { font-size: 0.78rem; opacity: 0.7; padding: 6px 2px; }
.magicflow-music-tab { cursor: pointer; user-select: none; }
.magicflow-music-row { border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07); padding: 6px 2px; }
.magicflow-music-row:first-of-type { border-top: none; }
.magicflow-music-row__title { font-size: 0.8rem; line-height: 1.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.magicflow-music-row__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 3px; font-size: 0.72rem; color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
.magicflow-music-row__stage { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.magicflow-music-row__pct { font-size: 0.72rem; font-variant-numeric: tabular-nums; opacity: 0.85; }
.magicflow-music-row__hash { font-size: 0.7rem; opacity: 0.55; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.magicflow-music-row__ts { font-variant-numeric: tabular-nums; opacity: 0.75; }
.magicflow-music-row--done .magicflow-music-row__title { color: rgba(var(--v-theme-on-surface), var(--mf-fg-soft)); }
</style>
