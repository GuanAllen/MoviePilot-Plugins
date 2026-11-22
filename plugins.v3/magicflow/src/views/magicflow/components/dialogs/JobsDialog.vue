<script setup>
// MagicFlow 前端 · 后台任务队列弹窗（★ 15.10.0）
// 数据向下、事件向上：本组件只渲染 + emit('refresh' / 'clear' / 'retry' / 'update:modelValue')。
// ★ 19.12.98：加「批次汇总」—— 一次批量一行，数字能加回总数（total = 成功+失败+进行中，
//   失败再拆「可重试 / 不可重试」）；失败任务给「重试」按钮，重试口径全部由后端判定。
import { computed } from 'vue'
import { formatDateTime } from '../../../../utils'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobs: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
  batches: { type: Array, default: () => [] },
  narrow: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'refresh', 'clear', 'retry'])

const open = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const STATUS = {
  queued: { text: '排队中', color: 'amber' },
  running: { text: '执行中', color: 'primary' },
  done: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
}
function statusMeta(status) {
  return STATUS[String(status ?? '')] || { text: String(status ?? '未知'), color: 'grey' }
}
function duration(job) {
  const s = Number(job?.started ?? 0)
  const f = Number(job?.finished ?? 0)
  if (!s) return ''
  const end = f || (Date.now() / 1000)
  const d = Math.max(0, end - s)
  return d < 60 ? `${d.toFixed(0)} 秒` : `${(d / 60).toFixed(1)} 分`
}
const running = computed(
  () => Number(props.summary?.running ?? 0) + Number(props.summary?.queued ?? 0),
)
/** 批次里还在排/在跑的条数（对账用：total = done + failed + inflight）。 */
function inflight(b) {
  return Number(b?.queued ?? 0) + Number(b?.running ?? 0)
}

// ---------------------------------------------------------------- 19.12.99 窄屏可读性
// 手机上一个弹窗只有 390px 宽，而 job 的 title / message 里塞的是专辑名和绝对路径。
// 19.12.98 那两个字段是 `nowrap` + 尾部省略 —— 结果 `/media/电视剧/金色…` 只剩前缀，
// 「落到哪」这个唯一有用的信息正好被砍掉。这里三件事一起改：
//   1. 中间省略：保头（路径根 / 名字前缀）也保尾（集数、文件名），砍掉的是中段
//   2. message 允许折成两行（尾部省略在手机上真的不够用）
//   3. title 剥掉 kind 前缀 —— 「音乐入库」已经单独一格显示了，标题里再来一遍纯属浪费

/** 超过 limit 字就中间省略；limit=0 表示不裁（桌面宽度不需要）。 */
function clip(text, limit) {
  const t = String(text ?? '')
  if (!limit || t.length <= limit) return t
  // 尾部权重更高：最后那段通常是文件名 / 集数，比路径中段有用
  const tail = Math.max(10, Math.floor(limit * 0.58))
  const head = Math.max(8, limit - tail - 1)
  return `${t.slice(0, head)}…${t.slice(-tail)}`
}

/** 路径按「段」压：从头累加整段，装不下了才收口，末段（文件名）永远保留不裁。 */
function clipPath(p, max = 40) {
  const s = String(p || '')
  if (s.length <= max) return s
  const lead = s.startsWith('/') ? '/' : ''
  const segs = s.split('/').filter(Boolean)
  if (segs.length <= 2) return s
  const last = segs[segs.length - 1]
  const headSegs = []
  for (const seg of segs.slice(0, segs.length - 1)) {
    const trial = `${lead}${[...headSegs, seg].join('/')}/…/${last}`
    if (headSegs.length && trial.length > max) break
    headSegs.push(seg)
  }
  return `${lead}${headSegs.join('/')}/…/${last}`
}

/**
 * 窄屏把 message 拆成 ≤2 行：短片段先并成一行，含路径的那段单独一行。
 * 桌面返回整段（由 CSS 折两行，不需要拆）。
 */
function msgLines(msg) {
  const t = String(msg ?? '').trim()
  if (!t || !props.narrow) return [t]
  const sep = t.includes('；') ? '；' : (t.includes(' · ') ? ' · ' : '')
  if (!sep) return [clip(t, 30)]
  const parts = t.split(sep).map(s => s.trim()).filter(Boolean)
  const lines = []
  for (const p of parts) {
    const prev = lines[lines.length - 1]
    // 路径段永远单独一行（并到前面的短句里必然被截掉）
    if (prev && !p.includes('/') && (prev.length + p.length + 1) <= 24) {
      lines[lines.length - 1] = `${prev}${sep.trim()}${p}`
    } else {
      lines.push(p)
    }
  }
  // 一行最多两条：多于两条时把后面的并起来（手机上 3 行消息太长）
  if (lines.length > 2) {
    return [lines[0], clipPath(lines.slice(1).join(sep.trim()))]
  }
  return lines.map(ln => (ln.includes('/') ? clipPath(ln) : clip(ln, 30)))
}

