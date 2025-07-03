import { createRouter, createWebHistory } from 'vue-router';
import App from '../App.vue';
import Map from '../views/Map.vue';

const routes = [
  {
    path: '/',
    component: App,
  },
  {
    path: '/demo',
    component: Map,
  }
];

export const router = createRouter({
  history: createWebHistory(),
  routes
});
