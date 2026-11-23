import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../src/keycloak", () => ({
  default: {
    authenticated: false,
    token: undefined,
    subject: "admin-user",
    updateToken: vi.fn(),
    isTokenExpired: vi.fn(),
    login: vi.fn(),
  },
}));

import keycloak from "../../src/keycloak";
import { useBorders } from "../../src/composables/useBorders";
import { useDevTestCases } from "../../src/composables/useDevTestCases";
import {
  useDevTestImportProcess,
  type DevTestImportInputs,
} from "../../src/composables/useDevTestImportProcess";
import {
  AuthRequiredError,
  sessionState,
  syncAuthenticatedSession,
} from "../../src/services/authSession";

const fetchMock = vi.fn();
const stopImports: Array<() => void> = [];
const inputs: DevTestImportInputs = {
  controlPoints: [],
  checkPoints: [],
  colors: [],
  frameBounds: null,
  legend: null,
};

function authenticate() {
  keycloak.authenticated = true;
  keycloak.token = "admin-token";
  syncAuthenticatedSession();
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("VITE_API_URL", "https://atlas.example/api");
  vi.mocked(keycloak.updateToken).mockResolvedValue(false);
  vi.mocked(keycloak.isTokenExpired).mockReturnValue(false);
  authenticate();
  keycloak.authenticated = false;
  keycloak.token = undefined;
});

afterEach(() => {
  stopImports.splice(0).forEach((stop) => stop());
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("protected dev-test requests", () => {
  it.each([
    ["countries", () => useBorders().listCountries()],
    ["regions", () => useBorders().listRegions("CA")],
    ["zone creation", () => useBorders().loadZone("CA", ["QC"])],
    ["test cases", () => useDevTestCases().listCases("test-map")],
    ["case inputs", () => useDevTestCases().fetchCaseInputs("test-map", "case")],
  ] as const)("blocks %s without sending an anonymous request after session loss", async (_, request) => {
    await expect(request()).rejects.toBeInstanceOf(AuthRequiredError);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(keycloak.login).not.toHaveBeenCalled();
    expect(sessionState.status).toBe("reauth-required");
  });

  it("renews the token before a zone request and preserves its payload", async () => {
    authenticate();
    vi.mocked(keycloak.updateToken).mockImplementationOnce(async () => {
      keycloak.token = "renewed-admin-token";
      return true;
    });
    fetchMock.mockResolvedValueOnce(new Response('{"geometry":null}'));

    await useBorders().loadZone("CA", ["QC"]);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, request] = fetchMock.mock.calls[0];
    expect(url).toBe("https://atlas.example/api/dev-test-api/borders/zone");
    expect(request.method).toBe("POST");
    expect(request.headers.get("Authorization")).toBe("Bearer renewed-admin-token");
    expect(JSON.parse(request.body)).toEqual({ country: "CA", regions: ["QC"] });
    expect(request).not.toHaveProperty("auth");
  });

  it("keeps a role denial distinct from a lost session", async () => {
    authenticate();
    fetchMock.mockResolvedValueOnce(new Response('{"detail":"Admin required"}', { status: 403 }));

    expect(await useDevTestCases().listCases("test-map")).toEqual({
      success: false,
      error: "Admin required",
      status: 403,
    });
    expect(sessionState.status).toBe("authenticated");
    expect(keycloak.login).not.toHaveBeenCalled();
  });

  it("keeps the upload inputs and requests reconnection when the session is missing", async () => {
    const process = useDevTestImportProcess();
    stopImports.push(process.cancelImport);
    const snapshot = JSON.stringify(inputs);

    expect(await process.startImport("test-map", "case", inputs)).toMatchObject({ success: false });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(process.isProcessing.value).toBe(false);
    expect(process.error.value).toContain("reconnecter");
    expect(JSON.stringify(inputs)).toBe(snapshot);
    expect(sessionState.status).toBe("reauth-required");
    expect(keycloak.login).not.toHaveBeenCalled();
  });

  it("stops watching a task after session loss without sending an anonymous status request", async () => {
    vi.useFakeTimers();
    authenticate();
    fetchMock.mockResolvedValueOnce(new Response('{"task_id":"task-1","map_id":"test-map"}'));
    const process = useDevTestImportProcess();
    stopImports.push(process.cancelImport);

    expect(await process.startImport("test-map", "case", inputs)).toEqual({ success: true });
    keycloak.authenticated = false;
    keycloak.token = undefined;
    await vi.advanceTimersByTimeAsync(1000);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(process.isProcessing.value).toBe(false);
    expect(process.error.value).toContain("reconnecter");
    expect(sessionState.status).toBe("reauth-required");
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("does not send an anonymous warmup request and exposes the lost session", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const process = useDevTestImportProcess();
    stopImports.push(process.cancelImport);

    await process.warmTextRegions("test-map");

    expect(fetchMock).not.toHaveBeenCalled();
    expect(sessionState.status).toBe("reauth-required");
  });
});
