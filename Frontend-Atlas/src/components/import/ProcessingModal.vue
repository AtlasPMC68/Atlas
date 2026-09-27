<template>
  <div class="modal modal-open">
    <div class="modal-box max-w-md">
      <div class="text-center space-y-6">
        <!-- Header -->
        <div>
          <h3 class="font-bold text-lg">Extraction en cours</h3>
          <p class="text-base-content/70 mt-2">
            Veuillez patienter pendant que nous analysons votre carte
          </p>
        </div>

        <ProcessingSteps :current-step="currentStep" :progress="progress" />

        <div class="w-full">
          <div class="flex justify-between text-sm text-base-content/70 mb-2">
            <span>{{ translatedMessage }}</span>
            <span>{{ Math.round(progress) }}%</span>
          </div>
          <progress
            class="progress progress-primary w-full"
            :value="progress"
            max="100"
          ></progress>
        </div>

        <div class="modal-action justify-center">
          <button class="btn btn-outline btn-sm" @click="$emit('cancel')">
            Annuler
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import ProcessingSteps from "./ProcessingSteps.vue";

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false,
  },
  currentStep: {
    type: String,
    default: "upload",
  },
  progress: {
    type: Number,
    default: 0,
  },
  message: {
    type: String,
    default: "",
  },
});

defineEmits(["cancel"]);

const translatedMessage = computed(() => {
  if (!props.message) return 'Progression globale';
  const translations = {
    "Processing step 1": "Traitement de l'étape 1",
    "Saving uploaded file": "Sauvegarde du fichier",
    "Loading and validating image": "Chargement et validation de l'image",
    "Extracting text with OCR pipeline": "Extraction du texte (OCR)",
    "Extracting shapes from image": "Extraction des formes",
    "Skipping text extraction (dev-test mode)": "Saut de l'extraction de texte (mode dev-test)",
    "Skipping shapes extraction (dev-test mode)": "Saut de l'extraction des formes (mode dev-test)",
    "Extracting colors from image": "Extraction des couleurs",
    "Cleaning up and finalizing": "Nettoyage et finalisation",
    "Saving test assets": "Sauvegarde des données de test"
  };
  return translations[props.message] || props.message;
});
</script>
