<template>
  <div
    class="h-screen-minus-header w-full bg-base-100 flex flex-col overflow-hidden"
  >
    <div class="flex flex-1 min-h-0 overflow-hidden">
      <div
        v-show="isSidebarVisible"
        class="h-full min-h-0 shrink-0 overflow-hidden bg-base-200 border-r border-base-300 py-3 px-1.5 flex flex-col"
        :style="{ width: `${sidebarWidth}px` }"
      >
        <FeatureVisibilityControls
          ref="featureVisibilityControlsRef"
          :features="features"
          :feature-visibility="featureVisibility"
          :map-periods="mapPeriods"
          :custom-label-styles="customLabelStyles"
          :selected-feature-id="selectedFeatureId"
          :multi-selected-feature-ids="multiSelectedFeatureIds"
          :active-map-id="activeMapPeriod?.id ?? null"
          @select-feature="selectFeature"
          @select-features="onSelectFeatures"
          @toggle-feature="toggleFeatureVisibility"
          @open-add-image-feature-dialog="addFeatureImageDialogRef?.open()"
          @save-map="onSaveMap"
          @delete-feature="onDeleteFeature"
          @delete-map="onDeleteMap"
          @add-map="openAddMapDialog"
          @duplicate-map="() => openDuplicateMapDialog()"
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
        @mousedown.prevent="startSidebarResize"
        @keydown.left.prevent="resizeSidebarBy(-16)"
        @keydown.right.prevent="resizeSidebarBy(16)"
      />
      <div class="flex-1 min-h-0 flex flex-col">
        <div class="flex-1 relative min-h-0 h-full w-full bg-[#d4dadc]">
          <!-- Presentation mode & View controls (Point 1) positioned on the left next to zoom -->
          <div class="absolute top-20 left-2 z-[1001] flex items-center gap-2">
            <button
              type="button"
              class="btn btn-sm bg-base-200/90 hover:bg-base-300 border border-base-300 shadow-md gap-1.5 text-base-content"
              data-testid="toggle-sidebar-button"
              :title="isSidebarVisible ? 'Masquer le panneau gauche (Mode présentation)' : 'Afficher le panneau gauche'"
              @click="toggleSidebar"
            >
              <Bars3Icon v-if="!isSidebarVisible" class="w-4 h-4 text-primary" />
              <ChevronLeftIcon v-else class="w-4 h-4" />
            </button>

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
            @select-feature="selectFeature"
            @select-features="onSelectFeatures"
            @duplicate-feature="duplicateFeature"
            @delete-feature="onDirectDeleteFeature"
            @draw-create="handleDrawChange"
            @draw-update="handleDrawChange"
            @draw-delete="handleDrawChange"
            @map-ready="onMapReady"
            @undo="onUndo"
            @redo="onRedo"
            @edit-feature-request="onEditFeatureRequest"
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

          <!-- Floating button to restore timeline when hidden (Point 6) -->
          <div
            v-if="!isTimelineVisible"
            class="absolute bottom-4 right-4 z-[1001] flex items-center gap-2"
          >
            <!-- Previous / Next milestone navigation controls when timeline is hidden -->
            <div
              v-if="sortedTimelineMilestones.length > 0"
              class="inline-flex items-center rounded-lg border border-base-300 bg-base-100 shadow-md overflow-hidden"
            >
              <button
                type="button"
                class="px-2.5 py-1.5 text-base-content hover:bg-base-200 active:bg-base-300 disabled:opacity-30 disabled:pointer-events-none border-r border-base-300 transition-colors flex items-center justify-center"
                :disabled="!hasPrevMilestone"
                :title="
                  prevMilestone
                    ? `Précédent : ${prevMilestone.label} (${prevMilestone.year})`
                    : 'Aucun jalon précédent'
                "
                aria-label="Jalon précédent"
                data-testid="prev-map-button-floating"
                @click="goToPrevMilestone"
              >
                <ChevronLeftIcon class="w-4 h-4 stroke-[2.5]" />
              </button>
              <button
                type="button"
                class="px-2.5 py-1.5 text-base-content hover:bg-base-200 active:bg-base-300 disabled:opacity-30 disabled:pointer-events-none transition-colors flex items-center justify-center"
                :disabled="!hasNextMilestone"
                :title="
                  nextMilestone
                    ? `Suivant : ${nextMilestone.label} (${nextMilestone.year})`
                    : 'Aucun jalon suivant'
                "
                aria-label="Jalon suivant"
                data-testid="next-map-button-floating"
                @click="goToNextMilestone"
              >
                <ChevronRightIcon class="w-4 h-4 stroke-[2.5]" />
              </button>
            </div>

            <button
              type="button"
              class="btn btn-sm btn-primary shadow-md gap-1.5"
              data-testid="show-timeline-button"
              title="Afficher la ligne du temps"
              @click="toggleTimeline"
            >
              <EyeIcon class="w-4 h-4" />
              <span class="text-xs font-semibold">Afficher la ligne du temps</span>
            </button>
          </div>
        </div>

        <!-- Horizontal resize handle for timeline (Point 7) -->
        <div
          v-show="isTimelineVisible"
          role="separator"
          aria-label="Redimensionner l'échelle de temps"
          aria-orientation="horizontal"
          tabindex="0"
          class="h-1.5 w-full shrink-0 cursor-row-resize bg-base-300/50 hover:bg-primary/50 focus:bg-primary/50 transition-colors z-[1002]"
          data-testid="timeline-resize-handle"
          @mousedown.prevent="startTimelineResize"
          @keydown.up.prevent="resizeTimelineBy(10)"
          @keydown.down.prevent="resizeTimelineBy(-10)"
        />

        <!-- Timeline panel with hide toggle and duplication button (Points 5, 6, 7) -->
        <div
          v-show="isTimelineVisible"
          class="map-timeline-toolbar relative z-[2000] flex flex-col bg-base-100 border-t border-base-300 overflow-visible"
          :style="timelineHeight ? { height: `${timelineHeight}px` } : {}"
        >
          <!-- Top bar with Filter Modes and Map Duplication -->
          <div
            class="map-timeline-topbar shrink-0 relative flex items-center justify-between px-3 py-1.5 border-b border-base-200 text-xs font-medium whitespace-nowrap bg-base-100 z-0"
          >
            <!-- Left section: Nom du projet -->
            <div class="flex items-center gap-2 min-w-0 pr-4">
              <span
                v-if="currentMapTitle"
                class="text-sm font-bold text-base-content select-none truncate max-w-xs md:max-w-sm"
                :title="currentMapTitle"
              >
                {{ currentMapTitle }}
              </span>
            </div>

            <!-- Center section: Flèches précédent / suivant parfaitement centrées sur toute la largeur -->
            <div
              v-if="sortedTimelineMilestones.length > 0"
              class="absolute left-1/2 -translate-x-1/2 inline-flex items-center rounded border border-base-300 bg-base-200/90 overflow-hidden shadow-xs pointer-events-auto"
            >
              <button
                type="button"
                class="px-2.5 py-1 text-base-content hover:bg-base-300 active:bg-base-300/80 disabled:opacity-30 disabled:pointer-events-none border-r border-base-300 transition-colors flex items-center justify-center"
                :disabled="!hasPrevMilestone"
                :title="
                  prevMilestone
                    ? `Précédent : ${prevMilestone.label} (${prevMilestone.year})`
                    : 'Aucun jalon précédent'
                "
                aria-label="Jalon précédent"
                data-testid="prev-map-button"
                @click="goToPrevMilestone"
              >
                <ChevronLeftIcon class="w-3.5 h-3.5 stroke-[2.5]" />
              </button>
              <button
                type="button"
                class="px-2.5 py-1 text-base-content hover:bg-base-300 active:bg-base-300/80 disabled:opacity-30 disabled:pointer-events-none transition-colors flex items-center justify-center"
                :disabled="!hasNextMilestone"
                :title="
                  nextMilestone
                    ? `Suivant : ${nextMilestone.label} (${nextMilestone.year})`
                    : 'Aucun jalon suivant'
                "
                aria-label="Jalon suivant"
                data-testid="next-map-button"
                @click="goToNextMilestone"
              >
                <ChevronRightIcon class="w-3.5 h-3.5 stroke-[2.5]" />
              </button>
            </div>

            <!-- Right section: Masquer la légende & Masquer la ligne du temps -->
            <div class="flex items-center gap-3 ml-auto">
              <button
                type="button"
                class="btn btn-ghost btn-xs text-base-content/70 hover:text-base-content gap-1"
                data-testid="hide-legend-button"
                :title="isLegendVisible ? 'Masquer la légende' : 'Afficher la légende'"
                @click="toggleLegend"
              >
                <EyeSlashIcon v-if="isLegendVisible" class="w-3.5 h-3.5" />
                <EyeIcon v-else class="w-3.5 h-3.5" />
                <span>{{ isLegendVisible ? "Masquer la légende" : "Afficher la légende" }}</span>
              </button>
              <button
                type="button"
                class="btn btn-ghost btn-xs text-base-content/70 hover:text-base-content gap-1"
                data-testid="hide-timeline-button"
                title="Masquer la ligne du temps"
                @click="toggleTimeline"
              >
                <EyeSlashIcon class="w-3.5 h-3.5" />
                <span>Masquer la ligne du temps</span>
              </button>
            </div>
          </div>

          <!-- Middle scrollable area containing the timeline tracks, ticks, labels, and legend -->
          <div class="map-timeline-slider flex-1 min-h-0 w-full overflow-visible px-3 pt-3 pb-1 relative z-20">
            <TimelineSlider
              v-model:year="selectedYear"
              v-model:mode="timelineMode"
              :selected-feature-id="selectedFeatureId"
              :multi-selected-feature-ids="multiSelectedFeatureIds"
              @exact-date-change="onExactDateChange"
              @select-date="onTimelineDateSelect"
              @edit-map="openEditMapDialog"
              @edit-element="onEditElementFromTimeline"
              @select-element="onSelectElementFromTimeline"
              @select-elements="onSelectFeatures"
              :min="timelineMinYear"
              :max="timelineMaxYear"
              :marker-years="timelineMarkerYears"
              :map-periods="enrichedPeriods"
              :element-markers="timelineElementMarkers"
              :current-exact-date="selectedExactDate"
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

  <DuplicateMapDialog
    ref="duplicateMapDialogRef"
    :map-periods="mapPeriods"
    :is-duplicating="isDuplicatingMap"
    @submit="onDuplicateMapSubmit"
  />

  <EditMapPeriodDialog ref="editMapPeriodDialogRef" @save="saveMapPeriod" />

  <CreateProjectDialog
    ref="createProjectDialogRef"
    @created="onProjectCreated"
    @error="onCreateProjectError"
    @closed="onCreateProjectDialogClosed"
  />

  <TextValidationModal
    :is-open="showTextValidationModal"
    :map-id="activeValidationMapId"
    :image-url="validationImageUrl"
    :map-title="validationMapTitle"
    :initial-items="textValidationEntries"
    :is-submitting="isSavingTextValidation"
    :custom-label-styles="customLabelStyles"
    @confirm="onConfirmTextValidation"
    @cancel="showTextValidationModal = false"
    @save-label-styles="saveCustomLabelStyles"
  />
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import AddImageDialog from "../components/add/AddImage.vue";
import AddMapDialog from "../components/add/AddMap.vue";
import DuplicateMapDialog from "../components/add/DuplicateMapDialog.vue";
import EditMapPeriodDialog from "../components/add/EditMapPeriodDialog.vue";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import TimelineSlider from "../components/TimelineSlider.vue";
import type { TimelineMarkerItem } from "../components/TimelineSlider.vue";
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
  rgbToHex,
  snakeToCamel,
  toImageSrc,
} from "../utils/utils";
import { isPeriodActiveAt, toYear } from "../utils/dateUtils";
import { apiFetch } from "../utils/api";
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
import {
  Bars3Icon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ArrowsPointingOutIcon,
  ArrowsPointingInIcon,
  EyeIcon,
  EyeSlashIcon,
} from "@heroicons/vue/24/outline";
import type {
  CreatedProjectRef,
  CreateProjectDialogExposed,
} from "../typescript/project";
import CreateProjectDialog from "../components/CreateProjectDialog.vue";
import TextValidationModal from "../components/import/TextValidationModal.vue";
import {
  type TextValidationEntry,
  featureToValidationEntry,
  applyValidationToFeature,
  isUnrecognizedTextFeature,
} from "../utils/textValidation";
import { isVisibleInMainLayers } from "../utils/featureValidationState";
import { isTextFeature, normalizeWordType } from "../utils/wordStyles";
import {
  applyCustomLabelStyleToFeature,
  removeCustomLabelStyleFromFeature,
} from "../utils/featureTextEditing";

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
  fitToVisibleFeatures: (featureIds?: ReadonlySet<string>, animate?: boolean) => void;
  multiSelectedIds: { value: Set<string> };
} | null>(null);
const addMapDialogRef = ref<{
  open: () => void;
  close: () => void;
} | null>(null);
const duplicateMapDialogRef = ref<{
  open: (preselectedMapId?: string) => void;
  close: () => void;
  setError: (msg: string) => void;
} | null>(null);
const isDuplicatingMap = ref(false);
const editMapPeriodDialogRef = ref<{
  open: (period: MapPeriod) => void;
  close: () => void;
  setSaving: (value: boolean) => void;
  setError: (message: string) => void;
} | null>(null);
const addFeatureImageDialogRef = ref<{
  open: () => void;
  close: () => void;
} | null>(null);
const featureVisibilityControlsRef = ref<InstanceType<
  typeof FeatureVisibilityControls
