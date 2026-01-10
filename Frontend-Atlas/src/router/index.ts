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
  {
    path: "/tableau-de-bord",
    component: Dashboard,
    meta: { requiresAuth: true },
  },
  {
    path: "/projets-publiques",
    component: Discover,
    meta: { requiresAuth: true },
  },
  { path: "/profil", component: Profile, meta: { requiresAuth: true } },
  { path: "/parametres", component: Settings, meta: { requiresAuth: true } },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition;
    return { top: 0 };
  },
});

router.beforeEach(async (to, from, next) => {
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth);

  if (!keycloak.didInitialize) {
    await new Promise((resolve) => {
      const checkInit = () => {
        if (keycloak.didInitialize) resolve(void 0);
        else setTimeout(checkInit, 100);
      };
      checkInit();
    });
  }

  if (!requiresAuth) {
    return next();
  }

  if (!keycloak.authenticated) {
    return keycloak.login({
      redirectUri: window.location.origin + to.fullPath,
    });
  }

  try {
    const res = await fetch("http://localhost:8000/me", {
      headers: { Authorization: `Bearer ${keycloak.token}` },
    });

    if (!res.ok) {
      await keycloak.logout();
      return keycloak.login({
        redirectUri: window.location.origin + to.fullPath,
      });
    }

    next();
  } catch (err) {
    console.error("Erreur vérification token :", err);
    await keycloak.logout();
    return keycloak.login({
      redirectUri: window.location.origin + to.fullPath,
    });
  }
});

export default router;
