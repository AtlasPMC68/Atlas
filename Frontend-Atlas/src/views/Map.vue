<template>
  <div
    class="h-screen-minus-header w-full bg-base-100 flex flex-col overflow-hidden"
  >
    <div class="flex flex-1 min-h-0 overflow-hidden">
      <div
        class="w-80 h-full min-h-0 overflow-hidden bg-base-200 border-r border-base-300 p-3 flex flex-col"
      >
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
          @open-add-image-feature-dialog="addFeatureImageDialogRef?.open()"
          @save-map="onSaveMap"
          @delete-feature="onDeleteFeature"
          @add-map="openAddMapDialog"
          @update-feature="onSaveMap"
        />
      </div>
      <div class="flex-1 min-h-0 flex flex-col overflow-hidden">
        <div class="flex-1 relative min-h-0 h-full w-full">
          <MapGeoJSON
            ref="mapGeoJsonRef"
            class="flex-1 min-h-0 w-full"
            :features="filteredFeatures"
            :selected-year="selectedYear"
            :feature-visibility="featureVisibility"
            :map-periods="mapPeriods"
            :project-id="projectId || projectRouteId || ''"
            @features-loaded="handleFeaturesLoaded"
            @draw-create="handleDrawChange"
            @draw-update="handleDrawChange"
            @draw-delete="handleDrawChange"
            @draw-delete-id="onDeleteFeature"
            @map-ready="onMapReady"
          />
          <div class="absolute bottom-4 left-4 z-[1001]">
            <Legend
              :zone-features="zoneFeatures"
              :feature-visibility="featureVisibility"
            />
          </div>
        </div>
        <div
          class="map-timeline-toolbar flex flex-col gap-1 px-3 py-1.5 bg-base-100 border-t border-base-300"
        >
          <div class="map-timeline-slider w-full min-w-0">
            <TimelineSlider
              v-model:year="selectedYear"
              @exact-date-change="onExactDateChange"
              :min="timelineMinYear"
              :max="timelineMaxYear"
              :marker-years="timelineMarkerYears"
              :map-periods="enrichedPeriods"
              :current-exact-date="selectedExactDate"
            />
          </div>
          <div
            class="map-timeline-filter flex flex-row gap-1 items-center text-xs font-medium whitespace-nowrap"
          >
            <span>Filtrer par date</span>
            <input
              v-model="useTimelineFilter"
              type="checkbox"
              aria-label="Filtrer par date"
              role="switch"
              class="timeline-filter-toggle"
            />
          </div>
        </div>
      </div>
    </div>

    <Alert />
  </div>

  <AddImageDialog
    ref="addFeatureImageDialogRef"
    :is-adding="isAdding"
    @submit="onAddFeatureImage"
  />

  <AddMapDialog
    ref="addMapDialogRef"
    :is-creating-map="isCreatingMap"
    @submit="createMapForProject"
  />
</template>
<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AddImageDialog from "../components/add/AddImage.vue";
import AddMapDialog from "../components/add/AddMap.vue";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import TimelineSlider from "../components/TimelineSlider.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import Legend from "../components/legend/Legend.vue";
import { Feature } from "../typescript/feature";
import { MapPeriod, PERIOD_COLORS } from "../typescript/map";
import type { SliderPeriod } from "../typescript/map";
import {
  camelToSnake,
  isUuid,
  prepareFeaturesForSave,
  snakeToCamel,
} from "../utils/utils";
import { toYear } from "../utils/dateUtils";
import { apiFetch } from "../utils/api";
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
const addMapDialogRef = ref<{
  open: () => void;
  close: () => void;
} | null>(null);
const addFeatureImageDialogRef = ref<{
  open: () => void;
  close: () => void;
} | null>(null);
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const isSaving = ref(false);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const leafletMap = ref<LeafletMap | null>(null);
const isAdding = ref(false);
const isCreatingMap = ref(false);
const mapPeriods = ref<MapPeriod[]>([]);

const zoneFeatures = computed(() =>
  filteredFeatures.value.filter((f) => f.properties?.mapElementType === "zone"),
);

const selectedYear = ref(-1);
const selectedExactDate = ref<string | null>(null);
const useTimelineFilter = ref(false);

const enrichedPeriods = computed((): SliderPeriod[] =>
  mapPeriods.value
    .map((p) => ({
      ...p,
      startYear: toYear(p.startDate),
      endYear: toYear(p.endDate),
    }))
    .filter((p): p is SliderPeriod => p.startYear != null && p.endYear != null),
);

const periodByMapId = computed(
  () => new Map(enrichedPeriods.value.map((p) => [p.id, p])),
);

const timelineMinYear = computed(() =>
  enrichedPeriods.value.length
    ? Math.min(...enrichedPeriods.value.map((p) => p.startYear))
    : 1400,
);

const timelineMaxYear = computed(() =>
  enrichedPeriods.value.length
    ? Math.max(...enrichedPeriods.value.map((p) => p.endYear))
    : new Date().getFullYear(),
);

