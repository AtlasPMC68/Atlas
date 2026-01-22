import { createRouter, createWebHistory } from "vue-router";
import Map from "../views/Map.vue";
import Home from "../views/Home.vue";
import ImportView from "../views/import/ImportView.vue";
import Dashboard from "../views/Dashboard.vue";
import Profile from "../views/Profile.vue";
import Settings from "../views/Settings.vue";
import Discover from "../views/Discover.vue";
import keycloak from "../keycloak";

const routes = [
  { path: "/", component: Home },
  { path: "/demo", component: Map, meta: { requiresAuth: true } },
  { path: "/demo/upload", component: ImportView, meta: { requiresAuth: true } },
  { path: "/tableau-de-bord", component: Dashboard, meta: { requiresAuth: true } },
  { path: "/projets-publiques", component: Discover, meta: { requiresAuth: true } },
  { path: "/profil", component: Profile, meta: { requiresAuth: true } },
  { path: "/parametres", component: Settings, meta: { requiresAuth: true } },
  { path: "/connexion", component: Home }, // Dummy route
  { path: "/inscription", component: Home }, // Dummy route
  { path: "/maps/:mapId", component: Map, meta: { requiresAuth: true } },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
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
  if (!to.matched.some(r => r.meta.requiresAuth)) return true;
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
    
    return true;
  } catch (err) {
    keycloak.login({
      redirectUri: window.location.origin + to.fullPath,
    });
    return false;
  }
});

export default router;