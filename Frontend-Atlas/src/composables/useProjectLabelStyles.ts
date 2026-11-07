import { ref } from "vue";
import type { CustomLabelStyle } from "../utils/labelPresentation";
import { apiFetch } from "../utils/api";
import { camelToSnake, snakeToCamel } from "../utils/utils";
import { showAlert } from "./useAlert";

export function useProjectLabelStyles() {
  const customLabelStyles = ref<CustomLabelStyle[]>([]);
  const isLoadingStyles = ref(false);
  const isSavingStyles = ref(false);

  async function loadCustomLabelStyles(
    projectId?: string | null,
  ): Promise<CustomLabelStyle[]> {
    if (!projectId) {
      customLabelStyles.value = [];
      return [];
    }

    isLoadingStyles.value = true;
    try {
      const response = await apiFetch(`/projects/${projectId}/label-styles`);
      if (!response.ok) {
        throw new Error(`Failed to load project label styles: ${response.status}`);
      }
      const data = snakeToCamel(await response.json()) as CustomLabelStyle[];
      customLabelStyles.value = Array.isArray(data) ? data : [];
      return customLabelStyles.value;
    } catch (error) {
      console.error("Failed to load project label styles:", error);
      showAlert("error", "Impossible de charger les styles de libellé du projet.");
      return [];
    } finally {
      isLoadingStyles.value = false;
    }
  }

  async function saveCustomLabelStyles(
    projectId: string | null | undefined,
    styles: CustomLabelStyle[],
  ): Promise<CustomLabelStyle[]> {
    if (!projectId) {
      showAlert("error", "Impossible d'enregistrer un style sans projet.");
      return [];
    }

    isSavingStyles.value = true;
    try {
      const response = await apiFetch(`/projects/${projectId}/label-styles`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(camelToSnake({ styles })),
      });
      if (!response.ok) {
        throw new Error(`Failed to save project label styles: ${response.status}`);
      }
      const updated = snakeToCamel(await response.json()) as CustomLabelStyle[];
      customLabelStyles.value = Array.isArray(updated) ? updated : [];
      showAlert("success", "Styles de libellé enregistrés dans ce projet.");
      return customLabelStyles.value;
    } catch (error) {
      console.error("Failed to save project label styles:", error);
      showAlert("error", "Impossible d'enregistrer les styles de libellé.");
      throw error;
    } finally {
      isSavingStyles.value = false;
    }
  }

  return {
    customLabelStyles,
    isLoadingStyles,
    isSavingStyles,
    loadCustomLabelStyles,
    saveCustomLabelStyles,
  };
}
