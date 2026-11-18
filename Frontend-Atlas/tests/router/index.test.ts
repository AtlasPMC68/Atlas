import { describe, it, expect, beforeEach, vi } from "vitest";
import { nextTick } from "vue";

vi.mock("../../src/keycloak", () => ({
  default: {
    authenticated: false,
    token: null,
    login: vi.fn(),
    logout: vi.fn(),
    init: vi.fn(),
    updateToken: vi.fn().mockResolvedValue(true),
    isTokenExpired: vi.fn().mockReturnValue(false),
    didInitialize: true,
  },
}));

global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: async () => ({}),
});

Object.defineProperty(window, "scrollTo", {
  value: vi.fn(),
  writable: true,
});

import keycloak from "../../src/keycloak";
import { router } from "../../src/router";
import { registerAuthRedirectHandler, syncAuthenticatedSession } from "../../src/services/authSession";

describe("router auth guard with Keycloak", () => {
  const targetUploadRoute =
    "/televersement/00000000-0000-0000-0000-000000000001";

  beforeEach(async () => {
    vi.clearAllMocks();
    vi.mocked(keycloak.updateToken).mockReset().mockResolvedValue(true);

    keycloak.authenticated = true;
    keycloak.token = "test-token";
    syncAuthenticatedSession();
    keycloak.authenticated = false;
    keycloak.token = null;

    await router.replace("/");
    await nextTick();
  });

  it("calls keycloak.login and blocks navigation if not authenticated", async () => {
    await router.push(targetUploadRoute);
    await nextTick();

    expect(router.currentRoute.value.fullPath).toBe("/");
    expect(keycloak.login).toHaveBeenCalledOnce();
    expect(keycloak.login).toHaveBeenCalledWith({
      redirectUri: expect.stringContaining(targetUploadRoute),
    });
  });

  it("allows navigation if authenticated", async () => {
    keycloak.authenticated = true;
    keycloak.token = "fake-token";

    await router.push(targetUploadRoute);
    await nextTick();

    expect(router.currentRoute.value.fullPath).toBe(targetUploadRoute);
  });

  it("keeps the current page after a transient refresh error without redirecting to login", async () => {
    keycloak.authenticated = true;
    keycloak.token = "old-token";
    vi.mocked(keycloak.updateToken).mockRejectedValueOnce(new TypeError("Network unavailable"));

    await router.push(targetUploadRoute);
    await nextTick();

    expect(router.currentRoute.value.fullPath).toBe("/");
    expect(keycloak.login).not.toHaveBeenCalled();
    expect(keycloak.token).toBe("old-token");
  });

  it("asks for login when Keycloak confirms that the session ended during refresh", async () => {
    keycloak.authenticated = true;
    keycloak.token = "old-token";
    vi.mocked(keycloak.updateToken).mockImplementationOnce(async () => {
      keycloak.authenticated = false;
      keycloak.token = undefined;
      throw new Error("Session expired");
    });

    await router.push(targetUploadRoute);
    await nextTick();

    expect(router.currentRoute.value.fullPath).toBe("/");
    expect(keycloak.login).toHaveBeenCalledOnce();
  });

  it("blocks protected-route login when the current editor cannot preserve its draft", async () => {
    const removeHandler = registerAuthRedirectHandler(async () => {
      throw new Error("Stockage local indisponible");
    });
    try {
      await router.push(targetUploadRoute);
      expect(router.currentRoute.value.fullPath).toBe("/");
      expect(keycloak.login).not.toHaveBeenCalled();
    } finally {
      removeHandler();
    }
  });
});
