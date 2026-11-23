<template>
  <div
    class="h-screen-minus-header w-full bg-base-100 flex flex-col overflow-hidden"
  >
    <div v-if="draft.error.value" role="alert" class="bg-amber-100 p-3 text-sm text-amber-950">
      {{ draft.error.value }}
    </div>
    <div v-else-if="draft.dirty.value && draft.savedAt.value" role="status" class="bg-slate-100 px-3 py-1 text-xs">
      Brouillon conservé sur cet appareil. Les modifications ne sont pas toutes enregistrées sur le serveur.
    </div>
    <div v-for="candidate in draft.candidates.value" :key="candidate.id" class="flex items-center gap-3 bg-blue-50 p-3 text-sm">
      <span>Un brouillon du {{ new Date(candidate.updatedAt).toLocaleString('fr-CA') }} est disponible.</span>
      <button class="btn btn-sm" :disabled="editorLocked" @click="restoreDraft(candidate)">Récupérer</button>
      <button class="btn btn-sm btn-ghost" :disabled="editorLocked" @click="discardDraft(candidate)">Supprimer ce brouillon</button>
    </div>
    <div v-if="recoveryConflict" role="alert" class="bg-amber-100 p-3 text-sm text-amber-950">
      Le contenu enregistré a changé ou le résultat d’une sauvegarde est incertain. Votre brouillon est conservé ; la carte existante ne sera pas remplacée automatiquement.
      <button class="btn btn-sm ml-3" :disabled="editorLocked" @click="saveAsCopy">Créer une copie du brouillon</button>
    </div>
    <div v-if="editorLocked" role="status" class="px-3 py-1 text-sm">{{ redirecting ? 'Préparation de la reconnexion…' : 'Enregistrement en cours…' }}</div>
    <div class="flex flex-1 min-h-0 overflow-hidden" :inert="editorLocked || undefined">
      <div
        class="h-full min-h-0 shrink-0 overflow-hidden bg-base-200 border-r border-base-300 p-3 flex flex-col"
        :style="{ width: `${sidebarWidth}px` }"
      >
        <FeatureVisibilityControls
          ref="featureVisibilityControlsRef"
          :features="features"
          :feature-visibility="featureVisibility"
          :map-periods="mapPeriods"
          :custom-label-styles="customLabelStyles"
          :selected-feature-id="selectedFeatureId"
          :busy="editorLocked"
          @draft-change="onDraftChanged"
          @select-feature="(id: string | null) => (selectedFeatureId = id)"
          @toggle-feature="toggleFeatureVisibility"
          @open-add-image-feature-dialog="addFeatureImageDialogRef?.open()"
          @save-map="onSaveMap"
          @delete-feature="onDeleteFeature"
          @delete-map="onDeleteMap"
          @add-map="openAddMapDialog"
          @edit-map="openEditMapDialog"
          @save-label-styles="saveCustomLabelStyles"
          @update-feature="onUpdateFeature"
          @validate-texts="onOpenTextValidation"
        />
      </div>
      <div
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
            @select-feature="(id: string | null) => (selectedFeatureId = id)"
            @draw-create="handleDrawChange"
            @draw-update="handleDrawChange"
            @draw-delete="handleDrawChange"
            @map-ready="onMapReady"
            @undo="onUndo"
            @redo="onRedo"
            @edit-feature-request="onEditFeatureRequest"
          />
          <div
            v-show="!showTextValidationModal"
            class="absolute bottom-4 left-4 z-[1001]"
          >
            <Legend
              :zone-features="zoneFeatures"
              :feature-visibility="featureVisibility"
              :selected-feature-id="selectedFeatureId"
              @select-feature="selectFeature"
              @edit-feature="onEditFeatureRequest"
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
    :is-adding="isAdding || editorLocked"
    @draft-change="onDraftChanged"
    @submit="onAddFeatureImage"
  />

  <AddMapDialog
    ref="addMapDialogRef"
    :is-creating-map="isCreatingMap || editorLocked"
    @draft-change="onDraftChanged"
    @submit="createMapForProject"
  />

  <EditMapPeriodDialog ref="editMapPeriodDialogRef" @save="saveMapPeriod" />

  <CreateProjectDialog
    ref="createProjectDialogRef"
    :busy="editorLocked"
    @draft-change="onDraftChanged"
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
import {
  onBeforeRouteLeave,
  onBeforeRouteUpdate,
  useRoute,
  useRouter,
} from "vue-router";
import AddImageDialog from "../components/add/AddImage.vue";
import AddMapDialog from "../components/add/AddMap.vue";
import EditMapPeriodDialog from "../components/add/EditMapPeriodDialog.vue";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import TimelineSlider from "../components/TimelineSlider.vue";
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
import { isPeriodActiveAt, toYear } from "../utils/dateUtils";
import { apiFetch } from "../utils/api";
import { useCurrentUser } from "../composables/useCurrentUser";
import { useEditorDraft } from "../composables/useEditorDraft";
import { useProjectLabelStyles } from "../composables/useProjectLabelStyles";
import { getOriginalMapImage } from "../composables/useMapImageCache";
import keycloak from "../keycloak";
import L, { type Map as LeafletMap } from "leaflet";
import { captureMapThumbnail } from "../utils/mapThumbnail";
import Alert from "../components/Alert.vue";
import { clearAlert, showAlert } from "../composables/useAlert";
import { FeatureHistoryService } from "../services/FeatureHistoryService";
import {
  AuthRequiredError,
  isAuthRequiredError,
  reconnect,
  registerAuthRedirectHandler,
  sessionState,
} from "../services/authSession";
import { haveSameEditorFeatures } from "../services/editorDraft";
import { cloneFeatureSnapshot } from "../utils/featureHistory";
import type { EditorDraft, EditorFormDrafts } from "../typescript/editorDraft";
import {
  upsertFeature,
  isCopyableFeature,
  getGeometryAnchor,
  cloneFeatureWithOffset,
} from "../utils/featureHelpers";
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
  fitToVisibleFeatures: (featureIds?: ReadonlySet<string>) => void;
} | null>(null);
const addMapDialogRef = ref<InstanceType<typeof AddMapDialog> | null>(null);
const editMapPeriodDialogRef = ref<{
  open: (period: MapPeriod) => void;
  close: () => void;
  setSaving: (value: boolean) => void;
  setError: (message: string) => void;
} | null>(null);
const addFeatureImageDialogRef = ref<InstanceType<typeof AddImageDialog> | null>(null);
const featureVisibilityControlsRef = ref<InstanceType<
  typeof FeatureVisibilityControls
