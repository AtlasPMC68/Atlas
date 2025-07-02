<template>
  <nav class="bg-white border-b border-gray-200">
    <div class="max-w-7xl mx-auto px-6">
      <div class="flex justify-between items-center h-16">
        <!-- Logo -->
        <router-link to="/dashboard" class="flex items-center space-x-2">
          <MapIcon class="h-8 w-8 text-primary-600" />
          <span class="text-xl font-bold text-gray-900">CardMaps</span>
        </router-link>

        <!-- Navigation Links -->
        <div class="hidden md:flex items-center space-x-8">
          <router-link 
            to="/dashboard" 
            class="text-gray-600 hover:text-gray-900 font-medium"
            :class="{ 'text-primary-600': $route.name === 'Dashboard' }"
          >
            Mes projets
          </router-link>
          <a href="#" class="text-gray-600 hover:text-gray-900 font-medium">
            Modèles
          </a>
          <a href="#" class="text-gray-600 hover:text-gray-900 font-medium">
            Communauté
          </a>
        </div>

        <!-- User Menu -->
        <div class="flex items-center space-x-4">
          <button class="text-gray-600 hover:text-gray-900">
            <BellIcon class="h-6 w-6" />
          </button>
          
          <div class="relative" ref="dropdown">
            <button
              @click="toggleDropdown"
              class="flex items-center space-x-2 text-gray-700 hover:text-gray-900"
            >
              <div class="w-8 h-8 bg-primary-100 rounded-full flex items-center justify-center">
                <UserIcon class="h-5 w-5 text-primary-600" />
              </div>
              <span class="font-medium">{{ user.name || 'Utilisateur' }}</span>
              <ChevronDownIcon class="h-4 w-4" />
            </button>
            
            <div
              v-if="showDropdown"
              class="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg border border-gray-200 z-50"
            >
              <div class="py-1">
                <a href="#" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                  Mon profil
                </a>
                <a href="#" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                  Paramètres
                </a>
                <hr class="my-1">
                <button
                  @click="handleLogout"
                  class="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  Déconnexion
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { MapIcon, BellIcon, UserIcon, ChevronDownIcon } from '@heroicons/vue/24/outline'
import { user, logout } from '../stores/auth'

const router = useRouter()
const showDropdown = ref(false)
const dropdown = ref<HTMLElement>()

function toggleDropdown() {
  showDropdown.value = !showDropdown.value
}

function handleLogout() {
  logout()
  router.push('/')
}

function handleClickOutside(event: Event) {
  if (dropdown.value && !dropdown.value.contains(event.target as Node)) {
    showDropdown.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>