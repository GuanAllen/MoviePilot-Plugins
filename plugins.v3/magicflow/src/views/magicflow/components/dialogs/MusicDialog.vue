<script setup>
// MagicFlow 前端 · 音乐弹窗
// ★ 2026-10-10 批2：清单视图（与点播同构）。
// ★ 19.12.87（移动端改版，稿见 _design_mobile/music-mobile.html）：
//   1. 窄屏走全屏：输入框 → 「全部站点」摘要行（默认收起）→ 全宽「搜索」；
//   2. 候选**只勾选**，下载走底部吸底「一并下载」（原来是逐行「下这条」）；
//   3. 清单改纵向分段：进行中卡片 → 已完成按「要不要你动手」分组（失败 / 待入库 / 已入库 / 种子已不在）；
//   4. 删掉「相关度 / score」并列与底部内部路由说明（那是给开发看的）。
//   数据向下（defineModel / props）、事件向上（emit）。
import { computed, ref } from 'vue'
import { tsText } from '../../format'
import {
  odPct, odSpeed, odEtaText, odStageColor, odIsPaused,
} from '../../composables/useOndemand'

const musicOpen = defineModel({ type: Boolean, default: false })
// 兼容旧绑定（index.vue 仍传 v-model:tab）；新结构是纵向分段，不再渲染 chip。
const musicTab = defineModel('tab', { type: String, default: 'inflight' })
const musicMsg = defineModel('msg', { type: String, default: '' })
const musicQuery = defineModel('query', { type: String, default: '' })
const musicSiteIds = defineModel('siteIds', { type: Array, default: () => [] })

// ★ 19.12.87：后 8 个 props 是移动端改版新增（勾选/分页/已完成分组）
const props = defineProps({
  musicInflight: { type: Array, default: () => [] },
  musicHistory: { type: Array, default: () => [] },
  musicItemsBusy: { type: Boolean, default: false },
  musicActing: { type: String, default: '' },
  musicImporting: { type: String, default: '' },
  musicSearching: { type: Boolean, default: false },
  musicCandidates: { type: Array, default: () => [] },
  musicResult: { type: Object, default: null },
  musicDownloading: { type: String, default: '' },
  siteSelectItems: { type: Array, default: () => [] },
  narrow: { type: Boolean, default: false },
  musicPicked: { type: Array, default: () => [] },
  musicBatchBusy: { type: Boolean, default: false },
  musicTotal: { type: Number, default: 0 },
  musicPending: { type: Array, default: () => [] },
  musicBroken: { type: Array, default: () => [] },
  musicInLibrary: { type: Array, default: () => [] },
  musicGone: { type: Array, default: () => [] },
  musicHasMore: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh-items', 'act', 'search', 'download', 'import',
  'toggle-pick', 'pick-all', 'download-picked', 'load-more'])

const advOpen = ref(false)
const showLib = ref(false)
const showGone = ref(false)

const siteSummary = computed(() => {
  const n = (props.musicSiteIds || []).length
  return n ? `只在 ${n} 个站点` : '全部站点'
})

const doneCount = computed(() => (props.musicTotal || 0) - props.musicInflight.length)

const pickedSize = computed(() => {
  const set = new Set(props.musicPicked || [])
  let gb = 0
  for (const c of props.musicCandidates || []) {
    if (c && set.has(String(c.cid))) gb += Number(c.size_gb || 0)
  }
  return gb
})

const allPicked = computed(() => {
  const ok = (props.musicCandidates || []).filter((c) => c && !c.excluded && c.cid)
  return ok.length > 0 && ok.every((c) => (props.musicPicked || []).includes(String(c.cid)))
})

/** 从标题里抽音质（纯前端，不改后端） */
function qualityOf(title) {
  const t = String(title || '').toUpperCase()
  if (/HI-?RES|24BIT|DSD|DSF/.test(t)) return 'Hi-Res'
  if (/FLAC|APE|WAV|ALAC|整轨/.test(t)) return 'FLAC'
  if (/320\s*K/.test(t)) return '320K'
  if (/V0|V2|MP3|AAC|M4A/.test(t)) return 'MP3'
  return ''
}

function sizeText(c) {
  const gb = Number(c?.size_gb || 0)
  if (!gb) return '体积未知'
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${Math.round(gb * 1024)} MB`
}

function rowSize(row) {
  const gb = Number(row?.size_gb || 0)
  if (!gb) return ''
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${Math.round(gb * 1024)} MB`
}

