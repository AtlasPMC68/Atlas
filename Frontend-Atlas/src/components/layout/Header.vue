<script setup lang="ts">
import { ref } from 'vue'
import { MapIcon } from '@heroicons/vue/24/outline'

const isMenuOpen = ref(false)

const toggleMenu = () => {
  isMenuOpen.value = !isMenuOpen.value
}
</script>

<template>
  <header class="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between items-center h-16">
        <!-- Logo -->
        <div class="flex items-center">
          <div class="flex-shrink-0 flex items-center">
            <div class="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center mr-3">
              <MapIcon class="h-6 w-6 text-white" />
            </div>
            <h1 class="text-xl font-bold text-gray-900">
              Plateforme Cartes
            </h1>
          </div>
        </div>

        <!-- Desktop Navigation -->
        <nav class="hidden md:flex space-x-8">
          <a href="#" class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors">
            Accueil
          </a>
          <router-link
            to="/demo/upload"
            class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors"
          > Upload </router-link>
          <a href="#" class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors">
            Galerie
          </a>
          <a href="#" class="text-gray-700 hover:text-primary-600 px-3 py-2 text-sm font-medium transition-colors">
            À propos
          </a>
        </nav>

        <!-- Desktop CTA -->
        <div class="hidden md:flex items-center space-x-4">
          <RouterLink 
            to="/connexion"
            class="btn-secondary text-sm">
            Connexion
          </RouterLink>
          <button class="btn-primary text-sm">
            S'inscrire
          </button>
        </div>

        <!-- Mobile menu button -->
        <div class="md:hidden">
          <button
            @click="toggleMenu"
            class="text-gray-700 hover:text-primary-600 focus:outline-none focus:text-primary-600"
          >
            <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path v-if="!isMenuOpen" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Mobile Navigation -->
      <div v-if="isMenuOpen" class="md:hidden py-4 border-t border-gray-200">
        <div class="flex flex-col space-y-2">
          <a href="#" class="text-gray-700 hover:text-primary-600 px-3 py-2 text-base font-medium">
            Accueil
          </a>
          <a href="#" class="text-gray-700 hover:text-primary-600 px-3 py-2 text-base font-medium">
            Upload
          </a>
          <a href="#" class="text-gray-700 hover:text-primary-600 px-3 py-2 text-base font-medium">
            Galerie
          </a>
          <a href="#" class="text-gray-700 hover:text-primary-600 px-3 py-2 text-base font-medium">
            À propos
          </a>
          <div class="pt-4 flex flex-col space-y-2">
            <button class="btn-secondary w-full justify-center">
              Connexion
            </button>
            <button class="btn-primary w-full justify-center">
              S'inscrire
            </button>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>