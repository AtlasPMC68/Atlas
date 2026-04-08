<template>
  <div class="h-screen-minus-header w-full bg-base-100 flex flex-col overflow-hidden">
    <div class="flex flex-1 min-h-0 overflow-hidden">
      <div class="w-80 h-full min-h-0 overflow-hidden bg-base-200 border-r border-base-300 p-3 flex flex-col">
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
          @open-add-image-feature-dialog="addFeatureImageDialog?.showModal()"
          @save-map="onSaveMap"
          @delete-feature="onDeleteFeature"
          @add-map="openAddMapDialog"
          @update-feature="onSaveMap"
        />
      </div>

      <div class="flex-1 min-h-0">
        <MapGeoJSON
          ref="mapGeoJsonRef"
          class="h-full w-full"
          :features="features"
          :feature-visibility="featureVisibility"
          :map-periods="mapPeriods"
          @features-loaded="handleFeaturesLoaded"
          @draw-create="handleDrawChange"
          @draw-update="handleDrawChange"
          @draw-delete="handleDrawChange"
          @draw-delete-id="onDeleteFeature"
          @map-ready="onMapReady"
        />
      </div>
    </div>

    <Alert />
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

  <dialog ref="addMapDialogRef" class="modal">
    <div class="modal-box p-0">
      <form @submit.prevent="createMapForProject">
        <div class="card-body">
          <h3 class="text-lg font-bold">Ajouter une carte au projet</h3>

          <fieldset class="fieldset" :disabled="isCreatingMap">
            <label class="label">Nom de la carte</label>
            <input
              v-model="newMapTitle"
              type="text"
              class="input"
              placeholder="Ex: Carte politique de 1850"
              required
            />
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="label">Date debut</label>
                <input
                  v-if="!usePreciseDates"
                  v-model.number="startYear"
                  type="number"
                  min="1"
                  max="9999"
                  class="input"
                  placeholder="Ex: 1850"
                  required
                />
                <input
                  v-else
                  v-model="startDate"
                  type="date"
                  class="input"
                  required
                />
              </div>

              <div>
                <label class="label">Date fin</label>
                <input
                  v-if="!usePreciseDates"
                  v-model.number="endYear"
                  type="number"
                  min="1"
                  max="9999"
                  class="input"
                  placeholder="Ex: 1900"
                />
                <input
                  v-else
                  v-model="endDate"
                  type="date"
                  class="input"
                />
              </div>
            </div>
          </fieldset>
          <label class="label cursor-pointer gap-2 mb-2">
            <input
              v-model="usePreciseDates"
              type="checkbox"
              class="checkbox checkbox-sm"
            />
            <span>Utiliser la date exacte</span>
          </label>
          <div class="flex justify-end gap-2 mt-6">
            <button
              type="button"
              class="btn btn-ghost"
              :disabled="isCreatingMap"
              @click="addMapDialogRef?.close()"
            >
              Annuler
            </button>
            <button
              type="submit"
              class="btn btn-primary"
              :disabled="!newMapTitle.trim() || !hasValidImportDates() || isCreatingMap"
            >
              <span
                v-if="isCreatingMap"
                class="loading loading-spinner loading-xs"
              ></span>
              <span v-else>Creer et importer</span>
            </button>
          </div>
        </div>
      </form>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isCreatingMap">close</button>
    </form>
  </dialog>
</template>
<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import { Feature } from "../typescript/feature";
import { MapPeriod } from "../typescript/map";
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
const projectRouteId = computed(
  () => (route.params.projectId as string | undefined) ?? null,
);
const projectId = ref<string | null>(null);
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
const addMapDialogRef = ref<HTMLDialogElement | null>(null);
const isAdding = ref(false);
const isCreatingMap = ref(false);
const newMapTitle = ref("");
const startYear = ref<number | null>(null);
const endYear = ref<number | null>(null);
const startDate = ref<string>("");
const endDate = ref<string>("");
const usePreciseDates = ref(false);
const selectedFile = ref<File | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const mapPeriods = ref<MapPeriod[]>([]);

const PERIOD_COLORS = [
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#14b8a6",
  "#e11d48",
  "#84cc16",
];

function getStartDateForImport(): string | null {
  if (usePreciseDates.value) {
    if (!startDate.value) return null;
    const parsed = new Date(startDate.value);
    if (Number.isNaN(parsed.getTime())) return null;
    return startDate.value;
  }

  if (!startYear.value || startYear.value < 1 || startYear.value > 9999) {
    return null;
  }
  return `${String(startYear.value).padStart(4, "0")}-01-01`;
}

function getEndDateForImport(): string | null {
  if (usePreciseDates.value) {
    if (!endDate.value) return null;
    const parsed = new Date(endDate.value);
    if (Number.isNaN(parsed.getTime())) return null;
    return endDate.value;
  }

  if (!endYear.value || endYear.value < 1 || endYear.value > 9999) {
    return null;
  }
  return `${String(endYear.value).padStart(4, "0")}-12-31`;
}

function hasValidImportDates(): boolean {
  const start = getStartDateForImport();
  const end = getEndDateForImport();
  if (!start || !end) return false;
  return start <= end;
}