/** 第一首未被过滤的候选 = 匹配度最高（后端已排序） */
const topCid = computed(() => {
  const c = (props.musicCandidates || []).find((x) => x && !x.excluded)
  return c ? String(c.cid) : ''
})

function loadMusicItems() { emit('refresh-items') }
function actMusic(row, action) { emit('act', row, action) }
function runMusicSearch() { emit('search') }
function importMusic(row) { emit('import', row) }
function togglePick(cid) { emit('toggle-pick', cid) }
function pickAll() { emit('pick-all') }
function downloadPicked() { emit('download-picked') }
function loadMore() { emit('load-more') }

/** 「全部暂停」只暂停**在跑的那些** —— 混合暂停/继续会把已暂停的又拉起来 */
function pauseAll() {
  ;(props.musicInflight || []).filter((r) => r && !odIsPaused(r)).forEach((r) => actMusic(r, 'pause'))
}

/** 入库状态的短说明（对用户说人话） */
function importHint(row) {
  const st = String(row?.import_state || '')
  if (st === 'failed') return row?.import_reason ? `上次没入成：${row.import_reason}` : '上次入库没成功'
  if (st === 'partial') return `上次入了 ${row?.import_failed || 0} 首失败`
  if (st === 'running') return '正在入库…'
  return ''
}
</script>

