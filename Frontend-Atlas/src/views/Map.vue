<template>
  <div
    class="h-screen-minus-header w-full bg-base-100 flex flex-col overflow-hidden"
  >
    <div class="flex flex-1 min-h-0 overflow-hidden">
      <div
        class="h-full min-h-0 shrink-0 overflow-hidden border-r border-base-300 flex flex-col"
        :class="isSidebarVisible ? 'overflow-auto bg-base-200 py-3 px-1.5' : 'bg-white'"
        :style="{ width: isSidebarVisible ? `${sidebarWidth}px` : `${COLLAPSED_SIDEBAR_WIDTH}px` }"
        data-testid="sidebar-wrapper"
      >
        <FeatureVisibilityControls
          ref="featureVisibilityControlsRef"
          :collapsed="!isSidebarVisible"
          :features="features"
          :feature-visibility="featureVisibility"
          :map-periods="mapPeriods"
          :custom-label-styles="customLabelStyles"
          :selected-feature-id="selectedFeatureId"
          :multi-selected-feature-ids="multiSelectedFeatureIds"
          :active-map-id="activeMapPeriod?.id ?? null"
          :selected-map-id="selectedMapId"
          @toggle-collapsed="toggleSidebar"
          @select-feature="selectFeature"
          @select-features="onSelectFeatures"
          @toggle-feature="toggleFeatureVisibility"
          @open-add-image-feature-dialog="mapDialogsRef?.openAddImageDialog()"
          @save-map="onSaveMap"
          @delete-feature="onDeleteFeature"
          @delete-map="onDeleteMap"
          @add-map="openAddMapDialog"
          @duplicate-map="() => openDuplicateMapDialog()"
          @select-map="selectMap"
          @edit-map="openEditMapDialog"
          @save-label-styles="saveCustomLabelStyles"
          @update-feature="onUpdateFeature"
          @validate-texts="onOpenTextValidation"
        />
      </div>
      <div
        v-show="isSidebarVisible"
        role="separator"
        aria-label="Redimensionner le panneau latéral"
        aria-orientation="vertical"
        tabindex="0"
        class="w-1.5 shrink-0 cursor-col-resize bg-base-300/50 hover:bg-primary/50 focus:bg-primary/50 transition-colors"
        data-testid="sidebar-resize-handle"
        @pointerdown.prevent="startSidebarResize"
        @keydown.left.prevent="resizeSidebarBy(-16)"
        @keydown.right.prevent="resizeSidebarBy(16)"
      />
      <div class="flex-1 min-h-0 flex flex-col">
        <div class="flex-1 relative min-h-0 h-full w-full bg-[#d4dadc]">
          <!-- Presentation mode & View controls (Point 1) positioned on the left next to zoom -->
          <div class="absolute top-20 left-2 z-[1001] flex items-center gap-2">
            <button
              type="button"
              class="btn btn-sm btn-circle bg-base-200/90 hover:bg-base-300 border border-base-300 shadow-md text-base-content"
              data-testid="toggle-fullscreen-button"
              :title="isFullscreen ? 'Quitter le plein écran' : 'Plein écran'"
              @click="toggleFullscreen"
            >
              <ArrowsPointingInIcon v-if="isFullscreen" class="w-4 h-4" />
              <ArrowsPointingOutIcon v-else class="w-4 h-4" />
            </button>
          </div>

          <MapGeoJSON
            ref="mapGeoJsonRef"
            class="flex-1 min-h-0 w-full"
            :features="features"
            :feature-visibility="combinedFeatureVisibility"
            :selected-year="selectedYear"
            :project-id="projectId || projectRouteId || ''"
            :can-undo="canUndo"
            :can-redo="canRedo"
            :selected-feature-id="selectedFeatureId"
            :multi-selected-feature-ids="multiSelectedFeatureIds"
            @select-feature="(id) => selectFeature(id, false)"
            @select-features="(ids) => onSelectFeatures(ids, false)"
            @duplicate-feature="duplicateFeature"
            @delete-feature="onDirectDeleteFeature"
            @draw-create="handleDrawChange"
            @draw-update="handleDrawChange"
            @draw-delete="handleDrawChange"
            @map-ready="onMapReady"
            @undo="onUndo"
            @redo="onRedo"
            @edit-feature-request="onEditFeatureRequest"
            @move-selected="nudgeSelectedFeatures"
            @select-all="onSelectAll"
          />
          <div
            v-show="!showTextValidationModal && isLegendVisible"
            class="absolute bottom-4 left-4 z-[1001]"
          >
            <Legend
              :zone-features="zoneFeatures"
              :feature-visibility="featureVisibility"
              :selected-feature-id="selectedFeatureId"
              :multi-selected-feature-ids="multiSelectedFeatureIds"
              @select-feature="selectFeature"
              @select-features="onSelectFeatures"
              @edit-feature="onEditFeatureRequest"
            />
          </div>
        </div>

        <!-- Timeline panel with hide toggle and duplication button (Points 5, 6, 7) -->
        <MapTimelinePanel
          :is-timeline-visible="isTimelineVisible"
          :is-legend-visible="isLegendVisible"
          :timeline-height="timelineHeight"
          :project-title="projectTitle"
          :sorted-timeline-milestones="sortedTimelineMilestones"
          :prev-milestone="prevMilestone"
          :next-milestone="nextMilestone"
          :has-prev-milestone="hasPrevMilestone"
          :has-next-milestone="hasNextMilestone"
          :year="selectedYear"
          :mode="timelineMode"
          :selected-feature-id="selectedFeatureId"
          :multi-selected-feature-ids="multiSelectedFeatureIds"
          :min="timelineMinYear"
          :max="timelineMaxYear"
          :marker-years="timelineMarkerYears"
          :map-periods="enrichedPeriods"
          :current-exact-date="selectedExactDate"
          @update:year="onTimelineYearUpdate"
          @update:mode="timelineMode = $event"
          @exact-date-change="onTimelineExactDateChange"
          @select-date="onTimelineSelectDate"
          @select-map="selectMap"
          @edit-map="openEditMapDialog"
          @edit-element="onEditElementFromTimeline"
          @select-element="onSelectElementFromTimeline"
          @select-elements="onSelectFeatures"
          @prev-milestone="onTimelinePrevMilestone"
          @next-milestone="onTimelineNextMilestone"
          @toggle-legend="toggleLegend"
          @toggle-timeline="toggleTimeline"
          @start-resize="startTimelineResize"
          @resize-by="resizeTimelineBy"
        />
      </div>
    </div>

    <Alert />
  </div>

  <MapDialogs
    ref="mapDialogsRef"
    :map-periods="mapPeriods"
    :is-adding="isAdding"
    :is-creating-map="isCreatingMap"
    :is-duplicating-map="isDuplicatingMap"
    :show-text-validation-modal="showTextValidationModal"
    :active-validation-map-id="activeValidationMapId"
    :validation-image-url="validationImageUrl"
    :validation-map-title="validationMapTitle"
    :text-validation-entries="textValidationEntries"
    :is-saving-text-validation="isSavingTextValidation"
    :custom-label-styles="customLabelStyles"
    @add-feature-image="onAddFeatureImage"
    @create-map="createMapForProject"
    @duplicate-map="onDuplicateMapSubmit"
    @save-map-period="saveMapPeriod"
    @project-created="onProjectCreated"
    @project-error="onCreateProjectError"
    @project-dialog-closed="onCreateProjectDialogClosed"
    @confirm-text-validation="onConfirmTextValidation"
    @cancel-text-validation="showTextValidationModal = false"
    @save-label-styles="saveCustomLabelStyles"
  />
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapDialogs from "../components/MapDialogs.vue";
import MapTimelinePanel from "../components/MapTimelinePanel.vue";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import Legend from "../components/legend/Legend.vue";
import { Feature } from "../typescript/feature";
import { MapPeriod, PERIOD_COLORS } from "../typescript/map";
import type { CustomLabelStyle } from "../utils/labelPresentation";
import type { SliderPeriod } from "../typescript/map";
import {
  camelToSnake,
  isUuid,
  prepareFeaturesForSave,
  snakeToCamel,
  toImageSrc,
} from "../utils/utils";
import { toYear } from "../utils/dateUtils";
import { apiErrorMessage, apiFetch } from "../utils/api";
import { useCurrentUser } from "../composables/useCurrentUser";
import { useProjectLabelStyles } from "../composables/useProjectLabelStyles";
import { getOriginalMapImage } from "../composables/useMapImageCache";
import keycloak from "../keycloak";
import L, { type Map as LeafletMap } from "leaflet";
import { captureMapThumbnail } from "../utils/mapThumbnail";
import Alert from "../components/Alert.vue";
import { clearAlert, showAlert } from "../composables/useAlert";
import { FeatureHistoryService } from "../services/FeatureHistoryService";
import {
  upsertFeature,
  isCopyableFeature,
  cloneFeatureWithOffset,
  getFeatureMapId,
  getFeatureMapIds,
} from "../utils/featureHelpers";
import { nudgeFeatureByPixels } from "../utils/mapDragUtils";
import {
  getNudgeDelta,
  getSelectedTargetFeatures,
  removeFeaturesByIds,
} from "../utils/selectionUtils";
import {
  ArrowsPointingOutIcon,
  ArrowsPointingInIcon,
} from "@heroicons/vue/24/outline";
import type { CreatedProjectRef } from "../typescript/project";
import {
  type TextValidationEntry,
  featureToValidationEntry,
  applyValidationToFeature,
  isUnrecognizedTextFeature,
} from "../utils/textValidation";
import { isVisibleInMainLayers } from "../utils/featureValidationState";
import { normalizeWordType } from "../utils/wordStyles";
import {
  applyCustomLabelStyleToFeature,
  removeCustomLabelStyleFromFeature,
} from "../utils/featureTextEditing";
import { useMapTimeline } from "../composables/useMapTimeline";
import { useResizablePanel } from "../composables/useResizablePanel";