async function onAddFeatureImage() {
  if (!selectedFile.value || !keycloak.token) {
    onCloseAddFeatureImageDialog();
    return;
  }

  if (!projectId.value) {
    const resolved = await resolveRouteContext();
    if (!resolved || !projectId.value) {
      onCloseAddFeatureImageDialog();
      return;
    }
  }

  isAdding.value = true;
  try {
    const formData = new FormData();
    formData.append("image", selectedFile.value);

    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/projects/${projectId.value}/features/image`,
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
  if (!leafletMap.value || !keycloak.token) return false;

  if (!projectId.value) {
    const resolved = await resolveRouteContext();
    if (!resolved) return false;
  }
  if (!projectId.value) return false;

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
        `${import.meta.env.VITE_API_URL}/projects/${projectId.value}/thumbnail`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${keycloak.token}` },
          body: formData,
        },
      );

      if (!res.ok) {
        console.error("Project thumbnail upload failed:", res.status);
      }
      resolve(res.ok);
    });
  });
}

async function loadProjectIdForMap(): Promise<boolean> {
  if (!projectRouteId.value) return false;
  projectId.value = projectRouteId.value;
  return true;
}

async function loadProjectMapsForTimeline() {
  if (!keycloak.token || !projectId.value) {
    mapPeriods.value = [];
    return;
  }

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/projects/${projectId.value}/maps`,
      {
        method: "GET",
        headers: { Authorization: `Bearer ${keycloak.token}` },
      },
    );
    if (!res.ok) throw new Error("Failed to fetch project maps for timeline");

    const rows = snakeToCamel(
      (await res.json()) as Array<{
        id: string;
        title: string;
        startDate?: string | null;
        endDate?: string | null;
        exactDate?: boolean;
      }>,
    );

    mapPeriods.value = rows.map((row, idx) => ({
      id: row.id,
      title: row.title,
      startDate: row.startDate ?? null,
      endDate: row.endDate ?? null,
      exactDate: Boolean(row.exactDate),
      color: PERIOD_COLORS[idx % PERIOD_COLORS.length],
    }));
  } catch (e) {
    console.error("Failed to load map periods for timeline:", e);
    mapPeriods.value = [];
  }
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

  if (!projectId.value) {
    const resolved = await resolveRouteContext();
    if (!resolved || !projectId.value) {
      const message = "Projet introuvable pour supprimer cet élément.";
      showAlert("error", message);
      callbacks?.onError?.(message);
      return;
    }
  }

  try {
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/projects/${projectId.value}/features/${featureId}`,
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
    console.error("Failed to delete feature:", error);
    callbacks?.onError?.("Erreur lors de la suppression de l'élément.");
  }
}

async function resolveRouteContext(): Promise<boolean> {
  return loadProjectIdForMap();
}

function openAddMapDialog() {
  newMapTitle.value = "";
  startYear.value = null;
  endYear.value = null;
  startDate.value = "";
  endDate.value = "";
  usePreciseDates.value = false;
  addMapDialogRef.value?.showModal();
}

async function createMapForProject() {
  if (!keycloak.token) return;
  const targetProjectId = projectId.value || projectRouteId.value;

  if (!targetProjectId || !newMapTitle.value.trim()) {
    return;
  }
  const startDateForImport = getStartDateForImport();
  const endDateForImport = getEndDateForImport();
  if (!startDateForImport || !endDateForImport) return;
  if (startDateForImport > endDateForImport) return;

  isCreatingMap.value = true;
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/projects/${targetProjectId}/maps`,
      {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${keycloak.token}`,
      },
      body: JSON.stringify(
        camelToSnake({
          title: newMapTitle.value.trim(),
          startDate: startDateForImport,
          endDate: endDateForImport,
          exactDate: usePreciseDates.value,
        }),
      ),
      },
    );

    if (!res.ok) {
      throw new Error(`Error creating map for project: ${res.status}`);
    }

    const payload = snakeToCamel(await res.json()) as { mapId: string };
    addMapDialogRef.value?.close();
    router.push(`/televersement/${payload.mapId}`);
  } catch (e) {
    console.error("Failed to create map for project:", e);
  } finally {
    isCreatingMap.value = false;
  }
}

function reconcileVisibility(list: Feature[]) {
  const next = new Map<string, boolean>(featureVisibility.value);
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
  if (!keycloak.token) {
    return;
  }

  if (!projectId.value) {
    features.value = [];
    featureVisibility.value = new Map();
    return;
  }

  try {
    const endpoint = `${import.meta.env.VITE_API_URL}/projects/${projectId.value}/features`;

    const res = await fetch(endpoint, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
      },
    });
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = snakeToCamel(await res.json()) as Feature[];

    features.value = allFeatures;
    reconcileVisibility(allFeatures);
  } catch (e) {
    console.error("Failed to load initial map features:", e);
    showAlert("error", "Erreur lors du chargement des éléments de la carte.");
  }
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  const next = new Map<string, boolean>(featureVisibility.value);
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
  await resolveRouteContext();
  await loadProjectMapsForTimeline();
  await loadInitialFeatures();
  window.addEventListener("keydown", handleCtrlS);
});

watch([projectRouteId], async () => {
  await resolveRouteContext();
  await loadProjectMapsForTimeline();
  await loadInitialFeatures();
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

    if (!projectId.value) {
      const resolved = await resolveRouteContext();
      if (!resolved || !projectId.value) {
        showAlert("error", "Projet introuvable pour la sauvegarde.");
        return;
      }
    }

    const payload = camelToSnake(prepareFeaturesForSave(features.value));

    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/projects/${projectId.value}/features`,
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
    showAlert("success", "Projet sauvegardée avec succès !");
  } catch (err) {
    showAlert("error", "Erreur lors de la sauvegarde des éléments.");
    throw new Error(
      `Error while saving features: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    isSaving.value = false;
  }
}
</script>
