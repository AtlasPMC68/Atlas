<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import {
  PlusIcon,
  MagnifyingGlassIcon,
  QuestionMarkCircleIcon,
  PencilSquareIcon,
} from "@heroicons/vue/24/outline";
import { MapData, MapDisplay } from "../typescript/map";
import { camelToSnake, snakeToCamel } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";
import { PaperAirplaneIcon, TrashIcon } from "@heroicons/vue/24/solid";

const maps = ref<MapDisplay[]>([]);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const newMapTitle = ref<string | undefined>(undefined);
const newMapDescription = ref<string | undefined>(undefined);
const newMapIsPrivate = ref(true);
const isCreating = ref(false);
const createMapDialogRef = ref<HTMLDialogElement | null>(null);
const mapToDelete = ref<MapDisplay | null>(null);
const isDeleting = ref(false);
const deleteConfirmDialogRef = ref<HTMLDialogElement | null>(null);
const editMapDialogRef = ref<HTMLDialogElement | null>(null);
const mapToEdit = ref<MapDisplay | null>(null);
const editMapTitle = ref<string | undefined>(undefined);
const editMapDescription = ref<string | undefined>(undefined);
const editMapIsPrivate = ref(true);
const isEditing = ref(false);
const alert = ref<{ type: "success" | "error"; message: string } | null>(null);
const searchQuery = ref("");
const filterVisibility = ref<"all" | "public" | "private">("all");
const filterDateFrom = ref("");
const filterDateTo = ref("");

function resetFilters() {
  filterVisibility.value = "all";
  filterDateFrom.value = "";
  filterDateTo.value = "";
}

const hasActiveFilters = computed(
  () =>
    filterVisibility.value !== "all" ||
    filterDateFrom.value !== "" ||
    filterDateTo.value !== "",
);

const filteredMaps = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  return maps.value.filter((m) => {
    if (
      q &&
      !m.title.toLowerCase().includes(q) &&
      !(m.description ?? "").toLowerCase().includes(q)
    )
      return false;

    if (filterVisibility.value === "public" && m.isPrivate) return false;
    if (filterVisibility.value === "private" && !m.isPrivate) return false;

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

function showAlert(type: "success" | "error", message: string) {
  alert.value = { type, message };
  setTimeout(() => (alert.value = null), 4000);
}

onMounted(async () => {
  await fetchCurrentUser();
  await fetchMapsAndRender();
});

// TODO: Add startDate endDate
async function createMap() {
  if (!currentUser.value) {
    showAlert("error", "Utilisateur non authentifié.");
    return;
  }
  if (!newMapTitle.value?.trim()) {
    showAlert("error", "Le titre de la carte est requis.");
    return;
  }
  isCreating.value = true;
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/create`, {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${keycloak.token}`,
      },
      method: "POST",
      body: JSON.stringify(
        camelToSnake({
          userId: currentUser.value.id,
          title: newMapTitle.value,
          description: newMapDescription.value,
          isPrivate: newMapIsPrivate.value,
        }),
      ),
    });
    if (!res.ok) {
      throw new Error(`Error creating map: ${res.status}`);
    }
    newMapTitle.value = undefined;
    newMapDescription.value = undefined;
    newMapIsPrivate.value = true;
    createMapDialogRef.value?.close();
    await fetchMapsAndRender();
    showAlert("success", "Carte créée avec succès !");
  } catch (err) {
    showAlert("error", "Erreur lors de la création de la carte.");
  } finally {
    isCreating.value = false;
  }
}

function resetCreateMapForm() {
  newMapTitle.value = undefined;
  newMapDescription.value = undefined;
  newMapIsPrivate.value = true;
}

function confirmDelete(map: MapDisplay) {
  mapToDelete.value = map;
  deleteConfirmDialogRef.value?.showModal();
}

function openEditDialog(map: MapDisplay) {
  mapToEdit.value = map;
  editMapTitle.value = map.title;
  editMapDescription.value = map.description ?? undefined;
  editMapIsPrivate.value = map.isPrivate ?? true;
  editMapDialogRef.value?.showModal();
}