const timelineMarkerYears = computed(() => {
  const markers = new Set<number>([
    timelineMinYear.value,
    timelineMaxYear.value,
  ]);
  enrichedPeriods.value.forEach((p) => {
    markers.add(p.startYear);
    markers.add(p.endYear);
  });
  return [...markers].sort((a, b) => a - b);
});

const filteredFeatures = computed(() => {
  return features.value.filter((feature: Feature) => {
    if (!useTimelineFilter.value) return true;

    // Project-level features without a map are always visible in timeline mode.
    if (!feature.mapId) return true;

    const period = periodByMapId.value.get(feature.mapId);
    if (!period) return true;

    if (selectedExactDate.value && period.startDate && period.endDate) {
      return (
        period.startDate <= selectedExactDate.value &&
        period.endDate >= selectedExactDate.value
      );
    }

    if (period.startYear == null || period.endYear == null) return true;
    return (
      period.startYear <= selectedYear.value &&
      period.endYear >= selectedYear.value
    );
  });
});

function onExactDateChange(nextDate: string | null) {
  selectedExactDate.value = nextDate;
}

async function onAddFeatureImage(file: File) {
  if (!keycloak.token) {
    addFeatureImageDialogRef.value?.close();
    return;
  }

  if (!projectId.value) {
    const resolved = await resolveRouteContext();
    if (!resolved || !projectId.value) {
      addFeatureImageDialogRef.value?.close();
      return;
    }
  }

  isAdding.value = true;
  try {
    const formData = new FormData();
    formData.append("image", file);

    const res = await apiFetch(`/projects/${projectId.value}/features/image`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      throw new Error(`HTTP error : ${res.status}`);
    }

    await loadInitialFeatures();
    addFeatureImageDialogRef.value?.close();
  } catch (e) {
    console.error("Upload image failed:", e);
  } finally {
    isAdding.value = false;
  }
}

function onMapReady(map: LeafletMap) {
  leafletMap.value = map;
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

      const res = await apiFetch(`/projects/${projectId.value}/thumbnail`, {
        method: "POST",
        body: formData,
      });

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
    const res = await apiFetch(`/projects/${projectId.value}/maps`);
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
    const response = await apiFetch(
      `/projects/${projectId.value}/features/${featureId}`,
      { method: "DELETE" },
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
  addMapDialogRef.value?.open();
}

async function createMapForProject(formPayload: {
  title: string;
  startDate: string;
  endDate: string;
  exactDate: boolean;
}) {
  if (!keycloak.token) return;
  const targetProjectId = projectId.value || projectRouteId.value;

  if (!targetProjectId || !formPayload.title.trim()) {
    return;
  }
  if (formPayload.startDate > formPayload.endDate) return;

  isCreatingMap.value = true;
  try {
    const res = await apiFetch(`/projects/${targetProjectId}/maps`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        camelToSnake({
          title: formPayload.title.trim(),
          startDate: formPayload.startDate,
          endDate: formPayload.endDate,
          exactDate: formPayload.exactDate,
        }),
      ),
    });

    if (!res.ok) {
      throw new Error(`Error creating map for project: ${res.status}`);
    }

    const payload = snakeToCamel(await res.json()) as { mapId: string };
    addMapDialogRef.value?.close();
    router.push(`/televersement/${payload.mapId}?projectId=${targetProjectId}`);
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
    const res = await apiFetch(`/projects/${projectId.value}/features`);
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

watch([timelineMinYear, timelineMaxYear], () => {
  if (selectedYear.value < timelineMinYear.value) {
    selectedYear.value = timelineMinYear.value;
  }
  if (selectedYear.value > timelineMaxYear.value) {
    selectedYear.value = timelineMaxYear.value;
  }
});

watch(
  timelineMarkerYears,
  (markers) => {
    if (!markers.length) return;
    if (!markers.includes(selectedYear.value)) {
      selectedYear.value = markers[0];
    }
  },
  { immediate: true },
);

onUnmounted(() => {
  window.removeEventListener("keydown", handleCtrlS);
  clearAlert();
});

async function onSaveMap() {
  if (isSaving.value) return;
  isSaving.value = true;

  try {
    if (!keycloak.token) {
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

    const response = await apiFetch(`/projects/${projectId.value}/features`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

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

<style>
.timeline-filter-toggle {
  appearance: none;
  width: 2.25rem;
  height: 1.25rem;
  border-radius: 9999px;
  border: 1px solid var(--color-base-300);
  background-color: var(--color-base-300);
  position: relative;
  cursor: pointer;
  transition:
    background-color 150ms ease,
    border-color 150ms ease;
}

.timeline-filter-toggle::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 2px;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 9999px;
  background-color: var(--color-primary-content);
  transform: translate(0, -50%);
  transition:
    transform 150ms ease,
    background-color 150ms ease;
}

.timeline-filter-toggle:checked {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}

.timeline-filter-toggle:checked::before {
  background-color: var(--color-primary-content);
  transform: translate(1rem, -50%);
}

.timeline-filter-toggle:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
</style>
