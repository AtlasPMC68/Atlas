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