const route = useRoute();
const router = useRouter();
const IMPORTED_MAP_QUERY = "carte";
const projectRouteId = computed(
  () => (route.params.projectId as string | undefined) ?? null,
);
const projectId = ref<string>();
const mapGeoJsonRef = ref<{
  syncFeaturesFromMapLayers: () => Feature[];
  clearDraftLayers: () => void;
  resetSelection: () => void;
  fitToVisibleFeatures: (
    featureIds?: ReadonlySet<string> | string[] | Set<string>,
    animate?: boolean,
  ) => void;
  multiSelectedIds: { value: Set<string> };
} | null>(null);

const mapDialogsRef = ref<InstanceType<typeof MapDialogs> | null>(null);
const isDuplicatingMap = ref(false);
const isAdding = ref(false);
const isCreatingMap = ref(false);

const featureVisibilityControlsRef = ref<InstanceType<
  typeof FeatureVisibilityControls
> | null>(null);

function onEditFeatureRequest(feature: Feature) {
  featureVisibilityControlsRef.value?.showEditFeatureDialog(feature);
}

function onSelectFeatures(ids: string[], fitView = true) {
  multiSelectedFeatureIds.value = ids;
  if (ids.length > 0) {
    selectedFeatureId.value = null;
    selectedMapId.value = null;
    if (fitView) {
      nextTick(() => {
        mapGeoJsonRef.value?.fitToVisibleFeatures?.(ids, true);
      });
    }
  }
}

function onSelectAll() {
  const allIds = features.value
    .filter((f: Feature) => {
      const id = String(f.id);
      return combinedFeatureVisibility.value.get(id) !== false;
    })
    .map((f: Feature) => String(f.id));
  multiSelectedFeatureIds.value = allIds;
  selectedFeatureId.value = null;
}

async function onSelectElementFromTimeline(featureId: string) {
  if (!isSidebarVisible.value) {
    isSidebarVisible.value = true;
    await nextTick();
  }
  const feat = features.value.find(
    (f: Feature) =>
      (f.id != null && String(f.id) === String(featureId)) ||
      (f.properties?.name != null &&
        String(f.properties.name).toLowerCase() ===
          String(featureId).toLowerCase()) ||
      (f.properties?.labelText != null &&
        String(f.properties.labelText).toLowerCase() ===
          String(featureId).toLowerCase()),
  );
  if (feat) {
    selectFeature(String(feat.id));
  } else {
    selectFeature(featureId);
  }
}

async function onEditElementFromTimeline(featureId: string) {
  if (!isSidebarVisible.value) {
    isSidebarVisible.value = true;
    await nextTick();
  }
  const feat = features.value.find(
    (f: Feature) =>
      (f.id != null && String(f.id) === String(featureId)) ||
      (f.properties?.id != null &&
        String(f.properties.id) === String(featureId)) ||
      (f.properties?.name != null &&
        String(f.properties.name).toLowerCase() ===
          String(featureId).toLowerCase()) ||
      (f.properties?.labelText != null &&
        String(f.properties.labelText).toLowerCase() ===
          String(featureId).toLowerCase()),
  );
  if (feat) {
    selectedFeatureId.value = String(feat.id);
    onEditFeatureRequest(feat);
  }
}

function selectFeature(id: string | null, fitView = true) {
  selectedFeatureId.value = id;
  if (id) {
    selectedMapId.value = null;
    multiSelectedFeatureIds.value = [];

    const feat = features.value.find((f: Feature) => String(f.id) === String(id));
    if (feat) {
      revealFeatureOnTimeline(feat);
    }

    if (fitView) {
      nextTick(() => {
        mapGeoJsonRef.value?.fitToVisibleFeatures?.([id], true);
      });
    }
  }
}

const features = ref<Feature[]>([]);
const selectedFeatureId = ref<string | null>(null);
const multiSelectedFeatureIds = ref<string[]>([]);
const selectedMapId = ref<string | null>(null);
const copiedFeatures = ref<Feature[]>([]);

// Sidebar, fullscreen, timeline, and legend visibility
const COLLAPSED_SIDEBAR_WIDTH = 56;
const isSidebarVisible = ref(true);
const isFullscreen = ref(false);
const isTimelineVisible = ref(true);
const isLegendVisible = ref(true);

// Panel resizing composables
const {
  size: sidebarWidth,
  startResize: startSidebarResize,
  resizeBy: resizeSidebarBy,
  stopResize: stopSidebarResize,
} = useResizablePanel({
  dimension: "width",
  initial: 350,
  min: 240,
  max: () => Math.min(600, Math.floor(window.innerWidth * 0.6)),
  cursor: "col-resize",
  onResize: () => leafletMap.value?.invalidateSize({ debounceMoveend: true }),
  onResizeEnd: () => leafletMap.value?.invalidateSize(),
});

const {
  size: timelineHeight,
  startResize: startTimelineResize,
  resizeBy: resizeTimelineBy,
  stopResize: stopTimelineResize,
} = useResizablePanel({
  dimension: "height",
  initial: null,
  min: 110,
  max: () => Math.min(450, Math.floor(window.innerHeight * 0.55)),
  cursor: "row-resize",
  direction: "reverse",
  elementSelector: ".map-timeline-toolbar",
  defaultFallback: 140,
  onResize: () => leafletMap.value?.invalidateSize(),
  onResizeEnd: () => leafletMap.value?.invalidateSize(),
});

