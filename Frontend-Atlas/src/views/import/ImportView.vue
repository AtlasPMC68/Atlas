<template>
  <div class="min-h-screen bg-base-200 p-6">
    <div class="max-w-4xl mx-auto">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-base-content mb-2">
          Importer une carte
          <span
            v-if="isDevTest && (routeMapId || devTestCaseName)"
            class="ml-2 text-sm font-normal text-base-content/60"
          >
            <span v-if="routeMapId">test: {{ routeMapId }}</span>
            <span v-if="routeMapId && devTestCaseName"> · </span>
            <span v-if="devTestCaseName">case: {{ devTestCaseName }}</span>
          </span>
        </h1>
        <p class="text-base-content/70">
          {{
            isDevTest
              ? "Utiliser la carte associée au test actuel"
              : "Glissez votre image de carte ou cliquez pour la sélectionner"
          }}
        </p>
      </div>

      <!-- Process steps -->
      <div class="steps w-full mb-8">
        <div class="step" :class="{ 'step-primary': currentStep >= 1 }">
          Sélection
        </div>
        <div class="step" :class="{ 'step-primary': currentStep >= 2 }">
          Prévisualisation
        </div>
        <div class="step" :class="{ 'step-primary': currentStep >= 3 }">
          Zone sur le monde
        </div>
        <div class="step" :class="{ 'step-primary': currentStep >= 4 }">
          Géoréférencement
        </div>
        <div class="step" :class="{ 'step-primary': currentStep >= 5 }">
          Légende
        </div>
        <div class="step" :class="{ 'step-primary': currentStep >= 6 }">
          Extraction
        </div>
      </div>

      <!-- Main content by step -->
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <!-- Step 1: Drag & Drop -->
          <FileDropZone
            v-if="currentStep === 1"
            @file-selected="handleFileSelected"
            :is-loading="isUploading"
          />

          <!-- Step 2: Preview + Controls -->
          <div v-else-if="currentStep === 2" class="space-y-6">
            <ImportPreview
              v-if="selectedFile"
              :image-file="selectedFile"
              :image-url="previewUrl"
            />

            <!-- Extraction Options -->
            <div
              v-if="!isDevTest"
              class="bg-base-200 rounded-lg p-4 space-y-3"
            >
              <h3 class="font-semibold text-sm mb-3">Options d'extraction</h3>

              <!-- Georeferencing Option -->
              <label
                class="flex items-center gap-3 cursor-pointer hover:bg-base-300 p-2 rounded"
              >
                <input
                  type="checkbox"
                  v-model="enableGeoreferencing"
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <div class="flex-1">
                  <div class="font-medium text-sm">Géoréférencement SIFT</div>
                  <div class="text-xs text-base-content/60">
                    Placer la carte dans l'espace géographique avec des points
                    de contrôle
                  </div>
                </div>
              </label>

              <!-- Color Extraction -->
              <label
                class="flex items-center gap-3 cursor-pointer hover:bg-base-300 p-2 rounded"
              >
                <input
                  type="checkbox"
                  v-model="enableColorExtraction"
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <div class="flex-1">
                  <div class="font-medium text-sm">
                    Extraction des zones colorées
                  </div>
                  <div class="text-xs text-base-content/60">
                    Détecter et extraire les régions par couleur (pays,
                    territoires, etc.)
                  </div>
                </div>
              </label>

              <!-- Shapes Extraction -->
              <label
                class="flex items-center gap-3 cursor-pointer hover:bg-base-300 p-2 rounded"
              >
                <input
                  type="checkbox"
                  v-model="enableShapesExtraction"
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <div class="flex-1">
                  <div class="font-medium text-sm">Extraction des formes</div>
                  <div class="text-xs text-base-content/60">
                    Détecter les formes géométriques (cercles, rectangles, etc.)
                  </div>
                </div>
              </label>

              <!-- Text Extraction -->
              <label
                class="flex items-center gap-3 cursor-pointer hover:bg-base-300 p-2 rounded"
              >
                <input
                  type="checkbox"
                  v-model="enableTextExtraction"
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <div class="flex-1">
                  <div class="font-medium text-sm">
                    Extraction de texte (OCR)
                  </div>
                  <div class="text-xs text-base-content/60">
                    Détecter et extraire le texte de la carte (noms de lieux,
                    légendes)
                  </div>
                </div>
              </label>
            </div>

            <ImportControls
              @start-import="startImportProcess"
              @cancel="resetImport"
              :is-processing="isProcessing"
              start-label="Confirmer carte"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- World area selection modal -->
     <WorldAreaPickerModal
      v-if="showWorldAreaPickerModal && previewUrl"
      :is-open="showWorldAreaPickerModal"
      :image-url="previewUrl"
      :initial-bounds="worldAreaBounds"
      :initial-zoom="worldAreaZoom ?? 2"
      @close="handleWorldAreaClose"
      @confirmed="handleWorldAreaConfirmed"
    />

    <!-- SIFT-based georeferencing modal -->
    <GeoRefSiftModal
      v-if="
        showSiftGeorefModal &&
        previewUrl &&
        worldAreaBounds &&
        coastlineKeypoints
      "
      :is-open="showSiftGeorefModal"
      :image-url="previewUrl"
      :world-bounds="worldAreaBounds"
      :keypoints="coastlineKeypoints"
      :used-lakes="usedLakes"
      @close="showSiftGeorefModal = false"
      @confirmed="handleGeorefConfirmed"
    />

    <!-- Processing modal -->
    <ProcessingModal
      v-if="showProcessingModal"
      :is-open="showProcessingModal"
      :current-step="processingStep"
      :progress="processingProgress"
      @cancel="cancelImport"
    />

    <!-- Legend area selection modal -->
    <LegendAreaPickerModal
      v-if="showLegendPickerModal && previewUrl"
      :is-open="showLegendPickerModal"
      :image-url="previewUrl"
      :initial-bounds="legendBounds"
      @close="handleLegendClose"
      @skip="handleLegendSkip"
      @confirmed="handleLegendConfirmed"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useImportStore } from "../../stores/import";
