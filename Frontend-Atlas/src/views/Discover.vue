<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  PlusIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
} from "@heroicons/vue/24/outline";

interface Projet {
  id: string;
  titre: string;
  auteur: string;
  image: string;
}

const projets = ref<Projet[]>([]);

onMounted(() => {
  fetchMapsAndRender();
});

async function fetchMapsAndRender() {
  try {
    const res = await fetch(`http://localhost:8000/maps/map`);

    if (!res.ok) {
      throw new Error(`Erreur HTTP : ${res.status}`);
    }

    const data = await res.json();

    projets.value = data.map((item: any) => {
      return {
        id: item.id,
        titre: item.title,
        auteur: item.owner_id,
        image: "/images/default.jpg",
      };
    });
  } catch (err) {
    console.error("Erreur attrapée :", err);
  }
}
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    <!-- Search bar + buttons -->
    <div
      class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6"
    >
      <!-- Search field + filter -->
      <div class="flex flex-1 gap-2">
        <div class="relative flex-1">
          <MagnifyingGlassIcon
            class="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400"
          />
          <input
            type="text"
            placeholder="Rechercher un projet..."
            class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <button
          class="inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100"
        >
          <FunnelIcon class="h-5 w-5 mr-2" />
          Filtres
        </button>
      </div>

      <!-- "Nouveau projet" button -->
      <RouterLink
        to="/demo/upload"
        class="btn-primary flex items-center gap-2 self-start md:self-auto"
      >
        <PlusIcon class="h-5 w-5" />
        Nouveau projet
      </RouterLink>
    </div>

    <!-- Projects grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="projet in projets"
        :key="projet.id"
        class="bg-white border border-gray-200 rounded-lg shadow hover:shadow-md transition-shadow cursor-pointer"
        @click="$router.push('/carte/${projet.id}')"
      >
        <img
          :src="projet.image"
          alt=""
          class="w-full h-40 object-cover rounded-t-lg"
        />
        <div class="p-4">
          <h3 class="text-lg font-semibold text-gray-900">
            {{ projet.titre }}
          </h3>
          <p class="text-sm text-gray-500">par {{ projet.auteur }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.btn-primary {
  @apply bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition;
}
</style>
