<template>
  <div class="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
    <Header />
    
    <main>
      <Hero />
      
      <!-- Features Section -->
      <section class="px-4 py-4 sm:px-6 lg:px-8">
        <div class="max-w-7xl mx-auto">
          <div class="text-center mb-12">
            <h2 class="text-3xl font-bold text-gray-900 mb-4">
              Fonctionnalités principales
            </h2>
            <p class="text-lg text-gray-600 max-w-2xl mx-auto">
              Une plateforme complète pour la gestion et la visualisation de vos cartes
            </p>
          </div>
          
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            <FeatureCard
              v-for="feature in features"
              :key="feature.title"
              :title="feature.title"
              :description="feature.description"
              :icon="feature.icon"
            />
          </div>
        </div>
      </section>
      
      <!-- CTA Section -->
      <section class="py-16 px-4 sm:px-6 lg:px-8 bg-white">
        <div class="max-w-4xl mx-auto text-center">
          <h2 class="text-3xl font-bold text-gray-900 mb-4">
            Prêt à commencer ?
          </h2>
          <p class="text-lg text-gray-600 mb-8">
            Découvrez la puissance de notre plateforme de gestion de cartes
          </p>
          <div class="flex flex-col sm:flex-row gap-4 justify-center">
            <RouterLink to="/connexion" class="btn-primary px-8 py-3 text-lg">
              Commencer maintenant
            </RouterLink>
          </div>
        </div>
      </section>
    </main>
    
    <!-- Footer -->
    <Footer />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Header from '../components/Header.vue'
import Footer from '../components/Footer.vue'
import Hero from '../components/Hero.vue'
import FeatureCard from '../components/FeatureCard.vue'
import 'leaflet/dist/leaflet.css';
import { ArrowUpTrayIcon, MapIcon, ClipboardDocumentListIcon } from '@heroicons/vue/24/outline'


const features = ref([
  {
    title: 'Upload de cartes',
    description: 'Importez facilement vos cartes depuis votre ordinateur avec support de multiples formats.',
    icon: ArrowUpTrayIcon,
    color: 'primary'
  },
  {
    title: 'Visualisation avancée',
    description: 'Explorez vos cartes avec des outils de visualisation interactifs et intuitifs.',
    icon: MapIcon,
    color: 'secondary'
  },
  {
    title: 'Gestion organisée',
    description: 'Organisez et gérez votre collection de cartes avec des outils de classement.',
    icon: ClipboardDocumentListIcon,
    color: 'accent'
  }
])
</script>

<style scoped>
/* Additional component-specific styles can go here */
</style>
