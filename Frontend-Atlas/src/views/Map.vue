<template>
  <div class="min-h-screen w-full bg-white flex flex-col">
    <h1 class="text-2xl font-bold text-center py-6">Carte démo</h1>
    <MapGeoJSON />
  </div>
</template>

<script setup>
import MapGeoJSON from '../components/MapGeoJSON.vue';
</script>