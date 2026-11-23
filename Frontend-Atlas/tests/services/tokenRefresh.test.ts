import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const keycloak = vi.hoisted(() => ({
  authenticated: true,
  token: "initial-token" as string | undefined,
  updateToken: vi.fn(),
  isTokenExpired: vi.fn(),
}));

vi.mock("../../src/keycloak", () => ({ default: keycloak }));

type TokenRefresh = typeof import("../../src/services/tokenRefresh");

let tokenRefresh: TokenRefresh;
let stopMonitoring: (() => void) | undefined;
let visibility: DocumentVisibilityState;

beforeEach(async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-07T12:00:00Z"));
  vi.resetModules();
  keycloak.authenticated = true;
  keycloak.token = "initial-token";
  keycloak.updateToken.mockReset().mockResolvedValue(false);
  keycloak.isTokenExpired.mockReset().mockReturnValue(false);
  visibility = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
  tokenRefresh = await import("../../src/services/tokenRefresh");
});

afterEach(() => {
  stopMonitoring?.();
  stopMonitoring = undefined;
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function startMonitoring() {
  stopMonitoring = tokenRefresh.startTokenRefresh();
  await vi.advanceTimersByTimeAsync(0);
}

describe("getValidAccessToken", () => {
  it("leaves guest requests unauthenticated without attempting a refresh", async () => {
    keycloak.authenticated = false;

    await expect(tokenRefresh.getValidAccessToken()).resolves.toBeUndefined();
    expect(keycloak.updateToken).not.toHaveBeenCalled();
    expect(keycloak.isTokenExpired).not.toHaveBeenCalled();
  });

  it("waits for renewal and returns the replacement token", async () => {
    let finishRefresh!: (refreshed: boolean) => void;
    keycloak.updateToken.mockImplementationOnce(
      () => new Promise<boolean>((resolve) => { finishRefresh = resolve; }),
    );
    let resolved = false;
    const request = tokenRefresh.getValidAccessToken().then((token) => {
      resolved = true;
      return token;
    });

    await Promise.resolve();
    expect(resolved).toBe(false);
    expect(keycloak.updateToken).toHaveBeenCalledWith(30);

    keycloak.token = "renewed-token";
    finishRefresh(true);
    await expect(request).resolves.toBe("renewed-token");
  });

  it("returns a still-valid token when Keycloak does not need to renew it", async () => {
    await expect(tokenRefresh.getValidAccessToken()).resolves.toBe("initial-token");
    expect(keycloak.updateToken).toHaveBeenCalledOnce();
  });

  it("shares an in-flight refresh and checks again for later requests", async () => {
    let finishRefresh!: (refreshed: boolean) => void;
    keycloak.updateToken.mockImplementationOnce(
      () => new Promise<boolean>((resolve) => { finishRefresh = resolve; }),
    );

    const first = tokenRefresh.getValidAccessToken();
    const second = tokenRefresh.getValidAccessToken();
    expect(second).toBe(first);
    expect(keycloak.updateToken).toHaveBeenCalledOnce();

    keycloak.token = "renewed-token";
    finishRefresh(true);
    await expect(Promise.all([first, second])).resolves.toEqual([
      "renewed-token", "renewed-token",
    ]);

    await expect(tokenRefresh.getValidAccessToken()).resolves.toBe("renewed-token");
    expect(keycloak.updateToken).toHaveBeenCalledTimes(2);
  });

  it("propagates a transient failure without clearing the session and allows a retry", async () => {
    const networkError = new TypeError("Network unavailable");
    keycloak.updateToken.mockRejectedValueOnce(networkError);

    await expect(tokenRefresh.getValidAccessToken()).rejects.toBe(networkError);
    expect(keycloak.authenticated).toBe(true);
    expect(keycloak.token).toBe("initial-token");

    keycloak.updateToken.mockImplementationOnce(async () => {
      keycloak.token = "retried-token";
      return true;
    });
    await expect(tokenRefresh.getValidAccessToken()).resolves.toBe("retried-token");
    expect(keycloak.updateToken).toHaveBeenCalledTimes(2);
  });

  it.each(["missing token", "expired token", "ended session"])(
    "rejects a refresh result with a %s",
    async (invalidState) => {
      keycloak.updateToken.mockImplementationOnce(async () => {
        if (invalidState === "missing token") keycloak.token = undefined;
        if (invalidState === "expired token") keycloak.isTokenExpired.mockReturnValue(true);
        if (invalidState === "ended session") keycloak.authenticated = false;
        return true;
      });

      await expect(tokenRefresh.getValidAccessToken()).rejects.toThrow(/session/i);
    },
  );
});

describe("activity-based token refresh", () => {
  it("checks tokens during local editing without requiring an API request", async () => {
    await startMonitoring();

    for (let interaction = 0; interaction < 6; interaction += 1) {
      await vi.advanceTimersByTimeAsync(20_000);
      document.dispatchEvent(new Event(interaction % 2 ? "keydown" : "pointerdown"));
      await vi.advanceTimersByTimeAsync(0);
    }

    expect(keycloak.updateToken.mock.calls.length).toBeGreaterThan(2);
    expect(keycloak.updateToken.mock.calls.every(([validity]) => validity === 30)).toBe(true);
  });

  it("stops refreshing an idle page and throttles checks when activity resumes", async () => {
    await startMonitoring();
    await vi.advanceTimersByTimeAsync(61_000);
    const checksBeforeIdle = keycloak.updateToken.mock.calls.length;

    await vi.advanceTimersByTimeAsync(10 * 60_000);
    expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeIdle);

    document.dispatchEvent(new Event("wheel"));
    await vi.advanceTimersByTimeAsync(0);
    expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeIdle + 1);

    await vi.advanceTimersByTimeAsync(1_000);
    document.dispatchEvent(new Event("input"));
    await vi.advanceTimersByTimeAsync(0);
    expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeIdle + 1);
  });

  it("counts dragging as activity but ignores mere pointer movement", async () => {
    await startMonitoring();
    await vi.advanceTimersByTimeAsync(90_000);
    const checksBeforeMovement = keycloak.updateToken.mock.calls.length;

    document.dispatchEvent(new MouseEvent("pointermove", { buttons: 0 }));
    await vi.advanceTimersByTimeAsync(30_000);
    expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeMovement);

    document.dispatchEvent(new MouseEvent("pointermove", { buttons: 1 }));
    await vi.advanceTimersByTimeAsync(0);
    expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeMovement + 1);
  });

  it.each(["focus", "pageshow", "visibilitychange"])(
    "waits while hidden and rechecks on visible %s",
    async (eventName) => {
      await startMonitoring();
      const checksBeforeHiding = keycloak.updateToken.mock.calls.length;
      visibility = "hidden";
      const target = eventName === "visibilitychange" ? document : window;

      target.dispatchEvent(new Event(eventName));
      document.dispatchEvent(new Event("pointerdown"));
      await vi.advanceTimersByTimeAsync(90_000);
      expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeHiding);

      visibility = "visible";
      target.dispatchEvent(new Event(eventName));
      await vi.advanceTimersByTimeAsync(0);
      expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeHiding + 1);
    },
  );

  it("recovers from a background refresh failure on the next resume", async () => {
    keycloak.updateToken.mockRejectedValueOnce(new TypeError("Network unavailable"));
    await startMonitoring();
    expect(keycloak.authenticated).toBe(true);
    expect(keycloak.token).toBe("initial-token");

    window.dispatchEvent(new Event("online"));
    await vi.advanceTimersByTimeAsync(0);
    expect(keycloak.updateToken).toHaveBeenCalledTimes(2);
  });

  it("does not treat a network reconnection as user activity on an abandoned page", async () => {
    await startMonitoring();
    await vi.advanceTimersByTimeAsync(61_000);
    const checksBeforeReconnect = keycloak.updateToken.mock.calls.length;

    window.dispatchEvent(new Event("online"));
    await vi.advanceTimersByTimeAsync(30_000);

    expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeReconnect);
  });

  it("starts only once and removes its timer and event listeners on cleanup", async () => {
    await startMonitoring();
    expect(tokenRefresh.startTokenRefresh()).toBe(stopMonitoring);
    expect(vi.getTimerCount()).toBe(1);

    stopMonitoring?.();
    expect(vi.getTimerCount()).toBe(0);
    const checksBeforeCleanup = keycloak.updateToken.mock.calls.length;
    for (const event of ["pointerdown", "keydown", "wheel", "input", "visibilitychange"]) {
      document.dispatchEvent(new Event(event));
    }
    document.dispatchEvent(new MouseEvent("pointermove", { buttons: 1 }));
    for (const event of ["focus", "online", "pageshow"]) {
      window.dispatchEvent(new Event(event));
    }
    await vi.advanceTimersByTimeAsync(90_000);
    expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeCleanup);

    await startMonitoring();
    expect(keycloak.updateToken).toHaveBeenCalledTimes(checksBeforeCleanup + 1);
  });
});

