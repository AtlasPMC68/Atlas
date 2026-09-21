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
          <!-- Re-run this case from its saved inputs. The switches apply to
               this run only; the worker's own settings are left alone. -->
          <div class="bg-base-100 rounded-box border border-base-300 p-3 space-y-3">
            <div class="flex items-center justify-between">
              <h2 class="text-sm font-semibold">Relancer</h2>
              <button
                type="button"
                class="btn btn-primary btn-sm"
                :disabled="isRerunning || !canRerun"
                :title="canRerun ? '' : rerunBlockedReason"
                @click="rerunCase"
              >
                <span
                  v-if="isRerunning"
                  class="loading loading-spinner loading-xs mr-1"
                />
                {{ isRerunning ? "En cours…" : "Relancer" }}
              </button>
            </div>

            <label class="flex items-start gap-2 cursor-pointer">
              <input
                v-model="runSnap"
                type="checkbox"
                class="checkbox checkbox-sm mt-0.5"
                :disabled="isRerunning"
              />
              <span class="text-xs">
                Snapping côtier
                <span class="block text-base-content/60">
                  À laisser <strong>désactivé</strong> pour juger le
                  géoréférencement : le snapping corrige l'erreur de transformation
                  après coup, ce qui flatte la référence et masque l'amélioration
                  que vous cherchez à voir.
                </span>
              </span>
            </label>

            <label class="flex items-start gap-2 cursor-pointer">
              <input
                v-model="runAlign"
                type="checkbox"
                class="checkbox checkbox-sm mt-0.5"
                :disabled="isRerunning"
              />
              <span class="text-xs">
                Alignement (étape 4)
                <span class="block text-base-content/60">
                  Chamfer + ICP. Lance l'OCR au premier passage sur cette carte
                  (~135 s), puis réutilise le cache.
                </span>
              </span>
            </label>

            <p v-if="isScored" class="text-xs text-warning">
              Ce cas est noté : relancer réécrit <code>report.json</code>. Un run
              avec des réglages non standard n'est jamais promu en «&nbsp;best&nbsp;».
            </p>

            <p v-if="rerunError" class="text-xs text-error">{{ rerunError }}</p>
            <p v-else-if="rerunNote" class="text-xs text-success">{{ rerunNote }}</p>
          </div>

          <!-- What this case is for, and whether its stored inputs still cover
               what the current algorithm needs. Shown above the metrics because
               it changes how the metrics should be read. -->
          <div
            v-if="caseState"
            class="bg-base-100 rounded-box border border-base-300 p-3 space-y-2"
          >
            <div class="flex items-center justify-between">
              <h2 class="text-sm font-semibold">Cas de test</h2>
              <div
                class="badge badge-sm"
                :class="isProbe ? 'badge-info' : 'badge-neutral'"
              >
                {{ isProbe ? "Exploration" : "Régression" }}
              </div>
            </div>

            <p v-if="isProbe" class="text-xs text-base-content/70">
              Aucune zone attendue : ce cas sert à rejouer la carte rapidement.
              Les zones extraites sont affichées telles quelles, sans score.
            </p>

            <div v-if="requirementGaps.length > 0" class="space-y-1 pt-1">
              <p class="text-xs font-semibold text-base-content/70">
                Entrées manquantes pour l'algorithme actuel
              </p>
              <div
                v-for="gap in requirementGaps"
                :key="gap.key"
                class="text-xs flex items-start gap-2"
              >
                <span class="badge badge-xs mt-0.5" :class="requirementBadgeClass(gap.status)">
                  {{ gap.status }}
                </span>
                <span class="min-w-0">
                  <span class="font-mono">{{ gap.key }}</span>
                  <span class="text-base-content/60"> (étape {{ gap.sinceStep }})</span>
                  <span class="block text-base-content/70">{{ gap.detail || gap.remedy }}</span>
                </span>
              </div>
            </div>

            <!-- Only a human can supply these, so the case has to be recreated:
                 no amount of re-running recovers a click that never happened. -->
            <div
              v-if="blockedRequirements.length > 0"
              class="alert alert-error text-xs py-2"
            >
              Ce cas ne peut plus être rejoué tel quel : recréez-le pour fournir
              {{ blockedRequirements.map((r) => r.key).join(", ") }}.
            </div>
          </div>

          <div v-if="isScored" class="bg-base-100 rounded-box border border-base-300 p-3">
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
                <span class="font-mono">{{ fmtRatio(primaryBestMatch?.falseNegativeArea) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">{{ expected0Label }} FP area</span>
                <span class="font-mono">{{ fmtRatio(primaryBestMatch?.falsePositiveArea) }}</span>
              </div>

              <div class="divider my-1"></div>

              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Mean IoU</span>
                <span class="font-mono">{{ fmtRatio(expectedBestSummary?.meanIou) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Mean precision</span>
                <span class="font-mono">{{ fmtRatio(expectedBestSummary?.meanPrecision) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Mean recall</span>
                <span class="font-mono">{{ fmtRatio(expectedBestSummary?.meanRecall) }}</span>
              </div>

              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Total FN area</span>
                <span class="font-mono">{{ fmtRatio(expectedBestSummary?.totalFalseNegativeArea) }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-base-content/70">Total FP area</span>
                <span class="font-mono">{{ fmtRatio(expectedBestSummary?.totalFalsePositiveArea) }}</span>
              </div>

              <!-- Zones are paired strictly by name (pipette name vs drawn zone
                   name); anything unpaired scores 0, so make the cause visible. -->
              <div
                v-if="nameMatchWarnings.length > 0"
                class="alert alert-warning text-xs mt-2 flex flex-col items-start gap-1 py-2"
              >
                <span
                  v-for="(warning, i) in nameMatchWarnings"
                  :key="`name-warning-${i}`"
                >
                  {{ warning }}
                </span>
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

          <!-- An unscored case still has an output worth stating plainly. -->
          <div v-else class="bg-base-100 rounded-box border border-base-300 p-3">
            <h2 class="text-sm font-semibold">Extraction</h2>
            <div v-if="isLoading" class="text-sm text-base-content/60 mt-2">
              Chargement…
            </div>
            <div v-else-if="loadError" class="text-sm text-error mt-2">
              {{ loadError }}
            </div>
            <div v-else class="mt-2 text-sm flex items-center justify-between">
              <span class="text-base-content/70">Zones extraites</span>
              <span class="font-mono">{{ extractedFeatures.length }}</span>
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
import MapTestGeoJSON from "../../components/dev/MapTestGeoJSON.vue";
import keycloak from "../../keycloak";
import { zoneFillColor } from "../../typescript/zoneColors";

type RequirementState = {
  key: string;
  kind: "user_input" | "derived";
  level: "required" | "optional";
  sinceStep: string;
  summary: string;
  remedy: string;
  status:
    | "satisfied"
    | "stale"
    | "refreshable"
    | "blocked"
    | "absent";
  detail: string | null;
};

type CaseState = {
  kind?: "regression" | "probe";
  scored?: boolean | null;
  hasExpectedZones?: boolean;
  requirements?: {
    version?: string;
    runnable?: boolean;
    blocked?: string[];
    refreshable?: string[];
    requirements?: RequirementState[];
  } | null;
};

type DevTestReport = {
  testId?: string;
  testCaseId?: string;
  pass?: boolean;
  metrics?: any;
  nameMatching?: {
    expectedWithoutNameMatch?: (string | null)[];
    extractedNeverMatchedByName?: string[];
  };
};

const route = useRoute();
const router = useRouter();

const testId = ref<string>("");
const testCaseId = ref<string>("");

const expectedFeatures = ref<any[]>([]);
const extractedFeatures = ref<any[]>([]);
const errorFeatures = ref<any[]>([]);

const latestReport = ref<DevTestReport | null>(null);
const bestReport = ref<DevTestReport | null>(null);
const caseState = ref<CaseState | null>(null);

// Snapping defaults OFF: the docs say to judge alignment with it off, and a
// re-run button exists to judge alignment. Alignment defaults ON because
// seeing what the current pipeline does is the point of re-running at all.
const runSnap = ref(false);
const runAlign = ref(true);
const isRerunning = ref(false);
const rerunError = ref<string | null>(null);
const rerunNote = ref<string | null>(null);
const isLoading = ref(false);
const loadError = ref<string | null>(null);

const mode = ref<"latest" | "best">("latest");
let suppressModeWatch = false;

// Static files under /dev-test can be aggressively cached by the browser.
// Bump this on each reload to force-fetch the latest artifacts.
const cacheBuster = ref(0);

const featureVisibility = ref(new Map<string, boolean>());

const isProbe = computed<boolean>(() => caseState.value?.kind === "probe");

// A run only produces a number when there is ground truth to compare it with.
// Fall back to "is there a report" for a case that has never been inspected.
const isScored = computed<boolean>(() => {
  if (caseState.value?.scored != null) return Boolean(caseState.value.scored);
  if (isProbe.value) return false;
  return latestReport.value != null;
});

// Everything the current algorithm wants that this case does not have. A case
// authored before a requirement existed otherwise runs quietly with less
// evidence than the pipeline expects and reports a worse number for a reason
// that has nothing to do with the change being measured.
const requirementGaps = computed<RequirementState[]>(() => {
  const all = caseState.value?.requirements?.requirements ?? [];
  return all.filter((r) => r.status !== "satisfied");
});

const blockedRequirements = computed<RequirementState[]>(() =>
  requirementGaps.value.filter((r) => r.status === "blocked"),
);

function requirementBadgeClass(status: RequirementState["status"]): string {
  if (status === "blocked") return "badge-error";
  if (status === "stale" || status === "refreshable") return "badge-warning";
  return "badge-ghost";
}

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

const primaryBestMatch = computed<any>(() => {
  const m = activeReport.value?.metrics as any;
  const first = Array.isArray(m?.expected) ? (m.expected as any[])[0] : null;
  return first?.bestMatch ?? null;
});

const expected0Label = computed<string>(() => {
  const m = activeReport.value?.metrics as any;
  const first = Array.isArray(m?.expected) ? (m.expected as any[])[0] : null;
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
  return primaryBestMatch.value?.iou;
});

const nameMatchWarnings = computed<string[]>(() => {
  const nm = activeReport.value?.nameMatching;
  if (!nm) return [];

  const warnings: string[] = [];

  const unmatchedExpected = (nm.expectedWithoutNameMatch ?? []).filter(
    (n): n is string => typeof n === "string" && n.trim().length > 0,
  );
  if (unmatchedExpected.length > 0) {
    warnings.push(
      `Zones attendues sans couleur extraite du même nom (IoU 0) : ${unmatchedExpected.join(", ")}`,
    );
  }

  const unusedExtracted = nm.extractedNeverMatchedByName ?? [];
  if (unusedExtracted.length > 0) {
    warnings.push(
      `Couleurs extraites qui ne correspondent à aucune zone attendue : ${unusedExtracted.join(", ")}`,
    );
  }

  return warnings;
});

const expectedBestSummary = computed<any>(() => {
  const m = activeReport.value?.metrics as any;
  if (m?.mean) return m.mean;

  const ms = Array.isArray(m?.expected) ? (m.expected as any[]) : [];
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

// A case missing a user input cannot be re-run at all -- no amount of
// re-running recovers a click that never happened.
const canRerun = computed<boolean>(
  () => (caseState.value?.requirements?.runnable ?? true) === true,
);

const rerunBlockedReason = computed<string>(() =>
  blockedRequirements.value.length
    ? `Entrées manquantes : ${blockedRequirements.value
        .map((r) => r.key)
        .join(", ")}. Recréez le cas.`
    : "",
);

async function rerunCase() {
  if (!testId.value || !testCaseId.value || isRerunning.value) return;

  isRerunning.value = true;
  rerunError.value = null;
  rerunNote.value = null;

  const params = new URLSearchParams({
    snap_to_coastline: String(runSnap.value),
    enable_curve_alignment: String(runAlign.value),
  });

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/dev-test-api/test-cases/${testId.value}/${testCaseId.value}/run-evaluate?${params}`,
      { method: "POST", headers: { Authorization: `Bearer ${keycloak.token}` } },
    );

    if (!res.ok) {
      let detail = "";
      try {
        detail = ((await res.json()) as any)?.detail ?? "";
      } catch {
        detail = "";
      }
      throw new Error(
        `Échec de la relance (${res.status})${detail ? `: ${detail}` : ""}`,
      );
    }

    const data = await res.json();
    rerunNote.value =
      data?.kind === "probe"
        ? "Relancé. Zones réextraites, pas de score (cas d'exploration)."
        : "Relancé et réévalué.";

    await reloadAll();
  } catch (err) {
    rerunError.value =
      err instanceof Error ? err.message : "Erreur inattendue lors de la relance";
  } finally {
    isRerunning.value = false;
  }
}

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

function normalizeZoneFeatures(
  raw: any,
  source: "expected" | "extracted",
): any[] {
  const feats = Array.isArray(raw?.features) ? raw.features : [];

  // Important: keep __sourceIndex equal to the original Feature index in the GeoJSON.
  // The backend stores extracted feature indices based on the on-disk FeatureCollection.
  const out: any[] = [];

  feats.forEach((f: any, idx: number) => {
    if (!f || f.type !== "Feature" || !f.geometry) return;

    const id = String(f.id ?? `${source}-${idx}`);
    const name = String(f?.properties?.name ?? `${source}-${idx}`);
    // Extracted zones render in the colour they were sampled from; expected
    // zones are hand-drawn and carry none, so they stay a flat blue and the two
    // layers remain tellable apart.
    const color = zoneFillColor(f.properties, source);
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

function normalizeErrorFeatures(raw: any): any[] {
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
        // Dashed, so the error layer reads as an overlay even on a map whose
        // own zones are red.
        strokeColor: "#7f1d1d",
        dashArray: "6 4",
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
    { headers: { Authorization: `Bearer ${keycloak.token}` } },
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

  // A probe case has no report to filter against, and filtering to nothing
  // would render an empty map — which is the whole output of a probe run.
  // Show everything that was extracted.
  if (!isScored.value) {
    extractedFeatures.value = all;
    return;
  }

  // Only show extracted zones that were actually selected as best matches.
  const usedIdx = new Set<number>();
  const m = activeReport.value?.metrics as any;
  const ms = Array.isArray(m?.expected) ? (m.expected as any[]) : [];
  ms.forEach((entry: any) => {
    const idx = entry?.bestMatch?.extracted?.index;
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
    { headers: { Authorization: `Bearer ${keycloak.token}` } },
  );
  if (!res.ok) {
    latestReport.value = null;
    return;
  }
  latestReport.value = await res.json();
}

async function loadCaseState() {
  if (!testId.value || !testCaseId.value) return;
  const res = await fetch(
    `${import.meta.env.VITE_API_URL}/dev-test-api/test-cases/${testId.value}/${testCaseId.value}/state`,
    { headers: { Authorization: `Bearer ${keycloak.token}` } },
  );
  if (!res.ok) {
    caseState.value = null;
    return;
  }
  caseState.value = await res.json();
}

async function loadBestReport() {
  if (!testId.value || !testCaseId.value) return;
  const res = await fetch(
    `${import.meta.env.VITE_API_URL}/dev-test-api/test-cases/${testId.value}/${testCaseId.value}/best-report`,
    { headers: { Authorization: `Bearer ${keycloak.token}` } },
  );
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
    await Promise.all([loadLatestReport(), loadBestReport(), loadCaseState()]);
    if (mode.value === "best" && !bestReport.value) {
      suppressModeWatch = true;
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

watch(mode, async () => {
  if (suppressModeWatch) {
    suppressModeWatch = false;
    return;
  }
  await reloadAll();
});

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
