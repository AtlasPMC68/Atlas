<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { MagnifyingGlassIcon } from "@heroicons/vue/24/outline";
import { MapData } from "../typescript/map";
import { snakeToCamel, toImageSrc } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";

const projects = ref<MapData[]>([]);
const { fetchCurrentUser } = useCurrentUser();

const searchQuery = ref("");
const filterDateFrom = ref("");
const filterDateTo = ref("");

function resetFilters() {
  filterDateFrom.value = "";
  filterDateTo.value = "";
}

const hasActiveFilters = computed(
  () => filterDateFrom.value !== "" || filterDateTo.value !== "",
);

const filteredProjects = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  return projects.value.filter((m) => {
    if (
      q &&
      !m.title.toLowerCase().includes(q) &&
      !(m.description ?? "").toLowerCase().includes(q) &&
      !(m.username ?? "").toLowerCase().includes(q)
    )
      return false;

    const createdAt = new Date(m.createdAt);
    if (filterDateFrom.value && createdAt < new Date(filterDateFrom.value))
      return false;
    if (
      filterDateTo.value &&
      createdAt > new Date(filterDateTo.value + "T23:59:59")
    )
      return false;

    return true;
  });
});

onMounted(async () => {
  await fetchCurrentUser();
  await fetchProjectsAndRender();
});

async function fetchProjectsAndRender() {
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/projects`);

    if (!res.ok) {
      throw new Error(`HTTP error : ${res.status}`);
    }

    const data = snakeToCamel(await res.json()) as MapData[];

    projects.value = data.map((map: MapData) => {
      return {
        id: map.id,
        title: map.title,
        description: map.description,
        createdAt: map.createdAt,
        updatedAt: map.updatedAt,
        isPrivate: map.isPrivate,
        userId: map.userId,
        username: map.username,
        image: map.image,
      };
    });
  } catch (err) {
    console.error("Catched error :", err);
  }
}
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    <!-- Filters + search -->
    <div class="flex flex-col gap-3 mb-6">
      <!-- Filters row -->
      <div class="flex flex-wrap gap-4 items-end">
        <!-- Date to -->
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-gray-600">Créée avant</label>
          <input v-model="filterDateTo" type="date" class="input input-sm" />
        </div>
        <!-- Date from -->
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-gray-600">Créée après</label>
          <input v-model="filterDateFrom" type="date" class="input input-sm" />
        </div>

        <!-- Reset -->
        <button
          v-if="hasActiveFilters"
          class="btn btn-ghost btn-sm text-gray-500"
          @click="resetFilters"
        >
          Réinitialiser
        </button>
      </div>

      <!-- Search -->
      <div
        class="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
      >
        <label class="flex input flex-1">
          <MagnifyingGlassIcon class="h-5 w-5 text-gray-400" />
          <input
            v-model="searchQuery"
            type="search"
            required
            placeholder="Rechercher un projet par titre, description ou nom d'utilisateur"
          />
        </label>
      </div>
    </div>

    <!-- Projects grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="map in filteredProjects"
        :key="map.id"
        class="card bg-base-100 w-90 shadow-sm hover:shadow-xl transition-shadow"
      >
        <figure>
          <img :src="toImageSrc(map.image)" class="w-full h-full" />
        </figure>
        <div class="card-body pb-0">
          <h2 class="card-title text-sm xl:text-lg">
            {{ map.title }}
          </h2>
          <p class="pb-2">
            {{ map.description || "Aucune description" }}
          </p>
          <p class="text-xs text-base-content/50">Par {{ map.username }}</p>
        </div>
        <div class="flex justify-between items-center">
          <div class="flex gap-2 p-4">
            <div class="badge badge-outline align-bottom">
              {{ new Date(map.createdAt).toLocaleDateString() }}
            </div>
            <div class="badge badge-outline align-bottom">
              {{ map.isPrivate ? "Privée" : "Publique" }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-if="filteredProjects.length === 0"
      class="text-center py-16 text-base-content/50"
    >
      <p class="text-lg">Aucun projet public trouvé.</p>
    </div>
  </div>
</template>
