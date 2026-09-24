// composables/useDevTestImportProcess.ts
import { ref, type Ref } from "vue";
import { snakeToCamel } from "../utils/utils";
import { apiFetch } from "../utils/api";
import { usePolling } from "./usePolling";
import type {
  ControlPointInput,
  ImposedColor,
  WorldBounds,
} from "../typescript/georef";
import type { LegendAnswer } from "../typescript/legend";

type StartDevTestImportResult =
  | { success: true }
  | { success: false; error: string };

interface UploadResponse {
  taskId: string;
  mapId: string;
}

interface StatusResponse {
  progress_percentage?: number;
  status?: string;
  state?: "PENDING" | "STARTED" | "PROGRESS" | "SUCCESS" | "FAILURE" | string;
  result?: unknown;
  error?: string;
}

export interface DevTestImportInputs {
  controlPoints: ControlPointInput[];
  colors: ImposedColor[];
  frameBounds: WorldBounds | null;
  legend: LegendAnswer | null;
}

// A dev-test run writes files, never the database, and cannot be stopped on
// the backend: "Annuler" stops watching it, and the run's files are simply
// overwritten by the next one.
export function useDevTestImportProcess() {
  const isProcessing: Ref<boolean> = ref(false);
  const progress: Ref<number> = ref(0);
  const status: Ref<string> = ref("");
  const error: Ref<string | null> = ref(null);
  const resultData: Ref<unknown | null> = ref(null);
  const mapId: Ref<string> = ref("");
  let taskId: string | null = null;

  const poller = usePolling(async () => {
    if (!taskId) return;
    try {
      const res = await apiFetch(`/projects/status/${taskId}`);
      const data: StatusResponse = await res.json();

      progress.value = data.progress_percentage || 0;
      status.value = data.status || "";

      if (data.state === "SUCCESS") {
        poller.stop();
        isProcessing.value = false;
        resultData.value = data.result;
      } else if (data.state === "FAILURE" || data.state === "REVOKED") {
        poller.stop();
        isProcessing.value = false;
        error.value = data.error || "Le traitement a échoué";
      }
    } catch (err) {
      poller.stop();
      isProcessing.value = false;
      error.value = err instanceof Error ? err.message : "Erreur lors du suivi";
    }
  }, 1000);

  const startImport = async (
    file: File,
    testId: string,
    testCase: string,
    inputs: DevTestImportInputs,
  ): Promise<StartDevTestImportResult> => {
    if (!file) return { success: false, error: "Aucun fichier sélectionné" };
    if (!testId) return { success: false, error: "Identifiant de test manquant" };
    if (!testCase) return { success: false, error: "Nom du cas de test manquant" };

    isProcessing.value = true;
    progress.value = 0;
    status.value = "";
    error.value = null;
    resultData.value = null;

    const formData = new FormData();
    formData.append("test_id", testId);
    formData.append("test_case", testCase);

    // SIFT and city control points, stored in the case config with their source
    if (inputs.controlPoints.length) {
      formData.append("control_points", JSON.stringify(inputs.controlPoints));
    }
    // The framing box is persisted into the case config, so a case re-runs with
    // the same working extent.
    if (inputs.frameBounds) {
      formData.append("frame_bounds", JSON.stringify(inputs.frameBounds));
    }
    // A rectangle or an explicit "no legend": both are answers the case keeps.
    if (inputs.legend) {
      formData.append("legend", JSON.stringify(inputs.legend));
    }
    // Pipette selections: without them the backend extracts no color zones at all.
    if (inputs.colors.length) {
      formData.append(
        "imposed_colors",
        JSON.stringify(
          inputs.colors.map((c) => {
            const rawRadius = Number(c.radius);
            const radius = Number.isFinite(rawRadius)
              ? Math.max(1, Math.min(200, Math.round(rawRadius)))
              : 20;
            return { x: c.x, y: c.y, name: c.name, radius, kind: c.kind };
          }),
        ),
      );
    }
    formData.append("file", file);

    try {
      const response = await apiFetch("/dev-test-api/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body: Partial<{ detail: string }> = await response.json();
        throw new Error(body.detail || "Erreur lors de l'envoi du fichier de test");
      }

      const data: UploadResponse = snakeToCamel(await response.json());
      taskId = data.taskId;
      mapId.value = data.mapId;
      if (!taskId) throw new Error("taskId is null");

      poller.start();
      return { success: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Erreur inattendue";
      isProcessing.value = false;
      error.value = message;
      return { success: false, error: message };
    }
  };

  const cancelImport = () => {
    poller.stop();
    taskId = null;
    isProcessing.value = false;
    progress.value = 0;
    status.value = "";
    resultData.value = null;
  };

  // Starts OCR for the test map in the background if it is not cached yet, so
  // the first case's run does not wait for it. Best effort: a failure only
  // means that run pays for OCR itself.
  const warmTextRegions = async (testId: string) => {
    try {
      await apiFetch(`/dev-test-api/tests/${testId}/warm-text-regions`, {
        method: "POST",
      });
    } catch (err) {
      console.warn("[DEV-TEST] Could not warm the text regions:", err);
    }
  };

  return {
    isProcessing,
    progress,
    status,
    error,
    resultData,
    mapId,
    startImport,
    cancelImport,
    warmTextRegions,
  };
}
