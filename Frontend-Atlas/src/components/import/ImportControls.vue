<template>
  <div class="flex flex-col sm:flex-row gap-4 justify-between items-center">
    <div class="text-sm text-base-content/70">
      Prêt à extraire les informations de votre carte
    </div>

    <div class="flex gap-3">
      <button
        class="btn btn-outline"
        @click="$emit('cancel')"
        :disabled="isProcessing"
      >
        <svg
          class="w-4 h-4 mr-2"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
        Annuler
      </button>

      <button
        class="btn btn-primary"
        @click="$emit('start-import')"
        :disabled="isProcessing"
      >
        <span v-if="!isProcessing" class="flex items-center">
          <svg
            class="w-4 h-4 mr-2"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M14 5l7 7m0 0l-7 7m7-7H3"
            />
          </svg>
          Commencer l'extraction
        </span>
        <span v-else class="flex items-center">
          <span class="loading loading-spinner loading-sm mr-2"></span>
          Traitement en cours...
        </span>
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  isProcessing: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["start-import", "cancel"]);
</script>
