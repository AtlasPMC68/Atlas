<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end gap-4">
        <SaveDropdown @save="saveMap" />
        <button @click="openAddMapDialog" class="btn btn-primary">
          Ajouter une carte
        </button>
        <button
          @click="addFeatureImageDialog?.showModal()"
          class="btn btn-primary"
          :disabled="!hasActiveMap"
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
import { ref, onMounted, computed, onUnmounted } from "vue";
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
const mapRouteId = ref((route.params.mapId as string | undefined) ?? null).value;
const projectRouteId = ref((route.params.projectId as string | undefined) ?? null).value;
const activeMapId = ref<string | null>(null);
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
const hasActiveMap = computed(() => Boolean(activeMapId.value));
const mapPeriods = ref<
  Array<{
    id: string;
    title: string;
    startDate: string | null;
    endDate: string | null;
    exactDate: boolean;
    color: string;
  }>
>([]);

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
  if (!selectedFile.value || !keycloak.token || !activeMapId.value) {
    onCloseAddFeatureImageDialog();
    return;
  }

  isAdding.value = true;
  try {
    const formData = new FormData();
    formData.append("image", selectedFile.value);
    formData.append("map_id", activeMapId.value);

    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/${activeMapId.value}/features/image`,
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
        `${import.meta.env.VITE_API_URL}/maps/${projectId.value}/thumbnail`,
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
  if (!keycloak.token) return false;

  if (projectRouteId) {
    projectId.value = projectRouteId;
    activeMapId.value = null;
    return true;
  }

  if (!mapRouteId) return false;

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/map-project/${mapRouteId}`,
      {
        method: "GET",
        headers: { Authorization: `Bearer ${keycloak.token}` },
      },
    );

    if (!res.ok) return false;

    const payload = snakeToCamel(await res.json()) as { projectId: string };
    projectId.value = payload.projectId;
    activeMapId.value = mapRouteId;
    return Boolean(projectId.value);
  } catch {
    return false;
  }
}

async function loadProjectMapsForTimeline() {
  if (!keycloak.token || !projectId.value) {
    mapPeriods.value = [];
    return;
  }

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/projects/${projectId.value}/maps`,
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
    features.value = features.value.filter((feature) => feature.id !== featureId);
    reconcileVisibility(features.value);
    callbacks?.onSuccess?.();
    return;
  }

  if (!currentUser.value) {
    const message = "Utilisateur non authentifié.";
    showAlert(alert, "error", message);
    callbacks?.onError?.(message);
    return;
  }

  if (!activeMapId.value) {
    const message = "Aucune carte active pour supprimer cet élément.";
    showAlert(alert, "error", message);
    callbacks?.onError?.(message);
    return;
  }

  try {
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${activeMapId.value}/${featureId}`,
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

    features.value = features.value.filter((feature) => feature.id !== featureId);
    reconcileVisibility(features.value);

    callbacks?.onSuccess?.();
  } catch (error) {
    const message = "Erreur lors de la suppression de l'élément.";
    showAlert(alert, "error", message);
    console.error("Failed to delete feature from API:", error);
    callbacks?.onError?.(message);
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
  const targetProjectId = projectId.value || projectRouteId;

  if (!targetProjectId || !newMapTitle.value.trim()) {
    return;
  }
  const startDateForImport = getStartDateForImport();
  const endDateForImport = getEndDateForImport();
  if (!startDateForImport || !endDateForImport) return;
  if (startDateForImport > endDateForImport) return;

  isCreatingMap.value = true;
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${keycloak.token}`,
      },
      body: JSON.stringify(
        camelToSnake({
          projectId: targetProjectId,
          title: newMapTitle.value.trim(),
          startDate: startDateForImport,
          endDate: endDateForImport,
          exactDate: usePreciseDates.value,
        }),
      ),
    });

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

  if (!activeMapId.value && !projectId.value) {
    features.value = [];
    featureVisibility.value = new Map();
    return;
  }

  try {
    const endpoint = activeMapId.value
      ? `${import.meta.env.VITE_API_URL}/maps/features/${activeMapId.value}`
      : `${import.meta.env.VITE_API_URL}/maps/projects/${projectId.value}/features`;

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
    showAlert(
      alert,
      "error",
      "Erreur lors du chargement des éléments de la carte.",
    );
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

onUnmounted(() => {
  window.removeEventListener("keydown", handleCtrlS);
  clearAlert(alert);
});

function saveMap() {
  void onSaveMap();
}

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
      features.value = syncedFeatures;
      reconcileVisibility(syncedFeatures);
    }

    if (!activeMapId.value) {
      showAlert(alert, "error", "Aucune carte active à sauvegarder.");
      return;
    }

    const payload = camelToSnake(prepareFeaturesForSave(features.value));

    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${activeMapId.value}`,
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

    mapGeoJsonRef.value?.clearDraftLayers();
    showAlert(alert, "success", "Carte sauvegardée avec succès !");
  } catch (err) {
    showAlert(alert, "error", "Erreur lors de la sauvegarde des éléments.");
    console.error("Error while saving features:", err);
  } finally {
    isSaving.value = false;
  }
}
</script>
