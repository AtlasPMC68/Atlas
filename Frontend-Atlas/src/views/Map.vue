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
      <div class="flex-1 min-h-0 flex flex-col">
        <div class="flex-1 relative min-h-0 h-full w-full">
          <MapGeoJSON
            ref="mapGeoJsonRef"
            class="flex-1 min-h-0 w-full"
            :features="filteredFeatures"
            :feature-visibility="featureVisibility"
            :selected-year="selectedYear"
            :map-periods="mapPeriods"
            :project-id="projectId || projectRouteId || ''"
            :can-undo="canUndo"
            :can-redo="canRedo"
            @draw-create="handleDrawChange"
            @draw-update="handleDrawChange"
            @draw-delete="handleDrawChange"
            @map-ready="onMapReady"
            @undo="onUndo"
            @redo="onRedo"
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

  <CreateProjectDialog
      ref="createProjectDialogRef"
      @created="onProjectCreated"
      @error="onCreateProjectError"
      @closed="onCreateProjectDialogClosed"
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
import L, { type Map as LeafletMap } from "leaflet";
import Alert from "../components/Alert.vue";
import { clearAlert, showAlert } from "../composables/useAlert";
import { FeatureHistoryService } from "../services/FeatureHistoryService";
import type {
  CreatedProjectRef,
  CreateProjectDialogExposed,
} from "../typescript/project";
import CreateProjectDialog from "../components/CreateProjectDialog.vue";

