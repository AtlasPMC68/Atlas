import { createRouter, createWebHistory } from 'vue-router';
import Map from '../views/Map.vue';
import Home from '../views/Home.vue';
import Login from '../views/Login.vue';
import ImportView from '../views/import/ImportView.vue';
import Signin from '../views/Signin.vue';
import Dashboard from '../views/Dashboard.vue';
import Profile from '../views/Profile.vue';
import Settings from '../views/Settings.vue';

const routes = [
  {
    path: '/',
    component: Home,
  },
  {
    path: '/demo',
    component: Map,
  },
  {
    path: '/connexion',
    component: Login,
  },
  {
    path: '/demo/upload',
    component: ImportView,
    meta: { requiresAuth: true }
  },
  {
    path: '/inscription',
    component: Signin,
  },
  {
    path: '/tableau-de-bord',
    component: Dashboard,
    meta: { requiresAuth: true }
  },
  {
    path: '/profil',
    component: Profile,
    meta: { requiresAuth: true }
  },
  {
    path: '/parametres',
    component: Settings,
    meta: { requiresAuth: true }
  }
];

export const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)

  if (requiresAuth && !token) {
    next('/connexion')  // 🔒 Pas connecté → redirection
  } else {
    next() // ✅ Autorisé
  }
})

export default router;