/** 标题去掉与 kind 重复的前缀，并把外层「」剥掉：`取消保护「再次奔向你」` → `再次奔向你`。 */
function titleText(job) {
  const t = String(job?.title ?? '')
  const k = String(job?.kind_text ?? '')
  if (!t || !k || !t.startsWith(k)) return t
  const rest = t.slice(k.length).trim()
  const m = rest.match(/^[「『"](.+)[」』"]$/)
  return (m ? m[1] : rest) || t
}

/** 窄屏只留时分（日期对「刚刚发生了什么」没意义），耗时保留。 */
function timeText(job) {
  const at = job.started || job.created
  const d = duration(job)
  let stamp = formatDateTime(at)
  if (props.narrow) {
    const raw = Number(at)
    const ms = raw < 1e12 ? raw * 1000 : raw   // 后端是秒，兼容毫秒
    const dt = new Date(ms)
    if (!Number.isNaN(dt.getTime())) {
      stamp = `${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`
    }
  }
  return d ? `${stamp} · ${d}` : stamp
}

/** 没有批次时（单条操作不编 batch）也给一行汇总，否则面板顶上空着像坏了。 */
const tally = computed(() => {
  const n = { done: 0, failed: 0, live: 0 }
  for (const j of props.jobs) {
    const s = String(j?.status ?? '')
    if (s === 'done') n.done += 1
    else if (s === 'failed') n.failed += 1
    else n.live += 1
  }
  return n
})
</script>