> | null>(null);

function onEditFeatureRequest(feature: Feature) {
  featureVisibilityControlsRef.value?.showEditFeatureDialog(feature);
}
function selectFeature(id: string | null) {
  selectedFeatureId.value = id;
}
const features = ref<Feature[]>([]);
const selectedFeatureId = ref<string | null>(null);
const copiedFeature = ref<Feature | null>(null);
const sidebarWidth = ref(350);
let sidebarResizeStartX = 0;
let sidebarResizeStartWidth = 0;
let isResizingSidebar = false;
let previousBodyCursor = "";
let previousBodyUserSelect = "";

function resizeSidebarBy(delta: number) {
  const maxWidth = Math.min(600, Math.floor(window.innerWidth * 0.6));
  sidebarWidth.value = Math.max(
    240,
    Math.min(maxWidth, sidebarWidth.value + delta),
  );
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
}

function copySelectedFeature(): boolean {
  const feature = features.value.find(
    (item: Feature) => String(item.id) === selectedFeatureId.value,
  );
  if (!isCopyableFeature(feature)) {
    return false;
  }

  copiedFeature.value = feature;
  const label =
    feature.properties?.labelText || feature.properties?.name || feature.name;
  if (label && navigator.clipboard?.writeText) {
    void navigator.clipboard.writeText(label).catch((error: unknown) => {
      console.error("Could not copy feature label to clipboard:", error);
      if (isTextFeature(feature)) {
        showAlert(
          "error",
          "Le texte est copié dans Atlas, mais pas dans le presse-papiers système.",
        );
      }
    });
  } else if (isTextFeature(feature)) {
    showAlert(
      "error",
      "Le navigateur ne permet pas de copier le texte dans le presse-papiers système.",
    );
  }
  return true;
}

