<template>
  <div
    class="bg-white rounded-[14px] p-8 max-w-lg w-full mx-auto shadow-[0_1px_4px_rgba(0,0,0,0.07)] flex flex-col gap-6 text-center"
  >
    <div>
      <h2 class="text-lg font-bold text-gray-900">{{ heading }}</h2>
      <p class="text-sm text-gray-500 mt-1">{{ subheading }}</p>
    </div>

    <template v-if="state === 'failed'">
      <div class="alert alert-error text-sm text-left">
        {{ error || "L'extraction a échoué." }}
      </div>
      <button type="button" class="btn btn-outline btn-sm self-center" @click="emit('back')">
        Retour aux paramètres
      </button>
    </template>

    <template v-else>
      <div class="w-full">
        <div class="flex justify-between text-xs text-gray-500 mb-2">
          <span>{{ stepLabel }}</span>
          <span v-if="state === 'running'">{{ Math.round(progress) }}%</span>
        </div>
        <progress
          v-if="state === 'running'"
          class="progress w-full [&::-webkit-progress-value]:bg-indigo-600 [&::-moz-progress-bar]:bg-indigo-600"
          :value="progress"
          max="100"
        />
        <progress v-else class="progress w-full" />
      </div>

      <button
        type="button"
        class="btn btn-outline btn-sm self-center"
        :disabled="state === 'cancelling'"
        @click="emit('cancel')"
      >
        {{ state === "cancelling" ? "Annulation…" : "Annuler" }}
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ExtractionState } from "../../typescript/importSession";

const props = withDefaults(
  defineProps<{
    state: ExtractionState;
    progress?: number;
    // The task's own progress line (English, from the worker).
    status?: string;
    error?: string | null;
  }>(),
  { progress: 0, status: "", error: null },
);

const emit = defineEmits<{
  (e: "cancel"): void;
  (e: "back"): void;
}>();

// The worker reports its step in English; the page speaks French.
const STATUS_LABELS: [string, string][] = [
  ["Loading", "Chargement de l'image"],
  ["Detecting cities", "Détection des villes dans le texte"],
  ["aligning", "Alignement de la carte sur la géographie"],
  ["shapes", "Extraction des formes"],
  ["colors", "Extraction des couleurs"],
  ["Saving", "Enregistrement"],
];

const heading = computed(() =>
  props.state === "failed" ? "L'extraction a échoué" : "Extraction en cours",
);

const subheading = computed(() => {
  switch (props.state) {
    case "waiting_for_text":
      return "L'analyse du texte de la carte se termine ; l'extraction démarre juste après.";
    case "cancelling":
      return "Arrêt en cours. Rien ne sera enregistré.";
    case "failed":
      return "Vos paramètres sont conservés : vous pouvez les corriger et relancer.";
    default:
      return "Veuillez patienter pendant que nous analysons votre carte.";
  }
});

const stepLabel = computed(() => {
  if (props.state === "waiting_for_text") return "Analyse du texte";
  if (props.state === "queued") return "En file d'attente";
  const match = STATUS_LABELS.find(([key]) => props.status.includes(key));
  return match ? match[1] : "Traitement";
});
</script>
