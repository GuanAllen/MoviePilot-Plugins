<script setup>
// MagicFlow 前端 · 功能中心（弹层）
// 定位：**全部功能入口的唯一落地页**。页头按设计稿只留「通知 / 设置 / 功能中心」三样，
// 原先散在页头的一排图标（推荐·云盘·跨站·豆瓣·健康·点播·考核·补源·站点报表）与
// 「更多 ⋮」菜单里的次级项（音乐·库内资源·后台任务·趋势·优化·计划·通知·认领·RSS·
// 静默池·H&R·容量·操作记录·新建任务·关闭）全部收进这里。
// 权责：数据向下（pages / badges）、事件向上（emit('open', page|key)），自身不直接调 api。
// ★ 样式全部自带：父级 index.vue 的 <style scoped> 不会命中子组件，别依赖它。
import { computed, ref } from 'vue'

const open = defineModel({ type: Boolean, default: false })

const props = defineProps({
  pages: { type: Array, default: () => [] }, // MF_PAGES（14 项，须与后端 FEATURES 对齐）
  narrow: { type: Boolean, default: false },
  badges: { type: Object, default: () => ({}) }, // 角标：recommend / exam / notify / jobs
})

const emit = defineEmits(['open'])

// 一句话说清「点进去能干什么」（卡片副标题）
const DESC = {
  ondemand: '片名 / 链接 → 选源下载',
  recommend: '按评分自动选种',
  exam: '新手考核进度与救急',
  signin: '各站点一键签到',
  cloud: '本地 → 云盘归档',
  douban: '库容量与评分源',
  crossseed: '已有资源去他站落户',
  claim: '发布站认领种子',
  rss: '订阅自动下载',
  silent: '静默池按站点托管',
  sitereport: '站点维度汇总报表',
  hrbills: 'H&R 欠种与临期',
  ceiling: '站点魔力容量水位',
  ops: '全站操作流水',
  settings: '插件参数与开关',
  assets: '删除 / 保护 / 订阅 / 整理 / 刮削',
  music: '清单：进行中 / 已完成',
  rescue: '停滞欠 H&R → 他站补种',
  jobs: '整理入库 / 订阅 / 刮削 进度',
  trend: '时魔走向与拐点归因',
  optimize: '体积预算内保谁删谁',
  plan: '计划 → 干跑 → 批准执行',
  notify: 'H&R 临期 / 容量红线 / 产出骤降',
  health: '各子系统自检与一键修复',
  create: '选站点、定模式、开跑',
  close: '退出 MagicFlow 插件页',
}

// ★ 次级入口：不在后端 FEATURES 里（塞进 MF_PAGES 会让 preflight 5/17 前后端对齐挂掉），
//   但它们本就是这个「功能中心」该有的格子 —— 原先只藏在顶栏图标与「更多」菜单里。
const EXTRA_PAGES = [
  { key: 'ondemand', label: '点播', icon: 'mdi-cloud-download-outline', scope: 'global' },
  { key: 'health', label: '健康自检', icon: 'mdi-heart-pulse', scope: 'global' },
  { key: 'assets', label: '库内资源管理', icon: 'mdi-folder-cog-outline', scope: 'global' },
  { key: 'music', label: '音乐', icon: 'mdi-music-circle-outline', scope: 'global' },
  { key: 'rescue', label: '死种补源', icon: 'mdi-lifebuoy', scope: 'global' },
  { key: 'jobs', label: '后台任务', icon: 'mdi-progress-clock', scope: 'view' },
  { key: 'trend', label: '魔力趋势', icon: 'mdi-chart-timeline-variant', scope: 'view' },
  { key: 'optimize', label: '组合优化', icon: 'mdi-chart-timeline-variant-shimmer', scope: 'view' },
  { key: 'plan', label: 'AI 计划审批', icon: 'mdi-clipboard-check-outline', scope: 'view' },
  { key: 'notify', label: '事件通知', icon: 'mdi-bell-ring-outline', scope: 'view' },
]