const route = useRoute();
const router = useRouter();
const projectRouteId = computed(
  () => (route.params.projectId as string | undefined) ?? null,
);
const projectId = ref<string | null>(null);
const mapGeoJsonRef = ref<{
  syncFeaturesFromMapLayers: () => Feature[];
  clearDraftLayers: () => void;
  resetSelection: () => void;
} | null>(null);
const addMapDialogRef = ref<{
  open: () => void;
  close: () => void;
} | null>(null);
const addFeatureImageDialogRef = ref<{
  open: () => void;
  close: () => void;
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
const pendingDeletions = ref<string[]>([]);
const persistedFeatureIds = ref<Set<string>>(new Set());
const isSaving = ref(false);
const pendingDeletions = ref<string[]>([]);
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

const createProjectDialogRef = ref<CreateProjectDialogExposed | null>(null);
const pendingCopiedFeatures = ref<Feature[] | null>(null);
const shouldSaveAfterCopy = ref(false);

const currentMapTitle = ref<string | undefined>(undefined);
const currentMapDescription = ref<string | undefined>(undefined);

const featureHistoryService = new FeatureHistoryService(5);
const canUndo = featureHistoryService.canUndo;
const canRedo = featureHistoryService.canRedo;
const trackingEnabled = featureHistoryService.trackingEnabled;

function handleDrawChange(updatedFeatures: Feature[]) {
  if (trackingEnabled.value) {
    commitFeatureSnapshot(updatedFeatures);
  } else {
    applyFeatureSnapshot(updatedFeatures, false);
  }
}

function applyFeatureSnapshot(next: Feature[], track = true) {
  const apply = () => {
    features.value = next;
    reconcileVisibility(next);

    const currentUuidIds = new Set(
      next
        .map((feature) => String(feature.id))
        .filter((id) => isUuid(id)),
    );

    pendingDeletions.value = [...persistedFeatureIds.value].filter(
      (id) => !currentUuidIds.has(id),
    );
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

function getImageNaturalSize(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve({ width: 1, height: 1 }); // fallback: square, backend will recompute
    };
    img.src = url;
  });
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

    // Spawn the image at the center of the user's current map view instead of [0,0].
    // Use the same 16° height constant as the backend, preserving the image aspect ratio.
    if (leafletMap.value) {
      const LAT_SPAN = 16.0;
      const { width, height } = await getImageNaturalSize(file);
      // Divide by cos(lat) to correct for Mercator: longitude degrees get physically
      // shorter away from the equator, so we need more of them to cover the same
      // screen width. Without this, images appear horizontally squished at high latitudes.
      const center = leafletMap.value.getCenter();
      const latRad = center.lat * (Math.PI / 180);
      const lngSpan = (LAT_SPAN * (width / height)) / Math.cos(latRad);
      const bounds = [
        [center.lat - LAT_SPAN / 2, center.lng - lngSpan / 2],
        [center.lat + LAT_SPAN / 2, center.lng + lngSpan / 2],
      ];
      formData.append("bounds", JSON.stringify(bounds));
    }

    const res = await apiFetch(`/projects/${projectId.value}/features/image`, {
      method: "POST",
      headers: { Authorization: `Bearer ${keycloak.token}` },
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

async function onMapReady(map: LeafletMap) {
  leafletMap.value = map;
}

async function uploadMapThumbnail(targetProjectId?: string): Promise<boolean> {
  if (!leafletMap.value || !keycloak.token) return false;

  const resolvedProjectId = targetProjectId ?? projectId.value;

  if (!resolvedProjectId && !targetProjectId) {
    const resolved = await resolveRouteContext();
    if (!resolved) return false;
  }

  const uploadProjectId = resolvedProjectId ?? projectId.value;
  if (!uploadProjectId) return false;

  await new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  );

  const removedLayers: L.Layer[] = [];

  leafletMap.value.eachLayer((layer) => {
    if (layer instanceof L.Marker && layer.options.icon instanceof L.DivIcon) {
      removedLayers.push(layer);
    }
  });

  removedLayers.forEach((layer) => leafletMap.value?.removeLayer(layer));

  return await new Promise<boolean>((resolve) => {
    leafletImage(leafletMap.value as LeafletMap, async (err, canvas) => {
      try {
        if (err || !canvas) return resolve(false);

        const blob = await new Promise<Blob | null>((r) =>
          canvas.toBlob(r, "image/png"),
        );
        if (!blob) return resolve(false);

        const formData = new FormData();
        formData.append("image", blob);

        const res = await apiFetch(`/projects/${uploadProjectId}/thumbnail`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          console.error("Project thumbnail upload failed:", res.status);
        }
        resolve(res.ok);
        resolve(res.ok);
      } finally {
        removedLayers.forEach((layer) => leafletMap.value?.addLayer(layer));
      }
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
  try {
    const nextFeatures = features.value.filter(
      (feature) => feature.id !== featureId,
    );

    if (trackingEnabled.value) {
      commitFeatureSnapshot(nextFeatures);
    } else {
      applyFeatureSnapshot(nextFeatures, false);
    }

    callbacks?.onSuccess?.();
  } catch (error) {
    console.error("Failed to delete feature:", error);
    callbacks?.onError?.("Erreur lors de la suppression de l'élément.");
  }
}

async function resolveRouteContext(): Promise<boolean> {
  return loadProjectIdForMap();
}

async function requireProjectId(): Promise<string> {
  if (projectId.value) {
    return projectId.value;
  }

  const resolved = await resolveRouteContext();
  if (!resolved || !projectId.value) {
    throw new Error("Can't find project.");
  }

  return projectId.value;
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
  const targetProjectId = projectId.value;

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

    persistedFeatureIds.value = new Set(
      allFeatures
        .map((feature) => String(feature.id))
        .filter((id) => isUuid(id)),
    );
    applyFeatureSnapshot(featureHistoryService.reset(allFeatures), false);
    pendingDeletions.value = [];
  } catch (e) {
    console.error("Failed to load initial map features:", e);
    showAlert("error", "Erreur lors du chargement des éléments de la carte.");
  }
}

async function loadCurrentMapInfo(): Promise<void> {
  try {
    const res = await apiFetch(`/projects/${projectId.value}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
      },
    });

    if (!res.ok) {
      throw new Error(`Failed to fetch map info: ${res.status}`);
    }

    const map = snakeToCamel(await res.json()) as {
      title?: string;
      description?: string;
    };

    currentMapTitle.value = map.title ?? undefined;
    currentMapDescription.value = map.description ?? undefined;
  } catch (err) {
    console.error("Failed to load current map info:", err);
    currentMapTitle.value = undefined;
    currentMapDescription.value = undefined;
  }
}

async function openCreateCopyDialog() {
  await loadCurrentMapInfo();

  createProjectDialogRef.value?.open({
    title: currentMapTitle.value,
    description: currentMapDescription.value,
    isPrivate: true,
  });
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  const next = new Map<string, boolean>(featureVisibility.value);
  next.set(featureId, visible);
  featureVisibility.value = next;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;

  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
}

async function isProjectOwner(targetProjectId: string): Promise<boolean> {
  if (!targetProjectId || !keycloak.token) {
    return false;
  }

  try {
    const res = await apiFetch(`/projects/is-owner/${targetProjectId}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
      },
    });

    if (!res.ok) {
      console.error(`Error checking project owner: ${res.status}`);
      return false;
    }

    const data = (await res.json()) as boolean;
    return data === true;
  } catch (err) {
    console.error("Error checking project owner:", err);
    return false;
  }
}

function onCreateProjectError(message: string) {
  showAlert("error", message);
}

function onCreateProjectDialogClosed() {
  pendingCopiedFeatures.value = null;
  shouldSaveAfterCopy.value = false;
}

async function onProjectCreated(project: CreatedProjectRef | null) {
  if (!project?.id) {
    pendingCopiedFeatures.value = null;
    shouldSaveAfterCopy.value = false;

    showAlert(
      "error",
      "La nouvelle carte a été créée, mais aucun identifiant valide n'a été retourné.",
    );
    return;
  }

  const featuresToSave = pendingCopiedFeatures.value;

  if (!featuresToSave) {
    pendingCopiedFeatures.value = null;
    shouldSaveAfterCopy.value = false;

    showAlert("error", "Aucune donnée à copier vers la nouvelle carte.");
    return;
  }

  try {
    isSaving.value = true;

    const targetProjectId = project.id;

    await saveFeaturesToProject(targetProjectId, featuresToSave);

    pendingCopiedFeatures.value = null;
    shouldSaveAfterCopy.value = false;

    await router.push(`/projet/${project.id}`);
    showAlert("success", "Une copie de la carte a été créée.");
  } catch (err) {
    console.error("Error while saving copied map features:", err);
    showAlert(
      "error",
      "La copie a été créée, mais la sauvegarde des éléments a échoué.",
    );
  } finally {
    isSaving.value = false;
  }
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
  await resolveRouteContext();
  await loadProjectMapsForTimeline();
  await loadCurrentMapInfo();
  await loadInitialFeatures();
  window.addEventListener("keydown", handleKeyboardShortcuts);
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

watch(
  () => route.params.mapId,
  async (newMapId, oldMapId) => {
    if (!newMapId || newMapId === oldMapId) return;

    featureVisibility.value = new Map();
    await loadCurrentMapInfo();

    if (shouldSaveAfterCopy.value) {
      return;
    }

    await loadInitialFeatures();
  },
);

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeyboardShortcuts);
  clearAlert();
});

async function saveFeaturesToProject(
  targetProjectId: string,
  featuresToSave: Feature[],
  deletionIds: string[] = [],
): Promise<void> {
  const payload = camelToSnake(prepareFeaturesForSave(featuresToSave));

  const response = await apiFetch(`/projects/${targetProjectId}/features`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${keycloak.token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Error saving features: ${response.status}`);
  }

  const pendingDeleteSet = new Set(deletionIds);
  const savedFeatures = (
    snakeToCamel(await response.json()) as Feature[]
  ).filter((feature) => !pendingDeleteSet.has(String(feature.id)));
  features.value = savedFeatures;
  reconcileVisibility(savedFeatures);

  if (deletionIds.length > 0) {
    const bulkDeleteResponse = await apiFetch(
      `/projects/${targetProjectId}/features`,
      {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: JSON.stringify(deletionIds),
      },
    );

    if (!bulkDeleteResponse.ok) {
      console.error(
        `Failed to bulk delete features: ${bulkDeleteResponse.status}`,
      );
    }
  }

  pendingDeletions.value = [];

  mapGeoJsonRef.value?.clearDraftLayers();
  await uploadMapThumbnail(targetProjectId);

  if (projectId.value === targetProjectId) {
    await loadInitialFeatures();
  }
}

async function onSaveMap() {
  if (isSaving.value) return;
  isSaving.value = true;
  mapGeoJsonRef.value?.resetSelection();

  try {
    if (!currentUser.value || !keycloak.token) {
      showAlert("error", "Utilisateur non authentifié.");
      return;
    }

    const syncedFeatures = mapGeoJsonRef.value?.syncFeaturesFromMapLayers();
    const featuresToSave = syncedFeatures ?? features.value;

    if (syncedFeatures) {
      features.value = syncedFeatures;
      reconcileVisibility(syncedFeatures);
    }

    const targetProjectId = await requireProjectId();

    if (!targetProjectId) {
      showAlert("error", "Projet introuvable.");
      return;
    }

    const isOwner = await isProjectOwner(targetProjectId);

    if (!isOwner) {
      pendingCopiedFeatures.value = [...featuresToSave];
      shouldSaveAfterCopy.value = true;
      await openCreateCopyDialog();
      return;
    }

    await saveFeaturesToProject(
      targetProjectId,
      featuresToSave,
      pendingDeletions.value,
    );
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
