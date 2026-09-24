<script setup>
import { onMounted } from 'vue'
import MagicFlowWorkbench from './MagicFlowWorkbench.vue'

defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['layout', 'close'])

onMounted(() => {
  emit('layout', { maxWidth: '80rem' })
})
</script>

<template>
  <MagicFlowWorkbench
    :api="api"
    plugin-id="MagicFlow"
    initial-tab="config"
    show-close
    compact
    @close="$emit('close')"
  />
</template>
