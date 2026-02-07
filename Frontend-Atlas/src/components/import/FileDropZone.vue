<template>
  <div class="w-full">
    <div
      ref="dropZone"
      class="border-2 border-dashed rounded-lg p-12 text-center transition-colors"
      :class="dropZoneClasses"
      @dragover.prevent="onDragOver"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
      @click="openFileDialog"
    >
      <input
        ref="fileInput"
        type="file"
        accept="image/*"
        class="hidden"
        @change="onFileSelect"
      />

      <div v-if="!isLoading" class="space-y-4">
        <div class="text-6xl text-base-content/30">📁</div>
        <div>
          <p class="text-xl font-semibold text-base-content mb-2">
            {{
              isDragOver ? "Déposez votre carte ici" : "Glissez votre carte ici"
            }}
          </p>
          <p class="text-base-content/70">
            ou
            <span
              class="text-primary font-medium cursor-pointer hover:underline"
            >
              cliquez pour parcourir
            </span>
          </p>
        </div>
        <div class="text-sm text-base-content/60">
          Formats supportés: JPG, PNG, GIF (max 10MB)
        </div>
      </div>

      <div v-else class="space-y-4">
        <div class="loading loading-spinner loading-lg text-primary"></div>
        <p class="text-base-content/70">Téléchargement en cours...</p>
      </div>
    </div>

    <div v-if="error" class="alert alert-error mt-4">
      <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
        <path
          fill-rule="evenodd"
          d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
          clip-rule="evenodd"
        />
      </svg>
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";

const props = defineProps({
  isLoading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["file-selected"]);

const dropZone = ref<HTMLElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const isDragOver = ref(false);
const error = ref("");

const dropZoneClasses = computed(() => ({
  "border-primary bg-primary/10": isDragOver.value,
  "border-base-300 bg-base-50 hover:border-primary/50 hover:bg-primary/5":
    !isDragOver.value && !props.isLoading,
  "border-base-200 bg-base-100": props.isLoading,
  "cursor-pointer": !props.isLoading,
}));

const onDragOver = () => {
  isDragOver.value = true;
};

const onDragLeave = (e: DragEvent) => {
  if (!dropZone.value?.contains(e.relatedTarget as Node)) {
    isDragOver.value = false;
  }
};

const onDrop = (e: DragEvent) => {
  isDragOver.value = false;
  const files = Array.from(e.dataTransfer?.files || []);

  if (files.length > 0) {
    handleFile(files[0]);
  }
};

const openFileDialog = () => {
  if (!props.isLoading) {
    fileInput.value?.click();
  }
};

const onFileSelect = (e: Event) => {
  const target = e.target as HTMLInputElement;
  const file = target.files ? target.files[0] : null;
  if (file) {
    handleFile(file);
  }
};

const handleFile = (file: File) => {
  error.value = "";

  if (!file.type.startsWith("image/")) {
    error.value = "Veuillez sélectionner une image valide";
    return;
  }

  if (file.size > 10 * 1024 * 1024) {
    // 10MB
    error.value = "Le fichier ne doit pas dépasser 10MB";
    return;
  }

  emit("file-selected", file);
};
</script>
