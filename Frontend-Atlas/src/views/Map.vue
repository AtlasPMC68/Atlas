<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end gap-4">
        <SaveDropdown @save="onSaveMap" />
        <button @click="upload(mapId)" class="btn btn-primary">
          Ajouter une carte
        </button>
        <button
          @click="addFeatureImageDialog?.showModal()"
          class="btn btn-primary"
        >
          Ajouter une image
        </button>
        <button class="btn" :disabled="!canUndo" @click="onUndo">
          Undo
        </button>

        <button class="btn" :disabled="!canRedo" @click="onRedo">
          Redo
        </button>
      </div>
    </div>

    <div class="flex flex-1">
      <div class="w-80 bg-base-200 border-r border-base-300 p-4">
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
        />
      </div>

      <div class="flex-1">
        <MapGeoJSON
          ref="mapGeoJsonRef"
          :features="features"
          :feature-visibility="featureVisibility"
          @features-loaded="handleFeaturesLoaded"
          @draw-create="handleDrawChange"
          @draw-update="handleDrawChange"
          @draw-delete="handleDrawChange"
          @draw-delete-id="onDeleteFeature"
          @map-ready="onMapReady"
        />
      </div>
    </div>
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0 translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-200 ease-in"
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
  </div>

  <dialog id="addFeatureImageDialog" ref="addFeatureImageDialog" class="modal">
    <div class="modal-box">
      <h3 class="text-lg font-bold mb-4">Ajouter une image</h3>

      <fieldset class="fieldset">
        <input
          ref="fileInputRef"
          type="file"
          class="file-input file-input-ghost"
          accept="image/*"
          @change="onFileChange"
        />
        <label class="label">Taille maximale de 10MB</label>
      </fieldset>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isAdding"
          @click="onCloseAddFeatureImageDialog"
        >
          Annuler
        </button>
        <button
          class="btn btn-primary"
          :disabled="isAdding || !selectedFile"
          @click="onAddFeatureImage"
        >
          <span
            v-if="isAdding"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Ajouter</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isAdding">close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import { Feature } from "../typescript/feature";
import {
  camelToSnake,
  prepareFeaturesForSave,
  snakeToCamel,
} from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";
import leafletImage from "leaflet-image";
import type { Map as LeafletMap } from "leaflet";
import type { AlertState } from "../typescript/alert";
import { showAlert, clearAlert } from "../utils/alert";
import { FeatureHistoryService } from "../services/FeatureHistoryService";

const alert = ref<AlertState>(null);

const route = useRoute();
const router = useRouter();
const mapId = ref(route.params.mapId as string).value;
const mapGeoJsonRef = ref<{
  syncFeaturesFromMapLayers: () => Feature[];
  clearDraftLayers: () => void;
} | null>(null);
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const isSaving = ref(false);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const leafletMap = ref<LeafletMap | null>(null);
const addFeatureImageDialog = ref<HTMLDialogElement | null>(null);
const isAdding = ref(false);
const selectedFile = ref<File | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);

const featureHistoryService = new FeatureHistoryService(5);
const canUndo = featureHistoryService.canUndo;
const canRedo = featureHistoryService.canRedo;
const trackingEnabled = featureHistoryService.trackingEnabled;

const handleDrawChange = (updatedFeatures: Feature[]) => {
  if (!trackingEnabled.value) {
    return;
  }

  commitFeatureSnapshot(updatedFeatures);
};

function applyFeatureSnapshot(next: Feature[], track = true) {
  const apply = () => {
    features.value = next;
    reconcileVisibility(next);
  };

  if (track) {
    apply();
    return;
  }

  featureHistoryService.withoutTracking(apply);
}

function commitFeatureSnapshot(next: Feature[]) {
  applyFeatureSnapshot(featureHistoryService.commit(features.value, next));
}

function onUndo() {
  if (!canUndo.value) return;
  applyFeatureSnapshot(featureHistoryService.undo(features.value), false);
}

function onRedo() {
  if (!canRedo.value) return;
  applyFeatureSnapshot(featureHistoryService.redo(features.value), false);
}

async function onAddFeatureImage() {
  if (!selectedFile.value || !keycloak.token) {
    onCloseAddFeatureImageDialog();
    return;
  }

  isAdding.value = true;
  try {
    const formData = new FormData();
    formData.append("image", selectedFile.value);
    formData.append("map_id", mapId);

    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/${mapId}/features/image`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${keycloak.token}` },
        body: formData,
      },
    );

    if (!res.ok) {
      throw new Error(`HTTP error : ${res.status}`);
    }

    await loadInitialFeatures();
    selectedFile.value = null;
    onCloseAddFeatureImageDialog();
  } catch (e) {
    console.error("Upload image failed:", e);
  } finally {
    isAdding.value = false;
  }
}

function onMapReady(map: LeafletMap) {
  leafletMap.value = map;
}

function onCloseAddFeatureImageDialog() {
  isAdding.value = false;
  selectedFile.value = null;
  if (fileInputRef.value) {
    fileInputRef.value.value = "";
  }
  addFeatureImageDialog.value?.close();
}

