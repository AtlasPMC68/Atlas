// composables/useImportProcess.ts
import { ref, Ref } from "vue";
import keycloak from "../keycloak";

type ImagePoint = { x: number; y: number };
type WorldPoint = { lat: number; lng: number };

type ExtractionOptions = {
  enableGeoreferencing?: boolean;
  enableColorExtraction?: boolean;
  enableShapesExtraction?: boolean;
  enableTextExtraction?: boolean;
};

type ProcessingStep = "upload" | "analysis" | "extraction" | "processing";

type StartImportResult = { success: true } | { success: false; error: string };

interface UploadResponse {
  task_id: string | null;
  map_id: string | null;
}

interface StatusResponse {
  progress_percentage?: number;
  status?: string;
  state?: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE" | string;
  result?: unknown;
  error?: string;
}

const isProcessing: Ref<boolean> = ref(false);
const processingStep: Ref<ProcessingStep> = ref("upload");
const processingProgress: Ref<number> = ref(0);
const showProcessingModal: Ref<boolean> = ref(false);
const taskId: Ref<string | null> = ref(null);
const resultData: Ref<unknown | null> = ref(null);
const mapId: Ref<string | null> = ref(null);

export function useImportProcess() {
  const startImport = async (
    file: File | null,
<<<<<<< HEAD
    imagePoints?: { x: number; y: number }[],
    worldPoints?: { lat: number; lng: number }[],
    options?: {
      enableGeoreferencing?: boolean;
      enableColorExtraction?: boolean;
      enableShapesExtraction?: boolean;
      enableTextExtraction?: boolean;
    }
  ) => {
=======
    imagePoints?: ImagePoint[],
    worldPoints?: WorldPoint[],
    options?: ExtractionOptions,
  ): Promise<StartImportResult> => {
>>>>>>> 0c052a9afe531e9630a00cc1384ca14f3f0e42e6
    if (!file) return { success: false, error: "Aucun fichier sélectionné" };

    isProcessing.value = true;
    showProcessingModal.value = true;
    processingStep.value = "upload";
    processingProgress.value = 0;

    const formData = new FormData();
<<<<<<< HEAD
    
=======

>>>>>>> 0c052a9afe531e9630a00cc1384ca14f3f0e42e6
    // Add matched point pairs as expected by backend
    if (imagePoints && imagePoints.length) {
      formData.append("image_points", JSON.stringify(imagePoints));
    }
    if (worldPoints && worldPoints.length) {
      formData.append("world_points", JSON.stringify(worldPoints));
    }
<<<<<<< HEAD
        // Add extraction options
=======
    // Add extraction options
>>>>>>> 0c052a9afe531e9630a00cc1384ca14f3f0e42e6
    if (options) {
      formData.append("enable_georeferencing", String(options.enableGeoreferencing ?? true));
      formData.append("enable_color_extraction", String(options.enableColorExtraction ?? true));
      formData.append("enable_shapes_extraction", String(options.enableShapesExtraction ?? false));
      formData.append("enable_text_extraction", String(options.enableTextExtraction ?? false));
    }
<<<<<<< HEAD
        formData.append("file", file);

    console.log("form data", formData)
=======
    formData.append("file", file);
>>>>>>> 0c052a9afe531e9630a00cc1384ca14f3f0e42e6

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/maps/upload`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${keycloak.token}`,
          },
          body: formData,
        },
      );

      if (!response.ok) {
        const error: Partial<{ detail: string }> = await response.json();
        throw new Error(error.detail || "Erreur lors de l'envoi du fichier");
      }

      const data: UploadResponse = await response.json();
      taskId.value = data.task_id;
      mapId.value = data.map_id;

      if (!taskId.value) {
        throw new Error("taskId is null");
      }

      pollStatus(taskId.value);

      return { success: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Erreur inattendue";
      isProcessing.value = false;
      showProcessingModal.value = false;
      return { success: false, error: message };
    }
  };

  const mapStatusToStep = (statusText: string): ProcessingStep => {
    if (statusText.includes("Saving")) return "upload";
    if (statusText.includes("Loading")) return "analysis";
    if (statusText.includes("Extracting")) return "extraction";
    if (statusText.includes("Cleaning")) return "processing";
    return "upload";
  };

  const pollStatus = (taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(
          `${import.meta.env.VITE_API_URL}/maps/status/${taskId}`,
        );
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
          console.error("Erreur de traitement:", data.error);
        }
      } catch (err) {
        console.error("Erreur lors du polling:", err);
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
