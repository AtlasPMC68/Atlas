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

    <ImportPreview
    v-if="selectedFile && previewUrl"
    :image-file="selectedFile"
    :image-url="previewUrl"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import FileDropZone from '../components/import/FileDropZone.vue'
import ImportPreview from '../components/import/ImportPreview.vue'

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