> | null>(null);

function parseOptionalYear(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return null;
  return Math.trunc(num);
}

function getFeatureCustomYears(f: Feature): {
  startYear: number | null;
  endYear: number | null;
} {
  const startYear =
    parseOptionalYear(f.properties?.startYear) ??
    (f.properties?.startDate
      ? parseOptionalYear(toYear(f.properties.startDate))
      : null);
  const endYear =
    parseOptionalYear(f.properties?.endYear) ??
    (f.properties?.endDate
      ? parseOptionalYear(toYear(f.properties.endDate))
      : null);

  return { startYear, endYear };
}

function onEditFeatureRequest(feature: Feature) {
  featureVisibilityControlsRef.value?.showEditFeatureDialog(feature);
}

function onSelectFeatures(ids: string[]) {
  multiSelectedFeatureIds.value = ids;
  if (ids.length > 0) selectedFeatureId.value = null;
}

async function onDeleteSelectedFeatures() {
  const idsToDelete =
    multiSelectedFeatureIds.value.length > 0
      ? multiSelectedFeatureIds.value
      : selectedFeatureId.value
        ? [selectedFeatureId.value]
        : [];
  if (idsToDelete.length === 0) return;
  const idsSet = new Set(idsToDelete);
  const nextFeatures = features.value.filter(
    (f: Feature) => !idsSet.has(String(f.id)),
  );
  multiSelectedFeatureIds.value = [];
  selectedFeatureId.value = null;
  if (trackingEnabled.value) {
    commitFeatureSnapshot(nextFeatures);
  } else {
    applyFeatureSnapshot(nextFeatures, false);
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

function selectFeature(id: string | null) {
  selectedFeatureId.value = id;
  if (id) {
    multiSelectedFeatureIds.value = [];

    const feat = features.value.find((f: Feature) => String(f.id) === String(id));
    if (feat) {
      const { startYear, endYear } = getFeatureCustomYears(feat);
      const featMapId = getFeatureMapId(feat);
      const featMapTitle =
        ("mapTitle" in feat ? (feat as { mapTitle?: string }).mapTitle : undefined) ||
        feat.properties?.mapTitle;

      const featMapKey = featMapId ?? featMapTitle;
      const featMapKeyNorm = featMapKey ? String(featMapKey).trim().toLowerCase() : null;

      const period = featMapKeyNorm
        ? (periodByMapId.value.get(featMapKeyNorm) ??
           periodByMapId.value.get(featMapKey!) ??
           enrichedPeriods.value.find(
             (p) =>
               String(p.id).trim().toLowerCase() === featMapKeyNorm ||
               p.title?.trim().toLowerCase() === featMapKeyNorm,
           ) ??
           mapPeriods.value.find(
             (p) =>
               String(p.id).trim().toLowerCase() === featMapKeyNorm ||
               p.title?.trim().toLowerCase() === featMapKeyNorm,
           ))
        : null;

      let targetYear: number | null = startYear ?? endYear;
      let targetExactDate: string | null = (feat.properties?.exactDate && feat.properties?.startDate)
        ? feat.properties.startDate
        : null;

      if (targetYear == null && period) {
        targetYear = (period as any).startYear ?? toYear(period.startDate);
        targetExactDate = ((period as any).exactDate && period.startDate) ? period.startDate : null;
      }

      if (timelineMode.value !== "global" && targetYear != null && targetYear !== selectedYear.value) {
        selectedYear.value = targetYear;
        if (targetExactDate) {
          selectedExactDate.value = targetExactDate;
        } else {
          selectedExactDate.value = null;
        }
      }

      if (period?.title) {
        currentMapTitle.value = period.title;
      } else if (targetYear != null) {
        const matchingPeriod = enrichedPeriods.value.find((p) =>
          p.startYear != null && p.endYear != null && isPeriodActiveAt(
            p.startYear,
            p.endYear,
            targetYear!,
            periodStartYears.value,
          )
        );
        if (matchingPeriod?.title) {
          currentMapTitle.value = matchingPeriod.title;
        }
      }
    }
  }
}

const features = ref<Feature[]>([]);
const selectedFeatureId = ref<string | null>(null);
const multiSelectedFeatureIds = ref<string[]>([]);
const copiedFeature = ref<Feature | null>(null);
const copiedFeatures = ref<Feature[]>([]);

// Presentation mode & Visibility states (Points 1, 6)
const isSidebarVisible = ref(true);
const isFullscreen = ref(false);
const isTimelineVisible = ref(true);
const isLegendVisible = ref(true);

// Panel resizing states (Point 7)
const sidebarWidth = ref(350);
let sidebarResizeStartX = 0;
let sidebarResizeStartWidth = 0;
let isResizingSidebar = false;

const timelineHeight = ref<number | null>(null);
let timelineResizeStartY = 0;
let timelineResizeStartHeight = 0;
let isResizingTimeline = false;

let previousBodyCursor = "";
let previousBodyUserSelect = "";

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
    document.documentElement.requestFullscreen?.().catch((err) => {
      console.error("Fullscreen error:", err);
    });
  } else {
    document.exitFullscreen?.().catch((err) => {
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

function resizeTimelineBy(delta: number) {
  const el = document.querySelector(".map-timeline-toolbar") as HTMLElement | null;
  const currentHeight = timelineHeight.value ?? el?.offsetHeight ?? 160;
  const maxHeight = Math.min(450, Math.floor(window.innerHeight * 0.55));
  timelineHeight.value = Math.max(
    110,
    Math.min(maxHeight, currentHeight + delta),
  );
  nextTick(() => leafletMap.value?.invalidateSize());
}

function onTimelineResizeMove(event: MouseEvent) {
  const maxHeight = Math.min(450, Math.floor(window.innerHeight * 0.55));
  const deltaY = timelineResizeStartY - event.clientY;
  timelineHeight.value = Math.max(
    110,
    Math.min(maxHeight, timelineResizeStartHeight + deltaY),
  );
  leafletMap.value?.invalidateSize();
}

function stopTimelineResize() {
  window.removeEventListener("mousemove", onTimelineResizeMove);
  window.removeEventListener("mouseup", stopTimelineResize);
  if (isResizingTimeline) {
    document.body.style.cursor = previousBodyCursor;
    document.body.style.userSelect = previousBodyUserSelect;
    isResizingTimeline = false;
    nextTick(() => leafletMap.value?.invalidateSize());
  }
}

function startTimelineResize(event: MouseEvent) {
  const el = document.querySelector(".map-timeline-toolbar") as HTMLElement | null;
  timelineResizeStartY = event.clientY;
  timelineResizeStartHeight = timelineHeight.value ?? el?.offsetHeight ?? 140;
  timelineHeight.value = timelineResizeStartHeight;
  previousBodyCursor = document.body.style.cursor;
  previousBodyUserSelect = document.body.style.userSelect;
  isResizingTimeline = true;
  document.body.style.cursor = "row-resize";
  document.body.style.userSelect = "none";
  window.addEventListener("mousemove", onTimelineResizeMove);
  window.addEventListener("mouseup", stopTimelineResize);
}

let sidebarResizeRaf: number | null = null;

function requestMapInvalidateSize() {
  if (sidebarResizeRaf !== null) return;
  sidebarResizeRaf = window.requestAnimationFrame(() => {
    sidebarResizeRaf = null;
    leafletMap.value?.invalidateSize({ debounceMoveend: true });
  });
}

function resizeSidebarBy(delta: number) {
  const maxWidth = Math.min(600, Math.floor(window.innerWidth * 0.6));
  sidebarWidth.value = Math.max(
    240,
    Math.min(maxWidth, sidebarWidth.value + delta),
  );
  nextTick(() => leafletMap.value?.invalidateSize());
}

function onSidebarResizeMove(event: MouseEvent) {
  const maxWidth = Math.min(600, Math.floor(window.innerWidth * 0.6));
  sidebarWidth.value = Math.max(
    240,
    Math.min(
      maxWidth,
      sidebarResizeStartWidth + event.clientX - sidebarResizeStartX,
    ),
  );
  requestMapInvalidateSize();
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
  copiedFeature.value = validFeatures[0];

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

function pasteCopiedFeature() {
  const sources =
    copiedFeatures.value.length > 0
      ? copiedFeatures.value
      : copiedFeature.value
        ? [copiedFeature.value]
        : [];
  const map = leafletMap.value;
  if (sources.length === 0 || !map) return;

  const centerPoint = map.getSize().divideBy(2);
  const targetPoint = L.point(centerPoint.x + 24, centerPoint.y + 24);
  const c1 = map.containerPointToLatLng(centerPoint);
  const c2 = map.containerPointToLatLng(targetPoint);
  const deltaLat = c2.lat - c1.lat;
  const deltaLng = c2.lng - c1.lng;

  const pastedFeatures: Feature[] = [];
  const newIds: string[] = [];

  sources.forEach((source) => {
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
  const map = leafletMap.value;
  if (!map || !feature.geometry) return;

  const centerPoint = map.getSize().divideBy(2);
  const targetPoint = L.point(centerPoint.x + 24, centerPoint.y + 24);
  const c1 = map.containerPointToLatLng(centerPoint);
  const c2 = map.containerPointToLatLng(targetPoint);
  const deltaLat = c2.lat - c1.lat;
  const deltaLng = c2.lng - c1.lng;

  const pasted = cloneFeatureWithOffset(feature, deltaLng, deltaLat);
  commitFeatureSnapshot([...features.value, pasted]);
  selectedFeatureId.value = String(pasted.id);
  multiSelectedFeatureIds.value = [];
}

function onDirectDeleteFeature(feature: Feature) {
  onDeleteFeature(String(feature.id));
}

function stopSidebarResize() {
  window.removeEventListener("mousemove", onSidebarResizeMove);
  window.removeEventListener("mouseup", stopSidebarResize);
  if (isResizingSidebar) {
    document.body.style.cursor = previousBodyCursor;
    document.body.style.userSelect = previousBodyUserSelect;
    isResizingSidebar = false;
    if (sidebarResizeRaf !== null) {
      window.cancelAnimationFrame(sidebarResizeRaf);
      sidebarResizeRaf = null;
    }
    leafletMap.value?.invalidateSize();
  }
}

function startSidebarResize(event: MouseEvent) {
  sidebarResizeStartX = event.clientX;
  sidebarResizeStartWidth = sidebarWidth.value;
  previousBodyCursor = document.body.style.cursor;
  previousBodyUserSelect = document.body.style.userSelect;
  isResizingSidebar = true;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  window.addEventListener("mousemove", onSidebarResizeMove);
  window.addEventListener("mouseup", stopSidebarResize);
}

const featureVisibility = ref<Map<string, boolean>>(new Map());
const pendingDeletions = ref<string[]>([]);
const persistedFeatureIds = ref<Set<string>>(new Set());
const isSaving = ref(false);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const leafletMap = ref<LeafletMap | null>(null);
const isAdding = ref(false);
const isCreatingMap = ref(false);
const mapPeriods = ref<MapPeriod[]>([]);
const {
  customLabelStyles,
  loadCustomLabelStyles: fetchCustomLabelStyles,
  saveCustomLabelStyles: persistCustomLabelStyles,
} = useProjectLabelStyles();

const zoneFeatures = computed(() =>
  filteredFeatures.value.filter(
    (f: Feature) => f.properties?.mapElementType === "zone",
  ),
);

const selectedYear = ref(-1);
const selectedExactDate = ref<string | null>(null);
export type TimelineFilterMode = "specific" | "cumulative" | "global";
const storedTimelineMode = typeof window !== "undefined" ? localStorage.getItem("atlas_timeline_filter_mode") : null;
const timelineMode = ref<TimelineFilterMode>(
  storedTimelineMode === "specific" || storedTimelineMode === "cumulative" || storedTimelineMode === "global"
    ? storedTimelineMode
    : "specific",
);
watch(timelineMode, (mode) => {
  try {
    localStorage.setItem("atlas_timeline_filter_mode", mode);
  } catch {
    // Ignore storage errors in restricted contexts
  }
});

const enrichedPeriods = computed<SliderPeriod[]>(() => {
  const mapIdsWithFeatures = new Set<string>();
  for (const f of features.value) {
    const mid = getFeatureMapId(f);
    if (mid) mapIdsWithFeatures.add(mid.toLowerCase());
    const mapTitle =
      ("mapTitle" in f ? (f as { mapTitle?: string }).mapTitle : undefined) ||
      f.properties?.mapTitle;
    if (mapTitle) mapIdsWithFeatures.add(String(mapTitle).trim().toLowerCase());
  }

  const periods: SliderPeriod[] = [];
  for (const p of mapPeriods.value) {
    const pIdNorm = String(p.id).trim().toLowerCase();
    const pTitleNorm = p.title ? p.title.trim().toLowerCase() : "";
    if (
      mapIdsWithFeatures.size > 0 &&
      !mapIdsWithFeatures.has(pIdNorm) &&
      (!pTitleNorm || !mapIdsWithFeatures.has(pTitleNorm))
    ) {
      continue;
    }
    const startYear = toYear(p.startDate);
    const endYear = toYear(p.endDate);
    if (startYear != null && endYear != null) {
      periods.push({
        ...p,
        startYear,
        endYear,
      });
    }
  }
  return periods;
});

const periodByMapId = computed(() => {
  const map = new Map<string, SliderPeriod>();
  for (const p of mapPeriods.value) {
    const startYear = toYear(p.startDate);
    const endYear = toYear(p.endDate);
    if (startYear != null && endYear != null) {
      const enriched: SliderPeriod = {
        ...p,
        startYear,
        endYear,
      };
      map.set(p.id, enriched);
      map.set(String(p.id).trim().toLowerCase(), enriched);
      if (p.title) {
        map.set(p.title, enriched);
        map.set(p.title.trim().toLowerCase(), enriched);
      }
    }
  }
  return map;
});

const customFeatureYears = computed<number[]>(() => {
  const years: number[] = [];
  features.value.forEach((f: Feature) => {
    const { startYear, endYear } = getFeatureCustomYears(f);
    if (startYear != null) years.push(startYear);
    if (endYear != null) years.push(endYear);
  });
  return years;
});

const timelineElementMarkers = computed<TimelineMarkerItem[]>(() => {
  const periodTitleById = new Map<string, string>(
    mapPeriods.value.map((p: MapPeriod) => [
      String(p.id).trim().toLowerCase(),
      p.title,
    ]),
  );

  const list: TimelineMarkerItem[] = [];

  features.value.forEach((f: Feature) => {
    const { startYear, endYear } = getFeatureCustomYears(f);
    const effectiveStart = startYear ?? endYear;
    if (effectiveStart == null) return;

    const rawName =
      f.properties?.name?.trim() ||
      f.name?.trim() ||
      f.properties?.labelText?.trim();
    const hasName = Boolean(rawName);
    const effectiveName = hasName && rawName ? rawName : "Nom manquant";

    list.push({
      id: String(
        f.id ??
          f.properties?.id ??
          f.properties?.name ??
          f.properties?.labelText ??
          "",
      ),
      name: effectiveName,
      isNameMissing: !hasName,
      year: effectiveStart,
      startYear: startYear != null ? startYear : effectiveStart,
      endYear: endYear != null ? endYear : null,
      type:
        f.properties?.mapElementType ||
        (isTextFeature(f) ? "Texte" : "Élément"),
      color:
        f.properties?.colorHex ||
        (f.properties?.colorRgb ? rgbToHex(f.properties.colorRgb) : undefined),
      mapId: null,
      mapTitle: "Éléments généraux",
      isCustom: true,
    });
  });

  return list;
});

interface TimelineMilestone {
  year: number;
  label: string;
  type: "map" | "element";
  id?: string;
}

const sortedTimelineMilestones = computed<TimelineMilestone[]>(() => {
  const list: TimelineMilestone[] = [];
  const seen = new Set<string>();

  for (const p of enrichedPeriods.value) {
    const key = `map-${p.id}-${p.startYear}`;
    if (!seen.has(key)) {
      seen.add(key);
      list.push({
        year: p.startYear,
        label: p.title || `Carte (${p.startYear})`,
        type: "map",
        id: String(p.id),
      });
    }
  }

  for (const item of timelineElementMarkers.value) {
    const key = `element-${item.id}-${item.year}`;
    if (!seen.has(key)) {
      seen.add(key);
      list.push({
        year: item.year,
        label: item.name || `Élément (${item.year})`,
        type: "element",
        id: String(item.id),
      });
    }
  }

  return list.sort((a, b) => a.year - b.year || (a.type === "map" ? -1 : 1));
});

const prevMilestone = computed<TimelineMilestone | null>(() => {
  const currentY = selectedYear.value;
  const earlier = sortedTimelineMilestones.value.filter((m) => m.year < currentY);
  return earlier.length > 0 ? earlier[earlier.length - 1] : null;
});

const nextMilestone = computed<TimelineMilestone | null>(() => {
  const currentY = selectedYear.value;
  const later = sortedTimelineMilestones.value.filter((m) => m.year > currentY);
  return later.length > 0 ? later[0] : null;
});

const hasPrevMilestone = computed<boolean>(() => prevMilestone.value != null);
const hasNextMilestone = computed<boolean>(() => nextMilestone.value != null);

function goToPrevMilestone() {
  if (!prevMilestone.value) return;
  selectedExactDate.value = null;
  selectedYear.value = prevMilestone.value.year;
  nextTick(() => {
    mapGeoJsonRef.value?.fitToVisibleFeatures(undefined, true);
  });
}

function goToNextMilestone() {
  if (!nextMilestone.value) return;
  selectedExactDate.value = null;
  selectedYear.value = nextMilestone.value.year;
  nextTick(() => {
    mapGeoJsonRef.value?.fitToVisibleFeatures(undefined, true);
  });
}

function onTimelineDateSelect() {
  nextTick(() => {
    mapGeoJsonRef.value?.fitToVisibleFeatures(undefined, true);
  });
}

// Automatically adjusts map focus/zoom to visible features when date, exact date, or filter mode changes
watch(
  [selectedYear, selectedExactDate, timelineMode],
  async () => {
    await nextTick();
    if (!selectedFeatureId.value) {
      mapGeoJsonRef.value?.fitToVisibleFeatures(undefined, true);
    }
  },
  { flush: "post" },
);

const allTimelineStartYears = computed(() => {
  const years = enrichedPeriods.value.map((p: SliderPeriod) => p.startYear);
  return [...years, ...customFeatureYears.value];
});

const allTimelineEndYears = computed(() => {
  const years = enrichedPeriods.value.map((p: SliderPeriod) => p.endYear);
  return [...years, ...customFeatureYears.value];
});

const timelineMinYear = computed(() =>
  allTimelineStartYears.value.length
    ? Math.min(...allTimelineStartYears.value)
    : 1400,
);

const timelineMaxYear = computed(() =>
  allTimelineEndYears.value.length
    ? Math.max(...allTimelineEndYears.value)
    : new Date().getFullYear(),
);

const timelineMarkerYears = computed(() => {
  const markers = new Set<number>([
    timelineMinYear.value,
    timelineMaxYear.value,
  ]);
  enrichedPeriods.value.forEach((p: SliderPeriod) => {
    markers.add(p.startYear);
    markers.add(p.endYear);
  });
  customFeatureYears.value.forEach((y) => markers.add(y));
  return [...markers].sort((a, b) => a - b);
});

const periodStartYears = computed(() => {
  const years = new Set(
    enrichedPeriods.value.map((p: SliderPeriod) => p.startYear),
  );
  features.value.forEach((f: Feature) => {
    const { startYear, endYear } = getFeatureCustomYears(f);
    const effectiveStart = startYear ?? endYear;
    if (effectiveStart != null) years.add(effectiveStart);
  });
  return years;
});

const periodStartDates = computed(() => {
  const dates = new Set<string>(
    enrichedPeriods.value
      .map((p: SliderPeriod) => p.startDate)
      .filter((date: string | null): date is string => Boolean(date)),
  );
  features.value.forEach((f: Feature) => {
    if (f.properties?.startDate) dates.add(f.properties.startDate);
  });
  return dates;
});

const activeMapPeriod = computed<SliderPeriod | null>(() => {
  if (selectedYear.value == null || selectedYear.value < 0) return null;
  if (selectedExactDate.value) {
    const match = enrichedPeriods.value.find((p) =>
      p.startDate && p.endDate && isPeriodActiveAt(
        p.startDate,
        p.endDate,
        selectedExactDate.value!,
        periodStartDates.value,
      ),
    );
    if (match) return match;
  }
  const match = enrichedPeriods.value.find((p) =>
    p.startYear != null && p.endYear != null && isPeriodActiveAt(
      p.startYear,
      p.endYear,
      selectedYear.value,
      periodStartYears.value,
    ),
  );
  return match ?? null;
});

watch(
  activeMapPeriod,
  (newPeriod) => {
    if (newPeriod?.title) {
      currentMapTitle.value = newPeriod.title;
    }
  },
  { immediate: true },
);

const filteredFeatures = computed(() => {
  return features.value.filter((feature: Feature) => {
    // Global mode: all features visible without date filtering
    if (timelineMode.value === "global") return true;

    const { startYear: featStartYear, endYear: featEndYear } =
      getFeatureCustomYears(feature);
    const hasCustomYears = featStartYear != null || featEndYear != null;

    let isCustomActive = false;
    if (hasCustomYears) {
      const sy = featStartYear ?? (featEndYear as number);
      const ey = featEndYear ?? sy;

      // Cumulative mode: features that have appeared up to selectedYear
      if (timelineMode.value === "cumulative") {
        isCustomActive = sy <= selectedYear.value;
      } else if (
        selectedExactDate.value &&
        feature.properties?.startDate &&
        feature.properties?.endDate
      ) {
        // Specific mode: active at selected date
        isCustomActive = isPeriodActiveAt(
          feature.properties.startDate,
          feature.properties.endDate,
          selectedExactDate.value,
          periodStartDates.value,
        );
      } else {
        isCustomActive = isPeriodActiveAt(
          sy,
          ey,
          selectedYear.value,
          periodStartYears.value,
        );
      }
    }

    // Custom date: detached from any map; visibility determined solely by custom period
    if (hasCustomYears) {
      return isCustomActive;
    }

    const featureMapIds = getFeatureMapIds(feature);
    const featureMapTitle =
      ("mapTitle" in feature ? (feature as { mapTitle?: string }).mapTitle : undefined) ||
      feature.properties?.mapTitle;
    const targetMapKeys =
      featureMapIds.length > 0
        ? featureMapIds
        : featureMapTitle
          ? [featureMapTitle]
          : [];

    if (targetMapKeys.length > 0) {
      return targetMapKeys.some((effectiveMapKey) => {
        const normalizedMapId = String(effectiveMapKey).trim().toLowerCase();
        const period =
          periodByMapId.value.get(effectiveMapKey) ??
          periodByMapId.value.get(normalizedMapId) ??
          enrichedPeriods.value.find(
            (p) =>
              String(p.id).trim().toLowerCase() === normalizedMapId ||
              p.title?.trim().toLowerCase() === normalizedMapId,
          );

        if (!period) return true;
        if (timelineMode.value === "cumulative") {
          return (
            period.startYear == null || period.startYear <= selectedYear.value
          );
        } else if (
          selectedExactDate.value &&
          period.startDate &&
          period.endDate
        ) {
          return isPeriodActiveAt(
            period.startDate,
            period.endDate,
            selectedExactDate.value,
            periodStartDates.value,
          );
        } else if (period.startYear == null || period.endYear == null) {
          return true;
        } else {
          return isPeriodActiveAt(
            period.startYear,
            period.endYear,
            selectedYear.value,
            periodStartYears.value,
          );
        }
      });
    }

    return true;
  });
});

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

  const mapContainer = document.getElementById("map") as
    | (HTMLElement & { _leaflet_map?: L.Map })
    | null;
  const leafletMap = mapContainer?._leaflet_map;
  if (!leafletMap) return;

  const idsSet = new Set(idsToNudge);
  const nextFeatures = features.value.map((f: Feature) => {
    if (!idsSet.has(String(f.id))) return f;
    return nudgeFeatureByPixels(f, leafletMap, dx, dy);
  });
  commitFeatureSnapshot(nextFeatures);
}

function nudgeFeatureByPixels(
  feature: Feature,
  leafletMap: L.Map,
  dx: number,
  dy: number,
): Feature {
  if (!feature.geometry) return feature;

  const shiftLatLng = (lat: number, lng: number): [number, number] => {
    const pt = leafletMap.latLngToContainerPoint([lat, lng]);
    const newPt = L.point(pt.x + dx, pt.y + dy);
    const ll = leafletMap.containerPointToLatLng(newPt);
    return [ll.lat, ll.lng];
  };

  const shiftCoords = (coords: unknown): unknown => {
    if (!Array.isArray(coords)) return coords;
    if (typeof coords[0] === "number") {
      const [sLat, sLng] = shiftLatLng(
        coords[1] as number,
        coords[0] as number,
      );
      return [sLng, sLat];
    }
    return coords.map(shiftCoords);
  };

  return {
    ...feature,
    geometry: {
      ...feature.geometry,
      coordinates: shiftCoords(
        feature.geometry.coordinates,
      ) as typeof feature.geometry.coordinates,
    } as any,
  };
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
        multiSelectedFeatureIds.value.some((id) => String(id) === fid)
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
    mapPeriods.value = mapPeriods.value.filter(
      (p: MapPeriod) => String(p.id).trim().toLowerCase() !== mapIdNorm,
    );

    const nextFeatures = features.value.filter(
      (feature: Feature) =>
        String(getFeatureMapId(feature) ?? "")
          .trim()
          .toLowerCase() !== mapIdNorm,
    );

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

    if (
      timelineMarkerYears.value.length > 0 &&
      timelineMarkerYears.value[0] != null &&
      !timelineMarkerYears.value.includes(selectedYear.value)
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

    // Positionne immédiatement la timeline sur la nouvelle année personnalisée si présente
    const firstCustomYears = list
      .map((item) => getFeatureCustomYears(item))
      .find((y) => y.startYear != null || y.endYear != null);
    const targetYear = firstCustomYears?.startYear ?? firstCustomYears?.endYear;
    if (targetYear != null) {
      selectedExactDate.value = null;
      selectedYear.value = targetYear;
    }

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
      validatedItems.map((i): [string, TextValidationEntry] => [i.id, i]),
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
  addMapDialogRef.value?.open();
}

function openEditMapDialog(mapId: string) {
  const period = mapPeriods.value.find((item: MapPeriod) => item.id === mapId);
  if (!period) {
    showAlert("error", "Impossible de trouver la carte à modifier.");
    return;
  }
  editMapPeriodDialogRef.value?.open(period);
}

async function saveMapPeriod(payload: {
  mapId: string;
  title: string;
  startDate: string;
  endDate: string;
  exactDate: boolean;
}) {
  editMapPeriodDialogRef.value?.setSaving(true);
  editMapPeriodDialogRef.value?.setError("");
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
    editMapPeriodDialogRef.value?.close();
    showAlert("success", "Nom et période de la carte mis à jour.");
  } catch (error) {
    console.error("Failed to update map metadata:", error);
    editMapPeriodDialogRef.value?.setError(
      "Erreur lors de l'enregistrement du nom et de la période.",
    );
    showAlert("error", "Erreur lors de la mise à jour de la carte.");
  } finally {
    editMapPeriodDialogRef.value?.setSaving(false);
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
    addMapDialogRef.value?.close();
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
  duplicateMapDialogRef.value?.open(targetId);
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

    duplicateMapDialogRef.value?.close();
    showAlert("success", `Carte dupliquée avec succès : "${payload.newTitle}"`);

    await loadProjectMapsForTimeline();
    await loadInitialFeatures();

    const yearMatch = payload.startDate.match(/^-?\d+/);
    if (yearMatch) {
      selectedYear.value = parseInt(yearMatch[0], 10);
      if (payload.exactDate) {
        selectedExactDate.value = payload.startDate;
      }
    }
  } catch (error: any) {
    console.error("Failed to duplicate map:", error);
    duplicateMapDialogRef.value?.setError(
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
  const ids = new Set(list.map((f) => f.id));
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

  if (isMod && key === "v" && (copiedFeatures.value.length > 0 || copiedFeature.value)) {
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
    if (multiSelectedFeatureIds.value.length > 1) {
      e.preventDefault();
      void onDeleteSelectedFeatures();
      return;
    }
    if (selectedFeatureId.value) {
      const selectedFeature = features.value.find(
        (feature: Feature) => String(feature.id) === selectedFeatureId.value,
      );
      if (selectedFeature) {
        e.preventDefault();
        featureVisibilityControlsRef.value?.showDeleteFeatureDialog(
          selectedFeature,
        );
      }
    }
    return;
  }

  if (isMod && key === "s") {
    e.preventDefault();
    void onSaveMap();
    return;
  }

  const NUDGE_PX = e.shiftKey ? 10 : 1;
  if (
    ["arrowup", "arrowdown", "arrowleft", "arrowright"].includes(key) &&
    (selectedFeatureId.value || multiSelectedFeatureIds.value.length > 0)
  ) {
    e.preventDefault();
    const mapEl = document.getElementById("map");
    if (!mapEl) return;
    const dx =
      key === "arrowright" ? NUDGE_PX : key === "arrowleft" ? -NUDGE_PX : 0;
    const dy =
      key === "arrowdown" ? NUDGE_PX : key === "arrowup" ? -NUDGE_PX : 0;
    nudgeSelectedFeatures(dx, dy);
    return;
  }
};

function onDocumentClick(e: MouseEvent) {
  const target = e.target as HTMLElement | null;
  if (!target || typeof target.closest !== "function") {
    if (selectedFeatureId.value) {
      selectedFeatureId.value = null;
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
    target.closest(".element-marker-pin") ||
    target.closest(".element-marker-popover") ||
    target.closest(".modal") ||
    target.closest("dialog")
  ) {
    return;
  }
  if (selectedFeatureId.value || multiSelectedFeatureIds.value.length > 0) {
    selectedFeatureId.value = null;
    multiSelectedFeatureIds.value = [];
  }
}

onMounted(async () => {
  await fetchCurrentUser();
  await resolveRouteContext();
  await loadProjectMapsForTimeline();
  await loadCustomLabelStyles();
  await loadCurrentMapInfo();
  await loadInitialFeatures();
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
  await resolveRouteContext();
  await loadProjectMapsForTimeline();
  await loadInitialFeatures();
  await frameVisibleFeatures();
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
  (markers: number[]) => {
    if (!markers.length) return;
    if (!markers.includes(selectedYear.value)) {
      // Find closest marker instead of resetting to markers[0]
      let closest = markers[0];
      let minDiff = Math.abs(selectedYear.value - closest);
      for (let i = 1; i < markers.length; i++) {
        const diff = Math.abs(selectedYear.value - markers[i]);
        if (diff < minDiff) {
          minDiff = diff;
          closest = markers[i];
        }
      }
      selectedYear.value = closest;
    }
  },
);

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