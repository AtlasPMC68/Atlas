<template>
  <dialog ref="dialogRef" class="modal">
    <div class="modal-box p-0">
      <form @submit.prevent="handleSubmit">
        <div class="card-body">
          <h3 class="text-lg font-bold">Dupliquer une carte</h3>

          <p v-if="error" class="text-xs text-error font-medium">{{ error }}</p>

          <fieldset class="fieldset" :disabled="isDuplicating">
            <!-- 1. Choisir la carte à dupliquer -->
            <label class="label font-medium" for="duplicate-source-map">
              Carte à dupliquer
            </label>
            <select
              id="duplicate-source-map"
              v-model="selectedSourceMapId"
              class="select select-bordered w-full"
              required
              data-testid="duplicate-source-map-select"
              @change="onSourceMapChange"
            >
              <option disabled value="">Sélectionnez une carte...</option>
              <option
                v-for="period in props.mapPeriods"
                :key="period.id"
                :value="period.id"
              >
                {{ period.title }} ({{ period.startDate }} - {{ period.endDate }})
              </option>
            </select>

            <!-- 2. Définir le nom de la nouvelle carte -->
            <label class="label font-medium" for="duplicate-map-title">
              Nom de la nouvelle carte
            </label>
            <input
              id="duplicate-map-title"
              v-model="newTitle"
              type="text"
              class="input w-full"
              placeholder="Ex: Carte politique 1850 (copie)"
              required
              data-testid="duplicate-map-title-input"
            />

            <!-- 3. Définir la date associée à la nouvelle carte -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
              <div>
                <label class="label font-medium">Date début</label>
                <input
                  v-if="!usePreciseDates"
                  v-model.number="startYear"
                  type="number"
                  min="1"
                  max="9999"
                  class="input w-full"
                  placeholder="Ex: 1850"
                  required
                  data-testid="duplicate-map-start-year"
                  @input="onStartYearInput"
                />
                <input
                  v-else
                  v-model="startDate"
                  type="date"
                  class="input w-full"
                  required
                  data-testid="duplicate-map-start-date"
                  @input="onStartDateInput"
                />
              </div>

              <div>
                <label class="label font-medium">Date fin</label>
                <input
                  v-if="!usePreciseDates"
                  v-model.number="endYear"
                  type="number"
                  min="1"
                  max="9999"
                  class="input w-full"
                  placeholder="Ex: 1900"
                  data-testid="duplicate-map-end-year"
                />
                <input
                  v-else
                  v-model="endDate"
                  type="date"
                  class="input w-full"
                  data-testid="duplicate-map-end-date"
                />
              </div>
            </div>
          </fieldset>

          <label class="label cursor-pointer gap-2 mt-2">
            <input
              v-model="usePreciseDates"
              type="checkbox"
              class="checkbox checkbox-sm"
              data-testid="duplicate-map-exact-date-toggle"
            />
            <span class="text-sm">Utiliser des dates exactes</span>
          </label>

          <div class="flex justify-end gap-2 mt-6">
            <button
              type="button"
              class="btn btn-ghost"
              :disabled="isDuplicating"
              @click="close"
            >
              Annuler
            </button>
            <button
              type="submit"
              class="btn btn-primary"
              :disabled="!isValid || isDuplicating"
              data-testid="duplicate-map-submit-button"
            >
              <span
                v-if="isDuplicating"
                class="loading loading-spinner loading-xs"
              ></span>
              <span v-else>Dupliquer</span>
            </button>
          </div>
        </div>
      </form>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isDuplicating" @click="close">close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { MapPeriod } from "../../typescript/map";
import { syncEndFromStart, toYear, yearToIsoEnd, yearToIsoStart } from "../../utils/dateUtils";

const props = defineProps<{
  mapPeriods: MapPeriod[];
  isDuplicating?: boolean;
}>();

const emit = defineEmits<{
  (
    e: "submit",
    payload: {
      sourceMapId: string;
      newTitle: string;
      startDate: string;
      endDate: string;
      exactDate: boolean;
    },
  ): void;
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);
const selectedSourceMapId = ref("");
const newTitle = ref("");
const startDate = ref("");
const endDate = ref("");
const startYear = ref<number | null>(null);
const endYear = ref<number | null>(null);
const usePreciseDates = ref(false);
const error = ref("");

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

function onSourceMapChange() {
  const source = props.mapPeriods.find((p) => p.id === selectedSourceMapId.value);
  if (!source) return;

  if (!newTitle.value || props.mapPeriods.some((p) => `${p.title} (copie)` === newTitle.value)) {
    newTitle.value = `${source.title} (copie)`;
  }

  usePreciseDates.value = Boolean(source.exactDate);
  if (source.exactDate) {
    startDate.value = source.startDate || "";
    endDate.value = source.endDate || source.startDate || "";
  } else {
    startYear.value = toYear(source.startDate);
    endYear.value = toYear(source.endDate);
  }
}

const isValid = computed(() => {
  if (!selectedSourceMapId.value) return false;
  if (!newTitle.value.trim()) return false;

  if (usePreciseDates.value) {
    if (!startDate.value) return false;
    const end = endDate.value || startDate.value;
    return startDate.value <= end;
  }

  if (startYear.value === null || startYear.value === undefined) return false;
  const end = endYear.value ?? startYear.value;
  return startYear.value <= end;
});

function handleSubmit() {
  if (!isValid.value) return;

  let finalStart = "";
  let finalEnd = "";

  if (usePreciseDates.value) {
    finalStart = startDate.value;
    finalEnd = endDate.value || startDate.value;
  } else {
    finalStart = yearToIsoStart(startYear.value!);
    finalEnd = yearToIsoEnd(endYear.value ?? startYear.value!);
  }

  emit("submit", {
    sourceMapId: selectedSourceMapId.value,
    newTitle: newTitle.value.trim(),
    startDate: finalStart,
    endDate: finalEnd,
    exactDate: usePreciseDates.value,
  });
}

function open(preselectedMapId?: string) {
  error.value = "";
  if (preselectedMapId && props.mapPeriods.some((p) => p.id === preselectedMapId)) {
    selectedSourceMapId.value = preselectedMapId;
  } else if (props.mapPeriods.length > 0) {
    selectedSourceMapId.value = props.mapPeriods[0].id;
  } else {
    selectedSourceMapId.value = "";
  }
  newTitle.value = "";
  startDate.value = "";
  endDate.value = "";
  startYear.value = null;
  endYear.value = null;
  usePreciseDates.value = false;

  if (selectedSourceMapId.value) {
    onSourceMapChange();
  }

  dialogRef.value?.showModal();
}

function close() {
  dialogRef.value?.close();
}

function setError(msg: string) {
  error.value = msg;
}

defineExpose({
  open,
  close,
  setError,
});
</script>