import { useFileUpload } from "../../composables/useFileUpload";
import { useImportProcess } from "../../composables/useImportProcess";
import { useDevTestImportProcess } from "../../composables/useDevTestImportProcess";
import { useSiftPoints } from "../../composables/useSiftPoints";
import { apiFetch } from "../../utils/api";
import { snakeToCamel } from "../../utils/utils";
import type {
  WorldBounds,
  LatLngTuple,
  XYTuple,
  CoastlineKeypoint,
  WorldAreaSelection,
} from "../../typescript/georef";
import type { LegendBounds } from "../../typescript/legend";

// Components
import FileDropZone from "../../components/import/FileDropZone.vue";
import ImportPreview from "../../components/import/ImportPreview.vue";
import ImportControls from "../../components/import/ImportControls.vue";
import ProcessingModal from "../../components/import/ProcessingModal.vue";
import GeoRefSiftModal from "../../components/georef/GeoRefSiftModal.vue";
import WorldAreaPickerModal from "../../components/import/WorldAreaPickerModal.vue";
import LegendAreaPickerModal from "../../components/legend/LegendAreaPickerModal.vue";

const router = useRouter();
const route = useRoute();
const importStore = useImportStore();

const routeMapId = computed(() => String(route.params.mapId)).value;

type ImportMode = "user" | "dev-test";

const mode = (route.meta.importMode as ImportMode | undefined) ?? "user";
const isDevTest = computed(() => mode === "dev-test");
const routeProjectId = computed(() => {
  const qp = route.query.projectId;
  return typeof qp === "string" ? qp : null;
}).value;

// Composables
const {
  selectedFile,
  previewUrl,
  isUploading,
  handleFileSelected: onFileSelected,
} = useFileUpload();

const prodImport = useImportProcess();
const devImport = useDevTestImportProcess();

// Pick the reactive state from the composable that matches the current mode.
// isDevTest is based on a const so this selection is stable for the component lifetime.
const activeImport = isDevTest.value ? devImport : prodImport;
const {
  isProcessing,
  processingStep,
  processingProgress,
  showProcessingModal,
  cancelImport,
  resultData,
  mapId,
} = activeImport;

const { fetchCoastlineKeypoints } = useSiftPoints();

// Types

interface GeorefPayload {
  worldPoints: LatLngTuple[];
  imagePoints: XYTuple[];
}

