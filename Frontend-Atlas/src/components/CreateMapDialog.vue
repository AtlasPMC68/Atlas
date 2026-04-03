<script setup lang="ts">
import { ref } from "vue";
import {
  QuestionMarkCircleIcon,
  PaperAirplaneIcon,
} from "@heroicons/vue/24/outline";
import { camelToSnake, snakeToCamel } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";
import type { CreatedMapRef, CreateMapDialogPrefill } from "../typescript/map";

const emit = defineEmits<{
  (e: "created", map: CreatedMapRef | null): void;
  (e: "error", message: string): void;
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);
const newMapTitle = ref<string | undefined>(undefined);
const newMapDescription = ref<string | undefined>(undefined);
const newMapIsPrivate = ref(true);
const isCreating = ref(false);

const { currentUser, fetchCurrentUser } = useCurrentUser();

function open(prefill?: CreateMapDialogPrefill) {
  newMapTitle.value = prefill?.title;
  newMapDescription.value = prefill?.description;
  newMapIsPrivate.value = prefill?.isPrivate ?? true;
  dialogRef.value?.showModal();
}

function close() {
    dialogRef.value?.close();
}

function resetForm() {
  newMapTitle.value = undefined;
  newMapDescription.value = undefined;
  newMapIsPrivate.value = true;
}

function extractCreatedMap(payload: unknown): CreatedMapRef | null {
  if (!payload || typeof payload !== "object") return null;

  const obj = payload as Record<string, unknown>;

  if (typeof obj.id === "string") {
    return { id: obj.id } as CreatedMapRef;
  }

  if (typeof obj.mapId === "string") {
    return { id: obj.mapId } as CreatedMapRef;
  }

  if (typeof obj.map_id === "string") {
    return { id: obj.map_id } as CreatedMapRef;
  }

  if (obj.map && typeof obj.map === "object") {
    const map = obj.map as Record<string, unknown>;

    if (typeof map.id === "string") {
      return { id: map.id } as CreatedMapRef;
    }

    if (typeof map.mapId === "string") {
      return { id: map.mapId } as CreatedMapRef;
    }

    if (typeof map.map_id === "string") {
      return { id: map.map_id } as CreatedMapRef;
    }
  }

  return null;
}

async function createMap() {
  if (!currentUser.value) {
    await fetchCurrentUser();
  }

  if (!currentUser.value) {
    emit("error", "Utilisateur non authentifié.");
    return;
  }

  if (!newMapTitle.value?.trim()) {
    emit("error", "Le titre de la carte est requis.");
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
          title: newMapTitle.value.trim(),
          description: newMapDescription.value?.trim() || undefined,
          isPrivate: newMapIsPrivate.value,
        }),
      ),
    });

    if (!res.ok) {
      throw new Error(`Error creating map: ${res.status}`);
    }

    const rawPayload = await res.json().catch(() => null);
    const payload = rawPayload ? snakeToCamel(rawPayload) : null;
    const createdMap = extractCreatedMap(payload);

    if (!createdMap?.id) {
      throw new Error("Aucun id valide retourné lors de la création de la carte.");
    }

    resetForm();
    close();
    emit("created", createdMap);
  } catch {
    emit("error", "Erreur lors de la création de la carte.");
  } finally {
    isCreating.value = false;
  }
}

defineExpose({
  open,
  close,
});
</script>

<template>
  <dialog ref="dialogRef" class="modal" @close="resetForm">
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
                  <QuestionMarkCircleIcon class="h-4 w-4 text-gray-400" />
                </div>
              </div>

              <label class="label cursor-pointer gap-2">
                <input
                  type="checkbox"
                  :checked="!newMapIsPrivate"
                  @change="
                    newMapIsPrivate = !($event.target as HTMLInputElement).checked
                  "
                  class="toggle toggle-primary"
                />
                {{ newMapIsPrivate ? "Privé" : "Public" }}
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
              :disabled="!newMapTitle?.trim() || isCreating"
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