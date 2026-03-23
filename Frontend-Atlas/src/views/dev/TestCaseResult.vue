<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex-1 items-center gap-3">
        <button class="btn btn-ghost btn-sm" type="button" @click="goBack">
          Retour
        </button>
        <h1 class="text-xl font-bold">
          Résultat test case
          <span class="ml-2 text-sm font-normal text-base-content/60">
            ({{ testId }} / {{ testCaseId }})
          </span>
        </h1>
      </div>
    </div>

    <div class="flex flex-1 min-h-0">
      <div class="w-96 bg-base-200 border-r border-base-300 p-4 overflow-y-auto">
        <FeatureVisibilityControls
          :features="allFeatures"
          :feature-visibility="featureVisibility"
          :allow-delete="false"
          :allow-rename="false"
          @toggle-feature="toggleFeatureVisibility"
        />
      </div>

      <div class="flex-1 flex min-h-0">
        <div class="flex-1 flex flex-col">
          <div class="flex-1">
            <MapTestGeoJSON
              v-if="testId"
              :key="`${testId}-${testCaseId}-${mode}`"
              :map-id="testId"
              :features="allFeatures"
              :feature-visibility="featureVisibility"
              :is-create-mode="false"
              :reset-create-key="0"
              :is-frontier-mode="false"
              :is-geo-border-mode="false"
              :undo-create-key="0"
              :sub-geometries="[]"
            />
          </div>
        </div>

        <div
          class="w-96 border-l border-base-300 bg-base-200 p-4 space-y-4 overflow-y-auto"
        >
          <div class="bg-base-100 rounded-box border border-base-300 p-3">
            <div class="flex items-center justify-between">
              <h2 class="text-sm font-semibold">Rapport</h2>
              <div class="join">
                <button
                  type="button"
                  class="btn btn-xs join-item"
                  :class="mode === 'latest' ? 'btn-primary' : 'btn-outline'"
                  @click="mode = 'latest'"
                >
                  Latest
                </button>
                <button
                  type="button"
                  class="btn btn-xs join-item"
                  :class="mode === 'best' ? 'btn-primary' : 'btn-outline'"
                  :disabled="!bestReport"
                  :title="bestReport ? '' : 'Aucun meilleur résultat enregistré'"
                  @click="mode = 'best'"
                >
                  Best
                </button>
              </div>
            </div>

            <div v-if="isLoading" class="text-sm text-base-content/60 mt-2">
              Chargement…
            </div>

            <div v-else-if="loadError" class="text-sm text-error mt-2">
              {{ loadError }}
            </div>

            <div v-else class="mt-2 space-y-2 text-sm">
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">{{ expected0Label }} IoU</span>
                <span class="font-mono">{{ fmtRatio(expected0Iou) }}</span>
              </div>

              <div class="flex items-center justify-between">
                <span class="text-base-content/70">{{ expected0Label }} precision</span>
                <span class="font-mono">{{ fmtRatio(primaryBestMatch?.precision) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">{{ expected0Label }} recall</span>
                <span class="font-mono">{{ fmtRatio(primaryBestMatch?.recall) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">{{ expected0Label }} FN area</span>
                <span class="font-mono">{{ fmtNumber(primaryBestMatch?.falseNegativeArea) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">{{ expected0Label }} FP area</span>
                <span class="font-mono">{{ fmtNumber(primaryBestMatch?.falsePositiveArea) }}</span>
              </div>

              <div class="divider my-1"></div>

              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Mean IoU (best-match)</span>
                <span class="font-mono">{{ fmtRatio(expectedBestSummary?.meanIou) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Mean precision (best-match)</span>
                <span class="font-mono">{{ fmtRatio(expectedBestSummary?.meanPrecision) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Mean recall (best-match)</span>
                <span class="font-mono">{{ fmtRatio(expectedBestSummary?.meanRecall) }}</span>
              </div>

              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Total FN area (best-match)</span>
                <span class="font-mono">{{ fmtNumber(expectedBestSummary?.totalFalseNegativeArea) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Total FP area (best-match)</span>
                <span class="font-mono">{{ fmtNumber(expectedBestSummary?.totalFalsePositiveArea) }}</span>
              </div>

              <div v-if="typeof activeReport?.pass === 'boolean'" class="mt-2">
                <div
                  class="badge"
                  :class="activeReport.pass ? 'badge-success' : 'badge-error'"
                >
                  {{ activeReport.pass ? 'PASS' : 'FAIL' }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import FeatureVisibilityControls from "../../components/FeatureVisibilityControls.vue";
import MapTestGeoJSON from "../../components/MapTestGeoJSON.vue";

type AnyFeature = any;

type DevTestReport = {
  testId?: string;
  testCaseId?: string;
  pass?: boolean;
  metrics?: any;
  matches?: any[];
};

const route = useRoute();
const router = useRouter();

const testId = ref<string>("");
const testCaseId = ref<string>("");

const expectedFeatures = ref<AnyFeature[]>([]);
const extractedFeatures = ref<AnyFeature[]>([]);
const errorFeatures = ref<AnyFeature[]>([]);

const latestReport = ref<DevTestReport | null>(null);
const bestReport = ref<DevTestReport | null>(null);
const isLoading = ref(false);
const loadError = ref<string | null>(null);

const mode = ref<"latest" | "best">("latest");

// Static files under /dev-test can be aggressively cached by the browser.
// Bump this on each reload to force-fetch the latest artifacts.
const cacheBuster = ref<number>(Date.now());

const featureVisibility = ref(new Map<string, boolean>());

const activeReport = computed<DevTestReport | null>(() => {
  if (mode.value === "best" && bestReport.value) return bestReport.value;
  return latestReport.value;
});

const extractedUrl = computed(() => {
  if (!testId.value || !testCaseId.value) return "";
  const filename = mode.value === "best" ? "zones_best.geojson" : "zones.geojson";
  return `${import.meta.env.VITE_API_URL}/dev-test/test_cases/${testId.value}/${testCaseId.value}/${filename}?v=${cacheBuster.value}`;
});

const errorsUrl = computed(() => {
  if (!testId.value || !testCaseId.value) return "";
  const filename = mode.value === "best" ? "errors_best.geojson" : "errors.geojson";
  return `${import.meta.env.VITE_API_URL}/dev-test/test_cases/${testId.value}/${testCaseId.value}/${filename}?v=${cacheBuster.value}`;
});

const allFeatures = computed(() => {
  return [...expectedFeatures.value, ...extractedFeatures.value, ...errorFeatures.value];
});

const metrics = computed(() => activeReport.value?.metrics ?? null);

const primaryBestMatch = computed<any>(() => {
  const m = metrics.value as any;
  if (m?.primaryMatch) return m.primaryMatch;
  const first = Array.isArray(activeReport.value?.matches)
    ? (activeReport.value?.matches as any[])[0]
    : null;
  return first?.bestMatch ?? null;
});

const expected0Label = computed<string>(() => {
  const first = Array.isArray(activeReport.value?.matches)
    ? (activeReport.value?.matches as any[])[0]
    : null;
  const exp = first?.expected;
  const idx = exp?.index;
  const name = exp?.name;
  if (typeof idx === "number" && typeof name === "string" && name.trim()) {
    return `Expected #${idx}: ${name}`;
  }
  if (typeof name === "string" && name.trim()) {
    return `Expected: ${name}`;
  }
  if (typeof idx === "number") {
    return `Expected #${idx}`;
  }
  return "Expected #0";
});

const expected0Iou = computed<any>(() => {
  const m = metrics.value as any;
  if (typeof m?.primaryExpectedBestIou === "number") return m.primaryExpectedBestIou;
  return primaryBestMatch.value?.iou;
});

const expectedBestSummary = computed<any>(() => {
  const m = metrics.value as any;
  if (m?.expectedBest) return m.expectedBest;

  const ms = Array.isArray(activeReport.value?.matches)
    ? (activeReport.value?.matches as any[])
    : [];
  if (!ms.length) {
    return {
      meanIou: 0,
      meanPrecision: 0,
      meanRecall: 0,
      totalFalseNegativeArea: 0,
      totalFalsePositiveArea: 0,
    };
  }

  const vals = ms
    .map((x) => x?.bestMatch)
    .filter((bm) => bm && typeof bm === "object");

  const nums = (arr: any[], key: string) =>
    arr
      .map((o) => Number(o?.[key]))
      .filter((n) => Number.isFinite(n));

  const ious = nums(vals, "iou");
  const precisions = nums(vals, "precision");
  const recalls = nums(vals, "recall");
  const fns = nums(vals, "falseNegativeArea");
  const fps = nums(vals, "falsePositiveArea");

  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

  return {
    meanIou: mean(ious),
    meanPrecision: mean(precisions),
    meanRecall: mean(recalls),
    totalFalseNegativeArea: sum(fns),
    totalFalsePositiveArea: sum(fps),
  };
});

function goBack() {
  if (testId.value) {
    router.push({ path: `/test-editor/${testId.value}` });
    return;
  }
  router.back();
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  featureVisibility.value.set(featureId, visible);
  featureVisibility.value = new Map(featureVisibility.value);
}

function fmtRatio(val: any): string {
  const n = typeof val === "number" ? val : Number(val);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(3);
}

function fmtNumber(val: any): string {
  const n = typeof val === "number" ? val : Number(val);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(3);
}

function normalizeZoneFeatures(
  raw: any,
  source: "expected" | "extracted",
): AnyFeature[] {
  const feats = Array.isArray(raw?.features) ? raw.features : [];
  const color = source === "expected" ? "blue" : "green";

  // Important: keep __sourceIndex equal to the original Feature index in the GeoJSON.
  // The backend stores extracted feature indices based on the on-disk FeatureCollection.
  const out: AnyFeature[] = [];

  feats.forEach((f: any, idx: number) => {
    if (!f || f.type !== "Feature" || !f.geometry) return;

    const id = String(f.id ?? `${source}-${idx}`);
    const name = String(f?.properties?.name ?? `${source}-${idx}`);
    out.push({
      ...f,
      id,
      __sourceIndex: idx,
      color,
      properties: {
        ...(f.properties || {}),
        name: source === "expected" ? `Expected: ${name}` : `Extracted: ${name}`,
        mapElementType: "zone",
      },
    });
  });

  return out;
}

function normalizeErrorFeatures(raw: any): AnyFeature[] {
  const feats = Array.isArray(raw?.features) ? raw.features : [];

  return feats
    .filter((f: any) => f && f.type === "Feature" && f.geometry)
    .map((f: any, idx: number) => {
      const kind = String(f?.properties?.kind ?? "error");
      const label =
        kind === "false_negative"
          ? "False negative (missing)"
          : kind === "false_positive"
            ? "False positive (extra)"
            : kind;

      const id = String(f.id ?? `error-${kind}-${idx}`);
      const baseName = String(f?.properties?.name ?? "error");
      return {
        ...f,
        id,
        color: "red",
        properties: {
          ...(f.properties || {}),
          name: `${baseName} (${label})`,
          mapElementType: "zone",
        },
      };
    });
}

async function loadExpected() {
  if (!testId.value) return;

  const res = await fetch(
    `${import.meta.env.VITE_API_URL}/dev-test-api/georef_zones/${testId.value}`,
  );

  if (!res.ok) {
    if (res.status === 404) {
      expectedFeatures.value = [];
      return;
    }
    throw new Error(`Failed to fetch expected zones (${res.status})`);
  }

  const data = await res.json();
  expectedFeatures.value = normalizeZoneFeatures(data, "expected");
}

async function loadExtracted() {
  if (!extractedUrl.value) return;
  const res = await fetch(extractedUrl.value);
  if (!res.ok) {
    extractedFeatures.value = [];
    return;
  }
  const data = await res.json();

  const all = normalizeZoneFeatures(data, "extracted");

  // Only show extracted zones that were actually selected as best matches.
  const usedIdx = new Set<number>();
  const ms = Array.isArray(activeReport.value?.matches)
    ? activeReport.value?.matches
    : [];
  ms.forEach((m: any) => {
    const idx = m?.bestMatch?.extracted?.index;
    if (typeof idx === "number" && Number.isFinite(idx)) usedIdx.add(idx);
  });

  extractedFeatures.value =
    usedIdx.size === 0
      ? []
      : all.filter((f: any) => usedIdx.has(Number(f.__sourceIndex)));
}

async function loadErrors() {
  if (!errorsUrl.value) return;
  const res = await fetch(errorsUrl.value);
  if (!res.ok) {
    errorFeatures.value = [];
    return;
  }
  const data = await res.json();
  errorFeatures.value = normalizeErrorFeatures(data);
}

async function loadLatestReport() {
  if (!testId.value || !testCaseId.value) return;
  const res = await fetch(
    `${import.meta.env.VITE_API_URL}/dev-test-api/test-cases/${testId.value}/${testCaseId.value}/report`,
  );
  if (!res.ok) {
    latestReport.value = null;
    return;
  }
  latestReport.value = await res.json();
}

async function loadBestReport() {
  if (!testId.value || !testCaseId.value) return;
  const url = `${import.meta.env.VITE_API_URL}/dev-test/test_cases/${testId.value}/${testCaseId.value}/best_report.json?v=${cacheBuster.value}`;
  const res = await fetch(url);
  if (!res.ok) {
    bestReport.value = null;
    return;
  }
  bestReport.value = await res.json();
}

function rebuildVisibility() {
  const vis = new Map<string, boolean>();
  allFeatures.value.forEach((f: any) => {
    if (f?.id) vis.set(String(f.id), true);
  });
  featureVisibility.value = vis;
}

async function reloadAll() {
  isLoading.value = true;
  loadError.value = null;
  cacheBuster.value = Date.now();
  try {
    // Load report first (extracted filtering depends on it).
    await Promise.all([loadLatestReport(), loadBestReport()]);
    if (mode.value === "best" && !bestReport.value) {
      mode.value = "latest";
    }
    await Promise.all([loadExpected(), loadExtracted(), loadErrors()]);
    rebuildVisibility();
  } catch (e: any) {
    loadError.value = e?.message ? String(e.message) : "Erreur lors du chargement";
  } finally {
    isLoading.value = false;
  }
}

function readParams() {
  const t = route.params.mapId;
  const c = route.params.caseId;
  testId.value = typeof t === "string" ? t : "";
  testCaseId.value = typeof c === "string" ? c : "";
}

watch(
  () => mode.value,
  async () => {
    await reloadAll();
  },
);

watch(
  () => route.fullPath,
  async () => {
    readParams();
    await reloadAll();
  },
);

onMounted(async () => {
  readParams();
  await reloadAll();
});
</script>
