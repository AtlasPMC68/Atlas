<template>
  <div v-if="cases.length > 0" class="card bg-base-100 shadow-xl">
    <div class="card-body gap-3">
      <h2 class="card-title text-lg">Partir d'un test case existant</h2>
      <p class="text-sm text-base-content/70">
        Les entrées reprises sont exactement celles du cas source, avec l'image
        du test. Ne décochez que ce que ce nouveau cas fait varier : le reste
        reste identique et les deux cas restent comparables. Chaque étape
        reprise peut encore être modifiée (retirer ou replacer des points, des
        couleurs).
      </p>

      <select
        v-model="sourceId"
        class="select select-sm w-full max-w-xs"
        :disabled="isLoadingSource"
        @change="loadSource"
      >
        <option disabled value="">Cas source…</option>
        <option v-for="c in cases" :key="c" :value="c">{{ c }}</option>
      </select>

      <span v-if="isLoadingSource" class="loading loading-spinner loading-sm" />

      <fieldset v-else-if="source" class="fieldset">
        <legend class="fieldset-legend">Entrées à reprendre</legend>
        <label v-for="part in PARTS" :key="part.id" class="label text-sm">
          <input
            v-model="selected"
            type="checkbox"
            class="checkbox checkbox-sm"
            :value="part.id"
            :disabled="isUnavailable(part.id)"
          />
          <span :class="{ 'opacity-50': isUnavailable(part.id) }">{{ part.label }}</span>
          <span v-if="countLabel(part.id)" class="badge badge-sm badge-ghost">
            {{ countLabel(part.id) }}
          </span>
        </label>
        <p class="label text-xs whitespace-normal">
          Les points (SIFT, villes, vérification) ne se reprennent qu'avec la zone
          sur le monde : ils ont été appariés dans celle-ci.
        </p>
      </fieldset>

      <div v-if="error" role="alert" class="alert alert-error alert-soft text-xs py-2">
        <span>{{ error }}</span>
      </div>

      <div class="card-actions justify-end">
        <button
          class="btn btn-primary btn-sm"
          type="button"
          :disabled="!source || effectiveParts.length === 0"
          @click="source && emit('start', source, effectiveParts)"
        >
          Partir de ce cas
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useDevTestCases } from "../../composables/useDevTestCases";
import { casePartCount, PARTS_NEEDING_FRAME, type CasePart } from "../../utils/importSteps";
import type { DevTestCaseInputsResponse } from "../../typescript/devTest";

const props = defineProps<{ testId: string }>();

const emit = defineEmits<{
  (e: "start", source: DevTestCaseInputsResponse, parts: CasePart[]): void;
}>();

const PARTS: { id: CasePart; label: string }[] = [
  { id: "frame", label: "Zone sur le monde" },
  { id: "legend", label: "Légende" },
  { id: "sift", label: "Points SIFT" },
  { id: "cities", label: "Villes" },
  { id: "checks", label: "Points de vérification" },
  { id: "zoneColors", label: "Couleurs des zones" },
  { id: "waterColors", label: "Pipette eau" },
];

const devTestCases = useDevTestCases();
const cases = ref<string[]>([]);
const sourceId = ref("");
const source = ref<DevTestCaseInputsResponse | null>(null);
const selected = ref<CasePart[]>([]);
const isLoadingSource = ref(false);
const error = ref<string | null>(null);

function isUnavailable(part: CasePart): boolean {
  const inputs = source.value?.inputs ?? {};
  if (casePartCount(inputs, part) === 0) return true;
  return PARTS_NEEDING_FRAME.includes(part) && !selected.value.includes("frame");
}

const effectiveParts = computed(() => selected.value.filter((p) => !isUnavailable(p)));

function countLabel(part: CasePart): string {
  const inputs = source.value?.inputs ?? {};
  if (part === "frame") return inputs.frameBounds ? "" : "absente";
  if (part === "legend") {
    if (!inputs.legend) return "non répondue";
    return inputs.legend.present ? "" : "pas de légende";
  }
  return String(casePartCount(inputs, part));
}

async function loadSource() {
  if (!sourceId.value) return;
  isLoadingSource.value = true;
  error.value = null;
  source.value = null;
  try {
    const res = await devTestCases.fetchCaseInputs(props.testId, sourceId.value);
    if (!res.success) {
      error.value = res.error;
      return;
    }
    source.value = res.data;
    // Everything the source has, ticked: a new case usually varies one thing.
    selected.value = PARTS.map((p) => p.id).filter(
      (p) => casePartCount(res.data.inputs ?? {}, p) > 0,
    );
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Impossible de lire le cas";
  } finally {
    isLoadingSource.value = false;
  }
}

// No cases, or no answer: the panel does not show, and the import proceeds.
onMounted(async () => {
  const res = await devTestCases.listCases(props.testId).catch(() => null);
  cases.value = res?.success ? res.data : [];
});
</script>
