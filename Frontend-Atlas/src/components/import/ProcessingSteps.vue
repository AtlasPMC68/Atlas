<template>
  <div class="space-y-4">
    <div
      v-for="step in steps"
      :key="step.id"
      class="flex items-center gap-3 p-3 rounded-lg transition-colors"
      :class="getStepClasses(step)"
    >
      <!-- Icône -->
      <div
        class="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center"
      >
        <svg
          v-if="step.status === 'completed'"
          class="w-5 h-5 text-success"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fill-rule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clip-rule="evenodd"
          />
        </svg>
        <div
          v-else-if="step.status === 'processing'"
          class="loading loading-spinner loading-sm"
        ></div>
        <div v-else class="w-2 h-2 rounded-full bg-base-300"></div>
      </div>

      <!-- Contenu -->
      <div class="flex-1">
        <div class="font-medium">{{ step.title }}</div>
        <div class="text-sm text-base-content/70">{{ step.description }}</div>

        <!-- Barre de progression pour l'étape courante -->
        <div v-if="step.status === 'processing'" class="mt-2">
          <progress
            class="progress progress-primary progress-sm w-full"
            :value="stepProgress"
            max="100"
          ></progress>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  currentStep: {
    type: String,
    default: "upload",
  },
  progress: {
    type: Number,
    default: 0,
  },
});

// Définition des étapes
const steps = [
  {
    id: "upload",
    title: "Téléchargement",
    description: "Envoi de l'image vers le serveur",
  },
  {
    id: "analysis",
    title: "Analyse de l'image",
    description: "Détection des éléments cartographiques",
  },
  {
    id: "extraction",
    title: "Extraction des données",
    description: "Identification des lieux et dates",
  },
  {
    id: "processing",
    title: "Traitement final",
    description: "Préparation de la carte interactive",
  },
];

// Statuts des étapes
const stepsWithStatus = computed(() => {
  const currentIndex = steps.findIndex((step) => step.id === props.currentStep);

  return steps.map((step, index) => ({
    ...step,
    status:
      index < currentIndex
        ? "completed"
        : index === currentIndex
          ? "processing"
          : "pending",
  }));
});

// Progression de l'étape courante
const stepProgress = computed(() => {
  const currentIndex = steps.findIndex((step) => step.id === props.currentStep);
  const baseProgress = (currentIndex / steps.length) * 100;
  const stepProgressPercent =
    (props.progress - baseProgress) / (100 / steps.length);

  return Math.max(0, Math.min(100, stepProgressPercent));
});

// Classes CSS pour chaque étape
const getStepClasses = (step) => ({
  "bg-success/10": step.status === "completed",
  "bg-primary/10": step.status === "processing",
  "bg-base-100": step.status === "pending",
});
</script>
