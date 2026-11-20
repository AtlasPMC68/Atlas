import keycloak from "../keycloak";

let refreshPromise: Promise<boolean> | null = null;
let refreshPromiseMinValidity: number | null = null;

async function getOrRefreshKeycloakToken(minValidity: number): Promise<boolean> {
  if (!keycloak.authenticated) return false;
  if (minValidity < 0 && refreshPromiseMinValidity !== null && refreshPromiseMinValidity >= 0) {
    refreshPromise = null;
  }
  if (!refreshPromise) {
    refreshPromiseMinValidity = minValidity;
    refreshPromise = keycloak
      .updateToken(minValidity)
      .finally(() => {
        refreshPromise = null;
        refreshPromiseMinValidity = null;
      });
  }
  return refreshPromise;
}

/**
 * Wrapper around fetch that automatically prepends VITE_API_URL and injects
 * the Keycloak Bearer token as an Authorization header. All other options
 * (method, body, additional headers) are forwarded as-is.
 */
export async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  // Try refreshing token before request if it's about to expire
  if (keycloak.authenticated) {
    try {
      await getOrRefreshKeycloakToken(30);
    } catch {
      console.warn("Could not refresh token before API call; session may be expired.");
      (keycloak as any).authenticated = false;
      keycloak.clearToken();
    }
  }

  const headers = new Headers(options.headers);
  if (keycloak.token) {
    headers.set("Authorization", `Bearer ${keycloak.token}`);
  }

  const response = await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
    ...options,
    headers,
  });

  // If 401 Unauthorized, token was rejected by backend
  if (response.status === 401 && keycloak.authenticated) {
    try {
      const refreshed = await getOrRefreshKeycloakToken(-1);
      if (refreshed && keycloak.token) {
        // Retry request with newly refreshed token
        const retryHeaders = new Headers(options.headers);
        retryHeaders.set("Authorization", `Bearer ${keycloak.token}`);
        return await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
          ...options,
          headers: retryHeaders,
        });
      }
    } catch {
      console.warn("Session expired on 401 response; clearing local token.");
      (keycloak as any).authenticated = false;
      keycloak.clearToken();
    }
  }

  return response;
}

/** The message a failed response carries (FastAPI's `detail`), or the fallback. */
export async function apiErrorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => ({}));
  const detail = (body as { detail?: unknown })?.detail;
  return typeof detail === "string" && detail ? detail : `${fallback} (${res.status})`;
}
