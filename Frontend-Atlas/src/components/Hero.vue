<script setup lang="ts">
// Component logic can be added here
</script>

<template>
  <section class="relative py-20 px-4 sm:px-6 lg:px-8 overflow-hidden">
    <!-- Background decoration -->
    <div class="absolute inset-0 bg-gradient-to-br from-primary-50 to-secondary-50 opacity-50"></div>
    
    <div class="relative max-w-7xl mx-auto">
      <div class="text-center">
        <!-- Badge -->
        <div class="inline-flex items-center px-4 py-2 rounded-full bg-primary-100 text-primary-800 text-sm font-medium mb-8 animate-fade-in">
          <span class="mr-2">🚀</span>
          Nouvelle plateforme de gestion de cartes
        </div>
        
        <!-- Main heading -->
        <h1 class="text-4xl md:text-6xl font-bold text-gray-900 mb-6 animate-slide-up text-balance">
          Gérez et visualisez vos 
          <span class="text-transparent bg-clip-text bg-gradient-to-r from-primary-600 to-secondary-600">
            cartes
          </span>
          facilement
        </h1>
        
        <!-- Subtitle -->
        <p class="text-xl text-gray-600 mb-12 max-w-3xl mx-auto leading-relaxed animate-slide-up">
          Une solution moderne et intuitive pour importer, organiser et explorer vos cartes 
          avec des outils de visualisation avancés et une interface utilisateur épurée.
        </p>
        
        <!-- CTA Buttons -->
        <div class="flex flex-col sm:flex-row gap-4 justify-center mb-16 animate-slide-up">
          <button class="btn-primary px-8 py-4 text-lg hover:scale-105 transform transition-all">
            <span class="mr-2">📤</span>
            Commencer l'upload
          </button>
          <button class="btn-secondary px-8 py-4 text-lg hover:scale-105 transform transition-all">
            <span class="mr-2">👁️</span>
            Voir la démo
          </button>
        </div>
        
        <!-- Stats -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-8 max-w-2xl mx-auto">
          <div class="text-center">
            <div class="text-3xl font-bold text-primary-600 mb-2">100+</div>
            <div class="text-gray-600">Formats supportés</div>
          </div>
          <div class="text-center">
            <div class="text-3xl font-bold text-secondary-600 mb-2">24/7</div>
            <div class="text-gray-600">Support disponible</div>
          </div>
          <div class="text-center">
            <div class="text-3xl font-bold text-accent-600 mb-2">99.9%</div>
            <div class="text-gray-600">Temps de disponibilité</div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>