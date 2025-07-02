<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { initAuth } from './stores/auth'

onMounted(() => {
  initAuth()
})
</script>