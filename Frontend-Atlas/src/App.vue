<template>
  <Header />
  <main>
    <router-view />
  </main>
  <Footer />
</template>

<script setup lang="ts">
  import Header from './components/layout/Header.vue'
  import Footer from './components/layout/Footer.vue'
</script>