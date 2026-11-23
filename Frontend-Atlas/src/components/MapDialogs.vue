<template>
  <AddImageDialog
    ref="addFeatureImageDialogRef"
    :is-adding="isAdding"
    @submit="emit('add-feature-image', $event)"
  />

  <AddMapDialog
    ref="addMapDialogRef"
    :is-creating-map="isCreatingMap"
    @submit="emit('create-map', $event)"
  />

  <DuplicateMapDialog
    ref="duplicateMapDialogRef"
    :map-periods="mapPeriods"
    :is-duplicating="isDuplicatingMap"
    @submit="emit('duplicate-map', $event)"
  />

  <EditMapPeriodDialog
    ref="editMapPeriodDialogRef"
    @save="emit('save-map-period', $event)"
  />

  <CreateProjectDialog
    ref="createProjectDialogRef"
    @created="emit('project-created', $event)"
    @error="emit('project-error', $event)"
    @closed="emit('project-dialog-closed')"
  />

  <TextValidationModal
    :is-open="showTextValidationModal"
    :map-id="activeValidationMapId"
    :image-url="validationImageUrl"
    :map-title="validationMapTitle"
    :initial-items="textValidationEntries"
    :is-submitting="isSavingTextValidation"
    :custom-label-styles="customLabelStyles"
    @confirm="emit('confirm-text-validation', $event)"
    @cancel="emit('cancel-text-validation')"
    @save-label-styles="emit('save-label-styles', $event)"
  />
</template>

<script setup lang="ts">
import { ref } from "vue";
import AddImageDialog from "./add/AddImage.vue";
import AddMapDialog from "./add/AddMap.vue";
import DuplicateMapDialog from "./add/DuplicateMapDialog.vue";
import EditMapPeriodDialog from "./add/EditMapPeriodDialog.vue";
import CreateProjectDialog from "./CreateProjectDialog.vue";
import TextValidationModal from "./import/TextValidationModal.vue";
import type { MapPeriod } from "../typescript/map";
import type { CustomLabelStyle } from "../utils/labelPresentation";
import type { TextValidationEntry } from "../utils/textValidation";
import type { CreatedProjectRef, CreateProjectDialogExposed } from "../typescript/project";

defineProps<{
  mapPeriods: MapPeriod[];
  isAdding: boolean;
  isCreatingMap: boolean;
  isDuplicatingMap: boolean;
  showTextValidationModal: boolean;
  activeValidationMapId: string | null;
  validationImageUrl: string | null;
  validationMapTitle: string;
  textValidationEntries: TextValidationEntry[];
  isSavingTextValidation: boolean;
  customLabelStyles: CustomLabelStyle[];
}>();

const emit = defineEmits<{
  (e: "add-feature-image", payload: any): void;
  (e: "create-map", payload: any): void;
  (e: "duplicate-map", payload: any): void;
  (e: "save-map-period", payload: any): void;
  (e: "project-created", payload: CreatedProjectRef): void;
  (e: "project-error", message: string): void;
  (e: "project-dialog-closed"): void;
  (e: "confirm-text-validation", items: TextValidationEntry[]): void;
  (e: "cancel-text-validation"): void;
  (e: "save-label-styles", styles: CustomLabelStyle[]): void;
}>();

const addFeatureImageDialogRef = ref<InstanceType<typeof AddImageDialog> | null>(null);
const addMapDialogRef = ref<InstanceType<typeof AddMapDialog> | null>(null);
const duplicateMapDialogRef = ref<InstanceType<typeof DuplicateMapDialog> | null>(null);
const editMapPeriodDialogRef = ref<InstanceType<typeof EditMapPeriodDialog> | null>(null);
const createProjectDialogRef = ref<CreateProjectDialogExposed | null>(null);

defineExpose({
  openAddImageDialog: () => addFeatureImageDialogRef.value?.open(),
  closeAddImageDialog: () => addFeatureImageDialogRef.value?.close(),
  openAddMapDialog: () => addMapDialogRef.value?.open(),
  closeAddMapDialog: () => addMapDialogRef.value?.close(),
  openDuplicateMapDialog: (targetId: string) => duplicateMapDialogRef.value?.open(targetId),
  closeDuplicateMapDialog: () => duplicateMapDialogRef.value?.close(),
  setDuplicateMapError: (msg: string) => duplicateMapDialogRef.value?.setError(msg),
  openEditMapPeriodDialog: (period: MapPeriod) => editMapPeriodDialogRef.value?.open(period),
  closeEditMapPeriodDialog: () => editMapPeriodDialogRef.value?.close(),
  setEditMapPeriodSaving: (v: boolean) => editMapPeriodDialogRef.value?.setSaving(v),
  setEditMapPeriodError: (msg: string) => editMapPeriodDialogRef.value?.setError(msg),
  openCreateProjectDialog: (options?: any) => createProjectDialogRef.value?.open(options),
});
</script>
