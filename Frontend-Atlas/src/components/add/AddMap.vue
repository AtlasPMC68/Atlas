<template>
  <dialog ref="addMapDialogRef" class="modal">
    <div class="modal-box p-0">
      <form @submit.prevent="createMapForProject">
        <div class="card-body">
          <h3 class="text-lg font-bold">Ajouter une carte au projet</h3>

          <fieldset class="fieldset" :disabled="isCreatingMap">
            <label class="label">Nom de la carte</label>
            <input
              v-model="newMapTitle"
              type="text"
              class="input"
              placeholder="Ex: Carte politique de 1850"
              required
            />
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="label">Date debut</label>
                <input
                  v-if="!usePreciseDates"
                  v-model.number="startYear"
                  type="number"
                  min="1"
                  max="9999"
                  class="input"
                  placeholder="Ex: 1850"
                  required
                />
                <input
                  v-else
                  v-model="startDate"
                  type="date"
                  class="input"
                  required
                />
              </div>

              <div>
                <label class="label">Date fin</label>
                <input
                  v-if="!usePreciseDates"
                  v-model.number="endYear"
                  type="number"
                  min="1"
                  max="9999"
                  class="input"
                  placeholder="Ex: 1900"
                />
                <input v-else v-model="endDate" type="date" class="input" />
              </div>
            </div>
          </fieldset>
          <label class="label cursor-pointer gap-2 mb-2">
            <input
              v-model="usePreciseDates"
              type="checkbox"
              class="checkbox checkbox-sm"
            />
            <span>Utiliser la date exacte</span>
          </label>
          <div class="flex justify-end gap-2 mt-6">
            <button
              type="button"
              class="btn btn-ghost"
              :disabled="isCreatingMap"
              @click="addMapDialogRef?.close()"
            >
              Annuler
            </button>
            <button
              type="submit"
              class="btn btn-primary"
              :disabled="
                !newMapTitle.trim() || !hasValidImportDates() || isCreatingMap
              "
            >
              <span
                v-if="isCreatingMap"
                class="loading loading-spinner loading-xs"
              ></span>
              <span v-else>Creer et importer</span>
            </button>
          </div>
        </div>
      </form>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isCreatingMap">close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { yearToIsoEnd, yearToIsoStart } from "../../utils/dateUtils";

type AddMapPayload = {
  title: string;
  startDate: string;
  endDate: string;
  exactDate: boolean;
};

defineProps<{
  isCreatingMap: boolean;
}>();

const emit = defineEmits<{
  submit: [payload: AddMapPayload];
}>();

const addMapDialogRef = ref<HTMLDialogElement | null>(null);
const newMapTitle = ref("");
const startYear = ref<number | null>(null);
const endYear = ref<number | null>(null);
const startDate = ref("");
const endDate = ref("");
const usePreciseDates = ref(false);

function resetForm() {
  newMapTitle.value = "";
  startYear.value = null;
  endYear.value = null;
  startDate.value = "";
  endDate.value = "";
  usePreciseDates.value = false;
}

function open() {
  resetForm();
  addMapDialogRef.value?.showModal();
}

function close() {
  addMapDialogRef.value?.close();
}

function getStartDateForImport(): string | null {
  if (usePreciseDates.value) {
    if (!startDate.value) return null;
    const parsed = new Date(startDate.value);
    if (Number.isNaN(parsed.getTime())) return null;
    return startDate.value;
  }

  if (!startYear.value || startYear.value < 1 || startYear.value > 9999) {
    return null;
  }
  return yearToIsoStart(startYear.value);
}

function getEndDateForImport(): string | null {
  if (usePreciseDates.value) {
    if (!endDate.value) return null;
    const parsed = new Date(endDate.value);
    if (Number.isNaN(parsed.getTime())) return null;
    return endDate.value;
  }

  if (!endYear.value || endYear.value < 1 || endYear.value > 9999) {
    return null;
  }
  return yearToIsoEnd(endYear.value);
}

function hasValidImportDates(): boolean {
  const start = getStartDateForImport();
  const end = getEndDateForImport();
  if (!start || !end) return false;
  return start <= end;
}

function createMapForProject() {
  if (!newMapTitle.value.trim() || !hasValidImportDates()) return;

  const start = getStartDateForImport();
  const end = getEndDateForImport();
  if (!start || !end || start > end) return;

  emit("submit", {
    title: newMapTitle.value.trim(),
    startDate: start,
    endDate: end,
    exactDate: usePreciseDates.value,
  });
}

defineExpose({
  open,
  close,
});
</script>
