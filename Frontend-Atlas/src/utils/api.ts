import { getValidAccessToken } from "../services/tokenRefresh";
import { AuthRequiredError, requireReauthentication } from "../services/authSession";

export type ApiRequestOptions = RequestInit & { auth?: "required" | "optional" };

/**
 * Wrapper around fetch that automatically prepends VITE_API_URL and injects
 * a renewed Keycloak Bearer token as an Authorization header. All other options
 * (method, body, additional headers) are forwarded as-is.
 */
export async function apiFetch(
  path: string,
  options: ApiRequestOptions = {},
): Promise<Response> {
  const { auth = "optional", ...requestOptions } = options;
  const token = await getValidAccessToken();
  if (auth === "required" && !token) {
    requireReauthentication();
    throw new AuthRequiredError();
  }
  const headers = new Headers(options.headers);
  // This wrapper owns authentication, including removing a stale caller token
  // after logout. Read the token only after renewal has completed.
  headers.delete("Authorization");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
    ...requestOptions,
    headers,
  });
  if (response.status === 401 && (token || auth === "required")) {
    requireReauthentication();
    throw new AuthRequiredError();
  }
  return response;
}

/** The message a failed response carries (FastAPI's `detail`), or the fallback. */
export async function apiErrorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => ({}));
  const detail = (body as { detail?: unknown })?.detail;
  return typeof detail === "string" && detail ? detail : `${fallback} (${res.status})`;
}
