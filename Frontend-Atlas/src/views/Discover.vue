<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  PlusIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
} from "@heroicons/vue/24/outline";
import { MapData, MapDisplay } from "../typescript/map";
import { snakeToCamel } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";

const maps = ref<MapDisplay[]>([]);
const { fetchCurrentUser } = useCurrentUser();

onMounted(async () => {
  await fetchCurrentUser();
  await fetchMapsAndRender();
});

async function fetchMapsAndRender() {
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/map`);

    if (!res.ok) {
      throw new Error(`HTTP error : ${res.status}`);
    }

    const data = snakeToCamel(await res.json()) as MapData[];

    maps.value = data.map((map: MapData) => {
      return {
        id: map.id,
        title: map.title,
        description: map.description,
        createdAt: map.createdAt,
        userId: map.userId,
        image: "/images/default.jpg",
      };
    });
  } catch (err) {
    console.error("Catched error :", err);
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
            placeholder="Rechercher une carte..."
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

      <!-- new Map button -->
      <RouterLink
        to="/demo/upload"
        class="btn-primary flex items-center gap-2 self-start md:self-auto"
      >
        <PlusIcon class="h-5 w-5" />
        Nouvelle Carte
      </RouterLink>
    </div>

    <!-- Maps grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="map in maps"
        :key="map.id"
        class="bg-white border border-gray-200 rounded-lg shadow hover:shadow-md transition-shadow cursor-pointer"
        @click="$router.push(`/maps/${map.id}`)"
      >
        <img
          :src="map.image || '/images/default.jpg'"
          alt=""
          class="w-full h-40 object-cover rounded-t-lg"
        />
        <div class="p-4">
          <h3 class="text-lg font-semibold text-gray-900">
            {{ map.title }}
          </h3>
          <p class="text-sm text-gray-500">par {{ map.userId }}</p>
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