// 页头级主操作：新建任务（原来在页头那颗实心按钮，收进这里当第一格）
const CREATE_PAGE = { key: 'create', label: '新建任务', icon: 'mdi-plus', scope: 'action' }
// 页头原先的 ✕：设计稿没有它，但功能不能丢 —— 放进「配置」组
const CLOSE_PAGE = { key: 'close', label: '关闭插件页', icon: 'mdi-close', scope: 'settings' }

const q = ref('')

const allPages = computed(() => {
  const seen = new Set()
  const out = []
  for (const p of [...(props.pages || []), ...EXTRA_PAGES]) {
    if (!p || !p.key || seen.has(p.key)) continue
    seen.add(p.key)
    out.push(p)
  }
  return out
})

const groups = computed(() => {
  const list = allPages.value
  const out = [
    { key: 'global', title: '常用功能', hint: '插件级单例', items: list.filter(p => p.scope === 'global' && p.key !== 'settings') },
    { key: 'view', title: '报表与工具', hint: '只读汇总 / 诊断 / 审批', items: list.filter(p => p.scope === 'view') },
    { key: 'settings', title: '配置', hint: '', items: [...list.filter(p => p.key === 'settings'), CLOSE_PAGE] },
  ]
  return out.filter(g => g.items.length)
})

// 搜索：命中名称或说明即保留（组标题保留，空组丢弃）
const kw = computed(() => String(q.value || '').trim().toLowerCase())
const filteredGroups = computed(() => {
  const k = kw.value
  if (!k) return groups.value
  return groups.value
    .map(g => ({
      ...g,
      items: g.items.filter(p => (`${p.label || ''} ${DESC[p.key] || ''} ${p.key}`).toLowerCase().includes(k)),
    }))
    .filter(g => g.items.length)
})

const total = computed(() => allPages.value.length + 1)

// ★ 模板只能用「本文件显式声明过的标识符」（preflight 13/17 守卫）：props 字段要包一层再到模板用
const isFullscreen = computed(() => !!props.narrow)
const badgeMap = computed(() => props.badges || {})
function badgeFor(key) {
  const v = Number((badgeMap.value || {})[key] || 0)
  return Number.isFinite(v) && v > 0 ? v : 0
}

function pick(page) {
  open.value = false
  emit('open', page)
}
</script>

<template>
  <VDialog v-model="open" max-width="60rem" scrollable :fullscreen="isFullscreen">
    <VCard class="mfhub">
      <header class="mfhub__head">
        <span class="mfhub__title">功能中心</span>
        <VChip size="x-small" color="grey" variant="tonal">{{ total }} 个入口</VChip>
        <span class="mfhub__spacer" />
        <label class="mfhub__search">
          <VIcon icon="mdi-magnify" size="16" />
          <input v-model="q" type="text" placeholder="搜索功能…" aria-label="搜索功能" />
          <button v-if="q" type="button" class="mfhub__search-clear" aria-label="清空" @click="q = ''">
            <VIcon icon="mdi-close-circle" size="14" />
          </button>
        </label>
        <VBtn icon="mdi-close" size="small" variant="text" aria-label="关闭" @click="open = false" />
      </header>

      <div class="mfhub__body">
        <!-- 主操作：新建任务（原页头实心按钮的落地） -->
        <button v-if="!kw" type="button" class="mfhub__primary" @click="pick(CREATE_PAGE)">
          <span class="mfhub__primary-icon"><VIcon icon="mdi-plus" size="20" /></span>
          <span class="mfhub__text">
            <strong>新建任务</strong>
            <em>选站点、定模式（做种 / 刷流）、开跑</em>
          </span>
          <VIcon icon="mdi-chevron-right" size="18" class="mfhub__primary-chev" />
        </button>

        <section v-for="g in filteredGroups" :key="g.key" class="mfhub__group">
          <div class="mfhub__group-head">
            <h3>{{ g.title }}</h3>
            <span v-if="g.hint">{{ g.hint }}</span>
          </div>
          <div class="mfhub__grid">
            <button
              v-for="p in g.items"
              :key="p.key"
              type="button"
              class="mfhub__card"
              @click="pick(p)"
            >
              <VIcon :icon="p.icon" size="20" class="mfhub__icon" />
              <span class="mfhub__text">
                <strong>{{ p.label }}</strong>
                <em>{{ DESC[p.key] || '' }}</em>
              </span>
              <VChip v-if="badgeFor(p.key)" size="x-small" color="primary" variant="tonal" class="mfhub__badge">
                {{ badgeFor(p.key) }}
              </VChip>
              <VIcon icon="mdi-chevron-right" size="18" class="mfhub__chev" />
            </button>
          </div>
        </section>
        <p v-if="!filteredGroups.length" class="mfhub__empty">没有匹配的功能</p>
      </div>
    </VCard>
  </VDialog>