// Local state
const currentStep = ref<number>(1);
const showWorldAreaPickerModal = ref<boolean>(false);
const showSiftGeorefModal = ref<boolean>(false);
const showLegendPickerModal = ref<boolean>(false);
const worldAreaBounds = ref<WorldBounds | null>(null); // { west, south, east, north } or null
const worldAreaZoom = ref<number | null>(null);
const coastlineKeypoints = ref<CoastlineKeypoint[] | null>(null); // SIFT coastline keypoints from backend
const legendBounds = ref<LegendBounds | null>(null);
const pendingGeorefPayload = ref<GeorefPayload | null>(null);
const legendReturnStep = ref<number>(2);
const usedLakes = ref<boolean>(false); // Whether lakes were used to find keypoints

// Dev-test: stable identifier to store assets/config under backend tests/assets
const devTestCaseName = ref<string | null>(null);
const isRedirecting = ref<boolean>(false);

// Extraction options (all enabled by default)
const enableGeoreferencing = ref<boolean>(true);
const enableColorExtraction = ref<boolean>(true);
const enableShapesExtraction = ref<boolean>(false);
const enableTextExtraction = ref<boolean>(false);

// Event handlers
const handleFileSelected = (file: File) => {
  onFileSelected(file);
  currentStep.value = 2;
};

async function startImportProcess() {
  if (!selectedFile.value) return;

  if (!isDevTest.value) {
    devTestCaseName.value = null;
  }

  if (isDevTest.value) {
    if (!devTestCaseName.value) {
      const entered = window.prompt(
        routeMapId
          ? `Nom du test-case pour le test ${routeMapId} (ex: '5 sift points')`
          : "Nom du test-case (scénario, ex: '5 sift points')",
        "",
      );
      const trimmed = (entered ?? "").trim();
      if (!trimmed) return;
      devTestCaseName.value = trimmed;
    }
    // In test mode, force georeferencing and color extraction on,
    // and disable other extraction options.
    enableGeoreferencing.value = true;
    enableColorExtraction.value = true;
    enableShapesExtraction.value = false;
    enableTextExtraction.value = false;
  }
  
  // If georeferencing is disabled, skip world area selection and go straight to upload
  // Note: dev-test mode always forces georef on, so this path is production-only.
  if (!enableGeoreferencing.value) {
    pendingGeorefPayload.value = null;
    legendReturnStep.value = 2;
    currentStep.value = 5;
    showLegendPickerModal.value = true;

    const importProjectId =
      routeProjectId ?? (await resolveProjectIdFromMapId(routeMapId));
    if (!importProjectId) {
      console.error("Impossible de resoudre le project_id pour cette importation");
      currentStep.value = 2;
      return;
    }

    const result = await prodImport.startImport(
      selectedFile.value,
      importProjectId,
      routeMapId,
      undefined,
      undefined,
      {
        enableGeoreferencing: false,
        enableColorExtraction: enableColorExtraction.value,
        enableShapesExtraction: enableShapesExtraction.value,
        enableTextExtraction: enableTextExtraction.value,
      },
    );
    if (result.success) {
      currentStep.value = 5;
    } else {
      console.error("Erreur importation:", result.error);
    }
    return;
  }

  // With georeferencing enabled, show world area picker
  currentStep.value = 3;
  showWorldAreaPickerModal.value = true;
}

function handleWorldAreaClose() {
  showWorldAreaPickerModal.value = false;
  // Go back to preview step if the user cancels.
  currentStep.value = 2;
}

async function handleWorldAreaConfirmed(payload: WorldAreaSelection) {
  // payload: { bounds: {west,south,east,north}, zoom }
  worldAreaBounds.value = payload.bounds;
  worldAreaZoom.value = payload.zoom;
  showWorldAreaPickerModal.value = false;

  // Call backend to get coastline keypoints for this ROI and
  // store the result for the next georef step.
  const res = await fetchCoastlineKeypoints(payload.bounds);
  if (res.success && res.data) {
    // Prefer backend bounds if it returns a more precise ROI
    worldAreaBounds.value = res.data.bounds || payload.bounds;
    coastlineKeypoints.value = res.data.keypoints;
    usedLakes.value = res.data.used_lakes || false;

    // Next step: SIFT-based georeferencing
    currentStep.value = 4;
    showSiftGeorefModal.value = true;
  } else {
    console.error("Failed to fetch coastline keypoints:", res.error);
    // In case of error, go back to previous step
    currentStep.value = 2;
  }
}

