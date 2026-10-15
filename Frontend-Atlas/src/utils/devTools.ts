// Whether the dev-test tool's pages are offered at all. Mirrors the backend's
// ENABLE_DEV_TOOLS: without it the backend serves none of the routes these
// pages call. On by default for now, for local development.
// TODO: default this to "false" before deploying anywhere, alongside the
// backend's ENABLE_DEV_TOOLS; set VITE_ENABLE_DEV_TOOLS=true locally instead.
export const DEV_TOOLS_ENABLED = ["1", "true", "yes", "on"].includes(
  String(import.meta.env.VITE_ENABLE_DEV_TOOLS ?? "true").trim().toLowerCase(),
);
