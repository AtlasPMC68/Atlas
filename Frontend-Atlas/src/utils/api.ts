import keycloak from "../keycloak";

/**
 * Wrapper around fetch that automatically prepends VITE_API_URL and injects
 * the Keycloak Bearer token as an Authorization header. All other options
 * (method, body, additional headers) are forwarded as-is.
 */
export async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(options.headers);
  if (keycloak.token) {
    headers.set("Authorization", `Bearer ${keycloak.token}`);
  }
  return fetch(`${import.meta.env.VITE_API_URL}${path}`, {
    ...options,
    headers,
  });
}

/** The message a failed response carries (FastAPI's `detail`), or the fallback. */
export async function apiErrorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => ({}));
  const detail = (body as { detail?: unknown })?.detail;
  return typeof detail === "string" && detail ? detail : `${fallback} (${res.status})`;
}
