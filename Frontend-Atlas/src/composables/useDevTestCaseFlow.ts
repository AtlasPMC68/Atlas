// The dev-test side of the import page: a case's check points, starting from
// another case, and running the case instead of a production import. The page
// stays the production import; this is what dev-test mode adds to it.
import { computed, watch } from "vue";
import { useRouter } from "vue-router";
import { useImportSessionStore } from "../stores/importSession";
import { useDevTestImportProcess } from "./useDevTestImportProcess";
import { slugifyTestCase } from "../utils/devTestSlug";
import { checkPoints, type CasePart } from "../utils/importSteps";
import type { ControlPointInput } from "../typescript/georef";
import type { DevTestCaseInputsResponse } from "../typescript/devTest";
import type { ExtractionState, ImportInputsPatch } from "../typescript/importSession";

export function useDevTestCaseFlow(mapId: string) {
  const store = useImportSessionStore();
  const router = useRouter();
  const devImport = useDevTestImportProcess();
  let caseName: string | null = null;

  // Check points come from two steps: SIFT pairs ticked at the SIFT step, and
  // cities from "Villes de vérification". Each step edits its own share.
  const checkPts = computed(() => checkPoints(store.inputs));
  const siftCheckPts = computed(() => checkPts.value.filter((p) => p.source === "sift"));
  const cityCheckPts = computed(() => checkPts.value.filter((p) => p.source === "city"));

  function siftChecksPatch(checks: ControlPointInput[]): ImportInputsPatch {
    return { checkPoints: [...checks, ...cityCheckPts.value] };
  }

  function cityChecksPatch(cities: ControlPointInput[]): ImportInputsPatch {
    return { checkPoints: [...siftCheckPts.value, ...cities] };
  }

  async function startFromCase(
    source: DevTestCaseInputsResponse,
    parts: CasePart[],
  ): Promise<string | null> {
    if (await store.startFromDevTestCase(source, parts)) return null;
    return store.error ?? "Impossible de reprendre ce cas";
  }

  // Saves the case's inputs and runs it. An edited case is saved under its own
  // name, which slugifies to its id, so the run overwrites that case. Returns
  // an error message, or null (also when the name prompt was cancelled).
  async function startExtraction(): Promise<string | null> {
    const edited = store.editedCase;
    if (edited && !caseName) {
      caseName = slugifyTestCase(edited.name) === edited.id ? edited.name : edited.id;
    }
    if (!caseName) {
      const entered = window.prompt(
        `Nom du test-case pour le test ${mapId} (ex: '5 sift points')`,
        "",
      );
      caseName = (entered ?? "").trim() || null;
      if (!caseName) return null;
    }
    const result = await devImport.startImport(mapId, caseName, {
      controlPoints: store.inputs.controlPoints ?? [],
      checkPoints: store.inputs.checkPoints ?? [],
      colors: store.inputs.colors ?? [],
      frameBounds: store.inputs.frameBounds ?? null,
      legend: store.inputs.legend ?? null,
      kind: edited?.kind ?? null,
    });
    if (!result.success) return result.error;
    store.phase = "extraction";
    return null;
  }

  // A dev-test run is watched through its Celery task, not an import row.
  const panel = computed<{
    state: ExtractionState;
    progress: number;
    status: string;
    error: string | null;
  }>(() => ({
    state: devImport.error.value ? "failed" : "running",
    progress: devImport.progress.value,
    status: devImport.status.value,
    error: devImport.error.value,
  }));

  function cancelExtraction(): void {
    devImport.cancelImport();
    store.phase = "saisie";
  }

  // The case's result page once the run is done. The slug, not the typed
  // name: the case is stored, and its files served, under it.
  watch(devImport.resultData, (result) => {
    if (!result) return;
    router.push(
      caseName
        ? `/test-editor/${mapId}/case/${encodeURIComponent(slugifyTestCase(caseName))}`
        : `/test-editor/${mapId}`,
    );
  });

  function caseResultPath(caseId: string): string {
    return `/test-editor/${mapId}/case/${encodeURIComponent(caseId)}`;
  }

  return {
    checkPts,
    siftCheckPts,
    cityCheckPts,
    siftChecksPatch,
    cityChecksPatch,
    startFromCase,
    startExtraction,
    panel,
    cancelExtraction,
    caseResultPath,
    warmTextRegions: () => devImport.warmTextRegions(mapId),
  };
}
