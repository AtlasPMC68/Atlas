import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useImportSession } from "../../src/composables/useImportSession";
import { usePolling } from "../../src/composables/usePolling";
import { apiFetch } from "../../src/utils/api";

vi.mock("../../src/utils/api", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

const session = {
  mapId: "map-1",
  projectId: "project-1",
  mapTitle: "Traité de Paris de 1783",
  filename: "map.png",
  inputs: {},
  ocr: { state: "running" },
  extraction: { state: "idle", taskId: null, error: null, progress: 0, status: "" },
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("useImportSession", () => {
  beforeEach(() => vi.clearAllMocks());

  it("uploads the map to /imports", async () => {
    mockedApiFetch.mockResolvedValueOnce(jsonResponse(session));
    const file = new File(["x"], "map.png", { type: "image/png" });

    const res = await useImportSession().createImport("map-1", file);

    expect(res).toEqual({ success: true, data: session });
    const [path, init] = mockedApiFetch.mock.calls[0];
    expect(path).toBe("/imports");
    expect(init?.method).toBe("POST");
    const body = init?.body as FormData;
    expect(body.get("map_id")).toBe("map-1");
    expect(body.get("file")).toBe(file);
  });

  it("reports a missing import as a 404", async () => {
    mockedApiFetch.mockResolvedValueOnce(
      jsonResponse({ detail: "No import in progress for this map" }, 404),
    );

    const res = await useImportSession().fetchImport("map-1");

    expect(res).toEqual({
      success: false,
      status: 404,
      error: "No import in progress for this map",
    });
  });

  it("saves inputs as a JSON patch", async () => {
    mockedApiFetch.mockResolvedValueOnce(jsonResponse(session));
    const patch = { legend: { present: false as const, bounds: null } };

    await useImportSession().saveInputs("map-1", patch);

    const [path, init] = mockedApiFetch.mock.calls[0];
    expect(path).toBe("/imports/map-1/inputs");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual(patch);
  });

  it("starts and cancels the extraction with no body", async () => {
    mockedApiFetch.mockResolvedValue(jsonResponse(session));
    const api = useImportSession();

    await api.startExtraction("map-1");
    await api.cancelExtraction("map-1");

    expect(mockedApiFetch.mock.calls.map(([path]) => path)).toEqual([
      "/imports/map-1/extract",
      "/imports/map-1/cancel",
    ]);
  });
});

describe("usePolling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("ticks until stopped, and never after", async () => {
    const tick = vi.fn();
    const poller = usePolling(tick, 1000);

    poller.start();
    poller.start(); // a second start does not add a second timer
    await vi.advanceTimersByTimeAsync(3000);
    expect(tick).toHaveBeenCalledTimes(3);

    poller.stop();
    await vi.advanceTimersByTimeAsync(5000);
    expect(tick).toHaveBeenCalledTimes(3);
  });
});
