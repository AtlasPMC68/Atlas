
<template>
  <Header v-if="!noHeaderRoutes.includes(route.path)" />
  <main>
    <router-view />
  </main>
  <Footer v-if="!noFooterRoutes.includes(route.path)" />
</template>

<script setup lang="ts">
import Header from './components/layout/Header.vue'
import Footer from './components/layout/Footer.vue'
import { useRoute } from 'vue-router'
const noHeaderRoutes = ['/connexion', '/inscription']
const noFooterRoutes = ['/connexion', '/inscription']
const route = useRoute()
</script>