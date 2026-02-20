<template>
  <div class="min-h-screen bg-base-200 p-6">
    <div class="max-w-4xl mx-auto">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-base-content mb-2">
          Importer une carte
        </h1>
        <p class="text-base-content/70">
          Glissez votre image de carte ou cliquez pour la sélectionner
        </p>
      </div>

      <!-- Étapes du processus -->
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
          Extraction
        </div>
      </div>

      <!-- Contenu principal selon l'étape -->
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <!-- Étape 1: Drag & Drop -->
          <FileDropZone
            v-if="currentStep === 1"
            @file-selected="handleFileSelected"
            :is-loading="isUploading"
          />

          <!-- Étape 2: Prévisualisation + Contrôles -->
          <div v-else-if="currentStep === 2" class="space-y-6">
            <ImportPreview
              v-if="selectedFile"
              :image-file="selectedFile"
              :image-url="previewUrl"
            />
            
            <!-- Extraction Options -->
            <div class="bg-base-200 rounded-lg p-4 space-y-3">
              <h3 class="font-semibold text-sm mb-3">Options d'extraction</h3>
              
              <!-- Georeferencing Option -->
              <label class="flex items-center gap-3 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input 
                  type="checkbox" 
                  v-model="enableGeoreferencing" 
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <div class="flex-1">
                  <div class="font-medium text-sm">Géoréférencement SIFT</div>
                  <div class="text-xs text-base-content/60">Placer la carte dans l'espace géographique avec des points de contrôle</div>
                </div>
              </label>
              
              <!-- Color Extraction -->
              <label class="flex items-center gap-3 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input 
                  type="checkbox" 
                  v-model="enableColorExtraction" 
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <div class="flex-1">
                  <div class="font-medium text-sm">Extraction des zones colorées</div>
                  <div class="text-xs text-base-content/60">Détecter et extraire les régions par couleur (pays, territoires, etc.)</div>
                </div>
              </label>
              
              <!-- Shapes Extraction -->
              <label class="flex items-center gap-3 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input 
                  type="checkbox" 
                  v-model="enableShapesExtraction" 
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <div class="flex-1">
                  <div class="font-medium text-sm">Extraction des formes</div>
                  <div class="text-xs text-base-content/60">Détecter les formes géométriques (cercles, rectangles, etc.)</div>
                </div>
              </label>
              
              <!-- Text Extraction -->
              <label class="flex items-center gap-3 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input 
                  type="checkbox" 
                  v-model="enableTextExtraction" 
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <div class="flex-1">
                  <div class="font-medium text-sm">Extraction de texte (OCR)</div>
                  <div class="text-xs text-base-content/60">Détecter et extraire le texte de la carte (noms de lieux, légendes)</div>
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

    <!-- Modal de sélection de zone monde -->
    <WorldAreaPickerModal
      v-if="showWorldAreaPickerModal && previewUrl"
      :is-open="showWorldAreaPickerModal"
      :image-url="previewUrl"
      :initial-bounds="worldAreaBounds"
      :initial-zoom="worldAreaZoom ?? 2"
      @close="handleWorldAreaClose"
      @confirmed="handleWorldAreaConfirmed"
    />

    <!-- Modal de géoréférencement basé sur les points SIFT -->
    <GeoRefSiftModal
      v-if="showSiftGeorefModal && previewUrl && worldAreaBounds && coastlineKeypoints"
      :is-open="showSiftGeorefModal"
      :image-url="previewUrl"
      :world-bounds="worldAreaBounds"
      :keypoints="coastlineKeypoints"
      @close="showSiftGeorefModal = false"
      @confirmed="handleGeorefConfirmed"
    />

    <!-- Modal de traitement -->
    <ProcessingModal
      v-if="showProcessingModal"
      :is-open="showProcessingModal"
      :current-step="processingStep"
      :progress="processingProgress"
      @cancel="cancelImport"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useImportStore } from "../../stores/import";