function pasteCopiedFeature() {
  const source = copiedFeature.value;
  const map = leafletMap.value;
  if (!source || !map || !source.geometry) return;

  const selectedFeature = features.value.find(
    (item: Feature) => String(item.id) === selectedFeatureId.value,
  );
  const refGeometry =
    (selectedFeature &&
      isCopyableFeature(selectedFeature) &&
      selectedFeature.geometry) ||
    source.geometry;
  const anchor = getGeometryAnchor(refGeometry);
  if (!anchor) return;

  const [lng, lat] = anchor;
  const screenPosition = map
    .latLngToContainerPoint(L.latLng(lat, lng))
    .add(L.point(24, -24));
  const pastedPosition = map.containerPointToLatLng(screenPosition);
  const deltaLat = pastedPosition.lat - lat;
  const deltaLng = pastedPosition.lng - lng;

  const pastedFeature = cloneFeatureWithOffset(source, deltaLng, deltaLat);

  commitFeatureSnapshot([...features.value, pastedFeature]);
  selectedFeatureId.value = pastedFeature.id;
}

function stopSidebarResize() {
  window.removeEventListener("mousemove", onSidebarResizeMove);
  window.removeEventListener("mouseup", stopSidebarResize);
  if (isResizingSidebar) {
    document.body.style.cursor = previousBodyCursor;
    document.body.style.userSelect = previousBodyUserSelect;
    isResizingSidebar = false;
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
const redirecting = ref(false);
const isLoadingEditor = ref(true);
const editorLocked = computed(() => isSaving.value || redirecting.value || isLoadingEditor.value);
const serverFeatures = ref<Feature[]>([]);
const serverLoaded = ref(false);
const recoveryConflict = ref(false);
const savePhase = ref<EditorDraft["savePhase"]>("idle");
const saveTargetProjectId = ref<string>();
let restoring = false;
let unregisterAuthRedirect: (() => void) | undefined;
let disposed = false;
const { fetchCurrentUser } = useCurrentUser();
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
const useTimelineFilter = ref(true);

const enrichedPeriods = computed<SliderPeriod[]>(() => {
  const periods: SliderPeriod[] = [];
  for (const p of mapPeriods.value) {
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

const periodByMapId = computed(
  () => new Map(enrichedPeriods.value.map((p: SliderPeriod) => [p.id, p])),
);

const timelineMinYear = computed(() =>
  enrichedPeriods.value.length
    ? Math.min(...enrichedPeriods.value.map((p: SliderPeriod) => p.startYear))
    : 1400,
);

const timelineMaxYear = computed(() =>
  enrichedPeriods.value.length
    ? Math.max(...enrichedPeriods.value.map((p: SliderPeriod) => p.endYear))
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
  return [...markers].sort((a, b) => a - b);
});

const periodStartYears = computed(
  () => new Set(enrichedPeriods.value.map((p: SliderPeriod) => p.startYear)),
);

const periodStartDates = computed(
  () =>
    new Set(
      enrichedPeriods.value
        .map((p: SliderPeriod) => p.startDate)
        .filter((date: string | null): date is string => Boolean(date)),
    ),
);

const filteredFeatures = computed(() => {
  return features.value.filter((feature: Feature) => {
    if (!useTimelineFilter.value) return true;

    // Project-level features without a map are always visible in timeline mode.
    if (!feature.mapId) return true;

    const period = periodByMapId.value.get(feature.mapId);
    if (!period) return true;

    if (selectedExactDate.value && period.startDate && period.endDate) {
      return isPeriodActiveAt(
        period.startDate,
        period.endDate,
        selectedExactDate.value,
        periodStartDates.value,
      );
    }

    if (period.startYear == null || period.endYear == null) return true;
    return isPeriodActiveAt(
      period.startYear,
      period.endYear,
      selectedYear.value,
      periodStartYears.value,
    );
  });
});

const combinedFeatureVisibility = computed(() => {
  const combined = new Map<string, boolean>();

  const visibleByTimeline = new Set(
    filteredFeatures.value.map((f: Feature) => String(f.id)),
  );

  features.value.forEach((feature: Feature) => {
    const id = String(feature.id);

    // Hide unvalidated or rejected OCR texts from the map
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

function captureForms(): EditorFormDrafts {
  return {
    featureEdit: featureVisibilityControlsRef.value?.getDraft() ?? undefined,
    addMap: addMapDialogRef.value?.getDraft() ?? undefined,
    addImage: addFeatureImageDialogRef.value?.getDraft() ?? undefined,
    createProject: createProjectDialogRef.value?.getDraft() ?? undefined,
  };
}

function snapshotFeatures(): Feature[] {
  const list = mapGeoJsonRef.value?.syncFeaturesFromMapLayers() ?? features.value;
  return cloneFeatureSnapshot(list.map((feature) => ({
    ...feature,
    properties: { ...feature.properties, isVisible: featureVisibility.value.get(feature.id) ?? feature.properties.isVisible ?? true },
  })));
}

const draft = useEditorDraft({
  subject: () => sessionState.subject,
  capture: () => ({
    features: cloneFeatureSnapshot(features.value),
    visibility: [...featureVisibility.value.entries()],
    persistedFeatureIds: [...persistedFeatureIds.value],
    pendingDeletions: [...pendingDeletions.value],
    baseFeatures: cloneFeatureSnapshot(serverFeatures.value),
    forms: captureForms(), savePhase: savePhase.value,
    targetProjectId: saveTargetProjectId.value,
  }),
});

function onDraftChanged() {
  if (restoring || editorLocked.value) return;
  if (savePhase.value === "delete-pending") savePhase.value = "idle";
  draft.markChanged();
}

watch([features, featureVisibility, pendingDeletions], onDraftChanged, { deep: true, flush: "sync" });

async function readServerFeatures(targetProjectId: string, auth: "required" | "optional" = "required"): Promise<Feature[]> {
  const response = await apiFetch(`/projects/${targetProjectId}/features`, { auth });
  if (!response.ok) throw new Error("Impossible de vérifier les changements déjà enregistrés.");
  return snakeToCamel(await response.json()) as Feature[];
}

async function checkServerBase(targetProjectId: string): Promise<boolean> {
  if (!serverLoaded.value || (saveTargetProjectId.value && saveTargetProjectId.value !== targetProjectId)) {
    recoveryConflict.value = true;
    return false;
  }
  const current = await readServerFeatures(targetProjectId);
  const deletions = new Set(pendingDeletions.value);
  const comparable = (list: Feature[]) => savePhase.value === "delete-pending"
    ? list.filter((feature) => !deletions.has(String(feature.id))) : list;
  recoveryConflict.value = !haveSameEditorFeatures(comparable(current), comparable(serverFeatures.value));
  if (!recoveryConflict.value) {
    serverFeatures.value = cloneFeatureSnapshot(current);
    serverLoaded.value = true;
    if (savePhase.value === "put-pending") savePhase.value = "idle";
  }
  return !recoveryConflict.value;
}

async function restoreDraft(saved: EditorDraft, resumeSave = false) {
  if (editorLocked.value || !projectId.value) return;
  if (saved.projectId !== projectId.value) return;
  if (saved.subject !== null && saved.subject !== sessionState.subject) return;
  restoring = true;
  isLoadingEditor.value = true;
  try {
    // Refresh immediately before recovery, including for guests viewing public maps.
    let currentServer: Feature[] = [];
    try {
      currentServer = await readServerFeatures(projectId.value, "optional");
      serverLoaded.value = true;
    } catch {
      serverLoaded.value = false;
    }
    features.value = featureHistoryService.reset(saved.features);
    featureVisibility.value = new Map(saved.visibility);
    pendingDeletions.value = [...saved.pendingDeletions];
    persistedFeatureIds.value = new Set(saved.persistedFeatureIds);
    serverFeatures.value = cloneFeatureSnapshot(saved.baseFeatures);
    savePhase.value = saved.savePhase;
    saveTargetProjectId.value = saved.targetProjectId;
    const deleted = new Set(saved.pendingDeletions);
    const comparable = (list: Feature[]) => saved.savePhase === "delete-pending"
      ? list.filter((feature) => !deleted.has(String(feature.id))) : list;
    recoveryConflict.value = !serverLoaded.value ||
      (!!saved.targetProjectId && saved.targetProjectId !== projectId.value) ||
      !haveSameEditorFeatures(comparable(currentServer), comparable(saved.baseFeatures));
    await nextTick();
    if (saved.forms.featureEdit) await featureVisibilityControlsRef.value?.restoreDraft(saved.forms.featureEdit);
    if (saved.forms.addMap) addMapDialogRef.value?.restoreDraft(saved.forms.addMap);
    if (saved.forms.addImage) addFeatureImageDialogRef.value?.restoreDraft(saved.forms.addImage);
    if (saved.forms.createProject) {
      pendingCopiedFeatures.value = cloneFeatureSnapshot(saved.features);
      shouldSaveAfterCopy.value = true;
      createProjectDialogRef.value?.restoreDraft(saved.forms.createProject);
    }
    await draft.adopt(saved);
  } catch (error) {
    showAlert("error", error instanceof Error ? error.message : "La récupération a échoué. Le brouillon a été conservé.");
    return;
  } finally {
    restoring = false;
    isLoadingEditor.value = false;
  }
  if (resumeSave && !saved.forms.createProject && !recoveryConflict.value && sessionState.status === "authenticated") {
    await onSaveMap(undefined, true);
  } else {
    showAlert("success", "Brouillon récupéré. Vos modifications sont disponibles dans l’éditeur.");
  }
}

async function discardDraft(saved: EditorDraft) {
  if (!window.confirm("Supprimer définitivement ce brouillon local ?")) return;
  try { await draft.discardCandidate(saved); }
  catch { showAlert("error", "Impossible de supprimer le brouillon."); }
}

async function protectEditorBeforeLeave() {
  if (editorLocked.value) return false;
  try {
    if (draft.dirty.value) features.value = snapshotFeatures();
    await draft.flush();
    return true;
  }
  catch { return false; }
}
onBeforeRouteLeave(protectEditorBeforeLeave);
onBeforeRouteUpdate(async (to, from) => to.params.projectId === from.params.projectId || await protectEditorBeforeLeave());

const beforeUnload = (event: BeforeUnloadEvent) => {
  if (!draft.dirty.value || redirecting.value) return;
  event.preventDefault();
  event.returnValue = "";
};

async function preserveBeforeAuthRedirect(intent: "resume" | "save") {
  if (editorLocked.value) throw new Error("Patientez jusqu’à la fin de l’opération avant de vous reconnecter.");
  redirecting.value = true;
  try {
    await nextTick();
    features.value = snapshotFeatures();
    await draft.prepareRedirect(intent);
    return window.location.origin + route.fullPath;
  } catch (error) {
    redirecting.value = false;
    throw error;
  }
}

// A failed SDK redirect must unlock the editor and restore the unload warning.
watch(() => sessionState.redirectError, (error) => {
  if (error) redirecting.value = false;
});

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
      resolve({ width: 1, height: 1 }); // fallback: square, backend will recompute
    };
    img.src = url;
  });
}

async function onAddFeatureImage(file: File) {
  // No silent token check here: closing the dialog would drop the selected
  // file. apiFetch reports a lost session and the dialog stays open.
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
      auth: "required",
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
    showAlert("error", isAuthRequiredError(e)
      ? "Votre session a expiré. Reconnectez-vous : l’image sélectionnée est conservée."
      : "Impossible d’ajouter l’image. Réessayez.");
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
    auth: "required",
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
    // persistCustomLabelStyles already confirmed the save to the user.
  } catch (error) {
    console.error("Failed to save project label styles:", error);
    showAlert(
      "error",
      "Impossible d'enregistrer les styles. Vérifiez que vous êtes propriétaire du projet.",
    );
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
      (feature: Feature) => feature.id !== featureId,
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
      auth: "required",
      method: "DELETE",
    });

    if (!res.ok) {
      throw new Error(`Failed to delete map: ${res.status}`);
    }

    const nextFeatures = features.value.filter(
      (feature: Feature) => feature.mapId !== mapId,
    );

    if (trackingEnabled.value) {
      commitFeatureSnapshot(nextFeatures);
    } else {
      applyFeatureSnapshot(nextFeatures, false);
    }

    await loadProjectMapsForTimeline();

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
    if (await onSaveMap(nextFeatures)) callbacks?.onSuccess?.();
    else callbacks?.onError?.("Les modifications restent dans le brouillon. La sauvegarde n’est pas terminée.");
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

  // 1. Check in-memory cache from recent import session
  let img = getOriginalMapImage(mapId);

  // 2. If not found, look for an image feature belonging to this map in the project
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
    if (!(await onSaveMap(nextFeatures))) return;
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
        auth: "required",
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
  const targetProjectId = projectId.value;

  if (!targetProjectId || !formPayload.title.trim()) {
    return;
  }
  if (formPayload.startDate > formPayload.endDate) return;

  isCreatingMap.value = true;
  try {
    const res = await apiFetch(`/projects/${targetProjectId}/maps`, {
      auth: "required",
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
    // The dialog stays open, and its fields are part of the local draft.
    showAlert("error", isAuthRequiredError(e)
      ? "Votre session a expiré. Reconnectez-vous : le formulaire est conservé."
      : "Impossible de créer la carte. Réessayez.");
  } finally {
    isCreatingMap.value = false;
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
  serverLoaded.value = false;
  if (!projectId.value) {
    features.value = [];
    featureVisibility.value = new Map();
    serverFeatures.value = [];
    return;
  }

  const wasRestoring = restoring;
  restoring = true;
  try {
    const res = await apiFetch(`/projects/${projectId.value}/features`);
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = snakeToCamel(await res.json()) as Feature[];
    serverFeatures.value = cloneFeatureSnapshot(allFeatures);
    serverLoaded.value = true;

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
  } finally {
    restoring = wasRestoring;
  }
}

// Opens the map on the project's elements instead of a fixed location. Only
// called when a project or map is opened, so saving never moves the view.
async function frameVisibleFeatures() {
  // Let MapGeoJSON render the freshly loaded features first
  await nextTick();
  mapGeoJsonRef.value?.fitToVisibleFeatures();
}

// Coming back from an import (?carte=<mapId>): moves the timeline onto the map
// that was just extracted and frames it, rather than the whole project.
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

  // The marker is single-use: a reload should open on the whole project again.
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

async function isProjectOwner(targetProjectId: string): Promise<boolean> {
  const res = await apiFetch(`/projects/is-owner/${targetProjectId}`, { auth: "required" });
  if (!res.ok) throw new Error("Impossible de vérifier la propriété du projet. Réessayez dans un instant.");
  return (await res.json()) === true;
}

async function saveAsCopy() {
  if (editorLocked.value) return;
  pendingCopiedFeatures.value = snapshotFeatures();
  shouldSaveAfterCopy.value = true;
  await openCreateCopyDialog();
  onDraftChanged();
  if (!keycloak.authenticated || sessionState.status === "reauth-required") {
    await reconnect().catch(() => {});
  }
}

function onCreateProjectError(message: string) {
  showAlert("error", message);
}

function onCreateProjectDialogClosed() {
  pendingCopiedFeatures.value = null;
  shouldSaveAfterCopy.value = false;
}

// The copy starts empty: give it its own maps (periods + dates) and point each
// feature at the matching new map, otherwise the features keep the source
// project's map ids and the copy has no timeline nor map groups.
async function copyMapsIntoProject(
  sourceProjectId: string,
  targetProjectId: string,
  featuresToCopy: Feature[],
): Promise<Feature[]> {
  const res = await apiFetch(
    `/projects/${targetProjectId}/copy-maps-from/${sourceProjectId}`,
    {
      auth: "required",
      method: "POST",
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

  // Drop id/projectId so the backend creates new rows in the copy.
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
    saveTargetProjectId.value = targetProjectId;
    savePhase.value = "put-pending";
    await draft.flush(null, true);

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

    isSaving.value = false;
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
  if (
    showTextValidationModal.value ||
    document.querySelector("dialog[open]") ||
    isEditableTarget(e.target)
  ) {
    return;
  }

  const isMod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();

  if (isMod && key === "c" && copySelectedFeature()) {
    e.preventDefault();
    return;
  }

  if (isMod && key === "v" && copiedFeature.value) {
    e.preventDefault();
    pasteCopiedFeature();
    return;
  }

  if (key === "delete" && selectedFeatureId.value) {
    const selectedFeature = features.value.find(
      (feature: Feature) => String(feature.id) === selectedFeatureId.value,
    );
    if (selectedFeature) {
      e.preventDefault();
      featureVisibilityControlsRef.value?.showDeleteFeatureDialog(
        selectedFeature,
      );
    }
    return;
  }

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
    target.closest(".modal") ||
    target.closest("dialog")
  ) {
    return;
  }
  if (selectedFeatureId.value) {
    selectedFeatureId.value = null;
  }
}

async function initializeEditor() {
  isLoadingEditor.value = true;
  restoring = true;
  let resume: EditorDraft | null = null;
  try {
    featureVisibilityControlsRef.value?.closeEditFeatureDialog?.();
    addMapDialogRef.value?.close();
    addFeatureImageDialogRef.value?.close();
    createProjectDialogRef.value?.close();
    features.value = featureHistoryService.reset([]);
    featureVisibility.value = new Map();
    pendingDeletions.value = [];
    persistedFeatureIds.value = new Set();
    serverFeatures.value = [];
    serverLoaded.value = false;
    recoveryConflict.value = false;
    savePhase.value = "idle";
    saveTargetProjectId.value = undefined;
    selectedFeatureId.value = null;
    copiedFeature.value = null;
    pendingCopiedFeatures.value = null;
    shouldSaveAfterCopy.value = false;
    await resolveRouteContext();
    await fetchCurrentUser();
    await Promise.all([
      loadProjectMapsForTimeline(), loadCustomLabelStyles(), loadCurrentMapInfo(), loadInitialFeatures(),
    ]);
    if (disposed || !projectId.value) return;
    await draft.initialize(projectId.value);
    resume = await draft.takeResume();
  } catch (error) {
    showAlert("error", error instanceof Error ? error.message : "Impossible de charger le projet.");
  } finally {
    restoring = false;
    isLoadingEditor.value = false;
  }
  if (disposed) return;
  if (resume) await restoreDraft(resume, resume.intent === "save");
  else if (draft.candidates.value.length === 0 && projectId.value) {
    // Migrate the old guest-save format only after durable storage succeeds.
    const legacyKey = `pending_public_edits_${projectId.value}`;
    try {
      const raw = localStorage.getItem(legacyKey);
      if (raw) {
        features.value = JSON.parse(raw) as Feature[];
        reconcileVisibility(features.value);
        draft.markChanged();
        await draft.flush();
        localStorage.removeItem(legacyKey);
      }
    } catch {
      showAlert("error", "Les anciennes modifications sont conservées, mais leur récupération a échoué.");
    }
  }
  await frameOpenedProject();
}

onMounted(async () => {
  window.addEventListener("keydown", handleKeyboardShortcuts);
  window.addEventListener("click", onDocumentClick);
  window.addEventListener("beforeunload", beforeUnload);
  unregisterAuthRedirect = registerAuthRedirectHandler(preserveBeforeAuthRedirect);
  await initializeEditor();
});

watch(projectRouteId, initializeEditor);

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
      selectedYear.value = markers[0];
    }
  },
  { immediate: true },
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
  disposed = true;
  unregisterAuthRedirect?.();
  window.removeEventListener("keydown", handleKeyboardShortcuts);
  window.removeEventListener("click", onDocumentClick);
  window.removeEventListener("beforeunload", beforeUnload);
  stopSidebarResize();
  clearAlert();
});

async function saveFeaturesToProject(
  targetProjectId: string,
  featuresToSave: Feature[],
  deletionIds: string[] = [],
): Promise<void> {
  const pendingDeleteSet = new Set(deletionIds);
  const savingCurrentProject = projectId.value === targetProjectId;
  const resumeDelete = savePhase.value === "delete-pending" && saveTargetProjectId.value === targetProjectId;
  saveTargetProjectId.value = targetProjectId;

  if (!resumeDelete) {
    // Persist the phase before sending: losing a response must never blindly
    // replay the creation of new feature IDs after reconnecting.
    savePhase.value = "put-pending";
    await draft.flush(null, true);
    const response = await apiFetch(`/projects/${targetProjectId}/features`, {
      auth: "required",
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(camelToSnake(prepareFeaturesForSave(featuresToSave))),
    });
    if (!response.ok) throw new Error(`Erreur de sauvegarde : ${response.status}`);
    const saved = snakeToCamel(await response.json()) as Feature[];
    if (savingCurrentProject) {
      serverFeatures.value = cloneFeatureSnapshot(saved);
      serverLoaded.value = true;
      features.value = saved.filter((feature) => !pendingDeleteSet.has(String(feature.id)));
      persistedFeatureIds.value = new Set(saved.map((feature) => String(feature.id)));
      reconcileVisibility(features.value);
    }
    savePhase.value = deletionIds.length ? "delete-pending" : "idle";
    await draft.flush(null, true);
  }

  if (deletionIds.length > 0) {
    const bulkDeleteResponse = await apiFetch(
      `/projects/${targetProjectId}/features`,
      {
        auth: "required",
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(deletionIds),
      },
    );

    if (!bulkDeleteResponse.ok) {
      throw new Error(`La suppression a échoué (${bulkDeleteResponse.status}). Le brouillon est conservé.`);
    }
  }
  if (savingCurrentProject) {
    serverFeatures.value = serverFeatures.value.filter((feature) => !pendingDeleteSet.has(String(feature.id)));
    persistedFeatureIds.value = new Set(serverFeatures.value.map((feature) => String(feature.id)));
  }
  pendingDeletions.value = [];
  savePhase.value = "idle";
  saveTargetProjectId.value = undefined;
  recoveryConflict.value = false;
  await nextTick();
  await draft.complete(Object.values(captureForms()).some(Boolean));
  mapGeoJsonRef.value?.clearDraftLayers();
  // A thumbnail failure must not turn a committed save into an uncertain one.
  void uploadMapThumbnail(targetProjectId).catch((error) => console.error("Thumbnail update failed:", error));
}

async function onSaveMap(featuresOverride?: Feature[], resumeSave = false): Promise<boolean> {
  if (editorLocked.value) return false;
  restoring = true;
  features.value = featuresOverride ? cloneFeatureSnapshot(featuresOverride) : snapshotFeatures();
  reconcileVisibility(features.value);
  restoring = false;
  draft.markChanged();
  isSaving.value = true;
  mapGeoJsonRef.value?.resetSelection();
  let needsLogin = false;
  try {
    await draft.flush(null, true);
    if (!keycloak.authenticated || !keycloak.token || sessionState.status === "reauth-required") {
      throw new AuthRequiredError();
    }
    const targetProjectId = await requireProjectId();
    const isOwner = await isProjectOwner(targetProjectId);
    if (!isOwner) {
      pendingCopiedFeatures.value = cloneFeatureSnapshot(features.value);
      shouldSaveAfterCopy.value = true;
      await openCreateCopyDialog();
      await draft.flush(null, true);
      return false;
    }
    if (recoveryConflict.value || !(await checkServerBase(targetProjectId))) {
      showAlert("error", "Le contenu du serveur a changé. Votre brouillon est conservé ; créez une copie pour garder vos modifications.");
      return false;
    }
    await saveFeaturesToProject(
      targetProjectId,
      features.value,
      pendingDeletions.value,
    );
    showAlert("success", "Projet sauvegardé avec succès !");
    return true;
  } catch (err) {
    needsLogin = isAuthRequiredError(err) && !resumeSave;
    showAlert("error", err instanceof Error ? err.message : "La sauvegarde a échoué. Le brouillon est conservé.");
  } finally {
    isSaving.value = false;
  }
  // Release the save lock before the preservation hook runs. A resumed save
  // never redirects again automatically if the new session is also rejected.
  if (needsLogin) await reconnect({ intent: "save" }).catch(() => {});
  return false;
}
</script>
