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

        <!-- Authentication Actions (Always visible) -->
        <div class="flex items-center space-x-3">
          <template v-if="isAuthenticated">
            <RouterLink
              to="/profil"
              class="text-gray-700 hover:text-primary-600 px-2 py-1 text-sm font-medium rounded-lg hover:bg-gray-100 transition-colors flex items-center"
              title="Mon compte / Profil"
            >
              <UserCircleIcon class="h-8 w-8" />
            </RouterLink>

            <button
              type="button"
              @click="logout"
              class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg shadow-sm hover:bg-gray-50 hover:text-gray-900 transition-colors"
              title="Se déconnecter"
            >
              Déconnexion
            </button>
          </template>

          <template v-else>
            <button
              type="button"
              @click="login"
              class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg shadow-sm hover:bg-gray-50 hover:text-gray-900 transition-colors"
              title="Se connecter"
            >
              Connexion
            </button>
            <button
              type="button"
              @click="register"
              class="px-4 py-2 text-sm font-medium text-white bg-primary-600 border border-transparent rounded-lg shadow-sm hover:bg-primary-700 transition-colors"
              title="Créer un compte"
            >
              S'inscrire
            </button>
          </template>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { MapIcon, UserCircleIcon } from "@heroicons/vue/24/outline";
import keycloak from "../../keycloak";
import { useCurrentUser } from "../../composables/useCurrentUser";

const { currentUser, isAuthenticated, fetchCurrentUser } = useCurrentUser();

onMounted(() => {
  if (keycloak.authenticated && !currentUser.value) {
    void fetchCurrentUser();
  }
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

const logout = async () => {
  await keycloak.logout({
    redirectUri: window.location.origin,
  });
};
</script>
