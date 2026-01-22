// composables/useImportProcess.ts
import { ref } from "vue";

const isProcessing = ref(false);
const processingStep = ref("upload");
const processingProgress = ref(0);
const showProcessingModal = ref(false);
const taskId = ref(null);
const resultData = ref(null);
const mapId = ref(null);

export function useImportProcess() {
  const startImport = async (file: File, imagePolyline?: any[], worldPolyline?: any[]) => {
    if (!file) return { success: false, error: "Aucun fichier sélectionné" };

    isProcessing.value = true;
    showProcessingModal.value = true;
    processingStep.value = "upload";
    processingProgress.value = 0;

    // Upload fichier + polylines → POST /maps/upload
    const formData = new FormData();
    
    // Add polylines if provided
    if (imagePolyline && worldPolyline) {
      formData.append("image_polyline", JSON.stringify(imagePolyline.map(([x, y]) => ({ x, y }))));
      formData.append("world_polyline", JSON.stringify(worldPolyline.map(([lat, lng]) => ({ lat, lng }))));
      console.log("polines", formData);
    }
    formData.append("file", file);

    try {
      const response = await fetch("http://localhost:8000/maps/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erreur lors de l’envoi du fichier");
      }

      const data = await response.json();
      taskId.value = data.task_id;
      mapId.value = data.map_id;
      if (!taskId.value) {
        throw new Error("taskId is null");
      }
      // Démarre le polling
      pollStatus(taskId.value);

      return { 
        success: true
      };
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
        const res = await fetch(`http://localhost:8000/maps/status/${taskId}`);
        const data = await res.json();
        console.log("[Polling]", data);
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
    mapId: mapId
  };
}