async function saveMap() {
  if (!mapToEdit.value) {
    showAlert("error", "Aucune carte sélectionnée pour la modification.");
    return;
  }
  if (!editMapTitle.value?.trim()) {
    showAlert("error", "Le titre de la carte est requis.");
    return;
  }
  if (!currentUser.value) {
    showAlert("error", "Utilisateur non authentifié.");
    return;
  }
  isEditing.value = true;
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/${mapToEdit.value.id}`,
      {
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        method: "PUT",
        body: JSON.stringify(
          camelToSnake({
            userId: currentUser.value.id,
            title: editMapTitle.value,
            description:
              editMapDescription.value === ""
                ? undefined
                : editMapDescription.value,
            isPrivate: editMapIsPrivate.value,
          }),
        ),
      },
    );
    if (!res.ok) {
      throw new Error(`Error updating map: ${res.status}`);
    }
    editMapTitle.value = undefined;
    editMapDescription.value = undefined;
    editMapIsPrivate.value = true;
    editMapDialogRef.value?.close();
    await fetchMapsAndRender();
    showAlert("success", "Carte modifiée avec succès !");
  } catch (err) {
    showAlert("error", "Erreur lors de la modification de la carte.");
  } finally {
    isEditing.value = false;
  }
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
      isPrivate: map.isPrivate,
      username: map.username,
      createdAt: map.createdAt,
      updatedAt: map.updatedAt,
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

    <!-- Filters + search + button -->
    <div class="flex flex-col gap-3 mb-6">
      <!-- Filters row -->
      <div class="flex flex-wrap gap-4 items-end">
        <!-- Visibility -->
        <div class="flex flex-col gap-1 min-w-40">
          <label class="text-sm font-medium text-gray-600">Accessibilité</label>
          <select v-model="filterVisibility" class="select select-sm">
            <option value="all">Toutes</option>
            <option value="public">Publiques</option>
            <option value="private">Privées</option>
          </select>
        </div>
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

      <!-- Search + new map button -->
      <div
        class="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
      >
        <label class="flex input flex-1">
          <MagnifyingGlassIcon class="h-5 w-5 text-gray-400" />
          <input
            v-model="searchQuery"
            type="search"
            required
            placeholder="Rechercher une carte par titre ou description"
          />
        </label>
        <button
          class="btn-primary flex items-center"
          onclick="createMap.showModal()"
        >
          <PlusIcon class="h-5 w-5" />
          Nouvelle Carte
        </button>
      </div>
    </div>
    <dialog
      id="createMap"
      ref="createMapDialogRef"
      class="modal"
      @close="resetCreateMapForm"
    >
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
              <div class="gap-1">
                <div class="flex items-center gap-1">
                  <span class="fieldset-legend">Accès à la carte</span>
                  <div
                    class="tooltip tooltip-right items-center"
                    data-tip="Les cartes publiques sont visibles par tous les utilisateurs, tandis que les cartes privées ne sont accessibles que par vous."
                  >
                    <QuestionMarkCircleIcon
                      class="h-4 w-4 text-gray-400"
                    ></QuestionMarkCircleIcon>
                  </div>
                </div>
                <label class="label cursor-pointer gap-2">
                  <input
                    type="checkbox"
                    :checked="!newMapIsPrivate"
                    @change="
                      newMapIsPrivate = !($event.target as HTMLInputElement)
                        .checked
                    "
                    class="toggle toggle-primary"
                  />
                  Public
                </label>
              </div>
            </fieldset>

            <div class="flex justify-end mt-8">
              <button
                type="submit"
                class="btn btn-primary flex items-center"
                :disabled="!newMapTitle"
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

    <!-- Maps grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="map in filteredMaps"
        :key="map.id"
        class="card bg-base-100 w-90 shadow-sm hover:shadow-xl transition-shadow cursor-pointer"
        @click="$router.push(`/maps/${map.id}`)"
      >
        <figure>
          <!-- TODO replace image -->
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
          <div class="flex gap-2">
            <div class="badge badge-outline align-bottom">
              {{ new Date(map.createdAt).toLocaleDateString() }}
            </div>
            <div class="badge badge-outline align-bottom">
              {{ map.isPrivate ? "Privé" : "Public" }}
            </div>
          </div>
          <div class="flex gap-1 p-2">
            <button
              class="btn btn-ghost btn-sm text-primary-600"
              @click.stop="openEditDialog(map)"
            >
              <PencilSquareIcon class="h-5 w-5" />
            </button>
            <button
              class="btn btn-ghost btn-sm text-error"
              @click.stop="confirmDelete(map)"
            >
              <TrashIcon class="h-5 w-5" />
            </button>
          </div>
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

    <!-- Edit map dialog -->
    <dialog ref="editMapDialogRef" class="modal">
      <div class="modal-box p-0">
        <form @submit.prevent="saveMap">
          <div class="card-body">
            <h3 class="text-lg font-bold">Modifier la carte</h3>

            <fieldset class="fieldset" :disabled="isEditing">
              <label class="label">Titre</label>
              <input
                v-model="editMapTitle"
                type="text"
                class="input"
                placeholder="Titre de la carte"
                required
              />
              <label class="label">Description</label>
              <input
                v-model="editMapDescription"
                type="text"
                class="input"
                placeholder="Description de la carte"
              />
              <div class="gap-1">
                <div class="flex items-center gap-1">
                  <span class="fieldset-legend">Accès à la carte</span>
                  <div
                    class="tooltip tooltip-right"
                    data-tip="Les cartes publiques sont visibles par tous les utilisateurs, tandis que les cartes privées ne sont accessibles que par vous."
                  >
                    <QuestionMarkCircleIcon class="h-4 w-4 text-gray-400" />
                  </div>
                </div>
                <label class="label cursor-pointer gap-2">
                  <input
                    type="checkbox"
                    :checked="!editMapIsPrivate"
                    @change="
                      editMapIsPrivate = !($event.target as HTMLInputElement)
                        .checked
                    "
                    class="toggle toggle-primary"
                  />
                  {{ editMapIsPrivate ? "Privé" : "Public" }}
                </label>
              </div>
            </fieldset>

            <div class="flex justify-end gap-2 mt-8">
              <button
                type="button"
                class="btn btn-ghost"
                :disabled="isEditing"
                @click="editMapDialogRef?.close()"
              >
                Annuler
              </button>
              <button
                type="submit"
                class="btn btn-primary flex items-center"
                :disabled="!editMapTitle?.trim() || isEditing"
              >
                <span
                  v-if="isEditing"
                  class="loading loading-spinner loading-xs"
                ></span>
                <span v-else>Modifier</span>
              </button>
            </div>
          </div>
        </form>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button :disabled="isEditing">close</button>
      </form>
    </dialog>
  </div>
</template>

<style scoped>
.btn-primary {
  @apply bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition;
}
</style>
