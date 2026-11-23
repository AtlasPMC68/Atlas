# Vue 3 + TypeScript + Vite

This template should help get you started developing with Vue 3 and TypeScript in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about the recommended Project Setup and IDE Support in the [Vue Docs TypeScript Guide](https://vuejs.org/guide/typescript/overview.html#project-setup).

## Authentication token renewal

Authenticated backend requests use `apiFetch`, which waits for Keycloak's
`updateToken(30)` before reading the Bearer token. Navigation and editor activity
share the same pending renewal. Failed renewal blocks the request without
automatically replaying writes or redirecting on a transient network error.

After initialization, `startTokenRefresh` checks at most every 30 seconds while
the user has interacted in the last minute. Visible tab focus/resume also checks
the token. An `online` event retries only for a recently active user; it does not
count as user activity. Guests do not trigger renewal.

Import polling pauses in hidden tabs and after one hour without user interaction,
then resumes on interaction. Polling never resets that activity deadline. The
backend import continues while polling is paused. Keycloak's SSO idle timeout is
measured from the last renewal, not from the last editor interaction.

`../keycloak/setdata.sh` configures five-minute access tokens, a one-hour SSO idle
timeout and a 24-hour maximum session. Apply the frontend changes before applying
the Keycloak settings (the configuration script runs at Keycloak startup).
Expired-session banners and persistent editor drafts are separate work.
