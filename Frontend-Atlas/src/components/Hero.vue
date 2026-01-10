<script setup lang="ts">
import { RocketLaunchIcon } from "@heroicons/vue/24/outline";
import { EyeIcon } from "@heroicons/vue/24/outline";
</script>

<template>
  <section class="relative py-10 px-4 sm:px-6 lg:px-8 overflow-hidden">
    <!-- Background decoration -->
    <div
      class="absolute inset-0 bg-gradient-to-br from-primary-50 to-secondary-50 opacity-50"
    ></div>

    <div class="relative max-w-7xl mx-auto">
      <div class="text-center">
        <!-- Badge -->
        <div
          class="inline-flex items-center px-4 py-2 rounded-full bg-primary-100 text-primary-800 text-sm font-medium mb-8 animate-fade-in"
        >
          <RocketLaunchIcon class="w-5 h-5 mr-2 text-primary-600" />
          Nouvelle plateforme de gestion de cartes
        </div>

        <!-- Main heading -->
        <h1
          class="text-4xl md:text-6xl font-bold text-gray-900 mb-6 animate-slide-up text-balance"
        >
          Gérez et visualisez vos
          <span
            class="text-transparent bg-clip-text bg-gradient-to-r from-primary-600 to-secondary-600"
          >
            cartes
          </span>
          facilement
        </h1>

        <!-- Subtitle -->
        <p
          class="text-xl text-gray-600 mb-12 max-w-3xl mx-auto leading-relaxed animate-slide-up"
        >
          Une solution moderne et intuitive pour importer, organiser et explorer
          vos cartes avec des outils de visualisation avancés et une interface
          utilisateur épurée.
        </p>

        <!-- CTA Buttons -->
        <div
          class="flex flex-col sm:flex-row gap-4 justify-center animate-slide-up"
        >
          <RouterLink
            to="/demo"
            class="btn-secondary px-8 py-4 text-lg hover:scale-105 transform transition-all inline-flex items-center justify-center"
          >
            <EyeIcon class="w-5 h-5 mr-2 text-primary-600" />
            Voir la démo
          </RouterLink>
        </div>
      </div>
    </div>
  </section>
</template>
