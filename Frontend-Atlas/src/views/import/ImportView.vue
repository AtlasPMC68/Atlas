<template>
  <div class="bg-gray-100 flex flex-col lg:h-[calc(100vh-4rem)] min-h-[calc(100vh-4rem)]">
    <ImportStepper :phase="store.phase" />

    <div v-if="store.isLoading" class="flex-1 flex items-center justify-center">
      <span class="loading loading-spinner loading-lg text-indigo-600" />
    </div>

    <!-- 1. Import -->
    <div v-else-if="store.phase === 'import'" class="flex-1 overflow-y-auto p-6">
      <div class="max-w-4xl mx-auto">
        <div class="mb-6">
          <h1 class="text-3xl font-bold text-base-content mb-2">
            Importer une carte
            <span v-if="isDevTest" class="ml-2 text-sm font-normal text-base-content/60">
              test: {{ mapId }}
            </span>
          </h1>
          <p class="text-base-content/70">
            {{
              isDevTest
                ? "Utiliser la carte associée au test actuel"
                : "Glissez votre image de carte ou cliquez pour la sélectionner"
            }}
          </p>
        </div>
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body">
            <FileDropZone
              v-if="!store.file"
              :is-loading="store.isSaving"
              @file-selected="store.setFile"
            />
            <div v-else class="space-y-6">
              <ImportPreview :image-file="store.file" :image-url="store.previewUrl" />
              <ImportControls
                :is-processing="store.isSaving"
                start-label="Confirmer carte"
                @start-import="confirmMap"
                @cancel="store.setFile(null)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 2. Saisie utilisateur -->
    <div
      v-else-if="store.phase === 'saisie'"
      class="flex-1 min-h-0 flex flex-col lg:flex-row gap-5 px-7 py-5"
    >
      <div class="lg:flex-[1.4] min-w-0 min-h-[26rem]">
        <ImportMapCard
          :image-url="store.previewUrl"
          :title="store.mapTitle"
          :legend="store.inputs.legend"
          :sift-points="siftPts"
          :city-points="cityPts"
          :colors="store.inputs.colors ?? []"
          can-change-map
          @change-map="askChangeMap"
        />
      </div>
      <div class="lg:w-[370px] shrink-0 lg:overflow-y-auto pr-0.5 pb-2">
        <ExtractionChecklist
          :inputs="store.inputs"
          :options="isDevTest ? null : options"
          :ocr-state="store.ocrState"
          :disabled="store.isSaving || isStarting"
          @open="openStep"
          @update:options="(value) => save({ options: value })"
          @start="startExtraction"
        />
      </div>
    </div>

    <!-- 3. Extraction -->
    <div v-else class="flex-1 overflow-y-auto p-10">
      <ExtractionPanel
        :state="panel.state"
        :progress="panel.progress"
        :status="panel.status"
        :error="panel.error"
        @cancel="cancelExtraction"
        @back="store.phase = 'saisie'"
      />
    </div>

    <!-- Step modals -->
    <WorldAreaPickerModal
      v-if="openModal === 'zone' && store.previewUrl"
      :is-open="true"
      :image-url="store.previewUrl"
      :initial-bounds="store.inputs.frameBounds ?? null"
      :initial-zoom="worldAreaZoom ?? 2"
      @close="openModal = null"
      @confirmed="onZoneConfirmed"
    />

    <LegendAreaPickerModal
      v-if="openModal === 'legend' && store.previewUrl"
      :is-open="true"
      :image-url="store.previewUrl"
      :initial-bounds="store.inputs.legend?.present ? store.inputs.legend.bounds : null"
      @close="openModal = null"
      @no-legend="save({ legend: { present: false, bounds: null } })"
      @confirmed="(bounds) => save({ legend: { present: true, bounds } })"
    />

    <GeoRefSiftModal
      v-if="
        openModal === 'sift' && store.previewUrl && store.inputs.frameBounds && store.keypoints
      "
      :is-open="true"
      :image-url="store.previewUrl"
      :world-bounds="store.inputs.frameBounds"
      :keypoints="store.keypoints"
      :used-lakes="store.usedLakes"
      :initial-points="siftPts"
      @close="openModal = null"
      @confirmed="(points) => save({ controlPoints: [...points, ...cityPts] })"
    />

    <GeoRefCitiesModal
      v-if="openModal === 'cities' && store.previewUrl && store.inputs.frameBounds"
      :is-open="true"
      :image-url="store.previewUrl"
      :world-bounds="store.inputs.frameBounds"
      :sift-points="siftPts"
      :initial-cities="cityPts"
      :used-lakes="store.usedLakes"
      @close="openModal = null"
      @confirmed="(cities) => save({ controlPoints: [...siftPts, ...cities] })"
    />

    <ColorPickerModal
      v-if="openModal === 'colors' && store.previewUrl && store.file"
      :is-open="true"
      :image-url="store.previewUrl"
      :image-file="store.file"
      :initial-colors="store.inputs.colors ?? []"
      @close="openModal = null"
      @confirmed="(colors) => save({ colors })"
    />

    <ConfirmDialog
      v-if="pendingConfirm"
      :title="pendingConfirm.title"
      :message="pendingConfirm.message"
      :confirm-label="pendingConfirm.confirmLabel"
      @confirm="onConfirmAccepted"
      @cancel="pendingConfirm = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useImportSessionStore, type ImportMode } from "../../stores/importSession";
