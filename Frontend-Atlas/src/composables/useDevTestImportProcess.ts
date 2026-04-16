// composables/useDevTestImportProcess.ts
import { ref, type Ref } from "vue";
import { snakeToCamel } from "../utils/utils";
import { apiFetch } from "../utils/api";
type ImagePoint = { x: number; y: number };
type WorldPoint = { lat: number; lng: number };
type ProcessingStep = "upload" | "analysis" | "extraction" | "processing";
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
  state?: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE" | string;
  result?: unknown;
  error?: string;
}

// Module-level singleton refs — same pattern as useImportProcess
const isProcessing: Ref<boolean> = ref(false);
const processingStep: Ref<ProcessingStep> = ref("upload");
const processingProgress: Ref<number> = ref(0);
const showProcessingModal: Ref<boolean> = ref(false);
const taskId: Ref<string | null> = ref(null);
const resultData: Ref<unknown | null> = ref(null);
const mapId: Ref<string> = ref("");

export function useDevTestImportProcess() {
  const startImport = async (
    file: File,
    testId: string,
    testCase: string,
    imagePoints?: ImagePoint[],
    worldPoints?: WorldPoint[],
  ): Promise<StartDevTestImportResult> => {
    if (!file) return { success: false, error: "Aucun fichier sélectionné" };
    if (!testId) return { success: false, error: "Identifiant de test manquant" };
    if (!testCase) return { success: false, error: "Nom du cas de test manquant" };

    isProcessing.value = true;
    showProcessingModal.value = true;
    processingStep.value = "upload";
    processingProgress.value = 0;

    const formData = new FormData();
    formData.append("test_id", testId);
    formData.append("test_case", testCase);

    if (imagePoints && imagePoints.length) {
      formData.append("image_points", JSON.stringify(imagePoints));
    }
    if (worldPoints && worldPoints.length) {
      formData.append("world_points", JSON.stringify(worldPoints));
    }
    formData.append("file", file);

    try {
      const response = await apiFetch("/dev-test-api/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error: Partial<{ detail: string }> = await response.json();
        throw new Error(
          error.detail || "Erreur lors de l'envoi du fichier de test",
        );
      }

      const data: UploadResponse = snakeToCamel(await response.json());
      taskId.value = data.taskId;
      mapId.value = data.mapId;

      if (!taskId.value) {
        throw new Error("taskId is null");
      }

      pollStatus(taskId.value);
      return { success: true };
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Erreur inattendue";
      isProcessing.value = false;
      showProcessingModal.value = false;
      return { success: false, error: message };
    }
  };

  const mapStatusToStep = (statusText: string): ProcessingStep => {
    if (statusText.includes("Saving uploaded")) return "upload";
    if (statusText.includes("Loading")) return "analysis";
    if (statusText.includes("Extracting")) return "extraction";
    if (
      statusText.includes("Saving test") ||
      statusText.includes("Cleaning")
    )
      return "processing";
    return "upload";
  };

  const pollStatus = (currentTaskId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await apiFetch(`/projects/status/${currentTaskId}`);
        const data: StatusResponse = await res.json();

        processingProgress.value = data.progress_percentage || 0;
        processingStep.value = mapStatusToStep(data.status || "");

        if (data.state === "SUCCESS") {
          clearInterval(interval);
          isProcessing.value = false;
          showProcessingModal.value = false;
          resultData.value = data.result;
        }

        if (data.state === "FAILURE") {
          clearInterval(interval);
          isProcessing.value = false;
          showProcessingModal.value = false;
          console.error("[DEV-TEST] Erreur de traitement:", data.error);
        }
      } catch (err) {
        console.error("[DEV-TEST] Erreur lors du polling:", err);
        clearInterval(interval);
        isProcessing.value = false;
        showProcessingModal.value = false;
      }
    }, 1000);
  };

  const cancelImport = () => {
    isProcessing.value = false;
    showProcessingModal.value = false;
    processingStep.value = "upload";
    processingProgress.value = 0;
    taskId.value = null;
    resultData.value = null;
  };

  return {
    isProcessing,
    processingStep,
    processingProgress,
    showProcessingModal,
    resultData,
    startImport,
    cancelImport,
    mapId,
  };
}
