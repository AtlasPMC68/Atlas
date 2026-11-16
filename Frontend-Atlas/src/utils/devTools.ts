// Whether the dev-test tool's pages are offered at all. Mirrors the backend's
// ENABLE_DEV_TOOLS: without it the backend serves none of the routes these
// pages call. Off unless enabled: docker-compose.yml sets VITE_ENABLE_DEV_TOOLS
// for local development, production builds set it to false.
export const DEV_TOOLS_ENABLED = ["1", "true", "yes", "on"].includes(
  String(import.meta.env.VITE_ENABLE_DEV_TOOLS ?? "false").trim().toLowerCase(),
);
