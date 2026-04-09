<template>
  <dialog
    id="addFeatureImageDialog"
    ref="addFeatureImageDialogRef"
    class="modal"
  >
    <div class="modal-box">
      <h3 class="text-lg font-bold mb-4">Ajouter une image</h3>

      <fieldset class="fieldset">
        <input
          ref="fileInputRef"
          type="file"
          class="file-input file-input-ghost"
          accept="image/*"
          @change="onFileChange"
        />
        <label class="label">Taille maximale de 10MB</label>
      </fieldset>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isAdding"
          @click="onCloseAddFeatureImageDialog"
        >
          Annuler
        </button>
        <button
          class="btn btn-primary"
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
