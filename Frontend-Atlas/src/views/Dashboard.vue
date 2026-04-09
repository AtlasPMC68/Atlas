<script setup lang="ts">
import { useRouter } from "vue-router";
import { ref, computed, onMounted, onUnmounted } from "vue";
import {
  PlusIcon,
  MagnifyingGlassIcon,
  QuestionMarkCircleIcon,
  PencilSquareIcon,
} from "@heroicons/vue/24/outline";
import {
  CreatedProjectRef,
  CreateProjectDialogExposed,
} from "../typescript/project";
import type { MapData } from "../typescript/map";
import { camelToSnake, snakeToCamel, toImageSrc } from "../utils/utils";
import { apiFetch } from "../utils/api";
import { useCurrentUser } from "../composables/useCurrentUser";
import { TrashIcon } from "@heroicons/vue/24/solid";
import { clearAlert, showAlert } from "../composables/useAlert";
import Alert from "../components/Alert.vue";
import CreateProjectDialog from "../components/CreateProjectDialog.vue";

const maps = ref<MapData[]>([]);
const router = useRouter();
const { currentUser, fetchCurrentUser } = useCurrentUser();
const createProjectDialogRef = ref<CreateProjectDialogExposed | null>(null);
const projectToDelete = ref<MapData | null>(null);
const isDeleting = ref(false);
const deleteConfirmDialogRef = ref<HTMLDialogElement | null>(null);
const editProjectDialogRef = ref<HTMLDialogElement | null>(null);
const projectToEdit = ref<MapData | null>(null);
const editProjectTitle = ref<string | undefined>(undefined);
const editProjectDescription = ref<string | undefined>(undefined);
const editProjectIsPrivate = ref(true);
const isEditing = ref(false);
const searchQuery = ref("");
const filterVisibility = ref<"all" | "public" | "private">("all");
const filterDateFrom = ref("");
const filterDateTo = ref("");

function openCreateProjectDialog() {
  createProjectDialogRef.value?.open();
}

async function onProjectCreated(project: CreatedProjectRef | null) {
  if (!project?.id) {
    showAlert("error", "Impossible de récupérer l'identifiant du projet.");
    return;
  }

  await router.push({
    path: `/projet/${project.id}`,
  });
}

function onCreateProjectError(message: string) {
  showAlert("error", message);
}

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

