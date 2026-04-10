<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  QuestionMarkCircleIcon,
  PaperAirplaneIcon,
} from "@heroicons/vue/24/outline";
import { camelToSnake, snakeToCamel } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import type { CreatedProjectRef, CreateProjectDialogPrefill } from "../typescript/project";
import { apiFetch } from "../utils/api";

const emit = defineEmits<{
  (e: "created", project: CreatedProjectRef | null): void;
  (e: "error", message: string): void;
  (e: "closed"): void;
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);
const newProjectTitle = ref<string | undefined>("");
const newProjectDescription = ref<string | undefined>("");
const newProjectIsPrivate = ref(true);
const isCreating = ref(false);
const closeTriggeredByCreate = ref(false);

const { currentUser, fetchCurrentUser, isLoading } = useCurrentUser();

function open(prefill?: CreateProjectDialogPrefill) {
  newProjectTitle.value = prefill?.title;
  newProjectDescription.value = prefill?.description;
  newProjectIsPrivate.value = prefill?.isPrivate ?? true;

  if (!currentUser.value && !isLoading.value) {
    void fetchCurrentUser();
  }

  dialogRef.value?.showModal();
}

function close() {
  dialogRef.value?.close();
}

function resetForm() {
  newProjectTitle.value = undefined;
  newProjectDescription.value = undefined;
  newProjectIsPrivate.value = true;
}

function extractCreatedProject(payload: unknown): CreatedProjectRef | null {
  if (!payload || typeof payload !== "object") return null;

  const obj = payload as Record<string, unknown>;

  if (typeof obj.projectId === "string") {
    return { id: obj.projectId } as CreatedProjectRef;
  }

  if (obj.map && typeof obj.map === "object") {
    const map = obj.map as Record<string, unknown>;

    if (typeof map.projectId === "string") {
      return { id: map.projectId } as CreatedProjectRef;
    }
  }

  return null;
}

async function createProject() {
  if (!currentUser.value) {
    await fetchCurrentUser();
  }

  if (!currentUser.value) {
    emit("error", "Utilisateur non authentifié.");
    return;
  }

  if (!newProjectTitle.value?.trim()) {
    emit("error", "Le titre du projet est requis.");
    return;
  }

  isCreating.value = true;

  try {
    const res = await apiFetch("/projects/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        camelToSnake({
          userId: currentUser.value.id,
          title: newProjectTitle.value.trim(),
          description: newProjectDescription.value?.trim() || undefined,
          isPrivate: newProjectIsPrivate.value,
        }),
      ),
    });

    if (!res.ok) {
      throw new Error(`Error creating project: ${res.status}`);
    }

    const rawPayload = await res.json().catch(() => null);
    const payload = snakeToCamel(rawPayload);
    const createdProject = extractCreatedProject(payload);

    if (!createdProject?.id) {
      throw new Error(
        "Aucun id valide retourné lors de la création du projet.",
      );
    }

    closeTriggeredByCreate.value = true;
    dialogRef.value?.close();
    emit("created", createdProject);
  } catch {
    emit("error", "Erreur lors de la création du projet.");
  } finally {
    isCreating.value = false;
  }
}

function onDialogClose() {
  resetForm();

  if (closeTriggeredByCreate.value) {
    closeTriggeredByCreate.value = false;
    return;
  }

  emit("closed");
}

onMounted(() => {
  if (!currentUser.value) {
    void fetchCurrentUser();
  }
});

defineExpose({
  open,
  close: () => dialogRef.value?.close(),
});
</script>

<template>
  <dialog ref="dialogRef" class="modal" @close="onDialogClose">
    <div class="modal-box p-0">
      <form @submit.prevent="createProject">
        <div class="card-body">
          <h3 class="text-lg font-bold">Créer une nouvelle carte</h3>

          <fieldset class="fieldset" :disabled="isCreating">
            <label class="label">Titre</label>
            <input
              v-model="newProjectTitle"
              type="text"
              class="input"
              placeholder="Titre du projet"
              required
            />

            <label class="label">Description</label>
            <input
              v-model="newProjectDescription"
              type="text"
              class="input"
              placeholder="Description du projet"
            />

            <div class="gap-1">
              <div class="flex items-center gap-1">
                <span class="fieldset-legend">Accès au projet</span>
                <div
                  class="tooltip tooltip-right items-center"
                  data-tip="Les projets publics sont visibles par tous les utilisateurs, tandis que les projets privés ne sont accessibles que par vous."
                >
                  <QuestionMarkCircleIcon class="h-4 w-4 text-gray-400" />
                </div>
              </div>

              <label class="label cursor-pointer gap-2">
                <input
                  type="checkbox"
                  :checked="!newProjectIsPrivate"
                  @change="
                    newProjectIsPrivate = !($event.target as HTMLInputElement)
                      .checked
                  "
                  class="toggle toggle-primary"
                />
                {{ newProjectIsPrivate ? "Privé" : "Public" }}
              </label>
            </div>
          </fieldset>

          <div class="flex justify-end gap-2 mt-8">
            <button
              type="button"
              class="btn btn-ghost"
              :disabled="isCreating"
              @click="close"
            >
              Annuler
            </button>

            <button
              type="submit"
              class="btn btn-primary flex items-center gap-2"
              :disabled="!newProjectTitle?.trim() || isCreating"
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
</template>
