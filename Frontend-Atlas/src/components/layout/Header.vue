<template>
  <header class="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between items-center h-16 relative">
        <!-- Logo -->
        <RouterLink to="/" class="flex items-center">
          <div class="flex items-center">
            <div class="flex-shrink-0 flex items-center">
              <div
                class="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center mr-3"
              >
                <MapIcon class="h-6 w-6 text-white" />
              </div>
              <h1 class="text-xl font-bold text-gray-900">Atlas</h1>
            </div>
          </div>
        </RouterLink>

        <!-- Desktop Navigation -->
        <nav
          class="hidden lg:flex space-x-8 absolute left-1/2 transform -translate-x-1/2"
        >
          <RouterLink
            to="/"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors"
          >
            Accueil
          </RouterLink>
          <RouterLink
            to="/tableau-de-bord"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors"
          >
            Mes projets
          </RouterLink>
          <RouterLink
            to="/projets-publiques"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors"
          >
            Explorer
          </RouterLink>
          <RouterLink
            to="/a-propos"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors"
          >
            À propos
          </RouterLink>
        </nav>

        <!-- Desktop CTA -->
        <div class="hidden md:flex items-center space-x-4 relative">
          <template v-if="isAuthenticated">
            <div
              class="relative group"
              @mouseenter="openDropdown"
              @mouseleave="closeDropdown"
            >
              <RouterLink
                to="/profil"
                class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors"
              >
                <UserCircleIcon class="h-8 w-8" />
              </RouterLink>
            </div>
          </template>

          <template v-else>
            <button @click="login" class="btn-secondary text-sm">
              Connexion
            </button>
            <button @click="register" class="btn-primary text-sm">
              S'inscrire
            </button>
          </template>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import {
  MapIcon,
  UserCircleIcon,
  ChevronDownIcon,
} from "@heroicons/vue/24/outline";
import { useRouter } from "vue-router";
import keycloak from "../../keycloak";

const isDropdownOpen = ref(false);
const router = useRouter();

let closeTimeout: ReturnType<typeof setTimeout> | null = null;

const openDropdown = () => {
  if (closeTimeout) {
    clearTimeout(closeTimeout);
    closeTimeout = null;
  }
  isDropdownOpen.value = true;
};

const closeDropdown = () => {
  closeTimeout = setTimeout(() => {
    isDropdownOpen.value = false;
  }, 100);
};

const isAuthenticated = computed(() => {
  return keycloak.authenticated;
});

const login = () => {
  (keycloak as any).loginToAtlas({
    redirectUri: window.location.origin,
  });
};

const register = () => {
  keycloak.register({
    redirectUri: window.location.origin,
  });
};
</script>