<template>
  <VDialog v-model="musicOpen" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-music-dialog">
      <header class="magicflow-settings-dialog__head">
        <div class="mf-head__main">
          <span class="magicflow-settings-dialog__title">音乐</span>
          <span v-if="musicTotal" class="mf-head__sub">
            {{ musicInflight.length }} 进行中 · {{ doneCount }} 已完成
          </span>
        </div>
        <div class="magicflow-recommend-dialog__head-actions">
          <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="musicOpen = false" />
        </div>
      </header>
      <VDivider />

      <VCardText class="magicflow-music-dialog__body" :class="{ 'is-dock': narrow && musicPicked.length }">
        <!-- ── 搜索 ─────────────────────────────────────────── -->
        <div class="mf-search">
          <!-- 窄屏：输入框 → 摘要行 → 全宽主按钮 -->
          <template v-if="narrow">
            <VTextField
              v-model="musicQuery"
              class="mf-q"
              variant="outlined"
              density="comfortable"
              hide-details
              placeholder="歌名 / 艺人"
              prepend-inner-icon="mdi-magnify"
              @keyup.enter="runMusicSearch"
            />
            <button type="button" class="mf-sum" :aria-expanded="advOpen" @click="advOpen = !advOpen">
              <span class="mf-sum__txt">{{ siteSummary }}</span>
              <VIcon size="18" :class="{ 'mf-rot': advOpen }">mdi-chevron-down</VIcon>
            </button>
            <div v-if="advOpen" class="mf-adv">
              <VSelect
                v-model="musicSiteIds"
                :items="siteSelectItems"
                label="只在"
                multiple
                chips
                closable-chips
                density="comfortable"
                hide-details
              />
            </div>
            <VBtn
              block
              size="large"
              color="primary"
              class="mf-go"
              :loading="musicSearching"
              @click="runMusicSearch"
            >搜索</VBtn>
          </template>

          <!-- 桌面：保持三列 -->
          <div v-else class="magicflow-music-search__row">
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
              prepend-icon="mdi-magnify"
              :loading="musicSearching"
              @click="runMusicSearch"
            >搜索</VBtn>
          </div>
        </div>

        <!-- ── 候选（勾选，不逐条下）────────────────────────── -->
        <div v-if="musicCandidates.length" class="mf-cands">
          <div class="mf-cands__head">
            <span>候选 {{ musicCandidates.length }} · 按匹配度</span>
            <button type="button" class="mf-link" @click="pickAll">{{ allPicked ? '取消全选' : '全选' }}</button>
          </div>
          <label
            v-for="c in musicCandidates"
            :key="c.cid"
            class="mf-cand"
            :class="{ 'is-on': musicPicked.includes(String(c.cid)), 'is-off': c.excluded }"
          >
            <input
              type="checkbox"
              class="mf-cand__cb"
              :checked="musicPicked.includes(String(c.cid))"
              :disabled="c.excluded"
              @change="togglePick(c.cid)"
            >
            <span class="mf-box" aria-hidden="true">
              <VIcon v-if="musicPicked.includes(String(c.cid))" size="15">mdi-check</VIcon>
            </span>
            <span class="mf-cand__body">
              <span class="mf-cand__title">{{ c.title || '(无标题)' }}</span>
              <span class="mf-cand__sub">{{ sizeText(c) }} · 做种 {{ c.seeders }}</span>
              <span class="mf-cand__tags">
                <span v-if="String(c.cid) === topCid" class="mf-t mf-t--rec">匹配度最高</span>
                <span class="mf-t mf-t--site">{{ c.site_name || ('站 ' + c.site) }}</span>
                <span v-if="c.free" class="mf-t mf-t--free">免费</span>
                <span v-if="c.hit_and_run" class="mf-t mf-t--hr">H&amp;R</span>
                <span v-if="qualityOf(c.title)" class="mf-t mf-t--q">{{ qualityOf(c.title) }}</span>
                <span v-if="c.excluded" class="mf-t mf-t--dim">已过滤：{{ c.exclude_reason || '不适配' }}</span>
              </span>
            </span>
          </label>
        </div>
        <div v-else-if="musicResult" class="mf-nores">
          没搜到候选（站点 {{ (musicResult.sites || []).join('、') || '—' }}）。换个关键词或站点。
        </div>

        <!-- ── 消息 ─────────────────────────────────────────── -->
        <VAlert
          v-if="musicMsg"
          :type="String(musicMsg).startsWith('❌') ? 'warning' : 'info'"
          variant="tonal"
          density="compact"
          closable
          class="mt-3 mb-1"
          @click:close="musicMsg = ''"
        >{{ musicMsg }}</VAlert>

        <!-- ── 进行中 ───────────────────────────────────────── -->
        <div class="mf-sec">
          <h3>进行中</h3><span class="n">{{ musicInflight.length }}</span>
          <button v-if="musicInflight.length > 1" type="button" class="mf-sec__act" @click="pauseAll">
            全部暂停
          </button>
        </div>
        <p v-if="!musicInflight.length" class="mf-empty">
          <b>现在没有在下的音乐</b>
          上面搜一首就能开始
        </p>
        <article v-for="row in musicInflight" :key="'m-i-' + row.hash" class="mf-card">
          <div class="mf-card__title" :title="row.title">{{ row.title || row.hash.slice(0, 12) }}</div>
          <div class="mf-card__sub">
            <span v-if="rowSize(row)">{{ rowSize(row) }}</span>
            <span v-if="row.site" class="mf-dot" /><span v-if="row.site">{{ row.site }}</span>
            <span v-if="row.free" class="mf-t mf-t--free">免费</span>
            <span v-if="row.hit_and_run" class="mf-t mf-t--hr">H&amp;R</span>
          </div>
          <VProgressLinear
            :model-value="odPct(row)"
            height="6"
            rounded
            :color="odIsPaused(row) ? 'warning' : (row.stage === 'downloading' ? 'primary' : 'success')"
            class="mt-2"
          />
          <div class="mf-card__foot">
            <span class="strong">
              <template v-if="row.stage === 'settling'">已下完 · 等入库</template>
              <template v-else-if="odIsPaused(row)">已暂停</template>
              <template v-else>{{ odEtaText(row.eta_s) || '—' }}</template>
            </span>
            <span v-if="row.stage === 'downloading' && !odIsPaused(row)" class="mf-dot" />
            <span v-if="row.stage === 'downloading' && !odIsPaused(row)">{{ odPct(row).toFixed(1) }}%</span>
            <span v-if="row.stage === 'downloading' && !odIsPaused(row) && row.speed" class="mf-dot" />
            <span v-if="row.stage === 'downloading' && !odIsPaused(row) && row.speed">{{ odSpeed(row.speed) }}</span>
            <VSpacer />
            <VBtn
              v-if="!odIsPaused(row)"
              size="small"
              variant="tonal"
              :loading="musicActing === row.hash + ':pause'"
              @click="actMusic(row, 'pause')"
            >暂停</VBtn>
            <VBtn
              v-else
              size="small"
              variant="tonal"
              color="primary"
              :loading="musicActing === row.hash + ':resume'"
              @click="actMusic(row, 'resume')"
            >继续</VBtn>
            <VBtn
              size="small"
              variant="text"
              color="error"
              :loading="musicActing === row.hash + ':remove'"
              @click="actMusic(row, 'remove')"
            >移除</VBtn>
          </div>
        </article>

        <!-- ── 已完成 ───────────────────────────────────────── -->
        <div class="mf-sec">
          <h3>已完成</h3><span class="n">{{ musicTotal ? doneCount : musicHistory.length }}</span>
          <button type="button" class="mf-sec__act" :disabled="musicItemsBusy" @click="loadMusicItems">
            {{ musicItemsBusy ? '刷新中…' : '刷新' }}
          </button>
        </div>

        <!-- 失败：唯一必须人动手的 -->
        <template v-if="musicBroken.length">
          <div class="mf-grp"><span>入库没成功</span><span class="gn">{{ musicBroken.length }}</span>
            <span class="why">重试一下，或看原因</span></div>
          <div v-for="row in musicBroken" :key="'m-b-' + row.hash" class="mf-line">
            <div class="t">
              <b :title="row.title">{{ row.title || row.hash.slice(0, 12) }}</b>
              <span>{{ rowSize(row) }}<template v-if="row.site"> · {{ row.site }}</template> · {{ importHint(row) }}</span>
            </div>
            <VBtn
              size="small"
              variant="tonal"
              color="primary"
              :loading="musicImporting === row.hash"
              @click="importMusic(row)"
            >重试</VBtn>
          </div>
        </template>

        <!-- 待入库 -->
        <template v-if="musicPending.length">
          <div class="mf-grp"><span>待入库</span><span class="gn">{{ musicPending.length }}</span>
            <span class="why">下完了，还没进音乐库</span></div>
          <div v-for="row in musicPending" :key="'m-p-' + row.hash" class="mf-line">
            <div class="t">
              <b :title="row.title">{{ row.title || row.hash.slice(0, 12) }}</b>
              <span>{{ rowSize(row) }}<template v-if="row.site"> · {{ row.site }}</template></span>
            </div>
            <VBtn
              size="small"
              variant="tonal"
              color="primary"
              :loading="musicImporting === row.hash"
              :title="'读标签 → 进音乐库 → 触发媒体库扫描'"
              @click="importMusic(row)"
            >入库</VBtn>
          </div>
        </template>

        <!-- 已入库（折叠，不占版面） -->
        <template v-if="musicInLibrary.length">
          <button type="button" class="mf-fold" @click="showLib = !showLib">
            <span>已入库 {{ musicInLibrary.length }} 首</span>
            <VIcon size="18" :class="{ 'mf-rot': showLib }">mdi-chevron-down</VIcon>
          </button>
          <template v-if="showLib">
            <div v-for="row in musicInLibrary" :key="'m-l-' + row.hash" class="mf-line mf-line--dim">
              <div class="t">
                <b :title="row.title">{{ row.title || row.hash.slice(0, 12) }}</b>
                <span>{{ rowSize(row) }}<template v-if="row.site"> · {{ row.site }}</template>
                  <template v-if="row.added_at"> · {{ tsText(row.added_at) }}</template></span>
              </div>
            </div>
          </template>
        </template>

        <!-- 种子已不在（只能看，不给删） -->
        <template v-if="musicGone.length">
          <button type="button" class="mf-fold" @click="showGone = !showGone">
            <span>种子已不在 {{ musicGone.length }} 首</span>
            <VIcon size="18" :class="{ 'mf-rot': showGone }">mdi-chevron-down</VIcon>
          </button>
          <template v-if="showGone">
            <div v-for="row in musicGone" :key="'m-g-' + row.hash" class="mf-line mf-line--dim">
              <div class="t">
                <b :title="row.title">{{ row.title || row.hash.slice(0, 12) }}</b>
                <span>{{ rowSize(row) }}<template v-if="row.site"> · {{ row.site }}</template> · 下载器里已经没有了</span>
              </div>
            </div>
          </template>
        </template>

        <p v-if="!musicHistory.length && !musicInflight.length" class="mf-empty mf-empty--quiet">
          还没有下过音乐。
        </p>

        <div v-if="musicHasMore" class="mf-more">
          <VBtn variant="tonal" size="small" :loading="musicItemsBusy" @click="loadMore">
            加载更多（已显示 {{ musicInflight.length + musicHistory.length }} / {{ musicTotal }}）
          </VBtn>
        </div>
      </VCardText>

      <!-- ── 吸底：勾选后的唯一出口 ─────────────────────────── -->
      <div v-if="narrow && musicPicked.length" class="mf-dock">
        <div class="mf-dock__cnt">
          <b>已选 {{ musicPicked.length }} 首</b>
          <span v-if="pickedSize">约 {{ pickedSize >= 1 ? pickedSize.toFixed(1) + ' GB' : Math.round(pickedSize * 1024) + ' MB' }}</span>
        </div>
        <VBtn color="primary" size="large" :loading="musicBatchBusy" @click="downloadPicked">一并下载</VBtn>
      </div>
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
  flex: 0 0 auto;
}
.magicflow-settings-dialog__head i { color: rgba(var(--v-theme-on-surface), 0.9); }
.magicflow-settings-dialog__title { font-size: 1.05rem; font-weight: 600; }
.magicflow-recommend-dialog__head-actions { display: flex; align-items: center; gap: 4px; }
.mf-head__main { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.mf-head__sub { font-size: 0.74rem; opacity: 0.6; white-space: nowrap; }

/* ── 弹窗骨架 ─────────────────────────────────────────────── */
.magicflow-music-dialog {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  max-block-size: 92vh;
  overflow: hidden;
  position: relative;
}
.magicflow-music-dialog__body { padding: 10px 18px 24px; overflow: auto; flex: 1 1 auto; min-height: 0; }
.magicflow-music-dialog__body.is-dock { padding-bottom: 96px; }

/* ── 搜索 ─────────────────────────────────────────────────── */
.mf-search { margin-bottom: 12px; }
.magicflow-music-search__row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.magicflow-music-search__row > .v-input:first-child { flex: 1 1 16rem; }
.magicflow-music-search__row > .v-input:nth-child(2) { flex: 1 1 12rem; max-width: 22rem; }

.mf-q { margin-bottom: 2px; }
.mf-sum {
  display: flex; align-items: center; gap: 6px; width: 100%;
  min-height: 44px; padding: 0 2px; border: 0; background: none; cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.62); font-size: 0.82rem; text-align: left;
}
.mf-sum__txt { color: rgba(var(--v-theme-on-surface), 0.9); }
.mf-sum i { margin-left: auto; opacity: 0.5; transition: transform 0.18s; }
.mf-adv { padding: 2px 0 10px; }
.mf-go { margin-top: 4px; }