async function handleGeorefConfirmed(payload: GeorefPayload) {
  // payload: { worldPoints: [ [lat,lng], ... ], imagePoints: [ [x,y], ... ] }
  showSiftGeorefModal.value = false;

  pendingGeorefPayload.value = payload;
  legendReturnStep.value = 4;
  currentStep.value = 5;
  showLegendPickerModal.value = true;
}

async function submitImportWithGeoref(legend: LegendBounds | null) {
  if (!selectedFile.value) return;

  const payload = pendingGeorefPayload.value;

  const imagePoints = payload
    ? payload.imagePoints.map(([x, y]) => ({ x, y }))
    : undefined;
  const worldPoints = payload
    ? payload.worldPoints.map(([lat, lng]) => ({ lat, lng }))
    : undefined;

  if (isDevTest.value) {
    if (!devTestCaseName.value) {
      console.error("[DEV-TEST] Test case name is missing");
      currentStep.value = 2;
      return;
    }
    const result = await devImport.startImport(
      selectedFile.value,
      routeMapId,
      devTestCaseName.value,
      imagePoints,
      worldPoints,
    );
    if (result.success) {
      currentStep.value = 6;
    } else {
      console.error("Erreur importation:", result.error);
      currentStep.value = 2;
    }
    pendingGeorefPayload.value = null;
    return;
  }

  // Production path
  const importProjectId =
    routeProjectId ?? (await resolveProjectIdFromMapId(routeMapId));
  if (!importProjectId) {
    console.error("Impossible de resoudre le project_id pour cette importation");
    currentStep.value = 2;
    return;
  }

  const result = await prodImport.startImport(
    selectedFile.value,
    importProjectId,
    routeMapId,
    imagePoints,
    worldPoints,
    {
      enableGeoreferencing: Boolean(payload),
      enableColorExtraction: enableColorExtraction.value,
      enableShapesExtraction: enableShapesExtraction.value,
      enableTextExtraction: enableTextExtraction.value,
    },
    legend,
  );
  if (result.success) {
    currentStep.value = 6;
  } else {
    console.error("Erreur importation:", result.error);
    currentStep.value = 2;
  }

  pendingGeorefPayload.value = null;
}

function handleLegendClose() {
  showLegendPickerModal.value = false;
  if (legendReturnStep.value === 4) {
    showSiftGeorefModal.value = true;
    currentStep.value = 4;
    return;
  }

  currentStep.value = 2;
}

async function handleLegendSkip() {
  showLegendPickerModal.value = false;
  legendBounds.value = null;
  await submitImportWithGeoref(null);
}

async function handleLegendConfirmed(bounds: LegendBounds) {
  showLegendPickerModal.value = false;
  legendBounds.value = bounds;
  await submitImportWithGeoref(bounds);
}

async function resolveProjectIdFromMapId(id: string): Promise<string | null> {
  try {
    const response = await apiFetch(`/projects/map-project/${id}`);

    if (!response.ok) return null;

    const data = snakeToCamel(
      (await response.json()) as { project_id?: string },
    ) as { projectId?: string };

    return data.projectId ?? null;
  } catch {
    return null;
  }
}

// Redirect when extraction is finished
watch([isProcessing, resultData, mapId], async ([processing, result, id]) => {
  if (isRedirecting.value || processing || !result || !id) return;

  isRedirecting.value = true;

  if (isDevTest.value) {
    const caseName = devTestCaseName.value;
    if (caseName) {
      router.push({ path: `/test-editor/${id}/case/${encodeURIComponent(caseName)}` });
    } else {
      router.push({ path: `/test-editor/${id}` });
    }
    return;
  }

  const projectId = await resolveProjectIdFromMapId(String(id));
  if (projectId) {
    await router.push(`/projet/${projectId}`);
    return;
  }

  await router.push(`/tableau-de-bord`);
});

const resetImport = () => {
  currentStep.value = 1;
  showWorldAreaPickerModal.value = false;
  showSiftGeorefModal.value = false;
  showLegendPickerModal.value = false;
  worldAreaBounds.value = null;
  worldAreaZoom.value = null;
  legendBounds.value = null;
  pendingGeorefPayload.value = null;
  coastlineKeypoints.value = null;
  usedLakes.value = false;
  importStore.resetImport();
};
</script>