</template>

<style scoped>
.mfhub {
  display: flex;
  flex-direction: column;
  max-height: min(84vh, 900px);
}

.mfhub__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 18px 12px;
}

.mfhub__title {
  font-size: 1.05rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), .95);
}

.mfhub__spacer { flex: 1 1 auto; }

.mfhub__search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  block-size: 32px;
  padding: 0 8px;
  border-radius: 9px;
  border: 1px solid rgba(var(--v-theme-on-surface), .12);
  background: rgba(var(--v-theme-on-surface), .04);
  color: rgba(var(--v-theme-on-surface), .55);
}

.mfhub__search input {
  inline-size: 150px;
  border: 0;
  outline: none;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), .9);
  font-size: 12.5px;
}

.mfhub__search-clear {
  display: inline-flex;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.mfhub__body {
  padding: 2px 18px 20px;
  overflow: auto;
  flex: 1 1 auto;
  min-height: 0;
}

.mfhub__primary {
  display: flex;
  align-items: center;
  gap: 12px;
  inline-size: 100%;
  padding: 13px 14px;
  margin-block-end: 16px;
  text-align: left;
  border: 1px solid rgba(var(--v-theme-primary), .45);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(var(--v-theme-primary), .22), rgba(var(--v-theme-primary), .08));
  color: inherit;
  cursor: pointer;
  transition: border-color .16s ease, transform .16s ease;
}

.mfhub__primary:hover {
  border-color: rgba(var(--v-theme-primary), .7);
  transform: translateY(-1px);
}

.mfhub__primary-icon {
  display: grid;
  place-items: center;
  inline-size: 34px;
  block-size: 34px;
  flex: none;
  border-radius: 10px;
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}

.mfhub__primary .mfhub__text strong { font-size: 14px; }

.mfhub__primary-chev { color: rgba(var(--v-theme-on-primary), .7); flex: none; }

.mfhub__group + .mfhub__group {
  margin-top: 18px;
}

.mfhub__group-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
}

.mfhub__group-head h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .02em;
  color: rgba(var(--v-theme-on-surface), .92);
}

.mfhub__group-head span {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), .48);
}

.mfhub__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(228px, 1fr));
  gap: 10px;
}

.mfhub__card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  text-align: left;
  border-radius: 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), .1);
  background: rgba(var(--v-theme-on-surface), .03);
  color: inherit;
  cursor: pointer;
  transition: border-color .16s ease, background .16s ease, transform .16s ease;
}

.mfhub__card:hover {
  border-color: rgba(var(--v-theme-primary), .45);
  background: rgba(var(--v-theme-primary), .1);
  transform: translateY(-1px);
}

.mfhub__icon {
  color: rgb(var(--v-theme-primary));
  flex: none;
}

.mfhub__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.mfhub__text strong {
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), .94);
}

.mfhub__text em {
  font-style: normal;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), .52);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mfhub__badge { flex: none; }

.mfhub__chev {
  color: rgba(var(--v-theme-on-surface), .3);
  flex: none;
}

.mfhub__empty {
  margin: 12px 0;
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), .5);
}

@media (max-width: 599px) {
  .mfhub__grid {
    grid-template-columns: 1fr;
  }

  .mfhub__search input { inline-size: 88px; }
}
</style>