function toggleSidebar() {
  isSidebarVisible.value = !isSidebarVisible.value;
  nextTick(() => {
    leafletMap.value?.invalidateSize();
  });
}

function toggleTimeline() {
  isTimelineVisible.value = !isTimelineVisible.value;
  nextTick(() => {
    leafletMap.value?.invalidateSize();
  });
}

function toggleLegend() {
  isLegendVisible.value = !isLegendVisible.value;
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.().catch((err: unknown) => {
      console.error("Fullscreen error:", err);
    });
  } else {
    document.exitFullscreen?.().catch((err: unknown) => {
      console.error("Exit fullscreen error:", err);
    });
  }
}

function onFullscreenChange() {
  isFullscreen.value = Boolean(document.fullscreenElement);
  nextTick(() => {
    leafletMap.value?.invalidateSize();
  });
}

function copySelectedFeature(): boolean {
  const ids =
    multiSelectedFeatureIds.value.length > 0
      ? multiSelectedFeatureIds.value
      : selectedFeatureId.value
        ? [selectedFeatureId.value]
        : [];
  if (ids.length === 0) return false;

  const validFeatures = features.value.filter(
    (f: Feature) => ids.includes(String(f.id)) && isCopyableFeature(f) && f.geometry,
  );
  if (validFeatures.length === 0) return false;

  copiedFeatures.value = validFeatures;

  if (validFeatures.length === 1) {
    const feature = validFeatures[0];
    const label =
      feature.properties?.labelText || feature.properties?.name || feature.name;
    if (label && navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(label).catch((error: unknown) => {
        console.error("Could not copy feature label to clipboard:", error);
      });
    }
  }
  return true;
}

function getCenterOffsetDelta(map: any, offsetPx = 24): { deltaLng: number; deltaLat: number } {
  const centerPoint = map.getSize().divideBy(2);
  const targetPoint = L.point(centerPoint.x + offsetPx, centerPoint.y + offsetPx);
  const c1 = map.containerPointToLatLng(centerPoint);
  const c2 = map.containerPointToLatLng(targetPoint);
  return {
    deltaLat: c2.lat - c1.lat,
    deltaLng: c2.lng - c1.lng,
  };
}

function pasteCopiedFeature() {
  const sources = copiedFeatures.value;
  const map = leafletMap.value;
  if (sources.length === 0 || !map) return;

  const { deltaLat, deltaLng } = getCenterOffsetDelta(map);

  const pastedFeatures: Feature[] = [];
  const newIds: string[] = [];

  sources.forEach((source: Feature) => {
    if (!source.geometry) return;
    const pasted = cloneFeatureWithOffset(source, deltaLng, deltaLat);
    pastedFeatures.push(pasted);
    newIds.push(String(pasted.id));
  });

  if (pastedFeatures.length === 0) return;

  commitFeatureSnapshot([...features.value, ...pastedFeatures]);

  if (pastedFeatures.length === 1) {
    selectedFeatureId.value = newIds[0];
    multiSelectedFeatureIds.value = [];
  } else {
    selectedFeatureId.value = null;
    multiSelectedFeatureIds.value = newIds;
  }
}

function duplicateFeature(feature: Feature) {
  duplicateFeatures([feature]);
}

function getSelectedCopyableFeatures(): Feature[] {
  const ids =
    multiSelectedFeatureIds.value.length > 0
      ? multiSelectedFeatureIds.value
      : selectedFeatureId.value
        ? [selectedFeatureId.value]
        : [];
  if (ids.length === 0) return [];
  return features.value.filter(
    (f: Feature) => ids.includes(String(f.id)) && isCopyableFeature(f) && f.geometry,
  );
}

function duplicateFeatures(sources: Feature[]) {
  const map = leafletMap.value;
  if (!map || sources.length === 0) return;

  const { deltaLat, deltaLng } = getCenterOffsetDelta(map);
  const pastedFeatures: Feature[] = [];
  const newIds: string[] = [];

  sources.forEach((source: Feature) => {
    if (!source.geometry) return;
    const pasted = cloneFeatureWithOffset(source, deltaLng, deltaLat);
    pastedFeatures.push(pasted);
    newIds.push(String(pasted.id));
  });

  if (pastedFeatures.length === 0) return;

  commitFeatureSnapshot([...features.value, ...pastedFeatures]);

  if (pastedFeatures.length === 1) {
    selectedFeatureId.value = newIds[0];
    multiSelectedFeatureIds.value = [];
  } else {
    selectedFeatureId.value = null;
    multiSelectedFeatureIds.value = newIds;
  }
}

function duplicateSelectedFeatures() {
  duplicateFeatures(getSelectedCopyableFeatures());
}

function cutSelectedFeatures(): boolean {
  const validFeatures = getSelectedCopyableFeatures();
  if (validFeatures.length === 0) return false;

  copiedFeatures.value = validFeatures;
  const idsToRemove = validFeatures.map((f: Feature) => String(f.id));
  commitFeatureSnapshot(removeFeaturesByIds(features.value, idsToRemove));
  selectedFeatureId.value = null;
  multiSelectedFeatureIds.value = [];
  return true;
}

function onDirectDeleteFeature(feature: Feature) {
  featureVisibilityControlsRef.value?.showDeleteFeatureDialog(feature);
}

const featureVisibility = ref<Map<string, boolean>>(new Map());
const pendingDeletions = ref<string[]>([]);
const persistedFeatureIds = ref<Set<string>>(new Set());
const isSaving = ref(false);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const leafletMap = ref<LeafletMap | null>(null);
const mapPeriods = ref<MapPeriod[]>([]);
const {
  customLabelStyles,
  loadCustomLabelStyles: fetchCustomLabelStyles,
  saveCustomLabelStyles: persistCustomLabelStyles,
} = useProjectLabelStyles();

const projectTitle = ref<string | undefined>(undefined);
const projectDescription = ref<string | undefined>(undefined);
const currentMapTitle = ref<string | undefined>(undefined);
const currentMapDescription = ref<string | undefined>(undefined);

const {
  selectedYear,
  selectedExactDate,
  timelineMode,
  enrichedPeriods,
  periodByMapId,
  sortedTimelineMilestones,
  prevMilestone,
  nextMilestone,
  hasPrevMilestone,
  hasNextMilestone,
  goToPrevMilestone,
  goToNextMilestone,
  onTimelineDateSelect,
  timelineMinYear,
  timelineMaxYear,
  timelineMarkerYears,
  activeMapPeriod,
  filteredFeatures,
  revealFeatureOnTimeline,
  onExactDateChange,
  beginTimelineRestore,
  restoreTimelinePosition,
  isRestoringPosition,
} = useMapTimeline({
  features,
  mapPeriods,
  currentMapTitle,
  projectId,
  onFitVisibleFeatures: () => {
    mapGeoJsonRef.value?.fitToVisibleFeatures(undefined, true);
  },
});

function onTimelineYearUpdate(year: number) {
  selectedYear.value = year;
  selectedMapId.value = null;
}

function onTimelineExactDateChange(date: string | null) {
  selectedMapId.value = null;
  onExactDateChange(date);
}

function onTimelineSelectDate() {
  selectedMapId.value = null;
  onTimelineDateSelect();
}

function onTimelinePrevMilestone() {
  selectedMapId.value = null;
  goToPrevMilestone();
}

function onTimelineNextMilestone() {
  selectedMapId.value = null;
  goToNextMilestone();
}

