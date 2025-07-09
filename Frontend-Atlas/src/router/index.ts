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
  },
  {
    path: '/inscription',
    component: Signin,
  },
  {
    path: '/tableau-de-bord',
    component: Dashboard,
  },
  {
    path: '/profil',
    component: Profile,
  },
  {
    path: '/parametres',
    component: Settings,
  }
];

export const router = createRouter({
  history: createWebHistory(),
  routes
});