const filteredProjects = computed(() => {
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

onMounted(async () => {
  await fetchCurrentUser();
  await fetchMapsAndRender();
});

onUnmounted(() => {
  clearAlert();
});

function confirmDelete(project: MapData) {
  projectToDelete.value = project;
  deleteConfirmDialogRef.value?.showModal();
}

function openEditDialog(project: MapData) {
  projectToEdit.value = project;
  editProjectTitle.value = project.title;
  editProjectDescription.value = project.description ?? undefined;
  editProjectIsPrivate.value = project.isPrivate ?? true;
  editProjectDialogRef.value?.showModal();
}

async function saveProject() {
  if (!projectToEdit.value) {
    showAlert("error", "Aucun projet sélectionné pour la modification.");
    return;
  }
  if (!editProjectTitle.value?.trim()) {
    showAlert("error", "Le titre du projet est requis.");
    return;
  }
  if (!currentUser.value) {
    showAlert("error", "Utilisateur non authentifié.");
    return;
  }
  isEditing.value = true;
  try {
    const res = await apiFetch(`/projects/${projectToEdit.value.id}`, {
      headers: { "Content-Type": "application/json" },
      method: "PUT",
      body: JSON.stringify(
        camelToSnake({
          userId: currentUser.value.id,
          title: editProjectTitle.value,
          description:
            editProjectDescription.value === ""
              ? undefined
              : editProjectDescription.value,
          isPrivate: editProjectIsPrivate.value,
        }),
      ),
    });
    if (!res.ok) {
      throw new Error(`Error updating project: ${res.status}`);
    }
    editProjectTitle.value = undefined;
    editProjectDescription.value = undefined;
    editProjectIsPrivate.value = true;
    editProjectDialogRef.value?.close();
    await fetchMapsAndRender();
    showAlert("success", "Projet modifié avec succès !");
  } catch (err) {
    showAlert("error", "Erreur lors de la modification du projet.");
  } finally {
    isEditing.value = false;
  }
}

async function executeDelete() {
  if (!projectToDelete.value) return;
  isDeleting.value = true;
  try {
    const res = await apiFetch(`/projects/${projectToDelete.value.id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      throw new Error(`Error deleting project: ${res.status}`);
    }
    deleteConfirmDialogRef.value?.close();
    projectToDelete.value = null;
    await fetchMapsAndRender();
    showAlert("success", "Projet supprimé avec succès !");
  } catch (err) {
    showAlert("error", "Erreur lors de la suppression du projet.");
  } finally {
    isDeleting.value = false;
  }
}

async function fetchMapsAndRender() {
  if (!currentUser.value) {
    throw new Error("No user or token available");
  }

  try {
    const res = await apiFetch(`/projects?user_id=${currentUser.value.id}`, {
      headers: { "Content-Type": "application/json" },
    });

    if (!res.ok) {
      throw new Error(`Error while fetching the projects: ${res.status}`);
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
      image: map.image,
    }));
  } catch (err) {
    throw new Error("Error while fetching the projects:" + err);
  }
}
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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

      <!-- Search + new project button -->
      <div
        class="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
      >
        <label class="flex input flex-1">
          <MagnifyingGlassIcon class="h-5 w-5 text-gray-400" />
          <input
            v-model="searchQuery"
            type="search"
            required
            placeholder="Rechercher un projet par titre ou description"
          />
        </label>
        <button
          class="btn-primary flex items-center"
          @click="openCreateProjectDialog"
        >
          <PlusIcon class="h-5 w-5" />
          Nouveau Projet
        </button>
      </div>
    </div>
    <CreateProjectDialog
      ref="createProjectDialogRef"
      @created="onProjectCreated"
      @error="onCreateProjectError"
    />

    <!-- Projects grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="project in filteredProjects"
        :key="project.id"
        class="card bg-base-100 w-90 shadow-sm hover:shadow-xl transition-shadow cursor-pointer"
        @click="router.push(`/projet/${project.id}`)"
      >
        <figure>
          <img :src="toImageSrc(project.image)" class="w-full h-full" />
        </figure>
        <div class="card-body pb-0">
          <h2 class="card-title text-sm xl:text-lg">
            {{ project.title }}
          </h2>
          <p class="pb-2">
            {{ project.description || "Aucune description" }}
          </p>
        </div>
        <div class="flex justify-between items-center">
          <div class="flex gap-2">
            <div class="badge badge-outline align-bottom">
              {{ new Date(project.createdAt).toLocaleDateString() }}
            </div>
            <div class="badge badge-outline align-bottom">
              {{ project.isPrivate ? "Privé" : "Public" }}
            </div>
          </div>
          <div class="flex gap-1 p-2">
            <button
              class="btn btn-ghost btn-sm text-primary-600"
              @click.stop="openEditDialog(project)"
            >
              <PencilSquareIcon class="h-5 w-5" />
            </button>
            <button
              class="btn btn-ghost btn-sm text-error"
              @click.stop="confirmDelete(project)"
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
        <h3 class="text-lg font-bold">Supprimer le projet</h3>
        <p class="py-4">
          Êtes-vous sûr de vouloir supprimer
          <span class="font-semibold">{{ projectToDelete?.title }}</span> ? Cette
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
        <form @submit.prevent="saveProject">
          <div class="card-body">
            <h3 class="text-lg font-bold">Modifier le projet</h3>

            <fieldset class="fieldset" :disabled="isEditing">
              <label class="label">Titre</label>
              <input
                v-model="editProjectTitle"
                type="text"
                class="input"
                placeholder="Titre du projet"
                required
              />
              <label class="label">Description</label>
              <input
                v-model="editProjectDescription"
                type="text"
                class="input"
                placeholder="Description du projet"
              />
              <div class="gap-1">
                <div class="flex items-center gap-1">
                  <span class="fieldset-legend">Accès au projet</span>
                  <div
                    class="tooltip tooltip-right"
                    data-tip="Les projets publics sont visibles par tous les utilisateurs, tandis que les projets privés ne sont accessibles que par vous."
                  >
                    <QuestionMarkCircleIcon class="h-4 w-4 text-gray-400" />
                  </div>
                </div>
                <label class="label cursor-pointer gap-2">
                  <input
                    type="checkbox"
                    :checked="!editProjectIsPrivate"
                    @change="
                      editProjectIsPrivate = !($event.target as HTMLInputElement)
                        .checked
                    "
                    class="toggle toggle-primary"
                  />
                  {{ editProjectIsPrivate ? "Privé" : "Public" }}
                </label>
              </div>
            </fieldset>

            <div class="flex justify-end gap-2 mt-8">
              <button
                type="button"
                class="btn btn-ghost"
                :disabled="isEditing"
                @click="editProjectDialogRef?.close()"
              >
                Annuler
              </button>
              <button
                type="submit"
                class="btn btn-primary flex items-center"
                :disabled="!editProjectTitle?.trim() || isEditing"
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

  <!-- Alerts -->
  <Alert />
</template>

<style scoped>
.btn-primary {
  @apply bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition;
}
</style>
