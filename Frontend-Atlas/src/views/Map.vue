<template>
  <Header />
  <div class="min-h-screen w-full bg-white flex flex-col">
    <h1 class="text-2xl font-bold text-center py-6">Carte démo</h1>
    <MapGeoJSON />
  </div>
  <Footer />

</template>

<script setup>
import MapGeoJSON from '../components/MapGeoJSON.vue';
import Header from '../components/Header.vue';
import Footer from '../components/Footer.vue';
</script>