/* ── 候选 ─────────────────────────────────────────────────── */
.mf-cands { display: flex; flex-direction: column; margin: 6px 0 4px; }
.mf-cands__head {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.76rem; opacity: 0.75; padding: 6px 2px;
}
.mf-link {
  margin-left: auto; border: 0; background: none; cursor: pointer;
  color: rgb(var(--v-theme-primary)); font-size: 0.78rem; padding: 8px 4px;
}
.mf-cand {
  position: relative; display: flex; gap: 10px; align-items: flex-start;
  padding: 12px 2px; border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  cursor: pointer;
}
.mf-cand:first-of-type { border-top: none; }
.mf-cand__cb { position: absolute; opacity: 0; width: 1px; height: 1px; }
.mf-box {
  flex: 0 0 22px; width: 22px; height: 22px; margin-top: 1px; border-radius: 6px;
  border: 1.5px solid rgba(var(--v-theme-on-surface), 0.3);
  display: grid; place-items: center; color: #fff;
}
.mf-cand.is-on .mf-box { background: rgb(var(--v-theme-primary)); border-color: rgb(var(--v-theme-primary)); }
.mf-cand.is-off { opacity: 0.5; }
.mf-cand__body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.mf-cand__title {
  font-size: 0.9rem; font-weight: 550; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.mf-cand__sub { font-size: 0.78rem; opacity: 0.7; }
.mf-cand__tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
.mf-t {
  font-size: 0.7rem; line-height: 1; padding: 5px 7px; border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.72); white-space: nowrap;
}
.mf-t--site { background: rgba(var(--v-theme-primary), 0.1); color: rgb(var(--v-theme-primary)); }
.mf-t--free { background: rgba(var(--v-theme-success), 0.14); color: rgb(var(--v-theme-success)); }
.mf-t--hr { background: rgba(var(--v-theme-warning), 0.16); color: rgb(var(--v-theme-warning)); }
.mf-t--rec { background: rgb(var(--v-theme-primary)); color: #fff; font-weight: 600; }
.mf-t--q { background: rgba(var(--v-theme-primary), 0.16); color: rgb(var(--v-theme-primary)); font-weight: 600; }
.mf-t--dim { color: rgba(var(--v-theme-on-surface), 0.5); }
.mf-nores { font-size: 0.8rem; opacity: 0.7; padding: 8px 2px; }

/* ── 分段标题 ─────────────────────────────────────────────── */
.mf-sec { display: flex; align-items: center; gap: 8px; margin: 22px 0 8px; }
.mf-sec h3 { margin: 0; font-size: 0.8rem; font-weight: 600; opacity: 0.7; letter-spacing: 0.02em; }
.mf-sec .n { font-size: 0.74rem; opacity: 0.45; font-variant-numeric: tabular-nums; }
.mf-sec__act {
  margin-left: auto; border: 0; background: none; cursor: pointer;
  color: rgb(var(--v-theme-primary)); font-size: 0.78rem; min-height: 44px; padding: 0 4px;
}
.mf-sec__act[disabled] { opacity: 0.4; cursor: default; }

/* ── 空状态 ───────────────────────────────────────────────── */
.mf-empty {
  margin: 0; padding: 22px 12px; text-align: center; font-size: 0.82rem; line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.42);
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.14); border-radius: 12px;
}
.mf-empty b { display: block; font-size: 0.88rem; font-weight: 550; color: rgba(var(--v-theme-on-surface), 0.7); margin-bottom: 3px; }
.mf-empty--quiet { border: 0; padding: 18px 0; }