import { useDevTestImportProcess } from "../../composables/useDevTestImportProcess";
import { usePolling } from "../../composables/usePolling";
import { showAlert } from "../../composables/useAlert";
import { slugifyTestCase } from "../../utils/devTestSlug";
import { cityPoints, siftPoints, zoneRedoResetsPoints } from "../../utils/importSteps";
import type { WorldAreaSelection } from "../../typescript/georef";
import type {
  ExtractionState,
  ImportInputsPatch,
  ImportOptions,
  StepId,
} from "../../typescript/importSession";

import ConfirmDialog from "../../components/ConfirmDialog.vue";
import FileDropZone from "../../components/import/FileDropZone.vue";
import ImportPreview from "../../components/import/ImportPreview.vue";
import ImportControls from "../../components/import/ImportControls.vue";
import ImportStepper from "../../components/import/ImportStepper.vue";
import ImportMapCard from "../../components/import/ImportMapCard.vue";
import ExtractionChecklist from "../../components/import/ExtractionChecklist.vue";
import ExtractionPanel from "../../components/import/ExtractionPanel.vue";
import WorldAreaPickerModal from "../../components/import/WorldAreaPickerModal.vue";
import LegendAreaPickerModal from "../../components/legend/LegendAreaPickerModal.vue";
import GeoRefSiftModal from "../../components/georef/GeoRefSiftModal.vue";
import GeoRefCitiesModal from "../../components/georef/GeoRefCitiesModal.vue";
import ColorPickerModal from "../../components/import/ColorPickerModal.vue";

const route = useRoute();
const router = useRouter();

const mode = (route.meta.importMode as ImportMode | undefined) ?? "user";
const isDevTest = mode === "dev-test";
const mapId = String(route.params.mapId);

const store = useImportSessionStore();
store.reset(mode, mapId);

const devImport = useDevTestImportProcess();

const openModal = ref<StepId | null>(null);
const worldAreaZoom = ref<number | null>(null);
const isStarting = ref(false);

interface PendingConfirm {
  title: string;
  message: string;
  confirmLabel: string;
  action: () => void | Promise<void>;
}
const pendingConfirm = ref<PendingConfirm | null>(null);

const siftPts = computed(() => siftPoints(store.inputs));
const cityPts = computed(() => cityPoints(store.inputs));
const options = computed<ImportOptions>(
  () => store.inputs.options ?? { textExtraction: false, shapesExtraction: false },
);

// --- 1. Import --------------------------------------------------------------

async function confirmMap() {
  if (!(await store.confirmMap())) {
    showAlert("error", store.error ?? "Erreur lors de l'envoi de la carte");
  }
}

function askChangeMap() {
  pendingConfirm.value = {
    title: "Changer de carte ?",
    message:
      "La carte importée et toutes les étapes déjà complétées seront abandonnées.",
    confirmLabel: "Changer de carte",
    action: async () => {
      if (!(await store.abandon())) {
        showAlert("error", store.error ?? "Impossible d'abandonner l'import");
      }
    },
  };
}

async function onConfirmAccepted() {
  const action = pendingConfirm.value?.action;
  pendingConfirm.value = null;
  await action?.();
}

// --- 2. Saisie utilisateur ---------------------------------------------------