watch(
  [selectedYear, selectedExactDate, timelineMode],
  async () => {
    await nextTick();
    if (!selectedFeatureId.value && multiSelectedFeatureIds.value.length === 0) {
      mapGeoJsonRef.value?.fitToVisibleFeatures(undefined, true);
    }
  },
  { flush: "post" },
);

const zoneFeatures = computed(() =>
  filteredFeatures.value.filter(
    (f: Feature) => f.properties?.mapElementType === "zone",
  ),
);

const combinedFeatureVisibility = computed(() => {
  const combined = new Map<string, boolean>();

  const visibleByTimeline = new Set(
    filteredFeatures.value.map((f: Feature) => String(f.id)),
  );

  features.value.forEach((feature: Feature) => {
    const id = String(feature.id);

    if (!isVisibleInMainLayers(feature)) {
      combined.set(id, false);
      return;
    }

    const explicitlyVisible = featureVisibility.value.get(id) ?? true;
    const isTimelineVisible = visibleByTimeline.has(id);

    combined.set(id, explicitlyVisible && isTimelineVisible);
  });

  return combined;
});

const pendingCopiedFeatures = ref<Feature[] | null>(null);
const shouldSaveAfterCopy = ref(false);

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
        .map((feature: Feature) => String(feature.id))
        .filter((id: string) => isUuid(id)),
    );

    pendingDeletions.value = [...persistedFeatureIds.value].filter(
      (id: string) => !currentUuidIds.has(id),
    );
  };

  if (track) {
    apply();
    return;
  }

  featureHistoryService.withoutTracking(apply);
}

function commitFeatureSnapshot(next: Feature[], label?: string) {
  applyFeatureSnapshot(
    featureHistoryService.commit(features.value, next, label),
  );
}

function resetMapSelection() {
  selectedMapId.value = null;
  mapGeoJsonRef.value?.resetSelection();
}

function nudgeSelectedFeatures(dx: number, dy: number) {
  const idsToNudge =
    multiSelectedFeatureIds.value.length > 0
      ? multiSelectedFeatureIds.value
      : selectedFeatureId.value
        ? [selectedFeatureId.value]
        : [];
  if (idsToNudge.length === 0) return;

  const currentMap = leafletMap.value;
  if (!currentMap) return;

  const idsSet = new Set(idsToNudge);
  const nextFeatures = features.value.map((f: Feature) => {
    if (!idsSet.has(String(f.id))) return f;
    return nudgeFeatureByPixels(f, currentMap as any as L.Map, dx, dy);
  });
  commitFeatureSnapshot(nextFeatures);
}

function onUndo() {
  if (!canUndo.value) return;
  resetMapSelection();
  applyFeatureSnapshot(featureHistoryService.undo(features.value), false);
}

function onRedo() {
  if (!canRedo.value) return;
  resetMapSelection();
  applyFeatureSnapshot(featureHistoryService.redo(features.value), false);
}

function getImageNaturalSize(
  file: File,
): Promise<{ width: number; height: number }> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve({ width: 1, height: 1 });
    };
    img.src = url;
  });
}

const FEATURE_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png"];
const FEATURE_IMAGE_MIME_TYPES = ["image/jpeg", "image/jpg", "image/png"];

function isSupportedFeatureImage(file: File): boolean {
  const name = file.name.toLowerCase();
  const hasAllowedExt = FEATURE_IMAGE_EXTENSIONS.some((ext) => name.endsWith(ext));
  const mime = (file.type || "").toLowerCase();
  const hasAllowedMime = !mime || FEATURE_IMAGE_MIME_TYPES.includes(mime);
  return hasAllowedExt && hasAllowedMime;
}

