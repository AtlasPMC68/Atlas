import { apiErrorMessage, apiFetch } from "../utils/api";
import { isAuthRequiredError } from "../services/authSession";
import type { ApiResult } from "../typescript/importSession";

export function useMapReferenceImage() {
  const fetchReferenceImage = async (
    mapId: string,
  ): Promise<ApiResult<string>> => {
    try {
      const response = await apiFetch(`/imports/${mapId}/reference-image`);
      if (!response.ok) {
        return {
          success: false,
          status: response.status,
          error: await apiErrorMessage(response, "Erreur lors du chargement de l'image"),
        };
      }
      return { success: true, data: URL.createObjectURL(await response.blob()) };
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : "Erreur lors du chargement de l'image",
      };
    }
  };

  const saveReferenceImage = async (
    mapId: string,
    file: File,
  ): Promise<ApiResult<void>> => {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await apiFetch(`/imports/${mapId}/reference-image`, {
        method: "PUT",
        body: formData,
        auth: "required",
      });
      if (!response.ok) {
        return {
          success: false,
          status: response.status,
          error: await apiErrorMessage(response, "Erreur lors de l'enregistrement de l'image"),
        };
      }
      return { success: true, data: undefined };
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : "Erreur lors de l'enregistrement de l'image",
        ...(isAuthRequiredError(err) ? { authRequired: true } : {}),
      };
    }
  };

  const deleteReferenceImage = async (
    mapId: string,
  ): Promise<ApiResult<void>> => {
    try {
      const response = await apiFetch(`/imports/${mapId}/reference-image`, {
        method: "DELETE",
        auth: "required",
      });
      if (!response.ok) {
        return {
          success: false,
          status: response.status,
          error: await apiErrorMessage(response, "Erreur lors de la suppression de l'image"),
        };
      }
      return { success: true, data: undefined };
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : "Erreur lors de la suppression de l'image",
        ...(isAuthRequiredError(err) ? { authRequired: true } : {}),
      };
    }
  };

  return { fetchReferenceImage, saveReferenceImage, deleteReferenceImage };
}
