<template>
  <div class="flex flex-col gap-3.5">
    <div class="flex justify-between items-start gap-3">
      <div>
        <h2 class="m-0 text-[19px] font-bold text-gray-900">Paramètres d'extraction</h2>
        <p class="m-0 mt-0.5 text-[13px] text-gray-500">
          {{
            ready
              ? "Toutes les étapes requises sont complètes."
              : "Complétez les étapes pour préparer l'extraction de données."
          }}
        </p>
      </div>
      <span
        v-if="ready"
        class="shrink-0 bg-green-100 rounded-lg px-2.5 py-1 flex items-center gap-1 text-[11px] text-green-600 font-bold"
      >
        <CheckIcon class="w-3.5 h-3.5" />
        Prêt
      </span>
    </div>

    <!-- Carte -->
    <ChecklistGroup
      title="Carte"
      :tone="mapDone === 2 ? 'done' : 'pending'"
      :badge="mapDone === 2 ? '2 / 2 complètes' : 'Requis'"
    >
      <ChecklistItem
        title="Zone sur le monde"
        :description="
          steps.zone.status === 'done'
            ? 'Zone définie'
            : 'Délimiter la région couverte par votre carte'
        "
        :status="steps.zone.status"
        :highlight="nextStep === 'zone'"
        :disabled="disabled"
        @open="emit('open', 'zone')"
      />
      <ChecklistItem
        title="Délimiter la légende"
        :description="legendDescription"
        :status="steps.legend.status"
        :highlight="nextStep === 'legend'"
        :disabled="disabled"
        @open="emit('open', 'legend')"
      />
    </ChecklistGroup>

    <!-- Points de contrôle -->
    <ChecklistGroup
      title="Points de contrôle"
      :tone="pointsLocked ? 'locked' : steps.sift.status === 'done' ? 'progress' : 'pending'"
      :locked="pointsLocked"
      :locked-hint="pointsLocked ? 'Disponible après la zone sur le monde' : ''"
      :badge="pointsLocked ? '' : `${pointsDone} / 2 complètes`"
    >
      <ChecklistItem
        title="Points SIFT automatiques"
        :description="
          steps.sift.status === 'done'
            ? `${siftCount} paires de points confirmées`
            : 'Géoréférencement assisté par l\'algorithme'
        "
        :status="steps.sift.status"
        :highlight="nextStep === 'sift'"
        :disabled="disabled"
        @open="emit('open', 'sift')"
      />
      <ChecklistItem
        title="Villes"
        :description="
          steps.cities.status === 'done'
            ? `${cityCount} ville${cityCount > 1 ? 's' : ''} placée${cityCount > 1 ? 's' : ''}`
            : 'Points de contrôle manuels sur les villes'
        "
        :status="steps.cities.status"
        :required="false"
        :disabled="disabled"
        @open="emit('open', 'cities')"
      />
    </ChecklistGroup>

    <!-- Couleurs -->
    <ChecklistGroup
      title="Couleurs"
      :tone="steps.colors.status === 'done' ? 'done' : 'pending'"
      :badge="steps.colors.status === 'done' ? 'Complété' : 'Requis'"
    >
      <ChecklistItem
        title="Couleurs à extraire"
        description="Sélection par pipette sur la carte"
        :status="steps.colors.status"
        :highlight="nextStep === 'colors'"
        :disabled="disabled"
        @open="emit('open', 'colors')"
      >
        <template v-if="steps.colors.status === 'done'" #detail>
          <div class="flex flex-wrap gap-1.5 mt-1.5 items-center">
            <span
              v-for="(color, index) in zoneColors"
              :key="index"
              class="w-3.5 h-3.5 rounded-[3px] border border-black/10"
              :style="{ backgroundColor: color.hex }"
              :title="color.name"
            />
            <span class="text-[11px] text-gray-400 ml-0.5">
              {{ zoneColors.length }} zone{{ zoneColors.length > 1 ? "s" : "" }}
              sélectionnée{{ zoneColors.length > 1 ? "s" : "" }}
            </span>
          </div>
        </template>
      </ChecklistItem>
    </ChecklistGroup>

    <!-- Options -->
    <ChecklistGroup v-if="options" title="Options d'extraction" tone="locked">
      <label
        v-for="option in OPTION_ROWS"
        :key="option.key"
        class="px-4 py-3 flex items-center gap-3 cursor-pointer border-b border-gray-50 last:border-b-0 hover:bg-gray-50"
      >
        <input
          type="checkbox"
          class="w-4 h-4 accent-indigo-600 cursor-pointer"
          :checked="options[option.key]"
          :disabled="disabled"
          @change="toggleOption(option.key, ($event.target as HTMLInputElement).checked)"
        />
        <span class="flex-1">
          <span class="block text-sm font-semibold text-gray-900">{{ option.title }}</span>
          <span class="block text-[11px] text-gray-400">{{ option.description }}</span>
        </span>
      </label>
    </ChecklistGroup>

    <!-- Start -->
    <div class="flex flex-col gap-1.5">
      <button
        type="button"
        class="w-full py-3.5 rounded-[11px] text-[15px] font-bold flex items-center justify-center gap-2"
        :class="
          ready && !disabled
            ? 'bg-indigo-600 text-white shadow-[0_4px_14px_rgba(79,70,229,0.35)] hover:bg-indigo-700'
            : 'bg-gray-200 text-gray-400 cursor-not-allowed'
        "
        :disabled="!ready || disabled"
        @click="emit('start')"
      >
        <PlayIcon class="w-4 h-4" />
        Commencer l'extraction
      </button>
      <p class="m-0 text-center text-[11px] text-gray-400">
        {{
          ready
            ? "Les étapes optionnelles peuvent être complétées avant ou après."
            : "Complétez la zone, la légende, les points SIFT et les couleurs pour continuer."
        }}
      </p>
      <p v-if="ocrLabel" class="m-0 text-center text-[11px]" :class="ocrLabel.tone">
        <span
          v-if="ocrState === 'pending' || ocrState === 'running'"
          class="loading loading-spinner loading-xs align-middle mr-1"
        />
        {{ ocrLabel.text }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { CheckIcon } from "@heroicons/vue/24/solid";
import { PlayIcon } from "@heroicons/vue/24/outline";
import ChecklistGroup from "./ChecklistGroup.vue";
import ChecklistItem from "./ChecklistItem.vue";
import {
  canStartExtraction,
  cityPoints,
  deriveStepStates,
  siftPoints,
} from "../../utils/importSteps";
import type {
  ImportInputs,
  ImportOptions,
  OcrState,
  StepId,
} from "../../typescript/importSession";

const props = withDefaults(
  defineProps<{
    inputs: ImportInputs;
    // Omitted where the options do not apply (dev-test).
    options?: ImportOptions | null;
    // Null where no background OCR runs (dev-test).
    ocrState?: OcrState | null;
    disabled?: boolean;
  }>(),
  { options: null, ocrState: null, disabled: false },
);

const emit = defineEmits<{
  (e: "open", step: StepId): void;
  (e: "update:options", options: ImportOptions): void;
  (e: "start"): void;
}>();

const OPTION_ROWS: { key: keyof ImportOptions; title: string; description: string }[] = [
  {
    key: "textExtraction",
    title: "Extraction de texte (OCR)",
    description: "Ajouter les noms de lieux détectés comme points sur la carte",
  },
  {
    key: "shapesExtraction",
    title: "Extraction des formes",
    description: "Détecter les formes géométriques (cercles, rectangles, etc.)",
  },
];

const steps = computed(() => deriveStepStates(props.inputs));
const ready = computed(() => canStartExtraction(props.inputs));

// The next required step to do, drawn in the primary colour.
const nextStep = computed<StepId | null>(() => {
  const order: StepId[] = ["zone", "legend", "sift", "colors"];
  return order.find((id) => steps.value[id].status === "available") ?? null;
});

const mapDone = computed(
  () =>
    Number(steps.value.zone.status === "done") +
    Number(steps.value.legend.status === "done"),
);
const pointsLocked = computed(() => steps.value.sift.status === "locked");
const pointsDone = computed(
  () =>
    Number(steps.value.sift.status === "done") +
    Number(steps.value.cities.status === "done"),
);
const siftCount = computed(() => siftPoints(props.inputs).length);
const cityCount = computed(() => cityPoints(props.inputs).length);
const zoneColors = computed(() => (props.inputs.colors ?? []).filter((c) => c.kind === "zone"));

const legendDescription = computed(() => {
  const legend = props.inputs.legend;
  if (!legend) return "Zone ignorée par l'extraction, ou aucune légende";
  return legend.present ? "Légende délimitée" : "Aucune légende sur la carte";
});

const ocrLabel = computed<{ text: string; tone: string } | null>(() => {
  switch (props.ocrState) {
    case "pending":
    case "running":
      return { text: "Analyse du texte de la carte en cours…", tone: "text-gray-400" };
    case "done":
      return { text: "Analyse du texte terminée", tone: "text-green-600" };
    case "failed":
      return {
        text: "L'analyse du texte a échoué ; elle sera relancée avec l'extraction.",
        tone: "text-amber-600",
      };
    default:
      return null;
  }
});

function toggleOption(key: keyof ImportOptions, value: boolean) {
  if (!props.options) return;
  emit("update:options", { ...props.options, [key]: value });
}
</script>
