<template>
  <div class="min-h-screen bg-gradient-to-br from-primary-50 to-secondary-50">
    <!-- Navigation -->
    <nav class="px-6 py-4">
      <div class="max-w-7xl mx-auto flex justify-between items-center">
        <div class="flex items-center space-x-2">
          <MapIcon class="h-8 w-8 text-primary-600" />
          <span class="text-xl font-bold text-gray-900">CardMaps</span>
        </div>
        <div class="flex items-center space-x-4">
          <router-link to="/login" class="text-gray-600 hover:text-gray-900 font-medium">
            Connexion
          </router-link>
          <router-link to="/login" class="btn-primary">
            Créer un compte
          </router-link>
        </div>
      </div>
    </nav>

    <!-- Hero Section -->
    <section class="px-6 py-20">
      <div class="max-w-4xl mx-auto text-center">
        <h1 class="text-5xl font-bold text-gray-900 mb-6 leading-tight">
          Créez des cartes
          <span class="text-primary-600">interactives</span>
          exceptionnelles
        </h1>
        <p class="text-xl text-gray-600 mb-12 max-w-2xl mx-auto leading-relaxed">
          Concevez, personnalisez et partagez des cartes interactives professionnelles 
          avec nos outils intuitifs et notre interface moderne.
        </p>
        <div class="flex flex-col sm:flex-row gap-4 justify-center">
          <router-link to="/login" class="btn-primary text-lg px-8 py-4">
            Commencer gratuitement
          </router-link>
          <button class="btn-secondary text-lg px-8 py-4" @click="scrollToFeatures">
            Découvrir les fonctionnalités
          </button>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section ref="featuresSection" class="px-6 py-20 bg-white">
      <div class="max-w-6xl mx-auto">
        <div class="text-center mb-16">
          <h2 class="text-3xl font-bold text-gray-900 mb-4">
            Tout ce dont vous avez besoin
          </h2>
          <p class="text-lg text-gray-600 max-w-2xl mx-auto">
            Des outils professionnels pour créer des cartes interactives qui captivent votre audience.
          </p>
        </div>
        
        <div class="grid md:grid-cols-3 gap-8">
          <div class="text-center p-6">
            <div class="bg-primary-100 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
              <PencilIcon class="h-8 w-8 text-primary-600" />
            </div>
            <h3 class="text-xl font-semibold text-gray-900 mb-3">Éditeur intuitif</h3>
            <p class="text-gray-600">
              Interface drag-and-drop simple avec tous les outils nécessaires pour créer rapidement.
            </p>
          </div>
          
          <div class="text-center p-6">
            <div class="bg-secondary-100 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
              <ShareIcon class="h-8 w-8 text-secondary-600" />
            </div>
            <h3 class="text-xl font-semibold text-gray-900 mb-3">Partage facile</h3>
            <p class="text-gray-600">
              Partagez vos créations instantanément avec des liens personnalisables et sécurisés.
            </p>
          </div>
          
          <div class="text-center p-6">
            <div class="bg-accent-100 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
              <ChartBarIcon class="h-8 w-8 text-accent-600" />
            </div>
            <h3 class="text-xl font-semibold text-gray-900 mb-3">Analytics avancées</h3>
            <p class="text-gray-600">
              Suivez l'engagement et les interactions de vos cartes avec des statistiques détaillées.
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="px-6 py-20 bg-primary-600">
      <div class="max-w-4xl mx-auto text-center">
        <h2 class="text-3xl font-bold text-white mb-6">
          Prêt à créer votre première carte ?
        </h2>
        <p class="text-xl text-primary-100 mb-8">
          Rejoignez des milliers de créateurs qui utilisent CardMaps pour leurs projets.
        </p>
        <div class="flex flex-col sm:flex-row gap-4 justify-center">
          <router-link to="/login" class="bg-white text-primary-600 hover:bg-gray-50 px-8 py-4 rounded-lg font-semibold text-lg transition-colors duration-200">
            Créer un compte gratuit
          </router-link>
          <router-link to="/dashboard" class="border-2 border-white text-white hover:bg-white hover:text-primary-600 px-8 py-4 rounded-lg font-semibold text-lg transition-colors duration-200">
            Explorer les cartes
          </router-link>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="px-6 py-12 bg-gray-900">
      <div class="max-w-6xl mx-auto text-center">
        <div class="flex items-center justify-center space-x-2 mb-4">
          <MapIcon class="h-6 w-6 text-primary-400" />
          <span class="text-lg font-bold text-white">CardMaps</span>
        </div>
        <p class="text-gray-400">
          © 2025 CardMaps. Créez des cartes interactives exceptionnelles.
        </p>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { MapIcon, PencilIcon, ShareIcon, ChartBarIcon } from '@heroicons/vue/24/outline'

const featuresSection = ref<HTMLElement>()

function scrollToFeatures() {
  featuresSection.value?.scrollIntoView({ behavior: 'smooth' })
}
</script>