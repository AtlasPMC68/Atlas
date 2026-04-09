<template>
  <div class="flex h-full min-h-0 flex-col">
    <Header v-if="!noHeaderRoutes.includes(route.path)" />
    <main class="flex-1">
      <router-view />
    </main>
    <Footer
      v-if="
        !noFooterRoutes.includes(route.path) &&
        withFooterRoutes.includes(route.path)
      "
    />
  </div>
</template>

<script setup lang="ts">
import Header from "./components/layout/Header.vue";
import Footer from "./components/layout/Footer.vue";
import { useRoute } from "vue-router";
const noHeaderRoutes = ["/connexion", "/inscription"];
const noFooterRoutes = ["/connexion", "/inscription"];
const withFooterRoutes = ["/"];
const route = useRoute();
</script>
