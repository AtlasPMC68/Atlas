// composables/useImportSession.ts
// The /imports API: one row per map while its import is in progress.
import { apiFetch } from "../utils/api";
import type {
  ApiResult,
  ImportInputsPatch,
  ImportSessionResponse,
} from "../typescript/importSession";

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const body: Partial<{ detail: string }> = await response.json().catch(() => ({}));
  return body.detail || fallback;
}

async function sessionRequest(
  path: string,
  init: RequestInit,
  fallback: string,
): Promise<ApiResult<ImportSessionResponse>> {
  try {
    const response = await apiFetch(path, init);
    if (!response.ok) {
      return {
        success: false,
        status: response.status,
        error: await errorMessage(response, fallback),
      };
    }
    return { success: true, data: (await response.json()) as ImportSessionResponse };
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : fallback,
    };
  }
}

export function useImportSession() {
  // Uploads the map; OCR starts on the backend right away.
  const createImport = (mapId: string, file: File) => {
    const formData = new FormData();
    formData.append("map_id", mapId);
    formData.append("file", file);
    return sessionRequest(
      "/imports",
      { method: "POST", body: formData },
      "Erreur lors de l'envoi de la carte",
    );
  };

  // A 404 (status on the error) means no import is in progress for the map.
  const fetchImport = (mapId: string) =>
    sessionRequest(`/imports/${mapId}`, {}, "Erreur lors du chargement de l'import");

  // The uploaded image, as a File so the pipette can send it like a picked one.
  const fetchImportImage = async (
    mapId: string,
    filename: string,
  ): Promise<ApiResult<File>> => {
    try {
      const response = await apiFetch(`/imports/${mapId}/image`);
      if (!response.ok) {
        return {
          success: false,
          status: response.status,
          error: await errorMessage(response, "Image introuvable"),
        };
      }
      const blob = await response.blob();
      return { success: true, data: new File([blob], filename, { type: blob.type }) };
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : "Image introuvable",
      };
    }
  };

  const saveInputs = (mapId: string, patch: ImportInputsPatch) =>
    sessionRequest(
      `/imports/${mapId}/inputs`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      },
      "Erreur lors de l'enregistrement",
    );

  const startExtraction = (mapId: string) =>
    sessionRequest(
      `/imports/${mapId}/extract`,
      { method: "POST" },
      "Erreur lors du lancement de l'extraction",
    );

  const cancelExtraction = (mapId: string) =>
    sessionRequest(
      `/imports/${mapId}/cancel`,
      { method: "POST" },
      "Erreur lors de l'annulation",
    );

  const abandonImport = async (mapId: string): Promise<ApiResult<null>> => {
    try {
      const response = await apiFetch(`/imports/${mapId}`, { method: "DELETE" });
      if (!response.ok) {
        return {
          success: false,
          status: response.status,
          error: await errorMessage(response, "Erreur lors de l'abandon de l'import"),
        };
      }
      return { success: true, data: null };
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : "Erreur inattendue",
      };
    }
  };

  return {
    createImport,
    fetchImport,
    fetchImportImage,
    saveInputs,
    startExtraction,
    cancelExtraction,
    abandonImport,
  };
}
