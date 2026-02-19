// composables/useImportProcess.ts
import { ref, Ref } from "vue";
import keycloak from "../keycloak";

const isProcessing = ref(false);
const processingStep = ref("upload");
const processingProgress = ref(0);
const showProcessingModal = ref(false);
const taskId: Ref<string | null> = ref(null);
const resultData: Ref<any> = ref(null);
const mapId: Ref<string | null> = ref(null);

export function useImportProcess() {
<<<<<<< HEAD
  const startImport = async (
    file: File,
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
  const startImport = async (file: File | null) => {
>>>>>>> 2e68347bea99385f12092db6f4b95ec37818eac2
    if (!file) return { success: false, error: "Aucun fichier sélectionné" };

    isProcessing.value = true;
    showProcessingModal.value = true;
    processingStep.value = "upload";
    processingProgress.value = 0;

<<<<<<< HEAD
    // Upload fichier + points SIFT POST /maps/upload
=======
>>>>>>> 2e68347bea99385f12092db6f4b95ec37818eac2
    const formData = new FormData();
    
    // Add matched point pairs as expected by backend
    if (imagePoints && imagePoints.length) {
      formData.append("image_points", JSON.stringify(imagePoints));
    }
    if (worldPoints && worldPoints.length) {
      formData.append("world_points", JSON.stringify(worldPoints));
    }
        // Add extraction options
    if (options) {
      formData.append("enable_georeferencing", String(options.enableGeoreferencing ?? true));
      formData.append("enable_color_extraction", String(options.enableColorExtraction ?? true));
      formData.append("enable_shapes_extraction", String(options.enableShapesExtraction ?? false));
      formData.append("enable_text_extraction", String(options.enableTextExtraction ?? false));
    }
        formData.append("file", file);

    console.log("form data", formData)

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
        const error = await response.json();
        throw new Error(error.detail || "Erreur lors de l'envoi du fichier");
      }

      const data = await response.json();
      taskId.value = data.task_id;
      mapId.value = data.map_id;

      if (!taskId.value) {
        throw new Error("taskId is null");
      }

      pollStatus(taskId.value);

      return { success: true };
    } catch (err: any) {
      isProcessing.value = false;
      showProcessingModal.value = false;
      return { success: false, error: err.message };
    }
  };

  const mapStatusToStep = (statusText: string): string => {
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
        const data = await res.json();

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
