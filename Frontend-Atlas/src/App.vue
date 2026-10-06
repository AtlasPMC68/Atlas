<template>
  <MobileBlocker />
  <div class="flex h-full min-h-0 flex-col">
    <Header v-if="!noHeaderRoutes.includes(route.path)" />
    <main class="flex-1">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import MobileBlocker from "./components/MobileBlocker.vue";
import Header from "./components/layout/Header.vue";
import { useRoute } from "vue-router";
const noHeaderRoutes = ["/connexion", "/inscription"];
const route = useRoute();
</script>
