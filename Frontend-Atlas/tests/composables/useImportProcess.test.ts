import { describe, it, expect, vi, beforeEach } from "vitest";
import { useImportProcess } from "../../src/composables/useImportProcess";
import { apiFetch } from "../../src/utils/api";

vi.mock("../../src/utils/api", () => ({
  apiFetch: vi.fn(),
}));

describe("useImportProcess", () => {
  let composable: ReturnType<typeof useImportProcess>;
  const mockedApiFetch = vi.mocked(apiFetch);

  beforeEach(() => {
    composable = useImportProcess();
    vi.clearAllMocks();
  });

  it("should return error if no file is provided", async () => {
    const result = await composable.startImport(
      null as any,
      "project-123",
      "map-123",
    );
    expect(result.success).toBe(false);
    if (result.success) {
      throw new Error("Expected import to fail when file is missing");
    }
    expect(result.error).toBe("Aucun fichier sélectionné");
  });

  it("should handle file upload and start polling on success", async () => {
    vi.useFakeTimers();

    const fakeFile = new File(["dummy content"], "test.csv", {
      type: "text/csv",
    });
    const mockTaskId = "12345";
    const mockMapId = "map-123";

    mockedApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ task_id: mockTaskId, map_id: mockMapId }),
    } as Response);
    mockedApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        state: "SUCCESS",
        progress_percentage: 100,
        status: "Done",
        result: { message: "Success" },
      }),
    } as Response);

    const result = await composable.startImport(
      fakeFile,
      "project-123",
      "map-123",
    );

    await vi.advanceTimersByTimeAsync(1000);

    expect(result.success).toBe(true);
    expect(composable.isProcessing.value).toBe(false);
    expect(composable.resultData.value).toEqual({ message: "Success" });

    vi.useRealTimers();
  });

  it("should return error on failed upload", async () => {
    mockedApiFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: "Fichier invalide" }),
    } as Response);

    const fakeFile = new File(["dummy"], "invalid.csv");

    const result = await composable.startImport(
      fakeFile,
      "project-123",
      "map-123",
    );
    expect(result.success).toBe(false);
    if (result.success) {
      throw new Error("Expected import to fail on invalid upload");
    }
    expect(result.error).toBe("Fichier invalide");
    expect(composable.isProcessing.value).toBe(false);
  });

  it("should append legend_bounds when provided and omit it when null", async () => {
    mockedApiFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Fichier invalide" }),
    } as Response);

    const fakeFile = new File(["dummy"], "map.png", { type: "image/png" });
    const legendBounds = { x: 10, y: 20, width: 30, height: 40 };

    await composable.startImport(
      fakeFile,
      "project-123",
      "map-123",
      undefined,
      undefined,
      undefined,
      legendBounds,
    );

    const firstUploadCall = mockedApiFetch.mock.calls[0];
    const firstBody = firstUploadCall[1].body as FormData;

    expect(firstBody.get("legend_bounds")).toBe(JSON.stringify(legendBounds));

    await composable.startImport(
      fakeFile,
      "project-123",
      "map-123",
      undefined,
      undefined,
      undefined,
      null,
    );

    const secondUploadCall = mockedApiFetch.mock.calls[1];
    const secondBody = secondUploadCall[1].body as FormData;

    expect(secondBody.has("legend_bounds")).toBe(false);
  });

  it("should cancel import correctly", () => {
    composable.isProcessing.value = true;
    composable.processingStep.value = "extraction";
    composable.processingProgress.value = 50;

    composable.cancelImport();

    expect(composable.isProcessing.value).toBe(false);
    expect(composable.processingStep.value).toBe("upload");
    expect(composable.processingProgress.value).toBe(0);
    expect(composable.resultData.value).toBeNull();
  });
});
