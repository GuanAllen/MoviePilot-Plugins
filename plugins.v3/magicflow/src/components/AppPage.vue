<script setup>
import MagicFlowWorkbench from './MagicFlowWorkbench.vue'

defineProps({
  api: { type: Object, default: () => ({}) },
  navKey: { type: String, default: 'main' },
  pluginId: { type: String, default: 'MagicFlow' },
})

defineEmits(['action'])
</script>

<template>
  <MagicFlowWorkbench
    :api="api"
    :plugin-id="pluginId"
    @action="$emit('action')"
  />
</template>
