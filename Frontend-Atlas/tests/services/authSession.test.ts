import { beforeEach, describe, expect, it, vi } from "vitest";

const keycloak = vi.hoisted(() => ({
  authenticated: false,
  token: undefined as string | undefined,
  subject: undefined as string | undefined,
  tokenParsed: undefined as { sub: string } | undefined,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  onAuthSuccess: undefined as (() => void) | undefined,
  onAuthRefreshSuccess: undefined as (() => void) | undefined,
  onAuthRefreshError: undefined as (() => void) | undefined,
  onAuthLogout: undefined as (() => void) | undefined,
}));
vi.mock("../../src/keycloak", () => ({ default: keycloak }));

let auth: typeof import("../../src/services/authSession");

beforeEach(async () => {
  vi.resetModules();
  vi.resetAllMocks();
  keycloak.authenticated = false;
  keycloak.token = undefined;
  keycloak.subject = undefined;
  keycloak.tokenParsed = undefined;
  auth = await import("../../src/services/authSession");
  auth.initializeAuthSession();
});

function connect() {
  keycloak.authenticated = true;
  keycloak.token = "access-token";
  keycloak.subject = "user-1";
  keycloak.onAuthSuccess?.();
}

describe("session state and protected authentication redirects", () => {
  it("reacts to SDK logout while retaining the identity needed to protect a draft", () => {
    connect();
    expect(auth.sessionState.status).toBe("authenticated");
    keycloak.authenticated = false;
    keycloak.token = undefined;
    keycloak.subject = undefined;
    keycloak.onAuthLogout?.();

    expect(auth.sessionState.status).toBe("reauth-required");
    expect(auth.sessionState.subject).toBe("user-1");
    expect(keycloak.login).not.toHaveBeenCalled();
  });

  it("distinguishes a transient refresh failure and recovers without redirecting", () => {
    connect();
    keycloak.onAuthRefreshError?.();
    expect(auth.sessionState.status).toBe("unavailable");
    expect(auth.sessionState.subject).toBe("user-1");

    keycloak.onAuthRefreshSuccess?.();
    expect(auth.sessionState.status).toBe("authenticated");
    expect(auth.sessionState.message).toBe("");
    expect(keycloak.login).not.toHaveBeenCalled();
  });

  it("marks a refresh that loses its session as requiring authentication", () => {
    connect();
    keycloak.authenticated = false;
    keycloak.token = undefined;
    keycloak.onAuthRefreshError?.();
    expect(auth.sessionState.status).toBe("reauth-required");
  });

  it("waits for durable draft preservation and returns to the editor instead of the requested route", async () => {
    let finishPreserving!: (url: string) => void;
    const preserve = vi.fn(() => new Promise<string>((resolve) => { finishPreserving = resolve; }));
    auth.registerAuthRedirectHandler(preserve);

    const redirect = auth.reconnect({ intent: "save", redirectUri: "https://atlas.example/profile" });
    expect(preserve).toHaveBeenCalledWith("save");
    expect(keycloak.login).not.toHaveBeenCalled();

    finishPreserving("https://atlas.example/projet/project-1");
    await redirect;
    expect(keycloak.login).toHaveBeenCalledWith({ redirectUri: "https://atlas.example/projet/project-1" });
  });

  it("blocks login when the draft cannot be stored and exposes the reason", async () => {
    auth.registerAuthRedirectHandler(async () => { throw new Error("Stockage local indisponible."); });

    await expect(auth.reconnect()).rejects.toThrow("Stockage local indisponible.");
    expect(keycloak.login).not.toHaveBeenCalled();
    expect(auth.sessionState.redirectError).toBe("Stockage local indisponible.");
  });

  it("removes only the registered editor handler when it unmounts", async () => {
    const first = vi.fn().mockResolvedValue("https://atlas.example/first");
    const second = vi.fn().mockResolvedValue("https://atlas.example/second");
    const removeFirst = auth.registerAuthRedirectHandler(first);
    const removeSecond = auth.registerAuthRedirectHandler(second);
    removeFirst();
    await auth.reconnect();
    expect(second).toHaveBeenCalledOnce();
    expect(first).not.toHaveBeenCalled();

    removeSecond();
    await auth.reconnect({ redirectUri: "https://atlas.example/profile" });
    expect(keycloak.login).toHaveBeenLastCalledWith({ redirectUri: "https://atlas.example/profile" });
  });

  it("protects explicit registration and logout with the same preservation hook", async () => {
    const preserve = vi.fn().mockRejectedValue(new Error("Draft unavailable"));
    auth.registerAuthRedirectHandler(preserve);
    await expect(auth.registerAccount()).rejects.toThrow("Draft unavailable");
    await expect(auth.logoutFromAtlas()).rejects.toThrow("Draft unavailable");
    expect(keycloak.register).not.toHaveBeenCalled();
    expect(keycloak.logout).not.toHaveBeenCalled();
  });

  it("shows an initialization failure without treating it as a confirmed expired session", () => {
    auth.reportInitializationFailure();
    expect(auth.sessionState.status).toBe("unavailable");
    expect(auth.sessionState.subject).toBeNull();
    expect(keycloak.login).not.toHaveBeenCalled();
  });
});
