<template>
  <div class="h-full w-full bg-base-100 flex flex-col">
    <div class="flex flex-1 min-h-0">
      <div class="w-80 bg-base-200 border-r border-base-300 min-h-0">
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
          @open-add-image-feature-dialog="addFeatureImageDialog?.showModal()"
          @save-map="onSaveMap"
          @delete-feature="onDeleteFeature"
          @add-map="upload(mapId)"
          @update-feature="onSaveMap"
        />
      </div>
      <div class="flex-1 min-h-0 flex flex-col">
        <div class="flex-1 min-h-0 relative h-full w-full">
          <MapGeoJSON
            class="h-full w-full"
            :features="features"
            :feature-visibility="featureVisibility"
            :selected-year="selectedYear"
            @features-loaded="handleFeaturesLoaded"
            @draw-create="handleDrawChange"
            @draw-update="handleDrawChange"
            @draw-delete-id="onDeleteFeature"
            @map-ready="onMapReady"
          />
          <div class="absolute bottom-4 left-4 z-[1001] pointer-events-auto">
            <Legend :zone-features="zoneFeatures" />
          </div>
        </div>

        <TimelineSlider v-model:year="selectedYear" />
      </div>
    </div>
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
  <Alert />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import TimelineSlider from "../components/TimelineSlider.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import Legend from "../components/legend/Legend.vue";
import { Feature } from "../typescript/feature";
import {
  camelToSnake,
  prepareFeaturesForSave,
  snakeToCamel,
} from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";
import leafletImage from "leaflet-image";
import { type Map as LeafletMap } from "leaflet";
import Alert from "../components/Alert.vue";
import { clearAlert, showAlert } from "../composables/useAlert";

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
} | null>(null);
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const selectedYear = ref(1740);
const isSaving = ref(false);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const leafletMap = ref<LeafletMap | null>(null);
const addFeatureImageDialog = ref<HTMLDialogElement | null>(null);
const isAdding = ref(false);
const selectedFile = ref<File | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);

const zoneFeatures = computed(() =>
  features.value.filter((f) => f.properties?.mapElementType === "zone"),
);

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
  // TODO : remove optional
  callbacks: {
    onSuccess?: () => void;
    onError?: (message?: string) => void;
  },
) {
  if (!isUuid(featureId)) {
    features.value = features.value.filter(
      (feature) => feature.id !== featureId,
    );
    reconcileVisibility(features.value);
    callbacks?.onSuccess?.();
    return;
  }

  if (!currentUser.value) {
    const message = "Utilisateur non authentifié.";
    showAlert("error", message);
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

    features.value = features.value.filter(
      (feature) => feature.id !== featureId,
    );
    reconcileVisibility(features.value);

    callbacks?.onSuccess?.();
  } catch (error) {
    const message = "Erreur lors de la suppression de l'élément.";
    console.error("Failed to delete feature:", error);
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

    features.value = allFeatures;
    reconcileVisibility(allFeatures);
  } catch (e) {
    console.error("Failed to load initial map features:", e);
    showAlert("error", "Erreur lors du chargement des éléments de la carte.");
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
  clearAlert();
});

async function onSaveMap() {
  if (isSaving.value) return;
  isSaving.value = true;

  try {
    if (!currentUser.value) {
      showAlert("error", "Utilisateur non authentifié.");
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
      showAlert("error", "Erreur lors de la sauvegarde des éléments.");
      throw new Error(`Error saving features: ${response.status}`);
    }

    const savedFeatures = snakeToCamel(await response.json()) as Feature[];
    features.value = savedFeatures;
    reconcileVisibility(savedFeatures);

    mapGeoJsonRef.value?.clearDraftLayers();
  } catch (err) {
    showAlert("error", "Erreur lors de la sauvegarde des éléments.");
    throw new Error(
      `Error while saving features: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    isSaving.value = false;
    showAlert("success", "Carte sauvegardée avec succès !");
  }
}
</script>