async function onAddFeatureImage(file: File) {
  if (!isSupportedFeatureImage(file)) {
    showAlert(
      "error",
      "Ce format n'est pas pris en charge. Utilisez une image JPG ou PNG.",
    );
    return;
  }

  if (!keycloak.token) {
    mapDialogsRef.value?.closeAddImageDialog();
    return;
  }

  if (!projectId.value) {
    const resolved = await resolveRouteContext();
    if (!resolved || !projectId.value) {
      mapDialogsRef.value?.closeAddImageDialog();
      return;
    }
  }

  isAdding.value = true;
  try {
    const formData = new FormData();
    formData.append("image", file);

    if (leafletMap.value) {
      const LAT_SPAN = 16.0;
      const { width, height } = await getImageNaturalSize(file);
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
      throw new Error(
        await apiErrorMessage(
          res,
          "Ce format n'est pas pris en charge. Utilisez une image JPG ou PNG.",
        ),
      );
    }

    await loadInitialFeatures();
    mapDialogsRef.value?.closeAddImageDialog();
  } catch (e) {
    console.error("Upload image failed:", e);
    showAlert(
      "error",
      e instanceof Error
        ? e.message
        : "Impossible d'ajouter l'image. Vérifiez le format (JPG ou PNG) et réessayez.",
    );
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

  const blob = await captureMapThumbnail(leafletMap.value as LeafletMap);
  if (!blob) return false;

  const formData = new FormData();
  formData.append("image", blob);

  const res = await apiFetch(`/projects/${uploadProjectId}/thumbnail`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    console.error("Project thumbnail upload failed:", res.status);
  }
  return res.ok;
}

async function loadProjectIdForMap(): Promise<boolean> {
  if (!projectRouteId.value) return false;
  projectId.value = projectRouteId.value;
  return true;
}

async function loadProjectMapsForTimeline() {
  if (!projectId.value) {
    mapPeriods.value = [];
    return;
  }

  try {
    const res = await apiFetch(`/projects/${projectId.value}/maps`);
    if (!res.ok) throw new Error("Failed to fetch project maps for timeline");

    const payload = snakeToCamel(await res.json()) as
      | Array<{
          id: string;
          title: string;
          startDate?: string | null;
          endDate?: string | null;
          exactDate?: boolean;
        }>
      | {
          maps?: Array<{
            id: string;
            title: string;
            startDate?: string | null;
            endDate?: string | null;
            exactDate?: boolean;
          }>;
          failedImports?: Array<{ mapId?: string; title?: string }>;
        };

    const rows = Array.isArray(payload) ? payload : (payload.maps ?? []);
    const failedImports = Array.isArray(payload)
      ? []
      : (payload.failedImports ?? []);
    if (failedImports.length > 0) {
      const titles = failedImports
        .map((row) => row.title?.trim())
        .filter((title): title is string => Boolean(title));
      const list = titles.length > 0 ? titles.join(", ") : "une carte";
      showAlert(
        "error",
        failedImports.length === 1
          ? `L'import de « ${list} » a échoué. La carte n'apparaît pas sur la timeline.`
          : `Des imports ont échoué (${list}). Ces cartes n'apparaissent pas sur la timeline.`,
      );
    }

    mapPeriods.value = rows.map(
      (
        row: {
          id: string;
          title: string;
          startDate?: string | null;
          endDate?: string | null;
          exactDate?: boolean;
        },
        idx: number,
      ) => ({
        id: row.id,
        title: row.title,
        startDate: row.startDate ?? null,
        endDate: row.endDate ?? null,
        exactDate: Boolean(row.exactDate),
        color: PERIOD_COLORS[idx % PERIOD_COLORS.length],
      }),
    );
  } catch (e) {
    console.error("Failed to load map periods for timeline:", e);
    mapPeriods.value = [];
  }
}

async function loadCustomLabelStyles() {
  await fetchCustomLabelStyles(projectId.value);
}

async function saveCustomLabelStyles(styles: CustomLabelStyle[]) {
  try {
    if (isSaving.value) {
      throw new Error(
        "Cannot update label styles while project features are saving",
      );
    }
    const targetProjectId = await requireProjectId();
    await persistCustomLabelStyles(targetProjectId, styles);

    const effectiveStyles =
      Array.isArray(customLabelStyles.value) &&
      customLabelStyles.value.length > 0
        ? customLabelStyles.value
        : styles;
    const stylesById = new Map<string, CustomLabelStyle>(
      effectiveStyles.map(
        (style: CustomLabelStyle): [string, CustomLabelStyle] => [
          style.id,
          style,
        ],
      ),
    );
    const nextFeatures = features.value.map((feature: Feature) => {
      const styleId = feature.properties.customLabelStyleId;
      if (typeof styleId !== "string") return feature;
      const style = stylesById.get(styleId);
      if (!style) return removeCustomLabelStyleFromFeature(feature);
      return applyCustomLabelStyleToFeature(
        feature,
        style,
        normalizeWordType(feature.properties.customLabelStyleFallbackWordType),
        feature.properties.name,
        feature.properties.labelText ?? feature.properties.name,
      );
    });
    const changed = nextFeatures.some(
      (feature: Feature, index: number) => feature !== features.value[index],
    );
    if (changed) {
      features.value = nextFeatures;
      await onSaveMap(nextFeatures);
    }
  } catch (error) {
    console.error("Failed to save project label styles:", error);
    showAlert(
      "error",
      "Impossible d'enregistrer les styles. Vérifiez que vous êtes propriétaire du projet.",
    );
  }
}

async function onDeleteFeature(
  featureIdOrIds: string | string[],
  callbacks?: {
    onSuccess?: () => void;
    onError?: (message?: string) => void;
  },
) {
  try {
    let idsToDelete: string[] = [];
    if (Array.isArray(featureIdOrIds)) {
      idsToDelete = featureIdOrIds.map(String);
    } else {
      const fid = String(featureIdOrIds);
      if (
        multiSelectedFeatureIds.value.length > 0 &&
        multiSelectedFeatureIds.value.some((id: string) => String(id) === fid)
      ) {
        idsToDelete = multiSelectedFeatureIds.value.map(String);
      } else {
        idsToDelete = [fid];
      }
    }

    const idsSet = new Set(idsToDelete);
    const nextFeatures = features.value.filter(
      (feature: Feature) => !idsSet.has(String(feature.id)),
    );

    selectedFeatureId.value = null;
    multiSelectedFeatureIds.value = [];

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

async function onDeleteMap(
  mapId: string,
  callbacks?: {
    onSuccess?: () => void;
    onError?: (message?: string) => void;
  },
) {
  try {
    if (!projectId.value) {
      throw new Error("Project ID is missing");
    }

    const res = await apiFetch(`/projects/${projectId.value}/maps/${mapId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${keycloak.token}` },
    });

    if (!res.ok) {
      throw new Error(`Failed to delete map: ${res.status}`);
    }

    const mapIdNorm = String(mapId).trim().toLowerCase();
    if (selectedMapId.value && selectedMapId.value.trim().toLowerCase() === mapIdNorm) {
      selectedMapId.value = null;
    }
    mapPeriods.value = mapPeriods.value.filter(
      (p: MapPeriod) => String(p.id).trim().toLowerCase() !== mapIdNorm,
    );
    const knownMapIds = new Set(
      mapPeriods.value.map((p: MapPeriod) => String(p.id).trim().toLowerCase()),
    );

    const nextFeatures: Feature[] = [];
    for (const feature of features.value) {
      const existingMapIds = getFeatureMapIds(feature);
      if (existingMapIds.length === 0) {
        nextFeatures.push(feature);
        continue;
      }
      const remainingMapIds = existingMapIds.filter(
        (id: string) =>
          id.trim().toLowerCase() !== mapIdNorm &&
          knownMapIds.has(id.trim().toLowerCase()),
      );
      if (remainingMapIds.length === 0) {
        continue;
      }
      if (remainingMapIds.length === existingMapIds.length) {
        nextFeatures.push(feature);
        continue;
      }
      const newPrimaryMapId = remainingMapIds[0];
      nextFeatures.push({
        ...feature,
        mapId: newPrimaryMapId,
        mapIds: remainingMapIds,
        map_id: newPrimaryMapId,
        properties: {
          ...feature.properties,
          mapId: newPrimaryMapId,
          mapIds: remainingMapIds,
          map_id: newPrimaryMapId,
        },
      });
    }

    if (
      activeValidationMapId.value &&
      String(activeValidationMapId.value).trim().toLowerCase() === mapIdNorm
    ) {
      activeValidationMapId.value = null;
      showTextValidationModal.value = false;
    }
    selectedExactDate.value = null;

    if (trackingEnabled.value) {
      commitFeatureSnapshot(nextFeatures);
    } else {
      applyFeatureSnapshot(nextFeatures, false);
    }

    await loadProjectMapsForTimeline();
    await loadInitialFeatures();

    if (
      timelineMarkerYears.value.length > 0
      && timelineMarkerYears.value[0] != null
      && !timelineMarkerYears.value.includes(selectedYear.value)
    ) {
      selectedYear.value = timelineMarkerYears.value[0];
    }

    callbacks?.onSuccess?.();
  } catch (error) {
    console.error("Failed to delete map:", error);
    callbacks?.onError?.("Erreur lors de la suppression de la carte.");
  }
}

async function onUpdateFeature(
  updatedFeature: Feature | Feature[],
  callbacks?: {
    onSuccess?: () => void;
    onError?: (message?: string) => void;
  },
) {
  try {
    const list = Array.isArray(updatedFeature)
      ? updatedFeature
      : [updatedFeature];
    let nextFeatures = features.value;
    for (const f of list) {
      nextFeatures = upsertFeature(nextFeatures, f);
    }
    const label =
      list.length === 1
        ? `Modification de ${list[0].name || "l'élément"}`
        : `Modification de ${list.length} éléments`;
    commitFeatureSnapshot(nextFeatures, label);

    await onSaveMap(nextFeatures);
    callbacks?.onSuccess?.();
  } catch (error) {
    console.error("Failed to update feature:", error);
    callbacks?.onError?.("Erreur lors de la mise à jour de l'élément.");
  }
}

const showTextValidationModal = ref(false);
const isSavingTextValidation = ref(false);
const activeValidationMapId = ref<string | null>(null);
const validationMapTitle = computed(() => {
  if (!activeValidationMapId.value) return "Éléments généraux";
  const mapIdStr = String(activeValidationMapId.value).trim().toLowerCase();
  const period = mapPeriods.value.find(
    (p: MapPeriod) => String(p.id).trim().toLowerCase() === mapIdStr,
  );
  if (period?.title) return period.title;

  const matchingFeature = features.value.find(
    (f: Feature) =>
      String(f.mapId || (f as any).map_id || "")
        .trim()
        .toLowerCase() === mapIdStr &&
      Boolean((f as any).mapTitle || (f.properties as any)?.mapTitle),
  );
  const customTitle =
    (matchingFeature as any)?.mapTitle ||
    (matchingFeature?.properties as any)?.mapTitle;
  if (customTitle) return customTitle;

  return "Éléments généraux";
});
const validationImageUrl = ref<string | null>(null);
const textValidationEntries = ref<TextValidationEntry[]>([]);

function onOpenTextValidation(mapId: string | null) {
  activeValidationMapId.value = mapId;

  let img = getOriginalMapImage(mapId);

  if (!img) {
    const imageFeature = features.value.find(
      (f: Feature) =>
        (!mapId || f.mapId === mapId) && (f.image || f.properties?.image),
    );
    const rawImage = imageFeature?.image || imageFeature?.properties?.image;
    if (rawImage) {
      img = toImageSrc(rawImage);
    }
  }

  validationImageUrl.value = img;

  const targetFeatures = features.value.filter((f: Feature) =>
    isUnrecognizedTextFeature(f, mapId),
  );

  if (targetFeatures.length === 0) {
    showAlert("error", "Aucun texte non reconnu trouvé pour cette carte.");
    return;
  }

  textValidationEntries.value = targetFeatures.map((f: Feature) =>
    featureToValidationEntry(f, featureVisibility.value.get(f.id) !== false),
  );

  showTextValidationModal.value = true;
}

async function onConfirmTextValidation(validatedItems: TextValidationEntry[]) {
  isSavingTextValidation.value = true;
  try {
    const validatedMap = new Map<string, TextValidationEntry>(
      validatedItems.map(
        (i: TextValidationEntry): [string, TextValidationEntry] => [i.id, i],
      ),
    );
    const openedIds = new Set<string>(
      textValidationEntries.value.map((i: TextValidationEntry) => i.id),
    );

    for (const id of openedIds) {
      if (!validatedMap.has(id)) {
        featureVisibility.value.delete(id);
      }
    }

    const nextFeatures = features.value
      .filter((f: Feature) => !(openedIds.has(f.id) && !validatedMap.has(f.id)))
      .map((f: Feature) => {
        const validated = validatedMap.get(f.id);
        if (!validated) return f;

        featureVisibility.value.set(f.id, validated.selected);
        return applyValidationToFeature(f, validated);
      });

    featureVisibility.value = new Map(featureVisibility.value);
    commitFeatureSnapshot(nextFeatures, "Validation des textes");
    await onSaveMap(nextFeatures);
    showTextValidationModal.value = false;
    showAlert("success", "Textes validés et enregistrés sur la carte.");
  } catch (err) {
    console.error("Failed to save validated texts:", err);
    showAlert(
      "error",
      "Erreur lors de l'enregistrement de la validation des textes.",
    );
  } finally {
    isSavingTextValidation.value = false;
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
  mapDialogsRef.value?.openAddMapDialog();
}

function selectMap(mapId: string) {
  selectedMapId.value = String(mapId);
  const period =
    enrichedPeriods.value.find((p: SliderPeriod) => String(p.id) === String(mapId)) ??
    mapPeriods.value.find((p: MapPeriod) => String(p.id) === String(mapId));

  if (!period) return;

  const targetYear = (period as any).startYear ?? toYear(period.startDate);
  const targetExactDate =
    (period as any).exactDate && period.startDate ? period.startDate : null;

  selectedYear.value = targetYear;
  selectedExactDate.value = targetExactDate;
  if (timelineMode.value === "global") {
    timelineMode.value = "specific";
  }

  if (period.title) {
    currentMapTitle.value = period.title;
  }

  // Clear element selection when switching maps
  selectedFeatureId.value = null;
  multiSelectedFeatureIds.value = [];

  nextTick(() => {
    const mapFeatureIds = new Set(
      features.value
        .filter((f: Feature) => {
          const mIds = getFeatureMapIds(f);
          return mIds.includes(mapId);
        })
        .map((f: Feature) => String(f.id)),
    );
    if (mapFeatureIds.size > 0) {
      mapGeoJsonRef.value?.fitToVisibleFeatures(mapFeatureIds, true);
    } else {
      mapGeoJsonRef.value?.fitToVisibleFeatures(undefined, true);
    }
  });
}

function openEditMapDialog(mapId: string) {
  const period = mapPeriods.value.find((item: MapPeriod) => item.id === mapId);
  if (!period) {
    showAlert("error", "Impossible de trouver la carte à modifier.");
    return;
  }
  mapDialogsRef.value?.openEditMapPeriodDialog(period);
}

async function saveMapPeriod(payload: {
  mapId: string;
  title: string;
  startDate: string;
  endDate: string;
  exactDate: boolean;
}) {
  mapDialogsRef.value?.setEditMapPeriodSaving(true);
  mapDialogsRef.value?.setEditMapPeriodError("");
  try {
    const targetProjectId = await requireProjectId();
    const response = await apiFetch(
      `/projects/${targetProjectId}/maps/${payload.mapId}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          camelToSnake({
            title: payload.title,
            startDate: payload.startDate,
            endDate: payload.endDate,
            exactDate: payload.exactDate,
          }),
        ),
      },
    );
    if (!response.ok) {
      throw new Error(`Error updating map metadata: ${response.status}`);
    }

    // 1. Immediately update mapPeriods in local state for instant reactivity
    const pIndex = mapPeriods.value.findIndex((p: MapPeriod) => p.id === payload.mapId);
    if (pIndex !== -1) {
      mapPeriods.value[pIndex] = {
        ...mapPeriods.value[pIndex],
        title: payload.title,
        startDate: payload.startDate,
        endDate: payload.endDate,
        exactDate: payload.exactDate,
      };
      mapPeriods.value = [...mapPeriods.value];
    }

    // 2. Immediately update in-memory features associated with this map
    const targetMapIdNorm = String(payload.mapId).trim().toLowerCase();
    features.value = features.value.map((f: Feature) => {
      const fMapId = getFeatureMapId(f);
      if (fMapId && String(fMapId).trim().toLowerCase() === targetMapIdNorm) {
        const updated = { ...f };
        if ((updated as any).mapTitle) {
          (updated as any).mapTitle = payload.title;
        }
        if (updated.properties) {
          updated.properties = { ...updated.properties };
          if (updated.properties.mapTitle) {
            updated.properties.mapTitle = payload.title;
          }
        }
        return updated;
      }
      return f;
    });

    // 3. Update current map title if it is the one displayed
    const currentRouteMapId = Array.isArray(route.params.mapId)
      ? route.params.mapId[0]
      : route.params.mapId;
    if (currentRouteMapId && String(currentRouteMapId).trim().toLowerCase() === targetMapIdNorm) {
      currentMapTitle.value = payload.title;
    }

    // 4. Reposition timeline to the map's updated date
    const newStartYear = toYear(payload.startDate);
    if (newStartYear != null) {
      selectedYear.value = newStartYear;
      selectedExactDate.value = payload.exactDate ? payload.startDate : null;
    }

    await loadProjectMapsForTimeline();
    mapDialogsRef.value?.closeEditMapPeriodDialog();
    showAlert("success", "Nom et période de la carte mis à jour.");
  } catch (error) {
    console.error("Failed to update map metadata:", error);
    mapDialogsRef.value?.setEditMapPeriodError(
      "Erreur lors de l'enregistrement du nom et de la période.",
    );
    showAlert("error", "Erreur lors de la mise à jour de la carte.");
  } finally {
    mapDialogsRef.value?.setEditMapPeriodSaving(false);
  }
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
    mapDialogsRef.value?.closeAddMapDialog();
    router.push(`/televersement/${payload.mapId}?projectId=${targetProjectId}`);
  } catch (e) {
    console.error("Failed to create map for project:", e);
  } finally {
    isCreatingMap.value = false;
  }
}

function openDuplicateMapDialog(defaultSourceMapId?: string) {
  const routeMapId = Array.isArray(route.params.mapId)
    ? route.params.mapId[0]
    : route.params.mapId;
  const targetId =
    defaultSourceMapId || routeMapId || mapPeriods.value[0]?.id || "";
  mapDialogsRef.value?.openDuplicateMapDialog(targetId);
}

async function onDuplicateMapSubmit(payload: {
  sourceMapId: string;
  newTitle: string;
  startDate: string;
  endDate: string;
  exactDate: boolean;
}) {
  if (!projectId.value || !keycloak.token) return;
  isDuplicatingMap.value = true;
  try {
    const res = await apiFetch(
      `/projects/${projectId.value}/maps/${payload.sourceMapId}/duplicate`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: JSON.stringify(
          camelToSnake({
            title: payload.newTitle.trim(),
            startDate: payload.startDate,
            endDate: payload.endDate,
            exactDate: payload.exactDate,
          }),
        ),
      },
    );

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData?.detail || `Erreur serveur (${res.status})`);
    }

    const resData = await res.json().catch(() => ({}));
    mapDialogsRef.value?.closeDuplicateMapDialog();
    showAlert("success", `Carte dupliquée avec succès : "${payload.newTitle}"`);

    await loadProjectMapsForTimeline();
    await loadInitialFeatures();

    const newMapId = resData?.map_id ?? resData?.id;
    if (newMapId) {
      selectMap(String(newMapId));
    } else {
      const yearMatch = payload.startDate.match(/^-?\d+/);
      if (yearMatch) {
        selectedYear.value = parseInt(yearMatch[0], 10);
        selectedExactDate.value = payload.exactDate ? payload.startDate : null;
      }
    }
  } catch (error: any) {
    console.error("Failed to duplicate map:", error);
    mapDialogsRef.value?.setDuplicateMapError(
      error?.message || "Erreur lors de la duplication de la carte.",
    );
    showAlert("error", "Erreur lors de la duplication de la carte.");
  } finally {
    isDuplicatingMap.value = false;
  }
}

function reconcileVisibility(list: Feature[]) {
  const next = new Map<string, boolean>(featureVisibility.value);
  for (const f of list) {
    const id = f?.id;
    if (id != null && next.get(id) === undefined) {
      const initialVisible =
        f.properties?.show !== false && (f.properties?.isVisible ?? true);
      next.set(id, initialVisible);
    }
  }
  const ids = new Set(list.map((f: Feature) => f.id));
  for (const k of next.keys()) {
    if (!ids.has(k)) next.delete(k);
  }
  featureVisibility.value = next;
}

async function loadInitialFeatures() {
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
        .map((feature: Feature) => String(feature.id))
        .filter((id: string) => isUuid(id)),
    );
    applyFeatureSnapshot(featureHistoryService.reset(allFeatures), false);
    pendingDeletions.value = [];
  } catch (e) {
    console.error("Failed to load initial map features:", e);
    showAlert("error", "Erreur lors du chargement des éléments de la carte.");
  }
}

async function frameVisibleFeatures() {
  await nextTick();
  mapGeoJsonRef.value?.fitToVisibleFeatures();
}

async function frameImportedMap(): Promise<boolean> {
  const importedMapId = route.query[IMPORTED_MAP_QUERY];
  if (typeof importedMapId !== "string" || !importedMapId) return false;

  const period = periodByMapId.value.get(importedMapId);
  if (period) selectedYear.value = period.startYear;

  const importedFeatureIds = new Set<string>(
    features.value
      .filter((feature: Feature) => feature.mapId === importedMapId)
      .map((feature: Feature) => String(feature.id)),
  );

  const { [IMPORTED_MAP_QUERY]: _consumed, ...query } = route.query;
  void _consumed;
  await router.replace({ query });

  if (importedFeatureIds.size === 0) return false;
  await nextTick();
  mapGeoJsonRef.value?.fitToVisibleFeatures(importedFeatureIds);
  return true;
}

async function frameOpenedProject() {
  if (await frameImportedMap()) return;
  await frameVisibleFeatures();
}

async function loadCurrentMapInfo(): Promise<void> {
  try {
    const res = await apiFetch(`/projects/${projectId.value}`, {
      method: "GET",
    });

    if (!res.ok) {
      throw new Error(`Failed to fetch map info: ${res.status}`);
    }

    const projectData = snakeToCamel(await res.json()) as {
      title?: string;
      description?: string;
    };

    projectTitle.value = projectData.title ?? undefined;
    projectDescription.value = projectData.description ?? undefined;
  } catch (err) {
    console.error("Failed to load current map info:", err);
    projectTitle.value = undefined;
    projectDescription.value = undefined;
  }
}

async function openCreateCopyDialog() {
  await loadCurrentMapInfo();

  mapDialogsRef.value?.openCreateProjectDialog({
    title: projectTitle.value ?? currentMapTitle.value,
    description: projectDescription.value ?? currentMapDescription.value,
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

async function isProjectOwner(
  targetProjectId: string,
): Promise<boolean | null> {
  if (!targetProjectId) {
    showAlert(
      "error",
      "Impossible de vérifier la propriété, l'identifiant du projet est invalide.",
    );
    return null;
  }

  if (!keycloak.token) {
    showAlert(
      "error",
      "Impossible de vérifier la propriété du projet, le jeton d'authentification est invalide.",
    );
    return null;
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

      if (res.status === 401 || res.status === 403) {
        showAlert(
          "error",
          "Votre session a expiré. Veuillez vous reconnecter.",
        );
        void keycloak.login({ redirectUri: window.location.href });
        return null;
      }

      showAlert(
        "error",
        "Impossible de vérifier la propriété du projet. Réessaie dans un instant.",
      );
      return null;
    }

    const data = (await res.json()) as boolean;
    return data === true;
  } catch (err) {
    console.error("Error checking project owner:", err);
    showAlert(
      "error",
      "Impossible de vérifier la propriété du projet. Réessaie dans un instant.",
    );
    return null;
  }
}

function onCreateProjectError(message: string) {
  showAlert("error", message);
}

function onCreateProjectDialogClosed() {
  pendingCopiedFeatures.value = null;
  shouldSaveAfterCopy.value = false;
}

async function copyMapsIntoProject(
  sourceProjectId: string,
  targetProjectId: string,
  featuresToCopy: Feature[],
): Promise<Feature[]> {
  const res = await apiFetch(
    `/projects/${targetProjectId}/copy-maps-from/${sourceProjectId}`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${keycloak.token}` },
    },
  );
  if (!res.ok) {
    throw new Error(`Error copying maps: ${res.status}`);
  }

  const { mapIdMapping = {} } = snakeToCamel(await res.json()) as {
    mapIdMapping?: Record<string, string>;
  };
  const toNewMapId = (oldMapId?: string | null) =>
    oldMapId ? (mapIdMapping[oldMapId] ?? null) : null;

  return featuresToCopy.map(({ id, projectId, ...feature }: Feature) => {
    void id;
    void projectId;
    const properties = { ...feature.properties };
    if (properties.mapId) {
      properties.mapId = toNewMapId(properties.mapId as string);
    }
    return {
      ...feature,
      mapId: toNewMapId(feature.mapId),
      properties,
    } as Feature;
  });
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
    const sourceProjectId = projectId.value;

    const copiedFeatures = sourceProjectId
      ? await copyMapsIntoProject(
          sourceProjectId,
          targetProjectId,
          featuresToSave,
        )
      : featuresToSave;

    await saveFeaturesToProject(targetProjectId, copiedFeatures);

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
  const isMod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();

  if (!isEditableTarget(e.target)) {
    if (isMod && !e.shiftKey && key === "z") {
      e.preventDefault();
      onUndo();
      return;
    }
    if ((isMod && key === "y") || (isMod && e.shiftKey && key === "z")) {
      e.preventDefault();
      onRedo();
      return;
    }
  }

  if (
    showTextValidationModal.value ||
    document.querySelector("dialog[open]") ||
    isEditableTarget(e.target)
  ) {
    return;
  }

  if (isMod && key === "c" && copySelectedFeature()) {
    e.preventDefault();
    return;
  }

  if (isMod && key === "x" && cutSelectedFeatures()) {
    e.preventDefault();
    return;
  }

  if (isMod && key === "d") {
    e.preventDefault();
    duplicateSelectedFeatures();
    return;
  }

  if (isMod && key === "v" && copiedFeatures.value.length > 0) {
    e.preventDefault();
    pasteCopiedFeature();
    return;
  }

  if (isMod && key === "a") {
    e.preventDefault();
    onSelectAll();
    return;
  }

  if (key === "escape") {
    if (selectedFeatureId.value || multiSelectedFeatureIds.value.length > 0) {
      e.preventDefault();
      selectedFeatureId.value = null;
      multiSelectedFeatureIds.value = [];
      return;
    }
  }

  if (
    (key === "delete" || key === "backspace") &&
    (selectedFeatureId.value || multiSelectedFeatureIds.value.length > 0)
  ) {
    e.preventDefault();
    const targetFeatures = getSelectedTargetFeatures(
      features.value,
      selectedFeatureId.value,
      multiSelectedFeatureIds.value,
    );
    if (targetFeatures.length > 0) {
      featureVisibilityControlsRef.value?.showDeleteFeatureDialog(
        targetFeatures.length === 1 ? targetFeatures[0] : targetFeatures,
      );
    }
    return;
  }

  if (isMod && key === "s") {
    e.preventDefault();
    void onSaveMap();
    return;
  }

  const nudge = getNudgeDelta(key, e.shiftKey);
  if (
    nudge &&
    (selectedFeatureId.value || multiSelectedFeatureIds.value.length > 0)
  ) {
    e.preventDefault();
    if (!leafletMap.value) return;
    nudgeSelectedFeatures(nudge.dx, nudge.dy);
    return;
  }
};

function onDocumentClick(e: MouseEvent) {
  const target = e.target as HTMLElement | null;
  if (!target || typeof target.closest !== "function") {
    if (selectedFeatureId.value) {
      selectedFeatureId.value = null;
    }
    if (selectedMapId.value) {
      selectedMapId.value = null;
    }
    return;
  }
  if (
    target.closest(".leaflet-container") ||
    target.closest(".city-label-text") ||
    target.closest("[data-testid='feature-visibility-controls']") ||
    target.closest(".sidebar-wrapper") ||
    target.closest(".map-timeline-container") ||
    target.closest(".timeline-container") ||
    target.closest(".modal") ||
    target.closest("dialog") ||
    target.closest(".leaflet-control") ||
    target.closest(".leaflet-pm-toolbar") ||
    target.closest(".leaflet-draw") ||
    target.closest(".feature-floating-actions-container") ||
    target.closest(".label-quick-actions") ||
    target.closest(".label-action-btn")
  ) {
    return;
  }
  if (selectedFeatureId.value || multiSelectedFeatureIds.value.length > 0) {
    selectedFeatureId.value = null;
    multiSelectedFeatureIds.value = [];
  }
  if (selectedMapId.value) {
    selectedMapId.value = null;
  }
}

onMounted(async () => {
  beginTimelineRestore();
  try {
    await fetchCurrentUser();
    await resolveRouteContext();
    await loadProjectMapsForTimeline();
    await loadCustomLabelStyles();
    await loadCurrentMapInfo();
    await loadInitialFeatures();
    await nextTick();
  } finally {
    await restoreTimelinePosition(projectId.value);
  }
  await frameOpenedProject();

  if (projectId.value) {
    const pendingEditsStr = localStorage.getItem(
      `pending_public_edits_${projectId.value}`,
    );
    if (pendingEditsStr) {
      try {
        const restoredFeatures = JSON.parse(pendingEditsStr);
        features.value = restoredFeatures;
        reconcileVisibility(restoredFeatures);

        if (currentUser.value && keycloak.token) {
          pendingCopiedFeatures.value = [...restoredFeatures];
          shouldSaveAfterCopy.value = true;
          setTimeout(async () => {
            await openCreateCopyDialog();
          }, 500);
          localStorage.removeItem(`pending_public_edits_${projectId.value}`);
        }
      } catch (e) {
        console.error("Failed to restore pending edits:", e);
        localStorage.removeItem(`pending_public_edits_${projectId.value}`);
      }
    }
  }

  window.addEventListener("keydown", handleKeyboardShortcuts);
  window.addEventListener("click", onDocumentClick);
  document.addEventListener("fullscreenchange", onFullscreenChange);

  if (projectId.value) void uploadMapThumbnail();
});

watch([projectRouteId], async () => {
  beginTimelineRestore();
  selectedYear.value = -1;
  selectedExactDate.value = null;
  try {
    await resolveRouteContext();
    await loadProjectMapsForTimeline();
    await loadInitialFeatures();
    await nextTick();
  } finally {
    await restoreTimelinePosition(projectId.value);
  }
  await frameVisibleFeatures();
});

watch([timelineMinYear, timelineMaxYear], () => {
  if (isRestoringPosition.value || selectedYear.value < 0) return;
  if (selectedYear.value < timelineMinYear.value) {
    selectedYear.value = timelineMinYear.value;
  }
  if (selectedYear.value > timelineMaxYear.value) {
    selectedYear.value = timelineMaxYear.value;
  }
});

watch(
  () => route.params.mapId,
  async (
    newMapId: string | string[] | undefined,
    oldMapId: string | string[] | undefined,
  ) => {
    if (!newMapId || newMapId === oldMapId) return;

    featureVisibility.value = new Map();
    await loadCurrentMapInfo();

    if (shouldSaveAfterCopy.value) {
      return;
    }

    await loadInitialFeatures();
    await frameVisibleFeatures();
  },
);

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeyboardShortcuts);
  window.removeEventListener("click", onDocumentClick);
  document.removeEventListener("fullscreenchange", onFullscreenChange);
  stopSidebarResize();
  stopTimelineResize();
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
  ).filter((feature: Feature) => !pendingDeleteSet.has(String(feature.id)));
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

