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
          Extraction
        </div>
        <div class="step" :class="{ 'step-primary': currentStep >= 4 }">
          Personnalisation
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
            />
          </div>
        </div>
      </div>
    </div>

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

// Components
import FileDropZone from "../../components/import/FileDropZone.vue";
import ImportPreview from "../../components/import/ImportPreview.vue";
import ImportControls from "../../components/import/ImportControls.vue";
import ProcessingModal from "../../components/import/ProcessingModal.vue";

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

// Local state
const currentStep = ref(1);

// Event handlers
const handleFileSelected = (file) => {
  onFileSelected(file);
  currentStep.value = 2;
};

async function startImportProcess() {
  if (!selectedFile.value) return;

  const result = await startImport(selectedFile.value);
  if (result.success) {
    currentStep.value = 3;
  } else {
    console.error("Erreur importation:", result.error);
  }
}

// Redirect when extraction is finished
watch([isProcessing, resultData, mapId], ([processing, result, id]) => {
  if (!processing && result && id) {
    router.push(`/maps/${id}`);
  }
});

const resetImport = () => {
  currentStep.value = 1;
  importStore.resetImport();
};
</script>
