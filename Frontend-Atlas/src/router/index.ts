import { createRouter, createWebHistory } from 'vue-router';
import Map from '../views/Map.vue';
import Home from '../views/Home.vue';
import Login from '../views/Login.vue';
import TestFileDrop from '../views/TestFileDrop.vue';

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
    path: '/test',
    name: 'TestDrop',
    component: TestFileDrop,
  }
];

export const router = createRouter({
  history: createWebHistory(),
  routes
});
