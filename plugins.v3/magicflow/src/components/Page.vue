<script setup>
import MagicFlowWorkbench from './MagicFlowWorkbench.vue'

defineProps({
  api: { type: Object, default: () => ({}) },
})

defineEmits(['action', 'close'])
</script>

<template>
  <MagicFlowWorkbench
    :api="api"
    plugin-id="MagicFlow"
    show-close
    compact
    @action="$emit('action')"
    @close="$emit('close')"
  />
</template>