/* ── 进行中卡片 ───────────────────────────────────────────── */
.mf-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12); border-radius: 12px;
  padding: 12px 13px; background: rgba(var(--v-theme-on-surface), 0.02);
}
.mf-card + .mf-card { margin-top: 10px; }
.mf-card__title {
  font-size: 0.92rem; font-weight: 550; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.mf-card__sub {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-top: 3px; font-size: 0.78rem; opacity: 0.7;
}
.mf-card__foot { display: flex; align-items: center; gap: 6px; margin-top: 8px; font-size: 0.8rem; }
.mf-card__foot .strong { font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.92); }
.mf-dot { width: 2px; height: 2px; border-radius: 50%; background: rgba(var(--v-theme-on-surface), 0.4); display: inline-block; }

/* ── 已完成分组 ───────────────────────────────────────────── */
.mf-grp { display: flex; align-items: baseline; gap: 7px; margin: 14px 0 2px; }
.mf-grp span:first-child { font-size: 0.78rem; font-weight: 600; opacity: 0.75; }
.mf-grp .gn { font-size: 0.74rem; opacity: 0.45; }
.mf-grp .why { margin-left: auto; font-size: 0.72rem; opacity: 0.45; text-align: right; }
.mf-line {
  display: flex; align-items: center; gap: 10px; min-height: 56px;
  padding: 6px 0; border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}
