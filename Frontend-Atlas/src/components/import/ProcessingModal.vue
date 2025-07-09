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
        
        <!-- Étapes de traitement -->
        <ProcessingSteps 
          :current-step="currentStep"
          :progress="progress"
        />
        
        <!-- Barre de progression globale -->
        <div class="w-full">
          <div class="flex justify-between text-sm text-base-content/70 mb-2">
            <span>Progression globale</span>
            <span>{{ Math.round(progress) }}%</span>
          </div>
          <progress 
            class="progress progress-primary w-full" 
            :value="progress" 
            max="100"
          ></progress>
        </div>
        
        <!-- Actions -->
        <div class="modal-action justify-center">
          <button 
            class="btn btn-outline btn-sm"
            @click="$emit('cancel')"
          >
            Annuler
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import ProcessingSteps from './ProcessingSteps.vue'

defineProps({
  isOpen: {
    type: Boolean,
    default: false
  },
  currentStep: {
    type: String,
    default: 'upload'
  },
  progress: {
    type: Number,
    default: 0
  }
})

defineEmits(['cancel'])
</script>