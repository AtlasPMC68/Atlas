<script>
</script>

<template>
  <div class="min-h-screen bg-base-200 p-10">
    <h1 class="text-2xl font-bold mb-4">Test Drop Zone</h1>

    <div class="w-[600px]">
        <FileDropZone 
      :is-loading="isLoading"
      @file-selected="handleFile"
    />
    </div>

    <div v-if="selectedFile" class="mt-6">
      <p class="font-medium">Fichier sélectionné :</p>
      <ul class="list-disc pl-5">
        <li><strong>Nom :</strong> {{ selectedFile.name }}</li>
        <li><strong>Taille :</strong> {{ (selectedFile.size / 1024).toFixed(2) }} KB</li>
        <li><strong>Type :</strong> {{ selectedFile.type }}</li>
      </ul>

      <img 
        v-if="previewUrl" 
        :src="previewUrl" 
        alt="Preview" 
        class="mt-4 rounded border w-96 max-w-full"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import FileDropZone from '../components/import/FileDropZone.vue'

const selectedFile = ref<File | null>(null)
const previewUrl = ref<string>('')
const isLoading = ref(false)

const handleFile = (file: File) => {
  selectedFile.value = file

  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = URL.createObjectURL(file)
}

watch(selectedFile, (newVal) => {
  if (!newVal && previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
})
</script>
