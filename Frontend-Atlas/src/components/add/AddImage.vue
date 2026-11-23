<template>
  <dialog ref="addFeatureImageDialogRef" class="modal">
    <div class="modal-box relative">
      <button
        type="button"
        class="btn btn-sm btn-circle btn-ghost absolute right-4 top-4 z-10"
        :disabled="isAdding"
        @click="onCloseAddFeatureImageDialog"
      >
        ✕
      </button>

      <h3 class="text-xl font-bold mb-4 pr-10">Ajouter une image</h3>

      <fieldset class="fieldset">
        <input
          ref="fileInputRef"
          type="file"
          class="file-input file-input-ghost"
          accept="image/*"
          @change="onFileChange"
        />
        <span class="text-xs text-base-content/60 mt-1">Taille maximale : 10 Mo</span>
      </fieldset>
      <div class="modal-action mt-6 flex justify-end gap-2">
        <button
          type="button"
          class="modal-secondary-btn w-32"
          :disabled="isAdding"
          @click="onCloseAddFeatureImageDialog"
        >
          Annuler
        </button>
        <button
          type="button"
          class="btn btn-primary rounded-lg w-32"
          :disabled="isAdding || !selectedFile"
          @click="onAddFeatureImage"
        >
          <span
            v-if="isAdding"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Ajouter</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isAdding">close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  isAdding: boolean;
}>();

const emit = defineEmits<{
  submit: [file: File];
}>();

const addFeatureImageDialogRef = ref<HTMLDialogElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);

function resetSelection() {
  selectedFile.value = null;
  if (fileInputRef.value) {
    fileInputRef.value.value = "";
  }
}

function onFileChange() {
  const input = fileInputRef.value;
  selectedFile.value = input?.files?.[0] ?? null;
}

function onCloseAddFeatureImageDialog() {
  resetSelection();
  addFeatureImageDialogRef.value?.close();
}

function onAddFeatureImage() {
  if (!selectedFile.value) {
    onCloseAddFeatureImageDialog();
    return;
  }
  emit("submit", selectedFile.value);
}

function open() {
  resetSelection();
  addFeatureImageDialogRef.value?.showModal();
}

function close() {
  onCloseAddFeatureImageDialog();
}

defineExpose({
  open,
  close,
});
</script>