.mf-line .t { flex: 1 1 auto; min-width: 0; }
.mf-line .t b {
  display: block; font-size: 0.86rem; font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mf-line .t span { font-size: 0.74rem; opacity: 0.5; }
.mf-line--dim .t b { color: rgba(var(--v-theme-on-surface), 0.65); }
.mf-fold {
  display: flex; align-items: center; justify-content: space-between; width: 100%;
  min-height: 48px; margin-top: 8px; padding: 0 2px;
  border: 0; border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  background: none; cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.6); font-size: 0.8rem;
}
.mf-fold i { opacity: 0.45; transition: transform 0.18s; }
.mf-more { display: flex; justify-content: center; padding: 16px 0 4px; }

/* ── 吸底条 ───────────────────────────────────────────────── */
.mf-dock {
  position: absolute; left: 0; right: 0; bottom: 0; z-index: 2;
  display: flex; align-items: center; gap: 12px;
  padding: 12px 18px calc(14px + env(safe-area-inset-bottom));
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: linear-gradient(to top, rgba(var(--v-theme-surface), 0.99) 62%, rgba(var(--v-theme-surface), 0.86));
  backdrop-filter: blur(12px);
}
.mf-dock__cnt { display: flex; flex-direction: column; gap: 1px; font-size: 0.76rem; opacity: 0.7; }
.mf-dock__cnt b { font-size: 0.92rem; opacity: 1; color: rgba(var(--v-theme-on-surface), 0.95); }
.mf-dock .v-btn { flex: 1 1 auto; }

.mf-rot { transform: rotate(180deg); }
</style>
