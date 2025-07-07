import { createRouter, createWebHistory } from 'vue-router';
import Map from '../views/Map.vue';
import Home from '../views/Home.vue';
import Login from '../views/Login.vue';
import Signin from '../views/Signin.vue';

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
    path: '/inscription',
    component: Signin,
  }
];

export const router = createRouter({
  history: createWebHistory(),
  routes
});
