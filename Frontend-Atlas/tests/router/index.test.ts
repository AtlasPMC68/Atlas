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
});

Object.defineProperty(window, "scrollTo", {
  value: vi.fn(),
  writable: true,
});

import keycloak from "../../src/keycloak";
import { router } from "../../src/router";

describe("router auth guard with Keycloak", () => {
  beforeEach(async () => {
    vi.clearAllMocks();

    keycloak.authenticated = false;
    keycloak.token = null;

    await router.replace("/");
    await nextTick();
  });

  it("calls keycloak.login and blocks navigation if not authenticated", async () => {
    await router.push("/demo/upload");
    await nextTick();

    expect(router.currentRoute.value.fullPath).toBe("/");

    expect(keycloak.login).toHaveBeenCalledOnce();

    expect(keycloak.login).toHaveBeenCalledWith({
      redirectUri: expect.stringContaining("/demo/upload"),
    });
  });

  it("allows navigation if authenticated", async () => {
    keycloak.authenticated = true;
    keycloak.token = "fake-token";

    await router.push("/demo/upload");
    await nextTick();

    expect(router.currentRoute.value.fullPath).toBe("/demo/upload");
  });
});