async function openStep(step: StepId) {
  if (step === "zone" && zoneRedoResetsPoints(store.inputs)) {
    pendingConfirm.value = {
      title: "Redéfinir la zone sur le monde ?",
      message:
        "Les points SIFT et les villes déjà placés correspondent à la zone actuelle : ils seront réinitialisés.",
      confirmLabel: "Redéfinir la zone",
      action: () => {
        openModal.value = "zone";
      },
    };
    return;
  }
  // The keypoints are fetched again after a reload; retry if that failed.
  if (step === "sift" && !store.keypoints && store.inputs.frameBounds) {
    if (!(await store.loadKeypoints(store.inputs.frameBounds))) {
      showAlert("error", store.error ?? "Impossible de trouver des points SIFT");
      return;
    }
  }
  openModal.value = step;
}

async function save(patch: ImportInputsPatch) {
  openModal.value = null;
  if (!(await store.saveInputs(patch))) {
    showAlert("error", store.error ?? "Erreur lors de l'enregistrement");
  }
}

async function onZoneConfirmed(selection: WorldAreaSelection) {
  openModal.value = null;
  worldAreaZoom.value = selection.zoom;
  if (!(await store.confirmZone(selection.bounds))) {
    showAlert("error", store.error ?? "Impossible d'enregistrer la zone");
  }
}

async function startExtraction() {
  isStarting.value = true;
  try {
    if (isDevTest) await startDevTestExtraction();
    else if (!(await store.startExtraction())) {
      showAlert("error", store.error ?? "Erreur lors du lancement de l'extraction");
    }
  } finally {
    isStarting.value = false;
  }
}

// --- 3. Extraction -----------------------------------------------------------

const devTestCaseName = ref<string | null>(null);

async function startDevTestExtraction() {
  if (!store.file) return;
  if (!devTestCaseName.value) {
    const entered = window.prompt(
      `Nom du test-case pour le test ${mapId} (ex: '5 sift points')`,
      "",
    );
    const trimmed = (entered ?? "").trim();
    if (!trimmed) return;
    devTestCaseName.value = trimmed;
  }
  const result = await devImport.startImport(store.file, mapId, devTestCaseName.value, {
    controlPoints: store.inputs.controlPoints ?? [],
    colors: store.inputs.colors ?? [],
    frameBounds: store.inputs.frameBounds ?? null,
    legend: store.inputs.legend ?? null,
  });
  if (result.success) store.phase = "extraction";
  else showAlert("error", result.error);
}

// Dev-test runs are watched by their Celery task; imports by their row.
const panel = computed<{
  state: ExtractionState;
  progress: number;
  status: string;
  error: string | null;
}>(() => {
  if (isDevTest) {
    return {
      state: devImport.error.value ? "failed" : "running",
      progress: devImport.progress.value,
      status: devImport.status.value,
      error: devImport.error.value,
    };
  }
  return {
    state: store.extraction.state,
    progress: store.extraction.progress,
    status: store.extraction.status,
    error: store.extraction.error,
  };
});

async function cancelExtraction() {
  if (isDevTest) {
    devImport.cancelImport();
    store.phase = "saisie";
    return;
  }
  await store.cancelExtraction();
}

// Polled while OCR runs in the background or an extraction is on its way.
const poller = usePolling(() => store.refresh(), 1500);

watch(
  () => [store.phase, store.ocrState] as const,
  ([phase, ocrState]) => {
    const ocrRunning = ocrState === "pending" || ocrState === "running";
    const watching =
      !isDevTest && (phase === "extraction" || (phase === "saisie" && ocrRunning));
    if (watching) poller.start();
    else poller.stop();
  },
  { immediate: true },
);

watch(
  () => store.extraction.state,
  (state) => {
    if (store.phase !== "extraction" || state !== "cancelled") return;
    store.phase = "saisie";
    showAlert("success", "Extraction annulée. Rien n'a été enregistré.");
  },
);

watch(
  () => store.completed,
  async (completed) => {
    if (!completed) return;
    poller.stop();
    await router.push(store.projectId ? `/projet/${store.projectId}` : "/tableau-de-bord");
  },
);

watch(devImport.resultData, (result) => {
  if (!result) return;
  const id = devImport.mapId.value || mapId;
  const caseName = devTestCaseName.value;
  // The slug, not the typed name: the case is stored under it, and its static
  // artifacts are served off that directory.
  router.push({
    path: caseName
      ? `/test-editor/${id}/case/${encodeURIComponent(slugifyTestCase(caseName))}`
      : `/test-editor/${id}`,
  });
});

onMounted(async () => {
  await store.restore();
  if (store.error) showAlert("error", store.error);
  // The first case on a new test map should not wait ~135 s for OCR.
  if (isDevTest) void devImport.warmTextRegions(mapId);
});
</script>
