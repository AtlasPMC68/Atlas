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
import keycloak from "../keycloak";
import { PaperAirplaneIcon, TrashIcon } from "@heroicons/vue/24/solid";

const maps = ref<MapDisplay[]>([]);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const newMapTitle = ref("");
const newMapDescription = ref("");
const isCreating = ref(false);
const createMapDialogRef = ref<HTMLDialogElement | null>(null);
const mapToDelete = ref<MapDisplay | null>(null);
const isDeleting = ref(false);
const deleteConfirmDialogRef = ref<HTMLDialogElement | null>(null);
const alert = ref<{ type: "success" | "error"; message: string } | null>(null);

function showAlert(type: "success" | "error", message: string) {
  alert.value = { type, message };
  setTimeout(() => (alert.value = null), 4000);
}

onMounted(async () => {
  await fetchCurrentUser();
  await fetchMapsAndRender();
});

async function createMap() {
  if (!currentUser.value) return;
  isCreating.value = true;
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/create`, {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${keycloak.token}`,
      },
      method: "POST",
      body: JSON.stringify({
        user_id: currentUser.value.id,
        title: newMapTitle.value,
        description: newMapDescription.value,
        is_private: false,
      }),
    });
    if (!res.ok) {
      throw new Error(`Error creating map: ${res.status}`);
    }
    newMapTitle.value = "";
    newMapDescription.value = "";
    createMapDialogRef.value?.close();
    await fetchMapsAndRender();
    showAlert("success", "Carte créée avec succès !");
  } catch (err) {
    showAlert("error", "Erreur lors de la création de la carte.");
  } finally {
    isCreating.value = false;
  }
}

function confirmDelete(map: MapDisplay) {
  mapToDelete.value = map;
  deleteConfirmDialogRef.value?.showModal();
}

async function executeDelete() {
  if (!mapToDelete.value) return;
  isDeleting.value = true;
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/${mapToDelete.value.id}`,
      {
        headers: { Authorization: `Bearer ${keycloak.token}` },
        method: "DELETE",
      },
    );
    if (!res.ok) {
      throw new Error(`Error deleting map: ${res.status}`);
    }
    deleteConfirmDialogRef.value?.close();
    mapToDelete.value = null;
    await fetchMapsAndRender();
    showAlert("success", "Carte supprimée avec succès !");
  } catch (err) {
    showAlert("error", "Erreur lors de la suppression de la carte.");
  } finally {
    isDeleting.value = false;
  }
}

async function fetchMapsAndRender() {
  if (!currentUser.value) {
    throw new Error("No user or token available");
    return;
  }

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/map?user_id=${currentUser.value.id}`,
      {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
      },
    );

    if (!res.ok) {
      throw new Error(`Error while fetching the maps: ${res.status}`);
    }

    const mapsData: MapData[] = snakeToCamel(await res.json()) as MapData[];

    maps.value = mapsData.map((map: MapData) => ({
      id: map.id,
      title: map.title,
      description: map.description,
      createdAt: map.createdAt,
      userId: map.userId,
      image: "/images/default.jpg",
    }));
  } catch (err) {
    throw new Error("Error while fetching the maps:" + err);
  }
}
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    <!-- Alerts -->
    <Transition
      enter-active-class="transition ease-out duration-300"
      enter-from-class="opacity-0 translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition ease-in duration-200"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-2"
    >
      <div
        v-if="alert"
        role="alert"
        :class="[
          'alert fixed bottom-6 right-6 z-50 w-auto max-w-sm shadow-lg',
          alert.type === 'success' ? 'alert-success' : 'alert-error',
        ]"
      >
        <span>{{ alert.message }}</span>
      </div>
    </Transition>

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

      <!-- New map button -->
      <button
        class="btn-primary flex items-center"
        onclick="createMap.showModal()"
      >
        <PlusIcon class="h-5 w-5" />
        Nouvelle Carte
      </button>
      <dialog id="createMap" ref="createMapDialogRef" class="modal">
        <div class="modal-box p-0">
          <form @submit.prevent="createMap">
            <div class="card-body">
              <h3 class="text-lg font-bold">Créer une nouvelle carte</h3>

              <fieldset class="fieldset" :disabled="isCreating">
                <label class="label">Titre</label>
                <input
                  v-model="newMapTitle"
                  type="text"
                  class="input"
                  placeholder="Titre de la carte"
                  required
                />
                <label class="label">Description</label>
                <input
                  v-model="newMapDescription"
                  type="text"
                  class="input"
                  placeholder="Description de la carte"
                />
              </fieldset>

              <div class="flex justify-end mt-8">
                <button
                  type="submit"
                  class="btn btn-primary flex items-center"
                  :disabled="!newMapTitle.trim()"
                >
                  <span>Créer</span>
                  <span
                    v-if="isCreating"
                    class="loading loading-spinner loading-xs"
                  ></span>
                  <PaperAirplaneIcon v-else class="h-4 w-4" />
                </button>
              </div>
            </div>
          </form>
        </div>
        <form method="dialog" class="modal-backdrop">
          <button :disabled="isCreating">close</button>
        </form>
      </dialog>
    </div>

    <!-- Maps grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="map in maps"
        :key="map.id"
        class="card bg-base-100 w-90 shadow-sm hover:shadow-xl transition-shadow cursor-pointer"
        @click="$router.push(`/maps/${map.id}`)"
      >
        <figure>
          <img
            src="https://img.daisyui.com/images/stock/photo-1606107557195-0e29a4b5b4aa.webp"
            alt="Map"
            class="w-full h-44"
          />
        </figure>
        <div class="card-body pb-0">
          <h2 class="card-title text-sm xl:text-lg">
            {{ map.title }}
          </h2>
          <p class="pb-2">
            {{ map.description || "Aucune description" }}
          </p>
        </div>
        <div class="flex justify-between items-center">
          <div class="badge badge-outline align-bottom">
            {{ new Date(map.createdAt).toLocaleDateString() }}
          </div>
          <button
            class="btn btn-ghost btn-sm text-error"
            @click.stop="confirmDelete(map)"
          >
            <TrashIcon class="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>

    <!-- Delete confirmation dialog -->
    <dialog ref="deleteConfirmDialogRef" class="modal">
      <div class="modal-box">
        <h3 class="text-lg font-bold">Supprimer la carte</h3>
        <p class="py-4">
          Êtes-vous sûr de vouloir supprimer
          <span class="font-semibold">{{ mapToDelete?.title }}</span> ? Cette
          action est irréversible.
        </p>
        <div class="modal-action">
          <button
            class="btn"
            :disabled="isDeleting"
            @click="deleteConfirmDialogRef?.close()"
          >
            Annuler
          </button>
          <button
            class="btn btn-error"
            :disabled="isDeleting"
            @click="executeDelete"
          >
            <span
              v-if="isDeleting"
              class="loading loading-spinner loading-xs"
            ></span>
            <span v-else class="text-white">Supprimer</span>
          </button>
        </div>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button :disabled="isDeleting">close</button>
      </form>
    </dialog>
  </div>
</template>

<style scoped>
.btn-primary {
  @apply bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition;
}
</style>
