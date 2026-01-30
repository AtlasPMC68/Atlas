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
            <ImportPreview :image-file="selectedFile" :image-url="previewUrl" />
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

    <!-- Modal de géoréférencement -->
    <GeoRefModal
      v-if="showGeorefModal && previewUrl"
      :is-open="showGeorefModal"
      :image-url="previewUrl"
      @close="showGeorefModal = false"
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

<script setup>
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { useImportStore } from "../../stores/import";
import { useFileUpload } from "../../composables/useFileUpload";
import { useImportProcess } from "../../composables/useImportProcess";
import { useSiftPoints } from "../../composables/useSiftPoints";

// Components
import FileDropZone from "../../components/import/FileDropZone.vue";
import ImportPreview from "../../components/import/ImportPreview.vue";
import ImportControls from "../../components/import/ImportControls.vue";
import ProcessingModal from "../../components/import/ProcessingModal.vue";
import GeoRefModal from "../../components/georef/GeoRefModal.vue";
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

// État local
const currentStep = ref(1);
const showWorldAreaPickerModal = ref(false);
const showGeorefModal = ref(false);
const worldAreaBounds = ref(null); // { west, south, east, north } or null
const worldAreaZoom = ref(null);
const worldPolyline = ref([]); // [ [lat,lng], ... ]
const imagePolyline = ref([]); // [ [x,y], ... ]
const worldPoint = ref(null); // [lat, lng] or null
const imagePoint = ref(null); // [x, y] or null

// Gestionnaires d'événements
const handleFileSelected = (file) => {
  onFileSelected(file);
  currentStep.value = 2;
};

async function startImportProcess() {
  if (!selectedFile.value) return;
  currentStep.value = 3;
  showWorldAreaPickerModal.value = true;
}

function handleWorldAreaClose() {
  showWorldAreaPickerModal.value = false;
  // Go back to preview step if the user cancels.
  currentStep.value = 2;
}

async function handleWorldAreaConfirmed(payload) {
  // payload: { bounds: {west,south,east,north}, zoom }
  worldAreaBounds.value = payload.bounds;
  worldAreaZoom.value = payload.zoom;
  showWorldAreaPickerModal.value = false;

  // Call backend to get coastline keypoints for this ROI.
  // For now we just log the response so you can verify the wiring.
  const res = await fetchCoastlineKeypoints(payload.bounds);
  if (res.success) {
    console.log("/maps/coastline-keypoints ->", res.data);
  } else {
    console.error("Failed to fetch coastline keypoints:", res.error);
  }

  // Next step: georeferencing (existing modal)
  currentStep.value = 4;
  showGeorefModal.value = true;
}

async function handleGeorefConfirmed(payload) {
  imagePolyline.value = payload.imagePolyline;
  worldPolyline.value = payload.worldPolyline;
  imagePoint.value = payload.imagePoint;
  worldPoint.value = payload.worldPoint;
  showGeorefModal.value = false;

  // Pass polylines and points to startImport
  const result = await startImport(
    selectedFile.value, 
    imagePolyline.value, 
    worldPolyline.value,
    imagePoint.value,
    worldPoint.value
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
  showGeorefModal.value = false;
  worldAreaBounds.value = null;
  worldAreaZoom.value = null;
  importStore.resetImport();
};
</script>