async function onSaveMap(featuresOverride?: Feature[]) {
  if (isSaving.value) return;
  isSaving.value = true;
  mapGeoJsonRef.value?.resetSelection();

  try {
    if (!currentUser.value || !keycloak.token) {
      const syncedFeatures = featuresOverride
        ? undefined
        : mapGeoJsonRef.value?.syncFeaturesFromMapLayers();
      const featuresToSave =
        featuresOverride ?? syncedFeatures ?? features.value;
      localStorage.setItem(
        `pending_public_edits_${projectId.value}`,
        JSON.stringify(featuresToSave),
      );
      showAlert(
        "success",
        "Veuillez vous connecter pour sauvegarder vos modifications. Vous serez redirigé...",
      );
      setTimeout(() => {
        keycloak.register({ redirectUri: window.location.href });
      }, 1500);
      return;
    }

    const syncedFeatures = featuresOverride
      ? undefined
      : mapGeoJsonRef.value?.syncFeaturesFromMapLayers();
    const featuresToSave = (
      featuresOverride ??
      syncedFeatures ??
      features.value
    ).map((feature: Feature) => ({
      ...feature,
      properties: {
        ...feature.properties,
        isVisible:
          featureVisibility.value.get(feature.id) ??
          feature.properties?.isVisible ??
          true,
      },
    }));

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

    if (isOwner === null) {
      return;
    }

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
    showAlert("success", "Projet sauvegardé avec succès !");
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