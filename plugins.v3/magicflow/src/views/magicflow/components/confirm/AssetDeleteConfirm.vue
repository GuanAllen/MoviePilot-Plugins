<script setup>
// MagicFlow 前端 · 库内资产手动强删确认弹窗
// 数据向下（defineModel / props）、事件向上（emit）；子组件不直接改父状态、不调父方法。
import { computed, ref, watch } from 'vue'

const open = defineModel({ type: Boolean, default: false })

const props = defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm'])

const deleteFiles = ref(true)

watch(open, (value) => {
  if (value) deleteFiles.value = true
})

const previewItems = computed(() => (props.items || []).slice(0, 10))
const moreCount = computed(() => Math.max(0, (props.items || []).length - 10))
const totalGb = computed(
  () => (props.items || []).reduce((sum, it) => sum + Number(it?.size_gb ?? 0), 0),
)
</script>

<template>
  <VDialog v-model="open" max-width="34rem">
    <VCard class="magicflow-dialog">
      <VCardTitle class="text-wrap">删除库内资产</VCardTitle>
      <VCardText class="text-body-2">
        确认强删选中的 <b>{{ (items || []).length }}</b> 个库内资产（合计 <b>{{ totalGb.toFixed(2) }}</b> GB）？
        <ul class="magicflow-asset-confirm-list">
          <li v-for="item in previewItems" :key="item.hash || item.title">
            <strong>{{ item.title || '未知种子' }}</strong>
            <span>{{ item.site ?? '' }} · {{ Number(item.size_gb ?? 0).toFixed(2) }} GB</span>
          </li>
        </ul>
        <div v-if="moreCount" class="magicflow-asset-confirm-more">等 {{ moreCount }} 条…</div>
      </VCardText>
      <VCardText class="magicflow-asset-confirm-warn">
        <p>① 这些是<b>已入库的库内资产</b>，默认永不删除，本次是手动强删。</p>
        <p>② 删除会<b>同时删除做种文件</b>（取决于下方勾选），文件删除不可恢复。</p>
        <p>③ 只突破「库内资产」这一道保护；手动保留 / 跨站来源份（H&amp;R 保种期）/ 已认领 / 欠 H&amp;R 仍会拦住。</p>
      </VCardText>
      <VCardText>
        <VCheckbox
          v-model="deleteFiles"
          color="error"
          density="compact"
          hide-details
          label="同时删除文件（不可恢复）"
        />
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="loading" @click="open = false">取消</VBtn>
        <VBtn
          color="error"
          variant="flat"
          :loading="loading"
          @click="emit('confirm', { deleteFiles })"
        >
          确认删除
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
/* ── 弹窗根：与同目录 confirm 组件同款（共享选择器 `.magicflow-dialog`）。
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

.magicflow-asset-confirm-list {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  max-block-size: 12rem;
  overflow-y: auto;
}

.magicflow-asset-confirm-list li {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-block: 4px;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.magicflow-asset-confirm-list li strong {
  overflow-wrap: anywhere;
}

.magicflow-asset-confirm-list li span {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.75rem;
}

.magicflow-asset-confirm-more {
  padding-block-start: 4px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.75rem;
}

.magicflow-asset-confirm-warn {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 0.8rem;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  background: rgba(var(--v-theme-error), 0.08);
  border-inline-start: 3px solid rgba(var(--v-theme-error), 0.5);
}

.magicflow-asset-confirm-warn p {
  margin: 0;
}

.magicflow-asset-confirm-warn p + p {
  margin-block-start: 4px;
}
</style>
