<script setup>
// 魔流 · RSS passkey 输入
// passkey 只在服务端使用；这里只负责录入/清除，回显一律脱敏。
import { computed, ref, watch } from 'vue'
import { unwrapResponse } from '../../../../utils'

const open = defineModel({ type: Boolean, default: false })
const props = defineProps({
  api: { type: Object, required: true },
  isNarrow: { type: Boolean, default: false },
})

const loading = ref(false)
const syncing = ref(false)
const saving = ref('')
const rows = ref([])
const drafts = ref({})
const msg = ref('')
const filter = ref('')

const savedCount = computed(() => rows.value.filter((r) => r.has_passkey).length)
const visible = computed(() => {
  const q = filter.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter(
    (r) => String(r.site_name || '').toLowerCase().includes(q) || String(r.domain || '').toLowerCase().includes(q),
  )
})

async function load() {
  loading.value = true
  msg.value = ''
  try {
    const res = unwrapResponse(await props.api.get('rss/config')) || {}
    rows.value = res.sites || []
    drafts.value = {}
  } catch (e) {
    msg.value = '读取失败：' + (e?.message || e)
  } finally {
    loading.value = false
  }
}

watch(open, (v) => {
  if (v) load()
})

async function save(row) {
  const pk = String(drafts.value[row.site_id] || '').trim()
  if (!pk) {
    msg.value = '请先输入 passkey（清空请点「清除」）'
    return
  }
  saving.value = String(row.site_id)
  msg.value = ''
  try {
    const q = new URLSearchParams({ site_id: String(row.site_id), passkey: pk }).toString()
    const res = unwrapResponse(await props.api.post(`rss/passkey?${q}`, {})) || {}
    if (res.success === false) {
      msg.value = res.message || '保存失败'
      return
    }
    row.has_passkey = true
    row.masked = (res.data && res.data.masked) || row.masked
    drafts.value[row.site_id] = ''
    msg.value = `已保存：${row.site_name}`
  } catch (e) {
    msg.value = '保存失败：' + (e?.message || e)
  } finally {
    saving.value = ''
  }
}

async function syncToMp() {
  syncing.value = true
  msg.value = ''
  try {
    const res = unwrapResponse(await props.api.post('creds/sync?confirm=1', {})) || {}
    msg.value = res.success === false ? (res.message || '同步失败') : (res.message || '已同步到 MP')
    await load()
  } catch (e) {
    msg.value = '同步失败：' + (e?.message || e)
  } finally {
    syncing.value = false
  }
}

async function clear(row) {
  saving.value = String(row.site_id)
  msg.value = ''
  try {
    const q = new URLSearchParams({ site_id: String(row.site_id), passkey: '' }).toString()
    const res = unwrapResponse(await props.api.post(`rss/passkey?${q}`, {})) || {}
    if (res.success === false) {
      msg.value = res.message || '清除失败'
      return
    }
    row.has_passkey = false
    row.masked = ''
    drafts.value[row.site_id] = ''
    msg.value = `已清除：${row.site_name}`
  } catch (e) {
    msg.value = '清除失败：' + (e?.message || e)
  } finally {
    saving.value = ''
  }
}
</script>

<template>
  <v-dialog v-model="open" :max-width="isNarrow ? undefined : 720" :fullscreen="isNarrow" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2" icon="mdi-rss" />
        RSS passkey
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </v-card-title>
      <v-card-subtitle>
        这里只存 passkey（MP 没有该字段）。RSS 与 API Key 请在 MP 站点配置里填，自动复用。
        已保存 {{ savedCount }} / {{ rows.length }}
      </v-card-subtitle>
      <v-card-text>
        <v-text-field
          v-model="filter"
          density="compact"
          variant="outlined"
          prepend-inner-icon="mdi-magnify"
          placeholder="筛选站点"
          hide-details
          class="mb-3"
        />
        <v-alert v-if="msg" :type="msg.includes('失败') ? 'error' : 'success'" density="compact" variant="tonal" class="mb-3">
          {{ msg }}
        </v-alert>
        <div v-if="loading" class="text-center py-6">
          <v-progress-circular indeterminate size="28" />
        </div>
        <v-list v-else density="compact">
          <v-list-item v-for="row in visible" :key="row.site_id" class="px-0">
            <template #prepend>
              <v-chip size="x-small" :color="row.has_passkey ? 'success' : 'default'" variant="tonal" class="mr-3">
                {{ row.has_passkey ? '已存' : '未填' }}
              </v-chip>
            </template>
            <v-list-item-title class="text-body-2">
              {{ row.site_name }}
              <span class="text-caption text-medium-emphasis ml-2">{{ row.domain }}</span>
            </v-list-item-title>
            <v-list-item-subtitle class="text-caption">
              <span v-if="row.has_passkey">passkey：{{ row.masked }}</span>
              <span v-else>passkey：未填</span>
              <v-chip v-if="row.mp_rss_set" size="x-small" class="ml-2" variant="tonal" color="info">MP RSS</v-chip>
              <v-chip v-if="row.mp_apikey_set" size="x-small" class="ml-2" variant="tonal" color="success">MP API</v-chip>
            </v-list-item-subtitle>
            <template #append>
              <div class="rss-row-actions">
                <v-text-field
                  v-model="drafts[row.site_id]"
                  class="rss-row-input"
                  density="compact"
                  variant="outlined"
                  placeholder="粘贴 passkey"
                  hide-details
                  @keyup.enter="save(row)"
                />
                <v-btn size="small" color="primary" :loading="saving === String(row.site_id)" @click="save(row)">
                  保存
                </v-btn>
                <v-btn
                  v-if="row.has_passkey"
                  size="small"
                  variant="text"
                  :loading="saving === String(row.site_id)"
                  @click="clear(row)"
                >
                  清除
                </v-btn>
              </div>
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :loading="syncing" @click="syncToMp">同步 RSS 到 MP</v-btn>
        <v-btn variant="text" @click="load">刷新</v-btn>
        <v-btn color="primary" variant="tonal" @click="open = false">完成</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.rss-row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rss-row-input {
  flex: 1 1 200px;
  min-width: 160px;
}

@media (max-width: 600px) {
  .rss-row-actions {
    width: 100%;
    min-width: 0;
  }

  .rss-row-input {
    flex: 1 1 100%;
  }
}
</style>
