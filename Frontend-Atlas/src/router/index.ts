import { createRouter, createWebHistory } from "vue-router";
import Map from "../views/Map.vue";
import Home from "../views/Home.vue";
import ImportView from "../views/import/ImportView.vue";
import Dashboard from "../views/Dashboard.vue";
import About from "../views/About.vue";
import Profile from "../views/Profile.vue";
import Discover from "../views/Discover.vue";
import keycloak from "../keycloak";
import { useCurrentUser } from "../composables/useCurrentUser";
import { DEV_TOOLS_ENABLED } from "../utils/devTools";

// The dev-test tool's pages, registered only when the dev tools are enabled.
// Loaded on demand, so they stay out of the main bundle.
const devTestRoutes = [
  {
    path: "/upload-test/:mapId",
    component: ImportView,
    meta: { requiresAuth: true, importMode: "dev-test" },
  },
  {
    path: "/tests",
    component: () => import("../views/dev/TestBrowser.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/test-editor/:mapId",
    component: () => import("../views/dev/TestEditor.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/test-editor/:mapId/case/:caseId",
    component: () => import("../views/dev/TestCaseResult.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/test-creation",
    component: () => import("../views/dev/TestCreation.vue"),
    meta: { requiresAuth: true },
  },
];

const routes = [
  ...(DEV_TOOLS_ENABLED ? devTestRoutes : []),
  { path: "/", component: Home },
  {
    path: "/televersement/:mapId",
    component: ImportView,
    meta: { requiresAuth: true },
  },
  {
    path: "/tableau-de-bord",
    component: Dashboard,
    meta: { requiresAuth: true },
  },
  {
    path: "/projets-publiques",
    component: Discover,
  },
  { path: "/profil", component: Profile, meta: { requiresAuth: true } },
  { path: "/connexion", component: Home }, // Dummy route
  { path: "/inscription", component: Home }, // Dummy route
  { path: "/projet/:projectId", component: Map },
  { path: "/a-propos", component: About },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(_, __, savedPosition) {
    if (savedPosition) return savedPosition;
    return { top: 0 };
  },
});

let keycloakReady: Promise<void> | null = null;

if (!keycloakReady) {
  keycloakReady = new Promise((resolve) => {
    const checkReady = () => {
      if ((keycloak as any).didInitialize) {
        setTimeout(() => {
          resolve();
        }, 500);
      } else {
        setTimeout(checkReady, 50);
      }
    };
    checkReady();
  });
}

router.beforeEach(async (to) => {
  if (!to.matched.some((r) => r.meta.requiresAuth)) return true;
  await keycloakReady;

  if (!keycloak.authenticated) {
    keycloak.login({
      redirectUri: window.location.origin + to.fullPath,
    });
    return false;
  }

  try {
    const refreshed = await keycloak.updateToken(30);
    if (!refreshed && keycloak.isTokenExpired()) {
      keycloak.login({
        redirectUri: window.location.origin + to.fullPath,
      });
      return false;
    }

    const { fetchCurrentUser } = useCurrentUser();
    await fetchCurrentUser();

    return true;
  } catch (err) {
    keycloak.login({
      redirectUri: window.location.origin + to.fullPath,
    });
    return false;
  }
});

export default router;
