import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../src/keycloak", () => ({
  default: {
    authenticated: false,
    token: undefined,
    updateToken: vi.fn(),
    isTokenExpired: vi.fn(),
    login: vi.fn(),
  },
}));

import keycloak from "../../src/keycloak";
import { apiFetch } from "../../src/utils/api";
import { AuthRequiredError, sessionState, syncAuthenticatedSession } from "../../src/services/authSession";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("VITE_API_URL", "https://atlas.example/api");
  keycloak.authenticated = true;
  keycloak.token = "test-token";
  syncAuthenticatedSession();
  keycloak.authenticated = false;
  keycloak.token = undefined;
  vi.mocked(keycloak.updateToken).mockResolvedValue(false);
  vi.mocked(keycloak.isTokenExpired).mockReturnValue(false);
  fetchMock.mockResolvedValue(new Response("{}"));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("apiFetch authentication", () => {
  it("allows guest reads without refreshing or sending an old Authorization header", async () => {
    await apiFetch("/projects", { headers: { Authorization: "Bearer stale" } });

    expect(keycloak.updateToken).not.toHaveBeenCalled();
    expect(keycloak.login).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://atlas.example/api/projects");
    expect(init.headers.has("Authorization")).toBe(false);
  });

  it("awaits refresh before uploading and uses the renewed token with the original request body", async () => {
    keycloak.authenticated = true;
    keycloak.token = "old";
    let finishRefresh!: (refreshed: boolean) => void;
    vi.mocked(keycloak.updateToken).mockImplementation(() => new Promise((resolve) => {
      finishRefresh = resolve;
    }));
    const body = new FormData();
    body.append("file", new File(["map"], "map.png"));
    const controller = new AbortController();
    const originalHeaders = new Headers({ Authorization: "Bearer old", "X-Request-Id": "upload-1" });

    const request = apiFetch("/imports", {
      method: "POST",
      body,
      signal: controller.signal,
      headers: originalHeaders,
    });
    expect(fetchMock).not.toHaveBeenCalled();
    keycloak.token = "renewed";
    finishRefresh(true);
    await request;

    expect(keycloak.updateToken).toHaveBeenCalledWith(30);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(body);
    expect(init.signal).toBe(controller.signal);
    expect(init.headers.get("Authorization")).toBe("Bearer renewed");
    expect(init.headers.get("X-Request-Id")).toBe("upload-1");
    expect(init.headers.has("Content-Type")).toBe(false);
    expect(originalHeaders.get("Authorization")).toBe("Bearer old");
  });

  it("uses the existing token when Keycloak reports renewal is unnecessary", async () => {
    keycloak.authenticated = true;
    keycloak.token = "still-valid";

    await apiFetch("/me");

    expect(fetchMock.mock.calls[0][1].headers.get("Authorization")).toBe("Bearer still-valid");
  });

  it("does not send a mutation or navigate after a refresh network error, and allows a later retry", async () => {
    keycloak.authenticated = true;
    keycloak.token = "expired";
    const networkError = new TypeError("Network unavailable");
    vi.mocked(keycloak.updateToken).mockRejectedValueOnce(networkError);

    await expect(apiFetch("/projects/1/features", { method: "PUT", body: "[]" }))
      .rejects.toBe(networkError);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(keycloak.login).not.toHaveBeenCalled();
    expect(keycloak.token).toBe("expired");

    vi.mocked(keycloak.updateToken).mockImplementationOnce(async () => {
      keycloak.token = "renewed";
      return true;
    });
    await apiFetch("/projects/1/features", { method: "PUT", body: "[]" });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][1].headers.get("Authorization")).toBe("Bearer renewed");
  });

  it.each([403, 500])("returns an API %i without repeating the mutation or starting login", async (status) => {
    keycloak.authenticated = true;
    keycloak.token = "valid";
    const response = new Response("{}", { status });
    fetchMock.mockResolvedValue(response);

    expect(await apiFetch("/projects/create", { method: "POST", body: "{}" })).toBe(response);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(keycloak.updateToken).toHaveBeenCalledOnce();
    expect(keycloak.login).not.toHaveBeenCalled();
  });

  it("blocks a protected mutation before sending when the session is missing", async () => {
    await expect(apiFetch("/projects/1/features", { auth: "required", method: "PUT", body: "[]" }))
      .rejects.toBeInstanceOf(AuthRequiredError);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(keycloak.login).not.toHaveBeenCalled();
    expect(sessionState.status).toBe("reauth-required");
  });

  it("marks an authenticated 401 without repeating a mutation or navigating", async () => {
    keycloak.authenticated = true;
    keycloak.token = "rejected-token";
    fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));

    await expect(apiFetch("/projects/create", { auth: "required", method: "POST", body: "{}" }))
      .rejects.toBeInstanceOf(AuthRequiredError);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("auth");
    expect(keycloak.login).not.toHaveBeenCalled();
    expect(sessionState.status).toBe("reauth-required");
  });
});
