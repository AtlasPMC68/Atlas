import keycloak from "../keycloak";
import {
  AuthRequiredError,
  reportRefreshFailure,
  sessionState,
  syncAuthenticatedSession,
} from "./authSession";

const MIN_VALIDITY_SECONDS = 30;
const CHECK_INTERVAL_MS = 30_000;
const RECENT_ACTIVITY_MS = 60_000;
// Watching a long-running import is useful work even without constant input.
// Polling never resets this deadline, and hidden tabs pause immediately.
const BACKGROUND_TASK_IDLE_MS = 60 * 60_000;

let pendingRefresh: Promise<string | undefined> | null = null;
let stopMonitoring: (() => void) | null = null;
let lastActivityAt = 0;

/** Share the refresh between navigation, API requests and editor activity. */
export function getValidAccessToken(): Promise<string | undefined> {
  if (pendingRefresh) return pendingRefresh;
  if (!keycloak.authenticated) return Promise.resolve(undefined);
  if (sessionState.status === "reauth-required") return Promise.reject(new AuthRequiredError());

  pendingRefresh = (async () => {
    // Keycloak only contacts its token endpoint when renewal is necessary.
    // Let failures reach the caller: do not send an expired token or redirect
    // away from unsaved work because the network is temporarily unavailable.
    try {
      await keycloak.updateToken(MIN_VALIDITY_SECONDS);
      if (!keycloak.authenticated || !keycloak.token || keycloak.isTokenExpired()) {
        throw new Error("La session ne permet plus d'authentifier la requête.");
      }
      syncAuthenticatedSession();
      return keycloak.token;
    } catch (error) {
      reportRefreshFailure();
      if (sessionState.status === "reauth-required") throw new AuthRequiredError();
      throw error;
    }
  })().finally(() => {
    pendingRefresh = null;
  });

  return pendingRefresh;
}

function hasRecentActivity(): boolean {
  return document.visibilityState !== "hidden" &&
    Date.now() - lastActivityAt < RECENT_ACTIVITY_MS;
}

/** Give visible imports a bounded window to finish without perpetual renewal. */
export function canRunAuthenticatedBackgroundTask(): boolean {
  if (!stopMonitoring) return true;
  if (document.visibilityState === "hidden" || !keycloak.authenticated || sessionState.status === "reauth-required") return false;
  return Date.now() - lastActivityAt < BACKGROUND_TASK_IDLE_MS;
}

/** Start once after Keycloak initialization; returns cleanup for HMR/tests. */
export function startTokenRefresh(): () => void {
  if (stopMonitoring) return stopMonitoring;

  lastActivityAt = Date.now();
  let lastCheckAt = -Infinity;

  const check = (immediate = false) => {
    if (!hasRecentActivity() || !keycloak.authenticated || sessionState.status === "reauth-required") return;
    const now = Date.now();
    if (!immediate && now - lastCheckAt < CHECK_INTERVAL_MS) return;
    lastCheckAt = now;
    void getValidAccessToken().catch(() => {
      // The session banner explains the failure. Keep the editor in place;
      // another interaction or the banner can retry a temporary failure.
    });
  };

  const onActivity = () => {
    if (document.visibilityState === "hidden") return;
    lastActivityAt = Date.now();
    check();
  };
  const onPointerMove = (event: PointerEvent) => {
    if (event.buttons) onActivity();
  };
  const onResume = () => {
    if (document.visibilityState === "hidden") return;
    lastActivityAt = Date.now();
    check(true);
  };
  const onOnline = () => check(true);

  // Capture also sees events stopped by the map editor. Mere mouse movement
  // and background API traffic do not count as editing activity.
  const activityEvents = ["pointerdown", "keydown", "wheel", "input"] as const;
  const listenerOptions = { capture: true, passive: true };
  activityEvents.forEach((event) => document.addEventListener(event, onActivity, listenerOptions));
  document.addEventListener("pointermove", onPointerMove, listenerOptions);
  document.addEventListener("visibilitychange", onResume);
  window.addEventListener("focus", onResume);
  window.addEventListener("online", onOnline);
  window.addEventListener("pageshow", onResume);
  const timer = window.setInterval(check, CHECK_INTERVAL_MS);

  const stop = () => {
    window.clearInterval(timer);
    activityEvents.forEach((event) => document.removeEventListener(event, onActivity, true));
    document.removeEventListener("pointermove", onPointerMove, true);
    document.removeEventListener("visibilitychange", onResume);
    window.removeEventListener("focus", onResume);
    window.removeEventListener("online", onOnline);
    window.removeEventListener("pageshow", onResume);
    if (stopMonitoring === stop) stopMonitoring = null;
  };
  stopMonitoring = stop;
  check();
  return stop;
}
