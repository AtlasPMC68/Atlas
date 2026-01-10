import { createRouter, createWebHistory } from "vue-router";
import Map from "../views/Map.vue";
import Home from "../views/Home.vue";
import Login from "../views/Login.vue";
import ImportView from "../views/import/ImportView.vue";
import Signin from "../views/Signin.vue";
import Dashboard from "../views/Dashboard.vue";
import Profile from "../views/Profile.vue";
import Settings from "../views/Settings.vue";
import Discover from "../views/Discover.vue";

const routes = [
  {
    path: "/",
    component: Home,
  },
  {
    path: "/demo",
    component: Map,
  },
  {
    path: "/connexion",
    component: Login,
  },
  {
    path: "/demo/upload",
    component: ImportView,
    meta: { requiresAuth: true },
  },
  {
    path: "/inscription",
    component: Signin,
  },
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
  {
    path: "/profil",
    component: Profile,
    meta: { requiresAuth: true },
  },
  {
    path: "/parametres",
    component: Settings,
    meta: { requiresAuth: true },
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    } else {
      return { top: 0 };
    }
  },
});

router.beforeEach(async (to, from, next) => {
  const token = localStorage.getItem("access_token");
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth);
  const guestOnly = ["/connexion", "/inscription"];

  if (!requiresAuth) {
    if (token && (to.path === "/connexion" || to.path === "/inscription")) {
      return next("/tableau-de-bord");
    }
    return next();
  }

  if (!token) {
    return next("/connexion");
  }

  try {
    const res = await fetch("http://localhost:8000/me", {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (res.ok) {
      if (guestOnly.includes(to.path)) {
        return next("/tableau-de-bord");
      } else {
        next();
      }
    } else {
      localStorage.removeItem("access_token");
      next("/connexion");
    }
  } catch (err) {
    console.error("Token verification failed:", err);
    localStorage.removeItem("access_token");
    next("/connexion");
  }
});

export default router;
