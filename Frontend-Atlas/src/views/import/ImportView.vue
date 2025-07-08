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
            <ImportPreview 
              :image-file="selectedFile"
              :image-url="previewUrl"
            />
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
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// Mock composables
const selectedFile = ref(null)
const previewUrl = ref('')
const isUploading = ref(false)

const isProcessing = ref(false)
const processingStep = ref(1)
const processingProgress = ref(0)
const showProcessingModal = ref(false)

// Mock composable functions
const onFileSelected = (file) => {
  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  console.log('Mock file selected:', file)
}

const startImport = async () => {
  return new Promise((resolve) =>
    setTimeout(() => resolve({ success: true, mapId: 'demo123' }), 1000)
  )
}

const cancelImport = () => {
  console.log('Import canceled')
}

const importStore = {
  resetImport: () => console.log('Resetting import state')
}

// État local
const currentStep = ref(1)

// Gestionnaires d'événements
const handleFileSelected = (file) => {
  onFileSelected(file)
  currentStep.value = 2
}

const startImportProcess = async () => {
  currentStep.value = 3
  try {
    const result = await startImport(selectedFile.value)
    if (result.success) {
      router.push(`/maps/${result.mapId}/edit`)
    }
  } catch (error) {
    console.error("Erreur lors de l'importation:", error)
  }
}

const resetImport = () => {
  currentStep.value = 1
  importStore.resetImport()
}

// Mock components
const FileDropZone = {
  props: ['isLoading'],
  emits: ['file-selected'],
  template: `
    <div class="p-6 border border-dashed text-center cursor-pointer" @click="$emit('file-selected', new File([], 'mock.png'))">
      [Zone de drop simulée] Cliquez ici pour simuler un fichier
    </div>
  `
}

const ImportPreview = {
  props: ['imageFile', 'imageUrl'],
  template: `<div class="border p-4 text-center">Prévisualisation (mock) : {{ imageUrl }}</div>`
}

const ImportControls = {
  props: ['isProcessing'],
  emits: ['start-import', 'cancel'],
  template: `
    <div class="flex gap-4 justify-center">
      <button class="btn btn-primary" @click="$emit('start-import')">Démarrer</button>
      <button class="btn btn-secondary" @click="$emit('cancel')">Annuler</button>
    </div>
  `
}

const ProcessingModal = {
  props: ['isOpen', 'currentStep', 'progress'],
  emits: ['cancel'],
  template: `
    <div class="fixed inset-0 bg-white bg-opacity-90 z-50 flex items-center justify-center">
      <div class="bg-base-100 p-6 rounded-lg shadow-lg text-center space-y-4">
        <p>Étape : {{ currentStep }} / Progression : {{ progress }}%</p>
        <button class="btn btn-error" @click="$emit('cancel')">Annuler</button>
      </div>
    </div>
  `
}
</script>
