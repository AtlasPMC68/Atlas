<template>
  <dialog ref="addFeatureImageDialogRef" class="modal" @close="onDialogClose" @cancel="onCancel">
    <div class="modal-box">
      <h3 class="text-lg font-bold mb-4">Ajouter une image</h3>

      <fieldset class="fieldset" :disabled="isAdding">
        <input
          ref="fileInputRef"
          type="file"
          class="file-input file-input-ghost"
          accept="image/*"
          @change="onFileChange"
        />
        <label class="label">Taille maximale de 10MB</label>
        <p v-if="selectedFile" class="text-sm break-all">Fichier sélectionné : {{ selectedFile.name }}</p>
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
import { ref, watch } from "vue";
import type { AddImageFormDraft } from "../../typescript/editorDraft";

const props = defineProps<{
  isAdding: boolean;
}>();

const emit = defineEmits<{
  submit: [file: File];
  "draft-change": [];
}>();

const addFeatureImageDialogRef = ref<HTMLDialogElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);

watch(selectedFile, () => {
  if (addFeatureImageDialogRef.value?.open) emit("draft-change");
});

function getDraft(): AddImageFormDraft | null {
  return addFeatureImageDialogRef.value?.open ? { selectedFile: selectedFile.value } : null;
}

function restoreDraft(draft: AddImageFormDraft) {
  selectedFile.value = draft.selectedFile;
  // Browsers do not allow restoring a file input; keep the File in component state.
  if (fileInputRef.value) fileInputRef.value.value = "";
  if (!addFeatureImageDialogRef.value?.open) addFeatureImageDialogRef.value?.showModal();
  emit("draft-change");
}

function onDialogClose() {
  resetSelection();
  emit("draft-change");
}

function onCancel(event: Event) {
  if (props.isAdding) event.preventDefault();
}

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
  if (props.isAdding) return;
  if (!selectedFile.value) {
    onCloseAddFeatureImageDialog();
    return;
  }
  emit("submit", selectedFile.value);
}

function open() {
  resetSelection();
  addFeatureImageDialogRef.value?.showModal();
  emit("draft-change");
}

function close() {
  onCloseAddFeatureImageDialog();
}

defineExpose({
  open,
  close,
  getDraft,
  restoreDraft,
});
</script>
