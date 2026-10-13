<template>
  <VDialog
    :model-value="modelValue"
    max-width="720"
    scrollable
    @update:model-value="v => emit('update:modelValue', v)"
  >
    <VCard class="mf-notify">
      <VCardTitle class="mf-notify__title">
        <VIcon icon="mdi-bell-ring-outline" size="20" class="me-2" />
        <span class="text-subtitle-1 font-weight-medium">事件通知</span>
        <VSpacer />
        <VBtn icon="mdi-refresh" variant="text" size="small" title="刷新" :loading="loading" @click="emit('refresh')" />
        <VBtn icon="mdi-close" variant="text" size="small" title="关闭" @click="emit('update:modelValue', false)" />
      </VCardTitle>
      <VDivider />

      <VCardText class="mf-notify__body">
        <div class="mf-notify__cfg">
          <VChip size="small" variant="tonal" :color="cfg.enabled ? 'primary' : 'grey'">
            {{ cfg.enabled ? '通知已开启' : '通知已关闭' }}
          </VChip>
          <VChip v-if="cfg.daily" size="small" variant="tonal" color="info">每日日报 {{ cfg.daily_hour }}:00</VChip>
          <VChip v-if="cfg.task_fail" size="small" variant="tonal" color="warning">任务失败</VChip>
          <VChip v-if="cfg.quiet" size="small" variant="tonal" color="grey">
            免打扰 {{ cfg.quiet }}{{ quietNow ? '（当前免打扰）' : '' }}
          </VChip>
        </div>
        <div class="mf-notify__thr">
          阈值：H&amp;R 提前 <strong>{{ cfg.hr_hours }}</strong> 小时 ·
          池盘 <strong>{{ cfg.capacity_pct }}%</strong> ·
          时魔骤降 <strong>{{ cfg.drop_pct }}%</strong>
          <span class="mf-notify__hint">（改阈值去「设置 → 通知」）</span>
        </div>

        <div class="mf-notify__acts">
          <VBtn size="small" variant="tonal" color="primary" prepend-icon="mdi-send-outline" @click="emit('act', 'test', '')">
            发送测试
          </VBtn>
          <VBtn size="small" variant="tonal" prepend-icon="mdi-radar" @click="emit('act', 'scan', '')">
            立即扫描
          </VBtn>
          <VBtn size="small" variant="text" color="grey" prepend-icon="mdi-delete-sweep-outline" @click="emit('act', 'clear', '')">
            清历史
          </VBtn>
        </div>

        <div class="mf-notify__list">
          <div v-if="!rows.length" class="mf-notify__empty">
            还没有事件。四类会推：H&amp;R 临期 · 池盘红线 · 产出骤降 · 任务失败。
          </div>
          <div v-for="(r, i) in rows" :key="i" class="mf-notify__row" :class="`is-${r.level || 'warn'}`">
            <div class="mf-notify__row-h">
              <VChip size="x-small" variant="tonal" :color="levelColor(r.level)">{{ r.kind_text || r.kind }}</VChip>
              <span class="mf-notify__time">{{ fmt(r.t) }}</span>
              <VSpacer />
              <span v-if="r.quiet" class="mf-notify__flag">免打扰未发</span>
              <span v-else-if="r.sent === false" class="mf-notify__flag is-bad">发送失败</span>
            </div>
            <div class="mf-notify__row-t">{{ r.title }}</div>
            <pre class="mf-notify__row-x">{{ r.text }}</pre>
          </div>
        </div>

        <div class="mf-notify__foot">
          历史落盘：<code>notify_history.json</code>（保留 200 条）· 同事件 {{ Math.round((data?.dedup_ttl || 21600) / 3600) }} 小时内去重
        </div>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  narrow: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'refresh', 'act'])

const cfg = computed(() => props.data?.cfg || {})
const rows = computed(() => (Array.isArray(props.data?.history) ? props.data.history : []))
const quietNow = computed(() => Boolean(props.data?.quiet_now))

function levelColor(level) {
  if (level === 'error') return 'error'
  if (level === 'info') return 'info'
  return 'warning'
}

function fmt(t) {
  const d = new Date(Number(t || 0) * 1000)
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<style scoped>
.mf-notify__title {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-block: 12px;
}

.mf-notify__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mf-notify__cfg {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mf-notify__thr {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  line-height: 1.6;
}

.mf-notify__thr strong { color: rgb(var(--v-theme-primary)); }

.mf-notify__hint { color: rgba(var(--v-theme-on-surface), 0.5); }

.mf-notify__acts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mf-notify__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mf-notify__empty {
  padding: 18px 4px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-align: center;
}

.mf-notify__row {
  padding: 8px 10px;
  border-radius: 8px;
  border-inline-start: 3px solid rgba(var(--v-theme-on-surface), 0.2);
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.mf-notify__row.is-error { border-inline-start-color: rgb(var(--v-theme-error)); }
.mf-notify__row.is-warn { border-inline-start-color: rgb(var(--v-theme-warning)); }
.mf-notify__row.is-info { border-inline-start-color: rgb(var(--v-theme-info)); }

.mf-notify__row-h {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mf-notify__time {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.mf-notify__flag {
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.mf-notify__flag.is-bad { color: rgb(var(--v-theme-error)); }

.mf-notify__row-t {
  margin-block-start: 2px;
  font-size: 12.5px;
  font-weight: 600;
  word-break: break-word;
}

.mf-notify__row-x {
  margin: 4px 0 0;
  font-family: inherit;
  font-size: 11.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgba(var(--v-theme-on-surface), 0.75);
}

.mf-notify__foot {
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  line-height: 1.5;
}
</style>