function onFileChange() {
  const input = fileInputRef.value;
  selectedFile.value = input?.files?.[0] ?? null;
}

async function uploadMapThumbnail(): Promise<boolean> {
  if (!leafletMap.value || !mapId || !keycloak.token) return false;

  await new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  );

  return await new Promise<boolean>((resolve) => {
    leafletImage(leafletMap.value as LeafletMap, async (err, canvas) => {
      if (err || !canvas) return resolve(false);

      const blob = await new Promise<Blob | null>((r) =>
        canvas.toBlob(r, "image/png"),
      );
      if (!blob) return resolve(false);

      const formData = new FormData();
      formData.append("image", blob);

      const res = await fetch(
        `${import.meta.env.VITE_API_URL}/maps/${mapId}/thumbnail`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${keycloak.token}` },
          body: formData,
        },
      );

      resolve(res.ok);
    });
  });
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  );
}

async function onDeleteFeature(
  featureId: string,
  callbacks?: {
    onSuccess?: () => void;
    onError?: (message?: string) => void;
  },
) {
  if (!isUuid(featureId)) {
    callbacks?.onSuccess?.();
    return;
  }

  if (!currentUser.value) {
    const message = "Utilisateur non authentifié.";
    showAlert(alert, "error", message);
    callbacks?.onError?.(message);
    return;
  }

  try {
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId}/${featureId}`,
      {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${keycloak.token}`,
        },
      },
    );

    if (!response.ok) {
      throw new Error(`Error deleting feature: ${response.status}`);
    }

    callbacks?.onSuccess?.();
  } catch (error) {
    const message = "Erreur lors de la suppression de l'élément.";
    showAlert(alert, "error", message);
    console.error("Failed to delete feature from API:", error);
    callbacks?.onError?.(message);
  }
}

function reconcileVisibility(list: Feature[]) {
  const next = new Map(featureVisibility.value);
  for (const f of list) {
    const id = f?.id;
    if (id != null && next.get(id) === undefined) {
      next.set(id, true);
    }
  }
  const ids = new Set(list.map((f) => f.id));
  for (const k of next.keys()) {
    if (!ids.has(k)) next.delete(k);
  }
  featureVisibility.value = next;
}

async function loadInitialFeatures() {
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId}`,
    );
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = snakeToCamel(await res.json()) as Feature[];

    applyFeatureSnapshot(featureHistoryService.reset(allFeatures), false);
  } catch (e) {
    console.error("Failed to load initial map features:", e);
    showAlert(
      alert,
      "error",
      "Erreur lors du chargement des éléments de la carte.",
    );
  }
}

function upload(mapId: string) {
  router.push(`/televersement/${mapId}`);
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  const next = new Map(featureVisibility.value);
  next.set(featureId, visible);
  featureVisibility.value = next;
}

function handleFeaturesLoaded(_loadedFeatures: Feature[]) {}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;

  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
}

const handleKeyboardShortcuts = (e: KeyboardEvent) => {
  if (isEditableTarget(e.target)) {
    return;
  }

  const isMod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();

  if (isMod && key === "s") {
    e.preventDefault();
    void onSaveMap();
    return;
  }

  if (isMod && !e.shiftKey && key === "z") {
    e.preventDefault();
    onUndo();
    return;
  }

  if ((isMod && key === "y") || (isMod && e.shiftKey && key === "z")) {
    e.preventDefault();
    onRedo();
  }
};

onMounted(async () => {
  await fetchCurrentUser();
  await loadInitialFeatures();
  window.addEventListener("keydown", handleKeyboardShortcuts);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeyboardShortcuts);
  clearAlert(alert);
});

async function onSaveMap() {
  if (isSaving.value) return;
  isSaving.value = true;

  try {
    if (!currentUser.value) {
      showAlert(alert, "error", "Utilisateur non authentifié.");
      return;
    }

    const syncedFeatures = mapGeoJsonRef.value?.syncFeaturesFromMapLayers();
    if (syncedFeatures) {
      applyFeatureSnapshot(syncedFeatures, false);
    }

    const payload = camelToSnake(prepareFeaturesForSave(features.value));

    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId}`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: JSON.stringify(payload),
      },
    );

    if (!response.ok) {
      showAlert(alert, "error", "Erreur lors de la sauvegarde des éléments.");
      throw new Error(`Error saving features: ${response.status}`);
    }

    const savedFeatures = snakeToCamel(await response.json()) as Feature[];
    applyFeatureSnapshot(featureHistoryService.reset(savedFeatures), false);

    mapGeoJsonRef.value?.clearDraftLayers();
  } catch (err) {
    showAlert(alert, "error", "Erreur lors de la sauvegarde des éléments.");
    throw new Error(
      `Error while saving features: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    isSaving.value = false;
    await uploadMapThumbnail();
    showAlert(alert, "success", "Carte sauvegardée avec succès !");
  }
}
</script>
