<template>
  <dialog ref="dialogRef" class="modal">
    <div class="modal-box relative">
      <button
        type="button"
        class="btn btn-sm btn-circle btn-ghost absolute right-4 top-4 z-10"
        :disabled="saving"
        @click="close"
      >
        ✕
      </button>
      <form @submit.prevent="submit">
        <h3 class="text-xl font-bold mb-4">Modifier la carte</h3>
        <fieldset class="flex flex-col gap-3" :disabled="saving">
          <label class="form-control">
            <span class="label">Nom de la carte</span>
            <input v-model="title" class="input input-bordered" required />
          </label>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label class="form-control">
              <span class="label">Date de début</span>
              <input
                v-if="exactDate"
                v-model="startDate"
                class="input input-bordered"
                type="date"
                required
                @input="onStartDateInput"
              />
              <input
                v-else
                v-model.number="startYear"
                class="input input-bordered"
                type="number"
                min="1"
                max="9999"
                required
                @input="onStartYearInput"
              />
            </label>
            <label class="form-control">
              <span class="label">Date de fin</span>
              <input
                v-if="exactDate"
                v-model="endDate"
                class="input input-bordered"
                type="date"
                required
              />
              <input
                v-else
                v-model.number="endYear"
                class="input input-bordered"
                type="number"
                min="1"
                max="9999"
                required
              />
            </label>
          </div>
          <label class="label cursor-pointer justify-start gap-2">
            <input v-model="exactDate" type="checkbox" class="checkbox checkbox-sm" />
            <span>Utiliser la période exacte</span>
          </label>
        </fieldset>

        <p v-if="errorMessage" class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1 mt-1">{{ errorMessage }}</p>
        <div class="modal-action mt-6 flex justify-end gap-2">
          <button type="button" class="modal-secondary-btn w-32" :disabled="saving" @click="close">
            Annuler
          </button>
          <button type="submit" class="btn btn-primary rounded-lg w-32" :disabled="!isValid || saving">
            <span v-if="saving" class="loading loading-spinner loading-xs"></span>
            <span v-else>Enregistrer</span>
          </button>
        </div>
      </form>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="saving">Fermer</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { MapPeriod } from "../../typescript/map";
import { syncEndFromStart, toYear, yearToIsoEnd, yearToIsoStart } from "../../utils/dateUtils";

const emit = defineEmits<{
  save: [payload: { mapId: string; title: string; startDate: string; endDate: string; exactDate: boolean }];
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);
const mapId = ref("");
const title = ref("");
const startDate = ref("");
const endDate = ref("");
const startYear = ref<number | null>(null);
const endYear = ref<number | null>(null);
const exactDate = ref(false);
const saving = ref(false);
const errorMessage = ref("");

let previousStartYear: number | null = null;
let previousStartDate = "";

function onStartYearInput() {
  if (startYear.value !== null && startYear.value !== undefined) {
    endYear.value = syncEndFromStart(startYear.value, endYear.value, previousStartYear);
    previousStartYear = startYear.value;
  }
}

function onStartDateInput() {
  if (startDate.value) {
    endDate.value = syncEndFromStart(startDate.value, endDate.value, previousStartDate);
    previousStartDate = startDate.value;
  }
}

const isValid = computed(() => {
  const start = exactDate.value
    ? startDate.value
    : startYear.value && startYear.value >= 1 && startYear.value <= 9999
      ? yearToIsoStart(startYear.value)
      : "";
  const end = exactDate.value
    ? endDate.value
    : endYear.value && endYear.value >= 1 && endYear.value <= 9999
      ? yearToIsoEnd(endYear.value)
      : "";
  return !!title.value.trim() && !!start && !!end && start <= end;
});

function open(period: MapPeriod | (Omit<MapPeriod, "color"> & { color?: string })) {
  mapId.value = period.id;
  title.value = period.title;
  startDate.value = period.startDate ?? "";
  endDate.value = period.endDate ?? "";
  startYear.value = period.startDate ? toYear(period.startDate) : null;
  endYear.value = period.endDate ? toYear(period.endDate) : null;
  exactDate.value = period.exactDate;
  errorMessage.value = "";
  dialogRef.value?.showModal();
}

function close() {
  dialogRef.value?.close();
}

function setSaving(value: boolean) {
  saving.value = value;
}

function setError(message: string) {
  errorMessage.value = message;
}

function submit() {
  if (!isValid.value) return;
  const start = exactDate.value
    ? startDate.value
    : yearToIsoStart(startYear.value!);
  const end = exactDate.value
    ? endDate.value
    : yearToIsoEnd(endYear.value!);
  emit("save", {
    mapId: mapId.value,
    title: title.value.trim(),
    startDate: start,
    endDate: end,
    exactDate: exactDate.value,
  });
}

defineExpose({ open, close, setSaving, setError });
</script>