<template>
  <VDialog v-model="open" max-width="46rem" scrollable :fullscreen="narrow">
    <VCard class="magicflow-dialog magicflow-jobs-dialog">
      <VCardTitle class="d-flex align-center">
        <VIcon icon="mdi-progress-clock" class="me-2" />
        后台任务
        <VChip v-if="running" size="x-small" color="primary" variant="tonal" class="ms-2">{{ running }} 进行中</VChip>
        <VSpacer />
        <VBtn icon="mdi-refresh" variant="text" size="small" aria-label="刷新" @click="emit('refresh')" />
        <VBtn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="open = false" />
      </VCardTitle>
      <VDivider />
      <VCardText>
        <div class="text-body-2 text-medium-emphasis mb-2">
          慢动作（整理入库 / 订阅 / 刮削 / 批量删除）都在后台跑，<strong>关掉页面也会继续</strong>；这里看进度和结果。
        </div>

        <!-- ★ 19.12.98：批次汇总（一次批量一行；数字必须能加回总数） -->
        <template v-if="batches.length">
          <div class="magicflow-jobs-sec">
            批次汇总
            <span class="magicflow-jobs-sec__hint">共 = 成功 + 失败 + 进行中；失败再拆可重试 / 不可重试</span>
          </div>
          <div class="magicflow-jobs-batches">
            <div v-for="b in batches" :key="b.batch_id" class="magicflow-jobs-batch">
              <div class="magicflow-jobs-batch__head">
                <span class="magicflow-jobs-batch__kind">{{ b.kind_text || b.kind }}</span>
                <span class="magicflow-jobs-batch__time">{{ formatDateTime(b.created) }}</span>
                <VSpacer />
                <VBtn v-if="b.retryable > 0" size="x-small" variant="tonal" color="warning"
                      prepend-icon="mdi-replay" class="ms-2"
                      @click="emit('retry', { batch_id: b.batch_id })">
                  重试 {{ b.retryable }} 条
                </VBtn>
              </div>
              <div class="magicflow-jobs-batch__stats">
                <span>共 {{ b.total }}</span>
                <span class="is-ok">成功 {{ b.done }}</span>
                <span v-if="b.failed" class="is-bad">
                  失败 {{ b.failed }}<template v-if="b.dead">（不可重试 {{ b.dead }}）</template>
                </span>
                <span v-if="inflight(b)">进行中 {{ inflight(b) }}</span>
              </div>
            </div>
          </div>
        </template>

        <!-- ★ 19.12.99：单条操作不编批次 → 这里给一行极简汇总，免得面板顶部空着 -->
        <div v-if="!batches.length && jobs.length" class="magicflow-jobs-tally">
          <span>最近 {{ jobs.length }} 条</span>
          <span v-if="tally.done" class="is-ok">成功 {{ tally.done }}</span>
          <span v-if="tally.failed" class="is-bad">失败 {{ tally.failed }}</span>
          <span v-if="tally.live">进行中 {{ tally.live }}</span>
        </div>

        <div v-if="!jobs.length" class="magicflow-jobs-empty">还没有后台任务</div>
        <ul v-else class="magicflow-jobs">
          <li v-for="job in jobs" :key="job.id" :class="{ 'is-narrow': narrow }">
            <VChip class="magicflow-jobs__chip" size="small" variant="tonal"
                   :color="statusMeta(job.status).color">
              {{ statusMeta(job.status).text }}
            </VChip>
            <span class="magicflow-jobs__kind">{{ job.kind_text || job.kind }}</span>
            <span class="magicflow-jobs__time">{{ timeText(job) }}</span>
            <span class="magicflow-jobs__title" :title="job.title">{{ titleText(job) }}</span>
            <span v-if="job.message && job.message !== job.title" class="magicflow-jobs__msg"
                  :title="job.message">
              <template v-if="narrow">
                <span v-for="(ln, i) in msgLines(job.message)" :key="i"
                      class="magicflow-jobs__msgline">{{ ln }}</span>
              </template>
              <template v-else>{{ job.message }}</template>
            </span>
            <div v-if="job.retryable" class="magicflow-jobs__act">
              <VBtn size="x-small" variant="text" color="warning" prepend-icon="mdi-replay"
                    @click="emit('retry', { job_id: job.id })">重试</VBtn>
            </div>
          </li>
        </ul>
      </VCardText>
      <VDivider />
      <VCardActions>
        <VBtn size="small" variant="text" prepend-icon="mdi-broom" @click="emit('clear')">清理已完成</VBtn>
        <VSpacer />
        <VBtn size="small" variant="tonal" prepend-icon="mdi-refresh" @click="emit('refresh')">刷新</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.magicflow-jobs-sec {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 0.78rem;
  font-weight: 600;
  margin: 4px 0 6px;
}
.magicflow-jobs-sec__hint {
  font-weight: 400;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-jobs-batches {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}
.magicflow-jobs-batch {
  padding: 7px 9px;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgba(var(--v-theme-on-surface), 0.03);
  font-size: 0.8rem;
}
.magicflow-jobs-batch__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.magicflow-jobs-batch__kind {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.magicflow-jobs-batch__time {
  white-space: nowrap;
  font-size: 0.7rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-jobs-batch__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 3px;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
}
.magicflow-jobs-batch__stats .is-ok { color: rgb(var(--v-theme-success)); }
.magicflow-jobs-batch__stats .is-bad { color: rgb(var(--v-theme-error)); }
.magicflow-jobs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.magicflow-jobs li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 3px 8px;
  padding: 7px 9px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  font-size: 0.82rem;
}
.magicflow-jobs__chip { flex: 0 0 auto; }
.magicflow-jobs__kind {
  min-inline-size: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
}
.magicflow-jobs-tally {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin: 2px 0 8px;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
}
.magicflow-jobs-tally .is-ok { color: rgb(var(--v-theme-success)); }
.magicflow-jobs-tally .is-bad { color: rgb(var(--v-theme-error)); }
/* 标题仍单行（专辑名/剧名认得前缀），消息给两行 —— 尾部是「落到哪」，截不得 */
.magicflow-jobs__title {
  grid-column: 1 / -1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.87);
}
.magicflow-jobs__msg {
  grid-column: 1 / -1;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.35;
}
/* 窄屏：message 已被拆成 ≤2 段，每段一行、行内尾部省略（段内路径已按段压过） */
.magicflow-jobs li.is-narrow .magicflow-jobs__msg {
  display: block;
  -webkit-line-clamp: none;
  line-clamp: none;
}
.magicflow-jobs__msgline {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.magicflow-jobs__act {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  margin-block-start: -2px;
}
.magicflow-jobs__time {
  white-space: nowrap;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
.magicflow-jobs-empty {
  padding: 24px 8px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
@media (max-width: 600px) {
  /* ★ 19.12.99：时间不再单独占一行（原来 grid-column:1/-1 白吃掉一整行），
     改为留在第一行右侧、只显示时分 —— 一条任务从 4 行压到 3 行。 */
  .magicflow-jobs li { gap: 2px 6px; }
  .magicflow-jobs__kind { font-size: 0.76rem; }
  .magicflow-jobs__time { font-size: 0.68rem; }
}
</style>
