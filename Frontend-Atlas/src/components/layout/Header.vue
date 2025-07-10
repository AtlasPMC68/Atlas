<template>
  <header class="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between items-center h-16 relative">
        <!-- Logo -->
        <div class="flex items-center">
          <div class="flex-shrink-0 flex items-center">
            <div class="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center mr-3">
              <MapIcon class="h-6 w-6 text-white" />
            </div>
            <h1 class="text-xl font-bold text-gray-900">
              Atlas
            </h1>
          </div>
        </div>

        <!-- Desktop Navigation -->
        <nav class="hidden lg:flex space-x-8 absolute left-1/2 transform -translate-x-1/2">
          <RouterLink 
            to ="/"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors">
            Accueil
          </RouterLink>
          <RouterLink
            to="/demo/upload"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors"
          > Téléversement </RouterLink>
          <RouterLink 
            to="/tableau-de-bord"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors">
            Mes projets
          </RouterLink>
          <a href="#" class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors">
            Explorer
          </a>
          <a href="https://youtu.be/xvFZjo5PgG0?si=u_0AuFzmGPL6cjRC"
            target="_blank"
            rel="noopener"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors">
            À propos
          </a>
        </nav>
        
        <!-- Desktop CTA -->
        <div class="hidden md:flex items-center space-x-4 relative">
          <template v-if="isAuthenticated">
            <div class="relative group">
              <button
                @click="toggleDropdown" 
                class="flex items-center space-x-0 text-gray-700 hover:text-primary-600 focus:outline-none">
                <UserCircleIcon class="h-10 w-10" />
                <ChevronDownIcon class="h-5 w-5" />
              </button>

              <!-- Dropdown menu -->
              <div
                v-show="isDropdownOpen"
                class="absolute right-0 top-full mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg p-4 space-y-4 flex flex-col z-50"
              >
                <RouterLink to="/profil" class="dropdown-item">Mon profil</RouterLink>
                <RouterLink to="/parametres" class="dropdown-item">Paramètres</RouterLink>
                <div class="h-0.5 bg-gray-200 my-1"></div>
                <!--TODO: Ajouter la logique de déconnexion-->
                <RouterLink 
                  to="/connexion"
                  class="dropdown-item text-red-600 hover:text-red-800">
                  Déconnexion
                </RouterLink>
              </div>
            </div>
          </template>

          <template v-else>
            <RouterLink 
              to="/connexion"
              class="btn-secondary text-sm">
              Connexion
            </RouterLink>
            <RouterLink 
              to="/inscription"
              class="btn-primary text-sm">
              S'inscrire
            </RouterLink>
          </template>
        </div>
    </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { MapIcon, UserCircleIcon, ChevronDownIcon } from '@heroicons/vue/24/outline'

const isDropdownOpen = ref(false)

const toggleDropdown = () => {
  isDropdownOpen.value = !isDropdownOpen.value
}

const isAuthenticated = ref(true) // Replace with actual authentication logic
</script>