describe("authenticated background tasks", () => {
  it("allows a visible import to renew while watched, then pauses after one hour without input", async () => {
    await startMonitoring();
    await vi.advanceTimersByTimeAsync(61_000);

    expect(tokenRefresh.canRunAuthenticatedBackgroundTask()).toBe(true);
    keycloak.isTokenExpired.mockImplementation((minValidity?: number) => minValidity === 30);
    expect(tokenRefresh.canRunAuthenticatedBackgroundTask()).toBe(true);
    await vi.advanceTimersByTimeAsync(60 * 60_000 - 61_000);
    expect(tokenRefresh.canRunAuthenticatedBackgroundTask()).toBe(false);

    document.dispatchEvent(new Event("pointerdown"));
    await vi.advanceTimersByTimeAsync(0);
    expect(tokenRefresh.canRunAuthenticatedBackgroundTask()).toBe(true);
  });

  it("pauses polling for a hidden page or an unauthenticated user", async () => {
    await startMonitoring();
    visibility = "hidden";
    expect(tokenRefresh.canRunAuthenticatedBackgroundTask()).toBe(false);

    visibility = "visible";
    keycloak.authenticated = false;
    expect(tokenRefresh.canRunAuthenticatedBackgroundTask()).toBe(false);
  });

  it("does not extend the background deadline when polling or connectivity checks repeat", async () => {
    await startMonitoring();
    await vi.advanceTimersByTimeAsync(30 * 60_000);
    expect(tokenRefresh.canRunAuthenticatedBackgroundTask()).toBe(true);

    window.dispatchEvent(new Event("online"));
    await vi.advanceTimersByTimeAsync(30 * 60_000);
    expect(tokenRefresh.canRunAuthenticatedBackgroundTask()).toBe(false);
  });
});
