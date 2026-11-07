import { describe, it, expect, vi, beforeEach } from "vitest";
import { useProjectLabelStyles } from "../../src/composables/useProjectLabelStyles";
import * as api from "../../src/utils/api";
import * as alert from "../../src/composables/useAlert";

vi.mock("../../src/utils/api", () => ({
  apiFetch: vi.fn(),
}));

vi.mock("../../src/composables/useAlert", () => ({
  showAlert: vi.fn(),
}));

describe("useProjectLabelStyles", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("loadCustomLabelStyles", () => {
    it("resets and returns empty array if projectId is missing", async () => {
      const { loadCustomLabelStyles, customLabelStyles } = useProjectLabelStyles();
      const result = await loadCustomLabelStyles(null);
      expect(result).toEqual([]);
      expect(customLabelStyles.value).toEqual([]);
      expect(api.apiFetch).not.toHaveBeenCalled();
    });

    it("fetches and sets customLabelStyles on success", async () => {
      const mockStyles = [
        {
          name: "City",
          font_family: "Cinzel",
          font_size: 14,
          font_color: "#ffffff",
          font_weight: "bold",
          font_style: "normal",
        },
      ];
      vi.mocked(api.apiFetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockStyles,
      } as any);

      const { loadCustomLabelStyles, customLabelStyles, isLoadingStyles } = useProjectLabelStyles();
      const promise = loadCustomLabelStyles("proj-1");
      expect(isLoadingStyles.value).toBe(true);

      const result = await promise;
      expect(isLoadingStyles.value).toBe(false);
      expect(api.apiFetch).toHaveBeenCalledWith("/projects/proj-1/label-styles");
      expect(result).toHaveLength(1);
      expect(result[0].fontFamily).toBe("Cinzel");
      expect(customLabelStyles.value).toEqual(result);
    });

    it("handles fetch failure gracefully and shows error alert", async () => {
      vi.mocked(api.apiFetch).mockResolvedValueOnce({
        ok: false,
        status: 500,
      } as any);

      const { loadCustomLabelStyles, customLabelStyles, isLoadingStyles } = useProjectLabelStyles();
      const result = await loadCustomLabelStyles("proj-1");

      expect(isLoadingStyles.value).toBe(false);
      expect(result).toEqual([]);
      expect(customLabelStyles.value).toEqual([]);
      expect(alert.showAlert).toHaveBeenCalledWith(
        "error",
        "Impossible de charger les styles de libellé du projet.",
      );
    });
  });

  describe("saveCustomLabelStyles", () => {
    it("shows error alert and returns empty array if projectId is missing", async () => {
      const { saveCustomLabelStyles } = useProjectLabelStyles();
      const result = await saveCustomLabelStyles(null, []);
      expect(result).toEqual([]);
      expect(alert.showAlert).toHaveBeenCalledWith(
        "error",
        "Impossible d'enregistrer un style sans projet.",
      );
    });

    it("saves styles, updates state, and shows success alert", async () => {
      const newStyles = [
        {
          name: "Province",
          fontFamily: "Lora",
          fontSize: 16,
          fontColor: "#000000",
          fontWeight: "bold",
          fontStyle: "italic",
        },
      ];
      vi.mocked(api.apiFetch).mockResolvedValueOnce({
        ok: true,
        json: async () => [{
          name: "Province",
          font_family: "Lora",
          font_size: 16,
          font_color: "#000000",
          font_weight: "bold",
          font_style: "italic",
        }],
      } as any);

      const { saveCustomLabelStyles, customLabelStyles, isSavingStyles } = useProjectLabelStyles();
      const promise = saveCustomLabelStyles("proj-1", newStyles as any);
      expect(isSavingStyles.value).toBe(true);

      const result = await promise;
      expect(isSavingStyles.value).toBe(false);
      expect(api.apiFetch).toHaveBeenCalledWith("/projects/proj-1/label-styles", expect.objectContaining({
        method: "PUT",
      }));
      expect(result[0].fontFamily).toBe("Lora");
      expect(customLabelStyles.value).toEqual(result);
      expect(alert.showAlert).toHaveBeenCalledWith(
        "success",
        "Styles de libellé enregistrés dans ce projet.",
      );
    });
  });
});
