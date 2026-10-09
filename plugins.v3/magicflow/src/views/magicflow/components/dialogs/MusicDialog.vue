<script setup>
// MagicFlow 前端 · 音乐甄别弹窗（15.8.2）
// P4 拆分：自 views/magicflow/index.vue **纯搬家**（template 块 + 配套 scoped 样式，无行为/样式变更）。
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态。
const open = defineModel({ type: Boolean, default: false })
const text = defineModel('text', { type: String, default: '' })
const sites = defineModel('sites', { type: String, default: '' })
const savePath = defineModel('savePath', { type: String, default: '' })
const error = defineModel('error', { type: String, default: '' })

defineProps({
  result: { type: Object, default: null },
  acting: { type: String, default: '' },
  grabReport: { type: Object, default: null },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['plan', 'grab', 'reset'])

const SAMPLE = 'Butter-Fly\n中島みゆき - 地上の星\n千里之外 @mptt,moufan\n青花瓷@3'

function onSample() {
  text.value = SAMPLE
}
function onClose() {
  open.value = false
}
function onClearError() {
  error.value = ''
}
</script>

<template>
  <VDialog v-model="open" max-width="52rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-music-dialog">
      <header class="magicflow-settings-dialog__head">
        <span class="magicflow-settings-dialog__title">音乐甄别</span>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-clipboard-text-outline" :disabled="!!acting" @click="onSample">示例</VBtn>
          <VBtn variant="text" color="primary" size="small" prepend-icon="mdi-refresh" @click="emit('reset')" :disabled="!!acting || !result">清结果</VBtn>
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="onClose" />
        </div>
      </header>
      <VDivider />
      <VCardText class="magicflow-music-body">
        <VTextarea
          v-model="text"
          label="歌单（每行一首）"
          placeholder="艺人 - 歌名&#10;歌名&#10;歌名@站id,站id&#10;例如：Butter-Fly"
          rows="6"
          density="comfortable"
          variant="outlined"
          auto-grow
          hide-details
          :readonly="!!acting"
        />
        <div class="magicflow-music-row mt-2">
          <VTextField
            v-model="sites"
            label="站点 id（空=全部已配站）"
            placeholder="逗号分隔，例如 3,7"
            density="compact"
            variant="outlined"
            hide-details
            clearable
            style="max-width: 14rem"
            :readonly="!!acting"
          />
          <VTextField
            v-model="savePath"
            label="保存目录（可选，留空走设置/默认）"
            placeholder="/vol6/1000/music"
            density="compact"
            variant="outlined"
            hide-details
            clearable
            style="max-width: 18rem"
            :readonly="!!acting"
          />
          <span class="flex-grow-1"></span>
          <VBtn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-playlist-music"
            :loading="acting === 'plan'"
            :disabled="!!acting || !text.trim()"
            @click="emit('plan')"
          >干跑计划</VBtn>
          <VBtn
            color="primary"
            variant="flat"
            prepend-icon="mdi-tray-arrow-down"
            :loading="acting === 'grab'"
            :disabled="!!acting || !text.trim()"
            @click="emit('grab')"
          >一键加种</VBtn>
        </div>
        <VAlert v-if="error" type="error" variant="tonal" density="compact" class="my-2" closable @click:close="onClearError">
          {{ error }}
        </VAlert>

        <!-- grab 报告 -->
        <VAlert v-if="grabReport && grabReport.totals" type="success" variant="tonal" density="compact" class="my-2">
          加种完成：新增 <strong>{{ (grabReport.totals.added || []).length }}</strong>，
          跳过 <strong>{{ (grabReport.totals.skipped || []).length }}</strong>，
          失败 <strong>{{ (grabReport.totals.failed || []).length }}</strong>
          <template v-if="grabReport.policy"> · {{ grabReport.policy }}</template>
        </VAlert>

        <!-- 计划 / 结果区 -->
        <VSheet v-if="result" tag="section" class="magicflow-panel app-surface-static mt-2">
          <header class="magicflow-panel__head">
            <div>
              <div class="text-subtitle-2 font-weight-medium">甄别结果</div>
              <div class="text-body-2 text-medium-emphasis">
                共 <strong>{{ result.summary?.entries || 0 }}</strong> 条歌单
                · 选中 <strong>{{ result.summary?.chosen || 0 }}</strong>
                · 空 <strong>{{ result.summary?.empty || 0 }}</strong>
                · 硬过滤 <strong>{{ result.summary?.excluded_video || 0 }}</strong>
                · 每首留 <strong>{{ result.summary?.per_item || 3 }}</strong> 候选
              </div>
            </div>
            <div class="d-flex align-center flex-wrap ga-2 justify-end">
              <VChip size="x-small" variant="tonal" color="primary">音乐线</VChip>
            </div>
          </header>
          <div class="magicflow-music-items">
            <article v-for="(it, idx) in (result.items || [])" :key="idx" class="magicflow-music-item">
              <div class="magicflow-music-item__head">
                <strong :title="it.query">
                  <VIcon :icon="it.chosen ? 'mdi-music-note-eighth' : 'mdi-music-note-outline'" size="14" :color="it.chosen ? 'primary' : 'medium-emphasis'" />
                  {{ it.artist || '' }}<span v-if="it.artist && it.title"> · </span>{{ it.title || it.raw }}
                </strong>
                <VChip size="x-small" :variant="it.chosen ? 'flat' : 'tonal'" :color="it.chosen ? 'primary' : 'medium-emphasis'">
                  {{ it.chosen ? `已选 · ${it.chosen.site_name || ('站 ' + it.chosen.site)}` : (it.empty_reason || '无候选') }}
                </VChip>
              </div>
              <div v-if="it.chosen" class="magicflow-music-item__body">
                <span class="text-body-2">
                  {{ it.chosen.title }}
                  <template v-if="it.chosen.size_gb"> · {{ Number(it.chosen.size_gb).toFixed(2) }}G</template>
                  <template v-if="it.chosen.seeders !== undefined && it.chosen.seeders !== null"> · {{ it.chosen.seeders }} 做种</template>
                  <template v-if="it.chosen.downloadvolumefactor !== undefined && it.chosen.downloadvolumefactor !== null"> · {{ Number(it.chosen.downloadvolumefactor).toFixed(2) }}x</template>
                  <template v-if="it.chosen.score !== undefined"> · score {{ it.chosen.score }}</template>
                </span>
                <span v-if="it.chosen_reasons && it.chosen_reasons.length" class="text-caption text-medium-emphasis">
                  命中：{{ it.chosen_reasons.join(' · ') }}
                </span>
                <span v-if="it.candidates && it.candidates.length > 1" class="text-caption text-medium-emphasis">
                  共 {{ it.candidates_total }} 候选 / 选中 1 / 备选 {{ it.candidates.length - 1 }}
                </span>
              </div>
              <div v-else-if="it.excluded && it.excluded.length" class="magicflow-music-item__body text-caption text-medium-emphasis">
                排除样本：<template v-for="(ex, i) in it.excluded" :key="i">
                  <span v-if="i > 0">；</span>{{ ex.title }}（{{ ex.reason }}）
                </template>
              </div>
            </article>
            <div v-if="!result.items?.length" class="magicflow-table-empty">
              暂无结果。试试贴一行歌单（如 Butter-Fly），再点「干跑计划」。
            </div>
          </div>
        </VSheet>

        <VSheet v-else class="paper-flat mt-2 pa-3 text-medium-emphasis text-body-2">
          贴歌单 → 「干跑计划」只看不下载；「一键加种」才会按计划加种
          （qB category=<code>音乐</code>、tag=<code>魔流-&lt;站&gt;-静默-资源</code>，自动进账本/静默/H&R/闸门/站点报表）。
        </VSheet>

        <p class="text-caption text-medium-emphasis mt-3 mb-0">
          <strong>判定（命中逻辑）：</strong>
          <span v-if="result && result.policy">
            {{ result.policy.search }} · {{ result.policy.exclude }} · {{ result.policy.score }}。
          </span>
          <span v-else>
            歌单逐行 MP 搜索（mtype=music，仅指定站点）→ 硬过滤视频/MV/录像 → 打分（无损+40/有损+8/高解析+15/分轨+5/免费+20/2x+5/做种折算0~10/体积+5）→ 选中并列取做种多。
          </span>
        </p>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根 / 标题行：随「音乐薄弹窗」自 index.vue 迁入。
     下列共享选择器（magicflow-dialog / settings-dialog__head / recommend-dialog__head-actions /
     panel / panel__head / table-empty）父页其它弹窗也在用 → 两处各留一份（纯复制，零改动）。── */
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

/* ── 音乐薄弹窗（15.8.2）──────────────────────────────────────────── */
.magicflow-music-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.magicflow-music-items { display: flex; flex-direction: column; gap: 6px; }
.magicflow-music-item {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: rgba(var(--v-theme-surface), 0.4);
}
.magicflow-music-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: space-between;
}
.magicflow-music-item__head > strong {
  font-weight: 600;
  overflow-wrap: anywhere;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-inline-size: 0;
}
.magicflow-music-item__body { display: flex; flex-direction: column; gap: 2px; min-inline-size: 0; }
.magicflow-music-item__body .text-body-2 { overflow-wrap: anywhere; }

@media (max-width: 699px) {
  .magicflow-panel { padding: 14px; }
  .magicflow-panel__head { flex-wrap: wrap; flex-direction: column; align-items: flex-start; }
}
</style>
