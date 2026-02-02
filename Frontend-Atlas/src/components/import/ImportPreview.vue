<template>
  <div class="space-y-4">
    <h3 class="text-lg font-semibold">Aperçu de la carte</h3>

    <div class="bg-base-200 rounded-lg p-6 flex flex-col items-center">
      <img
        :src="imageUrl"
        :alt="imageFile?.name || 'Carte importée'"
        class="max-h-96 w-auto object-contain rounded shadow"
      />

      <div class="text-sm text-base-content/60 mt-4 text-center">
        {{ imageFile.name }} – {{ formatFileSize(imageFile.size) }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { defineProps } from "vue";

const props = defineProps({
  imageFile: {
    type: File,
    required: true,
  },
  imageUrl: {
    type: String,
    required: true,
  },
});

const formatFileSize = (bytes) => {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
};
</script>
