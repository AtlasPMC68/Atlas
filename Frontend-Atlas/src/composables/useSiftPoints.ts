// composables/useSiftPoints.ts
import { ref } from "vue";

export type SiftKeypoint = {
  x: number;
  y: number;
  size?: number;
  angle?: number;
  response?: number;
  octave?: number;
  class_id?: number;
};

export type SiftResponse = {
  image?: { width: number; height: number };
  count: number;
  keypoints: SiftKeypoint[];
};

const isLoading = ref(false);
const error = ref<string | null>(null);
const siftData = ref<SiftResponse | null>(null);

export function useSiftPoints() {
  const fetchSiftPoints = async (file: File) => {
    if (!file) return { success: false, error: "Aucun fichier sélectionné" };

    isLoading.value = true;
    error.value = null;
    siftData.value = null;

    const formData = new FormData();
    formData.append("file", file);
//    formData.append("max_features", String(maxFeatures)); // backend expects Form field

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/maps/sift`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.detail || "Erreur lors de l’extraction SIFT");
      }

      const data = (await response.json()) as SiftResponse;
      siftData.value = data;

      return { success: true, data };
    } catch (e: any) {
      error.value = e.message || "Erreur inconnue";
      return { success: false, error: error.value };
    } finally {
      isLoading.value = false;
    }
  };

  const resetSift = () => {
    isLoading.value = false;
    error.value = null;
    siftData.value = null;
  };

  return {
    isSiftLoading: isLoading,
    siftError: error,
    siftData,
    fetchSiftPoints,
    resetSift,
  };
}