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
    />
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

const alert = ref<AlertState>(null);

const handleDrawChange = (updatedFeatures: Feature[]) => {
  features.value = updatedFeatures;
  reconcileVisibility(updatedFeatures);
};

const route = useRoute();
const router = useRouter();
const mapId = ref(route.params.mapId as string).value;
const mapGeoJsonRef = ref<{
  syncFeaturesFromMapLayers: () => Feature[];
  clearDraftLayers: () => void;
  resetSelection: () => void;
} | null>(null);
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const isSaving = ref(false);
const pendingDeletions = ref<string[]>([]);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const leafletMap = ref<LeafletMap | null>(null);
const addFeatureImageDialog = ref<HTMLDialogElement | null>(null);
const isAdding = ref(false);
const selectedFile = ref<File | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);

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

function onDeleteFeature(featureId: string) {
  // Non-UUID features are draft-only (never persisted); draw-delete already
  // removed them from features.value via handleDrawChange, nothing else to do.
  if (!isUuid(featureId)) return;

  // Queue the deletion — it will be flushed to the DB on the next save so the
  // user can undo accidental deletions before committing.
  pendingDeletions.value.push(featureId);
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

    features.value = allFeatures;
    reconcileVisibility(allFeatures);
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

function handleFeaturesLoaded(_loadedFeatures: Feature[]) {
  uploadMapThumbnail();
}

const handleCtrlS = (e: KeyboardEvent) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    void onSaveMap();
  }
};

onMounted(async () => {
  await fetchCurrentUser();
  await loadInitialFeatures();
  window.addEventListener("keydown", handleCtrlS);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleCtrlS);
  clearAlert(alert);
});

async function onSaveMap() {
  if (isSaving.value) return;
  isSaving.value = true;
  mapGeoJsonRef.value?.resetSelection();

  try {
    if (!currentUser.value) {
      showAlert(alert, "error", "Utilisateur non authentifié.");
      return;
    }

    const syncedFeatures = mapGeoJsonRef.value?.syncFeaturesFromMapLayers();
    if (syncedFeatures) {
      features.value = syncedFeatures;
      reconcileVisibility(syncedFeatures);
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
    features.value = savedFeatures;
    reconcileVisibility(savedFeatures);

    // Flush queued deletions now that the save succeeded.
    for (const id of pendingDeletions.value) {
      const delResponse = await fetch(
        `${import.meta.env.VITE_API_URL}/maps/features/${mapId}/${id}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${keycloak.token}` },
        },
      );
      if (!delResponse.ok) {
        console.error(`Failed to delete feature ${id}: ${delResponse.status}`);
      }
    }
    pendingDeletions.value = [];

    mapGeoJsonRef.value?.clearDraftLayers();
  } catch (err) {
    showAlert(alert, "error", "Erreur lors de la sauvegarde des éléments.");
    throw new Error(
      `Error while saving features: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    isSaving.value = false;
    showAlert(alert, "success", "Carte sauvegardée avec succès !");
  }
}
</script>