import { useFileUpload } from "../../composables/useFileUpload";
import { useImportProcess } from "../../composables/useImportProcess";
import { useSiftPoints } from "../../composables/useSiftPoints";
import type {
  WorldBounds,
  LatLngTuple,
  XYTuple,
  CoastlineKeypoint,
} from "../../typescript/georef";

// Components
import FileDropZone from "../../components/import/FileDropZone.vue";
import ImportPreview from "../../components/import/ImportPreview.vue";
import ImportControls from "../../components/import/ImportControls.vue";
import ProcessingModal from "../../components/import/ProcessingModal.vue";
import GeoRefSiftModal from "../../components/georef/GeoRefSiftModal.vue";
import WorldAreaPickerModal from "../../components/import/WorldAreaPickerModal.vue";

const router = useRouter();
const importStore = useImportStore();

// Composables
const {
  selectedFile,
  previewUrl,
  isUploading,
  handleFileSelected: onFileSelected,
} = useFileUpload();

const {
  isProcessing,
  processingStep,
  processingProgress,
  showProcessingModal,
  startImport,
  cancelImport,
  resultData,
  mapId,
} = useImportProcess();

const { fetchCoastlineKeypoints } = useSiftPoints();

// Types

interface WorldAreaPayload {
  bounds: WorldBounds;
  zoom: number;
}

interface GeorefPayload {
  worldPoints: LatLngTuple[];
  imagePoints: XYTuple[];
}

// État local
const currentStep = ref<number>(1);
const showWorldAreaPickerModal = ref<boolean>(false);
const showSiftGeorefModal = ref<boolean>(false);
const worldAreaBounds = ref<WorldBounds | null>(null); // { west, south, east, north } or null
const worldAreaZoom = ref<number | null>(null);
const coastlineKeypoints = ref<CoastlineKeypoint[] | null>(null); // SIFT coastline keypoints from backend

// Extraction options (all enabled by default)
const enableGeoreferencing = ref<boolean>(true);
const enableColorExtraction = ref<boolean>(true);
const enableShapesExtraction = ref<boolean>(false);
const enableTextExtraction = ref<boolean>(false);

// Gestionnaires d'événements
const handleFileSelected = (file: File) => {
  onFileSelected(file);
  currentStep.value = 2;
};

async function startImportProcess() {
  if (!selectedFile.value) return;
  
  // If georeferencing is disabled, skip world area selection and go straight to upload
  if (!enableGeoreferencing.value) {
    const result = await startImport(
      selectedFile.value,
      undefined,
      undefined,
      {
        enableGeoreferencing: false,
        enableColorExtraction: enableColorExtraction.value,
        enableShapesExtraction: enableShapesExtraction.value,
        enableTextExtraction: enableTextExtraction.value,
      }
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

async function handleWorldAreaConfirmed(payload: WorldAreaPayload) {
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

  // Map to backend-expected shapes
  const worldPoints = payload.worldPoints.map(([lat, lng]) => ({ lat, lng }));
  const imagePoints = payload.imagePoints.map(([x, y]) => ({ x, y }));

  // Pass matched point arrays to startImport with extraction options
  const result = await startImport(
    selectedFile.value,
    imagePoints,
    worldPoints,
    {
      enableGeoreferencing: true,
      enableColorExtraction: enableColorExtraction.value,
      enableShapesExtraction: enableShapesExtraction.value,
      enableTextExtraction: enableTextExtraction.value,
    }
  );
  if (result.success) {
    currentStep.value = 5;
  } else {
    console.error("Erreur importation:", result.error);
  }
}

// Redirect when extraction is finished
watch(
  [isProcessing, resultData, mapId],
  ([processing, result, id]) => {
    if (!processing && result && id) {
      router.push(`/maps/${id}`);
    }
  }
);

const resetImport = () => {
  currentStep.value = 1;
  showWorldAreaPickerModal.value = false;
  showSiftGeorefModal.value = false;
  worldAreaBounds.value = null;
  worldAreaZoom.value = null;
  importStore.resetImport();
};
</script>
